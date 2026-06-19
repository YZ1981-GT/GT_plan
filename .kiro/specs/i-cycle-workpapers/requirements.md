# I 类底稿（无形资产循环）— 需求文档

## 1. 概述

I 类底稿覆盖"实质性程序—无形资产循环"阶段（审计循环代号 I），根据 B50 风险评估结果和 C8（无形资产）+C9（研发）控制测试结论，执行实质性程序。包含 **6 个科目、6 个模板文件、约 40+ 个子底稿 sheet**。

I 类特殊性：I3（商誉）减值测试涉及 DCF 计算，联动 goodwill-impairment-workpaper spec。I6（研发费用）涉及资本化条件判断。

## 2. 现状与差距

| 维度 | 现状 | 说明 |
|------|------|------|
| wp_account_mapping | 少量 I 类条目 | 缺大量子码 |
| _WP_CODE_OVERRIDE | 0 条 | I 类无显式映射 |
| risk_for_cycle | B50→I 就绪 | ✅ |
| control_test_result_for_cycle | C8/C9→I 就绪 | ✅ |

## 3. 术语表

- **无形资产循环系统（Intangible_Asset_System）**：平台中负责 I 类底稿的子系统
- **商誉减值测试（Goodwill_Impairment_Test）**：I3 商誉的年度强制减值测试，涉及 DCF/可收回金额
- **开发支出资本化（Development_Expenditure_Capitalization）**：满足 CAS6 五条件的研发支出资本化处理
- **研发费用加计扣除（R_D_Super_Deduction）**：税法允许额外扣除的研发费用（与 N 类联动）

## 4. I 类底稿分组结构

| 组 | 编号 | 科目 | 模板文件 | 特殊说明 |
|----|------|------|---------|---------|
| I1 | I1/I1A/I1-1~I1-8 | 无形资产累计摊销及减值准备 | 1 xlsx | 含摊销测算 |
| I2 | I2/I2A/I2-1~I2-6 | 开发支出 | 1 xlsx | 资本化条件判断 |
| I3 | I3/I3A/I3-1~I3-6 | 商誉 | 1 xlsx | **DCF 减值测试** |
| I4 | I4/I4A/I4-1~I4-4 | 长期待摊费用 | 1 xlsx | |
| I5 | I5/I5A/I5-1~I5-4 | 其他非流动资产 | 1 xlsx | |
| I6 | I6/I6A/I6-1~I6-8 | 研发费用 | 1 xlsx | 资本化/费用化分类 |

## 5. 各组详细需求

### I1: 无形资产累计摊销及减值准备
**需求：** I1A程序表 + I1-1审定表 + I1-2明细 + I1-3摊销测算 + I1-4减值测试 + I1-5增减变动 + I1-6分析 + I1-7检查 + I1-8调整分录
- I1-3 摊销测算含公式（原值/摊销年限/残值率）→`audit-sheet`
- I1-4 减值测试→`audit-sheet`

### I2: 开发支出
**需求：** I2A程序表 + I2-1审定表 + I2-2明细 + I2-3资本化条件检查 + I2-4转无形资产 + I2-5分析 + I2-6调整分录
- I2-3 资本化条件检查（CAS6 五条件逐项判断）→`d-form-table`

### I3: 商誉（含 DCF 减值测试）
**需求：** I3A程序表 + I3-1审定表 + I3-2明细 + I3-3减值测试概要 + I3-4 DCF计算 + I3-5敏感性分析 + I3-6调整分录
- I3-4 DCF 计算含复杂公式（WACC/CAPM/自由现金流折现/永续增长）→`audit-sheet`
- **联动 goodwill-impairment-workpaper spec**：I3-4 复用 A3-8 DCF 引擎
- I3-5 敏感性分析（折现率±1%/增长率±1% 矩阵）→`audit-sheet`

### I4: 长期待摊费用
**需求：** I4A程序表 + I4-1审定表 + I4-2明细 + I4-3摊销检查 + I4-4调整分录

### I5: 其他非流动资产
**需求：** I5A程序表 + I5-1审定表 + I5-2明细 + I5-3检查 + I5-4调整分录

### I6: 研发费用
**需求：** I6A程序表 + I6-1审定表 + I6-2明细（需从tb_ledger取数） + I6-3资本化/费用化分类 + I6-4研发项目台账 + I6-5分析 + I6-6检查 + I6-7加计扣除测算 + I6-8调整分录
- I6-3 资本化/费用化分类判断→`d-form-table`
- I6-7 加计扣除测算（税法公式）→`audit-sheet`

## 6. 跨模块联动矩阵

| 源 | 目标 | 联动数据 | 方向 |
|----|------|---------|------|
| B23-14 穿行测试（无形资产/开发支出循环） | C8+C9 控制测试 | 设计有效性 | B→C→I ✅ |
| B50 风险 | I{n}A 程序表 | 风险展示 | B→I ✅ |
| C8+C9 控制测试 | I{n}A 程序表 | 控制有效性 | C→I ✅ |
| I{n}-1 审定表 | trial_balance | 审定金额回写 | I→全局 🔴 |
| I3-4 DCF | A3-8 goodwill-impairment | DCF 引擎 | I↔A 🔴 |
| I6-7 加计扣除 | N5 所得税费用 | 研发加计 | I→N 🔴 |
| I2-4 转无形资产 | I1 无形资产 | 转入金额 | I→I 内部 |

## 7. 技术约束

- wp_code 规则：I1~I6 共 6 组（无 I0 函证）
- componentType：摊销/DCF/敏感性→audit-sheet，资本化条件→d-form-table
- 审定表回写正则：`^I\d+-1$`
- I3 商誉 DCF：联动 goodwill-impairment-workpaper spec 的 DCF 引擎

## 8. 分期实施建议

| Phase | 范围 | 说明 |
|-------|------|------|
| P0 | 注册+分类：wp_account_mapping ~40 条 + _WP_CODE_OVERRIDE | 必做 |
| P1 | 程序表：I1A~I6A 共 6 个程序表提取 | 必做 |
| P2 | 审定表+回写：I{n}-1 schema + handler 正则 | 必做 |
| P3 | address_registry 坐标注册 | 必做 |
| P4 | 特殊程序：I3 DCF+I1-3摊销+I2-3资本化条件+I6研发 | 必做 |
| P5* | 联动完善：I3↔A3-8 DCF + I6→N5 加计扣除 | 增强 |
| P6 | 导入导出 + E2E（≥3） | 必做 |

## 9. 跨循环依赖提示

> 📌 **全局交叉索引**：`.kiro/specs/CYCLE-CROSS-REFERENCE.md`

- **前置依赖**：D 类 P0~P2 已完成；goodwill-impairment-workpaper spec（I3 DCF 引擎）
- **B23 穿行编号**：I 对应 B23-14（无形资产/开发支出循环穿行测试）
- **C 类编号**：I 对应 C8（无形资产）+ C9（研发）
- **完整链路**：B23-14 穿行→C8/C9 控制测试→I{n}A 实质性程序表
- **后续被依赖**：I6-7 研发加计扣除→N5 所得税费用（`rd_super_deduction_for_n5` resolver）
- **跨循环联动**：I3 商誉↔G7 长期股权投资减值；I2 开发支出转入→I1 无形资产

## 10. 经验教训应用

| # | 经验 | I 类应对 |
|---|------|---------|
| 1 | DCF 复杂计算→audit-sheet | I3-4/I3-5 用 OnlyOffice |
| 2 | 资本化条件→结构化检查 | I2-3/I6-3 用 d-form-table |
| 3 | 跨循环联动 | I3↔goodwill spec / I6→N5 |
