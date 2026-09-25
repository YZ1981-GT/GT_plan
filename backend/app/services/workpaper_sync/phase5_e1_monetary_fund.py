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
#: ✅ 2026-09-26 开启：声明层判据齐全（15 用例）+ 契约已生成并双向锁死。
#: ⚠️ 真栈 materialize / §9.6 三谓词仍卡 adapter 未注册（umbrella BP-61-1 平台级缺口）。
_INCLUDE_E102_CASH_DETAIL: Final[bool] = True

#: 第二张：E1-4 数字货币（验证「复用框架层零改动」）。
#: ✅ 2026-09-26 开启：与 canary 同批，用于证明「第二张接入无需改框架层」。
_INCLUDE_E104_DIGITAL: Final[bool] = True

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


#: 🔴 `oo_to_html` 的 rows 分支读的单数常量（**canary 的键**）。
#:
#:    E1 是多 store item 形态，但回方向的 rows 分支一次只镜像一条 item ⇒ 这里指向 canary
#:    `E1-cash-detail-rows`。其余 item 由 `all_store_item_ids()` 供出方向使用；
#:    将来多 item 一次性镜像时改走 `dual_store_fn` 门面（D4 的 `_mirror_d4_dual_stores` 同型），
#:    归 spec Task 10（宿主接桥）。
#:
#:    ⚠️ 为什么不留空/不省略：`oo_to_html` 用 `bridge.STORE_ITEM_ID` 取值，缺它就是
#:    AttributeError → opaque 500（g7/h1 刚因同款问题被修）。
STORE_ITEM_ID: Final[str] = "E1-cash-detail-rows"


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


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation / definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """单数入口（与 D1/D3 等同名函数同口径）：取受管清单的**第一个**动态 spec。

    🔴 受管清单为空（三个开关全 False）时抛而非返回 None —— 「没有受管 sheet 却在问
    instrumentation」是调用方逻辑错误，静默返回 None 会让下游在 `None.template_id` 处
    炸出无来源的 AttributeError。
    """
    specs = instrumentation_specs()
    if not specs:
        raise EntrySelectionError(
            "E1 当前无受管 sheet（三个 _INCLUDE_* 开关全 False）—— "
            "instrumentation_spec() 无可返回项；请先打开至少一个灰度开关"
        )
    return specs[0]


def template_definition_payload() -> dict[str, Any]:
    """template definition 的 canonical payload（发布 DAG 第一段）。"""
    from app.services.workpaper_sync.excel_instrumentation import (
        build_template_payload,
        normalized_structure_hash,
    )

    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    """instrumentation definition 的 canonical payload（单向引用 template digest）。"""
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.excel_instrumentation import (
        build_instrumentation_payload,
    )

    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    """authoritative model definition 的 canonical payload（独立批准）。"""
    from app.services.workpaper_sync.models import BundleSlot

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
#
# 🔴 契约由**框架层引擎**从受管 spec 装配（`phase5_row_table_sheet` 的 7 元组 +
#    `managed_field_specs` 排序），本模块不再手写 field 循环 —— 那正是本 spec 要消除的
#    「每家 provider 复制一份契约装配算法」。
# ═══════════════════════════════════════════════════════════════════════════


def _src(sheet: str, cell: str) -> str:
    """`source_ref` 的统一形态：权威源 xlsx 的 `sheet!单元格`。"""
    return f"源xlsx!{sheet}!{cell}"


def stable_key_for(spec: Any, column_key: str, row_identity: str = "{row_uuid}") -> str:
    """`{table_key}/{row_identity}/{column_key}`（转发框架层，唯一拼装处）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _framework_stable_key_for,
    )

    return _framework_stable_key_for(spec, column_key, row_identity)


def _rows_table_payload(spec: Any) -> dict[str, Any]:
    """一个受管行表区的契约 table payload（字段序由引擎按列序给出）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

    header_row = spec.header_leaf_row or spec.header_row or spec.header_group_row
    anchor_row = spec.header_group_row or spec.header_row or header_row
    fields: list[dict[str, Any]] = []
    for (
        column_key,
        column,
        mode,
        value_type,
        json_path,
        header_text,
        group_cell,
    ) in managed_field_specs(spec):
        field: dict[str, Any] = {
            "stable_field_key": stable_key_for(spec, column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(spec.managed_sheet, f"{column}{spec.first_data_row}"),
            "header_source_ref": _src(
                spec.managed_sheet,
                f"{column}{spec.header_leaf_row if group_cell else (spec.header_row or anchor_row)}",
            ),
            "store_item_id": spec.store_item_id,
            "header_text": header_text,
        }
        if group_cell:
            field["group_source_ref"] = _src(spec.managed_sheet, group_cell)
        fields.append(field)
    return {
        "table_key": spec.table_key,
        "anchor": f"A{anchor_row}",
        "header_rows": 2 if spec.header_group_row and spec.header_leaf_row else 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{spec.row_identity_key}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": spec.footer_marker,
            "search_column": "A",
            "carries_total_formula": True,
        },
        "formula_mask": list(spec.formula_mask),
        "fields": fields,
    }


