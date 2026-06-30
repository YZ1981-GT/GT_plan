"""D7 合同负债 — 导入导出端点

4个端点：
- POST /api/workpapers/{wp_id}/d7/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d7/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d7/import-data?sheet={sheet_code}      解析xlsx写入
- POST /api/workpapers/{wp_id}/d7/import-aux-balance                  从tb_aux_balance科目2205导入

支持sheets: D7-2, D7-5, D7-6
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d7-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {"D7-2", "D7-5", "D7-6"}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D7-2": [
        "序号", "合同名称", "单位名称", "公司代码", "关联关系", "类型(款项性质)",
        "期初未审数", "期初AJE", "期初RJE", "期初审定数",
        "期初账龄1年以下", "期初账龄1~2年", "期初账龄2~3年", "期初账龄3年以上",
        "借方发生", "贷方发生", "期末余额", "重分类调整",
        "期末未审余额", "期末AJE", "期末RJE", "期末审定数",
        "期末账龄1年以下", "期末账龄1~2年", "期末账龄2~3年", "期末账龄3年以上",
        "是否发函", "期后结转",
    ],
    "D7-5": [
        "客户名称", "期末余额", "账龄", "经济业务说明",
        "未结转原因", "至审计日结转金额", "处理计划", "备注",
    ],
    "D7-6": [
        "关联方名称", "关联关系", "期初余额", "借方发生", "贷方发生", "期末余额",
        "发生时间及账龄", "未结转原因", "至审计日结转金额", "处理计划", "备注",
    ],
}

_SHEET_ITEM_ID: dict[str, str] = {
    "D7-2": "D7-2-rows",
    "D7-5": "D7-5-rows",
    "D7-6": "D7-6-rows",
}


def _get_headers(sheet_code: str) -> list[str]:
    return _SHEET_HEADERS.get(sheet_code, [])


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d7/export-template")
async def d7_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D7-2"),
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
    ws.freeze_panes = "A2"
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + min(col_idx, 26))].width = 16

    if include_guidance:
        guidance = _get_d7_guidance_text(sheet)
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
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d7/export-data")
async def d7_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D7-2"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出当前数据xlsx"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    import sqlalchemy as sa

    item_id = _SHEET_ITEM_ID[sheet]
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

    for data_row in rows_data:
        row_values = _export_row(sheet, data_row, headers)
        ws.append(row_values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_数据.xlsx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d7/import-data")
async def d7_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D7-2"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """解析上传xlsx，校验格式，写入 checklist_responses"""
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
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
    actual_headers = [
        str(cell.value).strip() if cell.value else ""
        for cell in next(ws.iter_rows(min_row=1, max_row=1))
    ]

    errors: list[str] = []
    missing_cols = [h for h in expected_headers if h not in actual_headers]
    if missing_cols:
        errors.append(f"缺少列: {', '.join(missing_cols)}")

    if errors:
        raise HTTPException(400, detail=errors)

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
        rows_data.append(_parse_row(sheet, row, actual_headers))

    wb.close()

    # 写入 checklist_responses
    import sqlalchemy as sa

    item_id = _SHEET_ITEM_ID[sheet]
    remark_json = json.dumps(rows_data, ensure_ascii=False)

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
    )
    await db.commit()

    result_data: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": []}
    if truncated:
        result_data["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result_data["truncated"] = True

    return result_data


@router.post("/api/workpapers/{wp_id}/d7/import-aux-balance")
async def d7_import_aux_balance(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从 tb_aux_balance（科目2205，按客户维度）批量导入到D7-2"""
    import sqlalchemy as sa

    wp_result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id"),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, "底稿不存在")

    project_id = str(wp_row.project_id)

    aux_result = await db.execute(
        sa.text("""
            SELECT aux_name,
                   COALESCE(SUM(CASE WHEN period_type = 'opening' THEN balance ELSE 0 END), 0) AS prior_balance,
                   COALESCE(SUM(CASE WHEN period_type = 'closing' THEN balance ELSE 0 END), 0) AS current_balance
            FROM tb_aux_balance
            WHERE project_id = :pid
              AND account_code = '2205'
              AND is_deleted = false
            GROUP BY aux_name
            ORDER BY aux_name
        """),
        {"pid": project_id},
    )
    aux_rows = aux_result.fetchall()

    if not aux_rows:
        return {"ok": True, "imported_count": 0, "message": "未找到科目2205的辅助余额数据"}

    # 构建 D7-2 行数据（贷方科目）
    rows_data: list[dict] = []
    for idx, aux_row in enumerate(aux_rows[:_ROW_LIMIT], 1):
        prior_bal = float(aux_row.prior_balance)
        current_bal = float(aux_row.current_balance)
        rows_data.append({
            "rowId": str(uuid4()),
            "seqNo": idx,
            "contractName": aux_row.aux_name or "",
            "companyName": aux_row.aux_name or "",
            "companyCode": "",
            "relatedPartyType": "非关联方",
            "natureType": "预收货款",
            "priorUnadjusted": prior_bal,
            "priorAje": 0, "priorRje": 0,
            "priorAudited": prior_bal,
            "priorAging1": prior_bal, "priorAging2": 0, "priorAging3": 0, "priorAging4": 0,
            "debitAmount": 0, "creditAmount": 0,
            "endBalance": current_bal,
            "entityReclass": 0,
            "endUnadjusted": current_bal,
            "endAje": 0, "endRje": 0,
            "endAudited": current_bal,
            "endAging1": current_bal, "endAging2": 0, "endAging3": 0, "endAging4": 0,
            "isConfirmed": "否",
            "postTransfer": 0,
        })

    # Merge模式：保留已有行，追加新客户
    item_id = "D7-2-rows"
    existing_result = await db.execute(
        sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"),
        {"wp_id": wp_id, "item_id": item_id},
    )
    existing_row = existing_result.fetchone()
    existing_rows: list[dict] = []
    if existing_row and existing_row.remark:
        try:
            existing_rows = json.loads(existing_row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    existing_names = {r.get("companyName", "") for r in existing_rows}
    new_rows = [r for r in rows_data if r["companyName"] not in existing_names]
    merged = existing_rows + new_rows

    remark_json = json.dumps(merged, ensure_ascii=False)
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
    )
    await db.commit()

    return {
        "ok": True,
        "imported_count": len(new_rows),
        "message": f"成功导入{len(new_rows)}行数据",
        "total_rows": len(merged),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


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


def _col_val(row: tuple, actual_headers: list[str], col_name: str) -> Any:
    try:
        idx = actual_headers.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _export_row(sheet: str, data: dict, headers: list[str]) -> list:
    """按sheet类型导出一行数据"""
    if sheet == "D7-2":
        return [
            data.get("seqNo", ""), _safe_str(data.get("contractName")),
            _safe_str(data.get("companyName")), _safe_str(data.get("companyCode")),
            _safe_str(data.get("relatedPartyType")), _safe_str(data.get("natureType")),
            _safe_float(data.get("priorUnadjusted")), _safe_float(data.get("priorAje")),
            _safe_float(data.get("priorRje")), _safe_float(data.get("priorAudited")),
            _safe_float(data.get("priorAging1")), _safe_float(data.get("priorAging2")),
            _safe_float(data.get("priorAging3")), _safe_float(data.get("priorAging4")),
            _safe_float(data.get("debitAmount")), _safe_float(data.get("creditAmount")),
            _safe_float(data.get("endBalance")), _safe_float(data.get("entityReclass")),
            _safe_float(data.get("endUnadjusted")), _safe_float(data.get("endAje")),
            _safe_float(data.get("endRje")), _safe_float(data.get("endAudited")),
            _safe_float(data.get("endAging1")), _safe_float(data.get("endAging2")),
            _safe_float(data.get("endAging3")), _safe_float(data.get("endAging4")),
            _safe_str(data.get("isConfirmed")), _safe_float(data.get("postTransfer")),
        ]
    elif sheet == "D7-5":
        return [
            _safe_str(data.get("customerName")), _safe_float(data.get("endBalance")),
            _safe_str(data.get("aging")), _safe_str(data.get("businessDescription")),
            _safe_str(data.get("reason")), _safe_float(data.get("auditDateTransfer")),
            _safe_str(data.get("plan")), _safe_str(data.get("remark")),
        ]
    else:  # D7-6
        return [
            _safe_str(data.get("partyName")), _safe_str(data.get("relationship")),
            _safe_float(data.get("openingBalance")), _safe_float(data.get("debitAmount")),
            _safe_float(data.get("creditAmount")), _safe_float(data.get("endBalance")),
            _safe_str(data.get("agingTime")), _safe_str(data.get("reason")),
            _safe_float(data.get("auditDateTransfer")), _safe_str(data.get("plan")),
            _safe_str(data.get("remark")),
        ]


def _parse_row(sheet: str, row: tuple, actual_headers: list[str]) -> dict:
    """按sheet类型解析导入行"""
    if sheet == "D7-2":
        prior_unadj = _safe_float(_col_val(row, actual_headers, "期初未审数"))
        prior_aje = _safe_float(_col_val(row, actual_headers, "期初AJE"))
        prior_rje = _safe_float(_col_val(row, actual_headers, "期初RJE"))
        prior_audited = prior_unadj + prior_aje + prior_rje
        credit = _safe_float(_col_val(row, actual_headers, "贷方发生"))
        debit = _safe_float(_col_val(row, actual_headers, "借方发生"))
        # 贷方科目：期末余额=期初审定+贷方-借方
        end_balance = prior_audited + credit - debit
        entity_reclass = _safe_float(_col_val(row, actual_headers, "重分类调整"))
        end_unadjusted = end_balance + entity_reclass
        end_aje = _safe_float(_col_val(row, actual_headers, "期末AJE"))
        end_rje = _safe_float(_col_val(row, actual_headers, "期末RJE"))
        end_audited = end_unadjusted + end_aje + end_rje
        return {
            "rowId": str(uuid4()),
            "seqNo": _safe_float(_col_val(row, actual_headers, "序号")) or 0,
            "contractName": _safe_str(_col_val(row, actual_headers, "合同名称")),
            "companyName": _safe_str(_col_val(row, actual_headers, "单位名称")),
            "companyCode": _safe_str(_col_val(row, actual_headers, "公司代码")),
            "relatedPartyType": _safe_str(_col_val(row, actual_headers, "关联关系")) or "非关联方",
            "natureType": _safe_str(_col_val(row, actual_headers, "类型(款项性质)")) or "预收货款",
            "priorUnadjusted": prior_unadj, "priorAje": prior_aje, "priorRje": prior_rje,
            "priorAudited": prior_audited,
            "priorAging1": _safe_float(_col_val(row, actual_headers, "期初账龄1年以下")),
            "priorAging2": _safe_float(_col_val(row, actual_headers, "期初账龄1~2年")),
            "priorAging3": _safe_float(_col_val(row, actual_headers, "期初账龄2~3年")),
            "priorAging4": _safe_float(_col_val(row, actual_headers, "期初账龄3年以上")),
            "debitAmount": debit, "creditAmount": credit,
            "endBalance": end_balance,
            "entityReclass": entity_reclass,
            "endUnadjusted": end_unadjusted,
            "endAje": end_aje, "endRje": end_rje,
            "endAudited": end_audited,
            "endAging1": _safe_float(_col_val(row, actual_headers, "期末账龄1年以下")),
            "endAging2": _safe_float(_col_val(row, actual_headers, "期末账龄1~2年")),
            "endAging3": _safe_float(_col_val(row, actual_headers, "期末账龄2~3年")),
            "endAging4": _safe_float(_col_val(row, actual_headers, "期末账龄3年以上")),
            "isConfirmed": _safe_str(_col_val(row, actual_headers, "是否发函")) or "否",
            "postTransfer": _safe_float(_col_val(row, actual_headers, "期后结转")),
        }
    elif sheet == "D7-5":
        return {
            "rowId": str(uuid4()),
            "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
            "endBalance": _safe_float(_col_val(row, actual_headers, "期末余额")),
            "aging": _safe_str(_col_val(row, actual_headers, "账龄")),
            "businessDescription": _safe_str(_col_val(row, actual_headers, "经济业务说明")),
            "reason": _safe_str(_col_val(row, actual_headers, "未结转原因")),
            "auditDateTransfer": _safe_float(_col_val(row, actual_headers, "至审计日结转金额")),
            "plan": _safe_str(_col_val(row, actual_headers, "处理计划")),
            "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        }
    else:  # D7-6
        opening = _safe_float(_col_val(row, actual_headers, "期初余额"))
        credit = _safe_float(_col_val(row, actual_headers, "贷方发生"))
        debit = _safe_float(_col_val(row, actual_headers, "借方发生"))
        # 贷方科目：期末=期初+贷方-借方
        end_balance = opening + credit - debit
        return {
            "rowId": str(uuid4()),
            "partyName": _safe_str(_col_val(row, actual_headers, "关联方名称")),
            "relationship": _safe_str(_col_val(row, actual_headers, "关联关系")),
            "openingBalance": opening,
            "debitAmount": debit,
            "creditAmount": credit,
            "endBalance": end_balance,
            "agingTime": _safe_str(_col_val(row, actual_headers, "发生时间及账龄")),
            "reason": _safe_str(_col_val(row, actual_headers, "未结转原因")),
            "auditDateTransfer": _safe_float(_col_val(row, actual_headers, "至审计日结转金额")),
            "plan": _safe_str(_col_val(row, actual_headers, "处理计划")),
            "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明文本
# ═══════════════════════════════════════════════════════════════════════════════

_D7_SHEET_GUIDANCE: dict[str, list[str]] = {
    "D7-2": [
        "D7-2 合同负债明细表 编制说明",
        "",
        "一、本表目的",
        "按合同/客户维度列示合同负债（科目2205）明细，含28列完整数据。",
        "",
        "二、科目特征",
        "科目编码：2205 合同负债（贷方科目/负债类）",
        "核心公式：期末余额 = 期初审定 + 贷方发生 - 借方发生（贷增借减）",
        "",
        "三、填写要求",
        "1. 类型(款项性质)列选择：预收货款/开发项目预收款/预收工程款/其他",
        "2. 关联关系列选择：非关联方/实际控制人/控股股东等8种",
        "3. 灰底自动计算列：期初审定/期末余额/期末未审/期末审定（导入时忽略）",
        "",
        "四、自动计算列说明",
        "期初审定 = 期初未审 + AJE + RJE",
        "期末余额 = 期初审定 + 贷方 - 借方（贷方科目：贷增借减）",
        "期末未审 = 期末余额 + 重分类调整",
        "期末审定 = 期末未审 + AJE + RJE",
    ],
    "D7-5": [
        "D7-5 账龄1年以上合同负债检查表 编制说明",
        "",
        "一、本表目的",
        "对账龄超过1年的合同负债余额进行逐户检查，分析长期未结转原因。",
        "",
        "二、填写要求",
        "1. 从D7-2筛选审定账龄>1年的客户导入",
        "2. 逐户说明未结转原因和处理计划",
        "3. 至审计日结转金额：截止审计外勤结束日实际结转数",
    ],
    "D7-6": [
        "D7-6 关联方合同负债检查表 编制说明",
        "",
        "一、本表目的",
        "列示合同负债中关联方余额及交易情况，核查交易商业合理性。",
        "",
        "二、填写要求",
        "1. 从D7-2筛选关联关系≠非关联方的客户导入",
        "2. 关联关系列选择8种：实际控制人/控股股东等",
        "3. 期末余额=期初+贷方-借方（贷方科目，自动计算）",
    ],
}


def _get_d7_guidance_text(sheet_code: str) -> list[str]:
    """获取D7 sheet对应的编制说明文本"""
    if sheet_code in _D7_SHEET_GUIDANCE:
        return _D7_SHEET_GUIDANCE[sheet_code]
    return [
        "编制说明",
        "", "1. 按表头列名依次填写各字段数据。",
        "2. 金额列填写数值（正数），无需添加千分位。",
        "3. 请勿修改表头（第1行列名），否则导入时会校验失败。",
        "4. 空行将被自动跳过，最多支持500行数据。",
    ]
