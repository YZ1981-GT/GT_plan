# -*- coding: utf-8 -*-
"""A3/A4（按声明传播）+ A5（受管 sheet 裸引用平移）的 apply 侧判据。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 11.1~11.3 · 12.1~12.4
Properties: 1（字节那一半）· 10 · 11 · 12 · 13 · 14
Requirements: 1.2, 1.3, 4.1~4.7, 5.1~5.7

═══ 靶子为什么**不能**用 K11 ═══

K11 受管区 7..25 的**每一行**都有 6 处跨 sheet 单格引用（`'审定表K11-1'!A7`/`!G7`/`!D7`
逐行，写在 sheet4/sheet5 上）—— `find_undeletable_rows` 的 docstring 早已实测
「19 行全部被锁，100% 阻断」。拿它当删行靶子，`plan_workbook_row_change_for_delete`
在计划期就正确地抛 `DanglingReferenceError`，判据全部走不到 apply。

═══ 靶子为什么是 D1-8 DISCOUNT 区 ═══

现算（`find_undeletable_rows` 生产口径）：
* 受管区 **14..21**、footer **22**、裸合计 `B22=SUM(E14:E21)` / `F22=SUM(F14:F21)` /
  `G22=SUM(L14:L21)` ⇒ 区间末行**恰等于**受管区末行，正是 Property 14 的边界；
* 8 行**全部可删**（单格引用 0 处）⇒ apply 侧判据够得着；
* 同一 sheet 上还有兄弟区 `GT_D18_TRANSFER_ROWS`（26..33）⇒ 顺带覆盖 A1 的联动；
* 有 `_GT_SYNC` ⇒ A2 的重冻结相能跑。
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

import test_sibling_table_ref_row_shift as SIB  # noqa: E402

PROVIDER = "phase5_d1_notes_receivable"
SHEET = "应收票据贴现、票据已背书未到期明细表D1-8"
TABLE = "GT_D18_DISCOUNT_ROWS"
SIBLING_TABLE = "GT_D18_TRANSFER_ROWS"
UUID_COL = "Q"
FIRST_ROW = 14
LAST_ROW = 21
FOOTER_ROW = 22
#: 契约里这两个区的 `table_key`（现读 `D1.build_contract_payload()` 的 `d18-managed` sheet）。
#: 🔴 `ExcelInstrumentationSpec` **没有** `table_key` 字段（它只有 `template_id` /
#:    `sheet_key` / `table_name`），所以不能从 spec 反查；写成常量并由
#:    `test_fixture_preconditions` 断言它在契约里真的存在、且 region 解析到 14..21。
TABLE_KEY = "endorse_discount_rows"
SIBLING_TABLE_KEY = "endorse_transfer_rows"
#: footer 上带**裸**合计公式的格（现算，`_bdelp_find_target` 出）。
TOTAL_CELL = "F22"


# ═══════════════════════════════════════════════════════════════════════════
# 1. D1-8 删行世界
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def world() -> dict[str, Any]:
    data = SIB._instrumented_bytes_for_provider(PROVIDER)
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                entries[name] = zf.read(name)
        sheet_part = EE._sheet_parts(zf).get(SHEET)
    assert sheet_part, f"定位不到受管 sheet part：{SHEET}"
    return {
        "bytes": data,
        "entries": entries,
        "sheet_part": sheet_part,
        "table_part": M._managed_table_part(entries, table_name=TABLE),
        "sibling_part": M._managed_table_part(entries, table_name=SIBLING_TABLE),
    }


def _entries_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def _formulas_of(xml: str) -> dict[str, str]:
    """`{坐标: 公式文本}` —— ElementTree（与生产 digest 同口径，免正则过度匹配）。"""
    out: dict[str, str] = {}
    root = ET.fromstring(xml)
    for cell in root.iter():
        if cell.tag.rsplit("}", 1)[-1] != "c":
            continue
        ref = cell.attrib.get("r", "")
        if not ref:
            continue
        for child in cell:
            if child.tag.rsplit("}", 1)[-1] == "f" and (child.text or "").strip():
                out[ref] = child.text or ""
    return out


def _cell_text(view: Any, shared: list[str]) -> str:
    raw = view.raw
    if 't="s"' in (view.attrs or ""):
        found = re.search(r"<v>(\d+)</v>", raw)
        if found is not None:
            idx = int(found.group(1))
            return shared[idx] if 0 <= idx < len(shared) else ""
        return ""
    inline = re.findall(r"<t[^>]*>(.*?)</t>", raw, re.S)
    if inline:
        return "".join(inline)
    found = re.search(r"<v>(.*?)</v>", raw, re.S)
    return found.group(1) if found else ""


def _uuids_of(world: dict[str, Any], rows: tuple[int, ...]) -> dict[int, str]:
    """从 substrate **真读** UUID 列（不编造身份）。"""
    xml = world["entries"][world["sheet_part"]].decode("utf-8")
    index = M.build_sheet_cell_index(xml)
    shared = M._shared_strings(world["entries"])
    out: dict[int, str] = {}
    for row in rows:
        view = index.view(f"{UUID_COL}{row}")
        out[row] = _cell_text(view, shared) if view is not None else ""
    return out


def _plan(
    world: dict[str, Any],
    deleted: tuple[int, ...],
    *,
    total_formula_rows: tuple[int, ...] = (),
    with_declaration: bool = True,
) -> M.MaterializePlan:
    shift = N1.RowDeletionShift(
        deleted_rows=deleted, region_first_row=FIRST_ROW, region_last_row=LAST_ROW
    )
    change = None
    if with_declaration:
        change = N1.plan_workbook_row_change_for_delete(
            world["entries"],
            managed_sheet_name=SHEET,
            managed_sheet_part=world["sheet_part"],
            deleted_rows=deleted,
            region_first_row=FIRST_ROW,
            region_last_row=LAST_ROW,
            row_uuids=_uuids_of(world, deleted),
        )
    return M.MaterializePlan(
        sheet_part=world["sheet_part"],
        sheet_name=SHEET,
        writes=(),
        preserved_formulas={},
        dynamic_column_columns={},
        table_part=world["table_part"],
        stale_deleted=tuple(sorted(deleted)),
        managed_table_name=TABLE,
        total_formula_rows=total_formula_rows,
        row_deletion=shift,
        deletion_change=change,
    )


def _apply(world: dict[str, Any], plan: M.MaterializePlan) -> bytes:
    product, _report = M.apply_plan_zip_with_report(world["bytes"], plan)
    return product


def _content_sha(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        payload = "|".join(
            f"{n}:{hashlib.sha256(zf.read(n)).hexdigest()}" for n in sorted(zf.namelist())
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tail_row_of(formula: str) -> int:
    found = re.search(r":\s*\$?[A-Z]{1,3}\$?(\d+)", formula)
    assert found is not None, f"公式里没有区间：{formula!r}"
    return int(found.group(1))


def _head_row_of(formula: str) -> int:
    found = re.search(r"\$?[A-Z]{1,3}\$?(\d+)\s*:", formula)
    assert found is not None, f"公式里没有区间：{formula!r}"
    return int(found.group(1))


# ═══════════════════════════════════════════════════════════════════════════
# 2. 前提实测（fixture 非退化）
# ═══════════════════════════════════════════════════════════════════════════


def test_fixture_preconditions(world: dict[str, Any]) -> None:
    """🔴 四条前提：合计是裸引用 / 末行恰等于受管末行 / 全区可删 / 有兄弟区。"""
    xml = world["entries"][world["sheet_part"]].decode("utf-8")
    formulas = _formulas_of(xml)
    assert TOTAL_CELL in formulas, f"{TOTAL_CELL} 上没有公式：{sorted(formulas)[:12]}"
    total = formulas[TOTAL_CELL]
    assert "!" not in total, f"{TOTAL_CELL} 不是**裸**引用：{total!r}"
    assert _tail_row_of(total) == LAST_ROW, (
        f"合计区间末行 {_tail_row_of(total)} ≠ 受管末行 {LAST_ROW} ⇒ "
        "Property 14 的边界样本落空"
    )
    # 全区可删（生产口径）
    from app.services.excel_structure_fingerprint import (
        _normalise_part,
        _parse_workbook_xml,
    )

    with zipfile.ZipFile(io.BytesIO(world["bytes"])) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        sheet_parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = N1.scan_reference_carriers(
            zf, target_sheet=SHEET, sheet_parts=sheet_parts, defined_names=defined
        )
    blocked = N1.find_undeletable_rows(
        scan, region_first_row=FIRST_ROW, region_last_row=LAST_ROW, count=1
    )
    assert blocked == (), f"受管区内有不可删行 {blocked} ⇒ apply 侧判据够不着"
    assert world["sibling_part"] and world["sibling_part"] != world["table_part"]
    # UUID 列真有身份（留痕门够得着）
    uuids = _uuids_of(world, tuple(range(FIRST_ROW, LAST_ROW + 1)))
    assert all(uuids.values()), f"UUID 列有空值：{uuids}"
    # 🔴 两个 table_key 在契约里真的存在，且本区声明了 `carries_total_formula`
    contract = build_contract()
    keys = {t.table_key for s in contract.sheets for t in s.tables}
    assert {TABLE_KEY, SIBLING_TABLE_KEY} <= keys, (
        f"契约里找不到 {TABLE_KEY} / {SIBLING_TABLE_KEY}：{sorted(keys)[:12]}"
    )
    table = next(
        t for s in contract.sheets for t in s.tables if t.table_key == TABLE_KEY
    )
    assert table.footer_anchor is not None and table.footer_anchor.carries_total_formula, (
        "契约没声明 carries_total_formula ⇒ Property 13 的「已声明」那一态落空"
    )
    assert table.delete_policy is not None, "没有 delete_policy ⇒ 开启删行的 CS 规则验不了"


def build_contract() -> Any:
    from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
    from app.services.workpaper_sync.contracts import parse_contract

    return parse_contract(D1.build_contract_payload(), adapter_id=D1.ADAPTER_ID)


def build_binding() -> Any:
    return EE.ExcelIdentityBinding(
        table_name=TABLE, uuid_column=UUID_COL, table_key=TABLE_KEY
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 12 / 13 / 14：受管 sheet 裸引用平移（A5）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty12BareRefsShift:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 12: 受管 sheet 裸引用平移**

    **Validates: Requirement 5.1**
    """

    @pytest.mark.parametrize("row", [FIRST_ROW, FIRST_ROW + 3, LAST_ROW - 1, LAST_ROW])
    def test_total_range_tail_moves_up_by_one(
        self, world: dict[str, Any], row: int
    ) -> None:
        """删受管区内任一行 ⇒ 合计区间末行上移 1（裸引用真被平移）。"""
        before = _formulas_of(world["entries"][world["sheet_part"]].decode("utf-8"))
        product = _apply(world, _plan(world, (row,), total_formula_rows=(FOOTER_ROW,)))
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        coord_after = f"{col}{FOOTER_ROW - 1}"
        assert coord_after in after, f"合计格没落在 {coord_after}：{sorted(after)[-8:]}"
        assert _tail_row_of(after[coord_after]) == LAST_ROW - 1, (
            f"删 r={row}：{before[TOTAL_CELL]!r} → {after[coord_after]!r}，"
            f"末行应为 {LAST_ROW - 1}"
        )

    def test_range_head_stays_put_when_first_row_deleted(
        self, world: dict[str, Any]
    ) -> None:
        """删受管区**首行** ⇒ 合计区间**首行原地不动**（向下塌到下一存活行的新位置）。"""
        product = _apply(
            world, _plan(world, (FIRST_ROW,), total_formula_rows=(FOOTER_ROW,))
        )
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        formula = after[f"{col}{FOOTER_ROW - 1}"]
        assert _head_row_of(formula) == FIRST_ROW, (
            f"删首行后合计区间首行漂到 {_head_row_of(formula)}（应为 {FIRST_ROW}）：{formula!r}"
            " —— 区间凭空多覆盖一行"
        )

    def test_qualified_refs_are_not_touched_by_a5(self, world: dict[str, Any]) -> None:
        """🔴 A5 只管**裸**引用：限定引用由 A3/A4 的声明改，不在这里双改。

        双改的症状是「位移了两次」—— 产物能打开、值是隔两行的。
        """
        xml = world["entries"][world["sheet_part"]].decode("utf-8")
        plan = _plan(world, (FIRST_ROW + 3,), total_formula_rows=(FOOTER_ROW,))
        shrunk, _ = N1.shrink_sheet_rows(xml, delete_at=FIRST_ROW + 3, count=1)
        out, changed = M._shift_managed_sheet_bare_refs(shrunk, plan=plan)
        before_q = {c: f for c, f in _formulas_of(shrunk).items() if "!" in f}
        after_q = {c: f for c, f in _formulas_of(out).items() if "!" in f}
        assert changed > 0, "A5 一条公式都没改 ⇒ 下面的『限定引用没变』是恒真"
        if before_q:
            assert after_q == before_q, (
                "A5 改动了限定引用："
                f"{ {k: (before_q[k], after_q.get(k)) for k in before_q if after_q.get(k) != before_q[k]} }"
            )

    def test_single_a1_rewriter_entrypoint(self) -> None:
        """🔴 结构锁：A5 走既有改写器，**不**复用 `shift_sheet_rows`、不新写一份。"""
        import ast
        import inspect
        import textwrap

        def _callees(func: Any) -> set[str]:
            src = textwrap.dedent(inspect.getsource(func))
            return {
                getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Call)
            }

        # 🔴 判据必须**跟随间接层**：A5 与 A8 共用的端点感知改写器
        # `remap_bare_a1_for_deletion` 抽出来之后，`_rewrite_formula_refs` 就不在 A5 的
        # 直接被调集合里了。只看一层的话这条结构锁会误判「没走既有改写器」——
        # 收敛重复代码本是正事，判据不该因此打红。
        called = _callees(M._shift_managed_sheet_bare_refs)
        assert "remap_bare_a1_for_deletion" in called, sorted(c for c in called if c)
        called |= _callees(M.remap_bare_a1_for_deletion)
        assert "_rewrite_formula_refs" in called, sorted(c for c in called if c)
        assert "shift_sheet_rows" not in called, (
            "复用了插行的 `shift_sheet_rows` —— 上游明文：那个函数的语义是造新行 + 下移，"
            "共用会让两边的边界条件互相干扰"
        )
        assert "classify_bare_row_roles" in called, "没做 head/tail 角色分类"

    def test_role_classification_fails_closed_on_ambiguity(self) -> None:
        """🔴 一个行号同时是某区间起点与另一区间终点 ⇒ 一个 remap 表达不了 ⇒ 抛。"""
        rows, heads, tails = N1.classify_bare_row_roles("A5:A9+A1:A5")
        assert 5 in heads and 5 in tails, (rows, heads, tails)
        # 单格引用不进任何角色集合
        rows2, heads2, tails2 = N1.classify_bare_row_roles("B20*2")
        assert rows2 == frozenset({20}) and not heads2 and not tails2

    def test_role_classification_ignores_qualified_ranges(self) -> None:
        """限定区间的端点不算裸行号（否则会给它们一个不该有的方向修正）。"""
        rows, heads, tails = N1.classify_bare_row_roles("SUM('别表'!A1:A9)")
        assert rows == frozenset(), rows
        assert not heads and not tails


