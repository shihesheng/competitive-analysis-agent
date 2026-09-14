"""Build human review tickets from rejected workflow states."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from app.schemas.review import ReviewTicket


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_review_ticket(state: Dict[str, Any]) -> Dict[str, Any]:
    quality_result = state.get("quality_result", {})
    if not isinstance(quality_result, dict):
        quality_result = {}

    faithfulness_report = state.get("faithfulness_report", {})
    if not isinstance(faithfulness_report, dict):
        faithfulness_report = {}

    failed_checks = [
        str(item)
        for item in _as_list(quality_result.get("failed_checks"))
        if str(item).strip()
    ]
    required_actions = [
        str(item)
        for item in _as_list(quality_result.get("required_actions"))
        if str(item).strip()
    ]
    matrix_issues = [
        item for item in _as_list(quality_result.get("matrix_issues"))
        if isinstance(item, dict)
    ] or [
        item for item in _as_list(faithfulness_report.get("matrix_issues"))
        if isinstance(item, dict)
    ]
    unsupported_claim_ids = [
        str(item)
        for item in _as_list(state.get("unsupported_claim_ids"))
        if str(item).strip()
    ]

    suggested_next_steps = []
    if unsupported_claim_ids:
        suggested_next_steps.append("逐条核对 unsupported_claim_ids，删除或改写无法被证据支撑的 claim。")
    if matrix_issues:
        suggested_next_steps.append("检查 matrix_issues 中的矩阵单元格，移除未被证据支撑的数字或描述。")
    if quality_result.get("missing_dimensions"):
        suggested_next_steps.append("补充缺失维度的数据采集，再重新运行分析。")
    if quality_result.get("missing_platforms"):
        suggested_next_steps.append("补充缺失竞品的数据采集，再重新运行分析。")
    if not suggested_next_steps:
        suggested_next_steps.append("根据 failed_checks 和 required_actions 复核证据链后重新运行分析。")

    ticket = ReviewTicket(
        ticket_id=f"RT-{uuid4().hex[:10]}",
        reason="automatic retries exhausted; human review required",
        target_agent=quality_result.get("reject_to") or quality_result.get("target_agent"),
        failed_checks=failed_checks,
        required_actions=required_actions,
        unsupported_claim_ids=unsupported_claim_ids,
        matrix_issues=matrix_issues,
        missing_dimensions=[
            str(item)
            for item in _as_list(quality_result.get("missing_dimensions"))
            if str(item).strip()
        ],
        missing_platforms=[
            str(item)
            for item in _as_list(quality_result.get("missing_platforms"))
            if str(item).strip()
        ],
        risk_flags=[
            item for item in _as_list(state.get("risk_flags"))
            if isinstance(item, dict) and str(item.get("severity", "")).lower() == "high"
        ],
        suggested_next_steps=suggested_next_steps,
        created_at=_now(),
    )
    return ticket.model_dump()
