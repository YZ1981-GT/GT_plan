"""A7：删行后 footer 两门在同一次物化内复核（Property 16）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 14.1 · 14.2
Requirements: 7.1~7.5

═══ 为什么这一相必须存在 ═══

两门原来的门是 `if plan.row_shift is None: return None`（函数自己首行 + 调用点各一道）
⇒ **删行后一相都不复核**。A2（runtime binding 重冻结）与 A5（裸引用平移）里任何一处算错，
都要等到**下一次** materialize 才以别的症状冒出来 —— 那时用户看到的是「删行这次成功了、
下次点在线编辑起 500」，归因要跨两次物化。

🔴 上游 `test_excel_row_insertion_wiring` 留下的 M28 教训：只测
`apply_plan_zip_with_report` 的话，`assert_shifted_footer_gates` 的**整个调用点**可以被删掉
而全部用例仍绿。所以本文件同时立三层：
① 直接测两门的行为（正面 + 四条反面）；
② AST 钉死**两处门都放开**（只放一处 = 另一处照旧 return None = 接线了其实空转）；
③ 直接调 `_apply_step_to_bytes` 证明调用点对删行载体真的执行。
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync.excel_row_shift import RowShiftPlan  # noqa: E402

import test_row_deletion_apply_propagation as AP  # noqa: E402

#: D1-8 DISCOUNT 区的 per-template 冻结 footer 键（`GT_TEMPLATE_IDS` 里的 `D18DISCOUNT`）。
FROZEN_KEY = "GT_FOOTER_ROW_D18DISCOUNT"


@pytest.fixture(scope="module")
def gate_ctx(world: dict[str, Any]) -> dict[str, Any]:
    """契约 / binding / region / runtime_binding —— 两门的必需入参。"""
    import io
    import zipfile

    contract = AP.build_contract()
    binding = AP.build_binding()
    with zipfile.ZipFile(io.BytesIO(world["bytes"])) as zf:
        region = X.resolve_managed_region(zf, contract=contract, binding=binding)
        runtime_binding = X.read_runtime_binding_pairs(zf)
    return {
        "contract": contract,
        "binding": binding,
        "region": region,
        "runtime_binding": runtime_binding,
    }


@pytest.fixture(scope="module")
def world() -> dict[str, Any]:
    """复用 A3~A6 的 D1-8 靶子（module 级 fixture 不跨文件共享 ⇒ 这里再建一次）。"""
    import test_sibling_table_ref_row_shift as SIB

    data = SIB._instrumented_bytes_for_provider(AP.PROVIDER)
    entries = AP._entries_of(data)
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheet_part = X._sheet_parts(zf).get(AP.SHEET)
    assert sheet_part, f"定位不到受管 sheet part：{AP.SHEET}"
    return {
        "bytes": data,
        "entries": entries,
        "sheet_part": sheet_part,
        "table_part": M._managed_table_part(entries, table_name=AP.TABLE),
        "sibling_part": M._managed_table_part(entries, table_name=AP.SIBLING_TABLE),
    }


def _product(world: dict[str, Any], deleted: tuple[int, ...]) -> tuple[bytes, Any]:
    plan = AP._plan(world, deleted, total_formula_rows=(AP.FOOTER_ROW,))
    product, _ = M.apply_plan_zip_with_report(world["bytes"], plan)
    return product, plan


def _gate(
    staged: bytes, plan: Any, ctx: dict[str, Any], *, runtime_binding: Any = None
) -> int | None:
    return M.assert_shifted_footer_gates(
        staged_bytes=staged,
        plan=plan,
        contract=ctx["contract"],
        region=ctx["region"],
        runtime_binding=runtime_binding or ctx["runtime_binding"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 前提非退化
# ═══════════════════════════════════════════════════════════════════════════


def test_context_is_non_degenerate(world: dict[str, Any], gate_ctx: dict[str, Any]) -> None:
    """🔴 四条前提：冻结键存在且 == 22 / 契约声明携带合计 / footer 上真有公式格 / 区 14..21。"""
    binding = gate_ctx["runtime_binding"]
    assert FROZEN_KEY in binding, (
        f"{FROZEN_KEY} 不在 runtime binding 里，实测含 D18 的键："
        f"{sorted(k for k in binding if 'D18' in k)}"
    )
    assert binding[FROZEN_KEY].strip() == str(AP.FOOTER_ROW), (
        f"{FROZEN_KEY}={binding[FROZEN_KEY]!r}，而 AP.FOOTER_ROW={AP.FOOTER_ROW}"
    )
    region = gate_ctx["region"]
    assert (region.first_row, region.last_row) == (AP.FIRST_ROW, AP.LAST_ROW)

    anchor = next(
        t.footer_anchor
        for s in gate_ctx["contract"].sheets
        for t in s.tables
        if t.table_key == region.table_key
    )
    assert anchor is not None and anchor.carries_total_formula, (
        "契约没声明 carries_total_formula ⇒ 合计收缩那一支不会被执行，本文件判据空转"
    )
    checked = M.assert_footer_formula_covers_managed_rows(
        entries=world["entries"],
        sheet_part=world["sheet_part"],
        footer_row=AP.FOOTER_ROW,
        region=region,
        carries_total_formula=True,
    )
    assert len(checked) >= 2, f"footer 行 {AP.FOOTER_ROW} 上带公式的格只有 {checked}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 16：footer 两门的算术与零产物
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty16FooterGateArithmetic:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 16: footer 两门的算术与零产物**

    **Validates: Requirements 7.2, 7.3, 7.4**
    """

    @pytest.mark.parametrize(
        "deleted",
        [
            (AP.LAST_ROW,),
            (AP.FIRST_ROW,),
            (AP.FIRST_ROW + 2,),
            (AP.FIRST_ROW, AP.LAST_ROW),
            (AP.FIRST_ROW + 1, AP.FIRST_ROW + 2, AP.FIRST_ROW + 3),
        ],
    )
    def test_anchor_expectation_is_frozen_minus_declared_deletions(
        self, world: dict[str, Any], gate_ctx: dict[str, Any], deleted: tuple[int, ...]
    ) -> None:
        """🔴 预期行号 = 冻结值 − 声明的被删行数（Requirement 7.2）。

        判据用**返回值**断言它真的执行过，而不是「没抛错」（Requirement 7.5）——
        两门在载体为空时 `return None`，只看不抛的话门被整片关掉也是绿的。
        """
        staged, plan = _product(world, deleted)
        observed = _gate(staged, plan, gate_ctx)
        assert observed == AP.FOOTER_ROW - len(deleted), (
            f"删 {list(deleted)} 后 footer 实得 {observed}，"
            f"应为 {AP.FOOTER_ROW} − {len(deleted)}"
        )

    def test_gate_is_not_a_no_op_when_only_a_deletion_carrier_is_present(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 删行计划的 `row_shift` **是** None ⇒ 旧门会在这里 return None。

        这条把「门真的为删行载体放开了」钉死：断言 `row_shift is None` 与
        「返回值非 None」**同时**成立。
        """
        staged, plan = _product(world, (AP.LAST_ROW,))
        assert plan.row_shift is None, "本 spec 的删行计划不该带插行载体"
        assert plan.row_deletion is not None
        assert _gate(staged, plan, gate_ctx) is not None, (
            "只有删行载体时两门返回 None ⇒ 门没放开（A7 未接线）"
        )

    def test_declaring_more_deletions_than_applied_is_caught(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证①：产物只删了 1 行，载体声明删 2 行 ⇒ 抛。

        这正是「位移算错」的形态：声明与实测不符。顺带钉住错误信息按**方向**措辞
        （删行侧写 `-2 行` 与「删 2 行」，不是 `+-2` 与「插」）。
        """
        staged, plan = _product(world, (AP.LAST_ROW,))
        lying = N1.RowDeletionShift(
            deleted_rows=(AP.LAST_ROW - 1, AP.LAST_ROW),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        import dataclasses

        broken = dataclasses.replace(plan, row_deletion=lying, deletion_change=None)
        with pytest.raises(M.FooterAnchorDriftError) as err:
            _gate(staged, broken, gate_ctx)
        text = str(err.value)
        assert "-2 行" in text, f"错误信息没按删行方向措辞：{text}"
        assert "删 2 行" in text, f"错误信息没说清删了几行：{text}"
        assert "插入点" not in text, f"删行侧仍在说「插入点」：{text}"

    def test_tampered_frozen_value_is_caught(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证②：把冻结值改掉 ⇒ 抛（证明比较真的发生，不是恒真）。"""
        staged, plan = _product(world, (AP.LAST_ROW,))
        tampered = dict(gate_ctx["runtime_binding"])
        tampered[FROZEN_KEY] = str(AP.FOOTER_ROW + 1)
        with pytest.raises(M.FooterAnchorDriftError, match="声明之外"):
            _gate(staged, plan, gate_ctx, runtime_binding=tampered)

    def test_skipping_the_bare_ref_shift_makes_the_total_gate_red(
        self,
        world: dict[str, Any],
        gate_ctx: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """🔴 变异反证③（design A5 点名的那一条）：跳过 A5 ⇒ 合计覆盖门必须打红。

        A5 不跑时合计区间仍停在删行**前**的受管末行，而 footer 已经上移到那一行 ⇒
        合计把 footer 自己算了进去。这是 design A5 的「不做会怎样」落到的**具体错值**，
        也是 E.6 里「结构块塌陷改用两侧对称排除」的**补偿控制** —— 补偿控制必须被证明
        真的会打红，否则排除就是白排。
        """
        monkeypatch.setattr(
            M, "_shift_managed_sheet_bare_refs", lambda xml, *, plan: (xml, 0)
        )
        staged, plan = _product(world, (AP.LAST_ROW,))
        with pytest.raises(M.FooterFormulaRangeError, match="没跟着收缩"):
            _gate(staged, plan, gate_ctx)

    def test_superset_total_range_is_not_flagged(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 防假红：合计区间是受管区**超集**的形态真实存在（H1 模板 `SUM(I13:I27)`
        而受管区到 26，已在 `pilot_h1_grouped_dynamic` 里登记），删行后不得判红。

        没有这条，上一条的上界会把一整类合法模板判死。
        """
        region = gate_ctx["region"]
        shift = N1.RowDeletionShift(
            deleted_rows=(AP.LAST_ROW,),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        footer_row = AP.FOOTER_ROW - 1
        # 终点 = 老末行 + 2 ⇒ 超集；新末行 = 20 ⇒ `last >= effective` 成立 ⇒ 通过
        entries = _synthetic_footer(
            world, footer_row=footer_row, formula=f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW + 2})"
        )
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=entries,
            sheet_part=world["sheet_part"],
            footer_row=footer_row,
            region=region,
            row_shift=shift,
            carries_total_formula=True,
        )
        assert checked, "合成 footer 上一个公式格都没读到 ⇒ 本条空转"

    def test_unshrunk_range_is_flagged_on_the_same_synthetic_sheet(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 与上一条**同一份合成 sheet**、只把终点换成老末行 ⇒ 必须打红。

        两条成对才证明上界既不漏（本条）也不误（上一条）。
        """
        shift = N1.RowDeletionShift(
            deleted_rows=(AP.LAST_ROW,),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        footer_row = AP.FOOTER_ROW - 1
        entries = _synthetic_footer(
            world, footer_row=footer_row, formula=f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW})"
        )
        with pytest.raises(M.FooterFormulaRangeError, match="没跟着收缩"):
            M.assert_footer_formula_covers_managed_rows(
                entries=entries,
                sheet_part=world["sheet_part"],
                footer_row=footer_row,
                region=gate_ctx["region"],
                row_shift=shift,
                carries_total_formula=True,
            )

    def test_insert_side_arithmetic_is_unchanged(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 插行侧逐字未变：末行仍是 `region.last_row + count`。

        删行分支是按 `deleted_rows` 分流加上去的；这条证明分流没把插行那一支带歪。
        """
        region = gate_ctx["region"]
        insert = RowShiftPlan(
            insert_at=AP.FIRST_ROW + 1, count=1, style_from=AP.FIRST_ROW
        )
        footer_row = AP.FOOTER_ROW + 1
        # 覆盖到 last_row + 1 ⇒ 通过
        ok = _synthetic_footer(
            world, footer_row=footer_row, formula=f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW + 1})"
        )
        assert M.assert_footer_formula_covers_managed_rows(
            entries=ok,
            sheet_part=world["sheet_part"],
            footer_row=footer_row,
            region=region,
            row_shift=insert,
            carries_total_formula=True,
        )
        # 只覆盖到老末行 ⇒ 仍按「漏算」抛（插行侧既有语义）
        short = _synthetic_footer(
            world, footer_row=footer_row, formula=f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW})"
        )
        with pytest.raises(M.FooterFormulaRangeError, match="合计漏算") as err:
            M.assert_footer_formula_covers_managed_rows(
                entries=short,
                sheet_part=world["sheet_part"],
                footer_row=footer_row,
                region=region,
                row_shift=insert,
                carries_total_formula=True,
            )
        assert "+1 行插入" in str(err.value), str(err.value)

    def test_footer_frozen_row_inside_the_deleted_set_fails_closed(
        self, world: dict[str, Any], gate_ctx: dict[str, Any]
    ) -> None:
        """🔴 防御分支：载体把 footer 冻结行也删了 ⇒ `shift` 返 None。

        `RowDeletionShift` 的构造期约束（被删行 ⊆ 受管区）使这一形态不可达，但两门收的是
        **鸭子协议**不是具体类。没有这个分支时 `observed != None` 恒真 ⇒ 落进下一支后
        `expected - frozen_row` 抛 `TypeError` —— 一个与真实原因毫无关系的错误。
        """

        class _DuckDeletesFooter:
            deleted_rows = (AP.FOOTER_ROW,)
            count = 1
            insert_at = AP.FOOTER_ROW

            def shift(self, row: int) -> int | None:
                return None if row == AP.FOOTER_ROW else row

        staged, plan = _product(world, (AP.LAST_ROW,))
        import dataclasses

        broken = dataclasses.replace(
            plan, row_deletion=_DuckDeletesFooter(), deletion_change=None
        )
        with pytest.raises(M.FooterAnchorDriftError, match="越出了受管区"):
            _gate(staged, broken, gate_ctx)


