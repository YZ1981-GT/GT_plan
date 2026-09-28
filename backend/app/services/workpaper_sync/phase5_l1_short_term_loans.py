# -*- coding: utf-8 -*-
"""L1 短期借款「明细表 L1-2」—— L 循环首条真双向 entry。

spec: l-cycle-true-adapter-registration（前序 `l-cycle-sync-foundation-and-first-canary`
只交付判据体系，manifest 一条未翻；本模块是真改线的后端落点）

═══ 与 d6 同范式（两级表头行表），三处关键差异 ═══

受管 sheet = `明细表L1-2`（openpyxl 逐格实测）：两级表头（行 8 组标题 + 行 9 叶子），
30 列 A-AD（有效业务列到 AB），数据区行 10-25，footer 行 26。
五个公式列逐行：K=H+I-J（未审期末）、R=H+L+M（审定期初）、S=I+N+P（审定本期增加）、
T=J+O+Q（审定本期减少）、U=R+S-T（审定期末）—— 负债口径「期初+增加-减少」。

🔴 差异 1：**canary 不是审定表**。前序 spec 选 `审定表L1-1` + `L1-adj-*` 键组，但该表
R7~R11 **无一个可输入格**（B/C/D/F/G/H 全是 SUMIF 引用本表、E/I/J/L 是加总、K 是裸 IF），
写它会毁掉整册取数联动。真正的数据源头是本表。审定表改为 formula_mask 全覆盖的只读投影。

🔴 差异 2：**footer 标签在 C 列**（`C26 = '合计'`，A26 为空），不是 d6 的 A 列「合   计」
（3 半角空格）。footer H26~U26 连续 14 列全是 `=SUM(X10:X25)`。

🔴 差异 3：**册内零 Excel Table、零 definedName**（实测），故 `GT_L12_ROWS` 是本契约要
新建的表；隐藏 UUID 列取 `max_column + 1` = AE。

整册裸 IF **112** 格（审定表L1-1 34 / 附注上市 28 / 附注国企 20 / 利息测算表L1-5 22 /
逾期贷款检查表L1-7 8），**受管表零命中** —— 按 GC-2 per-file 策略仍挂中性化。

HTML store = `checklist_responses` 单条 item `L1-2-rows`（前端 useL1Detail.ts 的 DetailRow
整行数组 JSON.stringify）。🔴 旧形态 `L1-det-{rowIndex+1}-{field}` 是**位置化行身份**，
contract schema 明令拒绝 index/ordinal ⇒ 已切稳定 `rowId`；真库 `L1-det-*` 现算 0 行，
零迁移负担。其余四表（int/cred/ovd/plg）仍位置化，本 spec 不动（`int` 被 H2 跨循环消费）。

wp_code 裁决 = manifest 冻结的 `{'L1S'}`（宿主 GtL1ShortTermLoans CamelCase 幻影码，
finder 零命中）—— 同 d6 的 `D6C` 范式。
"""

from __future__ import annotations

import hashlib
import json
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
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_instrumentation_payload,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_l1_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_l1_store_payload_invalid"


