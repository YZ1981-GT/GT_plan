"""D7 合同负债 — 导入导出端点

4个端点：
- POST /api/workpapers/{wp_id}/d7/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d7/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d7/import-data?sheet={sheet_code}      解析xlsx写入
- POST /api/workpapers/{wp_id}/d7/import-aux-balance                  从tb_aux_balance科目2205导入

支持sheets: D7-2, D7-5, D7-6, D7-7-period, D7-7-post
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

_SUPPORTED_SHEETS: set[str] = {"D7-1", "D7-2", "D7-3", "D7-4", "D7-5", "D7-6", "D7-7-period", "D7-7-post"}

_D7_1_ROWS: list[tuple[str, str, str]] = [
    ("nature", "revenue", "预收货款"),
    ("nature", "development", "开发项目预收款"),
    ("nature", "engineering", "预收工程款"),
    ("nature", "other", "其他"),
    ("nature", "non-current-deduction", "减：计入其他非流动负债的合同负债"),
    ("aging", "within-1-year", "1年以内(含1年)"),
    ("aging", "1-to-2-years", "1至2年(含2年)"),
    ("aging", "2-to-3-years", "2至3年(含3年)"),
    ("aging", "over-3-years", "3年以上"),
    ("aging", "trial-balance", "试算平衡表数"),
]
_D7_1_FIELDS: list[tuple[str, str, bool]] = [
    ("priorUnadjusted", "期初未审", False),
    ("priorAje", "期初AJE", False),
    ("priorRje", "期初RJE", False),
    ("currentUnadjusted", "期末未审", False),
    ("currentAje", "期末AJE", False),
    ("currentRje", "期末RJE", False),
    ("reasonAnalysis", "原因分析", True),
]

_SHEET_HEADERS: dict[str, list[str]] = {
    "D7-1": [
        "区块", "行键", "项目",
        "期初未审", "期初AJE", "期初RJE",
        "期末未审", "期末AJE", "期末RJE",
        "原因分析",
    ],
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
    "D7-3": [
        "调整事项说明", "类别", "报表项目", "科目名称", "附注项目", "占位/对应项",
        "借方调整金额", "贷方调整金额", "索引", "备注",
    ],
    "D7-4": [
        "记录类型", "项目", "金额", "数据来源", "备注",
    ],
    "D7-6": [
        "关联方名称", "关联关系", "期初余额", "借方发生", "贷方发生", "期末余额",
        "发生时间及账龄", "未结转原因", "至审计日结转金额", "处理计划", "备注",
    ],
    "D7-7-period": [
        "客户名称", "日期", "凭证号", "业务内容", "对方科目", "对方明细",
        "借方金额", "贷方金额", "支持性文件",
        "核对内容1", "核对内容2", "核对内容3", "核对内容4", "核对内容5",
        "索引号", "是否异常", "备注说明",
    ],
    "D7-7-post": [
        "客户名称", "日期", "凭证号", "业务内容", "对方科目", "对方明细",
        "贷方金额", "支持性文件",
        "核对内容1", "核对内容2", "核对内容3", "核对内容4", "核对内容5",
        "索引号", "是否异常", "备注说明",
    ],
}

_SHEET_ITEM_ID: dict[str, str] = {
    "D7-2": "D7-2-rows",
    "D7-3": "D7-3-rows",
    "D7-4": "D7-4-debit-rows",
    "D7-5": "D7-5-rows",
    "D7-6": "D7-6-rows",
    "D7-7-period": "D7-7-period-rows",
    "D7-7-post": "D7-7-post-rows",
}


def _get_headers(sheet_code: str) -> list[str]:
    return _SHEET_HEADERS.get(sheet_code, [])


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


async def _fetch_d7_response_map(wp_id: str, db: AsyncSession, prefix: str) -> dict[str, str]:
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
        ),
        {"wp_id": wp_id, "prefix": f"{prefix}%"},
    )
    return {row.item_id: (row.remark or "") for row in result.fetchall()}


async def _upsert_d7_cell(db: AsyncSession, wp_id: str, item_id: str, remark: str) -> None:
    import sqlalchemy as sa

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark},
    )


async def _export_d7_1_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    responses = await _fetch_d7_response_map(wp_id, db, "D7-1-adj-")
    wb = Workbook()
    ws = wb.active
    ws.title = "D7-1"
    ws.append(_SHEET_HEADERS["D7-1"])
    ws.freeze_panes = "A2"
    for block, row_key, label in _D7_1_ROWS:
        values = [block, row_key, label]
        for field_key, _header, is_text in _D7_1_FIELDS:
            if row_key == "trial-balance":
                if field_key == "priorUnadjusted":
                    raw = responses.get("D7-1-adj-aging-trial-balance-priorAudited", "")
                    values.append(_safe_float(raw) if raw else 0.0)
                elif field_key == "currentUnadjusted":
                    raw = responses.get("D7-1-adj-aging-trial-balance-currentAudited", "")
                    values.append(_safe_float(raw) if raw else 0.0)
                else:
                    values.append("" if is_text else 0.0)
                continue
            item_id = f"D7-1-adj-{block}-{row_key}-{field_key}"
            raw = responses.get(item_id, "")
            values.append(raw if is_text else (_safe_float(raw) if raw else 0.0))
        ws.append(values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    encoded_filename = quote("D7-1_数据.xlsx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


async def _import_d7_1_data(wp_id: str, ws: Any, actual_headers: list[str], db: AsyncSession) -> dict[str, Any]:
    rows_data: list[dict[str, Any]] = []
    row_count = 0
    truncated = False
    valid = {(b, rk) for b, rk, _ in _D7_1_ROWS}

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break
        block = _safe_str(_col_val(row, actual_headers, "区块"))
        row_key = _safe_str(_col_val(row, actual_headers, "行键"))
        if (block, row_key) not in valid:
            continue
        parsed: dict[str, Any] = {"block": block, "rowKey": row_key}
        for field_key, header, is_text in _D7_1_FIELDS:
            val = _col_val(row, actual_headers, header)
            parsed[field_key] = _safe_str(val) if is_text else _safe_float(val)
        rows_data.append(parsed)

    field_count = 0
    for row_data in rows_data:
        block = row_data.get("block", "")
        row_key = row_data.get("rowKey", "")
        if row_key == "trial-balance":
            prior = _safe_float(row_data.get("priorUnadjusted"))
            current = _safe_float(row_data.get("currentUnadjusted"))
            await _upsert_d7_cell(db, wp_id, "D7-1-adj-aging-trial-balance-priorAudited", str(prior))
            await _upsert_d7_cell(db, wp_id, "D7-1-adj-aging-trial-balance-currentAudited", str(current))
            field_count += 2
            continue
        for field_key, _header, is_text in _D7_1_FIELDS:
            val = row_data.get(field_key)
            if val is None:
                continue
            item_id = f"D7-1-adj-{block}-{row_key}-{field_key}"
            remark = str(val) if is_text else str(_safe_float(val))
            await _upsert_d7_cell(db, wp_id, item_id, remark)
            field_count += 1

    await db.commit()
    result: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "field_count": field_count}
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


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
    if sheet == "D7-1":
        for block, row_key, label in _D7_1_ROWS:
            ws.append([block, row_key, label, *[None] * (len(headers) - 3)])

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

    if sheet == "D7-1":
        return await _export_d7_1_data(wp_id, db)

    rows_data: list[dict] = []
    if sheet == "D7-4":
        for item_id, row_type in [("D7-4-debit-rows", "debit"), ("D7-4-credit-rows", "credit")]:
            result = await db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                ),
                {"wp_id": wp_id, "item_id": item_id},
            )
            row = result.fetchone()
            if row and row.remark:
                try:
                    parsed = json.loads(row.remark)
                    if isinstance(parsed, list):
                        for r in parsed:
                            rows_data.append({**r, "_rowType": row_type})
                except (json.JSONDecodeError, TypeError):
                    pass
    else:
        item_id = _SHEET_ITEM_ID[sheet]
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
            ),
            {"wp_id": wp_id, "item_id": item_id},
        )
        row = result.fetchone()
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

    if sheet == "D7-1":
        result = await _import_d7_1_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

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

    if sheet == "D7-4":
        debit_rows = [r for r in rows_data if _safe_str(r.get("_rowType")).lower() != "credit"]
        credit_rows = [r for r in rows_data if _safe_str(r.get("_rowType")).lower() == "credit"]
        for item_id, payload in [("D7-4-debit-rows", debit_rows), ("D7-4-credit-rows", credit_rows)]:
            remark_json = json.dumps(payload, ensure_ascii=False)
            await db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
                    VALUES (:id, :wp_id, :item_id, :remark, NOW())
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET remark = :remark, updated_at = NOW()
                """),
                {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
            )
    else:
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
    elif sheet == "D7-3":
        return [
            _safe_str(data.get("description")), _safe_str(data.get("category")),
            _safe_str(data.get("reportItem")), _safe_str(data.get("accountName")),
            _safe_str(data.get("noteItem")), _safe_str(data.get("placeholder")),
            _safe_float(data.get("debitAmount")), _safe_float(data.get("creditAmount")),
            _safe_str(data.get("indexRef")), _safe_str(data.get("remark")),
        ]
    elif sheet == "D7-4":
        return [
            _safe_str(data.get("_rowType")), _safe_str(data.get("item")),
            _safe_float(data.get("amount")), _safe_str(data.get("dataSource")),
            _safe_str(data.get("remark")),
        ]
    elif sheet == "D7-7-period":
        check_items = data.get("checkItems") or [False] * 5
        return [
            _safe_str(data.get("customerName")), _safe_str(data.get("date")),
            _safe_str(data.get("voucherNo")), _safe_str(data.get("businessContent")),
            _safe_str(data.get("counterAccount")), _safe_str(data.get("counterDetail")),
            _safe_float(data.get("debitAmount")), _safe_float(data.get("creditAmount")),
            _safe_str(data.get("supportDocs")),
            *["Y" if c else "" for c in (list(check_items) + [False] * 5)[:5]],
            _safe_str(data.get("indexRef")),
            "是" if data.get("isAbnormal") else "",
            _safe_str(data.get("remark")),
        ]
    elif sheet == "D7-7-post":
        check_items = data.get("checkItems") or [False] * 5
        return [
            _safe_str(data.get("customerName")), _safe_str(data.get("date")),
            _safe_str(data.get("voucherNo")), _safe_str(data.get("businessContent")),
            _safe_str(data.get("counterAccount")), _safe_str(data.get("counterDetail")),
            _safe_float(data.get("creditAmount")), _safe_str(data.get("supportDocs")),
            *["Y" if c else "" for c in (list(check_items) + [False] * 5)[:5]],
            _safe_str(data.get("indexRef")),
            "是" if data.get("isAbnormal") else "",
            _safe_str(data.get("remark")),
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
    elif sheet == "D7-3":
        return {
            "rowId": str(uuid4()),
            "description": _safe_str(_col_val(row, actual_headers, "调整事项说明")),
            "category": _safe_str(_col_val(row, actual_headers, "类别")) or "账项调整",
            "reportItem": _safe_str(_col_val(row, actual_headers, "报表项目")),
            "accountName": _safe_str(_col_val(row, actual_headers, "科目名称")),
            "noteItem": _safe_str(_col_val(row, actual_headers, "附注项目")),
            "placeholder": _safe_str(_col_val(row, actual_headers, "占位/对应项")),
            "debitAmount": _safe_float(_col_val(row, actual_headers, "借方调整金额")),
            "creditAmount": _safe_float(_col_val(row, actual_headers, "贷方调整金额")),
            "indexRef": _safe_str(_col_val(row, actual_headers, "索引")),
            "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        }
    elif sheet == "D7-4":
        return {
            "rowId": str(uuid4()),
            "_rowType": _safe_str(_col_val(row, actual_headers, "记录类型")).lower() or "debit",
            "item": _safe_str(_col_val(row, actual_headers, "项目")),
            "amount": _safe_float(_col_val(row, actual_headers, "金额")),
            "dataSource": _safe_str(_col_val(row, actual_headers, "数据来源")),
            "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        }
    elif sheet == "D7-7-period":
        check_items = [
            _safe_str(_col_val(row, actual_headers, f"核对内容{i}")).upper() in ("Y", "是", "TRUE", "1")
            for i in range(1, 6)
        ]
        abnormal_raw = _safe_str(_col_val(row, actual_headers, "是否异常"))
        return {
            "rowId": str(uuid4()),
            "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
            "date": _safe_str(_col_val(row, actual_headers, "日期")),
            "voucherNo": _safe_str(_col_val(row, actual_headers, "凭证号")),
            "businessContent": _safe_str(_col_val(row, actual_headers, "业务内容")),
            "counterAccount": _safe_str(_col_val(row, actual_headers, "对方科目")),
            "counterDetail": _safe_str(_col_val(row, actual_headers, "对方明细")),
            "debitAmount": _safe_float(_col_val(row, actual_headers, "借方金额")),
            "creditAmount": _safe_float(_col_val(row, actual_headers, "贷方金额")),
            "supportDocs": _safe_str(_col_val(row, actual_headers, "支持性文件")),
            "checkItems": check_items,
            "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
            "isAbnormal": abnormal_raw in ("是", "Y", "TRUE", "1", "true"),
            "remark": _safe_str(_col_val(row, actual_headers, "备注说明")),
        }
    elif sheet == "D7-7-post":
        check_items = [
            _safe_str(_col_val(row, actual_headers, f"核对内容{i}")).upper() in ("Y", "是", "TRUE", "1")
            for i in range(1, 6)
        ]
        abnormal_raw = _safe_str(_col_val(row, actual_headers, "是否异常"))
        return {
            "rowId": str(uuid4()),
            "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
            "date": _safe_str(_col_val(row, actual_headers, "日期")),
            "voucherNo": _safe_str(_col_val(row, actual_headers, "凭证号")),
            "businessContent": _safe_str(_col_val(row, actual_headers, "业务内容")),
            "counterAccount": _safe_str(_col_val(row, actual_headers, "对方科目")),
            "counterDetail": _safe_str(_col_val(row, actual_headers, "对方明细")),
            "creditAmount": _safe_float(_col_val(row, actual_headers, "贷方金额")),
            "supportDocs": _safe_str(_col_val(row, actual_headers, "支持性文件")),
            "checkItems": check_items,
            "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
            "isAbnormal": abnormal_raw in ("是", "Y", "TRUE", "1", "true"),
            "remark": _safe_str(_col_val(row, actual_headers, "备注说明")),
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
    "D7-7-period": [
        "D7-7 凭证检查 — 本期增减变动 编制说明",
        "",
        "1. 填写抽样选取的本期合同负债增减凭证样本。",
        "2. 核对内容1~5列填 Y 表示已核对。",
        "3. 是否异常列填「是」标记异常样本。",
    ],
    "D7-7-post": [
        "D7-7 凭证检查 — 期后结转 编制说明",
        "",
        "1. 填写期后结转/冲减合同负债的凭证样本。",
        "2. 贷方金额为期后结转金额，将联动 D7-2 期后结转列。",
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
