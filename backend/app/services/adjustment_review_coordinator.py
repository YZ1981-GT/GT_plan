"""调整分录复核协调器。

手工 AJE/RJE 的“已批准”与试算表调整列、审定数和耐久下游事件在同一事务
成立。底稿来源批准只完成集中复核，不重复写 AJE/RJE；来源底稿发布门另行校验。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    Adjustment,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import EventPayload, EventType, ReviewStatusChange
from app.services import adjustment_review_task_service as review_tasks
from app.services.adjustment_service import AdjustmentService
from app.services.trial_balance_service import TrialBalanceService
from app.services.workpaper_sync.outbox import DurableEventOutboxService, PendingPublication


@dataclass(frozen=True)
class AdjustmentDecisionResult:
    info: dict[str, Any]
    tb_updated: bool
    account_codes: tuple[str, ...]
    publications: tuple[PendingPublication, ...] = ()


class AdjustmentReviewCoordinator:
    """拥有一笔复核决策的锁、状态、TB 与 outbox 事务边界。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.adjustments = AdjustmentService(db)

    async def ensure_tb_rows(
        self,
        *,
        project_id: UUID,
        year: int,
        company_code: str,
        account_codes: list[str],
    ) -> None:
        """为标准科目补零未审数 TB 行，避免批准后金额静默丢失。"""
        wanted = sorted({code for code in account_codes if code})
        existing = set((await self.db.execute(
            sa.select(TrialBalance.standard_account_code).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == company_code,
                TrialBalance.standard_account_code.in_(wanted),
                TrialBalance.is_deleted == sa.false(),
            )
        )).scalars().all())
        missing = [code for code in wanted if code not in existing]
        if not missing:
            return
        chart_rows = (await self.db.execute(
            sa.select(AccountChart).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code.in_(missing),
                AccountChart.source == AccountSource.standard,
                AccountChart.is_deleted == sa.false(),
            )
        )).scalars().all()
        chart = {row.account_code: row for row in chart_rows}
        unresolved = [code for code in missing if code not in chart]
        if unresolved:
            raise ValueError(f"以下调整科目无法建立试算表行：{'、'.join(unresolved)}")
        for code in missing:
            account = chart[code]
            self.db.add(TrialBalance(
                project_id=project_id,
                year=year,
                company_code=company_code,
                standard_account_code=code,
                account_name=account.account_name,
                account_category=account.category,
                unadjusted_amount=Decimal("0"),
                rje_adjustment=Decimal("0"),
                aje_adjustment=Decimal("0"),
                wp_adjustment=Decimal("0"),
                audited_amount=Decimal("0"),
            ))
        await self.db.flush()

    async def decide(
        self,
        *,
        project_id: UUID,
        entry_group_id: UUID,
        status: ReviewStatus,
        actor: Any,
        reason: str | None = None,
    ) -> AdjustmentDecisionResult:
        if status not in (ReviewStatus.approved, ReviewStatus.rejected):
            raise ValueError("复核决策只能批准或驳回")
        rows = await self.adjustments._get_group_rows(
            project_id, entry_group_id, for_update=True,
        )
        task = await review_tasks.require_decidable_task(
            self.db, project_id=project_id, rows=rows, actor=actor,
        )
        if rows[0].review_status != ReviewStatus.pending_review:
            raise ValueError("只有待复核的分录可以批准或驳回")

        from app.services.adjustment_risk_projection import project_adjustment_risk
        risk = await project_adjustment_risk(
            self.db, project_id=project_id, year=int(rows[0].year), rows=rows,
        )
        if status == ReviewStatus.approved and risk["required_level"] == "partner" and task.required_level != "partner":
            raise review_tasks.AdjustmentReviewTaskError(
                "REVIEW_TASK_RISK_STALE",
                "重要性或风险判断在提交后发生变化，请重新提交复核",
            )
        evidence: list[dict[str, Any]] = []
        if status == ReviewStatus.approved and risk["evidence_required"]:
            from app.services.adjustment_evidence_service import require_adjustment_evidence
            evidence = await require_adjustment_evidence(
                self.db, project_id=project_id, year=int(rows[0].year),
                entry_group_id=entry_group_id,
            )

        info = await self.adjustments.change_review_status(
            project_id,
            entry_group_id,
            ReviewStatusChange(
                status=status,
                reason=(reason or "").strip() or None,
                expected_revision=review_tasks.group_content_revision(rows),
            ),
            actor.id,
        )
        await review_tasks.decide_task(
            self.db,
            task,
            actor_id=actor.id,
            status=status.value,
            reason=reason,
        )
        info["review_task_id"] = str(task.id)
        info["review_task_revision"] = task.revision
        if reason:
            info["reason"] = reason
        info["risk"] = risk
        info["evidence"] = evidence

        if status == ReviewStatus.rejected:
            return AdjustmentDecisionResult(info, False, tuple(info["account_codes"]))

        origin = rows[0].origin or "manual"
        if origin == "workpaper":
            # 金额由来源底稿显式发布写 wp_adjustment；集中批准只成为发布前置。
            info["tb_update_status"] = "awaiting_workpaper_publish"
            return AdjustmentDecisionResult(info, False, tuple(info["account_codes"]))

        year = int(rows[0].year)
        company_code = str(rows[0].company_code)
        account_codes = list(info["account_codes"])
        await self.ensure_tb_rows(
            project_id=project_id,
            year=year,
            company_code=company_code,
            account_codes=account_codes,
        )
        tb = TrialBalanceService(self.db)
        await tb.recalc_adjustments(
            project_id, year, company_code=company_code, account_codes=account_codes,
        )
        await tb.recalc_audited(
            project_id, year, company_code=company_code, account_codes=account_codes,
        )
        from app.services.adjustment_treatment_service import record_initial_inclusion
        await record_initial_inclusion(
            self.db,
            project_id=project_id,
            year=year,
            entry_group_id=entry_group_id,
            actor_id=actor.id,
        )

        common_extra = {
            "operator_id": str(actor.id),
            "operator_name": getattr(actor, "username", ""),
            "origin": origin,
            "tb_recalc_committed": True,
            "review_task_id": str(task.id),
            "review_task_revision": task.revision,
        }
        publications: list[PendingPublication] = []
        publications.append(await DurableEventOutboxService.enqueue_event(self.db, EventPayload(
            event_type=EventType.ADJUSTMENT_APPROVED,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            entry_group_id=entry_group_id,
            extra=common_extra,
        )))
        publications.append(await DurableEventOutboxService.enqueue_event(self.db, EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            entry_group_id=entry_group_id,
            extra={**common_extra, "trigger": "adjustment_approved"},
        )))
        info["tb_update_status"] = "committed"
        return AdjustmentDecisionResult(info, True, tuple(account_codes), tuple(publications))

    async def revoke(
        self,
        *,
        project_id: UUID,
        entry_group_id: UUID,
        actor: Any,
        reason: str | None = None,
    ) -> AdjustmentDecisionResult:
        rows = await self.adjustments._get_group_rows(
            project_id, entry_group_id, for_update=True,
        )
        if not rows or rows[0].review_status != ReviewStatus.approved:
            raise ValueError("只有已批准的调整分录可以撤回复核")
        revision = self.adjustments._group_content_revision(rows)
        info = await self.adjustments.change_review_status(
            project_id,
            entry_group_id,
            ReviewStatusChange(status=ReviewStatus.draft, expected_revision=revision),
            actor.id,
            allow_approved_revoke=True,
        )
        origin = rows[0].origin or "manual"
        account_codes = list(info["account_codes"])
        if origin == "workpaper":
            info["tb_update_status"] = "workpaper_publish_unchanged"
            return AdjustmentDecisionResult(info, False, tuple(account_codes))

        year = int(rows[0].year)
        company_code = str(rows[0].company_code)
        tb = TrialBalanceService(self.db)
        await tb.recalc_adjustments(
            project_id, year, company_code=company_code, account_codes=account_codes,
        )
        await tb.recalc_audited(
            project_id, year, company_code=company_code, account_codes=account_codes,
        )
        extra = {
            "operator_id": str(actor.id),
            "operator_name": getattr(actor, "username", ""),
            "origin": origin,
            "tb_recalc_committed": True,
            "trigger": "adjustment_review_revoked",
            "reason": (reason or "").strip() or None,
        }
        publications: list[PendingPublication] = []
        publications.append(await DurableEventOutboxService.enqueue_event(self.db, EventPayload(
            event_type=EventType.ADJUSTMENT_REVIEW_REVOKED,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            entry_group_id=entry_group_id,
            extra=extra,
        )))
        publications.append(await DurableEventOutboxService.enqueue_event(self.db, EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=project_id,
            year=year,
            account_codes=account_codes,
            entry_group_id=entry_group_id,
            extra=extra,
        )))
        info["tb_update_status"] = "committed"
        return AdjustmentDecisionResult(info, True, tuple(account_codes), tuple(publications))
