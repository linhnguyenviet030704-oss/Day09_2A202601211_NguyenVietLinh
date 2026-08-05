import json
import platform
from importlib import import_module
from pathlib import Path
from typing import Any

from .core.coordinator import AgentSet, Coordinator


MODEL_NAME = "gpt-4o-mini"
PARAMETER_SIZE = "8B"
FRAMEWORK = "Python + pandas"


def run_batch(input_dir, output_dir, logging_dir, data_loader, agents: AgentSet):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    logging_dir = Path(logging_dir)
    input_paths = sorted(input_dir.glob("EC_*.json"))
    expected_names = [f"EC_{index:03d}.json" for index in range(1, 51)]
    actual_names = [path.name for path in input_paths]
    if actual_names != expected_names:
        raise ValueError(f"Expected exactly EC_001.json through EC_050.json, got {actual_names}")

    output_dir.mkdir(parents=True, exist_ok=True)
    logging_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("EC_*.json"):
        if path.is_file():
            path.unlink()

    trace_path = logging_dir / "trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as trace_file:
        def write_trace(record):
            trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            trace_file.flush()

        coordinator = Coordinator(data_loader, agents, trace_writer=write_trace)
        for input_path in input_paths:
            case = json.loads(input_path.read_text(encoding="utf-8"))
            output = coordinator.process_case(case)
            (output_dir / input_path.name).write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    metadata = {
        "model": MODEL_NAME,
        "parameter_size": PARAMETER_SIZE,
        "framework": FRAMEWORK,
        "runtime": f"Python {platform.python_version()}",
        "cases_processed": len(input_paths),
    }
    (logging_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_integrated_agents() -> AgentSet:
    order_seller = import_module("src.agents.order_seller")
    payment = import_module("src.agents.payment")
    delivery = import_module("src.agents.delivery")
    policy = import_module("src.agents.policy")
    verifier = import_module("src.agents.verifier")

    def records(frame):
        return [] if frame.empty else frame.to_dict("records")

    def bundle_dict(bundle):
        order = {} if bundle.order.empty else bundle.order.iloc[0].to_dict()
        return {**order, "items": records(bundle.items), "payments": records(bundle.payments)}

    def run_order_seller(bundle):
        finding, _trace = order_seller.run(bundle_dict(bundle))
        return finding

    def run_delivery(bundle):
        finding, _trace = delivery.run(bundle_dict(bundle))
        return finding

    def run_payment(bundle):
        data = bundle_dict(bundle)
        return payment.run_payment_agent(data.get("order_id", ""), data["items"], data["payments"])

    def run_policy(facts, case):
        request = case.get("customer_request") or {}
        result = policy.run_policy_agent(
            request.get("claimed_order_id", ""),
            facts["order_seller"],
            facts["delivery"],
            facts["payment"],
        )
        return {
            **result["assessment"],
            "ranked_causes": result["root_cause_analysis"]["ranked_causes"],
            "responsible_parties": result["root_cause_analysis"]["responsible_parties"],
            "recommended_refund_brl": result["financial_resolution"]["recommended_refund_brl"],
            "resolution_actions": result["resolution_actions"],
        }

    def run_verifier(candidate, facts, _bundle):
        order_id = candidate["affected_entities"]["order_ids"][0]
        causes = candidate["root_cause_analysis"].get("ranked_causes") or []
        ok, errors, _final = verifier.run_verifier_agent(
            candidate["case_id"],
            order_id,
            facts["order_seller"],
            facts["payment"],
            {
                "assessment": candidate["assessment"],
                "affected_entities": candidate["affected_entities"],
                "root_cause_analysis": candidate["root_cause_analysis"],
                "financial_resolution": candidate["financial_resolution"],
                "resolution_actions": candidate["resolution_actions"],
                "_cause_code": causes[0].get("cause_code") if causes else None,
            },
        )
        return {"status": "passed" if ok else "failed", "errors": errors}

    return AgentSet(run_order_seller, run_payment, run_delivery, run_policy, run_verifier)


def main():
    root = Path(__file__).resolve().parents[1]
    from .core.data import DataLoader

    run_batch(
        root / "input",
        root / "output",
        root / "logging",
        DataLoader(root / "data"),
        load_integrated_agents(),
    )


if __name__ == "__main__":
    main()
