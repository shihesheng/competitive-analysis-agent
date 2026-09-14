"""Collector Agent for the product-focused competitive-analysis workflow.

The public DAG exposes one collection role instead of several tiny MCP/status
nodes. Internally this agent performs four structured steps:

1. Resolve user inputs to official product entities.
2. Load stable hardware facts from the local product JSON catalog.
3. Mark official-spec, review-intel, and price data that still need MCP tools.
4. Seed structured evidence for downstream agents.

No network collection happens here. Missing external data is represented as
``pending_data`` so QualityAgent can lower report confidence without pretending the
data was collected.
"""

from __future__ import annotations

import time
import re
from typing import Any, Dict, List

from app.services import product_catalog_service as catalog
from app.services.official_spec_mcp_service import (
    collect_official_specs,
    merge_official_records,
    product_from_official_spec,
)
from app.services.price_mcp_service import (
    collect_prices,
    price_records_to_evidence,
    summarize_price_status,
)
from app.services.product_compare_service import build_compare_payload
from app.services.review_intel_mcp_service import (
    collect_review_intel,
    merge_review_records_into_evidence,
    summarize_review_intel_status,
)
from app.services.observability_service import (
    append_mcp_usage,
    append_usage_from_records,
    make_mcp_usage_record,
)
from app.services.search_mcp_service import search_candidates


EXPERIENCE_PENDING_DIMENSIONS = [
    "grip_feel",
    "hand_size_fit",
    "game_type_fit",
    "long_term_reliability",
    "driver_reputation",
    "community_sentiment",
]

OFFICIAL_SPEC_FIELDS = [
    "weight_g",
    "dimensions_mm",
    "shape",
    "shape_detail",
    "sensor",
    "dpi_max",
    "polling_rate_hz",
    "connection",
    "battery_hours",
    "switch_type",
    "click_system",
    "software",
    "onboard_memory",
    "mold_id",
    "official_url",
    "field_confidence",
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _model(product: Dict[str, Any]) -> str:
    return _as_text(product.get("model") or product.get("id"))


def _append_trace(
    state: dict,
    *,
    status: str,
    input_summary: str,
    output_summary: str,
    started_at: float,
    evidence_added: int = 0,
    pending_fields: List[str] | None = None,
    substeps: List[Dict[str, Any]] | None = None,
) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "CollectorAgent",
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "evidence_added": evidence_added,
            "pending_fields": pending_fields or [],
            "substeps": substeps or [],
            "duration_ms": int((time.time() - started_at) * 1000),
            "error": None,
        }
    )


def _pending_entry(agent: str, status: str, fields: List[str], note: str) -> Dict[str, Any]:
    return {
        "agent": agent,
        "status": status,
        "fields": fields,
        "note": note,
    }


