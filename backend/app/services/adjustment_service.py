"""审计调整分录管理服务

覆盖功能：
- CRUD（创建/修改/软删除）
- 复核状态机（draft→pending_review→approved/rejected→draft）
- 借贷平衡校验 + 自动编号
- 科目标准化校验
- 科目下拉（报表行次级联）
- 事件发布（通过 EventBus 触发试算表重算）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    AdjustmentCreate,
    AdjustmentEntryResponse,
    AdjustmentGroupResponse,
    AdjustmentSummary,
    AdjustmentUpdate,
    AccountOption,
    EventPayload,
    EventType,
    ReviewStatusChange,
)
from app.core.audit_decorator import audit_log
from app.services.adjustment_entry_rules import (
    entry_rule_errors,
    next_free_number,
    normalize_adjustment_no,
)
from app.services.event_bus import event_bus
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter


# 合法的状态转换
_VALID_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.draft: {ReviewStatus.pending_review},
    # pending_review → draft 只能走「撤回提交」（allow_withdraw）
    ReviewStatus.pending_review: {ReviewStatus.approved, ReviewStatus.rejected, ReviewStatus.draft},
    # rejected → pending_review = 驳回后不改明细直接重新提交
    ReviewStatus.rejected: {ReviewStatus.draft, ReviewStatus.pending_review},
    ReviewStatus.approved: {ReviewStatus.draft},  # 撤回复核
}


def _locked_hint(status: ReviewStatus) -> str:
    """不可修改 / 删除时的状态说明（中文 + 下一步该做什么）。"""
    return {
        ReviewStatus.pending_review: "「待复核」（请先撤回提交），",
        ReviewStatus.approved: "「已批准」（请先撤回复核），",
    }.get(status, f"「{status.value}」")


class AdjustmentService:
    """审计调整分录管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Event publishing helper
    # ------------------------------------------------------------------
    async def _publish_adjustment_event(
        self,
        event_type: EventType,
        project_id: UUID,
        year: int,
        account_codes: list[str],
        entry_group_id: UUID | None = None,
    ) -> None:
        """发布调整分录相关事件到 EventBus"""
        payload = EventPayload(
            event_type=event_type,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            entry_group_id=entry_group_id,
        )
        await event_bus.publish(payload)

    # ------------------------------------------------------------------
    # 13.1 create_entry
    # ------------------------------------------------------------------
    async def create_entry(
        self,
        project_id: UUID,
        data: AdjustmentCreate,
        user_id: UUID,
        batch_mode: bool = False,
    ) -> AdjustmentGroupResponse:
        """创建调整分录组：行校验→科目校验→编号（自定义或自动）→写入→发布事件"""
        # 1. 行校验（科目必填 / 金额非负 / 不同行双向 / 平衡且非零，规则见 adjustment_entry_rules）
        errors = entry_rule_errors(data.line_items)
        if errors:
            raise ValueError("；".join(errors))

        # 2. 科目标准化校验
        await self._validate_account_codes(
            project_id, [li.standard_account_code for li in data.line_items]
        )

        # 3. 解析主体与审计阶段；不允许无语义的 ``default`` 落库。
        company_code, audit_phase = await self._resolve_group_context(
            project_id, data.year, data.company_code
        )

        # 4. 编号：填了用自定义编号（同年度未删除分录组不得重复），否则自动编号
        custom_no = normalize_adjustment_no(data.adjustment_no)
        if custom_no is not None:
            if custom_no in await self._used_adjustment_nos(project_id, data.year):
                raise ValueError(f"编号「{custom_no}」已被本年度其他调整分录使用")
            adjustment_no = custom_no
        else:
            adjustment_no = await self._next_adjustment_no(
                project_id, data.year, data.adjustment_type
            )

        # 5. 生成 entry_group_id
        entry_group_id = uuid.uuid4()

        # 6. 写入 adjustments 表（每行一条记录，共享 entry_group_id）
        written = await AdjustmentGroupWriter(self.db).write_group(
            project_id=project_id,
            year=data.year,
            company_code=company_code,
            adjustment_no=adjustment_no,
            adjustment_type=data.adjustment_type,
            description=data.description,
            entry_group_id=entry_group_id,
            lines=[AdjustmentGroupLine(
                standard_account_code=line.standard_account_code,
                detail_account_code=line.detail_account_code,
                account_name=line.account_name,
                report_line_code=line.report_line_code,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
            ) for line in data.line_items],
            content_revision=1,
            audit_phase=audit_phase,
            created_by=user_id,
        )
        adj_rows = written.adjustments
        entry_rows = written.entries

        resp = self._build_group_response(
            entry_group_id, adjustment_no, data.adjustment_type,
            data.description, ReviewStatus.draft, adj_rows, entry_rows,
            user_id,
        )

        # batch_mode 时跳过事件发布，由 batch_commit 统一触发
        if not batch_mode:
            affected_codes = list({li.standard_account_code for li in data.line_items})
            await self._publish_adjustment_event(
                EventType.ADJUSTMENT_CREATED,
                project_id, data.year, affected_codes, entry_group_id,
            )

        return resp

    # ------------------------------------------------------------------
    # batch_commit — 批量提交后统一触发一次重算事件
    # ------------------------------------------------------------------
    async def batch_commit(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """批量提交：收集所有 draft 分录涉及的科目，统一发布一次事件触发重算。

        Task 2.5: 发布单条 ADJUSTMENT_BATCH_COMMITTED 事件（非逐条）
        Task 2.6: 使用单事务，任何校验失败整批回滚
        """
        adj = Adjustment.__table__
        q = (
            sa.select(sa.func.array_agg(sa.distinct(adj.c.account_code)))
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        all_codes = result.scalar() or []
        # 过滤 None
        all_codes = [c for c in all_codes if c]

        if all_codes:
            # Task 2.5: 发布单条 ADJUSTMENT_BATCH_COMMITTED 事件
            await self._publish_adjustment_event(
                EventType.ADJUSTMENT_BATCH_COMMITTED,
                project_id, year, all_codes,
            )

        return {
            "message": "批量提交成功，已触发重算",
            "affected_accounts": len(all_codes),
        }

    # ------------------------------------------------------------------
    # 13.2 update_entry / delete_entry
    # ------------------------------------------------------------------
    async def update_entry(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        data: AdjustmentUpdate,
        user_id: UUID,
    ) -> AdjustmentGroupResponse:
        """修改分录（仅 draft/rejected 可改）"""
        adj_rows = await self._get_group_rows(project_id, entry_group_id, for_update=True)
        if not adj_rows:
            raise ValueError("调整分录不存在")
        current_revision = self._group_content_revision(adj_rows)
        if data.expected_revision is not None and data.expected_revision != current_revision:
            raise ValueError(
                f"分录已被其他人更新（当前版本 {current_revision}），请刷新后重试"
            )

        status = adj_rows[0].review_status
        if (adj_rows[0].origin or "manual") == "workpaper":
            raise ValueError("底稿来源分录只能回来源底稿修改后重新同步，不能在调整大厅直接修改")
        if status not in (ReviewStatus.draft, ReviewStatus.rejected):
            raise ValueError(f"当前状态{_locked_hint(status)}不允许修改")

        # 更新描述
        if data.description is not None:
            for row in adj_rows:
                row.description = data.description
                row.updated_by = user_id
        if data.audit_phase is not None:
            for row in adj_rows:
                row.audit_phase = data.audit_phase
                row.updated_by = user_id

        # 更新行项
        if data.line_items is not None:
            errors = entry_rule_errors(data.line_items)
            if errors:
                raise ValueError("；".join(errors))
            await self._validate_account_codes(
                project_id, [li.standard_account_code for li in data.line_items]
            )

            old_entries = await self._get_entry_rows(entry_group_id)
            await AdjustmentGroupWriter(self.db).soft_delete_group(
                adj_rows, old_entries, user_id=user_id,
            )

            # 写入新行
            adj_no = adj_rows[0].adjustment_no
            adj_type = adj_rows[0].adjustment_type
            desc = data.description if data.description is not None else adj_rows[0].description
            new_revision = current_revision + 1
            audit_phase = data.audit_phase or adj_rows[0].audit_phase or "final"
            origin = adj_rows[0].origin or "manual"
            source_ref = adj_rows[0].source_ref
            written = await AdjustmentGroupWriter(self.db).write_group(
                project_id=project_id,
                year=adj_rows[0].year,
                company_code=adj_rows[0].company_code,
                adjustment_no=adj_no,
                adjustment_type=adj_type,
                description=desc,
                entry_group_id=entry_group_id,
                lines=[AdjustmentGroupLine(
                    standard_account_code=line.standard_account_code,
                    detail_account_code=line.detail_account_code,
                    account_name=line.account_name,
                    report_line_code=line.report_line_code,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                ) for line in data.line_items],
                content_revision=new_revision,
                audit_phase=audit_phase,
                review_status=ReviewStatus.draft,
                origin=origin,
                source_ref=source_ref,
                created_by=adj_rows[0].created_by,
                updated_by=user_id,
            )
            new_adj_rows = written.adjustments
            new_entry_rows = written.entries
            resp = self._build_group_response(
                entry_group_id, adj_no, adj_type, desc,
                ReviewStatus.draft, new_adj_rows, new_entry_rows,
                adj_rows[0].created_by,
            )

            # 发布事件（包含旧科目和新科目）
            old_codes = {r.account_code for r in adj_rows}
            new_codes = {li.standard_account_code for li in data.line_items}
            affected_codes = list(old_codes | new_codes)
            await self._publish_adjustment_event(
                EventType.ADJUSTMENT_UPDATED,
                project_id, adj_rows[0].year, affected_codes, entry_group_id,
            )

            # Phase 17: 操作 diff 审计记录
            try:
                from app.models.core import Log
                diff_log = Log(
                    action_type="adjustment_updated",
                    object_type="adjustment",
                    object_id=entry_group_id,
                    new_value={
                        "_diff": {
                            "old_lines": [{"account": r.account_code, "debit": str(r.debit_amount), "credit": str(r.credit_amount)} for r in adj_rows],
                            "new_lines": [{"account": li.standard_account_code, "debit": str(li.debit_amount), "credit": str(li.credit_amount)} for li in data.line_items],
                            "old_description": adj_rows[0].description,
                            "new_description": desc,
                        },
                        "project_id": str(project_id),
                        "year": adj_rows[0].year,
                    },
                    user_id=user_id,
                )
                self.db.add(diff_log)
            except Exception:
                pass  # diff 记录失败不阻断业务

            return resp

        # 摘要也是组内容的一部分；摘要-only 更新同样推进内容修订号。
        if data.description is not None or data.audit_phase is not None:
            next_revision = current_revision + 1
            for row in adj_rows:
                row.content_revision = next_revision
        await self.db.flush()
        entries = await self._get_entry_rows(entry_group_id)
        return self._build_group_response(
            entry_group_id, adj_rows[0].adjustment_no,
            adj_rows[0].adjustment_type, adj_rows[0].description,
            adj_rows[0].review_status, adj_rows, entries,
            adj_rows[0].created_by,
        )

    @audit_log(action="delete", object_type="adjustment")
    async def delete_entry(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        *,
        expected_revision: int | None = None,
        user_id: UUID | None = None,
    ) -> None:
        """软删除分录组（仅 draft/rejected 可删，支持内容版本 CAS）。"""
        adj_rows = await self._get_group_rows(project_id, entry_group_id, for_update=True)
        if not adj_rows:
            raise ValueError("调整分录不存在")
        current_revision = self._group_content_revision(adj_rows)
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError(f"分录已被其他人更新（当前版本 {current_revision}），请刷新后重试")

        status = adj_rows[0].review_status
        if status not in (ReviewStatus.draft, ReviewStatus.rejected):
            raise ValueError(f"当前状态{_locked_hint(status)}不允许删除")

        entry_rows = await self._get_entry_rows(entry_group_id)
        await AdjustmentGroupWriter(self.db).soft_delete_group(
            adj_rows, entry_rows, user_id=user_id,
        )

        # 发布事件
        affected_codes = list({r.account_code for r in adj_rows})
        await self._publish_adjustment_event(
            EventType.ADJUSTMENT_DELETED,
            project_id, adj_rows[0].year, affected_codes, entry_group_id,
        )

    # ------------------------------------------------------------------
    # 13.3 change_review_status
    # ------------------------------------------------------------------
    @audit_log(action="review", object_type="adjustment")
    async def change_review_status(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        change: ReviewStatusChange,
        reviewer_id: UUID,
        *,
        allow_approved_revoke: bool = False,
        allow_withdraw: bool = False,
    ) -> dict[str, Any]:
        """执行调整分录复核状态转换并返回事件与通知所需的影响范围。

        草稿只能提交复核；批准/驳回必须由有效复核任务从 pending_review 进入。
        ``approved`` 只能通过专用 revoke-review 端点回到 draft，pending_review
        只能经「撤回提交」回到 draft。新一轮会清除旧复核信息。
        """
        adj_rows = await self._get_group_rows(project_id, entry_group_id, for_update=True)
        if not adj_rows:
            raise ValueError("调整分录不存在")
        current_revision = self._group_content_revision(adj_rows)
        if change.expected_revision is not None and change.expected_revision != current_revision:
            raise ValueError(f"分录已被其他人更新（当前版本 {current_revision}），请刷新后重试")

        current = adj_rows[0].review_status
        target = change.status

        if target not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"非法状态转换：{current.value} → {target.value}"
            )
        if current == ReviewStatus.approved and target == ReviewStatus.draft and not allow_approved_revoke:
            raise ValueError("已通过的调整须使用撤回复核端点")
        if current == ReviewStatus.pending_review and target == ReviewStatus.draft and not allow_withdraw:
            raise ValueError("待复核的调整须使用撤回提交操作")

        if target == ReviewStatus.rejected and not change.reason:
            raise ValueError("驳回时必须填写原因")

        now = datetime.now(timezone.utc)
        for row in adj_rows:
            row.review_status = target
            row.updated_by = reviewer_id
            if target == ReviewStatus.approved:
                row.reviewer_id = reviewer_id
                row.reviewed_at = now
                row.rejection_reason = None
            elif target == ReviewStatus.rejected:
                row.reviewer_id = reviewer_id
                row.reviewed_at = now
                row.rejection_reason = change.reason
            else:  # draft / pending_review：新一轮，不带上一轮的复核信息
                row.reviewer_id = None
                row.reviewed_at = None
                row.rejection_reason = None

        await self.db.flush()

        # 在 flush 前已加载的 ORM 行上取值（不再查库），供 router 发事件 / 通知
        head = adj_rows[0]
        return {
            "previous_status": current.value,
            "status": target.value,
            "year": head.year,
            "account_codes": sorted({r.account_code for r in adj_rows if r.account_code}),
            "entry_group_id": str(entry_group_id),
            "adjustment_no": head.adjustment_no,
            "origin": head.origin or "manual",
            "created_by": sorted({str(r.created_by) for r in adj_rows if r.created_by}),
        }

    # ------------------------------------------------------------------
    # 13.4 get_summary
    # ------------------------------------------------------------------
    async def get_summary(
        self,
        project_id: UUID,
        year: int,
    ) -> AdjustmentSummary:
        """汇总统计"""
        adj = Adjustment.__table__

        # 按类型汇总
        type_q = (
            sa.select(
                adj.c.adjustment_type,
                sa.func.count(sa.distinct(adj.c.entry_group_id)).label("cnt"),
                sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0).label("total_credit"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
            .group_by(adj.c.adjustment_type)
        )
        result = await self.db.execute(type_q)
        type_map: dict[str, Any] = {}
        for r in result.fetchall():
            type_map[r.adjustment_type] = r

        # 按状态计数（按 entry_group_id 去重）
        status_q = (
            sa.select(
                adj.c.review_status,
                sa.func.count(sa.distinct(adj.c.entry_group_id)).label("cnt"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
            .group_by(adj.c.review_status)
        )
        status_result = await self.db.execute(status_q)
        status_counts = {r.review_status: r.cnt for r in status_result.fetchall()}

        aje = type_map.get(AdjustmentType.aje.value) or type_map.get(AdjustmentType.aje)
        rje = type_map.get(AdjustmentType.rje.value) or type_map.get(AdjustmentType.rje)

        return AdjustmentSummary(
            aje_count=aje.cnt if aje else 0,
            rje_count=rje.cnt if rje else 0,
            aje_total_debit=Decimal(str(aje.total_debit)) if aje else Decimal("0"),
            aje_total_credit=Decimal(str(aje.total_credit)) if aje else Decimal("0"),
            rje_total_debit=Decimal(str(rje.total_debit)) if rje else Decimal("0"),
            rje_total_credit=Decimal(str(rje.total_credit)) if rje else Decimal("0"),
            status_counts=status_counts,
        )

    # ------------------------------------------------------------------
    # 列表查询
    # ------------------------------------------------------------------
    async def list_entries(
        self,
        project_id: UUID,
        year: int,
        adjustment_type: AdjustmentType | None = None,
        review_status: ReviewStatus | None = None,
        origin: str | None = None,
        search: str | None = None,
        account_code: str | None = None,
        amount_min: Decimal | None = None,
        amount_max: Decimal | None = None,
        created_by: UUID | None = None,
        reviewer_id: UUID | None = None,
        audit_phase: str | None = None,
        treatment_status: str | None = None,
        focus_entry_group_id: UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        allowed_account_codes: set[str] | None = None,
        sort_by: str = "adjustment_no",
        sort_order: str = "asc",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """分录列表（按 entry_group_id 分组）"""
        adj = Adjustment.__table__

        # 用 GROUP BY 获取不重复的 entry_group_id
        # 注意：PG 不支持 min(uuid)，UUID 列需要 cast 为 text
        base = (
            sa.select(
                adj.c.entry_group_id,
                sa.func.min(adj.c.adjustment_no).label("adjustment_no"),
                sa.func.min(sa.cast(adj.c.adjustment_type, sa.Text)).label("adjustment_type"),
                sa.func.min(adj.c.description).label("description"),
                sa.func.min(sa.cast(adj.c.review_status, sa.Text)).label("review_status"),
                sa.func.min(sa.cast(adj.c.reviewer_id, sa.Text)).label("reviewer_id"),
                sa.func.min(adj.c.reviewed_at).label("reviewed_at"),
                sa.func.min(adj.c.rejection_reason).label("rejection_reason"),
                sa.func.min(sa.cast(adj.c.created_by, sa.Text)).label("created_by"),
                sa.func.min(adj.c.created_at).label("created_at"),
                sa.func.min(adj.c.audit_phase).label("audit_phase"),
                sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0).label("total_credit"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
            .group_by(adj.c.entry_group_id)
        )

        if adjustment_type is not None:
            base = base.where(adj.c.adjustment_type == adjustment_type)
        if review_status is not None:
            base = base.where(adj.c.review_status == review_status)
        if origin is not None:
            if origin == "manual":
                base = base.where(sa.or_(adj.c.origin.is_(None), adj.c.origin == "manual"))
            else:
                base = base.where(adj.c.origin == origin)
        if allowed_account_codes is not None:
            if not allowed_account_codes:
                return {
                    "items": [], "total": 0, "page": page, "page_size": page_size,
                    "has_more": False, "status_counts": {},
                }
            base = base.where(adj.c.account_code.in_(sorted(allowed_account_codes)))
        if account_code:
            base = base.where(adj.c.account_code == account_code.strip())
        if created_by is not None:
            base = base.where(adj.c.created_by == created_by)
        if reviewer_id is not None:
            base = base.where(adj.c.reviewer_id == reviewer_id)
        if audit_phase in {"preliminary", "final"}:
            base = base.where(adj.c.audit_phase == audit_phase)
        if created_from is not None:
            base = base.where(adj.c.created_at >= created_from)
        if created_to is not None:
            base = base.where(adj.c.created_at <= created_to)
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            base = base.where(sa.or_(
                sa.func.lower(adj.c.adjustment_no).like(term),
                sa.func.lower(sa.func.coalesce(adj.c.description, "")).like(term),
                sa.func.lower(adj.c.account_code).like(term),
                sa.func.lower(sa.func.coalesce(adj.c.account_name, "")).like(term),
            ))
        if treatment_status:
            all_group_ids = list((await self.db.execute(sa.select(sa.distinct(adj.c.entry_group_id)).where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            ))).scalars().all())
            from app.services.adjustment_treatment_service import treatment_projection
            projections = await treatment_projection(
                self.db, project_id=project_id, year=year, group_ids=all_group_ids,
            )
            def _matches_treatment(projection: Any) -> bool:
                if treatment_status == "client_booked":
                    return projection.status == "client_booked" and projection.effective
                if treatment_status == "client_booked_inactive":
                    return projection.status == "client_booked" and not projection.effective
                if treatment_status == "pending":
                    return projection.status in {"pending_internal_review", "awaiting_workpaper_publish"}
                return projection.status == treatment_status

            matching = [
                UUID(group_id) for group_id, projection in projections.items()
                if _matches_treatment(projection)
            ]
            if not matching:
                return {
                    "items": [], "total": 0, "page": page, "page_size": page_size,
                    "has_more": False, "status_counts": {},
                }
            base = base.where(adj.c.entry_group_id.in_(matching))

        # 用子查询做稳定分页
        sub = base.subquery()
        amount_expr = sa.case(
            (sub.c.total_debit >= sub.c.total_credit, sub.c.total_debit),
            else_=sub.c.total_credit,
        )
        filtered = sa.select(sub)
        if amount_min is not None:
            filtered = filtered.where(amount_expr >= amount_min)
        if amount_max is not None:
            filtered = filtered.where(amount_expr <= amount_max)
        filtered_sub = filtered.subquery()
        total = int((await self.db.execute(
            sa.select(sa.func.count()).select_from(filtered_sub)
        )).scalar() or 0)
        status_counts = {
            str(status): int(count)
            for status, count in (await self.db.execute(sa.select(
                filtered_sub.c.review_status, sa.func.count(),
            ).group_by(filtered_sub.c.review_status))).all()
        }
        sort_map = {
            "adjustment_no": filtered_sub.c.adjustment_no,
            "description": filtered_sub.c.description,
            "created_at": filtered_sub.c.created_at,
            "review_status": filtered_sub.c.review_status,
            "amount": sa.case(
                (filtered_sub.c.total_debit >= filtered_sub.c.total_credit, filtered_sub.c.total_debit),
                else_=filtered_sub.c.total_credit,
            ),
        }
        sort_expr = sort_map.get(sort_by, filtered_sub.c.adjustment_no)
        sort_expr = sort_expr.desc() if sort_order.lower() == "desc" else sort_expr.asc()
        stable_order = (sort_expr, sa.cast(filtered_sub.c.entry_group_id, sa.Text).asc())
        if focus_entry_group_id is not None:
            ordered_ids = list((await self.db.execute(
                sa.select(filtered_sub.c.entry_group_id).order_by(*stable_order)
            )).scalars().all())
            target_group_id = focus_entry_group_id
            if target_group_id not in ordered_ids:
                target_group_id = (await self.db.execute(sa.select(
                    AdjustmentEntry.entry_group_id,
                ).where(
                    AdjustmentEntry.id == focus_entry_group_id,
                    AdjustmentEntry.is_deleted == sa.false(),
                ))).scalar_one_or_none() or focus_entry_group_id
            try:
                page = ordered_ids.index(target_group_id) // page_size + 1
            except ValueError:
                pass
        groups_q = (
            sa.select(filtered_sub)
            .order_by(*stable_order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        groups = (await self.db.execute(groups_q)).fetchall()
        group_ids = [g.entry_group_id for g in groups]

        if not group_ids:
            return {
                "items": [], "total": total, "page": page, "page_size": page_size,
                "has_more": False, "status_counts": status_counts,
            }

        # 批量查询所有 Adjustment 行（替代 N 次单独查询，解决 N+1 问题）
        all_adj_q = sa.select(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.entry_group_id.in_(group_ids),
            Adjustment.is_deleted == sa.false(),
        )
        all_adj_result = await self.db.execute(all_adj_q)
        adj_by_group: dict = {}
        for row in all_adj_result.scalars().all():
            adj_by_group.setdefault(row.entry_group_id, []).append(row)

        # 批量查询所有 AdjustmentEntry 行（替代 N 次单独查询）
        all_entry_q = (
            sa.select(AdjustmentEntry)
            .where(
                AdjustmentEntry.entry_group_id.in_(group_ids),
                AdjustmentEntry.is_deleted == sa.false(),
            )
            .order_by(AdjustmentEntry.line_no)
        )
        all_entry_result = await self.db.execute(all_entry_q)
        entry_by_group: dict = {}
        for row in all_entry_result.scalars().all():
            entry_by_group.setdefault(row.entry_group_id, []).append(row)

        items = []
        for g in groups:
            adj_rows = adj_by_group.get(g.entry_group_id, [])
            entries = entry_by_group.get(g.entry_group_id, [])
            items.append(
                self._build_group_response(
                    g.entry_group_id, g.adjustment_no, g.adjustment_type,
                    g.description, g.review_status, adj_rows, entries,
                    g.created_by,
                )
            )

        return {
            "items": [item.model_dump() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
            "status_counts": status_counts,
        }


    # ------------------------------------------------------------------
    # 13.7 get_account_dropdown
    # ------------------------------------------------------------------
    async def get_account_dropdown(
        self,
        project_id: UUID,
        report_line_code: str | None = None,
        year: int | None = None,
    ) -> list[AccountOption]:
        """科目下拉：不传行次 → 全部标准科目（已确认映射的带报表项目，传年度附审定数）；
        传行次 → 该行次下已确认映射的科目。实现见 adjustment_account_options。"""
        from app.services.adjustment_account_options import list_account_options

        return await list_account_options(
            self.db, project_id, report_line_code=report_line_code, year=year,
        )

    async def _resolve_group_context(
        self,
        project_id: UUID,
        year: int,
        requested_company_code: str | None,
    ) -> tuple[str, str]:
        """解析分录主体和创建阶段，拒绝把无语义的 ``default`` 写入账簿。"""
        from app.models.core import Project

        requested = str(requested_company_code or "").strip()
        phase = (
            await self.db.execute(
                sa.select(Project.current_audit_phase).where(Project.id == project_id)
            )
        ).scalar_one_or_none() or "final"
        if requested and requested.lower() != "default":
            return requested, str(phase)

        companies = [
            str(value)
            for value in (
                await self.db.execute(
                    sa.select(sa.distinct(TrialBalance.company_code)).where(
                        TrialBalance.project_id == project_id,
                        TrialBalance.year == year,
                        TrialBalance.is_deleted == sa.false(),
                    )
                )
            ).scalars().all()
            if value
        ]
        if len(companies) == 1:
            return companies[0], str(phase)
        if len(companies) > 1:
            raise ValueError("本项目该年度存在多个主体，请明确选择调整分录所属主体")

        project_company = (
            await self.db.execute(
                sa.select(Project.company_code).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
        return str(project_company or "standalone"), str(phase)

    # ------------------------------------------------------------------
    # 13.8 科目标准化校验（内部方法）
    # ------------------------------------------------------------------
    async def _validate_account_codes(
        self,
        project_id: UUID,
        codes: list[str],
    ) -> None:
        """校验每行 standard_account_code 存在于 account_chart（source=standard）"""
        if not codes:
            return
        ac = AccountChart.__table__
        q = (
            sa.select(ac.c.account_code)
            .where(
                ac.c.project_id == project_id,
                ac.c.source == AccountSource.standard.value,
                ac.c.is_deleted == sa.false(),
                ac.c.account_code.in_(codes),
            )
        )
        result = await self.db.execute(q)
        found = {r.account_code for r in result.fetchall()}
        missing = set(codes) - found
        if missing:
            raise ValueError(
                f"科目编码不存在于标准科目表中: {', '.join(sorted(missing))}"
            )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------
    async def _next_adjustment_no(
        self,
        project_id: UUID,
        year: int,
        adj_type: AdjustmentType,
    ) -> str:
        """生成下一个编号 AJE-001 / RJE-001（使用 pg_advisory_xact_lock 防并发竞争）"""
        import hashlib
        from sqlalchemy import text as sa_text
        prefix = "AJE" if adj_type == AdjustmentType.aje else "RJE"
        # 稳定摘要 —— 跨进程 / 跨重启一致（ADR-P3-005 / ADR-P3-008）
        raw = f"{project_id}:{year}:{prefix}"
        lock_key = int.from_bytes(
            hashlib.sha256(raw.encode("utf-8")).digest()[:4], "big", signed=False,
        ) % (2**31)
        # SQLite 测试 dialect 没有 pg_advisory_xact_lock，跳过（单进程测试隔离即可）
        bind = self.db.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            await self.db.execute(sa_text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        adj = Adjustment.__table__
        q = (
            sa.select(sa.func.count(sa.distinct(adj.c.entry_group_id)))
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.adjustment_type == adj_type,
            )
        )
        result = await self.db.execute(q)
        count = result.scalar() or 0
        # 计数（含已删除组，删除的号不复用）+ 1 起，跳过自定义编号 / 覆盖导入钉入的已占用号
        return next_free_number(prefix, count + 1, await self._used_adjustment_nos(project_id, year))

    async def _used_adjustment_nos(self, project_id: UUID, year: int) -> set[str]:
        """本项目本年度未删除分录组已占用的编号。"""
        adj = Adjustment.__table__
        rows = await self.db.execute(
            sa.select(sa.distinct(adj.c.adjustment_no)).where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
        )
        return {r[0] for r in rows.fetchall() if r[0]}

    async def _get_group_rows(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        *,
        for_update: bool = False,
    ) -> list[Adjustment]:
        """获取同一 entry_group_id 的全部活跃行，可选数据库行锁。"""
        q = (
            sa.select(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.entry_group_id == entry_group_id,
                Adjustment.is_deleted == sa.false(),
            )
        )
        if for_update and self.db.get_bind() is not None and self.db.get_bind().dialect.name == "postgresql":
            q = q.with_for_update()
        result = await self.db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    def _group_content_revision(rows: list[Adjustment]) -> int:
        revisions = {int(row.content_revision or 1) for row in rows}
        if len(revisions) != 1:
            raise ValueError(f"分录组内容版本不一致：{sorted(revisions)}")
        return next(iter(revisions))

    async def _get_entry_rows(
        self,
        entry_group_id: UUID,
    ) -> list[AdjustmentEntry]:
        """获取同一 entry_group_id 的所有未删除明细行"""
        q = (
            sa.select(AdjustmentEntry)
            .where(
                AdjustmentEntry.entry_group_id == entry_group_id,
                AdjustmentEntry.is_deleted == sa.false(),
            )
            .order_by(AdjustmentEntry.line_no)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    def _build_group_response(
        self,
        entry_group_id: UUID,
        adjustment_no: str,
        adjustment_type: AdjustmentType,
        description: str | None,
        review_status: ReviewStatus,
        adj_rows: list[Adjustment],
        entry_rows: list[AdjustmentEntry],
        created_by: UUID | None = None,
    ) -> AdjustmentGroupResponse:
        """构建分录组响应"""
        total_debit = sum(
            (r.debit_amount or Decimal("0")) for r in adj_rows
        )
        total_credit = sum(
            (r.credit_amount or Decimal("0")) for r in adj_rows
        )

        line_items = [
            AdjustmentEntryResponse(
                id=e.id,
                line_no=e.line_no,
                standard_account_code=e.standard_account_code,
                detail_account_code=getattr(e, "detail_account_code", None),
                account_name=e.account_name,
                report_line_code=e.report_line_code,
                debit_amount=e.debit_amount,
                credit_amount=e.credit_amount,
            )
            for e in entry_rows
        ]

        reviewer_id = adj_rows[0].reviewer_id if adj_rows else None
        reviewed_at = adj_rows[0].reviewed_at if adj_rows else None
        rejection_reason = adj_rows[0].rejection_reason if adj_rows else None
        created_at = adj_rows[0].created_at if adj_rows else None
        origin = getattr(adj_rows[0], "origin", None) or "manual" if adj_rows else "manual"
        source_ref = getattr(adj_rows[0], "source_ref", None) if adj_rows else None
        content_revision = int(getattr(adj_rows[0], "content_revision", 1) or 1) if adj_rows else 1
        audit_phase = str(getattr(adj_rows[0], "audit_phase", "final") or "final") if adj_rows else "final"
        external_reference = getattr(adj_rows[0], "external_reference", None) if adj_rows else None
        import_batch_id = getattr(adj_rows[0], "import_batch_id", None) if adj_rows else None

        return AdjustmentGroupResponse(
            entry_group_id=entry_group_id,
            adjustment_no=adjustment_no,
            adjustment_type=adjustment_type,
            description=description,
            review_status=review_status,
            content_revision=content_revision,
            audit_phase=audit_phase,
            external_reference=external_reference,
            import_batch_id=import_batch_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            rejection_reason=rejection_reason,
            total_debit=total_debit,
            total_credit=total_credit,
            line_items=line_items,
            created_by=created_by,
            created_at=created_at,
            origin=origin,
            source_ref=source_ref,
        )
