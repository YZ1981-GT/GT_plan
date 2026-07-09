"""N2 应交税费 — 业务逻辑服务

纯函数多税种测算引擎 + 增值税测算引擎 + xlsx导入导出 + TB取数/回写 + 跨底稿合计。

提供功能：
- 负债类TB取数（tb_balance 期末余额，direction=贷）
- 增值税测算（销项-进项）
- 多税种测算（城建税/教育费附加/房产税/土地增值税）
- 出口退税核对
- 导出模板 / 导出数据 / 导入数据
- 审定数回写 trial_balance
- 跨底稿合计（N4税金及附加联动）

科目2221应交税费（贷方/负债类）：期末=期初+贷方-借方
N税费循环最复杂底稿（18 sheet/~180+公式）。

Requirements: 4~8, 12.1-12.4
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

_N2_ACCOUNT_CODE = "2221"


# ═══════════════════════════════════════════════════════════════════════════════
# 增值税测算引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_output_vat(sales_amount: float, tax_rate: float) -> float:
    """销项税额 = 销售额 × 适用税率

    Requirements: 4.2
    """
    return sales_amount * tax_rate


def calc_payable_vat(
    output_vat: float, input_vat: float, input_transfer_out: float
) -> float:
    """应交增值税 = 销项税额 - (进项税额 - 进项转出)

    Requirements: 4.2
    """
    return output_vat - (input_vat - input_transfer_out)


def calc_vat_burden_rate(payable_vat: float, sales_amount: float) -> float:
    """增值税税负率 = 应交增值税 / 销售额

    sales_amount=0 时返回 0.0（避免除零）。

    Requirements: 4.6
    """
    if sales_amount == 0:
        return 0.0
    return payable_vat / sales_amount


# ═══════════════════════════════════════════════════════════════════════════════
# 多税种测算引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_surtax(vat: float, consumption_tax: float, rate: float) -> float:
    """城建税及附加 = (增值税 + 消费税) × 税率

    rate:
    - 城建税：市区7%(0.07) / 县城5%(0.05) / 其他1%(0.01)
    - 教育费附加：3%(0.03)
    - 地方教育附加：2%(0.02)

    Requirements: 5.2
    """
    return (vat + consumption_tax) * rate


def calc_property_tax_by_value(original_value: float, deduct_rate: float) -> float:
    """房产税从价 = 房产原值 × (1 - 扣除比例) × 1.2%

    deduct_rate 通常为 10%~30% (0.1~0.3)。

    Requirements: 6.2
    """
    return original_value * (1 - deduct_rate) * 0.012


def calc_property_tax_by_rent(rent_income: float) -> float:
    """房产税从租 = 租金收入 × 12%

    Requirements: 6.2
    """
    return rent_income * 0.12


def calc_land_vat(
    appreciation: float,
    tax_rate: float,
    deduct_items: float,
    quick_deduct_coef: float,
) -> float:
    """土地增值税 = 增值额 × 税率 - 扣除项目 × 速算扣除系数

    四级累进：
    - 增值率≤50%:   税率30%, 速算系数0
    - 50%<增值率≤100%: 税率40%, 速算系数5%
    - 100%<增值率≤200%: 税率50%, 速算系数15%
    - 增值率>200%:  税率60%, 速算系数35%

    Requirements: 7.2, 7.4
    """
    return appreciation * tax_rate - deduct_items * quick_deduct_coef


def calc_appreciation_rate(appreciation: float, deduct_items: float) -> float:
    """土地增值税增值率 = 增值额 / 扣除项目

    deduct_items=0 时返回 0.0（避免除零）。

    Requirements: 7.2
    """
    if deduct_items == 0:
        return 0.0
    return appreciation / deduct_items


def determine_lvt_bracket(appreciation_rate: float) -> dict[str, float]:
    """根据增值率确定土地增值税税率档次

    Returns:
        {"tax_rate": float, "quick_deduct_coef": float, "bracket": str}

    Requirements: 7.3
    """
    if appreciation_rate <= 0.5:
        return {"tax_rate": 0.30, "quick_deduct_coef": 0.0, "bracket": "≤50%"}
    elif appreciation_rate <= 1.0:
        return {"tax_rate": 0.40, "quick_deduct_coef": 0.05, "bracket": "50%~100%"}
    elif appreciation_rate <= 2.0:
        return {"tax_rate": 0.50, "quick_deduct_coef": 0.15, "bracket": "100%~200%"}
    else:
        return {"tax_rate": 0.60, "quick_deduct_coef": 0.35, "bracket": ">200%"}


# ═══════════════════════════════════════════════════════════════════════════════
# 出口退税核对（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_export_refund(export_sales: float, refund_rate: float) -> float:
    """免抵退税额 = 出口销售额 × 退税率

    Requirements: 8.2
    """
    return export_sales * refund_rate


def calc_export_refund_diff(calculated: float, approved: float) -> float:
    """出口退税差异 = 测算免抵退税额 - 批复免抵退税额

    正数表示测算大于批复，需关注。

    Requirements: 8.3
    """
    return calculated - approved


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_liability_end_balance(begin: float, credit: float, debit: float) -> float:
    """负债类期末余额 = 期初 + 贷方 - 借方（2221贷方科目）

    Requirements: 12.1
    """
    return begin + credit - debit


def calc_audited_amount(unadjusted: float, aje: float, rje: float) -> float:
    """审定数 = 未审数 + AJE + RJE

    Requirements: 2.3
    """
    return unadjusted + aje + rje


def validate_liability_direction(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验负债类贷方公式方向

    负债类贷方：期末 = 期初 + 贷方 − 借方

    Requirements: 12.1, 12.4
    """
    expected = calc_liability_end_balance(begin, credit, debit)
    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": "期末=期初+贷方-借方（负债类贷方）",
        "direction": "credit",
        "account_code": _N2_ACCOUNT_CODE,
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


