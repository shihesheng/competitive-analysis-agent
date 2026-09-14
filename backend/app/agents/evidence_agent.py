"""Evidence Agent - structure raw research into traceable evidence records."""

from __future__ import annotations

import ast
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.schemas.evidence import EvidenceItem


BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
VALID_CREDIBILITIES = {"high", "medium", "low"}
SCHEMA_SOURCE_TYPES = {"official", "news", "review", "report", "ecommerce", "user_review"}


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env")
    load_dotenv()


def _llm_enabled() -> bool:
    value = os.getenv("EVIDENCE_AGENT_USE_LLM", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("ARK_EP", ""),
        api_key=os.getenv("ARK_API_KEY", ""),
        base_url=BASE_URL,
        temperature=0.1,
        timeout=30,
        max_retries=0,
    )


def _response_to_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


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
    cleaned = _strip_json_fence(text)
    yield cleaned

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


def _parse_response(text: str) -> Any:
    for candidate in _json_candidates(text):
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return parsed
    return None


def _extract_object(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str):
        return _extract_object(_parse_response(payload))
    if isinstance(payload, dict):
        for key in ("evidence", "record", "data", "result", "item"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                return nested[0]
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _canonical_source_type(source_type: Any, source_url: str = "", raw_content: str = "") -> str:
    text = _as_text(source_type).lower()
    if text in SCHEMA_SOURCE_TYPES:
        return text

    combined = f"{text} {source_url}".lower()
    if "commerce" in combined or "电商" in combined or "jd.com" in combined or "tmall" in combined:
        return "ecommerce"
    if "user_review" in combined or "user review" in combined or "survey" in combined or "用户" in combined:
        return "user_review"
    if "app_store" in combined or "app store" in combined or "apps.apple" in combined or "review" in combined or "评测" in combined:
        return "review"
    if "financial" in combined or "finance" in combined or "report" in combined or "investor" in combined or "财报" in combined:
        return "report"
    if "news" in combined or "press" in combined or "新闻" in combined:
        return "news"
    if "official" in combined or "官网" in combined or "www." in combined:
        return "official"
    content = raw_content.lower()
    if "财报" in content or "annual report" in content or "financial report" in content:
        return "report"
    return "report"


def _credibility_and_confidence(source_type: str, raw_content: str = "") -> tuple[str, float]:
    combined = f"{source_type} {raw_content}".lower()
    if source_type in {"official", "report"}:
        return "high", 0.85
    if "财报" in combined or "annual report" in combined or "financial report" in combined:
        return "high", 0.85
    if source_type in {"news", "review", "ecommerce"}:
        return "medium", 0.7
    if source_type == "user_review":
        return "medium", 0.6
    return "low", 0.4


def _build_source_title(raw_item: Dict[str, Any], source_type: str) -> str:
    explicit_title = _as_text(
        raw_item.get("source_title")
        or raw_item.get("title")
        or raw_item.get("source")
        or raw_item.get("source_name")
    )
    if explicit_title:
        return explicit_title

    platform = _as_text(raw_item.get("platform")) or "未知平台"
    dimension = _as_text(raw_item.get("dimension") or raw_item.get("related_dimension")) or "综合维度"
    source_names = {
        "official": "官网公开信息",
        "news": "新闻报道",
        "review": "专业评测",
        "report": "财报或行业报告",
        "ecommerce": "电商页面信息",
        "user_review": "用户评论信息",
    }
    return f"{platform}{dimension}{source_names.get(source_type, '公开信息')}"


def _fallback_claim(raw_item: Dict[str, Any]) -> str:
    platform = _as_text(raw_item.get("platform")) or "该平台"
    dimension = _as_text(raw_item.get("dimension") or raw_item.get("related_dimension")) or "相关维度"
    content = _as_text(raw_item.get("content") or raw_item.get("raw_content") or raw_item.get("summary"))
    if not content:
        return f"{platform}在{dimension}上存在可用于竞品分析的公开信息。"

    sentence = re.split(r"[。！？!?]\s*", content, maxsplit=1)[0].strip(" ，,；;")
    if not sentence:
        sentence = content[:80].strip()
    if platform not in sentence:
        sentence = f"{platform}在{dimension}上表现为：{sentence}"
    return sentence[:120]


def _infer_dimension(raw_item: Dict[str, Any], focus_dimensions: List[str]) -> str:
    explicit = _as_text(
        raw_item.get("related_dimension")
        or raw_item.get("relatedDimension")
        or raw_item.get("dimension")
        or raw_item.get("topic")
        or raw_item.get("category")
    )
    if explicit:
        return explicit

    content = _as_text(raw_item.get("raw_content") or raw_item.get("content") or raw_item.get("claim"))
    for dimension in focus_dimensions:
        dimension_text = _as_text(dimension)
        if dimension_text and dimension_text in content:
            return dimension_text

    return focus_dimensions[0] if focus_dimensions else "general"


def _build_prompt(raw_item: Dict[str, Any], focus_dimensions: List[str]) -> str:
    return f"""
你是 EvidenceAgent，负责把 ResearchAgent 的单条原始采集信息结构化为证据。

可信度评分标准：
- high：来自官网、上市公司财报、权威媒体或高可信报告
- medium：来自行业报告、知名媒体、专业评测、电商页面
- low：来自低可信来源、匿名来源或无法确认来源

请只输出一个 JSON 对象，不要输出 Markdown 或解释文字。字段如下：
{{
  "claim": "该证据支持的核心结论，一句话",
  "source_type": "official/news/review/report/ecommerce/user_review",
  "source_title": "来源标题",
  "credibility": "high/medium/low",
  "related_dimension": "对应分析维度"
}}

可选分析维度：
{json.dumps(focus_dimensions, ensure_ascii=False)}

原始信息：
{json.dumps(raw_item, ensure_ascii=False)}
""".strip()


def _structure_with_llm(
    llm: ChatOpenAI | None,
    raw_item: Dict[str, Any],
    focus_dimensions: List[str],
) -> Dict[str, Any]:
    if llm is None:
        return {}

    prompt = _build_prompt(raw_item, focus_dimensions)
    response = llm.invoke(prompt)
    parsed = _parse_response(_response_to_text(response))
    return _extract_object(parsed)


def _coerce_raw_item(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {"raw_content": _as_text(item), "source_type": "report"}


def _normalize_evidence(
    raw_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    evidence_id: str,
    collected_time: str,
    focus_dimensions: List[str],
) -> Dict[str, Any]:
    raw_content = _as_text(raw_item.get("raw_content") or raw_item.get("content") or raw_item.get("summary"))
    source_url = _as_text(
        raw_item.get("source_url")
        or raw_item.get("sourceUrl")
        or raw_item.get("url")
        or raw_item.get("link")
        or llm_item.get("source_url")
    )
    source_type = _canonical_source_type(
        llm_item.get("source_type") or llm_item.get("sourceType") or raw_item.get("source_type"),
        source_url,
        raw_content,
    )

    credibility = _as_text(llm_item.get("credibility")).lower()
    inferred_credibility, confidence_score = _credibility_and_confidence(source_type, raw_content)
    if credibility not in VALID_CREDIBILITIES:
        credibility = inferred_credibility
    elif credibility == "high":
        confidence_score = max(confidence_score, 0.85)
    elif credibility == "low":
        confidence_score = min(confidence_score, 0.4)

    related_dimension = _as_text(
        llm_item.get("related_dimension")
        or llm_item.get("relatedDimension")
    ) or _infer_dimension(raw_item, focus_dimensions)

    evidence = EvidenceItem(
        evidence_id=evidence_id,
        platform=_as_text(llm_item.get("platform") or raw_item.get("platform")) or "未知平台",
        claim=_as_text(llm_item.get("claim") or llm_item.get("core_claim")) or _fallback_claim(raw_item),
        source_type=source_type,
        source_title=_as_text(llm_item.get("source_title") or llm_item.get("sourceTitle"))
        or _build_source_title(raw_item, source_type),
        source_url=source_url or _as_text(raw_item.get("source")) or "manual://unknown",
        publish_time=_as_text(
            raw_item.get("publish_time")
            or raw_item.get("publishTime")
            or raw_item.get("date")
            or llm_item.get("publish_time")
        )
        or None,
        collected_time=_as_text(raw_item.get("collected_time")) or collected_time,
        credibility=credibility,
        related_dimension=related_dimension,
        raw_content=raw_content,
        confidence_score=confidence_score,
    ).model_dump()

    evidence.update(
        {
            "dimension": evidence["related_dimension"],
            "content": evidence["raw_content"],
            "summary": evidence["claim"],
            "source": evidence["source_title"],
            "used_by_agent": "EvidenceAgent",
        }
    )
    return evidence


def _append_trace(state: dict, evidence_count: int) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "EvidenceAgent",
            "status": "success",
            "input_summary": "normalize available evidence and pending MCP statuses",
            "output_summary": f"structured {evidence_count} evidence items",
            "pending_fields": state.get("pending_dimensions", []),
            "error": None,
        }
    )


