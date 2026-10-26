# -*- coding: utf-8 -*-
"""公式证据的提取 / 端到端合并 / store 镜像（spec oo-formula-recompute-not-tamper R2 / R1 / R3）。

* R2：真 D4（40 binding）world —— 证据覆盖多个 binding、不进摘要、不参与相等、P9 命中原样带着；
* R1 端到端：同一份真 D4 文件上模拟 OO 重算 / 公式格敲数字 / 公式改写 / 服务器侧另有改动，
  走生产 `adapter.extract`（oo_to_html 方向）+ `merge_projections`；
* R3：真 D2 契约 + 真 D2 store 合并函数 —— 采纳的重算值进 store、骨架行不回流、接线。
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import io
import json
import re
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

from app.services.workpaper_sync import parse_cache as PC
from app.services.workpaper_sync import pilot_d2_large_json as P
from app.services.workpaper_sync.adapters import excel as AX
from app.services.workpaper_sync.adapters.base import FieldValue
from app.services.workpaper_sync.cleared_field_view import (
    RecomputedFieldValue,
    store_view_with_recomputed_formulas,
)
from app.services.workpaper_sync.conflicts import ConflictKind
from app.services.workpaper_sync.content_mutation import projection_canonical_digest
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.d2_bidirectional_bridge import merge_projection_into_store_rows
from app.services.workpaper_sync.merge import FieldVerdict, merge_projections
from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator
from app.services.workpaper_sync.template_skeleton_baseline import (
    SkeletonBaseline,
    pure_template_skeleton_rows,
)
from tests.workpaper_sync.d4_materialize_harness import D4World, _text_safe, build_world


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    return build_world(tmp_path_factory.mktemp("d4-formula-recompute"))


@pytest.fixture(autouse=True)
def _isolated_cache() -> Iterator[None]:
    PC.clear_all_parse_caches()
    yield
    PC.clear_all_parse_caches()


def _clone(world: D4World, *, direction: str = "html_to_oo", baseline: Path | None = None) -> Any:
    a = world.adapter
    return AX.build_excel_adapter(
        definitions=a.definitions, binding=a.binding, sibling_bindings=a.sibling_bindings,
        direction=direction, baseline_representation=baseline,
    )


# ═══════════════════════════════════════════════════════════════════════════
# R2 证据
# ═══════════════════════════════════════════════════════════════════════════

PERIOD_TOTAL_12 = "revenue_detail_rows/GTROW-D42-0012/period_total"


def test_signatures_cover_every_binding_that_has_formulas(world: D4World) -> None:
    signatures = world.projection.formula_signatures
    assert signatures, "真 D4 提取没有带公式证据"
    tables = {key.split("/", 1)[0] for key in signatures}
    assert {"revenue_detail_rows", "customer_current_rows", "customer_prior_rows"} <= tables, tables
    assert signatures[PERIOD_TOTAL_12] == "=SUM(B{r}:M{r})"
    # 合计行 $C$24 按受管表几何归一（spec oo-writeback-template-parity-closure R6）：插行后不变。
    assert signatures["customer_current_rows/GTROW-D49C-0013/amount_ratio"] == "=IF(C{r}=0,0,C{r}/$C${end+2})"


def test_signatures_are_not_part_of_the_digest_or_equality(world: D4World) -> None:
    p = world.projection
    bare = dataclasses.replace(p, formula_signatures=None)
    assert projection_canonical_digest(p) == projection_canonical_digest(bare)
    assert projection_canonical_digest(p) == projection_canonical_digest(
        dataclasses.replace(p, formula_signatures={})
    )
    assert p == bare, "签名参与了相等比较"
    assert "formula_signatures" not in repr(p)


def test_p2_comparison_surface_really_compares_formula_signatures(world: D4World) -> None:
    """P2（链式 / 单趟物化反读逐字段等值）的比较面真的比公式签名，不只是把字段名登记进清单。"""
    from tests.workpaper_sync.test_single_pass_artifact_equivalence import projection_differences

    p = world.projection
    assert projection_differences(p, p) == ()
    rewritten = dataclasses.replace(p, formula_signatures={**p.formula_signatures, PERIOD_TOTAL_12: "=0"})
    assert any(PERIOD_TOTAL_12 in line for line in projection_differences(p, rewritten))
    assert projection_differences(p, dataclasses.replace(p, formula_signatures=None)) != ()


def test_p9_hit_carries_the_same_signatures_as_a_fresh_extraction(world: D4World) -> None:
    first = _clone(world).extract(artifact=world.base, contract=world.contract)
    hit = _clone(world).extract(artifact=world.base, contract=world.contract)
    assert hit is first
    PC.clear_all_parse_caches()
    fresh = _clone(world).extract(artifact=world.base, contract=world.contract)
    assert fresh is not first and fresh.formula_signatures == first.formula_signatures


def test_store_projection_carries_no_evidence() -> None:
    projection = P.build_store_projection("[]", contract=P.load_pilot_contract())
    assert projection.formula_signatures is None


# ═══════════════════════════════════════════════════════════════════════════
# R1 端到端：真 D4 文件
# ═══════════════════════════════════════════════════════════════════════════

ROW = "GTROW-D42-0013"
MONTH = f"revenue_detail_rows/{ROW}/month_01"
TOTAL = f"revenue_detail_rows/{ROW}/period_total"
PRIOR = f"revenue_detail_rows/{ROW}/prior_unadjusted"


def _sheet_part(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        workbook = zf.read("xl/workbook.xml").decode("utf-8")
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rid = re.search(r'<sheet [^>]*name="' + re.escape(name) + r'"[^>]*r:id="(rId\d+)"', workbook)
    target = re.search(r'Id="' + rid.group(1) + r'"[^>]*Target="([^"]+)"', rels).group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _with_cells(data: bytes, part: str, cells: Mapping[str, str]) -> bytes:
    """把已有的 `<c r="X">` 整格换成给定 XML（样式 `s` 保留）。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}
    xml = entries[part].decode("utf-8")
    for coord, inner in cells.items():
        pattern = re.compile(rf'<c r="{coord}"(?P<attrs>(?:\s[^>]*?)?)(?:/>|>.*?</c>)', re.S)
        found = pattern.search(xml)
        assert found is not None, f"模板里没有 {coord}"
        style = re.search(r'\ss="(\d+)"', found.group("attrs") or "")
        s_attr = f' s="{style.group(1)}"' if style else ""
        xml = xml[: found.start()] + f'<c r="{coord}"{s_attr}{inner}</c>' + xml[found.end():]
    entries[part] = xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


