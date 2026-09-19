"""合并附注 API 路由

覆盖:
- POST /api/consolidation/notes/{project_id}/{year}  生成合并附注
- GET  /api/consolidation/notes/{project_id}/{year}  获取合并附注
- POST /api/consolidation/notes/integrate            合并附注与单体附注整合
- POST /api/consolidation/notes/{project_id}/{year}/reaggregate  重新汇总

Validates: Phase 2 Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, D12
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import require_project_access
from app.core.database import get_db
from app.models.consolidation_schemas import ConsolDisclosureSection
from app.services.consol_disclosure_service import (
    generate_consol_notes_with_flag,
    integrate_consol_notes_sync,
    save_consol_notes_sync,
)
from app.services.note_consol_drilldown_service import get_note_consol_breakdown

router = APIRouter(
    prefix="/api/consolidation/notes",
    tags=["合并附注"],
)


class ConsolNotesIntegrateRequest(BaseModel):
    """合并附注整合请求"""
    project_id: UUID
    year: int
    existing_notes: list[dict] | None = None


# ---------------------------------------------------------------------------
# 合并附注接口
# ---------------------------------------------------------------------------


@router.post("/{project_id}/{year}", response_model=list[ConsolDisclosureSection])
async def create_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """生成合并附注"""
    sections = await generate_consol_notes_with_flag(db, project_id, year)
    return sections


@router.get("/{project_id}/{year}", response_model=list[ConsolDisclosureSection])
async def get_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取合并附注"""
    sections = await generate_consol_notes_with_flag(db, project_id, year)
    return sections


