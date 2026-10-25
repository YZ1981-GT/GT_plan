# Requirements Document

## Introduction

本 spec 把 **E1 货币资金**从**当前的 legacy 假双向**接成真双向，并覆盖第一册模板内可表达的 sheet。

🔴 **与 D 类 spec 的差异只有一级，不是「从零 vs 已接」（复盘修正，首版此处判断错误）。**

首版写「D 类每家都已有 1 张明细 `bidirectional_verified`（D1-3/D2-2/D3-2/D4-2/D5-2/D6-2/D7-2），
而 E1 一张都没接」。查 D 循环 slice（`workpaper_sync_d_cycle_manifest_slice.json`，umbrella
Task 46 冻结）实测推翻：**7 个 D 循环独立 entry 里只有 D2 / D4 真注册了 adapter**：

```
xlsx/gt-d2-accounts-receivable    adapter_registered          adapter=d2.receivable_detail
xlsx/gt-d4-operating-revenue      adapter_registered          adapter=d4.revenue_detail
xlsx/gt-d1-notes-receivable       legacy_fake_bidirectional   adapter=None  mount_count=2
xlsx/gt-d3-prepaid-accounts       legacy_fake_bidirectional   adapter=None
xlsx/gt-d5-receivables-financing  legacy_fake_bidirectional   adapter=None
xlsx/gt-d6-contract-assets        legacy_fake_bidirectional   adapter=None
xlsx/gt-d7-contract-liabilities   legacy_fake_bidirectional   adapter=None
```

D1/D3/D5/D6/D7 的 `verification_state` 均为 `UNVERIFIABLE`，五条 `unverifiable_reasons` 含
**`no_registered_sync_adapter`** ⇒ 它们与 E1 **同处 `legacy_fake_bidirectional`**，并非「已接 1 张」。

⇒ **E1 与它们的真实差异只有一级：provider 文件存在与否。**

| | provider 文件 | 受管 sheet 声明 | adapter 注册 | 缺口性质 |
|---|---|---|---|---|
| D1/D3/D5/D6/D7 | ✅ 存在（902/847/781/849/844 行） | ✅ 已声明 | ❌ None | 有 provider 缺发布链 |
| **E1** | ❌ **不存在** | ❌ 无 | ❌ None | **连 provider 都没有** |
| D2/D4 | ✅ | ✅ | ✅ | 已通 |

⇒ 本 spec 的 canary 链路比 D1/D3/D5/D6/D7 **多一步（建 provider）**，其后的契约发布链五环 +
adapter 注册是**六个循环共同的缺口**。🔴 **该缺口是平台级的**：umbrella 的 BP-61-1 实测
`working_paper_sync_entry_state` / `working_paper_content_version` /
`working_paper_content_representation` 三表近空，**186 个 planned entry 一个都注册不上**，
连供给最完整的 Excel pilot 也一样 ⇒ 本 spec 的 Task 9 若卡在第③环，须如实登记为
`upstream_gap` 而**不是** E1 自身的实现缺陷（见需求 1.4 与 tasks Task 9）。

