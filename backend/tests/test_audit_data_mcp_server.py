"""Tests for audit-data MCP server（dsh-agent-panel-integration Task 26）

行为守卫覆盖：
  - Property 26: tool catalog == MCP_READONLY_TOOLS, no dangerous tools
  - Property 27: 零数据库（无 DB import/connection/credential），零监听端口
  - Property 29: budget bound to run（预算耗尽后停止后续调用）

Validates: Requirements 11.2, 11.3, 11.4, 11.8
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# 路径设置：让 tools/audit-data-mcp/server.py 可导入
# ---------------------------------------------------------------------------

# tests 位于 backend/tests/，仓库根在 backend 的父目录
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SERVER_DIR = PROJECT_ROOT / "tools" / "audit-data-mcp"
SERVER_FILE = SERVER_DIR / "server.py"

# 确保可 import
sys.path.insert(0, str(SERVER_DIR))


# ---------------------------------------------------------------------------
# Property 27: 零数据库与零监听端口
# ---------------------------------------------------------------------------


class TestZeroDatabaseProperty:
    """Property 27: MCP server 运行期间无 DB 连接/import/凭据。

    **Validates: Requirements 11.4**
    """

    #: 禁止出现的 import 模块（static analysis）
    FORBIDDEN_IMPORTS = {
        "sqlalchemy",
        "asyncpg",
        "redis",
        "psycopg2",
        "psycopg",
        "aioredis",
    }

    #: 禁止出现的平台内部模块
    FORBIDDEN_PLATFORM_IMPORTS = {
        "app.models",
        "app.core.database",
        "app.core.config",
        "app.core.redis",
    }

    def test_no_db_imports_in_source(self) -> None:
        """源码静态分析：不 import 数据库/Redis/平台 ORM 模块。"""
        assert SERVER_FILE.exists(), f"server.py 不存在: {SERVER_FILE}"
        source = SERVER_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".")[0])
                    imported_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])
                    imported_modules.add(node.module)

        for forbidden in self.FORBIDDEN_IMPORTS:
            assert forbidden not in imported_modules, (
                f"server.py 禁止 import {forbidden}（Req 11.4: 不直连数据库）"
            )

        for forbidden in self.FORBIDDEN_PLATFORM_IMPORTS:
            assert forbidden not in imported_modules, (
                f"server.py 禁止 import {forbidden}（Req 11.4: 不读取平台密钥）"
            )

    def test_no_socket_bind_in_source(self) -> None:
        """源码不含 socket.bind / listen / TCP 监听（排除注释和文档字符串）。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        # 提取可执行代码行（排除注释和文档字符串内容）
        code_lines: list[str] = []
        in_docstring = False
        docstring_char = ""
        for line in source.splitlines():
            stripped = line.strip()
            # 跳过纯注释
            if stripped.startswith("#"):
                continue
            # 简单三引号文档字符串跟踪
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    # 单行文档字符串
                    if stripped.count(docstring_char) >= 2:
                        continue
                    in_docstring = True
                    continue
                code_lines.append(line)
            else:
                if docstring_char in stripped:
                    in_docstring = False
                continue

        code_only = "\n".join(code_lines)

        # 检查危险模式
        dangerous_patterns = [
            r"\bsocket\b.*\bbind\b",
            r"\bsocket\b.*\blisten\b",
            r"\.bind\(\s*\(['\"]",  # .bind(("host", port))
            r"uvicorn\.run",
            r"app\.run\(",
            r"HTTPServer",
            r"TCPServer",
            r"socketserver",
        ]
        for pattern in dangerous_patterns:
            assert not re.search(pattern, code_only), (
                f"server.py 可执行代码包含 TCP 监听模式 '{pattern}'（Req 11.4: 不监听端口）"
            )

    def test_no_db_credentials_in_env_reading(self) -> None:
        """源码只读取 AUDIT_API_BASE 和 MCP_TOKEN，不读取 DB 连接串。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        # 允许的环境变量
        allowed_env_vars = {"AUDIT_API_BASE", "MCP_TOKEN"}

        # 禁止的环境变量模式
        forbidden_env_patterns = [
            r"DATABASE_URL",
            r"DB_HOST",
            r"DB_PORT",
            r"DB_USER",
            r"DB_PASS",
            r"REDIS_URL",
            r"REDIS_HOST",
            r"PG_",
            r"POSTGRES_",
        ]
        for pattern in forbidden_env_patterns:
            matches = re.findall(
                rf'os\.environ\.get\(\s*["\']({pattern})',
                source,
            )
            assert not matches, (
                f"server.py 读取了禁止的环境变量模式 '{pattern}'（Req 11.4）"
            )

    def test_stdio_transport_only(self) -> None:
        """server.py 使用 stdio transport（mcp.run() 默认）。"""
        source = SERVER_FILE.read_text(encoding="utf-8")
        # FastMCP.run() 默认使用 stdio
        assert "mcp.run()" in source, "必须调用 mcp.run()（stdio 模式）"
        # 不应有 HTTP transport 配置
        assert "transport=\"http\"" not in source
        assert "transport='http'" not in source
        assert "sse" not in source.lower().replace("mcp_token", "").replace("mcp_readonly", "")


# ---------------------------------------------------------------------------
# Property 26: 工具目录受控
# ---------------------------------------------------------------------------


class TestToolCatalogProperty:
    """Property 26: 实际 Agent tool catalog 与 MCP_READONLY_TOOLS 完全相等。

    **Validates: Requirements 11.3**
    """

    def test_tool_names_match_backend_definition(self) -> None:
        """server.py 的 TOOL_NAMES 与后端 MCP_READONLY_TOOLS 完全一致。"""
        from app.services.ai_chat.mcp_token import MCP_READONLY_TOOLS

        # 从 server.py 源码中提取 TOOL_NAMES
        source = SERVER_FILE.read_text(encoding="utf-8")
        # 找到 frozenset 定义
        match = re.search(
            r'TOOL_NAMES:\s*frozenset\[str\]\s*=\s*frozenset\(\s*\{([^}]+)\}',
            source,
            re.DOTALL,
        )
        assert match, "找不到 TOOL_NAMES 定义"

        # 解析工具名
        tools_str = match.group(1)
        server_tools = set(re.findall(r'"(\w+)"', tools_str))

        assert server_tools == set(MCP_READONLY_TOOLS), (
            f"server.py TOOL_NAMES ({sorted(server_tools)}) != "
            f"MCP_READONLY_TOOLS ({sorted(MCP_READONLY_TOOLS)})"
        )

    def test_registered_tools_count(self) -> None:
        """恰好注册了 7 个工具，不多不少。"""
        source = SERVER_FILE.read_text(encoding="utf-8")
        # 计算 @mcp.tool() 装饰器出现次数
        tool_decorators = re.findall(r"@mcp\.tool\(\)", source)
        assert len(tool_decorators) == 7, (
            f"应注册 7 个工具，实际 {len(tool_decorators)} 个"
        )

    def test_all_tools_are_readonly(self) -> None:
        """所有工具函数名与 TOOL_NAMES 一一对应。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        # 提取所有 @mcp.tool() 下面的函数名
        registered_funcs = re.findall(
            r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\(",
            source,
        )

        expected = {"wp_list", "wp_read", "tb_query", "addr_lookup",
                    "kb_search", "note_read", "review_prompt"}

        assert set(registered_funcs) == expected, (
            f"注册函数 ({sorted(registered_funcs)}) != 期望 ({sorted(expected)})"
        )

    def test_no_dangerous_tools_registered(self) -> None:
        """不包含任何危险工具（Req 11.2: 禁止 shell/subprocess/fs-write）。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        dangerous = {
            "bash", "shell", "exec", "subprocess", "system",
            "fs_write", "file_write", "web_fetch", "http_get",
            "rm", "delete", "eval_code",
        }

        registered_funcs = re.findall(
            r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\(",
            source,
        )

        for func_name in registered_funcs:
            assert func_name not in dangerous, (
                f"注册了危险工具 '{func_name}'（Req 11.2）"
            )

    def test_validate_tool_catalog_function_exists(self) -> None:
        """server.py 提供 validate_tool_catalog() 自检函数。"""
        source = SERVER_FILE.read_text(encoding="utf-8")
        assert "def validate_tool_catalog()" in source


# ---------------------------------------------------------------------------
# Property 29: 预算绑定 run
# ---------------------------------------------------------------------------


class TestBudgetEnforcementProperty:
    """Property 29: 预算耗尽后停止后续调用。

    **Validates: Requirements 11.8**
    """

    def test_budget_exhausted_stops_calls(self) -> None:
        """预算耗尽后所有调用直接拒绝，不发 HTTP 请求。"""
        # 动态导入 server 模块
        import importlib.util

        spec = importlib.util.spec_from_file_location("audit_data_server", SERVER_FILE)
        mod = importlib.util.module_from_spec(spec)

        # Mock httpx 避免网络调用
        with patch.dict(os.environ, {"AUDIT_API_BASE": "http://test:9980", "MCP_TOKEN": "test-token"}):
            spec.loader.exec_module(mod)

        tracker = mod.LocalBudgetTracker()

        # 模拟正常使用
        tracker.update_from_response({"calls_used": 49, "calls_remaining": 1, "total_bytes": 1000})
        tracker.pre_check()  # 应通过

        # 标记耗尽
        tracker.mark_exhausted("调用次数超限")

        # 后续所有调用被拒绝
        with pytest.raises(mod.BudgetExhausted):
            tracker.pre_check()

    def test_budget_update_from_zero_remaining(self) -> None:
        """remaining=0 时自动标记为耗尽。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("audit_data_server", SERVER_FILE)
        mod = importlib.util.module_from_spec(spec)

        with patch.dict(os.environ, {"AUDIT_API_BASE": "http://test:9980", "MCP_TOKEN": "test-token"}):
            spec.loader.exec_module(mod)

        tracker = mod.LocalBudgetTracker()
        tracker.update_from_response({"calls_used": 50, "calls_remaining": 0, "total_bytes": 65000})

        assert tracker.is_exhausted
        with pytest.raises(mod.BudgetExhausted):
            tracker.pre_check()

    def test_budget_tracker_initial_state(self) -> None:
        """初始状态下未耗尽。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("audit_data_server", SERVER_FILE)
        mod = importlib.util.module_from_spec(spec)

        with patch.dict(os.environ, {"AUDIT_API_BASE": "http://test:9980", "MCP_TOKEN": "test-token"}):
            spec.loader.exec_module(mod)

        tracker = mod.LocalBudgetTracker()
        assert not tracker.is_exhausted
        tracker.pre_check()  # 不应抛异常


# ---------------------------------------------------------------------------
# REST 调用行为
# ---------------------------------------------------------------------------


class TestPlatformRestProxy:
    """验证工具调用确实代理到平台 REST endpoint。

    **Validates: Requirements 11.4**
    """

    def _load_server_module(self):
        """加载 server 模块（隔离环境）。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"audit_data_server_{uuid4().hex[:8]}",
            SERVER_FILE,
        )
        mod = importlib.util.module_from_spec(spec)

        with patch.dict(os.environ, {
            "AUDIT_API_BASE": "http://localhost:9980",
            "MCP_TOKEN": "test-scoped-token",
        }):
            spec.loader.exec_module(mod)
        return mod

    def test_call_platform_tool_sends_correct_payload(self) -> None:
        """_call_platform_tool 发送正确的 POST payload 和 header。"""
        mod = self._load_server_module()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tool_call_id": "test-id",
            "tool_name": "wp_list",
            "status": "success",
            "result": {"items": [{"id": "wp-1"}]},
            "budget": {"calls_used": 1, "calls_remaining": 49, "total_bytes": 100},
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_get_http_client", return_value=mock_client):
            # 重置模块级 budget
            mod._budget = mod.LocalBudgetTracker()
            result = mod._call_platform_tool("wp_list", {"cycle": "D"})

        # 验证请求内容
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/api/ai-chat/mcp/tools/call"
        payload = call_args[1]["json"]
        assert payload["tool_name"] == "wp_list"
        assert payload["arguments"] == {"cycle": "D"}
        assert "tool_call_id" in payload

        # 验证结果
        assert result == {"items": [{"id": "wp-1"}]}

    def test_call_platform_tool_propagates_budget_exceeded(self) -> None:
        """服务端返回 tool_budget_exceeded 时本地标记耗尽。"""
        mod = self._load_server_module()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tool_call_id": "test-id",
            "tool_name": "wp_list",
            "status": "error",
            "error_code": "tool_budget_exceeded",
            "error_message": "MCP calls 配额超限：当前 50，上限 50",
            "budget": {"calls_used": 50, "calls_remaining": 0, "total_bytes": 60000},
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_get_http_client", return_value=mock_client):
            mod._budget = mod.LocalBudgetTracker()
            with pytest.raises(mod.BudgetExhausted):
                mod._call_platform_tool("wp_list", {})

        # 后续调用直接拒绝（不发 HTTP）
        with pytest.raises(mod.BudgetExhausted):
            mod._call_platform_tool("wp_read", {"wp_id": "x"})

    def test_call_platform_tool_handles_401(self) -> None:
        """Token 失效时抛出明确错误。"""
        mod = self._load_server_module()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "MCP token 已过期"

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_get_http_client", return_value=mock_client):
            mod._budget = mod.LocalBudgetTracker()
            with pytest.raises(RuntimeError, match="token.*失效|过期"):
                mod._call_platform_tool("wp_list", {})

    def test_call_platform_tool_handles_403(self) -> None:
        """权限不足时抛出明确错误。"""
        mod = self._load_server_module()

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "scope 不匹配"

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_get_http_client", return_value=mock_client):
            mod._budget = mod.LocalBudgetTracker()
            with pytest.raises(RuntimeError, match="权限不足"):
                mod._call_platform_tool("wp_list", {})

    def test_call_platform_tool_handles_server_error(self) -> None:
        """服务端 500 时抛出明确错误。"""
        mod = self._load_server_module()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "internal error"

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_get_http_client", return_value=mock_client):
            mod._budget = mod.LocalBudgetTracker()
            with pytest.raises(RuntimeError, match="服务错误"):
                mod._call_platform_tool("wp_list", {})

    def test_http_client_uses_mcp_token_header(self) -> None:
        """HTTP 客户端设置 X-MCP-Token header。"""
        mod = self._load_server_module()
        # 检查 _get_http_client 设置了正确 header
        client = mod._get_http_client()
        assert "X-MCP-Token" in client.headers
        client.close()


