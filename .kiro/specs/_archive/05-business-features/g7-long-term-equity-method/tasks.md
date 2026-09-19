# Implementation Plan: G7 长期股权投资(权益法组)底稿专属HTML精美组件

## Overview

实现 `g7-long-term-equity-method` 组件，覆盖权益法核算全流程8个sheet（G7-4~G7-6/G7-13~G7-17）。采用 sheetName v-if 分发架构，子目录 info/calculation/impairment 分组。公式引擎9纯函数+parseNum，4处宽表区段Tab拆分，3处虚拟滚动，7张表导入导出，4个AI section，版本链+复核两大集成。

## Tasks

- [x] 1. 项目结构 + 注册四件套 + 公式引擎
  - [x] 1.1 创建目录结构和注册四件套
    - 创建 `g7-long-term-equity-method/` 目录（info/ + calculation/ + impairment/）
    - 在 `wp_code_overrides.json` 添加8条 sheetName→componentType 映射
    - 在 `htmlRendererRegistry` 注册 `g7-long-term-equity-method` 入口
    - 在 `VALID_COMPONENT_TYPES` 添加 `g7-long-term-equity-method`
    - 创建后端 `_g7_long_term_equity_method.py`（render策略函数 + RENDERER_DISPATCH注册）
    - _Requirements: 1.1, 1.3_

  - [x] 1.2 实现公式引擎 useG7EquityMethodFormulaEngine.ts（9纯函数+parseNum）
    - 实现 `parseNum`：null/undefined/NaN/空字符串→0，有效数字透传
    - 实现 `calcInvestmentCost`：支付对价+直接费用
    - 实现 `calcShareOfNetAssets`：净资产FV×持股比例
    - 实现 `calcGoodwill`：初始成本-享有份额
    - 实现 `calcAdjustedNetProfit`：报告净利润-内部交易-FV折旧+政策+其他
    - 实现 `calcEquityShare`：值×持股比例（通用乘法）
    - 实现 `calcEquityMethodBalance`：期初+收益+OCI+其他权益-股利
    - 实现 `calcUnrealizedProfit`：交易金额×毛利率
    - 实现 `calcEliminationAmount`：顺流=全额/逆流=×比例
    - 实现 `calcImpairmentAmount`：MAX(0, 账面-可收回)
    - 所有函数使用 `Math.round(... * 100) / 100` 保留2位小数
    - _Requirements: 7.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.5, 5.6, 5.7, 6.2, 6.3, 6.6_

  - [x]* 1.3 PBT: Property 1 — 初始投资成本公式
    - **Property 1: calcInvestmentCost(consideration, directCosts) === round(consideration + directCosts, 2)**
    - 使用 fast-check amountArb 生成器
    - **Validates: Requirements 4.2**

  - [x]* 1.4 PBT: Property 2 — 享有净资产份额公式
    - **Property 2: calcShareOfNetAssets(netAssetFV, ratio) === round(netAssetFV × ratio, 2)**
    - 使用 amountArb + ratioArb
    - **Validates: Requirements 4.3**

  - [x]* 1.5 PBT: Property 3 — 商誉/营业外收入差额
    - **Property 3: calcGoodwill(initialCost, shareOfNetAssets) === round(initialCost - shareOfNetAssets, 2)**
    - 验证正值=商誉性质、负值=营业外收入性质
    - **Validates: Requirements 4.4**

  - [x]* 1.6 PBT: Property 4 — 调整后净利润公式
    - **Property 4: calcAdjustedNetProfit(r, i, f, p, o) === round(r - i - f + p + o, 2)**
    - 5个 amountArb 参数
    - **Validates: Requirements 5.2**

  - [x]* 1.7 PBT: Property 5 — 持股比例份额通用乘法
    - **Property 5: calcEquityShare(value, ratio) === round(value × ratio, 2)**
    - 适用投资收益/OCI/其他权益三场景
    - **Validates: Requirements 5.3, 5.5, 5.6**

  - [x]* 1.8 PBT: Property 6 — 权益法余额递推
    - **Property 6: calcEquityMethodBalance(o, i, oci, eq, d) === round(o + i + oci + eq - d, 2)**
    - **Validates: Requirements 5.7**

  - [x]* 1.9 PBT: Property 7 — 内部交易抵销顺流/逆流
    - **Property 7: 顺流=round(profit, 2)全额; 逆流=round(profit×ratio, 2)按份额**
    - 使用 directionArb + amountArb + ratioArb
    - **Validates: Requirements 6.3**

  - [x]* 1.10 PBT: Property 8 — 减值非负+MAX语义
    - **Property 8: calcImpairmentAmount(bv, ra) === round(MAX(0, bv-ra), 2) 且 ≥ 0**
    - **Validates: Requirements 6.6**

  - [x]* 1.11 PBT: Property 9 — parseNum健壮性
    - **Property 9: 无效输入→0; 有效finite数字→原值透传**
    - 使用 invalidArb + finiteArb
    - **Validates: Requirements 7.1**

