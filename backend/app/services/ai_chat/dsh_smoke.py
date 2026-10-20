"""DSH smoke：SDK import / bundled Cordis 解析 / JSON-RPC 握手（自 dsh_discovery 拆出）。

Feature: dsh-agent-panel-integration（Req 10.6）
拆分：dsh-kb-ocr-local-first-routing Task 1 —— 原样搬移，``dsh_discovery`` 保留同名再导出。
vendor 根目录按调用时读取 ``dsh_discovery.DSH_VENDOR_ROOT``（测试可替换该模块属性）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from app.services.ai_chat.dsh_cordis_policy import build_platform_cordis_config


def _vendor_root() -> Path:
    from app.services.ai_chat import dsh_discovery

    return dsh_discovery.DSH_VENDOR_ROOT


# ---------------------------------------------------------------------------
# Smoke Test 函数
# ---------------------------------------------------------------------------


def smoke_sdk_import(vendor_root: Path | None = None) -> dict[str, Any]:
    """Smoke：验证 Python SDK 可 import 且核心接口可用。

    返回 {success, classes, error}。
    """
    root = vendor_root or _vendor_root()
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
    root = vendor_root or _vendor_root()
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
    root = vendor_root or _vendor_root()
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
