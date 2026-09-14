# Requirements Document: I5 其他非流动资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写
- **美观性**：分组配色 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：编制提示
- **导入导出**：el-dropdown三级 + useI5ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

## Introduction

I5其他非流动资产底稿的专属HTML精美组件构建。覆盖来自 `I5 其他非流动资产.xlsx` 的9个有效sheet。科目1911其他非流动资产（借方/资产类）。

**I5特点**：最简单标准底稿（9 sheets），无特殊逻辑。标准资产类三角勾稽+审定表+明细表+检查表模式。关键公式总数约80+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_I5A**: 其他非流动资产实质性程序表I5A
- **Adjudication_I5_1**: 审定表I5-1，89行11列61公式
- **Disclosure_Listed**: 附注上市公司，20行7列41公式
- **Disclosure_SOE**: 附注国企，20行5列23公式
- **Detail_I5_2**: 明细表I5-2，63行26列16公式
- **Adjustment_I5_3**: 调整分录汇总I5-3
- **Targeted_Check_I5_4**: 针对性检查表I5-4

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I5其他非流动资产按sheetName分发, so that 9个sheet有序组织。

#### Acceptance Criteria

1. THE I5 组件 SHALL 注册componentType: `i5-other-noncurrent-assets`，主入口GtI5OtherNoncurrentAssets.vue
2. THE GtI5OtherNoncurrentAssets.vue SHALL 接收sheetName prop，v-if分发
3. THE I5 组件 SHALL defineAsyncComponent懒加载
4. THE I5 组件 SHALL 子目录：i5/core/
5. THE I5 组件 SHALL composable分层：useI5FormData + useI5FormulaEngine + useI5CrossSheet + useI5DualMode + useI5ImportExport
6. THE I5 组件 SHALL htmlRendererRegistry注册'i5-other-noncurrent-assets'
7. THE I5 组件 SHALL wp_code_overrides: I5/I5-1~I5-4/I5A → 'i5-other-noncurrent-assets'
8. THE I5 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE I5 组件 SHALL selfLoad支持
10. THE I5 组件 SHALL checklist_responses存储，前缀"I5-{sheet}-{field}"

### Requirement 2: 审定表I5-1（61公式）

**User Story:** As a 审计助理, I want to 在审定表中查看其他非流动资产, so that 我能验证各项余额正确。

#### Acceptance Criteria

1. THE Adjudication_I5_1 SHALL 显示：项目|期初|本期增加|本期减少|期末|未审|AJE|RJE|审定数|变动率|备注
2. THE Formula_Engine SHALL 期末=期初+增加-减少（资产类借方1911）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_I5_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_I5_1 SHALL TB取数+差异+writebackTB(1911)
6. THE Adjudication_I5_1 SHALL 审计说明+结论+复核对话
7. THE Adjudication_I5_1 SHALL 89行支持虚拟滚动

### Requirement 3: 明细表I5-2（26列）

**User Story:** As a 审计助理, I want to 管理其他非流动资产明细, so that 我能逐项追踪。

#### Acceptance Criteria

1. THE Detail_I5_2 SHALL 26列拆为3区段Tab：基础(名称/类型/发生日/到期日) | 金额(期初/增加/减少/期末) | 检查(凭证号/备注/结论)
2. THE Detail_I5_2 SHALL 合计行联动审定表
3. THE Detail_I5_2 SHALL 动态行+导入导出
4. THE Detail_I5_2 SHALL 63行支持虚拟滚动

### Requirement 4: 针对性检查表I5-4

**User Story:** As a 审计助理, I want to 执行针对性检查, so that 我能关注分类正确性和可回收性。

#### Acceptance Criteria

1. THE Targeted_Check_I5_4 SHALL 检查：分类正确性(应否归入其他科目)/期限适当性(是否仍为非流动)/可回收性评估
2. THE Targeted_Check_I5_4 SHALL 逐项结论+琥珀色方法论

### Requirement 5: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 生成附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市20×7/国企20×5）
2. THE Disclosure SHALL 自动取数+AI辅助+EventBus

### Requirement 6: 调整分录I5-3

**User Story:** As a 审计助理, I want to 管理调整分录, so that 联动审定表。

#### Acceptance Criteria

1. THE Adjustment_I5_3 SHALL 标准调整分录+借贷平衡+EventBus+导入导出
