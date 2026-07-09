"""N3 递延所得税负债 — 业务逻辑服务

负债类取数（tb_balance期末余额，direction=贷）+ 递延税负债测算 + 跨底稿合计。

提供功能：
- 负债类TB取数（tb_balance 期末余额，direction=贷）
- 递延所得税负债测算（应纳税暂时性差异×适用税率）
- 负债类期末余额校验（期末=期初+贷方-借方）
- 加权平均税率计算
- 审定数回写 trial_balance
- 跨底稿合计（N1资产部分 + N3负债部分，供N5核对）

科目2901递延所得税负债（贷方/负债类）：期末=期初+贷方-借方
核心公式: 递延所得税负债 = 应纳税暂时性差异 × 适用税率

Requirements: 4.1-4.4, 6.6
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

_N3_ACCOUNT_CODE = "2901"


# ═══════════════════════════════════════════════════════════════════════════════
# 递延所得税测算引擎（纯函数，与N1同源逻辑）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_taxable_temporary_difference(book_value: float, tax_base: float) -> float:
    """应纳税暂时性差异 = 账面价值 - 计税基础

    资产项：账面 > 计税基础 → 应纳税暂时性差异（产生递延所得税负债）
    负债项：账面 < 计税基础 → 应纳税暂时性差异（产生递延所得税负债）

    Requirements: 4.1
    """
    return book_value - tax_base


def calc_deferred_tax_liability(taxable_diff: float, tax_rate: float) -> float:
    """递延所得税负债 = 应纳税暂时性差异 × 适用税率

    结果四舍五入到2位小数。

    Requirements: 4.2
    """
    return round(taxable_diff * tax_rate, 2)


def calc_weighted_avg_rate(tax_amounts: list[float], diffs: list[float]) -> float:
    """加权平均税率 = Σ递延税负债 / Σ应纳税暂时性差异

    当差异合计为0时返回0.0（避免除零）。

    Requirements: 4.3
    """
    total_diff = sum(diffs)
    if total_diff == 0:
        return 0.0
    total_tax = sum(tax_amounts)
    return total_tax / total_diff


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_liability_end_balance(begin: float, credit: float, debit: float) -> float:
    """负债类期末余额 = 期初 + 贷方 - 借方（2901贷方科目）

    Requirements: 6.6
    """
    return begin + credit - debit


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


def validate_liability_direction(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验负债类贷方公式方向

    负债类贷方：期末 = 期初 + 贷方 − 借方

    Requirements: 6.6
    """
    expected = calc_liability_end_balance(begin, credit, debit)
    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": "期末=期初+贷方-借方（负债类贷方）",
        "direction": "credit",
        "account_code": _N3_ACCOUNT_CODE,
    }

    if reported_end is not None:
        diff = reported_end - expected
        result["reported"] = reported_end
        result["difference"] = round(diff, 2)
        result["isValid"] = abs(diff) <= 0.01

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 不确认递延税负债的特殊项判定
# ═══════════════════════════════════════════════════════════════════════════════


_SPECIAL_NON_RECOGNITION_ITEMS = {
    "goodwill_initial": "商誉初始确认（合并中产生的应纳税暂时性差异不确认递延税负债）",
    "equity_long_term_hold": "长期股权投资拟长期持有（投资方能够控制转回且预计可预见未来不会转回）",
}


def check_non_recognition(item_type: str) -> dict[str, Any]:
    """判断是否属于不确认递延所得税负债的特殊项

    Requirements: 4.4
    """
    if item_type in _SPECIAL_NON_RECOGNITION_ITEMS:
        return {
            "is_special": True,
            "item_type": item_type,
            "reason": _SPECIAL_NON_RECOGNITION_ITEMS[item_type],
            "recognize_dtl": False,
        }
    return {
        "is_special": False,
        "item_type": item_type,
        "reason": "",
        "recognize_dtl": True,
    }


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


