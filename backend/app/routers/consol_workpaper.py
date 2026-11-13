"""合并薄底稿壳（A3-CONSOL）：负责人 / 复核 / 回收站路由（批 6 / ADR-CRW-006）。

壳本身在 operation 成功、生成 artifact 时由 `ensure_consol_workpaper_shell` 幂等建出；
本路由只做壳的生命周期联动，不碰合并业务数据（业务 JSON 以 consol 专用表为权威，不进 parsed_data）。

鉴权（R11 / 项目级按「谁会用」定级）：
- GET 壳：readonly（任何项目成员可看）。
- 指派负责人 / 移入回收站 / 恢复 / 提交复核：edit（编制类，partner/manager/auditor/assistant）。
- 复核处理（通过 / 退回）：review（质控 / 复核类，含 review 级与以上）。

所有写端点经 `validate_project_boundary(writable=True)`（合并项目 + 年度一致 + 未归档 + 未合并锁定）
与 `check_consol_lock`；service 只 flush，路由统一 commit。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.core import User
from app.services.consol_operation_service import OperationBoundaryError, validate_project_boundary
from app.services.consol_evidence_identity import (
    build_cell_ref,
    note_row_cell_ref,
    report_row_cell_ref,
    trial_row_cell_ref,
    worksheet_row_cell_ref,
)
from app.services.consol_workpaper_shell import (
    ReviewTransitionError,
    ShellNotFound,
    ensure_consol_workpaper_shell,
    get_consol_workpaper_shell,
    recycle_consol_workpaper_shell,
    restore_consol_workpaper_shell,
    review_consol_workpaper,
    set_consol_workpaper_owner,
    set_consol_workpaper_reviewer,
    submit_consol_workpaper_review,
)

router = APIRouter(prefix="/api/consolidation", tags=["合并底稿壳"])


# ─── 请求体 ───────────────────────────────────────────────────────────────


class OwnerBody(BaseModel):
    assigned_to: UUID | None = Field(default=None, description="负责人（编制人）user_id；null 取消指派")


class ReviewerBody(BaseModel):
    reviewer: UUID | None = Field(default=None, description="复核人 user_id；null 取消指派")


class ReviewDecisionBody(BaseModel):
    approved: bool = Field(..., description="true=复核通过；false=退回修改")
    rejection_reason: str | None = Field(default=None, max_length=2000, description="退回原因（退回时必填）")


class EvidenceTargetBody(BaseModel):
    """按稳定身份把合并某 sheet/node/row/col 解析成证据挂载坐标（批 6 / 任务 6.3）。

    返回的 ``wp_id`` + ``sheet_name`` + ``cell_ref`` 直接交给既有
    ``/api/projects/{pid}/workpapers/{wp_id}/evidence`` 上传 / 链接 / 小眼睛端点使用。
    """

    sheet_type: str = Field(..., description="trial / report / note / worksheet（默认 worksheet）")
    node_key: str = Field(..., description="合并表键：sheet_key / consol_trial / consol_report / section_id")
    row_fields: dict[str, Any] | None = Field(
        default=None, description="行的业务标识字段（无稳定 id 时据此派生稳定行身份；不含数组下标）",
    )
    row_identity: str | None = Field(
        default=None, description="显式稳定行 id（如科目码 / 行自带 id）；给定则优先于 row_fields",
    )
    col: str | None = Field(default=None, description="列身份（列键 / 列名；可空=行级证据）")


# ─── 错误映射 ──────────────────────────────────────────────────────────────


def _boundary_error(exc: OperationBoundaryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _shell_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "CONSOL_SHELL_NOT_FOUND", "message": "合并底稿壳尚未创建（先运行一次合并）"},
    )


# ─── 读取 ──────────────────────────────────────────────────────────────────


@router.get("/{project_id}/{year}/workpaper-shell")
async def read_shell(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """读取合并底稿壳（负责人 / 复核状态 / 版本 / 指针）。不含业务 JSON。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=False)
    except OperationBoundaryError as exc:
        raise _boundary_error(exc) from exc
    shell = await get_consol_workpaper_shell(db, project_id)
    if shell is None:
        raise _shell_not_found()
    return shell


