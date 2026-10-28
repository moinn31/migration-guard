from pydantic import BaseModel, EmailStr, ConfigDict
from .models import Role, RunState
class UserCreate(BaseModel): email: EmailStr; password: str; role: Role=Role.developer
class Token(BaseModel): access_token: str; token_type: str='bearer'
class ProjectCreate(BaseModel): name: str; repository_url: str|None=None
class ProjectOut(ProjectCreate): id: str; owner_id: str; model_config=ConfigDict(from_attributes=True)
class RunOut(BaseModel): id: str; project_id: str; state: RunState; verdict: str | None = None; model_config=ConfigDict(from_attributes=True)
