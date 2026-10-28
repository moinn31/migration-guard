from pydantic import BaseModel

class BuildResultOut(BaseModel):
    id: str
    run_id: str
    status: str
    exit_code: int | None = None
    logs: str | None = None
    artifacts: dict = {}
