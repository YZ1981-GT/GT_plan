# -*- coding: utf-8 -*-
"""R3 · P8：物化计划复用三方提取里同一份 incoming 的逐 binding 结果。

spec: oo-return-to-form-dead-end-and-save-speed · R3.1

真 D4（39 binding）的 OO→HTML 形态 adapter：同一实例先 `extract(incoming)`（三方提取那一遍），
再 `materialize(substrate=incoming)`（物化计划那一遍）—— 与 `oo_to_html` 一次 apply 的顺序相同。

判据三类：

① 复用的结果与「不带 baseline 重新提取」逐字段相同，受保护格发现除外。第一遍故意给一个必然
   产生发现的 baseline（空公式清册 ⇒ 每个带公式的受保护格都记一条），证明发现确实被去掉、
   且是唯一的差异；
② 次数：一次保存里 incoming 的 `extract_projection` 从 2×N 降到 N；产物与不复用时逐 zip entry
   相同，物化结果逐字段相同（时间戳与随之变化的字节摘要除外）；
③ 不复用：换内容 / 换形态 / 换 binding / 换定义 / 换 limits / 换保留清册口径 / 有退役身份 /
   写入用的是副本 / 已发布形态的提取 —— 各自照常提取；
④ OnlyOffice 掏空 `_GT_SYNC`、物化写重注副本（真实保存几乎每次都这样）：提取不读那个隐藏 part
   （掏空与重注后逐字段相同），重注副本照样复用、产物不变；另有部件不同的副本、重注之后又换了
   一份的写入副本都不认。
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import re
import zipfile
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.services.workpaper_sync import excel_materialize as EM
from app.services.workpaper_sync import incoming_view_reuse as IVR
from app.services.workpaper_sync.adapters import excel as AX
from app.services.workpaper_sync.adapters.base import SubstrateRole
from app.services.workpaper_sync.excel_extract import (
    IdentityCarrierMissingError,
    _sheet_parts,
    extract_projection,
    read_runtime_binding_pairs,
    reinject_runtime_binding_from_base_if_needed,
)
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    _text_safe,
    build_world,
    force_chained_path,
)
from tests.workpaper_sync.test_single_pass_artifact_equivalence import (
    compare_zip_entries,
    projection_differences,
)

INCOMING_SHAPE = (SubstrateRole.incoming, ArtifactKind.incoming, ArtifactState.durable)


@contextlib.contextmanager
def counted_extractions(outcomes: dict[str, Any] | None = None) -> Iterator[list[tuple[str, str]]]:
    """数 adapter 与物化计划两处的 `extract_projection`（按调用方 + 读的文件）。

    `outcomes` 给了 ⇒ 把 adapter 那一遍返回的原始 outcome（含受保护格发现）按 table_key 收下。
    """
    calls: list[tuple[str, str]] = []
    originals = (AX.extract_projection, EM.extract_projection)

    def wrap(label: str, original: Any) -> Any:
        def counted(**kwargs: Any) -> Any:
            calls.append((label, str(Path(kwargs["artifact"]).resolve())))
            outcome = original(**kwargs)
            if outcomes is not None and label == "adapter":
                outcomes[kwargs["binding"].table_key] = outcome
            return outcome

        return counted

    AX.extract_projection = wrap("adapter", originals[0])  # type: ignore[assignment]
    EM.extract_projection = wrap("plan", originals[1])  # type: ignore[assignment]
    try:
        yield calls
    finally:
        AX.extract_projection, EM.extract_projection = originals  # type: ignore[assignment]


def _count(calls: list[tuple[str, str]], label: str, artifact: Path) -> int:
    target = str(artifact.resolve())
    return sum(1 for who, path in calls if who == label and path == target)


def _oo_adapter(world: D4World, *, siblings: tuple[Any, ...] | None = None) -> Any:
    base = world.adapter
    return AX.build_excel_adapter(
        definitions=base.definitions,
        binding=base.binding,
        sibling_bindings=base.sibling_bindings if siblings is None else siblings,
        direction="oo_to_html",
        baseline_representation=world.base,
    )


def _incoming(world: D4World, name: str, data: bytes | None = None) -> Path:
    root = world.base.parent / "incoming"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(world.base.read_bytes() if data is None else data)
    return path


@contextlib.contextmanager
def findings_forcing_baseline() -> Iterator[None]:
    """空公式清册当 baseline ⇒ 每个带公式的受保护格都记 `formula_added_to_literal_cell`。"""
    original = AX.ExcelSyncAdapter._baseline_pair
    AX.ExcelSyncAdapter._baseline_pair = lambda self: (None, {})  # type: ignore[method-assign]
    try:
        yield
    finally:
        AX.ExcelSyncAdapter._baseline_pair = original  # type: ignore[method-assign]


def _outcome_differences(left: Any, right: Any) -> list[str]:
    """两个 ExcelExtractOutcome 的逐字段差异（projection 用逐字段的严格比较）。"""
    diffs: list[str] = []
    for spec in dataclasses.fields(left):
        a, b = getattr(left, spec.name), getattr(right, spec.name)
        if spec.name == "projection":
            found = projection_differences(a, b, left_label="reused", right_label="fresh")
            if found:
                diffs.append(f"projection: {list(found[:3])}")
        elif a != b:
            diffs.append(f"{spec.name}: reused={a!r:.160} / fresh={b!r:.160}")
    return diffs


def _fresh(adapter: Any, artifact: Path, binding: Any) -> Any:
    """物化计划在不复用时会算的那一份（不带 baseline）。"""
    return extract_projection(
        artifact=artifact,
        definitions=adapter.definitions,
        binding=binding,
        substrate_role=SubstrateRole.incoming,
        artifact_kind=ArtifactKind.incoming,
        artifact_state=ArtifactState.durable,
        limits=adapter._limits,
        retain_identity_inventory=binding.table_key == adapter.binding.table_key,
    )


@dataclasses.dataclass
class Runs:
    world: D4World
    adapter: Any
    incoming: Path
    projection: Any
    views: Any
    views_before: dict[str, Any]
    raw_outcomes: dict[str, Any]
    extract_calls: list[tuple[str, str]]
    reuse_calls: list[tuple[str, str]]
    reuse_result: Any
    reuse_output: Path
    control_calls: list[tuple[str, str]]
    control_result: Any
    control_output: Path
    leftover: bool


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    return build_world(tmp_path_factory.mktemp("d4-incoming-view-reuse"))


@pytest.fixture(scope="module")
def runs(world: D4World) -> Runs:
    """同一份 incoming：复用（先 extract 再 materialize）与不复用（新实例直接 materialize）各一次。"""
    adapter = _oo_adapter(world)
    incoming = _incoming(world, "incoming-a.xlsx")
    raw: dict[str, Any] = {}
    with findings_forcing_baseline(), counted_extractions(raw) as extract_calls:
        projection = _text_safe(adapter.extract(artifact=incoming, contract=world.contract))
    views = adapter._baseline.get("incoming_views")
    assert views is not None, "OO→HTML 形态的 incoming 提取没有登记逐 binding 结果"
    views_before = copy.deepcopy(views.views)

    reuse_output = world.staged("p8-reuse.xlsx")
    with counted_extractions() as reuse_calls:
        reuse_result = adapter.materialize(
            substrate=incoming, projection=projection, output=reuse_output, contract=world.contract
        )
    leftover = "incoming_views" in adapter._baseline

    control_output = world.staged("p8-control.xlsx")
    with counted_extractions() as control_calls:
        control_result = _oo_adapter(world).materialize(
            substrate=incoming, projection=projection, output=control_output, contract=world.contract
        )
    return Runs(
        world=world, adapter=adapter, incoming=incoming, projection=projection, views=views,
        views_before=views_before, raw_outcomes=raw, extract_calls=extract_calls,
        reuse_calls=reuse_calls, reuse_result=reuse_result, reuse_output=reuse_output,
        control_calls=control_calls, control_result=control_result,
        control_output=control_output, leftover=leftover,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ① 逐字段等价
# ═══════════════════════════════════════════════════════════════════════════


def test_the_first_pass_really_had_baseline_dependent_findings(runs: Runs) -> None:
    """反空转前提：第一遍的受保护格发现非空 —— 否则「去掉发现」这一条无从验证。"""
    with_findings = [key for key, outcome in runs.raw_outcomes.items() if outcome.protected_findings]
    assert with_findings, "强制 baseline 没让任何 binding 产生受保护格发现 ⇒ 等价判据空转"
    assert len(runs.raw_outcomes) == runs.world.binding_count


def test_reused_views_equal_a_fresh_extraction_without_baseline_field_by_field(runs: Runs) -> None:
    adapter = runs.adapter
    bindings = adapter._all_bindings()
    assert set(runs.views.views) == {b.table_key for b in bindings}
    mismatched = {}
    for binding in bindings:
        reused = runs.views_before[binding.table_key][2]
        diffs = _outcome_differences(reused, _fresh(adapter, runs.incoming, binding))
        if diffs:
            mismatched[binding.table_key] = diffs[:4]
    assert mismatched == {}, f"复用结果与重新提取不同：{mismatched}"


def test_findings_are_the_only_thing_the_baseline_changed(runs: Runs) -> None:
    """原始 outcome 与复用版本只差 protected_findings。"""
    for key, raw in runs.raw_outcomes.items():
        reused = runs.views_before[key][2]
        assert reused.protected_findings == ()
        assert _outcome_differences(dataclasses.replace(raw, protected_findings=()), reused) == []


# ═══════════════════════════════════════════════════════════════════════════
# ② 次数与产物
# ═══════════════════════════════════════════════════════════════════════════


def test_one_save_extracts_the_incoming_once_per_binding(runs: Runs) -> None:
    n = runs.world.binding_count
    assert _count(runs.extract_calls, "adapter", runs.incoming) == n
    assert _count(runs.reuse_calls, "plan", runs.incoming) == 0, "物化计划又提取了一遍 incoming"
    assert _count(runs.control_calls, "plan", runs.incoming) == n, "对照组没有走提取（判据空转）"


def test_reuse_changes_nothing_in_the_staged_artifact(runs: Runs) -> None:
    cmp = compare_zip_entries(runs.reuse_output, runs.control_output)
    assert cmp.namelist_equal and cmp.name_differences == ()
    assert cmp.content_differences == (), f"产物 zip entry 不同：{cmp.content_differences}"
    noisy = {"output_path", "artifact_sha256"}  # 写盘时间戳不同 ⇒ 整包字节摘要不同
    for spec in dataclasses.fields(runs.reuse_result):
        if spec.name in noisy:
            continue
        assert getattr(runs.reuse_result, spec.name) == getattr(runs.control_result, spec.name), spec.name


def test_the_materialize_consumes_the_views_and_does_not_mutate_them(runs: Runs) -> None:
    assert runs.leftover is False, "物化后登记还在：下一次物化可能误用"
    for key, (binding, retained, outcome) in runs.views.views.items():
        before_binding, before_retained, before = runs.views_before[key]
        assert (binding, retained) == (before_binding, before_retained)
        assert _outcome_differences(outcome, before) == [], f"{key} 的复用结果被物化改写"


def test_a_different_incoming_is_extracted_again(runs: Runs) -> None:
    """登记的是 A；物化 B（字节不同）⇒ 每个 binding 照常提取。"""
    world, adapter = runs.world, _oo_adapter(runs.world)
    first = _incoming(world, "incoming-b-first.xlsx")
    other = _incoming(world, "incoming-b-other.xlsx", data=runs.reuse_output.read_bytes())
    adapter.extract(artifact=first, contract=world.contract)
    with counted_extractions() as calls:
        adapter.materialize(
            substrate=other, projection=runs.projection,
            output=world.staged("p8-other.xlsx"), contract=world.contract,
        )
    assert _count(calls, "plan", other) == world.binding_count


def test_same_bytes_at_another_path_are_reused_and_still_exact(runs: Runs) -> None:
    """按内容判（不按路径）：同一份字节换了路径照样复用，且与该路径上的重新提取逐字段相同。"""
    world, adapter = runs.world, _oo_adapter(runs.world)
    first = _incoming(world, "incoming-c-first.xlsx")
    twin = _incoming(world, "incoming-c-twin.xlsx")
    adapter.extract(artifact=first, contract=world.contract)
    views = adapter._baseline["incoming_views"]
    twin_bytes = twin.read_bytes()
    mismatched = {}
    for binding in adapter._all_bindings():
        reused = views.view_for(
            source_bytes=twin_bytes, binding=binding, shape=INCOMING_SHAPE,
            definitions=adapter.definitions, limits=adapter._limits,
            retain_identity_inventory=binding.table_key == adapter.binding.table_key,
        )
        assert reused is not None, binding.table_key
        diffs = _outcome_differences(reused, _fresh(adapter, twin, binding))
        if diffs:
            mismatched[binding.table_key] = diffs[:4]
    assert mismatched == {}, f"换路径后的复用结果与重新提取不同：{mismatched}"
    with counted_extractions() as calls:
        adapter.materialize(
            substrate=twin, projection=runs.projection,
            output=world.staged("p8-twin.xlsx"), contract=world.contract,
        )
    assert _count(calls, "plan", twin) == 0


def test_chained_fallback_reuses_only_the_trip_that_reads_the_incoming(world: D4World) -> None:
    """链式回落：首趟读 incoming（复用），后续趟读中间产物（内容不同，照常提取）；产物不变。"""
    siblings = world.adapter.sibling_bindings[:2]
    incoming = _incoming(world, "incoming-chain.xlsx")
    adapter = _oo_adapter(world, siblings=siblings)
    projection = _text_safe(adapter.extract(artifact=incoming, contract=world.contract))
    outputs = {}
    for label, subject in (("reuse", adapter), ("control", _oo_adapter(world, siblings=siblings))):
        with force_chained_path(), counted_extractions() as calls:
            subject.materialize(
                substrate=incoming, projection=projection,
                output=world.staged(f"p8-chain-{label}.xlsx"), contract=world.contract,
            )
        outputs[label] = (calls, world.staged(f"p8-chain-{label}.xlsx"))
    reuse_calls, control_calls = outputs["reuse"][0], outputs["control"][0]
    assert _count(control_calls, "plan", incoming) == 1
    assert _count(reuse_calls, "plan", incoming) == 0
    assert len([c for c in reuse_calls if c[0] == "plan"]) == len(siblings)  # 后续趟照常提取
    cmp = compare_zip_entries(outputs["reuse"][1], outputs["control"][1])
    assert cmp.content_differences == () and cmp.name_differences == ()


# ═══════════════════════════════════════════════════════════════════════════
# ③ 判据逐项：任一输入不同即不复用
# ═══════════════════════════════════════════════════════════════════════════


def _primary_view_inputs(runs: Runs) -> dict[str, Any]:
    adapter = runs.adapter
    return {
        "source_bytes": runs.incoming.read_bytes(),
        "binding": adapter.binding,
        "shape": INCOMING_SHAPE,
        "definitions": adapter.definitions,
        "limits": adapter._limits,
        "retain_identity_inventory": True,
    }


def _views_copy(runs: Runs) -> Any:
    return dataclasses.replace(runs.views, views=dict(runs.views_before), _verified=None)


def test_exact_inputs_reuse_and_string_shapes_count_as_the_same_shape(runs: Runs) -> None:
    inputs = _primary_view_inputs(runs)
    assert _views_copy(runs).view_for(**inputs) is runs.views_before[runs.adapter.binding.table_key][2]
    as_strings = dict(inputs, shape=tuple(part.value for part in INCOMING_SHAPE))
    assert _views_copy(runs).view_for(**as_strings) is not None


@pytest.mark.parametrize(
    "change",
    ["bytes", "binding", "shape", "definitions", "limits", "retain", "unknown_table"],
)
def test_any_differing_input_means_extract_again(runs: Runs, change: str) -> None:
    inputs = _primary_view_inputs(runs)
    if change == "bytes":
        inputs["source_bytes"] = runs.reuse_output.read_bytes()
    elif change == "binding":
        inputs["binding"] = dataclasses.replace(inputs["binding"], tombstoned_row_keys=("tomb-x",))
    elif change == "shape":
        inputs["shape"] = (
            SubstrateRole.published_representation, ArtifactKind.canonical, ArtifactState.published,
        )
    elif change == "definitions":
        inputs["definitions"] = dataclasses.replace(inputs["definitions"])
    elif change == "limits":
        inputs["limits"] = dataclasses.replace(
            inputs["limits"], max_zip_entries=inputs["limits"].max_zip_entries + 1
        )
    elif change == "retain":
        inputs["retain_identity_inventory"] = False
    else:
        inputs["binding"] = dataclasses.replace(inputs["binding"], table_key="not-a-table")
    assert _views_copy(runs).view_for(**inputs) is None


def test_extracts_that_are_not_incoming_or_carry_retired_identities_record_nothing(runs: Runs) -> None:
    world = runs.world
    published = world.adapter  # html_to_oo 形态：读同一个文件也按已发布形态
    published._baseline.pop("incoming_views", None)
    published.extract(artifact=runs.incoming, contract=world.contract)
    assert "incoming_views" not in published._baseline

    adapter = _oo_adapter(world)
    remember = IVR.record_incoming_views(
        adapter, artifact=runs.incoming, shape=INCOMING_SHAPE, retired=("retired-row",)
    )
    remember(adapter.binding, True, runs.raw_outcomes[adapter.binding.table_key])
    assert "incoming_views" not in adapter._baseline

    # 已有 incoming 登记时，读 base（已发布形态）不清掉它。
    adapter._baseline["incoming_views"] = marker = object()
    adapter.extract(artifact=world.base, contract=world.contract)
    assert adapter._baseline.get("incoming_views") is marker


def test_writing_through_a_repaired_copy_takes_nothing_but_still_drops_the_record(runs: Runs) -> None:
    adapter = _oo_adapter(runs.world)
    adapter._baseline["incoming_views"] = _views_copy(runs)
    assert IVR.take_incoming_views(adapter, runs.incoming, runs.incoming.with_name("x.xlsx")) is None
    assert "incoming_views" not in adapter._baseline
    adapter._baseline["incoming_views"] = views = _views_copy(runs)
    assert IVR.take_incoming_views(adapter, runs.incoming, runs.incoming) is views


# ═══════════════════════════════════════════════════════════════════════════
# ④ OnlyOffice 掏空 `_GT_SYNC` ⇒ 物化写重注副本：仍复用（真实保存几乎每次都是这条）
# ═══════════════════════════════════════════════════════════════════════════


def _rewrite_part(source: Path, target: Path, part: str, edit: Any) -> None:
    with zipfile.ZipFile(source) as zf:
        items = [(info, zf.read(info.filename)) for info in zf.infolist()]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in items:
            out.writestr(info, edit(data) if info.filename == part else data)


def _hollowed(world: D4World, name: str) -> Path:
    """模拟 OnlyOffice 保存：`_GT_SYNC` 的清册项还在，worksheet part 的 sheetData 被清空。"""
    with zipfile.ZipFile(world.base) as zf:
        part = _sheet_parts(zf)[world.adapter.binding.metadata_sheet]
    target = _incoming(world, name)
    _rewrite_part(world.base, target, part, lambda data: re.sub(
        rb"<sheetData>.*</sheetData>", b"<sheetData/>", data, flags=re.S))
    with zipfile.ZipFile(target) as zf, pytest.raises(IdentityCarrierMissingError):
        read_runtime_binding_pairs(zf, metadata_sheet=world.adapter.binding.metadata_sheet)
    return target


@pytest.fixture(scope="module")
def hollow(world: D4World) -> tuple[Path, Path]:
    incoming = _hollowed(world, "incoming-hollow.xlsx")
    repaired = reinject_runtime_binding_from_base_if_needed(
        incoming=incoming, base=world.base, metadata_sheet=world.adapter.binding.metadata_sheet
    )
    assert repaired is not None, "掏空后没有走重注 —— 判据前提不成立"
    return incoming, repaired


#: 写入计划读复用结果的哪些字段（`excel_materialize` 里对 substrate view 的全部属性访问）。
_PLAN_READS = {"region", "scan", "formula_inventory", "projection", "identity_inventory"}


def _substrate_view_attributes() -> set[str]:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(EM))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            owner = node.value
            owner_name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", None)
            if owner_name == "substrate_view":
                names.add(node.attr)
    return names


def test_extraction_does_not_read_the_runtime_binding_part(world: D4World, hollow: tuple[Path, Path]) -> None:
    """掏空的 incoming 与重注副本，逐 binding 的提取结果只差文件大小统计 —— 复用重注副本的前提。

    `stats` 的 archive / expanded 字节数随隐藏 part 变（那是读文件的预算统计）；写入计划不读
    `stats`（下面按源码钉住它读的字段集合），其余字段逐项相同。
    """
    incoming, repaired = hollow
    adapter = _oo_adapter(world)
    mismatched = {}
    for binding in adapter._all_bindings():
        left, right = _fresh(adapter, incoming, binding), _fresh(adapter, repaired, binding)
        diffs = _outcome_differences(dataclasses.replace(left, stats=None), dataclasses.replace(right, stats=None))
        size_only = {"archive_bytes", "expanded_bytes"}
        stats_diffs = [f.name for f in dataclasses.fields(left.stats)
                       if getattr(left.stats, f.name) != getattr(right.stats, f.name) and f.name not in size_only]
        if diffs or stats_diffs:
            mismatched[binding.table_key] = diffs[:4] + stats_diffs
    assert mismatched == {}, f"重注 runtime binding 改变了提取结果：{mismatched}"
    assert _substrate_view_attributes() == _PLAN_READS, "写入计划读的字段变了 —— 先确认新字段不随隐藏 part 变"


def test_a_hollowed_incoming_still_reuses_through_the_reinjected_copy(world: D4World) -> None:
    incoming = _hollowed(world, "incoming-hollow-e2e.xlsx")
    adapter = _oo_adapter(world)
    projection = _text_safe(adapter.extract(artifact=incoming, contract=world.contract))
    with counted_extractions() as reuse_calls:
        adapter.materialize(
            substrate=incoming, projection=projection,
            output=world.staged("p8-hollow-reuse.xlsx"), contract=world.contract,
        )
    with counted_extractions() as control_calls:
        _oo_adapter(world).materialize(
            substrate=incoming, projection=projection,
            output=world.staged("p8-hollow-control.xlsx"), contract=world.contract,
        )
    plan = lambda calls: [path for who, path in calls if who == "plan"]  # noqa: E731
    assert len(plan(control_calls)) == world.binding_count, "对照组没有走重注副本的提取（判据空转）"
    assert all(path.endswith(".gtsync-repaired.xlsx") for path in plan(control_calls))
    assert plan(reuse_calls) == [], "物化计划又提取了一遍（重注副本没被认作同一份 incoming）"
    cmp = compare_zip_entries(world.staged("p8-hollow-reuse.xlsx"), world.staged("p8-hollow-control.xlsx"))
    assert cmp.namelist_equal and cmp.name_differences == () and cmp.content_differences == ()


def test_only_the_reinjected_copy_and_only_a_runtime_binding_difference_is_accepted(
    runs: Runs, hollow: tuple[Path, Path]
) -> None:
    world, adapter = runs.world, _oo_adapter(runs.world)
    incoming, repaired = hollow
    sheet = adapter.binding.metadata_sheet
    assert IVR._differs_only_in_sheet(incoming, repaired, sheet)

    # 另一个部件也不同（如业务 sheet 被改）的「副本」不认。
    with zipfile.ZipFile(repaired) as zf:
        parts = _sheet_parts(zf)
    business_part = next(part for name, part in parts.items() if name != sheet)
    tampered = repaired.with_name("p8-tampered.xlsx")
    _rewrite_part(repaired, tampered, business_part, lambda data: data + b" ")
    assert not IVR._differs_only_in_sheet(incoming, tampered, sheet)
    adapter._baseline["incoming_views"] = _views_copy(runs)
    assert IVR.take_incoming_views(adapter, incoming, tampered, reinjected=tampered) is None

    # 写入用的不是重注那一份（如重注后再做的 G7 中性化副本）⇒ 不认，即使重注那一份本身合格。
    g7 = repaired.with_name(repaired.name + ".g7-noif.xlsx")
    g7.write_bytes(repaired.read_bytes())
    adapter._baseline["incoming_views"] = _views_copy(runs)
    assert IVR.take_incoming_views(adapter, incoming, g7, reinjected=repaired) is None

    adapter._baseline["incoming_views"] = views = _views_copy(runs)
    assert IVR.take_incoming_views(adapter, incoming, repaired, reinjected=repaired) is views
    assert views.alias_sha256 is not None
