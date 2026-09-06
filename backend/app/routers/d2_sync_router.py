"""D2 明细表 HTML↔OnlyOffice 双向同步端点。

* `POST /api/workpapers/{wp_id}/d2-sync/push-to-excel`   结构化视图 → OnlyOffice
* `POST /api/workpapers/{wp_id}/d2-sync/pull-from-excel` OnlyOffice → 结构化视图
* `GET  /api/workpapers/{wp_id}/d2-sync/status`          两侧状态（供 UI 显示真实能力）

═══ 为什么单独一个 router ═══

`workpaper_sync` 的 17 个端点走 room/descriptor 全协议（需要 room 生命周期 +
forcesave ack 联动）。本 router 是**同一批引擎函数**的直连入口：把
`checklist_responses` 的 store 载荷与 OnlyOffice 实际打开的那份 xlsx 对接，
让「结构化视图 ↔ 在线编辑」立即可用，不阻塞在 room 协议的供给上。

🔴 不吞异常：任何失败都返回 4xx/5xx 带真实原因。fail-open 会把接线错误伪装成
「本项目无数据」，那是本 spec 复盘里最贵的一类坑。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Mapping
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.workpaper_sync import d2_bidirectional_bridge as bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers", tags=["working-papers", "d2-sync"])

#: 受管 sheet 对应的 OnlyOffice 文件 wp_code（`_resolve_wp_file` 的命名口径）。
_OO_WP_CODE = "D2-2"


async def _load_context(
    wp_id: UUID, db: AsyncSession
) -> tuple[UUID, str, Path]:
    """取 (project_id, wp_code, OO 文件路径)。文件不存在即 409 带可操作原因。"""
    row = (
        await db.execute(
            sa.select(WorkingPaper.project_id, WpIndex.wp_code)
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(WorkingPaper.id == wp_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"底稿 {wp_id} 不存在")
    project_id, wp_code = row

    from app.routers.wp_onlyoffice_router import _onlyoffice_storage_dir

    oo_dir = _onlyoffice_storage_dir(project_id)
    artifact = Path(oo_dir) / f"{_OO_WP_CODE}.xlsx"
    return project_id, str(wp_code or ""), artifact


#: OO 侧打开受管明细表用的 sheet 路径参数。
#:
#: 🔴 这是 **OO room 口径**的 sheet 名，不是工作簿里的 sheet 名。三者容易混：
#:   * 工作簿内真实 sheet 名 = `明细表D2-2`（`bridge.MANAGED_SHEET`，openpyxl 用）
#:   * sync manifest 的 entry_id = `xlsx/gt-d2-accounts-receivable`（契约用）
#:   * OO room 的 entry_id       = `xlsx-sheet/D2-2/D2-2`（doc_key 用）← 本常量
#: 实测依据：`GET /sheets/D2-2/onlyoffice-config` 返回
#: `key=wpsync-61bb6d65f4feaaeae1e3b0b6-g1`，与
#: `sheet_entry_id(wp_code='D2-2', sheet_name='D2-2')` 派生值逐字相等。
#: 用错任一个都会推进到没人读的键上，表现为「代码改了但 OO 还是旧内容」。
_OO_SHEET_PARAM = "D2-2"


async def _bump_oo_revision(wp_id: UUID, db: AsyncSession, *, reason: str) -> int:
    """推进受管 sheet 的 OO 内容修订号，使 doc_key 轮转、OO 放弃缓存副本。

    entry_id 走 `sheet_entry_id` 派生（唯一派生点），参数取实测值 —— 见
    `_OO_SHEET_PARAM` 的注释：wp_code 与 sheet_name **都**是 `D2-2`。
    """
    from app.services.onlyoffice_room_identity import (
        bump_oo_content_revision,
        sheet_entry_id,
    )

    entry = sheet_entry_id(
        wp_code=_OO_SHEET_PARAM,
        sheet_name=_OO_SHEET_PARAM,
        whole_workbook=False,
    )
    return await bump_oo_content_revision(
        db, wp_id=wp_id, entry_id=entry, reason=reason
    )


async def _read_narratives(wp_id: UUID, db: AsyncSession) -> dict[str, str]:
    """读审计说明 / 审计结论（`checklist_responses.remark`，逐 item_id 一行）。"""
    item_ids = [item for item, *_ in bridge.NARRATIVE_BLOCKS]
    rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, coalesce(remark, '') AS remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id = ANY(:items)"
            ),
            {"wp": str(wp_id), "items": item_ids},
        )
    ).all()
    found = {str(r[0]): str(r[1] or "") for r in rows}
    return {item: found.get(item, "") for item in item_ids}


async def _write_narratives(
    wp_id: UUID, project_id: UUID, values: Mapping[str, str], db: AsyncSession
) -> list[str]:
    """把从 Excel 读回的审计说明 / 结论落库。

    只写**内容真变了**的项：无谓 UPDATE 会刷新 `updated_at`，让复核看到假的
    「刚被改过」。返回实际更新的 item_id 列表，供报告如实呈现。
    """
    current = await _read_narratives(wp_id, db)
    changed: list[str] = []
    for item_id, text in values.items():
        new = str(text or "")
        if new == current.get(item_id, ""):
            continue
        updated = (
            await db.execute(
                sa.text(
                    "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                    "WHERE wp_id = :wp AND item_id = :item"
                ),
                {"val": new, "wp": str(wp_id), "item": item_id},
            )
        ).rowcount
        if not updated:
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                ),
                {
                    "pid": str(project_id),
                    "wp": str(wp_id),
                    "item": item_id,
                    "val": new,
                },
            )
        changed.append(item_id)
    return changed


async def _header_values(wp_id: UUID, project_id: UUID, db: AsyncSession) -> dict:
    """取系统权威表头值（单向下行到 Excel 的目录页）。

    🔴 用 `build_preparation_info` 而不是 `wp_header_data_service.get_header_data`：
    前者正是**前端「编制信息」面板真正调的那个**（`GET /preparation-info`，6 个可见
    字段 + index_no），字段名口径也一致（`entity_name` / `period_end` / `preparer` /
    `prep_date` / `reviewer` / `review_date`）。后者是另一套 camelCase 口径
    （`entityName` / `period` / …）给 HTML 表格渲染用 —— 两套混用会出现
    「填到 Excel 的值与 UI 显示的不是同一个」。

    该端点**只有 GET、没有写入**，7 字段全部从 `Project` / `working_paper` / 人员表
    派生 ⇒ 结构上就不存在「从 Excel 回写表头」的可能，故本函数只服务下行方向。
    """
    from app.services.wp_preparation_info_service import build_preparation_info

    return await build_preparation_info(db, project_id, wp_id)


async def _read_store_rows(wp_id: UUID, db: AsyncSession) -> list[dict]:
    """读结构化视图的明细行（`checklist_responses.remark` 的大 JSON）。"""
    raw = (
        await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id = :item"
            ),
            {"wp": str(wp_id), "item": bridge.STORE_ITEM_ID},
        )
    ).scalar_one_or_none()
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{bridge.STORE_ITEM_ID} 载荷不是合法 JSON：{exc}",
        ) from exc
    if not isinstance(rows, list):
        raise HTTPException(
            status_code=500,
            detail=f"{bridge.STORE_ITEM_ID} 载荷应为数组，实为 {type(rows).__name__}",
        )
    return rows


async def _write_store_rows(
    wp_id: UUID, project_id: UUID, rows: list[dict], db: AsyncSession
) -> None:
    """把合并后的明细行写回结构化视图（存在则更新，不存在则插入）。"""
    payload = json.dumps(rows, ensure_ascii=False)
    updated = (
        await db.execute(
            sa.text(
                "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                "WHERE wp_id = :wp AND item_id = :item"
            ),
            {"val": payload, "wp": str(wp_id), "item": bridge.STORE_ITEM_ID},
        )
    ).rowcount
    if not updated:
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses "
                "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
            ),
            {
                "pid": str(project_id),
                "wp": str(wp_id),
                "item": bridge.STORE_ITEM_ID,
                "val": payload,
            },
        )
    await db.commit()


@router.get("/{wp_id}/d2-sync/status")
async def d2_sync_status(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """两侧真实状态 —— 前端据此显示能力，**不再读硬编码常量**。

    返回 HTML 侧行数、Excel 侧业务行/身份行数、是否已建立身份载体。
    """
    _pid, _code, artifact = await _load_context(wp_id, db)
    rows = await _read_store_rows(wp_id, db)

    excel: dict = {"exists": artifact.is_file(), "path": str(artifact)}
    if artifact.is_file():
        try:
            excel.update(bridge.inspect_artifact(artifact))
        except Exception as exc:  # noqa: BLE001 — 观测端点：错误要可见不要静默
            logger.warning("D2 sync status 读 Excel 失败: %s", exc)
            excel["error"] = f"{type(exc).__name__}: {exc}"[:300]

    narratives = await _read_narratives(wp_id, db)
    return {
        "entry_id": "xlsx/gt-d2-accounts-receivable",
        "bidirectional": True,
        "managed_sheet": bridge.MANAGED_SHEET,
        "html": {
            "rows": len(rows),
            "narratives": {k: len(v) for k, v in narratives.items()},
        },
        "excel": excel,
        # 表头是单向下行（真源 Project / working_paper），在此如实标注，
        # 避免前端误以为可以从 Excel 改回编制人。
        "header_sync": "one_way_to_excel",
    }


@router.post("/{wp_id}/d2-sync/push-to-excel")
async def d2_push_to_excel(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """结构化视图 → OnlyOffice：把明细行写进 OO 打开的那份 xlsx。

    在**切到「在线编辑」之前**调用，保证编辑器里看到的就是刚才录入的数据。
    """
    project_id, _code, artifact = await _load_context(wp_id, db)
    rows = await _read_store_rows(wp_id, db)
    if not rows:
        raise HTTPException(
            status_code=409,
            detail=(
                "结构化视图没有明细行可推送 —— 请先在「结构化视图」录入或导入数据。"
            ),
        )
    if not artifact.is_file():
        raise HTTPException(
            status_code=409,
            detail=(
                f"OnlyOffice 文件尚未生成（{artifact.name}）—— "
                "请先点一次「在线编辑」让系统从模板创建它，再回来同步。"
            ),
        )
    narratives = await _read_narratives(wp_id, db)
    header = await _header_values(wp_id, project_id, db)
    try:
        report = bridge.push_html_to_excel(
            rows=rows, artifact=artifact, narratives=narratives, header=header
        )
    except bridge.D2BridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── 让 OnlyOffice 放弃缓存副本 ────────────────────────────────────
    # 🔴 2026-09-06 浏览器实测：不做这一步，磁盘文件已是 756 行，OO 里**仍显示空模板**。
    # doc_key 由 `(wp_id, entry_id, generation)` 派生且刻意与 mtime 解耦（Property 6），
    # 所以重写文件不会换 key ⇒ OO 按 key 命中服务端缓存、不重新下载。
    # 推进内容修订号 ⇒ 下次取 config 时 generation+1 ⇒ doc_key 轮转 ⇒ OO 重新拉取。
    revision = await _bump_oo_revision(wp_id, db, reason="d2_push_html_to_excel")
    await db.commit()
    return {"ok": True, "oo_content_revision": revision, **report.as_dict()}


@router.post("/{wp_id}/d2-sync/pull-from-excel")
async def d2_pull_from_excel(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """OnlyOffice → 结构化视图：读回 Excel 的受管值并落库。

    在**从「在线编辑」切回「结构化视图」时**调用，保证表格显示 Excel 里的最新编辑。
    """
    project_id, _code, artifact = await _load_context(wp_id, db)
    if not artifact.is_file():
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice 文件不存在：{artifact.name}"
        )
    base_rows = await _read_store_rows(wp_id, db)
    try:
        merged, report = bridge.pull_excel_to_html(
            artifact=artifact, base_rows=base_rows
        )
    except bridge.D2BridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _write_store_rows(wp_id, project_id, merged, db)

    # 叙述块（审计说明 / 审计结论）同样落库
    narratives = dict((report.detail or {}).get("narratives") or {})
    narratives_changed = await _write_narratives(wp_id, project_id, narratives, db)
    await db.commit()

    return {
        "ok": True,
        "rows_persisted": len(merged),
        "narratives_changed": narratives_changed,
        **report.as_dict(),
    }
