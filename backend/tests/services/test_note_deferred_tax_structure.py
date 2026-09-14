"""附注模板「递延所得税资产和递延所得税负债」章节结构守卫。

对应 spec ``n1-deferred-tax-disclosure-template-alignment`` R4 / Task 2.9。

权威源 = ``backend/wp_templates/N/N1 递延所得税资产.xlsx`` 两张披露 sheet
（结论固化在 spec design.md §1）。守卫要点：

1. 表数与表名逐字（改名 → 孤儿子表：附注 TAB 永空 + 底稿数据丢失）
2. 表 1 是 5 列两级表头，且**两版子列序相反**（源模板 B11:E11 实测）
3. 每张表在 ``group`` / ``flat`` 之间明确表态（未表态会被后端
   ``_infer_groups_from_headers`` 塞凭空父表头）
4. ``_column_groups`` 覆盖范围不越界、不重叠
5. 全表有 ``guidance``（TAB 页签编制提示）
6. ``text_sections`` 的表标题带 ``#`` 前缀（否则被 ``_is_table_title_paragraph``
   当正文，会把表名当披露段落输出）
7. 无 ``row_type: header_label`` 残留（压扁的第二行表头假数据行）
8. 幂等：重跑脚本逐字节相等
"""

from __future__ import annotations

import json

import pytest

from scripts.fix import fix_note_deferred_tax_structure as fx

_DIFF = "可抵扣/应纳税暂时性差异"
_TAX = "递延所得税资产/负债"

_EXPECTED_NAMES = {
    "listed": [
        fx.T_UNOFFSET,
        fx.T_NET_OFFSET,
        fx.T_UNRECOGNIZED_LISTED,
        fx.T_LOSS_EXPIRY,
    ],
    "soe": [
        fx.T_UNOFFSET,
        fx.T_NET_OFFSET,
        fx.T_OFFSET_DETAIL,
        fx.T_UNRECOGNIZED_SOE,
        fx.T_LOSS_EXPIRY,
    ],
}

_VARIANTS = ("listed", "soe")


def _section(variant: str) -> dict:
    path = fx.LISTED_PATH if variant == "listed" else fx.SOE_PATH
    number = fx.LISTED_SECTION if variant == "listed" else fx.SOE_SECTION
    data = json.loads(path.read_text(encoding="utf-8"))
    return fx._find_section(data, number)


def _tables(variant: str) -> list[dict]:
    return _section(variant)["tables"]


def _by_name(variant: str) -> dict[str, dict]:
    return {t["name"]: t for t in _tables(variant)}


# ─────────────────────── 1. 表数与表名 ───────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_table_names_verbatim(variant: str) -> None:
    assert [t["name"] for t in _tables(variant)] == _EXPECTED_NAMES[variant]


def test_soe_has_offset_detail_table() -> None:
    """国企源模板（2）B「互抵明细」原先整张表缺失。"""
    t = _by_name("soe")[fx.T_OFFSET_DETAIL]
    assert t["headers"] == ["项目", "本期互抵金额"]


@pytest.mark.parametrize("variant", _VARIANTS)
def test_section_marked_aligned(variant: str) -> None:
    assert _section(variant).get("_aligned_by") == fx.ALIGNED_BY


# ─────────────────────── 2. 表 1 两级表头 + 子列序 ───────────────────────


@pytest.mark.parametrize(
    ("variant", "prior_group", "sub_order"),
    [
        ("listed", "上年年末余额", [_DIFF, _TAX]),
        ("soe", "年初余额", [_TAX, _DIFF]),
    ],
)
def test_unoffset_two_level_header(
    variant: str, prior_group: str, sub_order: list[str]
) -> None:
    """表 1 = 5 列两级表头；🔴 两版子列序相反（源模板实测）。"""
    t = _by_name(variant)[fx.T_UNOFFSET]
    assert t["headers"] == ["项目", *sub_order, *sub_order]
    assert t["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 2},
        {"group": prior_group, "start": 3, "span": 2},
    ]
    # columns 键序必须与子列序一致，否则同步后附注列错位
    cols = t["columns"]
    assert [c["label"] for c in cols[1:]] == [*sub_order, *sub_order]
    assert [c["group"] for c in cols[1:]] == ["期末余额"] * 2 + [prior_group] * 2


def test_unoffset_sub_order_differs_between_variants() -> None:
    """反向断言：两版子列序不得被"统一"成同一个。"""
    assert fx._unoffset_sub_order("listed") != fx._unoffset_sub_order("soe")


def test_soe_net_offset_is_five_columns() -> None:
    """国企表 2 原被 md 抽取压扁成 3 列。"""
    t = _by_name("soe")[fx.T_NET_OFFSET]
    assert t["headers"] == [
        "项目",
        "报告期末互抵后的递延所得税资产或负债",
        "报告期末互抵后的可抵扣或应纳税暂时性差异",
        "报告年初互抵后的递延所得税资产或负债",
        "报告年初互抵后的可抵扣或应纳税暂时性差异",
    ]


def test_soe_net_offset_rows_mirror_unoffset() -> None:
    """国企表 2 行骨架按源 xlsx 补齐为与表 1 同构（md 原为 2 行简写）。"""
    labels1 = [r["label"] for r in _by_name("soe")[fx.T_UNOFFSET]["rows"]]
    labels2 = [r["label"] for r in _by_name("soe")[fx.T_NET_OFFSET]["rows"]]
    assert labels1 == labels2
    assert labels2.count("小计") == 2


