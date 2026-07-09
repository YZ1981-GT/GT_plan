"""J3 股份支付 — 导入导出端点.

三端点：template / export / import
动态行表格（J3-1 情况表）需要导入导出支持。

Spec: .kiro/specs/j3-share-based-payment/
Requirements: 2.7
"""
from __future__ import annotations
import io
import json
import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/import-export", tags=["j3-import-export"])

# ── J3-1 情况表列定义 ──────────────────────────────────────────────────────────

J3_DETAIL_COLUMNS = [
    "方案名称", "类型(权益/现金)", "授予日", "行权价", "标的股数",
    "等待期(年)", "可行权日", "有效期截止", "单位公允价值",
    "已服务年数", "以前累计确认", "本期确认", "累计确认", "剩余待确认", "状态",
]


@router.get("/template")
async def export_template(wp_id: str, user=Depends(get_current_user)):
    """导出空白模板."""
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "J3-1 股份支付情况表"

        # 写表头
        for col_idx, header in enumerate(J3_DETAIL_COLUMNS, 1):
            ws.cell(row=1, column=col_idx, value=header)

        # 示例行
        ws.cell(row=2, column=1, value="（示例）2024年股票期权激励")
        ws.cell(row=2, column=2, value="权益")
        ws.cell(row=2, column=3, value="2024-01-15")

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"J3_股份支付_模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
        encoded_name = quote(filename)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except Exception as e:
        logger.error("J3 template export failed: %s", e)
        raise HTTPException(status_code=500, detail="模板导出失败") from e


@router.get("/export")
async def export_data(wp_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """导出当前数据."""
    try:
        import openpyxl

        # 读取方案数据
        result = await db.execute(
            sa.text(
                "SELECT content FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = 'J3-plans-data'"
            ),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        plans = []
        if row and row.content:
            try:
                plans = json.loads(row.content)
            except (json.JSONDecodeError, TypeError):
                pass

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "J3-1 股份支付情况表"

        # 表头
        for col_idx, header in enumerate(J3_DETAIL_COLUMNS, 1):
            ws.cell(row=1, column=col_idx, value=header)

        # 数据行
        for row_idx, plan in enumerate(plans, 2):
            ws.cell(row=row_idx, column=1, value=plan.get("name", ""))
            ws.cell(row=row_idx, column=2, value=plan.get("type", ""))
            ws.cell(row=row_idx, column=3, value=plan.get("grantDate", ""))
            ws.cell(row=row_idx, column=4, value=plan.get("exercisePrice", 0))
            ws.cell(row=row_idx, column=5, value=plan.get("sharesCount", 0))
            ws.cell(row=row_idx, column=6, value=plan.get("vestingPeriod", 0))
            ws.cell(row=row_idx, column=7, value=plan.get("vestingDate", ""))
            ws.cell(row=row_idx, column=8, value=plan.get("expiryDate", ""))
            ws.cell(row=row_idx, column=9, value=plan.get("unitFairValue", 0))
            ws.cell(row=row_idx, column=10, value=plan.get("serviceYears", 0))
            ws.cell(row=row_idx, column=11, value=plan.get("priorCumulative", 0))
            ws.cell(row=row_idx, column=12, value=plan.get("currentExpense", 0))
            ws.cell(row=row_idx, column=13, value=plan.get("cumulativeExpense", 0))
            ws.cell(row=row_idx, column=14, value=plan.get("remainingExpense", 0))
            ws.cell(row=row_idx, column=15, value=plan.get("status", ""))

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"J3_股份支付_数据_{datetime.now().strftime('%Y%m%d')}.xlsx"
        encoded_name = quote(filename)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except Exception as e:
        logger.error("J3 export failed: %s", e)
        raise HTTPException(status_code=500, detail="数据导出失败") from e


@router.post("/import")
async def import_data(
    wp_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """导入Excel数据."""
    try:
        import openpyxl

        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active

        plans = []
        for row_idx in range(2, ws.max_row + 1):
            name = ws.cell(row=row_idx, column=1).value
            if not name:
                continue
            plan = {
                "id": f"plan-import-{row_idx}",
                "name": str(name),
                "type": "equity" if str(ws.cell(row=row_idx, column=2).value or "").startswith("权") else "cash",
                "grantDate": str(ws.cell(row=row_idx, column=3).value or ""),
                "exercisePrice": float(ws.cell(row=row_idx, column=4).value or 0),
                "sharesCount": int(ws.cell(row=row_idx, column=5).value or 0),
                "vestingPeriod": float(ws.cell(row=row_idx, column=6).value or 3),
                "vestingDate": str(ws.cell(row=row_idx, column=7).value or ""),
                "expiryDate": str(ws.cell(row=row_idx, column=8).value or ""),
                "unitFairValue": float(ws.cell(row=row_idx, column=9).value or 0),
                "serviceYears": float(ws.cell(row=row_idx, column=10).value or 0),
                "priorCumulative": float(ws.cell(row=row_idx, column=11).value or 0),
                "currentExpense": float(ws.cell(row=row_idx, column=12).value or 0),
                "cumulativeExpense": float(ws.cell(row=row_idx, column=13).value or 0),
                "remainingExpense": float(ws.cell(row=row_idx, column=14).value or 0),
                "status": str(ws.cell(row=row_idx, column=15).value or "vesting"),
            }
            plans.append(plan)

        # 存储到 checklist_responses（JSON打包）
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (wp_id, item_id, content) "
                "VALUES (:wp_id, :item_id, :content) "
                "ON CONFLICT (wp_id, item_id) DO UPDATE SET content = :content"
            ),
            {
                "wp_id": wp_id,
                "item_id": "J3-plans-data",
                "content": json.dumps(plans, ensure_ascii=False),
            },
        )
        await db.commit()

        return {"code": 0, "message": f"成功导入 {len(plans)} 个方案", "data": {"count": len(plans)}}
    except Exception as e:
        logger.error("J3 import failed: %s", e)
        raise HTTPException(status_code=500, detail="数据导入失败") from e