async def get_tb_data(project_id: str, db: Any) -> dict[str, Any]:
    """从 tb_balance 取科目2901递延所得税负债余额数据（负债类/贷方）

    Requirements: 6.6
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    result: dict[str, Any] = {
        "account_code": _N3_ACCOUNT_CODE,
        "account_name": "递延所得税负债",
        "direction": "credit",
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
                TbBalance.standard_account_code == _N3_ACCOUNT_CODE,
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
        logger.warning("N3 service: TB 取数失败 project_id=%s: %s", project_id, e)

    return result


async def writeback_tb(project_id: str, audited_amount: float, db: Any) -> dict[str, Any]:
    """回写审定数到 trial_balance（科目2901，期末余额，贷方/负债类）

    Requirements: 6.6
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
                "code": _N3_ACCOUNT_CODE,
            },
        )
        await db.flush()
        return {
            "success": True,
            "account_code": _N3_ACCOUNT_CODE,
            "audited_amount": audited_amount,
            "rows_affected": result.rowcount,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("N3 service: TB 回写失败 project_id=%s: %s", project_id, e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 跨底稿合计（N1资产部分 + N3负债部分，供N5递延所得税费用核对）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_cross_wp_total(project_id: str, db: Any) -> dict[str, Any]:
    """跨底稿合计：N1资产部分 + N3负债部分

    从 checklist_responses 中聚合 N3 审定数据，并从 tb_balance 获取 N1 资产数据，
    供 N5 递延所得税费用核对行（N5-8）消费。

    递延所得税费用 = 本期递延税负债增加（N3本期变动） - 本期递延税资产增加（N1本期变动）

    Requirements: 6.6
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    n3_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }
    n1_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }

    try:
        active_filter = get_active_filter(project_id)

        # N3 递延所得税负债（科目2901）
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

        # N1 递延所得税资产（科目1811）
        _N1_ACCOUNT_CODE = "1811"
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

    except Exception as e:  # noqa: BLE001
        logger.warning("N3 service: 跨底稿合计查询失败: %s", e)

    # 递延所得税费用 = 本期递延税负债增加 - 本期递延税资产增加
    deferred_tax_expense = n3_data["period_change"] - n1_data["period_change"]

    return {
        "project_id": str(project_id),
        "n3_liability": n3_data,
        "n1_asset": n1_data,
        "deferred_tax_expense": round(deferred_tax_expense, 2),
        "source": "N3-递延所得税负债 + N1-递延所得税资产",
        "target": "N5-8-递延所得税费用核对",
        "direction": "credit",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# N3 各sheet导出配置（明细表N3-2为主要动态行导入导出目标）
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "N3-2": {
        "title": "N3-2 明细表",
        "headers": [
            "序号", "应纳税暂时性差异项目", "账面价值", "计税基础",
            "应纳税暂时性差异", "适用税率", "期初递延税负债",
            "本期确认", "本期转回", "期末递延税负债",
            "是否特殊项", "特殊项类型", "不确认原因", "备注",
        ],
        "fields": [
            "seq", "itemName", "bookValue", "taxBase",
            "taxableDiff", "taxRate", "beginDtl",
            "periodRecognized", "periodReversed", "endDtl",
            "isSpecial", "specialType", "nonRecognitionReason", "remark",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "bookValue", "taxBase", "taxableDiff", "taxRate",
    "beginDtl", "periodRecognized", "periodReversed", "endDtl",
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
    """生成空白xlsx模板（N3-2明细表）

    Sheet列表: N3-2(明细14列)

    Requirements: 3.4
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
    """导出当前数据为xlsx（N3-2明细表）

    从 checklist_responses 读取已保存的数据并填入xlsx。

    Requirements: 3.4
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
        item_id = f"N3-{sheet_key}-rows"
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

    支持N3-2明细表导入。验证表头结构匹配。

    Requirements: 3.4
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
                    row_data[field] = _parse_num(raw_val)
                else:
                    row_data[field] = _safe_str(raw_val)

            parsed_rows.append(row_data)

        imported_counts[matched_key] = len(parsed_rows)

        # 写入 checklist_responses
        item_id = f"N3-{matched_key}-rows"
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
