# -*- coding: utf-8 -*-
"""A1 同 sheet 兄弟 Excel Table `ref` 随删行收缩（Properties 7/8 + 覆盖面普查 + 变异反证）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 9.1 · 9.2 · 9.3 · 9.4
Requirements: 2.1~2.8

═══ 为什么必须用真实双区 artifact ═══

模板库里**没有**同 sheet 多受管区（B8 口径纪律①：GT_* 受管 Excel Table 由
`excel_instrumentation` 在**运行期**写入，`wp_templates/` 上现算 0 ⇒ 在那里验等于空转）。
本文件走 `instrument_workbook_bytes_multi` 这条**生产**路径造双区字节，
并复用 `test_sibling_table_ref_row_shift` 的 fixture 构造件 —— 抄第二份就会出现
「插行侧在 A 形态上验过、删行侧在 B 形态上验过」而两者根本不是同一份字节。

═══ 🔴 两个「18」不是同一个集合 ═══

* B8（design「§ 现算基线」）扫 `backend/storage/**` 真实 artifact 得 **18** 组结构；
* 本文件的参数化源 `_multi_region_sheets()` 按 phase5 provider 的 instrumentation specs
  现算，也得 **18** 组。

两个 18 是**巧合**：交集只有 14。B8 独有 D6-6 / D6-9 / D7-4 / D7-7（历史产物里有，
当前 provider specs 里没有）；specs 独有 G5-2 / G1-2 / G3-2 / G9-2。
⇒ 断言「参数条数 == 18」会**恰好为真却覆盖了另一个集合**。本文件因此断言
「参数条数 == 现算的 specs 组数」，并把两个口径的差集显式登记（`test_two_census_differ`），
让缺口可见而不是静默。
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync.excel_workbook_row_change import (  # noqa: E402
    RowDeletionShift,
)

# 🔴 复用**同一份** fixture 构造件（插行侧判据用的就是它）。
import test_sibling_table_ref_row_shift as SIB  # noqa: E402

PBT = settings(max_examples=5, deadline=None)

#: 当前 instrumentation 就**已经**坏掉的多区 sheet —— 与本 spec 无关，显式登记 + 反向断言。
KNOWN_BROKEN_AT_INSTRUMENTATION: frozenset[str] = frozenset({"余额明细表G5-2"})


# ═══════════════════════════════════════════════════════════════════════════
# 1. D4-1 双区世界（main `GT_D41_MAIN_ROWS` / other `GT_D41_OTHER_ROWS`，同一 sheet）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def dual() -> dict[str, Any]:
    """真实 D4-1 双区 instrumented 字节 + 两区 region + Table part。"""
    inst = SIB.EI.instrument_workbook_bytes_multi(
        SIB.D4.read_authoritative_template(),
        SIB.D4.instrumentation_specs(),
        gate=SIB.D4.excel_carrier_gate(),
    )
    data = inst.instrumented_bytes
    contract = SIB.parse_contract(
        SIB.D4.build_contract_payload(), adapter_id=SIB.D4.ADAPTER_ID
    )
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                entries[name] = zf.read(name)
        region_main = EE.resolve_managed_region(
            zf, contract=contract, binding=SIB.BINDING_MAIN
        )
        region_other = EE.resolve_managed_region(
            zf, contract=contract, binding=SIB.BINDING_OTHER
        )
    assert region_main.sheet_part == region_other.sheet_part, (
        "两区不在同一 sheet ⇒ 本文件的整个前提不成立"
    )
    main_part = M._managed_table_part(entries, table_name=SIB.A.TABLE_NAME_MAIN)
    other_part = M._managed_table_part(entries, table_name=SIB.A.TABLE_NAME_OTHER)
    assert main_part and other_part and main_part != other_part
    return {
        "bytes": data,
        "entries": entries,
        "contract": contract,
        "region_main": region_main,
        "region_other": region_other,
        "sheet_part": region_main.sheet_part,
        "main_part": main_part,
        "other_part": other_part,
    }


def _ref_of(entries: Mapping[str, bytes], part: str) -> str:
    """该 Table part 的 `ref` 原文（唯一一处）。"""
    import re as _re

    xml = entries[part].decode("utf-8")
    found = _re.search(r'\bref="(?P<ref>[A-Z]{1,3}\d+:[A-Z]{1,3}\d+)"', xml)
    assert found is not None, f"{part} 里读不到 ref：{xml[:200]}"
    return found.group("ref")


def _display_name_of(entries: Mapping[str, bytes], part: str) -> str:
    import re as _re

    xml = entries[part].decode("utf-8")
    found = _re.search(r'\bdisplayName="([^"]*)"', xml)
    assert found is not None, f"{part} 里读不到 displayName"
    return found.group(1)


def _split_ref(ref: str) -> tuple[str, int, str, int]:
    import re as _re

    head, tail = ref.split(":", 1)
    return (
        _re.sub(r"\d", "", head),
        int(_re.sub(r"\D", "", head) or 0),
        _re.sub(r"\d", "", tail),
        int(_re.sub(r"\D", "", tail) or 0),
    )


def _delete_plan(dual: dict[str, Any], deleted: tuple[int, ...]) -> M.MaterializePlan:
    """走**真实** `MaterializePlan`，不用鸭子对象 —— 字段缺失要在类型上暴露。"""
    region = dual["region_main"]
    return M.MaterializePlan(
        sheet_part=dual["sheet_part"],
        sheet_name=region.sheet_name,
        writes=(),
        preserved_formulas={},
        dynamic_column_columns={},
        table_part=dual["main_part"],
        stale_deleted=tuple(sorted(deleted)),
        # 与生产一致：`plan_managed_writes` 恒设 `managed_table_name=binding.table_name`。
        managed_table_name=SIB.A.TABLE_NAME_MAIN,
        managed_sheet_key=None,
        row_deletion=RowDeletionShift(
            deleted_rows=tuple(deleted),
            region_first_row=region.first_row,
            region_last_row=region.last_row,
        ),
    )


def _apply_delete(dual: dict[str, Any], deleted: tuple[int, ...]) -> bytes:
    plan = _delete_plan(dual, deleted)
    product, _report = M.apply_plan_zip_with_report(dual["bytes"], plan)
    return product


def _entries_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 7：兄弟 Table `ref` 收缩
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty7SiblingRefShrinks:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 7: 兄弟 Table `ref` 收缩**

    **Validates: Requirements 2.1, 2.2, 2.4**
    """

    def test_fixture_is_non_degenerate(self, dual: dict[str, Any]) -> None:
        """🔴 先证明 other 区**在 main 区下方** —— 否则「收缩」判据恒真空转。"""
        main = _split_ref(_ref_of(dual["entries"], dual["main_part"]))
        other = _split_ref(_ref_of(dual["entries"], dual["other_part"]))
        assert other[1] > main[3], (
            f"other 区首行 {other[1]} 不在 main 区末行 {main[3]} 之下 —— "
            "这份 fixture 上删 main 区的行不会推动 other 区，判据无区分力"
        )

    @PBT
    @given(offset=st.integers(min_value=0, max_value=3))
    def test_sibling_head_and_tail_both_follow_the_carrier(
        self, dual: dict[str, Any], offset: int
    ) -> None:
        """① 首行与末行**各自**等于位移载体对其的映射（兄弟表首尾都要动）。"""
        region = dual["region_main"]
        row = min(region.first_row + offset, region.last_row)
        before = _split_ref(_ref_of(dual["entries"], dual["other_part"]))
        product = _apply_delete(dual, (row,))
        after = _split_ref(_ref_of(_entries_of(product), dual["other_part"]))
        shift = RowDeletionShift(
            deleted_rows=(row,),
            region_first_row=region.first_row,
            region_last_row=region.last_row,
        )
        assert after[1] == shift.shift_range_start(before[1]), (
            f"删 r={row}：other 首行 {before[1]}→{after[1]}，"
            f"载体给 {shift.shift_range_start(before[1])}"
        )
        assert after[3] == shift.shift_range_end(before[3]), (
            f"删 r={row}：other 末行 {before[3]}→{after[3]}，"
            f"载体给 {shift.shift_range_end(before[3])}"
        )
        # 🔴 首尾都动 —— 与本表（首行一律不动）相反。这条钉死「不是只缩末行」。
        assert after[1] != before[1] and after[3] != before[3], (
            f"other 区整块在删除点下方，首尾都该上移，实得 {before} → {after}"
        )

    @PBT
    @given(offset=st.integers(min_value=0, max_value=3))
    def test_column_span_is_verbatim(self, dual: dict[str, Any], offset: int) -> None:
        """② 列跨度逐字保留 —— 只改行分量。"""
        region = dual["region_main"]
        row = min(region.first_row + offset, region.last_row)
        before = _split_ref(_ref_of(dual["entries"], dual["other_part"]))
        after = _split_ref(_ref_of(_entries_of(_apply_delete(dual, (row,))), dual["other_part"]))
        assert (after[0], after[2]) == (before[0], before[2]), (
            f"列跨度被改了：{before[0]}..{before[2]} → {after[0]}..{after[2]}"
        )

    def test_sibling_entirely_above_is_verbatim_and_does_not_raise(
        self, dual: dict[str, Any]
    ) -> None:
        """③ 兄弟表完全位于被删行**之上** ⇒ 逐字不变且**不抛**。

        判据形态：把 main / other 的角色互换 —— 删 **other** 区的行，
        此时 main 区整块在删除点之上，它的 `ref` 一个字都不该动。
        与 `_shift_sibling_table_refs` 同纪律（那里 0 处改动也不抛）。
        """
        region_other = dual["region_other"]
        row = region_other.first_row + 1
        plan = M.MaterializePlan(
            sheet_part=dual["sheet_part"],
            sheet_name=region_other.sheet_name,
            writes=(),
            preserved_formulas={},
            dynamic_column_columns={},
            table_part=dual["other_part"],
            stale_deleted=(row,),
            managed_table_name=SIB.A.TABLE_NAME_OTHER,
            row_deletion=RowDeletionShift(
                deleted_rows=(row,),
                region_first_row=region_other.first_row,
                region_last_row=region_other.last_row,
            ),
        )
        product, _ = M.apply_plan_zip_with_report(dual["bytes"], plan)
        out = _entries_of(product)
        assert _ref_of(out, dual["main_part"]) == _ref_of(
            dual["entries"], dual["main_part"]
        ), "main 区在删除点之上却被改动了"
        # other 自己（本表）必须缩
        assert _ref_of(out, dual["other_part"]) != _ref_of(
            dual["entries"], dual["other_part"]
        ), "本表 ref 没缩 ⇒ 这条判据在观测一个什么都没做的调用"

    def test_non_contiguous_deletion_shrinks_by_the_right_amount(
        self, dual: dict[str, Any]
    ) -> None:
        """非连续删除：兄弟区上移量 == 它上方的被删行数（不是 `count` 也不是 1）。"""
        region = dual["region_main"]
        rows = tuple(
            r
            for r in (region.first_row, region.first_row + 2)
            if region.first_row <= r <= region.last_row
        )
        assert len(rows) == 2, f"main 区太窄，造不出非连续删除：{region}"
        before = _split_ref(_ref_of(dual["entries"], dual["other_part"]))
        after = _split_ref(_ref_of(_entries_of(_apply_delete(dual, rows)), dual["other_part"]))
        assert (after[1], after[3]) == (before[1] - 2, before[3] - 2), (
            f"删 {list(rows)}（2 行）后 other 区应整体上移 2，实得 {before} → {after}"
        )

    def test_shared_ref_pattern_is_one_constant(self) -> None:
        """🔴 结构锁：四个 ref 改写器共用**同一个** `ref=` 匹配常量。

        各写一份字面量时，任何一处的形态收窄只会让那一处漏掉宽表，
        而症状落在很远的地方（反读空 UUID → 重新 mint → extra），归因极难。
        """
        import ast
        import inspect
        import textwrap

        src = (
            _BACKEND / "app/services/workpaper_sync/excel_materialize.py"
        ).read_bytes().decode("utf-8")
        # 模块内不得再有第二份 `ref=` 的字面量正则
        inline = [
            node
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and r'(?P<prefix>\bref=")' in node.value
        ]
        assert len(inline) == 1, (
            f"`ref=` 正则字面量现算 {len(inline)} 处，应恰好 1 处（模块级常量）"
        )
        for fn in (
            M._shift_sibling_table_refs,
            M._grow_managed_table_ref,
            M._shrink_managed_table_ref,
            M._shrink_sibling_table_refs,
        ):
            body = textwrap.dedent(inspect.getsource(fn))
            assert "_rewrite_table_ref_rows" in body or "_TABLE_REF_RE" in body, (
                f"{fn.__name__} 没走共用的 ref 改写入口"
            )

    def test_sibling_parts_come_from_worksheet_rels(self) -> None:
        """🔴 走 `_sheet_table_parts`（worksheet rels），不扫 `xl/tables/*` 猜归属。

        Table part 里**没有**所属 sheet 的信息，sheet→table 的唯一权威关联就是
        worksheet 的 `<tableParts>` / rels。

        🔴 判据用 **AST 排除 docstring**，不用文本 `in`：本函数的 docstring 里就写着
        「不扫 `xl/tables/*`」这句**反例**，文本匹配会把解释当成违规
        （首版正是这样自己把自己判红的）。docstring 是 `Expr(Constant)`，
        排掉它之后剩下的字符串常量才是真的代码字面量。
        """
        import ast
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._shrink_sibling_table_refs))
        tree = ast.parse(src)
        fn = tree.body[0]
        assert isinstance(fn, ast.FunctionDef)
        docstring_node = (
            fn.body[0].value
            if fn.body
            and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)
            else None
        )
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
        }
        assert "_sheet_table_parts" in called, sorted(c for c in called if c)
        offenders = [
            node.value
            for node in ast.walk(fn)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node is not docstring_node
            and "xl/tables/" in node.value
        ]
        assert not offenders, f"代码字面量里在猜 Table 归属：{offenders}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 8：收缩后零身份 mint（G2 症状链的第 ②③④ 环）
