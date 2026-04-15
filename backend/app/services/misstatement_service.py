"""未更正错报汇总管理服务

覆盖功能：
- create_misstatement: 创建未更正错报记录
- create_from_rejected_aje: 从被拒绝AJE预填充创建
- get_summary: 按类型分组汇总 + 与重要性水平对比
- get_cumulative_amount: 累计金额计算
- check_materiality_threshold: 超限预警
- carry_forward: 上年结转
- check_evaluation_completeness: 评价完整性检查

Validates: Requirements 11.1-11.8
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    Materiality,
    MisstatementType,
    UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import (
    MisstatementCategorySummary,
    MisstatementCreate,
    MisstatementResponse,
    MisstatementSummary,
    MisstatementUpdate,
    ThresholdResult,
)


class UnadjustedMisstatementService:
    """未更正错报汇总管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # create_misstatement
    # ------------------------------------------------------------------
    async def create_misstatement(
        self,
        project_id: UUID,
        data: MisstatementCreate,
        created_by: UUID | None = None,
    ) -> MisstatementResponse:
        """创建未更正错报记录"""
        row = UnadjustedMisstatement(
            project_id=project_id,
            year=data.year,
            source_adjustment_id=data.source_adjustment_id,
            misstatement_description=data.misstatement_description,
            affected_account_code=data.affected_account_code,
            affected_account_name=data.affected_account_name,
            misstatement_amount=data.misstatement_amount,
            misstatement_type=data.misstatement_type,
            management_reason=data.management_reason,
            auditor_evaluation=data.auditor_evaluation,
            created_by=created_by,
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_response(row)

    # ------------------------------------------------------------------
    # create_from_rejected_aje
    # ------------------------------------------------------------------
    async def create_from_rejected_aje(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        year: int,
        created_by: UUID | None = None,
    ) -> MisstatementResponse:
        """从被拒绝AJE预填充创建未更正错报"""
        adj = Adjustment.__table__
        q = (
            sa.select(
                adj.c.id,
                adj.c.description,
                adj.c.account_code,
                adj.c.account_name,
                adj.c.debit_amount,
                adj.c.credit_amount,
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.entry_group_id == entry_group_id,
                adj.c.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        rows = result.fetchall()
        if not rows:
            raise ValueError("调整分录不存在")

        # 汇总金额：取净额（借方-贷方的绝对值）
        total_debit = sum(Decimal(str(r.debit_amount or 0)) for r in rows)
        total_credit = sum(Decimal(str(r.credit_amount or 0)) for r in rows)
        net_amount = abs(total_debit - total_credit) if total_debit != total_credit else total_debit

        # 取第一行的描述和科目信息
        first = rows[0]
        description = first.description or "从被拒绝AJE转入"
        # 如果有多行，拼接所有科目
        account_codes = list({r.account_code for r in rows})
        account_names = list({r.account_name for r in rows if r.account_name})

        row = UnadjustedMisstatement(
            project_id=project_id,
            year=year,
            source_adjustment_id=first.id,
            misstatement_description=description,
            affected_account_code=account_codes[0] if len(account_codes) == 1 else ",".join(account_codes),
            affected_account_name=account_names[0] if len(account_names) == 1 else ",".join(account_names),
            misstatement_amount=net_amount,
            misstatement_type=MisstatementType.factual,
            created_by=created_by,
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_response(row)

    # ------------------------------------------------------------------
    # list_misstatements
    # ------------------------------------------------------------------
    async def list_misstatements(
        self,
        project_id: UUID,
        year: int,
    ) -> list[MisstatementResponse]:
        """获取未更正错报列表"""
        q = (
            sa.select(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.year == year,
                UnadjustedMisstatement.is_deleted == sa.false(),
            )
            .order_by(UnadjustedMisstatement.created_at)
        )
        result = await self.db.execute(q)
        return [self._to_response(r) for r in result.scalars().all()]

    # ------------------------------------------------------------------
    # update_misstatement
    # ------------------------------------------------------------------
    async def update_misstatement(
        self,
        project_id: UUID,
        misstatement_id: UUID,
        data: MisstatementUpdate,
    ) -> MisstatementResponse:
        """更新未更正错报"""
        row = await self._get_by_id(project_id, misstatement_id)
        if not row:
            raise ValueError("未更正错报记录不存在")

        if data.misstatement_description is not None:
            row.misstatement_description = data.misstatement_description
        if data.affected_account_code is not None:
            row.affected_account_code = data.affected_account_code
        if data.affected_account_name is not None:
            row.affected_account_name = data.affected_account_name
        if data.misstatement_amount is not None:
            row.misstatement_amount = data.misstatement_amount
        if data.misstatement_type is not None:
            row.misstatement_type = data.misstatement_type
        if data.management_reason is not None:
            row.management_reason = data.management_reason
        if data.auditor_evaluation is not None:
            row.auditor_evaluation = data.auditor_evaluation

        await self.db.flush()
        return self._to_response(row)

    # ------------------------------------------------------------------
    # delete_misstatement (soft delete)
    # ------------------------------------------------------------------
    async def delete_misstatement(
        self,
        project_id: UUID,
        misstatement_id: UUID,
    ) -> None:
        """软删除未更正错报"""
        row = await self._get_by_id(project_id, misstatement_id)
        if not row:
            raise ValueError("未更正错报记录不存在")
        row.soft_delete()
        await self.db.flush()
    # ------------------------------------------------------------------
    # get_summary
    # ------------------------------------------------------------------
    async def get_summary(
        self,
        project_id: UUID,
        year: int,
    ) -> MisstatementSummary:
        """按类型分组汇总 + 与重要性水平对比"""
        tbl = UnadjustedMisstatement.__table__

        # 按类型分组汇总
        agg_q = (
            sa.select(
                tbl.c.misstatement_type,
                sa.func.count().label("cnt"),
                sa.func.coalesce(sa.func.sum(tbl.c.misstatement_amount), 0).label("total"),
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
            )
            .group_by(tbl.c.misstatement_type)
        )
        result = await self.db.execute(agg_q)

        by_type: list[MisstatementCategorySummary] = []
        cumulative = Decimal("0")
        for r in result.fetchall():
            amount = Decimal(str(r.total))
            by_type.append(MisstatementCategorySummary(
                misstatement_type=r.misstatement_type,
                count=r.cnt,
                total_amount=amount,
            ))
            cumulative += amount

        # 获取重要性水平
        mat = await self._get_materiality(project_id, year)
        overall_mat = mat.overall_materiality if mat else None
        perf_mat = mat.performance_materiality if mat else None
        trivial = mat.trivial_threshold if mat else None

        exceeds = False
        if overall_mat is not None:
            exceeds = cumulative >= overall_mat

        # 评价完整性检查
        eval_complete = await self.check_evaluation_completeness(project_id, year)

        return MisstatementSummary(
            by_type=by_type,
            cumulative_amount=cumulative,
            overall_materiality=overall_mat,
            performance_materiality=perf_mat,
            trivial_threshold=trivial,
            exceeds_materiality=exceeds,
            evaluation_complete=eval_complete,
        )

    # ------------------------------------------------------------------
    # get_cumulative_amount
    # ------------------------------------------------------------------
    async def get_cumulative_amount(
        self,
        project_id: UUID,
        year: int,
    ) -> Decimal:
        """累计金额计算"""
        tbl = UnadjustedMisstatement.__table__
        q = (
            sa.select(
                sa.func.coalesce(sa.func.sum(tbl.c.misstatement_amount), 0).label("total")
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        return Decimal(str(result.scalar_one()))

    # ------------------------------------------------------------------
    # check_materiality_threshold
    # ------------------------------------------------------------------
    async def check_materiality_threshold(
        self,
        project_id: UUID,
        year: int,
    ) -> ThresholdResult:
        """超限预警：累计金额 vs 整体重要性水平"""
        cumulative = await self.get_cumulative_amount(project_id, year)
        mat = await self._get_materiality(project_id, year)

        if mat is None:
            return ThresholdResult(
                cumulative_amount=cumulative,
                overall_materiality=Decimal("0"),
                exceeds=False,
                warning_message="尚未设置重要性水平",
            )

        overall = mat.overall_materiality
        exceeds = cumulative >= overall
        warning = None
        if exceeds:
            warning = (
                f"未更正错报累计金额({cumulative})已达到或超过"
                f"整体重要性水平({overall})，"
                f"可能需要出具保留意见或否定意见"
            )

        return ThresholdResult(
            cumulative_amount=cumulative,
            overall_materiality=overall,
            exceeds=exceeds,
            warning_message=warning,
        )

    # ------------------------------------------------------------------
    # carry_forward
    # ------------------------------------------------------------------
    async def carry_forward(
        self,
        project_id: UUID,
        prior_project_id: UUID,
        prior_year: int,
        target_year: int,
        created_by: UUID | None = None,
    ) -> int:
        """上年结转：复制上年未更正错报到本年"""
        q = (
            sa.select(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == prior_project_id,
                UnadjustedMisstatement.year == prior_year,
                UnadjustedMisstatement.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(q)
        prior_rows = result.scalars().all()

        count = 0
        for prior in prior_rows:
            new_row = UnadjustedMisstatement(
                project_id=project_id,
                year=target_year,
                source_adjustment_id=None,
                misstatement_description=prior.misstatement_description,
                affected_account_code=prior.affected_account_code,
                affected_account_name=prior.affected_account_name,
                misstatement_amount=prior.misstatement_amount,
                misstatement_type=prior.misstatement_type,
                management_reason=prior.management_reason,
                auditor_evaluation=prior.auditor_evaluation,
                is_carried_forward=True,
                prior_year_id=prior.id,
                created_by=created_by,
            )
            self.db.add(new_row)
            count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # check_evaluation_completeness
    # ------------------------------------------------------------------
    async def check_evaluation_completeness(
        self,
        project_id: UUID,
        year: int,
    ) -> bool:
        """评价完整性检查：所有记录的 management_reason 和 auditor_evaluation 非空"""
        tbl = UnadjustedMisstatement.__table__
        q = (
            sa.select(sa.func.count())
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
                sa.or_(
                    tbl.c.management_reason.is_(None),
                    tbl.c.management_reason == "",
                    tbl.c.auditor_evaluation.is_(None),
                    tbl.c.auditor_evaluation == "",
                ),
            )
        )
        result = await self.db.execute(q)
        incomplete_count = result.scalar_one()
        return incomplete_count == 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get_by_id(
        self,
        project_id: UUID,
        misstatement_id: UUID,
    ) -> UnadjustedMisstatement | None:
        q = sa.select(UnadjustedMisstatement).where(
            UnadjustedMisstatement.id == misstatement_id,
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.is_deleted == sa.false(),
        )
        result = await self.db.execute(q)
        return result.scalar_one_or_none()

    async def _get_materiality(
        self,
        project_id: UUID,
        year: int,
    ) -> Materiality | None:
        q = sa.select(Materiality).where(
            Materiality.project_id == project_id,
            Materiality.year == year,
            Materiality.is_deleted == sa.false(),
        )
        result = await self.db.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    def _to_response(row: UnadjustedMisstatement) -> MisstatementResponse:
        return MisstatementResponse(
            id=row.id,
            project_id=row.project_id,
            year=row.year,
            source_adjustment_id=row.source_adjustment_id,
            misstatement_description=row.misstatement_description,
            affected_account_code=row.affected_account_code,
            affected_account_name=row.affected_account_name,
            misstatement_amount=row.misstatement_amount,
            misstatement_type=row.misstatement_type,
            management_reason=row.management_reason,
            auditor_evaluation=row.auditor_evaluation,
            is_carried_forward=row.is_carried_forward,
            prior_year_id=row.prior_year_id,
            created_by=row.created_by,
            created_at=row.created_at,
        )
