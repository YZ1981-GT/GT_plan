"""科目映射 API 路由

Validates: Requirements 3.1-3.8
"""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.audit_platform_schemas import (
    AutoMatchResult,
    MappingCompletionRate,
    MappingInput,
    MappingResponse,
    MappingResult,
    MappingSuggestion,
    MappingUpdateInput,
    MappingYearInput,
)
from app.models.core import User
from app.services import mapping_service

router = APIRouter(prefix="/api/projects", tags=["mapping"])


@router.post(
    "/{project_id}/mapping/auto-suggest",
    response_model=list[MappingSuggestion],
)
async def auto_suggest(
    project_id: UUID,
    year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> list[MappingSuggestion]:
    """自动匹配建议：编码前缀→名称精确→名称模糊。

    Validates: Requirements 3.1
    """
    return await mapping_service.auto_suggest(project_id, db, year=year)


@router.post(
    "/{project_id}/mapping/auto-match",
    response_model=AutoMatchResult,
)
async def auto_match(
    project_id: UUID,
    body: MappingYearInput | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> AutoMatchResult:
    """自动匹配并直接保存映射结果。

    已映射的科目不会被覆盖，返回完整匹配详情供用户确认。

    手动触发同样回写 active 数据集的 ``validation_summary.auto_map``：否则入库时自动映射
    失败留下的红色提示，在用户点「重新映射」修好之后仍然挂着（状态只写不清）。
    """
    result = await mapping_service.auto_match(project_id, db, year=body.year if body else None)
    try:
        from app.services.event_handlers._impl import record_auto_map_outcome

        await record_auto_map_outcome(
            project_id, body.year if body else None, result=result, error=None,
        )
    except Exception:  # noqa: BLE001 — 状态回写失败不影响映射本身（已提交）
        import logging

        logging.getLogger(__name__).warning("auto-match 结果回写数据集失败", exc_info=True)
    return result


@router.get(
    "/{project_id}/mapping",
    response_model=list[MappingResponse],
)
async def get_mappings(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> list[MappingResponse]:
    """获取映射列表。

    Validates: Requirements 3.8
    """
    return await mapping_service.get_mappings(project_id, db)


@router.post(
    "/{project_id}/mapping",
    response_model=MappingResponse,
)
async def save_mapping(
    project_id: UUID,
    mapping: MappingInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> MappingResponse:
    """保存单条映射。

    Validates: Requirements 3.3
    """
    record = await mapping_service.save_mapping(project_id, mapping, db)
    return MappingResponse.model_validate(record)


@router.put(
    "/{project_id}/mapping/{mapping_id}",
    response_model=MappingResponse,
)
async def update_mapping(
    project_id: UUID,
    mapping_id: UUID,
    body: MappingUpdateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> MappingResponse:
    """修改映射。

    Validates: Requirements 3.7
    """
    record = await mapping_service.update_mapping(
        project_id, mapping_id, body.standard_account_code, db, year=body.year
    )
    return MappingResponse.model_validate(record)


@router.post(
    "/{project_id}/mapping/batch-confirm",
    response_model=MappingResult,
)
async def batch_confirm(
    project_id: UUID,
    mappings: list[MappingInput],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> MappingResult:
    """批量确认映射。

    Validates: Requirements 3.5
    """
    return await mapping_service.batch_confirm(project_id, mappings, db)


@router.get(
    "/{project_id}/mapping/completion-rate",
    response_model=MappingCompletionRate,
)
async def get_completion_rate(
    project_id: UUID,
    year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> MappingCompletionRate:
    """获取映射完成率。

    Validates: Requirements 3.5, 3.6
    """
    return await mapping_service.get_completion_rate(project_id, db, year=year)
