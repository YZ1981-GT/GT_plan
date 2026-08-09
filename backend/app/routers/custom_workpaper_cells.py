"""自定义底稿单元格编辑与投影刷新端点。

## 架构口径：xlsx 权威 + 单向投影

**xlsx 文件是唯一权威，`parsed_data.html_data[sheet]` 是它的投影。**

故本模块的两个端点都遵守同一顺序：

    ① 先写 xlsx（权威）      write_cells_to_xlsx
    ② 再从 xlsx 重投影        refresh_custom_projection
    ③ 递增 file_version 并提交

🔴 顺序反了（先刷投影再写 xlsx）会让投影领先于权威 —— 若 xlsx 写入失败，
   用户会看到一个「界面上有、文件里没有」的值，且下次 render 重投影时静默消失。

🔴 `write_cells_to_xlsx` 写盘失败**抛异常不 fail-open**：xlsx 是权威，写不进去
   就不能向用户报成功（这是它与投影读取路径 fail-open 语义相反的原因）。

spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 2 Task 6
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.custom_workpaper_context import (
    CustomWpContext,
    load_custom_context,
)
from app.services.custom_workpaper_projection import (
    normalize_cell_ref,
    refresh_custom_projection,
    write_cells_to_xlsx,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}",
    tags=["custom-workpaper-cells"],
)

#: 单次请求最多写入格数。防前端一次把整张大表推上来把 xlsx 写爆。
#: 🔴 超限返 422 且带 `overflow` 标记（不静默截断 —— 截断会让用户以为都存上了）。
MAX_CELL_UPDATES = 500


class CustomCellsUpdateRequest(BaseModel):
    """单元格补丁请求。

    🔴 body 键是 `updates` 而非 `patches` —— 与
    `custom_workpaper_projection.write_cells_to_xlsx(file_path, sheet_name, updates)`
    的参数名保持一致，避免同一份数据在两层用两个名字。
    """

    sheet_name: str | None = Field(
        default=None,
        description="目标 sheet，缺省取 wp_code（自定义底稿 sheet 名恒等于 wp_code）",
    )
    updates: dict[str, Any] = Field(
        default_factory=dict, description='单元格补丁，如 {"B5": 123.45, "C7": "文字"}'
    )


class CustomProjectionRefreshRequest(BaseModel):
    sheet_name: str | None = Field(default=None, description="缺省取 wp_code")


async def _require_custom_ctx(
    db: AsyncSession, wp_id: UUID, *, require_writable: bool
) -> CustomWpContext:
    """加载并校验自定义底稿上下文。

    404 底稿不存在 / 409 非 custom 类型 / 403 只读态。

    🔴 **409 而非静默放行**：标准底稿的 HTML 侧是结构化表单（字段有确定审计语义），
    往它的 xlsx 直写格会绕过审计语义校验，且它的 HTML 侧根本不读 xlsx 投影 ——
    写进去用户也看不见，属于「静默写坏文件」。
    """
    ctx = await load_custom_context(db, wp_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    if not ctx.is_custom:
        raise HTTPException(
            status_code=409,
            detail=(
                f"底稿 {ctx.wp_code or wp_id} 不是自定义底稿（componentType != custom），"
                "不支持直接编辑单元格"
            ),
        )
    if require_writable and ctx.is_read_only:
        raise HTTPException(status_code=403, detail="底稿已归档，不可编辑")
    return ctx


def _resolve_sheet_name(ctx: CustomWpContext, requested: str | None) -> str:
    """解析目标 sheet 名。

    🔴 自定义底稿的 sheet 名恒等于 wp_code。前端传了不一致的值时以 wp_code 为准
    并记 WARNING —— 写到别的 sheet 上会让 render 取不到 html_data（render 只读
    `html_data[wp_code]`），表现为「保存成功但界面没变」。
    """
    want = (requested or "").strip()
    if want and ctx.sheet_name and want != ctx.sheet_name:
        logger.warning(
            "custom-cells: sheet_name 与 wp_code 不一致（收到 %r，按 %r 处理）",
            want,
            ctx.sheet_name,
        )
    return ctx.sheet_name or want


@router.put("/custom-cells")
async def update_custom_cells(
    wp_id: UUID,
    data: CustomCellsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """写入自定义底稿单元格（先落 xlsx，再刷投影）。"""
    ctx = await _require_custom_ctx(db, wp_id, require_writable=True)
    sheet_name = _resolve_sheet_name(ctx, data.sheet_name)
    if not sheet_name:
        raise HTTPException(status_code=422, detail="无法解析目标 sheet（底稿缺少编号）")

    updates = data.updates or {}
    if not updates:
        raise HTTPException(status_code=422, detail="updates 不能为空")
    if len(updates) > MAX_CELL_UPDATES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"单次最多写入 {MAX_CELL_UPDATES} 格，收到 {len(updates)} 格",
                "overflow": True,
                "max_cells": MAX_CELL_UPDATES,
            },
        )

    # 引用非法先行拒绝（在碰 xlsx 之前），并指明是哪个键
    normalized: dict[str, Any] = {}
    for raw_ref, value in updates.items():
        ref = normalize_cell_ref(str(raw_ref))
        if ref is None:
            raise HTTPException(
                status_code=422, detail=f"单元格引用非法: {raw_ref}"
            )
        normalized[ref] = value

    if not ctx.wp.file_path:
        raise HTTPException(status_code=404, detail="底稿文件路径为空，请重新生成底稿")

    try:
        written = write_cells_to_xlsx(ctx.wp.file_path, sheet_name, normalized)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"底稿文件不存在: {exc}") from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=422, detail=f"底稿文件缺少 sheet {sheet_name}: {exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — 写盘失败必须让请求失败，不能报成功
        logger.error("custom-cells 写 xlsx 失败 wp_id=%s: %s", wp_id, exc)
        raise HTTPException(status_code=500, detail=f"写入底稿文件失败: {exc}") from exc

    grid = refresh_custom_projection(ctx.wp, sheet_name)
    ctx.wp.file_version = int(ctx.wp.file_version or 0) + 1
    ctx.wp.updated_by = current_user.id
    await db.commit()

    return {
        "updated": written,
        "sheet_name": sheet_name,
        "file_version": ctx.wp.file_version,
        "grid": grid,
    }


@router.post("/custom-refresh-projection")
async def refresh_custom_projection_endpoint(
    wp_id: UUID,
    data: CustomProjectionRefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 xlsx 重新投影（不改 xlsx）。

    用途：OnlyOffice 侧编辑保存后切回 HTML 模式时调它 —— 这是「OO 改动能被 HTML 侧
    看见」的唯一通路（平台既有双模式两侧数据不共享，自定义底稿靠 xlsx 权威打通）。

    🔴 `require_writable=False`：重投影不改 xlsx，归档底稿也应能刷新出正确内容。
    """
    ctx = await _require_custom_ctx(db, wp_id, require_writable=False)
    sheet_name = _resolve_sheet_name(ctx, data.sheet_name if data else None)
    if not sheet_name:
        raise HTTPException(status_code=422, detail="无法解析目标 sheet（底稿缺少编号）")

    grid = refresh_custom_projection(ctx.wp, sheet_name)
    await db.commit()
    return {"sheet_name": sheet_name, "grid": grid}
