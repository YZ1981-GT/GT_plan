# -*- coding: utf-8 -*-
"""注册缓存冷时，只为本请求的 entry 准备注册，不进全局冷建锁。

spec: oo-return-to-form-dead-end-and-save-speed · R2

═══ 为什么 ═══

``wp_sync_router._attach_pilot_adapters`` 在 ROI-0 缓存未命中时持全局锁建整套注册（4 条 pilot +
全部有供给的 entry，实测 36~42 s）。后端重载 / 任一底稿首版发布（指纹变化）之后到达的第一批请求 ——
包括 OnlyOffice 保存回调后的 apply —— 都排在这把锁后面：和平药房 D2 一次保存实测回调 51 s、
总计约 76 s。

而请求自己只用一条 entry：随后 ``bind_registration_to_target`` 按目标底稿 current representation
现绑，在零注册的 fork 上只跑该 entry 自己的 provider（按 ``(entry, representation)`` 加锁，不同键
互不阻塞），绑定结果进 ``TARGET_REGISTRATION_CACHE``。所以冷缓存时跳过整套建，只在工作线程里预热
本 entry 要用的源码事实与模板结构 hash（全量建原本在锁内预热它们；provider 在事件循环上调用时
直接命中，不在循环上整册解析）。

═══ 何时不能跳过 ═══

目标底稿没有 current representation（首版之前）：``bind_registration_to_target`` 回落到 entry 级
注册（``assert_bidirectional_ready``），必须有整套注册 ⇒ 返回 False，调用方照旧走锁内冷建。

═══ 取舍 ═══

* 本 entry 不与其它 entry 做 RG-3 matcher 重叠校验：这些请求按 entry_id 解析 adapter，不按 matcher；
  全量注册（启动预热、指纹不变时的下一次请求）照旧全校验。
* 不写 ROI-0 缓存：部分注册写进去会让后来的请求以为整套都建好了。
"""
from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["prepare_entry_only"]


async def prepare_entry_only(*, session: Any, registry: Any, entry_id: str, wp_id: Any) -> bool:
    """为 ``(entry_id, wp_id)`` 做绑定前的准备；返回 False ⇒ 调用方需要整套注册。"""
    from app.services.workpaper_sync.registration_template_warmup import (
        entry_provider_module,
        warm_source_facts_once,
        warm_template_structure_hashes,
    )
    from app.services.workpaper_sync.target_bound_registration import (
        TARGET_REGISTRATION_CACHE,
        target_representation_id,
    )

    entry_id = str(entry_id)
    representation_id = await target_representation_id(session, wp_id=wp_id, entry_id=entry_id)
    if representation_id is None:
        return False
    if TARGET_REGISTRATION_CACHE.get((entry_id, str(representation_id))) is None:
        # 绑定要现跑本 entry 的 provider：先在工作线程把它在循环上要用的两类首算做掉。
        await asyncio.to_thread(warm_source_facts_once)
        module = entry_provider_module(registry, entry_id)
        if module is not None:
            await asyncio.to_thread(warm_template_structure_hashes, (module,))
    return True
