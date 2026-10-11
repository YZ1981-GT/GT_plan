"""R14：请求期 adapter 必须绑在**目标底稿自己**的 current representation 上。

spec: d2-online-edit-platform-closure · R14

═══ 根因（2026-10-10 真库实测）═══

registry 按 entry 注册，provider attach 经共享解析器按 ``wp.created_at, wp.id`` 取**第一家**
可见底稿的 representation，冻结身份（行身份清册 / tombstone / 动态列绑定）跟着那一份走。
同一 entry 上第二家企业（重药安徽）的 store-projection 于是拿和平药房的 741 行清册比对自己的
文件 ⇒ 422「OO 往返后丢失 729 个 row identity，首个 'dr-mtl5bqmm-0o950ft'」。

═══ 本文件（零数据库）覆盖 ═══

* 解析器 pin：只返回目标底稿那一行、记下实际返回值、按 task 隔离、退出复原；
* registry 三原语：``fork_unregistered`` / ``entry_provider`` / ``rebind_entry``（判据全跑、失败复原）；
* 绑定入口：两家交替各绑各的、按 representation 缓存、首版前沿用 entry 级、provider 绕过
  解析器 / 并发发布 / 目标不可见三种绑不上都 fail closed、并发首请求只建一次、失败不缓存；
* 生产接线（AST）、全部 provider 经共享解析器、R15 指纹、R16 callback 缓存 ⇒
  ``test_target_bound_registration_wiring.py``（原样迁出，行数门）。

真库两家企业交替（真 D2 provider + 真首版发布）见 ``test_target_bound_registration_pg.py``。
"""
from __future__ import annotations

import asyncio
import collections
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync import entry_profile as EP  # noqa: E402
from app.services.workpaper_sync import projection_target_resolution as PTR  # noqa: E402
from app.services.workpaper_sync import target_bound_registration as TB  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
    SyncDomainError,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 脚手架（与 test_f2_p2_rg3_matcher_overlap 同一模式：真 registry 真 register()）
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


TEMPLATE_DEF = _d("r14-template-def")
INSTR_DEF = _d("r14-instrumentation-def")
AUTHORITY_DEF = _d("r14-authority-model-def")

ENTRY = "xlsx/r14-target-entry"
ADAPTER = "r14.target_entry"
OTHER_ENTRY = "xlsx/r14-other-entry"
OTHER_ADAPTER = "r14.other_entry"

GOOD_DESCRIPTOR = EP.DescriptorFacts(
    mode=EP.DescriptorMode.bidirectional, exposes_mode_switch=True
)
GOOD_ROOM = EP.RoomFacts(
    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
)


class StubAdapter:
    """满足 protocol 形态的最小 adapter；`bound_representation` 记它由哪份 representation 造出。"""

    def __init__(self, adapter_id: str, *, bound: Any, document_type: str = "xlsx") -> None:
        self.adapter_id = adapter_id
        self.document_type = document_type
        self.contract_version = "1.0.0"
        self.bound_representation = bound

    async def read_current_projection(self, ctx: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    async def stage_projection_mutation(
        self, ctx: Any, merged: Any, *, expected_revision: int
    ) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def materialize(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def extract(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def verify_unmanaged_regions(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError


def make_bundle(*, contract_digest: str) -> DefinitionBundleSnapshot:
    slots: dict[BundleSlot, BundleSlotSpec] = {}
    for slot, digest in (
        (BundleSlot.template, TEMPLATE_DEF),
        (BundleSlot.instrumentation, INSTR_DEF),
        (BundleSlot.contract, contract_digest),
    ):
        slots[slot] = D.definition_slot_spec(
            slot, definition_id=uuid.uuid4(), definition_sha256=digest
        )
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("r14-bundle"),
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=AUTHORITY_DEF,
        slots=slots,
    )


def xlsx_payload(contract_id: str) -> dict[str, Any]:
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "R/R14-test.xlsx",
            "template_sha256": _d("r14-template-blob"),
            "normalized_structure_hash": _d("r14-template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "r14-test",
                "excel_name": "测试表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "test_rows",
                        "anchor": "A7",
                        "header_rows": 2,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowId"},
                        "delete_policy": "tombstone",
                        "footer_anchor": {"marker": "合计", "search_column": "A"},
                        "formula_mask": [],
                        "fields": [
                            {
                                "stable_field_key": "test_rows/{row_uuid}/amount",
                                "json_pointer": "/rows/{row_uuid}/amount",
                                "column_key": "amount",
                                "cell": {"column": "B", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "R14-test!B8",
                            },
                        ],
                    },
                ],
            },
        ],
    }


