"""数据导入 API 路由

Validates: Requirements 4.3, 4.4, 4.23
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    ImportBatchResponse,
    ImportProgress,
)
from app.models.core import User
from app.services import import_service

router = APIRouter(prefix="/api/projects/{project_id}/import", tags=["import"])


@router.post("", response_model=ImportBatchResponse)
async def upload_and_import(
    project_id: UUID,
    file: UploadFile = File(...),
    source_type: str = Form(default="generic"),
    data_type: str = Form(...),
    year: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportBatchResponse:
    """Upload file and start import (multipart form).

    Validates: Requirements 4.3
    """
    batch = await import_service.start_import(
        project_id=project_id,
        file=file,
        source_type=source_type,
        data_type=data_type,
        year=year,
        db=db,
    )
    return ImportBatchResponse.model_validate(batch)


@router.get("/{batch_id}/progress", response_model=ImportProgress)
async def get_import_progress(
    project_id: UUID,
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportProgress:
    """Get import progress for a batch.

    Validates: Requirements 4.4
    """
    return await import_service.get_import_progress(batch_id, db)


@router.get("/batches", response_model=list[ImportBatchResponse])
async def list_import_batches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ImportBatchResponse]:
    """List all import batches for a project."""
    return await import_service.get_import_batches(project_id, db)


@router.post("/{batch_id}/rollback", response_model=ImportBatchResponse)
async def rollback_import(
    project_id: UUID,
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportBatchResponse:
    """Rollback an import batch.

    Validates: Requirements 4.23
    """
    batch = await import_service.rollback_import(batch_id, db)
    return ImportBatchResponse.model_validate(batch)
