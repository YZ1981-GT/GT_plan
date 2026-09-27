# -*- coding: utf-8 -*-
"""G 两条**实测型**红判据：G1R-P10 G11 占比列绝对引用位移 · G1R-P11 G12 SUM 起点异常。

spec: `g-cycle-single-region-detail-lanes` · Task 5 · Requirements 3.3 / 3.4

🔴 **本文件的判据一律真跑 `excel_row_shift.shift_sheet_rows`**，不得用静态推断代替
（裁决 G1R-H5 明令：「这是**须实测确认的行为**而不是可假设的」）。
每条判据都把「位移前公式 → 位移后公式」的逐字结果写进断言，读判据即可看到实测事实。

═══ 实测结论（2026-09-27，探针 `scripts/analyze/_g_shift_probe.py`）═══

**P10 / 裁决 G1R-H5 —— 走「位移」分支，G/K 两列受管，不改判 HTML-only**

    G10: IF(F10=0,0,F10/$F$31)  →  IF(F10=0,0,F10/$F$34)      ← 绝对引用**位移了**
    K10: IF(J10=0,0,J10/$J$31)  →  IF(J10=0,0,J10/$J$34)      ← 第二个分母同样位移
    F31: SUM(F10:F30)  → (移到 F34) SUM(F10:F33)              ← 合计行自身位移 + 区间扩张
    J31: SUM(J10:J30)  → (移到 J34) SUM(J10:J33)

**P11 —— 框架层扩张规则是「起点不动 + 末行 = last_data_row」**

    I14: SUM(I7:I13)         → (移到 I17) SUM(I7:I16)     ← 起点 I7（表头组行）**保持不动**
    C14: SUM(C9:C13)         → (移到 C17) SUM(C9:C16)     ← 正常整区间形态
    B14: SUM(B9,B12,B13:B13) → (移到 B17) SUM(B9,B12,B13:B16)
         🔴 **B10/B11 插行后仍然漏加** —— 枚举项不会因插行而补全，缺陷不自愈
"""
from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    RowShiftPlan,
    shift_sheet_rows,
)
from test_g_single_region_p1_p3_p5_p6 import EXPECTED, TPL_G  # noqa: E402

_ALL_COLS_13 = tuple("ABCDEFGHIJKLM")
_ALL_COLS_10 = tuple("ABCDEFGHIJ")


def _sheet_part(zf: zipfile.ZipFile, sheet_name: str) -> str:
    """按 `workbook.xml` + rels 定位该 sheet 的 part 路径（属性顺序两种都容忍）。"""
    wb = zf.read("xl/workbook.xml").decode("utf-8")
    pat_a = rf'<sheet[^>]*name="{re.escape(sheet_name)}"[^>]*r:id="(?P<rid>[^"]+)"'
    pat_b = rf'<sheet[^>]*r:id="(?P<rid>[^"]+)"[^>]*name="{re.escape(sheet_name)}"'
    m = re.search(pat_a, wb) or re.search(pat_b, wb)
    assert m, f"workbook.xml 里找不到 sheet {sheet_name!r}"
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rm = re.search(
        rf'<Relationship[^>]*Id="{re.escape(m.group("rid"))}"[^>]*Target="(?P<t>[^"]+)"', rels
    )
    assert rm, f"rels 里找不到 {m.group('rid')}"
    target = rm.group("t").lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _formula_of(sheet_xml: str, coord: str) -> str | None:
    """取该坐标格的 `<f>` 文本。

    🔴 先切出该格**完整**的 `<c …>…</c>` 再取 `<f>` —— 直接用 `re.S` 跨格匹配会把
    后续格子的公式当成本格的（首版探针实测踩过：`G30` 抓到了 `J30` 的公式）。
    """
    cm = re.search(rf'<c r="{coord}"(?:\s[^>]*)?(?:/>|>(?P<body>.*?)</c>)', sheet_xml, re.S)
    if cm is None or not cm.group("body"):
        return None
    fm = re.search(r"<f[^>]*>(?P<f>.*?)</f>", cm.group("body"), re.S)
    return fm.group("f") if fm else None


