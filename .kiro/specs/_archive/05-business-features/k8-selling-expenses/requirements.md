# Requirements Document: K8 销售费用底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K销售费用循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6601发生额) + 截止双向 + 实质性分析
- **美观性**：分组配色 + 同比环比图表 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK8ImportExport
- **AI辅助**：多section AI（波动分析/截止结论）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K8销售费用底稿的专属HTML精美组件构建。覆盖来自 `K8 销售费用.xlsx` 的12个有效sheet。科目覆盖6601销售费用（**损益类！取发生额**）。

**K8核心特殊**：①**损益类科目**！取发生额非余额（从tb_ledger明细科目发生额取数）②**实质性分析程序引擎**（同比/环比/占收入比/异常波动识别）③**截止性测试双向**（记账凭证→原始凭证 + 原始凭证→记账凭证）④合同检查。审定表K8-1（73公式）+ 明细表K8-2（13公式）+ 实质性分析K8-4（25公式）+ 截止双向K8-6/K8-7（各44行）。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K8A**: 销售费用实质性程序表K8A（复用a-program-console）
- **Adjudication_K8_1**: 审定表K8-1，29行12列73公式，损益类6601审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），42行28列
- **Disclosure_SOE**: 附注披露信息（国企），30行5列
- **Detail_K8_2**: 明细表K8-2，48行27列13公式，按费用明细科目的发生额明细
- **Adjustment_K8_3**: 调整分录汇总K8-3
- **Substantive_Analysis_K8_4**: 实质性分析K8-4，39行17列25公式，同比环比波动分析
- **Contract_Check_K8_5**: 合同检查表K8-5
- **Cutoff_Voucher2Source_K8_6**: 截止性测试(记账凭证至原始凭证)K8-6，44行11列
- **Cutoff_Source2Voucher_K8_7**: 截止性测试(原始凭证至记账凭证)K8-7，44行12列
- **Selling_Check_K8_8**: 销售费用检查表K8-8
- **Analysis_Engine**: 实质性分析引擎（同比/环比/占比/波动）
- **Cutoff_Engine**: 截止测试引擎（序时账±期末天数抽样）
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6601，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K8销售费用按sheetName分发, so that 12个sheet有序组织。

#### Acceptance Criteria

1. THE K8 组件 SHALL 注册componentType: `k8-selling-expenses`，主入口GtK8SellingExpenses.vue
2. THE GtK8SellingExpenses.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K8 组件 SHALL defineAsyncComponent懒加载
4. THE K8 组件 SHALL 子目录：k8/core/（审定/明细/调整/附注） + k8/analysis/（实质性分析） + k8/cutoff/（截止双向） + k8/inspection/（合同/检查）
5. THE K8 组件 SHALL composable分层：useK8FormData + useK8FormulaEngine(纯函数) + useK8AnalysisEngine(纯函数) + useK8CutoffEngine + useK8CrossSheet + useK8DualMode + useK8ImportExport
6. THE K8 组件 SHALL htmlRendererRegistry注册'k8-selling-expenses'
7. THE K8 组件 SHALL wp_code_overrides: K8/K8-1~K8-8/K8A → 'k8-selling-expenses'
8. THE K8 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K8 组件 SHALL selfLoad支持
10. THE K8 组件 SHALL checklist_responses存储，前缀"K8-{sheet}-{field}"

### Requirement 2: 审定表K8-1（73公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看销售费用, so that 我能验证各明细费用发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K8_1 SHALL 按费用明细项目分行（职工薪酬/差旅费/业务招待费/广告宣传费/运输费/折旧摊销/其他）
2. THE Adjudication_K8_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期借方发生额累计（费用类借方增加），不取期末余额
5. THE Adjudication_K8_1 SHALL 与K8-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6601，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K8_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K8-2（27列13公式）

**User Story:** As a 审计助理, I want to 管理销售费用明细, so that 各明细科目发生额可逐项核对。

#### Acceptance Criteria

