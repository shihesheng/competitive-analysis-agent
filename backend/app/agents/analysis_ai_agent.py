"""AnalysisAgent AI-interpretation node (SWOT) as a first-class DAG step.

Placed on the forward path (QualityAgent -> AnalysisAI/SWOT -> ReportAgent), so the
SWOT interpretation is part of the visible, traceable workflow instead of a lazily
triggered REST side effect. It runs exactly once on the approved/partial path and never
inside the quality retry loop.

It reuses ``generate_swot_interpretation``, which already validates every cited
evidence/claim id against the real ``evidence_list``/``claims`` (no fabricated EVxxx),
and degrades to a deterministic SWOT when the LLM is unavailable.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from app.services.swot_ai_service import generate_swot_interpretation


def analysis_ai_agent(state: dict) -> Dict[str, Any]:
    start = time.time()
    interpretation = generate_swot_interpretation(state)
    duration_ms = int((time.time() - start) * 1000)

    swot = interpretation.get("swot", {}) if isinstance(interpretation.get("swot"), dict) else {}
    point_count = sum(
        len(swot.get(key, [])) for key in ("strengths", "weaknesses", "opportunities", "threats")
        if isinstance(swot.get(key), list)
    )
    dropped = interpretation.get("dropped_evidence_ids", [])
    summary = (
        f"generated SWOT AI interpretation ({point_count} points, "
        f"{len(interpretation.get('used_evidence_ids', []))} grounded evidence ids"
        + (f", dropped {len(dropped)} fabricated ids" if dropped else "")
        + ")"
    )
    trace_entry = {
        "step_id": len(state.get("trace_log", [])) + 1,
        "agent_name": "AnalysisAgent.SWOT",
        "status": "success",
        "output_summary": summary,
        "duration_ms": duration_ms,
        "error": None,
    }
    return {
        "current_agent": "AnalysisAgent.SWOT",
        "analysis_ai_interpretation": interpretation,
        # context_summary uses a merge reducer; returning just this key appends it.
        "context_summary": {"AnalysisAgent.SWOT": interpretation.get("context_summary", {})},
        # trace_log uses a merge reducer; returning just the new entry appends it.
        "trace_log": [trace_entry],
    }
