from pydantic import BaseModel, Field


class ExplainOutput(BaseModel):
    explanation: str = Field(min_length=1)
    artifact_ids: list[str] = []


class PatchSuggestion(BaseModel):
    path: str
    diff: str
    reason: str
    before_content: str | None = None
    after_content: str | None = None


class SuggestOutput(BaseModel):
    summary: str
    patches: list[PatchSuggestion] = []
    artifact_ids: list[str] = []


class SummaryOutput(BaseModel):
    summary: str = Field(min_length=1)
    artifact_ids: list[str] = []
