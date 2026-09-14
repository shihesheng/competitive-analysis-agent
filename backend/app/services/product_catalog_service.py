"""产品规格事实底座的读取 / 搜索 / 对比服务（只读）。

数据源：`data/products/{category}.json`（结构化硬件参数事实底座，由
`gaming_mice.json` 等文件组成），与后续 MCP 证据流（ResearchProvider /
MCP 采集库）相互独立，互不影响分析主流程。

对外能力：
- load_catalog / list_products      读取整张品类表
- search_products                   按 q 模糊搜索（匹配 id/brand/model/aliases）
- resolve_product                   解析单个查询到唯一最佳产品（详情 / 对比用）
- compare_products                  两款产品的逐字段差异 + 缺失字段 + 来源摘要

匹配规则：忽略大小写、空格、连字符（以及下划线）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# backend/app/services/product_catalog_service.py -> parents[3] = 项目根目录
CATALOG_DIR = Path(__file__).resolve().parents[3] / "data" / "products"

# 合法品类名（同时用于防御路径穿越，category 来自 HTTP path/query）
_SAFE_CATEGORY = re.compile(r"^[A-Za-z0-9_-]+$")

# 归一化：去掉空格 / 连字符 / 下划线并转小写
_NORMALIZE_RE = re.compile(r"[\s\-_]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_BRAND_TOKENS = {
    "asus",
    "benq",
    "corsair",
    "endgame",
    "gear",
    "glorious",
    "lamzu",
    "logi",
    "logitech",
    "pulsar",
    "razer",
    "rog",
    "steelseries",
    "vgn",
    "wlmouse",
    "zowie",
}

# 各匹配字段的优先级权重（同等匹配质量下，越具体的字段越优先）
_FIELD_WEIGHT = {
    "id": 5,
    "model": 4,
    "brand_model": 4,
    "alias": 3,
    "brand_alias": 3,
    "community_alias": 3,
    "family": 2,
    "brand": 1,
}

# 官方可信字段 vs 玩家圈/系列字段（用于结果可信度与消歧）
_VERIFIED_MATCH_FIELDS = {"id", "model", "brand_model", "alias", "brand_alias"}


class ProductCatalogError(Exception):
    """产品目录相关错误基类。"""


class CategoryNotFoundError(ProductCatalogError):
    """品类数据文件不存在或品类名非法。"""


class ProductNotFoundError(ProductCatalogError):
    """在指定品类中找不到匹配的产品。"""


# 进程内缓存：品类 JSON 在运行期是静态的，加载一次即可。
# 以信封内的 `category` 字段（如 gaming_mouse）作为权威键，文件名（如
# gaming_mice）仅作为附加别名 —— 这样文件名与品类键不一致也能正确解析。
_CATALOGS: Dict[str, dict] = {}   # 权威品类键 -> 信封
_ALIASES: Dict[str, str] = {}     # 品类键 / 文件名 stem -> 权威品类键
_LOADED = False


def normalize(text: Any) -> str:
    """归一化文本用于匹配：小写 + 去空格/连字符/下划线。"""
    return _NORMALIZE_RE.sub("", str(text).strip().lower())


def _tokens(text: Any) -> List[str]:
    return _TOKEN_RE.findall(str(text or "").strip().lower())


def _dedupe_adjacent(tokens: List[str]) -> List[str]:
    deduped: List[str] = []
    for token in tokens:
        if not deduped or deduped[-1] != token:
            deduped.append(token)
    return deduped


def _variant_strings(text: Any) -> set[str]:
    """为实体匹配生成宽松变体。

    例如 `Logitech PRO X SUPERLIGHT 2` 可以匹配到本地 `G Pro X Superlight 2`：
    去品牌词后是 `proxsuperlight2`，去掉 Logitech 产品名前缀 `G` 后也是同一串。
    """
    normalized = normalize(text)
    tokens = _dedupe_adjacent(_tokens(text))
    variants = {normalized} if normalized else set()
    if not tokens:
        return variants

    variants.add("".join(tokens))
    no_brand = [token for token in tokens if token not in _BRAND_TOKENS]
    if no_brand:
        variants.add("".join(no_brand))
        if no_brand[0] == "g" and len(no_brand) > 1:
            variants.add("".join(no_brand[1:]))
    if tokens[0] == "g" and len(tokens) > 1:
        variants.add("".join(tokens[1:]))
    return {variant for variant in variants if variant}


def clear_cache() -> None:
    """清空品类缓存（测试或数据热更新时使用）。"""
    global _LOADED
    _LOADED = False
    _CATALOGS.clear()
    _ALIASES.clear()


# 图片相关字段：保证每个产品对外返回时一定带这三个键（前端据此渲染卡片/占位图）。
IMAGE_FIELDS = ("image_url", "image_alt", "image_source_url")

DEFAULT_FIELD_CONFIDENCE = {
    "weight_g": "official",
    "dimensions_mm": "official",
    "sensor": "official",
    "dpi_max": "official",
    "polling_rate_hz": "official",
    "battery_hours": "official",
    "switch_type": "official",
    "software": "official",
    "mold_id": "rule_inferred",
    "shape_detail": "rule_inferred",
    "click_system": "official",
    "community_aliases": "community_likely",
}


def _ensure_image_fields(product: dict) -> None:
    """补齐图片字段，缺失则置空；image_alt 兜底用 品牌+型号，避免空 alt。"""
    for key in IMAGE_FIELDS:
        product.setdefault(key, "")
    if not product.get("image_alt"):
        brand = str(product.get("brand", "")).strip()
        model = str(product.get("model", "")).strip()
        product["image_alt"] = f"{brand} {model}".strip()


def _derive_click_system(switch_type: Any) -> str:
    text = str(switch_type or "")
    if "混合" in text or "hybrid" in text.lower() or "lightforce" in text.lower():
        return "hybrid"
    if "光学" in text or "optical" in text.lower():
        return "optical"
    if text:
        return "mechanical"
    return "unknown"


def _ensure_identity_fields(product: dict) -> None:
    """补齐产品身份/变体字段，保证对外返回一定带这些键（旧数据/新品类也安全）。

    只在缺失时补默认值，不覆盖已有值；mold_id/shape_detail 缺失时留空，
    让评分侧据此降低 shape_confidence，而不是乱给高分。
    """
    product.setdefault("family", product.get("model", ""))
    product.setdefault("variant_name", "Standard")
    product.setdefault("variant_type", "official_model")
    product.setdefault("mold_id", "")
    product.setdefault("shape_detail", "")
    product.setdefault("community_aliases", [])
    product.setdefault("alias_confidence", "likely")
    product.setdefault("official_name_confidence", "verified")
    product.setdefault("data_status", "verified")
    field_confidence = dict(DEFAULT_FIELD_CONFIDENCE)
    if product.get("battery_hours") is None:
        field_confidence["battery_hours"] = "pending"
    if product.get("alias_confidence") == "unverified":
        field_confidence["community_aliases"] = "community_unverified"
    if isinstance(product.get("field_confidence"), dict):
        field_confidence.update(product["field_confidence"])
    product["field_confidence"] = field_confidence
    if not product.get("click_system"):
        product["click_system"] = _derive_click_system(product.get("switch_type"))


def _field_confidence_summary(product: dict) -> Dict[str, List[str]]:
    """按可信度分组字段名，供前端/报告展示字段来源。"""
    field_confidence = product.get("field_confidence")
    if not isinstance(field_confidence, dict):
        return {}
    grouped: Dict[str, List[str]] = {}
    for field, confidence in field_confidence.items():
        key = str(confidence or "pending")
        grouped.setdefault(key, []).append(str(field))
    return {key: sorted(values) for key, values in grouped.items()}


def _ensure_loaded() -> None:
    """扫描 data/products/*.json，按信封 category 建立索引（幂等）。"""
    global _LOADED
    if _LOADED:
        return
    _CATALOGS.clear()
    _ALIASES.clear()
    if CATALOG_DIR.exists():
        for path in sorted(CATALOG_DIR.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue  # 单个坏文件不阻断其它品类
            products = data.get("products")
            if not isinstance(products, list):
                # data/products/ also contains auxiliary stores such as
                # gaming_mice_reviews.json. They may share category=gaming_mouse,
                # but they are not hardware product catalogs.
                continue
            canonical = str(data.get("category") or path.stem).strip()
            if not canonical:
                continue
            for product in products:
                if isinstance(product, dict):
                    _ensure_image_fields(product)
                    _ensure_identity_fields(product)
            _CATALOGS[canonical] = data
            _ALIASES[canonical] = canonical
            _ALIASES.setdefault(path.stem, canonical)  # 文件名 stem 作为别名（gaming_mice -> gaming_mouse）
    _LOADED = True


def available_categories() -> List[str]:
    """列出可用的权威品类键（按信封 category 字段）。"""
    _ensure_loaded()
    return sorted(_CATALOGS.keys())


def load_catalog(category: str) -> dict:
    """读取某品类的完整信封（含 products 数组）。找不到则抛 CategoryNotFoundError。

    category 可传品类键（gaming_mouse）或文件名 stem（gaming_mice），均能解析。
    """
    category = (category or "").strip()
    if not category or not _SAFE_CATEGORY.match(category):
        raise CategoryNotFoundError(f"非法或为空的品类名: {category!r}")
    _ensure_loaded()
    canonical = _ALIASES.get(category)
    if canonical is None:
        raise CategoryNotFoundError(
            f"未找到品类数据: {category}（data/products/ 下没有 category={category} 的文件）"
        )
    return _CATALOGS[canonical]


def list_products(category: str) -> List[dict]:
    """返回某品类下全部产品列表。"""
    catalog = load_catalog(category)
    products = catalog.get("products", [])
    return products if isinstance(products, list) else []


# --------------------------------------------------------------------------- #
# 匹配 / 搜索
# --------------------------------------------------------------------------- #
def _iter_candidates(product: dict):
    """产出 (matched_by, 原始值) 候选，顺序无关，排序由权重决定。

    匹配范围：id / model / 官方 aliases / 玩家圈 community_aliases / family / brand。
    """
    yield "id", str(product.get("id", ""))
    yield "model", str(product.get("model", ""))
    brand = str(product.get("brand", ""))
    model = str(product.get("model", ""))
    if brand and model:
        yield "brand_model", f"{brand} {model}"
    for alias in product.get("aliases", []) or []:
        yield "alias", str(alias)
        if brand:
            yield "brand_alias", f"{brand} {alias}"
    for alias in product.get("community_aliases", []) or []:
        yield "community_alias", str(alias)
    yield "family", str(product.get("family", ""))
    yield "brand", str(product.get("brand", ""))


def _match_quality_variant(nq: str, ns: str) -> int:
    """匹配质量：3=完全相等，2=前缀，1=包含，0=不匹配（均基于归一化串）。"""
    if not ns or not nq:
        return 0
    if ns == nq:
        return 3
    if ns.startswith(nq):
        return 2
    if nq in ns:
        return 1
    return 0


def _best_match(product: dict, query: Any) -> Optional[Tuple[tuple, str, str]]:
    """返回该产品对查询的最佳匹配 (sortkey, matched_by, matched_value)，无匹配返回 None。

    sortkey = (匹配质量, 原始串是否完全相等, 字段权重, -匹配值长度)，越大越优。
    """
    best: Optional[Tuple[tuple, str, str]] = None
    query_variants = _variant_strings(query)
    for field, value in _iter_candidates(product):
        source_variants = _variant_strings(value)
        quality = max(
            (_match_quality_variant(nq, ns) for nq in query_variants for ns in source_variants),
            default=0,
        )
        if quality == 0:
            continue
        field_weight = _FIELD_WEIGHT[field]
        if field == "id" and normalize(value) != normalize(query):
            field_weight = 2
        sortkey = (quality, 1 if normalize(value) == normalize(query) else 0, field_weight, -len(normalize(value)))
        if best is None or sortkey > best[0]:
            best = (sortkey, field, value)
    return best


def _identity_summary(product: dict) -> dict:
    """给搜索卡片用的精简身份信息。"""
    return {
        "family": product.get("family"),
        "variant_name": product.get("variant_name"),
        "variant_type": product.get("variant_type"),
        "mold_id": product.get("mold_id"),
        "shape": product.get("shape"),
        "shape_detail": product.get("shape_detail"),
        "weight_g": product.get("weight_g"),
        "connection": product.get("connection") or [],
        "click_system": product.get("click_system"),
        "alias_confidence": product.get("alias_confidence"),
        "official_name_confidence": product.get("official_name_confidence"),
        "data_status": product.get("data_status"),
        "field_confidence": product.get("field_confidence") or {},
        "field_confidence_summary": _field_confidence_summary(product),
    }


def _match_confidence(matched_by: str, product: dict) -> str:
    """结果可信度：官方字段=verified；玩家圈简称取产品 alias_confidence；family/brand 单列。"""
    if matched_by in _VERIFIED_MATCH_FIELDS:
        return "verified"
    if matched_by == "community_alias":
        return str(product.get("alias_confidence") or "likely")
    return matched_by  # family / brand


def search_products(category: str, q: str) -> List[dict]:
    """模糊搜索，返回按相关度降序排列的结果列表。

    每条结果含 matched_by / matched_value / match_quality / match_confidence / identity，以及完整 product。
    """
    products = list_products(category)  # 触发 CategoryNotFoundError
    if not normalize(q):
        return []

    scored: List[Tuple[tuple, str, str, dict]] = []
    for product in products:
        match = _best_match(product, q)
        if match is None:
            continue
        sortkey, matched_by, matched_value = match
        scored.append((sortkey, matched_by, matched_value, product))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": product.get("id"),
            "brand": product.get("brand"),
            "model": product.get("model"),
            "matched_by": matched_by,
            "matched_value": matched_value,
            "match_quality": sortkey[0],  # 3=完全相等 2=前缀 1=包含
            "match_confidence": _match_confidence(matched_by, product),
            "identity": _identity_summary(product),
            "product": product,
        }
        for (sortkey, matched_by, matched_value, product) in scored
    ]


def search_products_detailed(category: str, q: str) -> dict:
    """搜索 + 消歧：返回 {results, needs_disambiguation, disambiguation_reason}。

    - 命中唯一明确产品 -> 直接返回，needs_disambiguation=False。
    - 命中多个同等候选 -> 全部返回，needs_disambiguation=True（让前端让用户选）。
    - 命中的是 unverified 玩家圈简称 -> 标记 needs_disambiguation=True 并给出原因。
    """
    results = search_products(category, q)
    needs = False
    reason: Optional[str] = None

    if results:
        top_quality = results[0]["match_quality"]
        top = [r for r in results if r["match_quality"] == top_quality]
        distinct_ids = {r["id"] for r in top}

        if len(distinct_ids) > 1:
            needs = True
            matched_fields = {r["matched_by"] for r in top}
            if matched_fields <= {"community_alias"}:
                reason = "该名称为玩家圈简称，未确认对应唯一官方型号"
            elif matched_fields <= {"family", "brand"}:
                reason = "该名称是系列 / 品牌名，请选择系列下的具体官方型号"
            else:
                reason = "匹配到多个候选型号，请选择具体官方型号"
        else:
            single = top[0]
            if single["matched_by"] == "community_alias" and single["match_confidence"] == "unverified":
                needs = True
                reason = "该名称为玩家圈简称，未确认对应唯一官方型号"
            elif single["matched_by"] == "family" and single["match_confidence"] == "family":
                # family 唯一命中（系列下只有一个型号）不算歧义；保持 needs=False
                pass

    return {
        "results": results,
        "count": len(results),
        "needs_disambiguation": needs,
        "disambiguation_reason": reason,
    }


def resolve_product(category: str, query: str) -> Tuple[dict, str, str]:
    """把单个查询解析成唯一最佳产品，返回 (product, matched_by, matched_value)。

    找不到抛 ProductNotFoundError；品类不存在抛 CategoryNotFoundError。
    """
    products = list_products(category)
    if not normalize(query):
        raise ProductNotFoundError("查询不能为空")

    best: Optional[Tuple[tuple, str, str, dict]] = None
    for product in products:
        match = _best_match(product, query)
        if match is None:
            continue
        sortkey, matched_by, matched_value = match
        if best is None or sortkey > best[0]:
            best = (sortkey, matched_by, matched_value, product)

    if best is None:
        raise ProductNotFoundError(f"在品类 '{category}' 中未找到匹配 '{query}' 的产品")

    _sortkey, matched_by, matched_value, product = best
    if matched_by in {"brand", "family"}:
        raise ProductNotFoundError(
            f"'{query}' only matched broad {matched_by} '{matched_value}', not a concrete product model"
        )
    return product, matched_by, matched_value


# --------------------------------------------------------------------------- #
# 对比
# --------------------------------------------------------------------------- #
def _is_missing(value: Any) -> bool:
    """字段是否缺失（用于对比）：None / 空串 / 空列表。注意 False/0 不算缺失。"""
    return value is None or value == "" or value == []


def _advantage(a: Any, b: Any, preferred: Optional[str]) -> Optional[str]:
    """根据指标偏好方向推断占优方（启发式）：'a' / 'b' / 'equal' / None。"""
    if a == b:
        return "equal"
    if preferred == "lower":
        return "a" if a < b else "b"
    if preferred == "higher":
        return "a" if a > b else "b"
    return None


def _numeric_entry(field: str, label: str, preferred: Optional[str], a: Any, b: Any) -> dict:
    entry = {
        "field": field,
        "label": label,
        "type": "numeric",
        "preferred": preferred,  # lower=越低越好 / higher=越高越好 / None=无偏好
        "a": a,
        "b": b,
    }
    if _is_missing(a) or _is_missing(b):
        entry.update({"comparable": False, "diff": None, "abs_diff": None, "equal": None, "advantage": None})
    else:
        diff = round(a - b, 3)  # 四舍五入到 3 位，去除 125-127.1 这类浮点噪声
        entry.update(
            {
                "comparable": True,
                "diff": diff,            # a - b
                "abs_diff": abs(diff),
                "equal": diff == 0,
                "advantage": _advantage(a, b, preferred),
            }
        )
    return entry


def _spec_differences(pa: dict, pb: dict) -> Tuple[List[dict], Dict[str, List[str]]]:
    """逐字段差异 + 缺失字段。输出顺序固定，便于前端稳定渲染。"""
    diffs: List[dict] = []
    missing: Dict[str, List[str]] = {"product_a": [], "product_b": []}

    def record_missing(field: str, a_val: Any, b_val: Any) -> None:
        if _is_missing(a_val):
            missing["product_a"].append(field)
        if _is_missing(b_val):
            missing["product_b"].append(field)

    # 1) 重量（越轻越好）
    a, b = pa.get("weight_g"), pb.get("weight_g")
    diffs.append(_numeric_entry("weight_g", "重量 (g)", "lower", a, b))
    record_missing("weight_g", a, b)

    # 2) 三围 length / width / height（尺寸无统一偏好）
    a_dim = pa.get("dimensions_mm") or {}
    b_dim = pb.get("dimensions_mm") or {}
    for sub, label in (("length", "长度 (mm)"), ("width", "宽度 (mm)"), ("height", "高度 (mm)")):
        a, b = a_dim.get(sub), b_dim.get(sub)
        entry = _numeric_entry(sub, label, None, a, b)
        entry["group"] = "dimensions_mm"
        diffs.append(entry)
        record_missing(sub, a, b)

    # 3) DPI / 回报率 / 续航（数值越高越好）
    for field, label in (("dpi_max", "最高 DPI"), ("polling_rate_hz", "回报率 (Hz)"), ("battery_hours", "续航 (小时)")):
        a, b = pa.get(field), pb.get(field)
        diffs.append(_numeric_entry(field, label, "higher", a, b))
        record_missing(field, a, b)

    # 4) 连接方式（集合差异）
    a_conn = pa.get("connection") or []
    b_conn = pb.get("connection") or []
    set_a, set_b = set(a_conn), set(b_conn)
    diffs.append(
        {
            "field": "connection",
            "label": "连接方式",
            "type": "set",
            "a": a_conn,
            "b": b_conn,
            "common": sorted(set_a & set_b),
            "only_a": sorted(set_a - set_b),
            "only_b": sorted(set_b - set_a),
            "equal": set_a == set_b,
            "comparable": bool(a_conn) and bool(b_conn),
        }
    )
    record_missing("connection", a_conn, b_conn)

    # 5) 形状 / 软件（类别相等性）
    for field, label in (("shape", "形状"), ("software", "软件")):
        a, b = pa.get(field), pb.get(field)
        entry = {"field": field, "label": label, "type": "categorical", "a": a, "b": b}
        if _is_missing(a) or _is_missing(b):
            entry.update({"comparable": False, "equal": None})
        else:
            entry.update({"comparable": True, "equal": normalize(a) == normalize(b)})
        diffs.append(entry)
        record_missing(field, a, b)

    # 6) 板载内存（布尔；False 是有效值，仅 None 视为缺失）
    a, b = pa.get("onboard_memory"), pb.get("onboard_memory")
    entry = {"field": "onboard_memory", "label": "板载内存", "type": "boolean", "a": a, "b": b}
    if a is None or b is None:
        entry.update({"comparable": False, "equal": None})
    else:
        entry.update({"comparable": True, "equal": a == b})
    diffs.append(entry)
    if a is None:
        missing["product_a"].append("onboard_memory")
    if b is None:
        missing["product_b"].append("onboard_memory")

    missing["product_a"] = sorted(set(missing["product_a"]))
    missing["product_b"] = sorted(set(missing["product_b"]))
    return diffs, missing


def _summarize_sources(product: dict) -> dict:
    sources = product.get("sources") or []
    return {
        "official_url": product.get("official_url"),
        "updated_at": product.get("updated_at"),
        "source_count": len(sources),
        "official_count": sum(1 for s in sources if isinstance(s, dict) and s.get("source_type") == "official"),
        "publishers": [s.get("publisher") for s in sources if isinstance(s, dict)],
        "sources": sources,
    }


def compare_products(category: str, query_a: str, query_b: str) -> dict:
    """对比两款产品，返回完整对比结构。"""
    product_a, by_a, val_a = resolve_product(category, query_a)
    product_b, by_b, val_b = resolve_product(category, query_b)

    spec_differences, missing_fields = _spec_differences(product_a, product_b)

    # 基于真实硬件 JSON 计算的产品评分（与报告 quality_score 无关）。
    from app.services import product_scoring_service

    scoreboard = product_scoring_service.build_scoreboard([product_a, product_b])

    return {
        "category": category,
        "product_a": product_a,
        "product_b": product_b,
        "product_scores": {
            "product_a": scoreboard["products"][0],
            "product_b": scoreboard["products"][1],
            "verdicts": scoreboard["verdicts"],
            "identification": scoreboard.get("identification", []),
            "scale": scoreboard["scale"],
            "score_type": scoreboard.get("score_type"),
            "score_type_note": scoreboard["score_type_note"],
            "price_note": scoreboard.get("price_note", ""),
            "not_final": scoreboard.get("not_final", True),
            "pending_dimensions": scoreboard.get("pending_dimensions", []),
        },
        "matched_by": {
            "product_a": {
                "input": query_a,
                "matched_by": by_a,
                "matched_value": val_a,
                "resolved_id": product_a.get("id"),
            },
            "product_b": {
                "input": query_b,
                "matched_by": by_b,
                "matched_value": val_b,
                "resolved_id": product_b.get("id"),
            },
        },
        "spec_differences": spec_differences,
        "missing_fields": missing_fields,
        "source_summary": {
            "product_a": _summarize_sources(product_a),
            "product_b": _summarize_sources(product_b),
        },
    }
