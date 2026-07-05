# Implementation Plan: K0 管理循环函证模块

## Overview

K0管理循环函证对齐D0架构：复用D0共享组件(6个componentType直接映射 + a-program-console) + 新建K0-5/K0-6替代程序组件(2个)。源模板1个xlsx/10 sheet。科目覆盖：其他应收款/其他应付款。核心公式：区块合计=Σ金额；检查比例=已检查/期末余额；行差异=账面-证据；对账差异=本方-对方。Same pattern as F0/G0（2个替代程序类似F0-5/F0-6）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave0", "tasks": ["0.1"] },
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1"] }
  ]
}
```

## Notes

- K0是函证循环，架构与F0/G0完全一致：复用D0共享 + 新建循环特有替代程序组件
- K0-1~K0-4/K0-7/K0-8直接复用D0共享组件，无需任何新代码
- K0-5/K0-6是唯一需要新建的组件（其他应收款/其他应付款替代程序4区块）：2个替代程序类似F0-5/F0-6
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- 跨循环共享的组件已由D0 spec完成开发（283任务全绿），此处仅补2个K循环特有组件
- K0无截止自动提取（函证类底稿不适用截止测试）
- 宽表拆分策略：K0-5/K0-6每区块左右视觉分组（记账凭证5列|检查证据N列）
- K0特色：往来对账区块（对账差异=本方余额-对方余额）

## Tasks

- [ ] 0. Phase0 双源输入（源模板实读）
  - [ ] 0.1 openpyxl实读源模板 + 底稿模板库交叉验证
    - 用openpyxl脚本读 `K0 管理循环函证.xlsx` 全10 sheet，确认K0-5/K0-6每区块实际列头/行数/公式（各73×25，8公式）
    - 与 `基础数据/致同通用审计程序及底稿模板（2025年修订）` 交叉验证4区块检查内容
    - 输出K0-5/K0-6的4区块精确列配置（记账凭证5列 + 各区块检查证据列清单）
    - _Requirements: 2.5, 3.5_

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和overrides映射
    - 在 `wp_code_overrides.json` 中添加K0→confirmation-hub, K0A→a-program-console, K0-1→confirmation-summary, K0-2→confirmation-entity-verify, K0-3→confirmation-followup, K0-4→confirmation-diff-reconcile, K0-5→confirmation-alternative-k05, K0-6→confirmation-alternative-k06, K0-7→confirmation-reliability, K0-8→confirmation-fraud-risk（10条）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册 'confirmation-alternative-k05' 和 'confirmation-alternative-k06'
    - 在 `htmlRendererRegistry.ts` 中注册 k05/k06→Vue组件映射（type union + registry entry + defineAsyncComponent import）
    - 创建 K0.yaml render schema（10 sheets的component_type和class_code）
    - 更新 account_package_registry.json 添加K0包（10 sheets按模板目录顺序）
    - _Requirements: 1.1~1.3, 5.1~5.3_

  - [ ]* 1.2 编写注册契约测试
    - 更新 htmlRendererRegistry.spec.ts 验证 confirmation-alternative-k05/k06 已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证10条K0映射
    - _Requirements: 5.3, 5.4_

- [ ] 2. 实现公式引擎 useK0FormulaEngine.ts
  - [ ] 2.1 创建 `k0-confirmation/composables/useK0FormulaEngine.ts`，实现全部5个纯函数
    - 实现 `calcBlockTotal`（区块合计 = Σ金额列，空数组→0，parseNum兜底NaN→0）
    - 实现 `calcCheckRatio`（检查比例 = 已检查金额 / 期末余额，期末余额=0→0）
    - 实现 `calcRowVariance`（行差异 = 账面金额 - 证据金额）
    - 实现 `calcReconcileDiff`（对账差异 = 本方余额 - 对方余额）
    - 实现 `isAbnormal`（是否异常 = |行差异| > 0）
    - _Requirements: 6.1~6.5_

  - [ ]* 2.2 编写 Property 1 PBT：区块合计公式
    - 生成器：`fc.array(fc.float({min:-1e8, max:1e8}))`
    - 断言：calcBlockTotal(amounts) === amounts.reduce((a,b)=>a+b,0)；calcBlockTotal([]) === 0
    - **Property 1: 区块合计=Σ金额**
    - **Validates: Requirements 6.1, 2.7, 3.7**

  - [ ]* 2.3 编写 Property 2 PBT：检查比例公式
    - 生成器：`fc.float({min:0, max:1e8})` checked × `fc.float({min:-1e8, max:1e8})` balance
    - 断言：calcCheckRatio(checked, balance) === (balance>0 ? checked/balance : 0)
    - **Property 2: 检查比例=已检查/期末余额（除零→0）**
    - **Validates: Requirements 6.2, 2.3, 3.3**

  - [ ]* 2.4 编写 Property 3 PBT：行差异公式与零差异恒等
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/evidence
    - 断言：calcRowVariance(book, evidence) === book - evidence；calcRowVariance(v, v) === 0
    - **Property 3: 行差异=账面-证据，自身差异=0**
    - **Validates: Requirements 6.3**

  - [ ]* 2.5 编写 Property 4 PBT：对账差异公式与零差异恒等
    - 生成器：`fc.float({min:-1e8, max:1e8})` × self/other
    - 断言：calcReconcileDiff(self, other) === self - other；calcReconcileDiff(v, v) === 0
    - **Property 4: 对账差异=本方-对方，自身对账差异=0**
    - **Validates: Requirements 6.4**

  - [ ]* 2.6 编写 Property 5 PBT：异常判定
    - 生成器：`fc.float({min:-1e8, max:1e8})` × book/evidence
    - 断言：isAbnormal(calcRowVariance(book, evidence)) === (book !== evidence)
    - **Property 5: 异常判定 ⟺ 账面≠证据**
    - **Validates: Requirements 6.5, 2.7, 3.7**

- [ ] 3. 实现 composable 数据管理
  - [ ] 3.1 创建 `k0-confirmation/composables/useAlternativeK05Data.ts`
    - Master-Detail结构（公司列表→选中公司→4区块检查表）
    - 定义4区块列配置（按Phase0实读xlsx列头：①期后收款 ②期末余额证据 ③本期发生额 ④往来对账/协议）
    - 实现余额汇总区（函证项目其他应收款/年初/借方/贷方/期末 + 本期发生额/期后收款检查比例/往来对账比例）
    - 实现4区块独立CRUD（addRow/removeRow/updateCell）+ 各区块合计行（调用calcBlockTotal）+ 对账差异列（calcReconcileDiff）
    - 实现反向联动（从K0-1获取未回函公司列表）
    - 实现loadAll/persistAll（JSON→checklist_responses.remark，item_id前缀K0-5-alt-{entity}-block{N}-rows）
    - _Requirements: 2.1~2.10, 4.1_

  - [ ] 3.2 创建 `k0-confirmation/composables/useAlternativeK06Data.ts`
    - 结构与K05一致，4区块列配置和标题按其他应付款不同（①期后付款 ②期末余额证据 ③本期发生额 ④往来对账/协议）
    - 余额汇总区（函证项目其他应付款 + 期后付款检查比例/往来对账比例）
    - loadAll/persistAll（item_id前缀K0-6-alt-{entity}-block{N}-rows）
    - _Requirements: 3.1~3.10, 4.2_

- [ ] 4. 实现 Vue 组件
  - [ ] 4.1 创建 `confirmation/alternativeK05/GtConfirmationAlternativeK05.vue`（~400行，参照alternativeD05）
    - 调用useAlternativeK05Data + useK0FormulaEngine
    - 多公司Master-Detail（el-tabs按公司 + ElMessageBox.prompt新增公司）
    - 顶部余额汇总区（2行表格）+ 抽样参数区（6字段textarea表单）
    - 4区块各自el-table（左右视觉分组：记账凭证5列固定 | 检查证据横滚分组），④区块含对账差异公式列
    - 每区块合计行 + 索引号列(GtIndexChip，prop名value) + 是否异常列(下拉)
    - 行级OCR上传📎列（复用`/d4/contract-ocr`端点→ElMessageBox确认→merge）
    - 底部审计说明textarea + 审计结论textarea（section标题行右侧AI辅助按钮）
    - selfLoad兜底 + 动态行增删 + 导入导出下拉
    - UI铁律：13px字体/公式列虚线下划线+tooltip/min-width自适应/审计说明结论el-card包裹/编制提示details折叠
    - _Requirements: 2.1~2.12_

  - [ ] 4.2 创建 `confirmation/alternativeK06/GtConfirmationAlternativeK06.vue`（~400行，参照alternativeD06）
    - 调用useAlternativeK06Data，与K05结构一致，仅4区块列配置和标题不同（其他应付款）
    - _Requirements: 3.1~3.12_

- [ ] 5. 后端实现
  - [ ] 5.1 创建后端3个py文件
    - `_k0_confirmation.py`：2个render策略函数(render_k0_alternative_k05/k06) + 注册RENDERER_DISPATCH（复用confirmation通用renderer返回checklist_responses snapshot）
    - `_k0_confirmation_import_export.py`：3端点（export-template按4区块→4 sheet含列头+说明 / export-data / import-data校验列头+解析行+回写），按sheet=K0-5|K0-6分发
    - `_k0_confirmation_ai.py`：AI section端点（alternative-audit-note / alternative-audit-conclusion）
    - 路径：`/api/workpapers/{wp_id}/k0/export-template?sheet=K0-5`
    - _Requirements: 5.5, 4.2~4.6_

  - [ ] 5.2 创建 `useK0ImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）+ axios三端点（带Authorization header，禁用原生fetch）
    - 多区块分sheet导出/导入，K05/K06按sheet参数区分
    - _Requirements: 4.3~4.6_

- [ ] 6. 跨模块联动集成
  - [ ] 6.1 版本链 + 复核集成
    - GtConfirmationAlternativeK05/K06主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer + 手动命名快照）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 7.1~7.4_

  - [ ] 6.2 行级OCR + 反向联动
    - 📎OCR列POST contract-ocr→往来信息识别→确认弹窗→merge
    - 从confirmation-hub的K0-1获取未回函公司列表（EventBus/API），K05取其他应收款/K06取其他应付款
    - _Requirements: 2.8, 2.9, 3.8, 3.9_

- [ ] 7. 集成测试与验收
  - [ ] 7.1 编写集成测试
    - wp_code_overrides映射正确性（10条K0→对应componentType）
    - K0-5/K0-6四区块独立增删行+合计行（calcBlockTotal）
    - 往来对账差异（calcReconcileDiff）
    - 检查比例除零安全（期末余额=0→0）
    - K0-1→K0-5/K0-6反向联动（未回函公司传入）
    - 导入导出round-trip（4区块分sheet，K05/K06分sheet参数）
    - 版本快照autoSnapshot
    - _Requirements: 全部_
