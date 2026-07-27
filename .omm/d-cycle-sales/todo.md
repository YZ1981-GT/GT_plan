# 待办（D 循环）

## 尚未闭环

- **D2 披露导入导出的取数派生区块**：账龄表 / 分类表 / 坏账变动是取数派生 + 手工覆盖，明确不在导入导出范围（已写进编制说明），若要纳入需先定"覆盖 vs 仅填空"语义。
- **四表取数灰度未开启**：`D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False，是否按循环灰度开启（建议先开 D6）待定。
- **D5/D6/D7 的 `import-aux-balance` 端点 SQL 列名错误**（用了不存在的 `period_type`/`balance`，真实列是 `opening_balance`/`debit_amount`/`credit_amount`/`closing_balance`）→ 这三个端点运行时必 500，属平台级 pre-existing 缺陷，未修。
- **D4 未见 TB 回写**：`useD4FormData` 中没有 `trial-balance/writeback` 调用（D1/D3/D5/D6/D7 都有）。是设计如此（损益类由报表取发生额）还是缺口，待核实。

## 可增强

- D2/D3 明细表 → 序时账取数（目前部分依赖手工录入 + 辅助余额导入）
- D 循环各明细表接入"受 N 笔集中调整影响"标注（行级 `matchByAccount` 仅适用行带标准科目码的表，D 循环多数明细表按业务对象组织 → 应走表级科目 banner 而非行级）
- 抽凭引擎在 D 循环的接入率核查（各检查表是否都用了正确 API：`account-code` 单数 + `phase=final` + `workpaper-id` + `year`）
