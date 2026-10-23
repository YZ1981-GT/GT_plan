# -*- coding: utf-8 -*-
"""冷注册之前，在工作线程里先把「有已发布供给的 entry」的模板结构 hash 算好。

spec: writeback-followup-issue-closure · R4 / D6

各 provider 的 attach 在事件循环上调 ``assert_contract_file_matches_source()``，它要模板的
normalized structure hash（整册 openpyxl 解析，每份 0.2~3.3 s）。一次冷注册要算 36 份不同模板
⇒ 实测事件循环被连续占住 15~19 s（期间到达的 OnlyOffice 回调、轮询全部排队）。这里在
attach 之前、在工作线程里按同一组 provider 先算一遍，结果进 ``structure_hash_memo``
（内容寻址）⇒ 随后事件循环上的调用只剩一次 sha256。

只是预热：任何失败都吞掉（原调用点会以原错误 fail closed），漏算的模板照旧在原调用点现算 ——
判据与结果都不依赖这里有没有跑。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Iterable

import sqlalchemy as sa

logger = logging.getLogger(__name__)

__all__ = [
    "PILOT_PROVIDER_MODULES",
    "provider_modules_for",
    "supplied_entry_ids",
    "warm_template_structure_hashes",
]

#: 四条显式 pilot attach（`wp_sync_router._isolated_pilot_attach` 逐条调用的同一组模块）。
PILOT_PROVIDER_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync.pilot_simple_checklist",
    "app.services.workpaper_sync.pilot_d2_large_json",
    "app.services.workpaper_sync.pilot_h1_grouped_dynamic",
    "app.services.workpaper_sync.pilot_g7_two_level_dynamic",
)


async def supplied_entry_ids(session: Any) -> frozenset[str]:
    """有 entry_state 行（已发布供给）的 entry —— ``register_from_manifest`` 只给这些建 adapter。"""
    from app.models.workpaper_sync_models import WorkpaperSyncEntryState

    try:
        rows = (
            await session.execute(sa.select(sa.distinct(WorkpaperSyncEntryState.entry_id)))
        ).scalars().all()
    except Exception:  # noqa: BLE001 - 预热的输入；取不到就只暖 pilot
        logger.debug("[预热] 读不到已发布 entry 清单，只预热 pilot 模板", exc_info=True)
        return frozenset()
    return frozenset(str(entry_id) for entry_id in rows)


def provider_modules_for(registry: Any, entry_ids: Iterable[str]) -> tuple[str, ...]:
    """这些 entry 的 provider 模块（取自 registry 已绑定的注册计划）+ 四条 pilot。"""
    wanted = frozenset(entry_ids)
    modules: list[str] = list(PILOT_PROVIDER_MODULES)
    try:
        plan = registry.registration_plan
    except Exception:  # noqa: BLE001 - 测试 registry 没有绑定计划
        plan = ()
    for item in plan:
        if item.entry_id in wanted and item.blocked_reason is None and item.provider_module:
            modules.append(str(item.provider_module))
    return tuple(dict.fromkeys(modules))


def warm_template_structure_hashes(module_paths: Iterable[str]) -> int:
    """在**调用线程**里逐个调 provider 的 ``template_definition_payload()``；返回成功个数。

    供 ``asyncio.to_thread`` 调用。``template_definition_payload`` 是纯函数（读模板字节、
    算结构 hash、拼 payload），不碰会话。
    """
    warmed = 0
    for path in module_paths:
        try:
            module = importlib.import_module(path)
            # attach 在 capability 未放开时直接返回、不算模板 hash：预热跟着跳过，不白算
            enabled = getattr(module, "manifest_capability_enabled", None)
            if callable(enabled) and not enabled():
                continue
            payload_fn = getattr(module, "template_definition_payload", None)
            if callable(payload_fn):
                payload_fn()
                warmed += 1
        except Exception:  # noqa: BLE001 - 预热；失败由原调用点以原错误 fail closed
            logger.debug("[预热] %s 的模板结构 hash 预算失败（交原调用点现算）", path, exc_info=True)
    return warmed