def _shift(book: str, sheet: str, plan: RowShiftPlan, cols: tuple[str, ...],
           total_rows: tuple[int, ...]) -> tuple[str, str]:
    """真跑一次插行位移，返回 `(before_xml, after_xml)`。"""
    with zipfile.ZipFile(TPL_G / book) as zf:
        before = zf.read(_sheet_part(zf, sheet)).decode("utf-8")
    after, _report = shift_sheet_rows(
        before, plan, total_formula_rows=total_rows, managed_columns=cols
    )
    return before, after


@pytest.fixture(scope="module")
def g11_shift() -> tuple[str, str, RowShiftPlan]:
    """G11-2：数据区 R10-30 / footer R31 ⇒ 在 R31 前插 3 行（`style_from=30`）。"""
    plan = RowShiftPlan(insert_at=31, count=3, style_from=30, table_key="G11-detail-rows")
    before, after = _shift(
        EXPECTED["G11"]["workbook"], EXPECTED["G11"]["managed_sheet"],
        plan, _ALL_COLS_13, total_rows=(31,),
    )
    return before, after, plan


@pytest.fixture(scope="module")
def g12_shift() -> tuple[str, str, RowShiftPlan]:
    """G12-2：数据区 R9-13 / footer R14 ⇒ 在 R14 前插 3 行（`style_from=13`）。"""
    plan = RowShiftPlan(insert_at=14, count=3, style_from=13, table_key="G12-hedge-detail-rows")
    before, after = _shift(
        EXPECTED["G12"]["workbook"], EXPECTED["G12"]["managed_sheet"],
        plan, _ALL_COLS_10, total_rows=(14,),
    )
    return before, after, plan


