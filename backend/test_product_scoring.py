"""Product scoring and final report tests."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("ENABLE_LANGSMITH", "false")
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"
os.environ["EVIDENCE_AGENT_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import product_catalog_service as catalog
from app.services import product_scoring_service as scoring


def _score(query: str) -> dict:
    product, _by, _val = catalog.resolve_product("gaming_mouse", query)
    return scoring.score_product(product)


def test_gpx2_and_viper_scores_differ():
    gpx2 = _score("GPX2")
    viper = _score("Viper V3 Pro")
    assert gpx2["overall_score"] != viper["overall_score"]
    assert viper["hardware_score"] > gpx2["hardware_score"]


def test_no_two_distinct_products_share_overall():
    ids = ["GPX2", "Viper V3 Pro", "G502 X Plus", "EC2-C", "Model O 2 Wireless"]
    overalls = [_score(q)["overall_score"]["current_score"] for q in ids]
    assert len(set(overalls)) == len(overalls), overalls


def test_current_vs_full_with_missing():
    score = _score("GPX2")
    assert score["overall_score"]["full_score_with_missing_as_zero"] <= score["overall_score"]["current_score"]
    assert score["sentiment_score"] is None
    assert score["sentiment_status"] == "pending"
    assert score["pending_dimensions"]


def test_driverless_software_not_punished():
    score = _score("EC2-C")
    assert 65 <= score["software_score"] <= 85


def test_scoreboard_verdicts():
    gpx2 = catalog.resolve_product("gaming_mouse", "GPX2")[0]
    viper = catalog.resolve_product("gaming_mouse", "Viper V3 Pro")[0]
    board = scoring.build_scoreboard([gpx2, viper])
    assert board["score_type"] == "local_hardware_fact_baseline"
    assert board["verdicts"]["strongest_overall"] == "Viper V3 Pro"
    assert board["verdicts"]["pending_verification"]
    assert board["identification"][0]["mold_id"]


def test_superstrike_click_system_and_field_confidence():
    standard = _score("GPX2")
    superstrike = _score("G PRO X2 SUPERSTRIKE")

    assert standard["click_system"]["type"] == "hybrid"
    assert superstrike["click_system"]["type"] == "haptic"
    assert superstrike["click_system_score"] > standard["click_system_score"]

    identity = superstrike["identity"]
    assert identity["field_confidence_summary"]["review_verified"]
    assert identity["field_confidence_summary"]["community_unverified"] == ["community_aliases"]


def test_dex_is_not_standard_gpx2_mold():
    standard = _score("GPX2")
    dex = _score("DEX")
    assert standard["identity"]["mold_id"] != dex["identity"]["mold_id"]
    assert dex["identity"]["variant_name"] == "DEX"
    assert dex["identity"]["shape"] != standard["identity"]["shape"]


def test_report_uses_professional_schema():
    from api.routes import AnalysisRequest, _build_initial_state
    from orchestration.workflow import app as workflow_app

    request = AnalysisRequest(
        industry_key="gaming_mouse",
        target_platform="G Pro X Superlight 2",
        competitors=["G Pro X Superlight 2", "Viper V3 Pro"],
        analysis_scene="comparison",
        target_user="buyer",
        time_range="last two years",
        focus_dimensions=[],
        selected_products=[{"id": "logitech-gpx-superlight-2"}, {"id": "razer-viper-v3-pro"}],
    )
    final = workflow_app.invoke(_build_initial_state(request), {"recursion_limit": 80})

    quality = final["quality_result"]
    assert quality["score_type"] == "report_credibility"
    assert quality["quality_score"] < 90
    assert quality["pending_data"]

    report = final["final_report"]
    assert report["schema_name"] == "gaming_mouse_competitive_report"
    assert report["product_identification"]
    assert report["hardware_specs"]
    assert report["feature_tree"]
    assert report["pricing_model"]["status"] == "pending"
    assert report["user_persona"]["status"] == "insufficient_evidence"
    assert report["score_flow"]["baseline_score"]["label"]
    assert report["agent_contributions"]
    assert report["final_recommendation"]

ALL_TESTS = [
    test_gpx2_and_viper_scores_differ,
    test_no_two_distinct_products_share_overall,
    test_current_vs_full_with_missing,
    test_driverless_software_not_punished,
    test_scoreboard_verdicts,
    test_superstrike_click_system_and_field_confidence,
    test_dex_is_not_standard_gpx2_mold,
    test_report_uses_professional_schema,
]


if __name__ == "__main__":
    for test in ALL_TESTS:
        test()
        print(f"PASS {test.__name__}")