# ═══════════════════════════════════════════════════════════════════════════


def _uuid_by_row(
    entries: Mapping[str, bytes], *, sheet_part: str, column: str, rows: range
) -> dict[int, str]:
    """`{行号: UUID 列原始值}` —— 与 `excel_extract` 建 `raw_by_row` 同口径。

    用 `SheetCellIndex` 这条**生产**入口读格，不自己写第二份单元格正则。
    """
    xml = entries[sheet_part].decode("utf-8")
    index = M.build_sheet_cell_index(xml)
    shared = M._shared_strings(entries)
    out: dict[int, str] = {}
    for row in rows:
        view = index.view(f"{column}{row}")
        if view is None:
            out[row] = ""
            continue
        text = _cell_text(view, shared)
        out[row] = text
    return out


def _cell_text(view: Any, shared: list[str]) -> str:
    """一格的显示文本（inlineStr / sharedString / 裸 `<v>` 三态）。"""
    import re as _re

    raw = view.raw
    if 't="s"' in (view.attrs or ""):
        found = _re.search(r"<v>(\d+)</v>", raw)
        if found is not None:
            idx = int(found.group(1))
            return shared[idx] if 0 <= idx < len(shared) else ""
        return ""
    inline = _re.findall(r"<t[^>]*>(.*?)</t>", raw, _re.S)
    if inline:
        return "".join(inline)
    found = _re.search(r"<v>(.*?)</v>", raw, _re.S)
    return found.group(1) if found else ""


