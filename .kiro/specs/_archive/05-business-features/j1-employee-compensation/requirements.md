# Requirements Document: J1 应付职工薪酬底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/J应付职工薪酬循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(**负债类贷方！**) + K8/K9费用分摊联动 + 附注
- **美观性**：分组配色 + 月度趋势图 + 进度条 + 5类检查表独立配色
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useJ1ImportExport
- **AI辅助**：多section AI（审计说明+异常分析）
- **双模式**：el-segmented + OO降级
- **月度分析**：12列横向（类D4-2/I6-2月度矩阵）
- **5类检查表**：计提/分配/一般/非货币福利/辞退 独立组件

## Introduction

J1应付职工薪酬底稿的专属HTML精美组件构建。覆盖来自 `J1 应付职工薪酬.xlsx` 的16个有效sheet。科目2211应付职工薪酬（**贷方/负债类！**期末=期初+贷方-借方，与H9同款处理）。

**J1核心特殊**：①**负债类贷方科目！**期末=期初+贷方发生-借方发生（与资产类相反！与H9同款）②月度分析表12列横向（类D4-2/I6-2）③**5类检查表**（计提/分配/一般/非货币福利/辞退）④工资测算公式（人数×均薪×月份）⑤社保测算（基数×比例）⑥联动K8/K9费用分摊。关键公式总数约110+（审定表57公式+月度20+其他）。

## Glossary

- **Tab_Index**: 底稿目录，19行7列
- **Procedure_Table_J1A**: 应付职工薪酬实质性程序表J1A，48行11列
- **Adjudication_J1_1**: 审定表J1-1，50行13列**57公式**（负债类贷方！）
- **Disclosure_Listed**: 附注上市公司，54行5列22公式
- **Disclosure_SOE**: 附注国企，44行5列19公式
- **Detail_J1_2**: 明细表J1-2，67行14列7公式
- **Adjustment_J1_3**: 调整分录汇总J1-3，24行10列
- **Monthly_Analysis_J1_4**: 月度分析表J1-4，61行16列**20公式**（12列横向）
- **Industry_Compare_J1_5**: 与同行业对比分析表J1-5，71行13列7公式
- **Accrual_Check_J1_6**: 计提情况检查表J1-6，60行11列
- **Allocation_Check_J1_7**: 分配情况检查表J1-7，48行13列
- **General_Check_J1_8**: 检查表J1-8，58行16列
- **NonMonetary_Check_J1_9**: 非货币性福利检查表J1-9，29行13列
- **Severance_Check_J1_10**: 辞退福利检查表J1-10，48行10列
- **Liability_Formula**: 负债类公式：期末=期初+贷方-借方（与资产类相反！）
- **Monthly_Matrix**: 月度12列横向矩阵（1月~12月）
- **Salary_Calc**: 工资测算：人数×均薪×月份
- **Social_Insurance_Calc**: 社保测算：基数×比例
- **Cross_WP_K8K9**: 联动K8管理费用/K9销售费用（薪酬费用分摊）
- **Five_Check_Tables**: 5类检查表体系（J1-6~J1-10）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to J1应付职工薪酬按sheetName分发, so that 16个sheet有序组织。

#### Acceptance Criteria

1. THE J1 组件 SHALL 注册componentType: `j1-employee-compensation`，主入口GtJ1EmployeeCompensation.vue
2. THE GtJ1EmployeeCompensation.vue SHALL 接收sheetName prop，v-if分发
3. THE J1 组件 SHALL defineAsyncComponent懒加载
4. THE J1 组件 SHALL 子目录：j1/core/（审定+明细+调整+附注）、j1/analysis/（月度+行业对比）、j1/inspection/（5类检查表）
5. THE J1 组件 SHALL composable分层：useJ1FormData + useJ1FormulaEngine(**负债类！**) + useJ1CrossSheet + useJ1DualMode + useJ1ImportExport + useJ1SalaryCalc
6. THE J1 组件 SHALL htmlRendererRegistry注册'j1-employee-compensation'
7. THE J1 组件 SHALL wp_code_overrides: J1/J1-1~J1-10/J1A → 'j1-employee-compensation'
8. THE J1 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE J1 组件 SHALL selfLoad支持
10. THE J1 组件 SHALL checklist_responses存储，前缀"J1-{sheet}-{field}"

