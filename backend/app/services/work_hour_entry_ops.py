"""工时条目拆分/合并/跨日操作服务"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.workhour_entry_models import WorkHourEntry


class WorkHourEntryOpsError(Exception):
    """操作错误（400 级别）"""
    pass


class WorkHourEntryOps:
    """工时条目拆分/合并/跨日操作（含状态守卫）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 状态守卫 ──

    def _assert_editable(self, entry: WorkHourEntry) -> None:
        """仅 draft 可操作；submitted/approved 返回错误"""
        if entry.status == "submitted":
            raise WorkHourEntryOpsError("该条目已提交审批，请先退回草稿状态再操作")
        if entry.status == "approved":
            raise WorkHourEntryOpsError("该条目已审批通过，不可修改")
        if entry.status not in ("draft", "rejected"):
            raise WorkHourEntryOpsError(f"该条目状态({entry.status})不允许此操作")

    # ── 拆分 ──

    async def split_entry(
        self, entry_id: uuid.UUID, splits: list[dict], operator_id: uuid.UUID
    ) -> list[WorkHourEntry]:
        """
        将一条拆为多条。
        splits: [{wp_code?, hours, description?, activity_type?}, ...]
        总时长守恒校验 + 原条目软删 + 新建 N 条 + edit_history
        """
        entry = await self._get_entry(entry_id)
        self._assert_editable(entry)

        # 总时长守恒校验
        split_total = sum(Decimal(str(s["hours"])) for s in splits)
        if abs(split_total - entry.hours) > Decimal("0.01"):
            raise WorkHourEntryOpsError(
                f"拆分后总时长({split_total})与原时长({entry.hours})不一致，差额{split_total - entry.hours}"
            )

        if len(splits) < 2:
            raise WorkHourEntryOpsError("拆分至少需要 2 个子条目")

        # 记录 edit_history
        before_snapshot = {
            "id": str(entry.id), "hours": float(entry.hours),
            "wp_code": entry.wp_code, "description": entry.description,
        }

        # 软删原条目
        entry.status = "draft"  # 确保
        entry.hours = Decimal("0")
        entry.description = f"[已拆分] {entry.description or ''}"

        # 新建 N 条
        new_entries = []
        for i, s in enumerate(splits):
            new_entry = WorkHourEntry(
                id=uuid.uuid4(),
                user_id=entry.user_id,
                project_id=entry.project_id,
                date=entry.date,
                hours=Decimal(str(s["hours"])),
                cycle=entry.cycle,
                wp_code=s.get("wp_code") or entry.wp_code,
                procedure=entry.procedure,
                description=s.get("description") or f"拆分自 {entry.description or ''}({i+1}/{len(splits)})",
                status="draft",
                source=entry.source,
                source_ref=f"{entry.source_ref or ''}:split:{i}" if entry.source_ref else None,
                activity_type=s.get("activity_type") or entry.activity_type,
                time_slots=None,
                edit_history=[{
                    "at": datetime.utcnow().isoformat(),
                    "by": str(operator_id),
                    "action": "split_from",
                    "before": before_snapshot,
                    "after": {"hours": float(s["hours"]), "wp_code": s.get("wp_code")},
                }],
            )
            self.db.add(new_entry)
            new_entries.append(new_entry)

        # 原条目也记录 history
        history = list(entry.edit_history or [])
        history.append({
            "at": datetime.utcnow().isoformat(),
            "by": str(operator_id),
            "action": "split_into",
            "before": before_snapshot,
            "after": {"split_count": len(splits), "new_ids": [str(e.id) for e in new_entries]},
        })
        entry.edit_history = history
        flag_modified(entry, 'edit_history')

        await self.db.flush()
        return new_entries

    # ── 合并 ──

    async def merge_entries(
        self, entry_ids: list[uuid.UUID], operator_id: uuid.UUID
    ) -> WorkHourEntry:
        """
        合并同项目同日多条为一条。
        时长相加，描述拼接，取第一条的 wp_code/cycle/activity_type。
        """
        if len(entry_ids) < 2:
            raise WorkHourEntryOpsError("合并至少需要选中 2 条")

        entries = []
        for eid in entry_ids:
            e = await self._get_entry(eid)
            self._assert_editable(e)
            entries.append(e)

        # 校验同项目同日
        projects = set(e.project_id for e in entries)
        dates = set(e.date for e in entries)
        if len(projects) > 1:
            raise WorkHourEntryOpsError("只能合并同一项目的条目")
        if len(dates) > 1:
            raise WorkHourEntryOpsError("只能合并同一天的条目")

        # 合并逻辑
        total_hours = sum(e.hours for e in entries)
        descriptions = [e.description for e in entries if e.description]
        first = entries[0]

        before_snapshot = [
            {"id": str(e.id), "hours": float(e.hours), "description": e.description}
            for e in entries
        ]

        # 新建合并条目
        merged = WorkHourEntry(
            id=uuid.uuid4(),
            user_id=first.user_id,
            project_id=first.project_id,
            date=first.date,
            hours=total_hours,
            cycle=first.cycle,
            wp_code=first.wp_code,
            procedure=first.procedure,
            description="；".join(descriptions) if descriptions else None,
            status="draft",
            source=first.source,
            activity_type=first.activity_type,
            time_slots=None,
            edit_history=[{
                "at": datetime.utcnow().isoformat(),
                "by": str(operator_id),
                "action": "merged_from",
                "before": before_snapshot,
                "after": {"hours": float(total_hours)},
            }],
        )
        self.db.add(merged)

        # 原条目标记已合并（hours→0，保留记录）
        for e in entries:
            history = list(e.edit_history or [])
            history.append({
                "at": datetime.utcnow().isoformat(),
                "by": str(operator_id),
                "action": "merged_into",
                "before": {"hours": float(e.hours)},
                "after": {"merged_id": str(merged.id)},
            })
            e.edit_history = history
            flag_modified(e, 'edit_history')
            e.hours = Decimal("0")
            e.description = f"[已合并] {e.description or ''}"

        await self.db.flush()
        return merged

    # ── 跨日转移 ──

    async def cross_day_transfer(
        self, entry_id: uuid.UUID, target_date: date, transfer_hours: Decimal, operator_id: uuid.UUID
    ) -> tuple[WorkHourEntry, WorkHourEntry]:
        """
        跨日转移部分时长。
        原条目减少，目标日新建/追加。原条目→0h 时保留标记。
        返回 (source_entry, target_entry)
        """
        entry = await self._get_entry(entry_id)
        self._assert_editable(entry)

        if transfer_hours <= 0:
            raise WorkHourEntryOpsError("转移时长必须大于 0")
        if transfer_hours > entry.hours:
            raise WorkHourEntryOpsError(
                f"转移时长({transfer_hours})不能超过原条目时长({entry.hours})"
            )
        if target_date == entry.date:
            raise WorkHourEntryOpsError("目标日期不能与原条目相同")

        before_snapshot = {"hours": float(entry.hours), "date": str(entry.date)}

        # 原条目减少
        entry.hours = entry.hours - transfer_hours
        history = list(entry.edit_history or [])
        history.append({
            "at": datetime.utcnow().isoformat(),
            "by": str(operator_id),
            "action": "cross_day_out",
            "before": before_snapshot,
            "after": {"hours": float(entry.hours), "transferred": float(transfer_hours), "to_date": str(target_date)},
        })
        entry.edit_history = history
        flag_modified(entry, 'edit_history')

        # 目标日新建
        target_entry = WorkHourEntry(
            id=uuid.uuid4(),
            user_id=entry.user_id,
            project_id=entry.project_id,
            date=target_date,
            hours=transfer_hours,
            cycle=entry.cycle,
            wp_code=entry.wp_code,
            procedure=entry.procedure,
            description=entry.description,
            status="draft",
            source=entry.source,
            activity_type=entry.activity_type,
            time_slots=None,
            edit_history=[{
                "at": datetime.utcnow().isoformat(),
                "by": str(operator_id),
                "action": "cross_day_in",
                "before": {"from_date": str(entry.date), "from_id": str(entry.id)},
                "after": {"hours": float(transfer_hours)},
            }],
        )
        self.db.add(target_entry)

        await self.db.flush()
        return entry, target_entry

    # ── helpers ──

    async def _get_entry(self, entry_id: uuid.UUID) -> WorkHourEntry:
        """获取条目，不存在则 404"""
        result = await self.db.execute(
            sa.select(WorkHourEntry).where(WorkHourEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise WorkHourEntryOpsError(f"工时条目不存在: {entry_id}")
        return entry
