"""用户与管理员记忆管理API模型。"""

from datetime import datetime
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryItem(BaseModel):
    id: int
    scope_type: str
    scope_id: str
    memory_type: str
    subject_key: str
    content: dict[str, Any]
    source_type: str
    confidence: float
    importance: float
    stability: float
    sensitivity: str
    status: str
    score: float | None = None
    expires_at: datetime | None = None
    supersedes_id: int | None = None
    access_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryListResponse(BaseModel):
    success: bool = True
    data: list[MemoryItem]


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_type: Literal["user_preference", "long_term_goal"]
    subject_key: str = Field(min_length=3, max_length=150)
    content: dict[str, Any]
    expires_at: datetime | None = None

    @field_validator("subject_key")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        return value.strip()

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False)) > 4000:
            raise ValueError("记忆内容不能超过4000字符")
        return value


class AdminMemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["tenant", "project"] = "tenant"
    scope_id: str = Field(default="fashionagent", min_length=1, max_length=100)
    memory_type: Literal[
        "project_rule",
        "verified_fact",
        "decision",
        "failure_pattern",
        "procedure",
    ]
    subject_key: str = Field(min_length=3, max_length=150)
    content: dict[str, Any]
    importance: float = Field(default=0.8, ge=0, le=1)
    stability: float = Field(default=0.9, ge=0, le=1)
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False)) > 4000:
            raise ValueError("记忆内容不能超过4000字符")
        return value


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: dict[str, Any]

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False)) > 4000:
            raise ValueError("记忆内容不能超过4000字符")
        return value


class MemoryResponse(BaseModel):
    success: bool = True
    data: MemoryItem


class MemoryDeleteResponse(BaseModel):
    success: bool = True
    deleted: bool = True


class SessionMemoryData(BaseModel):
    session_id: str
    recent_turns: list[dict[str, Any]]
    conversation_summary: dict[str, Any] | None
    task_checkpoint: dict[str, Any] | None


class SessionMemoryResponse(BaseModel):
    success: bool = True
    data: SessionMemoryData


class SessionMemoryDeleteData(BaseModel):
    turns: int
    summaries: int
    checkpoints: int


class SessionMemoryDeleteResponse(BaseModel):
    success: bool = True
    data: SessionMemoryDeleteData


class AdminMemoryStatsResponse(BaseModel):
    success: bool = True
    data: dict[str, Any]
