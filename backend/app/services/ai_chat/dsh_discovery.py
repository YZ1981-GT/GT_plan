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

import json
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.config import settings

# 拆分后的策略与 smoke 在独立模块；此处再导出原名，旧导入与 patch 路径保持可解析。
from app.services.ai_chat.dsh_cordis_policy import (  # noqa: F401
    MCP_READONLY_TOOLS,
    MODEL_ROUTE_ALLOWLIST_PATTERNS,
    PROHIBITED_AGENT_TOOLS,
    PROHIBITED_TOOL_PATTERNS,
    REQUIRED_CORDIS_SERVICES,
    CordisServiceSpec,
    DshCordisSpec,
    build_platform_cordis_config,
    validate_cordis_services,
    validate_model_route,
    validate_tool_catalog,
)

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

#: vendor 根目录——只读，绝不修改。取 ``settings.DSH_VENDOR_ROOT``（环境变量 > .env > 默认值）。
DSH_VENDOR_ROOT = Path(settings.DSH_VENDOR_ROOT)

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


# smoke 函数依赖本模块的 DSH_VENDOR_ROOT（调用时读取），放在末尾导入避免循环。
from app.services.ai_chat.dsh_smoke import (  # noqa: E402,F401
    smoke_cordis_config_load,
    smoke_jsonrpc_handshake,
    smoke_sdk_import,
)
