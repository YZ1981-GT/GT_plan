"""D4 营业收入 — 导入导出三级端点

3个端点：
- POST /api/workpapers/{wp_id}/d4/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d4/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d4/import-data?sheet={sheet_code}      解析xlsx写入

支持sheets: D4-2, D4-3, D4-12, D4-14~D4-20, D4-21~D4-36
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d4-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置：每种sheet的列头定义
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "D4-2", "D4-3", "D4-12",
    "D4-14", "D4-15", "D4-16", "D4-17", "D4-18", "D4-19", "D4-20",
    "D4-21", "D4-22", "D4-23", "D4-24", "D4-25", "D4-26", "D4-27",
    "D4-28", "D4-29", "D4-30", "D4-31", "D4-32",
    "D4-33", "D4-34", "D4-35", "D4-36",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D4-2": [
        "产品/服务", "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
        "未审合计", "审计调整", "本期审定", "上期未审", "上期调整", "上期审定",
        "未审变动率", "审定变动率", "备注",
    ],
    "D4-3": [
        "项目", "本期未审数", "本期调整", "上期未审数", "上期调整", "备注",
    ],
    "D4-12": [
        "索引号", "合同名称", "客户名称", "合同金额", "合同日期",
        "履约义务", "交易价格", "收入确认时点/时段", "可变对价", "合同变更", "结论", "备注",
    ],
    "D4-14": [
        "客户名称", "日期", "凭证编号", "业务内容", "金额",
        "支持性文件", "核对内容1", "核对内容2", "核对内容3", "是否异常", "备注",
    ],
    "D4-15": [
        "单据编号", "单据日期", "客户", "金额", "对应凭证编号",
        "入账日期", "差异", "是否异常", "备注",
    ],
    "D4-16": [
        "月份", "账面出口收入", "电子口岸金额", "汇率", "折算金额", "差异", "说明",
    ],
    "D4-17": [
        "凭证编号", "凭证日期", "客户名称", "收入金额", "对方科目",
        "发货单日期", "签收日期", "验收日期", "是否跨期", "跨期天数", "调整建议", "备注",
    ],
    "D4-18": [
        "单据编号", "单据日期", "客户名称", "金额", "对应凭证",
        "入账日期", "是否跨期", "跨期天数", "调整建议", "备注",
    ],
    "D4-19": [
        "客户名", "合同金额", "折扣率", "折扣金额", "是否符合政策", "备注",
    ],
    "D4-20": [
        "客户名", "退货日期", "金额", "原因", "是否重新确认收入", "备注",
    ],
    "D4-21": [
        "产品/服务", "关联方客户", "关联方单价", "非关联方客户",
        "非关联方单价", "差异原因", "结论", "备注",
    ],
}

# D4-22~D4-36使用通用列头
_GENERIC_HEADERS = ["序号", "项目", "金额", "说明", "结论", "备注"]


def _get_headers(sheet_code: str) -> list[str]:
    """获取sheet对应的列头，未定义则用通用列头"""
    return _SHEET_HEADERS.get(sheet_code, _GENERIC_HEADERS)


def _validate_sheet(sheet_code: str) -> None:
    """验证sheet_code是否支持"""
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d4/export-template")
async def d4_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    include_guidance: bool = Query(True, description="是否包含编制说明"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白模板xlsx（含表头+格式+编制说明，无数据行）"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)

    # 冻结首行+设置列宽
    ws.freeze_panes = "A2"
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + min(col_idx, 26))].width = 16

    # 添加编制说明 sheet
    if include_guidance:
        guidance = _get_guidance_text(sheet)
        if guidance:
            ws_guide = wb.create_sheet("编制说明")
            ws_guide.append(["编制说明"])
            ws_guide.append([])
            for line in guidance:
                ws_guide.append([line])
            ws_guide.column_dimensions["A"].width = 80

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_模板.xlsx"
    # HTTP headers must be ASCII; use RFC 5987 encoding for Chinese filename
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d4/export-data")
async def d4_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出当前数据xlsx"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    # 加载 checklist_responses 中的行数据
    import sqlalchemy as sa

    item_id = f"{sheet}-rows"
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    rows_data: list[dict] = []
    if row and row.remark:
        try:
            rows_data = json.loads(row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    ws.freeze_panes = "A2"

    # 写入数据行
    for data_row in rows_data:
        if sheet == "D4-2":
            months = data_row.get("months", [0] * 12)
            period_total = sum(_safe_float(m) for m in months)
            audit_adj = _safe_float(data_row.get("auditAdjustment"))
            audited = period_total + audit_adj
            prior_unadj = _safe_float(data_row.get("priorUnadjusted"))
            prior_adj = _safe_float(data_row.get("priorAdjustment"))
            prior_audited = prior_unadj + prior_adj
            # 变动率
            unadj_rate = ((period_total - prior_unadj) / prior_unadj * 100) if prior_unadj != 0 else 0
            audited_rate = ((audited - prior_audited) / prior_audited * 100) if prior_audited != 0 else 0
            row_values = [
                data_row.get("product", ""),
                *[_safe_float(m) for m in months],
                period_total,
                audit_adj,
                audited,
                prior_unadj,
                prior_adj,
                prior_audited,
                round(unadj_rate, 2),
                round(audited_rate, 2),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-3":
            row_values = [
                data_row.get("item", ""),
                data_row.get("currentUnadjusted", 0),
                data_row.get("currentAdjustment", 0),
                data_row.get("priorUnadjusted", 0),
                data_row.get("priorAdjustment", 0),
                data_row.get("remark", ""),
            ]
        else:
            # 通用：按 headers 顺序提取值
            row_values = [data_row.get(h, "") for h in headers]
        ws.append(row_values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_数据.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d4/import-data")
async def d4_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """解析上传xlsx，校验格式，写入 checklist_responses"""
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(400, "文件大小不能超过10MB")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请确认文件格式正确")

    ws = wb.active
    if ws is None:
        raise HTTPException(400, "xlsx文件中无活动工作表")

    # 验证列头
    expected_headers = _get_headers(sheet)
    actual_headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    actual_headers = [str(h).strip() if h else "" for h in actual_headers]

    errors: list[str] = []
    missing_cols = [h for h in expected_headers if h not in actual_headers]
    if missing_cols:
        errors.append(f"缺少列: {', '.join(missing_cols)}")

    if errors:
        return {"ok": False, "errors": errors, "imported_count": 0}

    # 解析数据行
    rows_data: list[dict] = []
    truncated = False
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break

        if sheet == "D4-2":
            row_dict = _parse_d4_2_row(row, actual_headers, expected_headers)
        elif sheet == "D4-3":
            row_dict = _parse_d4_3_row(row, actual_headers, expected_headers)
        else:
            row_dict = _parse_generic_row(row, actual_headers)

        rows_data.append(row_dict)

    wb.close()

    # 写入 checklist_responses
    import sqlalchemy as sa
    from uuid import uuid4

    item_id = f"{sheet}-rows"
    remark_json = json.dumps(rows_data, ensure_ascii=False)

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": remark_json,
        },
    )
    await db.commit()

    result: dict[str, Any] = {
        "ok": True,
        "imported_count": len(rows_data),
        "errors": errors,
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 行解析辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(val: Any) -> float:
    """安全转换为float，失败返回0"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    """安全转换为str"""
    if val is None:
        return ""
    return str(val).strip()


def _parse_d4_2_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    """解析D4-2行：产品+12月+计算列(忽略)+调整+上期+变动率(忽略)+备注"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    months = [_safe_float(_col_val(f"{m}月")) for m in range(1, 13)]

    return {
        "rowId": str(uuid4()),
        "product": _safe_str(_col_val("产品/服务")),
        "months": months,
        "auditAdjustment": _safe_float(_col_val("审计调整")),
        "priorUnadjusted": _safe_float(_col_val("上期未审")),
        "priorAdjustment": _safe_float(_col_val("上期调整")),
        "remark": _safe_str(_col_val("备注")),
        # 自动计算列（未审合计/本期审定/上期审定/变动率）导入时忽略，前端重算
    }


