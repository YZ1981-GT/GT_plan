# Requirements Document

## Introduction

本 spec 把 **F3 应付票据**从 legacy 假双向接成真双向，覆盖其**唯一一册**模板 `F/F3 应付票据.xlsx` 内可表达的 sheet。
它是 umbrella Task 48 的下游 lane spec；F 循环共同裁决 **FC-1~FC-13** 见
`f1-sync-coverage-and-first-canary/design.md` §F 循环共同裁决（本 spec 引用、不复述，**FC-11 由本 spec 首次提出**）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`F3-P{N}`**。

F3 与 F1/F4 结构近亲（审定表 + 明细表 + 调整分录 + 关联方 + 三区检查表），但有三处 F1/F4 都没有的形态：
① 审定表 store 是**按 `rowKey` 的行数组**（F1-1 是 per-cell、F4-1 是两个行数组）；② 有一张**利息测算表**（F3-4）；
③ 类别枚举**前端 5 个 vs 模板 4 槽**（红基线 B3）。

### F3 当前状态实测（manifest + slice + 真库，2026-09-26）

```
entry_id            xlsx/gt-f3-notes-payable
host_path           audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue
independent_entry   true     mount_count  2     parent_entry_id  null
capability          single_onlyoffice        migration_state  legacy_fake_bidirectional  🔴
adapter_id          null     html_store  "unresolved"
wp_code_patterns    ["F3N"]  ← 幻影码；真码 F3（wp_index 4 行）
scenario_profile    xlsx.editable.shared.single.room_service_wired.v1
legacy_reasons      template_only_open / no_durable_forcesave_ack / missing_adapter
template_ref        F/F3 应付票据.xlsx
```

| 事实 | 实测 |
|---|---|
| provider / 契约 | ❌ 无 `phase5_f3_*.py`、无 `f3.*.json` |
| 发布链供给 | `working_paper_sync_entry_state` F 循环 0 行 |
| wp_code 裁决 | 文件中 F 循环 0 条 |
| 宿主接桥 | `GtF3NotesPayable.vue` 两处 legacy `<GtOnlyOfficeSheet>`（L40 模式切换 / L252 兜底）+ `GtEntrySyncCapabilityNotice`；零 `useWorkpaperSyncBridge` |
| 公式管理 | 宿主 emit `open-formula-manager` 0 次；页面级入口由 F-SHELL 提供；`wp_formula` 表 F3 0 行 |
| TB 发布门 | ✅ `useF3Adjudication.ts:318 publishToTb()` → `publish-to-tb`（`sheet_name='审定表F3-1'`、科目 2201、`amount_kind=balance`）；旧 `f3:writeback-trial-balance` 监听已移除 |
| 调整分录中央同步 | ✅ `F3TabAdjustment.vue:36 useAdjustmentCentralSync` ⇒ F3-3 是 hub（FC-6） |
| 真库载荷 | 仅 `F3-5-rows`（675 B，wp_code=F3）；F3-1/2/3/4/6/7 全 0 行 |

### 模板实测：1 册 / 12 sheets（sha256 `06de707b…3a6b`，79,616 B）

| sheet | state | 尺寸 | 公式 | 表头 / 数据 / footer（逐格实测） | 形态 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | visible | 21r×H | 0 | — | 导航 | 不接 |
| 🔴 `应付票据实质性程序表F3A␠` | visible | 33r×M | 6 | — | 步骤清单（**sheet 名末尾有空格**） | 不接 |
| **审定表F3-1** | visible | 48r×L | 34 | 表头 R6；数据 **R7-10**（R7 银行 / R8 商业 / **R9-10 空槽**）；合计 **R11**；试算 R12；差异 R13 | 行数组（稳定 rowKey） | ✅ 最后接 |
| 附注披露信息(上市公司) | visible | 13r×P | 12 | R7/R8 引 F3-1!I7/E7 | 披露 | 不接 |
| 附注披露信息(国企) | visible | 11r×E | 12 | 同上 | 披露 | 不接 |
| **明细表F3-2** | visible | 44r×Y | 48 | 两级表头 **R13/R14**；数据 **R15-30**；footer **R31「合␠␠计」** | 行表 | ✅ **canary 候选** |
| 调整分录汇总F3-3 | visible | 24r×J | 7 | 表头 R5；空白 R6-20 | hub | 🔍 FC-6 |
| **应付票据（带息）利息测算表F3-4** | visible | 37r×M | 53 | 两级表头 **R9/R10**；数据 **R11-31**；footer **R32「合␠␠计」** | 行表 | ✅ |
| **逾期票据检查F3-5** | visible | 29r×O | 10 | 两级表头 **R5/R6**；数据 **R7-21**；footer **R22「合计」** | 行表 | ✅ **canary** |
| **关联方及交易检查表F3-6** | visible | 26r×P | 18 | 表头 **R6**；数据 **R7-12**；footer **R13「合计」**；R18-26 关系类型下拉源（「勿改、勿删」） | 行表 | ✅ |
| **应付票据检查表F3-7** | visible | 92r×R | 22 | 三区：R15/R16 · **R17-36** · **R37**；R39/R40 · **R41-58** · **R59**；R61/R62 · **R63-79** · **R80** | 三区行表 | ✅ |
| GT_Custom | hidden | 8r×B | 0 | — | 平台注入区 | 不接 |

