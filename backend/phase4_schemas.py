from pydantic import BaseModel

class IntegrityCheckRequest(BaseModel):
    baseline_files: dict[str, str]
    migrated_files: dict[str, str]

class IntegrityFindingOut(BaseModel):
    code: str
    severity: str
    path: str
    message: str

class IntegrityCheckOut(BaseModel):
    findings: list[IntegrityFindingOut]
    baseline_test_count: int
    migrated_test_count: int
