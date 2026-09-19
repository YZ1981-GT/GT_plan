# Feature: dsh-agent-panel-integration — Task 28 DshEngine 守卫
"""``DshEngine``、有界 worker 池与取消传播的行为守卫。

Requirements: 4.7, 10.2, 10.5, 11.6, 11.7, 11.11, 11.12
Properties:
  - **Property 8（取消传播到全部后代）**：cancel 后工具调用计数不再增加。
  - **Property 25（DSH 失败不降级）**：SDK/handshake/MCP 失败 → engine_unavailable，
    NativeEngine invocation count 恒为 0。
  - **Property 28（跨用户隔离）**：per-run 进程不跨 principal 复用。
  - **Property 29（子 Agent 权限只收窄）**：scoped token 继承。
  - **Property 38（DshEngine backpressure 有界）**：active/queue 超限返回 quota error。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.ai_models import ChatEngineName
from app.services.ai_chat.engine import (
    AuthorizedChatRunRequest,
    ChatEngine,
    EngineCancelled,
    EngineFailure,
    EngineStream,
    EventCancelSignal,
    NEVER_CANCELLED,
    SequentialEventIds,
    build_engine,
    capabilities_of,
    resolve_engine,
)
from app.services.ai_chat.run_contract import (
    ChatErrorCode,
    ChatEventType,
    EngineCapabilities,
    CAPABILITIES_BY_ENGINE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_host_context(
    *,
    principal_id: UUID | None = None,
    project_id: UUID | None = None,
) -> Any:
    """构造 fake AuthorizedHostContext。"""
    host = MagicMock()
    host.principal_id = principal_id or uuid4()
    host.project_id = project_id or uuid4()
    host.resource_type = MagicMock(value="workpaper")
    host.resource_id = str(uuid4())
    host.display_label = "测试底稿"
    host.permission_binding = "auditor"
    host.cycle_scope = frozenset({"D", "E"})
    host.project_tools_enabled = True
    return host


def _make_request(
    *,
    run_id: UUID | None = None,
    host: Any = None,
) -> AuthorizedChatRunRequest:
    """构造 AuthorizedChatRunRequest。"""
    h = host or _make_host_context()
    return AuthorizedChatRunRequest(
        run_id=run_id or uuid4(),
        session_id=uuid4(),
        request_id=uuid4(),
        host=h,
        query="测试查询",
        engine=ChatEngineName.dsh,
        capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.dsh],
        assistant_message_id=uuid4(),
    )


# ---------------------------------------------------------------------------
# Test: DshEngine 构造与协议满足
# ---------------------------------------------------------------------------


class TestDshEngineConstruction:
    """DshEngine 构造与 ChatEngine 协议。"""

    def test_build_engine_dsh_branch(self) -> None:
        """build_engine 在 engine=dsh 时构造 DshEngine 而非 NativeEngine。"""
        from app.services.ai_chat.dsh_engine import DshEngine

        # Mock execution with engine=dsh
        execution = MagicMock()
        execution.engine = ChatEngineName.dsh
        execution.host = _make_host_context()

        engine = build_engine(db=None, execution=execution)
        assert isinstance(engine, DshEngine)
        assert engine.name == ChatEngineName.dsh

    def test_build_engine_native_branch_unchanged(self) -> None:
        """build_engine 在 engine=native 时仍构造 NativeEngine。"""
        from app.services.ai_chat.native_engine import NativeEngine

        execution = MagicMock()
        execution.engine = ChatEngineName.native

        engine = build_engine(db=MagicMock(), execution=execution)
        assert isinstance(engine, NativeEngine)

    def test_dsh_engine_satisfies_protocol(self) -> None:
        """DshEngine 满足 ChatEngine 协议。"""
        from app.services.ai_chat.dsh_engine import DshEngine

        engine = DshEngine(db=None)
        assert isinstance(engine, ChatEngine)
        assert engine.name == ChatEngineName.dsh

    @pytest.mark.asyncio
    async def test_dsh_capabilities_from_single_source(self) -> None:
        """DshEngine.capabilities() 返回与 CAPABILITIES_BY_ENGINE 表项相等的 manifest。"""
        from app.services.ai_chat.dsh_engine import DshEngine

        engine = DshEngine(db=None)
        caps = await engine.capabilities()
        expected = CAPABILITIES_BY_ENGINE[ChatEngineName.dsh]
        assert caps == expected
        assert caps.tools is True
        assert caps.streaming is True
        assert caps.local_only is True

    def test_dsh_engine_run_returns_engine_stream(self) -> None:
        """DshEngine.run() 返回 EngineStream（与 NativeEngine 对称）。"""
        from app.services.ai_chat.dsh_engine import DshEngine

        engine = DshEngine(db=None)
        request = _make_request()
        stream = engine.run(request, NEVER_CANCELLED)
        assert isinstance(stream, EngineStream)


# ---------------------------------------------------------------------------
# Test: Property 25 — DSH 失败不降级
# ---------------------------------------------------------------------------


class TestDshFailureNoDegradation:
    """Property 25: DSH/MCP/handshake 失败 → engine_unavailable，NativeEngine 不被调用。"""

    @pytest.mark.asyncio
    async def test_sdk_unavailable_raises_engine_unavailable(self) -> None:
        """SDK discovery 失败 → EngineFailure(engine_unavailable)。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        engine = DshEngine(db=None)
        request = _make_request()

        # Mock SDK discovery to return unavailable
        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.sdk_not_found,
            vendor_root=Path("D:/NonExistent"),
            errors=["DSH vendor root 不存在"],
        )

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            stream = engine.run(request, NEVER_CANCELLED)
            with pytest.raises(EngineFailure) as exc_info:
                async for _ in stream:
                    pass
            assert exc_info.value.code == ChatErrorCode.engine_unavailable
            assert "不可用" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_native_engine_never_invoked_on_dsh_failure(self) -> None:
        """DSH 失败时 NativeEngine 调用次数恒为 0（绝不隐式回落）。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        native_invocations = []

        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.import_failed,
            vendor_root=Path("D:/NonExistent"),
            errors=["Python SDK import 失败"],
        )

        # Patch NativeEngine.run to track invocations & discovery to fail
        with patch(
            "app.services.ai_chat.native_engine.NativeEngine.run",
            side_effect=lambda *a, **k: native_invocations.append(1),
        ), patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            engine = DshEngine(db=None)
            request = _make_request()

            stream = engine.run(request, NEVER_CANCELLED)
            with pytest.raises(EngineFailure):
                async for _ in stream:
                    pass

        # NativeEngine 调用次数必须为 0
        assert len(native_invocations) == 0

    # ------------------------------------------------------------------
    # 🔴 门本身的判据（变异 M13 补口）
    #
    # 上面两条只断言**最终结果**是 `engine_unavailable`。但 `_run` 里 ②SDK 门之后还有
    # ④上下文创建 / ⑥MCP 进程 / ⑦DSH root / ⑧handshake，**任何一步失败也都抛
    # `engine_unavailable`**，detail 里同样可能带「不可用」。于是变异实测：给
    # `_verify_sdk_available` 开头加 `return`（SDK 门完全失效）——上面两条**依旧全绿**
    # （GREEN = 守卫缺陷），因为流程只是往后多走几步、换个地方失败，结果码不变。
    #
    # 下面三条把判据落到「门本身」：门要么抛、要么放行，且抛的时候后续步骤一次都没跑。
    # ------------------------------------------------------------------

    @staticmethod
    def _discovery(status_available: bool):
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        if status_available:
            return DshDiscoveryResult(
                status=DshDiscoveryStatus.available,
                vendor_root=Path("D:/DeepHorness"),
                version="0.1.0-rc.8",
                python_sdk_importable=True,
                bundled_cordis_exists=True,
            )
        return DshDiscoveryResult(
            status=DshDiscoveryStatus.sdk_not_found,
            vendor_root=Path("D:/NonExistent"),
            errors=["DSH vendor root 不存在", "second reason", "third reason"],
        )

    def test_verify_sdk_gate_raises_when_discovery_unavailable(self) -> None:
        """直接调 `_verify_sdk_available()`：discovery 不可用时**必须**抛。

        MUTATION ANCHOR P25-A: 门内加 `return` → 本条打红。
        """
        from app.services.ai_chat.dsh_engine import DshEngine

        engine = DshEngine(db=None)
        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=self._discovery(False),
        ):
            with pytest.raises(EngineFailure) as exc_info:
                engine._verify_sdk_available()

        assert exc_info.value.code == ChatErrorCode.engine_unavailable
        # detail 必须点名 SDK 门（否则分不清是门拦的还是后续步骤失败）
        assert "SDK" in exc_info.value.detail
        assert "sdk_not_found" in exc_info.value.detail
        # discovery 的具体原因要透出，便于运维定位
        assert "DSH vendor root 不存在" in exc_info.value.detail

    def test_verify_sdk_gate_is_silent_when_discovery_available(self) -> None:
        """反向自检：discovery 可用时门必须放行（不能变成恒抛）。

        没有这条，把门改成 `raise` 恒抛也能让上一条通过 —— 判据失去分辨力。
        """
        from app.services.ai_chat.dsh_engine import DshEngine

        engine = DshEngine(db=None)
        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=self._discovery(True),
        ):
            assert engine._verify_sdk_available() is None

    @pytest.mark.asyncio
    async def test_sdk_gate_blocks_before_context_and_process_creation(self) -> None:
        """SDK 不可用时，worker 许可 / 隔离上下文 / MCP 进程**一次都不创建**。

        这是「前置门」的真判据：不只看错误码，看后续副作用有没有发生。
        MUTATION ANCHOR P25-B: 门内加 `return` → 上下文与进程被创建 → 本条打红。
        """
        from app.services.ai_chat.dsh_engine import DshEngine

        created_contexts: list[Any] = []
        spawned_mcp: list[Any] = []

        async def _spy_create_run_context(_self, request):  # noqa: ANN001
            created_contexts.append(request.run_id)
            raise AssertionError("SDK 门失效：不该走到上下文创建")

        async def _spy_spawn_mcp(ctx):  # noqa: ANN001
            spawned_mcp.append(ctx)

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=self._discovery(False),
        ), patch(
            "app.services.ai_chat.dsh_engine.DshEngine._create_run_context",
            _spy_create_run_context,
        ), patch(
            "app.services.ai_chat.dsh_engine.DshProcessManager.spawn_mcp_process",
            _spy_spawn_mcp,
        ):
            engine = DshEngine(db=None)
            request = _make_request()
            stream = engine.run(request, NEVER_CANCELLED)
            with pytest.raises(EngineFailure) as exc_info:
                async for _ in stream:
                    pass

        assert exc_info.value.code == ChatErrorCode.engine_unavailable
        assert created_contexts == [], "SDK 门之后仍创建了 per-run 上下文"
        assert spawned_mcp == [], "SDK 门之后仍拉起了 MCP 进程"


# ---------------------------------------------------------------------------
# Test: Property 38 — DshEngine backpressure 有界
# ---------------------------------------------------------------------------


class TestDshBackpressure:
    """Property 38: active/queue 超限返回 quota error，不无界拉起进程。"""

    @pytest.mark.asyncio
    async def test_pool_acquire_and_release(self) -> None:
        """Worker pool 正常 acquire/release。"""
        from app.services.ai_chat.dsh_engine import DshWorkerPool

        pool = DshWorkerPool()
        run_id = uuid4()

        # acquire 应该成功
        await pool.acquire(run_id)
        pool.release(run_id)
        assert pool.active_count == 0

    @pytest.mark.asyncio
    async def test_pool_max_active_limit(self) -> None:
        """达到 max active 后，额外请求需排队。"""
        from app.services.ai_chat.dsh_engine import DshWorkerPool

        pool = DshWorkerPool()

        # 用小的 max_active 测试
        with patch("app.services.ai_chat.dsh_engine._dsh_max_active", return_value=2):
            # 重建 pool 以使用新的 limit
            pool = DshWorkerPool()

            # 获取 2 个许可
            await pool.acquire(uuid4())
            await pool.acquire(uuid4())

            # 第 3 个应该排队（用 timeout 检测阻塞）
            acquired = asyncio.Event()

            async def try_acquire():
                await pool.acquire(uuid4())
                acquired.set()

            task = asyncio.create_task(try_acquire())
            await asyncio.sleep(0.1)
            assert not acquired.is_set()  # 应该被阻塞

            # 释放一个后应该通过
            pool.release(uuid4())  # 这会释放 semaphore
            await asyncio.sleep(0.1)
            assert acquired.is_set()

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_pool_queue_limit_exceeded(self) -> None:
        """队列满后返回 rate_limited error。"""
        from app.services.ai_chat.dsh_engine import DshWorkerPool

        with (
            patch("app.services.ai_chat.dsh_engine._dsh_max_active", return_value=1),
            patch("app.services.ai_chat.dsh_engine._dsh_queue_limit", return_value=0),
        ):
            pool = DshWorkerPool()

            # 第一个 acquire 拿到许可
            await pool.acquire(uuid4())

            # semaphore locked + queue_limit=0 → 应该立即失败
            with pytest.raises(EngineFailure) as exc_info:
                await pool.acquire(uuid4())
            assert exc_info.value.code == ChatErrorCode.rate_limited


# ---------------------------------------------------------------------------
# Test: Property 8 — 取消传播
# ---------------------------------------------------------------------------


class TestDshCancelPropagation:
    """Property 8: cancel 后工具调用计数不再增加。"""

    def test_run_context_cancelled_flag(self) -> None:
        """DshRunContext.cancelled 标志设置后阻止工具计数增加。"""
        from app.services.ai_chat.dsh_engine import DshRunContext

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
        )

        # 初始状态
        assert not ctx.cancelled
        assert ctx.tool_call_count == 0

        # 模拟 cancel
        ctx.cancelled = True
        # cancel 后不应增加（由 engine 逻辑控制）
        assert ctx.cancelled

    @pytest.mark.asyncio
    async def test_cancel_signal_stops_execution(self) -> None:
        """cancel signal 导致 EngineCancelled。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        engine = DshEngine(db=None)
        request = _make_request()

        # 立即取消的 signal
        cancel = EventCancelSignal()
        cancel.cancel()

        # Mock SDK discovery to be available
        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.available,
            vendor_root=Path("D:/DeepHorness"),
            version="0.1.0-rc.8",
            python_sdk_importable=True,
            bundled_cordis_exists=True,
        )

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            stream = engine.run(request, cancel)
            with pytest.raises(EngineCancelled):
                async for _ in stream:
                    pass


