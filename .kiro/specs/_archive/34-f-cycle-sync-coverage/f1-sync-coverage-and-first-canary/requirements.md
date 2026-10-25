# Requirements Document

## Introduction

本 spec 把 **F1 预付账款**从 legacy 假双向接成真双向，覆盖其**唯一一册**模板
`F/F1 预付账款.xlsx` 内全部可表达的 sheet。

它是 umbrella spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的
**Task 48「逐一迁移 F 循环 Excel 独立 entry」**的下游 lane spec（该 task 复选框 `[x]`，正文要求
「与 F2 Word lane 分开计数；核验复合传输键、估值/监盘模板，不凭 wp_code 猜 sheet」，验证 umbrella
Property 21/28/69/70）。上游已冻结的产物**复用、不重造**：F 循环 manifest slice
`backend/data/workpaper_sync_f_cycle_manifest_slice.json` 与守卫
`backend/tests/workpaper_sync/test_task48_f_cycle_migration.py`。

它是 F 循环五份 spec（F1~F5）的**首份**，承载 **F 循环共同裁决 FC-1~FC-13**（design §F 循环共同裁决）；
F2~F5 spec 引用 FC 编号、不复述。

它消费三个上游，不重造引擎件：
- `d1-sync-row-table-engine-and-d1-coverage` —— `RowTableSheetSpec` / `AdjudicationSheetSpec` / 形态谱系三维
- `e1-sync-coverage-and-first-canary` —— 「连 provider 都没有」的 canary 先例（F1 与 E1 同级）
- `d3-sync-coverage-via-row-table-engine` —— 🔴 **F1 与 D3 结构同构**（预收↔预付：两级表头 + nested 账龄明细、
  余额/发生额分析、长期挂款、关联方、三区检查表、性质/账龄两区审定表），D3 每张 sheet 的裁决是 F1 对应 sheet 的先例

🔴 **Property 编号 spec-scoped**：本 spec 的 `Property N` 一律读作 **`F1-P{N}`**；引用上游写全
`umbrella Property N` / `E1-P{N}` / `D3-P{N}`（umbrella Task 61 附注记录过 BP 同号不同义事故）。

### F1 当前状态实测（manifest + slice + 真库，2026-09-26）

```
entry_id            xlsx/gt-f1-prepayment                （manifest 与 slice 一致）
host_path           audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue
independent_entry   true     parent_entry_id  null     mount_count  2
capability          single_onlyoffice（manifest）/ null + pipeline_entry_pending_definition_delivery（slice）
migration_state     legacy_fake_bidirectional   🔴
adapter_id          null     html_store  "unresolved"
wp_code_patterns    ["F1P"]  ← 宿主 CamelCase 抽出的幻影码；真码 F1（wp_index 5 行，5 行有 file_path）
scenario_profile    xlsx.editable.shared.single.room_service_wired.v1   ← 与 D1~D7 / E1 同型
legacy_reasons      template_only_open / no_durable_forcesave_ack / missing_adapter
```

