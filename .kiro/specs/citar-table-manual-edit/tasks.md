# 任务：CITAR 表格数据可人工编写修改保存

- [x] 1 税审底稿 / 申报表手工值盖过公式（R1）
  - [x] 1.1 `TaxWorkbook.evaluate` / `cell_value` 手工值优先 + `results.auto`；`save_sheet_inputs` 放开公式格；`compute_sheet` 给 `auto`
  - [x] 1.2 生成器：被公式引用 / 值为 0 的数字常量格 + 报告正文 F17~F41 加 `ref` + `role: 'c'`（71 格，22 个结构文件），`--src` 重生成
  - [x] 1.3 前端 `TaxWorkpaperGrid` / `useTaxSheetEditor`：f / c 格可改、恢复自动值、标记与悬停；底稿页与申报表页接线
  - [x] 1.4 测试：`test_tax_formula_engine` 4 例（下游传播 / null / 预置常量 / 环）、接口覆盖与恢复、申报表公式格改为可改；前端 `useTaxSheetEditor.spec.ts` 3 例
- [x] 2 报告正文 25 行金额可改（R9）：`build` 带 row / manual / auto / amounts_version、`PUT report-body/amounts`（只改 F17~F41、不冲 1-01 其他手工值）、`CitarReportBodyAmounts.vue` + 测试
- [x] 3 审核说明段落改 / 删 / 恢复（R8）：`layout(rules, edits)` + `layout_with_edits`（deleted / orphans）、`__review_notes__`、`PUT review-notes`、前端逐段修改 / 删除（二次确认）/ 恢复 + 测试（纯函数 4 例 + 接口 1 例）
- [x] 4 审定报表手工值（R6）
  - [x] 4.1 V260 / R260 + ORM `manual_amounts` + schema `ReportRow.manual_amounts`
  - [x] 4.2 `report_manual_values`（apply_auto / effective / save_manual）；生成 / 增量 / 过期重算三个写入点保留手工值、合计 / 上期按手工值（`PriorPeriodResolver.override`）；`PUT /api/reports/{pid}/{year}/manual`
  - [x] 4.3 前端 `CitarAmountCell` + `useCitarAmountDrafts`、`CitarReportTable` 可编辑、审定报表页保存 / 放弃（有草稿时禁用重新生成）
  - [x] 4.4 测试 `test_report_manual_values.py` 4 例（重新生成保留 + 合计 / 上期合计、数据变化 auto 刷新、恢复、增量与过期重算、清空、接口 409 / 422 / 403）；磁盘变异（ROW 缓存改回自动值）打红后复原
- [x] 5 单体财务报表手工值（R7）：`compute_statement(..., overrides)` + 合计行可改、生效值 / 自动值各算一份、`__fs__`、`PUT financial-statements`（标题 / 说明行拒收）、CAS 行带 row_code + manual 走 §4；前端 `CitarAmountCell` 接线（两种来源分别保存）；测试纯函数 1 例 + 接口 1 例（合计、平衡校验、导出、恢复、422 / 403）
- [x] 6 余额表 / 序时账可改（R3 R4 R5）
  - [x] 6.1 V260 `ledger_manual_edits` + ORM `LedgerManualEdit` + `ledger_edit_service`（末级校验、上级按借正贷负差额同步、按行原有存法写回、恢复取首次修改前值、日志时间应用写且递增）
  - [x] 6.2 路由 `ledger_edits.py`（已注册）：PUT 余额行 / 序时账行、restore、manual-edits 列表与汇总；余额接口行带 id；余额修改后 `full_recalc` + 清穿透缓存 / 试算表缓存 + 发 `TRIAL_BALANCE_UPDATED`；合并锁检查
  - [x] 6.3 前端余额表 / 序时账行内编辑、已修改 / 下级已修改标记、只看已修改、恢复（二次确认）；导入页「当前账套有人工修改」提示
  - [x] 6.4 测试 `test_ledger_manual_edits.py` 4 例：末级改后上级同步 + 试算表未审数变化 + 恢复原值、非末级 / 合成行拒收、序时账改与恢复、读只读 / 写 403
- [x] 7 试算表改审定数 → 调整分录草稿（R2）：`citarTbAdjust.ts` 纯函数（差额方向、借贷平衡、校验）+ `CitarTbAdjustDialog`（POST /adjustments AJE 草稿）；两张表的审定数可点、标「待批 N」（草稿 / 待复核 / 驳回）；期初 / 发生额悬停指向科目余额表；测试 `citarTbAdjust.spec.ts` 5 例
- [x] 8 回归：后端改动模块 13 个测试文件 402 passed / 0 failed；前端 4 个 spec 20 passed；单区域 vue-tsc（`tsconfig._table-manual-edit.json`）只余 1 条 HEAD 同现诊断（`LedgerImportDialog.vue` ConfirmedMapping 两份类型不一致，非本 spec 文件），注入 TS2322 变异能报出；V260 已用 `MigrationRunner.run_pending` 落本地库
- [x] 9 浏览器实测（V3，真后端 + 真库 ABC餐饮_2025，独立无头 Playwright 脚本）：审核说明（改段 → 保存 → 刷新仍在 → 恢复）、报告正文金额（改 → 刷新仍在、标原值 → 恢复）、审定报表（改货币资金 → 合计重算 → 刷新仍在、悬停自动值 → 恢复）、单体财务报表、税审底稿公式格（悬停「原公式值」→ 恢复）、序时账（改摘要 → 已修改 → 恢复）、试算表（弹窗差额 5,912.83 = 2,000,000 − 1,994,087.17 → 生成 AJE 草稿 → 「待批 1」）全部通过，页面无报错。实测抓到并修了 2 处：①审定报表恢复全部手工值后库里存 JSON null（`IS NOT NULL` 恒真）⇒ 列改 `JSONB(none_as_null=True)` + `load_manual` 只认有列的值 + 测试加 SQL 层断言（去掉修复的变异打红）②试算表弹窗内容未套 CITAR 样式、关闭动画期间内容先变空 ⇒ 弹窗引入 citar-data 样式、按钮移进正文、内容用打开时的副本。复原：调整分录草稿经平台删除接口删、BS-002 经恢复接口恢复、实测新建的 4 行空手工值与 2 条修改日志删除；与实测前留底逐项对账 6/6 一致
- [x] 10 收尾：V260 已用 `MigrationRunner.run_pending` 落本地库；`report_models.py` 801 行登记白名单（HEAD 800）；回归 15 个后端测试文件 449 passed / 2 failed（`test_lazy_import_resolvability` 两例，指向 `ai_content.py` / `consol_note_template_push_service.py` / `note_section_pairing.py` 的不存在模块，三个文件本 spec 未改、HEAD 原样存在，与本 spec 无关）；探针在仓库外 `D:\gtt\probe`

## 待用户决定（本 spec 范围外，未改）

- `import_templates.py` 调用不存在的 `TrialBalanceService.upsert_trial_balance_row`：平台统一导入的「试算表导入」逐行失败被吞
- 重新导入账套后，余额表 / 序时账的人工修改不带到新数据集（按设计；导入页已提示）
- 审定报表上期取自上年项目已生成报表时，上期合计照搬上年报表、不按本年手工明细重加（需要时手工改合计行）
