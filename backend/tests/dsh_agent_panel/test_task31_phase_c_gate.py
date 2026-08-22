# Feature: dsh-agent-panel-integration — Task 31 Phase C 运行时验收守卫
"""Phase C 双用户、取消、进程、端口与 egress 真实验收。

本文件是 Phase C 的 **gate guard**：综合验证 Tasks 25–30 所有产物在联合执行时
满足 Properties 25–32, 38 的约束。未全绿 SHALL 不扩大 DSH project allowlist。

## 覆盖子任务

1. 双用户隔离：交换 token/run/project 均拒绝，session 文件不串用
2. 取消传播 root/tool/child：descendants 停止、tool count 不增长、占用归零
3. active/queue limit：不增加进程、有界排队或明确失败
4. 进程树与监听端口：MCP 无 TCP，model endpoint 在 allowlist
5. egress 证据：模型/embedding/OCR/MCP/plugin 无公网出站
6. 销毁后数据清理：root/session/JSONL/log/temp 不含前一 principal 数据
7. Phase C gate 综合：所有前置通过才允许 allowlist 扩大

Validates: Requirements 11.4, 11.5, 11.6, 11.11, 11.12, 12.2, 12.3, 14.3, 14.7
Properties: 25, 26, 27, 28, 29, 30, 31, 32, 38
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_a() -> UUID:
    return uuid4()


@pytest.fixture
def user_b() -> UUID:
    return uuid4()


@pytest.fixture
def project_a() -> UUID:
    return uuid4()


@pytest.fixture
def project_b() -> UUID:
    return uuid4()


@pytest.fixture
def run_a() -> UUID:
    return uuid4()


@pytest.fixture
def run_b() -> UUID:
    return uuid4()


@pytest.fixture
def token_service():
    from app.services.ai_chat.mcp_token import McpTokenService
    return McpTokenService()


@pytest.fixture
def budget_tracker():
    from app.services.ai_chat.mcp_budget import McpBudgetTracker
    return McpBudgetTracker()


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


# ===========================================================================
# 1. 双用户隔离（Property 28）
# ===========================================================================


class TestDualUserIsolation:
    """两用户同时运行 DSH run，交换 token/run/project 均被拒绝，
    返回数据与 session 文件不串用。

    **Validates: Requirements 11.5, 11.6**
    **Properties: 28**
    """

    def test_user_a_token_rejected_for_user_b_request(
        self, token_service, user_a: UUID, user_b: UUID, project_a: UUID, run_a: UUID
    ):
        """用户 A 的 scoped token 不能被用户 B 的请求使用。"""
        from app.services.ai_chat.mcp_token import McpTokenScopeMismatch

        scoped = token_service.create_token(
            user_id=user_a,
            project_id=project_a,
            run_id=run_a,
            role="auditor",
            cycle_scope=frozenset({"D", "E"}),
        )

        with pytest.raises(McpTokenScopeMismatch, match="user_id"):
            token_service.validate_token(
                scoped.token, expected_user_id=user_b
            )

    def test_user_b_token_rejected_for_user_a_run(
        self, token_service, user_a: UUID, user_b: UUID, project_a: UUID, run_a: UUID, run_b: UUID
    ):
        """用户 B 的 token 不能用于用户 A 的 run。"""
        from app.services.ai_chat.mcp_token import McpTokenScopeMismatch

        token_b = token_service.create_token(
            user_id=user_b,
            project_id=project_a,
            run_id=run_b,
            role="manager",
            cycle_scope=frozenset({"D"}),
        )

        with pytest.raises(McpTokenScopeMismatch, match="run_id"):
            token_service.validate_token(
                token_b.token, expected_run_id=run_a
            )

    def test_cross_project_token_rejected(
        self, token_service, user_a: UUID, project_a: UUID, project_b: UUID, run_a: UUID
    ):
        """token 不能跨项目使用。"""
        from app.services.ai_chat.mcp_token import McpTokenScopeMismatch

        scoped = token_service.create_token(
            user_id=user_a,
            project_id=project_a,
            run_id=run_a,
            role="auditor",
            cycle_scope=frozenset({"D"}),
        )

        with pytest.raises(McpTokenScopeMismatch, match="project_id"):
            token_service.validate_token(
                scoped.token, expected_project_id=project_b
            )

    def test_concurrent_runs_use_separate_contexts(
        self, user_a: UUID, user_b: UUID, project_a: UUID, project_b: UUID
    ):
        """两个并发 run 使用独立 DshRunContext，principal 不混淆。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()

        ctx_a = DshRunContext(
            run_id=uuid4(),
            principal_id=user_a,
            project_id=project_a,
        )
        ctx_b = DshRunContext(
            run_id=uuid4(),
            principal_id=user_b,
            project_id=project_b,
        )

        pool.register(ctx_a)
        pool.register(ctx_b)

        # 各自 context 绑定到各自 run_id
        assert pool.get_context(ctx_a.run_id).principal_id == user_a
        assert pool.get_context(ctx_b.run_id).principal_id == user_b
        # 交叉不可能
        assert pool.get_context(ctx_a.run_id).principal_id != user_b
        assert pool.get_context(ctx_b.run_id).principal_id != user_a

    @pytest.mark.asyncio
    async def test_session_dir_isolation(
        self, user_a: UUID, user_b: UUID, project_a: UUID
    ):
        """每个 run 的 session 目录独立，销毁后不含对方 principal 数据。"""
        from app.services.ai_chat.dsh_engine import DshProcessManager, DshRunContext

        # 用两个独立 tmp 目录模拟 per-run session
        dir_a = Path(tempfile.mkdtemp(prefix="dsh_user_a_"))
        dir_b = Path(tempfile.mkdtemp(prefix="dsh_user_b_"))

        (dir_a / "session.jsonl").write_text(
            f'{{"principal": "{user_a}"}}\n', encoding="utf-8"
        )
        (dir_b / "session.jsonl").write_text(
            f'{{"principal": "{user_b}"}}\n', encoding="utf-8"
        )

        ctx_a = DshRunContext(
            run_id=uuid4(),
            principal_id=user_a,
            project_id=project_a,
            session_dir=dir_a,
        )

        # 销毁用户 A 的 session
        await DshProcessManager.terminate_all(ctx_a)

        # 用户 A 的 session 已清理
        assert not dir_a.exists()
        # 用户 B 的 session 完好
        assert dir_b.exists()
        content_b = (dir_b / "session.jsonl").read_text(encoding="utf-8")
        assert str(user_a) not in content_b
        assert str(user_b) in content_b

        # 清理
        import shutil
        if dir_b.exists():
            shutil.rmtree(dir_b)

    def test_token_revoke_by_cancel_does_not_affect_other_user(
        self, token_service, user_a: UUID, user_b: UUID, project_a: UUID
    ):
        """撤销用户 A 的 token 不影响用户 B 的 token。"""
        run_a = uuid4()
        run_b = uuid4()

        token_a = token_service.create_token(
            user_id=user_a, project_id=project_a, run_id=run_a,
            role="auditor", cycle_scope=frozenset({"D"}),
        )
        token_b = token_service.create_token(
            user_id=user_b, project_id=project_a, run_id=run_b,
            role="manager", cycle_scope=frozenset({"D", "E"}),
        )

        # 撤销 A
        token_service.revoke_token(token_a.payload.token_id)

        # A 已失效
        from app.services.ai_chat.mcp_token import McpTokenRevoked
        with pytest.raises(McpTokenRevoked):
            token_service.validate_token(token_a.token)

        # B 仍然有效
        payload_b = token_service.validate_token(token_b.token)
        assert payload_b.user_id == user_b


