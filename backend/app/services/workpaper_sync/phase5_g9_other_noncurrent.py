"""G9 其他非流动金融资产 —— Phase 5 entry 模块（`g-cycle-single-region-detail-lanes` 首条）。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5
　　　列模型依据 `evidence/task8-template-design-logic.md`（模板编制思路）

═══ 范式：照 `phase5_g2_interest_receivable`，不照 G7 的 `pilot_*` ═══

G2 是 G 循环第一条走 `phase5_*` 声明式范式的 entry（foundation spec 的 canary）。
本模块与它同构；唯一复用 G7 的是 `oo_crash_neutralization_fn`（GC-2，范式无关的
per-file 缓解件，声明在 `store_item_registry.STORE_MERGE_REGISTRY`）。

═══ 🔴 与已交付十一家的**结构性差异**：一个 store 键、三个受管区 ═══

`明细表G9-2` 有三个受管数据区（R12-16 / R19-23 / R26-28），中间夹着不受管的区标题行
与小计行。前端把三区的行存在**同一个** `G9-detail-rows` 数组里，用 `section` 字段标记
区归属（`useG9Detail.G9_SECTIONS`）。

平台既有多区范式（`phase5_d3_04_analysis`）是「一区一个 `store_item_id`」——那要求前端
拆键。这里**不拆**：`G9-detail-rows` 有真库载荷（605 B）、被 8 个跨表消费方读取、且是
BP-10 登记的键，拆键的波及面远大于在引擎加一层可选过滤。
⇒ sheet 层声明 `row_section_field="section"` + 三段各自的 `row_section_value`
（见 `phase5_g9_02_detail`），本模块的三个 store 门面按「**遍历三段**」组合：

* :func:`build_store_projection` —— 缺省投影**全部三段**并合并成一个 `Projection`
  （生产路径 `store_projection_response.py` / `projection_first_publication.py` 只传
  一份 payload、不带段参数；只投区①就会静默丢掉区②③的行）；
* :func:`merge_projection_into_store_rows` —— 三段**顺序穿线**：上一段的 merged 结果
  作为下一段的 `base_rows`，`applied/visited/touched` 累加。引擎的单段 merge 按 identity
  索引，不属本段的行原样保留，故穿线是安全的；
* :func:`iter_store_rows` —— 缺省串联三段（各段内部按 `section` 过滤）。

三者都接受 `section=` 显式指定单段，供逐段判据使用。

═══ GC-2：G9 册裸 IF 42 格 ⇒ 必挂中性化 ═══

按生产函数 `neutralize_oo_crash_if_formulas` 的口径现算（**格数**，不是 findall 出现
次数）：`审定表G9-1` **42** 格，其余 9 张 sheet 零命中 —— 受管表 `明细表G9-2` 本身干净。
中性化是 **per-file**（整册就地改写 substrate 副本）⇒ 即使受管表干净也必须挂：用户在
同一册里点任一 sheet 的在线编辑都会触发整册加载。BP-4（真 OO 9.4 场景集）未交付前
不得以「受管表干净」推断某册不需要。

═══ FC-2：matcher 用幻影码 `G9O` ═══

manifest 冻结的 `wp_code_patterns` 是 `["G9O"]`，而真库有载荷的 wp_code 是 **`G9`**
（裁决见 `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的
`store_payload_evidence.wp_code_with_payload`）⇒ 幻影码只用于 matcher 域，
provisioning 用真码。`sheet_keys` 留空是安全的：`G9O` 只服务本 entry 一条
（G9 册 1:1，不存在 G4/G6 那种一册三 entry 的同码竞争）。

═══ FC-9 TB 红线 ═══

G9 已接显式发布门（`useG9Adjudication.ts` 的 `publishToTb`）。sync 路径对
`trial_balance` 的写次数必须为 **0** —— 本模块不含任何 TB 写入。
审定表 `审定表G9-1` 归后置 spec `g-cycle-adjudication-sheets-coverage`（裁决 GF-H5）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

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
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.definitions import DefinitionKind
from app.services.workpaper_sync.definitions import BundleSlot


class EntrySelectionError(SyncDomainError):
    """G9 entry 的选型必要条件不再成立。"""

    error_code = "sync_phase5_g9_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_g9_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_other_noncurrent_financial"
ENTRY_ID: Final[str] = "xlsx/gt-g9-other-noncurrent-financial"
ADAPTER_ID: Final[str] = "g9.other_noncurrent_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。真码是 `G9`，见模块 docstring。
WP_CODES: Final[frozenset[str]] = frozenset({"G9O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G9 其他非流动金融资产.xlsx"
#: 逐字取 slice `authoritative_templates.files`（完整 64 位；88,636 B）
TEMPLATE_SHA256: Final[str] = (
    "264322c0ed1b4bf6882687b973377ff0e90bdb5664edb4d7e3752ba39fec2379"
)

#: 受管 store item（明细表G9-2 的三区共用）—— 按值取自 `useG9Detail.ts` 的 `ITEM_ID_ROWS`
STORE_ITEM_ID: Final[str] = "G9-detail-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 🔴 FD-1：payload 落 `remark`（真库实证 remark 605 B / conclusion 0 B）。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
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
# 3. 选型必要条件（照 G2 同签名：`resolution` 必填、**无关闭开关**）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts,
    *,
    wp_codes: frozenset[str],
) -> None:
    """幻影码不得在 finder 里命中真模板（零回退）。"""
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"幻影码 {sorted(leaked)} 在 finder 里意外命中真模板 "
            f"—— 零回退判据要求幻影码不得命中：{leaked}"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """对**真 manifest** 核四条事实 + 零回退（FC-2：不留关闭开关）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r}"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {
        str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()
    }
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} "
            f"与冻结的 {sorted(WP_CODES)} 不一致"
        )
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════
#
# G9 册 10 个 sheet 的处置：
#   明细表G9-2            → 本 spec（三区受管，`_INCLUDE_G902`）
#   审定表G9-1            → 后置 spec `g-cycle-adjudication-sheets-coverage`（GF-H5）
#   公允价值测试表G9-4 / 公允价值层次披露G9-5 → 后续 lane（跨表消费方已按 fallback 链读）
#   其余（披露 / 目录 / 实质性程序表 G9A）  → 不接

