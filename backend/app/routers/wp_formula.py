"""自定义底稿公式绑定 API（custom-workpaper-formula-binding 组①任务 2）。

- GET    /api/workpapers/{wp_id}/formulas
- PUT    /api/workpapers/{wp_id}/formulas
- DELETE /api/workpapers/{wp_id}/formulas/{formula_id}
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
from app.services.wp_formula_service import wp_formula_service
from app.services.wp_parsed_data_service import (
    format_cell_display_value,
    touch_wp_registry,
    write_cell_to_parsed_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}",
    tags=["wp-formula"],
)


class FormulaSaveRequest(BaseModel):
    sheet_name: str = Field(..., description="Sheet 名称")
    target_cell: str = Field(..., description="写入目标单元格，如 B5")
    expression: str = Field(..., description="公式表达式")
    year: int = Field(..., description="校验悬空引用所需年度")
    template_type: str = Field("soe", description="模板类型")
    category: str | None = None
    description: str | None = None


class FormulaItemResponse(BaseModel):
    id: str
    project_id: str
    wp_id: str
    sheet_name: str
    target_cell: str
    expression: str
    category: str | None = None
    description: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _formula_to_dict(f: WpFormula) -> dict:
    return {
        "id": str(f.id),
        "project_id": str(f.project_id),
        "wp_id": str(f.wp_id),
        "sheet_name": f.sheet_name,
        "target_cell": f.target_cell,
        "expression": f.expression,
        "category": f.category,
        "description": f.description,
        "created_by": str(f.created_by) if f.created_by else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


async def _load_wp(db: AsyncSession, wp_id: UUID) -> WorkingPaper:
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return wp


@router.get("/formulas")
async def list_formulas(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """列出该底稿的全部自定义公式。"""
    await _load_wp(db, wp_id)
    formulas = await wp_formula_service.list_by_wp(db, wp_id)
    return {
        "wp_id": str(wp_id),
        "count": len(formulas),
        "items": [_formula_to_dict(f) for f in formulas],
    }


@router.put("/formulas")
async def save_formula(
    wp_id: UUID,
    body: FormulaSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存（upsert）一条底稿公式；悬空引用返回 422。"""
    wp = await _load_wp(db, wp_id)
    saved, issues = await wp_formula_service.save(
        db,
        project_id=wp.project_id,
        wp_id=wp_id,
        sheet_name=body.sheet_name,
        target_cell=body.target_cell,
        expression=body.expression,
        year=body.year,
        template_type=body.template_type,
        category=body.category,
        description=body.description,
        created_by=user.id,
    )
    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "FORMULA_REF_NOT_FOUND", "issues": issues},
        )

    evaluated_value, eval_errors = await evaluate_wp_formula_expression(
        db,
        project_id=wp.project_id,
        year=body.year,
        expression=body.expression,
    )
    write_cell_to_parsed_data(
        wp,
        sheet_name=body.sheet_name,
        cell_ref=body.target_cell,
        value=format_cell_display_value(evaluated_value),
    )

    wp_code: str | None = None
    if wp.wp_index_id:
        idx = (
            await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
            )
        ).scalar_one_or_none()
        wp_code = idx

    linkage: dict | None = None
    if wp_code:
        try:
            from app.services.wp_formula_linkage_service import (
                propagate_custom_wp_cell_change,
            )

            linkage = await propagate_custom_wp_cell_change(
                db,
                project_id=wp.project_id,
                year=body.year,
                wp_code=wp_code,
                sheet_name=body.sheet_name,
                cell_ref=body.target_cell,
            )
        except Exception as linkage_err:
            logger.warning(
                "propagate_custom_wp_cell_change after wp_formula save: %s",
                linkage_err,
            )

    await db.commit()
    await touch_wp_registry(wp.project_id)

    payload: dict = {"saved": _formula_to_dict(saved)}
    payload["evaluated_value"] = str(evaluated_value)
    if eval_errors:
        payload["eval_warnings"] = eval_errors
    if linkage is not None:
        payload["linkage"] = linkage
    return payload


@router.delete("/formulas/{formula_id}")
async def delete_formula(
    wp_id: UUID,
    formula_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """删除单条底稿公式。"""
    wp = await _load_wp(db, wp_id)
    existing = (
        await db.execute(
            sa.select(WpFormula).where(
                WpFormula.id == formula_id,
                WpFormula.wp_id == wp_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="公式不存在")
    await wp_formula_service.delete(db, formula_id)
    await db.commit()
    await touch_wp_registry(wp.project_id)
    return {"deleted": str(formula_id)}
