"""交付 readiness 的数据源查询与内容摘要。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deliverable_readiness_types import ReadinessBlocker, SourceStatus
from app.services.deliverable_source_digest import content_digest

logger = logging.getLogger(__name__)


class ReadinessSourceChecks:
    """数据集、TB、推送、调整、报表和附注的权威源检查。"""

    async def _check_dataset(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
    ) -> SourceStatus:
        """记录当前 active 账套版本；历史无数据集项目不因此单独阻断。"""
        from app.models.dataset_models import DatasetStatus, LedgerDataset

        dataset = (
            await db.execute(
                sa.select(LedgerDataset)
                .where(
                    LedgerDataset.project_id == project_id,
                    LedgerDataset.year == year,
                    LedgerDataset.status == DatasetStatus.active,
                )
                .order_by(
                    LedgerDataset.activated_at.desc().nullslast(),
                    LedgerDataset.created_at.desc(),
                    LedgerDataset.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if dataset is None:
            return SourceStatus(
                available=False,
                detail={
                    "source_kind": "ledger_dataset",
                    "version_id": None,
                    "content_digest": content_digest([]),
                },
            )
        return SourceStatus(
            available=True,
            count=1,
            detail={
                "source_kind": "ledger_dataset",
                "version_id": str(dataset.id),
                "content_digest": content_digest(
                    [
                        {
                            "id": dataset.id,
                            "source_type": dataset.source_type,
                            "source_summary": dataset.source_summary,
                            "record_summary": dataset.record_summary,
                            "validation_summary": dataset.validation_summary,
                            "previous_dataset_id": dataset.previous_dataset_id,
                        }
                    ]
                ),
            },
        )

    async def _check_trial_balance(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
    ) -> SourceStatus:
        """试算表就绪检查。"""
        from app.models.audit_platform_models import TrialBalance

        rows = list(
            (
                await db.execute(
                    sa.select(
                        TrialBalance.id,
                        TrialBalance.company_code,
                        TrialBalance.standard_account_code,
                        TrialBalance.account_name,
                        sa.cast(TrialBalance.account_category, sa.String).label("account_category"),
                        TrialBalance.unadjusted_amount,
                        TrialBalance.rje_adjustment,
                        TrialBalance.aje_adjustment,
                        TrialBalance.audited_amount,
                        TrialBalance.wp_adjustment,
                        TrialBalance.wp_publish_base,
                        TrialBalance.opening_balance,
                        TrialBalance.currency_code,
                    ).where(
                        TrialBalance.project_id == project_id,
                        TrialBalance.year == year,
                        TrialBalance.is_deleted == False,  # noqa: E712
                    )
                )
            ).mappings().all()
        )
        tb_count = len(rows)

        status = SourceStatus(
            available=tb_count > 0,
            count=tb_count,
            detail={
                "source_kind": "trial_balance",
                "content_digest": content_digest(rows),
            },
        )

        if tb_count == 0:
            blockers.append(ReadinessBlocker(
                code="tb_snapshot_missing",
                message="试算表快照不存在，无法生成审定财务报表",
                evidence={"project_id": str(project_id), "year": year},
            ))

        return status

    async def _check_formula_push(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
        *,
        report_scope: str | None = None,
    ) -> SourceStatus:
        """按项目口径检查最后一次成功推送并记录其不可变 run 摘要。"""
        if str(report_scope or "").lower() == "consolidated":
            from app.models.consol_push_models import ConsolPushRun as RunModel
            source_kind = "consol_push_run"
            component = "consol_push"
        else:
            from app.models.formula_push_models import FormulaPushRun as RunModel
            source_kind = "formula_push_run"
            component = "formula_push"

        try:
            runs = list(
                (
                    await db.execute(
                        sa.select(RunModel)
                        .where(
                            RunModel.project_id == project_id,
                            RunModel.year == year,
                            RunModel.status == "succeeded",
                        )
                        .order_by(
                            RunModel.finished_at.desc().nullslast(),
                            RunModel.started_at.desc(),
                            RunModel.id.desc(),
                        )
                    )
                ).scalars().all()
            )
        except Exception as exc:
            logger.warning("%s query failed: %s", component, exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="公式推送数据不可查询（所需迁移可能未执行）",
                evidence={"component": component, "error": str(exc)[:200]},
            ))
            return SourceStatus(
                detail={
                    "source_kind": source_kind,
                    "content_digest": content_digest([]),
                }
            )

        latest = runs[0] if runs else None
        latest_payload: dict[str, Any] | None = None
        if latest is not None:
            latest_payload = {
                "id": latest.id,
                "status": latest.status,
                "trigger_source": latest.trigger_source,
            }
            if source_kind == "consol_push_run":
                latest_payload.update(
                    steps=latest.steps,
                    warnings=latest.warnings,
                )
            else:
                latest_payload.update(
                    written_count=latest.written_count,
                    unchanged_count=latest.unchanged_count,
                    kept_count=latest.kept_count,
                    skipped_count=latest.skipped_count,
                    detail=latest.detail,
                )
        status = SourceStatus(
            available=latest is not None,
            count=len(runs),
            detail={
                "source_kind": source_kind,
                "run_id": str(latest.id) if latest is not None else None,
                "run_status": latest.status if latest is not None else None,
                "content_digest": content_digest(
                    [latest_payload] if latest_payload is not None else []
                ),
            },
        )

        if latest is None:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message=(
                    "合并推送未成功运行，合并报表与附注可能不完整"
                    if source_kind == "consol_push_run"
                    else "公式推送未成功运行，下游底稿/附注数据可能不完整"
                ),
                evidence={"component": component, "project_id": str(project_id), "year": year},
            ))
        return status

    async def _check_adjustments(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
        warnings: list[ReadinessBlocker],
    ) -> SourceStatus:
        """调整分录确认检查 — draft 状态的调整是硬阻断。"""
        from app.models.audit_platform_models import Adjustment

        rows = list(
            (
                await db.execute(
                    sa.select(Adjustment).where(
                        Adjustment.project_id == project_id,
                        Adjustment.year == year,
                        Adjustment.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
        )
        total_count = len(rows)
        unconfirmed = sum(
            getattr(row.review_status, "value", row.review_status)
            in {"draft", "pending_review"}
            for row in rows
        )

        status = SourceStatus(
            available=True,
            count=total_count,
            detail={
                "unconfirmed_count": unconfirmed,
                "source_kind": "adjustments",
                "content_digest": content_digest(
                    {
                        "id": row.id,
                        "company_code": row.company_code,
                        "adjustment_no": row.adjustment_no,
                        "adjustment_type": row.adjustment_type,
                        "description": row.description,
                        "account_code": row.account_code,
                        "account_name": row.account_name,
                        "debit_amount": row.debit_amount,
                        "credit_amount": row.credit_amount,
                        "entry_group_id": row.entry_group_id,
                        "review_status": row.review_status,
                        "reviewer_id": row.reviewer_id,
                        "rejection_reason": row.rejection_reason,
                        "passed_reason": row.passed_reason,
                        "origin": row.origin,
                        "source_ref": row.source_ref,
                    }
                    for row in rows
                ),
            },
        )

        if unconfirmed > 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message=f"有 {unconfirmed} 条调整分录尚未确认（draft/pending_review），出具前需全部确认或删除",
                evidence={
                    "component": "adjustments",
                    "unconfirmed_count": unconfirmed,
                    "total_count": total_count,
                },
            ))

        return status

    async def _check_reports(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
    ) -> SourceStatus:
        """报表就绪检查 — 存在且无过期行（过期 = report_freshness.stale_clause，含计算版本不是当前版本的存量行）。"""
        from app.services.report_freshness import count_summary

        counts = await count_summary(db, project_id, year)
        report_count, stale_count = counts.total, counts.stale
        from app.models.report_models import FinancialReport

        rows = list(
            (
                await db.execute(
                    sa.select(FinancialReport).where(
                        FinancialReport.project_id == project_id,
                        FinancialReport.year == year,
                        FinancialReport.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
        )

        calc_versions = sorted(
            {row.calc_version for row in rows if row.calc_version is not None}
        )
        status = SourceStatus(
            available=report_count > 0,
            count=report_count,
            stale_count=stale_count,
            detail={
                "source_kind": "financial_report",
                "calc_versions": calc_versions,
                "version_id": (
                    "calc:" + ",".join(str(value) for value in calc_versions)
                    if calc_versions
                    else None
                ),
                "content_digest": content_digest(
                    {
                        "id": row.id,
                        "report_type": row.report_type,
                        "row_code": row.row_code,
                        "row_name": row.row_name,
                        "current_period_amount": row.current_period_amount,
                        "prior_period_amount": row.prior_period_amount,
                        "formula_used": row.formula_used,
                        "source_accounts": row.source_accounts,
                        "indent_level": row.indent_level,
                        "is_total_row": row.is_total_row,
                        "is_stale": row.is_stale,
                        "blank_reason": row.blank_reason,
                        "calc_version": row.calc_version,
                        "calc_error": row.calc_error,
                    }
                    for row in rows
                ),
            },
        )

        if report_count == 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="财务报表数据不存在，需先生成报表",
                evidence={"component": "financial_report", "project_id": str(project_id), "year": year},
            ))
        elif stale_count > 0:
            failed = f"，其中 {counts.calc_error} 行计算失败" if counts.calc_error else ""
            blockers.append(ReadinessBlocker(
                code="stale_source",
                message=(f"有 {stale_count} 条报表行已过期（已标过期或计算版本不是当前版本{failed}），"
                         "需重新生成报表后再出具"),
                evidence={
                    "component": "financial_report",
                    "stale_count": stale_count,
                    "total_count": report_count,
                    "calc_error_count": counts.calc_error,
                    "blank_count": counts.blank,
                },
            ))

        return status

    async def _check_notes(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
        *,
        report_scope: str | None = None,
        template_type: str | None = None,
    ) -> SourceStatus:
        """按项目口径检查权威附注源；合并只认已验证企业树根节点。"""
        root_node_key: str | None = None
        if str(report_scope or "").lower() == "consolidated":
            from app.services.consol_note_export_adapter import (
                ConsolNoteExportError,
                load_root_consol_records,
            )

            try:
                root = await load_root_consol_records(
                    db,
                    project_id,
                    year,
                    template_type=template_type,
                )
            except ConsolNoteExportError as exc:
                blockers.append(ReadinessBlocker(
                    code="upstream_not_ready",
                    message=str(exc),
                    evidence={
                        "component": "consol_disclosure_notes",
                        "error_code": exc.code,
                    },
                ))
                return SourceStatus(
                    detail={
                        "source_kind": "consol_note_data",
                        "content_digest": content_digest([]),
                    }
                )
            rows = list(root.records)
            root_node_key = root.node_key
            source_kind = "consol_note_data"
            component = "consol_disclosure_notes"
            digest_rows = (
                {
                    "id": row.id,
                    "section_id": row.section_id,
                    "node_key": row.node_key,
                    "data": row.data,
                    "is_stale": row.is_stale,
                    "cell_state": row.cell_state,
                    "locked_cells": row.locked_cells,
                    "last_formula_run_id": row.last_formula_run_id,
                    "last_formula_value": row.last_formula_value,
                }
                for row in rows
            )
        else:
            from app.models.report_models import DisclosureNote

            rows = list(
                (
                    await db.execute(
                        sa.select(DisclosureNote).where(
                            DisclosureNote.project_id == project_id,
                            DisclosureNote.year == year,
                            DisclosureNote.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalars().all()
            )
            source_kind = "disclosure_notes"
            component = "disclosure_notes"
            digest_rows = (
                {
                    "id": row.id,
                    "note_section": row.note_section,
                    "section_title": row.section_title,
                    "section_id": row.section_id,
                    "level": row.level,
                    "parent_section_id": row.parent_section_id,
                    "sort_index": row.sort_index,
                    "sort_order": row.sort_order,
                    "content_type": row.content_type,
                    "table_data": row.table_data,
                    "text_content": row.text_content,
                    "source_template": row.source_template,
                    "status": row.status,
                    "is_stale": row.is_stale,
                    "is_empty": row.is_empty,
                    "bound_dataset_id": row.bound_dataset_id,
                    "template_lineage": row.template_lineage,
                    "text_template_vars": row.text_template_vars,
                    "last_sync_source": row.last_sync_source,
                    "last_sync_wp_id": row.last_sync_wp_id,
                }
                for row in rows
            )

        note_count = len(rows)
        stale_count = sum(bool(getattr(row, "is_stale", False)) for row in rows)
        status = SourceStatus(
            available=note_count > 0,
            count=note_count,
            stale_count=stale_count,
            detail={
                "source_kind": source_kind,
                "root_node_key": root_node_key,
                "content_digest": content_digest(digest_rows),
            },
        )

        if source_kind == "consol_note_data" and note_count > 0 and stale_count == 0:
            from app.services.consol_note_export_adapter import (
                ConsolNoteExportError,
                adapt_root_consol_records,
            )
            from app.services.consol_note_formula_service import consol_note_tables
            from app.services.note_deliverable_outline import load_section_code_index
            from app.services.note_section_catalog import build_variant_key

            try:
                adapt_root_consol_records(
                    rows,
                    project_id=project_id,
                    year=year,
                    template_type=root.template_type,
                    index_sections=load_section_code_index(
                        build_variant_key(root.template_type, "consolidated")
                    ),
                    table_templates=consol_note_tables(root.template_type),
                )
            except ConsolNoteExportError as exc:
                blockers.append(ReadinessBlocker(
                    code="upstream_not_ready",
                    message=str(exc),
                    evidence={
                        "component": component,
                        "error_code": exc.code,
                    },
                ))

        if note_count == 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message=(
                    "合并项目根节点没有附注数据，需先完成重新汇总"
                    if source_kind == "consol_note_data"
                    else "报表附注不存在，需先准备附注章节"
                ),
                evidence={"component": component, "project_id": str(project_id), "year": year},
            ))
        elif stale_count > 0:
            blockers.append(ReadinessBlocker(
                code="stale_source",
                message=f"有 {stale_count} 个附注章节标记为过期（is_stale），需刷新后再出具",
                evidence={
                    "component": component,
                    "stale_count": stale_count,
                    "total_count": note_count,
                },
            ))
        return status


__all__ = ["ReadinessSourceChecks"]