# ════════════════════════════════════════════════════════════════════════════
# G1R-P10：G11-2 占比列的绝对引用在插行后**位移**（实测，非假设）
#   Validates: Requirements 3.3
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP10RatioColumnAbsoluteRefShifts:
    def test_before_state_is_the_two_denominator_form(self, g11_shift) -> None:
        """前置：位移**前**两列各引自己的分母（G→$F$31 · K→$J$31）。

        🔴 spec 只说「引合计行 F31」—— K 列实际引 `$J$31`（Task 2 发现 F）。
        """
        before, _after, _plan = g11_shift
        assert _formula_of(before, "G10") == "IF(F10=0,0,F10/$F$31)"
        assert _formula_of(before, "K10") == "IF(J10=0,0,J10/$J$31)"
        assert _formula_of(before, "F31") == "SUM(F10:F30)"
        assert _formula_of(before, "J31") == "SUM(J10:J30)"

    def test_g_column_denominator_shifts_from_f31_to_f34(self, g11_shift) -> None:
        """🔴 **实测结论**：插 3 行后 `$F$31` → `$F$34`（裁决 G1R-H5 的「位移」分支成立）。"""
        _before, after, _plan = g11_shift
        assert _formula_of(after, "G10") == "IF(F10=0,0,F10/$F$34)", (
            f"G10 位移后实得 {_formula_of(after, 'G10')!r} —— 若它仍是 $F$31，"
            "说明绝对引用**不位移**，按裁决 G1R-H5 须把 G/K 两列改判 HTML-only"
        )

    def test_k_column_denominator_shifts_from_j31_to_j34(self, g11_shift) -> None:
        """🔴 第二个分母同样位移 —— 只测 F31 会漏掉 K 列指向错行的情形。"""
        _before, after, _plan = g11_shift
        assert _formula_of(after, "K10") == "IF(J10=0,0,J10/$J$34)"

    def test_total_row_itself_moves_and_its_range_extends(self, g11_shift) -> None:
        """合计行自身移到 R34，且区间末行随插行扩张（`F10:F30` → `F10:F33`）。

        两件事必须同时成立，占比列才真的指向「真实合计行」：
        ① 分母坐标跟着合计行走（R31→R34）② 合计行的 SUM 覆盖新插入的 R31-33。
        """
        _before, after, plan = g11_shift
        assert plan.shift(31) == 34
        assert _formula_of(after, "F34") == "SUM(F10:F33)"
        assert _formula_of(after, "J34") == "SUM(J10:J33)"
        assert _formula_of(after, "D34") == "SUM(D10:D33)"

    def test_total_row_ratio_cells_are_shared_formula_members_not_literal_text(
        self, g11_shift
    ) -> None:
        """🔴 实测纠正：footer 的 G/K 两格是 **shared formula 成员**（`<f t="shared" si="N"/>`
        自闭合、**不带文本**），不是独立公式文本。

        首版判据假设 `G31` 有文本 `IF(F31=0,0,F31/$F$31)` ⇒ 实测 `None`。
        真相：`si="1"` 组的**主格在 G10**，footer 的 G 只是成员 ⇒ 它的公式来自主格文本，
        主格已位移到 `$F$34`（见上一条）⇒ footer 的占比格计算正确。
        ⇒ 判断「占比列是否指向真实合计行」**必须看 shared 组主格**，看成员格会得到 None 而误判。
        """
        before, after, _plan = g11_shift
        # 位移前 G31 就是成员格（自闭合 <f t="shared" si="1"/>）
        cm_before = re.search(r'<c r="G31"(?:\s[^>]*)?>(?P<b>.*?)</c>', before, re.S)
        assert cm_before and 't="shared" si="1"' in cm_before.group("b")
        assert _formula_of(before, "G31") is None
        # 位移后同理落在 G34
        cm_after = re.search(r'<c r="G34"(?:\s[^>]*)?>(?P<b>.*?)</c>', after, re.S)
        assert cm_after and 't="shared" si="1"' in cm_after.group("b")
        assert _formula_of(after, "G34") is None
        # 主格（G10）才带文本，且已位移
        assert _formula_of(after, "G10") == "IF(F10=0,0,F10/$F$34)"

    def test_newly_inserted_rows_keep_the_stale_absolute_denominator(self, g11_shift) -> None:
        """🔴🔴 **框架层真实缺陷（本 Task 新发现，spec 未预见）**：
        新插入行的 fill-down 公式里的绝对引用 `$F$31` **不位移**，仍指向 R31 ——
        而 R31 位移后已经是「第一个新行」自己，不再是合计行。

        逐字实测（`insert_at=31, count=3, style_from=30`）：

            R31: IF(F31=0,0,F31/$F$31)     ← 分母应为 $F$34
            R32: IF(F32=0,0,F32/$F$31)
            R33: IF(F33=0,0,F33/$F$31)
            R34: SUM(F10:F33)              ← 真正的合计行在这里

        根因（按值定位）：`excel_row_shift._build_inserted_row`(L1877) 用
        `translate_formula_rows(...)`(L1054)，后者固定 `freeze_absolute_rows=True`
        —— 那是 Excel 填充柄的正确语义。但造出来的新行公式**随后没有再经过插行位移**
        （`freeze_absolute_rows=False` 那条路）。
        **Excel 自己的顺序是「先插行（$F$31→$F$34）再填充（$F$34 保持）」⇒ 结果是 `$F$34`。**
        框架层的顺序相反，于是新行留下了位移前的绝对坐标。

        本判据**钉住当前行为**（不是期望行为）。缺陷登记见
        `evidence/task3-task6-red-baselines.md` §Task 5；修复归框架层另立项，
        🔴 本 spec **不改** `excel_row_shift.py`（跨循环影响面 + 引擎核心）。
        修好后本判据必红 —— 届时把断言改成 `$F$34` 并在 evidence 记修复 commit。
        """
        _before, after, _plan = g11_shift
        for r in (31, 32, 33):
            assert _formula_of(after, f"G{r}") == f"IF(F{r}=0,0,F{r}/$F$31)", (
                f"新行 G{r} 实得 {_formula_of(after, f'G{r}')!r}"
            )
            assert _formula_of(after, f"K{r}") == f"IF(J{r}=0,0,J{r}/$J$31)"
        # 合计行确实已经不在 R31 了 —— 这就是「指向错行」的证据
        assert _formula_of(after, "F34") == "SUM(F10:F33)"
        assert _formula_of(after, "F31") == "D31+E31", "R31 位移后是新行，不是合计行"

    def test_conclusion_g_and_k_stay_managed_as_formula_columns(self) -> None:
        """🔴 结论落地：位移成立 ⇒ G/K 两列**受管**（留在 `formula_columns` 里）。

        若实测为「不位移」，本判据须改成「G/K 不在 formula_columns 且登记 HTML-only」。
        两者互斥，改一处就必须改另一处 —— 这防止结论与声明脱钩。
        """
        cols = {c for _n, _r, cs in EXPECTED["G11"]["row_segments"] for c in cs}
        assert {"G", "K"} <= cols, "位移分支成立时 G/K 必须受管"
        assert cols == {"F", "G", "J", "K", "L"}

    def test_no_static_inference_the_assertion_came_from_a_real_shift(self, g11_shift) -> None:
        """🔴 反「静态推断」自检：断言位移**确实改变了** XML（不是读了同一份字节）。"""
        before, after, _plan = g11_shift
        assert before != after, "位移未改变 XML ⇒ 本文件的判据全部空转"
        # 🔴 不能断言 `"$F$31" not in after` —— 新插入行仍带 `$F$31`（上一条判据记的缺陷）。
        #    改为按「既有行的主格」取证：主格从 $F$31 变成 $F$34，且 $F$34 是位移后才出现的。
        assert "$F$34" not in before, "位移前不应出现 $F$34"
        assert "$F$34" in after, "位移后既有行的主格必须指向 $F$34"
        assert _formula_of(before, "G10") == "IF(F10=0,0,F10/$F$31)"
        assert _formula_of(after, "G10") == "IF(F10=0,0,F10/$F$34)"
        # 位移后残留的 $F$31 全部且仅在新插入行（31/32/33）上 —— 精确到行，不含既有行
        stale_rows = {
            int(m.group(1))
            for m in re.finditer(r'<c r="[GK](\d+)"[^>]*><f>[^<]*\$[FJ]\$31\)', after)
        }
        assert stale_rows == {31, 32, 33}, (
            f"位移后仍引 $F$31/$J$31 的行实得 {sorted(stale_rows)}；"
            "若出现既有行（<=30），说明既有行的位移也坏了 —— 那是更严重的回归"
        )


