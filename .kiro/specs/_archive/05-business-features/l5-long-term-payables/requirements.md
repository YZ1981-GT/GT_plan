# Requirements Document: L5 长期应付款底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + 未确认融资费用摊销→L8财务费用 + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL5ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L5长期应付款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l5-long-term-payables`，覆盖来自 `L5 长期应付款.xlsx` 的9个有效sheet。科目覆盖2701长期应付款（**贷方/负债类！**）+ 未确认融资费用（借方/负债备抵类）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L5核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方）②**未确认融资费用摊销**（实际利率法，与H9同款：每期摊销=期初摊余成本×实际利率）③长期应付款净额=长期应付款-未确认融资费用④关联方及交易检查。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L5A**: 长期应付款实质性程序表L5A（复用a-program-console）
- **Adjudication_L5_1**: 审定表L5-1，35×16，63公式，科目2701长期应付款(贷方/负债)+未确认融资费用(借方/备抵)
- **Disclosure_Listed**: 附注披露信息（上市公司），22×15
- **Disclosure_SOE**: 附注披露信息（国有企业），20×15
- **Detail_L5_2**: 明细表L5-2，35×30，26公式，按款项列示
- **Unrecognized_Detail_L5_3**: 未确认融资费用明细表L5-3，31×30，21公式
- **Adjustment_L5_4**: 调整分录L5-4
- **Amortization_L5_5**: 未确认融资费用测算表L5-5，26×17，9公式（核心！实际利率法摊销）
- **RelatedParty_Check_L5_6**: 关联方及交易检查表L5-6
- **LTPayable_Check_L5_7**: 长期应付款检查表L5-7
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Amortization_Engine**: 未确认融资费用摊销引擎（实际利率法，核心纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目2701+未确认融资费用）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L5长期应付款底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L5 组件 SHALL 注册新componentType: `l5-long-term-payables`，主入口为 GtL5LongTermPayables.vue
2. THE GtL5LongTermPayables.vue SHALL 接收 `sheetName` prop，正则提取编码(L5-1)，v-if分发
3. THE L5 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L5 组件 SHALL 拆为：l5/core/（审定+明细+未确认明细+调整+附注）、l5/amortization/（摊销测算）、l5/inspection/（关联方+检查表）
5. THE L5 组件 SHALL composable分层：useL5FormData + useL5FormulaEngine + useL5AmortizationEngine(纯函数) + useL5CrossSheet + useL5DualMode + useL5ImportExport
6. THE L5 组件 SHALL 在htmlRendererRegistry中注册'l5-long-term-payables'
7. THE L5 组件 SHALL 在wp_code_overrides.json中将L5/L5-1~L5-7/L5A映射为'l5-long-term-payables'
8. THE L5 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l5-long-term-payables'
9. THE GtL5LongTermPayables.vue SHALL 支持selfLoad
10. THE L5 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L5-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L5-1（负债类贷方+未确认融资费用备抵）

**User Story:** As a 审计助理, I want to 在精美审定表中查看长期应付款数据, so that 我能验证负债净额。

#### Acceptance Criteria

1. THE Adjudication_L5_1 SHALL 渲染为双区块：一、长期应付款(贷方/负债，按款项类型+小计) → 二、未确认融资费用(借方/备抵) → 长期应付款净额合计
2. THE Adjudication_L5_1 SHALL 显示列：项目 | 期初 | 贷方发生 | 借方发生 | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**
5. THE Formula_Engine SHALL 校验未确认融资费用（借方/备抵）：期末=期初+借方-贷方
6. THE Formula_Engine SHALL 计算净额=长期应付款-未确认融资费用
7. THE Adjudication_L5_1 SHALL 与L5-2/L5-3明细交叉验证
8. WHEN 审定数变化时 SHALL 回写TB(2701+未确认融资费用)+发布'substantive:adjudicated'

### Requirement 3: 明细表L5-2 + 未确认融资费用明细L5-3

**User Story:** As a 审计助理, I want to 管理长期应付款和未确认融资费用明细, so that 每笔款项和摊余可追溯。

#### Acceptance Criteria

