"""调整分录大厅的站内通知（spec adjustment-hall-entry-review-closure 需求 3.2 / 4.4 / 4.5）。

接收人口径：
- 复核人候选：本项目未删除、启用的成员（``project_users`` 级别 ≥ review）中，合并权限含
  ``adjustment:review`` 的人 —— 逐人调 ``resolve_project_context``，与审批门禁同一口径；
- 编制人：分录组各行 ``created_by``；
- 受影响底稿负责人：科目 → 底稿（``workpapers_for_account_codes``）→ ``working_paper.assigned_to``。
每次操作对每个接收人只发一条；不通知操作人自己。

写入：直接建 ``Notification`` 行，每条在独立 SAVEPOINT 内 flush，失败只记 warning
（一条坏数据不会把主事务弄成 aborted）；与状态变更同一事务由路由 commit。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import notification_types as nt

logger = logging.getLogger(__name__)

#: 一条通知里最多列出的编号 / 底稿编码个数
_MAX_LISTED = 10


def _as_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _listed(values: Sequence[str], unit: str = "笔") -> str:
    shown = [v for v in values if v][:_MAX_LISTED]
    text = "、".join(shown)
    if len(values) > _MAX_LISTED:
        text += f" 等 {len(values)} {unit}"
    return text


def build_metadata(project_id: UUID, year: int | None, items: Sequence[dict], **extra: Any) -> dict:
    """通知 metadata：前端据 project_id + object_id + year 跳到大厅并定位分录。"""
    gids = [str(it["entry_group_id"]) for it in items if it.get("entry_group_id")]
    meta = {
        "project_id": str(project_id),
        "year": year,
        "object_type": "adjustment",
        "object_id": gids[0] if gids else None,
        "entry_group_ids": gids,
        "adjustment_nos": [it.get("adjustment_no") or "" for it in items],
    }
    meta.update(extra)
    return meta


async def write_notifications(
    db: AsyncSession,
    recipient_ids: Iterable[Any],
    notif_type: str,
    title: str,
    content: str,
    metadata: dict,
) -> list[str]:
    """逐个接收人写一条通知（各自 SAVEPOINT），返回写成功的用户 id。"""
    from app.models.core import Notification

    sent: list[str] = []
    object_id = _as_uuid(metadata.get("object_id"))
    for uid in dict.fromkeys(u for u in (_as_uuid(r) for r in recipient_ids) if u):
        try:
            async with db.begin_nested():
                db.add(Notification(
                    recipient_id=uid,
                    message_type=notif_type,
                    title=title[:255],
                    content=content,
                    related_object_type=metadata.get("object_type"),
                    related_object_id=object_id,
                    notification_metadata=metadata,
                    is_read=False,
                ))
                await db.flush()
            sent.append(str(uid))
        except Exception as exc:  # noqa: BLE001 — 通知失败不阻断业务
            logger.warning("[ADJ_HALL] 通知写入失败 type=%s user=%s: %s", notif_type, uid, exc)
    return sent


async def display_names(db: AsyncSession, user_ids: Iterable[Any]) -> dict[str, str]:
    """用户 id → 显示名（人员库姓名优先，没有则用户名）。"""
    from app.models.core import User
    from app.models.staff_models import StaffMember

    ids = [u for u in {_as_uuid(x) for x in user_ids} if u]
    if not ids:
        return {}
    names = {
        str(uid): uname
        for uid, uname in (await db.execute(sa.select(User.id, User.username).where(User.id.in_(ids)))).all()
    }
    for uid, name in (await db.execute(
        sa.select(StaffMember.user_id, StaffMember.name).where(
            StaffMember.user_id.in_(ids), StaffMember.is_deleted == sa.false(),
        )
    )).all():
        if uid and name:
            names[str(uid)] = name
    return names


async def review_candidates(db: AsyncSession, project_id: UUID) -> list[dict]:
    """本项目可复核调整分录的成员（与 ``require_project_permission('adjustment:review')`` 同口径）。"""
    from app.deps import PERMISSION_HIERARCHY
    from app.models.core import ProjectUser, User
    from app.services.project_permissions import resolve_project_context

    members = (await db.execute(
        sa.select(User, ProjectUser.permission_level)
        .join(ProjectUser, ProjectUser.user_id == User.id)
        .where(
            ProjectUser.project_id == project_id,
            ProjectUser.is_deleted == sa.false(),
            User.is_deleted == sa.false(),
            User.is_active == sa.true(),
        )
    )).all()
    names = await display_names(db, [u.id for u, _ in members])
    out: list[dict] = []
    seen: set[str] = set()
    for user, level in members:
        uid = str(user.id)
        level_name = getattr(level, "value", level)
        if uid in seen or PERMISSION_HIERARCHY.get(str(level_name), 0) < PERMISSION_HIERARCHY["review"]:
            continue
        ctx = await resolve_project_context(db, user, project_id)
        if "adjustment:review" not in ctx.permissions:
            continue
        seen.add(uid)
        out.append({
            "user_id": uid,
            "name": names.get(uid) or user.username,
            "project_role": ctx.project_role,
            "system_role": ctx.system_role,
        })
    out.sort(key=lambda r: r["name"])
    return out


def _family(code: str) -> str:
    m = re.match(r"^([A-Z]\d+)", code or "")
    return m.group(1) if m else (code or "")


async def wp_owners_by_code(db: AsyncSession, project_id: UUID, wp_codes: Iterable[str]) -> dict[str, set[UUID]]:
    """底稿编码 → 负责人集合（本项目未删除、有负责人的底稿）。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    codes = sorted({c for c in wp_codes if c})
    if not codes:
        return {}
    rows = (await db.execute(
        sa.select(WpIndex.wp_code, WorkingPaper.assigned_to)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.in_(codes),
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.assigned_to.isnot(None),
        )
    )).all()
    out: dict[str, set[UUID]] = {}
    for code, owner in rows:
        if owner:
            out.setdefault(code, set()).add(owner)
    return out


