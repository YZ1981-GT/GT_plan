# -*- coding: utf-8 -*-
"""I5 其他非流动资产 —— Phase 5 entry 模块（I 循环结构最深的一条）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 11 / 13 / 17 / 18

═══ 🔴 I5 的五个「唯一」 ═══

| 维度 | I5 | 其余 5 条 |
|---|---|---|
| 载体族 | 🔴 **`formdata_composable`** | 全部 `host_inline` |
| `http_import`（宿主） | 🔴 **0** | 各 1 |
| 数据区数 | 🔴 **三区**（原值 / 减值 / 净值） | 单区或双区 |
| 内置行「删除」语义 | 🔴 **原位重置**（不是真删） | 真 splice |
| payload mode | 🔴 **`passthrough`** | `remark_only` × 4 · I4 `dual_write` |

**载体的意义**：I5 宿主 `GtI5OtherNoncurrentAssets.vue`（**289 行，全 I 最短**）里
**没有任何 http / api client import**（现算 0）—— 写在 `useI5FormData.ts` 里。
🔴 变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 在本条上打红 ——
这条反向断言是 IC-2 从「单一形态」推成「二分」的直接证据。

**`http_import` = 0 的解释**：I5 无导入入口（结构最深，靠 composable 建行）。
🔴 按 IC-20 空分母纪律：断言「现算 0 且不是漏扫」，**不宣称该维度通过**。
没有解释的 0 就是漏扫的伪装。

═══ 🔴 三区完全镜像是平台新形态（同一行同时在三个区）═══

与既有两种多区范式都不同（`phase5_d3_04_analysis` 的「一区一 store 键」、
G9/G1 的 `region_filter`「行按字段值分到某一个区」）——
本表是**一行的 gross 在区①、impairment 在区②、净值在区③派生**。

⇒ 处置：**两个 spec 共享同一 `store_item_id`**（`I5-2-rows`），
`json_key` 分别走嵌套路径 `gross/*` 与 `impairment/*`；**第 3 区不建 spec**。

🔴 **第 2 区的 A 列是 FORMULA 不是 editable**（`=A11`..`=A21` 镜像）⇒
它进 `formula_columns` 而**不映射任何 store 字段**；否则 merge 会拿 HTML 的 None 覆盖镜像公式、
让减值区的行标签整列变空。

🔴 **第 3 区 `fully_derived_region`**（A..O 全列 `=x11-x24`）⇒ 整区跳过、不接受用户输入。
若允许写入，用户改的净值会在下次 render 被公式覆盖、**静默丢失**。

🔴 **三区行数必须相同（各 11）且按行序镜像对应**；变异「把某一区改成 10 行」SHALL 打红。

═══ 🔴 IE-4：内置行「删除」是原位重置且曾换掉 rowId ═══

`useI5Detail.ts#L821-839` 实读：
`if (row.isBuiltin) rows[idx] = emptyI5DetailRow({projectName, name, isBuiltin, indexRef})
 else rows.splice(idx, 1)`

传入的字段里**原本不含 `rowId`**，而 `emptyI5DetailRow` 内 `#L305 rowId: generateRowId()`
⇒ 重置后 rowId 变了且 `_persist()` 把新 rowId 落库。

双重影响：①行数不变（按行数或 `projectName` 比对会认为没变）②rowId 变了
（按 rowId 比对会认为「删一行 + 增一行」）⇒ roundtrip 会把「重置的内置行」当成「已删的业务行」。

**双保险已落地**：
* 修复①（治未来）：`#L826` 传 `rowId: row.rowId` 保留原身份
* 修复②（治历史）：契约声明 `builtin_row_identity_field = "projectName"` ——
  实现自己就在用它反查 `indexRef`（`#L830` 的
  `I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)?.indexRef`）

═══ 🔴 真库载荷是 E2E 种子，不可作 roundtrip 基线 ═══

真库 `I5-2-rows` **745 B**（全 I 最大）但 `rowId == "e2e-i52-contract"` ——
**不符 `i52-` 生成器格式**，是 **E2E 测试种子**（随 E2E 套件可被重置）。
⇒ 标 `live_payload_is_e2e_seed_not_business_data`；
`passthrough` mode **未被业务数据证实**（真库 I 循环 7 行全 remark_only）；
roundtrip 用**合成载荷**并标 `synthetic_payload`。

═══ definedName 334 + 334 公式（全 I 最多）═══

与 I4 的 476 一起构成「基线不增长」口径的唯一实证场（其余四册全 0）。**不删**。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i5_02_detail as _i502
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_other_noncurrent_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i5-other-noncurrent-assets"
ADAPTER_ID: Final[str] = "i5.other_noncurrent_assets_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"I5O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I5 其他非流动资产.xlsx"
#: 🔴 2026-10-01 净化（`sanitize_i_cycle_template_external_links.py`，过 OOXML 门）后现算；
#: 净化前 `7e8ec9c22580e05daf7803362f1ab83ca39d452a56c009833b05d6f6a1393860`（slice 冻结值，append-only 保留；`.preclean.bak` 即其字节）。
TEMPLATE_SHA256: Final[str] = (
    "dacd18184ef82195b489d014ac2dc7a4dc5edb9df5306d85f7ceb433be56068f"
)

STORE_ITEM_ID: Final[str] = _i502.STORE_ITEM_ID_I502
EMPTY_STORE_PAYLOAD: Final[str] = _i502.EMPTY_PAYLOAD_I502
ROW_IDENTITY_STORE_KEY: Final[str] = _i502.ROW_IDENTITY_STORE_KEY_I502

PAYLOAD_COLUMN: Final[str] = "remark"
#: 🔴 slice 声明 `passthrough`；真库 7 行全 remark_only ⇒ 契约标 unverified。
PAYLOAD_COLUMN_MODE: Final[str] = "passthrough"

TB_PUBLISH_GATE: Final[str] = (
    "composables/useI5Adjudication.ts#L362 + i5/core/I5TabAdjudication.vue#L718"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 IC-2：载体第二族（全 I 唯一）+ 反向断言
    "carrier": {
        "write": "formdata_composable",
        "write_module": "composables/useI5FormData.ts",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i5-other-noncurrent-assets",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "gate_layer": "composable",
        "mounts": 2,
        "host_has_http_import": False,
        "host_checklist_get_hits": 0,
        "host_line_count": 289,
    },
    "carrier_reverse_assertion": (
        "🔴 I5 宿主 GtI5OtherNoncurrentAssets.vue（289 行，全 I 最短）里**无任何 "
        "http / api client import**（现算 0）—— 写在 useI5FormData.ts 里。"
        "变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 在本条上打红 —— "
        "这条反向断言是 IC-2 从「单一形态」推成「二分」的直接证据。"
    ),
    "oo_flags": {
        "legacyOO": 5,
        "http_import": 0,
        "isOoAvailable": 2,
        "structured_only_switch": 1,
    },
    "oo_flags_zero_note": (
        "🔴 `http_import` = **0**：I5 无导入入口（结构最深，靠 composable 建行）。"
        "按 IC-20 空分母纪律断言「现算 0 且不是漏扫」，**不宣称该维度通过** —— "
        "没有解释的 0 就是漏扫的伪装。"
    ),
    # 🔴 三区镜像（平台新形态）
    "region_mirror": dict(_i502.REGION_MIRROR_I502),
    "regions": [
        {"idx": 0, "rows": [11, 21], "kind": "editable", "role": "gross", "managed": True},
        {
            "idx": 1,
            "rows": [24, 34],
            "kind": "editable",
            "role": "impairment",
            "managed": True,
            "label_column_is_formula": True,
        },
        {
            "idx": 2,
            "rows": [37, 47],
            "kind": "fully_derived_region",
            "role": "carrying",
            "managed": False,
            "formula": "A..O 全列逐格 =x11-x24（原值 − 减值）",
        },
    ],
    "multi_region_paradigm_note": (
        "🔴 **平台新形态**：与既有两种多区范式都不同 —— "
        "`phase5_d3_04_analysis` 的「一区一 store 键」（各区行集互斥）与 G9/G1 的 "
        "`region_filter`（行按字段值**分到**某一个区）都是「一行属一个区」；"
        "本表是**一行同时在三个区**（gross 在区① / impairment 在区② / 净值在区③派生）。"
        "⇒ 处置 = **两个 spec 共享同一 store_item_id**，json_key 走嵌套路径 "
        "`gross/*` 与 `impairment/*`；第 3 区不建 spec。"
        "🔴 **第 2 区的 A 列是 FORMULA 不是 editable**（=A11..=A21 镜像）⇒ 它进 "
        "formula_columns 而**不映射任何 store 字段**；否则 merge 会拿 HTML 的 None "
        "覆盖镜像公式、让减值区行标签整列变空。"
        "🔴 **第 3 区 fully_derived_region** ⇒ 整区跳过不接受用户输入；若允许写入，"
        "用户改的净值会在下次 render 被公式覆盖、**静默丢失**。"
    ),
    "footer_rows": [22, 35, 48],
    "footer_rows_note": (
        "🔴 三个 footer **分别**标 kind（各区各一个，均为 pure_sum：B..O 各 "
        "=SUM(x{first}:x{last})）；不得只声明第一个。"
    ),
    # 🔴 IE-4：内置行原位重置 + 双保险
    "builtin_row_identity_field": _i502.BUILTIN_ROW_IDENTITY_FIELD_I502,
    "builtin_row_delete_semantics": _i502.BUILTIN_ROW_DELETE_SEMANTICS_I502,
    "builtin_row_note": (
        "🔴 `useI5Detail.ts#L821-839` 的 removeRow：`if (row.isBuiltin) rows[idx] = "
        "emptyI5DetailRow({projectName, name, isBuiltin, indexRef}) else rows.splice(idx,1)`。"
        "传入字段里**原本不含 rowId**，而 emptyI5DetailRow 内 #L305 `rowId: generateRowId()` "
        "⇒ 重置后 rowId 变了且 _persist() 把新 rowId 落库。双重影响：①行数不变"
        "（按行数或 projectName 比对会认为没变）②rowId 变了（按 rowId 比对会认为"
        "「删一行 + 增一行」）⇒ roundtrip 会把「重置的内置行」当成「已删的业务行」。"
        "**双保险已落地**：修复①（治未来）#L826 传 `rowId: row.rowId` 保留原身份；"
        "修复②（治历史）契约声明 builtin_row_identity_field='projectName' —— "
        "实现自己就在用它反查 indexRef（#L830 的 I5_BUILTIN_CATEGORIES.find("
        "c => c.name === row.projectName)?.indexRef）。"
        "🔴 判据 SHALL 断言**两个身份字段都存在**，只声明 rowId 一侧 SHALL 打红。"
    ),
    # 🔴 真库载荷是 E2E 种子
    "payload_column_mode_status": "unverified_in_live_db",
    "live_payload_flag": "live_payload_is_e2e_seed_not_business_data",
    "live_payload_note": (
        "真库 `I5-2-rows` **745 B**（全 I 最大）但 `rowId == 'e2e-i52-contract'` —— "
        "**不符 `i52-` 生成器格式，是 E2E 测试种子**（随 E2E 套件可被重置）。"
        "⇒ `passthrough` mode **未被业务数据证实**（真库 I 循环 7 行全 remark_only）；"
        "roundtrip 用**合成载荷**并标 synthetic_payload，**不得**把 E2E 种子行当基线。"
    ),
    # CD-3：clean（唯一正例之一）
    "classification": dict(_i502.CLASSIFICATION_FACTS_I502),
    # 🔴 IC-10：definedName 基线非 0
    "defined_name_baseline": _i502.DEFINED_NAME_BASELINE_I502,
    "defined_name_baseline_note": (
        "🔴 **334 个**（与 I4 的 476 一起构成「基线不增长」口径的唯一实证场；"
        "其余四册 I1/I2/I3/I6 全 0）⇒ 照抄 H 循环 HC-14 的「断言全 0」在那四册上恒真"
        "悄悄通过，**只有 I4/I5 会打红**。**不删**（模板公式的命名引用，删了公式整片失效），"
        "只声明「同步时不新增、不改写」。"
    ),
    # 🔴 IC-7：删行 API 属 id 族
    "row_delete_api": {
        "kind": "identity",
        "signature": "removeRow(rowId: string)",
        "site": "composables/useI5Detail.ts#L821",
        "builtin_branch": "composables/useI5Detail.ts#L825-831",
        "note": (
            "🔴 本 lane 是 **1:2 跨两族**（I2 index / I4+I5 identity），而 lane 1 两条 entry "
            "**100% 下标族** ⇒ 两个 lane **不得复用同一个签名断言**。"
        ),
    },
    # IC-6 在本 entry 命中 0
    "positional_identity_sites": [],
    "positional_identity_note": (
        "IC-6 在本 entry 现算 0 且不是漏扫（8 个 site 全在 lane 1 的 {I1, I3}）。"
        "按 IC-20 断言「现算 0」但不宣称该维度通过。"
    ),
    # representation：嵌套路径
    "representation": {
        "nested_paths": ["gross/*（15 字段）", "impairment/*（15 字段）"],
        "nested_note": (
            "两个子对象各 15 字段（unadjOpening/unadjIncrease/unadjDecrease/unadjEnding/"
            "openingAje/openingRje/ajeIncrease/ajeDecrease/rjeIncrease/rjeDecrease/"
            "auditedOpening/auditedIncrease/auditedDecrease/auditedEnding）；"
            "其中 5 个是前端按公式重算的派生值（unadjEnding + audited×4）⇒ 不进 field_specs。"
            "🔴 净值区（区③）**不入载荷**（完全派生）。"
        ),
    },
    "store_only_fields": ["isBuiltin", "indexRef", "name", "remark"],
    "store_only_note": (
        "`isBuiltin`（模板内置行标记，驱动 removeRow 的重置分支）· `indexRef`（跨底稿索引"
        "如 D7/M12/G2-13）· `name`（@deprecated → projectName 的别名）· `remark` —— "
        "四者在本 sheet 的 17 有效列里**无对应列** ⇒ store-only、merge 不动它们。"
    ),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i502.TEMPLATE_ONLY_FORMULA_COLUMNS_I502
    ],
    "template_cell_lock_facts": dict(_i502.TEMPLATE_CELL_LOCK_FACTS_I502),
    "variant_axis": None,
    "effective_columns": _i502.EFFECTIVE_COLUMNS_I502,
    "max_column": _i502.MAX_COLUMN_I502,
    "uuid_column": _i502.UUID_COL_I502,
    # IC-18：现算 0（IC-18 已裁 I3/I4/I5 皆 0 非漏扫）
    "derived_total_keys": [],
    "derived_total_keys_note": (
        "现算 **0** 个。IC-18 已裁 I3/I4/I5 皆 0 **不是漏扫**（I1 8 / I2 2 / I6 3）"
        "⇒ 按 IC-20 空分母纪律断言「现算 0」但不宣称该维度通过。"
    ),
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
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "I5 其他非流动资产的结构化 Tab 行数据存成 checklist_responses 的 JSON 数组。"
    "🔴 **一行同时映射三个区**：本契约据此建**两个 table**（`other_noncurrent_gross_rows` "
    "对区① R11-21 · `other_noncurrent_impairment_rows` 对区② R24-34），"
    "**共享同一 store item** `I5-2-rows`，json_key 走嵌套路径 `gross/*` 与 `impairment/*`。"
    "第 3 区（净值 R37-47）是 **fully_derived_region**（A..O 全列 =x11-x24）⇒ **不建 table、"
    "不入载荷**。"
    "🔴 区②的 **A 列是 FORMULA**（=A11..=A21 镜像）⇒ 进 formula_columns 而**不映射 store 字段**；"
    "区①的 A 列才是 editable 的 `projectName`。"
    "🔴 每区 10 个 formula 列里 5 个（E/L/M/N/O）是前端按同一套公式重算的派生值 ⇒ "
    "只进 formula_columns，formula_mask 保证 OO 侧不被覆盖。"
    "store-only 四字段（isBuiltin / indexRef / name / remark）在 17 有效列里无对应列。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I5 其他非流动资产.xlsx 的 `明细表I5-2`"
    "（**两级**表头 R8/R9 全 I 最浅 / 🔴 **三区完全镜像**：R10 区标题`其他非流动资产原值：` + "
    "区① R11-21 十一行（A 列字面标签 预付土地出让金……）+ footer R22 · "
    "R23 区标题`减值准备：` + 区② R24-34 十一行（🔴 A 列 **=A11..=A21 镜像公式**）+ footer R35 · "
    "R36 区标题`净值：` + 区③ R37-47 十一行（🔴 **A..O 全列 =x11-x24 逐格派生**）+ footer R48 / "
    "两区同形公式列 E=SUM(B:C)-D · L=B+F+G · M=C+H+J · N=D+I+K · O=L+M-N / "
    "有效内容列 17 即 A..Q / max_column 26 ⇒ UUID 放 R / **334 公式（全 I 最多）** / merged 8 / "
    "🔴 **definedName 334**（与 I4 476 构成「基线不增长」口径唯一实证场）/ 无 Excel Table / "
    "ws.protection.sheet=False ⇒ locked 全惰性）"
    " + 前端 `useI5Detail.ts` 按值 grep（ITEM_ID_ROWS='I5-2-rows' / 身份 rowId / "
    "🔴 removeRow(rowId) 的 isBuiltin 分支是**原位重置**不是真删（#L825-831），"
    "传入 emptyI5DetailRow 的 4 字段原本不含 rowId 而 #L305 `rowId: generateRowId()` ⇒ "
    "重置换身份；已双保险修复（#L826 传 rowId + 契约声明 projectName 为内置行事实主键）/ "
    "I5RollAmounts 的 15 字段 × gross|impairment 两个嵌套子对象 / "
    "🔴 宿主 GtI5OtherNoncurrentAssets.vue（289 行全 I 最短）**无任何 http/api import** ⇒ "
    "载体是 formdata_composable（全 I 唯一），变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 打红）"
    " + 真库现算（checklist_responses.item_id='I5-2-rows' **745 B 全 I 最大**，但 "
    "🔴 `rowId == 'e2e-i52-contract'` **不符 i52- 生成器格式、是 E2E 测试种子** ⇒ "
    "标 live_payload_is_e2e_seed_not_business_data，passthrough mode 未被业务数据证实，"
    "roundtrip 只能用合成载荷）"
    " + CD-3 三边校验（impl I5_BUILTIN_CATEGORIES **10 条** vs 源 `明细表I5-2!A11:A20` 真读 10 格，"
    "**有序等值 10/10** ⇒ MATCH/clean；边界 A21=`……` 可扩位 · A22=`合计`）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本批放 I5-2 的**两个区**（区③派生不接）；册内其余 8 个 sheet：
#   底稿目录 / 其他非流动资产实质性程序 I5A → 不接
#   审定表I5-1                            → 归后置（审定表族）
#   调整分录汇总I5-3                       → FC-6 默认 `single_html`
#   针对性检查表I5-4                       → 归后续批次
#   附注披露（上市公司 / 国有企业）          → 归附注披露族
#   GT_Custom（hidden）                    → 🔴 **不纳管**

#: 本批：明细表I5-2 的原值区 + 减值准备区（净值区是 fully_derived_region，不接）
_INCLUDE_I502_GROSS: Final[bool] = True
_INCLUDE_I502_IMPAIRMENT: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单。

    🔴 **两个 spec 共享同一 `store_item_id`** —— 这是「一行同时在三个区」形态的直接后果，
    不是重复声明。`all_store_item_ids()` 去重后仍只有一个 item。
    """
    specs: list[Any] = []
    if _INCLUDE_I502_GROSS:
        specs.append(_i502.SPEC_I502_GROSS)
    if _INCLUDE_I502_IMPAIRMENT:
        specs.append(_i502.SPEC_I502_IMPAIRMENT)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """🔴 两个 spec 共享一个 item ⇒ 去重后长度为 **1**（不是 2）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """I5-1 审定表 —— 归后置批次，本 spec 恒 None。"""
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    """🔴 两个 spec 在**同一张 sheet** 上 ⇒ 去重后长度为 **1**。"""
    names: list[str] = []
    for spec in managed_row_table_specs():
        if spec.managed_sheet not in names:
            names.append(spec.managed_sheet)
    return tuple(names)


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
            "audit-platform/frontend/src/components/workpaper/composables/useI5Detail.ts"
            " —— `_persist()` 写 { item_id: 'I5-2-rows', remark: JSON.stringify(rows) }；"
            "🔴 载体是 **formdata_composable**（useI5FormData.ts），宿主无 http/api import"
        ),
    )


def contract_file_path() -> Path:
    from app.services.workpaper_sync.contracts import contract_path_for

    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# 5. manifest capability
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 6. adapter 注册
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return HC.build_matcher(IDENTITY)


def build_registration(
    *, manifest: Mapping[str, Any] | None = None
) -> AdapterRegistration:
    return HC.build_registration(IDENTITY, manifest=manifest)


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> AdapterRegistration:
    return HC.register_adapter(IDENTITY, registry, manifest=manifest)


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach 本 entry 的 adapter（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 符号名必须是 `attach_pilot_adapters` —— `adapters/registry.py` 的 `_attach_of()`
    按这个**固定名字**从白名单模块里取（不是按 `register_adapter`），
    `test_registrar_delegates_to_each_entry_own_attach` 逐 provider 核它存在。

    🔴 第③环（published representation）缺供给时公共骨架**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
    """
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """读已发布的冻结身份（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 **薄委托**：函数体只有一条 `return await HC.<同名>(...)`。
    `test_task75_published_identity_observer` 的 `implementing_node()` 据此把四条判据
    转移到骨架那层执行（真 await 共享观测器 / 真做 contract digest 比对 / raise 在条件
    分支里 / 不返回 None）。这里**多写一条语句**就会被判为「provider 自有实现」，
    转而按严格判据核本函数 —— 那是故意的：借薄委托外壳偷塞逻辑必须打红。

    🔴 **不得**在本函数里抄 loader 九步（`ExcelEntryDefinitionLoader` /
    `assert_no_structure_drift` / `parse_identity_inventory` / `structure_fingerprint`）
    —— 抄一遍就是第二真源，任一侧被短路都不改变行为。
    """
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


