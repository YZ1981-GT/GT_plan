"""底稿证据就绪度的唯一事实来源。

展示、QC、签发和归档只能把这里的四态映射成自己的严重度，不能重新以“附件数 > 0”
等近似条件判断。``unknown`` 表示本次无法证明就绪，不等于无声明或已满足。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

Status = Literal["ready", "not_ready", "not_declared", "unknown"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkpaperEvidenceReadiness:
    wp_id: UUID
    project_id: UUID | None
    wp_code: str | None
    wp_name: str | None = None
    assignee: UUID | None = None
    status: Status = "unknown"
    requirements: tuple[dict[str, Any], ...] = ()
    missing_types: tuple[str, ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "wp_id": str(self.wp_id),
            "project_id": str(self.project_id) if self.project_id else None,
            "wp_code": self.wp_code,
            "wp_name": self.wp_name,
            "assignee": str(self.assignee) if self.assignee else None,
            "status": self.status,
            "requirements": [dict(row) for row in self.requirements],
            "missing_types": list(self.missing_types),
            "warnings": [dict(row) for row in self.warnings],
            "errors": [dict(row) for row in self.errors],
        }


@dataclass(frozen=True)
class ProjectEvidenceReadiness:
    project_id: UUID
    status: Status
    workpapers: tuple[WorkpaperEvidenceReadiness, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def blockers(self) -> tuple[WorkpaperEvidenceReadiness, ...]:
        return tuple(row for row in self.workpapers if row.status in {"not_ready", "unknown"})

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": str(self.project_id),
            "status": self.status,
            "counts": dict(self.counts),
            "workpapers": [row.as_dict() for row in self.workpapers],
        }


class EvidenceReadinessService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate_workpaper(
        self,
        wp_id: UUID,
        *,
        preloaded_items: list[dict[str, Any]] | None = None,
        wp_meta: dict[str, Any] | None = None,
    ) -> WorkpaperEvidenceReadiness:
        """在 SAVEPOINT 中严格判定；任一依赖失败收敛为 ``unknown``。"""
        project_id = wp_meta.get("project_id") if wp_meta else None
        wp_code = wp_meta.get("wp_code") if wp_meta else None
        wp_name = wp_meta.get("wp_name") if wp_meta else None
        assignee = wp_meta.get("assigned_to") if wp_meta else None
        savepoint = None
        try:
            savepoint = await self.db.begin_nested()
            if wp_meta is None:
                wp_meta = await self._load_wp_meta(wp_id)
                if wp_meta is None:
                    raise LookupError("底稿不存在")
            project_id = wp_meta.get("project_id")
            wp_code = wp_meta.get("wp_code")
            wp_name = wp_meta.get("wp_name")
            assignee = wp_meta.get("assigned_to")
            result = await self._evaluate_strict(
                wp_id, wp_meta, preloaded_items=preloaded_items,
            )
            await savepoint.commit()
            return result
        except Exception as exc:  # 保存点已回滚，正式消费方看到 unknown 而非伪通过
            if savepoint is not None:
                try:
                    await savepoint.rollback()
                except Exception:
                    logger.warning("证据就绪度保存点回滚失败 wp=%s", wp_id, exc_info=True)
            logger.warning("证据就绪度判定失败 wp=%s", wp_id, exc_info=True)
            return WorkpaperEvidenceReadiness(
                wp_id=wp_id,
                project_id=project_id,
                wp_code=wp_code,
                wp_name=wp_name,
                assignee=assignee,
                status="unknown",
                errors=({
                    "error_code": "EVIDENCE_READINESS_UNAVAILABLE",
                    "message": f"证据状态无法判断（{type(exc).__name__}）",
                },),
            )

    async def _load_wp_meta(self, wp_id: UUID) -> dict[str, Any] | None:
        from app.models.core import Project
        from app.models.workpaper_models import WorkingPaper, WpIndex

        row = (await self.db.execute(
            sa.select(
                WorkingPaper.project_id,
                WpIndex.wp_code,
                WpIndex.wp_name,
                WorkingPaper.assigned_to,
                Project.audit_year,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .join(Project, Project.id == WorkingPaper.project_id)
            .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )).first()
        if row is None:
            return None
        return {
            "project_id": row.project_id,
            "wp_code": row.wp_code,
            "wp_name": row.wp_name,
            "assigned_to": row.assigned_to,
            "audit_year": row.audit_year,
        }

    async def _evaluate_strict(
        self,
        wp_id: UUID,
        wp_meta: dict[str, Any],
        *,
        preloaded_items: list[dict[str, Any]] | None,
    ) -> WorkpaperEvidenceReadiness:
        from app.services.attachment_service import AttachmentService
        from app.services.attachment_wp_view import (
            _apply_confirmation_breakdown,
            _apply_voucher_samples,
            _collect_items,
        )
        from app.services.workpaper_evidence_requirements import (
            build_evidence_requirements_strict,
            resolve_requirements_for_wp_code_strict,
        )

        project_id = wp_meta["project_id"]
        wp_code = wp_meta.get("wp_code")
        declarations = resolve_requirements_for_wp_code_strict(wp_code)
        if not declarations:
            return WorkpaperEvidenceReadiness(
                wp_id=wp_id, project_id=project_id, wp_code=wp_code,
                wp_name=wp_meta.get("wp_name"), assignee=wp_meta.get("assigned_to"),
                status="not_declared",
            )

        items = preloaded_items
        if items is None:
            items = await _collect_items(AttachmentService(self.db), wp_id, strict=True)
        available_items = [row for row in items if row.get("state", "available") == "available"]
        requirements = build_evidence_requirements_strict(wp_code, available_items) or []
        await _apply_confirmation_breakdown(
            self.db, wp_id, wp_meta, requirements, strict=True,
        )
        await _apply_voucher_samples(
            self.db, wp_id, wp_meta, requirements, strict=True,
        )

        missing = [str(row["type"]) for row in requirements if not row.get("satisfied")]
        warnings: list[dict[str, Any]] = []
        key_unconfirmed: list[str] = []
        for item in available_items:
            has_ocr = bool(item.get("ocr_text_length")) or item.get("ocr_status") == "completed"
            if not has_ocr or item.get("ocr_confirmed"):
                continue
            issue = {
                "attachment_id": str(item.get("id") or ""),
                "file_name": str(item.get("file_name") or "未命名附件"),
                "error_code": "EVIDENCE_OCR_UNCONFIRMED",
                "message": "识别结果尚未人工确认",
            }
            if item.get("is_key_evidence"):
                key_unconfirmed.append(str(item.get("id") or ""))
                issue["blocking"] = True
            else:
                issue["blocking"] = False
            warnings.append(issue)

        if key_unconfirmed:
            missing.append("key_evidence_ocr_confirmation")
        status: Status = "not_ready" if missing else "ready"
        return WorkpaperEvidenceReadiness(
            wp_id=wp_id,
            project_id=project_id,
            wp_code=wp_code,
            wp_name=wp_meta.get("wp_name"),
            assignee=wp_meta.get("assigned_to"),
            status=status,
            requirements=tuple(requirements),
            missing_types=tuple(dict.fromkeys(missing)),
            warnings=tuple(warnings),
        )

    async def evaluate_project(self, project_id: UUID) -> ProjectEvidenceReadiness:
        from app.models.workpaper_models import WorkingPaper

        savepoint = None
        try:
            savepoint = await self.db.begin_nested()
            wp_ids = list((await self.db.execute(
                sa.select(WorkingPaper.id)
                .where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
                .order_by(WorkingPaper.id)
            )).scalars().all())
            await savepoint.commit()
        except Exception as exc:
            if savepoint is not None:
                try:
                    await savepoint.rollback()
                except Exception:
                    logger.warning("项目证据底稿清单保存点回滚失败 project=%s", project_id, exc_info=True)
            logger.warning("项目证据底稿清单读取失败 project=%s", project_id, exc_info=True)
            unknown = WorkpaperEvidenceReadiness(
                wp_id=UUID(int=0), project_id=project_id, wp_code=None, status="unknown",
                errors=({
                    "error_code": "EVIDENCE_READINESS_UNAVAILABLE",
                    "message": f"无法读取项目底稿（{type(exc).__name__}）",
                },),
            )
            return ProjectEvidenceReadiness(
                project_id=project_id, status="unknown", workpapers=(unknown,),
                counts={"unknown": 1},
            )

        results = tuple([await self.evaluate_workpaper(wp_id) for wp_id in wp_ids])
        counts = {name: sum(row.status == name for row in results) for name in (
            "ready", "not_ready", "not_declared", "unknown",
        )}
        if counts["unknown"]:
            status: Status = "unknown"
        elif counts["not_ready"]:
            status = "not_ready"
        elif counts["ready"]:
            status = "ready"
        else:
            status = "not_declared"
        return ProjectEvidenceReadiness(
            project_id=project_id, status=status, workpapers=results, counts=counts,
        )
