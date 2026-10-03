# -*- coding: utf-8 -*-
"""H 循环（固定资产）9 条 entry 的 provider 公共骨架。

spec: `h-cycle-sync-foundation-and-first-canary` · Task 20
下游：`h3-h5-h7-variant-axis-and-dynamic-column-paradigm` /
　　　`h4-h8-sub-entry-lanes-and-seed-identity-defects` /
　　　`h2-h6-h10-pilot-cross-reference-lanes`

═══ 为什么本模块存在 ═══

D/E/F/G 各循环的 provider 把「模板取字节 / 选型必要条件 / instrumentation 装配 /
契约装配 / matcher / 注册 / attach」这七段**各抄一遍**。到 G2 为止已经抄了 11 份，
每份 800~900 行，其中 600+ 行逐字相同。H 循环要接 **9 条** ——
再抄 9 份就是 9 个漂移面：引擎改一处要改 9 处，漏一处就是静默旧行为。

本模块把七段收进**一处**，per-entry 模块只剩「声明」：
:class:`HEntryIdentity` 一条身份 + 一组 `RowTableSheetSpec`。

🔴 **本模块不含任何 wp_code / sheet 名 / 键名字面量** —— 全部由调用方经
:class:`HEntryIdentity` 与 spec 传入。它只提供「怎么做」，不提供「做什么」。

═══ 🔴 与 G2 骨架的**唯一实质差异**：幻影码零回退的不变量口径 ═══

G2 的 `assert_no_implicit_template_fallback()` 断言「幻影码**不得命中任何模板**」。
H 循环按值实测（`test_h_foundation_hc_guards.py::
test_phantom_codes_must_not_leak_into_another_entrys_workbook`）：

| 幻影码 | `find_template_file` 实测 | 根因 |
|---|---|---|
| `H2C` `H3I` `H4E` `H5O` `H7B` `H8R` `H9L` | **None**（7 条） | 真幻影码 |
| 🔴 `H6A` | `H6 固定资产清理.xlsx` | `H6A` **同时**是真实程序表码（`固定资产清理实质性程序表H6A`） |
| 🔴 `H10A` | `H10 资产处置损益.xlsx` | 同理（`资产处置损益实质性程序表H10A`） |

⇒ 照 G2 写，**H6 与 H10 两条 provider 会在注册路径上直接抛 `HEntrySelectionError`**。

真正要守的不变量不是「不得命中」，而是「**不得命中别的 entry 的册子**」：
`H6A` → H6 自己的册、`H10A` → H10 自己的册，属**同册别名**，无跨 entry 泄漏风险。
:func:`assert_phantom_code_does_not_leak` 按这个口径实现，并把「同册别名」
显式登记在 `HEntryIdentity.phantom_code_resolves_to_own_workbook` 上
—— 谁是别名必须**声明**，不能运行时随便放过（否则真泄漏也会被放过）。

另：`find_all_template_files`（sheet 级解析）对 9 个幻影码**一律返 `[]`** ⇒
sheet 级零回退在 9 条上全部成立，本模块一并断言。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field as dc_field
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

__all__ = [
    "HEntrySelectionError",
    "HStorePayloadError",
    "HEntryIdentity",
    "TemplateResolutionFacts",
    "H_AUTHORITY_ROOT",
    "H_PHASE5_IDENTITY_CARRIERS",
    "excel_carrier_gate",
    "authoritative_template_path",
    "read_authoritative_template",
    "assert_phantom_code_does_not_leak",
    "assert_entry_selectable",
    "instrumentation_specs_for",
    "template_definition_payload",
    "instrumentation_definition_payload",
    "sheets_payload",
    "build_contract_payload",
    "assert_contract_file_matches_source",
    "build_matcher",
    "build_registration",
    "register_adapter",
    "manifest_capability_enabled",
    "assert_manifest_capability_enabled",
    "resolve_published_frozen_definitions",
    "attach_h_entry_adapter",
    "H_AUTHORITY_MODEL",
    "HDefinitions",
    "authority_model_payload",
    "primary_instrumentation_spec",
    "publish_definitions_for",
    "publish_h_entry_definitions",
]


class HEntrySelectionError(SyncDomainError):
    """H 循环 entry 的选型必要条件不成立（模板字节变了 / manifest 事实变了 / 幻影码泄漏）。"""

    error_code = "sync_phase5_h_selection_invalid"


class HStorePayloadError(SyncDomainError):
    """H 循环 HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_h_store_payload_invalid"


