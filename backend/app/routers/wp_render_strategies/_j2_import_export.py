"""J2 设定受益计划 — 导入导出端点.

三端点：
- GET /j2/export-template  导出空白模板
- GET /j2/export-data      导出当前数据
- POST /j2/import-data     导入数据

多区块分sheet导出：审定表 + 明细表 + 精算假设

Spec: .kiro/specs/j2-defined-benefit-plan/
Requirements: 5.2
"""
from __future__ import annotations
import io
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/j2", tags=["j2-import-export"])


@router.get("/export-template")
async def export_template(wp_id: str, db: AsyncSession = Depends(get_db)):
    """导出J2设定受益计划空白模板."""
    try:
        import openpyxl
        wb = openpyxl.Workbook()

        # Sheet1: 审定表
        ws_adj = wb.active
        ws_adj.title = "审定表J2-1"
        adj_headers = [
            "项目名称", "期初未审数", "期初AJE", "期初审定数",
            "期末未审数", "期末AJE", "期末审定数", "原因分析",
        ]
        ws_adj.append(adj_headers)
        ws_adj.append(["设定受益计划", 0, 0, 0, 0, 0, 0, ""])
        ws_adj.append(["其他长期职工福利", 0, 0, 0, 0, 0, 0, ""])
        ws_adj.append(["辞退福利", 0, 0, 0, 0, 0, 0, ""])

        # Sheet2: 明细表
        ws_det = wb.create_sheet("明细表J2-2")
        det_headers = [
            "项目", "期初余额", "服务成本", "利息费用", "精算损失",
            "已支付福利", "精算利得", "期末余额", "计划资产FV", "净负债",
        ]
        ws_det.append(det_headers)
        ws_det.append(["离职后福利-设定受益计划", 0, 0, 0, 0, 0, 0, 0, 0, 0])

        # Sheet3: 精算假设
        ws_assum = wb.create_sheet("精算假设")
        assum_headers = ["假设名称", "本期值", "上期值", "行业均值", "合理性评价"]
        ws_assum.append(assum_headers)
        ws_assum.append(["折现率", 0.04, 0.04, None, ""])
        ws_assum.append(["薪酬增长率", 0.08, 0.08, None, ""])
        ws_assum.append(["死亡率", 0.005, 0.005, None, ""])
        ws_assum.append(["离职率", 0.10, 0.10, None, ""])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = "J2_设定受益计划_模板.xlsx"
        encoded = filename.encode("utf-8").decode("latin-1")

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            },
        )
    except Exception as e:
        logger.error("J2 export template failed: %s", e)
        return {"error": str(e)}


@router.get("/export-data")
async def export_data(wp_id: str, db: AsyncSession = Depends(get_db)):
    """导出J2当前数据."""
    try:
        import openpyxl

        # 从 checklist_responses 读取当前数据
        result = await db.execute(
            sa.text(
                "SELECT item_id, content FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": wp_id, "pfx": "J2-%"},
        )
        responses = {}
        for row in result.fetchall():
            responses[row.item_id] = row.content or ""

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "J2数据"
        ws.append(["item_id", "content"])
        for k, v in responses.items():
            ws.append([k, v])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = "J2_设定受益计划_数据.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            },
        )
    except Exception as e:
        logger.error("J2 export data failed: %s", e)
        return {"error": str(e)}


@router.post("/import-data")
async def import_data(wp_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """导入J2数据."""
    try:
        import openpyxl
        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content))

        imported_count = 0

        # 处理审定表sheet
        if "审定表J2-1" in wb.sheetnames:
            ws = wb["审定表J2-1"]
            adj_data = []
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
                if row and row[0]:
                    adj_data.append({
                        "label": row[0],
                        "beginUnadj": float(row[1] or 0),
                        "beginAje": float(row[2] or 0),
                        "endUnadj": float(row[4] or 0),
                        "endAje": float(row[5] or 0),
                        "reasonAnalysis": row[7] or "",
                    })
            if adj_data:
                await _save_response(db, wp_id, "J2-adjudication-data", json.dumps(adj_data, ensure_ascii=False))
                imported_count += len(adj_data)

        # 处理精算假设sheet
        if "精算假设" in wb.sheetnames:
            ws = wb["精算假设"]
            assumptions = {}
            key_map = {"折现率": "discountRate", "薪酬增长率": "salaryGrowthRate", "死亡率": "mortalityRate", "离职率": "turnoverRate"}
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row and row[0] in key_map:
                    assumptions[key_map[row[0]]] = float(row[1] or 0)
            if assumptions:
                await _save_response(db, wp_id, "J2-actuarial-assumptions", json.dumps(assumptions))
                imported_count += 1

        await db.commit()
        return {"imported_count": imported_count, "status": "success"}
    except Exception as e:
        logger.error("J2 import data failed: %s", e)
        await db.rollback()
        return {"error": str(e)}


async def _save_response(db: AsyncSession, wp_id: str, item_id: str, content: str):
    """upsert checklist_response."""
    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses (wp_id, item_id, content) "
            "VALUES (:wp_id, :item_id, :content) "
            "ON CONFLICT (wp_id, item_id) DO UPDATE SET content = :content"
        ),
        {"wp_id": wp_id, "item_id": item_id, "content": content},
    )
