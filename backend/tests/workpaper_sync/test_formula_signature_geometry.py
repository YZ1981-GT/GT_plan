# -*- coding: utf-8 -*-
"""公式签名按受管表几何归一（spec oo-writeback-template-parity-closure R6 / R4 / R5）。

* R6：OO 在表内插行 / 删行后，引用合计行、表首末行、表内他行的公式签名不变；引用真被改，签名仍不同；
* R4：签名能按落点几何换回公式文本（还原用），落不了地的返回 None；
* R5：转置表没有公式字段（实证），不需要证据。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import formula_recompute_evidence as FE


def sig(text: str, row: int, frame=(12, 22)) -> str:
    return FE.formula_signature(text, own_row=row, frame=frame)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        # 合计行在表下方第 2 行；表内插 2 行后合计行下移 2 行
        (("=IF(C13=0,0,C13/$C$24)", 13, (12, 22)), ("=IF(C15=0,0,C15/$C$26)", 15, (12, 24))),
        # 区间覆盖整个数据区
        (("=C15/SUM(C$12:C$22)", 15, (12, 22)), ("=C16/SUM(C$12:C$24)", 16, (12, 24))),
        # 表内上一行（累计余额）：插在别处，相对位置不变
        (("=E15+F14", 15, (12, 22)), ("=E18+F17", 18, (12, 25))),
        # 删行：表缩短 1 行
        (("=D20/$D$24", 20, (12, 22)), ("=D19/$D$23", 19, (12, 21))),
    ],
)
def test_signature_survives_insert_and_delete(before, after) -> None:
    assert sig(before[0], before[1], before[2]) == sig(after[0], after[1], after[2])


def test_tokens() -> None:
    assert sig("=IF(C13=0,0,C13/$C$24)", 13) == "=IF(C{r}=0,0,C{r}/$C${end+2})"
    assert sig("=C15/SUM(C$12:C$22)", 15) == "=C{r}/SUM(C${start}:C${end})"
    assert sig("=E15+F14", 15) == "=E{r}+F{r-1}"
    assert sig("=E15+F17", 15) == "=E{r}+F{r+2}"
    assert sig("=C13*$B$5", 13) == "=C{r}*$B$5", "表上方的行逐字保留"
    assert sig("='明细表G3-2'!C21+C13", 13) == "='明细表G3-2'!C21+C{r}", "跨表引用逐字保留"
    assert FE.formula_signature("=C13/$C$24", own_row=13) == "=C{r}/$C$24", "不给几何时与修订前相同"


@pytest.mark.parametrize(
    ("original", "edited"),
    [
        ("=IF(C13=0,0,C13/$C$24)", "=IF(C13=0,0,C13/$C$23)"),  # 合计行改成末行
        ("=C15/SUM(C$12:C$22)", "=C15/SUM(C$13:C$22)"),        # 区间起点挪了
        ("=E15+F14", "=E15+F13"),                              # 上一行改成上两行
    ],
)
def test_real_reference_edits_stay_visible(original: str, edited: str) -> None:
    row = int(original.split("C")[1][:2]) if original.startswith("=IF") else 15
    assert sig(original, row) != sig(edited, row)


def test_sentinel_text_disables_normalization() -> None:
    text = "=C13*1048577+C24"
    assert sig(text, 13) == text


def test_transposed_tables_have_no_formula_fields() -> None:
    """R5 的前提实证：注册的转置表受管字段全是 editable（转置提取遇到公式格直接抛错），
    没有受保护公式格可判 ⇒ 不存在「拿不到公式证据而误报冲突」的格。"""
    from app.services.workpaper_sync import contracts as C
    from app.services.workpaper_sync.transposed_registry import REGISTRY

    keys = {spec.sheet_key for spec in REGISTRY}
    seen = set()
    for adapter_id in ("d4.revenue_detail", "g4.ecl_stage", "g6.ecl_stage"):
        for sheet in C.load_contract(adapter_id).sheets:
            if sheet.sheet_key in keys:
                seen.add(sheet.sheet_key)
                assert {f.mode for t in sheet.tables for f in t.fields} == {C.FieldMode.editable}
    assert seen == keys - {"g509-managed"}, seen  # G5-9 尚未接入任何契约


# ── R4：签名换回公式文本 ─────────────────────────────────────────────────────


def test_instantiate_round_trip_examples() -> None:
    cases = [
        ("=IF(C13=0,0,C13/$C$24)", 13, (12, 22)),
        ("=C15/SUM(C$12:C$22)", 15, (12, 22)),
        ("=E15+F14", 15, (12, 22)),
        ("=SUM(B13:M13)", 13, None),
    ]
    for text, row, frame in cases:
        assert FE.instantiate_signature(sig(text, row, frame), row=row, frame=frame) == text


def test_instantiate_into_shifted_geometry() -> None:
    """已发布形态的签名落到 OO 插过行的文件里：合计行跟着下移。"""
    base = sig("=IF(C13=0,0,C13/$C$24)", 13)
    assert FE.instantiate_signature(base, row=15, frame=(12, 24)) == "=IF(C15=0,0,C15/$C$26)"


def test_instantiate_refuses_what_it_cannot_place() -> None:
    assert FE.instantiate_signature("=C{r}/$C${end+2}", row=13, frame=None) is None
    assert FE.instantiate_signature("=SUM({1,2})+C{r}", row=5, frame=(1, 9)) is None


@settings(max_examples=5, deadline=None)
@given(
    first=st.integers(min_value=5, max_value=40),
    length=st.integers(min_value=2, max_value=30),
    pick=st.integers(min_value=0, max_value=10_000),
    below=st.integers(min_value=1, max_value=5),
)
def test_round_trip_property(first: int, length: int, pick: int, below: int) -> None:
    last = first + length
    own = first + pick % (length + 1)
    other = first + (pick // 7) % (length + 1)
    text = f"=C{own}+D{other}/$E${last + below}+$B$2"
    assert FE.instantiate_signature(sig(text, own, (first, last)), row=own, frame=(first, last)) == text
