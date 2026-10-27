# 实施计划：序时账增量追加改为真追加（ledger-incremental-append-true-merge）

> 以 design.md 为准。标完成须有代码 + 测试证据 + 至少一条磁盘变异证明（备份到 `tmp_ledger_append/mutations/`，注入、确认红在预期处、逐字节还原核对 sha256）。环境做不到的标 `[ ]*`。约束同 `voucher-identity-writeback-and-audit-phase/tasks.md` 页头；临时产物放 `tmp_ledger_append/`。依赖：凭证差异报告用 `voucher_identity.py`（该 spec 任务 2），未落地则按其 design §2 先建。

- [ ] 1. 合并函数与表归类清单（需求 1、5.2，ADR-LA-02/03/05）
  - 新建 `ledger_dataset_merge.py`：`merge_into_staged`、`DATASET_BOUND_TABLES`、行数守恒检查
  - Files: `backend/app/services/ledger_dataset_merge.py`、`backend/tests/test_ledger_dataset_merge.py`、`backend/tests/test_dataset_bound_tables_classified_pg.py`
  - Verify: 两策略月份集合、整表沿用、基准变化报错、守恒不等阻断；归类守卫与 information_schema 逐一相等。变异：覆盖策略复制重叠月 → 守恒用例红；清单删 `account_chart` → 守卫红

- [ ] 2. 两条导入链接入与提交参数（需求 1.1、1.5、2.1、2.2，ADR-LA-04）
  - `options.append = {strategy, base_dataset_id}`：两个提交入口写入、runner 透传；`execute_pipeline` 与 `smart_import_streaming` 激活前调用合并；MergeReport 写 staged `source_summary`
  - v2 提交删掉 `apply_incremental` 分支；`/ledger/smart-import` 增 `append_strategy`（`ledger_penetration.py` 净增 0 行）
  - Files: `ledger_import/pipeline.py`、`smart_import_engine.py`、`import_job_runner.py`、`ledger_import_application_service.py`、`ledger_import/orchestrator.py`、`routers/ledger_import_v2.py`、`routers/ledger_penetration.py`
  - Verify: 两条链各一例：追加后 staged 含继承月份、`source_summary` 记录完整；基准在提交后被别的导入替换 → 报错不激活。变异：去掉激活前基准断言 → 用例红

- [ ] 3. 删除导入前删行、余额表沿用闸门（需求 2.3、3）
  - `/ledger-data/incremental/apply` 返回 410；删除 `apply_incremental`（删前 grep 调用方，保留 `compute_incremental_diff`）；`/incremental/detect` 增「将继承月份」
  - 激活闸门：余额表沿用且序时账新增月份 → L2 警告需确认留痕
  - Files: `routers/ledger_data.py`、`ledger_data_service.py`、激活评估（`ledger_import/validator.py` 或旧链对应处）
  - Verify: 410 端点测试；闸门未确认不激活、确认后留痕。变异：闸门判断取反 → 用例红

- [ ] 4. 凭证差异报告（需求 4，ADR-LA-06）
  - 新建 `ledger_dataset_voucher_diff.py`，两条链激活前调用（追加与整年重导都生成），fail-open 记原因
  - Files: `backend/app/services/ledger_dataset_voucher_diff.py`、`backend/tests/test_ledger_dataset_voucher_diff.py`
  - Verify: 新增 / 删除 / 变化三类与按月汇总；同日同号不同凭证字不误判。变异：签名去掉金额 → 变化用例红

- [ ] 5. 前端入口与提示（需求 2.2~2.4、1.6、3.1、4.2）
  - 数据管理弹窗去「执行清理」、预览四类月份、带策略进入上传；序时账页与导入页提交带 `append_strategy`；完成页显示合并结果、余额表沿用提示、差异报告
  - Files: `LedgerDataManager.vue`、`LedgerPenetration.vue`、`useLedgerImport.ts`、`ImportCompletionSummary.vue`、`services/ledgerImportV2Api.ts`
  - Verify: 组件单测（预览与提交参数）；ESLint；单区域 vue-tsc

- [ ] 6. 端到端验收（需求 5.1、6）
  - `test_ledger_append_e2e_pg.py`：导入 1~11 月 → 追加 12 月（覆盖 / 跳过）→ 12 个月可见 → 回滚后逐表行数与金额一致；和平药房规模耗时记录（design §3）
  - 【测试】项目浏览器全流程，清理对账；变异记录汇总；干净 worktree 跑要提交的树；INDEX.md 登记