def _other_table_spec(dual: dict[str, Any]) -> Any:
    """契约里 other 区那张 `TableSpec`（`_scan_row_identities` 要它定 delete_policy）。"""
    for sheet in dual["contract"].sheets:
        for table in sheet.tables:
            if table.table_key == SIB.A.ROWS_TABLE_KEY_OTHER:
                return table
    raise AssertionError(
        f"契约里找不到 other 区 table_key={SIB.A.ROWS_TABLE_KEY_OTHER}"
    )


def _scan_other_region(dual: dict[str, Any], product: bytes) -> Any:
    """在**删行后的产物**上按 other 区的 `ref` 反读身份 —— G2 链的 ②③④ 环。"""
    entries = _entries_of(product)
    with zipfile.ZipFile(io.BytesIO(product)) as zf:
        region = EE.resolve_managed_region(
            zf, contract=dual["contract"], binding=SIB.BINDING_OTHER
        )
    raw_by_row = _uuid_by_row(
        entries,
        sheet_part=region.sheet_part,
        column=SIB.A.UUID_COL_OTHER,
        rows=range(region.first_row, region.last_row + 1),
    )
    import hashlib

    return region, raw_by_row, EE._scan_row_identities(
        table=_other_table_spec(dual),
        sheet_name=region.sheet_name,
        uuid_column=SIB.A.UUID_COL_OTHER,
        raw_by_row=raw_by_row,
        artifact_sha256=hashlib.sha256(product).hexdigest(),
        tombstoned=(),
    )


