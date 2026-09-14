from typing import Literal, Optional

from pydantic import BaseModel


class AgentTrace(BaseModel):
    step_id: int
    agent_name: str
    status: Literal["started", "success", "failed", "schema_failed", "rejected"]
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
