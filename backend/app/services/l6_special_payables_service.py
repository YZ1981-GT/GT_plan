"""L6 专项应付款 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ xlsx导入导出逻辑。

提供功能：
- 负债类公式方向验证（贷方科目：期末=期初+贷方-借方）
- 专款专用核查（实际用途vs批准用途）
- 审定数汇总计算
- 负余额检测
- 导出模板 / 导出数据 / 导入数据

科目2601专项应付款（贷方/负债类）：期末=期初+贷方-借方
L筹资循环标准负债底稿，专款专用核查为核心审计程序。

Requirements: 2.4, 4.1
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
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE = 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        n = float(v)
        return n if n == n else 0.0  # noqa: PLR0124 — NaN check
    try:
        n = float(str(v).strip())
        return n if n == n else 0.0  # noqa: PLR0124
    except (TypeError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式验证（纯函数，核心逻辑）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_formulas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验一组行的负债类公式：期末 = 期初 + 贷方 - 借方

    验证每行是否满足负债类（贷方科目）的余额等式。
    容差 0.01 元。

    Args:
        rows: 数据行列表，每行 dict 需含:
            - begin/opening/period_begin: 期初余额
            - credit/period_credit/increase: 贷方发生额
            - debit/period_debit/decrease: 借方发生额
            - end/closing/end_balance: 期末余额
            - row_key/rowKey/item_id: 行标识（可选）

    Returns:
        错误列表 [{row_key, field, message, variance}]

    Requirements: 2.4
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(
            row.get("row_key")
            or row.get("rowKey")
            or row.get("item_id")
            or row.get("project_name")
            or ""
        )
        begin = _parse_num(
            row.get("begin") or row.get("opening") or row.get("period_begin")
        )
        credit = _parse_num(
            row.get("credit") or row.get("period_credit") or row.get("increase")
        )
        debit = _parse_num(
            row.get("debit") or row.get("period_debit") or row.get("decrease")
        )
        end = _parse_num(
            row.get("end") or row.get("closing") or row.get("end_balance")
        )

        # 全零行跳过
        if end == 0.0 and begin == 0.0 and credit == 0.0 and debit == 0.0:
            continue

        # 负债类贷方：期末 = 期初 + 贷方 - 借方
        expected = begin + credit - debit
        variance = expected - end

        if abs(variance) > TOLERANCE:
            errors.append({
                "row_key": row_key,
                "field": "end_balance",
                "message": f"负债类公式不平衡: 期末应为 {expected:.2f}, 实际 {end:.2f}",
                "variance": round(variance, 2),
            })

    return errors


# ═══════════════════════════════════════════════════════════════════════════════
# 专款专用核查（核心审计程序）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_special_purpose_usage(check_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """核查专项应付款的专款专用合规性

    检查每个专项项目的实际用途是否与批准用途一致。
    专项应付款多为政府专项拨款，需确保资金按批准用途使用。

    Args:
        check_rows: 核查行列表，每行 dict 需含:
            - project_name/projectName: 专项项目名称
            - approved_purpose/approvedPurpose: 批准用途
            - actual_purpose/actualPurpose: 实际用途
            - amount（可选）: 涉及金额

    Returns:
        {
            total_checked: 检查总数,
            abnormal_count: 异常数,
            abnormal_projects: [{project_name, approved_purpose, actual_purpose, amount}],
            check_ratio: 异常比率
        }

    Requirements: 4.1
    """
    if not check_rows:
        return {
            "total_checked": 0,
            "abnormal_count": 0,
            "abnormal_projects": [],
            "check_ratio": 0.0,
        }

    abnormal_projects: list[dict[str, Any]] = []

    for row in check_rows:
        project_name = str(
            row.get("project_name") or row.get("projectName") or ""
        ).strip()
        approved_purpose = str(
            row.get("approved_purpose") or row.get("approvedPurpose") or ""
        ).strip()
        actual_purpose = str(
            row.get("actual_purpose") or row.get("actualPurpose") or ""
        ).strip()
        amount = _parse_num(row.get("amount") or row.get("end_balance") or 0)

        # 跳过空行
        if not project_name and not approved_purpose and not actual_purpose:
            continue

        # 专款专用核查：实际用途与批准用途不一致
        if actual_purpose and approved_purpose and actual_purpose != approved_purpose:
            abnormal_projects.append({
                "project_name": project_name,
                "approved_purpose": approved_purpose,
                "actual_purpose": actual_purpose,
                "amount": round(amount, 2),
            })

    total_checked = len([
        r for r in check_rows
        if str(r.get("project_name") or r.get("projectName") or "").strip()
        or str(r.get("approved_purpose") or r.get("approvedPurpose") or "").strip()
        or str(r.get("actual_purpose") or r.get("actualPurpose") or "").strip()
    ])

    abnormal_count = len(abnormal_projects)
    check_ratio = (abnormal_count / total_checked) if total_checked > 0 else 0.0

    return {
        "total_checked": total_checked,
        "abnormal_count": abnormal_count,
        "abnormal_projects": abnormal_projects,
        "check_ratio": round(check_ratio, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 审定数汇总计算
# ═══════════════════════════════════════════════════════════════════════════════


def compute_adjudication_totals(responses: dict[str, Any]) -> dict[str, Any]:
    """从审定表checklist_responses计算汇总审定数

    遍历 L6 审定表responses中的各行，汇总期初审定数和期末审定数。

    Args:
        responses: checklist_responses 数据字典，key为item_id，value含:
            - begin_balance/beginBalance: 期初
            - end_balance/endBalance: 期末
            - audited_amount/auditedAmount: 审定数

    Returns:
        {
            begin_audited_total: 期初审定合计,
            end_audited_total: 期末审定合计,
            variance: 期末-期初差额,
            variance_rate: 变动率
        }

    Requirements: 2.4
    """
    begin_total = 0.0
    end_total = 0.0

    for item_id, data in responses.items():
        if not item_id.startswith("L6-"):
            continue

        # 解析可能是JSON字符串的数据
        parsed = data
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not isinstance(parsed, dict):
            continue

        begin = _parse_num(
            parsed.get("begin_balance")
            or parsed.get("beginBalance")
            or parsed.get("begin")
        )
        end = _parse_num(
            parsed.get("end_balance")
            or parsed.get("endBalance")
            or parsed.get("audited_amount")
            or parsed.get("auditedAmount")
            or parsed.get("end")
        )

        begin_total += begin
        end_total += end

    variance = end_total - begin_total
    variance_rate = (variance / begin_total) if abs(begin_total) > TOLERANCE else 0.0

    return {
        "begin_audited_total": round(begin_total, 2),
        "end_audited_total": round(end_total, 2),
        "variance": round(variance, 2),
        "variance_rate": round(variance_rate, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 负余额检测
# ═══════════════════════════════════════════════════════════════════════════════


def detect_negative_balances(responses: dict[str, Any]) -> list[dict[str, Any]]:
    """检测 L6 responses 中期末余额为负的条目

    专项应付款（负债类）期末余额不应为负。若为负说明余额方向异常。

    Args:
        responses: checklist_responses 数据字典，key为item_id

    Returns:
        警告列表 [{item_id, end_balance, message}]

    Requirements: 2.4
    """
    warnings: list[dict[str, Any]] = []

    for item_id, data in responses.items():
        if not item_id.startswith("L6-"):
            continue

        # 解析数据
        parsed = data
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
        elif isinstance(data, dict):
            # 可能嵌套在 remark/conclusion 字段中
            for field_name in ("remark", "conclusion", "end_balance", "endBalance"):
                raw = data.get(field_name)
                if raw is None:
                    continue
                if isinstance(raw, str) and raw.startswith("{"):
                    try:
                        parsed = json.loads(raw)
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(raw, (int, float)):
                    # 直接是数值字段
                    end_bal = float(raw)
                    if end_bal < -TOLERANCE:
                        warnings.append({
                            "item_id": item_id,
                            "end_balance": round(end_bal, 2),
                            "message": f"专项应付款余额异常：{item_id} 期末为负({end_bal:.2f})",
                        })
                    parsed = None
                    break

        if not isinstance(parsed, dict):
            continue

        end_bal = _parse_num(
            parsed.get("end_balance")
            or parsed.get("endBalance")
            or parsed.get("closing")
            or parsed.get("end")
        )

        if end_bal < -TOLERANCE:
            warnings.append({
                "item_id": item_id,
                "end_balance": round(end_bal, 2),
                "message": f"专项应付款余额异常：{item_id} 期末为负({end_bal:.2f})",
            })

    return warnings


# ═══════════════════════════════════════════════════════════════════════════════
# 单行公式验证（供外部直接调用）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_direction(
    begin: float,
    credit: float,
    debit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验负债类贷方公式方向（单行）

    负债类贷方：期末 = 期初 + 贷方 − 借方

    Requirements: 2.4
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
        result["isValid"] = abs(diff) <= TOLERANCE

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# L6 各sheet导出配置
_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "L6-1": {
        "title": "L6-1 审定表",
        "headers": [
            "专项项目", "期初余额", "贷方发生额", "借方发生额", "期末余额",
            "未审数", "审计调整", "重分类调整", "审定数", "差异", "备注",
        ],
        "fields": [
            "projectName", "beginBalance", "creditAmount", "debitAmount", "endBalance",
            "unadjustedAmount", "ajeAmount", "rjeAmount", "auditedAmount", "difference", "remark",
        ],
    },
    "L6-2": {
        "title": "L6-2 明细表",
        "headers": [
            "专项项目", "拨款来源", "批文号", "批准用途", "期初余额",
            "本期拨入", "本期使用", "本期结转", "期末余额",
            "实际用途", "是否专款专用", "结余处理", "备注",
        ],
        "fields": [
            "projectName", "fundSource", "approvalNo", "approvedPurpose", "beginBalance",
            "periodIncome", "periodUsed", "periodTransfer", "endBalance",
            "actualPurpose", "isSpecialPurpose", "surplusHandling", "remark",
        ],
    },
    "L6-3": {
        "title": "L6-3 调整分录",
        "headers": [
            "调整类型", "科目编码", "科目名称", "摘要",
            "借方金额", "贷方金额", "备注",
        ],
        "fields": [
            "adjustmentType", "accountCode", "accountName", "summary",
            "debitAmount", "creditAmount", "remark",
        ],
    },
    "L6-4": {
        "title": "L6-4 检查表",
        "headers": [
            "专项项目", "批准用途", "实际用途", "是否专款专用",
            "结余处理", "核查结论", "备注",
        ],
        "fields": [
            "projectName", "approvedPurpose", "actualPurpose", "isSpecialPurpose",
            "surplusHandling", "checkConclusion", "remark",
        ],
    },
}

_NUMERIC_FIELDS: set[str] = {
    "beginBalance", "creditAmount", "debitAmount", "endBalance",
    "unadjustedAmount", "ajeAmount", "rjeAmount", "auditedAmount", "difference",
    "periodIncome", "periodUsed", "periodTransfer",
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

    Requirements: 6.5
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

    Requirements: 6.5
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
        item_id = f"L6-{sheet_key}-rows"
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

    Requirements: 6.5
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
        item_id = f"L6-{matched_key}-rows"
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
