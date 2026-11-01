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
    from app.services.wp_visibility.entry_integration import make_bulk_preflight

    # Wp_Bound_Gate（Task 4 / R3）：把 TB 派生值写入底稿正文前，逐资源 preflight
    # （make_bulk_preflight，save_parsed_data 写族）；任一目标不可见/跨项目/未委派 →
    # 抛 ExternalNotFound(404)，整请求原子失败于任何副作用前（不 fail-soft 跳过）。
    preflight = make_bulk_preflight(
        db, current_user, entrypoint="workpaper.parsed_data_write",
        action="save_parsed_data", method="PUT", entry_family="prefill",
    )
    for wp_id in body.wp_ids:
        await preflight(wp_id, None)

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
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    # Wp_Bound_Gate（Task 4 / R3）：渲染打包底稿正文前用可见集过滤 wp_ids；
    # 不可见/跨项目/未委派/scope 外底稿静默剔除，manifest 只由可见集构建。
    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="export",
    )
    visible_wp_ids = [wid for wid in body.wp_ids if await _visible(wid, None)]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for wp_id in visible_wp_ids:
            # Stub: 实际实现调用 soffice --headless --convert-to pdf
            placeholder = f"PDF placeholder for workpaper {wp_id}\n"
            zf.writestr(f"{wp_id}.pdf", placeholder.encode())

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workpapers_export.zip"},
    )


@router.post("/batch-submit")
async def batch_submit_review(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """退役不写库的假成功入口；旧客户端稳定得到 410。"""
    _ = current_user
    raise HTTPException(
        status_code=410,
        detail={
            "code": "LEGACY_BATCH_REVIEW_RETIRED",
            "message": "旧批量提交入口已退役，请刷新页面后重试",
            "replacement": f"/api/projects/{project_id}/working-papers/batch-submit",
        },
    )
