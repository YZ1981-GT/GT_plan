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
        from app.services.consistency_gate import ConsistencyGate, gate_decision

        gate = ConsistencyGate(self.db)
        consistency_result = await gate.run_all_checks(project_id, year)

        decision = gate_decision(consistency_result, consumer="export_package")

        warnings_text = None
        if decision.blocks or consistency_result.has_blocking_failures:
            if not force_export:
                raise ConsistencyCheckError(
                    # enforce：统一判定的提示；observe：按改造前口径拒绝，提示也用改造前原文
                    # （decision.summary 此时是「…（当前为只提示模式）」，而这里确实拒绝了，需求 16.4）
                    decision.summary if decision.blocks else "一致性检查未通过，无法导出",
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

        # ── 生成 Excel 报表（formal 来源）──────────────────────────────────
        #
        # 🔴 AC-20 要求「组合包任一来源/policy 失败时不生成 zip，包内无空文件和
        # placeholder」。改造前这里是 `except → BytesIO(b"")` 后**照样打包**：
        # 用户拿到一个 zip，里面那个 xlsx 是 0 字节、打开报「文件已损坏」，
        # 而调用方只看到 200 ⇒ 静默产出废件。
        from app.services.report_excel_exporter import ReportExcelExporter

        excel_exporter = ReportExcelExporter(self.db)
        try:
            excel_output = await excel_exporter.export(
                project_id=project_id,
                year=year,
                mode="audited",
            )
        except Exception as e:
            # fail closed：整包失败，不产出「少了报表」的静默半成品
            raise ExportPackageBuildError(
                f"财务报表生成失败，组合包未生成（不产出空文件）: {e}"
            ) from e
        excel_bytes = excel_output.getvalue()
        if not excel_bytes:
            raise ExportPackageBuildError(
                "财务报表生成返回 0 字节，组合包未生成（不产出空文件）"
            )

        # ── 生成 Word 附注（formal 来源）─────────────────────────────────
        from app.services.note_word_exporter import NoteWordExporter

        word_exporter = NoteWordExporter(self.db)
        try:
            from app.services.note_section_catalog import normalize_report_scope

            word_output = await word_exporter.export(
                project_id=project_id,
                year=year,
                template_type=project.template_type or "soe",
                report_scope=normalize_report_scope(project.report_scope),
            )
        except Exception as e:
            raise ExportPackageBuildError(
                f"附注 Word 生成失败，组合包未生成（不产出空文件）: {e}"
            ) from e
        word_bytes = word_output.getvalue()
        if not word_bytes:
            raise ExportPackageBuildError(
                "附注 Word 生成返回 0 字节，组合包未生成（不产出空文件）"
            )

        # ── 单位策略快照（formal 来源必须带 policy digest）───────────────
        #
        # AC-22 要求 manifest 逐项含 policy digest。取快照失败 ⇒ 整包失败：
        # 「这份包里金额按元还是万元」必须可审计，不能缺。
        from app.services.export_policy_snapshot import resolve_policy_snapshot_for_project

        try:
            policy_snapshot = await resolve_policy_snapshot_for_project(
                self.db, project_id=project_id, year=year
            )
        except Exception as e:
            raise ExportPackageBuildError(
                f"单位策略快照构造失败，组合包未生成（缺 policy 无法审计）: {e}"
            ) from e
        policy_payload = json.loads(policy_snapshot)
        policy_digest = policy_payload.get("_digest")

        # Build filenames per 致同 naming convention (Requirements: 32.1-32.4)
        excel_filename = sanitize_filename(f"{company_short}_{year}年度财务报表.xlsx")
        word_filename = sanitize_filename(f"{company_short}_{year}年度财务报表附注.docx")

        # Build ZIP
        zip_buffer = BytesIO()
        manifest_files = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Excel report
            zf.writestr(excel_filename, excel_bytes)
            manifest_files.append({
                "filename": excel_filename,
                "type": "financial_statements",
                "format": "xlsx",
                "size_bytes": len(excel_bytes),
                "sha256": hashlib.sha256(excel_bytes).hexdigest(),
                "classification": "formal",
                "policy_digest": policy_digest,
            })

            # Word notes
            zf.writestr(word_filename, word_bytes)
            manifest_files.append({
                "filename": word_filename,
                "type": "notes_to_financial_statements",
                "format": "docx",
                "size_bytes": len(word_bytes),
                "sha256": hashlib.sha256(word_bytes).hexdigest(),
                "classification": "formal",
                "policy_digest": policy_digest,
            })

            # ── 可选：审计报告 / 审定表 ──────────────────────────────────
            #
            # 🔴 改造前这两项写的是**真占位符字节**
            # （`b"Audit report placeholder"` / `b"Workpapers placeholder"`）：
            # 用户拿到的 zip 里那两个文件打不开，而 manifest 里还带着 sha256 与
            # size ⇒ 看起来像「有据可查的正式件」。
            # AC-20 明确「包内无空文件和 placeholder」⇒ 现在**要么产出真件、要么整包失败**。
            # 真件来源尚未接入组合包（审计报告走 `word-exports/audit-report/generate`，
            # 审定表走底稿导出），故当前显式拒绝而不是造假件。
            if include_audit_report:
                raise ExportPackageBuildError(
                    "审计报告真件来源尚未接入组合包（拒绝产出 placeholder）。"
                    "请先用 word-exports/audit-report/generate 单独生成。"
                )

            if include_workpapers:
                raise ExportPackageBuildError(
                    "审定表真件来源尚未接入组合包（拒绝产出 placeholder）。"
                    "请先用底稿导出单独生成。"
                )

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
                # 1.1：新增 `unit_policy`（AC-22 要求 manifest 能证明「按哪个单位出」）
                # 与每条文件的 `classification` / `policy_digest`
                "version": "1.1",
                "project_id": str(project_id),
                "project_name": project.name,
                "company_name": project.client_name or project.name,
                "year": year,
                "export_time": datetime.now(timezone.utc).isoformat(),
                "template_type": project.template_type or "soe",
                # AC-22：manifest 必须能证明「这份包按哪个单位出」
                "unit_policy": {
                    "unit": policy_payload.get("unit"),
                    "divisor": policy_payload.get("divisor"),
                    "digest": policy_digest,
                    "fallback": bool(policy_payload.get("_fallback", False)),
                },
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


class ExportPackageBuildError(Exception):
    """组合包构建失败（fail closed）。

    🔴 与 `ConsistencyCheckError` 的区别：那个是「数据不一致，可 force_export 放行」，
    这个是「来源拿不到 / 是空字节 / 是 placeholder / 缺 policy」——
    **不产出半成品**。改造前这些情形会静默产出空文件或 placeholder 字节，
    调用方只看到 200，用户拿到废件。
    """
