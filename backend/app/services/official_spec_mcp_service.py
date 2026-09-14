"""Official-spec MCP service for gaming mouse hardware extraction.

SearchMCP only discovers candidate official URLs. This service consumes an
official product URL, fetches the page text, and asks an LLM to extract a strict
hardware-spec JSON object. It does not write back to the local product catalog.
"""

from __future__ import annotations

import ast
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


BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

HARDWARE_FIELDS = [
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
]

ESSENTIAL_FIELDS = [
    "weight_g",
    "dimensions_mm",
    "sensor",
    "dpi_max",
    "polling_rate_hz",
    "connection",
    "click_system",
]


@dataclass(frozen=True)
class OfficialSpecConfig:
    enabled: bool
    api_key: str
    model: str
    base_url: str
    max_chars: int
    timeout_seconds: int
    max_products: int
    max_sources_per_product: int


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


def _config() -> OfficialSpecConfig:
    _load_env()
    return OfficialSpecConfig(
        enabled=_env_bool("OFFICIAL_SPEC_USE_LLM", "0"),
        api_key=(
            os.getenv("OFFICIAL_SPEC_API_KEY", "").strip()
            or os.getenv("ARK_API_KEY", "").strip()
        ),
        model=(
            os.getenv("OFFICIAL_SPEC_MODEL", "").strip()
            or os.getenv("ARK_EP", "").strip()
            or os.getenv("ARK_MODEL", "").strip()
        ),
        base_url=os.getenv("ARK_BASE_URL", BASE_URL).strip() or BASE_URL,
        max_chars=_env_int("OFFICIAL_SPEC_MAX_CHARS", 30000, minimum=2000, maximum=50000),
        timeout_seconds=_env_int("OFFICIAL_SPEC_TIMEOUT_SECONDS", 12, minimum=3, maximum=45),
        max_products=_env_int("OFFICIAL_SPEC_MAX_PRODUCTS", 2, minimum=1, maximum=6),
        max_sources_per_product=_env_int("OFFICIAL_SPEC_MAX_SOURCES_PER_PRODUCT", 3, minimum=1, maximum=6),
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


def _fetch_page_text(url: str, timeout_seconds: int, max_chars: int) -> Dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; CompetitiveAnalysisAgent/1.0; "
                "+https://localhost)"
            ),
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
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
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


def _get_llm(config: OfficialSpecConfig) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0,
        timeout=45,
        max_retries=0,
    )


