"""审计调整分录管理服务

覆盖功能：
- CRUD（创建/修改/软删除）
- 复核状态机（draft→pending_review→approved/rejected→draft）
- 借贷平衡校验 + 自动编号
- 科目标准化校验
- 科目下拉（报表行次级联）
- 底稿审定表数据
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
    ReportLineMapping,
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
    WPAdjustmentDetail,
    WPAdjustmentSummary,
)
from app.core.audit_decorator import audit_log
from app.services.event_bus import event_bus


# 合法的状态转换
_VALID_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.draft: {ReviewStatus.pending_review},
    ReviewStatus.pending_review: {ReviewStatus.approved, ReviewStatus.rejected},
    ReviewStatus.rejected: {ReviewStatus.draft},
    ReviewStatus.approved: set(),  # approved 不可转换
}


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
        """创建调整分录组：借贷平衡校验→自动编号→科目校验→写入→发布事件"""
        # 1. 借贷平衡校验
        total_debit = sum(li.debit_amount for li in data.line_items)
        total_credit = sum(li.credit_amount for li in data.line_items)
        if total_debit != total_credit:
            raise ValueError(
                f"借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}，"
                f"差额 {total_debit - total_credit}"
            )

        # 2. 科目标准化校验
        await self._validate_account_codes(
            project_id, [li.standard_account_code for li in data.line_items]
        )

        # 3. 自动编号
        adjustment_no = await self._next_adjustment_no(
            project_id, data.year, data.adjustment_type
        )

        # 4. 生成 entry_group_id
        entry_group_id = uuid.uuid4()

        # 5. 写入 adjustments 表（每行一条记录，共享 entry_group_id）
        adj_rows: list[Adjustment] = []
        entry_rows: list[AdjustmentEntry] = []
        for idx, li in enumerate(data.line_items, start=1):
            adj = Adjustment(
                project_id=project_id,
                year=data.year,
                company_code=data.company_code,
                adjustment_no=adjustment_no,
                adjustment_type=data.adjustment_type,
                description=data.description,
                account_code=li.standard_account_code,
                account_name=li.account_name,
                debit_amount=li.debit_amount,
                credit_amount=li.credit_amount,
                entry_group_id=entry_group_id,
                created_by=user_id,
            )
            self.db.add(adj)
            await self.db.flush()  # get adj.id

            entry = AdjustmentEntry(
                adjustment_id=adj.id,
                entry_group_id=entry_group_id,
                line_no=idx,
                standard_account_code=li.standard_account_code,
                account_name=li.account_name,
                report_line_code=li.report_line_code,
                debit_amount=li.debit_amount,
                credit_amount=li.credit_amount,
            )
            self.db.add(entry)
            adj_rows.append(adj)
            entry_rows.append(entry)

        await self.db.flush()

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
        """批量提交：收集所有 draft 分录涉及的科目，统一发布一次事件触发重算"""
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
            await self._publish_adjustment_event(
                EventType.ADJUSTMENT_CREATED,
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
        adj_rows = await self._get_group_rows(project_id, entry_group_id)
        if not adj_rows:
            raise ValueError("调整分录不存在")

        status = adj_rows[0].review_status
        if status not in (ReviewStatus.draft, ReviewStatus.rejected):
            raise ValueError(f"当前状态 {status.value} 不允许修改")

        # 更新描述
        if data.description is not None:
            for row in adj_rows:
                row.description = data.description
                row.updated_by = user_id

        # 更新行项
        if data.line_items is not None:
            total_debit = sum(li.debit_amount for li in data.line_items)
            total_credit = sum(li.credit_amount for li in data.line_items)
            if total_debit != total_credit:
                raise ValueError(
                    f"借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}"
                )
            await self._validate_account_codes(
                project_id, [li.standard_account_code for li in data.line_items]
            )

            # 软删除旧行
            for row in adj_rows:
                row.soft_delete()
            # 软删除旧 entry 行
            old_entries = await self._get_entry_rows(entry_group_id)
            for e in old_entries:
                e.soft_delete()

            # 写入新行
            adj_no = adj_rows[0].adjustment_no
            adj_type = adj_rows[0].adjustment_type
            desc = data.description if data.description is not None else adj_rows[0].description
            new_adj_rows: list[Adjustment] = []
            new_entry_rows: list[AdjustmentEntry] = []
            for idx, li in enumerate(data.line_items, start=1):
                adj = Adjustment(
                    project_id=project_id,
                    year=adj_rows[0].year,
                    company_code=adj_rows[0].company_code,
                    adjustment_no=adj_no,
                    adjustment_type=adj_type,
                    description=desc,
                    account_code=li.standard_account_code,
                    account_name=li.account_name,
                    debit_amount=li.debit_amount,
                    credit_amount=li.credit_amount,
                    entry_group_id=entry_group_id,
                    review_status=ReviewStatus.draft,
                    created_by=adj_rows[0].created_by,
                    updated_by=user_id,
                )
                self.db.add(adj)
                await self.db.flush()

                entry = AdjustmentEntry(
                    adjustment_id=adj.id,
                    entry_group_id=entry_group_id,
                    line_no=idx,
                    standard_account_code=li.standard_account_code,
                    account_name=li.account_name,
                    report_line_code=li.report_line_code,
                    debit_amount=li.debit_amount,
                    credit_amount=li.credit_amount,
                )
                self.db.add(entry)
                new_adj_rows.append(adj)
                new_entry_rows.append(entry)

            await self.db.flush()
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
                    action="adjustment_updated",
                    resource_type="adjustment",
                    resource_id=str(entry_group_id),
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
                    performed_by=user_id,
                )
                self.db.add(diff_log)
            except Exception:
                pass  # diff 记录失败不阻断业务

            return resp

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
    ) -> None:
        """软删除分录（仅 draft/rejected 可删）"""
        adj_rows = await self._get_group_rows(project_id, entry_group_id)
        if not adj_rows:
            raise ValueError("调整分录不存在")

        status = adj_rows[0].review_status
        if status not in (ReviewStatus.draft, ReviewStatus.rejected):
            raise ValueError(f"当前状态 {status.value} 不允许删除")

        for row in adj_rows:
            row.soft_delete()

        # 软删除 entry 行
        entry_rows = await self._get_entry_rows(entry_group_id)
        for e in entry_rows:
            e.soft_delete()

        await self.db.flush()

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
    ) -> None:
        """复核状态机转换"""
        adj_rows = await self._get_group_rows(project_id, entry_group_id)
        if not adj_rows:
            raise ValueError("调整分录不存在")

        current = adj_rows[0].review_status
        target = change.status

        if target not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"非法状态转换：{current.value} → {target.value}"
            )

        if target == ReviewStatus.rejected and not change.reason:
            raise ValueError("驳回时必须填写原因")

        now = datetime.now(timezone.utc)
        for row in adj_rows:
            row.review_status = target
            if target == ReviewStatus.approved:
                row.reviewer_id = reviewer_id
                row.reviewed_at = now
            elif target == ReviewStatus.rejected:
                row.reviewer_id = reviewer_id
                row.reviewed_at = now
                row.rejection_reason = change.reason
            elif target == ReviewStatus.draft:
                # 从 rejected 回到 draft，清除驳回信息
                row.rejection_reason = None

        await self.db.flush()

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

        # 用子查询做分页
        sub = base.subquery()
        count_q = sa.select(sa.func.count()).select_from(sub)
        total = (await self.db.execute(count_q)).scalar() or 0

        # 获取分页后的 group_ids
        groups_q = (
            sa.select(sub)
            .order_by(sub.c.adjustment_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        groups = (await self.db.execute(groups_q)).fetchall()
        group_ids = [g.entry_group_id for g in groups]

        if not group_ids:
            return {"items": [], "total": total, "page": page, "page_size": page_size}

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
        }


    # ------------------------------------------------------------------
    # 13.7 get_account_dropdown
    # ------------------------------------------------------------------
    async def get_account_dropdown(
        self,
        project_id: UUID,
        report_line_code: str | None = None,
    ) -> list[AccountOption]:
        """
        科目下拉选项：
        - report_line_code=None → 返回所有已映射的标准科目（含 report_line 字段）
        - report_line_code=指定值 → 返回该行次下的标准科目列表
        """
        rlm = ReportLineMapping.__table__
        ac = AccountChart.__table__

        if report_line_code is None:
            # 返回所有已映射且已确认的标准科目，附带报表行次名称
            q = (
                sa.select(
                    rlm.c.standard_account_code,
                    rlm.c.report_line_name,
                    ac.c.account_name,
                    ac.c.level,
                )
                .select_from(
                    rlm.join(
                        ac,
                        sa.and_(
                            ac.c.project_id == rlm.c.project_id,
                            ac.c.account_code == rlm.c.standard_account_code,
                            ac.c.source == AccountSource.standard.value,
                            ac.c.is_deleted == sa.false(),
                        ),
                    )
                )
                .where(
                    rlm.c.project_id == project_id,
                    rlm.c.is_deleted == sa.false(),
                    rlm.c.is_confirmed == sa.true(),
                )
                .distinct()
                .order_by(rlm.c.standard_account_code)
            )
            result = await self.db.execute(q)
            return [
                AccountOption(
                    code=r.standard_account_code,
                    name=r.account_name or "",
                    level=r.level if r.level else 1,
                    report_line=r.report_line_name,
                )
                for r in result.fetchall()
            ]
        else:
            # 返回该行次下的标准科目
            q = (
                sa.select(
                    rlm.c.standard_account_code,
                    rlm.c.report_line_name,
                    ac.c.account_name,
                    ac.c.level,
                )
                .select_from(
                    rlm.join(
                        ac,
                        sa.and_(
                            ac.c.project_id == rlm.c.project_id,
                            ac.c.account_code == rlm.c.standard_account_code,
                            ac.c.source == AccountSource.standard.value,
                            ac.c.is_deleted == sa.false(),
                        ),
                    )
                )
                .where(
                    rlm.c.project_id == project_id,
                    rlm.c.report_line_code == report_line_code,
                    rlm.c.is_deleted == sa.false(),
                    rlm.c.is_confirmed == sa.true(),
                )
                .order_by(rlm.c.standard_account_code)
            )
            result = await self.db.execute(q)
            return [
                AccountOption(
                    code=r.standard_account_code,
                    name=r.account_name or "",
                    level=r.level if r.level else 1,
                    report_line=r.report_line_name,
                )
                for r in result.fetchall()
            ]

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
    # 13.9 get_wp_adjustment_summary
    # ------------------------------------------------------------------
    async def get_wp_adjustment_summary(
        self,
        project_id: UUID,
        year: int,
        wp_code: str,
    ) -> WPAdjustmentSummary:
        """
        底稿审定表数据：
        通过 wp_code 查找关联的标准科目 → 汇总 AJE/RJE 明细 → 返回审定表
        简化实现：wp_code 直接作为 account_category 或 report_line_code 查找
        """
        # 通过 report_line_mapping 查找 wp_code 关联的标准科目
        rlm = ReportLineMapping.__table__
        q = (
            sa.select(rlm.c.standard_account_code)
            .where(
                rlm.c.project_id == project_id,
                rlm.c.report_line_code == wp_code,
                rlm.c.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        account_codes = [r.standard_account_code for r in result.fetchall()]

        if not account_codes:
            return WPAdjustmentSummary(wp_code=wp_code, accounts=account_codes)

        # 获取未审数（从 trial_balance）
        tb = TrialBalance.__table__
        tb_q = (
            sa.select(
                sa.func.coalesce(sa.func.sum(tb.c.unadjusted_amount), 0).label("unadj"),
            )
            .where(
                tb.c.project_id == project_id,
                tb.c.year == year,
                tb.c.standard_account_code.in_(account_codes),
                tb.c.is_deleted == sa.false(),
            )
        )
        tb_result = await self.db.execute(tb_q)
        unadjusted = Decimal(str(tb_result.scalar() or 0))

        # 获取 AJE/RJE 明细
        adj = Adjustment.__table__
        adj_q = (
            sa.select(
                adj.c.entry_group_id,
                adj.c.adjustment_no,
                adj.c.adjustment_type,
                adj.c.description,
                (sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0)
                 - sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0)).label("net"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.account_code.in_(account_codes),
                adj.c.is_deleted == sa.false(),
            )
            .group_by(
                adj.c.entry_group_id,
                adj.c.adjustment_no,
                adj.c.adjustment_type,
                adj.c.description,
            )
        )
        adj_result = await self.db.execute(adj_q)

        aje_details: list[WPAdjustmentDetail] = []
        rje_details: list[WPAdjustmentDetail] = []
        aje_total = Decimal("0")
        rje_total = Decimal("0")

        for r in adj_result.fetchall():
            detail = WPAdjustmentDetail(
                entry_group_id=r.entry_group_id,
                adjustment_no=r.adjustment_no,
                adjustment_type=r.adjustment_type,
                description=r.description,
                amount=Decimal(str(r.net)),
            )
            if r.adjustment_type in (AdjustmentType.aje.value, AdjustmentType.aje):
                aje_details.append(detail)
                aje_total += detail.amount
            else:
                rje_details.append(detail)
                rje_total += detail.amount

        return WPAdjustmentSummary(
            wp_code=wp_code,
            accounts=account_codes,
            unadjusted_amount=unadjusted,
            aje_details=aje_details,
            rje_details=rje_details,
            aje_total=aje_total,
            rje_total=rje_total,
            audited_amount=unadjusted + aje_total + rje_total,
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
        from sqlalchemy import text as sa_text
        prefix = "AJE" if adj_type == AdjustmentType.aje else "RJE"
        # 使用 advisory lock 防止并发竞争产生重复编号
        lock_key = hash(f"{project_id}:{year}:{prefix}") % (2**31)
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
        return f"{prefix}-{count + 1:03d}"

    async def _get_group_rows(
        self,
        project_id: UUID,
        entry_group_id: UUID,
    ) -> list[Adjustment]:
        """获取同一 entry_group_id 的所有未删除行"""
        q = (
            sa.select(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.entry_group_id == entry_group_id,
                Adjustment.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

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

        return AdjustmentGroupResponse(
            entry_group_id=entry_group_id,
            adjustment_no=adjustment_no,
            adjustment_type=adjustment_type,
            description=description,
            review_status=review_status,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            rejection_reason=rejection_reason,
            total_debit=total_debit,
            total_credit=total_credit,
            line_items=line_items,
            created_by=created_by,
            created_at=created_at,
        )
