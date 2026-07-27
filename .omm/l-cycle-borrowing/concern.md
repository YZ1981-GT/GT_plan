# 关注点 / 已知脆弱处（L 循环）

## 1. 🔴 审定表单期 roll-forward 误用（系统性，已大批修）

L1/L2/L3/L4/L5 审定表曾全部误做成**单期 roll-forward**（期初/贷/借/期末），源模板实为**期初/期末双期**
（各未审/账项调整/重分类/审定）。判定：源模板有"期初数/期末数各分组表头"即双期。
L6/L7 本就正确（两期动态行）；L8 损益类不适用。**已重建 L1/L2/L3/L4/L5**，勿回退成单期。

## 2. 🔴 L5 与 K5 共用 2701

L5 长期应付款用 `ACCOUNT_CODE_PAYABLE='2701'`，K5 预计负债也用 2701 → 两底稿回写 2701 会互相覆盖。
未核实是否刻意，审定合计关系需显式核对。

## 3. 审定表数据丢失（三种形态，L 循环全踩过）

- **无 hydration**：组件 `ref([])` 无从 allResponses 恢复 → 刷新全丢（L5 组件 onMounted 只 loadData 无 restore）
- **lossy 序列化**：save 只挑几个字段（L5-1 `saveAndWriteback` 只存计算列 endBalance/audited，不存可编辑输入
  beginning/aje/rje）→ 即使加 hydration 也丢字段，必须 `JSON.stringify(整行)`
- **update 不 persist**：`updateRow` 只 mutate reactive 从不 save（L5-1 两 update 函数末尾未调 _persistRows）

L5-1 用 `_hydratedOnce` 一次性 guard（reactive 数组恒非空，不能用 length===0 guard，否则每次 self-write 都 re-hydrate 覆盖编辑）。

## 4. 明细表 flat-key 无 hydration

L3-2/L3-5/L3-6 曾用 flat per-field keys（`L3-det-{n}-{field}`）+ 组件本地 `ref([])` 无 hydrate → 刷新丢数据；
且 4 个消费者（明细 hydrate / 附注聚合 / 审定带入 / 交叉验证）读 `L3-L3-2-rows` JSON 而 composable 存 flat →
全读不到（triple-key mess）。已改 JSON-array 单键 + hydrate。

## 5. 交叉验证 dead-key

L3-2↔L3-1 交叉验证曾读 `L3-1-end-balance-total`（实际写 `L3-1-total-audited`）→ 死链恒差异；
且 `detailTotal` 累加 `endBalance`（computed 列不落库，raw 行不含）→ 明细合计恒 0。
排查须对照消费端读的键与生产端写的键，且确认 raw 行是否真有该字段（计算列须现算）。

## 6. 检查表结构做错

L2-4 / L3-9 曾误做成 4 段合规 radio 清单，源模板实为**凭证级检查表**（记账凭证行 + 核对①~⑤ + 检查比例）。
L3-7 逾期检查加逾期比例 = 逾期金额 / L3-1 审定数（联动 `L3-L3-1-adjudication-total`）；L3-8 抵押加评估价值列。

## 7. 导入导出 project_id 缺失恒 500

`INSERT checklist_responses` 漏 `project_id`（NOT NULL）→ 即使 `ON CONFLICT DO UPDATE` 命中，
PG 在 INSERT 阶段先校验 NOT NULL → 导入恒 500（L3 全部导入受影响，从 working_paper 反查 project_id 修复）。
后端 `_SHEET_ITEM_ID` 必须指向前端存储键（`L3-L3-2-rows` 非 `L3-detail-rows`）。

## 8. L4 应付债券的 IE 模型不匹配（deferred）

L4 后端 IE 用 `L4-detail-rows` + 不同字段模型（摊余成本 faceValue/premiumDiscount/amortizedCost），
前端用 beginCostPrincipal/InterestAdj/Accrued 三分解 + credit/debit movement → 前后端 detail 模型本质不同，
IE round-trip 需二选一重构（未修）。

## 9. 报告期硬编码

L1-5 利息测算 / L1-7 逾期检查曾用 `new Date().getFullYear()` → 审计次年取错报告期，应用 props.year。

## 10. P0 模块级崩溃（L3 曾整册不可用）

`GtL3LongTermLoans` 曾**从未 `provide('l3FormData')`**，但 13 个子 tab 都 `inject('l3FormData')!` →
formData undefined → 各 tab setup 阶段解构崩 → 整个 L3 模块运行时不可用（ErrorBoundary）。
get_diagnostics/Vite 200 查不出，唯 Playwright/live 能抓。整册用 inject 共享 formData 时，父入口必须 provide 该实例。
