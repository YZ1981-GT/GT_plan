# Implementation Plan: G7 长期股权投资(子公司组)底稿专属HTML精美组件

## Overview

实现 `g7-long-term-equity-subsidiary` 组件，覆盖7个sheet（G7-7/G7-8/G7-9/G7-10/G7-11/G7-12/G7-18）。按子目录分组(initial/subsequent/disposal/voucher)，sheetName v-if分发，公式引擎8纯函数(含parseNum)，4大集成(版本链/抽凭/OCR/复核)，宽表拆分(G7-18→3区段Tab)，虚拟滚动(G7-18 99行)，导入导出6张表，AI 5 section。

## Tasks

- [x] 1. 公式引擎与数据层基础
  - [x] 1.1 创建 useG7SubFormulaEngine.ts 实现8个纯函数
    - 实现 parseNum / calcSameControlCost / calcNotSameControlCost / calcGoodwill / calcCostMethodIncome / calcSubsequentBalance / calcDisposalGain / isDebitCreditBalanced
    - 每个函数JSDoc标注CAS准则依据
    - _Requirements: 7.1, 3.3, 3.4, 4.2, 4.3, 5.3_

  - [x]* 1.2 编写 Property 1 PBT: 同控初始投资成本
    - **Property 1: calcSameControlCost(netAssets, ratio) === netAssets × ratio**
    - fast-check: fc.float() for netAssets, fc.float({min:0, max:1}) for ratio
    - **Validates: Requirements 3.3**

  - [x]* 1.3 编写 Property 2 PBT: 非同控初始投资成本
    - **Property 2: calcNotSameControlCost(price, fees) === price + fees**
    - fast-check: fc.float({min:0}) for price/fees
    - **Validates: Requirements 3.4**

  - [x]* 1.4 编写 Property 3 PBT: 商誉计算及符号语义
    - **Property 3: calcGoodwill(cost, share) === cost - share；正=商誉，负=营业外收入**
    - 验证符号语义：cost > share → 正, cost < share → 负
    - **Validates: Requirements 3.4, 7.1**

  - [x]* 1.5 编写 Property 4 PBT: 成本法投资收益
    - **Property 4: calcCostMethodIncome(dividend, ratio) === dividend × ratio**
    - **Validates: Requirements 4.2**

  - [x]* 1.6 编写 Property 5 PBT: 成本法期末账面余额
    - **Property 5: calcSubsequentBalance(opening, addition, impairment) === opening + addition - impairment**
    - **Validates: Requirements 4.3**

  - [x]* 1.7 编写 Property 6 PBT: 处置损益
    - **Property 6: calcDisposalGain(price, bookValue, dividend, oci) === price - bookValue - dividend + oci**
    - **Validates: Requirements 5.3**

  - [x]* 1.8 编写 Property 7 PBT: 借贷平衡恒等
    - **Property 7: isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01**
    - fast-check: fc.array(fc.float()) for debits/credits
    - **Validates: Requirements 6.2, 7.1**

  - [x]* 1.9 编写 Property 8 PBT: parseNum健壮性
    - **Property 8: parseNum(null/undefined/NaN/''/空白/'abc') → 0; parseNum(finite number) → 原值**
    - fast-check: fc.oneof(fc.constant(null), fc.constant(undefined), fc.float())
    - **Validates: Requirements 7.1**

  - [x] 1.10 创建 useG7SubFormData.ts composable
    - selfLoad逻辑（bundle内嵌htmlData为null时自调GET render-config）
    - 数据加载/保存/自动重试3次(指数退避)/localStorage暂存
    - _Requirements: 1.4, 7.6_

  - [x] 1.11 创建 useG7SubImportExport.ts composable
    - 6张表(G7-8/G7-9/G7-10/G7-11/G7-12/G7-18)导入导出
    - el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - G7-18按3区段分sheet导出
    - 使用http(axios)不用原生fetch
    - _Requirements: 3.5, 4.4, 5.5, 6.3, 7.3_

  - [x] 1.12 创建 useG7SubDualMode.ts composable
    - HTML ↔ OnlyOffice双模式切换
    - localStorage持久化用户偏好
    - _Requirements: 7.6_