**逐格实测公式：**

| 位置 | 公式 |
|---|---|
| F3-1 R7 | `B=SUMPRODUCT(('明细表F3-2'!$B$15:$B$30=$A7)*('明细表F3-2'!L$15:L$30))`；C/D 空（可编辑）；`E=B7+C7+D7`；F/G/H/I 同型 SUMPRODUCT 取明细 O/P/Q/R |
| F3-1 R9/R10 | 仅 `E=B+C+D`、`I=F+G+H`（**空槽行无 SUMPRODUCT**） |
| F3-1 R11/R13 | `SUM(7:10)` 逐列；`E13=E11-E12`、`I13=I11-I12` |
| F3-2 R15 | `O=L15+M15-N15`（期末未审）、`R=O15+P15+Q15`（期末审定） |
| F3-2 R31 | L..S 及 V 逐列 `SUM(15:30)` |
| F3-4 R11 | `H=ROUND(F11*G11,2)`（应计利息）、`J=H11-I11`（差异） |
| F3-5 R22 | `SUM(J/K/O 7:21)` |
| F3-6 R7 | `G=D7+F7-E7`（期末余额 = 期初 + 贷方 − 借方）；R13 `SUM(7:12)` |
| F3-7 footer | R37 `SUM(F/L 17:36)`；R59 `SUM(F/N 41:58)`；R80 `SUM(F/L 63:79)` |

模板**无 Excel Table**、**零 definedName**。数据验证：F3-2 `B15:B30`「银行承兑汇票,商业承兑汇票」+ `C15:C30` 关联方三枚举 +
`K15:K30`/`T15:T30`「是,否」；F3-3 `B6:B20`「账项调整,报表调整,其他」；F3-4 `A11:A31` / F3-5 `A7:A21` / F3-6 `C7:C12` /
F3-7 `G17:G36 G41:G58 G63:G79` 均为票据类别两枚举；F3-6 `B7:B12` ← `$B$19:$B$26`（绝对引用，footer 之下）。

**UUID 候选列（逐格实测数据区 + 表头全空）**：F3-2 **X**（W 备注、max_col Y）· F3-4 **L**（K 说明）· F3-5 **P**
（O 是「抵押情况-金额」有 SUM，非空列）· F3-6 **N**（M 备注）· F3-7 **S**（R 是「检查的关键证据…」说明列）。

### F3 store 键实测（按值 grep；`_probe_f_keys.py F3`）