def _parse_d4_3_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    """解析D4-3行"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "rowId": str(uuid4()),
        "item": _safe_str(_col_val("项目")),
        "currentUnadjusted": _safe_float(_col_val("本期未审数")),
        "currentAdjustment": _safe_float(_col_val("本期调整")),
        "priorUnadjusted": _safe_float(_col_val("上期未审数")),
        "priorAdjustment": _safe_float(_col_val("上期调整")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_generic_row(row: tuple, actual_headers: list[str]) -> dict:
    """通用行解析"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))
    result = {"rowId": str(uuid4())}
    for i, header in enumerate(actual_headers):
        if i < len(values):
            val = values[i]
            result[header] = val if val is not None else ""
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明文本（导出模板时附加）
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_GUIDANCE: dict[str, list[str]] = {
    "D4-2": [
        "D4-2 主营业务收入明细表 编制说明",
        "",
        "一、本表目的",
        "按产品/服务类别列示各月主营业务收入（科目6001），反映收入的季节性分布和波动趋势。",
        "",
        "二、填写要求",
        "1. 「产品/服务」列：填写公司产品/服务大类名称，与D4-1审定表对应。",
        "2. 「1月~12月」列：填写各月未审收入金额（含税/不含税按公司口径一致）。",
        "3. 「审计调整」列：如有AJE/RJE涉及该产品，在此填写调整净额。",
        "4. 「上期未审」「上期调整」列：填写上年同期数据供对比分析。",
        "5. 灰底列为自动计算列（未审合计/本期审定/上期审定/变动率），导入时会忽略。",
        "",
        "三、自动计算列说明",
        "未审合计 = SUM(1月~12月)",
        "本期审定 = 未审合计 + 审计调整",
        "上期审定 = 上期未审 + 上期调整",
        "未审变动率 = (未审合计 - 上期未审) / 上期未审 × 100%",
        "审定变动率 = (本期审定 - 上期审定) / 上期审定 × 100%",
        "",
        "四、审计关注",
        "1. 各月收入波动是否合理，有无年末突击确认收入的迹象。",
        "2. 变动率超过30%的产品需在审计说明中解释原因。",
        "3. 本表合计应与D4-1审定表「主营业务收入」行一致。",
        "",
        "五、数据来源",
        "从序时账（tb_ledger）按科目6001+辅助维度（产品/服务）按月汇总导入。",
        "或从ERP系统销售明细导出后按本模板格式整理。",
    ],
    "D4-3": [
        "D4-3 其他业务收入明细表 编制说明",
        "",
        "一、本表目的",
        "列示其他业务收入（科目6051）各项目的本期/上期对比。",
        "",
        "二、填写要求",
        "1. 「项目」列：填写其他业务收入项目名称（如租赁收入、材料销售等）。",
        "2. 「本期未审数」「本期调整」列：填写本期金额及AJE/RJE调整。",
        "3. 「上期未审数」「上期调整」列：填写上年同期对比数据。",
        "",
        "三、审计关注",
        "1. 其他业务收入占比是否异常增大。",
        "2. 与主营业务收入增长趋势是否匹配。",
    ],
    "D4-12": [
        "D4-12 合同检查表 编制说明",
        "",
        "一、本表目的",
        "对收入确认所依据的重大合同进行检查，评价CAS14收入准则的应用。",
        "",
        "二、填写要求",
        "1. 选取重大/异常合同（金额较大、条款特殊、新客户、年末签署等）。",
        "2. 每份合同识别履约义务个数、交易价格分摊、收入确认时点/时段。",
        "3. 关注可变对价（折扣/返利/奖金条款）和合同变更的会计处理。",
        "",
        "三、审计关注",
        "1. 是否存在捆绑销售未拆分履约义务的情形。",
        "2. 可变对价是否使用了适当的估计方法（期望值法/最可能金额法）。",
        "3. 合同变更是否按CAS14进行了正确处理（作为单独合同/终止原合同等）。",
    ],
    "D4-14": [
        "D4-14 营业收入发生检查表 编制说明",
        "",
        "一、本表目的",
        "对收入交易进行细节测试，验证收入的发生认定。",
        "",
        "二、填写要求",
        "1. 从收入明细账抽取样本，检查支持性文件（合同/发货单/签收单/发票）。",
        "2. 核对客户名称、金额、日期是否一致。",
        "3. 标注是否存在异常（如关联方交易、临近期末大额交易等）。",
    ],
    "D4-17": [
        "D4-17 营业收入截止测试（账到单据）编制说明",
        "",
        "一、本表目的",
        "测试期末收入是否存在跨期确认（从账簿→支持单据方向）。",
        "",
        "二、填写要求",
        "1. 选取资产负债表日前后N天的收入凭证。",
        "2. 追溯到发货单/签收单/验收单，确认收入确认时点正确。",
        "3. 标注是否跨期及跨期天数，>5天需进一步关注。",
    ],
    "D4-18": [
        "D4-18 营业收入截止测试（单据到账）编制说明",
        "",
        "一、本表目的",
        "测试期末是否有已发货未入账的收入（从单据→账簿方向）。",
        "",
        "二、填写要求",
        "1. 选取资产负债表日前后N天的发货/出库单据。",
        "2. 追溯到对应收入凭证，确认是否及时入账。",
        "3. 标注未入账项目，评估是否需要做截止调整。",
    ],
}

# 通用编制说明（未单独定义的sheet）
_GENERIC_GUIDANCE = [
    "编制说明",
    "",
    "一、填写要求",
    "1. 按表头列名依次填写各字段数据。",
    "2. 金额列填写数值（正数），无需添加千分位。",
    "3. 日期格式：YYYY-MM-DD。",
    "4. 「备注」列用于记录审计发现或需关注事项。",
    "",
    "二、导入说明",
    "1. 请勿修改表头（第1行列名），否则导入时会校验失败。",
    "2. 空行将被自动跳过。",
    "3. 最多支持500行数据。",
]


def _get_guidance_text(sheet_code: str) -> list[str]:
    """获取sheet对应的编制说明文本"""
    return _SHEET_GUIDANCE.get(sheet_code, _GENERIC_GUIDANCE)
