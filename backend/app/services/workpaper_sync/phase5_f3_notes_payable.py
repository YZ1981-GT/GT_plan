# -*- coding: utf-8 -*-
"""F3 应付票据 —— Phase 5 entry 模块（从零建）。

spec: f3-sync-coverage-and-first-canary · Task 7 · Requirements 1.2 / 1.3

═══ 与 D3 同范式、与 E1 同级（连 provider 都没有，前半段必须走完整发布链，FC-1）═══

canary = **F3-5 逾期票据检查**（裁决 F3-H1：数据区零公式 / F3 唯一有真载荷的 store 键 /
单区 / 零跨 sheet 消费方）。接入顺序（形态驱动 + 前置驱动）：

    F3-5（canary）→ F3-6 关联方 → F3-7 三区 → F3-2 明细 → F3-4 利息测算 → F3-1 审定表
    F3-3：FC-6 可行性核（默认 single_html）

🔴 **契约装配走框架层 `spec_to_contract_sheet_payload`**，不手写 table payload。
   实测依据：F1 provider（并发会话 WIP）手写了 `_rows_table_payload`，产出的 payload 缺
   `anchor` / `header_rows` / `delete_policy` / `row_identity.json_pointer` / 字段的
   `json_pointer`+`cell`+`source_ref`+`header_source_ref`+`store_item_id`，`parse_contract`
   直接抛 `ContractSchemaError: table anchor 必须是 A1 单元格，实得 None`。
   框架层那份的产出与 D1~D7 七家磁盘契约逐字段一致（已验证）。
   详见 `.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task0-prerequisites.md` §10。
"""
from __future__ import annotations

import hashlib
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
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_instrumentation_payload_for_sheets,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)
from app.services.workpaper_sync.sheet_geometry import col_index


class EntrySelectionError(SyncDomainError):
    """冻结的 F3 entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_f3_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法（非数组 / 缺 row identity / 重复 identity）。"""

    error_code = "sync_phase5_f3_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（真 manifest / 真库 / openpyxl 实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_notes_payable"
ENTRY_ID: Final[str] = "xlsx/gt-f3-notes-payable"
ADAPTER_ID: Final[str] = "f3.notes_payable_detail"

