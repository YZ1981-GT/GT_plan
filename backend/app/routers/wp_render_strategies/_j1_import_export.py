"""J1 应付职工薪酬 — 导入导出3端点.

支持的sheet类型：detail(明细表J1-2) / accrual(计提J1-6) / allocation(分配J1-7)
/ general(检查J1-8) / non_monetary(非货币J1-9) / severance(辞退J1-10)

Spec: .kiro/specs/j1-employee-compensation/
Requirements: 5.2
"""
from __future__ import annotations
import io
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
import sqlalchemy as sa
from openpyxl import Workbook, load_workbook

from app.core.database import get_db
from app.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["j1-import-export"])

SHEET_TYPES = {"detail", "accrual", "allocation", "general", "non_monetary", "severance"}

SHEET_COLUMNS = {
    "detail": ["项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
               "期末未审", "期末AJE", "期末RJE", "期末审定",
               "附注期初", "附注增加", "附注减少", "附注期末"],
    "accrual": ["薪酬类别", "人数", "基数/均薪", "比例", "月数", "应提(测算)", "实提", "差异率", "说明"],
    "allocation": ["薪酬项目", "管理费用", "销售费用", "生产成本", "制造费用",
                   "研发费用", "在建工程", "其他", "行合计", "贷方增加", "差额"],
    "general": ["区块", "凭证号", "日期", "摘要", "金额", "对方科目", "检查结果"],
    "non_monetary": ["福利形式", "实物来源", "计量方式", "金额", "凭证号", "受益人数", "检查结论"],
    "severance": ["部门", "涉及人数", "预计金额", "实际计提", "正式计划", "不可撤回", "精算师", "支付期间", "结论"],
}


@router.get("/api/workpapers/{wp_id}/j1/export-template")
async def export_template(
    wp_id: str,
    sheet_type: str = Query(...),
    _user=Depends(get_current_user),
):
    """导出模板（空表头）."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    wb = Workbook()
    ws = wb.active
    ws.title = f"J1-{sheet_type}"
    columns = SHEET_COLUMNS[sheet_type]
    ws.append(columns)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"J1_{sheet_type}_模板.xlsx"
    encoded = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.get("/api/workpapers/{wp_id}/j1/export-data")
async def export_data(
    wp_id: str,
    sheet_type: str = Query(...),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    """导出数据（含现有数据）."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    # 从 checklist_responses 读取数据
    item_id = f"J1-{sheet_type}-data"
    result = await db.execute(
        sa.text("SELECT content FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
        {"wp_id": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    data_rows = []
    if row and row.content:
        try:
            data_rows = json.loads(row.content)
        except (json.JSONDecodeError, TypeError):
            pass

    wb = Workbook()
    ws = wb.active
    ws.title = f"J1-{sheet_type}"
    columns = SHEET_COLUMNS[sheet_type]
    ws.append(columns)
    for item in data_rows:
        ws.append([item.get(c, "") for c in columns])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"J1_{sheet_type}_数据.xlsx"
    encoded = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/api/workpapers/{wp_id}/j1/import-data")
async def import_data(
    wp_id: str,
    file: UploadFile = File(...),
    sheet_type: str = Query("detail"),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    """导入数据."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    content = await file.read()
    wb = load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

    # 读取表头
    headers = [str(cell.value or "").strip() for cell in ws[1]]
    # 读取数据行
    imported_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_dict = {}
        for i, val in enumerate(row):
            if i < len(headers):
                row_dict[headers[i]] = val
        if any(v is not None and v != "" for v in row_dict.values()):
            imported_rows.append(row_dict)

    # 存储到 checklist_responses
    item_id = f"J1-{sheet_type}-data"
    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses (wp_id, item_id, content) "
            "VALUES (:wp_id, :iid, :content) "
            "ON CONFLICT (wp_id, item_id) DO UPDATE SET content = :content"
        ),
        {"wp_id": wp_id, "iid": item_id, "content": json.dumps(imported_rows, ensure_ascii=False)},
    )
    await db.commit()

    return {"imported_count": len(imported_rows), "sheet_type": sheet_type}
