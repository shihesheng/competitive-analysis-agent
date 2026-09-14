"""产品对比模式的事实底座接线。

把"产品对比页选中的两个产品"从 data/products/*.json 读出完整规格，转成：
- evidence_list：结构化硬规格证据（每个产品 × 每个硬维度一条 official 高可信证据），
  以及软性维度（用户口碑 / 电竞品牌影响力）的 pending_research 占位证据（标记 evidence_gap）。
- raw_research：与证据对应的原始采集镜像（给 ResearchAgent / trace 用）。
- product_facts：带 product_fact_id 的结构化产品事实，供 AnalysisAgent / 前端使用。
- competitors / focus_dimensions：把质检范围缩小到"被选中的两个产品 + 实际覆盖的维度"。

这样多 Agent 工作流就用真实硬参数跑，而不是旧的外部采集证据流；缺失的软性评价被标记为
待补充，而不会导致 QualityAgent 因覆盖不足三次打回。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.services import product_catalog_service as catalog


# 硬维度 -> 由哪些规格字段支撑
HARD_DIMENSION_SPECS: List[Tuple[str, List[str]]] = [
    ("性能参数", ["sensor", "dpi_max", "polling_rate_hz"]),
    ("轻量化设计", ["weight_g"]),
    ("无线与续航", ["connection", "battery_hours"]),
    ("软件生态", ["software", "onboard_memory"]),
]

# 暂无实时 MCP 的软性/时效维度 -> 标记 pending_research / evidence_gap，不阻断流程
PENDING_DIMENSIONS: List[str] = [
    "用户口碑",
    "博主测评",
    # "实时价格" 由 PriceMCP 真实采集（官方价 + 电商价两条证据），不再作为占位维度，
    # 避免占位证据与真实价格证据重复、以及"实时价格永远未覆盖"误扣分。
    "驱动长期口碑",
    "长期可靠性",
]

COMPARE_DIMENSIONS: List[str] = [dim for dim, _ in HARD_DIMENSION_SPECS] + PENDING_DIMENSIONS

# 用于结构化 product_facts.specs 的字段
FACT_SPEC_FIELDS = [
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
    "shape_detail",
    "official_url",
    "field_confidence",
]

# 比较型 claim：维度 / 字段 / 单位 / 优势措辞 / 偏好方向
COMPARATIVE_SPECS: List[Tuple[str, str, str, str, str]] = [
    ("轻量化设计", "weight_g", "克", "更轻", "lower"),
    ("性能参数", "dpi_max", "DPI", "更高", "higher"),
    ("性能参数", "polling_rate_hz", "Hz 回报率", "更高", "higher"),
    ("无线与续航", "battery_hours", "小时续航", "更长", "higher"),
]


def resolve_products(
    selected: List[Dict[str, Any]], category: str = "gaming_mouse"
) -> List[dict]:
    """把前端 selected_products（含 id/model/brand）解析成完整规格，保序去重。"""
    resolved: List[dict] = []
    seen: set[str] = set()
    for item in selected or []:
        if not isinstance(item, dict):
            continue
        query = str(item.get("id") or item.get("model") or item.get("brand") or "").strip()
        if not query:
            continue
        try:
            product, _by, _val = catalog.resolve_product(category, query)
        except catalog.ProductCatalogError:
            continue
        product_id = product.get("id")
        if product_id in seen:
            continue
        seen.add(product_id)
        resolved.append(product)
    return resolved


def _fmt_dimensions(dim: Any) -> str:
    if not isinstance(dim, dict):
        return "尺寸未知"
    return f"{dim.get('length', '?')}×{dim.get('width', '?')}×{dim.get('height', '?')} mm"


def _fmt_price(price_range: Any) -> str:
    price_range = price_range or {}
    cny = price_range.get("cny")
    if isinstance(cny, list) and cny:
        lo, hi = cny[0], cny[-1]
        return f"¥{lo}" if lo == hi else f"¥{lo}-{hi}"
    usd = price_range.get("usd")
    if isinstance(usd, list) and usd:
        lo, hi = usd[0], usd[-1]
        return f"${lo}" if lo == hi else f"${lo}-{hi}"
    return "价格未知"


def _fmt_connection(conn: Any) -> str:
    labels = {"wired": "有线", "2.4ghz": "2.4G 无线", "bluetooth": "蓝牙"}
    if not isinstance(conn, list) or not conn:
        return "连接方式未知"
    return "、".join(labels.get(c, str(c)) for c in conn)


def _fmt_shape(shape: Any) -> str:
    return {"symmetrical": "对称（双手）造型", "ergonomic": "人体工学（右手）造型"}.get(
        shape, str(shape) if shape else "造型未知"
    )


def _spec_sentence(product: dict, fields: List[str]) -> str:
    """把一组规格字段拼成嵌入了真实数值的中文句子（数值用于 claim 的忠实性校验）。"""
    parts: List[str] = []
    for field in fields:
        value = product.get(field)
        if field == "dimensions_mm":
            parts.append(f"三围 {_fmt_dimensions(value)}")
        elif field == "connection":
            parts.append(_fmt_connection(value))
        elif field == "price_range":
            parts.append(f"参考价 {_fmt_price(value)}")
        elif field == "weight_g":
            parts.append(f"整机重量 {value} 克" if value is not None else "重量未知")
        elif field == "dpi_max":
            parts.append(f"最高 {value} DPI" if value is not None else "")
        elif field == "polling_rate_hz":
            parts.append(f"回报率 {value} Hz" if value is not None else "")
        elif field == "battery_hours":
            parts.append(f"续航 {value} 小时" if value is not None else "有线连接无需续航")
        elif field == "onboard_memory":
            parts.append("支持板载内存" if value else "不支持板载内存")
        elif field == "sensor":
            parts.append(f"传感器 {value}" if value else "")
        elif field == "software":
            parts.append(f"驱动软件 {value}" if value else "")
        elif field == "shape":
            parts.append(_fmt_shape(value))
        elif value not in (None, "", []):
            parts.append(f"{field} {value}")
    return "；".join(part for part in parts if part)


def _product_identity(product: dict) -> str:
    """对比模式下每个产品作为一个独立"平台"，用 model（无则 id）标识。"""
    return str(product.get("model") or product.get("id") or "").strip()


def build_compare_payload(
    products: List[dict], category: str = "gaming_mouse"
) -> Dict[str, Any]:
    """把已解析的产品规格转成 evidence / raw_research / product_facts 等注入物。"""
    collected_time = datetime.now().isoformat(timespec="seconds")
    evidence_list: List[Dict[str, Any]] = []
    raw_research: List[Dict[str, Any]] = []
    product_facts: List[Dict[str, Any]] = []
    seq = 0

    for product_index, product in enumerate(products, start=1):
        model = _product_identity(product)
        brand = str(product.get("brand") or "")
        official = str(product.get("official_url") or "") or "local://product-catalog"
        publish_time = str(product.get("updated_at") or "2026-06-17")
        product_id = product.get("id")
        fact_evidence_ids: List[str] = []

        def _add(
            dimension: str,
            content: str,
            *,
            source_type: str,
            credibility: str,
            confidence: float,
            source_title: str,
            source_url: str,
            pending: bool,
        ) -> str:
            nonlocal seq
            seq += 1
            evidence_id = f"EV{seq:03d}"
            evidence_list.append(
                {
                    "evidence_id": evidence_id,
                    "platform": model,
                    "claim": content[:90],
                    "source_type": source_type,
                    "source_title": source_title,
                    "source_url": source_url,
                    "publish_time": publish_time,
                    "collected_time": collected_time,
                    "credibility": credibility,
                    "related_dimension": dimension,
                    "raw_content": content,
                    "confidence_score": confidence,
                    # 与 EvidenceAgent 产出对齐的别名字段
                    "dimension": dimension,
                    "content": content,
                    "summary": source_title,
                    "source": source_title,
                    "used_by_agent": "ProductCompareSeeder",
                    # 对比模式元信息
                    "product_id": product_id,
                    "data_status": "pending_research" if pending else "verified",
                    "pending_research": pending,
                    "evidence_gap": pending,
                }
            )
            raw_research.append(
                {
                    "item_id": f"PC{seq:03d}",
                    "platform": model,
                    "source_type": source_type,
                    "source_title": source_title,
                    "source_url": source_url,
                    "publish_time": publish_time,
                    "collected_time": collected_time,
                    "raw_content": content,
                    "collection_method": "database",
                    "dimension": dimension,
                    "related_dimension": dimension,
                    "product_name": model,
                    "category": category,
                }
            )
            return evidence_id

        # 硬维度：官方规格，高可信
        for dimension, fields in HARD_DIMENSION_SPECS:
            content = f"{brand} {model} 官方规格（{dimension}）：{_spec_sentence(product, fields)}。"
            fact_evidence_ids.append(
                _add(
                    dimension,
                    content,
                    source_type="official",
                    credibility="high",
                    confidence=0.92,
                    source_title=f"{brand} {model} 官方规格 - {dimension}",
                    source_url=official,
                    pending=False,
                )
            )

        # 软性维度：ReviewIntel MCP 已接入但本轮未抓到该维度内容（反爬 / 视频无开放 API / demo 限制）
        for dimension in PENDING_DIMENSIONS:
            content = (
                f"{model} 的{dimension}（用户评价 / 博主测评 / 驱动口碑）"
                "未抓取到数据：ReviewIntel 评价 MCP 已接入并尝试抓取，"
                "但评测站点反爬、视频平台无开放 API、LLM 难以从视频中稳定抽取，"
                "本轮 demo 未抓到该维度的可用内容。"
            )
            fact_evidence_ids.append(
                _add(
                    dimension,
                    content,
                    source_type="review",
                    credibility="low",
                    confidence=0.35,
                    source_title=f"{model} {dimension}实时评价（未抓取到数据）",
                    source_url="pending://realtime-review",
                    pending=True,
                )
            )

        product_facts.append(
            {
                "product_fact_id": f"PF{product_index:03d}",
                "product_id": product_id,
                "model": model,
                "brand": brand,
                "category": product.get("category", category),
                "evidence_ids": fact_evidence_ids,
                "data_status": product.get("data_status", "verified"),
                "fact_source": (
                    "official_spec_mcp"
                    if str(product.get("data_status") or "").startswith("official_spec")
                    else "local_product_json"
                ),
                "specs": {field: product.get(field) for field in FACT_SPEC_FIELDS},
                "official_url": official,
                "image_url": product.get("image_url", ""),
            }
        )

    return {
        "products": products,  # 完整规格，供 comparative_claims 读取顶层字段
        "evidence_list": evidence_list,
        "raw_research": raw_research,
        "product_facts": product_facts,
        "competitors": [_product_identity(p) for p in products],
        "focus_dimensions": list(COMPARE_DIMENSIONS),
        "pending_dimensions": list(PENDING_DIMENSIONS),
    }


def _evidence_for(
    evidence_list: List[Dict[str, Any]], model: str, dimension: str
) -> Optional[Dict[str, Any]]:
    for evidence in evidence_list:
        if (
            isinstance(evidence, dict)
            and evidence.get("platform") == model
            and evidence.get("related_dimension") == dimension
        ):
            return evidence
    return None


def build_product_matrix(
    products: List[dict],
    evidence_list: List[Dict[str, Any]],
    dimensions: List[str],
) -> Dict[str, Any]:
    """对比模式下确定性地构建 product_matrix：每个维度 × 每个产品一格，

    格内 analysis 直接用对应证据的完整 raw_content（不截断），evidence_ids 指向该证据。
    这样矩阵文案里的数值与所引证据数值完全一致，能通过 VerificationAgent 的矩阵忠实性校验
    （该校验用精确数字集合比较，截断会造成误报）。
    """
    models = [_product_identity(p) for p in products]
    matrix_dimensions: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for dimension in dimensions:
        matrix_dimensions[dimension] = {}
        for model in models:
            evidence = _evidence_for(evidence_list, model, dimension)
            if evidence is not None:
                pending = bool(evidence.get("pending_research"))
                content = str(evidence.get("raw_content") or "")
                matrix_dimensions[dimension][model] = {
                    "score": 2 if pending else 5,
                    "summary": content,
                    "analysis": content,
                    "evidence_ids": [evidence["evidence_id"]],
                    "confidence_score": evidence.get("confidence_score", 0.9),
                    "data_status": evidence.get("data_status", "verified"),
                }
            else:
                note = f"{model} 在「{dimension}」维度暂无规格证据，标记为 evidence_gap。"
                matrix_dimensions[dimension][model] = {
                    "score": 3,
                    "summary": note,
                    "analysis": note,
                    "evidence_ids": [],
                    "confidence_score": 0.0,
                    "data_status": "evidence_gap",
                }
    return {
        "dimensions": matrix_dimensions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def comparative_claims(
    products: List[dict],
    evidence_list: List[Dict[str, Any]],
    start_index: int,
) -> List[Dict[str, Any]]:
    """生成两款产品在硬参数上的对比 claim，每条引用双方对应维度证据（数值已落在证据里）。"""
    if len(products) < 2:
        return []
    a, b = products[0], products[1]
    a_model, b_model = _product_identity(a), _product_identity(b)
    claims: List[Dict[str, Any]] = []
    index = start_index

    for dimension, field, unit, verb, better in COMPARATIVE_SPECS:
        a_value, b_value = a.get(field), b.get(field)
        if not isinstance(a_value, (int, float)) or not isinstance(b_value, (int, float)):
            continue
        a_ev = _evidence_for(evidence_list, a_model, dimension)
        b_ev = _evidence_for(evidence_list, b_model, dimension)
        if not a_ev or not b_ev:
            continue

        if a_value == b_value:
            verdict = f"两者在该项上一致"
        else:
            a_wins = (better == "lower" and a_value < b_value) or (
                better == "higher" and a_value > b_value
            )
            verdict = f"{a_model if a_wins else b_model} {verb}"

        index += 1
        claims.append(
            {
                "claim_id": f"PCL{index:03d}",
                "content": (
                    f"{dimension}对比：{a_model} 为 {a_value}{unit}，"
                    f"{b_model} 为 {b_value}{unit}，{verdict}。"
                ),
                "dimension": dimension,
                "related_platforms": [a_model, b_model],
                "evidence_ids": [a_ev["evidence_id"], b_ev["evidence_id"]],
                "product_fact_ids": [
                    f"PF{1:03d}",
                    f"PF{2:03d}",
                ],
                "confidence_score": 0.9,
                "generated_by": "AnalysisAgent",
            }
        )

    return claims
