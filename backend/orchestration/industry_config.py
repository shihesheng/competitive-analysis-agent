"""Industry configuration for the current professional gaming-mouse workflow."""

from __future__ import annotations

from typing import Any, Mapping

from app.schemas.gaming_mouse import (
    GAMING_MOUSE_SCHEMA_FIELDS,
    GAMING_MOUSE_SCHEMA_ID,
    GAMING_MOUSE_SCHEMA_MODEL,
)


GAMING_MOUSE_DIMENSIONS = [
    "性能参数",
    "轻量化设计",
    "无线与续航",
    "软件生态",
    "点击系统",
    "模具与尺寸",
    "用户评价与博主测评",
    "实时价格",
    "长期可靠性",
]

GAMING_MOUSE_DATA_SOURCES = {
    "local_product_json": "本地稳定硬件事实库 data/products/gaming_mice.json",
    "official": "品牌官网、官方产品页、驱动/固件支持页",
    "review": "专业评测站、博主测评、长视频体验",
    "user_review": "电商评论、社区口碑、长期使用反馈",
    "price": "实时价格、折扣、地区可买性",
}

INDUSTRY_CONFIGS = {
    "gaming_mouse": {
        "name": "电竞鼠标",
        "competitors": ["Logitech", "Razer", "ZOWIE", "Pulsar", "Lamzu", "Glorious"],
        "representative_products": {
            "Logitech": ["G Pro X Superlight 2", "G Pro X Superlight 2 DEX", "G PRO X2 SUPERSTRIKE"],
            "Razer": ["Viper V3 Pro", "DeathAdder V3 Pro"],
            "ZOWIE": ["EC2-C", "U2"],
        },
        "dimensions": GAMING_MOUSE_DIMENSIONS,
        "description": "电竞鼠标垂直竞品分析：官方型号、实体消歧、硬件事实、模具/点击系统、评价测评、实时价格和长期可靠性。",
        "data_sources": GAMING_MOUSE_DATA_SOURCES,
        "schema_id": GAMING_MOUSE_SCHEMA_ID,
        "schema_model": GAMING_MOUSE_SCHEMA_MODEL,
        "schema_fields": GAMING_MOUSE_SCHEMA_FIELDS.copy(),
    }
}


def get_industry_config(industry_key: str | None) -> dict[str, Any]:
    """Return the configured industry by key, defaulting to gaming_mouse."""
    return INDUSTRY_CONFIGS.get(industry_key or "gaming_mouse", INDUSTRY_CONFIGS["gaming_mouse"])


def get_state_industry_name(state: Mapping[str, Any]) -> str:
    """Resolve industry display name from state first, then config."""
    industry_name = state.get("industry_name")
    if isinstance(industry_name, str) and industry_name.strip():
        return industry_name.strip()

    config = get_industry_config(state.get("industry_key"))
    return str(config.get("name") or "电竞鼠标")


def get_state_dimensions(state: Mapping[str, Any]) -> list[str]:
    """Resolve analysis dimensions from state first, then gaming-mouse config."""
    dimensions = state.get("focus_dimensions")
    if isinstance(dimensions, list):
        resolved = [str(item).strip() for item in dimensions if str(item).strip()]
        if resolved:
            return resolved

    return GAMING_MOUSE_DIMENSIONS.copy()


def get_state_data_sources(state: Mapping[str, Any]) -> dict[str, str]:
    """Resolve configured source types and descriptions."""
    config = get_industry_config(state.get("industry_key"))
    data_sources = config.get("data_sources")
    if isinstance(data_sources, dict) and data_sources:
        return {str(key): str(value) for key, value in data_sources.items()}
    return GAMING_MOUSE_DATA_SOURCES.copy()