| 事实 | 实测 |
|---|---|
| provider / 契约 | ❌ 无 `phase5_f1_*.py`，无 `backend/data/workpaper_sync_contracts/f1.*.json` |
| 发布链供给 | `working_paper_sync_entry_state` 全表 12 行，**F 循环 0 行**（D1~D7/G7/H1/B60 各有）；平台 content_representation 268 / content_version 262 / definition_bundle 60 行 —— 平台有供给，F 无 |
| wp_code 裁决 | `workpaper_sync_entry_wp_code_adjudication.json` 10 条，**F 循环 0 条** |
| 宿主接桥 | `GtF1Prepayment.vue` 两处 `<GtOnlyOfficeSheet>`（L20 模式切换 / L168 兜底）+ `GtEntrySyncCapabilityNotice`；**零** `useWorkpaperSyncBridge` / `WorkpaperSyncEditorHost` |
| 公式管理入口 | 宿主 emit `open-formula-manager` **0 次**；页面级入口由 `views/WorkpaperEditor.vue` 挂载的 `WorkpaperCapabilityShell`（F-SHELL 唯一 owner）统一提供 |
| `wp_formula` 表 | 全库 **2 行**（1 个 wp），F1 **0 行** |
| TB 发布门 | ✅ 已接：`useF1Adjudication.ts:552 publishToTb()` → `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（`sheet_name='审定表F1-1'`）；旧 `f1:writeback-trial-balance` 监听已移除（`GtF1Prepayment.vue:409` 注释） |
| 调整分录中央同步 | ✅ `F1TabAdjustment.vue:220 useAdjustmentCentralSync` ⇒ F1-3 是 hub store |

🔴 **当前所有 F1 sheet 切「在线编辑」都是假双向**：走 legacy `GtOnlyOfficeSheet`，OO 改动不合并回
`checklist_responses`，切回结构化视图即丢。

### 模板实测：1 册 / 12 sheets（openpyxl 直读，sha256 `f30055cb…510dd`，261,608 B）

| sheet | state | 尺寸 | 公式 | 数据区 / footer（实测） | 形态候选 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | visible | 22r×H | 15 | — | 导航 | 不接 |
| 预付账款实质性程序表F1A | visible | 34r×M | 7 | — | 步骤清单 | 不接 |
| 🔴 预付账款实质性程序表**G1A-修订前** | **hidden** | 96r×O | 6 | — | **残留**（G1 编号出现在 F1 册） | 不接 |
| **审定表F1-1** | visible | 28r×M | 93 | 性质区 R8-12 / 合计 R13；账龄区 R17-21 / 合计 R22；试算 R23；差异 R24 | 逐格 | ✅ `AdjudicationSheetSpec`（最后接） |
| 附注披露信息(上市公司) | visible | 39r×N | 49 | — | 披露 | 不接 |
| 附注披露信息(国企) | visible | 29r×N | 51 | — | 披露 | 不接 |
| **明细表F1-2** | visible | 55r×AF | 131 | 两级表头 R12/R13；数据 **R14-34**；footer **R35「合计」**；R36 账龄占比 / R37 账龄逻辑校验 | 行表 + nested 账龄 ×3 | ✅ **canary 候选之一** |
| **调整分录汇总F1-3** | visible | 25r×K | 7 | 表头 R5；空白 R6-21；R23 注 | hub store | 🔍 可行性核（FC-6） |
| **实质性分析F1-4** | visible | 56r×T | 70 | 区①余额 R12-18；区②借方 R23-29；区③贷方 R33-36（非表格）；区④大额供应商 **R41-50 / 小计 R51** | dict pack | ✅ 区④；区①~③ 核 |
| **长期挂款检查表F1-5** | visible | 19r×N | 11 | 表头 R5；数据 **R6-14**；footer **R15「合计」** | 行表 | ✅ |
| **关联方及交易检查表F1-6** | visible | 23r×P | 20 | 表头 R6；数据 **R7-9**；footer **R10「合计」**；R15-23 关系类型下拉源（「勿删、勿改」） | 行表 | ✅ **canary 候选之一** |
| **预付账款检查表F1-7** | visible | 93r×S | 23 | 三区：R17-37 / **R38**；R42-64 / **R65**；R69-85 / **R86**（两级表头 R15/16、R40/41、R67/68） | 三区行表 | ✅ |

**逐格实测的公式（数据区首行，按值直读，禁推演）：**

| sheet | 公式 |
|---|---|
| F1-2 R14 | `H=E14+F14+G14` · `O=E14+M14-N14` · `Q=O14+P14` · `X=O14+V14+W14` |
| F1-2 R35 | E..AB 逐列 `SUM(x14:x34)`，AD 同；AC「--」 |
| F1-2 R36/37 | `O36=IF((O35-R35-S35-T35-U35)=0,"OK",…)` · `X36` 同型 · `AB37=IF(AB35<=(K35+L35),TRUE,FALSE)` |
| F1-1 R8 | `E=B+C+D` · `F=SUMIF('明细表F1-2'!$D$14:$D$35,A8,'明细表F1-2'!$O$14:$O$35)` · G/H 同型取 V/W 列 · `I=F+G+H` · `J=I-E` · `K=IF(…)` |
| F1-1 R17 | `F='明细表F1-2'!R35` · `G=I17-F17-H17` · `I='明细表F1-2'!Y35` |
| F1-4 R41 | `E=B41+C41-D41` · `G=E41-F41`；R51 `SUM(41:50)` |
| F1-5 | 数据区 **零公式**（J 列审定余额模板无公式）；R15 `SUM(6:14)` 取 B/I/J/K |
| F1-6 R7 | `F=C7+D7-E7` · `H=F7-G7`；R10 `SUM(7:9)` |
| F1-7 | 数据区零公式；三 footer `SUM(G)` / `SUM(L)` / `SUM(N)` |

模板**无任何 Excel Table**（全 sheet `tables=[]`，Table 由 instrumentation 注入）；定义名 40 个
（含 `AFV=#REF!` 等历史残留，非本 spec 受管锚点）。数据验证：F1-2 `D14:D34` 款项性质五枚举 /
`C14:C34` 关联方类型三枚举 / `AC14:AC34` `√,×`；F1-6 `B7:B9` ← `$B$16:$B$23`（绝对引用，位于 footer 之下）。

**UUID 候选列（逐格实测空列，数据区 + 表头行全空）**：F1-2 `AF`（AE 为「备注」）· F1-5 `N` ·
F1-6 `N`（M 为「备注」）· F1-7 `T`（S 为「检查的关键证据…」说明列）· F1-4 区④ `S`（K40 有长文本说明，
L..R 需 Task 2 逐格复核）。

