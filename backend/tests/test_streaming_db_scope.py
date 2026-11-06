"""流式/文件响应不得把数据库连接持有到慢客户端完成下载。"""

from __future__ import annotations

import ast
import inspect
import textwrap

from fastapi.params import Depends

from app.core.database import get_db
from app.deps import get_current_user_stream, require_project_access_stream
from app.routers.attachments import download_attachment, preview_attachment
from app.routers.batch_export_progress import download_export
from app.routers.doc_ai_chat import doc_ai_chat
from app.routers.wp_chat import wp_chat
from app.routers.chain_workflow import get_progress_stream as get_chain_progress_stream
from app.routers.working_paper import download_workpaper, download_workpaper_pack
from app.routers.ledger_import_v2 import stream_job_progress
from app.routers.wp_bulk_router import (
    bulk_export_data,
    bulk_export_download,
    bulk_export_templates,
    get_bulk_progress_stream,
)
from app.routers.wp_template_download import (
    download_all_templates,
    download_template_by_code,
    download_template_prefilled,
)
from app.routers.wp_template_files import get_workpaper_xlsx
from app.routers.wp_download import download_pack, download_single
from app.routers.wp_xlsx_export import export_xlsx
from app.routers.wp_render_config import export_template
from app.routers.wp_export_import_router import batch_export_enhanced, export_with_metadata


def _depends(function, parameter: str) -> Depends:
    value = inspect.signature(function).parameters[parameter].default
    assert isinstance(value, Depends)
    return value


def test_stream_auth_uses_function_scoped_database_session():
    dependency = _depends(get_current_user_stream, "db")
    assert dependency.dependency is get_db
    assert dependency.scope == "function"


def test_attachment_streams_release_database_before_body():
    for endpoint in (download_attachment, preview_attachment):
        database = _depends(endpoint, "db")
        auth = _depends(endpoint, "current_user")
        assert database.dependency is get_db
        assert database.scope == "function"
        assert auth.dependency is get_current_user_stream


def test_export_file_response_uses_short_lived_auth_session():
    auth = _depends(download_export, "current_user")
    assert auth.dependency is get_current_user_stream


def test_stream_project_gate_uses_function_scoped_database_session():
    gate = require_project_access_stream("readonly")
    database = _depends(gate, "db")
    auth = _depends(gate, "current_user")
    assert database.dependency is get_db
    assert database.scope == "function"
    assert auth.dependency is get_current_user_stream


def test_bulk_file_and_sse_routes_use_short_lived_dependencies():
    for endpoint in (
        get_bulk_progress_stream,
        bulk_export_templates,
        bulk_export_data,
        bulk_export_download,
    ):
        gate = _depends(endpoint, "current_user")
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"

    for endpoint in (bulk_export_templates, bulk_export_data, bulk_export_download):
        database = _depends(endpoint, "db")
        assert database.dependency is get_db
        assert database.scope == "function"


def test_long_lived_sse_routes_use_stream_project_gate():
    for endpoint in (get_chain_progress_stream, stream_job_progress):
        gate = _depends(endpoint, "current_user")
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"


def test_doc_ai_stream_builds_context_with_function_scoped_session():
    database = _depends(doc_ai_chat, "db")
    auth = _depends(doc_ai_chat, "current_user")
    assert database.dependency is get_db
    assert database.scope == "function"
    assert auth.dependency is get_current_user_stream


def test_wp_chat_prepares_context_before_streaming():
    """A6：底稿 AI 流不能把 request-scope session 传入 generator。"""
    database = _depends(wp_chat, "db")
    auth = _depends(wp_chat, "current_user")
    assert database.dependency is get_db
    assert database.scope == "function"
    assert auth.dependency is get_current_user_stream

    from app.services.wp_chat_service import WpChatService

    source = textwrap.dedent(inspect.getsource(WpChatService.stream_prepared))
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    # docstring 文本不进 AST；只允许纯 LLM 流，不许在响应期读 DB/ORM 上下文。
    assert "AsyncSession" not in names
    assert "_load_wp_context" not in attrs


