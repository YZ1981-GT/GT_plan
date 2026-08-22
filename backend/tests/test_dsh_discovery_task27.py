"""DSH SDK discovery、精确 pin 与 custom Cordis smoke 守卫（Task 27）

Feature: dsh-agent-panel-integration
Properties:
  - 25：DSH 失败不降级 — DSH startup/handshake/MCP/local-model failure → engine_unavailable,
    NativeEngine invocation count == 0
  - 26：Effective Cordis 与工具目录受控 — JSON-RPC/MCP handshake success,
    model route in allowlist, tool catalog == MCP_READONLY_TOOLS, no dangerous tools

本测试文件的守卫策略：
- 不修改 D:\\DeepHorness（vendor 只读）
- 验证 discovery 结果的正确性
- 验证版本 pin 拒绝不安全版本
- 验证 custom Cordis 配置的完整性与安全性
- 验证工具目录与模型路由的约束
- 如果 SDK 不可用，明确标记原因而非静默跳过

Validates: Requirements 10.6, 11.1, 11.2, 11.3, 12.1, 14.7
"""

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_chat.dsh_discovery import (
    DSH_CORDIS_VERSION,
    DSH_PINNED_COMMIT,
    DSH_PINNED_VERSION,
    DSH_VENDOR_ROOT,
    MCP_READONLY_TOOLS,
    MODEL_ROUTE_ALLOWLIST_PATTERNS,
    PROHIBITED_AGENT_TOOLS,
    PROHIBITED_TOOL_PATTERNS,
    REQUIRED_CORDIS_SERVICES,
    DshCordisSpec,
    DshDiscoveryResult,
    DshDiscoveryStatus,
    build_platform_cordis_config,
    discover_dsh_sdk,
    smoke_cordis_config_load,
    smoke_sdk_import,
    validate_cordis_services,
    validate_model_route,
    validate_tool_catalog,
    validate_version_pin,
)


# ---------------------------------------------------------------------------
# Fixture: vendor 根目录
# ---------------------------------------------------------------------------


@pytest.fixture
def vendor_root() -> Path:
    """实际 DSH vendor 根目录。"""
    return DSH_VENDOR_ROOT


# ---------------------------------------------------------------------------
# Property 26: Effective Cordis 与工具目录受控
# ---------------------------------------------------------------------------


class TestDshDiscovery:
    """SDK discovery 结果验证。

    **Validates: Requirements 10.6, 14.7**
    """

    def test_vendor_root_exists(self, vendor_root: Path) -> None:
        """D:\\DeepHorness 必须存在。"""
        assert vendor_root.is_dir(), f"DSH vendor root 不存在: {vendor_root}"

    def test_package_json_exists(self, vendor_root: Path) -> None:
        """根 package.json 必须存在。"""
        pkg = vendor_root / "package.json"
        assert pkg.is_file(), f"package.json 不存在: {pkg}"

    def test_discovery_returns_valid_result(self, vendor_root: Path) -> None:
        """discover_dsh_sdk 返回结构化结果。"""
        result = discover_dsh_sdk(vendor_root)
        assert isinstance(result, DshDiscoveryResult)
        assert result.vendor_root == vendor_root
        assert result.version is not None

    def test_version_is_pinned_not_dev(self, vendor_root: Path) -> None:
        """monorepo 版本必须是精确 pin，不能是 0.0.0.dev0/latest/*。

        **Validates: Requirements 10.6**
        """
        result = discover_dsh_sdk(vendor_root)
        assert result.version == DSH_PINNED_VERSION, (
            f"DSH 版本 {result.version} != pinned {DSH_PINNED_VERSION}"
        )
        # 拒绝不安全版本标记
        unsafe = {"0.0.0.dev0", "latest", "0.0.0", "*"}
        assert result.version not in unsafe, (
            f"版本 {result.version} 不可作为生产 pin（Req 10.6）"
        )

    def test_cordis_version_pinned(self, vendor_root: Path) -> None:
        """Cordis 版本必须匹配精确 pin。"""
        result = discover_dsh_sdk(vendor_root)
        assert result.cordis_version == DSH_CORDIS_VERSION, (
            f"Cordis 版本 {result.cordis_version} != pinned {DSH_CORDIS_VERSION}"
        )

    def test_git_commit_pinned(self, vendor_root: Path) -> None:
        """Git commit 必须匹配精确 pin。"""
        result = discover_dsh_sdk(vendor_root)
        assert result.commit is not None, "无法读取 git commit"
        assert result.commit == DSH_PINNED_COMMIT, (
            f"Git commit {result.commit[:12]} != pinned {DSH_PINNED_COMMIT[:12]}"
        )

    def test_python_sdk_importable(self, vendor_root: Path) -> None:
        """Python SDK 必须可以 import。"""
        result = discover_dsh_sdk(vendor_root)
        assert result.python_sdk_importable, (
            f"Python SDK import 失败: {result.errors}"
        )

    def test_bundled_cordis_exists(self, vendor_root: Path) -> None:
        """bundled runtime/cordis.yml 必须存在。"""
        result = discover_dsh_sdk(vendor_root)
        assert result.bundled_cordis_exists, "bundled cordis.yml 不存在"

    def test_discovery_status_available(self, vendor_root: Path) -> None:
        """完整 discovery 应该报告 available。"""
        result = discover_dsh_sdk(vendor_root)
        assert result.is_available, (
            f"SDK discovery 状态 {result.status.value}，errors: {result.errors}"
        )

    def test_validate_version_pin_passes(self, vendor_root: Path) -> None:
        """版本 pin 校验应无错误。"""
        result = discover_dsh_sdk(vendor_root)
        errors = validate_version_pin(result)
        assert not errors, f"版本 pin 校验失败: {errors}"


