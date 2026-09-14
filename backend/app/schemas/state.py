from typing import Any, Dict, List

from pydantic import BaseModel, Field


class StateSnapshot(BaseModel):
    target_platform: str = ""
    competitors: List[str] = Field(default_factory=list)
    analysis_scene: str = ""
    target_user: str = ""
    time_range: str = ""
    focus_dimensions: List[str] = Field(default_factory=list)
    industry_key: str = ""
    industry_name: str = ""
    raw_research: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_list: List[Dict[str, Any]] = Field(default_factory=list)
    review_intel_records: List[Dict[str, Any]] = Field(default_factory=list)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    product_matrix: Dict[str, Any] = Field(default_factory=dict)
    business_matrix: Dict[str, Any] = Field(default_factory=dict)
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    faithfulness_report: Dict[str, Any] = Field(default_factory=dict)
    unsupported_claim_ids: List[str] = Field(default_factory=list)
    quality_result: Dict[str, Any] = Field(default_factory=dict)
    final_report: Dict[str, Any] = Field(default_factory=dict)
    context_summary: Dict[str, Any] = Field(default_factory=dict)
    review_ticket: Dict[str, Any] = Field(default_factory=dict)
    used_claim_ids: List[str] = Field(default_factory=list)
    used_evidence_ids: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    current_agent: str = ""
    iteration_count: int = 0
    rejected_agents: List[str] = Field(default_factory=list)
    is_approved: bool = False
    needs_human_review: bool = False
    degraded_report: bool = False
    quality_status: str = ""
    error_log: List[Dict[str, Any]] = Field(default_factory=list)
    trace_log: List[Dict[str, Any]] = Field(default_factory=list)