class TestProperty8NoIdentityMintAfterShrink:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 8: 收缩后零身份 mint**

    **Validates: Requirement 2.5**

    🔴 这是 G2 实测症状链的 ②③④ 环，**必须与①同一条测试链上**断言：
    ①兄弟 ref 未收缩 → ②region.row_span 尾部多一行 → ③该行 uuid 为空 →
    ④`_scan_row_identities` 按 tombstone 策略 mint `GTROW-MINTED-*`。
    """

    def test_delete_policy_is_tombstone_so_the_chain_is_reachable(
        self, dual: dict[str, Any]
    ) -> None:
        """🔴 前提实测：other 区的 `delete_policy` 必须是 tombstone。

        不是 tombstone 的话空 UUID 行走 `empty_rows` 而不 mint ⇒ ④环不可达 ⇒
        Property 8 在这份 fixture 上恒真。B11 现算 139/153 个 table 都是 tombstone，
        但**这一张**必须实测。
        """
        disposition = EE.classify_empty_row_identity(_other_table_spec(dual))
        assert disposition is EE.EmptyRowIdentityDisposition.assign_new_id, (
            f"other 区处置是 {disposition} 而非 assign_new_id ⇒ mint 分支不可达，"
            "Property 8 在这份 fixture 上恒真，须换一张 table 作靶子"
        )

    @PBT
    @given(offset=st.integers(min_value=0, max_value=3))
    def test_zero_mint_after_sibling_shrink(
        self, dual: dict[str, Any], offset: int
    ) -> None:
        region_main = dual["region_main"]
        row = min(region_main.first_row + offset, region_main.last_row)
        product = _apply_delete(dual, (row,))
        _region, raw_by_row, scan = _scan_other_region(dual, product)
        assert scan.minted_by_row == {}, (
            f"删 main 区 r={row} 后 other 区 mint 出了新身份 {scan.minted_by_row} —— "
            f"兄弟 ref 没跟着收缩，尾部读到空 UUID（raw={raw_by_row}）"
        )
        assert scan.empty_rows == (), f"other 区出现空 UUID 行：{scan.empty_rows}"

    def test_mutation_short_circuit_sibling_shrink_reds_this_property(
        self, dual: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 变异反证：进程内短路兄弟收缩 ⇒ 上一条的断言**必须打红**。

        用 `monkeypatch` 在**进程内**制造「修复前」态，**不改磁盘生产文件**
        （归档 README 教训 6：变异 harness 自身会假绿 —— 还原动作被跳过后
        把已变异文件当 pristine 快照）。
        """
        region_main = dual["region_main"]
        row = region_main.first_row

        def _noop(
            entries: dict[str, bytes], *, plan: Any, own_part: str
        ) -> tuple[dict[str, bytes], int]:
            return entries, 0

        monkeypatch.setattr(M, "_shrink_sibling_table_refs", _noop)
        product = _apply_delete(dual, (row,))
        _region, raw_by_row, scan = _scan_other_region(dual, product)
        assert scan.minted_by_row or scan.empty_rows, (
            "短路兄弟收缩后 other 区**仍然**没有空 UUID 行 —— "
            f"Property 8 没有区分力（raw={raw_by_row}）"
        )
        # ① 环：ref 真的没收缩
        assert _ref_of(_entries_of(product), dual["other_part"]) == _ref_of(
            dual["entries"], dual["other_part"]
        ), "变异没生效（ref 仍被收缩了）⇒ 这条反证在观测别的东西"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 覆盖面普查（Requirements 2.7 / 2.8）—— 分母**现算**，禁写死
