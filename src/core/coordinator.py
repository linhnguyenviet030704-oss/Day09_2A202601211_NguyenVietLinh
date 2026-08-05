from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Mapping

from .data import OrderBundle


FactAgent = Callable[[OrderBundle], dict[str, Any]]
PolicyAgent = Callable[[dict[str, Any], Mapping[str, Any]], dict[str, Any]]
VerifierAgent = Callable[[dict[str, Any], dict[str, Any], OrderBundle], dict[str, Any]]


@dataclass(frozen=True)
class AgentSet:
    order_seller: FactAgent
    payment: FactAgent
    delivery: FactAgent
    policy: PolicyAgent
    verifier: VerifierAgent


class VerificationError(ValueError):
    pass


class Coordinator:
    def __init__(self, data_loader, agents: AgentSet, trace_writer: Callable[[dict[str, Any]], None] | None = None):
        self.data_loader = data_loader
        self.agents = agents
        self.trace_writer = trace_writer

    def process_case(self, case: Mapping[str, Any]) -> dict[str, Any]:
        case_id = self._required(case, "case_id")
        request = case.get("customer_request") or {}
        order_id = self._required(request, "claimed_order_id")
        bundle = self.data_loader.get_order_bundle(order_id)
        steps = [{"agent": "CoordinatorAgent", "step": "LOAD_CASE", "status": "ok"}]

        facts = {
            "order_seller": self._call_fact_agent("OrderSellerAgent", self.agents.order_seller, bundle, steps),
            "payment": self._call_fact_agent("PaymentAgent", self.agents.payment, bundle, steps),
            "delivery": self._call_fact_agent("DeliveryAgent", self.agents.delivery, bundle, steps),
        }
        missing = self._missing_agents(facts)
        steps.append({
            "agent": "CoordinatorAgent",
            "step": "CHECK_COMPLETENESS",
            "status": "warning" if missing else "ok",
        })

        for name in missing:
            agent_name = {
                "order_seller": "OrderSellerAgent",
                "payment": "PaymentAgent",
                "delivery": "DeliveryAgent",
            }[name]
            facts[name] = self._call_fact_agent(
                agent_name,
                getattr(self.agents, name),
                bundle,
                steps,
                retry=True,
            )

        warnings = [f"missing facts after retry: {name}" for name in self._missing_agents(facts)]
        steps.append({
            "agent": "CoordinatorAgent",
            "step": "LOCK_FACTS",
            "status": "warning" if warnings else "ok",
        })

        locked_facts = deepcopy(facts)
        decision = self.agents.policy(locked_facts, deepcopy(dict(case)))
        if not isinstance(decision, dict):
            raise TypeError("PolicyAgent must return a dict")
        steps.append({"agent": "PolicyAgent", "primary_issue": decision.get("primary_issue")})

        candidate = self._assemble_output(case_id, order_id, bundle, facts, decision)
        verification = self.agents.verifier(candidate, deepcopy(facts), bundle)
        if not isinstance(verification, dict):
            raise TypeError("VerifierAgent must return a dict")
        if verification.get("status") != "passed" or verification.get("errors"):
            errors = verification.get("errors") or ["VerifierAgent rejected candidate"]
            self._write_trace({
                "case_id": case_id,
                "order_id": order_id,
                "steps": steps + [{"agent": "VerifierAgent", "status": "failed", "errors": errors}],
                "warnings": warnings,
            })
            raise VerificationError("; ".join(map(str, errors)))

        steps.append({"agent": "VerifierAgent", "status": "passed"})
        self._write_trace({
            "case_id": case_id,
            "order_id": order_id,
            "steps": steps,
            "warnings": warnings,
            "final_primary_issue": candidate["assessment"]["primary_issue"],
            "final_refund_brl": candidate["financial_resolution"]["recommended_refund_brl"],
        })
        return candidate

    @staticmethod
    def _required(mapping: Mapping[str, Any], key: str) -> str:
        value = mapping.get(key)
        if value is None or str(value).strip() == "":
            raise ValueError(f"Missing required case field: {key}")
        return str(value)

    @staticmethod
    def _call_fact_agent(name, agent, bundle, steps, retry=False):
        result = agent(bundle)
        if not isinstance(result, dict):
            raise TypeError(f"{name} must return a dict")
        steps.append({"agent": name, "status": "retry" if retry else "ok"})
        return result

    @classmethod
    def _missing_agents(cls, facts):
        missing = set()
        order_seller = facts["order_seller"]
        payment = facts["payment"]
        delivery = facts["delivery"]

        if not cls._present(order_seller.get("order_status")):
            missing.add("order_seller")

        status = order_seller.get("order_status")
        if status in {"canceled", "unavailable"} and not cls._present(payment.get("payment_total")):
            missing.add("payment")

        if status == "delivered":
            for key in ("estimated_date", "delivered_customer_date", "carrier_after_limit"):
                if not cls._present(delivery.get(key)):
                    missing.add("delivery")
            items = order_seller.get("items") or []
            if any(not cls._present(item.get("shipping_limit_date")) for item in items):
                missing.add("order_seller")
            for key in ("item_total", "freight_total"):
                if not cls._present(payment.get(key)):
                    missing.add("payment")

        payment_rows = payment.get("num_rows", payment.get("payment_row_count"))
        if payment_rows is None:
            payment_rows = len(payment.get("payments") or [])
        if int(payment_rows) >= 2:
            for key in ("payment_total", "item_total", "freight_total"):
                if not cls._present(payment.get(key)):
                    missing.add("payment")
            if not cls._present(payment.get("reconciled", payment.get("payment_matches_order_total"))):
                missing.add("payment")
        return sorted(missing)

    @staticmethod
    def _present(value):
        return value is not None and value != ""

    @classmethod
    def _assemble_output(cls, case_id, order_id, bundle, facts, decision):
        order_seller = facts["order_seller"]
        payment = facts["payment"]
        item_ids = cls._bundle_item_ids(order_id, bundle, order_seller)
        seller_ids = cls._bundle_seller_ids(bundle, order_seller)
        payment_ids = cls._bundle_payment_ids(order_id, bundle, payment)
        causes = decision.get("ranked_causes") or cls._single_cause(decision.get("root_cause_code"))
        causes = list(causes or [])[:3]
        parties = list(decision.get("responsible_parties") or [])[:3]
        order_evidence = [f"order:{order_id}"]
        item_evidence = [f"item:{item_id}" for item_id in item_ids]
        payment_evidence = [f"payment:{payment_id}" for payment_id in payment_ids]
        seller_evidence = [f"seller:{seller_id}" for seller_id in seller_ids]
        policy_evidence = [f"policy:{cause.get('cause_code')}" for cause in causes if cause.get("cause_code")]
        issue = decision["primary_issue"]
        seller_is_responsible = any(party.get("party_type") == "seller" for party in parties)
        if seller_is_responsible:
            evidence = order_evidence + item_evidence + payment_evidence + seller_evidence + policy_evidence
        elif issue in {"late_delivery_logistics", "unsupported_late_claim"}:
            evidence = order_evidence + item_evidence + payment_evidence + policy_evidence
        elif issue in {"canceled_order_paid", "unavailable_order_paid", "valid_split_payment"}:
            evidence = order_evidence + payment_evidence + policy_evidence
        else:
            evidence = order_evidence + policy_evidence
        evidence_ids = cls._cap_unique(evidence, 10)
        has_items = bool(item_ids)
        item_total = cls._money(payment.get("item_total")) if has_items else 0.0
        freight_total = cls._money(payment.get("freight_total")) if has_items else 0.0
        return {
            "case_id": case_id,
            "assessment": {
                "primary_issue": decision["primary_issue"],
                "case_status": decision["case_status"],
                "confidence": float(decision["confidence"]),
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids[:5],
                "seller_ids": seller_ids[:5],
                "payment_ids": payment_ids[:5],
            },
            "root_cause_analysis": {
                "ranked_causes": causes,
                "responsible_parties": parties,
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": item_total,
                "freight_total_brl": freight_total,
                "payment_total_brl": cls._money(payment.get("payment_total")),
                "recommended_refund_brl": cls._money(decision.get("recommended_refund_brl", 0)),
            },
            "resolution_actions": list(decision.get("resolution_actions") or [])[:5],
        }

    @staticmethod
    def _single_cause(code):
        return [{"cause_code": code, "rank": 1}] if code else []

    @staticmethod
    def _bundle_item_ids(order_id, bundle, handoff):
        if bundle.items.empty or "order_item_id" not in bundle.items:
            return []
        return [f"{order_id}:{value}" for value in bundle.items["order_item_id"].tolist()]

    @staticmethod
    def _bundle_seller_ids(bundle, handoff):
        if bundle.items.empty or "seller_id" not in bundle.items:
            return []
        return bundle.items["seller_id"].drop_duplicates().tolist()

    @staticmethod
    def _bundle_payment_ids(order_id, bundle, handoff):
        if not bundle.payments.empty and "payment_sequential" in bundle.payments:
            values = bundle.payments["payment_sequential"].tolist()
        else:
            values = [payment.get("sequential") for payment in handoff.get("payments", []) if payment.get("sequential")]
        return [f"{order_id}:{value}" for value in sorted(values, key=lambda value: int(value))]

    @staticmethod
    def _cap_unique(values, limit):
        return list(dict.fromkeys(values))[:limit]

    @staticmethod
    def _money(value):
        if value in (None, ""):
            return 0.0
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _write_trace(self, record):
        if self.trace_writer:
            self.trace_writer(record)
