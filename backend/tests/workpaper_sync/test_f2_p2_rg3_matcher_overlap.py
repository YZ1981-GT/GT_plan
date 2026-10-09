# -*- coding: utf-8 -*-
"""F2-P2 红判据：RG-3 冲突先红后绿。

spec: f2-sync-coverage-four-entry-lanes · Task 3 · Requirements 1.1, 1.2
Property 2: ①sheet_keys 为空的两个 F2I matcher 真跑 register() ⇒ MatcherOverlapError；
②互斥 sheet_keys 后三者同时注册成功。变异：给任一 matcher 加入另一 lane 的 sheet_key ⇒ 必红。

═══ 不 mock：真构造 WorkpaperSyncAdapterRegistry 跑 register() ═══
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C
from app.services.workpaper_sync import entry_profile as EP
from app.services.workpaper_sync.adapters import registry as RG
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot
from app.services.workpaper_sync import definitions as D


# ═══════════════════════════════════════════════════════════════════════════
# 工具（复用 test_task13 的模式，不 import 其私有 helpers）
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


TEMPLATE_DEF = _d("template-def")
INSTR_DEF = _d("instrumentation-def")
AUTHORITY_DEF = _d("authority-model-def")

GOOD_DESCRIPTOR = EP.DescriptorFacts(
    mode=EP.DescriptorMode.bidirectional, exposes_mode_switch=True
)
GOOD_ROOM = EP.RoomFacts(
    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
)


class StubAdapter:
    """满足 protocol 形态的最小 adapter。"""

    def __init__(self, adapter_id: str, document_type: str = "xlsx") -> None:
        self.adapter_id = adapter_id
        self.document_type = document_type
        self.contract_version = "1.0.0"

    async def read_current_projection(self, ctx: Any) -> Any:
        raise NotImplementedError

    async def stage_projection_mutation(
        self, ctx: Any, merged: Any, *, expected_revision: int
    ) -> Any:
        raise NotImplementedError

    def materialize(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def extract(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def verify_unmanaged_regions(self, **kwargs: Any) -> Any:
        raise NotImplementedError


def make_bundle(
    *,
    contract_digest: str | None = None,
) -> DefinitionBundleSnapshot:
    slots: dict[BundleSlot, BundleSlotSpec] = {}
    for slot, digest in (
        (BundleSlot.template, TEMPLATE_DEF),
        (BundleSlot.instrumentation, INSTR_DEF),
        (BundleSlot.contract, contract_digest),
    ):
        if digest is not None:
            slots[slot] = D.definition_slot_spec(
                slot, definition_id=uuid.uuid4(), definition_sha256=digest
            )
        else:
            slots[slot] = D.marker_slot_spec(slot, version=1)
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("bundle"),
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
            "relative_path": "F/F2-test.xlsx",
            "template_sha256": _d("template-blob"),
            "normalized_structure_hash": _d("template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "f2-test",
                "excel_name": "测试表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "test_rows",
                        "anchor": "A7",
                        "header_rows": 2,
                        "row_identity": {
                            "kind": "field",
                            "json_pointer": "/rows/*/rowId",
                        },
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
                                "source_ref": "F2-test!B8",
                            },
                        ],
                    },
                ],
            },
        ],
    }


def manifest_entry(entry_id: str) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "host_path": "test.vue",
        "independent_entry": True,
        "parent_entry_id": None,
        "document_type": "xlsx",
        "capability": "bidirectional",
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
    return {
        "schema_version": 1,
        "manifest_digest": _d("manifest"),
        "entries": list(entries),
    }


def registration(
    *,
    contract: C.SyncContract,
    entry_id: str,
    adapter_id: str,
    wp_codes: frozenset[str],
    sheet_keys: frozenset[str] = frozenset(),
) -> RG.AdapterRegistration:
    bundle = make_bundle(contract_digest=contract.canonical_sha256)
    return RG.AdapterRegistration(
        adapter=StubAdapter(adapter_id),
        entry_id=entry_id,
        matcher=RG.EntryMatcher(
            document_type="xlsx", wp_codes=wp_codes, sheet_keys=sheet_keys
        ),
        bundle=bundle,
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


# ═══════════════════════════════════════════════════════════════════════════
# F2 的三条 lane 的 sheet_keys（design F2-H1）
# ═══════════════════════════════════════════════════════════════════════════

# canary 阶段最小集——每 lane 只有 1 个受管 sheet key
MAIN_SHEET_KEYS = frozenset({"f26-managed"})
VALUATION_SHEET_KEYS = frozenset({"f248-managed"})
SPECIAL_SHEET_KEYS = frozenset({"f257-managed"})

# 三 entry 的 entry_id / adapter_id
MAIN_ENTRY = "xlsx/gt-f2-inventory-main"
MAIN_ADAPTER = "f2.inventory_main"
VALUATION_ENTRY = "xlsx/gt-f2-inventory-valuation"
VALUATION_ADAPTER = "f2.inventory_valuation"
SPECIAL_ENTRY = "xlsx/gt-f2-inventory-special"
SPECIAL_ADAPTER = "f2.inventory_special"

F2I = frozenset({"F2I"})


# ═══════════════════════════════════════════════════════════════════════════
# Property 2：RG-3 冲突先红后绿
# ═══════════════════════════════════════════════════════════════════════════


class TestF2P2Rg3MatcherOverlap:
    """三个 F2I entry 共用幻影码，sheet_keys 空→冲突，互斥→通过。"""

    def test_red_phase_sheet_keys_empty_second_register_rejected(
        self, contracts_dir: Path
    ) -> None:
        """sheet_keys 为空的两个 F2I matcher 真跑 register() ⇒ MatcherOverlapError。"""
        manifest = manifest_of(
            manifest_entry(MAIN_ENTRY),
            manifest_entry(VALUATION_ENTRY),
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)

        c1 = install_contract(contracts_dir, xlsx_payload(MAIN_ADAPTER))
        c2 = install_contract(contracts_dir, xlsx_payload(VALUATION_ADAPTER))

        # 第一个注册成功（空 sheet_keys = 覆盖全部 sheet）
        registry.register(
            registration(
                contract=c1,
                entry_id=MAIN_ENTRY,
                adapter_id=MAIN_ADAPTER,
                wp_codes=F2I,
                sheet_keys=frozenset(),  # 空！
            )
        )

        # 第二个同 wp_code 空 sheet_keys → RG-3 冲突
        with pytest.raises(RG.MatcherOverlapError, match="重叠"):
            registry.register(
                registration(
                    contract=c2,
                    entry_id=VALUATION_ENTRY,
                    adapter_id=VALUATION_ADAPTER,
                    wp_codes=F2I,
                    sheet_keys=frozenset(),  # 空！
                )
            )

    def test_green_phase_disjoint_sheet_keys_three_coexist(
        self, contracts_dir: Path
    ) -> None:
        """互斥 sheet_keys 后三个 F2I adapter 同时注册成功。"""
        manifest = manifest_of(
            manifest_entry(MAIN_ENTRY),
            manifest_entry(VALUATION_ENTRY),
            manifest_entry(SPECIAL_ENTRY),
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)

        c1 = install_contract(contracts_dir, xlsx_payload(MAIN_ADAPTER))
        c2 = install_contract(contracts_dir, xlsx_payload(VALUATION_ADAPTER))
        c3 = install_contract(contracts_dir, xlsx_payload(SPECIAL_ADAPTER))

        # 三个 adapter 各自声明互斥 sheet_keys → 全部注册成功
        registry.register(
            registration(
                contract=c1,
                entry_id=MAIN_ENTRY,
                adapter_id=MAIN_ADAPTER,
                wp_codes=F2I,
                sheet_keys=MAIN_SHEET_KEYS,
            )
        )
        registry.register(
            registration(
                contract=c2,
                entry_id=VALUATION_ENTRY,
                adapter_id=VALUATION_ADAPTER,
                wp_codes=F2I,
                sheet_keys=VALUATION_SHEET_KEYS,
            )
        )
        registry.register(
            registration(
                contract=c3,
                entry_id=SPECIAL_ENTRY,
                adapter_id=SPECIAL_ADAPTER,
                wp_codes=F2I,
                sheet_keys=SPECIAL_SHEET_KEYS,
            )
        )

        # 三个都能按 entry_id 解析
        assert registry.resolve_for_entry(MAIN_ENTRY).adapter_id == MAIN_ADAPTER
        assert registry.resolve_for_entry(VALUATION_ENTRY).adapter_id == VALUATION_ADAPTER
        assert registry.resolve_for_entry(SPECIAL_ENTRY).adapter_id == SPECIAL_ADAPTER

    def test_mutation_cross_lane_sheet_key_re_triggers_conflict(
        self, contracts_dir: Path
    ) -> None:
        """变异：给 valuation 加入 main 的 sheet_key ⇒ 必红。"""
        manifest = manifest_of(
            manifest_entry(MAIN_ENTRY),
            manifest_entry(VALUATION_ENTRY),
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)

        c1 = install_contract(contracts_dir, xlsx_payload(MAIN_ADAPTER))
        c2 = install_contract(contracts_dir, xlsx_payload(VALUATION_ADAPTER))

        registry.register(
            registration(
                contract=c1,
                entry_id=MAIN_ENTRY,
                adapter_id=MAIN_ADAPTER,
                wp_codes=F2I,
                sheet_keys=MAIN_SHEET_KEYS,
            )
        )

        # valuation 的 sheet_keys 包含 main 的 key → 重叠
        contaminated = VALUATION_SHEET_KEYS | MAIN_SHEET_KEYS
        with pytest.raises(RG.MatcherOverlapError, match="重叠"):
            registry.register(
                registration(
                    contract=c2,
                    entry_id=VALUATION_ENTRY,
                    adapter_id=VALUATION_ADAPTER,
                    wp_codes=F2I,
                    sheet_keys=contaminated,
                )
            )

    def test_stocktake_f2s_no_conflict_with_f2i(
        self, contracts_dir: Path
    ) -> None:
        """stocktake（F2S）独占幻影码，不与 F2I 冲突。"""
        stocktake_entry = "xlsx/gt-f2-stocktake-bundle"
        stocktake_adapter = "f2.stocktake_bundle"

        manifest = manifest_of(
            manifest_entry(MAIN_ENTRY),
            manifest_entry(stocktake_entry),
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)

        c1 = install_contract(contracts_dir, xlsx_payload(MAIN_ADAPTER))
        c2 = install_contract(contracts_dir, xlsx_payload(stocktake_adapter))

        # main 用 F2I，stocktake 用 F2S → 不同 wp_codes → 不冲突
        registry.register(
            registration(
                contract=c1,
                entry_id=MAIN_ENTRY,
                adapter_id=MAIN_ADAPTER,
                wp_codes=F2I,
                sheet_keys=frozenset(),  # 即使空也不冲突
            )
        )
        registry.register(
            registration(
                contract=c2,
                entry_id=stocktake_entry,
                adapter_id=stocktake_adapter,
                wp_codes=frozenset({"F2S"}),  # 不同幻影码
                sheet_keys=frozenset(),
            )
        )
        assert registry.resolve_for_entry(MAIN_ENTRY).adapter_id == MAIN_ADAPTER
        assert registry.resolve_for_entry(stocktake_entry).adapter_id == stocktake_adapter