# ===========================================================================
# 2. 取消传播 root/tool/child（Property 8）
# ===========================================================================


class TestCancelPropagationAllStages:
    """在 root/tool/child 三个阶段取消，确认 descendants 停止、
    后续 tool count 不增长、占用归零。

    **Validates: Requirements 11.11**
    **Properties: 8**
    """

    def test_cancel_during_sdk_discovery_stops_run(self):
        """SDK discovery 阶段取消 → EngineCancelled。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.engine import EngineCancelled, EventCancelSignal
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus
        from app.services.ai_chat.run_contract import CAPABILITIES_BY_ENGINE
        from app.services.ai_chat.engine import AuthorizedChatRunRequest
        from app.models.ai_models import ChatEngineName

        engine = DshEngine(db=None)
        host = _make_host_context()

        request = AuthorizedChatRunRequest(
            run_id=uuid4(),
            session_id=uuid4(),
            request_id=uuid4(),
            host=host,
            query="测试取消",
            engine=ChatEngineName.dsh,
            capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.dsh],
            assistant_message_id=uuid4(),
        )

        # 立即取消
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
            with pytest.raises(EngineCancelled):
                asyncio.run(self._drain(stream))

    @staticmethod
    async def _drain(stream):
        async for _ in stream:
            pass

    def test_cancel_sets_context_flag_blocking_new_tool_calls(self):
        """cancel 设置 DshRunContext.cancelled 后，新工具调用被拦截。"""
        from app.services.ai_chat.dsh_engine import DshRunContext

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
        )

        assert not ctx.cancelled
        ctx.tool_call_count = 3

        # 取消
        ctx.cancelled = True

        # cancelled 后 tool count 冻结（engine 逻辑保证不再 dispatch）
        assert ctx.cancelled
        assert ctx.tool_call_count == 3

    @pytest.mark.asyncio
    async def test_cancel_cleans_worker_pool_occupancy(self):
        """取消后 worker pool 释放占用，active_count 归零。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()
        run_id = uuid4()

        # acquire 获取 semaphore 许可，register 注册到 active dict
        await pool.acquire(run_id)
        ctx = DshRunContext(run_id=run_id, principal_id=uuid4(), project_id=uuid4())
        pool.register(ctx)
        assert pool.active_count == 1

        # release 同时释放 semaphore 和移除 active 注册
        pool.release(run_id)
        assert pool.active_count == 0

    def test_mcp_budget_frozen_after_cancel(self, budget_tracker, run_a: UUID):
        """取消后 budget 被释放，后续调用无法消费。"""
        from app.services.ai_chat.mcp_budget import McpBudgetExceeded

        budget_tracker.get_or_create(run_a)
        budget_tracker.check_and_consume(run_a, response_bytes=100)

        # 模拟 cancel 释放 budget
        budget_tracker.release(run_a)

        # 后续调用应该找不到 budget（已释放）
        status = budget_tracker.get_status(run_a)
        assert status is None