### F1 store 键实测（按值 grep，含模板化拼接；`_probe_f_keys.py F1`）

| sheet | store 键 | 形态 | 写入方 | 行身份 / 增删 |
|---|---|---|---|---|
| F1-1 审定表 | per-cell `F1-adj-${section}-${rowKey}-${field}`（`useF1Adjudication.ts:127` `makeItemId`；section ∈ `nature` / `aging`）+ `F1-adj-trial-balance-amount` + `F1-adj-note-{aging-reason\|change-analysis\|conclusion}` | per-cell | `useF1Adjudication`(634) | rowKey：性质 `goods/construction/equipment/service/other`（`NATURE_ROWS` L105）；账龄行随账龄口径动态（`agingRowDefs`） |
| F1-2 明细 | `F1-det-rows` + `F1-det-aging-preset` / `F1-det-aging-custom-segments` + `F1-det-note-{fluctuation\|over1year\|prior-linkage}` / `F1-detail-audit-conclusion` / `F1-det-notes` | rows | `useF1Detail`(602) | **`rowId`**（`row-${crypto.randomUUID()}`，L85）；add/del ×1/×1 |
| F1-3 调整分录 | `F1-aje-rows` + `F1-adjustment-audit-{note\|conclusion}` | rows（hub） | `useF1Adjustment`(274)；另被 `useF1LongTerm` / `useF1CrossSheet` 读写 | `rowId`；add/del ×1/×1 |
| F1-4 实质性分析 | **`F1-ana-pack`**（dict：`balanceNatures` / `inventoryBalance` / `debitNatures` / `inventoryPurchase` / `payableBalance` / `creditBreakdown` / **`suppliers[]`** / `notes` / `conclusion`，`useF1Analysis.ts:313`）+ `F1-ana-note` / `F1-analysis-audit-conclusion` | **dict** | `useF1Analysis`(864) | `suppliers[].rowId`；`addSupplierRow`/`removeSupplierRow`（L732/L738） |
| F1-5 长期挂款 | `F1-lt-rows` + `F1-lt-note` / `F1-lt-conclusion` | rows | `useF1LongTerm`(381)；`useF1DisclosureSoe` 读 | `rowId`；add/del ×1/×1 |
| F1-6 关联方 | `F1-rp-rows` + `F1-rp-note` / `F1-rp-conclusion` | rows | `useF1RelatedParty`(313) | `rowId`（L93 `row-${randomUUID}`）；add/del ×1/×1 |
| F1-7 检查 | 区① **`F1-vc-current-rows`**（`ITEM_ID_DEBIT_ROWS`，注释「兼容原 F1-7 导入 item_id」）· 区② `F1-vc-credit-rows` · 区③ `F1-vc-post-rows` + `F1-vc-params` / `F1-vc-audit-{note\|conclusion}` / `F1-vc-conclusion` | rows ×3 | `useF1ComprehensiveCheck`(964，L357-362) | `rowId`；`addSample(section)`/`removeSample(section,rowId)`（L785/L800）；`useF1CrossSheet:354` 读 post 区 |

🔴 **三处键名陷阱（按值实测，推演必错）**：①F1-7 区①键名是 `current` 不是 `debit`（`resolveSection('current')→'debit'`，L780）；
②`F1-7-credit` / `F1-7-post` 是**导入导出 sheet 标识**（`F1TabComprehensiveCheck.vue:447/502`），**不是** store 键；
③`F1-CONF` 是宿主内函证程序 tab 的 `currentSheet` 值（`GtF1Prepayment.vue:159`），`F1-TB4` 是附注勾稽规则编号
（`f1DisclosureConsistency.ts:482`），二者都不是 store 键。

**真库载荷（只读实测）**：`F1-det-rows` 1 行 46,295 B / **68 行全带 `rowId`**、三套 nested 账龄
（`agingPrior`/`agingCurrent`/`agingAudited`）段键全是 THREE_YEAR 的 `within1/y1to2/y2to3/over3`；
`F1-det-aging-preset='THREE_YEAR'`；`F1-aje-rows` 415 B / `F1-ana-pack` 912 B / `F1-lt-rows` 178 B /
`F1-rp-rows` 260 B（1 行空骨架带 `rowId`）；F1-7 三键 0 行。全部落在 **wp_code=F1**。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · F1-2 明细 HTML 与 OO 两侧行公式口径不一致（双模式数值会分歧）**

| 列 | 模板（`明细表F1-2` R14 按值直读） | 前端 `useF1Detail.recalcRowFormulas`（L143-L147 按值直读） |
|---|---|---|
| O 期末余额 | `=E+M-N`（**期初未审**起算） | `calcEndBalance(H, debit, credit)` = `H+M-N`（**期初审定**起算） |
| X 审定数 | `=O+V+W`（**期末余额**起算） | `calcEndAudited(Q, endAje, endRje)` = `Q+V+W`（**期末未审**起算） |

