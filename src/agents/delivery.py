"""Delivery Agent (Member B).

Responsibility: decide whether the order was actually delivered late (delivered
to the customer after the estimated date) and whether the carrier received the
goods after the shipping_limit_date. Together these two booleans let Policy
(Member C) choose between:
    late_delivery_seller     -> delivered_late AND carrier_after_limit
    late_delivery_logistics  -> delivered_late AND NOT carrier_after_limit
    unsupported_late_claim   -> NOT delivered_late (with reconciled payment)

Deterministic date comparisons are authoritative; the LLM adds a calibrated
confidence + rationale and cross-checks the customer's complaint.

Input  (bundle dict from Member A's loader):
    {
      "order_id": str,
      "order_estimated_delivery_date": str|None,
      "order_delivered_customer_date": str|None,
      "order_delivered_carrier_date": str|None,
      "items": [ {shipping_limit_date, ...}, ... ],
      "customer_message": str   # optional
    }

Output (finding dict, consumed by Policy):
    {
      "agent": "delivery_agent",
      "order_id",
      "estimated_date", "delivered_customer_date", "delivered_carrier_date",
      "delivered_late": bool,       # customer_date > estimated_date
      "carrier_after_limit": bool,  # any carrier_date > shipping_limit_date
      "confidence": float,
      "rationale": str
    }
"""

from ..core.llm import chat_json
from ..core.util import parse_ts

AGENT_NAME = "delivery_agent"

_SYSTEM = (
    "You are the Delivery investigator in an e-commerce dispute system. "
    "You are given already-computed delivery facts for one order. Do NOT recompute "
    "dates. Assess how well they support the customer's late-delivery complaint and "
    "how complete the data is, then return STRICT JSON: "
    '{"confidence": <float 0..1>, "rationale": <short string>}. '
    "Lower the confidence when delivery dates are missing."
)


def _extract(bundle: dict) -> dict:
    """Deterministic core: late-delivery and carrier-after-limit signals."""
    estimated_dt = parse_ts(bundle.get("order_estimated_delivery_date"))
    customer_dt = parse_ts(bundle.get("order_delivered_customer_date"))
    carrier_dt = parse_ts(bundle.get("order_delivered_carrier_date"))

    delivered_late = bool(customer_dt and estimated_dt and customer_dt > estimated_dt)

    carrier_after_limit = False
    for raw in bundle.get("items", []) or []:
        limit_dt = parse_ts(raw.get("shipping_limit_date"))
        if carrier_dt and limit_dt and carrier_dt > limit_dt:
            carrier_after_limit = True
            break

    return {
        "order_id": bundle.get("order_id"),
        "estimated_date": bundle.get("order_estimated_delivery_date"),
        "delivered_customer_date": bundle.get("order_delivered_customer_date"),
        "delivered_carrier_date": bundle.get("order_delivered_carrier_date"),
        "delivered_late": delivered_late,
        "carrier_after_limit": carrier_after_limit,
    }


def run(bundle: dict) -> tuple[dict, dict]:
    """Run the agent. Returns (finding, trace)."""
    facts = _extract(bundle)

    user = (
        f"Customer message: {bundle.get('customer_message', '(none)')}\n"
        f"estimated_delivery_date: {facts['estimated_date']}\n"
        f"delivered_customer_date: {facts['delivered_customer_date']}\n"
        f"delivered_carrier_date: {facts['delivered_carrier_date']}\n"
        f"delivered_late (computed): {facts['delivered_late']}\n"
        f"carrier_after_limit (computed): {facts['carrier_after_limit']}"
    )
    llm, trace = chat_json(
        _SYSTEM, user, agent=AGENT_NAME, case_id=bundle.get("case_id", "")
    )

    confidence = llm.get("confidence")
    if not isinstance(confidence, (int, float)):
        # Confident when we have both dates needed for the late decision.
        confidence = 0.9 if (facts["estimated_date"] and facts["delivered_customer_date"]) else 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    finding = {"agent": AGENT_NAME, **facts,
               "confidence": round(confidence, 2),
               "rationale": str(llm.get("rationale", "")).strip()}
    return finding, trace