def manifest_entry(entry_id: str, *, capability: str = "bidirectional") -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "host_path": "test.vue",
        "independent_entry": True,
        "parent_entry_id": None,
        "document_type": "xlsx",
        "capability": capability,
        "html_store": "parsed_data",
        "canonical_resolver": "workpaper_sync",
        "adapter_id": None,
        "migration_state": "adapter_candidate",
        "evidence": {},
        "editability": "editable",
        "room_model": "shared",
        "scenario_profile": "xlsx.editable.shared.single.room_service_wired.v1",
    }


def manifest_of(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "manifest_digest": _d("r14-manifest"), "entries": list(entries)}


def registration(
    *,
    contract: C.SyncContract,
    entry_id: str = ENTRY,
    adapter_id: str = ADAPTER,
    wp_codes: frozenset[str] = frozenset({"R14"}),
    bound: Any = None,
    document_type: str = "xlsx",
) -> RG.AdapterRegistration:
    return RG.AdapterRegistration(
        adapter=StubAdapter(adapter_id, bound=bound, document_type=document_type),
        entry_id=entry_id,
        matcher=RG.EntryMatcher(document_type="xlsx", wp_codes=wp_codes),
        bundle=make_bundle(contract_digest=contract.canonical_sha256),
        descriptor=GOOD_DESCRIPTOR,
        room=GOOD_ROOM,
        declared_capability=EP.Capability.bidirectional,
        contract=contract,
    )


@pytest.fixture()
def contracts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "workpaper_sync_contracts"
    target.mkdir()
    monkeypatch.setattr(C, "CONTRACTS_DIR", target)
    return target


def install_contract(directory: Path, payload: Mapping[str, Any]) -> C.SyncContract:
    path = directory / f"{payload['contract_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return C.load_contract(str(payload["contract_id"]))


@pytest.fixture(autouse=True)
def _clean_target_cache():
    TB.clear_target_registration_cache()
    yield
    TB.clear_target_registration_cache()


# ═══════════════════════════════════════════════════════════════════════════
# 零库替身：`working_paper_sync_entry_state` + 可见性
# ═══════════════════════════════════════════════════════════════════════════

_Row = collections.namedtuple("_Row", "rid wid")


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self) -> Any:
        rows = self._rows

        class _Scalars:
            def first(self) -> Any:
                return rows[0][0] if rows else None

        return _Scalars()


class FakeDb:
    """`(wp_id, entry_id) → current representation`，按建档顺序；`visible` 模拟三层软删过滤。"""

    def __init__(self) -> None:
        self.order: list[uuid.UUID] = []
        self.pointer: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self.visible: set[uuid.UUID] = set()

    def add_wp(self, *, visible: bool = True) -> uuid.UUID:
        wp = uuid.uuid4()
        self.order.append(wp)
        if visible:
            self.visible.add(wp)
        return wp

    def publish(self, wp: uuid.UUID, entry_id: str = ENTRY) -> uuid.UUID:
        rid = uuid.uuid4()
        self.pointer[(wp, entry_id)] = rid
        return rid


class FakeSession:
    """只认两种语句：共享解析器的 text SQL、`target_representation_id` 的 ORM select。"""

    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.text_calls = 0

    async def execute(self, statement: Any) -> _Result:
        await asyncio.sleep(0)  # 让并发 task 真的交错
        params = dict(statement.compile().params)
        if isinstance(statement, sa.sql.elements.TextClause):
            self.text_calls += 1
            entry_id = params["entry_id"]
            rows = [
                # 存成 hex 串：解析器必须在 Python 侧规范化后再比（PG/SQLite 形态不同）
                _Row(rid=self.db.pointer[(wp, entry_id)], wid=wp.hex)
                for wp in self.db.order
                if (wp, entry_id) in self.db.pointer and wp in self.db.visible
            ]
            if "LIMIT 1" in statement.text:
                rows = rows[:1]
            return _Result(rows)
        wp = next(v for k, v in params.items() if k.startswith("wp_id"))
        entry_id = next(v for k, v in params.items() if k.startswith("entry_id"))
        rid = self.db.pointer.get((PTR.as_uuid(wp), entry_id))
        return _Result([] if rid is None else [(rid,)])


def make_provider(
    contract: C.SyncContract,
    *,
    calls: list[Any],
    entry_id: str = ENTRY,
    adapter_id: str = ADAPTER,
    consult_resolver: bool = True,
    fail_once: list[BaseException] | None = None,
):
    """与生产 provider 同形：已注册即早退 → 经共享解析器取 representation → register()。"""

    async def provider(registry: Any, *, session: Any) -> tuple[str, ...]:
        calls.append(PTR.current_representation_target())
        if adapter_id in {reg.adapter_id for reg in registry.registrations()}:
            return ()
        if fail_once:
            raise fail_once.pop()
        if consult_resolver:
            rid = await PTR.resolve_visible_current_representation_id(
                session, entry_id=entry_id
            )
        else:
            rid = "self-chosen"
        if rid is None:
            return ()
        registry.register(
            registration(contract=contract, entry_id=entry_id, adapter_id=adapter_id, bound=rid)
        )
        return (adapter_id,)

    return provider


def build_world(contracts_dir: Path, *, capability: str = "bidirectional"):
    """一个 entry 两家企业 + 一个无关 entry（证 rebind 不碰别人、RG-3 照跑）。"""
    contract = install_contract(contracts_dir, xlsx_payload(ADAPTER))
    other_contract = install_contract(contracts_dir, xlsx_payload(OTHER_ADAPTER))
    registry = RG.WorkpaperSyncAdapterRegistry(
        manifest=manifest_of(
            manifest_entry(ENTRY, capability=capability), manifest_entry(OTHER_ENTRY)
        )
    )
    other = registration(
        contract=other_contract,
        entry_id=OTHER_ENTRY,
        adapter_id=OTHER_ADAPTER,
        wp_codes=frozenset({"R14-OTHER"}),
        bound="other",
    )
    registry.register(other)
    db = FakeDb()
    return contract, registry, other, db


def install_provider(registry: Any, provider: Any) -> None:
    """测试 registry 没绑注册计划：只把「取本 entry 的 provider」这一步换成替身。"""
    registry.entry_provider = lambda entry_id: provider  # type: ignore[method-assign]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 共享解析器的 pin
# ═══════════════════════════════════════════════════════════════════════════


class TestResolverPin:
    @pytest.mark.asyncio
    async def test_without_pin_the_resolver_still_picks_the_first_visible_workpaper(self) -> None:
        """不加 pin 时行为逐字不变（发布期宿主 / entry 级注册仍按全序取第一家）。"""
        db = FakeDb()
        wp_a, wp_b = db.add_wp(), db.add_wp()
        rep_a, _ = db.publish(wp_a), db.publish(wp_b)
        got = await PTR.resolve_visible_current_representation_id(
            FakeSession(db), entry_id=ENTRY
        )
        assert got == rep_a

    @pytest.mark.asyncio
    async def test_pin_returns_only_the_target_workpaper_and_records_it(self) -> None:
        db = FakeDb()
        wp_a, wp_b = db.add_wp(), db.add_wp()
        db.publish(wp_a)
        rep_b = db.publish(wp_b)
        with PTR.pin_representation_target(wp_b) as pin:
            got = await PTR.resolve_visible_current_representation_id(
                FakeSession(db), entry_id=ENTRY
            )
        assert got == rep_b, "pin 生效时取到的不是目标底稿的 representation"
        assert pin.resolved == {ENTRY: rep_b}, "pin 没有记下解析器实际返回的值"

    @pytest.mark.asyncio
    async def test_pin_to_an_invisible_workpaper_resolves_none(self) -> None:
        """目标底稿被软删（自身 / 项目 / 索引）⇒ 返回 None，**不**退回第一家。"""
        db = FakeDb()
        wp_a = db.add_wp()
        wp_hidden = db.add_wp(visible=False)
        db.publish(wp_a)
        db.publish(wp_hidden)
        with PTR.pin_representation_target(wp_hidden) as pin:
            got = await PTR.resolve_visible_current_representation_id(
                FakeSession(db), entry_id=ENTRY
            )
        assert got is None
        assert pin.resolved == {ENTRY: None}

    def test_pin_is_restored_on_exit_and_nests(self) -> None:
        outer_wp, inner_wp = uuid.uuid4(), uuid.uuid4()
        assert PTR.current_representation_target() is None
        with PTR.pin_representation_target(outer_wp):
            with PTR.pin_representation_target(str(inner_wp)):
                assert PTR.current_representation_target().wp_id == inner_wp
            assert PTR.current_representation_target().wp_id == outer_wp
        assert PTR.current_representation_target() is None

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_see_each_others_pin(self) -> None:
        """ContextVar 按 task 隔离：两家企业的请求并发时各绑各的。"""
        db = FakeDb()
        wps = [db.add_wp() for _ in range(4)]
        reps = {wp: db.publish(wp) for wp in wps}

        async def resolve_for(wp: uuid.UUID) -> Any:
            with PTR.pin_representation_target(wp):
                return await PTR.resolve_visible_current_representation_id(
                    FakeSession(db), entry_id=ENTRY
                )

        got = await asyncio.gather(*(resolve_for(wp) for wp in wps * 3))
        assert got == [reps[wp] for wp in wps * 3]

    @pytest.mark.parametrize(
        "left, right, equal",
        [
            (uuid.UUID(int=7), str(uuid.UUID(int=7)), True),
            (uuid.UUID(int=7), uuid.UUID(int=7).hex, True),
            (uuid.UUID(int=7).bytes, uuid.UUID(int=7), True),
            (uuid.UUID(int=7), uuid.UUID(int=8), False),
            (None, uuid.UUID(int=7), False),
            ("not-a-uuid", uuid.UUID(int=7), False),
        ],
    )
    def test_uuid_forms_compare_by_value(self, left: Any, right: Any, equal: bool) -> None:
        assert PTR.same_uuid(left, right) is equal


# ═══════════════════════════════════════════════════════════════════════════
# 2. registry 三原语
# ═══════════════════════════════════════════════════════════════════════════

D2_ENTRY = "xlsx/gt-d2-accounts-receivable"


