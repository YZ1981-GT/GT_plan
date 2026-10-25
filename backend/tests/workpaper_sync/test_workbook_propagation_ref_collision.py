# -*- coding: utf-8 -*-
"""Task 10 第 3a 段 —— apply 侧引用改写碰撞 + verify before-digest 缓存键。

spec: d3-sync-coverage-via-row-table-engine · Task 10 · Requirements 2.2, 2.4

═══ 钉住什么 ═══

1. **apply 纯函数**（`excel_materialize._apply_workbook_propagation`）：同一趟里一条声明的
   before 恰是别的声明 after 的前缀 / 与之逐字相等时，旧的逐条 `str.replace` 会扫到替换
   产物（D3-4 段①插 3 行 / 插 8 行两类真实碰撞）；现实现是每 part 一次同时替换 + token 边界。
   另钉住边界不误阻断的三种写法（`'S'!A1:'S'!B2`、`A1#`、`&apos;` 形态）。
2. **变异反证**：同一组判据换成旧实现的局部复刻跑一遍，碰撞类必须打红。
3. **D3-4 真实 adapter**：段①单趟插 3/5/8 行（4/6 行对照）materialize 不抛
   `PropagationDriftError`，workbook.xml 里指向 D3-4 的 definedName 逐条 = 模板值按插入点平移。
   verify 等价性不在这里断言（verify 侧的同类碰撞留给 3b）。
4. **before-digest 缓存键**（`excel_extract.verify_unmanaged_regions`）：同一进程、同一 base，
   先 verify (4,0) 再 verify (4,5) 两次都等价；键里去掉 region 几何的变异必须打红。
"""
from __future__ import annotations

import html
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync import parse_cache as PC  # noqa: E402
from app.services.workpaper_sync import phase5_d3_04_analysis as D304  # noqa: E402
from app.services.workpaper_sync import phase5_d3_expansion as P  # noqa: E402
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as ENTRY  # noqa: E402
from app.services.workpaper_sync.adapters.base import UnmanagedRegionDriftError  # noqa: E402

_MANAGED_PART = "xl/worksheets/sheet1.xml"
_WB = "xl/workbook.xml"
_REF_SHEET = "xl/worksheets/sheet2.xml"
#: D3-4 受管 sheet 名的引用前缀（裸单引号口径 = 计划期 `_unescape` 之后的形态）。
_Q = f"'{D304.MANAGED_SHEET_D304}'!"
UPPER = D304.SPEC_D304_DEBIT  # 段①：借方（数据区 13-15，footer 17）
LOWER = D304.SPEC_D304_CREDIT  # 段②：贷方（数据区 22-23，footer 25）
#: 段①插行点 = 段①末数据行 + 1（premise 判据核对）。
_D34_INSERT_AT = 16


# ═══════════════════════════════════════════════════════════════════════════
# 1. apply 纯函数判据
# ═══════════════════════════════════════════════════════════════════════════


def _bare_plan(**overrides: Any) -> M.MaterializePlan:
    """最小 `MaterializePlan`（照抄 `test_workbook_row_change_wiring._bare_plan`）。"""
    kwargs: dict[str, Any] = {
        "sheet_part": _MANAGED_PART,
        "sheet_name": "受管表",
        "writes": (),
        "preserved_formulas": {},
        "dynamic_column_columns": {},
    }
    kwargs.update(overrides)
    return M.MaterializePlan(**kwargs)


@dataclass(frozen=True)
class _Case:
    """一趟、一个 part 的声明 + 原文 + 期望产物。

    `decls` = `(ref_before, ref_after, row_before)`；`row_after = row_before + count`
    （`WorkbookRowChangePlan._validate_propagations` 要求每条增量都等于 `count`）。
    `legacy_red` = 旧的逐条 `str.replace` 在这条上是否打红（变异反证的期望）。
    """

    id: str
    part: str
    count: int
    decls: tuple[tuple[str, str, int], ...]
    text: str
    expected: str
    legacy_red: bool

    def plan(self) -> M.MaterializePlan:
        carrier = "defined_name" if self.part == _WB else "formula"
        change = N1.WorkbookRowChangePlan(
            kind=N1.RowChangeKind.INSERT,
            managed_sheet_name="受管表",
            managed_sheet_part=_MANAGED_PART,
            at=13,
            count=self.count,
            style_from=12,
            region_first_row=13,
            region_last_row=15,
            propagations=tuple(
                N1.PropagationEntry(
                    carrier=carrier,
                    part=self.part,
                    locator=f"L{index}#0",
                    ref_before=before,
                    ref_after=after,
                    row_before=row,
                    row_after=row + self.count,
                )
                for index, (before, after, row) in enumerate(self.decls)
            ),
        )
        return _bare_plan(workbook_row_change=change)

    def entries(self) -> dict[str, bytes]:
        return {_MANAGED_PART: b"<x/>", self.part: self.text.encode("utf-8")}


def _names_xml(names: list[tuple[str, str]], *, apos: bool = False) -> str:
    """definedNames 片段。`apos=True` 时单引号按真实 OOXML 序列化成 `&apos;`。"""
    body = "".join(
        f'<definedName name="{name}">'
        f"{value.replace(chr(39), '&apos;') if apos else value}</definedName>"
        for name, value in names
    )
    return f"<definedNames>{body}</definedNames>"