class TestProperty13TotalRangeIsContractGated:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 13: 合计区间收缩受契约声明门控**

    **Validates: Requirements 5.4, 5.5**
    """

    def test_declared_footer_is_rewritten(self, world: dict[str, Any]) -> None:
        product = _apply(
            world, _plan(world, (LAST_ROW,), total_formula_rows=(FOOTER_ROW,))
        )
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        assert _tail_row_of(after[f"{col}{FOOTER_ROW - 1}"]) == LAST_ROW - 1

    def test_undeclared_footer_formula_is_verbatim(self, world: dict[str, Any]) -> None:
        """🔴 契约**未**声明 `carries_total_formula` ⇒ 该 footer 的公式一个字都不改。

        与插行侧「未声明即不扩张、让 `assert_footer_formula_covers_managed_rows` 去拦」对称。
        """
        before = _formulas_of(world["entries"][world["sheet_part"]].decode("utf-8"))
        product = _apply(world, _plan(world, (LAST_ROW,), total_formula_rows=()))
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        assert after[f"{col}{FOOTER_ROW - 1}"] == before[TOTAL_CELL], (
            f"未声明却改写了 footer 公式：{before[TOTAL_CELL]!r} → "
            f"{after[f'{col}{FOOTER_ROW - 1}']!r}"
        )

    def test_the_gate_really_gates(self, world: dict[str, Any]) -> None:
        """两态对照：同一删除集，只有「声明与否」不同 ⇒ 结果必须不同。

        缺这条的话「未声明不改」与「根本没实现改写」分辨不出来。
        """
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        coord = f"{col}{FOOTER_ROW - 1}"
        a = _formulas_of(
            _entries_of(
                _apply(world, _plan(world, (LAST_ROW,), total_formula_rows=(FOOTER_ROW,)))
            )[world["sheet_part"]].decode("utf-8")
        )
        b = _formulas_of(
            _entries_of(_apply(world, _plan(world, (LAST_ROW,), total_formula_rows=())))[
                world["sheet_part"]
            ].decode("utf-8")
        )
        assert a[coord] != b[coord], "声明与未声明产出同一份公式 ⇒ 门控没有区分力"

    def test_rows_inside_the_region_are_rewritten_regardless_of_the_gate(
        self, world: dict[str, Any]
    ) -> None:
        """门控只管**受管区下方**的 footer；区内/区上的裸引用照常平移（Requirement 5.1）。"""
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._shift_managed_sheet_bare_refs))
        assert "row_before > region_last" in src, (
            "门控条件不是「受管区下方」—— 写宽了会把区内公式也豁免掉"
        )


class TestProperty14TotalRangeExcludesFooterItself:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 14: 合计区间不得覆盖 footer 自身**

    **Validates: Requirements 5.6, 5.7**
    """

    @pytest.mark.parametrize(
        "deleted",
        [
            (LAST_ROW,),
            (LAST_ROW - 1, LAST_ROW),
            (FIRST_ROW,),
            (FIRST_ROW + 2,),
            (FIRST_ROW, LAST_ROW),
            (FIRST_ROW, FIRST_ROW + 1, LAST_ROW),
        ],
    )
    def test_total_range_end_is_strictly_above_the_footer_row(
        self, world: dict[str, Any], deleted: tuple[int, ...]
    ) -> None:
        product = _apply(world, _plan(world, deleted, total_formula_rows=(FOOTER_ROW,)))
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        footer_after = FOOTER_ROW - len(deleted)
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        coord = f"{col}{footer_after}"
        assert coord in after, f"合计格没落在 {coord}：{sorted(after)[-8:]}"
        tail = _tail_row_of(after[coord])
        assert tail < footer_after, (
            f"删 {list(deleted)} 后合计区间末行 {tail} 覆盖到 footer 自身所在行 "
            f"{footer_after}（公式 {after[coord]!r}）—— Excel 循环引用 / 静默多算一行"
        )
        assert tail == LAST_ROW - len(deleted), (
            f"合计区间末行应为删行后的受管末行 {LAST_ROW - len(deleted)}，实得 {tail}"
        )

    def test_mutation_skipping_the_shift_reds_this_property(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 变异反证：短路 A5 ⇒ 上面的断言必须打红。"""
        monkeypatch.setattr(
            M, "_shift_managed_sheet_bare_refs", lambda xml, *, plan: (xml, 0)
        )
        product = _apply(
            world, _plan(world, (LAST_ROW,), total_formula_rows=(FOOTER_ROW,))
        )
        after = _formulas_of(_entries_of(product)[world["sheet_part"]].decode("utf-8"))
        footer_after = FOOTER_ROW - 1
        col = re.match(r"([A-Z]+)", TOTAL_CELL).group(1)
        tail = _tail_row_of(after[f"{col}{footer_after}"])
        assert tail >= footer_after, (
            f"短路 A5 后合计区间末行 {tail} 仍未覆盖 footer 行 {footer_after} ⇒ "
            "Property 14 没有区分力"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 10 / 11：按声明位移（A3/A4）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么这两条**不**在 D1-8 上测：现算 D1-8 的删行声明是 7 条、载体分布
#    `{defined_name: 7, formula: 0, …}` —— 没有任何跨 sheet **公式**指向它。
#    只在它上面验 Property 10 会让「跨 sheet 公式传播」这一半在空集上恒真。
#    所以用 `test_row_deletion_declaration` 的合成双 sheet 工作簿（引用侧 sheet 上有
#    删除点之上/之下/跨区间三类**公式**引用 + definedName），直接验
#    `_apply_workbook_propagation` 这个执行单元；真实接线由 D1-8 的端到端那几条承担。

import test_row_deletion_declaration as DECL  # noqa: E402


def _decl_plan(
    entries: dict[str, bytes], deleted: tuple[int, ...]
) -> M.MaterializePlan:
    change = DECL.plan_delete(deleted, entries=entries)
    assert change is not None, f"合成工作簿上删 {list(deleted)} 应产出声明"
    return M.MaterializePlan(
        sheet_part=DECL.MANAGED_PART,
        sheet_name=DECL.MANAGED_SHEET,
        writes=(),
        preserved_formulas={},
        dynamic_column_columns={},
        stale_deleted=tuple(sorted(deleted)),
        row_deletion=change.shift,
        deletion_change=change,
    )


class TestProperty10PropagationFollowsTheDeclaration:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 10: 按声明位移的三类形态**

    **Validates: Requirements 4.1, 4.5, 4.6, 4.7**
    """

    def test_fixture_covers_all_three_shapes(self) -> None:
        """🔴 前提：合成工作簿上三类形态**都有**样本，且载体不只 definedName。"""
        change = DECL.plan_delete((20,))
        assert change is not None
        counts = change.propagation_counts()
        assert counts["formula"] > 0, f"没有跨 sheet 公式条目 ⇒ 判据空转：{counts}"
        assert counts["defined_name"] > 0, f"没有 definedName 条目：{counts}"
        # 三类形态：之上（不动，不进声明）/ 之下（上移）/ 跨区间（收缩）
        ranges = [e for e in change.propagations if ":" in e.ref_before]
        singles = [e for e in change.propagations if ":" not in e.ref_before]
        assert ranges and singles, (
            f"区间/单格两类样本不全：ranges={len(ranges)} singles={len(singles)}"
        )

    @pytest.mark.parametrize("deleted", [(20,), (12, 20), (7,), (25,)])
    def test_every_declared_entry_is_applied_verbatim(
        self, deleted: tuple[int, ...]
    ) -> None:
        """① 声明点名的每处引用都已改成其**声明的**改后文本。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, deleted)
        out = M._apply_workbook_propagation(dict(entries), plan=plan)
        for entry in plan.deletion_change.propagations:
            text = out[entry.part].decode("utf-8")
            assert entry.ref_after in text or entry.ref_after.replace("'", "&apos;") in text, (
                f"{entry.part}!{entry.locator} 没被改成声明的 {entry.ref_after!r}"
            )
            assert entry.ref_before not in text, (
                f"{entry.part}!{entry.locator} 的改前文本 {entry.ref_before!r} 仍在 —— 没改"
            )

    def test_references_above_the_deleted_rows_are_verbatim(self) -> None:
        """② 位于被删行**之上**的引用逐字不变（它们根本不进声明）。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, (20,))
        before = entries[DECL.REF_PART].decode("utf-8")
        out = M._apply_workbook_propagation(dict(entries), plan=plan)
        after = out[DECL.REF_PART].decode("utf-8")
        # `A1` 上是 `'受管表'!B8`（删除点之上）
        assert f"'{DECL.MANAGED_SHEET}'!B8" in before
        assert f"'{DECL.MANAGED_SHEET}'!B8" in after, (
            "删除点之上的引用被改动了 —— 那是把没动的数据也指走了"
        )

    @pytest.mark.parametrize("deleted", [(20,), (12, 20, 21)])
    def test_spanning_range_shrinks_by_the_deleted_count_inside(
        self, deleted: tuple[int, ...]
    ) -> None:
        """③ 跨越被删区间的区间引用，覆盖行数的减少量 == 区间内被删行数。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, deleted)
        spanning = [
            e
            for e in plan.deletion_change.propagations
            if ":" in e.ref_before and e.carrier == "formula"
        ]
        assert spanning, "没有跨区间的公式条目 ⇒ 本条空转"
        for entry in spanning:
            b_head, b_tail = DECL._endpoint_rows(entry.ref_before)
            a_head, a_tail = DECL._endpoint_rows(entry.ref_after)
            inside = sum(1 for d in deleted if b_head <= d <= b_tail)
            before_span = b_tail - b_head + 1
            after_span = a_tail - a_head + 1
            assert before_span - after_span == inside, (
                f"{entry.locator}：{entry.ref_before!r} → {entry.ref_after!r}，"
                f"覆盖行数 {before_span}→{after_span}（减 {before_span - after_span}），"
                f"而区间内被删 {inside} 行"
            )

    def test_replacement_algorithm_is_untouched(self) -> None:
        """🔴 结构锁：`_apply_workbook_propagation` 的替换算法逐字未变，只多了选声明那一步。"""
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._apply_workbook_propagation))
        # 四候选形态与单次扫描都还在
        for needle in ("_apos(_escape(before))", "pattern.sub(_swap", "text.count(cand_before)"):
            assert needle in src, f"替换算法被改动了，找不到：{needle!r}"
        assert "plan.deletion_change" in src, "没有接上删行声明"
        assert "scan_reference_carriers" not in src, "apply 期重新扫描 ⇒ 第二个真源"

    def test_two_declarations_at_once_is_refused(self) -> None:
        """🔴 插行与删行两份声明同时存在 ⇒ fail-closed（纵深防御）。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, (20,))
        import dataclasses

        both = dataclasses.replace(plan, workbook_row_change=plan.deletion_change)
        with pytest.raises(M.RowSetDivergenceError) as err:
            M._apply_workbook_propagation(dict(entries), plan=both)
        assert "two_propagation_declarations" in str(err.value)


