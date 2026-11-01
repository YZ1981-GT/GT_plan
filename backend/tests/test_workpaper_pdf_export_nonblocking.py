"""在线 LibreOffice 路由不得回退到同步 subprocess。"""
from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_workpaper_pdf_export_awaits_shared_executor_and_closes_db(tmp_path):
    from app.routers.wp_editor_router import export_workpaper_pdf

    source = tmp_path / "D2.xlsx"
    source.write_bytes(b"xlsx")
    wp = SimpleNamespace(file_path=str(source), wp_code="D2", wp_name="收入明细")
    result = MagicMock()
    result.scalar_one_or_none.return_value = wp
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.close = AsyncMock()
    convert = AsyncMock(return_value=b"%PDF-shared-executor")

    with patch(
        "app.services.libreoffice_pool.find_soffice_path", return_value="soffice"
    ), patch(
        "app.services.libreoffice_pool.convert_office_to_pdf_bytes", convert
    ):
        response = await export_workpaper_pdf(
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            db=db,
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert response.body == b"%PDF-shared-executor"
    assert response.media_type == "application/pdf"
    convert.assert_awaited_once_with(source, timeout=60, soffice_path="soffice")
    db.close.assert_awaited_once()


def test_async_office_routes_do_not_call_subprocess_run():
    """静态防回退：在线附件、模板和底稿 PDF 路由禁止同步 subprocess.run。"""
    from app.routers import office_preview, wp_editor_router, wp_template_download

    functions = (
        office_preview.preview_office_as_pdf,
        wp_template_download.preview_template_as_pdf,
        wp_editor_router.export_workpaper_pdf,
    )
    for function in functions:
        tree = ast.parse(inspect.getsource(function))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        ]
        assert not calls, f"{function.__module__}.{function.__name__} 仍同步调用 subprocess.run"
