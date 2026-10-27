# 设计文档：序时账增量追加改为真追加

需求编号见 requirements.md；现状事实只在 requirements 的 F 表。

## 1. 架构决策

**ADR-LA-01 合并在 staged 数据集内完成，不动基准版本。** 否决「往 active 数据集里补行」：会破坏版本不可变与回滚，导入失败时 active 已被改。否决保留 `apply_incremental` 先删后导：F3 的数据丢失风险。

**ADR-LA-02 一个合并函数服务两条导入链。** 新模块 `backend/app/services/ledger_dataset_merge.py`：

```
merge_into_staged(db, *, staged_id, base_id, project_id, year, strategy) -> MergeReport
  1. 断言 base 仍是 (project, year) 的 active（否则 BaseChangedError）
  2. F = staged 序时账月份；B = base 序时账月份（两者都按 EXTRACT(MONTH FROM voucher_date)）
  3. 按月合并表：
       overwrite：复制 base 中月份 ∈ B − F 的行
       skip     ：删 staged 中月份 ∈ F ∩ B 的行；复制 base 中月份 ∈ B 的行
  4. 整表沿用表：staged 该表 0 行 → 复制 base 全部行，记 carried=True
  5. 复制用 INSERT … SELECT（新 id = gen_random_uuid()，dataset_id = staged，import_batch_id = 本次新建的「追加继承」批次）
  6. 返回 MergeReport{strategy, base_id, file_months, carried_months, dropped_months, tables:{名: {copied, carried}}}
```

PG 专有写法（`gen_random_uuid`、`EXTRACT`）按方言判断；SQLite 测试走等价的 ORM 路径。

**ADR-LA-03 表归类清单单一来源。** `DATASET_BOUND_TABLES = {periodic: (tb_ledger, tb_aux_ledger), snapshot: (tb_balance, tb_aux_balance, account_chart, direction_override), not_import_product: (activation_records, sampling_records, workpaper_row_name_mapping_target, _sign_migration_backup)}`。守卫查 information_schema 全部带 `dataset_id` 的表，与清单三组并集逐一相等（需求 6.2）。`account_chart` 只复制 `source = client` 的行。

**ADR-LA-04 基准版本在提交时冻结。** 提交追加时读当前 active id 写进作业 `options.append.base_dataset_id`；合并与激活前各断言一次（需求 1.5）。v2 已有「同项目同年度进行中作业 409」护栏，旧智能导入链在提交时同样检查进行中作业。

**ADR-LA-05 行数守恒闸门。** 激活前算 `expected = |base 行| − |被覆盖或丢弃的月份行| + |文件保留月份行|`，与 staged 实际行数比较，不等即阻断（需求 5.2），按表逐个比较。

**ADR-LA-06 凭证差异报告用凭证键聚合。** 每版本按凭证键 `GROUP BY` 出每张凭证的分录签名（`md5(string_agg(科目|借贷栏|金额 ORDER BY …))`），两版本 FULL JOIN：一侧缺 = 新增 / 删除，签名不同 = 变化；按月汇总张数与金额，各类前 20 个样例。只读；放在激活前执行，失败 fail-open 并把原因写入报告（需求 4.2）。整年重导同样生成。

## 2. 改动矩阵

| 位置 | 改动 | 需求 |
|---|---|---|
| 新 `services/ledger_dataset_merge.py` | ADR-LA-02/03/05 | 1、5.2 |
| 新 `services/ledger_dataset_voucher_diff.py` | ADR-LA-06（import `voucher_identity`） | 4 |
| `ledger_import/pipeline.py` | 写入完成后、`evaluate_activation` 前：`options.append` 存在则调 `merge_into_staged`；然后调差异报告；把 MergeReport 与差异写入 staged `source_summary` | 1、2.1、4 |
| `smart_import_engine.smart_import_streaming` | 激活前同上 | 2.1 |
| `import_job_runner.py` | 把 `options.append` 传给两条链 | 2.1 |
| `ledger_import_application_service.submit_import_job`、`ledger_import/orchestrator.submit` | 接收 `append`（strategy），读取 active 写 `base_dataset_id`；无 active 时按普通导入并提示 | 2.2、ADR-LA-04 |
| `routers/ledger_penetration.smart_import`、`routers/ledger_import_v2.submit` | 新表单 / 字段 `append_strategy`；v2 删掉调用 `apply_incremental` 的分支（`ledger_penetration.py` 净增 0 行：参数并入已有 Form 解析） | 2.2、2.3 |
| `routers/ledger_data.py` | `/incremental/apply` → 410；`/incremental/detect` 增「将继承月份」预览 | 2.3、2.4 |
| `ledger_data_service.apply_incremental` | 删除（删前 grep 调用方）；`compute_incremental_diff` 保留 | 2.3 |
| 激活闸门 | 余额表沿用 + 序时账新增月份 → L2 警告，须 `force_submit` 式确认留痕 | 3.1 |
| 前端 `LedgerDataManager.vue` | 去「执行清理」；预览四类月份；进入上传时带策略 | 2.3、2.4 |
| 前端 `LedgerPenetration.vue` / `useLedgerImport.ts` | 追加模式提交带 `append_strategy`；提示语改为如实描述 | 2.2、2.4 |
| 前端 `ImportCompletionSummary.vue` 等完成页 | 显示合并结果、余额表沿用提示、差异报告 | 1.6、3.1、4.2 |

行数门：`ledger_penetration.py` 现 1714 行、上限约 1715，只改参数解析不增行；`smart_import_engine.py`（3155 行）在白名单内，新增逻辑只留一行调用。

## 3. 性能

复制在单条 `INSERT … SELECT` 内完成，按表分批提交进度（复用导入进度回调）。和平药房基准：序时账 114.7 万、辅助明细账约 273 万行；验收记录实测耗时与 PG 临时空间，超过 5 分钟则改为按月分批复制。差异报告只读两版本的凭证级聚合，不拉明细到 Python。

## 4. 测试与验收

- `test_ledger_dataset_merge.py`（SQLite 等价路径）：覆盖 / 跳过两策略的月份集合、整表沿用、基准变化报错、行数守恒闸门。
- `test_ledger_append_e2e_pg.py`（pg_only，在【测试】项目或回滚事务内）：需求 6.1 全流程，含回滚后逐表行数与金额合计一致。
- `test_dataset_bound_tables_classified_pg.py`：ADR-LA-03 守卫。
- `test_ledger_dataset_voucher_diff.py`：新增 / 删除 / 变化三类与按月汇总；同号不同凭证字不误判。
- 变异：覆盖策略复制范围改成 B（含重叠月）→ 行数守恒用例红；去掉基准断言 → 并发用例红；清单删去 `account_chart` → 归类守卫红；差异签名去掉金额 → 变化凭证用例红。
- 浏览器（chrome-devtools，【测试】项目）：数据管理 → 增量追加 → 预览四类月份 → 上传 12 月 → 完成页合并结果与差异报告 → 序时账 12 个月可查 → 回滚。

## 5. 风险

| 风险 | 处理 |
|---|---|
| 两条导入链行为不一致 | 合并只在共享函数里；两条链各一例端到端 |
| 追加期间另一导入完成 | ADR-LA-04 双重断言，报错让用户重来 |
| 余额表沿用导致试算表口径落后 | 需求 3 强制确认 + 界面常驻提示 |
| 复制大表耗时 | §3 实测；超阈值按月分批 |