#: D3-4 模板 workbook.xml 里**指向 D3-4 sheet** 的全部 definedName（探针实测，§10.3；
#: `test_premise_template_defined_names_match_the_synthetic_table` 对真实模板逐条核对）。
_D34_TEMPLATE_NAMES: tuple[tuple[str, str], ...] = (
    ("_xlnm.Print_Area", f"{_Q}$A$1:$H$39"),
    ("GT_MANAGED_REGION_D34DEBIT", f"{_Q}$A$13:$D$15"),
    ("GT_FOOTER_ANCHOR_D34DEBIT", f"{_Q}$A$17"),
    ("GT_ROW_UUID_RANGE_D34DEBIT", f"{_Q}$J$13:$J$15"),
    ("GT_MANAGED_REGION_D34CREDIT", f"{_Q}$A$22:$D$23"),
    ("GT_FOOTER_ANCHOR_D34CREDIT", f"{_Q}$A$25"),
    ("GT_ROW_UUID_RANGE_D34CREDIT", f"{_Q}$K$22:$K$23"),
)


def _shift_rows(value: str, *, at: int, count: int) -> str:
    """测试侧**独立**的行号平移 oracle：`$n` 且 `n >= at` 的行号加 `count`。

    只处理本文件用到的 `$A$n` 绝对形态，刻意不调生产改写器（否则判据自证）。
    """
    return re.sub(
        r"\$(\d+)",
        lambda hit: f"${int(hit.group(1)) + count if int(hit.group(1)) >= at else hit.group(1)}",
        value,
    )


def _d34_case(case_id: str, k: int, *, apos: bool, legacy_red: bool) -> _Case:
    """D3-4 段①单趟插 k 行时 workbook.xml 那一趟的真实声明（顺序 = 计划期扫描顺序）。"""
    decls = tuple(
        (value, _shift_rows(value, at=_D34_INSERT_AT, count=k), row)
        for value, row in (
            (f"{_Q}$A$1:$H$39", 39),
            (f"{_Q}$A$17", 17),
            (f"{_Q}$A$22:$D$23", 22),
            (f"{_Q}$A$25", 25),
            (f"{_Q}$K$22:$K$23", 22),
        )
    )
    after_names = [
        (n, _shift_rows(v, at=_D34_INSERT_AT, count=k)) for n, v in _D34_TEMPLATE_NAMES
    ]
    return _Case(
        id=case_id,
        part=_WB,
        count=k,
        decls=decls,
        text=_names_xml(list(_D34_TEMPLATE_NAMES), apos=apos),
        expected=_names_xml(after_names, apos=apos),
        legacy_red=legacy_red,
    )


