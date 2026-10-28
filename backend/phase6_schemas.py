from pydantic import BaseModel, ConfigDict

class RiskAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    score: str
    rationale: str
    breakdown: list[dict] = []

class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    content: dict

class ApprovalRequest(BaseModel):
    decision: str
    justification: str | None = None
    override_reason: str | None = None

class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    user_id: str
    decision: str
    justification: str | None = None
