"""Gaming-mouse industry config and catalog tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).resolve().parent / ".env")

from api.routes import app
from app.schemas.gaming_mouse import GAMING_MOUSE_SCHEMA_FIELDS
from app.services.product_catalog_service import list_products, search_products
from orchestration.industry_config import INDUSTRY_CONFIGS


EXPECTED_COMPETITORS = {"Logitech", "Razer", "ZOWIE"}
EXPECTED_DIMENSIONS = {
    "性能参数",
    "轻量化设计",
    "无线与续航",
    "软件生态",
    "点击系统",
    "模具与尺寸",
    "用户评价与博主测评",
    "实时价格",
    "长期可靠性",
}
EXPECTED_PRODUCTS = {
    "G Pro X Superlight 2",
    "G Pro X Superlight 2 DEX",
    "G502 X Plus",
    "Viper V3 Pro",
    "DeathAdder V3 Pro",
    "M75 Air Wireless",
    "G PRO X2 SUPERSTRIKE",
}


if __name__ == "__main__":
    config = INDUSTRY_CONFIGS["gaming_mouse"]
    assert config["schema_id"] == "gaming_mouse_competitive_report"
    assert config["schema_model"] == "GamingMouseFinalReportSchema"
    assert config["schema_fields"] == GAMING_MOUSE_SCHEMA_FIELDS
    assert EXPECTED_COMPETITORS.issubset(set(config["competitors"]))
    assert EXPECTED_DIMENSIONS.issubset(set(config["dimensions"]))

    client = TestClient(app)
    response = client.get("/api/industries")
    assert response.status_code == 200
    industries = response.json()["industries"]
    assert len(industries) == 1
    gaming_mouse = industries[0]
    assert (gaming_mouse.get("industry_key") or gaming_mouse.get("key")) == "gaming_mouse"
    assert gaming_mouse["schema_id"] == "gaming_mouse_competitive_report"
    assert gaming_mouse["schema_model"] == "GamingMouseFinalReportSchema"
    assert gaming_mouse["schema_fields"] == GAMING_MOUSE_SCHEMA_FIELDS

    products = list_products("gaming_mouse")
    searchable_text = "\n".join(
        " ".join(str(product.get(field, "")) for field in ["brand", "model", "aliases", "community_aliases"])
        for product in products
    )

    assert len(products) >= len(EXPECTED_PRODUCTS)
    assert all(product in searchable_text for product in EXPECTED_PRODUCTS)
    assert search_products("gaming_mouse", "GPX2")
    assert search_products("gaming_mouse", "Viper V3 Pro")

    print("gaming mouse config test passed")
