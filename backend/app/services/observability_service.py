"""Local observability helpers for Agent/MCP/LLM execution.

LangSmith is useful for deep traces, but the demo UI should not depend on a
third-party trace page being reachable. These helpers keep a lightweight,
structured record in workflow state so the frontend can always show runtime,
tool usage, token usage, and cost estimates.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List


AGENT_ORDER = [
    "ResearchAgent",
    "CollectorAgent",
    "EvidenceAgent",
    "AnalysisAgent",
    "VerificationAgent",
    "QualityAgent",
    "ReportAgent",
]


LLM_AGENT_BY_TOOL = {
    "official_spec_mcp": "CollectorAgent",
    "price_mcp": "CollectorAgent",
    "review_intel_mcp": "CollectorAgent",
    "swot_ai": "AnalysisAgent",
}


MCP_AGENT_BY_TOOL = {
    "search_mcp": "CollectorAgent",
    "official_spec_mcp": "CollectorAgent",
    "price_mcp": "CollectorAgent",
    "review_intel_mcp": "CollectorAgent",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return 0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _extract_usage(response: Any) -> Dict[str, int]:
    """Read token usage from common LangChain/OpenAI-compatible shapes."""
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        prompt = _as_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
        completion = _as_int(usage.get("output_tokens") or usage.get("completion_tokens"))
        total = _as_int(usage.get("total_tokens")) or prompt + completion
        if total or prompt or completion:
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
            }

    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        for key in ("token_usage", "usage"):
            nested = metadata.get(key)
            if isinstance(nested, dict):
                prompt = _as_int(nested.get("prompt_tokens") or nested.get("input_tokens"))
                completion = _as_int(nested.get("completion_tokens") or nested.get("output_tokens"))
                total = _as_int(nested.get("total_tokens")) or prompt + completion
                if total or prompt or completion:
                    return {
                        "prompt_tokens": prompt,
                        "completion_tokens": completion,
                        "total_tokens": total,
                    }

    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Mixed Chinese/English prompt estimate. This is deliberately marked as
    # estimated in the record when provider usage is unavailable.
    return max(1, int(len(text) / 3.5))


def _estimated_cost(prompt_tokens: int, completion_tokens: int) -> float:
    input_per_1k = _env_float("OBS_INPUT_COST_PER_1K", 0.00014)
    output_per_1k = _env_float("OBS_OUTPUT_COST_PER_1K", 0.00028)
    return round(prompt_tokens / 1000 * input_per_1k + completion_tokens / 1000 * output_per_1k, 6)


def langsmith_enabled() -> bool:
    return os.getenv("ENABLE_LANGSMITH", "").strip().lower() in {"1", "true", "yes", "on"} or os.getenv(
        "LANGCHAIN_TRACING_V2", ""
    ).strip().lower() in {"1", "true", "yes", "on"}


def make_langsmith_run_collector() -> Any | None:
    """Create a local run collector when LangSmith tracing is enabled.

    The collector does not replace LangSmith tracing. It only keeps the root run
    object locally long enough for us to ask the LangSmith SDK for a UI URL.
    """
    if not langsmith_enabled():
        return None
    try:
        from langchain_core.tracers.run_collector import RunCollectorCallbackHandler

        return RunCollectorCallbackHandler()
    except Exception:
        return None


def resolve_langsmith_trace(collector: Any | None) -> Dict[str, Any]:
    if collector is None:
        return {
            "enabled": langsmith_enabled(),
            "project": os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
            "trace_url": "",
            "run_id": "",
            "status": "disabled" if not langsmith_enabled() else "collector_unavailable",
        }
    runs = [item for item in getattr(collector, "traced_runs", []) if item is not None]
    if not runs:
        return {
            "enabled": True,
            "project": os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
            "trace_url": "",
            "run_id": "",
            "status": "no_collected_run",
        }

    root_run = next((run for run in runs if not getattr(run, "parent_run_id", None)), runs[0])
    try:
        from langsmith import Client

        client = Client()
        trace_url = client.get_run_url(
            run=root_run,
            project_name=os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
        )
        return {
            "enabled": True,
            "project": os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
            "trace_url": trace_url,
            "run_id": _as_text(getattr(root_run, "id", "")),
            "status": "available",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "project": os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
            "trace_url": "",
            "run_id": _as_text(getattr(root_run, "id", "")),
            "status": "url_unavailable",
            "error": type(exc).__name__,
        }


def make_llm_usage_record(
    *,
    agent: str,
    tool: str,
    model: str,
    started_at: float,
    prompt_text: str = "",
    response: Any = None,
    response_text: str = "",
    status: str = "success",
    error: str = "",
    trace_url: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    usage = _extract_usage(response)
    usage_source = "provider" if usage.get("total_tokens") else "estimated"
    if usage_source == "estimated":
        usage = {
            "prompt_tokens": _estimate_tokens(prompt_text),
            "completion_tokens": _estimate_tokens(response_text),
        }
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    prompt_tokens = _as_int(usage.get("prompt_tokens"))
    completion_tokens = _as_int(usage.get("completion_tokens"))
    total_tokens = _as_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
    return {
        "agent": agent,
        "tool": tool,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _estimated_cost(prompt_tokens, completion_tokens),
        "latency_ms": int(max(0, (time.perf_counter() - started_at) * 1000)),
        "status": status,
        "error": error,
        "trace_url": trace_url,
        "usage_source": usage_source,
        "called_at": _now_iso(),
        "metadata": metadata or {},
    }


def make_mcp_usage_record(
    *,
    agent: str,
    tool: str,
    status: str,
    started_at: float | None = None,
    latency_ms: int | None = None,
    provider: str = "",
    query: str = "",
    result_count: int = 0,
    uses_llm: bool = False,
    external_call_count: int = 1,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if latency_ms is None:
        latency_ms = int(max(0, (time.perf_counter() - started_at) * 1000)) if started_at else 0
    return {
        "agent": agent,
        "tool": tool,
        "provider": provider,
        "status": status,
        "latency_ms": latency_ms,
        "query": query,
        "result_count": result_count,
        "uses_llm": uses_llm,
        "external_call_count": max(1, _as_int(external_call_count)),
        "called_at": _now_iso(),
        "metadata": metadata or {},
    }


def append_usage_from_records(state: Dict[str, Any], records: Iterable[Dict[str, Any]]) -> None:
    llm_usage = list(state.get("llm_usage", [])) if isinstance(state.get("llm_usage"), list) else []
    mcp_usage = list(state.get("mcp_usage", [])) if isinstance(state.get("mcp_usage"), list) else []
    seen_llm = {str(item.get("usage_id") or item) for item in llm_usage if isinstance(item, dict)}
    seen_mcp = {str(item.get("usage_id") or item) for item in mcp_usage if isinstance(item, dict)}

    for record in records:
        if not isinstance(record, dict):
            continue
        for key, target, seen in (("llm_usage", llm_usage, seen_llm), ("mcp_usage", mcp_usage, seen_mcp)):
            usage = record.get(key)
            items = usage if isinstance(usage, list) else [usage] if isinstance(usage, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                identity = str(item.get("usage_id") or item)
                if identity in seen:
                    continue
                target.append(item)
                seen.add(identity)

    state["llm_usage"] = llm_usage
    state["mcp_usage"] = mcp_usage


def append_mcp_usage(state: Dict[str, Any], records: Iterable[Dict[str, Any]]) -> None:
    mcp_usage = list(state.get("mcp_usage", [])) if isinstance(state.get("mcp_usage"), list) else []
    seen = {str(item.get("usage_id") or item) for item in mcp_usage if isinstance(item, dict)}
    for item in records:
        if not isinstance(item, dict):
            continue
        identity = str(item.get("usage_id") or item)
        if identity in seen:
            continue
        mcp_usage.append(item)
        seen.add(identity)
    state["mcp_usage"] = mcp_usage


def _trace_status_for_agent(trace_log: List[Dict[str, Any]], task_status: str, current_agent: str, agent: str) -> str:
    entries = [item for item in trace_log if isinstance(item, dict) and item.get("agent_name") == agent]
    if entries:
        last = entries[-1]
        status = _as_text(last.get("status")) or "completed"
        if status in {"success", "partial", "applied"}:
            return "completed" if status == "success" else status
        return status
    if current_agent == agent and task_status == "running":
        return "running"
    return "waiting"


def build_observability_payload(task_id: str, state: Dict[str, Any], *, task_status: str, current_agent: str) -> Dict[str, Any]:
    trace_log = [item for item in state.get("trace_log", []) if isinstance(item, dict)]
    llm_usage = [item for item in state.get("llm_usage", []) if isinstance(item, dict)]
    mcp_usage = [item for item in state.get("mcp_usage", []) if isinstance(item, dict)]

    llm_agents = defaultdict(int)
    mcp_agents = defaultdict(int)
    for item in llm_usage:
        llm_agents[_as_text(item.get("agent")) or LLM_AGENT_BY_TOOL.get(_as_text(item.get("tool")), "")] += 1
    for item in mcp_usage:
        mcp_agents[_as_text(item.get("agent")) or MCP_AGENT_BY_TOOL.get(_as_text(item.get("tool")), "")] += _as_int(item.get("external_call_count")) or 1

    trace_by_agent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in trace_log:
        trace_by_agent[_as_text(item.get("agent_name"))].append(item)

    agent_trace: List[Dict[str, Any]] = []
    for index, agent in enumerate(AGENT_ORDER, start=1):
        entries = trace_by_agent.get(agent, [])
        duration_ms = sum(_as_int(item.get("duration_ms")) for item in entries)
        agent_trace.append(
            {
                "order": index,
                "agent": agent,
                "status": _trace_status_for_agent(trace_log, task_status, current_agent, agent),
                "duration_ms": duration_ms,
                "calls_mcp": bool(mcp_agents.get(agent)),
                "calls_llm": bool(llm_agents.get(agent)),
                "mcp_call_count": mcp_agents.get(agent, 0),
                "llm_call_count": llm_agents.get(agent, 0),
                "summary": _as_text(entries[-1].get("output_summary")) if entries else "",
            }
        )

    per_agent: Dict[str, Dict[str, Any]] = {}
    for agent in AGENT_ORDER:
        per_agent[agent] = {
            "agent": agent,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "llm_call_count": 0,
        }
    for item in llm_usage:
        agent = _as_text(item.get("agent")) or LLM_AGENT_BY_TOOL.get(_as_text(item.get("tool")), "UnknownAgent")
        bucket = per_agent.setdefault(
            agent,
            {
                "agent": agent,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "llm_call_count": 0,
            },
        )
        bucket["prompt_tokens"] += _as_int(item.get("prompt_tokens"))
        bucket["completion_tokens"] += _as_int(item.get("completion_tokens"))
        bucket["total_tokens"] += _as_int(item.get("total_tokens"))
        bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"] + float(item.get("estimated_cost_usd") or 0), 6)
        bucket["llm_call_count"] += 1

    totals = {
        "prompt_tokens": sum(_as_int(item.get("prompt_tokens")) for item in llm_usage),
        "completion_tokens": sum(_as_int(item.get("completion_tokens")) for item in llm_usage),
        "total_tokens": sum(_as_int(item.get("total_tokens")) for item in llm_usage),
        "estimated_cost_usd": round(sum(float(item.get("estimated_cost_usd") or 0) for item in llm_usage), 6),
        "mcp_call_count": sum(_as_int(item.get("external_call_count")) or 1 for item in mcp_usage),
        "llm_call_count": len(llm_usage),
        "total_duration_ms": sum(_as_int(item.get("duration_ms")) for item in agent_trace),
    }

    langsmith_info = state.get("langsmith") if isinstance(state.get("langsmith"), dict) else {}
    return {
        "task_id": task_id,
        "status": task_status,
        "current_agent": current_agent,
        "agent_trace": agent_trace,
        "llm_usage": llm_usage,
        "mcp_usage": mcp_usage,
        "per_agent": list(per_agent.values()),
        "totals": totals,
        "langsmith": {
            "enabled": bool(langsmith_info.get("enabled")) if langsmith_info else langsmith_enabled(),
            "project": _as_text(langsmith_info.get("project")) or os.getenv("LANGCHAIN_PROJECT", "competitive-analysis-agent"),
            "trace_url": _as_text(
                state.get("langsmith_trace_url")
                or state.get("trace_url")
                or langsmith_info.get("trace_url")
            ),
            "run_id": _as_text(langsmith_info.get("run_id")),
            "status": _as_text(langsmith_info.get("status")),
            "error": _as_text(langsmith_info.get("error")),
        },
    }
