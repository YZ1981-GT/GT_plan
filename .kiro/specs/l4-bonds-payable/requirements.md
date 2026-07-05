# Requirements Document: L4 应付债券底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **L4利息测算→L2/L8** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL4ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L4应付债券底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l4-bonds-payable`，覆盖来自 `L4 应付债券.xlsx` 的15个有效sheet。科目覆盖2502应付债券（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L4核心特殊**（L筹资循环最复杂底稿）：①**贷方负债类科目**（期末=期初+贷方-借方）②**实际利率法后续计量2分支**（到期一次还本付息 vs 分期付息到期一次还本）用el-segmented分支选择器③**权益与负债划分检查**（复合金融工具分拆）④初始计量（发行价-交易费用）+摊余成本滚动⑤L4-2应付债券明细表**极宽表89列**需区段Tab拆分⑥L4-7后续计量/L4-8账面核对**各2版本**（分支选择器切换）。关键公式总数约250+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L4A**: 应付债券实质性程序表L4A（复用a-program-console）
- **Adjudication_L4_1**: 审定表L4-1，22×19，59公式，科目2502应付债券(贷方/负债)
- **Disclosure_Listed**: 附注披露信息（上市公司），72×19
- **Disclosure_SOE**: 附注披露信息（国有企业），61×19
- **Detail_L4_2**: 应付债券明细表L4-2，35×89（极宽表！需区段Tab拆分）
- **FinLiab_Other_L4_3**: 划分为金融负债的其他金融工具明细表L4-3，27×40，8公式
- **Adjustment_L4_4**: 调整分录L4-4
- **EquityLiab_Check_L4_5**: 权益与负债划分检查表L4-5，61×15
- **Initial_Measure_L4_6**: 应付债券初始计量L4-6，53×27（发行价-交易费用=初始摊余成本）
- **Subsequent_Bullet_L4_7A**: 应付债券后续计量(到期一次还本付息)，27×35，9公式（分支A）
- **Subsequent_Installment_L4_7B**: 应付债券后续计量(分期付息到期一次还本)，26×34，15公式（分支B）
- **BookRecon_Bullet_L4_8A**: 应付债券账面核对(到期一次还本付息)（分支A）
- **BookRecon_Installment_L4_8B**: 应付债券账面核对(分期付息到期一次还本)（分支B）
- **Bond_Check_L4_9**: 应付债券检查表L4-9
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **EIR_Engine**: 实际利率法引擎（每期利息=期初摊余成本×实际利率；摊余成本滚动，核心纯函数）
- **EquityLiab_Engine**: 权益负债划分引擎（复合工具分拆，纯函数）
- **Branch_Selector**: el-segmented分支选择器（到期一次还本付息/分期付息到期一次还本）
- **Trial_Balance_Writeback**: 审定数回写（科目2502）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L4应付债券底稿按sheetName分发, so that 15个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L4 组件 SHALL 注册新componentType: `l4-bonds-payable`，主入口为 GtL4BondsPayable.vue
2. THE GtL4BondsPayable.vue SHALL 接收 `sheetName` prop，正则提取编码(L4-1)，v-if分发
3. THE L4 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L4 组件 SHALL 拆为：l4/core/（审定+明细+调整+附注）、l4/measurement/（初始计量+后续计量2分支+账面核对2分支）、l4/classification/（权益负债划分+其他金融工具）、l4/inspection/（检查表）
5. THE L4 组件 SHALL composable分层：useL4FormData + useL4FormulaEngine + useL4EIREngine(纯函数) + useL4EquityLiabEngine(纯函数) + useL4CrossSheet + useL4DualMode + useL4ImportExport
6. THE L4 组件 SHALL 在htmlRendererRegistry中注册'l4-bonds-payable'
7. THE L4 组件 SHALL 在wp_code_overrides.json中将L4/L4-1~L4-9/L4A映射为'l4-bonds-payable'
8. THE L4 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l4-bonds-payable'
9. THE GtL4BondsPayable.vue SHALL 支持selfLoad
10. THE L4 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L4-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L4-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看应付债券数据, so that 我能验证负债类科目的期末余额和摊余成本。

#### Acceptance Criteria

