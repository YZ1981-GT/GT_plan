# 设计文档：S4　公式设置的持久化 outbox（formula-settings-durable-outbox）

> 需求编号：requirements §1 五条记 R1（定义与 outbox 同事务）、R2（幂等 worker）、R3（扇出分批）、R4（过期标记进发布事务）、R5（P1-7 / P1-14 / P2-11 的其余修法）；§4 的四个写入方记 R6。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`，含 ADR-FHIC-04 报表域三个出口同事务标过期）。数字为 2026-10-29 现算。

## 0. 结论

现在每个写公式定义的路由都是「提交 → 调 `publish_events` 逐项目发 `FORMULA_CONFIG_CHANGED`」，失败只记 warning；事件总线派发时又会吞掉处理器异常，`on_formula_config_changed` 自己也吞。所以传播失败没有任何重试机会，界面也看不到。修法沿用平台已有的耐久事件机制（`workpaper_sync/outbox.py` 的做法，不建第二套事件表）：写入方在同一事务里登记「哪些项目的哪些公式位变了」并就地标过期，提交后有界并发地投递；投递直接调用传播处理器，失败就让该行保持可重试，成功经消费闸门只生效一次。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：发布成功但扇出失败会静默丢传播 | `publish_events` 的调用点 16 处 / 10 个路由文件（`report_config`×4、`formula_settings`×2、`formula_templates`×2、`report_config_baseline`×2、`consol_note_formulas`、`formula_logic_check`、`disclosure_notes`、`formula_audit_log`、`tb_detail_formulas`、`template_library_mgmt`；其中 `formula_settings` 与 `formula_templates` 各有一处是被多个端点共用的 `_emit`），全部在 `commit` 之后；`event_bus.publish` 失败只记 warning | 成立 |
| 2 | （交接未列）处理器失败也被吞 | `EventBus._dispatch` 对每个处理器 `except Exception` 后记日志并发 SYNC_FAILED 通知，不向调用方抛；`on_formula_config_changed` 自己再包一层 `except Exception` 记降级日志 ⇒ 即使事件发出去了，传播失败也无人重试 | 新增：只把「发事件」做耐久不够 |
| 3 | （交接未列）订阅者 | `FORMULA_CONFIG_CHANGED` 两个订阅者：`formula_settings.propagation.on_formula_config_changed`（按域传播）、`event_handlers._impl._stale_engine_on_formula_config_changed`（反向索引失效 + 依赖图按报表行标下游过期） | 新增 |
| 4 | R3：扇出无并发上限 | 每个项目一条事件，`publish` 经 500 ms 去抖后各自 `ensure_future` 并发派发，无上限；现有未删项目 85 个 | 成立 |
| 5 | R4：只有报表域在发布事务内标过期 | 整合树：报表域在 `publish_global` / `save_overrides` / `restore_global` 三个出口同事务调 `report_freshness.mark_changed`；底稿域（`working_paper.prefill_stale`）、附注域（`disclosure_notes.is_stale`）、合并附注域（`consol_note_data.is_stale`）都在提交后的处理器里标 | 成立 |
| 6 | R6：四个写入方只靠提交后传播 | `template_sync._apply`、`legacy_report.sync_project_to_global`、`apply_ops.apply_to_projects`、`project_ops.resolve_items` 改有效定义但不调 `mark_changed` | 成立 |
| 7 | R5（P2-11）：反向索引只在本进程失效 | `formula_reverse_index.invalidate_reverse_index()` 只把本进程单例置空，其他 worker 进程继续用旧索引 | 成立 |
| 8 | R5（P2-11）：前端保存后再发一次传播且吞错 | `FormulaManagerDialog.vue` 的 `propagateFormulaStale` 被 6 处保存入口调用，`POST linkageBus.impact`（`source_uri = FORMULA:{节点}::config_changed`），`validateStatus: s < 600` 且 `catch {}` | 成立 |
| 9 | 可复用的耐久机制 | `import_event_outbox`（通用：事件类型、项目、年度、载荷、状态、重试次数、末次错误）+ `import_event_consumptions`（消费闸门唯一索引）+ `event_outbox_dlq` + `outbox_replay_worker`（30 秒一轮、每轮 100 条、上限 20 次后进死信）；`workpaper_sync/outbox.py` 已按「不建第二套事件表」复用它们，提供只 flush 的入队、提交后发布、按事件类型登记的派发闸门 `GATED_FANOUT_EVENT_TYPES` | 新增：直接复用 |
| 10 | 真库 | V199 六表业务行 0（`formula_setting`、`formula_publish`、`formula_sync_item` 等都是 0）⇒ 改造期间没有存量传播要迁移 | — |

## 2. 架构裁定

**ADR-SDO-01 复用平台耐久事件表，新增公式设置门面。** 新模块 `backend/app/services/formula_settings/outbox.py`（≤ 300 行）：

- `record_changes(db, *, domain, events, source, publish_id) -> None`：`events` 即各服务现在返回给路由的「每项目变化的公式位」清单。逐项目在 `import_event_outbox` 入队一行（`event_type = FORMULA_CONFIG_CHANGED`、`payload = {domain, slot_keys, source, publish_id, row_codes?}`、只 flush），并在同一事务里调 ADR-03 的标过期；入队清单挂在 `Session.info`（键独立于底稿同步门面，互不干扰）。
- `publish_pending(db) -> PendingSummary`：路由 `commit` 之后调用；取本会话登记的行，交给后台有界并发投递（ADR-02），立即返回已登记条数，不等投递完成。
- `deliver(db, item)`：被 `ImportEventOutboxService._deliver` 按事件类型分派调用（见 ADR-02）。

所有写入方（§1 第 1、6 行全部，以及 `fill_all_formulas` 的调用方、`consol_note_settings` 旧端点、`cross_check_rules`、`note_settings`、`tb_detail`、`rollback`）改为：服务内产生 `events` 处调 `record_changes`；路由 `commit` 后调 `publish_pending`。`propagation.publish_events` 删除。AST 守卫：`publish_events(` 0 处；`report_freshness.mark_changed` 只允许在 `record_changes` 内调用。

**ADR-SDO-02 投递直接调用传播处理器，失败可重试、成功只一次（R2、R3）。** `ImportEventOutboxService._deliver` 遇 `FORMULA_CONFIG_CHANGED` 时不走事件总线（总线会吞异常），改调 `formula_settings.outbox.deliver`：

1. `begin_fanout`（`FORMULA_CONFIG_CHANGED` 加入 `GATED_FANOUT_EVENT_TYPES`，归属写在注释里）；抢不到 ⇒ 此前已成功，跳过。
2. 年度按 `fetch_project_audit_year` 现取（与总线 `_backfill_year` 同口径）。
3. 依次直接调 `propagation.HANDLERS[domain](project_id, year, slot_keys)` 与从 `_stale_engine_on_formula_config_changed` 抽出的 `stale_engine_for_formula_change(project_id, year, row_codes)`（两者内部不再吞异常）。
4. 任一步抛错 ⇒ `abort_fanout` 后原样上抛，`replay_pending` 把行标 `failed`、累加重试次数，到上限进死信；成功 ⇒ 用 `broadcast_raw("formula_settings.propagated", …)` 只通知前端。

原来的两个总线订阅保留给旧事件（`extra.origin` 不是本门面的值时），避免改动尚未迁移的发布方；本门面投递的事件不再经总线，不会被处理两次。有界并发：`publish_pending` 用一个进程内 `asyncio.Semaphore(settings.FORMULA_PROPAGATION_CONCURRENCY)`（默认 4），每条一个独立会话，处理完即提交；没处理完的由 `outbox_replay_worker` 下一轮接着做。worker 每轮按创建时间顺序串行投递，本身就是有界的。

**ADR-SDO-03 过期标记进发布事务（R4、R6）。** `formula_settings/stale_marks.py::mark_in_txn(db, domain, project_slots)`：

| 域 | 同事务标记 |
|---|---|
| report | `report_freshness.mark_changed`（母 spec ADR-04，搬到这里统一调用） |
| wp | 受影响底稿的 `working_paper.prefill_stale = true`（与 `propagate_wp` 同口径选底稿） |
| note | 受影响章节的 `disclosure_notes.is_stale = true`、`stale_source = 'formula_settings'` |
| consol_note | 受影响章节的 `consol_note_data.is_stale = true` |
| cross_check / push / tb_detail | 不标（这三域的结果由处理器重算覆盖；tb_detail 无消费方） |

对应的传播处理器去掉自己的标记步骤，只做物化与重算；为同一判据只留一份，选底稿 / 章节的函数从处理器里抽出共用。附注域的「标过期」写法以 S3 的单一写入口 `stale_state.mark_note_stale`（必填 `stale_source`）为准：S3 先落地则本表直接调用它；本 spec 先落地则 `mark_in_txn` 先写 `stale_source='formula_settings'`，S3 落地时改为调用 `stale_state`（谁后落地谁接线）。合并附注与底稿预填两张表没有来源列（S3 design §4 D4），按本表只置过期标记，不经 `stale_state`。

**ADR-SDO-04 反向索引跨进程失效（R5）。** `invalidate_reverse_index()` 除置空本进程单例外，`INCR` Redis 键 `formula:reverse_index:version`；取索引时比较本进程记下的版本号（结果缓存 5 秒），不同即重建；Redis 不可用时退回 60 秒定时重建，并在日志里记一次降级。

**ADR-SDO-05 只留后端传播（R5）。** 删除前端 `propagateFormulaStale` 及 6 处调用；它做的「依赖图标下游过期」由 ADR-02 第 3 步的 `stale_engine_for_formula_change` 在后端做一次。实施时先现读该前端调用传的节点键与后端按公式位推出的报表行 URI 是否覆盖同一范围，有差集先补后端再删前端。vitest 守卫：`FormulaManagerDialog.vue` 不得再调用 `linkageBus.impact`。

**ADR-SDO-06 传播状态可见（R5）。** 项目有效定义端点（`GET /api/projects/{pid}/formula-settings/{domain}`）响应增 `propagation{pending, failed, last_error, oldest_pending_at}`（只统计本项目本域）；公式管理中心有 pending / failed 时在顶栏显示「公式变更还在传播 / 有 N 条传播失败（将自动重试）」。admin 可在现有 `performance` 路由的 outbox 重放接口按 `scope` 重放；不新增手动重试端点。

**ADR-SDO-07 发布循环分批：先量后改（R5）。** P2-11 的「发布请求内逐条读写、持有域排他锁，P=1000 估 7~35 秒」是估算，现有 85 个项目、V199 六表 0 行。任务 6 在回滚事务内用合成的 200 / 1000 个【测试】项目各测一次 `publish_global` 耗时与锁持有时间；1000 个项目时超过 5 秒才实施分批 upsert（每批 200 个项目、批间不放锁），否则记录测量结果、不改代码。

## 3. 测试与变异

- 单元（SQLite）：`record_changes` 在回滚后不留行；每个写入出口都入队（参数化 12 个出口）；`mark_in_txn` 四个域各一组；`publish_pending` 并发不超过上限（假处理器计并发峰值）；投递失败 ⇒ 行 `failed`、消费行被归还；重放成功 ⇒ 处理器副作用只出现一次（计数器）。
- 真 PG（回滚事务内【测试】项目）：全局发布后提交前 outbox 已有对应行、标记已落；注入处理器异常后重放一次成功、`import_event_consumptions` 恰一行。
- AST 守卫：`publish_events(` 0 处；`mark_changed` 调用点只在 `record_changes`；`_deliver` 对 `FORMULA_CONFIG_CHANGED` 不调用 `event_bus.publish*`。
- 前端：vitest 守卫（不再调用 `linkageBus.impact`）；顶栏传播状态显示两态。
- 跨进程反向索引：两个独立 Python 进程（子进程）共用 Redis 15 号库，一个失效后另一个下次取索引即重建。
- 磁盘变异：入队挪到 `commit` 之后 ⇒「回滚后不留行」用例红；投递改回经事件总线 ⇒ 失败重试用例红；去掉 `begin_fanout` ⇒ 副作用只一次用例红；去掉版本号比较 ⇒ 跨进程用例红。

## 4. 风险与待拍板

| # | 事项 | 处理 / 建议 |
|---|---|---|
| D1 | 复用 `import_event_outbox` 后，导入域的积压时长指标（`event_cascade_health_service`）与重放开关 `LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED` 同时覆盖公式事件 | 建议接受（同一套耐久事件，一处可观测）；配置说明与健康页文案改成「耐久事件」 |
| D2 | 处理器改为不吞异常后，原先「失败只记降级日志」的传播失败会进重试与死信 | 预期行为；死信条数进现有指标 |
| D3 | 与 S1 的先后 | 本 spec 先做（交接 §2 的建议）；S1 改写入路径时直接调用 `record_changes` |
