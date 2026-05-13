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
    ReportLineMappingUpdate,
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
    "/{project_id}/report-line-mapping/{mapping_id}",
    response_model=ReportLineMappingResponse,
)
async def update_mapping(
    project_id: UUID,
    mapping_id: UUID,
    body: ReportLineMappingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportLineMappingResponse:
    return await svc.update_mapping(project_id, mapping_id, body, db)


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


@router.delete(
    "/{project_id}/report-line-mapping/{mapping_id}",
    response_model=dict,
)
async def delete_mapping(
    project_id: UUID,
    mapping_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await svc.delete_mapping(project_id, mapping_id, db)
    return {"deleted": True, "id": str(mapping_id)}


@router.post(
    "/{project_id}/report-line-mapping/manual",
    response_model=dict,
)
async def create_manual_mapping(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """手动创建单条报表行次映射（用户从下拉选择报表项目）。"""
    from app.models.audit_platform_models import (
        ReportLineMapping,
        ReportLineMappingType,
        ReportType,
    )

    std_code = body.get("standard_account_code", "").strip()
    report_type_str = body.get("report_type", "balance_sheet")
    line_code = body.get("report_line_code", "").strip()
    line_name = body.get("report_line_name", "").strip()

    if not std_code or not line_code:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="科目编码和报表行次编码不能为空")

    # 解析 report_type
    try:
        rt = ReportType(report_type_str)
    except ValueError:
        rt = ReportType.balance_sheet

    # 检查是否已存在
    from sqlalchemy import select
    existing = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.standard_account_code == std_code,
            ReportLineMapping.report_type == rt,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        return {"created": False, "message": "该科目已有映射"}

    mapping = ReportLineMapping(
        project_id=project_id,
        standard_account_code=std_code,
        report_type=rt,
        report_line_code=line_code,
        report_line_name=line_name,
        report_line_level=1,
        parent_line_code=None,
        mapping_type=ReportLineMappingType.manual,
        is_confirmed=True,  # 手动映射直接确认
    )
    db.add(mapping)
    await db.flush()
    await db.commit()
    return {"created": True, "id": str(mapping.id)}


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
