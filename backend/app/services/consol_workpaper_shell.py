"""薄底稿壳：为合并项目幂等创建 A3-CONSOL 的 WpIndex + WorkingPaper（批 6 / ADR-CRW-006）。

业务 JSON 不写 `parsed_data`（合并数据以 `consol_worksheet_data`、`consol_trial`、
`financial_report` 和 `consol_note_data` 为权威）。`file_path` 指向最近 immutable artifact。
壳接入负责人、复核、附件证据、回收站和归档；通用 `EvidenceLink.wp_id` 可直接引用本壳。

`consol_workpaper_instance` 把项目/年度与壳及最近正式 operation/artifact 指针绑定，
version 随 artifact/operation 更新单调递增；本表只做身份与产物指针，不复制业务 JSON。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance
from app.models.core import Project
from app.models.workpaper_models import (
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WorkingPaper,
)

WP_CODE = "A3-CONSOL"
WP_NAME = "合并工作底稿"
AUDIT_CYCLE = "A"
SOURCE_TYPE = WpSourceType.template


class ShellNotFound(Exception):
    """合并底稿壳不存在（调用方应先 ``ensure_consol_workpaper_shell``）。"""


class ReviewTransitionError(Exception):
    """复核状态机不允许的转换（如未提交就通过 / 退回）。"""


async def _resolve_year(db: AsyncSession, project_id: UUID, year: int | None) -> int:
    """年度优先用显式入参，否则取项目审计年度；均缺省回落到 0（保持幂等键稳定）。"""
    if year is not None:
        return year
    resolved = (await db.execute(
        sa.select(Project.audit_year).where(Project.id == project_id)
    )).scalar_one_or_none()
    return int(resolved) if resolved is not None else 0


async def ensure_consol_workpaper_shell(
    db: AsyncSession,
    project_id: UUID,
    *,
    year: int | None = None,
    created_by: UUID | None = None,
    artifact_path: str | None = None,
    operation_id: UUID | None = None,
    artifact_id: UUID | None = None,
) -> dict[str, Any]:
    """幂等创建或更新合并底稿壳 + 实例指针。

    返回 ``{wp_index_id, working_paper_id, instance_id, wp_code, version, created}``。

    - 首次创建 WpIndex + WorkingPaper + ConsolWorkpaperInstance（file_path 指向 artifact 或占位）
    - 再次调用只更新 file_path / operation / artifact 指针，并在指针变化时 version += 1
    - 不写 parsed_data
    """
    now = datetime.now(timezone.utc)
    resolved_year = await _resolve_year(db, project_id, year)

    index = (await db.execute(
        sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == WP_CODE,
            WpIndex.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    created = False
    if index is None:
        index = WpIndex(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_code=WP_CODE,
            wp_name=WP_NAME,
            audit_cycle=AUDIT_CYCLE,
            created_at=now,
            updated_at=now,
        )
        db.add(index)
        await db.flush()
        created = True

    paper = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id == index.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    if paper is None:
        paper = WorkingPaper(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_index_id=index.id,
            file_path=artifact_path or f"consol://{project_id}/placeholder",
            source_type=SOURCE_TYPE,
            status=WpFileStatus.draft,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        db.add(paper)
        await db.flush()
        created = True
    elif artifact_path and paper.file_path != artifact_path:
        paper.file_path = artifact_path
        paper.updated_at = now
        await db.flush()

    instance = (await db.execute(
        sa.select(ConsolWorkpaperInstance).where(
            ConsolWorkpaperInstance.project_id == project_id,
            ConsolWorkpaperInstance.year == resolved_year,
        )
    )).scalar_one_or_none()

    if instance is None:
        instance = ConsolWorkpaperInstance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=resolved_year,
            working_paper_id=paper.id,
            wp_index_id=index.id,
            latest_operation_id=operation_id,
            latest_artifact_id=artifact_id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(instance)
        await db.flush()
        created = True
    else:
        # 指针变化（新 operation / 新 artifact / 换底稿）才 version += 1，保持幂等重调不膨胀
        pointer_changed = (
            (operation_id is not None and instance.latest_operation_id != operation_id)
            or (artifact_id is not None and instance.latest_artifact_id != artifact_id)
            or instance.working_paper_id != paper.id
            or instance.wp_index_id != index.id
        )
        if operation_id is not None:
            instance.latest_operation_id = operation_id
        if artifact_id is not None:
            instance.latest_artifact_id = artifact_id
        instance.working_paper_id = paper.id
        instance.wp_index_id = index.id
        if pointer_changed:
            instance.version += 1
            instance.updated_at = now
            await db.flush()

    # 不变量：薄底稿壳永不把合并业务 JSON 复制进 parsed_data（R8.2 / ADR-CRW-006）。
    # 合并数据以 consol_worksheet_data / consol_trial / financial_report / consol_note_data 为权威，
    # 壳只持有身份、负责人、复核状态与指向 immutable artifact 的 file_path。
    assert paper.parsed_data is None, "合并底稿壳不得写入 parsed_data（业务 JSON 第二真源）"

    return {
        "wp_index_id": str(index.id),
        "working_paper_id": str(paper.id),
        "instance_id": str(instance.id),
        "wp_code": WP_CODE,
        "year": resolved_year,
        "version": instance.version,
        "created": created,
    }


async def get_consol_workpaper_shell(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any] | None:
    """读取已有壳；不存在返回 None。"""
    index = (await db.execute(
        sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == WP_CODE,
            WpIndex.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if index is None:
        return None
    paper = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id == index.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if paper is None:
        return None
    instance = (await db.execute(
        sa.select(ConsolWorkpaperInstance).where(
            ConsolWorkpaperInstance.working_paper_id == paper.id,
        )
    )).scalar_one_or_none()
    return _shell_payload(index, paper, instance)


def _shell_payload(
    index: WpIndex,
    paper: WorkingPaper,
    instance: ConsolWorkpaperInstance | None,
) -> dict[str, Any]:
    """壳的只读投影（负责人 / 复核 / 版本 / 指针）。不含业务 JSON。"""
    return {
        "wp_index_id": str(index.id),
        "working_paper_id": str(paper.id),
        "instance_id": str(instance.id) if instance else None,
        "wp_code": WP_CODE,
        "file_path": paper.file_path,
        "status": str(getattr(paper.status, "value", paper.status)),
        "review_status": str(getattr(paper.review_status, "value", paper.review_status)),
        "assigned_to": str(paper.assigned_to) if paper.assigned_to else None,
        "reviewer": str(paper.reviewer) if paper.reviewer else None,
        "rejection_reason": paper.rejection_reason,
        "is_deleted": bool(paper.is_deleted),
        "year": instance.year if instance else None,
        "version": instance.version if instance else None,
        "latest_operation_id": (
            str(instance.latest_operation_id)
            if instance and instance.latest_operation_id else None
        ),
        "latest_artifact_id": (
            str(instance.latest_artifact_id)
            if instance and instance.latest_artifact_id else None
        ),
    }


async def _load_shell_rows(
    db: AsyncSession, project_id: UUID, *, include_deleted: bool = False
) -> tuple[WpIndex, WorkingPaper, ConsolWorkpaperInstance | None]:
    """取壳的 WpIndex + WorkingPaper + 实例行（可带锁调用方自理）；不存在抛 :class:`ShellNotFound`。

    ``include_deleted=True`` 时连回收站里的一起取（恢复 / 回收站列表用）。
    """
    index_stmt = sa.select(WpIndex).where(
        WpIndex.project_id == project_id,
        WpIndex.wp_code == WP_CODE,
    )
    if not include_deleted:
        index_stmt = index_stmt.where(WpIndex.is_deleted == sa.false())
    index = (await db.execute(index_stmt)).scalar_one_or_none()
    if index is None:
        raise ShellNotFound(f"项目 {project_id} 尚无 {WP_CODE} 合并底稿壳")

    paper_stmt = sa.select(WorkingPaper).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.wp_index_id == index.id,
    )
    if not include_deleted:
        paper_stmt = paper_stmt.where(WorkingPaper.is_deleted == sa.false())
    paper = (await db.execute(paper_stmt)).scalar_one_or_none()
    if paper is None:
        raise ShellNotFound(f"项目 {project_id} 的 {WP_CODE} 壳没有底稿文件行")

    instance = (await db.execute(
        sa.select(ConsolWorkpaperInstance).where(
            ConsolWorkpaperInstance.working_paper_id == paper.id,
        )
    )).scalar_one_or_none()
    return index, paper, instance


async def set_consol_workpaper_owner(
    db: AsyncSession,
    project_id: UUID,
    *,
    assigned_to: UUID | None,
    actor_user_id: UUID | None = None,
) -> dict[str, Any]:
    """设置 / 清空负责人（编制人）。``assigned_to=None`` 取消指派。WpIndex 与 WorkingPaper 两层同步。"""
    index, paper, instance = await _load_shell_rows(db, project_id)
    now = datetime.now(timezone.utc)
    paper.assigned_to = assigned_to
    paper.updated_by = actor_user_id
    paper.updated_at = now
    index.assigned_to = assigned_to
    index.updated_at = now
    await db.flush()
    return _shell_payload(index, paper, instance)


async def set_consol_workpaper_reviewer(
    db: AsyncSession,
    project_id: UUID,
    *,
    reviewer: UUID | None,
    actor_user_id: UUID | None = None,
) -> dict[str, Any]:
    """设置 / 清空复核人。WpIndex 与 WorkingPaper 两层同步。"""
    index, paper, instance = await _load_shell_rows(db, project_id)
    now = datetime.now(timezone.utc)
    paper.reviewer = reviewer
    paper.updated_by = actor_user_id
    paper.updated_at = now
    index.reviewer = reviewer
    index.updated_at = now
    await db.flush()
    return _shell_payload(index, paper, instance)


# 复核状态机（薄壳取单级）：not_submitted → pending_level1 →（pass）level1_passed /（reject）level1_rejected。
# 退回后可重新提交。与通用底稿 WpReviewStatus 语义一致，便于看板 / 复用复核组件。
_REVIEW_SUBMITTABLE = {WpReviewStatus.not_submitted, WpReviewStatus.level1_rejected}


async def submit_consol_workpaper_review(
    db: AsyncSession,
    project_id: UUID,
    *,
    actor_user_id: UUID | None = None,
) -> dict[str, Any]:
    """提交复核：not_submitted / 退回修改 → pending_level1，编制状态置 under_review。"""
    index, paper, instance = await _load_shell_rows(db, project_id)
    current = paper.review_status or WpReviewStatus.not_submitted
    if current not in _REVIEW_SUBMITTABLE:
        raise ReviewTransitionError(
            f"当前复核状态 {getattr(current, 'value', current)} 不允许提交复核"
        )
    now = datetime.now(timezone.utc)
    paper.review_status = WpReviewStatus.pending_level1
    paper.status = WpFileStatus.under_review
    paper.rejection_reason = None
    paper.rejected_by = None
    paper.rejected_at = None
    paper.updated_by = actor_user_id
    paper.updated_at = now
    await db.flush()
    return _shell_payload(index, paper, instance)


async def review_consol_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    approved: bool,
    actor_user_id: UUID | None = None,
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    """复核处理：``approved=True`` → level1_passed + 编制状态 review_passed；
    ``approved=False`` → level1_rejected + 退回修改，并记 rejection_reason / rejected_by / rejected_at。

    只有处于 pending_level1 / level1_in_progress 才能处理。
    """
    index, paper, instance = await _load_shell_rows(db, project_id)
    current = paper.review_status or WpReviewStatus.not_submitted
    if current not in (WpReviewStatus.pending_level1, WpReviewStatus.level1_in_progress):
        raise ReviewTransitionError(
            f"当前复核状态 {getattr(current, 'value', current)} 不允许复核处理（需先提交复核）"
        )
    now = datetime.now(timezone.utc)
    if approved:
        paper.review_status = WpReviewStatus.level1_passed
        paper.status = WpFileStatus.review_passed
        paper.rejection_reason = None
        paper.rejected_by = None
        paper.rejected_at = None
    else:
        if not (rejection_reason or "").strip():
            raise ReviewTransitionError("退回复核必须填写退回原因")
        paper.review_status = WpReviewStatus.level1_rejected
        paper.status = WpFileStatus.revision_required
        paper.rejection_reason = rejection_reason
        paper.rejected_by = actor_user_id
        paper.rejected_at = now
    paper.updated_by = actor_user_id
    paper.updated_at = now
    await db.flush()
    return _shell_payload(index, paper, instance)


async def resolve_consol_evidence_target(
    db: AsyncSession,
    project_id: UUID,
    *,
    year: int | None = None,
    sheet_type: str,
    node_key: str,
    row_fields: dict[str, Any] | None = None,
    row_identity: str | None = None,
    col: str | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    """为合并某 sheet/node/row/col 解析证据挂载目标（批 6 / 任务 6.3）。

    返回 ``{wp_id, sheet_name, cell_ref, node_key, row_identity, col}``：
    - ``wp_id`` = 薄壳 ``working_paper_id``（不存在则先幂等建占位壳，让证据能先挂）；
    - ``sheet_name`` = 合并表键（``consol_trial`` / ``consol_report`` / ``sheet_key`` / ``section_id``）；
    - ``cell_ref`` = 稳定 ``node:.../row:.../col:...`` 身份串（插删行不漂移）。

    前端把这里的 ``wp_id`` + ``sheet_name`` + ``cell_ref`` 原样交给既有
    ``/api/projects/{pid}/workpapers/{wp_id}/evidence`` 的上传 / 链接 / 小眼睛端点，
    不再自己拼接身份、也不复制任何附件逻辑。
    """
    from app.services.consol_evidence_identity import (
        build_cell_ref,
        note_row_cell_ref,
        report_row_cell_ref,
        stable_row_identity,
        trial_row_cell_ref,
        worksheet_row_cell_ref,
    )

    shell = await get_consol_workpaper_shell(db, project_id)
    if shell is None:
        shell = await ensure_consol_workpaper_shell(
            db, project_id, year=year, created_by=created_by,
        )
    wp_id = shell["working_paper_id"]

    kind = (sheet_type or "").strip().lower()
    fields = row_fields or {}
    # 行身份：显式 row_identity 优先；否则按权威源规则从行内容派生（均不含数组下标）
    if kind in ("trial", "consol_trial"):
        sheet_name = "consol_trial"
        code = row_identity or _clean_str(fields.get("standard_account_code") or fields.get("account_code"))
        cell_ref = trial_row_cell_ref(code, col=col)
    elif kind in ("report", "consol_report"):
        sheet_name = "consol_report"
        line_key = row_identity or _clean_str(
            fields.get("line_key") or fields.get("item_code") or fields.get("report_line")
        )
        cell_ref = report_row_cell_ref(line_key, col=col)
    elif kind in ("note", "consol_note"):
        sheet_name = node_key  # section_id
        if row_identity:
            cell_ref = build_cell_ref(node_key, row_identity="id:" + row_identity, col_identity=col)
        else:
            cell_ref = note_row_cell_ref(node_key, fields, col=col)
    else:
        # 默认按工作底稿表处理（sheet_key）
        sheet_name = node_key
        if row_identity:
            cell_ref = build_cell_ref(node_key, row_identity="id:" + row_identity, col_identity=col)
        else:
            cell_ref = worksheet_row_cell_ref(node_key, fields, col=col)

    resolved_identity = row_identity or (stable_row_identity(fields) if fields else None)
    return {
        "wp_id": wp_id,
        "sheet_name": sheet_name,
        "cell_ref": cell_ref,
        "node_key": node_key,
        "row_identity": resolved_identity,
        "col": col,
    }


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


async def recycle_consol_workpaper_shell(
    db: AsyncSession,
    project_id: UUID,
    *,
    reason: str = "合并底稿壳移入回收站",
    actor_user_id: UUID | None = None,
    request_id: str | None = None,
) -> list[str]:
    """把合并底稿壳（两层）移入回收站（``kind=consol``）。返回实际移入的编码（已在回收站则空）。

    走通用 :func:`workpaper_recycle_service.move_to_recycle_bin`：软删两层、写去向记录 + 生命周期事件、
    递增可见性策略纪元。不删文件、不删关联行，恢复即原样回来。
    """
    from app.services.workpaper_recycle_service import KIND_CONSOL, move_to_recycle_bin

    return await move_to_recycle_bin(
        db, project_id, [WP_CODE], kind=KIND_CONSOL, reason=reason,
        actor_user_id=actor_user_id, request_id=request_id,
    )


async def restore_consol_workpaper_shell(
    db: AsyncSession,
    project_id: UUID,
    *,
    reason: str = "合并底稿壳从回收站恢复",
    actor_user_id: UUID | None = None,
    request_id: str | None = None,
) -> list[str]:
    """从回收站恢复合并底稿壳（只恢复最后一次因 ``kind=consol`` 移入的）。返回实际恢复的编码。"""
    from app.services.workpaper_recycle_service import KIND_CONSOL, restore_from_recycle_bin

    return await restore_from_recycle_bin(
        db, project_id, [WP_CODE], kind=KIND_CONSOL, reason=reason,
        actor_user_id=actor_user_id, request_id=request_id,
    )


__all__ = [
    "WP_CODE",
    "WP_NAME",
    "ShellNotFound",
    "ReviewTransitionError",
    "ensure_consol_workpaper_shell",
    "get_consol_workpaper_shell",
    "set_consol_workpaper_owner",
    "set_consol_workpaper_reviewer",
    "submit_consol_workpaper_review",
    "review_consol_workpaper",
    "recycle_consol_workpaper_shell",
    "restore_consol_workpaper_shell",
    "resolve_consol_evidence_target",
]
