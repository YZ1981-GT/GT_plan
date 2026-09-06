# -*- coding: utf-8 -*-
"""Task 21 —— `plan_managed_writes` 接工作簿级计划（Requirement 1.1）。

spec: excel-workbook-wide-row-change-propagation / Wave 4 Task 21

═══ 接线的三个关口 ═══

1. **计划期冻结声明** —— `plan_managed_writes` 在返回 `MaterializePlan` 之前扫一次载体，
   把「改哪些位置、改成什么」冻结进 `plan.workbook_row_change`。
2. **apply 期按声明改** —— `apply_plan_zip_with_report` 逐条按声明改引用侧 sheet 与
   `xl/workbook.xml`，**不重跑扫描**。
3. **verify 期按同一份声明归一化** —— `verify_unmanaged_regions(propagation=...)`。

🔴 三个关口必须用**同一份**声明。任何一处改成「现扫」都会让另外两处的对账失去意义 ——
这正是本文件的判据要钉住的东西。

═══ 零传播路径必须逐字节不变 ═══

`row_shift is None`（不插行）或工作簿里没有跨 sheet 引用指向受管 sheet 时，
`workbook_row_change` 为 `None`，代码路径与本 spec 之前**逐字节相同**。
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

from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402


def _bare_plan(**overrides: Any) -> M.MaterializePlan:
    """最小 `MaterializePlan` —— 必填字段一处集中，避免每条判据各写一份。"""
    kwargs: dict[str, Any] = {
        "sheet_part": "xl/worksheets/sheet1.xml",
        "sheet_name": "受管表",
        "writes": (),
        "preserved_formulas": {},
        # ⚠ 是 Mapping（`{table: {field: column}}`）而不是 tuple —— `as_dict()` 会
        #    对它调 `.items()`。首版填 `()` 时 `as_dict()` 当场 AttributeError。
        "dynamic_column_columns": {},
    }
    kwargs.update(overrides)
    return M.MaterializePlan(**kwargs)


class TestPlanCarriesTheDeclaration:
    """计划期必须冻结声明，且零传播时保持 `None`。"""

    def test_materialize_plan_has_the_field(self) -> None:
        import dataclasses

        names = {f.name for f in dataclasses.fields(M.MaterializePlan)}
        assert "workbook_row_change" in names, names

    def test_field_defaults_to_none(self) -> None:
        """🔴 默认 `None` ⇒ 既有调用点与守卫逐字不变（零传播路径）。"""
        plan = _bare_plan()
        assert plan.workbook_row_change is None
        assert plan.as_dict()["workbook_row_change"] is None

    def test_plan_managed_writes_only_scans_when_shifting(self) -> None:
        """🔴 AST：扫描调用必须在 `row_shift is not None` 的分支里。

        不插行就没有行号变化要传播。无条件扫会让每次 materialize 都多跑一遍全工作簿
        扫描 —— 那既是性能问题，也会让「零位移路径逐字节不变」这条纪律失效。
        """
        source = textwrap.dedent(inspect.getsource(M.plan_managed_writes))
        tree = ast.parse(source)
        found_guarded = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            body_src = "".join(ast.dump(stmt) for stmt in node.body)
            if "plan_workbook_row_change_for_insert" not in body_src:
                continue
            test_src = ast.dump(node.test)
            if "row_shift" in test_src:
                found_guarded = True
        assert found_guarded, (
            "`plan_workbook_row_change_for_insert` 的调用不在 `row_shift is not None` "
            "分支里 —— 零位移路径会多跑扫描"
        )

    def test_scanner_is_the_single_source(self) -> None:
        """🔴 计划期走 N1 的 `scan_reference_carriers`，不自己抄一份扫描。"""
        source = textwrap.dedent(
            inspect.getsource(N1.plan_workbook_row_change_for_insert)
        )
        assert "scan_reference_carriers" in source
        assert "build_insert_plan" in source

    def test_returns_none_when_no_reference_exists(self) -> None:
        """没有任何跨 sheet 引用指向受管 sheet ⇒ `None` ⇒ 零传播路径。"""
        import io
        import zipfile

        buffer = io.BytesIO()
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                f'<worksheet xmlns="{ns}"><sheetData>'
                '<row r="13"><c r="A13"><v>1</v></c></row>'
                "</sheetData></worksheet>",
            )
            zf.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="' + ns + '" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="受管表" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/></Relationships>',
            )
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as zf:
            entries = {name: zf.read(name) for name in zf.namelist()}
        plan = N1.plan_workbook_row_change_for_insert(
            entries,
            managed_sheet_name="受管表",
            managed_sheet_part="xl/worksheets/sheet1.xml",
            insert_at=13,
            count=1,
            style_from=12,
            region_first_row=13,
            region_last_row=25,
        )
        assert plan is None


class TestApplyFollowsTheDeclaration:
    """apply 期必须逐条按声明改，且不碰受管 sheet（那半由 `shift_sheet_rows` 负责）。"""

    def test_apply_does_not_rescan(self) -> None:
        """🔴 AST：apply 侧不得调扫描器 —— 那会造出第二个真源。"""
        source = textwrap.dedent(inspect.getsource(M._apply_workbook_propagation))
        assert "scan_reference_carriers" not in source, (
            "apply 期重新扫描 ⇒ apply 与 plan 成了两个真源，"
            "而 verify 的归一化只认 plan 那一份"
        )
        assert "propagations" in source, "apply 没有读声明条目"

    def test_apply_skips_the_managed_sheet(self) -> None:
        """🔴 受管 sheet 不在这里改 —— 重复改会双重位移。"""
        source = textwrap.dedent(inspect.getsource(M._apply_workbook_propagation))
        assert "plan.sheet_part" in source and "continue" in source, source[:400]

    def test_apply_is_a_noop_without_declaration(self) -> None:
        """`workbook_row_change is None` 时 entries 原样返回（同一对象或等值）。"""
        plan = _bare_plan()
        entries = {"xl/worksheets/sheet2.xml": b"<x/>"}
        out = M._apply_workbook_propagation(dict(entries), plan=plan)
        assert out == entries

    def test_apply_refuses_when_declared_part_is_absent(self) -> None:
        """声明要改的 part 不在 zip 里 ⇒ fail closed（不带着对不上的计划写盘）。"""
        change = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.INSERT,
            managed_sheet_name="受管表",
            managed_sheet_part="xl/worksheets/sheet1.xml",
            at=13,
            count=1,
            style_from=12,
            region_first_row=13,
            region_last_row=25,
            propagations=(
                N1.PropagationEntry(
                    carrier="formula",
                    part="xl/worksheets/sheet9.xml",
                    locator="A1#0",
                    ref_before="'受管表'!A20",
                    ref_after="'受管表'!A21",
                    row_before=20,
                    row_after=21,
                ),
            ),
        )
        plan = _bare_plan(workbook_row_change=change)
        with pytest.raises(N1.PropagationDriftError, match="不在 substrate zip 里"):
            M._apply_workbook_propagation({"xl/worksheets/sheet1.xml": b"<x/>"}, plan=plan)

    def test_apply_refuses_on_count_mismatch(self) -> None:
        """声明 N 处但实际只改了 M 处 ⇒ 抛（artifact 在两相之间被动过）。"""
        change = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.INSERT,
            managed_sheet_name="受管表",
            managed_sheet_part="xl/worksheets/sheet1.xml",
            at=13,
            count=1,
            style_from=12,
            region_first_row=13,
            region_last_row=25,
            propagations=(
                N1.PropagationEntry(
                    carrier="formula",
                    part="xl/worksheets/sheet2.xml",
                    locator="A1#0",
                    ref_before="'受管表'!A20",
                    ref_after="'受管表'!A21",
                    row_before=20,
                    row_after=21,
                ),
            ),
        )
        plan = _bare_plan(workbook_row_change=change)
        with pytest.raises(N1.PropagationDriftError, match="实际只改了"):
            M._apply_workbook_propagation(
                {
                    "xl/worksheets/sheet1.xml": b"<x/>",
                    # 声明里的 ref_before 在这里找不到
                    "xl/worksheets/sheet2.xml": "<f>无关公式</f>".encode("utf-8"),
                },
                plan=plan,
            )

    def test_apply_rewrites_declared_reference(self) -> None:
        """正常路径：声明的引用被改成 `ref_after`。"""
        change = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.INSERT,
            managed_sheet_name="受管表",
            managed_sheet_part="xl/worksheets/sheet1.xml",
            at=13,
            count=1,
            style_from=12,
            region_first_row=13,
            region_last_row=25,
            propagations=(
                N1.PropagationEntry(
                    carrier="formula",
                    part="xl/worksheets/sheet2.xml",
                    locator="A5#0",
                    ref_before="'受管表'!A20",
                    ref_after="'受管表'!A21",
                    row_before=20,
                    row_after=21,
                ),
            ),
        )
        plan = _bare_plan(workbook_row_change=change)
        out = M._apply_workbook_propagation(
            {
                "xl/worksheets/sheet1.xml": b"<x/>",
                "xl/worksheets/sheet2.xml": "<f>'受管表'!A20+1</f>".encode("utf-8"),
            },
            plan=plan,
        )
        text = out["xl/worksheets/sheet2.xml"].decode("utf-8")
        assert "'受管表'!A21+1" in text, text


class TestPropagationOrderInApply:
    """🔴 传播必须排在**写格之前**、位移之后。"""

    @staticmethod
    def _call_order(func: Any) -> list[str]:
        """按**真实调用**（不含 docstring / 注释）的出现顺序列出被调函数名。

        🔴 用 AST 而不是 `str.find`：`apply_plan_zip_with_report` 的 docstring 里
        写着「最后才 `_patch_sheet_xml` 写格」，字符串查找会命中那句话（偏移 379）
        而不是真正的调用（偏移 1601），于是判据在正确的代码上打红。
        首版就踩了这个坑。
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        calls: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name:
                calls.append((node.lineno, name))
        return [name for _lineno, name in sorted(calls)]

    def test_propagation_precedes_cell_patch(self) -> None:
        """AST：`_apply_workbook_propagation` 的调用在 `_patch_sheet_xml` 之前。

        若排在写格之后，写格产生的新字节会进入传播的输入 ⇒ 声明与实测的对账口径
        就不再是「计划期冻结的那份」。
        """
        order = self._call_order(M.apply_plan_zip_with_report)
        assert "_apply_workbook_propagation" in order, order
        assert "_patch_sheet_xml" in order, order
        assert order.index("_apply_workbook_propagation") < order.index(
            "_patch_sheet_xml"
        ), f"传播排在写格之后 —— 写格的新字节会进入传播输入，对账口径失真：{order}"

    def test_propagation_follows_row_shift(self) -> None:
        """AST：传播在 `shift_sheet_rows` 之后（传播的行号基于位移后口径）。"""
        order = self._call_order(M.apply_plan_zip_with_report)
        assert "shift_sheet_rows" in order, order
        assert order.index("shift_sheet_rows") < order.index(
            "_apply_workbook_propagation"
        ), order