两者在 `F≠0 或 G≠0`（期初有调整）或 `P≠0`（被审计单位重分类）时数值不同。受管后 `O/X` 是
`mode=formula` 格、OO 按模板重算，HTML 按前端算 ⇒ **同一行两种模式显示两个数**。真库 68 行
当前恰好 `F=G=P=V=W=0`，两式数值相同（实测 `o_ne_template=0`），故尚未暴露。
🔴 **同型口径在 D3-2 已存在且未被 D3 spec 登记**：D3 模板 `O12=E12+N12-M12`、前端
`useD3Detail.ts:141` `calcEndBalance(H, credit, debit)`。以期初审定起算期末余额的还有 `useG2Detail.ts:224`。
⇒ 本 spec 需求 7 裁决 F1-2 的口径方向，D3/G2 同型登记为顺带发现、不在本 spec 修。

**B2 · 公式管理预设 4 条红测试**（`test_f1_formula_presets.py`，本会话复跑 9 failed / 66 passed 中属 F1 的 4 条）：

| 用例 | 失败原因（实测） |
|---|---|
| `test_runtime_preset_count_grew` / `test_preset_sheet_names_match_source_xlsx_tabs` | 预设块 `[16]` sheet 名为**全角** `附注披露信息（国企）`，源 tab 是**半角** `附注披露信息(国企)` |
| `test_new_sheet_has_presets[附注披露信息(国企)]` / `test_soe_disclosure_has_long_term_sheet_reference` | 同上 ⇒ 半角国企块不存在 |

🔴 **两个守卫口径互相矛盾**：`fix_f1_prefill_presets.py --check` 实测 **exit 0「F1 公式预设校验通过」**，
因为它只管 `审定表F1-1` / `明细表F1-2` / `实质性分析F1-4` 三块（L50-52），根本不检查披露块。红测试引用的
spec `f1-extraction-chain-and-disclosure-source-fidelity` 已归档于 `_archive/08-disclosure-notes/`（17 个编号任务，
残留 `[ ] 5.3 浏览器实测 + 数据复原`），其 design.md L163 明写国企块用**半角** `附注披露信息(国企)` ⇒
数据文件在归档后被**回退**成全角（`prefill_formula_mapping.json` 是多 spec 共享的回退高发文件，I 循环守卫同款注释），
而归档后**无活跃 owner 的 `--check`** 能发现。另 `test_disclosure_blocks_are_not_referenced_by_wp` 红的是 **D2** 块
（`=PREV('D2','附注披露信息(上市公司)',…)`），不属 F1，登记移交。

🔴 **静默失效**：`convert_prefill_presets()`（preset_library.py:162）以 `page_key=workpaper:{wp_code}`
收敛、忽略 sheet ⇒ 全角块照样出现在 F1 公式管理页（实测 F1 33 条预设）；而 `wp_template_init_service`
（L620-L628）按 sheet 名精确匹配、失配时回退到「含『审定表』的 sheet」⇒ 全角块的格**写进审定表而不是披露表**。

**B4 · F1-1 审定表 HTML 与 OO 两侧取数口径不一致**（按值直读模板 + 前端）

| 区块 | 模板 | 前端 |
|---|---|---|
| 性质区「期末未审数」F8 | `SUMIF(F1-2!D, A8, F1-2!O)` = Σ**O 期末余额**；G8/H8 = ΣV / ΣW；`I=F+G+H` | `natureAggregation` 取 `aggregateByNature(rows,'endAudited')`（`useF1CrossSheet.ts:202`）= Σ**X 审定数** 作未审数；AJE/RJE 取 F1-1 逐格手填（`useF1Adjudication.ts:174-181`） |
| 账龄区 F17 / I17 / G17 | `F='明细表F1-2'!R35`（期末**未审**账龄）· `I='明细表F1-2'!Y35`（**审定**账龄）· `G=I-F-H`（AJE 倒挤） | 账龄行取 `agingAgg[rowKey]`（`useF1CrossSheet.ts:191` 聚合 `agingAudited`）= **审定**账龄 作未审数，再加手填 AJE/RJE |

⇒ F1-1 受管后 F/G/H/I 列的公式格在两种模式下**不是同一个数**；且 HTML 侧若 F1-2 的 V/W 与 F1-1 手填
AJE/RJE 同时有值会重复计入（真库 F1-2 V/W 全 0，`vw_nonzero=0`，尚未暴露）。🔴 D3 同型：
`useD3CrossSheet.ts:195` 同样以 `endAudited` 聚合性质区。

**B3 · 行身份与 BP-7**：F1 五个 `-rows` 键载入路径全部 `raw.rowId || generateRowId()`（无下标回退），
**F1 无 BP-7**。但缺 `rowId` 的旧行每次载入都会现铸新 id（未回写前身份不稳定），Task 2 须核载入后是否立即落盘。