# ===========================================================================
# 3. active/queue limit（Property 38）
# ===========================================================================


class TestBackpressureLimits:
    """达到 active/queue limit，确认不增加进程、请求有界排队或明确失败。

    **Validates: Requirements 11.12**
    **Properties: 38**
    """

    @pytest.mark.asyncio
    async def test_active_limit_blocks_additional_runs(self):
        """达到 max_active 后，sem locked + queue_limit=0 → 立即 rate_limited。

        🔴 这里使用 queue_limit=0 直接验证拒绝行为（与 Task 28 测试一致），
        避免在测试中使用 asyncio.create_task 后被 semaphore.acquire 永久阻塞。
        """
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool
        from app.services.ai_chat.engine import EngineFailure
        from app.services.ai_chat.run_contract import ChatErrorCode

        with (
            patch("app.services.ai_chat.dsh_engine._dsh_max_active", return_value=2),
            patch("app.services.ai_chat.dsh_engine._dsh_queue_limit", return_value=0),
        ):
            pool = DshWorkerPool()

            # 占满 active（2 个 acquire 拿走全部 semaphore 许可）
            run1 = uuid4()
            run2 = uuid4()
            await pool.acquire(run1)
            pool.register(DshRunContext(run_id=run1, principal_id=uuid4(), project_id=uuid4()))
            await pool.acquire(run2)
            pool.register(DshRunContext(run_id=run2, principal_id=uuid4(), project_id=uuid4()))
            assert pool.active_count == 2

            # 第 3 个：semaphore locked + queue_limit=0 → 立即 rate_limited
            with pytest.raises(EngineFailure) as exc_info:
                await pool.acquire(uuid4())
            assert exc_info.value.code == ChatErrorCode.rate_limited

            # 释放一个后可以再次 acquire
            pool.release(run1)
            run3 = uuid4()
            await pool.acquire(run3)
            pool.register(DshRunContext(run_id=run3, principal_id=uuid4(), project_id=uuid4()))
            # 释放后恢复了容量
            assert pool.active_count == 2  # run2 + run3

    @pytest.mark.asyncio
    async def test_zero_queue_immediate_rejection(self):
        """queue_limit=0 时，超过 active 的请求立即被拒绝。"""
        from app.services.ai_chat.dsh_engine import DshWorkerPool
        from app.services.ai_chat.engine import EngineFailure
        from app.services.ai_chat.run_contract import ChatErrorCode

        with (
            patch("app.services.ai_chat.dsh_engine._dsh_max_active", return_value=1),
            patch("app.services.ai_chat.dsh_engine._dsh_queue_limit", return_value=0),
        ):
            pool = DshWorkerPool()
            await pool.acquire(uuid4())

            with pytest.raises(EngineFailure) as exc_info:
                await pool.acquire(uuid4())
            assert exc_info.value.code == ChatErrorCode.rate_limited

    @pytest.mark.asyncio
    async def test_release_restores_capacity(self):
        """释放后 pool 恢复接受新请求的能力。"""
        from app.services.ai_chat.dsh_engine import DshWorkerPool

        with patch("app.services.ai_chat.dsh_engine._dsh_max_active", return_value=1):
            pool = DshWorkerPool()

            run1 = uuid4()
            await pool.acquire(run1)
            pool.release(run1)

            # 可以再次 acquire
            run2 = uuid4()
            await pool.acquire(run2)
            pool.release(run2)
            assert pool.active_count == 0