| sheet | store 键 | 形态 | 写入方 | 行身份 / 增删 |
|---|---|---|---|---|
| F3-1 审定表 | **`F3-1-adj-rows`**（行数组，按 `rowKey` 索引）+ `F3-1-adj-tb-2201` / `-adj-note` / `-adj-conclusion` | rows（稳定 key） | `useF3Adjudication`(437) | `rowKey` ∈ `bank/commercial/letter_of_credit/supplychain/other`；无 add/del（按需 push 类别行） |
| F3-2 明细 | `F3-2-rows` + `F3-2-note` / `-conclusion` | rows | `useF3Detail`(362) | `rowId`（`raw.rowId \|\| raw.id \|\| generateRowId()`）；add/del ×1/×1 |
| F3-3 调整分录 | `F3-3-rows` + `F3-3-note` / `-conclusion` | rows（hub） | `useF3Adjustment`(153) + `f3AdjustmentInject`（F3-4/F3-5 注入拟调整分录） | `rowId`；add/del ×1/×1 |
| F3-4 利息测算 | `F3-4-rows` + `F3-4-note` / `-conclusion` | rows | `useF3InterestCalc`(304) | `rowId`；add/del ×1/×1 |
| F3-5 逾期检查 | `F3-5-rows` + `F3-5-note` / `-conclusion` | rows | `useF3OverdueCheck`(324) | `rowId`；add/del ×1/×1 |
| F3-6 关联方 | `F3-6-rows` + `F3-6-note` / `-conclusion` | rows | `useF3RelatedParty`(259) | `rowId`；add/del ×1/×1 |
| F3-7 检查 | 区① **`F3-7-debit-rows`** · 区② `F3-7-credit-rows` · 区③ `F3-7-subsequent-rows` + `F3-7-note` / `-conclusion` + 模板化 `F3-7-${section}-check-note` | rows ×3 | `useF3VoucherCheck`(447，L70-72) | `rowId`；add/del ×1/×1 |

🔴 **键名陷阱（按值实测）**：①F3-7 区③键名是 **`subsequent`** 不是 `post`（F1-7 是 `post`）；②`F3-7-debit` / `-credit` /
`-subsequent`（无 `-rows` 后缀）是**导入导出 sheet 标识**（`useF3ImportExport.ts:16-18` + `cycleImportExportRegistry`），
不是 store 键；③F3-1 的键是 `F3-1-adj-rows` 而非 F1 式 `F3-adj-*` per-cell。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · FC-11（本 spec 首次提出）：prefill 预设的 `items` 型块在运行时是死配置**

全库 308 个 mapping 块中有 **7 个块 `cells` 为空数组、公式写在 `items` 里**，且**全部属 F3/F4/F5**：

| 块 | wp_code / sheet | items |
|---|---|---|
| `[222]` / `[223]` / `[306]` | F3 `附注披露信息(上市公司)` / `附注披露信息（国企）`(全角) / `附注披露信息(国企)`(半角) | 2 / 2 / 2 |
| `[224]` / `[225]` / `[307]` | F4 同上三块 | 2 / 2 / 2 |
| `[226]` | F5 `营业务成本审定表F5-1` | **14** |

运行时四个消费方**全部只读 `cells`**（按值实测）：`wp_template_init_service.py:670`（预填写入 xlsx）·
`preset_library.py:163`（公式管理页预设）· `formula_reverse_index.py:294`（反向索引建边）·
`linkage_graph_builder.py:214`（依赖图）⇒ 这 14+12 条公式**在公式管理页看不到、不预填、不建边**。
实证：`convert_prefill_presets()` 现算统计 `workpaper:F0=2 / F1=33 / F2=78 / F3=18 / F4=18`，**F5 完全缺席**
（F5 唯一的块 `[226]` 是 items 型）。

🔴 **产生机制**：`fix_f_cycle_prefill_presets.py` 的 `_ensure_cells`（L418-L423）在块无 `cells` 键时**创建 `items` 键**
（`block["items"] = []; items_key = "items"`），且 `--check` 也兼容读 `items` ⇒ 修复脚本自己造出运行时读不到的键，
`--check` 还报 exit 0「全部到位」。这解释了三个 F 脚本 `--check` 全绿而红测试全红的矛盾。

**B2 · prefill 重复块 + 全角 sheet 名**：F3 有 `[223]`（全角 `附注披露信息（国企）`，模板真名是**半角**）与 `[306]`
（半角，正确）两个同义块 ⇒ `test_sheet_exists_in_source_xlsx[F3]` 红。F4 同型（`[225]` / `[307]`）。

**B3 · F3-1 类别槽位容量冲突**：模板数据区 **R7-R10 共 4 槽**（R7 银行 / R8 商业 / R9-R10 空），而前端
`F3_CATEGORY_META` 有 **5 个类别**（`bank` / `commercial` / `letter_of_credit` / `supplychain` / `other`，
`useF3CrossSheet.ts:48-54`），且 `useF3Adjudication.ts:155` 会在明细出现对应类别时**动态 push 行**
⇒ 五类同时出现时第 5 行在模板中无槽位。受管前必须裁决（需求 6.2）。

