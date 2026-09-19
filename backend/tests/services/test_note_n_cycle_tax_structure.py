"""附注 N 循环税务类章节结构守卫（N2 应交税费 / N4 税金及附加 / N5 所得税费用）。

对应 spec ``n-cycle-tax-disclosure-alignment`` R5 / Task 3.8。

权威源 = ``backend/wp_templates/N/{N2,N4,N5}*.xlsx`` 的两张披露 sheet
（结论固化在 spec design.md §Data Models）。守卫要点：

1. **表名同章节内唯一** —— 表名是同步键，同名会让 ``sub_table_data`` 互相覆盖丢表
   （N5 两版原先各有两张同名表：上市 ``项  目`` ×2 / 国企 ``所得税费用`` ×2）
2. N2 两版列结构**本质不同**（上市 3 列双期 / 国企 5 列变动），且反向断言不得被"统一"
3. N5 国企表 2 是 3 列（原被压扁成 2 列丢了「上期发生额」）
4. 每张表显式 ``flat`` 表态（否则 seed 路径被前缀推断塞凭空父表头）
5. 全表有 ``guidance``；``text_sections`` 表标题带 ``#`` 前缀
6. **国企税金及附加不得存在章节**（源模板 ``附注披露信息：无``）
7. 幂等：重跑逐字节相等
"""

from __future__ import annotations

import json

import pytest

from scripts.fix import fix_note_n_cycle_tax_structure as fx


