# Requirements Document

## Introduction

F0存货循环函证（采购与付款循环），覆盖科目：预付账款/应付票据/应付账款/采购。源模板1个xlsx文件11个sheet。

**核心架构决策（对齐D0实际实现）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用
- F0-1~F0-4/F0-4b/F0-7/F0-8直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-diff-checklist / confirmation-reliability / confirmation-fraud-risk）
- **仅F0-5/F0-6需要新建**：替代程序4区块按科目不同（预付账款 vs 应付账款），参照D0-5/D0-6模式
- F0A程序表复用`a-program-console`

**与D0的差异**：
- D0科目：应收账款/合同资产/其他应收款（收入循环）
- F0科目：预付账款/应付票据/应付账款/采购（采购与付款循环）
- F0-5替代程序4区块：期后收货/期末余额证据/本期付款/本期采购证据
- F0-6替代程序4区块：期后付款/期末余额证据/本期采购/本期入库证据

**源模板sheet清单（openpyxl实读2026-07-01）**：

| # | Sheet名 | wp_code | componentType | 新建/复用 |
|---|---------|---------|---------------|-----------|
| 1 | 底稿目录 | - | b-index | 复用 |
| 2 | 函证程序表F0A | F0A | a-program-console | 复用 |
| 3 | 函证结果汇总表F0-1 | F0-1 | confirmation-summary | 复用D0 |
| 4 | 核实被函证单位信息F0-2 | F0-2 | confirmation-entity-verify | 复用D0 |
| 5 | 跟函函证过程控制F0-3 | F0-3 | confirmation-followup | 复用D0 |
| 6 | 函证差异调节表F0-4 | F0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | 函证差异检查表（示例）| 函证差异检查表（示例）| confirmation-diff-checklist | 复用D0 |
| 8 | 预付及采购替代程序F0-5 | F0-5 | confirmation-alternative-f05 | **新建** |
| 9 | 应付及采购替代程序F0-6 | F0-6 | confirmation-alternative-f06 | **新建** |
| 10 | 邮件传真回函可靠性验证F0-7 | F0-7 | confirmation-reliability | 复用D0 |
| 11 | 函证程序舞弊风险评价表F0-8 | F0-8 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType（confirmation-summary/entity-verify/followup/diff-reconcile/diff-checklist/reliability/fraud-risk + 循环特有的alternative-xxx）
- **替代程序**: 对未回函的被询证单位执行的审计替代程序（检查期后收付款/余额支持性证据等），4区块检查宽表结构按科目不同

## Requirements

### Requirement 1: F0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to F0各sheet映射到D0共享组件, so that F0函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：F0→confirmation-hub, F0A→a-program-console, F0-1→confirmation-summary, F0-2→confirmation-entity-verify, F0-3→confirmation-followup, F0-4→confirmation-diff-reconcile, F0-4b→confirmation-diff-checklist, F0-5→confirmation-alternative-f05, F0-6→confirmation-alternative-f06, F0-7→confirmation-reliability, F0-8→confirmation-fraud-risk
2. THE F0.yaml render schema SHALL 准确反映11个sheet的component_type和class_code
3. THE account_package_registry.json SHALL 包含F0包（11 sheets按模板顺序）

