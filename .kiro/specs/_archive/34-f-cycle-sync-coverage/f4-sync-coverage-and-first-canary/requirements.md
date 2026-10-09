# Requirements Document

## Introduction

本 spec 把 **F4 应付账款**从 legacy 假双向接成真双向，覆盖其**唯一一册**模板 `F/F4 应付账款.xlsx` 内可表达的 sheet。
它是 umbrella Task 48 的下游 lane spec；F 循环共同裁决 **FC-1~FC-13** 见
`f1-sync-coverage-and-first-canary/design.md` §F 循环共同裁决（本 spec 引用、不复述）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`F4-P{N}`**。

F4 与 F1（预付账款）是借贷镜像、几何近乎同构（审定表两区 + 明细表两级表头 + 分析表 + 长期挂账 + 关联方 + 多区检查表），
差别集中在三处 F1 没有的形态：① **F4-7 是五区**（F1-7 三区）且五区列集全不同；② **F4-9 是供应商分组表**，模板固定 3 组
而前端组数/组内行数皆可变（容量冲突）；③ F4-1 审定表 store 是**两个行数组**（F1-1 是 per-cell）。

### F4 当前状态实测（manifest + slice + 真库，2026-09-26）

```
entry_id            xlsx/gt-f4-accounts-payable
host_path           audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue
independent_entry   true     mount_count  2     parent_entry_id  null
capability          single_onlyoffice        migration_state  legacy_fake_bidirectional  🔴
adapter_id          null     html_store  "unresolved"
wp_code_patterns    ["F4A"]  🔴 幻影码**撞真实程序表码**（见下）
scenario_profile    xlsx.editable.shared.single.room_service_wired.v1
legacy_reasons      template_only_open / no_durable_forcesave_ack / missing_adapter
template_ref        F/F4 应付账款.xlsx
```

🔴 **`F4A` 是全 F 循环唯一「幻影码撞真码」的 entry**：`backend/app/data/wp_code_overrides.json:549` 有
`"F4A": "f4-accounts-payable"`（应付账款实质性程序表的路由码，模板内真有该 sheet `应付账款实质性程序表F4A`），
而 manifest 的 `wp_code_patterns` 恰好也是 `F4A`（宿主 CamelCase `GtF4**A**ccountsPayable` 派生）。
`backend/wp_templates/_index.json` 中**无** `F4A` 条目（只有 `F4`，按值实测）⇒ finder 侧零命中、`assert_no_implicit_template_fallback`
可过；但任何「把 manifest 幻影码当业务 wp_code 用」的新代码都会误命中程序表。本 spec 需求 1.3 专门钉死。

| 事实 | 实测 |
|---|---|
| provider / 契约 | ❌ 无 `phase5_f4_*.py`、无 `f4.*.json` |
| 发布链供给 | `working_paper_sync_entry_state` F 循环 0 行 |
| wp_code 裁决 | 文件中 F 循环 0 条 |
| 宿主接桥 | `GtF4AccountsPayable.vue` 两处 legacy `<GtOnlyOfficeSheet>`（L39 / L151）+ `GtEntrySyncCapabilityNotice`；零 `useWorkpaperSyncBridge` |
| 公式管理 | 宿主 emit 0 次；入口由 F-SHELL 提供；`wp_formula` 表 F4 0 行 |
| TB 发布门 | ✅ `F4TabAdjudication.vue:218 publishToTb()`（`useF4Adjudication`）；旧 `f4:writeback-trial-balance` 监听已移除（`GtF4AccountsPayable.vue:326` 注释） |
| 调整分录中央同步 | ✅ `F4TabAdjustment.vue:100 useAdjustmentCentralSync` ⇒ F4-3 是 hub（FC-6） |
| 真库载荷 | `F4-2-rows`（3,485 B / **4 行全带 `rowId`**）+ `F4-7-estimated-inbound-rows`（1,211 B），均落 wp_code=F4 |

### 模板实测：1 册 / 15 sheets（sha256 `e20e6272…11fd`，108,329 B）

