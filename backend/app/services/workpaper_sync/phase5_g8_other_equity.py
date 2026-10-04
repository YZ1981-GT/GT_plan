"""G8 其他权益工具投资 —— Phase 5 entry 模块（`g-cycle-single-region-detail-lanes` 第三条）。

spec: `g-cycle-single-region-detail-lanes` · Task 9b / C-8
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §3 + 本轮逐格实测

═══ 范式：照 `phase5_g10_trading_liabilities`（**单区薄转发**）═══

G8 与 G10 几何同族（两级表头 R9/R10 + 单个受管区 R11-R20 + footer R21）⇒ 三个 store
门面各自 ≤3 行薄转发框架层引擎，不需要 G9 那样的「遍历三段」伴生模块。
本模块的机械段（选型 / instrumentation / 契约装配 / 注册）与 G10 逐字同形，
差异全部集中在下面三条 G8 专属事实上。

═══ 🔴 一：G8 是 FVOCI，OCI 三列是准则要求，**与 G9/G10 反向** ═══

受管表内注释逐字：「在初始确认时，企业可以将非交易性权益工具投资**指定为以公允价值计量
且其变动计入其他综合收益**的金融资产。该指定一经作出，**不得撤销**。」
⇒ 模板的三个 OCI 列（`F` 期初累计 / `L` 本期转留存 / `R` 期末累计）是 CAS22 要求的。

G9/G10 的前端根治**删掉**了 OCI/减值四列，依据是「那两张表五类全 FVTPL，CAS22 下不确认
OCI 与减值」。这条依据对 G8 **反向**成立 —— 照抄 G9/G10 的移除清单会把准则要求的列删掉。
同理 G6（其他债权投资）也是 FVOCI 口径。C-6 evidence §12 把这条列为「与 G9 相比要
**反向**注意的四条」之首。

═══ 🔴 二：模板四处行级缺陷 ⇒ 两个机制**分开取值** ═══

逐行实测 R11-R20（`M` 本期变动合计 / `P` 期末累计FV变动 / `R` 期末OCI累计 / `T` 审定数）：

* **R11**：`M=SUM(I:L)` ✅含 L · `P=D+J` ❌漏 K · `R` ✅ · `T` ✅
* **R12**：`M=SUM(I:K)` ❌漏 L · `P=D+J+K` ✅含 K · `R` ✅ · `T` ❌**整格无公式**
* **R13..R20**：`M=SUM(I:K)` ❌漏 L · `P=D+J` ❌漏 K · `R` ❌**整格无公式** · `T` ✅

会计判读：`M` 应含 L · `P` 应含 K · `R`(=F+J+L) 与 `T`(=Q+S) 都是恒等式、每行都该有。
即 R11 与 R12 各对一半、R13-R20 两处都漏。与 G5「三段合计各漏加一个小计」同族。

处置（详见 `phase5_g8_02_detail` 模块头）：
* `formula_columns` 只取模板**逐行完全一致**的 `E·H·O·Q` 四列 —— 它驱动 verify 的区间
  比对，放进 `M`/`P` 会在 R11/R12 上必红；
* `M`/`P`/`R`/`T` 的 `mode` 仍判 **formula**（`contracts.PROTECTED_MODES`，store 侧保护），
  由前端 `useG8Detail.enrichG8DetailRow` 按**会计正确**口径统一重算。
两个机制在引擎里互不校验、语义也不同（verify 区间 vs store 投影），分开取值是正解。

🔴 **裁决 G1R-H3 的原措辞（「拆两个 spec + 并集取 formula、交集取 editable」）需修正**：
① 按并集会把 R13 的 `R` 与 R12 的 `T` 标成 formula —— 正是判据 P12 要求证明**不发生**的
误标；② 三段无法用引擎表达 —— 引擎只支持 `row_section_field`（按**字段值**过滤），而 G8
是连续 R11-R20 里逐行公式不同，前端数组没有也不该有区归属字段（行的物理位置不是业务
属性，那会变成 BP-11 语义耦合行身份的同族问题）；③ P12 的前提「那两格留给用户手填」
也不成立 —— 前端改造前后都把 `T` 当公式算，`R` 是恒等式没有手填空间。

═══ 🔴 三：GC-2 裸 IF 12 格 ═══

按生产函数 `neutralize_oo_crash_if_formulas` 的口径现算（**格数**）：`审定表G8-1` **12**
格（全 G 循环最少），其余 10 张 sheet 零命中 —— 受管表 `明细表G8-2` 本身干净。
中性化是 per-file ⇒ 仍必须挂（点同册任一 sheet 的在线编辑都会触发整册加载）。

═══ FC-2 / FC-9 ═══

manifest 冻结的 `wp_code_patterns` 是 `["G8O"]`（幻影码），真库有载荷的 wp_code 是 **`G8`**
（裁决逐字见 `workpaper_sync_entry_wp_code_adjudication.json`，该节点 `contract_id` 就是
本模块的 `ADAPTER_ID`）⇒ 幻影码只用于 matcher 域，provisioning 用真码。
G8 已接显式发布门（`useG8Adjudication` 的 `publishToTb`），本模块对 `trial_balance`
写次数为 **0**；审定表归后置 spec `g-cycle-adjudication-sheets-coverage`（GF-H5）。
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
    """G8 entry 的选型必要条件不再成立。"""

    error_code = "sync_phase5_g8_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_g8_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_other_equity_instruments"
ENTRY_ID: Final[str] = "xlsx/gt-g8-other-equity-instruments"
ADAPTER_ID: Final[str] = "g8.other_equity_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。真码是 `G8`，见模块 docstring。
WP_CODES: Final[frozenset[str]] = frozenset({"G8O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G8 其他权益工具投资.xlsx"
#: 逐字取 slice `authoritative_templates.files`（完整 64 位；99,458 B）
TEMPLATE_SHA256: Final[str] = (
    "5c8d3de7ee60ffef8677768c6c3966a313d4210ebc96b19a12c56721954b83b6"
)

#: 受管 store item —— 按值取自 `useG8Detail.ts` 的 `ITEM_ID_ROWS`
STORE_ITEM_ID: Final[str] = "G8-detail-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 🔴 FD-1：payload 落 `remark`（真库实证 remark 2 B / conclusion 0 B）。
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
# 3. 选型必要条件（照 G2/G9 同签名：`resolution` 必填、**无关闭开关**）
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
# G8 册 11 个 sheet 的处置：
#   明细表G8-2            → 本 spec（单区受管，`_INCLUDE_G802`）
#   审定表G8-1            → 后置 spec `g-cycle-adjudication-sheets-coverage`（GF-H5）
#   公允价值测试表G8-4    → 后续 lane（C-8 已把层次 / 估值方法 / 持股数 / 每股公允价值
#                           五列的权威源收敛到这张表，并停用了 `pushG8FvToDetail`）
#   指定的适当性检查表G8-5 → 后续 lane（G8-4 → G8-5 的层次同步方向是对的，未动）
#   其余（目录 / 附注披露 ×2 / 调整分录 G8-3 / 凭证检查 G8-6 / 程序表 G8A /
#        参考中证协《非上市公司股权估值指引》）→ 不接

#: 明细表G8-2（单区 R11-R20）
_INCLUDE_G802: Final[bool] = True
#: 审定表G8-1（AdjudicationSheetSpec，归后置 spec）
_INCLUDE_G801: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_G802:
        from app.services.workpaper_sync import phase5_g8_02_detail as _g802

        specs.append(_g802.SPEC_G802)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """G8-1 审定表 —— 归后置 spec，本 spec 恒 None（GF-H5）。"""
    if not _INCLUDE_G801:
        return None
    raise EntrySelectionError(
        "G8-1 审定表归后置 spec `g-cycle-adjudication-sheets-coverage`（裁决 GF-H5）；"
        "本 spec 不交付其 AdjudicationSheetSpec"
    )


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称。"""
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
    """全部 instrumentation 声明（G8 单区 ⇒ **一条**）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("G8 当前无受管 sheet")
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
    "G8 其他权益工具投资（**FVOCI**）的明细行存成 checklist_responses 的 **remark** "
    "JSON 数组（真库实证 remark 2 B 即空数组 / conclusion 0 B —— 本条**没有**真实行数据，"
    "roundtrip 判据一律用合成行）。"
    f"单个受管区 R11-R20 ⇒ 契约里一条 `tables[]`、`html_store.item_ids` 一条 "
    f"`{STORE_ITEM_ID}`。"
    "🔴 另有 `G8-adj-tb-writeback`（真库 40 B）是 RG-10 模板化拼接键 —— 在前端源码按"
    "**字面量** grep 零命中，普查必须按值匹配；它不属本 sheet 的受管面。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 G/G8 其他权益工具投资.xlsx 的 `明细表G8-2`"
    "（两级表头 R9 组 / R10 叶子 / R9 横向合并区恰三个 C9:F9·I9:N9·O9:R9 / "
    "单个受管区 R11-R20 / footer R21 逐列 =SUM(x11:x20) / "
    "有效内容列 23 即 A-W 且 X 空 / max_column=24 含空列 / 0 个 definedName / "
    "受管表零裸 IF，整册 12 格裸 IF 全在 审定表G8-1 / "
    "🔴 模板**四处行级缺陷**：M 在 R12-R20 漏加 L、P 在 R11+R13-R20 漏加 K、"
    "R 在 R13-R20 整格无公式、T 在 R12 整格无公式 ⇒ formula_columns 只取逐行一致的 "
    "E·H·O·Q 四列，M/P/R/T 的 mode 仍判 formula 由前端按会计正确口径算)"
    " + 前端 `useG8Detail.ts` 按值 grep（ITEM_ID_ROWS / genId 带随机后缀 / "
    "G8DetailRow 23 字段与模板列序 A..W 逐列对应 / 无 section 字段即单区）"
    " + 模板编制思路见 spec evidence/task8-c6-remaining-eight-template-logic.md §3"
    "（🔴 **FVOCI** 口径：受管表注释逐字「指定为以公允价值计量且其变动计入其他综合收益……"
    "该指定一经作出不得撤销」⇒ OCI 三列 F/L/R 是 CAS22 要求的，与 G9/G10 的「删 OCI」"
    "**反向** / 本期变动的成本 I 是净额列 / 股利收入 N 是损益项不进余额 / O=C+I 走未审线）"
)


def _sheets_payload() -> list[dict[str, Any]]:
    """受管 spec → 契约 `sheets[]`（一律走框架层引擎的规范产出）。

    按 `sheet_key` 分组是防御性的（G8 单区 ⇒ 实际只有一组）：将来若在同一张 sheet 上
    加第二个受管区，这里自动合成「一张 sheet + 多条 tables」而不是产出两个同
    `excel_name` 的条目（G9 三区就是这么组合的）。
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
    return sheets


