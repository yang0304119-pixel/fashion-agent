"""租户知识文档及其不可变版本。"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_document"
    __table_args__ = (
        Index(
            "ix_knowledge_document_tenant_updated",
            "tenant_id",
            "updated_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenant.id"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    knowledge_type = Column(String(50), nullable=False, index=True)
    category = Column(String(100), nullable=False, default="通用")
    created_by = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    revisions = relationship(
        "KnowledgeRevision",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeRevision.version_no.desc()",
    )


class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revision"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_no",
            name="uq_knowledge_revision_document_version",
        ),
        CheckConstraint(
            "parse_status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_knowledge_revision_parse_status",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="ck_knowledge_revision_review_status",
        ),
        Index(
            "ix_knowledge_revision_document_created",
            "document_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("knowledge_document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no = Column(Integer, nullable=False)
    original_filename = Column(String(255), nullable=False)
    source_file_type = Column(String(20), nullable=False)
    raw_storage_key = Column(String(500), nullable=False)
    processed_storage_key = Column(String(500), nullable=True)
    source_sha256 = Column(String(64), nullable=False)
    processed_sha256 = Column(String(64), nullable=True)
    parse_status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    parse_error_code = Column(String(100), nullable=True)
    parse_error_message = Column(String(500), nullable=True)
    review_status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    quality_status = Column(String(20), nullable=True)
    quality_report = Column(JSON, nullable=True)
    created_by = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    reviewed_by = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    review_reason = Column(Text, nullable=True)
    effective_at = Column(DateTime, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship(
        "KnowledgeDocument",
        back_populates="revisions",
    )


class KnowledgeIndexBuild(Base):
    """租户级候选知识库构建及活跃版本记录。"""

    __tablename__ = "knowledge_index_build"
    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'ready', 'active', 'failed', 'superseded')",
            name="ck_knowledge_index_build_status",
        ),
        Index(
            "ix_knowledge_index_build_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenant.id"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(20),
        nullable=False,
        default="building",
        index=True,
    )
    collection_name = Column(String(200), nullable=True, unique=True)
    revision_snapshot = Column(JSON, nullable=False, default=list)
    document_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    triggered_by = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    error_code = Column(String(100), nullable=True)
    error_message = Column(String(500), nullable=True)
    previous_active_build_id = Column(
        Integer,
        ForeignKey("knowledge_index_build.id"),
        nullable=True,
        index=True,
    )
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
