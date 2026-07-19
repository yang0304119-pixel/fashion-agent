"""AI 客服运营台知识文档生命周期接口。"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from app.models.knowledge_document import KnowledgeDocument, KnowledgeRevision
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeContentData,
    KnowledgeContentResponse,
    KnowledgeContentUpdateRequest,
    KnowledgeDocumentDetailData,
    KnowledgeDocumentListItem,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeRejectRequest,
    KnowledgeRevisionData,
    KnowledgeRevisionResponse,
    KnowledgeIndexBuildData,
    KnowledgeIndexBuildListResponse,
    KnowledgeIndexBuildResponse,
    KnowledgeRollbackRequest,
    KnowledgeQuestionTestData,
    KnowledgeQuestionTestRequest,
    KnowledgeQuestionTestResponse,
    KnowledgeRetrievalHitData,
)
from app.services.knowledge_document_service import (
    KNOWLEDGE_TYPES,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentService,
    KnowledgeDocumentStateError,
    KnowledgeDocumentValidationError,
    latest_revision,
)
from app.services.knowledge_processing_service import KnowledgeProcessingError
from app.services.knowledge_index_service import (
    KnowledgeIndexBuildError,
    KnowledgeIndexNotFoundError,
    KnowledgeIndexService,
    KnowledgeIndexStateError,
)
from app.services.knowledge_test_service import KnowledgeTestService
from app.rag.errors import RagError


router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])


@router.post(
    "/question-tests",
    response_model=KnowledgeQuestionTestResponse,
)
def test_knowledge_question(
    request: KnowledgeQuestionTestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeQuestionTestResponse:
    try:
        result = KnowledgeTestService(db).test_question(
            tenant_id=admin.tenant_id,
            question=request.question,
            build_id=request.build_id,
            top_k=request.top_k,
        )
    except KnowledgeIndexNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeIndexStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RagError as error:
        raise HTTPException(
            status_code=502,
            detail=f"知识库测试失败：{error.info.code}",
        ) from error
    return KnowledgeQuestionTestResponse(
        data=KnowledgeQuestionTestData(
            build=_index_build_data(result.build),
            answer=result.answer,
            original_query=result.original_query,
            rewritten_query=result.rewritten_query,
            knowledge_type_filter=result.knowledge_type_filter,
            hits=[
                KnowledgeRetrievalHitData(**hit)
                for hit in result.hits
            ],
        )
    )


@router.get(
    "/index-builds",
    response_model=KnowledgeIndexBuildListResponse,
)
def list_knowledge_index_builds(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeIndexBuildListResponse:
    try:
        result = KnowledgeIndexService(db).list_for_tenant(
            tenant_id=admin.tenant_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    except KnowledgeIndexStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return KnowledgeIndexBuildListResponse(
        data=[_index_build_data(build) for build in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/index-builds",
    response_model=KnowledgeIndexBuildResponse,
    status_code=201,
)
def create_knowledge_index_build(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeIndexBuildResponse:
    try:
        build = KnowledgeIndexService(db).create_candidate(
            tenant_id=admin.tenant_id,
            triggered_by=admin.id,
        )
    except KnowledgeIndexStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except KnowledgeIndexBuildError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return KnowledgeIndexBuildResponse(data=_index_build_data(build))


@router.get(
    "/index-builds/{build_id}",
    response_model=KnowledgeIndexBuildResponse,
)
def get_knowledge_index_build(
    build_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeIndexBuildResponse:
    try:
        build = KnowledgeIndexService(db).get_for_tenant(
            tenant_id=admin.tenant_id,
            build_id=build_id,
        )
    except KnowledgeIndexNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return KnowledgeIndexBuildResponse(data=_index_build_data(build))


@router.post(
    "/index-builds/{build_id}/activate",
    response_model=KnowledgeIndexBuildResponse,
)
def activate_knowledge_index_build(
    build_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeIndexBuildResponse:
    try:
        build = KnowledgeIndexService(db).activate(
            tenant_id=admin.tenant_id,
            build_id=build_id,
        )
    except KnowledgeIndexNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeIndexStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeIndexBuildResponse(data=_index_build_data(build))


@router.post(
    "/index-builds/rollback",
    response_model=KnowledgeIndexBuildResponse,
)
def rollback_knowledge_index_build(
    request: KnowledgeRollbackRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeIndexBuildResponse:
    try:
        build = KnowledgeIndexService(db).rollback(
            tenant_id=admin.tenant_id,
            target_build_id=request.target_build_id,
        )
    except KnowledgeIndexNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeIndexStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeIndexBuildResponse(data=_index_build_data(build))


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_knowledge_documents(
    parse_status: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    knowledge_type: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeDocumentListResponse:
    try:
        result = KnowledgeDocumentService(db).list_for_tenant(
            tenant_id=admin.tenant_id,
            parse_status=parse_status,
            review_status=review_status,
            knowledge_type=knowledge_type,
            search=search,
            page=page,
            page_size=page_size,
        )
    except KnowledgeDocumentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return KnowledgeDocumentListResponse(
        data=[_document_list_item(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=201,
)
def upload_knowledge_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=200),
    knowledge_type: str = Form(...),
    category: str = Form(default="通用", max_length=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeDocumentResponse:
    try:
        document = KnowledgeDocumentService(db).create_document(
            tenant_id=admin.tenant_id,
            created_by=admin.id,
            title=title,
            knowledge_type=knowledge_type,
            category=category,
            original_filename=file.filename or "",
            stream=file.file,
        )
    except KnowledgeDocumentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        file.file.close()
    return KnowledgeDocumentResponse(data=_document_detail(document))


@router.post(
    "/documents/{document_id}/revisions",
    response_model=KnowledgeDocumentResponse,
    status_code=201,
)
def upload_knowledge_revision(
    document_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeDocumentResponse:
    try:
        document = KnowledgeDocumentService(db).create_revision(
            tenant_id=admin.tenant_id,
            document_id=document_id,
            created_by=admin.id,
            original_filename=file.filename or "",
            stream=file.file,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        file.file.close()
    return KnowledgeDocumentResponse(data=_document_detail(document))


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
)
def get_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeDocumentResponse:
    try:
        document = KnowledgeDocumentService(db).get_for_tenant(
            tenant_id=admin.tenant_id,
            document_id=document_id,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return KnowledgeDocumentResponse(data=_document_detail(document))


@router.post(
    "/revisions/{revision_id}/parse",
    response_model=KnowledgeRevisionResponse,
)
def parse_knowledge_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeRevisionResponse:
    try:
        revision = KnowledgeDocumentService(db).parse_revision(
            tenant_id=admin.tenant_id,
            revision_id=revision_id,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except KnowledgeProcessingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return KnowledgeRevisionResponse(data=_revision_data(revision))


@router.get(
    "/revisions/{revision_id}/content",
    response_model=KnowledgeContentResponse,
)
def get_knowledge_revision_content(
    revision_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeContentResponse:
    service = KnowledgeDocumentService(db)
    try:
        revision, content = service.read_processed_content(
            tenant_id=admin.tenant_id,
            revision_id=revision_id,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeContentResponse(
        data=KnowledgeContentData(
            revision=_revision_data(revision),
            content=content,
        )
    )


@router.put(
    "/revisions/{revision_id}/content",
    response_model=KnowledgeRevisionResponse,
)
def update_knowledge_revision_content(
    revision_id: int,
    request: KnowledgeContentUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeRevisionResponse:
    try:
        revision = KnowledgeDocumentService(db).update_processed_content(
            tenant_id=admin.tenant_id,
            revision_id=revision_id,
            content=request.content,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except KnowledgeDocumentStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeRevisionResponse(data=_revision_data(revision))


@router.post(
    "/revisions/{revision_id}/approve",
    response_model=KnowledgeRevisionResponse,
)
def approve_knowledge_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeRevisionResponse:
    try:
        revision = KnowledgeDocumentService(db).approve_revision(
            tenant_id=admin.tenant_id,
            revision_id=revision_id,
            reviewed_by=admin.id,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeRevisionResponse(data=_revision_data(revision))


@router.post(
    "/revisions/{revision_id}/reject",
    response_model=KnowledgeRevisionResponse,
)
def reject_knowledge_revision(
    revision_id: int,
    request: KnowledgeRejectRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeRevisionResponse:
    try:
        revision = KnowledgeDocumentService(db).reject_revision(
            tenant_id=admin.tenant_id,
            revision_id=revision_id,
            reviewed_by=admin.id,
            reason=request.reason,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeDocumentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except KnowledgeDocumentStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return KnowledgeRevisionResponse(data=_revision_data(revision))


def _document_list_item(
    document: KnowledgeDocument,
) -> KnowledgeDocumentListItem:
    return KnowledgeDocumentListItem(
        id=document.id,
        title=document.title,
        knowledge_type=document.knowledge_type,
        category=document.category,
        created_by=document.created_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
        latest_revision=_revision_data(latest_revision(document)),
    )


def _document_detail(
    document: KnowledgeDocument,
) -> KnowledgeDocumentDetailData:
    item = _document_list_item(document)
    return KnowledgeDocumentDetailData(
        **item.model_dump(),
        revisions=[
            _revision_data(revision)
            for revision in sorted(
                document.revisions,
                key=lambda value: value.version_no,
                reverse=True,
            )
        ],
    )


def _revision_data(revision: KnowledgeRevision) -> KnowledgeRevisionData:
    return KnowledgeRevisionData(
        id=revision.id,
        document_id=revision.document_id,
        version_no=revision.version_no,
        original_filename=revision.original_filename,
        source_file_type=revision.source_file_type,
        source_sha256=revision.source_sha256,
        processed_sha256=revision.processed_sha256,
        parse_status=revision.parse_status,
        parse_error_code=revision.parse_error_code,
        parse_error_message=revision.parse_error_message,
        review_status=revision.review_status,
        quality_status=revision.quality_status,
        quality_report=revision.quality_report,
        created_by=revision.created_by,
        reviewed_by=revision.reviewed_by,
        reviewed_at=revision.reviewed_at,
        review_reason=revision.review_reason,
        created_at=revision.created_at,
        updated_at=revision.updated_at,
    )


def _index_build_data(build) -> KnowledgeIndexBuildData:
    return KnowledgeIndexBuildData(
        id=build.id,
        status=build.status,
        collection_name=build.collection_name,
        revision_snapshot=list(build.revision_snapshot or []),
        document_count=build.document_count,
        chunk_count=build.chunk_count,
        triggered_by=build.triggered_by,
        error_code=build.error_code,
        error_message=build.error_message,
        previous_active_build_id=build.previous_active_build_id,
        started_at=build.started_at,
        finished_at=build.finished_at,
        activated_at=build.activated_at,
        created_at=build.created_at,
    )
