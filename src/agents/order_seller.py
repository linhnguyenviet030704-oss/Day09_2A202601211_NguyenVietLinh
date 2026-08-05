"""
Order & Seller Agent (Member B).

Extracts order status, item/seller facts, and whether any seller handed
an item to the carrier after that item's shipping_limit_date. This is
the fact-finding half (with Delivery Agent) that decides
late_delivery_seller vs late_delivery_logistics in policy.py.

Deterministic: this is direct comparison/extraction over CSV-derived
fields, not a judgment call, so an LLM call would add risk (misreading
a date) without upside. See architecture.md for why the investigation
agents are implemented this way.

Output matches the team contract:
{order_status, items[{item_id,seller_id,price,freight_value,shipping_limit_date}],
 seller_ids[], delivered_carrier_date, seller_handoff_late,
 late_seller_ids[], late_item_ids[]}
"""
from __future__ import annotations

import pandas as pd

from src.core.data import OrderBundle


def run_order_seller_agent(bundle: OrderBundle) -> dict:
    order = bundle.order or {}
    order_status = order.get("order_status")
    carrier_date = order.get("order_delivered_carrier_date")

    items = []
    late_seller_ids = []
    late_item_ids = []
    seller_ids = []

    for it in bundle.items:
        sid = it["seller_id"]
        seller_ids.append(sid)
        items.append(
            {
                "item_id": int(it["order_item_id"]),
                "seller_id": sid,
                "price": float(it["price"]),
                "freight_value": float(it["freight_value"]),
                "shipping_limit_date": str(it["shipping_limit_date"]),
            }
        )
        limit = it["shipping_limit_date"]
        if pd.notna(carrier_date) and pd.notna(limit) and carrier_date > limit:
            late_seller_ids.append(sid)
            late_item_ids.append(int(it["order_item_id"]))

    return {
        "order_status": order_status,
        "items": items,
        "seller_ids": sorted(set(seller_ids)),
        "delivered_carrier_date": str(carrier_date) if pd.notna(carrier_date) else None,
        "seller_handoff_late": len(late_seller_ids) > 0,
        "late_seller_ids": sorted(set(late_seller_ids)),
        "late_item_ids": sorted(set(late_item_ids)),
    }
