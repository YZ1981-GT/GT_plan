# 关注点 / 已知脆弱处（F 循环）

## 1. F2 四入口的一致性风险

四个 componentType 共享科目模型与审定表，但**各自独立渲染与持久化**。
风险点：某一入口改了行 schema / 键名而其他入口的消费端没跟 → 跨入口聚合失效。
判断某个键是否安全，要同时看 main / valuation / special / stocktake 四侧。

## 2. F2 审定表 overlay 与手工值的优先级容易误解

`crossSheet.grossAdjustmentByRowKey` / `impairmentAdjustmentByRowKey`（来自 F2-14）**覆盖**手工 adjustment，
手工值只在 F2-14 为空时可见。UI 上如果不提示，审计师会以为"带入没生效/被吃掉"。

## 3. F4 账龄口径未统一（唯一未统一的循环）

D/E/G/H/I/J/K/L/M/N 各明细表账龄都已收敛到 `useAgingConfig`，**只有 F4 还是自有 5 固定 rowKey + 扁平 4 字段**。
当前读写同源不产生错数，但：
- 切 5 年段 / 自定义段时 F4 不跟随项目口径
- `aging-other` 残差行不是账龄段（不应计入"1 年以上"），国企披露的"除 1 年内全部"写法需修正
- 后端 `subject_aging_periods('F4')` 需新增分支返 `['current','audited']`（F4 无期初账龄），否则落默认 `['prior','audited']` 会产错列头

## 4. F1 曾有的两类真实缺陷（勿回退）

- **F1-3 → F1-1 调整联动**：曾把 `eventAjeAccum` 注入每个账龄行造成多计，正确做法是纯 computed 消费 `crossSheet.adjustmentTotals`
- **`pushToA13` 传参错误**：模板 `@click="pushToA13"` 会把 PointerEvent 当 rowIds 传入 → `rowIds.includes` 抛错；必须 `@click="pushToA13(selectedRowIds)"`，事件名统一 `a13:push-misstatement`

## 5. F3 供应链票据曾被丢弃

F3-2 / F3-4 / F3-5 的票据类别枚举含"供应链票据"，但审定表与附注早期只硬编码银行承兑 / 商业承兑两行
→ 供应链票据进不了审定与附注，且 `detailGrandTotal`（全部）与 `subtotalRow`（仅两类）口径不一致产生虚假差异。
改为按 `noteType` 动态聚合后解决。附注里供应链票据是央行 2022 第 4 号明确要求讨论的项目。

## 6. F3 逾期票据重分类只有文字提示

源模板明确"逾期银行承兑 → 短期借款 2001/L1；逾期商业承兑 → 应付账款 2202/F4"，
但当前 F3-5 只算 `unpaidAmount` / `riskFlags`，**不生成 RJE 到 F3-3，也不发 L1/F4 信号**。

## 7. F2 曾出现的编译类崩溃

- `el-table-column` 的 `label` 属性内含 ASCII 双引号会破坏 Vue 模板解析（用全角引号或去掉引号）
- 列设置类改动误删 `<template #default="{ row }">` 开始标签 → `Element is missing end tag`，**`get_diagnostics` 查不出，只有 Vite 编译暴露**
- `f2/detail/F2DetailSheet.vue` 曾出现"部分 ref 带 `.value`、部分漏"的混合写法 → 段切换失效、合计空白