# ════════════════════════════════════════════════════════════════════════════
# G1R-P11：G12-2 合计 SUM 起点在数据区之上 —— 插行后的位移行为已实测并登记
#   Validates: Requirements 3.4
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP11SumStartAboveDataRegion:
    def test_before_state_records_the_two_template_defects(self, g12_shift) -> None:
        """前置：位移前逐字记下 G12-2 footer 的两处模板真实缺陷（Task 2 发现 G）。"""
        before, _after, _plan = g12_shift
        # 缺陷①：B 列合计枚举漏加 B10 / B11（**数值错**）
        assert _formula_of(before, "B14") == "SUM(B9,B12,B13:B13)"
        # 缺陷②：I 列合计起点越到 R7（表头组行）
        assert _formula_of(before, "I14") == "SUM(I7:I13)"
        # 对照：C 列是正常的整区间形态
        assert _formula_of(before, "C14") == "SUM(C9:C13)"

    def test_sum_start_stays_put_while_end_row_extends(self, g12_shift) -> None:
        """🔴 **实测结论**：框架层扩张规则是「起点不动 + 末行 = last_data_row」。

        `SUM(I7:I13)` → `SUM(I7:I16)`：起点 `I7` **保持**，末行 13 → 16（吸收新插 3 行）。
        ⇒ 「起点在表头之上」这个未覆盖形态在插行后**不会自愈也不会放大**。
        """
        _before, after, plan = g12_shift
        assert plan.shift(14) == 17
        assert _formula_of(after, "I17") == "SUM(I7:I16)", (
            f"I 列合计位移后实得 {_formula_of(after, 'I17')!r}，期望 SUM(I7:I16)"
        )
        # 对照组：正常形态也是「起点不动 + 末行扩张」⇒ 两者规则一致，不是特例处理
        assert _formula_of(after, "C17") == "SUM(C9:C16)"

    def test_the_off_by_two_rows_start_is_a_header_row_so_numerically_harmless(self, g12_shift) -> None:
        """起点 R7 是**表头组行**（文本格）⇒ SUM 忽略文本 ⇒ 缺陷②数值上无害，只是区间声明错。

        判据从模板取证：R7 的 I 列是字符串且**无公式**（表头），不是数值。
        """
        import openpyxl

        wb = openpyxl.load_workbook(TPL_G / EXPECTED["G12"]["workbook"], data_only=False)
        ws = wb[EXPECTED["G12"]["managed_sheet"]]
        assert EXPECTED["G12"]["header"] == (7, 8)
        i7 = ws["I7"].value
        assert isinstance(i7, str) and not i7.startswith("="), (
            f"G12 I7 实得 {i7!r} —— 若它是数值，缺陷② 就从「声明错」升级为「数值错」"
        )
        wb.close()

    def test_enumerated_sum_defect_is_not_healed_by_row_insertion(self, g12_shift) -> None:
        """🔴 **本 Task 最重要的一条**：`B14` 的漏加缺陷在插行后**依然存在**。

        `SUM(B9,B12,B13:B13)` → `SUM(B9,B12,B13:B16)`：
        末段区间 `B13:B13` 扩张为 `B13:B16`（吸收新行），但**枚举项 B9/B12 不变**
        ⇒ **B10 / B11 仍然不在合计里**。

        ⇒ 用户在 R10（模板预填的第二行数据）或 R11 填 B 列金额，合计**永远**不计入。
        这是真实数值错，且插行**不会**让它自愈 ⇒ 必须走覆盖层修（模板字节只读）。
        """
        _before, after, _plan = g12_shift
        got = _formula_of(after, "B17")
        assert got == "SUM(B9,B12,B13:B16)", f"B 列合计位移后实得 {got!r}"
        # 逐项证明 B10 / B11 不在任何被加总的项里
        assert "B10" not in got and "B11" not in got, (
            f"若 B10/B11 出现在 {got!r} 里，说明框架层已顺带补全枚举项 —— "
            "那本条缺陷登记要改写"
        )
        # 对照：C 列的整区间形态天然覆盖 C10/C11
        assert _formula_of(after, "C17") == "SUM(C9:C16)"

    def test_boolean_column_on_r9_is_untouched_by_a_footer_side_insertion(self, g12_shift) -> None:
        """布尔校验列在 R9（插入点 R14 之前）⇒ 位移不动它。

        这条把 P9（布尔列）与 P11（插行）的交叉面钉住：行级 mask 的那一行不会因插行而漂。
        """
        _before, after, _plan = g12_shift
        assert _formula_of(after, "G9") == "D9=SUM(E9:F9)"
        assert _formula_of(after, "I9") == "E9+H9"
        assert _formula_of(after, "I10") == "E10+H10"

    def test_no_static_inference_for_g12_either(self, g12_shift) -> None:
        """🔴 反「静态推断」自检（同 P10）。"""
        before, after, _plan = g12_shift
        assert before != after
        assert "SUM(I7:I13)" in before and "SUM(I7:I13)" not in after
        assert "SUM(I7:I16)" in after