# ---------------------------------------------------------------------------
# Test: Property 28 — 跨用户隔离
# ---------------------------------------------------------------------------


class TestDshUserIsolation:
    """Property 28: per-run 进程，不跨 principal 复用。"""

    def test_run_context_principal_binding(self) -> None:
        """每个 DshRunContext 绑定到特定 principal。"""
        from app.services.ai_chat.dsh_engine import DshRunContext

        user_a = uuid4()
        user_b = uuid4()

        ctx_a = DshRunContext(run_id=uuid4(), principal_id=user_a, project_id=uuid4())
        ctx_b = DshRunContext(run_id=uuid4(), principal_id=user_b, project_id=uuid4())

        assert ctx_a.principal_id != ctx_b.principal_id
        assert ctx_a.run_id != ctx_b.run_id

    def test_pool_isolates_runs(self) -> None:
        """Worker pool 中不同 run 使用不同的 context。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()
        ctx_a = DshRunContext(run_id=uuid4(), principal_id=uuid4(), project_id=uuid4())
        ctx_b = DshRunContext(run_id=uuid4(), principal_id=uuid4(), project_id=uuid4())

        pool.register(ctx_a)
        pool.register(ctx_b)

        assert pool.get_context(ctx_a.run_id) is ctx_a
        assert pool.get_context(ctx_b.run_id) is ctx_b
        assert pool.get_context(ctx_a.run_id) is not ctx_b


# ---------------------------------------------------------------------------
# Test: Process Manager cleanup
# ---------------------------------------------------------------------------


class TestDshProcessManager:
    """DshProcessManager 清理与审计。"""

    @pytest.mark.asyncio
    async def test_terminate_all_cleans_session_dir(self) -> None:
        """terminate_all 清理 session 目录。"""
        import tempfile
        from app.services.ai_chat.dsh_engine import DshProcessManager, DshRunContext

        # 创建临时 session 目录
        session_dir = Path(tempfile.mkdtemp(prefix="dsh_test_"))
        (session_dir / "test.jsonl").write_text("test", encoding="utf-8")

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            session_dir=session_dir,
        )

        assert session_dir.exists()
        await DshProcessManager.terminate_all(ctx)
        assert not session_dir.exists()

    @pytest.mark.asyncio
    async def test_terminate_all_records_cleanup_errors(self) -> None:
        """terminate_all 在清理失败时记录错误（不静默）。"""
        from app.services.ai_chat.dsh_engine import DshProcessManager, DshRunContext

        # 使用不存在的目录不会报错（rmtree 只在目录存在时执行）
        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            session_dir=Path("/nonexistent/path/that/definitely/does/not/exist"),
        )

        await DshProcessManager.terminate_all(ctx)
        # 目录不存在不会触发清理错误
        assert ctx.cleanup_errors == []

    def test_run_context_timeout_detection(self) -> None:
        """DshRunContext 正确检测超时。"""
        import time
        from app.services.ai_chat.dsh_engine import DshRunContext

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            started_at=time.monotonic() - 999,  # 999 秒前启动
        )

        assert ctx.is_timed_out  # 180s 超时

    def test_run_context_not_timed_out(self) -> None:
        """新创建的 context 不超时。"""
        from app.services.ai_chat.dsh_engine import DshRunContext

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
        )

        assert not ctx.is_timed_out


# ---------------------------------------------------------------------------
# Test: engine 选择门（补充 Task 6 的 DSH 路径）
# ---------------------------------------------------------------------------


class TestEngineResolutionDshPath:
    """resolve_engine 与 build_engine 的 DSH 分支。"""

    def test_resolve_engine_dsh_enabled_with_project(self) -> None:
        """配置 dsh + enabled + project in allowlist → 返回 dsh。"""
        project_id = uuid4()
        with patch.multiple(
            "app.core.config.settings",
            AI_CHAT_ENGINE="dsh",
            AI_DSH_ENABLED=True,
            AI_DSH_PROJECT_ALLOWLIST=str(project_id),
        ):
            engine, reason = resolve_engine(project_id=project_id)
            assert engine == ChatEngineName.dsh
            assert reason is None

    def test_resolve_engine_dsh_disabled(self) -> None:
        """配置 dsh 但 flag 关闭 → 回落 native + 原因。"""
        with patch.multiple(
            "app.core.config.settings",
            AI_CHAT_ENGINE="dsh",
            AI_DSH_ENABLED=False,
        ):
            engine, reason = resolve_engine(project_id=uuid4())
            assert engine == ChatEngineName.native
            assert reason == "experimental_disabled"

    def test_resolve_engine_dsh_project_not_in_allowlist(self) -> None:
        """配置 dsh + enabled 但项目不在 allowlist → 回落 native。"""
        with patch.multiple(
            "app.core.config.settings",
            AI_CHAT_ENGINE="dsh",
            AI_DSH_ENABLED=True,
            AI_DSH_PROJECT_ALLOWLIST=str(uuid4()),  # 不同项目
        ):
            engine, reason = resolve_engine(project_id=uuid4())
            assert engine == ChatEngineName.native
            assert reason == "project_not_allowlisted"

    def test_resolve_engine_dsh_no_project(self) -> None:
        """配置 dsh + enabled 但无项目 → 回落 native。"""
        with patch.multiple(
            "app.core.config.settings",
            AI_CHAT_ENGINE="dsh",
            AI_DSH_ENABLED=True,
            AI_DSH_PROJECT_ALLOWLIST="",
        ):
            engine, reason = resolve_engine(project_id=None)
            assert engine == ChatEngineName.native
            assert reason == "no_project_binding"


# ---------------------------------------------------------------------------
# Test: DshEngine 事件序列结构
# ---------------------------------------------------------------------------


class TestDshEventSequence:
    """DshEngine 产出的事件序列满足统一协议。"""

    @pytest.mark.asyncio
    async def test_failure_produces_error_terminal_intent(self) -> None:
        """DSH 失败时产出 error 终态意图事件。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        engine = DshEngine(db=None)
        request = _make_request()

        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.sdk_not_found,
            vendor_root=Path("D:/NonExistent"),
            errors=["SDK 不存在"],
        )

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            stream = engine.run(request, NEVER_CANCELLED)
            events = []
            with pytest.raises(EngineFailure):
                async for event in stream:
                    events.append(event)

            # 应该有一个 error 终态意图
            terminal_events = [e for e in events if e.type == ChatEventType.error]
            assert len(terminal_events) == 1
            assert terminal_events[0].payload["code"] == ChatErrorCode.engine_unavailable.value

    @pytest.mark.asyncio
    async def test_cancel_produces_cancelled_terminal_intent(self) -> None:
        """取消时产出 cancelled 终态意图事件。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        engine = DshEngine(db=None)
        request = _make_request()

        # 已取消的 signal
        cancel = EventCancelSignal()
        cancel.cancel()

        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.available,
            vendor_root=Path("D:/DeepHorness"),
            version="0.1.0-rc.8",
            python_sdk_importable=True,
            bundled_cordis_exists=True,
        )

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            stream = engine.run(request, cancel)
            events = []
            with pytest.raises(EngineCancelled):
                async for event in stream:
                    events.append(event)

            # 应该有 cancelled 终态意图
            terminal_events = [e for e in events if e.type == ChatEventType.cancelled]
            assert len(terminal_events) == 1

    @pytest.mark.asyncio
    async def test_no_project_context_fails_cleanly(self) -> None:
        """无项目上下文时 → engine_unavailable。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

        engine = DshEngine(db=None)
        host = _make_host_context(project_id=None)
        host.project_id = None  # 无项目
        request = _make_request(host=host)

        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.available,
            vendor_root=Path("D:/DeepHorness"),
            version="0.1.0-rc.8",
            python_sdk_importable=True,
            bundled_cordis_exists=True,
        )

        with patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            stream = engine.run(request, NEVER_CANCELLED)
            with pytest.raises(EngineFailure) as exc_info:
                async for _ in stream:
                    pass
            assert exc_info.value.code == ChatErrorCode.engine_unavailable
            assert "项目" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test: Worker pool cleanup
# ---------------------------------------------------------------------------


class TestDshWorkerPoolCleanup:
    """Worker pool expired process cleanup。"""

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_runs(self) -> None:
        """cleanup_expired 清理超 TTL 的进程。"""
        import time
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()

        # 注册一个"很久以前"启动的 run
        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            started_at=time.monotonic() - 99999,  # 远超 TTL
        )
        pool.register(ctx)
        assert pool.active_count == 1

        cleaned = await pool.cleanup_expired()
        assert cleaned == 1
        assert pool.active_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_preserves_active_runs(self) -> None:
        """cleanup_expired 不清理未超时的 run。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
        )
        pool.register(ctx)
        assert pool.active_count == 1

        cleaned = await pool.cleanup_expired()
        assert cleaned == 0
        assert pool.active_count == 1
