"""正式 PDF 导出的真实数据来源。

三条数据链都只复用各自领域的正式读取入口，不在 PDF 引擎里复制领域 SQL：

- 财务报表：直接读 ``financial_report``（项目 + 年度 + 软删过滤）；
- 审计报告：``AuditReportService.get_report``（同口径），正文优先
  ``report_body_json.sections``（按 section_order 排序），回退旧 ``paragraphs``；
- 附注：委托 ``NoteWordExporter`` 的加载与表格投影（``_load_export_notes`` /
  ``_note_tables``），再补齐软删过滤、报告口径过滤、值解包与按任务冻结
  policy 的折算。

所有来源共用 ``PDFSourceUnavailable``（409 = 数据未就绪 / 尚未接入，
422 = 请求前置条件不足）；空数据**永远不冒充成功**。
"""
from __future__ import annotations

import html
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.report_models import (
    AuditReport,
    FinancialReport,
    FinancialReportType,
    ReportStatus,
)

_FINANCIAL_TYPES = {
    FinancialReportType.balance_sheet.value,
    FinancialReportType.income_statement.value,
    FinancialReportType.cash_flow_statement.value,
    FinancialReportType.equity_statement.value,
}
_UNIT_LABELS = {"yuan": "元", "qian": "千元", "wan": "万元"}
#: 只有 EQCR 已批准 / 定稿的报告才能作为正式交付件导出（ReportStatus 没有
#: "approved" 成员——按枚举成员名实证，不按命名习惯猜）。
_EXPORTABLE_REPORT_STATUSES = {ReportStatus.eqcr_approved.value, ReportStatus.final.value}


class PDFSourceUnavailable(RuntimeError):
    """正式 PDF 数据来源不可用，不得用空页面冒充成功。"""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _validated_policy(unit_policy_snapshot: dict[str, Any] | None) -> tuple[str, int]:
    """解析任务冻结的 policy 快照；非法快照是请求前置条件问题（422）。"""
    snapshot = unit_policy_snapshot or {}
    unit = snapshot.get("unit")
    divisor = snapshot.get("divisor")
    if unit not in _UNIT_LABELS or not isinstance(divisor, int) or divisor <= 0:
        raise PDFSourceUnavailable("PDF 导出单位策略快照无效", status_code=422)
    return str(unit), divisor


