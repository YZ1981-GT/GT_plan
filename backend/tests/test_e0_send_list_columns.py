"""test_e0_send_list_columns — e0-send-list-components 契约/属性测试

覆盖 Property 1（四清单列 == 源模板 manifest，无 col_* 占位）、
Property 2（枚举/日期/金额语义）、Property 3（_reviewed 防重生成覆盖）、
Property 7（既有数据回显 — 键为业务 snake_case 后可 round-trip）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[1]
_E0_YAML = _BACKEND / "data" / "ledger_adapters" / "wp_render_schema" / "generated" / "E0.yaml"
_MANIFEST = _BACKEND / "data" / "e0_send_list_source_manifest.json"
_GENERATOR = _BACKEND / "scripts" / "gen" / "generate_wp_render_schema.py"

_SEND_LIST_SHEETS = [
    "货币资金发函记录表E0-3",
    "借款发函记录表E0-4",
    "应付银行承兑汇票发函记录表E0-5",
    "理财产品发函记录表E0-6",
]


@pytest.fixture(scope="module")
def e0_schema() -> dict:
    return yaml.safe_load(_E0_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _columns(schema: dict, sheet: str) -> dict:
    return schema["sheets"][sheet]["dynamic_table"]["columns"]


# ─── Property 1: 四清单渲染列 == 源模板清单，无 col_* 占位 ────────────────────

def test_manifest_covers_four_send_list_sheets(manifest):
    assert set(manifest["sheets"].keys()) == set(_SEND_LIST_SHEETS)


@pytest.mark.parametrize("sheet", _SEND_LIST_SHEETS)
def test_columns_match_manifest(e0_schema, manifest, sheet):
    yaml_cols = _columns(e0_schema, sheet)
    spec_cols = manifest["sheets"][sheet]["cell_columns"]
    # 列集合（cell 键）与顺序一致
    assert list(yaml_cols.keys()) == list(spec_cols.keys()), f"{sheet} 列顺序/集合不一致"
    for cell, spec in spec_cols.items():
        col = yaml_cols[cell]
        assert col.get("field") == spec["field"], f"{sheet}.{cell} field 不一致"
        assert col.get("label") == spec["label"], f"{sheet}.{cell} label 不一致"
        assert col.get("type") == spec["type"], f"{sheet}.{cell} type 不一致"


@pytest.mark.parametrize("sheet", _SEND_LIST_SHEETS)
def test_no_col_placeholder_fields(e0_schema, sheet):
    for cell, col in _columns(e0_schema, sheet).items():
        assert not str(col.get("field", "")).startswith("col_"), (
            f"{sheet}.{cell} 仍是 col_* 占位字段"
        )


# ─── Property 2: 枚举/日期/金额语义正确 ──────────────────────────────────────

@pytest.mark.parametrize("sheet", _SEND_LIST_SHEETS)
def test_enum_date_amount_semantics(e0_schema, manifest, sheet):
    yaml_cols = _columns(e0_schema, sheet)
    spec_cols = manifest["sheets"][sheet]["cell_columns"]
    for cell, spec in spec_cols.items():
        col = yaml_cols[cell]
        if spec["type"] == "enum":
            assert col.get("type") == "enum"
            assert col.get("enum") == spec["enum"], f"{sheet}.{cell} enum 选项不一致"
            assert isinstance(col["enum"], list) and col["enum"], "enum 必须为非空列表"
        elif spec["type"] == "date":
            assert col.get("type") == "date"
        if spec.get("render") == "amount":
            assert col.get("render") == "amount"
            assert col.get("type") == "number"


def test_is_confirm_column_exists_for_pull_upstream(e0_schema):
    """Property 5 上游可靠性：E0-3/E0-4 必须有 is_confirm 列供「清单→E0-1 带入」候选。"""
    for sheet in ("货币资金发函记录表E0-3", "借款发函记录表E0-4"):
        fields = [c.get("field") for c in _columns(e0_schema, sheet).values()]
        assert "is_confirm" in fields, f"{sheet} 缺 is_confirm（是否函证）列"


def test_restriction_flag_no_amount_column(e0_schema):
    """Property 6：E0-3 受限标志为枚举可筛选，且不新增受限金额列。"""
    cols = _columns(e0_schema, "货币资金发函记录表E0-3")
    has_restriction = [c for c in cols.values() if c.get("field") == "has_restriction"]
    assert has_restriction and has_restriction[0].get("type") == "enum"
    # 不存在受限金额列（源模板未定义）
    assert not any(
        c.get("field", "").startswith("restriction") and c.get("render") == "amount"
        for c in cols.values()
    )


# ─── Property 3: _reviewed 防覆盖 ────────────────────────────────────────────

def test_send_list_sheets_marked_reviewed(e0_schema):
    for sheet in _SEND_LIST_SHEETS:
        assert e0_schema["sheets"][sheet].get("_reviewed") is True, f"{sheet} 未标 _reviewed"


def _load_generator():
    spec = importlib.util.spec_from_file_location("_gen_wp_schema", _GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_regeneration_preserves_reviewed_columns():
    """模拟生成器重新检测（col_* 占位）→ preserve_reviewed_sheets 后审定 columns 逐字不变。"""
    gen = _load_generator()
    reviewed_snapshot = yaml.safe_load(_E0_YAML.read_text(encoding="utf-8"))["sheets"]
    # 模拟自动检测把四清单 sheet 打回 col_* 占位
    fresh = {"sheets": {}}
    for sheet in _SEND_LIST_SHEETS:
        fresh["sheets"][sheet] = {
            "component_type": "d-form-confirmation",
            "dynamic_table": {
                "columns": {
                    cell: {"field": f"col_{cell.lower()}", "type": "text", "label": "GARBLED"}
                    for cell in reviewed_snapshot[sheet]["dynamic_table"]["columns"]
                }
            },
        }
    preserved = gen.preserve_reviewed_sheets(fresh, _E0_YAML)
    assert preserved == len(_SEND_LIST_SHEETS)
    for sheet in _SEND_LIST_SHEETS:
        assert (
            fresh["sheets"][sheet]["dynamic_table"]["columns"]
            == reviewed_snapshot[sheet]["dynamic_table"]["columns"]
        ), f"{sheet} 审定 columns 被覆盖"
        # 未被打回 col_* 占位
        for col in fresh["sheets"][sheet]["dynamic_table"]["columns"].values():
            assert not col["field"].startswith("col_")


def test_preserve_no_op_when_output_missing(tmp_path):
    gen = _load_generator()
    fresh = {"sheets": {"x": {"_reviewed": True}}}
    assert gen.preserve_reviewed_sheets(fresh, tmp_path / "nope.yaml") == 0


# ─── Property 5: Confirm_Flag 候选去重（是否函证=是 才进候选） ──────────────────
#
# 说明：实际「清单→E0-1 带入」实现归 confirmation-hub-workbench-tabs；此处以纯函数
# 建模本 spec 保证的上游数据契约（仅 is_confirm='是' 的行进入候选集合，按被询证单位+
# 账号去重），不依赖 confirmation-hub，也不触库/前端。

def _select_confirm_candidates(rows: list[dict], party_field: str, account_field: str) -> list[dict]:
    """纯函数：模拟 Confirm_Flag 驱动的候选筛选 + 去重。

    - 仅 is_confirm == '是' 的行进入候选
    - 按 (被询证单位, 账号) 去重（首个赢），保证重复带入不产生重复候选
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in rows:
        if r.get("is_confirm") != "是":
            continue
        key = (str(r.get(party_field, "")).strip(), str(r.get(account_field, "")).strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def test_confirm_candidate_only_yes_rows():
    rows = [
        {"is_confirm": "是", "bank_name": "工行", "bank_account": "001"},
        {"is_confirm": "否", "bank_name": "农行", "bank_account": "002"},
        {"is_confirm": "", "bank_name": "中行", "bank_account": "003"},
    ]
    cands = _select_confirm_candidates(rows, "bank_name", "bank_account")
    assert [c["bank_name"] for c in cands] == ["工行"]


def test_confirm_candidate_dedup_by_party_account():
    rows = [
        {"is_confirm": "是", "bank_name": "工行", "bank_account": "001"},
        {"is_confirm": "是", "bank_name": "工行", "bank_account": "001"},  # 重复带入
        {"is_confirm": "是", "bank_name": "工行", "bank_account": "002"},  # 同行不同账号保留
    ]
    cands = _select_confirm_candidates(rows, "bank_name", "bank_account")
    assert len(cands) == 2
    assert {c["bank_account"] for c in cands} == {"001", "002"}


# ─── Property 7: 既有数据回显 round-trip（业务 snake_case 键） ───────────────────

def test_field_keys_roundtrip_stable(e0_schema, manifest):
    """审定后每列 field 是业务 snake_case，作为 checklist_responses 存取键可 round-trip。"""
    for sheet in _SEND_LIST_SHEETS:
        yaml_fields = [c["field"] for c in _columns(e0_schema, sheet).values()]
        spec_fields = [c["field"] for c in manifest["sheets"][sheet]["cell_columns"].values()]
        assert yaml_fields == spec_fields
        # field 均为合法 snake_case（可作存储键），无 col_* 占位、无空
        for f in yaml_fields:
            assert f and not f.startswith("col_") and f.replace("_", "").isalnum()


# ─── Property 8: 四表取数不臆造（无捏造账户明细/来源列） ─────────────────────────
#
# 决策（design 决策 6 + Requirement 5.3）：四表库无账户级维度时不臆造账户明细。
# 本 spec 只落源模板真实列，SHALL NOT 向 schema 注入任何「自动取数/来源」占位列。

_FABRICATION_MARKERS = ("pull", "auto_", "source", "from_ledger", "data_source", "_generated")


@pytest.mark.parametrize("sheet", _SEND_LIST_SHEETS)
def test_no_fabricated_pull_or_source_columns(e0_schema, manifest, sheet):
    yaml_cols = _columns(e0_schema, sheet)
    spec_cols = manifest["sheets"][sheet]["cell_columns"]
    # 列数不多不少（无注入捏造列），且 field 与源模板 manifest 完全一致
    assert len(yaml_cols) == len(spec_cols), f"{sheet} 列数与源模板不一致（疑似臆造列）"
    for cell, col in yaml_cols.items():
        field = str(col.get("field", ""))
        assert not any(m in field for m in _FABRICATION_MARKERS), (
            f"{sheet}.{cell} 疑似臆造取数/来源列: {field}"
        )
        assert field == spec_cols[cell]["field"], f"{sheet}.{cell} field 偏离源模板"
