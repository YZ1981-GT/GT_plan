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
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.deliverable_readiness_sources import ReadinessSourceChecks
from app.services.deliverable_readiness_types import ReadinessBlocker, SourceStatus

logger = logging.getLogger(__name__)


# ── 快照 digest 纯函数 ─────────────────────────────────────────────

_SNAPSHOT_SOURCE_KEYS = (
    "adjustments",
    "dataset",
    "formula_push",
    "notes",
    "reports",
    "tb",
)


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
                "content_digest": v.get("content_digest") or v.get("detail", {}).get("content_digest"),
                "version_id": v.get("version_id") or v.get("detail", {}).get("version_id"),
                "run_id": v.get("run_id") or v.get("detail", {}).get("run_id"),
                "run_status": v.get("run_status") or v.get("detail", {}).get("run_status"),
                "source_kind": v.get("source_kind") or v.get("detail", {}).get("source_kind"),
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


class DeliverableReadinessService(ReadinessSourceChecks):
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

        # 2. 当前账套数据集版本。没有 active 数据集可兼容历史项目，但快照必须显式记下 None。
        try:
            async with db.begin_nested():
                dataset_status = await self._check_dataset(db, project_id, year)
                sources["dataset"] = dataset_status.__dict__
        except Exception as exc:
            logger.warning("Dataset readiness check failed: %s", exc)
            blockers.append(ReadinessBlocker(
                code="upstream_not_ready",
                message="当前账套数据集不可查询",
                evidence={"component": "dataset", "error": str(exc)[:200]},
            ))
            sources["dataset"] = SourceStatus().__dict__

        # 3. 试算表（TB）
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

        # 4. 公式推送
        try:
            async with db.begin_nested():
                fp_status = await self._check_formula_push(
                    db,
                    project_id,
                    year,
                    blockers,
                    report_scope=(project.report_scope if project is not None else None),
                )
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
                notes_status = await self._check_notes(
                    db,
                    project_id,
                    year,
                    blockers,
                    report_scope=(project.report_scope if project is not None else None),
                    template_type=(project.template_type if project is not None else None),
                )
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
