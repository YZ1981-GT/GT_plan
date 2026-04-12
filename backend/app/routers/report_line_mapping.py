"""报表行次映射 API 路由

Validates: Requirements 3.9-3.14
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    ReferenceCopyRequest,
    ReferenceCopyResult,
    ReportLine,
    ReportLineMappingConfirm,
    ReportLineMappingResponse,
)
from app.models.core import User
from app.services import report_line_mapping_service as svc

router = APIRouter(prefix="/api/projects", tags=["report-line-mapping"])


@router.post(
    "/{project_id}/report-line-mapping/ai-suggest",
    response_model=list[dict],
)
async def ai_suggest(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """AI建议报表行次映射（当前为规则匹配占位）。

    Validates: Requirements 3.10
    """
    return await svc.ai_suggest_mappings(project_id, db)


@router.get(
    "/{project_id}/report-line-mapping",
    response_model=list[ReportLineMappingResponse],
)
async def get_mappings(
    project_id: UUID,
    report_type: str | None = Query(None, description="筛选报表类型"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportLineMappingResponse]:
    """获取报表行次映射列表。

    Validates: Requirements 3.9
    """
    return await svc.get_mappings(project_id, db, report_type=report_type)


@router.put(
    "/{project_id}/report-line-mapping/{mapping_id}/confirm",
    response_model=ReportLineMappingResponse,
)
async def confirm_mapping(
    project_id: UUID,
    mapping_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportLineMappingResponse:
    """确认单条报表行次映射。

    Validates: Requirements 3.11
    """
    return await svc.confirm_mapping(project_id, mapping_id, db)


@router.post(
    "/{project_id}/report-line-mapping/batch-confirm",
    response_model=dict,
)
async def batch_confirm(
    project_id: UUID,
    body: ReportLineMappingConfirm,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """批量确认报表行次映射。

    Validates: Requirements 3.11
    """
    count = await svc.batch_confirm(project_id, body.mapping_ids, db)
    return {"confirmed_count": count}


@router.post(
    "/{project_id}/report-line-mapping/reference-copy",
    response_model=ReferenceCopyResult,
)
async def reference_copy(
    project_id: UUID,
    body: ReferenceCopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReferenceCopyResult:
    """集团内企业一键参照复制。

    Validates: Requirements 3.12, 3.13
    """
    return await svc.reference_copy(body.source_company_code, project_id, db)


@router.get(
    "/{project_id}/report-line-mapping/report-lines",
    response_model=list[ReportLine],
)
async def get_report_lines(
    project_id: UUID,
    report_type: str | None = Query(None, description="筛选报表类型"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportLine]:
    """获取已确认的报表行次列表（供调整分录下拉）。

    Validates: Requirements 3.9
    """
    return await svc.get_report_lines(project_id, db, report_type=report_type)
