"""Domain schemas for esports mouse competitive intelligence.

These models are intentionally more specific than the old broad report
payloads. They describe the structured knowledge that agents pass through the
workflow: entity resolution, hardware facts, feature tree, pricing, user fit,
traceability, and final recommendation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class DomainSchemaModel(BaseModel):
    model_config = ConfigDict(extra="allow")


ConfidenceLabel = Literal[
    "official",
    "review_verified",
    "rule_inferred",
    "community_likely",
    "community_unverified",
    "pending",
]


GAMING_MOUSE_SCHEMA_ID = "gaming_mouse_competitive_report"
GAMING_MOUSE_SCHEMA_MODEL = "GamingMouseFinalReportSchema"
GAMING_MOUSE_SCHEMA_FIELDS = [
    "official_model",
    "brand",
    "family",
    "variant_name",
    "variant_type",
    "aliases",
    "community_aliases",
    "alias_confidence",
    "shape",
    "shape_detail",
    "weight_g",
    "sensor",
    "dpi_max",
    "polling_rate_hz",
    "connection",
    "battery_hours",
    "switch_type",
    "click_system",
    "software",
    "onboard_memory",
    "field_confidence",
    "official_spec_status",
    "official_spec_records",
    "review_intel_status",
    "price_status",
    "feature_tree",
    "pricing_model",
    "user_persona",
    "evidence_links",
]


class DimensionsMmSchema(DomainSchemaModel):
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


class PriceRangeSchema(DomainSchemaModel):
    usd: List[float] = Field(default_factory=list)
    cny: List[float] = Field(default_factory=list)
    status: str = "reference_only"
    note: str = "历史参考价不参与最终性价比判断，实时价格等待 PriceAgent/MCP 补齐。"


class ProductIdentitySchema(DomainSchemaModel):
    official_model: str = ""
    model: str = ""
    brand: str = ""
    family: str = ""
    variant_name: str = ""
    variant_type: str = ""
    aliases: List[str] = Field(default_factory=list)
    community_aliases: List[str] = Field(default_factory=list)
    alias_confidence: str = "pending"
    official_name_confidence: str = "pending"
    shape_detail: str = ""
    click_system: str = ""
    data_status: str = "pending"
    field_confidence: Dict[str, ConfidenceLabel | str] = Field(default_factory=dict)
    official_fields: List[str] = Field(default_factory=list)
    review_verified_fields: List[str] = Field(default_factory=list)
    rule_inferred_fields: List[str] = Field(default_factory=list)
    community_unverified_fields: List[str] = Field(default_factory=list)
    pending: Union[List[str], str] = Field(default_factory=list)


class HardwareSpecSchema(DomainSchemaModel):
    product_id: str = ""
    brand: str = ""
    model: str = ""
    weight_g: Optional[float] = None
    sensor: str = ""
    dpi_max: Optional[int] = None
    polling_rate_hz: Optional[int] = None
    connection: List[str] = Field(default_factory=list)
    battery_hours: Optional[float] = None
    switch_type: str = ""
    click_system: str = ""
    software: str = ""
    onboard_memory: Optional[bool] = None
    shape: str = ""
    price_range: Optional[PriceRangeSchema] = None
    field_confidence: Dict[str, ConfidenceLabel | str] = Field(default_factory=dict)
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class MatrixCellSchema(DomainSchemaModel):
    score: Optional[float] = Field(default=None, ge=0, le=100)
    summary: str = ""
    analysis: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0, le=1)
    data_status: str = "pending"


class CompetitiveMatrixSchema(DomainSchemaModel):
    dimensions: Dict[str, Dict[str, MatrixCellSchema]] = Field(default_factory=dict)
    generated_at: str = ""


class FeatureNodeSchema(DomainSchemaModel):
    name: str
    status: Literal["available", "partial", "pending", "insufficient_evidence"] = "pending"
    summary: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    source: str = "pending"
    fields: List[str] = Field(default_factory=list)


class FeatureTreeSchema(DomainSchemaModel):
    schema_name: Literal["gaming_mouse_feature_tree"] = "gaming_mouse_feature_tree"
    performance: FeatureNodeSchema = Field(
        default_factory=lambda: FeatureNodeSchema(
            name="性能参数",
            status="pending",
            fields=["sensor", "dpi_max", "polling_rate_hz"],
        )
    )
    shape_and_weight: FeatureNodeSchema = Field(
        default_factory=lambda: FeatureNodeSchema(
            name="轻量化与形态事实",
            status="pending",
            fields=["weight_g", "shape"],
        )
    )
    wireless_and_battery: FeatureNodeSchema = Field(
        default_factory=lambda: FeatureNodeSchema(
            name="无线与续航",
            status="pending",
            fields=["connection", "battery_hours", "polling_rate_hz"],
        )
    )
    click_system: FeatureNodeSchema = Field(
        default_factory=lambda: FeatureNodeSchema(
            name="点击系统",
            status="pending",
            fields=["switch_type", "click_system"],
        )
    )
    software_ecosystem: FeatureNodeSchema = Field(
        default_factory=lambda: FeatureNodeSchema(
            name="软件/驱动生态",
            status="pending",
            fields=["software", "onboard_memory"],
        )
    )


class PricingModelSchema(DomainSchemaModel):
    schema_name: Literal["gaming_mouse_pricing_model"] = "gaming_mouse_pricing_model"
    status: Literal["pending", "reference_only", "available"] = "pending"
    realtime_price_status: Literal["mcp_not_connected", "pending", "available"] = "mcp_not_connected"
    price_range_reference: List[Dict[str, Any]] = Field(default_factory=list)
    value_score_status: Literal["pending", "available"] = "pending"
    note: str = "价格会随时间变化，最终性价比等待 PriceAgent/MCP 实时采集。"


class UserPersonaSchema(DomainSchemaModel):
    schema_name: Literal["gaming_mouse_user_persona"] = "gaming_mouse_user_persona"
    status: Literal["pending", "insufficient_evidence", "partial", "available"] = "insufficient_evidence"
    grip_style_fit: Dict[str, str] = Field(default_factory=dict)
    hand_size_fit: Dict[str, str] = Field(default_factory=dict)
    game_type_fit: Dict[str, str] = Field(default_factory=dict)
    target_persona: List[str] = Field(default_factory=list)
    evidence_status: str = "review_intel_pending"
    limitation: str = "握法、手型、适合游戏和长期口碑必须等待真实评价/测评证据。"


class EvidenceLinkSchema(DomainSchemaModel):
    used_claim_ids: List[str] = Field(default_factory=list)
    used_evidence_ids: List[str] = Field(default_factory=list)
    evidence_status: Dict[str, Any] = Field(default_factory=dict)
    unsupported_claim_ids: List[str] = Field(default_factory=list)
    pending_data: List[Dict[str, Any]] = Field(default_factory=list)
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)


class ScoreFlowSchema(DomainSchemaModel):
    baseline_score: Dict[str, Any] = Field(default_factory=dict)
    agent_adjustments: List[Dict[str, Any]] = Field(default_factory=list)
    final_score: Dict[str, Any] = Field(default_factory=dict)


class AgentContributionSchema(DomainSchemaModel):
    agent: str
    role: str = ""
    summary: str = ""
    status: str = "not_run"


class GamingMouseFinalReportSchema(DomainSchemaModel):
    schema_name: Literal["gaming_mouse_competitive_report"] = "gaming_mouse_competitive_report"
    schema_version: str = "1.0"
    report_kind: Literal["gaming_mouse_product_comparison"] = "gaming_mouse_product_comparison"
    report_type: Literal["agent_final_report"] = "agent_final_report"
    title: str = "电竞鼠标 Agent 综合分析报告"
    summary: Union[Dict[str, Any], str, List[str]] = Field(default_factory=dict)
    executive_summary: Union[str, List[str]] = ""
    product_identification: List[ProductIdentitySchema] = Field(default_factory=list)
    hardware_specs: List[HardwareSpecSchema] = Field(default_factory=list)
    official_spec_records: List[Dict[str, Any]] = Field(default_factory=list)
    review_intel_records: List[Dict[str, Any]] = Field(default_factory=list)
    review_intel_status: Dict[str, Any] = Field(default_factory=dict)
    hardware_fact_comparison: Dict[str, Any] = Field(default_factory=dict)
    product_matrix: CompetitiveMatrixSchema = Field(default_factory=CompetitiveMatrixSchema)
    business_matrix: CompetitiveMatrixSchema = Field(default_factory=CompetitiveMatrixSchema)
    feature_tree: FeatureTreeSchema = Field(default_factory=FeatureTreeSchema)
    pricing_model: PricingModelSchema = Field(default_factory=PricingModelSchema)
    user_persona: UserPersonaSchema = Field(default_factory=UserPersonaSchema)
    evidence_links: EvidenceLinkSchema = Field(default_factory=EvidenceLinkSchema)
    score_flow: ScoreFlowSchema = Field(default_factory=ScoreFlowSchema)
    agent_contributions: List[AgentContributionSchema] = Field(default_factory=list)
    pending_data: List[Dict[str, Any]] = Field(default_factory=list)
    risk_disclosure: List[Dict[str, Any]] = Field(default_factory=list)
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    quality_status: str = "pending"
    report_status: str = "pending"
    approved_with_limitations: bool = False
    partial_report: bool = False
    auto_degraded: bool = False
    limitations: List[str] = Field(default_factory=list)
    final_recommendation: Dict[str, Any] = Field(default_factory=dict)
    scenario_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    final_score: List[Dict[str, Any]] = Field(default_factory=list)
    used_claim_ids: List[str] = Field(default_factory=list)
    used_evidence_ids: List[str] = Field(default_factory=list)
    generated_at: str = ""