_CASES: tuple[_Case, ...] = (
    # ── 碰撞类：旧实现扫到前面条目的替换产物 ──────────────────────────────
    _Case(  # D3-4 段①插 3 行的机理，最小化：区间先改出 `$A$25:$D$26`，footer 的 `$A$25` 命中其前缀
        "prefix_before_inside_earlier_product", _WB, 3,
        (("X!$A$22:$D$23", "X!$A$25:$D$26", 22), ("X!$A$25", "X!$A$28", 25)),
        _names_xml([("R", "X!$A$22:$D$23"), ("F", "X!$A$25")]),
        _names_xml([("R", "X!$A$25:$D$26"), ("F", "X!$A$28")]),
        legacy_red=True,
    ),
    _Case(  # 两条 before 本身是前缀关系：旧实现靠「长的先替换」躲过，新实现靠右边界 `:$D`
        "prefix_before_inside_longer_before", _WB, 3,
        (("X!$A$22:$D$23", "X!$A$25:$D$26", 22), ("X!$A$22", "X!$A$25", 22)),
        _names_xml([("R", "X!$A$22:$D$23"), ("F", "X!$A$22")]),
        _names_xml([("R", "X!$A$25:$D$26"), ("F", "X!$A$25")]),
        legacy_red=False,
    ),
    _Case(  # 数字右边界：`'S'!A25` 先改成 `'S'!A26`，`'S'!A2` 又命中它的前缀
        "digit_boundary_prefix_inside_earlier_product", _REF_SHEET, 1,
        (("'S'!A2", "'S'!A3", 2), ("'S'!A25", "'S'!A26", 25)),
        "<f>'S'!A2+'S'!A25</f>",
        "<f>'S'!A3+'S'!A26</f>",
        legacy_red=True,
    ),
    _Case(  # D3-4 段①插 8 行的机理，最小化：同趟同长，前者产物与后者 before 逐字相等
        "whole_token_equal_to_earlier_product", _WB, 8,
        (("X!$A$17", "X!$A$25", 17), ("X!$A$25", "X!$A$33", 25)),
        _names_xml([("D", "X!$A$17"), ("C", "X!$A$25")]),
        _names_xml([("D", "X!$A$25"), ("C", "X!$A$33")]),
        legacy_red=True,
    ),
    # ── D3-4 真实 definedName 全集（`&apos;` 序列化形态），段①单趟插 k 行 ──────
    _d34_case("d34_k3_apos_prefix_collision", 3, apos=True, legacy_red=True),
    _d34_case("d34_k5_apos_no_apply_collision", 5, apos=True, legacy_red=False),
    _d34_case("d34_k8_apos_equal_collision", 8, apos=True, legacy_red=True),
    # ── 边界：该挡的挡住 ────────────────────────────────────────────────
    _Case(  # 左边界：`XS!A20`（别的 sheet）与 `[1]S!A20`（外部工作簿）不是 `S!A20`
        "left_boundary_longer_sheet_name_and_external_book", _REF_SHEET, 1,
        (("S!A20", "S!A21", 20),),
        "<f>S!A20+XS!A20+[1]S!A20</f>",
        "<f>S!A21+XS!A20+[1]S!A20</f>",
        legacy_red=True,
    ),
    # 右边界：扫描器 / 改写器都逐字跳过字符串字面量，所以字面量里的引用不进声明；
    # apply 是文本级替换，只能靠 token 边界不去碰字面量里「更长的那个 token」。
    _Case(  # 数字阻断：`'S'!A2` 不是 `'S'!A25` 的一部分
        "right_boundary_digit_blocks_longer_row", _REF_SHEET, 1,
        (("'S'!A2", "'S'!A3", 2),),
        "<f>'S'!A2+INDIRECT(\"'S'!A25\")</f>",
        "<f>'S'!A3+INDIRECT(\"'S'!A25\")</f>",
        legacy_red=True,
    ),
    _Case(  # `:` 后跟 `$?[A-Za-z0-9]` 阻断：`'S'!$A$22` 不是 `'S'!$A$22:$D$23` 的一部分
        "right_boundary_colon_blocks_range_head", _REF_SHEET, 3,
        (("'S'!$A$22", "'S'!$A$25", 22),),
        "<f>'S'!$A$22+INDIRECT(\"'S'!$A$22:$D$23\")</f>",
        "<f>'S'!$A$25+INDIRECT(\"'S'!$A$22:$D$23\")</f>",
        legacy_red=True,
    ),
    # ── 边界：不该挡的不挡（阻断 ⇒ 少替换 ⇒ fail closed 回归）──────────────
    _Case(  # 扫描器把 `'S'!A20:'S'!B30` 拆成两条声明；`:` 后跟引号不阻断
        "colon_then_quote_is_not_a_range_tail", _REF_SHEET, 1,
        (("'S'!A20", "'S'!A21", 20), ("'S'!B30", "'S'!B31", 30)),
        "<f>SUM('S'!A20:'S'!B30)</f>",
        "<f>SUM('S'!A21:'S'!B31)</f>",
        legacy_red=False,
    ),
    _Case(  # 同上，`&apos;` 序列化：`:` 后跟 `&` 不阻断
        "colon_then_apos_is_not_a_range_tail", _WB, 1,
        (("'S'!$A$20", "'S'!$A$21", 20), ("'S'!$B$30", "'S'!$B$31", 30)),
        _names_xml([("N", "'S'!$A$20:'S'!$B$30")], apos=True),
        _names_xml([("N", "'S'!$A$21:'S'!$B$31")], apos=True),
        legacy_red=False,
    ),
    _Case(  # `A20#` 是溢出引用，锚格随位移 ⇒ `#` 不阻断
        "spill_reference_hash_is_not_blocked", _REF_SHEET, 1,
        (("'S'!A20", "'S'!A21", 20),),
        "<f>SUM('S'!A20#)</f>",
        "<f>SUM('S'!A21#)</f>",
        legacy_red=False,
    ),
)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.id)
def test_apply_rewrites_each_declared_reference_exactly_once(case: _Case) -> None:
    """每条声明恰好改一处、产物逐字等于期望；实改数与声明数对账不抛。"""
    out = M._apply_workbook_propagation(case.entries(), plan=case.plan())
    assert out[case.part].decode("utf-8") == case.expected


def test_same_reference_declared_with_two_afters_fails_closed() -> None:
    """同趟同 part 同一命中文本声明成两个 after ⇒ 抛（查表只能取一个，不得替计划裁决）。"""
    case = _Case(
        "conflict", _REF_SHEET, 1,
        (("'S'!A20", "'S'!A21", 20), ("'S'!A20", "'S'!B21", 20)),
        "<f>'S'!A20+'S'!A20</f>",
        "",
        legacy_red=False,
    )
    with pytest.raises(N1.PropagationDriftError, match="两个不同的改后值"):
        M._apply_workbook_propagation(case.entries(), plan=case.plan())


def test_each_before_uses_only_its_first_matching_form() -> None:
    """保留旧语义：同一个 before 的多种转义形态同时出现时，只替换第一个命中的形态。

    `&apos;` 形态排在裸引号之前 ⇒ 裸引号那处不改 ⇒ 实改 1 ≠ 声明 2 ⇒ fail closed。
    （同一 part 里混用两种序列化本身就说明 artifact 被外部改过。）
    """
    case = _Case(
        "mixed_forms", _WB, 1,
        (("'S'!$A$20", "'S'!$A$21", 20), ("'S'!$A$20", "'S'!$A$21", 20)),
        '<definedName name="A">&apos;S&apos;!$A$20</definedName>'
        "<definedName name=\"B\">'S'!$A$20</definedName>",
        "",
        legacy_red=False,
    )
    with pytest.raises(N1.PropagationDriftError, match="声明 2 处传播，实际只改了 1 处"):
        M._apply_workbook_propagation(case.entries(), plan=case.plan())


