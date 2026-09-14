"""M3 库存股 — 业务逻辑服务

提供功能：
- 导出模板 / 导出数据 / 导入数据（xlsx三级）
- 外币折算批量计算
- 回购注销核对
- TB取数（科目4002）

科目4002库存股（**借方/权益备抵类！**）：期末=期初+借方-贷方
回购在借方增加，注销/再售在贷方减少，与M2/M4/M5/M6方向相反！

Requirements: 5.2, 5.4, 7.7
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

_M3_ACCOUNT_CODE = "4002"
_ROW_LIMIT = 500


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "M3-2": {
        "title": "M3-2 明细表（回购批次）",
        "headers": [
            "回购批次", "回购日期", "回购股数", "回购单价", "回购金额",
            "注销股数", "注销金额", "期初库存股数", "期初金额",
            "本期回购股数", "本期回购金额", "本期注销股数", "本期注销金额",
            "期末库存股数", "期末金额", "币种", "汇率", "折算本位币", "备注",
        ],
        "fields": [
            "batchName", "repurchaseDate", "repurchaseShares", "repurchasePrice",
            "repurchaseAmount", "cancelShares", "cancelAmount",
            "beginShares", "beginAmount", "periodRepurchaseShares", "periodRepurchaseAmount",
            "periodCancelShares", "periodCancelAmount", "endShares", "endAmount",
            "currency", "exchangeRate", "convertedAmount", "remark",
        ],
    },
    "M3-4": {
        "title": "M3-4 外币投资汇率测算表",
        "headers": [
            "回购批次", "原币回购额", "币种", "回购日汇率",
            "折算本位币", "账面本位币", "折算差异", "备注",
        ],
        "fields": [
            "batchName", "foreignAmount", "currency", "exchangeRate",
            "convertedAmount", "bookedAmount", "fxDiff", "remark",
        ],
    },
    "M3-5": {
        "title": "M3-5 库存股检查表（回购/注销核对）",
        "headers": [
            "批次", "回购决议", "回购股数", "回购单价", "回购总额",
            "回购核对结果", "注销股数", "注销金额",
            "冲减实收资本(M2)", "冲减资本公积(M4)", "冲减差额", "差额处理", "备注",
        ],
        "fields": [
            "batchName", "resolution", "repurchaseShares", "repurchasePrice",
            "repurchaseTotal", "repurchaseCheckResult",
            "cancelShares", "cancelAmount", "deductCapital", "deductReserve",
            "cancelDiff", "diffTreatment", "remark",
        ],
    },
}

_HEADER_FONT = Font(bold=True, size=11)
_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HEADER_FONT_WHITE = Font(bold=True, size=11, color="FFFFFF")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(
    wp_id: str,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出空白xlsx模板

    Args:
        wp_id: 底稿ID
        db: 数据库会话
        sheet: 可选，指定导出单个sheet（M3-2/M3-4/M3-5）

    Requirements: 7.7
    """
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = [sheet] if sheet and sheet in _SHEET_CONFIGS else list(_SHEET_CONFIGS.keys())

    for sheet_key in sheets_to_export:
        cfg = _SHEET_CONFIGS[sheet_key]
        ws = wb.create_sheet(title=cfg["title"])

        # 写入表头
        for col_idx, header in enumerate(cfg["headers"], start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = _HEADER_FONT_WHITE
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        # 设置列宽
        for col_idx in range(1, len(cfg["headers"]) + 1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 15

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(
    wp_id: str,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出含当前数据的xlsx

    Args:
        wp_id: 底稿ID
        db: 数据库会话
        sheet: 可选，指定导出单个sheet

    Requirements: 7.7
    """
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = [sheet] if sheet and sheet in _SHEET_CONFIGS else list(_SHEET_CONFIGS.keys())

    for sheet_key in sheets_to_export:
        cfg = _SHEET_CONFIGS[sheet_key]
        ws = wb.create_sheet(title=cfg["title"])

        # 写入表头
        for col_idx, header in enumerate(cfg["headers"], start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = _HEADER_FONT_WHITE
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        # 从 checklist_responses 取数据
        prefix = f"M3-{sheet_key.split('-')[1]}-" if "-" in sheet_key else f"{sheet_key}-"
        try:
            result = await db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses WHERE wp_id = :wp_id "
                    "AND item_id LIKE :prefix "
                    "ORDER BY item_id "
                    "LIMIT :lim"
                ),
                {"wp_id": wp_id, "prefix": f"{prefix}%", "lim": _ROW_LIMIT},
            )
            row_idx = 2
            for db_row in result.fetchall():
                raw = db_row.conclusion or ""
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw) if raw.startswith("{") else {}
                except (json.JSONDecodeError, TypeError):
                    parsed = {}
                if not isinstance(parsed, dict):
                    continue
                for col_idx, field in enumerate(cfg["fields"], start=1):
                    val = parsed.get(field, "")
                    ws.cell(row=row_idx, column=col_idx, value=val)
                row_idx += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("M3 export_data: 查询失败 wp_id=%s sheet=%s: %s", wp_id, sheet_key, e)

        # 设置列宽
        for col_idx in range(1, len(cfg["headers"]) + 1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 15

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


async def import_data(
    wp_id: str,
    content: bytes,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses

    Args:
        wp_id: 底稿ID
        content: xlsx文件内容
        db: 数据库会话
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.7
    """
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(f"无法解析xlsx文件: {e}") from e

    imported_count = 0
    warnings: list[str] = []

    sheets_to_import = [sheet] if sheet and sheet in _SHEET_CONFIGS else list(_SHEET_CONFIGS.keys())

    for sheet_key in sheets_to_import:
        cfg = _SHEET_CONFIGS[sheet_key]
        # 尝试匹配工作簿中的sheet
        ws = None
        for ws_name in wb.sheetnames:
            if sheet_key in ws_name or cfg["title"] in ws_name:
                ws = wb[ws_name]
                break

        if ws is None:
            if sheet:  # 指定了单sheet但找不到
                warnings.append(f"未找到sheet: {sheet_key}")
            continue

        # 解析数据行（跳过表头）
        fields = cfg["fields"]
        prefix = f"M3-{sheet_key.split('-')[1]}-" if "-" in sheet_key else f"{sheet_key}-"

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
            if row_idx > _ROW_LIMIT:
                warnings.append(f"{sheet_key}: 超过{_ROW_LIMIT}行限制，截断")
                break

            # 跳过全空行
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue

            row_data: dict[str, Any] = {}
            for col_idx, field in enumerate(fields):
                if col_idx < len(row):
                    val = row[col_idx]
                    row_data[field] = val if val is not None else ""
                else:
                    row_data[field] = ""

            item_id = f"{prefix}row-{row_idx}"
            conclusion_json = json.dumps(row_data, ensure_ascii=False)

            # UPSERT checklist_responses
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses (id, wp_id, item_id, conclusion) "
                    "VALUES (:id, :wp_id, :item_id, :conclusion) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE SET conclusion = :conclusion"
                ),
                {
                    "id": str(uuid4()),
                    "wp_id": wp_id,
                    "item_id": item_id,
                    "conclusion": conclusion_json,
                },
            )
            imported_count += 1

    wb.close()
    return {"imported_count": imported_count, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════════
# TB 取数（科目4002库存股）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_tb_seed(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """获取TB科目4002库存股的种子数据

    查 tb_balance 科目4002（库存股），返回借方/贷方发生额和当前净额。
    库存股为权益备抵借方科目：current_amount = debit - credit（借方净额）

    Requirements: 7.7
    """
    # 先获取底稿对应的 project_id 和 year
    try:
        wp_row = (
            await db.execute(
                sa.text(
                    "SELECT w.project_id, p.audit_year "
                    "FROM working_paper w "
                    "JOIN projects p ON w.project_id = p.id "
                    "WHERE w.id = :wp_id"
                ),
                {"wp_id": wp_id},
            )
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("M3 tb_seed: 查询 working_paper 失败 wp_id=%s: %s", wp_id, e)
        return _empty_tb_result()

    if not wp_row:
        return _empty_tb_result()

    project_id = str(wp_row.project_id)
    year = str(wp_row.audit_year) if wp_row.audit_year else ""

    # 查 tb_balance 科目 4002
    try:
        active_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, year
        )
        result = await db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                active_filter,
                sa.or_(
                    TbBalance.account_code == _M3_ACCOUNT_CODE,
                    TbBalance.account_code.startswith(_M3_ACCOUNT_CODE),
                ),
            )
        )
        total_debit = 0.0
        total_credit = 0.0
        matched = False
        for row in result.fetchall():
            total_debit += float(row.debit_amount or 0)
            total_credit += float(row.credit_amount or 0)
            matched = True

        if matched:
            return {
                "account_code": _M3_ACCOUNT_CODE,
                "debit_amount": round(total_debit, 2),
                "credit_amount": round(total_credit, 2),
                "current_amount": round(total_debit - total_credit, 2),
                "direction": "debit",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("M3 tb_seed: TB查询失败 project=%s year=%s: %s", project_id, year, e)

    return _empty_tb_result()


def _empty_tb_result() -> dict[str, Any]:
    """返回空的TB结果（科目4002未找到）。"""
    return {
        "account_code": _M3_ACCOUNT_CODE,
        "debit_amount": 0.0,
        "credit_amount": 0.0,
        "current_amount": 0.0,
        "direction": "debit",
    }
