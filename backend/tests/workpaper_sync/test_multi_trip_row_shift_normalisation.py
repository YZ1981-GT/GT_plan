"""多趟插行的位移归一化 —— 两处根因判据（D1 整册门 ⑥ verify 的最后两道卡点）。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29 的整册门

═══ 这组判据守什么 ═══

D1 是平台上**第一个**同时满足下面三条的 entry：

  1. 多 binding（12 张受管 sheet / 18 张行表）；
  2. **多张 sheet 上各自有行插入**（13 张表各有自己的 `RowShiftPlan`）；
  3. 同 sheet 双区（D1-4 / D1-8 / D1-16 / D1-7 / D1-13 / D1-15 各 2 张行表）。

🔴 **不能拿 D4 全绿当「平台已支持」的背书**：实测 D4 整册门通过那一轮
`row_shift=None` —— 它根本没插行，从未走过「多 binding + sibling sheet 有行位移」
这条路。所以下面两个缺陷在 D1 之前一直是不可见的。

两处缺陷都属同一族：**「把多趟的累积效果当成单趟处理」**。

──────────────────────────────────────────────────────────────────
缺陷 ①（`excel_workbook_row_change.normalise_propagated_part`）
──────────────────────────────────────────────────────────────────

合并多趟声明后，同一处引用会留下一条链。原实现逐对串行 `str.replace()`，在
「同一 part 上多个引用处于链的不同位置」时**信息会丢**：

    审定表D1-1 的 B12 引用 `D1-4!B23`、B13 引用 `D1-4!B24`
    D1-4 两张行表各插 1 行 ⇒ 产物里成了 B25 / B26
    合并声明：B23→B24、B24→B25（两趟各一条）、B25→B26

    串行逆替换：
      ① B26→B25 ⇒ B13 变 B25，**此刻 B12 与 B13 都是 B25**（无法区分了）
      ② B25→B24 ⇒ 两个一起变 B24
      ③ B24→B23 ⇒ 两个一起变 B23 ⇒ B13 错成 B23（应为 B24）

修法：`net_propagation_pairs` 按 `(locator, 引用形状)` 分组，把每一处引用**自己的**
链合成净映射，再单次同时替换。

──────────────────────────────────────────────────────────────────
缺陷 ②（`excel_row_shift._rewrite_formula_refs` 的 `extend_end_at`）
──────────────────────────────────────────────────────────────────

「合计区间扩张」的还原条件原先拿 **remap 之后**的末行比较。正向
（`remap=plan.shift`）巧合正确 —— `shift` 对 `< insert_at` 的行是恒等映射；
逆向（`remap=plan.unshift`）就不然：`unshift` 会把末行往回挪，于是
「本来只是被普通位移带走的区间」也可能在 remap 后恰好等于 `extend_end_at`
⇒ 误判成扩张、又多减一次。

    D1-11 关联方检查表（insert_at=13 count=1）：
      before footer `SUM(C11:C13)`
      after  footer `SUM(C11:C14)`   ← R13 落在区间内，这是**纯位移**不是扩张
      旧逆向归一化：unshift(14)=13 恰等于 13-1+1=13 ⇒ 再减 1 ⇒ `SUM(C11:C12)` ✗

修法：判据与算术都用 **remap 前**的末行。
"""

from __future__ import annotations

import pytest

from app.services.workpaper_sync import excel_workbook_row_change as N1
from app.services.workpaper_sync.excel_row_shift import (
    RowShiftPlan,
    unextend_total_formula,
)

SHEET_PART = "xl/worksheets/sheet3.xml"


# ═══════════════════════════════════════════════════════════════════
# 缺陷 ②：合计区间扩张的还原条件必须看 remap 前的末行
# ═══════════════════════════════════════════════════════════════════