| sheet | state | 尺寸 | 公式 | 表头 / 数据 / footer（逐格实测） | 形态 | 本 spec |
|---|---|---|---|---|---|---|
| 修订说明 | **hidden** | 13r×C | 0 | — | 残留 | 不接 |
| 底稿目录 | visible | 21r×H | 18 | — | 导航 | 不接 |
| 应付账款实质性程序表F4A | visible | 41r×M | 7 | — | 步骤清单 | 不接 |
| **审定表F4-1** | visible | 30r×L | 93 | 性质区：表头 R6/R7，数据 **R8-12**，合计 **R13**；账龄区：表头 R15/R16，数据 **R17-21**，合计 **R22**；试算 R23；差异 R24 | 两个行数组 | ✅ 最后接 |
| 附注披露信息(上市公司) | visible | 16r×D | 22 | — | 披露 | 不接 |
| 附注披露信息(国企) | visible | 18r×E | 26 | — | 披露 | 不接 |
| **明细表F4-2** | visible | 52r×AC | 113 | 两级表头 **R9/R10**；数据 **R11-31**；footer **R32「合计」**；R33 账龄校验 | 行表 + nested 账龄 ×2 | ✅ |
| 调整分录汇总F4-3 | visible | 24r×J | 7 | 表头 R5 | hub | 🔍 FC-6 |
| **实质性分析F4-4** | visible | 49r×H | 40 | 区①周转率：表头 R11，固定行 **R12-23**；区②前十名：表头 R25，**固定 10 行 R26-35**，小计 **R36** | 双 dict（见下） | 🔍 核 |
| **长期挂账检查表F4-5** | visible | 19r×M | 9 | 表头 **R8**；数据 **R9-14**；footer **R15「合计」** | 行表（数据区零公式） | ✅ |
| **关联方及交易检查表F4-6** | visible | 25r×Q | 17 | 表头 **R6**；数据 **R7-11**；footer **R12「合计」** | 行表 | ✅ **canary** |
| **未入账检查表F4-7** | visible | 101r×N | 68 | 🔴 **五区**（见下表） | 五区行表 | ✅ |
| **应付账款检查表F4-8** | visible | 68r×T | 18 | 两区：R15/R16 · **R17-37** · **R38「合计」**；R40/R41 · **R42-57** · **R58「合计」** | 双区行表 | ✅ |
| **供应商融资检查表F4-9** | visible | 33r×R | 17 | 表头 **R11**；固定三组：供应商1 **R12-15**/小计 **R16**、供应商2 **R17-20**/小计 **R21**、供应商3 **R22-25**/小计 **R26**；合计 **R27** | 分组表（容量冲突） | 🔍 裁决后 |
| GT_Custom | hidden | 8r×B | 0 | — | 平台注入区 | 不接 |

**🔴 F4-7 五区逐区实测**（探针摘要只显示 4 个 footer 是 `--max-rows` 截断所致，实际五区；前端恰好五个 store 键）

| 区 | 标题行 | 表头 | 数据 | footer | 列集（按值） | 数据区公式 | store 键 |
|---|---|---|---|---|---|---|---|
| ① | R13「（一）期后付款是否在平均付款天数内」 | R14 单级 | **R15-24** | **R25** | A-K 11 列（序号/供应商/期初/借方/贷方/期末/平均付款天数/期后付款/差异/是否在天数内/备注） | `F=C+E-D` · `G=365/(E/F)` · `I=H-F` | `F4-7-payment-window-rows` |
| ② | R26「（二）料到单未到——存货暂估入库」 | R27/R28 两级 | **R29-44** | **R45** | A-K（入库单日期/编号/数量/合同单价/暂估金额/记账凭证日期/凭证号/金额/是否应调整/备注） | `F=D*E` | `F4-7-estimated-inbound-rows`（legacy `F4-7-receipt` / `F4-7-inbound-rows`） |
| ③ | R46「（三）截止审计现场结束日未处理的供应商发票」 | R47/R48 两级 | **R49-59** | **R60** | A-J（购货发票日期/编号/数量/发票内容/金额/供应商/是否应计入报告期/应计入金额/备注） | 无 | `F4-7-unprocessed-invoice-rows`（legacy `F4-7-invoice` / `F4-7-invoice-rows`） |
| ④ | R61「（四）应付账款期后付款核对」 | R62/R63 两级 | **R64-75** | **R76** | A-J（记账凭证日期/编号 + 银行付款凭单日期/编号 + 金额/供应商/是否应计入/金额/备注） | 无 | `F4-7-subsequent-payment-rows` |
| ⑤ | R77「（五）应付账款期后增加额核对」 | R78/R79 两级 | **R80-91** | **R92** | A-J（记账凭证 + 购货发票 + 金额/供应商/是否应计入/金额/备注） | 无 | `F4-7-subsequent-increase-rows`（legacy `F4-7-purchase` / `F4-7-purchase-rows`） |

