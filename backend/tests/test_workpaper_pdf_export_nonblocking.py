"""在线 LibreOffice 路由不得回退到同步 subprocess。"""
from __future__ import annotations

import ast
import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_db(*, idx_row, wp):
    """按真实查询顺序返回：先 ``WorkingPaper``，再 ``wp_index`` 取文件名。"""
    wp_result = MagicMock()
    wp_result.scalar_one_or_none.return_value = wp
    idx_result = MagicMock()
    idx_result.first.return_value = idx_row
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[wp_result, idx_result])
    db.close = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_workpaper_pdf_export_awaits_shared_executor_and_closes_db(tmp_path):
    from app.routers.wp_editor_router import export_workpaper_pdf

    source = tmp_path / "D2.xlsx"
    source.write_bytes(b"xlsx")
    # 🔴 `WorkingPaper` 没有 wp_code / wp_name 列，只有 wp_index_id。
    wp = SimpleNamespace(file_path=str(source), wp_index_id=uuid.uuid4())
    db = _fake_db(idx_row=("D2", "收入明细"), wp=wp)
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
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_workpaper_pdf_export_falls_back_when_index_row_missing(tmp_path):
    """悬空 ``wp_index_id``（历史数据）不能让导出失败 —— 文件名不是门禁。"""
    from app.routers.wp_editor_router import export_workpaper_pdf

    source = tmp_path / "orphan.xlsx"
    source.write_bytes(b"xlsx")
    wp = SimpleNamespace(file_path=str(source), wp_index_id=None)
    db = _fake_db(idx_row=None, wp=wp)
    convert = AsyncMock(return_value=b"%PDF-fallback")

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

    assert response.body == b"%PDF-fallback"
    disposition = response.headers["Content-Disposition"]
    assert "workpaper_" in disposition


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
