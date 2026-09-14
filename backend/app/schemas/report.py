from typing import List

from pydantic import BaseModel

from app.schemas.gaming_mouse import GamingMouseFinalReportSchema


class ReportAgentOutput(BaseModel):
    final_report: GamingMouseFinalReportSchema
    used_claim_ids: List[str]
    used_evidence_ids: List[str]
