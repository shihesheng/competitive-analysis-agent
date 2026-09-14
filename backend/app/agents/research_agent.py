from __future__ import annotations

from typing import Any, Dict

from app.services.research_provider_factory import ResearchProviderFactory
from app.services.error_log_service import append_error, normalize_error_log


def _append_trace(state: dict, raw_research_count: int) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "ResearchAgent",
            "status": "success",
            "input_summary": "planned data requirements for this analysis",
            "output_summary": f"planned data requirements; raw_research_items={raw_research_count}",
            "pending_fields": state.get("data_requirements", []),
            "error": None,
        }
    )


def _is_product_compare_request(state: dict) -> bool:
    if state.get("product_compare_mode"):
        return True
    if state.get("industry_key") != "gaming_mouse":
        return False
    inputs = []
    for value in [state.get("target_platform"), *(state.get("competitors") or [])]:
        text = str(value or "").strip()
        if text and text not in inputs:
            inputs.append(text)
    return len(inputs) >= 2


def research_agent(state: dict) -> Dict[str, Any]:
    """Plan product data needs or collect real research through the provider abstraction."""
    error_log = normalize_error_log(state.get("error_log", []))
    data_requirements = [
        "local_product_facts",
        "official_specs",
        "user_reviews",
        "creator_reviews",
        "realtime_price",
        "software_driver_ecosystem",
    ]

    # 产品对比模式：这里只规划数据需求，不调用 MCP provider。
    if _is_product_compare_request(state):
        raw_research = [item for item in state.get("raw_research", []) if isinstance(item, dict)]
        next_state = {
            **state,
            "product_compare_mode": True,
            "current_agent": "ResearchAgent",
            "data_requirements": data_requirements,
            "raw_research": raw_research,
            "error_log": error_log,
            "metrics": state.get("metrics", {}),
        }
        _append_trace(next_state, len(raw_research))
        print(f"[ResearchAgent] 产品对比模式：已规划数据需求，未执行 MCP 采集，raw_research={len(raw_research)}")
        return next_state

    try:
        raw_items = ResearchProviderFactory.create().collect(state)
        raw_research = [item.model_dump() for item in raw_items]
    except Exception as exc:
        error_log = append_error(
            error_log,
            agent_name="ResearchAgent",
            error_type="provider_failed",
            message=f"ResearchAgent provider 采集失败：{exc}",
            recover_action="continue_with_empty_raw_research",
            retry_count=int(state.get("iteration_count", 0) or 0),
        )
        raw_research = []

    next_state = {
        **state,
        "current_agent": "ResearchAgent",
        "data_requirements": data_requirements,
        "raw_research": raw_research,
        "error_log": error_log,
        "metrics": state.get("metrics", {}),
    }
    _append_trace(next_state, len(raw_research))

    print(f"[ResearchAgent] 采集完成，共 {len(raw_research)} 条原始研究数据")
    return next_state
