"""N1 递延所得税资产 — 业务逻辑服务

资产类取数（tb_balance期末余额，direction=借）+ 递延税资产测算 + 可弥补亏损确认 + 跨底稿合计。

提供功能：
- 资产类TB取数（tb_balance 期末余额，direction=借）
- 递延所得税资产测算（可抵扣暂时性差异×适用税率）
- 可弥补亏损确认（min(未弥补亏损, 预计未来应纳税所得额)×税率）
- 资产类期末余额校验（期末=期初+借方-贷方）
- 加权平均税率计算
- 审定数回写 trial_balance
- 跨底稿合计（N1资产部分 + N3负债部分，供N5核对）

科目1811递延所得税资产（借方/资产类）：期末=期初+借方-贷方
核心公式: 递延所得税资产 = 可抵扣暂时性差异 × 适用税率
可弥补亏损: 可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 税率

Requirements: 4.1-4.6, 5.1-5.6, 8.1-8.4
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

_N1_ACCOUNT_CODE = "1811"


# ═══════════════════════════════════════════════════════════════════════════════
# 递延所得税资产测算引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_temporary_difference(book_value: float, tax_base: float) -> float:
    """暂时性差异 = 账面价值 - 计税基础

    资产项：账面 < 计税基础 → 可抵扣暂时性差异（产生递延所得税资产）
    资产项：账面 > 计税基础 → 应纳税暂时性差异（产生递延所得税负债→N3）

    Requirements: 4.2
    """
    return book_value - tax_base


def calc_deferred_tax(temp_diff: float, tax_rate: float) -> float:
    """递延所得税 = 暂时性差异 × 适用税率

    结果四舍五入到2位小数。
    对于N1（可抵扣差异为负值），结果取绝对值表示递延税资产。

    Requirements: 4.3
    """
    return round(temp_diff * tax_rate, 2)


def calc_deferred_tax_asset(deductible_diff: float, tax_rate: float) -> float:
    """递延所得税资产 = 可抵扣暂时性差异 × 适用税率

    deductible_diff 应为正值（可抵扣暂时性差异绝对值）。
    结果四舍五入到2位小数。

    Requirements: 4.3
    """
    return round(deductible_diff * tax_rate, 2)


def calc_weighted_avg_rate(tax_amounts: list[float], diffs: list[float]) -> float:
    """加权平均税率 = Σ递延税资产 / Σ可抵扣暂时性差异

    当差异合计为0时返回0.0（避免除零）。

    Requirements: 4.3
    """
    total_diff = sum(diffs)
    if total_diff == 0:
        return 0.0
    total_tax = sum(tax_amounts)
    return total_tax / total_diff


def classify_temporary_differences(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """将暂时性差异分类为可抵扣（→N1资产）和应纳税（→N3负债）

    分类规则：
    - 资产项账面 < 计税基础 → 可抵扣暂时性差异 → 递延所得税资产(N1)
    - 资产项账面 > 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)

    Requirements: 4.4
    """
    deductible: list[dict[str, Any]] = []  # 可抵扣 → N1
    taxable: list[dict[str, Any]] = []  # 应纳税 → N3

    for row in rows:
        book_value = _parse_num(row.get("bookValue", 0))
        tax_base = _parse_num(row.get("taxBase", 0))
        diff = book_value - tax_base

        classified = {**row, "temporaryDifference": diff}
        if diff < 0:
            # 账面 < 计税基础 → 可抵扣
            classified["deductibleDiff"] = abs(diff)
            deductible.append(classified)
        elif diff > 0:
            # 账面 > 计税基础 → 应纳税
            classified["taxableDiff"] = diff
            taxable.append(classified)
        # diff == 0 → 无暂时性差异，不归入任何一方

    return {"deductible": deductible, "taxable": taxable}


# ═══════════════════════════════════════════════════════════════════════════════
# 可弥补亏损确认引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_unrecovered_loss(loss_amount: float, recovered: float) -> float:
    """未弥补亏损 = 亏损金额 - 已弥补金额

    结果不能为负（已弥补不能超过亏损金额）。

    Requirements: 5.2
    """
    return max(0.0, loss_amount - recovered)


def calc_recognizable_asset(
    unrecovered: float, future_taxable_income: float, tax_rate: float
) -> float:
    """可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 税率

    遵循谨慎性原则：以预计未来应纳税所得额为限确认。

    Requirements: 5.2, 5.4
    """
    recognizable_base = min(unrecovered, future_taxable_income)
    return round(recognizable_base * tax_rate, 2)


def is_compensation_expired(
    loss_year: int, current_year: int, max_years: int = 5
) -> bool:
    """判断弥补期限是否届满

    一般企业弥补期限5年，高新技术企业/科技型中小企业10年。

    Requirements: 5.3
    """
    return (current_year - loss_year) > max_years


def calc_loss_recognition(
    losses: list[dict[str, Any]],
    future_taxable_income: float,
    tax_rate: float,
) -> dict[str, Any]:
    """可弥补亏损批量确认计算

    逐年计算未弥补亏损，汇总可确认递延税资产总额。
    已过期亏损不确认。

    losses 结构: [{"lossYear": int, "lossAmount": float, "recovered": float,
                   "maxYears": int(可选,默认5)}]

    Requirements: 5.1-5.6
    """
    import datetime

    current_year = datetime.date.today().year
    details: list[dict[str, Any]] = []
    total_unrecovered = 0.0
    total_recognizable = 0.0
    remaining_income = future_taxable_income

    for loss in losses:
        loss_year = int(loss.get("lossYear", 0))
        loss_amount = _parse_num(loss.get("lossAmount", 0))
        recovered = _parse_num(loss.get("recovered", 0))
        max_years = int(loss.get("maxYears", 5))

        unrecovered = calc_unrecovered_loss(loss_amount, recovered)
        expired = is_compensation_expired(loss_year, current_year, max_years)

        if expired or unrecovered <= 0:
            details.append({
                "lossYear": loss_year,
                "lossAmount": loss_amount,
                "recovered": recovered,
                "unrecovered": unrecovered,
                "expired": expired,
                "recognizable": 0.0,
                "recognizableAsset": 0.0,
            })
            continue

        # 按剩余可用所得额限额确认
        recognizable_base = min(unrecovered, remaining_income)
        recognizable_asset = round(recognizable_base * tax_rate, 2)

        total_unrecovered += unrecovered
        total_recognizable += recognizable_asset
        remaining_income = max(0.0, remaining_income - recognizable_base)

        details.append({
            "lossYear": loss_year,
            "lossAmount": loss_amount,
            "recovered": recovered,
            "unrecovered": unrecovered,
            "expired": False,
            "recognizable": recognizable_base,
            "recognizableAsset": recognizable_asset,
        })

    return {
        "details": details,
        "totalUnrecovered": round(total_unrecovered, 2),
        "totalRecognizable": round(total_recognizable, 2),
        "futureTaxableIncome": future_taxable_income,
        "taxRate": tax_rate,
        "insufficientWarning": total_unrecovered > future_taxable_income,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 资产类公式（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_asset_end_balance(begin: float, debit: float, credit: float) -> float:
    """资产类期末余额 = 期初 + 借方 - 贷方（1811借方科目）

    Requirements: 8.1
    """
    return begin + debit - credit


def calc_audited_amount(unadjusted: float, aje: float, rje: float) -> float:
    """审定数 = 未审数 + AJE + RJE

    Requirements: 4.1
    """
    return unadjusted + aje + rje


def calc_subtotal(arr: list[float]) -> float:
    """合计 = Σarr

    Requirements: 4.1
    """
    return sum(arr)


def calc_proportion(item: float, total: float) -> float:
    """占比 = item / total

    total=0 时返回 0.0（避免除零）。

    Requirements: 4.3
    """
    if total == 0:
        return 0.0
    return item / total


def validate_asset_direction(
    begin: float,
    debit: float,
    credit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验资产类借方公式方向

    资产类借方：期末 = 期初 + 借方 − 贷方

    Requirements: 8.1, 8.4
    """
    expected = calc_asset_end_balance(begin, debit, credit)
    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": "期末=期初+借方-贷方（资产类借方）",
        "direction": "debit",
        "account_code": _N1_ACCOUNT_CODE,
    }

    if reported_end is not None:
        diff = reported_end - expected
        result["reported"] = reported_end
        result["difference"] = round(diff, 2)
        result["isValid"] = abs(diff) <= 0.01

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# TB 取数 + 回写
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


