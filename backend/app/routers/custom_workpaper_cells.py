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
from pathlib import Path
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
from app.services.workpaper_sync.content_mutation import CUSTOM
from app.services.workpaper_sync.models import RevisionConflictError
from app.services.workpaper_sync.writer_migration import (
    build_content_mutation_service_writer,
    opaque_entry_id,
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
    ctx.wp.updated_by = current_user.id

    # ─── Task 19：迁入统一 business revision 域（Property 50 / 61）────────────
    #
    # 改造前这里是 `ctx.wp.file_version += 1` + `await db.commit()`：一个 **JSON
    # projection 端点自己推进了权威 xlsx 的版本计数器**，且绕过统一提交入口
    # （Requirement 2.2）。Property 50 的原文是「custom adapter 的 HTML/OO 修改都落
    # 同一权威 xlsx content artifact，标准 projection persist 不被调用；但必须使用
    # approved `custom_authoritative_ooxml` authoritative model 与非空 bundle」。
    #
    # 落地形态：
    #   * 权威内容 = 刚写完的 xlsx **本体字节**，原样提交为 `authoritative_payload`
    #     （不是 `grid`、也不是 `parsed_data` 投影 —— 那两个是投影，Requirement 2.11
    #     禁止 JSON projection writer 改写权威本体）；
    #   * bundle = `custom_authoritative_ooxml` authority model + 三个版本化 typed
    #     null marker（`OpaqueAuthorityProvisioner` 幂等发布/复用，绝不留空 hash）；
    #   * 唯一提交出口 = `ContentMutationService.commit(...)`；本端点自己**没有**
    #     `db.commit()`，也**不再**碰任何版本字段。
    writer = build_content_mutation_service_writer(db)
    entry_id = opaque_entry_id(wp_code=ctx.wp_code, wp_id=wp_id)
    expected_revision = await writer.current_revision(wp_id)
    try:
        authoritative_bytes = Path(ctx.wp.file_path).read_bytes()
    except OSError as exc:
        # 权威 xlsx 刚写成功却读不回来 ⇒ 不能报成功（半成功比失败更危险）。
        logger.error("custom-cells 读回权威 xlsx 失败 wp_id=%s: %s", wp_id, exc)
        raise HTTPException(
            status_code=500, detail=f"读回底稿文件失败，未能提交内容版本: {exc}"
        ) from exc

    try:
        receipt = await writer.commit_bytes(
            project_id=ctx.wp.project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            source=CUSTOM,
            payload=authoritative_bytes,
            document_type="xlsx",
            expected_revision=expected_revision,
            substrate_path=Path(ctx.wp.file_path),
            # Task 65：authority model 不再由本调用点传，改由 lane 登记单向决定
            # （`opaque_entry_gate.authority_model_for_lane("custom_cells")` =
            # `custom_authoritative_ooxml`）。原先 `commit_bytes` 的 `authority_model`
            # 有默认值，漏传即静默落成 custom —— 那条参数现在已经不存在。
            lane_id="custom_cells",
            actor_id=current_user.id,
        )
    except RevisionConflictError as exc:
        # 真并发：CAS 命中 0 行。窄捕获 —— 宽泛 except 会把「artifact 发布失败」
        # 「事务分裂」一起吞成 409，用户看到的原因就是错的（Requirement 5.12）。
        raise HTTPException(
            status_code=409,
            detail={
                "error": "content_revision_conflict",
                "message": "其他用户在本次写入期间修改了该底稿，请刷新后重试。",
                "server_version": expected_revision,
            },
        ) from exc

    await writer.publish_committed_events(receipt)

    return {
        "updated": written,
        "sheet_name": sheet_name,
        # 对外契约保留 `file_version` 键（前端已在用），但它现在装的是**唯一** business
        # content revision。沿用键名是刻意的：换键名要同步改前端，属 Task 65 的活。
        "file_version": receipt.revision,
        "content_revision": receipt.revision,
        "content_version_id": str(receipt.content_version_id),
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
