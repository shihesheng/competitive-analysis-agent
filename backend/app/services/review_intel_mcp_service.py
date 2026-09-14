"""ReviewIntel MCP service for user/creator review signals.

This service is intentionally narrower than SearchMCP and OfficialSpecMCP:

- SearchMCP discovers candidate pages and snippets.
- ReviewIntelMCP turns review/community/creator text into structured experience
  signals with evidence IDs.
- It never overwrites hardware facts and never makes the final purchase decision.

The service degrades to explicit pending/partial records when search, page fetch,
or LLM extraction is unavailable.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from app.services.observability_service import make_llm_usage_record, make_mcp_usage_record
from app.services.search_mcp_service import search_candidates


DEFAULT_MAX_REVIEW_SOURCES = 5
DEFAULT_MAX_PAGE_CHARS = 16000
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_READER_BASE = "https://r.jina.ai/"
DEFAULT_READER_TIMEOUT_SECONDS = 20
# 一次喂给 LLM 的单源正文上限：取关键词最相关的片段，既压缩长转写又提高信号密度。
DEFAULT_PER_SOURCE_CHARS = 6000
MIN_USEFUL_TEXT_CHARS = 400
# 直连正文低于这个长度通常是 JS 外壳 / 导航占位，触发 reader 兜底拿全文。
RICH_TEXT_CHARS = 2500
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "review_intel"
# 本地评价数据库（database 路线）：命中的产品直接读结构化结论，不走爬虫。
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCAL_REVIEW_DB_PATHS = (
    _REPO_ROOT / "data" / "products" / "gaming_mice_reviews.json",
    Path(__file__).resolve().parents[2] / "data" / "products" / "gaming_mice_reviews.json",
)

# 评测正文里和体验维度强相关的关键词，用于长文本的相关段落抽取（map 前的预筛）。
REVIEW_KEYWORDS = (
    "grip",
    "claw",
    "palm",
    "fingertip",
    "shape",
    "comfort",
    "hand",
    "ergonom",
    "fps",
    "valorant",
    "aim",
    "competitive",
    "driver",
    "software",
    "synapse",
    "g hub",
    "ghub",
    "firmware",
    "durability",
    "reliability",
    "double click",
    "build quality",
    "coating",
    "feet",
    "shell",
    "creak",
    "battery",
    "wireless",
    "review",
    "verdict",
    "pros",
    "cons",
    "recommend",
)

REVIEW_DIMENSIONS = [
    "grip_feel",
    "hand_size_fit",
    "game_type_fit",
    "driver_reputation",
    "long_term_reliability",
    "community_sentiment",
    "build_quality",
]

DIMENSION_TO_PENDING_LABEL = {
    "community_sentiment": "用户口碑",
    "grip_feel": "博主测评",
    "hand_size_fit": "博主测评",
    "game_type_fit": "博主测评",
    "driver_reputation": "驱动长期口碑",
    "long_term_reliability": "长期可靠性",
    "build_quality": "长期可靠性",
}

PENDING_LABEL_TO_DIMENSIONS = {
    "用户口碑": {"community_sentiment", "build_quality"},
    "博主测评": {"grip_feel", "hand_size_fit", "game_type_fit"},
    "驱动长期口碑": {"driver_reputation"},
    "长期可靠性": {"long_term_reliability", "build_quality"},
}


@dataclass(frozen=True)
class ReviewIntelConfig:
    enabled: bool
    search_enabled: bool
    require_llm: bool
    allow_rule_fallback: bool
    api_key: str
    model: str
    base_url: str
    max_sources: int
    max_chars: int
    timeout_seconds: int
    reader_enabled: bool
    reader_base: str
    reader_timeout: int
    reader_api_key: str
    cache_enabled: bool
    per_source_chars: int
    llm_timeout: int
    local_db_enabled: bool


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env")
    load_dotenv()


def _env_bool(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 100000) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(int(raw), maximum))
    except ValueError:
        return default


def _config() -> ReviewIntelConfig:
    _load_env()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    api_key = (
        os.getenv("REVIEW_INTEL_API_KEY", "").strip()
        or deepseek_key
        or os.getenv("ARK_API_KEY", "").strip()
    )
    model = (
        os.getenv("REVIEW_INTEL_MODEL", "").strip()
        or os.getenv("DEEPSEEK_MODEL", "").strip()
        or ("deepseek-chat" if deepseek_key else "")
        or os.getenv("ARK_EP", "").strip()
        or os.getenv("ARK_MODEL", "").strip()
    )
    base_url = (
        os.getenv("REVIEW_INTEL_BASE_URL", "").strip()
        or os.getenv("DEEPSEEK_BASE_URL", "").strip()
        or ("https://api.deepseek.com" if deepseek_key else "")
        or os.getenv("ARK_BASE_URL", "").strip()
        or "https://ark.cn-beijing.volces.com/api/v3"
    )
    default_enabled = "1" if api_key and model else "0"
    reader_base = (os.getenv("REVIEW_INTEL_READER_BASE", "").strip() or DEFAULT_READER_BASE)
    if not reader_base.endswith("/"):
        reader_base += "/"
    reader_api_key = (
        os.getenv("REVIEW_INTEL_READER_API_KEY", "").strip()
        or os.getenv("JINA_API_KEY", "").strip()
    )
    return ReviewIntelConfig(
        enabled=_env_bool("REVIEW_INTEL_MCP_ENABLED", os.getenv("REVIEW_INTEL_USE_LLM", default_enabled)),
        search_enabled=_env_bool("REVIEW_INTEL_SEARCH_ENABLED", "1"),
        require_llm=_env_bool("REVIEW_INTEL_REQUIRE_LLM", "1"),
        allow_rule_fallback=_env_bool("REVIEW_INTEL_ALLOW_RULE_FALLBACK", "0"),
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_sources=_env_int("REVIEW_INTEL_MAX_SOURCES", DEFAULT_MAX_REVIEW_SOURCES, minimum=1, maximum=10),
        max_chars=_env_int("REVIEW_INTEL_MAX_CHARS", DEFAULT_MAX_PAGE_CHARS, minimum=2000, maximum=40000),
        timeout_seconds=_env_int("REVIEW_INTEL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=3, maximum=40),
        reader_enabled=_env_bool("REVIEW_INTEL_READER_ENABLED", "1"),
        reader_base=reader_base,
        reader_timeout=_env_int("REVIEW_INTEL_READER_TIMEOUT_SECONDS", DEFAULT_READER_TIMEOUT_SECONDS, minimum=5, maximum=60),
        reader_api_key=reader_api_key,
        cache_enabled=_env_bool("REVIEW_INTEL_CACHE_ENABLED", "1"),
        per_source_chars=_env_int("REVIEW_INTEL_PER_SOURCE_CHARS", DEFAULT_PER_SOURCE_CHARS, minimum=1500, maximum=20000),
        llm_timeout=_env_int("REVIEW_INTEL_LLM_TIMEOUT_SECONDS", 90, minimum=20, maximum=240),
        local_db_enabled=_env_bool("REVIEW_INTEL_LOCAL_DB_ENABLED", "1"),
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _html_to_text(markup: str, max_chars: int) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", markup)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_chars]


def _fetch_page_text(url: str, timeout_seconds: int, max_chars: int) -> Dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CompetitiveAnalysisAgent/1.0; +https://localhost)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    started = time.time()
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        encoding = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(encoding, errors="replace")
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        text = _html_to_text(text, max_chars)
    else:
        text = text[:max_chars]
    return {
        "url": url,
        "domain": _domain(url),
        "text": text,
        "latency_ms": int((time.time() - started) * 1000),
    }


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{digest}.txt"


def _cache_get(url: str, config: ReviewIntelConfig) -> str:
    if not config.cache_enabled:
        return ""
    path = _cache_path(url)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return ""


def _cache_put(url: str, text: str, config: ReviewIntelConfig) -> None:
    if not config.cache_enabled or not _as_text(text):
        return
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(text, encoding="utf-8")
    except OSError:
        return


def _fetch_via_reader(url: str, config: ReviewIntelConfig) -> str:
    """Use a reader proxy (Jina Reader by default) to bypass anti-bot / JS rendering.

    Works for review sites, community pages, e-commerce reviews, and even returns
    transcript/description text for YouTube/Bilibili video pages.
    """
    if not config.reader_enabled:
        return ""
    reader_url = config.reader_base + url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CompetitiveAnalysisAgent/1.0; +https://localhost)",
        "Accept": "text/plain, text/markdown, */*",
        "X-Return-Format": "text",
    }
    if config.reader_api_key:
        headers["Authorization"] = f"Bearer {config.reader_api_key}"
    request = Request(reader_url, headers=headers, method="GET")
    with urlopen(request, timeout=config.reader_timeout) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(encoding, errors="replace")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[: config.max_chars]


def _fetch_reddit_json(url: str, config: ReviewIntelConfig) -> str:
    """Reddit threads expose structured JSON by appending `.json` — no API key needed."""
    json_url = re.sub(r"/?$", ".json", url.split("?")[0])
    request = Request(
        json_url,
        headers={"User-Agent": "CompetitiveAnalysisAgent/1.0 (review-intel)"},
        method="GET",
    )
    with urlopen(request, timeout=config.timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    texts: List[str] = []

    def _walk(node: Any) -> None:
        if len(" ".join(texts)) > config.max_chars:
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            data = node.get("data") if isinstance(node.get("data"), dict) else node
            for key in ("title", "selftext", "body"):
                value = _as_text(data.get(key))
                if value and value not in {"[removed]", "[deleted]"}:
                    texts.append(value)
            for key in ("children", "replies"):
                if data.get(key):
                    _walk(data.get(key))

    _walk(payload)
    return "\n".join(texts)[: config.max_chars].strip()


def _fetch_readable(url: str, source_kind: str, config: ReviewIntelConfig) -> Dict[str, Any]:
    """Best-effort full-text fetch for ANY source kind.

    Strategy: cache -> source-specific direct fetch -> reader proxy fallback.
    Returns the longest text obtained plus the method used.
    """
    cached = _cache_get(url, config)
    if cached and len(cached) >= MIN_USEFUL_TEXT_CHARS:
        return {"text": cached, "method": "cache", "error": ""}

    domain = _domain(url)
    best_text = ""
    method = ""
    error = ""

    # 1) Reddit -> structured JSON (no key, rarely blocked).
    if "reddit.com" in domain:
        try:
            reddit_text = _fetch_reddit_json(url, config)
            if len(reddit_text) > len(best_text):
                best_text, method = reddit_text, "reddit_json"
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            error = type(exc).__name__

    # 2) Plain article/review pages -> direct HTML fetch is cheapest.
    direct_friendly = source_kind in {"review_site", "search_result", "community_review"}
    if direct_friendly and len(best_text) < MIN_USEFUL_TEXT_CHARS:
        try:
            page = _fetch_page_text(url, config.timeout_seconds, config.max_chars)
            page_text = _as_text(page.get("text"))
            if len(page_text) > len(best_text):
                best_text, method = page_text, "direct"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            error = type(exc).__name__

    # 3) Reader proxy fallback — bypasses anti-bot/JS and reads video transcripts.
    # Also kicks in when direct text is too thin (JS shell / nav-only page).
    needs_reader = len(best_text) < RICH_TEXT_CHARS or source_kind in {
        "creator_review",
        "ecommerce_review",
    }
    if needs_reader and config.reader_enabled:
        try:
            reader_text = _fetch_via_reader(url, config)
            if len(reader_text) > len(best_text):
                best_text, method = reader_text, "reader"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            error = error or type(exc).__name__

    # Only cache substantive content: a rich page, or any reader/reddit-json result.
    # Thin direct shells are not cached, so the reader is retried next run.
    if best_text and (len(best_text) >= RICH_TEXT_CHARS or method in {"reader", "reddit_json"}):
        _cache_put(url, best_text, config)
    return {"text": best_text, "method": method, "error": error}


def _relevant_excerpt(text: str, max_len: int) -> str:
    """Keep the review-relevant paragraphs of long content (transcripts/articles).

    Cheap, LLM-free pre-filter: score paragraphs by review keyword density and keep
    the densest ones until the budget is filled. This both avoids LLM timeouts on long
    transcripts and raises the signal density the extractor sees.
    """
    clean = _as_text(text)
    if len(clean) <= max_len:
        return clean
    blocks = [block.strip() for block in re.split(r"\n{2,}|(?<=[.!?。！？])\s{2,}", clean) if block.strip()]
    if not blocks:
        return clean[:max_len]
    scored: List[tuple[int, int, str]] = []
    for index, block in enumerate(blocks):
        lowered = block.lower()
        score = sum(lowered.count(keyword) for keyword in REVIEW_KEYWORDS)
        scored.append((score, index, block))
    # Always keep the opening block (usually title/verdict), then add by keyword score.
    ordered = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)
    picked: Dict[int, str] = {0: blocks[0]}
    total = len(blocks[0])
    for score, index, block in ordered:
        if score <= 0 or index in picked:
            continue
        if total + len(block) > max_len:
            continue
        picked[index] = block
        total += len(block)
    excerpt = "\n\n".join(picked[index] for index in sorted(picked))
    return excerpt[:max_len] if excerpt else clean[:max_len]


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _balanced_json_candidates(text: str) -> Iterable[str]:
    stack: List[str] = []
    start = -1
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            if not stack:
                start = index
            stack.append(char)
        elif char in "}]":
            if not stack:
                continue
            opener = stack.pop()
            if (opener, char) not in {("{", "}"), ("[", "]")}:
                stack.clear()
                start = -1
                continue
            if not stack and start >= 0:
                yield text[start : index + 1]
                start = -1


def _parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = _strip_json_fence(text)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    for candidate in _balanced_json_candidates(cleaned):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return {}


def _response_to_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(_as_text(item.get("text") or item.get("content")))
            else:
                parts.append(_as_text(item))
        return "\n".join(part for part in parts if part)
    return _as_text(content)


def _get_llm(config: ReviewIntelConfig) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0,
        timeout=config.llm_timeout,
        max_retries=1,
    )


def _source_kind(candidate: Dict[str, Any]) -> str:
    source_type = _as_text(candidate.get("source_type")).lower()
    domain = _as_text(candidate.get("domain") or _domain(_as_text(candidate.get("url")))).lower()
    if source_type == "creator_review_candidate" or "youtube" in domain or "bilibili" in domain:
        return "creator_review"
    if any(item in domain for item in ("reddit", "nga", "tieba", "chiphell", "zhihu")):
        return "community_review"
    if source_type == "ecommerce_candidate" or any(item in domain for item in ("amazon", "jd.", "taobao", "tmall")):
        return "ecommerce_review"
    if source_type == "review_candidate" or any(item in domain for item in ("rtings", "techpowerup", "eloshapes", "tomshardware")):
        return "review_site"
    return "search_result"


def _source_rank(source_kind: str) -> int:
    return {
        "review_site": 4,
        "creator_review": 3,
        "community_review": 2,
        "ecommerce_review": 2,
        "search_result": 1,
    }.get(source_kind, 0)


def _dedupe_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for source in sources:
        url = _as_text(source.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(source)
    deduped.sort(
        key=lambda item: (
            _source_rank(_as_text(item.get("source_kind"))),
            float(item.get("confidence_hint") or 0),
        ),
        reverse=True,
    )
    return deduped


def _review_search_query(target: Dict[str, Any]) -> str:
    model = _as_text(target.get("model") or target.get("input"))
    brand = _as_text(target.get("brand"))
    return " ".join(part for part in (brand, model) if part).strip() or model


def _source_docs(target: Dict[str, Any], config: ReviewIntelConfig) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    docs: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    search_result: Dict[str, Any] = {}
    if not config.search_enabled:
        return docs, search_result, blocked

    query = _review_search_query(target)
    if not query:
        return docs, search_result, blocked

    search_started = time.perf_counter()
    search_result = search_candidates(query, category="gaming_mouse", intent="review_collection")
    search_result["mcp_usage"] = make_mcp_usage_record(
        agent="CollectorAgent",
        tool="search_mcp",
        status=_as_text(search_result.get("status")) or "success",
        started_at=search_started,
        provider=_as_text(search_result.get("provider")) or "search",
        query=_as_text(search_result.get("executed_query") or search_result.get("_executed_query") or query),
        result_count=len(search_result.get("candidates") if isinstance(search_result.get("candidates"), list) else []),
        uses_llm=False,
        metadata={"intent": "review_collection", "input": query},
    )
    raw_candidates: List[Dict[str, Any]] = []
    for key in ("review_candidates", "usable_candidates", "candidates"):
        values = search_result.get(key)
        if isinstance(values, list):
            raw_candidates.extend(item for item in values if isinstance(item, dict))

    sources = []
    for candidate in raw_candidates:
        url = _as_text(candidate.get("url"))
        snippet = " ".join(
            _as_text(candidate.get(key))
            for key in ("title", "snippet", "url", "domain")
            if _as_text(candidate.get(key))
        )
        if not url or not snippet:
            continue
        source_kind = _source_kind(candidate)
        sources.append(
            {
                "url": url,
                "domain": _as_text(candidate.get("domain") or _domain(url)),
                "title": _as_text(candidate.get("title")),
                "text": snippet,
                "source_kind": source_kind,
                "confidence_hint": candidate.get("confidence_hint"),
                "category_relevance": candidate.get("category_relevance"),
                "source_type": candidate.get("source_type"),
            }
        )

    for source in _dedupe_sources(sources)[: config.max_sources]:
        url = _as_text(source.get("url"))
        source_kind = _as_text(source.get("source_kind")) or "search_result"
        # Fetch real body text for EVERY source kind (video/community/ecommerce
        # included) via cache -> direct -> reader proxy. The search snippet is only
        # the floor; the reader fallback bypasses anti-bot/JS and reads transcripts.
        snippet = _as_text(source.get("text"))
        result = _fetch_readable(url, source_kind, config)
        text = _as_text(result.get("text"))
        if len(text) > len(snippet):
            source = {
                **source,
                "text": text,
                "fetch_method": result.get("method"),
            }
        else:
            source = {**source, "fetch_method": result.get("method") or "snippet_only"}
            if result.get("error") and len(snippet) < MIN_USEFUL_TEXT_CHARS:
                blocked.append(
                    {"url": url, "domain": _domain(url), "reason": result.get("error")}
                )
        docs.append(source)
    return docs, search_result, blocked


def _prompt(target: Dict[str, Any], docs: List[Dict[str, Any]], per_source_chars: int = DEFAULT_PER_SOURCE_CHARS) -> str:
    model = _as_text(target.get("model") or target.get("input"))
    brand = _as_text(target.get("brand"))
    source_text = []
    for index, doc in enumerate(docs, start=1):
        excerpt = _relevant_excerpt(_as_text(doc.get("text")), per_source_chars)
        source_text.append(
            "\n".join(
                [
                    f"[S{index}] title: {_as_text(doc.get('title'))}",
                    f"[S{index}] url: {_as_text(doc.get('url'))}",
                    f"[S{index}] source_kind: {_as_text(doc.get('source_kind'))}",
                    f"[S{index}] text: {excerpt}",
                ]
            )
        )
    return f"""
