from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=180)
    description: str | None = None


class GenerateProjectKeyRequest(BaseModel):
    key_name: str | None = Field(default=None, max_length=120)