class TestTotalFormulaUnextendUsesSourceRow:
    """`unextend_total_formula` 的扩张判据必须基于**输入侧**末行。

    🔴 两个用例是一对**互相甄别**的样本，必须同时存在：
       * `d1_11` 是纯位移，**不得**再减一次（旧实现在这里错）；
       * `k11` 是真扩张，**必须**减回去（新实现不得把它一起放过）。
       只留前者会让「干脆不还原扩张」也通过；只留后者就是旧实现的原状。
    """

    def test_plain_shift_inside_range_is_not_treated_as_extension(self) -> None:
        """D1-11 实测形态：插入点落在区间**内部** ⇒ 纯位移，还原只能 unshift 一次。"""
        plan = RowShiftPlan(
            insert_at=13, count=1, style_from=12, table_key="related_party_rows"
        )
        # after 侧（materialize 产物）里的 footer 公式
        assert unextend_total_formula("SUM(C11:C14)", plan=plan) == "SUM(C11:C13)"
        assert unextend_total_formula("SUM(K11:K14)", plan=plan) == "SUM(K11:K13)"

    def test_real_extension_at_region_tail_is_still_unextended(self) -> None:
        """K11 原始形态：区间末行恰在插入点**之前** ⇒ 真扩张，必须减回 count。

        `insert_at=26 count=2` ⇒ `extend_end_at = 26 - 1 + 2 = 27`。
        after 侧末行 27 == 27 ⇒ 命中 ⇒ 还原成 `27 - 2 = 25`。
        """
        plan = RowShiftPlan(
            insert_at=26, count=2, style_from=25, table_key="k11_rows"
        )
        assert unextend_total_formula("SUM(B7:B27)", plan=plan) == "SUM(B7:B25)"

    def test_the_two_cases_are_genuinely_discriminated(self) -> None:
        """反向钉死：两个用例的 after 末行与 `extend_end_at` 的关系**相反**。

        没有这条，上面两条可能在「两侧都恰好相等」的退化情形下同时为真，
        那样它们就不再互相甄别了。
        """
        d1_11 = RowShiftPlan(insert_at=13, count=1, style_from=12, table_key="t")
        k11 = RowShiftPlan(insert_at=26, count=2, style_from=25, table_key="t")
        # extend_end_at = insert_at - 1 + count
        assert d1_11.insert_at - 1 + d1_11.count == 13
        assert k11.insert_at - 1 + k11.count == 27
        # D1-11 的 after 末行 14 ≠ 13（不命中）；K11 的 after 末行 27 == 27（命中）
        assert 14 != d1_11.insert_at - 1 + d1_11.count
        assert 27 == k11.insert_at - 1 + k11.count
        # 🔴 而 remap **之后** D1-11 恰好会命中 —— 这正是旧实现出错的机理
        assert d1_11.unshift(14) == d1_11.insert_at - 1 + d1_11.count

    def test_range_entirely_below_insert_point_is_untouched(self) -> None:
        """边界：区间完全在插入点之上 ⇒ 既不位移也不扩张。"""
        plan = RowShiftPlan(insert_at=13, count=1, style_from=12, table_key="t")
        assert unextend_total_formula("SUM(C5:C9)", plan=plan) == "SUM(C5:C9)"


# ═══════════════════════════════════════════════════════════════════
# 缺陷 ①：多趟链必须按「每处引用自己的链」合成净映射
# ═══════════════════════════════════════════════════════════════════


def _entry(locator: str, before: str, after: str, *, part: str = SHEET_PART):
    """造一条 PropagationEntry（`row_before/row_after` 从文本末段数字取）。"""
    import re

    rb = int(re.findall(r"\d+", before)[-1])
    ra = int(re.findall(r"\d+", after)[-1])
    return N1.PropagationEntry(
        carrier="formula",
        part=part,
        locator=locator,
        ref_before=before,
        ref_after=after,
        row_before=rb,
        row_after=ra,
    )


def _plan(*entries):
    return N1.MaterializeWorkbookChangeSet(propagations=tuple(entries))


#: D1 真栈实测形态：两处引用各被两趟位移一次，链互相交叠。
_D1_CHAIN = _plan(
    _entry("B12#0", "'坏账准备明细表D1-4'!B23", "'坏账准备明细表D1-4'!B24"),
    _entry("B12#0", "'坏账准备明细表D1-4'!B24", "'坏账准备明细表D1-4'!B25"),
    _entry("B13#0", "'坏账准备明细表D1-4'!B24", "'坏账准备明细表D1-4'!B25"),
    _entry("B13#0", "'坏账准备明细表D1-4'!B25", "'坏账准备明细表D1-4'!B26"),
)


