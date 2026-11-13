# 设计：公式管理评估问题逐项修复

## 1 现状核对（2026-11-03 现读）

| 项 | 现状 | 证据 |
|---|---|---|
| 传播 | `outbox.deliver` 只要处理器不抛就标 `published`；`propagate_report` 重算整体失败、`propagate_cross_check` 失败都返回 `{"error": …}` 不抛 ⇒ 不重试、无人可见 | `formula_settings/propagation.py`、`outbox.py` |
| 立即投递失败 | `_deliver_one` 只记 warning，行保持 `pending`、无 `last_error` | `outbox.py` `publish_pending` |
| 重放 | `ImportEventOutboxService.replay_pending` 对 `_deliver` 抛错记 failed / 尝试次数 / 原因，满次数进 `event_outbox_dlq` | `import_event_outbox_service.py` |
| 底稿写入口 | 5 个写端点不调 `record_changes` / `publish_pending`，只写 `wp_formula.base_*`（`_update_sync_tracking`） | `routers/wp_formula.py`、`routers/wp_user_formulas.py` |
| 应用范围 | 前端白名单 `APPLY_SCOPE_DOMAINS = report/tb_detail/cross_check`；后端 7 域都支持 | `FormulaSettingsToolbar.vue`、`apply_ops.py` |
| tb_detail | `READER_ENTRIES["tb_detail"] = ()`，`/domains` 给 `wired:false` + `wired_reason`；公式管理节点与应用范围弹窗不提示 | `consumers.py`、`FormulaManagerDialog.vue` |
| Excel 导入 | `import_templates._import_formulas` 导入不存在的 `save_formula_batch`；前端按钮已隐藏但弹窗仍挂载 | `routers/import_templates.py` |
| 自定义函数 | `_custom_registry` 进程内 dict；POST / DELETE 仅 admin；前端无入口 | `formula_custom_functions.py`、`routers/formula.py` |
| 模板 | 全局发布对模板来源的项目行一律 `TEMPLATE_SKIPPED`；`global_hints` 只读提示，无「保留模板」落点，全局删除不提示 | `publish.py`、`template_service.py` |

## 2 决策

- **D1 传播失败语义**：新增 `PropagationIncomplete(RuntimeError)`。报表重算整体失败、表间审核失败时：先保证过期标记已提交、写降级日志，再抛它 ⇒ `deliver` 归还消费权并上抛 ⇒ 行不标 published。否决「返回 error 字典 + 只记日志」（旧做法，失败不可重试也不可见）。单行重算失败（公式本身错）不抛：重试无用，行保留过期标记，降级日志可查。
- **D2 立即投递失败落状态**：`_deliver_one` 失败后另开会话把行记 `failed`、`attempt_count+1`、`last_error`；行仍满足 worker 的重放条件（failed 且次数未满）。
- **D3 状态接口不建新表**：从 `import_event_outbox`（`event_type = formula_config.changed`、`payload.origin = formula_settings_outbox`、本项目）取最近 200 行在 Python 里按 origin 过滤（不依赖 PG JSON 操作符，SQLite 测试可跑）；死信从 `event_outbox_dlq` 计本项目未处理数。否决「新建传播作业表」：需迁移且与 outbox 重复。
- **D4 底稿写入口**：路由层在审计 flush 之后、commit 之前登记；只有执行字段变化才登记（旧值在调 service 前存成普通值）；slot 用 `domain_stores.wp_slot`。批量与 user-formulas 一次登记多格。
- **D5 应用范围**：白名单加 `wp`；FormulaManagerDialog 底稿保存成功后按 `wp_code|sheet|cell` 调 `askApplyScope('wp', …)`。附注 / 合并附注 / 推送的保存入口在独立弹窗，本轮不接（R4.2）。
- **D6 Excel 导入**：保留 `ImportType.formula` 枚举（`/types` 与模板下载不受影响面最小），`import` 分支直接 410；前端删 `UnifiedImportDialog` formula 实例。
- **D7 自定义函数**：POST / DELETE 返回 501（`FORMULA_CUSTOM_FUNCTION_NOT_PERSISTED`），GET 保留；服务层函数不动（单测仍可直接调）。
- **D8 模板冲突（方案 A，无迁移）**：`global_hints` 每条加 `kind`：`follow`（模板 == 写入时全局，模板没改过）/ `same`（模板 == 新全局）/ `conflict` / `deleted`（全局已删）+ `base_version`。新增 `keep_template_baseline`：取模板锁 → 校验 `expected_version == tpl.version` 与 `expected_global_version == 当前全局版本` → 只改模板行 `base_definition / base_version` → 审计 `formula.template_baseline_kept`。不升模板版本、不触发订阅同步。路由 `POST /api/formula-templates/{id}/global-hints/keep`（管理权限）。否决在全局发布事务里级联改模板（锁序与模板发布相反，可能死锁，且一次发布放大成 N 次模板发布）。
- **D9 E2E**：按真实接口重写，断言具体状态码与业务值；无种子数据时 `test.skip` 并写明原因（显式跳过，不是假绿）。

