"""Tests for ACNR catalog load failure degradation (R23.4, R23.5).

Branch 1: Has old cache → read-only last version + admin alert,
           FORBID silent fallback to scattered JSON.
Branch 2: No old cache → operation fails entirely, require manual intervention.

Requirements: 23.4, 23.5
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.acnr.catalog import (
    CatalogIndex,
    CatalogLoadError,
    _alert_admin,
    _load_catalog,
    get_catalog,
    reload_catalog,
)
import app.services.acnr.catalog as catalog_module


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_catalog_state():
    """Reset module-level catalog state before each test."""
    catalog_module._catalog = None
    catalog_module._last_good_catalog = None
    yield
    catalog_module._catalog = None
    catalog_module._last_good_catalog = None


@pytest.fixture
def valid_catalog_data() -> dict:
    """Minimal valid catalog data for testing."""
    return {
        "version": "1",
        "registry_version": "test-v1",
        "sheets": [
            {
                "addr_id": "D2/D2-2",
                "domain": "wp",
                "origin": "standard",
                "cycle": "D",
                "parent_wp_code": "D2",
                "sheet_code": "D2-2",
                "sheet_name": "明细表D2-2",
                "sheet_name_aliases": ["应收账款明细"],
                "component_type": "d2-accounts-receivable",
            }
        ],
        "cells": [
            {
                "addr_id": "D2/D2-2/E100",
                "parent_addr_id": "D2/D2-2",
                "domain": "wp",
                "cell_address": "E100",
                "semantic_label": "合计行-期末余额",
                "formula_ref": "WP('D2','明细表D2-2','合计行-期末余额')",
                "uri": "wp://D2/明细表D2-2#E100",
            }
        ],
    }


@pytest.fixture
def catalog_file(tmp_path: Path, valid_catalog_data: dict) -> Path:
    """Create a temporary valid catalog file."""
    catalog_path = tmp_path / "global_catalog.json"
    catalog_path.write_text(json.dumps(valid_catalog_data), encoding="utf-8")
    return catalog_path


# ─── 正常加载测试 ─────────────────────────────────────────────────────────────


class TestNormalLoad:
    """Normal catalog load updates _last_good_catalog."""

    def test_successful_load_saves_last_good(
        self, catalog_file: Path, valid_catalog_data: dict
    ):
        """After successful load, _last_good_catalog is populated."""
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            result = _load_catalog()

        assert result is not None
        assert result.registry_version == "test-v1"
        assert catalog_module._last_good_catalog is result

    def test_successful_load_returns_cached(self, catalog_file: Path):
        """Second call returns cached instance without re-reading file."""
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            first = _load_catalog()
            # Delete the file — should still return cached
            catalog_file.unlink()
            second = _load_catalog()

        assert first is second


# ─── Branch 1: 有旧缓存 → 只读上一版 + 告警 ─────────────────────────────────


class TestBranch1HasOldCache:
    """R23.4: Load failure with old cache → read-only last version + alert."""

    def test_file_not_found_falls_back_to_last_good(
        self, catalog_file: Path, valid_catalog_data: dict
    ):
        """FileNotFoundError → use _last_good_catalog."""
        # First: load successfully to populate _last_good_catalog
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            first_load = _load_catalog()

        # Now simulate failure: reset _catalog, point to missing file
        catalog_module._catalog = None
        missing_path = str(catalog_file.parent / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            result = _load_catalog()

        # Should return the old cache, not raise
        assert result is first_load
        assert result.registry_version == "test-v1"

    def test_json_decode_error_falls_back_to_last_good(
        self, catalog_file: Path, tmp_path: Path
    ):
        """JSONDecodeError → use _last_good_catalog."""
        # First: load successfully
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            first_load = _load_catalog()

        # Write invalid JSON
        bad_file = tmp_path / "bad_catalog.json"
        bad_file.write_text("{invalid json!!!", encoding="utf-8")
        catalog_module._catalog = None

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(bad_file)}):
            result = _load_catalog()

        assert result is first_load

    def test_os_error_falls_back_to_last_good(
        self, catalog_file: Path, tmp_path: Path
    ):
        """OSError (permission denied etc.) → use _last_good_catalog."""
        # First: load successfully
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            first_load = _load_catalog()

        catalog_module._catalog = None

        # Simulate OSError by patching Path.read_text
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
                result = _load_catalog()

        assert result is first_load

    def test_alert_admin_called_on_degradation(
        self, catalog_file: Path, tmp_path: Path
    ):
        """管理告警在降级时被调用。"""
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            _load_catalog()

        catalog_module._catalog = None
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            with patch(
                "app.services.acnr.catalog._alert_admin"
            ) as mock_alert:
                _load_catalog()

        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[0][0] == "catalog_load_failed"

    def test_no_silent_fallback_to_scattered_json(
        self, catalog_file: Path, tmp_path: Path
    ):
        """R23.4 关键约束: 绝不静默退回分散 JSON 文件。

        验证降级后返回的是 _last_good_catalog (CatalogIndex 实例),
        不是空 CatalogIndex 或从其他 JSON 文件读取的内容。
        """
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            first_load = _load_catalog()

        catalog_module._catalog = None
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            result = _load_catalog()

        # Must be the exact same CatalogIndex from the last good load
        assert result is catalog_module._last_good_catalog
        # Must have actual data (not empty)
        assert len(result.sheets_by_addr_id) > 0
        assert result.registry_version == "test-v1"

    def test_degraded_catalog_is_functionally_usable(
        self, catalog_file: Path, tmp_path: Path
    ):
        """降级后的 catalog 可被 get_catalog() 正常使用。"""
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            _load_catalog()

        catalog_module._catalog = None
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            cat = get_catalog()

        # Should be able to use it for lookups
        assert "D2/D2-2" in cat.sheets_by_addr_id
        assert "D2/D2-2/E100" in cat.cells_by_addr_id


# ─── Branch 2: 无旧缓存 → 操作整体失败 ──────────────────────────────────────


class TestBranch2NoOldCache:
    """R23.5: Load failure without old cache → operation fails entirely."""

    def test_file_not_found_no_cache_raises(self, tmp_path: Path):
        """FileNotFoundError + no cache → CatalogLoadError."""
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            with pytest.raises(CatalogLoadError) as exc_info:
                _load_catalog()

        assert "操作整体失败" in str(exc_info.value)

    def test_json_decode_error_no_cache_raises(self, tmp_path: Path):
        """JSONDecodeError + no cache → CatalogLoadError."""
        bad_file = tmp_path / "bad_catalog.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(bad_file)}):
            with pytest.raises(CatalogLoadError):
                _load_catalog()

    def test_os_error_no_cache_raises(self, tmp_path: Path, catalog_file: Path):
        """OSError + no cache → CatalogLoadError."""
        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": str(catalog_file)}):
            with patch.object(Path, "read_text", side_effect=OSError("Disk failure")):
                with pytest.raises(CatalogLoadError):
                    _load_catalog()

    def test_alert_admin_called_before_raise(self, tmp_path: Path):
        """管理告警在抛异常前被调用。"""
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            with patch(
                "app.services.acnr.catalog._alert_admin"
            ) as mock_alert:
                with pytest.raises(CatalogLoadError):
                    _load_catalog()

        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[0][0] == "catalog_load_failed_no_cache"

    def test_original_exception_chained(self, tmp_path: Path):
        """CatalogLoadError chains the original exception."""
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            with pytest.raises(CatalogLoadError) as exc_info:
                _load_catalog()

        assert exc_info.value.__cause__ is not None
        assert isinstance(
            exc_info.value.__cause__, (FileNotFoundError, OSError)
        )

    def test_get_catalog_propagates_error(self, tmp_path: Path):
        """get_catalog() also raises CatalogLoadError when no cache."""
        missing_path = str(tmp_path / "nonexistent.json")

        with patch.dict("os.environ", {"ACNR_CATALOG_PATH": missing_path}):
            with pytest.raises(CatalogLoadError):
                get_catalog()


# ─── _alert_admin 单元测试 ────────────────────────────────────────────────────


class TestAlertAdmin:
    """_alert_admin function unit tests."""

    def test_alert_logs_warning(self, caplog):
        """_alert_admin logs at WARNING level."""
        with caplog.at_level(logging.WARNING):
            _alert_admin("test_event", "some details")

        assert "ACNR 管理告警" in caplog.text
        assert "test_event" in caplog.text
        assert "some details" in caplog.text

    def test_alert_does_not_raise(self):
        """_alert_admin should never raise an exception itself."""
        # Should not raise even with unusual inputs
        _alert_admin("", "")
        _alert_admin("event_with_special_chars", "错误：文件不存在 (ENOENT)")
