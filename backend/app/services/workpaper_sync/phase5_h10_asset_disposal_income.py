"""H10「资产处置损益」entry —— 受管 sheet 是 **调整分录汇总H10-3**。

spec: `h2-h6-h10-pilot-cross-reference-lanes`

═══ 🔴 本 entry 与 slice 的一处**实测反驳**（H 循环第 6 条）═══

slice 的 `primary_table` 记的是 `明细表H10-2 ↔ H10-detail-rows`。openpyxl + 前端双向
实测证明该配对在结构上不成立（理由见 `phase5_h10_03_adjustment` 模块 docstring 与
契约 `review.declared_coverage_gaps` 的 **H10-GAP-1**）。本 entry 改以
`调整分录汇总H10-3 ↔ H10-adjustment-rows` 为受管表：**6/10 映射，全 H 最高档**。

slice 是 append-only 审计轨迹，**不回填**；反驳写在这里与契约里，判据侧按现算分派。

═══ 册级事实（openpyxl 实测）═══

`H/H10 资产处置损益.xlsx` 42,334 B / **9 sheets**（全 H 最小的一册）：
底稿目录 · 资产处置损益实质性程序表H10A · 审定表H10-1 · 附注披露信息（上市公司） ·
附注披露信息（国企） · 明细表H10-2 · 调整分录汇总H10-3 · 检查表H10-4 · **GT_Custom**

* **definedName 0 个 / Excel Table 0 个**（H 循环 9 册一致，HC-14 「保持为无」）
* **含 `IF(` 的公式格 46 个**（明细表H10-2 43 / 调整分录汇总H10-3 1 / 检查表H10-4 2）
  ⇒ `oo_crash_neutralization_fn` 必挂，函数与 G7/G2/H9/H6/H4/H8/H2/H3/H5/H7 共用不新造
* `GT_Custom` hidden sheet 与 H9 两册独有（HD 族事实）

═══ 🔴 审定表H10-1 / 附注披露 两张是**整表派生**，不可写 ═══

* `审定表H10-1` 的 A6..J14 逐格是 `='明细表H10-2'!A8..W16`，E/J 列是 `=B+C+D` /
  `=G+H+I` ⇒ 全表只有 TB 数两格（`E16`/`J16`）是自由输入。
* `附注披露信息（上市公司）` 的 B9..C17 逐格是 `='审定表H10-1'!E6..J14`。

⇒ 模板里「账项调整 / 重分类调整」的**权威落格在 明细表H10-2 的 O/P 列**，不在 H10-1。
前端把这两个量叫做 H10-1 审定表的 `currentAje`/`currentRje`，名字不同、量是同一个。
往 H10-1 的 C/D 写会毁掉跨 sheet 公式 —— 这是 H10-GAP-1 里「H10-2 才是候选」的由来。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h10_03_adjustment as _h1003
from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract, contract_path_for
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_asset_disposal_income_adjustment"
ENTRY_ID: Final[str] = "xlsx/gt-h10-asset-disposal-income"
ADAPTER_ID: Final[str] = "h10.asset_disposal_income_adjustment"

#: 🔴 与其余 8 条不同：H10 的 `wp_code_pattern` 是 **`H10A`**（程序表码，slice 冻结值），
#:    不是幻影码。三条 finder 路径实测它解析到**所属整册**（commit `891aec512`
#:    「贯通整册打开即定位」之后的既有行为）⇒ `phantom_code_resolves_to_own_workbook=True`。
WP_CODES: Final[frozenset[str]] = frozenset({"H10A"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H10 资产处置损益.xlsx"
#: 逐字取 openpyxl 现算（42,334 B / 9 sheets）
TEMPLATE_SHA256: Final[str] = (
    "9f0d2a64dab1fd7661bb512194b4eba9a22f5afe28db38ec64fc22867421ac8a"
)

STORE_ITEM_ID: Final[str] = _h1003.STORE_ITEM_ID_H1003
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h1003.ROW_IDENTITY_STORE_KEY_H1003

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H10 **有** TB 发布门，但挂在 **H10-1 审定表**上，不是本受管 sheet。
TB_PUBLISH_GATE: Final[str] = (
    "H10TabAdjudication → useH10Adjudication.publishToTb "
    "（POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，"
    "sheet_name='审定表H10-1'，单科目 6115，`amount_kind='occurrence'` 发生额口径，"
    "中文二次确认）。🔴 挂在 H10-1 上；sync 路径对 trial_balance 写 0 次。"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    #: 🔴 `entryType` 是**受管字段里唯一的枚举**，且域是二值（前端）对三值（模板）。
    "enum_fields": {
        "entry_type": {
            "store_domain": ["AJE", "RJE"],
            "template_header_domain": ["账项调整AJE", "重分类调整RJE", "其他"],
            "normalizer": (
                "useH10Adjustment.normalizeEntry —— "
                "`raw.entryType === 'RJE' ? 'RJE' : 'AJE'`（非 RJE 一律归 AJE）"
            ),
            "mode": "auto_source",
            "why": "见 declared_coverage_gaps 的 H10-GAP-2：editable 会静默换掉「其他」",
        }
    },
    "derived_fields": [],
    "store_only_fields": list(_h1003.STORE_ONLY_FIELDS_H1003),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h1003.TEMPLATE_ONLY_COLUMNS_H1003
    ],
    "unmanaged_regions": [dict(r) for r in _h1003.UNMANAGED_REGIONS_H1003],
    "declared_coverage_gaps": [dict(g) for g in _h1003.DECLARED_COVERAGE_GAPS_H1003],
    "resolved_coverage_gaps": [],
    "legacy_folded_fields": {},
    "derived_total_keys": list(_h1003.DERIVED_TOTAL_KEYS_H1003),
    #: 🔴 本 entry 的兄弟键特别多（一册 9 sheet、前端 11 个 composable）。
    "sibling_tables_not_managed": [
        "H10-detail-rows",
        "H10-adj-rows",
        "H10-adj-tb",
        "H10-adj-note",
        "H10-adj-conclusion",
        "H10-1-adjudicated-amount",
        "H10-check-rows",
        "H10-4-check-sample-meta",
        "H10-3-adjustment-audit-note",
        "H10-disclosure-listed-trial",
    ],
    "variant_axis": None,
    "carrier": {
        "write": "formdata_composable",
        "read": "formdata_composable",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    #: footer R19 只有两个金额列有 SUM（不是全列）—— 其余 8 列 footer 格为空。
    "footer_non_sum_cells": {
        "A19": "'合计' 标记（footer_anchor.marker）",
        "B19..F19": "空（本表只有 G/H 两个金额列，其余列无合计语义）",
        "I19..J19": "空",
    },
    "effective_columns": _h1003.EFFECTIVE_COLUMNS_H1003,
    "uuid_column": _h1003.UUID_COL_H1003,
    "column_coverage_closure": {
        "mapped": len(_h1003.FIELD_SPECS_H1003),
        "template_only": len(_h1003.TEMPLATE_ONLY_COLUMNS_H1003),
        "effective_columns": _h1003.EFFECTIVE_COLUMNS_H1003,
    },
    #: 🔴 本 entry 的键是**字面量**（`ITEM_ID_ROWS = 'H10-adjustment-rows'` 模块常量），
    #:    不是 H5 那种 `${ITEM_PREFIX}-rows` 拼接 ⇒ 按值 grep 直接命中。
    "store_item_key_is_concatenated": None,
    #: 🔴 第三个客户端存储（slice 的 `extra_client_store`）—— 全 slice 唯一。
    "extra_client_store": {
        "kind": "localStorage_draft_fallback",
        "source": (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH10FormData.ts —— `saveImmediate` 重试 3 次仍失败时 "
            "`localStorage.setItem(draftKey(wpId, itemId), …)`；"
            "`restoreDrafts()` 在 `loadResponses` 之后回灌并立即重试。"
        ),
        "why_it_matters_for_sync": (
            "🔴 「HTML 侧内容 == checklist_responses」这个 roundtrip 前提在**有未同步草稿时"
            "不成立** —— 草稿里的改动还没进服务端，materialize 读不到它，"
            "回到 HTML 又会被 restoreDrafts 灌回来 ⇒ 看起来像「OO 侧把它删了又自己长回来」。"
            "本轮处置：`flushPendingSaves()` 先清防抖并 await 落库；"
            "落库失败进草稿的那一支**仍在缺口内**（网络不可用时切 OO 本就不该成功，"
            "桥的 fail-visible 会拦住），故不额外造机制。"
        ),
    },
}

IDENTITY: Final[HC.HEntryIdentity] = HC.HEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    expected_profile_id=EXPECTED_PROFILE_ID,
    #: 🔴 `H10A` 是**真程序表码**，finder 解析到所属整册（不是幻影码）
    phantom_code_resolves_to_own_workbook=True,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H10 资产处置损益的调整分录行存成 checklist_responses 的 **remark** JSON 数组"
    "（键 `H10-adjustment-rows`，模块常量 `useH10Adjustment.ITEM_ID_ROWS`，**字面量**不是拼接），"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 **受管 sheet 是 调整分录汇总H10-3，不是 slice 声明的 明细表H10-2** —— "
    "slice 依据 `A7='项目'` 把 明细表H10-2 配给 `H10-detail-rows`，实测两者结构不同类："
    "模板那张是 **9 类固定行 × 12 月** 的月度矩阵（R8:R16 × B..M，合计 `N=SUM(B:M)`），"
    "前端 `H10-detail-rows` 是**逐单项资产台账**（25 字段、行可增删、身份 `id`），"
    "且前端按值 grep `1月|月度|monthly|各月` 在全部 H10 组件/composable 下**零命中**。"
    "改配 `调整分录汇总H10-3 ↔ H10-adjustment-rows` 后映射率 **6/10（60%）是全 H 最高档**"
    "（对照 H5 10/54、H7 公允 3/28）。详见 review.declared_coverage_gaps 的 H10-GAP-1。"
    "🔴 **`B 类别` 是 `auto_source` 不是 `editable`**：前端 `entryType` 只有二值"
    "（`raw.entryType === 'RJE' ? 'RJE' : 'AJE'`），模板表头是三值（含「其他」）⇒ "
    "editable 会让 OO 侧填的「其他」被静默归一成 AJE 并回写覆盖（H10-GAP-2）。"
    "`auto_source` 让该格在 OO 侧受保护、值照写，缺陷无从触发。"
    "🔴 **单级表头 R5 是 H 循环唯一一张**（其余 8 条是两级/三级/四级）⇒ 走 `header_row` "
    "而非 `header_group_row`/`header_leaf_row` 一对，否则 header_rows 会算成 2、anchor 落进标题区。"
    "🔴 **数据区零公式**（R6:R18 实测 13 行全空）⇒ `FORMULA_TEMPLATES` 是空字典；"
    "footer R19 只有 `G19`/`H19` 两个 SUM（**不是全列 SUM**，本表只有两个金额列）。"
    "🔴 **派生聚合键 `H10-adj-overlay`**：`syncWriteback` 把本表行聚合成 "
    "`{currentAje, currentRje}` 写它、并据此 patch `H10-adj-rows`（H10-1 审定表 store）⇒ "
    "进 `derived_total_keys`，roundtrip 比对排除、重算责任方是前端。"
    "OO 侧改金额后的再聚合由 `useH10Adjustment` 的**按值守卫 watch** 触发（H10-GAP-4）。"
    "🔴 **第三个客户端存储**（全 slice 唯一）：`useH10FormData.saveImmediate` 重试 3 次失败后"
    "写 localStorage 草稿、`restoreDrafts()` 回灌 ⇒ 见 review.extra_client_store。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H10 资产处置损益.xlsx（42,334 B / **9 sheets**，全 H 最小的一册）："
    "`调整分录汇总H10-3`（**单级**表头 R5 / 数据 R6-R18 共 13 行**实测全空** / "
    "footer R19 `合计` 仅 G19=`=SUM(G6:G18)` H19=`=SUM(H6:H18)` **两格** / "
    "有效内容列 **10 即 A..J**，`max_column=10` 无空列尾巴 / 数据行公式列 **0 个** / "
    "数据区**零合并域**（全 sheet 只有 A1:J1 与 A2:J2 两个标题合并）/ "
    "R20-R21 未受管：A20='借贷差额（应为0）' G20=`=G19-H19` "
    "H20=`=IF(G20=0,\"平衡\",\"不平衡\")` + A21 提示文字)"
    " + 册级：definedName **0** / Excel Table **0** / 含 IF 公式格 **46** "
    "（明细表H10-2 43 · H10-3 1 · 检查表H10-4 2）/ `GT_Custom` hidden sheet（与 H9 两册独有）"
    " + 反驳 slice 的 primary_table 配对：`明细表H10-2` 实测是 9 类固定行（R8:R16，"
    "标签逐字与前端 `H10_ADJUDICATION_ITEMS` 前 9 项一致，R17 合计 / R18 各月比例）× "
    "12 月（B..M）+ N=SUM(B:M) + O 账项调整 + P 重分类调整 + Q=N+O+P + R/S 勾稽 + T 结构比 + "
    "U/V/W 上年三列 + X=U+V+W + Y 结构比 + Z 增长比；`审定表H10-1` A6..J14 **整表派生**"
    "（逐格 `='明细表H10-2'!…`，只有 TB 数两格自由）；`附注披露信息（上市公司）` B9..C17 "
    "逐格 `='审定表H10-1'!E6..J14`"
    " + 前端按值 grep（useH10Adjustment.ts `ITEM_ID_ROWS='H10-adjustment-rows'` 字面量常量 / "
    "`H10AdjustmentEntry` **11 字段** / normalizeEntry 的 entryType 二值归一 / "
    "`counterAccountCode: ''` 带 TODO 自证「无对方科目字段」/ "
    "syncWriteback 写 `H10-adj-overlay` + patch `H10-adj-rows` / "
    "useH10Detail.ts `H10DetailRow` **25 字段**、身份 `id`、`generateId()` = "
    "`h10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2,6)}` / "
    "`1月|月度|monthly|month|各月` 在 h10 全域**零命中**)"
    " + 发布门现算（useH10Adjudication.publishToTb，sheet_name='审定表H10-1'，"
    "科目 6115 `amount_kind='occurrence'`）"
    " + 覆盖闭合自检（6+4==10，并集连续 A..J 无缺口、无列重复无交叠）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H10-3 一张；册内其余 8 个 sheet 的处置：
#   底稿目录 / 资产处置损益实质性程序表H10A  → 不接
#   审定表H10-1                              → **整表派生**（A6..J14 全是跨 sheet 引用），
#                                              写它会毁公式；且带 TB 发布门 ⇒ 归审定表后置族
#   明细表H10-2                              → 🔴 **结构性不匹配**，见 H10-GAP-1
#   检查表H10-4                              → 归后续批次（R10:R18 × A..Q 全自由，但前端
#                                              `H10CheckRow` 的 9 个合规枚举与模板 J..N 的
#                                              5 项「核对内容」语义不对应，`voucherRef` 是
#                                              `date/no` 合并串 ⇒ 映射率约 2-3/17，低于 H10-3）
#   附注披露信息（上市公司）                  → B9..C17 派生自 H10-1；R18 与 R29:R31 试运行
#                                              小表自由（对应 `H10-disclosure-listed-trial`）
#                                              ⇒ 归附注披露族
#   附注披露信息（国企）                      → 归附注披露族
#   GT_Custom                                → 平台自用 hidden sheet，不接

_INCLUDE_H1003: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H1003:
        specs.append(_h1003.SPEC_H1003)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H10-1 审定表 —— **整表派生**（只有 TB 数两格自由）⇒ 恒 None。

    🔴 不是「归后置批次」那么简单：本册的 H10-1 逐格是 `='明细表H10-2'!…`，
    即便将来接它，可写面也只有 `E16`/`J16` 两格 TB 数。真正的输入面在 明细表H10-2。
    """
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    return HC.template_definition_payload(IDENTITY, managed_row_table_specs())


