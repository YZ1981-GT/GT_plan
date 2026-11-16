"""旧式 OnlyOffice URL 停止签发门（spec 任务 2.8 第 ① 步）。

从 `wp_onlyoffice_router.py` 抽出的伴生模块（行数门：宿主 1947 行 > 白名单基线
1820 +5%）。抽出而不是抬白名单，符合本仓「优先拆模块」的既有纪律。

## 这个门存在的原因

`/sheets/{sheet}/onlyoffice-config` 是**旧式**链路入口：它签发 `wopi/contents` +
`/onlyoffice-callback` 两个 URL，而那三个端点各自要**自己解析一次目标文件**
⇒ writer gate 的 `multi_resolver` 判据把它们全部点名。判据说的不是「这三个函数写得差」，
而是「优先级链没有单一来源」。只要这条路径还在生产上签发 URL，这条链就删不掉。

## 判据为什么是 `readiness.runtime.ready`

「这个 entry 能不能走 room 协议」这件事在仓库里**已经有唯一答案**：
`entry_readiness.evaluate_entry_readiness` 的 `runtime.ready`。它是
`GET /sync/entries/{entry_id}/readiness` 的同一份计算（3.1/3.5 建立的单一来源），
前端「在线编辑不可用」的红色提示也读它。这里**不另造**一套资格判定 ——
两处各写一份判据时，新增一条资格条件会让其中一处静默放行（本 spec 反复付过代价）。

## 为什么缺 readiness 时是 fail-open（照旧签发）

只有 `runtime.ready=True` 才拒绝。`entry` 不在 manifest / readiness 抛异常 /
尚未注册 adapter 这几种情形**一律照旧签发**：

* 那批 entry 本来就进不了 room（没 representation 就没法 materialize），
  拒绝它们等于让用户彻底打不开底稿 —— 比 `multi_resolver` 严重得多；
* 本任务是「停止签发**能替代的**旧 URL」，不是「一刀切停掉在线编辑」
  （Requirement 12.8 禁做假切换 / 禁让入口失效）。

## 为什么用 409 而不是 404 / 503

409 在平台错误词表里表示「当前状态不允许这个动作，但状态变了就能做」
（`conflict_resolution` / descriptor 系错误同档）。这里正是这个语义：
该 entry 的 room 供给已经就绪 ⇒ 前端**改成**走 room 协议即可，不是能力缺失。
响应体带 `error_code` 与可操作文案，前端据此显示中文原因而不是空白。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: 拒绝态的错误码。前端按它决定展示哪条引导（不得只看 409 状态码猜）。
LEGACY_ONLYOFFICE_URL_RETIRED = "legacy_onlyoffice_url_retired"

#: 可操作文案。**必须**告诉用户下一步做什么，否则界面只能显示一句笼统的「失败」。
RETIRED_MESSAGE = (
    "该底稿已支持统一在线编辑协议，请改用协同编辑入口打开"
    "（旧式编辑器地址已停止签发）"
)


async def refuse_legacy_url_when_room_ready(
    db: AsyncSession,
    *,
    wp_id: UUID,
    project_id: UUID,
    entry_id: str,
) -> None:
    """`settings.ONLYOFFICE_LEGACY_URL_ISSUE=False` 时，对已有 room 供给的 entry 拒绝旧式签发。

    Raises:
        HTTPException: 409 + :data:`LEGACY_ONLYOFFICE_URL_RETIRED`，仅在 room 供给确实就绪时。
    """
    from app.services.workpaper_sync.adapters.registry import build_production_registry
    from app.services.workpaper_sync.entry_readiness import evaluate_entry_readiness

    try:
        readiness = await evaluate_entry_readiness(
            session=db,
            # 与 `wp_sync_router.build_sync_services` 同一个装配入口 —— 不另建一份 registry。
            registry=build_production_registry(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
        )
    except Exception as exc:  # noqa: BLE001 — 判据算不出来时 fail-open 到旧路径
        logger.info(
            "legacy OO URL gate: readiness 不可用，照旧签发 wp_id=%s entry=%s: %s",
            wp_id, entry_id, exc,
        )
        return

    if not readiness.runtime.ready:
        return

    logger.warning(
        "legacy OO URL gate: 拒绝旧式签发（room 供给已就绪）wp_id=%s entry=%s",
        wp_id, entry_id,
    )
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": LEGACY_ONLYOFFICE_URL_RETIRED,
            "message": RETIRED_MESSAGE,
            # 🔴 effective entry：前端要拿它去调 materialize。用请求值会让前端去
            #    materialize 一个不存在的 entry，表现为「点了没反应」而不是可归因错误。
            "entry_id": readiness.effective_entry_id,
            "allowed_modes": list(readiness.allowed_modes),
        },
    )


__all__ = [
    "LEGACY_ONLYOFFICE_URL_RETIRED",
    "RETIRED_MESSAGE",
    "refuse_legacy_url_when_room_ready",
]
