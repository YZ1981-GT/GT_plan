"""名称对齐层 `row_name_alignment` 守卫 + PBT。

覆盖：
- classify 四态不变式（Property 1，Requirement 5.2）：归一后多命中必 ambiguous，
  绝不当 auto_matched 直接出数
- 目标身份 stale 不变式（Property 2，Requirement 1.4）
- 多对一重复引用告警不变式（Property 3，Requirement 2.4 / 5.1）
- unmatched 无值语义不变式（Property 6，Requirement 5.1）

spec: .kiro/specs/formula-row-name-alignment-confirmation/
"""
from __future__ import annotations

from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.four_table.row_name_alignment import (
    SOURCE_ACCOUNT,
    SOURCE_AUX,
    Candidate,
    MatchState,
    SavedMapping,
    TargetIdentity,
    classify,
    normalize_name,
    resolve_amounts,
    similarity,
)


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────


def _target(name: str, code: str = "1221", aux_type: str | None = "客户",
            ds: str | None = "ds-active") -> TargetIdentity:
    from app.services.four_table.row_name_alignment import _dimension_key

    return TargetIdentity(
        source_kind=SOURCE_AUX,
        account_code=code,
        aux_type=aux_type,
        aux_name=name,
        dimension_key=_dimension_key(code, aux_type, name),
        dataset_id=ds,
    )


