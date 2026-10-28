from pydantic import BaseModel, ConfigDict


class MigrationProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    run_id: str
    code: str
    path: str
    title: str
    rationale: str
    diff: str
    explanation: str
    reversible: bool = True
    advisory: bool = True


class MigrationPlanOut(BaseModel):
    run_id: str
    target: str
    proposals: list[MigrationProposalOut]
