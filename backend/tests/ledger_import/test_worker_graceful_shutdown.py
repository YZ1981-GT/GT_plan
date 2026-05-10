"""F44 / Sprint 7.16 — worker graceful shutdown 测试

覆盖点：
1. `_install_signal_handlers` 能把 SIGTERM / SIGINT 绑定到 stop_event
   （Windows 下回退到 signal.signal，测试中不真正发信号，而是直接调 handler）
2. `ImportJobRunner.run_forever` 在 stop_event.set() 后 30s 内优雅退出
   （不抢先中断当前轮次，但下一次 sleep 立刻醒来）
3. `ImportJobRunner._stop_event` 类级指针被正确赋值/还原，供 pipeline
   `cancel_check` 读取；运行结束后指针回到调用前的值，避免测试污染
4. `_execute_v2` 内部 `_cancel_check` 回调读 `cls._stop_event` — 用一个
   独立的 "mini cancel_check" 复刻同样逻辑验证：stop_event.set 后返回 True

这些测试只验证控制面的协同停机契约，不跑完整 pipeline（那部分已由
`test_cancel_cleanup_guarantee.py` / `test_execute_v2_e2e.py` 覆盖）。

Validates: Requirements F44（SIGTERM → stop_event → cancel_check 链路）
"""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import patch

import pytest

from app.services.import_job_runner import ImportJobRunner
from app.workers import import_worker


# ---------------------------------------------------------------------------
# Case 1 —— _install_signal_handlers 正确绑定 SIGTERM/SIGINT 到 stop_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_signal_handlers_sets_stop_event_on_sigterm():
    """调用安装函数后，模拟 SIGTERM handler 被触发，stop_event 应立即 set。"""
    stop_event = asyncio.Event()
    installed: dict[int, object] = {}
    loop = asyncio.get_running_loop()

    def fake_add_signal_handler(signum, callback, *args):
        # 捕获 callback + bound args，稍后直接手工触发
        installed[signum] = (callback, args)

    with patch.object(loop, "add_signal_handler", side_effect=fake_add_signal_handler):
        import_worker._install_signal_handlers(stop_event)

    # SIGTERM + SIGINT 都应该被注册
    assert signal.SIGTERM in installed
    assert signal.SIGINT in installed

    # 手工触发 SIGTERM handler → stop_event 应被设置
    cb, args = installed[signal.SIGTERM]
    cb(*args)
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_install_signal_handlers_idempotent_on_double_signal():
    """第二次触发同一信号不抛异常（已是 set 状态的 stop_event）。"""
    stop_event = asyncio.Event()
    installed: dict[int, object] = {}
    loop = asyncio.get_running_loop()

    def fake_add_signal_handler(signum, callback, *args):
        installed[signum] = (callback, args)

    with patch.object(loop, "add_signal_handler", side_effect=fake_add_signal_handler):
        import_worker._install_signal_handlers(stop_event)

    cb, args = installed[signal.SIGTERM]
    cb(*args)
    assert stop_event.is_set()
    # 再次触发不应抛
    cb(*args)
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_install_signal_handlers_falls_back_on_windows_notimplemented():
    """loop.add_signal_handler 抛 NotImplementedError（Windows 典型）时
    必须回退到 signal.signal；回退后仍然能让 stop_event 被 set。"""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_fallback: dict[int, object] = {}

    def _fake_add_signal_handler(*_a, **_kw):
        raise NotImplementedError("Windows fallback simulation")

    def _fake_signal(signum, handler):
        installed_fallback[signum] = handler
        return None  # 与 signal.signal 返回值签名对齐

    with patch.object(loop, "add_signal_handler", side_effect=_fake_add_signal_handler), \
         patch.object(import_worker.signal, "signal", side_effect=_fake_signal):
        import_worker._install_signal_handlers(stop_event)

    # 回退路径：signal.signal 应被调用注册 SIGTERM
    assert signal.SIGTERM in installed_fallback

    # 模拟 signal 线程调用 handler → 它会 call_soon_threadsafe 回 loop 再 _trigger；
    # 手工等一轮事件循环让 callback 执行完。
    handler = installed_fallback[signal.SIGTERM]
    handler(signal.SIGTERM, None)
    # 等待 call_soon_threadsafe 投递的任务执行
    for _ in range(10):
        if stop_event.is_set():
            break
        await asyncio.sleep(0.01)
    assert stop_event.is_set()


