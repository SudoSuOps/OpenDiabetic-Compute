#!/usr/bin/env python3
"""
OpenDiabetic Compute — hive server (v0.2 worker contract)
=========================================================

The HTTP face of the hive. Runs on the NAS. Nodes (edge boxes like sigedge)
call in over the LAN / Tailscale to register, heartbeat, lease NON-PHI jobs,
and report completion — every completion mints a hash-chained compute receipt.

Reuses the firewall + registry + ledger from odc.py. Stdlib only.

  python3 odc_server.py --port 8770 --bind 0.0.0.0

Worker endpoints require a bearer token (auto-created at .state/worker_token).
The firewall (no PHI ever enters) is enforced on POST /jobs/post exactly as in
the CLI: typed data refs only, PHI-marker scan, every receipt phi_touched:false.
"""

import argparse
import json
import mimetypes
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import odc  # reuse registry / firewall / ledger primitives

TOKEN_FILE = os.path.join(odc.STATE_DIR, "worker_token")
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")


def stats():
    """Public, no-PHI rollup for the OpenDiabetic ops dashboard."""
    nodes = odc.load_nodes()
    jobs = odc.load_jobs()
    led = odc.load_ledger()
    ok, n = odc.verify_ledger()
    t = {"nodes": len(nodes), "online": sum(1 for x in nodes.values() if x.get("status") in ("available", "busy")),
         "jobs_done": sum(1 for j in jobs.values() if j.get("status") == "done"),
         "jobs_queued": sum(1 for j in jobs.values() if j.get("status") == "queued"),
         "compute_receipts": sum(1 for r in led if r.get("kind") == "compute-receipt"),
         "gpu_seconds": sum(r.get("gpu_seconds", 0) for r in led),
         "donations": sum(1 for r in led if r.get("kind") == "donation"),
         "donated_usd": sum(r.get("value_usd", 0) for r in led if r.get("kind") == "donation"),
         "chain_ok": ok, "chain_len": n}
    return t


def worker_token():
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE).read().strip()
    os.makedirs(odc.STATE_DIR, exist_ok=True)
    t = "odc_" + secrets.token_hex(16)
    open(TOKEN_FILE, "w").write(t)
    return t


TOKEN = None  # set in main


