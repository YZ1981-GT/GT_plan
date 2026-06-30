"""D3 预收账款 — 导入导出三级端点

4个端点：
- POST /api/workpapers/{wp_id}/d3/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d3/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d3/import-data?sheet={sheet_code}      解析xlsx写入
- POST /api/workpapers/{wp_id}/d3/import-aux-balance                  从辅助余额表导入

支持sheets: D3-2, D3-5, D3-6, D3-7
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d3-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {"D3-2", "D3-5", "D3-6", "D3-7"}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D3-2": [
        "对方单位名称", "公司代码", "款项性质", "关联方类型",
        "期初未审余额", "期初账项调整", "期初重分类调整",
        "期初审定账龄(1年以下)", "期初审定账龄(1~2年)", "期初审定账龄(2~3年)", "期初审定账龄(3年以上)",
        "借方发生", "贷方发生", "被审计单位重分类调整",
        "期末账项调整", "期末重分类调整",
        "审定账龄(1年以下)", "审定账龄(1~2年)", "审定账龄(2~3年)", "审定账龄(3年以上)",
        "是否发函", "期后结转", "备注",
    ],
    "D3-5": [
        "对方单位名称", "期末余额", "账龄", "经济业务说明",
        "未结转或未偿还的原因", "至审计日结转或偿还金额", "处理计划", "备注",
    ],
    "D3-6": [
        "关联方名称", "关联关系", "期初余额", "借方发生", "贷方发生",
        "期末余额", "发生时间及账龄", "发生原因（款项性质）", "索引号", "备注",
    ],
    "D3-7": [
        "客户名称", "日期", "凭证编号", "业务内容", "对方科目",
        "对方明细科目", "贷方金额", "支持性文件",
        "核对内容1", "核对内容2", "核对内容3", "核对内容4", "核对内容5",
        "索引号", "是否异常", "备注说明",
    ],
}

# item_id 映射
_SHEET_ITEM_ID: dict[str, str] = {
    "D3-2": "D3-det-rows",
    "D3-5": "D3-lt-rows",
    "D3-6": "D3-rp-rows",
    "D3-7": "D3-vc-post-rows",
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


@router.post("/api/workpapers/{wp_id}/d3/export-template")
async def d3_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D3-2"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白模板xlsx（含表头+格式，无数据行）"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    ws.freeze_panes = "A2"
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + min(col_idx, 26))].width = 16

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_模板.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d3/export-data")
async def d3_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D3-2"),
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
        if sheet == "D3-2":
            row_values = _export_d3_2_row(data_row)
        elif sheet == "D3-5":
            row_values = _export_d3_5_row(data_row)
        elif sheet == "D3-6":
            row_values = _export_d3_6_row(data_row)
        else:  # D3-7
            row_values = _export_d3_7_row(data_row)
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


@router.post("/api/workpapers/{wp_id}/d3/import-data")
async def d3_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D3-2"),
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
    actual_headers = [str(cell.value).strip() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]

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

        if sheet == "D3-2":
            row_dict = _parse_d3_2_row(row, actual_headers)
        elif sheet == "D3-5":
            row_dict = _parse_d3_5_row(row, actual_headers)
        elif sheet == "D3-6":
            row_dict = _parse_d3_6_row(row, actual_headers)
        else:
            row_dict = _parse_d3_7_row(row, actual_headers)

        rows_data.append(row_dict)

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

    result_data: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": errors}
    if truncated:
        result_data["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result_data["truncated"] = True

    return result_data


@router.post("/api/workpapers/{wp_id}/d3/import-aux-balance")
async def d3_import_aux_balance(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从 tb_aux_balance（科目2203，按客户维度）批量导入到D3-2"""
    import sqlalchemy as sa

    # 获取 project_id
    wp_result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id"),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, "底稿不存在")

    project_id = str(wp_row.project_id)

    # 从 tb_aux_balance 查询科目2203按客户维度聚合
    aux_result = await db.execute(
        sa.text("""
            SELECT aux_name,
                   COALESCE(SUM(CASE WHEN period_type = 'opening' THEN balance ELSE 0 END), 0) AS prior_balance,
                   COALESCE(SUM(CASE WHEN period_type = 'closing' THEN balance ELSE 0 END), 0) AS current_balance
            FROM tb_aux_balance
            WHERE project_id = :pid
              AND account_code = '2203'
              AND is_deleted = false
            GROUP BY aux_name
            ORDER BY aux_name
        """),
        {"pid": project_id},
    )
    aux_rows = aux_result.fetchall()

    if not aux_rows:
        return {"ok": True, "imported_count": 0, "message": "未找到科目2203的辅助余额数据"}

    # 构建 D3-2 行数据
    rows_data: list[dict] = []
    for aux_row in aux_rows[:_ROW_LIMIT]:
        rows_data.append({
            "rowId": str(uuid4()),
            "customerName": aux_row.aux_name or "",
            "companyCode": "",
            "nature": "其他",
            "relationType": "非关联方",
            "priorUnadjusted": float(aux_row.prior_balance),
            "priorAdjustment": 0,
            "priorReclass": 0,
            "agingPrior": {"within1": float(aux_row.prior_balance), "y1to2": 0, "y2to3": 0, "over3": 0},
            "debit": 0,
            "credit": 0,
            "entityReclass": 0,
            "endAje": 0,
            "endRje": 0,
            "agingAudited": {"within1": float(aux_row.current_balance), "y1to2": 0, "y2to3": 0, "over3": 0},
            "isConfirmed": "",
            "postPeriodSettlement": 0,
            "remark": "",
        })

    # 写入（merge模式：保留已有行、追加新客户）
    item_id = "D3-det-rows"
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

    # Merge: 已有客户名不重复导入
    existing_names = {r.get("customerName", "") for r in existing_rows}
    new_rows = [r for r in rows_data if r["customerName"] not in existing_names]
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
        "message": f"成功导入{len(new_rows)}行数据，{len(new_rows)}个新客户",
        "total_rows": len(merged),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导出辅助函数
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


