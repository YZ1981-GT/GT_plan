"""PDF导出引擎 — 文档渲染 + 导出任务管理

MVP 实现：
- render_document: 生成简单 HTML 文件（WeasyPrint 可选）
- create_export_task: 创建导出任务记录
- execute_export: 同步执行导出（MVP 无 Celery）
- get_task_status / get_history: 查询任务状态和历史

Validates: Requirements 7.1, 7.2, 7.3, 7.7
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    ExportTask,
    ExportTaskStatus,
    ExportTaskType,
)
from app.services.pdf_export_sources import (
    PDFSourceUnavailable,
    build_financial_pdf_data,
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
    """渲染真实财务报表数据（支持单表或多个 section）。"""
    report_type = data.get("report_type", "financial_report")
    unit_label = data.get("unit_label")
    sections = data.get("sections")
    if not sections:
        sections = [{"report_type": report_type, "rows": data.get("rows", [])}]
    body_parts = [f'<div class="header">{report_type}</div>']
    if unit_label:
        body_parts.append(f'<div class="footer">金额单位：{unit_label}</div>')
    for section in sections:
        section_type = section.get("report_type", report_type)
        rows = section.get("rows", [])
        if len(sections) > 1:
            body_parts.append(f"<h3>{section_type}</h3>")
        body_parts.append("<table><tr><th>项目</th><th>期末余额</th><th>年初余额</th></tr>")
        for row in rows:
            cls = ' class="total"' if row.get("is_total") else ""
            body_parts.append(
                f"<tr{cls}><td>{row.get('row_name', '')}</td>"
                f"<td>{row.get('current_period_amount') or ''}</td>"
                f"<td>{row.get('prior_period_amount') or ''}</td></tr>"
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


# ---------------------------------------------------------------------------
# AI 贡献声明水印工具（R3 Sprint 4 Task 23）
# ---------------------------------------------------------------------------

def build_ai_contribution_statement(reviewer: str = "审计师") -> str:
    """生成 AI 贡献声明文本。

    Args:
        reviewer: 审阅人名称，默认"审计师"

    Returns:
        格式化的声明文本
    """
    return f"本文档含 AI 辅助生成内容，已由 {reviewer} 审阅并定稿"


def get_ai_statement_css() -> str:
    """生成 AI 贡献声明的 CSS 样式块。"""
    return """\