def build_contract_payload() -> dict[str, Any]:
    """本 entry 的 per-entry contract canonical payload（两个 digest 现算，单向引用）。

    🔴 受管清单为空时抛：空契约（`sheets: []`）会让 `parse_contract` 与 attach 侧的对齐
    计数守卫都拿不到锚点，且一旦被发布就固化成「这个 entry 什么都不受管」的假身份。
    """
    from app.services.workpaper_sync.contracts import CONTRACT_SCHEMA_VERSION
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    row_specs = managed_row_table_specs()
    if not row_specs:
        raise EntrySelectionError(
            "E1 当前无受管行表 sheet（三个 _INCLUDE_* 开关全 False）—— "
            "不得发布空契约（sheets: [] 会固化成「什么都不受管」的假身份）"
        )

    template_payload = template_definition_payload()

    # 同一 sheet 的多个受管区合并进一个 sheet 条目（一 sheet 多 table）
    sheets: list[dict[str, Any]] = []
    by_sheet_key: dict[str, dict[str, Any]] = {}
    for spec in row_specs:
        entry = by_sheet_key.get(spec.sheet_key)
        if entry is None:
            entry = {
                "sheet_key": spec.sheet_key,
                "excel_name": spec.managed_sheet,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [],
            }
            by_sheet_key[spec.sheet_key] = entry
            sheets.append(entry)
        entry["tables"].append(_rows_table_payload(spec))

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
            "cross_volume_keys": dict(CROSS_VOLUME_KEYS),
        },
    }


#: 契约 `review.html_store.note` 的冻结文本。
_HTML_STORE_NOTE: Final[str] = (
    "E1 第一册的受管 sheet 各自一条 checklist_responses item。🔴 行身份键是 `id`"
    "（**不是** D 循环惯用的 `rowId`）—— useE1CashDetail/useE1Digital 的行对象字段名实测为 "
    "`id`，照抄 D 类会让 store-projection fail-closed 抛「缺稳定行身份」把整个 entry 打挂。"
    "E1-2 另有不可删除的固定行 `fixed-rmb`（对应模板 R15 人民币），与动态行 `cash-<uuid>` "
    "同在 `id` 字段 ⇒ 混合身份无需拆区"
)

#: 契约 `review.reviewed_basis` 的冻结文本。
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格直读权威模板 E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx"
    "（第一册，16 sheet，sha256 8317e2ba）。受管 sheet 的几何全部逐格实测："
    "现金明细表E1-2 两级表头 R13/R14、数据区 R15-21（R15-19 预填币种 人民币/美元/日元/澳元/欧元、"
    "R20-21 空白待扩）、footer R22「合计」=SUM(15:21)、公式列 E=B+C-D / G=E*F（乘法）/ "
    "I=G+H*F（乘加混合）、R23「其中：存放在境外的款项总额」在 footer 之下故登记 HTML-only；"
    "数字货币明细表E1-4 单级表头 R9、数据区 R10-16（预填序号 1-7）、footer R17、"
    "公式列 H=E+F-G / I=H*D / K=H+J / L=K*D。"
    "形态判定用**前端三元组**（store 键按值 grep / addRow-removeRow 信号 / composable 归属）"
    "而非模板公式数 —— E1-9/E1-10/E1-11 各只 7 公式，按公式数阈值会把三张全判 static_region，"
    "实证只有 E1-11 成立（零 -rows 键、无 composable、承诺函段落表单）"
)


def contract_file_path() -> Path:
    """磁盘契约路径（`contracts.contract_path_for` 是唯一拼路径处）。"""
    from app.services.workpaper_sync.contracts import contract_path_for

    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk():
    """从磁盘加载并强校验本 entry 的生产契约。"""
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source():
    """磁盘契约 ↔ 本模块现算 payload **双向**锁死。"""
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync.definitions import canonical_digest

    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_e1_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. store 投影与合并（**薄转发框架层引擎**，本模块零算法）
#
# 🔴 这是本 spec 三层架构的收益兑现点：D1/D3/D5/D6/D7 五家各自复制了约 200 行
#    投影 + 合并代码，而 E1 作为「引擎落地后新建的第一个 entry」只需转发 —— 每个函数 ≤3 行。
#    若这里需要写算法，说明框架层抽象不足，应回上游
#    `d1-sync-row-table-engine-and-d1-coverage` 修而不是在此特化。
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（**不静默跳过** —— 那是 D4-35 恒空的根因形态）。"""
    for spec in (*managed_row_table_specs(), *static_region_specs()):
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 E1 当前受管清单里；"
        f"已受管：{sorted(all_store_item_ids())} —— "
        "灰度开关未开或键名写错时必须显式失败，不得静默当成零行"
    )


def build_store_projection(
    payload: Any, *, contract: Any, limits: Any | None = None, store_item_id: str | None = None
) -> Any:
    """HTML store 载荷 → `Projection`（薄转发框架层引擎）。

    :param store_item_id: 指定按哪个受管区投影；缺省用 canary（:data:`STORE_ITEM_ID`）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine_build,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_build(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list, store_item_id: str | None = None
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
