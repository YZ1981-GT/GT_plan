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

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Mapping
from uuid import UUID

import httpx
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.workpaper_sync import d2_bidirectional_bridge as bridge

logger = logging.getLogger(__name__)

#: 发 `c=forcesave` 的 HTTP 超时（秒）。OO 契约实测恒立即返回 200，给足余量即可。
_FORCESAVE_HTTP_TIMEOUT_S = 10.0

#: 等「磁盘文件真的变了」的上限（秒）。
#: OO 收到 forcesave 后要「导出 → callback → 后端下载 → 覆盖写盘」四步，
#: 2026-09-06 实测 1260 行 / 315KB 的往返约 1~3 秒，12 秒留足慢盘余量。
#: 🔴 超时**不**降级成成功：如实返回 `durable=False`，由调用方拒绝 pull。
_FORCESAVE_DURABLE_TIMEOUT_S = 12.0

#: 轮询磁盘的间隔（秒）。
_FORCESAVE_POLL_INTERVAL_S = 0.3

# ── forcesave 出站结果的三态 ──────────────────────────────────────────
#
# 刻意用三态而不是布尔：「命令已接受」与「已经不需要保存」在**能不能回写**上
# 结论相反，压成一个 bool 必然有一方被误判（2026-09-06 复测实证）。
#: OO 接受了命令，还会有 callback 落盘 ⇒ 需要等磁盘变化。
_FORCESAVE_ACCEPTED = "accepted"
#: OO 明确回报无未保存改动 ⇒ 磁盘已是最新，**无需等待**即可回写。
_FORCESAVE_NOTHING_TO_SAVE = "nothing_to_save"
#: 命令未送达或被拒 ⇒ 不得回写。
_FORCESAVE_REJECTED = "rejected"

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


def _artifact_fingerprint(artifact: Path) -> dict:
    """canonical 文件的陈旧判据基线：mtime_ns + size + 内容 sha256。

    🔴 三者都要：mtime 在同秒内重写可能不变、size 在等长改动下也不变，
    只有 sha256 能证明「内容真的换了」。反过来单用 sha256 又拿不到「谁更新」的
    时间序，故三者同时冻结。
    """
    st = artifact.stat()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "sha256": digest}


@router.post("/{wp_id}/d2-sync/forcesave")
async def d2_forcesave(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """命令 OnlyOffice 把当前编辑**落盘**，并等到磁盘文件真的变化才返回。

    ═══ 为什么必须有这个端点 ═══

    `pull_excel_to_html` 读的是磁盘 canonical 文件，而 OO 的编辑在编辑器销毁后才由
    容器异步保存。2026-09-06 浏览器实测的时序（真库 + OO 9.4）：

    ```
    19:51:19  用户切回结构化视图 → pull 读到 19:41:12 的旧文件（AL13=0）
              并把 0 写回 store，覆盖 HTML 侧刚录的 13571.99
              接口却返回 {"ok":true,"rows_persisted":1260}
    19:51:31  OO 才真正落盘（AL13=88888.77）—— 此时已无人再 pull
    ```

    ⇒ 两侧永久分叉，且伴随一条「已从在线编辑回写 1260 行」的成功文案。

    ═══ 返回语义（刻意区分三态，不合并成「成功」）═══

    * `durable=True`  文件已耐久（sha256 变了或本来就没有在编辑）——**只有这个**允许 pull
    * `durable=False` + `accepted=True`  命令已被 OO 接受但超时内未落盘 ⇒ 调用方**必须**拒绝 pull
    * 4xx/5xx  命令根本没送达

    🔴 不 fail-open：拿不到耐久确认就如实返回 `durable=False`，绝不返回成功让
    调用方去读旧文件。AC 11.3 明令「不得统一显示同步成功」。
    """
    project_id, _code, artifact = await _load_context(wp_id, db)
    if not artifact.is_file():
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice 文件不存在：{artifact.name}"
        )

    before = _artifact_fingerprint(artifact)

    from app.services.onlyoffice_room_identity import (
        resolve_room_doc_key,
        sheet_entry_id,
    )

    entry = sheet_entry_id(
        wp_code=_OO_SHEET_PARAM, sheet_name=_OO_SHEET_PARAM, whole_workbook=False
    )
    doc_key = await resolve_room_doc_key(db, wp_id=wp_id, entry_id=entry)

    outcome, detail = await _issue_forcesave(doc_key)
    accepted = outcome in (_FORCESAVE_ACCEPTED, _FORCESAVE_NOTHING_TO_SAVE)

    after = before
    if outcome == _FORCESAVE_NOTHING_TO_SAVE:
        # 无待保存内容 ⇒ 磁盘就是权威版本，不必等（等也永远等不到变化）。
        durable = True
    elif outcome == _FORCESAVE_ACCEPTED:
        # 等磁盘真的变化 —— 这才是「已耐久」，Command Service 的 HTTP 200 不算。
        durable = False
        deadline = time.monotonic() + _FORCESAVE_DURABLE_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(_FORCESAVE_POLL_INTERVAL_S)
            if not artifact.is_file():
                continue
            after = _artifact_fingerprint(artifact)
            if after["sha256"] != before["sha256"]:
                durable = True
                break
    else:
        durable = False

    return {
        "ok": True,
        "outcome": outcome,
        "accepted": accepted,
        "durable": durable,
        "doc_key": doc_key,
        "detail": detail,
        "artifact": {"before": before, "after": after},
        "project_id": str(project_id),
    }


