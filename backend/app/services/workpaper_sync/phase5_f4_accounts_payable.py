# -*- coding: utf-8 -*-
"""F4 应付账款 —— Phase 5 entry 模块（从零建）。

spec: f4-sync-coverage-and-first-canary · Task 6 · Requirements 1.2 / 1.3

canary = **F4-6 关联方及交易检查表**（裁决 F4-H1：与 F1-6/F3-6 三家同型，但公式镜像）。
接入顺序：F4-6 → F4-5 → F4-8（双区）→ F4-7（五区）→ F4-2（明细+账龄×2）→ [F4-9 容量裁决] → F4-1（两区）。
F4-3 / F4-4：可行性核。

🔴 **F4A 幻影码撞真实程序表路由码**（全 F 循环唯一，裁决 F4-H2）：
`wp_code_overrides.json` 有 `F4A -> f4-accounts-payable`（应付账款实质性程序表的路由码），
而 manifest 的 `wp_code_patterns` 恰好也是 `F4A`（宿主 `GtF4AccountsPayable` CamelCase 派生）。
两侧都不改（改 manifest 要动生成器、改 overrides 会断程序表路由），用四条隔离事实钉死：

| 判据 | 实测（2026-09-26） |
|---|---|
| `wp_templates/_index.json` 无 `F4A` | ✅ 476 条里 F 循环只有 F0~F5 |
| `wp_index` 无 `F4A` | ✅ 0 行（F4 真码 5 行） |
| provisioner 用真码 | ✅ 裁决文件 `wp_codes=["F4"]` |
| `assert_no_implicit_template_fallback('F4A')` | ✅ 前两条成立故可过 |

⇒ 幻影码只存在于**路由表**一处；误当业务码用时得到空集（不是命中程序表）。

🔴 契约装配走框架层 `spec_to_contract_sheet_payload`（不手写 table payload）——
理由与 F3 同（F1 手写版缺 `anchor` 等必填字段，`parse_contract` 直接抛）。
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
    """冻结的 F4 entry 不再满足选型必要条件。"""

    error_code = "sync_phase5_f4_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_f4_store_payload_invalid"


PHASE5_WAVE: Final[str] = "phase5_accounts_payable"
ENTRY_ID: Final[str] = "xlsx/gt-f4-accounts-payable"
ADAPTER_ID: Final[str] = "f4.accounts_payable_detail"

#: 🔴 幻影码（撞程序表路由码，见模块 docstring）。provisioner 用裁决真码 `["F4"]`。
WP_CODES: Final[frozenset[str]] = frozenset({"F4A"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "F/F4 应付账款.xlsx"
#: openpyxl 实测（108,329 B）。
TEMPLATE_SHA256: Final[str] = (
    "e20e62725c209b716eab4977231f21c627ab92346a72b58c20acdc7a6f1711fd"
)

STORE_ITEM_ID: Final[str] = "F4-6-rows"
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
            f"冻结的 F4 entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
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
# 🔴 F4 是 F 循环受管区最多的 entry：F4-7 五区 + F4-8 双区 + F4-1 两区 + 单区四张 = 13 区。
#    同 sheet 多区靠 `uuid_col` 配对 spec↔contract table（框架层
#    `spec_to_contract_sheet_payload` 注释：缺它 → 匹配 0 张 → ProviderCapabilityError）
#    ⇒ 各区必须实测**互不相同**的空列。spec design 受管区清单把 F4-7 五区全写 L、
#    F4-8 双区全写 S、F4-1 两区全写 M，那是不可用的声明，Task 2 须逐区重测。
# ═══════════════════════════════════════════════════════════════════════════

#: canary：F4-6 关联方及交易检查表（裁决 F4-H1）
_INCLUDE_F406: Final[bool] = True
#: F4-5 长期挂账检查表（第二张，数据区零公式）
_INCLUDE_F405: Final[bool] = True
#: F4-8 应付账款检查表（双区，兄弟 Table ref 首验）
_INCLUDE_F408: Final[bool] = True
#: F4-7 未入账检查表（**五区**，含除零公式列 G=365/(E/F)）
_INCLUDE_F407: Final[bool] = True
#: F4-2 明细表（两级表头 + nested 账龄 ×2；仅 THREE_YEAR 启用）
_INCLUDE_F402: Final[bool] = True
#: F4-9 供应商融资检查表（分组表，容量裁决后限额受管）
_INCLUDE_F409: Final[bool] = False
#: F4-1 审定表两区（性质区 + 账龄区；取数口径依赖 F1 spec 的三家统一裁决）
_INCLUDE_F401: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_F406:
        from app.services.workpaper_sync import phase5_f4_06_related_party as _f406

        specs.append(_f406.SPEC_F406)
    if _INCLUDE_F405:
        from app.services.workpaper_sync import phase5_f4_05_long_outstanding as _f405

        specs.append(_f405.SPEC_F405)
    if _INCLUDE_F408:
        from app.services.workpaper_sync import phase5_f4_08_voucher_check as _f408

        specs.extend((_f408.SPEC_F408_DEBIT, _f408.SPEC_F408_CREDIT))
    if _INCLUDE_F407:
        from app.services.workpaper_sync import phase5_f4_07_unrecorded as _f407

        specs.extend(
            (
                _f407.SPEC_F407_PAYMENT_WINDOW,
                _f407.SPEC_F407_ESTIMATED_INBOUND,
                _f407.SPEC_F407_UNPROCESSED_INVOICE,
                _f407.SPEC_F407_SUBSEQUENT_PAYMENT,
                _f407.SPEC_F407_SUBSEQUENT_INCREASE,
            )
        )
    if _INCLUDE_F402:
        from app.services.workpaper_sync import phase5_f4_02_detail as _f402

        specs.append(_f402.SPEC_F402)
    if _INCLUDE_F409:
        from app.services.workpaper_sync import phase5_f4_09_supplier_financing as _f409

        specs.append(_f409.SPEC_F409)
    if _INCLUDE_F401:
        from app.services.workpaper_sync import phase5_f4_01_adjudication as _f401

        specs.extend((_f401.SPEC_F401_NATURE, _f401.SPEC_F401_AGING))
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部受管 store item（出/回两方向都从它取）。

    🔴 只取**主键**，不取 legacy 别名（需求 2.3）：F4-7 三区各有 2 个别名
    （`F4-7-receipt` / `F4-7-invoice` / `F4-7-purchase` 等）、F4-9 有 7 个别名
    （`F4-9-factoring-rows` 等）—— 把别名也声明为受管区会造成一区两 binding。
    """
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
        f"store_item_id {store_item_id!r} 未在 F4 受管清单里登记 —— "
        f"当前受管: {list(all_store_item_ids())}"
    )


