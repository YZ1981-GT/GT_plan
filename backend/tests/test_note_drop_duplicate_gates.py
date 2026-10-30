"""重复编号行软删的四道硬门与「业务实值」判定（spec disclosure-note-template-word-realignment Phase 8 Task 5）。

纯逻辑守卫：业务实值识别（跳过结构键 / 零样值 / 合计 ratio=100）与四道门的组合判据。真库软删路径由
`realign_project_notes.py --drop`（宜宾 dry-run / apply）验收。
"""
from __future__ import annotations

from app.services.note_project_realign_apply import _business_values, _drop_protection_reasons


def test_business_values_skips_structural_and_zero_samples() -> None:
    td = {
        "sub_table_data": {
            "按坏账计提方法分类披露": [
                {"label": "合 计", "ratio": 100, "book_amount": 0, "carrying_value": 0},
            ],
            "本期计提、收回或转回的减值准备情况": [
                {"label": "期初余额", "row_key": "opening"},
                {"label": "本期计提", "row_key": "provision"},
            ],
        }
    }
    assert _business_values(td) == []  # ratio=100 / 0 / row_key 全不算实值


def test_business_values_detects_real_numbers() -> None:
    td = {
        "sub_table_data": {
            "按账龄披露": [
                {"label": "1 年以内", "amount": 1234567.89, "ratio": 100},
            ]
        }
    }
    vals = _business_values(td)
    assert ("按账龄披露.1 年以内.amount", 1234567.89) in vals
    assert all("ratio" not in k for k, _v in vals)  # ratio=100 仍被排除


def test_business_values_reads_flat_tables() -> None:
    td = {"_tables": [{"name": "货币资金", "rows": [{"label": "银行存款", "values": [0, 500.0, "/"]}]}]}
    assert _business_values(td) == [("货币资金.银行存款.1", 500.0)]


def test_business_values_handles_non_dict() -> None:
    assert _business_values(None) == []
    assert _business_values({"headers": [], "rows": []}) == []


def test_mutation_guard_ratio_100_is_not_a_real_value() -> None:
    """变异证明：若把 ratio=100 当实值（从排除集移除 100），上面两条「无实值」用例会红。"""
    from app.services import note_project_realign_apply as mod

    assert 100 in mod._DROP_EMPTY_VALUES, "合计 ratio=100 必须在零样值集合内，否则无实值判据失效"


def test_business_values_reads_legacy_top_level_rows() -> None:
    td = {"name": "旧单表", "rows": [{"label": "客户甲", "values": [0, 88]}]}
    assert _business_values(td) == [("旧单表.客户甲.1", 88)]


def test_amount_100_is_real_but_ratio_100_is_template_sample() -> None:
    td = {"sub_table_data": {"明细": [{"label": "A", "amount": 100, "ratio": 100}]}}
    assert _business_values(td) == [("明细.A.amount", 100)]


def test_nested_business_value_does_not_raise_unhashable_error() -> None:
    payload = {"source": "人工", "amounts": [1, 2]}
    td = {"sub_table_data": {"明细": [{"label": "A", "extra": payload}]}}
    assert _business_values(td) == [("明细.A.extra", payload)]


def test_text_content_is_part_of_delete_safety_gate() -> None:
    from app.services.note_project_realign_apply import _has_text

    assert _has_text("<p>审计师填写的说明</p>") is True
    assert _has_text("<p><br></p>&nbsp;") is False


def test_manual_and_locked_zero_are_business_values_but_auto_zero_is_not() -> None:
    for mode in ("manual", "locked"):
        td = {"_tables": [{"name": "明细", "rows": [
            {"label": "A", "values": [0], "_cell_modes": {"0": mode}},
        ]}]}
        assert _business_values(td) == [("明细.A.0", 0)]
    assert _business_values({"rows": [
        {"label": "A", "values": [0], "_cell_modes": {"0": "auto"}},
        {"label": "B", "values": [None], "_cell_modes": {"0": "manual"}},
    ]}) == []


def test_structured_manual_zero_is_preserved_without_treating_metadata_as_value() -> None:
    td = {"rows": [
        {"label": "A", "values": [{"value": 0, "mode": "manual"}]},
        {"label": "B", "values": [{"value": 0, "mode": "auto", "binding": {"id": "x"}}]},
        {"label": "C", "values": [{"mode": "locked"}]},
    ]}
    assert _business_values(td) == [("table.A.0", 0)]


def test_manual_override_and_orphans_are_independent_delete_blockers() -> None:
    assert _drop_protection_reasons({"_manual_override": True}) == ["manual_override:top"]
    assert _drop_protection_reasons({"sub_table_data": {"_manual_override": True}}) == [
        "manual_override:sub_table_data"
    ]
    assert _drop_protection_reasons({"_realign_orphans": [{"values": [0]}]}) == ["realign_orphans:1"]
    assert _drop_protection_reasons({"_realign_orphans": {"unexpected": True}}) == [
        "realign_orphans:malformed"
    ]
    assert _drop_protection_reasons({"_manual_override": "true", "_realign_orphans": []}) == []
