# -*- coding: utf-8 -*-
"""G2 应收利息 —— Phase 5 entry 模块（G 循环首条，从零建）。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 11

═══ 范式裁决 GF-H3：用 `phase5_*` 不照 G7 的 `pilot_*` ═══

G7 是 G 循环**唯一**已注册 adapter 的 entry，但它走 `pilot_g7_two_level_dynamic.py`
（`PILOT_ADAPTER_ID`）—— 那是 Tasks 40~43 四个先导之一，形态早于行表引擎。
照它会写出无法复用引擎的单例代码。本模块按 D/E/F 已验通 10 家的 `phase5_*` 声明式范式
（结构与 `phase5_f1_prepayment.py` / `phase5_d3_prepaid_receipts.py` 同构）。

🔴 唯一**必须**复用 G7 的是 `oo_crash_neutralization_fn`（GC-2）——
那是范式无关的 per-file 缓解件，声明在 `store_item_registry.STORE_MERGE_REGISTRY`。

═══ GC-2：G2 册裸 IF 21 格 ⇒ 必挂中性化 ═══

按生产函数 `neutralize_oo_crash_if_formulas` 现算：`审定表G2-1` 19 格 +
`应收利息坏账准备测算G2-7` 2 格 = **21 格**（受管表 `明细表G2-2` 本身零命中）。
中性化是 **per-file**（整册就地改写 substrate 副本）⇒ 即使受管表干净也必须挂。
BP-4（真 OO 9.4 场景集）未交付前不得以「裸 IF 数少」推断某册不需要。

⚠️ spec RG-4 表里 G2 记的是 **40** —— 那是 `findall` 的**出现次数**不是格数
（一格嵌两层 IF 算两次）。权威口径是格数，见 `evidence/task0-prerequisites.md`。

═══ GC-5：payload 列 = `remark_only`，且带全 slice 唯一的 null 占位子形态 ═══

`useG2Detail.ts` 的写入点是 `{ item_id, conclusion: null, remark: JSON.stringify(rows) }`
⇒ 契约 `review.html_store.payload_column` 指 **`remark`**。
🔴 判 mode 时必须**先剔除字面 null/undefined 占位**再判 —— 不剔会把 G2 误判成
`dual_write`（Task 49 首轮守卫正是这么错的）。真库正向实证：`G2-2-detail-rows`
remark **475 B** / conclusion **0 B**。

═══ FC-9 TB 红线 ═══

G2 已接显式发布门（科目 **1132**、余额口径，`useG2Adjudication.ts` 的 `publishToTb`=3）。
sync 路径对 `trial_balance` 的写次数必须为 **0** —— 本模块不含任何 TB 写入。
🔴 G2 的 TB 键有 legacy 双键（`ITEM_ID_TB='G2-1-tb'` 主 / `ITEM_ID_TB_LEGACY='G2-1-adj-tb-1132'` 回退），
本契约**只声明主键所属的 entry 不含 TB 表** —— 审定表 G2-1 归后置 spec
`g-cycle-adjudication-sheets-coverage`（裁决 GF-H5），legacy 读回退不得删。
"""
from __future__ import annotations

