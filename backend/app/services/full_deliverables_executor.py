"""一键生成全套交付件执行器 — audit-report-template-integration task 15 / design §14.

job_type=``full_deliverables``：在单个 ``ExportJob`` 内同步顺序生成
财务报表 → 附注 → 报告正文（与 ``generateGuard`` 依赖链一致）。

铁律：
- 复用 ``DeliverableService`` + ``export_jobs_v2``，不另起后台调度器（design §14）。
- 复用 ``ExportJobService`` 创建 job/item、更新进度（与 ``create_full_package`` 同步执行模式一致）。
- 单项失败不阻断其余步骤（需求 14.3）：每步 try/except，标记 item failed 后继续；
  最终 ``update_progress(done, failed)`` 自动落 partial_failed。
- service 仅 ``flush`` 不 ``commit``；由 router 统一 commit。
- 附注导出当前走 **programmatic 模式**（template 模式在 Phase 0.6.2 全量打标前 HARD-BLOCK）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.phase13_models import (
    ExportJob,
    ExportJobStatus,
    WordExportDocType,
)
from app.models.report_models import AuditReport, CompanyType, OpinionType
from app.services.export_job_service import ExportJobService
from app.services.report_body_service import ReportBodyService

logger = logging.getLogger(__name__)

# 全套生成步骤顺序（与 generateGuard 依赖链一致：报表 → 附注 → 报告正文）
FULL_DELIVERABLES_STEPS: list[str] = [
    "financial_reports",
    "disclosure_notes",
    "report_body",
]

# 报告正文 OPT 兜底默认（design §14 第 4 步）
_OPT_HARDCODED_FALSE = (
    "emphasis",
    "going_concern",
    "other_matter",
    "other_information",
)


def resolve_opt_defaults(
    *,
    payload_optional_sections: dict[str, bool] | None,
    last_optional_sections: dict[str, bool] | None,
    registry_defaults: dict[str, bool] | None,
    kam_required: bool,
) -> dict[str, bool]:
    """报告正文 OPT 默认勾选优先级链（design §14，无弹窗 job 内自动 confirm）。

    优先级：
      ① payload 显式 ``optional_sections``
      ② ``audit_report.report_body_json.optional_sections``（项目上次人工选择）
      ③ ``placeholder_registry.get_opt_defaults(company_subtype)``
      ④ 兜底硬编码：``key_audit_matters = kam_required``；``comparative = True``；其余 False。

    纯函数（不触 DB），便于单测覆盖优先级与兜底。
    """
    if payload_optional_sections:
        return {str(k): bool(v) for k, v in payload_optional_sections.items()}
    if last_optional_sections:
        return {str(k): bool(v) for k, v in last_optional_sections.items()}
    if registry_defaults:
        return {str(k): bool(v) for k, v in registry_defaults.items()}
    # ④ 兜底硬编码
    fallback: dict[str, bool] = {
        "key_audit_matters": bool(kam_required),
        "comparative": True,
    }
    for sid in _OPT_HARDCODED_FALSE:
        fallback[sid] = False
    return fallback


@dataclass
class StepOutcome:
    """单步执行结果。"""

    step: str
    item_id: UUID
    succeeded: bool
    error_message: str | None = None
    task_id: UUID | None = None
    validation_warning: str | None = None


@dataclass
class FullDeliverablesResult:
    """全套生成结果汇总。"""

    job_id: UUID
    status: str
    done: int
    failed: int
    outcomes: list[StepOutcome] = field(default_factory=list)
    kam_warning: str | None = None
    resolved_optional_sections: dict[str, bool] | None = None


class FullDeliverablesExecutor:
    """全套交付件同步执行器（job_type=full_deliverables）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.job_svc = ExportJobService(db)

    # ------------------------------------------------------------------
    # job 级前置校验（task 15.4 / design §14）
    # ------------------------------------------------------------------
    async def precheck(self, project_id: UUID, year: int) -> None:
        """试算表就绪校验（依赖链根节点，未就绪整链无法生成）。

        报表/附注/报告正文均下游于试算表；报表本身由本 job 步骤 1 生成，
        故 job 级硬前置仅校验 ``trialBalanceReady``，文案与 ``generateGuard`` 对齐。
        """
        if not await self._trial_balance_ready(project_id, year):
            raise ValueError(
                "无法生成「全套交付件」：试算表/序时账数据尚未就绪，请先完成前置数据准备"
            )

    async def _trial_balance_ready(self, project_id: UUID, year: int) -> bool:
        from app.models.audit_platform_models import TrialBalance

        result = await self.db.execute(
            sa.select(sa.func.count())
            .select_from(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        return (result.scalar_one() or 0) > 0

    # ------------------------------------------------------------------
    # 主执行流程
    # ------------------------------------------------------------------
    async def run(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        payload: dict,
    ) -> FullDeliverablesResult:
        """创建 job → 同步顺序执行三步 → 更新进度。

        payload 形如 design §14：
          ``{ year, template_variant, steps: [...], optional_sections: null }``
        """
        year = int(payload.get("year"))
        await self.precheck(project_id, year)

        steps = payload.get("steps") or FULL_DELIVERABLES_STEPS
        # 仅保留受支持的步骤并按权威顺序排序
        steps = [s for s in FULL_DELIVERABLES_STEPS if s in steps]
        if not steps:
            steps = list(FULL_DELIVERABLES_STEPS)

        job = await self.job_svc.create_job(
            project_id=project_id,
            job_type="full_deliverables",
            payload=payload,
            user_id=user_id,
            total=len(steps),
        )

        outcomes: list[StepOutcome] = []
        kam_warning: str | None = None
        resolved_opt: dict[str, bool] | None = None

        done = 0
        failed = 0
        for step in steps:
            item = await self.job_svc.add_item(job.id)
            try:
                if step == "financial_reports":
                    task_id = await self._run_financial_reports(
                        project_id, year, user_id
                    )
                    outcome = StepOutcome(step, item.id, True, task_id=task_id)
                elif step == "disclosure_notes":
                    task_id = await self._run_disclosure_notes(
                        project_id, year, user_id
                    )
                    outcome = StepOutcome(step, item.id, True, task_id=task_id)
                elif step == "report_body":
                    task_id, warning, resolved_opt = await self._run_report_body(
                        project_id, year, user_id, payload
                    )
                    kam_warning = warning
                    outcome = StepOutcome(
                        step, item.id, True,
                        task_id=task_id, validation_warning=warning,
                    )
                else:  # pragma: no cover - 已被 steps 过滤
                    raise ValueError(f"未知步骤: {step}")

                await self.job_svc.update_item_status(
                    item.id,
                    ExportJobStatus.succeeded.value,
                )
                if outcome.task_id is not None:
                    await self._link_item_task(item.id, outcome.task_id)
                done += 1
            except Exception as exc:  # noqa: BLE001 — 单项失败隔离（需求 14.3）
                logger.warning(
                    "[FULL_DELIVERABLES] step=%s failed job=%s: %s",
                    step, job.id, exc,
                )
                await self.job_svc.update_item_status(
                    item.id,
                    ExportJobStatus.failed.value,
                    error_message=str(exc)[:500],
                )
                outcome = StepOutcome(step, item.id, False, error_message=str(exc))
                failed += 1
            outcomes.append(outcome)

        # 进度落库（自动判定 succeeded / partial_failed / failed）
        await self.job_svc.update_progress(job.id, done=done, failed=failed)

        # KAM 警告 + 解析后的 OPT 写入 job.payload metadata（design §14 第 6 步）
        await self._persist_job_metadata(job, kam_warning, resolved_opt)

        refreshed = await self.job_svc.get_job(job.id)
        status = refreshed.status if refreshed else ExportJobStatus.queued.value

        return FullDeliverablesResult(
            job_id=job.id,
            status=status,
            done=done,
            failed=failed,
            outcomes=outcomes,
            kam_warning=kam_warning,
            resolved_optional_sections=resolved_opt,
        )

    # ------------------------------------------------------------------
    # 单步实现（复用 deliverable 路由同款内部 service 路径）
    # ------------------------------------------------------------------
    async def _run_financial_reports(
        self, project_id: UUID, year: int, user_id: UUID
    ) -> UUID:
        """生成财务报表 xlsx 并经 DeliverableService 落交付中心（复用 render 路径）。"""
        from app.services.deliverable_service import DeliverableService
        from app.services.report_excel_exporter import ReportExcelExporter

        dsvc = DeliverableService(self.db)
        task, _ = await dsvc.export_or_new_deliverable(
            project_id,
            WordExportDocType.financial_report.value,
            None,
            user_id,
        )
        await self.db.flush()

        exporter = ReportExcelExporter(self.db)
        buf = await exporter.export(project_id, year)
        file_name = f"financial_reports_{year}.xlsx"
        snapshot_refs = await dsvc.capture_snapshot_refs(
            project_id, year, WordExportDocType.financial_report.value
        )
        await dsvc.render_and_store(
            task.id,
            docx_bytes=buf.getvalue(),
            user_id=user_id,
            source_snapshot_refs=snapshot_refs,
            file_name=file_name,
        )
        await self._advance_to_editing(dsvc, task.id)
        return task.id

    async def _run_disclosure_notes(
        self, project_id: UUID, year: int, user_id: UUID
    ) -> UUID:
        """生成附注 Word（programmatic 模式）并落交付中心。

        注：template 模式（``##SECTION:`` 模板填充）在 Phase 0.6.2 附注全量打标前
        HARD-BLOCK；``NoteWordExporter.export`` 当前实现即 programmatic（从零构建文档）。
        """
        from app.services.deliverable_service import DeliverableService
        from app.services.note_section_catalog import normalize_report_scope
        from app.services.note_word_exporter import NoteWordExporter

        dsvc = DeliverableService(self.db)
        task, _ = await dsvc.export_or_new_deliverable(
            project_id,
            WordExportDocType.disclosure_notes.value,
            None,
            user_id,
        )
        await self.db.flush()

        proj_scope = await self._project_report_scope(project_id)
        template_type = await self._project_template_type(project_id)

        exporter = NoteWordExporter(self.db)
        buf = await exporter.export(
            project_id,
            year,
            template_type=template_type,
            report_scope=normalize_report_scope(proj_scope),
        )
        file_name = f"disclosure_notes_{year}.docx"
        snapshot_refs = await dsvc.capture_snapshot_refs(
            project_id, year, WordExportDocType.disclosure_notes.value
        )
        await dsvc.render_and_store(
            task.id,
            docx_bytes=buf.getvalue(),
            user_id=user_id,
            source_snapshot_refs=snapshot_refs,
            file_name=file_name,
        )
        await self._advance_to_editing(dsvc, task.id)
        return task.id

    async def _run_report_body(
        self,
        project_id: UUID,
        year: int,
        user_id: UUID,
        payload: dict,
    ) -> tuple[UUID, str | None, dict[str, bool]]:
        """报告正文：preview → 解析 OPT 默认 → 自动 confirm（无弹窗，design §14）。"""
        from app.services.placeholder_registry import get_placeholder_registry
        from app.services.template_fill_service import TemplateFillService

        report = await self._get_report(project_id, year)
        opinion_type = self._opinion_value(report)
        company_type = self._company_type_value(report)
        is_pie = bool(report.is_pie) if report is not None else False
        template_variant = str(payload.get("template_variant") or "simple")

        svc = TemplateFillService(self.db)
        preview = await svc.preview_report_body(
            project_id,
            year,
            opinion_type=opinion_type,
            company_subtype=(report.company_subtype if report is not None else None),
            template_variant=template_variant,
            user_id=user_id,
        )
        resolved_subtype = preview.company_subtype_resolved

        # OPT 默认优先级链（design §14）
        kam_required = ReportBodyService.kam_required(
            ReportBodyService.__new__(ReportBodyService),
            company_type=company_type,
            is_pie=is_pie,
            opinion_type=opinion_type,
        )
        registry_defaults = get_placeholder_registry().get_opt_defaults(resolved_subtype)
        last_choice = None
        if report is not None and isinstance(report.report_body_json, dict):
            last_choice = report.report_body_json.get("optional_sections")
            if not isinstance(last_choice, dict):
                last_choice = None

        resolved_opt = resolve_opt_defaults(
            payload_optional_sections=payload.get("optional_sections"),
            last_optional_sections=last_choice,
            registry_defaults=registry_defaults,
            kam_required=kam_required,
        )

        # 仅对模板实际扫描到的 OPT 段落下发勾选（避免下发模板中不存在的 section）
        scanned_ids = {v.section_id for v in preview.optional_sections}
        if scanned_ids:
            selections = {sid: resolved_opt.get(sid, False) for sid in scanned_ids}
        else:
            selections = resolved_opt

        confirm = await svc.confirm_report_body(
            project_id,
            year,
            preview_session_id=preview.preview_session_id,
            optional_sections=selections,
            user_id=user_id,
        )
        return confirm.task_id, confirm.validation_warning, selections

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def _link_item_task(self, item_id: UUID, task_id: UUID) -> None:
        from app.models.phase13_models import ExportJobItem

        item = await self.db.get(ExportJobItem, item_id)
        if item is not None:
            item.word_export_task_id = task_id
            await self.db.flush()

    async def _persist_job_metadata(
        self,
        job: ExportJob,
        kam_warning: str | None,
        resolved_opt: dict[str, bool] | None,
    ) -> None:
        payload = dict(job.payload or {})
        payload["kam_warning"] = kam_warning
        if resolved_opt is not None:
            payload["resolved_optional_sections"] = resolved_opt
        job.payload = payload
        await self.db.flush()

    async def _advance_to_editing(self, dsvc, task_id: UUID) -> None:
        from app.models.phase13_models import WordExportStatus

        refreshed = await dsvc.get_task(task_id)
        if refreshed and refreshed.status == WordExportStatus.draft.value:
            for st in (
                WordExportStatus.generating.value,
                WordExportStatus.generated.value,
                WordExportStatus.editing.value,
            ):
                try:
                    await dsvc.update_status(task_id, st)
                except ValueError:
                    break
        elif refreshed and refreshed.status == WordExportStatus.generated.value:
            try:
                await dsvc.update_status(task_id, WordExportStatus.editing.value)
            except ValueError:
                pass

    async def _get_report(self, project_id: UUID, year: int) -> AuditReport | None:
        result = await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
                AuditReport.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _opinion_value(report: AuditReport | None) -> str:
        if report is None:
            return OpinionType.unqualified.value
        return (
            report.opinion_type.value
            if isinstance(report.opinion_type, OpinionType)
            else str(report.opinion_type)
        )

    @staticmethod
    def _company_type_value(report: AuditReport | None) -> str:
        if report is None:
            return CompanyType.non_listed.value
        return (
            report.company_type.value
            if isinstance(report.company_type, CompanyType)
            else str(report.company_type)
        )

    async def _project_report_scope(self, project_id: UUID) -> str | None:
        row = (
            await self.db.execute(
                sa.select(Project.report_scope).where(
                    Project.id == project_id,
                    Project.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        return row if isinstance(row, str) else None

    async def _project_template_type(self, project_id: UUID) -> str:
        row = (
            await self.db.execute(
                sa.select(Project.template_type).where(
                    Project.id == project_id,
                    Project.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        return row if isinstance(row, str) and row else "soe"