#: N13 是共享公式的从属格（主格 N12），只换 `<v>` 或换掉这一格的 `<f>` 不影响别的行。
SHARED = '<f t="shared" si="0"/>'
INCOMING_CASES: dict[str, dict[str, str]] = {
    # OO 重算：改 1 月 → 期间合计跟着变，公式不动
    "recompute": {"B13": "><v>150</v>", "N13": f">{SHARED}<v>150</v>"},
    # 公式格敲了数字
    "literal": {"B13": "><v>150</v>", "N13": "><v>999</v>"},
    # 公式被改写（少加一个月）
    "rewritten": {"B13": "><v>150</v>", "N13": "><f>SUM(B13:L13)</f><v>150</v>"},
}


@pytest.fixture(scope="module")
def d4_files(world: D4World) -> dict[str, Path]:
    data = world.base.read_bytes()
    part = _sheet_part(data, "主营业务收入明细表D4-2")
    root = world.base.parent / "recompute"
    root.mkdir(exist_ok=True)
    base_bytes = _with_cells(
        data, part,
        {"A13": ' t="inlineStr"><is><t>产品甲</t></is>', "B13": "><v>100</v>", "N13": f">{SHARED}<v>100</v>"},
    )
    files = {"base": root / "base.xlsx"}
    files["base"].write_bytes(base_bytes)
    for name, cells in INCOMING_CASES.items():
        files[name] = root / f"{name}.xlsx"
        files[name].write_bytes(_with_cells(base_bytes, part, cells))
    files["current"] = root / "current.xlsx"  # 服务器侧在 OO 编辑期间改了期初未审
    files["current"].write_bytes(_with_cells(base_bytes, part, {"Q13": "><v>5</v>"}))
    return files


