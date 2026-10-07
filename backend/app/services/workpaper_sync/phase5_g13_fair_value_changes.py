"""G13 公允价值变动收益 —— Phase 5 entry 模块（`g-cycle-single-region-detail-lanes` 第六条）。

spec: `g-cycle-single-region-detail-lanes` · Task 12 / C-11
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §7 + 本轮逐格实测

═══ 范式：照 `phase5_g11_investment_income`（单区薄转发）═══

本模块与 G11/G14 逐字同形，差异集中在下面五条。

🔴 **一：受管载体是「分类骨架」不是工具明细**（用户拍板选项 A）。模板 `明细表G13-2` 的
R11-R20 是**固定 10 个损益表项目**（交易性金融资产 / 其中：指定… / 衍生金融资产 / … /
以公允价值计量的投资性房地产 / 其他），而前端 `G13-detail-rows` 存的是动态增删的**金融
工具级明细**（`instrumentName` 用户自填）⇒ 两侧行模型不同构，按序映射会把第 N 条工具写进
第 N 个损益项目行（**产出错数**）。前端原有 `buildG13CategorySkeleton()` 已按 10 个固定
项目汇总出骨架（`g13Constants.G13_ADJUDICATION_ITEMS` 的 `rowKey`/`kind`/`indent` 与模板
R11-R20 逐行对应），但它只是 `computed`、**不落库** ⇒ 双向回写没有载体。本轮把它持久化成
独立 store item **`G13-detail-skeleton`**（前端 `g13SkeletonStore.ts`），受管它；工具明细
`G13-detail-rows` 保持 HTML-only 平台增强。
⇒ :data:`STORE_ITEM_ID` 因此**不是** `G13-detail-rows` —— 照抄别家「store item = 前端主
rows 键」会接错载体。

🔴 **二：手工覆盖优先**。骨架值默认来自工具明细汇总；OO 侧改动回流后若被汇总无条件重算，
等于回流无效 ⇒ 落库行带 `manualOverride`，有标记的行用存库值，`resetSkeletonRow()` 退回
汇总口径。覆盖行的公式列（`D=B+C` / `I=F+H` / `J=G`）按模板口径重算，避免 UI 出现
「未审+调整 ≠ 审定」这种自相矛盾的数。

🔴 **三：`B`/`C` 判 `editable` 不判 `formula`**。两列在数据区只有 **3 格**有公式（父行
R11/R14/R17 汇总子行：`=B12+B13` / `=B15+B16` / **`=B18`**），其余 7 格是空可填格。
框架层 `mode` 是**列级**的 ⇒ 判 `formula` 会对 7 个无公式格抛、判 `auto_source` 会对 3 个
公式格抛、拆多 spec 因父行 `{11,14,17}` **非连续**要 7 份（footer 还只有一行）⇒ 只能
`editable`（代价：父行三格的模板公式在 materialize 后变成字面量）。三格是**普通公式、
不是 shared 主格** ⇒ 不撞 `SharedFormulaMasterWriteError`。完整论证与被否方案见
:mod:`app.services.workpaper_sync.phase5_g13_02_detail` 模块头「二」。
⇒ 🔴 这推翻 tasks.md Task 12 原写的 `formula_columns=("B","C","D","I","J","K")`。

🔴 **四：受管 sheet 零裸 IF**。整册 11 格全在别的 sheet，`明细表G13-2` 命中 **0 格** ⇒
中性化不动本表（与 G9/G10/G8/G14 同族、与 G11 的 44 格相反）⇒ `D`/`I`/`J`/`K` 四列判
`formula` 成立。GC-2 要求的 per-file 中性化照挂（不因本表零命中而省掉）。

🔴 **五：footer R21 三种约定混行** —— 枚举相加 3 格（`B21=B11+B14+B17+B19+B20`，加的是五个
**顶层**行）+ 纯 SUM 2 格（`I21`/`J21`）+ 布尔 1 格（`K21=J21=D21`，裁决 G1R-H4 的第二个
位点）⇒ `footer_carries_total_formula=True` 成立，但 roundtrip 判据**不得**假设 footer
全列同形态（同 I2-2/I3-2 的 `row_formula_applied` 教训）。

wp_code 裁决：manifest 幻影码 `G13F`（matcher 域），真码 **G13**（载荷所在）。
TB 口径：G13 是损益类（科目 **6101**）—— 不是余额。FC-9 红线 = 本 provider 对
`trial_balance` 写次数为 0；审定表 G13-1 归后置 spec `g-cycle-adjudication-sheets-coverage`
（GF-H5）。
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
    """G13 entry 的选型必要条件不再成立。"""

    error_code = "sync_phase5_g13_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_g13_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_fair_value_changes_detail"
ENTRY_ID: Final[str] = "xlsx/gt-g13-fair-value-changes"
ADAPTER_ID: Final[str] = "g13.fair_value_changes_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。真码是 `G13`，见模块 docstring。
WP_CODES: Final[frozenset[str]] = frozenset({"G13F"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G13 公允价值变动收益.xlsx"
#: 逐字取 slice `authoritative_templates.files`（完整 64 位；实测 58,717 B）
TEMPLATE_SHA256: Final[str] = (
    "fd5e5e9eeca7b392d59ca54beac51e96bb1575894113c0f3e69f05a234b0f099"
)

#: 受管 store item —— 按值取自 `useG13Detail.ts` 的 `ITEM_ID_SKELETON`
STORE_ITEM_ID: Final[str] = "G13-detail-skeleton"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowKey"

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
# G13 册 10 个 sheet 的处置：
#   明细分析表G13-2        → 本 spec（单区 R10-R30，`_INCLUDE_G1302`）
#   审定表G13-1            → 后置 spec `g-cycle-adjudication-sheets-coverage`（GF-H5）
#   调整分录汇总G13-3      → 后续 lane（真库 G13-adj-rows 有 2480 B 真实载荷，是本册最重的键）
#   收益率分析表G13-4      → 后续 lane（自带 32 格裸 IF）
#   凭证检查表G13-5        → 后续 lane
#   其余（目录 / 附注披露 ×2 / 程序表G13A ×2 含「-修订前」）→ 不接

#: 明细分析表G13-2（单区 R11-R20）
_INCLUDE_G1302: Final[bool] = True
#: 审定表G13-1（AdjudicationSheetSpec，已实施）
_INCLUDE_G1301: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_G1302:
        from app.services.workpaper_sync import phase5_g13_02_detail as _g1302

        specs.append(_g1302.SPEC_G1302)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """G13-1 审定表。"""
    if not _INCLUDE_G1301:
        return None
    from app.services.workpaper_sync.phase5_g13_01_adjudication import SPEC_G1301
    return SPEC_G1301


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
    """全部 instrumentation 声明（G13 单区 ⇒ **一条**）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("G13 当前无受管 sheet")
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
    "G13-2 的受管行存成 checklist_responses 的 **remark** JSON 数组（FD-1）。"
    f"🔴 item_id 是 **`{STORE_ITEM_ID}`**（分类骨架，落库形态见前端 `g13SkeletonStore.ts`）"
    "而**不是**工具明细键 `G13-detail-rows` —— 后者存动态增删的金融工具级明细，"
    "与模板的固定 10 个损益表项目不同构，本轮保持 HTML-only 平台增强、不受管。"
    "真库实证两键 remark 均 2 B（空数组）/ conclusion 0 B ⇒ roundtrip 判据一律用合成行；"
    "同册 `G13-disclosure-listed`(940 B) / `G13-disclosure-soe`(661 B) 有真实载荷，"
    "但那属附注披露 sheet、不在本 sheet 受管面。"
    "固定 10 行 R11-R20 ⇒ 契约里一条 `tables[]`、`html_store.item_ids` 一条 "
    f"`{STORE_ITEM_ID}`。"
    "🔴 行身份键是 **`rowKey`**（业务键，同 G14）—— 按值取自 "
    "`g13SkeletonStore.G13_SKELETON_ROW_KEYS`（其单一真源是 "
    "`g13Constants.G13_ADJUDICATION_ITEMS`），**不是**工具明细的 `rowId`。"
    "🔴 骨架落库行带 `manualOverride` 控制位：有标记的行用存库值、不被工具明细汇总重算"
    "冲掉（否则 OO 回流会被立刻覆盖 = 回流无效）；它不是模板列，不受管。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl + sheet XML 逐格实测 G/G13 公允价值变动收益.xlsx 的 `明细表G13-2`"
    "（两级表头 R9/R10：横向组 `B9:D9` 本期数 · **`F9:J9`** 对应科目-公允价值变动"
    "（🔴 含 J 列，而 J10=「计入损益」语义上不属该组 —— evidence §7.1 写作 F9:I10 不准确）；"
    "纵向合并 A9:A10 / E9:E10 / K9:K10 / L9:L10 / "
    "数据区 R11-R20 是**固定 10 个损益表项目**（三层父子：父行 R11/R14/R17 · 子行 "
    "R12/R13/R15/R16/R18 · 无子行的顶层行 R19/R20）/ "
    "footer R21 **三种约定混行**（枚举相加 B/C/D 加的是五个顶层行 + 纯 SUM I/J + "
    "🔴 布尔 K21=J21=D21）/ 有效内容列 12 即 A-L **恰等于 max_column**（无空尾列）/ "
    "0 个 definedName / "
    "🔴 **受管表零裸 IF**（整册 11 格全在别的 sheet）⇒ 中性化不动本表，与 G9/G10/G8/G14 "
    "同族、与 G11 的 44 格相反 / "
    "🔴 B/C 只有 **3 格**有公式（父行汇总，逐行不同形：=B12+B13 / =B15+B16 / **=B18** 单子行）"
    "且是**普通公式、不是 shared 主格** ⇒ 判 `editable`（列级 mode 对「3 行公式 + 7 行空」"
    "无解，拆多 spec 因父行非连续要 7 份）/ "
    "D/I/J/K 的 shared 主格在 **R12** 不在 R11，两者逐行同形 ⇒ 四列都进 formula_templates)"
    " + 前端 `useG13Detail.ts` / `g13SkeletonStore.ts` / "
    "`g13Constants.G13_ADJUDICATION_ITEMS` 按值 grep"
    "（ITEM_ID_SKELETON / 行身份键 **rowKey** / 10 项固定行集的 rowKey·label·kind·indent "
    "与模板 R11-R20 逐行对应 —— 这推翻 Task 2「发现 I：前端无骨架无父子字段」）"
    " + 真库 checklist_responses 实测（`G13-detail-rows` 与 "
    f"`{STORE_ITEM_ID}` 均 2 B 空数组 ⇒ 骨架落库零存量迁移风险）"
    " + 模板编制思路见 spec evidence/task8-c6-remaining-eight-template-logic.md §7"
    "（与 G14 同一张骨架，差别只在明细块：G14 是准备金滚动、G13 是公允价值三分量 / "
    "TB 口径是**本期发生额**，科目 6101 损益类）"
)


def _sheets_payload() -> list[dict[str, Any]]:
    """受管 spec → 契约 `sheets[]`（一律走框架层引擎的规范产出）。

    按 `sheet_key` 分组是防御性的（G13 单区 ⇒ 实际只有一组）：将来若在同一张 sheet 上
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
        raise EntrySelectionError("G13 当前无受管 sheet")

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
                    "useG13Detail.ts —— 写入点为 "
                    "debouncedSave(ITEM_ID_SKELETON, { remark: JSON.stringify(list) })"
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
            "请用 generate_phase5_g13_contract.py --apply 重生成"
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
        f"store item {store_item_id!r} 不在 G13 受管清单里；"
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
    # 🔴 R3 安全补丁（D4/F1/G2/G9/G10/G8/G14 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    #    （本行注释里的码是**先例清单**，不是 G13 自己的码）
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 `phase5_g2_interest_receivable`）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `G13I` + `document_type="xlsx"`（`sheet_keys` 留空，见模块头）。"""
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
    """发布链编排：attach G13 adapter（照 G2/G9/G10/G8/G14 同构）。

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
