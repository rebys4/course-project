from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TopicStatus = Literal["todo", "in_progress", "done"]


class TopicCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_at: date
    status: TopicStatus = "todo"

    @field_validator("due_at")
    @classmethod
    def due_at_not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("due_at must be today or in the future")
        return v


class TopicUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    due_at: Optional[date] = None
    status: Optional[TopicStatus] = None

    @field_validator("due_at")
    @classmethod
    def due_at_not_in_past(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("due_at must be today or in the future")
        return v


class TopicOut(BaseModel):
    id: int
    owner_id: int
    title: str
    due_at: date
    status: TopicStatus