#: 明细表G9-2（三区）
_INCLUDE_G902: Final[bool] = True
#: 审定表G9-1（AdjudicationSheetSpec，已实施）
_INCLUDE_G901: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。

    🔴 返回**三条**（同一张 sheet 的三个区），三条共享 `sheet_key` 与 `store_item_id`。
    """
    specs: list[Any] = []
    if _INCLUDE_G902:
        from app.services.workpaper_sync import phase5_g9_02_detail as _g902

        specs.extend(_g902.ALL_SPECS_G902)
    return tuple(specs)


def section_specs() -> tuple[Any, ...]:
    """受管的**分段** spec（`row_section_value` 非空的那些）。

    单独给一个名字是为了让「遍历三段」的调用点读起来是意图而不是巧合 ——
    将来若某段下线，遍历面自动跟着变。
    """
    return tuple(s for s in managed_row_table_specs() if s.row_section_field)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。

    三段共享一个键 ⇒ 去重后长度是 **1**（不是 3）。
    """
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """G9-1 审定表。"""
    if not _INCLUDE_G901:
        return None
    from app.services.workpaper_sync.phase5_g9_01_adjudication import SPEC_G901
    return SPEC_G901


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称（三段同名 ⇒ 去重后 1 张）。"""
    names: list[str] = []
    seen: set[str] = set()
    for s in managed_row_table_specs():
        if s.managed_sheet not in seen:
            names.append(s.managed_sheet)
            seen.add(s.managed_sheet)
    adj = adjudication_spec()
    if adj is not None and adj.managed_sheet not in seen:
        names.append(adj.managed_sheet)
    return tuple(names)


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
    """全部 instrumentation 声明（**三段各一条** —— uuid_col 与行区间逐段不同）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("G9 当前无受管 sheet")
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


# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约装配
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "G9 其他非流动金融资产的明细行存成 checklist_responses 的 **remark** JSON 数组"
    "（真库实证 remark 605 B / conclusion 0 B）。"
    "🔴 三个受管区（其他非流动金融资产 / 划分为FVTPL / 指定为FVTPL）共用**同一个** "
    f"`{STORE_ITEM_ID}` 数组，行的区归属由 `section` 字段表达 —— 契约里对应三条 "
    "`tables[]`（逐段不同 uuid_col 与行区间），但 `html_store.item_ids` 只有一条。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 G/G9 其他非流动金融资产.xlsx 的 `明细表G9-2`"
    "（两级表头 R9 组 / R10 叶子 / 三个受管区 R12-16·R19-23·R26-28 / "
    "区标题行 R11·R18·R25 无公式 / 小计 R17·R24·R29 / 合计 R30 枚举相加 "
    "=SUM(C17,C24,C29) / 12 个公式列 E·H·I·J·L·P·Q·R·U·V·W·Y 共 156 格 / "
    "有效内容列 28 即 A-AB / 0 个 definedName / 受管表零裸 IF)"
    " + 前端 `useG9Detail.ts` 按值 grep（ITEM_ID_ROWS / genId 带随机后缀 / "
    "G9DetailRow 28 字段与模板列序 A..AB 逐列对应 / G9_SECTIONS 三段）"
    " + 模板编制思路见 spec evidence/task8-template-design-logic.md"
    "（CAS22 FVTPL 口径 / 三分量恒等式 成本+累计公允价值变动=公允价值 / "
    "四阶段 未审→账项调整→审定→重分类报表 / P=C+M 与 Q=D+N 走未审线）"
)


