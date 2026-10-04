"""OnlyOfficeCallbackService.health_check 非阻塞 + 健康判定守卫。

🔴 2026-09-22 性能修复守卫：此前 health_check 用同步阻塞的 `urllib.request.urlopen`
（标了 async def 却在方法体内真阻塞事件循环最多 timeout 秒）。调用方
`wp_onlyoffice_router.get_onlyoffice_health` 是 D4 每次切换底稿都会打的无鉴权探针，
一次阻塞会连累同进程内所有并发请求。已改用 `httpx.AsyncClient`（真异步）。

本文件锚定两类判据：
  ① 健康判定正确：status 200 → True；非 200 → False；异常 → False（fail-safe 不抛）。
  ② 不阻塞事件循环：health_check 等待 HTTP 响应期间，同一事件循环上的其他协程仍能推进
     （变异反证：若退回同步阻塞 urllib，并发协程在等待窗口内无法推进，②打红）。

测试结构照抄 tests/test_libreoffice_pool.py 的 startup_health_check 用例
（module-level asyncio.run(_run()) + unittest.mock patch/AsyncMock），不自创新写法。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService


def _make_service() -> OnlyOfficeCallbackService:
    """构造 service。health_check 不触及 db，传 MagicMock 即可。"""
    return OnlyOfficeCallbackService(db=MagicMock())


def _patch_async_client(get_side_effect):
    """把 httpx.AsyncClient patch 成 async context manager，其 .get 用给定副作用。

    get_side_effect: 可为返回 resp 的 async 函数，或抛异常的 async 函数。
    返回 (patcher, mock_client)：mock_client.get 供断言是否被 await。
    """
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=get_side_effect)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    patcher = patch(
        "app.services.onlyoffice_callback_service.httpx.AsyncClient",
        return_value=mock_cm,
    )
    return patcher, mock_client


class TestHealthCheckVerdict:
    """① 健康判定正确。"""

    def test_status_200_returns_true(self):
        async def _run():
            async def _get(url):
                resp = MagicMock()
                resp.status_code = 200
                return resp

            patcher, mock_client = _patch_async_client(_get)
            with patcher:
                svc = _make_service()
                ok = await svc.health_check()
            assert ok is True
            # 关键回归锚点：走的是 httpx.AsyncClient.get（真异步），被 await 了一次
            mock_client.get.assert_awaited_once()

        asyncio.run(_run())

    def test_status_non_200_returns_false(self):
        async def _run():
            async def _get(url):
                resp = MagicMock()
                resp.status_code = 503
                return resp

            patcher, _ = _patch_async_client(_get)
            with patcher:
                svc = _make_service()
                ok = await svc.health_check()
            assert ok is False

        asyncio.run(_run())

    def test_exception_returns_false_not_raise(self):
        """OO 不可达时 fail-safe 返 False，绝不把异常抛给调用方。"""

        async def _run():
            async def _get(url):
                raise ConnectionError("OO down")

            patcher, _ = _patch_async_client(_get)
            with patcher:
                svc = _make_service()
                ok = await svc.health_check()  # 不应抛
            assert ok is False

        asyncio.run(_run())


class TestHealthCheckNonBlocking:
    """② 不阻塞事件循环（治本判据）。"""

    def test_event_loop_progresses_while_health_check_awaits(self):
        """health_check 等待 HTTP 响应期间，同循环上的另一协程应能推进。

        变异反证：若 health_check 退回同步阻塞 urllib.request.urlopen，等待窗口内
        事件循环被独占，`progressed` 无法在 health_check 返回前被置位，断言打红。
        """

        async def _run():
            progressed = {"value": False}
            release = asyncio.Event()

            async def _slow_get(url):
                # 模拟一次真异步的网络等待：让出控制权，直到并发协程把标记置位
                await release.wait()
                resp = MagicMock()
                resp.status_code = 200
                return resp

            async def _competitor():
                # health_check 让出控制权后，本协程应能被调度、推进并放行 get
                progressed["value"] = True
                release.set()

            patcher, _ = _patch_async_client(_slow_get)
            with patcher:
                svc = _make_service()
                # 并发跑 health_check 与竞争协程；若事件循环被阻塞，_competitor
                # 永远拿不到执行权，release 不会 set，health_check 会挂死（gather 超时）
                results = await asyncio.wait_for(
                    asyncio.gather(svc.health_check(), _competitor()),
                    timeout=3.0,
                )
            assert results[0] is True
            assert progressed["value"] is True

        asyncio.run(_run())