## Glossary

| 术语 | 含义 |
|------|------|
| canary | 首张接入样本：从零建 provider + 契约 + adapter + 宿主接桥的完整链路（同 E1） |
| `legacy_fake_bidirectional` | manifest migration_state：走 legacy `GtOnlyOfficeSheet`，OO 改动不合并回 store |
| 幻影码 | manifest `wp_code_patterns` 从宿主 CamelCase 抽出的码（F1 为 `F1P`），`find_template_file` 零命中；真码 `F1` 由 wp_code 裁决文件提供（D3P/D4O/D5R 先例） |
| 受管区 / binding | 契约声明的一个 `(sheet, table)` 受管数据区；同 sheet 多区走兄弟 Table ref 位移 |
| `binding_kind` | `excel_table`（动态，Table + UUID 列）/ `static_region`（definedName 锚点，绕开位移链） |
| 三元组判据 | `(store 键存在, addRow/removeRow 信号数, composable 归属)` —— 判 `binding_kind` 的唯一依据（E1 裁决 H8） |
| hub store | 被多条专用链共同占用的 store 键（`F1-aje-rows` 被 `useF1Adjustment` / `useF1LongTerm` / `useF1CrossSheet` 三方读写 + 中央调整登记） |
| 口径分歧 | 同一格 HTML 前端公式与模板 Excel 公式数学不等价 ⇒ 双模式显示值不同 |
| F-SHELL | `shell/formula/WorkpaperCapabilityShell.vue`，挂在 `views/WorkpaperEditor.vue`，是页面级公式管理/能力条的**唯一 owner** |
| 三层公式 | ①平台公式管理（`wp_formula` + F-SHELL）②表内/表间计算（前端 composable 公式链 + `prefill_formula_mapping.json`）③`formula_mask`（模板公式格，materialize 不覆盖、由 OO 重算）—— 三层不得混淆 |
| TB 显式发布门 | 唯一 TB 回写通道 `publishToTb` → `POST …/audit-determination/publish-to-tb` + 中文二次确认 |
| BP-61-1 | umbrella Task 61 实测的平台级绑定约束：published representation 供给缺失 ⇒ entry 注册不上 |

## Requirements

### Requirement 1: F1 首张 canary —— 从零打通真双向

**User Story:** 作为审计助理，我希望 F1 切「在线编辑」后在 OO 里改的数能真正写回结构化视图，而不是切回来就丢。

#### Acceptance Criteria

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`关联方及交易检查表F1-6`**（23r×P / 20 公式 / 数据 R7-9 /
   footer R10 / 键 `F1-rp-rows`）—— 理由见 design 裁决 F1-H1：单级表头、无账龄组、零跨 sheet 取数、
   零 OCR、无口径分歧、失败面最小（与 E1-2、D3-6 同一选择逻辑）。
2. WHEN 建 provider THEN SHALL 新建 `backend/app/services/workpaper_sync/phase5_f1_prepayment.py`，照
   D3/E1 同构；`assert_entry_selectable` SHALL 在**真 manifest + 真 finder** 上核四条事实（entry 存在 /
   `independent_entry=True` / profile 同型 / `wp_code_patterns` 落点）+ 零模板回退，且**默认严格**（不得提供
   可关闭第四条的开关 —— 见 FC-2 对 E1 同类缺陷的实测）。
3. WHEN provider 声明 wp_code THEN 模块 `WP_CODES` SHALL 取 manifest 冻结的幻影码 `{"F1P"}`（matcher 域），
   provisioner 定位宿主 SHALL 取 wp_code 裁决文件新增条目的真码 `["F1"]`（D3P/D4O/D5R 同范式，FC-2）。
4. WHEN 契约发布 THEN SHALL 走完整链路：`build_contract_payload` → 生成器 `--apply` →
   `assert_contract_file_matches_source` → approved bundle → published representation → `entry_state` →
   `register_from_manifest()` 真注册 adapter。
5. WHEN adapter 注册成功 THEN manifest `migration_state` SHALL 从 `legacy_fake_bidirectional` 变为
   `adapter_registered`，三条 `legacy_reasons` SHALL 全部消除。
6. WHEN 宿主接桥 THEN `GtF1Prepayment.vue` SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
   （包在有确定高度的 `.oo-container` 里），**保留** legacy `GtOnlyOfficeSheet` 给未接 sheet，受管 sheet 集合
   SHALL 从 provider 受管清单派生、不前端硬编码。
7. WHEN 真栈验收 THEN SHALL 达到三谓词 `confirm 200` / `forcesave cs_error=0` / `store_mirrored`+`marker_visible`
   并留 DB 证据。