@router.post("/{project_id}/{year}/workpaper-shell/evidence-target")
async def resolve_evidence_target(
    project_id: UUID,
    year: int,
    body: EvidenceTargetBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """把合并某 sheet/node/row/col 解析成稳定证据坐标（身份构造是纯函数，不写库）。

    返回 ``{wp_id?, shell_exists, sheet_name, cell_ref, node_key, row_identity, col}``：
    - 身份串 ``cell_ref`` 由业务键派生，插删行不漂移；
    - ``wp_id`` 为薄壳底稿 id（壳未创建时为 null，``shell_exists=false``，前端首次上传前先调
      ``/ensure`` 幂等建壳——那是 edit 级写操作）。

    readonly 用户可据此查看 / 预览既有证据；上传 / 链接仍走证据端点的 edit 门。
    """
    from app.services.consol_evidence_identity import stable_row_identity

    try:
        await validate_project_boundary(db, project_id, year, writable=False)
    except OperationBoundaryError as exc:
        raise _boundary_error(exc) from exc

    kind = (body.sheet_type or "").strip().lower()
    fields = body.row_fields or {}
    col = body.col
    if kind in ("trial", "consol_trial"):
        sheet_name = "consol_trial"
        code = body.row_identity or str(
            fields.get("standard_account_code") or fields.get("account_code") or ""
        ).strip()
        cell_ref = trial_row_cell_ref(code, col=col)
    elif kind in ("report", "consol_report"):
        sheet_name = "consol_report"
        line_key = body.row_identity or str(
            fields.get("line_key") or fields.get("item_code") or fields.get("report_line") or ""
        ).strip()
        cell_ref = report_row_cell_ref(line_key, col=col)
    elif kind in ("note", "consol_note"):
        sheet_name = body.node_key
        cell_ref = (
            build_cell_ref(body.node_key, row_identity="id:" + body.row_identity, col_identity=col)
            if body.row_identity
            else note_row_cell_ref(body.node_key, fields, col=col)
        )
    else:
        sheet_name = body.node_key
        cell_ref = (
            build_cell_ref(body.node_key, row_identity="id:" + body.row_identity, col_identity=col)
            if body.row_identity
            else worksheet_row_cell_ref(body.node_key, fields, col=col)
        )

    shell = await get_consol_workpaper_shell(db, project_id)
    resolved_identity = body.row_identity or (stable_row_identity(fields) if fields else None)
    return {
        "wp_id": shell["working_paper_id"] if shell else None,
        "shell_exists": shell is not None,
        "sheet_name": sheet_name,
        "cell_ref": cell_ref,
        "node_key": body.node_key,
        "row_identity": resolved_identity,
        "col": col,
    }


@router.post("/{project_id}/{year}/workpaper-shell/ensure")
async def ensure_shell(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """幂等创建合并底稿壳（无 artifact 时建占位壳），便于先指派负责人 / 发起复核。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        result = await ensure_consol_workpaper_shell(
            db, project_id, year=year, created_by=getattr(user, "id", None),
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    return result


# ─── 负责人 / 复核人指派（edit） ─────────────────────────────────────────────


@router.put("/{project_id}/{year}/workpaper-shell/owner")
async def assign_owner(
    project_id: UUID,
    year: int,
    body: OwnerBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """指派 / 取消合并底稿壳负责人（编制人）。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        result = await set_consol_workpaper_owner(
            db, project_id, assigned_to=body.assigned_to, actor_user_id=getattr(user, "id", None),
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    except ShellNotFound as exc:
        await db.rollback()
        raise _shell_not_found() from exc
    return result


@router.put("/{project_id}/{year}/workpaper-shell/reviewer")
async def assign_reviewer(
    project_id: UUID,
    year: int,
    body: ReviewerBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """指派 / 取消合并底稿壳复核人。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        result = await set_consol_workpaper_reviewer(
            db, project_id, reviewer=body.reviewer, actor_user_id=getattr(user, "id", None),
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    except ShellNotFound as exc:
        await db.rollback()
        raise _shell_not_found() from exc
    return result


# ─── 复核流转 ──────────────────────────────────────────────────────────────


@router.post("/{project_id}/{year}/workpaper-shell/submit-review")
async def submit_review(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """编制人提交复核（not_submitted / 退回修改 → 待一级复核）。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        result = await submit_consol_workpaper_review(
            db, project_id, actor_user_id=getattr(user, "id", None),
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    except ShellNotFound as exc:
        await db.rollback()
        raise _shell_not_found() from exc
    except ReviewTransitionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail={"code": "REVIEW_TRANSITION_INVALID", "message": str(exc)},
        ) from exc
    return result


@router.post("/{project_id}/{year}/workpaper-shell/review")
async def review_shell(
    project_id: UUID,
    year: int,
    body: ReviewDecisionBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("review")),
    _lock_check=Depends(check_consol_lock),
):
    """复核处理：通过（level1_passed）或退回修改（level1_rejected + 原因）。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        result = await review_consol_workpaper(
            db, project_id, approved=body.approved,
            actor_user_id=getattr(user, "id", None), rejection_reason=body.rejection_reason,
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    except ShellNotFound as exc:
        await db.rollback()
        raise _shell_not_found() from exc
    except ReviewTransitionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail={"code": "REVIEW_TRANSITION_INVALID", "message": str(exc)},
        ) from exc
    return result


# ─── 回收站 ────────────────────────────────────────────────────────────────


@router.post("/{project_id}/{year}/workpaper-shell/recycle")
async def recycle_shell(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
    request_id: str | None = Header(default=None, alias="X-Request-Id"),
):
    """把合并底稿壳（两层）移入回收站（kind=consol）。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        moved = await recycle_consol_workpaper_shell(
            db, project_id, actor_user_id=getattr(user, "id", None), request_id=request_id,
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    return {"recycled": moved}


@router.post("/{project_id}/{year}/workpaper-shell/restore")
async def restore_shell(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
    request_id: str | None = Header(default=None, alias="X-Request-Id"),
):
    """从回收站恢复合并底稿壳（只恢复因 kind=consol 移入的）。"""
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        restored = await restore_consol_workpaper_shell(
            db, project_id, actor_user_id=getattr(user, "id", None), request_id=request_id,
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise _boundary_error(exc) from exc
    return {"restored": restored}


__all__ = ["router"]
