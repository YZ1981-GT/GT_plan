# Requirements Document

## Introduction

L0债务循环（筹资循环）函证，覆盖科目：短期借款/长期借款/应付债券/长期应付款（金融机构及债权人第三方函证确认）。源模板1个xlsx文件10个sheet。

**核心架构决策（对齐D0实际实现 + F0 pattern）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用（🔴铁律：函证模块跨循环共享）
- L0-1~L0-4/差异检查表(示例)/L0-6/L0-7直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-diff-checklist / confirmation-reliability / confirmation-fraud-risk）
- **仅L0-5需要新建**：长期应付款替代程序4区块（按长期应付款/借款科目），参照D0-5模式。只有1个替代程序
- L0A程序表复用`a-program-console`（注意：源模板L0A的tab名误写为"函证程序表F0A"，映射时以wp_code=L0A为准）
- L0比H0多一个"函证差异检查表（示例）"→confirmation-diff-checklist（复用D0）

**与D0的差异**：
- D0科目：应收账款/合同资产/其他应收款（收入循环）
- L0科目：短期借款/长期借款/应付债券/长期应付款（债务/筹资循环）
- L0-5长期应付款替代程序4区块：期后付款还款检查/期末余额支持性证据/本期借款检查/抵质押担保证据

**源模板sheet清单（openpyxl实读）**：

| # | Sheet名 | 行×列 | wp_code | componentType | 新建/复用 |
|---|---------|-------|---------|---------------|-----------|
| 1 | 底稿目录 | - | - | b-index | 复用 |
| 2 | 函证程序表L0A（tab名误写F0A） | - | L0A | a-program-console | 复用 |
| 3 | 函证结果汇总表L0-1 | 69×33(54公式) | L0-1 | confirmation-summary | 复用D0 |
| 4 | 核实被函证单位信息L0-2 | 40×40(12公式) | L0-2 | confirmation-entity-verify | 复用D0 |
| 5 | 跟函函证过程控制L0-3 | 37×18 | L0-3 | confirmation-followup | 复用D0 |
| 6 | 函证差异调节表L0-4 | 21×15(14公式) | L0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | 函证差异检查表（示例） | - | 函证差异检查表（示例） | confirmation-diff-checklist | 复用D0 |
| 8 | 长期应付款替代程序L0-5 | 59×28(8公式) | L0-5 | confirmation-alternative-l05 | **新建** |
| 9 | 邮件传真回函可靠性验证L0-6 | 39×20 | L0-6 | confirmation-reliability | 复用D0 |
| 10 | 函证程序舞弊风险评价表L0-7 | 31×10 | L0-7 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType（confirmation-summary/entity-verify/followup/diff-reconcile/diff-checklist/reliability/fraud-risk + 循环特有的alternative-xxx）
- **替代程序**: 对未回函的被询证单位（金融机构/债权人）执行的审计替代程序（检查期后还款/借款合同/银行对账单等），4区块检查宽表结构按科目不同
- **合计行**: 每区块底部SUM金额列，等于该区块所有明细行金额之和

## Requirements

### Requirement 1: L0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to L0各sheet映射到D0共享组件, so that L0债务循环函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：L0→confirmation-hub, L0A→a-program-console, L0-1→confirmation-summary, L0-2→confirmation-entity-verify, L0-3→confirmation-followup, L0-4→confirmation-diff-reconcile, 函证差异检查表（示例）→confirmation-diff-checklist, L0-5→confirmation-alternative-l05, L0-6→confirmation-reliability, L0-7→confirmation-fraud-risk（10个wp_code条目）
2. THE L0.yaml render schema SHALL 准确反映10个sheet的component_type和class_code（含L0A的tab名误写F0A的映射修正）
3. THE account_package_registry.json SHALL 包含L0包（10 sheets按模板目录顺序）

### Requirement 2: L0-5长期应付款替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的长期应付款/借款执行替代程序, so that 我能获取充分适当的存在性/计价/权属证据。

#### Acceptance Criteria

