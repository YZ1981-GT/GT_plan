# -*- coding: utf-8 -*-
"""K2 其他流动资产「调整分录汇总K2-3」—— K 循环真双向 entry。

与 K8~K13 同构，共享内核 `phase5_k_adjustment_summary.py`。
本模块只持有 K2 专属身份与逐册差异（行号 / store item / 前端字段名）。

HTML store：前端 `K2TabAdjustment.vue` 以 `{ remark: JSON.stringify(entries) }` 写 `K2-3-adj-entries`。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.models import DefinitionKind
from app.services.workpaper_sync.phase5_k_adjustment_summary import (
    EXPECTED_PROFILE_ID,
    FIRST_DATA_ROW,
    FOOTER_MARKER,
    MANAGED_LAST_COL,
    PHASE5_WAVE,
    ROW_IDENTITY_STORE_KEY,
    ROWS_TABLE_KEY,
    UUID_COL,
    KAdjustmentEntryConfig,
    build_k_adjustment_provider,
    publish_with_authority,
)

ENTRY_ID: Final[str] = "xlsx/gt-k2-other-current-assets"
ADAPTER_ID: Final[str] = "k2.other_current_assets_adjustment"
WP_CODES: Final[frozenset[str]] = frozenset({"K2O"})
TEMPLATE_RELATIVE_PATH: Final[str] = "K/K2 其他流动资产.xlsx"
TEMPLATE_SHA256: Final[str] = "5ae401411039385e70766635dc9eeb9c0a79c6da4f8c1af316b2ad1430589162"
MANAGED_SHEET: Final[str] = "调整分录汇总K2-3"
STORE_ITEM_ID: Final[str] = "K2-3-adj-entries"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
LAST_DATA_ROW: Final[int] = 21
FOOTER_ROW: Final[int] = 22

CONFIG: Final[KAdjustmentEntryConfig] = KAdjustmentEntryConfig(
    n=2,
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    managed_sheet=MANAGED_SHEET,
    store_item_id=STORE_ITEM_ID,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    json_keys={
        "A": "summary", "B": "category", "C": "reportItem", "D": "accountName",
        "E": "noteItem", "F": "placeholder", "G": "debitAmount", "H": "creditAmount",
        "I": "indexRef", "J": "remark",
    },
    store_only_keys=("seq",),
    html_store_note=(
        "前端 `K2TabAdjustment.vue` 以 `{ remark: JSON.stringify(entries) }` "
        "写 `K2-3-adj-entries`。ITEM_PREFIX='K2-3-adj'。"
    ),
    reviewed_basis=(
        "openpyxl 逐格实测 `K/K2 其他流动资产.xlsx` 的 `调整分录汇总K2-3`：单级表头 R5 十列 A..J、"
        "数据区 R6:R21 纯空白待填（公式格 0 / 裸 IF 0）、R22 是「提示：」文字、"
        "整册裸 IF 0 格。"
    ),
)

_P = build_k_adjustment_provider(CONFIG)
_O = _P.orch

SPEC_K203 = _P.SPEC
SHEET_KEY: Final[str] = CONFIG.sheet_key
TEMPLATE_ID: Final[str] = CONFIG.template_id
TABLE_NAME: Final[str] = CONFIG.table_name

instrumentation_spec = _P.instrumentation_spec
instrumentation_specs = _P.instrumentation_specs
managed_row_table_specs = _P.managed_row_table_specs
build_contract_payload = _P.build_contract_payload
assert_contract_file_matches_source = _P.assert_contract_file_matches_source
build_store_projection = _P.build_store_projection
merge_projection_into_store_rows = _P.merge_projection_into_store_rows
iter_store_rows = _P.iter_store_rows
all_store_item_ids = _P.all_store_item_ids

EntrySelectionError = _O.EntrySelectionError
StorePayloadError = _O.StorePayloadError
Phase5Definitions = _O.Phase5Definitions
TemplateResolutionFacts = _O.TemplateResolutionFacts
excel_carrier_gate = _O.excel_carrier_gate
authoritative_template_path = _O.authoritative_template_path
read_authoritative_template = _O.read_authoritative_template
assert_no_implicit_template_fallback = _O.assert_no_implicit_template_fallback
assert_entry_selectable = _O.assert_entry_selectable
template_definition_payload = _O.template_definition_payload
instrumentation_definition_payload = _O.instrumentation_definition_payload
authority_model_payload = _O.authority_model_payload
contract_file_path = _O.contract_file_path
load_contract_from_disk = _O.load_contract_from_disk
build_matcher = _O.build_matcher
build_registration = _O.build_registration
register_adapter = _O.register_adapter
attach_adapters = _O.attach_adapters
manifest_capability_enabled = _O.manifest_capability_enabled
assert_manifest_capability_enabled = _O.assert_manifest_capability_enabled


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: Any
) -> Any:
    from pathlib import Path
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    backend_root = Path(__file__).resolve().parents[3]
    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(backend_root)),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器 digest {observation.definitions.contract.canonical_sha256} "
            f"与 source-locked {contract.canonical_sha256} 不一致"
        )
    return observation


async def publish_definitions(publisher: Any) -> Any:
    assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    return await publish_with_authority(_O, publisher, authority)


publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