def _merge(world: D4World, files: Mapping[str, Path], incoming: str, current: str = "base") -> Any:
    adapter = _clone(world, direction="oo_to_html", baseline=files["base"])
    read = lambda name: _text_safe(adapter.extract(artifact=files[name], contract=world.contract))  # noqa: E731
    base = read("base")
    return merge_projections(
        base=base, current=base if current == "base" else read(current),
        incoming=read(incoming), contract=world.contract,
    )


def test_oo_recompute_on_a_real_d4_file_is_taken(world: D4World, d4_files) -> None:
    outcome = _merge(world, d4_files, "recompute")
    assert outcome.conflict_count == 0, [r.reason for r in outcome.conflicts.records]
    assert outcome.verdicts[TOTAL] is FieldVerdict.took_recomputed
    assert outcome.verdicts[MONTH] is FieldVerdict.took_incoming
    assert outcome.merged.get(TOTAL).value == 150


@pytest.mark.parametrize(("incoming", "needle"), [("literal", "换成了数值"), ("rewritten", "被改写")])
def test_tamper_on_a_real_d4_file_is_a_protected_conflict(world: D4World, d4_files, incoming, needle) -> None:
    outcome = _merge(world, d4_files, incoming)
    records = [r for r in outcome.conflicts.records if r.locator.stable_field_key == TOTAL]
    assert len(records) == 1 and records[0].kind is ConflictKind.protected
    assert needle in records[0].reason
    assert outcome.merged.get(TOTAL).value == 100


def test_server_side_edit_during_oo_session_blocks_the_recompute(world: D4World, d4_files) -> None:
    outcome = _merge(world, d4_files, "recompute", current="current")
    [record] = [r for r in outcome.conflicts.records if r.locator.stable_field_key == TOTAL]
    assert "R1.2" in record.reason and PRIOR in record.reason
    assert outcome.merged.get(PRIOR).value == 5, "服务器侧的改动照常保留"


# ═══════════════════════════════════════════════════════════════════════════
# R2 / R1 静态受管区：真 A5-1（纯静态 entry，两张静态区）
# ═══════════════════════════════════════════════════════════════════════════
# 静态区走另一条提取路径（`_extract_static_projection`）；D4 的三张静态区没有公式字段，
# 只测 D4 时去掉这条路径的签名照样全绿（磁盘变异 X2 存活过）。

A51_SHEET = "A5-1-1列示于现金流量表的现金及现金等价物"
A51_G10 = "a51-audit-formula-g10"


@pytest.fixture(scope="module")
def a51_world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from app.services.workpaper_sync import excel_instrumentation as EI
    from app.services.workpaper_sync import phase5_a51_cashflow_audit as A51
    from app.services.workpaper_sync import published_identity_observer as OBS
    from app.services.workpaper_sync.excel_entry_gate import AdapterBuild, FrozenEntryDefinitions
    from tests.workpaper_sync.d4_materialize_harness import _bundle, _digest

    contract = A51.load_contract_from_disk()
    data = EI.instrument_workbook_bytes_static_only(
        A51.read_authoritative_template(), A51.static_only_instrumentation_spec(),
        gate=A51.excel_carrier_gate(), identity_carriers=A51.IDENTITY_CARRIERS,
    ).instrumented_bytes
    _fp, _physical, inventory, _structure = OBS.collect_workbook_structure(
        data=data, contract=contract, sheet_anchors=OBS._frozen_sheet_anchors(A51.build_instrumentation_payload())
    )
    definitions = FrozenEntryDefinitions(
        entry_id=A51.ENTRY_ID, bundle=_bundle(contract), contract=contract,
        adapter_build=AdapterBuild(adapter_id=A51.ADAPTER_ID, adapter_build_digest=_digest("ofr-a51"),
                                   document_type="xlsx", contract_version=contract.semantic_version),
        identity_inventory=inventory, business_sheets=(), dynamic_column_keys={}, structure_inventory_size=0,
    )
    root = tmp_path_factory.mktemp("a51-formula-recompute")
    part = _sheet_part(data, A51_SHEET)
    g10 = '><f t="shared" si="0"/><v>{}</v>'  # G8:G13 共享公式 D{r}+E{r} 的从属格
    files = {
        "base": _with_cells(data, part, {"D10": "><v>100</v>", "G10": g10.format(100)}),
        "recompute": _with_cells(data, part, {"D10": "><v>150</v>", "G10": g10.format(150)}),
        "literal": _with_cells(data, part, {"D10": "><v>150</v>", "G10": "><v>999</v>"}),
    }
    paths = {}
    for name, payload in files.items():
        paths[name] = root / f"{name}.xlsx"
        paths[name].write_bytes(payload)
    bindings = tuple(A51.static_identity_bindings())
    adapter = AX.build_excel_adapter(
        definitions=definitions, binding=bindings[0], sibling_bindings=bindings[1:],
        direction="oo_to_html", baseline_representation=paths["base"],
    )
    return {"adapter": adapter, "contract": contract, "files": paths}