def _prompt(target: Dict[str, Any], page_text: str) -> str:
    brand_hint = _as_text(target.get("brand"))
    model_hint = _as_text(target.get("input") or target.get("model"))
    page_title_hint = _as_text(target.get("source_title") or target.get("page_title") or target.get("model"))
    url = _as_text(target.get("official_url") or target.get("url"))
    return f"""
You are OfficialSpecMCP for a gaming mouse competitive-analysis system.
Extract only verifiable official hardware specs from the official product page text.

Rules:
- Return JSON only. No Markdown.
- Do not guess. If a field is not present in the page text, return null or [].
- Do not use review opinions, prices, grip recommendations, or marketing claims as specs.
- Prefer numeric values with units converted to grams, millimeters, Hertz, DPI, and hours.
- If multiple polling rates appear, use the highest official supported polling rate and mention uncertainty in missing_fields if unclear.
- missing_fields must contain only these exact field names when missing: weight_g, dimensions_mm, shape, shape_detail, sensor, dpi_max, polling_rate_hz, connection, battery_hours, switch_type, click_system, software, onboard_memory, mold_id.
- Map brand terms conservatively: HyperSpeed/LIGHTSPEED/wireless dongle means "2.4ghz"; USB or wired mode means "wired"; Bluetooth means "bluetooth".
- Map optical mouse switches to click_system="optical"; mechanical switches to click_system="mechanical"; hybrid/Lightforce to click_system="hybrid"; haptic/adjustable actuation to click_system="haptic".
- Scan the whole text for sections named Tech Specs, Specifications, Dimensions, Sensor, Battery Life, Connectivity, Switches, and On-board Memory.
- If the official page is a series/collection page with multiple variants, extract the variant that best matches model_hint.
- For example, if model_hint is "WLMOUSE Beast X Pro" and the page also contains Mini/Max/Miao, only use the Beast X Pro row or card.

Target:
brand_hint: {brand_hint}
model_hint: {model_hint}
page_title_hint: {page_title_hint}
official_url: {url}

Required JSON shape:
{{
  "brand": string | null,
  "official_model": string | null,
  "weight_g": number | null,
  "dimensions_mm": {{"length": number | null, "width": number | null, "height": number | null}} | null,
  "shape": "symmetrical" | "ergonomic" | null,
  "shape_detail": string | null,
  "sensor": string | null,
  "dpi_max": integer | null,
  "polling_rate_hz": integer | null,
  "connection": ["wired" | "2.4ghz" | "bluetooth"],
  "battery_hours": number | null,
  "switch_type": string | null,
  "click_system": string | null,
  "software": string | null,
  "onboard_memory": boolean | null,
  "mold_id": string | null,
  "source_title": string | null,
  "confidence": "high" | "medium" | "low",
  "missing_fields": [string],
  "evidence_snippets": [string]
}}

Official page text:
{page_text}
""".strip()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(round(number)) if number is not None else None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "support", "supported", "1"}:
        return True
    if text in {"false", "no", "not supported", "0"}:
        return False
    return None


def _normalize_dimensions(value: Any) -> Dict[str, float | None] | None:
    if isinstance(value, dict):
        return {
            "length": _to_float(value.get("length")),
            "width": _to_float(value.get("width")),
            "height": _to_float(value.get("height")),
        }
    if isinstance(value, str):
        numbers = re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))
        if len(numbers) >= 3:
            return {
                "length": float(numbers[0]),
                "width": float(numbers[1]),
                "height": float(numbers[2]),
            }
    return None


def _normalize_connection(value: Any) -> List[str]:
    raw_items = value if isinstance(value, list) else [value]
    normalized: List[str] = []
    for item in raw_items:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if "wire" in text and "wireless" not in text and "2.4" not in text:
            key = "wired"
        elif "2.4" in text or "lightspeed" in text or "hyperspeed" in text or "wireless" in text:
            key = "2.4ghz"
        elif "bluetooth" in text or "bt" == text:
            key = "bluetooth"
        else:
            key = text
        if key not in normalized:
            normalized.append(key)
    return normalized


def _field_is_missing(record: Dict[str, Any], field: str) -> bool:
    return record.get(field) in (None, "", [])


