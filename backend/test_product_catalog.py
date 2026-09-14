"""产品目录服务 / 接口基础测试。

运行方式（从 backend 目录）：
    python test_product_catalog.py
也兼容 pytest 收集（test_* 函数）。
"""

import os
import sys
from pathlib import Path

# 与其它测试一致：关闭 LLM / tracing，避免导入主应用时的外部依赖。
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGSMITH_TRACING", "false")
for _agent in ("RESEARCH", "EVIDENCE", "QUALITY"):
    os.environ.setdefault(f"{_agent}_AGENT_USE_LLM", "0")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from app.services import product_catalog_service as catalog
from api.routes import app  # 通过真实主应用验证路由已正确挂载

client = TestClient(app)


# --------------------------------------------------------------------------- #
# 服务层：别名/归一化解析
# --------------------------------------------------------------------------- #
def test_gpx2_resolves_to_superlight_2():
    product, matched_by, matched_value = catalog.resolve_product("gaming_mouse", "GPX2")
    assert product["id"] == "logitech-gpx-superlight-2", product["id"]
    assert product["brand"] == "Logitech"
    assert product["model"] == "G Pro X Superlight 2"
    assert matched_by == "alias"
    assert matched_value == "GPX2"


def test_viper_v3_pro_resolves():
    product, matched_by, matched_value = catalog.resolve_product("gaming_mouse", "Viper V3 Pro")
    assert product["id"] == "razer-viper-v3-pro", product["id"]
    assert product["brand"] == "Razer"
    assert matched_by in ("model", "alias"), matched_by


def test_complex_logitech_aliases_and_variants():
    # 普通狗屁王2仍然指向标准版，而不是 DEX / Superstrike。
    product, matched_by, _matched_value = catalog.resolve_product("gaming_mouse", "狗屁王2")
    assert product["id"] == "logitech-gpx-superlight-2"
    assert matched_by == "community_alias"

    dex, dex_by, _dex_value = catalog.resolve_product("gaming_mouse", "DEX")
    assert dex["id"] == "logitech-gpx-superlight-2-dex"
    assert dex_by == "alias"

    superstrike, super_by, _super_value = catalog.resolve_product("gaming_mouse", "GPW4朱雀")
    assert superstrike["id"] == "logitech-g-pro-x2-superstrike"
    assert super_by == "community_alias"


def test_community_alias_disambiguation_flags():
    zhuque = catalog.search_products_detailed("gaming_mouse", "朱雀")
    assert zhuque["count"] == 1
    assert zhuque["results"][0]["id"] == "logitech-g-pro-x2-superstrike"
    assert zhuque["needs_disambiguation"] is True
    assert "玩家圈简称" in zhuque["disambiguation_reason"]

    dukuai = catalog.search_products_detailed("gaming_mouse", "毒蝰")
    assert dukuai["needs_disambiguation"] is True
    assert len({item["id"] for item in dukuai["results"][:2]}) >= 2


def test_gpx2_dex_and_standard_have_different_molds():
    standard = catalog.resolve_product("gaming_mouse", "狗屁王2")[0]
    dex = catalog.resolve_product("gaming_mouse", "GPX2 DEX")[0]
    assert standard["mold_id"] != dex["mold_id"]
    assert standard["shape"] == "symmetrical"
    assert dex["shape"] == "ergonomic"


def test_field_confidence_present():
    product = catalog.resolve_product("gaming_mouse", "朱雀")[0]
    confidence = product.get("field_confidence", {})
    assert confidence["click_system"] == "review_verified"
    assert confidence["community_aliases"] == "community_unverified"
    search = catalog.search_products_detailed("gaming_mouse", "朱雀")
    identity = search["results"][0]["identity"]
    assert identity["field_confidence_summary"]["community_unverified"] == ["community_aliases"]


def test_normalization_ignores_case_space_hyphen():
    # 同一目标的多种写法都应解析到同一产品
    ids = {
        catalog.resolve_product("gaming_mouse", variant)[0]["id"]
        for variant in ("gpx2", "G-P-X-2", "  GPX 2 ", "gpX2")
    }
    assert ids == {"logitech-gpx-superlight-2"}, ids


def test_brand_prefix_and_missing_g_still_resolve_locally():
    # 用户经常省略 Logitech 产品名里的 G，或把品牌词写在前面；这仍应走本地事实库。
    product, matched_by, _matched_value = catalog.resolve_product(
        "gaming_mouse",
        "Logitech PRO X SUPERLIGHT 2",
    )
    assert product["id"] == "logitech-gpx-superlight-2"
    assert matched_by in {"model", "brand_model", "alias", "brand_alias"}


def test_future_or_unknown_model_does_not_resolve_by_family():
    # Viper V4 Pro is not in the local catalog. It must go to Search/OfficialSpec MCP,
    # not fall back to the broad Viper family and pretend to be Viper V3 Pro.
    for query in ("viper v4 pro", "Razer Viper V4 Pro"):
        try:
            catalog.resolve_product("gaming_mouse", query)
        except catalog.ProductNotFoundError:
            continue
        raise AssertionError(f"{query} should not resolve to a local product by family-only matching")


