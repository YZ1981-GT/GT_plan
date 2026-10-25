# -*- coding: utf-8 -*-
"""G4-ecl 独立 entry 模块 —— 「债权投资三阶段划分G4-9」转置表。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 10

与 G4-main 共用 `TEMPLATE_SHA256`（同一册 G4 债权投资.xlsx），但有独立的
ENTRY_ID / ADAPTER_ID / build_matcher(sheet_keys={"g409-managed"})。
pointer 靠 `entry_id` 区分（裁决 G46-H2），matcher 靠互斥 sheet_keys 分域（F2-H1）。

只挂一个转置 sheet `g409-managed`，走 `TransposedSheetSpec` / `phase5_transposed_sheet` 引擎。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.models import SyncDomainError

# ── 转置 spec ─────────────────────────────────────────────────────────
from app.services.workpaper_sync.phase5_g4_09_ecl_stage import (
    SPEC_G409,
    MANAGED_SHEET as ECL_MANAGED_SHEET,
    SHEET_KEY as ECL_SHEET_KEY,
    STORE_ITEM_ID as ECL_STORE_ITEM_ID,
    sheet_payload as ecl_sheet_payload,
    compute_mapping_digest as ecl_mapping_digest,
)

# ── 共用常量（同册 G4）──────────────────────────────────────────────────
from app.services.workpaper_sync.phase5_g4_bond_investment import (
    TEMPLATE_SHA256,
    TEMPLATE_RELATIVE_PATH,
    WP_CODES,
    EXPECTED_PROFILE_ID,
    excel_carrier_gate,
    read_authoritative_template,
)


class EntrySelectionError(SyncDomainError):
    error_code = "sync_phase5_g4_ecl_selection_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_bond_investment_ecl"
ENTRY_ID: Final[str] = "xlsx/gt-g4-bond-investment-ecl"
ADAPTER_ID: Final[str] = "g4.ecl_stage"

#: 互斥 sheet_keys（F2-H1 解法）
SHEET_KEYS: Final[frozenset[str]] = frozenset({ECL_SHEET_KEY})

STORE_ITEM_ID: Final[str] = ECL_STORE_ITEM_ID
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write"

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_HTML_STORE_NOTE: Final[str] = (
    "G4-9 ECL 三阶段划分：转置形态（一列=一投资、一行=一评估维度），"
    "payload dual_write；16384 列表 UUID 放第 12 列 L（有效内容列 +1）。"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 spec 与 store
# ═══════════════════════════════════════════════════════════════════════════

def managed_transposed_spec():
    return SPEC_G409


def all_store_item_ids() -> tuple[str, ...]:
    return (ECL_STORE_ITEM_ID,)


def all_managed_sheet_names() -> tuple[str, ...]:
    return (ECL_MANAGED_SHEET,)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约
# ═══════════════════════════════════════════════════════════════════════════

def _transposed_sheet_dict() -> dict[str, Any]:
    """转置 sheet 的 contract sheet 条目。"""
    payload = ecl_sheet_payload()
    return {
        "sheet_key": ECL_SHEET_KEY,
        "excel_name": ECL_MANAGED_SHEET,
        "locator": payload["locator"],
        "tables": payload["tables"],
    }


def build_contract_payload() -> dict[str, Any]:
    # 读模板字节计算 structure hash
    template_data = read_authoritative_template()
    from app.services.workpaper_sync.excel_instrumentation import normalized_structure_hash

    structure_hash = normalized_structure_hash(template_data)

    # 转置 sheet payload
    sheet_dict = _transposed_sheet_dict()

    # instrumentation = 只有转置 sheet
    instr_payload = {"transposed_sheets": [ecl_sheet_payload()]}

    # template definition（与 G4-main 共用同一模板文件，structure_hash 一致）
    template_def = {
        "template_sha256": TEMPLATE_SHA256,
        "relative_path": TEMPLATE_RELATIVE_PATH,
        "normalized_structure_hash": structure_hash,
    }

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_def),
        "instrumentation_definition_sha256": canonical_digest(instr_payload),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": structure_hash,
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "hidden_uuid_column",
        ],
        "sheets": [sheet_dict],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
                "payload_column": PAYLOAD_COLUMN,
                "payload_column_mode": PAYLOAD_COLUMN_MODE,
                "note": _HTML_STORE_NOTE,
            },
        },
    }


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 generate_phase5_g4_ecl_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 4. manifest capability
# ═══════════════════════════════════════════════════════════════════════════

def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    ).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID} 不在 manifest 里")
    cap = capability_of(entry)
    if cap is not Capability.bidirectional:
        raise EntrySelectionError(f"{ENTRY_ID} capability={cap!r}，期望 bidirectional")
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. matcher + registration
# ═══════════════════════════════════════════════════════════════════════════

def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 G4B + sheet_keys={g409-managed}（互斥分域）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES, sheet_keys=SHEET_KEYS)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=ENTRY_ID,
        matcher=build_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=(contract if contract is not None else load_contract_from_disk()),
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    registration = build_registration(
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract,
    )
    registry.register(registration)
    return registration
