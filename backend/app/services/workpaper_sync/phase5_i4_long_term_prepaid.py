# -*- coding: utf-8 -*-
"""I4 长期待摊费用 —— Phase 5 entry 模块（I 循环第三条接入）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 17 / 18

═══ 🔴 I4 的两个「唯一」 ═══

| 维度 | I4 | 其余 5 条 |
|---|---|---|
| definedName | 🔴 **476**（全 I 最多） | I5 334 · I1/I2/I3/I6 全 0 |
| payload mode | 🔴 **`dual_write`**（slice 声明） | 其余 4 条 `remark_only` · I5 `passthrough` |

**definedName 的意义**：本册与 I5 是「**基线不增长**」口径的唯一实证场。
🔴 照抄 H 循环 HC-14 的「断言全 0」在 I1/I2/I3/I6 上恒真悄悄通过，**只有 I4/I5 会打红** ——
本条是捕获「照抄 H 口径」这个错误的地方。**不删这 476 个**（是模板公式的命名引用，
删了会让 `max_column` 内的公式整片失效），只声明「同步时不新增、不改写」。

**payload mode 的意义**：slice 记 `dual_write_remark_and_conclusion_for_status_marker`，
但真库 I 循环 **7 行全部 remark_only**（`conclusion` 全 NULL）⇒ 标 `unverified_in_live_db`，
🔴 **不得**把 slice 声明当已验证事实。`dual_write` 落地时须断言写 `conclusion` 列
**不破坏** `remark_only` 读侧（I2 的第二写路径与 lane 1 的 `useI1AdditionCheck` 都读 `conclusion` 兜底）。

═══ 🔴 BP-5：`useI4FormData.ts` 双零消费死代码，禁接不删 ═══

394 行，import 生产消费 **0** / import 测试消费 **0**（按 import 路径字面量三形态现算，
禁符号名 grep —— I 循环有 4 处注释链式提及 dual-mode composable，符号名口径会把注释当消费边）。

🔴 **对比 I2**：`useI2FormData.ts`（501 行）消费计数 **4** 是**活代码**（`_doSave` 内真 PUT
= I2 的第二写路径）。三个 FormData 文件名同型（i2/i4/i6）但**只有 I2 那个是活的** ——
一刀切「I 循环的 FormData composable 都是孤儿」会把 I2 的写路径删掉、保存静默失效。

⇒ 处置 = 契约 `forbidden_carriers` 禁接；🔴 **本轮不删文件**
（删除是跨 spec 清理动作，与并发会话有冲突风险；禁接已足够防误用）。

═══ 双区：R11-22 业务区 + R24-28 派生区（IC-19）═══

第 2 区 `R24「其中：」+ R25-28`（4 行）：A 列逐格 `=底稿目录!A9`..`A12`、
E..J 等列是 **ArrayFormula** 按 B 列类别回汇总第 1 区 ⇒ 标 `derived`、**不纳入业务行比对**。
🔴 允许用户改该区标签会被下次 render 从 `底稿目录` 静默覆盖。

═══ CD-8 = BP-8②：分类枚举 6 条对源 1 条 ═══

`CATEGORY_OPTIONS` **6 条** vs `明细表I4-2!A11` 真读**仅 1 条**（`使用权资产改良及维护支出`；
`A9`/`A10` 空 + `A12:A22` 全空）⇒ 无真源尾部 **3 条**
（`租入固定资产改良支出` / `固定资产大修理支出` / `开办费`）。
🔴 修法归**业务确认**（是否属长期待摊费用的合法分类是会计判断）⇒ 本轮登记不修。

═══ IC-9：I4 册裸 IF **186 格**（全 I 第二重）⇒ per-file 挂 ═══

I1 321 / **I4 186** / I2 113 / I3 63 / I5 49 / I6 45，总 777。整册统一挂不行（差 7 倍）。

═══ 删行 API：I4 属 **id 族**（与 I2 的下标族不同）═══

`useI4Detail.ts#L672 removeRow(rowId: string)` 先 `findIndex` 再 splice。
对比 I2 是 `removeRow(index: number)` 直接按下标 splice。
🔴 本 lane 是 **1:2 跨两族**（I2 index / I4+I5 identity），而 lane 1 两条 entry **100% 下标族**
⇒ 两个 lane **不得复用同一个签名断言**，否则一边必然假红或假绿。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i4_02_detail as _i402
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

PHASE5_WAVE: Final[str] = "phase5_long_term_prepaid_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i4-long-term-prepaid"
ADAPTER_ID: Final[str] = "i4.long_term_prepaid_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"I4L"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I4 长期待摊费用.xlsx"
#: 🔴 2026-10-01 净化（`sanitize_i_cycle_template_external_links.py`，过 OOXML 门）后现算；
#: 净化前 `8bfb85884705e47121589227d3212f3e406cab9b4ea6e0736d53b951c65eb8f8`（slice 冻结值，append-only 保留；`.preclean.bak` 即其字节）。
TEMPLATE_SHA256: Final[str] = (
    "94a5baab24adb2990678e9d1cf7a91f75f83ce34ebed7cf725634009dad81a8b"
)

STORE_ITEM_ID: Final[str] = _i402.STORE_ITEM_ID_I402
EMPTY_STORE_PAYLOAD: Final[str] = _i402.EMPTY_PAYLOAD_I402
ROW_IDENTITY_STORE_KEY: Final[str] = _i402.ROW_IDENTITY_STORE_KEY_I402

#: 🔴 slice 声明 `dual_write` 但真库 7 行全 remark_only ⇒ 契约标 unverified。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write"

TB_PUBLISH_GATE: Final[str] = (
    "composables/useI4Adjudication.ts#L371 + i4/core/I4TabAdjudication.vue#L634"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 IC-10：definedName 基线**非 0** —— 本册与 I5 是「基线不增长」口径的唯一实证场
    "defined_name_baseline": _i402.DEFINED_NAME_BASELINE_I402,
    "defined_name_baseline_note": (
        "🔴 **476 个**（全 I 最多；I5 334、其余四册全 0，合计 810）。判据 SHALL 用"
        "「登记基线 + 断言不增长」口径，**不得**照抄 H 循环 HC-14 的「断言全 0」—— "
        "那在 I1/I2/I3/I6 上恒真悄悄通过，**只有 I4/I5 会打红**。"
        "🔴 **不删这 476 个**：它们是模板公式的命名引用，删了会让 max_column 内的公式整片失效；"
        "只声明「同步时不新增、不改写」。"
    ),
    # 🔴 payload mode 未被真库证实
    "payload_column_mode_status": "unverified_in_live_db",
    "payload_column_mode_note": (
        "slice 记 dual_write_remark_and_conclusion_for_status_marker，但真库 I 循环 "
        "**7 行全部 remark_only**（conclusion 全 NULL）⇒ 该 mode 从未被真实数据走过。"
        "🔴 落地时须断言写 conclusion 列**不破坏** remark_only 读侧"
        "（I2 的第二写路径与 lane 1 的 useI1AdditionCheck 都读 conclusion 兜底）。"
    ),
    # 🔴 BP-5：双零消费死代码，禁接不删
    "forbidden_carriers": ["composables/useI4FormData.ts"],
    "forbidden_carriers_note": (
        "394 行、import 生产/测试消费**双零**（按 import 路径字面量三形态现算，禁符号名 grep）。"
        "🔴 **对比 I2**：useI2FormData.ts（501 行）消费计数 **4** 是活代码（_doSave 内真 PUT = "
        "I2 的第二写路径）—— 三个 FormData 文件名同型（i2/i4/i6）但**只有 I2 那个是活的**，"
        "一刀切「I 的 FormData 都是孤儿」会把 I2 的写路径删掉、保存静默失效。"
        "🔴 本轮**只禁接不删文件**（删除是跨 spec 清理动作，与并发会话有冲突风险）。"
    ),
    # 🔴 IC-19：双区，第 2 区派生不受管
    "regions": [
        {"idx": 0, "rows": [11, 22], "kind": "editable", "row_count": 12},
        {
            "idx": 1,
            "rows": list(_i402.DERIVED_REGION_I402["rows"]),
            "kind": "derived",
            "marker_row": _i402.DERIVED_REGION_I402["marker_row"],
            "marker_label": _i402.DERIVED_REGION_I402["marker_label"],
            "label_source": _i402.DERIVED_REGION_I402["label_source"],
            "editable_labels": False,
        },
    ],
    "derived_region_facts": dict(_i402.DERIVED_REGION_I402),
    # CD-8 = BP-8②
    "classification": dict(_i402.CLASSIFICATION_FACTS_I402),
    # IC-2 载体族（I4 属 host_inline，无第二写路径）
    "carrier": {
        "write": "host_inline",
        "write_client": "http",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i4-long-term-prepaid",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "gate_layer": "composable",
        "mounts": 2,
        "host_checklist_get_hits": 0,
        "second_write_path": None,
    },
    "oo_flags": {
        "legacyOO": 5,
        "http_import": 1,
        "isOoAvailable": 2,
        "structured_only_switch": 1,
    },
    # 🔴 IC-7：删行 API 属 **id 族**（与同 lane 的 I2 下标族不同）
    "row_delete_api": {
        "kind": "identity",
        "signature": "removeRow(rowId: string)",
        "site": "composables/useI4Detail.ts#L672",
        "note": (
            "先 findIndex 再 splice。🔴 本 lane 是 **1:2 跨两族**（I2 index / I4+I5 identity），"
            "而 lane 1 两条 entry **100% 下标族** ⇒ 两个 lane **不得复用同一个签名断言**。"
        ),
    },
    # IC-6 在本 entry 命中 0（8 个 site 全在 lane 1）—— 主动断言非漏扫
    "positional_identity_sites": [],
    "positional_identity_note": (
        "IC-6 在本 entry 现算 0 且不是漏扫（8 个 site 全在 lane 1 的 {I1, I3}）。"
        "按 IC-20 空分母纪律：断言「现算 0」但不宣称该维度通过。"
    ),
    "store_only_fields": [],
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i402.TEMPLATE_ONLY_FORMULA_COLUMNS_I402
    ],
    "template_cell_lock_facts": dict(_i402.TEMPLATE_CELL_LOCK_FACTS_I402),
    # IC-11：本册命中的 sheet 命名陷阱（禁 strip 括号）
    "sheet_name_traps": ["摊销测算表I4-7（工作量法）"],
    "variant_axis": None,
    "effective_columns": _i402.EFFECTIVE_COLUMNS_I402,
    "max_column": _i402.MAX_COLUMN_I402,
    "uuid_column": _i402.UUID_COL_I402,
    # IC-18：现算 0 个 ⇒ 按空分母纪律不宣称通过（IC-18 已裁 I3/I4/I5 皆 0 非漏扫）
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
    "I4 长期待摊费用的结构化 Tab 行数据存成 checklist_responses 的 JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 15 个受管字段；6 个公式列（J/O/P/Q/R/S）在 `I4DetailRow` 里虽有同名字段"
    "（unadjEnding / auditedOpening / … / auditedEnding）但都是**前端按同一套公式重算的派生值**"
    "⇒ 只进 formula_columns 不进 field_specs，formula_mask 保证 OO 侧不被覆盖。"
    "🔴 `I4DetailRow` 另有摊销政策族（amortizationMethod / totalMonths / elapsedMonths / "
    "accAmortization / monthlyAmortization / amortizationStartMonth / remainingMonths / "
    "amortizationProgress）与基础族（occurDate / accountCategory / contractNo / startDate / "
    "endDate / status）**模板本表无对应列** —— 它们属 `摊销测算I4-6` / `摊销测算表I4-7（工作量法）`"
    "两张后置 sheet，**不进本 sheet 契约**（Requirement 6.1 禁止无来源自造字段）。"
    "🔴 payload mode 声明 `dual_write` 但真库**未证实**（7 行全 remark_only）。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I4 长期待摊费用.xlsx 的 `明细表I4-2`"
    "（🔴 **三级**表头 R8/R9/R10 ⇒ header_rows=3；各列 header_text 取该列最深非空标题"
    "（A/B/C/D/E/T/U 在 R8 · F/G/J/K/L/O/P/S 在 R9 · H/I/M/N/Q/R 在 R10）/ "
    "数据 R11-22 十二行 / footer R23 合计（E..S 各 =SUM(x11:x22)，A/B/C/D/T/U 无合计）/ "
    "🔴 **第 2 区 R24「其中：」+ R25-28 四行是派生区**（A 列逐格 =底稿目录!A9..A12、"
    "E..J 等列是 **ArrayFormula** 按 B 列类别回汇总第 1 区）⇒ 标 derived 不纳入业务行比对 / "
    "公式列 J·O·P·Q·R·S（J 与 S 是**减两项**口径 期初+增加−本期摊销−其他减少）/ "
    "有效内容列 22 即 A..V / max_column 25 ⇒ UUID 放 W / 98 公式 / merged 27 / "
    "🔴 **definedName 476**（全 I 最多，与 I5 334 一起构成「基线不增长」口径的唯一实证场）/ "
    "裸 IF 186（findall 口径，全 I 第二重）/ 无 Excel Table / "
    "ws.protection.sheet=False ⇒ 数据行 locked 全惰性）"
    " + 前端 `useI4Detail.ts` 按值 grep（ITEM_ID_ROWS='I4-2-rows' / 身份字段 rowId / "
    "🔴 removeRow(rowId: string) 属 **id 族**，与同 lane 的 I2 下标族不同 ⇒ 两 lane 不得"
    "复用同一签名断言 / I4DetailRow 的核心 15 字段 + 摊销政策族与基础族（属后置 sheet 不进本契约）"
    "+ 40+ deprecated 别名）"
    " + 真库现算（checklist_responses.item_id='I4-2-rows' **无行** ⇒ roundtrip 只能合成载荷；"
    "且 dual_write mode 从未被真实数据走过）"
    " + CD-8 三边校验（impl CATEGORY_OPTIONS **6 条** vs 源 `明细表I4-2!A11` 真读**仅 1 条** "
    "`使用权资产改良及维护支出`，A9/A10 空 + A12:A22 全空 ⇒ 无真源尾部 3 条，修法归业务确认）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本批只放 I4-2 一张；册内其余 11 个 sheet 的处置：
#   底稿目录 / 长期待摊费用实质性程序 I4A       → 不接
#   审定表I4-1                                → 归后置（审定表族）
#   调整分录汇总I4-3                          → FC-6 默认 `single_html`
#   摊销政策检查表I4-4 / 针对性检查表I4-5      → 归后续批次
#   摊销测算I4-6 / 摊销测算表I4-7（工作量法）  → 归后续批次（🔴 后者禁 strip 括号）
#   附注披露（上市公司 / 国有企业）             → 归附注披露族
#   GT_Custom（hidden）                       → 🔴 **不纳管**

#: 本批：明细表I4-2
_INCLUDE_I402: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_I402:
        specs.append(_i402.SPEC_I402)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """I4-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
            "audit-platform/frontend/src/components/workpaper/composables/useI4Detail.ts"
            " —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'I4-2-rows', remark: JSON.stringify(rows) }；"
            "🔴 **禁接** useI4FormData.ts（394 行双零消费死代码）"
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
