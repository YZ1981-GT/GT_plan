"""交付物服务 — 扩展 ExportTaskService，交付中心 CRUD + 版本 + 双路径存储"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport, ReportStatus
from app.services.export_task_service import ExportTaskService
from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.completeness_service import CompletenessService
from app.services.deliverable_capabilities import (
    supports_section_refresh,
    supports_writeback,
)
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.deliverable_snapshot_service import DeliverableSnapshotService

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))
DELIVERABLE_SUBDIR = "deliverables"

TERMINAL_REEXPORT_STATUSES = {"confirmed", "signed", "archived"}


@dataclass
class DeliverableDTO:
    task_id: UUID
    project_id: UUID
    doc_type: str
    status: str
    file_name: str | None
    version_no: int
    file_size: int | None
    exporter_name: str | None
    exported_at: datetime | None
    template_type: str | None
    selected_sections: list | None
    #: 能力标志（需求 6.5）：由 deliverable_capabilities 单一真源派生，供前端门控
    supports_writeback: bool = False
    supports_section_refresh: bool = False
    #: 报表差异告警（需求 10.3）：由 should_block_confirm **唯一入口**判定。
    #: 放在列表 DTO 而非只放版本链 —— 「数字与试算表不符」是阻断 confirmed 的信号，
    #: 藏在「更多 ▾ → 版本链」里等于要用户先怀疑再去查。列表循环本就取了最新版本
    #: 对象，读它的 drift_report 是**零额外查询**。
    drift_blocked: bool = False
    drift_reason: str | None = None


@dataclass
class StoreResult:
    version: WordExportTaskVersion
    download_url: str
    platform_persist_failed: bool = False
    file_path: str | None = None
    html_path: str | None = None


@dataclass
class VersionCompareResult:
    version_a: int
    version_b: int
    exported_at_diff: dict | None
    file_size_diff: dict | None
    selected_sections_diff: dict | None


class DeliverableService(ExportTaskService):
    """交付物维度服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _deliverable_dir(self, project_id: UUID, task_id: UUID) -> Path:
        return STORAGE_ROOT / DELIVERABLE_SUBDIR / str(project_id) / str(task_id)

    async def _latest_version(self, task_id: UUID) -> WordExportTaskVersion | None:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion)
            .where(WordExportTaskVersion.word_export_task_id == task_id)
            .order_by(WordExportTaskVersion.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_version_chain(self, task_id: UUID) -> list[WordExportTaskVersion]:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion)
            .where(WordExportTaskVersion.word_export_task_id == task_id)
            .order_by(
                WordExportTaskVersion.created_at.desc(),
                WordExportTaskVersion.version_no.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_version_chain_view(self, task_id: UUID) -> list[dict]:
        """版本链 + 派生展示字段（需求 11.1 / 11.2 / 10.3）。

        在 ORM 行之外补三类**只能在后端算**的字段，避免前端各拼一份：

        - ``bound_tb_hash`` / ``is_stale``：该版绑定的试算表快照，以及它是否已与
          交付件当前绑定不同。``is_stale`` 用 **三态** —— 任一侧 hash 缺失时返
          ``None``（未知），**不返 False**，否则历史版本会一律显示成"最新"骗人。
        - ``edited_by_name``：实际编辑人用户名（V142 的 ``edited_by``；OO 路径下
          ``created_by`` 只是回调处理占位，展示链路一律读 ``edited_by``）。
        - ``drift_blocked`` / ``drift_reason``：由 ``should_block_confirm`` **唯一入口**
          判定，前端不得自己写 `if drift_report:`。
        """
        from app.services.financial_report_drift_service import should_block_confirm

        task = await self.get_task(task_id)
        task_refs = (
            task.source_snapshot_refs
            if task is not None and isinstance(task.source_snapshot_refs, dict)
            else {}
        )
        task_tb_hash = task_refs.get("tb_hash")

        rows = (
            await self.db.execute(
                sa.select(WordExportTaskVersion, User.username)
                .outerjoin(User, User.id == WordExportTaskVersion.edited_by)
                .where(WordExportTaskVersion.word_export_task_id == task_id)
                .order_by(
                    WordExportTaskVersion.created_at.desc(),
                    WordExportTaskVersion.version_no.desc(),
                )
            )
        ).all()

        out: list[dict] = []
        for version, edited_by_name in rows:
            refs = (
                version.source_snapshot_refs
                if isinstance(version.source_snapshot_refs, dict)
                else {}
            )
            bound = refs.get("tb_hash")
            is_stale: bool | None = None
            if bound and task_tb_hash:
                is_stale = bound != task_tb_hash
            blocked, reason = should_block_confirm(version.drift_report)
            out.append(
                {
                    "id": version.id,
                    "word_export_task_id": version.word_export_task_id,
                    "version_no": version.version_no,
                    "file_path": version.file_path,
                    "html_path": version.html_path,
                    "file_size": version.file_size,
                    "created_by": version.created_by,
                    "created_at": version.created_at,
                    "selected_sections": version.selected_sections,
                    "created_via": version.created_via,
                    "edited_by": version.edited_by,
                    "edited_at": version.edited_at,
                    "edited_by_name": edited_by_name,
                    "bound_tb_hash": bound,
                    "is_stale": is_stale,
                    "drift_report": version.drift_report,
                    "drift_blocked": blocked,
                    "drift_reason": reason,
                }
            )
        return out

    async def get_version(
        self, task_id: UUID, version_no: int
    ) -> WordExportTaskVersion | None:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task_id,
                WordExportTaskVersion.version_no == version_no,
            )
        )
        return result.scalar_one_or_none()

    async def delete_task(self, task_id: UUID) -> None:
        """删除交付物及其所有版本（仅 draft/editing/generated 态可删）"""
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status in ("confirmed", "signed", "archived"):
            raise ValueError("已确认/已签章/已归档的交付物不可删除")
        # 清理关联的 export_job_items_v2（FK 约束）
        from app.models.phase13_models import ExportJobItem
        await self.db.execute(
            sa.delete(ExportJobItem).where(
                ExportJobItem.word_export_task_id == task_id
            )
        )
        # 清理 deliverable_section_state
        from app.models.audit_platform_models import DeliverableSectionState
        await self.db.execute(
            sa.delete(DeliverableSectionState).where(
                DeliverableSectionState.word_export_task_id == task_id
            )
        )
        # 删除版本记录
        await self.db.execute(
            sa.delete(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task_id
            )
        )
        # 删除主记录
        await self.db.execute(
            sa.delete(WordExportTask).where(WordExportTask.id == task_id)
        )
        await self.db.flush()

    async def create_version(
        self,
        task_id: UUID,
        *,
        file_path: str | None,
        html_path: str | None,
        user_id: UUID,
        source_snapshot_refs: dict | None = None,
        selected_sections: list | None = None,
        file_size: int | None = None,
        created_via: str = "generate",
        edited_by: UUID | None = None,
        edited_at: datetime | None = None,
    ) -> WordExportTaskVersion:
        # 归档锁定不变式（需求 11.2 / Property 24）：archived 态禁止创建新版本
        task = await self.get_task(task_id)
        if task is not None and task.status == WordExportStatus.archived.value:
            raise ValueError(
                f"交付物已归档，禁止创建新版本: task_id={task_id}"
            )

        result = await self.db.execute(
            sa.select(sa.func.coalesce(sa.func.max(WordExportTaskVersion.version_no), 0))
            .where(WordExportTaskVersion.word_export_task_id == task_id)
        )
        max_no = int(result.scalar_one() or 0)
        version_no = max_no + 1

        version = WordExportTaskVersion(
            word_export_task_id=task_id,
            version_no=version_no,
            file_path=file_path,
            html_path=html_path,
            file_size=file_size,
            created_by=user_id,
            source_snapshot_refs=source_snapshot_refs,
            selected_sections=selected_sections,
            created_via=created_via,
            edited_by=edited_by,
            edited_at=edited_at,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def export_or_new_deliverable(
        self,
        project_id: UUID,
        doc_type: str,
        template_type: str | None,
        user_id: UUID,
        *,
        existing_task_id: UUID | None = None,
    ) -> tuple[WordExportTask, bool]:
        """终态再导出 → 新建独立交付物；否则复用/追加版本"""
        if existing_task_id:
            task = await self.get_task(existing_task_id)
            if task and task.status in TERMINAL_REEXPORT_STATUSES:
                task = await self.create_task(project_id, doc_type, template_type, user_id)
                return task, True
            if task:
                return task, False

        history = await self.get_history(project_id)
        same_type = [t for t in history if t.doc_type == doc_type]
        if same_type and same_type[0].status in TERMINAL_REEXPORT_STATUSES:
            task = await self.create_task(project_id, doc_type, template_type, user_id)
            return task, True
        if same_type:
            return same_type[0], False

        task = await self.create_task(project_id, doc_type, template_type, user_id)
        return task, True

    async def compare_versions(
        self, task_id: UUID, version_a: int, version_b: int
    ) -> VersionCompareResult:
        va = await self.get_version(task_id, version_a)
        vb = await self.get_version(task_id, version_b)
        if va is None or vb is None:
            raise ValueError("版本不存在")

        if version_a == version_b:
            return VersionCompareResult(version_a, version_b, None, None, None)

        def _diff(field_a, field_b, name: str) -> dict | None:
            if field_a == field_b:
                return None
            return {name: {"a": field_a, "b": field_b}}

        return VersionCompareResult(
            version_a=version_a,
            version_b=version_b,
            exported_at_diff=_diff(va.created_at, vb.created_at, "exported_at"),
            file_size_diff=_diff(va.file_size, vb.file_size, "file_size"),
            selected_sections_diff=_diff(va.selected_sections, vb.selected_sections, "selected_sections"),
        )

    async def capture_snapshot_refs(
        self, project_id: UUID, year: int, doc_type: str = "audit_report"
    ) -> dict:
        snap_svc = DeliverableSnapshotService(self.db)
        return await snap_svc.capture_snapshot_refs(project_id, year, doc_type)

    async def _assert_eqcr_passed(self, project_id: UUID, year: int) -> None:
        result = await self.db.execute(
            sa.select(AuditReport.status).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
            )
        )
        status = result.scalar_one_or_none()
        allowed = {ReportStatus.eqcr_approved.value, ReportStatus.final.value}
        if status not in allowed:
            raise ValueError("需先完成 EQCR 复核")

    async def _assert_no_report_drift(self, task_id: UUID) -> None:
        """财务报表 xlsx 若被手工改过数字则拒绝确认（需求 10.4 / 10.6 / 10.8）。

        判定**唯一入口**是 ``should_block_confirm`` —— 它区分三态：
        ``None``（未配映射）放行 / ``{"unavailable":…}``（检测不可用）阻断 /
        ``{"diffs":[…]}`` 非空阻断、空数组放行。

        🔴 禁止在此写 ``if version.drift_report:`` —— ``{"diffs": []}`` 是非空 dict
        但表示「已比对且一致」，那样写会让每个配了映射的报表永远确认不了。

        fail-open 边界：读不到最新版本时不阻断（该交付件可能尚无版本），
        但**检测结果本身**若为「不可用」则必须阻断（配置坏了不得放行）。
        """
        from app.services.financial_report_drift_service import should_block_confirm

        latest = await self._latest_version(task_id)
        if latest is None:
            return
        blocked, reason = should_block_confirm(latest.drift_report)
        if blocked:
            logger.warning(
                "confirm 被差异检测阻断: task=%s v%s reason=%s",
                task_id,
                latest.version_no,
                reason,
            )
            raise ValueError(reason or "报表存在手工改动，不可确认")

    async def confirm_deliverable(
        self, task_id: UUID, user_id: UUID, year: int
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        await self._assert_eqcr_passed(task.project_id, year)
        await self._assert_no_report_drift(task_id)
        return await self.confirm_task(task_id, user_id)

    async def sign(
        self,
        task_id: UUID,
        signer_id: UUID,
        sign_type: str,
        year: int,
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")

        await self._assert_eqcr_passed(task.project_id, year)

        if task.status != WordExportStatus.confirmed.value:
            raise ValueError(
                f"仅 confirmed 状态可签章，当前状态: {task.status}"
            )

        await self.update_status(task_id, WordExportStatus.signed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.signed_by = signer_id
        task.signed_at = datetime.now(timezone.utc)
        task.sign_type = sign_type
        await self.db.flush()
        logger.info(
            "交付物已签章: task_id=%s, signer=%s, sign_type=%s",
            task_id,
            signer_id,
            sign_type,
        )
        return task

    async def render_and_store(
        self,
        task_id: UUID,
        *,
        docx_bytes: bytes | None = None,
        docx_path: Path | None = None,
        html_content: str | None = None,
        user_id: UUID,
        source_snapshot_refs: dict | None = None,
        selected_sections: list | None = None,
        file_name: str | None = None,
        created_via: str = "generate",
        inherit_snapshot_refs: bool = False,
        edited_by: UUID | None = None,
        edited_at: datetime | None = None,
    ) -> StoreResult:
        """落盘一个新版本。

        Args:
            inherit_snapshot_refs: 为 True 时**继承上一版**的 ``source_snapshot_refs``
                并且**不覆盖** ``task.source_snapshot_refs``（需求 7.1）。

                为什么必须有这个开关：OO 在线编辑保存产生的新版本，其内容并未按新的
                试算表重算，只是人工改了文字。若像历史实现那样重新
                ``capture_snapshot_refs()`` 拿**当前** tb_hash 并赋给 task，
                则「试算表已变、交付件本该 stale」的状态会被一次错别字修改洗白 ——
                `check_stale` / `check_trio_consistency` 双双转绿而内容其实过期。
                故 OO 路径必须锁定「生成时快照」作为 stale 判定基准。

            edited_by / edited_at: 实际编辑人与编辑时间（需求 7.2/7.3）。
                解析不出时传 None（如实记为未知），**禁止**回退 ``task.created_by``。

        三个参数均为 additive，默认值 ⇒ 与引入前逐字节等价。
        """
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")

        if inherit_snapshot_refs:
            prev = await self._latest_version(task_id)
            inherited = prev.source_snapshot_refs if prev is not None else None
            if inherited is None:
                # 上一版也没有绑定（历史数据），退回 task 级；仍不主动捕获当前快照
                inherited = task.source_snapshot_refs
            source_snapshot_refs = inherited

        out_dir = self._deliverable_dir(task.project_id, task_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        latest = await self._latest_version(task_id)
        next_no = (latest.version_no + 1) if latest else 1

        ext = ".docx"
        fname = file_name or f"{task.doc_type}_v{next_no}{ext}"
        file_path = out_dir / fname
        html_path = out_dir / f"{task.doc_type}_v{next_no}.html"

        platform_persist_failed = False
        try:
            if docx_path and docx_path.exists():
                file_path.write_bytes(docx_path.read_bytes())
            elif docx_bytes:
                file_path.write_bytes(docx_bytes)
            else:
                raise ValueError("无文件内容可存储")

            if html_content:
                html_path.write_text(html_content, encoding="utf-8")
            file_size = file_path.stat().st_size
        except Exception as exc:
            logger.error("平台存储写入失败 task=%s: %s", task_id, exc)
            platform_persist_failed = True
            file_size = len(docx_bytes) if docx_bytes else 0
            file_path = None
            html_path = None

        version = await self.create_version(
            task_id,
            file_path=str(file_path) if file_path else None,
            html_path=str(html_path) if html_path and html_path.exists() else None,
            user_id=user_id,
            source_snapshot_refs=source_snapshot_refs,
            selected_sections=selected_sections,
            file_size=file_size if not platform_persist_failed else None,
            created_via=created_via,
            edited_by=edited_by,
            edited_at=edited_at,
        )

        if not platform_persist_failed and file_path and file_path.exists():
            await DeliverableHashService(self.db).bind_version_hash(
                version, task, user_id
            )

        if not platform_persist_failed:
            task.file_path = str(file_path)
            task.html_path = str(html_path) if html_path and html_path.exists() else None
            task.file_size = file_size
            # 需求 7.1：继承模式下**不覆盖** task 级快照绑定。
            # 覆盖会让 stale 判定基准漂移到「最后一次人工编辑的时刻」，
            # 而该版本内容并未按当时的试算表重算 → staleness 被静默洗白。
            if not inherit_snapshot_refs:
                task.source_snapshot_refs = source_snapshot_refs
            task.selected_sections = selected_sections
            # 渲染完成并落盘 → 交付物进入 generated 态。
            # 既覆盖 draft 直接生成，也覆盖经 generating 中间态的标准渲染流程
            # （draft→generating→generated→editing），避免任务卡在 generating。
            if task.status in (
                WordExportStatus.draft.value,
                WordExportStatus.generating.value,
            ):
                task.status = WordExportStatus.generated.value
            await self.db.flush()

        download_url = f"/api/projects/{task.project_id}/deliverables/{task_id}/versions/{version.version_no}/download"
        return StoreResult(
            version=version,
            download_url=download_url,
            platform_persist_failed=platform_persist_failed,
            file_path=str(file_path) if file_path else None,
            html_path=str(html_path) if html_path and html_path.exists() else None,
        )

    async def list_deliverables(
        self,
        project_id: UUID,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        keyword: str | None = None,
    ) -> list[DeliverableDTO]:
        query = (
            sa.select(WordExportTask, User.username)
            .outerjoin(User, User.id == WordExportTask.created_by)
            .where(WordExportTask.project_id == project_id)
        )

        if doc_type:
            query = query.where(WordExportTask.doc_type == doc_type)
        if status:
            query = query.where(WordExportTask.status == status)
        if date_from:
            query = query.where(WordExportTask.created_at >= date_from)
        if date_to:
            query = query.where(WordExportTask.created_at <= date_to)

        result = await self.db.execute(query.order_by(WordExportTask.created_at.desc()))
        rows = result.all()

        dtos: list[DeliverableDTO] = []
        for task, exporter_name in rows:
            version = await self._latest_version(task.id)
            file_name = None
            if task.file_path:
                file_name = Path(task.file_path).name
            elif version and version.file_path:
                file_name = Path(version.file_path).name

            if keyword:
                kw = keyword.lower()
                name_match = file_name and kw in file_name.lower()
                exporter_match = exporter_name and kw in exporter_name.lower()
                if not name_match and not exporter_match:
                    continue

            # 需求 10.3：列表行即可见「数字与重算值不一致」。判定走唯一入口
            # should_block_confirm（禁写 `if version.drift_report:` —— `{"diffs": []}`
            # 是非空 dict 但表示已比对且一致）。
            from app.services.financial_report_drift_service import (
                should_block_confirm,
            )

            drift_blocked, drift_reason = should_block_confirm(
                version.drift_report if version is not None else None
            )

            dtos.append(
                DeliverableDTO(
                    task_id=task.id,
                    project_id=task.project_id,
                    doc_type=task.doc_type,
                    status=task.status,
                    file_name=file_name,
                    version_no=version.version_no if version else 1,
                    file_size=task.file_size or (version.file_size if version else None),
                    exporter_name=exporter_name,
                    exported_at=task.updated_at or task.created_at,
                    template_type=task.template_type,
                    selected_sections=task.selected_sections,
                    supports_writeback=supports_writeback(task.doc_type),
                    supports_section_refresh=supports_section_refresh(task.doc_type),
                    drift_blocked=drift_blocked,
                    drift_reason=drift_reason,
                )
            )
        return dtos

    async def submit_for_approval(
        self, task_id: UUID, user_id: UUID
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.editing.value:
            raise ValueError(f"仅 editing 状态可提交审批，当前: {task.status}")
        return await self.update_status(
            task_id, WordExportStatus.pending_approval.value
        )

    async def approve(
        self, task_id: UUID, approver_id: UUID, year: int
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.pending_approval.value:
            raise ValueError(
                f"仅 pending_approval 状态可批准，当前: {task.status}"
            )
        await self._assert_eqcr_passed(task.project_id, year)
        await self.update_status(task_id, WordExportStatus.confirmed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.approval_by = approver_id
        task.approval_at = datetime.now(timezone.utc)
        task.confirmed_by = approver_id
        task.confirmed_at = datetime.now(timezone.utc)
        task.reject_reason = None
        await self.db.flush()
        return task

    async def reject(
        self, task_id: UUID, approver_id: UUID, reason: str
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.pending_approval.value:
            raise ValueError(
                f"仅 pending_approval 状态可驳回，当前: {task.status}"
            )
        await self.update_status(task_id, WordExportStatus.editing.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.reject_reason = reason
        task.approval_by = approver_id
        task.approval_at = datetime.now(timezone.utc)
        await self.db.flush()
        return task

    async def archive_project_deliverables(
        self,
        project_id: UUID,
        user_id: UUID,
        year: int,
        *,
        force: bool = False,
    ) -> int:
        check = await CompletenessService(self.db).check(project_id, year)
        if not check.passed and not force:
            raise ValueError(
                "完整性检查未通过，无法归档。"
                + ("；".join(check.warnings) if check.warnings else "")
            )

        result = await self.db.execute(
            sa.select(WordExportTask).where(
                WordExportTask.project_id == project_id,
                WordExportTask.status.in_(
                    [
                        WordExportStatus.confirmed.value,
                        WordExportStatus.signed.value,
                    ]
                ),
            )
        )
        tasks = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        count = 0
        for task in tasks:
            await self.update_status(task.id, WordExportStatus.archived.value)
            task.archived_at = now
            count += 1

        if count > 0:
            project = await self.db.get(Project, project_id)
            if project and project.status != ProjectStatus.archived:
                all_result = await self.db.execute(
                    sa.select(WordExportTask).where(
                        WordExportTask.project_id == project_id
                    )
                )
                all_tasks = list(all_result.scalars().all())
                terminal = {WordExportStatus.archived.value}
                if all_tasks and all(t.status in terminal for t in all_tasks):
                    project.status = ProjectStatus.archived

        await self.db.flush()
        return count

    async def unarchive(
        self,
        task_id: UUID,
        admin_id: UUID,
        reason: str,
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.archived.value:
            raise ValueError(f"仅 archived 状态可解除归档，当前: {task.status}")

        previous = task.status
        await self.update_status(task_id, WordExportStatus.confirmed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.archived_at = None

        from app.services.audit_log_helper import append_audit_log

        await append_audit_log(
            self.db,
            {
                "user_id": admin_id,
                "project_id": task.project_id,
                "action": "deliverable_unarchive",
                "resource_type": "word_export_task",
                "resource_id": str(task_id),
                "details": {
                    "event_type": "archive_unarchive",
                    "reason": reason,
                    "previous_status": previous,
                },
            },
        )
        await self.db.flush()
        return task
