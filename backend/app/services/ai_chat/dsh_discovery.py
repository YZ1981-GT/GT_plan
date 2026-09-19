"""DSH SDK discovery、精确 pin 与 custom Cordis smoke（Task 27）

Feature: dsh-agent-panel-integration
Requirements:
  - 10.6：实施前先完成 SDK discovery：验证实际安装 artifact、版本/commit/hash、Python import、
    配置 schema 和 JSON-RPC handshake，再将兼容版本精确 pin 到平台依赖；
    ``0.0.0.dev0`` 或 ``latest`` 不可作为生产 pin。
  - 11.1：custom Cordis 的最小组成与安全约束。
  - 11.2：禁止注册为 Agent 工具的名单。
  - 11.3：启动自检读取 *effective* 状态（model route / tool catalog）。
  - 12.1：只在运行时验收通过后启用 DSH。
  - 14.7：``D:\\DeepHorness`` 保持 vendor 只读；不修改上游源码。
Design: "Components and Interfaces → 13. DSH Custom Cordis and MCP"
Properties: 25（DSH 失败不降级）、26（Effective Cordis 与工具目录受控）

## 概述

本模块负责：
1. 发现并验证 ``D:\\DeepHorness`` SDK 安装状态
2. 验证 artifact 版本/commit/hash 并精确 pin
3. 产出 custom Cordis 配置（仅限平台所需的最小安全组成）
4. 提供 smoke 验证函数（import → Cordis load → JSON-RPC handshake → MCP handshake）
5. 输出并断言 effective model route / tool catalog

所有验证均为**只读**：不修改 ``D:\\DeepHorness`` 下任何文件。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DSH_VENDOR_ROOT",
    "DSH_PINNED_VERSION",
    "DSH_PINNED_COMMIT",
    "DSH_CORDIS_VERSION",
    "DshDiscoveryStatus",
    "DshDiscoveryResult",
    "DshCordisSpec",
    "REQUIRED_CORDIS_SERVICES",
    "PROHIBITED_AGENT_TOOLS",
    "MCP_READONLY_TOOLS",
    "MODEL_ROUTE_ALLOWLIST_PATTERNS",
    "discover_dsh_sdk",
    "validate_version_pin",
    "build_platform_cordis_config",
    "validate_cordis_services",
    "validate_tool_catalog",
    "validate_model_route",
]


# ---------------------------------------------------------------------------
# 精确 Pin：版本/commit 锚定（Req 10.6）
# ---------------------------------------------------------------------------

#: vendor 根目录——只读，绝不修改
DSH_VENDOR_ROOT = Path(os.environ.get("DSH_VENDOR_ROOT", r"D:\DeepHorness"))

#: 精确 pin 的 monorepo 版本（root package.json::version）
#: 🔴 不接受 0.0.0.dev0 / latest / *
DSH_PINNED_VERSION = "0.1.0-rc.8"

#: 精确 pin 的 git commit SHA（长哈希）
DSH_PINNED_COMMIT = "9a226f1077b782fc13de6aa0cdcb3c2295eadaff"

#: vendor/cordis 的精确版本
DSH_CORDIS_VERSION = "4.0.1"

#: Python SDK 的预期包名与 dev 版本标记
#: 注意：Python SDK 使用 0.0.0.dev0 因为是 editable 开发安装（pyproject.toml 明确），
#: 而 npm packages 使用 0.1.0-rc.8。这不是"未 pin"，是 dev 安装与发布版本的区分。
#: 我们以 **npm monorepo 版本 + git commit** 作为精确锚点。
DSH_PYTHON_SDK_PACKAGE = "deepseek-harness-sdk"
DSH_PYTHON_SDK_DEV_VERSION = "0.0.0.dev0"


# ---------------------------------------------------------------------------
# 禁止的 Agent 工具（Design §13：禁止注册为 Agent 工具）
# ---------------------------------------------------------------------------

#: 绝对禁止出现在 Agent tool catalog 中的工具名/模式
PROHIBITED_AGENT_TOOLS: frozenset[str] = frozenset(
    {
        # filesystem write
        "dsh-tool-fs",
        "dsh-fs-local",
        "fs-local",
        "tool-fs",
        # bash/shell/subprocess
        "dsh-bash-local",
        "dsh-tool-bash-persistent",
        "bash",
        "terminal-bash",
        "dsh-terminal-bash",
        "dsh-terminal",
        # subprocess command
        "dsh-subprocess-local",
        "subprocess",
        # web fetch / external search
        "web-fetch",
        "web-search",
        "dsh-tool-web-fetch",
        "dsh-tool-web-search",
    }
)

#: 禁止工具名匹配的正则模式（更宽泛的安全网）
PROHIBITED_TOOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)bash"),
    re.compile(r"(?i)shell"),
    re.compile(r"(?i)subprocess"),
    re.compile(r"(?i)fs[-_]?write"),
    re.compile(r"(?i)web[-_]?fetch"),
    re.compile(r"(?i)web[-_]?search"),
    re.compile(r"(?i)terminal"),
)


# ---------------------------------------------------------------------------
# MCP 只读工具目录（Design §13：audit-data MCP server 工具清单）
# ---------------------------------------------------------------------------

#: MCP server 提供给 Agent 的只读工具（Task 26 实现的 audit-data MCP server）
MCP_READONLY_TOOLS: frozenset[str] = frozenset(
    {
        "wp_list",
        "wp_read",
        "tb_query",
        "addr_lookup",
        "kb_search",
        "note_read",
        "review_prompt",
    }
)


# ---------------------------------------------------------------------------
# 模型路由允许名单（Design §13：model endpoint ∈ loopback/internal allowlist）
# ---------------------------------------------------------------------------

#: effective model endpoint 必须匹配这些模式之一（本地 vLLM / 内网）
MODEL_ROUTE_ALLOWLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^https?://localhost[:/]"),
    re.compile(r"^https?://127\.0\.0\.1[:/]"),
    re.compile(r"^https?://\[::1\][:/]"),
    re.compile(r"^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}[:/]"),
    re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}[:/]"),
    re.compile(r"^https?://192\.168\.\d{1,3}\.\d{1,3}[:/]"),
)


# ---------------------------------------------------------------------------
# Custom Cordis 配置规范（Design §13）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CordisServiceSpec:
    """Cordis 服务项声明。"""

    id: str
    name: str
    required: bool = True
    is_transport: bool = False
    config: dict[str, Any] = field(default_factory=dict)


#: 平台 custom Cordis 的最小必需服务
REQUIRED_CORDIS_SERVICES: tuple[CordisServiceSpec, ...] = (
    CordisServiceSpec(
        id="sdk-jsonrpc-server",
        name="@deepseek-ai/dsh-sdk-jsonrpc-server",
        required=True,
        is_transport=False,
    ),
    CordisServiceSpec(
        id="agent-spine",
        name="@deepseek-ai/dsh-agent-spine-demo",
        required=True,
        is_transport=False,
    ),
    CordisServiceSpec(
        id="llm-local-vllm",
        name="@deepseek-ai/dsh-llm-deepseek",
        required=True,
        is_transport=False,
    ),
    CordisServiceSpec(
        id="mcp-client",
        name="@deepseek-ai/dsh-mcp-client",
        required=True,
        is_transport=False,
    ),
    CordisServiceSpec(
        id="internal-stdio-transport",
        name="@deepseek-ai/dsh-subprocess-local",
        required=True,
        is_transport=True,  # 运输服务，不暴露为 Agent 工具
    ),
)


@dataclass
class DshCordisSpec:
    """平台 custom Cordis 的完整描述。"""

    services: list[CordisServiceSpec] = field(default_factory=list)
    prohibited_tools: frozenset[str] = PROHIBITED_AGENT_TOOLS
    mcp_readonly_tools: frozenset[str] = MCP_READONLY_TOOLS
    model_route_allowlist: tuple[re.Pattern[str], ...] = MODEL_ROUTE_ALLOWLIST_PATTERNS


# ---------------------------------------------------------------------------
# Discovery 结果
# ---------------------------------------------------------------------------


class DshDiscoveryStatus(str, Enum):
    """发现结果状态。"""

    available = "available"
    version_mismatch = "version_mismatch"
    sdk_not_found = "sdk_not_found"
    import_failed = "import_failed"
    runtime_not_built = "runtime_not_built"
    cordis_config_missing = "cordis_config_missing"


@dataclass
class DshDiscoveryResult:
    """SDK 发现结果快照。"""

    status: DshDiscoveryStatus
    vendor_root: Path
    version: str | None = None
    commit: str | None = None
    cordis_version: str | None = None
    python_sdk_importable: bool = False
    runtime_binary_exists: bool = False
    node_runtime_exists: bool = False
    bundled_cordis_exists: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        return self.status == DshDiscoveryStatus.available

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "vendor_root": str(self.vendor_root),
            "version": self.version,
            "commit": self.commit,
            "cordis_version": self.cordis_version,
            "python_sdk_importable": self.python_sdk_importable,
            "runtime_binary_exists": self.runtime_binary_exists,
            "node_runtime_exists": self.node_runtime_exists,
            "bundled_cordis_exists": self.bundled_cordis_exists,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# 核心 Discovery 函数
# ---------------------------------------------------------------------------


def discover_dsh_sdk(vendor_root: Path | None = None) -> DshDiscoveryResult:
    """执行完整 SDK discovery，返回结果快照。

    此函数**只读** vendor_root，绝不修改任何文件。

    步骤：
    1. 确认 vendor_root 存在且含 package.json
    2. 读取 version 与 git commit
    3. 尝试 Python SDK import
    4. 检查 runtime binary / node closure
    5. 检查 bundled cordis.yml
    """
    root = vendor_root or DSH_VENDOR_ROOT
    result = DshDiscoveryResult(status=DshDiscoveryStatus.sdk_not_found, vendor_root=root)

    # Step 1: vendor root 存在性
    if not root.is_dir():
        result.errors.append(f"DSH vendor root 不存在: {root}")
        return result

    pkg_json = root / "package.json"
    if not pkg_json.is_file():
        result.errors.append(f"package.json 不存在: {pkg_json}")
        return result

    # Step 2: 版本与 commit
    try:
        pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
        result.version = pkg_data.get("version")
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"读取 package.json 失败: {exc}")
        return result

    # Cordis 版本
    cordis_pkg = root / "vendor" / "cordis" / "package.json"
    if cordis_pkg.is_file():
        try:
            cordis_data = json.loads(cordis_pkg.read_text(encoding="utf-8"))
            result.cordis_version = cordis_data.get("version")
        except (OSError, json.JSONDecodeError):
            pass

    # Git commit（只读 .git/HEAD → refs/heads/... → commit hash）
    result.commit = _read_git_head(root)

    # Step 3: Python SDK import
    sdk_src = root / "python" / "sdk" / "src"
    if sdk_src.is_dir():
        original_path = sys.path.copy()
        try:
            if str(sdk_src) not in sys.path:
                sys.path.insert(0, str(sdk_src))
            # 尝试导入核心接口
            from deepseek_harness import HarnessClient, HarnessConfig  # noqa: F401

            result.python_sdk_importable = True
        except ImportError as exc:
            result.errors.append(f"Python SDK import 失败: {exc}")
            result.status = DshDiscoveryStatus.import_failed
        finally:
            sys.path[:] = original_path
    else:
        result.errors.append(f"Python SDK src 目录不存在: {sdk_src}")
        result.status = DshDiscoveryStatus.import_failed

    # Step 4: runtime binary / node closure
    runtime_dir = root / "python" / "sdk-runtime" / "src" / "deepseek_harness_runtime" / "runtime"
    if runtime_dir.is_dir():
        # Check for compiled exe (platform-specific, may not exist on Windows)
        exe_candidates = list(runtime_dir.glob("dsh-jsonrpc-agent-pkg-*"))
        result.runtime_binary_exists = len(exe_candidates) > 0

        # Check for node dev closure
        node_bin = (
            runtime_dir
            / "node"
            / "node_modules"
            / "@deepseek-ai"
            / "dsh-sdk-jsonrpc-demo"
            / "lib"
            / "packaged-bin.js"
        )
        result.node_runtime_exists = node_bin.is_file()

        # Check bundled cordis.yml
        bundled_config = runtime_dir / "cordis.yml"
        result.bundled_cordis_exists = bundled_config.is_file()
    else:
        result.errors.append(f"Runtime 目录不存在: {runtime_dir}")
        result.status = DshDiscoveryStatus.runtime_not_built

    # Status determination
    if not result.python_sdk_importable:
        if result.status == DshDiscoveryStatus.sdk_not_found:
            result.status = DshDiscoveryStatus.import_failed
    elif not result.bundled_cordis_exists:
        result.status = DshDiscoveryStatus.cordis_config_missing
    elif result.version and result.version != DSH_PINNED_VERSION:
        result.status = DshDiscoveryStatus.version_mismatch
        result.errors.append(
            f"版本不匹配: 发现 {result.version}，期望 {DSH_PINNED_VERSION}"
        )
    else:
        result.status = DshDiscoveryStatus.available

    return result


def validate_version_pin(result: DshDiscoveryResult) -> list[str]:
    """验证版本 pin 的严格性。

    返回 errors 列表，空 = 全部通过。

    🔴 Req 10.6：``0.0.0.dev0`` 或 ``latest`` 不可作为生产 pin。
    我们以 npm monorepo 版本 + git commit 为锚，不以 Python pyproject.toml 的
    dev 版本为 pin 基准（它是 editable install 形态，与发布版本无关）。
    """
    errors: list[str] = []

    if not result.version:
        errors.append("未能读取 SDK 版本")
        return errors

    # 拒绝不安全版本标记
    unsafe_versions = {"0.0.0.dev0", "latest", "0.0.0", "*"}
    if result.version.lower() in unsafe_versions:
        errors.append(f"版本 {result.version} 不可作为生产 pin")

    # 精确版本匹配
    if result.version != DSH_PINNED_VERSION:
        errors.append(
            f"monorepo 版本 {result.version} != pinned {DSH_PINNED_VERSION}"
        )

    # Commit 验证（可选但强烈建议）
    if result.commit and result.commit != DSH_PINNED_COMMIT:
        errors.append(
            f"git commit {result.commit[:12]} != pinned {DSH_PINNED_COMMIT[:12]}"
        )

    # Cordis 版本验证
    if result.cordis_version and result.cordis_version != DSH_CORDIS_VERSION:
        errors.append(
            f"Cordis 版本 {result.cordis_version} != pinned {DSH_CORDIS_VERSION}"
        )

    return errors


# ---------------------------------------------------------------------------
# Custom Cordis 配置生成
# ---------------------------------------------------------------------------


def build_platform_cordis_config(
    *,
    vllm_base_url: str = "http://localhost:8100/v1",
    vllm_model: str = "Qwen3.5-27B-NVFP4",
    mcp_command: str | None = None,
    session_root: str = "./.sessions",
) -> list[dict[str, Any]]:
    """生成平台 custom Cordis 配置。

    只包含平台所需的最小安全组成，**不包含**任何 bash/fs-write/web-fetch/shell 工具。

    与 vendor 默认 cordis.yml 的核心区别：
    - ❌ 移除 bash/subprocess/fs-local（write）/terminal
    - ✅ 保留 sdk-jsonrpc-server（SDK bridge，必需）
    - ✅ 保留 agent-spine（Agent 核心）
    - ✅ LLM provider 指向本地 vLLM（非 DeepSeek 官方 API）
    - ✅ 新增 MCP client（连接 audit-data MCP server）
    - ✅ subprocess-local 仅作为 MCP stdio 运输，不暴露为 Agent 工具
    """
    config: list[dict[str, Any]] = [
        # 1. SDK JSON-RPC Server（bridge，必需）
        {
            "id": "sdk-jsonrpc-server",
            "name": "@deepseek-ai/dsh-sdk-jsonrpc-server",
            "config": {"maxTokensAsSuccess": True},
        },
        # 2. Agent Spine（核心调度）
        {
            "id": "agent-spine",
            "name": "@deepseek-ai/dsh-agent-spine-demo",
            "config": {
                "persona": "你是致同审计平台的 AI 审计助手，协助审计师完成审计工作。",
                "workspaceContext": False,
                "skills": {"enabled": False},
                # 🔴 明确禁用 bash / jobs 工具
                "toolBash": False,
                "toolJobs": False,
            },
        },
        # 3. Local vLLM Provider（本地模型，非 cloud）
        {
            "id": "llm-local-vllm",
            "name": "@deepseek-ai/dsh-llm-deepseek",
            "config": {
                "baseUrl": vllm_base_url,
                "thinking": "enabled",
                "reasoningEffort": "max",
                "models": [
                    {
                        "id": vllm_model,
                        "contextWindow": 32768,
                    }
                ],
            },
        },
        # 4. MCP Client（连接 audit-data MCP server）
        {
            "id": "mcp-client",
            "name": "@deepseek-ai/dsh-mcp-client",
        },
        # 5. JSONL Session Persistence
        {
            "id": "sessions",
            "name": "@deepseek-ai/dsh-session-persistence-jsonl",
            "config": {"root": session_root, "compression": "none"},
        },
        # 6. Token Meter（用量追踪）
        {
            "id": "token-meter",
            "name": "@deepseek-ai/dsh-token-meter",
        },
    ]

    # 7. Internal stdio transport（仅用于 MCP stdio，不暴露为 Agent 工具）
    # 只有指定 mcp_command 时才加（Task 28 使用）
    if mcp_command:
        config.append(
            {
                "id": "internal-stdio-transport",
                "name": "@deepseek-ai/dsh-subprocess-local",
                # 此服务仅被 mcp-client 消费，不注册 Agent 工具
            }
        )

    return config


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------


def validate_cordis_services(config: list[dict[str, Any]]) -> list[str]:
    """验证 Cordis 配置是否包含所有必需服务且不含禁止工具。

    返回 errors 列表，空 = 全部通过。
    """
    errors: list[str] = []
    service_names = {item.get("name", "") for item in config}
    service_ids = {item.get("id", "") for item in config}

    # 检查必需服务
    for spec in REQUIRED_CORDIS_SERVICES:
        if spec.name not in service_names:
            errors.append(f"缺少必需 Cordis 服务: {spec.name} (id={spec.id})")

    # 检查禁止工具——在 service 级别
    for item in config:
        svc_id = item.get("id", "")
        svc_name = item.get("name", "")
        cfg = item.get("config", {})

        # 检查是否是已知禁止工具
        for prohibited in PROHIBITED_AGENT_TOOLS:
            if prohibited in svc_id or prohibited in svc_name:
                # subprocess-local 作为内部运输是允许的
                if "subprocess" in prohibited and svc_id == "internal-stdio-transport":
                    continue
                errors.append(f"Cordis 配置包含禁止的工具服务: {svc_name} (id={svc_id})")

        # 特别检查 agent-spine 的 toolBash 配置
        if "agent-spine" in svc_id or "agent-spine" in svc_name:
            if cfg.get("toolBash") is not False:
                errors.append(
                    "agent-spine 的 toolBash 必须显式设为 false（禁止 bash 工具）"
                )
            if cfg.get("toolJobs") is not False:
                errors.append(
                    "agent-spine 的 toolJobs 必须显式设为 false（禁止 jobs 工具）"
                )

    return errors


def validate_tool_catalog(
    effective_tools: set[str] | frozenset[str],
    expected_tools: frozenset[str] | None = None,
) -> list[str]:
    """验证 effective tool catalog 是否受控。

    Args:
        effective_tools: 运行时实际激活的工具名集合
        expected_tools: 期望的工具集合（默认 MCP_READONLY_TOOLS）

    Returns:
        errors 列表，空 = 全部通过。
    """
    errors: list[str] = []
    expected = expected_tools or MCP_READONLY_TOOLS

    # 检查不应存在的工具
    for tool_name in effective_tools:
        # 精确匹配
        if tool_name in PROHIBITED_AGENT_TOOLS:
            errors.append(f"工具目录包含禁止工具: {tool_name}")
            continue
        # 模式匹配
        for pattern in PROHIBITED_TOOL_PATTERNS:
            if pattern.search(tool_name):
                errors.append(f"工具 {tool_name} 匹配禁止模式: {pattern.pattern}")
                break

    # 如果提供了 expected，检查集合相等
    if expected:
        extra = effective_tools - expected
        missing = expected - effective_tools
        if extra:
            errors.append(f"工具目录有多余工具: {sorted(extra)}")
        if missing:
            errors.append(f"工具目录缺少期望工具: {sorted(missing)}")

    return errors


def validate_model_route(
    effective_endpoint: str,
    allowlist: tuple[re.Pattern[str], ...] | None = None,
) -> list[str]:
    """验证 effective model endpoint 是否在允许列表内。

    Returns:
        errors 列表，空 = 在允许范围内。
    """
    errors: list[str] = []
    patterns = allowlist or MODEL_ROUTE_ALLOWLIST_PATTERNS

    if not effective_endpoint:
        errors.append("模型 endpoint 为空")
        return errors

    matched = any(p.match(effective_endpoint) for p in patterns)
    if not matched:
        errors.append(
            f"模型 endpoint {effective_endpoint} 不在 loopback/内网 allowlist 内"
        )

    # 额外检查：不能是已知 cloud provider
    cloud_indicators = [
        "api.deepseek.com",
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    ]
    for cloud in cloud_indicators:
        if cloud in effective_endpoint:
            errors.append(f"模型 endpoint 指向 cloud provider: {cloud}")

    return errors


# ---------------------------------------------------------------------------
# Smoke Test 函数
# ---------------------------------------------------------------------------


def smoke_sdk_import(vendor_root: Path | None = None) -> dict[str, Any]:
    """Smoke：验证 Python SDK 可 import 且核心接口可用。

    返回 {success, classes, error}。
    """
    root = vendor_root or DSH_VENDOR_ROOT
    sdk_src = root / "python" / "sdk" / "src"
    original_path = sys.path.copy()

    try:
        if str(sdk_src) not in sys.path:
            sys.path.insert(0, str(sdk_src))

        from deepseek_harness import (
            DeepSeekHarness,
            DeepSeekHarnessConfig,
            HarnessClient,
            HarnessConfig,
            RunResult,
            Session,
        )

        return {
            "success": True,
            "classes": [
                "DeepSeekHarness",
                "DeepSeekHarnessConfig",
                "HarnessClient",
                "HarnessConfig",
                "RunResult",
                "Session",
            ],
            "config_fields": list(HarnessConfig.__dataclass_fields__.keys()),
            "high_level_config_fields": list(
                DeepSeekHarnessConfig.__dataclass_fields__.keys()
            ),
            "error": None,
        }
    except Exception as exc:
        return {"success": False, "classes": [], "error": str(exc)}
    finally:
        sys.path[:] = original_path


def smoke_cordis_config_load(vendor_root: Path | None = None) -> dict[str, Any]:
    """Smoke：验证 bundled cordis.yml 可解析且结构正确。

    不启动运行时，只做配置文件层面的校验。
    返回 {success, services, error}。
    """
    root = vendor_root or DSH_VENDOR_ROOT
    config_path = (
        root
        / "python"
        / "sdk-runtime"
        / "src"
        / "deepseek_harness_runtime"
        / "runtime"
        / "cordis.yml"
    )

    try:
        if not config_path.is_file():
            return {
                "success": False,
                "services": [],
                "error": f"cordis.yml 不存在: {config_path}",
            }

        # 解析 YAML（简单方式，不需要 js 表达式求值）
        content = config_path.read_text(encoding="utf-8")
        # 提取 service names（不依赖 pyyaml，因为 vendor cordis 用了 !!js）
        services: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("name:"):
                name_val = stripped[5:].strip().strip("'\"")
                services.append(name_val)

        return {
            "success": True,
            "services": services,
            "service_count": len(services),
            "has_jsonrpc_server": "@deepseek-ai/dsh-sdk-jsonrpc-server" in services,
            "has_agent_spine": "@deepseek-ai/dsh-agent-spine-demo" in services,
            "has_llm": "@deepseek-ai/dsh-llm-deepseek" in services,
            "error": None,
        }
    except Exception as exc:
        return {"success": False, "services": [], "error": str(exc)}


def smoke_jsonrpc_handshake(vendor_root: Path | None = None) -> dict[str, Any]:
    """Smoke：真跑 JSON-RPC handshake（启动 → initialize → shutdown）。

    ⚠️ 需要 runtime binary（exe 或 node）可用。如果不可用则记录原因。
    本函数在 Windows 上可能不可用（exe 只编译 linux/macos）。
    """
    root = vendor_root or DSH_VENDOR_ROOT
    sdk_src = root / "python" / "sdk" / "src"
    runtime_src = root / "python" / "sdk-runtime" / "src"

    original_path = sys.path.copy()
    try:
        for p in [str(sdk_src), str(runtime_src)]:
            if p not in sys.path:
                sys.path.insert(0, p)

        from deepseek_harness import HarnessClient, HarnessConfig

        # 尝试使用 node 运行时（dev 模式，Windows 可用）
        node_bin_js = (
            root
            / "python"
            / "sdk-runtime"
            / "src"
            / "deepseek_harness_runtime"
            / "runtime"
            / "node"
            / "node_modules"
            / "@deepseek-ai"
            / "dsh-sdk-jsonrpc-demo"
            / "lib"
            / "packaged-bin.js"
        )

        import shutil

        node_path = shutil.which("node")
        if not node_path:
            return {
                "success": False,
                "handshake": None,
                "error": "node 未安装（JSON-RPC handshake 需要 Node.js >=22.19）",
                "skipped_reason": "no_node",
            }

        if not node_bin_js.is_file():
            return {
                "success": False,
                "handshake": None,
                "error": f"node runtime closure 不存在: {node_bin_js}",
                "skipped_reason": "no_node_closure",
            }

        # 使用平台 cordis 配置（无 bash/fs 工具）
        platform_config = build_platform_cordis_config()
        import tempfile
        import yaml  # type: ignore[import-untyped]

        # 注意：Cordis YAML 中的 !!js 需要 node 运行时解析，
        # 我们的平台配置不使用 !!js 所以可以直接写 YAML
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(platform_config, f, allow_unicode=True)
            config_path = f.name

        try:
            client = HarnessClient(
                HarnessConfig(
                    launch_args_override=(node_path, str(node_bin_js)),
                    env={
                        "DSH_CORDIS_CONFIG": config_path,
                        "DSH_CWD": str(root),
                    },
                    request_timeout_seconds=30.0,
                    shutdown_timeout_seconds=5.0,
                )
            )

            client.start()
            try:
                resp = client.initialize(
                    cwd=str(root),
                    provider="deepseek-official",
                    model="test-model",
                )
                return {
                    "success": True,
                    "handshake": {
                        "server_info": (
                            resp.serverInfo.model_dump() if resp.serverInfo else None
                        ),
                    },
                    "error": None,
                }
            finally:
                client.close()
        finally:
            try:
                os.unlink(config_path)
            except OSError:
                pass

    except Exception as exc:
        return {
            "success": False,
            "handshake": None,
            "error": str(exc),
            "skipped_reason": "exception",
        }
    finally:
        sys.path[:] = original_path


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _read_git_head(root: Path) -> str | None:
    """从 .git/HEAD 读取当前 commit hash（只读，不调 git CLI）。"""
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return None

    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return None

    try:
        head_content = head_file.read_text(encoding="utf-8").strip()
        # 如果是 ref: refs/heads/...，读对应文件
        if head_content.startswith("ref: "):
            ref_path = git_dir / head_content[5:]
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()
            # 可能在 packed-refs 中
            packed = git_dir / "packed-refs"
            if packed.is_file():
                ref_name = head_content[5:]
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(ref_name):
                        return line.split()[0]
            return None
        # 已经是 commit hash
        if len(head_content) == 40 and all(c in "0123456789abcdef" for c in head_content):
            return head_content
    except OSError:
        pass
    return None