def _a51_merge(world: Mapping[str, Any], incoming: str) -> Any:
    adapter, contract, files = world["adapter"], world["contract"], world["files"]
    base = adapter.extract(artifact=files["base"], contract=contract)
    return base, merge_projections(
        base=base, current=base, incoming=adapter.extract(artifact=files[incoming], contract=contract),
        contract=contract,
    )


def test_static_regions_carry_signatures_from_every_binding(a51_world) -> None:
    base, _outcome = _a51_merge(a51_world, "recompute")
    signatures = base.formula_signatures or {}
    assert signatures[A51_G10] == "=D{r}+E{r}"  # 主 binding（A5-1-1）
    assert signatures["a51-reconcile-formula-b18"] == "=SUM(B8:B17)"  # 兄弟 binding（A5-1-3）


def test_static_region_recompute_is_taken_and_tamper_is_not(a51_world) -> None:
    _base, outcome = _a51_merge(a51_world, "recompute")
    assert outcome.conflict_count == 0, [r.reason for r in outcome.conflicts.records]
    assert outcome.verdicts[A51_G10] is FieldVerdict.took_recomputed
    assert outcome.verdicts["a51-audit-3.unadjusted"] is FieldVerdict.took_incoming
    assert outcome.merged.get(A51_G10).value == 150
    _base, tampered = _a51_merge(a51_world, "literal")
    [record] = [r for r in tampered.conflicts.records if r.locator.stable_field_key == A51_G10]
    assert record.kind is ConflictKind.protected and "换成了数值" in record.reason
    assert tampered.merged.get(A51_G10).value == 100


# ═══════════════════════════════════════════════════════════════════════════
# R3 store：真 D2 契约 + 真 D2 store 合并
# ═══════════════════════════════════════════════════════════════════════════

D2_ROW = "dr-ofr-row-a"
D2_SIGS = {
    "end_balance": "=E{r}+O{r}-P{r}",
    "current_unadjusted": "=Q{r}+R{r}",
    "current_audited": "=S{r}+Z{r}+AA{r}",
}


@pytest.fixture(scope="module")
def d2_contract() -> Any:
    return P.load_pilot_contract()


def _d2_rows() -> list[dict[str, Any]]:
    return [{
        "rowId": D2_ROW, "seq": 1, "customerName": "甲公司", "relationType": "非关联方",
        "priorUnadjusted": 1000, "debitOccurrence": 0, "creditOccurrence": 0, "endBalance": 1000,
        "reclassification": 0, "currentUnadjusted": 1000, "currentAje": 0, "currentRje": 0,
        "currentAudited": 1000,
    }]


def _d2_merge(contract: Any, *, current_change: Mapping[str, Any] | None = None) -> tuple[Any, list]:
    seed = P.build_store_projection(json.dumps(_d2_rows()), contract=contract)
    rows, *_ = merge_projection_into_store_rows(projection=seed, base_rows=_d2_rows())
    store = P.build_store_projection(json.dumps(rows), contract=contract)
    sigs = {P.stable_key_for(col, D2_ROW): sig for col, sig in D2_SIGS.items()}
    base = dataclasses.replace(store, formula_signatures=sigs)

    def changed(changes: Mapping[str, Any]) -> Any:
        values = dict(base.values)
        for col, value in changes.items():
            key = P.stable_key_for(col, D2_ROW)
            values[key] = dataclasses.replace(values[key], value=value)
        return dataclasses.replace(base, values=values)

    incoming = changed({"debit_occurrence": 1500, "end_balance": 2500,
                        "current_unadjusted": 2500, "current_audited": 2500})
    current = changed(current_change) if current_change else base
    return merge_projections(base=base, current=current, incoming=incoming, contract=contract), rows


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return next(r for r in rows if r["rowId"] == D2_ROW)