def test_workpaper_download_routes_release_db_before_streaming():
    """A6：底稿 ZIP 和单件下载都必须在响应体开始前释放鉴权/查询 session。"""
    for endpoint in (download_workpaper_pack, download_workpaper):
        database = _depends(endpoint, "db")
        gate = _depends(endpoint, "current_user")
        assert database.dependency is get_db
        assert database.scope == "function"
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"


def test_template_download_routes_use_stream_project_gate():
    """模板单件/整包/预填下载不能保留项目权限 session 到慢客户端下载结束。"""
    for endpoint in (download_template_by_code, download_all_templates, download_template_prefilled):
        gate = _depends(endpoint, "current_user")
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"
    database = _depends(download_template_prefilled, "db")
    assert database.dependency is get_db
    assert database.scope == "function"


def test_univer_xlsx_file_response_uses_function_scoped_session():
    database = _depends(get_workpaper_xlsx, "db")
    assert database.dependency is get_db
    assert database.scope == "function"


def test_legacy_wp_download_routes_use_function_scoped_stream_gate():
    """旧 /workpapers/download-* 路径也必须释放 session，不能因别名路由绕过 A6。"""
    for endpoint in (download_pack, download_single):
        database = _depends(endpoint, "db")
        gate = _depends(endpoint, "current_user")
        assert database.dependency is get_db
        assert database.scope == "function"
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"


def test_xlsx_export_uses_function_scoped_auth_and_database():
    database = _depends(export_xlsx, "db")
    auth = _depends(export_xlsx, "current_user")
    assert database.dependency is get_db
    assert database.scope == "function"
    assert auth.dependency is get_current_user_stream


def test_cycle_import_export_common_exports_use_function_scope_and_stream_auth():
    """A6 第二波：L/M/N/K 等循环共用的 `_cycle_import_export_common.py` 一处收口。

    `register_cycle_import_export_endpoints` 内部注册的 `export_template` / `export_data`
    是闭包函数，只能从 `router.routes` 动态获取；本断言按闭包源码文本验证两处 Depends
    均已切 function-scope + stream auth，`import_data` 保留请求级 session（写路径不迁）。
    """
    import re
    from pathlib import Path

    source = Path(
        inspect.getsourcefile(
            __import__(
                "app.routers.wp_render_strategies._cycle_import_export_common",
                fromlist=["_cycle_import_export_common"],
            )
        )
    ).read_text(encoding="utf-8")
    # 粗切闭包块
    export_template_block = source.split("async def export_template(")[1].split("async def export_data(")[0]
    export_data_block = source.split("async def export_data(")[1].split("async def import_data(")[0]
    import_data_block = source.split("async def import_data(")[1][:400]
    for block, name in (
        (export_template_block, "export_template"),
        (export_data_block, "export_data"),
    ):
        assert re.search(
            r"Depends\(get_db,\s*scope=\"function\"\)", block
        ), f"{name} 应迁到 function-scope DB"
        assert "Depends(get_current_user_stream)" in block, f"{name} 应用 stream 认证"
    # import_data 走写路径，保留 request-scope（防止回归时顺手改坏）
    assert "Depends(get_db)" in import_data_block
    assert "Depends(get_current_user)" in import_data_block
    assert "scope=\"function\"" not in import_data_block


def test_render_config_export_template_uses_short_lived_session():
    """A6 第二波：模板文件下载提前释放 DB。"""
    database = _depends(export_template, "db")
    auth = _depends(export_template, "current_user")
    assert database.dependency is get_db
    assert database.scope == "function"
    assert auth.dependency is get_current_user_stream


def test_enhanced_export_routes_release_db_before_streaming():
    """A6 第二波：单份/批量增强导出 StreamingResponse 发出前 commit 并释放 DB。"""
    for endpoint in (export_with_metadata, batch_export_enhanced):
        database = _depends(endpoint, "db")
        gate = _depends(endpoint, "current_user")
        assert database.dependency is get_db
        assert database.scope == "function"
        gate_database = _depends(gate.dependency, "db")
        assert gate_database.dependency is get_db
        assert gate_database.scope == "function"
