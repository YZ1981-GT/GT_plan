"""M10 其他权益工具 — 服务层

科目4003其他权益工具（贷方/权益类）
- 导入导出：M10-2明细表（永续债/优先股动态行）
- CAS37负债权益区分：逐项金融工具判定分类
- 金额守恒：权益部分+负债部分=工具总额

Requirements: 6.6, 4.2-4.3, 6.1-6.3
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── M10-2 明细表列头定义 ────────────────────────────────────────────────────

_M10_2_HEADERS = [
    "序号",
    "工具名称",
    "工具类型",
    "发行日期",
    "到期日/永续",
    "发行金额",
    "票面利率/股息率",
    "期初余额",
    "本期发行",
    "本期赎回/转换",
    "本期利息/股息",
    "期末余额",
    "CAS37分类",
    "备注",
]

_CLASSIFICATION_ITEM_PREFIX = "M10-4-item-"

TOLERANCE = 0.01


def _parse_num(v: Any) -> float:
    """安全解析数值."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (ValueError, TypeError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(
    wp_id: str, db: AsyncSession, *, sheet: str | None = None
) -> io.BytesIO:
    """生成M10空白模板xlsx."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet or "M10-2"

    # 写入列头
    for col_idx, header in enumerate(_M10_2_HEADERS, 1):
        ws.cell(row=1, column=col_idx, value=header)

    # 冻结首行
    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(
    wp_id: str, db: AsyncSession, *, sheet: str | None = None
) -> io.BytesIO:
    """导出当前M10-2明细数据到xlsx."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet or "M10-2"

    # 写入列头
    for col_idx, header in enumerate(_M10_2_HEADERS, 1):
        ws.cell(row=1, column=col_idx, value=header)

    # 从 checklist_responses 读取 M10-2 明细行
    rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, conclusion, evidence "
                "FROM checklist_responses "
                "WHERE wp_id = :wid AND item_id LIKE 'M10-2-row-%' "
                "ORDER BY item_id"
            ),
            {"wid": wp_id},
        )
    ).fetchall()

    row_idx = 2
    for r in rows:
        data: dict[str, Any] = {}
        raw = r.conclusion
        if raw and isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        ws.cell(row=row_idx, column=1, value=row_idx - 1)
        ws.cell(row=row_idx, column=2, value=data.get("instrument_name", ""))
        ws.cell(row=row_idx, column=3, value=data.get("instrument_type", ""))
        ws.cell(row=row_idx, column=4, value=data.get("issue_date", ""))
        ws.cell(row=row_idx, column=5, value=data.get("maturity", ""))
        ws.cell(row=row_idx, column=6, value=_parse_num(data.get("issue_amount")))
        ws.cell(row=row_idx, column=7, value=data.get("coupon_rate", ""))
        ws.cell(row=row_idx, column=8, value=_parse_num(data.get("period_begin")))
        ws.cell(row=row_idx, column=9, value=_parse_num(data.get("issued_this_period")))
        ws.cell(row=row_idx, column=10, value=_parse_num(data.get("redeemed_this_period")))
        ws.cell(row=row_idx, column=11, value=_parse_num(data.get("interest_dividend")))
        ws.cell(row=row_idx, column=12, value=_parse_num(data.get("period_end")))
        ws.cell(row=row_idx, column=13, value=data.get("classification", ""))
        ws.cell(row=row_idx, column=14, value=data.get("remark", ""))
        row_idx += 1

    ws.freeze_panes = "A2"
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


