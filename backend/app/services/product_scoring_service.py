"""产品评分服务（与"报告可信度/质量分"完全分离）。

`quality_score`（QualityAgent）衡量的是**分析报告的可信度**，不是产品好坏；它在所有
检查通过时固定 ~90，不能用来比产品。本模块只根据 data/products/gaming_mice.json 里的
**真实硬件字段**为每个产品算出差异化的产品评分。

每个产品输出（分数均为 0-100，越高越好）：
- hardware_score：重量/传感器/回报率/连接/续航/微动/板载 综合
- software_score：是否有配套驱动 / 板载能力的基础事实判断，不代表驱动口碑
- game_fit_score / grip_fit_score / hand_fit_score：体验结论，等待真实用户评价/测评 MCP
- sentiment_score：网友评价/博主测评 —— MCP 未接入，故为 None 并标 pending
- data_completeness：已覆盖的评分维度占比
- pending_dimensions：当前缺失（待采集）的维度
- overall_score.current_score：只用现有数据
- overall_score.full_score_with_missing_as_zero：缺失外部体验维度按 0 计入
- score_basis：每个分数基于哪些字段
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 软性/MCP 维度，未接入实时数据前为待采集；不写入本地 JSON，不参与本地硬件事实基线。
PENDING_SCORE_DIMENSIONS = [
    "grip_fit（握法适配：趴握 / 抓握 / 指握，待用户评价与测评验证）",
    "hand_fit（手型适配：小手 / 中手 / 大手，待用户评价与测评验证）",
    "game_type_fit（适合游戏类型，待用户评价与测评验证）",
    "sentiment_score（网友评价 / 博主测评）",
    "real_time_price（实时价格 / 性价比）",
    "driver_reputation（驱动稳定性与口碑）",
]

# overall 权重：基础快评只使用本地硬件/官方事实；体验口碑由 external_experience 占位。
OVERALL_WEIGHTS = {
    "hardware": 0.58,
    "software": 0.14,
    "click_system": 0.13,
    "external_experience": 0.15,  # MCP 未接入，current_score 归一化时剔除，full 分按 0 计入
}

# 点击系统评分与优劣/风险说明
CLICK_SYSTEM_INFO = {
    "optical": (88.0, "光学微动：无金属触点、寿命长、零 debounce 延迟", "手感偏脆、回弹偏硬，部分玩家不适应"),
    "hybrid": (90.0, "光-机混合微动：兼顾光学响应与机械段落感", "结构较新，长期耐久性仍待观察"),
    "mechanical": (80.0, "机械微动：段落感清晰、手感成熟", "可能出现双击/氧化，寿命相对光学短"),
    "haptic": (94.0, "HITS / 触觉可调触发：触发行程可调、支持 Rapid Trigger、点击反馈可自定义", "长期可靠性、用户适应成本与游戏生态收益仍需口碑验证"),
    "unknown": (70.0, "点击系统未知", "缺少点击系统数据，置信度偏低"),
}

MATURE_SOFTWARE = ("g hub", "ghub", "synapse", "icue", "armoury crate", "steelseries gg")
LIGHT_SOFTWARE = ("fusion", "glorious core", "lamzu", "endgame", "configurator", "web")
DRIVERLESS_HINTS = ("无", "免驱", "driverless", "none")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round(value: Optional[float], ndigits: int = 1) -> Optional[float]:
    return round(value, ndigits) if isinstance(value, (int, float)) else None


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# --------------------------------------------------------------------------- #
# 硬件子分（缺字段返回 None，加权时跳过）
# --------------------------------------------------------------------------- #
def _score_weight(weight_g: Any) -> Optional[float]:
    if not _is_num(weight_g):
        return None
    return round(_clamp(100 - (weight_g - 50) * 1.3, 35, 100), 1)


def _score_dpi(dpi_max: Any) -> Optional[float]:
    if not _is_num(dpi_max):
        return None
    return round(_clamp(40 + dpi_max / 1000 * 1.6, 40, 100), 1)


def _score_polling(hz: Any) -> Optional[float]:
    if not _is_num(hz):
        return None
    return round(_clamp(60 + (hz - 1000) / 7000 * 40, 60, 100), 1)


def _has_wireless(connection: Any) -> bool:
    return isinstance(connection, list) and ("2.4ghz" in connection or "bluetooth" in connection)


def _score_connection(connection: Any) -> Optional[float]:
    if not isinstance(connection, list) or not connection:
        return None
    has_24 = "2.4ghz" in connection
    base = 82.0 if has_24 else 70.0
    if "bluetooth" in connection:
        base += 12
    if not has_24 and "wired" in connection and len(connection) == 1:
        base = 70.0
    return round(_clamp(base, 40, 100), 1)


def _score_battery(hours: Any) -> Optional[float]:
    # 有线鼠标 battery_hours=None：续航对其不适用，返回 None（加权时跳过，不当扣分）
    if not _is_num(hours):
        return None
    return round(_clamp(55 + hours * 0.25, 55, 100), 1)


def _score_switch(switch_type: Any) -> Optional[float]:
    text = str(switch_type or "")
    if not text:
        return None
    if "光学" in text or "optical" in text.lower():
        return 90.0
    if "机械" in text or "omron" in text.lower() or "kailh" in text.lower() or "huano" in text.lower():
        return 80.0
    return 78.0


def _score_onboard(onboard: Any) -> Optional[float]:
    if onboard is None:
        return None
    return 88.0 if onboard else 70.0


def _comfort_score(shape: Any) -> float:
    return {"ergonomic": 84.0, "symmetrical": 80.0}.get(shape, 76.0)


def _click_system_eval(product: dict) -> tuple[str, float, str, str]:
    """点击系统类型 + 分数 + 优势/风险（优先 click_system 字段，缺失从 switch_type 推断）。"""
    ctype = str(product.get("click_system") or "").lower()
    if "haptic" in ctype or "adjust" in ctype or "磁" in ctype:
        key = "haptic"
    elif ctype in ("optical", "hybrid", "mechanical"):
        key = ctype
    else:
        sw = str(product.get("switch_type") or "")
        if "混合" in sw or "lightforce" in sw.lower():
            key = "hybrid"
        elif "光学" in sw or "optical" in sw.lower():
            key = "optical"
        elif sw:
            key = "mechanical"
        else:
            key = "unknown"
    score, pros, risk = CLICK_SYSTEM_INFO.get(key, CLICK_SYSTEM_INFO["unknown"])
    return key, score, pros, risk


def _shape_confidence(product: dict) -> float:
    """模具置信度：mold_id + shape_detail 齐全=1.0；缺一=0.75；都缺=0.5。"""
    has_mold = bool(str(product.get("mold_id") or "").strip())
    has_detail = bool(str(product.get("shape_detail") or "").strip())
    if has_mold and has_detail:
        return 1.0
    if has_mold or has_detail:
        return 0.75
    return 0.5


def _field_confidence_summary(product: dict) -> Dict[str, List[str]]:
    """按可信度分组字段名，避免报告只给一个笼统 confidence。"""
    field_confidence = product.get("field_confidence")
    if not isinstance(field_confidence, dict):
        return {}
    grouped: Dict[str, List[str]] = {}
    for field, confidence in field_confidence.items():
        key = str(confidence or "pending")
        grouped.setdefault(key, []).append(str(field))
    return {key: sorted(values) for key, values in grouped.items()}


def _length(product: dict) -> Optional[float]:
    dims = product.get("dimensions_mm") or {}
    length = dims.get("length") if isinstance(dims, dict) else None
    return float(length) if _is_num(length) else None


def _weighted(parts: List[tuple[Optional[float], float]]) -> Optional[float]:
    """对 (分数, 权重) 列表加权平均，跳过 None 分并对剩余权重归一化。"""
    usable = [(s, w) for s, w in parts if s is not None and w > 0]
    if not usable:
        return None
    total_w = sum(w for _s, w in usable)
    return round(sum(s * w for s, w in usable) / total_w, 1) if total_w else None


def score_product(product: dict) -> dict:
    """为单个产品（gaming_mice.json 的一条）计算结构化评分。"""
    subscores = {
        "weight": _score_weight(product.get("weight_g")),
        "dpi": _score_dpi(product.get("dpi_max")),
        "polling": _score_polling(product.get("polling_rate_hz")),
        "connection": _score_connection(product.get("connection")),
        "battery": _score_battery(product.get("battery_hours")),
        "switch": _score_switch(product.get("switch_type")),
        "onboard": _score_onboard(product.get("onboard_memory")),
    }

    hardware_score = _weighted(
        [
            (subscores["weight"], 0.26),
            (subscores["dpi"], 0.16),
            (subscores["polling"], 0.18),
            (subscores["connection"], 0.13),
            (subscores["battery"], 0.13),
            (subscores["switch"], 0.08),
            (subscores["onboard"], 0.06),
        ]
    )

    # software
    software_raw = str(product.get("software") or "")
    sw = software_raw.lower()
    onboard = bool(product.get("onboard_memory"))
    if (not software_raw.strip()) or any(h in sw for h in DRIVERLESS_HINTS):
        software_base, software_note = 72.0, "免驱 / 无配套软件：即插即用、稳定省心，但软件层可调性弱"
    elif any(m in sw for m in MATURE_SOFTWARE):
        software_base, software_note = 86.0, "成熟驱动生态，功能与可调性强"
    elif any(l in sw for l in LIGHT_SOFTWARE):
        software_base, software_note = 78.0, "轻量 / 网页配置工具，够用但生态较薄"
    else:
        software_base, software_note = 80.0, "具备配套软件"
    software_score = round(_clamp(software_base + (5 if onboard else 0)), 1)

    # ergonomics / size
    comfort = _comfort_score(product.get("shape"))
    dims = product.get("dimensions_mm") or {}
    length = _length(product)
    width = float(dims.get("width")) if _is_num(dims.get("width")) else None
    size_small = _clamp(100 - ((length or 122) - 110) * 3, 40, 100)
    size_large = _clamp(40 + ((length or 122) - 115) * 3, 40, 100)
    wireless = _has_wireless(product.get("connection"))
    has_bt = isinstance(product.get("connection"), list) and "bluetooth" in product["connection"]
    weight_s = subscores["weight"] or 60.0
    polling_s = subscores["polling"] or 65.0
    dpi_s = subscores["dpi"] or 60.0
    conn_s = subscores["connection"] or 70.0
    battery_s = subscores["battery"] or 65.0
    weight_g = product.get("weight_g") if _is_num(product.get("weight_g")) else 70.0
    length_v = length or 122.0
    width_v = width or 64.0

    # 点击系统评分 + 模具置信度
    click_type, click_system_score, click_pros, click_risk = _click_system_eval(product)
    shape_confidence = _shape_confidence(product)

    # ---- 旧 game_fit / persona_fit 形状保留，后面会统一覆盖为 pending（前端老字段兼容）----
    fps = round(0.45 * weight_s + 0.30 * polling_s + 0.15 * dpi_s + 0.10 * (100 if wireless else 60), 1)
    moba = round(0.35 * software_score + 0.30 * comfort + 0.20 * conn_s + 0.15 * (88 if onboard else 70), 1)
    office = round(0.35 * (100 if has_bt else 55) + 0.25 * battery_s + 0.25 * comfort + 0.15 * conn_s, 1)
    game_fit = {"fps": fps, "moba": moba, "office": office}
    game_best_label = {"fps": "FPS", "moba": "MOBA / 综合", "office": "办公 / 多设备"}
    game_fit["best_fit"] = game_best_label[max(("fps", "moba", "office"), key=lambda k: game_fit[k])]
    game_fit_score = round(max(fps, moba, office), 1)

    small_hand = round(0.55 * size_small + 0.3 * weight_s + 0.15 * comfort, 1)
    large_hand = round(0.6 * size_large + 0.4 * (90 if product.get("shape") == "ergonomic" else 70), 1)
    low_sens = round(0.5 * weight_s + 0.3 * (90 if wireless else 65) + 0.2 * comfort, 1)
    high_sens = round(0.4 * weight_s + 0.35 * polling_s + 0.25 * (100 - abs(length_v - 120) * 2), 1)
    persona_fit = {"small_hand": small_hand, "large_hand": large_hand, "low_sens": low_sens, "high_sens": high_sens}
    persona_labels = {"small_hand": "小手", "large_hand": "大手", "low_sens": "低敏", "high_sens": "高敏"}
    persona_fit["best_fit"] = [persona_labels[k] for k, v in persona_fit.items() if v >= 80] or [
        persona_labels[max(("small_hand", "large_hand", "low_sens", "high_sens"), key=lambda k: persona_fit[k])]
    ]
    persona_fit_score = round(max(small_hand, large_hand, low_sens, high_sens), 1)

    # ---- 旧手型适配形状保留，后面会统一覆盖为 pending ----
    hand_small = round(_clamp(100 - (length_v - 112) * 4 - max(0.0, width_v - 62) * 3, 30, 100), 1)
    hand_medium = round(_clamp(100 - abs(length_v - 122) * 4 - abs(width_v - 64) * 3, 40, 100), 1)
    hand_large = round(_clamp(40 + (length_v - 118) * 4 + max(0.0, width_v - 62) * 3, 30, 100), 1)
    hand_labels = {"small": "小手", "medium": "中手", "large": "大手"}
    hand_fit = {"small": hand_small, "medium": hand_medium, "large": hand_large}
    hand_fit["best_fit"] = hand_labels[max(("small", "medium", "large"), key=lambda k: hand_fit[k])]
    hand_fit_score = round(max(hand_small, hand_medium, hand_large), 1)

    # ---- 旧握法适配形状保留，后面会统一覆盖为 pending；不再读取 JSON 体验字段 ----
    listed_grips: set[str] = set()
    palm_d = _clamp(60 + (length_v - 115) * 2 + (15 if product.get("shape") == "ergonomic" else 0) - max(0.0, weight_g - 80) * 0.4, 30, 100)
    claw_d = _clamp(82 - abs(length_v - 122) * 2, 45, 95)
    fingertip_d = _clamp(92 - max(0.0, length_v - 115) * 2.5 - max(0.0, weight_g - 65) * 0.6, 30, 100)
    grip_fit = {
        "palm": round(max(palm_d, 85.0) if "palm" in listed_grips else palm_d, 1),
        "claw": round(max(claw_d, 85.0) if "claw" in listed_grips else claw_d, 1),
        "fingertip": round(max(fingertip_d, 85.0) if "fingertip" in listed_grips else fingertip_d, 1),
    }
    grip_labels = {"palm": "趴握", "claw": "抓握", "fingertip": "指握"}
    grip_fit["best_fit"] = grip_labels[max(("palm", "claw", "fingertip"), key=lambda k: grip_fit[k])]
    grip_fit_score = round(max(grip_fit["palm"], grip_fit["claw"], grip_fit["fingertip"]), 1)
    if shape_confidence < 1.0:
        # 旧兼容计算会在下方被 pending 覆盖。
        grip_fit_score = round(grip_fit_score * (0.85 + 0.15 * shape_confidence), 1)

    # ---- 旧专业游戏类型适配形状保留，后面会统一覆盖为 pending；不再读取 JSON 体验字段 ----
    json_types: set[str] = set()

    def _boost(key: str, base: float) -> float:
        return round(_clamp(base + (5 if key in json_types else 0)), 1)

    game_type_fit = {
        "tactical_fps": _boost("tac_fps", 0.30 * weight_s + 0.25 * polling_s + 0.20 * dpi_s + 0.15 * click_system_score + 0.10 * comfort),
        "tracking_fps": _boost("tracking_fps", 0.40 * weight_s + 0.30 * polling_s + 0.20 * dpi_s + 0.10 * click_system_score),
        "moba": _boost("moba", 0.35 * software_score + 0.30 * comfort + 0.20 * (88 if onboard else 70) + 0.15 * conn_s),
        "rts": _boost("rts", 0.30 * software_score + 0.30 * comfort + 0.20 * dpi_s + 0.20 * (88 if onboard else 70)),
        "office": _boost("office", 0.35 * (100 if has_bt else 55) + 0.25 * battery_s + 0.25 * comfort + 0.15 * conn_s),
    }
    gt_labels = {"tactical_fps": "战术 FPS", "tracking_fps": "追踪 FPS", "moba": "MOBA", "rts": "RTS", "office": "办公"}
    gt_best = max(("tactical_fps", "tracking_fps", "moba", "rts", "office"), key=lambda k: game_type_fit[k])
    game_type_fit["best_fit"] = gt_labels[gt_best]
    game_type_fit_score = round(max(game_type_fit[k] for k in ("tactical_fps", "tracking_fps", "moba", "rts", "office")), 1)

    click_system = {"type": click_type, "score": click_system_score, "pros": click_pros, "risk": click_risk}

    # 体验适配不再由本地 JSON/规则给结论。握法、手型、适合游戏类型需要真实用户评价
    # 和博主测评验证，暂时仅保留字段形状供前端兼容。
    pending_experience = {
        "status": "pending_mcp",
        "reason": "需要用户评价、博主测评或长期使用反馈验证，本地硬件事实基线不直接判断。",
    }
    game_fit_score = None
    persona_fit_score = None
    grip_fit_score = None
    hand_fit_score = None
    game_type_fit_score = None
    game_fit = {"best_fit": "待 MCP 验证", **pending_experience}
    persona_fit = {"best_fit": ["待 MCP 验证"], **pending_experience}
    grip_fit = {"best_fit": "待 MCP 验证", **pending_experience}
    hand_fit = {"best_fit": "待 MCP 验证", **pending_experience}
    game_type_fit = {"best_fit": "待 MCP 验证", **pending_experience}

    # sentiment：MCP 未接入 -> pending
    sentiment_score = None

    # ---- overall：只纳入本地硬件/官方事实；体验口碑维度等待 MCP ----
    available = {
        "hardware": hardware_score,
        "software": software_score,
        "click_system": click_system_score,
    }
    current_num = sum(available[k] * OVERALL_WEIGHTS[k] for k in available)
    current_den = sum(OVERALL_WEIGHTS[k] for k in available)
    current_score = round(current_num / current_den, 1) if current_den else None
    # 缺失的体验/口碑维度按 0 计入完整分，作为保守占位展示。
    full_with_zero = round(current_num + 0.0 * OVERALL_WEIGHTS["external_experience"], 1)

    total_weight = sum(OVERALL_WEIGHTS.values())
    data_completeness = round(current_den / total_weight, 2) if total_weight else 0.0

    return {
        "product_id": product.get("id"),
        "model": product.get("model"),
        "brand": product.get("brand"),
        "hardware_specs": {
            "weight_g": product.get("weight_g"),
            "shape": product.get("shape"),
            "sensor": product.get("sensor"),
            "dpi_max": product.get("dpi_max"),
            "polling_rate_hz": product.get("polling_rate_hz"),
            "connection": product.get("connection") or [],
            "battery_hours": product.get("battery_hours"),
            "switch_type": product.get("switch_type"),
            "software": product.get("software"),
            "onboard_memory": product.get("onboard_memory"),
            "shape_detail": product.get("shape_detail"),
            "click_system": product.get("click_system"),
        },
        "overall_score": {
            "current_score": current_score,
            "full_score_with_missing_as_zero": full_with_zero,
        },
        "hardware_score": hardware_score,
        "software_score": software_score,
        "game_fit_score": game_fit_score,
        "persona_fit_score": persona_fit_score,
        "grip_fit_score": grip_fit_score,
        "hand_fit_score": hand_fit_score,
        "game_type_fit_score": game_type_fit_score,
        "click_system_score": click_system_score,
        "sentiment_score": sentiment_score,
        "sentiment_status": "pending",
        "data_completeness": data_completeness,
        "pending_dimensions": list(PENDING_SCORE_DIMENSIONS),
        "subscores": subscores,
        "game_fit": game_fit,
        "persona_fit": persona_fit,
        "grip_fit": grip_fit,
        "hand_fit": hand_fit,
        "game_type_fit": game_type_fit,
        "click_system": click_system,
        "identity": {
            "family": product.get("family"),
            "variant_name": product.get("variant_name"),
            "variant_type": product.get("variant_type"),
            "shape": product.get("shape"),
            "shape_detail": product.get("shape_detail"),
            "official_name_confidence": product.get("official_name_confidence"),
            "alias_confidence": product.get("alias_confidence"),
            "data_status": product.get("data_status"),
            "field_confidence": product.get("field_confidence") or {},
            "field_confidence_summary": _field_confidence_summary(product),
        },
        "score_basis": {
            "hardware_score": "weight_g / sensor·dpi_max / polling_rate_hz / connection / battery_hours / switch_type / onboard_memory",
            "software_score": f"software（{software_raw or '无'}）+ onboard_memory；仅代表驱动支持事实，不代表驱动口碑。{software_note}",
            "grip_fit_score": "待 MCP：握法适配需要真实用户评价 / 博主测评验证",
            "hand_fit_score": "待 MCP：手型适配需要真实用户评价 / 博主测评验证",
            "game_type_fit_score": "待 MCP：适合游戏类型需要真实用户评价 / 博主测评验证",
            "click_system_score": f"click_system={click_type}：{click_pros}；风险：{click_risk}",
            "sentiment_score": "网友评价 / 博主测评 —— MCP 未接入，待采集（pending）",
            "overall_score.current_score": "硬件/驱动支持事实/点击系统 按权重归一化（剔除 pending 的体验口碑维度）",
            "overall_score.full_score_with_missing_as_zero": "把缺失的体验口碑维度按 0 计入后的保守占位分",
        },
    }


# --------------------------------------------------------------------------- #
# 双产品裁决（喂给 AnalysisAgent / ReportAgent）
# --------------------------------------------------------------------------- #
def _winner(scored: List[dict], key_fn) -> Optional[str]:
    if not scored:
        return None
    best = max(scored, key=key_fn)
    # 并列则标记为持平
    top = key_fn(best)
    leaders = [s for s in scored if abs(key_fn(s) - top) < 1e-9]
    if len(leaders) > 1:
        return "持平"
    return best.get("model")


def build_scoreboard(products: List[dict]) -> dict:
    """对一组产品出本地硬件事实基线 + 裁决；体验/口碑维度等待 MCP。"""
    scored = [score_product(p) for p in products]

    def by(path):
        return lambda s: _path(s, path) if _path(s, path) is not None else -1

    verdicts: Dict[str, Any] = {
        "strongest_overall": _winner(scored, by("overall_score.current_score")),
        "strongest_hardware": _winner(scored, lambda s: s.get("hardware_score") or -1),
        "best_software": _winner(scored, lambda s: s.get("software_score") or -1),
        "best_click_system": _winner(scored, lambda s: s.get("click_system_score") or -1),
        "best_for": {},
        "pending_verification": [
            "握法适配 / 手型适配 / 适合游戏类型不再由本地 JSON 推断，等待真实用户评价和博主测评。",
            "网友评价 / 博主测评（sentiment）尚未接入实时 MCP，相关结论标记为待验证。",
            "实时价格、驱动长期稳定性、电竞品牌影响力 / 长期口碑缺少实时数据，仅供参考。",
        ],
    }

    identification = [_identification_for(score) for score in scored]

    return {
        "scale": "0-100，越高越好",
        "score_type": "local_hardware_fact_baseline",
        "score_type_note": (
            "本地硬件事实基线只基于本地产品 JSON 中较稳定的硬件/官方事实计算，不是最终综合购买建议；"
            "握法、手型、适合游戏类型、网友评价、博主测评、实时价格和长期可靠性待 MCP 补齐。"
        ),
        "price_note": "price_range 仅作为参考价 / 历史参考区间展示，不参与当前核心评分；实时价格待 MCP 接入。",
        "not_final": True,
        "products": scored,
        "verdicts": verdicts,
        "identification": identification,
        "pending_dimensions": [
            "网友评价 / 博主测评",
            "握法 / 手型 / 适合游戏类型",
            "驱动长期稳定性",
            "实时价格",
            "长期可靠性",
        ],
    }


def _identification_for(score: dict) -> dict:
    """单个产品的"识别与变体说明"，供报告的产品识别区使用。"""
    identity = score.get("identity", {}) or {}
    field_summary = identity.get("field_confidence_summary") or {}
    return {
        "model": score.get("model"),
        "brand": score.get("brand"),
        "family": identity.get("family"),
        "variant_name": identity.get("variant_name"),
        "variant_type": identity.get("variant_type"),
        "shape_detail": identity.get("shape_detail") or "未标注",
        "click_system": (score.get("click_system", {}) or {}).get("type"),
        "official_name_confidence": identity.get("official_name_confidence"),
        "alias_confidence": identity.get("alias_confidence"),
        "data_status": identity.get("data_status"),
        "field_confidence": identity.get("field_confidence") or {},
        "field_confidence_summary": field_summary,
        "official_fields": field_summary.get("official", []),
        "review_verified_fields": field_summary.get("review_verified", []),
        "rule_inferred_fields": field_summary.get("rule_inferred", []),
        "community_unverified_fields": field_summary.get("community_unverified", []),
        "community_likely_fields": field_summary.get("community_likely", []),
        "hardware_based": "本地事实库只用于官方型号、重量、传感器、回报率、连接、续航、点击系统等稳定硬件事实。",
        "pending": "握法 / 手型 / 适合游戏类型 / 网友口碑 / 博主测评尚未接入 MCP，相关体验结论需后续验证。",
    }


def _path(obj: dict, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur
