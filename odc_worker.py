#!/usr/bin/env python3
"""
OpenDiabetic Compute — edge worker (v0.2 worker contract)
=========================================================

Runs on an edge node (e.g. sigedge, a Jetson Orin Nano). Registers with the
hive, heartbeats, leases NON-PHI jobs, runs them on the node's LOCAL ollama
model, and reports completion. This is HAT 1: the bee plugging into the hive.

THE FIREWALL still holds: the hive only ever hands this worker open/synthetic
jobs (records never enter the hive). The local model here runs OPEN work; the
same model, pointed at a user's vault, runs LocalDiabetic's local helper — but
that PHI path stays entirely on the box and never calls the hive.

  python3 odc_worker.py --hive http://192.168.0.102:8770 --token <T> \
      --node sigedge --owner Donovan --gpu "Orin Nano" --vram 8 \
      --ollama-model hf.co/LiquidAI/LFM2.5-8B-A1B-GGUF:Q4_K_M --once

Stdlib only. Loops every --interval seconds, or runs one cycle with --once.
"""

import argparse
import json
import time
import urllib.request

UA = "OpenDiabetic-Worker/0.2"


def api(url, token, payload=None, method="POST", timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", UA)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def run_on_ollama(model, prompt, timeout=120):
    """Exercise the local model. Returns (elapsed_seconds, ok, preview)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": ("You are a diabetic-life ORGANIZER. You never diagnose, never "
                   "change medications. You organize and explain in plain language, "
                   "and you always say to confirm medical decisions with a clinician."),
        "stream": False,
        "options": {"num_predict": 80},
    }
    t0 = time.time()
    try:
        out = api("http://127.0.0.1:11434/api/generate", None, payload, timeout=timeout)
        elapsed = time.time() - t0
        text = (out.get("response") or "").strip().replace("\n", " ")
        return elapsed, True, text[:140]
    except Exception as e:
        return time.time() - t0, False, f"(ollama error: {e})"


def cycle(args):
    hive, tok = args.hive.rstrip("/"), args.token
    # register (idempotent) + heartbeat
    api(f"{hive}/nodes/register", tok, {
        "id": args.node, "owner": args.owner, "kind": "jetson",
        "gpu": args.gpu, "vram": args.vram, "location": args.location})
    api(f"{hive}/nodes/heartbeat", tok, {"node": args.node})
    # lease
    r = api(f"{hive}/nodes/lease", tok, {"node": args.node})
    job = r.get("job")
    if not job:
        print(f"[{args.node}] heartbeat ok — no queued jobs")
        return False
    print(f"[{args.node}] leased {job['id']} [{job['kind']}] model={job['model']} data={job['data']}")
    # run it on the local model (open work only)
    prompt = job.get("desc") or "In plain language, what makes a balanced plate?"
    elapsed, ok, preview = run_on_ollama(args.ollama_model, prompt)
    gpu_s = max(1, round(elapsed))
    print(f"[{args.node}] ran locally on {args.ollama_model}: {elapsed:.1f}s ok={ok}")
    print(f"           model said: \"{preview}\"")
    # complete -> hive mints the receipt
    c = api(f"{hive}/jobs/complete", tok, {"job": job["id"], "gpu_seconds": gpu_s, "node": args.node})
    print(f"[{args.node}] ✓ completed {job['id']} — receipt #{c['receipt_seq']} "
          f"phi_touched:{c['phi_touched']} hash={c['hash'][:16]}…")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hive", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--node", default="sigedge")
    p.add_argument("--owner", default="Donovan")
    p.add_argument("--gpu", default="Orin Nano")
    p.add_argument("--vram", type=int, default=8)
    p.add_argument("--location", default="edge")
    p.add_argument("--ollama-model", required=True)
    p.add_argument("--interval", type=int, default=20)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    if a.once:
        cycle(a)
        return
    print(f"[{a.node}] worker loop — hive {a.hive} every {a.interval}s")
    while True:
        try:
            cycle(a)
        except Exception as e:
            print(f"[{a.node}] cycle error (fail-open, will retry): {e}")
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