**B4 · F3-1 取数口径分歧（FC-5，与 F1-1 同型）**

| 列 | 模板（R7 按值直读） | 前端 `useF3Adjudication.computeRow`(L105-L107) |
|---|---|---|
| B 期初未审 | `SUMPRODUCT(明细 B=类别 × 明细 L)` = Σ明细**期初余额** | `openingUnadjusted` 手填 / 四表预填 |
| F 期末未审 | `SUMPRODUCT(… × 明细 O)` = Σ明细**期末未审** | `calcCreditBalance(openingAdjusted, periodCredit, periodDebit)` = **期初审定**+贷−借 |
| G / H 期末账项 / 重分类调整 | `SUMPRODUCT(… × 明细 P / Q)` = Σ明细调整 | `closingAje` / `closingRje` **逐行手填** |

⇒ 受管后 B/F/G/H/I 在两种模式下不是同一个数；且明细 P/Q 与 F3-1 手填 AJE/RJE 构成**双写入源**（真库两键均 0 行，尚未暴露）。

**B5 · F3-4 应计利息口径分歧（FC-5）**：模板 `H11=ROUND(F11*G11,2)`（面值 × 利率，**不含天数**）；前端
`computeInterestRow`（`useF3InterestCalc.ts:82-88`）在 `termDays>0` 时算 `faceValue*rate/100*days/360`，仅当无日期时
退化为 `ROUND(F*G/100)`。前端自身注释（L6-L7）已承认「无日期时…与源表 ROUND(F*G,2) 一致」⇒ **有日期时必然不一致**。
另叠加 FC-10：模板 `G11` 格式 `0.00%`（期望小数）而前端存百分数 ⇒ 两层偏差叠乘。

**B6 · FC-10 命中清单（模板百分比格式 × 前端百分数存储）**

| sheet | 列 | 模板格式 | 前端字段（按值） |
|---|---|---|---|
| F3-2 | J 票面利率 | `0%` | `interestRate` 标签「票面利率(%)」（`useF3Detail.ts:84`） |
| F3-2 | U 票据保证金比例 | `0.00%` | `depositRate` 标签「(%)」（L101） |
| F3-4 | G 票面利率 | `0.00%` | `interestRate`，`calcInterest` 内 `/100`（`useF3NotPayFormulaEngine.ts:12`） |
| F3-5 | I 票面利率 | `0.00%` | `interestRate`（`useF3OverdueCheck.ts:113`） |

**B7 · 已修缺陷（本 spec 创建前，同会话修复，登记以防回归）**：`useF3CrossSheet.aggregateDetailByCategory` 的累加器与
`activeCategoryKeys` 原手写四键、漏 `letter_of_credit` ⇒ 明细含「信用证」或附注遍历 META 时
`TypeError: Cannot read properties of undefined (reading 'count')`；同时 `buildF3DisclosureClassRows` 无明细时退回期初审定、
与审定表 `computeRow` 口径不符。两者已改为从 `F3_CATEGORY_META` 派生 + 用 F3-1 行的 `periodCredit`/`periodDebit`，
F3 前端 14 文件 206/206 绿。⇒ 本 spec 需求 7.4 要求判据覆盖「累加器键集合 == META 键集合」。

**B8 · `F3-3-rows` 有写无读待复核**：F3 调研登记「有写无读」，但按值 grep 见 `f3AdjustmentInject.ts:24` 与
`F3TabAdjustment.vue:41` 均引用该键 ⇒ Task 2 须按值复核结论，不沿用旧登记（禁推演）。

## Glossary

沿用 F1 spec Glossary；新增：

| 术语 | 含义 |
|------|------|
| FC-11 | prefill 预设的 `items` 型块在运行时是死配置（消费方只读 `cells`）；见本 spec 红基线 B1 |
| 类别槽位 | 审定表按票据类别的固定行位置；模板槽数 < 前端类别数时构成容量冲突（B3） |
| 双写入源 | 同一格既由明细汇总驱动、又由本表手填（F3-1 的 G/H 列） |

## Requirements

### Requirement 1: F3 首张 canary —— 从零打通真双向（F3-5 逾期票据检查）

