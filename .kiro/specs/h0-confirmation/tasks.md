# Implementation Plan: H0 固定资产循环函证模块

## Overview

H0固定资产循环函证对齐D0架构：复用D0共享组件(6个componentType直接映射 + a-program-console) + 新建H0-5替代程序组件(1个)。源模板1个xlsx/9 sheet。科目覆盖：固定资产/在建工程/融资租赁/长期资产权属。核心公式：区块合计=Σ金额；检查比例=已检查/期末余额；行差异=账面-证据。Same pattern as F0/G0。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave0", "tasks": ["0.1"] },
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1"] }
  ]
}
```

## Notes

- H0是函证循环，架构与F0/G0完全一致：复用D0共享 + 新建循环特有替代程序组件
- H0-1~H0-4/H0-6/H0-7直接复用D0共享组件，无需任何新代码
- H0-5是唯一需要新建的组件（固定资产循环替代程序4区块）：只有1个替代程序（不像F0有F0-5/F0-6两个）
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- 跨循环共享的组件已由D0 spec完成开发（283任务全绿），此处仅补1个H循环特有组件
- H0无截止自动提取（函证类底稿不适用截止测试）
- 宽表拆分策略：H0-5每区块左右视觉分组（记账凭证5列|检查证据N列）

- [ ] 2. 注册新componentType
  - [ ] 2.1 VALID_COMPONENT_TYPES注册confirmation-alternative-h05
    - 在wp_classification_service.py的VALID_COMPONENT_TYPES中添加
    - _Requirements: 4_
  - [ ] 2.2 htmlRendererRegistry注册h05
    - 添加type union + registry entry + defineAsyncComponent import
    - _Requirements: 4_
  - [ ] 2.3 后端RENDERER_DISPATCH注册h05
    - 复用confirmation通用renderer（返回checklist_responses snapshot）
    - _Requirements: 4_
  - [ ] 2.4 更新htmlRendererRegistry.spec.ts
    - expected componentType列表添加confirmation-alternative-h05
    - _Requirements: 4_

- [ ] 3. 创建composable `useAlternativeH05Data.ts`
  - [ ] 3.1 定义3区块列配置（按xlsx实际列头：①产权核查/②抵押担保核查/③期后银行对账）
    - 每区块拆左右视觉分组（记账凭证列 | 检查证据列）
    - _Requirements: 2, 3_
  - [ ] 3.2 实现Master-Detail数据管理（按对象分组，每对象3区块独立行数据）
    - loadAll/persistAll（JSON→checklist_responses.remark）
    - addRow/removeRow/updateCell（每区块独立CRUD）
    - _Requirements: 2, 3_
  - [ ] 3.3 实现余额汇总区 + 抽样参数区 + 合计行计算
    - 余额汇总：函证项目/年初/借方/贷方/期末 + 抵押担保金额 + 检查比例
    - 抽样参数：6字段
    - 合计行：SUM金额列
    - _Requirements: 2_
  - [ ] 3.4 实现importFromSummary反向联动（从H0-1未回函对象带入）
    - _Requirements: 2, 5_

- [ ] 4. 创建组件 `alternativeH05/GtConfirmationAlternativeH05.vue`
  - [ ] 4.1 多公司/多对象Master-Detail（el-tabs按对象 + ElMessageBox.prompt新增对象）
    - 抽样参数区（6字段textarea表单）
    - 余额汇总区（函证项目+抵押担保2行表格）
    - _Requirements: 2_
  - [ ] 4.2 3区块检查宽表（每区块el-table，记账凭证列固定分组，检查证据列可横滚分组）
    - 每区块合计行 + 索引号列(GtIndexChip) + 是否异常列(下拉)
    - 行级OCR上传按钮（📎列，复用/d4/contract-ocr）
    - 与H1/L1/L3交叉核对ref_index chip
    - _Requirements: 2, 5_
  - [ ] 4.3 底部审计说明textarea + 审计结论textarea（section标题行右侧AI辅助按钮）
    - ~400行
    - _Requirements: 2_

- [ ] 5. 导入导出端点
  - [ ] 5.1 创建后端 `_h0_import_export.py`
    - export-template（按sheet=H0-5，3区块→3个sheet含列头+说明）
    - export-data（当前数据导出）
    - import-data（校验列头+解析行+回写checklist_responses）
    - 路径：`/api/workpapers/{wp_id}/h0/export-template?sheet=H0-5`
    - _Requirements: 3_

- [ ] 6. confirmation-hub集成
  - [ ] 6.1 验证confirmation-hub按wp_code路由H0-5到GtConfirmationAlternativeH05
    - ConfirmationTabs.vue按wp_code分发（H0系列复用现有路由逻辑）
    - _Requirements: 4, 7_
  - [ ] 6.2 实现H0-1→H0-5反向联动（未回函对象带入）
    - EventBus订阅confirmation:updated刷新
    - _Requirements: 5_

- [ ] 7. 版本链集成
  - [ ] 7.1 集成useVersionTrail到GtConfirmationAlternativeH05主入口
    - import并调用useVersionTrail(wpId)，debouncedSave成功回调调用autoSnapshot()
    - 工具栏右侧"版本历史"按钮 → GtWpVersionTrail drawer(rtl,400px)内嵌VersionDiffPanel
    - 手动命名快照入口（ElMessageBox.prompt）
    - _Requirements: 6_

- [ ]* 8. 测试验证
  - [ ]* 8.1 运行注册契约测试确认无回归
    - vitest run htmlRendererRegistry.spec.ts
    - _Requirements: 4_
  - [ ]* 8.2 编写H05 PBT测试 **Feature: confirmation-alternative-h05, Property P1: persistAll后loadAll数据完全还原(round-trip)**
    - _Requirements: 2, 3_
  - [ ]* 8.3 编写H05 PBT测试 **Feature: confirmation-alternative-h05, Property P2: computeBlockTotal === 区块行金额列之和**
    - _Requirements: 2_
  - [ ]* 8.4 编写H05 PBT测试 **Feature: confirmation-alternative-h05, Property P3: importFromSummary幂等不重复累加**
    - _Requirements: 2, 5_
  - [ ]* 8.5 编写H05 PBT测试 **Feature: confirmation-alternative-h05, Property P4: componentType同时在VALID_COMPONENT_TYPES与htmlRendererRegistry**
    - _Requirements: 4_
  - [ ]* 8.6 编写H05 PBT测试 **Feature: confirmation-alternative-h05, Property P5: export-data→import-data往返等价**
    - _Requirements: 3_
  - [ ]* 8.7 Playwright实测confirmation-hub路由H0-5渲染+增删行+导入导出
    - _Requirements: 2, 4_

## Notes

- H0-1~H0-4/H0-6/H0-7直接复用D0共享组件，无需任何新代码
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- H0-5是唯一需要新建的组件（替代程序按固定资产循环证据类型3区块）
- 跨循环共享的9个confirmation-*组件已由D0 spec完成开发（283任务全绿）
- H0特殊性：大额单笔资产100%函证 + 抵押/担保函证，与H1/L1/L3交叉核对

## Tasks

- [ ] 0. Phase0 双源输入（源模板实读）
  - [ ] 0.1 openpyxl实读源模板 + 底稿模板库交叉验证
    - 用openpyxl脚本读 `H0 固定资产循环函证.xlsx` 全9 sheet，确认H0-5每区块实际列头/行数/公式
    - 与 `基础数据/致同通用审计程序及底稿模板（2025年修订）` 交叉验证4区块检查内容
    - 输出H0-5的4区块精确列配置（记账凭证5列 + 各区块检查证据列清单）
    - _Requirements: 2.5_

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和overrides映射
    - 在 `wp_code_overrides.json` 中添加H0→confirmation-hub, H0A→a-program-console, H0-1→confirmation-summary, H0-2→confirmation-entity-verify, H0-3→confirmation-followup, H0-4→confirmation-diff-reconcile, H0-5→confirmation-alternative-h05, H0-6→confirmation-reliability, H0-7→confirmation-fraud-risk（9条）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册 'confirmation-alternative-h05'
    - 在 `htmlRendererRegistry.ts` 中注册 h05→Vue组件映射（type union + registry entry + defineAsyncComponent import）
    - 创建 H0.yaml render schema（9 sheets的component_type和class_code）
    - 更新 account_package_registry.json 添加H0包（9 sheets按模板目录顺序）
    - _Requirements: 1.1~1.3, 4.1~4.2_

  - [ ]* 1.2 编写注册契约测试
    - 更新 htmlRendererRegistry.spec.ts 验证 confirmation-alternative-h05 已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证9条H0映射
    - _Requirements: 4.3, 4.4_

- [ ] 2. 实现公式引擎 useH0FormulaEngine.ts
  - [ ] 2.1 创建 `h0-confirmation/composables/useH0FormulaEngine.ts`，实现全部4个纯函数
    - 实现 `calcBlockTotal`（区块合计 = Σ金额列，空数组→0，parseNum兜底NaN→0）
    - 实现 `calcCheckRatio`（检查比例 = 已检查金额 / 期末余额，期末余额=0→0）
    - 实现 `calcRowVariance`（行差异 = 账面金额 - 证据金额）
    - 实现 `isAbnormal`（是否异常 = |行差异| > 0）
    - _Requirements: 5.1~5.4_

  - [ ]* 2.2 编写 Property 1 PBT：区块合计公式
    - 生成器：`fc.array(fc.float({min:-1e8, max:1e8}))`
    - 断言：calcBlockTotal(amounts) === amounts.reduce((a,b)=>a+b,0)；calcBlockTotal([]) === 0
    - **Property 1: 区块合计=Σ金额**
    - **Validates: Requirements 5.1, 2.7**

  - [ ]* 2.3 编写 Property 2 PBT：检查比例公式
    - 生成器：`fc.float({min:0, max:1e8})` checked × `fc.float({min:-1e8, max:1e8})` balance
    - 断言：calcCheckRatio(checked, balance) === (balance>0 ? checked/balance : 0)
    - **Property 2: 检查比例=已检查/期末余额（除零→0）**
    - **Validates: Requirements 5.2, 2.3**

  - [ ]* 2.4 编写 Property 3 PBT：行差异公式与零差异恒等
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/evidence
    - 断言：calcRowVariance(book, evidence) === book - evidence；calcRowVariance(v, v) === 0
    - **Property 3: 行差异=账面-证据，自身差异=0**
    - **Validates: Requirements 5.3**

  - [ ]* 2.5 编写 Property 4 PBT：异常判定
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/evidence
    - 断言：isAbnormal(calcRowVariance(book, evidence)) === (book !== evidence)
    - **Property 4: 异常判定 ⟺ 账面≠证据**
    - **Validates: Requirements 5.4, 2.7**

- [ ] 3. 实现 composable 数据管理
  - [ ] 3.1 创建 `h0-confirmation/composables/useAlternativeH05Data.ts`
    - Master-Detail结构（公司列表→选中公司→4区块检查表）
    - 定义4区块列配置（按Phase0实读xlsx列头：①期后验收/权属 ②期末余额证据 ③本期新增 ④抵押担保/融资租赁）
    - 实现余额汇总区（函证项目/年初/借方/贷方/期末 + 本期新增/权属检查比例/期后验收比例）
    - 实现4区块独立CRUD（addRow/removeRow/updateCell）+ 各区块合计行（调用calcBlockTotal）
    - 实现反向联动（从H0-1获取未回函公司列表）
    - 实现loadAll/persistAll（JSON→checklist_responses.remark，item_id前缀H0-5-alt-{entity}-block{N}-rows）
    - _Requirements: 2.1~2.10, 3.1_

- [ ] 4. 实现 Vue 组件
  - [ ] 4.1 创建 `confirmation/alternativeH05/GtConfirmationAlternativeH05.vue`（~400行，参照alternativeD05）
    - 调用useAlternativeH05Data + useH0FormulaEngine
    - 多公司Master-Detail（el-tabs按公司 + ElMessageBox.prompt新增公司）
    - 顶部余额汇总区（2行表格）+ 抽样参数区（6字段textarea表单）
    - 4区块各自el-table（左右视觉分组：记账凭证5列固定 | 检查证据横滚分组）
    - 每区块合计行 + 索引号列(GtIndexChip，prop名value) + 是否异常列(下拉)
    - 行级OCR上传📎列（复用`/d4/contract-ocr`端点→ElMessageBox确认→merge）
    - 底部审计说明textarea + 审计结论textarea（section标题行右侧AI辅助按钮）
    - selfLoad兜底 + 动态行增删 + 导入导出下拉
    - UI铁律：13px字体/公式列虚线下划线+tooltip/min-width自适应/审计说明结论el-card包裹/编制提示details折叠
    - _Requirements: 2.1~2.12_

- [ ] 5. 后端实现
  - [ ] 5.1 创建后端3个py文件
    - `_h0_confirmation.py`：1个render策略函数(render_h0_alternative) + 注册RENDERER_DISPATCH（复用confirmation通用renderer返回checklist_responses snapshot）
    - `_h0_confirmation_import_export.py`：3端点（export-template按4区块→4 sheet含列头+说明 / export-data / import-data校验列头+解析行+回写）
    - `_h0_confirmation_ai.py`：2个AI section端点（alternative-audit-note / alternative-audit-conclusion）
    - 路径：`/api/workpapers/{wp_id}/h0/export-template?sheet=H0-5`
    - _Requirements: 4.4, 3.2~3.5_

  - [ ] 5.2 创建 `useH0ImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）+ axios三端点（带Authorization header，禁用原生fetch）
    - 多区块分sheet导出/导入
    - _Requirements: 3.2~3.5_

- [ ] 6. 跨模块联动集成
  - [ ] 6.1 版本链 + 复核集成
    - GtConfirmationAlternativeH05主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer + 手动命名快照）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 6.1~6.4_

  - [ ] 6.2 行级OCR + 反向联动
    - 📎OCR列POST contract-ocr→资产信息识别→确认弹窗→merge
    - 从confirmation-hub的H0-1获取未回函公司列表（EventBus/API）
    - _Requirements: 2.8, 2.9_

- [ ] 7. 集成测试与验收
  - [ ] 7.1 编写集成测试
    - wp_code_overrides映射正确性（9条H0→对应componentType）
    - H0-5四区块独立增删行+合计行（calcBlockTotal）
    - 检查比例除零安全（期末余额=0→0）
    - H0-1→H0-5反向联动（未回函公司传入）
    - 导入导出round-trip（4区块分sheet）
    - 版本快照autoSnapshot
    - _Requirements: 全部_