- [x] 2. Checkpoint - 公式引擎+PBT验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 主入口 + 数据层 composable
  - [x] 3.1 实现主入口 GtG7LongTermEquityMethod.vue（sheetName v-if分发）
    - 正则提取 sheetName 中的编码(G7-4/G7-5/.../G7-17)
    - defineAsyncComponent 懒加载8个子组件
    - 未匹配编码→OnlyOffice fallback
    - htmlData为null时selfLoad逻辑
    - 版本链集成：`useVersionTrail(wpId)` + `autoSnapshot`
    - 复核集成：`provide('openReviewDialog', openReviewDialog)`
    - _Requirements: 1.1, 1.2, 1.4, 7.2_

  - [x] 3.2 实现 useG7EquityMethodFormData.ts（数据加载/保存/selfLoad）
    - `loadData(wpId, sheetCode)` → GET render-config → 解析 htmlData
    - `saveData(wpId, sheetCode, data)` → POST 保存 + autoSnapshot
    - selfLoad逻辑（bundle内嵌场景 htmlData 为 null）
    - 保存失败自动重试3次(指数退避)+localStorage暂存
    - _Requirements: 1.4, 7.2_

  - [x] 3.3 实现 useG7EquityMethodDualMode.ts（HTML↔OnlyOffice双模式切换）
    - localStorage 记住用户偏好
    - 模式切换不丢失当前编辑数据
    - _Requirements: 7.6_

- [x] 4. Info 子组件组（G7-4/G7-5/G7-6）
  - [x] 4.1 实现 G7TabBasicInfo.vue — G7-4 被投资单位基本信息（25列→2区段Tab）
    - Tab1 工商信息(12列)：含控制类型下拉、持股/投票权比例输入
    - Tab2 股权结构+管理层(13列)：含textarea重大影响判断依据
    - 行同步：Tab切换保持当前行索引
    - 动态行增删：ElMessageBox.prompt 输入被投资单位名称（名称唯一性校验）
    - _Requirements: 2.1, 2.2_

  - [x] 4.2 实现 G7TabFinancialInfo.vue — G7-5 被投资单位财务信息（57行虚拟滚动）
    - 57行×10列，按被投资单位分组
    - 虚拟滚动（57行阈值）
    - 动态行增删
    - 变动额=本年-上年（自动计算）、变动率=变动/上年(上年=0→null)
    - _Requirements: 3.1, 3.3, 7.5_

  - [x] 4.3 实现 G7TabAccountingPolicy.vue — G7-6 会计政策一致性（31行×7列问卷式）
    - 一致性下拉(一致/不一致/不适用)
    - 调整金额+调整说明
    - 保存时校验：一致性未选择则阻断提示
    - 动态行增删
    - _Requirements: 3.2, 3.4_