class TestNetPropagationPairs:
    def test_each_reference_gets_its_own_chain(self) -> None:
        """两处引用各自成链，净映射互不干扰。"""
        pairs = N1.net_propagation_pairs(_D1_CHAIN, part=SHEET_PART)
        assert pairs == {
            ("'坏账准备明细表D1-4'!B25", "'坏账准备明细表D1-4'!B23"): 1,
            ("'坏账准备明细表D1-4'!B26", "'坏账准备明细表D1-4'!B24"): 1,
        }

    def test_single_trip_is_identity(self) -> None:
        """单趟时每个 locator 一步 ⇒ 净映射 == 原条目（与本函数引入前等价）。"""
        plan = _plan(
            _entry("B12#0", "'S'!B23", "'S'!B24"),
            _entry("B13#0", "'S'!B24", "'S'!B25"),
        )
        pairs = N1.net_propagation_pairs(plan, part=SHEET_PART)
        assert pairs == {("'S'!B24", "'S'!B23"): 1, ("'S'!B25", "'S'!B24"): 1}

    def test_shape_dimension_separates_same_locator_different_sheets(self) -> None:
        """🔴 `locator` 单独不够：defined name 的 locator 对所有 sheet 是同一个。

        实测 `_xlnm.Print_Area#0` 一个 locator 底下有 13 条，分属多张 sheet 的打印区。
        只按 locator 分组会把它们错并成一条链（串不起来 ⇒ fail-closed 打红）。
        """
        wb = "xl/workbook.xml"
        plan = _plan(
            _entry("_xlnm.Print_Area#0", "'D1-3'!$A$1:$O$27", "'D1-3'!$A$1:$O$28", part=wb),
            _entry("_xlnm.Print_Area#0", "'D1-4'!$A$1:$N$30", "'D1-4'!$A$1:$N$31", part=wb),
            _entry("_xlnm.Print_Area#0", "'D1-4'!$A$1:$N$31", "'D1-4'!$A$1:$N$32", part=wb),
        )
        pairs = N1.net_propagation_pairs(plan, part=wb)
        # D1-3 一步；D1-4 两步合成一条
        assert pairs == {
            ("'D1-3'!$A$1:$O$28", "'D1-3'!$A$1:$O$27"): 1,
            ("'D1-4'!$A$1:$N$32", "'D1-4'!$A$1:$N$30"): 1,
        }

    def test_locator_dimension_separates_same_shape_different_cells(self) -> None:
        """🔴 「形状」单独不够：B12 与 B13 都引用 `D1-4!B{行}`，形状完全相同。

        只按形状分组会把两处独立引用并成一条 4 步链 ⇒ 净映射错成 B23⇒B26。
        """
        pairs = N1.net_propagation_pairs(_D1_CHAIN, part=SHEET_PART)
        # 两个净映射各覆盖 1 处，而不是一条 B23⇒B26
        assert len(pairs) == 2
        assert ("'坏账准备明细表D1-4'!B26", "'坏账准备明细表D1-4'!B23") not in pairs

    def test_broken_chain_fails_closed(self) -> None:
        """同一 locator+形状 内串不成单链 ⇒ 抛而不是挑一条用。"""
        plan = _plan(
            _entry("B12#0", "'S'!B23", "'S'!B24"),
            _entry("B12#0", "'S'!B30", "'S'!B31"),  # 与上一条不相接
        )
        with pytest.raises(N1.PropagationDriftError, match="串不成单链"):
            N1.net_propagation_pairs(plan, part=SHEET_PART)

    def test_chain_head_ambiguity_is_what_broken_chain_means(self) -> None:
        """把上一条的失败机理钉住：断链的表现是**链头候选不唯一**。

        没有这条，`match="串不成单链"` 可能在别的原因（比如成环）下也通过，
        那样上一条就不再证明「断链被检出」。
        """
        plan = _plan(
            _entry("B12#0", "'S'!B23", "'S'!B24"),
            _entry("B12#0", "'S'!B30", "'S'!B31"),
        )
        with pytest.raises(N1.PropagationDriftError) as info:
            N1.net_propagation_pairs(plan, part=SHEET_PART)
        assert "链头候选" in str(info.value)

    def test_conflicting_target_fails_closed(self) -> None:
        """同一改前文本被声明位移到两个不同目标 ⇒ 抛。"""
        plan = _plan(
            _entry("B12#0", "'S'!B23", "'S'!B24"),
            _entry("B12#0", "'S'!B23", "'S'!B25"),
        )
        with pytest.raises(N1.PropagationDriftError, match="不自洽"):
            N1.net_propagation_pairs(plan, part=SHEET_PART)

    def test_other_parts_are_ignored(self) -> None:
        """只取本 part 的条目（空分母时返回空 dict，不抛）。"""
        assert N1.net_propagation_pairs(_D1_CHAIN, part="xl/workbook.xml") == {}