def instrumentation_definition_payload() -> dict[str, Any]:
    return HC.instrumentation_definition_payload(IDENTITY, managed_row_table_specs())


def excel_carrier_gate():
    return HC.excel_carrier_gate()


def authoritative_template_path() -> Path:
    return HC.authoritative_template_path(IDENTITY)


def read_authoritative_template() -> bytes:
    return HC.read_authoritative_template(IDENTITY)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件
# ═══════════════════════════════════════════════════════════════════════════

TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    """口径见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。"""
    del wp_codes
    HC.assert_phantom_code_does_not_leak(IDENTITY, resolution)


def assert_entry_selectable(
    *,
    resolution: HC.TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return HC.assert_entry_selectable(IDENTITY, resolution=resolution, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约装配
# ═══════════════════════════════════════════════════════════════════════════


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH10Adjustment.ts —— `persist()` 经宿主 `debouncedSave` 写 "
            "{ item_id: 'H10-adjustment-rows', remark: JSON.stringify(list) }"
        ),
    )


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# 5. store 投影 / 合并（**薄转发**框架层）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 H10 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`。

    🔴 签名形态刚性：`payload` 第一个位置参、`store_item_id` 走关键字。
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
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, payload)


# ═══════════════════════════════════════════════════════════════════════════
# 6. manifest capability / adapter 注册 / attach
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    """matcher 域：`H10A` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
    return HC.build_matcher(IDENTITY)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return HC.build_registration(
        IDENTITY,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
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
    return HC.register_adapter(
        registry,
        IDENTITY,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach H10 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )
