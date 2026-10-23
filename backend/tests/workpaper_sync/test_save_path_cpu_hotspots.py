# -*- coding: utf-8 -*-
"""双向回写 CPU 热点与事件循环阻塞的等价守卫（spec workpaper-sync-save-path-cpu-hotspots）。

* R1 物化单格解析：`_cell_view` 与「逐格编译正则 + search」逐字段相同（真实 D2 模板 + 边界）。
* R2 契约键索引：三个消费方开 / 关索引逐条对拍（真实契约 + 构造的边界键）；关索引 = 契约外包
  一层、藏起 `template_candidate_indices`，三个消费方自动回到原来的全量扫描。
* R3 去重复提取：current 与 base 同 artifact 不再提取；published 形态不先算 baseline，base 主
  binding 的结果填进 baseline 缓存，且与 `derive_baseline_from_representation` 相同。
* R4 事件循环：三方提取在工作线程执行、阶段顺序不变；合并经 `asyncio.to_thread`。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import os
import random
import re
import shutil
import sys
import textwrap
import threading
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import endpoint_payloads as EP  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_rematerialize as XR  # noqa: E402
from app.services.workpaper_sync import merge as G  # noqa: E402
from app.services.workpaper_sync import oo_to_html as OH  # noqa: E402
from app.services.workpaper_sync import pilot_d2_large_json as P  # noqa: E402
from app.services.workpaper_sync import projection_first_publication as F  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ROW_UUID_PLACEHOLDER,
    SyncContract,
    load_contract,
)
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_CONTRACT_DIR = _BACKEND / "data" / "workpaper_sync_contracts"
#: 全量扫描参照的抽样：最大的几份 + 每隔 8 份取 1 份（全量 95 份 × 全量扫描约 20 s）。
_SWEEP_EVERY = 8


def _outcome(fn: Any) -> Any:
    try:
        return ("ok", fn())
    except Exception as exc:  # noqa: BLE001 - 对拍要的就是异常类型与文案
        return (type(exc).__name__, str(exc))


class _NoIndex:
    """契约外包一层并藏起 `template_candidate_indices` ⇒ 消费方回到全量扫描（参照实现）。"""

    def __init__(self, contract: SyncContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str) -> Any:
        if name == "template_candidate_indices":
            raise AttributeError(name)
        return getattr(self._contract, name)


def _keys_for(contract: SyncContract) -> list[tuple[str, str | None]]:
    """每个模板：合法实例化 / 空占位段 / 多一段 / 少一段 / 末段改名 / 模板原样 / 行域标志相反。"""
    out: list[tuple[str, str | None]] = []
    for spec in contract.all_fields():
        template = spec.stable_field_key
        segments = template.split("/")
        row = "r1" if spec.row_scoped else None
        valid = template.replace(ROW_UUID_PLACEHOLDER, "r1")
        out += [
            (valid, row),
            (template.replace(ROW_UUID_PLACEHOLDER, ""), "" if spec.row_scoped else None),
            (valid + "/x", row),
            ("/".join(valid.split("/")[:-1]), row),
            (valid + "_typo", row),
            (template, row),
            (valid, None if spec.row_scoped else "r1"),
        ]
        if len(segments) > 1:
            out.append(("/".join(["zz"] + valid.split("/")[1:]), row))
    return list(dict.fromkeys(out))


def _loadable_contracts() -> list[SyncContract]:
    """目录里能通过强校验的契约（`_` 前缀是示例；少数草稿缺已发布定义引用，`load_contract` 拒收）。"""
    out = []
    for path in sorted(_CONTRACT_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            out.append(load_contract(path.stem))
        except Exception:  # noqa: BLE001 - 草稿契约不在本守卫范围
            continue
    return out


_ALL = _loadable_contracts()


def _sweep_contracts() -> list[SyncContract]:
    loaded = _ALL
    by_size = sorted(loaded, key=lambda c: -len(c.all_fields()))
    picked = {c.contract_id: c for c in by_size[:4] + loaded[::_SWEEP_EVERY]}
    picked[P.load_pilot_contract().contract_id] = P.load_pilot_contract()
    return list(picked.values())


_SWEEP = _sweep_contracts()


def test_all_real_contracts_load_and_cover_every_template_once() -> None:
    """全部真实契约：每个模板的合法实例化都以它自己为候选，候选升序、无越界。"""
    contracts = _ALL
    assert len(contracts) >= 60, len(contracts)
    for contract in contracts:
        fields = contract.all_fields()
        for position, spec in enumerate(fields):
            key = spec.stable_field_key.replace(ROW_UUID_PLACEHOLDER, "r1")
            got = contract.template_candidate_indices(key)
            assert position in got, (contract.contract_id, key, got)
            assert list(got) == sorted(set(got)) and all(0 <= i < len(fields) for i in got)


@pytest.mark.parametrize("contract", _SWEEP, ids=[c.contract_id for c in _SWEEP])
def test_projection_contract_check_matches_full_scan(contract: SyncContract) -> None:
    for key, row_key in _keys_for(contract):
        spec = contract.all_fields()[0]
        value = FieldValue(stable_key=key, value="x", value_type=spec.value_type, mode=spec.mode, row_key=row_key)
        projection = Projection(
            contract_id=contract.contract_id, semantic_version=contract.semantic_version,
            document_type=contract.document_type, values={key: value},
        )
        fast = _outcome(lambda: projection.assert_matches_contract(contract))
        slow = _outcome(lambda: projection.assert_matches_contract(_NoIndex(contract)))
        assert fast == slow, (contract.contract_id, key, row_key)


@pytest.mark.parametrize("contract", _SWEEP, ids=[c.contract_id for c in _SWEEP])
def test_merge_locator_matches_full_scan(contract: SyncContract) -> None:
    fast_index, slow_index = G.ContractIndex(contract), G.ContractIndex(_NoIndex(contract))
    assert fast_index._candidates_of is not None and slow_index._candidates_of is None
    for key, _row in _keys_for(contract):
        fast = _outcome(lambda: fast_index.resolve(key))
        slow = _outcome(lambda: slow_index.resolve(key))
        assert fast == slow, (contract.contract_id, key)


@pytest.mark.parametrize("contract", _SWEEP, ids=[c.contract_id for c in _SWEEP])
def test_payload_key_resolution_matches_full_scan(contract: SyncContract) -> None:
    templates = {s.stable_field_key for s in contract.all_fields() if s.row_scoped}
    candidates = EP._row_scoped_candidates_of(contract)
    assert candidates is not None and EP._row_scoped_candidates_of(_NoIndex(contract)) is None
    for key, row_key in _keys_for(contract):
        kwargs = dict(contract=contract, row_key=row_key, row_scoped_templates=templates)
        fast = _outcome(lambda: EP._resolve_stable_key(key, candidates=candidates, **kwargs))
        slow = _outcome(lambda: EP._resolve_stable_key(key, **kwargs))
        assert fast == slow, (contract.contract_id, key, row_key)


def test_build_projection_wires_the_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """生产 `build_projection` 确实走候选（而不是只在测试里调了候选函数）。"""
    contract = P.load_pilot_contract()
    seen: list[Any] = []
    real = EP._resolve_stable_key

    def spy(key: str, **kwargs: Any) -> Any:
        seen.append(kwargs.get("candidates"))
        return real(key, **kwargs)

    monkeypatch.setattr(EP, "_resolve_stable_key", spy)
    template = next(s.stable_field_key for s in contract.all_fields() if s.row_scoped)
    key = template.replace(ROW_UUID_PLACEHOLDER, "r1")
    EP.build_projection(payload={"values": {key: {"value": "x", "row_key": "r1"}}}, contract=contract)
    assert seen and callable(seen[0])


def test_candidate_indices_are_a_sorted_superset_on_overlapping_templates() -> None:
    """多个模板同时命中时（真实契约里没有），候选必须全部列出且按 all_fields 原序。"""
    templates = ["t/{row_uuid}/x", "t/y/{row_uuid}", "t/y/x", "t/{row_uuid}/{row_uuid}", "u/{row_uuid}/x"]
    fake = SimpleNamespace(
        all_fields=lambda: tuple(SimpleNamespace(stable_field_key=t) for t in templates)
    )
    assert SyncContract.template_candidate_indices(fake, "t/y/x") == (0, 1, 2, 3)
    assert SyncContract.template_candidate_indices(fake, "t//x") == (0, 3)
    assert SyncContract.template_candidate_indices(fake, "t/y") == ()
    # 分组建立顺序与下标顺序不一致时仍须按下标升序（merge 多命中报错列出的顺序取决于它）
    later = ["q/{row_uuid}/x", "t/y/{row_uuid}", "t/{row_uuid}/x"]
    fake2 = SimpleNamespace(all_fields=lambda: tuple(SimpleNamespace(stable_field_key=t) for t in later))
    assert SyncContract.template_candidate_indices(fake2, "t/y/x") == (1, 2)


# ═══════════════════════════════════════════════════════════════════════════
# R1 物化单格解析
# ═══════════════════════════════════════════════════════════════════════════

_OLD_CELL_RE_TPL = (
    '(?:<c r="{coord}"(?P<selfattrs>(?:\\s[^>]*?)?)/>)'
    '|(?:<c r="{coord}"(?P<attrs>(?:\\s[^>]*?)?)>(?P<body>.*?)</c>)'
)


def _old_cell_view(xml: str, coord: str) -> Any:
    """修复前的实现（逐格编译 + search），作参照。"""
    found = re.compile(_OLD_CELL_RE_TPL.format(coord=re.escape(coord)), re.S).search(xml)
    if found is None:
        return None
    attrs = found.group("selfattrs") or found.group("attrs") or ""
    body = found.group("body") or ""
    formula = M._FORMULA_RE.search(body)
    text = shared_ref = None
    formula_attrs = ""
    if formula is not None:
        raw_text = formula.group("text")
        text = M._xml_unescape(raw_text) if raw_text else ""
        formula_attrs = formula.group("fattrs") or ""
        ref = re.search(r'\bref="([^"]+)"', formula_attrs)
        shared_ref = ref.group(1) if ref else None
    return M._CellView(
        coord=coord, raw=found.group(0), attrs=attrs, body=body,
        formula_text=text, shared_ref=shared_ref, formula_attrs=formula_attrs,
    )


def test_cell_template_string_is_unchanged() -> None:
    assert M._CELL_RE_TPL == _OLD_CELL_RE_TPL


def test_cell_view_handles_decoys_and_prefix_collisions() -> None:
    xml = (
        '<row r="1"><c r="A1"x/><c r="A1" s="3"/><c r="A10"><v>9</v></c>'
        '<c r="B1" t="s"><v>1</v></c><c r="C1" s="2"><f t="shared" ref="C1:C5" si="0">'
        'SUM(A1:&quot;B&quot;)</f><v>2</v></c><c r="C2"><f t="shared" si="0"/></c></row>'
    )
    for coord in ("A1", "A10", "B1", "C1", "C2", "A100", "Z9"):
        assert M._cell_view(xml, coord) == _old_cell_view(xml, coord), coord
    assert M._cell_view(xml, "A1").raw == '<c r="A1" s="3"/>'


@pytest.fixture(scope="module")
def d2_contract() -> Any:
    return P.load_pilot_contract()


@pytest.fixture(scope="module")
def d2_staged(d2_contract: Any, tmp_path_factory: pytest.TempPathFactory) -> Any:
    return F.stage_instrumented_substrate(
        entry_id=P.PILOT_ENTRY_ID, staging_dir=tmp_path_factory.mktemp("save-path"), contract=d2_contract
    )


def test_cell_view_matches_old_on_every_sheet_of_the_d2_template(d2_staged: Any) -> None:
    rng = random.Random(20261023)
    checked = 0
    with zipfile.ZipFile(d2_staged.staged_path) as zf:
        parts = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        for part in parts:
            xml = zf.read(part).decode("utf-8")
            coords = [f"{m.group(1) or m.group(3)}{m.group(2) or m.group(4)}" for m in M._ANY_CELL_RE.finditer(xml)]
            sample = coords[:150] + coords[-30:] + rng.sample(coords, min(80, len(coords))) + ["ZZ99999"]
            index = M.build_sheet_cell_index(xml)
            for coord in dict.fromkeys(sample):
                old = _old_cell_view(xml, coord)
                assert M._cell_view(xml, coord) == old, (part, coord)
                if old is not None and index.span(coord) is not None:
                    assert index.view(coord) == _old_cell_view(xml[slice(*index.span(coord))], coord)
                checked += 1
    assert len(parts) >= 3 and checked >= 500


# ═══════════════════════════════════════════════════════════════════════════
# R3 去重复提取（ExcelSyncAdapter）
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _oo_adapter(contract: Any, staged: Any) -> Any:
    """与 `OoToHtmlCoordinator._adapter_for_oo_to_html` 同形：incoming 方向 + 冻结 base。"""
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(), bundle_sha256=_d("save-path-bundle"), schema_version="definition-bundle:v1",
        state=DefinitionState.approved, authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(), authority_model_definition_sha256=_d("save-path-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(BundleSlot.instrumentation, contract.instrumentation_definition_sha256),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    definitions = FrozenEntryDefinitions(
        entry_id=P.PILOT_ENTRY_ID, bundle=bundle, contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID, adapter_build_digest=_d("save-path-build"),
            document_type="xlsx", contract_version=str(contract.semantic_version),
        ),
        identity_inventory=staged.identity_inventory, business_sheets=(), dynamic_column_keys={},
        structure_inventory_size=0,
    )
    primary = F._identity_binding(provider=P, staged=staged, contract=contract)
    siblings = F._sibling_identity_bindings(provider=P, staged=staged, contract=contract, primary=primary)
    return AX.build_excel_adapter(
        definitions=definitions, binding=primary, direction="oo_to_html",
        baseline_representation=staged.staged_path, sibling_bindings=siblings,
    )


def test_published_read_skips_baseline_and_seeds_it_identically(
    d2_contract: Any, d2_staged: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = XR.derive_baseline_from_representation
    calls: list[Any] = []
    monkeypatch.setattr(
        XR, "derive_baseline_from_representation", lambda **kw: calls.append(kw) or real(**kw)
    )
    adapter = _oo_adapter(d2_contract, d2_staged)
    adapter.extract(artifact=d2_staged.staged_path, contract=d2_contract)
    assert calls == [], "读冻结 base（published）不需要 baseline"
    seeded = adapter._baseline["pair"]
    expected = real(
        representation=d2_staged.staged_path, definitions=adapter.definitions,
        binding=adapter.binding, limits=adapter._limits,
    )
    assert seeded[0] == expected[0] and dict(seeded[1]) == dict(expected[1])

    incoming = tmp_path / "incoming.xlsx"
    shutil.copyfile(d2_staged.staged_path, incoming)
    got = adapter.extract(artifact=incoming, contract=d2_contract)
    assert calls == [], "incoming 形态命中已填的 baseline"
    fresh = _oo_adapter(d2_contract, d2_staged)
    want = fresh.extract(artifact=incoming, contract=d2_contract)
    assert len(calls) == 1, "未填缓存的新 adapter 照旧现算一次"
    assert got == want


# ═══════════════════════════════════════════════════════════════════════════
# R3 / R4 三方提取（替身 resolution / adapter）
# ═══════════════════════════════════════════════════════════════════════════


class _Resolution:
    def __init__(self, base: Any, current: Any) -> None:
        self.base, self.current = base, current

    async def resolve(self, *, representation_id: Any = None, **_kw: Any) -> Any:
        return self.base if representation_id is not None else self.current


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def extract(self, *, artifact: Path, contract: Any) -> Projection:
        self.calls.append((Path(artifact).name, threading.get_ident()))
        return Projection(contract_id="c", semantic_version="1", document_type="xlsx", values={})


def _resolved(name: str, artifact_id: uuid.UUID, bundle_id: uuid.UUID) -> Any:
    return SimpleNamespace(
        artifact_path=Path(name), artifact_id=artifact_id, representation_id=uuid.uuid4(),
        bundle=SimpleNamespace(bundle_id=bundle_id),
    )


async def _three_way(same_artifact: bool) -> tuple[Any, _Adapter, int, list[Any]]:
    bundle_id, artifact = uuid.uuid4(), uuid.uuid4()
    base = _resolved("base.xlsx", artifact, bundle_id)
    current = _resolved("base.xlsx" if same_artifact else "current.xlsx", artifact if same_artifact else uuid.uuid4(), bundle_id)
    coordinator = object.__new__(OH.OoToHtmlCoordinator)
    coordinator._resolution = _Resolution(base, current)
    journal = OH.ApplyJournal()
    journal.record(OH.ApplyStage.substrate_opened, "s")
    adapter = _Adapter()
    frozen = SimpleNamespace(
        project_id=uuid.uuid4(), wp_id=uuid.uuid4(), entry_id="xlsx/e",
        base_representation_id=base.representation_id, definition_bundle_id=bundle_id,
    )
    substrate = SimpleNamespace(path=Path("incoming.xlsx"), sha256=_d("in"), artifact_id=uuid.uuid4())
    inputs = await coordinator.extract_three_way(
        frozen=frozen, substrate=substrate, adapter=adapter, bundle=object(), contract=object(), journal=journal
    )
    return inputs, adapter, threading.get_ident(), [stage for stage, _ in journal.entries]


@pytest.mark.parametrize("same_artifact", [True, False])
def test_three_way_runs_off_the_event_loop_and_reuses_base_only_for_the_same_artifact(same_artifact: bool) -> None:
    inputs, adapter, loop_thread, stages = asyncio.run(_three_way(same_artifact))
    names = [name for name, _ in adapter.calls]
    assert names == (["base.xlsx", "incoming.xlsx"] if same_artifact else ["base.xlsx", "current.xlsx", "incoming.xlsx"])
    assert (inputs.current is inputs.base) is same_artifact
    assert all(tid != loop_thread for _, tid in adapter.calls), "整簿提取不得在事件循环线程上执行"
    assert stages == [
        OH.ApplyStage.substrate_opened, OH.ApplyStage.base_extracted,
        OH.ApplyStage.current_extracted, OH.ApplyStage.incoming_extracted,
    ]


def test_merge_is_called_through_to_thread() -> None:
    """`apply_durable_incoming` 里的合并只能经 `asyncio.to_thread` 调（直接调用即阻塞事件循环）。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(OH.OoToHtmlCoordinator.apply_durable_incoming)))
    direct = threaded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "merge_projections":
            direct += 1
        if (
            isinstance(node.func, ast.Attribute) and node.func.attr == "to_thread"
            and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "merge_projections"
        ):
            threaded += 1
    assert (direct, threaded) == (0, 1)
