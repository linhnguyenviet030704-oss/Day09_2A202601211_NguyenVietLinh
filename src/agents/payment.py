"""
Payment Agent (Member C).

Reconciles payment rows against item + freight totals for an order.
Deterministic by design: this is pure arithmetic, so an LLM call would
only add cost and non-determinism without improving correctness. See
individual report section 5 for the rationale.

Dependency this file needs from the rest of the pipeline (documented,
not implemented here -- Member A's Coordinator/data loader owns it):
  - a list of item rows for the order, each with at least
    "price" and "freight_value"
  - a list of payment rows for the order, each with at least
    "payment_sequential" and "payment_value"
No other module in this repo is imported.

Output matches the team's shared contract:
{payments, payment_total, item_total, freight_total, num_rows, reconciled, split_payment}
"""
from __future__ import annotations

RECONCILE_TOLERANCE_BRL = 0.10


def run_payment_agent(order_id: str, items: list[dict], payments: list[dict]) -> dict:
    payment_rows = sorted(payments, key=lambda p: p["payment_sequential"])
    payments_out = [
        {"sequential": int(p["payment_sequential"]), "value": round(float(p["payment_value"]), 2)}
        for p in payment_rows
    ]
    payment_total = round(sum(p["value"] for p in payments_out), 2)

    item_total = round(sum(float(it["price"]) for it in items), 2)
    freight_total = round(sum(float(it["freight_value"]) for it in items), 2)

    reconciled = abs(payment_total - round(item_total + freight_total, 2)) <= RECONCILE_TOLERANCE_BRL
    num_rows = len(payments_out)

    return {
        "payments": payments_out,
        "payment_total": payment_total,
        "item_total": item_total,
        "freight_total": freight_total,
        "num_rows": num_rows,
        "reconciled": reconciled,
        "split_payment": num_rows >= 2,
    }
