"""旧式 OnlyOffice URL 停止签发门（spec 任务 2.8 第 ① 步 + 2.6 binding 级状态机）。

从 `wp_onlyoffice_router.py` 抽出的伴生模块（行数门：宿主 1947 行 > 白名单基线
1820 +5%）。抽出而不是抬白名单，符合本仓「优先拆模块」的既有纪律。

## 这个门存在的原因

`/sheets/{sheet}/onlyoffice-config` 是**旧式**链路入口：它签发 `wopi/contents` +
`/onlyoffice-callback` 两个 URL，而那三个端点各自要**自己解析一次目标文件**
⇒ writer gate 的 `multi_resolver` 判据把它们全部点名。判据说的不是「这三个函数写得差」，
而是「优先级链没有单一来源」。只要这条路径还在生产上签发 URL，这条链就删不掉。

## 判据分两层（spec 2.6）

**第一层 = binding 状态机**（`sheet_open_bindings`，本 spec 的显式真源）：

| binding status | 旧式 URL | 理由 |
| --- | --- | --- |
| `migrated` / `retired` | **拒**（409） | 该入口已走 room 协议；再签旧 URL 就是双写 |
| `draining` | **拒**（409，文案指向已签发会话） | 不再为新请求造旧 doc key，已签发者按 TTL 结算 |
| `pending` | **放**，但标 `sync_mode=independent` | 映射未完成，必须保留独立在线编辑（R6.2） |
| `out_of_scope` | **放**，但标 `sync_mode=independent` | custom / Word / single_onlyoffice 不适用本迁移 |
| 无 binding | 放（走第二层） | 未纳入本 spec 的入口不能因本门失效 |

**第二层 = readiness**（`entry_readiness.evaluate_entry_readiness` 的 `runtime.ready`）：
binding 层没有结论时才用它，语义与 2.8 第 ① 步完全一致。

## 为什么 readiness 层缺结果时是 fail-open

只有 `runtime.ready=True` 才拒绝。`entry` 不在 manifest / readiness 抛异常 /
尚未注册 adapter 这几种情形**一律照旧签发**：

* 那批 entry 本来就进不了 room（没 representation 就没法 materialize），
  拒绝它们等于让用户彻底打不开底稿 —— 比 `multi_resolver` 严重得多；
* 本任务是「停止签发**能替代的**旧 URL」，不是「一刀切停掉在线编辑」
  （Requirement 12.8 禁做假切换 / 禁让入口失效）。

## 为什么 binding 层是 fail-**closed** 而 readiness 层是 fail-open

两者的「算不出来」含义不同：

* binding 算不出来（生成物缺失 / schema 不符）是**本 spec 自己的交付物坏了**，属部署缺陷，
  这时按「不知道状态」放行会让 migrated 入口继续双写 —— 那是本 spec 要消灭的事故本身。
  但也不能拒（会让全平台在线编辑一起挂），所以取**中间档**：放行 + `logger.error` +
  响应标 `binding_resolution_failed`，让监控能抓、让用户能继续工作。
* readiness 算不出来是**正常业务状态**（entry 没接 adapter），拒了就是功能缺失。

## 为什么用 409 而不是 404 / 503

409 在平台错误词表里表示「当前状态不允许这个动作，但状态变了就能做」
（`conflict_resolution` / descriptor 系错误同档）。这里正是这个语义：
该 entry 的 room 供给已经就绪 ⇒ 前端**改成**走 room 协议即可，不是能力缺失。
响应体带 `error_code` 与可操作文案，前端据此显示中文原因而不是空白。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
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

#: `draining` 的文案与 `migrated` 分开：前者是「已打开的会话还能存」，后者是「必须换入口」。
DRAINING_MESSAGE = (
    "该底稿已切换到统一在线编辑协议，旧的编辑会话已进入收尾期 —— "
    "请保存并关闭当前编辑器，之后改用协同编辑入口打开"
)

#: 响应里标「这条是独立在线编辑，不与 HTML 同步」的字段值（R4.2 / R6.2）。
SYNC_MODE_INDEPENDENT = "independent"
SYNC_MODE_BOUND = "bound"

#: binding 层已明确「这个入口该走 room」的状态。
_BINDING_STATES_REFUSING_LEGACY = frozenset({"migrated", "retired"})
#: binding 层明确「这个入口不适用本迁移，保留独立在线编辑」的状态。
_BINDING_STATES_KEEPING_INDEPENDENT = frozenset({"pending", "out_of_scope"})


def _binding_verdict(
    *, source_wp_code: str, sheet_name: str, whole_workbook: bool,
    project_id: UUID | None = None,
    source_wp_codes: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """binding 层结论。

    Returns:
        `(verdict, binding)`，verdict ∈
        `{"refuse_migrated", "refuse_draining", "keep_independent", "unresolved", "no_binding"}`。

        🔴 `unresolved` 与 `no_binding` 必须分开：前者是「生成物坏了」（部署缺陷，要报警），
        后者是「这个入口本来就不在本 spec 范围内」（正常）。
    """
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    try:
        resolution = SheetOpenBindingResolver().resolve(
            source_wp_code=source_wp_code,
            source_wp_codes=source_wp_codes,
            sheet_name=sheet_name,
            whole_workbook=whole_workbook,
            manifest=_manifest(),
            project_id=str(project_id) if project_id is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — 见 docstring：不拒，但要报警
        logger.error(
            "legacy OO URL gate: sheet binding 解析失败（生成物可能缺失/过期）"
            " wp_code=%s sheet=%r: %s",
            source_wp_code, sheet_name, exc,
        )
        return "unresolved", None

    status = str(resolution.status or "")
    if status in _BINDING_STATES_REFUSING_LEGACY:
        return "refuse_migrated", dict(resolution.binding or {})
    if status == "draining":
        return "refuse_draining", dict(resolution.binding or {})
    if status in _BINDING_STATES_KEEPING_INDEPENDENT:
        return "keep_independent", dict(resolution.binding or {})
    if status == "ready":
        # `ready` = 映射已审核但还没切；旧式仍可签发，第二层 readiness 继续把关。
        return "keep_independent", dict(resolution.binding or {})
    return "no_binding", dict(resolution.binding or {})


def _manifest() -> dict[str, Any]:
    from app.services.workpaper_sync.entry_profile import load_entry_manifest

    return load_entry_manifest()


async def evaluate_legacy_issue_verdict(
    db: AsyncSession,
    *,
    wp_id: UUID,
    project_id: UUID,
    entry_id: str,
    source_wp_code: str = "",
    source_wp_codes: Iterable[str] | None = None,
    sheet_name: str = "",
    whole_workbook: bool = False,
) -> dict[str, Any]:
    """旧式 URL 能否签发 + 该标什么同步模式（**只读**，不抛）。

    Returns:
        `{"allowed": bool, "sync_mode": str, "error_code": str|None, "message": str|None,
        "entry_id": str, "allowed_modes": list[str], "binding_status": str|None}`

    端点把它并进响应或据此抛 409 —— 判定逻辑本身不抛，便于单独测。
    """
    binding_verdict, binding = _binding_verdict(
        source_wp_code=source_wp_code,
        sheet_name=sheet_name,
        whole_workbook=whole_workbook,
        project_id=project_id,
        source_wp_codes=source_wp_codes,
    )
    binding_status = str(binding.get("status")) if binding and binding.get("status") else None

    if binding_verdict == "refuse_migrated":
        logger.warning(
            "legacy OO URL gate: 拒绝旧式签发（binding 已 migrated/retired）"
            " wp_id=%s entry=%s status=%s",
            wp_id, entry_id, binding_status,
        )
        return {
            "allowed": False,
            "sync_mode": SYNC_MODE_BOUND,
            "error_code": LEGACY_ONLYOFFICE_URL_RETIRED,
            "message": RETIRED_MESSAGE,
            "entry_id": str((binding or {}).get("effective_entry_id") or entry_id),
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": binding_status,
        }

    if binding_verdict == "refuse_draining":
        logger.warning(
            "legacy OO URL gate: 拒绝旧式签发（binding draining）wp_id=%s entry=%s",
            wp_id, entry_id,
        )
        return {
            "allowed": False,
            "sync_mode": SYNC_MODE_BOUND,
            "error_code": LEGACY_ONLYOFFICE_URL_RETIRED,
            "message": DRAINING_MESSAGE,
            "entry_id": str((binding or {}).get("effective_entry_id") or entry_id),
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": binding_status,
        }

    if binding_verdict == "keep_independent":
        # R6.2：pending / out_of_scope / ready 保留独立在线编辑，但**必须**标明不同步。
        return {
            "allowed": True,
            "sync_mode": SYNC_MODE_INDEPENDENT,
            "error_code": None,
            "message": None,
            "entry_id": entry_id,
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": binding_status,
        }

    # `no_binding` / `unresolved` ⇒ 第二层 readiness（与 2.8 第 ① 步同口径）。
    verdict = await _readiness_verdict(db, wp_id=wp_id, project_id=project_id, entry_id=entry_id)
    if binding_verdict == "unresolved":
        # 生成物坏了：放行但标出来（见 docstring 的「中间档」）。
        verdict["binding_status"] = "resolution_failed"
    return verdict


async def _readiness_verdict(
    db: AsyncSession, *, wp_id: UUID, project_id: UUID, entry_id: str
) -> dict[str, Any]:
    """第二层：`runtime.ready` 就绪 ⇒ 拒旧式；算不出来 ⇒ fail-open。"""
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
        return {
            "allowed": True,
            "sync_mode": SYNC_MODE_INDEPENDENT,
            "error_code": None,
            "message": None,
            "entry_id": entry_id,
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": None,
        }

    if not readiness.runtime.ready:
        return {
            "allowed": True,
            "sync_mode": SYNC_MODE_INDEPENDENT,
            "error_code": None,
            "message": None,
            "entry_id": entry_id,
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": None,
        }

    logger.warning(
        "legacy OO URL gate: 拒绝旧式签发（room 供给已就绪）wp_id=%s entry=%s",
        wp_id, entry_id,
    )
    return {
        "allowed": False,
        "sync_mode": SYNC_MODE_BOUND,
        "error_code": LEGACY_ONLYOFFICE_URL_RETIRED,
        "message": RETIRED_MESSAGE,
        # 🔴 effective entry：前端要拿它去调 materialize。用请求值会让前端去
        #    materialize 一个不存在的 entry，表现为「点了没反应」而不是可归因错误。
        "entry_id": readiness.effective_entry_id,
        "allowed_modes": list(readiness.allowed_modes),
        "binding_status": None,
    }


def _raise_for_verdict(verdict: dict[str, Any]) -> None:
    """`allowed=False` ⇒ 抛 409（响应体带 error_code / message / entry_id / allowed_modes）。"""
    if verdict.get("allowed"):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": verdict["error_code"],
            "message": verdict["message"],
            "entry_id": verdict["entry_id"],
            "allowed_modes": list(verdict.get("allowed_modes") or []),
        },
    )


async def refuse_legacy_url_when_room_ready(
    db: AsyncSession,
    *,
    wp_id: UUID,
    project_id: UUID,
    entry_id: str,
    source_wp_code: str = "",
    source_wp_codes: Iterable[str] | None = None,
    sheet_name: str = "",
    whole_workbook: bool = False,
) -> dict[str, Any]:
    """旧式签发前的唯一门。返回 verdict 供端点并进响应（`sync_mode`）。

    Raises:
        HTTPException: 409 + :data:`LEGACY_ONLYOFFICE_URL_RETIRED`，仅在判定为拒绝时。
    """
    verdict = await evaluate_legacy_issue_verdict(
        db,
        wp_id=wp_id,
        project_id=project_id,
        entry_id=entry_id,
        source_wp_code=source_wp_code,
        source_wp_codes=source_wp_codes,
        sheet_name=sheet_name,
        whole_workbook=whole_workbook,
    )
    _raise_for_verdict(verdict)
    return verdict


__all__ = [
    "DRAINING_MESSAGE",
    "LEGACY_ONLYOFFICE_URL_RETIRED",
    "RETIRED_MESSAGE",
    "SYNC_MODE_BOUND",
    "SYNC_MODE_INDEPENDENT",
    "evaluate_legacy_issue_verdict",
    "refuse_legacy_url_when_room_ready",
]
