from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TaskStatus

# Create = what a client sends to make a resource (no id / created_at: the server owns those).
# Update = partial update, every field optional; crud applies only the fields actually sent.
# Read   = what the API returns; from_attributes lets Pydantic read SQLAlchemy objects directly.


# ---------- Projects ----------

class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    # Omitting name is fine (leave it unchanged), but sending "name": null is not,
    # because the column is NOT NULL. Validators only run on values that were sent.
    @field_validator("name")
    @classmethod
    def name_not_null(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("name cannot be null")
        return v


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------- Tasks ----------

class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    status: TaskStatus = TaskStatus.todo


class TaskCreate(TaskBase):
    project_id: int


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TaskStatus | None = None
    project_id: int | None = None

    @field_validator("title", "status", "project_id")
    @classmethod
    def not_null(cls, v):
        if v is None:
            raise ValueError("field cannot be null")
        return v


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime


# ---------- Nested ----------

class ProjectWithTasks(ProjectRead):
    tasks: list[TaskRead] = []