def _scale(value: Any, divisor: int) -> Decimal | None:
    if value is None:
        return None
    try:
        return (Decimal(str(value)) / Decimal(divisor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PDFSourceUnavailable("数据含不可转换的金额") from exc


# ---------------------------------------------------------------------------
# 财务报表
# ---------------------------------------------------------------------------


async def build_financial_pdf_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None,
    document_types: list[str],
    unit_policy_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """从当前项目年度的 ``financial_report`` 构造非空 PDF renderer 数据。"""
    if year is None:
        raise PDFSourceUnavailable("正式 PDF 导出必须携带审计年度", status_code=422)
    if not document_types:
        raise PDFSourceUnavailable("正式 PDF 导出至少选择一份文档", status_code=422)
    unsupported = [item for item in document_types if item not in _FINANCIAL_TYPES]
    if unsupported:
        raise PDFSourceUnavailable(
            "当前批次只接入财务报表 PDF，尚未接入：" + ", ".join(unsupported)
        )
    _, divisor = _validated_policy(unit_policy_snapshot)

    sections: list[dict[str, Any]] = []
    for report_type in dict.fromkeys(document_types):
        enum_type = FinancialReportType(report_type)
        result = await db.execute(
            sa.select(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == enum_type,
                FinancialReport.is_deleted == sa.false(),
            )
            .order_by(FinancialReport.row_code)
        )
        source_rows = list(result.scalars().all())
        if not source_rows:
            raise PDFSourceUnavailable(
                f"项目 {project_id} 的 {year} 年 {report_type} 没有可导出的正式数据"
            )
        rows: list[dict[str, Any]] = []
        for source in source_rows:
            rows.append(
                {
                    "row_code": source.row_code,
                    "row_name": html.escape(source.row_name or source.row_code),
                    "current_period_amount": _scale(source.current_period_amount, divisor),
                    "prior_period_amount": _scale(source.prior_period_amount, divisor),
                    "is_total": bool(source.is_total_row),
                    "indent_level": source.indent_level,
                }
            )
        sections.append({"report_type": report_type, "rows": rows})

    return {
        "report_type": sections[0]["report_type"] if len(sections) == 1 else "financial_report",
        "unit_label": _UNIT_LABELS[str(unit_policy_snapshot["unit"])],
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# 审计报告
# ---------------------------------------------------------------------------


def _new_audit_service(db: AsyncSession):
    """构造审计报告正式读取服务（单一接缝，测试注入点）。"""
    from app.services.audit_report_service import AuditReportService

    return AuditReportService(db)


def extract_audit_report_paragraphs(report: Any) -> dict[str, str]:
    """从 ``AuditReport`` 提取正文段落（Word 模板主源 + 旧载体回退）。

    正文优先 ``report_body_json.sections``（按 ``section_order`` 排序、KAM
    ``items`` 与 ``render_docx`` 同口径合入正文），回退旧 ``paragraphs`` 载体
    （JSON 单阶段模式只写这套）。两套都空返回 ``{}``。

    🔴 为什么抽成公共函数：PDF 数据源（``build_audit_report_pdf_data``）与
    整包 ZIP（``ExportPackageService._build_audit_report_bytes``）需要**同一份
    正文口径** —— 只改 PDF 不改整包，Word 模板模式项目的 PDF 能导出、组合包
    仍误判「无段落内容」整包失败（双写必漂移）。

    注意：本函数**不做 HTML 转义**（docx/纯文本路径不需要）；调用方按输出
    目的地自行处理。
    """
    paragraphs: dict[str, str] = {}
    body = report.report_body_json if isinstance(report.report_body_json, dict) else {}
    for section in sorted(
        body.get("sections") or [], key=lambda s: s.get("section_order", 0)
    ):
        name = str(section.get("section_name") or section.get("section_id") or "").strip()
        if not name:
            continue
        content = str(section.get("content") or "")
        # KAM 多条目段：与 render_docx 同口径合入正文（matter + response）。
        for item in section.get("items") or []:
            matter = str(item.get("matter") or "")
            response = str(item.get("response") or "")
            content = f"{content}\n\n{matter}\n{response}".strip()
        if content:
            paragraphs[name] = content

    if not paragraphs:
        # 回退旧 paragraphs 载体（JSON 单阶段模式只写这一套）
        for name, content in (report.paragraphs or {}).items():
            if content:
                paragraphs[str(name)] = str(content)

    return paragraphs


async def build_audit_report_pdf_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None,
) -> dict[str, Any]:
    """从 ``audit_report`` 构造审计报告 PDF 的 ``paragraphs`` 数据。

    正文优先 ``report_body_json.sections``（Word 模板模式的主源，按
    ``section_order`` 排序、KAM items 合入正文），回退旧 ``paragraphs`` 载体
    （JSON 单阶段模式）。两套载体都空 = 409。草稿/复核中不导出（409）：
    正式交付件只有 EQCR 已批准或定稿两种状态。
    """
    from app.services.audit_report_service import AuditReportService  # noqa: F401 - 保留旧导入兼容

    if year is None:
        raise PDFSourceUnavailable("正式 PDF 导出必须携带审计年度", status_code=422)
    report = await _new_audit_service(db).get_report(project_id, year)
    if report is None:
        raise PDFSourceUnavailable(
            f"项目 {project_id} 的 {year} 年审计报告尚未生成，请先在报告模块生成"
        )
    status_value = getattr(report.status, "value", report.status)
    if status_value not in _EXPORTABLE_REPORT_STATUSES:
        raise PDFSourceUnavailable(
            f"审计报告状态为 {status_value}，未达可导出状态（需 eqcr_approved 或 final）"
        )

    # 共享正文口径（Word 模板主源 + 旧载体回退）；PDF 目的地需要 HTML 转义。
    raw_paragraphs = extract_audit_report_paragraphs(report)
    paragraphs = {
        html.escape(name): html.escape(content).replace("\n", "<br/>")
        for name, content in raw_paragraphs.items()
    }

    if not paragraphs:
        raise PDFSourceUnavailable(
            f"项目 {project_id} 的 {year} 年审计报告没有正文内容"
            "（report_body_json.sections 与 paragraphs 均为空）"
        )
    return {"report_type": "audit_report", "paragraphs": paragraphs}


# ---------------------------------------------------------------------------
# 附注
# ---------------------------------------------------------------------------


def _cell_value(value: Any, divisor: int) -> Any:
    """解包附注单元格（dict 载体优先 ``value``，回退 ``manual_value``）并折算。"""
    if isinstance(value, dict):
        value = value.get("value", value.get("manual_value", 0))
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        # 公式串/文本不折算；转义防注入
        return html.escape(value) if value.startswith("=") or not _is_number(value) else value
    return _scale(value, divisor)


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return False
    return True


def _new_note_exporter(db: AsyncSession):
    """构造附注正式读取链的 exporter（单一接缝，测试注入点）。"""
    from app.services.note_word_exporter import NoteWordExporter

    return NoteWordExporter(db)


async def build_disclosure_notes_pdf_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None,
    unit_policy_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """从附注正式读取链构造 PDF 的 ``notes`` 列表。

    复用 ``NoteWordExporter`` 的加载与表格投影（``_load_export_notes`` /
    ``_note_tables``），自己补齐：软删过滤（``_load_notes`` 不带 ``is_deleted``）、
    报告口径过滤（``note_applies_to_report_scope``，否则单体项目长出合并专属章节）、
    按任务冻结 policy 折算（renderer 不做）。合并项目的 fail-closed 校验
    （模板未映射 / 表头不一致 / is_stale）由 adapter 抛 ``ConsolNoteExportError``，
    这里转成 ``PDFSourceUnavailable``（保留其 409/400 语义）。
    """
    from app.services.note_section_catalog import note_applies_to_report_scope
    from app.services.note_word_exporter import (
        normalize_report_scope,
        normalize_template_type,
    )

    if year is None:
        raise PDFSourceUnavailable("正式 PDF 导出必须携带审计年度", status_code=422)
    unit, divisor = _validated_policy(unit_policy_snapshot)

    exporter = _new_note_exporter(db)
    project = (
        await db.execute(sa.select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise PDFSourceUnavailable(f"项目 {project_id} 不存在")
    template_type = normalize_template_type(getattr(project, "template_type", None) or "soe")
    report_scope = normalize_report_scope(
        getattr(project, "report_scope", None) or "standalone"
    )

    try:
        notes = await exporter._load_export_notes(
            project_id, year, template_type=template_type, report_scope=report_scope
        )
    except Exception as exc:  # noqa: BLE001 - adapter 的 fail-closed 错误转 PDF 语义
        message = str(exc)
        status = getattr(exc, "status", None)
        raise PDFSourceUnavailable(f"附注数据不可用：{message}", status_code=status or 409) from exc

    notes = [
        n for n in notes
        if note_applies_to_report_scope(n.note_section, template_type, report_scope)
        and not getattr(n, "is_deleted", False)
    ]
    if not notes:
        raise PDFSourceUnavailable(
            f"项目 {project_id} 的 {year} 年附注没有可导出的正式数据"
        )

    out: list[dict[str, Any]] = []
    for note in notes:
        tables = exporter._note_tables(note)
        if not tables and not (note.text_content or "").strip():
            # 空章节（本期无此项业务）：不出现在正式 PDF，也不报错
            continue
        for idx, table in enumerate(tables):
            headers = list(table.get("headers") or [])
            rows: list[dict[str, Any]] = []
            for source_row in table.get("rows") or []:
                raw_values = source_row.get("cells", source_row.get("values")) or []
                rows.append(
                    {
                        "label": html.escape(str(source_row.get("label") or "")),
                        "values": [_cell_value(v, divisor) for v in raw_values],
                        "is_total": bool(source_row.get("is_total")),
                    }
                )
            title = str(note.section_title or note.note_section or "")
            if idx > 0:
                # 一章多表：renderer 每条只吃一张表，第 2+ 张把表名并进标题
                title = f"{title}｜{table.get('name') or f'表{idx + 1}'}"
            out.append(
                {
                    "note_section": note.note_section,
                    "section_title": html.escape(title),
                    "table_data": {"headers": [html.escape(str(h)) for h in headers], "rows": rows},
                    "text_content": None,
                }
            )
        if (note.text_content or "").strip():
            out.append(
                {
                    "note_section": note.note_section,
                    "section_title": html.escape(str(note.section_title or note.note_section or "")),
                    "table_data": None,
                    "text_content": html.escape(str(note.text_content)),
                }
            )

    if not out:
        raise PDFSourceUnavailable(
            f"项目 {project_id} 的 {year} 年附注没有可导出的正式数据"
        )
    return {"report_type": "disclosure_notes", "unit_label": _UNIT_LABELS[unit], "notes": out}


# ---------------------------------------------------------------------------
# 分派器
# ---------------------------------------------------------------------------

#: 多文档合并的固定顺序：审计报告 → 四张报表（枚举序）→ 附注。
#: 前端勾选顺序不稳定，正式交付件顺序必须确定。
_BUNDLE_ORDER: tuple[str, ...] = (
    "audit_report",
    FinancialReportType.balance_sheet.value,
    FinancialReportType.income_statement.value,
    FinancialReportType.cash_flow_statement.value,
    FinancialReportType.equity_statement.value,
    "disclosure_notes",
)

_SINGLE_DOC_BUILDERS: dict[str, Any] = {}


def _single_doc_builder(doc_type: str):
    """返回单文档 builder 协程；未知类型 422。"""
    if doc_type in _FINANCIAL_TYPES:
        return lambda db, *, project_id, year, snapshot: build_financial_pdf_data(
            db, project_id=project_id, year=year, document_types=[doc_type],
            unit_policy_snapshot=snapshot,
        )
    if doc_type == "audit_report":
        return lambda db, *, project_id, year, snapshot: build_audit_report_pdf_data(
            db, project_id=project_id, year=year
        )
    if doc_type == "disclosure_notes":
        return lambda db, *, project_id, year, snapshot: build_disclosure_notes_pdf_data(
            db, project_id=project_id, year=year, unit_policy_snapshot=snapshot
        )
    raise PDFSourceUnavailable(f"未知文档类型：{doc_type}", status_code=422)


async def build_pdf_source_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None,
    document_types: list[str],
    unit_policy_snapshot: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | list[tuple[str, dict[str, Any]]]:
    """按任务冻结的文档清单解析 PDF 数据。

    返回：
    - 单文档：``(renderer_type, data)``（既有契约，调用方行为不变）；
    - 多文档：``[(renderer_type, data), ...]``，按 :data:`_BUNDLE_ORDER` 排序；
      逐类独立校验，任一失败整体 409/422 —— **不静默丢一类**（旧形态是
      「选了审计报告 + 资产负债表却得到一张报表 PDF 还标 completed」）。
    """
    if year is None:
        raise PDFSourceUnavailable("正式 PDF 导出必须携带审计年度", status_code=422)
    if not document_types:
        raise PDFSourceUnavailable("正式 PDF 导出至少选择一份文档", status_code=422)
    unique = list(dict.fromkeys(document_types))

    if len(unique) == 1:
        doc_type = unique[0]
        builder = _single_doc_builder(doc_type)
        data = await builder(db, project_id=project_id, year=year,
                             snapshot=unit_policy_snapshot)
        return _bundle_renderer_type(doc_type), data

    # 多文档：按固定顺序逐类解析；未登记类型先报，避免「解析到一半才红」。
    for doc_type in unique:
        if doc_type not in _BUNDLE_ORDER:
            raise PDFSourceUnavailable(f"未知文档类型：{doc_type}", status_code=422)
    ordered = [t for t in _BUNDLE_ORDER if t in unique]
    parts: list[tuple[str, dict[str, Any]]] = []
    for doc_type in ordered:
        builder = _single_doc_builder(doc_type)
        data = await builder(db, project_id=project_id, year=year,
                             snapshot=unit_policy_snapshot)
        parts.append((_bundle_renderer_type(doc_type), data))
    return parts


def _bundle_renderer_type(doc_type: str) -> str:
    """多文档分块渲染时每块用的 renderer 名（financial 系列共用同一 renderer）。"""
    if doc_type in _FINANCIAL_TYPES:
        return doc_type
    return doc_type
