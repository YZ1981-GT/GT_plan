"""单元测试 — SingleTabIeAdapter (Task 2.1)

验证：
- IE_ADAPTER_REGISTRY 未注册 prefix → export_tab/import_tab 抛 KeyError
- 注册后调用正确的 export_fn / import_fn
- make_import_result_from_legacy 正确转换旧格式
- workbook_to_bytes 输出合法 xlsx bytes
"""
import pytest
import asyncio
from unittest.mock import AsyncMock

from app.services.bulk_tab.single_tab_adapter import (
    AdapterSpec,
    IE_ADAPTER_REGISTRY,
    ROW_LIMIT,
    TabImportResult,
    export_tab,
    import_tab,
    make_import_result_from_legacy,
    register_adapter,
    workbook_to_bytes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """确保测试间互不干扰 registry。"""
    original = dict(IE_ADAPTER_REGISTRY)
    yield
    IE_ADAPTER_REGISTRY.clear()
    IE_ADAPTER_REGISTRY.update(original)


# ---------------------------------------------------------------------------
# Tests: unregistered prefix → KeyError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_tab_unregistered_raises_key_error():
    """未注册的 api_prefix 调用 export_tab 应抛 KeyError。"""
    with pytest.raises(KeyError, match="no_adapter"):
        await export_tab(None, "wp-123", "z99", "Z99-1", "template")


@pytest.mark.asyncio
async def test_import_tab_unregistered_raises_key_error():
    """未注册的 api_prefix 调用 import_tab 应抛 KeyError。"""
    with pytest.raises(KeyError, match="no_adapter"):
        await import_tab(None, "wp-123", "z99", "Z99-1", b"fake", "overwrite")


# ---------------------------------------------------------------------------
# Tests: registered adapter dispatches correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_tab_dispatches_to_registered_adapter():
    """注册后 export_tab 应调用正确的 export_fn。"""
    mock_export = AsyncMock(return_value=b"PK\x03\x04fake_xlsx")
    mock_import = AsyncMock()
    register_adapter("test-prefix", AdapterSpec(export_fn=mock_export, import_fn=mock_import))

    result = await export_tab(None, "wp-1", "test-prefix", "TP-1", "data")

    assert result == b"PK\x03\x04fake_xlsx"
    mock_export.assert_called_once_with(None, "wp-1", "TP-1", "data")


@pytest.mark.asyncio
async def test_import_tab_dispatches_to_registered_adapter():
    """注册后 import_tab 应调用正确的 import_fn。"""
    expected = TabImportResult(status="success", rows_imported=10)
    mock_export = AsyncMock()
    mock_import = AsyncMock(return_value=expected)
    register_adapter("test-prefix", AdapterSpec(export_fn=mock_export, import_fn=mock_import))

    result = await import_tab(None, "wp-1", "test-prefix", "TP-1", b"xlsx-data", "fill-empty")

    assert result.status == "success"
    assert result.rows_imported == 10
    mock_import.assert_called_once_with(None, "wp-1", "TP-1", b"xlsx-data", "fill-empty")


# ---------------------------------------------------------------------------
# Tests: make_import_result_from_legacy
# ---------------------------------------------------------------------------


def test_legacy_ok_success():
    """ok=True 且无超限 → status=success。"""
    r = make_import_result_from_legacy({"ok": True, "imported_count": 42, "errors": []})
    assert r.status == "success"
    assert r.rows_imported == 42
    assert r.warnings == []
    assert r.errors == []


def test_legacy_ok_with_truncation_warning():
    """ok=True 但有 warning → status=partial。"""
    r = make_import_result_from_legacy({
        "ok": True,
        "imported_count": 500,
        "errors": [],
        "warning": "数据行数超过500行限制，已截断",
    })
    assert r.status == "partial"
    assert r.rows_imported == 500
    assert "500" in r.warnings[0]


def test_legacy_failed():
    """ok=False + errors → status=failed。"""
    r = make_import_result_from_legacy({
        "ok": False,
        "imported_count": 0,
        "errors": ["缺少列: 序号"],
    })
    assert r.status == "failed"
    assert r.rows_imported == 0
    assert "缺少列" in r.errors[0]


def test_legacy_row_limit_exceeded():
    """imported_count >= ROW_LIMIT → status=partial + row_limit_exceeded。"""
    r = make_import_result_from_legacy({
        "ok": True,
        "imported_count": ROW_LIMIT,
        "errors": [],
    })
    assert r.status == "partial"
    assert any("row_limit_exceeded" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Tests: workbook_to_bytes
# ---------------------------------------------------------------------------


def test_workbook_to_bytes_produces_valid_xlsx():
    """workbook_to_bytes 应产出以 PK 开头的 ZIP 格式 bytes。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Test"
    ws.append(["col1", "col2"])
    ws.append([1, 2])

    data = workbook_to_bytes(wb)
    assert isinstance(data, bytes)
    assert len(data) > 0
    # xlsx 是 ZIP 格式，PK 开头
    assert data[:2] == b"PK"


# ---------------------------------------------------------------------------
# Tests: TabImportResult dataclass
# ---------------------------------------------------------------------------


def test_tab_import_result_defaults():
    """TabImportResult 默认值正确。"""
    r = TabImportResult(status="success")
    assert r.rows_imported == 0
    assert r.warnings == []
    assert r.errors == []
