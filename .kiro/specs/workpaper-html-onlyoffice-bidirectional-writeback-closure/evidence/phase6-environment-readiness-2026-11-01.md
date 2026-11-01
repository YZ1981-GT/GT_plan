# 环境就绪核查（2026-11-01，只读）

用户确认「环境都在」后做的现场核查。**这不是验收**，只是把 6.3 / 6.4 / 写共享 PG 所需的
前置事实钉下来，省掉下一轮重新摸底。探针：`tmp_workpaper_sync_impl/probe_env2.py`。

## 1. 服务

| 项 | 实测 |
|---|---|
| 后端 `/api/health` | `status=degraded`，但 `services={postgres: ok, redis: ok}` |
| 启动编排 | 41 个任务全 `ok`，`failed=[]`，唯一 `skipped=["run_migrations"]`（`GT_BOOTSTRAP_DONE=1`） |
| 热重载 | `mode=overlap`，`primary_state=ready`，最近一次 `result=ok`（`spawn_to_ready 7.39s`） |
| OnlyOffice | 容器 `audit-onlyoffice` healthy，`/healthcheck` 返 `true` |
| 前端 | `http://127.0.0.1:3030/` 200 |

🔴 `degraded` 的具体来源**未定位**：`health.data` 里还有 `audit_chain` / `audit_log` /
`events` / `gc` / `migration` / `schema_drift` 六个分项没取，`services` 两项都是 ok。
做真实验收前要先确认 degraded 不是来自同步链相关的分项，否则验收结果无法归因。

🔴 `run_migrations` 被 `GT_BOOTSTRAP_DONE=1` 跳过 = **启动后新加的 `V*.sql` 不会落到本地库**
（仓库铁律）。本 spec 当前不新增迁移，但若后续需要，必须全量重启 `start-dev.bat` 或手动
`MigrationRunner(...).run_pending()`。

## 2. 共享 PG（`audit_platform`）

| 事实 | 值 |
|---|---|
| 未删除项目 | 20 |
| 其中【测试】项目 | **3** |
| `working_paper_content_representation` 行数 | 455 |
| 其中不同 `entry_id` | 90 |
| 其中不同 `wp_id` | 93 |
| `working_paper_sync_test_run` 行数 | **0** |

🔴 **`sync_test_run` 为 0** 是对 6.1 / 6.2 的硬事实：当前库里**一条真实验收 run 都没有**，
所以 readiness 的 `acceptance.state` 对全部 entry 都只能是 `missing`。6.2「从 PG 现算
acceptance」现在能跑但分母为空；6.1 的 required scenario set digest 也没有任何 run 可比对。
⇒ 这两项必须排在 6.3（真实 OnlyOffice 往返，产出第一条 run）**之后**，顺序不能按编号。

🔴 两处表名教训（本轮各踩一次）：真实表名是 `working_paper_content_representation` 与
`working_paper_sync_test_run`（**不是** `workpaper_*`）。首版探针凭名字猜，PG 报
`UndefinedTable` 后事务 aborted，后面三条查询连带全挂 —— 这正是「每条查询独立事务」那条
铁律的现场。表名一律从 ORM 的 `__tablename__` 取。

## 3. 据此得出的执行顺序

1. **先** 6.3：在【测试】项目逐 entry 跑真实 OnlyOffice required scenarios ⇒ 产出第一批
   `sync_test_run`；
2. **再** 6.1 / 6.2：有 run 之后 required scenario set 与 acceptance 现算才有分母；
3. 写共享 PG 的三类（25 条 representation-only rehash / 19 条重投影 / 14 条首版）按
   「先【测试】项目、逐条复验、每条记迁移前后 generation 与 content_revision」推进；
   重投影会**推进 content revision**，与 rehash 风险不同，两类不可混批。

## 4. `degraded` 已定位：`schema_drift.critical_count = 6`，且与同步链无关

探针 `tmp_workpaper_sync_impl/probe_drift.py` 直接查 `schema_drift_log`，按
`CRITICAL_DRIFT_TYPES`（`orm_extra` / `enum_mismatch` / `checksum_drift` —— health 的
degraded 判定只引用这三类）取明细。6 条逐项如下：

| # | 表 / 迁移 | 列 | 类型 | 归属 |
|---|---|---|---|---|
| 1 | `attachment_lineage` | `project_id` | `orm_extra` | 附件系列 spec |
| 2 | `financial_report` | `calc_error` | `orm_extra` | 公式中枢 spec |
| 3 | `financial_report` | `calc_version` | `orm_extra` | 公式中枢 spec |
| 4 | `formula_sync_item` | `revision` | `orm_extra` | 公式设置 spec |
| 5 | `V227__project_creation_grants.sql` | — | `checksum_drift` | 批量建项授权 spec |
| 6 | `V228__project_creation_grant_uscc_checksum.sql` | — | `checksum_drift` | 批量建项授权 spec |

**判定：`touches_sync_tables = []`** —— 把 `workpaper_sync_models` 里 29 个 ORM 的
`__tablename__` 全取出来做交集，6 条 critical 一条都不落在同步链表上。

成因是「`run_migrations` 被 `GT_BOOTSTRAP_DONE=1` 跳过」：并发会话加了 ORM 列与 `V*.sql`，
开发服务器热重载不跑迁移 ⇒ ORM 有列、DB 没有 ⇒ `orm_extra`。两条 `checksum_drift` 是
V227 / V228 应用后又被编辑。**全部不属于本 spec**，本 spec 也不新增迁移。

⇒ 结论：6.3 / 6.4 的真实验收**可以照常做**，`degraded` 不会污染归因。但报告里要写明
这 6 条的存在与归属，否则读者会把 degraded 当成同步链的问题。修它们要分别由那三个
spec 的负责人全量重启 `start-dev.bat`（或按号补迁移 / 登记 drift ledger），不在本 spec 范围。
