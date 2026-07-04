# Implementation Plan: G4 债权投资底稿(ECL组)专属HTML精美组件

## Overview

将G4债权投资(ECL组)7个sheet升级为专属HTML组件`g4-bond-investment-ecl`。按D~N底稿开发标准8步组织：注册四件套→公式引擎+PBT→主入口分发→G4-9三阶段→G4-10减值测算→G4-11/G4-12→G4-13凭证→参考材料→导入导出+AI→UI精调集成测试。

## Tasks

- [ ] 1. 注册四件套 + 后端render策略
  - [x] 1.1 注册componentType与wp_code映射
    - 在 `wp_code_overrides.json` 中新增7条映射（G4-9/G4-10/G4-11/G4-12/G4-13/参考-减值指引/参考-PD折算 → g4-bond-investment-ecl）
    - 在 `VALID_COMPONENT_TYPES` 中注册 'g4-bond-investment-ecl'
    - 在 `RENDERER_DISPATCH` 中注册 render_g4_bond_investment_ecl 策略函数
    - 在 `htmlRendererRegistry` 中注册前端异步组件映射
    - _Requirements: 1.1, 1.3, 1.4, 1.5_

  - [ ] 1.2 实现后端render策略 `_g4_bond_investment_ecl.py`
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_ecl.py`
    - 实现 `render_g4_bond_investment_ecl(wp_id, config)` 返回 componentType + sheets配置
    - 返回7个sheet的html_data结构（G4-9~G4-13 + 2参考材料）
    - _Requirements: 1.1, 1.6_

- [ ] 2. 公式引擎 useG4EclFormulaEngine.ts（15纯函数）
  - [ ] 2.1 实现公式引擎核心纯函数
    - 创建 `frontend/src/components/workpaper/composables/useG4EclFormulaEngine.ts`
    - 实现 parseNum（输入清洗：null/undefined/NaN/空串→0）
    - 实现 calcImpairmentProvision（③=①×②）
    - 实现 calcBookValue（④=①-③）
    - 实现 calcImpairmentAdjustment（⑥=⑤×②A+①×(②A-②)，可负）
    - 实现 calcAdjustedBalance（⑦=①+⑤）
    - 实现 calcAdjustedImpairment（⑧=③+⑥）
    - 实现 calcAdjustedBookValue（⑨=⑦-⑧）
    - 实现 determineStage（三阶段判定，creditImpaired优先级最高）
    - 实现 isStageConsistent（阶段一致性）
    - 实现 isReversalValid（转回≤累计计提）
    - 实现 isDebitCreditBalanced（|差额|<0.01）
    - 实现 calcDebitCreditDifference（借-贷差额）
    - 实现 isVoucherNormal（6项全true→正常）
    - 实现 calcSumColumn（数组求和，空数组→0）
    - 所有函数为纯函数，无Vue响应式依赖，结果保留2位小数
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15_

  - [ ]* 2.2 PBT: Property 1 — 减值准备公式
    - **Property 1: 减值准备公式**
    - fc.assert: ∀ bookBalance≥0, rate∈[0,1]: calcImpairmentProvision(b,r) === round(b×r, 2)
    - **Validates: Requirements 8.1, 3.2**

  - [ ]* 2.3 PBT: Property 2 — 账面价值公式
    - **Property 2: 账面价值恒等**
    - fc.assert: ∀ bookBalance≥0, impairment≤bookBalance: calcBookValue(b,i) === round(b-i, 2)
    - **Validates: Requirements 8.2, 3.3**

  - [ ]* 2.4 PBT: Property 3 — 审计调整公式链一致性
    - **Property 3: 审计调整公式链一致性**
    - fc.assert: ∀ ①,②,⑤,②A: 整条链 calcAdjustedBookValue(⑦,⑧) === round((①+⑤)-(①×②+⑤×②A+①×(②A-②)), 2)
    - **Validates: Requirements 8.3, 8.4, 8.5, 8.6, 3.4, 3.5, 3.6, 3.7**

  - [ ]* 2.5 PBT: Property 4 — 减值准备调整公式展开
    - **Property 4: 减值准备调整公式展开**
    - fc.assert: ∀ balanceAdj, adjRate, origBalance, origRate: calcImpairmentAdjustment(...) === round(balanceAdj×adjRate + origBalance×(adjRate-origRate), 2)
    - **Validates: Requirements 8.3, 3.4**

  - [ ]* 2.6 PBT: Property 5 — 三阶段划分确定性与优先级
    - **Property 5: 三阶段划分确定性与优先级**
    - fc.assert: ∀ boolean³: creditImpaired→Stage3; (ratingDeclined∨overdue30)→Stage2; else→Stage1
    - **Validates: Requirements 8.7, 2.2**

  - [ ]* 2.7 PBT: Property 6 — Stage1必要条件
    - **Property 6: Stage1必要条件**
    - fc.assert: determineStage(...)===Stage1 → 三项均false
    - **Validates: Requirements 8.7, 2.2**

  - [ ]* 2.8 PBT: Property 7 — 阶段一致性判定
    - **Property 7: 阶段一致性判定**
    - fc.assert: ∀ s1,s2∈{Stage1,Stage2,Stage3}: isStageConsistent(s1,s2) ↔ (s1===s2)
    - **Validates: Requirements 8.8, 2.3**

  - [ ]* 2.9 PBT: Property 8 — 转回有效性
    - **Property 8: 转回有效性**
    - fc.assert: ∀ reversal≥0, accumulated≥0: isReversalValid(r,a) ↔ (r≤a)
    - **Validates: Requirements 8.9, 5.2**

  - [ ]* 2.10 PBT: Property 9 — 借贷平衡恒等
    - **Property 9: 借贷平衡恒等**
    - fc.assert: isDebitCreditBalanced(d,c) ↔ |SUM(d)-SUM(c)|<0.01，且 calcDebitCreditDifference === round(SUM(d)-SUM(c),2)
    - **Validates: Requirements 8.10, 8.11, 6.6**

  - [ ]* 2.11 PBT: Property 10 — 凭证异常判定完备性
    - **Property 10: 凭证异常判定完备性**
    - fc.assert: ∀ checks∈boolean[6]: isVoucherNormal(checks) ↔ all(checks)
    - **Validates: Requirements 8.12, 6.7**

  - [ ]* 2.12 PBT: Property 11 — 合计行加法交换律
    - **Property 11: 合计行加法交换律**
    - fc.assert: ∀ values[]: calcSumColumn(values) === calcSumColumn(shuffle(values))
    - **Validates: Requirements 8.13**

  - [ ]* 2.13 PBT: Property 12 — parseNum健壮性
    - **Property 12: parseNum健壮性**
    - fc.assert: parseNum(null/undefined/''/NaN)===0; ∀ finite n: parseNum(n)===n
    - **Validates: Requirements 8.14**

  - [ ]* 2.14 PBT: Property 13 — 审定减值准备组合恒等
    - **Property 13: 审定减值准备=未审+调整**
    - fc.assert: calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②)) === round(①×②+⑤×②A+①×(②A-②), 2)
    - **Validates: Requirements 8.5, 8.3**

  - [ ]* 2.15 PBT: Property 14 — 审定账面余额=原值+调整
    - **Property 14: 审定账面余额=原值+调整**
    - fc.assert: ∀ origBalance, balanceAdj: calcAdjustedBalance(o,b) === round(o+b, 2)
    - **Validates: Requirements 8.4, 3.5**

- [ ] 3. Checkpoint — 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 主入口 GtG4BondInvestmentEcl.vue（sheetName v-if分发）
  - [ ] 4.1 创建主入口组件 + selfLoad逻辑
    - 创建 `frontend/src/components/workpaper/GtG4BondInvestmentEcl.vue`
    - 接收 props: htmlData/sheetName/wpId/projectId/readonly
    - sheetName正则提取编码 → v-if分发到7个子组件
    - defineAsyncComponent懒加载所有子组件
    - 未匹配编码→OnlyOffice fallback
    - selfLoad模式：htmlData为null时调用render-config获取数据
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 11.7_

  - [ ] 4.2 集成版本链 + 复核对话provide
    - 集成 useVersionTrail（autoSnapshot on save + 版本历史按钮）
    - provide('openReviewDialog', openReviewDialog) 供子组件inject
    - _Requirements: 9.1, 9.4_

  - [ ] 4.3 创建 useG4EclFormData.ts 数据加载/保存composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclFormData.ts`
    - 实现数据加载（从render-config解析）、保存（POST content JSON）、selfLoad模式
    - 定义 G4EclContent 顶层数据接口
    - _Requirements: 1.6_

  - [ ] 4.4 创建 useG4EclDualMode.ts 双模式切换composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclDualMode.ts`
    - HTML↔OnlyOffice切换 + localStorage持久化
    - _Requirements: 10.6_

- [ ] 5. G4-9 三阶段划分（Stage判定 + 一致性比对 + 61行虚拟滚动）
  - [ ] 5.1 实现 G4TabStageClassification.vue 组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/impairment/G4TabStageClassification.vue`
    - **列式转置结构**：源模板投资项目为列，前端转换为行式交互视图
    - 三区块检查：(一)信用风险显著增加(13项) / (二)较低信用风险(3项) / (三)已发生信用减值(8项)
    - 行式汇总视图：投资项目|显著增加判定|较低信用风险|已发生减值|企业阶段(下拉)|审计阶段(下拉)|一致性(公式)|差异说明|索引
    - 支持展开/折叠详情模式（展开显示逐项检查明细）
    - 顶部方法论上下文（琥珀色左边线+浅黄背景：Stage1/2/3判定标准）
    - 底部汇总区（各Stage数量+不一致项数）+ 审计结论textarea + AI按钮 + 编制提示折叠
    - 不一致行红色高亮 + 强制差异说明
    - 动态投资项目增删（ElMessageBox.prompt输入名称）
    - 16384列智能解析：仅取有数据的投资列
    - _Requirements: 2.1~2.13, 11.1, 11.5, 11.6, 11.10_

  - [ ] 5.2 实现 useG4EclStageClassification.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclStageClassification.ts`
    - **列式→行式转换**：解析源模板列式数据（投资1~N各占一列），转为行式reactive数组
    - 三区块综合判定逻辑：(一)13项任一为"是"→hasSignificantIncrease=true / (二)3项全为"是"→hasLowCreditRisk=true / (三)8项任一为"是"→hasCreditImpairment=true
    - Stage判定逻辑（调用 determineStage(hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment)）
    - 一致性比对（调用 isStageConsistent）
    - 汇总统计（stage1Count/stage2Count/stage3Count/inconsistentCount）
    - 16384列智能解析（仅取有数据列，忽略空列）
    - 展开/折叠切换逻辑
    - _Requirements: 2.1~2.13_

  - [ ]* 5.3 单元测试: G4-9 Stage判定与一致性逻辑
    - 边界case：全false→Stage1 / 单true→Stage2或3 / creditImpaired覆盖其他
    - 一致性判定：相同/不同Stage组合
    - _Requirements: 2.2, 2.3_

- [ ] 6. G4-10 减值测算（ECL公式链 + 2区段Tab + Stage分组）
  - [ ] 6.1 实现 G4TabImpairmentCalc.vue 组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/impairment/G4TabImpairmentCalc.vue`
    - 37行×19列 → 2区段Tab（Tab1: 未审数+审计调整11列 / Tab2: 审定数+差异8列）
    - Tab切换行同步（selectedRowIndex跨Tab保持）
    - 按Stage分组显示（Stage1/Stage2/Stage3 + 分组小计 + 总计行）
    - 公式列tooltip显示来源（虚线下划线+cursor:help）
    - 底部审计结论textarea + AI按钮 + 编制提示折叠
    - 动态行增删（ElMessageBox.prompt输入投资项目名称）
    - _Requirements: 3.1, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 11.2, 11.5, 11.8_

  - [ ] 6.2 实现 useG4EclImpairmentCalc.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclImpairmentCalc.ts`
    - 公式链自动计算（③④⑥⑦⑧⑨ 全部调用 useG4EclFormulaEngine 纯函数）
    - Stage分组逻辑 + GroupSubtotal 小计汇总
    - 行CRUD + 数据响应式绑定
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 6.3 单元测试: G4-10 公式链端到端
    - 具体数值验证整条公式链（①→③→④→⑥→⑦→⑧→⑨）
    - 分组小计合计正确性
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 7. Checkpoint — 核心sheet验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. G4-11 ECL计量测试（4 section叙述）+ G4-12 转回核销（2区段Tab）
  - [ ] 8.1 实现 G4TabEclMeasurement.vue 组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/impairment/G4TabEclMeasurement.vue`
    - 4 section布局：(一)ECL方法评价 / (二)组合划分依据 / (三)信用损失率确定 / (四)审计结论
    - 每个section标题行右侧AI辅助按钮
    - section(一): 检查项目|检查内容|企业方法(textarea)|审计评价(下拉)|说明(textarea)
    - section(二): 组合名称|划分依据|风险特征|样本量|评价(下拉)|说明 + 动态行增删
    - section(三): 参数名(PD/LGD/EAD)|数据来源|计算方法|验证结果|评价(下拉)|说明 + 动态行增删
    - section(四): 综合审计结论textarea + AI按钮
    - 顶部方法论上下文（琥珀色：ECL三种方法简介）+ 底部编制提示折叠
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 11.1, 11.5_

  - [ ] 8.2 实现 G4TabReversalWriteOff.vue 组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/impairment/G4TabReversalWriteOff.vue`
    - 43行×20列 → 2区段Tab（Tab1: 转回检查10列 / Tab2: 核销检查10列）
    - Tab1: 转回金额校验（>累计计提→红色高亮+错误信息）
    - Tab2: 关联交易行橙色高亮
    - Tab切换行同步 + 各Tab底部合计行
    - 底部审计结论textarea + AI按钮 + 编制提示折叠
    - 各Tab动态行增删 + GtIndexChip索引跳转
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 11.2, 11.5, 11.8_

  - [ ] 8.3 实现 useG4EclReversalWriteOff.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclReversalWriteOff.ts`
    - 转回校验逻辑（调用 isReversalValid）
    - 核销数据管理 + 关联交易标记
    - 合计行计算（调用 calcSumColumn）
    - _Requirements: 5.2, 5.6_

  - [ ]* 8.4 单元测试: G4-12 转回校验边界
    - 转回恰好=累计(合法) / 转回>累计(非法) / 转回=0(合法)
    - _Requirements: 5.2, 5.3_

