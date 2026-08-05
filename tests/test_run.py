import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.core.coordinator import AgentSet
from src.core.data import OrderBundle
from src.run import load_integrated_agents, run_batch


class BatchRunnerTests(unittest.TestCase):
    def test_run_batch_writes_exactly_50_outputs_trace_lines_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            output_dir = root / "output"
            logging_dir = root / "logging"
            input_dir.mkdir()
            output_dir.mkdir()
            (output_dir / "EC_999.json").write_text("stale", encoding="utf-8")
            for index in range(1, 51):
                case_id = f"EC_{index:03d}"
                (input_dir / f"{case_id}.json").write_text(json.dumps({
                    "case_id": case_id,
                    "customer_request": {"claimed_order_id": f"order-{index}"},
                    "policy_version": "EC_POLICY_V1",
                }), encoding="utf-8")

            bundle = OrderBundle(
                order=pd.DataFrame(),
                items=pd.DataFrame(),
                payments=pd.DataFrame(),
                sellers=pd.DataFrame(),
            )
            loader = type("Loader", (), {"get_order_bundle": lambda self, order_id: bundle})()
            agents = AgentSet(
                lambda _bundle: {"order_status": "canceled", "items": []},
                lambda _bundle: {"payment_total": 10.0, "num_rows": 1},
                lambda _bundle: {},
                lambda _facts, _case: {
                    "primary_issue": "canceled_order_paid",
                    "case_status": "action_required",
                    "confidence": 1.0,
                    "recommended_refund_brl": 10.0,
                    "resolution_actions": ["issue_full_refund"],
                },
                lambda _candidate, _facts, _bundle: {"status": "passed", "errors": []},
            )

            run_batch(input_dir, output_dir, logging_dir, loader, agents)

            self.assertEqual(
                sorted(path.name for path in output_dir.glob("EC_*.json")),
                [f"EC_{index:03d}.json" for index in range(1, 51)],
            )
            trace_lines = (logging_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(trace_lines), 50)
            metadata = json.loads((logging_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["model"], "gpt-4o-mini")
            self.assertEqual(metadata["parameter_size"], "8B")
            self.assertEqual(json.loads((output_dir / "EC_050.json").read_text())["case_id"], "EC_050")

    def test_load_integrated_agents_returns_coordinator_callables(self):
        agents = load_integrated_agents()

        self.assertTrue(callable(agents.order_seller))
        self.assertTrue(callable(agents.payment))
        self.assertTrue(callable(agents.delivery))
        self.assertTrue(callable(agents.policy))
        self.assertTrue(callable(agents.verifier))


if __name__ == "__main__":
    unittest.main()