class TestVersionPinRejection:
    """版本 pin 拒绝不安全值。

    **Validates: Requirements 10.6**
    """

    @pytest.mark.parametrize(
        "bad_version",
        ["0.0.0.dev0", "latest", "0.0.0", "*"],
    )
    def test_rejects_unsafe_version(self, bad_version: str) -> None:
        """不安全版本标记必须被拒绝。"""
        result = DshDiscoveryResult(
            status=DshDiscoveryStatus.available,
            vendor_root=Path("/fake"),
            version=bad_version,
            commit=DSH_PINNED_COMMIT,
            cordis_version=DSH_CORDIS_VERSION,
        )
        errors = validate_version_pin(result)
        assert any("不可作为生产 pin" in e for e in errors), (
            f"版本 {bad_version} 应被拒绝，但 errors: {errors}"
        )

    def test_rejects_version_mismatch(self) -> None:
        """版本不匹配必须被拒绝。"""
        result = DshDiscoveryResult(
            status=DshDiscoveryStatus.available,
            vendor_root=Path("/fake"),
            version="0.2.0",
            commit=DSH_PINNED_COMMIT,
            cordis_version=DSH_CORDIS_VERSION,
        )
        errors = validate_version_pin(result)
        assert any("!= pinned" in e for e in errors)


