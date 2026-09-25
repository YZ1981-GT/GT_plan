# -*- coding: utf-8 -*-
"""E1 货币资金 —— 循环层 entry（第一册 16 sheet 的受管清单与选型守卫）。

spec: e1-sync-coverage-and-first-canary · Task 7 · Requirements 1.2
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ E1 与 D 循环的唯一结构差异（spec 复盘修正）═══

D 循环 slice 实测：7 个独立 entry 里只有 D2/D4 真注册了 adapter，D1/D3/D5/D6/D7 均
`legacy_fake_bidirectional` + `adapter_id=None`（`unverifiable_reasons` 含
`no_registered_sync_adapter`），**与 E1 同态**。真实差异只有**provider 文件存在与否** ⇒
本模块就是在补这一步；其后的契约发布链五环 + adapter 注册是**六个循环共同的平台级缺口**
（umbrella BP-61-1：`working_paper_sync_entry_state` / `working_paper_content_version` /
`working_paper_content_representation` 三表近空，186 个 planned entry 一个都注册不上）。

═══ 🔴 只覆盖第一册（裁决 H2）═══

E1 是 **5 册模板**（实测）：

  1. `E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx`  ← **本 entry 覆盖这一册**（16 sheet）
  2. `E1-14至E1-15  货币资金 -分析程序（…）.xlsx`（4 sheet，含残留 `货币资金分析表F1-6 (修订前)`）
  3. `E1-18至E1-23  货币资金 -检查（…）.xlsx`
  4. `E1-26至E1-32  货币资金-IPO 上市 新三板 重组 舞弊…xlsx`
  5. `E0 货币资金 - 函证（…）.xlsx`

entry ↔ template blob 是 1:1（`_entry_id` 从宿主文件派生 + 碰撞检查 ⇒ 一宿主恰一 entry）
⇒ 后四册需新建宿主另立 entry。**「一循环一 entry」对 E1 须读作「一册一 entry」**
（与 D2 三册同理）。

⇒ 由此，E1-1 审定表的跨册取数键 `E1-accrued-interest-rows`（属**第 3 册**）在本 entry 范围外，
   必须定义「第 3 册未受管」时的降级行为，**不得**因缺失把该格判成空或 0（spec 需求 4.5）。

═══ 第一册 16 sheet 的形态清单（实测公式数 + 前端三元组）═══

| # | sheet | 几何 | 公式 | 形态裁决 |
|---|---|---|---|---|
| 0 | 底稿目录 | 21r×7c | 0 | 导航，不受管 |
| 1 | 货币资金实质性程序表E1A | 44r×11c | 7 | 程序表，不受管 |
| 2 | 附注披露信息(上市公司) | 62r×10c | 153 | 披露，范围外 |
| 3 | 附注披露信息(国企) | 62r×10c | 158 | 披露，范围外 |
| 4 | 货币资金审定表E1-1 | 47r×10c | **193** | `AdjudicationSheetSpec`（槽位驱动，阶段 6） |
| 5 | 现金明细表E1-2 | 34r×22c | 38 | **canary**（动态行表）✅ 已声明 |
| 6 | 银行存款…(仅人民币)E1-3 | 92r×28c | 185 | variant 风险，阶段 5 裁决 |
| 7 | 银行存款…(人民币及外币)E1-3 | 89r×**41c** | **567** | 同上（全平台单 sheet 公式最多） |
| 8 | 数字货币明细表E1-4 | 22r×17c | 52 | 动态行表 ✅ 已声明 |
| 9 | 调整分录汇总E1-5 | 26r×10c | 7 | 第八张同型，倾向 `single_html`（阶段 7 核） |
| 10 | 银行存款余额调节表E1-6 | 56r×17c | 14 | 动态行表（阶段 3） |
| 11 | 库存现金（人民币）盘点表E1-7 | 67r×9c | 27 | 共享 `useE1CashCount`（variant=rmb） |
| 12 | 库存现金（外币）盘点表E1-8 | 78r×12c | 48 | 同上（variant=fx） |
| 13 | 银行存单盘点表E1-9 | 34r×15c | **7** | 🔴 动态行表（**不是** static_region） |
| 14 | 已开立银行账户清单核对表E1-10 | 37r×12c | **7** | 🔴 动态行表（**不是** static_region） |
| 15 | 银行账户情况承诺E1-11 | 31r×7c | **7** | **唯一 `static_region`** ✅ 已声明 |

🔴 三张各 7 公式 —— spec 首版据此把它们全判 `static_region`（裁决 H3），实证只有 E1-11 成立
   （零 `-rows` 键）。**形态判据是前端三元组，不是模板公式数**（裁决 H8）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.entry_profile import (
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
)
from app.services.workpaper_sync.models import AuthorityModel, SyncDomainError

__all__ = [
    "ENTRY_ID",
    "ADAPTER_ID",
    "WP_CODES",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "EntrySelectionError",
    "assert_entry_selectable",
    "managed_row_table_specs",
    "instrumentation_specs",
    "all_store_item_ids",
    "CROSS_VOLUME_KEYS",
]


class EntrySelectionError(SyncDomainError):
    """E1 entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_e1_selection_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest slice / 模板字节实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_monetary_fund"

