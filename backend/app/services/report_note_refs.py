"""报表附注列编号：导出 Excel 与报表页共用的唯一来源。

spec platform-performance-residual-findings-closure R2。原先三套口径并存：报表页按「有金额的行」计数编「五、N」，
``GET /api/report-config/row-note-mapping`` 返回静态映射的模板编号（且该端点被 ``/{config_id}`` 遮蔽从未可达），
导出 Excel 用附注模板轮廓 + 本项目附注「有数据」口径求交付件编号（单体国企「八、10」显示为「七、N」，无数据的节不占号）。

本模块把导出的那套算法原样提供给两边：

* :func:`build_report_note_ref_plan` —— 导出 ``ReportExcelExporter._build_note_ref_plan`` 直接委托这里；
* :func:`project_row_note_refs` —— 对模板里每个附注列占位格用导出同一函数 ``render_note_refs`` 渲染出格值，
  再按行名挂到本项目报表行上（模板与库内是两套编码，按行名对，不按编码）。
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

#: 有附注列的报表（模板里 ``{{note_ref:…}}`` 只出现在资产负债表与利润表）
_NOTE_REF_REPORT_TYPES = ("balance_sheet", "income_statement")


def _variant(template_key: str) -> dict[str, Any]:
    from app.services.report_excel_exporter import _load_note_ref_mapping

    variant = _load_note_ref_mapping().get(template_key, {})
    return variant if isinstance(variant, dict) else {}


def note_ref_hints(template_key: str) -> dict[str, tuple[str, str]]:
    """``report_row_note_mapping.json`` 该变体的 模板编码 → (附注编码, 附注标题)。"""
    return {
        code: (str(info.get("section_code") or ""), str(info.get("section_title") or ""))
        for code, info in _variant(template_key).items()
        if isinstance(info, dict) and info.get("section_code")
    }


def static_note_refs(template_key: str) -> dict[str, str]:
    """模板编码 → 静态附注编码（编号方案不可用时导出按它填附注列）。"""
    return {code: section for code, (section, _title) in note_ref_hints(template_key).items()}


def static_row_note_mapping(applicable_standard: str) -> dict[str, dict[str, Any]]:
    """静态映射原样返回：``{模板编码: {section_code, section_title, seq}}``，seq 按 JSON 键序（BS→IS→…）全局连续。"""
    result: dict[str, dict[str, Any]] = {}
    for seq, (row_code, info) in enumerate(_variant(applicable_standard).items(), start=1):
        entry = dict(info) if isinstance(info, dict) else {"section_code": str(info)}
        entry["seq"] = seq
        result[row_code] = entry
    return result


async def build_report_note_ref_plan(db, project_id: UUID, year: int, *, template_type: str, report_scope: str):
    """附注列编号方案（``note_deliverable_outline.build_fs_note_ref_plan``）；附注模板缺失或出错返回 ``None``。

    读失败只回滚自身 SAVEPOINT，不毒化调用方会话（PG 首条失败会使整个事务 aborted）。
    """
    try:
        from app.services.note_deliverable_outline import build_fs_note_ref_plan

        hints = note_ref_hints(f"{template_type}_{report_scope}")
        async with db.begin_nested():
            return await build_fs_note_ref_plan(
                db, project_id, year, template_type=template_type, report_scope=report_scope, hints=hints,
            )
    except Exception:  # noqa: BLE001 — fail-open：回退按静态映射填附注列
        logger.warning("附注列编号方案生成失败，回退静态映射 project=%s", project_id, exc_info=True)
        return None


@lru_cache(maxsize=16)
def _scan_template_note_ref_cells(path: str, _mtime_ns: int) -> tuple[tuple[str, str, str], ...]:
    """模板里整格是附注列占位的格 → ``(格文本, 左侧行名, 首个本级编码)``，按 sheet、行、列顺序。"""
    from openpyxl import load_workbook

    from app.services.report_excel_sheet_ops import NOTE_REF_ANY_RE, row_label_left_of

    wb = load_workbook(path)
    out: list[tuple[str, str, str]] = []
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    text = cell.value.strip() if isinstance(cell.value, str) else ""
                    # 与导出 Track 1b 同一判据：整格只有附注列占位（可多个，如合并模板「本级;母公司」）
                    if "{{note_ref:" not in text or "{{" in NOTE_REF_ANY_RE.sub("", text):
                        continue
                    codes = [m.group(1) for m in NOTE_REF_ANY_RE.finditer(text) if not m.group(2)]
                    if not codes:
                        continue
                    out.append((text, row_label_left_of(ws, cell.row, cell.column), codes[0]))
    finally:
        wb.close()
    return tuple(out)


def template_note_ref_cells(template_key: str) -> tuple[tuple[str, str, str], ...]:
    """按文件修改时间缓存的模板附注列占位格；模板缺失返回空。"""
    from app.services.report_excel_exporter import resolve_fs_template_path

    path = resolve_fs_template_path(template_key)
    if path is None:
        return ()
    try:
        return _scan_template_note_ref_cells(str(path), os.stat(path).st_mtime_ns)
    except Exception:  # noqa: BLE001 — 模板读失败：页面不显示附注列编号，不影响报表
        logger.warning("附注列模板扫描失败 template=%s", template_key, exc_info=True)
        return ()


#: 模板编码前缀 → 报表类型（模板与库内编码是两套，只借前缀判断这一格属于哪张表）
_CODE_PREFIX_TYPES = {"BS": "balance_sheet", "IS": "income_statement"}


async def _report_rows(db, project_id: UUID, year: int) -> list[tuple[str, str, str]]:
    """本项目资产负债表 / 利润表行 → ``[(report_type, row_code, row_name)]``，按报表、编码顺序。"""
    import sqlalchemy as sa

    from app.models.report_models import FinancialReport, FinancialReportType

    types = [FinancialReportType(t) for t in _NOTE_REF_REPORT_TYPES]
    async with db.begin_nested():
        rows = (await db.execute(
            sa.select(FinancialReport.report_type, FinancialReport.row_code, FinancialReport.row_name)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
                FinancialReport.report_type.in_(types),
            )
            .order_by(FinancialReport.report_type, FinancialReport.row_code)
        )).all()
    return [
        (getattr(r.report_type, "value", str(r.report_type)), r.row_code, r.row_name or "")
        for r in rows if r.row_code
    ]


async def project_row_note_refs(db, project_id: UUID, year: int, *, template_type: str, report_scope: str) -> dict:
    """本项目报表行 → 导出 Excel 附注列会写的格值。

    返回 ``{row_code: {section_code, section_title, seq, display}, "_meta": {...}}``：
    ``display`` 是导出该格的值（``None`` = 导出留空）；``section_code`` 是点击跳转的库内附注编号（取不到时为
    静态映射编码）；``_meta.source`` 为 ``export_plan``（按编号方案）或 ``static``（方案不可用，与导出一样按静态映射）。
    模板格按行名（``title_key``，限同一张表）挂到库内行，同名多行优先编码相同的那行；库内没有同名行的格不登记
    （模板与库内是两套编码，按编码硬挂会挂错行）。
    """
    from app.services.note_deliverable_outline import title_key
    from app.services.report_excel_sheet_ops import render_note_refs

    template_key = f"{template_type}_{report_scope}"
    plan = await build_report_note_ref_plan(
        db, project_id, year, template_type=template_type, report_scope=report_scope,
    )
    statics = static_note_refs(template_key)
    try:
        rows = await _report_rows(db, project_id, year)
    except Exception:  # noqa: BLE001 — 报表未生成 / 读失败：按模板编码登记
        logger.warning("附注列取报表行失败 project=%s", project_id, exc_info=True)
        rows = []
    by_key: dict[tuple[str, str], list[str]] = {}
    for report_type, code, name in rows:
        k = title_key(name)
        if k:
            by_key.setdefault((report_type, k), []).append(code)

    result: dict[str, Any] = {}
    for seq, (text, label, code) in enumerate(template_note_ref_cells(template_key), start=1):
        display, _missed = render_note_refs(text, label, statics, plan)
        section = plan.section_for(label, hint_code=code) if plan is not None else None
        report_type = _CODE_PREFIX_TYPES.get(code.split("-", 1)[0])
        key = title_key(label)
        pool = (by_key.get((report_type, key), []) if report_type else
                [c for (rt, k), codes in by_key.items() if k == key for c in codes])
        candidates = [c for c in pool if c not in result]
        if not candidates:
            continue  # 库内没有同名行：页面上没有这一行可挂（不按编码硬挂，两套编码会挂错行）
        target = code if code in candidates else candidates[0]
        result[target] = {
            "section_code": section or statics.get(code),
            "section_title": label,
            "seq": seq,
            "display": display,
        }
    result["_meta"] = {
        "source": "export_plan" if plan is not None else "static",
        "has_notes": None if plan is None else bool(plan.has_notes),
    }
    return result
