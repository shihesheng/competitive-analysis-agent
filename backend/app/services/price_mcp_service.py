"""Price MCP service for realtime-ish product price collection.

The service uses already resolved product identities plus known URLs. It does
not write prices to the local product catalog because prices are time-sensitive.
It returns structured price records that CollectorAgent can expose as evidence
and that ReportAgent can summarize later.
"""

from __future__ import annotations

import ast
import html
import json
import os
import re
import statistics
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


DEFAULT_MAX_PRICE_SOURCES = 3
DEFAULT_MAX_PAGE_CHARS = 18000
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class PriceMcpConfig:
    enabled: bool
    search_enabled: bool
    api_key: str
    model: str
    base_url: str
    region: str
    currency: str
    max_sources: int
    max_chars: int
    timeout_seconds: int


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


def _config() -> PriceMcpConfig:
    _load_env()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    api_key = (
        os.getenv("PRICE_API_KEY", "").strip()
        or deepseek_key
        or os.getenv("OFFICIAL_SPEC_API_KEY", "").strip()
        or os.getenv("ARK_API_KEY", "").strip()
    )
    model = (
        os.getenv("PRICE_MODEL", "").strip()
        or os.getenv("DEEPSEEK_MODEL", "").strip()
        or ("deepseek-chat" if deepseek_key else "")
        or os.getenv("OFFICIAL_SPEC_MODEL", "").strip()
        or os.getenv("ARK_EP", "").strip()
        or os.getenv("ARK_MODEL", "").strip()
    )
    base_url = (
        os.getenv("PRICE_BASE_URL", "").strip()
        or os.getenv("DEEPSEEK_BASE_URL", "").strip()
        or ("https://api.deepseek.com" if deepseek_key else "")
        or os.getenv("ARK_BASE_URL", "").strip()
        or "https://ark.cn-beijing.volces.com/api/v3"
    )
    default_enabled = "1" if api_key and model else "0"
    return PriceMcpConfig(
        enabled=_env_bool("PRICE_MCP_ENABLED", os.getenv("PRICE_USE_LLM", default_enabled)),
        search_enabled=_env_bool("PRICE_SEARCH_ENABLED", "1"),
        api_key=api_key,
        model=model,
        base_url=base_url,
        region=os.getenv("PRICE_REGION", "US").strip().upper() or "US",
        currency=os.getenv("PRICE_CURRENCY", "USD").strip().upper() or "USD",
        max_sources=_env_int("PRICE_MAX_SOURCES", DEFAULT_MAX_PRICE_SOURCES, minimum=1, maximum=8),
        max_chars=_env_int("PRICE_MAX_CHARS", DEFAULT_MAX_PAGE_CHARS, minimum=2000, maximum=40000),
        timeout_seconds=_env_int("PRICE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=3, maximum=40),
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

    try:
        decoded = raw.decode(encoding, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
    return {
        "url": url,
        "domain": _domain(url),
        "content_type": content_type,
        "text": _html_to_text(decoded, max_chars),
        "latency_ms": int((time.time() - started) * 1000),
    }


def _html_to_text(markup: str, max_chars: int) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", markup)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    return match.group(1).strip() if match else cleaned


def _balanced_json_candidates(text: str) -> Iterable[str]:
    for start, char in enumerate(text):
        if char not in "[{":
            continue
        stack = [char]
        in_string = False
        escape = False
        for index in range(start + 1, len(text)):
            current = text[index]
            if in_string:
                if escape:
                    escape = False
                elif current == "\\":
                    escape = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current in "[{":
                stack.append(current)
            elif current in "]}":
                if not stack:
                    break
                opening = stack[-1]
                if (opening, current) not in (("[", "]"), ("{", "}")):
                    break
                stack.pop()
                if not stack:
                    yield text[start : index + 1]
                    break


def _json_candidates(text: str) -> Iterable[str]:
    yield _strip_json_fence(text)
    for block in re.findall(r"```(?:json|JSON)?\s*(.*?)\s*```", text, re.DOTALL):
        yield block.strip()
    yield from _balanced_json_candidates(text)


def _try_parse_json(candidate: str) -> Any:
    normalized = candidate.strip().lstrip("\ufeff")
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(normalized)
        except (SyntaxError, ValueError):
            return None


def _parse_json_object(text: str) -> Dict[str, Any]:
    for candidate in _json_candidates(text):
        parsed = _try_parse_json(candidate)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"quotes": [item for item in parsed if isinstance(item, dict)]}
    return {}


def _response_to_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _get_llm(config: PriceMcpConfig) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0,
        timeout=45,
        max_retries=0,
    )


def _prompt(target: Dict[str, Any], sources: List[Dict[str, Any]], config: PriceMcpConfig) -> str:
    product_name = _as_text(target.get("model") or target.get("input"))
    brand = _as_text(target.get("brand"))
    source_text = "\n\n".join(
        f"Source {index}\nurl: {_as_text(source.get('url'))}\ndomain: {_as_text(source.get('domain'))}\ntext: {_as_text(source.get('text'))[: config.max_chars]}"
        for index, source in enumerate(sources, start=1)
    )
    return f"""
You are PriceMCP for a gaming mouse competitive-analysis system.
Extract current product prices from the provided official page/search snippets.

Rules:
- Return JSON only. No Markdown.
- Only include prices that likely refer to the target gaming mouse, not mousepads, dongles, skins, used parts, or older variants.
- Ignore monthly financing / installment prices (e.g., "$22/mo", "from $X/month", Affirm/Klarna/Afterpay). Only the full one-time purchase price counts.
- Ignore accessory or bundle prices (mousepad, dock, grips, case, dongle, spare parts).
- A current flagship gaming mouse typically costs about 80-220 {config.currency}; treat a price far below this as suspect (likely financing or an accessory) and set is_target_product=false.
- If a page says out of stock or notify me and no price is visible, do not invent a price.
- Prefer official store price when clearly available, then retailer prices.
- Use currency {config.currency} unless the source explicitly uses another currency.
- Do not compute recommendations or value scores.

Target:
brand: {brand}
product_name: {product_name}
region: {config.region}
currency: {config.currency}

Required JSON shape:
{{
  "quotes": [
    {{
      "retailer": string,
      "price": number,
      "currency": string,
      "availability": "in_stock" | "out_of_stock" | "preorder" | "unknown",
      "condition": "new" | "used" | "refurbished" | "unknown",
      "source_url": string,
      "source_type": "official_store" | "retailer" | "search_snippet",
      "is_target_product": boolean,
      "confidence": "high" | "medium" | "low",
      "evidence_snippet": string
    }}
  ],
  "rejected_reason": string | null
}}

Sources:
{source_text}
""".strip()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _price_in_expected_range(price: float, currency: str) -> bool:
    # 旗舰电竞鼠标的合理整机售价区间；下限抬高以挡掉分期价 / 配件价这类垃圾低价。
    currency = currency.upper()
    if currency in {"USD", "AUD", "EUR", "GBP"}:
        return 40 <= price <= 500
    if currency in {"CNY", "RMB"}:
        return 200 <= price <= 4000
    return 30 <= price <= 5000


# 分期/月供价 与 配件/捆绑价 —— 价格抽取里最常见的两类误命中，命中即丢弃。
_FINANCING_RE = re.compile(
    r"/\s*mo\b|/\s*month|per\s+month|monthly|installments?|payments?\s+of|"
    r"affirm|klarna|afterpay|financing|as\s+low\s+as\s*\$?\s*\d+\s*/",
    re.IGNORECASE,
)
_ACCESSORY_RE = re.compile(
    r"mouse\s*pad|mousepad|dock|charging\s+(?:dock|puck|pad|stand)|grip\s*tape|"
    r"bungee|keycap|wrist\s*rest|\bskin\b|sticker|\bbundle\b|paracord|dongle|"
    r"replacement|spare\s+part",
    re.IGNORECASE,
)
_LOW_TRUST_PRICE_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "bilibili.com",
    "www.bilibili.com",
    "tiktok.com",
    "reddit.com",
}