You are ReviewIntelMCP for a gaming mouse competitive-analysis agent system.
Extract only review-backed experience signals from the provided review/search sources.

Rules:
- Return JSON only. No Markdown.
- Do not invent grip, hand-size, game-fit, driver, or reliability claims.
- If a signal is not supported by the provided sources, omit it or mark confidence="low" with an explicit limitation.
- Do not extract hardware specs or prices here.
- Every signal must cite source_ids from the provided [S#] blocks.
- Summaries, fit_recommendations, common_complaints, and limitations must be written in Simplified Chinese.
- Keep Chinese summaries concise and suitable for a professional competitive-analysis report.

Target product:
brand: {brand}
model: {model}

Allowed dimensions:
grip_feel, hand_size_fit, game_type_fit, driver_reputation, long_term_reliability, community_sentiment, build_quality

Required JSON shape:
{{
  "status": "collected" | "partial_collected" | "insufficient_evidence",
  "signals": [
    {{
      "dimension": "grip_feel",
      "summary": "short evidence-backed summary",
      "sentiment": "positive" | "mixed" | "negative" | "unknown",
      "confidence": "high" | "medium" | "low",
      "support_level": "strong" | "medium" | "weak",
      "source_ids": ["S1"],
      "evidence_snippets": ["short quote/paraphrase from source"]
    }}
  ],
  "fit_recommendations": [
    {{
      "scenario": "FPS / claw grip / large hand / driver-sensitive users / long-term reliability",
      "summary": "who this product seems suitable or risky for",
      "confidence": "high" | "medium" | "low",
      "source_ids": ["S1"]
    }}
  ],
  "common_complaints": ["complaint with source-backed wording"],
  "limitations": ["what is missing or weak"]
}}

Sources:
{"\n\n".join(source_text)}
""".strip()


def _normalize_dimension(value: Any) -> str:
    key = re.sub(r"[^a-z_]+", "", _as_text(value).lower().replace("-", "_").replace(" ", "_"))
    aliases = {
        "grip": "grip_feel",
        "gripstyle": "grip_feel",
        "grip_style": "grip_feel",
        "hand_size": "hand_size_fit",
        "handsize": "hand_size_fit",
        "game_fit": "game_type_fit",
        "game": "game_type_fit",
        "driver": "driver_reputation",
        "software": "driver_reputation",
        "reliability": "long_term_reliability",
        "sentiment": "community_sentiment",
        "community": "community_sentiment",
        "build": "build_quality",
        "quality": "build_quality",
    }
    return aliases.get(key, key if key in REVIEW_DIMENSIONS else "")


def _source_lookup(docs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {f"S{index}": doc for index, doc in enumerate(docs, start=1)}


def _record_confidence(signals: List[Dict[str, Any]]) -> str:
    if not signals:
        return "none"
    ranks = {"high": 3, "medium": 2, "low": 1}
    best = max(ranks.get(_as_text(item.get("confidence")), 0) for item in signals)
    return {3: "high", 2: "medium"}.get(best, "low")


def _normalize_signal(raw: Dict[str, Any], docs_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    dimension = _normalize_dimension(raw.get("dimension"))
    summary = _as_text(raw.get("summary"))
    if not dimension or not summary:
        return None
    source_ids = [
        _as_text(item)
        for item in raw.get("source_ids", [])
        if _as_text(item) in docs_by_id
    ] if isinstance(raw.get("source_ids"), list) else []
    if not source_ids:
        return None
    source_urls = [_as_text(docs_by_id[source_id].get("url")) for source_id in source_ids]
    source_kinds = [_as_text(docs_by_id[source_id].get("source_kind")) for source_id in source_ids]
    confidence = _as_text(raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium" if any(kind in {"review_site", "creator_review"} for kind in source_kinds) else "low"
    support_level = _as_text(raw.get("support_level")).lower()
    if support_level not in {"strong", "medium", "weak"}:
        support_level = "strong" if confidence == "high" else "medium" if confidence == "medium" else "weak"
    sentiment = _as_text(raw.get("sentiment")).lower()
    if sentiment not in {"positive", "mixed", "negative", "unknown"}:
        sentiment = "unknown"
    snippets = [
        _as_text(item)[:280]
        for item in raw.get("evidence_snippets", [])
        if _as_text(item)
    ] if isinstance(raw.get("evidence_snippets"), list) else []
    return {
        "dimension": dimension,
        "summary": summary[:500],
        "sentiment": sentiment,
        "confidence": confidence,
        "support_level": support_level,
        "source_ids": source_ids,
        "source_urls": source_urls,
        "source_kinds": source_kinds,
        "evidence_snippets": snippets[:3],
    }


def _rule_extract_signals(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    docs_by_id = _source_lookup(docs)
    keyword_map = {
        "grip_feel": ["grip", "claw", "palm", "fingertip", "shape", "comfort"],
        "hand_size_fit": ["hand size", "small hands", "large hands", "medium hands"],
        "game_type_fit": ["fps", "valorant", "cs2", "aim", "competitive"],
        "driver_reputation": ["driver", "software", "synapse", "g hub", "firmware"],
        "long_term_reliability": ["long term", "durability", "reliability", "double click", "qc"],
        "community_sentiment": ["review", "users", "community", "reddit", "comments"],
        "build_quality": ["build quality", "creak", "coating", "feet", "shell"],
    }
    for index, doc in enumerate(docs, start=1):
        text = _as_text(doc.get("text")).lower()
        title = _as_text(doc.get("title"))
        for dimension, keywords in keyword_map.items():
            if any(keyword in text for keyword in keywords):
                source_id = f"S{index}"
                source_kind = _as_text(doc.get("source_kind"))
                confidence = "medium" if source_kind in {"review_site", "creator_review"} else "low"
                signal = _normalize_signal(
                    {
                        "dimension": dimension,
                        "summary": f"{title or 'Review source'} mentions {dimension.replace('_', ' ')} related feedback.",
                        "sentiment": "unknown",
                        "confidence": confidence,
                        "support_level": "medium" if confidence == "medium" else "weak",
                        "source_ids": [source_id],
                        "evidence_snippets": [_as_text(doc.get("text"))[:240]],
                    },
                    docs_by_id,
                )
                if signal:
                    signals.append(signal)
                break
    deduped: Dict[str, Dict[str, Any]] = {}
    for signal in signals:
        dimension = _as_text(signal.get("dimension"))
        current = deduped.get(dimension)
        if not current or _source_rank(signal.get("source_kinds", [""])[0]) > _source_rank(current.get("source_kinds", [""])[0]):
            deduped[dimension] = signal
    return list(deduped.values())


def _parse_llm_result(payload: Dict[str, Any], docs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], List[str]]:
    docs_by_id = _source_lookup(docs)
    signals: List[Dict[str, Any]] = []
    for raw in payload.get("signals", []) if isinstance(payload.get("signals"), list) else []:
        if not isinstance(raw, dict):
            continue
        signal = _normalize_signal(raw, docs_by_id)
        if signal:
            signals.append(signal)

    recommendations: List[Dict[str, Any]] = []
    for raw in payload.get("fit_recommendations", []) if isinstance(payload.get("fit_recommendations"), list) else []:
        if not isinstance(raw, dict):
            continue
        source_ids = [
            _as_text(item)
            for item in raw.get("source_ids", [])
            if _as_text(item) in docs_by_id
        ] if isinstance(raw.get("source_ids"), list) else []
        summary = _as_text(raw.get("summary"))
        if not source_ids or not summary:
            continue
        recommendations.append(
            {
                "scenario": _as_text(raw.get("scenario")) or "experience_fit",
                "summary": summary[:500],
                "confidence": _as_text(raw.get("confidence")) or "low",
                "source_ids": source_ids,
                "source_urls": [_as_text(docs_by_id[source_id].get("url")) for source_id in source_ids],
            }
        )
    complaints = [
        _as_text(item)[:300]
        for item in payload.get("common_complaints", [])
        if _as_text(item)
    ] if isinstance(payload.get("common_complaints"), list) else []
    limitations = [
        _as_text(item)[:300]
        for item in payload.get("limitations", [])
        if _as_text(item)
    ] if isinstance(payload.get("limitations"), list) else []
    return signals, recommendations[:6], complaints[:8], limitations[:8]


def _source_summary(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "review_site": 0,
        "creator_review": 0,
        "community_review": 0,
        "ecommerce_review": 0,
        "search_result": 0,
    }
    for doc in docs:
        kind = _as_text(doc.get("source_kind")) or "search_result"
        summary[kind] = summary.get(kind, 0) + 1
    return summary


def _fetch_summary(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    """How each source's body text was obtained (reader/direct/reddit_json/cache/snippet)."""
    summary: Dict[str, int] = {}
    for doc in docs:
        method = _as_text(doc.get("fetch_method")) or "snippet_only"
        summary[method] = summary.get(method, 0) + 1
    return summary


def _pending_result(target: Dict[str, Any], status: str, note: str, *, search_result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "product_id": _as_text(target.get("product_id") or target.get("id")),
        "brand": _as_text(target.get("brand")),
        "model": _as_text(target.get("model") or target.get("input")),
        "status": status,
        "signals": {},
        "fit_recommendations": [],
        "common_complaints": [],
        "limitations": [note] if note else [],
        "source_summary": {},
        "source_urls": [],
        "search_result": search_result or {},
        "confidence_level": "none",
        "review_dimensions_pending": list(REVIEW_DIMENSIONS),
        "note": note,
        "extraction_method": "pending",
        "collected_at": _now(),
    }


_LOCAL_REVIEW_DB_CACHE: Dict[str, Any] | None = None


def _load_local_review_db() -> List[Dict[str, Any]]:
    """Load and cache the curated local review database (database route)."""
    global _LOCAL_REVIEW_DB_CACHE
    if _LOCAL_REVIEW_DB_CACHE is not None:
        return _LOCAL_REVIEW_DB_CACHE.get("records", [])
    records: List[Dict[str, Any]] = []
    for path in _LOCAL_REVIEW_DB_PATHS:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("records"), list):
                    records = [item for item in payload["records"] if isinstance(item, dict)]
                    break
        except (OSError, json.JSONDecodeError):
            continue
    _LOCAL_REVIEW_DB_CACHE = {"records": records}
    return records