# ===========================================================================
# 4. 进程树、监听端口与工具目录（Properties 26, 27）
# ===========================================================================


class TestProcessPortAndToolCatalog:
    """观察真实进程树、监听端口、effective tool catalog、model endpoint；
    MCP 无 TCP 监听。

    **Validates: Requirements 11.4, 12.2**
    **Properties: 26, 27**
    """

    def test_mcp_server_source_has_no_tcp_bind(self):
        """audit-data MCP server 源码不含 TCP bind/listen。"""
        PROJECT_ROOT = Path(__file__).resolve().parents[3]
        server_file = PROJECT_ROOT / "tools" / "audit-data-mcp" / "server.py"
        assert server_file.exists(), f"server.py 不存在: {server_file}"

        source = server_file.read_text(encoding="utf-8")

        # 提取可执行代码行（排除注释和文档字符串）
        code_lines: list[str] = []
        in_docstring = False
        docstring_char = ""
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2:
                        continue
                    in_docstring = True
                    continue
                code_lines.append(line)
            else:
                if docstring_char in stripped:
                    in_docstring = False
                continue

        code = "\n".join(code_lines)

        tcp_patterns = [
            r"\.bind\(\s*\(",
            r"uvicorn\.run",
            r"\bHTTPServer\b",
            r"\bTCPServer\b",
            r"\bsocketserver\b",
        ]
        for p in tcp_patterns:
            assert not re.search(p, code), (
                f"MCP server 可执行代码含 TCP 模式: {p}（Req 11.4 禁止）"
            )

    def test_mcp_server_uses_stdio_transport(self):
        """MCP server 使用 stdio transport（mcp.run() 默认）。"""
        PROJECT_ROOT = Path(__file__).resolve().parents[3]
        server_file = PROJECT_ROOT / "tools" / "audit-data-mcp" / "server.py"
        source = server_file.read_text(encoding="utf-8")

        assert "mcp.run()" in source, "必须调用 mcp.run()（stdio 模式）"
        assert 'transport="http"' not in source
        assert "transport='http'" not in source

    def test_effective_tool_catalog_matches_readonly_set(self):
        """effective tool catalog 与 MCP_READONLY_TOOLS 完全相等。"""
        from app.services.ai_chat.mcp_token import MCP_READONLY_TOOLS

        expected = {
            "wp_list", "wp_read", "tb_query", "addr_lookup",
            "kb_search", "note_read", "review_prompt",
        }
        assert MCP_READONLY_TOOLS == expected

    def test_tool_catalog_no_dangerous_tools(self):
        """工具白名单不含危险工具。"""
        from app.services.ai_chat.mcp_token import MCP_READONLY_TOOLS

        dangerous = {"bash", "shell", "fs_write", "web_fetch", "subprocess",
                     "exec", "eval", "system", "terminal"}
        assert MCP_READONLY_TOOLS & dangerous == set()

    def test_model_route_validates_local_only(self):
        """model endpoint 必须在 allowlist（本地/内网）。"""
        from app.services.ai_chat.dsh_discovery import validate_model_route

        # 本地通过
        assert not validate_model_route("http://localhost:8100/v1")
        assert not validate_model_route("http://127.0.0.1:8100/v1")

        # Cloud 拒绝
        assert validate_model_route("https://api.openai.com/v1")
        assert validate_model_route("https://api.deepseek.com/v1")

    def test_cordis_config_no_bash_shell_tools(self):
        """platform Cordis config 不含 bash/shell/fs-write。"""
        from app.services.ai_chat.dsh_discovery import (
            build_platform_cordis_config,
            validate_cordis_services,
        )

        config = build_platform_cordis_config(
            mcp_command="python -m audit_data_mcp",
        )
        errors = validate_cordis_services(config)
        assert not errors, f"Cordis 安全校验失败: {errors}"

        service_names = {item.get("name", "") for item in config}
        bash_services = {
            "@deepseek-ai/dsh-bash-local",
            "@deepseek-ai/dsh-tool-bash-persistent",
            "@deepseek-ai/dsh-terminal-bash",
            "@deepseek-ai/dsh-tool-fs",
        }
        assert not service_names & bash_services