- [x] 2. Checkpoint - 公式引擎与composable层完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 主入口与注册四件套
  - [x] 3.1 创建 GtG7LongTermEquitySubsidiary.vue 主入口
    - sheetName prop + regex提取编码(G7-7~G7-18)
    - v-if分发7个defineAsyncComponent懒加载子组件
    - 未匹配sheetName → OnlyOffice fallback
    - htmlData为null → selfLoad
    - useVersionTrail集成(autoSnapshot)
    - provide('openReviewDialog', openReviewDialog)复核对话
    - _Requirements: 1.1, 1.2, 1.4, 7.2_

  - [x] 3.2 注册四件套(7条wp_code_overrides + htmlRendererRegistry + VALID_COMPONENT_TYPES + RENDERER_DISPATCH)
    - wp_code_overrides.json添加7条G7-7~G7-18映射
    - htmlRendererRegistry注册componentType
    - 后端VALID_COMPONENT_TYPES添加
    - RENDERER_DISPATCH注册render函数
    - _Requirements: 1.3_

- [x] 4. 初始判断G7-7子组件
  - [x] 4.1 创建 initial/G7TabControlJudgment.vue
    - 47行×9列CAS33六要素问卷式决策树
    - 方法论上下文(琥珀色左边线+浅黄背景): 控制三要素定义
    - 蓝色渐变引导区(2列grid, 4步骤)
    - 6个section: (一)权力~(六)综合判断
    - 每行: 序号|判断维度|判断标准(预填)|被投资单位|判断结果(下拉)|判断依据(textarea)|风险标识(下拉)|审计结论|索引(GtIndexChip)
    - 每section标题行右侧: AI按钮 + 复核按钮
    - 底部综合审计结论textarea(AI辅助)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x]* 4.2 编写 G7-7 单元测试
    - 测试六要素全"是"→控制结论推导
    - 测试部分满足→共同控制/重大影响
    - 测试保存时阻断(控制判断结果为空)
    - _Requirements: 2.1, 2.2_

- [x] 5. 同控/非同控初始计量子组件(G7-8/G7-9)
  - [x] 5.1 创建 initial/G7TabSameControlMeasurement.vue (G7-8)
    - 52行×9列: 被投资单位|合并日|合并方式(下拉)|被合并方账面净资产|持股比例|享有份额(公式列)|初始投资成本|支付对价|差额处理(textarea)|审计结论
    - 方法论上下文: CAS20同控合并规则
    - 公式列虚线下划线+cursor:help+tooltip
    - 动态行增删(ElMessageBox.prompt命名)
    - calcSameControlCost实时计算
    - _Requirements: 3.1, 3.3, 3.5_

  - [x] 5.2 创建 initial/G7TabNotSameControlMeasurement.vue (G7-9)
    - 53行×9列: 被投资单位|购买日|合并方式|支付对价|直接费用|初始投资成本(公式)|被购买方净资产FV|享有份额(公式)|商誉(公式)
    - 方法论上下文: CAS20非同控合并规则
    - calcNotSameControlCost + calcGoodwill实时计算
    - 商誉正值=商誉(资产)显示，负值=绿色提示"廉价购买利得"
    - 动态行增删+导入导出
    - _Requirements: 3.2, 3.4, 3.5_

  - [x]* 5.3 编写 G7-8/G7-9 单元测试
    - 测试同控差额计算(对价远超账面→橙色高亮)
    - 测试非同控商誉符号显示逻辑
    - 测试动态行名称唯一性校验
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 6. 后续计量G7-10子组件
  - [x] 6.1 创建 subsequent/G7TabSubsequentMeasurement.vue (G7-10)
    - 48行×9列: 被投资单位|期初账面|本期增加|本期减值|被投资方宣告股利|持股比例|应确认投资收益(公式)|期末账面(公式)|企业期末数|差异(公式)
    - 方法论上下文: 成本法后续计量规则
    - calcCostMethodIncome + calcSubsequentBalance实时计算
    - 动态行增删+导入导出+AI辅助
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x]* 6.2 编写 G7-10 单元测试
    - 测试投资收益=股利×比例
    - 测试期末账面=期初+追加-减值
    - 测试差异=期末账面-企业期末数
    - _Requirements: 4.2, 4.3_

