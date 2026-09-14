# Requirements Document

## Introduction

F2存货底稿Group 2：计价测试 + 跌价准备测试 + 关联交易的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f2-inventory-valuation`，覆盖3个xlsx源模板/13个有效sheet（计价方法测试F2-38~F2-40 + 生产成本分析F2-41~F2-44 + 跌价准备测试F2-47~F2-49 + 关联交易F2-52）。与 `f2-inventory-main` 独立但共享部分composable逻辑（useF2FormulaEngine公式引擎扩展NRV公式）。

**源模板sheet清单（openpyxl实读确认）**：

### File 1: F2-38至F2-44 计价测试（7 effective sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **计价方法测试表-平均F2-38** | 94×15 | 月末一次加权平均法测试 |
| 2 | **计价方法测试表-先进先出F2-39** | 75×15 | 先进先出/移动加权平均法 |
| 3 | **计价方法测试表-标准成本差异F2-40** | 64×16 | 标准成本差异测试 |
| 4 | **生产成本明细表F2-41** | 27×17 | 生产成本构成 |
| 5 | **直接人工分析表F2-42** | 48×17 | 直接人工分析 |
| 6 | **制造费用明细表F2-43** | 36×16 | 制造费用构成 |
| 7 | **生产成本分配F2-44** | 29×15 | 成本分配测试 |

### File 2: F2-47至F2-49 跌价准备测试（3 effective sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **跌价准备测试表F2-47** | 59×28 | **最复杂宽表！** 抽样参数区+NRV测试 |
| 2 | **长库龄呆滞超保质期存货明细表F2-48** | 33×14 | 库龄/呆滞/保质期风险 |
| 3 | **跌价转回F2-49** | 36×24 | 转回项目对比分析 |

### File 3: F2-52 关联交易（1 effective sheet）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **关联采购分析表F2-52** | 41×17 | 关联方采购公允性分析 |

**宽表处理策略**：
- F2-47跌价准备测试(28列)：拆为3区段Tab（基础信息/NRV测算/跌价结论），每区段8-10列
- F2-49跌价转回(24列)：拆为2区段Tab（上期跌价情况/本期NRV+转回判定）
- F2-38~F2-40计价测试(15-16列)：含抽样参数区 + 动态行检查表（凭证核对模式）

核心特色：NRV测算公式（可变现净值=估计售价-估计完工成本-估计销售费用；应计提跌价=MAX(0, 账面成本-NRV)）、跌价转回判定逻辑、计价方法抽样凭证核对、生产成本构成分析、关联交易公允性评价。与f2-inventory-main的EventBus联动（impairment:calculated → F2-1跌价区联动）。

## Glossary

- **NRV**: Net Realizable Value，可变现净值 = 估计售价 - 估计完工成本 - 估计销售费用
- **Impairment_Provision**: 存货跌价准备 = MAX(0, 账面成本 - NRV)
- **Valuation_Test**: 计价方法测试，验证企业发出存货计价方法（加权平均/先进先出/标准成本）的正确性
- **Weighted_Average**: 月末一次加权平均法，单位成本 = (期初金额+本期入库金额)/(期初数量+本期入库数量)
- **FIFO**: 先进先出法/移动加权平均法
- **Standard_Cost_Variance**: 标准成本差异 = 实际成本 - 标准成本
- **Production_Cost**: 生产成本 = 直接材料 + 直接人工 + 制造费用
- **Direct_Labor**: 直接人工 = 工时×工资率
- **Manufacturing_Overhead**: 制造费用，按分配基准归集到产品
- **Cost_Allocation**: 成本分配测试，验证分配基准和分配结果的正确性
- **Obsolete_Inventory**: 长库龄/呆滞/超保质期存货，需额外评估跌价
- **Impairment_Reversal**: 跌价转回，前期已计提跌价但本期NRV回升，CAS准则限额转回
- **Related_Party_Purchase**: 关联采购，需评价定价公允性（关联方价格 vs 可比市场价格）
- **Sampling_Parameters**: 抽样参数区（总体/样本量/抽样方法/置信水平/可接受误差）
- **Segment_Tab**: 区段Tab宽表拆分模式，>15列表横向拆为多区段Tab，行保持同步
- **EventBus**: 进程内事件总线，impairment:calculated发布跌价测算结果联动F2-1
- **Formula_Engine_Extended**: 扩展公式引擎，在useF2FormulaEngine基础上增加NRV/跌价/差异率公式

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F2计价+跌价+关联交易底稿按sheetName prop分发到独立子组件, so that 13个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F2-Valuation 组件 SHALL 注册新componentType: `f2-inventory-valuation`，主入口为 GtF2InventoryValuation.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F2-Valuation 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（13个sheet按需加载）
1.3 THE F2-Valuation 组件 SHALL 在htmlRendererRegistry中注册'f2-inventory-valuation'→GtF2InventoryValuation映射
1.4 THE F2-Valuation 组件 SHALL 在wp_code_overrides.json中将F2-38~F2-40/F2-41~F2-44/F2-47~F2-49/F2-52的componentType统一映射为'f2-inventory-valuation'（13个wp_code条目）
1.5 THE F2-Valuation 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f2-inventory-valuation'
1.6 THE GtF2InventoryValuation.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f2-inventory-valuation）
1.7 THE GtF2InventoryValuation.vue SHALL 用正则从sheetName提取末尾编码(F2-38/F2-47等)，匹配失败走OnlyOffice fallback
1.8 THE F2-Valuation 组件 SHALL 采用el-tabs模式组织4个tab-group：计价方法测试(F2-38~F2-40) / 生产成本分析(F2-41~F2-44) / 跌价准备(F2-47~F2-49) / 关联交易(F2-52)

### Requirement 2: 计价方法测试表-平均F2-38 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中执行月末一次加权平均法计价测试, so that 我能验证企业发出存货计价金额的正确性。

#### Acceptance Criteria

2.1 THE Valuation_Test(F2-38) SHALL 分为两个区域：抽样参数区（固定） + 动态行检查表
2.2 THE 抽样参数区 SHALL 显示：总体金额/样本量/抽样方法(下拉)/置信水平/可接受误差/重要性水平（6字段横排）
2.3 THE 动态行检查表 SHALL 显示15列：序号 | 品名 | 期初数量 | 期初金额 | 本期入库数量 | 本期入库金额 | 加权平均单价(公式) | 发出数量 | 审计计算发出金额(公式) | 企业记录发出金额 | 差异额(公式) | 差异率(公式) | 凭证编号 | 核对结果 | 备注
2.4 THE Formula_Engine_Extended SHALL 计算加权平均单价 = (期初金额 + 本期入库金额) / (期初数量 + 本期入库数量)
2.5 THE Formula_Engine_Extended SHALL 计算审计计算发出金额 = 加权平均单价 × 发出数量
2.6 THE Formula_Engine_Extended SHALL 计算差异额 = 审计计算发出金额 - 企业记录发出金额
2.7 THE Formula_Engine_Extended SHALL 计算差异率 = 差异额 / 企业记录发出金额 × 100%
2.8 WHEN 差异率绝对值>1%时, THE 系统 SHALL 以红色高亮该行
2.9 THE Valuation_Test(F2-38) SHALL 支持动态行增删
2.10 THE Valuation_Test(F2-38) SHALL 底部汇总：合计差异金额 + 超差异笔数 + 测试结论textarea(AI辅助)
2.11 THE Valuation_Test(F2-38) SHALL 支持导入导出

### Requirement 3: 计价方法测试表-先进先出F2-39 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中执行先进先出/移动加权平均法计价测试, so that 我能验证FIFO计价的正确性。

#### Acceptance Criteria

3.1 THE Valuation_Test(F2-39) SHALL 分为两个区域：抽样参数区（同F2-38结构） + 动态行检查表
3.2 THE 动态行检查表 SHALL 显示15列：序号 | 品名 | 批次号 | 入库日期 | 入库数量 | 入库单价 | 入库金额 | 发出数量 | 应发单价(FIFO序) | 审计计算发出金额(公式) | 企业记录发出金额 | 差异额(公式) | 差异率(公式) | 核对结果 | 备注
3.3 THE Formula_Engine_Extended SHALL 计算FIFO发出金额（按入库时间顺序匹配发出数量）
3.4 THE Formula_Engine_Extended SHALL 计算差异额 = 审计计算发出金额 - 企业记录发出金额
3.5 WHEN 差异率绝对值>1%时, THE 系统 SHALL 以红色高亮该行
3.6 THE Valuation_Test(F2-39) SHALL 支持动态行增删 + 底部合计 + 测试结论textarea(AI辅助)
3.7 THE Valuation_Test(F2-39) SHALL 支持导入导出

### Requirement 4: 计价方法测试表-标准成本差异F2-40 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中执行标准成本差异测试, so that 我能验证标准成本法的差异分配是否合理。

#### Acceptance Criteria

4.1 THE Valuation_Test(F2-40) SHALL 分为两个区域：抽样参数区 + 动态行检查表
4.2 THE 动态行检查表 SHALL 显示16列：序号 | 品名 | 标准单价 | 标准数量 | 标准成本(公式) | 实际单价 | 实际数量 | 实际成本(公式) | 价格差异(公式) | 数量差异(公式) | 总差异(公式) | 差异率(公式) | 差异分配方式 | 分配比例 | 核对结果 | 备注
4.3 THE Formula_Engine_Extended SHALL 计算标准成本 = 标准单价 × 标准数量
4.4 THE Formula_Engine_Extended SHALL 计算实际成本 = 实际单价 × 实际数量
4.5 THE Formula_Engine_Extended SHALL 计算价格差异 = (实际单价 - 标准单价) × 实际数量
4.6 THE Formula_Engine_Extended SHALL 计算数量差异 = (实际数量 - 标准数量) × 标准单价
4.7 THE Formula_Engine_Extended SHALL 计算总差异 = 实际成本 - 标准成本（= 价格差异 + 数量差异）
4.8 WHEN 差异率绝对值>5%时, THE 系统 SHALL 以红色高亮该行
4.9 THE Valuation_Test(F2-40) SHALL 支持动态行增删 + 底部合计 + 测试结论textarea(AI辅助)
4.10 THE Valuation_Test(F2-40) SHALL 支持导入导出

### Requirement 5: 生产成本明细表F2-41 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析生产成本构成, so that 我能验证成本归集的完整性和准确性。

#### Acceptance Criteria

5.1 THE Production_Cost(F2-41) SHALL 显示17列：产品名称 | 直接材料(期初/本期投入/完工转出/期末) | 直接人工(同4列) | 制造费用(同4列) | 合计(同4列) | 备注
5.2 THE Production_Cost(F2-41) SHALL 每个成本要素内计算：期末 = 期初 + 本期投入 - 完工转出
5.3 THE Formula_Engine_Extended SHALL 计算合计列 = 直接材料 + 直接人工 + 制造费用（同一行同一期间）
5.4 THE Production_Cost(F2-41) SHALL 底部合计行 = SUM各产品行
5.5 THE Production_Cost(F2-41) SHALL 底部审计说明textarea(AI辅助)
5.6 THE Production_Cost(F2-41) SHALL 支持动态行增删

### Requirement 6: 直接人工分析表F2-42 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析直接人工成本, so that 我能验证人工费用归集的合理性。

#### Acceptance Criteria

6.1 THE Direct_Labor(F2-42) SHALL 显示17列：部门/产品 | 工种 | 人数 | 出勤工时 | 工资率 | 计算人工费(公式) | 实际人工费 | 差异额(公式) | 差异率(公式) | 加班工时 | 加班费率 | 加班费 | 社保 | 公积金 | 人工费合计(公式) | 占比(公式) | 备注
6.2 THE Formula_Engine_Extended SHALL 计算计算人工费 = 人数 × 出勤工时 × 工资率
6.3 THE Formula_Engine_Extended SHALL 计算人工费合计 = 计算人工费 + 加班费 + 社保 + 公积金
6.4 THE Formula_Engine_Extended SHALL 计算差异额 = 计算人工费 - 实际人工费
6.5 THE Formula_Engine_Extended SHALL 计算占比 = 该行人工费合计 / 全部行人工费合计SUM × 100%
6.6 WHEN 差异率绝对值>5%时, THE 系统 SHALL 以橙色高亮该行
6.7 THE Direct_Labor(F2-42) SHALL 支持动态行增删 + 底部合计 + 审计说明textarea(AI辅助)
6.8 THE Direct_Labor(F2-42) SHALL 支持导入导出

### Requirement 7: 制造费用明细表F2-43 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析制造费用构成, so that 我能验证费用归集分配的合理性。

#### Acceptance Criteria

7.1 THE Manufacturing_Overhead(F2-43) SHALL 显示16列：费用项目 | 本期发生额 | 上期发生额 | 变动额(公式) | 变动率(公式) | 预算数 | 预算差异(公式) | 预算差异率(公式) | 分配基准 | 分配率 | 产品A分配额 | 产品B分配额 | 产品C分配额 | 分配合计(公式) | 是否合理 | 备注
7.2 THE Formula_Engine_Extended SHALL 计算变动额 = 本期 - 上期
7.3 THE Formula_Engine_Extended SHALL 计算变动率 = (本期 - 上期) / 上期 × 100%
7.4 THE Formula_Engine_Extended SHALL 计算预算差异 = 本期发生额 - 预算数
7.5 THE Formula_Engine_Extended SHALL 计算分配合计 = 产品A + 产品B + 产品C（≠发生额时红色高亮）
7.6 WHEN 变动率绝对值>20%时, THE 系统 SHALL 以橙色高亮该行
7.7 THE Manufacturing_Overhead(F2-43) SHALL 支持动态行增删 + 底部合计 + 审计说明textarea(AI辅助)
7.8 THE Manufacturing_Overhead(F2-43) SHALL 支持导入导出

### Requirement 8: 生产成本分配F2-44 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中验证生产成本分配, so that 我能确认成本分配标准的一致性和结果的正确性。

#### Acceptance Criteria

8.1 THE Cost_Allocation(F2-44) SHALL 显示15列：产品名称 | 分配基准(下拉:工时/产量/机器小时/材料成本) | 基准数量 | 基准占比(公式) | 直接材料分配(公式) | 直接人工分配(公式) | 制造费用分配(公式) | 合计分配(公式) | 企业分配额 | 差异(公式) | 差异率(公式) | 审计评价 | 分配方法变更 | 变更说明 | 备注
8.2 THE Formula_Engine_Extended SHALL 计算基准占比 = 该产品基准数量 / 全部产品基准数量SUM × 100%
8.3 THE Formula_Engine_Extended SHALL 计算各成本要素分配额 = 对应要素总额 × 基准占比
8.4 THE Formula_Engine_Extended SHALL 计算差异 = 合计分配 - 企业分配额
8.5 WHEN 差异率绝对值>3%时, THE 系统 SHALL 以橙色高亮该行
8.6 THE Cost_Allocation(F2-44) SHALL 与F2-41/F2-42/F2-43自动取数（直接材料/人工/制造费用总额）
8.7 THE Cost_Allocation(F2-44) SHALL 支持动态行增删 + 底部合计 + 审计说明textarea(AI辅助)
8.8 THE Cost_Allocation(F2-44) SHALL 支持导入导出

### Requirement 9: 跌价准备测试表F2-47 HTML渲染（28列宽表→3区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中执行存货跌价准备NRV测试, so that 我能验证各存货项目的可变现净值及应计提跌价金额。

#### Acceptance Criteria

9.1 THE Impairment_Test(F2-47) SHALL 分为两大区域：抽样参数区（固定顶部） + 3区段Tab动态检查表
9.2 THE 抽样参数区 SHALL 显示：总体金额/样本量/抽样方法/置信水平/重要性水平/跌价准备账面余额（6字段横排）
9.3 THE 3区段Tab SHALL 拆分28列如下：
   - **基础信息(10列)**：序号 | 存货类别 | 品名 | 规格 | 数量 | 单位成本 | 账面成本(公式) | 库龄 | 存放地点 | 状态(正常/呆滞/报废)
   - **NRV测算(10列)**：估计售价 | 至完工估计成本 | 估计销售费用 | 估计销售税金 | 可变现净值(公式) | 单位NRV(公式) | NRV-账面差(公式) | 应计提跌价(公式) | 测试结论(下拉) | 备注
   - **跌价结论(8列)**：已计提跌价 | 本期应补提(公式) | 本期应转回(公式) | 调整后跌价 | 与企业差异(公式) | 差异原因 | 审计建议 | 索引
9.4 THE Formula_Engine_Extended SHALL 计算账面成本 = 数量 × 单位成本
9.5 THE Formula_Engine_Extended SHALL 计算NRV = 估计售价 - 至完工估计成本 - 估计销售费用 - 估计销售税金
9.6 THE Formula_Engine_Extended SHALL 计算应计提跌价 = MAX(0, 账面成本 - NRV)
9.7 THE Formula_Engine_Extended SHALL 计算本期应补提 = MAX(0, 应计提跌价 - 已计提跌价)
9.8 THE Formula_Engine_Extended SHALL 计算本期应转回 = MAX(0, 已计提跌价 - 应计提跌价)
9.9 THE Formula_Engine_Extended SHALL 计算与企业差异 = 调整后跌价 - 已计提跌价
9.10 WHEN 应计提跌价>0 且 测试结论为空时, THE 系统 SHALL 以橙色高亮提醒填写结论
9.11 THE Impairment_Test(F2-47) SHALL 支持动态行增删
9.12 THE Impairment_Test(F2-47) SHALL 底部汇总：合计账面成本/合计NRV/合计应计提/合计已计提/净差异 + 测试结论textarea(AI辅助)
9.13 THE Impairment_Test(F2-47) SHALL 区段间保持行同步（切换区段不丢失当前行位置）
9.14 THE Impairment_Test(F2-47) SHALL 实现EventBus发布 `impairment:calculated`（payload含各类别应计提跌价合计 → F2-1跌价区联动）
9.15 THE Impairment_Test(F2-47) SHALL 支持导入导出

### Requirement 10: 长库龄呆滞超保质期存货明细表F2-48 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中识别长库龄/呆滞/超保质期存货, so that 我能评估这些高风险存货的跌价风险。

#### Acceptance Criteria

10.1 THE Obsolete_Inventory(F2-48) SHALL 显示14列：序号 | 品名 | 规格 | 库龄(天) | 入库日期 | 数量 | 账面金额 | 是否呆滞(下拉) | 保质期(天) | 是否超保质期(公式) | 剩余保质天数(公式) | 处理方案(下拉) | 跌价建议金额 | 备注
10.2 THE Formula_Engine_Extended SHALL 计算是否超保质期 = 库龄 > 保质期 → "是" / "否"
10.3 THE Formula_Engine_Extended SHALL 计算剩余保质天数 = 保质期 - 库龄（<0时显示"已超期N天"）
10.4 WHEN 是否超保质期="是" 或 是否呆滞="是" 时, THE 系统 SHALL 以橙色高亮该行
10.5 THE Obsolete_Inventory(F2-48) SHALL 处理方案下拉选项：正常销售/促销处理/报废/退货/转跌价
10.6 THE Obsolete_Inventory(F2-48) SHALL 底部汇总：长库龄笔数/呆滞笔数/超保质期笔数/跌价建议合计金额
10.7 THE Obsolete_Inventory(F2-48) SHALL 支持动态行增删 + 审计说明textarea(AI辅助)
10.8 THE Obsolete_Inventory(F2-48) SHALL 支持导入导出

### Requirement 11: 跌价转回F2-49 HTML渲染（24列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中评估存货跌价准备转回的合理性, so that 我能验证转回是否符合CAS准则。

#### Acceptance Criteria

11.1 THE Impairment_Reversal(F2-49) SHALL 拆为2区段Tab：
   - **上期跌价情况(12列)**：序号 | 品名 | 规格 | 上期账面成本 | 上期NRV | 上期应计提跌价 | 上期已计提跌价 | 上期跌价充足性 | 计提日期 | 计提原因 | 累计计提 | 备注
   - **本期NRV+转回判定(12列)**：本期账面成本 | 本期估计售价 | 本期至完工成本 | 本期销售费用 | 本期NRV(公式) | 本期应计提(公式) | 是否应转回(公式) | 转回金额(公式) | 转回上限(公式) | 实际转回 | 转回合理性(下拉) | 审计评价
11.2 THE Formula_Engine_Extended SHALL 计算本期NRV = 本期估计售价 - 本期至完工成本 - 本期销售费用
11.3 THE Formula_Engine_Extended SHALL 计算本期应计提 = MAX(0, 本期账面成本 - 本期NRV)
11.4 THE Formula_Engine_Extended SHALL 计算是否应转回 = 上期已计提跌价 > 本期应计提 → "应转回" / "不转回"
11.5 THE Formula_Engine_Extended SHALL 计算转回金额 = MIN(上期已计提跌价 - 本期应计提, 转回上限)
11.6 THE Formula_Engine_Extended SHALL 计算转回上限 = 累计计提金额（CAS规定转回不超过原计提）
11.7 WHEN 是否应转回="应转回" 且 转回合理性为空时, THE 系统 SHALL 以橙色高亮提醒评价
11.8 THE Impairment_Reversal(F2-49) SHALL 底部汇总：转回笔数/转回总额/超限笔数 + 审计说明textarea(AI辅助)
11.9 THE Impairment_Reversal(F2-49) SHALL 区段间行同步
11.10 THE Impairment_Reversal(F2-49) SHALL 支持动态行增删 + 导入导出

### Requirement 12: 关联采购分析表F2-52 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析关联采购的公允性, so that 我能评价关联交易定价是否公允。

#### Acceptance Criteria

12.1 THE Related_Party_Purchase(F2-52) SHALL 显示17列：序号 | 关联方名称 | 关联关系 | 采购品名 | 采购数量 | 采购单价 | 采购金额(公式) | 占总采购比例(公式) | 定价方式(下拉) | 可比市场价格 | 差异率(公式) | 同类非关联方价格 | 非关联差异率(公式) | 公允性结论(下拉) | 审计评价 | 索引 | 备注
12.2 THE Formula_Engine_Extended SHALL 计算采购金额 = 采购数量 × 采购单价
12.3 THE Formula_Engine_Extended SHALL 计算占总采购比例 = 该关联方采购金额 / 全部采购金额SUM × 100%
12.4 THE Formula_Engine_Extended SHALL 计算差异率 = (采购单价 - 可比市场价格) / 可比市场价格 × 100%
12.5 THE Formula_Engine_Extended SHALL 计算非关联差异率 = (采购单价 - 同类非关联方价格) / 同类非关联方价格 × 100%
12.6 WHEN 差异率绝对值>10%时, THE 系统 SHALL 以红色高亮该行
12.7 THE Related_Party_Purchase(F2-52) SHALL 定价方式下拉选项：市场定价/协议定价/成本加成/参照同类
12.8 THE Related_Party_Purchase(F2-52) SHALL 公允性结论下拉：公允/基本公允/不公允/无法判断
12.9 THE Related_Party_Purchase(F2-52) SHALL 底部汇总：关联采购总额/占比/不公允笔数 + 审计说明textarea(AI辅助)
12.10 THE Related_Party_Purchase(F2-52) SHALL 支持动态行增删 + 导入导出 + GtIndexChip索引列

### Requirement 13: 扩展公式引擎

**User Story:** As a 开发者, I want to 在f2-inventory-main公式引擎基础上扩展NRV/计价/差异公式, so that 跌价和计价测试的公式可PBT验证。

#### Acceptance Criteria

13.1 THE Formula_Engine_Extended SHALL 实现 `calcNRV`（NRV = 售价 - 完工成本 - 销售费用 - 销售税金）
13.2 THE Formula_Engine_Extended SHALL 实现 `calcImpairmentProvision`（应计提跌价 = MAX(0, 账面成本 - NRV)）
13.3 THE Formula_Engine_Extended SHALL 实现 `calcWeightedAvgPrice`（加权平均单价 = (期初金额+入库金额)/(期初数量+入库数量)）
13.4 THE Formula_Engine_Extended SHALL 实现 `calcStandardCost`（标准成本 = 标准单价 × 标准数量）
13.5 THE Formula_Engine_Extended SHALL 实现 `calcPriceVariance`（价格差异 = (实际单价-标准单价) × 实际数量）
13.6 THE Formula_Engine_Extended SHALL 实现 `calcQuantityVariance`（数量差异 = (实际数量-标准数量) × 标准单价）
13.7 THE Formula_Engine_Extended SHALL 实现 `calcTotalVariance`（总差异 = 实际成本 - 标准成本）
13.8 THE Formula_Engine_Extended SHALL 实现 `calcReversalAmount`（转回金额 = MIN(已计提-应计提, 转回上限)）
13.9 THE Formula_Engine_Extended SHALL 实现 `calcAllocationRatio`（分配比例 = 本品基准/全部基准SUM）
13.10 THE Formula_Engine_Extended SHALL 实现 `calcFairnessDeviation`（公允性差异率 = (关联价-可比价)/可比价 × 100%）
13.11 THE Formula_Engine_Extended SHALL 实现 `isExpired`（超保质期判定 = 库龄 > 保质期）
13.12 THE Formula_Engine_Extended SHALL 实现 `calcRemainingShelfDays`（剩余保质天数 = 保质期 - 库龄）

### Requirement 14: 导入导出功能

**User Story:** As a 审计助理, I want to 支持Excel导入导出, so that 我能离线填写计价/跌价测试数据后导入系统。

#### Acceptance Criteria

14.1 THE Import_Export SHALL 使用useF2ValuationImportExport composable统一管理（后端三端点）
14.2 THE Import_Export SHALL 对以下动态行表格支持导入导出：F2-38~F2-40计价测试(3张)/F2-41~F2-44成本分析(4张)/F2-47~F2-49跌价测试(3张)/F2-52关联交易(1张)，共11张
14.3 THE Import_Export SHALL 导出空模板含填写说明sheet + 数据校验规则
14.4 THE Import_Export SHALL 导入时进行数据验证（日期/金额/必填字段/NRV公式校验）
14.5 THE Import_Export SHALL 导入失败时显示详细错误信息（行号/字段/原因）
14.6 THE Import_Export SHALL StreamingResponse中文文件名RFC5987编码

### Requirement 15: EventBus联动与跨组件通信

**User Story:** As a 开发者, I want to F2-47跌价测试结果联动F2-1审定表跌价区, so that 跌价数据自动同步不需手工搬运。

#### Acceptance Criteria

15.1 THE EventBus SHALL 发布 `impairment:calculated` 事件（F2-47测试完成→payload含各类别应计提跌价合计）
15.2 THE f2-inventory-main SHALL 监听 `impairment:calculated` 事件 → 更新F2-1审定表跌价准备区对应行
15.3 THE EventBus SHALL 发布 `valuation:tested` 事件（F2-38~F2-40测试完成→payload含计价差异汇总）
15.4 THE F2-44成本分配 SHALL 从F2-41/F2-42/F2-43自动取数（不走EventBus，走allResponses computed链）

### Requirement 16: AI辅助生成

**User Story:** As a 审计助理, I want to 点击AI按钮自动生成测试结论, so that 快速完成专业文本撰写。

#### Acceptance Criteria

16.1 THE AI_Assistant SHALL 在计价测试(F2-38~F2-40)提供"AI生成测试结论"按钮
16.2 THE AI_Assistant SHALL 在跌价测试(F2-47)提供"AI生成跌价评价"按钮
16.3 THE AI_Assistant SHALL 在跌价转回(F2-49)提供"AI生成转回评价"按钮
16.4 THE AI_Assistant SHALL 在关联交易(F2-52)提供"AI生成公允性评价"按钮
16.5 THE AI_Assistant SHALL 在成本分析(F2-41~F2-44)提供"AI生成分析说明"按钮
16.6 THE AI_Assistant SHALL 支持用户编辑+重新生成

### Requirement 17: 双模式切换

**User Story:** As a 审计助理, I want to 支持HTML与OnlyOffice模式切换, so that 复杂场景可降级到Excel编辑。

#### Acceptance Criteria

17.1 THE Dual_Mode SHALL 在每个sheet子组件右上角显示"切换到OnlyOffice"按钮
17.2 WHEN 用户点击切换按钮时, THE 系统 SHALL 切换到OnlyOffice编辑当前sheet
17.3 THE Dual_Mode SHALL OnlyOffice模式隐藏非目标sheet tab
17.4 THE Dual_Mode SHALL 切换回HTML时重新渲染Vue组件并同步数据
17.5 THE Dual_Mode SHALL 记住用户选择（localStorage持久化）
17.6 WHEN OnlyOffice加载失败时, THE 系统 SHALL 自动降级到HTML模式并显示提示

### Requirement 18: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且宽表流畅, so that 28列跌价测试表和94行计价测试表都能流畅操作。

#### Acceptance Criteria

18.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
18.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
18.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
18.4 THE UI SHALL 编制提示details折叠底部
18.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（F2-38计价测试94行/F2-39先进先出75行/F2-40标准成本64行/F2-47跌价测试59行）
18.6 THE Performance SHALL 区段Tab切换debounce（300ms）
18.7 THE Performance SHALL defineAsyncComponent懒加载所有子组件
18.8 THE Performance SHALL 公式计算缓存（相同输入不重复计算）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证扩展公式引擎的正确性。

**P1: NRV公式** — ∀ price, completionCost, sellingExpense, tax ∈ ℝ≥0: calcNRV(price, completionCost, sellingExpense, tax) === price - completionCost - sellingExpense - tax

**P2: 跌价计提公式** — ∀ bookCost, nrv ∈ ℝ≥0: calcImpairmentProvision(bookCost, nrv) === Math.max(0, bookCost - nrv)

**P3: 加权平均单价** — ∀ openAmt, inAmt ∈ ℝ, openQty, inQty ∈ ℝ>0: calcWeightedAvgPrice(openAmt, inAmt, openQty, inQty) === (openAmt+inAmt)/(openQty+inQty)

**P4: 标准成本差异恒等** — ∀ stdPrice, stdQty, actPrice, actQty ∈ ℝ: calcPriceVariance + calcQuantityVariance === calcTotalVariance

**P5: 跌价转回金额约束** — ∀ provision, required, cap ∈ ℝ≥0: calcReversalAmount(provision, required, cap) ≤ cap ∧ calcReversalAmount ≥ 0

**P6: 分配比例合计=100%** — ∀ ratios[]: SUM(calcAllocationRatio(each, total)) === 100% (±浮点误差)

**P7: 公允性差异率公式** — ∀ relatedPrice, comparablePrice ∈ ℝ, comparablePrice≠0: calcFairnessDeviation(relatedPrice, comparablePrice) === (relatedPrice-comparablePrice)/comparablePrice×100

**P8: 超保质期判定幂等** — ∀ ageDays, shelfDays ∈ ℤ≥0: isExpired(ageDays, shelfDays) 结果确定且幂等

**P9: NRV≥0时无需计提** — ∀ bookCost, nrv ∈ ℝ≥0 WHERE nrv ≥ bookCost: calcImpairmentProvision(bookCost, nrv) === 0

**P10: 计价差异可加性** — ∀ priceVar, qtyVar, totalVar: calcTotalVariance(actPrice, actQty, stdPrice, stdQty) === calcPriceVariance(...) + calcQuantityVariance(...)


### Requirement 19: 抽凭引擎集成

**User Story:** As a 审计助理, I want to 在F2-38~F2-40计价测试表的抽样参数区使用抽凭引擎, so that 我能利用平台统一抽样算法科学确定计价测试样本。

#### Acceptance Criteria

19.1 THE F2-38/F2-39/F2-40计价测试表 SHALL 在抽样参数区提供"使用抽凭引擎"按钮（el-button type="primary" icon）
19.2 WHEN 用户点击"使用抽凭引擎"按钮时, THE 系统 SHALL 打开 GtVoucherSamplingEngine 对话框（dialog模式）
19.3 THE GtVoucherSamplingEngine 对话框 SHALL 预填总体金额（从抽样参数区取）和科目代码（存货科目1401~1412）
19.4 WHEN 用户在GtVoucherSamplingEngine中完成抽样并确认时, THE 系统 SHALL 将选中样本自动填入计价测试动态行（品名/期初数量/金额/凭证编号等字段从样本映射）
19.5 THE 抽样参数区 SHALL 自动更新为引擎返回的参数（样本量/抽样方法/置信水平）
19.6 THE 已通过抽凭引擎填入的行 SHALL 显示来源标记（tooltip: "来自抽凭引擎 {algorithm}"）

### Requirement 20: 版本链集成

**User Story:** As a 审计助理, I want to F2计价+跌价底稿自动记录版本快照, so that 我能追溯底稿变更历史并对比差异。

#### Acceptance Criteria

20.1 THE GtF2InventoryValuation 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
20.2 WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
20.3 THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板
20.4 THE GtWpVersionTrail SHALL 显示版本列表（时间/操作人/摘要），支持差异对比
20.5 THE useVersionTrail SHALL 支持手动创建命名快照
20.6 THE 版本快照 SHALL 记录当前allResponses完整JSON + 操作人 + 时间戳
20.7 THE GtF2InventoryValuation 主入口 SHALL provide('openReviewDialog', openReviewDialog)，子组件inject使用

### Requirement 21: 行级OCR集成（F2-47跌价测试）

**User Story:** As a 审计助理, I want to 在F2-47跌价准备测试通过OCR上传采购发票, so that 系统自动识别售价字段填入NRV测算区，减少手工录入。

#### Acceptance Criteria

21.1 THE F2-47跌价准备测试表 SHALL 在NRV测算区段提供📎列（每行附件上传按钮）
21.2 WHEN 用户点击📎上传文件（采购发票/销售合同等）时, THE 系统 SHALL POST /api/workpapers/{wp_id}/f2-valuation/contract-ocr
21.3 THE OCR端点 SHALL 返回extracted_fields（估计售价/品名/规格/数量等）
21.4 THE 系统 SHALL 弹出ElMessageBox.confirm显示识别结果，用户确认后merge到当前行的估计售价/至完工估计成本等字段
21.5 WHEN OCR识别置信度<80%的字段, THE 确认弹窗 SHALL 以橙色高亮提示人工核对
21.6 THE 上传成功后 SHALL 在📎列显示已上传图标，hover可预览附件
