"""L5 长期应付款 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ xlsx导入导出逻辑。

提供功能：
- 实际利率法摊销表生成（每期摊销=期初摊余成本×实际利率）
- 摊销表验证（末期余额≈0）
- 净额计算（长期应付款−未确认融资费用）
- 关联方检查汇总
- 负债类/备抵类公式方向验证
- 导出模板 / 导出数据 / 导入数据

科目2701长期应付款（贷方/负债类）：期末=期初+贷方-借方
未确认融资费用（借方/负债备抵类）：期末=期初+借方-贷方
净额 = 长期应付款 − 未确认融资费用

Requirements: 4.2-4.4, 6.1-6.5
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
# 实际利率法摊销引擎（核心纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_amortization(amortized_cost: float, eir: float) -> float:
    """每期摊销 = 期初摊余成本 × 实际利率

    Requirements: 4.2
    """
    return amortized_cost * eir


def calc_end_cost(begin: float, amortization: float, repayment: float) -> float:
    """期末摊余成本 = 期初 − 本期摊销 − 还款

    未确认融资费用随摊销逐期减少。

    Requirements: 4.3
    """
    return begin - amortization - repayment


def generate_amortization_schedule(
    initial_cost: float,
    repayments: list[float],
    eir: float,
    periods: int,
) -> list[dict[str, Any]]:
    """生成完整摊销表（实际利率法）

    最后一期自动尾差调整使期末未确认余额=0。

    Args:
        initial_cost: 期初未确认融资费用（初始摊余成本）
        repayments: 各期还款额列表（若长度不足periods则补0）
        eir: 实际利率
        periods: 期数

    Returns:
        list of AmortRow dicts

    Requirements: 4.2-4.4
    """
    if periods <= 0:
        return []

    # 补齐还款列表
    padded_repayments = list(repayments) + [0.0] * max(0, periods - len(repayments))

    schedule: list[dict[str, Any]] = []
    begin_cost = initial_cost

    for period in range(1, periods + 1):
        repayment = padded_repayments[period - 1]
        amortization = calc_amortization(begin_cost, eir)
        end_cost = calc_end_cost(begin_cost, amortization, repayment)

        # 最后一期尾差调整：强制期末=0
        if period == periods and abs(end_cost) < abs(initial_cost) * 0.01:
            amortization = begin_cost - repayment
            end_cost = 0.0

        schedule.append({
            "period": period,
            "beginCost": round(begin_cost, 2),
            "amortization": round(amortization, 2),
            "repayment": round(repayment, 2),
            "endCost": round(end_cost, 2),
        })

        begin_cost = end_cost

    return schedule


def validate_schedule(schedule: list[dict[str, Any]]) -> dict[str, Any]:
    """验证摊销表：最后一期未确认余额≈0

    Requirements: 4.4
    """
    if not schedule:
        return {"isValid": False, "tailDiff": 0.0, "reason": "空摊销表"}

    last_end = schedule[-1]["endCost"]
    return {
        "isValid": abs(last_end) <= 1.0,
        "tailDiff": round(last_end, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 净额计算
# ═══════════════════════════════════════════════════════════════════════════════


def calc_net_payable(payable: float, unrecognized: float) -> float:
    """净额 = 长期应付款 − 未确认融资费用

    Requirements: 6.1
    """
    return payable - unrecognized


# ═══════════════════════════════════════════════════════════════════════════════
# 关联方检查汇总
# ═══════════════════════════════════════════════════════════════════════════════


async def related_party_check_summary(wp_id: str, db: Any) -> dict[str, Any]:
    """关联方及交易检查汇总统计

    从 checklist_responses 读取 L5-6 关联方检查数据。

    Requirements: 6.5
    """
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": "L5-related-party-rows"},
    )
    row = result.fetchone()

    if not row or not row.remark:
        return {
            "totalParties": 0,
            "totalAmount": 0.0,
            "hasFairnessIssue": False,
            "summary": "暂无关联方数据",
        }

    try:
        parties = json.loads(row.remark)
    except (json.JSONDecodeError, TypeError):
        return {
            "totalParties": 0,
            "totalAmount": 0.0,
            "hasFairnessIssue": False,
            "summary": "数据解析失败",
        }

    total_amount = sum(float(p.get("amount", 0)) for p in parties)
    fairness_issues = [p for p in parties if p.get("fairnessFlag")]

    return {
        "totalParties": len(parties),
        "totalAmount": round(total_amount, 2),
        "hasFairnessIssue": len(fairness_issues) > 0,
        "fairnessIssueCount": len(fairness_issues),
        "summary": f"共 {len(parties)} 笔关联方交易，金额合计 {total_amount:,.2f} 元"
                   + (f"，其中 {len(fairness_issues)} 笔存在公允性问题" if fairness_issues else ""),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类/备抵类公式验证
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_direction(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
    direction: str = "liability",
) -> dict[str, Any]:
    """校验公式方向

    负债类贷方：期末 = 期初 + 贷方 − 借方
    备抵类借方：期末 = 期初 + 借方 − 贷方

    Requirements: 6.2
    """
    if direction == "contra":
        # 备抵类借方
        expected = begin + debit - credit
        formula = "期末=期初+借方-贷方（备抵类借方）"
    else:
        # 负债类贷方
        expected = begin + credit - debit
        formula = "期末=期初+贷方-借方（负债类贷方）"

    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": formula,
        "direction": direction,
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

# L5 各sheet导出配置
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "L5-2": {
        "title": "L5-2 长期应付款明细",
        "headers": [
            "款项名称", "款项类型", "对方单位", "合同编号", "起始日",
            "到期日", "币种", "合同金额", "期初余额", "本期增加",
            "本期减少", "期末余额", "年利率", "付款方式", "担保方式", "备注",
        ],
        "fields": [
            "itemName", "category", "counterparty", "contractNo", "startDate",
            "maturityDate", "currency", "contractAmount", "beginBalance", "periodIncrease",
            "periodDecrease", "endBalance", "interestRate", "paymentMethod", "guarantee", "remark",
        ],
    },
    "L5-3": {
        "title": "L5-3 未确认融资费用明细",
        "headers": [
            "款项名称", "款项类型", "期初余额", "本期增加", "本期摊销",
            "期末余额", "对应应付款", "实际利率", "摊销方法", "备注",
        ],
        "fields": [
            "itemName", "category", "beginBalance", "periodIncrease", "periodAmortization",
            "endBalance", "relatedPayable", "eir", "amortizationMethod", "remark",
        ],
    },
    "L5-5": {
        "title": "L5-5 未确认融资费用测算",
        "headers": [
            "款项名称", "期数", "期初摊余成本", "本期摊销",
            "本期还款", "期末摊余成本", "实际利率", "备注",
        ],
        "fields": [
            "itemName", "period", "beginCost", "amortization",
            "repayment", "endCost", "eir", "remark",
        ],
    },
    "L5-6": {
        "title": "L5-6 关联方及交易检查",
        "headers": [
            "关联方名称", "关系类型", "款项性质", "金额",
            "交易条件", "公允性判断", "定价依据", "备注",
        ],
        "fields": [
            "partyName", "relationType", "transactionNature", "amount",
            "transactionTerms", "fairnessFlag", "pricingBasis", "remark",
        ],
    },
    "L5-7": {
        "title": "L5-7 长期应付款检查表",
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
    "contractAmount", "beginBalance", "periodIncrease", "periodDecrease",
    "endBalance", "interestRate", "beginCost", "amortization", "repayment",
    "endCost", "eir", "amount", "periodAmortization", "period",
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

    Requirements: 8.2
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

    Requirements: 8.2
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
        item_id = f"L5-{sheet_key}-rows"
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

    Requirements: 8.2
    """
    import sqlalchemy as sa

    if len(file_content) > 10 * 1024 * 1024:
        raise ValueError("文件大小超过 10MB 限制")

    try:
        wb = load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    except Exception:
        raise ValueError("无法解析xlsx文件")

    imported_counts: dict[str, int] = {}

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

        imported_counts[matched_key] = len(parsed_rows)

        # 写入 checklist_responses
        item_id = f"L5-{matched_key}-rows"
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
        "imported_counts": imported_counts,
        "total_rows": sum(imported_counts.values()),
    }
