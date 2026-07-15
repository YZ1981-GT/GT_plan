"""PBT: 锁定版本确定性 — 同 input + 同 version → 幂等 [P11]

**Validates: Requirements 9.1, 9.2, 9.3**

Property P11: 对于同一 input (addr_id) + 同一 locked registry_version，
full_resolve 的返回值应当完全一致（幂等/确定性）。

额外验证：
- load_versioned_catalog 对同一 version 始终返回相同 CatalogIndex
- 版本缺失时正确抛出 VersionNotFoundError
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ─── 路径设置 ──────────────────────────────────────────────────────────────
import sys

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.resolver import (
    load_versioned_catalog,
    VersionNotFoundError,
    full_resolve,
    _CATALOG_SNAPSHOTS_DIR,
)
from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.immutability import (
    record_project_registry_version,
    remove_project_registry_version,
    _project_registry_versions,
)


# ─── Strategies ───────────────────────────────────────────────────────────────

# 合法 wp_code 样式的 addr_id
st_wp_code = st.from_regex(r"[A-N]\d{1,2}", fullmatch=True)
st_sheet_code = st.from_regex(r"[A-N]\d{1,2}-\d{1,2}", fullmatch=True)
st_addr_id = st.builds(
    lambda wp, sheet: f"{wp}/{sheet}",
    st_wp_code,
    st_sheet_code,
)

# 版本号 = 时间戳格式字符串
st_version = st.from_regex(r"20[2-3]\d[01]\d[0-3]\d[0-2]\d[0-5]\d[0-5]\d", fullmatch=True)

# 项目 ID = UUID 格式
st_project_id = st.uuids().map(str)


# ─── Fixtures / Helpers ───────────────────────────────────────────────────────


def _create_snapshot(tmp_dir: Path, version: str, sheets: list[dict] | None = None) -> Path:
    """在临时目录创建一个 catalog snapshot 文件。"""
    snapshot_path = tmp_dir / f"{version}.json"
    catalog_data = {
        "version": "1",
        "registry_version": version,
        "sheets": sheets or [
            {
                "addr_id": "D2/D2-2",
                "sheet_code": "D2-2",
                "sheet_name": "明细表D2-2",
                "domain": "wp",
                "parent_wp_code": "D2",
                "cycle": "D",
                "sheet_name_aliases": [],
            }
        ],
        "cells": [
            {
                "addr_id": "D2/D2-2/E100",
                "parent_addr_id": "D2/D2-2",
                "domain": "wp",
                "cell_address": "E100",
                "semantic_label": "应收账款合计",
                "formula_ref": "WP('D2','D2-2','E100')",
                "uri": "wp://D2/明细表D2-2#E100",
            }
        ],
    }
    snapshot_path.write_text(
        json.dumps(catalog_data, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return snapshot_path


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestVersionNotFoundError:
    """VersionNotFoundError 基本行为。"""

    def test_raises_on_missing_version(self, tmp_path: Path):
        """版本缺失时 load_versioned_catalog 抛出 VersionNotFoundError。"""
        # 清除 LRU 缓存
        load_versioned_catalog.cache_clear()

        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        try:
            with pytest.raises(VersionNotFoundError) as exc_info:
                load_versioned_catalog("99999999999999")

            assert "99999999999999" in str(exc_info.value)
            assert exc_info.value.version == "99999999999999"
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            load_versioned_catalog.cache_clear()

    def test_loads_existing_version(self, tmp_path: Path):
        """存在的版本快照能成功加载为 CatalogIndex。"""
        load_versioned_catalog.cache_clear()

        version = "20260715120000"
        _create_snapshot(tmp_path, version)

        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        try:
            cat = load_versioned_catalog(version)
            assert isinstance(cat, CatalogIndex)
            assert cat.registry_version == version
            assert "D2/D2-2" in cat.sheets_by_addr_id
            assert "D2/D2-2/E100" in cat.cells_by_addr_id
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            load_versioned_catalog.cache_clear()


class TestLoadVersionedCatalogLRU:
    """LRU 缓存行为验证。"""

    def test_lru_returns_same_instance(self, tmp_path: Path):
        """同一 version 多次调用返回同一对象（LRU 缓存）。"""
        load_versioned_catalog.cache_clear()

        version = "20260715130000"
        _create_snapshot(tmp_path, version)

        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        try:
            cat1 = load_versioned_catalog(version)
            cat2 = load_versioned_catalog(version)
            assert cat1 is cat2  # 同一对象引用 = LRU 命中
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            load_versioned_catalog.cache_clear()


class TestVersionedResolveDeterminism:
    """P11: 同 input + 同 version → 幂等。"""

    @settings(max_examples=5, deadline=None)
    @given(
        addr_id=st_addr_id,
        version=st_version,
        project_id=st_project_id,
    )
    def test_same_input_same_version_yields_identical_result(
        self, addr_id: str, version: str, project_id: str, tmp_path: Path
    ):
        """PBT: 对同一 addr_id + 同一 locked version，full_resolve 幂等。

        **Validates: Requirements 9.1**
        """
        import asyncio
        load_versioned_catalog.cache_clear()

        # 创建对应版本快照
        _create_snapshot(tmp_path, version)

        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        # 注册项目锁定版本
        record_project_registry_version(project_id, version)

        # Mock 当前 catalog version 为不同值（触发版本分支）
        from app.services.acnr.catalog import get_catalog as real_get_catalog

        try:
            # 设置当前 catalog version 与 locked 不同
            mock_cat = CatalogIndex({
                "version": "1",
                "registry_version": "CURRENT_DIFFERENT",
                "sheets": [],
                "cells": [],
            })

            with patch("app.services.acnr.resolver.get_catalog", return_value=mock_cat):
                # 两次调用应产生完全一致的结果
                result1 = asyncio.run(full_resolve(addr_id=addr_id, project_id=project_id))
                result2 = asyncio.run(full_resolve(addr_id=addr_id, project_id=project_id))

            # 核心断言：幂等性
            assert result1.found == result2.found
            assert result1.addr_id == result2.addr_id
            assert result1.entry_type == result2.entry_type
            assert result1.cell_address == result2.cell_address
            assert result1.semantic_label == result2.semantic_label
            assert result1.error == result2.error
            assert result1.source_layer == result2.source_layer
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            remove_project_registry_version(project_id)
            load_versioned_catalog.cache_clear()

    @settings(max_examples=5, deadline=None)
    @given(
        version=st_version,
        project_id=st_project_id,
    )
    def test_version_not_found_raises_deterministically(
        self, version: str, project_id: str, tmp_path: Path
    ):
        """PBT: 不存在的版本始终抛出 VersionNotFoundError。

        **Validates: Requirements 9.3**
        """
        import asyncio
        load_versioned_catalog.cache_clear()

        # 不创建快照 → 版本不存在
        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        record_project_registry_version(project_id, version)

        try:
            mock_cat = CatalogIndex({
                "version": "1",
                "registry_version": "DIFFERENT",
                "sheets": [],
                "cells": [],
            })

            with patch("app.services.acnr.resolver.get_catalog", return_value=mock_cat):
                with pytest.raises(VersionNotFoundError) as exc_info:
                    asyncio.run(full_resolve(addr_id="D2/D2-2/E100", project_id=project_id))

                assert exc_info.value.version == version
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            remove_project_registry_version(project_id)
            load_versioned_catalog.cache_clear()

    @settings(max_examples=5, deadline=None)
    @given(version=st_version)
    def test_load_versioned_catalog_idempotent(self, version: str, tmp_path: Path):
        """PBT: load_versioned_catalog 对同一 version 返回内容一致的 CatalogIndex。

        **Validates: Requirements 9.2**
        """
        load_versioned_catalog.cache_clear()

        _create_snapshot(tmp_path, version)

        import app.services.acnr.resolver as resolver_mod
        original_dir = resolver_mod._CATALOG_SNAPSHOTS_DIR
        resolver_mod._CATALOG_SNAPSHOTS_DIR = tmp_path

        try:
            cat_a = load_versioned_catalog(version)
            # 清缓存强制重新加载
            load_versioned_catalog.cache_clear()
            cat_b = load_versioned_catalog(version)

            # 内容一致
            assert cat_a.registry_version == cat_b.registry_version
            assert set(cat_a.sheets_by_addr_id.keys()) == set(cat_b.sheets_by_addr_id.keys())
            assert set(cat_a.cells_by_addr_id.keys()) == set(cat_b.cells_by_addr_id.keys())
        finally:
            resolver_mod._CATALOG_SNAPSHOTS_DIR = original_dir
            load_versioned_catalog.cache_clear()