# ═══════════════════════════════════════════════════════════════════════════

#: 现算的 specs 口径多区 sheet 清单（`managed_sheet → [spec, …]`，按首数据行升序）。
_SPEC_CENSUS: dict[str, list[Any]] = SIB._multi_region_sheets()

#: 参数化对象 = 现算清单 − 已知在 instrumentation 阶段就坏掉的（与本 spec 无关）。
_CENSUS_SHEETS: tuple[str, ...] = tuple(
    sorted(s for s in _SPEC_CENSUS if s not in KNOWN_BROKEN_AT_INSTRUMENTATION)
)

#: design「§ 现算基线」B8 的 18 组（storage 口径）按循环前缀归类后的 `displayName` 前缀。
#: 🔴 只用于**对账差集**，不作参数化源。
_B8_TABLE_PREFIXES: frozenset[str] = frozenset(
    {
        "GT_D113", "GT_D115", "GT_D116", "GT_D14", "GT_D17", "GT_D18",
        "GT_D23", "GT_D34", "GT_D37",
        "GT_D41", "GT_D420", "GT_D434", "GT_D436", "GT_D49",
        "GT_D66", "GT_D69", "GT_D74", "GT_D77",
    }
)


def test_census_denominator_is_computed_not_hardcoded() -> None:
    """🔴 参数条数 == 现算组数（**禁写死 18**）。"""
    assert len(_CENSUS_SHEETS) == len(_SPEC_CENSUS) - len(
        KNOWN_BROKEN_AT_INSTRUMENTATION & set(_SPEC_CENSUS)
    ), (
        f"参数条数 {len(_CENSUS_SHEETS)} ≠ 现算组数 {len(_SPEC_CENSUS)} − 已知坏 "
        f"{len(KNOWN_BROKEN_AT_INSTRUMENTATION & set(_SPEC_CENSUS))}"
    )
    assert _CENSUS_SHEETS, "现算清单为空 ⇒ 参数化空转"