footer 公式：R25 `SUM(C/D/E/F/H/I 15:24)` + `G25=365/(E25/F25)`；R45/R60/R76/R92 各 `SUM(F,I …)`。
🔴 区① `G=365/(E{r}/F{r})` 是**除法且分母可为 0**（E=0 时 `#DIV/0!`）—— 引擎首次在 F 循环遇到可能产出错误值的公式列。

**其余逐格公式**：F4-1 R8 `E=B+C+D` · `F/G/H=SUMIF('明细表F4-2'!$D$11:…)` · `I=F+G+H` · `J=I-E` · `K=IF(AND(E=0,J=0),0,…)`；
R17 `F='明细表F4-2'!N32` · `I='明细表F4-2'!U32` · `G=I-F-H`（AJE 倒挤）；F4-2 R11 `H=E+F+G` · `K=E+J-I` · `M=K+L` · `T=M+R+S`；
F4-4 `B12='审定表F4-1'!E13` · `B13='审定表F4-1'!I13` · `C13='审定表F4-1'!E13`，R26 `D=B-C` · `E=D/C`；
F4-6 R7 `F=C+E-D`；F4-9 小计 `F16=SUM(F12:F15)` · `M16=F16-L16`，合计 `F27=F26+F21+F16`（**三组相加，非 SUM 区间**）。

**UUID 候选列（逐格实测数据区 + 表头全空）**：F4-1 **M**（L 原因分析、max_col N）· F4-2 **AB**（AA 备注、max AC）·
F4-5 **L**（K 备注、max M）· F4-6 **M**（L 备注、max Q）· F4-7 **L**（区①② K 是备注，区③④⑤ J 是备注、max N）·
F4-8 **S**（R 是「检查的关键证据…」说明列、max T）· F4-9 **P**（N 借款余额、**O16 有提示文本**、max R）。

### F4 store 键实测（按值 grep；`_probe_f_keys.py F4`）