- [x] 5. Checkpoint - Info子组件完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Calculation 子组件组（G7-13/G7-14/G7-15，最核心）
  - [x] 6.1 实现 G7TabInvestmentCostTest.vue — G7-13 投资成本测试（68行×17列→2区段Tab+虚拟滚动）
    - 方法论上下文区域（琥珀色左边线+浅黄背景：CAS2投资成本判断规则）
    - Tab1 初始计量(9列)：初始成本(公式)=calcInvestmentCost / 享有份额(公式)=calcShareOfNetAssets / 差额(公式)=calcGoodwill
    - Tab2 商誉计算+调整(8列)：差额性质自动判断（正=商誉绿色/负=营业外蓝色）
    - 68行虚拟滚动 + 行同步 + 动态行增删
    - 底部审计结论textarea(AI辅助 cost-test-conclusion) + details编制提示折叠
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.4, 7.5_

  - [x] 6.2 实现 G7TabEquityMethodCalc.vue — G7-14 权益法测算表（54行×20列→2区段Tab+虚拟滚动，★最核心）
    - 蓝色渐变引导区（5步骤指引,2列grid）
    - 方法论上下文区域（琥珀色左边线+浅黄背景：权益法核算公式）
    - Tab1 净利润调整(10列)：调整后净利润(公式)=calcAdjustedNetProfit / 享有份额(公式)=calcEquityShare
    - Tab2 权益法计算(10列)：收益差异(公式)=享有-确认 / OCI份额(公式)=calcEquityShare / 其他权益份额(公式) / 期末余额(公式)=calcEquityMethodBalance
    - |收益差异|>重要性水平 → 红色高亮
    - 54行虚拟滚动 + 按被投资单位分组 + 行同步 + 动态行增删
    - 底部审计结论textarea(AI辅助 equity-method-conclusion) + details编制提示折叠
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 7.4, 7.5_

  - [x] 6.3 实现 G7TabInternalTransaction.vue — G7-15 内部交易抵销（41行×14列）
    - 方法论上下文区域（琥珀色左边线+浅黄背景：顺流/逆流抵销规则）
    - 交易类型下拉(顺流/逆流)
    - 未实现利润(公式)=calcUnrealizedProfit（或支持直接填写覆盖）
    - 应抵销金额(公式)=calcEliminationAmount（根据方向差异化）
    - 本年变动=应抵销-上年
    - 顺流/逆流未选时应抵销列显示"—"
    - 动态行增删
    - 底部审计结论textarea(AI辅助 internal-transaction-conclusion) + details编制提示折叠
    - _Requirements: 6.1, 6.2, 6.3, 7.4_

  - [x]* 6.4 写单元测试：顺流/逆流差异化逻辑 + 重要性水平高亮 + 区段Tab行同步
    - 验证 calcEliminationAmount 对两种方向的不同计算结果
    - 验证 |incomeDifference|>materialityLevel 时触发红色高亮
    - 验证 Tab 切换后行索引保持不变
    - _Requirements: 5.8, 6.3_

- [x] 7. Checkpoint - Calculation子组件完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Impairment 子组件组（G7-16/G7-17）
  - [x] 8.1 实现 G7TabUnrecognizedLoss.vue — G7-16 未确认损失（40行×17列→2区段Tab）
    - 方法论上下文区域（琥珀色左边线+浅黄背景：CAS2第44条超额亏损抵减顺序）
    - Tab1 长期权益分析(9列)：合计(公式)=各项之和 / 超额亏损(公式)=MAX(0, 累计亏损-合计)
    - Tab2 超额亏损分配(8列)：未确认损失(公式)=超额-各项冲减
    - 超额亏损为0时Tab2全部禁用
    - 行同步 + 动态行增删
    - _Requirements: 6.4, 6.7_

  - [x] 8.2 实现 G7TabImpairmentTest.vue — G7-17 减值测试（33行×9列）
    - 方法论上下文区域（琥珀色左边线+浅黄背景：CAS8减值判断标准）
    - 减值金额(公式)=calcImpairmentAmount
    - 减值迹象=否时：可收回金额/FV-处置/使用价值三列灰色禁用
    - 减值迹象=是时：三列高亮必填
    - 减值金额>0时红色标记
    - 动态行增删
    - 底部审计结论textarea(AI辅助 impairment-conclusion) + details编制提示折叠
    - _Requirements: 6.5, 6.6, 6.7, 7.4_

  - [x]* 8.3 写单元测试：减值非负性 + G7-16超额亏损逻辑 + 减值迹象联动
    - 验证 calcImpairmentAmount 永远≥0
    - 验证 累计亏损≤合计权益时超额=0，Tab2禁用
    - 验证 减值迹象切换→条件必填联动
    - _Requirements: 6.4, 6.5, 6.6_

