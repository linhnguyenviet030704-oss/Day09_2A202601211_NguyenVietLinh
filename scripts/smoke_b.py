"""Independent smoke test for Member B's agents (order_seller + delivery).

Builds an order bundle straight from the CSVs for one or more input cases and
runs both agents. The loader here is a TEST STUB — in the real pipeline Member A's
data loader supplies the bundle; Member B's agents only consume it.

Usage:
    python scripts/smoke_b.py                 # runs EC_001, EC_002, EC_003
    python scripts/smoke_b.py EC_010 EC_042   # specific cases
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import delivery, order_seller  # noqa: E402

DATA = ROOT / "data"
INPUT = ROOT / "input"

_orders = None
_items = None


def _load_tables():
    """Load the two CSVs Member B needs, once, as strings with None for blanks."""
    global _orders, _items
    if _orders is None:
        _orders = pd.read_csv(DATA / "olist_orders_dataset.csv", dtype=str)
        _items = pd.read_csv(DATA / "olist_order_items_dataset.csv", dtype=str)


def _none(v):
    return None if (v is None or (isinstance(v, float)) or pd.isna(v)) else v


def build_bundle(case_id: str) -> dict:
    """TEST STUB loader — mirrors the contract Member A's loader must satisfy."""
    _load_tables()
    case = json.loads((INPUT / f"{case_id}.json").read_text(encoding="utf-8"))
    order_id = case["customer_request"]["claimed_order_id"]

    orow = _orders[_orders["order_id"] == order_id]
    irows = _items[_items["order_id"] == order_id]

    if orow.empty:
        return {"case_id": case_id, "order_id": order_id, "order_status": None,
                "items": [], "customer_message": case["customer_request"]["message"]}

    o = orow.iloc[0]
    items = [
        {
            "order_item_id": _none(r["order_item_id"]),
            "seller_id": _none(r["seller_id"]),
            "shipping_limit_date": _none(r["shipping_limit_date"]),
            "price": _none(r["price"]) or 0.0,
            "freight_value": _none(r["freight_value"]) or 0.0,
        }
        for _, r in irows.iterrows()
    ]
    return {
        "case_id": case_id,
        "order_id": order_id,
        "order_status": _none(o["order_status"]),
        "order_estimated_delivery_date": _none(o["order_estimated_delivery_date"]),
        "order_delivered_customer_date": _none(o["order_delivered_customer_date"]),
        "order_delivered_carrier_date": _none(o["order_delivered_carrier_date"]),
        "items": items,
        "customer_message": case["customer_request"]["message"],
    }


def main(case_ids):
    for cid in case_ids:
        bundle = build_bundle(cid)
        os_finding, _ = order_seller.run(bundle)
        dl_finding, _ = delivery.run(bundle)
        print(f"\n===== {cid}  (order {bundle['order_id'][:12]}…, "
              f"status={bundle['order_status']}) =====")
        print("[order_seller]", json.dumps(
            {k: os_finding[k] for k in
             ("seller_ids", "seller_handoff_late", "late_sellers", "confidence")},
            ensure_ascii=False))
        print("[delivery]    ", json.dumps(
            {k: dl_finding[k] for k in
             ("delivered_late", "carrier_after_limit", "confidence")},
            ensure_ascii=False))
        # Derived policy hint (for sanity only — Policy agent is Member C's job).
        if dl_finding["delivered_late"]:
            hint = "late_delivery_seller" if dl_finding["carrier_after_limit"] else "late_delivery_logistics"
        else:
            hint = "not_late (canceled/unavailable/within-estimate handled elsewhere)"
        print("  -> policy hint:", hint)


if __name__ == "__main__":
    cases = sys.argv[1:] or ["EC_001", "EC_002", "EC_003"]
    main(cases)
