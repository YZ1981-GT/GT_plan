# Implementation Plan

## Overview

按 design M0 → M4 实施。**前置**：`confirmation-hub-workbench-tabs` Req10 让 G0-3/G0-4 可达（否则 diffSecurities 零渲染无法验证）。**M0 硬前置**（两表源模板 17/15 列未逐列核对不得进 M1）。证券表 additive 补列（`diff-securities-v1` 读回不丢）；非证券表新建三维专属组件（**不改共享 `diffReconcile`**，六枢纽零回归红线）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "note": "只读核对两表源模板列清单 + 源外登记 + 既有数据行数 + 基线（硬前置）" },
    { "wave": 1, "tasks": ["2.1"], "note": "证券表 additive 补 5 列 + 调账判断列（依赖 Req10 可达）" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "note": "非证券三维组件 + 类型 + 注册 + override 接力 Req10" },
    { "wave": 3, "tasks": ["4.1"], "note": "上下游 confirm_index 关联 + 两表分工 + 旧 diffReconcile 数据 hydrate" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "note": "契约/属性/守卫（含 diffReconcile 未改守卫）+ 零回归门 + Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：源模板列清单核对与基线（硬前置）

- [x] 1.1 落 g0DiffSourceManifest
  - 新建 `audit-platform/frontend/src/components/workpaper/g0-confirmation/g0DiffSourceManifest.ts`
  - 对照源模板逐列录入：证券表 17 列、非证券表 15 列（含三维分组 持股比例/投资金额/投资条款 × 账面·回函·差异）
  - 登记源外增强字段：`security_code` / `security_type`
  - 核实 G0 系列（G0-3证券 / G0-4非证券）既有 checklist_responses 行数（判断迁移风险，预期近零）
  - 纯数据文件，不改生产行为
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 1.2 零回归基线
  - 运行并记录：六枢纽 `diffReconcile` 相关测试、函证域前端全量测试
  - 记录 `DiffReconcileRow` 与 `diffReconcile/` 组件当前内容（作为 Property 5「未改动」比对基准）
  - _Requirements: 5.1, 5.2_

- [x] 2. Wave 1：证券表补列

- [x] 2.1 SecuritiesDiffRow additive 补 5 列 + 调账判断列
  - `diffSecuritiesTypes.ts`：additive 补 `confirm_index` / `fund_account` / `account_holder` / `booked_balance` / `support_evidence` / `need_adjust: '是'|'否'|'待定'`；每列注释源出处
  - `diffSecurities/` grid：渲染 5 新列（按源 17 列顺序，含数量/市价/公允价值三维分组表头）；「是否需要调账」改点选判断列，既有非空 `adjustment_note` 映射 need_adjust=待定 + 保留原文
  - 从 G0-1 带入 `confirm_index` 去重
  - `security_code`/`security_type` 保留（登记源外，不删）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Properties: 1, 2, 3_

- [x] 3. Wave 2：非证券三维组件

- [x] 3.1 NonSecuritiesDiffRow 三维类型 + 组件
  - 新建 `diffNonSecurities/nonSecuritiesDiffTypes.ts`：`NonSecuritiesDiffRow`（持股比例/投资金额/投资条款三维，见 design Data Models）+ payload `diff-nonsecurities-v1`
  - 新建 `GtG0DiffNonSecurities.vue` + `useG0DiffNonSecurities.ts`：三维核对渲染（分组表头 账面·回函·差异）+ 计算（amount_diff=booked−reply / ratio_diff=百分点 / 条款 term_match 不相减）
  - 列与源模板 15 列一致（对 manifest），不新增源模板没有的列
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 7.1, 7.2_
  - _Properties: 4, 6_

- [x] 3.2 注册 + override 接力 Req10
  - `htmlRendererRegistry.ts` 注册 `confirmation-diff-nonsecurities`
  - `wp_code_overrides.json` 把 `函证差异核对表G0-4(非证券投资)` 从 `confirmation-diff-reconcile`（Req10 落的可达值）改指向 `confirmation-diff-nonsecurities`
  - 改后需重启后端使 `_WP_CODE_OVERRIDE` 重载（该 JSON 不随 watchfiles 热重载）
  - _Requirements: 2.4_
  - _Properties: 5, 6_

- [x] 4. Wave 3：上下游关联与旧数据兼容

- [x] 4.1 confirm_index 关联 + 两表分工 + 旧 diffReconcile hydrate
  - 两表行标注 `confirm_index` 关联 G0-1；G0-1 match_status='不符' 行可带入或待核对提示；无法自动关联提供手工填索引不静默断链
  - 「需要调账」经 `need_adjust` 可被下游消费或提示 + 索引
  - 底稿内明示两表适用范围（证券/非证券），同一被投资单位归一表；性质不明允许选归属不自动双写；差异合计分别统计不隐式相加
  - 非证券组件 hydrate 时读旧 `diff-reconcile-v1`（若既有项目录在共享 diffReconcile）→ 映射到投资金额维（booked/reply/difference），比例/条款维空，不丢
  - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_
  - _Properties: 7, 8, 9_

- [x] 5. Wave 4：测试与守卫

- [x] 5.1 属性测试与契约测试
  - fast-check：Property 1 证券 round-trip、Property 7 非证券旧数据 hydrate、Property 4 三维计算规则
  - 契约：Property 6 非证券 15 列对 manifest、Property 10 每列可追溯源出处、Property 3 源外登记
  - _Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3_

- [x] 5.2 diffReconcile 未改守卫（零回归红线）
  - Property 5：断言 `DiffReconcileRow` 与 `diffReconcile/` 组件未被本 spec 改动（对 1.2 基线 diff/grep）
  - 六枢纽 diffReconcile 相关测试全绿
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.4_

- [x] 5.3 零回归门 + live 验证
  - 已完成 · 函证域全量前端测试：692 中 691 绿，唯一失败 `alternativeCallerMount.smoke.spec.ts::GtConfirmationAlternativeL05`（`getBlockTotalByDirection is not a function`）属并发 `confirmation-alternative-structure-alignment` 会话的在建文件（git `M`），非本 spec 触及；diffReconcile/diffSecurities/diffNonSecurities 全绿
  - 已完成 · 注册契约（htmlRendererRegistry/componentTypeContract/useEditorMode）66 绿；后端 `test_g0_confirmation_integration` 29 绿；g0-confirmation 域 33 绿
  - 已完成 · 改动文件 `get_diagnostics` 全清 + Vite transform 全 200（GtConfirmationDiffSecurities / GtG0DiffNonSecurities / useG0DiffNonSecurities / nonSecuritiesDiffTypes / htmlRendererRegistry）
  - 已完成 · **live HTTP round-trip（重药控股安徽 0ec33ac9 / G0 wp 2948473b，create→verify→restore 零污染）**：render-config 实测两表**可达**——`函证差异核对表G0-3（证券投资）`→`confirmation-diff-securities`/`diff-securities-v1`、`函证差异核对表G0-4(非证券投资)`→`confirmation-diff-nonsecurities`/`diff-nonsecurities-v1`（均未落 univer/onlyoffice 兜底，证 Req10 可达性由全名 override 已满足）；G0-4 三维 save→read 持久化正确、G0-4 旧 `diff-reconcile-v1` 后端 passthrough（Property 7 前端 hydrate 种子）、G0-3 证券 5 新列+need_adjust save→read；RESTORED_CLEAN 两表还原为空零污染
  - 说明 · 浏览器 Playwright 未单独跑：可达性与持久化已由 live render-config + save round-trip 权威证明（比 SSE-flaky 的函证编辑器更可靠），派生列计算由 Property 4 单测覆盖
  - _Requirements: 5.3_
  - _Properties: 1, 2, 4, 5, 7_

## Notes

- **前置**：`confirmation-hub-workbench-tabs` Req10 让 G0-3/G0-4 可达；本 spec 只做可达之后的结构正确性
- **M0 硬前置**：两表源模板 17/15 列未逐列核对不得进 M1
- 证券表 additive（`diff-securities-v1` 读回不丢）；非证券表新建三维专属组件
- **红线**：共享 `diffReconcile` 与 `DiffReconcileRow` 一行不改（D0/E0/F0/H0/K0/L0 六枢纽零回归），Property 5 守卫
- 不臆造列（对源模板 17/15 列）；`security_code`/`security_type` 源外增强保留不删
- G0-4 override 改指向新 componentType 后需重启后端（`wp_code_overrides.json` 不热重载）