def _target_phrases(target: Dict[str, Any]) -> List[str]:
    raw_values = [
        _as_text(target.get("input")),
        _as_text(target.get("model")),
        _as_text(target.get("source_title") or target.get("page_title")),
    ]
    phrases: List[str] = []
    stop_words = {
        "wlmouse",
        "gaming",
        "mouse",
        "mice",
        "wireless",
        "wired",
        "magnesium",
        "series",
        "official",
        "product",
    }
    for value in raw_values:
        if not value:
            continue
        phrases.append(value)
        tokens = re.findall(r"[a-z0-9]+", value.lower())
        core = [item for item in tokens if item not in stop_words]
        if len(core) >= 2:
            phrases.append(" ".join(core))
        if len(core) >= 3:
            phrases.append(" ".join(core[-3:]))

    deduped: List[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        normalized = re.sub(r"\s+", " ", phrase).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def _target_windows(text: str, target: Dict[str, Any]) -> List[str]:
    windows: List[str] = []
    for phrase in _target_phrases(target):
        tokens = re.findall(r"[a-z0-9]+", phrase.lower())
        if len(tokens) < 2:
            continue
        pattern = r"\b" + r"\W+".join(re.escape(token) for token in tokens) + r"\b"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = match.start()
            end = min(len(text), match.end() + 900)
            windows.append(text[start:end])
            if len(windows) >= 4:
                return windows
    return windows or [text[:3000]]


def _first_number(patterns: Iterable[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _to_float(match.group(1))
    return None


def _first_int(patterns: Iterable[str], text: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            number = _to_float(match.group(1))
            if number is None:
                continue
            unit = match.group(2).lower() if len(match.groups()) >= 2 and match.group(2) else ""
            if unit.startswith("k"):
                number *= 1000
            return int(round(number))
    return None


def _first_dimensions(text: str) -> Dict[str, float | None] | None:
    patterns = [
        r"(?:size|dimensions?|measurement)\s*[:：-]?\s*(\d+(?:\.\d+)?)\D{1,8}(\d+(?:\.\d+)?)\D{1,8}(\d+(?:\.\d+)?)\s*(?:mm)?",
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*mm",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {
                "length": _to_float(match.group(1)),
                "width": _to_float(match.group(2)),
                "height": _to_float(match.group(3)),
            }
    return None


def _first_sensor(text: str) -> str | None:
    patterns = [
        r"(?:sensor|sensors)\s*[:：-]?\s*([A-Za-z]*\s?\d{3,5}\s?[A-Za-z0-9-]*)",
        r"\b(PAW\s?\d{3,5}\s?[A-Za-z0-9-]*)\b",
        r"\b(Focus\s+Pro\s+\d{2}K(?:\s+Optical\s+Sensor)?(?:\s+Gen-?\d+)?)\b",
        r"\b(HERO\s?\d{1,2}K)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _patch_record_from_official_text(
    record: Dict[str, Any],
    target: Dict[str, Any],
    page_text: str,
) -> None:
    """Patch fields that are explicit in official text but missed by the LLM.

    This is especially useful for official series pages where one page contains
    several variants. The patch only uses a small window around the target model
    phrase, so Mini/Max rows do not bleed into Pro rows.
    """

    snippets = "\n".join(_as_text(item) for item in record.get("evidence_snippets", []) if _as_text(item))
    search_text = f"{snippets}\n{page_text}"
    windows = _target_windows(search_text, target)
    patched: set[str] = set()

    for window in windows:
        if _field_is_missing(record, "weight_g"):
            weight = _first_number([r"\bweight\s*[:：-]?\s*(\d+(?:\.\d+)?)\s*g\b"], window)
            if weight is not None:
                record["weight_g"] = weight
                patched.add("weight_g")

        if _field_is_missing(record, "dimensions_mm"):
            dims = _first_dimensions(window)
            if dims and all(value is not None for value in dims.values()):
                record["dimensions_mm"] = dims
                patched.add("dimensions_mm")

        if _field_is_missing(record, "sensor"):
            sensor = _first_sensor(window)
            if sensor:
                record["sensor"] = sensor
                patched.add("sensor")

        if _field_is_missing(record, "dpi_max"):
            dpi = _first_int(
                [
                    r"\b(?:max\s*)?dpi\s*[:：-]?\s*(\d{4,6})\b()",
                    r"\b(\d{4,6})\s*dpi\b()",
                ],
                window,
            )
            if dpi:
                record["dpi_max"] = dpi
                patched.add("dpi_max")

        if _field_is_missing(record, "polling_rate_hz"):
            polling = _first_int(
                [
                    r"\b(?:polling\s*rate|polling|report\s*rate)\D{0,30}(\d+(?:\.\d+)?)\s*(khz|k|hz)?",
                    r"\b(\d+(?:\.\d+)?)\s*(khz|k)\s*(?:polling|hz|report)?",
                ],
                window,
            )
            if polling:
                record["polling_rate_hz"] = polling
                patched.add("polling_rate_hz")

        if _field_is_missing(record, "connection"):
            connection = _normalize_connection(
                [
                    "2.4ghz" if re.search(r"\b(?:wireless|2\.4g|2\.4\s*ghz)\b", window, flags=re.IGNORECASE) else "",
                    "wired" if re.search(r"\b(?:wired|usb-c|usb)\b", window, flags=re.IGNORECASE) else "",
                    "bluetooth" if re.search(r"\bbluetooth\b", window, flags=re.IGNORECASE) else "",
                ]
            )
            if connection:
                record["connection"] = connection
                patched.add("connection")

        if _field_is_missing(record, "click_system"):
            if re.search(r"\boptical\s+(?:switch|switches|click)\b", window, flags=re.IGNORECASE):
                record["click_system"] = "optical"
                patched.add("click_system")
            elif re.search(r"\bmechanical\s+(?:switch|switches|click)\b", window, flags=re.IGNORECASE):
                record["click_system"] = "mechanical"
                patched.add("click_system")

    if patched:
        snippets_list = record.get("evidence_snippets")
        if not isinstance(snippets_list, list):
            snippets_list = []
        snippets_list.append(
            "Deterministic official-text patch filled: " + ", ".join(sorted(patched))
        )
        record["evidence_snippets"] = [_as_text(item)[:240] for item in snippets_list if _as_text(item)][:6]
        if record.get("confidence") == "low" and {"weight_g", "dimensions_mm", "sensor"} & patched:
            record["confidence"] = "medium"


def _refresh_record_confidence(record: Dict[str, Any]) -> None:
    missing: set[str] = set()
    for field in HARDWARE_FIELDS:
        value = record.get(field)
        if value in (None, "", []):
            missing.add(field)
    for field in ESSENTIAL_FIELDS:
        value = record.get(field)
        if value in (None, "", []):
            missing.add(field)
    record["missing_fields"] = sorted(missing)
    record["field_confidence"] = {
        field: ("pending" if field in missing or record.get(field) in (None, "", []) else "official")
        for field in HARDWARE_FIELDS
    }


def _normalize_record(payload: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "brand": _as_text(payload.get("brand")) or _as_text(target.get("brand")),
        "official_model": _as_text(payload.get("official_model"))
        or _as_text(payload.get("model"))
        or _as_text(target.get("input") or target.get("model")),
        "weight_g": _to_float(payload.get("weight_g")),
        "dimensions_mm": _normalize_dimensions(payload.get("dimensions_mm")),
        "shape": _as_text(payload.get("shape")).lower() or None,
        "shape_detail": _as_text(payload.get("shape_detail")) or None,
        "sensor": _as_text(payload.get("sensor")) or None,
        "dpi_max": _to_int(payload.get("dpi_max")),
        "polling_rate_hz": _to_int(payload.get("polling_rate_hz")),
        "connection": _normalize_connection(payload.get("connection")),
        "battery_hours": _to_float(payload.get("battery_hours")),
        "switch_type": _as_text(payload.get("switch_type")) or None,
        "click_system": _as_text(payload.get("click_system")) or None,
        "software": _as_text(payload.get("software")) or None,
        "onboard_memory": _to_bool(payload.get("onboard_memory")),
        "mold_id": _as_text(payload.get("mold_id")) or None,
        "source_title": _as_text(payload.get("source_title")) or "Official product page",
        "official_url": _as_text(target.get("official_url") or target.get("url")),
        "source_domain": _domain(_as_text(target.get("official_url") or target.get("url"))),
        "extraction_method": "llm_official_page",
    }
    if record["shape"] not in {"symmetrical", "ergonomic"}:
        record["shape"] = None
    target_input = _as_text(target.get("input"))
    if (
        target_input
        and "series" in _as_text(record.get("official_model")).lower()
        and "series" not in target_input.lower()
    ):
        record["official_model"] = target_input

    raw_missing = [
        _as_text(item)
        for item in payload.get("missing_fields", [])
        if _as_text(item)
    ] if isinstance(payload.get("missing_fields"), list) else []
    missing: set[str] = set()
    allowed_missing = set(HARDWARE_FIELDS)
    for item in raw_missing:
        normalized = item.lower().strip()
        if normalized in allowed_missing:
            missing.add(normalized)
            continue
        for field in allowed_missing:
            if field in normalized:
                missing.add(field)
                break
    for field in ESSENTIAL_FIELDS:
        value = record.get(field)
        if value in (None, "", []):
            missing.add(field)
    record["missing_fields"] = sorted(missing)

    confidence = _as_text(payload.get("confidence")).lower()
    record["confidence"] = confidence if confidence in {"high", "medium", "low"} else "low"
    snippets = payload.get("evidence_snippets") if isinstance(payload.get("evidence_snippets"), list) else []
    record["evidence_snippets"] = [_as_text(item)[:240] for item in snippets if _as_text(item)][:5]
    record["field_confidence"] = {
        field: ("pending" if field in missing or record.get(field) in (None, "", []) else "official")
        for field in HARDWARE_FIELDS
    }
    return record


def _extraction_status(record: Dict[str, Any]) -> str:
    missing = {
        _as_text(item)
        for item in record.get("missing_fields", [])
        if _as_text(item)
    }
    missing_essential = missing & set(ESSENTIAL_FIELDS)
    filled_essential = len(ESSENTIAL_FIELDS) - len(missing_essential)
    if len(missing_essential) <= 2:
        return "collected"
    if filled_essential >= 3:
        return "partial_collected"
    return "insufficient_specs"


def _pending_result(target: Dict[str, Any], status: str, note: str) -> Dict[str, Any]:
    url = _as_text(target.get("official_url") or target.get("url"))
    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "brand_hint": _as_text(target.get("brand")),
        "model_hint": _as_text(target.get("model") or target.get("input")),
        "source": _as_text(target.get("source")) or "unknown",
        "source_url": url,
        "source_domain": _domain(url) if url else "",
        "status": status,
        "record": {},
        "missing_fields": list(ESSENTIAL_FIELDS),
        "confidence": "low",
        "field_confidence": {field: "pending" for field in HARDWARE_FIELDS},
        "note": note,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def extract_official_spec(target: Dict[str, Any], *, category: str = "gaming_mouse") -> Dict[str, Any]:
    """Extract one official product spec record from an official URL."""
    mcp_started = time.perf_counter()
    config = _config()
    url = _as_text(target.get("official_url") or target.get("url"))
    if not url:
        return _pending_result(target, "missing_url", "OfficialSpecMCP needs an official URL.")
    if not config.enabled:
        return _pending_result(
            target,
            "mcp_not_connected",
            "Set OFFICIAL_SPEC_USE_LLM=1 and ARK_API_KEY/ARK_EP to enable OfficialSpecMCP.",
        )
    if not config.api_key or not config.model:
        return _pending_result(
            target,
            "mcp_not_configured",
            "OfficialSpecMCP is enabled but ARK_API_KEY or ARK_EP is missing.",
        )

    try:
        page = _fetch_page_text(url, config.timeout_seconds, config.max_chars)
    except HTTPError as exc:
        return {
            **_pending_result(target, "fetch_failed", f"Official page HTTP error: {exc.code}"),
            "mcp_usage": make_mcp_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                status="fetch_failed",
                started_at=mcp_started,
                provider=_domain(url),
                query=url,
                result_count=0,
                uses_llm=False,
                metadata={"http_error": exc.code, "input": _as_text(target.get("input") or target.get("model"))},
            ),
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            **_pending_result(target, "fetch_failed", f"Official page fetch failed: {type(exc).__name__}"),
            "mcp_usage": make_mcp_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                status="fetch_failed",
                started_at=mcp_started,
                provider=_domain(url),
                query=url,
                result_count=0,
                uses_llm=False,
                metadata={"error": type(exc).__name__, "input": _as_text(target.get("input") or target.get("model"))},
            ),
        }

    if not page.get("text"):
        return {
            **_pending_result(target, "fetch_failed", "Official page text was empty."),
            "mcp_usage": make_mcp_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                status="fetch_failed",
                started_at=mcp_started,
                provider=_domain(url),
                query=url,
                result_count=0,
                uses_llm=False,
                metadata={"input": _as_text(target.get("input") or target.get("model"))},
            ),
        }

    try:
        llm = _get_llm(config)
        prompt = _prompt(target, page["text"])
        llm_started = time.perf_counter()
        response = llm.invoke(prompt)
        response_text = _response_to_text(response)
        llm_usage = make_llm_usage_record(
            agent="CollectorAgent",
            tool="official_spec_mcp",
            model=config.model,
            started_at=llm_started,
            prompt_text=prompt,
            response=response,
            response_text=response_text,
            status="success",
            metadata={"input": _as_text(target.get("input") or target.get("model")), "url": url},
        )
        parsed = _parse_json_object(response_text)
    except Exception as exc:
        return {
            **_pending_result(target, "llm_failed", f"OfficialSpecMCP LLM extraction failed: {type(exc).__name__}"),
            "llm_usage": make_llm_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                model=config.model,
                started_at=llm_started if "llm_started" in locals() else mcp_started,
                prompt_text=prompt if "prompt" in locals() else "",
                status="failed",
                error=type(exc).__name__,
                metadata={"input": _as_text(target.get("input") or target.get("model")), "url": url},
            ),
            "mcp_usage": make_mcp_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                status="llm_failed",
                started_at=mcp_started,
                provider=_domain(url),
                query=url,
                result_count=0,
                uses_llm=True,
                metadata={"input": _as_text(target.get("input") or target.get("model"))},
            ),
        }

    if not parsed:
        return {
            **_pending_result(target, "validation_failed", "LLM did not return a parseable JSON object."),
            "llm_usage": llm_usage,
            "mcp_usage": make_mcp_usage_record(
                agent="CollectorAgent",
                tool="official_spec_mcp",
                status="validation_failed",
                started_at=mcp_started,
                provider=_domain(url),
                query=url,
                result_count=0,
                uses_llm=True,
                metadata={"input": _as_text(target.get("input") or target.get("model"))},
            ),
        }

    record = _normalize_record(parsed, target)
    _patch_record_from_official_text(record, target, _as_text(page.get("text")))
    _refresh_record_confidence(record)
    status = _extraction_status(record)
    return {
        "input": _as_text(target.get("input") or target.get("model")),
        "brand_hint": _as_text(target.get("brand")),
        "model_hint": _as_text(target.get("model") or target.get("input")),
        "category": category,
        "source": _as_text(target.get("source")) or "official_url",
        "source_url": url,
        "source_domain": _domain(url),
        "status": status,
        "record": record,
        "missing_fields": record["missing_fields"],
        "confidence": record["confidence"],
        "field_confidence": record["field_confidence"],
        "latency_ms": page.get("latency_ms"),
        "llm_usage": llm_usage,
        "mcp_usage": make_mcp_usage_record(
            agent="CollectorAgent",
            tool="official_spec_mcp",
            status=status,
            started_at=mcp_started,
            provider=_domain(url),
            query=url,
            result_count=1,
            uses_llm=True,
            metadata={"input": _as_text(target.get("input") or target.get("model"))},
        ),
        "note": (
            "Official hardware specs extracted from official page text by LLM."
            if status == "collected"
            else "Official page was read, but extracted specs are incomplete; keep hardware facts pending."
        ),
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def collect_official_specs(
    targets: List[Dict[str, Any]],
    *,
    category: str = "gaming_mouse",
) -> List[Dict[str, Any]]:
    """Extract official/high-credibility specs, trying multiple sources per product.

    Targets are grouped by product (``input``). For each product we extract from
    several candidate URLs (up to ``max_sources_per_product``) but **stop early**
    once the essential hardware fields are covered across the sources seen so far,
    to limit page fetches and LLM calls. Multiple records per product are returned
    and later combined field-by-field by :func:`merge_official_records`.
    """
    config = _config()

    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        key = _as_text(target.get("input") or target.get("model") or target.get("official_url"))
        if not key:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(target)

    results: List[Dict[str, Any]] = []
    products_done = 0
    for key in order:
        if products_done >= config.max_products:
            break
        products_done += 1
        filled_essential: set[str] = set()
        sources_used = 0
        seen_urls: set[str] = set()
        for target in groups[key]:
            if sources_used >= config.max_sources_per_product:
                break
            url = _as_text(target.get("official_url") or target.get("url"))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            result = extract_official_spec(target, category=category)
            sources_used += 1
            results.append(result)
            record = result.get("record") if isinstance(result.get("record"), dict) else {}
            for field in ESSENTIAL_FIELDS:
                if record.get(field) not in (None, "", []):
                    filled_essential.add(field)
            # 提前停：核心字段已凑齐就不再抽这个产品的其它来源。
            if len(filled_essential) >= len(ESSENTIAL_FIELDS):
                break
    return results


def merge_official_records(
    records: List[Dict[str, Any]],
    *,
    category: str = "gaming_mouse",
) -> List[Dict[str, Any]]:
    """Field-level merge of multiple records describing the same product.

    Groups records by ``input`` / official model, orders them by (status,
    confidence), and fills each hardware field from the first source that
    provides it — so gaps on one site are补齐 from another high-credibility site.
    Records per-field provenance in ``field_sources`` and keeps every contributing
    ``source_url``. Returns one merged result-envelope per product.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for result in records:
        if not isinstance(result, dict):
            continue
        record = result.get("record") if isinstance(result.get("record"), dict) else {}
        key = _as_text(result.get("input") or record.get("official_model") or result.get("model_hint"))
        if not key:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(result)

    conf_rank = {"high": 3, "medium": 2, "low": 1}
    status_rank = {"collected": 2, "partial_collected": 1}
    merged_results: List[Dict[str, Any]] = []

    for key in order:
        group = groups[key]
        usable = [
            item
            for item in group
            if item.get("status") in {"collected", "partial_collected"}
            and isinstance(item.get("record"), dict)
        ]
        if not usable:
            merged_results.append(group[0])  # 无可用来源，保留首条 pending 供 UI 展示
            continue
        usable.sort(
            key=lambda item: (
                status_rank.get(item.get("status"), 0),
                conf_rank.get(item.get("confidence"), 0),
            ),
            reverse=True,
        )

        merged_record: Dict[str, Any] = {}
        field_sources: Dict[str, str] = {}
        source_urls: List[str] = []
        source_domains: List[str] = []
        snippets: List[str] = []
        llm_usage: List[Dict[str, Any]] = []
        mcp_usage: List[Dict[str, Any]] = []

        for item in usable:
            record = item.get("record") or {}
            if isinstance(item.get("llm_usage"), dict):
                llm_usage.append(item["llm_usage"])
            usage_item = item.get("mcp_usage")
            if isinstance(usage_item, list):
                mcp_usage.extend(x for x in usage_item if isinstance(x, dict))
            elif isinstance(usage_item, dict):
                mcp_usage.append(usage_item)
            url = _as_text(item.get("source_url") or record.get("official_url"))
            domain = _as_text(item.get("source_domain")) or _domain(url)
            if url and url not in source_urls:
                source_urls.append(url)
                source_domains.append(domain)
            for identity_field in ("brand", "official_model", "source_title"):
                if not merged_record.get(identity_field) and record.get(identity_field):
                    merged_record[identity_field] = record.get(identity_field)
            for field in HARDWARE_FIELDS:
                if merged_record.get(field) in (None, "", []) and record.get(field) not in (None, "", []):
                    merged_record[field] = record.get(field)
                    field_sources[field] = domain or "source"
            for snippet in record.get("evidence_snippets", []) or []:
                text = _as_text(snippet)
                if text and text not in snippets:
                    snippets.append(text)

        merged_record["evidence_snippets"] = snippets[:6]
        _refresh_record_confidence(merged_record)

        primary = usable[0]
        primary_url = source_urls[0] if source_urls else _as_text(primary.get("source_url"))
        status = _extraction_status(merged_record)
        confidence = "high" if status == "collected" else "medium" if status == "partial_collected" else "low"
        merged_record["confidence"] = confidence

        merged_results.append(
            {
                "input": _as_text(primary.get("input") or key),
                "brand_hint": _as_text(primary.get("brand_hint")),
                "model_hint": _as_text(merged_record.get("official_model") or primary.get("model_hint") or key),
                "category": category,
                "source": "official_multi_source" if len(source_urls) > 1 else _as_text(primary.get("source")) or "official_url",
                "source_url": primary_url,
                "source_domain": _domain(primary_url),
                "source_urls": source_urls,
                "source_domains": source_domains,
                "status": status,
                "record": merged_record,
                "missing_fields": merged_record.get("missing_fields", []),
                "confidence": confidence,
                "field_confidence": merged_record.get("field_confidence", {}),
                "field_sources": field_sources,
                "merged_source_count": len(source_urls),
                "llm_usage": llm_usage,
                "mcp_usage": mcp_usage,
                "note": (
                    f"Merged hardware specs from {len(source_urls)} source(s): {', '.join(source_domains)}"
                    if source_urls
                    else "No usable source."
                ),
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return merged_results


def product_from_official_spec(result: Dict[str, Any], *, category: str = "gaming_mouse") -> Dict[str, Any] | None:
    """Convert a collected official spec result into the local product-fact shape."""
    if not isinstance(result, dict) or result.get("status") not in {"collected", "partial_collected"}:
        return None
    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    model = _as_text(record.get("official_model") or result.get("model_hint") or result.get("input"))
    if not model:
        return None
    brand = _as_text(record.get("brand") or result.get("brand_hint"))
    slug_base = f"{brand}-{model}".strip() or model
    slug = re.sub(r"[^a-z0-9]+", "-", slug_base.lower()).strip("-") or "official-product"
    source_url = _as_text(result.get("source_url") or record.get("official_url"))
    source_urls = result.get("source_urls") if isinstance(result.get("source_urls"), list) else []
    if not source_urls and source_url:
        source_urls = [source_url]
    sources = [
        {
            "source_type": "official",
            "publisher": _domain(_as_text(url)),
            "title": record.get("source_title") or model,
            "url": _as_text(url),
        }
        for url in source_urls
        if _as_text(url)
    ]
    product: Dict[str, Any] = {
        "id": f"official-{slug}",
        "brand": brand,
        "model": model,
        "aliases": [_as_text(result.get("input"))] if _as_text(result.get("input")) and _as_text(result.get("input")) != model else [],
        "category": category,
        "data_status": "official_spec_extracted" if result.get("status") == "collected" else "official_spec_partial",
        "official_name_confidence": result.get("confidence") or "medium",
        "official_url": source_url,
        "sources": sources,
        "field_confidence": record.get("field_confidence") or result.get("field_confidence") or {},
        "field_sources": result.get("field_sources") or {},
        "merged_source_count": result.get("merged_source_count") or len(source_urls),
        "updated_at": result.get("collected_at") or datetime.now().date().isoformat(),
    }
    for field in HARDWARE_FIELDS:
        product[field] = record.get(field)
    return product