### Requirement 2: 审定表J1-1（负债类贷方科目！57公式）

**User Story:** As a 审计助理, I want to 在审定表中查看应付职工薪酬科目余额, so that 我能验证负债类期末余额正确。

#### Acceptance Criteria

1. THE Adjudication_J1_1 SHALL 显示列：项目|期初|贷方发生(计提增加)|借方发生(发放减少)|期末|未审|AJE|RJE|审定数|同期|变动率|变动额|备注
2. THE Formula_Engine SHALL **负债类！**期末=期初+贷方-借方（2211贷方=计提增加，借方=发放减少）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_J1_1 SHALL 按薪酬类别分组：短期薪酬(工资/奖金/津贴/社保/公积金/福利费) + 离职后福利 + 辞退福利 + 其他
5. THE Adjudication_J1_1 SHALL 变动率=(本期-同期)/同期×100%
6. THE Adjudication_J1_1 SHALL TB取数+差异+writebackTB(**期末余额**，科目2211)
7. THE Adjudication_J1_1 SHALL 审计说明+结论+复核对话
8. THE Adjudication_J1_1 SHALL 与J1-2明细合计交叉验证

### Requirement 3: 明细表J1-2（67行14列）

**User Story:** As a 审计助理, I want to 查看薪酬明细, so that 我能按类别追踪各项薪酬变动。

#### Acceptance Criteria

1. THE Detail_J1_2 SHALL 显示：薪酬类别|部门|期初|本期计提|本期发放|期末|占比|备注
2. THE Formula_Engine SHALL 期末=期初+计提-发放（贷方逻辑）
3. THE Detail_J1_2 SHALL 底部合计行=各列SUM
4. THE Detail_J1_2 SHALL 合计行联动审定表期末余额
5. THE Detail_J1_2 SHALL 动态行+导入导出
6. THE Detail_J1_2 SHALL 占比=各项/合计×100%

### Requirement 4: 月度分析表J1-4（12列横向，20公式）

**User Story:** As a 审计助理, I want to 分析薪酬月度变动, so that 我能识别异常月份的薪酬波动。

#### Acceptance Criteria

1. THE Monthly_Analysis_J1_4 SHALL 61行16列拆为：固定列(薪酬项目/员工人数) + 12月份列(1月~12月各月金额) + 合计列 + 均值列
2. THE Monthly_Analysis_J1_4 SHALL 固定前2列，12月份列横向滚动
3. THE Formula_Engine SHALL 合计列=SUM(1月~12月)
4. THE Formula_Engine SHALL 均值=合计/12
5. THE Monthly_Analysis_J1_4 SHALL 月度趋势折线图（顶部可折叠）
6. THE Monthly_Analysis_J1_4 SHALL 工资测算公式：月薪酬≈人数×均薪
7. THE Monthly_Analysis_J1_4 SHALL 对月度变动率超阈值(±30%)的月份黄色高亮
8. THE Monthly_Analysis_J1_4 SHALL 动态行+导入导出

### Requirement 5: 与同行业对比分析表J1-5（71行13列）

**User Story:** As a 审计助理, I want to 与同行业薪酬对比, so that 我能评价薪酬水平合理性。

#### Acceptance Criteria

1. THE Industry_Compare_J1_5 SHALL 显示：公司名|行业|人均薪酬|薪酬总额|人数|薪酬占收入比|变动率
2. THE Formula_Engine SHALL 人均薪酬=薪酬总额/人数
3. THE Formula_Engine SHALL 薪酬占收入比=薪酬总额/营业收入×100%
4. THE Industry_Compare_J1_5 SHALL 差异率=(被审计单位-行业平均)/行业平均×100%
5. THE Industry_Compare_J1_5 SHALL 显示同行业区间(最大/最小/中位数/均值)
6. WHEN 差异率>20%时 SHALL 黄色高亮+审计关注提示
7. THE Industry_Compare_J1_5 SHALL 动态行+导入导出

### Requirement 6: 计提情况检查表J1-6（60行11列）

**User Story:** As a 审计助理, I want to 检查薪酬计提是否正确, so that 我能验证计提金额的准确性。

#### Acceptance Criteria

