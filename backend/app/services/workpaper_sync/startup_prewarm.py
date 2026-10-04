# -*- coding: utf-8 -*-
"""workpaper-sync 的**启动预热**：把冷成本从用户的首次点击里挪到启动阶段。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / oo-html-writeback-performance

═══ 为什么单开一个模块 ═══

预热不是路由职责：它没有请求、没有用户、不映射状态码。`wp_sync_router` 的 docstring
明确它「只搬运参数 / 过 guard / 映射状态码」，而预热是启动编排。依赖方向是单向的
（本模块 → router），router 不回头 import 本模块，因此不成环。

═══ 两段预热，各自的实测依据 ═══

活体实测（重启后端后直接打 store-projection，真库 D4-营业收入）：

    改前          GET #1  32325 ms   #2 232 ms   #3 292 ms
    只暖注册      GET #1   8212 ms   #2 133 ms   #3 138 ms
    两段都暖      GET #1    131 ms   #2 194 ms   #3 122 ms

* **第一段（注册）** —— 4 条 pilot attach + ``register_from_manifest``（186 条 entry）
  实测 25~30s，此前完整发生在**首个** sync 请求内。用户点「在线编辑」看到的 32 秒
  主要就是它。
* **第二段（基线 projection）** —— 注册暖了之后仍有 8.2s，那是
  ``BASELINE_EXTRACT_CACHE``（键 = ``{contract_id}:{artifact sha256}``）的冷 miss：
  D4-营业收入 39 个 binding，整册反读 cProfile 实测 6.5s。

两段都走请求路径**同一条**代码（``_attach_pilot_adapters`` /
``compute_store_projection_response``），于是不会出现「预热建的缓存与请求需要的不是
一回事」——那种预热是纯浪费且无法察觉。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger(__name__)

__all__ = [
    "PREWARM_PROJECTION_MAX_ENTRIES",
    "PrewarmProjectionOutcome",
    "prewarm_sync_baseline_projections",
    "prewarm_sync_registration_cache",
]


@dataclass(frozen=True)
class PrewarmProjectionOutcome:
    """第二段预热的分项结果。

    🔴 ``not_eligible`` 与 ``failed`` **必须**是两个数，不能合并成一个 ``skipped``。
    二者都让 entry 没被暖到，但语义相反：

    * ``not_eligible`` —— 这条 entry 本就不该预热（capability 非 bidirectional、
      或不在 source-backed manifest）。这是设计内的正常分流，数字大是正常的。
    * ``failed`` —— 这条 entry 应该能暖，但 projection 算炸了。这是**真故障**。

    合并的后果（本次修复的起因）：生产 ``log_level=WARNING`` 下「暖 5 / 跳过 7」与
    「暖 4 / 跳过 8（其中 1 个是异常）」长相完全一样，而失败详情当时只记 ``info``
    ⇒ 预热失败静默，运维手上没有任何可察觉的信号。
    """

    warmed: int = 0
    not_eligible: int = 0
    failed: int = 0

#: 预热基线 projection 的 entry 上限。
#
# 真库当前只有 12 行 ``working_paper_sync_entry_state``，其中可切 OO（bidirectional）
# 的是 D2/D4/G7/H1 几条。设上限只为「库长大之后预热不会变成无界后台负载」，
# 不是业务约束。
PREWARM_PROJECTION_MAX_ENTRIES: int = 32


async def prewarm_sync_registration_cache() -> tuple[str, ...]:
    """第一段：把 ROI-0 注册缓存在**没有用户请求**的时候建好。

    失败不吞在这里（交给调用方 `app.main._warm_workpaper_sync_registry` 统一记
    WARNING）：预热只是把成本提前，失败就退回原来的惰性路径（首请求自己建）。
    """
    from app.core.database import async_session
    from app.routers.wp_sync_router import (  # noqa: PLC0415 - 单向依赖，避免导入期成环
        _RegistrationWarmupContext,
        _attach_pilot_adapters,
    )
    from app.services.workpaper_sync.adapters.registry import build_production_registry

    async with async_session() as session:
        context = _RegistrationWarmupContext(
            session=session, registry=build_production_registry()
        )
        return await _attach_pilot_adapters(context)


async def prewarm_sync_baseline_projections() -> PrewarmProjectionOutcome:
    """第二段：把**可切 OO 的 entry** 的基线 extract 结果算好。

    只预热 ``assert_bidirectional_ready`` 通过的 entry：那正是用户会点「在线编辑」的
    那批，其余 entry 预热了也没人会走 OO 往返。逐个**顺序**做（不并发）—— 这些解析是
    CPU 密集且持 GIL，并发只会和前台请求互抢。

    返回 :class:`PrewarmProjectionOutcome`（暖 / 不适用 / 失败 三个分项，理由见该类）。
    单个 entry 失败只跳过：一个坏底稿不得让整段预热（以及后面的 entry）全丢 —— 但
    「跳过」必须留下 WARNING，否则等于没发生。
    """
    from app.core.database import async_session
    from app.models.workpaper_models import WorkingPaper
    from app.models.workpaper_sync_models import WorkpaperSyncEntryState
    from app.routers.wp_sync_router import (  # noqa: PLC0415 - 同上
        _RegistrationWarmupContext,
        _attach_pilot_adapters,
    )
    from app.services.workpaper_sync.adapters.registry import build_production_registry
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.store_projection_response import (
        compute_store_projection_response,
    )

    warmed = 0
    not_eligible = 0
    failed = 0
    async with async_session() as session:
        registry = build_production_registry()
        await _attach_pilot_adapters(
            _RegistrationWarmupContext(session=session, registry=registry)
        )

        rows = (
            await session.execute(
                sa.select(
                    WorkpaperSyncEntryState.wp_id,
                    WorkpaperSyncEntryState.entry_id,
                    WorkingPaper.project_id,
                )
                .join(WorkingPaper, WorkingPaper.id == WorkpaperSyncEntryState.wp_id)
                .order_by(WorkpaperSyncEntryState.entry_id)
                .limit(PREWARM_PROJECTION_MAX_ENTRIES)
            )
        ).all()

        resolution = CanonicalResolutionService(
            session, CanonicalArtifactRepository(BACKEND_ROOT)
        )
        for wp_id, entry_id, project_id in rows:
            try:
                registration = registry.assert_bidirectional_ready(str(entry_id))
            except Exception as exc:  # noqa: BLE001 - 非 bidirectional / 未注册：本就不预热
                not_eligible += 1
                # info 足够：这是设计内的正常分流，不是故障。
                logger.info(
                    "[预热] entry %s 不适用基线 projection 预热（%s）：%s",
                    entry_id,
                    type(exc).__name__,
                    exc,
                )
                continue
            try:
                await compute_store_projection_response(
                    session=session,
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=str(entry_id),
                    registration=registration,
                    resolution=resolution,
                )
                warmed += 1
            except Exception as exc:  # noqa: BLE001 - 单 entry 失败只跳过
                failed += 1
                # 🔴 必须 WARNING 而不是 INFO：生产 log_level=WARNING，info 一律不输出。
                # 这条 entry 是 bidirectional-ready 的（用户会点「在线编辑」），它的基线
                # 算不出来意味着首请求要自己付整册反读的代价，甚至根本打不开 —— 属真故障。
                logger.warning(
                    "[预热] entry %s 基线 projection 预热失败（该 entry 可切 OO，首请求将付冷成本）：%s: %s",
                    entry_id,
                    type(exc).__name__,
                    exc,
                )
    return PrewarmProjectionOutcome(
        warmed=warmed, not_eligible=not_eligible, failed=failed
    )