def _is_low_trust_price_domain(domain: str) -> bool:
    normalized = _domain(f"https://{domain}") if "://" not in domain else _domain(domain)
    return any(normalized == item or normalized.endswith(f".{item}") for item in _LOW_TRUST_PRICE_DOMAINS)


def _is_junk_context(snippet: str) -> bool:
    """报价上下文是否疑似分期价 / 配件价（这类不是整机售价）。"""
    text = snippet or ""
    return bool(_FINANCING_RE.search(text) or _ACCESSORY_RE.search(text))


def _normalize_quote(raw: Dict[str, Any], *, fallback_url: str, fallback_domain: str, config: PriceMcpConfig) -> Dict[str, Any] | None:
    price = _to_float(raw.get("price"))
    currency = _as_text(raw.get("currency")).upper() or config.currency
    if price is None or not _price_in_expected_range(price, currency):
        return None
    if raw.get("is_target_product") is False:
        return None
    if _is_junk_context(_as_text(raw.get("evidence_snippet"))):
        return None
    confidence = _as_text(raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    availability = _as_text(raw.get("availability")).lower() or "unknown"
    if availability not in {"in_stock", "out_of_stock", "preorder", "unknown"}:
        availability = "unknown"
    condition = _as_text(raw.get("condition")).lower() or "unknown"
    if condition not in {"new", "used", "refurbished", "unknown"}:
        condition = "unknown"
    source_url = _as_text(raw.get("source_url")) or fallback_url
    source_domain = _domain(source_url) if source_url else fallback_domain
    if _is_low_trust_price_domain(source_domain):
        return None
    return {
        "retailer": _as_text(raw.get("retailer")) or fallback_domain or source_domain,
        "price": round(price, 2),
        "currency": currency,
        "availability": availability,
        "condition": condition,
        "source_url": source_url,
        "source_domain": source_domain,
        "source_type": _as_text(raw.get("source_type")) or "search_snippet",
        "is_target_product": True,
        "confidence": confidence,
        "evidence_snippet": _as_text(raw.get("evidence_snippet"))[:260],
        "collected_at": _now(),
    }


def _rule_extract_quotes(source: Dict[str, Any], target: Dict[str, Any], config: PriceMcpConfig) -> List[Dict[str, Any]]:
    text = _as_text(source.get("text"))
    url = _as_text(source.get("url"))
    domain = _as_text(source.get("domain")) or _domain(url)
    if not text:
        return []
    product_name = _as_text(target.get("model") or target.get("input")).lower()
    if product_name:
        tokens = [token for token in re.findall(r"[a-z0-9]+", product_name) if len(token) >= 2]
        blob = text.lower()
        token_hits = sum(1 for token in tokens if token in blob)
        if tokens and token_hits / max(1, len(tokens)) < 0.45:
            return []

    patterns = [
        r"(?:USD|US\$|\$)\s*([0-9]{2,4}(?:[.,][0-9]{2})?)",
        r"([0-9]{2,4}(?:[.,][0-9]{2})?)\s*(?:USD|dollars?)",
        r"(?:CNY|RMB|¥|￥)\s*([0-9]{2,5}(?:[.,][0-9]{2})?)",
    ]
    quotes: List[Dict[str, Any]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 120)
            snippet = text[start:end]
            currency = "CNY" if re.search(r"(?:CNY|RMB|¥|￥)", match.group(0), flags=re.IGNORECASE) else config.currency
            quote = _normalize_quote(
                {
                    "retailer": domain,
                    "price": match.group(1),
                    "currency": currency,
                    "availability": "unknown",
                    "condition": "new",
                    "source_url": url,
                    "source_type": "official_store" if source.get("source_kind") == "official_page" else "search_snippet",
                    "is_target_product": True,
                    "confidence": "medium" if source.get("source_kind") == "official_page" else "low",
                    "evidence_snippet": snippet,
                },
                fallback_url=url,
                fallback_domain=domain,
                config=config,
            )
            if quote:
                quotes.append(quote)
    return quotes[:4]


def _dedupe_quotes(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, float, str]] = set()
    for quote in quotes:
        key = (
            _as_text(quote.get("source_domain") or quote.get("retailer")).lower(),
            float(quote.get("price") or 0),
            _as_text(quote.get("currency")).upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(quote)
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    deduped.sort(key=lambda item: (conf_rank.get(item.get("confidence"), 0), -float(item.get("price") or 99999)), reverse=True)
    return deduped


def _anchor_price(quotes: List[Dict[str, Any]]) -> float | None:
    """锚点价：优先官方店价；否则取 high/medium 可信报价的中位数；再否则全体中位数。"""
    def prices(predicate) -> List[float]:
        return [
            float(quote["price"])
            for quote in quotes
            if isinstance(quote.get("price"), (int, float)) and predicate(quote)
        ]

    official = prices(lambda q: q.get("source_type") == "official_store")
    if official:
        return statistics.median(official)
    strong = prices(lambda q: q.get("confidence") in {"high", "medium"})
    if strong:
        return statistics.median(strong)
    allp = prices(lambda q: True)
    return statistics.median(allp) if allp else None


def _filter_quotes(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """以锚点价为基准剔除离群报价（< 0.5× 或 > 2×），挡掉串到配件 / 别的产品的价格。"""
    anchor = _anchor_price(quotes)
    if not anchor or anchor <= 0:
        return quotes
    low, high = 0.5 * anchor, 2.0 * anchor
    kept = [
        quote
        for quote in quotes
        if isinstance(quote.get("price"), (int, float)) and low <= float(quote["price"]) <= high
    ]
    return kept or quotes  # 兜底：不要把所有报价都剔光


def _summary(quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [
        quote for quote in quotes
        if quote.get("condition") in {"new", "unknown"}
        and quote.get("availability") in {"in_stock", "preorder", "unknown"}
    ]
    prices = [float(item["price"]) for item in valid if isinstance(item.get("price"), (int, float))]
    if not prices:
        return {"sample_count": 0}
    official = [
        float(item["price"])
        for item in valid
        if item.get("source_type") == "official_store"
        and isinstance(item.get("price"), (int, float))
    ]
    return {
        "lowest_price": round(min(prices), 2),
        "median_price": round(statistics.median(prices), 2),
        "official_price": round(official[0], 2) if official else None,
        "sample_count": len(prices),
        "currency": valid[0].get("currency"),
    }


def _pending_result(target: Dict[str, Any], status: str, note: str, *, search_result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "product_id": _as_text(target.get("product_id") or target.get("id")),
        "brand": _as_text(target.get("brand")),
        "model": _as_text(target.get("model") or target.get("input")),
        "status": status,
        "region": os.getenv("PRICE_REGION", "US").strip().upper() or "US",
        "currency": os.getenv("PRICE_CURRENCY", "USD").strip().upper() or "USD",
        "quotes": [],
        "price_summary": {"sample_count": 0},
        "source_urls": [],
        "search_result": search_result or {},
        "note": note,
        "collected_at": _now(),
    }


def _fallback_links_from_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        url = _as_text(doc.get("url"))
        domain = _as_text(doc.get("domain")) or _domain(url)
        if not url or url in seen:
            continue
        if _is_low_trust_price_domain(domain):
            seen.add(url)
            links.append(
                {
                    "title": _as_text(doc.get("title")) or domain or "fallback source",
                    "url": url,
                    "domain": domain,
                    "source_kind": _as_text(doc.get("source_kind")) or "search_snippet",
                    "confidence": "low",
                    "note": "Fallback discovery link only; not a verified price quote.",
                }
            )
        if len(links) >= 3:
            break
    return links


def _source_docs(
    target: Dict[str, Any], config: PriceMcpConfig
) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    docs: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []  # 官方/已知页被反爬拦截时记下来，前端可展示"被反爬拦截"。
    search_result: Dict[str, Any] = {}
    urls = [_as_text(target.get("official_url"))]
    if isinstance(target.get("source_urls"), list):
        urls.extend(_as_text(url) for url in target.get("source_urls", []) if _as_text(url))
    seen_urls: set[str] = set()
    for url in urls:
        if not url or url in seen_urls or len(docs) >= config.max_sources:
            continue
        seen_urls.add(url)
        try:
            page = _fetch_page_text(url, config.timeout_seconds, config.max_chars)
            docs.append(
                {
                    "url": url,
                    "domain": page.get("domain") or _domain(url),
                    "text": page.get("text") or "",
                    "source_kind": "official_page",
                    "latency_ms": page.get("latency_ms"),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            blocked.append({"url": url, "domain": _domain(url), "reason": type(exc).__name__})
            continue

    if config.search_enabled:
        query = _as_text(target.get("model") or target.get("input"))
        if query:
            search_started = time.perf_counter()
            search_result = search_candidates(query, category="gaming_mouse", intent="price_collection")
            search_result["mcp_usage"] = make_mcp_usage_record(
                agent="CollectorAgent",
                tool="search_mcp",
                status=_as_text(search_result.get("status")) or "success",
                started_at=search_started,
                provider=_as_text(search_result.get("provider")) or "search",
                query=_as_text(search_result.get("executed_query") or search_result.get("_executed_query") or query),
                result_count=len(search_result.get("candidates") if isinstance(search_result.get("candidates"), list) else []),
                uses_llm=False,
                metadata={"intent": "price_collection", "input": query},
            )
            candidates = search_result.get("candidates") if isinstance(search_result.get("candidates"), list) else []
            for candidate in candidates[: config.max_sources]:
                if not isinstance(candidate, dict):
                    continue
                snippet = " ".join(
                    _as_text(candidate.get(key))
                    for key in ("title", "snippet", "url", "domain")
                    if _as_text(candidate.get(key))
                )
                if not snippet:
                    continue
                docs.append(
                    {
                        "url": _as_text(candidate.get("url")),
                        "domain": _as_text(candidate.get("domain")),
                        "title": _as_text(candidate.get("title")),
                        "text": snippet,
                        "source_kind": "search_snippet",
                    }
                )
    return docs, search_result, blocked


def collect_price_for_product(target: Dict[str, Any], *, category: str = "gaming_mouse") -> Dict[str, Any]:
    del category
    mcp_started = time.perf_counter()
    config = _config()
    if not config.enabled and not config.search_enabled:
        return _pending_result(
            target,
            "mcp_not_configured",
            "PriceMCP is disabled. Set PRICE_MCP_ENABLED=1 or PRICE_SEARCH_ENABLED=1 to collect realtime prices.",
        )
    docs, search_result, blocked = _source_docs(target, config)
    if not docs:
        return {
            **_pending_result(
                target,
                "no_sources",
                "PriceMCP could not read an official page or search result for this product.",
                search_result=search_result,
            ),
            "blocked_sources": blocked,
            "official_price_blocked": bool(blocked),
            "confidence_level": "none",
            "mcp_usage": [
                item
                for item in [
                    search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                    make_mcp_usage_record(
                        agent="CollectorAgent",
                        tool="price_mcp",
                        status="no_sources",
                        started_at=mcp_started,
                        provider="price_sources",
                        query=_as_text(target.get("input") or target.get("model")),
                        result_count=0,
                        uses_llm=False,
                        metadata={"blocked_count": len(blocked)},
                    ),
                ]
                if isinstance(item, dict)
            ],
        }
    fallback_links = _fallback_links_from_docs(docs)

    rule_quotes: List[Dict[str, Any]] = []
    for doc in docs:
        rule_quotes.extend(_rule_extract_quotes(doc, target, config))

    llm_quotes: List[Dict[str, Any]] = []
    llm_error = ""
    llm_usage: Dict[str, Any] | None = None
    if config.enabled and config.api_key and config.model:
        try:
            llm = _get_llm(config)
            prompt = _prompt(target, docs, config)
            llm_started = time.perf_counter()
            response = llm.invoke(prompt)
            response_text = _response_to_text(response)
            llm_usage = make_llm_usage_record(
                agent="CollectorAgent",
                tool="price_mcp",
                model=config.model,
                started_at=llm_started,
                prompt_text=prompt,
                response=response,
                response_text=response_text,
                status="success",
                metadata={"input": _as_text(target.get("input") or target.get("model")), "source_count": len(docs)},
            )
            parsed = _parse_json_object(response_text)
            for raw in parsed.get("quotes", []) if isinstance(parsed.get("quotes"), list) else []:
                if not isinstance(raw, dict):
                    continue
                quote = _normalize_quote(
                    raw,
                    fallback_url=_as_text(docs[0].get("url")),
                    fallback_domain=_as_text(docs[0].get("domain")),
                    config=config,
                )
                if quote:
                    llm_quotes.append(quote)
        except Exception as exc:  # noqa: BLE001 - MCP should degrade, not break the DAG.
            llm_error = f"{type(exc).__name__}"
            llm_usage = make_llm_usage_record(
                agent="CollectorAgent",
                tool="price_mcp",
                model=config.model,
                started_at=llm_started if "llm_started" in locals() else mcp_started,
                prompt_text=prompt if "prompt" in locals() else "",
                status="failed",
                error=llm_error,
                metadata={"input": _as_text(target.get("input") or target.get("model")), "source_count": len(docs)},
            )

    quotes = _filter_quotes(_dedupe_quotes([*llm_quotes, *rule_quotes]))
    if not quotes:
        status = "llm_failed" if llm_error and not rule_quotes else "no_price_found"
        note = (
            f"PriceMCP read {len(docs)} source(s), but no target-product price was found."
            if not llm_error
            else f"PriceMCP LLM extraction failed ({llm_error}) and rule extraction found no price."
        )
        if not config.enabled:
            status = "mcp_not_configured"
            note = "PriceMCP has sources but PRICE_MCP_ENABLED/PRICE_API_KEY/PRICE_MODEL are not configured; no reliable price quote was extracted."
        return {
            **_pending_result(target, status, note, search_result=search_result),
            "source_urls": [_as_text(doc.get("url")) for doc in docs if _as_text(doc.get("url"))],
            "fallback_links": fallback_links,
            "blocked_sources": blocked,
            "official_price_blocked": bool(blocked),
            "confidence_level": "none",
            "llm_usage": llm_usage,
            "mcp_usage": [
                item
                for item in [
                    search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                    make_mcp_usage_record(
                        agent="CollectorAgent",
                        tool="price_mcp",
                        status=status,
                        started_at=mcp_started,
                        provider="price_sources",
                        query=_as_text(target.get("input") or target.get("model")),
                        result_count=0,
                        uses_llm=bool(llm_usage),
                        metadata={"source_count": len(docs), "blocked_count": len(blocked)},
                    ),
                ]
                if isinstance(item, dict)
            ],
        }

    summary = _summary(quotes)
    has_official = any(
        quote.get("source_type") == "official_store"
        and quote.get("confidence") in {"high", "medium"}
        for quote in quotes
    )
    # Only official-store price is high confidence. Retail/search/ecommerce prices
    # are usable for comparison, but should stay low-confidence in the report.
    confidence_level = "high" if has_official else "low"
    official_price_blocked = summary.get("official_price") is None and bool(blocked)
    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "product_id": _as_text(target.get("product_id") or target.get("id")),
        "brand": _as_text(target.get("brand")),
        "model": _as_text(target.get("model") or target.get("input")),
        "status": "collected",
        "region": config.region,
        "currency": summary.get("currency") or config.currency,
        "quotes": quotes,
        "price_summary": summary,
        "confidence_level": confidence_level,
        "official_price_blocked": official_price_blocked,
        "blocked_sources": blocked,
        "source_urls": [_as_text(doc.get("url")) for doc in docs if _as_text(doc.get("url"))],
        "fallback_links": fallback_links,
        "search_result": search_result,
        "llm_usage": llm_usage,
        "mcp_usage": [
            item
            for item in [
                search_result.get("mcp_usage") if isinstance(search_result, dict) else None,
                make_mcp_usage_record(
                    agent="CollectorAgent",
                    tool="price_mcp",
                    status="collected",
                    started_at=mcp_started,
                    provider="price_sources",
                    query=_as_text(target.get("input") or target.get("model")),
                    result_count=len(quotes),
                    uses_llm=bool(llm_usage),
                    metadata={"source_count": len(docs), "blocked_count": len(blocked)},
                ),
            ]
            if isinstance(item, dict)
        ],
        "note": (
            "官方价被反爬拦截，价格来自其他高可信来源。"
            if official_price_blocked
            else "PriceMCP extracted realtime price quote candidates; value scoring is left to AnalysisAgent."
        ),
        "collected_at": _now(),
    }


def collect_prices(targets: List[Dict[str, Any]], *, category: str = "gaming_mouse") -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        key = _as_text(target.get("product_id") or target.get("id") or target.get("model") or target.get("input"))
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(collect_price_for_product(target, category=category))
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


def _is_realtime_price_evidence(evidence: Dict[str, Any]) -> bool:
    related = _as_text(evidence.get("related_dimension") or evidence.get("dimension")).lower()
    blob = " ".join(
        _as_text(evidence.get(key))
        for key in ("source_title", "claim", "summary", "raw_content")
    ).lower()
    return (
        related in {"realtime_price", "实时价格"}
        or "realtime_price" in blob
        or "实时价格" in blob
        or "price quote" in blob
    )


def _same_price_product(evidence: Dict[str, Any], record: Dict[str, Any]) -> bool:
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


def _quote_rank(quote: Dict[str, Any]) -> tuple[int, int]:
    source_type = _as_text(quote.get("source_type")).lower()
    confidence = _as_text(quote.get("confidence")).lower()
    source_rank = 3 if source_type == "official_store" else 2 if source_type == "retailer" else 1
    confidence_rank = {"high": 3, "medium": 2, "low": 1}.get(confidence, 0)
    return source_rank, confidence_rank


def _best_price_quote(record: Dict[str, Any]) -> Dict[str, Any] | None:
    quotes = [
        item
        for item in record.get("quotes", [])
        if isinstance(item, dict)
        and isinstance(item.get("price"), (int, float))
        and _as_text(item.get("source_url"))
    ]
    if not quotes:
        return None
    return sorted(quotes, key=_quote_rank, reverse=True)[0]


def _price_evidence_reliability(quote: Dict[str, Any] | None) -> tuple[str, float, str, bool]:
    if not quote:
        return "low", 0.3, "pending", True
    if (
        _as_text(quote.get("source_type")).lower() == "official_store"
        and _as_text(quote.get("confidence")).lower() in {"high", "medium"}
    ):
        return "high", 0.92, "verified", False
    return "low", 0.48, "weak_support", True


def _price_evidence_from_record(record: Dict[str, Any], evidence_id: str) -> Dict[str, Any]:
    model = _as_text(record.get("model") or record.get("input")) or "unknown product"
    quote = _best_price_quote(record)
    fallback_links = [item for item in record.get("fallback_links", []) if isinstance(item, dict)]
    fallback_link = fallback_links[0] if fallback_links else {}
    credibility, score, data_status, evidence_gap = _price_evidence_reliability(quote)

    if quote:
        price = quote.get("price")
        currency = _as_text(quote.get("currency")) or _as_text(record.get("currency")) or "USD"
        retailer = _as_text(quote.get("retailer") or quote.get("source_domain")) or "price source"
        source_type = _as_text(quote.get("source_type")).lower()
        source_label = "official store" if source_type == "official_store" else "low-confidence commerce/search source"
        claim = f"{model} has a realtime price quote of {price} {currency} from {retailer}."
        summary = f"Realtime price quote from {source_label}: {price} {currency} ({retailer})."
        source_url = _as_text(quote.get("source_url"))
        source_title = f"{model} realtime price - {retailer}"
        raw = {
            "quote": quote,
            "record_status": record.get("status"),
            "confidence_level": record.get("confidence_level"),
            "official_price_blocked": record.get("official_price_blocked"),
            "blocked_sources": record.get("blocked_sources", []),
        }
        pending_research = False
    elif fallback_link:
        source_url = _as_text(fallback_link.get("url"))
        source_title = _as_text(fallback_link.get("title")) or f"{model} price fallback source"
        claim = f"{model} official price could not be verified; fallback discovery link is weak support only."
        summary = (
            "No usable price quote was extracted. Fallback link is retained for traceability, "
            "not for price-performance scoring."
        )
        raw = {
            "fallback_link": fallback_link,
            "blocked_sources": record.get("blocked_sources", []),
            "record_status": record.get("status"),
            "note": record.get("note"),
        }
        pending_research = False
        data_status = "weak_support"
        evidence_gap = True
    else:
        source_url = ""
        source_title = f"{model} realtime price pending"
        claim = f"{model} realtime price is not available yet."
        summary = _as_text(record.get("note")) or "Realtime price remains pending."
        raw = {
            "record_status": record.get("status"),
            "note": record.get("note"),
            "blocked_sources": record.get("blocked_sources", []),
        }
        pending_research = True

    evidence = {
        "evidence_id": evidence_id,
        "platform": model,
        "claim": claim,
        "source_type": "price" if quote else "price_fallback",
        "source_title": source_title,
        "source_url": source_url,
        "publish_time": "",
        "collected_time": (quote or {}).get("collected_at") or record.get("collected_at") or _now(),
        "credibility": credibility,
        "related_dimension": "realtime_price",
        "raw_content": json.dumps(raw, ensure_ascii=False),
        "confidence_score": score,
        "dimension": "realtime_price",
        "content": json.dumps(raw, ensure_ascii=False),
        "summary": summary,
        "source": _as_text((quote or {}).get("source_domain")) or _as_text(fallback_link.get("domain")) or "PriceMCP",
        "used_by_agent": "PriceMCP",
        "data_status": data_status,
        "pending_research": pending_research,
        "evidence_gap": evidence_gap,
    }
    record["evidence_id"] = evidence_id
    record["evidence_credibility"] = credibility
    record["evidence_status"] = data_status
    return evidence


def _best_quote_of(record: Dict[str, Any], predicate) -> Dict[str, Any] | None:
    quotes = [
        item
        for item in record.get("quotes", [])
        if isinstance(item, dict)
        and isinstance(item.get("price"), (int, float))
        and _as_text(item.get("source_url"))
        and predicate(item)
    ]
    return sorted(quotes, key=_quote_rank, reverse=True)[0] if quotes else None


def _best_official_quote(record: Dict[str, Any]) -> Dict[str, Any] | None:
    return _best_quote_of(record, lambda q: _as_text(q.get("source_type")).lower() == "official_store")


def _best_ecom_quote(record: Dict[str, Any]) -> Dict[str, Any] | None:
    return _best_quote_of(record, lambda q: _as_text(q.get("source_type")).lower() != "official_store")


def _build_price_evidence(record: Dict[str, Any], quote: Dict[str, Any] | None, evidence_id: str, *, kind: str) -> Dict[str, Any]:
    """构造一条价格证据。kind: official(官方价/高可信) | ecom(电商价/低可信) | pending(未抽到)。"""
    model = _as_text(record.get("model") or record.get("input")) or "unknown product"
    currency = _as_text((quote or {}).get("currency")) or _as_text(record.get("currency")) or "USD"
    price = (quote or {}).get("price")
    retailer = _as_text((quote or {}).get("retailer") or (quote or {}).get("source_domain"))
    if kind == "official":
        credibility, score, data_status = "high", 0.92, "verified"
        label, price_kind = "官方价", "official_price"
        claim = f"{model} 官方价 {price} {currency}（{retailer or '官方商店'}）。"
        summary = f"Official-store price: {price} {currency} ({retailer})."
        source_url = _as_text(quote.get("source_url"))
    elif kind == "ecom":
        credibility, score, data_status = "low", 0.5, "weak_support"
        label, price_kind = "电商价", "ecommerce_price"
        claim = f"{model} 电商价 {price} {currency}（{retailer or '零售/电商'}，非官方、低可信）。"
        summary = f"E-commerce price (low confidence): {price} {currency} ({retailer})."
        source_url = _as_text(quote.get("source_url"))
    else:  # pending / 抓不到
        fallback_links = [item for item in record.get("fallback_links", []) if isinstance(item, dict)]
        fallback = fallback_links[0] if fallback_links else {}
        credibility, score, data_status = "low", 0.3, "weak_support"
        label, price_kind = "实时价格", "price_pending"
        claim = f"{model} 未抽到可靠实时价格（官方页可能被反爬拦截），仅保留弱支撑来源。"
        summary = _as_text(record.get("note")) or "Realtime price pending."
        source_url = _as_text(fallback.get("url"))
        quote = None
    raw = {
        "price_kind": price_kind,
        "quote": quote,
        "record_status": record.get("status"),
        "official_price_blocked": record.get("official_price_blocked"),
        "blocked_sources": record.get("blocked_sources", []),
    }
    return {
        "evidence_id": evidence_id,
        "platform": model,
        "claim": claim,
        "source_type": "price",
        "price_kind": price_kind,
        "source_title": f"{model} {label} - {retailer}" if retailer else f"{model} {label}",
        "source_url": source_url,
        "publish_time": "",
        "collected_time": (quote or {}).get("collected_at") or record.get("collected_at") or _now(),
        "credibility": credibility,
        "related_dimension": "实时价格",
        "raw_content": json.dumps(raw, ensure_ascii=False),
        "confidence_score": score,
        "dimension": "实时价格",
        "content": json.dumps(raw, ensure_ascii=False),
        "summary": summary,
        "source": _as_text((quote or {}).get("source_domain")) or "PriceMCP",
        "used_by_agent": "PriceMCP",
        "data_status": data_status,
        "pending_research": kind == "pending",
        "evidence_gap": kind != "official",
    }


def _price_evidences_from_record(record: Dict[str, Any], seq: int) -> tuple[List[Dict[str, Any]], int]:
    """每个产品产出官方价 + 电商价两条证据（缺哪条就少哪条；都缺给一条 pending）。"""
    evidences: List[Dict[str, Any]] = []
    record.pop("official_evidence_id", None)
    record.pop("ecom_evidence_id", None)
    official_quote = _best_official_quote(record)
    ecom_quote = _best_ecom_quote(record)
    if official_quote:
        seq += 1
        ev = _build_price_evidence(record, official_quote, f"EV{seq:03d}", kind="official")
        record["official_evidence_id"] = ev["evidence_id"]
        evidences.append(ev)
    if ecom_quote:
        seq += 1
        ev = _build_price_evidence(record, ecom_quote, f"EV{seq:03d}", kind="ecom")
        record["ecom_evidence_id"] = ev["evidence_id"]
        evidences.append(ev)
    if not evidences:
        seq += 1
        ev = _build_price_evidence(record, None, f"EV{seq:03d}", kind="pending")
        record["evidence_id"] = ev["evidence_id"]
        evidences.append(ev)
    return evidences, seq


def price_records_to_evidence(records: List[Dict[str, Any]], existing_count: int) -> List[Dict[str, Any]]:
    """每个产品产出官方价 + 电商价两条价格证据（追加到 evidence_list）。"""
    evidence: List[Dict[str, Any]] = []
    seq = existing_count
    for record in records:
        if not isinstance(record, dict):
            continue
        evidences, seq = _price_evidences_from_record(record, seq)
        evidence.extend(evidences)
    return evidence


def merge_price_records_into_evidence(
    evidence_list: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fill existing realtime-price evidence slots before appending new rows."""
    updated = [dict(item) for item in evidence_list if isinstance(item, dict)]
    used_indexes: set[int] = set()
    seq = len(updated)

    for record in records:
        if not isinstance(record, dict):
            continue
        match_index = None
        for index, evidence in enumerate(updated):
            if index in used_indexes:
                continue
            if not _is_realtime_price_evidence(evidence):
                continue
            if _same_price_product(evidence, record):
                match_index = index
                break

        if match_index is not None:
            evidence_id = _as_text(updated[match_index].get("evidence_id")) or f"EV{match_index + 1:03d}"
            updated[match_index] = _price_evidence_from_record(record, evidence_id)
            used_indexes.add(match_index)
        else:
            seq += 1
            updated.append(_price_evidence_from_record(record, f"EV{seq:03d}"))

    return updated


def summarize_price_status(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {
            "status": "pending",
            "price_data_required": True,
            "records": [],
            "collected_count": 0,
            "sample_count": 0,
            "contribution_to_final_score": 0,
            "note": "PriceMCP did not receive product targets.",
        }
    collected = [item for item in records if isinstance(item, dict) and item.get("status") == "collected"]
    sample_count = sum(
        int((item.get("price_summary") or {}).get("sample_count") or 0)
        for item in collected
        if isinstance(item.get("price_summary"), dict)
    )
    low_conf = [item for item in collected if item.get("confidence_level") == "low"]
    blocked = [item for item in records if item.get("official_price_blocked")]
    status = "available" if len(collected) == len(records) else "partial" if collected else _as_text(records[0].get("status")) or "pending"
    return {
        "status": status,
        "price_data_required": len(collected) < len(records),
        "records": records,
        "collected_count": len(collected),
        "target_count": len(records),
        "sample_count": sample_count,
        "low_confidence_count": len(low_conf),
        "official_blocked_count": len(blocked),
        # 整体价格可信度：有低可信价 / 官方价被拦截 → low（报告可信度据此扣分）。
        "price_confidence": "low" if (low_conf or blocked) else ("high" if collected else "pending"),
        "contribution_to_final_score": 0,
        "note": (
            "官方价被反爬拦截，价格仅来自其他来源，可信度较低。"
            if blocked
            else "Realtime price quotes collected. AnalysisAgent can later compute value score."
            if collected
            else "Realtime price remains pending; no value score should be generated."
        ),
    }
