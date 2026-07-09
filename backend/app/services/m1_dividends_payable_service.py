"""M1 应付股利（利润）— 服务层

外币折算 + 股利测算 + 导入导出

科目编码: 2232应付股利（贷方/负债类）
公式方向: 期末=期初+贷方-借方

Requirements: 4.2, 5.3, 7.7
"""

from __future__ import annotations

import io
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# 导入导出涉及的3个sheet
EXPORT_SHEETS = ["M1-2", "M1-4", "M1-5"]
SHEET_NAMES = {
    "M1-2": "M1-2 明细表",
    "M1-4": "M1-4 外币汇率",
    "M1-5": "M1-5 股利测算",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 公式验证（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_formulas(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验负债类公式方向：期末=期初+贷方-借方

    应付股利为贷方/负债类科目：
    - 宣告分配时贷方增加
    - 实际支付时借方减少
    """
    calculated_end = begin + credit - debit

    result: dict[str, Any] = {
        "begin": begin,
        "credit": credit,
        "debit": debit,
        "calculatedEnd": round(calculated_end, 2),
        "formula": "期末 = 期初 + 贷方(宣告) - 借方(支付)",
        "direction": "credit",  # 贷方科目
        "isValid": True,
    }

    if reported_end is not None:
        diff = round(calculated_end - reported_end, 2)
        result["reportedEnd"] = reported_end
        result["diff"] = diff
        result["isValid"] = abs(diff) < 0.01

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 外币折算（M1-4）
# ═══════════════════════════════════════════════════════════════════════════════


async def calc_fx_conversion(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
) -> dict[str, Any]:
    """外币折算计算 — 从checklist_responses取M1-4数据并计算

    折算本位币 = 原币金额 × 期末汇率
    汇兑差异 = 折算本位币 - 账面本位币
    """
    # 从 checklist_responses 读取 M1-4 sheet 的已存数据
    result = await db.execute(
        sa.text("""
            SELECT item_id, value
            FROM checklist_responses
            WHERE wp_id = :wp_id AND item_id LIKE 'M1-4-%'
            ORDER BY item_id
        """),
        {"wp_id": wp_id},
    )
    rows = result.fetchall()

    # 按股东行分组解析
    items: list[dict[str, Any]] = []
    row_data: dict[str, dict[str, Any]] = {}

    for row in rows:
        item_id = row.item_id
        value = row.value
        # item_id format: M1-4-{row_idx}-{field}
        parts = item_id.split("-")
        if len(parts) >= 4:
            row_key = parts[2]
            field = "-".join(parts[3:])
            if row_key not in row_data:
                row_data[row_key] = {}
            row_data[row_key][field] = value

    total_fx_diff = 0.0
    material_threshold = 1000.0  # 汇兑差异重要性阈值

    for row_key in sorted(row_data.keys()):
        data = row_data[row_key]
        original_amount = _safe_float(data.get("original_amount", 0))
        rate = _safe_float(data.get("rate", 0))
        booked = _safe_float(data.get("booked", 0))

        converted = round(original_amount * rate, 2)
        fx_diff = round(converted - booked, 2)
        total_fx_diff += fx_diff

        items.append({
            "shareholder": data.get("shareholder", ""),
            "currency": data.get("currency", ""),
            "original_amount": original_amount,
            "rate": rate,
            "converted": converted,
            "booked": booked,
            "fx_diff": fx_diff,
        })

    return {
        "items": items,
        "total_fx_diff": round(total_fx_diff, 2),
        "has_material_diff": abs(total_fx_diff) > material_threshold,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 股利测算（M1-5）
# ═══════════════════════════════════════════════════════════════════════════════


async def calc_dividend_estimation(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
) -> dict[str, Any]:
    """股利测算 — 从checklist_responses取M1-5数据并计算

    应宣告股利 = 可供分配利润 × 分配比例
    宣告差异 = 测算宣告 - 账面宣告
    """
    result = await db.execute(
        sa.text("""
            SELECT item_id, value
            FROM checklist_responses
            WHERE wp_id = :wp_id AND item_id LIKE 'M1-5-%'
            ORDER BY item_id
        """),
        {"wp_id": wp_id},
    )
    rows = result.fetchall()

    # 按股东行分组解析
    items: list[dict[str, Any]] = []
    row_data: dict[str, dict[str, Any]] = {}

    for row in rows:
        item_id = row.item_id
        value = row.value
        parts = item_id.split("-")
        if len(parts) >= 4:
            row_key = parts[2]
            field = "-".join(parts[3:])
            if row_key not in row_data:
                row_data[row_key] = {}
            row_data[row_key][field] = value

    total_estimated = 0.0
    total_booked = 0.0
    material_threshold = 1000.0

    for row_key in sorted(row_data.keys()):
        data = row_data[row_key]
        profit = _safe_float(data.get("distributable_profit", 0))
        ratio = _safe_float(data.get("ratio", 0))
        booked = _safe_float(data.get("booked_dividend", 0))

        estimated = round(profit * ratio, 2)
        diff = round(estimated - booked, 2)
        total_estimated += estimated
        total_booked += booked

        items.append({
            "shareholder": data.get("shareholder", ""),
            "distributable_profit": profit,
            "ratio": ratio,
            "estimated_dividend": estimated,
            "booked_dividend": booked,
            "diff": diff,
        })

    total_diff = round(total_estimated - total_booked, 2)

    return {
        "items": items,
        "total_estimated": round(total_estimated, 2),
        "total_booked": round(total_booked, 2),
        "total_diff": total_diff,
        "has_material_diff": abs(total_diff) > material_threshold,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(wp_id: str, db: AsyncSession) -> io.BytesIO:
    """导出空白xlsx模板（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算）"""
    from openpyxl import Workbook

    wb = Workbook()
    # 删除默认sheet
    wb.remove(wb.active)

    # M1-2 明细表
    ws2 = wb.create_sheet("M1-2 明细表")
    ws2.append([
        "股东名称", "持股比例(%)", "币种",
        "期初应付", "本期宣告", "本期支付", "期末应付",
        "备注",
    ])

    # M1-4 外币汇率
    ws4 = wb.create_sheet("M1-4 外币汇率")
    ws4.append([
        "股东名称", "原币金额", "币种", "期末汇率",
        "折算本位币", "账面本位币", "汇兑差异",
    ])

    # M1-5 股利测算
    ws5 = wb.create_sheet("M1-5 股利测算")
    ws5.append([
        "股东名称", "可供分配利润", "分配比例(%)",
        "应宣告股利", "账面宣告", "差异", "备注",
    ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(wp_id: str, db: AsyncSession) -> io.BytesIO:
    """导出含当前数据的xlsx（3个sheet）"""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)

    # 读取 checklist_responses 中的 M1 数据
    result = await db.execute(
        sa.text("""
            SELECT item_id, value
            FROM checklist_responses
            WHERE wp_id = :wp_id AND (
                item_id LIKE 'M1-2-%' OR
                item_id LIKE 'M1-4-%' OR
                item_id LIKE 'M1-5-%'
            )
            ORDER BY item_id
        """),
        {"wp_id": wp_id},
    )
    rows = result.fetchall()

    # 分组
    sheet_data: dict[str, dict[str, dict[str, Any]]] = {
        "M1-2": {},
        "M1-4": {},
        "M1-5": {},
    }

    for row in rows:
        item_id = row.item_id
        value = row.value
        parts = item_id.split("-")
        if len(parts) >= 4:
            sheet_key = f"{parts[0]}-{parts[1]}"
            row_key = parts[2]
            field = "-".join(parts[3:])
            if sheet_key in sheet_data:
                if row_key not in sheet_data[sheet_key]:
                    sheet_data[sheet_key][row_key] = {}
                sheet_data[sheet_key][row_key][field] = value

    # M1-2 明细表
    ws2 = wb.create_sheet("M1-2 明细表")
    ws2.append(["股东名称", "持股比例(%)", "币种", "期初应付", "本期宣告", "本期支付", "期末应付", "备注"])
    for row_key in sorted(sheet_data["M1-2"].keys()):
        d = sheet_data["M1-2"][row_key]
        ws2.append([
            d.get("shareholder", ""),
            d.get("ratio", ""),
            d.get("currency", ""),
            d.get("begin", ""),
            d.get("credit", ""),
            d.get("debit", ""),
            d.get("end", ""),
            d.get("note", ""),
        ])

    # M1-4 外币汇率
    ws4 = wb.create_sheet("M1-4 外币汇率")
    ws4.append(["股东名称", "原币金额", "币种", "期末汇率", "折算本位币", "账面本位币", "汇兑差异"])
    for row_key in sorted(sheet_data["M1-4"].keys()):
        d = sheet_data["M1-4"][row_key]
        ws4.append([
            d.get("shareholder", ""),
            d.get("original_amount", ""),
            d.get("currency", ""),
            d.get("rate", ""),
            d.get("converted", ""),
            d.get("booked", ""),
            d.get("fx_diff", ""),
        ])

    # M1-5 股利测算
    ws5 = wb.create_sheet("M1-5 股利测算")
    ws5.append(["股东名称", "可供分配利润", "分配比例(%)", "应宣告股利", "账面宣告", "差异", "备注"])
    for row_key in sorted(sheet_data["M1-5"].keys()):
        d = sheet_data["M1-5"][row_key]
        ws5.append([
            d.get("shareholder", ""),
            d.get("distributable_profit", ""),
            d.get("ratio", ""),
            d.get("estimated_dividend", ""),
            d.get("booked_dividend", ""),
            d.get("diff", ""),
            d.get("note", ""),
        ])

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
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持3个sheet）"""
    from openpyxl import load_workbook

    buffer = io.BytesIO(content)
    try:
        wb = load_workbook(buffer, read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(f"无法解析xlsx文件: {e}")

    imported_count = 0
    warnings: list[str] = []

    # sheet名称匹配（容错）
    sheet_mapping = {
        "M1-2": ["M1-2 明细表", "M1-2", "明细表"],
        "M1-4": ["M1-4 外币汇率", "M1-4", "外币汇率"],
        "M1-5": ["M1-5 股利测算", "M1-5", "股利测算"],
    }

    for sheet_key, possible_names in sheet_mapping.items():
        ws = None
        for name in possible_names:
            if name in wb.sheetnames:
                ws = wb[name]
                break

        if ws is None:
            continue

        # 跳过表头行
        row_idx = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or all(cell is None or cell == "" for cell in row):
                continue

            row_idx += 1
            fields = _get_field_mapping(sheet_key)

            for col_idx, field in enumerate(fields):
                if col_idx < len(row) and row[col_idx] is not None:
                    item_id = f"{sheet_key}-{row_idx:03d}-{field}"
                    value = str(row[col_idx])

                    await db.execute(
                        sa.text("""
                            INSERT INTO checklist_responses (wp_id, item_id, value)
                            VALUES (:wp_id, :item_id, :value)
                            ON CONFLICT (wp_id, item_id) DO UPDATE SET value = :value
                        """),
                        {"wp_id": wp_id, "item_id": item_id, "value": value},
                    )
                    imported_count += 1

    wb.close()
    return {"imported_count": imported_count, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(val: Any) -> float:
    """安全浮点转换"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _get_field_mapping(sheet_key: str) -> list[str]:
    """获取sheet列→field名映射"""
    if sheet_key == "M1-2":
        return ["shareholder", "ratio", "currency", "begin", "credit", "debit", "end", "note"]
    elif sheet_key == "M1-4":
        return ["shareholder", "original_amount", "currency", "rate", "converted", "booked", "fx_diff"]
    elif sheet_key == "M1-5":
        return ["shareholder", "distributable_profit", "ratio", "estimated_dividend", "booked_dividend", "diff", "note"]
    return []