class TestRegistryPrimitives:
    def test_fork_has_the_same_manifest_and_plan_but_no_registration(self) -> None:
        registry = RG.build_production_registry()
        fork = registry.fork_unregistered()
        assert fork.registrations() == ()
        assert set(fork.manifest_entries) == set(registry.manifest_entries)
        assert fork.registration_plan == registry.registration_plan

    def test_entry_provider_is_the_entry_own_attach(self) -> None:
        from app.services.workpaper_sync import pilot_d2_large_json as D2

        registry = RG.build_production_registry()
        assert registry.entry_provider(D2_ENTRY) is D2.attach_pilot_adapters

    def test_entry_provider_refuses_unknown_and_statically_blocked_entries(self) -> None:
        registry = RG.build_production_registry()
        with pytest.raises(RG.StaleAdapterError, match="不在注册计划中"):
            registry.entry_provider("xlsx/never-existed")
        blocked = next(
            item for item in registry.registration_plan if item.blocked_reason is not None
        )
        with pytest.raises(RG.RegistrationError) as excinfo:
            registry.entry_provider(blocked.entry_id)
        assert blocked.blocked_reason in str(excinfo.value), "静态不可注册原因没有原样透出"

    def test_rebind_replaces_the_entry_registration_in_place(self, contracts_dir: Path) -> None:
        contract, registry, other, _ = build_world(contracts_dir)
        first = registration(contract=contract, bound="rep-a")
        registry.register(first)
        second = registration(contract=contract, bound="rep-b")
        registry.rebind_entry(second)
        assert registry.resolve_for_entry(ENTRY) is second
        assert [r.entry_id for r in registry.registrations()].count(ENTRY) == 1
        assert registry.resolve_for_entry(OTHER_ENTRY) is other, "rebind 碰了别的 entry"

    def test_rebind_of_the_same_object_is_a_no_op(self, contracts_dir: Path) -> None:
        contract, registry, _, _ = build_world(contracts_dir)
        first = registration(contract=contract, bound="rep-a")
        registry.register(first)
        registry.rebind_entry(first)
        assert registry.resolve_for_entry(ENTRY) is first

    def test_rebind_without_existing_registration_registers(self, contracts_dir: Path) -> None:
        contract, registry, _, _ = build_world(contracts_dir)
        reg = registration(contract=contract, bound="rep-a")
        registry.rebind_entry(reg)
        assert registry.resolve_for_entry(ENTRY) is reg

    def test_rebind_refuses_another_adapter_and_keeps_the_old_one(
        self, contracts_dir: Path
    ) -> None:
        contract, registry, _, _ = build_world(contracts_dir)
        first = registration(contract=contract, bound="rep-a")
        registry.register(first)
        alien_contract = install_contract(contracts_dir, xlsx_payload("r14.alien"))
        alien = registration(contract=alien_contract, adapter_id="r14.alien", bound="x")
        with pytest.raises(RG.RegistrationError, match="同一 adapter"):
            registry.rebind_entry(alien)
        assert registry.resolve_for_entry(ENTRY) is first

    def test_a_failing_rebind_restores_the_old_registration(self, contracts_dir: Path) -> None:
        """判据经 register() 全跑：document_type 不符 ⇒ 抛，且旧注册原样复原（无半态）。"""
        contract, registry, _, _ = build_world(contracts_dir)
        first = registration(contract=contract, bound="rep-a")
        registry.register(first)
        broken = registration(contract=contract, bound="rep-b", document_type="docx")
        with pytest.raises(RG.DocumentTypeMismatchError):
            registry.rebind_entry(broken)
        assert registry.resolve_for_entry(ENTRY) is first
        assert registry.assert_bidirectional_ready(ENTRY) is first

    def test_rebind_still_runs_the_matcher_overlap_check(self, contracts_dir: Path) -> None:
        """RG-3 与其它 entry 照比：换绑不得成为绕过 matcher 唯一性的后门。"""
        contract, registry, _, _ = build_world(contracts_dir)
        first = registration(contract=contract, bound="rep-a")
        registry.register(first)
        overlapping = registration(
            contract=contract, bound="rep-b", wp_codes=frozenset({"R14-OTHER"})
        )
        with pytest.raises(RG.MatcherOverlapError):
            registry.rebind_entry(overlapping)
        assert registry.resolve_for_entry(ENTRY) is first


# ═══════════════════════════════════════════════════════════════════════════
# 3. 绑定入口
# ═══════════════════════════════════════════════════════════════════════════


async def _entry_level(registry: Any, provider: Any, session: Any) -> Any:
    """生产里 entry 级注册的来源：同一个 provider、**不加 pin** ⇒ 全序第一家。"""
    await provider(registry, session=session)
    return registry.resolve_for_entry(ENTRY)


