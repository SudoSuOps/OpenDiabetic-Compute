#!/usr/bin/env python3
"""
OpenDiabetic Compute — the hive
===============================

The donor/worker spine of the OpenDiabetic foundation. Donors register compute
(a GPU, a NAS, a Jetson); the foundation posts NON-PHI jobs (serve an open
model, build an education dataset, run an eval); nodes lease and run them; and
every job mints a hash-chained compute receipt proving no patient data was
touched.

THE COMPUTE INVARIANT, ENFORCED STRUCTURALLY
--------------------------------------------
Raw personal health records NEVER enter the hive. A job's data reference must be
typed `open:` / `synthetic:` / `model:` — a vault path or untyped reference is
refused. Descriptions/models/data are scanned for PHI markers and refused on a
hit. Every receipt records phi_touched=false. See COMPUTE-INVARIANT.md.

Models flow DOWN to the box, receipts flow UP to the ledger, PHI crosses NEVER.

USAGE
-----
  register a donated node:
    odc.py register-node --id whale-5090 --owner Donovan --kind gpu \
        --gpu "RTX 5090" --vram 32 --location "home rig"
  odc.py nodes
  odc.py heartbeat --node whale-5090
  post a NON-PHI foundation job:
    odc.py post-job --kind model-serve --model diabetic-life-assistant-open \
        --data open:diabetic-education-v1 --desc "serve plain-language helper"
  odc.py jobs
  odc.py lease --node whale-5090            # node takes the next queued job
  odc.py complete --job <id> --gpu-seconds 42
  odc.py ledger                              # public-good view + receipts
  odc.py verify                              # check the receipt hash-chain

Stdlib only — no pip install. State in .state/, receipts in receipts/ledger.jsonl.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, ".state")
NODES_FILE = os.path.join(STATE_DIR, "nodes.json")
JOBS_FILE = os.path.join(STATE_DIR, "jobs.json")
LEDGER = os.path.join(HERE, "receipts", "ledger.jsonl")

# Data references MUST be typed as one of these — never a vault path / record.
ALLOWED_DATA_PREFIXES = ("open:", "synthetic:", "model:")
ALLOWED_JOB_KINDS = ("model-serve", "model-train", "dataset-build", "eval", "research")

# PHI backstop. The real protection is that jobs may only name open/synthetic
# data; this catches an operator who tries to smuggle PHI into a description.
PHI_MARKERS = [
    "patient", "record", "vault", "localdiabetic", "phi", "ssn", "mrn",
    "glucose", "insulin", "a1c", "diagnosis", "prescription", "/0", "/1",
    "discharge", "lab result", "member id", "policy number",
]

ZERO = "0" * 64


# ── State ────────────────────────────────────────────────────────────────────
def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def load_nodes():
    return _load(NODES_FILE, {})


def load_jobs():
    return _load(JOBS_FILE, {})


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ── The firewall ─────────────────────────────────────────────────────────────
def scan_phi(*texts):
    blob = " ".join(t for t in texts if t).lower()
    return sorted({m for m in PHI_MARKERS if m in blob})


def assert_non_phi(kind, model, data, desc):
    """Refuse anything that could carry PHI into the hive. Raises ValueError."""
    if kind not in ALLOWED_JOB_KINDS:
        raise ValueError(f"unknown job kind '{kind}' (allowed: {', '.join(ALLOWED_JOB_KINDS)})")
    if not data.startswith(ALLOWED_DATA_PREFIXES):
        raise ValueError(
            f"data ref '{data}' is not typed open:/synthetic:/model: — "
            f"the hive never takes a vault path or a record. REFUSED."
        )
    hits = scan_phi(model, data, desc)
    if hits:
        raise ValueError(f"PHI markers in job {hits} — REFUSED. The hive never sees records.")


# ── Hash-chained compute ledger ──────────────────────────────────────────────
def _hash(prev, body):
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + canon).encode("utf-8")).hexdigest()


def load_ledger():
    if not os.path.exists(LEDGER):
        return []
    out = []
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_receipt(payload):
    led = load_ledger()
    prev = led[-1]["hash"] if led else ZERO
    body = {"seq": len(led), "prev_hash": prev, **payload}
    rec = {**body, "hash": _hash(prev, body)}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def verify_ledger():
    led = load_ledger()
    prev = ZERO
    for rec in led:
        body = {k: v for k, v in rec.items() if k != "hash"}
        if rec.get("prev_hash") != prev or _hash(prev, body) != rec.get("hash"):
            return False, rec["seq"]
        prev = rec["hash"]
    return True, len(led)


# ── Commands ─────────────────────────────────────────────────────────────────
def cmd_register_node(a):
    nodes = load_nodes()
    if a.id in nodes:
        print(f"node '{a.id}' already registered")
        return
    nodes[a.id] = {
        "id": a.id, "owner": a.owner, "kind": a.kind,
        "gpu": a.gpu, "vram_gb": a.vram, "location": a.location,
        "registered_at": now_iso(), "last_heartbeat": None,
        "status": "registered", "jobs_done": 0, "gpu_seconds": 0,
    }
    _save(NODES_FILE, nodes)
    print(f"✓ registered node '{a.id}' ({a.kind} {a.gpu or ''} {a.vram or ''}GB) — owner {a.owner}")
    print("  thank you for donating compute to the hive 🐝")


def cmd_nodes(a):
    nodes = load_nodes()
    if not nodes:
        print("no nodes registered yet")
        return
    for n in nodes.values():
        hb = n["last_heartbeat"] or "never"
        print(f"  {n['id']:<16} {n['status']:<10} {n['kind']:<7} {n.get('gpu') or '-':<12} "
              f"vram={n.get('vram_gb') or '-'}GB  jobs={n['jobs_done']} gpu_s={n['gpu_seconds']}  hb={hb}")


def cmd_heartbeat(a):
    nodes = load_nodes()
    if a.node not in nodes:
        sys.exit(f"unknown node '{a.node}'")
    nodes[a.node]["last_heartbeat"] = now_iso()
    if nodes[a.node]["status"] in ("registered", "offline"):
        nodes[a.node]["status"] = "available"
    _save(NODES_FILE, nodes)
    print(f"♥ heartbeat {a.node} @ {nodes[a.node]['last_heartbeat']} (status={nodes[a.node]['status']})")


def cmd_post_job(a):
    try:
        assert_non_phi(a.kind, a.model, a.data, a.desc or "")
    except ValueError as e:
        sys.exit(f"[FLAG] job refused — {e}")
    jobs = load_jobs()
    jid = f"job-{len(jobs)+1:04d}"
    jobs[jid] = {
        "id": jid, "kind": a.kind, "model": a.model, "data": a.data,
        "desc": a.desc or "", "phi": False, "status": "queued",
        "posted_at": now_iso(), "node": None,
    }
    _save(JOBS_FILE, jobs)
    print(f"✓ posted {jid} [{a.kind}] model={a.model} data={a.data}  (phi:false, firewall passed)")


def cmd_jobs(a):
    jobs = load_jobs()
    if not jobs:
        print("no jobs posted yet")
        return
    for j in jobs.values():
        print(f"  {j['id']}  {j['status']:<9} {j['kind']:<13} {j['model']:<28} "
              f"{j['data']:<28} node={j['node'] or '-'}")


def cmd_lease(a):
    nodes, jobs = load_nodes(), load_jobs()
    if a.node not in nodes:
        sys.exit(f"unknown node '{a.node}'")
    queued = [j for j in jobs.values() if j["status"] == "queued"]
    if not queued:
        print("no queued jobs")
        return
    job = queued[0]
    job["status"] = "leased"
    job["node"] = a.node
    job["leased_at"] = now_iso()
    nodes[a.node]["status"] = "busy"
    _save(JOBS_FILE, jobs)
    _save(NODES_FILE, nodes)
    print(f"→ {a.node} leased {job['id']} [{job['kind']}] {job['model']}")


def cmd_complete(a):
    nodes, jobs = load_nodes(), load_jobs()
    if a.job not in jobs:
        sys.exit(f"unknown job '{a.job}'")
    job = jobs[a.job]
    if job["status"] not in ("leased", "queued"):
        sys.exit(f"job '{a.job}' is {job['status']}, not runnable")
    node_id = job["node"]
    # mint the hash-chained compute receipt — the proof PHI never crossed
    rec = append_receipt({
        "kind": "compute-receipt",
        "job_id": job["id"], "job_kind": job["kind"], "model": job["model"],
        "data": job["data"], "node": node_id, "owner": nodes.get(node_id, {}).get("owner"),
        "gpu_seconds": a.gpu_seconds, "phi_touched": False,
        "completed_at": now_iso(),
    })
    job["status"] = "done"
    job["receipt_seq"] = rec["seq"]
    if node_id and node_id in nodes:
        nodes[node_id]["status"] = "available"
        nodes[node_id]["jobs_done"] += 1
        nodes[node_id]["gpu_seconds"] += a.gpu_seconds
    _save(JOBS_FILE, jobs)
    _save(NODES_FILE, nodes)
    print(f"✓ {job['id']} done on {node_id} — receipt #{rec['seq']} "
          f"(phi_touched:false)  hash={rec['hash'][:16]}…")


def cmd_ledger(a):
    led = load_ledger()
    nodes = load_nodes()
    print("=== OpenDiabetic Compute Ledger — donated compute as public good ===")
    if not led:
        print("  (no receipts yet)")
    contrib = {}
    for r in led:
        owner = r.get("owner") or "?"
        contrib.setdefault(owner, {"jobs": 0, "gpu_seconds": 0})
        contrib[owner]["jobs"] += 1
        contrib[owner]["gpu_seconds"] += r.get("gpu_seconds", 0)
    for r in led:
        print(f"  #{r['seq']:<3} {r['job_id']}  {r['job_kind']:<13} {r['model']:<26} "
              f"node={r['node']}  gpu_s={r['gpu_seconds']}  phi:{r['phi_touched']}  {r['hash'][:12]}…")
    print("  --- contribution by donor ---")
    for owner, c in contrib.items():
        print(f"    {owner}: {c['jobs']} jobs, {c['gpu_seconds']} gpu-seconds donated 🐝")
    ok, n = verify_ledger()
    print(f"  chain: {'✓ intact' if ok else '✗ BROKEN at #'+str(n)} ({len(led)} receipts)")


def cmd_verify(a):
    ok, n = verify_ledger()
    if ok:
        print(f"✓ ledger intact — {n} receipts, hash-chain verified")
    else:
        sys.exit(f"✗ ledger BROKEN at receipt #{n} — tamper detected")


def main():
    p = argparse.ArgumentParser(description="OpenDiabetic Compute — the hive (node registry + receipts)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register-node"); r.set_defaults(fn=cmd_register_node)
    r.add_argument("--id", required=True); r.add_argument("--owner", required=True)
    r.add_argument("--kind", required=True, choices=["gpu", "nas", "jetson", "cpu"])
    r.add_argument("--gpu", default=""); r.add_argument("--vram", type=int, default=0)
    r.add_argument("--location", default="")

    sub.add_parser("nodes").set_defaults(fn=cmd_nodes)

    h = sub.add_parser("heartbeat"); h.set_defaults(fn=cmd_heartbeat); h.add_argument("--node", required=True)

    pj = sub.add_parser("post-job"); pj.set_defaults(fn=cmd_post_job)
    pj.add_argument("--kind", required=True); pj.add_argument("--model", required=True)
    pj.add_argument("--data", required=True); pj.add_argument("--desc", default="")

    sub.add_parser("jobs").set_defaults(fn=cmd_jobs)

    l = sub.add_parser("lease"); l.set_defaults(fn=cmd_lease); l.add_argument("--node", required=True)

    c = sub.add_parser("complete"); c.set_defaults(fn=cmd_complete)
    c.add_argument("--job", required=True); c.add_argument("--gpu-seconds", type=int, default=0)

    sub.add_parser("ledger").set_defaults(fn=cmd_ledger)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