def _append_pending(state: dict, entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    pending = [item for item in state.get("pending_data", []) if isinstance(item, dict)]
    key = (entry.get("agent"), entry.get("status"))
    if not any((item.get("agent"), item.get("status")) == key for item in pending):
        pending.append(entry)
    return pending


def _selected_inputs(state: dict) -> List[Any]:
    selected = state.get("selected_products", [])
    if isinstance(selected, list) and selected:
        return selected

    candidates: List[Any] = []
    target = _as_text(state.get("target_platform"))
    if target:
        candidates.append(target)
    for competitor in state.get("competitors", []) or []:
        text = _as_text(competitor)
        if text and text not in candidates:
            candidates.append(text)
    return candidates[:2]


def _input_query(item: Any) -> tuple[str, str | None]:
    if isinstance(item, dict):
        query = _as_text(
            item.get("original_input")
            or item.get("query")
            or item.get("id")
            or item.get("model")
            or item.get("brand")
        )
        preferred_id = _as_text(item.get("id")) or None
        return query, preferred_id
    return _as_text(item), None


def _choose_search_result(category: str, query: str, preferred_id: str | None) -> Dict[str, Any]:
    detail = catalog.search_products_detailed(category, query)
    results = [item for item in detail.get("results", []) if isinstance(item, dict)]
    if preferred_id:
        for result in results:
            if _as_text(result.get("id")) == preferred_id:
                result["disambiguation_reason"] = detail.get("disambiguation_reason")
                return result
    if results:
        results[0]["disambiguation_reason"] = detail.get("disambiguation_reason")
        return results[0]

    product, matched_by, matched_value = catalog.resolve_product(category, query)
    return {
        "id": product.get("id"),
        "brand": product.get("brand"),
        "model": product.get("model"),
        "matched_by": matched_by,
        "matched_value": matched_value,
        "match_confidence": "verified" if matched_by in {"id", "model", "alias"} else matched_by,
        "product": product,
        "disambiguation_reason": None,
    }


def _resolve_products(state: dict, category: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    resolved: List[Dict[str, Any]] = []
    full_products: List[Dict[str, Any]] = []
    unresolved: List[str] = []

    for raw_item in _selected_inputs(state):
        query, preferred_id = _input_query(raw_item)
        if not query:
            continue
        try:
            result = _choose_search_result(category, query, preferred_id)
        except Exception:
            unresolved.append(query)
            continue

        product = result.get("product") if isinstance(result.get("product"), dict) else {}
        if not product:
            unresolved.append(query)
            continue

        confidence = _as_text(result.get("match_confidence")) or "unknown"
        matched_by = _as_text(result.get("matched_by"))
        alias_warning = ""
        if matched_by == "community_alias" and confidence != "verified":
            alias_warning = "Community alias is not confirmed as an official product name."

        resolved.append(
            {
                "original_input": query,
                "resolved_product_id": product.get("id"),
                "official_brand": product.get("brand"),
                "official_model": product.get("model"),
                "matched_by": matched_by,
                "matched_value": result.get("matched_value"),
                "match_confidence": confidence,
                "alias_warning": alias_warning,
                "disambiguation_note": result.get("disambiguation_reason"),
                "family": product.get("family"),
                "variant_name": product.get("variant_name"),
                "variant_type": product.get("variant_type"),
                "mold_id": product.get("mold_id"),
                "click_system": product.get("click_system"),
                "product": product,
            }
        )
        full_products.append(product)

    return resolved, full_products, unresolved


def _official_spec_status(product_facts: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    statuses: List[Dict[str, Any]] = []
    for fact in product_facts:
        if not isinstance(fact, dict):
            continue
        specs = fact.get("specs") if isinstance(fact.get("specs"), dict) else {}
        connection = specs.get("connection") if isinstance(specs.get("connection"), list) else []
        missing = []
        for field in OFFICIAL_SPEC_FIELDS:
            if field == "battery_hours" and "2.4ghz" not in connection and "bluetooth" not in connection:
                continue
            if specs.get(field) in (None, "", []):
                missing.append(field)
        statuses.append(
            {
                "product_id": fact.get("product_id"),
                "model": fact.get("model"),
                "status": "pending" if missing else "complete",
                "mcp_required": bool(missing),
                "missing_official_fields": missing,
                "next_action": "future_official_spec_mcp" if missing else "none",
            }
        )

    pending_fields = sorted(
        {field for item in statuses for field in item.get("missing_official_fields", [])}
    )
    return statuses, pending_fields


def _unresolved_official_status(unresolved: List[str]) -> List[Dict[str, Any]]:
    return [
        {
            "input": item,
            "status": "pending",
            "mcp_required": True,
            "missing_official_fields": list(OFFICIAL_SPEC_FIELDS),
            "next_action": "future_search_and_official_spec_mcp",
            "note": "Local product JSON did not match this input; official model and hardware specs must be collected externally.",
        }
        for item in unresolved
    ]


def _review_intel_status(review_records: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    if review_records:
        return summarize_review_intel_status(review_records)
    return {
        "status": "mcp_not_connected",
        "mcp_required": True,
        "review_dimensions_pending": list(EXPERIENCE_PENDING_DIMENSIONS),
        "contribution_to_final_score": 0,
        "sources_pending": ["bilibili", "youtube", "ecommerce_reviews", "creator_reviews"],
    }


def _price_status(price_records: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    if price_records:
        return summarize_price_status(price_records)
    return {
        "status": "pending",
        "price_data_required": True,
        "records": [],
        "collected_count": 0,
        "sample_count": 0,
        "contribution_to_final_score": 0,
        "note": "Prices are time-sensitive and should be collected by PriceMCP.",
    }


def _append_price_pending(
    state: dict,
    price_status: Dict[str, Any],
    collected_count: int,
    target_count: int,
) -> List[Dict[str, Any]]:
    """价格未全收齐、或仅低可信 / 官方价被反爬拦截时，登记一条 price pending，
    让 QualityAgent 据此下调报告可信度分。"""
    fully_collected = bool(target_count) and collected_count >= target_count
    if fully_collected:
        return [item for item in state.get("pending_data", []) if isinstance(item, dict)]
    status_label = _as_text(price_status.get("status")) or "pending"
    note = _as_text(price_status.get("note")) or "Realtime price is intentionally not read from local JSON."
    return _append_pending(
        state,
        _pending_entry(
            "CollectorAgent.price",
            status_label,
            ["realtime_price", "discounts", "regional_availability"],
            note,
        ),
    )


def _search_unresolved_products(unresolved: List[str], category: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in unresolved:
        if not _as_text(item):
            continue
        started = time.perf_counter()
        result = search_candidates(
            item,
            category=category,
            intent="product_entity_resolution",
        )
        result["mcp_usage"] = make_mcp_usage_record(
            agent="CollectorAgent",
            tool="search_mcp",
            status=_as_text(result.get("status")) or "success",
            started_at=started,
            provider=_as_text(result.get("provider")) or "search",
            query=_as_text(result.get("executed_query") or result.get("_executed_query") or item),
            result_count=len(result.get("candidates") if isinstance(result.get("candidates"), list) else []),
            uses_llm=False,
            metadata={"intent": "product_entity_resolution", "input": item},
        )
        results.append(result)
    return results


LOCAL_COMPLETE_FIELDS = [
    "weight_g",
    "dimensions_mm",
    "sensor",
    "dpi_max",
    "polling_rate_hz",
    "connection",
]


def _has_complete_local_facts(product: Dict[str, Any]) -> bool:
    """本地命中产品是否已具备核心硬件字段（具备则无需再走官方抽取）。"""
    if not isinstance(product, dict):
        return False
    return all(product.get(field) not in (None, "", []) for field in LOCAL_COMPLETE_FIELDS)


def _slug_match_score(query: str, url: str) -> float:
    """候选 URL 路径与型号 slug 的吻合度：含完整型号的产品页 > 系列 / 新闻页。"""
    query_tokens = {
        token for token in re.findall(r"[a-z0-9]+", _as_text(query).lower()) if len(token) >= 2
    }
    if not query_tokens:
        return 0.0
    path = re.sub(r"^https?://[^/]+", "", _as_text(url).lower())
    path_tokens = set(re.findall(r"[a-z0-9]+", path))
    score = len(query_tokens & path_tokens) / len(query_tokens)
    if any(
        segment in path
        for segment in ("-line", "/series", "/newsroom", "/news", "/blog", "/collections", "/category")
    ):
        score -= 0.3
    return round(score, 3)


def _external_candidates_from_search_results(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    external: List[Dict[str, Any]] = []
    for result in search_results:
        if not isinstance(result, dict):
            continue
        best = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else None
        official_items = result.get("official_candidates")
        review_items = result.get("review_candidates")
        official_items = official_items if isinstance(official_items, list) else []
        review_items = review_items if isinstance(review_items, list) else []
        official = [
            item for item in official_items
            if isinstance(item, dict)
        ][:3]
        review = [
            item for item in review_items
            if isinstance(item, dict)
        ][:3]
        usable_items = result.get("usable_candidates")
        usable_items = usable_items if isinstance(usable_items, list) else []
        # 已通过相关度门控的可消费候选；这里再按"型号 slug 吻合度"重排——
        # 让含完整型号的产品页排在系列 / 新闻页之前，抽取更好抽。
        query_text = _as_text(result.get("query"))
        usable = [item for item in usable_items if isinstance(item, dict)]
        usable.sort(
            key=lambda candidate: (
                _slug_match_score(query_text, _as_text(candidate.get("url"))),
                float(candidate.get("category_relevance") or 0),
                float(candidate.get("confidence_hint") or 0),
            ),
            reverse=True,
        )
        usable = usable[:4]
        usable_count = int(result.get("usable_candidate_count") or 0)
        status = _as_text(result.get("status")) or "pending"
        external.append(
            {
                "original_input": result.get("query"),
                "candidate_status": status,
                "provider": result.get("provider"),
                "executed_query": result.get("executed_query"),
                "best_candidate": best,
                "usable_candidates": usable,
                "official_candidates": official,
                "review_candidates": review,
                "usable_candidate_count": usable_count,
                "rejected_candidate_count": int(result.get("rejected_candidate_count") or 0),
                "needs_llm_disambiguation": bool(result.get("needs_llm_disambiguation")),
                "next_action": result.get("next_action"),
                "note": result.get("note"),
                "consumable_by_next_agent": usable_count > 0,
            }
        )
    return external


def _official_spec_targets(
    resolved: List[Dict[str, Any]],
    external_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build OfficialSpecMCP targets from local products and SearchMCP candidates."""
    targets: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for item in resolved:
        if not isinstance(item, dict):
            continue
        product = item.get("product") if isinstance(item.get("product"), dict) else {}
        # 本地已命中且核心字段完整 → 本地事实即权威，跳过官方抽取
        # （省一次抓取+LLM 调用，并避免本地产品官网被反爬时产生 fetch_failed 噪音）。
        if _has_complete_local_facts(product):
            continue
        url = _as_text(product.get("official_url"))
        if not url or url in seen:
            continue
        seen.add(url)
        targets.append(
            {
                "input": item.get("original_input") or product.get("model"),
                "brand": product.get("brand"),
                "model": product.get("model"),
                "official_url": url,
                "source": "local_product_json",
            }
        )

    for item in external_candidates:
        if not isinstance(item, dict):
            continue
        # 多网站：对每个未命中产品，把 top N 个可消费候选（官方优先，其次高可信
        # 测评站）都作为抽取目标；后续按产品分组、补齐字段、提前停。
        candidates = item.get("usable_candidates")
        candidates = candidates if isinstance(candidates, list) else []
        if not candidates and isinstance(item.get("best_candidate"), dict):
            candidates = [item["best_candidate"]]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            url = _as_text(candidate.get("url"))
            if not url or url in seen:
                continue
            seen.add(url)
            targets.append(
                {
                    "input": item.get("original_input"),
                    "brand": "",
                    "model": item.get("original_input") or candidate.get("title"),
                    "source_title": candidate.get("title"),
                    "official_url": url,
                    "source": "search_mcp_candidate",
                    "source_type": candidate.get("source_type"),
                    "candidate_confidence": candidate.get("confidence_hint"),
                    "candidate_relevance": candidate.get("category_relevance"),
                }
            )

    return targets


def _price_targets(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = _as_text(product.get("id"))
        model = _as_text(product.get("model"))
        key = product_id or model
        if not key or key in seen:
            continue
        seen.add(key)
        source_urls: List[str] = []
        if isinstance(product.get("sources"), list):
            for source in product.get("sources", []):
                if isinstance(source, dict) and _as_text(source.get("url")):
                    source_urls.append(_as_text(source.get("url")))
        if isinstance(product.get("source_urls"), list):
            source_urls.extend(_as_text(url) for url in product.get("source_urls", []) if _as_text(url))
        targets.append(
            {
                "input": model or product_id,
                "product_id": product_id,
                "brand": product.get("brand"),
                "model": model,
                "official_url": product.get("official_url"),
                "source_urls": source_urls,
            }
        )
    return targets


def _review_targets(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = _as_text(product.get("id"))
        model = _as_text(product.get("model"))
        key = product_id or model
        if not key or key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "input": model or product_id,
                "product_id": product_id,
                "brand": product.get("brand"),
                "model": model,
                "official_url": product.get("official_url"),
            }
        )
    return targets


def _append_review_pending(
    state: dict,
    review_status: Dict[str, Any],
    collected_count: int,
    target_count: int,
) -> List[Dict[str, Any]]:
    fully_collected = bool(target_count) and collected_count >= target_count
    pending_dimensions = [
        _as_text(item)
        for item in review_status.get("review_dimensions_pending", [])
        if _as_text(item)
    ] if isinstance(review_status.get("review_dimensions_pending"), list) else []
    low_conf = int(review_status.get("low_confidence_count") or 0) > 0
    if fully_collected and not pending_dimensions:
        return [item for item in state.get("pending_data", []) if isinstance(item, dict)]
    status_label = "partial" if collected_count else (_as_text(review_status.get("status")) or "pending")
    if low_conf:
        status_label = "low_confidence"
    note = _as_text(review_status.get("note")) or "Review/user feedback data is not complete yet."
    if pending_dimensions:
        note = f"{note} Pending dimensions: {', '.join(pending_dimensions)}."
    return _append_pending(
        state,
        _pending_entry(
            "CollectorAgent.review_intel",
            status_label,
            pending_dimensions or list(EXPERIENCE_PENDING_DIMENSIONS),
            note,
        ),
    )


def _official_products_from_records(
    official_records: List[Dict[str, Any]],
    category: str,
) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for result in official_records:
        product = product_from_official_spec(result, category=category)
        if not product:
            continue
        product_id = _as_text(product.get("id"))
        if product_id in seen:
            continue
        seen.add(product_id)
        products.append(product)
    return products


def _product_identity_keys(product: Dict[str, Any]) -> set[str]:
    def norm(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", _as_text(value).lower())

    brand = _as_text(product.get("brand"))
    model = _as_text(product.get("model"))
    keys = {
        norm(product.get("id")),
        norm(model),
        norm(f"{brand} {model}"),
    }
    for key in ("aliases", "community_aliases"):
        values = product.get(key)
        if isinstance(values, list):
            keys.update(norm(item) for item in values)
    return {key for key in keys if key}


def _merge_products_for_compare(
    local_products: List[Dict[str, Any]],
    official_products: List[Dict[str, Any]],
    *,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for product in [*local_products, *official_products]:
        keys = _product_identity_keys(product)
        if keys and seen.intersection(keys):
            continue
        merged.append(product)
        seen.update(keys)
        if len(merged) >= limit:
            break
    return merged


def _official_spec_evidence(
    official_records: List[Dict[str, Any]],
    existing_count: int,
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for index, result in enumerate(official_records, start=existing_count + 1):
        if not isinstance(result, dict) or result.get("status") not in {"collected", "partial_collected"}:
            continue
        record = result.get("record") if isinstance(result.get("record"), dict) else {}
        model = _as_text(record.get("official_model") or result.get("model_hint") or result.get("input"))
        if not model:
            continue
        raw_content = {
            key: record.get(key)
            for key in [
                "brand",
                "official_model",
                "weight_g",
                "dimensions_mm",
                "sensor",
                "dpi_max",
                "polling_rate_hz",
                "connection",
                "battery_hours",
                "switch_type",
                "click_system",
                "software",
                "onboard_memory",
                "mold_id",
                "missing_fields",
            ]
        }
        confidence = 0.9 if result.get("confidence") == "high" else 0.78 if result.get("confidence") == "medium" else 0.62
        evidence.append(
            {
                "evidence_id": f"EV{index:03d}",
                "platform": model,
                "claim": f"{model} official hardware specs extracted from official page.",
                "source_type": "official",
                "source_title": record.get("source_title") or f"{model} official specs",
                "source_url": result.get("source_url") or record.get("official_url") or "",
                "publish_time": "",
                "collected_time": result.get("collected_at") or "",
                "credibility": "high" if result.get("status") == "collected" and result.get("confidence") in {"high", "medium"} else "medium",
                "related_dimension": "official_specs",
                "raw_content": str(raw_content),
                "confidence_score": confidence,
                "dimension": "official_specs",
                "content": str(raw_content),
                "summary": "OfficialSpecMCP extracted structured hardware specs.",
                "source": result.get("source_domain") or "official_page",
                "used_by_agent": "OfficialSpecMCP",
                "data_status": "verified" if result.get("status") == "collected" else "partial_verified",
                "pending_research": False,
                "evidence_gap": result.get("status") != "collected",
            }
        )
    return evidence


def _official_status_from_records(
    base_status: List[Dict[str, Any]],
    official_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not official_records:
        return base_status
    statuses: List[Dict[str, Any]] = []
    for result in official_records:
        if not isinstance(result, dict):
            continue
        record = result.get("record") if isinstance(result.get("record"), dict) else {}
        statuses.append(
            {
                "input": result.get("input"),
                "model": record.get("official_model") or result.get("model_hint"),
                "source_url": result.get("source_url"),
                "source_domain": result.get("source_domain"),
                "status": result.get("status"),
                "mcp_required": result.get("status") != "collected",
                "missing_official_fields": result.get("missing_fields", []),
                "field_confidence": result.get("field_confidence", {}),
                "next_action": "none" if result.get("status") == "collected" else "configure_or_retry_official_spec_mcp",
                "note": result.get("note"),
            }
        )
    return statuses or base_status


def _product_schema(category: str) -> Dict[str, Any]:
    return {
        "category": category,
        "stable_local_fields": [
            "brand",
            "model",
            "weight_g",
            "dimensions_mm",
            "shape",
            "sensor",
            "dpi_max",
            "polling_rate_hz",
            "connection",
            "battery_hours",
            "switch_type",
            "click_system",
            "software",
            "onboard_memory",
            "mold_id",
        ],
        "external_pending_fields": [
            "official_spec_updates",
            "user_reviews",
            "creator_reviews",
            "driver_reputation",
            "realtime_price",
            "long_term_reliability",
        ],
    }


def collector_agent(state: dict) -> Dict[str, Any]:
    """Collect and structure inputs for downstream analysis."""
    started = time.time()
    category = _as_text(state.get("industry_key")) or "gaming_mouse"
    inputs = _selected_inputs(state)

    # Empty-input compatibility flow: keep the DAG observable even without product inputs.
    # when no product inputs were supplied.
    if not inputs:
        next_state = {
            **state,
            "current_agent": "CollectorAgent",
            "knowledge_schema": _product_schema(category),
        }
        _append_trace(
            next_state,
            status="skipped",
            input_summary="no product inputs supplied",
            output_summary="collector skipped; legacy research evidence will be used",
            started_at=started,
        )
        return next_state

    resolved, products, unresolved = _resolve_products(state, category)
    if len(products) < 2:
        search_results = _search_unresolved_products(unresolved, category)
        external_candidates = _external_candidates_from_search_results(search_results)
        found_external_candidates = any(
            item.get("consumable_by_next_agent")
            for item in external_candidates
            if isinstance(item, dict)
        )
        search_statuses = {
            _as_text(item.get("candidate_status"))
            for item in external_candidates
            if isinstance(item, dict)
        }
        pending_data = list(state.get("pending_data", []))
        if unresolved:
            pending_data = _append_pending(
                {**state, "pending_data": pending_data},
                _pending_entry(
                    "CollectorAgent.product_resolution",
                    "pending",
                    unresolved,
                    (
                        "SearchMCP produced consumable external product candidates, but official identity still needs "
                        "LLM/user confirmation before hardware facts are trusted."
                    )
                    if found_external_candidates
                    else (
                        "SearchMCP suspects at least one input is off-category or only found low-confidence candidates; "
                        "user/LLM disambiguation is required before official specs can be collected."
                    )
                    if search_statuses & {"off_category_suspected", "low_confidence_candidates"}
                    else "Local product JSON did not match all inputs; SearchMCP/official-site MCP should identify official models.",
                ),
            )
            pending_data = _append_pending(
                {**state, "pending_data": pending_data},
                _pending_entry(
                    "CollectorAgent.official_spec",
                    "pending",
                    list(OFFICIAL_SPEC_FIELDS),
                    "Official-site MCP is required before hardware comparison or winner claims.",
                ),
            )
        pending_data = _append_pending(
            {**state, "pending_data": pending_data},
            _pending_entry(
                "CollectorAgent.review_intel",
                "mcp_not_connected",
                list(EXPERIENCE_PENDING_DIMENSIONS),
                "User reviews and creator reviews are not collected yet.",
            ),
        )
        pending_data = _append_pending(
            {**state, "pending_data": pending_data},
            _pending_entry(
                "CollectorAgent.price",
                "mcp_not_connected",
                ["realtime_price", "discounts", "regional_availability"],
                "Realtime price is intentionally not read from local JSON.",
            ),
        )
        # 部分命中（例如一款命中、一款未命中）：仍读取已命中产品的本地硬件事实，
        # 不再整体丢弃；未命中的留给 Search / 官网 MCP。只有 0 款命中才走全空路径。
        matched_payload = build_compare_payload(products, category) if products else None
        official_records = collect_official_specs(
            _official_spec_targets(resolved, external_candidates),
            category=category,
        )
        # 同一产品的多来源记录按字段合并补齐：缺的字段从其它高可信来源补上。
        merged_records = merge_official_records(official_records, category=category)
        official_products = _official_products_from_records(merged_records, category)
        combined_products = _merge_products_for_compare(products, official_products, limit=2)
        matched_payload = build_compare_payload(combined_products, category) if combined_products else None
        if matched_payload and merged_records:
            matched_payload["evidence_list"].extend(
                _official_spec_evidence(merged_records, len(matched_payload["evidence_list"]))
            )
        price_records = collect_prices(_price_targets(combined_products), category=category)
        price_status = _price_status(price_records)
        if matched_payload:
            matched_payload["evidence_list"].extend(
                price_records_to_evidence(price_records, len(matched_payload["evidence_list"]))
            )
        review_records = collect_review_intel(_review_targets(combined_products), category=category)
        review_status = _review_intel_status(review_records)
        if matched_payload:
            matched_payload["evidence_list"] = merge_review_records_into_evidence(
                matched_payload["evidence_list"],
                review_records,
            )
        price_collected_count = int(price_status.get("collected_count") or 0)
        price_target_count = int(price_status.get("target_count") or len(price_records) or 0)
        review_collected_count = int(review_status.get("collected_count") or 0)
        review_target_count = int(review_status.get("target_count") or len(review_records) or 0)
        pending_data = [
            item
            for item in pending_data
            if not (
                isinstance(item, dict)
                and item.get("agent") == "CollectorAgent.price"
            )
        ]
        pending_data = _append_price_pending(
            {**state, "pending_data": pending_data}, price_status, price_collected_count, price_target_count
        )
        pending_data = [
            item
            for item in pending_data
            if not (
                isinstance(item, dict)
                and item.get("agent") == "CollectorAgent.review_intel"
            )
        ]
        pending_data = _append_review_pending(
            {**state, "pending_data": pending_data}, review_status, review_collected_count, review_target_count
        )

        if matched_payload:
            matched_official, _matched_missing = _official_spec_status(matched_payload["product_facts"])
            official_status = _official_status_from_records(
                matched_official + _unresolved_official_status(unresolved),
                merged_records,
            )
        else:
            official_status = _official_status_from_records(
                _unresolved_official_status(unresolved),
                merged_records,
            )
        official_usable_count = sum(
            1 for item in merged_records if isinstance(item, dict) and item.get("status") in {"collected", "partial_collected"}
        )
        official_collected_count = sum(
            1 for item in merged_records if isinstance(item, dict) and item.get("status") == "collected"
        )
        effective_unresolved = [] if unresolved and official_usable_count >= len(unresolved) else unresolved
        if unresolved and official_usable_count >= len(unresolved):
            pending_data = [
                item
                for item in pending_data
                if not (
                    isinstance(item, dict)
                    and item.get("agent") == "CollectorAgent.product_resolution"
                )
            ]
        if unresolved and official_collected_count >= len(unresolved):
            pending_data = [
                item
                for item in pending_data
                if not (
                    isinstance(item, dict)
                    and item.get("agent") == "CollectorAgent.official_spec"
                )
            ]
        official_substep_status = (
            "collected"
            if official_collected_count
            else _as_text(merged_records[0].get("status")) if merged_records else "pending"
        )

        next_state = {
            **state,
            "current_agent": "CollectorAgent",
            "product_compare_mode": True,
            "resolved_products": resolved,
            "selected_products": matched_payload["products"] if matched_payload else [],
            "competitors": matched_payload["competitors"] if matched_payload else state.get("competitors", []),
            "unresolved_products": effective_unresolved,
            "search_mcp_results": search_results,
            "external_product_candidates": external_candidates,
            "product_facts": matched_payload["product_facts"] if matched_payload else [],
            "official_spec_records": merged_records,
            "price_records": price_records,
            "review_intel_records": review_records,
            "raw_research": matched_payload["raw_research"] if matched_payload else [],
            "evidence_list": matched_payload["evidence_list"] if matched_payload else [],
            "focus_dimensions": matched_payload["focus_dimensions"] if matched_payload else state.get("focus_dimensions", []),
            "official_spec_status": official_status,
            "review_intel_status": review_status,
            "price_status": price_status,
            "pending_data": pending_data,
            "pending_dimensions": [
                *(["official_model", "hardware_specs"] if effective_unresolved else []),
                *(
                    review_status.get("review_dimensions_pending", [])
                    if isinstance(review_status.get("review_dimensions_pending"), list)
                    else EXPERIENCE_PENDING_DIMENSIONS
                ),
                *(["realtime_price"] if price_collected_count < max(1, price_target_count) else []),
            ],
            "knowledge_schema": _product_schema(category),
            "data_requirements": [
                "search_mcp_pending",
                "official_spec_mcp_pending",
                "review_intel_mcp_pending",
                "price_mcp_pending",
            ],
        }
        append_usage_from_records(next_state, [*merged_records, *price_records, *review_records])
        append_mcp_usage(
            next_state,
            [
                item.get("mcp_usage")
                for item in search_results
                if isinstance(item, dict) and isinstance(item.get("mcp_usage"), dict)
            ],
        )
        _append_trace(
            next_state,
            status="partial",
            input_summary=f"resolved {len(inputs)} product inputs",
            output_summary=(
                f"{len(combined_products)} products resolved, {len(effective_unresolved)} unresolved; "
                f"seeded {len(matched_payload['evidence_list']) if matched_payload else 0} evidence "
                "for matched or official-spec products"
            ),
            started_at=started,
            evidence_added=len(matched_payload["evidence_list"]) if matched_payload else 0,
            pending_fields=[
                *effective_unresolved,
                *(["official_model", "hardware_specs"] if effective_unresolved else []),
                *(
                    review_status.get("review_dimensions_pending", [])
                    if isinstance(review_status.get("review_dimensions_pending"), list)
                    else EXPERIENCE_PENDING_DIMENSIONS
                ),
                *(["realtime_price"] if price_collected_count < max(1, price_target_count) else []),
            ],
            substeps=[
                {"name": "ProductResolver", "status": "partial", "count": len(resolved)},
                {
                    "name": "SearchMCP",
                    "status": (
                        "official_candidate_found"
                        if "official_candidate_found" in search_statuses
                        else "review_candidate_found"
                        if "review_candidate_found" in search_statuses
                        else "low_confidence_candidates"
                        if "low_confidence_candidates" in search_statuses
                        else "off_category_suspected"
                        if "off_category_suspected" in search_statuses
                        else "pending"
                    ),
                    "count": sum(
                        int(item.get("usable_candidate_count", 0) or 0)
                        for item in external_candidates
                        if isinstance(item, dict)
                    ),
                },
                {
                    "name": "ProductFact",
                    "status": "partial" if matched_payload else "pending",
                    "count": len(matched_payload["product_facts"]) if matched_payload else 0,
                },
                {
                    "name": "OfficialSpec",
                    "status": official_substep_status,
                    "count": official_usable_count,
                    "pending_fields": [] if official_collected_count else list(OFFICIAL_SPEC_FIELDS),
                },
                {
                    "name": "ReviewIntel",
                    "status": review_status.get("status") or "pending",
                    "count": review_collected_count,
                    "source_count": review_status.get("source_count", 0),
                },
                {
                    "name": "Price",
                    "status": price_status.get("status") or "pending",
                    "count": price_collected_count,
                    "sample_count": price_status.get("sample_count", 0),
                },
            ],
        )
        return next_state

    payload = build_compare_payload(products[:2], category)
    official_records = collect_official_specs(
        _official_spec_targets(resolved, []),
        category=category,
    )
    if official_records:
        payload["evidence_list"].extend(
            _official_spec_evidence(official_records, len(payload["evidence_list"]))
        )
    price_records = collect_prices(_price_targets(payload["products"]), category=category)
    price_status = _price_status(price_records)
    payload["evidence_list"].extend(
        price_records_to_evidence(price_records, len(payload["evidence_list"]))
    )
    review_records = collect_review_intel(_review_targets(payload["products"]), category=category)
    review_status = _review_intel_status(review_records)
    payload["evidence_list"] = merge_review_records_into_evidence(
        payload["evidence_list"],
        review_records,
    )
    price_collected_count = int(price_status.get("collected_count") or 0)
    price_target_count = int(price_status.get("target_count") or len(price_records) or 0)
    review_collected_count = int(review_status.get("collected_count") or 0)
    review_target_count = int(review_status.get("target_count") or len(review_records) or 0)
    official_status, official_missing = _official_spec_status(payload["product_facts"])
    official_status = _official_status_from_records(official_status, official_records)
    official_collected_count = sum(
        1 for item in official_records if isinstance(item, dict) and item.get("status") == "collected"
    )
    official_usable_count = sum(
        1 for item in official_records if isinstance(item, dict) and item.get("status") in {"collected", "partial_collected"}
    )
    official_substep_status = (
        "collected"
        if official_collected_count
        else _as_text(official_records[0].get("status")) if official_records else "complete"
    )
    pending_data = list(state.get("pending_data", []))
    if official_missing:
        pending_data = _append_pending(
            {**state, "pending_data": pending_data},
            _pending_entry(
                "CollectorAgent.official_spec",
                "pending",
                official_missing,
                "Some official hardware fields still need official-site extraction or confirmation.",
            ),
        )
    pending_data = _append_review_pending(
        {**state, "pending_data": pending_data}, review_status, review_collected_count, review_target_count
    )
    pending_data = _append_price_pending(
        {**state, "pending_data": pending_data}, price_status, price_collected_count, price_target_count
    )

    next_state = {
        **state,
        "current_agent": "CollectorAgent",
        "product_compare_mode": True,
        "resolved_products": resolved,
        "selected_products": payload["products"],
        "competitors": payload["competitors"],
        "unresolved_products": unresolved,
        "search_mcp_results": [],
        "external_product_candidates": [],
        "product_facts": payload["product_facts"],
        "official_spec_records": official_records,
        "price_records": price_records,
        "review_intel_records": review_records,
        "raw_research": payload["raw_research"],
        "evidence_list": payload["evidence_list"],
        "focus_dimensions": payload["focus_dimensions"],
        "pending_dimensions": [
            *payload.get("pending_dimensions", []),
            *(
                review_status.get("review_dimensions_pending", [])
                if isinstance(review_status.get("review_dimensions_pending"), list)
                else EXPERIENCE_PENDING_DIMENSIONS
            ),
            *(["realtime_price"] if price_collected_count < max(1, price_target_count) else []),
        ],
        "official_spec_status": official_status,
        "review_intel_status": review_status,
        "price_status": price_status,
        "pending_data": pending_data,
        "knowledge_schema": _product_schema(category),
            "data_requirements": [
                "local_product_json",
                "official_spec_mcp_pending",
                "review_intel_mcp_pending",
                "price_mcp_pending",
            ],
        }
    append_usage_from_records(next_state, [*official_records, *price_records, *review_records])
    _append_trace(
        next_state,
        status="success",
        input_summary=f"resolved {len(inputs)} product inputs",
        output_summary=(
            f"resolved {len(products[:2])} products, loaded {len(payload['product_facts'])} "
            f"local fact records, seeded {len(payload['evidence_list'])} evidence items"
        ),
        evidence_added=len(payload["evidence_list"]),
        started_at=started,
        pending_fields=[
            *unresolved,
            *official_missing,
            *(
                review_status.get("review_dimensions_pending", [])
                if isinstance(review_status.get("review_dimensions_pending"), list)
                else EXPERIENCE_PENDING_DIMENSIONS
            ),
            *(["realtime_price"] if price_collected_count < max(1, price_target_count) else []),
        ],
        substeps=[
            {"name": "ProductResolver", "status": "success", "count": len(resolved)},
            {"name": "ProductFact", "status": "success", "count": len(payload["product_facts"])},
            {
                "name": "OfficialSpec",
                "status": official_substep_status,
                "count": official_usable_count,
                "pending_fields": official_missing if not official_collected_count else [],
            },
            {
                "name": "ReviewIntel",
                "status": review_status.get("status") or "pending",
                "count": review_collected_count,
                "source_count": review_status.get("source_count", 0),
            },
            {
                "name": "Price",
                "status": price_status.get("status") or "pending",
                "count": price_collected_count,
                "sample_count": price_status.get("sample_count", 0),
            },
        ],
    )
    return next_state
