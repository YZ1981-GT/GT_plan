"""账表导入智能增强 API

提供：
- 列映射模糊匹配建议
- 深度数据质量校验
- 增量导入准备
- 导入结果概览
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.import_intelligence import (
    enhance_column_mapping,
    deep_quality_check,
    prepare_incremental_import,
    generate_import_overview,
    detect_sheet_type_by_content,
)

router = APIRouter(prefix="/api/projects/{project_id}/import-intelligence", tags=["导入智能"])


class EnhanceMappingRequest(BaseModel):
    headers: list[str]
    existing_mapping: dict[str, str]


class IncrementalPrepareRequest(BaseModel):
    mode: str  # full_replace / append_period / append_dimension / merge
    period: str | None = None


@router.post("/enhance-mapping")
async def enhance_mapping(
    project_id: UUID,
    data: EnhanceMappingRequest,
    current_user: User = Depends(get_current_user),
):
    """增强列映射：对未匹配的列尝试模糊匹配

    返回自动匹配结果 + 需用户确认的建议 + 仍未匹配的列。
    """
    result = enhance_column_mapping(data.headers, data.existing_mapping)
    return result


@router.get("/quality-check")
async def quality_check(
    project_id: UUID,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """深度数据质量校验（导入后执行）

    5项校验：科目格式/金额异常/日期连续性/借贷平衡/余额vs序时账一致性
    返回质量评分（A/B/C/D）+ 问题列表。
    """
    return await deep_quality_check(db, project_id, year)


@router.post("/prepare-incremental")
async def prepare_incremental(
    project_id: UUID,
    data: IncrementalPrepareRequest,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """准备增量导入：分析现有数据，返回追加策略

    支持4种模式：
    - full_replace: 全量替换（默认）
    - append_period: 按月份追加（如只追加10月数据）
    - append_dimension: 按辅助维度追加
    - merge: 合并（新增+更新，不删除）
    """
    return await prepare_incremental_import(db, project_id, year, data.mode, data.period)


@router.get("/overview")
async def import_overview(
    project_id: UUID,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导入结果概览（供前端可视化）

    包含：按科目类别汇总、按月份分布、关键指标、质量评分。
    """
    overview = await generate_import_overview(db, project_id, year)
    quality = await deep_quality_check(db, project_id, year)
    overview["quality"] = {"score": quality["score"], "grade": quality["grade"], "findings_count": len(quality["findings"])}
    return overview
