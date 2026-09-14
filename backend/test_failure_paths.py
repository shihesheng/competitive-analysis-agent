"""Failure-path tests for verification, quality and degraded reports."""

from __future__ import annotations

import os
import sys

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.quality_agent import quality_agent, quality_router
from app.agents.report_agent import report_agent
from app.agents.verification_agent import verification_agent
from app.core.agent_runner import run_node
from app.services.context_manager import select_evidence_context


def _evidence():
    return {
        "evidence_id": "EV001",
        "platform": "Logitech",
        "related_dimension": "weight",
        "credibility": "high",
        "confidence_score": 0.9,
        "claim": "The mouse weighs 60 g.",
        "raw_content": "Official specs show the mouse weighs 60 g.",
    }


def _base_state():
    matrix = {
        "dimensions": {
            "weight": {
                "Logitech": {
                    "score": 4,
                    "summary": "The mouse weighs 60 g.",
                    "analysis": "The mouse weighs 60 g.",
                    "evidence_ids": ["EV001"],
                    "confidence_score": 0.9,
                }
            }
        }
    }
    return {
        "industry_key": "gaming_mouse",
        "industry_name": "电竞鼠标",
        "target_platform": "Logitech",
        "competitors": ["Logitech"],
        "analysis_scene": "test",
        "target_user": "test",
        "time_range": "last two years",
        "focus_dimensions": ["weight"],
        "product_compare_mode": True,
        "raw_research": [],
        "evidence_list": [_evidence()],
        "claims": [
            {
                "claim_id": "PCL001",
                "content": "The mouse weighs 60 g.",
                "dimension": "weight",
                "related_platforms": ["Logitech"],
                "evidence_ids": ["EV001"],
                "confidence_score": 0.9,
                "generated_by": "AnalysisAgent",
            }
        ],
        "product_matrix": matrix,
        "business_matrix": matrix,
        "risk_flags": [],
        "faithfulness_report": {},
        "unsupported_claim_ids": [],
        "quality_result": {},
        "final_report": {},
        "context_summary": {},
        "review_ticket": {},
        "trace_log": [],
        "error_log": [],
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
    }


def test_context_summary_observable():
    evidence_list = [
        {**_evidence(), "evidence_id": f"EV{index:03d}", "raw_content": "x" * 80}
        for index in range(1, 6)
    ]
    selected, summary = select_evidence_context(
        "AnalysisAgent",
        evidence_list,
        max_items=2,
        max_per_dimension=2,
        max_content_chars=20,
    )
    assert len(selected) == 2
    assert summary["total_evidence_count"] == 5
    assert summary["selected_evidence_count"] == 2
    assert summary["trimmed_evidence_count"] == 3


def test_unsupported_claim_rejected():
    state = _base_state()
    state["claims"][0]["content"] = "The mouse weighs 73 g."

    verified = verification_agent(state)
    assert verified["unsupported_claim_ids"] == ["PCL001"]

    checked = quality_agent(verified)
    result = checked["quality_result"]
    assert result["status"] == "rejected"
    assert "all_claims_faithful" in result["failed_checks"]
    assert result["target_agent"] == "AnalysisAgent"


def test_matrix_issue_rejected():
    state = _base_state()
    state["product_matrix"]["dimensions"]["weight"]["Logitech"]["analysis"] = "The mouse weighs 73 g."

    verified = verification_agent(state)
    assert verified["faithfulness_report"]["matrix_issues"]

    checked = quality_agent(verified)
    result = checked["quality_result"]
    assert result["status"] == "rejected"
    assert "all_matrix_claims_faithful" in result["failed_checks"]


def test_partial_report_after_three_failures():
    state = _base_state()
    state["product_matrix"]["dimensions"]["weight"]["Logitech"]["analysis"] = "The mouse weighs 73 g."
    state["iteration_count"] = 2

    verified = verification_agent(state)
    checked = quality_agent(verified)
    result = checked["quality_result"]
    assert checked["needs_human_review"] is False
    assert checked["degraded_report"] is True
    assert checked["quality_status"] == "partial_report"
    assert result["status"] == "partial_report"
    assert quality_router(checked) == "report_agent"

    reported = report_agent(checked)
    final_report = reported["final_report"]
    assert final_report["quality_status"] == "partial_report"
    assert final_report["partial_report"] is True
    assert final_report["auto_degraded"] is True


def test_structured_error_recovery():
    def _broken_agent(_state):
        raise RuntimeError("boom")

    recovered = run_node("BrokenAgent", _broken_agent, _base_state())
    assert recovered["trace_log"][0]["status"] == "failed"
    assert recovered["error_log"][0]["agent_name"] == "BrokenAgent"


if __name__ == "__main__":
    for test in (
        test_context_summary_observable,
        test_unsupported_claim_rejected,
        test_matrix_issue_rejected,
        test_partial_report_after_three_failures,
        test_structured_error_recovery,
    ):
        test()
        print(f"PASS {test.__name__}")