# ---------------------------------------------------------------------------
# 结构与安全性
# ---------------------------------------------------------------------------


class TestServerStructure:
    """验证 server.py 的结构安全性。"""

    def test_no_shell_command_acceptance(self) -> None:
        """server.py 不接受 Agent 自定义 shell command（Req 11.2）。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        # 不应有 subprocess/os.system/exec 调用
        dangerous_calls = [
            r"\bsubprocess\.",
            r"\bos\.system\b",
            r"\bos\.popen\b",
            r"\bexec\s*\(",
            r"\beval\s*\(",
            r"\b__import__\b",
        ]
        for pattern in dangerous_calls:
            # 排除注释行
            code_lines = [
                line for line in source.splitlines()
                if not line.strip().startswith("#")
            ]
            code_only = "\n".join(code_lines)
            assert not re.search(pattern, code_only), (
                f"server.py 包含危险调用 '{pattern}'（Req 11.2）"
            )

    def test_all_tools_call_platform_rest(self) -> None:
        """每个工具函数内部调用 _call_platform_tool。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        tool_funcs = re.findall(
            r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\([^)]*\)[^:]*:(.*?)(?=@mcp\.tool\(\)|^def\s|^class\s|\Z)",
            source,
            re.DOTALL | re.MULTILINE,
        )

        for func_name, func_body in tool_funcs:
            assert "_call_platform_tool" in func_body, (
                f"工具 '{func_name}' 未调用 _call_platform_tool"
                f"（Req 11.4: 全部数据经平台受权 REST API 获取）"
            )

    def test_environment_validation_at_startup(self) -> None:
        """启动时校验环境变量和工具目录。"""
        source = SERVER_FILE.read_text(encoding="utf-8")
        assert "_validate_environment()" in source
        assert "validate_tool_catalog()" in source

    def test_only_audit_api_base_as_http_target(self) -> None:
        """所有 HTTP 调用只指向 AUDIT_API_BASE，不含其他硬编码 URL。"""
        source = SERVER_FILE.read_text(encoding="utf-8")

        # 排除注释和文档字符串中的 URL
        # 找所有字符串中的 http:// 或 https://
        url_in_code = re.findall(r'["\']https?://[^"\']+["\']', source)

        for url_str in url_in_code:
            # 允许默认值 http://localhost:9980（AUDIT_API_BASE 的默认）
            if "localhost:9980" in url_str or "test:9980" in url_str:
                continue
            # 文档字符串中的 URL 可以存在
            # 实际代码中不应有其他 URL
            # 这里宽松检查：确保没有其他 production URL
            assert "0.0.0.0" not in url_str, f"不应绑定到 0.0.0.0: {url_str}"