- [x] 7. Checkpoint - 初始+后续计量子组件完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 处置子组件(G7-11/G7-12)
  - [x] 8.1 创建 disposal/G7TabDisposalSingle.vue (G7-11)
    - 47行×14列单表(横向可滚动，固定前2列)
    - 方法论上下文: 非一揽子处置规则(CAS33/CAS2)
    - calcDisposalGain实时计算个别处置损益
    - 合并报表处置损益计算
    - 处置比例>100%前端校验阻断
    - 动态行增删+导入导出+AI辅助
    - _Requirements: 5.1, 5.3, 5.5_

  - [x] 8.2 创建 disposal/G7TabDisposalPackage.vue (G7-12)
    - 54行×14列单表(横向可滚动，固定前2列)
    - 方法论上下文: 一揽子交易处置规则(CAS33解释)
    - 累计对价/累计持股变动公式(SUM of prior)
    - 丧失控制权日统一确认+追溯调整逻辑
    - 一揽子判断依据textarea(必填校验)
    - 动态行增删+导入导出+AI辅助
    - _Requirements: 5.2, 5.4, 5.5_

  - [x]* 8.3 编写 G7-11/G7-12 单元测试
    - 测试个别处置损益公式
    - 测试一揽子累计计算(cumulativePrice/cumulativeShareChange正确累加)
    - 测试处置比例>100%校验
    - 测试一揽子判断依据必填阻断
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 9. 凭证检查G7-18子组件(3区段Tab+虚拟滚动+OCR)
  - [x] 9.1 创建 voucher/G7TabVoucherCheck.vue (G7-18)
    - 99行×19列→3区段Tab实现
    - Tab1(7列): 日期|凭证号|业务内容|对方科目|借方|贷方|📎附件
    - Tab2(7列): 支持性文件|核对1~核对6(checkbox)
    - Tab3(5列): 索引(GtIndexChip)|是否异常|异常说明|风险等级|备注
    - 3个Tab间切换保持行索引同步
    - 虚拟滚动(99行)，降级分页模式(每页30行)
    - 顶部借贷差额汇总(差额≠0红色)
    - isDebitCreditBalanced校验
    - 任一check为false→isAbnormal自动置true
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 9.2 集成抽凭引擎+行级OCR
    - GtVoucherSamplingEngine dialog-mode, account-codes=['1511']
    - @samples-ready → fillVoucherRows填入
    - 📎附件列: 上传→POST /d4/contract-ocr→ElMessageBox确认→mergeOCRResult
    - OCR失败→ElMessage.warning+允许手动填入
    - _Requirements: 6.2, 7.2_

  - [x]* 9.3 编写 G7-18 单元测试
    - 测试异常自动检测逻辑(check1-6任一false→isAbnormal=true)
    - 测试区段Tab行同步(切换Tab后选中行索引不变)
    - 测试借贷平衡汇总(差额≠0红色显示)
    - 测试虚拟滚动降级到分页
    - _Requirements: 6.1, 6.2_

