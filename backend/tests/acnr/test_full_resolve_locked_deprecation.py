"""锁定项目命中停用条目时，替代地址的显示名取锁定目录（段七复审 RV7-04）。

full_resolve 在项目锁定到别的版本时改用锁定快照解析；命中停用 sheet / cell 后，
`reason` 里「建议改用 …」的显示名也必须取这份锁定快照——当前目录里没有该替代地址时，
取当前目录会退回成 addr_id。故障注在下一层 `load_versioned_catalog`（不替换被测的 full_resolve）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

import app.services.acnr.resolver as resolver_mod
from app.services.acnr.catalog import CatalogIndex, get_catalog
from app.services.acnr.immutability import (
    record_project_registry_version,
    remove_project_registry_version,
)

_LOCKED_VERSION = "20200101000000"
_OLD = "Z9/Z9-1"
_NEW = "Z9/Z9-2"
_NEW_LABEL = "锁定版替代表Z9-2"


def _locked_index() -> CatalogIndex:
    sheet = {"domain": "wp", "parent_wp_code": "Z9", "cycle": "Z", "sheet_name_aliases": []}
    return CatalogIndex({
        "version": "1",
        "registry_version": _LOCKED_VERSION,
        "sheets": [
            {**sheet, "addr_id": _OLD, "sheet_code": "Z9-1", "sheet_name": "旧表Z9-1",
             "deprecated": True, "replaced_by": _NEW},
            {**sheet, "addr_id": _NEW, "sheet_code": "Z9-2", "sheet_name": _NEW_LABEL},
        ],
        "cells": [
            {"addr_id": f"{_OLD}/B5", "parent_addr_id": _OLD, "domain": "wp", "cell_address": "B5",
             "semantic_label": "旧格", "formula_ref": "WP('Z9','Z9-1','B5')", "uri": "wp://Z9/Z9-1#B5",
             "deprecated": True, "replaced_by": _NEW},
        ],
    })


@pytest.fixture
def locked_project(monkeypatch):
    assert _NEW not in get_catalog().sheets_by_addr_id, "前提：当前目录里没有该替代地址"
    locked = _locked_index()
    monkeypatch.setattr(resolver_mod, "load_versioned_catalog", lambda version: locked)
    pid = str(uuid4())
    record_project_registry_version(pid, _LOCKED_VERSION)
    yield pid
    remove_project_registry_version(pid)


@pytest.mark.parametrize("addr_id", [_OLD, f"{_OLD}/B5"], ids=["sheet", "cell"])
async def test_replacement_label_comes_from_locked_catalog(locked_project, addr_id):
    res = await resolver_mod.full_resolve(addr_id=addr_id, project_id=locked_project)
    assert res.found and res.deprecated and res.replaced_by == _NEW
    assert _NEW_LABEL in (res.reason or ""), res.reason


async def test_without_lock_current_catalog_is_used():
    """未锁定时照旧用当前目录：同一 addr_id 在当前目录不存在 ⇒ 不命中（对照组，证明上例确实走了锁定快照）。"""
    res = await resolver_mod.full_resolve(addr_id=_OLD)
    assert not res.found
