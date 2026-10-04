# -*- coding: utf-8 -*-
"""N4 税金及附加「明细表 N4-2」—— N 循环首条真双向 entry（canary）。

spec: n-cycle-sync-foundation-and-first-canary（前序三份 N spec 只交付判据体系，manifest 一条
未翻；本模块是 N4 真改线的后端落点，照 L1 `phase5_l1_short_term_loans.py` 范式装配，全委派
`phase5_l_cycle_common` 公共骨架）。

受管 sheet = `税金及附加明细表N4-2`（openpyxl 逐格实测，净化后复算）：**单级表头** r8、
11 列 A-K、数据区 r9-18、footer r19（标签在 **A19**「合计」）。三个公式列逐行：
E=B+C+D（本期审定数）/ I=F+G+H（上期审定数）/ K=E-J（与应交税费贷方差异）。

🔴 差异 1：**canary 不是审定表**。`税金及附加审定表N4-1` 的 r7~r15 无一个可输入格（全是跨表
引用 N4-2 + 加总 + 裸 IF 变动率），写它会毁掉整册取数联动。真正的数据源头是 N4-2。

🔴 差异 2（相对 L1）：footer 标签在 **A 列**（`A19='合计'`），引擎默认即 A，无需像 L1 补 C。

🔴 差异 3：**单级表头**（N4-2 只 r8 一行表头），L1 是两级表头。

🔴 模板既知缺陷（T-1，记录型锁定，SHALL NOT 改 .xlsx）：`E9='=B9+C9+N4'`（第三加数误写列
引用，NC-32 A1 族）+ `D19='=SUM(D4:N18)'`（footer 越界）。materialize 不触碰既有公式格文本。

整册裸 IF 20 格全在派生表 `税金及附加审定表N4-1`（K/M 列变动率），**受管表零命中** ——
按 GC-2 per-file 策略仍挂中性化。

模板已净化（Task 7a 删 2 外链部件 + 中性化隐藏「原底稿」册 5 个外部引用公式，留 `.preclean.bak`）；
受管 sheet 逐格 0 diff，`TEMPLATE_SHA256` 取净化后值。

HTML store = `checklist_responses` 单条 item `N4-2-detail-rows`（前端 useN4Detail.ts rows 数组
JSON）。🔴 行身份是**熵键**（同税种可多行），保留 `rowKey` 不改语义键。真库 `N4-2-detail-rows`
现算 0 行，零迁移负担。

wp_code 裁决 = manifest 冻结的 `{'N4T'}`（宿主 GtN4TaxesAndSurcharges CamelCase 幻影码，
finder 零命中）—— 同 L1 的 `L1S` / d6 的 `D6C` 范式。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    SyncContract,
    contract_path_for,
    load_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    DescriptorFacts,
    RoomFacts,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_n4_store_payload_invalid"


#: 🔴 整组 re-export：守卫与生成器按 `phase5_n4_taxes_and_surcharges.<常量>` 读几何真源，
#: 本模块内未直接使用的也要留（F401 是有意的）。
from app.services.workpaper_sync.phase5_n4_sheets import (  # noqa: F401,E402
    ADAPTER_ID,
    AUTHORITY_MODEL,
    DERIVED_SHEET,
    EMPTY_STORE_PAYLOAD,
    ENTRY_ID,
    EXPECTED_PROFILE_ID,
    FIRST_DATA_ROW,
    FOOTER_LABEL_CELL,
    FOOTER_MARKER,
    FOOTER_ROW,
    FOOTER_SEARCH_COLUMN,
    FORMULA_COLUMNS,
    FORMULA_MASK,
    FORMULA_TEMPLATES,
    GROUP_HEADER_CELLS,
    HEADER_ROW,
    HTML_ONLY_ROW_KEYS,
    LAST_DATA_ROW,
    MANAGED_FIELD_SPECS,
    MANAGED_FIELD_SPECS_7,
    MANAGED_LAST_COL,
    MANAGED_SHEET,
    PHASE5_WAVE,
    ROW_IDENTITY_STORE_KEY,
    ROWS_TABLE_KEY,
    SHEET_KEY,
    SPEC_N42,
    STORE_ITEM_ID,
    TABLE_NAME,
    TEMPLATE_ID,
    TEMPLATE_RELATIVE_PATH,
    TEMPLATE_SHA256,
    UUID_COL,
    WP_CODES,
    _HTML_STORE_NOTE,
    _REVIEWED_BASIS,
)


# ═══════════════════════════════════════════════════════════════════════════
# 3~6. 权威模板 / 选型 / instrumentation / 契约 —— 装配全部委派 L 公共骨架
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync import phase5_l_cycle_common as _L  # noqa: E402

IDENTITY: Final[_L.LEntryIdentity] = _L.LEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=frozenset(WP_CODES),
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY,
    html_store_note=_HTML_STORE_NOTE,
    reviewed_basis=_REVIEWED_BASIS,
    authority_model=AUTHORITY_MODEL,
    expected_profile_id=EXPECTED_PROFILE_ID,
    html_only_keys=tuple(HTML_ONLY_ROW_KEYS),
    derived_readonly_sheet={
        "excel_name": DERIVED_SHEET,
        "reason": (
            "r7~r15 无一个可输入格：全是跨表引用 税金及附加明细表N4-2 + 加总 + "
            "裸 IF 变动率 ⇒ 只读投影，一格不写"
        ),
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_N42,)

#: 与公共骨架同一个类 —— 骨架抛的就是它，调用方 `except EntrySelectionError` 照常生效。
EntrySelectionError = _L.LEntrySelectionError
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return _L.excel_carrier_gate()


def authoritative_template_path() -> Path:
    return _L.authoritative_template_path(IDENTITY)


def read_authoritative_template() -> bytes:
    return _L.read_authoritative_template(IDENTITY)


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    """N4 独有：幻影码不得命中任何模板 + 父码 canonical resolver 落在权威模板。"""
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(
            f"缺少 wp_code {missing} 的 finder 实测结果 —— 零回退判据不得对未观测的码放行"
        )
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"wp_code {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
            "本 canary 的零回退判据要求它们全部解析不到任何文件"
        )
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 canary entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r} —— 重复入口不得注册"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} 与冻结的 {sorted(WP_CODES)} 不一致"
        )
    if resolution is not None:
        assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """复数形态（注册路径优先读这个）—— N4 本轮单受管 sheet，故只有一条。"""
    return _L.instrumentation_specs_for(IDENTITY, SPECS)


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return instrumentation_specs()[0]


def template_definition_payload() -> dict[str, Any]:
    return _L.template_definition_payload(IDENTITY, SPECS)


def instrumentation_definition_payload() -> dict[str, Any]:
    return _L.instrumentation_definition_payload(IDENTITY, SPECS)


def authority_model_payload() -> dict[str, Any]:
    return _L.authority_model_payload(IDENTITY)


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """薄转发框架层同名函数（逐字节等价）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(SPEC_N42, column_key, row_identity)


