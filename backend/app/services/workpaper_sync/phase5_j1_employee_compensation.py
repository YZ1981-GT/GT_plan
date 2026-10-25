# -*- coding: utf-8 -*-
"""J1 应付职工薪酬 —— Phase 5 entry 模块（J 循环 canary，唯一一条独立 entry）。

spec: `j-cycle-sync-foundation-and-first-canary` · Task 22

═══ 🔴 J 与 D~I 六轮的五处结构性差异 ═══

| 维度 | J | D~I |
|---|---|---|
| 载体族 | 🔴 **第三种 `shared_platform_persistence_adapter`** | host_inline / formdata_composable |
| write client | 🔴 **`api` from `@/services/apiProxy`** | `http` from `@/utils/http` |
| primary table | 🔴 **一表三键** `J1-2-detail-{shortTerm,postEmployment,severance}` | 一表一键 |
| 行身份 | 🔴 **`id`** | 多为 `rowId`（I6 例外也是 id） |
| canary 硬标准 | 🔴 **须改口径**（primary table 真库全空） | primary table 有载荷 |

═══ 🔴 JC-2：载体第三族 + 两条对照反证 ═══

写路径在 **`composables/workpaper/useChecklistPersistence.ts`**（平台共享持久化适配器），
client 是 🔴 **`api` from `@/services/apiProxy`**（不是 `http` from `@/utils/http`），
statement 消费边现算 **23**。

🔴 **反证①**：按 H 的「载体里必须有 `http.put`」去核 SHALL 在本适配器上**假红**（它用 `api.put`）
🔴 **反证②**：按 I 的「宿主必须 import `@/utils/http`」去核 SHALL 在 J1 宿主上**假红**
（现算宿主 `@/utils/http` 与 `apiProxy` 命中**均为 0**）

⇒ 判据 SHALL 按 entry 声明的 `write_client` 名字去找 `{client}.put(`，不写死 `http`。

═══ 🔴 JC-3：写路径按端点字面量判定，禁按函数名 ═══

现算六类端点：

| # | 端点 | 文件数 | 性质 |
|---|---|---|---|
| ① | `PUT /api/workpapers/{wpId}/checklist-responses` | **13** | 主写路径 |
| ② | `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` | **1** | 🔴 **TB 发布门** |
| ③ | `POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper` | **4** | 写**另一张表** |
| ④ | `POST /api/workpapers/{wpId}/ai/generate-text` | **16** | AI 生成（**非持久化**） |

🔴 **非空反证**：符号名 `publishToTb` 在全 J 域命中 **0**，而端点 `publish-to-tb` 命中 **2**
（同一文件 `j1/core/J1TabAdjudication.vue` 内两处）——
「**按函数名判定得 0、按端点判定得 1 个文件**」是本条判据存在的全部理由。

⇒ **GC-9 在 J 是 1/1 有门**（推翻「J 无发布门」的误判），canary **可以**覆盖发布链。

═══ 🔴 JC-4 / BP-11：一表三键 + 键真源 4 文件 5 处 ═══

`J1-2-detail-{shortTerm, postEmployment, severance}` 由
`useJ1Detail.ts` 的 `STORAGE_KEY_PREFIX = 'J1-2-detail-'` + `storageKey()` 派生，
section 取自 `J1_SECTIONS[].key`（三值）。

🔴 **键真源实际是 4 文件 5 处声明**（slice 只记「两份」）：
①`useJ1Detail.ts` 前缀派生（**写方**）②`useJ1Adjudication.ts` 的 `J1_DETAIL_SECTION_KEYS`
三字面量 ③`J1TabAccrualCheck.vue` 的 `DETAIL_KEYS` 三字面量 ④`J1TabAllocationCheck.vue`
的 `DETAIL_KEYS` ⑤`useJ1DisclosureSections.ts` 三处 `readJson('J1-2-detail-…')` 内联
⇒ 判据 SHALL **五处同时比对**；变异「只改前缀」SHALL 打红。

🔴 **本 canary 不接 `J1-2-detail-*`**（真库三键全空，不满足硬标准）—— 它们归后续批次。

═══ canary = `J1-6-short-term`（硬标准改口径，详见 sheet spec docstring）═══

真库 **3473 B 全 J 最大**，但**金额字段全 0**（骨架已落库、业务未填）⇒
roundtrip 第一轮只验结构、第二轮须合成带金额载荷验 `G=ROUND(D*F,2)` 与 `I=G-H`。

🔴 **本 sheet 无 footer 合计行**（`footer_rows: []`）——
R36 是模板预留的第 20 行（只有 G/I 公式、A36 无标签），R37 已是第二分区标题。
判据按 **A 列非空**判业务行，🔴 **不得**套 `明细表J1-2 ` 的「B 列 + 三 footer」口径。

═══ 🔴 JC-10：sheet 名禁 strip 任何空格 ═══

本册三类空格：**尾部空格 2 张**（`审定表J1-1 ` / `明细表J1-2 `）·
**名中空格 3 张**（`应付职工薪酬实质性程序表 J1A` 等）·
🔴 **跨 sheet 引用里带空格且单引号包裹**（`审定表J1-1 !B8 = ='明细表J1-2 '!C13`）。

⇒ 重写公式时 SHALL 保留空格与单引号；变异「strip 后匹配」SHALL 打红。
🔴 本 canary 的 `计提情况检查表J1-6` **无空格**，但同册其他 sheet 有 ⇒ 契约仍须登记该陷阱。

═══ 🔴 JC-11：`J1-10` 一码两义（须带 visible 过滤）═══

`J1-10` → `辞退福利检查表J1-10`（**visible**, 48 行）+ `股份支付检查表J1-10-删除`（hidden, 66 行）
—— 两张**完全不同业务**的表，不是版本变体。
⇒ 按 sheet 尾码定位 SHALL 带 **visible 过滤**；变异「只按尾码匹配」SHALL 取到两张而打红。

另 `J1A` → `应付职工薪酬实质性程序表 J1A`(visible) + `…J1A-原版`(hidden) 是版本变体。

═══ 🔴 JC-17：J 循环完全自闭 + 端点跨循环复用 1 处 ═══

两侧都验：①J 的键无一个被非 J 路径文件消费 ②J 文件里无任何非 J 循环的键字面量
⇒ **HC-8 / IC-17 的跨循环键冻结在 J 不命中**（重大简化：改键名无跨循环风险）。

🔴 **但端点跨循环复用 1 处**：`composables/workpaper/j1/useJ1VoucherOcr.ts` 调
**D4 的** `POST /api/workpapers/{wpId}/d4/contract-ocr` ⇒ 冻结对象从「键」换成「**端点**」。
这也让 **FC-8 在 J 命中**（不是不适用）—— 宿主层 `ocr` 命中 0 成立，但 composable 层有真 OCR 调用。

═══ IC-9 同源：J1 册裸 IF **224** ⇒ per-file 挂，但本 sheet 是 0 ═══

整册 224（`审定表J1-1 ` 56 / `与同行业对比分析表J1-5` 60 / `月度分析表J1-4` 16 等），
🔴 **本 canary sheet 裸 IF 为 0** —— 但中性化是 per-file（整册就地改写 substrate 副本）
⇒ 即使受管表干净也必须挂。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_j1_06_accrual_check as _j106
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.models import AuthorityModel, BundleSlot, DefinitionKind

PHASE5_WAVE: Final[str] = "phase5_accrual_check_short_term"
ENTRY_ID: Final[str] = "xlsx/j1/gt-j1-employee-compensation"
ADAPTER_ID: Final[str] = "j1.accrual_check_short_term"

WP_CODES: Final[frozenset[str]] = frozenset({"J1E"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "J/J1 应付职工薪酬.xlsx"
#: 🔴 2026-10-01 净化后的哨兵（`scripts/fix/sanitize_j1_template_external_links.py`，D3~D7 同款）：
#:    删 2 个孤儿外链（旧作者本机路径）+ hidden 串册 sheet `…L1A-原` 6 格 `[2]` 公式转缓存值 +
#:    1 个 `[n]` defined name；受管 sheet 逐格 0 diff。净化前 `a6100d91…6061`/196,750 B
#:    （slice 冻结值，append-only 保留）被首版发布 OOXML `external_relationships` 门拒绝。
TEMPLATE_SHA256: Final[str] = (
    "6830eda60b73a7f14adc336e9a9e3610deee6ce5c24b983e78fab822cfb4c8ce"
)
#: 净化前哨兵（slice / 历史已发布 definition 引用的是它）。
PRE_SANITIZE_TEMPLATE_SHA256: Final[str] = (
    "a6100d91202f4d066dc39fb00e3016ea87794489bb75d308fec2733e92ca6061"
)

STORE_ITEM_ID: Final[str] = _j106.STORE_ITEM_ID_J106
EMPTY_STORE_PAYLOAD: Final[str] = _j106.EMPTY_PAYLOAD_J106
ROW_IDENTITY_STORE_KEY: Final[str] = _j106.ROW_IDENTITY_STORE_KEY_J106

#: 🔴 真库 J 前缀 83 行 `conclusion` **全 NULL**。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 🔴 按**端点**判定（符号名 publishToTb 全 J 域 0 命中）。
TB_PUBLISH_GATE: Final[str] = (
    "POST /api/workpapers/{wpId}/audit-determination/publish-to-tb"
    " @ j1/core/J1TabAdjudication.vue"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 JC-2：载体第三族 + 两条对照反证
    "carrier": {
        "write": "shared_platform_persistence_adapter",
        "write_module": "composables/workpaper/useChecklistPersistence.ts",
        "write_client": "api",
        "write_client_import": "@/services/apiProxy",
        "write_endpoint": "PUT /api/workpapers/{wpId}/checklist-responses",
        "read": "host_inline_render_config_refetch",
        "mounts": 1,
        "force_component_type": "j1-employee-compensation",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "host_has_http_import": False,
        "host_has_apiproxy_import": False,
        "host_line_count": 259,
        "statement_edges": 23,
    },
    "carrier_reverse_assertions": (
        "🔴 **反证①**：按 H 的「载体里必须有 `http.put`」去核 SHALL 在 "
        "`useChecklistPersistence` 上**假红**（它用 `api.put`）。"
        "🔴 **反证②**：按 I 的「宿主必须 import `@/utils/http`」去核 SHALL 在 J1 宿主上**假红** "
        "—— 现算宿主 `@/utils/http` 与 `apiProxy` 命中**均为 0**（259 行宿主零 client import）。"
        "⇒ 判据 SHALL 按 entry 声明的 `write_client` 名字去找 `{client}.put(`，不写死 `http`。"
    ),
    # 🔴 JC-3：六类端点 + 发布门非空反证
    "endpoint_inventory": {
        "checklist_responses_put": 13,
        "publish_to_tb_post": 1,
        "disclosure_notes_sync_post": 4,
        "ai_generate_text_post": 16,
    },
    "tb_gate_symbol_vs_endpoint": {
        "symbol_name_hit_count": 0,
        "endpoint_hit_count": 2,
        "endpoint_real_call_count": 1,
        "endpoint_comment_count": 1,
        "endpoint_file_count": 1,
        "real_call_site": "j1/core/J1TabAdjudication.vue#L446",
        "confirm_gate_site": "j1/core/J1TabAdjudication.vue#L434 `ElMessageBox.confirm`",
        "note": (
            "🔴 **非空反证**：符号名 `publishToTb` 在全 J 域命中 **0**，而端点 `publish-to-tb` "
            "命中 **2**，均在 `j1/core/J1TabAdjudication.vue`——「按函数名判定得 0、"
            "按端点判定得 1 个文件」是本条判据存在的**全部理由**。"
            "🔴 **精度更正（2026-09-27 逐行实测）**：2 处命中里 **1 处是注释**（#L425 的 spec "
            "溯源注释）、**1 处是真调用**（#L446 `api.post(...)`）⇒ 真实发布站点 **1 个**。"
            "判据 SHALL **先剥注释再匹配**（平台既有守卫 `check_tb_publish_confirm_gate` 正是"
            "先 `strip_comments` 再跑 `PUBLISH_CALL_RE`），否则会把注释数成发布站点。"
            "⇒ **GC-9 在 J 是 1/1 有门**（推翻「J 无发布门」的误判），canary 可以覆盖发布链。"
        ),
        "ci_gate_verified": (
            "✅ 平台既有 2 道 CI 守卫现算通过（扫 5190 源文件，0 违规）："
            "`check_tb_writeback_no_direct_call`（前端零 TB 回写直调）+ "
            "`check_tb_publish_confirm_gate`（发布全经显式确认门、无自动发布路径）。"
            "🔴 **非空反证已做**：J1 的真调用 #L446 被 `PUBLISH_CALL_RE` 覆盖"
            "（`.post(` + 反引号串 + `audit-determination/publish-to-tb`），同文件 #L434 "
            "有 `ElMessageBox.confirm` 被 `CONFIRM_RE` 覆盖 ⇒ 判为 confirmed 而非空分母。"
        ),
    },
    #: 🔴 诚实登记：前端传的 sheet_name 缺尾部空格，但**对本端点无害**（不虚报）。
    "sheet_name_arg_missing_trailing_space": {
        "site": "j1/core/J1TabAdjudication.vue#L448 `sheet_name: '审定表J1-1'`",
        "template_true_name": "审定表J1-1 ",
        "harmful_here": False,
        "why_harmless": (
            "🔴 端点 `publish_determination_to_tb` 只用 "
            "`extract_determination_wp_code(body.sheet_name)` 按正则 `[D-N]\\d+-1` **提子码**，"
            "**不**做 sheet 名精确匹配 ⇒ 从 `审定表J1-1` 能正确提出 `J1-1`。"
            "🔴 **不得报成缺陷**（虚报与漏报同罪）—— 只登记为「若将来有人拿它去定位模板 sheet "
            "则会失配」的潜在风险点。"
        ),
        "contrast": (
            "🔴 对照：`prefill_formula_mapping.json` 里同样的 `sheet: '审定表J1-1'` **是真缺陷** "
            "—— 那边的守卫（如 `test_i_cycle_formula_presets.py` 同族）按 sheet 名**精确匹配模板**。"
            "同一个字符串在两处消费方式不同 ⇒ 判据必须看消费方，不能只看字面。"
        ),
    },
    # 🔴 JC-4 / BP-11：一表三键 + 键真源 4 文件 5 处（本 canary 不接）
    "primary_table_three_keys": {
        "keys": [
            "J1-2-detail-shortTerm",
            "J1-2-detail-postEmployment",
            "J1-2-detail-severance",
        ],
        "derivation": (
            "`useJ1Detail.ts` 的 `STORAGE_KEY_PREFIX = 'J1-2-detail-'` + `storageKey()` 派生，"
            "section 取自 `J1_SECTIONS[].key`（三值）"
        ),
        "live_db_rows": 0,
        "managed_in_this_batch": False,
        "source_declarations_count": 5,
        "source_declarations_files": 4,
        "source_declarations": [
            "useJ1Detail.ts 前缀派生（**写方**）",
            "useJ1Adjudication.ts 的 J1_DETAIL_SECTION_KEYS 三字面量",
            "J1TabAccrualCheck.vue 的 DETAIL_KEYS 三字面量",
            "J1TabAllocationCheck.vue 的 DETAIL_KEYS",
            "useJ1DisclosureSections.ts 三处 readJson('J1-2-detail-…') 内联",
        ],
        "note": (
            "🔴 **BP-11 实际是 4 文件 5 处声明**（slice 只记「两份」）⇒ 判据 SHALL "
            "**五处同时比对**；变异「只改前缀」SHALL 打红。"
            "🔴 **本 canary 不接这三键**（真库全空，不满足改口径后的硬标准）⇒ 归后续批次。"
        ),
    },
    # 🔴 canary 硬标准改口径
    "canary_standard_revision": {
        "d_to_i_standard": "primary managed table 真库有非空载荷",
        "why_broken_in_j": (
            "J1-2-detail-* 三键 + J1-1-rows（审定表）+ J1-3-adjustment-rows（调整分录）"
            "真库**全部无行**"
        ),
        "revised_standard": "真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组",
        "chosen": "J1-6-short-term（3473 B 全 J 最大）",
        "rejected": {
            "J1-disc-soe-short-term": (
                "1325 B **且有真金额**，但披露层叠 5 个最难形态（双变体 / 49 硬编码 id / "
                "**同 id 跨变体语义不同**（SOE `st-7`=其他 vs Listed `st-7`=住房公积金）/ "
                "第三条写路径写**另一张表** / 与明细表**非行对行映射** 12 行←20 行）"
            ),
            "J1-8-voucher-check": (
                "911 B 且 id 形态 `j1vc-imp-credit-1` 真实，但属 **parent_duplicate**"
                "（`xlsx/j1/inspection/j1-tab-general-check`）⇒ 不独立发布 "
                "contract / bundle / candidate / evidence"
            ),
            "J1-2-detail-*": "primary managed table 真库空（0 行）",
        },
    },
    "live_payload_facts": dict(_j106.LIVE_PAYLOAD_FACTS_J106),
    # 🔴 sibling shape 三值
    "sibling_shapes": dict(_j106.SIBLING_SHAPES_J106),
    "sibling_shapes_note": _j106.SIBLING_SHAPES_NOTE_J106,
    # 🔴 无 footer
    "no_footer_facts": dict(_j106.NO_FOOTER_FACTS_J106),
    # 🔴 RD-5 三边校验缺口（canary 前置已补）
    "rd5_diff_facts": dict(_j106.RD5_DIFF_FACTS_J106),
    # 🔴 JC-10：sheet 名禁 strip
    "sheet_name_traps": [
        "🔴 **尾部空格 2 张**：`审定表J1-1 ` · `明细表J1-2 `",
        "🔴 **名中空格 3 张**：`应付职工薪酬实质性程序表 J1A` · `…J1A-原版` · `…L1A-原`",
        "🔴 **跨 sheet 引用里带空格且单引号包裹**：`审定表J1-1 !B8 = ='明细表J1-2 '!C13` "
        "⇒ 重写公式时 SHALL 保留空格与单引号；变异「strip 后匹配」SHALL 打红",
        "本 canary 的 `计提情况检查表J1-6` **无空格**，但同册其他 sheet 有 ⇒ 契约仍须登记",
    ],
    # 🔴 JC-11：一码两义
    "variant_axis": None,
    "code_collision_facts": {
        "J1-10": {
            "visible": "辞退福利检查表J1-10（48 行）",
            "hidden": "股份支付检查表J1-10-删除（66 行）",
            "kind": "🔴 **一码两义**（两张完全不同业务的表，不是版本变体）",
            "requirement": (
                "按 sheet 尾码定位 SHALL 带 **visible 过滤**；"
                "变异「只按尾码匹配」SHALL 取到两张而打红"
            ),
        },
        "J1A": {
            "visible": "应付职工薪酬实质性程序表 J1A",
            "hidden": "应付职工薪酬实质性程序表 J1A-原版",
            "kind": "版本变体",
        },
    },
    # 🔴 JC-17：完全自闭 + 端点跨循环复用
    "cross_cycle_facts": {
        "key_isolation": "🔴 **J 循环完全自闭** —— J 的键无一个被非 J 路径消费 ∧ J 文件里无非 J 键",
        "consequence": "⇒ **HC-8 / IC-17 的跨循环键冻结在 J 不命中**（改键名无跨循环风险）",
        "endpoint_reuse": [
            "🔴 `composables/workpaper/j1/useJ1VoucherOcr.ts` 调 **D4 的** "
            "`POST /api/workpapers/{wpId}/d4/contract-ocr` ⇒ 冻结对象从「键」换成「**端点**」"
        ],
        "fc8_verdict": (
            "🔴 **FC-8 在 J 命中**（不是不适用）—— 宿主层 `ocr` 命中 0 成立，但 composable 层"
            "有真 OCR 调用 ⇒ 判据扫描范围 SHALL 含 composable 层"
        ),
    },
    # 跨循环程序表串册（登记不修）
    "cross_cycle_template_bleed": [
        "🔴 `应付职工薪酬实质性程序表 L1A-原`（本册，hidden）—— 是 **L 循环**的程序表串在 J 册里"
        "（slice 漏记）",
        "`长期应付职工薪酬实质性程序表 L2A`（J2 册，hidden）—— 同型",
    ],
    "retired_sheets_count": 7,
    "retired_sheets_all_hidden": True,
    "business_sheet_count": 15,
    "sheet_count_check": "23 = 业务 15 + retired 7 + GT_Custom 1（四向等值比对）",
    "store_only_fields": ["indent"],
    "store_only_note": (
        "`indent` 是**缩进层级字段**（0/1）—— 模板用**全角空格前缀**表达缩进（见 RD-5 类②），"
        "HTML 侧用独立字段 ⇒ store-only、不映射格。"
    ),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _j106.TEMPLATE_ONLY_FORMULA_COLUMNS_J106
    ],
    "template_cell_lock_facts": dict(_j106.TEMPLATE_CELL_LOCK_FACTS_J106),
    "effective_columns": _j106.EFFECTIVE_COLUMNS_J106,
    "max_column": _j106.MAX_COLUMN_J106,
    "uuid_column": _j106.UUID_COL_J106,
    "bare_if_workbook": 224,
    "bare_if_this_sheet": 0,
    "bare_if_note": (
        "🔴 整册 **224**（`审定表J1-1 ` 56 / `与同行业对比分析表J1-5` 60 / `月度分析表J1-4` 16 等），"
        "但**本 canary sheet 为 0** —— 中性化是 per-file（整册就地改写 substrate 副本）"
        "⇒ 即使受管表干净也必须挂。"
    ),
    "defined_name_baseline": 0,
    "defined_name_baseline_note": (
        "J1 册 **0**；🔴 但 J2 **37**（断链 30）/ J3 **502**（断链 479，是跨循环复制残留 "
        "`_1固定资产数据库_筛选打印` / `_.dbf` / `AS2DocOpenMode` 等）⇒ 判据须用"
        "「基线不增长」口径，且 J2/J3 的处置归下游 lane（**不删** —— 删会让公式整片失效）。"
    ),
    "derived_total_keys": [
        "J1-1-audited-total",
        "J1-1-audited-begin-total",
        "J1-7-total-admin-expense",
        "J1-7-total-production-cost",
        "J1-7-total-selling-expense",
    ],
    "derived_total_keys_note": (
        "🔴 J1 侧现算 **5 个**（另 `J2-listed-summary` / `J2-soe-summary` 属 J2，归下游 lane）。"
        "🔴 正则 SHALL 覆盖 **`-total-` 出现在中间**的形态 —— 只写 `total$` 会漏 "
        "`J1-7-total-*` 三个。禁写死阈值。"
    ),
    "positional_identity_sites": [],
    "positional_identity_note": (
        "本 canary sheet 的行身份是 `AccrualRow.id`（`acr-{ts}-{i}-{rnd}` 属安全族）。"
        "🔴 J 循环的 family_a（纯序号真落库）唯一一处是 `J2TabAdjustment` 的 `id: i + 1` → "
        "`J2-3-entries`（真库 171 B 载荷里 `\"id\":1` **已确证落库**）⇒ 归下游 lane。"
        "🔴 披露层另有 **49 个硬编码序号 id**（SOE 25 + Listed 24）—— **登记但不判为位置化缺陷**"
        "（id 与 label 写在**同一个对象字面量**里，绑定静态不随数组顺序变；报成位置化会造 49 个假缺陷）。"
    ),
    "prefill_defects": [
        "🔴 `sheet: '审定表J1-1'` **缺尾部空格**（模板真名 `审定表J1-1 `）⇒ 按名定位必失配",
        "🔴 `sheet: '明细表J1-2 '` 那条 `cells: []` **空数组** = 死配置",
        "🔴 `=PREV('J1','分析程序J1-3','审定数')` 引用的 `分析程序J1-3` **在模板 23 张 sheet 里不存在**",
        "🔴 J3 一条 `wp_name: '股份支付审定表'` 但 **J3 册没有审定表**（6 张 sheet 里无 `审定表J3-*`）",
    ],
    "prefill_defects_note": (
        "四处均**登记不修**（prefill 配置属另一条产品链路）；本 spec 只交付判据 + 登记。"
        "J 的 prefill mapping 现算 **10 条**，字段名是 **`sheet`** 不是 `sheet_name`，"
        "全部 `cells` 型 / `items` 全 0；`wp_code` 只 `J1`/`J2`/`J3` 三值（非子码）。"
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
    "J1 应付职工薪酬的结构化行数据存成 checklist_responses 的 **remark** JSON 数组"
    "（🔴 真库 J 前缀 83 行 `conclusion` 列**全 NULL**）。本契约按 stable field + 行身份 "
    "`id` 拆开。"
    "🔴 **载体是平台第三种族 `shared_platform_persistence_adapter`** —— 写路径在 "
    "`composables/workpaper/useChecklistPersistence.ts`，client 是 **`api` from "
    "`@/services/apiProxy`**（不是 `http` from `@/utils/http`）；J1 宿主 259 行里"
    "两种 client import **命中均为 0** ⇒ 判据按 entry 声明的 `write_client` 找 "
    "`{client}.put(`，不写死 `http`。"
    "🔴 **8 个受管字段 / 2 个公式列**（G=ROUND(D*F,2) 应提金额 · I=G-H 差异）—— "
    "`AccrualRow` 里虽有 `estimated`/`diff` 同名字段但都是前端按同一套公式重算的派生值 "
    "⇒ 只进 formula_columns 不进 field_specs。"
    "🔴 **同 Tab 三兄弟键 shape 三值不同**：`J1-6-short-term`/`J1-6-post-employment` 是 "
    "`structured_row_array`、`J1-6-questions` 是 **`free_text_array`**（真库 901 B 是 AI 生成 "
    "markdown 长文本，5 元素字符串数组，首元素含 `###` 标题与列表）、`J1-6-conclusion` 是 "
    "`free_text_scalar` ⇒ 按行数组解析后两者会失败。"
    "唯一 store-only 字段 `indent` 是缩进层级（0/1）—— 模板用**全角空格前缀**表达缩进"
    "（RD-5 类②），HTML 侧用独立字段 ⇒ 不映射格。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 J/J1 应付职工薪酬.xlsx 的 `计提情况检查表J1-6`"
    "（🔴 **两级**表头 R15/R16 ⇒ header_rows=**2**（R15 是 项目/计提基数/计提比例/应提金额/"
    "实际计提数/差异/差异原因/结论，R16 只有 C=名称 / D=金额 / E=索引 三个「计提基数」子列）/ "
    "分区标题行 R14 `（1）短期薪酬` / 数据 **R17-R35（19 行）** / "
    "🔴 **`footer_rows: []` 本 sheet 无 footer 合计行** —— R36 只有 G36=`=ROUND(D36*F36,2)` 与 "
    "I36=`=G36-H36` 两个公式但 **A36 无标签**，R37 已是第二分区标题 "
    "`（2）离职后福利中设定提存计划…` ⇒ R36 是**模板预留的第 20 行**；引擎 dataclass 必填 "
    "footer_row ⇒ 给 36 并在契约显式声明 footer_rows=[] + "
    "footer_carries_total_formula=False，判据 SHALL 断言该行无 `合计` 标签 / "
    "🔴 判业务行按 **A 列非空**，**不得**套 `明细表J1-2 ` 的「B 列 + 三 footer」口径 / "
    "**2 个公式列** G·I（全 19 行同形 `=ROUND(D{r}*F{r},2)` / `=G{r}-H{r}`）/ "
    "有效内容列 **11 即 A..K** 且 max_column **也是 11**（两者相等）⇒ UUID 放 L / "
    "63 公式 / merged 17 / definedName **0** / 🔴 **本 sheet 裸 IF 为 0**（整册 J1 是 **224**"
    " —— `审定表J1-1 ` 56 / `与同行业对比分析表J1-5` 60 / `月度分析表J1-4` 16 等；"
    "中性化是 per-file 就地改写 substrate 副本 ⇒ 即使受管表干净也必须挂）/ "
    "无 Excel Table / ws.protection.sheet=False ⇒ locked 全惰性）"
    " + 前端 `j1/inspection/J1TabAccrualCheck.vue` 按值 grep"
    "（item_id 四值 J1-6-short-term / -post-employment / -questions / -conclusion；"
    "`AccrualRow` = id/label/indent + baseName/baseAmount/baseIndex + rate/estimated/actual"
    " + diff/diffReason/conclusion；身份字段 **`id`** 形态 `acr-{ts}-{i}-{rnd}` 属安全族）"
    " + 🔴 **RD-5 本轮新登记**（`SHORT_TERM_DEFAULTS` **19 项** vs 模板 `A17:A35` **19 格**："
    "行数一致但**内容 10 处不等**，三类分开记 —— ①序号分隔符 **9 处**（模板全角 `．` U+FF0E / "
    "impl 半角 `.`）②缩进前缀 **9 处**（模板带 3 个全角空格 `\\u3000` / impl 靠 `indent: 1` "
    "字段表达）③🔴 **单元格内换行符 1 处**（模板 `八、辞退福利\\n（因解除劳动关系给予的补偿）` / "
    "impl 写成一行）；🔴 **禁标点归一化** —— `NFKC` 会同时洗掉 RD-2 的 5 处与本条的 9 处 ⇒ "
    "逐格**字节**比对；修哪一侧属业务判断 ⇒ 登记不修，`header_text` 取**模板原字节**）"
    " + 🔴 **canary 硬标准改口径**（D~I 的「primary managed table 真库有非空载荷」在 J **不成立** "
    "—— `J1-2-detail-{shortTerm,postEmployment,severance}` 三键 + `J1-1-rows` + "
    "`J1-3-adjustment-rows` 真库**全部无行** ⇒ 改「真库有非空载荷 + 在 entry 内 + "
    "非 parent_duplicate + 单 sheet 单键组」四项；`J1-6-short-term` 真库 **3473 B 全 J 最大**"
    "且满足其余三项）"
    " + 🔴 **三条逆风如实登记**（①3473 B 载荷的**金额字段全 0**（baseAmount/rate/estimated/"
    "actual/diff 全 0，baseName/baseIndex/diffReason/conclusion 全空串）= 「骨架已落库、"
    "业务未填」⇒ roundtrip 第一轮只验结构、第二轮须合成带金额载荷验两个公式 "
    "②RD-5 三边校验缺口须在 canary 内先补 ③同 Tab `J1-6-questions` 901 B 是自由文本 shape）"
    " + 🔴 **JC-3 非空反证**（符号名 `publishToTb` 全 J 域命中 **0**，端点 `publish-to-tb` "
    "命中 **2**（同一文件 `j1/core/J1TabAdjudication.vue` 内两处）⇒ **GC-9 在 J 是 1/1 有门**，"
    "推翻「J 无发布门」误判，canary 可覆盖发布链）"
    " + 🔴 **BP-11 键真源实际 4 文件 5 处**（slice 只记两份）⇒ 判据五处同时比对"
    " + 🔴 **JC-17 J 循环完全自闭**（两侧都验：J 键无一个被非 J 路径消费 ∧ J 文件里无非 J 键）"
    "⇒ HC-8/IC-17 的跨循环键冻结在 J **不命中**；🔴 **但端点跨循环复用 1 处** —— "
    "`useJ1VoucherOcr.ts` 调 **D4 的** `POST /api/workpapers/{wpId}/d4/contract-ocr` "
    "⇒ 冻结对象从「键」换成「**端点**」，且 **FC-8 在 J 命中**（宿主层 ocr=0 成立但 "
    "composable 层有真调用）"
)

#: 本批：计提情况检查表J1-6 短期薪酬区（册内其余 22 个 sheet 归后置/排除）
_INCLUDE_J106: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_J106:
        specs.append(_j106.SPEC_J106)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """🔴 `审定表J1-1 `（**带尾部空格**）—— 真库 `J1-1-rows` 无行，归后置批次，本 spec 恒 None。"""
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """单数形态（首版发布的 identity inventory / binding 装配读它）。

    🔴 2026-10-01 补：`projection_first_publication` 在 identity inventory 与主 binding 处
    调 `provider.instrumentation_spec()`（单数），缺它即 `SubstrateStagingError: … has no
    attribute 'instrumentation_spec'`（真库 `--apply` 实测踩到）。本 entry 单受管 sheet ⇒ 取唯一一条。
    """
    specs = instrumentation_specs()
    if len(specs) != 1:
        raise HC.HEntrySelectionError(f"J1 受管 spec 应恰 1 条，实际 {len(specs)}")
    return specs[0]


#: 首版发布 binding 装配读的三个 provider 常量（与 L1 同名；契约派生值与之双向锁死）。
ROWS_TABLE_KEY: Final[str] = _j106.ROWS_TABLE_KEY_J106
UUID_COL: Final[str] = _j106.UUID_COL_J106


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


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/composables/workpaper/"
            "useChecklistPersistence.ts —— 🔴 平台共享持久化适配器经 "
            "`api.put('/workpapers/{wpId}/checklist-responses', …)` 写 "
            "{ item_id: 'J1-6-short-term', remark: JSON.stringify(rows) }；"
            "client 是 `api` from `@/services/apiProxy`（**不是** `http` from `@/utils/http`）"
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
# store 投影 / 合并（**薄转发**框架层，照 H9 同构）
#
# 🔴 2026-10-01 补：Task 22 交付契约时缺了这一段 ⇒ `STORE_MERGE_REGISTRY` 无法登记
#    （`resolve_store_merge_plan` 按 provider 模块取 merge 门面）。
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（不静默跳过）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 J1 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`。🔴 `payload` 必须是首位位置参数（golden digest 门按此调用）。"""
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


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    return HC.build_matcher(IDENTITY)