8. 🔴 WHERE 第③环 published representation 缺供给（BP-61-1）THE Task SHALL 如实登记 `upstream_gap`，**不得**
   以离线 engine / 合成数据 / 文档声明冒充通过；canary 未通之前不得声明第二张受管 sheet 的**真栈验收**
   （声明层可先行，灰度开关默认关）。

### Requirement 2: 形态判定先行（三元组实证，不按公式数）

**User Story:** 作为维护者，我不希望凭模板公式数或 sheet 编号推演形态。

#### Acceptance Criteria

1. WHEN 判定任一 sheet 形态 THEN SHALL 在上游三维谱系内选择，**不新造**：`binding_kind` · `row_identity_key` ·
   HTML-only item 子集。
2. WHEN 判定 `binding_kind` THEN 判据 SHALL 是前端三元组实证。实测结论：F1-2/F1-5/F1-6/F1-7 均为
   `excel_table` + `rowId`；F1-4 区④是 **dict 子数组**（`F1-ana-pack.suppliers[]`）；F1 **无** `static_region`
   强候选（F1-4 区①②是固定行 dict 子对象，须按 D4-9 dict 范式核，见需求 5）。
3. WHEN 声明 `store_item_id` THEN SHALL 逐字等于按值 grep 实测值；变异 SHALL 包含 `F1-vc-current-rows→F1-vc-debit-rows`
   与 `F1-rp-rows→F1-6-rows` 两条并证明打红。
4. WHEN 某 sheet 的 note / conclusion 类 item 落在 footer 之下 THEN SHALL 逐项核是否与插行 fail-closed 冲突，
   命中者登记 HTML-only 子集（`HTML_ONLY_ITEM_IDS_F1`），**不**塞进动态区。
5. WHEN footer 下存在非数据的保护区（F1-6 R15-23「勿删、勿改」关系类型下拉源）THEN 它 SHALL 不进 `field_specs`，
   且 SHALL 有判据证明插行后 `B7:B9` 的数据验证 `formula1=$B$16:$B$23` 随位移同步（位移链已支持
   `formula1` 位移，`excel_row_shift.py:183`）。

### Requirement 3: F1-2 明细（两级表头 + 三套 nested 账龄 + 口径裁决）

**User Story:** 作为审计助理，我希望 F1-2 在两种模式下每一行的期末余额和审定数是同一个数。

#### Acceptance Criteria

1. WHEN 声明 F1-2 THEN SHALL 用 `RowTableSheetSpec`（`store_item_id="F1-det-rows"` / `row_identity_key="rowId"` /
   两级表头 R12/R13 / 数据 R14-34 / footer R35 / UUID 列 `AF`），账龄 `aging_layout=nested`、三组
   `agingPrior`(I-L) / `agingCurrent`(R-U) / `agingAudited`(Y-AB)。
2. 🔴 WHEN F1-2 受管 THEN 需求 7 的口径裁决 SHALL 已落地且 HTML 与模板对 O/X 两列**数学等价**；未落地前
   F1-2 灰度开关 SHALL 保持关闭。
3. WHEN F1-2 账龄口径为 `FIVE_YEAR` / `CUSTOM`（`useF1AgingScope` 支持 2~10 段，`F1-det-aging-preset` 持久化）
   THEN 模板只有 4 列账龄格 ⇒ 受管 SHALL 仅在 `THREE_YEAR` 下启用；非 THREE_YEAR 时 SHALL 降级为只读或
   保持 legacy 并显示中文原因，**不得**把第 5 段起的金额在 OO 往返中丢弃（列集守恒判据，同 E1-P18 精神）。
4. WHEN footer 之下 R36/R37 校验行（账龄占比 / 账龄逻辑校验）THEN 它们 SHALL 不受管（纯公式、无行维度）。
5. WHEN F1-2 回写 THEN 下游消费方 SHALL 在回写后正确重算：`useF1CrossSheet`（F1-1 聚合 / 附注）·
   `useF1Analysis`（F1-4 前五名候选）· `useF1ConfirmationProcedure` · `useF1DisclosureListed` / `-Soe`（按值
   grep `F1-det-rows` 的 15 处引用由 Task 2 补全清单）。

### Requirement 4: F1-5 / F1-7 行表（单区 + 三区）

**User Story:** 作为审计助理，我希望长期挂款与三区凭证检查在 OO 里增删行也能写回。

#### Acceptance Criteria

1. WHEN 声明 F1-5 THEN SHALL 用 `RowTableSheetSpec`（`F1-lt-rows` / `rowId` / 表头 R5 / 数据 R6-14 /
   footer R15 / UUID 列 `N` / `formula_columns=()`）。