# ─────────────────────── 3./4. 表态与分组合法性 ───────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_every_table_declares_header_state(variant: str) -> None:
    """每张表要么有 group（多级）要么有 flat（单级），不得都无、不得并存。"""
    offenders: list[str] = []
    for t in _tables(variant):
        cols = t.get("columns") or []
        has_flat = any(c.get("flat") for c in cols)
        has_group = any(c.get("group") for c in cols)
        if not cols or has_flat == has_group:
            offenders.append(f"{t['name']}(flat={has_flat},group={has_group})")
    assert offenders == []


@pytest.mark.parametrize("variant", _VARIANTS)
def test_columns_align_headers(variant: str) -> None:
    for t in _tables(variant):
        cols = t["columns"]
        assert [c["label"] for c in cols] == t["headers"], t["name"]
        assert cols[0].get("is_label") is True, t["name"]
        assert all(str(h).strip() for h in t["headers"]), t["name"]


@pytest.mark.parametrize("variant", _VARIANTS)
def test_column_groups_within_bounds_and_disjoint(variant: str) -> None:
    for t in _tables(variant):
        groups = t.get("_column_groups")
        if not groups:
            continue
        occupied: set[int] = set()
        ncol = len(t["headers"])
        for g in groups:
            span = range(g["start"], g["start"] + g["span"])
            assert g["start"] >= 1, t["name"]
            assert g["start"] + g["span"] <= ncol, t["name"]
            assert not (occupied & set(span)), f"{t['name']} 分组重叠"
            occupied |= set(span)


@pytest.mark.parametrize("variant", _VARIANTS)
def test_flat_tables_have_no_column_groups(variant: str) -> None:
    """显式单级表不得同时带 _column_groups（会让前端渲染出父表头）。"""
    for t in _tables(variant):
        if any(c.get("flat") for c in t["columns"]):
            assert not t.get("_column_groups"), t["name"]


# ─────────────────────── 5. guidance ───────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_every_table_has_guidance(variant: str) -> None:
    missing = [t["name"] for t in _tables(variant) if not str(t.get("guidance", "")).strip()]
    assert missing == []


@pytest.mark.parametrize("variant", _VARIANTS)
def test_guidance_has_no_html(variant: str) -> None:
    for t in _tables(variant):
        assert "<" not in t["guidance"] or "<br" not in t["guidance"], t["name"]


# ─────────────────────── 6. text_sections ───────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_table_titles_in_text_sections_are_prefixed(variant: str) -> None:
    """裸表名段落会被当正文输出；表标题必须带 `#` 前缀。"""
    sec = _section(variant)
    names = {t["name"] for t in sec["tables"]}
    bare = [p for p in sec["text_sections"] if p.strip() in names]
    assert bare == []


@pytest.mark.parametrize("variant", _VARIANTS)
def test_each_table_has_a_title_paragraph(variant: str) -> None:
    sec = _section(variant)
    titles = {p.lstrip("#").strip() for p in sec["text_sections"] if p.startswith("#")}
    for t in sec["tables"]:
        assert any(t["name"] in title for title in titles), t["name"]


def test_listed_text_sections_carry_source_notes() -> None:
    texts = "\n".join(_section("listed")["text_sections"])
    assert "其中一年后预期转回的递延所得税资产和递延所得税负债" in texts
    assert "扭亏为盈" in texts
    assert "持有待售资产的资产减值准备" in texts
    assert "并在备注栏予以说明" in texts


def test_soe_text_sections_carry_disclosure_branch_rule() -> None:
    texts = "\n".join(_section("soe")["text_sections"])
    assert "不以抵销后的净额列示的，按（1）披露" in texts
    assert "其他权益工具投资" in texts


# ─────────────────────── 7. 无假数据行 ───────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_no_header_label_rows(variant: str) -> None:
    """压扁的第二行表头会残留成 header_label 假数据行，必须已删除。"""
    residues = [
        f"{t['name']}:{r['label']}"
        for t in _tables(variant)
        for r in t["rows"]
        if r.get("row_type") == "header_label"
    ]
    assert residues == []


@pytest.mark.parametrize("variant", _VARIANTS)
def test_subtotal_and_total_rows_marked(variant: str) -> None:
    for t in _tables(variant):
        for r in t["rows"]:
            label = str(r["label"]).replace(" ", "")
            if label.startswith("小计") or label.startswith("合计"):
                assert r.get("is_total") is True, f"{t['name']}:{label}"


# ─────────────────────── 8. 幂等 ───────────────────────


def test_apply_is_idempotent() -> None:
    """已对齐状态下再跑不产生改动（check 返回 False）。"""
    assert fx.apply(check_only=True) is False


def test_build_functions_are_pure() -> None:
    """两次构造结果相等且互不共享可变行对象。"""
    a, b = fx.build_soe_tables(), fx.build_soe_tables()
    assert a == b
    a[0]["rows"][1]["label"] = "MUTATED"
    assert fx.build_soe_tables()[0]["rows"][1]["label"] != "MUTATED"
