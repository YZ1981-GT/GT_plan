"""底稿模板文件路由

提供底稿 xlsx 文件的获取和初始化端点。
WorkpaperEditor 前端通过这些端点加载底稿 xlsx 文件供 Univer 渲染。
"""
from __future__ import annotations

import logging
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_template_init_service import (
    get_workpaper_file,
    get_workpaper_storage_path,
    init_workpaper_from_template,
    list_available_templates,
    prefill_workpaper_xlsx,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/template-file",
    tags=["workpaper-template-files"],
)


@router.get("")
async def get_workpaper_xlsx(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取底稿 xlsx 文件（供 Univer importXLSX 加载）

    如果底稿文件已存在，直接返回。
    如果不存在，从模板初始化后自动 prefill 试算表数据再返回。
    """
    pid = UUID(project_id)
    wid = UUID(wp_id)

    # 检查是否已有底稿文件
    existing = get_workpaper_file(pid, wid)
    if existing:
        return FileResponse(
            str(existing),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=existing.name,
        )

    # 从数据库获取 wp_code（支持多种关联方式）
    row = (await db.execute(text("""
        SELECT i.wp_code
        FROM working_paper w
        LEFT JOIN wp_index i ON w.wp_index_id = i.id
        WHERE w.id = :wid
    """), {"wid": wp_id})).first()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="底稿不存在或无编码，无法加载模板")
    else:
        wp_code = row[0]

    # 从模板初始化
    result = init_workpaper_from_template(pid, wid, wp_code)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"模板文件不存在: {wp_code}（系统将使用空白 Univer 编辑器）",
        )

    # P1-1: Auto-prefill on first initialization
    # Only prefill xlsx files (not xlsm/docx)
    if result.suffix.lower() == '.xlsx':
        tb_data = await _get_tb_data_for_prefill(db, pid)
        if tb_data:
            try:
                filled = prefill_workpaper_xlsx(result, wp_code, tb_data)
                if filled > 0:
                    logger.info("Auto-prefill on init: wp_code=%s, filled=%d cells", wp_code, filled)
            except Exception as e:
                logger.warning("Auto-prefill failed (non-blocking): wp_code=%s, error=%s", wp_code, e)

    return FileResponse(
        str(result),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=result.name,
    )


@router.post("/init")
async def init_from_template(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """手动触发从模板初始化底稿文件（覆盖已有文件）"""
    pid = UUID(project_id)
    wid = UUID(wp_id)

    row = (await db.execute(text("""
        SELECT i.wp_code FROM working_paper w
        JOIN wp_index i ON w.wp_index_id = i.id
        WHERE w.id = :wid
    """), {"wid": wp_id})).first()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="底稿不存在或无编码")

    result = init_workpaper_from_template(pid, wid, row[0])
    if not result:
        raise HTTPException(status_code=404, detail=f"模板文件不存在: {row[0]}")

    return {
        "message": f"底稿已从模板初始化: {row[0]}",
        "file_path": str(result.name),
        "size_kb": round(result.stat().st_size / 1024, 1),
    }


@router.get("/available-templates", include_in_schema=True)
async def get_available_templates():
    """列出所有可用模板（供前端展示）"""
    templates = list_available_templates()
    return {"items": templates, "total": len(templates)}


@router.post("/upload-xlsx")
async def upload_xlsx_file(
    project_id: str,
    wp_id: str,
    request: Request,
):
    """接收 Univer 导出的 xlsx blob 并覆盖保存

    P2-2: 加入文件级冲突检测——如果服务端文件的修改时间比客户端打开时更新，
    说明有其他人在此期间保存过，返回 409 提示冲突。
    前端通过 header X-File-Opened-At 传递打开时间戳。
    """
    pid = UUID(project_id)
    wid = UUID(wp_id)
    storage_path = get_workpaper_storage_path(pid, wid)

    # P2-2: 文件级冲突检测
    opened_at = request.headers.get("X-File-Opened-At")
    if opened_at and storage_path.exists():
        try:
            file_mtime = storage_path.stat().st_mtime
            client_opened = float(opened_at)
            if file_mtime > client_opened:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "XLSX_FILE_CONFLICT",
                        "message": "底稿文件已被其他用户修改，请刷新后重试",
                        "server_mtime": file_mtime,
                        "client_opened_at": client_opened,
                    },
                )
        except (ValueError, TypeError):
            pass  # 无法解析时间戳，跳过冲突检测

    form = await request.form()
    file = form.get("file")
    if file:
        content = await file.read()
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(storage_path, "wb") as f:
            f.write(content)
        logger.info("xlsx saved: %s (%d bytes)", storage_path.name, len(content))
        return {"message": "xlsx 已保存", "size_kb": round(len(content) / 1024, 1)}

    raise HTTPException(status_code=400, detail="未收到文件")


async def _get_tb_data_for_prefill(
    db: AsyncSession,
    project_id: UUID,
) -> dict[str, dict[str, float]]:
    """P1-1: Query trial_balance data for prefill.

    Returns: {standard_account_code: {列名: 值}} dict suitable for prefill_workpaper_xlsx.
    """
    try:
        result = await db.execute(text("""
            SELECT
                tb.standard_account_code,
                tb.opening_balance,
                tb.unadjusted_amount,
                tb.audited_amount
            FROM trial_balance tb
            WHERE tb.project_id = :pid
            LIMIT 5000
        """), {"pid": str(project_id)})
        rows = result.fetchall()
    except Exception:
        # trial_balance table may not exist or have different schema
        return {}

    if not rows:
        return {}

    tb_data: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row[0]
        if not code:
            continue
        # trial_balance 无 closing_balance/借贷发生额列：期末余额/未审数取 unadjusted_amount，
        # 审定数取 audited_amount；发生额明细在 tb_balance（此处不取）。
        tb_data[code] = {
            "期初余额": float(row[1] or 0),
            "期末余额": float(row[2] or 0),
            "未审数": float(row[2] or 0),
            "审定数": float(row[3] or 0),
        }
    return tb_data



# ─────────────────────────────────────────────────────────────────────────────
# proposal-remaining-18 D-1 大底稿懒加载 — 单 sheet 按需端点
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/sheet/{sheet_name}")
async def get_single_sheet_data(
    project_id: str,
    wp_id: str,
    sheet_name: str,
    db: AsyncSession = Depends(get_db),
):
    """proposal-remaining-18 D-1：按需加载单个 sheet 完整数据

    配合 GET /xlsx-to-json?sheets=active 使用：
    - 首屏只加载 active sheet（其余仅元数据）
    - 用户切换 sheet 时调用此端点按需加载
    - 前端 useLazySheetLoader composable 含缓存 + inflight 去重

    返回：单 sheet 完整对象 {id, name, rowCount, columnCount, cellData, mergeData, ...}
    """
    pid = UUID(project_id)
    wid = UUID(wp_id)

    # 1. 找 storage 文件，不存在则从模板初始化
    storage_path = get_workpaper_file(pid, wid)
    if not storage_path:
        row = (await db.execute(text("""
            SELECT i.wp_code FROM working_paper w
            LEFT JOIN wp_index i ON w.wp_index_id = i.id
            WHERE w.id = :wid
        """), {"wid": wp_id})).first()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="底稿不存在或无编码")
        result = init_workpaper_from_template(pid, wid, row[0])
        if not result:
            raise HTTPException(status_code=404, detail=f"模板文件不存在: {row[0]}")
        storage_path = result

    if storage_path.suffix.lower() not in (".xlsx", ".xlsm"):
        raise HTTPException(
            status_code=400,
            detail=f"非 xlsx 类底稿: {storage_path.name}",
        )

    try:
        from openpyxl import load_workbook
        content = storage_path.read_bytes()
        wb = load_workbook(BytesIO(content), read_only=False, data_only=False)

        if sheet_name not in wb.sheetnames:
            wb.close()
            raise HTTPException(
                status_code=404,
                detail=f"sheet 不存在: {sheet_name}",
            )

        from app.routers.wp_template_xlsx import _build_sheet_obj_from_ws

        idx = wb.sheetnames.index(sheet_name)
        sheet_id = f"sheet{idx}"
        ws = wb[sheet_name]
        sheet_obj = _build_sheet_obj_from_ws(ws, sheet_id, sheet_name)
        wb.close()

        return JSONResponse(content=sheet_obj)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_single_sheet_data failed: sheet=%s, err=%s", sheet_name, e)
        raise HTTPException(
            status_code=500,
            detail=f"加载 sheet 失败: {type(e).__name__}: {e}",
        )