def test_without_the_view_the_store_keeps_stale_formula_values(d2_contract) -> None:
    """负对照（修前形态）：store 合并跳过受保护字段 ⇒ 借方更新了、期末三列还是旧值。"""
    merge, rows = _d2_merge(d2_contract)
    assert merge.conflict_count == 0
    merged_rows, *_ = merge_projection_into_store_rows(projection=merge.merged, base_rows=rows)
    assert _row(merged_rows)["debitOccurrence"] == 1500
    assert _row(merged_rows)["endBalance"] == 1000


def test_recomputed_formula_values_reach_the_store(d2_contract) -> None:
    merge, rows = _d2_merge(d2_contract)
    view, keys = store_view_with_recomputed_formulas(merge.merged, merge=merge)
    assert keys == tuple(sorted(P.stable_key_for(col, D2_ROW) for col in D2_SIGS))
    merged_rows, applied, _visited, touched = merge_projection_into_store_rows(projection=view, base_rows=rows)
    row = _row(merged_rows)
    assert (row["endBalance"], row["currentUnadjusted"], row["currentAudited"]) == (2500, 2500, 2500)
    assert row["debitOccurrence"] == 1500 and applied == 4 and touched == {D2_ROW}
    # 发布出去的 projection 不变：仍是普通 FieldValue（受保护）
    assert all(type(merge.merged.get(k)) is FieldValue for k in keys)
    assert all(isinstance(view.get(k), RecomputedFieldValue) and not view.get(k).is_protected for k in keys)
    assert all(view.get(k).mode is FieldMode.formula for k in keys)


def test_nothing_to_release_returns_the_same_object(d2_contract) -> None:
    merge, _rows = _d2_merge(d2_contract, current_change={"customer_name": "乙公司"})
    assert not [k for k, v in merge.verdicts.items() if v is FieldVerdict.took_recomputed]
    view, keys = store_view_with_recomputed_formulas(merge.merged, merge=merge)
    assert view is merge.merged and keys == ()
    assert store_view_with_recomputed_formulas(merge.merged, merge=None) == (merge.merged, ())


def test_recomputed_values_do_not_resurrect_template_skeleton_rows() -> None:
    """只有公式值的骨架行（base 里没有）仍按「模板原样」跳过，且不读模板（R12 不回流）。"""
    rid = "GTROW-D22-0013"
    key = P.stable_key_for("end_balance", rid)
    value = RecomputedFieldValue(stable_key=key, value=0, value_type=ValueType.amount,
                                 mode=FieldMode.formula, row_key=rid)
    projection = dataclasses.replace(
        P.build_store_projection("[]", contract=P.load_pilot_contract()),
        values={key: value}, row_keys={P.ROWS_TABLE_KEY: (rid,)},
    )

    def no_template_read() -> SkeletonBaseline:
        raise AssertionError("没有可编辑值的候选行却读了模板")

    assert pure_template_skeleton_rows(
        projection, table_key=P.ROWS_TABLE_KEY, base_identities=set(), baseline=no_template_read
    ) == frozenset({rid})
    rows, applied, _visited, touched = merge_projection_into_store_rows(projection=projection, base_rows=[])
    assert rows == [] and applied == 0 and touched == set()


def test_the_coordinator_mirrors_both_views() -> None:
    """接线：`_apply_committed` 先补清空视图、再放行重算值，镜像拿到的是最后那一层（AST）。"""
    fn = ast.parse(textwrap.dedent(inspect.getsource(OoToHtmlCoordinator._apply_committed)))
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    names = [n.func.id for n in sorted(calls, key=lambda n: (n.lineno, n.col_offset))]
    assert names.index("store_view_with_cleared_fields") < names.index("store_view_with_recomputed_formulas")
    recompute = next(n for n in calls if n.func.id == "store_view_with_recomputed_formulas")
    assert isinstance(recompute.args[0], ast.Name) and recompute.args[0].id == "store_view"
    mirror = next(
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_mirror_store_backed_if_needed"
    )
    assert mirror.lineno > recompute.lineno
    kw = {k.arg: k.value for k in mirror.keywords}
    assert isinstance(kw["merged_projection"], ast.Name) and kw["merged_projection"].id == "store_view"
