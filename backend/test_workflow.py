"""LangGraph workflow test for the professional gaming-mouse schema."""

from __future__ import annotations

import os
import sys

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"
os.environ["EVIDENCE_AGENT_USE_LLM"] = "0"
os.environ["OFFICIAL_SPEC_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestration.workflow import app


EXPECTED_TRACE = [
    "ResearchAgent",
    "CollectorAgent",
    "EvidenceAgent",
    "AnalysisAgent",
    "VerificationAgent",
    "QualityAgent",
    "ReportAgent",
]


initial_state = {
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
    final_state = app.invoke(dict(initial_state), {"recursion_limit": 80})

    report = final_state["final_report"]
    quality = final_state["quality_result"]

    assert final_state["current_agent"] == "ReportAgent"
    assert report["schema_name"] == "gaming_mouse_competitive_report"
    assert report["report_kind"] == "gaming_mouse_product_comparison"
    assert report["product_identification"]
    assert report["hardware_specs"]
    assert report["feature_tree"]["schema_name"] == "gaming_mouse_feature_tree"
    assert report["pricing_model"]["schema_name"] == "gaming_mouse_pricing_model"
    assert report["user_persona"]["schema_name"] == "gaming_mouse_user_persona"
    assert report["evidence_links"]["used_claim_ids"] == report["used_claim_ids"]
    assert quality["score_type"] == "report_credibility"
    assert quality["status"] in {"approved", "approved_with_limitations", "partial_report"}

    trace_agents = [item["agent_name"] for item in final_state["trace_log"]]
    for agent_name in EXPECTED_TRACE:
        assert agent_name in trace_agents, trace_agents

    print("workflow test passed")