2. 🔴 WHEN F1-5 J 列「审定余额」THEN 模板 J6:J14 **无公式**而前端 `recalcLongTermRow` 自动派生
   `auditedBalance = endBalance − badDebtProvision`（`useF1LongTerm.ts:55-62`）⇒ J 列 SHALL 判定为 HTML 派生列：
   契约 mode 不得标 `editable`（否则 OO 手改 J 后 HTML 下一次重算即覆盖、用户改动静默丢失）；具体取
   `auto_source` 或由 provider 注入模板公式 `=B{r}-I{r}` 由 Task 1 裁决并留证（FC-7）。
3. WHEN 声明 F1-7 THEN SHALL 声明**三个** `RowTableSheetSpec`，同 `managed_sheet`、不同 `store_item_id`
   （`F1-vc-current-rows` / `F1-vc-credit-rows` / `F1-vc-post-rows`）/ 行段 / 两级表头。三区**列集不同**
   （逐格实测：区① R16 G=借方金额、H..O 为审批单/回单/合同证据、R=是否异常；区②③ R41/R68 G=贷方金额、
   H..N 为入库单/发票证据、Q=是否异常），SHALL 各自声明 `field_specs`，不得三区共用一份。
   🔴 区①模板 O 列「预付比例」（`O17` 格式 `0.00%`）在前端 `F1DebitCheckRow`（L21-L43，按值读全 20 字段）
   **无对应字段** ⇒ O 列 SHALL 不进 `field_specs`（HTML-only 空列，OO 侧填写不回写并中文登记），不得臆造字段键。
4. WHEN F1-7 三区同 sheet THEN SHALL 走兄弟 Table ref 位移路径，且任一区插行后另两区的 footer 公式与数据
   验证随位移同步（D3-7 双区已验证的路径）。
5. WHEN F1-7 有 OCR 入口（`F1VoucherCheckDialog.vue` `runOcr` → `POST /api/workpapers/{wpId}/f4/contract-ocr`，
   回填**单个弹窗表单**）THEN 须实测它是否整表替换 `-rows` 键；若只改单行则不构成 E1 意义的第二批量写入方，
   结论登记证据（FC-8）。

### Requirement 5: F1-4 实质性分析（dict pack）

**User Story:** 作为维护者，我不希望把一个 dict 载荷硬拆成行表。

#### Acceptance Criteria

1. WHEN 判定 F1-4 THEN SHALL 登记其 store 为单一 `StoreKind.dict`（`F1-ana-pack`，9 个顶层键）。
2. WHEN 受管区④大额供应商（R41-50 / 小计 R51）THEN SHALL 以 dict 子数组 `suppliers[]` 为行源（行身份
   `rowId`），走 provider 专用 merge 门面（D4 `merge_d*_from_projection` 范式），合并时 SHALL 保留 pack 其余 8 个
   顶层键逐字不变。
3. WHEN 区①余额分析（R12-18）/ 区②借方分析（R23-29）THEN 行是写死的性质行（与 dict 子对象
   `balanceNatures` / `debitNatures` 的 `inventory/expense/construction/other` 四键对应），SHALL 按「稳定 key 固定行」
   核可行性；区③贷方（R33-36）是非表格的「标签+金额」散格，SHALL 判 HTML-only 或 `static_region`，由 Task 核定。
4. WHEN F1-4 任一区受管 THEN `computeTop5`（`useF1Analysis.ts:809`）从 F1-2 自动填 suppliers 的行为 SHALL 不回归。

### Requirement 6: F1-3 调整分录汇总（hub store 可行性核）

1. WHEN 核 F1-3 THEN SHALL 只产裁决与证据、**不改生产代码**；判据沿用统一裁决 spec
   `cycle-adjustment-sheets-single-html-adjudication`（D1-5/D2-4/D3-3/D4-4/D5-3/D6-4/D7-3/E1-5 同型，F1-3 为第九张）。
2. WHERE `F1-aje-rows` 有三方读写（`useF1Adjustment` / `useF1LongTerm.mergeSuggestedIntoAje` 注入拟调整分录 /
   `useF1CrossSheet` 读）+ 中央调整登记 THE 默认裁决 SHALL 为 `single_html`，除非可行性核证明三方写入可串行化。

### Requirement 7: 公式管理与双模式口径一致

**User Story:** 作为审计助理，我希望公式管理入口在两种模式下行为一致，且 HTML 算出来的数与 Excel 公式一致。

#### Acceptance Criteria

1. WHEN 提供公式管理入口 THEN SHALL 消费 F-SHELL（`WorkpaperCapabilityShell` 唯一 owner），**不**在 F1 宿主内新建
   第二个按钮 owner；判据 SHALL 覆盖结构化视图与在线编辑两种模式下入口均可达。
2. 🔴 WHEN F1-2 的 O/X 口径分歧（红基线 B1）THEN SHALL 以**模板公式为权威**修前端
   （`O = priorUnadjusted + debit − credit`，`X = O + endAje + endRje`）—— 依据：审计底稿以致同权威模板为准、
   OO 模式直接执行模板公式；修复 SHALL 同步 `useF1Detail.ts` 注释与单测，并跑 F1 全部前端测试零回归。