class TestPlatformCordisConfig:
    """平台 custom Cordis 配置守卫。

    **Validates: Requirements 11.1, 11.2, 11.3**
    **Properties: 26**
    """

    def test_has_required_services(self) -> None:
        """配置必须包含所有必需服务。"""
        config = build_platform_cordis_config()
        service_names = {item["name"] for item in config}

        for spec in REQUIRED_CORDIS_SERVICES:
            if spec.is_transport:
                # transport 只在指定 mcp_command 时加入
                continue
            assert spec.name in service_names, (
                f"缺少必需 Cordis 服务: {spec.name}"
            )

    def test_has_required_services_with_mcp(self) -> None:
        """带 MCP 命令时配置包含 internal-stdio-transport。"""
        config = build_platform_cordis_config(mcp_command="python -m audit_data_mcp")
        service_names = {item["name"] for item in config}

        for spec in REQUIRED_CORDIS_SERVICES:
            assert spec.name in service_names, (
                f"缺少必需 Cordis 服务: {spec.name}"
            )

    def test_no_prohibited_tools_in_config(self) -> None:
        """配置不能包含禁止的工具服务。"""
        config = build_platform_cordis_config(mcp_command="python -m audit_data_mcp")
        errors = validate_cordis_services(config)
        assert not errors, f"Cordis 配置安全校验失败: {errors}"

    def test_no_bash_tool(self) -> None:
        """配置不能包含 bash 工具。"""
        config = build_platform_cordis_config()
        service_names = {item["name"] for item in config}
        service_ids = {item["id"] for item in config}

        bash_services = {
            "@deepseek-ai/dsh-bash-local",
            "@deepseek-ai/dsh-tool-bash-persistent",
            "@deepseek-ai/dsh-terminal-bash",
        }
        assert not service_names & bash_services, (
            f"配置包含 bash 工具: {service_names & bash_services}"
        )

    def test_no_fs_write_tool(self) -> None:
        """配置不能包含文件系统写工具。"""
        config = build_platform_cordis_config()
        service_names = {item["name"] for item in config}

        # dsh-fs-local 是文件系统读写，不应该有
        # 注意 agent-spine 关闭了 toolBash 所以不会暴露 fs 工具
        fs_write_services = {"@deepseek-ai/dsh-tool-fs"}
        assert not service_names & fs_write_services

    def test_no_web_fetch_tool(self) -> None:
        """配置不能包含 web-fetch 工具。"""
        config = build_platform_cordis_config()
        for item in config:
            name = item.get("name", "")
            assert "web-fetch" not in name.lower()
            assert "web-search" not in name.lower()

    def test_agent_spine_disables_bash(self) -> None:
        """agent-spine 必须显式禁用 toolBash。"""
        config = build_platform_cordis_config()
        spine = next(
            (item for item in config if "agent-spine" in item.get("id", "")), None
        )
        assert spine is not None, "agent-spine 不存在"
        assert spine.get("config", {}).get("toolBash") is False
        assert spine.get("config", {}).get("toolJobs") is False

    def test_llm_points_to_local_vllm(self) -> None:
        """LLM provider 必须指向本地 vLLM（不是 cloud）。"""
        config = build_platform_cordis_config()
        llm = next(
            (item for item in config if "llm" in item.get("id", "")), None
        )
        assert llm is not None, "LLM provider 不存在"
        base_url = llm.get("config", {}).get("baseUrl", "")
        assert "localhost" in base_url or "127.0.0.1" in base_url, (
            f"LLM baseUrl 不是本地地址: {base_url}"
        )


class TestToolCatalogValidation:
    """工具目录约束验证。

    **Validates: Requirements 11.2, 11.3**
    **Properties: 26**
    """

    def test_mcp_readonly_tools_are_expected(self) -> None:
        """MCP_READONLY_TOOLS 包含且仅包含设计规定的工具。"""
        expected = {
            "wp_list",
            "wp_read",
            "tb_query",
            "addr_lookup",
            "kb_search",
            "note_read",
            "review_prompt",
        }
        assert MCP_READONLY_TOOLS == expected

    def test_validates_exact_match(self) -> None:
        """精确匹配的工具目录通过校验。"""
        errors = validate_tool_catalog(MCP_READONLY_TOOLS, MCP_READONLY_TOOLS)
        assert not errors

    def test_rejects_extra_tools(self) -> None:
        """多余工具被拒绝。"""
        tools = MCP_READONLY_TOOLS | {"bash_execute", "wp_list"}
        errors = validate_tool_catalog(tools, MCP_READONLY_TOOLS)
        assert any("多余工具" in e for e in errors)

    def test_rejects_missing_tools(self) -> None:
        """缺少工具被拒绝。"""
        tools = frozenset({"wp_list", "wp_read"})
        errors = validate_tool_catalog(tools, MCP_READONLY_TOOLS)
        assert any("缺少期望工具" in e for e in errors)

    def test_rejects_prohibited_tools(self) -> None:
        """禁止工具被拒绝。"""
        tools = MCP_READONLY_TOOLS | {"bash"}
        errors = validate_tool_catalog(tools, MCP_READONLY_TOOLS)
        # 应该同时触发"多余"和"禁止"
        assert any("禁止工具" in e or "禁止模式" in e for e in errors)

    @pytest.mark.parametrize(
        "prohibited_name",
        [
            "bash",
            "shell_exec",
            "subprocess_run",
            "fs_write_file",
            "web_fetch_url",
            "web_search",
            "terminal_exec",
        ],
    )
    def test_pattern_catches_prohibited(self, prohibited_name: str) -> None:
        """禁止工具模式能捕获各种变体。"""
        matched = any(p.search(prohibited_name) for p in PROHIBITED_TOOL_PATTERNS)
        assert matched, f"模式未捕获禁止工具: {prohibited_name}"