#: 从 E 循环 manifest slice 冻结（`backend/data/workpaper_sync_e_cycle_manifest_slice.json`
#: 的 independent_entries[0]，实测 migration_state=legacy_fake_bidirectional / adapter_id=None）。
ENTRY_ID: Final[str] = "xlsx/gt-e1-monetary-fund"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
ADAPTER_ID: Final[str] = "e1.monetary_fund_detail"

#: 🔴 **待核**：manifest 的 `wp_match.wp_code_patterns`。`assert_entry_selectable` 从真 manifest
#:    读并与本常量比对；照 D3/D5/D6/D7 的裁决范式，模块 WP_CODES 用 manifest 冻结值，
#:    provisioner JOIN wp_index 用 adjudication 的裁决值（二者可不同，见 D3 provider docstring）。
WP_CODES: Final[frozenset[str]] = frozenset({"E1"})

#: slice 实测的 profile（与 D1/D2/D3 同型 ⇒ required scenario set 是 shared+editable 标准集）。
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"

#: 第一册权威模板（5 册里的第 1 册，16 sheet）。
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx"
)

#: 权威模板字节哨兵（实测，`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "8317e2bac2e57a70778755923332450bd07634e1ff68eb8c14e74d259e58a9ea"
)

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 🔴 跨册取数键（E1-1 审定表会读它，但它属**第 3 册**，本 entry 范围外）。
#:    须定义「第 3 册未受管」时的降级行为：**不得**因缺失把该格判成空或 0（需求 4.5）。
CROSS_VOLUME_KEYS: Final[Mapping[str, str]] = {
    "E1-accrued-interest-rows": (
        "属第 3 册（E1-18至E1-23 检查册）；E1-1 审定表读它做应计利息槽位。"
        "本 entry 只覆盖第一册 ⇒ 该键在本 entry 内**永远读不到** ⇒ 对应审定格必须"
        "显式标记为「上游未受管」而非空/0，否则审计师会以为该项真为零"
    ),
}


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
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（真 manifest；四条事实里前三条由 slice 核对供给）
# ═══════════════════════════════════════════════════════════════════════════