# ═══════════════════════════════════════════════════════════════════════════
# ── 五环发布面（委托 HC，2026-10-01）
#
# 🔴 硬前置：`projection_provisioning.load_projection_supply()` 只认
#    `publish_pilot_definitions` + `PILOT_WP_CODES`；`projection_first_publication`
#    另要 `instrumentation_spec()`（单数 = 主表）与 `build_store_projection`。
#    实现全在 `phase5_h_cycle_common`，这里只写薄委托（与 J1 / L1 同形，不复制逻辑）。
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return HC.primary_instrumentation_spec(IDENTITY, managed_row_table_specs())


def build_store_projection(
    payload: Any,
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """🔴 `payload` 必须是首位位置参数（golden digest 门按此调用）。"""
    return HC.build_store_projection_for(
        IDENTITY,
        managed_row_table_specs(),
        payload,
        contract=contract,
        limits=limits,
        store_item_id=store_item_id,
    )


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list, store_item_id: str | None = None
) -> Any:
    return HC.merge_projection_into_store_rows_for(
        IDENTITY,
        managed_row_table_specs(),
        projection=projection,
        base_rows=base_rows,
        store_item_id=store_item_id,
    )


def iter_store_rows(payload: Any, *, store_item_id: str | None = None) -> Any:
    return HC.iter_store_rows_for(
        IDENTITY, managed_row_table_specs(), payload, store_item_id=store_item_id
    )


async def publish_definitions(publisher: Any) -> HC.HEntryDefinitions:
    return await HC.publish_h_entry_definitions(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
        contract_payload_builder=build_contract_payload,
    )


publish_pilot_definitions = publish_definitions

#: 首版发布 binding 装配读的两个 provider 常量（与 J1 / L1 同名）。🔴 必须有：
#: `ExcelInstrumentationSpec` 的字段名是 `uuid_col`，而 `projection_first_publication`
#: 按 `spec.uuid_column or provider.UUID_COL` 取 ⇒ 缺这个常量时 UUID 列解析为 None，
#: 首版发布炸在 `excel_entry_identity_inventory_invalid`（I6 实测）。
#: 多受管表（I5）时 `ROWS_TABLE_KEY` 指向主表，其余由 sibling binding 覆盖。
UUID_COL: Final[str] = instrumentation_spec().uuid_col
ROWS_TABLE_KEY: Final[str] = managed_row_table_specs()[0].table_key
PILOT_WP_CODES = WP_CODES