def test_known_broken_list_is_falsifiable() -> None:
    """🔴 豁免名单必配反向断言：名单里的每一项**真的**在 instrumentation 阶段就坏。

    只存名字的名单是「加一行就变绿」的后门。这条让名单可被伪证：
    某项被修好之后本判据打红，逼人把它从名单里拿掉（而不是让它永久豁免）。
    """
    assert KNOWN_BROKEN_AT_INSTRUMENTATION <= set(_SPEC_CENSUS), (
        f"名单里有不在现算清单里的条目（已失效）："
        f"{sorted(KNOWN_BROKEN_AT_INSTRUMENTATION - set(_SPEC_CENSUS))}"
    )
    for sheet in sorted(KNOWN_BROKEN_AT_INSTRUMENTATION):
        with pytest.raises(Exception) as err:
            SIB._instrumented_bytes_for_provider(SIB._provider_of_sheet(sheet))
        assert "InstrumentationError" in type(err.value).__name__ or "Typography" in str(
            type(err.value)
        ), (
            f"{sheet} 现在能 instrument 了（或坏的原因变了：{type(err.value).__name__}）"
            " —— 请从 KNOWN_BROKEN_AT_INSTRUMENTATION 里拿掉它并纳入参数化"
        )


def test_two_census_differ_and_the_gap_is_registered() -> None:
    """🔴 B8（storage 口径）与 specs 口径**都是 18 但不是同一个集合**。

    断言「参数条数 == 18」会恰好为真却覆盖另一个集合 —— 这条把差集显式登记下来，
    让缺口可见。
    """
    spec_prefixes = {
        str(getattr(spec, "table_name", "")).rsplit("_", 1)[0]
        for specs in _SPEC_CENSUS.values()
        for spec in specs
    }
    # storage 有而 specs 没有的循环（历史产物里存在、当前 provider 不再声明）
    b8_only = sorted(
        p for p in _B8_TABLE_PREFIXES if not any(q.startswith(p) for q in spec_prefixes)
    )
    assert b8_only, (
        "两个口径的差集为空 ⇒ 要么某一侧的清单过期了，要么本判据的前缀比对写错了；"
        f"spec 前缀现算 {sorted(spec_prefixes)[:8]}…"
    )
    # 登记（不断言具体成员，避免把快照写死）：差集非空这件事本身就是结论
    assert len(b8_only) <= len(_B8_TABLE_PREFIXES), b8_only