1. THE Accrual_Check_J1_6 SHALL 段落型检查含：工资计提(人数×均薪×月份) + 社保计提(基数×比例) + 公积金计提 + 年终奖预提
2. THE Formula_Engine SHALL 工资测算=人数×月均薪酬×计提月数
3. THE Formula_Engine SHALL 社保测算=缴费基数×缴费比例×月数
4. THE Accrual_Check_J1_6 SHALL 逐项结论 + 差异分析
5. THE Accrual_Check_J1_6 SHALL 计提差异率=(实际计提-测算金额)/测算金额×100%
6. WHEN 计提差异率>5%时 SHALL 红色高亮

### Requirement 7: 分配情况检查表J1-7（48行13列）

**User Story:** As a 审计助理, I want to 检查薪酬费用分配, so that 我能验证薪酬正确归集到各成本/费用科目。

#### Acceptance Criteria

1. THE Allocation_Check_J1_7 SHALL 显示：部门|人数|薪酬金额|分配科目(生产成本/制造费用/管理费用/销售费用/研发费用)|分配比例
2. THE Formula_Engine SHALL 分配比例=各科目金额/薪酬总额×100%
3. THE Allocation_Check_J1_7 SHALL 分配合计=薪酬总额（闭合校验）
4. THE Allocation_Check_J1_7 SHALL 联动K8管理费用/K9销售费用中薪酬部分
5. WHEN 分配合计≠薪酬总额时 SHALL 红色警告"分配不平"

### Requirement 8: 检查表J1-8（一般检查，58行16列）

**User Story:** As a 审计助理, I want to 执行一般性检查, so that 我能完成薪酬科目标准检查程序。

#### Acceptance Criteria

1. THE General_Check_J1_8 SHALL 段落型检查含：工资单核对/银行流水核对/个税代扣核对/社保核对/异常支付检查
2. THE General_Check_J1_8 SHALL 逐项结论+方法论上下文
3. THE General_Check_J1_8 SHALL 行级OCR支持（工资单/银行回单附件）
4. THE General_Check_J1_8 SHALL AI辅助审计说明

### Requirement 9: 非货币性福利检查表J1-9（29行13列）

**User Story:** As a 审计助理, I want to 检查非货币性福利, so that 我能验证实物/服务福利的计量和披露。

#### Acceptance Criteria

1. THE NonMonetary_Check_J1_9 SHALL 显示：福利项目|受益对象|计量方式|公允价值|账面价值|差异|税务处理|结论
2. THE NonMonetary_Check_J1_9 SHALL 非货币福利类型分类：自产产品/外购商品/自有房产/租赁房产/其他
3. THE Formula_Engine SHALL 差异=公允价值-账面价值
4. THE NonMonetary_Check_J1_9 SHALL 逐项结论

### Requirement 10: 辞退福利检查表J1-10（48行10列）

**User Story:** As a 审计助理, I want to 检查辞退福利, so that 我能验证辞退福利的确认和计量符合CAS9。

#### Acceptance Criteria

1. THE Severance_Check_J1_10 SHALL 显示：员工/部门|辞退日期|补偿标准|补偿金额|是否满足确认条件|实际支付|余额
2. THE Severance_Check_J1_10 SHALL CAS9确认条件检查：正式计划+无法单方撤回
3. THE Formula_Engine SHALL 余额=补偿金额-实际支付
4. THE Severance_Check_J1_10 SHALL 逐项结论+方法论

### Requirement 11: 附注披露（上市54×5 + 国企44×5）

**User Story:** As a 审计助理, I want to 生成薪酬附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市54×5/22公式 + 国企44×5/19公式）
2. THE Disclosure SHALL 自动取数（审定表各分类金额）+ AI辅助 + EventBus
3. THE Disclosure SHALL 按CAS9/CAS10分类披露：短期薪酬/离职后福利/辞退福利/其他

### Requirement 12: 调整分录J1-3 + 跨底稿联动

**User Story:** As a 审计助理, I want to 管理调整分录并联动费用科目, so that 薪酬调整同步反映到相关费用底稿。

#### Acceptance Criteria

1. THE Adjustment_J1_3 SHALL 标准调整分录24行10列+借贷平衡+EventBus
2. THE Cross_WP_K8K9 SHALL EventBus publish 'compensation:adjusted'（J1保存时）
3. THE Cross_WP_K8K9 SHALL GtIndexChip支持J1→K8/K9跳转
4. THE Cross_WP_K8K9 SHALL 分配表J1-7与K8/K9交叉验证