🔴 **本 spec 是 umbrella spec 的下游 lane spec，不是新话题（复盘补：首版缺这段锚定）。**
上游是 **`workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 Task 47「逐一迁移 E 循环
Excel 独立 entry」**（该 task 复选框为 `[x]`，正文写明「处理账户动态行、币种变体和稳定账号/UUID；
防 variant 切换抹零；验证 Property 23 / 69 / 70」），与 D4 lane 在该 umbrella 的
`2026-09-22 D4 lane 登记` 附注里的关系同型。

⇒ 已存在的上游产物必须**复用而非重造**：

| 产物 | 位置 | 已冻结内容 |
|---|---|---|
| E 循环 manifest slice | `backend/data/workpaper_sync_e_cycle_manifest_slice.json`（322 行） | `entry_id` / `migration_state` / 五个 null 供给位 / `scenario_profile_id` / 三条 `manifest_legacy_reasons` / `verification_state=UNVERIFIABLE` + 五条 `unverifiable_reasons` / `not_single_html_because` / `not_bidirectional_because` / `excluded_from_slice`（E0 函证归 Task 57） |
| 行身份守卫 | `composables/__tests__/e1SyncEntryRowIdentity.spec.ts` | umbrella **Property 23**「动态行身份不使用下标」的单点守卫，真跑 `useE1BankDetail` |
| variant 金额守卫 | `composables/__tests__/e1BankVariantIntegrity.spec.ts` | 本位币六列跨 `rmb`/`multi` 守恒，防 `recalcRow` 由原币反推抹零 |

⇒ 需求 1 的 `assert_entry_selectable` 四条事实**不需重新调研**（slice 已冻结），Task 1 改为
**核对 slice 与现状是否仍一致**（slice 冻结于 Task 47 执行时，可能已过期）。

🔴 **Property 编号必须 spec-scoped**：umbrella 有 Property 1–71，其 `Property 3` / `Property 23`
与本 spec 同号不同义。本 spec 的 `Property N` 一律读作 **`E1-P{N}`**，引用上游时须写全
`umbrella Property N`。该纪律有上游事故背书：umbrella 自己的 Task 61 附注记录「全局
`BP-16`~`BP-22` 已被 Tasks 60/63/64 各自重复占用、同号不同义」，修法是改用 task-scoped 前缀
`BP-61-x` 并以 `re.fullmatch(r"BP-61-\d+")` 锁死。

🔴 **结构性前置：E1 的 `parent_duplicate_count = 0`，而 D4 是 31。** slice 原文：E1 的 30+ 子 sheet
由同一宿主按 `currentSheet` 分发到结构化子组件，子组件里没有第二个 `GtOnlyOfficeSheet` 挂载点
⇒ manifest 不产生 `parent_duplicate` 条目。这不是统计差异而是**接入机制差异**：D4 每个受管 sheet
在 manifest 里有自己的条目，E1 一条都没有 ⇒「声明层 +1 per sheet」在 E1 上**不足以**让 manifest
扫出受管 sheet。canary 段须先裁决路线（见 design 上游锚定节：取路线 α 仿 D4 子组件各挂挂载点，
否决路线 β 改 `_entry_id` 派生规则）。

它**消费**三个上游，**不重造**引擎件、**不另起**平行裁决：
- `d1-sync-row-table-engine-and-d1-coverage` —— 框架层行表引擎 / `AdjudicationSheetSpec` /
  **形态谱系三维**（需求 11：`binding_kind` 二分 + `row_identity_key` 三形态 + HTML-only item 子集）
- `d-cycle-sheet-bidirectional-expansion` —— 四条纪律（一 entry 一 adapter · 诚实边界 ·
  可行性核硬门 · D4-4 已判 `single_html` 的判据）
- Phase 5 canary 范式 —— `phase5_d1_notes_receivable` / `phase5_d3_prepaid_receipts` 等六家
  provider 的 `assert_entry_selectable` 四条事实核 + 契约发布链

### E1 当前状态实测（manifest + 宿主 grep）

```
entryId            xlsx/gt-e1-monetary-fund              （已存在）
hostPath           GtE1MonetaryFund.vue
independentEntry   true
scenarioProfileId  xlsx.editable.shared.single.room_service_wired.v1   ← 与 D1/D2/D3 同型
roomServiceState   room_service_wired                    ← room 已接线
migrationState     legacy_fake_bidirectional             🔴
reasonCodes        template_only_open / no_durable_forcesave_ack / missing_adapter
hasContractEvidence  false     hasBrowserEvidence  false
```

⇒ **选型门可过**（entry 存在 + `independent=true` + profile 与 D 类 canary 同型），缺的是
**adapter / 契约 / 发布链**。三条 `reasonCodes` 精确指出了缺口。

🔴 **当前所有 E1 sheet 切「在线编辑」都是假双向**：走 legacy `GtOnlyOfficeSheet`，
`migration_state=legacy_fake_bidirectional` 意味着 OO 里改的东西**不会合并回** `checklist_responses`，
切回结构化视图即丢。这是比 D 类更差的起点（D 类非受管 sheet 至少有 D2 那种「直接禁用 + 中文原因」
的做法），也是本 spec 的直接业务价值。

### 🔴 E 循环模板实测：5 册 / 56 sheets（远超 D 类任何循环）

| # | 模板 | sheets | 含 | 本 spec |
|---|---|---|---|---|
| 1 | `E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx` | **16** | 底稿目录 / E1A / 披露×2 / **E1-1 ~ E1-11** | ✅ **范围** |
| 2 | `E1-14至E1-15 货币资金 -分析程序.xlsx` | 4 | 底稿目录 / E1-14 / E1-15 / 🔴`货币资金分析表F1-6 (修订前)` | ❌ 需新宿主 |
| 3 | `E1-18至E1-23 货币资金 -检查.xlsx` | 7 | 底稿目录 / E1-18 ~ E1-23 | ❌ 需新宿主 |
| 4 | `E1-26至E1-32 货币资金-IPO 上市 新三板 重组 舞弊应对.xlsx` | 9 | 底稿目录 / E26A / E1-26 ~ E1-32 | ❌ 需新宿主 |
| 5 | `E0 货币资金 - 函证（Leap应对措施-函证）.xlsx` | **20** / 987KB | E0A / E0-1 ~ E0-8 + **9 张残留/参考 sheet** | ❌ 需新宿主 |

`entry ↔ template blob` 是 1:1，且 `_entry_id` 从宿主文件派生 + 碰撞检查 ⇒ **一宿主恰一 entry**
⇒ 本 spec 只能覆盖**第一册**（与 D2 的三册同款约束，见 D2 spec 裁决 E1）。

### 第一册各 sheet 几何实测（openpyxl 直读）

| sheet | rows | cols | 公式 | 主公式列 | 形态候选 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | 21 | 7 | 0 | — | 导航 | 不接 |
| 货币资金实质性程序表E1A | 44 | 11 | 7 | A2 D2 G2 J1 | 步骤清单 | 不接 |
| 附注披露信息(上市公司) | 62 | 10 | 153 | C31 B31 D29 | 披露巨表 | 不接 |
| 附注披露信息(国企) | 62 | 10 | 158 | C33 B33 D29 | 披露巨表 | 不接 |
| **货币资金审定表E1-1** | 47 | 10 | **193** | D31 G30 H26 I26 | **逐格**（密度 41%，全平台审定表最高） | ✅ `AdjudicationSheetSpec` |
| **现金明细表E1-2** | 34 | 22 | 38 | E11 G11 I8 | 行表 | ✅ **首张 canary** |
| 🔴 **银行存款及其他货币资金明细表(仅人民币)E1-3** | 92 | 28 | 185 | J41 H39 L38 | 行表 | ✅ 二选一或都接 |
| 🔴 **银行存款及其他货币资金明细表(人民币及外币)E1-3** | 89 | **41** | **567** | Y35 AE35 R34 | 行表（**全平台公式最多**） | ✅ 同上 |
| **数字货币明细表E1-4** | 22 | 17 | 52 | K10 H8 I8 L8 | 行表 | ✅ |
| **调整分录汇总E1-5** | 26 | 10 | 7 | A2 C2 G2 J1 | hub store | 🔍 **可行性核** |
| **银行存款余额调节表E1-6** | 56 | 17 | 14 | C7 A2 E2 H2 | 行表 | ✅ |
| **库存现金（人民币）盘点表E1-7** | 67 | 9 | 27 | C16 G7 A2 D2 | 行表（variant=rmb） | ✅ |
| **库存现金（外币）盘点表E1-8** | 78 | 12 | 48 | D18 C16 H10 | 行表（variant=fx） | ✅ |
| **银行存单盘点表E1-9** | 34 | 15 | 7 | A2 F2 J2 O1 | 行表（variant=cert） | ✅ |
| **已开立银行账户清单核对表E1-10** | 37 | 12 | 7 | A2 C2 F2 K1 | 行表 + **OCR** | ✅ |
| **银行账户情况承诺E1-11** | 31 | 7 | 7 | A2 C2 D2 G1 | **`static_region`（唯一）** + OCR | ✅ |

🔴 **末三行是复盘修正结果，首版把三张全判成 `static_region` 强命中，理由是「各只 7 公式」。**
前端实证只有 E1-11 成立：E1-9 走 `useE1CashCount(variant='cert')`（键 `E1-cash-count-cert-rows`，
`addRow`/删行 ×4）、E1-10 走 `useE1AccountList`（键 `E1-account-list-rows` + 跨 sheet 读
`E1-bank-detail-rows` + OCR ×43），两张都是动态行表；E1-11 零 `-rows` 键，是唯一 `static_region`
候选。**模板公式数是 xlsx 侧几何量，与前端是否有动态行无因果关系** —— 见 design 裁决 H8。

🔴 **E1-3 是同编号两个 sheet**（`(仅人民币)` / `(人民币及外币)`）—— D 类无此形态。必须裁决：
接哪个、还是都接、前端 `E1-bank-detail-rows` 单一 store 键如何对应两张物理 sheet。
`(人民币及外币)` 变体 **567 公式 / 41 列**是全平台单 sheet 公式最多的，逐格 mask 规模需实测。

### E1 的 store 键实测（按值 grep，**四种命名风格并存**）

| sheet | store 键 | 写入方 |
|---|---|---|
| E1-2 现金明细 | `E1-cash-detail-rows` | `useE1CashDetail`(354) |
| E1-3 银行存款明细 | `E1-bank-detail-rows`（**`rmb`/`multi` 两 variant 共用**）+ `E1-bank-variant` | `useE1BankDetail`(413) |
| E1-4 数字货币 | `E1-digital-rows` | `E1TabDigitalCurrency`(661) |
| E1-5 调整分录 | `E1-adjustment-rows` | `useE1Adjustment`(382) |
| E1-6 余额调节表 | `E1-reconciliation-rows` | `useE1Reconciliation`(392) |
| E1-7 / E1-8 / E1-9 盘点 | `E1-cash-count-${variant}-rows`（`rmb`/`fx`/`cert`）+ 副键 `${key}-summary`（cert 无）+ legacy 兜底 `E1-cashcount-fx-summary-fx` + `E1-cert-signatures` | `useE1CashCount`(534) |
| E1-10 账户清单 | `E1-account-list-rows` + `E1-account-commit-snapshot`（与 E1-11 联动） | `useE1AccountList`(340) |
| E1-11 账户承诺 | `E1-account-commit` + `E1-account-commit-check-summary`（**零 `-rows` 键**） | `E1TabAccountCommitment`(700) |
| E1-1 审定表 | **per-cell**：`E1-adj-tb-amount-{opening\|ending}` / `E1-adj-diff-note` / `E1-adj-total-note` / `E1-adj-{item}-opening-unadj` / `E1-adj-total-${...}` / `E1-adjustment-by-item-${...}`；跨 sheet 聚合 `E1-bank-detail-{institution\|finance\|other}-{opening\|total}-unaudited` 6 键；跨册 `E1-accrued-interest-rows` | `useE1Adjudication`(725) |
| 各 sheet 文本块 | `E1-cashcount-{elements\|audit-note\|audit-conclusion}-${variant}`、`E1-{语义}-audit-note` / `-audit-conclusion`（目录 38 键） | 各 tab 组件 |
| 第 2~4 册（范围外）| `E1-analysis-rows` / `E1-credit-check-rows` / `E1-credit-query-rows` / `E1-cutoff-bank-rows` / `E1-cutoff-other-rows` / `E1-accrued-interest-rows` / `E1-interest-monthly-rows` / **`E1-ipo-E1-26-rows`** / `E1-ipo-E1-28-rows` / `E1-ipo-E1-29-rows` / `E1-ipo-E1-30-rows` / `E1-ipo-E1-31-rows` / `E1-ipo-E1-32-rows` | — |

🔴 **四种命名风格并存，键名绝对不能推演**：①语义命名（`E1-cash-detail-rows`）②**编号嵌套**
（`E1-ipo-E1-26-rows` —— 键名里嵌了两次 `E1`）③**模板化**（`E1-cash-count-${variant}-rows`）
④**无连字符**（`E1-cashcount-audit-note-${variant}`）。

最危险的是 ③④ 同时落在同一张底稿上：E1-8 同时有 `E1-cash-count-fx-rows` 与
`E1-cashcount-audit-note-fx`，**`cash-count` 与 `cashcount` 只差一个连字符**。这比 D3 的语义
缩写更不可预测。本 spec 沿用 D3 裁决 F2：`store_item_id` 逐个按值 grep 实测（该裁决已有
**六次事故背书**：D2-3 三键 / D1-15 双键 / D1-13 双键 / D3 语义缩写 / D567 三处必错 /
**E1 四风格并存 + 一字之差**）。

🔴 **反向教训（复盘补）**：查「零写入键」时**必须同时匹配模板化拼接**。`E1TabDirectory.vue`
声明 19 编号 × note/conclusion = 38 键，按全字符串 grep 会把其中 10 个模板化键（`-${variant}`
形态）误报成零写入；按前缀匹配后实测**零缺失**。⇒ 本 spec 不需要 D567 spec Task 1 那类
「目录键零写入、完成度恒未填」的修复。

### 其余红基线（实测）

| 事实 | 实测值 |
|---|---|
| **E1 有公式管理，且是平台范式源头** | `GtE1MonetaryFund.vue:256` `openFormulaManager()`，注释：「由 `ThreeColumnLayout` 顶层挂载的全局 `FormulaManagerDialog` 响应 `open-formula-manager`」；`D4TabOtherMargin.vue:32` 明写「**同 E1 范式**…平台唯一一套公式：`wp_formula` 表权威存储，后端权威执行 + CAS + 审计」⇒ **D4 是照 E1 做的** |
| **E1-5 是第八张同型调整分录汇总表** | `E1TabAdjustment.vue` 接 `useAdjustmentCentralSync` ⇒ 与 D1-5/D2-4/D3-3/D4-4(已判 `single_html`)/D5-3/D6-4/D7-3 同型 |
| composable 规模 | 20 个（路径 `components/workpaper/composables/`），最大 `useE1BankFlowReconcile`(1047) / `useE1DepositDailyMatch`(870) / `useE1Adjudication`(725) / `useE1KeyPersonFlow`(660) / `useE1LargeCheck`(618) / `useE1CashCount`(534)。🔴 **`useE1Adjudication` 属第 1 册 E1-1 审定表、在本 spec 范围内**（首版误标「属第 2/4 册范围外」）；范围外的是 `useE1BankFlowReconcile` / `useE1DepositDailyMatch` / `useE1KeyPersonFlow` / `useE1LargeCheck`。行数按含空行计（`Measure-Object -Line` 不计空行，会少 30~80 行） |
| tab 组件规模 | `e1/` 下 34 个 `.vue`，最大 `E1TabDisclosure`(2063) / `E1TabBankFlowReconcile`(1179) / `E1TabCreditCheck`(951) / `E1TabCashCount`(807) / `E1TabAccountCommitment`(700)。**组件数 ≠ 模板 sheet 数**（34 vs 56），含 7 个 OCR 确认弹窗 + `E1FourTableSourcePanel` / `E1IpoSheetChrome` / `E1PreparationHandbookDialog` 等非 sheet 组件 |
| E0 函证册残留 sheet | **9 张**：`函证程序表-原版本备份` / `参考用-往来函证程序` / `函证结果汇总表E0-1（原）` / `函证结果汇总表E0-1 (备份)` / `回函情况汇编` / `货币资金及借款函证结果汇总表-旧版` / `函证结果汇总表-旧版` / `核实被函证单位信息F1-10-原` / `邮件传真回函核对记录F1-12`（**F1 编号出现在 E0 册**）；另 **`E0-5` 编号重复两张**（`应付银行承兑汇票发函记录表E0-5` / `银行函证其他信息核对表E0-5`） |
| 第 2 册残留 | `货币资金分析表F1-6 (修订前)`（88r×16c/57f，**F1 编号出现在 E1 册**） |
| 超大公式表（范围外） | `存款规模与利息收入匹配性分析E1-30` 389r×22c / **1187 公式**（扫前 250 行即 1187） |

## Glossary

| 术语 | 含义 |
|------|------|
| canary | Phase 5 的首张接入样本 —— 从零建 provider + 契约 + adapter + 宿主接桥的完整链路 |
| `legacy_fake_bidirectional` | manifest 的 migration_state：走 legacy `GtOnlyOfficeSheet`，OO 改动**不合并回** store、切回即丢 |
| `missing_adapter` | reasonCode：entry 存在但无 registry adapter ⇒ 真双向链路断在第一环 |
| 受管区 / binding | 契约声明的一个 `(sheet, table)` 受管数据区 |
| `binding_kind` | `excel_table`（动态，Table + UUID 列）/ `static_region`（静态，definedName 锚点、**绕开整条位移链**） |
| `row_identity_key` | `rowId`（UUID 动态行）/ `key`（稳定 key 固定行，D4-6 范式）/ 无（走 `static_region`） |
| HTML-only item 子集 | 受管 sheet ≠ 全部 item 受管；footer 下 `static_row` 与插行冲突者保持 HTML-only（`HTML_ONLY_ITEM_IDS_D45` 先例） |
| `RowTableSheetSpec` / `AdjudicationSheetSpec` | 声明数据类，由上游 D1 spec 交付 |
| 可行性核硬门 | 上游 `blocking.8`：有行身份列 + 无专用同步链冲突，否则不得扩 `sheets[]` |
| hub store | 被多条专用链共同占用的 store 键（`E1-adjustment-rows` 被借贷平衡 + 中央登记占用） |
| 公式管理 | 平台唯一一套：各页 emit `open-formula-manager` → 顶层全局 `FormulaManagerDialog`；后端 `wp_formula` 表权威 + CAS + 审计。**E1 是该范式源头** |
| 两套宿主 gating | `isE1DetailSheet`（主 detail 链）+ 专用同步 sheet 链；漏后者会工具条叠加冲突（D4-35/D4-13 踩过） |
| `parent_duplicate` | manifest 里「同宿主下每个受管 sheet 各一条」的 entry 形态。D4 有 31 条，**E1 为 0** ⇒ E1 声明层加 sheet 不足以让 manifest 扫出受管 sheet |
| umbrella spec | `workpaper-html-onlyoffice-bidirectional-writeback-closure`（Waves 0–7 / 77 tasks / Property 1–71）。本 spec 是其 **Task 47** 的下游 lane spec |
| lane spec | umbrella 某个 Task 的下游落地 spec（D4 lane 已在 umbrella 附注登记）。Property 编号 spec-scoped，读作 `E1-P{N}` |
| OCR 第二写入方 | E1 的 7 个 `E1*OcrConfirmDialog`，对 `-rows` 键是**整表替换**语义；与 OO forcesave 构成两个批量写入方。**D4 范式零 OCR** |
| TB 显式发布门 | 平台 `tb-writeback-explicit-publish-gate` 建立的唯一 TB 回写通道（`publishToTb` + 中文二次确认）。E1-1 是接入方（`data-testid="e1-publish-tb"`） |
| 七态 e2e 结果枚举 | D4 lane `SheetResult.status`：`applied_store_ok` / `applied_store_miss` / `no_safe_target` / `type_fail` / `op_error` / `op_timeout` / `enter_fail` —— 区分「引擎错」与「该 sheet 无可安全编辑的格」 |

## Requirements

### Requirement 1: E1 首张 canary —— 从零打通真双向（E1-2 现金明细表）

**User Story:** 作为审计助理，我希望 E1 切「在线编辑」后在 OO 里改的数能真正写回结构化视图，
而不是像现在这样切回来就丢。

#### Acceptance Criteria

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`现金明细表E1-2`**（34 行 ×22 列 / 38 公式 /
   store 键 `E1-cash-detail-rows`）—— 它是第一册里结构最简的行表，失败面最小。
2. WHEN 建 provider THEN 它 SHALL 照 Phase 5 canary 范式（`phase5_d1_notes_receivable` /
   `phase5_d3_prepaid_receipts` 同构）新建 `phase5_e1_monetary_fund.py`，并用
   `assert_entry_selectable` 在**真 manifest + 真 finder** 上核四条事实：entry 存在 /
   `independent=True` / profile 与 D 类 canary 同型（实测 `xlsx.editable.shared.single.room_service_wired.v1`
   已同型）/ `wp_code` 落点，且**零回退**。
3. WHEN provider 声明受管 sheet THEN 它 SHALL 消费上游 D1 spec 的 `RowTableSheetSpec` 而**不重造**；
   `store_item_id` SHALL 取实测值 **`E1-cash-detail-rows`**，几何由 Task 1 实测。
4. WHEN 契约发布 THEN SHALL 走完整链路：`build_contract_payload` → 生成器 `--apply` →
   `assert_contract_file_matches_source` → approved bundle → **published representation** →
   `entry_state` → `register_from_manifest()` 真注册 adapter。
5. WHEN adapter 注册成功 THEN manifest 的 `migrationState` SHALL 从 `legacy_fake_bidirectional`
   变为 `adapter_registered`，三条 `reasonCodes`（`template_only_open` /
   `no_durable_forcesave_ack` / `missing_adapter`）SHALL 全部消除。
6. WHEN 宿主接桥 THEN `GtE1MonetaryFund.vue` SHALL 引入 `useWorkpaperSyncBridge` +
   `WorkpaperSyncEditorHost`，**并保留** legacy `GtOnlyOfficeSheet` 给未接 sheet
   （与 D1 宿主同款 `v-if` / `v-else-if` 结构）。
7. WHEN 真栈验收 THEN SHALL 达到 §9.6 三谓词：`confirm 200` / `forcesave cs_error=0` /
   `store_mirrored` + `marker_visible`，并留 DB 证据（op / marker / store 键）。
8. 🔴 WHERE E1 当前**一张都没接** THE 本需求是后续全部需求的**硬前置** —— 在 canary 未通之前
   不得声明第二张受管 sheet（照 `d-cycle-sheet-bidirectional-expansion` 的 Wave 0→1 顺序）。

### Requirement 2: 形态判定先行（消费上游形态谱系）

**User Story:** 作为维护者，我不希望把纯静态 cell 的 sheet 硬塞进行表引擎 —— 第一册里有三张是
`static_region` 的强命中。

#### Acceptance Criteria

1. WHEN 判定任一 sheet 形态 THEN SHALL 在上游 D1 spec 需求 11 的三维谱系内选择，**不新造**：
   `binding_kind`（`excel_table` / `static_region`）· `row_identity_key`（`rowId` / 稳定 key / 无）·
   HTML-only item 子集。
2. 🔴 WHEN 判定 `binding_kind` THEN 判据 SHALL 是**前端三元组实证**
   `(store 键是否存在, addRow/removeRow 信号数, composable 归属)`，**不得**用模板公式数 / 行数 /
   列数推演。实测结论：**E1-11 是第一册唯一的 `static_region`**（零 `-rows` 键，仅
   `E1-account-commit` + `-check-summary`）；**E1-9 / E1-10 是动态行表**
   （`E1-cash-count-cert-rows` / `E1-account-list-rows`）。
   ⇒ 只有 E1-11 绕开整条位移链（无 `row_shift` / footer 两门 / minted UUID / workbook 传播 /
   兄弟 Table ref 维护）⇒ 它 SHALL 排在「验证第二种 `BindingKind`」的位置（canary 与 E1-4 之后）。
   🔴 本条是复盘修正：首版按「各只 7 公式 ⇒ 三张全是 `static_region` 强命中」判定，实证推翻两张。
   变异 SHALL 包含「把判据改回公式数阈值」并证明其打红（需求 9.2）。
3. WHEN 判定 **E1-6 余额调节表**（56r×17c / 14 公式）THEN SHALL 实测判形态（键
   `E1-reconciliation-rows`）。WHERE **E1-7 / E1-8 / E1-9 三张共享 `useE1CashCount`(534) 且只差
   `variant` 参数**（`rmb` / `fx` / `cert`）THE 三张 SHALL 合一个声明文件、只差 `variant` 与列集，
   **不得**复制三份 —— 与 D5/D6/D7 共享 33 个同名函数、只差 `aging_layout` 一参同范式。
   🔴 首版记「`useE1CashCount` 无 `-rows` 键、形态待核」有误：它的键是**模板化**的
   `E1-cash-count-${variant}-rows`，按字面量 grep `-rows` 查不到，按前缀才查得到。
4. WHEN 某张判为 `static_region` THEN 受管区数 SHALL 按 definedName 锚点数计，而非行数。
5. WHEN 各 sheet 的 note / conclusion / procedures 类 item 落在 footer 之下 THEN 逐项核是否命中
   「footer 下 `static_row` 与插行 fail-closed 冲突」（`HTML_ONLY_ITEM_IDS_D45` 先例），
   命中则登记 HTML-only 子集。
   🔴 **E1-7/E1-8/E1-9 是强候选**：三张各有 `E1-cashcount-elements-${variant}` /
   `-audit-note-${variant}` / `-audit-conclusion-${variant}` 三个 per-variant 文本键，
   与 `HTML_ONLY_ITEM_IDS_D45` 的 `D4-5-credit-policy` / `-audit-note` / `-audit-conclusion`
   **形态逐一对应**；D4-5 正是因此被判 HTML-only。⇒ 须优先核这三张，预期产出
   `HTML_ONLY_ITEM_IDS_E1` 常量。
6. 🔴 WHERE **E1 有 7 个 OCR 确认弹窗**（`E1AccountListOcrConfirmDialog` /
   `E1CommitOcrConfirmDialog` / `E1CreditOcrConfirmDialog` / `E1CutoffOcrConfirmDialog` /
   `E1KeyPersonFlowOcrConfirmDialog` / `E1LargeCheckOcrConfirmDialog` /
   `E1StatementOcrConfirmDialog`，全目录 OCR 提及 **454 次**）THE 受管 sheet 的 `-rows` 键有
   **两个批量写入方**（OCR 整表替换 + OO forcesave 回写）。
   ⇒ 受管 sheet 处于 OO 编辑态时，OCR 确认入口 SHALL `disabled` 且给中文原因；
   SHALL **不**做字段级三方合并（当前 `E1*OcrConfirmDialog` 只有整表确认粒度、无 per-field 溯源）。
   🔴 **D4 范式完全不含 OCR**（实测 d4 目录 OCR 弹窗 0 个、提及 0 次；d5/d6/d7 全 0），
   故本条无先例可抄，且 OCR 正落在要接的 E1-10（×43）与 E1-11（×43）上。

### Requirement 3: E1-3 同编号双 sheet 裁决（D 类无此形态）

**User Story:** 作为维护者，我需要先定清「一个 store 键对两张物理 sheet」怎么办，再动手声明。

#### Acceptance Criteria

1. WHERE **`E1-3` 是同编号两个物理 sheet**（`(仅人民币)` 92r×28c/185f 与 `(人民币及外币)`
   89r×**41c**/**567f**，后者是全平台单 sheet 公式最多）THE 本 spec SHALL 先裁决三个选项之一并留证：
   ① 只接 `(仅人民币)` ② 只接 `(人民币及外币)` ③ 两张都接（各占独立受管区）。
2. WHEN 裁决依据被收集 THEN SHALL 实测：前端 `E1-bank-detail-rows`（`useE1BankDetail` 413 行）
   是否区分币种、两张 sheet 的列语义是否可由同一 store 载荷投影、项目实例化时是否两张都出现
   （若按客户是否有外币二选一实例化，则只接对应那张）。
3. IF 选项③（两张都接）THEN 它们 SHALL 是同 store 键的两个受管区 —— 此形态 D 类**从未出现过**，
   须先确认引擎支持「一 store item 投影到两张 sheet」，若不支持则退回①或②。
4. WHEN `(人民币及外币)` 变体被选中 THEN 其逐格 mask 规模 SHALL 实测登记（567 公式 / 41 列）；
   IF mask 覆盖到数据区之外的行 THEN SHALL 确认 `merge._protection` 的格级判定
   （`cell_in_ranges` + `_mask_spans_data_column`）已入库，否则受管金额字段会被整列误判只读
   （D4-1 踩过的坑）。
5. WHEN 裁决产出 THEN SHALL 落证据 JSON，**不改任何生产代码**。
6. 🔴 WHERE 复盘实测把本需求的风险从「待裁决」升级为**数据损坏级** THE 裁决 SHALL 默认
   **只接 `(人民币及外币)` 一张**，`(仅人民币)` 保持 legacy 并显式登记。实证依据：

   ```
   useE1BankDetail.ts:9    type BankDetailVariant = 'rmb' | 'multi'
   E1TabBankDetail.vue:35  variant = props.sheetName?.includes('人民币及外币') ? 'multi' : 'rmb'
   useE1BankDetail.ts:61   VARIANT_KEY = 'E1-bank-variant'      ← variant 选择本身被持久化
   useE1BankDetail.ts:110  注释明写「两 variant 字段集不同是 AC 1.9 的意图」
                           rmb 版**不下发**原币列（fxCurrency / fxRate）
   ```

   两 variant 共用同一个 `E1-bank-detail-rows` 但列集不同 ⇒ 若两张同时受管，OO 在 `rmb` sheet
   上 forcesave 回写整行会把 `multi` 侧的原币列写成缺省/抹零。**这正是既有守卫
   `e1BankVariantIntegrity.spec.ts` 在守的缺陷形态**（`recalcRow` 由原币反推导致抹零），
   OO 回写只是从第二个方向引入同一后果。
   ⇒ `multi` 是列集超集、`rmb` 是其投影子集，接超集不丢列。IF 将来要两张都接
   THEN 硬前置是**先把 `E1-bank-detail-rows` 拆成两个键**（或引入 per-variant 列集投影），
   而**不是**让引擎支持「一 store item 投影到两张列集不同的 sheet」。

### Requirement 4: E1-1 审定表接入（193 公式，全平台审定表最高密度）

**User Story:** 作为审计助理，我希望审定表的取数与我的人工覆盖不互相吞掉。

#### Acceptance Criteria

1. WHEN 声明 E1-1 THEN 它 SHALL 用上游交付的 `AdjudicationSheetSpec`，**不**用行表引擎。
2. WHEN 声明 mask THEN 它 SHALL 是**逐格**形态（实测 47 行 ×10 列 / **193 公式** / 密度 **41%**，
   为全平台审定表最高），且 SHALL 依赖已入库的 `merge._protection` 格级判定（需求 7.2）。
3. WHEN 确定 E1-1 的区块数与行模型 THEN 它们 SHALL 由 Task 1 **实测**确定，**不得**照
   D1-1（3 区 × 动态票据种类）/ D2-1（1 区 × 写死 4 行 + SUMIF）/ D4-1（2 区 × 动态行）推演 ——
   五个循环的审定表形态已证互不相同。
4. WHEN E1-1 的取数来自 cross-sheet 派生 THEN 它 SHALL 接入四态覆盖状态机
   （`resolveCellState` / `displayValueForCellState`），复用 `shared/dynamicAdjudicationRows`，
   **不得**在 E1 侧另写一套。实测 `useE1Adjudication`(725 行) 读 `E1-accrued-interest-rows`
   （属第 3 册 E1-20 应计利息测算）⇒ 跨册取数，须确认该键在本 spec 范围外时如何处理。
5. WHEN 覆盖发生 THEN S2 SHALL 标「已人工覆盖」、S4 SHALL 同时呈现覆盖值 / 原派生值 / 现派生值
   且**不自动二选一**，并提供逐格「恢复取数」。
6. 🔴 WHERE **E1-1 接平台统一 TB 显式发布门**（`E1TabAdjudication.vue:336`
   `data-testid="e1-publish-tb"`、`:338` 绑 `publishToTb`，同型接入方遍布 F1~F5 / G1~G14 /
   H1~H10 / D2）THE 双向回写 SHALL **不**成为 TB 回写的第二条路径。三条红线：
   ① sync 回写路径（extract → merge → store）对 `trial_balance` 的写次数 SHALL 为 **0**；
   ② OO 侧改 E1-1 审定数后，未点 `e1-publish-tb` 前 `trial_balance` SHALL 不变；
   ③ 接入 E1-1 前后两道既有 CI 守卫 SHALL 保持绿：
   `check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate`。
   🔴 D 类四个 spec 均无此条：D1/D3/D5/D6/D7 的审定表排在最后且未触及，D2-1 虽接 `publishToTb`
   但 D2 spec 只扩第一册且 D2-1 未进受管清单。**E1-1 是第一次「受管 sheet 与 TB 发布门落在同一张
   底稿」**。
7. 🔴 WHEN 声明 E1-1 的 per-cell 锚点 THEN SHALL 区分三个值来源，且 SHALL 断言**派生格不可由
   OO 侧直接写**（否则 OO 回写覆盖聚合结果）：

   ```
   本 sheet 人工   E1-adj-diff-note / E1-adj-total-note / E1-adj-{item}-opening-unadj
   跨 sheet 聚合   E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited  6 键
                   ← 取自 E1-3 三个分组小计（useE1BankDetail:80-90）
   跨册取数        E1-accrued-interest-rows  ← E1-20 应计利息测算在**第 3 册**（范围外）
   槽位顺序        E1TabAdjudication.vue 的 E1_SLOT_ORDER 常量
   ```

   ⇒ 跨册键在本 spec 范围外，SHALL 明确其在「第 3 册未受管」状态下的降级行为（不得因缺失而
   把该格判成空或 0）。

### Requirement 5: E1-5 调整分录汇总 —— 可行性核（**第八张同型**）

**User Story:** 作为维护者，我不希望把已被中央登记链占用的 hub store 强行接成单元格双向。

#### Acceptance Criteria

1. WHEN E1-5 进入评估 THEN 它 SHALL 先过上游可行性核硬门。
2. WHERE E1-5 与已判 `single_html` 的 D4-4 同型 THE 默认倾向 `single_html`。已实证：
   `E1TabAdjustment.vue` **接了 `useAdjustmentCentralSync`** ⇒ 经后端 `AdjustmentSyncService`
   中央登记；`E1-adjustment-rows` 是 hub store；模板 26r×10c / 仅 7 公式。
   待核：借贷平衡不变式是否仅 HTML 侧强制、有无行身份列。
3. WHEN 裁决产出 THEN SHALL 落证据 JSON（照 `T08-d44-single-html-adjudication.json` 范式），
   **不改任何生产代码**（上游诚实边界红线）。
4. 📌 **触类旁通已闭环：八张调整分录汇总表全部同型** —— D1-5 `D1-entry-rows` /
   D2-4 `D2-entry-rows` / D3-3 `D3-aje-rows` / D4-4 `D4-4-rows`（**已判 `single_html`**）/
   D5-3 / D6-4 / D7-3 / **E1-5 `E1-adjustment-rows`**，各自宿主均接 `useAdjustmentCentralSync`。
   ⇒ 建议统一裁决另立 `cycle-adjustment-sheets-single-html-adjudication`（原建议名带 `d-`
   前缀，现应去掉 —— E1 证明它不只是 D 类问题）。IF 该 spec 已立 THEN 本需求降级为引用其结论。

### Requirement 6: 公式管理 —— 确认不冲突，**本 spec 不改**

**User Story:** 作为底稿编制人，我希望接了双向回写之后，公式管理入口还能正常用。

#### Acceptance Criteria

1. 🔴 WHERE **E1 是平台公式管理范式的源头** THE 本 spec **不改动**公式管理的任何实现。
   实证：`GtE1MonetaryFund.vue:256` 的 `openFormulaManager()` 注释写明「由 `ThreeColumnLayout`
   顶层挂载的全局 `FormulaManagerDialog` 响应 `open-formula-manager`」；`D4TabOtherMargin.vue:32`
   明写「**同 E1 范式** …… 平台唯一一套公式：`wp_formula` 表权威存储，后端权威执行 + CAS + 审计」
   ⇒ **D4 是照 E1 做的**，E1 侧已完整。
2. WHEN E1 接入 sync 后 THEN 公式管理入口 SHALL 在**两种渲染模式下行为一致** —— 结构化视图与
   在线编辑模式切换不得使 `open-formula-manager` 事件丢失或弹窗挂不上。判据 SHALL 覆盖两模式。
3. WHERE 公式管理的收敛归 `workpaper-page-formula-toolbar-closure`（15/15，`F-SHELL` 已发布）
   THE 本 spec SHALL 消费其 outlet 契约，**不得**在 E1 宿主内新建第二个按钮 owner 或第二套
   location owner（该 spec 需求 1.4 / 2.4 的红线）。
4. 🔴 WHEN 区分两个「公式」概念 THEN 它们 SHALL 不被混淆：
   * **公式管理**（`wp_formula` 表 / `workpaper` scope / 全局弹窗）—— 审计师维护的跨底稿取数公式
   * **`formula_mask`**（契约声明 / 逐格或列向区间）—— 模板里的 Excel 内部公式，
     materialize 不覆盖、由 OO 重算
   二者**不在一层**，本 spec 只碰后者。首版用户表述「参照 D4 实现公式管理」易被读成要改前者。

### Requirement 7: 前置依赖

**User Story:** 作为维护者，我不希望本 spec 建立在未交付的引擎或未入库的修复上。

#### Acceptance Criteria

1. WHEN 本 spec 开工前 THEN 上游 `d1-sync-row-table-engine-and-d1-coverage` 的框架层
   （`RowTableSheetSpec` / `StoreItemSpec` 注册表 / **形态谱系三维** / `attach_sibling_bindings(provider=…)`）
   SHALL 已入 HEAD。判定用 `git show HEAD:` 而非工作树。
2. WHEN 需求 4（E1-1 审定表）与需求 3.4 开工前 THEN 两件 SHALL 已在 HEAD：
   ①`AdjudicationSheetSpec` ②`merge._protection` 格级判定 + `_mask_spans_data_column`。
3. 🔴 WHERE E1 的 adapter **尚不存在**（`missing_adapter`）THE 需求 1 的 canary 链路本身就是
   在解除这个前置 ⇒ 与 D3/D567 的 `adapter_registered=False` 不同：那边是「有 provider 缺发布链」，
   E1 是「连 provider 都没有」。⇒ 真栈实测的解除条件是需求 1.4/1.5 走完。
4. WHEN 需求 2 的形态判定开工前 THEN 上游形态谱系（`binding_kind` / `row_identity_key` /
   HTML-only 子集三个声明位）SHALL 已落 —— 否则三张 `static_region` 强命中的 sheet 只能退回行表声明。
5. IF 前置 1 未满足 THEN 全部阻塞。IF 仅 2 未满足 THEN 需求 3.4 / 4 阻塞，需求 1/2/5/6 可推进。

### Requirement 8: 性能门与零回归

**User Story:** 作为多人平台的现场经理，我要求 E1 接入不让 materialize 变慢，也不动其他循环。

#### Acceptance Criteria

1. WHEN 每接入一张 sheet THEN SHALL 实测一次整册 materialize 耗时并登记（脚本现测，不手抄）。
2. IF 耗时超过配置软上限 THEN 接入 SHALL 停止并转性能 spec，**不得**带退化铺量。
   🔴 E1 第一册 16 sheets，且 `(人民币及外币)E1-3` 有 567 公式 / 41 列 ⇒ 整簿解析成本高于 D 类
   多数循环，本条门比 D 类更要紧。
3. WHEN E1 新增 contract THEN 已有 8 个 contract（b60/d1/d2/d3/d4/d5/d6/d7）+ g7/h1 的 golden
   digest SHALL 全部不变。
4. WHEN store-projection 被请求 THEN `store_field_count` 与 `field_count` SHALL 记录实测值；
   🔴 判据**不得**用二者作差推断数据丢失（D4 spec 曾误判 1648 vs 992）。
5. WHEN 宿主接桥 THEN 未接 sheet SHALL 保持现状（legacy `GtOnlyOfficeSheet`）**但须显式登记**
   它们仍是 `legacy_fake_bidirectional`（OO 改动不合并回 store、切回即丢）—— 这是既有事实，
   本 spec 只缩小它的范围、不掩盖它。
6. WHEN 前端受管 sheet 集合被判定 THEN 它 SHALL **从 provider 受管清单派生**而非前端硬编码；
   `capability` 与 `flushHtml` SHALL 从 `Ref` 读取。
7. WHEN 宿主接线 THEN SHALL 覆盖**两套 gating**（`isE1DetailSheet` + 专用同步 sheet 链，
   如审定表 E1-1 或三张 `static_region` 走独立宿主）—— 漏后者会工具条叠加冲突（D4-35/D4-13 踩过）。

### Requirement 9: 变异检验与证据

**User Story:** 作为质量控制复核合伙人，我要求每条判据都被证明不是永绿的装饰。

#### Acceptance Criteria

1. WHEN 每条核心判据落地 THEN SHALL 配一次变异并记录打红条数；未能打红的重写而非保留。
2. WHEN 变异覆盖 THEN SHALL 至少含下列九条：

   | # | 变异 | 预期打红的判据 |
   |---|---|---|
   | 1 | `store_item_id` 按编号推演（`E1-2-rows` 而非 `E1-cash-detail-rows`） | E1-P2 |
   | 2 | 把 `cash-count` 写成 `cashcount`（一字之差） | E1-P2 |
   | 3 | 🔴 把 `binding_kind` 判据改回**公式数阈值**（`< 10 ⇒ static_region`） | E1-P3 |
   | 4 | E1-9 或 E1-10 声明成 `static_region`；E1-11 声明成行表 | E1-P3 |
   | 5 | E1-1 的区块数照 D1-1 推演 | E1-P6 |
   | 6 | 四态用 `stored ≠ derived` 错法 | E1-P9 |
   | 7 | 公式管理在 OO 模式下弹窗挂不上 | E1-P8 |
   | 8 | 🔴 OCR 确认入口在 OO 编辑态下不 disabled（或改成写完自动 forcesave） | E1-P16 |
   | 9 | 🔴 让 merge 顺带写 `trial_balance`；或在 sync 回写里调 `publishToTb` | E1-P17 |
   | 10 | 🔴 E1-3 两张 sheet 都声明受管同一键；或投影列集取两 variant 交集 | E1-P18 |

   🔴 第 3 条是**自省变异**：它复现的正是本 spec 首版裁决 H3 的错法，判据必须能打红自己的历史
   错误，否则下一轮会原样复发。
3. WHEN 真栈验收 THEN SHALL 达 §9.6 三谓词（`confirm 200` / `forcesave cs_error=0` /
   `store_mirrored`+`marker_visible`）+ DB 三谓词，并覆盖 OO canvas 逐值断言与回读等值。`--workers=1`。
4. WHERE 真栈判据有已知陷阱 THE 沿用上游三条结论：不能用 `page.on('response')` 判 callback
   （须读后端 `application_bound_at`）；不能用 `asc_*` API 写格（须真实键盘输入
   `#ce-cell-name` → `keyboard.type` → Enter）；模式切换条选择器**须实测确认**不得照抄 D4。