async def get_tb_data(project_id: str, db: Any) -> dict[str, Any]:
    """从 tb_balance 取科目2221应交税费余额数据（负债类/贷方）

    Requirements: 12.2
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    result: dict[str, Any] = {
        "account_code": _N2_ACCOUNT_CODE,
        "account_name": "应交税费",
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
                TbBalance.standard_account_code == _N2_ACCOUNT_CODE,
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
        logger.warning("N2 service: TB 取数失败 project_id=%s: %s", project_id, e)

    return result


async def writeback_tb(project_id: str, audited_amount: float, db: Any) -> dict[str, Any]:
    """回写审定数到 trial_balance（科目2221，期末余额，贷方/负债类）

    Requirements: 12.3
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
                "code": _N2_ACCOUNT_CODE,
            },
        )
        await db.flush()
        return {
            "success": True,
            "account_code": _N2_ACCOUNT_CODE,
            "audited_amount": audited_amount,
            "rows_affected": result.rowcount,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("N2 service: TB 回写失败 project_id=%s: %s", project_id, e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 跨底稿合计（N4联动）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_cross_wp_summary(project_id: str, db: Any) -> dict[str, Any]:
    """获取N2各税种计提合计，供N4税金及附加消费

    从 checklist_responses 中聚合各税种计提数据。

    Requirements: 11.1-11.4
    """
    import sqlalchemy as sa

    tax_accruals: dict[str, float] = {
        "城建税": 0.0,
        "教育费附加": 0.0,
        "地方教育附加": 0.0,
        "房产税": 0.0,
        "土地使用税": 0.0,
        "印花税": 0.0,
        "土地增值税": 0.0,
        "所得税": 0.0,
    }

    try:
        # 查找 N2 审定表中各税种计提额
        # item_id 格式: N2-1-tax-accrual-{taxType}
        rows = (
            await db.execute(
                sa.text(
                    "SELECT cr.item_id, cr.conclusion "
                    "FROM checklist_responses cr "
                    "JOIN working_papers wp ON wp.id = cr.wp_id "
                    "WHERE wp.project_id = :pid "
                    "AND cr.item_id LIKE 'N2-1-tax-accrual-%'"
                ),
                {"pid": str(project_id)},
            )
        ).fetchall()

        for row in rows:
            item_id = row.item_id
            tax_type = item_id.replace("N2-1-tax-accrual-", "")
            amount = _parse_num(row.conclusion)
            if tax_type in tax_accruals:
                tax_accruals[tax_type] = amount

    except Exception as e:  # noqa: BLE001
        logger.warning("N2 service: 跨底稿合计查询失败: %s", e)

    total = sum(tax_accruals.values())
    return {
        "project_id": str(project_id),
        "tax_accruals": tax_accruals,
        "total_accrual": round(total, 2),
        "source": "N2-应交税费",
        "target": "N4-税金及附加",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# N2 各sheet导出配置（多税种分sheet导出）
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "N2-2": {
        "title": "N2-2 明细表",
        "headers": [
            "税种", "明细子目", "税目", "计税依据", "适用税率",
            "纳税期间", "期初余额", "本期计提", "本期缴纳", "期末余额",
            "申报表金额", "差异", "差异原因", "核查结论",
            "完税凭证号", "缴纳日期", "纳税地点", "减免标识",
            "减免金额", "计提凭证号", "缴纳凭证号", "关联科目", "备注",
        ],
        "fields": [
            "taxType", "subItem", "taxItem", "taxBase", "taxRate",
            "taxPeriod", "beginBalance", "periodAccrual", "periodPayment", "endBalance",
            "declarationAmount", "difference", "diffReason", "checkConclusion",
            "taxReceiptNo", "paymentDate", "taxLocation", "exemptionFlag",
            "exemptionAmount", "accrualVoucherNo", "paymentVoucherNo", "relatedAccount", "remark",
        ],
    },
    "N2-6": {
        "title": "N2-6 增值税测算",
        "headers": [
            "期间", "销售额", "销项税额", "进项税额",
            "进项转出", "应交增值税", "已交税额", "未交税额",
        ],
        "fields": [
            "period", "salesAmount", "outputVat", "inputVat",
            "inputTransferOut", "payableVat", "paidVat", "unpaidVat",
        ],
    },
    "N2-8": {
        "title": "N2-8 其他税费测算",
        "headers": [
            "税种", "计税依据", "税率", "应交税额",
            "已交税额", "未交税额", "地区", "政策依据", "备注",
        ],
        "fields": [
            "taxType", "taxBase", "taxRate", "payableAmount",
            "paidAmount", "unpaidAmount", "region", "policyBasis", "remark",
        ],
    },
    "N2-9": {
        "title": "N2-9 房产税测算",
        "headers": [
            "房产名称", "计税方式", "计税依据", "扣除比例",
            "税率", "应交房产税", "备注",
        ],
        "fields": [
            "propertyName", "taxMethod", "taxBase", "deductRate",
            "taxRate", "payableAmount", "remark",
        ],
    },
    "N2-10": {
        "title": "N2-10 土地增值税测算",
        "headers": [
            "项目名称", "转让收入", "扣除项目金额", "增值额",
            "增值率", "适用税率", "速算扣除系数",
        ],
        "fields": [
            "projectName", "transferIncome", "deductItems", "appreciation",
            "appreciationRate", "taxRate", "quickDeductCoef",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "taxBase", "taxRate", "beginBalance", "periodAccrual", "periodPayment",
    "endBalance", "declarationAmount", "difference", "exemptionAmount",
    "salesAmount", "outputVat", "inputVat", "inputTransferOut",
    "payableVat", "paidVat", "unpaidVat",
    "payableAmount", "paidAmount", "unpaidAmount",
    "deductRate", "transferIncome", "deductItems", "appreciation",
    "appreciationRate", "quickDeductCoef",
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


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
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

    Sheet列表: N2-2(明细23列), N2-6(增值税8列), N2-8(其他税费9列),
              N2-9(房产税7列), N2-10(土增税7列)

    Requirements: 12.2
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

    Requirements: 12.2
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
        item_id = f"N2-{sheet_key}-rows"
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
    验证表头结构匹配。

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
        item_id = f"N2-{matched_key}-rows"
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
