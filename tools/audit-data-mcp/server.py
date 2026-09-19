#!/usr/bin/env python3
"""audit-data MCP server（dsh-agent-panel-integration Task 26）

stdio-only MCP server for DSH Agent，全部数据经平台受权 REST API 获取。

设计约束（Requirements 11.2–11.4 / Properties 26, 27, 29）：
  - 零 DB：不 import sqlalchemy/asyncpg/redis/平台 ORM，不读取 DB/Redis/平台密钥
  - 零监听端口：stdio transport only，不 socket.bind()
  - 工具目录受控：集合恒等于 MCP_READONLY_TOOLS（7 个 readonly 工具）
  - 预算绑定 run：budget errors 从 REST API 传播为 MCP 工具错误并停止后续调用
  - 不接受 Agent 自定义 shell command

环境变量：
  AUDIT_API_BASE   平台 REST 基地址（如 http://localhost:9980）
  MCP_TOKEN        scoped token（绑定 user/project/run/scope/exp）

每个工具仅调用 POST {AUDIT_API_BASE}/api/ai-chat/mcp/tools/call
平台端重新执行 ResourceAccessResolver、masking、配额和审计。
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# 🔴 禁止导入验证（Property 27）
# 以下模块绝不可出现在本文件的 import 中：
#   sqlalchemy, asyncpg, redis, app.models, app.core.database, app.core.config
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

AUDIT_API_BASE: str = os.environ.get("AUDIT_API_BASE", "http://localhost:9980")
MCP_TOKEN: str = os.environ.get("MCP_TOKEN", "")

#: 工具清单（与后端 MCP_READONLY_TOOLS 必须完全一致）
#: 🔴 运行时集合不多不少（Property 26）
TOOL_NAMES: frozenset[str] = frozenset(
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
# 预算追踪（客户端侧镜像，防止无意义的超限调用）
# ---------------------------------------------------------------------------


class BudgetExhausted(Exception):
    """本地预算耗尽，停止后续调用。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class LocalBudgetTracker:
    """客户端侧预算镜像。

    从平台返回的 budget 字段更新本地状态。
    一旦耗尽，后续所有工具调用立即拒绝，不再发 HTTP 请求。
    """

    def __init__(self) -> None:
        self._exhausted: bool = False
        self._calls_used: int = 0
        self._calls_remaining: int | None = None  # None = 未获得初始值
        self._total_bytes: int = 0

    @property
    def is_exhausted(self) -> bool:
        return self._exhausted

    def update_from_response(self, budget: dict[str, Any]) -> None:
        """从 REST 响应中的 budget 字段刷新本地状态。"""
        if not budget:
            return
        self._calls_used = budget.get("calls_used", self._calls_used)
        self._calls_remaining = budget.get("calls_remaining", self._calls_remaining)
        self._total_bytes = budget.get("total_bytes", self._total_bytes)
        if self._calls_remaining is not None and self._calls_remaining <= 0:
            self._exhausted = True

    def mark_exhausted(self, reason: str) -> None:
        """被服务端 tool_budget_exceeded 标记为耗尽。"""
        self._exhausted = True
        logger.warning("预算耗尽: %s", reason)

    def pre_check(self) -> None:
        """调用前检查。耗尽后所有调用直接拒绝。"""
        if self._exhausted:
            raise BudgetExhausted(
                "MCP 调用预算已耗尽，后续工具调用将不再执行。"
            )


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------

_budget = LocalBudgetTracker()


