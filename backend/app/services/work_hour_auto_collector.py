"""工时自动采集服务 — 从平台操作轨迹推断工时草稿"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workhour_entry_models import WorkHourEntry


# 可配置常量
FIXED_ACTIVITY_DURATION = Decimal("0.25")  # 复核/抽凭等按次计时长（小时）
SESSION_GAP_MINUTES = 30  # 相邻操作间隔超过此值视为断点
MAX_DAILY_HOURS = Decimal("24")  # 单日上限
OO_SESSION_MAX_HOURS = Decimal("4")  # OnlyOffice 单次会话上限


class WorkHourAutoCollector:
    """平台操作轨迹→工时草稿聚合器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def collect_for_user(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> dict:
        """
        采集指定日期范围的操作轨迹，生成草稿条目。
        返回 {created: int, skipped: int, warnings: list[str]}
        """
        all_activities: list[dict] = []
        warnings: list[str] = []

        # 按优先级从各数据源采集（fail-open）
        for resolver in [
            self._collect_audit_log,
            self._collect_extraction_log,
            self._collect_sampled_vouchers,
            # self._collect_wopi_callback,  # 如 onlyoffice_callback_log 表存在
            self._collect_ai_content_log,
        ]:
            try:
                activities = await resolver(user_id, date_from, date_to)
                all_activities.extend(activities)
            except Exception as e:
                warnings.append(f"{resolver.__name__} failed: {str(e)[:100]}")

        # 按 (project_id, date) 聚合
        aggregated = self._aggregate_by_project_date(all_activities)

        # 幂等 upsert + 计时器优先 + 24h cap
        created = await self._dedup_and_persist(user_id, aggregated, warnings)

        return {"created": created, "skipped": len(aggregated) - created, "warnings": warnings}

    async def _check_timer_priority(
        self, user_id: uuid.UUID, target_date: date, project_id: uuid.UUID, wp_code: Optional[str]
    ) -> bool:
        """检查是否已有 source='timer' 条目"""
        q = sa.select(sa.func.count()).where(
            WorkHourEntry.user_id == user_id,
            WorkHourEntry.date == target_date,
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.source == "timer",
        )
        if wp_code:
            q = q.where(WorkHourEntry.wp_code == wp_code)
        count = (await self.db.execute(q)).scalar() or 0
        return count > 0

    async def _collect_audit_log(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """从 audit_log_entries 采集（主数据源，有 user_id 权威）"""
        from app.models.audit_log_models import AuditLogEntry  # 避免循环导入

        q = (
            sa.select(
                AuditLogEntry.object_type,
                AuditLogEntry.object_id,
                AuditLogEntry.action_type,
                AuditLogEntry.created_at,
                AuditLogEntry.payload,
            )
            .where(
                AuditLogEntry.user_id == user_id,
                sa.func.date(AuditLogEntry.created_at) >= date_from,
                sa.func.date(AuditLogEntry.created_at) <= date_to,
            )
            .order_by(AuditLogEntry.created_at)
        )
        rows = (await self.db.execute(q)).all()

        activities: list[dict] = []
        for row in rows:
            # 从 audit_log 推断项目和活动类型
            activity = {
                "timestamp": row.created_at,
                "action_type": row.action_type,
                "object_type": row.object_type,
                "object_id": str(row.object_id) if row.object_id else None,
                "project_id": self._extract_project_id(row.payload),
                "wp_code": self._extract_wp_code(row.payload),
                "activity_type": self._classify_activity(row.action_type),
            }
            if activity["project_id"]:
                activities.append(activity)

        return activities

    async def _collect_extraction_log(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """从 workpaper_extraction_log 采集抽凭/截止测试"""
        try:
            from app.models.workpaper_models import WorkpaperExtractionLog
        except ImportError:
            return []

        q = (
            sa.select(
                WorkpaperExtractionLog.wp_id,
                WorkpaperExtractionLog.created_at,
            )
            .where(
                WorkpaperExtractionLog.user_id == user_id,
                sa.func.date(WorkpaperExtractionLog.created_at) >= date_from,
                sa.func.date(WorkpaperExtractionLog.created_at) <= date_to,
            )
        )
        try:
            rows = (await self.db.execute(q)).all()
        except Exception:
            return []

        # 批量反查 wp_id → project_id
        wp_ids = list(set(r.wp_id for r in rows if r.wp_id))
        wp_project_map = await self._resolve_projects_from_wp_ids(wp_ids)

        activities: list[dict] = []
        for row in rows:
            project_id = wp_project_map.get(str(row.wp_id)) if row.wp_id else None
            if not project_id:
                continue
            activities.append({
                "timestamp": row.created_at,
                "project_id": project_id,
                "wp_code": None,
                "activity_type": "抽凭",
                "fixed_duration": True,
            })
        return activities

    async def _resolve_projects_from_wp_ids(self, wp_ids: list) -> dict[str, str]:
        """批量从 wp_id 反查 project_id（经 working_paper 表）"""
        if not wp_ids:
            return {}
        try:
            q = sa.text("""
                SELECT wp.id AS wp_id, wp.project_id
                FROM working_paper wp
                WHERE wp.id = ANY(:ids)
            """)
            rows = (await self.db.execute(q, {"ids": wp_ids})).all()
            return {str(r.wp_id): str(r.project_id) for r in rows}
        except Exception:
            return {}

    async def _collect_sampled_vouchers(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """从 sampled_vouchers 采集凭证检查"""
        # sampled_vouchers 可能无 user_id 列，fail-open 返空
        return []

    async def _collect_ai_content_log(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """从 ai_content_log 采集 AI 操作"""
        try:
            q = sa.text("""
                SELECT created_at, project_id
                FROM ai_content_log
                WHERE user_id = :uid
                  AND DATE(created_at) >= :d1
                  AND DATE(created_at) <= :d2
            """)
            rows = (await self.db.execute(q, {"uid": user_id, "d1": date_from, "d2": date_to})).all()
            return [
                {
                    "timestamp": r.created_at,
                    "project_id": str(r.project_id) if r.project_id else None,
                    "wp_code": None,
                    "activity_type": "AI操作",
                    "fixed_duration": True,
                }
                for r in rows
            ]
        except Exception:
            return []

    def _estimate_editing_duration(self, timestamps: list[datetime]) -> Decimal:
        """相邻操作间隔 ≤30min 累加为编制时长"""
        if not timestamps:
            return Decimal("0")
        if len(timestamps) == 1:
            return FIXED_ACTIVITY_DURATION

        sorted_ts = sorted(timestamps)
        total_seconds = 0
        for i in range(1, len(sorted_ts)):
            gap = (sorted_ts[i] - sorted_ts[i - 1]).total_seconds()
            if gap <= SESSION_GAP_MINUTES * 60:
                total_seconds += gap
            # 超过 30min 视为断点，不累加

        hours = Decimal(str(total_seconds)) / Decimal("3600")
        # 至少 0.25h（有操作就计）
        return max(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), FIXED_ACTIVITY_DURATION)

    def _infer_time_slots(self, timestamps: list[datetime]) -> list[dict]:
        """从时间戳推断时段 [{start:'HH:MM', end:'HH:MM'}]"""
        if not timestamps:
            return []

        sorted_ts = sorted(timestamps)
        slots: list[dict] = []
        slot_start = sorted_ts[0]
        last_ts = sorted_ts[0]

        for ts in sorted_ts[1:]:
            gap = (ts - last_ts).total_seconds()
            if gap > SESSION_GAP_MINUTES * 60:
                # 断点：结束当前 slot，开始新 slot
                end_ts = last_ts + timedelta(minutes=15) if slot_start == last_ts else last_ts
                slots.append({
                    "start": slot_start.strftime("%H:%M"),
                    "end": end_ts.strftime("%H:%M"),
                })
                slot_start = ts
            last_ts = ts

        # 最后一个 slot（单时间戳给 15min 宽度）
        end_ts = last_ts + timedelta(minutes=15) if slot_start == last_ts else last_ts
        slots.append({
            "start": slot_start.strftime("%H:%M"),
            "end": end_ts.strftime("%H:%M"),
        })

        return slots

    def _aggregate_by_project_date(self, activities: list[dict]) -> list[dict]:
        """按 (project_id, date) 聚合"""
        groups: dict[tuple, list[dict]] = {}
        for act in activities:
            if not act.get("project_id"):
                continue
            ts = act.get("timestamp")
            if not ts:
                continue
            key = (act["project_id"], ts.date() if isinstance(ts, datetime) else ts)
            groups.setdefault(key, []).append(act)

        aggregated: list[dict] = []
        for (project_id, act_date), acts in groups.items():
            timestamps = [a["timestamp"] for a in acts if a.get("timestamp")]
            fixed_count = sum(1 for a in acts if a.get("fixed_duration"))
            editing_acts = [a for a in acts if not a.get("fixed_duration")]

            # 时长 = 连续编制估算 + 固定活动×单位时长
            editing_hours = self._estimate_editing_duration(
                [a["timestamp"] for a in editing_acts]
            ) if editing_acts else Decimal("0")
            fixed_hours = FIXED_ACTIVITY_DURATION * fixed_count

            total_hours = editing_hours + fixed_hours

            # 推断活动类型（取最频繁的）
            type_counts: dict[str, int] = {}
            for a in acts:
                at = a.get("activity_type", "底稿编制")
                type_counts[at] = type_counts.get(at, 0) + 1
            activity_type = max(type_counts, key=type_counts.get) if type_counts else "底稿编制"

            # 推断 wp_code（取最频繁的）
            wp_counts: dict[str, int] = {}
            for a in acts:
                wc = a.get("wp_code")
                if wc:
                    wp_counts[wc] = wp_counts.get(wc, 0) + 1
            wp_code = max(wp_counts, key=wp_counts.get) if wp_counts else None

            # source_ref 幂等键
            source_ref = f"auto:{project_id}:{act_date}"

            aggregated.append({
                "project_id": project_id,
                "date": act_date,
                "hours": total_hours,
                "activity_type": activity_type,
                "wp_code": wp_code,
                "cycle": (wp_code[0] if wp_code and wp_code[0].isalpha() else "A"),
                "source_ref": source_ref,
                "time_slots": self._infer_time_slots(timestamps),
                "description": f"系统采集：{activity_type}（{len(acts)}次操作）",
            })

        return aggregated

    async def _dedup_and_persist(
        self, user_id: uuid.UUID, aggregated: list[dict], warnings: list[str]
    ) -> int:
        """source_ref 幂等 upsert + 计时器优先 + 24h cap"""
        created = 0

        for draft in aggregated:
            project_id = uuid.UUID(draft["project_id"]) if isinstance(draft["project_id"], str) else draft["project_id"]

            # 计时器优先检查
            if await self._check_timer_priority(user_id, draft["date"], project_id, draft.get("wp_code")):
                continue

            # source_ref 幂等检查
            existing = (await self.db.execute(
                sa.select(WorkHourEntry.id).where(
                    WorkHourEntry.user_id == user_id,
                    WorkHourEntry.source_ref == draft["source_ref"],
                )
            )).scalar_one_or_none()
            if existing:
                continue

            # 24h cap 检查
            daily_total_q = sa.select(sa.func.coalesce(sa.func.sum(WorkHourEntry.hours), 0)).where(
                WorkHourEntry.user_id == user_id,
                WorkHourEntry.date == draft["date"],
            )
            daily_total = Decimal(str((await self.db.execute(daily_total_q)).scalar() or 0))
            remaining = MAX_DAILY_HOURS - daily_total
            if remaining <= 0:
                warnings.append(f"{draft['date']}: 当日已满 24h，跳过采集")
                continue

            hours = min(draft["hours"], remaining)
            if hours < Decimal("0.01"):
                continue

            entry = WorkHourEntry(
                id=uuid.uuid4(),
                user_id=user_id,
                project_id=project_id,
                date=draft["date"],
                hours=hours,
                cycle=draft.get("cycle", "A"),
                wp_code=draft.get("wp_code"),
                description=draft.get("description"),
                status="draft",
                source="auto_collected",
                source_ref=draft["source_ref"],
                activity_type=draft.get("activity_type"),
                time_slots=draft.get("time_slots"),
            )
            self.db.add(entry)
            created += 1

        if created > 0:
            await self.db.flush()

        return created

    # ── helpers ──

    @staticmethod
    def _extract_project_id(payload: dict | None) -> Optional[str]:
        """从 audit_log payload 提取 project_id"""
        if not payload or not isinstance(payload, dict):
            return None
        return payload.get("project_id") or payload.get("projectId")

    @staticmethod
    def _extract_wp_code(payload: dict | None) -> Optional[str]:
        """从 audit_log payload 提取 wp_code"""
        if not payload or not isinstance(payload, dict):
            return None
        return payload.get("wp_code") or payload.get("wpCode")

    @staticmethod
    def _classify_activity(action_type: str | None) -> str:
        """action_type → 活动类型中文"""
        if not action_type:
            return "底稿编制"
        mapping = {
            "checklist_save": "底稿编制",
            "workpaper_save": "底稿编制",
            "review_complete": "复核",
            "adjustment_create": "调整分录",
            "adjustment_approve": "复核",
            "tb_writeback": "底稿编制",
            "note_sync": "附注同步",
            "report_generate": "报告生成",
            "voucher_extract": "抽凭",
            "cutoff_extract": "截止测试",
            "ai_generate": "AI操作",
            "ai_review": "AI操作",
        }
        return mapping.get(action_type, "底稿编制")


# ── WORKPAPER_SAVED 增量 handler（供 event_handlers 调用） ──

async def on_workpaper_saved_increment(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, wp_code: str | None = None):
    """底稿保存时异步写 mini draft（增量 0.25h 或累加既有 auto_collected 条目）。
    
    由 event_handlers/_impl.py 在 WORKPAPER_SAVED 后 best-effort 调用。
    fail-open：异常只 warning 不阻断保存。
    """
    from datetime import date as date_type
    today = date_type.today()
    source_ref = f"increment:{project_id}:{today}"

    # 查是否今天已有该项目的 auto_collected 条目
    existing_q = sa.select(WorkHourEntry).where(
        WorkHourEntry.user_id == user_id,
        WorkHourEntry.project_id == project_id,
        WorkHourEntry.date == today,
        WorkHourEntry.source == "auto_collected",
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()

    if existing:
        # 累加 0.25h（上限 24h 单条不超 8h）
        new_hours = min(existing.hours + FIXED_ACTIVITY_DURATION, Decimal("8"))
        if new_hours != existing.hours:
            existing.hours = new_hours
            existing.description = f"系统采集：底稿编制（增量更新）"
    else:
        # 检查计时器优先
        timer_exists = (await db.execute(
            sa.select(sa.func.count()).where(
                WorkHourEntry.user_id == user_id,
                WorkHourEntry.date == today,
                WorkHourEntry.project_id == project_id,
                WorkHourEntry.source == "timer",
            )
        )).scalar() or 0
        if timer_exists:
            return  # 计时器优先

        # 24h cap
        daily_total = Decimal(str((await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(WorkHourEntry.hours), 0)).where(
                WorkHourEntry.user_id == user_id,
                WorkHourEntry.date == today,
            )
        )).scalar() or 0))
        if daily_total >= Decimal("24"):
            return

        entry = WorkHourEntry(
            id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            date=today,
            hours=FIXED_ACTIVITY_DURATION,
            cycle=(wp_code[0] if wp_code and wp_code[0].isalpha() else "A"),
            wp_code=wp_code,
            description="系统采集：底稿编制（增量）",
            status="draft",
            source="auto_collected",
            source_ref=source_ref,
            activity_type="底稿编制",
        )
        db.add(entry)

    await db.flush()