| sheet | store 键 | 形态 | 写入方 | 行身份 / 增删 |
|---|---|---|---|---|
| F4-1 审定表 | **两个行数组**：`F4-1-adj-nature-rows` / `F4-1-adj-aging-rows` + `F4-1-adj-tb-2202` / `-adj-note` / `-adj-conclusion` | rows ×2（稳定 rowKey） | `useF4Adjudication`(791) | `rowKey`；无 add/del；🔴 **L230 `custom-${index}` 下标回退**（BP-7 同型，rowKey 版） |
| F4-2 明细 | `F4-2-rows` + `F4-2-audit-note` / `-audit-conclusion` | rows | `useF4Detail`(744) | `rowId`（`raw.rowId \|\| raw.id \|\| generateRowId()`，L367）；add/del ×1/×1；真库 4 行全带 rowId |
| F4-3 调整分录 | `F4-3-rows` + `F4-3-audit-note` / `-audit-conclusion` | rows（hub） | `F4TabAdjustment.vue` | `rowId`；add/del |
| F4-4 分析 | **两键**：`F4-4-turnover`（dict `{inputs: Record<key,number>, remarks}`）+ `F4-4-creditor-overrides`（数组 `{rowId, reason}`）+ 三个 note/conclusion 键 | dict + 覆盖数组 | `useF4SubstantiveAnalysis`(482) | 区②行**派生自 F4-2**，只存 `reason` 覆盖 |
| F4-5 长期挂账 | `F4-5-rows` + `-audit-note` / `-audit-conclusion` / `-note` | rows | `useF4LongOutstanding`(576) | `rowId`；add/del ×1/×1 |
| F4-6 关联方 | `F4-6-rows` + `-audit-note` / `-audit-conclusion` / `-note` | rows | `useF4RelatedParty`(588) | `rowId`；add/del ×1/×1 |
| F4-7 未入账 | **五键**：`F4-7-payment-window-rows` / `-estimated-inbound-rows` / `-unprocessed-invoice-rows` / `-subsequent-payment-rows` / `-subsequent-increase-rows`（各带 `legacyStorageKeys`，`useF4UnrecordedCheck.ts:49-134`）+ `-audit-note` / `-audit-conclusion` / `-note` | rows ×5 | `useF4UnrecordedCheck`(717) | `rowId`；add/del ×1/×1 |
| F4-8 凭证检查 | `F4-8-debit-rows` / `F4-8-credit-rows` + `-audit-note` / `-audit-conclusion` / `-sample-basis` + 模板化 `F4-8-${section}-check-note` | rows ×2 | `useF4VoucherCheck`(553) | `rowId`；add/del ×1/×1 |
| F4-9 供应商融资 | `F4-9-rows`（主键）+ **7 个 legacy 键**（`F4-9-factoring-rows` / `-note-rows` / `-supply-rows` / `-factoring` / `-note` / `-supply` / `-supplychain`，`useF4SupplierFinancing.ts:118`）+ `-audit-note` / `-audit-conclusion` / `-note-conclusion` | rows（分组） | `useF4SupplierFinancing`(701) | `rowId` + **`groupId`**；`addSupplierGroup` / `addRowInGroup` / `addRow` 三个新增入口 |

🔴 **键名陷阱（按值实测）**：①F4-7 五键里 `-estimated-inbound-rows` / `-unprocessed-invoice-rows` / `-subsequent-increase-rows`
各有 2 个 legacy 别名（`F4-7-receipt` / `F4-7-invoice` / `F4-7-purchase` 等），按 grep 命中数会误以为有 8 个区；
②F4-9 有 **7 个 legacy 键**，`F4-9-rows` 才是主键；③F4-8 读了两个**零写入键** `F4-8-debit-note` / `F4-8-credit-note`
（`useF4VoucherCheck.ts:349/350` 只读、全仓无写入方）⇒ 恒 undefined 的兼容回退，登记不修。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · F4-1 BP-7 同型（rowKey 版）**：`useF4Adjudication.ts:229-230`
`parsed.map((raw:any,index)=> aliases[...] ?? String(raw?.rowKey ?? defaults[index]?.rowKey ?? `custom-${index}`))`
⇒ 旧载荷缺 `rowKey` 时身份退化为 `custom-<下标>`。与 F2 的 `String(r.id||i+1)` 同型（slice BP-7）。
🔴 但 F4-1 是**稳定 key 固定行**（性质 5 行 / 账龄段行），`defaults[index]?.rowKey` 兜底在行序未变时是正确的；
仅当旧载荷行序与 defaults 不一致才错位 ⇒ 风险低于 F2，但受管前仍须判据证明重铸后无 `custom-` 前缀。

**B2 · F4-1 取数口径分歧（FC-5，与 F1-1 / F3-1 三家同型）**

| 区 | 模板 | 前端 `useF4Adjudication` |
|---|---|---|
| 性质区 F/G/H | `SUMIF('明细表F4-2'!$D$11:…, A8, …)` 按款项性质汇总明细 | 由 `F4-2-rows` 聚合 + 逐行手填 AJE/RJE（Task 2 逐字核聚合字段） |
| 账龄区 F / I / G | `F='明细表F4-2'!N32`（未审账龄合计）· `I=!U32`（审定账龄合计）· `G=I-F-H`（**AJE 倒挤**） | 同上 |

⇒ 与 F1-1 裁决同源：受管前须出影响评估。F1/F3/F4 三家同型 ⇒ 建议一次性统一裁决（见需求 6.3）。

