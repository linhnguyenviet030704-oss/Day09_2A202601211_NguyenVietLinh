"""
Verifier Agent (Member C).

Last gate before Coordinator writes output/EC_*.json. README section 5
+ 6 impose a hard gate (0 points for the case) on invalid evidence IDs,
wrong amounts or schema violations, so this must be deterministic and
exhaustive -- no LLM call.

Does NOT import core/data.py or any other Member A/B module. It only
validates against the contract data it is handed: the Order/Seller
Agent output and the Payment Agent output (both already derived from
CSV rows upstream). If those two contracts are correct, every ID this
agent approves is guaranteed to trace back to real CSV rows.

Responsibilities:
1. Build evidence_ids from the Policy Agent's decision, keeping only
   IDs that are present in order_seller["items"]/["seller_ids"] or
   payment["payments"] -- never trust an ID that isn't backed by the
   contract data.
2. Enforce the caps from README section 6 (<=5 per entity set, <=10
   evidence, <=3 causes, <=3 responsible parties, <=5 actions).
3. Enforce 2-decimal rounding and the "no item rows" special case.
4. Return (is_valid, errors, final_case_dict) -- Coordinator should
   only write to disk when is_valid is True.
"""
from __future__ import annotations

VALID_CAUSE_CODES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}

MAX_ENTITY_IDS = 5
MAX_EVIDENCE = 10
MAX_CAUSES = 3
MAX_PARTIES = 3
MAX_ACTIONS = 5


def _r2(x) -> float:
    return round(float(x), 2)


def run_verifier_agent(
    case_id: str,
    order_id: str,
    order_seller: dict,
    payment: dict,
    policy_result: dict,
) -> tuple[bool, list[str], dict]:
    errors: list[str] = []

    entities = policy_result["affected_entities"]
    root_cause = policy_result["root_cause_analysis"]
    financial = policy_result["financial_resolution"]
    actions = policy_result["resolution_actions"]
    assessment = policy_result["assessment"]

    order_items = order_seller.get("items", [])
    has_items = len(order_items) > 0
    valid_item_ids = {f"{order_id}:{it['item_id']}" for it in order_items}
    valid_seller_ids = set(order_seller.get("seller_ids", []))
    valid_payment_ids = {f"{order_id}:{p['sequential']}" for p in payment.get("payments", [])}
    order_exists = order_seller.get("order_status") is not None

    order_ids = entities.get("order_ids", [])[:MAX_ENTITY_IDS]
    item_ids = [i for i in entities.get("item_ids", [])[:MAX_ENTITY_IDS] if i in valid_item_ids]
    seller_ids = [s for s in entities.get("seller_ids", [])[:MAX_ENTITY_IDS] if s in valid_seller_ids]
    payment_ids = [p for p in entities.get("payment_ids", [])[:MAX_ENTITY_IDS] if p in valid_payment_ids]

    if not order_exists:
        errors.append(f"order_id {order_id}: order_seller reports no order_status (order not found upstream)")
    if order_ids != [order_id]:
        errors.append(f"affected_entities.order_ids mismatch: {order_ids} vs [{order_id}]")

    if not has_items:
        if item_ids or seller_ids:
            errors.append("order has no item rows but item_ids/seller_ids are non-empty")
        item_ids, seller_ids = [], []

    dropped_items = set(entities.get("item_ids", [])[:MAX_ENTITY_IDS]) - set(item_ids)
    if dropped_items:
        errors.append(f"item_ids not present in order_seller contract, dropped: {sorted(dropped_items)}")
    dropped_sellers = set(entities.get("seller_ids", [])[:MAX_ENTITY_IDS]) - set(seller_ids)
    if dropped_sellers:
        errors.append(f"seller_ids not present in order_seller contract, dropped: {sorted(dropped_sellers)}")
    dropped_payments = set(entities.get("payment_ids", [])[:MAX_ENTITY_IDS]) - set(payment_ids)
    if dropped_payments:
        errors.append(f"payment_ids not present in payment contract, dropped: {sorted(dropped_payments)}")

    ranked_causes = root_cause.get("ranked_causes", [])[:MAX_CAUSES]
    for c in ranked_causes:
        if c["cause_code"] not in VALID_CAUSE_CODES:
            errors.append(f"unknown cause_code: {c['cause_code']}")
    responsible_parties = root_cause.get("responsible_parties", [])[:MAX_PARTIES]
    actions = actions[:MAX_ACTIONS]

    item_total = 0.0 if not has_items else _r2(financial["item_total_brl"])
    freight_total = 0.0 if not has_items else _r2(financial["freight_total_brl"])
    payment_total = _r2(financial["payment_total_brl"])
    refund = _r2(financial["recommended_refund_brl"])

    if payment_total != _r2(payment.get("payment_total", payment_total)):
        errors.append("financial_resolution.payment_total_brl does not match payment agent output")

    if not (0.0 <= assessment["confidence"] <= 1.0):
        errors.append(f"confidence out of range: {assessment['confidence']}")

    if assessment["case_status"] not in {"action_required", "no_action"}:
        errors.append(f"invalid case_status: {assessment['case_status']}")
    if assessment["case_status"] == "action_required" and refund <= 0 and assessment["primary_issue"] not in {
        "late_delivery_seller",
        "late_delivery_logistics",
    }:
        errors.append("action_required with zero refund and no freight-refund issue")
    if assessment["case_status"] == "no_action" and refund != 0:
        errors.append(f"no_action but recommended_refund_brl={refund} (should be 0)")

    evidence_ids: list[str] = [f"order:{order_id}"]
    for iid in item_ids:
        evidence_ids.append(f"item:{iid}")
    for pid in payment_ids:
        evidence_ids.append(f"payment:{pid}")
    for sid in seller_ids:
        evidence_ids.append(f"seller:{sid}")
    cause_code = policy_result.get("_cause_code")
    if cause_code:
        evidence_ids.append(f"policy:{cause_code}")
    evidence_ids = evidence_ids[:MAX_EVIDENCE]

    final = {
        "case_id": case_id,
        "assessment": assessment,
        "affected_entities": {
            "order_ids": order_ids,
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "payment_ids": payment_ids,
        },
        "root_cause_analysis": {
            "ranked_causes": ranked_causes,
            "responsible_parties": responsible_parties,
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "payment_total_brl": payment_total,
            "recommended_refund_brl": refund,
        },
        "resolution_actions": actions,
    }

    return (len(errors) == 0, errors, final)
