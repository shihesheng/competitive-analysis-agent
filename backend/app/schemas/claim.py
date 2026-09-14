from typing import List

from pydantic import BaseModel, Field


class Claim(BaseModel):
    claim_id: str
    content: str
    dimension: str
    related_platforms: List[str]
    evidence_ids: List[str]
    confidence_score: float = Field(ge=0, le=1)
    generated_by: str