@router.post("/integrate", response_model=list[ConsolDisclosureSection])
async def integrate_notes(
    data: ConsolNotesIntegrateRequest,
    project_id: UUID = Query(..., description="项目ID（用于权限校验）"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """将合并附注与 Phase 1 单体附注整合"""
    sections = integrate_consol_notes_sync(
        db, data.project_id, data.year, data.existing_notes,
    )
    return sections


@router.post("/{project_id}/{year}/save")
async def save_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """保存合并附注到数据库"""
    sections = await generate_consol_notes_with_flag(db, project_id, year)
    saved = save_consol_notes_sync(db, project_id, year, sections)
    return {
        "message": "合并附注保存成功",
        "saved_count": len(saved),
        "sections": [s.section_code for s in sections],
    }


# ---------------------------------------------------------------------------
# B.0.8 重新汇总端点（Sprint B.0）
# ---------------------------------------------------------------------------


class ReaggregateRequest(BaseModel):
    """重新汇总请求"""
    section_ids: list[str] | None = None  # None = 全部章节
    force: bool = False  # True = 忽略 stale 状态强制重算


class ReaggregateResponse(BaseModel):
    """重新汇总响应"""
    success: bool
    sections_processed: int
    sections_updated: int
    errors: list[str] = []


@router.post(
    "/{project_id}/{year}/reaggregate",
    response_model=ReaggregateResponse,
)
async def reaggregate_consol_notes(
    project_id: UUID,
    year: int,
    request: ReaggregateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """重新汇总合并附注（同步版，SSE 留 Phase 2 B.1 完善）.

    从子公司单体附注重新聚合数据到合并附注。
    可指定 section_ids 部分重算，或全部重算。
    """
    from app.services.consol_note_aggregation_service import (
        aggregate_section,
        validate_lineage_dag,
    )

    request = request or ReaggregateRequest()

    # CI-16: 校验 lineage 无环
    is_dag_valid = await validate_lineage_dag(project_id, db)
    if not is_dag_valid:
        raise HTTPException(
            status_code=400,
            detail="合并层级链存在循环引用，无法汇总",
        )

    # 确定要处理的章节
    section_ids = request.section_ids
    if not section_ids:
        # 从 CSV 映射加载所有章节
        section_ids = _load_mapped_section_ids()

    errors: list[str] = []
    updated = 0

    for sid in section_ids:
        try:
            result = await aggregate_section(
                consol_project_id=project_id,
                section_id=sid,
                year=year,
                db=db,
            )
            if result:
                updated += 1
        except Exception as err:
            errors.append(f"{sid}: {err!s}")

    return ReaggregateResponse(
        success=len(errors) == 0,
        sections_processed=len(section_ids),
        sections_updated=updated,
        errors=errors[:10],  # 最多返回 10 个错误
    )


def _load_mapped_section_ids() -> list[str]:
    """从 CSV 映射文件加载所有 section_id."""
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "consol_note_section_mapping.csv"
    if not csv_path.exists():
        return []

    section_ids: list[str] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(
            (line for line in f if not line.startswith("#")),
        )
        for row in reader:
            sid = row.get("section_id", "").strip()
            if sid:
                section_ids.append(sid)
    return section_ids


# ---------------------------------------------------------------------------
# Phase 3 附注级穿透端点（consol-phase3-frontend-drilldown / 需求 2.3）
# ---------------------------------------------------------------------------
#
# 路由顺序说明：本端点路径 {year}/{section_id}/consol-breakdown 与既有
# {year}/save、{year}/reaggregate 不冲突（后者第二段是静态 save/reaggregate，
# 本端点第二段是动态 {section_id}）。为稳妥放在所有既有路由之后注册。


@router.get("/{project_id}/{year}/{section_id}/consol-breakdown")
async def get_consol_note_breakdown(
    project_id: UUID,
    year: int,
    section_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取某合并附注章节的子公司贡献明细（附注级穿透）.

    数据来自 disclosure_notes.consolidation_breakdown（V2 汇总时写入）。
    无明细时返回空 by_company + has_breakdown=false + 中文友好提示（HTTP 200，
    不 404/500），见错误场景 EH1/EH3。
    """
    return await get_note_consol_breakdown(db, project_id, year, section_id)


# ---------------------------------------------------------------------------
# 合并附注 V2 灰度按项目开关（consol-disclosure-note-persistence Req5）
# ---------------------------------------------------------------------------
#
# 路由 {project_id}/config/consol-note-gray 为 3 段静态路径（第二段字面 config），
# 与 {project_id}/{year}（2 段、year:int）不冲突。放在所有既有路由之后注册。


class ConsolNoteGrayResponse(BaseModel):
    """合并附注 V2 灰度状态"""
    project_enabled: bool          # 项目级 opt-in（wizard_state.consol_notes_v2_enabled）
    global_enabled: bool           # 全局开关 CONSOL_NOTES_V2_ENABLED
    effective_enabled: bool        # 生效值（global OR project）


class ConsolNoteGrayUpdateRequest(BaseModel):
    """设置合并附注 V2 项目级 opt-in"""
    enabled: bool


@router.get(
    "/{project_id}/config/consol-note-gray",
    response_model=ConsolNoteGrayResponse,
)
async def get_consol_note_gray(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """读取合并附注 V2 灰度状态（项目级 opt-in / 全局 / 生效值）。"""
    import sqlalchemy as sa
    from app.core.config import settings
    from app.models.core import Project

    global_enabled = getattr(settings, "CONSOL_NOTES_V2_ENABLED", False) is True

    result = await db.execute(
        sa.select(Project.wizard_state).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = row[0]
    project_enabled = bool(ws.get("consol_notes_v2_enabled", False)) if isinstance(ws, dict) else False

    return ConsolNoteGrayResponse(
        project_enabled=project_enabled,
        global_enabled=global_enabled,
        effective_enabled=global_enabled or project_enabled,
    )


@router.put(
    "/{project_id}/config/consol-note-gray",
    response_model=ConsolNoteGrayResponse,
)
async def update_consol_note_gray(
    project_id: UUID,
    payload: ConsolNoteGrayUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """设置合并附注 V2 项目级 opt-in（现场经理+ 编辑权限）。

    写 project.wizard_state.consol_notes_v2_enabled（JSONB，flag_modified 就地改落库）。
    全局开关 True 时本 opt-in 不影响生效值（生效恒 True，向后兼容）。
    """
    import sqlalchemy as sa
    from sqlalchemy.orm.attributes import flag_modified
    from app.core.config import settings
    from app.models.core import Project

    result = await db.execute(
        sa.select(Project).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = project.wizard_state if isinstance(project.wizard_state, dict) else {}
    ws["consol_notes_v2_enabled"] = bool(payload.enabled)
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.commit()

    global_enabled = getattr(settings, "CONSOL_NOTES_V2_ENABLED", False) is True
    project_enabled = bool(payload.enabled)
    return ConsolNoteGrayResponse(
        project_enabled=project_enabled,
        global_enabled=global_enabled,
        effective_enabled=global_enabled or project_enabled,
    )