**B3 · F4-9 分组容量冲突**：模板固定 **3 组 × 各 4 行**（R12-15 / R17-20 / R22-25）+ 三个小计 + 合计
`F27=F26+F21+F16`（**非 SUM 区间，是三个小计相加**）；前端 `useF4SupplierFinancing` 支持**任意组数、任意组内行数**
（`addSupplierGroup` / `addRowInGroup`，`buildF4FinancingDisplayRows` 现算 subtotal/total）⇒ 组数 >3 或组内行数 >4 时
模板无处承载，且合计公式写死三项相加、插组后不会自动纳入。受管前必须裁决（需求 5.3）。

**B4 · F4-4 不是行表**：区①周转率是**固定 12 行**（R12-23，`inputs: Record<key,number>` dict）；区②前十名是**模板写死
10 行**（债权人1~10，R26-35）且前端行**派生自 F4-2**、只存 `reason` 覆盖 ⇒ 两区都不是「动态行 + 行身份」形态。
按 FC-4 三元组判定：**无 `-rows` 键、无 addRow/removeRow** ⇒ 不进行表引擎，候选 `static_region`（区①）+ 派生只读（区②）。

**B5 · FC-11（prefill `items` 型死配置）在 F4 的三块**：`[224]` `附注披露信息(上市公司)` · `[225]`
`附注披露信息（国企）`（**全角**，模板真名半角）· `[307]` `附注披露信息(国企)`（半角，正确）—— 三块 `cells` 全空、公式在
`items` 里（各 2 条）⇒ 运行时不预填、公式管理页看不到。`[225]` 与 `[307]` 还是重复块 ⇒
`test_sheet_exists_in_source_xlsx[F4]` 红。FC-11 工具链根因由 F3 spec 修，本 spec 只迁移 F4 三块的数据。

**B6 · FC-10 在 F4 不命中（与 F3 相反，实测结论）**：F4 模板所有百分比格式列都是**公式列**（F4-1 `K` 变动率、
F4-4 `E` 变动比例、F4-8 `G` 检查比例，逐格实测），走 `mode=formula` 不回写 ⇒ 不存在「前端百分数写入模板小数格」的路径。
⇒ 本 spec **不需要** FC-10 换算前置，是四个 F spec 里唯一没有该阻塞的（F1 有 F1-7 O 列、F2 有 F2-47、F3 有四列）。

**B7 · F4-7 区① `G=365/(E{r}/F{r})` 除零**：E（本期贷方）为 0 时 Excel 产出 `#DIV/0!`。按值读 `excel_extract.py:3400-3431`
实测行为：extract 对**所有**字段（含 `mode=formula` 的受保护字段）都读值并 `normalize_value`，失败时记
`SchemaAnomalyKind.type_normalization_failure` 并**保留原值**（不崩）；`PROTECTED_MODES={formula, auto_source}` 使该值
不合并回 store。⇒ 真实后果不是崩溃或脏数据，而是**每次 extract 都产出一条异常记录**。需求 4.4 的判据须钉住这一行为
（构造 E=0 行 ⇒ 不崩 + 异常类型为 `type_normalization_failure` + store 中该字段不出现 `#DIV/0!`），而不是笼统写「不崩」。

**B8 · F4-2 前端已对齐模板（正面事实，登记为参照）**：`useF4Detail.computeF4DetailRow:301` 注释
「源表 K 列以期初未审余额（E）为起点，而非期初审定余额（H）」+ `calcCreditBalance(stored.openingUnadjusted, …)`
⇒ 与模板 `K=E+J-I` 一致。**这是 F 循环里唯一主动对齐过模板的明细表**，可作 F1-2（红基线 B1）修复的参照写法。

## Glossary

沿用 F1 spec Glossary；新增：

| 术语 | 含义 |
|------|------|
| 分组表 | 行按业务分组、每组带小计、末尾总计的形态（F4-9）；模板组数固定而前端可变时构成容量冲突 |
| 派生只读区 | 行来自别张 sheet 的派生、本表只存局部覆盖字段（F4-4 区②前十名只存 `reason`） |
| legacy 别名键 | 同一区的历史 store 键（F4-7 三区各 2 个、F4-9 共 7 个），读时回退、写时只写主键 |
| 除零公式列 | 模板公式可能产出 `#DIV/0!` 的列（F4-7 区① G），extract 须容错 |

