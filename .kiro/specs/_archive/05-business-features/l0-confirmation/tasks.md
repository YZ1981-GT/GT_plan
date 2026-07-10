# Implementation Plan: L0 债务循环函证模块

## Overview

L0债务循环（筹资循环）函证对齐D0架构：复用D0共享组件(7个componentType直接映射 + a-program-console) + 新建L0-5替代程序组件(1个)。源模板1个xlsx/10 sheet。科目覆盖：短期借款/长期借款/应付债券/长期应付款。核心公式：区块合计=Σ金额；还款比例=已检查还款/期末余额；对账差异=账面-对账单。L0比H0多一个confirmation-diff-checklist（复用D0）。Same pattern as F0/G0。

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

- L0是函证循环，架构与F0/G0完全一致：复用D0共享 + 新建循环特有替代程序组件
- L0-1~L0-4/差异检查表(示例)/L0-6/L0-7直接复用D0共享组件，无需任何新代码
- L0-5是唯一需要新建的组件（长期应付款/借款替代程序4区块）：只有1个替代程序
- L0比H0多一个"函证差异检查表（示例）"→confirmation-diff-checklist（复用D0）
- 🔴 L0A源模板tab名误写为"函证程序表F0A"，overrides/yaml以wp_code=L0A为准修正，勿误映射到F0
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- 跨循环共享的组件已由D0 spec完成开发（283任务全绿），此处仅补1个L循环特有组件
- L0无截止自动提取（函证类底稿不适用截止测试）
- 宽表拆分策略：L0-5每区块左右视觉分组（记账凭证5列|检查证据N列）

## Tasks

- [x] 0. Phase0 双源输入（源模板实读）
  - [x] 0.1 openpyxl实读源模板 + 底稿模板库交叉验证
    - 用openpyxl脚本读 `L0 债务循环函证.xlsx` 全10 sheet，确认L0-5每区块实际列头/行数/公式（59×28，8公式）
    - 核实L0A的tab名误写"函证程序表F0A"，确认以wp_code=L0A为准
    - 与 `基础数据/致同通用审计程序及底稿模板（2025年修订）` 交叉验证4区块检查内容
    - 输出L0-5的4区块精确列配置（记账凭证5列 + 各区块检查证据列清单）
    - _Requirements: 2.5, 1.2_

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和overrides映射
    - 在 `wp_code_overrides.json` 中添加L0→confirmation-hub, L0A→a-program-console, L0-1→confirmation-summary, L0-2→confirmation-entity-verify, L0-3→confirmation-followup, L0-4→confirmation-diff-reconcile, 函证差异检查表（示例）→confirmation-diff-checklist, L0-5→confirmation-alternative-l05, L0-6→confirmation-reliability, L0-7→confirmation-fraud-risk（10条）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册 'confirmation-alternative-l05'
    - 在 `htmlRendererRegistry.ts` 中注册 l05→Vue组件映射（type union + registry entry + defineAsyncComponent import）
    - 创建 L0.yaml render schema（10 sheets的component_type和class_code，修正L0A tab名误写F0A）
    - 更新 account_package_registry.json 添加L0包（10 sheets按模板目录顺序）
    - _Requirements: 1.1~1.3, 4.1~4.2_

  - [x]* 1.2 编写注册契约测试
    - 更新 htmlRendererRegistry.spec.ts 验证 confirmation-alternative-l05 已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证10条L0映射
    - _Requirements: 4.3, 4.4_

- [x] 2. 实现公式引擎 useL0FormulaEngine.ts
  - [x] 2.1 创建 `l0-confirmation/composables/useL0FormulaEngine.ts`，实现全部4个纯函数
    - 实现 `calcBlockTotal`（区块合计 = Σ金额列，空数组→0，parseNum兜底NaN→0）
    - 实现 `calcRepaymentRatio`（还款检查比例 = 已检查还款金额 / 期末余额，期末余额=0→0）
    - 实现 `calcReconcileDiff`（对账差异 = 账面余额 - 银行对账单余额）
    - 实现 `isAbnormal`（是否异常 = |对账差异| > 0）
    - _Requirements: 5.1~5.4_

  - [x]* 2.2 编写 Property 1 PBT：区块合计公式
    - 生成器：`fc.array(fc.float({min:-1e8, max:1e8}))`
    - 断言：calcBlockTotal(amounts) === amounts.reduce((a,b)=>a+b,0)；calcBlockTotal([]) === 0
    - **Property 1: 区块合计=Σ金额**
    - **Validates: Requirements 5.1, 2.7**

  - [x]* 2.3 编写 Property 2 PBT：还款检查比例公式
    - 生成器：`fc.float({min:0, max:1e8})` repaid × `fc.float({min:-1e8, max:1e8})` balance
    - 断言：calcRepaymentRatio(repaid, balance) === (balance>0 ? repaid/balance : 0)
    - **Property 2: 还款检查比例=已检查还款/期末余额（除零→0）**
    - **Validates: Requirements 5.2, 2.3**

  - [x]* 2.4 编写 Property 3 PBT：对账差异公式与零差异恒等
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/statement
    - 断言：calcReconcileDiff(book, statement) === book - statement；calcReconcileDiff(v, v) === 0
    - **Property 3: 对账差异=账面-对账单，自身差异=0**
    - **Validates: Requirements 5.3**

  - [x]* 2.5 编写 Property 4 PBT：异常判定
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/statement
    - 断言：isAbnormal(calcReconcileDiff(book, statement)) === (book !== statement)
    - **Property 4: 异常判定 ⟺ 账面≠对账单**
    - **Validates: Requirements 5.4, 2.7**