- [x] 9. 导入导出 + AI辅助
  - [x] 9.1 实现后端导入导出 _g7_long_term_equity_method_import_export.py（7张表×3端点=21端点）
    - POST export-template / export-data / import-data（multipart/form-data）
    - sheet codes: G7-4/G7-5/G7-13/G7-14/G7-15/G7-16/G7-17
    - 宽表按区段分sheet导出：G7-4(2sheet) / G7-13(2sheet) / G7-14(2sheet) / G7-16(2sheet)
    - 中文文件名RFC5987编码（StreamingResponse）
    - 导入格式不匹配→422+具体列错误
    - _Requirements: 7.3_

  - [x] 9.2 实现前端 useG7EquityMethodImportExport.ts composable
    - el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - 使用 axios（http）实现（不用原生fetch，避免缺Authorization header）
    - 7张表共用composable，sheet参数区分
    - _Requirements: 7.3_

  - [x] 9.3 实现后端AI辅助 _g7_long_term_equity_method_ai.py（4 section）
    - POST /api/workpapers/{wp_id}/g7-equity-method/ai/{section}
    - section: cost-test-conclusion / equity-method-conclusion / internal-transaction-conclusion / impairment-conclusion
    - 基于底稿当前数据生成审计结论
    - _Requirements: 7.4_

  - [x]* 9.4 写单元测试：导入导出宽表分sheet + AI端点参数校验
    - 验证G7-4/G7-13/G7-14/G7-16导出各生成2sheet
    - 验证invalid section返回400
    - _Requirements: 7.3, 7.4_

- [x] 10. 集成联动 + UI规范收尾
  - [x] 10.1 版本链集成 + 复核对话注入 + 双模式工具栏
    - 主入口 useVersionTrail + autoSnapshot 触发
    - 工具栏：版本历史按钮 → GtWpVersionTrail drawer
    - provide/inject openReviewDialog → 各子组件 section 标题栏右侧复核按钮
    - 双模式切换按钮（HTML↔OnlyOffice）
    - _Requirements: 7.2, 7.6_

  - [x] 10.2 UI规范统一收尾：表格字体13px + 公式列虚线下划线 + 审计结论el-card + 编制提示details折叠
    - 公式列：虚线下划线 + cursor:help + tooltip显示公式来源
    - 列宽 min-width 自适应
    - 审计说明/结论 el-card 包裹
    - 编制提示 details 折叠底部
    - AI+复核按钮右对齐在section标题同行
    - _Requirements: 7.6_

  - [x]* 10.3 后端PBT验证：hypothesis测试公式引擎Python端
    - test_g7_long_term_equity_method_pbt.py
    - 对应9个Property，max_examples=5
    - _Requirements: 7.1_

- [x] 11. Final checkpoint - 全部功能完成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (9 properties via fast-check)
- Unit tests validate specific examples and edge cases
- 公式引擎为纯函数无副作用，支持独立PBT验证
- 虚拟滚动3处：G7-5(57行) / G7-13(68行) / G7-14(54行)
- 宽表拆分4处：G7-4(25列→2Tab) / G7-13(17列→2Tab) / G7-14(20列→2Tab) / G7-16(17列→2Tab)
- 两大集成：版本链(useVersionTrail) + 复核对话(provide/inject)
- 导入导出7张表（G7-6无需导入导出因固定问卷行）

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "3.1", "3.2", "3.3"] },
    { "id": 2, "tasks": ["4.1", "4.2", "4.3", "9.1"] },
    { "id": 3, "tasks": ["6.1", "6.2", "6.3", "9.3"] },
    { "id": 4, "tasks": ["6.4", "8.1", "8.2", "9.2"] },
    { "id": 5, "tasks": ["8.3", "9.4", "10.1"] },
    { "id": 6, "tasks": ["10.2", "10.3"] }
  ]
}
```
