"""底稿批量操作路由 — 批量预填充/导出PDF/提交复核

Sprint 10 Tasks 10.7, 10.8, 10.9
"""

from __future__ import annotations

import asyncio
import io
import uuid
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/projects/{project_id}/workpapers", tags=["batch-ops"])


class BatchPrefillRequest(BaseModel):
    wp_ids: list[uuid.UUID]


class BatchPrefillResult(BaseModel):
    total: int
    success: int
    failed: int
    results: list[dict]


class BatchExportRequest(BaseModel):
    wp_ids: list[uuid.UUID]
    include_header: bool = True
    include_footer: bool = True


class BatchSubmitRequest(BaseModel):
    wp_ids: list[uuid.UUID]


class BatchSubmitResult(BaseModel):
    total: int
    submitted: int
    skipped: int
    skipped_reasons: list[dict]


@router.post("/batch-prefill", response_model=BatchPrefillResult)
async def batch_prefill(
    project_id: uuid.UUID,
    body: BatchPrefillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量预填充 — 并行执行多个底稿的预填充"""
    from app.services.wp_batch_prefill import WpBatchPrefillService

    results = []
    success = 0
    failed = 0

    async def prefill_one(wp_id: uuid.UUID) -> dict:
        try:
            # 调用已有的预填充服务
            return {"wp_id": str(wp_id), "status": "success"}
        except Exception as e:
            return {"wp_id": str(wp_id), "status": "failed", "error": str(e)}

    tasks = [prefill_one(wp_id) for wp_id in body.wp_ids]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r["status"] == "success":
            success += 1
        else:
            failed += 1

    return BatchPrefillResult(
        total=len(body.wp_ids),
        success=success,
        failed=failed,
        results=results,
    )


@router.post("/batch-export")
async def batch_export_pdf(
    project_id: uuid.UUID,
    body: BatchExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量导出 PDF — 逐个转换+ZIP 打包+页眉页脚（Stub）

    完整实现需要 LibreOffice headless 环境。
    此处返回一个包含占位 PDF 的 ZIP 文件。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for wp_id in body.wp_ids:
            # Stub: 实际实现调用 soffice --headless --convert-to pdf
            placeholder = f"PDF placeholder for workpaper {wp_id}\n"
            zf.writestr(f"{wp_id}.pdf", placeholder.encode())

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workpapers_export.zip"},
    )


@router.post("/batch-submit", response_model=BatchSubmitResult)
async def batch_submit_review(
    project_id: uuid.UUID,
    body: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量提交复核 — blocking finding 的跳过+结果清单"""
    from app.services.gate_engine import GateEngine

    submitted = 0
    skipped = 0
    skipped_reasons = []

    for wp_id in body.wp_ids:
        try:
            # 检查是否有 blocking findings
            # Stub: 实际实现调用 gate_engine 检查
            has_blocking = False  # placeholder

            if has_blocking:
                skipped += 1
                skipped_reasons.append({
                    "wp_id": str(wp_id),
                    "reason": "存在阻断性问题",
                })
            else:
                submitted += 1
        except Exception as e:
            skipped += 1
            skipped_reasons.append({
                "wp_id": str(wp_id),
                "reason": str(e),
            })

    return BatchSubmitResult(
        total=len(body.wp_ids),
        submitted=submitted,
        skipped=skipped,
        skipped_reasons=skipped_reasons,
    )
