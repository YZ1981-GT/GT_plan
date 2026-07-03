# Implementation Plan: G6 其他债权投资(ECL组)专属HTML精美组件

## Overview

实现 `g6-other-bond-investment-ecl` 组件，覆盖5个sheet的ECL减值全流程：三阶段划分(G6-11)→减值测算(G6-12)→ECL计量测试(G6-13)→转回核销(G6-14)→凭证检查(G6-15)。采用D~N专属组件标准开发模式：sheetName v-if分发 + defineAsyncComponent懒加载 + 公式引擎纯函数 + 五大集成 + 3张表导入导出 + AI 4 section + 虚拟滚动。

## Tasks

- [ ] 1. 公式引擎与核心纯函数
  - [ ] 1.1 创建 useG6EclFormulaEngine.ts 实现8个纯函数
    - 创建 `frontend/src/composables/useG6EclFormulaEngine.ts`
    - 实现 parseNum / calcImpairmentProvision / calcImpairmentAdjustment / calcAdjustedBalance / calcAdjustedImpairment / calcAdjustedBookValue / determineStage / isDebitCreditBalanced
    - 所有函数纯函数，无副作用，Math.round(x*100)/100精度控制
    - _Requirements: 6.1, 3.2_

  - [ ]* 1.2 Property Test: ECL公式链一致性 (P1)
    - **Property 1: ECL公式链一致性**
    - fast-check验证 ⑨=(①+⑤)-(①×②+⑤×②A+①×(②A-②)) 恒等
    - 生成器: fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    - **Validates: Requirements 3.2, 6.1**

  - [ ]* 1.3 Property Test: 三阶段确定性与Stage3优先级 (P2+P3)
    - **Property 2: 三阶段确定性**
    - **Property 3: Stage3优先级**
    - fast-check验证 determineStage输出∈{Stage1,Stage2,Stage3} + hasCreditImpairment→Stage3
    - **Validates: Requirements 2.3, 6.1**

  - [ ]* 1.4 Property Test: 坏账调整展开式 (P4)
    - **Property 4: 坏账调整展开式**
    - fast-check验证 ⑥=⑤×②A+①×(②A-②) 含负数冲回
    - **Validates: Requirements 3.2, 6.1**

  - [ ]* 1.5 Property Test: 借贷平衡 (P5)
    - **Property 5: 借贷平衡**
    - fast-check验证 |SUM(debits)-SUM(credits)|<0.01 ↔ isDebitCreditBalanced
    - **Validates: Requirements 5.3, 6.1**

  - [ ]* 1.6 Property Test: parseNum健壮性 (P6)
    - **Property 6: parseNum健壮性**
    - fast-check验证 null/undefined/NaN/Infinity/空串→0, 有效数字透传
    - **Validates: Requirements 6.1**

- [ ] 2. Checkpoint - 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 主入口与注册四件套
  - [ ] 3.1 创建主入口 GtG6OtherBondInvestmentEcl.vue
    - 创建 `frontend/src/components/workpaper/GtG6OtherBondInvestmentEcl.vue`
    - sheetName prop + 正则提取编码 + v-if分发5子组件
    - defineAsyncComponent懒加载5个子组件
    - useVersionTrail集成(autoSnapshot) + provide openReviewDialog
    - selfLoad逻辑（htmlData为null时自动加载）
    - 未匹配sheetName → OnlyOffice fallback
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.2_

  - [ ] 3.2 注册四件套（前端+后端）
    - htmlRendererRegistry注册 `g6-other-bond-investment-ecl`
    - wp_code_overrides.json添加5条映射(G6-11~G6-15)
    - VALID_COMPONENT_TYPES添加 `g6-other-bond-investment-ecl`
    - RENDERER_DISPATCH注册 render_g6_other_bond_investment_ecl
    - _Requirements: 1.3_

  - [ ] 3.3 创建后端 render 策略 _g6_other_bond_investment_ecl.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_ecl.py`
    - render_g6_other_bond_investment_ecl函数返回componentType和sheets配置
    - _Requirements: 1.1, 1.4_

- [ ] 4. 数据层 composables
  - [ ] 4.1 创建 useG6EclFormData.ts 数据加载/保存
    - 创建 `frontend/src/composables/useG6EclFormData.ts`
    - selfLoad / save / autoSnapshot联动
    - G6EclContent数据结构：5个sheet数据统一管理
    - _Requirements: 1.4, 6.2_

  - [ ] 4.2 创建 useG6EclDualMode.ts 双模式切换
    - 创建 `frontend/src/composables/useG6EclDualMode.ts`
    - HTML ↔ OnlyOffice切换 + localStorage记忆
    - _Requirements: 6.6_

  - [ ] 4.3 创建 useG6EclImportExport.ts 导入导出
    - 创建 `frontend/src/composables/useG6EclImportExport.ts`
    - 3张表(G6-12/G6-14/G6-15)的导出模板/导出数据/导入数据
    - el-dropdown"导入导出▾"统一交互
    - _Requirements: 6.3, 3.4, 5.4_

  - [ ] 4.4 创建后端导入导出端点 _g6_other_bond_investment_ecl_import_export.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_ecl_import_export.py`
    - POST export-template / export-data / import-data 三端点
    - sheet参数: G6-12(2区段分sheet导出) / G6-14 / G6-15(3区段分sheet导出)
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 6.3_