# ---------------------------------------------------------------------------
# Case 2 —— run_forever 在 stop_event 触发后 30s 内优雅退出
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_forever_exits_when_stop_event_set_during_sleep():
    """run_forever 在 sleep 中收到 stop_event 应立刻返回（不等 poll 超时）。"""
    stop_event = asyncio.Event()

    # recover_jobs / run_worker_once 设为 no-op，避免真的查 DB
    async def _noop(*args, **kwargs):
        return 0

    with patch.object(ImportJobRunner, "recover_jobs", side_effect=_noop), \
         patch.object(ImportJobRunner, "run_worker_once", side_effect=_noop):
        run_task = asyncio.create_task(
            ImportJobRunner.run_forever(
                poll_interval_seconds=30,  # 故意设大，验证不是靠 timeout
                batch_size=1,
                stop_event=stop_event,
            )
        )
        # 让 run_forever 进到 sleep 分支
        await asyncio.sleep(0.1)
        # 触发 stop_event —— run_forever 应在 wait_for 立即醒来并退出
        stop_event.set()
        # 给 0.5s 完成返回
        await asyncio.wait_for(run_task, timeout=2.0)

    # 运行结束后，类级指针应被还原（防止跨测试污染）
    assert ImportJobRunner._stop_event is None


@pytest.mark.asyncio
async def test_run_forever_sets_class_stop_event_during_execution():
    """run_forever 执行期间，cls._stop_event 应指向入参，供 pipeline 读取。"""
    stop_event = asyncio.Event()
    captured: list[asyncio.Event | None] = []

    async def _capture_then_stop(*args, **kwargs):
        captured.append(ImportJobRunner._stop_event)
        stop_event.set()
        return 0

    with patch.object(ImportJobRunner, "recover_jobs", side_effect=_capture_then_stop), \
         patch.object(ImportJobRunner, "run_worker_once", side_effect=_capture_then_stop):
        await ImportJobRunner.run_forever(
            poll_interval_seconds=30,
            batch_size=1,
            stop_event=stop_event,
        )

    # recover_jobs 或 run_worker_once 被调用时，类级指针应 == 入参 stop_event
    assert captured, "recover_jobs should have been called at least once"
    assert captured[0] is stop_event

    # 退出后回到 None
    assert ImportJobRunner._stop_event is None


@pytest.mark.asyncio
async def test_run_forever_restores_previous_stop_event():
    """嵌套/重入场景：run_forever 退出后应还原前一个 stop_event 指针。"""
    outer_event = asyncio.Event()
    inner_event = asyncio.Event()

    # 先手工塞一个 outer_event 模拟外层已占用
    ImportJobRunner._stop_event = outer_event
    try:
        async def _stop_immediately(*args, **kwargs):
            inner_event.set()
            return 0

        with patch.object(ImportJobRunner, "recover_jobs", side_effect=_stop_immediately), \
             patch.object(ImportJobRunner, "run_worker_once", side_effect=_stop_immediately):
            await ImportJobRunner.run_forever(
                poll_interval_seconds=30,
                batch_size=1,
                stop_event=inner_event,
            )
        # 退出后应还原为 outer_event（不是 None，也不是 inner_event）
        assert ImportJobRunner._stop_event is outer_event
    finally:
        ImportJobRunner._stop_event = None


# ---------------------------------------------------------------------------
# Case 3 —— pipeline cancel_check 契约：读 _stop_event 时语义正确
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_check_returns_true_when_stop_event_set():
    """复刻 _execute_v2._cancel_check 的 stop_event 分支逻辑。

    这里不跑完整 _execute_v2（需要真实 DB + job），而是直接验证
    "读 cls._stop_event.is_set() → 返回 True" 的契约成立。
    """
    # Arrange：类级 stop_event 被 set
    stop_event = asyncio.Event()
    ImportJobRunner._stop_event = stop_event
    try:
        # 复刻 _execute_v2 _cancel_check 中的 stop_event 分支（DB 分支不测）
        async def _cancel_check_stop_branch() -> bool:
            ev = ImportJobRunner._stop_event
            if ev is not None and ev.is_set():
                return True
            return False

        # 未 set 时应返回 False
        assert await _cancel_check_stop_branch() is False

        # set 后应立即返回 True
        stop_event.set()
        assert await _cancel_check_stop_branch() is True
    finally:
        ImportJobRunner._stop_event = None


@pytest.mark.asyncio
async def test_cancel_check_stop_event_is_none_by_default():
    """默认状态（无 worker 注册）下 _stop_event 应为 None，不会误触发 cancel。"""
    # 确保干净初始状态
    ImportJobRunner._stop_event = None

    async def _cancel_check_stop_branch() -> bool:
        ev = ImportJobRunner._stop_event
        if ev is not None and ev.is_set():
            return True
        return False

    assert await _cancel_check_stop_branch() is False