# ═══════════════════════════════════════════════════════════════════════════
# 2. 变异反证：换回旧的逐条 `str.replace`，碰撞类必须打红
# ═══════════════════════════════════════════════════════════════════════════


def _legacy_apply(entries: dict[str, bytes], *, plan: M.MaterializePlan) -> dict[str, bytes]:
    """修复前 `_apply_workbook_propagation` 的**局部复刻**（替换循环逐字照抄旧实现）。"""
    change = plan.workbook_row_change
    if change is None:
        return entries
    by_part: dict[str, list[Any]] = {}
    for entry in change.propagations:
        by_part.setdefault(entry.part, []).append(entry)
    for part, part_entries in sorted(by_part.items()):
        if part == plan.sheet_part:
            continue
        if part not in entries:
            raise N1.PropagationDriftError(f"计划声明要改 {part}，但它不在 substrate zip 里")
        text = entries[part].decode("utf-8")
        pairs: dict[tuple[str, str], int] = {}
        for entry in part_entries:
            key = (entry.ref_before, entry.ref_after)
            pairs[key] = pairs.get(key, 0) + 1
        applied = 0

        def _apos(s: str) -> str:
            return s.replace("'", "&apos;")

        for before, after in sorted(pairs, key=lambda kv: len(kv[0]), reverse=True):
            for cand_before, cand_after in (
                (_apos(N1._escape(before)), _apos(N1._escape(after))),
                (N1._escape(before), N1._escape(after)),
                (_apos(before), _apos(after)),
                (before, after),
            ):
                hits = text.count(cand_before)
                if hits:
                    text = text.replace(cand_before, cand_after)
                    applied += hits
                    break
        declared = len(part_entries)
        if applied != declared:
            raise N1.PropagationDriftError(
                f"{part}：声明 {declared} 处传播，实际只改了 {applied} 处"
            )
        entries[part] = text.encode("utf-8")
    return entries


def _verdict(apply: Callable[..., dict[str, bytes]], case: _Case) -> bool:
    """判据在给定实现上是否**通过**（产物逐字等于期望且不抛）。"""
    try:
        out = apply(case.entries(), plan=case.plan())
    except N1.PropagationDriftError:
        return False
    return out[case.part].decode("utf-8") == case.expected


def test_mutation_legacy_str_replace_turns_collision_criteria_red() -> None:
    """旧实现上：`legacy_red` 的判据全红、其余全绿；新实现上全绿。

    红的条数 ≥ 2 是任务门槛；逐条对齐 `legacy_red` 是为了让「哪条靠新实现才绿」可读，
    而不是只数个数（数对了但红错了条目同样说明判据没钉住机理）。
    """
    legacy = {case.id: _verdict(_legacy_apply, case) for case in _CASES}
    current = {case.id: _verdict(M._apply_workbook_propagation, case) for case in _CASES}
    red = sorted(case_id for case_id, passed in legacy.items() if not passed)
    assert red == sorted(case.id for case in _CASES if case.legacy_red), legacy
    assert len(red) >= 2, red
    assert all(current.values()), current


# ═══════════════════════════════════════════════════════════════════════════
# 3. D3-4 真实 adapter（照抄 test_d3_04_dual_zone_shift_and_verify 的驱动手法，不改那个文件）
# ═══════════════════════════════════════════════════════════════════════════


def _import_d304_sibling() -> Any:
    """`tests/workpaper_sync` 不是包 ⇒ 临时把目录放进 `sys.path` 取 `_synthetic_definitions`。"""
    here = str(Path(__file__).resolve().parent)
    sys.path.insert(0, here)
    try:
        import test_d3_04_dual_zone_shift_and_verify as sibling
    finally:
        sys.path.remove(here)
    return sibling


@dataclass(frozen=True)
class _D34World:
    adapter: Any
    contract: Any
    base: Path
    tmp: Path

    def materialize(self, n_up: int, n_lo: int, *, tag: str) -> tuple[Any, Path]:
        """段①派生 `n_up` 行、段②派生 `n_lo` 行。

        派生行全是 orphan 身份 ⇒ 每区插行数 = 派生行数（由 `per_table_shift` 逐条核对）。
        """
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        def rows(prefix: str, n: int, amount: float) -> list[dict[str, Any]]:
            return [
                {"rowId": f"{prefix}{i}", "label": f"{prefix}{i}", "amount": amount + i,
                 "source": "tb", "remark": ""}
                for i in range(n)
            ]

        upper = build_store_projection(UPPER, rows("debit-p", n_up, 100.0), contract=self.contract)
        lower = build_store_projection(LOWER, rows("credit-q", n_lo, 200.0), contract=self.contract)
        combined = Projection(
            contract_id=upper.contract_id,
            semantic_version=upper.semantic_version,
            document_type=upper.document_type,
            values={**upper.values, **lower.values},
            row_keys={**upper.row_keys, **lower.row_keys},
        )
        output = self.tmp / ".staging" / f"d304-{tag}-{n_up}-{n_lo}.xlsx"
        output.parent.mkdir(parents=True, exist_ok=True)
        result = self.adapter.materialize(
            substrate=self.base, projection=combined, output=output, contract=self.contract
        )
        return result, output

    def verify(self, result: Any, output: Path) -> Any:
        return self.adapter.verify_unmanaged_regions(
            before=self.base,
            after=output,
            contract=self.contract,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )


@pytest.fixture(scope="module")
def d34(tmp_path_factory: pytest.TempPathFactory) -> _D34World:
    from app.services.excel_structure_fingerprint import identity_inventory
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory

    instrumented = EI.instrument_workbook_bytes_multi(
        ENTRY.read_authoritative_template(),
        P.instrumentation_specs(),
        gate=EI.ExcelIdentityCarrierGate.load(),
    )
    contract = parse_contract(ENTRY.build_contract_payload(), adapter_id=ENTRY.ADAPTER_ID)
    synthetic = _import_d304_sibling()._synthetic_definitions(contract)
    inventory = parse_identity_inventory(
        identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(UPPER.table_name),
            uuid_column_letter=str(UPPER.uuid_col),
        )
    )
    definitions = synthetic.__class__(
        entry_id=synthetic.entry_id,
        bundle=synthetic.bundle,
        contract=synthetic.contract,
        adapter_build=synthetic.adapter_build,
        identity_inventory=inventory,
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )
    adapter = build_excel_adapter(
        definitions=definitions,
        binding=X.ExcelIdentityBinding(
            table_name=UPPER.table_name, uuid_column=UPPER.uuid_col, table_key=UPPER.table_key
        ),
        direction="html_to_oo",
        sibling_bindings=(
            X.ExcelIdentityBinding(
                table_name=LOWER.table_name, uuid_column=LOWER.uuid_col, table_key=LOWER.table_key
            ),
        ),
    )
    tmp = tmp_path_factory.mktemp("d34_collision")
    base = tmp / "d304-base.xlsx"
    base.write_bytes(instrumented.instrumented_bytes)
    return _D34World(adapter=adapter, contract=contract, base=base, tmp=tmp)


_DEFINED_NAME_RE = re.compile(r'<definedName name="([^"]+)"[^>]*>([^<]*)</definedName>')


def _d34_defined_names(artifact: Path) -> dict[str, str]:
    """产物 workbook.xml 里**值指向 D3-4 sheet** 的 definedName（值按 XML 实体还原）。

    按值筛而不是按名字筛：`_xlnm.Print_Area` 每张 sheet 各有一条（`localSheetId` 区分），
    按名字取会拿到别的 sheet 的那条。
    """
    with zipfile.ZipFile(artifact) as zf:
        workbook = zf.read(_WB).decode("utf-8")
    found: dict[str, str] = {}
    for hit in _DEFINED_NAME_RE.finditer(workbook):
        value = html.unescape(hit.group(2))
        if _Q in value:
            assert hit.group(1) not in found, f"指向 D3-4 的 definedName 重名：{hit.group(1)}"
            found[hit.group(1)] = value
    return found


def test_premise_template_defined_names_match_the_synthetic_table(d34: _D34World) -> None:
    """前提：第 1 节合成用例抄的是**真实**模板值（不是凭印象写的）。"""
    assert _d34_defined_names(d34.base) == dict(_D34_TEMPLATE_NAMES)
    assert _D34_INSERT_AT == int(UPPER.last_data_row) + 1


@pytest.mark.parametrize(
    "k",
    [
        pytest.param(3, id="k3-prefix-collision"),
        pytest.param(4, id="k4-control"),
        pytest.param(5, id="k5"),
        pytest.param(6, id="k6-control"),
        pytest.param(8, id="k8-equal-collision"),
    ],
)
def test_d34_upper_single_pass_materializes_and_shifts_each_name_once(
    d34: _D34World, k: int
) -> None:
    """段①单趟插 k 行：materialize 不抛 `PropagationDriftError`，且每个 definedName 恰好位移一次。

    只钉 apply 侧。verify 等价性不在这里断言：k=5/8 时 verify 侧 `normalise_propagated_part`
    仍有同类碰撞（第 3b 段）。
    """
    result, output = d34.materialize(k, 0, tag="apply")
    shifts = {key: value[0].count for key, value in (result.per_table_shift or {}).items()}
    assert shifts == {str(UPPER.table_key): k}, shifts
    # 只核对本趟**声明**的那几条（oracle 下值会变的）；不动的名字不属于 apply 的职责面。
    expected = {
        name: shifted
        for name, value in _D34_TEMPLATE_NAMES
        if (shifted := _shift_rows(value, at=_D34_INSERT_AT, count=k)) != value
    }
    assert len(expected) == len(result.workbook_row_change.propagations) == 5
    actual = _d34_defined_names(output)
    assert {name: actual.get(name) for name in expected} == expected


