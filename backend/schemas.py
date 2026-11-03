from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from .models import Role, RunState

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: Role = Role.developer

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class ProjectCreate(BaseModel):
    name: str
    repository_url: str | None = None

class ProjectOut(ProjectCreate):
    id: str
    owner_id: str
    model_config = ConfigDict(from_attributes=True)

class RunOut(BaseModel):
    id: str
    project_id: str
    state: RunState
    verdict: str | None = None
    status_message: str | None = None
    node_analysis: dict | None = None
    model_config = ConfigDict(from_attributes=True)

class ProjectImportRequest(BaseModel):
    name: str
    repository_url: str
    repository_id: Optional[str] = None
    repository_owner: Optional[str] = None
    default_branch: Optional[str] = "main"
    github_token: Optional[str] = None

class ProjectImportOut(BaseModel):
    project_id: str
    run_id: str
    name: str
    repository_url: str
    state: RunState
    status_message: Optional[str] = None

class FileItemOut(BaseModel):
    id: str
    path: str
    size_bytes: int
    is_binary: bool
    model_config = ConfigDict(from_attributes=True)

class FileContentOut(BaseModel):
    path: str
    content: Optional[str] = None
    size_bytes: int
    is_binary: bool
