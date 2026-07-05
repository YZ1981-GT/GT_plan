# Requirements Document

## Introduction

H0固定资产循环函证，覆盖科目：固定资产/在建工程/融资租赁资产/长期资产权属等的第三方函证确认（银行借款抵押物/在建工程进度/融资租赁/权属证明）。源模板1个xlsx文件9个sheet。

**核心架构决策（对齐D0实际实现 + F0 pattern）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用（🔴铁律：函证模块跨循环共享）
- H0-1~H0-4/H0-6/H0-7直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-reliability / confirmation-fraud-risk）
- **仅H0-5需要新建**：固定资产循环替代程序4区块（按固定资产/在建工程科目），参照D0-5模式。只有1个替代程序（不像F0有F0-5/F0-6两个）
- H0A程序表复用`a-program-console`

**与D0的差异**：
- D0科目：应收账款/合同资产/其他应收款（收入循环）
- H0科目：固定资产/在建工程/融资租赁/长期资产权属（固定资产循环）
- H0-5替代程序4区块：期后验收权属证据/期末余额支持性证据/本期新增资产检查/抵押担保融资租赁证据

**源模板sheet清单（openpyxl实读）**：

| # | Sheet名 | 行×列 | wp_code | componentType | 新建/复用 |
|---|---------|-------|---------|---------------|-----------|
| 1 | 底稿目录 | - | - | b-index | 复用 |
| 2 | 函证程序表H0A | - | H0A | a-program-console | 复用 |
| 3 | 函证结果汇总表H0-1 | 69×33(52公式) | H0-1 | confirmation-summary | 复用D0 |
| 4 | 核实被函证单位信息H0-2 | 41×40(10公式) | H0-2 | confirmation-entity-verify | 复用D0 |
| 5 | 跟函函证过程控制H0-3 | 37×18 | H0-3 | confirmation-followup | 复用D0 |
| 6 | 差异核对表H0-4 | 21×9(6公式) | H0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | 替代程序H0-5 | 35×29 | H0-5 | confirmation-alternative-h05 | **新建** |
| 8 | 邮件传真回函可靠性验证H0-6 | 39×20 | H0-6 | confirmation-reliability | 复用D0 |
| 9 | 函证程序舞弊风险评价表H0-7 | 31×10 | H0-7 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType（confirmation-summary/entity-verify/followup/diff-reconcile/diff-checklist/reliability/fraud-risk + 循环特有的alternative-xxx）
- **替代程序**: 对未回函的被询证单位执行的审计替代程序（检查期后验收/权属证据/余额支持性证据等），4区块检查宽表结构按科目不同
- **合计行**: 每区块底部SUM金额列，等于该区块所有明细行金额之和

## Requirements

### Requirement 1: H0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to H0各sheet映射到D0共享组件, so that H0函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：H0→confirmation-hub, H0A→a-program-console, H0-1→confirmation-summary, H0-2→confirmation-entity-verify, H0-3→confirmation-followup, H0-4→confirmation-diff-reconcile, H0-5→confirmation-alternative-h05, H0-6→confirmation-reliability, H0-7→confirmation-fraud-risk
2. THE H0.yaml render schema SHALL 准确反映9个sheet的component_type和class_code
3. THE account_package_registry.json SHALL 包含H0包（9 sheets按模板目录顺序）
4. THE 底稿目录 SHALL 映射到`b-index`（复用）

### Requirement 2: H0-5固定资产循环替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的抵押/担保/大额固定资产执行替代程序, so that 我能获取充分适当的审计证据。

#### Acceptance Criteria