## Requirements

### Requirement 1: F4 首张 canary —— 从零打通真双向（F4-6 关联方及交易检查表）

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`关联方及交易检查表F4-6`**（25r×Q / 17 公式 / 表头 R6 / 数据 R7-11 /
   footer R12「合计」/ 键 `F4-6-rows` / UUID **M**）—— 与 F1-6、F3-6 三家同型（单级表头 + 1 公式列 + 零跨 sheet + 无 FC-10），
   失败面最小且一次验通可在三个 spec 间复用写法。
2. WHEN 建 provider THEN SHALL 新建 `phase5_f4_accounts_payable.py`；`assert_entry_selectable(*, resolution, manifest=None)`
   照 D3 同签名（`resolution` 必填、无关闭开关、真 manifest 真调）；`build_matcher()` =
   `EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)`；`build_registration` 照 `phase5_d3_prepaid_receipts.py:830`，
   并有**真构造**判据（E1 WIP 反例：缺 `document_type` 即 `TypeError`）。
3. 🔴 WHEN 声明 `WP_CODES` THEN SHALL 取 manifest 幻影码 `{"F4A"}`，并 SHALL 有一条**专门判据**钉死其与真实程序表码
   `F4A`（`wp_code_overrides.json:549` → `f4-accounts-payable`）的隔离：①`_index.json` 中无 `F4A` 条目（finder 零命中）
   ②`assert_no_implicit_template_fallback` 对 `F4A` 通过 ③provisioner 用裁决文件的真码 `["F4"]`、不用幻影码查 wp_index。
   变异：用幻影码去 `find_template_file` / JOIN `wp_index` ⇒ 必红。
4. WHEN 契约发布 THEN SHALL 走完整五环链路；第③环缺供给时如实登记 `upstream_gap`（BP-61-1），不伪造通过。
5. WHEN adapter 注册成功 THEN manifest `migration_state` SHALL 变为 `adapter_registered`、三条 `legacy_reasons` 全消。
6. WHEN 宿主接桥 THEN `GtF4AccountsPayable.vue` SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
   （`.oo-container` 确定高度、`flushHtml` 先 `flushPendingSave()`），保留 legacy 给未接 sheet，受管集合从 provider 派生。
7. WHEN 真栈验收 THEN SHALL 达三谓词并留 DB 证据；真库 `F4-2-rows`（4 行带 rowId）可作真数据 roundtrip 样本。

### Requirement 2: 形态判定先行（三元组实证）

1. WHEN 判定形态 THEN SHALL 用前端三元组，不用模板公式数。实测结论：F4-2/5/6/7（五区）/8（双区）/9 为 `excel_table` + `rowId`；
   F4-1 两区为 `excel_table` + 稳定 `rowKey`；**F4-4 两区都不是行表**（无 `-rows` 键、无 addRow ⇒ 见需求 5.4）。
2. WHEN 声明 `store_item_id` THEN SHALL 逐字等于按值 grep 实测的**主键**（不取 legacy 别名）；变异 SHALL 含
   ①`F4-7-estimated-inbound-rows → F4-7-receipt`（legacy 别名）②`F4-9-rows → F4-9-factoring-rows` 并证明打红。
3. WHEN 某区有 legacy 别名键 THEN 契约 SHALL 只声明主键；读回退由前端保留，**不得**把别名也声明为受管区（会造成一区两 binding）。
4. WHEN footer 之下有 note/conclusion THEN 登记 HTML-only；F4-8 读的两个零写入键（`F4-8-debit-note` / `-credit-note`）
   SHALL 登记为「恒 undefined 的兼容回退」，不进 field_specs、不修。

### Requirement 3: F4-2 明细表（两级表头 + nested 账龄 ×2）

1. WHEN 声明 F4-2 THEN SHALL 用 `RowTableSheetSpec`：`F4-2-rows` / `rowId` / 两级表头 R9/R10 / 数据 R11-31 /
   footer R32「合计」/ UUID **AB** / `formula_columns=("H","K","M","T")` /
   `FORMULA_TEMPLATES={"H":"=E{r}+F{r}+G{r}","K":"=E{r}+J{r}-I{r}","M":"=K{r}+L{r}","T":"=M{r}+R{r}+S{r}"}`；
   账龄 `aging_layout=nested`、两组 `N-Q`（未审）/ `U-X`（审定）。