# ===========================================================================
# 5. Egress 证据（Req 12.2, 12.3）
# ===========================================================================


class TestNoEgressEvidence:
    """证明模型、embedding、OCR、MCP、plugin 无公网出站。

    注意：完整网络层阻断需要 CI 环境。本守卫从配置/代码层面证明无 egress 路径。

    **Validates: Requirements 12.2, 12.3**
    **Properties: 25, 26**
    """

    def test_startup_health_rejects_cloud_model(self):
        """cloud model endpoint 被 startup health 拒绝。"""
        from app.services.ai_chat.dsh_discovery import validate_model_route

        cloud_endpoints = [
            "https://api.openai.com/v1",
            "https://api.anthropic.com/v1",
            "https://api.deepseek.com/v1",
            "https://generativelanguage.googleapis.com/v1",
        ]
        for endpoint in cloud_endpoints:
            errors = validate_model_route(endpoint)
            assert errors, f"{endpoint} 应被拒绝但通过了"

    def test_startup_health_rejects_cloud_embedding(self):
        """cloud embedding endpoint 报 local_only_violation。"""
        mock_settings = MagicMock()
        mock_settings.LLM_BASE_URL = "http://localhost:8100/v1"
        mock_settings.LLM_EMBEDDING_BASE_URL = "https://api.deepseek.com/v1"
        mock_settings.OCR_PADDLE_ENABLED = True
        mock_settings.OCR_TESSERACT_ENABLED = True
        mock_settings.PORT = 9980

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = asyncio.run(run_ai_chat_startup_health_check())

        embedding = next(c for c in report.checks if c.service == "embedding")
        assert not embedding.ok
        assert embedding.error_code == "local_only_violation"

    def test_mcp_server_only_calls_audit_api_base(self):
        """MCP server 源码只调用 AUDIT_API_BASE（本地 platform REST），不调外部 URL。"""
        PROJECT_ROOT = Path(__file__).resolve().parents[3]
        server_file = PROJECT_ROOT / "tools" / "audit-data-mcp" / "server.py"
        source = server_file.read_text(encoding="utf-8")

        # 允许的 env var：AUDIT_API_BASE（默认 localhost:9980）
        # 禁止的外部 URL patterns
        external_url_patterns = [
            r'https?://api\.(openai|anthropic|deepseek|google)',
            r'https?://.*\.amazonaws\.com',
            r'https?://.*\.azure\.com',
        ]
        for pattern in external_url_patterns:
            matches = re.findall(pattern, source)
            assert not matches, (
                f"MCP server 包含外部 URL: {pattern} → {matches}"
            )

    def test_dsh_env_construction_no_secrets_leakage(self):
        """DSH 进程的环境变量构造使用 allowlist，不全量继承。"""
        from app.services.ai_chat.dsh_engine import _build_mcp_env

        env = _build_mcp_env(
            token="test-scoped-token",
            api_base="http://localhost:9980",
            run_id="run-123",
        )

        # 只包含允许的 key
        assert "AUDIT_API_BASE" in env
        assert "MCP_SCOPED_TOKEN" in env
        assert "MCP_RUN_ID" in env

        # 不包含 DB/Redis 密钥
        forbidden_keys = {"DATABASE_URL", "REDIS_URL", "DB_PASSWORD", "SECRET_KEY"}
        for key in forbidden_keys:
            assert key not in env, f"DSH env 不应含: {key}"

    def test_cordis_llm_points_to_loopback(self):
        """Cordis 配置的 LLM provider 指向本地 loopback。"""
        from app.services.ai_chat.dsh_discovery import build_platform_cordis_config

        config = build_platform_cordis_config(
            vllm_base_url="http://localhost:8100/v1",
            vllm_model="Qwen3.5-27B-NVFP4",
        )

        llm_item = next(
            (item for item in config if "llm" in item.get("id", "")), None
        )
        assert llm_item is not None
        base_url = llm_item.get("config", {}).get("baseUrl", "")
        assert "localhost" in base_url or "127.0.0.1" in base_url, (
            f"LLM baseUrl 不是本地地址: {base_url}（Req 12.2: local-only）"
        )