def _get_http_client() -> httpx.Client:
    """创建同步 HTTP 客户端（每次调用一个短生命周期实例）。"""
    return httpx.Client(
        base_url=AUDIT_API_BASE,
        headers={
            "X-MCP-Token": MCP_TOKEN,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def _call_platform_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """调用平台 MCP REST endpoint。

    POST /api/ai-chat/mcp/tools/call
    Body: { tool_name, arguments, tool_call_id }
    Header: X-MCP-Token

    返回 McpToolCallResponse 的 result 字段（成功时）。
    失败时抛出异常或返回错误 dict。
    """
    # 预算预检（Property 29：预算耗尽后停止后续调用）
    _budget.pre_check()

    tool_call_id = str(uuid.uuid4())

    payload = {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_call_id": tool_call_id,
    }

    with _get_http_client() as client:
        response = client.post("/api/ai-chat/mcp/tools/call", json=payload)

    # HTTP 级错误
    if response.status_code == 401:
        raise RuntimeError("MCP token 已失效或过期")
    if response.status_code == 403:
        raise RuntimeError(f"权限不足: {response.text}")
    if response.status_code >= 500:
        raise RuntimeError(f"平台服务错误 ({response.status_code})")
    if response.status_code >= 400:
        raise RuntimeError(f"请求错误 ({response.status_code}): {response.text}")

    data = response.json()

    # 更新本地预算镜像
    budget_info = data.get("budget", {})
    _budget.update_from_response(budget_info)

    # 检查工具级错误
    status = data.get("status", "")
    if status == "error":
        error_code = data.get("error_code", "unknown")
        error_message = data.get("error_message", "工具调用失败")

        # 预算超限 → 标记本地耗尽，后续调用直接拒绝
        if error_code == "tool_budget_exceeded":
            _budget.mark_exhausted(error_message)
            raise BudgetExhausted(error_message)

        raise RuntimeError(f"[{error_code}] {error_message}")

    return data.get("result", {})


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("audit-data")


@mcp.tool()
def wp_list(
    cycle: str = "",
    status: str = "",
    limit: int = 50,
) -> str:
    """列出当前项目有权访问的底稿。

    Args:
        cycle: 循环字母过滤（如 "D", "E", "G"），空则不过滤
        status: 底稿状态过滤（如 "in_progress", "completed"），空则不过滤
        limit: 最大返回条数（默认 50，最大 200）

    Returns:
        JSON 字符串，包含底稿列表
    """
    args: dict[str, Any] = {}
    if cycle:
        args["cycle"] = cycle
    if status:
        args["status"] = status
    if limit:
        args["limit"] = min(limit, 200)

    result = _call_platform_tool("wp_list", args)
    return _format_result(result)


@mcp.tool()
def wp_read(
    wp_id: str,
    sheet_name: str = "",
    include_data: bool = True,
) -> str:
    """读取指定底稿内容。

    Args:
        wp_id: 底稿实例 ID（UUID）
        sheet_name: sheet 名称（如 "审定表"），空则返回概要
        include_data: 是否包含数据内容

    Returns:
        JSON 字符串，包含底稿内容
    """
    args: dict[str, Any] = {"wp_id": wp_id}
    if sheet_name:
        args["sheet_name"] = sheet_name
    args["include_data"] = include_data

    result = _call_platform_tool("wp_read", args)
    return _format_result(result)


@mcp.tool()
def tb_query(
    account_code: str = "",
    level: int = 0,
    period: str = "current",
) -> str:
    """查询试算表数据。

    Args:
        account_code: 科目代码前缀过滤（如 "1001"），空则返回一级汇总
        level: 科目层级（0=全部, 1=一级, 2=二级...）
        period: 期间（"current"=本期, "prior"=上期, "both"=双期）

    Returns:
        JSON 字符串，包含试算表数据
    """
    args: dict[str, Any] = {}
    if account_code:
        args["account_code"] = account_code
    if level > 0:
        args["level"] = level
    if period:
        args["period"] = period

    result = _call_platform_tool("tb_query", args)
    return _format_result(result)


@mcp.tool()
def addr_lookup(
    addr_id: str = "",
    query: str = "",
    domain: str = "",
) -> str:
    """查询地址坐标。

    Args:
        addr_id: 精确地址 ID（如 "D2/审定表/row_1"）
        query: 模糊搜索文本
        domain: 域过滤（如 "tb", "report", "note", "wp", "aux"）

    Returns:
        JSON 字符串，包含地址坐标信息
    """
    args: dict[str, Any] = {}
    if addr_id:
        args["addr_id"] = addr_id
    if query:
        args["query"] = query
    if domain:
        args["domain"] = domain

    result = _call_platform_tool("addr_lookup", args)
    return _format_result(result)


@mcp.tool()
def kb_search(
    query: str,
    scope: str = "project",
    limit: int = 10,
) -> str:
    """搜索知识库。

    Args:
        query: 搜索文本
        scope: 搜索范围（"project"=项目, "global"=全局）
        limit: 最大返回条数

    Returns:
        JSON 字符串，包含搜索结果
    """
    args: dict[str, Any] = {"query": query}
    if scope:
        args["scope"] = scope
    if limit:
        args["limit"] = min(limit, 50)

    result = _call_platform_tool("kb_search", args)
    return _format_result(result)


@mcp.tool()
def note_read(
    note_id: str = "",
    section_key: str = "",
    chapter: str = "",
) -> str:
    """读取附注内容。

    Args:
        note_id: 附注实例 ID
        section_key: section 标识（如 "cash_and_bank"）
        chapter: 章节号过滤

    Returns:
        JSON 字符串，包含附注内容
    """
    args: dict[str, Any] = {}
    if note_id:
        args["note_id"] = note_id
    if section_key:
        args["section_key"] = section_key
    if chapter:
        args["chapter"] = chapter

    result = _call_platform_tool("note_read", args)
    return _format_result(result)


@mcp.tool()
def review_prompt(
    wp_code: str = "",
    sheet_name: str = "",
) -> str:
    """获取复核提示信息。

    Args:
        wp_code: 底稿编码（如 "D2-1"）
        sheet_name: sheet 名称

    Returns:
        JSON 字符串，包含复核提示（source_level/tips/checklist/risk_areas/version）
    """
    args: dict[str, Any] = {}
    if wp_code:
        args["wp_code"] = wp_code
    if sheet_name:
        args["sheet_name"] = sheet_name

    result = _call_platform_tool("review_prompt", args)
    return _format_result(result)


# ---------------------------------------------------------------------------
# 工具目录校验（Property 26: tool catalog == MCP_READONLY_TOOLS）
# ---------------------------------------------------------------------------


def validate_tool_catalog() -> list[str]:
    """校验本 server 注册的工具集合与 MCP_READONLY_TOOLS 完全一致。

    Returns:
        错误列表（空=通过）
    """
    # 获取 FastMCP 实际注册的工具名
    registered_tools = set(mcp._tool_manager._tools.keys())  # noqa: SLF001
    expected = TOOL_NAMES

    errors: list[str] = []
    extra = registered_tools - expected
    missing = expected - registered_tools
    if extra:
        errors.append(f"多余工具: {sorted(extra)}")
    if missing:
        errors.append(f"缺少工具: {sorted(missing)}")
    return errors


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _format_result(result: dict[str, Any] | list | Any) -> str:
    """将结果格式化为 JSON 字符串返回给 Agent。"""
    import json

    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------


def _validate_environment() -> None:
    """启动前环境校验。"""
    if not MCP_TOKEN:
        logger.warning("MCP_TOKEN 未设置，所有工具调用将失败")
    if not AUDIT_API_BASE:
        logger.error("AUDIT_API_BASE 未设置")
        sys.exit(1)

    # 校验工具目录一致性
    errors = validate_tool_catalog()
    if errors:
        logger.error("工具目录校验失败: %s", errors)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    _validate_environment()
    mcp.run()
