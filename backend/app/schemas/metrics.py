from pydantic import BaseModel


class ReportMetrics(BaseModel):
    evidence_count: int
    claim_count: int
    citation_rate: float
    coverage_rate: float
    high_credibility_ratio: float
    low_credibility_ratio: float
    faithfulness_rate: float = 1.0
    unsupported_claim_count: int = 0
    weak_claim_count: int = 0
    matrix_issue_count: int = 0
    context_trimmed_evidence_count: int = 0
    error_count: int = 0
    has_review_ticket: bool = False
    quality_score: float
    iteration_count: int
