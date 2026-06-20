# The Compute Invariant — OpenDiabetic Law

The mirror of LocalDiabetic's `HARD-INVARIANT.md`. Together they form a firewall.

---

## The invariant

> **Raw personal health records never enter the OpenDiabetic compute network.**

- The hive runs **only** open models, synthetic/education data, and research jobs.
- A LocalDiabetic vault's records stay on the user's box. **They never become a job.**
- Every job must declare its data as **open** or **synthetic** — never a vault path,
  never a patient record.
- Every job mints a **compute receipt** proving `phi_touched: false`.

---

## The firewall

OpenDiabetic (the hive) and LocalDiabetic (the healers) are two halves with
**opposite** invariants. That opposition is the whole design:

| | LocalDiabetic (healers) | OpenDiabetic (hive) |
|---|---|---|
| **Invariant** | Records **never leave** the box | Records **never enter** the compute |
| **Holds** | Your PHI, your vault | Open models, synthetic/education data, research |

**Only three things cross the wall:**

- **Models flow DOWN** — the hive trains/serves an open helper → it lands on your
  Jetson or box, where it meets your data locally.
- **Receipts flow UP** — proof of what compute did. Never the data it touched.
- **PHI crosses NEVER.** In either direction.

The foundation can give a person world-class compute and models **without ever
seeing a single patient record**, because records and compute live on opposite
sides of the wall. Extractive health-tech is built on the data crossing. We are
built on it never crossing.

---

## How it's enforced (structurally, not by promise)

1. **Data references are typed.** A job's data ref must begin with `open:`,
   `synthetic:`, or `model:`. A vault path or untyped reference is **refused**.
2. **PHI backstop.** Job descriptions, models, and data refs are scanned for PHI
   markers (patient, record, vault, glucose, insulin, a LocalDiabetic path…). A hit
   **refuses the job** and raises a flag.
3. **Every receipt records `phi_touched: false`.** If a job could not honor that, it
   does not run.
4. **Receipts are hash-chained.** The compute ledger is tamper-evident: mutate one
   receipt and `verify` breaks the chain — the same proof-of-execution discipline
   used across the Defendable house.

---

*If a job cannot honor this invariant, the job does not run. Full stop.*