- [x] 3. 实现 composable 数据管理
  - [x] 3.1 创建 `l0-confirmation/composables/useAlternativeL05Data.ts`
    - Master-Detail结构（公司列表→选中公司→4区块检查表）
    - 定义4区块列配置（按Phase0实读xlsx列头：①期后付款/还款 ②期末余额证据(借款合同/对账单) ③本期借款 ④抵质押/担保）
    - 实现余额汇总区（函证项目长期应付款/借款/年初/借方/贷方/期末 + 本期借款/期后还款检查比例/抵质押证据检查比例）
    - 实现4区块独立CRUD（addRow/removeRow/updateCell）+ 各区块合计行（调用calcBlockTotal）+ 对账差异列（calcReconcileDiff）
    - 实现反向联动（从L0-1获取未回函公司列表）
    - 实现loadAll/persistAll（JSON→checklist_responses.remark，item_id前缀L0-5-alt-{entity}-block{N}-rows）
    - _Requirements: 2.1~2.10, 3.1_

- [x] 4. 实现 Vue 组件
  - [x] 4.1 创建 `confirmation/alternativeL05/GtConfirmationAlternativeL05.vue`（~400行，参照alternativeD05）
    - 调用useAlternativeL05Data + useL0FormulaEngine
    - 多公司Master-Detail（el-tabs按公司 + ElMessageBox.prompt新增公司）
    - 顶部余额汇总区（2行表格）+ 抽样参数区（6字段textarea表单）
    - 4区块各自el-table（左右视觉分组：记账凭证5列固定 | 检查证据横滚分组），②区块含对账差异公式列
    - 每区块合计行 + 索引号列(GtIndexChip，prop名value) + 是否异常列(下拉)
    - 行级OCR上传📎列（复用`/d4/contract-ocr`端点→ElMessageBox确认→merge）
    - 底部审计说明textarea + 审计结论textarea（section标题行右侧AI辅助按钮）
    - selfLoad兜底 + 动态行增删 + 导入导出下拉
    - UI铁律：13px字体/公式列虚线下划线+tooltip/min-width自适应/审计说明结论el-card包裹/编制提示details折叠
    - _Requirements: 2.1~2.12_

- [x] 5. 后端实现
  - [x] 5.1 创建后端3个py文件
    - `_l0_confirmation.py`：1个render策略函数(render_l0_alternative) + 注册RENDERER_DISPATCH（复用confirmation通用renderer返回checklist_responses snapshot）
    - `_l0_confirmation_import_export.py`：3端点（export-template按4区块→4 sheet含列头+说明 / export-data / import-data校验列头+解析行+回写）
    - `_l0_confirmation_ai.py`：2个AI section端点（alternative-audit-note / alternative-audit-conclusion）
    - 路径：`/api/workpapers/{wp_id}/l0/export-template?sheet=L0-5`
    - _Requirements: 4.4, 3.2~3.5_

  - [x] 5.2 创建 `useL0ImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）+ axios三端点（带Authorization header，禁用原生fetch）
    - 多区块分sheet导出/导入
    - _Requirements: 3.2~3.5_

- [x] 6. 跨模块联动集成
  - [x] 6.1 版本链 + 复核集成
    - GtConfirmationAlternativeL05主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer + 手动命名快照）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 6.1~6.4_

  - [x] 6.2 行级OCR + 反向联动
    - 📎OCR列POST contract-ocr→借款信息识别→确认弹窗→merge
    - 从confirmation-hub的L0-1获取未回函公司列表（EventBus/API）
    - _Requirements: 2.8, 2.9_

- [x] 7. 集成测试与验收
  - [x] 7.1 编写集成测试
    - wp_code_overrides映射正确性（10条L0→对应componentType，含L0A tab名误写修正）
    - L0-5四区块独立增删行+合计行（calcBlockTotal）
    - 银行对账差异（calcReconcileDiff）
    - 还款比例除零安全（期末余额=0→0）
    - L0-1→L0-5反向联动（未回函公司传入）
    - 导入导出round-trip（4区块分sheet）
    - 版本快照autoSnapshot
    - _Requirements: 全部_
