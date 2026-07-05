# Requirements Document: K5 预计负债底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K预计负债循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(2701) + 或有事项判断联动
- **美观性**：分组配色 + 三级可能性色标 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK5ImportExport
- **AI辅助**：多section AI（诉讼评估/质保测算/弃置费用）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K5预计负债底稿的专属HTML精美组件构建。覆盖来自 `K5 预计负债.xlsx` 的10个有效sheet。科目覆盖2701预计负债（**贷方/负债类**）。

**K5核心特殊**：①**或有事项判断引擎**（CAS13三级可能性：很可能>50%/可能≤50%且>极小/极小可能）②**最佳估计数引擎**（单一最可能金额 或 区间上下限中值/期望值加权）③律师函/未决诉讼检查④产品质量保修测算⑤弃置费用（现值折现）。审定表K5-1（73公式）+ 明细表K5-2（42行）。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K5A**: 预计负债实质性程序表K5A（复用a-program-console）
- **Adjudication_K5_1**: 审定表K5-1，25行12列73公式，负债类2701审定
- **Disclosure_Listed**: 附注披露信息（上市公司），16行12列
- **Disclosure_SOE**: 附注披露信息（国企），31行14列
- **Detail_K5_2**: 明细表K5-2，42行23列，按类型的预计负债明细
- **Adjustment_K5_3**: 调整分录汇总K5-3
- **Warranty_Check_K5_4**: 产品质量保修检查表K5-4
- **Decommission_Check_K5_5**: 弃置费用检查表K5-5
- **Litigation_Check_K5_6**: 未决诉讼检查表K5-6
- **Provision_Check_K5_7**: 预计负债检查表K5-7
- **Contingency_Engine**: 或有事项判断引擎（三级可能性）
- **BestEstimate_Engine**: 最佳估计数引擎（单值/区间中值/期望值加权）
- **Formula_Engine**: 前端公式引擎（负债类）
- **Likelihood_Level**: 可能性级别（很可能/可能/极小可能）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（2701）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K5预计负债按sheetName分发, so that 10个sheet有序组织。

#### Acceptance Criteria

1. THE K5 组件 SHALL 注册componentType: `k5-provisions`，主入口GtK5Provisions.vue
2. THE GtK5Provisions.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K5 组件 SHALL defineAsyncComponent懒加载
4. THE K5 组件 SHALL 子目录：k5/core/（审定/明细/调整/附注） + k5/contingency/（质保/弃置/诉讼/检查）
5. THE K5 组件 SHALL composable分层：useK5FormData + useK5FormulaEngine(纯函数) + useK5ContingencyEngine(纯函数) + useK5BestEstimateEngine(纯函数) + useK5CrossSheet + useK5DualMode + useK5ImportExport
6. THE K5 组件 SHALL htmlRendererRegistry注册'k5-provisions'
7. THE K5 组件 SHALL wp_code_overrides: K5/K5-1~K5-7/K5A → 'k5-provisions'
8. THE K5 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K5 组件 SHALL selfLoad支持
10. THE K5 组件 SHALL checklist_responses存储，前缀"K5-{sheet}-{field}"

### Requirement 2: 审定表K5-1（73公式，负债类！）

**User Story:** As a 审计助理, I want to 在审定表中查看预计负债, so that 我能验证各类预计负债余额正确。

#### Acceptance Criteria

1. THE Adjudication_K5_1 SHALL 按类型分行（产品质量保证/未决诉讼/亏损合同/重组义务/弃置义务/其他）
2. THE Adjudication_K5_1 SHALL 显示：项目|期初|本期增加(计提)|本期减少(转销/冲回)|期末|未审|AJE|RJE|审定数|备注
3. THE Formula_Engine SHALL 计算期末=期初+计提-转销（负债类2701）
4. THE Formula_Engine SHALL 计算审定=未审+AJE+RJE
5. THE Adjudication_K5_1 SHALL 三角勾稽校验+红色高亮
6. THE Adjudication_K5_1 SHALL 与K5-2明细/各专项检查表交叉验证
7. WHEN 审定数变化时 SHALL 回写trial_balance(2701)+发布'substantive:adjudicated'
8. THE Adjudication_K5_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K5-2（23列+或有事项判断）

**User Story:** As a 审计助理, I want to 管理预计负债明细并记录或有事项判断, so that 确认和计量依据可追溯。

#### Acceptance Criteria

1. THE Detail_K5_2 SHALL 将23列拆为3区段Tab：基础(序号/项目/类型/现时义务描述/期初/期末) | 判断(可能性级别/是否确认/确认依据/计量方法) | 估计(最佳估计数/上限/下限/期望值/凭证/结论)
2. THE Contingency_Engine SHALL 根据可能性级别判定是否确认（很可能→确认预计负债；可能→披露或有负债；极小可能→不处理）
3. THE Detail_K5_2 SHALL 对三级可能性用色标（很可能=红/可能=橙/极小可能=灰）
4. THE Detail_K5_2 SHALL 合计行与K5-1审定表交叉验证
5. THE Detail_K5_2 SHALL 动态行新增+导入导出
6. THE Detail_K5_2 SHALL 42行虚拟滚动