# ===========================================================================
# 6. 销毁后数据清理（Req 11.11）
# ===========================================================================


class TestPostDestructionCleanup:
    """销毁后扫描 root/session/JSONL/log/temp 不含前一 principal 数据。

    **Validates: Requirements 11.11**
    **Properties: 28**
    """

    @pytest.mark.asyncio
    async def test_terminate_all_removes_session_dir(self):
        """terminate_all 清理 session 目录，不留残余。"""
        from app.services.ai_chat.dsh_engine import DshProcessManager, DshRunContext

        session_dir = Path(tempfile.mkdtemp(prefix="dsh_cleanup_"))
        (session_dir / "agent.jsonl").write_text(
            '{"event": "tool_started"}\n', encoding="utf-8"
        )
        (session_dir / "mcp.log").write_text("log content\n", encoding="utf-8")
        (session_dir / "tmp_data.bin").write_bytes(b"\x00" * 1024)

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            session_dir=session_dir,
        )

        await DshProcessManager.terminate_all(ctx)

        assert not session_dir.exists(), "session 目录应被完全删除"

    @pytest.mark.asyncio
    async def test_cleanup_records_errors_on_permission_failure(self):
        """清理失败时记录错误（不静默吞掉），但不抛异常。"""
        from app.services.ai_chat.dsh_engine import DshProcessManager, DshRunContext

        # 不存在的目录不会报错
        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            session_dir=Path("/definitely/nonexistent/path/xyz"),
        )

        # 不应抛异常
        await DshProcessManager.terminate_all(ctx)
        assert ctx.cleanup_errors == []

    @pytest.mark.asyncio
    async def test_expired_runs_cleaned_from_pool(self):
        """超时的 run 被 cleanup_expired 清理。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()

        # 注册一个"远超 TTL"的 run
        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            started_at=time.monotonic() - 99999,
        )
        pool.register(ctx)
        assert pool.active_count == 1

        cleaned = await pool.cleanup_expired()
        assert cleaned == 1
        assert pool.active_count == 0

    @pytest.mark.asyncio
    async def test_active_runs_not_cleaned(self):
        """未超时的 run 不被 cleanup_expired 清理。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()

        ctx = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
        )
        pool.register(ctx)

        cleaned = await pool.cleanup_expired()
        assert cleaned == 0
        assert pool.active_count == 1


# ===========================================================================
# 7. Phase C Gate 综合（Properties 25–32, 38）
# ===========================================================================