def _local_entry_tokens(entry: Dict[str, Any]) -> set[str]:
    match = entry.get("match") if isinstance(entry.get("match"), dict) else {}
    tokens = {_identity_tokens(match.get("product_id"))}
    for alias in match.get("aliases", []) if isinstance(match.get("aliases"), list) else []:
        tokens.add(_identity_tokens(alias))
    tokens.add(_identity_tokens(entry.get("model")))
    return {token for token in tokens if token}


def _match_local_review(target: Dict[str, Any]) -> Dict[str, Any] | None:
    target_tokens = {
        _identity_tokens(target.get(key))
        for key in ("product_id", "id", "model", "input")
    }
    target_tokens = {token for token in target_tokens if token}
    if not target_tokens:
        return None
    for entry in _load_local_review_db():
        if target_tokens & _local_entry_tokens(entry):
            return entry
    return None


def _normalize_local_signal(dimension: str, raw: Dict[str, Any]) -> Dict[str, Any] | None:
    dimension = _normalize_dimension(dimension) or _as_text(dimension)
    summary = _as_text(raw.get("summary"))
    if not dimension or not summary:
        return None
    confidence = _as_text(raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    support_level = _as_text(raw.get("support_level")).lower()
    if support_level not in {"strong", "medium", "weak"}:
        support_level = "strong" if confidence == "high" else "medium" if confidence == "medium" else "weak"
    sentiment = _as_text(raw.get("sentiment")).lower()
    if sentiment not in {"positive", "mixed", "negative", "unknown"}:
        sentiment = "unknown"
    source_urls = [_as_text(url) for url in raw.get("source_urls", []) if _as_text(url)] if isinstance(raw.get("source_urls"), list) else []
    source_kinds = [_as_text(kind) for kind in raw.get("source_kinds", []) if _as_text(kind)] if isinstance(raw.get("source_kinds"), list) else []
    snippets = [_as_text(item)[:280] for item in raw.get("evidence_snippets", []) if _as_text(item)] if isinstance(raw.get("evidence_snippets"), list) else []
    corroboration = raw.get("corroborating_sources")
    if not isinstance(corroboration, int):
        corroboration = len({_domain(url) for url in source_urls if url}) or 1
    return {
        "dimension": dimension,
        "summary": summary[:500],
        "sentiment": sentiment,
        "confidence": confidence,
        "support_level": support_level,
        "source_ids": [],
        "source_urls": source_urls,
        "source_kinds": source_kinds or ["review_site"],
        "corroborating_sources": corroboration,
        "evidence_snippets": snippets[:3],
    }


def _record_from_local_entry(entry: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    """Build a canonical review record (same shape as the crawler) from a local DB entry."""
    raw_signals = entry.get("signals") if isinstance(entry.get("signals"), dict) else {}
    signals: Dict[str, Dict[str, Any]] = {}
    for dimension, raw in raw_signals.items():
        if not isinstance(raw, dict):
            continue
        signal = _normalize_local_signal(dimension, raw)
        if signal:
            signals[signal["dimension"]] = signal

    sources = [item for item in entry.get("sources", []) if isinstance(item, dict)] if isinstance(entry.get("sources"), list) else []
    source_summary: Dict[str, int] = {}
    for src in sources:
        kind = _as_text(src.get("source_kind")) or "review_site"
        source_summary[kind] = source_summary.get(kind, 0) + 1
    source_urls: List[str] = []
    for src in sources:
        url = _as_text(src.get("url"))
        if url and url not in source_urls:
            source_urls.append(url)
    for signal in signals.values():
        for url in signal.get("source_urls", []):
            if _as_text(url) and url not in source_urls:
                source_urls.append(url)

    pending = [dimension for dimension in REVIEW_DIMENSIONS if dimension not in signals]
    confidence = _as_text(entry.get("confidence_level")).lower() or _record_confidence(list(signals.values()))
    status = _as_text(entry.get("status")) or ("collected" if not pending else "partial_collected")
    fit = [item for item in entry.get("fit_recommendations", []) if isinstance(item, dict)] if isinstance(entry.get("fit_recommendations"), list) else []
    complaints = [_as_text(item)[:300] for item in entry.get("common_complaints", []) if _as_text(item)] if isinstance(entry.get("common_complaints"), list) else []
    limitations = [_as_text(item)[:300] for item in entry.get("limitations", []) if _as_text(item)] if isinstance(entry.get("limitations"), list) else []
    note = _as_text(entry.get("note")) or "本地评价数据库命中（database 路线）。"
    return {
        "input": _as_text(target.get("input") or target.get("model")) or _as_text(entry.get("model")),
        "product_id": _as_text(target.get("product_id") or target.get("id")),
        "brand": _as_text(target.get("brand")) or _as_text(entry.get("brand")),
        "model": _as_text(target.get("model") or target.get("input")) or _as_text(entry.get("model")),
        "status": status,
        "signals": signals,
        "fit_recommendations": fit[:6],
        "common_complaints": complaints[:8],
        "limitations": limitations[:8],
        "sources": sources,
        "source_summary": source_summary,
        "fetch_summary": {"local_database": len(sources)} if sources else {"local_database": 1},
        "source_urls": source_urls,
        "blocked_sources": [],
        "search_result": {},
        "confidence_level": confidence if confidence in {"high", "medium", "low"} else "medium",
        "review_dimensions_pending": pending,
        "note": note,
        "extraction_method": "local_database",
        "source_route": "local_database",
        "llm_model": "",
        "collected_at": _now(),
    }


def collect_review_intel_for_product(target: Dict[str, Any], *, category: str = "gaming_mouse") -> Dict[str, Any]:
    del category
    mcp_started = time.perf_counter()
    config = _config()
    if config.local_db_enabled:
        local_entry = _match_local_review(target)
        if local_entry:
            return _record_from_local_entry(local_entry, target)
    if not config.enabled and not config.search_enabled:
        return _pending_result(
            target,
            "mcp_not_configured",
            "ReviewIntelMCP is disabled. Set REVIEW_INTEL_MCP_ENABLED=1 and configure an LLM/search provider.",
        )
    docs, search_result, blocked = _source_docs(target, config)
    if not docs:
        return {
            **_pending_result(
                target,
                "no_sources",
                "ReviewIntelMCP found no usable review, creator, community, or ecommerce-review sources.",
                search_result=search_result,
            ),
            "blocked_sources": blocked,
            "mcp_usage": [
                item
                for item in [
                    search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                    make_mcp_usage_record(
                        agent="CollectorAgent",
                        tool="review_intel_mcp",
                        status="no_sources",
                        started_at=mcp_started,
                        provider="review_sources",
                        query=_as_text(target.get("input") or target.get("model")),
                        result_count=0,
                        uses_llm=False,
                        metadata={"blocked_count": len(blocked)},
                    ),
                ]
                if isinstance(item, dict)
            ],
        }

    signals: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    complaints: List[str] = []
    limitations: List[str] = []
    llm_error = ""
    llm_usage: Dict[str, Any] | None = None
    if config.enabled and config.api_key and config.model:
        try:
            llm = _get_llm(config)
            prompt = _prompt(target, docs, config.per_source_chars)
            llm_started = time.perf_counter()
            response = llm.invoke(prompt)
            response_text = _response_to_text(response)
            llm_usage = make_llm_usage_record(
                agent="CollectorAgent",
                tool="review_intel_mcp",
                model=config.model,
                started_at=llm_started,
                prompt_text=prompt,
                response=response,
                response_text=response_text,
                status="success",
                metadata={"input": _as_text(target.get("input") or target.get("model")), "source_count": len(docs)},
            )
            parsed = _parse_json_object(response_text)
            signals, recommendations, complaints, limitations = _parse_llm_result(parsed, docs)
        except Exception as exc:  # noqa: BLE001 - MCP should degrade, not break the DAG.
            llm_error = f"{type(exc).__name__}"
            llm_usage = make_llm_usage_record(
                agent="CollectorAgent",
                tool="review_intel_mcp",
                model=config.model,
                started_at=llm_started if "llm_started" in locals() else mcp_started,
                prompt_text=prompt if "prompt" in locals() else "",
                status="failed",
                error=llm_error,
                metadata={"input": _as_text(target.get("input") or target.get("model")), "source_count": len(docs)},
            )

    if not signals:
        if config.allow_rule_fallback and not config.require_llm:
            signals = _rule_extract_signals(docs)
            if llm_error:
                limitations.append(f"LLM extraction failed ({llm_error}); rule-based snippet extraction was used.")
            elif not config.enabled:
                limitations.append("LLM extraction is disabled; rule-based snippet extraction was used.")
        else:
            if not (config.enabled and config.api_key and config.model):
                reason = "Review sources were found, but ReviewIntelMCP requires a configured LLM before extracting user/creator review conclusions."
                status = "llm_not_configured"
            elif llm_error:
                reason = f"Review sources were found, but LLM extraction failed ({llm_error}); no rule-based fallback was used."
                status = "llm_extraction_failed"
            else:
                reason = "Review sources were found, but the LLM did not return supported review signals."
                status = "insufficient_evidence"
            return {
                **_pending_result(
                    target,
                    status,
                    reason,
                    search_result=search_result,
                ),
                "sources": docs,
                "source_summary": _source_summary(docs),
                "source_urls": [_as_text(doc.get("url")) for doc in docs if _as_text(doc.get("url"))],
                "blocked_sources": blocked,
                "limitations": [reason],
                "llm_model": config.model,
                "llm_error": llm_error,
                "extraction_method": "llm_required",
                "llm_usage": llm_usage,
                "mcp_usage": [
                    item
                    for item in [
                        search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                        make_mcp_usage_record(
                            agent="CollectorAgent",
                            tool="review_intel_mcp",
                            status=status,
                            started_at=mcp_started,
                            provider="review_sources",
                            query=_as_text(target.get("input") or target.get("model")),
                            result_count=0,
                            uses_llm=bool(llm_usage),
                            metadata={"source_count": len(docs), "blocked_count": len(blocked)},
                        ),
                    ]
                    if isinstance(item, dict)
                ],
            }

    if not signals:
        return {
            **_pending_result(
                target,
                "insufficient_evidence",
                "Review sources were found, but no supported experience signal could be extracted.",
                search_result=search_result,
            ),
            "sources": docs,
            "source_summary": _source_summary(docs),
            "source_urls": [_as_text(doc.get("url")) for doc in docs if _as_text(doc.get("url"))],
            "blocked_sources": blocked,
            "limitations": limitations or ["No supported review signal extracted."],
            "llm_usage": llm_usage,
            "mcp_usage": [
                item
                for item in [
                    search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                    make_mcp_usage_record(
                        agent="CollectorAgent",
                        tool="review_intel_mcp",
                        status="insufficient_evidence",
                        started_at=mcp_started,
                        provider="review_sources",
                        query=_as_text(target.get("input") or target.get("model")),
                        result_count=0,
                        uses_llm=bool(llm_usage),
                        metadata={"source_count": len(docs), "blocked_count": len(blocked)},
                    ),
                ]
                if isinstance(item, dict)
            ],
        }

    # Group signals per dimension and cross-check corroboration across distinct domains.
    by_dimension_all: Dict[str, List[Dict[str, Any]]] = {}
    for signal in signals:
        dimension = _as_text(signal.get("dimension"))
        if dimension:
            by_dimension_all.setdefault(dimension, []).append(signal)

    rank = {"high": 3, "medium": 2, "low": 1}
    signals_by_dimension: Dict[str, Dict[str, Any]] = {}
    for dimension, group in by_dimension_all.items():
        best = max(group, key=lambda item: rank.get(_as_text(item.get("confidence")), 0))
        merged_urls: List[str] = []
        for item in group:
            for url in item.get("source_urls", []):
                if _as_text(url) and url not in merged_urls:
                    merged_urls.append(url)
        distinct_domains = {_domain(_as_text(url)) for url in merged_urls if _as_text(url)}
        corroboration = len(distinct_domains)
        best = {**best, "source_urls": merged_urls or best.get("source_urls", []), "corroborating_sources": corroboration}
        # ≥2 独立来源印证：弱信号升为强支撑，medium 可升 high（更"专业级"且更稳）。
        if corroboration >= 2:
            best["support_level"] = "strong"
            if _as_text(best.get("confidence")) == "medium":
                best["confidence"] = "high"
        signals_by_dimension[dimension] = best

    pending = [dimension for dimension in REVIEW_DIMENSIONS if dimension not in signals_by_dimension]
    status = "collected" if not pending else "partial_collected"
    confidence = _record_confidence(list(signals_by_dimension.values()))
    if confidence == "low":
        status = "partial_collected"
        limitations.append("Only low-confidence review/community/search sources support some signals.")

    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "product_id": _as_text(target.get("product_id") or target.get("id")),
        "brand": _as_text(target.get("brand")),
        "model": _as_text(target.get("model") or target.get("input")),
        "status": status,
        "signals": signals_by_dimension,
        "fit_recommendations": recommendations,
        "common_complaints": complaints,
        "limitations": limitations,
        "sources": docs,
        "source_summary": _source_summary(docs),
        "fetch_summary": _fetch_summary(docs),
        "source_urls": [_as_text(doc.get("url")) for doc in docs if _as_text(doc.get("url"))],
        "blocked_sources": blocked,
        "search_result": search_result,
        "confidence_level": confidence,
        "review_dimensions_pending": pending,
        "note": "ReviewIntelMCP extracted review-backed experience signals.",
        "extraction_method": "rule_fallback" if limitations and any("rule-based" in item for item in limitations) else "llm",
        "llm_model": config.model if config.enabled and config.api_key and config.model else "",
        "llm_usage": llm_usage,
        "mcp_usage": [
            item
            for item in [
                search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                make_mcp_usage_record(
                    agent="CollectorAgent",
                    tool="review_intel_mcp",
                    status=status,
                    started_at=mcp_started,
                    provider="review_sources",
                    query=_as_text(target.get("input") or target.get("model")),
                    result_count=len(signals_by_dimension),
                    uses_llm=bool(llm_usage),
                    metadata={"source_count": len(docs), "blocked_count": len(blocked)},
                ),
            ]
            if isinstance(item, dict)
        ],
        "collected_at": _now(),
    }


def collect_review_intel(targets: List[Dict[str, Any]], *, category: str = "gaming_mouse") -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        key = _identity_tokens(target.get("product_id") or target.get("id") or target.get("model") or target.get("input"))
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(collect_review_intel_for_product(target, category=category))
    return results


def _identity_tokens(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _as_text(value).lower())


def _record_identity_keys(record: Dict[str, Any]) -> List[str]:
    keys = [
        record.get("product_id"),
        record.get("id"),
        record.get("model"),
        record.get("input"),
        " ".join(part for part in (_as_text(record.get("brand")), _as_text(record.get("model"))) if part),
    ]
    return [key for key in (_identity_tokens(item) for item in keys) if key]


def _evidence_identity_keys(evidence: Dict[str, Any]) -> List[str]:
    keys = [
        evidence.get("product_id"),
        evidence.get("platform"),
        evidence.get("model"),
        evidence.get("product"),
        evidence.get("source_title"),
    ]
    return [key for key in (_identity_tokens(item) for item in keys) if key]


def _same_review_product(evidence: Dict[str, Any], record: Dict[str, Any]) -> bool:
    evidence_keys = _evidence_identity_keys(evidence)
    record_keys = _record_identity_keys(record)
    for evidence_key in evidence_keys:
        for record_key in record_keys:
            if evidence_key == record_key:
                return True
            if min(len(evidence_key), len(record_key)) >= 8 and (
                evidence_key in record_key or record_key in evidence_key
            ):
                return True
    return False


def _is_review_evidence(evidence: Dict[str, Any]) -> bool:
    related = _as_text(evidence.get("related_dimension") or evidence.get("dimension"))
    source_url = _as_text(evidence.get("source_url"))
    source_type = _as_text(evidence.get("source_type")).lower()
    return (
        related in PENDING_LABEL_TO_DIMENSIONS
        or source_url.startswith("pending://realtime-review")
        or source_type in {"review", "review_site", "creator_review", "community_review", "ecommerce_review"}
    )


def _review_bucket_for_evidence(evidence: Dict[str, Any]) -> str:
    related = _as_text(evidence.get("related_dimension") or evidence.get("dimension"))
    if related in PENDING_LABEL_TO_DIMENSIONS:
        return related
    blob = " ".join(_as_text(evidence.get(key)) for key in ("source_title", "claim", "raw_content"))
    for label in PENDING_LABEL_TO_DIMENSIONS:
        if label in blob:
            return label
    return "用户口碑"


def _signal_for_bucket(record: Dict[str, Any], bucket: str) -> Dict[str, Any] | None:
    signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
    dimensions = PENDING_LABEL_TO_DIMENSIONS.get(bucket, set())
    candidates = [
        signal
        for dimension, signal in signals.items()
        if dimension in dimensions and isinstance(signal, dict)
    ]
    if not candidates:
        return None
    rank = {"high": 3, "medium": 2, "low": 1}
    return sorted(
        candidates,
        key=lambda item: rank.get(_as_text(item.get("confidence")), 0),
        reverse=True,
    )[0]


def _signal_reliability(signal: Dict[str, Any] | None) -> tuple[str, float, str, bool]:
    if not signal:
        return "low", 0.3, "pending", True
    confidence = _as_text(signal.get("confidence")).lower()
    if confidence == "high":
        return "high", 0.88, "verified", False
    if confidence == "medium":
        return "medium", 0.72, "partial_verified", False
    return "low", 0.5, "weak_support", True


def _review_evidence_from_record(
    record: Dict[str, Any],
    evidence_id: str,
    bucket: str,
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    model = _as_text(record.get("model") or record.get("input")) or "unknown product"
    # Explicit signal lets every signal get its own evidence_id (so verification of a
    # fully-collected record marks all dimensions supported, not just the bucket-best one).
    if signal is None:
        signal = _signal_for_bucket(record, bucket)
    credibility, score, data_status, evidence_gap = _signal_reliability(signal)
    if signal:
        dimension = _as_text(signal.get("dimension"))
        source_urls = [url for url in signal.get("source_urls", []) if _as_text(url)]
        source_url = _as_text(source_urls[0]) if source_urls else ""
        source_kind = _as_text((signal.get("source_kinds") or ["review"])[0]) if isinstance(signal.get("source_kinds"), list) else "review"
        claim = f"{model} review signal for {dimension}: {_as_text(signal.get('summary'))}"
        summary = _as_text(signal.get("summary"))
        title_suffix = f" · {dimension}" if dimension else ""
        raw = {
            "bucket": bucket,
            "signal": signal,
            "record_status": record.get("status"),
            "confidence_level": record.get("confidence_level"),
        }
        pending_research = False
        record.setdefault("evidence_ids", []).append(evidence_id)
        signal.setdefault("evidence_ids", []).append(evidence_id)
    else:
        source_url = ""
        source_kind = "review_pending"
        claim = f"{model} {bucket} review evidence is not available yet."
        summary = "Review intelligence remains pending for this dimension."
        raw = {
            "bucket": bucket,
            "record_status": record.get("status"),
            "review_dimensions_pending": record.get("review_dimensions_pending", []),
            "note": record.get("note"),
        }
        pending_research = True
        title_suffix = ""
    return {
        "evidence_id": evidence_id,
        "platform": model,
        "claim": claim,
        "source_type": source_kind,
        "source_title": f"{model} {bucket}{title_suffix} review intelligence",
        "source_url": source_url,
        "publish_time": "",
        "collected_time": record.get("collected_at") or _now(),
        "credibility": credibility,
        "related_dimension": bucket,
        "raw_content": json.dumps(raw, ensure_ascii=False),
        "confidence_score": score,
        "dimension": bucket,
        "content": json.dumps(raw, ensure_ascii=False),
        "summary": summary,
        "source": _domain(source_url) if source_url else "ReviewIntelMCP",
        "used_by_agent": "ReviewIntelMCP",
        "product_id": record.get("product_id") or "",
        "data_status": data_status,
        "pending_research": pending_research,
        "evidence_gap": evidence_gap,
    }


def merge_review_records_into_evidence(
    evidence_list: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fill existing review evidence slots before appending new rows."""
    updated = [dict(item) for item in evidence_list if isinstance(item, dict)]
    used_indexes: set[int] = set()
    seq = len(updated)

    for record in records:
        if not isinstance(record, dict):
            continue
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        if not signals:
            continue
        # One evidence per signal so EVERY review dimension gets its own evidence_id.
        # The first signal of a bucket fills an existing pending placeholder; the rest
        # (same bucket, different dimension) are appended as new evidence rows.
        ordered = sorted(
            signals.items(),
            key=lambda item: (
                REVIEW_DIMENSIONS.index(item[0]) if item[0] in REVIEW_DIMENSIONS else len(REVIEW_DIMENSIONS)
            ),
        )
        filled_buckets: set[str] = set()
        for dimension, signal in ordered:
            if not isinstance(signal, dict):
                continue
            bucket = DIMENSION_TO_PENDING_LABEL.get(dimension, "用户口碑")
            match_index = None
            if bucket not in filled_buckets:
                for index, evidence in enumerate(updated):
                    if index in used_indexes:
                        continue
                    if not _is_review_evidence(evidence):
                        continue
                    if _review_bucket_for_evidence(evidence) != bucket:
                        continue
                    if _same_review_product(evidence, record):
                        match_index = index
                        break
            if match_index is not None:
                evidence_id = _as_text(updated[match_index].get("evidence_id")) or f"EV{match_index + 1:03d}"
                updated[match_index] = _review_evidence_from_record(record, evidence_id, bucket, signal)
                used_indexes.add(match_index)
            else:
                seq += 1
                updated.append(_review_evidence_from_record(record, f"EV{seq:03d}", bucket, signal))
            filled_buckets.add(bucket)
    return updated


def summarize_review_intel_status(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {
            "status": "pending",
            "mcp_required": True,
            "review_dimensions_pending": list(REVIEW_DIMENSIONS),
            "records": [],
            "collected_count": 0,
            "target_count": 0,
            "source_count": 0,
            "contribution_to_final_score": 0,
            "note": "ReviewIntelMCP did not receive product targets.",
        }
    collected = [
        item for item in records
        if isinstance(item, dict) and item.get("status") in {"collected", "partial_collected"}
    ]
    source_count = sum(
        len(item.get("source_urls", []))
        for item in records
        if isinstance(item, dict) and isinstance(item.get("source_urls"), list)
    )
    all_pending = sorted(
        {
            dimension
            for item in records
            if isinstance(item, dict)
            for dimension in item.get("review_dimensions_pending", [])
            if _as_text(dimension)
        }
    )
    low_conf = [item for item in collected if item.get("confidence_level") == "low"]
    extraction_methods = sorted(
        {
            _as_text(item.get("extraction_method"))
            for item in records
            if isinstance(item, dict) and _as_text(item.get("extraction_method"))
        }
    )
    if len(collected) == len(records) and not all_pending:
        status = "available"
    elif collected:
        status = "partial"
    else:
        status = _as_text(records[0].get("status")) or "pending"
    return {
        "status": status,
        "mcp_required": len(collected) < len(records) or bool(all_pending),
        "records": records,
        "collected_count": len(collected),
        "target_count": len(records),
        "source_count": source_count,
        "low_confidence_count": len(low_conf),
        "review_confidence": "low" if low_conf else ("medium" if collected else "pending"),
        "review_dimensions_pending": all_pending,
        "extraction_methods": extraction_methods,
        "contribution_to_final_score": 0,
        "note": (
            "ReviewIntelMCP collected some review-backed experience signals."
            if collected
            else "Review intelligence remains pending."
        ),
    }
