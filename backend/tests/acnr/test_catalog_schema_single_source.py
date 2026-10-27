"""T03：目录契约单一来源（design §4.2 / D3）。

- 已提交 schema 文件与 build_schema() 逐字节相等；
- 四类受控约束与常量逐值相等；
- 真实目录 0 错误；4 份历史快照只做加载测试；
- 变异（产物副本）：词表外 functional_type / registry_version 旧形态 / 删 sheet_code /
  给 cell 加 project_id → 各自红并点名 JSON 路径。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from app.services.acnr import catalog_contract as cc

_ACNR = Path(__file__).resolve().parents[2] / "data" / "acnr"
_SCHEMA_FILE = Path(__file__).resolve().parents[2].parent / "docs" / "acnr" / "schemas" / "global_catalog.schema.json"


def test_schema_file_byte_equal_to_build_schema():
    assert _SCHEMA_FILE.exists(), "schema 文件缺失（应由生成器/契约写出）"
    on_disk = _SCHEMA_FILE.read_bytes()
    from_source = cc.schema_json().encode("utf-8")
    assert on_disk == from_source, "schema 文件与 build_schema() 不一致；请重新生成"


def test_schema_is_valid_draft7():
    Draft7Validator.check_schema(cc.build_schema())


def test_controlled_constants_match_schema():
    schema = cc.build_schema()
    sheet = schema["$defs"]["SheetCatalogEntry"]["properties"]
    cell = schema["$defs"]["CellCatalogEntry"]["properties"]

    assert schema["properties"]["registry_version"]["pattern"] == cc.REGISTRY_VERSION_PATTERN
    assert sheet["functional_type"]["enum"] == cc.FUNCTIONAL_TYPES
    assert cell["purpose"]["pattern"] == cc.PURPOSE_PATTERN
    assert sheet["source_of_truth"]["enum"] == cc.SOURCE_OF_TRUTH
    assert sheet["editor_engine"]["enum"] == cc.EDITOR_ENGINES
    assert sheet["skip_reason"]["enum"] == cc.SKIP_REASONS
    # item_id 多值
    assert "oneOf" in sheet["import_export"]["properties"]["item_id"]
    # 禁 project_id / wp_id
    assert schema["not"] == cc.NOT_PROJECT_CTX
    assert schema["$defs"]["SheetCatalogEntry"]["not"] == cc.NOT_PROJECT_CTX
    assert schema["$defs"]["CellCatalogEntry"]["not"] == cc.NOT_PROJECT_CTX
    # additionalProperties:false
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["SheetCatalogEntry"]["additionalProperties"] is False
    assert schema["$defs"]["CellCatalogEntry"]["additionalProperties"] is False


def test_controlled_values_match_current_real_catalog():
    """契约词表必须覆盖真实目录的实际取值（否则 additionalProperties/enum 会误拒真实数据）。"""
    cat = json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))
    import re
    for s in cat["sheets"]:
        ft = s.get("functional_type")
        if ft is not None:
            assert ft in cc.FUNCTIONAL_TYPES, f"目录出现词表外 functional_type: {ft}"
        ee = s.get("editor_engine")
        if ee is not None:
            assert ee in cc.EDITOR_ENGINES
        sot = s.get("source_of_truth")
        if sot is not None:
            assert sot in cc.SOURCE_OF_TRUTH
    pp = re.compile(cc.PURPOSE_PATTERN)
    for c in cat["cells"]:
        p = c.get("purpose")
        if p is not None:
            assert pp.match(p), f"purpose 不合模式: {p}"
    assert re.match(cc.REGISTRY_VERSION_PATTERN, cat["registry_version"])


def test_real_catalog_zero_errors():
    v = Draft7Validator(cc.build_schema())
    cat = json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))
    errs = list(v.iter_errors(cat))
    assert errs == [], [list(e.absolute_path) for e in errs[:10]]


def test_four_snapshots_load_and_validate():
    v = Draft7Validator(cc.build_schema())
    snaps = sorted((_ACNR / "catalog_snapshots").glob("*.json"))
    legacy = {"20260710000000.json", "20260727114611.json", "20260727114738.json", "20260727115337.json"}
    release = json.loads((_ACNR / "catalog_report.json").read_text(encoding="utf-8"))["release"]["registry_version"]
    # 4 份既有快照 + T07 起生成器发布批次的当前版本快照
    assert {s.name for s in snaps} == legacy | {f"{release}.json"}
    for s in snaps:
        data = json.loads(s.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert list(v.iter_errors(data)) == [], s.name


# ─── 变异（产物副本，不改真实目录） ──────────────────────────────────────────


def _good_catalog() -> dict:
    return {
        "version": "1",
        "registry_version": "20260727115337",
        "sheets": [{
            "addr_id": "D2/D2-2", "domain": "wp", "parent_wp_code": "D2",
            "sheet_code": "D2-2", "sheet_name": "明细表D2-2",
        }],
        "cells": [{
            "addr_id": "D2/D2-2/E100", "parent_addr_id": "D2/D2-2",
            "domain": "wp", "formula_ref": "WP('D2','明细表D2-2','E100')",
        }],
    }


def test_mutation_functional_type_out_of_vocab_rejected():
    v = Draft7Validator(cc.build_schema())
    bad = _good_catalog()
    bad["sheets"][0]["functional_type"] = "not_a_real_type"
    errs = list(v.iter_errors(bad))
    assert errs, "词表外 functional_type 应被拒"
    assert any("functional_type" in list(e.absolute_path) for e in errs)


def test_mutation_old_registry_version_rejected():
    v = Draft7Validator(cc.build_schema())
    bad = _good_catalog()
    bad["registry_version"] = "2026.1.1"
    errs = list(v.iter_errors(bad))
    assert errs and any("registry_version" in list(e.absolute_path) for e in errs)


def test_mutation_missing_sheet_code_rejected():
    v = Draft7Validator(cc.build_schema())
    bad = _good_catalog()
    del bad["sheets"][0]["sheet_code"]
    errs = list(v.iter_errors(bad))
    assert errs, "缺 sheet_code 应被拒"


def test_mutation_cell_project_id_rejected():
    v = Draft7Validator(cc.build_schema())
    bad = _good_catalog()
    bad["cells"][0]["project_id"] = "p1"
    bad["cells"][0]["wp_id"] = "w1"
    errs = list(v.iter_errors(bad))
    assert errs, "cell 带 project_id/wp_id 应被 not 约束拒"


# ─── 段四审计 F4-15：import_export 封闭、A1 口径单一来源 ──────────────────────


def test_import_export_closed_extra_field_rejected():
    """import_export 内多余字段被拒（此前新旧 schema 都不拦）；合法字段仍接受。"""
    v = Draft7Validator(cc.build_schema())
    good = _good_catalog()
    good["sheets"][0]["import_export"] = {"enabled": True, "api_prefix": "/api/x", "item_id": ["a", "b"],
                                          "storage_field": "s", "import_order": 1, "depends_on_sheets": ["D2-1"]}
    assert list(v.iter_errors(good)) == []
    bad = copy.deepcopy(good)
    bad["sheets"][0]["import_export"]["bogus"] = 1
    errs = list(v.iter_errors(bad))
    assert errs and any("import_export" in list(e.absolute_path) for e in errs), "import_export 多余字段应被拒"


def test_real_catalog_import_export_fields_within_contract():
    """真实目录 import_export 实际出现的字段 ⊆ 契约字段（封闭前先现算，0 例外）。"""
    cat = json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))
    allowed = set(cc.build_schema()["$defs"]["SheetCatalogEntry"]["properties"]["import_export"]["properties"])
    seen = {k for s in cat["sheets"] if isinstance(s.get("import_export"), dict) for k in s["import_export"]}
    assert seen, "真实目录没有 import_export（防空转）"
    assert seen <= allowed, f"真实目录出现契约外 import_export 字段：{sorted(seen - allowed)}"


def test_a1_pattern_single_source():
    """schema 的 cell_address、exact_identity、发布门禁三处 A1 口径都取 catalog_contract.A1_PATTERN。"""
    from app.services.acnr import catalog_release, exact_identity

    schema = cc.build_schema()
    assert schema["$defs"]["CellCatalogEntry"]["properties"]["cell_address"]["pattern"] == cc.A1_PATTERN
    assert exact_identity._A1_RE.pattern == cc.A1_PATTERN
    assert catalog_release._A1_RE.pattern == cc.A1_PATTERN


def test_mutation_cell_address_outside_a1_pattern_rejected():
    """A1 口径收紧为 1~3 个字母 + 1~7 位数字：4 个字母的列被拒（旧口径 ^[A-Z]+[0-9]+$ 会放过）。"""
    v = Draft7Validator(cc.build_schema())
    bad = _good_catalog()
    bad["cells"][0]["cell_address"] = "ABCD1"
    errs = list(v.iter_errors(bad))
    assert errs and any("cell_address" in list(e.absolute_path) for e in errs)
