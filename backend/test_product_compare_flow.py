"""Backend product-comparison workflow tests.

Run from the repository root:
    backend\\venv\\Scripts\\python.exe backend\\test_product_compare_flow.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("ENABLE_LANGSMITH", "false")
os.environ["SEARCH_PROVIDER"] = "disabled"
os.environ["OFFICIAL_SPEC_USE_LLM"] = "0"
for _agent in ("RESEARCH", "EVIDENCE", "QUALITY"):
    os.environ[f"{_agent}_AGENT_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routes import AnalysisRequest, _build_initial_state
from orchestration.workflow import app as workflow_app


EXPECTED_TRACE = [
    "ResearchAgent",
    "CollectorAgent",
    "EvidenceAgent",
    "AnalysisAgent",
    "VerificationAgent",
    "QualityAgent",
    "ReportAgent",
]


def _run(initial_state: dict) -> dict:
    final = dict(initial_state)
    for event in workflow_app.stream(initial_state, {"recursion_limit": 80}, stream_mode="updates"):
        for _node_name, update in event.items():
            if isinstance(update, dict):
                final.update(update)
    return final


def _request(product_a: dict, product_b: dict) -> AnalysisRequest:
    a_name = product_a.get("model") or product_a.get("id") or "product-a"
    b_name = product_b.get("model") or product_b.get("id") or "product-b"
    return AnalysisRequest(
        industry_key="gaming_mouse",
        target_platform=a_name,
        competitors=[a_name, b_name],
        analysis_scene="gaming mouse product comparison",
        target_user="gaming peripheral buyer",
        time_range="last two years",
        focus_dimensions=[],
        selected_products=[product_a, product_b],
    )


def _gpx2_viper_request() -> AnalysisRequest:
    return _request(
        {
            "id": "logitech-gpx-superlight-2",
            "model": "G Pro X Superlight 2",
            "brand": "Logitech",
            "category": "gaming_mouse",
        },
        {
            "id": "razer-viper-v3-pro",
            "model": "Viper V3 Pro",
            "brand": "Razer",
            "category": "gaming_mouse",
        },
    )


def _zhuque_dex_request() -> AnalysisRequest:
    return _request(
        {"model": "\u6731\u96c0", "category": "gaming_mouse"},
        {"model": "DEX", "category": "gaming_mouse"},
    )


def test_initial_state_keeps_inputs_only():
    state = _build_initial_state(_gpx2_viper_request())
    assert state["product_compare_mode"] is True
    assert len(state["selected_products"]) == 2
    assert state["resolved_products"] == []
    assert state["product_facts"] == []
    assert state["official_spec_records"] == []
    assert state["evidence_list"] == []
    assert state["claims"] == []
    return state


def test_free_text_entry_uses_product_compare_mode():
    request = AnalysisRequest(
        industry_key="gaming_mouse",
        target_platform="Logitech",
        competitors=["Logitech", "Razer"],
        analysis_scene="gaming mouse competitive analysis",
        target_user="product manager",
        time_range="last two years",
        focus_dimensions=["performance"],
    )
    state = _build_initial_state(request)
    assert state["product_compare_mode"] is True
    assert state["selected_products"] == []
    assert state["original_product_inputs"] == ["Logitech", "Razer"]
    assert state["evidence_list"] == []


def test_full_workflow_gpx2_viper():
    final = _run(_build_initial_state(_gpx2_viper_request()))

    trace_names = [item.get("agent_name") for item in final.get("trace_log", [])]
    for agent_name in EXPECTED_TRACE:
        assert agent_name in trace_names, trace_names

    assert final.get("current_agent") == "ReportAgent"
    assert final.get("review_intel_status", {}).get("status") in {"partial", "available", "collected"}
    assert final.get("price_status", {}).get("status") in {"partial", "collected", "no_sources", "mcp_not_connected"}
    assert final.get("experience_analysis", {}).get("status") in {"partial", "available"}

    assert len(final.get("resolved_products", [])) == 2
    assert len(final.get("product_facts", [])) == 2
    assert len(final.get("evidence_list", [])) >= 18
    assert final.get("faithfulness_report", {}).get("review_verification", {}).get("unsupported_review_signals") == 0
    assert final.get("hardware_analysis", {}).get("scope") == "hardware_facts_only"

    quality = final.get("quality_result", {})
    assert quality.get("approved") is True, quality
    assert quality.get("quality_score") != 90
    assert quality.get("pending_data"), quality

    report = final.get("final_report", {})
    for key in (
        "schema_name",
        "schema_version",
        "product_identification",
        "hardware_specs",
        "hardware_fact_comparison",
        "feature_tree",
        "pricing_model",
        "user_persona",
        "evidence_links",
        "agent_contributions",
        "pending_data",
        "risk_flags",
        "score_flow",
        "final_score",
        "final_recommendation",
    ):
        assert key in report, key

    assert report["schema_name"] == "gaming_mouse_competitive_report"
    assert report["report_kind"] == "gaming_mouse_product_comparison"
    assert report["feature_tree"]["schema_name"] == "gaming_mouse_feature_tree"
    assert report["pricing_model"]["schema_name"] == "gaming_mouse_pricing_model"
    assert report["user_persona"]["schema_name"] == "gaming_mouse_user_persona"
    assert report["user_persona"]["evidence_status"] in {"partial", "available", "collected"}
    assert report["pricing_model"]["realtime_price_status"] in {"partial", "collected", "no_sources", "mcp_not_connected", "pending"}
    assert report["evidence_links"]["evidence_status"]["local_json"]["count"] >= 8
    return final


def test_full_workflow_zhuque_dex_resolution():
    final = _run(_build_initial_state(_zhuque_dex_request()))

    resolved = final.get("resolved_products", [])
    resolved_by_input = {item.get("original_input"): item for item in resolved}

    zhuque = resolved_by_input.get("\u6731\u96c0")
    assert zhuque, resolved
    assert zhuque["resolved_product_id"] == "logitech-g-pro-x2-superstrike"
    assert zhuque["official_model"] == "G PRO X2 SUPERSTRIKE"
    assert zhuque["matched_by"] == "community_alias"
    assert zhuque["match_confidence"] == "unverified"
    assert zhuque["alias_warning"]

    dex = resolved_by_input.get("DEX")
    assert dex, resolved
    assert dex["resolved_product_id"] == "logitech-gpx-superlight-2-dex"
    assert dex["official_model"] == "G Pro X Superlight 2 DEX"
    assert dex["mold_id"] == "gpx-dex-ergonomic"

    assert final.get("experience_analysis", {}).get("status") == "insufficient_evidence"
    assert final.get("quality_result", {}).get("approved") is True
    return final


def test_unknown_products_do_not_use_seed_evidence():
    request = AnalysisRequest(
        industry_key="gaming_mouse",
        target_platform="unknown mouse alpha",
        competitors=["unknown mouse alpha", "unknown mouse beta"],
        analysis_scene="unknown gaming mouse comparison",
        target_user="gaming peripheral buyer",
        time_range="last two years",
        focus_dimensions=[],
    )
    final = _run(_build_initial_state(request))

    assert final["product_compare_mode"] is True
    assert final.get("resolved_products", []) == []
    assert final.get("unresolved_products") == ["unknown mouse alpha", "unknown mouse beta"]
    assert final.get("raw_research", []) == []
    assert final.get("evidence_list", []) == []
    assert final.get("claims", []) == []
    assert len(final.get("search_mcp_results", [])) == 2
    assert all(item.get("status") == "mcp_not_connected" for item in final.get("search_mcp_results", []))
    assert len(final.get("external_product_candidates", [])) == 2
    assert all(
        item.get("consumable_by_next_agent") is False
        for item in final.get("external_product_candidates", [])
    )
    assert final.get("pending_data"), final
    assert final.get("quality_result", {}).get("status") == "partial_report"
    risk_flags = [item for item in final.get("risk_flags", []) if isinstance(item, dict)]
    assert any(
        item.get("risk_type") == "evidence_gap"
        and "product_resolution" in item.get("related_dimensions", [])
        for item in risk_flags
    )
    report = final.get("final_report", {})
    assert any(
        item.get("agent") == "CollectorAgent.product_resolution"
        for item in report.get("pending_data", [])
        if isinstance(item, dict)
    )
    assert report.get("schema_name") == "gaming_mouse_competitive_report"
    assert report.get("hardware_specs") == []
    assert report.get("pricing_model", {}).get("status") == "pending"
    assert report.get("user_persona", {}).get("status") == "insufficient_evidence"
    return final


ALL_TESTS = [
    test_initial_state_keeps_inputs_only,
    test_free_text_entry_uses_product_compare_mode,
    test_full_workflow_gpx2_viper,
    test_full_workflow_zhuque_dex_resolution,
    test_unknown_products_do_not_use_seed_evidence,
]


if __name__ == "__main__":
    for test in ALL_TESTS:
        test()
        print(f"  PASS  {test.__name__}")
    final = test_full_workflow_gpx2_viper()
    print(
        "\nProduct compare workflow passed: "
        f"trace={len(final.get('trace_log', []))}, "
        f"claims={len([c for c in final.get('claims', []) if isinstance(c, dict)])}, "
        f"quality={final.get('quality_result', {}).get('quality_score')}"
    )