2. WHEN 字段键 THEN SHALL 逐字取 `useF4Detail.StoredAPDetailRow`；派生列按 FC-7 核（模板无公式而 HTML 派生者不得标 `editable`）。
3. WHEN 账龄口径为 `FIVE_YEAR` / `CUSTOM` THEN 同 F1 需求 3.3：模板只有 4 列账龄格 ⇒ 仅 THREE_YEAR 启用受管，
   非 THREE_YEAR 降级并中文提示，不得在 OO 往返中丢弃第 5 段起的金额。
4. WHEN footer 之下 R33 账龄校验行 THEN 不受管（纯公式）。
5. WHEN F4-2 回写 THEN 下游 SHALL 正确重算：`useF4Adjudication`（F4-1 两区聚合）· `useF4SubstantiveAnalysis`（F4-4 前十名派生）·
   `useF4LongOutstanding` · `useF4RelatedParty` · `useF4VoucherCheck` · `useF4SupplierFinancing`（供应商候选）·
   `useF4DisclosureListed` / `-SOE`（按值 grep 9 处引用，Task 2 补全清单）。

### Requirement 4: F4-5 / F4-8 / F4-7（单区 + 双区 + 五区）

1. WHEN 声明 F4-5 THEN `F4-5-rows` / 表头 R8 / 数据 R9-14 / footer R15「合计」/ UUID **L** / `formula_columns=()`
   （数据区零公式）；🔴 I 列「审定金额」若前端自动派生（同 F1-5 J 列）SHALL 按 FC-7 判 `auto_source`，Task 2 按值核。
2. WHEN 声明 F4-8 THEN 两个 spec：区① `F4-8-debit-rows`（表头 R15/R16 / 数据 R17-37 / footer R38）· 区②
   `F4-8-credit-rows`（R40/R41 / R42-57 / R58）；UUID **S**；两区列集按 Task 2 逐格实测（不假设相同）。
3. WHEN 声明 F4-7 THEN SHALL **五个** spec，与五个 store 主键一一对应（区①~⑤ 的表头/数据/footer 见 requirements 五区表）；
   🔴 五区**列集与表头层级都不同**（区① 单级表头 11 列、区②~⑤ 两级表头 10~11 列）⇒ SHALL 各自声明 `field_specs`，
   不得共用；区①`formula_columns=("F","G","I")`、区②`("F",)`、区③④⑤`()`。
4. 🔴 WHEN F4-7 区① G 列（`=365/(E{r}/F{r})`）THEN SHALL 有判据覆盖除零行为（红基线 B7）：构造 E=0 的行后
   ①extract 不崩 ②异常类型为 `type_normalization_failure` ③store 中该字段不出现 `#DIV/0!` 字符串。
5. WHEN F4-7 / F4-8 多区同 sheet THEN SHALL 走兄弟 Table ref 位移；任一区插行后其余区 footer SUM 区间随位移、数据不变。

### Requirement 5: F4-9 分组表 + F4-4 非行表两区（裁决后再定）

1. WHEN 核 F4-9 THEN SHALL 先裁决容量冲突（红基线 B3）：模板固定 3 组 × 4 行 + 合计 `F27=F26+F21+F16`（三小计相加）
   vs 前端任意组数/行数。默认裁决：**组数 ≤3 且各组行数 ≤4 时启用受管**，超限整表降级 legacy + 中文提示；
   不得为适配前端而改模板合计公式（那会改变权威模板语义）。
2. WHEN F4-9 受管（限额内）THEN 行身份 SHALL 同时保留 `rowId`（行）与 `groupId`（组）；组小计行 SHALL 不受管（模板公式）。
3. WHEN 超限 THEN 降级判据 SHALL 可观测（capability 说明含「供应商组数或组内行数超过模板容量」）。
4. WHEN 核 F4-4 THEN 按红基线 B4：区①周转率（固定 12 行、dict `inputs`）候选 `static_region`；区②前十名
   （模板写死 10 行、前端派生自 F4-2 且只存 `reason` 覆盖）候选**派生只读 + 局部覆盖**。两区都 SHALL 先做可行性核，
   **不得**塞进行表引擎；核后产裁决与证据，不改生产代码。