1. THE H0-5 SHALL 注册componentType: `confirmation-alternative-h05`
2. THE H0-5 SHALL 多公司/多被函证对象Master-Detail（一对象一检查表，参照D0-5 GtConfirmationAlternativeD05模式）
3. THE H0-5 SHALL 顶部余额汇总区，显示：函证项目(固定资产/抵押借款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 抵押/担保金额 | 大额资产检查比例 | 抵押函证检查比例
4. THE H0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE H0-5 多区块 SHALL 为（每区块独立el-table动态行，按固定资产循环证据类型设计）：
   - ①大额单笔资产产权核查：日期/凭证编号/资产名称/对方科目/金额 | 产权证编号/发证日期/权属人 | 评估报告编号/评估值 | 索引号/是否异常
   - ②抵押/担保合同核查：抵押物名称/账面价值 | 抵押合同编号/抵押权人(银行) | 担保金额/担保期限 | 对应借款(L1/L3索引) | 索引号/是否异常
   - ③期后事项/银行对账核查：日期/凭证编号/业务内容/金额 | 银行对账单日期/银行名称 | 抵质押余额/或有事项 | 索引号/是否异常
6. THE H0-5 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证列 | 检查证据列），减少横向滚动
7. THE H0-5 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列(GtIndexChip) + 是否异常列
8. THE H0-5 SHALL 支持从confirmation-hub的H0-1带入未回函对象（反向联动）
9. THE H0-5 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点）
10. THE H0-5 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE H0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE H0-5 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）
13. THE H0-5 SHALL 支持与H1固定资产抵押、L1/L3银行借款抵质押的交叉核对索引（ref_index chip可跳转）

### Requirement 3: 独立composable与导入导出

**User Story:** As a 开发者, I want to H0-5有独立composable管理数据和导入导出, so that 代码组织清晰、复用D4导入导出模式。

#### Acceptance Criteria

1. THE H0-5 SHALL 有独立composable `useAlternativeH05Data.ts`（多区块CRUD+持久化+loadAll+persistAll+合计计算）
2. THE H0-5 SHALL 复用 `useXImportExport` 模式（composable封装三端点调用，后端3端点：export-template/export-data/import-data）
3. THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/h0/export-template?sheet=H0-5` 等
4. THE 导出模板 SHALL 包含各区块对应sheet（每个区块一个sheet，含列头+填写说明）
5. THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-h05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE htmlRendererRegistry SHALL 包含h05→GtConfirmationAlternativeH05的映射
3. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含confirmation-alternative-h05
4. THE 后端RENDERER_DISPATCH SHALL 有h05的render策略（复用confirmation通用renderer，返回checklist_responses snapshot）

### Requirement 5: 跨循环联动集成

**User Story:** As a 审计助理, I want to H0函证与固定资产/借款底稿联动, so that 抵押担保信息全链可追溯。

#### Acceptance Criteria

1. THE H0-5 SHALL 支持从H1固定资产明细带入抵押资产（ref_index引用H1索引）
2. THE H0-5 SHALL 支持与L1短期借款/L3长期借款抵质押检查表交叉核对（ref_index chip可跳转）
3. WHEN 抵押金额与借款底稿不一致时, THE H0-5 SHALL 标记差异供审计人员核查
4. THE H0-5 SHALL 通过EventBus订阅confirmation:updated事件刷新未回函对象列表

### Requirement 6: 版本链集成

**User Story:** As a 审计助理, I want to H0函证底稿自动记录每次保存的版本快照并可查看历史, so that 我能追溯底稿变更过程、对比差异、满足质量控制要求。

#### Acceptance Criteria

1. THE GtConfirmationAlternativeH05 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
2. WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（调用 POST /api/workpapers/{wp_id}/versions/snapshot）
3. THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板（右侧drawer）
4. THE GtWpVersionTrail SHALL 显示版本列表（时间/操作人/摘要），支持点击查看 VersionDiffPanel 差异对比
5. THE VersionDiffPanel SHALL 高亮显示两个版本间的数据变更（新增行/删除行/修改单元格）
6. THE useVersionTrail SHALL 支持手动创建命名快照（用户可输入备注如"一审完成"/"复核修改"）
7. THE 版本快照 SHALL 记录当前allResponses完整JSON + 操作人 + 时间戳

### Requirement 7: 复用D0共享组件（配置即用，零新代码）

**User Story:** As a 开发者, I want to H0-1~H0-4/H0-6/H0-7直接复用D0共享组件, so that 无需重复开发即可获得完整函证功能。

#### Acceptance Criteria

1. THE H0-1 SHALL 通过overrides映射到confirmation-summary（无新代码）
2. THE H0-2 SHALL 通过overrides映射到confirmation-entity-verify（无新代码）
3. THE H0-3 SHALL 通过overrides映射到confirmation-followup（无新代码）
4. THE H0-4 SHALL 通过overrides映射到confirmation-diff-reconcile（无新代码）
5. THE H0-6 SHALL 通过overrides映射到confirmation-reliability（无新代码）
6. THE H0-7 SHALL 通过overrides映射到confirmation-fraud-risk（无新代码）
7. THE confirmation-hub SHALL 按wp_code自动路由H0系列各sheet到对应共享组件

## Requirements

### Requirement 1: H0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to H0各sheet映射到D0共享组件, so that H0固定资产循环函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：H0→confirmation-hub, H0A→a-program-console, H0-1→confirmation-summary, H0-2→confirmation-entity-verify, H0-3→confirmation-followup, H0-4→confirmation-diff-reconcile, H0-5→confirmation-alternative-h05, H0-6→confirmation-reliability, H0-7→confirmation-fraud-risk（9个wp_code条目）
2. THE H0.yaml render schema SHALL 准确反映9个sheet的component_type和class_code
3. THE account_package_registry.json SHALL 包含H0包（9 sheets按模板目录顺序）

### Requirement 2: H0-5固定资产循环替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的固定资产/在建工程执行替代程序, so that 我能获取充分适当的存在性/权属/计价证据。

#### Acceptance Criteria

1. THE H0-5 SHALL 注册componentType: `confirmation-alternative-h05`
2. THE H0-5 SHALL 多公司Master-Detail（一公司一检查表，参照D0-5 GtConfirmationAlternativeD05模式，el-tabs按公司 + ElMessageBox.prompt新增公司）
3. THE H0-5 SHALL 顶部余额汇总区，显示：函证项目(固定资产/在建工程) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期新增金额 | 权属证据检查比例 | 期后验收检查比例
4. THE H0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE H0-5 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①期后验收/权属证据检查：日期/凭证编号/业务内容/对方科目/金额 | 验收单日期编号/资产名称/规格型号/数量 | 权属证书编号/权属人/取得日期 | 索引号/是否异常
   - ②期末余额支持性证据（合同/发票/付款凭证）：日期/凭证编号/业务内容/对方科目/金额 | 采购合同日期编号/供应商/合同金额 | 采购发票日期编号/金额 | 付款凭证日期/金额/索引号/是否异常
   - ③本期新增资产检查：日期/凭证编号/业务内容/对方科目/金额 | 请购审批单日期编号/是否恰当审批 | 到货验收单日期/资产名称/数量 | 转固日期/原值/索引号/是否异常
   - ④抵押担保/融资租赁证据：日期/凭证编号/业务内容/对方科目/金额 | 抵押合同编号/抵押权人/担保金额 | 融资租赁合同编号/出租方/租赁期 | 他项权证编号/索引号/是否异常
6. THE H0-5 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE H0-5 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列（下拉）
8. THE H0-5 SHALL 支持从confirmation-hub的H0-1带入未回函公司（反向联动）
9. THE H0-5 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点，📎附件列）
10. THE H0-5 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE H0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE H0-5 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 3: 独立composable与导入导出

**User Story:** As a 开发者, I want to H0-5有独立composable管理数据和导入导出, so that 代码组织清晰、复用D4导入导出模式。

#### Acceptance Criteria

1. THE H0-5 SHALL 有独立composable `useAlternativeH05Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
2. THE H0-5 SHALL 复用 `useH0ImportExport` 模式（composable封装三端点调用，后端3端点：export-template/export-data/import-data）
3. THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/h0/export-template?sheet=H0-5` 等
4. THE 导出模板 SHALL 包含4区块对应4个sheet（每个区块一个sheet，含列头+填写说明）
5. THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据回写checklist_responses

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-h05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE htmlRendererRegistry SHALL 包含h05→对应Vue组件的映射（defineAsyncComponent lazy）
3. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含confirmation-alternative-h05
4. THE 后端RENDERER_DISPATCH SHALL 有h05的render策略（复用confirmation通用renderer，返回checklist_responses snapshot）

### Requirement 5: 公式引擎（H0专属）

**User Story:** As a 开发者, I want to 实现H0-5替代程序的合计与比例公式引擎, so that 合计行/检查比例计算可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现 `calcBlockTotal`（区块合计 = Σ金额列）
2. THE Formula_Engine SHALL 实现 `calcCheckRatio`（检查比例 = 已检查金额 / 期末余额，期末余额=0→0）
3. THE Formula_Engine SHALL 实现 `calcRowVariance`（行差异 = 账面金额 - 证据金额）
4. THE Formula_Engine SHALL 实现 `isAbnormal`（是否异常 = |行差异| > 0）

### Requirement 6: 版本链集成

**User Story:** As a 审计助理, I want to H0函证底稿自动记录版本快照并可查看历史, so that 满足质量控制要求。

#### Acceptance Criteria

1. THE GtConfirmationAlternativeH05 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
2. WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
3. THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板（右侧drawer）
4. THE useVersionTrail SHALL 支持手动创建命名快照（用户可输入备注）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证H0-5公式引擎的正确性。

**P1: 区块合计公式** — ∀ amounts ∈ ℝ*: calcBlockTotal(amounts) === Σ amounts；空数组 → 0

**P2: 检查比例公式** — ∀ checked ∈ ℝ≥0, balance ∈ ℝ: calcCheckRatio(checked, balance) === balance>0 ? checked/balance : 0

**P3: 行差异公式** — ∀ book, evidence ∈ ℝ: calcRowVariance(book, evidence) === book - evidence；零差异恒等：calcRowVariance(v, v) === 0

**P4: 异常判定** — ∀ book, evidence ∈ ℝ: isAbnormal(calcRowVariance(book, evidence)) === (book ≠ evidence)
