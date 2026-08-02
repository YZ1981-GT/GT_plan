"""共享表段解析守卫（行级合并的段边界真源）。

**Validates: Requirements 2.1, 2.5, 2.6, 2.7, 4.4 / Properties 4, 18**

覆盖：
- Property 4：段数 == 带 `report_row_code` 的行数；区间两两不重叠且并集连续
- Property 18：变体解析**不按章节号推导**（20 个撞号章节、13 个标题不同）
- Requirement 4.4：`stamp_baseline_rows` 的 `_seg` 向下传播、数值置空
- Requirement 3.4：`find_stamped_window` 按落库 `_seg` 定位（标签跨段重复不串段）

两条**反向自检**：
1. 改成「按标签分组」→「标签重复不串段」必失败
2. 改成「按章节号谁有取谁」→ `八、1` 必取错模板
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_shared_table_segments import (
    MIN_SHARED_SEGMENTS,
    SEG_KEY,
    VARIANT_LISTED,
    VARIANT_SOE,
    VARIANTS,
    UNOWNED_ROW_TYPE,
    find_segment,
    find_stamped_window,
    has_discontiguous_stamp,
    is_shared_rows,
    is_shared_table,
    iter_shared_tables,
    resolve_segment_window,
    resolve_template_variant,
    segment_row_codes,
    split_segments,
    stamp_baseline_rows,
    template_rows,
)

# 外币货币性项目：soe `八、92` 25 行 5 段 / listed `五、73` 16 行 3 段（2026-08-02 实测）
def _is_unowned_row_public(row) -> bool:
    """测试侧的无主行判定（不依赖被测模块的私有函数，避免自证）。"""
    return isinstance(row, dict) and str(row.get("row_type") or "").strip() == UNOWNED_ROW_TYPE


FX_SOE = (VARIANT_SOE, "八、92", "外币货币性项目")
FX_LISTED = (VARIANT_LISTED, "五、73", "外币货币性项目")


class TestUnownedPBT:
    """Property 4（PBT）：可写区永不跨越 `unowned` 行。"""

    @settings(max_examples=60, deadline=None)
    @given(
        kinds=st.lists(
            st.sampled_from(["head", "data", "unowned", "total"]), min_size=2, max_size=12
        )
    )
    def test_writable_window_never_crosses_unowned(self, kinds):
        rows: list[dict] = []
        code_n = 0
        for k in kinds:
            if k == "head":
                code_n += 1
                rows.append({"label": f"h{code_n}", "report_row_code": f"BS-{code_n:03d}"})
            elif k == "data":
                rows.append({"label": f"d{len(rows)}"})
            elif k == "unowned":
                rows.append({"label": f"u{len(rows)}", "row_type": UNOWNED_ROW_TYPE})
            else:
                rows.append({"label": "合计", "is_total": True})

        for seg in split_segments(rows):
            assert seg.start < seg.data_end <= seg.end
            body = rows[seg.start + 1 : seg.data_end]
            assert not any(_is_unowned_row_public(r) for r in body), (
                f"可写区 [{seg.start},{seg.data_end}) 跨越了 unowned 行"
            )
            # 段首行永远在可写区内（否则 owner 无处落笔）
            assert seg.data_end >= seg.start + 1


class TestSplitSegmentsPure:
    """Property 4：段边界只由 `report_row_code` 决定。"""

    def test_basic_split(self):
        rows = [
            {"label": "货币资金", "report_row_code": "BS-002"},
            {"label": "其中：美元"},
            {"label": "欧元"},
            {"label": "应收账款", "report_row_code": "BS-006"},
            {"label": "其中：美元"},
        ]
        segs = split_segments(rows)
        assert [(s.row_code, s.label, s.start, s.end) for s in segs] == [
            ("BS-002", "货币资金", 0, 3),
            ("BS-006", "应收账款", 3, 5),
        ]
        assert [s.length for s in segs] == [3, 2]

    def test_rows_before_first_head_belong_to_no_segment(self):
        """首个段首行之前的行（表内说明行）不属于任何段。"""
        rows = [
            {"label": "（提示：按币种列示）"},
            {"label": "货币资金", "report_row_code": "BS-002"},
            {"label": "其中：美元"},
        ]
        segs = split_segments(rows)
        assert len(segs) == 1
        assert (segs[0].start, segs[0].end) == (1, 3)

    def test_empty_and_malformed_rows(self):
        assert split_segments(None) == []
        assert split_segments([]) == []
        # 非 dict 行 / 空白 code 一律不当段首
        assert split_segments(["x", None, {"report_row_code": "   "}]) == []

    def test_segment_row_codes_dedup_and_order(self):
        rows = [
            {"report_row_code": "BS-002"},
            {"report_row_code": "BS-006"},
            {"report_row_code": "BS-002"},  # 模板不应如此，但不崩
        ]
        assert segment_row_codes(rows) == ["BS-002", "BS-006"]

    def test_find_segment_takes_first_on_duplicate(self):
        rows = [{"report_row_code": "A"}, {"report_row_code": "B"}, {"report_row_code": "A"}]
        seg = find_segment(rows, "A")
        assert (seg.start, seg.end) == (0, 1)
        assert find_segment(rows, "ZZ") is None
        assert find_segment(rows, "") is None

    def test_is_shared_rows(self):
        assert is_shared_rows([{"report_row_code": "A"}, {"report_row_code": "B"}]) is True
        assert is_shared_rows([{"report_row_code": "A"}, {"label": "x"}]) is False
        assert is_shared_rows([]) is False


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(st.booleans(), st.integers(min_value=0, max_value=4)),
        min_size=0,
        max_size=14,
    )
)
def test_property4_segments_are_disjoint_and_contiguous(spec):
    """PBT：随机位置插 `report_row_code` → 区间两两不重叠、并集连续、段首必带 code。"""
    rows = []
    for is_head, n in spec:
        rows.append({"label": f"r{n}", "report_row_code": f"BS-{n:03d}"} if is_head
                    else {"label": f"r{n}"})
    segs = split_segments(rows)
    heads = [i for i, r in enumerate(rows) if r.get("report_row_code")]

    assert len(segs) == len(heads)
    for seg, idx in zip(segs, heads):
        assert seg.start == idx
        assert rows[seg.start].get("report_row_code") == seg.row_code
        assert seg.end > seg.start
    # 两两不重叠 + 首尾相接（并集 = 首个段首 → 表尾）
    for a, b in zip(segs, segs[1:]):
        assert a.end == b.start
    if segs:
        assert segs[-1].end == len(rows)
        covered = sum(s.length for s in segs)
        assert covered == len(rows) - heads[0]


class TestStampBaselineRows:
    """Requirement 4.4：`_seg` 向下传播、数值置空、标签保留。"""

    def test_seg_propagates_downward(self):
        rows = [
            {"label": "货币资金", "report_row_code": "BS-002", "account_codes": ["1001"]},
            {"label": "其中：美元", "row_type": "data"},
            {"label": "应收账款", "report_row_code": "BS-006"},
            {"label": "其中：美元"},
        ]
        base = stamp_baseline_rows(rows)
        assert [r[SEG_KEY] for r in base] == ["BS-002", "BS-002", "BS-006", "BS-006"]
        assert [r["label"] for r in base] == ["货币资金", "其中：美元", "应收账款", "其中：美元"]

    def test_template_metadata_not_persisted_values_blank(self):
        """`report_row_code` / `account_codes` 是模板元数据不落库；数值列一律不预置。"""
        base = stamp_baseline_rows([
            {"label": "货币资金", "report_row_code": "BS-002", "account_codes": ["1001"],
             "fc_amount": 999},
        ])
        assert base == [{"label": "货币资金", SEG_KEY: "BS-002"}]
        assert "report_row_code" not in base[0]
        assert "account_codes" not in base[0]
        assert "fc_amount" not in base[0], "数值列不得预置（保持「空」而非 0）"

    def test_rows_before_first_head_get_empty_seg(self):
        base = stamp_baseline_rows([{"label": "说明行"}, {"label": "A", "report_row_code": "X"}])
        assert base[0][SEG_KEY] == ""
        assert base[1][SEG_KEY] == "X"

    def test_is_total_and_row_type_kept(self):
        base = stamp_baseline_rows([
            {"label": "合计", "report_row_code": "X", "is_total": True},
            {"label": "……", "row_type": "placeholder"},
            {"label": "普通", "row_type": "data"},
        ])
        assert base[0]["is_total"] is True
        assert base[1]["row_type"] == "placeholder"
        assert "row_type" not in base[2], "row_type=data 是默认值，不必落库"


class TestFindStampedWindow:
    """Requirement 3.4：落库侧靠 `_seg` 定位，标签跨段重复不串段。"""

    ROWS = [
        {"label": "货币资金", SEG_KEY: "BS-002"},
        {"label": "其中：美元", SEG_KEY: "BS-002"},
        {"label": "应收账款", SEG_KEY: "BS-006"},
        {"label": "其中：美元", SEG_KEY: "BS-006"},
        {"label": "短期借款", SEG_KEY: "BS-031"},
    ]

    def test_window_for_each_owner(self):
        assert find_stamped_window(self.ROWS, "BS-002") == (0, 2)
        assert find_stamped_window(self.ROWS, "BS-006") == (2, 4)
        assert find_stamped_window(self.ROWS, "BS-031") == (4, 5)
        assert find_stamped_window(self.ROWS, "BS-999") is None
        assert find_stamped_window(self.ROWS, "") is None

    def test_duplicate_labels_across_segments_do_not_leak(self):
        """🔴「其中：美元」在两段都有 —— 窗口必须只覆盖 owner 那一段。"""
        dup = [i for i, r in enumerate(self.ROWS) if r["label"] == "其中：美元"]
        assert len(dup) == 2, "反向自检：fixture 必须真有跨段重复标签"
        s, e = find_stamped_window(self.ROWS, "BS-002")
        assert dup[0] in range(s, e)
        assert dup[1] not in range(s, e)

    def test_reverse_check_label_grouping_would_leak(self):
        """反向自检：改成「按标签分组」则两段的「其中：美元」会被归到一起。"""
        by_label: dict[str, list[int]] = {}
        for i, r in enumerate(self.ROWS):
            by_label.setdefault(r["label"], []).append(i)
        leaked = by_label["其中：美元"]
        assert len(leaked) == 2, "按标签分组必然跨段串味 → 证明 `_seg` 方案必要"

    def test_discontiguous_stamp_takes_first_run_and_is_flagged(self):
        rows = [
            {"label": "a", SEG_KEY: "X"},
            {"label": "b", SEG_KEY: "Y"},
            {"label": "c", SEG_KEY: "X"},   # 历史脏数据：X 不连续
        ]
        assert find_stamped_window(rows, "X") == (0, 1)
        assert has_discontiguous_stamp(rows, "X") is True
        assert has_discontiguous_stamp(rows, "Y") is False


class TestResolveTemplateVariant:
    """Property 18：变体解析**不按章节号推导**。"""

    @pytest.mark.parametrize(
        "standard,expected",
        [
            ("listed_standalone", VARIANT_LISTED),
            ("listed_consolidated", VARIANT_LISTED),
            ("soe_standalone", VARIANT_SOE),
            ("soe_consolidated", VARIANT_SOE),
            ("SOE_STANDALONE", VARIANT_SOE),
            ("  listed  ", VARIANT_LISTED),
        ],
    )
    def test_from_current_standard(self, standard, expected):
        assert resolve_template_variant(standard) == expected

    def test_falls_back_to_source_template(self):
        assert resolve_template_variant(None, "soe") == VARIANT_SOE
        assert resolve_template_variant("general", "listed") == VARIANT_LISTED

        class _Enum:
            value = "soe"

        assert resolve_template_variant(None, _Enum()) == VARIANT_SOE

    def test_returns_none_when_undeterminable(self):
        """Requirement 2.7：无法确定 → None → 调用方 fail closed。"""
        assert resolve_template_variant(None, None) is None
        assert resolve_template_variant("general", None) is None
        assert resolve_template_variant("", "") is None


class TestTemplateLookupRealData:
    """真实模板行集：外币表段区间逐个钉死。"""

    def test_soe_fx_table_has_five_segments(self):
        rows = template_rows(*FX_SOE)
        assert rows is not None and len(rows) == 25
        segs = split_segments(rows)
        assert [(s.row_code, s.label, s.start, s.end) for s in segs] == [
            ("BS-002", "货币资金", 0, 5),
            ("BS-006", "应收账款", 5, 10),
            ("BS-031", "短期借款", 10, 15),
            ("BS-061", "长期借款", 15, 20),
            ("BS-062", "应付债券", 20, 25),
        ]

    def test_listed_fx_table_has_three_segments(self):
        rows = template_rows(*FX_LISTED)
        assert rows is not None and len(rows) == 16
        segs = split_segments(rows)
        assert [(s.row_code, s.label, s.start, s.end) for s in segs] == [
            ("BS-002", "货币资金", 0, 5),
            ("BS-006", "应收账款", 5, 10),
            ("BS-061", "长期借款", 10, 16),
        ]

    def test_both_variants_are_shared_tables(self):
        assert is_shared_table(*FX_SOE) is True
        assert is_shared_table(*FX_LISTED) is True

    def test_resolve_segment_window_real(self):
        seg = resolve_segment_window(*FX_SOE, "BS-002")
        assert (seg.start, seg.end) == (0, 5)
        assert resolve_segment_window(*FX_SOE, "BS-999") is None

    def test_missing_table_or_section_returns_none(self):
        """fail closed 的前置条件：查不到就是 None，不给兜底。"""
        assert template_rows(VARIANT_SOE, "八、92", "不存在的表") is None
        assert template_rows(VARIANT_SOE, "不存在的章节", "外币货币性项目") is None
        assert template_rows("bogus", "八、92", "外币货币性项目") is None
        assert template_rows(VARIANT_SOE, "", "外币货币性项目") is None
        assert is_shared_table(VARIANT_SOE, "八、92", "不存在的表") is False

    def test_baseline_from_real_template_keeps_all_segments(self):
        """Property 8 前置：基线含**全部**段的标签，数值为空。"""
        from app.services.note_shared_table_segments import template_baseline_rows

        base = template_baseline_rows(*FX_SOE)
        assert len(base) == 25
        assert {r[SEG_KEY] for r in base} == {
            "BS-002", "BS-006", "BS-031", "BS-061", "BS-062"
        }
        for r in base:
            assert set(r) <= {"label", SEG_KEY, "is_total", "row_type"}


class TestSharedTableInventory:
    """全库共享表普查（Property 14 的数据基础）。"""

    def test_counts_match_measured_baseline(self):
        """实测基线：listed 23 张 / soe 6 张，共 29 张。"""
        listed = list(iter_shared_tables(VARIANT_LISTED))
        soe = list(iter_shared_tables(VARIANT_SOE))
        assert len(listed) == 23, f"listed 共享表数变了：{[t[2] for t in listed]}"
        assert len(soe) == 6, f"soe 共享表数变了：{[t[2] for t in soe]}"

    def test_every_shared_table_has_at_least_two_segments(self):
        for variant in (VARIANT_LISTED, VARIANT_SOE):
            for num, _title, name, _rows, segs in iter_shared_tables(variant):
                codes = {s.row_code for s in segs}
                assert len(codes) >= MIN_SHARED_SEGMENTS, f"{variant} {num} {name}"

    def test_key_tables_are_in_inventory(self):
        """立 spec 时列举的重点表必须在清单里（防判据漂移）。

        🔴 章节号逐字取自实测（`五、32` 不是 `五、82`、`五、71` 不是 `五、81`），
        表名两版用字不同（listed「所有权**或**使用权」/ soe「所有权**和**使用权」）。
        """
        soe = {(n, t) for n, _ti, t, _r, _s in iter_shared_tables(VARIANT_SOE)}
        listed = {(n, t) for n, _ti, t, _r, _s in iter_shared_tables(VARIANT_LISTED)}
        assert ("八、92", "外币货币性项目") in soe
        assert ("八、93", "所有权和使用权受到限制的资产") in soe
        assert ("八、81", "筹资活动产生的各项负债的变动情况") in soe
        assert ("八、31", "未经抵销的递延所得税资产和递延所得税负债") in soe
        assert ("五、73", "外币货币性项目") in listed
        assert ("五、32", "所有权或使用权受到限制的资产") in listed
        # 「续：」已由 restricted-assets-note-row-scope-rollout Task 3 正名
        # （裸续表名会跨章节撞键，`sub_table_data` 以表名为键）
        assert ("五、32", "所有权或使用权受到限制的资产（续：上年年末）") in listed
        assert ("五、32", "续：") not in listed
        assert ("五、71", "资产负债表中的列报项目和相关信息") in listed

    def test_duplicate_row_code_in_one_table_is_tolerated(self):
        """🔴 真实边界：listed 风险管理有一张表段序为 `BS-041 / BS-002 / BS-041`。

        `find_segment` 取**首个**匹配段（不合并两段 —— 合并会跨过中间的 BS-002 段，
        把他人行卷进来）；`segment_row_codes` 去重后仍 ≥2 故仍算共享表。
        """
        dup = [
            (n, t, [s.row_code for s in segs])
            for n, _ti, t, _r, segs in iter_shared_tables(VARIANT_LISTED)
            if len([s.row_code for s in segs]) != len({s.row_code for s in segs})
        ]
        assert len(dup) == 1, f"重复 row_code 的表数变了：{dup}"
        _num, _name, codes = dup[0]
        assert codes == ["BS-041", "BS-002", "BS-041"]

        rows = [
            {"label": "a", "report_row_code": "BS-041"},
            {"label": "b"},
            {"label": "c", "report_row_code": "BS-002"},
            {"label": "d", "report_row_code": "BS-041"},
        ]
        seg = find_segment(rows, "BS-041")
        assert (seg.start, seg.end) == (0, 2), "只取首段，不得跨过中间的 BS-002 段"
        assert segment_row_codes(rows) == ["BS-041", "BS-002"]

    def test_empty_table_name_is_excluded_from_lookup(self):
        """🔴 真实脏数据：listed 风险管理有一张表 `name=''`（空表名）。

        空表名无法作为 `sub_table_data` 的键，`template_rows` 必须拒绝它
        （否则行级合并会去查一张永远匹配不上的表）。属另一个 data-hygiene 点，
        本 spec 只保证不被误用。
        """
        empties = [
            (n, t) for n, _ti, t, _r, _s in iter_shared_tables(VARIANT_LISTED) if not t
        ]
        assert len(empties) == 1, f"空表名的表数变了：{empties}"
        assert template_rows(VARIANT_LISTED, empties[0][0], "") is None

    def test_data_end_excludes_trailing_total_rows(self):
        """🔴 段尾的表级汇总行（合计/小计）**不属于任何段**。

        `五、32 所有权或使用权受到限制的资产` 的末段 `BS-032 无形资产` 是 [5,8)，
        尾部挂着 `……`（该段合法可扩行）与 `合计`（表级汇总）。若把合计行算进段内，
        owner 一推数据就会**把合计行删掉**。

        （下标在 Task 3 删掉 `header_label` 假行后整体前移一位。）
        """
        rows = template_rows(VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产")
        assert rows is not None
        assert len(rows) == 8, "6 个科目段 + 可扩行 + 合计（假行已删）"
        seg = find_segment(rows, "BS-032")
        assert (seg.start, seg.end) == (5, 8)
        assert seg.data_end == 7, "合计行（下标 7）必须排除在可写区之外"
        assert seg.data_length == 2, "段首「无形资产」+ 可扩行「……」"
        # `……` 是该段留给 owner 的可扩行 → **在**可写区内
        assert str(rows[6].get("label")) == "……"
        assert str(rows[7].get("label")) == "合计"
        assert rows[7].get("is_total") is True

    def test_data_end_equals_end_when_no_total(self):
        """无汇总行的段 `data_end == end` → 引入该字段前后逐字等价（零回归支点）。"""
        for variant, num in ((VARIANT_SOE, "八、92"), (VARIANT_LISTED, "五、73")):
            rows = template_rows(variant, num, "外币货币性项目")
            for seg in split_segments(rows):
                assert seg.data_end == seg.end, f"{variant} {num} {seg.row_code}"

    def test_placeholder_rows_stay_inside_segment(self):
        """`……` / `可无限量添加行` 是段内**合法可扩行**，不得被当成无主行剔除。"""
        rows = template_rows(VARIANT_SOE, "八、92", "外币货币性项目")
        seg = find_segment(rows, "BS-002")
        assert (seg.start, seg.data_end) == (0, 5)
        assert str(rows[4].get("label")) == "……"

    def test_orphan_total_count_baseline(self):
        """实测基线：**15 个段**的可写区窄于段区间（变了就要核实并更新）。

        14 条是「表最后一行的 合计 / 小计」（表级汇总，剔除后 owner 推送不会删掉它），
        1 条是 soe `八、93 受限资产` 末行「其他」—— 模板显式标 `row_type: "unowned"`
        的表级兜底行（`restricted-assets-note-row-scope-rollout` Task 3 加的）。
        """
        hits = [
            (variant, num, name, seg.row_code, tuple(
                (str(r.get("label")), str(r.get("row_type") or ""))
                for r in rows[seg.data_end : seg.end]
            ))
            for variant in VARIANTS
            for num, _t, name, rows, segs in iter_shared_tables(variant)
            for seg in segs
            if seg.data_end != seg.end
        ]
        assert len(hits) == 15, f"受影响段数变了：{hits}"
        for *_x, cut in hits:
            for lab, row_type in cut:
                assert "计" in lab or row_type == UNOWNED_ROW_TYPE, (
                    f"被剔除的行既不是汇总行也没标 unowned：{lab!r}"
                )
        keys = {(v, n, name) for v, n, name, _c, _l in hits}
        assert (VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产") in keys
        assert (VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产（续：上年年末）") in keys
        # soe `八、93` 的 unowned 兜底行「其他」（Task 3 新增）
        assert (VARIANT_SOE, "八、93", "所有权和使用权受到限制的资产") in keys
        assert (VARIANT_LISTED, "五、71", "资产负债表中的列报项目和相关信息") in keys
        assert (VARIANT_SOE, "八、91", "资产负债表中的列报项目和相关信息") in keys
        assert (VARIANT_SOE, "八、81", "筹资活动产生的各项负债的变动情况") in keys
        # 外币表（本 spec 首个消费者）零影响
        assert not any(name == "外币货币性项目" for _v, _n, name, _c, _l in hits)

    def test_per_segment_subtotals_are_not_trimmed(self):
        """🔴 **段级小计**属段内，不得剔除（与表级合计相反）。

        `五、30`/`八、31` 递延所得税表**每个段**尾部都有自己的小计
        （资产小计 / 负债小计）→ 判定为「段级小计」模式 → `data_end == end`。
        判据是数据驱动的（是否每个段都有尾部汇总行），不靠配置白名单。
        """
        for variant, num in ((VARIANT_LISTED, "五、30"), (VARIANT_SOE, "八、31")):
            rows = template_rows(variant, num, "未经抵销的递延所得税资产和递延所得税负债")
            assert rows is not None, f"{variant} {num}"
            segs = split_segments(rows)
            assert len(segs) == 2
            assert all(str(rows[s.end - 1].get("label") or "").strip() == "小计" for s in segs), (
                "前提：两段尾部都是「小计」"
            )
            for s in segs:
                assert s.data_end == s.end, f"{variant} {num} {s.row_code} 的段级小计被误剔除"

    def test_stamp_leaves_total_rows_unstamped(self):
        """汇总行的 `_seg` 必须留空 → `find_stamped_window` 天然止于合计行前。"""
        rows = template_rows(VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产")
        stamped = stamp_baseline_rows(rows)
        assert stamped[7]["label"] == "合计"
        assert stamped[7][SEG_KEY] == "", "合计行不属于任何 owner"
        assert stamped[6][SEG_KEY] == "BS-032", "`……` 属无形资产段"
        assert find_stamped_window(stamped, "BS-032") == (5, 7)

    def test_reverse_check_data_end_without_fix_would_swallow_total(self):
        """🔴 反向自检：若 `data_end` 退化为 `end`，合计行必被卷进末段。"""
        rows = template_rows(VARIANT_LISTED, "五、71", "资产负债表中的列报项目和相关信息")
        seg = find_segment(rows, "BS-050")
        assert (seg.start, seg.end, seg.data_end) == (4, 7, 6)
        swallowed = [str(r.get("label")) for r in rows[seg.data_end : seg.end]]
        assert swallowed == ["合计"], f"退化口径会吞掉 {swallowed}"

    def test_unowned_row_at_segment_tail_shrinks_writable_window(self):
        """🔴 显式无主行（`row_type: "unowned"`）不属于任何段的可写区。

        场景来自 soe `八、93 受限资产` 末行「其他」：紧随 `BS-029 在建工程` 段之后，
        既不是合计行（`data_end` 既有判据抓不到）也不是该段可扩行 →
        必须由模板**显式**声明，否则 H2 一推数据就把它删掉。
        """
        rows = [
            {"label": "在建工程", "report_row_code": "BS-029"},
            {"label": "自建厂房"},
            {"label": "其他", "row_type": UNOWNED_ROW_TYPE},
        ]
        seg = find_segment(rows, "BS-029")
        assert (seg.start, seg.end, seg.data_end) == (0, 3, 2)
        assert seg.data_length == 2

    def test_unowned_row_in_middle_truncates_not_skips(self):
        """Requirement 2.5：段中间的无主行让可写区**提前截断**，不得跨越保留。

        跨越保留会把 owner 的数据劈成两段（前半 + 后半），顺序不可控。
        """
        rows = [
            {"label": "货币资金", "report_row_code": "BS-002"},
            {"label": "银行承兑保证金"},
            {"label": "未分类", "row_type": UNOWNED_ROW_TYPE},
            {"label": "其他受限"},
            {"label": "应收票据", "report_row_code": "BS-005"},
        ]
        seg = find_segment(rows, "BS-002")
        assert (seg.start, seg.end, seg.data_end) == (0, 4, 2)

    def test_multiple_unowned_rows_use_first(self):
        rows = [
            {"label": "存货", "report_row_code": "BS-010"},
            {"label": "a", "row_type": UNOWNED_ROW_TYPE},
            {"label": "b", "row_type": UNOWNED_ROW_TYPE},
        ]
        seg = find_segment(rows, "BS-010")
        assert seg.data_end == 1

    def test_unowned_head_row_is_ignored(self):
        """段首行本身若被标 unowned（模板写错）→ 可写区至少保住段首行，不产出空区间。"""
        rows = [
            {"label": "存货", "report_row_code": "BS-010", "row_type": UNOWNED_ROW_TYPE},
            {"label": "抵押存货"},
        ]
        seg = find_segment(rows, "BS-010")
        assert seg.start < seg.data_end <= seg.end

    def test_unowned_rows_unstamped_and_window_stops_before(self):
        rows = [
            {"label": "在建工程", "report_row_code": "BS-029"},
            {"label": "自建厂房"},
            {"label": "其他", "row_type": UNOWNED_ROW_TYPE},
        ]
        stamped = stamp_baseline_rows(rows)
        assert stamped[2][SEG_KEY] == "", "无主行的 `_seg` 必须留空"
        assert stamped[2]["row_type"] == UNOWNED_ROW_TYPE
        assert find_stamped_window(stamped, "BS-029") == (0, 2)

    #: 使用 `row_type: "unowned"` 的表登记表（只许按 spec 增，不许悄悄冒出来）。
    #: 值 = 该表里 unowned 行的 label 列表。
    UNOWNED_REGISTRY = {
        (VARIANT_SOE, "八、93", "所有权和使用权受到限制的资产"): ["其他"],
    }

    def test_unowned_usage_is_registered(self):
        """全库哪些表用了 `unowned` 必须显式登记（防止悄悄扩散改变段语义）。"""
        actual: dict[tuple[str, str, str], list[str]] = {}
        for variant in VARIANTS:
            for num, _t, name, rows, _segs in iter_shared_tables(variant):
                labels = [str(r.get("label")) for r in rows if _is_unowned_row_public(r)]
                if labels:
                    actual[(variant, num, name)] = labels
        assert actual == self.UNOWNED_REGISTRY, (
            "unowned 行的使用面变了 —— 请在对应 spec 里说明后更新本登记表"
        )

    def test_property3_segments_match_manifest(self):
        """段区间与清单逐段一致（清单由生成器产出，是唯一真源）。"""
        gen = _load_generator()
        manifest = json.loads(gen.OUT_PATH.read_text(encoding="utf-8"))
        # 🔴 不能按 (variant, section, table_name) 建字典 —— 同一章节里存在**重名表**
        #    （`三、在合营安排或联营` 有两张 `项  目`），建字典会互相覆盖。按**顺序**比对。
        want = [
            (t["variant"], t["section_number"], t["table_name"],
             [(s["start"], s["end"], s["data_end"]) for s in t["segments"]])
            for t in manifest["tables"]
        ]
        got = []
        for variant in VARIANTS:
            for num, _t, name, rows, segs in iter_shared_tables(variant):
                got.append((variant, num, name, [(s.start, s.end, s.data_end) for s in segs]))
        assert len(got) == 29
        assert got == want, "段区间与清单漂移 → 重跑 gen_note_shared_table_segments.py --write"

    def test_unowned_only_narrows_its_own_table(self):
        """零回归的现行凭据：除登记表里的表以外，`data_end < end` 只由**汇总行**造成。"""
        for variant in VARIANTS:
            for num, _t, name, rows, segs in iter_shared_tables(variant):
                if (variant, num, name) in self.UNOWNED_REGISTRY:
                    continue
                for seg in segs:
                    for r in rows[seg.data_end : seg.end]:
                        assert not _is_unowned_row_public(r), f"{variant} {num} {name}"

    def test_reverse_check_unowned_without_fix_would_delete_row(self):
        """🔴 反向自检：不认 `unowned` 时（可写区取到 `end`），相邻段推送必删该行。"""
        rows = [
            {"label": "在建工程", "report_row_code": "BS-029"},
            {"label": "其他", "row_type": UNOWNED_ROW_TYPE},
        ]
        seg = find_segment(rows, "BS-029")
        naive = rows[: seg.start] + [{"label": "x"}] + rows[seg.end :]
        assert not any(r.get("label") == "其他" for r in naive), "退化口径确实删掉了无主行"
        good = rows[: seg.start] + [{"label": "x"}] + rows[seg.data_end :]
        assert good[-1]["label"] == "其他"

    def test_reverse_check_section_number_lookup_would_pick_wrong_template(self):
        """🔴 反向自检：按章节号「谁有取谁」→ `八、1` 必取错模板。

        实测 `八、1` 在 listed 是「政府补助」、在 soe 是「货币资金」。
        若变体解析退化为「先查 listed，没有再查 soe」，soe 项目的 `八、1`
        就会拿到政府补助的行集 → 段边界全错。
        """
        from app.services.note_shared_table_segments import _template_doc

        def _title(variant: str, num: str) -> str | None:
            for sec in _template_doc(variant).get("sections") or []:
                if str(sec.get("section_number") or "").strip() == num:
                    return str(sec.get("section_title") or "").strip()
            return None

        assert _title(VARIANT_LISTED, "八、1") == "政府补助"
        assert _title(VARIANT_SOE, "八、1") == "货币资金"
        # 正确实现按 current_standard 取，不会串
        assert resolve_template_variant("soe_standalone") == VARIANT_SOE
        assert resolve_template_variant("listed_standalone") == VARIANT_LISTED


# ---------------------------------------------------------------------------
# Property 14：共享表清单（`backend/data/note_shared_table_segments.json`）
# 与模板不得漂移。清单只供守卫/前端消费，服务端运行期直接读模板。
# ---------------------------------------------------------------------------

_GEN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gen" / "gen_note_shared_table_segments.py"


def _load_generator():
    """按路径加载生成器（`backend/scripts/gen` 不是包）。"""
    spec = importlib.util.spec_from_file_location("_gen_shared_table_segments", _GEN_PATH)
    assert spec and spec.loader, f"无法加载生成器：{_GEN_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestManifestDrift:
    """Property 14：清单 ↔ 模板双向锁死。"""

    def test_generator_exists(self):
        assert _GEN_PATH.exists(), f"生成器缺失：{_GEN_PATH}"

    def test_check_passes(self, monkeypatch):
        """`--check` 必须 0 欠账（清单是最新的）。"""
        gen = _load_generator()
        monkeypatch.setattr(sys, "argv", ["gen_note_shared_table_segments.py", "--check"])
        assert gen.main() == 0, "共享表清单与模板漂移 —— 请重跑 --write"

    def test_manifest_counts_match_baseline(self):
        gen = _load_generator()
        payload = json.loads(gen.OUT_PATH.read_text(encoding="utf-8"))
        assert payload["counts"] == {VARIANT_LISTED: 23, VARIANT_SOE: 6}
        assert len(payload["tables"]) == 29

    def test_manifest_segments_wellformed(self):
        """清单里每张表都必须是**真**共享表且段区间自洽。"""
        gen = _load_generator()
        payload = json.loads(gen.OUT_PATH.read_text(encoding="utf-8"))
        for t in payload["tables"]:
            segs = t["segments"]
            label = f"{t['variant']} {t['section_number']} {t['table_name']}"
            assert len(segs) >= MIN_SHARED_SEGMENTS, f"{label} 段数 < {MIN_SHARED_SEGMENTS}"
            # 区间递增、两两不重叠、不越界
            prev_end = 0
            for s in segs:
                assert 0 <= s["start"] < s["end"] <= t["row_count"], f"{label} 段越界：{s}"
                assert s["start"] >= prev_end, f"{label} 段重叠：{s}"
                prev_end = s["end"]
            assert str(t["table_name"] or "").strip() or t["table_name"] == "", label

    def test_manifest_has_no_timestamp(self):
        """清单不得含时间戳/生成时刻 —— 否则每次生成都 drift。"""
        gen = _load_generator()
        text = gen.OUT_PATH.read_text(encoding="utf-8")
        for banned in ("generated_at", "timestamp", "_at\":"):
            assert banned not in text, f"清单含易漂移字段 {banned!r}"

    def test_write_is_idempotent(self):
        """`build_payload()` 的序列化结果与落盘内容逐字节相同。"""
        gen = _load_generator()
        assert gen.dump(gen.build_payload()) == gen.OUT_PATH.read_text(encoding="utf-8")

    def test_reverse_check_mutated_manifest_is_detected(self, monkeypatch, tmp_path):
        """🔴 反向自检：手改一处段区间必被 `--check` 抓出。

        没有这条，`--check` 恒返回 0 也看不出来（断言空转）。
        """
        gen = _load_generator()
        payload = json.loads(gen.OUT_PATH.read_text(encoding="utf-8"))
        payload["tables"][0]["segments"][0]["end"] += 1
        mutated = tmp_path / "note_shared_table_segments.json"
        mutated.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        monkeypatch.setattr(gen, "OUT_PATH", mutated)
        monkeypatch.setattr(sys, "argv", ["gen_note_shared_table_segments.py", "--check"])
        assert gen.main() == 1, "改了段区间却没被 --check 抓出 → 守卫空转"

    def test_reverse_check_missing_manifest_is_detected(self, monkeypatch, tmp_path):
        gen = _load_generator()
        monkeypatch.setattr(gen, "OUT_PATH", tmp_path / "does-not-exist.json")
        monkeypatch.setattr(sys, "argv", ["gen_note_shared_table_segments.py", "--check"])
        assert gen.main() == 1

    def test_manifest_covers_e1_fx_table(self):
        """E1 外币章节两版都必须在清单里（本 spec 的首个消费者）。"""
        gen = _load_generator()
        payload = json.loads(gen.OUT_PATH.read_text(encoding="utf-8"))
        keys = {(t["variant"], t["section_number"], t["table_name"]) for t in payload["tables"]}
        assert FX_SOE in keys
        assert FX_LISTED in keys
