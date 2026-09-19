# Requirements Document: I6 研发费用底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：**I6↔I2双向联动（核心！）** + TB回写(**发生额！**) + 附注
- **美观性**：分组配色 + 月度趋势图 + 进度条
- **跳转溯源**：GtIndexChip跳转I2 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 编制提示
- **导入导出**：el-dropdown三级 + useI6ImportExport
- **AI辅助**：审计说明+异常分析
- **双模式**：el-segmented + OO降级

## Introduction

I6研发费用底稿的专属HTML精美组件构建。覆盖来自 `I6 研发费用.xlsx` 的11个有效sheet。科目6602研发费用（**损益类！贷方科目**，取发生额非余额）。

**I6核心特殊**：①**损益类科目！**取发生额非余额（与H10同款处理）②**I6↔I2双向联动**：同一研发活动的费用化(I6)与资本化(I2)，VR-I6-01: 研发总额=费用化+资本化 ③月度明细表12列横向（类D4-2月度宽表）④截止性测试双向。关键公式总数约120+（审定表73公式密度极高！）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_I6A**: 研发费用实质性程序表I6A
- **Adjudication_I6_1**: 审定表I6-1，27行11列**73公式！**（公式密度最高）
- **Disclosure_Listed**: 附注上市公司，19行7列24公式
- **Disclosure_SOE**: 附注国企，16行6列24公式
- **Detail_I6_2**: 明细表I6-2，44行65列23公式 — 月度12列横向宽表
- **Adjustment_I6_3**: 调整分录汇总I6-3
- **Targeted_Check_I6_4**: 其他针对性检查表I6-4
- **Cutoff_Forward_I6_5**: 截止性测试（账到单据）I6-5
- **Cutoff_Backward_I6_6**: 截止性测试（单据到账）I6-6
- **Income_Statement_Rule**: 损益类取数规则：取发生额非余额！
- **Cross_WP_I6_I2**: I6↔I2双向联动（VR-I6-01）
- **Monthly_Matrix**: 月度12列横向矩阵（1月~12月各列）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I6研发费用按sheetName分发, so that 11个sheet有序组织。

#### Acceptance Criteria

1. THE I6 组件 SHALL 注册componentType: `i6-research-development-expense`，主入口GtI6ResearchDevelopmentExpense.vue
2. THE GtI6ResearchDevelopmentExpense.vue SHALL 接收sheetName prop，v-if分发
3. THE I6 组件 SHALL defineAsyncComponent懒加载
4. THE I6 组件 SHALL 子目录：i6/core/、i6/cutoff/
5. THE I6 组件 SHALL composable分层：useI6FormData + useI6FormulaEngine(损益类！) + useI6CrossSheet + useI6DualMode + useI6ImportExport
6. THE I6 组件 SHALL htmlRendererRegistry注册'i6-research-development-expense'
7. THE I6 组件 SHALL wp_code_overrides: I6/I6-1~I6-6/I6A → 'i6-research-development-expense'
8. THE I6 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE I6 组件 SHALL selfLoad支持
10. THE I6 组件 SHALL checklist_responses存储，前缀"I6-{sheet}-{field}"

### Requirement 2: 审定表I6-1（损益类！73公式，取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看研发费用, so that 我能验证费用化金额和发生额正确。

#### Acceptance Criteria

1. THE Adjudication_I6_1 SHALL 显示：项目|借方发生(费用增加)|贷方发生(费用冲回)|净发生额|未审|AJE|RJE|审定数|同期|变动率|备注
2. THE Formula_Engine SHALL **损益类！**净发生额=借方发生-贷方发生（6602借方=费用增加）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_I6_1 SHALL **取发生额非余额**！TB取数来源为tb_ledger发生额汇总
5. THE Adjudication_I6_1 SHALL 变动率=(本期-同期)/同期×100%
6. THE Adjudication_I6_1 SHALL TB取数+差异+writebackTB(**发生额**，科目6602)
7. THE Adjudication_I6_1 SHALL 审计说明+结论+复核对话
8. THE Adjudication_I6_1 SHALL 显示"研发费用化vs资本化分拆校验"行（联动I2）

### Requirement 3: 明细表I6-2（月度12列横向宽表）

**User Story:** As a 审计助理, I want to 查看研发费用月度明细, so that 我能按月追踪费用发生趋势。