class TestProperty11PropagationReconciliationFailsClosed:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 11: 传播对账 fail-closed**

    **Validates: Requirements 4.3, 4.4**
    """

    def test_missing_part_is_refused(self) -> None:
        """声明点名的部件不在工作簿里 ⇒ `PropagationDriftError`。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, (20,))
        crippled = {k: v for k, v in entries.items() if k != DECL.REF_PART}
        with pytest.raises(N1.PropagationDriftError) as err:
            M._apply_workbook_propagation(crippled, plan=plan)
        assert DECL.REF_PART in str(err.value)

    def test_count_mismatch_is_refused(self) -> None:
        """实改处数 ≠ 声明处数 ⇒ `PropagationDriftError`（artifact 在两相之间被动过）。"""
        entries = DECL.build_entries()
        plan = _decl_plan(entries, (20,))
        # 把引用侧 sheet 上的一处声明目标**抹掉** ⇒ 实改数少于声明数
        target = next(
            e for e in plan.deletion_change.propagations if e.part == DECL.REF_PART
        )
        tampered = dict(entries)
        tampered[DECL.REF_PART] = (
            entries[DECL.REF_PART].decode("utf-8").replace(target.ref_before, "REMOVED")
        ).encode("utf-8")
        with pytest.raises(N1.PropagationDriftError) as err:
            M._apply_workbook_propagation(tampered, plan=plan)
        assert "声明" in str(err.value)

    def test_no_bytes_are_produced_when_it_fails(self, world: dict[str, Any]) -> None:
        """🔴 失败即**零产物**：整条 apply 抛错时不落任何字节。

        判据在 `apply_plan_zip_with_report` 这一层 —— 它返回字节而不落盘，
        抛错发生在返回之前，所以调用方拿不到半成品。
        """
        plan = _plan(world, (LAST_ROW,), total_formula_rows=(FOOTER_ROW,))
        import dataclasses

        # 让声明点名一个不存在的 part
        bogus = N1.PropagationEntry(
            carrier="defined_name",
            part="xl/does-not-exist.xml",
            locator="X#0",
            ref_before=f"'{SHEET}'!$A$22",
            ref_after=f"'{SHEET}'!$A$21",
            row_before=22,
            row_after=21,
        )
        change = dataclasses.replace(
            plan.deletion_change,
            propagations=plan.deletion_change.propagations + (bogus,),
        )
        broken = dataclasses.replace(plan, deletion_change=change)
        before_sha = _content_sha(world["bytes"])
        with pytest.raises(N1.PropagationDriftError):
            M.apply_plan_zip_with_report(world["bytes"], broken)
        assert _content_sha(world["bytes"]) == before_sha, "入参字节被改动了"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 1：零传播路径恒等（字节那一半）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1ZeroPropagationIsByteIdentical:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 1: 零传播路径恒等**

    **Validates: Requirements 1.2, 1.3**

    ⚠ 比的是**内容口径**（`{条目名: sha256(载荷)}`）而不是 zip 容器 sha256：
    `_write_entries` 用 `writestr(name, payload)` 会把当前时间写进条目头
    ⇒ 容器 sha 不稳定，拿它当判据就是一个永红门禁
    （同一条理由见 `test_clear_path_byte_zero_regression` 的模块 docstring）。
    """

    def test_no_reference_workbook_is_byte_identical_with_and_without_the_planner(
        self,
    ) -> None:
        """没有任何指向受管 sheet 的引用 ⇒ 产物内容与「根本不产声明」时逐字节相同。"""
        entries = DECL.build_entries(no_reference_at_all=True)
        deleted = (20,)
        change = DECL.plan_delete(deleted, entries=entries)
        assert change is None, f"这份工作簿应走零传播路径，实得 {change}"
        product_a = M._apply_workbook_propagation(dict(entries), plan=_bare(entries, deleted, change))
        product_b = M._apply_workbook_propagation(dict(entries), plan=_bare(entries, deleted, None))
        assert product_a == product_b
        # 且**逐条目**与输入相同（传播一个字节都没改）
        assert product_a == entries, (
            f"零传播路径改动了字节：{sorted(k for k in entries if product_a.get(k) != entries[k])}"
        )

    def test_all_references_above_is_also_zero_propagation(self) -> None:
        entries = DECL.build_entries(reference_rows_only_above=True)
        assert DECL.plan_delete((20,), entries=entries) is None
        out = M._apply_workbook_propagation(dict(entries), plan=_bare(entries, (20,), None))
        assert out == entries

    def test_the_comparison_has_discriminating_power(self) -> None:
        """🔴 反向：**有**传播时两者必须**不同** —— 否则上面两条是恒真。"""
        entries = DECL.build_entries()
        change = DECL.plan_delete((20,), entries=entries)
        assert change is not None
        with_decl = M._apply_workbook_propagation(dict(entries), plan=_bare(entries, (20,), change))
        without = M._apply_workbook_propagation(dict(entries), plan=_bare(entries, (20,), None))
        assert with_decl != without, (
            "有声明与无声明产出同一份字节 ⇒ 声明根本没被消费，Property 1 恒真"
        )


def _bare(entries: dict[str, bytes], deleted: tuple[int, ...], change: Any) -> M.MaterializePlan:
    return M.MaterializePlan(
        sheet_part=DECL.MANAGED_PART,
        sheet_name=DECL.MANAGED_SHEET,
        writes=(),
        preserved_formulas={},
        dynamic_column_columns={},
        stale_deleted=tuple(sorted(deleted)),
        row_deletion=N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=DECL.REGION_FIRST,
            region_last_row=DECL.REGION_LAST,
        ),
        deletion_change=change,
    )
