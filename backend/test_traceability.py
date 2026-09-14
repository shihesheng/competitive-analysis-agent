"""Traceability checks for claims, evidence and final report links."""

from __future__ import annotations

import os
import sys

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"
os.environ["EVIDENCE_AGENT_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestration.workflow import app
from test_workflow import EXPECTED_TRACE, initial_state


def _assert_subset(values, valid_values, label):
    missing = [value for value in values if value not in valid_values]
    assert not missing, f"{label} has invalid IDs: {missing}"


if __name__ == "__main__":
    final_state = app.invoke(dict(initial_state), {"recursion_limit": 80})

    claims = final_state["claims"]
    evidence_list = final_state["evidence_list"]
    report = final_state["final_report"]

    evidence_ids = {
        item["evidence_id"]
        for item in evidence_list
        if isinstance(item, dict) and item.get("evidence_id")
    }
    claim_ids = {
        item["claim_id"]
        for item in claims
        if isinstance(item, dict) and item.get("claim_id")
    }

    assert claims
    assert evidence_ids
    for claim in claims:
        _assert_subset(claim.get("evidence_ids", []), evidence_ids, "claim.evidence_ids")

    _assert_subset(report["used_claim_ids"], claim_ids, "report.used_claim_ids")
    _assert_subset(report["used_evidence_ids"], evidence_ids, "report.used_evidence_ids")
    _assert_subset(report["evidence_links"]["used_claim_ids"], claim_ids, "evidence_links.used_claim_ids")
    _assert_subset(report["evidence_links"]["used_evidence_ids"], evidence_ids, "evidence_links.used_evidence_ids")

    required_schema_fields = {
        "product_identification",
        "hardware_specs",
        "feature_tree",
        "pricing_model",
        "user_persona",
        "evidence_links",
        "score_flow",
        "agent_contributions",
    }
    assert required_schema_fields.issubset(report.keys())

    trace_agents = {item["agent_name"] for item in final_state["trace_log"]}
    assert set(EXPECTED_TRACE).issubset(trace_agents)
    assert "AnalysisAgent" in final_state["context_summary"]

    print("traceability test passed")