1. THE Detail_K8_2 SHALL 将27列拆为3区段Tab：基础(序号/明细科目/本期发生/上期发生) | 分析(同比/占收入比/波动说明) | 检查(凭证抽查/核查结论/备注)
2. THE Formula_Engine SHALL 从tb_ledger明细科目取发生额，合计行联动审定表
3. THE Detail_K8_2 SHALL 动态行新增+导入导出
4. THE Detail_K8_2 SHALL 48行虚拟滚动+底部统计

### Requirement 4: 实质性分析程序K8-4（25公式，分析引擎）

**User Story:** As a 审计助理, I want to 执行销售费用实质性分析, so that 我能识别异常波动。

#### Acceptance Criteria

1. THE Substantive_Analysis_K8_4 SHALL 显示：费用项目/本期/上期/同比变动额(公式)/同比变动率(公式)/占营业收入比(公式)/上期占比/波动阈值/是否异常(公式)/原因分析
2. THE Analysis_Engine SHALL 计算同比变动率=(本期-上期)/上期
3. THE Analysis_Engine SHALL 计算占收入比=费用/营业收入
4. THE Analysis_Engine SHALL 判断是否异常=|同比变动率|>阈值 OR 占比偏离>阈值
5. WHEN 判定异常时 SHALL 红色标记并要求填写原因分析
6. THE Substantive_Analysis_K8_4 SHALL 39行虚拟滚动+AI辅助生成波动分析

### Requirement 5: 截止性测试双向（K8-6记账至原始 + K8-7原始至记账）

**User Story:** As a 审计助理, I want to 双向执行截止性测试, so that 销售费用期末截止正确。

#### Acceptance Criteria

1. THE Cutoff_Voucher2Source_K8_6 SHALL 从记账凭证到原始凭证方向：凭证号/日期/摘要/金额/原始凭证日期/是否跨期/结论
2. THE Cutoff_Source2Voucher_K8_7 SHALL 从原始凭证到记账凭证方向：原始凭证/日期/金额/记账日期/是否及时入账/是否跨期/结论
3. THE Cutoff_Engine SHALL 自动从序时账提取期末±5天凭证作为测试样本（useCutoffAutoSampling）
4. THE Cutoff_Engine SHALL 判断是否跨期（原始凭证日期与记账日期分属不同会计期间）
5. WHEN 存在跨期项时 SHALL 红色标记并提示调整
6. THE 截止双向 SHALL 各44行虚拟滚动+行级抽凭

### Requirement 6: 合同检查表K8-5 + 销售费用检查表K8-8

**User Story:** As a 审计助理, I want to 完成合同和综合检查, so that 销售费用合规性全覆盖。

#### Acceptance Criteria

1. THE Contract_Check_K8_5 SHALL 检查重大费用合同（广告/推广/运输）的真实性/金额匹配/审批
2. THE Selling_Check_K8_8 SHALL 综合检查表，逐项"合规/不合规/不适用"判断
3. THE 检查表组 SHALL 支持行级抽凭+行级OCR（合同/发票）
4. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 7: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K8不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（费用类借方发生累计），非tb_balance期末余额
2. THE TB取数 SHALL 使用损益类专用取数逻辑（发生额）
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
4. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 8: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市42×28/国企30×5）+按费用性质披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K8_3 SHALL 借贷平衡+双向同步K8-1+publish 'adjustment:created'→A13+导入导出

### Requirement 9: 实质性分析引擎与公式引擎（纯函数）

**User Story:** As a 开发者, I want to 实现分析与公式纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcIncomeStatementOccurrence(debitOcc, creditOcc): 费用类发生额=借方发生-贷方发生（红冲）
3. THE Analysis_Engine SHALL calcYoYChange(current, prior): 同比变动率=(本期-上期)/上期
4. THE Analysis_Engine SHALL calcRatioToRevenue(expense, revenue): 占收入比
5. THE Analysis_Engine SHALL isAbnormalFluctuation(changeRate, threshold): 异常判断
6. THE Formula_Engine SHALL calcSubtotal(arr): 合计
7. THE Cutoff_Engine SHALL isCrossPeriod(sourceDate, bookDate, periodEnd): 跨期判断