async def _owners_for_items(
    db: AsyncSession, project_id: UUID, items: Sequence[dict], *, exclude_family: str | None = None,
) -> dict[UUID, tuple[list[str], list[dict]]]:
    """负责人 → (受影响底稿编码, 涉及的分录)。"""
    from app.services.wp_mapping_service import workpapers_for_account_codes

    per_item: list[tuple[dict, list[str]]] = []
    for it in items:
        codes = workpapers_for_account_codes(list(it.get("account_codes") or []), include_parent=True)
        if exclude_family:
            codes = [c for c in codes if _family(c) != _family(exclude_family)]
        per_item.append((it, codes))
    owners = await wp_owners_by_code(db, project_id, (c for _, codes in per_item for c in codes))
    out: dict[UUID, tuple[list[str], list[dict]]] = {}
    for it, codes in per_item:
        for code in codes:
            for owner in owners.get(code, ()):
                wp_list, item_list = out.setdefault(owner, ([], []))
                if code not in wp_list:
                    wp_list.append(code)
                if it not in item_list:
                    item_list.append(it)
    return out


async def notify_status_change(
    db: AsyncSession,
    project_id: UUID,
    items: Sequence[dict],
    *,
    actor_id: UUID,
    actor_name: str,
    reviewer_ids: Sequence[str] | None = None,
    note: str | None = None,
) -> list[dict]:
    """按状态变更发通知，返回 ``[{user_id, name, kind}]``（kind: reviewer / preparer / owner）。

    ``items`` 是 ``AdjustmentService.change_review_status`` 的返回（同一批同一目标状态），
    另可带 ``reason``。规则见模块说明与需求 4.4：
    - → 待复核：所选复核人（未传则全部候选）；
    - 待复核 / 草稿 → 已批准 / 已驳回、已批准 → 草稿（撤回复核）：编制人；
      手工来源的批准 / 撤回复核再通知受影响底稿负责人；
    - 待复核 → 草稿（撤回提交）：不通知。
    """
    if not items:
        return []
    status = items[0]["status"]
    previous = {it.get("previous_status") for it in items}
    year = items[0].get("year")
    actor = str(actor_id)
    notified: list[tuple[str, str]] = []

    if status == "pending_review":
        if reviewer_ids is None:
            reviewer_ids = [c["user_id"] for c in await review_candidates(db, project_id)]
        nos = [it.get("adjustment_no") or "" for it in items]
        title = f"{actor_name} 提交了 {len(items)} 笔调整分录待复核"
        content = f"{_listed(nos)} 待你复核。" + (f"备注：{note}" if note else "")
        sent = await write_notifications(
            db, [r for r in reviewer_ids if str(r) != actor], nt.ADJ_REVIEW_SUBMITTED, title, content,
            build_metadata(project_id, year, items, status=status),
        )
        notified += [(uid, "reviewer") for uid in sent]
    elif status in ("approved", "rejected") or (status == "draft" and previous == {"approved"}):
        kind = {"approved": nt.ADJ_REVIEW_APPROVED, "rejected": nt.ADJ_REVIEW_REJECTED}.get(status, nt.ADJ_REVIEW_REVOKED)
        verb = {"approved": "批准", "rejected": "驳回"}.get(status, "撤回复核")
        by_preparer: dict[str, list[dict]] = {}
        for it in items:
            for uid in it.get("created_by") or []:
                if uid != actor:
                    by_preparer.setdefault(uid, []).append(it)
        for uid, its in by_preparer.items():
            nos = [it.get("adjustment_no") or "" for it in its]
            content = f"{actor_name} {verb}了 {_listed(nos)}。"
            if status == "rejected":
                reasons = "；".join(f"{it.get('adjustment_no')}：{it.get('reason')}" for it in its if it.get("reason"))
                content += f"驳回原因 —— {reasons}。请修改后重新提交。" if reasons else "请修改后重新提交。"
            elif status == "draft":
                content += "分录已回到草稿，试算表审定数随之回退。"
                reasons = "；".join(f"{it.get('adjustment_no')}：{it.get('reason')}" for it in its if it.get("reason"))
                if reasons:
                    content += f"撤回原因 —— {reasons}。"
            elif any((it.get("origin") or "manual") != "workpaper" for it in its):
                content += "已计入试算表审定数。"
            sent = await write_notifications(
                db, [uid], kind, f"你的 {len(its)} 笔调整分录已{verb}", content,
                build_metadata(project_id, year, its, status=status),
            )
            notified += [(u, "preparer") for u in sent]
        if status in ("approved", "draft"):
            manual = [it for it in items if (it.get("origin") or "manual") != "workpaper"]
            done = {u for u, _ in notified} | {actor}
            for owner, (wp_codes, its) in (await _owners_for_items(db, project_id, manual)).items():
                if str(owner) in done:
                    continue
                nos = [it.get("adjustment_no") or "" for it in its]
                codes = _listed(wp_codes, "张")
                sent = await write_notifications(
                    db, [owner], nt.ADJ_APPROVED_IMPACT, f"调整分录已{verb}，涉及你负责的底稿 {codes}",
                    f"{actor_name} {verb}了 {_listed(nos)}，试算表审定数已重算，涉及底稿 {codes}，请刷新审定表并复核结论。",
                    build_metadata(project_id, year, its, status=status, affected_wp_codes=wp_codes),
                )
                notified += [(u, "owner") for u in sent]

    names = await display_names(db, [u for u, _ in notified])
    return [{"user_id": u, "name": names.get(u, ""), "kind": k} for u, k in notified]