- [x] 10. Checkpoint - 前端7个子组件全部完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 后端服务层
  - [x] 11.1 创建 _g7_long_term_equity_subsidiary.py (render策略)
    - render_g7_long_term_equity_subsidiary函数
    - 返回componentType='g7-long-term-equity-subsidiary'和sheets配置
    - 注册RENDERER_DISPATCH
    - _Requirements: 1.1, 1.3_

  - [x] 11.2 创建 _g7_long_term_equity_subsidiary_service.py (业务逻辑)
    - G7SubsidiaryService类
    - save_control_judgment / save_measurement / validate_formulas
    - 公式验证(后端校验同控/非同控/处置公式)
    - _Requirements: 7.1_

  - [x] 11.3 创建 _g7_long_term_equity_subsidiary_import_export.py (导入导出)
    - 6张表×3端点=18个端点
    - POST export-template / export-data / import-data
    - sheet codes: G7-8/G7-9/G7-10/G7-11/G7-12/G7-18
    - G7-18按3区段分sheet导出
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 7.3_

  - [x] 11.4 创建 _g7_long_term_equity_subsidiary_ai.py (AI生成)
    - POST /api/workpapers/{wp_id}/g7-sub/ai/{section}
    - 5个section: control-judgment-conclusion / initial-measurement-conclusion / subsequent-conclusion / disposal-conclusion / voucher-conclusion
    - _Requirements: 7.4_

  - [x]* 11.5 编写后端PBT测试 (test_g7_sub_formula_pbt.py)
    - hypothesis实现8个属性验证
    - max_examples=5
    - Tag: Feature: g7-long-term-equity-subsidiary, Property {N}
    - **Validates: Requirements 3.3, 3.4, 4.2, 4.3, 5.3, 6.2, 7.1**

  - [x]* 11.6 编写后端单元测试
    - 测试render策略返回正确componentType
    - 测试service公式验证逻辑
    - 测试导入导出格式校验(422错误)
    - _Requirements: 1.1, 7.1, 7.3_

- [x] 12. 集成与联动
  - [x] 12.1 版本链集成 + 复核对话联动
    - 主入口useVersionTrail(wpId) + autoSnapshot
    - provide/inject openReviewDialog
    - 每个子组件section标题栏右侧复核按钮
    - 工具栏"版本历史"按钮→GtWpVersionTrail drawer
    - _Requirements: 7.2_

  - [x] 12.2 AI辅助5个section接入
    - 每个子组件section标题行右侧AI按钮
    - G7-7: control-judgment-conclusion (底部综合+各section)
    - G7-8/G7-9: initial-measurement-conclusion
    - G7-10: subsequent-conclusion
    - G7-11/G7-12: disposal-conclusion
    - G7-18: voucher-conclusion
    - _Requirements: 2.3, 7.4_

  - [x] 12.3 虚拟滚动实现
    - G7-18(99行): 虚拟滚动+降级分页(每页30行)
    - G7-7(47行)/G7-8(52行)/G7-9(53行): 按需虚拟滚动
    - _Requirements: 7.5_

  - [x]* 12.4 编写集成测试
    - 测试render-config端点返回正确sheets配置
    - 测试导入导出18端点(6张表×3)
    - 测试AI 5个section端点
    - 测试selfLoad逻辑(htmlData为null)
    - _Requirements: 1.4, 7.2, 7.3, 7.4_

- [x] 13. Final checkpoint - 全部完成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 前端使用 TypeScript + Vue 3 (Composition API)，后端使用 Python (FastAPI)
- PBT前端用 vitest + fast-check (numRuns: 100)，后端用 pytest + hypothesis (max_examples: 5)
- 公式引擎8个纯函数是PBT核心验证对象，与业务UI解耦
- G7-18宽表19列→3区段Tab是核心交互创新点，需保证行同步
- 4大集成(版本链/抽凭/OCR/复核)遵循D~N循环联动标准
- 控制判断CAS33六要素问卷(G7-7)是本组核心特色，需要方法论预填

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.10", "1.11", "1.12"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4.1", "5.1", "5.2", "6.1"] },
    { "id": 4, "tasks": ["4.2", "5.3", "6.2", "8.1", "8.2"] },
    { "id": 5, "tasks": ["8.3", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3", "11.4"] },
    { "id": 8, "tasks": ["11.5", "11.6", "12.1", "12.2", "12.3"] },
    { "id": 9, "tasks": ["12.4"] }
  ]
}
```
