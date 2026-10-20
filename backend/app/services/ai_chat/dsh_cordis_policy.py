"""DSH custom Cordis 安全策略：工具清单、禁用模式、服务清单与配置生成（自 dsh_discovery 拆出）。

Feature: dsh-agent-panel-integration（Req 11.1 / 11.2 / 11.3 / 12.1）
拆分：dsh-kb-ocr-local-first-routing Task 1 —— 原样搬移，``dsh_discovery`` 保留同名再导出。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

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

#: 环回地址（DSH 子进程的模型服务只允许连平台环回转发端点）
LOOPBACK_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^https?://localhost[:/]"),
    re.compile(r"^https?://127\.0\.0\.1[:/]"),
    re.compile(r"^https?://\[::1\][:/]"),
)

#: effective model endpoint 必须匹配这些模式之一（本地 vLLM / 内网）
MODEL_ROUTE_ALLOWLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    *LOOPBACK_URL_PATTERNS,
    re.compile(r"^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}[:/]"),
    re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}[:/]"),
    re.compile(r"^https?://192\.168\.\d{1,3}\.\d{1,3}[:/]"),
)


# ---------------------------------------------------------------------------
# Custom Cordis 配置规范（Design §13）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CordisServiceSpec:
    """Cordis 服务项声明。

    ``conditional``：只在提供对应启动参数时出现（mcp-client 需要 MCP 启动配置才能装载）。
    """

    id: str
    name: str
    required: bool = True
    conditional: bool = False
    config: dict[str, Any] = field(default_factory=dict)


#: 平台 custom Cordis 的最小必需服务。
#: 🔴 不含 ``dsh-subprocess-local``：vendor mcp-client 用 MCP SDK 的 ``StdioClientTransport`` 自己
#: 拉起子进程（``packages/mcp/mcp-client/src/transport.ts``，``inject = ['tools']``），不消费该服务；
#: 旧配置把它当「MCP 运输」挂上，只是多挂了一个禁用名单里的服务（spec dsh-kb-ocr-local-first-routing D5）。
REQUIRED_CORDIS_SERVICES: tuple[CordisServiceSpec, ...] = (
    CordisServiceSpec(id="sdk-jsonrpc-server", name="@deepseek-ai/dsh-sdk-jsonrpc-server"),
    CordisServiceSpec(id="agent-spine", name="@deepseek-ai/dsh-agent-spine-demo"),
    CordisServiceSpec(id="llm-platform", name="@deepseek-ai/dsh-llm-deepseek"),
    CordisServiceSpec(id="mcp-client", name="@deepseek-ai/dsh-mcp-client", conditional=True),
)

#: vendor llm-deepseek 唯一注册的 provider 路由名（``packages/llm/llm-deepseek/src/index.ts::PROVIDER``）。
#: 只是适配器名，不代表请求目的地；目的地由配置里的 ``baseURL`` 决定（spec D2 / Req 2.3）。
DSH_LLM_PROVIDER = "deepseek-official"


@dataclass
class DshCordisSpec:
    """平台 custom Cordis 的完整描述。"""

    services: list[CordisServiceSpec] = field(default_factory=list)
    prohibited_tools: frozenset[str] = PROHIBITED_AGENT_TOOLS
    mcp_readonly_tools: frozenset[str] = MCP_READONLY_TOOLS
    model_route_allowlist: tuple[re.Pattern[str], ...] = MODEL_ROUTE_ALLOWLIST_PATTERNS


# ---------------------------------------------------------------------------
# Custom Cordis 配置生成
# ---------------------------------------------------------------------------


def build_platform_cordis_config(
    *,
    llm_base_url: str = "http://127.0.0.1:9980/api/ai-chat/dsh-llm/v1",
    llm_api_key_env: str = "GT_DSH_LLM_TOKEN",
    model: str = "Qwen3.5-27B-NVFP4",
    context_window: int = 32768,
    max_output_tokens: int = 8192,
    mcp_server: dict[str, Any] | None = None,
    session_root: str = "./.sessions",
    dsh_home: str | None = None,
) -> list[dict[str, Any]]:
    """生成平台 custom Cordis 配置（键名与 vendor schema 一致，见 vendor ``docs/config-catalog.md``）。

    只包含平台所需的最小安全组成，**不包含**任何 bash/fs-write/web-fetch/shell 工具。

    - 模型服务 ``baseURL`` 指向平台环回转发端点，``apiKeyEnv`` 是 run 令牌变量名：平台按令牌绑定的
      候选转发上游（ADR-DKR-001）。🔴 必须写 ``baseURL``（大写）—— 写成 ``baseUrl`` vendor 读不到，
      会回落 ``$DEEPSEEK_BASE_URL`` 再到公网 api.deepseek.com（spec D1）。
    - ``maxTokens`` / ``contextWindow`` 按候选给：vendor 默认输出上限 256000，本机 vLLM
      ``max_model_len=32768`` 首个请求即 400（spec D7）。
    - 思考参数由转发端按候选重写，DSH 侧关闭（适配器只会发 low/high/max，企业网关拒收 high）。
    - ``mcp_server``：mcp-client 的 stdio 配置（command/args/env/cwd…），由 DSH 自己拉起 audit-data
      MCP；不提供时不挂 mcp-client（vendor 要求它必须带完整连接配置）。
    """
    spine: dict[str, Any] = {
        "persona": "你是致同审计平台的 AI 审计助手，协助审计师完成审计工作。",
        "workspaceContext": False,
        "skills": {"enabled": False},
        # 🔴 明确禁用 bash / jobs 工具
        "toolBash": False,
        "toolJobs": False,
    }
    if dsh_home:
        spine["dshHome"] = dsh_home
    config: list[dict[str, Any]] = [
        # 1. SDK JSON-RPC Server（bridge，必需）
        {
            "id": "sdk-jsonrpc-server",
            "name": "@deepseek-ai/dsh-sdk-jsonrpc-server",
            "config": {"maxTokensAsSuccess": True},
        },
        # 2. Agent Spine（核心调度）
        {"id": "agent-spine", "name": "@deepseek-ai/dsh-agent-spine-demo", "config": spine},
        # 3. 模型服务：经平台环回转发（不直连任何上游）
        {
            "id": "llm-platform",
            "name": "@deepseek-ai/dsh-llm-deepseek",
            "config": {
                "baseURL": llm_base_url,
                "apiKeyEnv": llm_api_key_env,
                "thinking": "disabled",
                "maxTokens": max_output_tokens,
                "defaultContextWindow": context_window,
                "models": [
                    {
                        "id": model,
                        "contextWindow": context_window,
                        "maxTokens": max_output_tokens,
                    }
                ],
                # 上游失败快速结束本次 run，由下一次 run 选下一个候选（ADR-DKR-002）
                "retryPolicy": {"mode": "normal", "maxRetries": 1},
            },
        },
        # 4. JSONL Session Persistence
        {
            "id": "sessions",
            "name": "@deepseek-ai/dsh-session-persistence-jsonl",
            "config": {"root": session_root},
        },
    ]
    if mcp_server is not None:
        # 5. MCP Client：DSH 按 stdio 配置自己拉起 audit-data MCP（spec D5）
        config.append(
            {"id": "mcp-client", "name": "@deepseek-ai/dsh-mcp-client", "config": dict(mcp_server)}
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

    # 检查必需服务
    for spec in REQUIRED_CORDIS_SERVICES:
        if spec.name not in service_names:
            errors.append(f"缺少必需 Cordis 服务: {spec.name} (id={spec.id})")

    # 检查禁止工具——在 service 级别
    for item in config:
        svc_id = item.get("id", "")
        svc_name = item.get("name", "")
        cfg = item.get("config", {})

        # 检查是否是已知禁止工具（mcp-client 自己拉起 MCP 子进程，不需要 subprocess-local 例外）
        for prohibited in PROHIBITED_AGENT_TOOLS:
            if prohibited in svc_id or prohibited in svc_name:
                errors.append(f"Cordis 配置包含禁止的工具服务: {svc_name} (id={svc_id})")

        # 模型服务：必须显式 baseURL 且只连环回（平台转发端点），否则 vendor 回落公网 DeepSeek
        if svc_name == "@deepseek-ai/dsh-llm-deepseek":
            base_url = str(cfg.get("baseURL") or "")
            if not base_url:
                errors.append("模型服务缺少 baseURL（vendor 会回落 $DEEPSEEK_BASE_URL / 公网 API）")
            elif not any(p.match(base_url) for p in LOOPBACK_URL_PATTERNS):
                errors.append(f"模型服务 baseURL 必须是平台环回转发地址，实际 {base_url}")
            if cfg.get("apiKeyEnv") in (None, "", "DEEPSEEK_API_KEY"):
                errors.append("模型服务必须用平台令牌变量（apiKeyEnv），不得读 DEEPSEEK_API_KEY")

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
