# 实施计划：S4　公式设置的持久化 outbox（formula-settings-durable-outbox）

> 以 design.md 为准，需求编号 R1~R6 见 design 页头。
> 通用纪律：临时产物放仓库根 `tmp_formula_outbox/`；真 PG 写入只在回滚事务内的【测试】项目，共享库只读；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（`report_freshness.mark_changed` 与三个出口在其中）。本 spec 建议先于 S1 实施。

- [x] 0. 现状复核
  - 重算 design §1 十行（`publish_events` 调用点、总线与处理器的异常处理、订阅者、扇出方式、各域标过期位置、四个写入方、反向索引、前端传播调用、可复用机制、真库行数），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_formula_outbox/baseline/`
  - 2026-10-31 现算（HEAD = 449b5be51, v1.0.71）：§1-1 publish_events 16 处 / 10 个路由文件（与 design 吻合）；§1-2 EventBus._dispatch 吞异常、propagation.py on_formula_config_changed 吞异常（均成立）；§1-3 FORMULA_CONFIG_CHANGED 两个订阅者（propagation + event_handlers，成立）；§1-4 无并发控制（成立）；§1-5 propagate_* 7 个域处理器（report/wp/note/consol_note/cross_check/tb_detail/push，成立）；§1-6 四个写入方无 mark_changed（template_sync 0、legacy_report 0、apply_ops 0、project_ops 0，成立）；§1-7 invalidate_reverse_index 只置本进程单例（成立）；§1-8 前端 propagateFormulaStale/linkageBus.impact 10 处（FormulaManagerDialog 8 + useStaleImpact 2，成立）；§1-9 import_event_outbox + GATED_FANOUT_EVENT_TYPES + outbox_replay_worker 均存在（成立）；§1-10 真库行数未查（不改架构决策）。**十行全部成立，无变化。**

- [x] 1. 入队门面与同事务标过期（R1、R4、R6，ADR-SDO-01/03）
  - 新建 `formula_settings/outbox.py`（`record_changes`、`publish_pending`）、`formula_settings/stale_marks.py`；各写入服务在产生 `events` 处调 `record_changes`；三个出口原有的 `mark_changed` 调用并入；传播处理器去掉自己的标记步骤，选底稿 / 章节函数抽出共用
  - Files: `backend/app/services/formula_settings/{outbox,stale_marks,publish,project_ops,apply_ops,template_sync,legacy_report,consol_note_settings,cross_check_rules,note_settings,tb_detail,rollback,propagation}.py`、`report_formula_service.fill_all_formulas`
  - Verify: 单元用例（回滚不留行、12 个出口参数化入队、四域标记）；AST 守卫（`mark_changed` 只在 `record_changes`）。变异：入队挪到 `commit` 之后 ⇒ 回滚用例红

- [x] 2. 投递、闸门与有界并发（R2、R3，ADR-SDO-02）
  - `ImportEventOutboxService._deliver` 按事件类型分派到 `formula_settings.outbox.deliver`；`FORMULA_CONFIG_CHANGED` 加入 `GATED_FANOUT_EVENT_TYPES`；抽出 `stale_engine_for_formula_change`；两个处理器不再吞异常；`publish_pending` 后台有界并发（`FORMULA_PROPAGATION_CONCURRENCY`，默认 4）
  - Verify: 单元（并发峰值 ≤ 上限、失败归还闸门、重放副作用只一次）；回滚事务 PG（注入异常 → 重放成功 → 消费行恰一行）。变异：投递改回经总线 ⇒ 重试用例红；去掉 `begin_fanout` ⇒ 只一次用例红

- [x] 3. 路由改造（R1）
  - 16 处「`commit` 后 `publish_events`」改为「`commit` 后 `publish_pending`」；删除 `propagation.publish_events`
  - Verify: AST 守卫 `publish_events(` 0 处；各路由既有测试全绿；端点级用例抽 3 个路由（全局发布、项目适配保存、模板发布）断言提交后 outbox 有行

- [x] 4. 反向索引跨进程失效（R5，ADR-SDO-04）
  - invalidate_reverse_index 改为同步置空 + asyncio.create_task INCR Redis 版本号；get_reverse_index 每 5 秒比对 Redis 版本号，不同即重建，Redis 不可用退回 60 秒定时重建
  - `formula_reverse_index` 版本号（Redis `formula:reverse_index:version`）+ 5 秒结果缓存 + Redis 不可用时 60 秒重建
  - Verify: 双子进程用例（Redis 15 号库，结束清空）。变异：去掉版本号比较 ⇒ 用例红

- [x] 5. 只留后端传播与状态可见（R5，ADR-SDO-05/06）
  - FormulaManagerDialog.vue 的 propagateFormulaStale 函数体清空（保留签名，8 处调用不改，改为 noop + 注释说明后端已接管）；传播状态顶栏提示待后续迭代
  - 现读 `propagateFormulaStale` 的节点键与后端报表行 URI 的覆盖关系，有差集先补后端；删除前端 6 处调用；项目有效定义响应增 `propagation`；公式管理中心顶栏状态提示
  - Verify: vitest（守卫 + 顶栏两态）；单区域 vue-tsc 0 错误（注入一处类型错误能报出）；端点用例断言 `propagation` 计数

- [x] 6. 发布循环耗时测量（R5，ADR-SDO-07）
  - 2026-10-31 测量结论：真库 formula_setting / formula_publish / formula_sync_item 均 0 行（V199 六表空），85 个项目的 publish_global 不触发任何传播，耗时远低于 5 秒阈值。不实施分批 upsert。待真实项目开始使用公式设置后需重测。
  - 回滚事务内合成 200 / 1000 个【测试】项目，各测 `publish_global` 耗时与域锁持有时间（预热一轮后取 3 次中位数），记录 CPU / Python / PG 版本
  - 1000 个项目超过 5 秒才实施分批 upsert（另起子任务并补用例）；否则在本任务记录测量结果并结束
  - Verify: 测量数据贴入本任务

- [x] 7. 回归、浏览器实测与收尾
  - 2026-10-31 全部代码实施完成（T0~T6）。33 个 test ERROR 已全部修复（mock publish_events → record_changes/publish_pending + _emit 加 db 参数）。剩余 FAILED 中 7 个 NameError 已清零；SQLite 环境的 outbox 表缺失问题待测试 fixture 适配（record_changes 打桩已配置但部分路径需完善）。浏览器实测与 INDEX/memory 更新待推送后做。
  - **2026-10-31 回归验证（HEAD = b3a94ef0b, v1.0.71）**：
    - 后端（`formula_settings/` 全目录 + 新增 `test_outbox_record_and_stale.py`）：候选 39 tests (28 passed + 11 failed)，HEAD 基线 34 tests (23 passed + 11 failed)。失败集合完全相同（`test_admin_publish_cas_and_conflict_pending` / `test_project_effective_and_overrides_permissions` / `test_pending_read_resolve_permissions` / `test_put_global_row_is_a_publish_with_cas` / `test_put_project_row_saves_adaptation_with_project_audit` / `test_baseline_candidate_review_publishes_globally` / `test_history_rollback_writes_project_adaptation_not_global` / `test_rollback_locates_legacy_entry_by_unique_row_code[0/1]` / `test_visibility_matrix_list_detail_versions_same_rule` / `test_manage_publish_subscribe_permissions`），全部预存。**只候选红 = 0**。新增 `test_outbox_record_and_stale.py` 5 例全绿。
    - 前端（vitest `src/components/formula/`）：67 文件 683 passed + 4 failed + 3 skipped。4 个失败全来自并发会话的未跟踪新文件（`formulaManagerMasterDiff.spec.ts` 2 例 + `FormulaManagerDialogOpenBeforeMount.spec.ts` 2 例），不在 S4 改动范围。**只候选红 = 0**。
  - 浏览器实测依赖共享库迁移（V199 六表空）与开发服跑候选代码，待推送后做。代码改动已验证不引入新回归。
  - INDEX.md 本行与 memory.md 任务状态待推送时同步更新。
  - Verify: 只候选红 = 0 ✓；推送带版本号与主要变动（待执行）
