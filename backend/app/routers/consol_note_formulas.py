"""合并附注单元格公式（spec consol-elimination-single-source-push 任务 7，design §十 公式管理「合并附注」节点）。

模板级配置（不属于某个项目）：读 = 已登录；写 = admin / partner / manager（design §十）。
改动后前端对当前合并项目调 ``POST /api/consolidation/{pid}/{year}/push``（公式是模板级，后端不知道该推哪个项目）。
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
    create_note_formula,
    delete_note_formula,
    find_table,
    formula_to_dict,
    list_note_formulas,
    seed_note_formulas,
    update_note_formula,
)

router = APIRouter(prefix="/api/consol-note-formulas", tags=["合并附注公式"])

EDITOR_ROLES = ["admin", "partner", "manager"]


def _error(exc: NoteFormulaError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.get("")
async def get_note_formulas(
    template_type: str = Query("soe", description="soe / listed"),
    section_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按章节列出合并附注公式（单元格位置、公式、来源：自动种子 / 人工）。

    首次读取（或模板 / 合并口径报表配置变化后）按需种子化并提交 —— 写的是模板级派生配置，不是项目数据。
    """
    try:
        result = await list_note_formulas(db, template_type, section_id)
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    return result


@router.post("", status_code=201)
async def add_note_formula(
    body: ConsolNoteFormulaCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    try:
        row = await create_note_formula(
            db, template_type=body.template_type, section_id=body.section_id, row_index=body.row_index,
            col_index=body.col_index, formula=body.formula, description=body.description, user_id=user.id,
        )
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    return formula_to_dict(row, find_table(row.template_type, row.section_id))


@router.put("/{formula_id}")
async def edit_note_formula(
    formula_id: UUID,
    body: ConsolNoteFormulaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    """改公式 ⇒ 来源变为「人工」（之后自动种子不再覆盖该单元格）。"""
    try:
        row = await update_note_formula(db, formula_id, formula=body.formula, description=body.description,
                                        user_id=user.id)
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    return formula_to_dict(row, find_table(row.template_type, row.section_id))


@router.delete("/{formula_id}")
async def remove_note_formula(
    formula_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(EDITOR_ROLES)),
):
    """删除（软删；自动种子不再补回该单元格）。"""
    try:
        row = await delete_note_formula(db, formula_id, user_id=user.id)
    except NoteFormulaError as e:
        await db.rollback()
        raise _error(e) from e
    await db.commit()
    return {"id": str(row.id), "deleted": True}


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
