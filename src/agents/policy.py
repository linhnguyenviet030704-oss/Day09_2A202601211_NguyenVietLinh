"""
Policy Agent (Member C).

Applies EC_POLICY_V1 (README section 4) in strict priority order to the
outputs of Order/Seller (Member B), Delivery (Member B) and Payment
(this module's sibling, agents/payment.py).

Deterministic by design -- same rationale as payment.py: rule selection
and refund math are the highest-weighted, most objectively-checkable
part of the grade (financial 20%, root cause 15%), so they must not be
left to LLM judgment. See individual report section 5.

Expected inputs (team contract, see architecture.md):

order_seller = {
    "order_status": str,
    "items": [{"item_id": int, "seller_id": str, "price": float,
                "freight_value": float, "shipping_limit_date": str}],
    "seller_ids": [str],
    "delivered_carrier_date": str | None,
    "seller_handoff_late": bool,       # True if ANY seller handed off after their shipping_limit_date
    "late_seller_ids": [str],          # sellers that violated shipping_limit_date
    "late_item_ids": [int],            # order_item_id of violating items
}

delivery = {
    "estimated_date": str,
    "delivered_customer_date": str | None,
    "delivered_late": bool,            # delivered_customer_date > estimated_date
    "carrier_after_limit": bool,       # mirrors order_seller.seller_handoff_late; carried for clarity
}

payment = {  # output of agents/payment.py
    "payments": [{"sequential": int, "value": float}],
    "payment_total": float,
    "item_total": float,
    "freight_total": float,
    "num_rows": int,
    "reconciled": bool,
    "split_payment": bool,
}

Output: a dict with everything the Verifier/Coordinator need to fill the
final schema (README section 6), except case_id / opened_at (Coordinator's).
The "_cause_code" key is an internal handoff field consumed only by
agents/verifier.py (to build the "policy:<cause_code>" evidence id) and
must be stripped before writing to output/ -- Coordinator's job.

No other module in this repo is imported here.
"""
from __future__ import annotations

CAUSE_CANCELED = "ORDER_CANCELED_AFTER_PAYMENT"
CAUSE_UNAVAILABLE = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
CAUSE_SELLER_LATE = "SELLER_HANDOFF_AFTER_LIMIT"
CAUSE_CARRIER_LATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
CAUSE_SPLIT_PAYMENT = "MULTIPLE_PAYMENTS_RECONCILED"
CAUSE_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"

PLATFORM_PARTY = "OLIST_PLATFORM"
LOGISTICS_PARTY = "LOGISTICS_PROVIDER"


def _r2(x: float) -> float:
    return round(float(x), 2)