### Requirement 4: 或有事项判断引擎（三级可能性）

**User Story:** As a 开发者, I want to 实现或有事项三级可能性判断逻辑, so that 确认/披露/不处理的决策正确。

#### Acceptance Criteria

1. THE Contingency_Engine SHALL 定义三级：'very_likely'(很可能,>50%)/'possible'(可能,≤50%且非极小)/'remote'(极小可能)
2. THE Contingency_Engine SHALL determineRecognition(level): 很可能→'recognize'(确认预计负债)；可能→'disclose'(披露)；极小可能→'ignore'(不处理)
3. WHEN 判定为'recognize'时 SHALL 要求填写最佳估计数
4. WHEN 判定为'disclose'时 SHALL 标记进入附注或有负债披露

### Requirement 5: 最佳估计数引擎

**User Story:** As a 审计助理, I want to 测算最佳估计数, so that 计量金额符合CAS13。

#### Acceptance Criteria

1. THE BestEstimate_Engine SHALL 单一事项：最佳估计数=最可能发生金额
2. THE BestEstimate_Engine SHALL 连续区间：最佳估计数=(上限+下限)/2（区间中值）
3. THE BestEstimate_Engine SHALL 多情形：最佳估计数=Σ(各情形金额×概率)（期望值加权）
4. THE BestEstimate_Engine SHALL 涉及时间价值重大时按现值折现
5. THE Detail_K5_2 SHALL 显示所选计量方法及测算结果

### Requirement 6: 产品质量保修检查表K5-4

**User Story:** As a 审计助理, I want to 测算产品质量保修准备, so that 质保计提合理。

#### Acceptance Criteria

1. THE Warranty_Check_K5_4 SHALL 显示：产品/销售收入/历史保修率/预计保修支出(公式)/期初/本期计提/本期使用/期末/结论
2. THE Warranty_Check_K5_4 SHALL 计算预计保修支出=销售收入×历史保修率
3. THE Warranty_Check_K5_4 SHALL 与K5-1产品质量保证行交叉验证
4. THE Warranty_Check_K5_4 SHALL AI辅助生成结论

### Requirement 7: 弃置费用检查表K5-5

**User Story:** As a 审计助理, I want to 检查弃置费用, so that 弃置义务现值计量正确。

#### Acceptance Criteria

1. THE Decommission_Check_K5_5 SHALL 显示：资产/预计弃置支出/预计弃置时间/折现率/现值(公式)/期初/本期增加/利息调整/期末/结论
2. THE Decommission_Check_K5_5 SHALL 计算现值=预计弃置支出/(1+折现率)^年数
3. THE Decommission_Check_K5_5 SHALL 计算本期利息调整=期初现值×折现率
4. THE Decommission_Check_K5_5 SHALL 与K5-1弃置义务行交叉验证

### Requirement 8: 未决诉讼检查表K5-6 + 预计负债检查表K5-7

**User Story:** As a 审计助理, I want to 完成诉讼和综合检查, so that 或有事项充分识别。

#### Acceptance Criteria

1. THE Litigation_Check_K5_6 SHALL 显示：案件/涉案金额/诉讼阶段/律师意见/败诉可能性/预计损失/是否确认/披露
2. THE Litigation_Check_K5_6 SHALL 联动律师函证据+可能性级别判断
3. THE Provision_Check_K5_7 SHALL 综合检查表，逐项"合规/不合规/不适用"判断
4. THE 检查表组 SHALL 支持行级抽凭+行级OCR（律师函/评估报告）
5. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 9: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市16×12/国企31×14）+或有事项披露段+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K5_3 SHALL 借贷平衡+双向同步K5-1+publish 'adjustment:created'→A13+导入导出

### Requirement 10: 公式引擎与专项引擎（纯函数）

**User Story:** As a 开发者, I want to 实现公式与专项纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, provision, release): 期末=期初+计提-转销
3. THE Contingency_Engine SHALL determineRecognition(level): 确认/披露/不处理
4. THE BestEstimate_Engine SHALL calcRangeMidpoint(upper, lower): 区间中值=(上限+下限)/2
5. THE BestEstimate_Engine SHALL calcExpectedValue(amounts, probs): 期望值=Σ(金额×概率)
6. THE Warranty_Check SHALL calcWarrantyProvision(revenue, rate): 保修支出=收入×保修率
7. THE Decommission_Check SHALL calcPresentValue(future, rate, years): 现值=future/(1+rate)^years
8. THE Formula_Engine SHALL calcSubtotal(arr): 合计