1. THE Adjudication_L4_1 SHALL 渲染为单区块：应付债券(贷方/负债，按债券品种分类+小计)，列示面值/溢折价/摊余成本
2. THE Adjudication_L4_1 SHALL 显示列：项目 | 期初 | 贷方发生(发行+利息调整) | 借方发生(兑付) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**
5. THE Adjudication_L4_1 SHALL 与L4-2明细、L4-7后续计量摊余成本交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2502)+发布'substantive:adjudicated'
7. THE Adjudication_L4_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 应付债券明细表L4-2（极宽表89列！）

**User Story:** As a 审计助理, I want to 管理应付债券明细, so that 每只债券的完整信息可追溯。

#### Acceptance Criteria

1. THE Detail_L4_2 SHALL 显示债券基础信息：债券名称 | 发行日 | 到期日 | 面值总额 | 票面利率 | 实际利率 | 付息方式 | 期初/期末摊余成本
2. THE Detail_L4_2 SHALL **89列极宽表按区段Tab拆分**：基础信息/发行信息/计息付息/摊余成本/兑付信息 多区段Tab切换（行同步）
3. THE Detail_L4_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入债券名称）+导入导出（多区段分sheet导出）
4. THE Detail_L4_2 SHALL 与审定表L4-1交叉验证
5. THE Detail_L4_2 SHALL 与L4-6初始计量、L4-7后续计量按债券一一对应

### Requirement 4: 实际利率法后续计量L4-7（核心！2分支）

**User Story:** As a 审计助理, I want to 用实际利率法验证应付债券后续计量, so that 每期利息费用和摊余成本正确。

#### Acceptance Criteria

1. THE L4-7 SHALL 提供 Branch_Selector（el-segmented）：到期一次还本付息 / 分期付息到期一次还本
2. WHEN 选择"到期一次还本付息"时 SHALL 渲染 Subsequent_Bullet_L4_7A（27×35，9公式）
3. WHEN 选择"分期付息到期一次还本"时 SHALL 渲染 Subsequent_Installment_L4_7B（26×34，15公式）
4. THE EIR_Engine SHALL 实现：每期利息费用=期初摊余成本×实际利率
5. THE EIR_Engine SHALL 实现摊余成本滚动：
   - 到期一次还本付息：期末摊余成本=期初+利息费用（利息资本化滚入）
   - 分期付息到期一次还本：期末摊余成本=期初+利息费用-实付利息
6. THE L4-7 SHALL 显示表：期数 | 期初摊余成本 | 票面利息 | 实际利息费用(=期初×实际利率) | 利息调整摊销 | 期末摊余成本
7. THE L4-7 SHALL 验证最后一期期末摊余成本≈面值（允许±1元尾差）
8. THE L4-7 SHALL 合计实际利息费用 → EventBus publish 'l4:interest-calculated'（供L2/L8订阅）

### Requirement 5: 应付债券账面核对L4-8（2分支）

**User Story:** As a 审计助理, I want to 核对应付债券账面记录与后续计量, so that 账面记录准确。

#### Acceptance Criteria

1. THE L4-8 SHALL 提供 Branch_Selector 与L4-7联动（同分支）
2. WHEN 分支A时 SHALL 渲染 BookRecon_Bullet_L4_8A
3. WHEN 分支B时 SHALL 渲染 BookRecon_Installment_L4_8B
4. THE L4-8 SHALL 显示：账面摊余成本 | 测算摊余成本(来自L4-7) | 差异
5. THE L4-8 SHALL 自动计算差异=账面-测算
6. WHEN |差异|>阈值时 SHALL 红色高亮

### Requirement 6: 初始计量L4-6（发行价-交易费用）

**User Story:** As a 审计助理, I want to 验证应付债券初始计量, so that 初始摊余成本和实际利率正确。

#### Acceptance Criteria

1. THE Initial_Measure_L4_6 SHALL 显示：债券名称 | 面值 | 发行价格 | 交易费用 | 初始入账金额 | 溢折价 | 实际利率
2. THE Formula_Engine SHALL 计算初始入账金额=发行价格-交易费用
3. THE Formula_Engine SHALL 计算溢折价=初始入账金额-面值（正溢价/负折价）
4. THE L4-6 SHALL 提供实际利率求解（IRR，使未来现金流现值=初始入账金额）
5. THE L4-6 SHALL 与L4-7后续计量期初摊余成本对接