## 3 风险与对策

- 底稿写入口登记会把本项目同编码底稿标 `prefill_stale`（含刚编辑那张）：与 `PUT /{domain}/overrides` 同口径，属预期；只在执行字段变化时登记以免空写。
- 用最小 SQLite schema 的既有端点测试可能没有 `import_event_outbox` 表：跑相关测试，缺表的用例在测试侧建表或打桩，不改生产判据。
- `publish_pending` 后台投递用全局 `async_session`：测试不设 `DATABASE_URL` 会连共享库 ⇒ 相关用例打桩 `publish_pending`。

## 4 验证

- 后端：`backend/tests/formula_settings`、`backend/tests/formula_hub` 选集与 HEAD 基线逐节点对比，新增失败 0；新增用例覆盖 R1 / R2 / R3 / R6。
- 前端：相关 vitest + 区域 vue-tsc（新增错误 0）。
- 变异：抛错改回返回字典、登记调用删除、状态接口去掉 origin 过滤、保留模板去掉全局版本校验，各自应打红。
- 浏览器：受共享库缺迁移影响（项目页 500），能走的全局设置页 / 模板页实测；项目内页面在迁移放行后补测。（实际做法：一次性库全链走查，见 tasks 第 9 项。）

## 5 修复中现查出的阻断（R0，2026-11-03）

### 5.1 报表运行记录（R0.1）

`install_report_generation_provenance(ReportEngine)` 在导入期给三条生成路径套运行上下文，每次先插一行 `report_generation_run`。
共享表的结构由 V246（合并运行 spec）决定：V246 先于 V251 执行，V251 的 `CREATE TABLE IF NOT EXISTS` 与 `ADD COLUMN IF NOT EXISTS`
都是空操作，实际只多建一条外键与两个索引。共享库现查（2026-11-03）：状态 CHECK = `building/succeeded/failed/stale`、`calc_version integer`、
有 `error` 无 `error_summary`、运行记录 0 行（自 13:48 迁移落库后没有一次生成成功）。

裁决：S5 代码改按共享表写 —— 开始 `building`、结束 `succeeded`（部分行失败计 `failed_rows`、原因写 `error`）、`calc_version` 存整数
`CALC_VERSION`（信封里的 `report:2` 不变）。否决新增迁移把 `running/partial` 加进 CHECK：要改合并 spec 的 ORM 与 CHECK，且共享库
迁移需放行；`partial` 的信息已由 `failed_rows` 承载。R251 原本会删 V246 的表与两列，改为只撤销 V251 实际新增的三个对象。

### 5.2 迁移文件（R0.2）

共享库 `/api/health`：V236（字面量 `'…; …'` 被分句器切断）、V248 / V249（UTF-8 BOM）三条 `ProgrammingError`，`pending_versions=[236,248,249]`。
PG 日志 11-03 13:48:35 UTC 三条报错：`unterminated quoted string at or near "'Minimal authorized-context …"`、两条 `syntax error at or near "\ufeff"`。

**2026-11-04 改基**：远端 ddcde5244（`note-disclosure-pull-regression-and-headless-backend` 批 1，11-04 10:07 推送）已提交同样的分句器修复（同名模块 `app/core/migration_sql_split.py`），推送前改基时取远端实现、本 spec 的同名实现与用例不入库（自写用例对远端实现 17 / 17 通过）。下面是改判经过与验证记录。

