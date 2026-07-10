# Requirements Document: I4 长期待摊费用底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写 + 摊销分摊联动
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 摊销方法选择引导 + 编制提示
- **导入导出**：el-dropdown三级 + useI4ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

## Introduction

I4长期待摊费用底稿的专属HTML精美组件构建。覆盖来自 `I4 长期待摊费用.xlsx` 的12个有效sheet。科目1801长期待摊费用（借方/资产类）。

**I4核心特殊**：①摊销2种方法（直线法I4-6 + 工作量法I4-7），分支选择器 ②标准资产类三角勾稽 ③摊销引擎是H循环折旧引擎的子集（仅直线+工作量2种）。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_I4A**: 长期待摊费用实质性程序表I4A
- **Adjudication_I4_1**: 审定表I4-1，47行9列47公式
- **Disclosure_Listed**: 附注上市公司，14行13列42公式
- **Disclosure_SOE**: 附注国企，16行12列47公式
- **Detail_I4_2**: 明细表I4-2，53行25列18公式
- **Adjustment_I4_3**: 调整分录汇总I4-3
- **Policy_Check_I4_4**: 摊销政策检查表I4-4
- **Targeted_Check_I4_5**: 针对性检查表I4-5
- **Amortization_Straight_I4_6**: 摊销测算I4-6直线法，65行28列39公式
- **Amortization_Units_I4_7**: 摊销测算表I4-7工作量法，65行28列21公式
- **Branch_Selector**: 分支选择器，I4-6/I4-7两版本切换（直线法/工作量法）
- **Amortization_Engine**: 摊销计算引擎（直线法+工作量法，H折旧引擎子集）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I4长期待摊费用按sheetName分发, so that 12个sheet有序组织。

#### Acceptance Criteria

1. THE I4 组件 SHALL 注册componentType: `i4-long-term-prepaid`，主入口GtI4LongTermPrepaid.vue
2. THE GtI4LongTermPrepaid.vue SHALL 接收sheetName prop，v-if分发
3. THE I4 组件 SHALL defineAsyncComponent懒加载
4. THE I4 组件 SHALL 子目录：i4/core/、i4/amortization/
5. THE I4 组件 SHALL composable分层：useI4FormData + useI4FormulaEngine + useI4AmortizationEngine(纯函数) + useI4CrossSheet + useI4DualMode + useI4ImportExport
6. THE I4 组件 SHALL htmlRendererRegistry注册'i4-long-term-prepaid'
7. THE I4 组件 SHALL wp_code_overrides: I4/I4-1~I4-7/I4A → 'i4-long-term-prepaid'
8. THE I4 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE I4 组件 SHALL selfLoad支持
10. THE I4 组件 SHALL checklist_responses存储，前缀"I4-{sheet}-{field}"

### Requirement 2: 审定表I4-1（47公式）

**User Story:** As a 审计助理, I want to 在审定表中查看长期待摊费用, so that 我能验证摊销正确性。

#### Acceptance Criteria

1. THE Adjudication_I4_1 SHALL 显示：项目|期初|本期增加|本期摊销|本期减少|期末|未审|AJE|RJE|审定数
2. THE Formula_Engine SHALL 期末=期初+增加-摊销-减少（资产类借方1801）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_I4_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_I4_1 SHALL TB取数+差异+writebackTB(1801)
6. THE Adjudication_I4_1 SHALL 审计说明+结论+复核对话

### Requirement 3: 明细表I4-2（25列）

**User Story:** As a 审计助理, I want to 管理长期待摊费用明细, so that 我能逐项追踪摊销情况。

#### Acceptance Criteria

1. THE Detail_I4_2 SHALL 显示25列拆为3区段Tab：基础(项目名/发生日/类型/原始金额) | 摊销(摊销方法/期限/已摊月数/累计摊销/本期摊销) | 余额(期初/变动/期末/剩余月数)
2. THE Detail_I4_2 SHALL 合计行联动审定表
3. THE Detail_I4_2 SHALL 动态行+导入导出

### Requirement 4: 摊销政策检查I4-4

**User Story:** As a 审计助理, I want to 检查长期待摊费用摊销政策, so that 我能验证政策适当性。

#### Acceptance Criteria

1. THE Policy_Check_I4_4 SHALL 段落型检查：摊销方法/受益期估计/变更处理
2. THE Policy_Check_I4_4 SHALL 琥珀色方法论+引导区

### Requirement 5: 针对性检查表I4-5

**User Story:** As a 审计助理, I want to 执行针对性检查, so that 我能关注特定风险。

#### Acceptance Criteria

1. THE Targeted_Check_I4_5 SHALL 段落型：大额新增核查/受益期变更/提前终止处理
2. THE Targeted_Check_I4_5 SHALL 逐项结论

### Requirement 6: 摊销测算分支选择器（I4-6/I4-7）

**User Story:** As a 审计助理, I want to 在直线法和工作量法间切换, so that 我能选择正确的摊销方法测算。

#### Acceptance Criteria

1. THE Branch_Selector SHALL el-segmented切换："直线法（I4-6）" / "工作量法（I4-7）"
2. WHEN 选择"直线法"时, THE 组件 SHALL 渲染I4TabAmortizationStraight.vue（39公式）
3. WHEN 选择"工作量法"时, THE 组件 SHALL 渲染I4TabAmortizationUnits.vue（21公式）
4. THE Amortization_Engine SHALL 直线法：月摊销=原始金额÷摊销总月数
5. THE Amortization_Engine SHALL 工作量法：月摊销=原始金额×(本月工作量÷总预计工作量)
6. THE 摊销测算表 SHALL 横向12月矩阵（28列）+ 底部合计

### Requirement 7: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 生成附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市14×13/国企16×12）
2. THE Disclosure SHALL 自动取数+AI辅助+EventBus

### Requirement 8: 调整分录I4-3

**User Story:** As a 审计助理, I want to 管理调整分录, so that 联动审定表。

#### Acceptance Criteria

1. THE Adjustment_I4_3 SHALL 标准调整分录+借贷平衡+EventBus+导入导出