# ════════════════════════════════════════════════════════════════════════════
# 交叉：两条实测结论必须落到 Task 11 / Task 13 的声明里（现在必红）
# ════════════════════════════════════════════════════════════════════════════
class TestBClassShiftConclusionsNotYetWiredIntoProviders:
    def test_g11_provider_declares_footer_carries_total_formula(self) -> None:
        """🔴 红：G11 的 footer 带合计公式 ⇒ `footer_carries_total_formula=True`（默认值也算）。

        它决定 `_grow_managed_table_ref` 是否把 footer 区间归一化 —— P10 的位移结论要靠它落地。
        """
        import importlib

        try:
            mod = importlib.import_module(
                "app.services.workpaper_sync.phase5_g11_investment_income"
            )
        except ModuleNotFoundError:
            pytest.fail("G11 provider 未交付（Task 11 转绿）")
        specs = [
            s for s in vars(mod).values()
            if getattr(s.__class__, "__name__", "") == "RowTableSheetSpec"
        ]
        assert specs, "G11 provider 未导出 RowTableSheetSpec"
        for s in specs:
            assert s.footer_row == 31
            assert s.footer_carries_total_formula is True

    def test_g12_provider_records_the_template_defects_in_its_docstring(self) -> None:
        """🔴 红：G12 provider 的模块 docstring 须逐字登记两处模板缺陷（覆盖层不改字节）。

        判据查 docstring 里同时出现两个公式字面量 —— 这是「缺陷已登记」的最小可执行证据。
        """
        import importlib

        try:
            mod = importlib.import_module(
                "app.services.workpaper_sync.phase5_g12_net_hedge_gains"
            )
        except ModuleNotFoundError:
            pytest.fail("G12 provider 未交付（Task 13 转绿）")
        doc = (mod.__doc__ or "") + "\n".join(
            getattr(v, "__doc__", "") or "" for v in vars(mod).values()
        )
        assert "SUM(B9,B12,B13:B13)" in doc, "G12 provider 未登记 B 列漏加缺陷"
        assert "SUM(I7:I13)" in doc, "G12 provider 未登记 I 列起点越界缺陷"
