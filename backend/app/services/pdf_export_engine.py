"""PDF导出引擎 — 文档渲染 + 导出任务管理

MVP 实现：
- render_document: 生成简单 HTML 文件（WeasyPrint 可选）
- create_export_task: 创建导出任务记录
- execute_export: 同步执行导出（MVP 无 Celery）
- get_task_status / get_history: 查询任务状态和历史

Validates: Requirements 7.1, 7.2, 7.3, 7.7
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    ExportTask,
    ExportTaskStatus,
    ExportTaskType,
)

logger = logging.getLogger(__name__)

# Export files directory
EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "exports"


# ---------------------------------------------------------------------------
# Simple Jinja2-style HTML templates (inline, no separate files)
# ---------------------------------------------------------------------------

_BASE_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: 仿宋_GB2312, SimSun, serif; font-size: 12pt;
       margin: 3cm 3.18cm 2.54cm 3cm; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 4px 8px; text-align: right; }}
th {{ font-weight: bold; border-bottom: 1pt solid #000; }}
td:first-child, th:first-child {{ text-align: left; }}
tr.total td {{ font-weight: bold; border-top: 1pt solid #000; }}
.header {{ text-align: center; font-size: 16pt; font-weight: bold; margin-bottom: 20px; }}
.footer {{ text-align: center; font-size: 9pt; color: #666; margin-top: 30px; }}
</style></head>
<body>{body}</body></html>
"""


def _render_audit_report_html(data: dict) -> str:
    """渲染审计报告 HTML"""
    paragraphs = data.get("paragraphs", {})
    body_parts = [f'<div class="header">审计报告</div>']
    for section_name, content in paragraphs.items():
        body_parts.append(f"<h3>{section_name}</h3>")
        body_parts.append(f"<p>{content}</p>")
    return _BASE_HTML.format(title="审计报告", body="\n".join(body_parts))


def _render_financial_report_html(data: dict) -> str:
    """渲染财务报表 HTML"""
    report_type = data.get("report_type", "financial_report")
    rows = data.get("rows", [])
    body_parts = [f'<div class="header">{report_type}</div>']
    body_parts.append("<table><tr><th>项目</th><th>期末余额</th><th>年初余额</th></tr>")
    for row in rows:
        cls = ' class="total"' if row.get("is_total") else ""
        body_parts.append(
            f"<tr{cls}><td>{row.get('row_name', '')}</td>"
            f"<td>{row.get('current_period_amount', 0)}</td>"
            f"<td>{row.get('prior_period_amount', 0)}</td></tr>"
        )
    body_parts.append("</table>")
    return _BASE_HTML.format(title=report_type, body="\n".join(body_parts))


