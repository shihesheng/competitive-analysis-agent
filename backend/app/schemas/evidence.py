from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    platform: str
    claim: str
    source_type: Literal[
        "official",
        "news",
        "review",
        "report",
        "ecommerce",
        "user_review",
    ]
    source_title: str
    source_url: str
    publish_time: Optional[str] = None
    collected_time: str
    credibility: Literal["high", "medium", "low"]
    related_dimension: str
    raw_content: str
    confidence_score: float = Field(default=0.7, ge=0, le=1)