async def import_data(
    wp_id: str, content: bytes, db: AsyncSession, *, sheet: str | None = None
) -> dict[str, Any]:
    """解析xlsx写入checklist_responses（M10-2明细表动态行）."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    target_sheet = sheet or "M10-2"

    # 尝试匹配sheet名
    ws = None
    for name in wb.sheetnames:
        if target_sheet in name:
            ws = wb[name]
            break
    if ws is None:
        ws = wb.active

    if ws is None:
        raise ValueError(f"无法找到工作表 '{target_sheet}'")

    # 解析列头（第1行）
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise ValueError("模板无列头行")

    imported_count = 0
    warnings: list[str] = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
        # 跳过全空行
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue

        # 解析行数据
        row_data: dict[str, Any] = {}
        if len(row) > 1:
            row_data["instrument_name"] = str(row[1] or "").strip()
        if len(row) > 2:
            row_data["instrument_type"] = str(row[2] or "").strip()
        if len(row) > 3:
            row_data["issue_date"] = str(row[3] or "").strip()
        if len(row) > 4:
            row_data["maturity"] = str(row[4] or "").strip()
        if len(row) > 5:
            row_data["issue_amount"] = _parse_num(row[5])
        if len(row) > 6:
            row_data["coupon_rate"] = str(row[6] or "").strip()
        if len(row) > 7:
            row_data["period_begin"] = _parse_num(row[7])
        if len(row) > 8:
            row_data["issued_this_period"] = _parse_num(row[8])
        if len(row) > 9:
            row_data["redeemed_this_period"] = _parse_num(row[9])
        if len(row) > 10:
            row_data["interest_dividend"] = _parse_num(row[10])
        if len(row) > 11:
            row_data["period_end"] = _parse_num(row[11])
        if len(row) > 12:
            row_data["classification"] = str(row[12] or "").strip()
        if len(row) > 13:
            row_data["remark"] = str(row[13] or "").strip()

        # 工具名称为空则跳过
        if not row_data.get("instrument_name"):
            warnings.append(f"第{row_idx + 1}行: 工具名称为空，已跳过")
            continue

        item_id = f"M10-2-row-{row_idx:04d}"
        conclusion_json = json.dumps(row_data, ensure_ascii=False)

        # upsert到checklist_responses
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (wp_id, item_id, conclusion, status) "
                "VALUES (:wid, :iid, :conclusion, 'imported') "
                "ON CONFLICT (wp_id, item_id) "
                "DO UPDATE SET conclusion = :conclusion, status = 'imported'"
            ),
            {"wid": wp_id, "iid": item_id, "conclusion": conclusion_json},
        )
        imported_count += 1

    return {"imported_count": imported_count, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════════
# CAS37 纯函数：负债权益区分判定 (Requirements 4.2-4.3, 6.1-6.3)
# ═══════════════════════════════════════════════════════════════════════════════


def classify_instrument(has_contractual_obligation: bool) -> str:
    """CAS37 分类判定（纯函数）。

    根据发行方是否存在交付现金/其他金融资产的合同义务：
    - 有合同义务 → 'liability'（金融负债）
    - 无合同义务 → 'equity'（权益工具）

    Requirement 6.1: classifyInstrument(hasContractualObligation)
    """
    return "liability" if has_contractual_obligation else "equity"


def split_amount(total: float, equity_part: float) -> float:
    """计算负债部分金额（纯函数）。

    一项复合金融工具拆分为权益部分与负债部分：
    负债部分 = 总额 - 权益部分

    Requirement 6.2: splitAmount(total, equityPart) = total - equityPart
    """
    return total - equity_part


def validate_classification_consistency(
    equity: float, liability: float, total: float
) -> bool:
    """校验权益+负债金额守恒（纯函数）。

    权益部分 + 负债部分 ≈ 工具总额（容差 TOLERANCE）。
    ADR-3: 权益+负债金额守恒，防止拆分错误。

    Requirement 6.3: calcClassificationConsistency(eq, liab, total)
    """
    return abs(equity + liability - total) < TOLERANCE


# ═══════════════════════════════════════════════════════════════════════════════
# CAS37 分类明细查询
# ═══════════════════════════════════════════════════════════════════════════════


async def get_classification_detail(
    wp_id: str, db: AsyncSession
) -> list[dict[str, Any]]:
    """获取每项金融工具的CAS37分类明细。

    从 checklist_responses 查询 M10-4 逐条判定记录，
    返回每项工具的判定要素 + 分类结论 + 金额。

    Requirement 4.2-4.3: 逐条判定 + 权益/负债守恒
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, conclusion, evidence "
                "FROM checklist_responses "
                "WHERE wp_id = :wid AND item_id LIKE :prefix "
                "ORDER BY item_id"
            ),
            {"wid": wp_id, "prefix": f"{_CLASSIFICATION_ITEM_PREFIX}%"},
        )
    ).fetchall()

    details: list[dict[str, Any]] = []
    for r in rows:
        data: dict[str, Any] = {}
        raw = r.conclusion
        if raw and isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        instrument_name = data.get("instrument_name", "")
        has_obligation = data.get("has_contractual_obligation", False)
        amount = _parse_num(data.get("amount"))
        equity_part = _parse_num(data.get("equity_part"))

        # 用纯函数进行分类判定
        classification = classify_instrument(bool(has_obligation))
        liability_part = split_amount(amount, equity_part) if amount > 0 else 0.0
        is_consistent = validate_classification_consistency(
            equity_part, liability_part, amount
        ) if amount > 0 else True

        details.append({
            "item_id": r.item_id,
            "instrument_name": instrument_name,
            "has_contractual_obligation": has_obligation,
            "classification": classification,
            "amount": amount,
            "equity_part": equity_part,
            "liability_part": liability_part,
            "is_consistent": is_consistent,
            # 判定要素明细
            "mandatory_payment": data.get("mandatory_payment", False),
            "redemption_obligation": data.get("redemption_obligation", False),
            "settlement_method": data.get("settlement_method", ""),
        })

    return details


# ═══════════════════════════════════════════════════════════════════════════════
# CAS37 负债权益区分汇总
# ═══════════════════════════════════════════════════════════════════════════════


async def get_classification_summary(
    wp_id: str, db: AsyncSession
) -> dict[str, Any]:
    """从checklist_responses查询M10-4区分项，聚合权益/负债金额."""
    rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, conclusion "
                "FROM checklist_responses "
                "WHERE wp_id = :wid AND item_id LIKE :prefix "
                "ORDER BY item_id"
            ),
            {"wid": wp_id, "prefix": f"{_CLASSIFICATION_ITEM_PREFIX}%"},
        )
    ).fetchall()

    equity_total = 0.0
    liability_total = 0.0
    items: list[dict[str, Any]] = []

    for r in rows:
        data: dict[str, Any] = {}
        raw = r.conclusion
        if raw and isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        classification = data.get("classification", "").lower()
        amount = _parse_num(data.get("amount"))
        instrument_name = data.get("instrument_name", "")

        if classification == "equity":
            equity_total += amount
        elif classification == "liability":
            liability_total += amount

        items.append({
            "instrument_name": instrument_name,
            "classification": classification,
            "amount": amount,
        })

    total = equity_total + liability_total
    is_consistent = True
    # 如果有明确 total 字段，校验守恒
    if items:
        declared_total = sum(_parse_num(i.get("amount", 0)) for i in items)
        is_consistent = abs(equity_total + liability_total - declared_total) < TOLERANCE

    return {
        "equity_total": equity_total,
        "liability_total": liability_total,
        "total": total,
        "is_consistent": is_consistent,
        "items": items,
    }
