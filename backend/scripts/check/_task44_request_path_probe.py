"""Task 44 门禁的「请求路径注册」探针 —— 单独一个模块，避免宿主继续膨胀。

═══ 为什么是请求路径而不是 registry 快照 ═══

`build_production_registry()` 自 Task 75 起**只绑定注册计划、不执行注册**，真实注册
在 `await registry.register_from_manifest(session=...)`。于是「读一眼 registry 的
`registrations()`」恒为空集 —— 拿它当「adapter 有没有注册上」的判据，会在供给完全
就绪时仍报 False。2026-09-06 实测两口径对同一事实给出相反结论：

* 无 session 的 registry 快照：``()``
* 真实请求路径：``('d2.receivable_detail', 'g7.soe_subsidiary_disclosure',
  'h1.disposal_check')``

本模块因此只做一件事：跑一次真实请求路径的 manifest 驱动注册。
"""

from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["probe_request_path_registration"]


def probe_request_path_registration() -> tuple[tuple[str, ...] | None, str]:
    """跑一次真实请求路径的 manifest 驱动注册。

    :returns: ``(注册到的 adapter_id 元组, 说明)``；拿不到真库时第一项是 ``None``。

    🔴 **拿不到真库返回 ``None`` 而不是 ``()``**：「环境不可得」（=> ``unverifiable``）
    与「实现没做」（=> ``failed``）必须分型，混为一谈会把没有数据库的 CI 跑成假红。

    🔴 用**独立 ``NullPool`` 引擎**并在结束时 ``dispose()``：门禁里多处各自
    ``asyncio.run``，共享连接池会把上一次 event loop 里的连接留下，第二次取到它就报
    ``'NoneType' object has no attribute 'send'`` —— 那是**假 ERROR 态**，会被误读成
    「库不可达」（Task 61 gate/2 首跑踩过同一个坑）。
    """
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
        from app.services.workpaper_sync.adapters import registry as registry_mod
    except Exception as exc:  # noqa: BLE001
        return None, f"导入失败：{type(exc).__name__}: {exc}"[:200]

    async def _run() -> tuple[str, ...]:
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        session_factory: Any = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                reg = registry_mod.build_production_registry()
                outcome = await reg.register_from_manifest(session=session)
                return tuple(sorted(outcome.registered_adapter_ids))
        finally:
            await engine.dispose()

    try:
        return tuple(asyncio.run(_run())), "请求路径真跑（真库 session）"
    except Exception as exc:  # noqa: BLE001 - 环境不可得记 None，不记 ()
        return None, f"真库不可达或注册路径抛错：{type(exc).__name__}: {exc}"[:300]
