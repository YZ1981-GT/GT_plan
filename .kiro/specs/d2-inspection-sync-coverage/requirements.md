# D2 检查底稿双向回写覆盖 — Requirements

## 背景

D2 应收账款底稿分布在 3 本 Excel 工作簿中：

| 工作簿 | wp_code | 包含 sheet | 当前双向状态 |
|---|---|---|---|
| D2-1至D2-4 审定表明细表 | D2 | D2-1/D2-2/D2-3/D2-4 | **D2-1/D2-2/D2-3 已全通** |
| D2-5 分析程序 | 待确认 | D2-5 | 未覆盖 |
| D2-6至D2-13 检查 | 待确认 | D2-6~D2-13 (8张) | 未覆盖 |

本 spec 目标：让 D2-5 分析表 + D2-6~D2-13 检查底稿走真双向回写。

## 勘测结果（2026-10-12 实测）

### Excel sheet 结构

| Sheet | 行×列 | 公式数 | 合计行 | 形态 |
|---|---|---|---|---|
| D2-5 分析表 | 54×9 | 63 | R48 | 5 区段（指标/借方核对/贷方分析/前十名/账龄） |
| D2-6 关联方 | 31×14 | 17 | R16 | 动态行表（11列+操作） |
| D2-7 凭证检查 | 52×17 | 20 | R43 | 双区（本期/期后）凭证级检查 |
| D2-8 坏账政策 | 46×22 | 6 | 无 | 卡片式政策段落 + 矩阵 |
| D2-9 坏账测算 | 50×14 | 57 | R39 | 单项 ECL 行表 |
| D2-10 ECL | 110×10 | 198 | R60 | 折现法 + 迁徙率矩阵 |
| D2-11 核销 | 29×8 | 10 | R22 | 双段（转回/核销）行表 |
| D2-12 质押 | 43×12 | 13 | R19 | 双段（质押/保理）行表 |
| D2-13 业务模式 | 30×5 | 12 | 无 | QA 判断卡片 + 组合表 |

### 前端子组件 store 持久化完整清单

所有 8 个子组件**已有 store 持久化**（通过 `allResponses.set()` + `D2_SAVE_ITEMS_KEY` inject 或 CustomEvent）。

| Sheet | 子组件 | store item_id | 行身份键 | 数据模型 |
|---|---|---|---|---|
| D2-5 | D2TabAnalysis | `D2-analysis-debit-recon` / `D2-analysis-credit-analysis` / `D2-analysis-top10` / `D2-analysis-aging-compare` + 指标系列 | Top10Row 无 rowId；其余无行身份（固定行） | DebitReconRow / CreditAnalysisRow / Top10Row / AgingCompareRow |
| D2-6 | D2TabRelatedParty | `D2-related-party-rows` / `-note` / `-conclusion` | `rowId`（`rp-*`） | RelatedPartyRow（11 字段） |
| D2-7 | D2TabVoucherCheck | `D2-vc-current-rows` / `D2-vc-post-rows` / `D2-vc-methodology` / `D2-vc-audit-summary` / `D2-vc-conclusion` | `rowId`（`vcr-*`） | VoucherCheckRow / SampledVoucher |
| D2-8 | D2TabPolicyCheck | `D2-policy-paragraphs` / `-historical-matrix` / `-migration-matrix` / `-conclusion` / `-summary` | `paragraphId` / `rowId` | PolicyParagraph / PolicyHistoricalRow / PolicyMigrationRow |
| D2-9/10 | D2TabEcl | `D2-ecl-single-rows` / `-discount-rows` / `-migration-matrix` / `D2-ecl-note` | `rowId`（`ecl-*`） | EclSingleRow / EclDiscountRow / MigrationRateRow |
| D2-11 | D2TabWriteoffCheck | `D2-writeoff-reversal-rows` / `-writeoff-rows` / `-section-analysis` | `rowId`（`wo-*`） | WriteoffRow（section='reversal'\|'writeoff'） |
| D2-12 | D2TabPledgeCheck | `D2-pledge-rows` / `D2-factoring-rows` / `-note` / `-conclusion` + `D2-derecognition` | `rowId`（`pl-*`） | PledgeRow / FactoringRow |
| D2-13 | D2TabBizModel | `D2-bizmodel-judgments` / `-groups` / `-note` / `-conclusion` | `rowId` / `questionId` | BizModelJudgment / BizModelGroup |

### 真库数据

和平药房项目的 `checklist_responses` 中 D2-6~D2-13 相关 item_id **零行**（审计师尚未在这些表上录入数据）。

## 架构决策（待定）

### 方案 A：归入现有 entry `xlsx/gt-d2-accounts-receivable`

D2-6~D2-13 工作簿虽然是独立 xlsx，但在平台里可能共用 D2 主底稿的 `wp_id`（不同 sheet 通过 sheet_name 路由）。如果是这样，可以在现有 entry 上扩容（类似 D4 一个 entry 覆盖 36 张 sheet）。

### 方案 B：新建独立 entry

如果 D2-6~D2-13 工作簿有自己的 `wp_id`（独立底稿），则需要新建 manifest entry。

### 前置确认

1. D2-6~D2-13 工作簿在 `working_paper` 表里的 `wp_id` 是哪个？（从真库查 `wp_code LIKE 'D2%'`）
2. 前端宿主 `GtD2AccountsReceivable.vue` 里 D2-6~D2-13 tab 读的是哪个 `wp_id` 的 `checklist_responses`？

## 需求

1. 为 D2-5 ~ D2-13 的 9 张 Excel sheet 建立逐字段的双向映射
2. 每张 sheet 的 provider 模块（字段映射 + store 投影 + merge 回写）
3. 契约 JSON 扩容（9 张 sheet 加入 sheets 列表）
4. instrumentation（DefinedName 注入模板字节）
5. 前端受管 sheet map 扩展（`D2_MANAGED_SHEET_KEYS` 加入 9 张）
6. roundtrip 验证（HTML→OO→HTML 每张 sheet 数据不丢不错）
