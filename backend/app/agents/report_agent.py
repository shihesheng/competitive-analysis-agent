"""Report Agent for the gaming-mouse professional schema.

This node is the only final-report writer in the public DAG. It does not invent
new evidence or product facts. It assembles the verified state into
GamingMouseFinalReportSchema and explicitly preserves pending MCP gaps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.schemas.report import ReportAgentOutput
from app.services.metrics_service import calculate_report_metrics


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _valid_claims(state: dict, evidence_ids: set[str]) -> List[Dict[str, Any]]:
    unsupported = {_as_text(item) for item in state.get("unsupported_claim_ids", []) if _as_text(item)}
    claims = [item for item in state.get("claims", []) if isinstance(item, dict)]
    valid: List[Dict[str, Any]] = []
    for claim in claims:
        claim_id = _as_text(claim.get("claim_id"))
        if claim_id and claim_id in unsupported:
            continue
        cited = [_as_text(item) for item in claim.get("evidence_ids", []) if _as_text(item)]
        if cited and all(item in evidence_ids for item in cited):
            valid.append(claim)
    return valid


def _used_ids(valid_claims: List[Dict[str, Any]], evidence_ids: set[str]) -> tuple[List[str], List[str]]:
    used_claim_ids: List[str] = []
    used_evidence_ids: List[str] = []
    for claim in valid_claims:
        claim_id = _as_text(claim.get("claim_id"))
        if claim_id:
            used_claim_ids.append(claim_id)
        for evidence_id in claim.get("evidence_ids", []):
            evidence_id = _as_text(evidence_id)
            if evidence_id and evidence_id in evidence_ids and evidence_id not in used_evidence_ids:
                used_evidence_ids.append(evidence_id)
    return used_claim_ids, used_evidence_ids


def _product_label(product: Dict[str, Any]) -> str:
    brand = _as_text(product.get("brand"))
    model = _as_text(product.get("model"))
    return f"{brand} {model}".strip() or _as_text(product.get("product_id")) or "待识别产品"


def _score_products(state: dict) -> List[Dict[str, Any]]:
    scores = state.get("product_scores", {})
    if not isinstance(scores, dict):
        return []
    return [item for item in scores.get("products", []) if isinstance(item, dict)]


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_as_text(item) for item in value if _as_text(item)]


def _clean_identity(item: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {
        "official_model": _as_text(item.get("official_model") or item.get("model")),
        "model": _as_text(item.get("model") or item.get("official_model")),
        "brand": _as_text(item.get("brand")),
        "family": _as_text(item.get("family")),
        "variant_name": _as_text(item.get("variant_name")),
        "variant_type": _as_text(item.get("variant_type")),
        "aliases": _string_list(item.get("aliases")),
        "community_aliases": _string_list(item.get("community_aliases")),
        "alias_confidence": _as_text(item.get("alias_confidence")) or "pending",
        "official_name_confidence": _as_text(item.get("official_name_confidence")) or "pending",
        "shape_detail": _as_text(item.get("shape_detail")),
        "click_system": _as_text(item.get("click_system")),
        "data_status": _as_text(item.get("data_status")) or "pending",
        "field_confidence": item.get("field_confidence") if isinstance(item.get("field_confidence"), dict) else {},
        "official_fields": _string_list(item.get("official_fields")),
        "review_verified_fields": _string_list(item.get("review_verified_fields")),
        "rule_inferred_fields": _string_list(item.get("rule_inferred_fields")),
        "community_unverified_fields": _string_list(item.get("community_unverified_fields")),
        "pending": item.get("pending") if isinstance(item.get("pending"), list) else _as_text(item.get("pending")),
    }
    if not cleaned["official_model"]:
        cleaned["official_model"] = cleaned["model"] or "待识别产品"
    if not cleaned["model"]:
        cleaned["model"] = cleaned["official_model"]
    return cleaned


def _identification(state: dict) -> List[Dict[str, Any]]:
    scores = state.get("product_scores", {})
    if isinstance(scores, dict):
        identities = [item for item in scores.get("identification", []) if isinstance(item, dict)]
        if identities:
            return [_clean_identity(item) for item in identities]

    identities: List[Dict[str, Any]] = []
    for item in state.get("resolved_products", []):
        if not isinstance(item, dict):
            continue
        identities.append(
            {
                "official_model": item.get("official_model") or item.get("model"),
                "model": item.get("official_model") or item.get("model"),
                "brand": item.get("official_brand") or item.get("brand"),
                "family": item.get("family") or "",
                "variant_name": item.get("variant_name") or "",
                "variant_type": item.get("variant_type") or "",
                "alias_confidence": item.get("match_confidence") or "pending",
                "click_system": item.get("click_system") or "",
                "data_status": "resolved",
            }
        )
    return [_clean_identity(item) for item in identities]


def _hardware_specs(state: dict) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for fact in state.get("product_facts", []):
        if not isinstance(fact, dict):
            continue
        fact_specs = fact.get("specs") if isinstance(fact.get("specs"), dict) else {}
        specs.append(
            {
                "product_id": fact.get("product_id"),
                "brand": fact.get("brand"),
                "model": fact.get("model"),
                "data_status": fact.get("data_status") or fact_specs.get("data_status") or "verified",
                "fact_source": fact.get("fact_source") or "local_product_json",
                "weight_g": fact_specs.get("weight_g"),
                "sensor": fact_specs.get("sensor") or "",
                "dpi_max": fact_specs.get("dpi_max"),
                "polling_rate_hz": fact_specs.get("polling_rate_hz"),
                "connection": fact_specs.get("connection") or [],
                "battery_hours": fact_specs.get("battery_hours"),
                "switch_type": fact_specs.get("switch_type") or "",
                "click_system": fact_specs.get("click_system") or "",
                "software": fact_specs.get("software") or "",
                "onboard_memory": fact_specs.get("onboard_memory"),
                "shape": fact_specs.get("shape") or "",
                "price_range": {
                    **(fact_specs.get("price_range") if isinstance(fact_specs.get("price_range"), dict) else {}),
                    "status": "reference_only",
                    "note": "历史参考价格不参与最终性价比判断，实时价格等待 Price MCP 补齐。",
                },
                "field_confidence": fact_specs.get("field_confidence") or {},
                "sources": fact_specs.get("sources") or [],
            }
        )
    return specs


def _feature_tree(state: dict, hardware_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    has_hardware = bool(hardware_specs)
    source = "local_product_json" if has_hardware else "pending_official_spec_mcp"
    hardware_status = "available" if has_hardware else "pending"
    return {
        "schema_name": "gaming_mouse_feature_tree",
        "performance": {
            "name": "性能参数",
            "status": hardware_status,
            "summary": "传感器、DPI 与回报率来自本地事实库或后续官网 MCP。",
            "source": source,
            "fields": ["sensor", "dpi_max", "polling_rate_hz"],
        },
        "shape_and_weight": {
            "name": "轻量化与形态事实",
            "status": hardware_status,
            "summary": "重量与形态只作为稳定硬件事实展示；尺寸、模具 ID、握法和手感等待用户评价/测评证据。",
            "source": source,
            "fields": ["weight_g", "shape"],
        },
        "wireless_and_battery": {
            "name": "无线与续航",
            "status": hardware_status,
            "summary": "连接方式、回报率与续航以稳定规格为准；实测体验等待评测数据。",
            "source": source,
            "fields": ["connection", "battery_hours", "polling_rate_hz"],
        },
        "click_system": {
            "name": "点击系统",
            "status": hardware_status,
            "summary": "点击系统和微动类型可进入硬件对比，长期可靠性等待用户反馈验证。",
            "source": source,
            "fields": ["switch_type", "click_system"],
        },
        "software_ecosystem": {
            "name": "软件/驱动生态",
            "status": "partial" if has_hardware else "pending",
            "summary": "当前只展示驱动名称和板载内存事实，驱动稳定性等待 ReviewIntel MCP。",
            "source": source,
            "fields": ["software", "onboard_memory"],
        },
    }


def _pricing_model(state: dict) -> Dict[str, Any]:
    price_status = state.get("price_status", {}) if isinstance(state.get("price_status"), dict) else {}
    price_records = state.get("price_records", []) if isinstance(state.get("price_records"), list) else []
    price_available = price_status.get("status") == "available"
    return {
        "schema_name": "gaming_mouse_pricing_model",
        "status": "available" if price_available else "pending",
        "realtime_price_status": "available" if price_available else "pending",
        "price_range_reference": price_records,
        "value_score_status": "pending",
        "note": "价格会随时间变化，最终性价比等待 PriceAgent/MCP 实时采集。",
    }


def _user_persona(state: dict) -> Dict[str, Any]:
    review_status = state.get("review_intel_status", {}) if isinstance(state.get("review_intel_status"), dict) else {}
    records = [item for item in state.get("review_intel_records", []) if isinstance(item, dict)]
    grip: Dict[str, str] = {}
    hand_size: Dict[str, str] = {}
    game_type: Dict[str, str] = {}
    personas: List[str] = []
    limitations: List[str] = []
    for record in records:
        model = _as_text(record.get("model") or record.get("input")) or "unknown product"
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        if isinstance(signals.get("grip_feel"), dict):
            grip[model] = _as_text(signals["grip_feel"].get("summary"))
        if isinstance(signals.get("hand_size_fit"), dict):
            hand_size[model] = _as_text(signals["hand_size_fit"].get("summary"))
        if isinstance(signals.get("game_type_fit"), dict):
            game_type[model] = _as_text(signals["game_type_fit"].get("summary"))
        for item in record.get("fit_recommendations", []) if isinstance(record.get("fit_recommendations"), list) else []:
            if isinstance(item, dict) and _as_text(item.get("summary")):
                personas.append(f"{model}: {_as_text(item.get('summary'))}")
        for item in record.get("limitations", []) if isinstance(record.get("limitations"), list) else []:
            if _as_text(item):
                limitations.append(f"{model}: {_as_text(item)}")
    if grip or hand_size or game_type or personas:
        return {
            "schema_name": "gaming_mouse_user_persona",
            "status": "available" if review_status.get("status") == "available" else "partial",
            "grip_style_fit": grip,
            "hand_size_fit": hand_size,
            "game_type_fit": game_type,
            "target_persona": personas,
            "evidence_status": review_status.get("status") or "partial",
            "limitation": "; ".join(limitations) if limitations else "Review-backed persona signals are available with per-signal confidence labels.",
        }
    return {
        "schema_name": "gaming_mouse_user_persona",
        "status": "insufficient_evidence",
        "grip_style_fit": {},
        "hand_size_fit": {},
        "game_type_fit": {},
        "target_persona": [],
        "evidence_status": review_status.get("status") or "review_intel_pending",
        "limitation": "握法、手型、适合游戏和长期口碑必须等待真实评价/测评证据。",
    }


def _score_flow(state: dict) -> Dict[str, Any]:
    flow = state.get("score_flow", {}) if isinstance(state.get("score_flow"), dict) else {}
    # Product scoring is intentionally removed from the Agent workflow. ReportAgent
    # uses scenario recommendations and credibility metrics instead.
    return flow if flow.get("baseline_score") or flow.get("final_score") else {}


def _final_recommendation(state: dict, score_flow: Dict[str, Any]) -> Dict[str, Any]:
    final_score = score_flow.get("final_score", {}) if isinstance(score_flow.get("final_score"), dict) else {}
    recommended = _as_text(final_score.get("recommended_product"))
    if not recommended or recommended == "待定":
        return {
            "recommended_product": "待定",
            "reason": "当前缺少完整产品事实或证据链，不输出确定购买建议。",
            "top_reasons": ["本地事实不足或外部数据仍为 pending。"],
            "cautions": [],
        }

    return {
        "recommended_product": recommended,
        "reason": "当前建议只基于已验证的硬件事实、证据链、风险披露和质量门控。",
        "top_reasons": [
            "本地硬件事实已结构化进入对比。",
            "所有正式 claim 必须引用有效 evidence_id。",
            "pending 的评价、测评和实时价格已披露，不伪造成已完成。",
        ],
        "cautions": [],
    }


def _scenario_recommendations(state: dict) -> List[Dict[str, Any]]:
    """按"购买场景"给推荐，而不是单一赢家。

    硬件类(性能/轻量/续航/驱动)用本地+官网事实，高可信直接给结论；
    价格类只做"官方价对官方价、电商价对电商价"，缺一边就判数据缺失；
    需要真实测评的(FPS/手感/长期可靠性)显示占位，等 ReviewIntelMCP。
    """
    products = _score_products(state)
    price_records = [item for item in state.get("price_records", []) if isinstance(item, dict)]
    scenarios: List[Dict[str, Any]] = []
    if len(products) < 2:
        return scenarios

    def norm(value: Any) -> str:
        return _as_text(value).lower().replace(" ", "")

    def spec(product: Dict[str, Any], field: str) -> Any:
        specs = product.get("hardware_specs") if isinstance(product.get("hardware_specs"), dict) else {}
        return specs.get(field)

    def num(product: Dict[str, Any], field: str) -> float | None:
        value = spec(product, field)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def model_of(product: Dict[str, Any]) -> str:
        return _as_text(product.get("model") or product.get("brand")) or "产品"

    def add(
        scenario: str,
        key: str,
        status: str,
        recommended: str | None,
        verdict: str,
        reason: str,
        confidence: str,
        evidence_ids: List[str] | None = None,
        source: str | None = None,
    ) -> None:
        item = {
            "scenario": scenario,
            "key": key,
            "status": status,  # recommended / tie / data_missing / pending_review
            "recommended_product": recommended,
            "verdict": verdict,
            "reason": reason,
            "confidence": confidence,  # high / medium / low / pending
        }
        if evidence_ids:
            item["evidence_ids"] = evidence_ids
        if source:
            item["source"] = source
        scenarios.append(item)

    a, b = products[0], products[1]
    a_name, b_name = model_of(a), model_of(b)

    # 1) 硬件性能（综合评分）
    ha, hb = a.get("hardware_score"), b.get("hardware_score")
    if isinstance(ha, (int, float)) and isinstance(hb, (int, float)):
        if abs(ha - hb) < 1:
            add("追求硬件性能", "hardware_performance", "tie", None, f"{a_name} 与 {b_name} 硬件综合接近，基本持平", "基于本地 / 官网硬件事实的综合评分。", "high")
        else:
            winner = a_name if ha > hb else b_name
            add("追求硬件性能", "hardware_performance", "recommended", winner, f"{winner} 硬件综合更强（{max(ha, hb)} vs {min(ha, hb)}）", "综合重量、传感器、回报率、连接、续航、点击系统。", "high")

    # 2) 轻量化
    wa, wb = num(a, "weight_g"), num(b, "weight_g")
    if wa is not None and wb is not None:
        if wa == wb:
            add("追求极致轻量", "lightweight", "tie", None, f"两款重量相同（{wa} g）", "基于官方重量事实。", "high")
        else:
            winner, lo, hi = (a_name, wa, wb) if wa < wb else (b_name, wb, wa)
            add("追求极致轻量", "lightweight", "recommended", winner, f"{winner} 更轻（{lo} g vs {hi} g）", "基于官方重量事实。", "high")
    else:
        add("追求极致轻量", "lightweight", "data_missing", None, "缺少一方重量数据，无法给出建议", "重量字段未抽全。", "pending")

    # 3) 无线与续航
    bat_a, bat_b = num(a, "battery_hours"), num(b, "battery_hours")
    if bat_a is not None and bat_b is not None:
        if bat_a == bat_b:
            add("无线续航", "battery", "tie", None, f"两款续航相同（{bat_a} 小时）", "基于官方续航事实。", "high")
        else:
            winner, hi, lo = (a_name, bat_a, bat_b) if bat_a > bat_b else (b_name, bat_b, bat_a)
            add("无线续航", "battery", "recommended", winner, f"{winner} 续航更长（{hi}h vs {lo}h）", "基于官方续航事实。", "high")
    else:
        add("无线续航", "battery", "data_missing", None, "一方无续航数据（可能有线 / 未抽全），无法对比", "续航字段缺失。", "pending")

    # 4) 驱动与可调性
    def has_driver(product: Dict[str, Any]) -> bool:
        sw = _as_text(spec(product, "software")).lower()
        return bool(sw) and not any(hint in sw for hint in ("无", "免驱", "driverless", "none"))

    da, db = has_driver(a), has_driver(b)
    if da and db:
        add("驱动与可调性", "driver", "tie", None, "两款都有配套驱动软件，均可自定义 / 板载", "基于官方软件字段。", "high")
    elif da and not db:
        add("驱动与可调性", "driver", "recommended", a_name, f"只有 {a_name} 有配套驱动软件", "基于官方软件字段。", "high")
    elif db and not da:
        add("驱动与可调性", "driver", "recommended", b_name, f"只有 {b_name} 有配套驱动软件", "基于官方软件字段。", "high")
    else:
        add("驱动与可调性", "driver", "tie", None, "两款均免驱 / 无配套软件，即插即用", "基于官方软件字段。", "high")

    # 5/6) 预算敏感：官方价对官方价、电商价对电商价（缺一边即数据缺失）
    def price_record_for(name: str) -> Dict[str, Any] | None:
        for record in price_records:
            if norm(record.get("model") or record.get("input")) == norm(name):
                return record
        return None

    def official_price(record: Dict[str, Any] | None) -> float | None:
        value = (record.get("price_summary") or {}).get("official_price") if record else None
        return float(value) if isinstance(value, (int, float)) else None

    def ecom_quote(record: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not record:
            return None
        quotes = [
            quote for quote in record.get("quotes", [])
            if isinstance(quote, dict)
            and isinstance(quote.get("price"), (int, float))
            and _as_text(quote.get("source_type")) != "official_store"
        ]
        if not quotes:
            return None
        rank = {"retailer": 3, "ecommerce_candidate": 2, "search_snippet": 1}
        return sorted(quotes, key=lambda quote: rank.get(_as_text(quote.get("source_type")), 0), reverse=True)[0]

    record_a, record_b = price_record_for(a_name), price_record_for(b_name)
    oa, ob = official_price(record_a), official_price(record_b)
    if oa is not None and ob is not None:
        if oa == ob:
            add("预算敏感 · 官方价", "budget_official", "tie", None, f"两款官方价相同（${oa}）", "官方价高可信，仅官方对官方。", "high")
        else:
            winner, lo, hi = (a_name, oa, ob) if oa < ob else (b_name, ob, oa)
            add("预算敏感 · 官方价", "budget_official", "recommended", winner, f"{winner} 官方价更低（${lo} vs ${hi}）", "官方价高可信，仅官方对官方。", "high")
    else:
        add("预算敏感 · 官方价", "budget_official", "data_missing", None, "一方缺少官方价（被反爬拦截 / 未采集），数据缺失无法给出建议", "官方价只能与官方价对比。", "pending")

    qa, qb = ecom_quote(record_a), ecom_quote(record_b)
    if qa and qb:
        pa, pb = float(qa["price"]), float(qb["price"])

        def is_video(quote: Dict[str, Any]) -> bool:
            return _as_text(quote.get("source_type")) == "search_snippet" or "youtube" in _as_text(quote.get("source_domain")).lower()

        conf = "low" if (is_video(qa) or is_video(qb)) else "medium"
        if pa == pb:
            add("预算敏感 · 电商价", "budget_ecom", "tie", None, f"两款电商价相同（${pa}）", "电商价仅电商对电商；视频来源为低可信。", conf)
        else:
            winner, lo, hi = (a_name, pa, pb) if pa < pb else (b_name, pb, pa)
            add("预算敏感 · 电商价", "budget_ecom", "recommended", winner, f"{winner} 电商价更低（${lo} vs ${hi}）", "电商价仅电商对电商；视频来源为低可信。", conf)
    else:
        add("预算敏感 · 电商价", "budget_ecom", "data_missing", None, "一方缺少电商价，数据缺失无法给出建议", "电商价只能与电商价对比。", "pending")

    review_records = [item for item in state.get("review_intel_records", []) if isinstance(item, dict)]

    def review_signal(product_name: str, dimension: str) -> Dict[str, Any] | None:
        for record in review_records:
            name = _as_text(record.get("model") or record.get("input"))
            if norm(name) != norm(product_name):
                continue
            signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
            signal = signals.get(dimension)
            if isinstance(signal, dict) and signal.get("evidence_ids"):
                return signal
        return None

    def add_review_scenario(scenario: str, key: str, dimension: str) -> None:
        a_signal = review_signal(a_name, dimension)
        b_signal = review_signal(b_name, dimension)
        rank = {"high": 3, "medium": 2, "low": 1}
        a_rank = rank.get(_as_text((a_signal or {}).get("confidence")).lower(), 0)
        b_rank = rank.get(_as_text((b_signal or {}).get("confidence")).lower(), 0)
        if a_signal and b_signal:
            if a_rank == b_rank:
                add(
                    scenario,
                    key,
                    "tie",
                    None,
                    f"{a_name} 与 {b_name} 都有 {dimension} 的测评/评价证据。",
                    f"A: {_as_text(a_signal.get('summary'))}; B: {_as_text(b_signal.get('summary'))}",
                    _as_text(a_signal.get("confidence")) or "low",
                )
            else:
                winner = a_name if a_rank > b_rank else b_name
                signal = a_signal if a_rank > b_rank else b_signal
                add(
                    scenario,
                    key,
                    "recommended",
                    winner,
                    f"{winner} 在 {dimension} 上有更强的测评/评价支撑。",
                    _as_text(signal.get("summary")),
                    _as_text(signal.get("confidence")) or "low",
                )
        elif a_signal or b_signal:
            signal = a_signal or b_signal
            winner = a_name if a_signal else b_name
            add(
                scenario,
                key,
                "recommended",
                winner,
                f"{winner} 有 {dimension} 的测评/评价支撑；另一款缺少同类证据。",
                _as_text(signal.get("summary")),
                _as_text(signal.get("confidence")) or "low",
            )
        else:
            add(
                scenario,
                key,
                "pending_review",
                None,
                "等待博主测评 / 用户评价（ReviewIntelMCP）",
                "需要真实测评 / 评价数据，暂为占位。",
                "pending",
            )

    add_review_scenario("追求极限 FPS", "fps", "game_type_fit")
    add_review_scenario("重视手感 / 握法", "grip_feel", "grip_feel")
    add_review_scenario("长期可靠性", "long_term", "long_term_reliability")

    def canonical_feedback_product(raw: Any, message: str) -> str | None:
        text = norm(raw)
        message_text = norm(message)
        for name in (a_name, b_name):
            normalized_name = norm(name)
            if normalized_name and (
                normalized_name in text
                or text in normalized_name
                or normalized_name in message_text
            ):
                return name
        return _as_text(raw) or None

    def replace_scenario(payload: Dict[str, Any]) -> None:
        key = _as_text(payload.get("key"))
        for index, item in enumerate(scenarios):
            if _as_text(item.get("key")) == key:
                scenarios[index] = payload
                return
        scenarios.append(payload)

    for feedback in state.get("human_feedback", []):
        if not isinstance(feedback, dict):
            continue
        message = _as_text(feedback.get("message"))
        if not message:
            continue
        feedback_status = _as_text(feedback.get("status")).lower()
        if feedback.get("needs_verification") or feedback_status in {
            "pending_verification",
            "needs_external_evidence",
        }:
            continue
        dimension = norm(feedback.get("dimension"))
        message_norm = norm(message)
        product_name = canonical_feedback_product(feedback.get("product"), message)
        if not product_name:
            continue

        evidence_id = _as_text(feedback.get("feedback_id"))
        evidence_ids = [evidence_id] if evidence_id else []
        if dimension in {"fps_performance", "scenario_fit", "game_type_fit"} and any(
            hint in message_norm for hint in ("fps", "瓦", "cs", "valorant", "apex", "竞技")
        ):
            replace_scenario(
                {
                    "scenario": "追求极限 FPS",
                    "key": "fps",
                    "status": "recommended",
                    "recommended_product": product_name,
                    "verdict": f"推荐：{product_name}",
                    "reason": f"人工修正指出：{message}；已进入 VerificationAgent 校验链路，按中可信场景证据展示。",
                    "confidence": "medium",
                    "evidence_ids": evidence_ids,
                    "source": "human_feedback",
                }
            )
        elif dimension in {"grip_feel", "scenario_fit"} and any(
            hint in message_norm for hint in ("手感", "握", "抓", "趴", "指握", "掌握")
        ):
            replace_scenario(
                {
                    "scenario": "重视手感 / 握法",
                    "key": "grip_feel",
                    "status": "recommended",
                    "recommended_product": product_name,
                    "verdict": f"推荐：{product_name}",
                    "reason": f"人工修正指出：{message}；该结论等待更多用户/测评证据增强。",
                    "confidence": "medium",
                    "evidence_ids": evidence_ids,
                    "source": "human_feedback",
                }
            )

    return scenarios


def _agent_contributions(state: dict) -> List[Dict[str, Any]]:
    defaults = [
        ("ResearchAgent", "调研规划员", "规划本地事实、官网规格、评价测评和实时价格的数据需求。"),
        ("CollectorAgent", "采集与实体识别员", "识别产品、读取本地事实库，并把外部 MCP 数据标记为 pending。"),
        ("EvidenceAgent", "证据结构化员", "把本地事实和采集结果统一转换成可追溯 evidence。"),
        ("AnalysisAgent", "分析师", "只分析有 evidence 支撑的硬件事实差异，并披露体验/价格缺口。"),
        ("VerificationAgent", "事实校验员", "检查 claim 和矩阵结论是否被 evidence 支撑。"),
        ("QualityAgent", "质量门控员", "根据证据、风险和 pending 数据决定 approved、limited 或 partial_report。"),
        ("ReportAgent", "报告撰写员", "汇总专业电竞鼠标 schema 报告。"),
    ]
    trace_agents = {
        item.get("agent_name"): item.get("status")
        for item in state.get("trace_log", [])
        if isinstance(item, dict)
    }
    return [
        {
            "agent": agent,
            "role": role,
            "summary": summary,
            "status": trace_agents.get(agent, "not_run"),
        }
        for agent, role, summary in defaults
    ]


def _evidence_links(
    state: dict,
    used_claim_ids: List[str],
    used_evidence_ids: List[str],
    risk_flags: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quality_result = state.get("quality_result", {}) if isinstance(state.get("quality_result"), dict) else {}
    return {
        "used_claim_ids": used_claim_ids,
        "used_evidence_ids": used_evidence_ids,
        "evidence_status": state.get("evidence_status", {}),
        "unsupported_claim_ids": state.get("unsupported_claim_ids", []),
        "pending_data": quality_result.get("pending_data") or state.get("pending_data", []),
        "risk_flags": risk_flags,
    }


def _append_trace(state: dict, used_claim_ids: List[str], used_evidence_ids: List[str]) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "ReportAgent",
            "status": "success",
            "output_summary": (
                f"generated gaming_mouse final_report with {len(used_claim_ids)} claims "
                f"and {len(used_evidence_ids)} evidence items"
            ),
            "error": None,
        }
    )


def report_agent(state: dict) -> Dict[str, Any]:
    """Generate the final professional report."""
    evidence_list = [item for item in state.get("evidence_list", []) if isinstance(item, dict)]
    evidence_ids = {_as_text(item.get("evidence_id")) for item in evidence_list if _as_text(item.get("evidence_id"))}
    valid_claims = _valid_claims(state, evidence_ids)
    used_claim_ids, used_evidence_ids = _used_ids(valid_claims, evidence_ids)

    quality_result = state.get("quality_result", {}) if isinstance(state.get("quality_result"), dict) else {}
    quality_status = _as_text(quality_result.get("status") or state.get("quality_status") or "pending")
    risk_flags = [item for item in state.get("risk_flags", []) if isinstance(item, dict)]
    hardware_specs = _hardware_specs(state)
    score_flow = _score_flow(state)
    metrics = calculate_report_metrics(state)
    pending_data = quality_result.get("pending_data") or state.get("pending_data", [])

    final_report = {
        "schema_name": "gaming_mouse_competitive_report",
        "schema_version": "1.0",
        "report_kind": "gaming_mouse_product_comparison",
        "report_type": "agent_final_report",
        "title": "电竞鼠标 Agent 综合分析报告",
        "summary": {
            "status": quality_status,
            "evidence_count": len(evidence_list),
            "claim_count": len(valid_claims),
            "pending_count": len(pending_data) if isinstance(pending_data, list) else 0,
            "schema": "GamingMouseFinalReportSchema",
        },
        "executive_summary": [
            f"本次报告使用 {len(valid_claims)} 条已验证 claims 和 {len(evidence_list)} 条 evidence。",
            "本地硬件事实可直接进入对比，评价测评、实时价格和长期口碑仍等待 MCP 补齐。",
            f"QualityAgent 状态为 {quality_status}，quality_score 是报告可信度，不是产品评分。",
        ],
        "product_identification": _identification(state),
        "hardware_specs": hardware_specs,
        "official_spec_records": state.get("official_spec_records", []),
        "review_intel_records": state.get("review_intel_records", []),
        "review_intel_status": state.get("review_intel_status", {}),
        "hardware_fact_comparison": state.get("hardware_analysis", {}),
        "analysis_ai_interpretation": state.get("analysis_ai_interpretation", {}),
        "product_matrix": state.get("product_matrix", {}),
        "business_matrix": state.get("business_matrix", {}),
        "feature_tree": _feature_tree(state, hardware_specs),
        "pricing_model": _pricing_model(state),
        "user_persona": _user_persona(state),
        "evidence_links": _evidence_links(state, used_claim_ids, used_evidence_ids, risk_flags),
        "score_flow": score_flow,
        "agent_contributions": _agent_contributions(state),
        "pending_data": pending_data,
        "risk_disclosure": risk_flags,
        "risk_flags": risk_flags,
        "quality_status": quality_status,
        "report_status": quality_status,
        "approved_with_limitations": quality_status == "approved_with_limitations",
        "partial_report": quality_status == "partial_report",
        "auto_degraded": bool(quality_result.get("auto_degraded")),
        "limitations": quality_result.get("limitations", []),
        "final_recommendation": _final_recommendation(state, score_flow),
        "scenario_recommendations": _scenario_recommendations(state),
        # Final report uses scenario recommendations instead of product scores.
        "final_score": [],
        "used_claim_ids": used_claim_ids,
        "used_evidence_ids": used_evidence_ids,
        "metrics": metrics,
        "faithfulness_report": state.get("faithfulness_report", {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    output = ReportAgentOutput(
        final_report=final_report,
        used_claim_ids=used_claim_ids,
        used_evidence_ids=used_evidence_ids,
    )
    final_report_payload = output.final_report.model_dump(mode="json")
    next_state = {
        **state,
        "current_agent": "ReportAgent",
        "final_report": final_report_payload,
        "used_claim_ids": output.used_claim_ids,
        "used_evidence_ids": output.used_evidence_ids,
        "metrics": metrics,
    }
    _append_trace(next_state, output.used_claim_ids, output.used_evidence_ids)
    print(
        f"[ReportAgent] 专业报告生成完成，claims={len(output.used_claim_ids)}, "
        f"evidence={len(output.used_evidence_ids)}"
    )
    return next_state