- [ ] 5. G6-11 三阶段划分（列式转置）
  - [ ] 5.1 创建 useG6EclStageClassification.ts
    - 创建 `frontend/src/composables/useG6EclStageClassification.ts`
    - 列式→行式转换(transposeToRows): 16384列智能解析仅取有数据列
    - Stage判定逻辑(调用determineStage) + 一致性校验
    - 不一致时红色高亮+强制差异说明
    - 底部汇总(S1/S2/S3数量+不一致数)
    - 动态增删(ElMessageBox.prompt命名) + 展开/折叠
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 5.2 创建 G6TabStageClassification.vue
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-ecl/impairment/G6TabStageClassification.vue`
    - 行式视图表格：投资项目|信用风险显著增加|较低信用风险|已发生信用减值|企业划分阶段(下拉)|审计判断阶段(下拉)|是否一致(公式)|差异说明|索引
    - 虚拟滚动(61行) + GtIndexChip
    - 展开/折叠详情 + 底部汇总
    - 方法论上下文(琥珀色) + AI按钮(stage-conclusion)
    - 复核按钮(inject openReviewDialog)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.5_

  - [ ]* 5.3 Property Test: 列式转置数据完整性 (P6)
    - **Property 6: 列式转置数据完整性**
    - fast-check验证有效列数=输出行数 + investProject对应原始列头
    - **Validates: Requirements 2.1, 2.6**

- [ ] 6. G6-12 减值准备测算（22列→2区段Tab）
  - [ ] 6.1 创建 useG6EclImpairmentCalc.ts
    - 创建 `frontend/src/composables/useG6EclImpairmentCalc.ts`
    - ECL公式链自动计算(watch触发): ③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧
    - Stage分组(stage1/stage2/stage3) + 小计/合计
    - 行同步(Tab切换selectedRowIndex保持)
    - 动态行增删 + 导入导出调用
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 6.2 创建 G6TabImpairmentCalc.vue
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-ecl/impairment/G6TabImpairmentCalc.vue`
    - 2区段Tab: Tab1未审+调整(12列) / Tab2审定数(10列)
    - Tab切换不销毁表格实例，仅切换columns computed
    - 公式列虚线下划线+cursor:help+tooltip公式来源
    - Stage分组渲染+小计行
    - 方法论上下文 + AI按钮(impairment-conclusion) + 复核按钮
    - GtIndexChip + 导入导出dropdown
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.3_