def _assert_not_stale(artifact: Path, fingerprint: Mapping) -> None:
    """磁盘文件必须是「forcesave 确认落盘后的那一份」，否则 409。

    `fingerprint` 是 `/d2-sync/forcesave` 回执里的 `artifact`，形如
    ``{"before": {...}, "after": {...}}``。判据：

    * 若 forcesave 期间 **没**观察到变化（before.sha256 == after.sha256），
      而磁盘现在仍是那个 sha256 ⇒ OO 的编辑从未落盘，读它必然拿到旧值 ⇒ 拒绝。
    * 若磁盘当前 sha256 既不等于 `after` 也不等于 `before` ⇒ 文件被第三方并发换掉，
      本次 pull 的前置确认已失效 ⇒ 拒绝，让调用方重新走 forcesave。

    只在 `fingerprint` 存在时生效；不带指纹的调用（如运维手动触发）不阻断，
    但那种调用本身就不该用于「切回视图」路径。
    """
    before = dict(fingerprint.get("before") or {})
    after = dict(fingerprint.get("after") or {})
    before_sha = str(before.get("sha256") or "")
    after_sha = str(after.get("sha256") or "")
    if not before_sha and not after_sha:
        return  # 指纹形状不认识：不假装校验过，直接放行由前端那道门负责

    current_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()

    if before_sha and after_sha and before_sha == after_sha:
        if current_sha == before_sha:
            raise HTTPException(
                status_code=409,
                detail=(
                    "在线编辑的内容尚未落盘 —— 磁盘上仍是切换前的那一份文件。"
                    "为避免用旧数据覆盖你在结构化视图的录入，本次回写已取消。"
                    "请回到在线编辑，等状态显示已保存后再切换。"
                ),
            )
        return  # 磁盘已变新（forcesave 之后又落了一次），可读

    if after_sha and current_sha != after_sha:
        raise HTTPException(
            status_code=409,
            detail=(
                "OnlyOffice 文件在确认落盘后又被改动（可能有其他人正在编辑）—— "
                "本次回写已取消，请重新切换以获取最新内容。"
            ),
        )


