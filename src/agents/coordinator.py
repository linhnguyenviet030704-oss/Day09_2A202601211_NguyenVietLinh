"""
Coordinator Agent (Member A).

Dispatches a case to the investigation agents (Order/Seller, Delivery),
the reconciliation agent (Payment), the rule engine (Policy), and the
Verifier gate, then assembles/writes the final output schema (README
section 6). Also runs one LLM (google/gemma-3-4b-it, see
core/llm_client.py) triage call per case that cross-checks the
customer's free-text claim against the deterministic findings; this is
informational only (logged to trace.jsonl) and never overrides the
deterministic decision, so an LLM hiccup cannot corrupt output/EC_*.json.

Handoff order: Order/Seller + Delivery + Payment (parallel-ish facts)
-> Policy (decision) -> Verifier (gate) -> Coordinator (write).
"""
from __future__ import annotations

from src.core.data import get_order_bundle
from src.core.llm_client import MODEL_NAME, call_llm_json
from src.agents.order_seller import run_order_seller_agent
from src.agents.delivery import run_delivery_agent
from src.agents.payment import run_payment_agent
from src.agents.policy import run_policy_agent
from src.agents.verifier import run_verifier_agent

TRIAGE_SYSTEM_PROMPT = (
    "You are a triage assistant for an e-commerce dispute case. You are given the "
    "customer's raw complaint and a deterministic assessment already computed from "
    "verifiable order data. Do NOT invent facts or override the assessment. Reply with "
    "a JSON object: {\"claim_matches_assessment\": true|false, \"note\": \"<=200 chars\"}."
)


def _triage_note(customer_message: str, primary_issue: str) -> dict:
    try:
        user_prompt = (
            f"Customer message: {customer_message!r}\n"
            f"Deterministic primary_issue already decided: {primary_issue!r}\n"
            "Does the customer's complaint plausibly match this primary_issue?"
        )
        return call_llm_json(TRIAGE_SYSTEM_PROMPT, user_prompt)
    except Exception as e:  # noqa: BLE001 - triage is best-effort, must never break the case
        return {"claim_matches_assessment": None, "note": f"triage_call_failed: {e}"}


def process_case(case: dict) -> dict:
    """
    case: parsed input/EC_xxx.json
    returns: {"ok": bool, "errors": [...], "output": {...} | None, "trace": {...}}
    """
    case_id = case["case_id"]
    order_id = case["customer_request"]["claimed_order_id"]
    customer_message = case["customer_request"]["message"]

    bundle = get_order_bundle(order_id)

    order_seller = run_order_seller_agent(bundle)
    delivery = run_delivery_agent(bundle, order_seller)
    payment = run_payment_agent(order_id, bundle.items, bundle.payments)
    policy_result = run_policy_agent(order_id, order_seller, delivery, payment)
    ok, errors, final = run_verifier_agent(case_id, order_id, order_seller, payment, policy_result)

    triage = _triage_note(customer_message, policy_result["assessment"]["primary_issue"])

    trace = {
        "case_id": case_id,
        "order_id": order_id,
        "model": MODEL_NAME,
        "agents_run": ["order_seller", "delivery", "payment", "policy", "verifier", "triage_llm"],
        "order_seller": order_seller,
        "delivery": delivery,
        "payment": payment,
        "policy_result": {k: v for k, v in policy_result.items() if k != "_cause_code"},
        "triage": triage,
        "verifier_ok": ok,
        "verifier_errors": errors,
    }

    return {"ok": ok, "errors": errors, "output": final if ok else None, "trace": trace}