3. WHEN F1-1 取数口径分歧（红基线 B4）THEN SHALL 同样以模板为权威：性质区 F 列 = Σ明细 O、G/H 列 = Σ明细 V/W；
   账龄区 F = 明细 R35（未审账龄）、I = 明细 Y35（审定账龄）、G 倒挤。🔴 该修改改变 F1-1 的 AJE 来源（手填 → 汇总明细），
   SHALL 先出影响评估（真库 F1-1 per-cell AJE 键现状 + 下游附注/TB 发布金额是否变化）再实施，属需求 4.2 同级「改代码前先证」。
   🔴 **该影响评估与方向裁决 SHALL 一次覆盖三家同型审定表**（F1-1 per-cell / F3-1 行数组 / F4-1 两个行数组，
   三者的分歧同源：模板按明细 SUMIF/SUMPRODUCT/直引汇总 vs 前端以审定口径作未审数 + 手填 AJE/RJE）。
   F3 spec 需求 6.3 与 F4 spec 需求 6.3 明写依赖本条结论，各自只负责落地自己那张 —— 避免三份 spec 各裁一次互相不一致。
4. WHEN 修 prefill 预设（红基线 B2）THEN SHALL 把块 `[16]` sheet 名改为半角 `附注披露信息(国企)` 并使
   `test_f1_formula_presets.py` 的 4 条 F1 用例转绿；SHALL 为披露块补一个带 `--check` 的幂等 owner（扩
   `fix_f1_prefill_presets.py` 或新建），使「`--check` 通过 ⇔ 红测试转绿」同口径。
5. WHEN 声明任一受管 sheet 的 `formula_columns` THEN SHALL 与模板逐格实测一致（mask 由引擎现算，不手写字面量）。

### Requirement 8: 审定表 F1-1（最后接，TB 发布门红线）

1. WHEN 声明 F1-1 THEN SHALL 用 `AdjudicationSheetSpec`，`sections` = 实测两区（性质 R8-12 / 账龄 R17-21），
   `row_mode`：性质区 `fixed_rows`（5 个 rowKey 与 `NATURE_ROWS` 逐字一致），账龄区 `slot_driven`（行随账龄口径，
   THREE_YEAR 4 行 + 模板 R21 空槽）；cell_mask 逐格实测（93 公式）。
2. WHEN F1-1 受管 THEN sync 回写路径对 `trial_balance` 的写次数 SHALL 为 **0**；TB 回写 SHALL 仍只经
   `publishToTb`（`useF1Adjudication.ts:552`）；判据 SHALL 包含「在 sync 回写里调 publishToTb ⇒ 必红」变异。
3. WHEN F1-1 的 per-cell 键（`F1-adj-${section}-${rowKey}-${field}`）受管 THEN 投影/合并 SHALL 以该模板化键为
   `store_item_id` 集合的唯一口径（`all_store_item_ids()` 出/回同源）。

### Requirement 9: 零回归与证据纪律

1. WHEN F1 provider 纳入 THEN 既有 contract 的 golden digest SHALL **逐项不变**
   （🔴 **现算基线，不写死数字** —— 依 G 循环裁决 GC-10：本条原写「10 个（b60/d1~d7/e1/g7/h1）」，
   但那串名字实为 **11** 个且契约目录已涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1）⇒
   判据形态应为「非 F1 的 digest 逐项比对」，不断言集合大小）；F1 SHALL
   加入 `check_sync_provider_golden_digest.py` 的 `PROVIDERS`。
2. WHEN 登记新 provider THEN SHALL 同步：`registry.py` 的 `DELIVERED_PER_ENTRY_CONTRACTS` 与
   `_ALLOWED_PROVIDER_MODULES`、`store_item_registry` 的 merge plan、wp_code 裁决文件、entry overlay + 重生 manifest、
   `backend/scripts/file_size_whitelist.txt`（如超阈）。
3. WHEN 声称任一判据有效 THEN SHALL 有变异打红证据；e2e SHALL `--workers=1`，写格走 `#ce-cell-name` → 键入 → Enter，
   callback 判定读 `application_bound_at`。
4. WHEN 未接 sheet 切在线编辑 THEN SHALL 保持 legacy 并显式登记为假双向（不静默）。

### 不在本 spec 范围

- 底稿目录 / F1A 程序表 / 两张附注披露 / 隐藏残留 `预付账款实质性程序表G1A-修订前`。
- 宿主内非模板 tab `F1-CONF`（函证程序，走 D0 共享函证模块）。
- D3-2 / G2 同型口径分歧、`test_disclosure_blocks_are_not_referenced_by_wp` 的 D2 块（登记移交）。
- 发布链平台级供给（BP-61-1）本身。
