"""
Unit tests for agents/payment.py. Uses hand-built mock rows only --
no dependency on core/data.py or any real CSV.
"""
from src.agents.payment import run_payment_agent


def test_reconciled_single_payment():
    items = [{"price": 100.0, "freight_value": 15.0}]
    payments = [{"payment_sequential": 1, "payment_value": 115.0}]

    result = run_payment_agent("order_1", items, payments)

    assert result["item_total"] == 100.0
    assert result["freight_total"] == 15.0
    assert result["payment_total"] == 115.0
    assert result["reconciled"] is True
    assert result["num_rows"] == 1
    assert result["split_payment"] is False


def test_reconciled_within_tolerance():
    items = [{"price": 50.0, "freight_value": 10.0}]
    payments = [{"payment_sequential": 1, "payment_value": 60.09}]

    result = run_payment_agent("order_2", items, payments)

    assert result["reconciled"] is True  # 0.09 <= 0.10 tolerance


def test_not_reconciled_outside_tolerance():
    items = [{"price": 50.0, "freight_value": 10.0}]
    payments = [{"payment_sequential": 1, "payment_value": 61.0}]

    result = run_payment_agent("order_3", items, payments)

    assert result["reconciled"] is False


def test_split_payment_multiple_rows():
    items = [{"price": 200.0, "freight_value": 20.0}]
    payments = [
        {"payment_sequential": 1, "payment_value": 110.0},
        {"payment_sequential": 2, "payment_value": 110.0},
    ]

    result = run_payment_agent("order_4", items, payments)

    assert result["num_rows"] == 2
    assert result["split_payment"] is True
    assert result["reconciled"] is True
    assert result["payments"] == [
        {"sequential": 1, "value": 110.0},
        {"sequential": 2, "value": 110.0},
    ]


def test_multi_item_order_sums_correctly():
    items = [
        {"price": 30.5, "freight_value": 5.25},
        {"price": 19.99, "freight_value": 4.75},
    ]
    payments = [{"payment_sequential": 1, "payment_value": 60.49}]

    result = run_payment_agent("order_5", items, payments)

    assert result["item_total"] == 50.49
    assert result["freight_total"] == 10.0
    assert result["reconciled"] is True


def test_no_payment_rows():
    items = [{"price": 100.0, "freight_value": 10.0}]
    payments = []

    result = run_payment_agent("order_6", items, payments)

    assert result["num_rows"] == 0
    assert result["payment_total"] == 0.0
    assert result["reconciled"] is False
    assert result["split_payment"] is False


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
