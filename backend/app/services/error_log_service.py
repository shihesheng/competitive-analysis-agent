"""Structured error log helpers for agent recovery paths."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_error_entry(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, dict):
        return {
            "error_id": str(entry.get("error_id") or f"ERR-{uuid4().hex[:8]}"),
            "agent_name": str(entry.get("agent_name") or "UnknownAgent"),
            "error_type": str(entry.get("error_type") or "unknown_error"),
            "message": str(entry.get("message") or ""),
            "recover_action": str(entry.get("recover_action") or "record_only"),
            "retry_count": int(entry.get("retry_count") or 0),
            "created_at": str(entry.get("created_at") or _now()),
        }

    return {
        "error_id": f"ERR-{uuid4().hex[:8]}",
        "agent_name": "UnknownAgent",
        "error_type": "legacy_error",
        "message": str(entry),
        "recover_action": "record_only",
        "retry_count": 0,
        "created_at": _now(),
    }


def normalize_error_log(error_log: Any) -> List[Dict[str, Any]]:
    if not isinstance(error_log, list):
        return []
    return [normalize_error_entry(item) for item in error_log]


def append_error(
    error_log: Any,
    agent_name: str,
    error_type: str,
    message: str,
    recover_action: str,
    retry_count: int = 0,
) -> List[Dict[str, Any]]:
    errors = normalize_error_log(error_log)
    errors.append(
        {
            "error_id": f"ERR-{uuid4().hex[:8]}",
            "agent_name": agent_name,
            "error_type": error_type,
            "message": message,
            "recover_action": recover_action,
            "retry_count": retry_count,
            "created_at": _now(),
        }
    )
    return errors
