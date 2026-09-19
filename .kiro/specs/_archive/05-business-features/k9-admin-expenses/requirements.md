# Requirements Document: K9 管理费用底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K管理费用循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6602发生额) + 截止双向 + 实质性分析
- **美观性**：分组配色 + 同比环比图表 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK9ImportExport
- **AI辅助**：多section AI（波动分析/截止结论）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K9管理费用底稿的专属HTML精美组件构建。覆盖来自 `K9 管理费用.xlsx` 的12个有效sheet。科目覆盖6602管理费用（**损益类！取发生额**）。

**K9核心特殊**：①**损益类科目**！取发生额非余额（从tb_ledger明细科目发生额取数）②**实质性分析程序引擎**（同比/环比/占收入比/异常波动识别）③**截止性测试双向**（记账凭证→原始凭证 + 原始凭证→记账凭证）④合同检查。审定表K9-1（73公式）+ 明细表K9-2（15公式）+ 实质性分析K9-4（16公式）+ 截止双向K9-6/K9-7。与K8销售费用同款方法论。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K9A**: 管理费用实质性程序表K9A（复用a-program-console）
- **Adjudication_K9_1**: 审定表K9-1，44行14列73公式，损益类6602审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），42行13列
- **Disclosure_SOE**: 附注披露信息（国企），42行13列
- **Detail_K9_2**: 明细表K9-2，55行25列15公式，按费用明细科目的发生额明细
- **Adjustment_K9_3**: 调整分录汇总K9-3
- **Substantive_Analysis_K9_4**: 实质性分析K9-4，48行16列16公式，同比环比波动分析
- **Contract_Check_K9_5**: 合同检查表K9-5
- **Cutoff_Voucher2Source_K9_6**: 截止性测试(记账凭证至原始凭证)K9-6
- **Cutoff_Source2Voucher_K9_7**: 截止性测试(原始凭证至记账凭证)K9-7
- **Admin_Check_K9_8**: 管理费用检查表K9-8
- **Analysis_Engine**: 实质性分析引擎（同比/环比/占比/波动）
- **Cutoff_Engine**: 截止测试引擎（序时账±期末天数抽样）
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6602，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K9管理费用按sheetName分发, so that 12个sheet有序组织。

#### Acceptance Criteria

1. THE K9 组件 SHALL 注册componentType: `k9-admin-expenses`，主入口GtK9AdminExpenses.vue
2. THE GtK9AdminExpenses.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K9 组件 SHALL defineAsyncComponent懒加载
4. THE K9 组件 SHALL 子目录：k9/core/（审定/明细/调整/附注） + k9/analysis/（实质性分析） + k9/cutoff/（截止双向） + k9/inspection/（合同/检查）
5. THE K9 组件 SHALL composable分层：useK9FormData + useK9FormulaEngine(纯函数) + useK9AnalysisEngine(纯函数) + useK9CutoffEngine + useK9CrossSheet + useK9DualMode + useK9ImportExport
6. THE K9 组件 SHALL htmlRendererRegistry注册'k9-admin-expenses'
7. THE K9 组件 SHALL wp_code_overrides: K9/K9-1~K9-8/K9A → 'k9-admin-expenses'
8. THE K9 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K9 组件 SHALL selfLoad支持
10. THE K9 组件 SHALL checklist_responses存储，前缀"K9-{sheet}-{field}"

### Requirement 2: 审定表K9-1（73公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看管理费用, so that 我能验证各明细费用发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K9_1 SHALL 按费用明细项目分行（职工薪酬/办公费/折旧摊销/中介机构费/研发费/税金/无形资产摊销/其他）
2. THE Adjudication_K9_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期借方发生额累计，不取期末余额
5. THE Adjudication_K9_1 SHALL 与K9-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6602，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K9_1 SHALL 底部审计说明+结论+复核入口，44行虚拟滚动

### Requirement 3: 明细表K9-2（25列15公式）

**User Story:** As a 审计助理, I want to 管理管理费用明细, so that 各明细科目发生额可逐项核对。

#### Acceptance Criteria