#: 🔴 判定为 HTML-only 的区（裁决 FC-6 / F4-H4 / F4-P10）—— 登记以证明"不是漏声明"。
#: 判据断言这些键**不在** `all_store_item_ids()`。
HTML_ONLY_STORE_KEYS: Final[tuple[tuple[str, str], ...]] = (
    (
        "F4-3-rows",
        "调整分录汇总 hub，接 useAdjustmentCentralSync ⇒ single_html（FC-6）",
    ),
    (
        "F4-4-turnover",
        "实质性分析付款期区：dict 包 + 9 固定行（非行数组），RowTableSheetSpec 不适用；"
        "前十名区从 F4-2 动态聚合 ⇒ html_only（裁决 F4-P10）",
    ),
    (
        "F4-9-rows",
        "供应商融资分组表：数据区中间有小计行 + groupId 动态分组键 + 合计行三小计相加 ⇒ "
        "html_only（裁决 F4-H4，需引擎层扩展支持分组表）",
    ),
)

#: 🔴 零写入读键（读方有、全仓无写方 ⇒ 恒 undefined 的兼容回退）。
#: 登记而不误接（需求 2.4 / Property 18）—— 它们不得出现在 `all_store_item_ids()`。
ZERO_WRITER_READ_KEYS: Final[tuple[str, ...]] = (
    "F4-8-debit-note",
    "F4-8-credit-note",
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
        raise EntrySelectionError("F4 当前无受管 sheet —— 灰度开关全关时不应装配定义")
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
            "F4 应付账款：结构化 Tab（HTML store）与 OnlyOffice 共写同一份权威模板，"
            "投影契约是唯一权威 —— 与 D1~D7 / E1 / F1 同型"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 契约装配（🔴 走框架层 `spec_to_contract_sheet_payload`，不手写 table payload）
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "F4 应付账款的结构化 Tab 行数据存成 checklist_responses 的 remark JSON 数组，"
    "一张 sheet 一条 item。本契约按 stable field + rowId 拆开，禁止把整 JSON 当一个字段。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 F/F4 应付账款.xlsx（15 sheets）+ 前端 useF4*.ts 按值 grep + "
    "真库 checklist_responses 载荷实测（F4-6-rows 675 B / 2 行全带 rowId）"
)


def build_contract_payload() -> dict[str, Any]:
    """从受管 spec 清单自动派生 per-entry contract payload。

    🔴 每张 sheet 的 payload 由框架层 `spec_to_contract_sheet_payload(spec)` 产出 ——
    它与 D1~D7 七家磁盘契约逐字段一致（含 `anchor` / `header_rows` /
    `row_identity.json_pointer` / `delete_policy` / `uuid_col` / 每字段的
    `json_pointer`+`cell`+`source_ref`+`header_source_ref`+`store_item_id`）。
    手写会漏字段并在 `parse_contract` 处炸（F1 的现成反例，见模块 docstring）。

    同 sheet 多区（F4-7 五区 / F4-8 双区 / F4-1 两区）时按 `sheet_key` 合并 tables ——
    框架层用 `uuid_col` 把 spec 与 table 一一配对，故各区的 `uuid_col` 必须互不相同。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("F4 当前无受管 sheet —— 灰度开关全关时不应装配契约")

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
            "backend/scripts/gen/generate_phase5_f4_contract.py --apply` 重生成"
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
