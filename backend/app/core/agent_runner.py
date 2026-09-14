"""Resilient node runner for the LangGraph workflow.

Every agent is executed through ``run_node`` so that a single misbehaving agent does
not crash the whole graph. On success the node's update is returned unchanged (the
agents already append their own success trace entry). On an uncaught exception or a
schema-validation failure the runner:

- records a ``failed`` / ``schema_failed`` entry in ``trace_log`` (with duration), and
- records a structured entry in ``error_log``,

then returns a minimal recovery update so the graph keeps flowing. Downstream agents and
the QualityAgent already degrade gracefully on missing data (empty matrices/claims get
rejected and eventually routed to human review), turning an agent crash into observable,
recoverable degradation instead of a hard failure.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Type

from pydantic import BaseModel, ValidationError

from app.services.error_log_service import append_error


def _recover(
    state: dict,
    agent_name: str,
    status: str,
    error_type: str,
    message: str,
    duration_ms: int,
) -> Dict[str, Any]:
    existing_trace: List[Dict[str, Any]] = list(state.get("trace_log", []))
    trace_entry = {
        "step_id": len(existing_trace) + 1,
        "agent_name": agent_name,
        "status": status,
        "output_summary": f"{agent_name} {status}: recorded and recovered with degraded output",
        "duration_ms": duration_ms,
        "error": message,
    }
    return {
        "current_agent": agent_name,
        # trace_log has a merge reducer, so returning just the new entry appends it.
        "trace_log": [trace_entry],
        # error_log has no reducer (overwrite), so carry the full accumulated list.
        "error_log": append_error(
            state.get("error_log", []),
            agent_name=agent_name,
            error_type=error_type,
            message=message,
            recover_action="degrade_and_continue",
            retry_count=int(state.get("iteration_count", 0) or 0),
        ),
    }


def run_node(
    agent_name: str,
    agent_func: Callable[[dict], dict],
    state: dict,
    output_schema: Optional[Type[BaseModel]] = None,
    output_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Run an agent with schema validation and error recovery.

    ``output_schema``/``output_keys`` (optional) validate just the subset of the node's
    update that the agent owns, e.g. ``ReportAgentOutput`` over ``final_report`` and
    ``claims``. A validation failure is recovered like any other error.
    """
    start = time.time()
    try:
        update = agent_func(state) or {}
        if output_schema is not None and output_keys is not None:
            subset = {key: update.get(key) for key in output_keys}
            output_schema.model_validate(subset)
        return update
    except ValidationError as exc:
        duration_ms = int((time.time() - start) * 1000)
        return _recover(state, agent_name, "schema_failed", "schema_validation_failed", str(exc), duration_ms)
    except Exception as exc:  # noqa: BLE001 - the whole point is to contain any agent error.
        duration_ms = int((time.time() - start) * 1000)
        return _recover(state, agent_name, "failed", "agent_failed", str(exc), duration_ms)