### Requirement 6: F4-1 审定表（最后接）+ F4-3 核

1. WHEN 声明 F4-1 THEN SHALL 用 **两个** `RowTableSheetSpec`（不是 `AdjudicationSheetSpec` —— store 是两个行数组、
   行身份是稳定 `rowKey`，同 F3-H3 裁决）：性质区 `F4-1-adj-nature-rows`（表头 R6/R7 / 数据 R8-12 / footer R13）·
   账龄区 `F4-1-adj-aging-rows`（R15/R16 / R17-21 / R22）；两区同 sheet 走兄弟 Table ref。
2. 🔴 WHEN 行身份 THEN 受管前 SHALL 修红基线 B1 的 `custom-${index}` 回退，并有判据证明重铸后无 `custom-` 前缀行。
3. 🔴 WHEN 取数口径（红基线 B2）THEN 受管前 SHALL 出影响评估；F1-1 / F3-1 / F4-1 三家同型 ⇒ 评估 SHALL 一次覆盖三家
   并给出统一裁决（建议在 F1 spec 需求 7.3 的影响评估中并入 F3/F4，避免三份 spec 各裁一次互相不一致）。
4. WHEN F4-1 受管 THEN FC-9 TB 红线：sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（`F4TabAdjudication.vue:218`）
   仍是唯一入口；变异「sync 回写里调 publishToTb」SHALL 必红。
5. WHEN 核 F4-3 THEN 照 FC-6 默认 `single_html`，只产裁决与证据（`F4TabAdjustment.vue:100 useAdjustmentCentralSync`）。

### Requirement 7: 公式管理、prefill 修复与零回归

1. WHEN 提供公式管理入口 THEN SHALL 消费 F-SHELL，不在 F4 宿主新建第二个 owner；判据覆盖两种渲染模式下入口可达。
2. 🔴 WHEN 修 prefill（红基线 B5）THEN SHALL：①`[224]` / `[225]` / `[307]` 三块的 `items` 迁为 `cells`（FC-11 数据侧）
   ②删全角重复块 `[225]`、保留半角 `[307]` ③`test_sheet_exists_in_source_xlsx[F4]` 转绿。
   工具链根因（`_ensure_cells` 造 `items`）由 F3 spec 修，本 spec **依赖**其完成、不重复改。
3. WHEN 声明 `formula_columns` THEN SHALL 与模板逐格实测一致，mask 由引擎现算；F4-1 两区各自的公式列集合按区实测
   （不得把性质区的列集套到账龄区）。
4. WHEN F4 provider 纳入 THEN 既有 contract golden digest **逐项不变**（🔴 **现算基线，不写死数字** —— 依 G 循环裁决 GC-10：契约目录已从 10 涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1），写死数字的判据下次交付即 stale；判据形态应为「非本 spec 的 digest 逐项比对」，不断言集合大小）；F4 进 `check_sync_provider_golden_digest.PROVIDERS`；
   登记点（`DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` / `store_item_registry` plan / wp_code 裁决 /
   overlay + 重生 manifest）同步。
5. WHEN 未接 sheet 切在线编辑 THEN SHALL 保持 legacy 并显式登记为假双向。
6. WHERE F4 无 FC-10 命中（红基线 B6）THE 本 spec SHALL **不引入** FC-10 前置，但 Task 2 SHALL 出证据证明该结论
   （逐列核百分比格式列均为公式列），避免「以为不命中」。

### 不在本 spec 范围

- 修订说明（hidden）/ 底稿目录 / `应付账款实质性程序表F4A` / 两张附注披露 / GT_Custom。
- FC-11 工具链根因（F3 spec）；F3 / F5 的 items 型块。
- F1-1 / F3-1 / F4-1 三家统一口径裁决的**执行**（本 spec 只提出并参与评估，落地随三家各自的审定表任务）。
- 模板覆盖层本身、发布链平台级供给（BP-61-1）。
