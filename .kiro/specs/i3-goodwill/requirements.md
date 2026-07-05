# Requirements Document: I3 商誉底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写 + 附注
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + DCF参数引导 + 编制提示
- **导入导出**：el-dropdown三级 + useI3ImportExport
- **AI辅助**：DCF参数建议 + 减值结论生成
- **双模式**：el-segmented + OO降级

## Introduction

I3商誉底稿的专属HTML精美组件构建。覆盖来自 `I3 商誉.xlsx` 的15个有效sheet（含1个历史遗留sheet已被regex skip）。科目1711商誉（借方/资产类）。

**I3核心特殊**：①**商誉不摊销！**仅年度减值测试 ②期末=期初-减值（只减不增，无摊销，无新增商誉除非新并购）③DCF资产组(CGU)模型是核心 ④不可单独识别现金流→必须按资产组分摊 ⑤减值先冲商誉再分摊至资产组其他资产 ⑥可收回金额测试100×16超大表 ⑦复核公司减值测试过程153行。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_I3A**: 商誉实质性程序表I3A
- **Adjudication_I3_1**: 审定表I3-1，56行13列66公式
- **Disclosure_Listed**: 附注上市公司，41行8列38公式
- **Disclosure_SOE**: 附注国企，31行7列31公式
- **Detail_I3_2**: 明细表I3-2，29行30列12公式
- **Adjustment_I3_3**: 调整分录汇总I3-3
- **InitialValue_I3_4**: 入账价值测算表I3-4，22行13列12公式
- **Targeted_Check_I3_5**: 针对性检查表I3-5
- **Impairment_Test_I3_6**: 商誉减值测试I3-6，70行12列
- **Recoverable_Test_I3_7**: 可收回金额测试I3-7，100行16列22公式 — **DCF核心超大表**
- **Review_Process_I3_8**: 复核公司减值测试过程及结论I3-8，153行12列
- **CGU**: 资产组（Cash Generating Unit），商誉减值测试的最小单元
- **DCF_Model**: 折现现金流模型（Discounted Cash Flow）
- **Goodwill_Rule**: 商誉特殊规则：不摊销+仅减值+先冲商誉+不可转回

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I3商誉底稿按sheetName分发, so that 15个sheet有序组织。

#### Acceptance Criteria

1. THE I3 组件 SHALL 注册componentType: `i3-goodwill`，主入口GtI3Goodwill.vue
2. THE GtI3Goodwill.vue SHALL 接收sheetName prop，v-if分发
3. THE I3 组件 SHALL defineAsyncComponent懒加载
4. THE I3 组件 SHALL 子目录：i3/core/、i3/impairment/
5. THE I3 组件 SHALL composable分层：useI3FormData + useI3FormulaEngine + useI3DcfEngine(纯函数) + useI3CrossSheet + useI3DualMode + useI3ImportExport
6. THE I3 组件 SHALL htmlRendererRegistry注册'i3-goodwill'
7. THE I3 组件 SHALL wp_code_overrides: I3/I3-1~I3-8/I3A → 'i3-goodwill'
8. THE I3 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE I3 组件 SHALL selfLoad支持
10. THE I3 组件 SHALL checklist_responses存储，前缀"I3-{sheet}-{field}"

### Requirement 2: 审定表I3-1（商誉不摊销！66公式）

**User Story:** As a 审计助理, I want to 在审定表中查看商誉审定数据, so that 我能验证商誉仅发生减值变动。

#### Acceptance Criteria

1. THE Adjudication_I3_1 SHALL 显示：被投资单位|初始确认|期初余额|本期增加(新并购)|本期减少(减值)|期末余额|未审|AJE|RJE|审定数|减值准备|净额
2. THE Formula_Engine SHALL **商誉不摊销**！期末=期初+增加(新并购)-减少(减值)
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_I3_1 SHALL "本期增加"仅来自新并购（正常情况为0），非零时黄色提示
5. THE Adjudication_I3_1 SHALL "本期减少"仅来自减值（商誉减值不可转回！）
6. THE Adjudication_I3_1 SHALL 净额=商誉原值-累计减值
7. THE Adjudication_I3_1 SHALL TB取数+差异+writebackTB(1711)
8. THE Adjudication_I3_1 SHALL 审计说明+结论+复核对话

### Requirement 3: 明细表I3-2（30列）

**User Story:** As a 审计助理, I want to 查看商誉明细, so that 我能追踪每笔商誉的来源和减值情况。

#### Acceptance Criteria