#: 🔴 manifest 冻结的幻影码（FC-2：matcher 域用幻影码，provisioning 用真码）。
#: 宿主 `GtF3NotesPayable` CamelCase 派生；`wp_index` 与 `wp_templates/_index.json` 均 0 命中。
#: provisioner 用 `workpaper_sync_entry_wp_code_adjudication.json` 的真码 `["F3"]`（wp_index 4 行）。
WP_CODES: Final[frozenset[str]] = frozenset({"F3N"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "F/F3 应付票据.xlsx"
#: openpyxl 实测（79,616 B）。
TEMPLATE_SHA256: Final[str] = (
    "06de707ba4d4f8d91534e872c7d135b9576cc3a012e3877b1f60db59ce6b3a6b"
)

#: canary 的 store item（单数形态，与七家 provider 的既有接口对齐）。
STORE_ITEM_ID: Final[str] = "F3-5-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板（sha 哨兵）
# ═══════════════════════════════════════════════════════════════════════════


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
            f"冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（照 D3 同签名：`resolution` 必填、**无关闭开关**、真 manifest 真调）
#
# 🔴 FC-2 记录的 E1 反例：`phase5_e1_monetary_fund.WP_CODES = {"E1"}`（真码）而 manifest 是
#    `["E1M"]`，`assert_entry_selectable()` 默认调用对真 manifest 必抛，而 E1 测试只断言
#    `WP_CODES == {"E1"}`、从不真调 ⇒ 守卫空转。本模块不带 `require_wp_codes` 之类开关，
#    且判据里有一条对真 manifest 的真调（`test_f3_property1_2_entry_selectable.py`）。
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
            f"幻影码 {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
            "零回退判据要求它们全部解析不到任何文件"
        )
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 F3 entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
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
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单（照 phase5_d3_expansion:75-116 范式）
#
# 🔴 除 canary 外全部默认 False：每张一个 commit、一张过一次门（D1 引擎落地时的安全性来源）。
# ═══════════════════════════════════════════════════════════════════════════

#: canary：F3-5 逾期票据检查（裁决 F3-H1）
_INCLUDE_F305: Final[bool] = True
#: F3-6 关联方及交易检查表（第二张，验证"复用框架层零改动"）
#: 🔴 Task 13 实测后开启：单级表头 R6（R5 是说明文字）· 数据区 R7-12 · footer R13 ·
#: uuid_col N · 一个公式列 G（=D+F-E，与前端 computeRelatedPartyRow 逐字等价 FC-5）·
#: FC-10 零命中 · 🔴 last_data_row=12 是硬上限（R18-26 是 DV 源区，插行余量为 0）。
#: 实测结论：`RowTableSheetSpec` 原样够用，**零框架层改动**。
_INCLUDE_F306: Final[bool] = True
#: F3-7 应付票据检查表（三区：debit / credit / subsequent）
#: 🔴 Task 14 实测后开启：三区几何各不相同（R17-36 / R41-58 / R63-79，行数 20/18/17），
#: 且区② 证据组宽 7 列（H:K 入库单 + L:N 采购发票）而区①③ 宽 5 列（H:I 审批单 + J:L 回单）
#: ⇒ 其后列整体右移 2 列（索引号/是否异常在 P/Q 而非 N/O），footer SUM 列集也随之不同
#: （区② 用 N，区①③ 用 L）⇒ **三份独立 field_specs 是必须的**（裁决 F3-H3 同型）。
#: uuid_col S/T/U 逐区独立（兄弟 Table ref 位移靠它配对），三者均超 max_column=R 需扩列。
_INCLUDE_F307: Final[bool] = True
#: F3-2 明细表（两级表头；J/U 两列卡 FC-10）
_INCLUDE_F302: Final[bool] = True
#: F3-4 利息测算表（H 列方向③：mode=formula 不受管，2026-10-07 完成）
_INCLUDE_F304: Final[bool] = True
#: F3-1 审定表（双区声明完成，2026-10-07）
_INCLUDE_F301: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。

    单一口径：投影/合并/契约装配/instrumentation 全部从这里取，不各自维护第二份清单。
    """
    specs: list[Any] = []
    if _INCLUDE_F305:
        from app.services.workpaper_sync import phase5_f3_05_overdue as _f305

        specs.append(_f305.SPEC_F305)
    if _INCLUDE_F306:
        from app.services.workpaper_sync import phase5_f3_06_related_party as _f306

        specs.append(_f306.SPEC_F306)
    if _INCLUDE_F307:
        from app.services.workpaper_sync import phase5_f3_07_voucher_check as _f307

        specs.extend(
            (_f307.SPEC_F307_DEBIT, _f307.SPEC_F307_CREDIT, _f307.SPEC_F307_SUBSEQUENT)
        )
    if _INCLUDE_F302:
        from app.services.workpaper_sync import phase5_f3_02_detail as _f302

        specs.append(_f302.SPEC_F302)
    if _INCLUDE_F304:
        from app.services.workpaper_sync import phase5_f3_04_interest as _f304

        specs.append(_f304.SPEC_F304)
    if _INCLUDE_F301:
        from app.services.workpaper_sync import phase5_f3_01_adjudication as _f301

        specs.extend((_f301.SPEC_F301_SEED, _f301.SPEC_F301_SLOT))
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部受管 store item（出/回两方向都从它取，D4-35 恒空根因的防复发口径）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    names: list[str] = []
    for spec in managed_row_table_specs():
        if spec.managed_sheet not in names:
            names.append(spec.managed_sheet)
    return tuple(names)


def _spec_of_store_item(store_item_id: str) -> Any:
    """store_item_id → spec。未登记即抛（不静默跳过 —— D4-35 恒空根因）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise StorePayloadError(
        f"store_item_id {store_item_id!r} 未在 F3 受管清单里登记 —— "
        f"当前受管: {list(all_store_item_ids())}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation（复数；照 D3/D2 已验证范式）
# ═══════════════════════════════════════════════════════════════════════════


def _managed_last_col_of(spec: Any) -> str:
    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row,
        last_data_row=spec.last_data_row,
        footer_row=spec.footer_row,
        managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col,
        table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """复数 —— 每个受管区一条。单数会让扩容面对判据不可见（D2 注释警告过的假绿）。"""
    return tuple(_instrumentation_of(spec) for spec in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("F3 当前无受管 sheet —— 灰度开关全关时不应装配定义")
    return build_template_payload(
        spec=_instrumentation_of(specs[0]),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "entry_id": ENTRY_ID,
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "pilot_class": PHASE5_WAVE,
        "reason": (
            "F3 应付票据：结构化 Tab（HTML store）与 OnlyOffice 共写同一份权威模板，"
            "投影契约是唯一权威 —— 与 D1~D7 / E1 / F1 同型"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 契约装配（🔴 走框架层 `spec_to_contract_sheet_payload`，不手写 table payload）
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "F3 应付票据的结构化 Tab 行数据存成 checklist_responses 的 remark JSON 数组，"
    "一张 sheet 一条 item。本契约按 stable field + rowId 拆开，禁止把整 JSON 当一个字段。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 F/F3 应付票据.xlsx（12 sheets）+ 前端 useF3*.ts 按值 grep + "
    "真库 checklist_responses 载荷实测（F3-5-rows 675 B / 2 行全带 rowId）"
)


def build_contract_payload() -> dict[str, Any]:
    """从受管 spec 清单自动派生 per-entry contract payload。

    🔴 每张 sheet 的 payload 由框架层 `spec_to_contract_sheet_payload(spec)` 产出 ——
    它与 D1~D7 七家磁盘契约逐字段一致（含 `anchor` / `header_rows` /
    `row_identity.json_pointer` / `delete_policy` / `uuid_col` / 每字段的
    `json_pointer`+`cell`+`source_ref`+`header_source_ref`+`store_item_id`）。
    手写会漏字段并在 `parse_contract` 处炸（F1 的现成反例，见模块 docstring）。

    同 sheet 多区（F3-7 三区 / F3-1 拆两 spec）时按 `sheet_key` 合并 tables ——
    框架层用 `uuid_col` 把 spec 与 table 一一配对，故各区的 `uuid_col` 必须互不相同。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("F3 当前无受管 sheet —— 灰度开关全关时不应装配契约")

    sheets: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for spec in specs:
        payload = spec_to_contract_sheet_payload(spec)
        existing = by_key.get(spec.sheet_key)
        if existing is None:
            by_key[spec.sheet_key] = payload
            sheets.append(payload)
            continue
        # 同 sheet 兄弟区：合并 tables（配对键是 uuid_col，须逐区不同）
        sibling_uuid_cols = {t.get("uuid_col") for t in existing["tables"]}
        if payload["tables"][0].get("uuid_col") in sibling_uuid_cols:
            raise EntrySelectionError(
                f"sheet {spec.managed_sheet!r} 的兄弟区 uuid_col 重复 "
                f"({payload['tables'][0].get('uuid_col')!r}) —— "
                "同 sheet 多 table 靠 uuid_col 配对 spec↔table，重复会匹配 0 张并抛 "
                "ProviderCapabilityError；须为每区实测独立空列"
            )
        existing["tables"].extend(payload["tables"])

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
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": sheets,
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
                "note": _HTML_STORE_NOTE,
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
            f"source={canonical_digest(expected)}；请用 "
            "`& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_f3_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. store 投影 / 合并（薄转发框架层引擎，零算法复制）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str = STORE_ITEM_ID,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine_build,
    )

    return _engine_build(
        _spec_of_store_item(store_item_id), payload, contract=contract, limits=limits
    )


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str = STORE_ITEM_ID,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(
        _spec_of_store_item(store_item_id), projection=projection, base_rows=base_rows
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 发布（五个 definition + bundle；照 D3:770）
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
# 9. adapter 注册与宿主接线（🔴 照 phase5_d3_prepaid_receipts:854）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """🔴 `document_type` 必填 —— E1 的 WIP 反例缺它即 `TypeError`（FC-2 顺带发现 1）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    """🔴 字段名照 D3:854 —— `matcher=` / `declared_capability=` / `contract=`，
    **不是** `adapter_id=` / `entry_matcher=`（E1 WIP 用错过）。
    """
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
        resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT)),
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


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """🔴 供给未就绪时返回空元组且一次库都不读（BP-61-1 卡点下的诚实行为）。"""
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

    representation_id = await resolve_visible_current_representation_id(session, entry_id=ENTRY_ID)
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

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
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


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    entry = manifest_entries_by_id(manifest if manifest is not None else load_entry_manifest())[
        ENTRY_ID
    ]
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional "
            "并重生成 manifest"
        )
    if str(entry.get("adapter_id") or "") != ADAPTER_ID:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest adapter_id={entry.get('adapter_id')!r} "
            f"与本 entry 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. provisioning / attach 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
