"""T08 CatalogIndex fail-closed 与加载期互校（design §5.5 / D4；段四审计 F4-07 返工）。

合成三类 addr_id 重复各一例 → CatalogIntegrityError；真实目录与 4 份历史快照
全部可加载；临时目录注入重复验证「无缓存失败」与「有缓存降级 + 告警」。

加载期互校（规则在 catalog_integrity.check_release_report）：release 段缺字段 / 版本号 /
sha256 不一致 → CatalogIntegrityError；无 release 段只在过渡期登记存在时跳过；默认生产路径
缺报告失败；内容哈希按 LF 规范内容（CRLF 落盘同一哈希）。生产报告：断言存在，且「有 release
段 ⇒ 互校真实执行（release_check_status == checked）」「无 release 段 ⇒ 必须是登记的那份
旧报告」——T07 写漏或写错 release 段都会红，互校不会永久空转。

不写任何仓库产物（临时目录用 tmp_path）。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.acnr import catalog as cat_mod
from app.services.acnr import catalog_integrity as ci
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


#: 需求 4.5 / design §5.6：4 份既有快照内容不变（LF 规范内容 sha256，与检出平台无关）。
_SNAPSHOT_CONTENT_SHA256 = {
    "20260710000000.json": "8645205d291992d306760346cfc9faf75a44c456fec727899f75c74a6ff914c5",
    "20260727114611.json": "ba831e5f75e1857b4cf3e2d25a9a543786070f21cc390445e8b33191c018fa62",
    "20260727114738.json": "8c0a7c47ec3211cde808cb52adb167b301931811dfd9794b653840e0d1b31e7c",
    "20260727115337.json": "e98a127ed7c4f275b41c0e3315585479e0d1f36b122a2cded1fc1abdade3126e",
    # 已被新批次取代的发布批次快照同样不可变：每发布一个新批次，把上一批次快照的内容哈希追加到这里（只增）
    "20261027130014.json": "63ffa79465bd22cbe998e06ee5c17433ad682382f202d1da4bd1e42dcb676bdd",  # T07 首个合规批次
    "20261027145857.json": "c64daad9f533c88a77a405541168df3c148e82bd0bf1f24c79cd0bd4a49e8075",  # T09 批次
    "20261027161822.json": "b171acc97ef47a856a2a5030ccbae05ab8e445fb4664b8489e8e3cf38f878bf7",  # T10 批次
    "20261028075152.json": "5d2d5fd96e7589022ff93913639d67232f0c9baf4767778d191976a5eaac5755",  # T22 批次
    "20261028130507.json": "7d8477ceeec4a997bde230787f5240af1cf8c6c74d5d81aaa84b402f5cbd18bd",  # 段十 wp_account_mapping 输入变化批次
    "20261028151046.json": "36f8fe261a86b2e4dc8f3065a3b86dfabc3b83b3898139c8b4138dc6f23e4a47",  # 段十 RV10.1-02 批次
    "20261029002303.json": "ae5ee0cfd7dc8de7d20d29f40406e26bc7b23f02364c5a89cc240b9db0626a73",  # T29 统一显示名批次
    "20261029075533.json": "b3a08722f11cdb1ea8b10c0a8e3ca0b2cc903d92c3f36e34f4b284e51dc64f6f",  # 单元格坐标复核前的末批次
}


def test_snapshot_content_hashes_pinned():
    got = {fp.name: ci.content_sha256(fp.read_bytes()) for fp in sorted(_SNAPSHOT_DIR.glob("*.json"))}
    pinned = {k: got.get(k) for k in _SNAPSHOT_CONTENT_SHA256}
    assert pinned == _SNAPSHOT_CONTENT_SHA256, "既有快照内容被改动或被删（需求 4.5：只能新增快照，不能改旧快照）"
    # 新增快照只能是生成器发布批次：当前 release 版本的快照，内容与报告 release.catalog_sha256 相同（T07）
    release = json.loads((_SNAPSHOT_DIR.parent / "catalog_report.json").read_text(encoding="utf-8"))["release"]
    extra = {k: v for k, v in got.items() if k not in _SNAPSHOT_CONTENT_SHA256}
    assert extra == {f"{release['registry_version']}.json": release["catalog_sha256"]}, extra


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


def _fresh_load(monkeypatch, fp: Path | None):
    """清缓存后按 fp（None = 默认生产路径）真实加载一次。"""
    if fp is None:
        monkeypatch.delenv("ACNR_CATALOG_PATH", raising=False)
    else:
        monkeypatch.setenv("ACNR_CATALOG_PATH", str(fp))
    monkeypatch.setattr(cat_mod, "_catalog", None, raising=False)
    monkeypatch.setattr(cat_mod, "_last_good_catalog", None, raising=False)
    return cat_mod._load_catalog()


def test_cross_check_no_release_segment_skipped_while_legacy_registered(tmp_path, monkeypatch):
    fp, _ = _write_valid_catalog(tmp_path)
    # 旧格式报告：无 release 段；过渡期登记存在 → 跳过互校。T07 首个合规发布批次后生产登记已删除（None），
    # 这里注入一条登记只为覆盖 legacy_skip 分支本身（生产登记为 None 由 test_production_report_release_or_registered_legacy 钉住）
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"registry_version": "20261027000000", "summary": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(ci, "LEGACY_REPORT_WITHOUT_RELEASE", {"report_sha256": "x", "registry_version": "20261027000000"})
    idx = _fresh_load(monkeypatch, fp)
    assert idx.registry_version == "20261027000000"
    assert idx.release_check_status == "legacy_skip"


def test_cross_check_no_release_segment_rejected_after_legacy_removed(tmp_path, monkeypatch):
    fp, _ = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"registry_version": "20261027000000", "summary": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(ci, "LEGACY_REPORT_WITHOUT_RELEASE", None)
    with pytest.raises(CatalogIntegrityError) as exc:
        _fresh_load(monkeypatch, fp)
    assert "缺 release 段" in str(exc.value)


def test_cross_check_release_missing_field_rejected(tmp_path, monkeypatch):
    """release 段存在但缺 catalog_sha256（或键名写错）→ 拒绝，不再「缺字段就跳过」。"""
    fp, _ = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "20261027000000", "catalog_hash": "x"}}),
        encoding="utf-8",
    )
    with pytest.raises(CatalogIntegrityError) as exc:
        _fresh_load(monkeypatch, fp)
    assert "缺字段" in str(exc.value) and "catalog_sha256" in str(exc.value)


def test_cross_check_unparseable_report_rejected(tmp_path, monkeypatch):
    fp, _ = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogIntegrityError) as exc:
        _fresh_load(monkeypatch, fp)
    assert "无法读取或解析" in str(exc.value)


def test_cross_check_missing_report_in_test_dir_skipped(tmp_path, monkeypatch):
    fp, _ = _write_valid_catalog(tmp_path)
    idx = _fresh_load(monkeypatch, fp)
    assert idx.release_check_status == "no_report"


def test_cross_check_missing_report_on_default_path_rejected(tmp_path, monkeypatch):
    """默认生产路径旁缺报告 → 失败（design §5.5）。用临时文件冒充默认路径。"""
    fp, _ = _write_valid_catalog(tmp_path)
    monkeypatch.setattr(cat_mod, "_CATALOG_PATH", fp)
    with pytest.raises(CatalogIntegrityError) as exc:
        _fresh_load(monkeypatch, None)
    assert "缺 catalog_report.json" in str(exc.value)


def test_content_sha256_is_lf_normalized():
    """内容哈希口径 = LF 规范内容（git blob 内容），CRLF 与 LF 两种字节形态同一哈希。"""
    lf = b'{\n  "a": 1\n}\n'
    crlf = lf.replace(b"\n", b"\r\n")
    assert ci.content_sha256(crlf) == ci.content_sha256(lf) == hashlib.sha256(lf).hexdigest()
    assert ci.content_sha256(crlf.decode("utf-8")) == hashlib.sha256(lf).hexdigest()


def test_cross_check_crlf_catalog_file_matches_lf_hash(tmp_path, monkeypatch):
    """目录文件按 CRLF 落盘（Windows autocrlf 检出形态），报告记 LF 内容哈希 → 互校通过。"""
    _, raw = _write_valid_catalog(tmp_path)
    fp = tmp_path / "global_catalog.json"
    fp.write_bytes(raw.replace("\n", "\r\n").encode("utf-8"))
    lf_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "20261027000000", "catalog_sha256": lf_sha}}),
        encoding="utf-8",
    )
    idx = _fresh_load(monkeypatch, fp)
    assert idx.release_check_status == "checked"


def test_production_report_exists():
    """tasks T08 原文验收：守卫断言生产路径报告存在。"""
    assert (_ACNR_DIR / "catalog_report.json").is_file()


def test_production_report_release_or_registered_legacy(monkeypatch):
    """生产报告：有 release 段 ⇒ 互校真实执行且通过、过渡期登记必须已删除；
    无 release 段 ⇒ 必须是登记的那份旧报告（内容哈希相等）且登记未过期。
    T07 写漏 release 段或写错键名、报告被改动，都会让本用例红（不会永久空转）。"""
    report_text = (_ACNR_DIR / "catalog_report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    legacy = ci.LEGACY_REPORT_WITHOUT_RELEASE
    idx = _fresh_load(monkeypatch, None)
    if ci.REPORT_RELEASE_KEY in report:
        assert legacy is None, "生产报告已有 release 段：过渡期登记 LEGACY_REPORT_WITHOUT_RELEASE 已失效，须删除"
        assert idx.release_check_status == "checked"
    else:
        assert legacy is not None, "生产报告无 release 段且无过渡期登记：加载器应拒绝"
        assert ci.content_sha256(report_text) == legacy["report_sha256"], (
            "生产报告内容已变（不是登记的过渡期旧报告）：T07 须写出带 release 段的报告，或更正登记"
        )
        assert legacy["owner"] and legacy["reason"] and legacy["retire_when"]
        assert date.fromisoformat(legacy["expires_on"]) >= date.today(), "过渡期登记已过期"
        assert idx.release_check_status == "legacy_skip"


def test_cross_check_version_mismatch_fail(tmp_path, monkeypatch):
    fp, raw = _write_valid_catalog(tmp_path)
    (tmp_path / "catalog_report.json").write_text(
        json.dumps({"release": {"registry_version": "99999999999999",
                                 "catalog_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}}),
        encoding="utf-8",
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
    assert idx.release_check_status == "checked"