def build_contract_payload() -> dict[str, Any]:
    template_payload = template_definition_payload()
    sheets = _sheets_payload()
    if not sheets:
        raise EntrySelectionError("G8 当前无受管 sheet")

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
                    "useG8Detail.ts —— 写入点为 "
                    "debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })"
                ),
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
            "请用 generate_phase5_g8_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影/合并（**薄转发**框架层，≤3 行 —— 单区，不需伴生模块）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（不静默跳过）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 G8 受管清单里；"
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

    :param store_item_id: 指定按哪个受管区投影；缺省用 :data:`STORE_ITEM_ID`。

    🔴 **签名形态是刚性的**：`payload` 必须是**第一个位置参数**、其余走关键字。零回归门
    `scripts/check/check_sync_provider_golden_digest.py` 按
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 写成
    `(store_item_id, payload, *, contract)` 两位置参的 F1/F2 在该门上直接
    `TypeError`（G2 初版照抄 F1 也踩过）。
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
    # 🔴 R3 安全补丁（D4/F1/G2/G9/G10 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    #    （本行注释里的 G10 是**先例清单**，不是 G8 自己的码）
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 `phase5_g2_interest_receivable`）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `G8O` + `document_type="xlsx"`（`sheet_keys` 留空，见模块头）。"""
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
    """发布链编排：attach G8 adapter（照 G2/G9/G10 同构）。

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


__all__ = [
    "ENTRY_ID",
    "ADAPTER_ID",
    "STORE_ITEM_ID",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
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