def _sections(path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["sections"]


def _section(path, number: str) -> dict:
    hits = [s for s in _sections(path) if s.get("section_number") == number]
    assert len(hits) == 1, f"{number} 命中 {len(hits)} 个"
    return hits[0]


_CASES = [
    ("N2/listed", fx.LISTED_PATH, fx.SECTION_N2_LISTED),
    ("N2/soe", fx.SOE_PATH, fx.SECTION_N2_SOE),
    ("N4/listed", fx.LISTED_PATH, fx.SECTION_N4_LISTED),
    ("N5/listed", fx.LISTED_PATH, fx.SECTION_N5_LISTED),
    ("N5/soe", fx.SOE_PATH, fx.SECTION_N5_SOE),
]


# ─────────────────────── 1. 表名唯一（同步键）───────────────────────


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_table_names_unique_within_section(label, path, number) -> None:
    """🔴 同名表会让 sub_table_data 键互相覆盖 → 丢表。"""
    names = [t["name"] for t in _section(path, number)["tables"]]
    assert len(names) == len(set(names)), f"{label} 表名重复：{names}"


def test_n5_listed_table_names_no_longer_leak_header_cell() -> None:
    """原先两表都叫 `项  目`（md 重建把表头首格当表名泄漏）。"""
    names = [t["name"] for t in _section(fx.LISTED_PATH, fx.SECTION_N5_LISTED)["tables"]]
    assert names == [fx.T_N5_DETAIL, fx.T_N5_RECONCILE_LISTED]
    assert "项  目" not in names


def test_n5_soe_second_table_renamed() -> None:
    names = [t["name"] for t in _section(fx.SOE_PATH, fx.SECTION_N5_SOE)["tables"]]
    assert names == [fx.T_N5_SOE_MAIN, fx.T_N5_RECONCILE_SOE]


def test_legacy_table_names_declared_for_orphan_cleanup() -> None:
    """重命名产生的旧键必须登记，供前端 `_removed_table_keys` 清理孤儿表。"""
    assert fx.LEGACY_TABLE_NAMES[fx.SECTION_N5_LISTED] == ["项  目"]
    assert fx.LEGACY_TABLE_NAMES[fx.SECTION_N5_SOE] == ["所得税费用"]


# ─────────────────────── 2. N2 两版列结构本质不同 ───────────────────────


def test_n2_listed_is_dual_period_three_columns() -> None:
    t = _section(fx.LISTED_PATH, fx.SECTION_N2_LISTED)["tables"][0]
    assert t["headers"] == ["税项", "期末余额", "上年年末余额"]


def test_n2_soe_is_movement_five_columns() -> None:
    """国企侧源模板是变动表，此前被 md 重建压成 3 列双期表。"""
    t = _section(fx.SOE_PATH, fx.SECTION_N2_SOE)["tables"][0]
    assert t["headers"] == ["项目", "期初余额", "本期应交", "本期已交", "期末余额"]


def test_n2_variants_must_not_be_unified() -> None:
    """反向断言：两版列集合不得相同（现状缺陷即上市误用了国企口径）。"""
    listed = _section(fx.LISTED_PATH, fx.SECTION_N2_LISTED)["tables"][0]
    soe = _section(fx.SOE_PATH, fx.SECTION_N2_SOE)["tables"][0]
    assert len(listed["headers"]) != len(soe["headers"])
    assert {c["key"] for c in listed["columns"]} != {c["key"] for c in soe["columns"]}


# ─────────────────────── 3. N5 国企表 2 列数恢复 ───────────────────────


def test_n5_soe_reconcile_table_has_prior_column() -> None:
    """原被压扁成 2 列（丢「上期发生额」）；源模板 R14 实测 3 列。"""
    t = _section(fx.SOE_PATH, fx.SECTION_N5_SOE)["tables"][1]
    assert t["headers"] == ["项目", "本期发生额", "上期发生额"]


def test_n5_listed_reconcile_last_row_is_not_total() -> None:
    """末行「所得税费用」是勾稽落点（源模板注 1），不是合计行。"""
    rows = _section(fx.LISTED_PATH, fx.SECTION_N5_LISTED)["tables"][1]["rows"]
    assert rows[-1]["label"] == "所得税费用"
    assert rows[-1].get("is_total") is not True


# ─────────────────────── 4./5. 表态 / guidance / 文本 ───────────────────────


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_every_table_declares_flat(label, path, number) -> None:
    for t in _section(path, number)["tables"]:
        assert any(c.get("flat") for c in t["columns"]), f"{label} {t['name']} 未表态 flat"
        assert not t.get("_column_groups"), f"{label} {t['name']} 单级表不应带 _column_groups"


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_columns_align_headers(label, path, number) -> None:
    for t in _section(path, number)["tables"]:
        assert [c["label"] for c in t["columns"]] == t["headers"], f"{label} {t['name']}"
        assert t["columns"][0].get("is_label") is True
        assert all(str(h).strip() for h in t["headers"])


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_every_table_has_guidance(label, path, number) -> None:
    missing = [
        t["name"] for t in _section(path, number)["tables"]
        if not str(t.get("guidance") or "").strip()
    ]
    assert missing == [], f"{label} 缺 guidance: {missing}"


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_table_titles_prefixed_in_text_sections(label, path, number) -> None:
    """裸表名段落会被 `_is_table_title_paragraph` 当正文输出。"""
    sec = _section(path, number)
    names = {t["name"] for t in sec["tables"]}
    bare = [p for p in sec["text_sections"] if p.strip() in names]
    assert bare == [], f"{label} 裸表名段落: {bare}"


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_each_table_has_title_paragraph(label, path, number) -> None:
    sec = _section(path, number)
    titles = [p.lstrip("#").strip() for p in sec["text_sections"] if p.startswith("#")]
    for t in sec["tables"]:
        assert any(t["name"] in title for title in titles), f"{label} {t['name']} 无标题段"


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_section_marked_aligned(label, path, number) -> None:
    assert _section(path, number).get("_aligned_by") == fx.ALIGNED_BY


@pytest.mark.parametrize(("label", "path", "number"), _CASES)
def test_total_rows_marked(label, path, number) -> None:
    for t in _section(path, number)["tables"]:
        for r in t["rows"]:
            if str(r["label"]).replace(" ", "").startswith(("小计", "合计")):
                assert r.get("is_total") is True, f"{label} {t['name']}:{r['label']}"


def test_source_template_notes_carried() -> None:
    n2l = "\n".join(_section(fx.LISTED_PATH, fx.SECTION_N2_LISTED)["text_sections"])
    assert "小税（费）种可合并反映" in n2l
    assert "其他流动资产" in n2l
    n4 = "\n".join(_section(fx.LISTED_PATH, fx.SECTION_N4_LISTED)["text_sections"])
    assert "计缴标准详见附注四、税项" in n4
    n5l = "\n".join(_section(fx.LISTED_PATH, fx.SECTION_N5_LISTED)["text_sections"])
    assert "所得税费用等于第二行至倒数第二行之和" in n5l
    n5s = "\n".join(_section(fx.SOE_PATH, fx.SECTION_N5_SOE)["text_sections"])
    assert "国资委格式未要求披露，建议披露" in n5s


def test_n2_guidance_states_variant_difference() -> None:
    """guidance 必须写明两版口径不同，防后来者"统一"。"""
    soe = _section(fx.SOE_PATH, fx.SECTION_N2_SOE)["tables"][0]["guidance"]
    assert "变动" in soe and "不可互相套用" in soe


# ─────────────────────── 6. 国企税金及附加不得建章节 ───────────────────────


def test_no_soe_section_for_surtaxes() -> None:
    """源模板国企侧此节为「附注披露信息：无」→ 不披露，不得"补齐"章节。"""
    hits = [
        s for s in _sections(fx.SOE_PATH)
        if str(s.get("account_name") or "") == "税金及附加"
        or str(s.get("section_title") or "") == "税金及附加"
    ]
    assert hits == [], f"国企模板不应有税金及附加章节：{[s.get('section_number') for s in hits]}"


def test_variant_matrix_keeps_soe_none_for_surtaxes() -> None:
    m = json.loads(
        (fx.DATA_DIR / "note_template_variant_matrix.json").read_text(encoding="utf-8")
    )
    entry = next(a for a in m["accounts"] if a["account_key"] == "shui_jin_ji_fu_jia")
    assert entry["variants"]["soe_standalone"] is None
    assert entry["variants"]["soe_consolidated"] is None


# ─────────────────────── 7. 幂等 / 纯函数 ───────────────────────


def test_apply_is_idempotent() -> None:
    assert fx.apply(check_only=True) is False


@pytest.mark.parametrize(
    "builder",
    [
        fx.build_n2_listed_tables,
        fx.build_n2_soe_tables,
        fx.build_n4_listed_tables,
        fx.build_n5_listed_tables,
        fx.build_n5_soe_tables,
    ],
)
def test_builders_are_pure(builder) -> None:
    a, b = builder(), builder()
    assert a == b
    a[0]["rows"][0]["label"] = "MUTATED"
    assert builder()[0]["rows"][0]["label"] != "MUTATED"
