"""行名对齐层底稿级端点（formula-row-name-alignment-confirmation Task 8）。

独立路由文件（与 wp_render_config 分离，避免与并发会话同改一文件）：
扩展底稿级刷新链在「名称维度」的可见化 + 裁决入口 —— 不新建平行刷新端点。

- POST /api/workpapers/{wp_id}/row-name-alignment（只读）：逐行 match_state + 候选 + 映射来源
- POST /api/workpapers/{wp_id}/row-name-mapping/confirm（写，单事务）：批量确认

门禁复用 `require_wp_edit_permission`（编辑权）。router prefix 与 tags 与 wp-render-config
一致以并入同一 workpaper 路由族；注册见 router_registry。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_wp_edit_permission
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.project_audit_year import PROJECT_AUDIT_YEAR_SQL

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-render-config"],
)


class _RowAlignInputModel(BaseModel):
    row_key: str
    row_label: str
    account_prefixes: list[str] = Field(default_factory=list)


class RowAlignmentRequest(BaseModel):
    """底稿级刷新的名称对齐请求：逐行行名 + 该行科目前缀集。"""

    sheet_code: str
    rows: list[_RowAlignInputModel] = Field(default_factory=list)
    dataset_id: str | None = None


class _TargetIdentityModel(BaseModel):
    source_kind: str
    account_code: str
    aux_type: str | None = None
    aux_name: str
    dimension_key: str
    dataset_id: str | None = None


class _RowConfirmModel(BaseModel):
    row_key: str
    targets: list[_TargetIdentityModel] = Field(default_factory=list)
    base_mapping_version: int | None = None


class RowMappingConfirmRequest(BaseModel):
    """批量确认请求（单事务、幂等、版本冲突检测）。"""

    sheet_code: str
    rows: list[_RowConfirmModel] = Field(default_factory=list)
    idempotency_key: str
    dataset_id: str | None = None
    base_mapping_version: int | None = None  # 兼容整体 base；行级优先


async def _resolve_wp_scope(db: AsyncSession, wp_id: UUID):
    """wp_id → (wp_code, project_id, year)；不存在抛 404 / 无年度抛 422。"""
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    wp_index = (
        await db.execute(sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id))
    ).scalars().first()
    wp_code = wp_index.wp_code if wp_index else ""
    year_row = (
        await db.execute(PROJECT_AUDIT_YEAR_SQL, {"pid": str(wp.project_id)})
    ).first()
    project_year = year_row[0] if year_row and year_row[0] else None
    if not project_year:
        raise HTTPException(status_code=422, detail="项目未设置审计期间，无法取数")
    return wp_code, wp.project_id, int(project_year)


_WP_ACCOUNT_MAPPING_CACHE: dict[str, list[str]] | None = None


def _resolve_account_prefixes(wp_code: str, sheet_code: str) -> list[str]:
    """按 wp_code / sheet_code 从 wp_account_mapping.json 解析科目原始码前缀（后端职责）。

    优先精确 sheet_code，回退 wp_code，再回退 wp_code 一级前缀（如 D3-2 → D3）。
    无映射返回 []（候选生成得空、行判 unmatched）。
    """
    global _WP_ACCOUNT_MAPPING_CACHE
    if _WP_ACCOUNT_MAPPING_CACHE is None:
        import json as _json
        from pathlib import Path as _Path

        _WP_ACCOUNT_MAPPING_CACHE = {}
        try:
            mp = _Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
            data = _json.loads(mp.read_text(encoding="utf-8"))
            for m in data.get("mappings", []):
                code = str(m.get("wp_code") or "").strip()
                codes = [str(c).strip() for c in (m.get("account_codes") or []) if str(c).strip()]
                if code and codes:
                    _WP_ACCOUNT_MAPPING_CACHE[code] = codes
        except Exception:  # noqa: BLE001
            logger.warning("row-name-alignment: 加载 wp_account_mapping 失败", exc_info=True)

    table = _WP_ACCOUNT_MAPPING_CACHE
    for key in (sheet_code, wp_code):
        k = str(key or "").strip()
        if k and k in table:
            return list(table[k])
    top = str(wp_code or "").split("-", 1)[0].strip()
    return list(table.get(top, []))


@router.post("/{wp_id}/row-name-alignment")
async def row_name_alignment(
    wp_id: UUID,
    body: RowAlignmentRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_wp_edit_permission()),
):
    """底稿级刷新的名称对齐：逐行返回 match_state + 候选 + 映射来源（Requirement 1.1 / 1.3 / 3.3）。

    只读，不写库。已确认且未失效的映射自动生效（不触发弹窗，has_pending=false）。
    """
    from app.services.four_table.row_name_alignment import CandidateSourceError
    from app.services.row_name_alignment_wire import (
        RowAlignmentInput,
        build_alignment_wire,
    )
    from app.services.row_name_mapping_service import MappingScope

    wp_code, project_id, year = await _resolve_wp_scope(db, wp_id)
    scope = MappingScope(
        project_id=project_id, year=year, wp_code=wp_code, sheet_code=body.sheet_code
    )
    # 🔴 科目定位是后端职责（红基线 3）：前端行未带 account_prefixes 时，按 wp_code/sheet_code
    #    从 wp_account_mapping 兜底解析，前端只需传行名 —— 不让前端知道科目码。
    fallback_prefixes = _resolve_account_prefixes(wp_code, body.sheet_code)
    rows = [
        RowAlignmentInput(
            row_key=r.row_key,
            row_label=r.row_label,
            account_prefixes=list(r.account_prefixes or []) or fallback_prefixes,
        )
        for r in body.rows
    ]
    try:
        return await build_alignment_wire(db, scope, rows, dataset_id=body.dataset_id)
    except CandidateSourceError as exc:
        # 🔴 复盘 #5：取数源出错返回可识别错误码，不伪装成「无候选/unmatched」
        raise HTTPException(
            status_code=502,
            detail={"message": "账套取数源异常，无法生成候选", "source": exc.source},
        ) from exc


@router.post("/{wp_id}/row-name-mapping/confirm")
async def confirm_row_name_mapping(
    wp_id: UUID,
    body: RowMappingConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_wp_edit_permission()),
):
    """批量确认行名映射（单事务全回滚、幂等、版本冲突 409；Requirement 3.6）。

    router 层负责 commit / rollback（service 只 flush）。
    """
    from app.services.four_table.row_name_alignment import TargetIdentity
    from app.services.row_name_mapping_service import (
        MappingConflictError,
        MappingScope,
        RowConfirmInput,
        RowNameMappingService,
    )

    wp_code, project_id, year = await _resolve_wp_scope(db, wp_id)
    scope = MappingScope(
        project_id=project_id, year=year, wp_code=wp_code, sheet_code=body.sheet_code
    )
    confirm_rows = [
        RowConfirmInput(
            row_key=r.row_key,
            targets=[
                TargetIdentity(
                    source_kind=t.source_kind,
                    account_code=t.account_code,
                    aux_type=t.aux_type,
                    aux_name=t.aux_name,
                    dimension_key=t.dimension_key,
                    dataset_id=t.dataset_id,
                )
                for t in r.targets
            ],
            base_mapping_version=(
                r.base_mapping_version
                if r.base_mapping_version is not None
                else body.base_mapping_version
            ),
        )
        for r in body.rows
    ]
    svc = RowNameMappingService(db)
    try:
        result = await svc.batch_confirm(
            scope,
            confirm_rows,
            confirmed_by=user.id,
            idempotency_key=body.idempotency_key,
            dataset_id=body.dataset_id,
        )
    except MappingConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "映射版本冲突，请重新加载后再确认",
                "row_key": exc.row_key,
                "expected_base_version": exc.expected,
                "current_active_version": exc.actual,
            },
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc

    await db.commit()
    return {
        "confirmed": {
            rk: {
                "mapping_version": m.mapping_version,
                "target_count": len(m.targets),
                "confirmed_by": m.confirmed_by,
                "confirmed_at": m.confirmed_at,
            }
            for rk, m in result.items()
        }
    }