def _export_d3_2_row(data: dict) -> list:
    aging_prior = data.get("agingPrior", {})
    aging_audited = data.get("agingAudited", {})
    return [
        _safe_str(data.get("customerName")),
        _safe_str(data.get("companyCode")),
        _safe_str(data.get("nature")),
        _safe_str(data.get("relationType")),
        _safe_float(data.get("priorUnadjusted")),
        _safe_float(data.get("priorAdjustment")),
        _safe_float(data.get("priorReclass")),
        _safe_float(aging_prior.get("within1")),
        _safe_float(aging_prior.get("y1to2")),
        _safe_float(aging_prior.get("y2to3")),
        _safe_float(aging_prior.get("over3")),
        _safe_float(data.get("debit")),
        _safe_float(data.get("credit")),
        _safe_float(data.get("entityReclass")),
        _safe_float(data.get("endAje")),
        _safe_float(data.get("endRje")),
        _safe_float(aging_audited.get("within1")),
        _safe_float(aging_audited.get("y1to2")),
        _safe_float(aging_audited.get("y2to3")),
        _safe_float(aging_audited.get("over3")),
        _safe_str(data.get("isConfirmed")),
        _safe_float(data.get("postPeriodSettlement")),
        _safe_str(data.get("remark")),
    ]


def _export_d3_5_row(data: dict) -> list:
    return [
        _safe_str(data.get("customerName")),
        _safe_float(data.get("endBalance")),
        _safe_str(data.get("aging")),
        _safe_str(data.get("businessDescription")),
        _safe_str(data.get("unsettledReason")),
        _safe_float(data.get("settledAmount")),
        _safe_str(data.get("plan")),
        _safe_str(data.get("remark")),
    ]


def _export_d3_6_row(data: dict) -> list:
    return [
        _safe_str(data.get("partyName")),
        _safe_str(data.get("relationship")),
        _safe_float(data.get("priorBalance")),
        _safe_float(data.get("debit")),
        _safe_float(data.get("credit")),
        _safe_float(data.get("endBalance")),
        _safe_str(data.get("agingDescription")),
        _safe_str(data.get("nature")),
        _safe_str(data.get("indexRef")),
        _safe_str(data.get("remark")),
    ]


