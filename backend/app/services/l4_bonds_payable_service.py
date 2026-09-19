"""L4 应付债券 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ xlsx导入导出逻辑。

提供功能：
- 实际利率法后续计量（2分支：到期一次还本付息 / 分期付息到期一次还本）
- IRR求解（二分法）
- 负债成分现值计算（权益负债划分）
- 权益成分计算（剩余法）
- 初始入账金额计算
- 导出模板 / 导出数据 / 导入数据

科目2502应付债券（贷方/负债类）：期末=期初+贷方-借方
核心：实际利率法EIR引擎 — 每期利息费用=期初摊余成本×实际利率

Requirements: 4.4-4.7, 6.2-6.4, 7.2-7.3, 9.1-9.6, 10.1-10.3
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 实际利率法引擎（核心纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_interest_expense(amortized_cost: float, eir: float) -> float:
    """利息费用 = 期初摊余成本 × 实际利率

    Requirements: 9.1
    """
    return amortized_cost * eir


def calc_end_amortized_cost_bullet(begin: float, interest_expense: float) -> float:
    """到期一次还本付息：期末摊余成本 = 期初 + 利息费用

    利息资本化滚入摊余成本（不实际支付）。

    Requirements: 9.2
    """
    return begin + interest_expense


def calc_end_amortized_cost_installment(
    begin: float, interest_expense: float, coupon_paid: float
) -> float:
    """分期付息到期一次还本：期末摊余成本 = 期初 + 利息费用 - 实付利息

    每期支付票面利息，差额摊销溢折价。

    Requirements: 9.3
    """
    return begin + interest_expense - coupon_paid


def generate_eir_schedule(
    initial_cost: float,
    face_value: float,
    coupon_rate: float,
    eir: float,
    periods: int,
    branch: Literal["bullet", "installment"] = "installment",
) -> list[dict[str, Any]]:
    """生成完整后续计量表（按分支）

    最后一期自动调整尾差使期末摊余成本=面值。

    Args:
        initial_cost: 初始入账金额（期初摊余成本）
        face_value: 面值
        coupon_rate: 票面利率
        eir: 实际利率
        periods: 期数
        branch: "bullet"（到期一次还本付息）或 "installment"（分期付息）

    Returns:
        list of EIRRow dicts

    Requirements: 9.4, 9.5
    """
    if periods <= 0:
        return []

    schedule: list[dict[str, Any]] = []
    begin_cost = initial_cost

    for period in range(1, periods + 1):
        coupon_interest = face_value * coupon_rate
        interest_expense = calc_interest_expense(begin_cost, eir)

        if branch == "bullet":
            end_cost = calc_end_amortized_cost_bullet(begin_cost, interest_expense)
        else:
            end_cost = calc_end_amortized_cost_installment(
                begin_cost, interest_expense, coupon_interest
            )

        # 最后一期调整尾差：强制期末=面值
        if period == periods:
            if branch == "bullet":
                # 到期一次还本付息：最后一期期末应等于面值+所有累计利息？
                # 实际上到期一次还本付息最后一期期末就是面值（到期兑付后）
                # 但摊销表显示的是到期前的摊余成本，最后一期end_cost≈面值+最后一期利息
                # 根据spec：最后一期endCost≈面值（验证用）
                # 重新理解：bullet模式下，摊余成本逐期增加，最终趋向面值
                # 这里的face_value指的是到期应付总额
                pass
            # 通用尾差调整
            amortization = interest_expense - coupon_interest
            tail_diff = end_cost - face_value
            if abs(tail_diff) < 1.0:
                end_cost = face_value
                # 反推调整利息费用
                if branch == "bullet":
                    interest_expense = end_cost - begin_cost
                else:
                    interest_expense = end_cost - begin_cost + coupon_interest
                amortization = interest_expense - coupon_interest

        amortization = interest_expense - coupon_interest

        schedule.append({
            "period": period,
            "beginCost": round(begin_cost, 2),
            "couponInterest": round(coupon_interest, 2),
            "interestExpense": round(interest_expense, 2),
            "amortization": round(amortization, 2),
            "endCost": round(end_cost, 2),
        })

        begin_cost = end_cost

    return schedule


def validate_schedule(schedule: list[dict[str, Any]], face_value: float) -> dict[str, Any]:
    """验证最后一期期末摊余成本≈面值

    Requirements: 9.5
    """
    if not schedule:
        return {"isValid": False, "tailDiff": 0.0, "reason": "空摊销表"}

    last_end = schedule[-1]["endCost"]
    tail_diff = last_end - face_value
    return {
        "isValid": abs(tail_diff) <= 1.0,
        "tailDiff": round(tail_diff, 2),
    }


def solve_eir(cash_flows: list[float], initial_amount: float) -> float:
    """IRR求解（二分法）：使未来现金流现值=初始入账金额

    NPV(r) = Σ CF_t / (1+r)^t - initial_amount = 0

    现金流为正（收到的未来支付），initial_amount为正（初始投入）。
    求解使 NPV = 0 的 r。

    Requirements: 9.4, 6.4
    """
    if not cash_flows or initial_amount <= 0:
        return 0.0

    def npv(rate: float) -> float:
        pv = sum(cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cash_flows))
        return pv - initial_amount

    # 二分法
    low, high = 0.0001, 1.0
    max_iter = 200
    tolerance = 0.0001

    # 确保区间有效
    if npv(low) < 0:
        return low
    if npv(high) > 0:
        return high

    for _ in range(max_iter):
        mid = (low + high) / 2
        val = npv(mid)
        if abs(val) < tolerance:
            return round(mid, 6)
        if val > 0:
            low = mid
        else:
            high = mid

    return round((low + high) / 2, 6)


# ═══════════════════════════════════════════════════════════════════════════════
# 权益负债划分引擎
# ═══════════════════════════════════════════════════════════════════════════════


def calc_liability_component(cash_flows: list[float], market_rate: float) -> float:
    """负债成分 = 未来现金流按市场利率折现的现值

    用于复合金融工具（如可转债）的权益负债划分。

    Requirements: 10.1
    """
    if not cash_flows or market_rate <= 0:
        return 0.0
    pv = sum(cf / (1 + market_rate) ** (t + 1) for t, cf in enumerate(cash_flows))
    return round(pv, 2)


def calc_equity_component(total_proceeds: float, liability_component: float) -> float:
    """权益成分 = 发行总额 - 负债成分（剩余法）

    Requirements: 10.2
    """
    return round(total_proceeds - liability_component, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 初始计量
# ═══════════════════════════════════════════════════════════════════════════════


def calc_initial_amount(issue_price: float, transaction_cost: float) -> float:
    """初始入账金额 = 发行价格 - 交易费用

    Requirements: 6.2
    """
    return issue_price - transaction_cost


def calc_premium_discount(initial_amount: float, face_value: float) -> float:
    """溢折价 = 初始入账金额 - 面值

    正数=溢价发行，负数=折价发行。

    Requirements: 6.3
    """
    return initial_amount - face_value


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式验证
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_direction(
    begin: float, credit: float, debit: float, reported_end: float | None = None
) -> dict[str, Any]:
    """校验负债类贷方：期末=期初+贷方-借方

    Requirements: Req 2.4
    """
    expected = begin + credit - debit
    result: dict[str, Any] = {"expected": round(expected, 2), "formula": "期末=期初+贷方-借方"}

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

# L4-2明细表89列按区段分sheet导出
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "L4-2-基础": {
        "title": "L4-2 应付债券明细-基础信息",
        "headers": [
            "债券名称", "债券代码", "发行日", "到期日", "面值总额",
            "票面利率", "实际利率", "付息方式", "付息频率", "发行价格",
            "交易费用", "初始入账金额", "备注",
        ],
        "fields": [
            "bondName", "bondCode", "issueDate", "maturityDate", "faceValue",
            "couponRate", "eir", "paymentMethod", "paymentFrequency", "issuePrice",
            "transactionCost", "initialAmount", "remark",
        ],
    },
    "L4-2-发行": {
        "title": "L4-2 应付债券明细-发行信息",
        "headers": [
            "债券名称", "发行方式", "发行对象", "信用评级", "担保方式",
            "担保人", "上市交易所", "债券期限(年)", "募集资金用途", "备注",
        ],
        "fields": [
            "bondName", "issueMethod", "issueTarget", "creditRating", "guaranteeType",
            "guarantor", "exchange", "termYears", "fundsUsage", "remark",
        ],
    },
    "L4-2-计息": {
        "title": "L4-2 应付债券明细-计息付息",
        "headers": [
            "债券名称", "本期票面利息", "本期实际利息", "利息调整摊销",
            "已付利息", "应付利息余额", "利息起始日", "利息终止日", "备注",
        ],
        "fields": [
            "bondName", "couponInterest", "actualInterest", "amortization",
            "paidInterest", "interestPayable", "interestStartDate", "interestEndDate", "remark",
        ],
    },
    "L4-2-摊余": {
        "title": "L4-2 应付债券明细-摊余成本",
        "headers": [
            "债券名称", "期初面值", "期初溢折价", "期初摊余成本",
            "本期利息调整", "本期兑付面值", "期末面值", "期末溢折价",
            "期末摊余成本", "备注",
        ],
        "fields": [
            "bondName", "beginFaceValue", "beginPremiumDiscount", "beginAmortizedCost",
            "periodAmortization", "periodRedemption", "endFaceValue", "endPremiumDiscount",
            "endAmortizedCost", "remark",
        ],
    },
    "L4-2-兑付": {
        "title": "L4-2 应付债券明细-兑付信息",
        "headers": [
            "债券名称", "兑付日期", "兑付面值", "兑付溢折价",
            "兑付摊余成本", "实际支付", "兑付损益", "是否提前兑付", "备注",
        ],
        "fields": [
            "bondName", "redemptionDate", "redemptionFaceValue", "redemptionPremDisc",
            "redemptionAmortizedCost", "actualPayment", "redemptionGainLoss", "isEarly", "remark",
        ],
    },
}

# 单sheet导出配置（非明细表）
_SINGLE_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "L4-6": {
        "title": "L4-6 初始计量",
        "headers": [
            "债券名称", "面值", "发行价格", "交易费用",
            "初始入账金额", "溢折价", "实际利率", "备注",
        ],
        "fields": [
            "bondName", "faceValue", "issuePrice", "transactionCost",
            "initialAmount", "premiumDiscount", "eir", "remark",
        ],
    },
    "L4-7": {
        "title": "L4-7 后续计量",
        "headers": [
            "债券名称", "期数", "期初摊余成本", "票面利息",
            "实际利息费用", "利息调整摊销", "期末摊余成本",
        ],
        "fields": [
            "bondName", "period", "beginCost", "couponInterest",
            "interestExpense", "amortization", "endCost",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "faceValue", "couponRate", "eir", "issuePrice", "transactionCost",
    "initialAmount", "beginAmortizedCost", "endAmortizedCost",
    "couponInterest", "actualInterest", "amortization", "paidInterest",
    "interestPayable", "beginFaceValue", "beginPremiumDiscount",
    "periodAmortization", "periodRedemption", "endFaceValue",
    "endPremiumDiscount", "redemptionFaceValue", "redemptionPremDisc",
    "redemptionAmortizedCost", "actualPayment", "redemptionGainLoss",
    "premiumDiscount", "beginCost", "endCost", "interestExpense",
    "termYears", "period",
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
# 导出模板（多sheet，89列按区段分sheet）
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(wp_id: str, db: Any) -> io.BytesIO:
    """生成空白xlsx模板（多sheet，L4-2按区段分5个sheet + L4-6 + L4-7）

    Requirements: 12.2
    """
    wb = Workbook()
    # 删除默认sheet
    wb.remove(wb.active)

    # L4-2 五区段
    for sheet_key, config in _SHEET_CONFIGS.items():
        ws = wb.create_sheet(title=config["title"][:31])  # Excel sheet name max 31 chars
        for col_idx, header in enumerate(config["headers"], 1):
            ws.cell(row=1, column=col_idx, value=header)
        _style_header_row(ws)

    # L4-6, L4-7 单sheet
    for sheet_key, config in _SINGLE_SHEET_CONFIGS.items():
        ws = wb.create_sheet(title=config["title"][:31])
        for col_idx, header in enumerate(config["headers"], 1):
            ws.cell(row=1, column=col_idx, value=header)
        _style_header_row(ws)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


async def export_data(wp_id: str, db: Any) -> io.BytesIO:
    """导出当前数据为xlsx（多sheet）

    从 checklist_responses 读取已保存的数据并填入xlsx。

    Requirements: 12.2
    """
    import sqlalchemy as sa

    wb = Workbook()
    wb.remove(wb.active)

    # 读取L4-2明细行数据
    detail_rows: list[dict] = []
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": "L4-detail-rows"},
    )
    row = result.fetchone()
    if row and row.remark:
        try:
            detail_rows = json.loads(row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    # L4-2 五区段数据填充
    for sheet_key, config in _SHEET_CONFIGS.items():
        ws = wb.create_sheet(title=config["title"][:31])
        for col_idx, header in enumerate(config["headers"], 1):
            ws.cell(row=1, column=col_idx, value=header)
        _style_header_row(ws)

        for data_row in detail_rows:
            row_values = []
            for field in config["fields"]:
                val = data_row.get(field, "")
                row_values.append(val if val is not None else "")
            ws.append(row_values)

    # L4-6 初始计量数据
    initial_rows: list[dict] = []
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": "L4-initial-measure-rows"},
    )
    row = result.fetchone()
    if row and row.remark:
        try:
            initial_rows = json.loads(row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    config = _SINGLE_SHEET_CONFIGS["L4-6"]
    ws = wb.create_sheet(title=config["title"][:31])
    for col_idx, header in enumerate(config["headers"], 1):
        ws.cell(row=1, column=col_idx, value=header)
    _style_header_row(ws)
    for data_row in initial_rows:
        row_values = [data_row.get(f, "") or "" for f in config["fields"]]
        ws.append(row_values)

    # L4-7 后续计量数据
    schedule_rows: list[dict] = []
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": "L4-schedule-rows"},
    )
    row = result.fetchone()
    if row and row.remark:
        try:
            schedule_rows = json.loads(row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    config = _SINGLE_SHEET_CONFIGS["L4-7"]
    ws = wb.create_sheet(title=config["title"][:31])
    for col_idx, header in enumerate(config["headers"], 1):
        ws.cell(row=1, column=col_idx, value=header)
    _style_header_row(ws)
    for data_row in schedule_rows:
        row_values = [data_row.get(f, "") or "" for f in config["fields"]]
        ws.append(row_values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


async def import_data(wp_id: str, file_content: bytes, db: Any) -> dict[str, Any]:
    """解析上传的xlsx并写入checklist_responses

    支持多sheet导入（自动识别区段）。

    Requirements: 12.2
    """
    import sqlalchemy as sa

    if len(file_content) > 10 * 1024 * 1024:
        raise ValueError("文件大小超过 10MB 限制")

    try:
        wb = load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    except Exception:
        raise ValueError("无法解析xlsx文件")

    imported_counts: dict[str, int] = {}
    merged_detail_rows: list[dict] = []

    for ws in wb.worksheets:
        ws_title = ws.title.strip()

        # 尝试匹配到区段配置
        matched_config: dict[str, Any] | None = None
        matched_key: str | None = None

        for sheet_key, config in {**_SHEET_CONFIGS, **_SINGLE_SHEET_CONFIGS}.items():
            if config["title"][:31] == ws_title or sheet_key in ws_title:
                matched_config = config
                matched_key = sheet_key
                break

        if not matched_config:
            continue

        # 读取表头
        actual_headers: list[str] = []
        for cell in next(ws.iter_rows(min_row=1, max_row=1)):
            if cell.value is not None:
                actual_headers.append(str(cell.value).strip())

        # 解析数据行
        parsed_rows: list[dict] = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if row_idx > _ROW_LIMIT + 1:
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

        imported_counts[matched_key or ws_title] = len(parsed_rows)

        # 根据类型写入不同的item_id
        if matched_key and matched_key.startswith("L4-2"):
            merged_detail_rows.extend(parsed_rows)
        elif matched_key == "L4-6":
            json_str = json.dumps(parsed_rows, ensure_ascii=False)
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                    "VALUES (:id, :wp_id, :item_id, :remark) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
                ),
                {"id": str(uuid4()), "wp_id": wp_id, "item_id": "L4-initial-measure-rows", "remark": json_str},
            )
        elif matched_key == "L4-7":
            json_str = json.dumps(parsed_rows, ensure_ascii=False)
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                    "VALUES (:id, :wp_id, :item_id, :remark) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
                ),
                {"id": str(uuid4()), "wp_id": wp_id, "item_id": "L4-schedule-rows", "remark": json_str},
            )

    # 写入L4-2明细（合并五区段）
    if merged_detail_rows:
        # 去重合并：按bondName合并同一行的不同区段字段
        merged_map: dict[str, dict] = {}
        for row_data in merged_detail_rows:
            bond_name = row_data.get("bondName", "")
            if bond_name and bond_name in merged_map:
                merged_map[bond_name].update(
                    {k: v for k, v in row_data.items() if v and k != "rowId"}
                )
            else:
                key = bond_name or row_data.get("rowId", str(uuid4()))
                merged_map[key] = row_data
        final_rows = list(merged_map.values())
        json_str = json.dumps(final_rows, ensure_ascii=False)
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                "VALUES (:id, :wp_id, :item_id, :remark) "
                "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
            ),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": "L4-detail-rows", "remark": json_str},
        )
        imported_counts["L4-2-merged"] = len(final_rows)

    await db.flush()

    return {
        "imported_counts": imported_counts,
        "total_rows": sum(imported_counts.values()),
    }