async def notify_sync_arrived(
    db: AsyncSession,
    project_id: UUID,
    *,
    source_wp_code: str,
    account_codes: Sequence[str],
    adjustment_no: str,
    sender_user_id: UUID,
    entry_group_id: Any = None,
    year: int | None = None,
) -> int:
    """底稿推送新分录到大厅后，提醒受影响科目对应的其他底稿负责人（不含来源底稿那一族与发送人）。"""
    item = {"entry_group_id": entry_group_id, "adjustment_no": adjustment_no, "account_codes": list(account_codes)}
    source = (source_wp_code or "").upper()
    owners = await _owners_for_items(db, project_id, [item], exclude_family=source or None)
    count = 0
    for owner, (wp_codes, _its) in owners.items():
        if owner == sender_user_id:
            continue
        codes_str = "、".join(sorted(set(wp_codes))[:5])
        meta = build_metadata(project_id, year, [item] if entry_group_id else [], adjustment_no=adjustment_no,
                              affected_wp_codes=sorted(set(wp_codes)), source_wp_code=source)
        count += len(await write_notifications(
            db, [owner], nt.ADJ_SYNC_ARRIVED, f"新调整分录 {adjustment_no} 涉及你负责的底稿",
            f"来自 {source or '未知'} 的调整分录涉及科目属于底稿 {codes_str}，建议在审定表中带入该调整。", meta,
        ))
    return count
