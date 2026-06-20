#!/usr/bin/env python3
"""
giving.py — the giving ledger, wired into the hive
==================================================

A self-contained, hash-chained giving ledger (donation -> asset -> income ->
give -> job) the hive console reads and writes. Same discipline as the public
diabeticledger.com surface: tamper-evident, no PHI (money layer only).

State lives in .state/giving.jsonl (instance data). Stdlib only.
"""

import hashlib
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, ".state", "giving.jsonl")
ZERO = "0" * 64


def _canon(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(prev, body):
    return hashlib.sha256((prev + _canon(body)).encode("utf-8")).hexdigest()


def now():
    return datetime.now().strftime("%Y-%m-%d")


def load():
    if not os.path.exists(LEDGER):
        return []
    out = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append(fields):
    led = load()
    prev = led[-1]["hash"] if led else ZERO
    body = {"seq": len(led), "prev_hash": prev, **fields}
    rec = {**body, "hash": _hash(prev, body)}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    return rec


def verify():
    prev = ZERO
    for rec in load():
        body = {k: v for k, v in rec.items() if k != "hash"}
        if rec.get("prev_hash") != prev or _hash(prev, body) != rec.get("hash"):
            return False, rec["seq"]
        prev = rec["hash"]
    return True, len(load())


def totals():
    led = load()
    t = {"donated_usd": 0, "earned_usd": 0, "given_usd": 0, "jobs_paid_usd": 0,
         "donations": 0, "assets": 0, "gives": 0, "jobs": 0, "by_donor": {}}
    for r in led:
        k = r.get("kind")
        if k == "donation":
            t["donated_usd"] += r.get("value_usd", 0); t["donations"] += 1
            t["by_donor"][r.get("donor", "?")] = t["by_donor"].get(r.get("donor", "?"), 0) + r.get("value_usd", 0)
        elif k == "asset":
            t["assets"] += 1
        elif k == "income":
            t["earned_usd"] += r.get("amount_usd", 0)
        elif k == "give":
            t["given_usd"] += r.get("value_usd", 0); t["gives"] += 1
        elif k == "job":
            t["jobs_paid_usd"] += r.get("pay_usd", 0); t["jobs"] += 1
    ok, n = verify()
    t["chain_ok"] = ok; t["count"] = len(led)
    return t


# record helpers
def add_donation(donor, form, item, value, note=""):
    return append({"kind": "donation", "date": now(), "donor": donor[:80], "form": form,
                   "item": item[:120], "value_usd": max(0, int(value or 0)), "note": note[:200]})


def add_give(to, need, value, funded="income", by="OpenDiabetic"):
    return append({"kind": "give", "date": now(), "recipient": to[:80], "need": need[:120],
                   "value_usd": max(0, int(value or 0)), "funded_from": funded, "fulfilled_by": by})


def add_job(worker, task, pay):
    return append({"kind": "job", "date": now(), "worker": worker[:80], "task": task[:160],
                   "pay_usd": max(0, int(pay or 0))})