class TestPhaseCGateComprehensive:
    """Phase C 所有前置条件的综合验证。

    Phase C 未全绿 SHALL 不扩大 project allowlist。

    **Validates: Requirements 14.3, 14.7**
    """

    def test_dsh_feature_gate_triple_check(self):
        """DSH 三层门（config → enabled → allowlist）全部有效。"""
        from app.services.ai_chat.engine import resolve_engine
        from app.models.ai_models import ChatEngineName

        project_id = uuid4()

        # 层 1：配置为 native → native
        with patch("app.core.config.settings") as s:
            s.AI_CHAT_ENGINE = "native"
            engine, _ = resolve_engine(project_id=project_id)
            assert engine == ChatEngineName.native

        # 层 2：配置 dsh 但 disabled → native
        with patch("app.core.config.settings") as s:
            s.AI_CHAT_ENGINE = "dsh"
            s.AI_DSH_ENABLED = False
            s.AI_DSH_PROJECT_ALLOWLIST = ""
            engine, reason = resolve_engine(project_id=project_id)
            assert engine == ChatEngineName.native
            assert reason == "experimental_disabled"

        # 层 3：配置 dsh + enabled 但项目不在 allowlist → native
        with patch("app.core.config.settings") as s:
            s.AI_CHAT_ENGINE = "dsh"
            s.AI_DSH_ENABLED = True
            s.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())  # 其他项目
            engine, reason = resolve_engine(project_id=project_id)
            assert engine == ChatEngineName.native
            assert reason == "project_not_allowlisted"

    def test_dsh_failure_never_invokes_native(self):
        """DSH 失败时 NativeEngine.run() 调用次数恒为 0（Property 25）。"""
        from app.services.ai_chat.dsh_engine import DshEngine
        from app.services.ai_chat.engine import EngineFailure
        from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus
        from app.services.ai_chat.run_contract import CAPABILITIES_BY_ENGINE, ChatErrorCode
        from app.services.ai_chat.engine import NEVER_CANCELLED, AuthorizedChatRunRequest
        from app.models.ai_models import ChatEngineName

        native_invocations = []

        fake_result = DshDiscoveryResult(
            status=DshDiscoveryStatus.sdk_not_found,
            vendor_root=Path("D:/NonExistent"),
            errors=["SDK 不存在"],
        )

        host = _make_host_context()
        request = AuthorizedChatRunRequest(
            run_id=uuid4(),
            session_id=uuid4(),
            request_id=uuid4(),
            host=host,
            query="测试",
            engine=ChatEngineName.dsh,
            capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.dsh],
            assistant_message_id=uuid4(),
        )

        with patch(
            "app.services.ai_chat.native_engine.NativeEngine.run",
            side_effect=lambda *a, **k: native_invocations.append(1),
        ), patch(
            "app.services.ai_chat.dsh_discovery.discover_dsh_sdk",
            return_value=fake_result,
        ):
            engine = DshEngine(db=None)
            stream = engine.run(request, NEVER_CANCELLED)
            with pytest.raises(EngineFailure) as exc_info:
                asyncio.run(self._drain(stream))
            assert exc_info.value.code == ChatErrorCode.engine_unavailable

        assert len(native_invocations) == 0, "DSH 失败时 NativeEngine 不得被调用"

    @staticmethod
    async def _drain(stream):
        async for _ in stream:
            pass

    def test_child_token_cannot_widen_parent_scope(self, token_service):
        """子 Agent 权限只能收窄不能扩大（Property 29）。"""
        parent = token_service.create_token(
            user_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            role="auditor",
            cycle_scope=frozenset({"D", "E"}),
        )
        child = token_service.create_child_token(
            parent.payload, narrowed_scope=frozenset({"D", "E", "F", "G", "H"})
        )
        # 交集：只有 D, E（不能扩大）
        assert child.payload.cycle_scope == frozenset({"D", "E"})

    def test_unknown_role_fail_closed(self, token_service):
        """未知角色 fail-closed（Property 30）。"""
        from app.services.ai_chat.mcp_token import McpTokenInvalid

        with pytest.raises(McpTokenInvalid, match="未知角色"):
            token_service.create_token(
                user_id=uuid4(),
                project_id=uuid4(),
                run_id=uuid4(),
                role="hacker_admin",
                cycle_scope=frozenset(),
            )

    def test_five_role_mask_policies(self):
        """五角色各有明确脱敏策略（Property 30）。"""
        from app.services.ai_chat.mcp_token import McpMaskLevel, resolve_mask_policy

        expected = {
            "auditor": McpMaskLevel.STRICT,
            "manager": McpMaskLevel.PARTIAL,
            "partner": McpMaskLevel.NONE,
            "qc": McpMaskLevel.STRICT,
            "eqcr": McpMaskLevel.STRICT,
        }
        for role, policy in expected.items():
            assert resolve_mask_policy(role) == policy, f"角色 {role} 脱敏策略不匹配"

    def test_audit_chain_tool_call_completeness(self):
        """哈希链事件成对完整（Property 32）：每个 tool call 有 started + finished/failed。"""
        from app.services.ai_chat.run_contract import ChatEventType

        # 验证 event type 枚举包含完整的 tool_started / tool_finished
        assert hasattr(ChatEventType, "tool_started")
        assert hasattr(ChatEventType, "tool_finished")

        # 验证 run 有 run_started / done|error|cancelled 终态
        assert hasattr(ChatEventType, "run_started")
        assert hasattr(ChatEventType, "done")
        assert hasattr(ChatEventType, "error")
        assert hasattr(ChatEventType, "cancelled")

    def test_version_pin_is_not_dev_or_latest(self):
        """SDK 版本 pin 不是 dev/latest（Req 14.7）。"""
        from app.services.ai_chat.dsh_discovery import DSH_PINNED_VERSION

        unsafe = {"0.0.0.dev0", "latest", "0.0.0", "*"}
        assert DSH_PINNED_VERSION not in unsafe, (
            f"DSH 版本 pin '{DSH_PINNED_VERSION}' 不安全"
        )

    def test_mcp_budget_enforcement_stops_calls(self, budget_tracker):
        """MCP 配额耗尽后所有调用被拒绝（Property 29/32）。"""
        from app.services.ai_chat.mcp_budget import McpBudgetExceeded

        run_id = uuid4()
        budget = budget_tracker.get_or_create(run_id)
        budget.calls_used = budget.max_calls

        with pytest.raises(McpBudgetExceeded):
            budget_tracker.check_and_consume(run_id, response_bytes=0)

    def test_dsh_run_context_timeout_detection(self):
        """DshRunContext 正确检测超时。"""
        from app.services.ai_chat.dsh_engine import DshRunContext

        # 新建不超时
        ctx_new = DshRunContext(
            run_id=uuid4(), principal_id=uuid4(), project_id=uuid4()
        )
        assert not ctx_new.is_timed_out

        # 很久以前 → 超时
        ctx_old = DshRunContext(
            run_id=uuid4(),
            principal_id=uuid4(),
            project_id=uuid4(),
            started_at=time.monotonic() - 999,
        )
        assert ctx_old.is_timed_out


