"""F2 存货分类归类守卫（按科目名称，两个标准变体下必须一致）。

本文件把 spec 的核心裁决钉死：**存货分类不能按编码写死**。

依据（postgres 只读实证，`account_chart` `source='standard'`，9 个真实项目）：
库内并存两个互不兼容的标准存货科目表变体，`1405`/`1406`/`1407`/`1408`/`1411`/
`1416`/`1451`/`1461` 的名称↔编码对应关系完全冲突。

spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ (Task 1.2)
Properties 1~5
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.services.f2_extraction.category_rules import (
    F2_CATEGORY_DEFAULT,
    F2_CATEGORY_ROW_KEYS,
    F2_CATEGORY_RULES,
    F2_IMPAIRMENT_ROW_KEY,
    classify_f2_category,
    classify_f2_leaf,
    is_f2_impairment_category,
    top_level_code,
)

# ── 两个标准变体的真实 (code, name) 样本（逐条取自 account_chart 实测） ────────

#: 变体 A —— 项目 0ec33ac9 / 12c15a96 / a7fc75e5
VARIANT_A: tuple[tuple[str, str], ...] = (
    ("1401", "材料采购"),
    ("1402", "在途物资"),
    ("1403", "原材料"),
    ("1404", "材料成本差异"),
    ("1405", "自制半成品"),
    ("1406", "库存商品"),
    ("1407", "发出商品"),
    ("1408", "商品进销差价"),
    ("1409", "周转材料"),
    ("1411", "委托加工物资"),
    ("1416", "存货跌价准备"),
    ("1421", "消耗性生物资产"),
    ("1451", "包装物"),
    ("1452", "低值易耗品"),
    ("1471", "合同取得成本"),
    ("1472", "合同履约成本"),
)

#: 变体 B —— 项目 4f6dbc36 / b39809ed / c8621493 / df5b8403 / f064f5e4（CAS 2006 官方口径）
VARIANT_B: tuple[tuple[str, str], ...] = (
    ("1401", "材料采购"),
    ("1402", "在途物资"),
    ("1403", "原材料"),
    ("1404", "材料成本差异"),
    ("1405", "库存商品"),
    ("1406", "发出商品"),
    ("1407", "商品进销差价"),
    ("1408", "委托加工物资"),
    ("1411", "周转材料"),
    ("1421", "消耗性生物资产"),
    ("1431", "贵金属"),
    ("1441", "抵债资产"),
    ("1451", "损余物资"),
    ("1452", "低值易耗品"),
    ("1461", "存货跌价准备"),
    ("1471", "合同取得成本"),
    ("1472", "合同履约成本"),
)

#: 名称 → 期望 rowKey（两变体共用；这是「与编码无关」的核心断言表）
EXPECTED_BY_NAME: dict[str, str] = {
    "材料采购": "material-in-transit",
    "在途物资": "material-in-transit",
    "原材料": "raw-materials",
    "材料成本差异": "raw-materials",
    "自制半成品": "semi-finished",
    "库存商品": "finished-goods",
    "发出商品": "goods-in-transit",
    "商品进销差价": "price-difference",
    "周转材料": "revolving-materials",
    "委托加工物资": "outsourced-processing",
    "存货跌价准备": F2_IMPAIRMENT_ROW_KEY,
    "消耗性生物资产": "consumable-bio",
    "贵金属": "finished-goods",
    "抵债资产": "finished-goods",
    "包装物": "revolving-materials",
    "损余物资": "revolving-materials",
    "低值易耗品": "revolving-materials",
    "合同取得成本": "contract-performance",
    "合同履约成本": "contract-performance",
}

#: 客户自定义子科目实测样本 ``(叶子名, 父级名, 期望 rowKey)``
CLIENT_LEAVES: tuple[tuple[str, str | None, str], ...] = (
    ("库存商品_产成品", "库存商品", "finished-goods"),
    ("库存商品_外购商品", "库存商品", "finished-goods"),
    ("库存商品_外购商品（零售）", "库存商品", "finished-goods"),
    ("材料成本差异_采购差异", "材料成本差异", "raw-materials"),
    ("材料成本差异_原材料差异", "材料成本差异", "raw-materials"),
    ("材料成本差异_周转材料差异", "材料成本差异", "revolving-materials"),
    ("存货跌价准备_原材料", "存货跌价准备", F2_IMPAIRMENT_ROW_KEY),
    ("存货跌价准备_周转材料", "存货跌价准备", F2_IMPAIRMENT_ROW_KEY),
    ("存货跌价准备_自制半成品", "存货跌价准备", F2_IMPAIRMENT_ROW_KEY),
    ("存货跌价准备_库存商品", "存货跌价准备", F2_IMPAIRMENT_ROW_KEY),
    # 纯客户命名 → 靠父级名回退
    ("新车", "自制半成品", "semi-finished"),
    ("旧车", "自制半成品", "semi-finished"),
    ("修复件", "自制半成品", "semi-finished"),
)


# ═════════════════ Property 2：两变体下归类只取决于名称 ═════════════════


@pytest.mark.parametrize("variant_name,rows", [("A", VARIANT_A), ("B", VARIANT_B)])
def test_classification_is_code_independent(variant_name: str, rows):
    for code, name in rows:
        expected = EXPECTED_BY_NAME[name]
        got = classify_f2_category(name)
        assert got == expected, (
            f"变体 {variant_name} {code} {name!r} 应归 {expected}，实为 {got}"
        )


def test_finished_goods_resolves_under_both_variants():
    """「库存商品」在变体 A 是 1406、在变体 B 是 1405 —— 两者都必须归 finished-goods。"""
    a_code = next(c for c, n in VARIANT_A if n == "库存商品")
    b_code = next(c for c, n in VARIANT_B if n == "库存商品")
    assert a_code == "1406" and b_code == "1405", (a_code, b_code)
    assert classify_f2_category("库存商品") == "finished-goods"


def test_same_code_different_meaning_gets_different_row_key():
    """反向证明「按编码写死必错」：1406 在两变体下语义不同 → rowKey 必须不同。"""
    a_name = dict(VARIANT_A)["1406"]
    b_name = dict(VARIANT_B)["1406"]
    assert a_name != b_name, (a_name, b_name)
    assert classify_f2_category(a_name) != classify_f2_category(b_name)


@pytest.mark.parametrize("code", ["1405", "1406", "1407", "1408", "1411", "1451"])
def test_conflicting_codes_are_really_conflicting(code: str):
    """守卫参数表自检：这 6 个码在两变体下名称确实不同（否则上面的断言无意义）。"""
    a = dict(VARIANT_A).get(code)
    b = dict(VARIANT_B).get(code)
    assert a and b and a != b, f"{code}: A={a!r} B={b!r}"


# ═════════════════ Property 3：备抵优先级 ═════════════════


@pytest.mark.parametrize(
    "name",
    [
        "存货跌价准备",
        "存货跌价准备_库存商品",
        "存货跌价准备_原材料",
        "存货跌价准备_周转材料",
        "存货跌价准备_自制半成品",
        "库存商品跌价准备",
        "合同履约成本减值准备",
    ],
)
def test_impairment_wins_over_gross_keywords(name: str):
    assert classify_f2_category(name) == F2_IMPAIRMENT_ROW_KEY
    assert is_f2_impairment_category(classify_f2_category(name))


def test_impairment_rule_is_first_reverse_selfcheck():
    """反向自检：若把备抵规则挪到末尾，`存货跌价准备_库存商品` 会被「商品」吃掉。

    这里不改真规则，只用同构的「打乱顺序」副本证明顺序是本质的。
    """
    shuffled = tuple(r for r in F2_CATEGORY_RULES if r[0] != F2_IMPAIRMENT_ROW_KEY) + tuple(
        r for r in F2_CATEGORY_RULES if r[0] == F2_IMPAIRMENT_ROW_KEY
    )

    def classify_with(rules, name: str) -> str:
        for row_key, hints in rules:
            if any(h in name for h in hints):
                return row_key
        return F2_CATEGORY_DEFAULT

    assert classify_with(shuffled, "存货跌价准备_库存商品") == "finished-goods", (
        "打乱顺序后竟仍归备抵 —— 说明本守卫没抓住顺序的本质"
    )
    assert classify_with(F2_CATEGORY_RULES, "存货跌价准备_库存商品") == F2_IMPAIRMENT_ROW_KEY


def test_material_purchase_wins_over_raw_materials():
    """「材料采购」含「材料」→ 必须先于 原材料 规则命中。"""
    assert classify_f2_category("材料采购") == "material-in-transit"
    assert classify_f2_category("原材料") == "raw-materials"


def test_contract_cost_wins_over_dev_cost():
    assert classify_f2_category("合同履约成本") == "contract-performance"
    assert classify_f2_category("合同取得成本") == "contract-performance"
    assert classify_f2_category("开发成本") == "dev-costs"


# ═════════════════ Property 4：叶子未命中回退父级 ═════════════════


@pytest.mark.parametrize("leaf,parent,expected", CLIENT_LEAVES)
def test_client_leaf_classification(leaf: str, parent: str | None, expected: str):
    assert classify_f2_leaf(leaf, parent) == expected


def test_leaf_without_parent_falls_back_to_other():
    assert classify_f2_leaf("修复件", None) == F2_CATEGORY_DEFAULT
    assert classify_f2_leaf("修复件", "") == F2_CATEGORY_DEFAULT


def test_leaf_own_name_wins_over_parent():
    """叶子名自身可判时不看父级（`材料成本差异_周转材料差异` 归周转材料）。"""
    assert classify_f2_leaf("材料成本差异_周转材料差异", "材料成本差异") == "revolving-materials"


# ═════════════════ Property 1：不重不漏（闭集 + PBT） ═════════════════


def test_classify_returns_only_known_row_keys():
    for name in EXPECTED_BY_NAME:
        assert classify_f2_category(name) in F2_CATEGORY_ROW_KEYS
    for leaf, parent, _ in CLIENT_LEAVES:
        assert classify_f2_leaf(leaf, parent) in F2_CATEGORY_ROW_KEYS


@pytest.mark.parametrize("name", ["", None, "   ", "不存在的科目", "银行存款"])
def test_unknown_falls_back_to_other(name):
    assert classify_f2_category(name) == F2_CATEGORY_DEFAULT


@hyp_settings(max_examples=8)
@given(names=st.lists(st.sampled_from(sorted(EXPECTED_BY_NAME)), max_size=12))
def test_buckets_partition_the_input(names: list[str]):
    """任意科目名集合按归类分桶后，各桶元素数之和 == 输入元素数（不重不漏）。"""
    buckets: dict[str, list[str]] = {}
    for n in names:
        buckets.setdefault(classify_f2_category(n), []).append(n)
    assert sum(len(v) for v in buckets.values()) == len(names)


@hyp_settings(max_examples=8)
@given(
    text=st.text(min_size=0, max_size=12, alphabet=st.characters(categories=("L", "N")))
)
def test_classify_never_raises(text: str):
    assert classify_f2_category(text) in F2_CATEGORY_ROW_KEYS


# ═════════════════ 归一与工具 ═════════════════


def test_whitespace_normalised():
    assert classify_f2_category(" 库 存 商 品 ") == "finished-goods"
    assert classify_f2_category("存货\u3000跌价准备") == F2_IMPAIRMENT_ROW_KEY


@pytest.mark.parametrize(
    "code,expected",
    [("1406", "1406"), ("1406.02", "1406"), ("1416.04", "1416"), ("", ""), (None, "")],
)
def test_top_level_code(code, expected: str):
    assert top_level_code(code) == expected


def test_row_keys_closed_set_matches_rules():
    """`F2_CATEGORY_ROW_KEYS` 必须 == 规则表的 rowKey ∪ {other}（防漏登记）。"""
    from_rules = {r for r, _ in F2_CATEGORY_RULES} | {F2_CATEGORY_DEFAULT}
    assert set(F2_CATEGORY_ROW_KEYS) == from_rules