def _render_disclosure_notes_html(data: dict) -> str:
    """渲染附注 HTML"""
    notes = data.get("notes", [])
    body_parts = ['<div class="header">财务报表附注</div>']
    for note in notes:
        body_parts.append(f"<h3>{note.get('note_section', '')} {note.get('section_title', '')}</h3>")
        if note.get("table_data"):
            td = note["table_data"]
            headers = td.get("headers", [])
            body_parts.append("<table><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
            for row in td.get("rows", []):
                cls = ' class="total"' if row.get("is_total") else ""
                vals = "".join(f"<td>{v}</td>" for v in row.get("values", []))
                body_parts.append(f"<tr{cls}><td>{row.get('label', '')}</td>{vals}</tr>")
            body_parts.append("</table>")
        if note.get("text_content"):
            body_parts.append(f"<p>{note['text_content']}</p>")
    return _BASE_HTML.format(title="财务报表附注", body="\n".join(body_parts))


# Map document_type to renderer
_RENDERERS = {
    "audit_report": _render_audit_report_html,
    "financial_report": _render_financial_report_html,
    "balance_sheet": _render_financial_report_html,
    "income_statement": _render_financial_report_html,
    "cash_flow_statement": _render_financial_report_html,
    "equity_statement": _render_financial_report_html,
    "disclosure_notes": _render_disclosure_notes_html,
}


class PDFExportEngine:
    """PDF导出引擎

    MVP 实现：同步导出，WeasyPrint 可选。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 渲染单个文档
    # ------------------------------------------------------------------
    def render_document(
        self,
        document_type: str,
        data: dict,
        output_path: Path,
    ) -> Path:
        """将文档数据渲染为 HTML，如果 WeasyPrint 可用则转为 PDF。

        Validates: Requirements 7.1, 7.4
        """
        renderer = _RENDERERS.get(document_type, _render_financial_report_html)
        html_content = renderer(data)

        # Try WeasyPrint → PDF, fallback to HTML
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]
            pdf_path = output_path.with_suffix(".pdf")
            HTML(string=html_content).write_pdf(str(pdf_path))
            logger.info("Rendered PDF: %s", pdf_path)
            return pdf_path
        except (ImportError, OSError):
            logger.info("WeasyPrint not available, saving as HTML")
            html_path = output_path.with_suffix(".html")
            html_path.write_text(html_content, encoding="utf-8")
            return html_path

    # ------------------------------------------------------------------
    # 创建导出任务
    # ------------------------------------------------------------------
    async def create_export_task(
        self,
        project_id: UUID,
        task_type: ExportTaskType,
        document_type: str | None = None,
        created_by: UUID | None = None,
    ) -> ExportTask:
        """创建导出任务记录。

        Validates: Requirements 7.2, 7.7
        """
        task = ExportTask(
            project_id=project_id,
            task_type=task_type,
            document_type=document_type,
            status=ExportTaskStatus.queued,
            progress_percentage=0,
            created_by=created_by,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    # ------------------------------------------------------------------
    # 执行导出（MVP 同步）
    # ------------------------------------------------------------------
    async def execute_export(self, task_id: UUID) -> ExportTask:
        """同步执行导出任务（MVP 无 Celery）。

        Validates: Requirements 7.2, 7.3
        TODO: 15.3 — xlsx→PDF 转换
        TODO: 15.4 — PDF 合并与后处理
        TODO: 15.5 — PDF 密码保护
        """
        result = await self.db.execute(
            sa.select(ExportTask).where(ExportTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise ValueError(f"导出任务不存在: {task_id}")

        now = datetime.utcnow()
        task.status = ExportTaskStatus.processing
        task.started_at = now
        task.progress_percentage = 10
        await self.db.flush()

        try:
            # Ensure export directory exists
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)

            # Generate a simple placeholder file
            output_path = EXPORT_DIR / f"export_{task.id}"
            doc_type = task.document_type or "financial_report"

            # Render a minimal document
            rendered = self.render_document(
                doc_type,
                {"report_type": doc_type, "rows": [], "paragraphs": {}, "notes": []},
                output_path,
            )

            task.progress_percentage = 100
            task.status = ExportTaskStatus.completed
            task.completed_at = datetime.utcnow()
            task.file_path = str(rendered)
            task.file_size = rendered.stat().st_size if rendered.exists() else 0
            await self.db.flush()
            return task

        except Exception as e:
            logger.exception("Export task %s failed: %s", task_id, e)
            task.status = ExportTaskStatus.failed
            task.error_message = str(e)
            task.completed_at = datetime.utcnow()
            await self.db.flush()
            return task

    # ------------------------------------------------------------------
    # 查询任务状态
    # ------------------------------------------------------------------
    async def get_task_status(self, task_id: UUID) -> ExportTask | None:
        """获取导出任务状态"""
        result = await self.db.execute(
            sa.select(ExportTask).where(ExportTask.id == task_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 导出历史
    # ------------------------------------------------------------------
    async def get_history(
        self,
        project_id: UUID,
        limit: int = 20,
    ) -> list[ExportTask]:
        """获取项目导出历史"""
        result = await self.db.execute(
            sa.select(ExportTask)
            .where(ExportTask.project_id == project_id)
            .order_by(ExportTask.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