- [ ] 9. G4-13 凭证检查（3区段Tab + 97行虚拟滚动 + 抽凭 + OCR）
  - [ ] 9.1 实现 G4TabVoucherCheck.vue 组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue`
    - 97行×19列 → 3区段Tab（Tab1: 记账凭证8列 / Tab2: 支持性文件+核对7列 / Tab3: 结论+备注4列）
    - 启用虚拟滚动（97行>50阈值）
    - 分借方区/贷方区两个区块
    - Tab切换行同步
    - Tab2: 6项checkbox核对，全✓显示绿色"全部通过"badge
    - Tab3: 任一核对✗→自动设isAbnormal=true + 红色高亮
    - 顶部借贷平衡汇总区（差额红色显示）
    - 底部审计结论textarea + AI按钮 + 编制提示折叠
    - 动态行增删 + GtIndexChip索引跳转
    - _Requirements: 6.1, 6.2, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 11.1, 11.5, 11.6, 11.9_

  - [ ] 9.2 实现 useG4EclVoucherCheck.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclVoucherCheck.ts`
    - 借贷平衡实时校验（调用 isDebitCreditBalanced + calcDebitCreditDifference）
    - 凭证异常判定（调用 isVoucherNormal）
    - 抽凭结果填入逻辑（fillVoucherSamples）
    - _Requirements: 6.6, 6.7_

  - [ ] 9.3 集成抽凭引擎 + 行级OCR
    - 集成 GtVoucherSamplingEngine（dialog→抽样结果填入借方/贷方区）
    - Tab1 📎附件列行级OCR：上传→POST /d4/contract-ocr→ElMessageBox确认→merge填入
    - _Requirements: 6.3, 6.4, 9.2, 9.3_

  - [ ]* 9.4 单元测试: G4-13 凭证异常判定+借贷平衡
    - 6项全通过/单项失败/多项失败
    - 借贷平衡：差额<0.01(平衡) / 差额≥0.01(不平衡)
    - _Requirements: 6.6, 6.7_