### Requirement 2: F0-5预付及采购替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的预付账款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE F0-5 SHALL 注册componentType: `confirmation-alternative-f05`
2. THE F0-5 SHALL 多公司Master-Detail（一公司一检查表，参照D0-5 GtConfirmationAlternativeD05模式）
3. THE F0-5 SHALL 顶部余额汇总区，显示：函证项目(预付账款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期采购金额 | 本期付款检查比例 | 本期入库检查比例
4. THE F0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE F0-5 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①预付账款期后收货检查（15列）：日期/凭证编号/业务内容/对方科目/金额 | 入库单日期编号/品名/单位/数量 | 采购发票日期编号/对手方/金额 | 索引号/是否异常
   - ②预付账款期末余额支持性证据（13列）：日期/凭证编号/业务内容/对方科目/金额 | 付款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/金额 | 合同供应商/合同金额/预付比例
   - ③本期付款检查（13列）：日期/凭证编号/业务内容/对方科目/金额 | 付款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/金额 | 采购发票日期编号/对手方/金额
   - ④本期采购入库证据（15列）：日期/凭证编号/业务内容/对方科目/金额 | 入库单日期编号/品名/单位/数量 | 合同日期编号/供应商/金额 | 采购发票日期编号/对手方/金额
6. THE F0-5 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE F0-5 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列
8. THE F0-5 SHALL 支持从confirmation-hub的F0-1带入未回函公司（反向联动）
9. THE F0-5 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点）
10. THE F0-5 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE F0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE F0-5 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 3: F0-6应付及采购替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的应付账款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE F0-6 SHALL 注册componentType: `confirmation-alternative-f06`
2. THE F0-6 SHALL 多公司Master-Detail（一公司一检查表，参照D0-6 GtConfirmationAlternativeD06模式）
3. THE F0-6 SHALL 顶部余额汇总区，显示：函证项目(应付票据商业承兑/应付账款) | 年初余额 | 借方发生额 | 贷方发生额 | 期末余额 + 本期采购金额 | 本期入库检查比例 | 本期付款检查比例
4. THE F0-6 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
5. THE F0-6 4区块 SHALL 为（每区块独立el-table动态行，按xlsx实际列结构）：
   - ①应付余额支持性证据检查（15列）：日期/凭证编号/业务内容/对方科目/金额 | 入库单日期编号/品名/单位/数量 | 合同日期/供应商/合同金额 | 采购发票日期编号/对手方/金额
   - ②期后付款检查（13列）：日期/凭证编号/业务内容/对方科目/金额 | 付款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/金额 | 采购发票日期编号/对手方/金额
   - ③本期采购入库证据（15列）：日期/凭证编号/业务内容/对方科目/金额 | 入库单日期编号/品名/单位/数量 | 合同日期编号/供应商/金额 | 采购发票日期编号/对手方/金额
   - ④本期付款检查（13列）：日期/凭证编号/业务内容/对方科目/金额 | 付款审批单日期编号/是否恰当审批 | 银行回单日期/收款方/金额 | 采购发票日期编号/对手方/金额
6. THE F0-6 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
7. THE F0-6 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列 + 是否异常列
8. THE F0-6 SHALL 支持从confirmation-hub的F0-1带入未回函公司（反向联动）
9. THE F0-6 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点）
10. THE F0-6 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
11. THE F0-6 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
12. THE F0-6 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）

### Requirement 5: 独立composable与导入导出

**User Story:** As a 开发者, I want to F0-5/F0-6各有独立composable管理数据和导入导出, so that 代码组织清晰、复用D4导入导出模式。

#### Acceptance Criteria

1. THE F0-5 SHALL 有独立composable `useAlternativeF05Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
2. THE F0-6 SHALL 有独立composable `useAlternativeF06Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
3. THE F0-5/F0-6 SHALL 复用 `useXImportExport` 模式（composable封装三端点调用，后端3端点：export-template/export-data/import-data）
4. THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/f0/export-template?sheet=F0-5` 等
5. THE 导出模板 SHALL 包含4区块对应4个sheet（每个区块一个sheet，含列头+填写说明）
6. THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的2个componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-f05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE `confirmation-alternative-f06` SHALL 在VALID_COMPONENT_TYPES中注册
3. THE htmlRendererRegistry SHALL 包含f05/f06→对应Vue组件的映射
4. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含f05/f06
5. THE 后端RENDERER_DISPATCH SHALL 有f05/f06的render策略（复用confirmation通用renderer）


### Requirement 6: 版本链集成

**User Story:** As a 审计助理, I want to F0函证底稿自动记录每次保存的版本快照并可查看历史, so that 我能追溯底稿变更过程、对比差异、满足质量控制要求。

#### Acceptance Criteria

1. THE GtConfirmationAlternativeF05/F06 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
2. WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（调用 POST /api/workpapers/{wp_id}/versions/snapshot）
3. THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板（右侧drawer）
4. THE GtWpVersionTrail SHALL 显示版本列表（时间/操作人/摘要），支持点击查看 VersionDiffPanel 差异对比
5. THE VersionDiffPanel SHALL 高亮显示两个版本间的数据变更（新增行/删除行/修改单元格）
6. THE useVersionTrail SHALL 支持手动创建命名快照（用户可输入备注如"一审完成"/"复核修改"）
7. THE 版本快照 SHALL 记录当前allResponses完整JSON + 操作人 + 时间戳