async def _issue_forcesave(doc_key: str) -> tuple[str, str]:
    """向 OO Command Service 发 `c=forcesave`。返回 (三态之一, 可读原因)。

    三态见 `_FORCESAVE_ACCEPTED` / `_FORCESAVE_NOTHING_TO_SAVE` / `_FORCESAVE_REJECTED`。

    ═══ 为什么不复用 `CommandServiceClient` ═══

    `workpaper_sync.command_service.CommandServiceClient.forcesave()` 的第一个参数
    类型是 `AcceptedRequest`——它只能由 room 协议的 Task 23 入口产出，用来在**类型层**
    强制「先落库再出站」。D2 直连通道没有 room / request 行，硬造一个 `AcceptedRequest`
    等于绕过那条不变量，比不用更糟。故这里直连 Command Service，且**不写任何 request 行**，
    保持「直连通道不伪造 room 证据」。room 协议供给就绪后本函数应整体让位给 Task 23/24。

    OO 契约实测：HTTP 恒 200，成败看 body 的 `error` 字段（0 = 已接受）。
    """
    base = str(getattr(settings, "ONLYOFFICE_URL", "") or "").strip().rstrip("/")
    if not base:
        return _FORCESAVE_REJECTED, "ONLYOFFICE_URL 未配置，无法发起强制保存"

    payload: dict = {"c": "forcesave", "key": doc_key}
    headers: dict[str, str] = {}
    secret = str(getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or "")
    if secret:
        from jose import jwt as jose_jwt

        token = jose_jwt.encode(dict(payload), secret, algorithm="HS256")
        payload["token"] = token
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=_FORCESAVE_HTTP_TIMEOUT_S) as client:
            resp = await client.post(
                f"{base}/coauthoring/CommandService.ashx",
                json=payload,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        return (
            _FORCESAVE_REJECTED,
            f"Command Service 不可达：{type(exc).__name__}: {exc}"[:300],
        )

    if resp.status_code != 200:
        return _FORCESAVE_REJECTED, f"Command Service 返回 HTTP {resp.status_code}"

    try:
        body = resp.json()
    except ValueError:
        return (
            _FORCESAVE_REJECTED,
            f"Command Service 响应不是 JSON：{resp.text[:160]!r}",
        )

    err = body.get("error")
    if err == 0:
        return _FORCESAVE_ACCEPTED, "强制保存命令已被 OnlyOffice 接受"
    # 🔴 error=4 = 「文档无未保存改动」。它**不是**失败，而是「磁盘已经是最新」的
    # 确凿证明 —— 没有任何待落盘内容，此时磁盘文件就是权威版本，可以直接回写。
    # 2026-09-06 复测踩到过：把它只算 accepted 而不算 durable，会让「打开 OO 看了
    # 一眼什么都没改就切回来」这种最常见的操作被误判成「尚未落盘」而拒绝回写。
    if err == 4:
        return _FORCESAVE_NOTHING_TO_SAVE, "文档无未保存改动，磁盘文件已是最新"
    return _FORCESAVE_REJECTED, f"OnlyOffice 拒绝强制保存：error={err}"


class _PullRequest(BaseModel):
    """pull 的可选载荷：forcesave 冻结的耐久指纹。

    前端把 `/d2-sync/forcesave` 回执里的 `artifact` 原样带回来，服务端据此判定
    「我现在读的这份文件，是不是就是刚刚确认落盘的那一份」。
    """

    durable_fingerprint: dict | None = None


@router.post("/{wp_id}/d2-sync/pull-from-excel")
async def d2_pull_from_excel(
    wp_id: UUID,
    payload: _PullRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """OnlyOffice → 结构化视图：读回 Excel 的受管值并落库。

    在**从「在线编辑」切回「结构化视图」时**调用，保证表格显示 Excel 里的最新编辑。

    ═══ 陈旧校验（第二道门）═══

    调用方应先调 `/d2-sync/forcesave` 拿到耐久确认，并把回执里的 `artifact`
    作为 `durable_fingerprint` 带回来。本端点据此拒绝两种危险情形：

    * `before.sha256 == 磁盘当前 sha256` 且 forcesave 当时**未**观察到变化
      ⇒ 说明读的还是切换前那一份，OO 的编辑没落盘 ⇒ **409 不写库**；
    * 磁盘 sha256 与 forcesave 观察到的 `after` 不一致且更旧 ⇒ 文件被并发换掉 ⇒ 409。

    🔴 为什么不能只靠前端那道门：前端可以被绕过（直接打 API），而一次错误的
    pull 会把陈旧值写满整张表、覆盖 HTML 侧的真实录入（2026-09-06 实测把
    刚录的 13571.99 覆盖成 0，同时返回成功文案）。写库前的校验必须在服务端。
    """
    project_id, _code, artifact = await _load_context(wp_id, db)
    if not artifact.is_file():
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice 文件不存在：{artifact.name}"
        )

    fingerprint = (payload.durable_fingerprint if payload else None) or None
    if fingerprint:
        _assert_not_stale(artifact, fingerprint)

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

    # 🔴 `rows_changed` 与 `rows_persisted` 是两件事，必须都给：
    #   rows_persisted = 落库的总行数（永远等于全表）
    #   rows_changed   = 本次**真的从 Excel 带回了新值**的行数
    # 只报前者就会出现「回写 1260 行」却一个字都没变的假成功
    #（2026-09-06 实测正是如此：读陈旧文件，每格都「回写」成旧值仍报全量成功）。
    return {
        "ok": True,
        "rows_persisted": len(merged),
        "rows_changed": report.rows,
        "narratives_changed": narratives_changed,
        **report.as_dict(),
    }