def evidence_agent(state: dict) -> Dict[str, Any]:
    """Convert raw_research into EvidenceItem-compatible records."""
    _load_env()

    # 产品对比模式：证据已是结构化硬规格事实，直接沿用，不再用 LLM 二次抽取（避免改写数值/维度）。
    if state.get("product_compare_mode"):
        evidence_list = [item for item in state.get("evidence_list", []) if isinstance(item, dict)]
        local_count = len([item for item in evidence_list if not item.get("pending_research")])
        pending_count = len([item for item in evidence_list if item.get("pending_research")])
        evidence_status = {
            "local_json": {
                "status": "available",
                "count": local_count,
                "description": "Stable hardware facts loaded from the local product catalog.",
            },
            "official_pending": state.get("official_spec_status", []),
            "review_pending": state.get("review_intel_status", {}),
            "price_pending": state.get("price_status", {}),
            "pending_evidence_count": pending_count,
        }
        next_state = {
            **state,
            "current_agent": "EvidenceAgent",
            "evidence_list": evidence_list,
            "evidence_status": evidence_status,
        }
        _append_trace(next_state, len(evidence_list))
        print(f"[EvidenceAgent] 产品对比模式：沿用注入的 {len(evidence_list)} 条结构化产品证据")
        return next_state

    raw_research = state.get("raw_research", [])
    competitors = state.get("competitors", [])
    focus_dimensions = state.get("focus_dimensions", [])
    del competitors  # Kept as an explicit input for future competitor-aware evidence rules.

    evidence_list: List[Dict[str, Any]] = []
    collected_time = datetime.now().isoformat(timespec="seconds")

    llm: ChatOpenAI | None = None
    if _llm_enabled() and os.getenv("ARK_EP") and os.getenv("ARK_API_KEY"):
        try:
            llm = _get_llm()
        except Exception:
            llm = None

    for index, item in enumerate(raw_research, start=1):
        raw_item = _coerce_raw_item(item)
        evidence_id = f"EV{index:03d}"
        try:
            llm_item = _structure_with_llm(llm, raw_item, focus_dimensions)
        except Exception:
            llm_item = {}

        evidence_list.append(
            _normalize_evidence(
                raw_item=raw_item,
                llm_item=llm_item,
                evidence_id=evidence_id,
                collected_time=collected_time,
                focus_dimensions=focus_dimensions,
            )
        )

    next_state = {
        **state,
        "current_agent": "EvidenceAgent",
        "evidence_list": evidence_list,
    }
    _append_trace(next_state, len(evidence_list))

    print(f"[EvidenceAgent] 处理完成，共 {len(evidence_list)} 条证据")
    return next_state
