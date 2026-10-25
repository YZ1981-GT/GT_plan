# -*- coding: utf-8 -*-
"""R3 · P9：已发布形态 / 物化反读的整簿提取结果跨请求缓存。

spec: oo-return-to-form-dead-end-and-save-speed · R3.2

真 D4（39 binding）world。判据：

① 命中与重新提取逐字段相同；命中时 adapter 一次 `extract_projection` 都不跑；
② 键覆盖全部输入：文件字节、契约、冻结定义的每个字段（含 `as_dict()` 摘要不覆盖的 identity
   清册字段）、每个 binding 的每个字段与顺序、limits —— 任一项变化键都变；
③ incoming 与带退役身份的提取既不查也不填；
④ 读冻结 base 时，命中与未命中都给 `_baseline["pair"]` 填同一份主 binding 结果；读别的已发布文件不填；
⑤ 物化反读填入后，「上次物化的产物」作为下一次的 base 读即命中（第二次保存的形态）；
⑥ merge / overlay 不改写缓存值；`clear_all_parse_caches()` 清掉它；有界。
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from app.services.workpaper_sync import parse_cache as PC
from app.services.workpaper_sync import published_extract_cache as PEC
from app.services.workpaper_sync.adapters import excel as AX
from app.services.workpaper_sync.excel_extract import extract_projection
from app.services.workpaper_sync.merge import merge_projections
from app.services.workpaper_sync.models import DefinitionState
from app.services.workpaper_sync.projection_first_publication import (
    overlay_store_on_baseline_projection,
)
from tests.workpaper_sync.d4_materialize_harness import D4World, _text_safe, build_world
from tests.workpaper_sync.test_single_pass_artifact_equivalence import projection_differences


@contextlib.contextmanager
def counted_adapter_extractions() -> Iterator[list[str]]:
    calls: list[str] = []
    original = AX.extract_projection

    def counted(**kwargs: Any) -> Any:
        calls.append(str(Path(kwargs["artifact"]).resolve()))
        return original(**kwargs)

    AX.extract_projection = counted  # type: ignore[assignment]
    try:
        yield calls
    finally:
        AX.extract_projection = original  # type: ignore[assignment]


def _clone(world: D4World, *, baseline: Path | None = None, direction: str = "html_to_oo") -> Any:
    """同一冻结定义 / binding 的新实例（模拟下一个请求）。"""
    a = world.adapter
    return AX.build_excel_adapter(
        definitions=a.definitions,
        binding=a.binding,
        sibling_bindings=a.sibling_bindings,
        direction=direction,
        baseline_representation=baseline,
    )


def _copy(world: D4World, name: str, data: bytes) -> Path:
    root = world.base.parent / "published"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(data)
    return path


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    return build_world(tmp_path_factory.mktemp("d4-published-extract-cache"))


@pytest.fixture(autouse=True)
def _isolated_cache() -> Iterator[None]:
    PC.clear_all_parse_caches()
    yield
    PC.clear_all_parse_caches()


# ═══════════════════════════════════════════════════════════════════════════
# ① 命中 = 重新提取
# ═══════════════════════════════════════════════════════════════════════════


def test_a_hit_equals_a_fresh_extraction_and_runs_no_extraction(world: D4World) -> None:
    first = _clone(world).extract(artifact=world.base, contract=world.contract)
    assert PC.PUBLISHED_EXTRACT_CACHE.stats["size"] == 1
    with counted_adapter_extractions() as calls:
        hit = _clone(world).extract(artifact=world.base, contract=world.contract)
    assert calls == [], "命中仍跑了提取"
    assert hit is first
    PC.clear_all_parse_caches()
    with counted_adapter_extractions() as calls:
        fresh = _clone(world).extract(artifact=world.base, contract=world.contract)
    assert len(calls) == world.binding_count, "清缓存后没有重新提取（判据空转）"
    assert projection_differences(hit, fresh, left_label="hit", right_label="fresh") == ()


# ═══════════════════════════════════════════════════════════════════════════
# ② 键覆盖全部输入
# ═══════════════════════════════════════════════════════════════════════════


def _stand_in(adapter: Any, **changes: Any) -> Any:
    """`published_extract_key` 只读 definitions / _all_bindings() / _limits —— 用替身改单项。"""
    definitions = changes.get("definitions", adapter.definitions)
    bindings = changes.get("bindings", adapter._all_bindings())
    limits = changes.get("limits", adapter._limits)
    return SimpleNamespace(definitions=definitions, _all_bindings=lambda: bindings, _limits=limits)


def _variants(world: D4World) -> dict[str, dict[str, Any]]:
    a = world.adapter
    d, bindings, lim = a.definitions, a._all_bindings(), a._limits
    inv = d.identity_inventory
    first, *rest = bindings
    other_state = next(state for state in DefinitionState if state is not d.bundle.state)
    return {
        "bundle.state": {"definitions": dataclasses.replace(
            d, bundle=dataclasses.replace(d.bundle, state=other_state))},
        "bundle.schema_version": {"definitions": dataclasses.replace(
            d, bundle=dataclasses.replace(d.bundle, schema_version=d.bundle.schema_version + "-x"))},
        "adapter_build": {"definitions": dataclasses.replace(
            d, adapter_build=dataclasses.replace(d.adapter_build, adapter_build_digest="0" * 64))},
        # `FrozenEntryDefinitions.as_dict()` 只摘 identity 清册的三项；这一项它不覆盖。
        "identity_inventory.uuid_column_hidden": {"definitions": dataclasses.replace(
            d, identity_inventory=dataclasses.replace(inv, uuid_column_hidden=not inv.uuid_column_hidden))},
        "business_sheets": {"definitions": dataclasses.replace(d, business_sheets=(*d.business_sheets, "x"))},
        "dynamic_column_keys": {"definitions": dataclasses.replace(d, dynamic_column_keys={"t": ("c",)})},
        "structure_inventory_size": {"definitions": dataclasses.replace(
            d, structure_inventory_size=d.structure_inventory_size + 1)},
        "binding.tombstones": {"bindings": (
            dataclasses.replace(first, tombstoned_row_keys=("tomb",)), *rest)},
        "binding.dynamic_columns": {"bindings": (
            dataclasses.replace(first, dynamic_column_columns={"t": {"c_1": "Z"}}), *rest)},
        "binding.order": {"bindings": (first, *reversed(rest))},
        "binding.dropped": {"bindings": (first, *rest[:-1])},
        "limits": {"limits": dataclasses.replace(lim, max_table_rows=lim.max_table_rows + 1)},
        "limits.ooxml": {"limits": dataclasses.replace(
            lim, ooxml=dataclasses.replace(lim.ooxml, policy_version=str(lim.ooxml.policy_version) + "x"))},
    }


def test_the_key_changes_with_every_input(world: D4World) -> None:
    a = world.adapter
    base_key = PEC.published_extract_key(_stand_in(a), artifact=world.base, contract=world.contract)
    assert PEC.published_extract_key(_stand_in(a), artifact=world.base, contract=world.contract) == base_key
    other_bytes = _copy(world, "key-bytes.xlsx", world.base.read_bytes() + b"\0")
    assert PEC.published_extract_key(_stand_in(a), artifact=other_bytes, contract=world.contract) != base_key
    other_contract = SimpleNamespace(canonical_sha256="f" * 64)
    assert PEC.published_extract_key(_stand_in(a), artifact=world.base, contract=other_contract) != base_key
    same = [
        name
        for name, change in _variants(world).items()
        if PEC.published_extract_key(_stand_in(a, **change), artifact=world.base, contract=world.contract)
        == base_key
    ]
    assert same == [], f"这些输入变了键却没变：{same}"


def test_same_bytes_at_another_path_hit(world: D4World) -> None:
    """键按内容不按路径（已发布 artifact 是内容寻址的不可变字节）。"""
    _clone(world).extract(artifact=world.base, contract=world.contract)
    twin = _copy(world, "twin.xlsx", world.base.read_bytes())
    with counted_adapter_extractions() as calls:
        _clone(world).extract(artifact=twin, contract=world.contract)
    assert calls == []


# ═══════════════════════════════════════════════════════════════════════════
# ③ incoming / 退役身份不查不填
# ═══════════════════════════════════════════════════════════════════════════


def test_incoming_and_retired_reads_neither_look_up_nor_fill(world: D4World) -> None:
    cache = PC.PUBLISHED_EXTRACT_CACHE
    oo = _clone(world, baseline=world.base, direction="oo_to_html")
    incoming = _copy(world, "incoming.xlsx", world.base.read_bytes())
    before = dict(cache.stats)
    oo.extract(artifact=incoming, contract=world.contract)
    after = dict(cache.stats)
    assert (after["size"], after["hits"], after["misses"]) == (before["size"], before["hits"], before["misses"])

    cached, recorder = PEC.begin_extract(
        _clone(world), artifact=world.base, contract=world.contract,
        shape=AX.ExcelSyncAdapter._substrate_shape_of(_clone(world), world.base), retired=("retired-row",),
    )
    assert cached is None and recorder.finish("projection") == "projection"
    assert dict(cache.stats)["size"] == 0 and dict(cache.stats)["misses"] == after["misses"]


# ═══════════════════════════════════════════════════════════════════════════
# ④ ⑤ 冻结 base 的 pair 与「上次物化产物」作为下次 base
# ═══════════════════════════════════════════════════════════════════════════


def _primary_pair(adapter: Any, artifact: Path) -> tuple[Any, dict[str, str]]:
    outcome = extract_projection(
        artifact=artifact, definitions=adapter.definitions, binding=adapter.binding,
        substrate_role=AX.SubstrateRole.published_representation,
        artifact_kind=AX.ArtifactKind.canonical, artifact_state=AX.ArtifactState.published,
        limits=adapter._limits, retain_identity_inventory=True,
    )
    return outcome.projection, dict(outcome.formula_inventory)


def test_frozen_base_reads_seed_the_same_pair_on_miss_and_on_hit(world: D4World) -> None:
    expected_projection, expected_formulas = _primary_pair(world.adapter, world.base)
    miss = _clone(world, baseline=world.base, direction="oo_to_html")
    miss.extract(artifact=world.base, contract=world.contract)
    hit = _clone(world, baseline=world.base, direction="oo_to_html")
    with counted_adapter_extractions() as calls:
        hit.extract(artifact=world.base, contract=world.contract)
    assert calls == []
    for adapter in (miss, hit):
        projection, formulas = adapter._baseline["pair"]
        assert projection_differences(projection, expected_projection) == ()
        assert formulas == expected_formulas


def test_a_published_read_of_another_file_never_seeds_the_frozen_base_pair(world: D4World) -> None:
    """pair 只取自冻结 base 本身：带了 base 的 adapter 读另一份已发布形态（html_to_oo 下非 base 文件都判
    已发布）不得填 pair —— 否则受保护格篡改分类拿错基线；随后读 base 照常填。"""
    other = _copy(world, "p9-other-published.xlsx", world.materialize("p9-other.xlsx").read_bytes())
    adapter = _clone(world, baseline=world.base, direction="html_to_oo")
    assert adapter._substrate_shape_of(other)[0] is AX.SubstrateRole.published_representation
    adapter.extract(artifact=other, contract=world.contract)
    assert "pair" not in adapter._baseline, "读的不是冻结 base 却填了 pair"
    adapter.extract(artifact=world.base, contract=world.contract)
    projection, formulas = adapter._baseline["pair"]
    expected_projection, expected_formulas = _primary_pair(world.adapter, world.base)
    assert projection_differences(projection, expected_projection) == ()
    assert formulas == expected_formulas


def test_the_staged_readback_makes_the_next_base_read_a_hit(world: D4World) -> None:
    """第二次保存：base = 上次物化的产物。物化后的反读（staged 形态）填入，发布后的同一份字节命中。"""
    staged = world.materialize("p9-staged.xlsx")
    readback = _clone(world).extract(artifact=staged, contract=world.contract)
    published = _copy(world, "published-gen.xlsx", staged.read_bytes())
    next_save = _clone(world, baseline=published, direction="oo_to_html")
    with counted_adapter_extractions() as calls:
        base = next_save.extract(artifact=published, contract=world.contract)
    assert calls == [] and base is readback
    projection, formulas = next_save._baseline["pair"]
    expected_projection, expected_formulas = _primary_pair(world.adapter, published)
    assert projection_differences(projection, expected_projection) == ()
    assert formulas == expected_formulas


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ 只读、可清、有界
# ═══════════════════════════════════════════════════════════════════════════


def test_merge_and_overlay_do_not_rewrite_the_cached_value(world: D4World) -> None:
    cached = _clone(world).extract(artifact=world.base, contract=world.contract)
    snapshot = copy.deepcopy(cached)
    value = next(iter(PC.PUBLISHED_EXTRACT_CACHE._store.values()))
    pair_snapshot = copy.deepcopy(value.primary_pair)
    incoming = _text_safe(cached)
    merge_projections(base=cached, current=cached, incoming=incoming, contract=world.contract)
    overlay_store_on_baseline_projection(baseline=cached, store_projection=incoming)
    assert projection_differences(cached, snapshot, left_label="after", right_label="before") == ()
    assert projection_differences(value.primary_pair[0], pair_snapshot[0]) == ()
    assert value.primary_pair[1] == pair_snapshot[1]


def test_clear_all_parse_caches_empties_it_and_it_is_bounded(world: D4World) -> None:
    _clone(world).extract(artifact=world.base, contract=world.contract)
    assert PC.PUBLISHED_EXTRACT_CACHE.stats["size"] == 1
    PC.clear_all_parse_caches()
    assert PC.PUBLISHED_EXTRACT_CACHE.stats["size"] == 0
    assert PC.PUBLISHED_EXTRACT_CACHE.stats["maxsize"] == 16


def test_an_uncanonicalisable_input_skips_the_cache_instead_of_guessing(world: D4World) -> None:
    odd = _stand_in(world.adapter, limits=object())
    with pytest.raises(PEC._Uncacheable):
        PEC.published_extract_key(odd, artifact=world.base, contract=world.contract)
    odd.baseline_representation, odd._baseline = None, {}
    shape = AX.ExcelSyncAdapter._substrate_shape_of(_clone(world), world.base)
    cached, recorder = PEC.begin_extract(
        odd, artifact=world.base, contract=world.contract, shape=shape, retired=()
    )
    assert cached is None
    recorder.finish("projection")
    assert PC.PUBLISHED_EXTRACT_CACHE.stats["size"] == 0, "规范化失败的输入不该进缓存"
