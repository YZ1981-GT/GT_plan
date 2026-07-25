# Implementation Plan: F2 存货底稿跨底稿勾稽与智能取数加固

## Overview

在既有 F2 模块上做加法增强：后端 render 预填 + 跨底稿 pull 纯函数 + EventBus 联动。分 8 波执行，Wave 0/1 无依赖，Wave 2+ 依赖前序。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2"], "depends_on": [] },
    { "wave": 1, "tasks": ["3", "4", "5"], "depends_on": [] },
    { "wave": 2, "tasks": ["6", "7", "8"], "depends_on": [0, 1] },
    { "wave": 3, "tasks": ["9", "10"], "depends_on": [1] },
    { "wave": 4, "tasks": ["11", "12"], "depends_on": [1] },
    { "wave": 5, "tasks": ["13", "14"], "depends_on": [1] },
    { "wave": 6, "tasks": ["15"], "depends_on": [2] },
    { "wave": 7, "tasks": ["16", "17", "18"], "depends_on": [0, 1, 2, 3, 4, 5, 6] }
  ]
}
```

## Tasks

### Wave 0 — 后端 render 基础设施

- [x] 1. F2 render 补 bs_date + related_parties
  - 文件：`backend/app/routers/wp_render_strategies/_f2_inventory_main.py`
  - 照 `_h2_construction_in_progress.py::_load_project_context` 范式：`project_context` 加 `bs_date`（=`{audit_year}-12-31`）+ `related_parties`（查 `related_party_registry` project_id + is_deleted=false，try/except 优雅降级返回 []）。
  - 验证：render-config 返回含 bs_date/related_parties 字段（ast.parse + 后端启动无错）。
  - _Requirements: 2_

- [x] 2. F2-1 审定表 TB 子科目预填
  - 文件：`_f2_inventory_main.py` 新增 `_build_adjudication_prefill(ctx)`（照 J1/D5 范式）。
  - 用 `get_active_filter(TbBalance)` 查 1401~1412 + 1471，优先二级明细归集到 `F2_CATEGORIES` rowKey，退一级；资产类期初/期末直取，1471 备抵取 abs；仅 `F2-adjudication-data` 缺失时输出预填。
  - render 返回 dict 加 `tb_values`（各 rowKey 期初/期末未审）+ `adjudication_prefill`。
  - 验证：pytest 断言预填期末合计 == tb_balance 存货科目期末汇总（P1）；已有持久化时不覆盖（P2）。
  - _Requirements: 1_

### Wave 1 — 跨底稿 pull 纯函数

- [x] 3. 新建 f2D4CostPull.ts（F2→D4 营业成本勾稽）
  - 文件：`frontend/src/components/workpaper/composables/f2D4CostPull.ts`（复用 h1CipH2Pull 结构）。
  - `pullOperatingCost(projectId, year)`：从 project trial-balance 端点取 6401 主营业务成本审定发生额，返回 `{ status, operatingCost, message }`（优雅降级）。
  - 纯函数 `buildCostCarryforwardReconcile(outboundTotal, operatingCost, invBalance, tolPct=0.05)`：diff/matched。
  - 验证：vitest 覆盖 P4（matched ⟺ 容差内；diff 符号）。
  - _Requirements: 3_

- [x] 4. 新建 f2LedgerPostOutbound.ts（期后出库取数）
  - 文件：`frontend/.../composables/f2LedgerPostOutbound.ts`（复用 D2 importPostPaymentFromLedger 范式）。
  - `pullPostPeriodOutbound(projectId, bsYear, accountCode, opts?)`：查 `ledger/entries` 次年存货科目贷方（窗口默认次年前 6 月），名称归集。
  - 纯函数 `aggregateOutboundByName(entries)` + `normalizeInvName(name)`。
  - 验证：vitest 覆盖 P5（归集合计=输入贷方；规范化幂等）。
  - _Requirements: 4_

- [x] 5. 新建 f2NrvPricePull.ts（NRV 售价参考）
  - 文件：`frontend/.../composables/f2NrvPricePull.ts`。
  - `pullRecentSalesPrice(projectId, year, itemName?)`：从序时账 6001 贷方或 D4 明细取近期销售单价，返回参考单价列表 + status（优雅降级）。
  - 验证：vitest 覆盖不可得时返回空 + status；纯函数解析正确。
  - _Requirements: 10_

### Wave 2 — 内部勾稽扩展

- [x] 6. 审定表预填消费 + 净额行
  - 文件：`useF2Adjudication.ts` + `F2TabAdjudication.vue`（或 `F2AdjudicationBlockTable.vue`）。
  - 消费后端 `adjudication_prefill`/`tb_values`（`F2-adjudication-data` 缺失时 seed）；审定表加"存货净额 = 余额 − 跌价准备(1471)"行（computed，跌价变动重算）。
  - 验证：vitest 覆盖 P6（净额=余额−跌价，重算正确）。
  - _Requirements: 1, 5_

- [x] 7. 明细表期后出库一键取数
  - 文件：`useF2DetailSheet.ts` + `F2DetailSheet.vue`。
  - `importPostPeriodOutbound()`：调 Task4 pull + ElMessageBox 预览（匹配 N/未匹配 M）+ 填 postPeriodQty/Amt（不覆盖非零提示）+ 只读守卫；工具栏加"取期后出库"按钮。
  - 验证：vitest（取数填充逻辑）+ 组件 transform 200。
  - _Requirements: 4_

- [x] 8. useF2CrossSheet 成本/产销存勾稽
  - 文件：`useF2CrossSheet.ts`。
  - 新增 `operatingCostReconcile`（消费 Task3）、`productionSalesIdentity`（期初+入−出=期末）、`costToPlReconcile`（在产品变动≈营业成本）；surface 到分析/审定区（差异警示色）。
  - 验证：vitest 覆盖 P11（恒等式差异计算；成本 diff）。
  - _Requirements: 3, 11_

### Wave 3 — 联动

- [x] 9. 减值测试 → K11 EventBus
  - 文件：`useF2Impairment.ts` / `useF2ImpairmentTest.ts` / `useF2ImpairmentReversal.ts`。
  - 计提/转回金额算出后 `eventBus.emit('impairment:calculated', { wpCode:'F2', accountCode:'1471', amount, ... })`；金额 0 不发；确认 `impairment:calculated` 在 `crossWpEventBridge.BRIDGED_EVENTS`。
  - 验证：vitest 覆盖 P7（0 不发；非 0 发一次含 1471）。
  - _Requirements: 6_

- [x] 10. 呆滞存货从库龄自动提候选
  - 文件：`useF2ObsoleteInventory.ts` + `F2TabObsoleteInventory.vue`。
  - `importCandidatesFromDetail()`：跨 F2-2~7 读 `-rows`，`isLongTermRow` 过滤，按名称汇总标"候选"，不覆盖已录；组件加"从明细带入候选"按钮。
  - 验证：vitest 覆盖 P8（仅超期行；不覆盖已录）。
  - _Requirements: 7_

### Wave 4 — 监盘 + 截止

- [x] 11. 抽盘汇总 → 账面核对回写
  - 文件：`F2TabStocktakeReconcile.vue` + `useF2StocktakeSheet.ts`（+ 读 F2-25 抽盘结果）。
  - `fillActualFromSample()`：读 F2-25 抽盘按名称匹配填 F2-24 实盘数 + 自动算账实差异 + 未匹配提示。
  - 验证：vitest 覆盖 P9（匹配填入；未匹配计数）。
  - _Requirements: 8_

- [x] 12. 截止三流日期 + 跨期勾稽面板
  - 文件：`useF2CutoffSheet.ts` + `f2CutoffSheetConfigs.ts` + `F2CutoffSheet.vue` + `useF2CutoffCrossSheet.ts`。
  - 行模型加 inspectDate/inboundDate 列；三日期差异 > N 天 row-class 标红；跨期面板 computed（笔数/金额）+ D4/D6 pull 优雅降级提示。
  - 验证：vitest 覆盖 P10（差异>阈值⟺标红；跨期笔数=跨期行数）。
  - _Requirements: 9_

### Wave 5 — NRV + 材料领用

- [x] 13. NRV 测算从 D4 pull 近期售价
  - 文件：`useF2ImpairmentTest.ts` + `F2TabImpairmentTest.vue`。
  - `pullRecentPrice()`（调 Task5），售价列旁"参考"提示，不覆盖手录；不可得优雅提示。
  - 验证：vitest（参考带入不覆盖）+ 组件 transform 200。
  - _Requirements: 10_

- [x] 14. F2-34 材料领用引导式弹窗
  - 文件：`F2MaterialUsageVoucherDialog.vue`（确认现有同名文件是否已实现，未实现则按 F2-33 范式建）+ `F2TabMaterialUsageCheck.vue` + 勾稽纯函数进 `useF2InspectionCheckFormulas.ts`。
  - 5 分组卡片（领料单/生产工单/记账凭证/核对项/结论）+ 实时勾稽 + 📎OCR（复用 contract-ocr）+ 视图切换（完整表格/逐笔核对）+ 卡片视图 + 操作列"核对"按钮；保存回写行并持久化。
  - 验证：vitest 覆盖 P12（勾稽状态与核对项一致；保存不丢字段）。
  - _Requirements: 12_

### Wave 6 — 风险信号

- [x] 15. F2 异常 → B50 风险信号
  - 文件：`useF2CrossSheet.ts` 或 `useF2OverallAnalysis.ts`（异常判定所在）。
  - 呆滞/减值异常/毛利率异常 computed 触发 → eventBus 风险信号（复用既有风险事件名，若无用 `risk:identified`，含来源 wpCode/描述）；无异常不发。
  - 验证：vitest（异常触发发信号；无异常不发）。
  - _Requirements: 13_

### Wave 7 — 验证

- [x] 16. 前端 vitest 全套
  - 补齐/运行 F2 相关 vitest（f2D4CostPull/f2LedgerPostOutbound/f2NrvPricePull/CrossSheet/Adjudication/ObsoleteInventory/Stocktake/Cutoff/InspectionCheckFormulas），P1-P12 全覆盖，全绿。
  - _Requirements: 全部_

- [x] 17. 后端 pytest
  - 运行 F2 render 预填 pytest（`_build_adjudication_prefill` P1/P2、related_parties 降级 P3），全绿；ast.parse 通过；后端重启健康。
  - _Requirements: 1, 2_

- [x] 18. Playwright E2E round-trip
  - 用已实例化 F2 项目（重药控股安徽 0ec33ac9 或其它含 F2 数据项目）实测关键路径：①F2-1 审定表 TB 预填回显 ②明细表取期后出库 ③减值→K11 事件 ④截止三流列 ⑤材料领用弹窗勾稽。0 console error（pre-existing SSE 噪声除外）。
  - _Requirements: 全部_

## Notes

- 所有跨底稿 pull 遵守 `h1CipH2Pull` 范式（wp-id-by-code + checklist-responses + 纯函数 + 容差 reconcile），优雅降级。
- 后端仅改 `_f2_inventory_main.py`（照 H2 范式），不新造 xlsx 列格式、不改架构。
- optional 任务同样执行完（本 spec 无 optional，全部为必做）。
- 标记完成前须 vitest/pytest 真实通过；关键路径 Playwright 实测，不假绿。
- 仅用 fs_write/str_replace 改代码文件，禁止 PowerShell Set-Content 破坏 UTF-8。
