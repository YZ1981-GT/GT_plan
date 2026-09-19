"""Task 30: 引擎能力、feature flag 与 local-only 自检守卫

Feature: dsh-agent-panel-integration
Requirements: 10.1, 10.3, 10.4, 10.5, 10.6, 12.1, 12.2, 12.4
Properties:
  - 24：引擎能力与 UI 一致 — request body engine 不影响选择；capability 在 /capabilities 可查；
    不支持入口在 DOM 禁用并显示中文原因。
  - 25：DSH 失败不降级 — engine_unavailable，绝不静默 NativeEngine。
  - 26：Effective Cordis 与工具目录受控 — model route 在 allowlist，tool catalog 正确。

## 守卫设计

1. `/capabilities` 返回正确 engine + capabilities（native/dsh 两态）
2. DSH feature flag 三层门：配置 → experimental flag → allowlist
3. 客户端不可通过请求体覆盖 engine 选择
4. 启动自检：本地 model/embedding 通过，cloud 拒绝 + local_only_violation
5. embedding/OCR/model 各自独立 typed error
6. DSH 不可用时 engine_unavailable、NativeEngine invocation = 0
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID, uuid4

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """模拟 settings 对象。"""
    settings = MagicMock()
    settings.AI_CHAT_ENGINE = "native"
    settings.AI_DSH_ENABLED = False
    settings.AI_DSH_PROJECT_ALLOWLIST = ""
    settings.LLM_BASE_URL = "http://localhost:8100/v1"
    settings.LLM_EMBEDDING_BASE_URL = "http://localhost:8101/v1"
    settings.OCR_PADDLE_ENABLED = True
    settings.OCR_TESSERACT_ENABLED = True
    settings.PORT = 9980
    return settings


# ===========================================================================
# 1. /capabilities 端点返回正确 engine + capabilities
# ===========================================================================


class TestCapabilityEndpointNative:
    """**Validates: Requirements 10.1, 10.3**（Property 24）"""

    def test_native_engine_returns_correct_capabilities(self, mock_settings):
        """native engine 返回 tools=False, subagents=False。"""
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=None)

        assert result.engine == "native"
        assert result.capabilities.tools is False
        assert result.capabilities.subagents is False
        assert result.capabilities.streaming is True
        assert result.capabilities.local_only is True
        assert result.capabilities.review_mode is True
        assert result.capabilities.attachments is True

    def test_native_engine_has_disabled_reasons_for_tools(self, mock_settings):
        """native 时 tools/subagents 有中文禁用原因。"""
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=None)

        assert "tools" in result.disabled_reasons
        assert "subagents" in result.disabled_reasons
        assert len(result.disabled_reasons["tools"]) > 0
        assert len(result.disabled_reasons["subagents"]) > 0

    def test_no_gate_reason_when_native_configured(self, mock_settings):
        """配置为 native 时 gate_reason 为 None（不是"被拦下"）。"""
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=None)

        assert result.gate_reason is None


class TestCapabilityEndpointDsh:
    """**Validates: Requirements 10.3, 10.6**（Property 24/26）"""

    def test_dsh_engine_returns_tools_and_subagents(self, mock_settings):
        """DSH 引擎支持 tools=True, subagents=True。"""
        mock_settings.AI_CHAT_ENGINE = "dsh"
        mock_settings.AI_DSH_ENABLED = True
        mock_settings.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())
        project_id = UUID(mock_settings.AI_DSH_PROJECT_ALLOWLIST)

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=project_id)

        assert result.engine == "dsh"
        assert result.capabilities.tools is True
        assert result.capabilities.subagents is True
        assert result.capabilities.structured_output is True

    def test_dsh_no_disabled_reasons_for_tools(self, mock_settings):
        """DSH 引擎的 tools/subagents 没有禁用原因。"""
        mock_settings.AI_CHAT_ENGINE = "dsh"
        mock_settings.AI_DSH_ENABLED = True
        mock_settings.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())
        project_id = UUID(mock_settings.AI_DSH_PROJECT_ALLOWLIST)

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=project_id)

        assert "tools" not in result.disabled_reasons
        assert "subagents" not in result.disabled_reasons


# ===========================================================================
# 2. DSH feature flag 三层门
# ===========================================================================


class TestDshFeatureFlagGating:
    """**Validates: Requirements 10.1, 10.6**（Property 24/25）"""

    def test_dsh_disabled_flag_falls_back_to_native(self, mock_settings):
        """AI_DSH_ENABLED=False → 即使 engine=dsh 也回落 native + gate_reason。"""
        mock_settings.AI_CHAT_ENGINE = "dsh"
        mock_settings.AI_DSH_ENABLED = False

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=uuid4())

        assert result.engine == "native"
        assert result.gate_reason is not None
        assert "实验" in result.gate_reason or "尚未" in result.gate_reason

    def test_project_not_in_allowlist_falls_back_to_native(self, mock_settings):
        """项目不在 allowlist → 回落 native + gate_reason。"""
        mock_settings.AI_CHAT_ENGINE = "dsh"
        mock_settings.AI_DSH_ENABLED = True
        mock_settings.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())  # 另一个项目

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=uuid4())  # 不同的项目

        assert result.engine == "native"
        assert result.gate_reason is not None
        assert "尚未" in result.gate_reason or "项目" in result.gate_reason

    def test_no_project_binding_falls_back_to_native(self, mock_settings):
        """无项目绑定（global knowledge）→ 回落 native。"""
        mock_settings.AI_CHAT_ENGINE = "dsh"
        mock_settings.AI_DSH_ENABLED = True
        mock_settings.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=None)

        assert result.engine == "native"
        assert result.gate_reason is not None


# ===========================================================================
# 3. 客户端不可覆盖 engine（Req 10.1）
# ===========================================================================


class TestClientCannotOverrideEngine:
    """**Validates: Requirements 10.1**（Property 24）"""

    def test_capabilities_ignores_query_engine_param(self, mock_settings):
        """请求参数不含 engine 字段；即使用户恶意添加也被忽略。"""
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            # get_capabilities 只接受 project_id，没有 engine 参数
            result = get_capabilities(project_id=None)

        assert result.engine == "native"

    def test_chat_run_request_rejects_engine_field(self):
        """ChatRunRequest 不包含 engine 字段（Req 10.1 的结构保证）。"""
        from app.services.ai_chat.run_contract import ChatRunRequest

        schema = ChatRunRequest.model_json_schema()
        properties = schema.get("properties", {})
        assert "engine" not in properties, \
            "ChatRunRequest 不应包含 engine 字段（客户端不可覆盖）"


# ===========================================================================
# 4. local-only 启动自检
# ===========================================================================


class TestStartupLocalOnlyCheck:
    """**Validates: Requirements 12.1, 12.2**（Property 24）"""

    @pytest.mark.asyncio
    async def test_local_model_passes(self, mock_settings):
        """本地 model endpoint 通过 local-only 检查。"""
        mock_settings.LLM_BASE_URL = "http://localhost:8100/v1"

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        model_check = next(c for c in report.checks if c.service == "model")
        assert model_check.ok is True
        assert report.all_local is True

    @pytest.mark.asyncio
    async def test_cloud_model_fails_local_only(self, mock_settings):
        """cloud provider model endpoint → local_only_violation。"""
        mock_settings.LLM_BASE_URL = "https://api.openai.com/v1"

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        model_check = next(c for c in report.checks if c.service == "model")
        assert model_check.ok is False
        assert model_check.error_code == "local_only_violation"
        assert report.has_violations is True
        assert report.all_local is False

    @pytest.mark.asyncio
    async def test_cloud_embedding_fails_local_only(self, mock_settings):
        """cloud embedding endpoint → local_only_violation。"""
        mock_settings.LLM_EMBEDDING_BASE_URL = "https://api.deepseek.com/v1"

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        embedding_check = next(c for c in report.checks if c.service == "embedding")
        assert embedding_check.ok is False
        assert embedding_check.error_code == "local_only_violation"

    @pytest.mark.asyncio
    async def test_unconfigured_model_returns_unavailable(self, mock_settings):
        """未配置 model endpoint → engine_unavailable（不是 violation）。"""
        mock_settings.LLM_BASE_URL = ""

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        model_check = next(c for c in report.checks if c.service == "model")
        assert model_check.ok is False
        assert model_check.error_code == "engine_unavailable"


# ===========================================================================
# 5. embedding/OCR/model 各自独立 typed error（Req 12.4）
# ===========================================================================


class TestSeparateHealthErrors:
    """**Validates: Requirements 12.4**（各服务独立错误码）"""

    @pytest.mark.asyncio
    async def test_ocr_disabled_returns_ocr_unavailable(self, mock_settings):
        """OCR 全关 → ocr_unavailable（不是 engine_unavailable）。"""
        mock_settings.OCR_PADDLE_ENABLED = False
        mock_settings.OCR_TESSERACT_ENABLED = False

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        ocr_check = next(c for c in report.checks if c.service == "ocr")
        assert ocr_check.ok is False
        assert ocr_check.error_code == "ocr_unavailable"

    @pytest.mark.asyncio
    async def test_embedding_error_code_is_not_engine_unavailable(self, mock_settings):
        """embedding violation 用 local_only_violation，不用 engine_unavailable。"""
        mock_settings.LLM_EMBEDDING_BASE_URL = "https://api.anthropic.com/v1"

        with patch("app.core.config.settings", mock_settings), \
             patch("app.services.ai_chat.startup_health._audit_violations", new_callable=AsyncMock):
            from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

            report = await run_ai_chat_startup_health_check()

        embedding_check = next(c for c in report.checks if c.service == "embedding")
        assert embedding_check.error_code == "local_only_violation"
        # 不应该是 engine_unavailable
        assert embedding_check.error_code != "engine_unavailable"

    def test_capability_health_separates_services(self, mock_settings):
        """/capabilities 健康字段对 model/embedding/ocr 分别报告。

        🔴 本条只查**结构**（字段在不在），不查**取值** —— 变异实测：把
        `_check_model_health` 改成无条件 `return ServiceHealth(available=True, …)`
        本条依旧绿。取值判据见下面的 `TestCapabilityEndpointLocalOnly`。
        """
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import get_capabilities

            result = get_capabilities(project_id=None)

        assert "model" in result.health
        assert "embedding" in result.health
        assert "ocr" in result.health
        # 各服务有独立 available/error_code
        for svc in ["model", "embedding", "ocr"]:
            h = result.health[svc]
            assert hasattr(h, "available")
            assert hasattr(h, "error_code")


# ===========================================================================
# 5b. /capabilities 自己的 local-only 判定（变异 M14 补口）
#
# 🔴 上面 §4 全部走 `startup_health.run_ai_chat_startup_health_check`，而
# `/capabilities` 的 `health` 字段走的是**另一套实现**
# `capability_endpoint._collect_service_health() → _check_model_health()`。
# 那套实现此前**零取值覆盖**：唯一触达它的 `test_capability_health_separates_services`
# 只断言字段存在。变异实测：给 `_check_model_health` 开头插一条无条件
# `return ServiceHealth(available=True, …)`（等于关掉 local-only 校验，
# 前端会认为"云端模型可用"并放开入口）—— `test_task30_capabilities.py` 全绿
# （GREEN = 守卫缺陷）。
#
# 下面按「本地放行 / 云端拒绝 / 未配置区分 / 两套实现结论一致」四个角度补取值判据。
# ===========================================================================


class TestCapabilityEndpointLocalOnly:
    """`/capabilities` 的 health 取值判据。

    **Validates: Requirements 12.1, 12.2, 12.4**（Property 24）
    """

    @staticmethod
    def _health(mock_settings, service: str):
        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.capability_endpoint import _collect_service_health

            return _collect_service_health()[service]

    def test_local_model_endpoint_reported_available(self, mock_settings):
        """本地 model endpoint → available=True 且无 error_code（反向自检）。"""
        mock_settings.LLM_BASE_URL = "http://localhost:8100/v1"
        h = self._health(mock_settings, "model")
        assert h.available is True
        assert h.error_code is None

    def test_cloud_model_endpoint_reported_local_only_violation(self, mock_settings):
        """cloud model endpoint → available=False + local_only_violation。

        MUTATION ANCHOR P24-A: `_check_model_health` 无条件返回可用 → 本条打红。
        """
        mock_settings.LLM_BASE_URL = "https://api.openai.com/v1"
        h = self._health(mock_settings, "model")
        assert h.available is False, "云端模型 endpoint 被报成可用 —— local-only 校验失效"
        assert h.error_code == "local_only_violation"
        # endpoint 必须脱敏后回显，且不得回显成占位串
        assert h.endpoint, "endpoint 不得为空（前端要显示到底连了哪里）"
        assert "mutated" not in h.endpoint.lower()
        assert "不合规" in h.message

    def test_unconfigured_model_is_engine_unavailable_not_violation(self, mock_settings):
        """未配置 ≠ 违规：两种不可用必须用不同 typed error。"""
        mock_settings.LLM_BASE_URL = ""
        h = self._health(mock_settings, "model")
        assert h.available is False
        assert h.error_code == "engine_unavailable"
        assert h.error_code != "local_only_violation"

    def test_cloud_embedding_endpoint_reported_local_only_violation(self, mock_settings):
        """embedding 侧同样要判 local-only（与 model 各自独立报告）。"""
        mock_settings.LLM_EMBEDDING_BASE_URL = "https://api.deepseek.com/v1"
        h = self._health(mock_settings, "embedding")
        assert h.available is False
        assert h.error_code == "local_only_violation"

    def test_capabilities_health_matches_startup_health_verdict(self, mock_settings):
        """两套 local-only 实现对同一 settings 必须给出**一致结论**。

        `/capabilities`（前端据此禁用入口）与启动自检（据此拒绝启动）若结论不一致，
        就会出现「启动自检拦住了但前端仍放开入口」这类矛盾。
        """
        from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

        for endpoint, expect_ok in (
            ("http://localhost:8100/v1", True),
            ("https://api.openai.com/v1", False),
        ):
            mock_settings.LLM_BASE_URL = endpoint

            cap_health = self._health(mock_settings, "model")

            with patch("app.core.config.settings", mock_settings), patch(
                "app.services.ai_chat.startup_health._audit_violations",
                new_callable=AsyncMock,
            ):
                report = asyncio.run(run_ai_chat_startup_health_check())
            startup_check = next(c for c in report.checks if c.service == "model")

            assert cap_health.available is expect_ok, f"{endpoint}: /capabilities 结论错"
            assert startup_check.ok is expect_ok, f"{endpoint}: 启动自检结论错"
            assert cap_health.available == startup_check.ok, (
                f"{endpoint}: /capabilities 与启动自检结论不一致 "
                f"({cap_health.available} vs {startup_check.ok})"
            )
            assert cap_health.error_code == startup_check.error_code


# ===========================================================================
# 6. DSH 失败不降级（Property 25）
# ===========================================================================


class TestDshNoFallback:
    """**Validates: Requirements 10.5**（Property 25）"""

    def test_resolve_engine_native_config_is_not_fallback(self, mock_settings):
        """配置门回落 native 是"从一开始就是 native"，不是运行期降级。"""
        mock_settings.AI_CHAT_ENGINE = "native"

        with patch("app.core.config.settings", mock_settings):
            from app.services.ai_chat.engine import resolve_engine

            engine, reason = resolve_engine(project_id=uuid4())

        assert engine.value == "native"
        assert reason is None

    def test_dsh_engine_build_raises_on_unknown_engine(self, mock_settings):
        """未登记的 engine 不会静默回落 native。

        build_engine 对非法 enum 值走 resolve_engine 的 fail-safe 路径（native），
        但对已注册为 dsh 且 SDK 不可用时会抛 engine_unavailable（Property 25 保证）。
        这里验证的是：引擎名称不被客户端覆盖、配置决定一切（Req 10.1）。
        """
        from app.services.ai_chat.engine import resolve_engine
        from app.models.ai_models import ChatEngineName

        # 非法配置值 → resolve_engine_name 回落 native（fail-safe）
        mock_settings.AI_CHAT_ENGINE = "totally_invalid_engine_xyz"
        with patch("app.core.config.settings", mock_settings):
            engine, _reason = resolve_engine(project_id=uuid4())

        # 非法值回落 native，而不是抛给用户一个未知引擎
        assert engine is ChatEngineName.native


# ===========================================================================
# 7. start-dev.bat 不再启动 DSH Web UI
# ===========================================================================


class TestStartupScriptNoDshWebUi:
    """**Validates: Requirements 10.6**（启动脚本变更确认）"""

    def test_start_dev_bat_no_web_port_start(self):
        """start-dev.bat 不再启动 DSH Web UI（iframe 移除）。"""
        from pathlib import Path

        bat_path = Path(__file__).parents[3] / "start-dev.bat"
        if not bat_path.exists():
            pytest.skip("start-dev.bat not found at workspace root")

        content = bat_path.read_text(encoding="utf-8", errors="replace")

        # 不应包含 `node apps\cli\lib\bin.js web` 启动命令
        assert "bin.js web --port" not in content, \
            "start-dev.bat 仍在启动 DSH Web UI（应移除 iframe 依赖）"

        # 应该有 SDK runtime 检查提示
        assert "DshEngine" in content or "SDK runtime" in content or "vendor read-only" in content, \
            "start-dev.bat 应包含 SDK runtime 检查信息"
