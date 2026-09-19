# Requirements Document

## Introduction

K0管理循环函证，覆盖科目：其他应收款/其他应付款为主（往来款项第三方函证确认）。源模板1个xlsx文件10个sheet。

**核心架构决策（对齐D0实际实现 + F0 pattern）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用（🔴铁律：函证模块跨循环共享）
- K0-1~K0-4/K0-7/K0-8直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-reliability / confirmation-fraud-risk）
- **仅K0-5/K0-6需要新建**：替代程序4区块按科目不同（其他应收款 vs 其他应付款），参照D0-5/D0-6模式（类似F0-5/F0-6，2个替代程序）
- K0A程序表复用`a-program-console`

**与D0的差异**：
- D0科目：应收账款/合同资产/其他应收款（收入循环）
- K0科目：其他应收款/其他应付款（管理循环）
- K0-5其他应收款替代程序4区块：期后收款/期末余额证据/本期发生额/往来对账协议证据（参照F0-5预付账款模式）
- K0-6其他应付款替代程序4区块：期后付款/期末余额证据/本期发生额/往来对账协议证据（参照F0-6应付账款模式）

**源模板sheet清单（openpyxl实读）**：

| # | Sheet名 | 行×列 | wp_code | componentType | 新建/复用 |
|---|---------|-------|---------|---------------|-----------|
| 1 | 底稿目录 | - | - | b-index | 复用 |
| 2 | 函证程序表K0A | - | K0A | a-program-console | 复用 |
| 3 | 函证结果汇总表K0-1 | 68×33(62公式) | K0-1 | confirmation-summary | 复用D0 |
| 4 | 核实被函证单位信息K0-2 | 41×40(16公式) | K0-2 | confirmation-entity-verify | 复用D0 |
| 5 | 跟函函证过程控制K0-3 | 37×18 | K0-3 | confirmation-followup | 复用D0 |
| 6 | 函证差异调节表K0-4 | 21×15(14公式) | K0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | 其他应收款替代程序K0-5 | 73×25(8公式) | K0-5 | confirmation-alternative-k05 | **新建** |
| 8 | 其他应付款替代程序K0-6 | 73×25(8公式) | K0-6 | confirmation-alternative-k06 | **新建** |
| 9 | 邮件传真回函可靠性验证K0-7 | 38×20 | K0-7 | confirmation-reliability | 复用D0 |
| 10 | 函证程序舞弊风险评价表K0-8 | 31×11 | K0-8 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType（confirmation-summary/entity-verify/followup/diff-reconcile/diff-checklist/reliability/fraud-risk + 循环特有的alternative-xxx）
- **替代程序**: 对未回函的被询证单位执行的审计替代程序（检查期后收付款/余额支持性证据/往来对账等），4区块检查宽表结构按科目不同
- **往来对账**: K0特有，其他应收/应付款需与往来单位对账，对账差异 = 本方余额 - 对方余额
- **合计行**: 每区块底部SUM金额列，等于该区块所有明细行金额之和

## Requirements

### Requirement 1: K0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to K0各sheet映射到D0共享组件, so that K0管理循环函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：K0→confirmation-hub, K0A→a-program-console, K0-1→confirmation-summary, K0-2→confirmation-entity-verify, K0-3→confirmation-followup, K0-4→confirmation-diff-reconcile, K0-5→confirmation-alternative-k05, K0-6→confirmation-alternative-k06, K0-7→confirmation-reliability, K0-8→confirmation-fraud-risk（10个wp_code条目）
2. THE K0.yaml render schema SHALL 准确反映10个sheet的component_type和class_code
3. THE account_package_registry.json SHALL 包含K0包（10 sheets按模板目录顺序）