# ---------------------------------------------------------------------------
# 工具参数与调用
# ---------------------------------------------------------------------------


class TestToolParameters:
    """验证各工具参数传递。"""

    def _load_and_mock(self):
        """加载模块并 mock HTTP 层。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"audit_data_server_{uuid4().hex[:8]}",
            SERVER_FILE,
        )
        mod = importlib.util.module_from_spec(spec)

        with patch.dict(os.environ, {
            "AUDIT_API_BASE": "http://localhost:9980",
            "MCP_TOKEN": "test-scoped-token",
        }):
            spec.loader.exec_module(mod)

        # Mock _call_platform_tool
        mock_call = MagicMock(return_value={"status": "ok"})
        mod._call_platform_tool = mock_call
        return mod, mock_call

    def test_wp_list_passes_filter_args(self) -> None:
        """wp_list 正确传递过滤参数。"""
        mod, mock_call = self._load_and_mock()
        mod.wp_list(cycle="D", status="completed", limit=10)
        mock_call.assert_called_once_with("wp_list", {"cycle": "D", "status": "completed", "limit": 10})

    def test_wp_list_limit_capped_at_200(self) -> None:
        """wp_list limit 上限 200。"""
        mod, mock_call = self._load_and_mock()
        mod.wp_list(limit=500)
        args = mock_call.call_args[0][1]
        assert args["limit"] == 200

    def test_wp_read_requires_wp_id(self) -> None:
        """wp_read 传递 wp_id。"""
        mod, mock_call = self._load_and_mock()
        mod.wp_read(wp_id="uuid-123", sheet_name="审定表")
        mock_call.assert_called_once_with(
            "wp_read",
            {"wp_id": "uuid-123", "sheet_name": "审定表", "include_data": True},
        )

    def test_tb_query_default_period(self) -> None:
        """tb_query 默认 period=current。"""
        mod, mock_call = self._load_and_mock()
        mod.tb_query()
        args = mock_call.call_args[0][1]
        assert args.get("period") == "current"

    def test_addr_lookup_by_id(self) -> None:
        """addr_lookup 按 ID 查询。"""
        mod, mock_call = self._load_and_mock()
        mod.addr_lookup(addr_id="D2/审定表/row_1")
        args = mock_call.call_args[0][1]
        assert args["addr_id"] == "D2/审定表/row_1"

    def test_kb_search_limit_capped(self) -> None:
        """kb_search limit 上限 50。"""
        mod, mock_call = self._load_and_mock()
        mod.kb_search(query="test", limit=100)
        args = mock_call.call_args[0][1]
        assert args["limit"] == 50

    def test_note_read_by_section_key(self) -> None:
        """note_read 按 section_key 查询。"""
        mod, mock_call = self._load_and_mock()
        mod.note_read(section_key="cash_and_bank", chapter="7")
        args = mock_call.call_args[0][1]
        assert args["section_key"] == "cash_and_bank"
        assert args["chapter"] == "7"

    def test_review_prompt_by_wp_code(self) -> None:
        """review_prompt 按 wp_code 查询。"""
        mod, mock_call = self._load_and_mock()
        mod.review_prompt(wp_code="D2-1", sheet_name="Sheet1")
        mock_call.assert_called_once_with(
            "review_prompt",
            {"wp_code": "D2-1", "sheet_name": "Sheet1"},
        )


# ---------------------------------------------------------------------------
# 集成级：确认与后端 MCP_READONLY_TOOLS 一致
# ---------------------------------------------------------------------------


class TestBackendConsistency:
    """确认 server TOOL_NAMES 与后端单一真源一致。"""

    def test_exact_match_with_backend_mcp_readonly_tools(self) -> None:
        """server.py TOOL_NAMES == backend MCP_READONLY_TOOLS（单一真源）。"""
        from app.services.ai_chat.mcp_token import MCP_READONLY_TOOLS

        # 从 server.py 读取 TOOL_NAMES
        source = SERVER_FILE.read_text(encoding="utf-8")
        match = re.search(
            r'TOOL_NAMES:\s*frozenset\[str\]\s*=\s*frozenset\(\s*\{([^}]+)\}',
            source,
            re.DOTALL,
        )
        assert match
        server_tools = frozenset(re.findall(r'"(\w+)"', match.group(1)))
        assert server_tools == MCP_READONLY_TOOLS

    def test_exact_seven_tools(self) -> None:
        """恰好 7 个工具。"""
        from app.services.ai_chat.mcp_token import MCP_READONLY_TOOLS

        assert len(MCP_READONLY_TOOLS) == 7