@pytest.mark.parametrize("k", [3, 8], ids=["k3-prefix-collision", "k8-equal-collision"])
def test_mutation_legacy_apply_fails_d34_real_adapter(
    d34: _D34World, k: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """变异反证（真实 adapter）：把 apply 换回旧实现，k=3 / k=8 必须在 materialize 期 fail closed。"""
    monkeypatch.setattr(M, "_apply_workbook_propagation", _legacy_apply)
    with pytest.raises(N1.PropagationDriftError, match="声明 5 处传播，实际只改了 6 处"):
        d34.materialize(k, 0, tag="legacy")


# ═══════════════════════════════════════════════════════════════════════════
# 4. verify before-digest 缓存键：不同 region 几何不得串味
# ═══════════════════════════════════════════════════════════════════════════


class _GeometryBlindCache:
    """变异：把 `before_key` 里的**本区几何**段剥掉再查表 = 修复前的键。

    按形态识别几何段（`A26:K27,26,27,A,K,K`），不按位置 —— 键的段序是实现细节。
    """

    _GEOMETRY = re.compile(
        r"^[A-Z]{1,3}\d+:[A-Z]{1,3}\d+,\d+,\d+,[A-Z]{1,3},[A-Z]{1,3},[A-Z]{1,3}$"
    )

    def __init__(self) -> None:
        self._inner: PC.BoundedLruCache[str, object] = PC.BoundedLruCache(maxsize=128)
        self.stripped = 0

    def _blind(self, key: str) -> str:
        segments = key.split("|")
        kept = [segment for segment in segments if not self._GEOMETRY.match(segment)]
        self.stripped += len(segments) - len(kept)
        return "|".join(kept)

    def get(self, key: str) -> object | None:
        return self._inner.get(self._blind(key))

    def put(self, key: str, value: object) -> None:
        self._inner.put(self._blind(key), value)

    def clear(self) -> None:
        self._inner.clear()


def test_before_digest_cache_does_not_leak_across_region_geometry(
    d34: _D34World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一进程、同一 base：先 verify (4,0) 再 verify (4,5)，两次都必须等价。

    选行理由：(4,5) 在新键下单独重算 before digest 时本身就等价（17+4≠22，没有 verify 侧碰撞），
    所以它若红只能是缓存串味。(4,0)/(4,5) 的上区几何相同（`A13:J19`）、下区不同
    （`A26:K27` / `A26:K32`），而下区 binding 的兄弟坐标（上区）两次逐字相同 —— 正是旧键
    分不开的那一对。
    """
    first, first_out = d34.materialize(4, 0, tag="cache")
    second, second_out = d34.materialize(4, 5, tag="cache")

    # ── 真实键：两次都等价；不同几何不命中，同一几何仍命中 ──
    # （adapter 层逐 binding `assert_equivalent()`，漂移直接抛 `UnmanagedRegionDriftError`。）
    PC.clear_all_parse_caches()
    cache = PC.BEFORE_DIGEST_CACHE
    assert d34.verify(first, first_out).equivalent is True
    before_second = cache.stats
    assert d34.verify(second, second_out).equivalent is True
    after_second = cache.stats
    assert d34.verify(first, first_out).equivalent is True
    after_repeat = cache.stats
    assert after_second["hits"] == before_second["hits"], "不同 region 几何命中了缓存"
    assert after_repeat["misses"] == after_second["misses"], "同一 region 几何没命中缓存"

    # ── 变异反证：修复前的键 ⇒ (4,5) 的下区命中 (4,0) 的 before digest ⇒ 误报 ──
    blind = _GeometryBlindCache()
    with monkeypatch.context() as patch:
        patch.setattr(PC, "BEFORE_DIGEST_CACHE", blind)
        assert d34.verify(first, first_out).equivalent is True
        with pytest.raises(UnmanagedRegionDriftError, match="managed_sheet_unmanaged_cells"):
            d34.verify(second, second_out)
    assert blind.stripped > 0, "变异没剥到任何几何段 —— 键的形态变了，反证失效"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 第 3b 段 —— verify 侧精确逆（`normalise_propagated_part`）
# ═══════════════════════════════════════════════════════════════════════════
#
# apply 与 verify 用**同一个**原语 `_simultaneous_rewrite`：apply 传 `(before, after)`，
# verify 传其逆 `(after, before)`。round-trip = 「apply 的产物再 normalise 回来 == 改前原文」。
# 跨趟链必须按 `trips` 倒序、每趟一次同时逆替换（不能迭代到不动点，k=8 反例见 §10.0 第 2 条）。


def _plan_from_trips(
    trips: tuple[tuple[tuple[str, str, int], ...], ...],
    *,
    part: str,
    count: int,
) -> N1.MaterializeWorkbookChangeSet:
    """把「每趟一组 `(ref_before, ref_after, row_before)`」组装成带趟序的 ChangeSet。

    verify 侧 `normalise_propagated_part` 按 `trips` 倒序逆替换；扁平 `propagations` 供对账。
    """
    carrier = "defined_name" if part == _WB else "formula"
    plan_trips: list[tuple[N1.PropagationEntry, ...]] = []
    flat: list[N1.PropagationEntry] = []
    for trip_index, decls in enumerate(trips):
        trip_entries = tuple(
            N1.PropagationEntry(
                carrier=carrier,
                part=part,
                locator=f"T{trip_index}L{decl_index}#0",
                ref_before=before,
                ref_after=after,
                row_before=row,
                row_after=row + count,
            )
            for decl_index, (before, after, row) in enumerate(decls)
        )
        plan_trips.append(trip_entries)
        flat.extend(trip_entries)
    return N1.MaterializeWorkbookChangeSet(
        propagations=tuple(flat), trips=tuple(plan_trips)
    )


def test_single_trip_cases_normalise_back_to_before() -> None:
    """所有单趟 apply 判据：apply 的产物再 `normalise` 回来必须逐字等于改前原文。

    覆盖前缀碰撞、整段相等碰撞（同趟）、D3-4 k=3/5/8 `&apos;` 形态、各边界写法。
    round-trip 计量：`reverted` == 该 part 的声明条数（逆替换命中次数与声明数对账）。
    """
    for case in _CASES:
        # 单趟：把 `_Case` 的声明喂成 ChangeSet 的一趟（part 命中过滤在 normalise 内做）。
        changeset = _plan_from_trips(
            (case.decls,), part=case.part, count=case.count
        )
        normalised, reverted = N1.normalise_propagated_part(
            case.expected, changeset, part=case.part
        )
        assert normalised == case.text, case.id
        assert reverted == len(case.decls), (case.id, reverted)


def _chain_case_prefix_collision() -> tuple[str, str, N1.MaterializeWorkbookChangeSet]:
    """跨趟链（前缀碰撞形状）：同一 definedName 两趟各改一次。

    趟①：`X!$A$17` → `X!$A$22`（+5）；趟②：`X!$A$22` → `X!$A$27`（+5）。产物是 `$A$27`。
    逆替换必须先趟②（`$A$27`→`$A$22`）再趟①（`$A$22`→`$A$17`），逐层剥回 `$A$17`。
    另有一条不参与链的 CREDIT region `X!$A$22:$D$23`（趟①同时改成 `$A$27:$D$28`）——它的
    before `$A$22` 与链中间态 `$A$22` 逐字相等，正是「逐条替换会串味」的形状；一次同时逆替换
    靠右边界（`:$D`）区分。
    """
    before = _names_xml(
        [("FOOTER", "X!$A$17"), ("REGION", "X!$A$22:$D$23")]
    )
    after = _names_xml(
        [("FOOTER", "X!$A$27"), ("REGION", "X!$A$27:$D$28")]
    )
    changeset = _plan_from_trips(
        (
            # 趟①：footer 17→22、region 22:23→27:28（同趟一次同时替换）。
            (("X!$A$17", "X!$A$22", 17), ("X!$A$22:$D$23", "X!$A$27:$D$28", 22)),
            # 趟②：footer 22→27（链的第二段）。
            (("X!$A$22", "X!$A$27", 22),),
        ),
        part=_WB,
        count=5,
    )
    return before, after, changeset


def _chain_case_whole_equal() -> tuple[str, str, N1.MaterializeWorkbookChangeSet]:
    """跨趟同文本、**不同** definedName（k=8 反例形状）：单趟内两条 `$A$17→$A$25`、`$A$25→$A$33`。

    这是**同一趟**里两条不同 definedName 的引用互为「产物 == 别条 before」的形状。一次同时
    逆替换 = `$A$33`→`$A$25`、`$A$25`→`$A$17` 各一处，正确；旧 `_chain_depth` 按文本相等会把
    两条误连成链、逆错。
    """
    before = _names_xml([("DEBIT", "X!$A$17"), ("CREDIT", "X!$A$25")])
    after = _names_xml([("DEBIT", "X!$A$25"), ("CREDIT", "X!$A$33")])
    changeset = _plan_from_trips(
        ((("X!$A$17", "X!$A$25", 17), ("X!$A$25", "X!$A$33", 25)),),
        part=_WB,
        count=8,
    )
    return before, after, changeset


def _chain_case_cross_trip_text_collision() -> tuple[
    str, str, N1.MaterializeWorkbookChangeSet
]:
    """跨趟、文本相同但**不同** definedName、且**不成链**：两趟各改一处不同的引用。

    趟①改 `X!$A$40`→`X!$A$45`（+5）；趟②改 `Y!$A$40`→`Y!$A$45`（+5）。两条 before 的行号
    文本相同（`$A$40`）但 sheet 前缀不同 ⇒ 各趟一次同时逆替换互不干扰。
    """
    before = _names_xml([("A", "X!$A$40"), ("B", "Y!$A$40")])
    after = _names_xml([("A", "X!$A$45"), ("B", "Y!$A$45")])
    changeset = _plan_from_trips(
        (
            (("X!$A$40", "X!$A$45", 40),),
            (("Y!$A$40", "Y!$A$45", 40),),
        ),
        part=_WB,
        count=5,
    )
    return before, after, changeset


_CHAIN_CASES = {
    "cross_trip_chain_prefix": _chain_case_prefix_collision,
    "same_trip_whole_equal_k8": _chain_case_whole_equal,
    "cross_trip_same_text_diff_name": _chain_case_cross_trip_text_collision,
}


@pytest.mark.parametrize("chain_id", sorted(_CHAIN_CASES))
def test_multi_trip_normalise_round_trip(chain_id: str) -> None:
    """跨趟链 / 同趟整段相等 / 跨趟文本巧合：`normalise` 逐字剥回改前原文。"""
    before, after, changeset = _CHAIN_CASES[chain_id]()
    normalised, reverted = N1.normalise_propagated_part(after, changeset, part=_WB)
    assert normalised == before, chain_id
    # 逆替换命中数 == 扁平声明条数（链式两趟各命中一次，合计 = 两条）。
    assert reverted == len(changeset.propagations), (chain_id, reverted)


def _legacy_normalise(
    text: str, plan: Any, *, part: str
) -> tuple[str, int]:
    """修复前 `normalise_propagated_part` 的**局部复刻**：`_chain_depth` + 逐条 `str.replace`。

    只用扁平 `propagations`（旧实现没有趟序），按（链深度、长度）排序后逐条 `text.replace`。
    碰撞类必须在此打红（round-trip 剥不回改前口径）。
    """
    entries = [e for e in plan.propagations if e.part == part]
    if not entries:
        return text, 0
    pairs: dict[tuple[str, str], int] = {}
    for entry in entries:
        pairs[(entry.ref_after, entry.ref_before)] = (
            pairs.get((entry.ref_after, entry.ref_before), 0) + 1
        )

    def _apos(s: str) -> str:
        return s.replace("'", "&apos;")

    by_after = {after: before for after, before in pairs}

    def _chain_depth(after: str) -> int:
        depth = 0
        cursor = by_after.get(after)
        seen = {after}
        while cursor is not None and cursor in by_after and cursor not in seen:
            seen.add(cursor)
            depth += 1
            cursor = by_after.get(cursor)
        return depth

    out = text
    reverted = 0
    for after, before in sorted(
        pairs, key=lambda kv: (_chain_depth(kv[0]), len(kv[0])), reverse=True
    ):
        for cand_after, cand_before in (
            (_apos(N1._escape(after)), _apos(N1._escape(before))),
            (N1._escape(after), N1._escape(before)),
            (_apos(after), _apos(before)),
            (after, before),
        ):
            hits = out.count(cand_after)
            if hits:
                out = out.replace(cand_after, cand_before)
                reverted += hits
                break
    return out, reverted


def test_mutation_legacy_normalise_turns_collision_round_trips_red() -> None:
    """变异反证：把 normalise 换回旧实现（`_chain_depth` + 逐条 replace），碰撞类必须打红。

    红 = round-trip 剥不回改前原文（或计量不符）。逐条列出红的判据，门槛 ≥ 2 条。
    """

    def _round_trip_ok(
        normalise: Callable[..., tuple[str, int]],
        before: str,
        after: str,
        changeset: Any,
    ) -> bool:
        got, reverted = normalise(after, changeset, part=_WB)
        return got == before and reverted == len(changeset.propagations)

    # 单趟碰撞（`_CASES` 里 `legacy_red` 的那些，在 workbook part 上的）+ 跨趟链。
    red: list[str] = []
    for case in _CASES:
        if case.part != _WB:
            continue
        changeset = _plan_from_trips((case.decls,), part=_WB, count=case.count)
        legacy_ok = _round_trip_ok(
            _legacy_normalise, case.text, case.expected, changeset
        )
        current_ok = _round_trip_ok(
            N1.normalise_propagated_part, case.text, case.expected, changeset
        )
        assert current_ok, f"新实现 round-trip 应绿：{case.id}"
        if not legacy_ok:
            red.append(f"case:{case.id}")
    for chain_id, factory in _CHAIN_CASES.items():
        before, after, changeset = factory()
        assert _round_trip_ok(
            N1.normalise_propagated_part, before, after, changeset
        ), f"新实现 round-trip 应绿：{chain_id}"
        if not _round_trip_ok(_legacy_normalise, before, after, changeset):
            red.append(f"chain:{chain_id}")
    assert len(red) >= 2, red
    # 关键碰撞形状必须在红名单里（不能只靠边缘判据凑数）。
    assert "chain:cross_trip_chain_prefix" in red or "chain:same_trip_whole_equal_k8" in red, red


# ═══════════════════════════════════════════════════════════════════════════
# 6. 第 3b 段 —— D3-4 真实 adapter verify 等价性
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "k",
    [
        pytest.param(3, id="k3"),
        pytest.param(4, id="k4"),
        pytest.param(5, id="k5-was-verify-collision"),
        pytest.param(6, id="k6"),
        pytest.param(8, id="k8-was-chain-misconnect"),
    ],
)
def test_d34_upper_single_pass_verify_equivalent(d34: _D34World, k: int) -> None:
    """段①单趟插 k 行：materialize 后 verify 判**等价**（含 3a 修复前 verify 侧仍红的 k=5/8）。"""
    result, output = d34.materialize(k, 0, tag="verify")
    assert d34.verify(result, output).equivalent is True


@pytest.mark.parametrize(
    "n_up,n_lo",
    [pytest.param(5, 5, id="two-pass-5-5"), pytest.param(3, 5, id="two-pass-3-5")],
)
def test_d34_dual_zone_two_pass_verify_equivalent(
    d34: _D34World, n_up: int, n_lo: int
) -> None:
    """两区都插行（两趟）：materialize + verify 等价。

    5/5 = `test_d3_04_dual_zone_shift_and_verify::…::test_cumulative_two_pass_insertion_still_verifies_correctly`
    的同形状（那条在不改断言的前提下已随本段转绿）。3/5 = 段①前缀碰撞 + 段②各改一趟。
    """
    result, output = d34.materialize(n_up, n_lo, tag="two-pass")
    assert d34.verify(result, output).equivalent is True