def _synthetic_footer(
    world: dict[str, Any], *, footer_row: int, formula: str
) -> dict[str, bytes]:
    """把受管 sheet 换成「只有一个 footer 行 + 一个公式格」的最小 XML。

    🔴 合成而不是改真产物：合计区间的**上界**判据要在「超集 / 恰等于老末行」两种取值上
    各跑一次，而真模板只有一种取值。合成让两条判据落在同一份输入上、只差那一个数字。
    """
    entries = dict(world["entries"])
    xml = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f'<row r="{footer_row}"><c r="F{footer_row}"><f>{formula}</f><v>0</v></c></row>'
        "</sheetData></worksheet>"
    )
    entries[world["sheet_part"]] = xml.encode("utf-8")
    return entries


# ═══════════════════════════════════════════════════════════════════════════
# 3. 两处门都必须放开 + 调用点真的在链路上
# ═══════════════════════════════════════════════════════════════════════════


class TestBothGatesAreOpenedForDeletion:
    """**Validates: Requirement 7.1**

    🔴 门有**两道**：`assert_shifted_footer_gates` 自己首行，以及
    `_apply_step_to_bytes` 里的调用点 `if`。只放开一道 = 另一道照旧 `return None`
    = 看起来接线了其实空转。上游 M28 变异（摘掉调用点）实测 **GREEN** 过一次，
    所以这两条判据缺一不可。
    """

    def _condition_names(self, func: Any) -> set[str]:
        src = textwrap.dedent(inspect.getsource(func))
        tree = ast.parse(src)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                for sub in ast.walk(node.test):
                    if isinstance(sub, ast.Attribute):
                        names.add(sub.attr)
                    elif isinstance(sub, ast.Name):
                        names.add(sub.id)
        return names

    def test_gate_function_itself_looks_at_the_deletion_carrier(self) -> None:
        src = textwrap.dedent(inspect.getsource(M.assert_shifted_footer_gates))
        tree = ast.parse(src)
        # 门必须是「两个载体都空才 return」——用 AST 找出函数体里对两个字段的读取
        attrs = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert {"row_shift", "row_deletion"} <= attrs, (
            f"两门函数没同时读两个载体字段：{sorted(attrs)}"
        )

    def test_call_site_condition_mentions_the_deletion_carrier(self) -> None:
        names = self._condition_names(M._apply_step_to_bytes)
        assert "row_deletion" in names, (
            f"`_apply_step_to_bytes` 的 if 条件没提 row_deletion：{sorted(names)} —— "
            "调用点没放开的话，函数内部放开也白搭"
        )
        assert "row_shift" in names, f"插行那一支被删了：{sorted(names)}"

    def test_call_site_actually_runs_for_a_deletion_plan(
        self,
        world: dict[str, Any],
        gate_ctx: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """🔴 M28 教训：只测两门函数不够，必须证明**调用点**对删行载体执行了。

        直接调 `_apply_step_to_bytes`（它就是链路上那一层），用计数器断言门被调过一次。
        """
        import types

        plan = AP._plan(world, (AP.LAST_ROW,), total_formula_rows=(AP.FOOTER_ROW,))
        calls: list[Any] = []
        real = M.assert_shifted_footer_gates

        def _counting(**kwargs: Any) -> Any:
            calls.append(kwargs["plan"])
            return real(**kwargs)

        monkeypatch.setattr(M, "assert_shifted_footer_gates", _counting)
        step = M.MaterializePlanStep(
            binding=gate_ctx["binding"],
            plan=plan,
            strategy=None,
            substrate_view=types.SimpleNamespace(region=gate_ctx["region"]),
            runtime_binding=gate_ctx["runtime_binding"],
        )
        staged, _report = M._apply_step_to_bytes(
            source_bytes=world["bytes"],
            step=step,
            definitions=types.SimpleNamespace(contract=gate_ctx["contract"]),
        )
        assert len(calls) == 1, f"两门在链路上被调了 {len(calls)} 次（应为 1）"
        assert calls[0] is plan
        assert staged and staged != world["bytes"]

    def test_the_counting_judgement_is_not_vacuous(self, world: dict[str, Any]) -> None:
        """🔴 反事实：条件若只看 `row_shift`，删行计划根本进不去 ⇒ 计数会是 0。

        直接在删行计划上求值两个条件，证明上一条判据**能**被变异掉（不是恒真）。
        没有这条，「计数 == 1」可能只是因为条件恒真。
        """
        plan = AP._plan(world, (AP.LAST_ROW,), total_formula_rows=(AP.FOOTER_ROW,))
        insert_only = plan.row_shift is not None
        both = plan.row_shift is not None or plan.row_deletion is not None
        assert not insert_only, "删行计划竟带插行载体 ⇒ 反事实前提不成立"
        assert both, "双载体条件在删行计划上为假 ⇒ 生产条件写错了"