1. THE Detail_L5_2 SHALL 显示列：款项来源 | 债权人 | 起始日 | 到期日 | 名义金额 | 折现率 | 现值 | 期初 | 本期增加 | 本期偿还 | 期末余额
2. THE Detail_L5_2 SHALL 自动计算：期末余额=期初+本期增加-本期偿还（负债类）
3. THE Unrecognized_Detail_L5_3 SHALL 显示：款项 | 初始未确认 | 本期摊销 | 累计摊销 | 未确认余额
4. THE Unrecognized_Detail_L5_3 SHALL 自动计算：未确认余额=初始-累计摊销
5. THE Detail_L5_2/L5_3 SHALL 支持动态行新增+导入导出
6. THE Detail_L5_2 SHALL 与L5-5摊销测算每笔款项一一对应

### Requirement 4: 未确认融资费用测算表L5-5（核心！实际利率法摊销）

**User Story:** As a 审计助理, I want to 验证未确认融资费用的摊销计算, so that 我能确认实际利率法下每期摊销正确。

#### Acceptance Criteria

1. THE Amortization_L5_5 SHALL 以表格渲染：期数 | 期初摊余成本 | 摊销额(=期初×实际利率) | 本期偿还 | 期末摊余成本
2. THE Amortization_Engine SHALL 实现实际利率法：每期摊销=期初摊余成本×实际利率
3. THE Amortization_Engine SHALL 实现期末摊余成本滚动
4. THE Amortization_L5_5 SHALL 验证最后一期未确认融资费用余额≈0（允许±1元尾差）
5. THE Amortization_L5_5 SHALL 全部期数摊销合计=初始未确认融资费用总额
6. THE Amortization_L5_5 SHALL 支持按款项筛选查看
7. THE Amortization_L5_5 SHALL 本期摊销 → EventBus publish 'l5:amortization-calculated'（供L8财务费用订阅）

### Requirement 5: 关联方及交易检查L5-6 + 检查表L5-7 + 调整 + 附注

**User Story:** As a 审计助理, I want to 检查关联方交易并完成检查表和附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE RelatedParty_Check_L5_6 SHALL 显示：债权人 | 关联关系 | 交易金额 | 定价依据 | 公允性评价
2. THE LTPayable_Check_L5_7 SHALL 提供核对清单+审计结论区（el-card包裹）+ AI辅助
3. THE Adjustment_L5_4 SHALL 借贷平衡校验+EventBus+双向同步L5-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 摊销引擎（实际利率法，纯函数）

**User Story:** As a 开发者, I want to 实现未确认融资费用摊销纯函数引擎, so that 每期摊销/余额可PBT验证。

#### Acceptance Criteria

1. THE Amortization_Engine SHALL calcAmortization(amortizedCost, eir): 摊销=期初摊余成本×实际利率
2. THE Amortization_Engine SHALL calcEndCost(begin, amortization, repayment): 期末摊余成本
3. THE Amortization_Engine SHALL generateSchedule(initialCost, repayments, eir, periods): 完整摊销表
4. THE generateSchedule SHALL 确保最后一期未确认余额≈0（调整尾差到最后一期）
5. THE Amortization_Engine SHALL 处理边界：eir=0时摊销=0

### Requirement 7: 公式引擎（负债类+净额）

**User Story:** As a 开发者, I want to 实现负债类纯函数公式引擎, so that 期末余额和净额可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(u, a, r)=u+a+r
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit)=begin+credit-debit
3. THE Formula_Engine SHALL calcContraLiabilityEndBalance(begin, debit, credit)=begin+debit-credit
4. THE Formula_Engine SHALL calcNetPayable(payable, unrecognized)=payable-unrecognized

### Requirement 8: 双模式+导入导出+版本链+复核对话+L8联动

**User Story:** As a 项目经理, I want to L5支持完整集成能力并联动L8, so that 与D~N底稿标准一致。

#### Acceptance Criteria

1. THE L5 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
2. THE L5 SHALL 支持导入导出三级（useL5ImportExport，http带Authorization）
3. THE L5 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
4. THE L5 SHALL 通过cross_wp_references关联L8财务费用（本期摊销计入财务费用），ref_index chip可跳转