- [ ] 7. Checkpoint - 核心sheet验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. G6-13 ECL计量测试（49行5section）
  - [ ] 8.1 创建 G6TabEclMeasurement.vue
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-ecl/impairment/G6TabEclMeasurement.vue`
    - 49行×10列问卷式表格，5个section: PD/LGD/EAD/折现率/前瞻性信息
    - 列: 序号|检查区域|检查项目|审计要求|企业参数(textarea)|是否合理(下拉)|审计结论(textarea)|风险等级|索引|备注
    - 顶部方法论上下文(ECL三要素定义)
    - 每个section标题行右侧AI按钮(ecl-measurement-conclusion)
    - 复核按钮 + GtIndexChip
    - _Requirements: 4.1, 4.2, 4.3_

- [ ] 9. G6-14 转回核销 + G6-15 凭证检查
  - [ ] 9.1 创建 G6TabReversalWriteOff.vue
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-ecl/impairment/G6TabReversalWriteOff.vue`
    - 42行×8列: 序号|投资项目|转回/核销类型(下拉)|金额|原因(textarea)|审批程序|合理性结论(下拉)|索引
    - 动态行增删 + 导入导出dropdown
    - AI按钮 + 复核按钮 + GtIndexChip
    - _Requirements: 5.1, 5.4_

  - [ ] 9.2 创建 useG6EclVoucherCheck.ts
    - 创建 `frontend/src/composables/useG6EclVoucherCheck.ts`
    - OCR识别逻辑(POST /d4/contract-ocr → ElMessageBox确认 → 字段填入)
    - 异常自动判定(7项核对任一✗→isAbnormal=true)
    - 借贷平衡校验(调用isDebitCreditBalanced)
    - 抽凭引擎样本填入
    - _Requirements: 5.2, 5.3_

  - [ ] 9.3 创建 G6TabVoucherCheck.vue
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue`
    - 22列→3区段Tab: Tab1凭证基础(8列) / Tab2核对内容(8列) / Tab3结论(6列)
    - Tab切换行同步 + 虚拟滚动(100行)
    - 📎附件列: 上传→OCR识别→确认弹窗→填入
    - GtVoucherSamplingEngine dialog集成(抽凭引擎)
    - 借贷平衡实时校验: 顶部显示借方合计/贷方合计/差额 + 不平衡红色banner
    - AI按钮(voucher-conclusion) + 复核按钮 + 导入导出dropdown + GtIndexChip
    - _Requirements: 5.2, 5.3, 5.4, 6.2, 6.5_

- [ ] 10. AI端点与集成联动
  - [ ] 10.1 创建后端AI端点 _g6_other_bond_investment_ecl_ai.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_ecl_ai.py`
    - POST /api/workpapers/{wp_id}/g6-ecl/ai/{section}
    - 4个section: stage-conclusion / impairment-conclusion / ecl-measurement-conclusion / voucher-conclusion
    - 每个section提取对应数据上下文 → LLM生成结论
    - _Requirements: 6.4_

  - [ ] 10.2 集成联动最终整合
    - 版本链: 主入口save→autoSnapshot确认工作
    - 抽凭引擎: G6-15 GtVoucherSamplingEngine dialog→fillVoucherSamples
    - OCR: G6-15 Tab1 📎列handleAttachmentUpload完整链路
    - 复核对话: provide/inject openReviewDialog确认所有子组件可用
    - _Requirements: 6.2_

- [ ] 11. 单元测试与集成测试
  - [ ]* 11.1 公式引擎单元测试
    - G6-12 ECL公式链端到端（①=1000万,②=1%,⑤=200万,②A=2%）
    - parseNum边界值(null/undefined/NaN/Infinity/空串/含空格数字)
    - determineStage所有组合
    - isDebitCreditBalanced正常/边界
    - _Requirements: 6.1_

  - [ ]* 11.2 组件逻辑单元测试
    - G6-11列式转置解析(空列/合并单元格/全空列过滤)
    - G6-13 section结构完整性(5个section均存在)
    - G6-14转回类型校验(仅允许转回/核销/收回)
    - G6-15凭证异常自动判定(7项核对全通过=正常,任一✗=异常)
    - _Requirements: 2.1, 4.1, 5.1, 5.3_

  - [ ]* 11.3 集成测试
    - selfLoad: render-config端点返回正确结构
    - 导入导出: 3张表×3端点 roundtrip
    - AI接口: 4个section各返回合理文本
    - 版本链: save触发autoSnapshot
    - _Requirements: 1.4, 6.2, 6.3, 6.4_

- [ ] 12. Final Checkpoint - 全部验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (6 PBT in design)
- 公式引擎8纯函数是核心，必须先实现并通过PBT验证后再构建UI
- G6-11列式转置复用G4-9/G5-9方案
- G6-12/G6-15宽表采用区段Tab拆分（Tab切换不销毁实例，行同步）
- 虚拟滚动阈值>50行：G6-11(61行) + G6-15(100行)
- 五大集成：版本链✅ 抽凭✅(G6-15) OCR✅(G6-15) 复核✅ 截止❌ 附注EventBus❌

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.3", "4.4"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "3.1", "3.2", "4.1", "4.2"] },
    { "id": 2, "tasks": ["4.3", "5.1", "6.1", "9.2"] },
    { "id": 3, "tasks": ["5.2", "5.3", "6.2", "8.1", "9.1", "9.3"] },
    { "id": 4, "tasks": ["10.1", "10.2"] },
    { "id": 5, "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```
