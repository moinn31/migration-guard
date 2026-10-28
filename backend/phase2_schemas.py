from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SnapshotOut(BaseModel):
    id: str
    project_id: str
    run_id: str
    commit_sha: str
    content_hash: str
    snapshot_path: str
    metadata: dict
    model_config = ConfigDict(from_attributes=True)


class FindingOut(BaseModel):
    id: str
    run_id: str
    severity: str
    message: str
    code: str = "ANALYSIS"
    path: str | None = None
    line_number: int | None = None
    provenance: str | None = None
    confidence: str | None = None
    evidence: str | None = None
    note: str | None = None
    model_config = ConfigDict(from_attributes=True)


class RunDetailOut(BaseModel):
    id: str
    project_id: str
    state: str
    created_at: datetime | None = None
    snapshot: SnapshotOut | None = None
    findings: list[FindingOut] = []