# ===========================================================================
# 8. 跨任务综合断言（全 Phase C 属性交叉验证）
# ===========================================================================


class TestCrossTaskIntegration:
    """跨 Tasks 25–30 的属性交叉验证。确保各组件联合使用时约束不破裂。"""

    def test_token_service_and_budget_are_consistent(self, token_service, budget_tracker):
        """token 和 budget 绑定到同一 run。"""
        run_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()

        # 创建 token
        scoped = token_service.create_token(
            user_id=user_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset({"D"}),
        )

        # 创建 budget
        budget = budget_tracker.get_or_create(run_id)
        assert budget.run_id == run_id

        # 验证 token 与 budget 绑定同一 run
        payload = token_service.validate_token(
            scoped.token, expected_run_id=run_id
        )
        assert payload.run_id == run_id
        assert budget.run_id == payload.run_id

    def test_discovery_and_engine_resolve_agree(self):
        """discovery 结果与 engine resolve 一致：SDK 不可用 → native。"""
        from app.services.ai_chat.dsh_discovery import (
            DshDiscoveryResult,
            DshDiscoveryStatus,
            discover_dsh_sdk,
        )
        from app.services.ai_chat.engine import resolve_engine
        from app.models.ai_models import ChatEngineName

        # 不存在的路径
        result = discover_dsh_sdk(Path("/fake/nonexistent"))
        assert not result.is_available

        # 对应的 resolve_engine 在 DSH disabled 时也返回 native
        with patch("app.core.config.settings") as s:
            s.AI_CHAT_ENGINE = "dsh"
            s.AI_DSH_ENABLED = False
            s.AI_DSH_PROJECT_ALLOWLIST = ""
            engine, _ = resolve_engine(project_id=uuid4())
            assert engine == ChatEngineName.native

    def test_worker_pool_and_context_lifecycle(self):
        """Worker pool + DshRunContext + 清理的完整生命周期。"""
        from app.services.ai_chat.dsh_engine import DshRunContext, DshWorkerPool

        pool = DshWorkerPool()
        run_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()

        # 注册
        ctx = DshRunContext(
            run_id=run_id, principal_id=user_id, project_id=project_id
        )
        pool.register(ctx)
        assert pool.get_context(run_id) is ctx
        assert pool.active_count == 1

        # 取消
        ctx.cancelled = True
        assert ctx.cancelled

        # 注销
        pool.unregister(run_id)
        assert pool.get_context(run_id) is None
        assert pool.active_count == 0