5. WHEN 证据登记 THEN SHALL 落 `docs/operations/evidence/e1-sync-coverage/`，数字脚本现测。

### 不在本 spec 范围

- **第 2~5 册全部 sheet**（E1-14/E1-15 分析 · E1-18~E1-23 检查 · E1-26~E1-32 IPO 舞弊 ·
  E0-1~E0-8 函证共 40 张）—— 各需新建独立宿主才能有 entry，登记为
  `e1-analysis-inspection-ipo-confirmation-sync-hosts` 另立。含全平台公式最多的
  `存款规模与利息收入匹配性分析E1-30`（389r / **1187 公式**）。
- **E1A 程序表**（步骤清单）与**两张附注披露**（62r×10c / 153~158 公式）。
- **E0 册的 9 张残留/参考 sheet** 与 **`货币资金分析表F1-6 (修订前)`** —— 模板治理问题，
  登记但不处理；另 **`E0-5` 编号重复两张**须在接第 5 册前先裁决。
- **八张调整分录汇总表的统一裁决**：建议另立 `cycle-adjustment-sheets-single-html-adjudication`
  （去掉原建议的 `d-` 前缀 —— E1-5 证明它不只是 D 类问题）。
- **公式管理的任何改动**（需求 6：E1 是范式源头、已完整；收敛归
  `workpaper-page-formula-toolbar-closure`）。
- **性能根因优化**（归 `oo-html-writeback-performance` 与已归档的
  `workpaper-sync-materialize-large-table-performance`）。本 spec 只立门。