def build_contract_payload() -> dict[str, Any]:
    return _L.build_contract_payload(IDENTITY, SPECS)


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return _L.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# 7. HTML store 载荷拆分（stable field + 稳定 rowKey，流式）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_N42, ...)`，转译引擎异常为 domain 4xx。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )

    try:
        return _engine_build_store_projection(
            SPEC_N42, payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_N42, ...)`。

    🔴 幽灵行防护锚点取 `SPEC_N42.ghost_row_anchor_index=0`（`tax_type` 税种名，模板 A 列真业务名称）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_N42, projection=projection, base_rows=base_rows)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 受管的 store item 全集（单一口径，注册与门禁都读这里）。"""
    return (STORE_ITEM_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# 8. 发布
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID,
            "adapter_id": ADAPTER_ID,
            "authority_model": AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    """五环发布：template → instrumentation → contract → bundle（顺序不可颠倒）。"""
    out = await _L.publish_definitions(
        IDENTITY, SPECS, publisher, contract_payload=build_contract_payload()
    )
    return Phase5Definitions(
        authority_model_definition_id=out["authority"].definition_id,
        authority_model_definition_sha256=out["authority"].sha256,
        template_definition_id=out["template"].definition_id,
        template_definition_sha256=out["template"].sha256,
        instrumentation_definition_id=out["instrumentation"].definition_id,
        instrumentation_definition_sha256=out["instrumentation"].sha256,
        contract_definition_id=out["contract"].definition_id,
        contract_definition_sha256=out["contract"].sha256,
        bundle_id=out["bundle"].bundle_id,
        bundle_sha256=out["bundle"].canonical_sha256,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return _L.build_matcher(IDENTITY)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return _L.build_registration(
        IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room,
        contract=contract,
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
    return _L.register_adapter(
        registry, IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room,
        contract=contract,
    )


def manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> bool:
    """manifest 是否已把本 entry 裁决成 bidirectional 且 adapter_id 对得上。"""
    return _L.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> None:
    _L.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    return await _L.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


def contract_payload_digest() -> str:
    """现算 payload 的 canonical digest（生成器 `--check` 与守卫共用一个口径）。"""
    return canonical_digest(build_contract_payload())


def dump_contract_json() -> str:
    return _L.dump_contract_json(build_contract_payload())


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """按 manifest + 真库 representation 把本 entry 的 adapter 挂进 registry（三道前置缺一返空）。"""
    return await _L.attach_l_entry_adapter(
        registry, IDENTITY, session=session, contract_payload_builder=build_contract_payload
    )


# ═══════════════════════════════════════════════════════════════════════════
# 10. provisioning / attach 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这三个别名是**硬前置**，不是装饰（K 教训）：
# · `fix_task76_provision_projection_definitions.py` 经 `projection_provisioning.
#   load_projection_supply()` 只认 `publish_pilot_definitions` 与 `PILOT_WP_CODES`，
#   缺任一即抛 `ProviderModuleNotAllowedError: provider 是空壳`；
# · `registry._load_entry_attach()` 只认 `attach_pilot_adapters`。

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