class Hive(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self):
        rel = "index.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0]
        path = os.path.normpath(os.path.join(APP_DIR, rel))
        if not path.startswith(APP_DIR) or not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _authed(self):
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "service": "opendiabetic-hive", "v": "0.2"})
        if self.path == "/nodes":
            return self._send(200, {"nodes": list(odc.load_nodes().values())})
        if self.path == "/jobs":
            return self._send(200, {"jobs": list(odc.load_jobs().values())})
        if self.path == "/ledger":
            ok, n = odc.verify_ledger()
            return self._send(200, {"receipts": odc.load_ledger(), "chain_ok": ok, "count": n})
        if self.path == "/verify":
            ok, n = odc.verify_ledger()
            return self._send(200, {"chain_ok": ok, "at": n})
        if self.path == "/api/stats":
            return self._send(200, stats())
        # anything else -> serve the OpenDiabetic ops app (static)
        self._serve_static()

    def do_POST(self):
        # ALL writes require the operator/worker bearer token (safe for public exposure;
        # the public console reads freely, but donate/post-job/worker actions need the token).
        if not self._authed():
            return self._send(401, {"error": "operator token required"})
        # foundation posts a job (firewall-enforced)
        if self.path == "/jobs/post":
            b = self._body()
            try:
                odc.assert_non_phi(b.get("kind", ""), b.get("model", ""), b.get("data", ""), b.get("desc", ""))
            except ValueError as e:
                return self._send(403, {"error": "firewall", "detail": str(e)})
            jobs = odc.load_jobs()
            jid = f"job-{len(jobs)+1:04d}"
            jobs[jid] = {"id": jid, "kind": b["kind"], "model": b["model"], "data": b["data"],
                         "desc": b.get("desc", ""), "phi": False, "status": "queued",
                         "posted_at": odc.now_iso(), "node": None}
            odc._save(odc.JOBS_FILE, jobs)
            return self._send(200, {"job": jobs[jid]})

        # donor intake (public) — records a hash-chained donation, no PHI
        if self.path == "/api/donate":
            b = self._body()
            form = b.get("form", "cash")
            if form not in ("cash", "compute", "device"):
                return self._send(400, {"error": "form must be cash/compute/device"})
            rec = odc.append_receipt({
                "kind": "donation", "donor": (b.get("donor") or "Anonymous")[:80],
                "form": form, "item": (b.get("item") or form)[:120],
                "value_usd": max(0, int(b.get("value_usd") or 0)),
                "note": (b.get("note") or "")[:200], "received_at": odc.now_iso()})
            return self._send(200, {"ok": True, "seq": rec["seq"], "hash": rec["hash"]})

        if self.path == "/nodes/register":
            b = self._body()
            nodes = odc.load_nodes()
            nodes[b["id"]] = {**nodes.get(b["id"], {}),
                "id": b["id"], "owner": b.get("owner", "?"), "kind": b.get("kind", "?"),
                "gpu": b.get("gpu", ""), "vram_gb": b.get("vram", 0), "location": b.get("location", ""),
                "registered_at": odc.now_iso(), "last_heartbeat": odc.now_iso(),
                "status": "available", "jobs_done": nodes.get(b["id"], {}).get("jobs_done", 0),
                "gpu_seconds": nodes.get(b["id"], {}).get("gpu_seconds", 0)}
            odc._save(odc.NODES_FILE, nodes)
            return self._send(200, {"node": nodes[b["id"]]})

        if self.path == "/nodes/heartbeat":
            b = self._body(); nodes = odc.load_nodes()
            if b["node"] not in nodes:
                return self._send(404, {"error": "unknown node"})
            nodes[b["node"]]["last_heartbeat"] = odc.now_iso()
            if nodes[b["node"]]["status"] in ("registered", "offline"):
                nodes[b["node"]]["status"] = "available"
            odc._save(odc.NODES_FILE, nodes)
            return self._send(200, {"ok": True, "status": nodes[b["node"]]["status"]})

        if self.path == "/nodes/lease":
            b = self._body(); nodes, jobs = odc.load_nodes(), odc.load_jobs()
            if b["node"] not in nodes:
                return self._send(404, {"error": "unknown node"})
            queued = [j for j in jobs.values() if j["status"] == "queued"]
            if not queued:
                return self._send(200, {"job": None})
            job = queued[0]
            job["status"] = "leased"; job["node"] = b["node"]; job["leased_at"] = odc.now_iso()
            nodes[b["node"]]["status"] = "busy"
            odc._save(odc.JOBS_FILE, jobs); odc._save(odc.NODES_FILE, nodes)
            return self._send(200, {"job": job})

        if self.path == "/jobs/complete":
            b = self._body(); nodes, jobs = odc.load_nodes(), odc.load_jobs()
            jid = b["job"]
            if jid not in jobs:
                return self._send(404, {"error": "unknown job"})
            job = jobs[jid]; node_id = job.get("node")
            rec = odc.append_receipt({
                "kind": "compute-receipt", "job_id": jid, "job_kind": job["kind"],
                "model": job["model"], "data": job["data"], "node": node_id,
                "owner": nodes.get(node_id, {}).get("owner"),
                "gpu_seconds": b.get("gpu_seconds", 0), "phi_touched": False,
                "completed_at": odc.now_iso()})
            job["status"] = "done"; job["receipt_seq"] = rec["seq"]
            if node_id in nodes:
                nodes[node_id]["status"] = "available"
                nodes[node_id]["jobs_done"] += 1
                nodes[node_id]["gpu_seconds"] += b.get("gpu_seconds", 0)
            odc._save(odc.JOBS_FILE, jobs); odc._save(odc.NODES_FILE, nodes)
            return self._send(200, {"receipt_seq": rec["seq"], "hash": rec["hash"], "phi_touched": False})

        self._send(404, {"error": "not found"})


def main():
    global TOKEN
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--bind", default="0.0.0.0")
    a = p.parse_args()
    TOKEN = worker_token()
    print(f"OpenDiabetic hive server on {a.bind}:{a.port}  (worker token at {TOKEN_FILE})")
    ThreadingHTTPServer((a.bind, a.port), Hive).serve_forever()


if __name__ == "__main__":
    main()