1. THE Detail_I3_2 SHALL 将30列拆为3区段Tab：基础(被投资单位/并购日期/对价/被购方净资产) | 入账(合并成本/可辨认净资产公允/商誉原值) | 减值(累计减值/本期减值/期末净额)
2. THE Detail_I3_2 SHALL 商誉原值=合并成本-可辨认净资产公允价值（12公式）
3. THE Detail_I3_2 SHALL 合计行联动审定表
4. THE Detail_I3_2 SHALL 动态行（弹ElMessageBox输入被投资单位名称）

### Requirement 4: 入账价值测算表I3-4

**User Story:** As a 审计助理, I want to 测算商誉入账价值, so that 我能验证初始确认金额正确。

#### Acceptance Criteria

1. THE InitialValue_I3_4 SHALL 显示：合并成本(对价+或有对价+交易费用) - 可辨认净资产公允价值 = 商誉
2. THE Formula_Engine SHALL 商誉=合并成本-被购方可辨认净资产公允价值份额
3. THE InitialValue_I3_4 SHALL 12公式全覆盖

### Requirement 5: 商誉减值测试I3-6

**User Story:** As a 审计助理, I want to 对商誉执行年度减值测试, so that 我能确定是否需计提减值。

#### Acceptance Criteria

1. THE Impairment_Test_I3_6 SHALL 按资产组(CGU)逐行显示：CGU名称|包含商誉|资产组账面(含商誉)|可收回金额|减值金额|商誉分摊|其他资产分摊
2. THE Formula_Engine SHALL 减值=MAX(资产组账面-可收回金额, 0)
3. THE Formula_Engine SHALL 减值分摊规则：**先冲商誉**（至零为止），剩余按比例分摊至资产组其他资产
4. THE Impairment_Test_I3_6 SHALL 商誉减值不可转回（不允许负数减值）
5. THE Impairment_Test_I3_6 SHALL 可收回金额列链接I3-7 DCF测试

### Requirement 6: 可收回金额测试I3-7（DCF核心，100×16超大表）

**User Story:** As a 审计助理, I want to 通过DCF测算资产组可收回金额, so that 我能确定商誉减值金额。

#### Acceptance Criteria

1. THE Recoverable_Test_I3_7 SHALL 显示完整DCF模型：收入预测(5年) + 成本预测 + 自由现金流 + 折现率(WACC) + 终值 + 现值合计
2. THE DCF_Model SHALL 计算：PV=Σ(FCF_i/(1+WACC)^i) + TV/(1+WACC)^n
3. THE DCF_Model SHALL 终值=FCF_n×(1+g)/(WACC-g)（永续增长模型）
4. THE Recoverable_Test_I3_7 SHALL 可收回金额=MAX(公允价值-处置费用, 使用价值DCF)
5. THE Recoverable_Test_I3_7 SHALL 敏感性分析：WACC±1%/增长率±0.5%/收入±10%
6. THE Recoverable_Test_I3_7 SHALL 支持虚拟滚动（100行大表）
7. THE Recoverable_Test_I3_7 SHALL AI辅助：根据行业数据建议折现率和增长率

### Requirement 7: 复核公司减值测试过程I3-8（153行）

**User Story:** As a 审计助理, I want to 复核被审计单位自身的减值测试, so that 我能评估其测试过程和结论的合理性。

#### Acceptance Criteria

1. THE Review_Process_I3_8 SHALL 按章节展示：假设审阅|模型检查|参数合理性|计算验证|结论评价
2. THE Review_Process_I3_8 SHALL 153行12列超大段落型检查（虚拟滚动）
3. THE Review_Process_I3_8 SHALL 逐项结论(合理/不合理/需调整)+证据描述
4. THE Review_Process_I3_8 SHALL AI辅助：自动标注常见问题

### Requirement 8: 针对性检查表I3-5

**User Story:** As a 审计助理, I want to 执行针对性检查, so that 我能关注商誉特定风险。

#### Acceptance Criteria

1. THE Targeted_Check_I3_5 SHALL 段落型检查：减值迹象识别/商誉分摊合理性/CGU划分一致性
2. THE Targeted_Check_I3_5 SHALL 逐项结论+琥珀色方法论

### Requirement 9: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 生成商誉附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市41×8/国企31×7）
2. THE Disclosure SHALL 从审定表+减值测试自动取数
3. THE Disclosure SHALL AI辅助+EventBus附注联动

### Requirement 10: 调整分录I3-3

**User Story:** As a 审计助理, I want to 管理商誉调整分录, so that 减值调整能联动审定表。

#### Acceptance Criteria

1. THE Adjustment_I3_3 SHALL 标准调整分录表+借贷平衡
2. THE Adjustment_I3_3 SHALL EventBus联动审定表+A13
3. THE Adjustment_I3_3 SHALL 导入导出三级