### Requirement 2: K0-5其他应收款替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的其他应收款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE K0-5 SHALL 注册componentType: `confirmation-alternative-k05`
2. THE K0-5 SHALL 多公司Master-Detail（一公司一检查表，参照D0-5 GtConfirmationAlternativeD05模式，el-tabs按公司 + ElMessageBox.prompt新增公司）
3. THE K0-5 SHALL 顶部余额汇总区，显示：函证项目(其他应收款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期发生额 | 期后收款检查比例 | 往来对账比例
4. THE K0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE K0-5 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①期后收款检查：日期/凭证编号/业务内容/对方科目/金额 | 银行回单日期编号/收款方/金额 | 期后收回比例/索引号/是否异常
   - ②期末余额支持性证据：日期/凭证编号/业务内容/对方科目/金额 | 借款/垫款审批单日期编号/是否恰当审批 | 借据/协议编号/对方单位/金额/索引号/是否异常
   - ③本期发生额检查：日期/凭证编号/业务内容/对方科目/金额 | 原始单据日期编号/事由 | 审批凭证/审批人/金额/索引号/是否异常
   - ④往来对账/协议证据：日期/凭证编号/业务内容/对方科目/金额 | 对账单日期/对方余额/本方余额/对账差异 | 往来协议编号/签订日期/索引号/是否异常
6. THE K0-5 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE K0-5 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列（下拉）
8. THE K0-5 SHALL 支持从confirmation-hub的K0-1带入未回函公司（反向联动）
9. THE K0-5 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点，📎附件列）
10. THE K0-5 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE K0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE K0-5 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 3: K0-6其他应付款替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的其他应付款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE K0-6 SHALL 注册componentType: `confirmation-alternative-k06`
2. THE K0-6 SHALL 多公司Master-Detail（一公司一检查表，参照D0-6 GtConfirmationAlternativeD06模式，el-tabs按公司 + ElMessageBox.prompt新增公司）
3. THE K0-6 SHALL 顶部余额汇总区，显示：函证项目(其他应付款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期发生额 | 期后付款检查比例 | 往来对账比例
4. THE K0-6 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE K0-6 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①期后付款检查：日期/凭证编号/业务内容/对方科目/金额 | 付款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/金额/索引号/是否异常
   - ②期末余额支持性证据：日期/凭证编号/业务内容/对方科目/金额 | 借款/收款审批单日期编号/是否恰当审批 | 借据/协议编号/对方单位/金额/索引号/是否异常
   - ③本期发生额检查：日期/凭证编号/业务内容/对方科目/金额 | 原始单据日期编号/事由 | 审批凭证/审批人/金额/索引号/是否异常
   - ④往来对账/协议证据：日期/凭证编号/业务内容/对方科目/金额 | 对账单日期/对方余额/本方余额/对账差异 | 往来协议编号/签订日期/索引号/是否异常
6. THE K0-6 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE K0-6 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列（下拉）
8. THE K0-6 SHALL 支持从confirmation-hub的K0-1带入未回函公司（反向联动）
9. THE K0-6 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点，📎附件列）
10. THE K0-6 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE K0-6 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE K0-6 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 4: 独立composable与导入导出

**User Story:** As a 开发者, I want to K0-5/K0-6各有独立composable管理数据和导入导出, so that 代码组织清晰、复用D4导入导出模式。

#### Acceptance Criteria

1. THE K0-5 SHALL 有独立composable `useAlternativeK05Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
2. THE K0-6 SHALL 有独立composable `useAlternativeK06Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
3. THE K0-5/K0-6 SHALL 复用 `useK0ImportExport` 模式（composable封装三端点调用，后端3端点：export-template/export-data/import-data）
4. THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/k0/export-template?sheet=K0-5` 等
5. THE 导出模板 SHALL 包含4区块对应4个sheet（每个区块一个sheet，含列头+填写说明）
6. THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据回写checklist_responses

### Requirement 5: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的2个componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-k05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE `confirmation-alternative-k06` SHALL 在VALID_COMPONENT_TYPES中注册
3. THE htmlRendererRegistry SHALL 包含k05/k06→对应Vue组件的映射（defineAsyncComponent lazy）
4. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含confirmation-alternative-k05/k06
5. THE 后端RENDERER_DISPATCH SHALL 有k05/k06的render策略（复用confirmation通用renderer，返回checklist_responses snapshot）

### Requirement 6: 公式引擎（K0专属）

**User Story:** As a 开发者, I want to 实现K0-5/K0-6替代程序的合计/比例/对账差异公式引擎, so that 合计行/检查比例/对账差异计算可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现 `calcBlockTotal`（区块合计 = Σ金额列，空数组→0）
2. THE Formula_Engine SHALL 实现 `calcCheckRatio`（检查比例 = 已检查金额 / 期末余额，期末余额=0→0）
3. THE Formula_Engine SHALL 实现 `calcRowVariance`（行差异 = 账面金额 - 证据金额）
4. THE Formula_Engine SHALL 实现 `calcReconcileDiff`（对账差异 = 本方余额 - 对方余额）
5. THE Formula_Engine SHALL 实现 `isAbnormal`（是否异常 = |行差异| > 0）

### Requirement 7: 版本链集成

**User Story:** As a 审计助理, I want to K0函证底稿自动记录版本快照并可查看历史, so that 满足质量控制要求。

#### Acceptance Criteria

1. THE GtConfirmationAlternativeK05/K06 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
2. WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
3. THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板（右侧drawer）
4. THE useVersionTrail SHALL 支持手动创建命名快照（用户可输入备注）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证K0-5/K0-6公式引擎的正确性。

**P1: 区块合计公式** — ∀ amounts ∈ ℝ*: calcBlockTotal(amounts) === Σ amounts；空数组 → 0

**P2: 检查比例公式** — ∀ checked ∈ ℝ≥0, balance ∈ ℝ: calcCheckRatio(checked, balance) === balance>0 ? checked/balance : 0

**P3: 行差异公式** — ∀ book, evidence ∈ ℝ: calcRowVariance(book, evidence) === book - evidence；零差异恒等：calcRowVariance(v, v) === 0

**P4: 对账差异公式** — ∀ self, other ∈ ℝ: calcReconcileDiff(self, other) === self - other；calcReconcileDiff(v, v) === 0

**P5: 异常判定** — ∀ book, evidence ∈ ℝ: isAbnormal(calcRowVariance(book, evidence)) === (book ≠ evidence)