- [ ] 10. Checkpoint — 所有sheet组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. 参考材料（只读178行 + 蓝色信息条）
  - [ ] 11.1 实现参考材料组件
    - 创建 `frontend/src/components/workpaper/g4-bond-investment-ecl/reference/G4TabRefImpairmentGuidance.vue`
    - 178行×13列只读HTML表格 + 虚拟滚动
    - 顶部蓝色信息条"本sheet为参考材料，仅供查阅"
    - 全文搜索（Ctrl+F高亮匹配）
    - 只读保护（无编辑/保存按钮）
    - 创建 `G4TabRefPdConversion.vue`（20行×2列只读表格 + 蓝色信息条）
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 11.6, 11.11_

- [ ] 12. 导入导出（4张表）+ AI（5 section）
  - [ ] 12.1 实现后端导入导出端点
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_ecl_import_export.py`
    - 3个端点：导出模板/导出数据/导入数据（sheet codes: G4-9/G4-10/G4-12/G4-13）
    - G4-10按2区段分sheet导出，G4-12按2Tab分sheet导出，G4-13按3区段分sheet导出
    - 导入格式错误返回详细错误列表（行号/字段/原因）
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 12.2 实现前端 useG4EclImportExport.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG4EclImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）
    - 使用http(axios)调用后端三端点
    - 4张动态行表格（G4-9/G4-10/G4-12/G4-13）各自集成
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 12.3 实现后端AI生成端点
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_ecl_ai.py`
    - POST /api/workpapers/{wp_id}/g4-ecl/ai/{section}
    - 5个section: stage-classification-conclusion / ecl-measurement-conclusion / ecl-method-evaluation / reversal-writeoff-conclusion / voucher-check-conclusion
    - _Requirements: 10.4, 10.5_