1. THE L0-5 SHALL 注册componentType: `confirmation-alternative-l05`
2. THE L0-5 SHALL 多公司Master-Detail（一公司一检查表，参照D0-5 GtConfirmationAlternativeD05模式，el-tabs按公司 + ElMessageBox.prompt新增公司）
3. THE L0-5 SHALL 顶部余额汇总区，显示：函证项目(长期应付款/借款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期借款金额 | 期后还款检查比例 | 抵质押证据检查比例
4. THE L0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE L0-5 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①期后付款/还款检查：日期/凭证编号/业务内容/对方科目/金额 | 还款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/还款本金/还款利息/索引号/是否异常
   - ②期末余额支持性证据(借款合同/银行对账单)：日期/凭证编号/业务内容/对方科目/金额 | 借款合同编号/债权人/合同金额/借款期限 | 银行对账单日期/账面余额/对账差异/索引号/是否异常
   - ③本期借款检查：日期/凭证编号/业务内容/对方科目/金额 | 借款审批单日期编号/是否恰当审批 | 到账银行回单日期/到账金额/借款利率/索引号/是否异常
   - ④抵质押/担保证据：日期/凭证编号/业务内容/对方科目/金额 | 抵质押合同编号/抵押物/抵押金额 | 担保合同编号/担保方/担保金额 | 他项权证编号/索引号/是否异常
6. THE L0-5 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE L0-5 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列（下拉）
8. THE L0-5 SHALL 支持从confirmation-hub的L0-1带入未回函公司（反向联动）
9. THE L0-5 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点，📎附件列）
10. THE L0-5 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE L0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE L0-5 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 3: 独立composable与导入导出

**User Story:** As a 开发者, I want to L0-5有独立composable管理数据和导入导出, so that 代码组织清晰、复用D4导入导出模式。

#### Acceptance Criteria

1. THE L0-5 SHALL 有独立composable `useAlternativeL05Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
2. THE L0-5 SHALL 复用 `useL0ImportExport` 模式（composable封装三端点调用，后端3端点：export-template/export-data/import-data）
3. THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/l0/export-template?sheet=L0-5` 等
4. THE 导出模板 SHALL 包含4区块对应4个sheet（每个区块一个sheet，含列头+填写说明）
5. THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据回写checklist_responses

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-l05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE htmlRendererRegistry SHALL 包含l05→对应Vue组件的映射（defineAsyncComponent lazy）
3. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含confirmation-alternative-l05
4. THE 后端RENDERER_DISPATCH SHALL 有l05的render策略（复用confirmation通用renderer，返回checklist_responses snapshot）

### Requirement 5: 公式引擎（L0专属）

**User Story:** As a 开发者, I want to 实现L0-5替代程序的合计/还款比例/对账差异公式引擎, so that 合计行/检查比例/对账差异计算可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现 `calcBlockTotal`（区块合计 = Σ金额列，空数组→0）
2. THE Formula_Engine SHALL 实现 `calcRepaymentRatio`（还款检查比例 = 已检查还款金额 / 期末余额，期末余额=0→0）
3. THE Formula_Engine SHALL 实现 `calcReconcileDiff`（对账差异 = 账面余额 - 银行对账单余额）
4. THE Formula_Engine SHALL 实现 `isAbnormal`（是否异常 = |对账差异| > 0）

### Requirement 6: 版本链集成

**User Story:** As a 审计助理, I want to L0函证底稿自动记录版本快照并可查看历史, so that 满足质量控制要求。

#### Acceptance Criteria

1. THE GtConfirmationAlternativeL05 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
2. WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
3. THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板（右侧drawer）
4. THE useVersionTrail SHALL 支持手动创建命名快照（用户可输入备注）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证L0-5公式引擎的正确性。

**P1: 区块合计公式** — ∀ amounts ∈ ℝ*: calcBlockTotal(amounts) === Σ amounts；空数组 → 0

**P2: 还款检查比例公式** — ∀ repaid ∈ ℝ≥0, balance ∈ ℝ: calcRepaymentRatio(repaid, balance) === balance>0 ? repaid/balance : 0

**P3: 对账差异公式** — ∀ book, statement ∈ ℝ: calcReconcileDiff(book, statement) === book - statement；零差异恒等：calcReconcileDiff(v, v) === 0

**P4: 异常判定** — ∀ book, statement ∈ ℝ: isAbnormal(calcReconcileDiff(book, statement)) === (book ≠ statement)
