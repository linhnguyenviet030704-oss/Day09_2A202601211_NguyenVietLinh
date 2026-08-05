"""
Unit tests for agents/policy.py -- one case per EC_POLICY_V1 rule.
Uses hand-built mock order_seller/delivery dicts (Member B's contract)
and the real agents/payment.py to build the payment dict, since that's
Member C's own module. No dependency on core/data.py.
"""
from src.agents.payment import run_payment_agent
from src.agents.policy import run_policy_agent


def _order_seller(order_status="delivered", seller_handoff_late=False, seller_id="seller_1"):
    return {
        "order_status": order_status,
        "items": [
            {
                "item_id": 1,
                "seller_id": seller_id,
                "price": 100.0,
                "freight_value": 15.0,
                "shipping_limit_date": "2018-01-10 00:00:00",
            }
        ],
        "seller_ids": [seller_id],
        "delivered_carrier_date": "2018-01-12 00:00:00",
        "seller_handoff_late": seller_handoff_late,
        "late_seller_ids": [seller_id] if seller_handoff_late else [],
        "late_item_ids": [1] if seller_handoff_late else [],
    }


def _delivery(delivered_late=False):
    return {
        "estimated_date": "2018-01-20 00:00:00",
        "delivered_customer_date": "2018-01-25 00:00:00" if delivered_late else "2018-01-15 00:00:00",
        "delivered_late": delivered_late,
        "carrier_after_limit": False,
    }


def _payment(payment_value=115.0, split=False):
    payments = [{"payment_sequential": 1, "payment_value": payment_value}]
    if split:
        payments = [
            {"payment_sequential": 1, "payment_value": payment_value / 2},
            {"payment_sequential": 2, "payment_value": payment_value / 2},
        ]
    items = [{"price": 100.0, "freight_value": 15.0}]
    return run_payment_agent("order_x", items, payments)


def test_rule1_canceled_order_paid():
    result = run_policy_agent(
        "order_1", _order_seller(order_status="canceled"), _delivery(), _payment()
    )
    assert result["assessment"]["primary_issue"] == "canceled_order_paid"
    assert result["assessment"]["case_status"] == "action_required"
    assert result["financial_resolution"]["recommended_refund_brl"] == 115.0
    assert result["_cause_code"] == "ORDER_CANCELED_AFTER_PAYMENT"
    assert result["resolution_actions"] == ["issue_full_refund"]


def test_rule2_unavailable_order_paid():
    result = run_policy_agent(
        "order_2", _order_seller(order_status="unavailable"), _delivery(), _payment()
    )
    assert result["assessment"]["primary_issue"] == "unavailable_order_paid"
    assert result["root_cause_analysis"]["responsible_parties"] == [
        {"party_type": "platform", "party_id": "OLIST_PLATFORM"}
    ]


def test_rule3_late_delivery_seller():
    result = run_policy_agent(
        "order_3",
        _order_seller(seller_handoff_late=True, seller_id="seller_late"),
        _delivery(delivered_late=True),
        _payment(),
    )
    assert result["assessment"]["primary_issue"] == "late_delivery_seller"
    assert result["_cause_code"] == "SELLER_HANDOFF_AFTER_LIMIT"
    assert result["root_cause_analysis"]["responsible_parties"] == [
        {"party_type": "seller", "party_id": "seller_late"}
    ]
    assert result["financial_resolution"]["recommended_refund_brl"] == 15.0  # freight only


def test_rule4_late_delivery_logistics():
    result = run_policy_agent(
        "order_4",
        _order_seller(seller_handoff_late=False),
        _delivery(delivered_late=True),
        _payment(),
    )
    assert result["assessment"]["primary_issue"] == "late_delivery_logistics"
    assert result["_cause_code"] == "CARRIER_DELIVERED_AFTER_ESTIMATE"
    assert result["root_cause_analysis"]["responsible_parties"] == [
        {"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}
    ]


def test_rule5_valid_split_payment():
    result = run_policy_agent(
        "order_5",
        _order_seller(seller_handoff_late=False),
        _delivery(delivered_late=False),
        _payment(split=True),
    )
    assert result["assessment"]["primary_issue"] == "valid_split_payment"
    assert result["assessment"]["case_status"] == "no_action"
    assert result["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert result["root_cause_analysis"]["responsible_parties"] == []


def test_rule6_unsupported_late_claim():
    result = run_policy_agent(
        "order_6",
        _order_seller(seller_handoff_late=False),
        _delivery(delivered_late=False),
        _payment(split=False),
    )
    assert result["assessment"]["primary_issue"] == "unsupported_late_claim"
    assert result["assessment"]["case_status"] == "no_action"
    assert result["resolution_actions"] == ["reject_late_refund"]


def test_priority_canceled_beats_late_delivery():
    # Even if delivery also looks late, canceled+paid must win (rule 1 has priority).
    result = run_policy_agent(
        "order_7",
        _order_seller(order_status="canceled", seller_handoff_late=True),
        _delivery(delivered_late=True),
        _payment(),
    )
    assert result["assessment"]["primary_issue"] == "canceled_order_paid"


if __name__ == "__main__":
    import sys

    failed = 0
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
