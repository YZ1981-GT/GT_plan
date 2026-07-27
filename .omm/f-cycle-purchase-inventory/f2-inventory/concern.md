# F2 关注点

## 1. 四入口共享科目模型但独立持久化

`f2AccountModel.ts` 是唯一科目真源，但四个 componentType 各自渲染与存 sheet。
改行 schema / 键名时必须四侧同查（main / valuation / special / stocktake），否则跨入口聚合静默失效。

## 2. 审定表 overlay 覆盖手工值

F2-14 有数据时 `crossSheet.grossAdjustmentByRowKey` / `impairmentAdjustmentByRowKey` 覆盖手工 adjustment，
手工值仅 fallback → "带入调整"只在 F2-14 空时可见。UI 若不提示会被当成 bug。

## 3. 单列净额调整不能套双列 helper

F2 审定表账项调整是单列净额 + `updateCell(block, rowKey, field, value)` 四参 block-scoped + 双科目族。
通用双列（AJE/RJE）带入 helper 的快照累加会覆盖或丢掉单列原值 → F2 必须自包含实现。

## 4. 曾出现的编译类崩溃（Vite 才能抓）

- `el-table-column` 的 `label` 属性里写 ASCII 双引号 → 破坏 Vue 模板解析
- 加列设置时误删 `<template #default="{ row }">` 开始标签 → `Element is missing end tag`
- `F2DetailSheet.vue` 曾"部分 ref 带 `.value`、部分漏" → 段切换失效（`v-if` 比较 ref 对象恒 false）、合计空白
- `f2/**` 的相对导入层级错（`voucher-sampling` / `GtGridSheet` / `F2SheetToolbar` 多一级 `../`）→ Vite 500

以上 `get_diagnostics` 全部查不出，**判定崩溃类问题以 Vite transform 200 为准**。

## 5. 配置驱动的双刃

`f2DetailSheetConfigs.ts` / `f2CutoffSheetConfigs.ts` / `f2StocktakeConfigs.ts` 让一个组件服务多张表，
但也意味着**改配置会同时影响多张源模板表**。改前要确认该配置被哪些 sheet 消费。

## 6. 抽凭引擎接入的 API 契约

F2 各检查表接 `GtVoucherSamplingEngine` 必须 `account-code`（单数）+ `phase`（仅 `preliminary|final`）+
`workpaper-id` + `year`，`@filled` 回调收到的是**对象** `{samples, ...}` 不是数组。
早期传 `:account-codes="[...]"` + `dialog-mode` 是旧 API，会缺 required props 直接 422。
