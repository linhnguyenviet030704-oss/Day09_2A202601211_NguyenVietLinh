"""
Delivery Agent (Member B).

Compares actual delivery timestamp against the estimated delivery date.
Deterministic for the same reason as order_seller.py: a plain date
comparison should not be delegated to an LLM.

Output matches the team contract:
{estimated_date, delivered_customer_date, delivered_late, carrier_after_limit}
"""
from __future__ import annotations

import pandas as pd

from src.core.data import OrderBundle


def run_delivery_agent(bundle: OrderBundle, order_seller: dict) -> dict:
    order = bundle.order or {}
    estimated = order.get("order_estimated_delivery_date")
    delivered_customer = order.get("order_delivered_customer_date")

    delivered_late = bool(
        pd.notna(estimated) and pd.notna(delivered_customer) and delivered_customer > estimated
    )

    return {
        "estimated_date": str(estimated) if pd.notna(estimated) else None,
        "delivered_customer_date": str(delivered_customer) if pd.notna(delivered_customer) else None,
        "delivered_late": delivered_late,
        "carrier_after_limit": order_seller["seller_handoff_late"],
    }
