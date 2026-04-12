"""
AI Knowledge Base Router

Provides endpoints for:
- GET  /api/projects/{id}/knowledge/index         — check index status
- POST /api/projects/{id}/knowledge/build        — trigger full rebuild
- POST /api/projects/{id}/knowledge/search       — semantic search
- POST /api/projects/{id}/knowledge/search-cross-year — cross-year search
- DELETE /api/projects/{id}/knowledge/index      — delete index
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.core import Project
from app.services.knowledge_index_service import KnowledgeIndexService

router = APIRouter(prefix="/api/projects", tags=["ai-knowledge"])


# -------------------------------------------------------------------------
# Request / Response Models
# -------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    source_type: str
    source_id: str
    content: str
    score: float
    chunk_index: int | None = None
    project_id: str | None = None
    is_prior: bool | None = None


class IndexStatusResponse(BaseModel):
    project_id: str
    total_chunks: int
    by_source_type: dict[str, int]
    is_indexed: bool


class BuildResponse(BaseModel):
    project_id: str
    indexed_chunks: int
    message: str


class SearchResponse(BaseModel):
    project_id: str | None = None
    query: str
    results: list[SearchResultItem]
    total: int


class DeleteIndexResponse(BaseModel):
    project_id: str
    message: str


# -------------------------------------------------------------------------
# Dependencies
# -------------------------------------------------------------------------


async def get_knowledge_service(
    db=Depends(get_db),
) -> KnowledgeIndexService:
    return KnowledgeIndexService(db)


async def _get_project_or_404(
    project_id: UUID,
    db: AsyncSession,
) -> Project:
    """Fetch project by ID or raise 404."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


async def _get_prior_year_project_id(
    project_id: UUID,
    db: AsyncSession,
) -> UUID | None:
    """
    Find the prior year project for cross-year search.
    Strategy: look for another project with the same client_name
    and an audit_period_end that is one year before the current project's
    audit_period_end (or audit_period_start).
    """
    # First get the current project to know its year and client
    current = await _get_project_or_404(project_id, db)

    # Determine current audit year
    ref_date = current.audit_period_end or current.audit_period_start
    if ref_date is None:
        return None
    current_year = ref_date.year

    # Find another project for the same client, one year prior
    prior_year = current_year - 1
    result = await db.execute(
        select(Project)
        .where(
            Project.client_name == current.client_name,
            Project.is_deleted == False,
        )
    )
    for p in result.scalars().all():
        ref = p.audit_period_end or p.audit_period_start
        if ref and ref.year == prior_year:
            return p.id

    return None


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------


@router.get(
    "/{project_id}/knowledge/index",
    response_model=IndexStatusResponse,
)
async def check_index_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    knowledge_svc: KnowledgeIndexService = Depends(get_knowledge_service),
) -> IndexStatusResponse:
    """Check knowledge base index status for a project."""
    await _get_project_or_404(project_id, db)
    status_info = await knowledge_svc.get_index_status(project_id)
    return IndexStatusResponse(**status_info)


@router.post(
    "/{project_id}/knowledge/build",
    response_model=BuildResponse,
)
async def trigger_build(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    knowledge_svc: KnowledgeIndexService = Depends(get_knowledge_service),
) -> BuildResponse:
    """Trigger full rebuild of project knowledge base index."""
    await _get_project_or_404(project_id, db)
    indexed_chunks = await knowledge_svc.build_index(project_id)
    return BuildResponse(
        project_id=str(project_id),
        indexed_chunks=indexed_chunks,
        message=f"Indexed {indexed_chunks} chunks successfully",
    )


@router.post(
    "/{project_id}/knowledge/search",
    response_model=SearchResponse,
)
async def semantic_search(
    project_id: UUID,
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    knowledge_svc: KnowledgeIndexService = Depends(get_knowledge_service),
) -> SearchResponse:
    """Perform semantic search on project knowledge base."""
    await _get_project_or_404(project_id, db)
    results = await knowledge_svc.semantic_search(
        project_id=project_id,
        query=request.query,
        top_k=request.top_k,
    )
    return SearchResponse(
        project_id=str(project_id),
        query=request.query,
        results=[SearchResultItem(**r) for r in results],
        total=len(results),
    )


@router.post(
    "/{project_id}/knowledge/search-cross-year",
    response_model=SearchResponse,
)
async def cross_year_search(
    project_id: UUID,
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    knowledge_svc: KnowledgeIndexService = Depends(get_knowledge_service),
) -> SearchResponse:
    """
    Cross-year semantic search: search both current project and prior year project.
    Prior project is determined from the current project's client_name and audit year.
    """
    await _get_project_or_404(project_id, db)

    prior_project_id = await _get_prior_year_project_id(project_id, db)
    if not prior_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prior year project found for project {project_id}",
        )

    results = await knowledge_svc.search_cross_year(
        project_id=project_id,
        prior_project_id=prior_project_id,
        query=request.query,
    )
    return SearchResponse(
        query=request.query,
        results=[SearchResultItem(**r) for r in results],
        total=len(results),
    )


@router.delete(
    "/{project_id}/knowledge/index",
    response_model=DeleteIndexResponse,
)
async def delete_project_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    knowledge_svc: KnowledgeIndexService = Depends(get_knowledge_service),
) -> DeleteIndexResponse:
    """Delete all knowledge base index data for a project."""
    await _get_project_or_404(project_id, db)
    await knowledge_svc.delete_index(project_id)
    return DeleteIndexResponse(
        project_id=str(project_id),
        message="Index deleted successfully",
    )