def _export_d3_7_row(data: dict) -> list:
    check_items = data.get("checkItems", [False] * 5)
    return [
        _safe_str(data.get("customerName")),
        _safe_str(data.get("date")),
        _safe_str(data.get("voucherNo")),
        _safe_str(data.get("businessContent")),
        _safe_str(data.get("counterAccount")),
        _safe_str(data.get("counterDetailAccount")),
        _safe_float(data.get("creditAmount")),
        _safe_str(data.get("supportingDoc")),
        *["Y" if c else "" for c in (check_items + [False] * 5)[:5]],
        _safe_str(data.get("indexRef")),
        _safe_str(data.get("isAbnormal")),
        _safe_str(data.get("remark")),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 导入解析辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _col_val(row: tuple, actual_headers: list[str], col_name: str) -> Any:
    try:
        idx = actual_headers.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _parse_d3_2_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "customerName": _safe_str(_col_val(row, actual_headers, "对方单位名称")),
        "companyCode": _safe_str(_col_val(row, actual_headers, "公司代码")),
        "nature": _safe_str(_col_val(row, actual_headers, "款项性质")) or "其他",
        "relationType": _safe_str(_col_val(row, actual_headers, "关联方类型")) or "非关联方",
        "priorUnadjusted": _safe_float(_col_val(row, actual_headers, "期初未审余额")),
        "priorAdjustment": _safe_float(_col_val(row, actual_headers, "期初账项调整")),
        "priorReclass": _safe_float(_col_val(row, actual_headers, "期初重分类调整")),
        "agingPrior": {
            "within1": _safe_float(_col_val(row, actual_headers, "期初审定账龄(1年以下)")),
            "y1to2": _safe_float(_col_val(row, actual_headers, "期初审定账龄(1~2年)")),
            "y2to3": _safe_float(_col_val(row, actual_headers, "期初审定账龄(2~3年)")),
            "over3": _safe_float(_col_val(row, actual_headers, "期初审定账龄(3年以上)")),
        },
        "debit": _safe_float(_col_val(row, actual_headers, "借方发生")),
        "credit": _safe_float(_col_val(row, actual_headers, "贷方发生")),
        "entityReclass": _safe_float(_col_val(row, actual_headers, "被审计单位重分类调整")),
        "endAje": _safe_float(_col_val(row, actual_headers, "期末账项调整")),
        "endRje": _safe_float(_col_val(row, actual_headers, "期末重分类调整")),
        "agingAudited": {
            "within1": _safe_float(_col_val(row, actual_headers, "审定账龄(1年以下)")),
            "y1to2": _safe_float(_col_val(row, actual_headers, "审定账龄(1~2年)")),
            "y2to3": _safe_float(_col_val(row, actual_headers, "审定账龄(2~3年)")),
            "over3": _safe_float(_col_val(row, actual_headers, "审定账龄(3年以上)")),
        },
        "isConfirmed": _safe_str(_col_val(row, actual_headers, "是否发函")),
        "postPeriodSettlement": _safe_float(_col_val(row, actual_headers, "期后结转")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d3_5_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "customerName": _safe_str(_col_val(row, actual_headers, "对方单位名称")),
        "endBalance": _safe_float(_col_val(row, actual_headers, "期末余额")),
        "aging": _safe_str(_col_val(row, actual_headers, "账龄")),
        "businessDescription": _safe_str(_col_val(row, actual_headers, "经济业务说明")),
        "unsettledReason": _safe_str(_col_val(row, actual_headers, "未结转或未偿还的原因")),
        "settledAmount": _safe_float(_col_val(row, actual_headers, "至审计日结转或偿还金额")),
        "plan": _safe_str(_col_val(row, actual_headers, "处理计划")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d3_6_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "partyName": _safe_str(_col_val(row, actual_headers, "关联方名称")),
        "relationship": _safe_str(_col_val(row, actual_headers, "关联关系")),
        "priorBalance": _safe_float(_col_val(row, actual_headers, "期初余额")),
        "debit": _safe_float(_col_val(row, actual_headers, "借方发生")),
        "credit": _safe_float(_col_val(row, actual_headers, "贷方发生")),
        "endBalance": _safe_float(_col_val(row, actual_headers, "期末余额")),
        "agingDescription": _safe_str(_col_val(row, actual_headers, "发生时间及账龄")),
        "nature": _safe_str(_col_val(row, actual_headers, "发生原因（款项性质）")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d3_7_row(row: tuple, actual_headers: list[str]) -> dict:
    check_items = [
        _safe_str(_col_val(row, actual_headers, f"核对内容{i}")).upper() in ("Y", "是", "TRUE", "1")
        for i in range(1, 6)
    ]
    return {
        "rowId": str(uuid4()),
        "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
        "date": _safe_str(_col_val(row, actual_headers, "日期")),
        "voucherNo": _safe_str(_col_val(row, actual_headers, "凭证编号")),
        "businessContent": _safe_str(_col_val(row, actual_headers, "业务内容")),
        "counterAccount": _safe_str(_col_val(row, actual_headers, "对方科目")),
        "counterDetailAccount": _safe_str(_col_val(row, actual_headers, "对方明细科目")),
        "creditAmount": _safe_float(_col_val(row, actual_headers, "贷方金额")),
        "supportingDoc": _safe_str(_col_val(row, actual_headers, "支持性文件")),
        "checkItems": check_items,
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
        "isAbnormal": _safe_str(_col_val(row, actual_headers, "是否异常")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注说明")),
    }
