"""三形式联动适配器 — 将 Excel+HTML+structure.json 统一接入各业务模块

适用模块：
1. 底稿审定表（workpaper）— 核心场景
2. 附注表格（disclosure_note）— 替代自建JSON表格
3. 报表（financial_report）— 支持自定义格式上传
4. 调整分录汇总（adjustment_summary）— 导出用
5. 试算表（trial_balance）— 支持自定义格式
6. 合并差额表（consol_worksheet）— 多企业宽表
7. 底稿模板管理（template）— 上传→预览→确认

每个模块通过 adapter 获得：
- to_structure(): 从模块数据生成 structure.json
- from_structure(): 从 structure.json 更新模块数据
- to_html(): 生成可编辑 HTML
- to_excel(): 导出 Excel
- sync_from_excel(): 编辑器保存后同步（向后兼容）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.excel_html_converter import (
    excel_to_structure,
    structure_to_html,
    structure_to_excel,
    update_structure_from_edits,
)

_logger = logging.getLogger(__name__)


# ═══ 1. 底稿审定表适配器 ═══

class WorkpaperAdapter:
    """底稿审定表 ↔ 三形式联动

    底稿 Excel 文件 → structure.json → HTML 在线编辑
    取数公式绑定到 structure.json 单元格
    Univer 编辑后自动同步
    """

    @staticmethod
    async def wp_to_structure(
        db: AsyncSession, project_id: UUID, wp_code: str,
    ) -> dict | None:
        """从底稿文件生成 structure.json"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        result = await db.execute(
            sa.select(WorkingPaper)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WpIndex.project_id == project_id, WpIndex.wp_code == wp_code,
                   WorkingPaper.is_deleted == sa.false())
            .limit(1)
        )
        wp = result.scalar_one_or_none()
        if not wp or not wp.file_path:
            return None

        fp = Path(wp.file_path)
        if not fp.exists():
            return None

        structure = excel_to_structure(str(fp))
        structure["metadata"]["module"] = "workpaper"
        structure["metadata"]["wp_code"] = wp_code
        structure["metadata"]["project_id"] = str(project_id)

        # 绑定已有的取数公式（从 wp_data_rules 映射）
        from app.services.wp_data_rules import get_mapping_for_wp
        mapping = get_mapping_for_wp(wp_code)
        if mapping:
            structure["metadata"]["account_codes"] = mapping.get("account_codes", [])
            structure["metadata"]["note_section"] = mapping.get("note_section")
            structure["metadata"]["report_row"] = mapping.get("report_row")

        return structure

    @staticmethod
    async def save_wp_from_structure(
        db: AsyncSession, project_id: UUID, wp_code: str, structure: dict,
    ) -> str:
        """从 structure.json 回写底稿 Excel"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        result = await db.execute(
            sa.select(WorkingPaper)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WpIndex.project_id == project_id, WpIndex.wp_code == wp_code,
                   WorkingPaper.is_deleted == sa.false())
            .limit(1)
        )
        wp = result.scalar_one_or_none()
        if not wp or not wp.file_path:
            raise ValueError(f"底稿 {wp_code} 不存在")

        structure_to_excel(structure, wp.file_path)
        return wp.file_path


# ═══ 2. 附注表格适配器 ═══

class DisclosureNoteAdapter:
    """附注表格 ↔ 三形式联动

    将 DisclosureNote.table_data 转为 structure.json 格式，
    支持 Excel 导入/导出 + HTML 在线编辑。
    """

    @staticmethod
    async def note_to_structure(
        db: AsyncSession, project_id: UUID, year: int, note_section: str,
    ) -> dict | None:
        """从附注表格数据生成 structure.json"""
        from app.models.report_models import DisclosureNote

        result = await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
            )
        )
        note = result.scalar_one_or_none()
        if not note or not note.table_data:
            return None

        td = note.table_data
        headers = td.get("headers", [])
        rows = td.get("rows", [])

        # 转为 structure.json 格式
        cells = {}
        # 表头行
        for c, h in enumerate(headers):
            cells[f"0:{c}"] = {"value": h, "style": {"bold": True, "textAlign": "center"}}

        # 数据行
        for r, row in enumerate(rows):
            label = row.get("label", "")
            values = row.get("values", [])
            cell_modes = row.get("_cell_modes", {})
            is_total = row.get("is_total", False)

            # 标签列
            style = {"bold": True} if is_total else {}
            cells[f"{r+1}:0"] = {"value": label, "style": style}

            # 数据列
            for c, val in enumerate(values):
                key = f"{r+1}:{c+1}"
                cell = {"value": val}
                mode = cell_modes.get(str(c), "auto")
                if mode != "auto":
                    cell["_mode"] = mode
                if is_total:
                    cell["style"] = {"bold": True}
                cells[key] = cell

        # 公式
        formulas = td.get("_formulas", {})
        for fkey, fdef in formulas.items():
            parts = fkey.split(":")
            row_idx = int(parts[0]) + 1  # 偏移表头行
            col_idx = int(parts[1]) + 1  # 偏移标签列
            cell_key = f"{row_idx}:{col_idx}"
            if cell_key in cells:
                cells[cell_key]["formula"] = fdef.get("expression", "")
                cells[cell_key]["_formula_type"] = fdef.get("type", "")

        cols = [{"width": 150}] + [{"width": 120}] * (len(headers) - 1) if headers else []

        return {
            "sheets": [{
                "name": note_section,
                "cols": cols,
                "rows": [{"height": 24}] * (len(rows) + 1),
                "cells": cells,
                "merges": [],
            }],
            "metadata": {
                "module": "disclosure_note",
                "note_section": note_section,
                "project_id": str(project_id),
                "year": year,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            },
        }

    @staticmethod
    async def update_note_from_structure(
        db: AsyncSession, project_id: UUID, year: int, note_section: str,
        structure: dict,
    ) -> None:
        """从 structure.json 更新附注表格数据（支持新增浮动行）"""
        from app.models.report_models import DisclosureNote
        from sqlalchemy.orm.attributes import flag_modified

        result = await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
            )
        )
        note = result.scalar_one_or_none()
        if not note:
            return

        sheet = structure["sheets"][0] if structure.get("sheets") else {}
        cells = sheet.get("cells", {})

        # 重建 table_data
        td = note.table_data or {}
        headers = td.get("headers", [])
        num_data_cols = len(headers) - 1 if headers else 0

        # 确定数据行数（从 structure 中推断，跳过表头行0）
        max_row = 0
        for key in cells:
            parts = key.split(":")
            if len(parts) == 2:
                r = int(parts[0])
                if r > max_row:
                    max_row = r

        # 重建 rows（支持新增行）
        new_rows = []
        for r in range(1, max_row + 1):
            # 标签列
            label_cell = cells.get(f"{r}:0", {})
            label = label_cell.get("value", "")

            # 数据列
            values = []
            for c in range(1, num_data_cols + 1):
                cell = cells.get(f"{r}:{c}", {})
                values.append(cell.get("value"))

            # 检测是否为合计行
            is_total = bool(label_cell.get("style", {}).get("bold")) and "合计" in str(label)

            row_data: dict[str, Any] = {"label": label, "values": values}
            if is_total:
                row_data["is_total"] = True

            # 保留 _cell_modes（如果原行存在）
            old_rows = td.get("rows", [])
            if r - 1 < len(old_rows) and old_rows[r - 1].get("_cell_modes"):
                row_data["_cell_modes"] = old_rows[r - 1]["_cell_modes"]

            new_rows.append(row_data)

        td["rows"] = new_rows
        note.table_data = td
        flag_modified(note, "table_data")
        await db.flush()


# ═══ 3. 报表适配器 ═══

class FinancialReportAdapter:
    """报表 ↔ 三形式联动

    支持用户上传自定义报表格式 Excel，
    解析后绑定取数公式生成报表。
    """

    @staticmethod
    async def report_to_structure(
        db: AsyncSession, project_id: UUID, year: int, report_type: str,
    ) -> dict:
        """从报表数据生成 structure.json"""
        from app.models.report_models import FinancialReport

        result = await db.execute(
            sa.select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == report_type,
                FinancialReport.is_deleted == sa.false(),
            ).order_by(FinancialReport.row_order)
        )
        rows = result.scalars().all()

        cells = {}
        # 表头
        headers = ["项目", "行次", "期末余额", "期初余额"]
        for c, h in enumerate(headers):
            cells[f"0:{c}"] = {"value": h, "style": {"bold": True, "textAlign": "center"}}

        # 数据行
        for r, row in enumerate(rows):
            indent = row.indent_level or 0
            is_total = row.is_total_row or False
            style = {"bold": True} if is_total else {}
            if indent > 0:
                style["paddingLeft"] = f"{indent * 16}px"

            cells[f"{r+1}:0"] = {"value": row.row_name, "style": style}
            cells[f"{r+1}:1"] = {"value": row.row_code}
            cells[f"{r+1}:2"] = {"value": float(row.amount) if row.amount else None,
                                  "formula": row.formula_used}
            cells[f"{r+1}:3"] = {"value": float(row.prior_amount) if row.prior_amount else None}

        return {
            "sheets": [{
                "name": _report_type_label(report_type),
                "cols": [{"width": 200}, {"width": 60}, {"width": 130}, {"width": 130}],
                "rows": [{"height": 22}] * (len(rows) + 1),
                "cells": cells,
                "merges": [],
            }],
            "metadata": {
                "module": "financial_report",
                "report_type": report_type,
                "project_id": str(project_id),
                "year": year,
                "row_count": len(rows),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            },
        }


# ═══ 4. 调整分录汇总适配器 ═══

class AdjustmentSummaryAdapter:
    """调整分录汇总 ↔ 三形式联动"""

    @staticmethod
    async def summary_to_structure(
        db: AsyncSession, project_id: UUID, year: int, entry_type: str = "aje",
    ) -> dict:
        """从调整分录生成汇总表 structure.json"""
        from app.models.audit_platform_models import Adjustment, AdjustmentEntry

        result = await db.execute(
            sa.select(Adjustment, AdjustmentEntry)
            .join(AdjustmentEntry, AdjustmentEntry.adjustment_id == Adjustment.id)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.entry_type == entry_type,
                Adjustment.is_deleted == sa.false(),
            )
            .order_by(Adjustment.entry_number, AdjustmentEntry.id)
        )
        rows_data = result.all()

        cells = {}
        headers = ["编号", "摘要", "科目编码", "科目名称", "借方", "贷方"]
        for c, h in enumerate(headers):
            cells[f"0:{c}"] = {"value": h, "style": {"bold": True, "textAlign": "center"}}

        for r, (adj, entry) in enumerate(rows_data):
            cells[f"{r+1}:0"] = {"value": adj.entry_number}
            cells[f"{r+1}:1"] = {"value": adj.description or ""}
            cells[f"{r+1}:2"] = {"value": entry.account_code}
            cells[f"{r+1}:3"] = {"value": entry.account_name or ""}
            cells[f"{r+1}:4"] = {"value": float(entry.debit_amount) if entry.debit_amount else None}
            cells[f"{r+1}:5"] = {"value": float(entry.credit_amount) if entry.credit_amount else None}

        return {
            "sheets": [{
                "name": f"{'审计'if entry_type=='aje' else '重分类'}调整分录",
                "cols": [{"width": 60}, {"width": 200}, {"width": 80}, {"width": 150}, {"width": 120}, {"width": 120}],
                "rows": [{"height": 22}] * (len(rows_data) + 1),
                "cells": cells,
                "merges": [],
            }],
            "metadata": {
                "module": "adjustment_summary",
                "entry_type": entry_type,
                "project_id": str(project_id),
                "year": year,
                "entry_count": len(rows_data),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            },
        }


# ═══ 5. 试算表适配器 ═══

class TrialBalanceAdapter:
    """试算表 ↔ 三形式联动"""

    @staticmethod
    async def tb_to_structure(
        db: AsyncSession, project_id: UUID, year: int,
    ) -> dict:
        """从试算表生成 structure.json"""
        from app.models.audit_platform_models import TrialBalance

        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            ).order_by(TrialBalance.standard_account_code)
        )
        rows = result.scalars().all()

        cells = {}
        headers = ["科目编码", "科目名称", "类别", "期初余额", "未审数", "AJE调整", "RJE调整", "审定数"]
        for c, h in enumerate(headers):
            cells[f"0:{c}"] = {"value": h, "style": {"bold": True, "textAlign": "center"}}

        for r, row in enumerate(rows):
            cells[f"{r+1}:0"] = {"value": row.standard_account_code}
            cells[f"{r+1}:1"] = {"value": row.account_name or ""}
            cells[f"{r+1}:2"] = {"value": row.account_category or ""}
            cells[f"{r+1}:3"] = {"value": float(row.opening_balance) if row.opening_balance else None}
            cells[f"{r+1}:4"] = {"value": float(row.unadjusted_amount) if row.unadjusted_amount else None}
            cells[f"{r+1}:5"] = {"value": float(row.aje_adjustment) if row.aje_adjustment else None}
            cells[f"{r+1}:6"] = {"value": float(row.rje_adjustment) if row.rje_adjustment else None}
            cells[f"{r+1}:7"] = {"value": float(row.audited_amount) if row.audited_amount else None}

        return {
            "sheets": [{
                "name": "试算表",
                "cols": [{"width": 80}, {"width": 150}, {"width": 60}, {"width": 110},
                         {"width": 110}, {"width": 100}, {"width": 100}, {"width": 110}],
                "rows": [{"height": 22}] * (len(rows) + 1),
                "cells": cells,
                "merges": [],
            }],
            "metadata": {
                "module": "trial_balance",
                "project_id": str(project_id),
                "year": year,
                "row_count": len(rows),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            },
        }


# ═══ 6. 合并差额表适配器 ═══

class ConsolWorksheetAdapter:
    """合并差额表 ↔ 三形式联动"""

    @staticmethod
    async def consol_to_structure(
        db: AsyncSession, project_id: UUID, year: int,
    ) -> dict:
        """从合并差额表生成 structure.json（多企业宽表）"""
        try:
            from app.models.consolidation_models import ConsolWorksheet
        except ImportError:
            return {"sheets": [], "metadata": {"module": "consol_worksheet", "error": "model not available"}}

        result = await db.execute(
            sa.select(ConsolWorksheet).where(
                ConsolWorksheet.project_id == project_id,
                ConsolWorksheet.year == year,
            ).order_by(ConsolWorksheet.account_code)
        )
        rows = result.scalars().all()

        cells = {}
        headers = ["科目编码", "科目名称", "子公司汇总", "调整借方", "调整贷方", "抵消借方", "抵消贷方", "差额净额", "合并数"]
        for c, h in enumerate(headers):
            cells[f"0:{c}"] = {"value": h, "style": {"bold": True, "textAlign": "center"}}

        for r, row in enumerate(rows):
            cells[f"{r+1}:0"] = {"value": row.account_code}
            cells[f"{r+1}:1"] = {"value": ""}  # account_name 需从 trial_balance 关联获取
            cells[f"{r+1}:2"] = {"value": float(row.children_amount_sum) if row.children_amount_sum else None}
            cells[f"{r+1}:3"] = {"value": float(row.adjustment_debit) if row.adjustment_debit else None}
            cells[f"{r+1}:4"] = {"value": float(row.adjustment_credit) if row.adjustment_credit else None}
            cells[f"{r+1}:5"] = {"value": float(row.elimination_debit) if row.elimination_debit else None}
            cells[f"{r+1}:6"] = {"value": float(row.elimination_credit) if row.elimination_credit else None}
            cells[f"{r+1}:7"] = {"value": float(row.net_difference) if row.net_difference else None}
            cells[f"{r+1}:8"] = {"value": float(row.consolidated_amount) if row.consolidated_amount else None}

        return {
            "sheets": [{
                "name": "合并差额表",
                "cols": [{"width": 80}, {"width": 150}] + [{"width": 110}] * 7,
                "rows": [{"height": 22}] * (len(rows) + 1),
                "cells": cells,
                "merges": [],
            }],
            "metadata": {
                "module": "consol_worksheet",
                "project_id": str(project_id),
                "year": year,
                "row_count": len(rows),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            },
        }


# ═══ 统一入口 ═══

async def module_to_structure(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    module: str,
    **kwargs,
) -> dict:
    """统一入口：任意模块 → structure.json

    module 取值：workpaper / disclosure_note / financial_report /
                 adjustment_summary / trial_balance / consol_worksheet
    """
    if module == "workpaper":
        return await WorkpaperAdapter.wp_to_structure(db, project_id, kwargs.get("wp_code", "")) or {}
    elif module == "disclosure_note":
        return await DisclosureNoteAdapter.note_to_structure(db, project_id, year, kwargs.get("note_section", "")) or {}
    elif module == "financial_report":
        return await FinancialReportAdapter.report_to_structure(db, project_id, year, kwargs.get("report_type", "BS"))
    elif module == "adjustment_summary":
        return await AdjustmentSummaryAdapter.summary_to_structure(db, project_id, year, kwargs.get("entry_type", "aje"))
    elif module == "trial_balance":
        return await TrialBalanceAdapter.tb_to_structure(db, project_id, year)
    elif module == "consol_worksheet":
        return await ConsolWorksheetAdapter.consol_to_structure(db, project_id, year)
    else:
        return {"error": f"未知模块: {module}"}


async def module_to_html(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    module: str,
    editable: bool = False,
    **kwargs,
) -> str:
    """统一入口：任意模块 → HTML"""
    structure = await module_to_structure(db, project_id, year, module, **kwargs)
    if not structure or "error" in structure:
        return f"<p>无数据: {structure.get('error', '')}</p>"
    return structure_to_html(structure, editable=editable)


async def module_to_excel(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    module: str,
    output_path: str,
    **kwargs,
) -> str:
    """统一入口：任意模块 → Excel 文件"""
    structure = await module_to_structure(db, project_id, year, module, **kwargs)
    if not structure or "error" in structure:
        raise ValueError(f"无法生成: {structure.get('error', '')}")
    return structure_to_excel(structure, output_path)


async def module_to_word(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    module: str,
    output_path: str,
    **kwargs,
) -> str:
    """统一入口：任意模块 → Word 文件（致同三线表排版）"""
    from app.services.excel_html_converter import structure_to_word

    structure = await module_to_structure(db, project_id, year, module, **kwargs)
    if not structure or "error" in structure:
        raise ValueError(f"无法生成: {structure.get('error', '')}")
    return structure_to_word(structure, output_path)


# ═══ 辅助函数 ═══

def _report_type_label(report_type: str) -> str:
    labels = {"BS": "资产负债表", "IS": "利润表", "CFS": "现金流量表", "EQ": "所有者权益变动表"}
    return labels.get(report_type, report_type)