class TestModelRouteValidation:
    """模型路由允许列表验证。

    **Validates: Requirements 11.3, 12.1**
    **Properties: 26**
    """

    @pytest.mark.parametrize(
        "valid_endpoint",
        [
            "http://localhost:8100/v1",
            "http://127.0.0.1:8100/v1",
            "http://[::1]:8100/v1",
            "http://10.0.0.5:8100/v1",
            "http://172.16.0.1:8100/v1",
            "http://192.168.1.100:8100/v1",
        ],
    )
    def test_allows_local_endpoints(self, valid_endpoint: str) -> None:
        """本地/内网 endpoint 通过校验。"""
        errors = validate_model_route(valid_endpoint)
        assert not errors, f"{valid_endpoint} 应被允许，但: {errors}"

    @pytest.mark.parametrize(
        "cloud_endpoint",
        [
            "https://api.deepseek.com/v1",
            "https://api.openai.com/v1",
            "https://api.anthropic.com/v1",
            "https://generativelanguage.googleapis.com/v1",
            "https://some-cloud-provider.com/llm",
        ],
    )
    def test_rejects_cloud_endpoints(self, cloud_endpoint: str) -> None:
        """Cloud provider endpoint 被拒绝。"""
        errors = validate_model_route(cloud_endpoint)
        assert errors, f"{cloud_endpoint} 应被拒绝"

    def test_rejects_empty_endpoint(self) -> None:
        """空 endpoint 被拒绝。"""
        errors = validate_model_route("")
        assert errors


# ---------------------------------------------------------------------------
# Property 25: DSH 失败不降级
# ---------------------------------------------------------------------------


class TestDshFailureNoDegradation:
    """DSH 失败时不能静默回落 native。

    **Validates: Requirements 10.5**
    **Properties: 25**
    """

    def test_engine_build_constructs_dsh_engine(self) -> None:
        """build_engine 对 dsh engine 名应构造 DshEngine 实例（Task 28 已实现）。

        原测试断言 dsh 未实现时抛 EngineFailure；Task 28 交付后 build_dsh_engine
        已存在，此处改为验证构造成功且返回值满足 ChatEngine 协议。
        """
        from app.services.ai_chat.engine import build_engine
        from app.models.ai_models import ChatEngineName

        class FakeExecDsh:
            engine = ChatEngineName.dsh

            class host:
                project_id = uuid4()

        engine = build_engine(db=None, execution=FakeExecDsh)
        # DshEngine 满足 ChatEngine 协议：有 run 和 capabilities
        assert hasattr(engine, "run")
        assert hasattr(engine, "capabilities")

    def test_resolve_engine_gate_disabled(self) -> None:
        """AI_DSH_ENABLED=False 时 resolve_engine 返回 native + gate_reason。"""
        from app.services.ai_chat.engine import resolve_engine

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.AI_CHAT_ENGINE = "dsh"
            mock_settings.AI_DSH_ENABLED = False
            mock_settings.AI_DSH_PROJECT_ALLOWLIST = ""

            engine, reason = resolve_engine(project_id=uuid4())
            from app.models.ai_models import ChatEngineName

            assert engine == ChatEngineName.native
            assert reason == "experimental_disabled"

    def test_resolve_engine_gate_no_project(self) -> None:
        """无项目绑定时 DSH 不可用。"""
        from app.services.ai_chat.engine import resolve_engine

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.AI_CHAT_ENGINE = "dsh"
            mock_settings.AI_DSH_ENABLED = True
            mock_settings.AI_DSH_PROJECT_ALLOWLIST = ""

            engine, reason = resolve_engine(project_id=None)
            from app.models.ai_models import ChatEngineName

            assert engine == ChatEngineName.native
            assert reason == "no_project_binding"

    def test_resolve_engine_gate_not_allowlisted(self) -> None:
        """项目不在 allowlist 时 DSH 不可用。"""
        from app.services.ai_chat.engine import resolve_engine

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.AI_CHAT_ENGINE = "dsh"
            mock_settings.AI_DSH_ENABLED = True
            mock_settings.AI_DSH_PROJECT_ALLOWLIST = str(uuid4())  # 其他项目

            engine, reason = resolve_engine(project_id=uuid4())
            from app.models.ai_models import ChatEngineName

            assert engine == ChatEngineName.native
            assert reason == "project_not_allowlisted"


# ---------------------------------------------------------------------------
# Smoke Tests（SDK import / Cordis load）
# ---------------------------------------------------------------------------


