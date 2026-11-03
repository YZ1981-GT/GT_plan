"""可逆合并附注 UAT 工具的纯函数与 fail-closed 安全门。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/e2e/note_pull_residual_uat.py"
SPEC = importlib.util.spec_from_file_location("note_pull_residual_uat", SCRIPT)
assert SPEC and SPEC.loader
uat = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = uat
SPEC.loader.exec_module(uat)


def test_canonical_hash_ignores_object_key_order_but_keeps_array_order() -> None:
    assert uat.digest({"b": 2, "a": 1}) == uat.digest({"a": 1, "b": 2})
    assert uat.digest({"rows": [1, 2]}) != uat.digest({"rows": [2, 1]})


def test_table_hash_distinguishes_sql_null_marker() -> None:
    row = json.dumps({"id": "00000000-0000-0000-0000-000000000001", "data": None})
    plain = [{"row": row, "json_null": []}]
    json_null = [{"row": row, "json_null": ["data"]}]
    assert uat.table_digest("x", {}, plain) != uat.table_digest("x", {}, json_null)


def test_table_name_is_strictly_whitelisted() -> None:
    assert uat._safe_table("consol_note_data") == "consol_note_data"
    for bad in ("x;drop table projects", "public.x", 'x"'):
        with pytest.raises(ValueError, match="非法表名"):
            uat._safe_table(bad)


def test_verified_backup_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    payload = {"format": uat.FORMAT, "中文": [1, 2, 3]}
    uat._write_verified(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob("*.tmp"))


def _args(action: str, **overrides):
    values = {
        "action": action,
        "project": "00000000-0000-0000-0000-000000000001",
        "year": 2025,
        "confirm_project_name": "【测试】集团",
        "backup": Path("backup.json"),
        "run_id": None,
        "apply": False,
    }
    values.update(overrides)
    return type("Args", (), values)()


@pytest.mark.parametrize("action", ["inject", "restore"])
def test_database_write_actions_require_apply(action: str) -> None:
    with pytest.raises(ValueError, match="--apply"):
        uat._validate_args(_args(action))
    uat._validate_args(_args(action, apply=True))


def test_targeted_actions_require_exact_identity() -> None:
    with pytest.raises(ValueError, match="--project"):
        uat._validate_args(_args("snapshot", project=None))
    with pytest.raises(ValueError, match="--backup"):
        uat._validate_args(_args("capture-after", backup=None))


def test_run_id_rejects_untrusted_text() -> None:
    with pytest.raises(ValueError, match="run-id"):
        uat._validate_args(_args("snapshot", run_id="bad;sql"))


def test_replace_table_preserves_unrelated_tables_and_replaces_exact_name() -> None:
    old = {"_tables": [{"name": "A", "rows": [[1]]}, {"name": "B", "rows": [[2]]}]}
    new = uat._replace_table(old, {"name": "A", "rows": [[3]]})
    assert [item["name"] for item in new["_tables"]] == ["A", "B"]
    assert new["_tables"][0]["rows"] == [[3]]
    assert old["_tables"][0]["rows"] == [[1]], "不得原地改备份输入"


def test_topn_fixture_has_cross_entity_duplicate_and_group_peer() -> None:
    one = uat._topn_fixture("run1", 0, "【测试】乙")
    two = uat._topn_fixture("run1", 1, "【测试】甲")
    names1 = [row["label"] for row in one["rows"] if row.get("row_type") == "data"]
    names2 = [row["label"] for row in two["rows"] if row.get("row_type") == "data"]
    assert "NRG-run1-共同客户" in names1
    assert "NRG-run1-共同 客户" in names2
    assert "【测试】乙" in names1 and "【测试】甲" in names2
    assert len(names1) + len(names2) > 5


def test_hash_guard_names_every_drifted_table() -> None:
    exports = {"a": {"before_hash": "1"}, "b": {"before_hash": "2"}}
    with pytest.raises(RuntimeError, match="b"):
        uat._assert_hashes(exports, {"a": "1", "b": "x"}, "恢复前")


def test_tree_facts_uses_api_tree_and_requires_two_data_leaves(monkeypatch) -> None:
    tree = {
        "role": "consol", "node_key": "root", "kind": "root", "children": [
            {"kind": "data", "node_key": "a", "project_id": "p-a", "company_name": "甲", "children": []},
            {"kind": "data", "node_key": "b", "project_id": "p-b", "company_name": "乙", "children": []},
        ],
    }
    monkeypatch.setattr(uat, "api_get", lambda *_args: {"tree": tree})
    facts = uat.tree_facts("p", "secret", "http://127.0.0.1")
    assert facts["root_node_key"] == "root"
    assert [leaf["project_id"] for leaf in facts["leaves"]] == ["p-a", "p-b"]
    assert len(facts["tree_hash"]) == 64


def test_tree_facts_fails_closed_for_non_group_or_one_leaf(monkeypatch) -> None:
    monkeypatch.setattr(uat, "api_get", lambda *_args: {"role": "data", "children": []})
    with pytest.raises(RuntimeError, match="不是 consol"):
        uat.tree_facts("p", "secret", "http://127.0.0.1")

    monkeypatch.setattr(uat, "api_get", lambda *_args: {
        "role": "consol", "node_key": "root", "children": [
            {"kind": "data", "node_key": "a", "project_id": "p-a", "children": []},
        ],
    })
    with pytest.raises(RuntimeError, match="只有 1 个"):
        uat.tree_facts("p", "secret", "http://127.0.0.1")


def test_detail_fixture_defines_columns_used_by_mapping_amounts() -> None:
    one = uat._detail_fixture(1)
    two = uat._detail_fixture(2)
    expected_keys = [
        "label", "end_amount", "end_provision", "end_loss_rate",
        "prior_amount", "prior_provision", "prior_loss_rate",
    ]
    assert [column["key"] for column in one["columns"]] == expected_keys
    assert len(one["headers"]) == len(one["columns"])
    assert all(len(row["values"]) == len(one["columns"]) - 1 for row in one["rows"])
    assert one["rows"][0]["values"][0] + two["rows"][0]["values"][0] == 300
    assert one["rows"][0]["values"][3] + two["rows"][0]["values"][3] == 240


def test_new_injection_round_clears_stale_after_and_restore_state() -> None:
    backup = {
        "after_hashes": {"consol_note_data": "old"},
        "after_counts": {"consol_note_data": 1},
        "captured_after_at": "old-capture",
        "restored": True,
        "restored_at": "old-restore",
    }
    uat._reset_after_for_new_injection(backup)
    assert backup["after_hashes"] is None
    assert backup["after_counts"] is None
    assert backup["restored"] is False
    assert "captured_after_at" not in backup
    assert "restored_at" not in backup