def test_unknown_product_raises():
    try:
        catalog.resolve_product("gaming_mouse", "completely-unknown-mouse-zzz")
    except catalog.ProductNotFoundError:
        return
    raise AssertionError("应抛 ProductNotFoundError")


def test_unknown_category_raises():
    try:
        catalog.list_products("not_a_category")
    except catalog.CategoryNotFoundError:
        return
    raise AssertionError("应抛 CategoryNotFoundError")


# --------------------------------------------------------------------------- #
# 服务层：对比
# --------------------------------------------------------------------------- #
def test_compare_returns_spec_differences():
    result = catalog.compare_products("gaming_mouse", "GPX2", "Viper V3 Pro")

    assert result["product_a"]["id"] == "logitech-gpx-superlight-2"
    assert result["product_b"]["id"] == "razer-viper-v3-pro"

    diffs = {d["field"]: d for d in result["spec_differences"]}
    # 必算字段都在
    for field in (
        "weight_g", "length", "width", "height", "dpi_max",
        "polling_rate_hz", "battery_hours", "connection", "shape",
        "software", "onboard_memory",
    ):
        assert field in diffs, f"缺少差异字段 {field}"

    # GPX2 60g vs Viper V3 Pro 54g -> diff = 6，A 较重，偏好 lower 时 B 占优
    weight = diffs["weight_g"]
    assert weight["a"] == 60 and weight["b"] == 54
    assert weight["diff"] == 6 and weight["abs_diff"] == 6
    assert weight["advantage"] == "b"

    # software 不同
    assert diffs["software"]["equal"] is False
    # 两者都板载存储
    assert diffs["onboard_memory"]["equal"] is True


def test_compare_missing_battery_for_wired_mouse():
    # ZOWIE EC2-C 是有线鼠标，battery_hours 为 null -> 进 missing_fields
    result = catalog.compare_products("gaming_mouse", "EC2-C", "GPX2")
    assert "battery_hours" in result["missing_fields"]["product_a"], result["missing_fields"]
    battery = next(d for d in result["spec_differences"] if d["field"] == "battery_hours")
    assert battery["comparable"] is False


def test_source_summary_present():
    result = catalog.compare_products("gaming_mouse", "GPX2", "Viper V3 Pro")
    summary = result["source_summary"]
    assert summary["product_a"]["official_count"] >= 1
    assert summary["product_b"]["official_count"] >= 1


# --------------------------------------------------------------------------- #
# 接口层：通过真实主应用调用
# --------------------------------------------------------------------------- #
def test_api_search():
    resp = client.get("/api/products/search", params={"q": "razer", "category": "gaming_mouse"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    first = body["results"][0]
    assert first["matched_by"] == "brand"
    assert first["matched_value"] == "Razer"
    assert "product" in first


def test_api_detail():
    resp = client.get("/api/products/gaming_mouse/logitech-gpx-superlight-2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"]["model"] == "G Pro X Superlight 2"
    assert body["matched_by"] == "id"


def test_api_compare():
    resp = client.post(
        "/api/products/compare",
        json={"category": "gaming_mouse", "product_a": "GPX2", "product_b": "Viper V3 Pro"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_by"]["product_a"]["resolved_id"] == "logitech-gpx-superlight-2"
    assert body["matched_by"]["product_b"]["resolved_id"] == "razer-viper-v3-pro"
    assert len(body["spec_differences"]) >= 11


def test_api_detail_404():
    resp = client.get("/api/products/gaming_mouse/no-such-mouse-zzz")
    assert resp.status_code == 404


def test_api_analysis_routes_untouched():
    # 回归保护：分析主流程接口仍存在（仅验证路由健在，不跑工作流）
    assert resp_ok("/health")


def resp_ok(path: str) -> bool:
    return client.get(path).status_code == 200


ALL_TESTS = [
    test_gpx2_resolves_to_superlight_2,
    test_viper_v3_pro_resolves,
    test_complex_logitech_aliases_and_variants,
    test_community_alias_disambiguation_flags,
    test_gpx2_dex_and_standard_have_different_molds,
    test_field_confidence_present,
    test_normalization_ignores_case_space_hyphen,
    test_brand_prefix_and_missing_g_still_resolve_locally,
    test_future_or_unknown_model_does_not_resolve_by_family,
    test_unknown_product_raises,
    test_unknown_category_raises,
    test_compare_returns_spec_differences,
    test_compare_missing_battery_for_wired_mouse,
    test_source_summary_present,
    test_api_search,
    test_api_detail,
    test_api_compare,
    test_api_detail_404,
    test_api_analysis_routes_untouched,
]


if __name__ == "__main__":
    for test in ALL_TESTS:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n产品目录测试全部通过（{len(ALL_TESTS)} 项）")