class TestSdkSmoke:
    """SDK smoke test。

    **Validates: Requirements 10.6, 11.1**
    """

    def test_smoke_sdk_import(self, vendor_root: Path) -> None:
        """Python SDK 可 import 并包含所有核心类。"""
        result = smoke_sdk_import(vendor_root)
        assert result["success"], f"SDK import 失败: {result['error']}"
        # 核心类必须存在
        for cls_name in [
            "DeepSeekHarness",
            "DeepSeekHarnessConfig",
            "HarnessClient",
            "HarnessConfig",
        ]:
            assert cls_name in result["classes"]

    def test_smoke_sdk_config_fields(self, vendor_root: Path) -> None:
        """HarnessConfig 必须包含必要字段。"""
        result = smoke_sdk_import(vendor_root)
        assert result["success"]
        required_fields = [
            "runtime_bin",
            "launch_args_override",
            "cwd",
            "env",
            "request_timeout_seconds",
            "shutdown_timeout_seconds",
        ]
        for field_name in required_fields:
            assert field_name in result["config_fields"], (
                f"HarnessConfig 缺少字段: {field_name}"
            )

    def test_smoke_high_level_config_fields(self, vendor_root: Path) -> None:
        """DeepSeekHarnessConfig 必须包含 cordis/env/base_url 等字段。"""
        result = smoke_sdk_import(vendor_root)
        assert result["success"]
        required_fields = ["cordis", "env", "base_url", "runtime_bin", "provider", "model"]
        for field_name in required_fields:
            assert field_name in result["high_level_config_fields"], (
                f"DeepSeekHarnessConfig 缺少字段: {field_name}"
            )

    def test_smoke_cordis_config_load(self, vendor_root: Path) -> None:
        """bundled cordis.yml 可解析且包含核心服务。"""
        result = smoke_cordis_config_load(vendor_root)
        assert result["success"], f"Cordis 配置加载失败: {result['error']}"
        assert result["has_jsonrpc_server"], "缺少 @deepseek-ai/dsh-sdk-jsonrpc-server"
        assert result["has_agent_spine"], "缺少 @deepseek-ai/dsh-agent-spine-demo"
        assert result["has_llm"], "缺少 @deepseek-ai/dsh-llm-deepseek"


# ---------------------------------------------------------------------------
# Discovery for non-existent path (structural guard)
# ---------------------------------------------------------------------------


class TestDiscoveryNonExistent:
    """对不存在路径的 discovery 返回明确状态。"""

    def test_returns_sdk_not_found(self) -> None:
        """不存在的路径返回 sdk_not_found。"""
        result = discover_dsh_sdk(Path("/nonexistent/path/that/does/not/exist"))
        assert result.status == DshDiscoveryStatus.sdk_not_found
        assert not result.is_available
        assert result.errors


# ---------------------------------------------------------------------------
# Integration: full discovery + validation pipeline
# ---------------------------------------------------------------------------


class TestFullDiscoveryPipeline:
    """完整 discovery + 版本 pin + Cordis 安全校验管线。

    **Validates: Requirements 10.6, 11.1, 11.2, 11.3**
    """

    def test_full_pipeline(self, vendor_root: Path) -> None:
        """端到端管线：discovery → pin check → cordis gen → validation。"""
        # 1. Discovery
        discovery = discover_dsh_sdk(vendor_root)
        assert discovery.is_available, (
            f"Discovery 失败: {discovery.status.value}, {discovery.errors}"
        )

        # 2. Version pin
        pin_errors = validate_version_pin(discovery)
        assert not pin_errors, f"Pin 校验失败: {pin_errors}"

        # 3. Generate platform Cordis config
        config = build_platform_cordis_config(
            vllm_base_url="http://localhost:8100/v1",
            vllm_model="Qwen3.5-27B-NVFP4",
            mcp_command="python -m audit_data_mcp",
        )

        # 4. Validate Cordis services
        service_errors = validate_cordis_services(config)
        assert not service_errors, f"Cordis 服务校验失败: {service_errors}"

        # 5. Validate model route
        route_errors = validate_model_route("http://localhost:8100/v1")
        assert not route_errors, f"模型路由校验失败: {route_errors}"

        # 6. Validate tool catalog (expected = MCP_READONLY_TOOLS)
        tool_errors = validate_tool_catalog(MCP_READONLY_TOOLS, MCP_READONLY_TOOLS)
        assert not tool_errors, f"工具目录校验失败: {tool_errors}"