def _sheets_payload() -> list[dict[str, Any]]:
    """受管 spec → 契约 `sheets[]`（一律走框架层引擎的规范产出）。

    🔴 按 `sheet_key` 分组是**必需的**（不像 G2 那样只是防御）：三段共享
    `sheet_key="g902-managed"`，不分组会产出三个同 `excel_name` 的 sheet 条目，
    装配时冲突。分组后是「一张 sheet + 三条 tables」。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    sheets: list[dict[str, Any]] = []
    by_sheet_key: dict[str, dict[str, Any]] = {}
    for spec in managed_row_table_specs():
        produced = spec_to_contract_sheet_payload(spec)
        existing = by_sheet_key.get(spec.sheet_key)
        if existing is None:
            by_sheet_key[spec.sheet_key] = produced
            sheets.append(produced)
        else:
            existing["tables"].extend(produced["tables"])

    # 审定表（独立 sheet，不进行表引擎）
    adj = adjudication_spec()
    if adj is not None:
        from app.services.workpaper_sync.phase5_adjudication_sheet import (
            static_sheet_payload_for_adjudication,
        )
        sheets.append(static_sheet_payload_for_adjudication(adj))

    return sheets


def build_contract_payload() -> dict[str, Any]:
    template_payload = template_definition_payload()
    sheets = _sheets_payload()
    if not sheets:
        raise EntrySelectionError("G9 当前无受管 sheet")

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
                "payload_column": PAYLOAD_COLUMN,
                "payload_column_mode": PAYLOAD_COLUMN_MODE,
                "payload_column_source": (
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useG9Detail.ts —— 写入点为 "
                    "debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })"
                ),
                "row_section_field": "section",
                "row_section_values": [
                    s.row_section_value for s in section_specs()
                ],
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
            f"source={canonical_digest(expected)}；"
            "请用 generate_phase5_g9_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影 / 合并（**三段组合**）—— 实现在伴生模块，见文件末尾重导出
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 四个 store 门面（uild_store_projection / merge_projection_into_store_rows /
#    iter_store_rows / split_store_payload_by_section）实现在
#    phase5_g9_store_facade.py，本模块在**文件末尾**重导出，调用方按名取属性时零改动。
#    抽出原因与先例（pilot_h1_store_merge）见伴生模块 docstring。

# ═══════════════════════════════════════════════════════════════════════════
# 7. manifest capability 检查
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
    # 🔴 R3 安全补丁（D4/F1/G2 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 `phase5_g2_interest_receivable`）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `G9O` + `document_type="xlsx"`（`sheet_keys` 留空，见模块头）。"""
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
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
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
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与本模块 source-locked 的 {contract.canonical_sha256} 不一致"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach G9 adapter（照 G2/D3/F1 同构）。

    第③环（published representation）缺供给时**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
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
        raise EntrySelectionError(f"entry {ENTRY_ID} 的宿主实测不可达")
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
# 9. store 门面重导出（伴生模块 `phase5_g9_store_facade`）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 放在**文件末尾**：伴生模块对本模块的引用是函数体内惰性 import，这里正向 import
#    才不会构成循环。重导出使 `getattr(provider, "build_store_projection")` 一类
#    按名取属性的调用点（store_projection_response / projection_first_publication /
#    oo_to_html / 零回归门）零改动。
from app.services.workpaper_sync.phase5_g9_store_facade import (  # noqa: E402
    build_store_projection,
    iter_store_rows,
    merge_projection_into_store_rows,
    specs_for as _specs_for,
    split_store_payload_by_section,
)

__all__ = [
    "ENTRY_ID",
    "ADAPTER_ID",
    "STORE_ITEM_ID",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
    "split_store_payload_by_section",
    "_specs_for",
]

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "entry_id": ENTRY_ID,
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "pilot_class": "phase5",
        "reason": (
            f"{ENTRY_ID}：结构化 Tab（HTML store）与 OnlyOffice 共写同一份权威模板，"
            "投影契约是唯一权威 —— 与 D1~D7 / E1 / F3~F5 同型"
        ),
    }


@dataclass(frozen=True)
class Phase5Definitions:
    """发布结果（与 F3/F4/F5/H 系各家同形）。"""
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
    """发布五个 definition + bundle（照 F3/D3 范式）。"""
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
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
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


publish_pilot_definitions = publish_definitions