**User Story:** 作为审计助理，我希望 F3 切「在线编辑」后在 OO 里改的数能真正写回结构化视图。

#### Acceptance Criteria

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`逾期票据检查F3-5`**（29r×O / 10 公式 / 数据 R7-21 / footer R22「合计」/
   键 `F3-5-rows`）—— 理由见 design 裁决 F3-H1：数据区**零公式**（无 FC-5 分歧面）、真库**唯一有载荷**的 sheet（675 B，
   可做真数据往返）、单区、零跨 sheet 取数。
   🔴 I 列票面利率命中 FC-10 ⇒ canary 阶段 I 列 SHALL 判 HTML-only（不进 `field_specs`），待 FC-10 换算落地后再纳入。
2. WHEN 建 provider THEN SHALL 新建 `phase5_f3_notes_payable.py`；`assert_entry_selectable(*, resolution, manifest=None)`
   照 D3 同签名（`resolution` 必填、无关闭开关、真 manifest 真调）；`WP_CODES={"F3N"}`（幻影码，FC-2）；
   `build_matcher()` = `EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)`；`build_registration` 照 `phase5_d3_prepaid_receipts.py:830`
   （`matcher=` / `declared_capability=Capability.bidirectional`），并有**真构造**判据。
3. WHEN 声明 wp_code 裁决 THEN `workpaper_sync_entry_wp_code_adjudication.json` SHALL 新增 F3 条目
   `wp_codes=["F3"]` + `store_payload_evidence`（`F3-5-rows` 675 B / wp_code=F3 / 1 wp）+ `matcher_domain_conflict=null`。
4. WHEN 契约发布 THEN SHALL 走完整五环链路并在第③环缺供给时如实登记 `upstream_gap`（BP-61-1），不伪造通过。
5. WHEN adapter 注册成功 THEN manifest `migration_state` SHALL 变为 `adapter_registered`、三条 `legacy_reasons` 全消。
6. WHEN 宿主接桥 THEN `GtF3NotesPayable.vue` SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
   （`.oo-container` 确定高度、`flushHtml` 先 `flushPendingSave()`），保留 legacy 给未接 sheet，受管集合从 provider 派生；
   🔴 宿主 `currentSheet` 正则 `/(F3A|F3-\d+)/`（L434）SHALL 不受影响，且 `F3A` 的 sheet 名末尾空格不得被 trim 掉后误配。
7. WHEN 真栈验收 THEN SHALL 达三谓词 `confirm 200` / `forcesave cs_error=0` / `store_mirrored`+`marker_visible` 并留 DB 证据。

### Requirement 2: 形态判定先行（三元组实证）

1. WHEN 判定形态 THEN SHALL 在上游三维谱系内选择；判据是前端三元组，**不用模板公式数**。实测结论：F3-2/4/5/6/7 均为
   `excel_table` + `rowId`；F3-1 是 `excel_table` + **稳定 `rowKey`**（D4-6 / D2-1 范式）；F3 **无** `static_region` 候选。
2. WHEN 声明 `store_item_id` THEN SHALL 逐字等于按值 grep 实测值；变异 SHALL 含 `F3-7-subsequent-rows → F3-7-post-rows`
   与 `F3-5-rows → F3-overdue-rows` 两条并证明打红。
3. WHEN footer 之下有 note / conclusion / 下拉源 THEN SHALL 登记 HTML-only 或保护区，不进 `field_specs`；
   F3-6 的 R18-26「勿改、勿删」关系类型源 SHALL 有判据证明插行后 `B7:B12` 的 `formula1=$B$19:$B$26` 随位移同步。
4. WHEN 两张 footer 标记是「合␠␠计」（F3-2 R31 / F3-4 R32，含两个空格）THEN `footer_marker` SHALL 逐字带空格
   （D6-9 先例：`footer_marker="合  计"`），不得写成「合计」。

### Requirement 3: F3-2 明细表（两级表头 + FC-10 两列）

1. WHEN 声明 F3-2 THEN SHALL 用 `RowTableSheetSpec`：`store_item_id="F3-2-rows"` / `row_identity_key="rowId"` /
   两级表头 R13/R14 / 数据 R15-30 / footer R31「合␠␠计」/ UUID 列 **X** / `formula_columns=("O","R")` /
   `FORMULA_TEMPLATES={"O":"=L{r}+M{r}-N{r}","R":"=O{r}+P{r}+Q{r}"}`。
