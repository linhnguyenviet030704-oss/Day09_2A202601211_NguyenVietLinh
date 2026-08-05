import json
import platform
from importlib import import_module
from pathlib import Path
from typing import Any

from .core.coordinator import AgentSet, Coordinator


MODEL_NAME = "llama-3.1-8b-instant"
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
    modules = {
        "order_seller": ("src.agents.order_seller", "analyze"),
        "payment": ("src.agents.payment", "analyze"),
        "delivery": ("src.agents.delivery", "analyze"),
        "policy": ("src.agents.policy", "decide"),
        "verifier": ("src.agents.verifier", "verify"),
    }
    loaded: dict[str, Any] = {}
    for name, (module_name, function_name) in modules.items():
        module = import_module(module_name)
        loaded[name] = getattr(module, function_name)
    return AgentSet(**loaded)


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
