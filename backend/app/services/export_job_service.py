"""导出后台任务编排 — Phase 13 Stage 2.5

管理长时间运行的导出任务（全套导出、批量渲染、失败重试）。
统一走 job_id，支持页面刷新恢复与失败项重试。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import (
    ExportJob,
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
)

logger = logging.getLogger(__name__)

#: attempt 的「终态」集合：一旦落到这些状态，记录即不可变（append-only，design §3.3）。
#: 对已终结 attempt 的任何二次写入都是「覆盖历史」违规，必须被 ``_ImmutableAttemptError`` 拒绝。
_ATTEMPT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {ExportJobStatus.succeeded.value, ExportJobStatus.failed.value}
)


class ImmutableAttemptError(RuntimeError):
    """试图覆盖一个已终结（succeeded/failed）的 attempt —— 违反 append-only 历史（design §3.3）。

    attempt 历史是不可变审计轨迹：失败 attempt 永不覆盖，重试只能**新增** attempt。
    任何对已终结 attempt 的二次 finish/改写都是「把多次尝试压成一个时间点」或「洗掉原始
    失败原因」的 bug，必须在服务边界抛出而非静默覆盖（需求 4.3/5.4）。
    """


class ExportJobService:
    """后台导出任务编排服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        project_id: UUID,
        job_type: str,
        payload: dict | None,
        user_id: UUID,
        total: int = 0,
    ) -> ExportJob:
        """创建后台导出任务

        Args:
            project_id: 项目ID
            job_type: 任务类型 (generate/full_package/retry)
            payload: 任务参数 (JSONB)
            user_id: 发起人ID
            total: 预计总项数
        """
        job = ExportJob(
            project_id=project_id,
            job_type=job_type,
            status=ExportJobStatus.queued.value,
            payload=payload or {},
            progress_total=total,
            progress_done=0,
            failed_count=0,
            initiated_by=user_id,
        )
        self.db.add(job)
        await self.db.flush()

        logger.info(
            "创建导出任务: job_id=%s, type=%s, project=%s",
            job.id, job_type, project_id,
        )
        return job

    async def get_job(self, job_id: UUID) -> ExportJob | None:
        """获取任务详情（含明细项）"""
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job_items(self, job_id: UUID) -> list[ExportJobItem]:
        """获取任务明细项列表"""
        result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == job_id)
            .order_by(ExportJobItem.finished_at.asc().nullsfirst())
        )
        return list(result.scalars().all())

    async def get_job_item(self, item_id: UUID) -> ExportJobItem | None:
        """按主键获取单个明细项（下载端点用）。

        ``ExportJobItem`` 本身不带 ``project_id`` —— 项目归属在 ``ExportJob`` 上。
        下载端点必须经本方法取到 item 后，再用 ``item.job_id`` 反查 job 校验归属
        （铁律㉗：路径里的 project_id 不是隔离，数据层必须真的按它过滤）。
        """
        result = await self.db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def add_item(
        self,
        job_id: UUID,
        word_export_task_id: UUID | None = None,
    ) -> ExportJobItem:
        """添加任务明细项"""
        item = ExportJobItem(
            job_id=job_id,
            word_export_task_id=word_export_task_id,
            status=ExportJobStatus.queued.value,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def update_item_status(
        self,
        item_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> ExportJobItem | None:
        """更新明细项状态"""
        result = await self.db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None

        item.status = status
        if error_message:
            item.error_message = error_message
        if status in (
            ExportJobStatus.succeeded.value,
            ExportJobStatus.failed.value,
        ):
            item.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return item

    # ------------------------------------------------------------------
    # attempt append-only 历史（phase4 Task 6/7，design §3.3）
    # ------------------------------------------------------------------
    async def start_attempt(
        self,
        job_id: UUID,
        item_id: UUID,
        *,
        snapshot_id: str | None = None,
        trigger: str = "initial",
        created_by: UUID | None = None,
    ) -> ExportJobAttempt:
        """为某 item 新建一次尝试记录（append-only，``attempt_no`` 单调递增）。

        **必须在步骤的 savepoint 之外调用**：attempt 是失败留痕的载体，不能与被回滚的
        业务写入共享回滚边界（design §6）。``attempt_no`` 从该 item 现有最大值 +1。
        """
        current_max = (
            await self.db.execute(
                sa.select(sa.func.max(ExportJobAttempt.attempt_no)).where(
                    ExportJobAttempt.item_id == item_id
                )
            )
        ).scalar_one_or_none()
        next_no = (current_max or 0) + 1
        attempt = ExportJobAttempt(
            job_id=job_id,
            item_id=item_id,
            attempt_no=next_no,
            status=ExportJobStatus.running.value,
            trigger=trigger,
            snapshot_id=snapshot_id,
            created_by=created_by,
        )
        self.db.add(attempt)
        await self.db.flush()

        # item 的当前投影：尝试计数 + 最近 attempt 指针
        item = await self.db.get(ExportJobItem, item_id)
        if item is not None:
            item.attempt_count = next_no
            item.last_attempt_id = attempt.id
            await self.db.flush()
        return attempt

    async def finish_attempt_success(
        self,
        attempt_id: UUID,
        *,
        version_id: UUID | None = None,
        file_path: str | None = None,
        file_size: int | None = None,
        file_sha256: str | None = None,
    ) -> None:
        """标记一次尝试成功，并记录版本/文件指纹投影。

        append-only 守护：若该 attempt 已终结（succeeded/failed），拒绝二次写入
        （``ImmutableAttemptError``），杜绝覆盖历史（design §3.3，需求 4.3/5.4）。
        """
        attempt = await self.db.get(ExportJobAttempt, attempt_id)
        if attempt is None:
            return
        self._assert_attempt_mutable(attempt)
        attempt.status = ExportJobStatus.succeeded.value
        attempt.finished_at = datetime.now(timezone.utc)
        if version_id is not None:
            attempt.version_id = version_id
        if file_path is not None:
            attempt.file_path = file_path
        if file_size is not None:
            attempt.file_size = file_size
        if file_sha256 is not None:
            attempt.file_sha256 = file_sha256
        await self.db.flush()

    async def finish_attempt_failed(
        self,
        attempt_id: UUID,
        exc: BaseException,
        *,
        user_message: str | None = None,
        diagnostic_detail: dict | None = None,
    ) -> None:
        """标记一次尝试失败，保存原始异常类型/中文消息/诊断细节（append-only，永不覆盖）。

        **必须在步骤 savepoint 回滚之后调用**，否则失败留痕会随业务写入一起被回滚。

        append-only 守护：若该 attempt 已终结，拒绝二次写入（``ImmutableAttemptError``），
        保留原始失败原因不被后来的尝试洗掉（design §3.3，需求 4.3/5.4）。
        """
        attempt = await self.db.get(ExportJobAttempt, attempt_id)
        if attempt is None:
            return
        self._assert_attempt_mutable(attempt)
        attempt.status = ExportJobStatus.failed.value
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.error_type = type(exc).__name__
        attempt.error_message = (user_message or str(exc))[:2000]
        if diagnostic_detail is not None:
            attempt.diagnostic_detail = diagnostic_detail
        await self.db.flush()

    @staticmethod
    def _assert_attempt_mutable(attempt: ExportJobAttempt) -> None:
        """append-only 守护：已终结 attempt 不得再被改写（design §3.3）。"""
        if attempt.status in _ATTEMPT_TERMINAL_STATUSES:
            raise ImmutableAttemptError(
                f"attempt {attempt.id}（item={attempt.item_id} 第 {attempt.attempt_no} 次尝试）"
                f"已处于终态 {attempt.status!r}，不可覆盖历史；重试请新增 attempt"
            )

    # ------------------------------------------------------------------
    # attempt 历史查询（append-only；design §3.3，需求 4.3/5.4）
    # ------------------------------------------------------------------
    async def get_item_attempts(self, item_id: UUID) -> list[ExportJobAttempt]:
        """返回某 item 的**完整**尝试历史，按 ``attempt_no`` 升序（单调编号）。

        这是不可变审计轨迹：原始失败 attempt 与后续重试 attempt 都在列表里，
        前端刷新 job 不得用空数组覆盖（design §7 末段）。
        """
        result = await self.db.execute(
            sa.select(ExportJobAttempt)
            .where(ExportJobAttempt.item_id == item_id)
            .order_by(ExportJobAttempt.attempt_no.asc())
        )
        return list(result.scalars().all())

    async def get_job_attempts(self, job_id: UUID) -> list[ExportJobAttempt]:
        """返回整个 job 的完整尝试历史，按 (item_id, attempt_no) 稳定排序。"""
        result = await self.db.execute(
            sa.select(ExportJobAttempt)
            .where(ExportJobAttempt.job_id == job_id)
            .order_by(
                ExportJobAttempt.item_id.asc(),
                ExportJobAttempt.attempt_no.asc(),
            )
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 中断/超时恢复：fail-closed（需求 4.6）
    # ------------------------------------------------------------------
    async def recover_orphaned_running(
        self,
        job_id: UUID,
        *,
        reason: str = "进程中断/超时：该尝试在运行中未收到结束信号，已按失败处理，可重试",
    ) -> int:
        """把因进程中断/超时而**遗留在 ``running``** 的 attempt 与 item 收敛为失败（fail-closed）。

        需求 4.6：取消/超时/进程中断后，下一次查询必须能发现未完成 attempt，**绝不**把
        ``running`` 永久显示为成功。恢复策略是 fail-closed——

        - 遗留的 running attempt 一律标 ``failed`` 并写入 ``error_type='Interrupted'`` + 中文
          诊断，**保留** 原有 ``attempt_no`` 与开始时间（append-only，不新增、不改写已终结项）；
        - 对应 item 若仍是 ``running``/``queued`` 则标 ``failed``，让前端把它作为「需要关注/
          可重试」呈现，而不是悬在成功态；
        - 决不执行 ``running → succeeded`` 的乐观收尾。

        返回被恢复（标失败）的 running attempt 数。service 只 flush，由 router/编排统一 commit。
        """
        running_attempts = (
            await self.db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.job_id == job_id,
                    ExportJobAttempt.status == ExportJobStatus.running.value,
                )
            )
        ).scalars().all()

        recovered = 0
        for attempt in running_attempts:
            # 直接改写——此处 attempt 尚未终结（running），不触发 append-only 守护。
            attempt.status = ExportJobStatus.failed.value
            attempt.finished_at = datetime.now(timezone.utc)
            attempt.error_type = attempt.error_type or "Interrupted"
            attempt.error_message = attempt.error_message or reason
            detail = dict(attempt.diagnostic_detail or {})
            detail["recovered_from_running"] = True
            attempt.diagnostic_detail = detail

            # item 投影 fail-closed：running/queued ⇒ failed（绝不收成功）。
            item = await self.db.get(ExportJobItem, attempt.item_id)
            if item is not None and item.status in (
                ExportJobStatus.running.value,
                ExportJobStatus.queued.value,
            ):
                item.status = ExportJobStatus.failed.value
                if not item.error_message:
                    item.error_message = reason
                if item.finished_at is None:
                    item.finished_at = datetime.now(timezone.utc)
            recovered += 1

        if recovered:
            await self.db.flush()
            logger.warning(
                "[RECOVERY] 中断恢复 fail-closed: job=%s 将 %d 个遗留 running attempt 标失败",
                job_id, recovered,
            )
        return recovered

    async def update_progress(
        self,
        job_id: UUID,
        done: int,
        failed: int = 0,
    ) -> ExportJob | None:
        """更新任务进度

        Args:
            job_id: 任务ID
            done: 已完成数
            failed: 失败数
        """
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.progress_done = done
        job.failed_count = failed

        # Auto-determine job status
        if done + failed >= job.progress_total and job.progress_total > 0:
            if failed == 0:
                job.status = ExportJobStatus.succeeded.value
            elif done > 0:
                job.status = ExportJobStatus.partial_failed.value
            else:
                job.status = ExportJobStatus.failed.value

            # ── Phase 16: 导出完成后自动生成取证包 hash ──
            if job.status == ExportJobStatus.succeeded.value:
                try:
                    from app.services.export_integrity_service import export_integrity_service
                    from pathlib import Path
                    import glob
                    # 查找导出文件
                    export_dir = Path("storage") / "exports" / str(job_id)
                    if export_dir.exists():
                        files = [str(f) for f in export_dir.rglob("*") if f.is_file()]
                        if files:
                            manifest = await export_integrity_service.build_manifest(str(job_id), files)
                            await export_integrity_service.persist_checks(self.db, str(job_id), manifest["files"])
                            logger.info(f"[INTEGRITY] export hash generated: job={job_id} files={len(files)}")
                except Exception as _int_err:
                    logger.warning(f"[INTEGRITY] export hash generation failed: {_int_err}")

        elif done > 0 or failed > 0:
            job.status = ExportJobStatus.running.value

        await self.db.flush()
        logger.info(
            "导出任务进度: job_id=%s, done=%d/%d, failed=%d",
            job_id, done, job.progress_total, failed,
        )
        return job

    async def retry_failed(
        self,
        job_id: UUID,
        *,
        user_id: UUID | None = None,
        requesting_project_id: UUID | None = None,
    ) -> int:
        """真正重试失败项（phase4 Task 8，design §7，需求 5.2–5.5）。

        **不再是**「只把状态改回 queued、清空 error_message」的 fail-open 旧实现——
        那种实现既不重跑步骤、也不新增 attempt、还洗掉了原始失败原因。现在：

        1. **保留原始失败原因**（需求 5.4）：失败项若尚无 attempt 记录（历史数据或经
           ``update_item_status`` 直接置失败），先按原始 ``error_message`` **补记**一条
           已终结的失败 attempt，使重试后历史里仍能查到原始失败原因（append-only）。
        2. **真正重跑**（需求 5.2）：对**正式三件套** item（有 ``step_key`` 且 job 绑定了
           快照），委托 ``FullDeliverablesExecutor.retry_failed`` 经同一渲染/落盘/指纹/
           版本路径重执行，并为每次重试**新增 attempt**（``trigger="retry"``，attempt_no
           单调递增）。已成功且指纹有效的项复用既有文件、不重跑（需求 5.3）；若 job 绑定
           快照已与当前项目数据不一致，executor 抛 ``SnapshotMismatchError``，由上层映射为
           冲突/新建 job（需求 5.5），绝不混用快照。
        3. **非三件套 item**（无 ``step_key``，如旧 ``full_package``/批量渲染明细）没有可
           重跑的步骤入口 —— 为其**新增一条 retry attempt** 记录重试意图并复位为 queued，
           供既有后台渲染路径继续处理；原始失败原因已在第 1 步保留。

        返回「本次识别并处理的失败项数」。service 只 flush，由 router 统一 commit。
        """
        failed_items = (
            await self.db.execute(
                sa.select(ExportJobItem).where(
                    ExportJobItem.job_id == job_id,
                    ExportJobItem.status.in_(
                        (
                            ExportJobStatus.failed.value,
                            "blocked_by_dependency",
                        )
                    ),
                )
            )
        ).scalars().all()

        if not failed_items:
            logger.info("重试失败项: job_id=%s, 无失败项", job_id)
            return 0

        # ① 补记原始失败 attempt，保留原始失败原因（需求 5.4，append-only）。
        for item in failed_items:
            await self._ensure_original_failure_attempt(job_id, item)

        trio_items = [it for it in failed_items if it.step_key]
        generic_items = [it for it in failed_items if not it.step_key]

        processed = 0

        # ② 正式三件套：委托 executor 真正重跑（新增 retry attempt + 重渲染/落盘/建版本）。
        if trio_items:
            job = await self.get_job(job_id)
            if job is not None and job.snapshot_id:
                from app.services.full_deliverables_executor import (
                    FullDeliverablesExecutor,
                )

                executor = FullDeliverablesExecutor(self.db)
                retry_user = user_id or job.initiated_by
                result = await executor.retry_failed(
                    job_id,
                    user_id=retry_user,
                    requesting_project_id=requesting_project_id,
                )
                # executor 已重算 job 状态/trio 完成数；processed 计入被处理的三件套项。
                processed += result.retried
            else:
                # 无快照绑定的三件套 item 无法安全重跑（缺共享快照，需求 2.4）；
                # 退化为通用项处理（新增 retry attempt + 复位 queued）。
                generic_items.extend(trio_items)
                trio_items = []

        # ③ 非三件套 item：新增 retry attempt 并复位 queued（无专用步骤入口可重跑）。
        for item in generic_items:
            await self.start_attempt(
                job_id, item.id, snapshot_id=None, trigger="retry",
            )
            item.status = ExportJobStatus.queued.value
            item.error_message = None
            item.finished_at = None
            processed += 1

        if generic_items:
            # 仅通用项路径需在此复位 job（三件套路径已由 executor 重算 job 状态）。
            job = await self.get_job(job_id)
            if job is not None:
                job.status = ExportJobStatus.running.value
                job.failed_count = max(0, job.failed_count - len(generic_items))
                job.progress_done = max(
                    0, job.progress_done - len(generic_items)
                )
            await self.db.flush()

        logger.info("重试失败项: job_id=%s, processed=%d", job_id, processed)
        return processed

    async def _ensure_original_failure_attempt(
        self, job_id: UUID, item: ExportJobItem
    ) -> None:
        """失败项若尚无任何 attempt，则按其 ``error_message`` 补记一条终结失败 attempt。

        这保证「原始失败原因」在重试新增 attempt **之前**就已固化进 append-only 历史
        （需求 5.4）。若该 item 已有 attempt（executor initial 路径已开过），不重复补记——
        原始失败 attempt 已存在。
        """
        existing = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(ExportJobAttempt)
                .where(ExportJobAttempt.item_id == item.id)
            )
        ).scalar_one()
        if existing and existing > 0:
            return

        attempt = ExportJobAttempt(
            job_id=job_id,
            item_id=item.id,
            attempt_no=1,
            status=ExportJobStatus.failed.value,
            trigger="initial",
            snapshot_id=item.snapshot_id,
            error_type="OriginalFailure",
            error_message=(item.error_message or "原始失败（原因未记录）")[:2000],
            diagnostic_detail={"synthesized_from_item": True},
            finished_at=item.finished_at or datetime.now(timezone.utc),
        )
        self.db.add(attempt)
        await self.db.flush()
        # 更新 item 的 attempt 投影，使后续 start_attempt 的 attempt_no 从 2 起。
        item.attempt_count = max(item.attempt_count or 0, 1)
        item.last_attempt_id = attempt.id
        await self.db.flush()
