"""Smoke test for the current 7-agent gaming-mouse DAG."""

from __future__ import annotations

import os
import sys

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"
os.environ["EVIDENCE_AGENT_USE_LLM"] = "0"
os.environ["OFFICIAL_SPEC_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.analysis_agent import analysis_agent
from app.agents.collector_agent import collector_agent
from app.agents.evidence_agent import evidence_agent
from app.agents.quality_agent import quality_agent, quality_router
from app.agents.report_agent import report_agent
from app.agents.research_agent import research_agent
from app.agents.verification_agent import verification_agent


def _initial_state() -> dict:
    return {
        "industry_key": "gaming_mouse",
        "industry_name": "电竞鼠标",
        "target_platform": "G Pro X Superlight 2",
        "competitors": ["G Pro X Superlight 2", "Viper V3 Pro"],
        "analysis_scene": "gaming mouse product comparison",
        "target_user": "gaming peripheral buyer",
        "time_range": "last two years",
        "focus_dimensions": [],
        "data_requirements": [],
        "product_compare_mode": True,
        "selected_products": [
            {"id": "logitech-gpx-superlight-2"},
            {"id": "razer-viper-v3-pro"},
        ],
        "original_product_inputs": ["G Pro X Superlight 2", "Viper V3 Pro"],
        "resolved_products": [],
        "unresolved_products": [],
        "product_facts": [],
        "official_spec_records": [],
        "official_spec_status": [],
        "review_intel_status": {},
        "price_status": {},
        "hardware_analysis": {},
        "experience_analysis": {},
        "business_analysis": {},
        "agent_contributions": [],
        "pending_data": [],
        "pending_dimensions": [],
        "score_flow": {},
        "product_scores": {},
        "raw_research": [],
        "evidence_list": [],
        "evidence_status": {},
        "claims": [],
        "product_matrix": {},
        "business_matrix": {},
        "risk_flags": [],
        "faithfulness_report": {},
        "unsupported_claim_ids": [],
        "quality_result": {},
        "final_report": {},
        "context_summary": {},
        "review_ticket": {},
        "trace_log": [],
        "metrics": {},
        "used_claim_ids": [],
        "used_evidence_ids": [],
        "current_agent": "",
        "iteration_count": 0,
        "rejected_agents": [],
        "is_approved": False,
        "needs_human_review": False,
        "degraded_report": False,
        "quality_status": "",
        "error_log": [],
    }


if __name__ == "__main__":
    state = research_agent(_initial_state())
    assert state["raw_research"] == []
    assert state["data_requirements"]

    state = collector_agent(state)
    assert len(state["resolved_products"]) == 2
    assert len(state["product_facts"]) == 2
    assert len(state["evidence_list"]) == 20

    state = evidence_agent(state)
    assert state["evidence_status"]["local_json"]["count"] == 10
    assert state["evidence_status"]["pending_evidence_count"] == 10

    state = analysis_agent(state)
    assert state["product_matrix"]["dimensions"]
    assert state["claims"]
    assert state["risk_flags"]

    state = verification_agent(state)
    assert "faithfulness_rate" in state["faithfulness_report"]

    state = quality_agent(state)
    assert state["quality_result"]["status"] in {"approved", "approved_with_limitations", "partial_report"}
    assert quality_router(state) == "report_agent"

    state = report_agent(state)
    report = state["final_report"]
    assert report["schema_name"] == "gaming_mouse_competitive_report"
    assert report["product_identification"]
    assert report["hardware_specs"]
    assert report["feature_tree"]["schema_name"] == "gaming_mouse_feature_tree"
    assert report["pricing_model"]["status"] == "pending"
    assert report["user_persona"]["status"] == "insufficient_evidence"

    trace_agents = [item["agent_name"] for item in state["trace_log"]]
    for agent in (
        "ResearchAgent",
        "CollectorAgent",
        "EvidenceAgent",
        "AnalysisAgent",
        "VerificationAgent",
        "QualityAgent",
        "ReportAgent",
    ):
        assert agent in trace_agents

    print("7-agent smoke test passed")
