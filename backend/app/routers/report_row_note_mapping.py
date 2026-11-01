"""报表行次 → 附注编号（从 ``report_config.py`` 迁出，路径不变：``GET /api/report-config/row-note-mapping``）。

在 ``router_registry/report.py`` §4 里**先于** ``report_config`` 注册：同前缀的 ``GET /{config_id}`` 会把
``row-note-mapping`` 当成配置 id 截走（迁出前恒 422，报表页附注列从未用上它）。守卫 ``tests/test_route_shadow_guard.py``。

spec platform-performance-residual-findings-closure R2：带 ``project_id`` + ``year`` 时返回导出 Excel 附注列同一份格值
（``services/report_note_refs.py``），报表页与交付件编号一致；不带时按静态映射原样返回（兼容旧调用）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.services.report_note_refs import project_row_note_refs, static_row_note_mapping

router = APIRouter(prefix="/api/report-config", tags=["report-config"])

_TEMPLATE_TYPES = frozenset({"soe", "listed"})
_REPORT_SCOPES = frozenset({"standalone", "consolidated"})


@router.get("/row-note-mapping")
async def get_row_note_mapping(
    applicable_standard: str = Query(..., description="变体标识如 soe_standalone/listed_standalone"),
    project_id: UUID | None = Query(None, description="与 year 同给时按导出 Excel 同一编号方案返回各行附注列格值"),
    year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """报表行次 → 附注编号。

    * 只给 ``applicable_standard``：静态映射 ``{模板编码: {section_code, section_title, seq}}``。
    * 同时给 ``project_id`` 与 ``year``：先校验项目只读权限，返回 ``{库内 row_code: {section_code, section_title,
      seq, display}, "_meta": {source, has_notes}}``，``display`` 即导出该行附注列的格值（``None`` = 导出留空）。
    """
    if project_id is None or year is None:
        return static_row_note_mapping(applicable_standard)
    template_type, _, report_scope = applicable_standard.partition("_")
    if template_type not in _TEMPLATE_TYPES or report_scope not in _REPORT_SCOPES:
        raise HTTPException(status_code=422, detail=f"不支持的报表口径：{applicable_standard}")
    await assert_project_permission(db, current_user, project_id, "readonly")
    return await project_row_note_refs(
        db, project_id, year, template_type=template_type, report_scope=report_scope,
    )
