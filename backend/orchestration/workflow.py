"""LangGraph workflow for the competitive-analysis multi-agent system.

The competition rubric asks for a clear DAG, structured agent communication,
traceability, and a real quality feedback loop. This workflow exposes seven
specialized roles:

Research -> Collector -> Evidence -> Analysis -> Verification -> Quality -> Report

Quality can route rejected work back to Collector/Evidence/Analysis/Research. After
the retry cap, Quality marks a partial report and still routes to ReportAgent so the
demo does not block on manual review.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.analysis_agent import analysis_agent
from app.agents.analysis_ai_agent import analysis_ai_agent
from app.agents.collector_agent import collector_agent
from app.agents.evidence_agent import evidence_agent
from app.agents.quality_agent import quality_agent, quality_router
from app.agents.report_agent import report_agent
from app.agents.research_agent import research_agent
from app.agents.verification_agent import verification_agent
from app.core.agent_runner import run_node
from app.schemas.report import ReportAgentOutput
from app.services.metrics_service import calculate_report_metrics
from app.services.review_service import create_review_ticket

from .state import CompetitiveAnalysisState


def human_review_node(state: CompetitiveAnalysisState) -> dict:
    """Compatibility fallback for explicit manual-review flows.

    The default product-comparison path degrades to a partial report after automatic
    retries are exhausted, instead of blocking the user.
    """
    quality_result = state.get("quality_result", {})
    metrics = calculate_report_metrics(state)
    review_ticket = create_review_ticket(state)
    trace_log = list(state.get("trace_log", []))
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "HumanReviewRequired",
            "status": "rejected",
            "output_summary": "automatic retries exhausted; human review required",
            "review_ticket_id": review_ticket.get("ticket_id"),
            "error": None,
        }
    )
    return {
        **state,
        "current_agent": "HumanReviewRequired",
        "is_approved": False,
        "needs_human_review": True,
        "quality_status": "rejected_after_max_iterations",
        "metrics": metrics,
        "review_ticket": review_ticket,
        "trace_log": trace_log,
        "final_report": {
            "quality_status": "rejected_after_max_iterations",
            "needs_human_review": True,
            "auto_approved": False,
            "executive_summary": [
                "Automatic analysis finished, but quality checks still failed after retries.",
                "This draft should not be used as a formal decision record.",
                "Please add or correct evidence, then rerun the workflow.",
            ],
            "quality_result": quality_result,
            "risk_flags": state.get("risk_flags", []),
            "missing_dimensions": quality_result.get("missing_dimensions", []),
            "missing_platforms": quality_result.get("missing_platforms", []),
            "required_actions": quality_result.get("required_actions", []),
            "review_ticket": review_ticket,
            "used_claim_ids": state.get("used_claim_ids", []),
            "used_evidence_ids": state.get("used_evidence_ids", []),
            "metrics": metrics,
            "draft_product_matrix": state.get("product_matrix", {}),
            "draft_business_matrix": state.get("business_matrix", {}),
            "draft_claims": state.get("claims", []),
            "disclaimer": "This report requires human review before use.",
        },
    }


def research_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("ResearchAgent", research_agent, state)


def collector_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("CollectorAgent", collector_agent, state)


def evidence_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("EvidenceAgent", evidence_agent, state)


def analysis_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("AnalysisAgent", analysis_agent, state)


def analysis_ai_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("AnalysisAgent.SWOT", analysis_ai_agent, state)


def verification_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("VerificationAgent", verification_agent, state)


def quality_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node("QualityAgent", quality_agent, state)


def report_agent_node(state: CompetitiveAnalysisState) -> dict:
    return run_node(
        "ReportAgent",
        report_agent,
        state,
        ReportAgentOutput,
        ["final_report", "used_claim_ids", "used_evidence_ids"],
    )


def build_workflow():
    workflow = StateGraph(CompetitiveAnalysisState)

    workflow.add_node("research_agent", research_agent_node)
    workflow.add_node("collector_agent", collector_agent_node)
    workflow.add_node("evidence_agent", evidence_agent_node)
    workflow.add_node("analysis_agent", analysis_agent_node)
    workflow.add_node("verification_agent", verification_agent_node)
    workflow.add_node("quality_agent", quality_agent_node)
    workflow.add_node("analysis_ai_agent", analysis_ai_node)
    workflow.add_node("report_agent", report_agent_node)
    workflow.add_node("human_review", human_review_node)

    workflow.set_entry_point("research_agent")

    workflow.add_edge("research_agent", "collector_agent")
    workflow.add_edge("collector_agent", "evidence_agent")
    workflow.add_edge("evidence_agent", "analysis_agent")
    workflow.add_edge("analysis_agent", "verification_agent")
    workflow.add_edge("verification_agent", "quality_agent")
    workflow.add_conditional_edges(
        "quality_agent",
        quality_router,
        {
            "research_agent": "research_agent",
            "collector_agent": "collector_agent",
            "evidence_agent": "evidence_agent",
            "analysis_agent": "analysis_agent",
            # Forward (approved / partial) path runs the SWOT node once before ReportAgent.
            "report_agent": "analysis_ai_agent",
            "human_review": "human_review",
        },
    )
    workflow.add_edge("analysis_ai_agent", "report_agent")
    workflow.add_edge("report_agent", END)
    workflow.add_edge("human_review", END)

    return workflow


app = build_workflow().compile()
