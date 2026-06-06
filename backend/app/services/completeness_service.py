"""交付物齐全性 + 三件套一致性校验"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.phase13_models import WordExportDocType, WordExportStatus, WordExportTask
from app.services.deliverable_doc_types import required_doc_types
from app.services.deliverable_snapshot_service import DeliverableSnapshotService

FINANCIAL_MIN_REPORT_TYPES = {"balance_sheet", "income_statement"}


@dataclass
class CompletenessResult:
    passed: bool
    missing_doc_types: list[str] = field(default_factory=list)
    missing_financial_reports: list[str] = field(default_factory=list)
    has_confirmed: bool = False
    trio_consistent: bool = True
    trio_message: str | None = None
    warnings: list[str] = field(default_factory=list)


class CompletenessService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._snapshot_svc = DeliverableSnapshotService(db)

    def required_doc_types(self, project_type: str) -> list[str]:
        return required_doc_types(project_type)

    async def check(self, project_id: UUID, year: int) -> CompletenessResult:
        project = await self.db.get(Project, project_id)
        project_type = (
            project.project_type.value if project else ProjectType.annual.value
        )
        required = self.required_doc_types(project_type)

        result = await self.db.execute(
            sa.select(WordExportTask).where(WordExportTask.project_id == project_id)
        )
        tasks = list(result.scalars().all())

        missing: list[str] = []
        missing_financial: list[str] = []
        has_confirmed = False

        for doc_type in required:
            type_tasks = [t for t in tasks if t.doc_type == doc_type]
            has_file = any(
                t.file_path or t.status not in (WordExportStatus.draft.value,)
                for t in type_tasks
            )
            if not has_file:
                missing.append(doc_type)
                continue

            if doc_type == WordExportDocType.financial_report.value:
                covered = self._financial_report_types_covered(type_tasks)
                if not FINANCIAL_MIN_REPORT_TYPES.issubset(covered):
                    missing_financial = sorted(
                        FINANCIAL_MIN_REPORT_TYPES - covered
                    )

        for t in tasks:
            if t.status == WordExportStatus.confirmed.value:
                has_confirmed = True
                break

        trio = await self._snapshot_svc.check_trio_consistency(project_id, year)

        warnings: list[str] = []
        if missing:
            warnings.append(f"缺失交付物类型: {', '.join(missing)}")
        if missing_financial:
            warnings.append(
                f"财务报表未包含: {', '.join(missing_financial)}"
            )
        if not has_confirmed:
            warnings.append("尚无状态为 confirmed 的交付物版本")
        if not trio.consistent and trio.message:
            warnings.append(trio.message)

        passed = (
            not missing
            and not missing_financial
            and has_confirmed
            and trio.consistent
        )

        return CompletenessResult(
            passed=passed,
            missing_doc_types=missing,
            missing_financial_reports=missing_financial,
            has_confirmed=has_confirmed,
            trio_consistent=trio.consistent,
            trio_message=trio.message,
            warnings=warnings,
        )

    def _financial_report_types_covered(
        self, tasks: list[WordExportTask]
    ) -> set[str]:
        covered: set[str] = set()
        for task in tasks:
            sections = task.selected_sections
            if isinstance(sections, list):
                covered.update(sections)
            elif task.file_path:
                covered.update(FINANCIAL_MIN_REPORT_TYPES)
        return covered
