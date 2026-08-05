"""
Unit tests for agents/verifier.py. Uses hand-built order_seller/payment
contract dicts and Policy Agent's real output -- no dependency on
core/data.py.
"""
from src.agents.payment import run_payment_agent
from src.agents.policy import run_policy_agent
from src.agents.verifier import run_verifier_agent


def _order_seller():
    return {
        "order_status": "delivered",
        "items": [
            {
                "item_id": 1,
                "seller_id": "seller_1",
                "price": 100.0,
                "freight_value": 15.0,
                "shipping_limit_date": "2018-01-10 00:00:00",
            }
        ],
        "seller_ids": ["seller_1"],
        "delivered_carrier_date": "2018-01-08 00:00:00",
        "seller_handoff_late": False,
        "late_seller_ids": [],
        "late_item_ids": [],
    }


def _delivery(delivered_late=True):
    return {
        "estimated_date": "2018-01-20 00:00:00",
        "delivered_customer_date": "2018-01-25 00:00:00",
        "delivered_late": delivered_late,
        "carrier_after_limit": False,
    }


def test_valid_case_passes():
    order_seller = _order_seller()
    payment = run_payment_agent("order_1", [{"price": 100.0, "freight_value": 15.0}], [
        {"payment_sequential": 1, "payment_value": 115.0}
    ])
    policy_result = run_policy_agent("order_1", order_seller, _delivery(), payment)

    ok, errors, final = run_verifier_agent("EC_001", "order_1", order_seller, payment, policy_result)

    assert ok is True, errors
    assert errors == []
    assert final["case_id"] == "EC_001"
    assert final["affected_entities"]["order_ids"] == ["order_1"]
    assert "order:order_1" in final["evidence_ids"]
    assert final["financial_resolution"]["recommended_refund_brl"] == 15.0


def test_fabricated_item_id_is_dropped_and_flagged():
    order_seller = _order_seller()
    payment = run_payment_agent("order_2", [{"price": 100.0, "freight_value": 15.0}], [
        {"payment_sequential": 1, "payment_value": 115.0}
    ])
    policy_result = run_policy_agent("order_2", order_seller, _delivery(), payment)
    # Simulate a policy bug that invents an item id not backed by data.
    policy_result["affected_entities"]["item_ids"].append("order_2:999")

    ok, errors, final = run_verifier_agent("EC_002", "order_2", order_seller, payment, policy_result)

    assert ok is False
    assert any("item_ids not present" in e for e in errors)
    assert "item:order_2:999" not in final["evidence_ids"]


def test_no_item_rows_forces_empty_entities_and_zero_totals():
    order_seller = {
        "order_status": "delivered",
        "items": [],
        "seller_ids": [],
        "delivered_carrier_date": None,
        "seller_handoff_late": False,
        "late_seller_ids": [],
        "late_item_ids": [],
    }
    payment = run_payment_agent("order_3", [], [{"payment_sequential": 1, "payment_value": 0.0}])
    policy_result = run_policy_agent("order_3", order_seller, _delivery(delivered_late=False), payment)

    ok, errors, final = run_verifier_agent("EC_003", "order_3", order_seller, payment, policy_result)

    assert final["affected_entities"]["item_ids"] == []
    assert final["affected_entities"]["seller_ids"] == []
    assert final["financial_resolution"]["item_total_brl"] == 0.0
    assert final["financial_resolution"]["freight_total_brl"] == 0.0


def test_entity_and_evidence_caps_enforced():
    order_seller = {
        "order_status": "delivered",
        "items": [
            {
                "item_id": i,
                "seller_id": f"seller_{i}",
                "price": 10.0,
                "freight_value": 1.0,
                "shipping_limit_date": "2018-01-10 00:00:00",
            }
            for i in range(1, 8)  # 7 items -> must be capped to 5
        ],
        "seller_ids": [f"seller_{i}" for i in range(1, 8)],
        "delivered_carrier_date": "2018-01-08 00:00:00",
        "seller_handoff_late": False,
        "late_seller_ids": [],
        "late_item_ids": [],
    }
    payments = [{"payment_sequential": 1, "payment_value": 71.0}]
    payment = run_payment_agent("order_4", order_seller["items"], payments)
    policy_result = run_policy_agent("order_4", order_seller, _delivery(delivered_late=False), payment)

    ok, errors, final = run_verifier_agent("EC_004", "order_4", order_seller, payment, policy_result)

    assert len(final["affected_entities"]["item_ids"]) <= 5
    assert len(final["affected_entities"]["seller_ids"]) <= 5
    assert len(final["evidence_ids"]) <= 10


def test_invalid_case_status_is_rejected():
    order_seller = _order_seller()
    payment = run_payment_agent("order_5", [{"price": 100.0, "freight_value": 15.0}], [
        {"payment_sequential": 1, "payment_value": 115.0}
    ])
    policy_result = run_policy_agent("order_5", order_seller, _delivery(delivered_late=False), payment)
    policy_result["assessment"]["case_status"] = "maybe"  # invalid value

    ok, errors, _ = run_verifier_agent("EC_005", "order_5", order_seller, payment, policy_result)

    assert ok is False
    assert any("invalid case_status" in e for e in errors)


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
