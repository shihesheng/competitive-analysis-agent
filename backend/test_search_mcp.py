from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import search_mcp_service


def test_search_mcp_disabled():
    os.environ["SEARCH_PROVIDER"] = "disabled"
    os.environ.pop("TAVILY_API_KEY", None)
    result = search_mcp_service.search_candidates("unknown mouse alpha")
    assert result["status"] == "mcp_not_connected"
    assert result["candidate_count"] == 0


def test_search_mcp_missing_key():
    os.environ["SEARCH_PROVIDER"] = "tavily"
    os.environ["TAVILY_API_KEY"] = ""
    result = search_mcp_service.search_candidates("unknown mouse alpha")
    assert result["status"] == "mcp_not_configured"
    assert result["provider"] == "tavily"


def test_tavily_candidate_normalization_without_network():
    candidate = search_mcp_service._candidate_from_tavily(
        {
            "title": "Razer Viper V3 Pro | Razer Official",
            "url": "https://www.razer.com/gaming-mice/razer-viper-v3-pro",
            "content": "Wireless gaming mouse with esports features.",
            "score": 0.7,
        }
    )
    assert candidate["domain"] == "razer.com"
    assert candidate["source_type"] == "official_candidate"
    assert candidate["confidence_hint"] > 0.7


def test_official_candidate_is_consumable_without_network():
    candidate = search_mcp_service._candidate_from_tavily(
        {
            "title": "WLMOUSE Beast X Pro Wireless Gaming Mouse",
            "url": "https://www.wlmouse.com/products/x-pro",
            "content": "Ultra-light wireless gaming mouse with magnesium shell.",
            "score": 0.78,
        }
    )
    classified = search_mcp_service._classify_search_candidates(
        "WLmouse Beast X Pro",
        "gaming_mouse",
        [candidate],
    )
    assert classified["status"] == "official_candidate_found"
    assert classified["usable_candidate_count"] == 1
    assert classified["best_candidate"]["domain"] == "wlmouse.com"
    assert classified["needs_llm_disambiguation"] is True


def test_off_category_result_is_not_consumable_without_network():
    candidate = search_mcp_service._candidate_from_tavily(
        {
            "title": "iPhone 15 Pro - Apple",
            "url": "https://www.apple.com/iphone-15-pro/",
            "content": "Smartphone with titanium design.",
            "score": 0.9,
        }
    )
    classified = search_mcp_service._classify_search_candidates(
        "iPhone 15 Pro",
        "gaming_mouse",
        [candidate],
    )
    assert classified["status"] == "off_category_suspected"
    assert classified["usable_candidate_count"] == 0
    assert classified["best_candidate"] is None
    assert classified["needs_llm_disambiguation"] is False


if __name__ == "__main__":
    for test in (
        test_search_mcp_disabled,
        test_search_mcp_missing_key,
        test_tavily_candidate_normalization_without_network,
        test_official_candidate_is_consumable_without_network,
        test_off_category_result_is_not_consumable_without_network,
    ):
        test()
        print(f"PASS {test.__name__}")
