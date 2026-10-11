# -*- coding: utf-8 -*-
"""请求期把 adapter 绑到**目标底稿自己**的 current representation（R14）。

spec: d2-online-edit-platform-closure · R14

═══ 为什么必须存在（2026-10-10 真库实测）═══════════════════════════════════════

adapter 不是 entry 级常量。Excel adapter 由某个 representation 冻结的身份造出：
``FrozenEntryDefinitions.identity_inventory``（行身份清册）、
``ExcelIdentityBinding.tombstoned_row_keys`` / ``dynamic_column_columns``。而 registry
**按 entry** 注册、进程级缓存 —— provider attach 用
``resolve_visible_current_representation_id`` 按 ``wp.created_at, wp.id`` 取**第一家**
可见底稿的 representation，于是同一 entry 上只有第一家企业能用双向回写：

* 重药安徽（D2，首版 gen 1 已发布）点「在线编辑」⇒ store-projection 422
  ``excel_extract_identity_not_retained``「OO 往返后丢失 729 个 row identity，首个
  'dr-mtl5bqmm-0o950ft'」—— 那是**和平药房**的行；
* 受影响的是全部同步端点（store-projection / adopt / materialize / resolve / retry /
  rollback / callback apply 都用 ``registration.adapter``）与全部 provider。

═══ 修法 ═══════════════════════════════════════════════════════════════════════

entry 级注册照旧（它负责「这个 entry 有没有资格双向」与 matcher 唯一性），请求期再按
``(entry_id, 目标底稿 current representation id)`` 取一份**绑定注册**：

1. 读目标底稿 ``(wp_id, entry_id)`` 的 current pointer；没有（首版之前）⇒ 沿用 entry 级
   注册 —— 首版发布本就不走 registry（``ensure_first_publication`` 按 approved bundle
   现算 adapter），没有 representation 时也没有任何冻结清册可比；
2. 缓存未命中 ⇒ 在零注册的 fork 上跑该 entry **自己**的 provider，并用
   ``pin_representation_target`` 把共享解析器钉到目标底稿 —— 全部 provider 经这一个
   入口取 representation（BP-27），因此一处修复对全部 entry 生效；
3. 证伪「provider 绕过了解析器」：pin 记下的返回值必须等于第 1 步读到的 pointer；
4. ``registry.rebind_entry`` 把本请求 registry 里该 entry 的注册换成绑定注册（RG 判据
   全部重跑），最后照旧 ``assert_bidirectional_ready``。

缓存键是 representation id：representation 一经发布即不可变（frozen bundle + artifact），
同一 id 永远造出同一份冻结身份；新代际 = 新 id = 自然 miss。契约文件漂移照旧由
``register()`` 的 RG-11 在每次 rebind 时拦下（与 entry 级缓存的重放同一纪律）。
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Final

import sqlalchemy as sa

from app.services.workpaper_sync.adapters.registry import (
    AdapterNotRegisteredError,
    AdapterRegistration,
    RegistryError,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.parse_cache import BoundedLruCache
from app.services.workpaper_sync.projection_target_resolution import (
    pin_representation_target,
    same_uuid,
)

__all__ = [
    "TARGET_REGISTRATION_CACHE",
    "TargetRepresentationBindingError",
    "bind_registration_to_target",
    "clear_target_registration_cache",
    "target_representation_id",
]


class TargetRepresentationBindingError(RegistryError):
    """目标底稿有 current representation，却造不出绑在它上面的 adapter。

    🔴 不退回 entry 级注册：那份绑的是**另一家企业**的 representation，退回去就是 R14
    本身（拿别家的行身份清册比对本家的文件）。
    """

    error_code = "adapter_target_representation_unbound"


#: `(entry_id, representation_id)` → 绑定注册。值由 frozen definitions 构建、不持有会话，
#: 跨请求安全（与 `wp_sync_router._REGISTRATION_CACHE` 同一前提）。上限按「同时活跃的
#: (entry, 代际) 组合」估：每家企业每个在编 entry 一份，旧代际由 LRU 淘汰。
TARGET_REGISTRATION_CACHE: Final["BoundedLruCache[tuple[str, str], AdapterRegistration]"] = (
    BoundedLruCache(maxsize=256)
)

#: 冷构建按键串行：同一 (entry, 代际) 被并发首请求（store-projection / materialize /
#: timeline 同时打）各建一遍会各解析一次整册。不同键互不阻塞。
_BUILD_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}

_NOT_RESOLVED: Final = object()


def clear_target_registration_cache() -> None:
    """清空绑定注册缓存（测试隔离 / 运维用）。"""
    TARGET_REGISTRATION_CACHE.clear()
    _BUILD_LOCKS.clear()


async def target_representation_id(
    session: Any, *, wp_id: Any, entry_id: str
) -> Any | None:
    """目标底稿 `(wp_id, entry_id)` 的 current representation id；没有则 None。

    与 `first_publication_on_demand.current_publication` / `resolve_plan` 供给判据 B
    同表同条件（`working_paper_sync_entry_state` 主键行）。
    """
    from app.models.workpaper_sync_models import WorkpaperSyncEntryState

    return (
        await session.execute(
            sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                WorkpaperSyncEntryState.wp_id == wp_id,
                WorkpaperSyncEntryState.entry_id == str(entry_id),
            )
        )
    ).scalars().first()


async def bind_registration_to_target(
    *,
    session: Any,
    registry: WorkpaperSyncAdapterRegistry,
    entry_id: str,
    wp_id: Any,
) -> AdapterRegistration:
    """返回绑在目标底稿 current representation 上的注册，并换进本请求的 `registry`。

    Raises:
        TargetRepresentationBindingError: 目标底稿有 representation 却绑不上（原因写明）。
        RegistryError / SyncDomainError: provider 或注册判据自身的 fail-visible 失败，原样上抛。
    """
    entry_id = str(entry_id)
    representation_id = await target_representation_id(
        session, wp_id=wp_id, entry_id=entry_id
    )
    if representation_id is None:
        # 首版之前：没有任何冻结清册可比；首版发布本身不经 registry。
        return registry.assert_bidirectional_ready(entry_id)

    key = (entry_id, str(representation_id))
    bound = TARGET_REGISTRATION_CACHE.get(key)
    if bound is None:
        lock = _BUILD_LOCKS.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                bound = TARGET_REGISTRATION_CACHE.get(key)
                if bound is None:
                    bound = await _build_target_registration(
                        session=session,
                        registry=registry,
                        entry_id=entry_id,
                        wp_id=wp_id,
                        representation_id=representation_id,
                    )
                    TARGET_REGISTRATION_CACHE.put(key, bound)
        finally:
            # 已建好（或已失败）⇒ 后来者先查缓存；仍在等锁的协程手里持有同一把锁的引用。
            if not lock.locked():
                _BUILD_LOCKS.pop(key, None)
    registry.rebind_entry(bound)
    return registry.assert_bidirectional_ready(entry_id)


async def _build_target_registration(
    *,
    session: Any,
    registry: WorkpaperSyncAdapterRegistry,
    entry_id: str,
    wp_id: Any,
    representation_id: Any,
) -> AdapterRegistration:
    provider = registry.entry_provider(entry_id)
    scratch = registry.fork_unregistered()
    with pin_representation_target(wp_id) as pin:
        supplied = provider(scratch, session=session)
        if inspect.isawaitable(supplied):
            await supplied
    resolved = pin.resolved.get(entry_id, _NOT_RESOLVED)
    try:
        bound = scratch.resolve_for_entry(entry_id)
    except AdapterNotRegisteredError:
        bound = None

    if bound is None:
        # entry 级判据（capability 未裁决双向 / manifest 漂移）先说话：它们与 representation
        # 无关，比「绑不上」更根本。entry 级也只是「没注册」时，以目标绑定原因为准。
        try:
            registry.assert_bidirectional_ready(entry_id)
        except AdapterNotRegisteredError:
            pass
        raise TargetRepresentationBindingError(
            f"entry {entry_id}: 底稿 {wp_id} 的 current representation {representation_id} "
            f"上造不出 adapter —— {_unbound_reason(resolved)}"
        )
    if resolved is _NOT_RESOLVED:
        raise TargetRepresentationBindingError(
            f"entry {entry_id}: provider 注册了 adapter，却没有经共享解析器 "
            "`resolve_visible_current_representation_id` 取 representation —— 无法证明它绑在"
            f"底稿 {wp_id} 上（BP-27 / R14：provider 不得自取 representation）"
        )
    if not same_uuid(resolved, representation_id):
        raise TargetRepresentationBindingError(
            f"entry {entry_id}: 共享解析器为底稿 {wp_id} 返回 {resolved}，与刚读到的 current "
            f"pointer {representation_id} 不一致 —— 期间有并发发布，请重试"
        )
    return bound


def _unbound_reason(resolved: Any) -> str:
    if resolved is _NOT_RESOLVED:
        return "provider 在调用共享解析器之前就返回了空（provider 自身前置未过）"
    if resolved is None:
        return "该底稿在可见性过滤后不可见（底稿 / 所在项目 / 索引行已删除）"
    return (
        f"provider 在 representation {resolved} 上返回了空（如该 representation 未绑定 "
        "definition bundle）"
    )
