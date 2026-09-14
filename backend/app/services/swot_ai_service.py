"""SWOT AI interpretation and human-feedback normalization.

This service is intentionally small and API-oriented: it reads the already
structured workflow state (evidence, claims, risks, specs), asks an LLM for a
concise SWOT when configured, and falls back to deterministic summaries when the
LLM is unavailable. Human feedback is stored as evidence rather than directly
overwriting the report.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from app.services.context_manager import select_evidence_context
from app.services.observability_service import make_llm_usage_record


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env")
    load_dotenv()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _compact_product_name(item: Dict[str, Any]) -> str:
    return (
        _as_text(item.get("model"))
        or _as_text(item.get("official_model"))
        or _as_text(item.get("product_id"))
        or _as_text(item.get("input"))
        or "未知产品"
    )


def _json_loads(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    return data if isinstance(data, dict) else {}


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


def _llm_config() -> Dict[str, Any]:
    _load_env()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    api_key = (
        os.getenv("ANALYSIS_AI_API_KEY", "").strip()
        or os.getenv("SWOT_AI_API_KEY", "").strip()
        or deepseek_key
        or os.getenv("PRICE_API_KEY", "").strip()
        or os.getenv("OFFICIAL_SPEC_API_KEY", "").strip()
    )
    model = (
        os.getenv("ANALYSIS_AI_MODEL", "").strip()
        or os.getenv("SWOT_AI_MODEL", "").strip()
        or os.getenv("DEEPSEEK_MODEL", "").strip()
        or os.getenv("PRICE_MODEL", "").strip()
        or os.getenv("OFFICIAL_SPEC_MODEL", "").strip()
        or ("deepseek-chat" if deepseek_key else "")
    )
    base_url = (
        os.getenv("ANALYSIS_AI_BASE_URL", "").strip()
        or os.getenv("SWOT_AI_BASE_URL", "").strip()
        or os.getenv("DEEPSEEK_BASE_URL", "").strip()
        or os.getenv("PRICE_BASE_URL", "").strip()
        or os.getenv("ARK_BASE_URL", "").strip()
        or ("https://api.deepseek.com" if deepseek_key else "")
    )
    enabled = os.getenv("ANALYSIS_AI_ENABLED", os.getenv("SWOT_AI_ENABLED", "1")).strip().lower()
    return {
        "enabled": enabled in {"1", "true", "yes", "on"} and bool(api_key and model),
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
    }


def _get_llm(config: Dict[str, Any]) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=0.2,
        timeout=60,
        max_retries=0,
    )


def _prompt(state: Dict[str, Any], evidence_context: List[Dict[str, Any]], context_summary: Dict[str, Any]) -> str:
    products = [_compact_product_name(item) for item in _as_list(state.get("selected_products")) if isinstance(item, dict)]
    claims = [
        {
            "claim_id": _as_text(item.get("claim_id")),
            "content": _as_text(item.get("content")),
            "dimension": _as_text(item.get("dimension")),
            "evidence_ids": _as_list(item.get("evidence_ids")),
            "generated_by": _as_text(item.get("generated_by")),
        }
        for item in _as_list(state.get("claims"))
        if isinstance(item, dict)
    ][:18]
    risks = [
        {
            "risk_type": _as_text(item.get("risk_type")),
            "description": _as_text(item.get("description")),
            "severity": _as_text(item.get("severity")),
        }
        for item in _as_list(state.get("risk_flags"))
        if isinstance(item, dict)
    ][:10]
    payload = {
        "products": products,
        "claims": claims,
        "evidence_context": evidence_context,
        "risk_flags": risks,
        "quality_result": state.get("quality_result", {}),
        "context_summary": context_summary,
        "human_feedback": state.get("human_feedback", []),
    }
    return f"""
You are the AnalysisAgent AI interpretation step for a gaming-mouse competitor analysis system.
Use only the structured input below. Do not invent missing review, price, or hardware facts.

