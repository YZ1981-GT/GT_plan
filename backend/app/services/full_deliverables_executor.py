"""一键生成全套交付件执行器 — audit-report-template-integration task 15 / design §14.

job_type=``full_deliverables``：在单个 ``ExportJob`` 内同步顺序生成
审定财务报表 → 未审财务报表 → 附注 → 报告正文（与 ``generateGuard`` 依赖链一致）。

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
    ExportJobItem,
    ExportJobStatus,
    WordExportDocType,
)
from app.models.report_models import AuditReport, CompanyType, OpinionType
from app.services.deliverable_trio_snapshot import (
    TRIO_STEP_KEYS,
    DeliverableTrioSnapshot,
    build_digest,
)
from app.services.export_job_service import ExportJobService
from app.services.report_body_service import ReportBodyService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 正式三件套权威契约（spec chain-closure-phase4-deliverable-center-trio 需求 2.1/2.5）
# ---------------------------------------------------------------------------
#
# 单一真源原则：稳定键只有一处定义——``deliverable_trio_snapshot.TRIO_STEP_KEYS``。
# 本模块的 ``TRIO_STEPS`` 在其上附加 **固定顺序（sequence）**、**导出 doc_type** 与
# **前置依赖（depends_on）**，但键集合必须与 ``TRIO_STEP_KEYS`` 完全一致（见下方断言）。
# readiness service 复用的也是同一个 ``TRIO_STEP_KEYS``，三处不得各写一份键。
#
# ``financial_report_unadjusted`` 是**辅助对照步骤**，不进入 ``TRIO_STEPS``、不计入
# 正式完成数（trio_total 固定 3）、不进入成功 gate、也不占用正式下载集合。


#: 标记审计报告正文「因前置项失败而被依赖阻断」的 item 状态值（design §6）。
#: 不是 ``ExportJobStatus`` 枚举成员——它表达的是「未运行即被阻断」而非「运行失败」，
#: 聚合时既不算成功也不算可直接重试的导出器异常；status 列为自由 String，可承载此值。
BLOCKED_BY_DEPENDENCY: str = "blocked_by_dependency"


class SnapshotMismatchError(RuntimeError):
    """重试时发现 job 绑定快照与当前项目数据复算的 digest 不一致（需求 5.5）。

    绝不在旧快照上混用新数据重试 —— 由 router 映射为 409 并提示用户重新发起一键
    出具（新建 job）。携带两侧 digest 便于诊断。
    """

    def __init__(
        self, message: str, *, job_snapshot: str | None, current_snapshot: str
    ):
        super().__init__(message)
        self.message = message
        self.job_snapshot = job_snapshot
        self.current_snapshot = current_snapshot


@dataclass(frozen=True)
class TrioStep:
    """正式三件套的单个步骤定义（固定顺序 + 稳定键 + doc_type + 依赖）。"""

    key: str
    sequence: int
    doc_type: str
    #: 前置步骤键（其失败会使本步骤标 blocked_by_dependency）。audit_report 依赖前两项。
    depends_on: tuple[str, ...] = ()


#: 权威三件套：financial_report → disclosure_notes → audit_report（固定顺序，稳定键）。
#: audit_report 复用现有 ``report_body`` 渲染路径，但稳定键用 ``audit_report``（需求 2 正式集合）。
TRIO_STEPS: tuple[TrioStep, ...] = (
    TrioStep("financial_report", 1, WordExportDocType.financial_report.value),
    TrioStep("disclosure_notes", 2, WordExportDocType.disclosure_notes.value),
    TrioStep(
        "audit_report",
        3,
        WordExportDocType.audit_report.value,
        depends_on=("financial_report", "disclosure_notes"),
    ),
)

# 单一真源守护：TRIO_STEPS 的键集合与顺序必须与权威 TRIO_STEP_KEYS 完全一致。
# 任何一处漂移（改名/漏项/调换顺序）在 import 期即炸，杜绝第三份分叉定义。
assert tuple(s.key for s in TRIO_STEPS) == tuple(TRIO_STEP_KEYS), (
    "TRIO_STEPS 键/顺序必须与 deliverable_trio_snapshot.TRIO_STEP_KEYS 一致"
)

#: 辅助（非正式）步骤键：审前未审财务报表，仅内部对照，**不计入正式三件套**（需求 2.5）。
AUXILIARY_STEP_KEYS: tuple[str, ...] = (
    WordExportDocType.financial_report_unadjusted.value,
)

# 全套生成兼容顺序（旧 full_package 调用保留；非正式三件套编排入口）。
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
    #: item 终态状态值（succeeded / failed / blocked_by_dependency）。
    status: str = ExportJobStatus.succeeded.value
    #: 是否正式三件套成员（辅助项为 False，不计入正式完成数）。
    is_trio: bool = True
    sequence: int | None = None
    #: 报告正文步骤解析出的 OPT 勾选（仅 audit_report 步骤非空）。
    resolved_opt: dict[str, bool] | None = None
    #: 本次是否复用了已校验的既有版本文件而未重跑导出器（需求 5.3）。
    reused_existing: bool = False


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
    #: 共享交付快照 digest（三件套三项引用同一个值，需求 1.5/2.4）。
    snapshot_id: str | None = None
    #: 正式三件套总数（固定 3）与成功数（只统计正式三项，需求 2.6/4.4）。
    trio_total: int = len(TRIO_STEPS)
    trio_succeeded: int = 0


@dataclass
class RetryOutcome:
    """失败项重试结果汇总（design §7）。"""

    job_id: UUID
    #: 本次真正重跑（新增 attempt + 重渲染/落盘/建版本）的 item 数。
    retried: int
    #: 已成功且指纹仍有效、被复用而未重跑的正式项数（需求 5.3）。
    reused: int = 0
    outcomes: list[StepOutcome] = field(default_factory=list)
    snapshot_id: str | None = None


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
        """创建 job → 按权威 ``TRIO_STEPS`` 固定顺序生成三件套 → 聚合正式状态。

        payload 形如 design §14：
          ``{ year, template_variant, steps: [...], optional_sections: null }``

        关键边界（spec 需求 2.1–2.6 / 4.4，design §6）：

        - 固定顺序 ``financial_report → disclosure_notes → audit_report`` 来自 ``TRIO_STEPS``；
          不以字典遍历或 payload 顺序为准（``steps`` 仅用于子集过滤，顺序仍由 TRIO_STEPS 定）。
        - 三件套三项引用**同一** snapshot（``build_digest`` + ``bind_items_to_snapshot``）。
        - ``audit_report`` 的前置（前两项）失败时标 ``blocked_by_dependency``，**不运行导出器**、
          不伪装成导出异常；可在后续 retry 依赖成功项重跑。
        - 聚合**只统计正式三项**：三项成功 → succeeded；无阻断但部分失败 → partial_failed；
          三项全失败 → failed。``financial_report_unadjusted`` 等辅助项不计入正式完成数。
        """
        year = int(payload.get("year"))
        await self.precheck(project_id, year)

        # payload.steps 仅做「正式三件套子集」过滤；顺序永远由 TRIO_STEPS 决定（需求 2.1）。
        requested = payload.get("steps")
        trio_steps = list(TRIO_STEPS)
        if requested:
            requested_set = set(requested)
            filtered = [s for s in TRIO_STEPS if s.key in requested_set]
            if filtered:
                trio_steps = filtered

        job = await self.job_svc.create_job(
            project_id=project_id,
            job_type="full_deliverables",
            payload=payload,
            user_id=user_id,
            total=len(trio_steps),
        )

        # 建立不可变共享快照 digest 并写入 job（三项 item 稍后绑定同一值）。
        snapshot_input = await self._build_snapshot_input(project_id, year, payload)
        snapshot_id = build_digest(snapshot_input)
        job.snapshot_id = snapshot_id
        await self.db.flush()

        outcomes: list[StepOutcome] = []
        kam_warning: str | None = None
        resolved_opt: dict[str, bool] | None = None

        done = 0
        failed = 0
        blocked = 0
        succeeded_keys: set[str] = set()

        for step in trio_steps:
            item = await self.job_svc.add_item(job.id)
            await self._stamp_item_contract(item.id, step, snapshot_id)

            # 依赖阻断：前置项未成功 ⇒ 本步骤标 blocked_by_dependency，不运行导出器（design §6）。
            # 阻断不是「步骤失败」，不开 attempt、不进 savepoint（它从未运行导出器）。
            unmet = [dep for dep in step.depends_on if dep not in succeeded_keys]
            if unmet:
                reason = (
                    f"前置项未成功，依赖阻断：缺少 {', '.join(unmet)}"
                )
                await self.job_svc.update_item_status(
                    item.id, BLOCKED_BY_DEPENDENCY, error_message=reason,
                )
                outcomes.append(
                    StepOutcome(
                        step.key, item.id, False,
                        error_message=reason,
                        status=BLOCKED_BY_DEPENDENCY,
                        sequence=step.sequence,
                    )
                )
                blocked += 1
                continue

            # 事务边界与 attempt 留痕由共享单元 ``_execute_step_in_savepoint`` 统一承载
            # （初次生成与 retry 走同一条渲染/落盘/指纹/版本路径，design §6/§7）。
            outcome = await self._execute_step_in_savepoint(
                job=job,
                item=item,
                step=step,
                project_id=project_id,
                year=year,
                user_id=user_id,
                payload=payload,
                snapshot_id=snapshot_id,
                trigger="initial",
            )
            outcomes.append(outcome)
            if outcome.succeeded:
                if outcome.validation_warning is not None:
                    kam_warning = outcome.validation_warning
                if outcome.resolved_opt is not None:
                    resolved_opt = outcome.resolved_opt
                succeeded_keys.add(step.key)
                done += 1
            else:
                failed += 1

        # 三项全部引用同一 snapshot（绑定 + 复核；需求 2.4 fail-closed）。
        snap = DeliverableTrioSnapshot(self.db)
        await snap.bind_items_to_snapshot(job.id, snapshot_id)

        # 进度落库（update_progress 自动判定 succeeded / partial_failed / failed）。
        # done+failed+blocked == total 时才会落终态；blocked 既非 done 也非可成功。
        await self.job_svc.update_progress(
            job.id, done=done, failed=failed + blocked,
        )

        # 正式三件套聚合（只统计正式三项，需求 2.6/4.4）。
        job.trio_total = len(TRIO_STEPS)
        job.trio_succeeded = done
        await self.db.flush()

        # KAM 警告 + 解析后的 OPT 写入 job.payload metadata（design §14 第 6 步）
        await self._persist_job_metadata(job, kam_warning, resolved_opt)

        refreshed = await self.job_svc.get_job(job.id)
        status = refreshed.status if refreshed else ExportJobStatus.queued.value

        return FullDeliverablesResult(
            job_id=job.id,
            status=status,
            done=done,
            failed=failed + blocked,
            outcomes=outcomes,
            kam_warning=kam_warning,
            resolved_optional_sections=resolved_opt,
            snapshot_id=snapshot_id,
            trio_total=len(TRIO_STEPS),
            trio_succeeded=done,
        )

    # ------------------------------------------------------------------
    # 共享步骤执行单元（初次生成 + retry 同一路径，design §6/§7）
    # ------------------------------------------------------------------
    async def _execute_step_in_savepoint(
        self,
        *,
        job: ExportJob,
        item: "ExportJobItem",
        step: TrioStep,
        project_id: UUID,
        year: int,
        user_id: UUID,
        payload: dict,
        snapshot_id: str,
        trigger: str,
    ) -> StepOutcome:
        """在 savepoint 内真正执行一个三件套步骤，返回 ``StepOutcome``。

        这是**初次生成**与**重试**共用的唯一执行路径（design §7 第 4 步要求 retry
        走同一渲染/落盘/指纹/版本流程，而非只改状态）。事务边界（需求 4.1/4.2/4.3）：

        - attempt（append-only 失败留痕）在 savepoint **之外**开/收；
        - 步骤业务写入（版本/task 状态/章节状态/item 成功投影）在 ``begin_nested()`` 内：
          成功随上下文 RELEASE 留在外层事务（router 统一 commit）；失败 ROLLBACK TO
          SAVEPOINT 撤销半成品，回滚**之后**在保存点外记 ``finish_attempt_failed`` +
          item=failed（失败留痕因在保存点外故不被回滚，需求 4.2/4.3）。

        ``trigger`` 区分 initial / retry —— retry 的 attempt_no 由 ``start_attempt``
        在该 item 现有最大值上 +1，原始失败 attempt 永不被覆盖（需求 5.4）。
        """
        attempt = await self.job_svc.start_attempt(
            job.id, item.id, snapshot_id=snapshot_id, trigger=trigger,
            created_by=user_id,
        )
        try:
            async with self.db.begin_nested():
                task_id, warning, step_opt = await self._dispatch_trio_step(
                    step, project_id, year, user_id, payload
                )
                if task_id is not None:
                    await self._link_item_task(item.id, task_id)
                # item 成功投影也在保存点内——与业务写入同生共死（避免「item=succeeded
                # 而版本不存在」）；retry 时同时清掉上一轮失败的 error_message。
                await self.job_svc.update_item_status(
                    item.id, ExportJobStatus.succeeded.value,
                )
        except Exception as exc:  # noqa: BLE001 — 单项失败隔离（需求 4.2/4.4）
            logger.warning(
                "[TRIO] step=%s %s failed job=%s: %s",
                step.key, trigger, job.id, exc,
            )
            await self.job_svc.finish_attempt_failed(
                attempt.id, exc,
                diagnostic_detail={
                    "step": step.key, "sequence": step.sequence, "trigger": trigger,
                },
            )
            await self.job_svc.update_item_status(
                item.id, ExportJobStatus.failed.value,
                error_message=str(exc)[:500],
            )
            return StepOutcome(
                step.key, item.id, False,
                error_message=str(exc),
                status=ExportJobStatus.failed.value,
                sequence=step.sequence,
            )

        # 保存点成功 RELEASE 后收尾：记成功 attempt（含文件指纹投影）。
        await self._finish_attempt_with_fingerprint(attempt.id, task_id)
        return StepOutcome(
            step.key, item.id, True,
            task_id=task_id, validation_warning=warning,
            status=ExportJobStatus.succeeded.value,
            sequence=step.sequence,
            resolved_opt=step_opt,
        )

    async def _finish_attempt_with_fingerprint(
        self, attempt_id: UUID, task_id: UUID | None
    ) -> None:
        """成功 attempt 收尾：把最新成功版本的 version_id/file_path/size/sha256 写入 attempt。

        文件指纹来自 ``render_and_store`` 已校验落盘的最终文件（需求 3.2/5.5），
        不重新另算一套；无 task_id（理论不至）时仅标成功。
        """
        version_id = None
        file_path = None
        file_size = None
        file_sha256 = None
        if task_id is not None:
            from app.services.deliverable_service import DeliverableService

            latest = await DeliverableService(self.db)._latest_version(task_id)
            if latest is not None:
                version_id = latest.id
                file_path = latest.file_path
                file_size = latest.file_size
                file_sha256 = latest.file_sha256
        await self.job_svc.finish_attempt_success(
            attempt_id,
            version_id=version_id,
            file_path=file_path,
            file_size=file_size,
            file_sha256=file_sha256,
        )

    def _step_for_key(self, step_key: str | None) -> TrioStep | None:
        """按稳定键取回权威 ``TrioStep``（含固定 sequence/doc_type/依赖）。"""
        if not step_key:
            return None
        for s in TRIO_STEPS:
            if s.key == step_key:
                return s
        return None

    async def retry_failed(
        self,
        job_id: UUID,
        *,
        user_id: UUID,
        requesting_project_id: UUID | None = None,
    ) -> "RetryOutcome":
        """真正重试失败步骤（design §7，需求 5.2–5.5）。

        流程：
          1. 校验 job 存在、（给定时）属于请求 project；
          2. 复算当前 snapshot digest，与 job 绑定快照比对 —— 不一致则**拒绝重试并
             要求新建 job**（``SnapshotMismatchError``），绝不混用新旧来源（需求 5.5）；
          3. 对每个 ``failed`` / ``blocked_by_dependency`` 的三件套 item，经共享单元
             ``_execute_step_in_savepoint(trigger="retry")`` 重新渲染/落盘/指纹/建版本
             并**新增 attempt**（保留原始失败 attempt，需求 5.4）；
          4. 已 ``succeeded`` 且文件指纹仍有效的正式项**复用**既有文件、**不重跑**
             导出器（需求 5.3）；指纹失效的成功项降级为需重试；
          5. 依赖项（audit_report）在前置重试成功后一并重试；
          6. 重算 job 状态与 trio 完成数（service 只 flush，router 统一 commit）。
        """
        job = await self.job_svc.get_job(job_id)
        if job is None:
            raise ValueError(f"任务不存在: {job_id}")
        if requesting_project_id is not None and job.project_id != requesting_project_id:
            raise ValueError("任务不属于该项目")

        snapshot_id = job.snapshot_id
        year = int((job.payload or {}).get("year") or 0)

        # ② 快照一致性复核（需求 5.5）：复算 digest，与 job 绑定快照比对。
        if snapshot_id and year:
            current_input = await self._build_snapshot_input(
                job.project_id, year, job.payload or {}
            )
            current_digest = build_digest(current_input)
            if current_digest != snapshot_id:
                raise SnapshotMismatchError(
                    "项目数据已变化，原交付快照不再有效；请重新发起一键出具（新建 job），"
                    "不得在旧快照上混用新数据重试",
                    job_snapshot=snapshot_id,
                    current_snapshot=current_digest,
                )

        items = await self.job_svc.get_job_items(job_id)
        succeeded_keys: set[str] = {
            it.step_key
            for it in items
            if it.step_key and it.status == ExportJobStatus.succeeded.value
        }

        retried = 0
        reused = 0
        outcomes: list[StepOutcome] = []

        # 按固定顺序重试（前置先于依赖项，保证 audit_report 能看到前置重试结果）。
        ordered = sorted(
            [it for it in items if it.step_key],
            key=lambda it: it.sequence or 0,
        )
        for item in ordered:
            step = self._step_for_key(item.step_key)
            if step is None:
                continue

            if item.status == ExportJobStatus.succeeded.value:
                # 已成功：复用前重新校验既有文件指纹（需求 5.3），通过则不重跑。
                if await self._succeeded_item_file_still_valid(item):
                    reused += 1
                    continue
                # 指纹失效 ⇒ 当作需重试项继续往下走。

            # 依赖阻断的 audit_report：前置仍未成功则维持阻断，不重跑导出器。
            unmet = [d for d in step.depends_on if d not in succeeded_keys]
            if unmet:
                reason = f"前置项未成功，依赖阻断：缺少 {', '.join(unmet)}"
                await self.job_svc.update_item_status(
                    item.id, BLOCKED_BY_DEPENDENCY, error_message=reason,
                )
                outcomes.append(
                    StepOutcome(
                        step.key, item.id, False,
                        error_message=reason,
                        status=BLOCKED_BY_DEPENDENCY,
                        sequence=step.sequence,
                    )
                )
                continue

            outcome = await self._execute_step_in_savepoint(
                job=job,
                item=item,
                step=step,
                project_id=job.project_id,
                year=year,
                user_id=user_id,
                payload=job.payload or {},
                snapshot_id=snapshot_id or "",
                trigger="retry",
            )
            outcomes.append(outcome)
            retried += 1
            if outcome.succeeded:
                succeeded_keys.add(step.key)

        # ⑥ 重算 job 状态与 trio 完成数（只统计正式三项）。
        await self._recompute_job_after_retry(job)

        return RetryOutcome(
            job_id=job_id,
            retried=retried,
            reused=reused,
            outcomes=outcomes,
            snapshot_id=snapshot_id,
        )

    async def _succeeded_item_file_still_valid(self, item: "ExportJobItem") -> bool:
        """已成功 item 的既有版本文件是否仍存在/可读/指纹一致（需求 5.3/5.5）。

        复用统一指纹入口 ``verify_file_fingerprint``；任一校验失败即判失效（需重试）。
        """
        from app.services.deliverable_file_fingerprint import (
            FileFingerprintError,
            verify_file_fingerprint,
        )

        file_path = item.file_path
        expected_sha = item.file_sha256
        expected_size = item.file_size
        # item 投影缺指纹时回退到最新成功版本（兼容 initial 未回填 item 指纹的历史数据）。
        if not file_path and item.word_export_task_id is not None:
            from app.services.deliverable_service import DeliverableService

            latest = await DeliverableService(self.db)._latest_version(
                item.word_export_task_id
            )
            if latest is not None:
                file_path = latest.file_path
                expected_sha = latest.file_sha256
                expected_size = latest.file_size
        if not file_path:
            return False
        try:
            verify_file_fingerprint(
                file_path,
                expected_sha256=expected_sha,
                expected_size=expected_size,
                enforce_root=False,
            )
            return True
        except FileFingerprintError:
            return False

    async def _recompute_job_after_retry(self, job: ExportJob) -> None:
        """重试后按正式三件套重算 job 进度/状态与 trio 完成数（需求 2.6/4.4）。"""
        from app.models.phase13_models import ExportJobItem

        trio_items = (
            await self.db.execute(
                sa.select(ExportJobItem).where(
                    ExportJobItem.job_id == job.id,
                    ExportJobItem.step_key.in_(TRIO_STEP_KEYS),
                )
            )
        ).scalars().all()
        done = sum(
            1 for it in trio_items
            if it.status == ExportJobStatus.succeeded.value
        )
        not_done = sum(
            1 for it in trio_items
            if it.status != ExportJobStatus.succeeded.value
        )
        await self.job_svc.update_progress(job.id, done=done, failed=not_done)
        job.trio_total = len(TRIO_STEPS)
        job.trio_succeeded = done
        await self.db.flush()

    async def _dispatch_trio_step(
        self,
        step: TrioStep,
        project_id: UUID,
        year: int,
        user_id: UUID,
        payload: dict,
    ) -> tuple[UUID | None, str | None, dict[str, bool] | None]:
        """按稳定键派发到对应渲染实现。返回 (task_id, kam_warning, resolved_opt)。

        稳定键 ``audit_report`` 复用现有 ``_run_report_body`` 渲染路径（内部产物 doc_type
        仍为 audit_report），不新造一套报告正文逻辑。
        """
        if step.key == "financial_report":
            task_id = await self._run_financial_reports(project_id, year, user_id)
            return task_id, None, None
        if step.key == "disclosure_notes":
            task_id = await self._run_disclosure_notes(project_id, year, user_id)
            return task_id, None, None
        if step.key == "audit_report":
            task_id, warning, resolved_opt = await self._run_report_body(
                project_id, year, user_id, payload
            )
            return task_id, warning, resolved_opt
        raise ValueError(f"未知三件套步骤: {step.key}")  # pragma: no cover

    async def _stamp_item_contract(
        self, item_id: UUID, step: TrioStep, snapshot_id: str
    ) -> None:
        """给 item 写入稳定键、固定顺序与共享快照（design §3.2）。"""
        from app.models.phase13_models import ExportJobItem

        item = await self.db.get(ExportJobItem, item_id)
        if item is not None:
            item.step_key = step.key
            item.sequence = step.sequence
            item.snapshot_id = snapshot_id
            await self.db.flush()

    async def _build_snapshot_input(
        self, project_id: UUID, year: int, payload: dict
    ) -> dict:
        """组装共享快照的内容输入（不含生成时间与绝对路径；digest 由 build_digest 计算）。

        绑定项目/年度/准则/模板/报表与附注的 snapshot refs。三件套三项据此共享同一 digest。
        """
        template_type = await self._project_template_type(project_id)
        report_scope = await self._project_report_scope(project_id)
        dsvc_refs: dict = {}
        try:
            from app.services.deliverable_service import DeliverableService

            dsvc = DeliverableService(self.db)
            for doc_type in (
                WordExportDocType.financial_report.value,
                WordExportDocType.disclosure_notes.value,
            ):
                dsvc_refs[doc_type] = await dsvc.capture_snapshot_refs(
                    project_id, year, doc_type
                )
        except Exception as exc:  # noqa: BLE001 — 快照 refs 捕获失败不应吞根因
            logger.warning("[TRIO] capture snapshot refs failed: %s", exc)
            dsvc_refs = {"_capture_error": str(exc)[:200]}
        return {
            "project_id": str(project_id),
            "year": year,
            "template_type": template_type,
            "report_scope": report_scope,
            "snapshot_refs": dsvc_refs,
        }

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
        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=buf.getvalue(),
            user_id=user_id,
            source_snapshot_refs=snapshot_refs,
            file_name=file_name,
        )
        # fail-closed（需求 3.1）：落盘/校验失败无成功版本 ⇒ 本步骤视为失败。
        if store.version is None:
            raise ValueError("审定财务报表落盘失败，未生成版本")
        await self._advance_to_editing(dsvc, task.id)
        return task.id

    async def _run_financial_reports_unadjusted(
        self, project_id: UUID, year: int, user_id: UUID
    ) -> UUID:
        """生成未审财务报表 xlsx 并落交付中心（doc_type=financial_report_unadjusted）。"""
        from app.services.deliverable_service import DeliverableService
        from app.services.report_excel_exporter import ReportExcelExporter

        dsvc = DeliverableService(self.db)
        task, _ = await dsvc.export_or_new_deliverable(
            project_id,
            WordExportDocType.financial_report_unadjusted.value,
            None,
            user_id,
        )
        await self.db.flush()

        exporter = ReportExcelExporter(self.db)
        buf = await exporter.export(project_id, year, mode="unadjusted")
        file_name = f"financial_reports_unadjusted_{year}.xlsx"
        snapshot_refs = await dsvc.capture_snapshot_refs(
            project_id,
            year,
            WordExportDocType.financial_report_unadjusted.value,
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
        """生成附注 Word 并落交付中心 + 落章节状态。

        导出模式跟随 ``settings.USE_TEMPLATE_FILL_SERVICE``（与 ``render_disclosure_notes``
        路由同一灰度开关）。此前本入口硬写 programmatic —— 那是 Phase 0.6.2 打标未完成
        期的遗留，导致「一键生成全套」与「单独生成附注」产出**两种排版**，且全套路径的
        附注永远没有 Section_Anchor（溯源/刷新/回填对它全部失效）。现统一为同一开关。
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
        # export_with_meta：拿章节级元数据落 deliverable_section_state（与
        # render_disclosure_notes 路由同款接线；需求 1.5 要求覆盖两条生产入口）
        from app.core.config import settings as _settings

        export_mode = (
            "template" if _settings.USE_TEMPLATE_FILL_SERVICE else "programmatic"
        )
        buf, note_meta = await exporter.export_with_meta(
            project_id,
            year,
            template_type=template_type,
            report_scope=normalize_report_scope(proj_scope),
            mode=export_mode,
            # 与路由一致：交付导出把残留公式串解析为静态值（Req 18.1/18.3 兜底守卫）
            flatten_formulas=True,
        )
        file_name = f"disclosure_notes_{year}.docx"
        snapshot_refs = await dsvc.capture_snapshot_refs(
            project_id, year, WordExportDocType.disclosure_notes.value
        )
        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=buf.getvalue(),
            user_id=user_id,
            source_snapshot_refs=snapshot_refs,
            file_name=file_name,
        )
        # fail-closed（需求 3.1）：落盘/校验失败无成功版本，本步骤视为失败。
        if store.version is None:
            raise ValueError("报表附注落盘失败，未生成版本")
        from app.services.deliverable_section_state_service import (
            persist_note_export_section_states,
        )

        await persist_note_export_section_states(
            self.db,
            word_export_task_id=task.id,
            project_id=project_id,
            year=year,
            meta=note_meta,
            version_no=store.version.version_no,
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