def _cand(name: str, row_label: str, amount: float = 100.0, **kw) -> Candidate:
    t = _target(name, **kw)
    return Candidate(
        target=t,
        display_name=name,
        normalized_name=normalize_name(name),
        amount=Decimal(str(amount)),
        similarity=similarity(row_label, name),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 归一 / 相似度纯函数
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_folds_fullwidth_and_whitespace():
    # 全角空格 + 全角字母 → 折叠
    assert normalize_name("ＡＢＣ　公司") == normalize_name("abc公司")


def test_normalize_strips_common_suffix():
    assert normalize_name("华为技术有限公司") == normalize_name("华为技术")


def test_normalize_does_not_overstrip_when_equals_suffix():
    # 名字本身就是「公司」时不剥空（len > suffix 才剥）
    assert normalize_name("公司") == "公司"


def test_similarity_identical_is_one():
    assert similarity("应收甲公司", "应收甲公司") == 1.0


def test_similarity_disjoint_is_zero():
    assert similarity("甲", "乙丙丁") == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Property 1: classify 四态 + 多命中必 ambiguous
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_unique_exact_is_auto_matched():
    res = classify("预收销售款", [_cand("预收销售款", "预收销售款")])
    assert res.state is MatchState.AUTO_MATCHED
    assert len(res.matched_targets) == 1


def test_classify_normalized_multi_hit_is_ambiguous_not_auto():
    """归一后两个候选同名 → 必 ambiguous，绝不 auto_matched（Requirement 5.2）。"""
    # 两个候选归一后都等于 "预收款"（一个带后缀、一个全角空格）
    cands = [
        _cand("预收款", "预收款", code="2203"),
        _cand("预收款 ", "预收款", code="2205"),
    ]
    res = classify("预收款", cands)
    assert res.state is MatchState.AMBIGUOUS


def test_classify_similar_but_not_exact_is_ambiguous():
    """相似度命中但归一后不相等 → ambiguous，不得直接出数。

    「应收账款甲」与「应收账款乙」归一后不相等（末字不同），但二元组重叠高
    → 相似度 >= 阈值 → ambiguous。
    """
    res = classify("应收账款甲", [_cand("应收账款乙", "应收账款甲", amount=5.0)])
    assert res.state is MatchState.AMBIGUOUS


def test_classify_zero_candidate_is_unmatched():
    assert classify("任何行名", []).state is MatchState.UNMATCHED


def test_classify_no_similar_candidate_is_unmatched():
    res = classify("张三", [_cand("完全不相关的很长的名字", "张三")])
    assert res.state is MatchState.UNMATCHED


_names = st.text(
    alphabet="预收销售款项甲乙丙abc 公司",
    min_size=1,
    max_size=8,
)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(row=_names, cand_names=st.lists(_names, min_size=0, max_size=6))
def test_property_classify_always_returns_valid_state(row, cand_names):
    """Property 1：返回值必属四态之一。"""
    cands = [_cand(n, row) for n in cand_names]
    res = classify(row, cands)
    assert res.state in set(MatchState)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(row=_names)
def test_property_normalized_multi_hit_never_auto(row):
    """Property 1：同一归一名的多个候选 → 永不 auto_matched。"""
    # 造两个归一后都等于 row 的候选（不同 account_code 保证是两条）
    cands = [
        _cand(row, row, code="1001"),
        _cand(row + " ", row, code="1002"),  # 尾部空白归一后相同
    ]
    res = classify(row, cands)
    assert res.state is not MatchState.AUTO_MATCHED


# ─────────────────────────────────────────────────────────────────────────────
# Property 2: 目标身份 stale 不变式
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_saved_mapping_valid_is_user_confirmed():
    t = _target("应收甲")
    mapping = SavedMapping(row_key="r1", targets=(t,))
    cand = _cand("应收甲", "应收甲")  # 同身份候选存在
    res = classify("应收甲", [cand], mapping)
    assert res.state is MatchState.USER_CONFIRMED


def test_classify_saved_mapping_stale_falls_back_unmatched():
    """已确认目标在当前候选身份集消失 → stale ⇒ UNMATCHED（不复用过期映射）。"""
    saved_t = _target("应收甲", ds="ds-OLD")  # dataset 变了
    mapping = SavedMapping(row_key="r1", targets=(saved_t,))
    cand = _cand("应收甲", "应收甲", ds="ds-active")  # 当前 active 是新 dataset
    res = classify("应收甲", [cand], mapping)
    assert res.state is MatchState.UNMATCHED
    assert res.stale_reason


def test_classify_saved_mapping_stale_by_missing_name():
    """明细名整个消失 → stale ⇒ UNMATCHED。"""
    saved_t = _target("已注销单位")
    mapping = SavedMapping(row_key="r1", targets=(saved_t,))
    res = classify("行名", [_cand("别的单位", "行名")], mapping)
    assert res.state is MatchState.UNMATCHED


# ─────────────────────────────────────────────────────────────────────────────
# Property 3: 多对一重复引用告警
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_multi_to_one_flags_duplicate():
    """两个 row_key 引用同一目标身份 → 两行都标 duplicate_reference。"""
    shared = _target("共享单位")
    mappings = {
        "r1": SavedMapping(row_key="r1", targets=(shared,)),
        "r2": SavedMapping(row_key="r2", targets=(shared,)),
    }
    amounts = {shared.identity_tuple(): Decimal("500")}
    out = resolve_amounts(mappings, amounts)
    assert out["r1"].duplicate_reference is True
    assert out["r2"].duplicate_reference is True
    # DEC-3：不自动去重，各行各自聚合
    assert out["r1"].amount == Decimal("500")
    assert out["r2"].amount == Decimal("500")


def test_resolve_no_share_no_duplicate_flag():
    a = _target("单位A", code="1001")
    b = _target("单位B", code="1002")
    mappings = {
        "r1": SavedMapping(row_key="r1", targets=(a,)),
        "r2": SavedMapping(row_key="r2", targets=(b,)),
    }
    amounts = {a.identity_tuple(): Decimal("1"), b.identity_tuple(): Decimal("2")}
    out = resolve_amounts(mappings, amounts)
    assert out["r1"].duplicate_reference is False
    assert out["r2"].duplicate_reference is False


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(n=st.integers(min_value=2, max_value=5))
def test_property_shared_target_all_flagged(n):
    """Property 3：任意多个 row_key 共享同一目标 → 全部标 duplicate。"""
    shared = _target("共享")
    mappings = {
        f"r{i}": SavedMapping(row_key=f"r{i}", targets=(shared,)) for i in range(n)
    }
    amounts = {shared.identity_tuple(): Decimal("10")}
    out = resolve_amounts(mappings, amounts)
    assert all(out[f"r{i}"].duplicate_reference for i in range(n))


# ─────────────────────────────────────────────────────────────────────────────
# Property 6: unmatched 无值语义
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_stale_row_has_none_amount():
    """stale 行金额必须是 None（无值），不得是 0。"""
    t = _target("单位")
    mappings = {"r1": SavedMapping(row_key="r1", targets=(t,))}
    amounts = {t.identity_tuple(): Decimal("999")}
    out = resolve_amounts(
        mappings, amounts, stale_reasons={"r1": "目标已失效"}
    )
    assert out["r1"].amount is None
    assert out["r1"].state is MatchState.UNMATCHED
    assert out["r1"].stale_reason == "目标已失效"


def test_resolve_unmatched_state_has_none_amount():
    t = _target("单位")
    mappings = {"r1": SavedMapping(row_key="r1", targets=(t,))}
    amounts = {t.identity_tuple(): Decimal("999")}
    out = resolve_amounts(
        mappings, amounts, states={"r1": MatchState.UNMATCHED}
    )
    assert out["r1"].amount is None


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(amt=st.decimals(min_value=0, max_value=Decimal("1e9"), allow_nan=False,
                       allow_infinity=False, places=2))
def test_property_confirmed_row_sums_targets(amt):
    """user_confirmed 行金额 == 其目标身份金额之和（非 0/非上期）。"""
    t = _target("单位")
    mappings = {"r1": SavedMapping(row_key="r1", targets=(t,))}
    amounts = {t.identity_tuple(): amt}
    out = resolve_amounts(mappings, amounts, states={"r1": MatchState.USER_CONFIRMED})
    assert out["r1"].amount == amt
