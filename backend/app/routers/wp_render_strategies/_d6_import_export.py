"""D6 合同资产 — 导入导出端点

4个端点：
- POST /api/workpapers/{wp_id}/d6/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d6/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d6/import-data?sheet={sheet_code}      解析xlsx写入
- POST /api/workpapers/{wp_id}/d6/import-aux-balance                  从tb_aux_balance科目1402导入

支持sheets: D6-2, D6-3, D6-5, D6-8
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

router = APIRouter(tags=["d6-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {"D6-2", "D6-3", "D6-5", "D6-8"}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D6-2": [
        "序号", "合同名称", "类型", "客户名称", "公司代码", "关联关系",
        "期初未审数", "期初AJE", "期初RJE", "期初审定余额",
        "期初账龄1年以下", "期初账龄1~2年", "期初账龄2~3年", "期初账龄3年以上",
        "借方发生", "贷方发生", "期末未审余额",
        "期末AJE", "期末RJE", "期末审定余额",
        "期末账龄1年以下", "期末账龄1~2年", "期末账龄2~3年", "期末账龄3年以上",
        "1年以内收款权", "1年以上收款权",
        "是否在建设期或质保期内", "信用风险组合方式", "是否函证", "期后结转金额",
    ],
    "D6-3": [
        "项目", "分类", "期初未审余额", "期初AJE", "期初RJE", "期初审定余额",
        "本期计提", "本期其他增加", "本期转回", "本期核销", "本期其他减少",
        "期末未审余额", "期末AJE", "期末RJE", "期末审定余额",
    ],
    "D6-5": [
        "关联方名称", "关联关系", "期初余额", "借方发生", "贷方发生", "期末余额",
        "坏账准备", "账面价值", "发生时间及账龄", "未结转原因",
        "至审计日结转金额", "处理计划", "索引号", "备注",
    ],
    "D6-8": [
        "债务人名称", "审定余额", "损失率", "应计提", "账面余额", "差异", "依据", "索引号",
    ],
}

_SHEET_ITEM_ID: dict[str, str] = {
    "D6-2": "D6-2-rows",
    "D6-3": "D6-3-rows",
    "D6-5": "D6-5-rows",
    "D6-8": "D6-8-single-rows",
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


@router.post("/api/workpapers/{wp_id}/d6/export-template")
async def d6_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D6-2"),
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
        guidance = _get_d6_guidance_text(sheet)
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


@router.post("/api/workpapers/{wp_id}/d6/export-data")
async def d6_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D6-2"),
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


@router.post("/api/workpapers/{wp_id}/d6/import-data")
async def d6_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D6-2"),
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


@router.post("/api/workpapers/{wp_id}/d6/import-aux-balance")
async def d6_import_aux_balance(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从 tb_aux_balance（科目1402，按客户/合同维度）批量导入到D6-2"""
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
              AND account_code = '1402'
              AND is_deleted = false
            GROUP BY aux_name
            ORDER BY aux_name
        """),
        {"pid": project_id},
    )
    aux_rows = aux_result.fetchall()

    if not aux_rows:
        return {"ok": True, "imported_count": 0, "message": "未找到科目1402的辅助余额数据"}

    # 构建 D6-2 行数据
    rows_data: list[dict] = []
    for idx, aux_row in enumerate(aux_rows[:_ROW_LIMIT], 1):
        prior_bal = float(aux_row.prior_balance)
        current_bal = float(aux_row.current_balance)
        rows_data.append({
            "rowId": str(uuid4()),
            "seqNo": idx,
            "contractName": aux_row.aux_name or "",
            "contractType": "工程施工",
            "customerName": aux_row.aux_name or "",
            "companyCode": "",
            "relatedPartyType": "非关联方",
            "priorUnadjusted": prior_bal,
            "priorAje": 0, "priorRje": 0,
            "priorAudited": prior_bal,
            "agePrior1y": prior_bal, "agePrior1to2y": 0, "agePrior2to3y": 0, "agePrior3yAbove": 0,
            "debitAmount": 0, "creditAmount": 0,
            "endUnadjusted": current_bal,
            "endAje": 0, "endRje": 0,
            "endAudited": current_bal,
            "ageEnd1y": current_bal, "ageEnd1to2y": 0, "ageEnd2to3y": 0, "ageEnd3yAbove": 0,
            "receivableWithin1y": current_bal, "receivableAbove1y": 0,
            "isInConstructionPeriod": "否",
            "creditRiskGroup": "业务类型组合",
            "isConfirmed": "否",
            "postPeriodSettlement": 0,
        })

    # Merge模式：保留已有行，追加新客户
    item_id = "D6-2-rows"
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

    existing_names = {r.get("contractName", "") for r in existing_rows}
    new_rows = [r for r in rows_data if r["contractName"] not in existing_names]
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
    if sheet == "D6-2":
        return [
            data.get("seqNo", ""), _safe_str(data.get("contractName")),
            _safe_str(data.get("contractType")), _safe_str(data.get("customerName")),
            _safe_str(data.get("companyCode")), _safe_str(data.get("relatedPartyType")),
            _safe_float(data.get("priorUnadjusted")), _safe_float(data.get("priorAje")),
            _safe_float(data.get("priorRje")), _safe_float(data.get("priorAudited")),
            _safe_float(data.get("agePrior1y")), _safe_float(data.get("agePrior1to2y")),
            _safe_float(data.get("agePrior2to3y")), _safe_float(data.get("agePrior3yAbove")),
            _safe_float(data.get("debitAmount")), _safe_float(data.get("creditAmount")),
            _safe_float(data.get("endUnadjusted")),
            _safe_float(data.get("endAje")), _safe_float(data.get("endRje")),
            _safe_float(data.get("endAudited")),
            _safe_float(data.get("ageEnd1y")), _safe_float(data.get("ageEnd1to2y")),
            _safe_float(data.get("ageEnd2to3y")), _safe_float(data.get("ageEnd3yAbove")),
            _safe_float(data.get("receivableWithin1y")), _safe_float(data.get("receivableAbove1y")),
            _safe_str(data.get("isInConstructionPeriod")),
            _safe_str(data.get("creditRiskGroup")),
            _safe_str(data.get("isConfirmed")),
            _safe_float(data.get("postPeriodSettlement")),
        ]
    elif sheet == "D6-3":
        return [
            _safe_str(data.get("itemName")), _safe_str(data.get("category")),
            _safe_float(data.get("priorUnadjusted")), _safe_float(data.get("priorAje")),
            _safe_float(data.get("priorRje")), _safe_float(data.get("priorAudited")),
            _safe_float(data.get("provision")), _safe_float(data.get("otherIncrease")),
            _safe_float(data.get("reversal")), _safe_float(data.get("writeOff")),
            _safe_float(data.get("otherDecrease")),
            _safe_float(data.get("endUnadjusted")), _safe_float(data.get("endAje")),
            _safe_float(data.get("endRje")), _safe_float(data.get("endAudited")),
        ]
    elif sheet == "D6-5":
        return [
            _safe_str(data.get("partyName")), _safe_str(data.get("relationship")),
            _safe_float(data.get("priorBalance")), _safe_float(data.get("debitAmount")),
            _safe_float(data.get("creditAmount")), _safe_float(data.get("endBalance")),
            _safe_float(data.get("impairment")), _safe_float(data.get("bookValue")),
            _safe_str(data.get("agingAndTiming")), _safe_str(data.get("unsettledReason")),
            _safe_float(data.get("postSettlement")), _safe_str(data.get("plan")),
            _safe_str(data.get("indexRef")), _safe_str(data.get("remark")),
        ]
    else:  # D6-8
        return [
            _safe_str(data.get("debtorName")), _safe_float(data.get("auditedBalance")),
            _safe_float(data.get("lossRate")), _safe_float(data.get("expectedProvision")),
            _safe_float(data.get("bookBalance")), _safe_float(data.get("difference")),
            _safe_str(data.get("basis")), _safe_str(data.get("indexRef")),
        ]


def _parse_row(sheet: str, row: tuple, actual_headers: list[str]) -> dict:
    """按sheet类型解析导入行"""
    if sheet == "D6-2":
        prior_unadj = _safe_float(_col_val(row, actual_headers, "期初未审数"))
        prior_aje = _safe_float(_col_val(row, actual_headers, "期初AJE"))
        prior_rje = _safe_float(_col_val(row, actual_headers, "期初RJE"))
        prior_audited = prior_unadj + prior_aje + prior_rje
        debit = _safe_float(_col_val(row, actual_headers, "借方发生"))
        credit = _safe_float(_col_val(row, actual_headers, "贷方发生"))
        end_unadj = prior_audited + debit - credit
        end_aje = _safe_float(_col_val(row, actual_headers, "期末AJE"))
        end_rje = _safe_float(_col_val(row, actual_headers, "期末RJE"))
        end_audited = end_unadj + end_aje + end_rje
        return {
            "rowId": str(uuid4()),
            "seqNo": _safe_float(_col_val(row, actual_headers, "序号")) or 0,
            "contractName": _safe_str(_col_val(row, actual_headers, "合同名称")),
            "contractType": _safe_str(_col_val(row, actual_headers, "类型")) or "工程施工",
            "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
            "companyCode": _safe_str(_col_val(row, actual_headers, "公司代码")),
            "relatedPartyType": _safe_str(_col_val(row, actual_headers, "关联关系")) or "非关联方",
            "priorUnadjusted": prior_unadj, "priorAje": prior_aje, "priorRje": prior_rje,
            "priorAudited": prior_audited,
            "agePrior1y": _safe_float(_col_val(row, actual_headers, "期初账龄1年以下")),
            "agePrior1to2y": _safe_float(_col_val(row, actual_headers, "期初账龄1~2年")),
            "agePrior2to3y": _safe_float(_col_val(row, actual_headers, "期初账龄2~3年")),
            "agePrior3yAbove": _safe_float(_col_val(row, actual_headers, "期初账龄3年以上")),
            "debitAmount": debit, "creditAmount": credit,
            "endUnadjusted": end_unadj, "endAje": end_aje, "endRje": end_rje,
            "endAudited": end_audited,
            "ageEnd1y": _safe_float(_col_val(row, actual_headers, "期末账龄1年以下")),
            "ageEnd1to2y": _safe_float(_col_val(row, actual_headers, "期末账龄1~2年")),
            "ageEnd2to3y": _safe_float(_col_val(row, actual_headers, "期末账龄2~3年")),
            "ageEnd3yAbove": _safe_float(_col_val(row, actual_headers, "期末账龄3年以上")),
            "receivableWithin1y": _safe_float(_col_val(row, actual_headers, "1年以内收款权")),
            "receivableAbove1y": _safe_float(_col_val(row, actual_headers, "1年以上收款权")),
            "isInConstructionPeriod": _safe_str(_col_val(row, actual_headers, "是否在建设期或质保期内")) or "否",
            "creditRiskGroup": _safe_str(_col_val(row, actual_headers, "信用风险组合方式")) or "业务类型组合",
            "isConfirmed": _safe_str(_col_val(row, actual_headers, "是否函证")) or "否",
            "postPeriodSettlement": _safe_float(_col_val(row, actual_headers, "期后结转金额")),
        }
    elif sheet == "D6-3":
        prior_unadj = _safe_float(_col_val(row, actual_headers, "期初未审余额"))
        prior_aje = _safe_float(_col_val(row, actual_headers, "期初AJE"))
        prior_rje = _safe_float(_col_val(row, actual_headers, "期初RJE"))
        prior_audited = prior_unadj + prior_aje + prior_rje
        provision = _safe_float(_col_val(row, actual_headers, "本期计提"))
        other_inc = _safe_float(_col_val(row, actual_headers, "本期其他增加"))
        reversal = _safe_float(_col_val(row, actual_headers, "本期转回"))
        writeoff = _safe_float(_col_val(row, actual_headers, "本期核销"))
        other_dec = _safe_float(_col_val(row, actual_headers, "本期其他减少"))
        end_unadj = prior_audited + provision + other_inc - reversal - writeoff - other_dec
        end_aje = _safe_float(_col_val(row, actual_headers, "期末AJE"))
        end_rje = _safe_float(_col_val(row, actual_headers, "期末RJE"))
        return {
            "rowId": str(uuid4()),
            "itemName": _safe_str(_col_val(row, actual_headers, "项目")),
            "category": _safe_str(_col_val(row, actual_headers, "分类")) or "single",
            "priorUnadjusted": prior_unadj, "priorAje": prior_aje, "priorRje": prior_rje,
            "priorAudited": prior_audited,
            "provision": provision, "otherIncrease": other_inc,
            "reversal": reversal, "writeOff": writeoff, "otherDecrease": other_dec,
            "endUnadjusted": end_unadj, "endAje": end_aje, "endRje": end_rje,
            "endAudited": end_unadj + end_aje + end_rje,
        }
    elif sheet == "D6-5":
        prior_bal = _safe_float(_col_val(row, actual_headers, "期初余额"))
        debit = _safe_float(_col_val(row, actual_headers, "借方发生"))
        credit = _safe_float(_col_val(row, actual_headers, "贷方发生"))
        end_bal = prior_bal + debit - credit
        impairment = _safe_float(_col_val(row, actual_headers, "坏账准备"))
        return {
            "rowId": str(uuid4()),
            "partyName": _safe_str(_col_val(row, actual_headers, "关联方名称")),
            "relationship": _safe_str(_col_val(row, actual_headers, "关联关系")),
            "priorBalance": prior_bal, "debitAmount": debit, "creditAmount": credit,
            "endBalance": end_bal,
            "impairment": impairment,
            "bookValue": end_bal - impairment,
            "agingAndTiming": _safe_str(_col_val(row, actual_headers, "发生时间及账龄")),
            "unsettledReason": _safe_str(_col_val(row, actual_headers, "未结转原因")),
            "postSettlement": _safe_float(_col_val(row, actual_headers, "至审计日结转金额")),
            "plan": _safe_str(_col_val(row, actual_headers, "处理计划")),
            "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
            "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        }
    else:  # D6-8
        balance = _safe_float(_col_val(row, actual_headers, "审定余额"))
        rate = _safe_float(_col_val(row, actual_headers, "损失率"))
        expected = balance * rate
        book = _safe_float(_col_val(row, actual_headers, "账面余额"))
        return {
            "rowId": str(uuid4()),
            "debtorName": _safe_str(_col_val(row, actual_headers, "债务人名称")),
            "auditedBalance": balance,
            "lossRate": rate,
            "expectedProvision": expected,
            "bookBalance": book,
            "difference": expected - book,
            "basis": _safe_str(_col_val(row, actual_headers, "依据")),
            "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明文本
# ═══════════════════════════════════════════════════════════════════════════════

_D6_SHEET_GUIDANCE: dict[str, list[str]] = {
    "D6-2": [
        "D6-2 合同资产明细表 编制说明",
        "",
        "一、本表目的",
        "按合同/客户维度列示合同资产（科目1402）明细，含30列完整数据。",
        "",
        "二、科目特征",
        "科目编码：1402 合同资产（借方科目/资产类）",
        "核心公式：期末未审 = 期初审定 + 借方发生 - 贷方发生",
        "",
        "三、填写要求",
        "1. 类型列选择：工程施工/质量保证金/其他",
        "2. 关联关系列选择：非关联方/实际控制人/控股股东等8种",
        "3. 灰底自动计算列：期初审定/期末未审/期末审定（导入时忽略）",
        "",
        "四、自动计算列说明",
        "期初审定(10) = 期初未审(7) + AJE(8) + RJE(9)",
        "期末未审(17) = 期初审定(10) + 借方(15) - 贷方(16)",
        "期末审定(20) = 期末未审(17) + AJE(18) + RJE(19)",
    ],
    "D6-3": [
        "D6-3 合同资产减值准备明细表 编制说明",
        "",
        "一、本表目的",
        "列示合同资产坏账准备的本期变动（计提/其他增加/转回/核销/其他减少）。",
        "",
        "二、填写要求",
        "1. 分类列选择：single（按单项评估）或 group（按信用风险组合）",
        "2. 灰底自动计算列导入时忽略",
        "",
        "三、自动计算列说明",
        "期初审定 = 期初未审 + AJE + RJE",
        "期末未审 = 期初审定 + 计提 + 其他增加 - 转回 - 核销 - 其他减少",
        "期末审定 = 期末未审 + AJE + RJE",
    ],
    "D6-5": [
        "D6-5 关联关系及交易检查 编制说明",
        "",
        "一、本表目的",
        "检查合同资产中关联方余额及交易情况。",
        "",
        "二、填写要求",
        "1. 关联关系列选择8种：实际控制人/控股股东/控股股东附属企业等",
        "2. 期末余额=期初+借方-贷方（借方科目，自动计算）",
        "3. 账面价值=期末余额-坏账准备（自动计算）",
    ],
    "D6-8": [
        "D6-8 合同资产减值准备测算 编制说明",
        "",
        "一、本表目的",
        "按单项评估计提的ECL减值测算（债务人级别）。",
        "",
        "二、填写要求",
        "1. 审定余额：从D6-2取各客户期末审定余额",
        "2. 损失率：预期信用损失率（0~1之间小数）",
        "3. 自动计算：应计提=余额×损失率；差异=应计提-账面余额",
    ],
}


def _get_d6_guidance_text(sheet_code: str) -> list[str]:
    """获取D6 sheet对应的编制说明文本"""
    if sheet_code in _D6_SHEET_GUIDANCE:
        return _D6_SHEET_GUIDANCE[sheet_code]
    return [
        "编制说明",
        "", "1. 按表头列名依次填写各字段数据。",
        "2. 金额列填写数值（正数），无需添加千分位。",
        "3. 请勿修改表头（第1行列名），否则导入时会校验失败。",
        "4. 空行将被自动跳过，最多支持500行数据。",
    ]
