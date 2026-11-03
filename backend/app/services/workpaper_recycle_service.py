"""底稿回收站：移入 / 恢复（两层软删）与实质内容判定。

spec procedure-trim-generation-delegation-chain 需求 3 / ADR-4。

底稿 = ``wp_index``（编码、名称、循环）+ 名下 ``working_paper``（文件、内容）。移入回收站把两层都置
``is_deleted``；底稿列表、看板、可见性、委派候选都按 ``wp_index.is_deleted`` 过滤，一处生效全处。
不删文件、不删关联行（复核意见、附件、填写内容都留着），恢复即原样回来。

``uq_wp_index_project_code (project_id, wp_code)`` 与 ``uq_working_paper_project_index
(project_id, wp_index_id)`` 都不含 ``is_deleted`` ⇒ 同码底稿只能复活原行，不能新建；恢复按 wp_index 把
两层一起复活。

每次移入 / 恢复同事务写一条只追加的领域事件 ``workpaper_lifecycle_events``（spec procedure-chain-hardening-and-java-contracts
R18：操作人、原因类别、原因、编码、底稿 id、请求 id）；回收站「删除人」先读最近一条事件，没有（旧数据）再回退去向记录。

去向记录（lineage）写在 ``wp_index.cross_ref_codes["_recycle_lineage"]``（与准则转换的
``_conversion_lineage`` 同一落点），最后一条 ``action == "recycled"`` 的 ``kind`` 标明因何移入：
``trim`` = 程序裁剪，``standard_conversion`` = 准则切换后不适用。粗裁恢复执行只恢复 ``trim`` 的，准则切回
只恢复 ``standard_conversion`` 的，别的原因移入的（手工删除等）都不动。

约定：只 flush 不 commit；移入 / 恢复各递增一次可见性策略纪元（同事务）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.workpaper_lifecycle_models import EVENT_RECYCLED, WorkpaperLifecycleEvent
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpIndex, WpReviewStatus

logger = logging.getLogger(__name__)

RECYCLE_LINEAGE_KEY = "_recycle_lineage"
KIND_TRIM = "trim"
KIND_STANDARD_CONVERSION = "standard_conversion"
ACTION_RECYCLED = "recycled"
ACTION_RESTORED = "restored"

_IN_CHUNK = 500

_FILE_STATUS_LABELS = {
    "edit_complete": "编制完成",
    "under_review": "复核中",
    "revision_required": "退回修改",
    "review_passed": "复核通过",
    "archived": "已归档",
    "review_level1_passed": "一级复核通过",
    "review_level2_passed": "二级复核通过",
}

#: 关联表（无 ORM 模型或只需计数）：(表名, 底稿列, 须非空的列, 软删列, 原因文字模板)
#: ``checklist_responses.updated_by`` 为空 = 公式推送 / 预填写入，不算人工内容。
_RELATED_COUNTS = (
    ("checklist_responses", "wp_id", "updated_by", None, "人工填写 {n} 项"),
    ("attachment_working_paper", "wp_id", None, None, "关联附件 {n} 个"),
    ("review_records", "working_paper_id", None, "is_deleted", "复核意见 {n} 条"),
    ("review_threads", "wp_id", None, None, "复核对话 {n} 个"),
)


@dataclass
class RecycleTarget:
    """一张底稿（wp_index + 名下 working_paper）。``substantive_reasons`` 非空 = 有实质内容。"""

    wp_index_id: UUID
    wp_code: str
    wp_name: str
    working_paper_ids: list[UUID] = field(default_factory=list)
    substantive_reasons: list[str] = field(default_factory=list)

    @property
    def substantive(self) -> bool:
        return bool(self.substantive_reasons)

    def to_dict(self) -> dict:
        return {
            "wp_index_id": str(self.wp_index_id),
            "wp_code": self.wp_code,
            "wp_name": self.wp_name,
            "substantive_reasons": list(self.substantive_reasons),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_lineage(wp_index: WpIndex) -> list[dict]:
    raw = wp_index.cross_ref_codes
    if isinstance(raw, dict):
        items = raw.get(RECYCLE_LINEAGE_KEY)
        return [dict(x) for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    return []


def last_recycle_kind(cross_ref_codes) -> str | None:
    """最后一条去向记录是「移入」时返回其原因类别，否则 ``None``（已恢复 / 从未移入）。"""
    if not isinstance(cross_ref_codes, dict):
        return None
    items = cross_ref_codes.get(RECYCLE_LINEAGE_KEY)
    if not isinstance(items, list) or not items or not isinstance(items[-1], dict):
        return None
    last = items[-1]
    return str(last.get("kind") or "") or None if last.get("action") == ACTION_RECYCLED else None


def last_recycle_actor(cross_ref_codes) -> str | None:
    """最后一条去向记录是「移入」时返回操作人 user_id（回收站「删除人」用），否则 ``None``。"""
    if not isinstance(cross_ref_codes, dict):
        return None
    items = cross_ref_codes.get(RECYCLE_LINEAGE_KEY)
    if not isinstance(items, list) or not items or not isinstance(items[-1], dict):
        return None
    last = items[-1]
    return (str(last.get("actor") or "") or None) if last.get("action") == ACTION_RECYCLED else None


def _append_lineage(wp_index: WpIndex, entry: dict) -> None:
    raw = wp_index.cross_ref_codes
    if isinstance(raw, dict):
        data = dict(raw)
    elif isinstance(raw, list) and raw:
        data = {"codes": list(raw)}  # 旧形态（交叉引用编码列表）原样保留
    else:
        data = {}
    data[RECYCLE_LINEAGE_KEY] = [*read_lineage(wp_index), entry]
    wp_index.cross_ref_codes = data
    flag_modified(wp_index, "cross_ref_codes")


def _is_missing_events_table(exc: BaseException) -> bool:
    """库里还没有事件表：迁移 V207 未落（开发服热重载不跑迁移，重启后才建表）。只认这一种，别的错误照常抛。"""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if getattr(cur, "sqlstate", None) == "42P01" or type(cur).__name__ == "UndefinedTableError":
            return True
        if "no such table" in str(cur) and WorkpaperLifecycleEvent.__tablename__ in str(cur):  # SQLite
            return True
        cur = getattr(cur, "orig", None) or cur.__cause__
    return False


async def _record_events(db: AsyncSession, events: list[WorkpaperLifecycleEvent]) -> None:
    """同事务写事件（调用方已 flush 本次的底稿改动）。事件表还没建时：保存点回滚这一步、记警告，
    移入 / 恢复照常完成（去向记录照写，回收站「删除人」回退去向记录）。"""
    if not events:
        return
    try:
        async with db.begin_nested():
            db.add_all(events)
            await db.flush()
    except SQLAlchemyError as exc:
        if not _is_missing_events_table(exc):
            raise
        logger.warning("[workpaper_recycle] 事件表 %s 不存在（迁移 V207 未执行），本次 %d 条事件未记录",
                       WorkpaperLifecycleEvent.__tablename__, len(events))


def _event(project_id: UUID, index: WpIndex, papers: Sequence[WorkingPaper], *, event_type: str, kind: str,
           reason: str, actor_user_id: UUID | None, request_id: str | None,
           trim_codes: Sequence[str] = ()) -> WorkpaperLifecycleEvent:
    return WorkpaperLifecycleEvent(
        project_id=project_id, wp_index_id=index.id, wp_code=index.wp_code, event_type=event_type,
        kind=kind or "", reason=reason or "", actor_user_id=actor_user_id, request_id=request_id,
        working_paper_ids=[str(wp.id) for wp in papers], trim_codes=list(trim_codes),
        created_at=datetime.now(timezone.utc),
    )


async def latest_recycle_actors(db: AsyncSession, wp_index_ids: Sequence[UUID]) -> dict[UUID, str | None]:
    """按事件取操作人：最近一条事件是「移入」的底稿 ⇒ ``{wp_index_id: actor_user_id}``（无操作人为 ``None``）。
    没有事件（旧数据）或最近一条不是移入的不在结果里 ⇒ 调用方回退去向记录。事件表还没建时返回空。"""
    ids = list(dict.fromkeys(wp_index_ids))
    if not ids:
        return {}
    latest: dict[UUID, tuple[str, UUID | None]] = {}
    try:
        async with db.begin_nested():
            for i in range(0, len(ids), _IN_CHUNK):
                rows = (await db.execute(
                    sa.select(WorkpaperLifecycleEvent.wp_index_id, WorkpaperLifecycleEvent.event_type,
                              WorkpaperLifecycleEvent.actor_user_id)
                    .where(WorkpaperLifecycleEvent.wp_index_id.in_(ids[i:i + _IN_CHUNK]))
                    .order_by(WorkpaperLifecycleEvent.created_at)
                )).all()
                for wp_index_id, event_type, actor in rows:  # 按时间升序，后来的覆盖先来的
                    latest[wp_index_id] = (event_type, actor)
    except SQLAlchemyError as exc:
        if not _is_missing_events_table(exc):
            raise
        return {}
    return {wid: (str(actor) if actor else None)
            for wid, (event_type, actor) in latest.items() if event_type == EVENT_RECYCLED}


async def _count_related(db: AsyncSession, wp_ids: Sequence[UUID]) -> dict[UUID, list[str]]:
    """每张底稿在关联表里的人工内容计数。某张表读取失败 ⇒ 记「无法核对」（按有内容处理，要求确认）。"""
    reasons: dict[UUID, list[str]] = {wid: [] for wid in wp_ids}
    for table_name, column, non_null, deleted_col, template in _RELATED_COUNTS:
        cols = [sa.column(column, sa.Uuid)] + ([sa.column(non_null, sa.Uuid)] if non_null else [])
        cols += [sa.column(deleted_col, sa.Boolean)] if deleted_col else []
        table = sa.table(table_name, *cols)
        key = table.c[column]
        counts: dict[UUID, int] = {}
        try:
            async with db.begin_nested():
                for i in range(0, len(wp_ids), _IN_CHUNK):
                    stmt = sa.select(key, sa.func.count()).where(key.in_(list(wp_ids[i:i + _IN_CHUNK])))
                    if non_null:
                        stmt = stmt.where(table.c[non_null].isnot(None))
                    if deleted_col:
                        stmt = stmt.where(table.c[deleted_col] == sa.false())
                    for wid, n in (await db.execute(stmt.group_by(key))).all():
                        counts[wid] = int(n)
        except SQLAlchemyError as exc:
            logger.warning("回收站实质内容核对失败 table=%s: %s", table_name, exc)
            for wid in wp_ids:
                reasons[wid].append(f"无法核对（{table_name} 读取失败）")
            continue
        for wid, n in counts.items():
            if n > 0 and wid in reasons:
                reasons[wid].append(template.format(n=n))
    return reasons


def _paper_reasons(wp: WorkingPaper) -> list[str]:
    out: list[str] = []
    status = getattr(wp.status, "value", wp.status) or WpFileStatus.draft.value
    if status != WpFileStatus.draft.value:
        out.append(f"编制状态为「{_FILE_STATUS_LABELS.get(status, status)}」")
    review = getattr(wp.review_status, "value", wp.review_status) or WpReviewStatus.not_submitted.value
    if review != WpReviewStatus.not_submitted.value:
        out.append("已提交复核")
    if (wp.content_revision or 0) > 0:
        out.append(f"已保存过 {wp.content_revision} 次")
    if (wp.file_version or 1) > 1:
        out.append(f"文件已有 v{wp.file_version}")
    return out


async def _load_targets(
    db: AsyncSession, project_id: UUID, codes: Iterable[str], *, deleted: bool, lock: bool
) -> list[tuple[WpIndex, list[WorkingPaper]]]:
    wanted = sorted({c for c in codes if c})
    out: list[tuple[WpIndex, list[WorkingPaper]]] = []
    for i in range(0, len(wanted), _IN_CHUNK):
        stmt = sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.in_(wanted[i:i + _IN_CHUNK]),
            WpIndex.is_deleted == (sa.true() if deleted else sa.false()),
        ).order_by(WpIndex.wp_code)
        if lock:
            stmt = stmt.with_for_update()
        indexes = list((await db.execute(stmt)).scalars().all())
        if not indexes:
            continue
        wp_stmt = sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id.in_([x.id for x in indexes]),
            WorkingPaper.is_deleted == (sa.true() if deleted else sa.false()),
        )
        if lock:
            wp_stmt = wp_stmt.with_for_update()
        papers: dict[UUID, list[WorkingPaper]] = {}
        for wp in (await db.execute(wp_stmt)).scalars().all():
            papers.setdefault(wp.wp_index_id, []).append(wp)
        out.extend((x, papers.get(x.id, [])) for x in indexes)
    return out


async def plan_recycle(db: AsyncSession, project_id: UUID, codes: Iterable[str]) -> list[RecycleTarget]:
    """``codes`` 中尚未删除的底稿及其实质内容判定（只读）。"""
    loaded = await _load_targets(db, project_id, codes, deleted=False, lock=False)
    wp_ids = [wp.id for _, papers in loaded for wp in papers]
    related = await _count_related(db, wp_ids) if wp_ids else {}
    targets: list[RecycleTarget] = []
    for index, papers in loaded:
        reasons: list[str] = []
        for wp in papers:
            reasons.extend(_paper_reasons(wp))
            reasons.extend(related.get(wp.id, []))
        targets.append(RecycleTarget(index.id, index.wp_code, index.wp_name, [wp.id for wp in papers],
                                     list(dict.fromkeys(reasons))))
    return targets


async def _bump_epoch(db: AsyncSession, project_id: UUID, action: str, codes: list[str],
                      actor_user_id: UUID | None, request_id: str | None) -> None:
    from app.services.wp_visibility.delegation_transaction import DelegationTransactionService

    await DelegationTransactionService(db).bump_policy_epoch(
        project_id, "permission", request_id=request_id, actor_user_id=actor_user_id,
        detail={"action": action, "wp_codes": codes[:200], "count": len(codes)},
    )


async def move_to_recycle_bin(
    db: AsyncSession,
    project_id: UUID,
    codes: Iterable[str],
    *,
    kind: str,
    reason: str,
    actor_user_id: UUID | None,
    trim_codes: dict[str, list[str]] | None = None,
    request_id: str | None = None,
) -> list[str]:
    """把 ``codes`` 中尚未删除的底稿（两层）移入回收站，返回实际移入的编码。

    ``trim_codes``：编码 → 导致移入的程序行编码（如 ``H3-2`` → ``["H3"]``），写进去向记录。
    """
    loaded = await _load_targets(db, project_id, codes, deleted=False, lock=True)
    now = datetime.now(timezone.utc)
    moved: list[str] = []
    events: list[WorkpaperLifecycleEvent] = []
    for index, papers in loaded:
        for wp in papers:
            wp.is_deleted = True
            wp.updated_at = now
        index.is_deleted = True
        index.updated_at = now
        codes_for_index = list((trim_codes or {}).get(index.wp_code, []))
        _append_lineage(index, {
            "action": ACTION_RECYCLED, "kind": kind, "reason": reason,
            "trim_codes": codes_for_index,
            "working_paper_ids": [str(wp.id) for wp in papers],
            "actor": str(actor_user_id) if actor_user_id else None, "at": _now_iso(),
        })
        events.append(_event(project_id, index, papers, event_type=ACTION_RECYCLED, kind=kind, reason=reason,
                             actor_user_id=actor_user_id, request_id=request_id, trim_codes=codes_for_index))
        moved.append(index.wp_code)
    if moved:
        await db.flush()
        await _record_events(db, events)
        await _bump_epoch(db, project_id, "workpaper_recycled", moved, actor_user_id, request_id)
        await db.flush()
    return moved


async def plan_restore(
    db: AsyncSession, project_id: UUID, codes: Iterable[str], *, kind: str | None = KIND_TRIM
) -> list[str]:
    """``codes`` 中在回收站里、且最后一次因 ``kind`` 移入的底稿编码（``kind=None`` 不限原因）。"""
    loaded = await _load_targets(db, project_id, codes, deleted=True, lock=False)
    return [index.wp_code for index, _ in loaded
            if kind is None or last_recycle_kind(index.cross_ref_codes) == kind]


async def restore_from_recycle_bin(
    db: AsyncSession,
    project_id: UUID,
    codes: Iterable[str],
    *,
    kind: str | None,
    reason: str,
    actor_user_id: UUID | None,
    request_id: str | None = None,
) -> list[str]:
    """恢复 ``codes`` 中在回收站里的底稿（两层一起），返回实际恢复的编码。

    ``kind`` 非空时只恢复最后一次因该原因移入的（粗裁恢复执行只恢复 ``trim``）。
    """
    loaded = await _load_targets(db, project_id, codes, deleted=True, lock=True)
    restored: list[str] = []
    events: list[WorkpaperLifecycleEvent] = []
    now = datetime.now(timezone.utc)
    for index, papers in loaded:
        if kind is not None and last_recycle_kind(index.cross_ref_codes) != kind:
            continue
        index.is_deleted = False
        index.updated_at = now
        for wp in papers:
            wp.is_deleted = False
            wp.updated_at = now
        restored_kind = kind or last_recycle_kind(index.cross_ref_codes) or ""
        _append_lineage(index, {
            "action": ACTION_RESTORED, "kind": restored_kind,
            "reason": reason, "working_paper_ids": [str(wp.id) for wp in papers],
            "actor": str(actor_user_id) if actor_user_id else None, "at": _now_iso(),
        })
        events.append(_event(project_id, index, papers, event_type=ACTION_RESTORED, kind=restored_kind, reason=reason,
                             actor_user_id=actor_user_id, request_id=request_id))
        restored.append(index.wp_code)
    if restored:
        await db.flush()
        await _record_events(db, events)
        await _bump_epoch(db, project_id, "workpaper_restored", restored, actor_user_id, request_id)
        await db.flush()
    return restored
