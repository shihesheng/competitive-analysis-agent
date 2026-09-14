"""Search MCP service for product entity discovery.

This service intentionally uses search APIs instead of scraping search result
pages. The first provider is Tavily. It returns candidate URLs and snippets only;
then applies a conservative category relevance gate. SearchMCP may discover an
official candidate, but it never writes hardware facts by itself. Unknown or
ambiguous products remain pending until a later LLM/user disambiguation and
official-spec extraction step.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60

_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}

OFFICIAL_DOMAIN_HINTS = {
    "logitech": ["logitechg.com", "logitech.com"],
    "razer": ["razer.com"],
    "zowie": ["zowie.benq.com", "benq.com"],
    "corsair": ["corsair.com"],
    "steelseries": ["steelseries.com"],
    "glorious": ["gloriousgaming.com"],
    "pulsar": ["pulsargg.com"],
    "endgame": ["endgamegear.com"],
    "lamzu": ["lamzu.com"],
    "asus": ["rog.asus.com", "asus.com"],
    "vaxee": ["vaxee.co"],
    "finalmouse": ["finalmouse.com"],
    "wlmouse": ["wlmouse.com"],
    "vgn": ["vgnlab.com"],
    "vxe": ["vgnlab.com"],
}

GAMING_MOUSE_CATEGORY_TERMS = {
    "gaming mouse",
    "wireless mouse",
    "mouse",
    "mice",
    "esports mouse",
    "dpi",
    "polling",
    "sensor",
    "ultralight",
    "ultra-light",
    "magnesium",
    "optical switch",
    "mechanical switch",
}

GAMING_MOUSE_OFF_CATEGORY_TERMS = {
    "iphone",
    "ipad",
    "phone",
    "case",
    "controller",
    "keyboard",
    "keycap",
    "monitor",
    "headset",
    "earbuds",
    "laptop",
}

OFFICIAL_OR_REVIEW_SOURCES = {
    "official_candidate",
    "review_candidate",
    "creator_review_candidate",
}


@dataclass(frozen=True)
class SearchConfig:
    provider: str
    api_key: str
    max_results: int
    country: str
    ttl_seconds: int


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env")
    load_dotenv()


def _config() -> SearchConfig:
    _load_env()
    return SearchConfig(
        provider=os.getenv("SEARCH_PROVIDER", "disabled").strip().lower() or "disabled",
        api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        max_results=max(1, min(_env_int("SEARCH_MAX_RESULTS", 6), 10)),
        country=os.getenv("SEARCH_COUNTRY", "united states").strip(),
        ttl_seconds=max(60, _env_int("SEARCH_CACHE_TTL_SECONDS", DEFAULT_TTL_SECONDS)),
    )


def _cache_key(config: SearchConfig, query: str, category: str, intent: str) -> str:
    return "|".join([config.provider, query.strip().lower(), category, intent, str(config.max_results), config.country])


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _executed_query(query: str, category: str, intent: str) -> str:
    clean = query.strip()
    if category == "gaming_mouse":
        if intent == "price_collection":
            return f'"{clean}" gaming mouse price buy official store'
        if intent == "product_entity_resolution":
            return f'"{clean}" gaming mouse official product'
        return f'"{clean}" gaming mouse review official'
    return clean


def _source_type(title: str, url: str) -> str:
    text = f"{title} {_domain(url)}".lower()
    if "official" in text:
        return "official_candidate"
    for brand, domains in OFFICIAL_DOMAIN_HINTS.items():
        if brand in text and any(domain in text for domain in domains):
            return "official_candidate"
    if any(domain in text for domains in OFFICIAL_DOMAIN_HINTS.values() for domain in domains):
        return "official_candidate"
    if "youtube.com" in text or "youtu.be" in text or "bilibili.com" in text:
        return "creator_review_candidate"
    if "rtings.com" in text or "techpowerup.com" in text or "eloshapes.com" in text:
        return "review_candidate"
    if "amazon.com" in text or "maxgaming.com" in text or "jd.com" in text or "taobao.com" in text:
        return "ecommerce_candidate"
    return "search_result"


def _confidence_hint(title: str, url: str, content: str, score: Any, source_type: str) -> float:
    base = float(score) if isinstance(score, (int, float)) else 0.35
    bonus = 0.0
    if source_type == "official_candidate":
        bonus += 0.18
    if "gaming mouse" in f"{title} {content}".lower():
        bonus += 0.05
    return round(max(0.0, min(1.0, base + bonus)), 3)


def _candidate_from_tavily(result: Dict[str, Any]) -> Dict[str, Any]:
    title = str(result.get("title") or "").strip()
    url = str(result.get("url") or "").strip()
    content = str(result.get("content") or "").strip()
    source_type = _source_type(title, url)
    return {
        "title": title,
        "url": url,
        "domain": _domain(url),
        "snippet": content,
        "source_type": source_type,
        "provider_score": result.get("score"),
        "confidence_hint": _confidence_hint(title, url, content, result.get("score"), source_type),
    }


def _text_blob(candidate: Dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "url", "domain", "snippet")
    ).lower()


def _known_brand_hit(text: str) -> bool:
    return any(brand in text for brand in OFFICIAL_DOMAIN_HINTS)


def _mouse_term_score(candidate: Dict[str, Any]) -> float:
    title_url_domain = " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "url", "domain")
    ).lower()
    snippet = str(candidate.get("snippet") or "").lower()
    score = 0.0
    if any(term in title_url_domain for term in GAMING_MOUSE_CATEGORY_TERMS):
        score += 0.32
    if any(term in snippet for term in GAMING_MOUSE_CATEGORY_TERMS):
        score += 0.12
    return score


def _off_category_hit(candidate: Dict[str, Any]) -> bool:
    title_url_domain = " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "url", "domain")
    ).lower()
    return any(term in title_url_domain for term in GAMING_MOUSE_OFF_CATEGORY_TERMS)


def _category_relevance(candidate: Dict[str, Any], category: str) -> float:
    if category != "gaming_mouse":
        return float(candidate.get("confidence_hint") or 0)

    text = _text_blob(candidate)
    source_type = str(candidate.get("source_type") or "")
    relevance = 0.0
    if source_type == "official_candidate":
        relevance += 0.42
    elif source_type in {"review_candidate", "creator_review_candidate"}:
        relevance += 0.26
    elif source_type == "ecommerce_candidate":
        relevance += 0.14
    if _known_brand_hit(text):
        relevance += 0.12
    relevance += _mouse_term_score(candidate)
    if _off_category_hit(candidate) and _mouse_term_score(candidate) == 0:
        relevance -= 0.45
    return round(max(0.0, min(1.0, relevance)), 3)


def _classify_search_candidates(
    query: str,
    category: str,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify raw search results into consumable entity candidates.

    Raw results are still returned for UI transparency, but only candidates
    passing this gate should be consumed by CollectorAgent.
    """
    annotated: List[Dict[str, Any]] = []
    for candidate in candidates:
        relevance = _category_relevance(candidate, category)
        confidence = float(candidate.get("confidence_hint") or 0)
        source_type = str(candidate.get("source_type") or "")
        usable = (
            source_type in OFFICIAL_OR_REVIEW_SOURCES
            and relevance >= 0.46
            and confidence >= 0.5
        ) or (
            source_type == "ecommerce_candidate"
            and relevance >= 0.5
            and confidence >= 0.62
        )
        annotated.append(
            {
                **candidate,
                "category_relevance": relevance,
                "candidate_usable": usable,
            }
        )

    annotated.sort(
        key=lambda item: (
            1 if item.get("candidate_usable") else 0,
            float(item.get("category_relevance") or 0),
            float(item.get("confidence_hint") or 0),
        ),
        reverse=True,
    )
    usable_candidates = [item for item in annotated if item.get("candidate_usable")]
    official_candidates = [
        item for item in usable_candidates if item.get("source_type") == "official_candidate"
    ]
    review_candidates = [
        item
        for item in usable_candidates
        if item.get("source_type") in {"review_candidate", "creator_review_candidate"}
    ]

    if official_candidates:
        candidate_status = "official_candidate_found"
        next_action = "confirm_entity_then_official_spec_mcp"
    elif review_candidates:
        candidate_status = "review_candidate_found"
        next_action = "llm_disambiguation_then_official_spec_mcp"
    elif annotated:
        max_relevance = max(float(item.get("category_relevance") or 0) for item in annotated)
        off_category_count = sum(1 for item in annotated if _off_category_hit(item))
        if off_category_count >= max(1, len(annotated) // 2) or max_relevance < 0.28:
            candidate_status = "off_category_suspected"
            next_action = "ask_user_to_confirm_category_or_refine_query"
        else:
            candidate_status = "low_confidence_candidates"
            next_action = "llm_disambiguation_or_search_query_refinement"
    else:
        candidate_status = "no_candidates"
        next_action = "search_query_refinement"

    return {
        "status": candidate_status,
        "candidates": annotated,
        "usable_candidates": usable_candidates,
        "official_candidates": official_candidates,
        "review_candidates": review_candidates,
        "best_candidate": usable_candidates[0] if usable_candidates else None,
        "candidate_count": len(annotated),
        "usable_candidate_count": len(usable_candidates),
        "rejected_candidate_count": len(annotated) - len(usable_candidates),
        "needs_llm_disambiguation": bool(usable_candidates),
        "next_action": next_action,
        "note": _classification_note(candidate_status, query),
    }


def _classification_note(status: str, query: str) -> str:
    if status == "official_candidate_found":
        return "SearchMCP found an official-looking product candidate; hardware facts still require entity confirmation and official-spec extraction."
    if status == "review_candidate_found":
        return "SearchMCP found review candidates but no official candidate; entity confirmation is required before trusting facts."
    if status == "low_confidence_candidates":
        return "SearchMCP found low-confidence candidates only; do not use them as product facts without LLM/user disambiguation."
    if status == "off_category_suspected":
        return f"SearchMCP suspects '{query}' is outside the gaming_mouse category or too ambiguous."
    return "SearchMCP did not find usable product candidates."


def _tavily_search(config: SearchConfig, query: str, category: str, intent: str) -> Dict[str, Any]:
    executed_query = _executed_query(query, category, intent)
    body: Dict[str, Any] = {
        "query": executed_query,
        "search_depth": "basic",
        "topic": "general",
        "max_results": config.max_results,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_favicon": True,
    }
    if config.country:
        body["country"] = config.country

    request = Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    started = time.time()
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latency_ms = int((time.time() - started) * 1000)

    raw_candidates = [
        _candidate_from_tavily(item)
        for item in payload.get("results", [])
        if isinstance(item, dict) and item.get("url")
    ]
    classified = _classify_search_candidates(query, category, raw_candidates)

    return {
        "status": classified["status"],
        "provider": "tavily",
        "query": query,
        "executed_query": executed_query,
        "category": category,
        "intent": intent,
        "candidates": classified["candidates"],
        "candidate_count": classified["candidate_count"],
        "usable_candidates": classified["usable_candidates"],
        "official_candidates": classified["official_candidates"],
        "review_candidates": classified["review_candidates"],
        "best_candidate": classified["best_candidate"],
        "usable_candidate_count": classified["usable_candidate_count"],
        "rejected_candidate_count": classified["rejected_candidate_count"],
        "needs_llm_disambiguation": classified["needs_llm_disambiguation"],
        "next_action": classified["next_action"],
        "note": classified["note"],
        "latency_ms": latency_ms,
        "request_id": payload.get("request_id"),
    }


def search_candidates(
    query: str,
    *,
    category: str = "gaming_mouse",
    intent: str = "product_entity_resolution",
) -> Dict[str, Any]:
    """Return search candidates for an unresolved product query.

    The service is disabled unless SEARCH_PROVIDER=tavily and TAVILY_API_KEY is
    present. Disabled or misconfigured states are explicit so the DAG can show
    pending data without treating it as a failure.
    """
    query = str(query or "").strip()
    if not query:
        return {
            "status": "empty_query",
            "provider": "disabled",
            "query": query,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
        }

    config = _config()
    if config.provider in {"", "disabled", "none", "off"}:
        return {
            "status": "mcp_not_connected",
            "provider": "disabled",
            "query": query,
            "category": category,
            "intent": intent,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
            "note": "Set SEARCH_PROVIDER=tavily and TAVILY_API_KEY to enable SearchMCP.",
        }

    if config.provider != "tavily":
        return {
            "status": "unsupported_provider",
            "provider": config.provider,
            "query": query,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
            "note": "Only Tavily is implemented for SearchMCP MVP.",
        }

    if not config.api_key:
        return {
            "status": "mcp_not_configured",
            "provider": "tavily",
            "query": query,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
            "note": "TAVILY_API_KEY is missing.",
        }

    key = _cache_key(config, query, category, intent)
    cached = _CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] <= config.ttl_seconds:
        return {**cached[1], "cache_hit": True}

    try:
        result = _tavily_search(config, query, category, intent)
    except HTTPError as exc:
        result = {
            "status": "rate_limited" if exc.code == 429 else "mcp_http_error",
            "provider": "tavily",
            "query": query,
            "category": category,
            "intent": intent,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
            "http_status": exc.code,
            "note": "SearchMCP request failed; no external candidates were trusted.",
        }
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        result = {
            "status": "mcp_error",
            "provider": "tavily",
            "query": query,
            "category": category,
            "intent": intent,
            "candidates": [],
            "candidate_count": 0,
            "needs_llm_disambiguation": False,
            "note": f"SearchMCP unavailable: {type(exc).__name__}",
        }

    _CACHE[key] = (now, result)
    return result