class TestBindRegistrationToTarget:
    @pytest.mark.asyncio
    async def test_two_companies_alternate_and_each_gets_its_own_representation(
        self, contracts_dir: Path
    ) -> None:
        """R14 的直接判据：同一 entry 两家企业交替，各自绑自己的 representation。"""
        contract, registry, other, db = build_world(contracts_dir)
        wp_a, wp_b = db.add_wp(), db.add_wp()
        rep_a, rep_b = db.publish(wp_a), db.publish(wp_b)
        session = FakeSession(db)
        calls: list[Any] = []
        provider = make_provider(contract, calls=calls)
        install_provider(registry, provider)
        entry_level = await _entry_level(registry, provider, session)
        assert entry_level.adapter.bound_representation == rep_a, "前提：entry 级绑第一家"

        for wp, rep in ((wp_b, rep_b), (wp_a, rep_a), (wp_b, rep_b), (wp_a, rep_a)):
            got = await TB.bind_registration_to_target(
                session=session, registry=registry, entry_id=ENTRY, wp_id=wp
            )
            assert got.adapter.bound_representation == rep, (
                f"底稿 {wp} 拿到的 adapter 绑在 {got.adapter.bound_representation} 上，"
                f"应为它自己的 {rep} —— 又在用别家企业的冻结身份"
            )
            assert registry.resolve_for_entry(ENTRY) is got, "请求 registry 里没换成绑定注册"
            assert [r.entry_id for r in registry.registrations()].count(ENTRY) == 1
            assert registry.resolve_for_entry(OTHER_ENTRY) is other
        pinned = [pin.wp_id for pin in calls if pin is not None]
        assert pinned == [wp_b, wp_a], (
            f"每个 (entry, representation) 只应冷建一次（命中缓存不再跑 provider），实际 pin={pinned}"
        )

    @pytest.mark.asyncio
    async def test_a_new_generation_is_a_new_cache_key(self, contracts_dir: Path) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        db.publish(wp_a)
        session = FakeSession(db)
        provider = make_provider(contract, calls=[])
        install_provider(registry, provider)
        first = await TB.bind_registration_to_target(
            session=session, registry=registry, entry_id=ENTRY, wp_id=wp_a
        )
        rep_next = db.publish(wp_a)  # 再发一代：current pointer 换了
        second = await TB.bind_registration_to_target(
            session=session, registry=registry, entry_id=ENTRY, wp_id=wp_a
        )
        assert second is not first
        assert second.adapter.bound_representation == rep_next

    @pytest.mark.asyncio
    async def test_before_first_publication_the_entry_level_registration_is_used(
        self, contracts_dir: Path
    ) -> None:
        """首版前没有冻结清册可比；首版发布本身不经 registry ⇒ 沿用 entry 级，不跑 provider。"""
        contract, registry, _, db = build_world(contracts_dir)
        wp_a, wp_new = db.add_wp(), db.add_wp()
        db.publish(wp_a)
        session = FakeSession(db)
        calls: list[Any] = []
        provider = make_provider(contract, calls=calls)
        install_provider(registry, provider)
        entry_level = await _entry_level(registry, provider, session)
        calls.clear()
        got = await TB.bind_registration_to_target(
            session=session, registry=registry, entry_id=ENTRY, wp_id=wp_new
        )
        assert got is entry_level
        assert calls == [], "没有 representation 时不该去建绑定注册"

    @pytest.mark.asyncio
    async def test_a_provider_that_bypasses_the_shared_resolver_is_refused(
        self, contracts_dir: Path
    ) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        db.publish(wp_a)
        install_provider(registry, make_provider(contract, calls=[], consult_resolver=False))
        # 🔴 匹配「没有经共享解析器」而不是「共享解析器」：后者也出现在「并发发布」那条文案里，
        #    删掉本判据分支时会被下一条判据以错误的原因接住而照样绿（变异 T3 实测）。
        with pytest.raises(TB.TargetRepresentationBindingError, match="没有经共享解析器") as excinfo:
            await TB.bind_registration_to_target(
                session=FakeSession(db), registry=registry, entry_id=ENTRY, wp_id=wp_a
            )
        assert "并发发布" not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_a_concurrent_publication_between_the_two_reads_is_refused(
        self, contracts_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        db.publish(wp_a)
        stale = uuid.uuid4()

        async def stale_pointer(session: Any, *, wp_id: Any, entry_id: str) -> Any:
            return stale

        monkeypatch.setattr(TB, "target_representation_id", stale_pointer)
        install_provider(registry, make_provider(contract, calls=[]))
        with pytest.raises(TB.TargetRepresentationBindingError, match="并发发布"):
            await TB.bind_registration_to_target(
                session=FakeSession(db), registry=registry, entry_id=ENTRY, wp_id=wp_a
            )
        assert TB.TARGET_REGISTRATION_CACHE.get((ENTRY, str(stale))) is None

    @pytest.mark.asyncio
    async def test_an_invisible_target_does_not_fall_back_to_another_company(
        self, contracts_dir: Path
    ) -> None:
        """目标底稿不可见 ⇒ fail closed；**不**退回 entry 级（那份绑的是别家企业）。"""
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        wp_hidden = db.add_wp(visible=False)
        db.publish(wp_a)
        db.publish(wp_hidden)
        session = FakeSession(db)
        provider = make_provider(contract, calls=[])
        install_provider(registry, provider)
        await _entry_level(registry, provider, session)
        with pytest.raises(TB.TargetRepresentationBindingError, match="可见性"):
            await TB.bind_registration_to_target(
                session=session, registry=registry, entry_id=ENTRY, wp_id=wp_hidden
            )

    @pytest.mark.asyncio
    async def test_unbound_target_without_any_entry_level_registration_names_the_cause(
        self, contracts_dir: Path
    ) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_hidden = db.add_wp(visible=False)
        db.publish(wp_hidden)
        install_provider(registry, make_provider(contract, calls=[]))
        with pytest.raises(TB.TargetRepresentationBindingError, match="可见性"):
            await TB.bind_registration_to_target(
                session=FakeSession(db), registry=registry, entry_id=ENTRY, wp_id=wp_hidden
            )

    @pytest.mark.asyncio
    async def test_entry_level_gate_speaks_before_the_binding(self, contracts_dir: Path) -> None:
        """capability 未裁决双向是 entry 级事实，比「绑不上」更根本 ⇒ 原错误类型照抛。"""
        contract, registry, _, db = build_world(contracts_dir, capability="single_onlyoffice")
        wp_a = db.add_wp()
        db.publish(wp_a)

        async def gated(registry: Any, *, session: Any) -> tuple[str, ...]:
            return ()  # 生产 provider 的 capability 门：未放行即返回空

        install_provider(registry, gated)
        with pytest.raises(RG.FakeBidirectionalError):
            await TB.bind_registration_to_target(
                session=FakeSession(db), registry=registry, entry_id=ENTRY, wp_id=wp_a
            )

    @pytest.mark.asyncio
    async def test_concurrent_first_requests_build_the_binding_once(
        self, contracts_dir: Path
    ) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        db.publish(wp_a)
        calls: list[Any] = []
        install_provider(registry, make_provider(contract, calls=calls))
        session = FakeSession(db)
        got = await asyncio.gather(
            *(
                TB.bind_registration_to_target(
                    session=session, registry=registry, entry_id=ENTRY, wp_id=wp_a
                )
                for _ in range(5)
            )
        )
        assert len(calls) == 1, f"5 个并发首请求跑了 {len(calls)} 次 provider（应 1 次）"
        assert len({id(reg) for reg in got}) == 1
        assert TB._BUILD_LOCKS == {}, "建完后按键的锁没有回收（长跑进程会无界增长）"

    @pytest.mark.asyncio
    async def test_a_failed_build_is_not_cached(self, contracts_dir: Path) -> None:
        contract, registry, _, db = build_world(contracts_dir)
        wp_a = db.add_wp()
        rep_a = db.publish(wp_a)
        calls: list[Any] = []

        class _Transient(SyncDomainError):
            error_code = "r14_probe_transient"

        install_provider(
            registry, make_provider(contract, calls=calls, fail_once=[_Transient("once")])
        )
        session = FakeSession(db)
        with pytest.raises(_Transient):
            await TB.bind_registration_to_target(
                session=session, registry=registry, entry_id=ENTRY, wp_id=wp_a
            )
        got = await TB.bind_registration_to_target(
            session=session, registry=registry, entry_id=ENTRY, wp_id=wp_a
        )
        assert got.adapter.bound_representation == rep_a
        assert len(calls) == 2


# ═══════════════════════════════════════════════════════════════════════════
# §4~§7（生产接线 AST / 全 provider 经共享解析器 / R15 指纹 / R16 callback 缓存）
# 已原样迁到 ``test_target_bound_registration_wiring.py``（行数门：单文件 ≤ 800）。
# ═══════════════════════════════════════════════════════════════════════════