1. THE Detail_K9_2 SHALL 将25列拆为3区段Tab：基础(序号/明细科目/本期发生/上期发生) | 分析(同比/占收入比/波动说明) | 检查(凭证抽查/核查结论/备注)
2. THE Formula_Engine SHALL 从tb_ledger明细科目取发生额，合计行联动审定表
3. THE Detail_K9_2 SHALL 动态行新增+导入导出
4. THE Detail_K9_2 SHALL 55行虚拟滚动+底部统计

### Requirement 4: 实质性分析程序K9-4（16公式，分析引擎）

**User Story:** As a 审计助理, I want to 执行管理费用实质性分析, so that 我能识别异常波动。

#### Acceptance Criteria

1. THE Substantive_Analysis_K9_4 SHALL 显示：费用项目/本期/上期/同比变动额(公式)/同比变动率(公式)/占营业收入比(公式)/上期占比/波动阈值/是否异常(公式)/原因分析
2. THE Analysis_Engine SHALL 计算同比变动率=(本期-上期)/上期
3. THE Analysis_Engine SHALL 计算占收入比=费用/营业收入
4. THE Analysis_Engine SHALL 判断是否异常=|同比变动率|>阈值 OR 占比偏离>阈值
5. WHEN 判定异常时 SHALL 红色标记并要求填写原因分析
6. THE Substantive_Analysis_K9_4 SHALL 48行虚拟滚动+AI辅助生成波动分析

### Requirement 5: 截止性测试双向（K9-6记账至原始 + K9-7原始至记账）

**User Story:** As a 审计助理, I want to 双向执行截止性测试, so that 管理费用期末截止正确。

#### Acceptance Criteria

1. THE Cutoff_Voucher2Source_K9_6 SHALL 从记账凭证到原始凭证方向：凭证号/日期/摘要/金额/原始凭证日期/是否跨期/结论
2. THE Cutoff_Source2Voucher_K9_7 SHALL 从原始凭证到记账凭证方向：原始凭证/日期/金额/记账日期/是否及时入账/是否跨期/结论
3. THE Cutoff_Engine SHALL 自动从序时账提取期末±5天凭证作为测试样本（useCutoffAutoSampling）
4. THE Cutoff_Engine SHALL 判断是否跨期（原始凭证日期与记账日期分属不同会计期间）
5. WHEN 存在跨期项时 SHALL 红色标记并提示调整
6. THE 截止双向 SHALL 虚拟滚动+行级抽凭

### Requirement 6: 合同检查表K9-5 + 管理费用检查表K9-8

**User Story:** As a 审计助理, I want to 完成合同和综合检查, so that 管理费用合规性全覆盖。

#### Acceptance Criteria

1. THE Contract_Check_K9_5 SHALL 检查重大费用合同（中介服务/咨询/租赁）的真实性/金额匹配/审批
2. THE Admin_Check_K9_8 SHALL 综合检查表，逐项"合规/不合规/不适用"判断
3. THE 检查表组 SHALL 支持行级抽凭+行级OCR（合同/发票）
4. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 7: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K9不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（费用类借方发生累计），非tb_balance期末余额
2. THE TB取数 SHALL 使用损益类专用取数逻辑（发生额）
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
4. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 8: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市42×13/国企42×13）+按费用性质披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K9_3 SHALL 借贷平衡+双向同步K9-1+publish 'adjustment:created'→A13+导入导出

### Requirement 9: 实质性分析引擎与公式引擎（纯函数）

**User Story:** As a 开发者, I want to 实现分析与公式纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcIncomeStatementOccurrence(debitOcc, creditOcc): 费用类发生额=借方发生-贷方发生
3. THE Analysis_Engine SHALL calcYoYChange(current, prior): 同比变动率=(本期-上期)/上期
4. THE Analysis_Engine SHALL calcRatioToRevenue(expense, revenue): 占收入比
5. THE Analysis_Engine SHALL isAbnormalFluctuation(changeRate, threshold): 异常判断
6. THE Formula_Engine SHALL calcSubtotal(arr): 合计
7. THE Cutoff_Engine SHALL isCrossPeriod(sourceDate, bookDate, periodEnd): 跨期判断
