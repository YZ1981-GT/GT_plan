"""F1 取数链路补齐守卫（减值准备双口径 + 辅助余额归集关联方自动识别）。

两组被测对象都是**纯函数**，故本文件不碰 DB：

1. :func:`resolve_impairment_prefill` —— 合并 ``tb_balance`` 反解路径与
   ``trial_balance`` 标准码路径。背景（postgres 实证，项目 ``0ec33ac9`` / 2025）：
   ``account_mapping`` 无 ``1231-04`` 记录而 ``trial_balance`` 有
   ``1231-04 坏账准备-预付账款`` 行 → 旧单路径恒 ``None``。

2. :func:`match_related_party` / :func:`build_f1_detail_rows_from_aux` ——
   四表入库后 F1-2 自动归集的行原先一律标 ``非关联方``，而 render 早已下发
   ``related_parties``（取自 ``related_party_registry``）。

spec: .kiro/specs/f1-extraction-chain-and-disclosure-source-fidelity/ (Task 2.5)
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._f1_import_export import (
    F1_RELATION_MATCHED,
    F1_RELATION_NONE,
    build_f1_detail_rows_from_aux,
    match_related_party,
)
from app.routers.wp_render_strategies._f1_prepayment import resolve_impairment_prefill


class _Seg:
    """账龄段替身（只需 `.key`）。"""

    def __init__(self, key: str, label: str = "") -> None:
        self.key = key
        self.label = label or key


_SEGS = [_Seg("within1", "1年以内"), _Seg("y1to2", "1至2年"), _Seg("over2", "2年以上")]


def _rid_factory():
    counter = {"n": 0}

    def make() -> str:
        counter["n"] += 1
        return f"row-{counter['n']}"

    return make


# ════════════════════ Property 5：减值准备合并的宁缺勿造 ════════════════════


def test_impairment_both_empty_returns_none():
    assert resolve_impairment_prefill(None, None) is None


def test_impairment_trial_zero_is_not_a_hit():
    """`trial_balance` 里 `1231-04` 常有一行但金额为 0 —— 0 不算命中。"""
    assert resolve_impairment_prefill(None, 0.0) is None
    assert resolve_impairment_prefill(None, 1e-12) is None
    assert resolve_impairment_prefill({}, 0.0) is None


def test_impairment_trial_only_gives_end_without_prior():
    """trial_balance v2 无期初列 → 只给 end，**不得**臆造 prior。"""
    out = resolve_impairment_prefill(None, 12345.678)
    assert out == {"end": 12345.68}
    assert "prior" not in out


def test_impairment_tb_balance_wins():
    """tb_balance 路径同时给期初+期末，信息更全 → 优先。"""
    tb = {"end": 100.0, "prior": 80.0}
    assert resolve_impairment_prefill(tb, 999.0) == tb


def test_impairment_tb_balance_zero_pair_still_wins():
    """tb_balance 命中但两期都是 0：dict 非空即算命中口径（真值就是 0）。"""
    tb = {"end": 0.0, "prior": 0.0}
    assert resolve_impairment_prefill(tb, 500.0) == tb


@hyp_settings(max_examples=5)
@given(
    end=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    prior=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    trial=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
)
def test_impairment_tb_path_is_returned_verbatim(end: float, prior: float, trial: float):
    tb = {"end": end, "prior": prior}
    assert resolve_impairment_prefill(tb, trial) is tb


# ════════════ Property 6/7：关联方匹配（空名单恒等 + 双向包含） ════════════


_REGISTRY = ["重庆和平药房连锁有限责任公司", "重庆医药集团医疗器械有限公司"]


@pytest.mark.parametrize(
    "name,expected_hit",
    [
        # 往来单位名 ⊇ 名单项（带分店后缀）
        ("重庆和平药房连锁有限责任公司江北分店", "重庆和平药房连锁有限责任公司"),
        # 名单项 ⊇ 往来单位名（名单登记全称、账套用简称）
        ("重庆和平药房连锁", "重庆和平药房连锁有限责任公司"),
        # 去空白归一
        ("  重庆医药集团医疗器械有限公司 ", "重庆医药集团医疗器械有限公司"),
        # 无交集
        ("陕西华氏医药有限公司", None),
        # 空名与超短名一律不匹配（防误标）
        ("", None),
        ("重庆", None),
    ],
)
def test_match_related_party(name: str, expected_hit):
    assert match_related_party(name, _REGISTRY) == expected_hit


def test_match_related_party_skips_too_short_registry_entries():
    """名单里出现「医药」这类超短项时不得命中一切（宁漏勿误）。"""
    assert match_related_party("陕西华氏医药有限公司", ["医药"]) is None
    # 反向自检：把名单项补长到阈值以上就应命中
    assert match_related_party("陕西华氏医药有限公司", ["华氏医药"]) == "华氏医药"


def test_match_related_party_empty_registry():
    assert match_related_party("重庆和平药房连锁有限责任公司", None) is None
    assert match_related_party("重庆和平药房连锁有限责任公司", []) is None


_ENTRIES = [
    ("重庆和平药房连锁有限责任公司江北分店", 100.0, 50.0, 30.0, 120.0),
    ("陕西华氏医药有限公司", 0.0, 200.0, 200.0, 0.0),
]


def test_build_rows_without_registry_is_identity_to_legacy():
    """Property 6：名单缺省 / 为空时全部 `非关联方`，且 remark 无关联方后缀。"""
    for registry in (None, []):
        rows = build_f1_detail_rows_from_aux(
            _ENTRIES, _SEGS, row_id_factory=_rid_factory(), related_parties=registry
        )
        assert len(rows) == 2
        assert {r["relationType"] for r in rows} == {F1_RELATION_NONE}
        assert all(r["remark"] == "由辅助余额表(1123)导入" for r in rows)


def test_build_rows_marks_matched_related_party():
    rows = build_f1_detail_rows_from_aux(
        _ENTRIES, _SEGS, row_id_factory=_rid_factory(), related_parties=_REGISTRY
    )
    by_name = {r["customerName"]: r for r in rows}
    hit = by_name["重庆和平药房连锁有限责任公司江北分店"]
    miss = by_name["陕西华氏医药有限公司"]

    assert hit["relationType"] == F1_RELATION_MATCHED
    assert "关联方名单命中：重庆和平药房连锁有限责任公司" in hit["remark"]
    assert miss["relationType"] == F1_RELATION_NONE
    assert "关联方名单命中" not in miss["remark"]


def test_build_rows_relation_type_is_a_valid_enum_value():
    """写入值必须是 F1-2 下拉的枚举项，不能是关联方名称（否则 el-select 显示枚举外值）。"""
    valid = {"非关联方", "母公司", "子公司", "联营企业", "合营企业", "其他关联方"}
    assert F1_RELATION_NONE in valid
    assert F1_RELATION_MATCHED in valid
    rows = build_f1_detail_rows_from_aux(
        _ENTRIES, _SEGS, row_id_factory=_rid_factory(), related_parties=_REGISTRY
    )
    assert {r["relationType"] for r in rows} <= valid


def test_build_rows_amount_and_aging_untouched_by_related_party_change():
    """关联方标注不得影响金额/账龄口径（改造零副作用）。"""
    base = build_f1_detail_rows_from_aux(
        _ENTRIES, _SEGS, row_id_factory=_rid_factory(), related_parties=None
    )
    with_rp = build_f1_detail_rows_from_aux(
        _ENTRIES, _SEGS, row_id_factory=_rid_factory(), related_parties=_REGISTRY
    )
    money_keys = [
        "priorUnadjusted", "priorAudited", "debit", "credit",
        "endBalance", "endUnadjusted", "endAudited",
        "agingPrior", "agingCurrent", "agingAudited",
    ]
    for a, b in zip(base, with_rp):
        assert a["customerName"] == b["customerName"]
        for k in money_keys:
            assert a[k] == b[k], k
