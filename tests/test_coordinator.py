import unittest

import pandas as pd

from src.core.coordinator import AgentSet, Coordinator, VerificationError
from src.core.data import OrderBundle


class CoordinatorTests(unittest.TestCase):
    def test_retries_missing_agent_once_and_caps_output_before_verification(self):
        bundle = OrderBundle(
            order=pd.DataFrame(),
            items=pd.DataFrame([
                {"order_id": "o1", "order_item_id": str(i), "seller_id": f"s{i}"}
                for i in range(1, 7)
            ]),
            payments=pd.DataFrame([
                {"order_id": "o1", "payment_sequential": str(i)}
                for i in range(1, 7)
            ]),
            sellers=pd.DataFrame(),
        )
        loader = type("Loader", (), {"get_order_bundle": lambda self, order_id: bundle})()
        calls = {"payment": 0}
        trace = []

        def order_seller(_bundle):
            return {
                "order_status": "delivered",
                "items": [
                    {"item_id": str(i), "seller_id": f"s{i}", "shipping_limit_date": "2017-01-01"}
                    for i in range(1, 7)
                ],
                "seller_ids": [f"s{i}" for i in range(1, 7)],
                "delivered_carrier_date": "2017-01-02",
                "seller_handoff_late": False,
            }

        def payment(_bundle):
            calls["payment"] += 1
            if calls["payment"] == 1:
                return {"num_rows": 2}
            return {
                "payments": [{"sequential": i, "value": 20.0} for i in range(1, 7)],
                "payment_total": 115.0,
                "item_total": 100.0,
                "freight_total": 15.0,
                "num_rows": 2,
                "reconciled": True,
                "split_payment": True,
            }

        def delivery(_bundle):
            return {
                "estimated_date": "2017-01-01",
                "delivered_customer_date": "2017-01-03",
                "delivered_late": True,
                "carrier_after_limit": False,
            }

        def policy(_facts, _case):
            return {
                "primary_issue": "late_delivery_logistics",
                "case_status": "action_required",
                "confidence": 0.9,
                "ranked_causes": [
                    {"cause_code": f"CAUSE_{i}", "rank": i}
                    for i in range(1, 5)
                ],
                "responsible_parties": [
                    {"party_type": "seller", "party_id": f"s{i}"}
                    for i in range(1, 5)
                ],
                "recommended_refund_brl": 15.0,
                "resolution_actions": [f"action_{i}" for i in range(1, 7)],
            }

        def verifier(candidate, _facts, _bundle):
            self.assertLessEqual(len(candidate["affected_entities"]["item_ids"]), 5)
            self.assertLessEqual(len(candidate["evidence_ids"]), 10)
            self.assertLessEqual(len(candidate["root_cause_analysis"]["ranked_causes"]), 3)
            self.assertLessEqual(len(candidate["root_cause_analysis"]["responsible_parties"]), 3)
            self.assertLessEqual(len(candidate["resolution_actions"]), 5)
            return {"status": "passed", "errors": []}

        result = Coordinator(
            loader,
            AgentSet(order_seller, payment, delivery, policy, verifier),
            trace_writer=trace.append,
        ).process_case({
            "case_id": "EC_001",
            "customer_request": {"claimed_order_id": "o1"},
            "policy_version": "EC_POLICY_V1",
        })

        self.assertEqual(calls["payment"], 2)
        self.assertEqual(result["financial_resolution"]["recommended_refund_brl"], 15.0)
        self.assertEqual(len(result["affected_entities"]["seller_ids"]), 5)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["final_primary_issue"], "late_delivery_logistics")

    def test_does_not_return_output_when_verifier_rejects(self):
        bundle = OrderBundle(
            order=pd.DataFrame(),
            items=pd.DataFrame(),
            payments=pd.DataFrame(),
            sellers=pd.DataFrame(),
        )
        loader = type("Loader", (), {"get_order_bundle": lambda self, order_id: bundle})()

        agents = AgentSet(
            lambda _bundle: {"order_status": "delivered", "items": []},
            lambda _bundle: {"payment_total": 0, "item_total": 0, "freight_total": 0, "num_rows": 0},
            lambda _bundle: {
                "estimated_date": "2017-01-01",
                "delivered_customer_date": "2017-01-01",
                "carrier_after_limit": False,
            },
            lambda _facts, _case: {
                "primary_issue": "unsupported_late_claim",
                "case_status": "no_action",
                "confidence": 0.8,
                "recommended_refund_brl": 0,
                "resolution_actions": ["reject_late_refund"],
            },
            lambda _candidate, _facts, _bundle: {"status": "failed", "errors": ["bad evidence"]},
        )

        with self.assertRaises(VerificationError):
            Coordinator(loader, agents).process_case({
                "case_id": "EC_002",
                "customer_request": {"claimed_order_id": "o2"},
                "policy_version": "EC_POLICY_V1",
            })


if __name__ == "__main__":
    unittest.main()