H_AUTHORITY_ROOT: Final[str] = "backend/wp_templates"

#: 九条 H entry 的 authority model —— 与 D/E/F/G/L 已交付各家逐字相同。
#: `register()` 的 RG-8/RG-9（`assert_authority_model_contract_pairing`）要求
#: `projection_contract` 必须解析到 approved per-entry contract，H 九条都有。
H_AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 四载体（与 D/E/F/G 已交付 11 家逐字相同）。
H_PHASE5_IDENTITY_CARRIERS: Final[tuple[str, ...]] = (
    "hidden_sheet",
    "defined_name",
    "excel_table",
    "hidden_uuid_column",
)

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class HEntryIdentity:
    """一条 H entry 的冻结身份。per-entry 模块只声明它，七段流程全由本模块驱动。

    :param entry_id: manifest 的 `entry_id`（**持久化键**，GC-1 的 pointer 就用它）。
    :param adapter_id: 契约 id，同时是磁盘文件名（`h9.lease_liability_detail`）。
    :param phase5_wave: `pilot_class` 字段值。🔴 一律 `phase5_*` 范式，**不照** G7/H1 的 `pilot_*`
        —— 那两个是 Tasks 40~43 的先导形态，早于行表引擎，照它会写出无法复用引擎的单例代码。
    :param wp_codes: manifest 冻结的**幻影码**（FC-2：matcher 域用幻影码）。
    :param phantom_code_resolves_to_own_workbook: 🔴 该幻影码是否**同时**是真实程序表码
        （只有 `H6A` / `H10A` 两条为 True）。必须**显式声明** —— 运行时随便放过等于不守。
    :param template_relative_path: `backend/wp_templates/` 下的相对路径。
    :param template_sha256: slice 冻结的完整 64 位 sha256（字节变了即抛）。
    :param expected_profile_id: manifest `scenario_profile.profile_id`。
    :param primary_store_item_id: 主受管区的 store item（投影/合并的缺省口径）。
    :param tb_publish_gate: TB 发布门位置；**None 表示该 entry 无发布门**（HD-7 的 H8/H9）。
    """

    entry_id: str
    adapter_id: str
    phase5_wave: str
    wp_codes: frozenset[str]
    template_relative_path: str
    template_sha256: str
    primary_store_item_id: str
    expected_profile_id: str = "xlsx.editable.shared.single.room_service_wired.v1"
    phantom_code_resolves_to_own_workbook: bool = False
    tb_publish_gate: str | None = None
    #: 契约 `review` 段的额外键（变体轴 / 冻结键 / 子入口 / 客户端草稿声明 …）。
    extra_review: Mapping[str, Any] = dc_field(default_factory=dict)

    @property
    def template_file_name(self) -> str:
        return self.template_relative_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class TemplateResolutionFacts:
    """finder 实测结果（由判据 / 调用方现算后传入，本模块不自己调 finder 造事实）。

    :param by_wp_code: 幻影码 → `find_all_template_files()` 的 sheet 级命中（应恒为空）。
    :param single_resolution: 幻影码 → `find_template_file()` 的单册命中（`None` 或文件名）。
    """

    by_wp_code: Mapping[str, Sequence[Any]]
    single_resolution: Mapping[str, str | None]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path(identity: HEntryIdentity) -> Path:
    return excel_carrier_gate().assert_template_under_authority(
        identity.template_relative_path
    )


def read_authoritative_template(identity: HEntryIdentity) -> bytes:
    """读权威模板并核 sha256。字节变了立刻抛 —— 契约的几何全建立在这份字节上。"""
    data = authoritative_template_path(identity).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != identity.template_sha256:
        raise HEntrySelectionError(
            f"权威模板字节已变: {identity.template_relative_path} 实测 sha256={digest}，"
            f"冻结哨兵={identity.template_sha256}"
        )
    return data


