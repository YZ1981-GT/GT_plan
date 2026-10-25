"""交付中心 readiness 检查服务 — phase4 spec §四

提供项目 × 年度级 readiness 判定：
- 硬闸门（hard_blockers）：必须全部清零才能出具三件套
- 软警告（warnings）：记录在案，不阻断

hardBlocker code 是稳定字符串，前端按 code 定位行动点。
中文 message 随业务语义更新，但 code 不变。

service 仅 flush 不 commit；由 router 统一 commit。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


# ── 快照 digest 纯函数 ─────────────────────────────────────────────

_SNAPSHOT_SOURCE_KEYS = ("adjustments", "formula_push", "notes", "reports", "tb")


def build_snapshot_digest(
    project_id: UUID,
    year: int,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """构建快照摘要（纯函数，可独立测试）。

    digest 不含生成时间和本机绝对路径（design §五 / 需求 1.5）。
    对同一输入生成相同 digest。
    返回 ``{"id": "<uuid5>", "digest": "<sha256>", "payload": {...}}``。
    """
    payload = {
        "project_id": str(project_id),
        "year": year,
        "sources": {
            k: {
                "available": v.get("available"),
                "count": v.get("count"),
                "stale_count": v.get("stale_count", 0),
            }
            for k, v in sorted(sources.items())  # 排序确保稳定
            if k in _SNAPSHOT_SOURCE_KEYS
        },
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, digest)),
        "digest": digest,
        "payload": payload,
    }

# ── 正式三件套 step 定义（与 design §二 对齐）────────────────────────

TRIO_STEP_KEYS: list[dict[str, Any]] = [
    {"key": "financial_report", "sequence": 1, "label": "审定财务报表"},
    {"key": "disclosure_notes", "sequence": 2, "label": "报表附注"},
    {"key": "audit_report", "sequence": 3, "label": "审计报告正文"},
]


# ── 结果数据类 ─────────────────────────────────────────────────────

@dataclass
class ReadinessBlocker:
    """一条硬闸门或软警告。"""
    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceStatus:
    """某一数据源的 readiness 摘要。"""
    available: bool = False
    count: int = 0
    stale_count: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrioStepStatus:
    """正式三件套某步骤的 readiness 状态。"""
    key: str
    sequence: int
    status: str = "ready"  # ready / blocked


@dataclass
class ReadinessResult:
    """readiness 完整返回结构。"""
    status: str  # ready / blocked / ready_with_warnings
    hard_blockers: list[ReadinessBlocker] = field(default_factory=list)
    warnings: list[ReadinessBlocker] = field(default_factory=list)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    trio: dict[str, Any] = field(default_factory=dict)


class DeliverableReadinessService:
    """交付中心 readiness 检查。

    ``check(db, project_id, year)`` 真读取 TB、公式推送、调整、
    报表、附注的项目年度状态，返回结构化的 blockers / warnings / snapshot。

    phase3 尚未落库的能力 → 返回明确 blocker code。
    """

    async def check(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        *,
        include_file_checks: bool = True,
    ) -> ReadinessResult:
        """执行 readiness 检查。"""
        blockers: list[ReadinessBlocker] = []
        warnings: list[ReadinessBlocker] = []
        sources: dict[str, dict[str, Any]] = {}

        # 1. 项目存在性 & 准则/模板/年度唯一性
        try:
            async with db.begin_nested():
                project = await self._check_project(db, project_id, year, blockers)
        except Exception as exc:
            logger.warning("Project readiness check failed: %s", exc)
            project = None
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="项目数据不可查询",
                evidence={"component": "project", "error": str(exc)[:200]},
            ))

        # 2. 试算表（TB）
        try:
            async with db.begin_nested():
                tb_status = await self._check_trial_balance(db, project_id, year, blockers)
                sources["tb"] = tb_status.__dict__
        except Exception as exc:
            logger.warning("TB readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="试算表数据不可查询",
                evidence={"component": "tb", "error": str(exc)[:200]},
            ))
            sources["tb"] = SourceStatus().__dict__

        # 3. 公式推送
        try:
            async with db.begin_nested():
                fp_status = await self._check_formula_push(db, project_id, year, blockers)
                sources["formula_push"] = fp_status.__dict__
        except Exception as exc:
            logger.warning("Formula push readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="公式推送数据不可查询",
                evidence={"component": "formula_push", "error": str(exc)[:200]},
            ))
            sources["formula_push"] = SourceStatus().__dict__

        # 4. 调整确认
        try:
            async with db.begin_nested():
                adj_status = await self._check_adjustments(db, project_id, year, blockers, warnings)
                sources["adjustments"] = adj_status.__dict__
        except Exception as exc:
            logger.warning("Adjustments readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="调整分录数据不可查询",
                evidence={"component": "adjustments", "error": str(exc)[:200]},
            ))
            sources["adjustments"] = SourceStatus().__dict__

        # 5. 报表
        try:
            async with db.begin_nested():
                report_status = await self._check_reports(db, project_id, year, blockers)
                sources["reports"] = report_status.__dict__
        except Exception as exc:
            logger.warning("Reports readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="报表数据不可查询",
                evidence={"component": "financial_report", "error": str(exc)[:200]},
            ))
            sources["reports"] = SourceStatus().__dict__

        # 6. 附注
        try:
            async with db.begin_nested():
                notes_status = await self._check_notes(db, project_id, year, blockers)
                sources["notes"] = notes_status.__dict__
        except Exception as exc:
            logger.warning("Notes readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="附注数据不可查询",
                evidence={"component": "disclosure_notes", "error": str(exc)[:200]},
            ))
            sources["notes"] = SourceStatus().__dict__

        # 7. 历史版本文件物理校验
        if include_file_checks:
            try:
                async with db.begin_nested():
                    await self._check_existing_files(db, project_id, blockers, warnings)
            except Exception as exc:
                logger.warning("File checks failed: %s", exc)
                warnings.append(ReadinessBlocker(
                    code="file_check_error",
                    message="历史版本文件校验异常",
                    evidence={"error": str(exc)[:200]},
                ))

        # 8. 构建快照摘要
        snapshot = self._build_snapshot_digest(project_id, year, sources)

        # 9. trio 步骤状态
        trio_steps = self._build_trio_steps(blockers)

        # 10. 汇总状态
        if blockers:
            status = "blocked"
        elif warnings:
            status = "ready_with_warnings"
        else:
            status = "ready"

        return ReadinessResult(
            status=status,
            hard_blockers=blockers,
            warnings=warnings,
            sources=sources,
            snapshot=snapshot,
            trio={
                "total": 3,
                "steps": [
                    {"key": s.key, "sequence": s.sequence, "status": s.status}
                    for s in trio_steps
                ],
            },
        )

    # ── 各数据源检查 ───────────────────────────────────────────────

    async def _check_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
    ) -> Project | None:
        """项目存在性 / 准则 / 模板 / 年度唯一性。"""
        result = await db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            blockers.append(ReadinessBlocker(
                code="missing_project",
                message="项目不存在或已删除",
                evidence={"project_id": str(project_id)},
            ))
            return None

        # 准则唯一性
        if not project.template_type and not project.accounting_standard_id:
            blockers.append(ReadinessBlocker(
                code="missing_template_or_standard",
                message="项目未设置会计准则或模板类型，无法确定出具格式",
                evidence={"project_id": str(project_id)},
            ))

        # 年度校验：用 audit_period_end 或 audit_year
        project_year = project.audit_year
        if project_year is None and project.audit_period_end is not None:
            project_year = project.audit_period_end.year
        if project_year is not None and project_year != year:
            blockers.append(ReadinessBlocker(
                code="year_mismatch",
                message=f"请求年度 {year} 与项目审计年度 {project_year} 不一致",
                evidence={"requested_year": year, "project_year": project_year},
            ))

        return project

    async def _check_trial_balance(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
    ) -> SourceStatus:
        """试算表就绪检查。"""
        from app.models.audit_platform_models import TrialBalance

        result = await db.execute(
            sa.select(sa.func.count()).select_from(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        tb_count = result.scalar_one()

        status = SourceStatus(
            available=tb_count > 0,
            count=tb_count,
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
    ) -> SourceStatus:
        """公式推送就绪检查 — 需至少一次 succeeded 运行记录。"""
        try:
            from app.models.formula_push_models import FormulaPushRun
        except ImportError:
            # phase2 模块未在 HEAD — fail-closed
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="公式推送引擎模块未就绪（phase2 依赖）",
                evidence={"component": "formula_push"},
            ))
            return SourceStatus()

        try:
            result = await db.execute(
                sa.select(sa.func.count()).select_from(FormulaPushRun).where(
                    FormulaPushRun.project_id == project_id,
                    FormulaPushRun.year == year,
                    FormulaPushRun.status == "succeeded",
                )
            )
            success_count = result.scalar_one()
        except Exception as exc:
            logger.warning("formula_push query failed: %s", exc)
            try:
                await db.rollback()
            except Exception:
                pass
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="公式推送数据不可查询（phase2 迁移可能未执行）",
                evidence={"component": "formula_push", "error": str(exc)[:200]},
            ))
            return SourceStatus()

        status = SourceStatus(
            available=success_count > 0,
            count=success_count,
        )

        if success_count == 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="公式推送未成功运行，下游底稿/附注数据可能不完整",
                evidence={"component": "formula_push", "project_id": str(project_id), "year": year},
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

        # 所有非删除调整分录
        result = await db.execute(
            sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.is_deleted == False,  # noqa: E712
            )
        )
        total_count = result.scalar_one()

        # 未确认（draft / pending_review）的调整
        result = await db.execute(
            sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.is_deleted == False,  # noqa: E712
                Adjustment.review_status.in_(["draft", "pending_review"]),
            )
        )
        unconfirmed = result.scalar_one()

        status = SourceStatus(
            available=True,
            count=total_count,
            detail={"unconfirmed_count": unconfirmed},
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
        """报表就绪检查 — 存在且无 stale。"""
        from app.models.report_models import FinancialReport

        result = await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
        )
        report_count = result.scalar_one()

        stale_result = await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == False,  # noqa: E712
                FinancialReport.is_stale == True,  # noqa: E712
            )
        )
        stale_count = stale_result.scalar_one()

        status = SourceStatus(
            available=report_count > 0,
            count=report_count,
            stale_count=stale_count,
        )

        if report_count == 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="财务报表数据不存在，需先生成报表",
                evidence={"component": "financial_report", "project_id": str(project_id), "year": year},
            ))
        elif stale_count > 0:
            blockers.append(ReadinessBlocker(
                code="stale_source",
                message=f"有 {stale_count} 条报表行标记为过期（is_stale），需刷新后再出具",
                evidence={
                    "component": "financial_report",
                    "stale_count": stale_count,
                    "total_count": report_count,
                },
            ))

        return status

    async def _check_notes(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        blockers: list[ReadinessBlocker],
    ) -> SourceStatus:
        """附注就绪检查 — 存在且无 stale。"""
        from app.models.report_models import DisclosureNote

        result = await db.execute(
            sa.select(sa.func.count()).select_from(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,  # noqa: E712
            )
        )
        note_count = result.scalar_one()

        stale_result = await db.execute(
            sa.select(sa.func.count()).select_from(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,  # noqa: E712
                DisclosureNote.is_stale == True,  # noqa: E712
            )
        )
        stale_count = stale_result.scalar_one()

        status = SourceStatus(
            available=note_count > 0,
            count=note_count,
            stale_count=stale_count,
        )

        if note_count == 0:
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="报表附注不存在，需先准备附注章节",
                evidence={"component": "disclosure_notes", "project_id": str(project_id), "year": year},
            ))
        elif stale_count > 0:
            blockers.append(ReadinessBlocker(
                code="stale_source",
                message=f"有 {stale_count} 个附注章节标记为过期（is_stale），需刷新后再出具",
                evidence={
                    "component": "disclosure_notes",
                    "stale_count": stale_count,
                    "total_count": note_count,
                },
            ))

        return status

    async def _check_existing_files(
        self,
        db: AsyncSession,
        project_id: UUID,
        blockers: list[ReadinessBlocker],
        warnings: list[ReadinessBlocker],
    ) -> None:
        """历史交付版本文件物理校验（可选）。

        只检查已存在的正式版本 — 无历史版本不是阻断。
        """
        from app.models.phase13_models import (
            WordExportTask,
            WordExportTaskVersion,
        )

        # 查找项目已有的正式版本（有 file_path 且状态为生效态）
        result = await db.execute(
            sa.select(WordExportTaskVersion).join(
                WordExportTask,
                WordExportTaskVersion.word_export_task_id == WordExportTask.id,
            ).where(
                WordExportTask.project_id == project_id,
                WordExportTaskVersion.file_path.isnot(None),
            )
        )
        versions = result.scalars().all()

        for v in versions:
            fp = Path(v.file_path) if v.file_path else None
            if fp is None:
                continue
            if not fp.exists():
                warnings.append(ReadinessBlocker(
                    code="missing_file",
                    message=f"历史交付版本文件不存在：{fp.name}",
                    evidence={
                        "version_id": str(v.id),
                        "file_path": str(fp),
                    },
                ))
            elif fp.stat().st_size == 0:
                warnings.append(ReadinessBlocker(
                    code="unreadable_file",
                    message=f"历史交付版本文件大小为零：{fp.name}",
                    evidence={
                        "version_id": str(v.id),
                        "file_path": str(fp),
                    },
                ))

    # ── 快照 & trio 构建 ──────────────────────────────────────────

    def _build_snapshot_digest(
        self,
        project_id: UUID,
        year: int,
        sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """构建快照摘要 — 委托给模块级纯函数。"""
        return build_snapshot_digest(project_id, year, sources)

    def _build_trio_steps(
        self,
        blockers: list[ReadinessBlocker],
    ) -> list[TrioStepStatus]:
        """构建 trio 步骤状态 — blockers 存在时全部标 blocked。"""
        step_status = "blocked" if blockers else "ready"
        return [
            TrioStepStatus(
                key=s["key"],
                sequence=s["sequence"],
                status=step_status,
            )
            for s in TRIO_STEP_KEYS
        ]

    # ── 序列化辅助 ────────────────────────────────────────────────

    @staticmethod
    def result_to_dict(r: ReadinessResult) -> dict[str, Any]:
        """ReadinessResult → JSON 可序列化 dict。"""
        return {
            "status": r.status,
            "hard_blockers": [
                {"code": b.code, "message": b.message, "evidence": b.evidence}
                for b in r.hard_blockers
            ],
            "warnings": [
                {"code": w.code, "message": w.message, "evidence": w.evidence}
                for w in r.warnings
            ],
            "sources": r.sources,
            "snapshot": r.snapshot,
            "trio": r.trio,
        }