**2026-11-04 改判**：首版去掉了三个文件的 BOM、把 V236 字面量里的分号改成逗号。提交前只读核对共享库：这三条已于 11-03 15:24:05 UTC
登记为已应用（checksum 与远端文件一致，字段注释是含分号的原文，失败记录已清；登记方不明，本会话的脚本没有写过共享库），对象齐全。此时改文件 =
`detect_checksum_drift` 报 3 条 critical 漂移、`/api/health` degraded。裁决：文件恢复原样，修迁移器。

- 分句器抽到 `app/core/migration_sql_split.py`（`migration_runner.py` 1172 行已超行数门白名单阈值 1170，抽出后 1039 行）：
  文本开头 BOM 先去掉；`'…'`（`''` 转义，`E'…'` 另认反斜杠）与 `"…"` 整体保留。checksum 仍按原文算，已登记值不变。
- 全库 443 个 V / R 文件新旧分句只有 V236（3 条 → 2 条）、V248 / V249（去 BOM）不同。
- `test_migration_split_quotes_and_bom.py`：字面量 / BOM 用例 + 全库扫描（独立判据，断言分母非空）+ 钉住三个已应用文件的 checksum；
  旧分句器 10 红，去 BOM / 不认 `E''` / 不认双引号三处变异各自打红。
- 全新库按 `formula-e2e.yml` 的建库顺序（代码取候选提交树）：迁移 247 执行 / 0 失败、无 checksum 漂移，V236 注释为含分号的原文。
- R248 / R249 是回滚脚本、不进 `schema_version`，去 BOM 与注释改正编号保留。

### 5.3 85caab386 整文件回退（R0.3）

`probe_stale_overwrite.py` 现算：该提交把 18 个文件写回更早的版本，抹掉 11-01 11:21~14:47 的 6 个提交在这些文件里的改动。本轮恢复：

| 文件 | 被抹的修复 | 影响 |
|---|---|---|
| `formula_settings/outbox.py` | bb29a49f6：依赖图过期改调 `stale_engine.on_change` | 回退后延迟导入不存在的 `stale_summary_aggregate.mark_downstream_stale`，每条投递的下游过期都是空操作 |
| `formula_reverse_index.py` | bb29a49f6：`app.core.redis` | 回退后导入不存在的 `app.core.redis_client`，多进程反向索引版本号失效 |
| `routers/wp_user_formulas_v2.py` | bb29a49f6：实验接口退役 410 | 回退后恢复进程内全局存储（无项目 / 底稿隔离），`test_platform_release_security` 红 |
| `formula-template-dual-project-pilot/tasks.md` | d17a1587a：任务 4 浏览器验收记录 | gt-plan 显示 6/7 |

未恢复、交原 spec（行为或性能改动需连同调用方一起验证）：a6c1fa93a 的批量 CAS 写（`formula_runtime/adapters/workpaper.py` +182/-78、
`consol_note_settings.py` +76/-25、`test_workpaper_adapter.py`、`test_formula_push_engine_pg.py`）、`useD4FormulaEngine.ts` 类型修正；
60f2fed79 的合并附注公式填数来源投影（`consol_note_formula_service.py` +10）。其余被抹文件（`noteScopeTargeting*`、`FormulaPushPanel.vue`、
`formula_push/triggers.py`、`note_settings.py`、两份附注公式测试）工作树已由并发会话在恢复，本 spec 不碰。

2026-11-04 改基：远端 ddcde5244（`note-disclosure-pull-regression-and-headless-backend` 批 1，11-04 10:07 推送）与 530007874 按文件三方恢复了上面「未恢复」的批量 CAS 写、合并附注设置 / 公式服务、`useD4FormulaEngine.ts` 等（见其提交说明，本 spec 未逐项复核），本 spec 不再跟进。

### 5.4 重放空转（R0.4）

`GATED_FANOUT_EVENT_TYPES` 含 `FORMULA_CONFIG_CHANGED`：派发口 `ImportEventOutboxService._deliver` 先抢 `(event_id, fanout@1)`，
再调 `formula_settings.outbox.deliver`，后者又抢同一把 ⇒ 唯一索引冲突 ⇒ `already_delivered`、处理器不执行，派发口照样标 published。
立即投递走的是 `deliver` 直调（只抢一次），所以首次能跑；失败后的每次重放都是空操作。裁决：抢权与记状态只归派发口，`deliver`
只读载荷、取年度、调处理器；`publish_pending` 的立即投递也改走 `publish_one`，失败当场记 failed / 次数 / 原因。