def assert_phantom_code_does_not_leak(
    identity: HEntryIdentity, resolution: TemplateResolutionFacts
) -> None:
    """🔴 FC-2 零回退在 H 的**正确**口径：幻影码不得命中**别的 entry** 的册子。

    见模块 docstring 的口径说明。三条断言：

    1. **sheet 级解析恒空** —— `find_all_template_files(幻影码) == []`（9 条全成立）；
    2. 单册解析若为 `None` ⇒ 通过（7 条真幻影码）；
    3. 单册解析若非 `None` ⇒ 必须 ①`identity` 已**显式声明**它是同册别名，
       且 ②命中的就是**本 entry 自己**的册子。任一不满足即抛。
    """
    missing = sorted(set(identity.wp_codes) - set(resolution.by_wp_code))
    if missing:
        raise HEntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked_sheet_level = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked_sheet_level:
        raise HEntrySelectionError(
            f"幻影码 {sorted(leaked_sheet_level)} 在 sheet 级 finder 里命中了模板 —— "
            f"H 循环 9 条实测恒为空：{leaked_sheet_level}"
        )
    for code in sorted(identity.wp_codes):
        resolved = resolution.single_resolution.get(code)
        if resolved is None:
            continue
        name = str(resolved).replace("\\", "/").rsplit("/", 1)[-1]
        if not identity.phantom_code_resolves_to_own_workbook:
            raise HEntrySelectionError(
                f"幻影码 {code!r} 单册解析命中 {name!r}，但 entry {identity.entry_id!r} "
                "未声明 `phantom_code_resolves_to_own_workbook=True` —— "
                "同册别名必须显式声明，否则无法与真正的跨 entry 泄漏区分"
            )
        if name != identity.template_file_name:
            raise HEntrySelectionError(
                f"幻影码 {code!r} 单册解析命中**别的 entry** 的册子 {name!r}，"
                f"本 entry 的册子是 {identity.template_file_name!r} —— 这是真泄漏"
            )