class TestNormaliseUsesNetMapping:
    def test_two_cells_at_different_chain_positions_normalise_correctly(self) -> None:
        """🔴 本组最核心的一条：串行实现在这里会把第二处错成第一处的值。"""
        after = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B25</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B26</f></c>'
        )
        before = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B23</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B24</f></c>'
        )
        normalised, reverted = N1.normalise_propagated_part(
            after, _D1_CHAIN, part=SHEET_PART
        )
        assert normalised == before
        assert reverted == 2  # 两处引用各逆替换一次

    def test_declared_exactly_passes_on_the_real_shape(self) -> None:
        """端到端：`assert_propagation_declared_exactly` 不再把它判成漂移。"""
        after = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B25</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B26</f></c>'
        )
        before = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B23</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B24</f></c>'
        )
        N1.assert_propagation_declared_exactly(
            before, after, _D1_CHAIN, part=SHEET_PART
        )

    def test_result_is_independent_of_declaration_order(self) -> None:
        """🔴 单次扫描的**决定性**判据：结果不得依赖声明顺序。

        本用例是**单趟**形态 —— 三处独立引用，每处只被位移一次，但它们的
        「改前/改后」文本首尾相接：

            B12 引用 B23 → B24 ·  B13 引用 B24 → B25 ·  B14 引用 B25 → B26

        净映射就是这三条本身（没有链可合成），所以 `net_propagation_pairs`
        救不了它 —— 能救它的只有「替换产物不参与匹配」。

        串行 `str.replace()` 在**逆序**处理时必然串台：
            ① `B26→B25` ⇒ B14 变 B25，此刻 B13 与 B14 都是 B25
            ② `B25→B24` ⇒ 两个一起变 B24（连 B12 那处一起三个都成 B24）
            ③ `B24→B23` ⇒ 全变 B23
        而顺序处理时又恰好正确 —— 所以**只测一种顺序会漏掉这个缺陷**
        （实测：按声明顺序做串行替换时本组其余 15 条判据全绿）。

        这里刻意把声明**按行号降序**排列，让串行实现无论稳定排序如何都会走进
        上面那条错误路径。
        """
        plan = _plan(
            _entry("B14#0", "'S'!B25", "'S'!B26"),
            _entry("B13#0", "'S'!B24", "'S'!B25"),
            _entry("B12#0", "'S'!B23", "'S'!B24"),
        )
        after = (
            '<c r="B12"><f>\'S\'!B24</f></c>'
            '<c r="B13"><f>\'S\'!B25</f></c>'
            '<c r="B14"><f>\'S\'!B26</f></c>'
        )
        before = (
            '<c r="B12"><f>\'S\'!B23</f></c>'
            '<c r="B13"><f>\'S\'!B24</f></c>'
            '<c r="B14"><f>\'S\'!B25</f></c>'
        )
        normalised, reverted = N1.normalise_propagated_part(
            after, plan, part=SHEET_PART
        )
        assert normalised == before, (
            "逆归一化结果依赖声明顺序 —— 替换产物被后续替换重新匹配了"
        )
        assert reverted == 3
        # 同一组声明换成升序排列必须给出**同一个**结果（顺序无关性的正面断言）
        plan_asc = _plan(
            _entry("B12#0", "'S'!B23", "'S'!B24"),
            _entry("B13#0", "'S'!B24", "'S'!B25"),
            _entry("B14#0", "'S'!B25", "'S'!B26"),
        )
        assert N1.normalise_propagated_part(after, plan_asc, part=SHEET_PART) == (
            before,
            3,
        )

    def test_undeclared_change_still_detected(self) -> None:
        """失效反向检查：净映射化**不得**放过未声明的改动。"""
        after = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B25</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B26</f></c>'
            '<c r="Z99"><v>偷偷加的</v></c>'  # 未声明
        )
        before = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B23</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B24</f></c>'
        )
        with pytest.raises(N1.PropagationDriftError, match="未声明"):
            N1.assert_propagation_declared_exactly(
                before, after, _D1_CHAIN, part=SHEET_PART
            )

    def test_missing_declared_change_still_detected(self) -> None:
        """失效反向检查：声明了但产物里没做 ⇒ 仍判漂移。"""
        after = '<c r="B12"><f>\'坏账准备明细表D1-4\'!B25</f></c>'  # 缺 B13 那处
        before = (
            '<c r="B12"><f>\'坏账准备明细表D1-4\'!B23</f></c>'
            '<c r="B13"><f>\'坏账准备明细表D1-4\'!B24</f></c>'
        )
        with pytest.raises(N1.PropagationDriftError):
            N1.assert_propagation_declared_exactly(
                before, after, _D1_CHAIN, part=SHEET_PART
            )