def run_policy_agent(order_id: str, order_seller: dict, delivery: dict, payment: dict) -> dict:
    order_status = order_seller.get("order_status")
    payment_total = payment["payment_total"]
    item_total = payment["item_total"]
    freight_total = payment["freight_total"]

    seller_ids = order_seller.get("seller_ids", [])
    item_ids = [it["item_id"] for it in order_seller.get("items", [])]
    payment_ids = [p["sequential"] for p in payment.get("payments", [])]

    base_entities = {
        "order_ids": [order_id],
        "item_ids": [f"{order_id}:{i}" for i in item_ids[:5]],
        "seller_ids": seller_ids[:5],
        "payment_ids": [f"{order_id}:{s}" for s in payment_ids[:5]],
    }

    # Rule 1: canceled_order_paid
    if order_status == "canceled" and payment_total > 0:
        return _result(
            primary_issue="canceled_order_paid",
            case_status="action_required",
            confidence=0.97,
            cause_code=CAUSE_CANCELED,
            responsible=[{"party_type": "platform", "party_id": PLATFORM_PARTY}],
            recommended_refund=payment_total,
            actions=["issue_full_refund"],
            entities=base_entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    # Rule 2: unavailable_order_paid
    if order_status == "unavailable" and payment_total > 0:
        return _result(
            primary_issue="unavailable_order_paid",
            case_status="action_required",
            confidence=0.97,
            cause_code=CAUSE_UNAVAILABLE,
            responsible=[{"party_type": "platform", "party_id": PLATFORM_PARTY}],
            recommended_refund=payment_total,
            actions=["issue_full_refund"],
            entities=base_entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    delivered_late = delivery.get("delivered_late", False)
    seller_handoff_late = order_seller.get("seller_handoff_late", False)

    # Rule 3: late_delivery_seller
    if delivered_late and seller_handoff_late:
        late_seller_ids = order_seller.get("late_seller_ids") or seller_ids[:1]
        late_item_ids = order_seller.get("late_item_ids") or item_ids
        entities = dict(base_entities)
        entities["seller_ids"] = late_seller_ids[:5]
        entities["item_ids"] = [f"{order_id}:{i}" for i in late_item_ids[:5]]
        return _result(
            primary_issue="late_delivery_seller",
            case_status="action_required",
            confidence=0.93,
            cause_code=CAUSE_SELLER_LATE,
            responsible=[{"party_type": "seller", "party_id": sid} for sid in late_seller_ids[:3]],
            recommended_refund=freight_total,
            actions=["refund_freight"],
            entities=entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    # Rule 4: late_delivery_logistics
    if delivered_late and not seller_handoff_late:
        return _result(
            primary_issue="late_delivery_logistics",
            case_status="action_required",
            confidence=0.93,
            cause_code=CAUSE_CARRIER_LATE,
            responsible=[{"party_type": "logistics_provider", "party_id": LOGISTICS_PARTY}],
            recommended_refund=freight_total,
            actions=["refund_freight"],
            entities=base_entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    reconciled = payment.get("reconciled", False)
    split_payment = payment.get("split_payment", False)

    # Rule 5: valid_split_payment
    if split_payment and reconciled:
        return _result(
            primary_issue="valid_split_payment",
            case_status="no_action",
            confidence=0.9,
            cause_code=CAUSE_SPLIT_PAYMENT,
            responsible=[],
            recommended_refund=0.0,
            actions=["explain_valid_split_payment"],
            entities=base_entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    # Rule 6: unsupported_late_claim
    if not delivered_late and reconciled:
        return _result(
            primary_issue="unsupported_late_claim",
            case_status="no_action",
            confidence=0.9,
            cause_code=CAUSE_WITHIN_ESTIMATE,
            responsible=[],
            recommended_refund=0.0,
            actions=["reject_late_refund"],
            entities=base_entities,
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
        )

    # No rule matched cleanly: fall back to unsupported_late_claim with low confidence
    # rather than fabricating a cause. Verifier/Coordinator should flag this for review.
    return _result(
        primary_issue="unsupported_late_claim",
        case_status="no_action",
        confidence=0.4,
        cause_code=CAUSE_WITHIN_ESTIMATE,
        responsible=[],
        recommended_refund=0.0,
        actions=["reject_late_refund"],
        entities=base_entities,
        item_total=item_total,
        freight_total=freight_total,
        payment_total=payment_total,
    )


def _result(
    *,
    primary_issue: str,
    case_status: str,
    confidence: float,
    cause_code: str,
    responsible: list[dict],
    recommended_refund: float,
    actions: list[str],
    entities: dict,
    item_total: float,
    freight_total: float,
    payment_total: float,
) -> dict:
    return {
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": round(confidence, 2),
        },
        "affected_entities": entities,
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": cause_code, "rank": 1}],
            "responsible_parties": responsible[:3],
        },
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": _r2(item_total),
            "freight_total_brl": _r2(freight_total),
            "payment_total_brl": _r2(payment_total),
            "recommended_refund_brl": _r2(recommended_refund),
        },
        "resolution_actions": actions[:5],
        "_cause_code": cause_code,  # used by verifier to build policy:<cause_code> evidence id
    }