def assert_entry_selectable(
    identity: HEntryIdentity,
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """对**真 manifest** 核四条事实 + 幻影码零泄漏（FC-2：不留关闭开关）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(identity.entry_id)
    if entry is None:
        raise HEntrySelectionError(f"冻结的 entry {identity.entry_id!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx":
        raise HEntrySelectionError(f"{identity.entry_id!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise HEntrySelectionError(
            f"{identity.entry_id!r} independent_entry={entry.get('independent_entry')!r}"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != identity.expected_profile_id:
        raise HEntrySelectionError(
            f"{identity.entry_id!r} profile_id={profile_id!r} 与冻结的 "
            f"{identity.expected_profile_id!r} 不符"
        )
    codes = {
        str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()
    }
    if codes != set(identity.wp_codes):
        raise HEntrySelectionError(
            f"{identity.entry_id!r} wp_code_patterns={sorted(codes)} "
            f"与冻结的 {sorted(identity.wp_codes)} 不一致"
        )
    assert_phantom_code_does_not_leak(identity, resolution)
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# instrumentation / 契约装配
# ═══════════════════════════════════════════════════════════════════════════


def _managed_last_col_of(spec: Any) -> str:
    if not spec.field_specs:
        raise HEntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(identity: HEntryIdentity, spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=identity.entry_id,
        template_id=spec.template_id,
        template_relative_path=identity.template_relative_path,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row,
        last_data_row=spec.last_data_row,
        footer_row=spec.footer_row,
        managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col,
        table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def instrumentation_specs_for(
    identity: HEntryIdentity, specs: Sequence[Any]
) -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 的全部 instrumentation 声明（**复数** —— 注册路径读的是这个）。

    🔴 单数形态是 D4-35 事故的形态：契约有 8 张 sheet、instrumentation 只给 7 个 spec ⇒
    attach 期 `_align_specs_to_sibling_tables` fail-closed 打挂**整个 entry**。
    """
    return tuple(_instrumentation_of(identity, s) for s in specs)


def primary_instrumentation_spec(
    identity: HEntryIdentity, specs: Sequence[Any]
) -> ExcelInstrumentationSpec:
    """取本 entry 的主 instrumentation spec（第一个）。

    I 系六个 provider 调用此函数取单个 spec 来定位 UUID_COL / ROWS_TABLE_KEY。
    与 projection_first_publication._primary_instrumentation_spec 语义相同，
    但入参是 (identity, specs) 而非 provider 模块。
    """
    all_specs = instrumentation_specs_for(identity, specs)
    if not all_specs:
        raise HEntrySelectionError(
            f"{identity.entry_id} 无受管 sheet ⇒ 无 instrumentation spec"
        )
    return all_specs[0]


def template_definition_payload(
    identity: HEntryIdentity, specs: Sequence[Any]
) -> dict[str, Any]:
    data = read_authoritative_template(identity)
    if not specs:
        raise HEntrySelectionError(f"{identity.entry_id} 当前无受管 sheet")
    return build_template_payload(
        spec=_instrumentation_of(identity, specs[0]),
        template_sha256=identity.template_sha256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload(
    identity: HEntryIdentity, specs: Sequence[Any]
) -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs_for(identity, specs),
        template_definition_sha256=canonical_digest(
            template_definition_payload(identity, specs)
        ),
        template_sha256=identity.template_sha256,
        gate=excel_carrier_gate(),
    )


def sheets_payload(specs: Sequence[Any]) -> list[dict[str, Any]]:
    """受管 sheet → 契约 `sheets[]`，**一律走框架层引擎的规范产出**。

    🔴 用 `spec_to_contract_sheet_payload(spec)` 而**不是**手写字段循环。
    G2 的 docstring 记了实测教训：照抄 `phase5_f1_prepayment._rows_table_payload()` 的形态
    （`row_identity: {store_key, column, hidden}` + 无 `anchor`）会过不了
    `parse_contract`（`table anchor 必须是 A1 单元格，实得 None`）—— F1 的磁盘契约至今如此。

    按 `sheet_key` 分组：同 sheet 多区（将来 lane 打开双区时）不会产出两个同名 `excel_name`。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    sheets: list[dict[str, Any]] = []
    by_sheet_key: dict[str, dict[str, Any]] = {}
    for spec in specs:
        produced = spec_to_contract_sheet_payload(spec)
        existing = by_sheet_key.get(spec.sheet_key)
        if existing is None:
            by_sheet_key[spec.sheet_key] = produced
            sheets.append(produced)
        else:
            existing["tables"].extend(produced["tables"])
    return sheets


def build_contract_payload(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    *,
    html_store_note: str,
    reviewed_basis: str,
    payload_column: str = "remark",
    payload_column_mode: str = "remark_only",
    payload_column_source: str = "",
) -> dict[str, Any]:
    """装配 per-entry 契约 payload（9 条 H entry 共用这一处）。

    :param payload_column: 🔴 H 循环 9 条实测全部落 `remark`（`conclusion` 或为 null 占位
        或另存文本），与 G2 的 `remark_only` 同族。
    """
    template_payload = template_definition_payload(identity, specs)
    sheets = sheets_payload(specs)
    if not sheets:
        raise HEntrySelectionError(f"{identity.entry_id} 当前无受管 sheet")
    item_ids: list[str] = []
    for spec in specs:
        if spec.store_item_id and spec.store_item_id not in item_ids:
            item_ids.append(spec.store_item_id)

    review: dict[str, Any] = {
        "entry_id": identity.entry_id,
        "pilot_class": identity.phase5_wave,
        "authority_root": H_AUTHORITY_ROOT,
        "html_store": {
            "table": "checklist_responses",
            "item_ids": item_ids,
            "shape": "json_array_of_row_objects",
            "payload_column": payload_column,
            "payload_column_mode": payload_column_mode,
            "payload_column_source": payload_column_source,
            "note": html_store_note,
        },
        "reviewed_basis": reviewed_basis,
        # 🔴 HD-7：`None` 表示该 entry **没有** TB 发布门（H8 / H9 两条缺口）。
        # 写进契约是为了让 roundtrip 判据知道「不覆盖发布链」是**声明**而不是遗漏。
        "tb_publish_gate": identity.tb_publish_gate,
    }
    review.update(dict(identity.extra_review))

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": identity.adapter_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload(identity, specs)
        ),
        "template": {
            "relative_path": identity.template_relative_path,
            "template_sha256": identity.template_sha256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": list(H_PHASE5_IDENTITY_CARRIERS),
        "sheets": sheets,
        "review": review,
    }


def assert_contract_file_matches_source(
    identity: HEntryIdentity, expected: Mapping[str, Any]
) -> SyncContract:
    """磁盘契约与模块现算 payload 双向锁（禁手改磁盘 json）。"""
    on_disk = load_contract(identity.adapter_id)
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise HEntrySelectionError(
            "磁盘 per-entry contract 与 provider 现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 backend/scripts/gen/generate_phase5_h_contracts.py --apply 重生成"
        )
    parse_contract(dict(expected), adapter_id=identity.adapter_id)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# manifest capability / matcher / 注册 / attach
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(
    identity: HEntryIdentity, *, manifest: Mapping[str, Any] | None = None
) -> bool:
    try:
        assert_manifest_capability_enabled(identity, manifest=manifest)
    except HEntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    identity: HEntryIdentity, *, manifest: Mapping[str, Any] | None = None
) -> None:
    """🔴 HC-1：capability 从 `single_onlyoffice` → `bidirectional` **只能**由
    `register_from_manifest()` 在注册成功后驱动，**禁止手改 manifest 文件**
    （手改会造出「manifest 说双向、实际无 adapter」的假绿）。

    本函数是那条禁令的可执行落点：capability 不是 `bidirectional` 就拒绝注册。
    9 条 H entry 当前实测全为 `single_onlyoffice` ⇒ attach 走「返回空元组」分支，
    如实登记为 BP-1~BP-3 平台级供给缺口，而**不是**放宽判据凑注册数。
    """
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    ).get(identity.entry_id)
    if entry is None:
        raise HEntrySelectionError(f"{identity.entry_id} 不在 manifest 里")
    cap = capability_of(entry)
    if cap is not Capability.bidirectional:
        raise HEntrySelectionError(
            f"{identity.entry_id} capability={cap!r}，期望 bidirectional"
        )
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != identity.adapter_id:
        raise HEntrySelectionError(
            f"{identity.entry_id} adapter_id={aid!r} 与本 provider 的 "
            f"{identity.adapter_id!r} 不符"
        )


def build_matcher(
    identity: HEntryIdentity, *, sheet_keys: Sequence[str] = ()
) -> EntryMatcher:
    """matcher 域：幻影码 + `document_type="xlsx"`。

    🔴 `sheet_keys` 留空（= 覆盖该幻影码的全部 sheet）在 H 循环是**安全**的：
    **FC-3 在 H 成立** —— H 按循环整册组织「一 wp_code 一册」，26 个 H 码逐个实跑
    `find_template_file` 候选集合大小恒为 1，不存在 G4/G6 那种「一册三 entry 同码竞争」。
    GC-1 的互斥 `sheet_keys` 只对 G 的 `G4B` / `G6O` 两组是硬要求。
    """
    if sheet_keys:
        return EntryMatcher(
            document_type="xlsx",
            wp_codes=frozenset(identity.wp_codes),
            sheet_keys=frozenset(sheet_keys),
        )
    return EntryMatcher(document_type="xlsx", wp_codes=frozenset(identity.wp_codes))


def build_registration(
    identity: HEntryIdentity,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
    sheet_keys: Sequence[str] = (),
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=identity.entry_id,
        matcher=build_matcher(identity, sheet_keys=sheet_keys),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=(
            contract if contract is not None else load_contract(identity.adapter_id)
        ),
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    identity: HEntryIdentity,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
    sheet_keys: Sequence[str] = (),
) -> AdapterRegistration:
    registration = build_registration(
        identity,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
        sheet_keys=sheet_keys,
    )
    registry.register(registration)
    return registration


# ═══════════════════════════════════════════════════════════════════════════
# definition 发布（approved bundle）—— 本段此前**整段缺失**
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么补这一段（2026-10-01，spec h-cycle-sync-foundation-and-first-canary）：
#
# H 九条的 **attach 侧**（`attach_h_entry_adapter`）一直是完整的，但**publish 侧**在本
# 模块里从来没有过。后果是 `fix_task76_provision_projection_definitions.py`
# —— `ProjectionDefinitionProvisioner` 的唯一消费宿主、也是产出 approved bundle 的唯一
# 入口 —— 经 `projection_provisioning.load_projection_supply()` 只认
# `publish_pilot_definitions` 与 `PILOT_WP_CODES` 两个名字，缺任一即抛
# `ProviderModuleNotAllowedError: provider 是空壳`。
#
# 现算缺口面：台账 51 条里 **只有 12 条**同时具备这两个名字（a51/b60/d1~d7/g7/h1/l1），
# 其余 **39 条**缺（含 H 全部 9 条、G 全部 13 条、I 全部 6 条…）。而该脚本连
# **`--check`（只读）** 都 fail closed 在第一个缺口（实测 `xlsx/gt-e1-monetary-fund`）
# ⇒ 这个诊断入口**平台级跑不完**，H 的供给状况此前根本看不到。
#
# 🔴 实现**不新造口径**：逐行对照 `phase5_entry_orchestration.publish_definitions`
# （D/E/F/L 十二家共用的那份），四段 definition + bundle 的 kind / logical_id /
# semantic_version / slot 结构 / 两条单向引用校验全部一致。差别只有两处，都是 H 侧既有事实：
#   ① payload 由 HC 的 `(identity, specs)` 版函数产出（H 的 payload 函数带参数）；
#   ② `authority_model` 取本模块的 `H_AUTHORITY_MODEL`（值与那十二家相同）。
#
# ⚠️ 本函数**只发布 definition 与 bundle**，不碰 representation / entry pointer ——
# 那是 provisioner 自己的后续阶段。publish 成功 ≠ 该 entry 可注册：注册还要
# published representation（见 `attach_h_entry_adapter` 第③环）。


@dataclass(frozen=True)
class HDefinitions:
    """一次 `publish_definitions_for()` 的产出（字段名与 provisioner 的读取面逐字对齐）。

    🔴 字段名不可改：`projection_provisioning.ProjectionDefinitionProvisioner.ensure()`
    逐个读 `template_definition_id` / `..._sha256` / `instrumentation_*` / `contract_*` /
    `authority_model_*` / `bundle_id` / `bundle_sha256`。改名会在真 provisioning 时才炸。
    """

    entry_id: str
    adapter_id: str
    authority_model_definition_id: Any
    authority_model_definition_sha256: str
    template_definition_id: Any
    template_definition_sha256: str
    instrumentation_definition_id: Any
    instrumentation_definition_sha256: str
    contract_definition_id: Any
    contract_definition_sha256: str
    bundle_id: Any
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "adapter_id": self.adapter_id,
            "authority_model": H_AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "bundle_id": str(self.bundle_id),
            "bundle_sha256": self.bundle_sha256,
        }


def authority_model_payload(identity: HEntryIdentity) -> dict[str, Any]:
    """authority-model definition 的 payload（与十二家已交付逐字同形）。"""
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": H_AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": identity.entry_id,
        "pilot_class": identity.phase5_wave,
    }


async def publish_definitions_for(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    *,
    publisher: Any,
    contract_payload_builder: Any,
) -> HDefinitions:
    """发布该 entry 的四段 definition + approved bundle。

    :param specs: 受管区 spec（必须与 `build_contract_payload` 用的**同一来源**，九条实测
        都是 `managed_row_table_specs()`）—— 否则 template/instrumentation digest 会与契约
        声明不等，下面两条单向引用校验当场打红。
    """
    contract = assert_contract_file_matches_source(identity, contract_payload_builder())
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(identity),
        logical_id=f"{identity.adapter_id}.authority-model",
        semantic_version="1.0.0",
    )
    tp = template_definition_payload(identity, specs)
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=tp,
        logical_id=f"{identity.adapter_id}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(identity),
        structure_hash=tp["normalized_structure_hash"],
    )
    instr = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(identity, specs),
        logical_id=f"{identity.adapter_id}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_def = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=identity.adapter_id,
        semantic_version=contract.semantic_version,
    )
    # 🔴 两条**单向引用**校验：契约里冻结的 digest 必须等于刚发布出来的 digest。
    #    方向是「契约声明 → 已发布」，不是反过来按发布结果改契约。
    if template.sha256 != contract.template_definition_sha256:
        raise HEntrySelectionError(
            f"entry {identity.entry_id}: 已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instr.sha256 != contract.instrumentation_definition_sha256:
        raise HEntrySelectionError(
            f"entry {identity.entry_id}: 已发布 instrumentation digest {instr.sha256} 与契约"
            f"声明 {contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=H_AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instr.definition_id}",
                "digest": instr.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_def.definition_id}",
                "digest": contract_def.sha256,
            },
        },
    )
    return HDefinitions(
        entry_id=identity.entry_id,
        adapter_id=identity.adapter_id,
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instr.definition_id,
        instrumentation_definition_sha256=instr.sha256,
        contract_definition_id=contract_def.definition_id,
        contract_definition_sha256=contract_def.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


# I 系六个 provider 用此名称调用（历史接口名，保留向后兼容）
publish_h_entry_definitions = publish_definitions_for


async def resolve_published_frozen_definitions(
    identity: HEntryIdentity,
    *,
    session: Any,
    representation: Any,
    contract: SyncContract,
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
        correlation_id=f"{identity.adapter_id}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise HEntrySelectionError(
            f"entry {identity.entry_id}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与 provider source-locked 的 {contract.canonical_sha256} 不一致"
        )
    return observation


async def attach_h_entry_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    identity: HEntryIdentity,
    *,
    session: Any,
    contract_payload_builder: Any,
    sheet_keys: Sequence[str] = (),
) -> tuple[str, ...]:
    """发布链编排：attach 一条 H entry 的 adapter（9 条共用）。

    第③环（published representation）缺供给时**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
    """
    if identity.adapter_id in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled(identity):
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
        session, entry_id=identity.entry_id
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
    contract = assert_contract_file_matches_source(identity, contract_payload_builder())
    entry = manifest_entries_by_id(load_entry_manifest())[identity.entry_id]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise HEntrySelectionError(f"entry {identity.entry_id} 的宿主实测不可达")
    observation = await resolve_published_frozen_definitions(
        identity, session=session, representation=representation, contract=contract
    )
    register_adapter(
        registry,
        identity,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
        sheet_keys=sheet_keys,
    )
    return (identity.adapter_id,)


# ═══════════════════════════════════════════════════════════════════════════
# 泛化 store projection / merge / iter（I 循环 6 家委托到这里）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item_for(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    store_item_id: str | None,
) -> Any:
    """在给定 specs 中按 store_item_id 查找对应 spec。未命中即抛。"""
    default_id = specs[0].store_item_id if specs else None
    target = store_item_id or default_id
    for spec in specs:
        if spec.store_item_id == target:
            return spec
    raise HEntrySelectionError(
        f"entry {identity.entry_id}: store item {target!r} 不在受管清单里；"
        f"已受管：{sorted(s.store_item_id for s in specs)}"
    )


def build_store_projection_for(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    payload: Any,
    *,
    contract: Any,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → Projection（泛化版，供 I 循环 6 家委托调用）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )

    spec = _spec_of_store_item_for(identity, specs, store_item_id)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows_for(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    *,
    projection: Any,
    base_rows: list,
    store_item_id: str | None = None,
) -> Any:
    """projection → HTML store 行（泛化版，供 I 循环 6 家委托调用）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    spec = _spec_of_store_item_for(identity, specs, store_item_id)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows_for(
    identity: HEntryIdentity,
    specs: Sequence[Any],
    payload: Any,
    *,
    store_item_id: str | None = None,
) -> Any:
    """流式 (row_identity, row)（泛化版，供 I 循环 6 家委托调用）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item_for(identity, specs, store_item_id)
    return _engine_iter(spec, payload)
