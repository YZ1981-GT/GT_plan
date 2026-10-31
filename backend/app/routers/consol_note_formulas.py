"""合并附注单元格公式（spec consol-elimination-single-source-push 任务 7，design §十 公式管理「合并附注」节点）。

模板级配置（不属于某个项目）：读 = 已登录；写 = admin（ADR-CNS-02；原 admin / partner / manager）。
改动后前端对当前合并项目调 ``POST /api/consolidation/{pid}/{year}/push``（公式是模板级，后端不知道该推哪个项目）。

formula-global-settings-sync：模板级表即合并附注域的全局层，增删改经全局发布（版本 + 同步内核）；
修改 / 删除须带 ``expected_version``（缺 428、不符 409）；本项目改过该单元格的项目按内核跟随或生成待确认。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.consolidation_schemas import ConsolNoteFormulaCreate, ConsolNoteFormulaUpdate
from app.models.core import User
from app.services.consol_note_formula_service import (
    NoteFormulaError,
    find_table,
    formula_to_dict,
    list_note_formulas,
    seed_note_formulas,
)
from app.services.formula_settings import consol_note_settings as settings
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.permissions import can_edit_global
from app.services.formula_settings.outbox import record_changes, publish_pending

router = APIRouter(prefix="/api/consol-note-formulas", tags=["合并附注公式"])

EDITOR_ROLES = ["admin"]


def _error(exc: NoteFormulaError | FormulaSettingError) -> HTTPException:
    if isinstance(exc, FormulaSettingError):
        return HTTPException(status_code=exc.status_code, detail=exc.to_detail())
    return HTTPException(status_code=exc.status, detail=str(exc))


async def _commit_and_notify(db: AsyncSession, events: list[dict]) -> None:
    if events:
        await record_changes(db, events=events, domain=settings.DOMAIN, source="direct_edit")
    await db.commit()
    await publish_pending(db)


@router.get("")
async def get_note_formulas(
    template_type: str = Query("soe", description="soe / listed"),
    section_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按章节列出合并附注公式（单元格位置、公式、来源：自动种子 / 人工）。

    首次读取（或模板 / 合并口径报表配置变化后）按需种子化并提交 —— 写的是模板级派生配置，不是项目数据。
    响应包含 ``can_edit_global``：调用方据此显示或隐藏编辑控件。
    """
    try:
        result = await list_note_formulas(db, template_type, section_id)
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    result["can_edit_global"] = can_edit_global(user)
    return result


@router.post("", status_code=201)
async def add_note_formula(
    body: ConsolNoteFormulaCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    try:
        row, events = await settings.create_formula(
            db, template_type=body.template_type, section_id=body.section_id, row_index=body.row_index,
            col_index=body.col_index, formula=body.formula, description=body.description, user_id=user.id,
        )
        out = formula_to_dict(row, find_table(row.template_type, row.section_id))
    except (NoteFormulaError, FormulaSettingError) as e:
        await db.rollback()
        raise _error(e) from e
    await _commit_and_notify(db, events)
    return out


@router.put("/{formula_id}")
async def edit_note_formula(
    formula_id: UUID,
    body: ConsolNoteFormulaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    """改公式 ⇒ 来源变为「人工」（之后自动种子不再覆盖该单元格）。须带 ``expected_version``。"""
    try:
        row, events = await settings.update_formula(
            db, formula_id, formula=body.formula, description=body.description,
            expected_version=body.expected_version, user_id=user.id)
        out = formula_to_dict(row, find_table(row.template_type, row.section_id))
    except (NoteFormulaError, FormulaSettingError) as e:
        await db.rollback()
        raise _error(e) from e
    await _commit_and_notify(db, events)
    return out


@router.delete("/{formula_id}")
async def remove_note_formula(
    formula_id: UUID,
    expected_version: int | None = Query(None, description="当前版本号（必填，防并发覆盖）"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    """删除（软删；自动种子不再补回该单元格）。须带 ``expected_version``。"""
    try:
        row, events = await settings.delete_formula(db, formula_id, expected_version=expected_version,
                                                    user_id=user.id)
        out = {"id": str(row.id), "deleted": True}
    except (NoteFormulaError, FormulaSettingError) as e:
        await db.rollback()
        raise _error(e) from e
    await _commit_and_notify(db, events)
    return out


@router.post("/seed")
async def reseed_note_formulas(
    template_type: str = Query(..., description="soe / listed"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    """按当前模板与合并口径报表配置重新种子化（幂等；不覆盖人工公式、不补回人工删除的）。"""
    try:
        result = await seed_note_formulas(db, template_type)
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    return result.to_dict()