#### Acceptance Criteria

1. THE Detail_I6_2 SHALL 44行65列拆为：固定列(项目名/费用类别) + 12月份列(1月~12月各月金额) + 合计列
2. THE Detail_I6_2 SHALL 固定前2列（项目/类别），12月份列横向滚动
3. THE Formula_Engine SHALL 合计列=SUM(1月~12月)
4. THE Detail_I6_2 SHALL 底部合计行=各列SUM
5. THE Detail_I6_2 SHALL 合计行联动审定表净发生额
6. THE Detail_I6_2 SHALL 月度趋势折线图（顶部可折叠）
7. THE Detail_I6_2 SHALL 动态行+导入导出

### Requirement 4: I6↔I2双向联动（核心！）

**User Story:** As a 审计助理, I want to 研发费用与开发支出双向联动, so that 费用化+资本化=研发总额。

#### Acceptance Criteria

1. THE Cross_WP_I6_I2 SHALL 通过cross_wp_references建立双向引用
2. THE Cross_WP_I6_I2 SHALL EventBus publish 'research:expense-updated'（I6保存时）
3. THE Cross_WP_I6_I2 SHALL EventBus subscribe I2的'development:capitalized-updated'
4. THE Cross_WP_I6_I2 SHALL **VR-I6-01校验**：I6费用化金额 + I2资本化金额 = 研发总额
5. WHEN VR-I6-01校验失败时, THE 组件 SHALL 红色警告"费用化+资本化≠研发总额，差额xxx"
6. THE Cross_WP_I6_I2 SHALL GtIndexChip支持I6→I2 / I2→I6双向跳转
7. THE Adjudication_I6_1 SHALL 底部显示联动状态面板：费用化(I6)|资本化(I2)|合计|校验状态

### Requirement 5: 截止性测试双向（I6-5/I6-6）

**User Story:** As a 审计助理, I want to 执行研发费用截止测试, so that 我能验证费用归属期间正确。

#### Acceptance Criteria

1. THE Cutoff_Forward_I6_5 SHALL 从账簿→单据（期末±5天）
2. THE Cutoff_Backward_I6_6 SHALL 从单据→账簿（期末±5天）
3. 截止测试 SHALL useCutoffAutoSampling自动提取序时账样本
4. 截止测试 SHALL 显示：日期|金额|费用类型|记账期间|单据日期|归属期间|是否跨期|结论

### Requirement 6: 针对性检查表I6-4

**User Story:** As a 审计助理, I want to 执行针对性检查, so that 我能关注费用归集的合规性。

#### Acceptance Criteria

1. THE Targeted_Check_I6_4 SHALL 段落型检查：费用归集完整性/人员费用分摊合理性/与I2划分一致性
2. THE Targeted_Check_I6_4 SHALL 逐项结论+方法论

### Requirement 7: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 生成研发费用附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市19×7/国企16×6）
2. THE Disclosure SHALL 自动取数（含I2资本化金额）+AI辅助+EventBus

### Requirement 8: 调整分录I6-3

**User Story:** As a 审计助理, I want to 管理调整分录, so that 联动审定表。

#### Acceptance Criteria

1. THE Adjustment_I6_3 SHALL 标准调整分录+借贷平衡+EventBus+导入导出

### Requirement 9: 月度波动分析

**User Story:** As a 审计助理, I want to 分析月度费用波动, so that 我能识别异常月份。

#### Acceptance Criteria

1. THE Adjudication_I6_1 SHALL 对月度变动率超阈值(±30%)的月份黄色高亮
2. THE Detail_I6_2 SHALL 月度趋势图中异常月份红色标记
3. THE AI_Assistant SHALL 对异常月份自动建议审计关注事项

### Requirement 10: 损益类取数规则

**User Story:** As a 开发者, I want to 确保损益类科目正确取数, so that 发生额计算无误。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 损益类取发生额：从tb_ledger汇总borrowing_amount + lending_amount
2. THE Formula_Engine SHALL 6602为借方科目：借方=费用增加，贷方=费用冲回/结转
3. THE writebackTB SHALL 回写发生额而非期末余额（与H10同款）
4. THE 组件 SHALL 明确标注"损益类-取发生额"标识避免混淆