async def get_tb_balance_for_n1(project_id: str, db: Any) -> dict[str, Any]:
    """从 tb_balance 取科目1811递延所得税资产余额数据（资产类/借方）

    资产类取数规则：从tb_balance取期末余额（direction=借）。
    期末余额 = 期初 + 本期借方 - 本期贷方。

    Requirements: 8.2, 8.3
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    result: dict[str, Any] = {
        "account_code": _N1_ACCOUNT_CODE,
        "account_name": "递延所得税资产",
        "direction": "debit",
        "begin_balance": 0.0,
        "debit_amount": 0.0,
        "credit_amount": 0.0,
        "end_balance": 0.0,
        "found": False,
    }

    try:
        active_filter = get_active_filter(project_id)
        stmt = (
            sa.select(
                TbBalance.begin_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.end_balance,
            )
            .where(
                TbBalance.project_id == str(project_id),
                TbBalance.standard_account_code == _N1_ACCOUNT_CODE,
                active_filter,
            )
            .limit(1)
        )
        row = (await db.execute(stmt)).fetchone()
        if row:
            result["begin_balance"] = _parse_num(row.begin_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.end_balance)
            result["found"] = True
    except Exception as e:  # noqa: BLE001
        logger.warning("N1 service: TB 取数失败 project_id=%s: %s", project_id, e)

    return result


async def writeback_tb(
    project_id: str, audited_amount: float, db: Any
) -> dict[str, Any]:
    """回写审定数到 trial_balance（科目1811，期末余额，借方/资产类）

    Requirements: 8.3
    """
    import sqlalchemy as sa

    try:
        result = await db.execute(
            sa.text(
                "UPDATE trial_balance "
                "SET audited_amount = :amount "
                "WHERE project_id = :pid AND standard_account_code = :code"
            ),
            {
                "amount": audited_amount,
                "pid": str(project_id),
                "code": _N1_ACCOUNT_CODE,
            },
        )
        await db.flush()
        return {
            "success": True,
            "account_code": _N1_ACCOUNT_CODE,
            "audited_amount": audited_amount,
            "rows_affected": result.rowcount,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("N1 service: TB 回写失败 project_id=%s: %s", project_id, e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 跨底稿合计（N1+N3联动，供N5递延所得税费用核对）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_cross_workpaper_totals(project_id: str, db: Any) -> dict[str, Any]:
    """跨底稿合计：N1资产部分 + N3负债部分

    从 tb_balance 获取 N1 资产数据和 N3 负债数据，
    供 N5 递延所得税费用核对行（N5-8）消费。

    递延所得税费用 = 本期递延税负债增加（N3本期变动）
                    - 本期递延税资产增加（N1本期变动）

    Requirements: 4.4, 4.6
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    _N3_ACCOUNT_CODE = "2901"

    n1_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }
    n3_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }

    try:
        active_filter = get_active_filter(project_id)

        # N1 递延所得税资产（科目1811，资产类借方）
        n1_row = (
            await db.execute(
                sa.select(
                    TbBalance.begin_balance,
                    TbBalance.end_balance,
                )
                .where(
                    TbBalance.project_id == str(project_id),
                    TbBalance.standard_account_code == _N1_ACCOUNT_CODE,
                    active_filter,
                )
                .limit(1)
            )
        ).fetchone()

        if n1_row:
            n1_begin = _parse_num(n1_row.begin_balance)
            n1_end = _parse_num(n1_row.end_balance)
            n1_data["begin_balance"] = n1_begin
            n1_data["end_balance"] = n1_end
            n1_data["period_change"] = n1_end - n1_begin

        # N3 递延所得税负债（科目2901，负债类贷方）
        n3_row = (
            await db.execute(
                sa.select(
                    TbBalance.begin_balance,
                    TbBalance.end_balance,
                )
                .where(
                    TbBalance.project_id == str(project_id),
                    TbBalance.standard_account_code == _N3_ACCOUNT_CODE,
                    active_filter,
                )
                .limit(1)
            )
        ).fetchone()

        if n3_row:
            n3_begin = _parse_num(n3_row.begin_balance)
            n3_end = _parse_num(n3_row.end_balance)
            n3_data["begin_balance"] = n3_begin
            n3_data["end_balance"] = n3_end
            n3_data["period_change"] = n3_end - n3_begin

    except Exception as e:  # noqa: BLE001
        logger.warning("N1 service: 跨底稿合计查询失败: %s", e)

    # 递延所得税费用 = 本期递延税负债增加 - 本期递延税资产增加
    deferred_tax_expense = n3_data["period_change"] - n1_data["period_change"]

    return {
        "project_id": str(project_id),
        "n1_asset": n1_data,
        "n3_liability": n3_data,
        "deferred_tax_expense": round(deferred_tax_expense, 2),
        "source": "N1-递延所得税资产 + N3-递延所得税负债",
        "target": "N5-8-递延所得税费用核对",
        "direction": "debit",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# N1 各sheet导出配置（明细表N1-2为主要动态行导入导出目标）
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "N1-2": {
        "title": "N1-2 明细表",
        "headers": [
            "序号", "可抵扣暂时性差异项目", "账面价值", "计税基础",
            "可抵扣暂时性差异", "适用税率", "期初递延税资产",
            "本期确认", "本期转回", "期末递延税资产",
            "确认条件", "备注",
        ],
        "fields": [
            "seq", "itemName", "bookValue", "taxBase",
            "deductibleDiff", "taxRate", "beginDta",
            "periodRecognized", "periodReversed", "endDta",
            "recognitionCondition", "remark",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "bookValue", "taxBase", "deductibleDiff", "taxRate",
    "beginDta", "periodRecognized", "periodReversed", "endDta",
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


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(wp_id: str, db: Any, sheet: str | None = None) -> io.BytesIO:
    """生成空白xlsx模板（N1-2明细表）

    Sheet列表: N1-2(明细12列)

    Requirements: 4.1
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
    """导出当前数据为xlsx（N1-2明细表）

    从 checklist_responses 读取已保存的数据并填入xlsx。

    Requirements: 4.1
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
        item_id = f"N1-{sheet_key}-rows"
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

    支持N1-2明细表导入。验证表头结构匹配。

    Requirements: 4.1
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
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=2, values_only=True), start=2
        ):
            if row_idx > _ROW_LIMIT + 1:
                warnings.append(
                    f"Sheet '{ws_title}' 超过 {_ROW_LIMIT} 行限制，已截断"
                )
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
                    row_data[field] = _parse_num(raw_val)
                else:
                    row_data[field] = _safe_str(raw_val)

            parsed_rows.append(row_data)

        imported_counts[matched_key] = len(parsed_rows)

        # 写入 checklist_responses
        item_id = f"N1-{matched_key}-rows"
        json_str = json.dumps(parsed_rows, ensure_ascii=False)
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                "VALUES (:id, :wp_id, :item_id, :remark) "
                "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
            ),
            {
                "id": str(uuid4()),
                "wp_id": wp_id,
                "item_id": item_id,
                "remark": json_str,
            },
        )

    await db.flush()

    return {
        "imported_count": sum(imported_counts.values()),
        "imported_counts": imported_counts,
        "warnings": warnings,
    }