from app.services.workpaper_sync.phase5_l1_sheets import (
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
    FORMULA_COLUMNS,
    FORMULA_MASK,
    FORMULA_TEMPLATES,
    GROUP_HEADER_CELLS,
    HEADER_GROUP_ROW,
    HEADER_LEAF_ROW,
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
    SPEC_L12,
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
# 3. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 4. 选型必要条件（真实 manifest，不经封闭枚举）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
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


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """复数形态（注册路径优先读这个）—— L1 本轮单受管 sheet，故只有一条。"""
    return (instrumentation_spec(),)


def template_definition_payload() -> dict[str, Any]:
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(read_authoritative_template()),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": ENTRY_ID,
        "pilot_class": PHASE5_WAVE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. per-entry contract（与磁盘契约双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """薄转发框架层同名函数（逐字节等价）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(SPEC_L12, column_key, row_identity)



def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    template_payload = template_definition_payload()
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload()
        ),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        #: 🔴 只用 `hidden_uuid_column`（册内零 definedName / 零 Excel Table，
        #: 声明 `defined_name` / `excel_table` 需先新建；`hidden_sheet` 由 Task 17 的
        #: `_GT_SYNC` 注入）。sheet 锚点走 `excel_table_sheet_association`，
        #: 禁 `sheet_id` / `sheet_display_name`（OO 9.4 实测 failed）。
        "identity_carriers": [
            "hidden_sheet",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": [spec_to_contract_sheet_payload(SPEC_L12)],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "row_identity_key": ROW_IDENTITY_STORE_KEY,
                "shape": "json_array_of_row_objects",
                "html_only_keys": list(HTML_ONLY_ROW_KEYS),
                "note": _HTML_STORE_NOTE,
            },
            "derived_readonly_sheet": {
                "excel_name": DERIVED_SHEET,
                "reason": (
                    "R7~R11 无一个可输入格：B/C/D/F/G/H 全是 SUMIF 引用受管表、"
                    "E/I/J/L 是加总、K 是裸 IF、R11 是 SUM ⇒ 只读投影，一格不写"
                ),
            },
            "reviewed_basis": _REVIEWED_BASIS,
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
            "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_l_contracts.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. HTML store 载荷拆分（stable field + 稳定 rowId，流式）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_L12, ...)`。

    🔴 **必须转译引擎异常**：引擎抛 `RowTableStorePayloadError(Exception)` 非 domain 错误 ⇒
    直接冒泡是 opaque 500；畸形 store 载荷属用户侧数据问题，必须 4xx。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )

    try:
        return _engine_build_store_projection(
            SPEC_L12, payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_L12, ...)`。

    🔴 幽灵行防护锚点取 `SPEC_L12.ghost_row_anchor_index=2`（`bank` 贷款单位）——
    `[0]` 的 `seq_no` 是整数序号（`0` 是合法真值不是"空"信号，同 d6）、
    `[1]` 的 `loan_type` 是枚举（同 d5 的 `category`，枚举不适合当锚点）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_L12, projection=projection, base_rows=base_rows)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 受管的 store item 全集（单一口径，注册与门禁都读这里）。

    🔴 只登记**本轮真受管**的键。其余四表（`L1-int-*` / `L1-cred-*` / `L1-ovd-*` /
    `L1-plg-*`）仍是位置化形态、本 spec 不动，**不得**预登记 —— 预登记会让
    `check_sheet_specs_fully_registered` 的分母失真。
    """
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
    contract = assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise EntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise EntrySelectionError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instrumentation.definition_id}",
                "digest": instrumentation.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_definition.definition_id}",
                "digest": contract_definition.sha256,
            },
        },
    )
    return Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instrumentation.definition_id,
        instrumentation_definition_sha256=instrumentation.sha256,
        contract_definition_id=contract_definition.definition_id,
        contract_definition_sha256=contract_definition.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


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
        contract=contract if contract is not None else load_contract_from_disk(),
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
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
    )
    registry.register(registration)
    return registration


def manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> bool:
    """manifest 是否已把本 entry 裁决成 bidirectional 且 adapter_id 对得上。

    🔴 这是「先翻 manifest 再注册」的门：注册路径读它，避免 manifest 仍是
    `legacy_fake_bidirectional` 时就把 adapter 挂上去（那会让账本与运行时脱钩）。
    """
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        return False
    if str(entry.get("capability") or "") != Capability.bidirectional.value:
        return False
    return str(entry.get("adapter_id") or "") == ADAPTER_ID


def assert_manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> None:
    if not manifest_capability_enabled(manifest):
        raise EntrySelectionError(
            f"manifest 尚未把 {ENTRY_ID!r} 裁决成 bidirectional + "
            f"adapter_id={ADAPTER_ID!r} —— 发布链第⑤环走完后须重生成 manifest 再注册"
        )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
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


def contract_payload_digest() -> str:
    """现算 payload 的 canonical digest（生成器 `--check` 与守卫共用一个口径）。"""
    return canonical_digest(build_contract_payload())


def dump_contract_json() -> str:
    """生成器落盘用的 JSON 文本（2 空格缩进 + 排序键 + 尾换行，与既有契约文件同形态）。"""
    return json.dumps(
        build_contract_payload(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """按 manifest + 真库 representation 把本 entry 的 adapter 挂进 registry。

    三道前置缺一即静默返回空元组（不是抛错 —— 启动期 attach 对「还没供给」必须容忍）：
    ① manifest 已裁决 bidirectional + adapter_id 对得上；
    ② 真库有 current published representation；
    ③ 该 representation 绑定了 definition bundle。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=ENTRY_ID
    )
    if representation_id is None:
        return ()
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None or representation.definition_bundle_id is None:
        return ()

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— "
            "不可达入口不得注册 adapter"
        )
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# 10. provisioning / attach 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这三个别名是**硬前置**，不是装饰：
# · `fix_task76_provision_projection_definitions.py` 经
#   `projection_provisioning.load_projection_supply()` 只认 `publish_pilot_definitions`
#   与 `PILOT_WP_CODES`，缺任一即抛 `ProviderModuleNotAllowedError: provider 是空壳`
#   （本 spec Task 7 实测踩到）；
# · `registry._load_entry_attach()` 只认 `attach_pilot_adapters`。

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