@pytest.mark.parametrize("sheet_name", _CENSUS_SHEETS)
def test_every_multi_region_sheet_shrinks_its_sibling_refs(sheet_name: str) -> None:
    """对每张同 sheet 多受管区底稿：删**最上区**一行 ⇒ 其下方每个兄弟区 ref 整体上移 1。

    🔴 不依赖 per-provider 契约：直接从 worksheet rels 取同 sheet 的 Table 清单、
    按首行排序定「最上区」。这样 18 组一次都能跑，而不是只跑有契约 fixture 的那几组。
    """
    data = SIB._instrumented_bytes_for_provider(SIB._provider_of_sheet(sheet_name))
    entries = _entries_of(data)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheet_part = EE._sheet_parts(zf).get(sheet_name)
    assert sheet_part, f"定位不到受管 sheet part：{sheet_name}"

    parts = [p for p in M._sheet_table_parts(entries, sheet_part=sheet_part) if p in entries]
    refs = {p: _split_ref(_ref_of(entries, p)) for p in parts}
    assert len(refs) >= 2, f"{sheet_name} 现算只有 {len(refs)} 个 Table ⇒ 不是多区"
    ordered = sorted(refs, key=lambda p: refs[p][1])

    # 🔴 删的那一行必须是**真能删**的：受管 sheet 自己的裸**单格**引用指着它时，删完即
    # `#REF!`，生产的计划期 `find_bare_dangling_rows` 会（正确地）拒绝。本普查只验 A1
    # （兄弟 Table ref 收缩），不该去挑战一个本来就该被拒的删除 ⇒ 用**生产的检测函数**
    # 现算（不在测试里手抄第二份口径）自末行向上找。
    #
    # 而「最上区」也不一定有可删行：D3-4 的 `B17` 写成 `B11-B13-B14-B15-B16`（逐行相减
    # 而非 SUM），把它上面那个区的每一行都钉死了。所以自上而下取**第一个有可删行的区**，
    # 并把断言拆成三段：本区收缩 / 其**上方**各区逐字不变 / 其**下方**各区整体上移。
    # 这比原来「只验最上区」覆盖更宽（多了「上方不动」这一侧）。
    sheet_xml = entries[sheet_part].decode("utf-8")
    target: str | None = None
    row: int | None = None
    blocked: dict[str, dict[int, tuple]] = {}
    for part in ordered:
        head, tail = refs[part][1], refs[part][3]
        if tail <= head:
            blocked[part] = {}
            continue
        per_row: dict[int, tuple] = {}
        for candidate in range(tail, head - 1, -1):
            dangling = N1.find_bare_dangling_rows(sheet_xml, deleted_rows=(candidate,))
            if not dangling:
                target, row = part, candidate
                break
            per_row[candidate] = dangling
        if target is not None:
            break
        blocked[part] = per_row
    assert target is not None and row is not None, (
        f"{sheet_name} 每个受管区的每一行都被裸单格引用指着（或只有一行）⇒ 整张表不可删："
        f"{ {p: {k: v[:1] for k, v in d.items()} for p, d in blocked.items()} }"
    )
    idx = ordered.index(target)
    uppers, lowers = ordered[:idx], ordered[idx + 1 :]
    top, top_head, top_tail = target, refs[target][1], refs[target][3]
    # 🔴 `managed_table_name` **必须给**：生产的 `plan_managed_writes` 恒设它
    #    （`binding.table_name`），`_refresh_gt_sync_runtime_binding` 靠它经
    #    `GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS` 平行清册定位本区的 per-template footer 键。
    #    不给会落到「managed_tid is None」的 fallback 上 ⇒ 把 **primary sheet** 的
    #    workbook 全局键当成本趟的（实测 D1-8：`GT_FOOTER_ROW=21` 其实是 D1-3 的 footer，
    #    而 D1-8 最上区末行也是 21 ⇒ 数值相撞、当场 fail-closed）。
    top_table_name = _display_name_of(entries, top)
    plan = M.MaterializePlan(
        sheet_part=sheet_part,
        sheet_name=sheet_name,
        writes=(),
        preserved_formulas={},
        dynamic_column_columns={},
        table_part=top,
        stale_deleted=(row,),
        managed_table_name=top_table_name,
        row_deletion=RowDeletionShift(
            deleted_rows=(row,),
            region_first_row=top_head,
            region_last_row=top_tail,
        ),
    )
    product, _ = M.apply_plan_zip_with_report(data, plan)
    out = _entries_of(product)

    after_top = _split_ref(_ref_of(out, top))
    assert (after_top[1], after_top[3]) == (top_head, top_tail - 1), (
        f"{sheet_name} 本区 ref 应缩成 {top_head}:{top_tail - 1}，实得 {after_top}"
    )
    for part in uppers:
        assert _split_ref(_ref_of(out, part)) == refs[part], (
            f"{sheet_name} 被删行**上方**的区 {part} 动了：{refs[part]} → "
            f"{_split_ref(_ref_of(out, part))}（上方的行号不受下方删除影响）"
        )
    for part in lowers:
        before = refs[part]
        after = _split_ref(_ref_of(out, part))
        assert (after[1], after[3]) == (before[1] - 1, before[3] - 1), (
            f"{sheet_name} 兄弟区 {part} 应整体上移 1："
            f"{before[1]}:{before[3]} → 实得 {after[1]}:{after[3]}"
        )
        assert (after[0], after[2]) == (before[0], before[2]), (
            f"{sheet_name} 兄弟区 {part} 列跨度被改了"
        )


def test_mutation_hardcoded_single_sheet_would_miss_the_others() -> None:
    """🔴 变异反证：把参数化改回「只跑 D4-1」⇒ 必漏其余组。

    钉住参数化本身没有退化 —— 不靠人工承诺。
    """
    hardcoded = {"营业收入审定表D4-1"}
    missed = sorted(set(_CENSUS_SHEETS) - hardcoded)
    assert len(missed) >= 10, (
        f"只跑 D4-1 会漏掉 {len(missed)} 组 —— 若这个数变得很小，说明现算清单缩水了："
        f"{missed}"
    )
