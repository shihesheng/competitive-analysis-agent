from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ReviewTicket(BaseModel):
    ticket_id: str
    status: Literal["open", "resolved"] = "open"
    reason: str
    target_agent: Optional[str] = None
    failed_checks: List[str] = Field(default_factory=list)
    required_actions: List[str] = Field(default_factory=list)
    unsupported_claim_ids: List[str] = Field(default_factory=list)
    matrix_issues: List[Dict[str, Any]] = Field(default_factory=list)
    missing_dimensions: List[str] = Field(default_factory=list)
    missing_platforms: List[str] = Field(default_factory=list)
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_next_steps: List[str] = Field(default_factory=list)
    created_at: str
