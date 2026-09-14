"""Quality Agent - run rule-based checks and route rejected work."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.schemas.quality import QualityResult


MAX_ITERATIONS = 3
ROUTER_MAP = {
    "ResearchAgent": "research_agent",
    "CollectorAgent": "collector_agent",
    "EvidenceAgent": "evidence_agent",
    "AnalysisAgent": "analysis_agent",
    "ReportAgent": "report_agent",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _dimension_key(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", _as_text(value).lower())


def _evidence_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = re.findall(r"EV\d{3,}", value)
    elif isinstance(value, list):
        candidates = [_as_text(item) for item in value]
    else:
        candidates = [_as_text(value)]

    result: List[str] = []
    for evidence_id in candidates:
        if evidence_id and evidence_id not in result:
            result.append(evidence_id)
    return result


def _matrix_not_empty(matrix: Any) -> bool:
    if not isinstance(matrix, dict):
        return False
    dimensions = matrix.get("dimensions")
    if not isinstance(dimensions, dict) or not dimensions:
        return False
    return any(
        isinstance(platform_map, dict) and bool(platform_map)
        for platform_map in dimensions.values()
    )


def _claim_owner(claim: Dict[str, Any]) -> str:
    claim_id = _as_text(claim.get("claim_id"))
    if claim_id.startswith(("PCL", "BCL", "ACL")):
        return "AnalysisAgent"
    generated_by = _as_text(claim.get("generated_by"))
    if generated_by == "HumanFeedback":
        return "CollectorAgent"
    if generated_by == "AnalysisAgent":
        return "AnalysisAgent"
    return "AnalysisAgent"


def _risk_reject_target(risk: Dict[str, Any]) -> str:
    risk_type = _as_text(risk.get("risk_type"))
    if risk_type in {"evidence_gap", "data_credibility", "data_timeliness"}:
        return "CollectorAgent"
    if risk_type == "compliance":
        return "ResearchAgent"
    return "AnalysisAgent"


def _matrix_issue_owner(issue: Dict[str, Any]) -> str:
    matrix_name = _as_text(issue.get("matrix"))
    if matrix_name in {"product_matrix", "business_matrix"}:
        return "AnalysisAgent"
    return "AnalysisAgent"


def _claim_owner_by_id(claim_id: str, claims: List[Dict[str, Any]]) -> str:
    for claim in claims:
        if isinstance(claim, dict) and _as_text(claim.get("claim_id")) == claim_id:
            return _claim_owner(claim)
    return _claim_owner({"claim_id": claim_id})


def _build_checked_items(
    evidence_list: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    product_matrix: Dict[str, Any],
    business_matrix: Dict[str, Any],
    risk_flags: List[Dict[str, Any]],
    competitors: List[str],
    focus_dimensions: List[str],
    unsupported_claim_ids: List[str],
    matrix_issues: List[Dict[str, Any]],
    product_compare_mode: bool = False,
) -> tuple[Dict[str, bool], List[str], List[str], List[str], str | None]:
    existing_evidence_ids = {
        _as_text(evidence.get("evidence_id"))
        for evidence in evidence_list
        if isinstance(evidence, dict) and evidence.get("evidence_id")
    }
    # 覆盖度只认非人工证据：人工反馈是"待验证线索"，不能靠手动输入一句话就把某个缺失
    # 维度/竞品标成已覆盖、从而抬高质量分（否则反馈闭环会变成可被操纵的伪闭环）。
    def _is_human_evidence(evidence: Dict[str, Any]) -> bool:
        return bool(evidence.get("human_provided")) or _as_text(
            evidence.get("source_type")
        ).lower().startswith("human")

    platforms_in_evidence = {
        _as_text(evidence.get("platform"))
        for evidence in evidence_list
        if isinstance(evidence, dict)
        and _as_text(evidence.get("platform"))
        and not _is_human_evidence(evidence)
    }
    dimensions_in_evidence = {
        _dimension_key(evidence.get("related_dimension") or evidence.get("dimension"))
        for evidence in evidence_list
        if isinstance(evidence, dict)
        and _dimension_key(evidence.get("related_dimension") or evidence.get("dimension"))
        and not _is_human_evidence(evidence)
    }

    missing_platforms = [
        competitor
        for competitor in competitors
        if _as_text(competitor) and _as_text(competitor) not in platforms_in_evidence
    ]
    missing_dimensions = [
        dimension
        for dimension in focus_dimensions
        if _as_text(dimension) and _dimension_key(dimension) not in dimensions_in_evidence
    ]

    claims_without_evidence = [
        claim
        for claim in claims
        if isinstance(claim, dict) and not _evidence_ids(claim.get("evidence_ids"))
    ]
    claims_with_invalid_evidence = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        ids = _evidence_ids(claim.get("evidence_ids"))
        if ids and any(evidence_id not in existing_evidence_ids for evidence_id in ids):
            claims_with_invalid_evidence.append(claim)

    high_risks = [
        risk
        for risk in risk_flags
        if isinstance(risk, dict) and _as_text(risk.get("severity")).lower() == "high"
    ]

    unsupported_claim_ids = [
        claim_id for claim_id in unsupported_claim_ids if _as_text(claim_id)
    ]
    matrix_issues = [issue for issue in matrix_issues if isinstance(issue, dict)]

    checked_items = {
        "all_claims_have_evidence": not claims_without_evidence,
        "all_evidence_ids_valid": not claims_with_invalid_evidence,
        "all_claims_faithful": not unsupported_claim_ids,
        "all_matrix_claims_faithful": not matrix_issues,
        "all_competitors_covered": not missing_platforms,
        # Missing dimensions are disclosed and penalized instead of forcing retries. This
        # keeps the workflow able to produce a caveated report with clear data gaps.
        "all_dimensions_covered": True,
        "missing_dimensions_disclosed": True,
        "product_matrix_not_empty": _matrix_not_empty(product_matrix),
        # 对比模式只看被选中的两个产品，不要求品牌级商业矩阵。
        "business_matrix_not_empty": True if product_compare_mode else _matrix_not_empty(business_matrix),
        # High risks should be disclosed and penalize report credibility, but they should
        # not automatically prevent ReportAgent from producing a caveated report.
        "no_high_severity_risk": True,
        "high_severity_risk_disclosed": True,
    }

    required_actions: List[str] = []
    reject_to: str | None = None

    if claims_without_evidence:
        reject_to = _claim_owner(claims_without_evidence[0])
        required_actions.append("补充 claims 中缺失的 evidence_ids。")

    if claims_with_invalid_evidence:
        reject_to = reject_to or _claim_owner(claims_with_invalid_evidence[0])
        required_actions.append("修正 claims 中不存在的 evidence_ids。")

    if unsupported_claim_ids:
        reject_to = reject_to or _claim_owner_by_id(unsupported_claim_ids[0], claims)
        required_actions.append("修正或移除 claims 中无法被所引证据支撑的结论（疑似幻觉）。")

    if matrix_issues:
        reject_to = reject_to or _matrix_issue_owner(matrix_issues[0])
        required_actions.append("修正矩阵分析中无法被所引证据支撑的数字或描述。")

    if missing_platforms:
        reject_to = reject_to or "CollectorAgent"
        required_actions.append("补充缺失竞品的 evidence。")

    if not checked_items["product_matrix_not_empty"]:
        reject_to = reject_to or "AnalysisAgent"
        required_actions.append("重新生成 product_matrix。")

    if not checked_items["business_matrix_not_empty"]:
        reject_to = reject_to or "AnalysisAgent"
        required_actions.append("重新生成 business_matrix。")

    return checked_items, missing_dimensions, missing_platforms, required_actions, reject_to


def _quality_result_with_legacy_fields(result: QualityResult, reason: str) -> Dict[str, Any]:
    data = result.model_dump()
    data.update(
        {
            "status": "approved" if result.approved else "rejected",
            "quality_score": result.score,
            # 明确：这是报告可信度/分析质量分，不是产品综合评分。
            "score_type": "report_credibility",
            "score_meaning": "报告可信度 / 分析质量分（非产品评分）",
            "reason": reason,
            "passed_checks": [
                name for name, passed in result.checked_items.items() if passed
            ],
            "failed_checks": [
                name for name, passed in result.checked_items.items() if not passed
            ],
        }
    )
    if not result.approved:
        data["target_agent"] = result.reject_to
        data["required_fix"] = "；".join(result.required_actions)
    return data


def _append_trace(state: dict, quality_result: QualityResult) -> None:
    trace_log = state.setdefault("trace_log", [])
    quality_status = _as_text(state.get("quality_status"))
    trace_status = quality_status or ("success" if quality_result.approved else "rejected")
    if trace_status == "approved":
        trace_status = "success"
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "QualityAgent",
            "status": trace_status,
            "output_summary": (
                "quality approved"
                if quality_result.approved
                else (
                    "quality degraded to partial_report"
                    if quality_status == "partial_report"
                    else f"quality rejected to {quality_result.reject_to}"
                )
            ),
            "error": None,
        }
    )


def quality_agent(state: dict) -> Dict[str, Any]:
    """Run quality checks and set approval or a structured rejection target."""
    evidence_list = [
        item for item in state.get("evidence_list", [])
        if isinstance(item, dict)
    ]
    claims = [
        item for item in state.get("claims", [])
        if isinstance(item, dict)
    ]
    product_matrix = state.get("product_matrix", {})
    business_matrix = state.get("business_matrix", {})
    risk_flags = [
        item for item in state.get("risk_flags", [])
        if isinstance(item, dict)
    ]
    competitors = [
        _as_text(item) for item in state.get("competitors", [])
        if _as_text(item)
    ]
    focus_dimensions = [
        _as_text(item) for item in state.get("focus_dimensions", [])
        if _as_text(item)
    ]
    iteration_count = int(state.get("iteration_count", 0) or 0)
    unsupported_claim_ids = [
        _as_text(item) for item in state.get("unsupported_claim_ids", []) if _as_text(item)
    ]
    faithfulness_report = state.get("faithfulness_report", {})
    if not isinstance(faithfulness_report, dict):
        faithfulness_report = {}
    matrix_issues = [
        item for item in faithfulness_report.get("matrix_issues", []) if isinstance(item, dict)
    ]

    (
        checked_items,
        missing_dimensions,
        missing_platforms,
        required_actions,
        reject_to,
    ) = _build_checked_items(
        evidence_list=evidence_list,
        claims=claims,
        product_matrix=product_matrix if isinstance(product_matrix, dict) else {},
        business_matrix=business_matrix if isinstance(business_matrix, dict) else {},
        risk_flags=risk_flags,
        competitors=competitors,
        focus_dimensions=focus_dimensions,
        unsupported_claim_ids=unsupported_claim_ids,
        matrix_issues=matrix_issues,
        product_compare_mode=bool(state.get("product_compare_mode")),
    )

    approved = all(checked_items.values())
    deductions = sum(1 for passed in checked_items.values() if not passed) * 10
    high_risk_count = len(
        [
            risk
            for risk in risk_flags
            if isinstance(risk, dict) and _as_text(risk.get("severity")).lower() == "high"
        ]
    )
    deductions += min(20, high_risk_count * 4)
    deductions += min(12, len(missing_dimensions) * 4)
    pending_data = [item for item in state.get("pending_data", []) if isinstance(item, dict)]
    pending_statuses = {
        _as_text(item.get("status"))
        for item in pending_data
        if _as_text(item.get("status")) and _as_text(item.get("status")) not in {"complete", "success"}
    }
    pending_penalty = min(18, len(pending_statuses) * 4 + (4 if pending_data else 0))
    score = max(0, 90 - deductions - pending_penalty)
    price_status = state.get("price_status", {}) if isinstance(state.get("price_status"), dict) else {}
    price_verification = (
        faithfulness_report.get("price_verification", {})
        if isinstance(faithfulness_report.get("price_verification"), dict)
        else {}
    )
    review_verification = (
        faithfulness_report.get("review_verification", {})
        if isinstance(faithfulness_report.get("review_verification"), dict)
        else {}
    )
    weak_price_count = int(price_status.get("low_confidence_count") or 0) + int(
        price_verification.get("weak_price_records") or 0
    )
    weak_review_count = int(review_verification.get("weak_review_signals") or 0)
    claim_results = [
        item for item in faithfulness_report.get("claim_results", []) if isinstance(item, dict)
    ]
    weak_claim_count = int(faithfulness_report.get("weak_claim_count") or 0)
    human_unverified_count = len(
        [item for item in claim_results if _as_text(item.get("reason")) == "human_feedback_unverified"]
    )
    weak_price_penalty = min(12, weak_price_count * 4)
    weak_review_penalty = min(10, weak_review_count * 2)
    weak_claim_penalty = min(10, max(0, weak_claim_count - human_unverified_count) * 2)
    human_feedback_penalty = min(18, human_unverified_count * 8)
    score = max(
        0,
        score
        - weak_price_penalty
        - weak_review_penalty
        - weak_claim_penalty
        - human_feedback_penalty,
    )
    reject_reason = None if approved else "部分质量检查未通过"

    quality_result = QualityResult(
        approved=approved,
        score=score,
        reject_to=None if approved else reject_to or "EvidenceAgent",
        reject_reason=reject_reason,
        missing_dimensions=missing_dimensions,
        missing_platforms=missing_platforms,
        matrix_issues=[] if approved else matrix_issues,
        required_actions=[] if approved else required_actions,
        checked_items=checked_items,
    )

    needs_human_review = False
    degraded_report = False
    has_limitations = bool(
        pending_data
        or missing_dimensions
        or missing_platforms
        or high_risk_count
        or weak_price_count
        or weak_review_count
        or weak_claim_count
        or human_unverified_count
    )
    quality_status = (
        "approved_with_limitations"
        if quality_result.approved and has_limitations
        else "approved" if quality_result.approved else "rejected"
    )
    next_iteration_count = iteration_count
    rejected_agents = list(state.get("rejected_agents", []))

    if not quality_result.approved:
        if quality_result.reject_to:
            rejected_agents.append(quality_result.reject_to)
        next_iteration_count = iteration_count + 1
        if next_iteration_count >= MAX_ITERATIONS:
            degraded_report = True
            needs_human_review = False
            quality_status = "partial_report"

    reason = (
        "质检通过，证据链、矩阵完整性和风险水位满足进入策略生成要求；但实时评价、价格或测评数据如为 pending，会降低报告可信度。"
        if quality_result.approved
        else quality_result.reject_reason or "部分质量检查未通过"
    )
    quality_result_dict = _quality_result_with_legacy_fields(quality_result, reason)
    quality_result_dict["status"] = quality_status
    quality_result_dict["report_status"] = quality_status
    quality_result_dict["approved_with_limitations"] = quality_status == "approved_with_limitations"
    quality_result_dict["partial_report"] = quality_status == "partial_report"
    quality_result_dict["auto_degraded"] = degraded_report
    quality_result_dict["limitations"] = []
    if pending_data:
        quality_result_dict["limitations"].append("external_data_pending")
    if missing_dimensions:
        quality_result_dict["limitations"].append("missing_dimensions_disclosed")
    if missing_platforms:
        quality_result_dict["limitations"].append("missing_platforms_disclosed")
    if high_risk_count:
        quality_result_dict["limitations"].append("high_risks_disclosed")
    if weak_price_count:
        quality_result_dict["limitations"].append("weak_price_support")
    if weak_review_count:
        quality_result_dict["limitations"].append("weak_review_support")
    if human_unverified_count:
        quality_result_dict["limitations"].append("human_feedback_unverified")
    if degraded_report:
        quality_result_dict["degradation_reason"] = (
            "Automatic repair attempts were exhausted; unsupported or invalid content "
            "will be excluded and a partial report will be generated."
        )
        quality_result_dict["excluded_claim_ids"] = unsupported_claim_ids
        quality_result_dict["matrix_issues_disclosed"] = matrix_issues
    if pending_data:
        quality_result_dict["pending_data"] = pending_data
        quality_result_dict["evidence_gap_note"] = (
            "Official spec MCP, review intelligence, realtime price or experience evidence "
            "is still pending; report can pass with conservative caveats but should not claim "
            "review-backed fit or price-performance conclusions."
        )
    quality_result_dict["score_breakdown"] = {
        "base_score": 90,
        "failed_check_deductions": sum(1 for passed in checked_items.values() if not passed) * 10,
        "high_risk_deductions": min(20, high_risk_count * 4),
        "missing_dimension_deductions": min(12, len(missing_dimensions) * 4),
        "pending_data_deductions": pending_penalty,
        "weak_price_support_count": weak_price_count,
        "weak_review_support_count": weak_review_count,
        "weak_claim_count": weak_claim_count,
        "human_feedback_unverified_count": human_unverified_count,
        "weak_price_deductions": weak_price_penalty,
        "weak_review_deductions": weak_review_penalty,
        "weak_claim_deductions": weak_claim_penalty,
        "human_feedback_deductions": human_feedback_penalty,
        "note": (
            "Report credibility is reduced by disclosed pending data and risks. Weak price support is "
            "shown as a limitation; weak or pending review/user-feedback data is also part of the reason."
        ),
    }

    next_state = {
        **state,
        "current_agent": "QualityAgent",
        "quality_result": quality_result_dict,
        "is_approved": quality_result.approved,
        "iteration_count": next_iteration_count,
        "rejected_agents": rejected_agents,
        "needs_human_review": needs_human_review,
        "degraded_report": degraded_report,
        "quality_status": quality_status,
    }
    _append_trace(next_state, quality_result)

    print(
        f"[QualityAgent] 质检完成：{quality_result_dict.get('status')}，"
        f"得分 {quality_result_dict.get('quality_score')}"
    )
    return next_state


def quality_router(state: dict) -> str:
    """Route approved states to report_agent, rejected states to a repair node."""
    quality_result = state.get("quality_result", {})
    iteration_count = int(state.get("iteration_count", 0) or 0)
    status = _as_text(quality_result.get("status") or state.get("quality_status"))

    if status in {"approved", "approved_with_limitations", "partial_report"} or state.get("degraded_report"):
        return "report_agent"

    if state.get("needs_human_review") or (
        not quality_result.get("approved")
        and status == "rejected"
        and iteration_count >= MAX_ITERATIONS
    ):
        return "report_agent"

    if (
        state.get("is_approved")
        or quality_result.get("approved")
        or status == "approved"
    ):
        return "report_agent"

    reject_to = quality_result.get("reject_to") or quality_result.get("target_agent")
    return ROUTER_MAP.get(reject_to, "evidence_agent")
