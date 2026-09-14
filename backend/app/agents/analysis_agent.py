"""Analysis Agent for the product-focused DAG.

This node is the analyst role in the seven-agent workflow. It consumes structured
evidence from CollectorAgent/EvidenceAgent and produces:

- hardware fact comparison,
- conservative experience/business placeholders when MCP evidence is missing,
- product baseline scores,
- evidence-bound claims,
- risk flags.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from app.services.product_compare_service import build_product_matrix, comparative_claims
from app.services.product_scoring_service import build_scoreboard


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _append_trace(
    state: dict,
    *,
    status: str,
    input_summary: str,
    output_summary: str,
    started_at: float,
    claims_added: int = 0,
    risk_count: int = 0,
    substeps: List[Dict[str, Any]] | None = None,
) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "AnalysisAgent",
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "claims_added": claims_added,
            "risk_count": risk_count,
            "substeps": substeps or [],
            "duration_ms": int((time.time() - started_at) * 1000),
            "error": None,
        }
    )


def _business_matrix_from_facts(product_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    dimensions: Dict[str, Dict[str, Dict[str, Any]]] = {
        "software_driver_ecosystem": {},
        "market_value": {},
        "brand_reputation": {},
    }
    for fact in product_facts:
        if not isinstance(fact, dict):
            continue
        model = _as_text(fact.get("model") or fact.get("product_id")) or "unknown"
        specs = fact.get("specs") if isinstance(fact.get("specs"), dict) else {}
        software = _as_text(specs.get("software")) or "unknown"
        onboard = specs.get("onboard_memory")
        first_evidence = fact.get("evidence_ids", [])[:1] if isinstance(fact.get("evidence_ids"), list) else []
        dimensions["software_driver_ecosystem"][model] = {
            "score": 3,
            "summary": f"Official software field: {software}; onboard_memory={onboard}.",
            "analysis": (
                "Conservative software-ecosystem note based only on local official facts. "
                "Driver stability and reputation require review/user feedback MCP data."
            ),
            "evidence_ids": first_evidence,
            "confidence_score": 0.55,
            "data_status": "limited_official_fact",
        }
        dimensions["market_value"][model] = {
            "score": 0,
            "summary": "Realtime price MCP is not connected.",
            "analysis": "Market value and price-performance cannot be concluded without realtime price data.",
            "evidence_ids": [],
            "confidence_score": 0.0,
            "data_status": "evidence_missing",
        }
        dimensions["brand_reputation"][model] = {
            "score": 0,
            "summary": "Brand/community reputation MCP is not connected.",
            "analysis": "Brand reputation and driver reputation require user review or creator review evidence.",
            "evidence_ids": [],
            "confidence_score": 0.0,
            "data_status": "evidence_missing",
        }
    return {
        "dimensions": dimensions,
        "mode": "gaming_mouse_product_compare_conservative",
    }


def _experience_analysis(state: dict) -> Dict[str, Any]:
    review_status = state.get("review_intel_status", {})
    records = [item for item in state.get("review_intel_records", []) if isinstance(item, dict)]
    products: Dict[str, Dict[str, Any]] = {}
    for record in records:
        model = _as_text(record.get("model") or record.get("input")) or "unknown"
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        if not signals:
            continue
        products[model] = {
            "status": record.get("status"),
            "confidence_level": record.get("confidence_level"),
            "signals": signals,
            "fit_recommendations": record.get("fit_recommendations", []),
            "common_complaints": record.get("common_complaints", []),
            "limitations": record.get("limitations", []),
        }
    if products:
        pending_review_dimensions = []
        if isinstance(review_status, dict):
            pending_review_dimensions = list(review_status.get("review_dimensions_pending", []) or [])
        return {
            "status": "available" if not pending_review_dimensions else "partial",
            "products": products,
            "pending_dimensions": pending_review_dimensions,
            "reason": "ReviewIntelMCP provided evidence-backed experience signals; scenario recommendations may use these signals with confidence labels.",
        }
    pending = []
    if isinstance(review_status, dict):
        pending = list(review_status.get("review_dimensions_pending", []) or [])
    if not pending:
        pending = [
            "grip_feel",
            "hand_size_fit",
            "game_type_fit",
            "long_term_reliability",
            "driver_reputation",
            "community_sentiment",
        ]
    return {
        "status": "insufficient_evidence",
        "pending_dimensions": pending,
        "cannot_conclude_fields": [
            "grip_fit",
            "hand_size_fit",
            "game_type_fit",
            "suitable_people",
            "suitable_games",
            "long_term_reliability",
        ],
        "reason": "Review-intelligence MCP has not provided real user/creator review evidence.",
    }


def _review_claims(state: dict, start_index: int) -> List[Dict[str, Any]]:
    records = [item for item in state.get("review_intel_records", []) if isinstance(item, dict)]
    claims: List[Dict[str, Any]] = []
    index = start_index
    confidence_score = {"high": 0.86, "medium": 0.7, "low": 0.48}
    for record in records:
        model = _as_text(record.get("model") or record.get("input")) or "unknown product"
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        for dimension, signal in signals.items():
            if not isinstance(signal, dict):
                continue
            evidence_ids = [
                _as_text(item)
                for item in signal.get("evidence_ids", [])
                if _as_text(item)
            ] if isinstance(signal.get("evidence_ids"), list) else []
            if not evidence_ids:
                continue
            summary = _as_text(signal.get("summary"))
            if not summary:
                continue
            confidence = _as_text(signal.get("confidence")).lower() or "low"
            index += 1
            claims.append(
                {
                    "claim_id": f"RCL{index:03d}",
                    "content": f"{model} review-backed {dimension}: {summary}",
                    "dimension": dimension,
                    "related_platforms": [model],
                    "evidence_ids": evidence_ids,
                    "confidence_score": confidence_score.get(confidence, 0.48),
                    "generated_by": "AnalysisAgent",
                    "support_level": signal.get("support_level"),
                }
            )
    return claims


def _business_analysis() -> Dict[str, Any]:
    return {
        "status": "limited_official_fact",
        "software_driver_ecosystem": "Only official software and onboard-memory fields are used.",
        "market_value": "pending_realtime_price",
        "brand_reputation": "pending_review_intel",
    }


def _risk_flags_from_state(state: dict, selected: List[Dict[str, Any]], evidence_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    unresolved = [_as_text(item) for item in state.get("unresolved_products", []) if _as_text(item)]
    if unresolved:
        risks.append(
            {
                "risk_type": "evidence_gap",
                "description": (
                    f"{'、'.join(unresolved)} 未命中本地产品事实库，官方型号与硬件规格需要搜索/官网 MCP 补齐。"
                ),
                "severity": "medium",
                "related_platforms": unresolved,
                "related_dimensions": ["product_resolution", "official_specs", "hardware_specs"],
            }
        )

    if len(selected) < 2:
        risks.append(
            {
                "risk_type": "evidence_gap",
                "description": "当前不足两款已解析产品，不能输出硬件胜负或最终推荐。",
                "severity": "high",
                "related_platforms": unresolved,
                "related_dimensions": ["product_resolution", "hardware_specs"],
            }
        )

    pending_data = [item for item in state.get("pending_data", []) if isinstance(item, dict)]
    for item in pending_data:
        agent = _as_text(item.get("agent")) or "pending_data"
        fields = [_as_text(field) for field in item.get("fields", []) if _as_text(field)] if isinstance(item.get("fields"), list) else []
        note = _as_text(item.get("note"))
        risk_type = "data_timeliness" if "price" in agent.lower() else "evidence_gap"
        risks.append(
            {
                "risk_type": risk_type,
                "description": note or f"{agent} 仍有待补齐字段：{'、'.join(fields) if fields else '待采集数据'}。",
                "severity": "medium",
                "related_platforms": [_as_text(item.get("agent"))] if _as_text(item.get("agent")) else [],
                "related_dimensions": fields,
            }
        )

    if not evidence_list and not unresolved:
        risks.append(
            {
                "risk_type": "evidence_gap",
                "description": "当前没有可用 evidence，报告只能生成有限占位结构。",
                "severity": "high",
                "related_platforms": [],
                "related_dimensions": ["evidence"],
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for risk in risks:
        key = (_as_text(risk.get("risk_type")), _as_text(risk.get("description")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped


def _price_claims(state: dict, start_index: int) -> List[Dict[str, Any]]:
    """把实时价格做成 evidence 绑定的 claim，每产品最多两条：官方价 + 电商价，分别链接各自证据。

    定性表述、不写死具体数字（避免数值忠实性误判，价格数值由价格证据本身承载）。
    官方价 -> 高可信证据 -> 校验时「支撑」；电商价 / 被拦截 -> 低可信证据 -> 「弱支撑」（按事实）。
    """
    records = [item for item in state.get("price_records", []) if isinstance(item, dict)]
    claims: List[Dict[str, Any]] = []
    index = start_index

    def add(content: str, evidence_id: str, model: str, score: float) -> None:
        nonlocal index
        index += 1
        claims.append(
            {
                "claim_id": f"PCL{index:03d}",
                "content": content,
                "dimension": "实时价格",
                "related_platforms": [model],
                "evidence_ids": [evidence_id],
                "confidence_score": score,
                "generated_by": "AnalysisAgent",
            }
        )

    for record in records:
        model = _as_text(record.get("model") or record.get("input")) or "该产品"
        official_id = _as_text(record.get("official_evidence_id"))
        ecom_id = _as_text(record.get("ecom_evidence_id"))
        pending_id = _as_text(record.get("evidence_id"))
        if official_id:
            add(f"{model} 官方价来自官方商店（高可信），价格事实可用于对比。", official_id, model, 0.9)
        if ecom_id:
            add(f"{model} 电商价来自第三方电商 / 搜索（低可信），可参与对比但不作为最终性价比依据。", ecom_id, model, 0.5)
        if not official_id and not ecom_id and pending_id:
            add(f"{model} 未抽到可靠实时价格，官方页可能被反爬拦截。", pending_id, model, 0.4)
    return claims


def _product_compare_analysis(state: dict, started: float) -> Dict[str, Any]:
    selected = [item for item in state.get("selected_products", []) if isinstance(item, dict)]
    evidence_list = [item for item in state.get("evidence_list", []) if isinstance(item, dict)]
    dimensions = [_as_text(item) for item in state.get("focus_dimensions", []) if _as_text(item)]
    existing_claims = [item for item in state.get("claims", []) if isinstance(item, dict)]

    product_matrix = build_product_matrix(selected, evidence_list, dimensions)
    comp_claims = comparative_claims(selected, evidence_list, len(existing_claims))
    for claim in comp_claims:
        if isinstance(claim, dict):
            claim["generated_by"] = "AnalysisAgent"

    price_claims = _price_claims(state, len(existing_claims) + len(comp_claims))
    review_claims = _review_claims(state, len(existing_claims) + len(comp_claims) + len(price_claims))
    experience_analysis = _experience_analysis(state)

    product_scores = build_scoreboard(selected)
    hardware_analysis = {
        "status": "complete",
        "scope": "hardware_facts_only",
        "hardware_diff_summary": [
            claim.get("content")
            for claim in comp_claims
            if isinstance(claim, dict) and claim.get("content")
        ],
        "hardware_score": {
            score.get("model"): score.get("hardware_score")
            for score in product_scores.get("products", [])
            if isinstance(score, dict)
        },
        "hardware_advantages": product_scores.get("verdicts", {}),
        "hardware_tradeoffs": [
            "Experience fit uses ReviewIntelMCP only when review-backed evidence IDs exist; otherwise it remains pending."
        ],
        "evidence_ids_used": sorted(
            {
                evidence_id
                for claim in comp_claims
                if isinstance(claim, dict)
                for evidence_id in claim.get("evidence_ids", [])
                if evidence_id
            }
        ),
    }

    business_matrix = _business_matrix_from_facts(
        [item for item in state.get("product_facts", []) if isinstance(item, dict)]
    )
    risk_flags = _risk_flags_from_state(state, selected, evidence_list)

    intermediate = {
        **state,
        "current_agent": "AnalysisAgent",
        "product_matrix": product_matrix,
        "business_matrix": business_matrix,
        "claims": [*existing_claims, *comp_claims, *price_claims, *review_claims],
        "product_scores": product_scores,
        "hardware_analysis": hardware_analysis,
        "experience_analysis": experience_analysis,
        "business_analysis": _business_analysis(),
        # AnalysisAgent only produces evidence-bound facts and tradeoffs. It does
        # not emit product scores; scenario recommendations are ReportAgent's job.
        "score_flow": {},
        "risk_flags": risk_flags,
    }

    context_summary = dict(state.get("context_summary", {}))
    context_summary["AnalysisAgent"] = {
        "mode": "gaming_mouse_product_compare",
        "selected_product_count": len(selected),
        "claim_count": len(comp_claims) + len(price_claims) + len(review_claims),
        "risk_count": len(risk_flags),
        "experience_status": experience_analysis.get("status"),
        "business_status": "limited_official_fact",
    }

    next_state = {
        **intermediate,
        "current_agent": "AnalysisAgent",
        "context_summary": context_summary,
        "agent_contributions": [
            {
                "agent": "AnalysisAgent",
                "contribution": "Compared hardware facts and added review/price claims only when MCP evidence IDs exist.",
                "status": "applied",
            }
        ],
    }
    _append_trace(
        next_state,
        status="success",
        input_summary=f"analyzed {len(selected)} resolved products and {len(evidence_list)} evidence items",
        output_summary=(
            f"generated hardware comparison, {len(comp_claims)} evidence-bound claims, "
            f"{len(review_claims)} review-backed claims, {len(price_claims)} price claims, "
            f"and {len(risk_flags)} risk flags"
        ),
        claims_added=len(comp_claims) + len(price_claims) + len(review_claims),
        risk_count=len(risk_flags),
        started_at=started,
        substeps=[
            {"name": "HardwareFacts", "status": "complete"},
            {"name": "ExperienceFit", "status": experience_analysis.get("status"), "count": len(review_claims)},
            {"name": "DriverAndBusiness", "status": "limited_official_fact"},
            {"name": "RiskDetection", "status": "complete", "count": len(risk_flags)},
        ],
    )
    return next_state


def analysis_agent(state: dict) -> Dict[str, Any]:
    """Generate analysis matrices, claims, scores, and risks."""
    started = time.time()
    return _product_compare_analysis({**state, "product_compare_mode": True}, started)
