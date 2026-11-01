"""流式/文件响应不得把数据库连接持有到慢客户端完成下载。"""

from __future__ import annotations

import inspect

from fastapi.params import Depends

from app.core.database import get_db
from app.deps import get_current_user_stream, require_project_access_stream
from app.routers.attachments import download_attachment, preview_attachment
from app.routers.batch_export_progress import download_export
from app.routers.doc_ai_chat import doc_ai_chat
from app.routers.chain_workflow import get_progress_stream as get_chain_progress_stream
from app.routers.ledger_import_v2 import stream_job_progress
from app.routers.wp_bulk_router import (
    bulk_export_data,
    bulk_export_download,
    bulk_export_templates,
    get_bulk_progress_stream,
)


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
