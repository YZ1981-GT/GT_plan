"""L7 其他非流动负债 — 业务逻辑服务

纯函数计算引擎 + xlsx导入导出逻辑。

提供功能：
- 负债类公式方向验证（贷方科目：期末=期初+贷方-借方）
- 导出模板 / 导出数据 / 导入数据

科目2801其他非流动负债（贷方/负债类）：期末=期初+贷方-借方
L筹资循环最简标准负债底稿，无复杂计算引擎。

Requirements: 5.1-5.5
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import uuid4

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式验证（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_direction(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验负债类贷方公式方向

    负债类贷方：期末 = 期初 + 贷方 − 借方

    Requirements: 5.1-5.3
    """
    expected = begin + credit - debit
    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": "期末=期初+贷方-借方（负债类贷方）",
        "direction": "liability",
    }

    if reported_end is not None:
        diff = reported_end - expected
        result["reported"] = reported_end
        result["difference"] = round(diff, 2)
        result["isValid"] = abs(diff) <= 0.01

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# L7 各sheet导出配置
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "L7-1": {
        "title": "L7-1 审定表",
        "headers": [
            "项目", "期初余额", "贷方发生额", "借方发生额", "期末余额",
            "未审数", "审计调整", "重分类调整", "审定数", "差异", "备注",
        ],
        "fields": [
            "itemName", "beginBalance", "creditAmount", "debitAmount", "endBalance",
            "unadjustedAmount", "ajeAmount", "rjeAmount", "auditedAmount", "difference", "remark",
        ],
    },
    "L7-2": {
        "title": "L7-2 明细表",
        "headers": [
            "项目名称", "性质", "形成原因", "合同编号", "对方单位",
            "起始日", "到期日", "币种", "合同金额", "期初余额",
            "本期增加", "本期减少", "期末余额", "是否逾期", "到期情况",
            "利率", "担保方式", "抵质押物", "关联方标识", "备注",
        ],
        "fields": [
            "itemName", "nature", "formReason", "contractNo", "counterparty",
            "startDate", "maturityDate", "currency", "contractAmount", "beginBalance",
            "periodIncrease", "periodDecrease", "endBalance", "isOverdue", "maturityStatus",
            "interestRate", "guaranteeMethod", "pledgeAsset", "relatedPartyFlag", "remark",
        ],
    },
    "L7-3": {
        "title": "L7-3 调整分录",
        "headers": [
            "调整类型", "科目编码", "科目名称", "摘要",
            "借方金额", "贷方金额", "备注",
        ],
        "fields": [
            "adjustmentType", "accountCode", "accountName", "summary",
            "debitAmount", "creditAmount", "remark",
        ],
    },
    "L7-4": {
        "title": "L7-4 检查表",
        "headers": [
            "检查项目", "检查内容", "检查结果", "结论",
            "问题描述", "建议", "备注",
        ],
        "fields": [
            "checkItem", "checkContent", "checkResult", "conclusion",
            "issueDesc", "suggestion", "remark",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "beginBalance", "creditAmount", "debitAmount", "endBalance",
    "unadjustedAmount", "ajeAmount", "rjeAmount", "auditedAmount", "difference",
    "contractAmount", "periodIncrease", "periodDecrease", "interestRate",
    "debitAmount", "creditAmount",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 导出辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _style_header_row(ws: Any) -> None:
    """给表头行设置样式"""
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = max(
            len(str(cell.value or "")) * 2 + 4, 12
        )
    ws.freeze_panes = "A2"


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(wp_id: str, db: Any, sheet: str | None = None) -> io.BytesIO:
    """生成空白xlsx模板（多sheet或单sheet）

    Requirements: 5.5
    """
    wb = Workbook()
    wb.remove(wb.active)

    configs_to_export = _SHEET_CONFIGS
    if sheet and sheet in _SHEET_CONFIGS:
        configs_to_export = {sheet: _SHEET_CONFIGS[sheet]}

    for _sheet_key, config in configs_to_export.items():
        ws = wb.create_sheet(title=config["title"][:31])
        for col_idx, header in enumerate(config["headers"], 1):
            ws.cell(row=1, column=col_idx, value=header)
        _style_header_row(ws)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(wp_id: str, db: Any, sheet: str | None = None) -> io.BytesIO:
    """导出当前数据为xlsx（多sheet或单sheet）

    从 checklist_responses 读取已保存的数据并填入xlsx。

    Requirements: 5.5
    """
    import sqlalchemy as sa

    wb = Workbook()
    wb.remove(wb.active)

    configs_to_export = _SHEET_CONFIGS
    if sheet and sheet in _SHEET_CONFIGS:
        configs_to_export = {sheet: _SHEET_CONFIGS[sheet]}

    for sheet_key, config in configs_to_export.items():
        ws = wb.create_sheet(title=config["title"][:31])
        for col_idx, header in enumerate(config["headers"], 1):
            ws.cell(row=1, column=col_idx, value=header)
        _style_header_row(ws)

        # 读取对应数据
        item_id = f"L7-{sheet_key}-rows"
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
            ),
            {"wp_id": wp_id, "item_id": item_id},
        )
        row = result.fetchone()
        data_rows: list[dict] = []
        if row and row.remark:
            try:
                data_rows = json.loads(row.remark)
            except (json.JSONDecodeError, TypeError):
                pass

        for data_row in data_rows:
            row_values = [data_row.get(f, "") or "" for f in config["fields"]]
            ws.append(row_values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


async def import_data(
    wp_id: str, file_content: bytes, db: Any, sheet: str | None = None
) -> dict[str, Any]:
    """解析上传的xlsx并写入checklist_responses

    支持多sheet导入（自动识别区段）或单sheet导入。

    Requirements: 5.5
    """
    import sqlalchemy as sa

    if len(file_content) > 10 * 1024 * 1024:
        raise ValueError("文件大小超过 10MB 限制")

    try:
        wb = load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    except Exception:
        raise ValueError("无法解析xlsx文件")

    imported_counts: dict[str, int] = {}
    warnings: list[str] = []

    for ws in wb.worksheets:
        ws_title = ws.title.strip()

        # 尝试匹配到配置
        matched_config: dict[str, Any] | None = None
        matched_key: str | None = None

        for sheet_key, config in _SHEET_CONFIGS.items():
            if config["title"][:31] == ws_title or sheet_key in ws_title:
                matched_config = config
                matched_key = sheet_key
                break

        if not matched_config or not matched_key:
            continue

        # 若指定了sheet，跳过不匹配的
        if sheet and matched_key != sheet:
            continue

        # 读取表头
        actual_headers: list[str] = []
        for cell in next(ws.iter_rows(min_row=1, max_row=1)):
            if cell.value is not None:
                actual_headers.append(str(cell.value).strip())

        # 校验表头结构
        expected_headers = matched_config["headers"]
        if actual_headers and actual_headers[:3] != expected_headers[:3]:
            warnings.append(f"Sheet '{ws_title}' 表头结构不匹配，尝试按位置解析")

        # 解析数据行
        parsed_rows: list[dict] = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if row_idx > _ROW_LIMIT + 1:
                warnings.append(f"Sheet '{ws_title}' 超过 {_ROW_LIMIT} 行限制，已截断")
                break
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            row_data: dict[str, Any] = {"rowId": str(uuid4())}
            fields = matched_config["fields"]
            headers = matched_config["headers"]

            for i, (header, field) in enumerate(zip(headers, fields)):
                try:
                    header_idx = actual_headers.index(header)
                    raw_val = row[header_idx] if header_idx < len(row) else None
                except (ValueError, IndexError):
                    raw_val = row[i] if i < len(row) else None

                if field in _NUMERIC_FIELDS:
                    row_data[field] = _safe_float(raw_val)
                else:
                    row_data[field] = _safe_str(raw_val)

            parsed_rows.append(row_data)

        imported_counts[matched_key] = len(parsed_rows)

        # 写入 checklist_responses
        item_id = f"L7-{matched_key}-rows"
        json_str = json.dumps(parsed_rows, ensure_ascii=False)
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                "VALUES (:id, :wp_id, :item_id, :remark) "
                "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
            ),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": json_str},
        )

    await db.flush()

    return {
        "imported_count": sum(imported_counts.values()),
        "imported_counts": imported_counts,
        "warnings": warnings,
    }