2. WHEN 字段键 THEN SHALL 逐字取自 `useF3Detail.StoredF3DetailRow`（23 字段，L107-L131），派生列
   （`termDays` / `maturityBucket` / `isOverdue` / `closingUnadjusted` / `closingAdjusted`）区分处置：模板有公式的走
   `mode=formula`；模板无公式而 HTML 派生的（`termDays` / `maturityBucket` / `isOverdue`）按 **FC-7** 判 `auto_source`，
   不得标 `editable`。
3. 🔴 WHEN J 列（票面利率）与 U 列（保证金比例）THEN 命中 FC-10 ⇒ 受管前 SHALL 落地单位换算裁决；未落地前两列判 HTML-only。
4. WHEN 下游消费方 THEN 回写后 SHALL 正确重算：`useF3Adjudication`（F3-1 跨表聚合）· `useF3CrossSheet`（附注分类行）·
   `useF3DisclosureListed` / `-Soe` · `useF3VoucherCheck`（读 `F3-2-rows` 取账面基准），清单由 Task 2 补全（按值 grep 6 处引用）。

### Requirement 4: F3-4 利息测算表（口径分歧 + FC-10 叠加）

1. WHEN 声明 F3-4 THEN SHALL 用 `RowTableSheetSpec`：`F3-4-rows` / 两级表头 R9/R10 / 数据 R11-31 / footer R32「合␠␠计」/
   UUID 列 **L** / `formula_columns=("H","J")` / `FORMULA_TEMPLATES={"H":"=ROUND(F{r}*G{r},2)","J":"=H{r}-I{r}"}`。
2. 🔴 WHEN 应计利息口径（红基线 B5）THEN 受管前 SHALL 裁决并落地：模板不含天数、前端含 `days/360`。按 FC-5 以模板为权威
   意味着**丢掉天数折算**（审计上更粗），故本条 SHALL **先出业务影响评估**（列出真库/典型场景下两式差额）再定方向：
   ①改前端对齐模板 ②经模板覆盖层把模板改为含天数 ③H 列判 HTML-only 暂不受管（默认③，风险最低）。
3. WHEN G 列命中 FC-10 THEN 与需求 3.3 同处置。
4. WHEN F3-4 向 F3-3 注入拟调整分录（`injectF3Adjustments(…, 'interest-accrual')`，L289）THEN 受管后该注入 SHALL 幂等、
   不因 OO 回写重复注入（判据：同一 variance 连续两次回写后 `F3-3-rows` 条数不变）。

### Requirement 5: F3-6 关联方 + F3-7 三区检查表

1. WHEN 声明 F3-6 THEN `F3-6-rows` / 表头 R6 / 数据 R7-12 / footer R13「合计」/ UUID **N** /
   `formula_columns=("G",)` / `FORMULA_TEMPLATES={"G":"=D{r}+F{r}-E{r}"}`（贷方科目：期初 + 贷方 − 借方）。
   前端 `recalcRelatedPartyRow` SHALL 与该式逐字核等价（FC-5）。
2. WHEN 声明 F3-7 THEN SHALL 三个 spec，同 `managed_sheet`、不同 `sheet_key` / `store_item_id` / 行段：
   区① `F3-7-debit-rows`（R17-36 / footer R37）· 区② `F3-7-credit-rows`（R41-58 / R59）· 区③ `F3-7-subsequent-rows`
   （R63-79 / R80）；UUID 列 **S**；三区**列集不同**（区①③ H..L 为付款审批单/银行回单，区② H..N 为入库单/发票），
   SHALL 各自声明 `field_specs`。
3. WHEN F3-7 三区同 sheet THEN SHALL 走兄弟 Table ref 位移，且任一区插行后另两区 footer SUM 区间与数据验证随位移同步。
4. WHEN F3-7 有 `F3VoucherCheckDialog` OCR 入口 THEN SHALL 按 FC-8 实测写入粒度（单表单 vs 整表替换），结论落证据。

### Requirement 6: F3-1 审定表（最后接；槽位 + 口径两处硬前置）

