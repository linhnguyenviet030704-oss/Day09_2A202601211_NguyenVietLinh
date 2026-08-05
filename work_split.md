# Project Plan

## Phase 0 — Shared Foundation (All 3 Members, ~30 min)

- Repository layout:
  ```
  src/
    agents/
    core/
    run.py
  ```
- `.env` (Groq API key, gitignored) + shared `llm_client.py` wrapper (OpenAI-compatible → Groq `llama-3.1-8b-instant`)
- Data loader (`core/data.py`)
  - Load all 9 CSV files once.
  - Index data by `order_id`.
  - Provide `get_order_bundle(order_id)` returning:
    - Order row
    - Order items
    - Payments
    - Seller rows
- Agree on the intermediate contract below. This is the key interface that enables parallel development.

### Intermediate Contract

Each investigation agent returns a small JSON. The Policy Agent consumes all three.

```json
{
  "order_seller": {
    "order_status": "...",
    "items": [
      {
        "item_id": "...",
        "seller_id": "...",
        "price": 0,
        "freight_value": 0,
        "shipping_limit_date": "..."
      }
    ],
    "seller_ids": [],
    "delivered_carrier_date": "...",
    "seller_handoff_late": false
  },
  "delivery": {
    "estimated_date": "...",
    "delivered_customer_date": "...",
    "delivered_late": false,
    "carrier_after_limit": false
  },
  "payment": {
    "payments": [
      {
        "sequential": 1,
        "value": 0
      }
    ],
    "payment_total": 0,
    "item_total": 0,
    "freight_total": 0,
    "num_rows": 0,
    "reconciled": true,
    "split_payment": false
  }
}
```

---

# Member A — Data + Coordinator + Runner (Backbone)

| Owns | Files | Deliverable |
|------|-------|-------------|
| Data loader & order lookup | `core/data.py` | `get_order_bundle()` |
| Coordinator Agent | `agents/coordinator.py` | Dispatch → collect → assemble final output schema |
| Batch runner (50 cases) | `run.py` | Write `output/EC_*.json` |
| Trace & metadata | `logging/trace.jsonl`<br>`logging/metadata.json` | Real run trace, model/size/framework |
| Architecture document | `architecture.md` | Agent diagram, roles, handoff flow |

### Responsibilities

- Assemble the final output schema.
- Enforce submission constraints:
  - Maximum 5 IDs
  - Maximum 10 evidence items
  - Other required caps

---

# Member B — Investigation Agents

| Owns | Files | Deliverable |
|------|-------|-------------|
| Order & Seller Agent | `agents/order_seller.py` | Order status, items, seller IDs, `seller_handoff_late` (`carrier_date > shipping_limit`) |
| Delivery Agent | `agents/delivery.py` | `delivered_late` (`delivered > estimated`), `carrier_after_limit` |

These two agents together determine whether the dispute is:

- `late_delivery_seller`
- `late_delivery_logistics`

Outputs **must match the shared contract exactly**.

---

# Member C — Payment + Policy + Verifier

| Owns | Files | Deliverable |
|------|-------|-------------|
| Payment Agent | `agents/payment.py` | Reconcile `payment_total` vs `item_total + freight_total` (±0.10), detect `split_payment` |
| Policy Agent | `agents/policy.py` | Apply `EC_POLICY_V1` in priority order → `primary_issue`, responsible party, `root_cause_code`, refund calculation (2 decimal places), actions |
| Verifier Agent | `agents/verifier.py` | Validate evidence IDs exist in CSVs, amounts, schema, and output constraints before writing |

> **Recommendation:** Assign the strongest developer to Member C. This module contains the grading-critical logic (rules, refund calculations, evidence validation) and accounts for approximately **45% of the project score**.

---

# Integration & Individual Deliverables

- Integrate once all contracts pass validation.
- Perform a dry run on **2–3 cases** before full integration.
- Each member completes their own `individual_<HoVaTen>.md`:
  - Fill in name and student ID.
  - Describe the modules they implemented.
- **Note:** The current report template's **Section 7** contains questions from a different (RAG/Crossref) lab. Rewrite this section so it reflects the dispute-resolution workflow instead.
- Before submission, ensure the ZIP contains:
  - `EC_001.json` ... `EC_050.json`
  - No source code
  - No `.env`

---

# Suggested Timeline (09:30–12:30)

| Time | Task |
|------|------|
| 09:30–10:00 | Phase 0 together (loader, LLM client, shared contract) |
| 10:00–11:30 | Parallel development (Members A/B/C) |
| 11:30–12:00 | Integration + dry run (~5 cases) |
| 12:00–12:20 | Full 50-case execution, verify outputs, trace, metadata |
| 12:20–12:30 | Complete reports, commit, package `output/` for submission |