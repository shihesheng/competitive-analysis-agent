"""Context management for LLM prompts.

The analysis agents (Product/Business) used to serialize the *entire* evidence_list
into their prompt. That is fine for a small curated dataset, but once a real
external collection feeds in dozens or hundreds of long evidence records the prompt would blow past
the context window, inflate cost/latency, and degrade quality ("lost in the middle").

This module selects and trims evidence before it is serialized into a prompt:

- rank by credibility / confidence (then recency, then id) so the strongest sources win
  the limited budget,
- cap the number of items per dimension and overall,
- truncate each record's raw_content to a character budget,
- keep only the fields the LLM actually needs.

Selection only affects what the LLM *sees*. The agents still validate and build their
fallback output against the full evidence_list, so traceability is unaffected.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

_CREDIBILITY_RANK = {"high": 3, "medium": 2, "low": 1}

DEFAULT_MAX_ITEMS = 40
DEFAULT_MAX_PER_DIMENSION = 8
DEFAULT_MAX_CONTENT_CHARS = 240


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _confidence(evidence: Dict[str, Any]) -> float:
    value = evidence.get("confidence_score")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _rank_key(evidence: Dict[str, Any]):
    credibility = _CREDIBILITY_RANK.get(_as_text(evidence.get("credibility")).lower(), 0)
    publish_time = _as_text(evidence.get("publish_time"))
    # Higher credibility, higher confidence and more recent publish_time first.
    return (credibility, _confidence(evidence), publish_time, _as_text(evidence.get("evidence_id")))


def _slim(evidence: Dict[str, Any], max_chars: int) -> Dict[str, Any]:
    raw_content = _as_text(evidence.get("raw_content") or evidence.get("content"))
    if max_chars and len(raw_content) > max_chars:
        raw_content = raw_content[:max_chars].rstrip() + "…"
    return {
        "evidence_id": _as_text(evidence.get("evidence_id")),
        "platform": _as_text(evidence.get("platform")),
        "related_dimension": _as_text(
            evidence.get("related_dimension") or evidence.get("dimension")
        ),
        "source_type": _as_text(evidence.get("source_type")),
        "credibility": _as_text(evidence.get("credibility")),
        "confidence_score": _confidence(evidence),
        "claim": _as_text(evidence.get("claim") or evidence.get("summary")),
        "raw_content": raw_content,
    }


def select_evidence_for_prompt(
    evidence_list: List[Dict[str, Any]],
    max_items: int | None = None,
    max_per_dimension: int | None = None,
    max_content_chars: int | None = None,
) -> List[Dict[str, Any]]:
    """Return a ranked, trimmed, slimmed subset of evidence for an LLM prompt."""
    max_items = max_items or _env_int("CONTEXT_MAX_EVIDENCE_ITEMS", DEFAULT_MAX_ITEMS)
    max_per_dimension = max_per_dimension or _env_int(
        "CONTEXT_MAX_EVIDENCE_PER_DIMENSION", DEFAULT_MAX_PER_DIMENSION
    )
    max_content_chars = max_content_chars or _env_int(
        "CONTEXT_MAX_EVIDENCE_CHARS", DEFAULT_MAX_CONTENT_CHARS
    )

    items = [item for item in evidence_list if isinstance(item, dict)]
    ranked = sorted(items, key=_rank_key, reverse=True)

    per_dimension: Dict[str, int] = {}
    selected: List[Dict[str, Any]] = []
    for evidence in ranked:
        if len(selected) >= max_items:
            break
        dimension = _as_text(evidence.get("related_dimension") or evidence.get("dimension"))
        if per_dimension.get(dimension, 0) >= max_per_dimension:
            continue
        per_dimension[dimension] = per_dimension.get(dimension, 0) + 1
        selected.append(_slim(evidence, max_content_chars))

    # Keep a stable, readable order (by evidence_id) once the budget is decided.
    selected.sort(key=lambda item: item.get("evidence_id", ""))
    return selected


def select_evidence_context(
    agent_name: str,
    evidence_list: List[Dict[str, Any]],
    max_items: int | None = None,
    max_per_dimension: int | None = None,
    max_content_chars: int | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return prompt evidence plus an observable context-management summary."""
    max_items = max_items or _env_int("CONTEXT_MAX_EVIDENCE_ITEMS", DEFAULT_MAX_ITEMS)
    max_per_dimension = max_per_dimension or _env_int(
        "CONTEXT_MAX_EVIDENCE_PER_DIMENSION", DEFAULT_MAX_PER_DIMENSION
    )
    max_content_chars = max_content_chars or _env_int(
        "CONTEXT_MAX_EVIDENCE_CHARS", DEFAULT_MAX_CONTENT_CHARS
    )

    items = [item for item in evidence_list if isinstance(item, dict)]
    selected = select_evidence_for_prompt(
        items,
        max_items=max_items,
        max_per_dimension=max_per_dimension,
        max_content_chars=max_content_chars,
    )
    selected_ids = [
        _as_text(item.get("evidence_id")) for item in selected if _as_text(item.get("evidence_id"))
    ]
    all_ids = [
        _as_text(item.get("evidence_id")) for item in items if _as_text(item.get("evidence_id"))
    ]
    selected_id_set = set(selected_ids)
    trimmed_ids = [evidence_id for evidence_id in all_ids if evidence_id not in selected_id_set]

    dimension_counts: Dict[str, int] = {}
    for item in selected:
        dimension = _as_text(item.get("related_dimension")) or "unknown"
        dimension_counts[dimension] = dimension_counts.get(dimension, 0) + 1

    summary = {
        "agent_name": agent_name,
        "total_evidence_count": len(items),
        "selected_evidence_count": len(selected),
        "trimmed_evidence_count": max(0, len(items) - len(selected)),
        "selected_evidence_ids": selected_ids,
        "trimmed_evidence_ids": trimmed_ids,
        "dimension_counts": dimension_counts,
        "limits": {
            "max_items": max_items,
            "max_per_dimension": max_per_dimension,
            "max_content_chars": max_content_chars,
        },
    }
    return selected, summary