### Requirement 7: 权益与负债划分检查L4-5 + 其他金融工具L4-3

**User Story:** As a 审计助理, I want to 检查复合金融工具的权益负债划分, so that 分类正确。

#### Acceptance Criteria

1. THE EquityLiab_Check_L4_5 SHALL 显示（61×15）：工具名称 | 合同条款 | 负债成分 | 权益成分 | 划分依据
2. THE EquityLiab_Engine SHALL 实现复合工具分拆：权益成分=发行总额-负债成分现值
3. THE EquityLiab_Engine SHALL 负债成分现值=未来现金流按市场利率折现
4. THE FinLiab_Other_L4_3 SHALL 显示划分为金融负债的其他金融工具明细（27×40，8公式）
5. WHEN 权益成分<0时 SHALL 红色警告（分拆异常）

### Requirement 8: 调整分录L4-4 + 检查表L4-9 + 附注

**User Story:** As a 审计助理, I want to 管理应付债券调整并完成检查表和附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_L4_4 SHALL 借贷平衡校验+EventBus+双向同步L4-1
2. THE Bond_Check_L4_9 SHALL 提供核对清单+审计结论区（el-card包裹）+ AI辅助
3. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
4. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 9: 实际利率法引擎（核心纯函数）

**User Story:** As a 开发者, I want to 实现实际利率法的纯函数引擎, so that 每期利息/摊余成本可PBT验证。

#### Acceptance Criteria

1. THE EIR_Engine SHALL calcInterestExpense(amortizedCost, eir): 利息费用=期初摊余成本×实际利率
2. THE EIR_Engine SHALL calcEndAmortizedCost_Bullet(begin, interestExpense): 到期一次还本付息 期末=期初+利息费用
3. THE EIR_Engine SHALL calcEndAmortizedCost_Installment(begin, interestExpense, couponPaid): 分期付息 期末=期初+利息费用-实付利息
4. THE EIR_Engine SHALL generateSchedule(initialCost, faceValue, couponRate, eir, periods, branch): 完整后续计量表
5. THE generateSchedule SHALL 确保最后一期期末摊余成本≈面值（调整尾差到最后一期）
6. THE EIR_Engine SHALL 处理边界：eir=0时利息费用=0

### Requirement 10: 权益负债划分引擎（纯函数）

**User Story:** As a 开发者, I want to 实现复合金融工具分拆纯函数, so that 权益负债划分可PBT验证。

#### Acceptance Criteria

1. THE EquityLiab_Engine SHALL calcLiabilityComponent(cashFlows, marketRate): 负债成分=现金流现值
2. THE EquityLiab_Engine SHALL calcEquityComponent(totalProceeds, liabilityComponent): 权益成分=总额-负债成分
3. THE EquityLiab_Engine SHALL 处理边界：权益成分不为负则正常，为负标记异常

### Requirement 11: 跨底稿联动（L4→L2/L8）

**User Story:** As a 项目经理, I want to L4利息费用联动L2应付利息和L8财务费用, so that 筹资循环数据一致。

#### Acceptance Criteria

1. THE L4 SHALL 在L4-7后续计量完成后 publish 'l4:interest-calculated'（payload含合计实际利息费用）
2. THE L2应付利息 SHALL 订阅用于计提核对
3. THE L8财务费用 SHALL 订阅用于利息支出测算
4. THE L4 SHALL 通过cross_wp_references关联L2、L8，ref_index chip可跳转

### Requirement 12: 双模式+导入导出+版本链+复核对话

**User Story:** As a 审计助理, I want to L4支持完整集成能力, so that 与D~N底稿标准一致。

#### Acceptance Criteria

1. THE L4 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
2. THE L4 SHALL 支持导入导出三级（useL4ImportExport，89列极宽表多区段分sheet导出，http带Authorization）
3. THE L4 SHALL 集成useVersionTrail(autoSnapshot)
4. THE L4 SHALL 主入口provide openReviewDialog，子组件inject