.ai-contribution-statement {
    position: fixed;
    bottom: 10px;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 9pt;
    color: #666;
    padding: 4px 0;
    border-top: 1px solid #ddd;
}
"""


def get_ai_statement_html(reviewer: str = "审计师") -> str:
    """生成 AI 贡献声明的 HTML 片段。

    Args:
        reviewer: 审阅人名称

    Returns:
        包含声明文本的 HTML div
    """
    text = build_ai_contribution_statement(reviewer)
    return f'<div class="ai-contribution-statement">{text}</div>'


def render_with_ai_statement(html_content: str, reviewer: str = "审计师") -> str:
    """将 AI 贡献声明注入到已有 HTML 文档中。

    注入逻辑：
    1. CSS 注入到 </style> 前（若有），否则创建 <style> 注入到 </head> 前
       若无 </head>，则在 HTML 片段中使用 inline style
    2. HTML 片段注入到 </body> 前；若无 </body> 则追加到末尾

    Args:
        html_content: 原始 HTML 文档字符串
        reviewer: 审阅人名称

    Returns:
        注入声明后的 HTML 文档
    """
    css = get_ai_statement_css()
    statement_text = build_ai_contribution_statement(reviewer)

    # 注入 CSS
    if "</style>" in html_content:
        html_content = html_content.replace("</style>", css + "</style>", 1)
        html_snippet = f'<div class="ai-contribution-statement">{statement_text}</div>'
    elif "</head>" in html_content:
        html_content = html_content.replace(
            "</head>", f"<style>{css}</style></head>", 1
        )
        html_snippet = f'<div class="ai-contribution-statement">{statement_text}</div>'
    else:
        # 无 head/style 标签，使用 inline style
        html_snippet = (
            f'<div class="ai-contribution-statement" '
            f'style="position:fixed;bottom:10px;text-align:center;'
            f'font-size:9pt;color:#666;">{statement_text}</div>'
        )

    # 注入 HTML 片段到 </body> 前；若无 </body> 则追加到末尾
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", html_snippet + "</body>", 1)
    else:
        html_content = html_content + html_snippet + "\n"

    return html_content


def _normalize_document_types(
    document_type: str | None,
    document_types: list[str] | None,
) -> list[str]:
    """把旧单数/新复数导出合同归一成数据库要求的 JSON 数组。"""
    if not document_types:
        return [document_type] if document_type else []
    normalized = list(dict.fromkeys(str(item) for item in document_types if item))
    if document_type and document_type not in normalized:
        raise ValueError(
            "document_type 与 document_types 不一致，不能静默选择其中一套"
        )
    return normalized


def _normalize_policy_snapshot(
    snapshot: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """把 resolver 的 canonical JSON 转成 JSONB object，禁止写入 JSON 字符串。"""
    if snapshot is None:
        return None
    parsed: Any = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    if not isinstance(parsed, dict):
        raise ValueError("unit_policy_snapshot 必须是 JSON object")
    return parsed


class PDFConversionUnavailable(RuntimeError):
    """PDF 转换链不可用（WeasyPrint 未安装且 LibreOffice 不可用）。

    spec platform-global-display-settings-closure 任务 10 / AC-20：
    转换器缺失时**不得**把 HTML 当 PDF 交付并标 `completed` ——
    用户按「导出 PDF」拿到 `.html` 而任务显示成功，是静默撒谎
    （memory 铁律：报成功的失败比报失败更糟）。调用方据此返回 503。
    """


class PDFExportEngine:
    """PDF导出引擎

    转换链：WeasyPrint（若已安装，纯 Python 更快）→ LibreOffice headless。
    两者都不可用时**抛 `PDFConversionUnavailable`**，不降级为 HTML。
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
        """将文档数据渲染为 PDF（WeasyPrint 优先，LibreOffice 兜底）。

        Validates: Requirements 7.1, 7.4

        🔴 与旧实现的差别：旧版在 WeasyPrint 缺失时**写 HTML 并返回**，
        调用方照样把任务标 `completed`、`file_path` 指向 `.html`。
        用户点「导出 PDF」得到一个 HTML 文件而界面显示成功 —— 静默撒谎。
        现在转换链不可用即抛 `PDFConversionUnavailable`，由调用方返回 503。
        """
        renderer = _RENDERERS.get(document_type, _render_financial_report_html)
        html_content = renderer(data)

        pdf_bytes = self._convert_html_to_pdf(html_content)
        if pdf_bytes is None:
            raise PDFConversionUnavailable(
                "PDF 转换链不可用：WeasyPrint 未安装且 LibreOffice 不可用。"
                "请安装其中任一转换器，或改用 Excel / Word 导出。"
            )
        pdf_path = output_path.with_suffix(".pdf")
        pdf_path.write_bytes(pdf_bytes)
        logger.info("Rendered PDF: %s", pdf_path)
        return pdf_path

    @staticmethod
    def _convert_html_to_pdf(html_content: str) -> bytes | None:
        """HTML → PDF bytes；两条链都不可用返回 ``None``（不写 HTML 冒充）。"""
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]

            return HTML(string=html_content).write_pdf()
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - 转换失败才降级到 LibreOffice
            logger.warning("WeasyPrint 转换失败，降级 LibreOffice: %s", exc)

        try:
            from app.services.libreoffice_pool import find_soffice_path
        except Exception:  # noqa: BLE001 - 池模块缺失时按不可用处理
            return None
        soffice = find_soffice_path()
        if not soffice:
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "input.html"
            html_file.write_text(html_content, encoding="utf-8")
            try:
                subprocess.run(
                    [
                        soffice,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        tmpdir,
                        str(html_file),
                    ],
                    timeout=90,
                    capture_output=True,
                    check=True,
                )
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
                logger.error("LibreOffice 转换 PDF 失败: %s", exc)
                return None
            pdf_file = Path(tmpdir) / "input.pdf"
            return pdf_file.read_bytes() if pdf_file.exists() else None

    # ------------------------------------------------------------------
    # 创建导出任务
    # ------------------------------------------------------------------
    async def create_export_task(
        self,
        project_id: UUID,
        task_type: ExportTaskType,
        document_type: str | None = None,
        created_by: UUID | None = None,
        *,
        export_year: int | None = None,
        document_types: list[str] | None = None,
        unit_policy_snapshot: str | dict[str, Any] | None = None,
    ) -> ExportTask:
        """创建导出任务记录。

        旧调用方只传 `document_type` 时归一为单元素数组；新调用方传
        `document_types` 时保留去重后的顺序。`unit_policy_snapshot` 在
        JSONB 写入边界统一解析为 object，避免 PostgreSQL CHECK 收到 JSON 字符串。
        """
        normalized_document_types = _normalize_document_types(
            document_type, document_types
        )
        normalized_policy_snapshot = _normalize_policy_snapshot(unit_policy_snapshot)
        task = ExportTask(
            project_id=project_id,
            task_type=task_type,
            document_type=document_type,
            status=ExportTaskStatus.queued,
            progress_percentage=0,
            created_by=created_by,
            export_year=export_year,
            document_types=normalized_document_types,
            unit_policy_snapshot=normalized_policy_snapshot,
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

        now = datetime.now(timezone.utc)
        task.status = ExportTaskStatus.processing
        task.started_at = now
        task.progress_percentage = 10
        await self.db.flush()

        try:
            # Ensure export directory exists
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = EXPORT_DIR / f"export_{task.id}"

            # 先解析任务冻结的文档清单；只有带年度的正式请求进入真实数据源。
            # 旧内部调用没有年度时保留兼容状态，后续正式出口批次会移除该兼容路径。
            document_types = list(task.document_types or [])
            if not document_types and task.document_type:
                document_types = [task.document_type]
            if task.export_year is not None:
                source_data = await build_financial_pdf_data(
                    self.db,
                    project_id=task.project_id,
                    year=task.export_year,
                    document_types=document_types,
                    unit_policy_snapshot=task.unit_policy_snapshot,
                )
            else:
                source_data = {
                    "report_type": task.document_type or "financial_report",
                    "rows": [],
                    "paragraphs": {},
                    "notes": [],
                }

            # Render the resolved source data; the formal path must not invent rows.
            rendered = self.render_document(
                document_types[0] if len(document_types) == 1 else "financial_report",
                source_data,
                output_path,
            )

            task.progress_percentage = 100
            task.status = ExportTaskStatus.completed
            task.completed_at = datetime.now(timezone.utc)
            task.file_path = str(rendered)
            task.file_size = rendered.stat().st_size if rendered.exists() else 0
            await self.db.flush()
            return task

        except PDFConversionUnavailable as e:
            # 转换链缺失是**环境**问题，不是业务失败：任务标 failed 留痕，
            # 同时上抛让路由返回 503（可重试 / 换导出格式），不假装成功。
            logger.error("Export task %s: PDF 转换链不可用: %s", task_id, e)
            task.status = ExportTaskStatus.failed
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            raise

        except PDFSourceUnavailable as exc:
            logger.warning("Export task %s source unavailable: %s", task_id, exc)
            task.status = ExportTaskStatus.failed
            task.error_message = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            raise

        except Exception as e:
            logger.exception("Export task %s failed: %s", task_id, e)
            task.status = ExportTaskStatus.failed
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
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
