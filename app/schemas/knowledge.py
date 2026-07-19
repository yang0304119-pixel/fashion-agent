"""知识文档生命周期管理 API 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeRevisionData(BaseModel):
    id: int
    document_id: int
    version_no: int
    original_filename: str
    source_file_type: str
    source_sha256: str
    processed_sha256: str | None
    parse_status: str
    parse_error_code: str | None
    parse_error_message: str | None
    review_status: str
    quality_status: str | None
    quality_report: dict | None
    created_by: int
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None


class KnowledgeDocumentListItem(BaseModel):
    id: int
    title: str
    knowledge_type: str
    category: str
    created_by: int
    created_at: datetime | None
    updated_at: datetime | None
    latest_revision: KnowledgeRevisionData


class KnowledgeDocumentDetailData(KnowledgeDocumentListItem):
    revisions: list[KnowledgeRevisionData]


class KnowledgeDocumentListResponse(BaseModel):
    data: list[KnowledgeDocumentListItem]
    total: int
    page: int
    page_size: int


class KnowledgeDocumentResponse(BaseModel):
    success: bool = True
    data: KnowledgeDocumentDetailData


class KnowledgeRevisionResponse(BaseModel):
    success: bool = True
    data: KnowledgeRevisionData


class KnowledgeContentData(BaseModel):
    revision: KnowledgeRevisionData
    content: str


class KnowledgeContentResponse(BaseModel):
    success: bool = True
    data: KnowledgeContentData


class KnowledgeContentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2_000_000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("解析内容不能为空")
        return value


class KnowledgeRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("拒绝原因不能为空")
        return normalized


class KnowledgeIndexBuildData(BaseModel):
    id: int
    status: str
    collection_name: str | None
    revision_snapshot: list[int]
    document_count: int
    chunk_count: int
    triggered_by: int
    error_code: str | None
    error_message: str | None
    previous_active_build_id: int | None
    started_at: datetime
    finished_at: datetime | None
    activated_at: datetime | None
    created_at: datetime | None


class KnowledgeIndexBuildListResponse(BaseModel):
    data: list[KnowledgeIndexBuildData]
    total: int
    page: int
    page_size: int


class KnowledgeIndexBuildResponse(BaseModel):
    success: bool = True
    data: KnowledgeIndexBuildData


class KnowledgeRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_build_id: int | None = Field(default=None, gt=0)