#: 🔴 2026-10-01 修：原两个包装按 `(IDENTITY, manifest=…)` / `(IDENTITY, registry, …)` 调
#:    `HC`，而 `HC.build_registration` 要 `adapter/bundle/descriptor/room`、
#:    `HC.register_adapter` 首参是 `registry` ⇒ 任一调用都 TypeError（从未被执行过）。
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


# ═══════════════════════════════════════════════════════════════════════════
# 五环发布（参照 L1 / D 系 phase5_* 同构）
#
# 🔴 2026-10-01 补：`projection_provisioning.load_projection_supply()` 只认
#    `publish_pilot_definitions` + `assert_contract_file_matches_source`，缺任一即抛
#    `ProviderModuleNotAllowedError: provider 是空壳` ⇒ 没有这段 J1 连 task76 的
#    `--check` 预演都跑不起来（H 系 provider 同样缺，本 spec 不代补）。
# ═══════════════════════════════════════════════════════════════════════════

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract


def authority_model_payload() -> dict[str, Any]:
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


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
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
    """authority → template → instrumentation → contract → bundle（顺序不可颠倒）。"""
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
        raise EntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise EntrySelectionError(
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


#: provisioning 白名单接口别名（硬前置，见上方注释）。
publish_pilot_definitions = publish_definitions
PILOT_WP_CODES = WP_CODES


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
