# Requirements Document: H9 租赁负债底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **H8使用权资产强联动** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useH9ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级
- **CAS21**：新租赁准则核心，与H8配对

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

H9租赁负债底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h9-lease-liabilities`，覆盖来自 `H9 租赁负债.xlsx` 的约10个有效sheet。科目覆盖2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）。

**H9核心特殊**：①CAS21新租赁准则核心底稿（与H8配对）②**摊销表是核心**（实际利率法：每期利息=期初余额×实际利率；本金偿还=每期付款-利息）③增量借款利率确定（IBR）④现值折现（租赁负债=未来租金现值）⑤**贷方科目**（负债类！期末=期初+贷方-借方）。关键公式总数约150+。

## Glossary

- **Tab_Index**: 底稿目录，19行8列
- **Procedure_Table_H9A**: 租赁负债实质性程序表H9A
- **Adjudication_H9_1**: 审定表H9-1，科目2205租赁负债(贷方/负债)+未确认融资费用(借方/备抵)
- **Disclosure_Listed**: 附注披露信息（上市公司）
- **Disclosure_SOE**: 附注披露信息（国企）
- **Detail_H9_2**: 租赁负债明细表H9-2，按合同列示
- **Finance_Cost_H9_3**: 未确认融资费用明细表H9-3
- **Amortization_H9_4**: 租赁负债摊销表H9-4（核心！每期利息+本金分摊）
- **Adjustment_H9_5**: 调整分录H9-5
- **Related_Party_H9_6**: 关联交易检查表H9-6
- **Cross_Sheet_Engine**: 跨sheet引擎 + H8联动
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Amortization_Engine**: 摊销表引擎（实际利率法，核心纯函数）
- **IBR_Engine**: 增量借款利率确定引擎
- **PV_Engine**: 现值计算引擎（租赁负债=未来租金的现值）
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目2205+未确认融资费用）
- **H8_Linkage**: H8使用权资产联动

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H9租赁负债底稿按sheetName分发, so that ~10个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE H9 组件 SHALL 注册新componentType: `h9-lease-liabilities`，主入口为 GtH9LeaseLiabilities.vue
2. THE GtH9LeaseLiabilities.vue SHALL 接收 `sheetName` prop，v-if分发
3. THE H9 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE H9 组件 SHALL 拆为：h9/core/（审定+明细+融资费用+调整+附注）、h9/amortization/（摊销表）、h9/inspection/（关联交易）
5. THE H9 组件 SHALL composable分层：useH9FormData + useH9FormulaEngine + useH9AmortizationEngine(纯函数) + useH9PVEngine(纯函数) + useH9CrossSheet + useH9DualMode + useH9ImportExport
6. THE H9 组件 SHALL 在htmlRendererRegistry中注册'h9-lease-liabilities'
7. THE H9 组件 SHALL 在wp_code_overrides.json中将H9/H9-1~H9-6/H9A映射为'h9-lease-liabilities'
8. THE H9 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h9-lease-liabilities'
9. THE GtH9LeaseLiabilities.vue SHALL 支持selfLoad
10. THE H9 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"H9-{sheet}-{field}"

### Requirement 2: 审定表H9-1（负债类贷方科目+未确认融资费用备抵）

**User Story:** As a 审计助理, I want to 在精美审定表中查看租赁负债数据, so that 我能验证CAS21下的负债计量。

#### Acceptance Criteria

1. THE Adjudication_H9_1 SHALL 渲染为双区块：一、租赁负债(贷方/负债，按合同类型+小计) → 二、未确认融资费用(借方/备抵) → 租赁负债净额合计
2. THE Adjudication_H9_1 SHALL 显示列：项目 | 期初 | 贷方发生(增加) | 借方发生(减少) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**（注意！与资产类相反）
5. THE Formula_Engine SHALL 校验未确认融资费用（借方/备抵）：期末=期初+借方-贷方
6. THE Adjudication_H9_1 SHALL 与H9-2明细合计交叉验证
7. THE Adjudication_H9_1 SHALL 与H8审定表联动校验（H9初始≈H8初始-直接费用+激励）
8. WHEN 审定数变化时 SHALL 回写TB(2205+未确认融资费用)+发布'substantive:adjudicated'

### Requirement 3: 租赁负债明细表H9-2 + 未确认融资费用H9-3

**User Story:** As a 审计助理, I want to 管理租赁负债和未确认融资费用的明细, so that 每笔租赁合同的负债和利息可追溯。

#### Acceptance Criteria

1. THE Detail_H9_2 SHALL 显示按合同列示：合同号 | 出租方 | 承租资产 | 租赁期 | 年租金 | 利率(IBR) | 初始确认 | 本期偿还 | 本期利息 | 期末余额
2. THE Detail_H9_2 SHALL 自动计算：期末余额=期初+本期利息-本期偿还
3. THE Detail_H9_2 SHALL 与H8-2每笔合同一一对应（通过合同号关联）
4. THE Finance_Cost_H9_3 SHALL 显示：合同号 | 初始融资费用 | 本期确认 | 累计确认 | 未确认余额
5. THE Finance_Cost_H9_3 SHALL 自动计算：未确认余额=初始-累计确认
6. THE Detail_H9_2/H9_3 SHALL 支持动态行新增+导入导出

### Requirement 4: 租赁负债摊销表H9-4（核心！实际利率法）

**User Story:** As a 审计助理, I want to 验证租赁负债的摊销计算, so that 我能确认实际利率法下每期利息和本金分摊正确。

#### Acceptance Criteria

1. THE Amortization_H9_4 SHALL 以表格渲染：期数 | 期初余额 | 本期租金 | 利息费用(=期初×利率) | 本金偿还(=租金-利息) | 期末余额(=期初-本金)
2. THE Amortization_Engine SHALL 实现实际利率法：每期利息=期初余额×实际利率
3. THE Amortization_Engine SHALL 实现本金拆分：本金偿还=每期付款-利息费用
4. THE Amortization_Engine SHALL 实现期末余额：期末=期初-本金偿还
5. THE Amortization_H9_4 SHALL 验证最后一期期末余额≈0（允许±1元尾差）
6. THE Amortization_H9_4 SHALL 全部期数利息费用合计=初始融资费用总额
7. THE Amortization_H9_4 SHALL 支持按合同筛选（下拉选择合同号查看对应摊销）
8. THE Amortization_H9_4 SHALL 与H9-1审定表本期利息交叉验证

### Requirement 5: 调整分录H9-5 + 关联交易H9-6

**User Story:** As a 审计助理, I want to 管理租赁负债调整和检查关联租赁, so that 审计调整有据可循且关联租赁公允性得到评价。

#### Acceptance Criteria

1. THE Adjustment_H9_5 SHALL 10列+借贷平衡+EventBus+双向同步H9-1
2. THE Related_Party_H9_6 SHALL 15列含：合同号/出租方/关联关系/年租金/市场租金/价差率
3. THE Related_Party_H9_6 SHALL 自动计算价差率=(年租金-市场租金)/市场租金×100%
4. WHEN 价差率>10%时 SHALL 红色高亮

### Requirement 6: 现值计算引擎（租赁负债初始确认）

**User Story:** As a 开发者, I want to 实现租赁负债现值计算的纯函数引擎, so that 初始确认金额=未来租金现值可PBT验证。

#### Acceptance Criteria

1. THE PV_Engine SHALL calcPresentValue(payments, rate, periods): 现值=Σ(付款/(1+rate)^n)
2. THE PV_Engine SHALL calcAnnuityPV(payment, rate, periods): 等额年金现值
3. THE PV_Engine SHALL calcIBR(marketRate, creditSpread, termAdjust): 增量借款利率
4. THE PV_Engine SHALL 处理边界：利率为0时PV=payments之和；期数为0时PV=0

### Requirement 7: 摊销表引擎（实际利率法）

**User Story:** As a 开发者, I want to 实现实际利率法摊销的纯函数引擎, so that 每期利息/本金/余额计算可PBT验证。

#### Acceptance Criteria

1. THE Amortization_Engine SHALL calcInterest(balance, rate): 利息=期初余额×利率
2. THE Amortization_Engine SHALL calcPrincipal(payment, interest): 本金=付款-利息
3. THE Amortization_Engine SHALL calcEndBalance(beginBalance, principal): 期末=期初-本金
4. THE Amortization_Engine SHALL generateSchedule(initialBalance, payment, rate, periods): 完整摊销表
5. THE generateSchedule SHALL 确保最后一期期末余额≈0（调整尾差到最后一期）

### Requirement 8: H8-H9联动校验

**User Story:** As a 项目经理, I want to 系统自动验证H9与H8的一致性, so that CAS21配对底稿数据不偏差。

#### Acceptance Criteria

1. THE H9 SHALL 在审定表底部显示"H8-H9联动校验"区域
2. THE 联动 SHALL 验证：H9初始确认金额 ≈ H8初始-直接费用+激励（±1元容差）
3. THE H9-2每笔合同 SHALL 与H8-2一一对应（合同号匹配）
4. WHEN 联动不一致时 SHALL 红色警告+差额显示
