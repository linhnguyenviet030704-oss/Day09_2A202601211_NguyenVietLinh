"""Order & Seller Agent (Member B).

Responsibility: from an order bundle, establish the order status, its items, the
seller(s), and — critically — whether the seller handed the order to the carrier
AFTER the item's shipping_limit_date. That handoff signal is what separates a
seller-caused late delivery from a logistics-caused one downstream in Policy.

Design: the facts are computed deterministically (dates don't need an LLM). The
LLM is then used as a genuine agent step to cross-check the finding against the
customer's message and assign a calibrated confidence + rationale. The
deterministic booleans remain authoritative — the model never overrides them.

Input  (bundle dict, produced by Member A's data loader):
    {
      "order_id": str,
      "order_status": str,
      "order_delivered_carrier_date": str|None,
      "items": [ {order_item_id, seller_id, price, freight_value, shipping_limit_date}, ... ],
      "customer_message": str        # optional, for the LLM cross-check
    }

Output (finding dict, consumed by Policy — Member C):
    {
      "agent": "order_seller_agent",
      "order_id", "order_status",
      "seller_ids": [...],
      "items": [ {item_id, seller_id, price, freight_value, shipping_limit_date}, ... ],
      "delivered_carrier_date": str|None,
      "seller_handoff_late": bool,   # any item: carrier_date > shipping_limit_date
      "late_sellers": [seller_id, ...],
      "confidence": float,
      "rationale": str
    }
"""

from ..core.llm import chat_json
from ..core.util import parse_ts

AGENT_NAME = "order_seller_agent"

_SYSTEM = (
    "You are the Order & Seller investigator in an e-commerce dispute system. "
    "You are given already-computed facts about one order. Do NOT recompute dates. "
    "Judge only how well the facts support the customer's complaint and how complete "
    "the data is, then return STRICT JSON: "
    '{"confidence": <float 0..1>, "rationale": <short string>}. '
    "Lower the confidence when key dates are missing."
)


def _extract(bundle: dict) -> dict:
    """Deterministic core: normalize items, sellers, and the handoff-late signal."""
    carrier_dt = parse_ts(bundle.get("order_delivered_carrier_date"))

    items_out = []
    seller_ids = []
    late_sellers = []
    for raw in bundle.get("items", []) or []:
        item_id = str(raw.get("order_item_id", raw.get("item_id", "")))
        seller_id = raw.get("seller_id")
        limit_dt = parse_ts(raw.get("shipping_limit_date"))
        # Seller handed off late for this item iff carrier received it after the
        # item's shipping_limit_date (README §4 multi-item rule).
        item_late = bool(carrier_dt and limit_dt and carrier_dt > limit_dt)

        items_out.append(
            {
                "item_id": item_id,
                "seller_id": seller_id,
                "price": float(raw.get("price", 0.0) or 0.0),
                "freight_value": float(raw.get("freight_value", 0.0) or 0.0),
                "shipping_limit_date": raw.get("shipping_limit_date"),
            }
        )
        if seller_id and seller_id not in seller_ids:
            seller_ids.append(seller_id)
        if item_late and seller_id and seller_id not in late_sellers:
            late_sellers.append(seller_id)

    return {
        "order_id": bundle.get("order_id"),
        "order_status": bundle.get("order_status"),
        "seller_ids": seller_ids,
        "items": items_out,
        "delivered_carrier_date": bundle.get("order_delivered_carrier_date"),
        "seller_handoff_late": len(late_sellers) > 0,
        "late_sellers": late_sellers,
    }


def run(bundle: dict) -> tuple[dict, dict]:
    """Run the agent. Returns (finding, trace)."""
    facts = _extract(bundle)

    user = (
        f"Customer message: {bundle.get('customer_message', '(none)')}\n"
        f"order_status: {facts['order_status']}\n"
        f"delivered_carrier_date: {facts['delivered_carrier_date']}\n"
        f"item shipping_limit_dates: "
        f"{[i['shipping_limit_date'] for i in facts['items']]}\n"
        f"seller_handoff_late (computed): {facts['seller_handoff_late']}\n"
        f"late_sellers (computed): {facts['late_sellers']}"
    )
    llm, trace = chat_json(
        _SYSTEM, user, agent=AGENT_NAME, case_id=bundle.get("case_id", "")
    )

    # Deterministic facts are authoritative; LLM only adds confidence + rationale.
    confidence = llm.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.9 if facts["delivered_carrier_date"] else 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    finding = {"agent": AGENT_NAME, **facts,
               "confidence": round(confidence, 2),
               "rationale": str(llm.get("rationale", "")).strip()}
    return finding, trace
