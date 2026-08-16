"""test_k_source_template_facts —— 用例层。

判据（常量 / 登记表 / fixture / 纯函数 / helper）见 `_test_k_source_template_facts_criteria.py`，
原文件 docstring 也在那里。拆分原因：原单文件 887 行 > pre-commit 800 行门禁。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._test_k_source_template_facts_criteria import (  # noqa: F401  fixtures 需在本模块命名空间
    AGING_COLUMN_ANCHORS,
    AGING_FIRST_BAND_LISTED,
    AGING_FIRST_BAND_SOE,
    AGING_ROW_ANCHORS,
    CYCLES_WITHOUT_DISCLOSURE,
    DISCLOSURE_MARKERS,
    DISCLOSURE_SHEETS,
    K1_MONTHLY_DETAIL_ANCHORS,
    K1_REF_ERROR_COUNTS,
    K3_NATURE_LABEL_HEADER,
    K6_TOTAL_ROW_TEXT_CELLS,
    MARKER_FORMS,
    MARKER_FORMS_ABSENT_IN_K,
    SHEET_COUNTS,
    TOTAL_DISCLOSURE_MARKERS,
    TOTAL_DISCLOSURE_SHEETS,
    TOTAL_MARKERS,
    TOTAL_VISIBLE_SHEETS,
    TPL_DIR,
    TWO_LEVEL_CYCLES,
    TWO_LEVEL_HEADERS,
    WORKBOOKS,
    _load,
    _text,
    _ws,
)

__all__ = [
    "AGING_COLUMN_ANCHORS",
    "AGING_FIRST_BAND_LISTED",
    "AGING_FIRST_BAND_SOE",
    "AGING_ROW_ANCHORS",
    "CYCLES_WITHOUT_DISCLOSURE",
    "DISCLOSURE_MARKERS",
    "DISCLOSURE_SHEETS",
    "K1_MONTHLY_DETAIL_ANCHORS",
    "K1_REF_ERROR_COUNTS",
    "K3_NATURE_LABEL_HEADER",
    "K6_TOTAL_ROW_TEXT_CELLS",
    "MARKER_FORMS",
    "MARKER_FORMS_ABSENT_IN_K",
    "SHEET_COUNTS",
    "TOTAL_DISCLOSURE_MARKERS",
    "TOTAL_DISCLOSURE_SHEETS",
    "TOTAL_MARKERS",
    "TOTAL_VISIBLE_SHEETS",
    "TPL_DIR",
    "TWO_LEVEL_CYCLES",
    "TWO_LEVEL_HEADERS",
    "WORKBOOKS",
    "_load",
    "_text",
    "_ws",
]


def test_template_dir_exists_and_has_14_workbooks():
    """反向自检：源模板目录存在且恰有 14 个 xlsx（扫描面非空）。"""
    assert TPL_DIR.is_dir(), f"源模板目录不存在：{TPL_DIR}"
    found = sorted(p.name for p in TPL_DIR.glob("*.xlsx") if not p.name.startswith("~$"))
    assert len(found) == 14, f"K 目录应有 14 个 xlsx，实际 {len(found)}：{found}"
    assert set(found) == set(WORKBOOKS.values()), (
        f"文件名清单与实际不符\n仅登记={set(WORKBOOKS.values()) - set(found)}\n"
        f"仅实际={set(found) - set(WORKBOOKS.values())}"
    )


def test_all_14_cycles_registered():
    """K0~K13 十四个循环全部登记。"""
    assert set(WORKBOOKS) == {f"K{i}" for i in range(14)}
    assert len(WORKBOOKS) == 14


# ─────────────────────────────────────────────────────────────────────────────
# Property 28：披露 sheet 名逐字一致（6 种括号写法）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp", sorted(DISCLOSURE_SHEETS, key=lambda c: int(c[1:])))
def test_disclosure_sheet_names_are_exact(wp: str):
    """🔴 披露 sheet 名逐字冻结（含 6 种括号写法与「国有企业」）。"""
    wb = _load(wp)
    for variant, name in DISCLOSURE_SHEETS[wp].items():
        assert name in wb.sheetnames, (
            f"{wp}/{variant} 期望 sheet 名「{name}」不存在。\n"
            f"实际 sheetnames={wb.sheetnames}\n"
            "⚠️ 括号宽度/「国企」vs「国有企业」都是源模板事实，不得统一"
        )


def test_bracket_forms_are_six_not_four():
    """🔴 推翻初稿：披露 sheet 括号写法是 **6 种**不是 4 种。

    按 4 种写判据会漏掉 K5 listed（前全后半）与 K6 soe（前半后全）。
    """
    forms: set[str] = set()
    for variants in DISCLOSURE_SHEETS.values():
        for name in variants.values():
            m = re.search(r"[（(].*?[）)]", name)
            if m:
                seg = m.group(0)
                forms.add(f"{seg[0]}…{seg[-1]}|{'国有企业' if '国有企业' in seg else ('国企' if '国企' in seg else '上市')}")
    assert len(forms) >= 6, (
        f"括号+用语组合只有 {len(forms)} 种：{sorted(forms)}；"
        "实测应 ≥6（初稿记 4 种已被推翻）"
    )


def test_k7_soe_is_the_only_state_owned_enterprise_wording():
    """K7 soe 是**唯一**用「国有企业」的 K 循环（其余用「国企」）。"""
    with_full = [
        wp for wp, v in DISCLOSURE_SHEETS.items() if "国有企业" in v.get("soe", "")
    ]
    assert with_full == ["K7"], (
        f"用「国有企业」的循环应只有 K7，实际 {with_full} —— "
        "按 `'国企' in name` 判披露 sheet 会漏掉 K7"
    )


def test_k0_has_no_disclosure_sheet():
    """K0 是函证循环，无披露 sheet。"""
    for wp in CYCLES_WITHOUT_DISCLOSURE:
        wb = _load(wp)
        hits = [n for n in wb.sheetnames if "附注披露" in n]
        assert not hits, f"{wp} 不应有披露 sheet，实际命中 {hits}"
        assert wp not in DISCLOSURE_SHEETS


# ─────────────────────────────────────────────────────────────────────────────
# sheet 可见性与计数
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp", sorted(SHEET_COUNTS, key=lambda c: int(c[1:])))
def test_sheet_counts_and_hidden(wp: str):
    """sheet 总数 / visible 数 / hidden 名逐个冻结。

    ⚠️ ``wb.sheetnames`` **含隐藏 sheet**，判「某 sheet 属不属于底稿集合」
    必须查 ``sheet_state``（平台级 P0，曾让 353 行本不该出现的页签进渲染面）。
    """
    total, visible, hidden = SHEET_COUNTS[wp]
    wb = _load(wp)
    assert len(wb.sheetnames) == total, (
        f"{wp} sheet 总数应 {total}，实际 {len(wb.sheetnames)}：{wb.sheetnames}"
    )
    actual_hidden = tuple(n for n in wb.sheetnames if wb[n].sheet_state != "visible")
    assert actual_hidden == hidden, f"{wp} hidden 应 {hidden}，实际 {actual_hidden}"
    actual_visible = sum(1 for n in wb.sheetnames if wb[n].sheet_state == "visible")
    assert actual_visible == visible


def test_all_disclosure_sheets_are_visible():
    """26 张披露 sheet 全部 visible（不得被 skip 掉）。"""
    invisible: list[str] = []
    for wp, variants in DISCLOSURE_SHEETS.items():
        wb = _load(wp)
        for variant, name in variants.items():
            if name in wb.sheetnames and wb[name].sheet_state != "visible":
                invisible.append(f"{wp}/{variant}={wb[name].sheet_state}")
    assert not invisible, f"披露 sheet 应全 visible，实际 {invisible}"


def test_totals_match_frozen_counts():
    """全册 visible / 披露 sheet 计数（覆盖面判据的分母）。"""
    total_visible = 0
    for wp in WORKBOOKS:
        wb = _load(wp)
        total_visible += sum(1 for n in wb.sheetnames if wb[n].sheet_state == "visible")
    assert total_visible == TOTAL_VISIBLE_SHEETS, (
        f"全册 visible sheet 应 {TOTAL_VISIBLE_SHEETS}，实际 {total_visible}"
    )
    n_disc = sum(len(v) for v in DISCLOSURE_SHEETS.values())
    assert n_disc == TOTAL_DISCLOSURE_SHEETS == 26


# ─────────────────────────────────────────────────────────────────────────────
# Property 33 / 34：动态插行标记（5 种写法 / 148 处 / 披露内 18 处）
# ─────────────────────────────────────────────────────────────────────────────


def _iter_marker_hits(wp: str):
    """遍历某 workbook 全部 visible sheet 的动态标记命中。

    命中判据 = 单元格文本含 ``MARKER_FORMS`` 任一写法；按**最长写法优先**归类
    （``……`` 含 ``…`` ⇒ 不先判长的会把 147 处 `……` 全归成 `…`）。
    """
    # 🔴 必须 data_only=True —— 标记格有一批是**公式格**（K8/K9/K10/K11/K12 的披露
    # sheet），`data_only=False` 下读到的是公式字符串而非用户看到的 `……`
    # ⇒ 那批标记会整体扫不到（实测差 16 处）。判「源模板事实」以用户可见值为准。
    wb = _load(wp, data_only=True)
    forms = sorted(MARKER_FORMS, key=len, reverse=True)
    for sn in wb.sheetnames:
        ws = wb[sn]
        if ws.sheet_state != "visible":
            continue
        for row in ws.iter_rows():
            for c in row:
                if not isinstance(c.value, str):
                    continue
                for f in forms:
                    if f in c.value:
                        yield sn, c.coordinate, f, c.value
                        break


def test_marker_forms_are_five_and_counts_frozen():
    """🔴 推翻初稿：动态标记 **164 处 / 4 种写法**（初稿记 24 处 / 3 种）。"""
    counts: dict[str, int] = {f: 0 for f in MARKER_FORMS}
    total = 0
    for wp in WORKBOOKS:
        for _sn, _coord, form, _txt in _iter_marker_hits(wp):
            counts[form] += 1
            total += 1
    assert total == TOTAL_MARKERS, (
        f"全册动态标记应 {TOTAL_MARKERS} 处，实际 {total}；逐写法={counts}\n"
        "⚠️ 初稿记的「24 处 / 3 种」与首轮探针的「148 处 / 5 种」都是错的，判据不得回退"
    )
    assert counts == MARKER_FORMS, f"逐写法计数不符\n期望={MARKER_FORMS}\n实际={counts}"


def test_single_char_ellipsis_does_exist():
    """🔴 推翻初稿：`…`（单字符）在 K 类**确实存在** 10 处，不得排除。

    初稿的 Requirement 9.7 写「未出现的写法 `…` 不进判据」——
    按它写会把 K6-6 的三处、K8-5/K9-5 的可扩位排除在外。
    """
    hits: list[str] = []
    for wp in WORKBOOKS:
        for sn, coord, form, txt in _iter_marker_hits(wp):
            if form == "…":
                hits.append(f"{wp}/{sn}/{coord}={txt[:40]!r}")
    assert len(hits) == MARKER_FORMS["…"] == 9, (
        f"`…` 应有 9 处，实际 {len(hits)}：{hits}"
    )


def test_absent_marker_forms_have_zero_hits():
    """反向自检：`预留`/`可改名` 在 K 类零命中 ⇒ 不得加入 K 类判据（防空转）。"""
    found: dict[str, list[str]] = {f: [] for f in MARKER_FORMS_ABSENT_IN_K}
    for wp in WORKBOOKS:
        wb = _load(wp)
        for sn in wb.sheetnames:
            ws = wb[sn]
            if ws.sheet_state != "visible":
                continue
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str):
                        for f in MARKER_FORMS_ABSENT_IN_K:
                            if f in c.value:
                                found[f].append(f"{wp}/{sn}/{c.coordinate}")
    nonzero = {f: v[:5] for f, v in found.items() if v}
    assert not nonzero, (
        f"以下写法在 K 类**已出现**，需纳入判据并更新 MARKER_FORMS：{nonzero}"
    )


@pytest.mark.parametrize("wp", sorted(DISCLOSURE_MARKERS, key=lambda c: int(c[1:])))
def test_disclosure_sheet_markers_frozen(wp: str):
    """披露 sheet 内的动态标记位置与写法逐处冻结（Task 18 的作业面）。

    🔴 必须 `data_only=True`。K8~K12 五个循环的标记格是**公式格** —— 缓存值是
    `……`、公式串里没有，用默认的 `data_only=False` 扫这 5 个循环恒得空集合，
    表现为 5 条参数化恒红「实际=()」，看起来像登记表写错了坐标。
    `_load` 的 docstring 早已写明这个坑（「实测 148 vs 164，差的 16 处全在这批」），
    本函数此前却用了默认值。判据形态的教训：读取口径本身就是判据的一部分，
    口径错会让正确的登记表被打红。
    """
    for variant, expected in DISCLOSURE_MARKERS[wp].items():
        ws = _ws(wp, variant, data_only=True)
        actual: list[tuple[str, str]] = []
        forms = sorted(MARKER_FORMS, key=len, reverse=True)
        for row in ws.iter_rows():
            for c in row:
                if not isinstance(c.value, str):
                    continue
                for f in forms:
                    if f in c.value:
                        actual.append((c.coordinate, f))
                        break
        assert tuple(actual) == expected, (
            f"{wp}/{variant} 披露 sheet 动态标记不符\n期望={expected}\n实际={tuple(actual)}"
        )


def test_disclosure_markers_total_is_frozen():
    """披露 sheet 内动态标记合计 29 处（全册 164 处里只有这些要判 expandable）。

    🔴 函数名原为 `..._is_18` 而断言写的是 29 —— 名字与断言不同步，读者按名字
    理解会得到错的数。改成不含数字的名字，避免下次调整又留一个骗人的名字。
    """
    n = sum(len(v) for variants in DISCLOSURE_MARKERS.values() for v in variants.values())
    assert n == TOTAL_DISCLOSURE_MARKERS == 29


@pytest.mark.parametrize("wp", ["K8", "K9", "K10", "K11", "K12"])
def test_formula_cell_markers_need_data_only(wp: str):
    """钉死「这批标记格是公式格」这一读取口径，防 `data_only` 被写回默认值。

    `test_disclosure_sheet_markers_frozen` 曾漏传 `data_only=True`，于是这 5 个
    循环恒红「实际=()」，看起来像登记表把坐标写错了。仅把参数补上不够 —— 没有
    任何东西证明「这批必须用缓存值读」，下次有人顺手去掉参数又会红一轮，且仍会
    被误判成登记表的错。这里正反两面都断言：缓存值口径读得到、公式串口径读不到。
    """
    forms = sorted(MARKER_FORMS, key=len, reverse=True)

    def scan(data_only: bool) -> list[str]:
        ws = _ws(wp, "listed", data_only=data_only)
        return [
            c.coordinate
            for row in ws.iter_rows()
            for c in row
            if isinstance(c.value, str) and any(f in c.value for f in forms)
        ]

    expected = [coord for coord, _ in DISCLOSURE_MARKERS[wp]["listed"]]
    assert scan(True) == expected, (
        f"{wp}/listed 缓存值口径读到 {scan(True)}，与登记表 {expected} 不符"
    )
    assert not scan(False), (
        f"{wp}/listed 公式串口径竟读到 {scan(False)} —— 若源模板把这批标记改成了"
        "字面量格，本条与 test_disclosure_sheet_markers_frozen 的 data_only 参数"
        "都应重新评估"
    )


def test_cycles_without_disclosure_markers_are_registered():
    """反向自检：未登记披露标记的循环，其披露 sheet 确实零标记。

    防「登记表漏了某循环」被静默放过。
    """
    missing: list[str] = []
    forms = sorted(MARKER_FORMS, key=len, reverse=True)
    for wp, variants in DISCLOSURE_SHEETS.items():
        for variant in variants:
            if (wp, variant) in {
                (w, v) for w, vs in DISCLOSURE_MARKERS.items() for v in vs
            }:
                continue
            ws = _ws(wp, variant)
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and any(f in c.value for f in forms):
                        missing.append(f"{wp}/{variant}/{c.coordinate}={c.value[:30]!r}")
    assert not missing, (
        f"以下披露 sheet 有动态标记但未登记进 DISCLOSURE_MARKERS：{missing}"
    )


def test_marker_in_narrative_text_is_not_expandable_slot():
    """Requirement 9.8：说明文字里的省略号**不是**可扩位。

    判据不得只看「是否含标记字符」——``?`` 41 处与部分 `……` 属此类
    （如 `1.XX费用较上期增长XX%，本期大幅增加原因……`）。
    本条冻结几个典型样本，供 Task 18 的分类判据做反向自检。
    """
    samples = [
        ("K8", "明细表K8-2", "A28", "本期大幅增加原因"),
        ("K9", "明细表K9-2", "A32", "本期大幅增加原因"),
        ("K5", "未决诉讼检查表 K5-6", "A21", "诉讼判决进展"),
    ]
    wb_cache: dict[str, object] = {}
    for wp, sn, coord, needle in samples:
        wb = wb_cache.setdefault(wp, _load(wp))
        assert sn in wb.sheetnames, f"{wp} 无 sheet「{sn}」"  # type: ignore[union-attr]
        txt = _text(wb[sn], coord)  # type: ignore[index]
        assert needle in txt, (
            f"{wp}/{sn}/{coord} 期望含「{needle}」，实际 {txt[:60]!r} —— "
            "该样本用于证明「含标记字符 ≠ 可扩位」，判据须能区分"
        )
        # 它含标记字符，但语义是叙述文字
        assert any(f in txt for f in MARKER_FORMS)
        assert len(txt) > 12, "叙述文字应远长于纯占位符（长度是可用的辅助判据之一）"


# ─────────────────────────────────────────────────────────────────────────────
# Property 29：两级表头
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp", TWO_LEVEL_CYCLES)
def test_two_level_headers_frozen(wp: str):
    """有两级表头的披露 sheet：父表头 range / 行 / 列跨度 / 文字逐个冻结。"""
    for variant, expected in TWO_LEVEL_HEADERS[wp].items():
        ws = _ws(wp, variant)
        ranges = {str(r) for r in ws.merged_cells.ranges}
        for rng, row, c_from, c_to, text in expected:
            assert rng in ranges, (
                f"{wp}/{variant} 缺合并区 {rng}（期望父表头「{text}」）；"
                f"实际合并区={sorted(ranges)}"
            )
            top_left = ws.cell(row=row, column=c_from).value
            assert str(top_left or "").strip() == text, (
                f"{wp}/{variant} {rng} 父表头文字应「{text}」，实际 {top_left!r}"
            )
            assert c_to > c_from, f"{rng} 不是跨列合并"


def test_single_level_cycles_have_no_data_area_parent_header():
    """反向自检：其余 11 循环的披露表**无数据区跨列父表头** ⇒ 必须标 `flat`。

    ⚠️ 排除 r1/r2 标题行与 `【提示：` 说明段（那些是跨列合并但不是表头）。
    """
    offenders: list[str] = []
    for wp, variants in DISCLOSURE_SHEETS.items():
        if wp in TWO_LEVEL_CYCLES:
            continue
        for variant in variants:
            ws = _ws(wp, variant)
            for rng in ws.merged_cells.ranges:
                if rng.min_row <= 2:  # 标题行
                    continue
                if rng.min_col == rng.max_col:  # 纵向合并
                    continue
                txt = str(ws.cell(row=rng.min_row, column=rng.min_col).value or "")
                if txt.startswith("【") or txt.startswith("（注") or not txt.strip():
                    continue  # 说明段 / 空
                offenders.append(f"{wp}/{variant}/{rng}={txt[:30]!r}")
    assert not offenders, (
        f"以下循环有数据区跨列父表头，应纳入 TWO_LEVEL_CYCLES：{offenders}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 36 / 37：账龄
# ─────────────────────────────────────────────────────────────────────────────


def test_aging_first_band_differs_by_variant():
    """🔴 反向自检：listed 与 soe 的账龄首档字面**必须不同**。

    listed = `1年以内` / soe = `1年以内（含1年）`；共用一份常量即打红。
    """
    assert AGING_FIRST_BAND_LISTED != AGING_FIRST_BAND_SOE
    ws_l = _ws("K1", "listed")
    ws_s = _ws("K1", "soe")
    assert _text(ws_l, "A8").strip() == AGING_FIRST_BAND_LISTED
    assert _text(ws_s, "A7").strip() == AGING_FIRST_BAND_SOE


@pytest.mark.parametrize("wp", sorted(AGING_ROW_ANCHORS, key=lambda c: int(c[1:])))
def test_aging_row_anchors_present(wp: str):
    """账龄作**行**维度的锚点仍在源模板（行集判据的依据）。"""
    for variant, coords in AGING_ROW_ANCHORS[wp].items():
        ws = _ws(wp, variant)
        for coord in coords:
            txt = _text(ws, coord).strip()
            assert txt, f"{wp}/{variant}/{coord} 期望是账龄档位行，实际为空"
            assert re.search(r"年|以内|以上", txt), (
                f"{wp}/{variant}/{coord} 不像账龄档位：{txt!r}"
            )


@pytest.mark.parametrize("wp", sorted(AGING_COLUMN_ANCHORS, key=lambda c: int(c[1:])))
def test_aging_column_anchors_are_columns_not_rows(wp: str):
    """🔴 账龄作**列**维度的 4 处（Requirement 10.3）—— 必须保持为列。

    这 4 处在 K1 两版的前五名表与政府补助表，改成行会与源模板不符。
    """
    for variant, coords in AGING_COLUMN_ANCHORS[wp].items():
        ws = _ws(wp, variant)
        for coord in coords:
            txt = _text(ws, coord).strip()
            assert "账龄" in txt, (
                f"{wp}/{variant}/{coord} 期望是账龄**列头**，实际 {txt!r}"
            )
            # 列头所在行的左侧应有别的列头（证明它是表头行而非数据行）
            row = ws[coord].row
            left = str(ws.cell(row=row, column=1).value or "").strip()
            assert left, f"{wp}/{variant} 第 {row} 行首列为空，不像表头行"


def test_aging_column_anchor_count_is_four():
    """账龄作列共 4 处（两版各 2 处）。"""
    n = sum(len(v) for variants in AGING_COLUMN_ANCHORS.values() for v in variants.values())
    assert n == 4, f"账龄列锚点应 4 处，实际 {n}"


def test_k1_listed_monthly_detail_rows_exist():
    """Requirement 10.4：K1 listed 的月度细分行是源模板事实，必须保留。"""
    ws = _ws("K1", "listed")
    for coord, text in K1_MONTHLY_DETAIL_ANCHORS:
        assert _text(ws, coord).strip() == text, (
            f"K1 listed {coord} 期望「{text}」，实际 {_text(ws, coord)!r}"
        )


def test_k3_aging_over_one_year_is_standalone_section():
    """Requirement 10.5：K3 两版的「账龄超过1年」段是独立表（表内无账龄列/行）。"""
    for variant in ("listed", "soe"):
        ws = _ws("K3", variant)
        txt = _text(ws, K3_NATURE_LABEL_HEADER[variant]).strip()
        assert "账龄超过1年" in txt, (
            f"K3/{variant} A18 期望「其中，账龄超过1年的重要其他应付款」，实际 {txt!r}"
        )


def test_no_aging_cycles_have_zero_aging_hits():
    """反向自检：无账龄维度的 11 循环，披露 sheet 确实零账龄命中。

    Requirement 10.6 要反向锁死这些循环不得引入账龄枚举；
    先证明源模板侧确实没有（否则那条锁死是错的）。
    """
    with_aging = set(AGING_ROW_ANCHORS) | set(AGING_COLUMN_ANCHORS) | {"K3"}
    offenders: list[str] = []
    for wp, variants in DISCLOSURE_SHEETS.items():
        if wp in with_aging:
            continue
        for variant in variants:
            ws = _ws(wp, variant)
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and "账龄" in c.value:
                        offenders.append(f"{wp}/{variant}/{c.coordinate}={c.value[:30]!r}")
    assert not offenders, (
        f"以下循环披露 sheet 含「账龄」，Requirement 10.6 的反向锁死需复核：{offenders}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 31：源模板自身缺陷登记 + stale 检测
# ─────────────────────────────────────────────────────────────────────────────


def test_k1_ref_errors_still_reproduce():
    """🔴 K1 两版 `#REF!` 断链仍复现（**70 处，推翻初稿记的 11 处**）。

    stale 检测：源模板哪天修好了本条打红，提醒把它从「已知缺陷」移出。
    """
    for variant, expected in K1_REF_ERROR_COUNTS.items():
        ws = _ws("K1", variant)
        n = 0
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "#REF!" in c.value:
                    n += 1
        assert n == expected, (
            f"K1/{variant} `#REF!` 应 {expected} 处，实际 {n} —— "
            "若源模板已修好，请把本条与 Requirement 8.6 的登记一并更新"
        )


def test_k1_ref_error_total_is_70_not_11():
    """推翻初稿：K1 的 `#REF!` 合计 70 处（listed 35 + soe 35），不是 11 处。"""
    assert sum(K1_REF_ERROR_COUNTS.values()) == 70


def test_k6_total_row_carrying_amount_is_narrative_text():
    """K6 合计行「账面价值」列是说明文字而非公式 ⇒ 载荷层须派生。

    源模板把 `C=A+B=报表数` 这类说明写进了数据格；照抄会把说明文字推进附注。
    """
    for variant, (coord, needle) in K6_TOTAL_ROW_TEXT_CELLS.items():
        ws = _ws("K6", variant)
        txt = _text(ws, coord)
        assert needle in txt, (
            f"K6/{variant} {coord} 期望含说明文字「{needle}」，实际 {txt!r} —— "
            "该格是源模板缺陷登记依据（Requirement 8.6），"
            "若源模板已改为公式请更新登记"
        )
        assert not txt.startswith("="), "说明文字不应是公式"


def test_source_defect_registry_is_nonempty():
    """反向自检：源模板缺陷登记表非空（空表意味着 stale 检测在空转）。"""
    assert K1_REF_ERROR_COUNTS
    assert K6_TOTAL_ROW_TEXT_CELLS
    assert K3_NATURE_LABEL_HEADER
