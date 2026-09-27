# -*- coding: utf-8 -*-
"""G 九条两条红判据：G1R-P9 布尔校验列容错 · G1R-P12 G8 行级 mask 拆区且不误标。

spec: `g-cycle-single-region-detail-lanes` · Task 4 · Requirements 3.2 / 3.5

🔴 **本 Task 实测推翻 design 裁决 G1R-H4 的第②条判据**（详见 evidence/task3-task6-red-baselines.md）：
裁决写「判据须三条：①extract 不抛 ②异常类型为 `type_normalization_failure` ③store 无 TRUE/FALSE」。
按值实测 `merge.normalize_value`：

    normalize_value(True,  ValueType.boolean) → True     ← 成功，**不产生任何 anomaly**
    normalize_value(True,  ValueType.amount ) → RAISE ValueNormalizationError
    normalize_value('TRUE', ValueType.boolean) → RAISE   ← 大写字符串**不被**接受

⇒ 第②条描述的是**声明错误时**的症状（布尔列被声明成 amount/number），不是正确状态。
正确声明（`value_type=boolean` + `mode=formula`）下 `type_normalization_failure` 应为 **0 条**。
⇒ 本文件把第②条改写为「正确声明下零 anomaly + **变异成 amount 时每行一条**」的双向判据。

平台旁证（BP-22，`excel_materialize.py:1583-1587` 逐字）：`boolean` 必须先于数值族判定并落
OOXML 真布尔格 `t="b"`；归到 `number_literal` 时 extract 读回 int ⇒ `normalize_value` 拒绝折叠 0/1
⇒ **每行一条 `type_normalization_failure`**（D2 实测 13/13 行全中，首版发布卡在 roundtrip_verified）。
⇒ 本 spec 四处布尔列若声明成数值族，会原样重演 D2 那次失败。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DB_DISABLE_SSL", "True")

# 🔴 期望表只有一份（Task 3 的文件）—— 抄第二份必漂移。
from test_g_single_region_p1_p3_p5_p6 import (  # noqa: E402
    EXPECTED,
    TPL_G,
    _formula_cols,
    sheets,  # noqa: F401  （pytest fixture 需在本模块命名空间可见）
)

#: 🔴 四处布尔校验列（Task 2 发现 E：spec 说三处，实测 G14 footer L20 也是布尔）。
#:   (code, 列字母, 该列为布尔的行号元组, 公式模板)
BOOLEAN_CHECK_COLUMNS: tuple[tuple[str, str, tuple[int, ...], str], ...] = (
    ("G12", "G", (9,), "=D{r}=SUM(E{r}:F{r})"),          # 🔴 只 R9 一行（发现 H）
    ("G13", "K", tuple(range(11, 21)), "=J{r}=D{r}"),
    ("G13", "K", (21,), "=J{r}=D{r}"),                    # footer 也是布尔
    ("G14", "L", tuple(range(11, 20)), "=D{r}=K{r}"),
    ("G14", "L", (20,), "=D{r}=K{r}"),                    # 🔴 footer 是布尔不是 SUM
)


# ════════════════════════════════════════════════════════════════════════════
# G1R-P9：布尔校验列判 mode=formula + value_type=boolean，容错判据（重写第②条）
#   Validates: Requirements 3.2
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP9BooleanCheckColumns:
    def test_four_boolean_columns_exist_with_exact_formulas(self, sheets) -> None:
        """A 类：四处布尔列逐格公式与期望模板逐字相等（含 footer 两处）。"""
        from openpyxl.utils import column_index_from_string

        for code, col, rows, tpl in BOOLEAN_CHECK_COLUMNS:
            ws = sheets[code]
            ci = column_index_from_string(col)
            for r in rows:
                got = ws.cell(row=r, column=ci).value
                assert got == tpl.format(r=r), (
                    f"{code} {col}{r} 实得 {got!r}，期望 {tpl.format(r=r)!r}"
                )

    def test_boolean_columns_are_three_columns_but_five_declaration_units(self, sheets) -> None:
        """🔴 发现 E：布尔校验列是**三列**（G12!G / G13!K / G14!L），但**五个声明单元**
        —— spec 只数了数据区的三处，漏了 G13!K21 与 G14!L20 两个 footer 位点。

        判据从模板现算：扫九条主表全区 + footer，找形如 `=X{r}=Y{r}` / `=X{r}=SUM(...)` 的比较式。
        """
        import re

        sites: set[tuple[str, str]] = set()
        cmp_rx = re.compile(r"^=[A-Z]+\d+=(?:[A-Z]+\d+|SUM\()")
        for code, spec in EXPECTED.items():
            ws = sheets[code]
            rows = [r for _n, rs, _c in spec["row_segments"] for r in rs]
            rows += list(spec["footer_rows"])
            for r in rows:
                for c in range(1, ws.max_column + 1):
                    v = ws.cell(row=r, column=c).value
                    if isinstance(v, str) and cmp_rx.match(v):
                        from openpyxl.utils import get_column_letter

                        sites.add((code, get_column_letter(c)))
        assert sites == {("G12", "G"), ("G13", "K"), ("G14", "L")}, (
            f"布尔校验列的 (entry, 列) 实得 {sorted(sites)}"
        )
        # 逐位点计数：三列 ×（数据区 + footer）= 五个声明单元（BOOLEAN_CHECK_COLUMNS）
        assert len(BOOLEAN_CHECK_COLUMNS) == 5
        footer_sites = {
            (c, col) for c, col, rows, _t in BOOLEAN_CHECK_COLUMNS
            if set(rows) & set(EXPECTED[c]["footer_rows"])
        }
        assert footer_sites == {("G13", "K"), ("G14", "L")}, (
            f"footer 行带布尔的实得 {sorted(footer_sites)} —— spec 只提了数据区"
        )

    def test_normalize_value_accepts_real_bool_only_under_boolean_type(self) -> None:
        """🔴 重写后的第②条（正向）：`value_type=boolean` 下真 bool 规范化**成功**。

        ⇒ 正确声明时 `type_normalization_failure` 应为 0 条，而不是「异常类型为它」。
        """
        from app.services.workpaper_sync.contracts import ValueType
        from app.services.workpaper_sync.merge import normalize_value

        assert normalize_value(True, ValueType.boolean) is True
        assert normalize_value(False, ValueType.boolean) is False
        # 0/1 也被接受（BP-22 说的「拒绝折叠」是在**数值族**上，不是 boolean 族）
        assert normalize_value(1, ValueType.boolean) is True
        assert normalize_value(0, ValueType.boolean) is False

    def test_uppercase_string_true_is_rejected_even_under_boolean_type(self) -> None:
        """🔴 实测边界：`'TRUE'` / `'FALSE'`（Excel 显示形态的大写串）在 boolean 下**被拒**。

        这条必须登记：若某册的缓存值是大写字符串而不是真 bool，即使声明 boolean 也会产生
        `type_normalization_failure`。四处布尔列的模板值形态见 `test_..._cached_value_shape`。
        """
        from app.services.workpaper_sync.contracts import ValueType
        from app.services.workpaper_sync.merge import ValueNormalizationError, normalize_value

        for raw in ("TRUE", "FALSE"):
            with pytest.raises(ValueNormalizationError):
                normalize_value(raw, ValueType.boolean)
        # 小写串是被接受的（措辞精确：不是「字符串全被拒」）
        assert normalize_value("true", ValueType.boolean) is True
        assert normalize_value("false", ValueType.boolean) is False

    def test_mutation_declaring_boolean_column_as_amount_raises_every_row(self) -> None:
        """🔴 变异自检（重写后的第②条，反向）：把布尔列声明成 `amount` ⇒ **每行**一次规范化失败。

        这正是 D2 的 BP-22 形态（13/13 行全中）。断言「变异确实打中每一行」，不是「还能过吗」。
        """
        from app.services.workpaper_sync.contracts import ValueType
        from app.services.workpaper_sync.merge import ValueNormalizationError, normalize_value

        total_rows = sum(len(rows) for _c, _col, rows, _t in BOOLEAN_CHECK_COLUMNS)
        assert total_rows == 1 + 10 + 1 + 9 + 1 == 22
        failures = 0
        for _code, _col, rows, _tpl in BOOLEAN_CHECK_COLUMNS:
            for _r in rows:
                for bad_type in (ValueType.amount, ValueType.integer, ValueType.rate):
                    try:
                        normalize_value(True, bad_type)
                    except ValueNormalizationError:
                        failures += 1
                        break
        assert failures == total_rows, (
            f"变异体必须让全部 {total_rows} 行都失败，实得 {failures} ⇒ 判据空转"
        )

    def test_formula_mode_is_protected_so_boolean_never_enters_store(self) -> None:
        """重写后的第③条：`mode=formula` ∈ `PROTECTED_MODES` ⇒ 该字段不合并进 store。

        🔴 变异自检：标 `editable` ⇒ 不受保护 ⇒ 布尔值会进 store。
        """
        from app.services.workpaper_sync.contracts import PROTECTED_MODES, FieldMode

        assert FieldMode.formula in PROTECTED_MODES
        assert FieldMode.auto_source in PROTECTED_MODES
        assert FieldMode.editable not in PROTECTED_MODES, (
            "变异「把布尔列标 editable」之所以危险，正是因为 editable 不在 PROTECTED_MODES 里"
        )

    @pytest.mark.parametrize("code,col", [("G12", "G"), ("G13", "K"), ("G14", "L")])
    def test_boolean_column_is_in_that_entrys_formula_columns(self, code: str, col: str) -> None:
        """A 类：三处布尔列都已在 `EXPECTED` 的对应段 `formula_columns` 里（⇒ 会被判 formula）。"""
        segs = EXPECTED[code]["row_segments"]
        in_any = {c for _n, _r, cols in segs for c in cols}
        assert col in in_any, f"{code} 的布尔列 {col} 不在任何段的公式列里 ⇒ 会被误判 editable"
        # G12 的 G 只在 r9 段（行级 mask），不得出现在 r10plus 段
        if code == "G12":
            by_seg = {n: cols for n, _r, cols in segs}
            assert "G" in by_seg["r9"] and "G" not in by_seg["r10plus"], (
                "G12 的布尔列只在 R9 一行 ⇒ r10plus 段不得含 G（否则 R10 的手填格被锁）"
            )


# ════════════════════════════════════════════════════════════════════════════
# G1R-P12：G8-2 行级 mask 拆区且不误标
#   Validates: Requirements 3.5
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP12G8RowLevelMask:
    def test_g8_is_three_segments_not_two(self) -> None:
        """🔴 发现 B：spec 裁决 G1R-H3 默认拆两段（`r11` + `r12plus`=R12-20），实测**三段**。

        R12 与 R13-20 在三处不同（`R`/`T` 列归属 · `M` 区间 · `P` 公式）⇒ 不能同段。
        """
        segs = EXPECTED["G8"]["row_segments"]
        assert [n for n, _r, _c in segs] == ["r11", "r12", "r13plus"], (
            f"G8 分段实得 {[n for n, _r, _c in segs]}"
        )
        by = {n: (rows, cols) for n, rows, cols in segs}
        assert by["r11"][0] == (11,)
        assert by["r12"][0] == (12,)
        assert by["r13plus"][0] == tuple(range(13, 21))

    def test_g8_three_segments_column_sets_are_pairwise_distinct(self, sheets) -> None:
        """A 类：三段列集两两不等，且与模板逐行实测一致（R13~R20 八行同型是三段论的关键）。"""
        ws = sheets["G8"]
        by = {n: (rows, cols) for n, rows, cols in EXPECTED["G8"]["row_segments"]}
        assert set(by["r11"][1]) != set(by["r12"][1])
        assert set(by["r12"][1]) != set(by["r13plus"][1])
        assert set(by["r11"][1]) != set(by["r13plus"][1])
        for name, (rows, cols) in by.items():
            for r in rows:
                assert _formula_cols(ws, r) == cols, (
                    f"G8 段 {name} 的 R{r} 公式列实得 {_formula_cols(ws, r)}，期望 {cols}"
                )

    def test_g8_r_and_t_column_ownership_is_row_specific(self, sheets) -> None:
        """A 类：`R` 列属 R11/R12（不属 R13+）· `T` 列属 R11/R13+（不属 R12）。

        这两条是「不得用并集套全区」的直接理由：并集会把手填格标成 formula 并在 merge 时覆盖。
        """
        ws = sheets["G8"]
        assert ws["R11"].value == "=F11+J11+L11"
        assert ws["R12"].value == "=F12+J12+L12"
        assert ws["R13"].value is None, "R13 的 R 列应无公式（手填）"
        assert ws["T11"].value == "=Q11+S11"
        assert ws["T12"].value is None, "R12 的 T 列应无公式（手填）"
        assert ws["T13"].value == "=Q13+S13"

    def test_g8_m_column_ranges_differ_by_row(self, sheets) -> None:
        """A 类：`M` 列区间逐行不同 —— R11 含 L、R12/R13 不含。"""
        ws = sheets["G8"]
        assert ws["M11"].value == "=SUM(I11:L11)"
        assert ws["M12"].value == "=SUM(I12:K12)"
        assert ws["M13"].value == "=SUM(I13:K13)"

    def test_g8_p_column_has_an_extra_term_only_on_r12(self, sheets) -> None:
        """🔴 spec 未记的第三处差异：`P12` 多一项 `K12`（spec 只记了 M 区间与 R/T）。"""
        ws = sheets["G8"]
        assert ws["P11"].value == "=D11+J11"
        assert ws["P12"].value == "=D12+J12+K12"
        assert ws["P13"].value == "=D13+J13"

    def test_mutation_union_of_all_rows_mislabels_手填格(self, sheets) -> None:
        """🔴 变异自检①（并集）：用三段并集套全区 ⇒ R12 的 T、R13+ 的 R 被误标 formula。"""
        by = {n: set(cols) for n, _r, cols in EXPECTED["G8"]["row_segments"]}
        union = by["r11"] | by["r12"] | by["r13plus"]
        assert union == {"E", "H", "M", "O", "P", "Q", "R", "T"}
        mislabeled_on_r12 = union - by["r12"]
        mislabeled_on_r13 = union - by["r13plus"]
        assert mislabeled_on_r12 == {"T"}, f"并集在 R12 上多标的实得 {sorted(mislabeled_on_r12)}"
        assert mislabeled_on_r13 == {"R"}, f"并集在 R13+ 上多标的实得 {sorted(mislabeled_on_r13)}"

    def test_mutation_intersection_shrinks_the_editable_surface(self) -> None:
        """🔴 变异自检②（交集）：取交集则 R12 的 R、R13+ 的 T 都不受管 ⇒ 可编辑面缩小。

        两个变异一起证明：**只有三段拆分**能既不误标也不缩面（裁决 G1R-H3 的备选分支）。
        """
        by = {n: set(cols) for n, _r, cols in EXPECTED["G8"]["row_segments"]}
        inter = by["r11"] & by["r12"] & by["r13plus"]
        assert inter == {"E", "H", "M", "O", "P", "Q"}
        assert by["r12"] - inter == {"R"}
        assert by["r13plus"] - inter == {"T"}

    def test_mutation_using_r11_columns_for_the_whole_region_breaks_m_range(self, sheets) -> None:
        """🔴 变异自检③（spec 原文指定的那个变异）：用 R11 列集套全区 ⇒ R12 的 `M` 区间被误声明。

        R11 的 M 含 L 列，若把 R11 的 mask 套到 R12，R12 的 `SUM(I12:K12)` 会被按 `SUM(I12:L12)`
        归一 ⇒ 多加一列。本判据断言两式**确实不同**（即变异确实有害）。
        """
        ws = sheets["G8"]
        assert ws["M11"].value != ws["M12"].value.replace("12", "11"), (
            "R11 与 R12 的 M 公式在行号归一后必须仍不同（区间宽度差一列）"
        )
        assert "L11" in str(ws["M11"].value) and "L12" not in str(ws["M12"].value)


# ════════════════════════════════════════════════════════════════════════════
# B 类：G8 三段 / 四处布尔列的 provider 声明 —— 本 Task 必红
# ════════════════════════════════════════════════════════════════════════════
class TestBClassG8AndBooleanDeclarationsNotYetDelivered:
    def test_g8_row_level_formula_mask_is_expressed_without_faking_sections(self) -> None:
        """G8 的行级公式差异必须被表达出来，且**不得**靠伪造分段来表达。

        🔴 **本判据在 Task 9b 实测后改写**（原文：「须导出三个 `RowTableSheetSpec`，
        sheet_key 为 `g802-r11`/`g802-r12`/`g802-r13plus`」）。改写依据，两条都是实测：

        ① **三段在引擎里表达不出来**：`RowTableSheetSpec` 的分段能力只有
           `row_section_field`（按**行对象的字段值**过滤，见 `phase5_row_table_sheet`
           的 `iter_store_rows`）。G8 是**连续** R11-R20 里逐行公式不同，前端 store 是
           一个顺序数组、没有也不该有区归属字段 —— 行的物理位置不是业务属性，把它写进
           持久化数据就是 BP-11「语义耦合行身份」的同族问题（插行即错）。
           引擎不支持按数组下标切段，硬造三段只会让区②③恒空。
        ② **真正需要挡住的是误标**：模板 R13-R20 的 `R`、R12 的 `T` **整格无公式**，
           而 `excel_materialize` 写受保护格时要求 `view.has_formula` —— 判
           `mode=formula` 会抛 `ProtectedRegionWriteError`。这正是 P12 的硬根据。

        ⇒ 正确形态 = **单 spec** + 逐行实测台账（`TEMPLATE_ROW_FORMULAS_G802` /
        `TEMPLATE_ROW_DEFECTS_G802`）+ `R`/`T` 判 `editable`。
        逐格复核在 `test_g8_column_isomorphism.py`（含 P12 专条）。
        """
        import importlib

        try:
            detail = importlib.import_module(
                "app.services.workpaper_sync.phase5_g8_02_detail"
            )
        except ModuleNotFoundError:
            pytest.fail("G8 provider 未交付（Task 9b 转绿）")

        specs = [
            s
            for s in vars(detail).values()
            if getattr(s, "__class__", None).__name__ == "RowTableSheetSpec"
        ]
        assert len(specs) == 1, f"G8 应是单 spec（见 docstring 依据），实得 {len(specs)} 条"
        spec = specs[0]
        assert spec.sheet_key == "g802-managed"
        # ① 不得靠伪造分段表达
        assert not spec.row_section_field, "G8 不得声明 row_section_field（伪造分段）"
        # ② 行级差异必须以逐行台账的形式被表达出来（不是靠注释)
        per_row = detail.TEMPLATE_ROW_FORMULAS_G802
        assert {c for c, _r in per_row} == {"M", "P"}, "逐行台账应恰覆盖 M/P 两列"
        assert len(per_row) == 20, f"M/P × 10 行 = 20 格，实得 {len(per_row)}"
        defects = {c for c, _rows, _note in detail.TEMPLATE_ROW_DEFECTS_G802}
        assert defects == {"M", "P", "R", "T"}, f"缺陷台账应覆盖四列，实得 {sorted(defects)}"
        # ③ P12：R/T 不被误标 formula
        modes = {f[1]: f[2] for f in detail.FIELD_SPECS_G802}
        assert modes["R"] == "editable" and modes["T"] == "editable", (
            "R/T 被误标 formula —— 模板那几格无公式，materialize 会抛 "
            "ProtectedRegionWriteError（判据 P12）"
        )

    @pytest.mark.parametrize("code,col", [("G12", "G"), ("G13", "K"), ("G14", "L")])
    def test_boolean_column_declared_as_formula_and_boolean_type(self, code: str, col: str) -> None:
        """🔴 红：三处布尔列在 provider 的 `field_specs` 里须是 `mode=formula` + `value_type=boolean`。"""
        import importlib

        mod_name = {
            "G12": "phase5_g12_net_hedge_gains",
            "G13": "phase5_g13_fair_value_changes",
            "G14": "phase5_g14_credit_impairment",
        }[code]
        try:
            mod = importlib.import_module(f"app.services.workpaper_sync.{mod_name}")
        except ModuleNotFoundError:
            pytest.fail(f"{code} provider 未交付（Task 10/12/13 转绿）")
        found = []
        for spec in vars(mod).values():
            if getattr(spec.__class__, "__name__", "") != "RowTableSheetSpec":
                continue
            for fs in getattr(spec, "field_specs", ()):
                # 7 元组 (column_key, column, mode, value_type, json_key, header_text, group_cell)
                if len(fs) >= 4 and fs[1] == col:
                    found.append((fs[2], fs[3]))
        assert found, f"{code} 的 field_specs 里找不到列 {col}"
        for mode, vtype in found:
            assert mode == "formula", f"{code}!{col} 的 mode 实得 {mode!r} —— 布尔列不得 editable"
            assert vtype == "boolean", (
                f"{code}!{col} 的 value_type 实得 {vtype!r} —— 数值族会重演 D2 的 BP-22"
            )