1. WHEN 声明 F3-1 THEN SHALL 用 `RowTableSheetSpec`（**不是** `AdjudicationSheetSpec` —— store 是行数组、行身份是稳定
   `rowKey`，与 D2-1 `fixed_rows` 同型）：`F3-1-adj-rows` / `row_identity_key="rowKey"` / 表头 R6 / 数据 R7-10 /
   footer R11「合计」/ `formula_columns=("B","E","F","G","H","I")`（R7/R8 六列均为公式；R9/R10 仅 E/I 有公式）。
   🔴 R7/R8 与 R9/R10 的公式集合不同 ⇒ `formula_mask` SHALL 按**行**实测（引擎按 `formula_columns × 数据行区间`
   现算的矩形 mask 在此**过宽**），须裁决：拆两个 spec（R7-8 / R9-10）或引入行级 mask 声明位。
2. 🔴 WHEN 类别槽位容量（红基线 B3）THEN 受管前 SHALL 裁决：①模板经覆盖层扩到 5 槽 ②前端限制同时展示 ≤4 类
   ③仅当实际类别数 ≤4 时启用受管（默认③ + 超限时中文降级提示）。
3. 🔴 WHEN 取数口径（红基线 B4）THEN 受管前 SHALL 落地 FC-5：B/F/G/H/I 以模板 SUMPRODUCT 为权威；改动会把 F3-1 的
   期末 AJE/RJE 从「手填」变为「汇总明细 P/Q」⇒ 须同步 `detailCrossValidation` 与 `publishToTb` 的金额来源判据。
   🔴 **影响评估与方向裁决不在本 spec 独立做** —— F1-1 / F3-1 / F4-1 三家同型，统一裁决在
   `f1-sync-coverage-and-first-canary` 需求 7.3（真库 F3-1 键 0 行 ⇒ F3 侧评估成本最低，可作三家中的对照样本）；
   本 spec 只负责按统一结论落地 F3-1 那张。
4. WHEN F3-1 受管 THEN FC-9 TB 红线：sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（科目 2201、
   `sheet_name='审定表F3-1'`）仍是唯一入口；变异「在 sync 回写里调 publishToTb」SHALL 必红。

### Requirement 7: 公式管理、prefill 修复与零回归

1. WHEN 提供公式管理入口 THEN SHALL 消费 F-SHELL，不在 F3 宿主新建第二个 owner；判据覆盖两种渲染模式下入口可达。
2. 🔴 WHEN 修 prefill（红基线 B1/B2）THEN SHALL：①把 `[222]`/`[223]`/`[306]` 三块的 `items` 迁为 `cells`（FC-11）
   ②删除全角重复块 `[223]`、保留半角 `[306]`（模板真名半角）③修 `fix_f_cycle_prefill_presets.py` 的 `_ensure_cells`
   使其**只写 `cells`**、`--check` 只认 `cells`，并加「块内 `cells` 非空」与「sheet 名 ∈ 模板 tab」两条校验
   ④`test_f_cycle_formula_presets.py::test_sheet_exists_in_source_xlsx[F3]` 转绿。
3. WHEN 声明 `formula_columns` THEN SHALL 与模板逐格实测一致，mask 由引擎现算（F3-1 除外，见需求 6.1）。
4. WHEN 回归守卫 THEN SHALL 保留红基线 B7 已修两处的判据（累加器键集合 == `F3_CATEGORY_META`；附注期末 == 审定表期末）。
5. WHEN F3 provider 纳入 THEN 既有 contract golden digest **逐项不变**（🔴 **现算基线，不写死数字** —— 依 G 循环裁决 GC-10：契约目录已从 10 涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1），写死数字的判据下次交付即 stale；判据形态应为「非本 spec 的 digest 逐项比对」，不断言集合大小）；F3 进 `check_sync_provider_golden_digest.PROVIDERS`；
   登记点（`DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` / `store_item_registry` plan / overlay + 重生 manifest）同步。
6. WHEN 未接 sheet 切在线编辑 THEN SHALL 保持 legacy 并显式登记为假双向。

### 不在本 spec 范围

- 底稿目录 / `应付票据实质性程序表F3A␠` / 两张附注披露 / GT_Custom。
- F4 的 items 型块 `[224]`/`[225]`/`[307]` 与 F5 的 `[226]`（同属 FC-11，各归 F4 / F5 spec）。
- 模板覆盖层本身、发布链平台级供给（BP-61-1）。