def assert_entry_selectable(
    *, manifest: Mapping[str, Any] | None = None, require_wp_codes: bool = True
) -> Mapping[str, Any]:
    """在**真实** manifest 上核选型必要条件；任一不成立即抛。

    :param require_wp_codes: 第四条事实（wp_code 落点）待核期间可置 False —— 但**必须**
        在接入前置真并过一次（spec Task 7 明令「待核第四条」）。默认 True 使遗漏必红。
    """
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 document_type={entry.get('document_type')!r} 非 xlsx"
        )
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 independent_entry={entry.get('independent_entry')!r} —— "
            "重复入口不得注册 adapter"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    if require_wp_codes:
        codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
        if codes != set(WP_CODES):
            raise EntrySelectionError(
                f"{ENTRY_ID!r} 的 wp_code_patterns={sorted(codes)} 与冻结的 matcher 域 "
                f"{sorted(WP_CODES)} 不一致 —— matcher 必须覆盖该 entry 的全部 wp_code"
            )
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 受管 sheet 清单（灰度开关逐张接入，照 D4/D1 的 `_INCLUDE_*` 模式）
# ═══════════════════════════════════════════════════════════════════════════

#: canary：E1-2 现金明细（零 OCR / 零跨 sheet / 键独立，第一册失败面最小的行表）。
_INCLUDE_E102_CASH_DETAIL: Final[bool] = False

#: 第二张：E1-4 数字货币（验证「复用框架层零改动」）。
_INCLUDE_E104_DIGITAL: Final[bool] = False

#: 唯一 static_region：E1-11 银行账户情况承诺（绕开整条位移链）。
_INCLUDE_E111_COMMITMENT_STATIC: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的**行表型** spec 清单（按灰度开关，顺序稳定）。"""
    specs: list[Any] = []
    if _INCLUDE_E102_CASH_DETAIL:
        from app.services.workpaper_sync import phase5_e1_02_cash_detail as _e102

        specs.append(_e102.SPEC_E102)
    if _INCLUDE_E104_DIGITAL:
        from app.services.workpaper_sync import phase5_e1_04_digital as _e104

        specs.append(_e104.SPEC_E104)
    return tuple(specs)


def static_region_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的 `static_region` spec 清单。"""
    if not _INCLUDE_E111_COMMITMENT_STATIC:
        return ()
    from app.services.workpaper_sync import phase5_e1_11_commitment as _e111

    return (_e111.SPEC_E111,)


def _managed_last_col_of(spec: Any) -> str:
    from app.services.workpaper_sync.sheet_geometry import col_index

    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    """`RowTableSheetSpec` → `ExcelInstrumentationSpec`（只翻动态区）。"""
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


def _static_sheet_declarations() -> tuple[dict[str, Any], ...]:
    """静态受管区寄生声明（`region_kind=static`：只写 definedName，不建 Table、不注 UUID 列）。"""
    return tuple(
        {
            "sheet_key": s.sheet_key,
            "managed_sheet": s.managed_sheet,
            "defined_name": s.defined_name,
            "first_data_row": s.first_data_row,
            "last_data_row": s.last_data_row,
            "region_kind": "static",
        }
        for s in static_region_specs()
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 的全部 instrumentation 声明（静态区寄生在首个动态 spec 上）。"""
    dynamic = [_instrumentation_of(s) for s in managed_row_table_specs()]
    statics = _static_sheet_declarations()
    if statics and dynamic:
        primary = dynamic[0]
        dynamic[0] = ExcelInstrumentationSpec(
            entry_id=primary.entry_id,
            template_id=primary.template_id,
            template_relative_path=primary.template_relative_path,
            managed_sheet=primary.managed_sheet,
            first_data_row=primary.first_data_row,
            last_data_row=primary.last_data_row,
            footer_row=primary.footer_row,
            managed_last_col=primary.managed_last_col,
            uuid_col=primary.uuid_col,
            table_name=primary.table_name,
            sheet_key=primary.sheet_key,
            transposed_sheets=primary.transposed_sheets,
            static_sheets=statics,
        )
    return tuple(dynamic)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 的全部 store item（**单一口径**，出/回两方向都从它取，需求 3.3）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    if _INCLUDE_E111_COMMITMENT_STATIC:
        from app.services.workpaper_sync import phase5_e1_11_commitment as _e111

        for item in _e111.STORE_ITEM_IDS_E111:
            if item not in items:
                items.append(item)
    return tuple(items)
