"""OfficialSpecMCP unit tests.

These tests avoid live network and LLM calls. They validate the service contract
used by CollectorAgent.
"""

from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import official_spec_mcp_service as official_spec


def test_official_spec_disabled():
    os.environ["OFFICIAL_SPEC_USE_LLM"] = "0"
    result = official_spec.extract_official_spec(
        {
            "input": "Razer Viper V3 Pro",
            "brand": "Razer",
            "model": "Viper V3 Pro",
            "official_url": "https://www.razer.com/gaming-mice/razer-viper-v3-pro",
            "source": "local_product_json",
        }
    )
    assert result["status"] == "mcp_not_connected"
    assert result["record"] == {}
    assert "weight_g" in result["missing_fields"]


def test_official_spec_missing_key_when_enabled():
    os.environ["OFFICIAL_SPEC_USE_LLM"] = "1"
    os.environ["ARK_API_KEY"] = ""
    os.environ["ARK_EP"] = ""
    os.environ["OFFICIAL_SPEC_API_KEY"] = ""
    os.environ["OFFICIAL_SPEC_MODEL"] = ""
    result = official_spec.extract_official_spec(
        {
            "input": "Razer Viper V3 Pro",
            "official_url": "https://www.razer.com/gaming-mice/razer-viper-v3-pro",
        }
    )
    assert result["status"] == "mcp_not_configured"


def test_normalize_record_and_product_conversion():
    payload = {
        "brand": "Razer",
        "official_model": "Razer Viper V3 Pro",
        "weight_g": "54 g",
        "dimensions_mm": "127.1 x 63.9 x 39.9 mm",
        "shape": "symmetrical",
        "sensor": "Razer Focus Pro 35K Gen-2",
        "dpi_max": "35000 DPI",
        "polling_rate_hz": "8000 Hz",
        "connection": ["Razer HyperSpeed Wireless", "USB-C wired"],
        "battery_hours": "95 hours",
        "switch_type": "Optical Mouse Switches Gen-3",
        "click_system": "optical",
        "software": "Razer Synapse",
        "onboard_memory": "yes",
        "confidence": "high",
        "missing_fields": [],
    }
    target = {
        "input": "Viper V3 Pro",
        "official_url": "https://www.razer.com/gaming-mice/razer-viper-v3-pro",
    }
    record = official_spec._normalize_record(payload, target)
    assert record["weight_g"] == 54
    assert record["dimensions_mm"] == {"length": 127.1, "width": 63.9, "height": 39.9}
    assert record["dpi_max"] == 35000
    assert record["polling_rate_hz"] == 8000
    assert record["connection"] == ["2.4ghz", "wired"]
    assert record["onboard_memory"] is True
    result = {
        "status": "collected",
        "input": "Viper V3 Pro",
        "source_url": target["official_url"],
        "source_domain": "razer.com",
        "confidence": "high",
        "record": record,
    }
    product = official_spec.product_from_official_spec(result)
    assert product
    assert product["id"] == "official-razer-razer-viper-v3-pro"
    assert product["model"] == "Razer Viper V3 Pro"
    assert product["sensor"] == "Razer Focus Pro 35K Gen-2"


def test_series_page_variant_patch_and_partial_product_conversion():
    payload = {
        "brand": "WLMOUSE",
        "official_model": "WLMOUSE Beast X Series",
        "sensor": "PAW 3950HS",
        "confidence": "low",
        "missing_fields": [
            "weight_g",
            "dimensions_mm",
            "dpi_max",
            "polling_rate_hz",
            "connection",
            "click_system",
        ],
        "evidence_snippets": [
            "Beast X Mini Pro: Weight 34g Sensor PAW 3950HS Battery 220 mA Material Magnesium alloy Size 116×58×35",
            "Beast X Pro: Weight 39g Sensor PAW 3950HS Battery 300 mA Material Magnesium alloy Size 122×62×37",
            "Beast X Max: Weight 42g Sensor PAW 3950HS Battery 300 mA Size 126×65×39",
        ],
    }
    target = {
        "input": "WLMOUSE Beast X Pro",
        "model": "WLMOUSE Beast X Pro",
        "official_url": "https://www.wlmouse.com/collections/beast-x-series",
    }
    record = official_spec._normalize_record(payload, target)
    official_spec._patch_record_from_official_text(record, target, "")
    official_spec._refresh_record_confidence(record)
    assert record["weight_g"] == 39
    assert record["dimensions_mm"] == {"length": 122.0, "width": 62.0, "height": 37.0}
    assert record["sensor"] == "PAW 3950HS"
    assert "weight_g" not in record["missing_fields"]
    assert "dimensions_mm" not in record["missing_fields"]
    assert official_spec._extraction_status(record) == "partial_collected"

    result = {
        "status": "partial_collected",
        "input": "WLMOUSE Beast X Pro",
        "source_url": target["official_url"],
        "source_domain": "wlmouse.com",
        "confidence": record["confidence"],
        "record": record,
    }
    product = official_spec.product_from_official_spec(result)
    assert product
    assert product["model"] == "WLMOUSE Beast X Pro"
    assert product["data_status"] == "official_spec_partial"
    assert product["weight_g"] == 39


ALL_TESTS = [
    test_official_spec_disabled,
    test_official_spec_missing_key_when_enabled,
    test_normalize_record_and_product_conversion,
    test_series_page_variant_patch_and_partial_product_conversion,
]


if __name__ == "__main__":
    for test in ALL_TESTS:
        test()
        print(f"  PASS  {test.__name__}")
