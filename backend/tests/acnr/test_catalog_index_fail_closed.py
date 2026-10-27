"""T08 CatalogIndex fail-closed 与加载期互校（design §5.5 / D4）。

合成三类 addr_id 重复各一例 → CatalogIntegrityError；真实目录与 4 份历史快照
全部可加载；临时目录注入重复验证「无缓存失败」与「有缓存降级 + 告警」；加载期
互校：release 段版本号 / sha256 不一致 → CatalogIntegrityError，无 release 段跳过。

不写任何仓库产物（临时目录用 tmp_path）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.acnr import catalog as cat_mod
from app.services.acnr.catalog import (
    CatalogIndex,
    CatalogIntegrityError,
    CatalogLoadError,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ACNR_DIR = _REPO_ROOT / "backend" / "data" / "acnr"
_CATALOG_PATH = _ACNR_DIR / "global_catalog.json"
_SNAPSHOT_DIR = _ACNR_DIR / "catalog_snapshots"


def _one_sheet(addr="D2/D2-1", code="D2-1", parent="D2", name="应收账款审定表"):
    return {
        "addr_id": addr,
        "domain": "wp",
        "parent_wp_code": parent,
        "sheet_code": code,
        "sheet_name": name,
    }


def _one_cell(addr="D2/D2-1/E10", parent="D2/D2-1"):
    return {
        "addr_id": addr,
        "parent_addr_id": parent,
        "domain": "wp",
        "formula_ref": f"WP('D2','D2-1','E10')",
        "cell_address": "E10",
    }


# ─── 三类 addr_id 重复各一例 ─────────────────────────────────────────────────


def test_duplicate_sheet_addr_id_fail_closed():
    data = {"version": "1", "registry_version": "20261027000000",
            "sheets": [_one_sheet(), _one_sheet()], "cells": []}
    with pytest.raises(CatalogIntegrityError) as exc:
        CatalogIndex(data)
    assert "D2/D2-1" in str(exc.value)
    assert "sheets 内" in str(exc.value)


def test_duplicate_cell_addr_id_fail_closed():
    data = {"version": "1", "registry_version": "20261027000000",
            "sheets": [_one_sheet()], "cells": [_one_cell(), _one_cell()]}
    with pytest.raises(CatalogIntegrityError) as exc:
        CatalogIndex(data)
    assert "cells 内" in str(exc.value)


def test_sheet_cell_cross_collision_fail_closed():
    data = {"version": "1", "registry_version": "20261027000000",
            "sheets": [_one_sheet()],
            "cells": [_one_cell(addr="D2/D2-1", parent="D2/D2-1")]}
    with pytest.raises(CatalogIntegrityError) as exc:
        CatalogIndex(data)
    assert "同时是 sheet 与 cell" in str(exc.value)


def test_integrity_error_is_load_error_subclass():
    # §8 版本锁映射 409 依赖此继承关系
    assert issubclass(CatalogIntegrityError, CatalogLoadError)


# ─── 新索引建立 ─────────────────────────────────────────────────────────────


def test_indices_built():
    data = {
        "version": "1", "registry_version": "20261027000000",
        "sheets": [
            _one_sheet("D2/D2-1", "D2-1"),
            _one_sheet("D2/D2-2", "D2-2", name="应收账款明细表"),
        ],
        "cells": [],
    }
    idx = CatalogIndex(data)
    assert set(idx.sheets_by_parent) == {"D2"}
    assert len(idx.sheets_by_parent["D2"]) == 2
    assert idx.forbidden_aliases == {}


def test_forbidden_alias_index_built():
    data = {
        "version": "1", "registry_version": "20261027000000",
        "sheets": [
            {**_one_sheet("D2/D2-1", "D2-1"), "sheet_name_aliases": ["共用名"]},
            {**_one_sheet("D2/D2-2", "D2-2", name="明细"), "sheet_name_aliases": ["共用名"]},
        ],
        "cells": [],
    }
    idx = CatalogIndex(data)
    assert ("D2", "共用名") in idx.forbidden_aliases
    assert idx.forbidden_aliases[("D2", "共用名")] == ["D2-1", "D2-2"]


# ─── 真实目录与历史快照全部可加载 ───────────────────────────────────────────


def test_real_catalog_loads():
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    idx = CatalogIndex(data)  # 不应抛（真实目录无重复 addr_id）
    assert len(idx.sheets_by_addr_id) >= 1000


def test_all_snapshots_load():
    if not _SNAPSHOT_DIR.exists():
        pytest.skip("无快照目录")
    snaps = sorted(_SNAPSHOT_DIR.glob("*.json"))
    assert snaps, "应至少有 1 份历史快照"
    for fp in snaps:
        data = json.loads(fp.read_text(encoding="utf-8"))
        CatalogIndex(data)  # 全部可加载，不抛


# ─── _load_catalog 降级分支（临时目录注入重复） ─────────────────────────────


def _write_dup_catalog(dirpath: Path) -> Path:
    data = {"version": "1", "registry_version": "20261027000000",
            "sheets": [_one_sheet(), _one_sheet()], "cells": []}
    fp = dirpath / "global_catalog.json"
    fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return fp


def test_load_catalog_integrity_fail_no_cache(tmp_path, monkeypatch):
    fp = _write_dup_catalog(tmp_path)
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    with pytest.raises(CatalogIntegrityError):
        cat_mod._load_catalog()


def test_load_catalog_integrity_degrades_with_cache(tmp_path, monkeypatch, caplog):
    # 有上一版缓存 → 只读上一版 + 告警（不抛）
    good = CatalogIndex({"version": "1", "registry_version": "20261027000000",
                         "sheets": [_one_sheet()], "cells": []})
    fp = _write_dup_catalog(tmp_path)
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", good, raising=False)
    with caplog.at_level("WARNING"):
        got = cat_mod._load_catalog()
    assert got is good
    assert any("catalog_integrity_failed" in r.getMessage() for r in caplog.records)


# ─── 加载期互校（release 段） ───────────────────────────────────────────────


def _write_valid_catalog(dirpath: Path, registry_version="20261027000000") -> tuple[Path, str]:
    data = {"version": "1", "registry_version": registry_version,
            "sheets": [_one_sheet()], "cells": []}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fp = dirpath / "global_catalog.json"
    fp.write_text(raw, encoding="utf-8")
    return fp, raw


def test_cross_check_no_release_segment_skipped(tmp_path, monkeypatch):
    fp, _ = _write_valid_catalog(tmp_path)
    # 旧格式报告：无 release 段 → 跳过互校，正常加载
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"registry_version": "20261027000000", "summary": {}}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    idx = cat_mod._load_catalog()
    assert idx.registry_version == "20261027000000"


def test_cross_check_version_mismatch_fail(tmp_path, monkeypatch):
    fp, raw = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "99999999999999"}}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    with pytest.raises(CatalogIntegrityError) as exc:
        cat_mod._load_catalog()
    assert "registry_version" in str(exc.value)


def test_cross_check_sha256_mismatch_fail(tmp_path, monkeypatch):
    fp, raw = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "20261027000000",
                                 "catalog_sha256": "0" * 64}}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    with pytest.raises(CatalogIntegrityError) as exc:
        cat_mod._load_catalog()
    assert "sha256" in str(exc.value)


def test_cross_check_sha256_match_ok(tmp_path, monkeypatch):
    fp, raw = _write_valid_catalog(tmp_path)
    actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "20261027000000",
                                 "catalog_sha256": actual}}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    idx = cat_mod._load_catalog()
    assert idx.registry_version == "20261027000000"
