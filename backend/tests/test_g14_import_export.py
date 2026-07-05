"""G14 导入导出 — 单元测试（storage_field=remark + 带符号转回字段）."""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies._cycle_import_export_common import (
    build_workbook_template,
    parse_upload_xlsx,
    import_rows_generic,
    upsert_json_rows,
)
from app.routers.wp_render_strategies._g14_credit_impairment_loss_import_export import (
    _G14_SPECS,
)


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_g14_export_template_g14_2():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g14/export-template?sheet=G14-2",
        )
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_g14_import_empty_template_persists_remark(override_deps: AsyncMock):
    """导入空模板应写入 remark 字段（非 VARCHAR(32) 的 conclusion）."""
    sp = _G14_SPECS["G14-2"]
    wb = build_workbook_template("G14-2", sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    headers, raw = parse_upload_xlsx(buf.read(), sp["headers"], header_row=2)
    rows, _ = import_rows_generic(raw, headers, sp["field_keys"])
    assert rows == []

    # 模拟 upsert：捕获 SQL 参数字段名
    captured: dict = {}

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        if "INSERT INTO checklist_responses" in sql and params:
            captured.update(params or {})
        result = MagicMock()
        result.scalar_one_or_none.return_value = "proj-1"
        result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = fake_execute
    db.commit = AsyncMock()

    await upsert_json_rows(db, "wp-1", sp["item_id"], rows, field="remark")

    assert captured.get("item_id") == "G14-detail-rows"
    payload = json.loads(captured.get("payload", "[]"))
    assert payload == []
    assert "payload" in captured


def test_g14_2_numeric_reversal_signed():
    """转回带符号字段应解析为浮点数."""
    from app.routers.wp_render_strategies._cycle_import_export_common import parse_row_by_headers

    sp = _G14_SPECS["G14-2"]
    row = ("ar", "应收账款", "1231", 100, 0, 500, 100, -20, 10, 570, "")
    parsed = parse_row_by_headers(row, sp["headers"], sp["field_keys"])
    assert parsed["currentReversal"] == -20.0
    assert parsed["currentProvision"] == 100.0
