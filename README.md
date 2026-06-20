# OpenDiabetic Compute — the hive

**Privacy-first diabetic compute infrastructure.** The foundation half of the house.

*OpenDiabetic is the hive. [LocalDiabetic](https://github.com/SudoSuOps/LocalDiabetic-Home-Vault)
is the healers.*

---

## What this is

OpenDiabetic is the **public-good compute layer** for diabetic life support. Donors
contribute compute — a GPU, a NAS, a Jetson — and the foundation uses it to run
**open models, education datasets, and research** that help diabetics. The donor/worker
spine lives here: register a node, post a job, run it, keep a receipt.

> **Donate compute. Help diabetics. Support research. Keep data local.**

## What this is **not**

The hive **never touches a patient record.** It runs only open and synthetic data.
A person's records live in their LocalDiabetic vault, on their own box, and never
enter the compute network. See `COMPUTE-INVARIANT.md` — it's the law this is built on.

---

## The firewall (why this matters)

OpenDiabetic and LocalDiabetic have **opposite** invariants, and that's the whole design:

| | LocalDiabetic (healers) | OpenDiabetic (hive) |
|---|---|---|
| **Invariant** | Records **never leave** the box | Records **never enter** the compute |

**Models flow DOWN** to the box · **Receipts flow UP** to the ledger · **PHI crosses NEVER.**

The foundation gives a person world-class compute and models without ever seeing a
single record. Extractive health-tech is built on the data crossing. We're built on
it never crossing.

---

## The lifecycle

```bash
# a donor contributes a rig
python3 odc.py register-node --id whale-5090 --owner Donovan --kind gpu \
    --gpu "RTX 5090" --vram 32 --location "home rig"
python3 odc.py heartbeat --node whale-5090

# the foundation posts a NON-PHI job (firewall-checked)
python3 odc.py post-job --kind model-serve --model diabetic-life-assistant-open \
    --data open:diabetic-education-v1 --desc "serve plain-language helper"

# the node runs it and a receipt is minted
python3 odc.py lease --node whale-5090
python3 odc.py complete --job job-0001 --gpu-seconds 42

python3 odc.py ledger     # public-good view + receipts
python3 odc.py verify     # check the hash-chain
```

## Commands

| Command | What |
|---|---|
| `register-node` | A donor registers a GPU / NAS / Jetson. |
| `nodes` | List nodes + status + contributed compute. |
| `heartbeat --node` | A node reports alive + available. |
| `post-job` | Foundation posts a NON-PHI job (firewall-enforced). |
| `jobs` | List jobs + status. |
| `lease --node` | A node takes the next queued job. |
| `complete --job --gpu-seconds` | Finish a job, mint a hash-chained compute receipt. |
| `ledger` | The public-good ledger: who donated what, every receipt, chain status. |
| `verify` | Verify the receipt hash-chain (tamper-evident). |

## How the firewall is enforced (in code, not by promise)

1. **Typed data refs** — a job's `--data` must start with `open:` / `synthetic:` / `model:`.
   A vault path or untyped ref is **refused**.
2. **PHI backstop** — model / data / description scanned for PHI markers (patient, record,
   vault, glucose, insulin, a LocalDiabetic path…). A hit **refuses the job**.
3. **Every receipt records `phi_touched: false`.**
4. **Hash-chained ledger** — mutate one receipt and `verify` breaks the chain.

---

## Roadmap

- **v0.1 (here)** — node registry + hash-chained compute ledger + firewall, as an
  auditable local tool. Proven end-to-end.
- **v0.2** — HTTP worker contract (register → bearer → heartbeat → lease → complete over
  the network), reusing the proven `defendable-router` spine.
- **v0.3** — the compute donation surface (opendiabetic.com intake) + the first open
  diabetic-life-assistant model the LocalDiabetic vault calls down.

---

*OpenDiabetic Compute v0.1 · the hive · donated compute, records stay local.*
