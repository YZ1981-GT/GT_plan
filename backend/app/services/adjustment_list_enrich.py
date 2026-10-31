"""调整分录列表富化（spec adjustment-hall-entry-review-closure 需求 3.4 / 5.3）。

给列表项附加：编制人 / 复核人姓名、是否有进行中的协作、来源底稿编码与来源底稿是否已删除。
原实现查不存在的 ``StaffMember.staff_name``（真名 ``name``），异常被吞 ⇒ 编制人、「协作中」标记与对应筛选
从未生效；现在每一段各自兜底（失败记 warning，不吞掉其他段），且来源底稿编码按底稿索引查，不再猜 item_id 前缀。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _as_uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _active_collab_groups(db: AsyncSession, project_id: UUID, group_ids: list[UUID]) -> set[str]:
    from app.models.audit_platform_models import AdjustmentCollaboration
    from app.services.adjustment_collaboration_service import ACTIVE_STATUSES

    if not group_ids:
        return set()
    rows = await db.execute(
        sa.select(AdjustmentCollaboration.entry_group_id).where(
            AdjustmentCollaboration.project_id == project_id,
            AdjustmentCollaboration.entry_group_id.in_(group_ids),
            AdjustmentCollaboration.status.in_(list(ACTIVE_STATUSES)),
            AdjustmentCollaboration.is_deleted == sa.false(),
        )
    )
    return {str(x) for x in rows.scalars().all()}


async def _converted_misstatements(db: AsyncSession, project_id: UUID, group_ids: list[UUID]) -> dict[str, str]:
    """分录组 → 已转出的未更正错报 id（转错报以组内首行为来源，见 misstatement_service）。"""
    from app.models.audit_platform_models import Adjustment, UnadjustedMisstatement

    if not group_ids:
        return {}
    rows = await db.execute(
        sa.select(Adjustment.entry_group_id, UnadjustedMisstatement.id)
        .join(UnadjustedMisstatement, UnadjustedMisstatement.source_adjustment_id == Adjustment.id)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.entry_group_id.in_(group_ids),
            UnadjustedMisstatement.is_deleted == sa.false(),
        )
    )
    out: dict[str, str] = {}
    for gid, mid in rows.all():
        out.setdefault(str(gid), str(mid))
    return out


async def _source_workpapers(db: AsyncSession, wp_ids: list[UUID]) -> dict[str, tuple[str, bool]]:
    """wp_id → (底稿编码, 是否已删除)；查不到的不在结果里（视为来源缺失）。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    if not wp_ids:
        return {}
    rows = await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.is_deleted, WpIndex.wp_code)
        .outerjoin(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id.in_(wp_ids))
    )
    return {str(wid): (code or "", bool(deleted)) for wid, deleted, code in rows.all()}


async def _guarded(db: AsyncSession, label: str, project_id: UUID, query, default):
    """单段富化：各自一个保存点 —— PG 上一条查询出错会让整个事务进入 aborted，不隔离会连带后面几段全失败。"""
    try:
        async with db.begin_nested():
            return await query()
    except Exception as exc:  # noqa: BLE001
        logger.warning("调整分录列表：%s富化失败 project=%s: %s", label, project_id, exc)
        return default


async def enrich_adjustment_list(db: AsyncSession, project_id: UUID, items: list[dict]) -> None:
    from app.services.adjustment_hall_notify import display_names

    group_ids = [g for g in (_as_uuid(it.get("entry_group_id")) for it in items) if g]
    people = [it.get("created_by") for it in items] + [it.get("reviewer_id") for it in items]
    wp_ids: list[UUID] = []
    for it in items:
        ref = it.get("source_ref") or ""
        if it.get("origin") == "workpaper" and ":" in ref:
            wid = _as_uuid(ref.split(":", 1)[0])
            if wid:
                wp_ids.append(wid)

    active = await _guarded(db, "协作状态", project_id, lambda: _active_collab_groups(db, project_id, group_ids), set())
    names = await _guarded(db, "人员姓名", project_id, lambda: display_names(db, people), {})
    converted = await _guarded(db, "已转错报", project_id,
                               lambda: _converted_misstatements(db, project_id, group_ids), {})
    sources = await _guarded(db, "来源底稿", project_id, lambda: _source_workpapers(db, wp_ids), None)
    sources_ok = sources is not None
    sources = sources or {}

    for it in items:
        gid = it.get("entry_group_id")
        it["has_active_collaboration"] = bool(gid and str(gid) in active)
        it["creator_name"] = names.get(str(it.get("created_by"))) if it.get("created_by") else None
        it["reviewer_name"] = names.get(str(it.get("reviewer_id"))) if it.get("reviewer_id") else None
        it["converted_to_misstatement_id"] = converted.get(str(gid)) if gid else None
        if it.get("origin") == "workpaper":
            wid = (it.get("source_ref") or "").split(":", 1)[0]
            code, deleted = sources.get(wid, ("", True))
            it["source_wp_code"] = code
            it["source_missing"] = sources_ok and (wid not in sources or deleted)
