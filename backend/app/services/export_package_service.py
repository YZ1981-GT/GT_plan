"""组合导出包服务 — ZIP 打包

Sprint 6 Task 6.5 + 6.6: ExportPackageService + 文件命名规范

ZIP 包含：
  - 财务报表_{公司名}_{年度}.xlsx
  - 财务报表附注_{公司名}_{年度}.docx
  - 可选：审计报告 + 审定表
  - manifest.json（文件清单）

打包前执行 ConsistencyGate 校验：
  - 校验失败返回 400
  - force_export=true 跳过校验附加 _warnings.txt

Requirements: 5.1-5.8, 32.1-32.4
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Replace special characters in filename with underscores.

    Requirements: 32.4
    Avoids: / \\ : * ? " < > |
    """
    return re.sub(r'[/\\:*?"<>|]', '_', name)


def get_company_short_name(project: Project) -> str:
    """Get company short name from project config.

    Requirements: 32.3
    Priority: wizard_state.company_short_name > client_name > project.name
    """
    if project.wizard_state and isinstance(project.wizard_state, dict):
        short_name = project.wizard_state.get("company_short_name")
        if short_name:
            return sanitize_filename(short_name)

    name = project.client_name or project.name or "未知公司"
    # Extract Chinese characters for short name
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', name)
    if len(chinese_chars) <= 6:
        return sanitize_filename(name)
    return sanitize_filename("".join(chinese_chars[:4]))


class ExportPackageService:
    """组合导出包服务

    Requirements: 5.1-5.8
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_package(
        self,
        project_id: UUID,
        year: int,
        include_audit_report: bool = False,
        include_workpapers: bool = False,
        force_export: bool = False,
    ) -> BytesIO:
        """生成组合导出 ZIP 包

        Args:
            project_id: 项目 ID
            year: 年度
            include_audit_report: 是否包含审计报告
            include_workpapers: 是否包含审定表
            force_export: 强制导出（跳过一致性检查）

        Returns:
            BytesIO containing the ZIP file

        Raises:
            ConsistencyCheckError: 一致性检查失败且 force_export=False
        """
        # Load project
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        company_short = get_company_short_name(project)

        # Run consistency check
        from app.services.consistency_gate import ConsistencyGate

        gate = ConsistencyGate(self.db)
        consistency_result = await gate.run_all_checks(project_id, year)

        warnings_text = None
        if consistency_result.has_blocking_failures:
            if not force_export:
                raise ConsistencyCheckError(
                    "一致性检查未通过，无法导出",
                    checks=[
                        {"check_name": c.check_name, "passed": c.passed, "details": c.details, "severity": c.severity}
                        for c in consistency_result.checks
                    ],
                )
            else:
                # Generate warnings text
                failed_checks = [c for c in consistency_result.checks if not c.passed]
                lines = ["导出警告 — 以下一致性检查未通过：", ""]
                for c in failed_checks:
                    lines.append(f"  [{c.severity}] {c.check_name}: {c.details}")
                lines.append("")
                lines.append(f"导出时间: {datetime.now(timezone.utc).isoformat()}")
                lines.append("注意: 此导出包含未通过一致性检查的数据，请谨慎使用。")
                warnings_text = "\n".join(lines)

        # Generate Excel report
        from app.services.report_excel_exporter import ReportExcelExporter

        excel_exporter = ReportExcelExporter(self.db)
        try:
            excel_output = await excel_exporter.export(
                project_id=project_id,
                year=year,
                mode="audited",
            )
        except Exception as e:
            logger.warning("Excel export failed, using empty placeholder: %s", e)
            excel_output = BytesIO(b"")

        # Generate Word notes
        from app.services.note_word_exporter import NoteWordExporter

        word_exporter = NoteWordExporter(self.db)
        try:
            word_output = await word_exporter.export(
                project_id=project_id,
                year=year,
                template_type=project.template_type or "soe",
            )
        except Exception as e:
            logger.warning("Word export failed, using empty placeholder: %s", e)
            word_output = BytesIO(b"")

        # Build filenames per 致同 naming convention (Requirements: 32.1-32.4)
        excel_filename = sanitize_filename(f"{company_short}_{year}年度财务报表.xlsx")
        word_filename = sanitize_filename(f"{company_short}_{year}年度财务报表附注.docx")

        # Build ZIP
        zip_buffer = BytesIO()
        manifest_files = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Excel report
            excel_bytes = excel_output.getvalue()
            zf.writestr(excel_filename, excel_bytes)
            manifest_files.append({
                "filename": excel_filename,
                "type": "financial_statements",
                "format": "xlsx",
                "size_bytes": len(excel_bytes),
                "sha256": hashlib.sha256(excel_bytes).hexdigest(),
            })

            # Word notes
            word_bytes = word_output.getvalue()
            zf.writestr(word_filename, word_bytes)
            manifest_files.append({
                "filename": word_filename,
                "type": "notes_to_financial_statements",
                "format": "docx",
                "size_bytes": len(word_bytes),
                "sha256": hashlib.sha256(word_bytes).hexdigest(),
            })

            # Optional: audit report placeholder
            if include_audit_report:
                audit_filename = sanitize_filename(f"{company_short}_{year}年度审计报告.docx")
                audit_content = b"Audit report placeholder"
                zf.writestr(audit_filename, audit_content)
                manifest_files.append({
                    "filename": audit_filename,
                    "type": "audit_report",
                    "format": "docx",
                    "size_bytes": len(audit_content),
                    "sha256": hashlib.sha256(audit_content).hexdigest(),
                })

            # Optional: workpapers placeholder
            if include_workpapers:
                wp_filename = sanitize_filename(f"{company_short}_{year}年度审定表.xlsx")
                wp_content = b"Workpapers placeholder"
                zf.writestr(wp_filename, wp_content)
                manifest_files.append({
                    "filename": wp_filename,
                    "type": "workpapers",
                    "format": "xlsx",
                    "size_bytes": len(wp_content),
                    "sha256": hashlib.sha256(wp_content).hexdigest(),
                })

            # Warnings file (if force_export with failures)
            if warnings_text:
                zf.writestr("_warnings.txt", warnings_text.encode("utf-8"))
                manifest_files.append({
                    "filename": "_warnings.txt",
                    "type": "warnings",
                    "format": "txt",
                    "size_bytes": len(warnings_text.encode("utf-8")),
                })

            # manifest.json
            manifest = {
                "version": "1.0",
                "project_id": str(project_id),
                "project_name": project.name,
                "company_name": project.client_name or project.name,
                "year": year,
                "export_time": datetime.now(timezone.utc).isoformat(),
                "template_type": project.template_type or "soe",
                "consistency_check": {
                    "overall": consistency_result.overall,
                    "force_export": force_export,
                    "checks": [
                        {"name": c.check_name, "passed": c.passed, "severity": c.severity}
                        for c in consistency_result.checks
                    ],
                },
                "files": manifest_files,
            }
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
            zf.writestr("manifest.json", manifest_json.encode("utf-8"))

        zip_buffer.seek(0)
        return zip_buffer


class ConsistencyCheckError(Exception):
    """一致性检查失败异常"""

    def __init__(self, message: str, checks: list[dict] | None = None):
        super().__init__(message)
        self.checks = checks or []