import hashlib
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
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.definitions import DefinitionKind
from app.services.workpaper_sync.definitions import BundleSlot


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件。"""

    error_code = "sync_phase5_g2_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_g2_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_interest_receivable"
ENTRY_ID: Final[str] = "xlsx/gt-g2-interest-receivable"
ADAPTER_ID: Final[str] = "g2.interest_receivable_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2：matcher 域用幻影码、provisioning 用真码）。
#: `G2I` 在 `wp_index` 实测 **0 命中**；真码 `G2` 有活行 —— 裁决见
#: `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的
#: `xlsx/gt-g2-interest-receivable` 条目。
WP_CODES: Final[frozenset[str]] = frozenset({"G2I"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G2 应收利息.xlsx"
#: 逐字取 slice `authoritative_templates`（完整 64 位；99,479 B）
TEMPLATE_SHA256: Final[str] = (
    "c7563e85a3ebffb7f60a5800dca66f76a5baef97e57cd4be4147f484e7decc84"
)

#: canary store item（明细表G2-2，裁决 GF-H1）
STORE_ITEM_ID: Final[str] = "G2-2-detail-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

#: 🔴 GC-5：payload 落 `remark`（`conclusion` 恒为字面 null 占位）。
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
# 3. 选型必要条件（照 D3 同签名：`resolution` 必填、**无关闭开关**）
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
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
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
# 🔴 canary 只放 G2-2 一张；其余全部默认 False（Task 11 要求「除 G2-2 外默认 False」）。
# G2 册 12 个 sheet 的处置见 spec design §canary 受管区：
#   审定表G2-1          → 后置 spec `g-cycle-adjudication-sheets-coverage`（裁决 GF-H5）
#   调整分录汇总G2-4     → FC-6 默认 `single_html`（`G2TabAdjustment.vue` 是 hub）
#   坏账准备明细表G2-3 / 利息测算表G2-5 / 长期未收回款项检查表G2-6 /
#   应收利息坏账准备测算G2-7 / 凭证检查表G2-8 → 归 `g-cycle-single-region-detail-lanes`
#   两张附注披露 / 底稿目录 / 应收利息实质性程序表G2A → 不接

#: canary：明细表G2-2（裁决 GF-H1）
_INCLUDE_G202: Final[bool] = True
#: G2-3 坏账准备明细表
_INCLUDE_G203: Final[bool] = False
#: G2-5 利息测算表
_INCLUDE_G205: Final[bool] = False
#: G2-6 长期未收回款项检查表
_INCLUDE_G206: Final[bool] = False
#: G2-8 凭证检查表（🔴 它是 FC-8 的 OCR 第二写入方所在 sheet —— 纳管前须先处置
#: `G2TabVoucherCheck.vue` 的 `d4/contract-ocr` 写入路径，见 GF-P1 的重裁）
_INCLUDE_G208: Final[bool] = False
#: G2-1 审定表（AdjudicationSheetSpec，已实施）
_INCLUDE_G201: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_G202:
        from app.services.workpaper_sync import phase5_g2_02_detail as _g202

        specs.append(_g202.SPEC_G202)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """G2-1 审定表。"""
    if not _INCLUDE_G201:
        return None
    from app.services.workpaper_sync.phase5_g2_01_adjudication import SPEC_G201
    return SPEC_G201


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称（含审定表）。"""
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
    """本 entry 的全部 instrumentation 声明（**复数** —— 注册路径读的是这个）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("G2 当前无受管 sheet")
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
    "G2 应收利息的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组"
    "（`conclusion` 是字面 null 占位 —— FD-1 的 null 占位子形态，全 slice 仅 G2 一条）。"
    "本契约按 stable field + 行身份 `id` 拆开。"
    "🔴 判 payload mode 时必须先剔除字面 null 占位再判，否则会被误判成 dual_write。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 G/G2 应收利息.xlsx 的 `明细表G2-2`"
    "（单级表头 R9 / 数据 R10-15 / footer R16 合计 / 公式列 E·H·J 共 18 格 / "
    "有效内容列 13 即 A-M、N·O·P 全空 / 0 个 definedName / "
    "数据行恰好 E·H·J 三列 locked）"
    " + 前端 `useG2Detail.ts` 按值 grep（STORAGE_KEY:122 / generateId:145 / "
    "InterestDetailRow 字段键 / 写入点的 conclusion:null 占位）"
)


def _sheets_payload() -> list[dict[str, Any]]:
    """受管 sheet → 契约 `sheets[]`，**一律走框架层引擎的规范产出**。

    🔴 用 `spec_to_contract_sheet_payload(spec)` 而**不是**手写字段循环。理由是实测的：
    本模块初版照抄了 `phase5_f1_prepayment._rows_table_payload()` 的形态
    （`row_identity: {store_key, column, hidden}` + 无 `anchor`），结果
    `assert_contract_file_matches_source()` 里的 `parse_contract` 直接抛

        ContractSchemaError: …tables[…]: table anchor 必须是 A1 单元格，实得 None

    ⇒ 那个形态**过不了契约 schema**。本轮顺带实测四家：D3 ✅ / D1 ✅ /
    **F1 ❌（同一错误）** / E1 ❌（磁盘契约与源不一致，另一回事）。
    F1 的是既存潜伏 bug（属 `f1-sync-coverage-and-first-canary` 作业面），
    已登记在 `evidence/task11-task14-g2-canary.md`。

    引擎产出的形态与 D3 扩容面手写的那份逐字段等价（`anchor` / `header_rows` /
    `row_identity{kind,json_pointer}` / `delete_policy` / `footer_anchor` /
    `formula_mask` / `fields[*]{stable_field_key,json_pointer,column_key,cell,mode,
    value_type,source_ref,header_source_ref,store_item_id,header_text}`），
    且**只有一处**产出者 ⇒ 引擎改了这里跟着改，不会漂。

    按 `sheet_key` 分组（同 D3/E1 手法）：G2 当前只有一张受管表，分组是防御性的 ——
    将来同 sheet 多区（如 G2-8 三区）打开时不会产出两个同名 `excel_name` 条目。
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
        raise EntrySelectionError("G2 当前无受管 sheet")

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
                # 🔴 GC-5：json_pointer 指 remark，**不得**写死成 conclusion 或双写
                "payload_column": PAYLOAD_COLUMN,
                "payload_column_mode": PAYLOAD_COLUMN_MODE,
                "payload_column_source": (
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useG2Detail.ts —— 写入点为 "
                    "{ item_id, conclusion: null, remark: JSON.stringify(rows) }"
                ),
                "null_placeholder_column": "conclusion",
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
            "请用 generate_phase5_g2_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影/合并（**薄转发**框架层，≤3 行）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（不静默跳过）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 G2 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`（薄转发框架层引擎）。

    :param store_item_id: 指定按哪个受管区投影；缺省用 canary（:data:`STORE_ITEM_ID`）。

    🔴 **签名形态是刚性的**：`payload` 必须是**第一个位置参数**、`store_item_id` 走关键字。
    零回归门 `scripts/check/check_sync_provider_golden_digest.py:206` 按
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 本轮实测：
    写成 `(store_item_id, payload, *, contract)` 两位置参的 **F1 / F2** 在该门上直接
    `TypeError: missing 1 required positional argument: 'payload'`；
    D1/D3/D5/D6/D7/E1/F3/F4/F5 九家用单位置参形态，全部通过。
    本模块初版照抄了 F1 的两位置参形态并踩到同一坑，已按 E1 形态改正
    （E1 是其中最完备的：单位置参 + 可选 `store_item_id`，兼容多受管区）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → HTML store 行（薄转发框架层引擎，含幽灵行防护）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
    """流式 `(row_identity, row)`（薄转发框架层引擎）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, payload)


# ═══════════════════════════════════════════════════════════════════════════
# 7. manifest capability 检查
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> bool:
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
    # 🔴 R3 安全补丁（D4/F1 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 `phase5_d3_prepaid_receipts.py:830`）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `G2I` + `document_type="xlsx"`。

    🔴 `sheet_keys` 留空（= 覆盖 `G2I` 的全部 sheet）是**安全的**：`G2I` 只服务
    本 entry 一条（G2 册 1:1），不存在 G4/G6 那种一册三 entry 的同码竞争。
    GC-1 的互斥 `sheet_keys` 只对 `G4B` / `G6O` 两组是硬要求
    —— 见 `test_g_foundation_p5_gc1_pointer_isolation.py`。
    """
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
    if (
        observation.definitions.contract.canonical_sha256
        != contract.canonical_sha256
    ):
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与本模块 source-locked 的 {contract.canonical_sha256} 不一致"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach G2 adapter（照 D3/F1 同构）。

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
    bundle = await resolution.load_bundle_snapshot(
        representation.definition_bundle_id
    )
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
