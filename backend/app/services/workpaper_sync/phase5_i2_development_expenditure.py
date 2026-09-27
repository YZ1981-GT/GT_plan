# -*- coding: utf-8 -*-
"""I2 开发支出 —— Phase 5 entry 模块（I 循环第二条接入）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 17 / 18

═══ 🔴 I2 是 I 循环唯一「双例外」entry ═══

| 维度 | I2 | 其余 5 条 |
|---|---|---|
| 二级 UI 门控 | 🔴 **无**（`isOoAvailable` 与「仅结构化视图」tag 命中均 0） | 各有 2 / 1 |
| TB 发布门层级 | 🔴 **`host_tab`**（`I2TabAdjudication.vue#L384` 自建） | `composable` |
| 第二写路径 | 🔴 **有**（`useI2FormData.ts#L185` 的 `api.put`） | 无 |

三条含义：

1. 🔴 「I 循环 6/6 全有 TB 发布门」是 **entry 维度**成立的结论。判据若写成
   「composable 里必须有 `publishToTb`」，**I2 会假红** —— `useI2Adjudication.ts` 里
   那个符号 **0 命中**。判据必须按 entry 维度找门并记录 `gate_layer`。
2. 🔴 缺二级门控意味着 OO 探测失败时切换按钮**照样显示** ⇒ 违反 AC 1.5。
   判据若写「全 slice 都有二级门控」会在 I2 上**静默恒真**（找不到就跳过），恰好漏掉最严重那条。
3. 🔴 **第二写路径是活代码不是死代码**：`useI2FormData.ts`（501 行）import 生产消费现算 **4**
   （宿主 + `useI2Adjudication` + `useI2Impairment` + `i2/core/I2TabAdjudication.vue`）。
   对比 `useI4FormData.ts`（394 行）与 `useI6FormData.ts`（448 行）**双零消费**是死代码。
   ⇒ 三个文件名同型但只有 I2 那个是活的；一刀切「I 的 FormData 都是孤儿」会把 I2 的写路径删掉、
   保存静默失效。两条写路径打**同一端点、同一 item 形状** `{item_id, conclusion, remark}`，
   注册 adapter 后不应分叉。

═══ 🔴 主表键 `I2-2-rows` 是跨 lane 冻结键 ═══

`useI1AdditionCheck.ts#L250-251`（**lane 1 的 I1**）读它，读法 `?.remark ?? ?.conclusion`
⇒ ①不得改键名 ②不得在未通知 lane 1 的情况下改 payload 列语义。
另 `i2ConsistencyModel.ts#L213` 的前缀映射也依赖它 —— 改键名会同时打断一致性检查前缀表。

═══ IC-12：全 I 最严重的 wp_index 问题落在 I2 ═══

🔴 真库 wp_index 里 `I2-1` **一码两名两底稿**：`商誉减值测试`（×1，业务上属 **I3**）与
`开发支出审定表`（×3）⇒ 同一 wp_code 指**完全不同的底稿**（比 H 的 `H1-2` 同底稿不同名严重）。
⇒ 契约 `source_ref` 只用 `{workbook_sha256, sheet_name}`，**禁任何 wp_index 来源字段**。

═══ IC-5：CD-5 与 CD-6 同属 I2 但是两个 verdict ═══

* **CD-5**：I2 主表无 impl 分类常量 ⇒ `NO_IMPL_CLASSIFICATION_BY_DESIGN` / clean
* **CD-6**：`defaultPerCapitaPeers` ⇒ `HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF` /
  `scanned_and_classified_not_a_defect`（**不是缺陷**：它是「同业人均数」对照表的默认行数种子，
  模板里本来就没有对应分类区间 ⇒ 无真源是设计而非漏登记）

🔴 status 维度上 CD-5 计 clean、CD-6 计 classified_not_defect，**两者不相加**。

═══ 源模板真源断链（登记不修）═══

`明细表I2-2!A17` 是**字面** `数据资源`（不是 `=底稿目录!A18`）⇒ 改 `底稿目录!A18` 不传播到这里。
另 2 处同型在 I1（`附注披露信息（上市公司）!K10` 与 `明细表I1-2!A29`）⇒ 归 lane 1。
本轮**不改模板字节**（运行时只读 + sha 冻结）。

═══ IC-9：I2 册裸 IF **113 格** ⇒ per-file 挂中性化 ═══

按 `g7_oo_crash_if_neutralize._BARE_IF_CALL` 的 `findall` 口径现算 = **113**
（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，总 777）。
🔴 整册统一挂不行 —— 最重与最轻差 7 倍。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i2_02_detail as _i202
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

PHASE5_WAVE: Final[str] = "phase5_development_expenditure_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i2-development-expenditure"
ADAPTER_ID: Final[str] = "i2.development_expenditure_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"I2D"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I2 开发支出.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "a93c298b1f4adfe28532ba899a9e44904459534c703158a5b4e6d92ca4d67178"
)

STORE_ITEM_ID: Final[str] = _i202.STORE_ITEM_ID_I202
EMPTY_STORE_PAYLOAD: Final[str] = _i202.EMPTY_PAYLOAD_I202
ROW_IDENTITY_STORE_KEY: Final[str] = _i202.ROW_IDENTITY_STORE_KEY_I202

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 🔴 I2 的门在 `.vue` 自建，不在 composable（全 I 唯一）。
TB_PUBLISH_GATE: Final[str] = "i2/core/I2TabAdjudication.vue#L384"

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 IC-17 / 跨 lane：键名冻结（lane 1 的 I1 读它 + I2 自身一致性前缀表）
    "frozen_key": True,
    "frozen_reason": (
        "lane 1 的 useI1AdditionCheck.ts#L250-251 跨 entry 读它（remark 优先 / conclusion 兜底）；"
        "i2ConsistencyModel.ts#L213 的前缀映射 'I2-2-': ['I2-2-rows'] 也依赖它 ⇒ "
        "改键名会同时打断跨 lane 消费边与一致性检查前缀表。"
    ),
    "frozen_cross_ref": {_i202.STORE_ITEM_ID_I202: list(_i202.FROZEN_CROSS_REF_I202)},
    # 🔴 IC-16 / IE-8：两条例外
    "secondary_ui_gate": False,
    "secondary_ui_gate_note": (
        "全 I 唯一缺二级门控：宿主 isOoAvailable 与「仅结构化视图」tag 命中均 0 ⇒ "
        "OO 探测失败时切换按钮照样显示。判据写「全 slice 都有二级门控」会在本条上静默恒真。"
    ),
    "gate_layer": "host_tab",
    "gate_layer_note": (
        "全 I 唯一发布门不在 composable：useI2Adjudication.ts 里 publishToTb 0 命中，"
        "门在 I2TabAdjudication.vue#L384 自建 ⇒ 判据按 composable 找门会让本条假红。"
        "「I 循环 6/6 全有发布门」是 entry 维度成立的结论。"
    ),
    # 🔴 IE-1：第二写路径是活代码
    "second_write_path": "composables/useI2FormData.ts#L185",
    "second_write_path_note": (
        "501 行、import 生产消费现算 4（宿主 + useI2Adjudication + useI2Impairment + "
        "i2/core/I2TabAdjudication.vue）⇒ **活代码**。对比 useI4FormData(394 行) 与 "
        "useI6FormData(448 行) 双零消费是死代码 —— 三个文件名同型但只有本条是活的，"
        "一刀切会把 I2 的写路径删掉、保存静默失效。两条写路径打同一端点同一 item 形状。"
    ),
    # IC-2 载体族（I 循环二分，I2 属 host_inline 但多一条第二写路径）
    "carrier": {
        "write": "host_inline",
        "write_client": "http",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i2-development-expenditure",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "gate_layer": "host_tab",
        "mounts": 2,
        "host_checklist_get_hits": 0,
    },
    "oo_flags": {
        "legacyOO": 5,
        "http_import": 1,
        "isOoAvailable": 0,
        "structured_only_switch": 0,
    },
    # IC-5：两个 verdict 同属 I2，status 维度不相加
    "classification": {
        "impl_constant": None,
        "verdict": "NO_IMPL_CLASSIFICATION_BY_DESIGN",
        "status": "clean",
    },
    "classification_extra": {
        "impl_constant": "defaultPerCapitaPeers",
        "verdict": "HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF",
        "status": "scanned_and_classified_not_a_defect",
        "note": (
            "「同业人均数」对照表的默认行数种子，模板里本来就没有对应分类区间 ⇒ "
            "无真源是设计而非漏登记。🔴 与 CD-5 同属 I2 但是两个 verdict，status 维度不相加。"
        ),
    },
    # IC-12：全 I 最严重 wp_index 问题
    "wp_index_hazard": (
        "🔴 I2-1 一码两名两底稿：真库 wp_index 里同时对应 `商誉减值测试`（×1，业务上属 I3）"
        "与 `开发支出审定表`（×3）⇒ 契约 source_ref 只用 {workbook_sha256, sheet_name}，"
        "禁任何 wp_index 来源字段；变异「用 wp_index 的 I2-1 反查底稿」会取到 I3 的底稿。"
    ),
    # 源模板真源断链（登记不修）
    "template_source_break": [
        "明细表I2-2!A17 是字面「数据资源」（不是 =底稿目录!A18）⇒ 改 A18 不传播（不改模板字节）"
    ],
    # IC-6 在本 entry 命中 0（8 个位置化 site 全在 lane 1 的 I1/I3）—— 主动断言非漏扫
    "positional_identity_sites": [],
    "positional_identity_note": (
        "IC-6 在本 entry 现算 0 且不是漏扫（8 个 site 全在 lane 1 的 {I1, I3}）。"
        "按 IC-20 空分母纪律：断言「现算 0」但不宣称该维度通过。"
    ),
    # IC-13：footer 非单一形态
    "footer_shape_facts": dict(_i202.FOOTER_SHAPE_FACTS_I202),
    "store_only_fields": [],
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i202.TEMPLATE_ONLY_FORMULA_COLUMNS_I202
    ],
    "template_cell_lock_facts": dict(_i202.TEMPLATE_CELL_LOCK_FACTS_I202),
    "variant_axis": None,
    "effective_columns": _i202.EFFECTIVE_COLUMNS_I202,
    "max_column": _i202.MAX_COLUMN_I202,
    "uuid_column": _i202.UUID_COL_I202,
    "uuid_column_note": (
        "有效 20 + 1 = U。🔴 不得放 62 —— max_column 是 61，有效与 max 之间 41 列全空"
        "（全 I 差距最大），放 62 会让 OO 打开后列宽错位。"
    ),
    # IC-18：现算 2 个，禁写死
    "derived_total_keys": ["I2-1-audited-total", "I2-15-supplement-total"],
    "defined_name_baseline": 0,
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
    "I2 开发支出的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 13 个受管字段；7 个公式列（G/L/M/N/O/P/R）在 `I2DetailRow` 里虽有同名字段"
    "（unadjEnding / auditedOpening / … / diffVsIA）但都是**前端按同一套公式重算的派生值**"
    "（行类型注释逐条标了「公式 G = B+C-E-F」）⇒ 只进 formula_columns 不进 field_specs，"
    "formula_mask 保证 OO 侧不被 HTML 的派生值覆盖。"
    "🔴 `I2DetailRow` 另有 40+ 个 @deprecated 别名与跨 sheet 兼容字段（capBeginAmount / "
    "transferToI1 / auditedEnd 等）—— 它们**不进契约**（既非模板列亦非受管语义）。"
    "🔴 本 entry 有**第二写路径** `useI2FormData.ts#L185`（活代码，消费计数 4），"
    "两条写路径打同一端点同一 item 形状 ⇒ 注册 adapter 后不应分叉。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I2 开发支出.xlsx 的 `明细表I2-2`"
    "（🔴 **三级**表头 R10/R11/R12 ⇒ header_rows=3；各列 header_text 取该列最深非空标题"
    "（A/Q/S/T 在 R10 · B/G/H/I/L/M/P 在 R11 · C/D/E/F/J/K/N/O 在 R12，"
    "照「统一取 leaf 行」会让 12 列取到 None）/ 数据 R13-22 十行 / "
    "footer R23 合计（B..P 各 =SUM(x13:x22) 但 🔴 **R23 例外是 =P23-Q23** 套用行公式）/ "
    "公式列 G·L·M·N·O·P·R（G 与 P 是**减两项**口径 期初+增加−计入资产−计入损益，"
    "抄成「期初+增加−减少」会漏一个减项）/ 有效内容列 20 即 A..T / max_column 61"
    "（差 41 列全空，全 I 最大 ⇒ UUID 放 U 不放 62）/ 92 公式 / merged 21 / "
    "裸 IF 113（findall 口径）/ 0 个 definedName / 无 Excel Table / "
    "ws.protection.sheet=False ⇒ 数据行 locked 全惰性）"
    " + 前端 `useI2Detail.ts` 按值 grep（ITEM_ID_ROWS='I2-2-rows' / 身份字段 rowId / "
    "removeRow(index: number) 属**下标族** / I2DetailRow 的核心 13 字段 + 40+ deprecated 别名）"
    " + 真库现算（checklist_responses.item_id='I2-2-rows' **无行** ⇒ roundtrip 只能合成载荷）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本批只放 I2-2 一张；册内其余 20 个 sheet 的处置：
#   底稿目录 / 开发支出实质性程序I2A            → 不接
#   审定表I2-1                                 → 归后置（审定表族；🔴 wp_index 一码两底稿）
#   调整分录汇总I2-3                           → FC-6 默认 `single_html`
#   会计政策检查I2-4 / 实质性分析I2-5          → 归后续批次
#   研发项目资本化时点判断I2-6 / 构成明细I2-7   → 归后续批次
#   研发材料投入I2-8 / 人员认定I2-9 / 工时I2-10 → 归后续批次
#   委外研发I2-11 / 针对性检查I2-12            → 归后续批次
#   截止性测试 I2-13 / I2-14                   → 归后续批次
#   减值准备测试I2-15 / 可收回金额I2-16        → 归后续批次
#   附注披露（上市公司 / 国有企业）             → 归附注披露族
#   GT_Custom（hidden）                        → 🔴 **不纳管**

#: 本批：明细表I2-2
_INCLUDE_I202: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_I202:
        specs.append(_i202.SPEC_I202)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """I2-1 审定表 —— 归后置批次（🔴 且 wp_index 一码两底稿，定位须靠模板 sheet 全名）。"""
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
            "audit-platform/frontend/src/components/workpaper/composables/useI2Detail.ts"
            " —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'I2-2-rows', remark: JSON.stringify(rows) }；"
            "🔴 另有第二写路径 useI2FormData.ts#L185 的 api.put（活代码，同端点同 item 形状）"
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
