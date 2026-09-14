from __future__ import annotations

from typing import Any

from app.schemas.metrics import ReportMetrics
from app.services.error_log_service import normalize_error_log


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def calculate_report_metrics(state: dict) -> dict:
    """Calculate report metrics from the current workflow state."""
    evidence_list = [
        evidence for evidence in _as_list(state.get("evidence_list", []))
        if isinstance(evidence, dict)
    ]
    claims = [
        claim for claim in _as_list(state.get("claims", []))
        if isinstance(claim, dict)
    ]
    focus_dimensions = [
        str(dimension).strip()
        for dimension in _as_list(state.get("focus_dimensions", []))
        if str(dimension).strip()
    ]
    quality_result = state.get("quality_result", {})
    if not isinstance(quality_result, dict):
        quality_result = {}
    faithfulness_report = state.get("faithfulness_report", {})
    if not isinstance(faithfulness_report, dict):
        faithfulness_report = {}

    evidence_count = len(evidence_list)
    claim_count = len(claims)

    unsupported_claim_count = len(
        [
            claim_id
            for claim_id in state.get("unsupported_claim_ids", [])
            if str(claim_id).strip()
        ]
    )
    if "faithfulness_rate" in faithfulness_report:
        faithfulness_rate = float(faithfulness_report.get("faithfulness_rate") or 0.0)
    else:
        faithfulness_rate = _safe_ratio(claim_count - unsupported_claim_count, claim_count) if claim_count else 1.0
    weak_claim_count = int(faithfulness_report.get("weak_claim_count", 0) or 0)
    matrix_issue_count = len(
        [
            item for item in _as_list(faithfulness_report.get("matrix_issues", []))
            if isinstance(item, dict)
        ]
    )
    context_summary = state.get("context_summary", {})
    if not isinstance(context_summary, dict):
        context_summary = {}
    context_trimmed_evidence_count = sum(
        int(item.get("trimmed_evidence_count", 0) or 0)
        for item in context_summary.values()
        if isinstance(item, dict)
    )
    error_count = len(normalize_error_log(state.get("error_log", [])))

    claims_with_evidence = sum(
        1
        for claim in claims
        if isinstance(claim.get("evidence_ids"), list) and len(claim.get("evidence_ids", [])) > 0
    )
    covered_dimensions = {
        str(evidence.get("related_dimension") or evidence.get("dimension") or "").strip()
        for evidence in evidence_list
    }
    covered_dimensions.discard("")

    high_credibility_count = sum(
        1
        for evidence in evidence_list
        if str(evidence.get("credibility", "")).lower() == "high"
    )
    low_credibility_count = sum(
        1
        for evidence in evidence_list
        if str(evidence.get("credibility", "")).lower() == "low"
    )

    metrics = ReportMetrics(
        evidence_count=evidence_count,
        claim_count=claim_count,
        citation_rate=_safe_ratio(claims_with_evidence, claim_count),
        coverage_rate=_safe_ratio(len(covered_dimensions), len(focus_dimensions)),
        high_credibility_ratio=_safe_ratio(high_credibility_count, evidence_count),
        low_credibility_ratio=_safe_ratio(low_credibility_count, evidence_count),
        faithfulness_rate=round(faithfulness_rate, 4),
        unsupported_claim_count=unsupported_claim_count,
        weak_claim_count=weak_claim_count,
        matrix_issue_count=matrix_issue_count,
        context_trimmed_evidence_count=context_trimmed_evidence_count,
        error_count=error_count,
        has_review_ticket=bool(state.get("review_ticket", {})),
        quality_score=float(quality_result.get("score", quality_result.get("quality_score", 0)) or 0),
        iteration_count=int(state.get("iteration_count", 0) or 0),
    )
    return metrics.model_dump()
