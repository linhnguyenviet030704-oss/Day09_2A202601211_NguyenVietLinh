# Role A Data Coordinator and Runner Design

**Status:** Approved by the user on 2026-08-05.

## Goal

Implement Role A's data lookup, coordinator orchestration, batch runner, trace, and metadata path so the repository can process `input/EC_001.json` through `input/EC_050.json` and produce matching JSON files in `output/`.

## Scope

Role A owns:

- `src/core/data.py`: pandas-backed order bundle lookup.
- `src/core/coordinator.py`: injected-agent orchestration and final output assembly.
- `src/run.py`: exact 50-case batch execution.
- `logging/trace.jsonl` and `logging/metadata.json`: current-run trace and runtime metadata.
- `requirements.txt`: pandas dependency for the project virtual environment.

Role A does not implement the Order & Seller, Delivery, Payment, Policy, or Verifier agents. Those modules plug into the coordinator through injected callables.

## Architecture

`DataLoader` reads the orders, order-items, payments, and sellers CSVs into pandas DataFrames once. `get_order_bundle(order_id)` returns an `OrderBundle` containing filtered DataFrames for that order and its sellers.

`Coordinator` receives five injected callables:

```text
fact_agent(bundle) -> dict
policy_agent(facts, case) -> dict
verifier(candidate, facts, bundle) -> {"status": str, "errors": list}
```

The three fact agents are called for order/seller, payment, and delivery analysis. The coordinator merges their handoffs, checks required facts, retries only the deficient agent once, passes a copied fact snapshot to Policy, assembles the README output schema, calls Verifier, then writes the output and one trace record only after verification passes.

The batch runner validates that the input set is exactly `EC_001.json` through `EC_050.json`, removes only stale generated `output/EC_*.json` files, rewrites the trace and metadata files, and stops on the first invalid or unverifiable case. It does not generate fallback facts or invalid output.

## Data contract

`OrderBundle` contains four pandas DataFrames:

```text
order: one row or empty
items: zero or more rows
payments: zero or more rows
sellers: zero or more rows referenced by the items
```

CSV values remain in their pandas-loaded form at this boundary. Fact agents own conversion into the shared intermediate handoff contract:

```json
{
  "order_seller": {},
  "delivery": {},
  "payment": {}
}
```

An unknown order returns empty DataFrames. No customer message is used to invent facts.

## State flow

```text
LOAD_CASE
  -> DISPATCH_FACT_AGENTS
  -> MERGE_HANDOFFS
  -> CHECK_COMPLETENESS
  -> REPAIR_ONCE_IF_NEEDED
  -> LOCK_FACTS
  -> POLICY_DECISION
  -> BUILD_FINAL_OUTPUT
  -> VERIFY_OUTPUT
  -> WRITE_OUTPUT_AND_TRACE
```

Completeness checks require order status and payment totals for paid canceled/unavailable orders. Delivered orders require the delivery comparison fields, item shipping-limit information, and item/freight totals. Multiple payment rows require payment totals, order totals, and reconciliation status. Missing facts cause one targeted retry; persistent missing facts remain warnings and are not replaced with guesses.

## Output rules

The coordinator writes the README schema with these deterministic rules:

- Round monetary values to two decimal places.
- Cap each entity ID list at 5, evidence IDs at 10, root causes at 3, responsible parties at 3, and actions at 5.
- Use empty item/seller IDs and `0.0` item/freight totals when the order has no item rows.
- Preserve the policy agent's primary issue, case status, confidence, causes, parties, refund, and actions.
- Let the verifier reject schema, evidence, amount, status, and cap violations before any output file is written.

## Runtime and verification

`requirements.txt` contains pandas. The supported setup is:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Tests use stdlib `unittest` and temporary CSVs. The runner is exercised with injected fakes before the full B/C integration. The final run uses the project virtual environment and must produce exactly 50 JSON files in `output/`, one trace line per case, and metadata containing the model name, parameter size, framework, and Python runtime.

