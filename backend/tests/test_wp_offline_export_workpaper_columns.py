"""离线导出不得在 ``WorkingPaper`` 上读不存在的列。

🔴 回归背景：``_load_workpaper`` 原先执行 ``sa_select(WorkingPaper)`` 后读
``wp.wp_code`` / ``getattr(wp, "year", "")``。``WorkingPaper`` 只有
``wp_index_id``，没有 ``wp_code`` / ``wp_name`` / ``year`` ⇒ ``AttributeError``
被函数内 ``except Exception`` 吞成空 dict ⇒ ``export_template`` 恒返回
``b""``，端点回 404「底稿不存在或无数据」，前端表现为导出静默失效。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.wp_offline_export_service import WpOfflineExportService


def _db_returning(row):
    result = MagicMock()
    result.first.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_load_workpaper_reads_index_code_and_project_year():
    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()
    db = _db_returning((wp_id, project_id, {"sheets": {}}, "D2-1", 2025))

    data = await WpOfflineExportService(db)._load_workpaper(wp_id)

    assert data == {
        "wp_id": str(wp_id),
        "wp_code": "D2-1",
        "project_id": project_id,
        "year": 2025,
        "parsed_data": {"sheets": {}},
    }


@pytest.mark.asyncio
async def test_load_workpaper_returns_empty_for_missing_row():
    db = _db_returning(None)
    assert await WpOfflineExportService(db)._load_workpaper(uuid.uuid4()) == {}


@pytest.mark.asyncio
async def test_load_workpaper_degrades_gracefully_on_null_joins():
    """悬空 ``wp_index_id`` / 缺项目时不能整体失败：编码与年度各自兜底。"""
    wp_id = uuid.uuid4()
    db = _db_returning((wp_id, None, None, None, None))

    data = await WpOfflineExportService(db)._load_workpaper(wp_id)

    assert data["wp_code"] == ""
    assert data["year"] == ""
    assert data["parsed_data"] == {}


@pytest.mark.asyncio
async def test_export_template_reaches_exporter_instead_of_returning_empty(monkeypatch):
    """端到端判据：有数据时必须真的产出文件，而不是静默 `b""`。"""
    wp_id = uuid.uuid4()
    db = _db_returning((wp_id, uuid.uuid4(), {"sheets": {}}, "D2-1", 2025))
    sentinel = (b"xlsx-bytes", "hash")

    monkeypatch.setattr(
        "app.services.wp_offline_export_service.export_workpaper_template",
        lambda *args, **kwargs: sentinel,
    )
    service = WpOfflineExportService(db)
    monkeypatch.setattr(service, "_get_project_name", AsyncMock(return_value="测试项目"))

    assert await service.export_template(wp_id) == sentinel