- [ ] 13. UI精调 + 集成测试
  - [ ] 13.1 UI规范统一
    - 表格字体13px + AI/复核按钮右对齐section标题同行
    - 公式列虚线下划线+cursor:help+tooltip来源
    - 列宽min-width自适应 + 审计结论el-card包裹
    - 编制提示details折叠底部
    - G4-10/G4-12 Tab切换无闪烁
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.8_

  - [ ]* 13.2 集成测试: selfLoad + 导入导出roundtrip
    - selfLoad模式：render-config返回正确结构
    - 导入导出：4张表×3端点 roundtrip验证
    - 抽凭引擎：dialog→样本填入G4-13
    - OCR：POST /d4/contract-ocr → 确认 → 字段填入
    - 版本链：save触发autoSnapshot
    - _Requirements: 1.6, 9.1, 9.2, 9.3, 10.1_

  - [ ]* 13.3 Playwright E2E测试
    - sheetName分发到7个子组件验证
    - G4-10区段Tab切换+行同步
    - G4-13借贷平衡实时校验+异常高亮
    - 参考材料只读保护（无法编辑）
    - 虚拟滚动在178行参考材料中流畅滚动
    - _Requirements: 1.8, 3.10, 6.6, 7.5, 11.6_

- [ ] 14. Final checkpoint — 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 14 universal correctness properties defined in design
- Unit tests validate specific examples and edge cases
- 公式引擎15个纯函数先于所有UI组件开发，确保逻辑正确性
- 所有PBT使用vitest + fast-check，numRuns≥100
- 后端Python / 前端TypeScript(Vue 3)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14", "2.15", "4.3", "4.4"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["5.1", "5.2", "6.1", "6.2"] },
    { "id": 5, "tasks": ["5.3", "6.3", "8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["8.4", "9.1", "9.2"] },
    { "id": 7, "tasks": ["9.3", "9.4", "11.1"] },
    { "id": 8, "tasks": ["12.1", "12.2", "12.3"] },
    { "id": 9, "tasks": ["13.1"] },
    { "id": 10, "tasks": ["13.2", "13.3"] }
  ]
}
```
