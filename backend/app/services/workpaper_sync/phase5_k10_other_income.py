# -*- coding: utf-8 -*-
"""K10 其他收益「调整分录汇总K10-3」—— K 循环真双向 entry。

spec: k-cycle-sync-foundation-and-first-canary · Task 22/23（canary）

共享内核见 `phase5_k_adjustment_summary.py`（六册模板层同构，逐册差异只有行号 / store
item / 前端字段名三处，收进 `KAdjustmentEntryConfig`）。本模块只持有**本 entry 的身份**，
并保留 authority model 这一环的发布调用（`projection_lane_registry` 的 AST 判据要在
本模块源码里找到它，见内核 `publish_with_authority` docstring）。

HTML store：前端 `K10TabAdjustment.vue` 以裸数组 emit `K10-3-entries`（宿主 `toChecklistPatch` 归一成 remark JSON）。🔴 `type`(AJE/RJE) 是 store-only 分组维度（模板无列），OO 侧新增行回 HTML 后默认 AJE。F 列「……」HTML 无字段 ⇒ `placeholder`。
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

ENTRY_ID: Final[str] = "xlsx/gt-k10-other-income"
ADAPTER_ID: Final[str] = "k10.other_income_adjustment"
#: manifest 冻结的 wp_code_pattern（宿主 CamelCase 幻影码，finder 零命中；真实码由
#: `workpaper_sync_entry_wp_code_adjudication.json` 裁决为 `K10`）。
WP_CODES: Final[frozenset[str]] = frozenset({"K10O"})
TEMPLATE_RELATIVE_PATH: Final[str] = "K/K10 其他收益.xlsx"
TEMPLATE_SHA256: Final[str] = "04996321e9ff9525b293ef3fd2bd0fffbc1249aae2e760ddd7c90aa836afbc0d"
MANAGED_SHEET: Final[str] = "调整分录汇总K10-3"
STORE_ITEM_ID: Final[str] = "K10-3-entries"
#: 空 store 载荷形态（行数组）—— 首版发布宿主按它判「空表单」，不替 provider 猜。
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
LAST_DATA_ROW: Final[int] = 22
FOOTER_ROW: Final[int] = 23

CONFIG: Final[KAdjustmentEntryConfig] = KAdjustmentEntryConfig(
    n=10,
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    managed_sheet=MANAGED_SHEET,
    store_item_id=STORE_ITEM_ID,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    json_keys={'A': 'description', 'B': 'category', 'C': 'reportItem', 'D': 'accountName', 'E': 'noteItem', 'F': 'placeholder', 'G': 'debitAmount', 'H': 'creditAmount', 'I': 'refIndex', 'J': 'remark'},
    store_only_keys=('type',),
    html_store_note=(
        '前端 `K10TabAdjustment.vue` 以裸数组 emit `K10-3-entries`（宿主 `toChecklistPatch` 归一成 remark JSON）。🔴 `type`(AJE/RJE) 是 store-only 分组维度（模板无列），OO 侧新增行回 HTML 后默认 AJE。F 列「……」HTML 无字段 ⇒ `placeholder`。'
    ),
    reviewed_basis=(
        "openpyxl 逐格实测 `K/K10 其他收益.xlsx` 的 `调整分录汇总K10-3`：单级表头 R5 十列 A..J、"
        "数据区 R6:R22 纯空白待填（公式格 0 / 裸 IF 0）、R23 是 A:J 合并的「提示：」"
        "文字（不承载 SUM）、K~O 列全空 ⇒ UUID 载体取 K 列无需注入、册内零 Excel Table、"
        "sheet 级保护未启用；前端 `K10TabAdjustment.vue` 按值 grep 字段面与 store 键。"
    ),
)

_P = build_k_adjustment_provider(CONFIG)
_O = _P.orch

SPEC_K1003 = _P.SPEC
SHEET_KEY: Final[str] = CONFIG.sheet_key
TEMPLATE_ID: Final[str] = CONFIG.template_id
TABLE_NAME: Final[str] = CONFIG.table_name

# ── provider 面（store 投影 / 合并 / 契约）──
instrumentation_spec = _P.instrumentation_spec
instrumentation_specs = _P.instrumentation_specs
managed_row_table_specs = _P.managed_row_table_specs
build_contract_payload = _P.build_contract_payload
assert_contract_file_matches_source = _P.assert_contract_file_matches_source
build_store_projection = _P.build_store_projection
merge_projection_into_store_rows = _P.merge_projection_into_store_rows
iter_store_rows = _P.iter_store_rows
all_store_item_ids = _P.all_store_item_ids

# ── 编排面（模板 / definition payload / 注册）──
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
    """经公共观测器现读该 representation 冻结的 definitions，并与 source-locked 契约逐 digest 对账。

    🔴 自持而非转发编排工厂：`test_task75_published_identity_observer` 的 AST 判据要求
    provider（或白名单骨架）里**真有** await 观测器 + digest 比对 + raise —— 工厂闭包
    不在白名单骨架里，转发它等于让判据无分母。
    """
    from pathlib import Path

    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
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
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    return observation


async def publish_definitions(publisher: Any) -> Any:
    """五环发布：authority model（本模块）→ template → instrumentation → contract → bundle。"""
    assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    return await publish_with_authority(_O, publisher, authority)


# ── provisioning / attach 白名单接口别名（硬前置，缺一即「provider 是空壳」）──
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES

__all__ = [
    "ENTRY_ID", "ADAPTER_ID", "WP_CODES", "STORE_ITEM_ID", "SHEET_KEY",
    "ROW_IDENTITY_STORE_KEY", "ROWS_TABLE_KEY", "FIRST_DATA_ROW", "LAST_DATA_ROW",
    "FOOTER_ROW", "FOOTER_MARKER", "MANAGED_LAST_COL", "UUID_COL", "PHASE5_WAVE",
    "EXPECTED_PROFILE_ID", "build_contract_payload", "build_store_projection",
    "merge_projection_into_store_rows", "publish_definitions", "attach_adapters",
]
