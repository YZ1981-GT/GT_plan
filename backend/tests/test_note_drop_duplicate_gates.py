"""重复编号行软删的四道硬门与「业务实值」判定（spec disclosure-note-template-word-realignment Phase 8 Task 5）。

纯逻辑守卫：业务实值识别（跳过结构键 / 零样值 / 合计 ratio=100）与四道门的组合判据。真库软删路径由
`realign_project_notes.py --drop`（宜宾 dry-run / apply）验收。
"""
from __future__ import annotations

from app.services.note_project_realign_apply import _business_values


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