Return JSON only, in Simplified Chinese, with this exact shape:
{{
  "status": "available",
  "overall_reading": "2-4 sentences, cautious and evidence-bound",
  "swot": {{
    "strengths": [{{"point": "...", "product": "...", "evidence_ids": ["EV001"], "confidence": "high|medium|low"}}],
    "weaknesses": [{{"point": "...", "product": "...", "evidence_ids": ["EV001"], "confidence": "high|medium|low"}}],
    "opportunities": [{{"point": "...", "product": "...", "evidence_ids": [], "confidence": "low"}}],
    "threats": [{{"point": "...", "product": "...", "evidence_ids": [], "confidence": "low"}}]
  }},
  "data_gaps": ["missing or weak dimensions"],
  "human_feedback_questions": ["short prompt user could answer to improve the report"],
  "used_claim_ids": ["PCL001"],
  "used_evidence_ids": ["EV001"]
}}

Rules:
- SWOT is not a final winner verdict. It should explain scenario tradeoffs.
- If a point relies on user feedback, say it requires VerificationAgent validation.
- Every factual point should include evidence_ids when available.
- If data is unclear, put it in data_gaps, not in strengths.

Structured input:
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def _fallback_swot(state: Dict[str, Any], evidence_context: List[Dict[str, Any]], context_summary: Dict[str, Any]) -> Dict[str, Any]:
    claims = [item for item in _as_list(state.get("claims")) if isinstance(item, dict)]
    risks = [item for item in _as_list(state.get("risk_flags")) if isinstance(item, dict)]
    products = [_compact_product_name(item) for item in _as_list(state.get("selected_products")) if isinstance(item, dict)]
    strengths = []
    weaknesses = []
    used_claim_ids: List[str] = []
    used_evidence_ids: List[str] = []

    for claim in claims[:6]:
        evidence_ids = [_as_text(item) for item in _as_list(claim.get("evidence_ids")) if _as_text(item)]
        point = _as_text(claim.get("content"))
        if not point:
            continue
        strengths.append(
            {
                "point": point,
                "product": ", ".join([_as_text(p) for p in _as_list(claim.get("related_platforms")) if _as_text(p)]) or "相关产品",
                "evidence_ids": evidence_ids,
                "confidence": "medium" if evidence_ids else "low",
            }
        )
        if _as_text(claim.get("claim_id")):
            used_claim_ids.append(_as_text(claim.get("claim_id")))
        used_evidence_ids.extend(evidence_ids)

    for risk in risks[:4]:
        weaknesses.append(
            {
                "point": _as_text(risk.get("description")) or _as_text(risk.get("risk_type")),
                "product": ", ".join([_as_text(p) for p in _as_list(risk.get("related_platforms")) if _as_text(p)]) or "整体分析",
                "evidence_ids": [],
                "confidence": "low" if _as_text(risk.get("severity")) == "low" else "medium",
            }
        )

    data_gaps = [
        _as_text(item.get("description")) or _as_text(item.get("risk_type"))
        for item in risks
        if isinstance(item, dict) and _as_text(item.get("description") or item.get("risk_type"))
    ][:5]
    if not data_gaps:
        data_gaps = ["部分体验、价格或长期可靠性结论仍需真实测评/评论数据补强。"]

    return {
        "status": "fallback",
        "model": "rule_fallback",
        "overall_reading": (
            f"当前已基于 {len(evidence_context)} 条裁剪后的证据和 {len(claims)} 条结构化结论生成保守 SWOT。"
            "没有证据支撑的体验结论不会被直接写成最终推荐。"
        ),
        "swot": {
            "strengths": strengths[:4] or [{"point": "已有本地/官网硬件事实可进入对比。", "product": "整体分析", "evidence_ids": [], "confidence": "medium"}],
            "weaknesses": weaknesses[:4] or [{"point": "体验口碑、价格和长期可靠性仍存在数据缺口。", "product": "整体分析", "evidence_ids": [], "confidence": "medium"}],
            "opportunities": [
                {
                    "point": "补充用户评价、博主测评和价格源后，可以把场景推荐从硬件倾向升级为体验证据支撑。",
                    "product": "整体分析",
                    "evidence_ids": [],
                    "confidence": "low",
                }
            ],
            "threats": [
                {
                    "point": "如果外部来源被反爬或只有低可信搜索结果，QualityAgent 会降低报告可信度。",
                    "product": "整体分析",
                    "evidence_ids": [],
                    "confidence": "low",
                }
            ],
        },
        "data_gaps": data_gaps,
        "human_feedback_questions": [
            "你是否有真实使用体验可以补充到握法、FPS 表现或驱动稳定性？",
            "这条人工补充是否来自实测、长期使用，还是个人观点？",
        ],
        "used_claim_ids": sorted(set(used_claim_ids)),
        "used_evidence_ids": sorted(set(used_evidence_ids)),
        "context_summary": context_summary,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _validate_swot_grounding(data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the SWOT block honest and consistent with the project's traceability claim.

    The LLM self-reports evidence/claim ids; nothing guarantees they exist. Here we drop
    any cited id that is not in the real evidence_list / claims, mark every SWOT point as
    grounded only when it still cites a real evidence id, downgrade ungrounded points that
    claimed "high" confidence, and recompute the top-level used_* ids from the real set.
    """
    real_evidence_ids = {
        _as_text(ev.get("evidence_id"))
        for ev in _as_list(state.get("evidence_list"))
        if isinstance(ev, dict) and _as_text(ev.get("evidence_id"))
    }
    real_claim_ids = {
        _as_text(c.get("claim_id"))
        for c in _as_list(state.get("claims"))
        if isinstance(c, dict) and _as_text(c.get("claim_id"))
    }
    swot = data.get("swot") if isinstance(data.get("swot"), dict) else {}
    used_ev: set[str] = set()
    dropped_ev: set[str] = set()
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        points = swot.get(key) if isinstance(swot.get(key), list) else []
        clean: List[Dict[str, Any]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            cited = [_as_text(x) for x in _as_list(point.get("evidence_ids")) if _as_text(x)]
            valid = [x for x in cited if x in real_evidence_ids]
            dropped_ev.update(x for x in cited if x not in real_evidence_ids)
            point["evidence_ids"] = valid
            point["grounded"] = bool(valid)
            # 没有真实证据绑定的 point 不允许标 high
            if not valid and _as_text(point.get("confidence")).lower() == "high":
                point["confidence"] = "low"
            used_ev.update(valid)
            clean.append(point)
        if isinstance(swot.get(key), list):
            swot[key] = clean
    data["swot"] = swot
    data["used_evidence_ids"] = sorted(used_ev)
    data["used_claim_ids"] = sorted(
        x for x in (_as_text(i) for i in _as_list(data.get("used_claim_ids"))) if x in real_claim_ids
    )
    if dropped_ev:
        data["dropped_evidence_ids"] = sorted(dropped_ev)
        gaps = data.get("data_gaps") if isinstance(data.get("data_gaps"), list) else []
        gaps.append(f"已剔除 {len(dropped_ev)} 个模型引用但实际不存在的证据编号，未计入溯源。")
        data["data_gaps"] = gaps
    return data


def generate_swot_interpretation(state: Dict[str, Any]) -> Dict[str, Any]:
    evidence_context, context_summary = select_evidence_context(
        "AnalysisAgent.SWOT",
        [item for item in _as_list(state.get("evidence_list")) if isinstance(item, dict)],
        max_items=18,
        max_per_dimension=4,
        max_content_chars=360,
    )
    config = _llm_config()
    if not config["enabled"]:
        return _validate_swot_grounding(_fallback_swot(state, evidence_context, context_summary), state)

    try:
        llm = _get_llm(config)
        prompt = _prompt(state, evidence_context, context_summary)
        llm_started = time.perf_counter()
        response = llm.invoke(prompt)
        response_text = _response_to_text(response)
        usage_record = make_llm_usage_record(
            agent="AnalysisAgent",
            tool="swot_ai",
            model=config["model"],
            started_at=llm_started,
            prompt_text=prompt,
            response=response,
            response_text=response_text,
            status="success",
            metadata={"evidence_count": len(evidence_context)},
        )
        data = _json_loads(response_text)
        if not data:
            raise ValueError("empty SWOT JSON")
        state.setdefault("llm_usage", []).append(usage_record)
        data.setdefault("status", "available")
        data["model"] = config["model"]
        data["context_summary"] = context_summary
        data["generated_at"] = datetime.now().isoformat(timespec="seconds")
        return _validate_swot_grounding(data, state)
    except Exception as exc:
        state.setdefault("llm_usage", []).append(
            make_llm_usage_record(
                agent="AnalysisAgent",
                tool="swot_ai",
                model=config.get("model", ""),
                started_at=llm_started if "llm_started" in locals() else time.perf_counter(),
                prompt_text=prompt if "prompt" in locals() else "",
                status="failed",
                error=type(exc).__name__,
                metadata={"evidence_count": len(evidence_context)},
            )
        )
        fallback = _fallback_swot(state, evidence_context, context_summary)
        fallback["status"] = "fallback_llm_failed"
        fallback["llm_error"] = type(exc).__name__
        return _validate_swot_grounding(fallback, state)


def build_human_feedback_patch(state: Dict[str, Any], message: str, *, product: str = "", dimension: str = "") -> Dict[str, Any]:
    text = _as_text(message)
    if not text:
        raise ValueError("empty feedback")

    evidence_list = [item for item in _as_list(state.get("evidence_list")) if isinstance(item, dict)]
    claims = [item for item in _as_list(state.get("claims")) if isinstance(item, dict)]
    feedback = [item for item in _as_list(state.get("human_feedback")) if isinstance(item, dict)]
    next_index = len(feedback) + 1
    evidence_id = f"HF{next_index:03d}"
    claim_id = f"HCL{next_index:03d}"
    product_name = _as_text(product) or "用户指定产品/场景"
    dimension_name = _as_text(dimension) or "human_feedback"
    now = datetime.now().isoformat(timespec="seconds")

    feedback_record = {
        "feedback_id": evidence_id,
        "type": "human_feedback",
        "product": product_name,
        "dimension": dimension_name,
        "message": text,
        "status": "pending_verification",
        "needs_verification": True,
        "created_at": now,
    }
    evidence = {
        "evidence_id": evidence_id,
        "platform": product_name,
        "claim": text,
        "source_type": "human_feedback",
        "source_title": "人工反馈 / 现场修正",
        "source_url": "",
        "publish_time": now,
        "collected_time": now,
        # 人工输入默认低可信、待验证：不与外部证据无关地自证为事实。
        "credibility": "low",
        "data_status": "weak_support",
        "related_dimension": dimension_name,
        "raw_content": text,
        "confidence_score": 0.4,
        "human_provided": True,
        "needs_verification": True,
    }
    claim = {
        "claim_id": claim_id,
        "content": f"人工补充（待验证）：{text}",
        "dimension": dimension_name,
        "related_platforms": [product_name],
        "evidence_ids": [evidence_id],
        "confidence_score": 0.4,
        "generated_by": "HumanFeedback",
        "needs_verification": True,
    }
    assistant_reply = (
        "已把这条补充作为人工 evidence 写入任务，默认标记为低可信、待验证。VerificationAgent 会把它"
        "作为人工输入处理：只有当至少有一条非人工证据同向支撑时才升为支撑，否则按"
        "「弱支撑 / 待验证」披露，不直接当作最终事实，也不会因此抬高质量分。"
    )
    return {
        "human_feedback": [*feedback, feedback_record],
        "evidence_list": [*evidence_list, evidence],
        "claims": [*claims, claim],
        "assistant_reply": assistant_reply,
        "feedback_record": feedback_record,
        "evidence": evidence,
        "claim": claim,
    }
