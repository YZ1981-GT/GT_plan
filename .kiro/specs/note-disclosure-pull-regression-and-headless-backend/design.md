# 附注取数回归修复与披露 builder 后端化 — 设计

## §0　实施状态（2026-11-04）

| 批 | 内容 | 状态 |
|---|---|---|
| 批 1 | R1 迁移补执行 + 执行器修复；R2 三方恢复 + 阻碍验证面的 HEAD 缺陷（R2.5） | 代码与验证完成，本次推送 |
| 批 2 | R3.2 Word 门禁修真 + R3.3 / R3.4 白名单与表名判据（任务 5 / 6） | 未开始 |
| 批 3 | R4 期 1：可移植性现算、Node 执行器、D2 / E1 逐字节对拍、手工触发（任务 10~13） | 未开始 |

**凡本文档给出的数字都是某次现扫的快照，实施期须重扫，不得引用。**

## §1　现状确认

### 1.1 判据自检（2026-11-01 写文档时踩到一次）

扫「待执行迁移是否有回滚脚本」时，首版判据按精确文件名拼 `R{V文件名去掉首字母}`，而真实命名多一个 `rollback_`
段，16 个全部误判；表达式里又混入恒真的 `or any(...)`，把误判显示成「全部 True」。修正为 `glob(f"R{num}__*.sql")`
并加正向自检（抽不到已逐字读过的 R245 / R247 即 assert 失败）。

### 1.2 两次现扫

| 项 | 2026-11-01（`93789e405`） | 2026-11-03（`8352d7b38`） |
|---|---|---|
| 共享库 | 234 条，最高 V234 | 247 条（V236 / V248 / V249 未执行，见 §2） |
| `consol_note_data` 来源投影四列 | 不存在 | 已存在（V247 已由其他进程执行） |
| 后端宽口径回归（本 spec 选集 346 文件） | — | HEAD：6866 passed / 142 failed / 19 error |
| 前端 builder | 122 定义 / 86 文件 / 78 码 / 10 组 | 批 3 重扫 |

## §2　R1　共享库迁移

### 2.1 实际发生的事

2026-11-03 现扫：V235、V237~V247、V250、V251 已于 13:48 由其他进程（另一会话的本地分支 `merge1103`，
`5b27a4648`）经启动路径执行；**V236、V248、V249 执行失败**，留在 `schema_migration_failures`。失败原因不在迁移本身，
而在执行器分句：

| 版本 | PG 报错 | 根因 |
|---|---|---|
| V236 | `unterminated quoted string at or near "'Minimal authorized-context request IDs for restart recovery"` | `COMMENT ... IS 'a; b'`：字符串里的分号被当成语句结束 |
| V248 / V249 | `syntax error at or near "\ufeff"` | 文件带 UTF-8 BOM，原样发给了数据库 |

### 2.2 修执行器，不修迁移（ADR-NPR-06）

已应用行的 checksum 就是迁移文件的身份；改文件会让已执行这三个迁移的其他库全部报漂移。修
`MigrationRunner._split_sql_statements`：去掉开头 BOM；认 `'...'`（`''` 转义，`E'...'` 另认反斜杠转义，`E` 不能是
更长标识符的尾字母）与 `"..."`（`""` 转义），其中的分号不分句。用例 `test_migration_runner_split_quotes_bom.py`
与既有执行器用例共 52 passed；变异 M02（不去 BOM）/ M03（不认单引号）各红在自己的用例上。

### 2.3 执行与验证（用户 2026-11-03 放行方案甲）

`tmp_note_pull_doc/apply_pending_migrations.py --apply`：先 dry-run（pending = 236 / 248 / 249），再经
`MigrationRunner.run_pending()` 执行。备份 `backup_schema_version_20261103_232405.json`。结果：

- executed 236 / 248 / 249，failed 无；`schema_migration_failures` 残留 0。
- `ai_chat_runs.context_request_snapshot`、`formula_push_state.provenance` 列与 `note_formula_run` 表由无变有。
- 三行 checksum 与磁盘一致；`schema_version` 247 → 250；`VERIFY OK`。

未做（任务 8 余项，如实登记）：`/api/health` 启动报告复核、合并附注三条生产路径在【测试】项目各跑一次、
V235 前后 `adjustments` / `adjustment_entries` 行数对账（V235 由其他进程执行，本会话没有执行前快照）。

### 2.4 归属清单

| 版本 | 归属域 | 与附注链路 |
|---|---|---|
| V235 | 调整分录复核（建 5 表 / 改 16 表 / 4 drop） | 间接（审定数上游） |
| V236 | AI 对话运行快照列 | 无 |
| V237~V239 | AI 模型信任域 / 批任务 / 待确认产物 | 无 |
| V241 / V242 | 资产 blob 基座 / 附件血缘索引 | 无（测试基座外键依赖它，见 §3.4） |
| V243 | 平台持久化作业 `platform_jobs` | R4 期 3 依赖 |
| V244 / V245 | 合并 operation / 抵销工作表版本 | 间接 |
| V246 | 报表生成运行 `report_generation_run` | 直接（§3.5） |
| V247 | 合并附注来源投影四列 | 直接且必需 |
| V248 / V249 | 推送溯源列 / 附注公式运行表 | 直接 |
| V250 / V251 | 显示偏好与金额单位 / 公式溯源报表运行 | V251 与 V246 同名建表因 `IF NOT EXISTS` 不生效（§3.5） |

## §3　R2　HEAD 回归修复

### 3.0 根因：两个提交从陈旧基线整文件覆盖

2026-11-01 的文档把三组回归记为「合并时丢接线」。实施时逐提交现算（探针 `probe_clobber_footprint.py` /
`probe_exact_revert.py` / `probe_stale_base.py`）得出的真实成因：

| 提交 | 形态 | 覆盖面 |
|---|---|---|
| `03496b1f3`（11-01 14:51，合并运行批 1-6） | 合并提交，父 = `dcf881b39`（v1.0.85，已含 `2de9f17aa`）+ `60f2fed79`（「temp: batch 1-6 on old base」，基于 11-01 00:04 的 `ff8ccd354`） | 冲突处取了旧基线一侧：`2de9f17aa` 的子树汇总表头接线、`consolidationApi.ts` / `ConsolNoteTab.vue` 改动、S9 拓扑序后更新的种子用例等被回退 |
| `85caab386`（11-01 15:15，formula-hub S1/S3/S4/S5/S6/S9 代码批） | 单父 = `03496b1f3`，提交树来自 11-01 09:50~14:22 之间的陈旧工作区 | **18 个文件整文件回退到旧版（HEAD 上仍有 16 个）、删除 12 个文件（HEAD 上仍缺 7 个）**；丢失的提交包括 `2de9f17aa`、`a6c1fa93a`、`bb29a49f6`、`53a1a4b83`、`d17a1587a` 等 |

两个提交都不是「改坏了」，而是**把别人已入库的版本换回了旧版**：HEAD 上这些文件的测试也一起回到旧版，所以
HEAD 上许多相关用例是绿的（例如 `test_bad_debt_table_presets` 在 HEAD 通过——测试文件被同一提交回退；2026-11-01
记录的 `KeyError: 't1:5:1'` 来自主工作树磁盘上未回退的新版用例）。

### 3.1 恢复方法（R2.0）

`restore_plan.py` 对两个覆盖提交的足迹逐文件做三方合并：基线 = 覆盖提交的父，「他方」= 覆盖提交，「我方」=
HEAD（`git merge-file`）。结果：候选 214 个文件，**会改变 HEAD 的 51 个**，其中 **11 个有冲突**。`85caab386` 的
父就是 `03496b1f3`，两步合并在 `propagation.py` / `consol_note_formula_service.py` 上第二步会把第一步刚恢复的改动
再回退，这两个文件改按「两个覆盖提交各自丢掉的块」一次恢复（`restore_both_fix.py`）。

冲突裁决：

| 文件 | 裁决 | 理由 |
|---|---|---|
| `formula_push/engine.py` | 取恢复版 + 只导入 `note_total_push, note_writer` | 恢复的抽取模块（ADR-9）与批量定位底稿（消 N+1） |
| `models/__init__.py` | 恢复资产模型注册 + V250 注释 | 测试基座与生产启动都靠它注册 `asset_blobs`（§3.4） |
| `models/report_models.py` | HEAD | 恢复 S5 的 `ReportGenerationRun` 类会与 V246 的同名表重复定义（§3.5） |
| `formula_push/note_followup.py`、`formula_settings/note_settings.py` | HEAD | HEAD 版已是后续修订 |
| `note_formula_push_guard.py` | 恢复版 | 只认生效规则拥有格；只认规则自己的字段 |
| `FormulaManagerDialog.vue` | HEAD 一侧 + 恢复 `openRevision` / immediate，再修 TDZ（§3.7） | — |
| `noteScopeTargeting.ts` | HEAD + 用户公式行按 `target_label` 显示目标单元格 | — |
| `INDEX.md` | HEAD + 重新插入 `note-table-structure-formula-pull-closure` 速递行 | — |
| 该 spec 的 design / requirements | HEAD | 文档以 HEAD 后续修订为准 |

两处恢复后又撤回：`ConsolidationIndex.vue` 的 `void copyText` 改动与附注链路无关且是体验回退（复制失败不再提示），
回到 HEAD；`ConsolNoteTab.vue` 的 `_silent` 保留恢复版（`validateStatus < 600` 下错误响应会被当成功）。

### 3.2 R2.1 比例 / 损失率预设公式

`_ratio_presets` 与 `table_preset_formulas` 内调用点按 `2de9f17aa` 原样恢复（经 `85caab386` 的三方合并），不重写：
`note_formula_ratios.ratio_plans` 给派生计划与未派生原因；带 `requires: [[r, 分子列]]`；已被合计 / 账面价值占用的
key 不覆盖。执行侧补齐同一判据：`note_formula_generator` 在求值前先查 `_required_blank`，分子格为空就跳过、不写 0
（用例 `test_ratio_with_blank_numerator_is_skipped_not_written_as_zero`）。变异 M10（不生成比例预设）、M08'（执行时
不看 requires）各红在自己的用例上。

### 3.3 R2.2 推送提交后附注公式：收口到提交边界（ADR-NPR-08）

`2de9f17aa` 让四个调用方（`triggers._push` / `panel.adopt` / `routers/formula_push.run_push` /
`propagation.propagate_push`）各自在推送后调 `recalc_pushed_notes`；被覆盖丢失的后续修订（R20）把它收进
`persistence.execute_and_commit` 的提交边界。两者同时恢复会让每次推送跑两遍附注公式，所以只保留 R20：

- 删除四个调用方各自的调用，`run_push` 响应去掉 `note_formulas_updated`。
- `engine.run_and_commit(..., skip_note_followup=False)` 把开关转给 `_skip_note_followup`。
- 附注刷新链路 `note_workpaper_pull_service._push` 传 `skip_note_followup=True`（HEAD 上这里传的
  `_skip_note_followup` 是 `run_and_commit` 不认的关键字 ⇒ 刷新时推送一步必抛 `TypeError`）。
- `note_formula_generator`：推送拥有格的写入包保存点；拥有格保留时状态是 `kept_push`（自带原因，不再报
  `skipped_manual`）；「来路不明的值 ⇒ 当人工」的启发式排除推送拥有格，所以用户公式能覆盖推送拥有格（R20.3），
  而旧的手填值仍受保护。

用例：`test_formula_push_note_followup.py`（R20 口径重写）、`test_formula_push_legacy_tables.py` /
`test_formula_push_note_total_pick.py`（`skip_note_followup`）。变异 M04（不转发开关）、M05（调用方再调一次）、
M06 / M07（拥有格套人工启发式 / 状态回 `skipped_manual`）、M09（停用规则仍算拥有）、M18（刷新链路不跳过）全红。

### 3.4 R2.3 合并附注公式种子：根因是模板数据有意变化

2026-11-01 的根因假设（`value_column` 里 `net is None` 的拒绝排在「纯期间列唯一」之后被绕过）**不成立**，作废。
实测三条红分两件事：

1. `test_unexpandable_report_row_skips_measure_columns` 是**过期用例**。S9（`income-statement-lower-section-formulas`，
   ADR-ISL-01）让报表行按公式依赖拓扑序展开，「引用排在后面的行」不再展开失败；对应的用例更新在 `03496b1f3`
   里被回退。恢复后拆成两条：前向引用按拓扑序展开（`test_forward_report_row_is_expanded_by_topological_order`），
   真正的循环引用仍不种（`test_cyclic_report_row_still_skips_measure_columns`）。
2. 种子计数 soe `(3,5)≠(4,6)`、listed `(4,6)≠(5,7)`：逐提交对比两版单体模板的 `account_codes`
   （`probe_account_codes_history.py`），唯一变化在 `07bbbc4e1`（R8.4 批 9b-2「两版单体附注模板按底稿披露表改结构」）：
   「交易性金融负债」主表按底稿 G10 披露表重建，父行 = 其中三项之和（底稿 B8 = B9+B10+B11），**不再标科目 2101**；
   国企 41→40 行、上市 123→122 行带科目码，其余一行未变。⇒ 种子 (b) 类两版各少一格（国企 五-34-1 (0,1)、上市
   五-34-1 (0,4)），同表合计照种 `REPORT('BS-042')`。

裁决（ADR-NPR-09）：以底稿披露表为准接受数据变化，`SEED_COUNTS` 改为 soe (3,5) / listed (4,6)，注释写明逐格依据，
并加钉死断言（五-34-1 第 0 行不按科目种、合计仍是 `REPORT('BS-042')`）。不把 2101 加回父行：有「指定为以公允价值
计量…的金融负债」时会把整个 2101 余额写进父行。变异 M15（父行恢复 2101）红在种子计数用例上。

### 3.5 R2.4 测试基座外键悬空

HEAD 上本 spec 选集的 19 个 ERROR 全部是 `NoReferencedTableError: attachment_versions.blob_id → asset_blobs`
（合并附注种子持久化 / 端点、章节列角色、入口锁、L4 扩展四个文件）。两处一起修：`tests/conftest.py` 按 pkgutil 走包导入 `app.models` 全部子模块；
`app/models/__init__.py` 恢复资产模型注册（覆盖丢失）。变异 M01（两处同时撤回）复现 ERROR。

### 3.6 R2.5 单体报表运行记录写共享表（ADR-NPR-07）

HEAD 上单体报表生成必失败：`asyncpg DataError: invalid input for query argument $11: 'report:2'`（SQLite 上是
`CHECK constraint failed: ck_report_generation_run_status`）。S5 原有一个同名的 `ReportGenerationRun` 类（自己的状态词表、
字符串 `calc_version`、`error_summary` 列）；HEAD 上 `report_models.ReportGenerationRun` 已改成对 V246 类的再导出，写入方
`report_provenance.generation_context` 却还按 S5 的口径写 `status='running'`、`calc_version='report:2'`、`error_summary`。
库里的 `report_generation_run` 是 V246 建的（合并运行共用；状态词表 building / succeeded / failed / stale，`calc_version`
是整数，失败原因列叫 `error`；V251 的同名建表因 `IF NOT EXISTS` 不生效）。修法：写入方改用 `report_generation_models.ReportGenerationRun`，开始写 `building`、
结束写 `succeeded`，失败行写 `error`，`calc_version` 写整数 `CALC_VERSION`；对外状态由 `run_display_status()` 换算
（building → running，succeeded 且 `failed_rows > 0` → partial），`routers/reports.py` 用它。否决：新迁移扩 CHECK
（未经放行的 schema 变更，且一列两套词表）；恢复 S5 自己的类（同名表重复定义）。真库回滚事务探针
`probe_report_generate.py`：HEAD 失败于 DataError；候选生成成功，258 行全部带 run_id 与溯源，运行 1 条
`succeeded / 0 失败行`。变异 M11（写 running）/ M12（calc_version 写字符串）/ M13（不显示 partial）全红。

### 3.7 R2.5 推送用例测试环境与公式管理首开

- `_formula_push_env.make_env`：有 `adjustments` 表时同时建 `AdjustmentTreatmentEvent` / `AdjustmentClientBooking`
  （V235 新表被推送读取路径引用），41 个推送用例恢复。变异 M14 红。
- `FormulaManagerDialog.vue`：HEAD 的打开流程监听没有 `immediate`，而 `ThreeColumnLayout` 用 `useMountOnFirstOpen`
  首次打开才挂载 ⇒ 挂载时已是打开态，首次打开什么都不加载。恢复的 `a6c1fa93a` 原写法加了 `immediate`，但监听注册在
  `<script setup>` 中段，首轮同步执行读到第 2800 行才声明的 `activeCategory`（暂时性死区）⇒ 打开流程在第一处赋值就
  中断，vitest 报 22 条 Unhandled Rejection（HEAD 0 条）。修法：回调提成函数 `onOpenContextChange`，`watch(…, {
  immediate: true })` 移到 `<script setup>` 末尾。新用例「挂载即打开」两条（以打开态挂载完整跑一次且没有未处理错误 /
  以关闭态挂载不加载、打开后只跑一次），变异 M22（去 immediate）、M23（注册回中段）均红。

### 3.7a R2.5 全量回归删掉 worktree 的 index

批 1 用分片并行跑后端全量（两棵树各 8 片）时，候选树与基线树的 index 先后被清空（基线树 0 条、候选树只剩我刚
`git add` 的两个目录）；工作树文件完好。根因在 `scripts/check/candidate_tree_identity.py` 的 `cmd_build`：

```python
fd, private_index = tempfile.mkstemp(...)
try:
    if Path(private_index).resolve() == real_index:   # 安全校验
        raise RuntimeError("Private index path resolved to .git/index — aborting")
    ...
finally:
    os.unlink(private_index)                           # 校验不过也会走到这里
```

它的变异用例 `test_private_index_resolving_to_git_index_is_rejected` 正是让 `mkstemp` 返回真实 index 路径，期望被拒绝；
拒绝确实发生了，但 `finally` 随即删掉了真实 index。用例只断言抛错，不查真实 index 还在不在，所以一直是绿的；
模块文档写的「把私有 index 换成默认 index 的变异必须红并逐字节还原」没有对应的判据。

修法：校验移到 `try` 之外（校验不过时这条路径不是本工具建的，不归它清理）；用例补「真实 index 存在且逐字节不变」。
危害：任何人在主工作树跑后端全量都会丢 index；此时若只 `git add` 部分路径再提交，提交树就只剩这几个路径
（推送即整库删除）。本次恢复：两棵树 `git reset -q`（index := HEAD，工作树不动），再与提交前快照逐文件核对。

### 3.8 其余随恢复带回的改动

附注 / 公式链：`formula_push/note_total_push.py`（附注写入与多汇总行取舍抽出，ADR-9 / R12）、`orphan_states.py`
（孤儿推送格）、`engine` 批量定位底稿、合并附注多章节公式批量读（`effective_formulas_many`，变异 M19 / M17）、合并附注
公式变更经 `consol_operation_service.request_operation` 排 push operation（变异 M16）、子树汇总把合并表头传给
`build_note_rows`（比例 / 损失率按本表派生、合计只加金额列）。最后一条首轮变异 **M20 存活**：`build_note_rows`
自己的用例测不到调用方传没传表头 ⇒ 补 `test_ratio_columns_follow_the_consolidated_header_not_the_children`
后 M20' 红。

**跨域的恢复（同在覆盖足迹里，行为会变，须知会归属方）**：

| 文件 | 恢复内容 | 原提交 | 影响 |
|---|---|---|---|
| `core/startup_registry.py` | 启动注册 `event_loop_lag_worker` / `ai_task_worker` / `platform_job_worker` 三个常驻 worker 与 `gate_rules_evidence` 门禁规则 | `a6c1fa93a` | HEAD 上这三个 worker 的模块都在、却从不启动（耐久 AI 批任务、平台重任务不会被接管） |
| 同上 | 迁移两步改为「执行 + 只读完整性核验」，有待执行或失败的迁移即**阻断启动** | `bb29a49f6` | `test_release_migration_readiness.py` 3 条在 HEAD 红、候选绿；共享库已无待执行 / 失败迁移 |
| `models/__init__.py` | 注册 `AiTaskJob` / `AiTaskItem` 与资产 blob 模型 | `a6c1fa93a` 等 | 启动期 ORM 注册完整 |
| `routers/wp_user_formulas_v2.py` | 用户公式 v2 实验接口退役为登录后 410（进程内全局 store 无项目隔离） | `bb29a49f6` | HEAD 上该接口仍读写全局 store |
| `services/formula_reverse_index.py` | Redis 客户端改从 `app.core.redis` 取（HEAD 引用不存在的 `app.core.redis_client`，被 try 吞掉 ⇒ 跨进程版本号恒取不到） | `bb29a49f6` | 反向索引跨进程失效恢复 |
| `services/formula_settings/outbox.py` | 报表公式变更的下游过期走 `stale_engine.on_change`（HEAD 是 S4 `b410cfb0c` 的旧写法 `mark_downstream_stale`） | `bb29a49f6` | — |
| `router_registry/system.py` | 只改注释（高级查询写入口现为 410 兼容桩） | — | 无 |

### 3.8a 行数门（提交时）

pre-commit 行数门拦下 7 个文件：其中 5 个在 HEAD 上就已超基线 +5%（`ConsolNoteTab.vue` 3439、`consolidationApi.ts`
1627 且未登记、`migration_runner.py` 1172、`startup_registry.py` 1042、`note_formula_generator.py` 1558），2 个是恢复
把它们顶过线。按「优先抽伴生模块、不抬白名单」处理后端：迁移分句器抽成 `core/migration_sql_split.py`（`migration_runner`
1223 → 1043），启动迁移两步抽成 `core/startup_migrations.py`（1073 → 1023），合并附注模板表结构工具按白名单登记的
拆分方向抽成 `services/consol_note_template_utils.py`（1563 → 1409），附注公式 REGION 聚合抽成
`services/note_formula_region.py`（1584 → 1393），批量定位底稿用例挪到 `test_formula_push_engine_locate.py`；都是原样
搬移、原名导入。两个前端文件本批只是净 0 / +1 行的恢复，按惯例登记当前真实行数并写拆分方向。

### 3.9 恢复链之外的丢失（只登记，不在本 spec 恢复）

覆盖足迹里与附注 / 公式链无关的文件，HEAD 上仍缺原提交新增的行（行数 = 原提交新增行里 HEAD 已不存在的）。
其中部分可能是后续有意改写，须由文件归属方复核后决定：

| 文件 | 丢失行 | 原提交 |
|---|---|---|
| `components/query/CustomQueryDialog.vue` | 44 / 53 | `a6c1fa93a` platform-perf |
| `middleware/audit_log.py` | 7 / 7 | `a6c1fa93a` |
| `tests/test_review_prompt_integration.py` | 6 / 6 | `a6c1fa93a` |
| `routers/wp_ai.py` | 2 / 5 | `a6c1fa93a` |
| `views/composables/useNoteAi.ts` | 2 / 15 | `a6c1fa93a` |
| `models/user_display_preferences.py` | 1 / 1 | `a6c1fa93a` |
| `layouts/ThreeColumnLayout.vue` | 2 / 14 | `bb29a49f6` release-blocker-closure |
| `frontend/package.json` | 1 / 3 | `bb29a49f6` |

`V235__display_preferences…` / `R235__…` 不是丢失：已改号为 V250 / R250。

## §4　R3　单体附注表格权威源固化与门禁修真（批 2，未开始）

### 4.1 权威分层（用户 2026-11-01 确认）

| 对象 | 权威源 | 不得由谁改 |
|---|---|---|
| 章 / 节 / 节标题 / 章内顺序 / 单体-合并归属 | 四版 Word | 底稿、模板 JSON |
| **单体每张表的列结构、表名** | **底稿模板 xlsx 的披露 sheet** | Word（不按 Word 回退） |
| 合并附注拉数模板表结构 | 合并版 Word，8 处明确服从单体（`STANDALONE_INSTANTIATED` 6 + `LOGICAL_COLUMNS` 2） | — |
| 附注表内数值 | 底稿披露表（经同步）+ 公式推送（审定数主项） | — |

`07bbbc4e1` 按底稿 G10 披露表重建「交易性金融负债」主表（§3.4）就是这条裁定的一次落地；本轮要做的是让它在门禁
里可见：现在「与 Word 不一致」和「漏改」在门禁输出里长得一样。

### 4.2 Word 同步门禁修真（R3.2）

缺陷：`sync_note_templates_from_word.py` 各 phase 的写入都在 `if not dry_run:` 内，`--check`（= dry-run）下
`json_data` 未被修改 ⇒ `write_json` 比较出「无变化」⇒ `total_drift` 不增（实测 phase 6 报「81 更新 / 116 更新」而
总判通过）。方案 A：`--check` 下各 phase 改 `deepcopy(json_data)`，再与磁盘比较；改动集中在 `main()`，phase 签名
不动。否决 B（phase 计数直接累加：计数与「文件内容是否真会变」不是同一件事，会假红）。两条反向断言：注入一处 Word
不一致 ⇒ exit 2 并点名；不注入 ⇒ exit 0。

### 4.3 白名单可解释声明（R3.3）与表名判据（R3.4）

白名单每条带 `category`（`workpaper_authority` / `workpaper_typo` / `word_placeholder` / `synonym` / `todo`）与可伪证的
中文 `reason`；`todo` 类条目数只许减少；保留「白名单无失效条目」。应收账款族优先（上市 `五、5#*` / `五、8#*`，
国企 `八、4#*` / `八、5#*`）。表名判据：`note_template_workpaper_alignment` 已配对成功的表，模板表名与底稿表名按
`note_workpaper_disclosure.name_key` / `base_name` 归一后相同，或落白名单。

## §5　R4　详细披露 builder 后端化（批 3，未开始）

### 5.1 与既有裁定的关系

`disclosure-payload-authority-source` 否决的是「用 Python 再写一遍」（后端 `disclosure_builders` 已因口径与前端
Tab 不同、写进附注是错数而于 2026-10-27 删除）。用户要的是「不依赖浏览器就能跑」。本设计让**既有 TS builder 在
服务端运行**，不翻译成 Python（ADR-NPR-03）。

| | A　Node 侧执行既有 builder | B　Python 重写 | C　无头浏览器跑附注页 |
|---|---|---|---|
| 算法源 | 1 份 | 2 份（已证伪） | 1 份 |
| 6000 并发 | 可（无状态进程池） | 可 | 不可（每任务一个浏览器） |
| 新依赖 | Node 运行时（前端构建已需） | 无 | Playwright + Chromium 常驻 |

可行性依据：`headlessFramework.defineHeadlessProvider` 已在 `effectScope(true)` 里实例化 composable、`await nextTick()`
后调 `build()`，只用 `@vue/reactivity` 与 http 客户端；取数收口在 `loadWorkpaperResponses` / `loadRenderConfig` /
`primeAgingConfig` 三处，是 Node 侧唯一要注入的边界。

### 5.2 形态与分期

```
手工触发 / 期 3 的 TRIAL_BALANCE_UPDATED ──► Node 执行器（project_id, year, wp_codes[]，服务端令牌，只连 127.0.0.1）
   复用 registry.ts 的 HEADLESS_PROVIDERS ──► 与浏览器逐字节相同的载荷
   ──► POST /disclosure-notes/sync-from-workpaper（现有端点，不改）──► 推送 → 回填 → 附注公式（§3.3）
```

- 不新建写入端点：四层人工保护、owner 差集、推送 ownership 重放原样生效。前端「刷新」保留为降级路径，两条路径跑
  同一份 builder ⇒ 不存在双写。
- 期 1（本 spec）：①现算 provider 依赖闭包（浏览器专有物分可移植 / 需注入 / 无法剥离）②执行器骨架 + 取数注入
  （模块解析用 `vite build --ssr` 或 `tsx` + alias，禁止改源码适配 Node；令牌按 DSH 范式 HMAC 派生自
  `JWT_SECRET_KEY`）③D2 + E1 浏览器载荷与 Node 载荷 canonical JSON 相等，不相等不扩面④手工触发端点 + CLI，
  跑通「不开任何页面 → 附注被更新」。
- 期 2（扩面到全部 provider，逐组对拍、清单只许变短）与期 3（事件接入 `platform_jobs`、运行记录 `note_formula_run`、
  刷新按钮改触发后端任务）另立 spec。
- 降级：期 1 可移植性证明失败时转 C 路线作过渡，并在本节追加说明。

## §6　验证（批 1，2026-11-04）

候选 = HEAD `8352d7b38` + 本批改动（干净分离头 worktree `tmp_note_pull_doc/verify_wt`）；基线 = 同一 HEAD 的干净
worktree（`head_wt`）。选集按附注 / 公式 / 合并 / 迁移关键字取后端测试文件，前端取 7 个目录。

| 面 | 基线（HEAD） | 候选 | 结论 |
|---|---|---|---|
| 后端（候选 346 文件） | 6866 passed / 142 failed / 19 error | 7026 passed / 77 failed / 0 error | **candidate-only red 0**；修好 84（65 failed + 19 error）；两边都红 77（§9.2）；新增节点 79；消失 3（均为同义改名 / 拆分：§3.4 的两条种子用例、R4.1 合并附注传播用例、读取入口改名） |
| 后端全量（`backend/tests` 全部，8 片 + 子片，`not pg_only and not e2e and not perf`，库指向不存在的 PG） | 73480 节点：67033 passed / 3100 failed / 2342 error | 73557 节点：68443 passed / 3025 failed / 1087 error | candidate-only red 13 条逐条在候选单跑：12 条绿（9 条读 git 状态，跑在 index 被删的 09:21–09:47 窗口里；另 3 条是 CLI 子进程、性能基准、批量执行顺序，单跑绿）；1 条是 PBT 随机反例 `test_pbt_metadata_roundtrip::test_docx_embed_extract_roundtrip`（docx 往返吞掉末尾不换行空格 `'0\xa0'`），同一输入在 HEAD 同样失败 ⇒ 预存。修好 1343（1202 条 error→passed，主因 `attachment_versions` / `knowledge_documents.blob_id → asset_blobs` 外键找不到表，任务 1；17 条单体报表运行 status 约束，任务 4b）；两边都红 4099（无库环境等）；两边都采集失败 `test_check_catalog_execution.py` / `test_batch_review_pass.py`；`test_pytest_import_isolation.py` 在长进程里单条要 35 分钟以上，单独跑两边各 10 passed；「消失」38 条全是按随机 UUID 参数化、每次运行 id 不同 |
| 子树汇总接线用例补上后 | — | `test_consol_note_subtree_reaggregate.py` + `test_note_formula_ratios.py` 40 passed | M20' 红 |
| 前端 vitest（433 文件） | 5224 passed / 33 failed | 5229 passed / 36 failed | candidate-only 3 条全是 PBT 随机种子红，同种子在 HEAD 复跑同样红（`pbt_seed_head.txt`：G4 Property 4 种子 2015764921、G6 Property 6 种子 126501068 / 2061351923）⇒ 预存；未处理错误 0 / 0（TDZ 修复前候选 22 条） |
| 全量 `vue-tsc`（40GB 堆，未崩溃） | 2969 | 2964 | **added 0**，resolved 5（`ConsolNoteMappingDialog.vue` 4、`useD4FormulaEngine.ts` 1） |
| 磁盘变异 | — | 24 条全红 | M08 首轮红在基线本来就红的 `test_s5_cell_sources` 上（`-x` 停在第一个红）不算数，点名用例复跑 M08' 红；M20 首轮存活，补接线用例后 M20' 红；M02 / M03 随分句器搬到 `migration_sql_split.py` 后复跑仍红在各自用例上；M24（安全校验放回 `try`）红在 `test_private_index_resolving_to_git_index_is_rejected`，变异态下跑这条用例真把 worktree 的 index 删空（`ls-files` 26284 → 0），`git reset -q` 后逐行核对 `git status` 与跑前一致 |
| 共享库 | 247 条，3 个失败迁移 | 250 条，`VERIFY OK` | §2.3 |
| 单体报表生成（真库回滚事务） | DataError | 258 行全带 run_id 与溯源 | §3.6 |

参照：覆盖之前的 `dcf881b39`（`pre_wt`，同口径选集）6737 passed / 160 failed / 7 error（其中 2 个文件采集失败）。
它不是「应有状态」，不作基线，只用于确认恢复的改动在覆盖前确实存在。

## §7　风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 恢复带回的改动与 HEAD 上后来的修订冲突 | 按文件三方合并，冲突逐条裁决（§3.1）；不整文件取旧版 |
| 2 | 恢复链之外仍有丢失（§3.9） | 只登记、交归属方复核，本 spec 不动 |
| 3 | 推送后附注公式跑两遍 / 不跑 | R20 收口到提交边界 + 「恰好一次」用例 + 变异 M04 / M05 / M18 |
| 4 | 种子基线被当绿灯开关 | 逐格依据 + 钉死断言 + 变异 M15 |
| 5 | V235 由其他进程执行，本会话无执行前快照 | 如实登记（§2.3），不补造对账 |
| 6 | 并发会话在共享终端里注入 ^C / 改主工作树 | 长跑一律后台独立进程 + UTF-8 日志；只在分离头 worktree 提交 |
| 7 | R4 期 1 可移植性证明失败 | 降级 C 路线并在 §5 追加 |

## §8　ADR

- **ADR-NPR-01**：单体附注表格权威源 = 底稿披露表 xlsx；Word 权威章节与合并骨架。与 Word 的差异须在白名单里带
  类别与理由。
- **ADR-NPR-02**：共享库迁移整批执行（方案甲），不跳号。实际 13 个由其他进程先执行，本会话补执行失败的 3 个。
- **ADR-NPR-03**：披露 builder 后端化 = 在 Node 侧运行既有 TS builder，不用 Python 重写。
- **ADR-NPR-04**：后端化不新建写入端点，仍走 `sync-from-workpaper`；前端直算保留为降级。
- **ADR-NPR-05**：种子基线只能在每个增减单元格可逐条解释后调整。
- **ADR-NPR-06**：迁移执行失败修执行器、不改已发布的迁移文件（checksum 是已应用行的身份）。
- **ADR-NPR-07**：单体报表运行写 V246 共享表 `report_generation_run` 的词表与类型，对外状态读时换算；不扩 CHECK、
  不另建同名类。
- **ADR-NPR-08**：推送提交后附注公式只在 `run_and_commit` 的提交边界执行一次；调用方不再各自调用，刷新链路用
  `skip_note_followup` 跳过、自己最后执行。
- **ADR-NPR-09**：交易性金融负债父行不按科目 2101 种（以底稿披露表为准），种子基线随 `07bbbc4e1` 下调。
- **ADR-NPR-10**：带 `immediate` 的 Vue 监听只在 `<script setup>` 全部声明之后注册（首轮同步执行，注册在中段即 TDZ）。

## §9　本 spec 不纳入（已登记）

### 9.1 分析中发现的其他缺口（另立 spec）

1. `GET /api/consol-note-formulas` 经 `ensure_seeded` + `db.commit` 写模板级全局表（只需登录即触发，不经同步内核与审计）。
2. `confirm_mapping` 接收 `preview_token` 但不验证；同仓库已有 HMAC `verify_preview_token` 范式。
3. 合并来源结构指纹不含列维度 ⇒ 只改列标题或合并表头时绑定不变 stale。
4. 读取层「零金额列命中」仍报 `found`，apply 可能写出全空值并清 `is_stale`。
5. 公式定位是纯位置键，合并侧 `_check_cell` 不校验 `row_index < 实际行数`（真实库人工公式为 0，当前暴露为 0）。
6. 前端两份列树并存（`consolNoteColumns.ts` 自认应复用 `noteColumnTree.ts`）。
7. 「应用范围」前端白名单缺 `note` / `consol_note`；合并附注面板隐藏了后端已有的项目适配 / 订阅 / 待确认 / 历史 / 调试入口。
8. `find_previous_year_rules()` 是孤儿实现。
9. `refresh-from-disclosure` 端点名与行为不符且无生产调用方。
10. `normalize_template_type()` 对未知 / 空值默认 `soe`（真实库 8 个项目 `template_type` 为空，其中 2 个合并项目）。
11. 映射 preview / confirm 始终覆盖全树，只有 apply / reaggregate 按当前节点限定。
12. 无「章节 → 预期子表清单」的后端目录。
13. **S5 真缺陷**：`DisclosureEngine.update_note` 保存时丢掉 `_formula_provenance` 旁注（从未实现），
    `test_s5_editor_save_preserves_formula_provenance_sidecar` 两边都红。
14. 恢复链之外的丢失（§3.9）。

### 9.2 两边都红的预存失败（本批不修，未归因者如实标注）

后端 77 条（按文件）：`formula_hub/test_l1_failure_semantics` 16 · `test_draft_refresh_service_counts` 7 ·
`formula_settings/test_legacy_report_paths` 6 · `test_formula_provenance_lineage_endpoint` 5 ·
`formula_runtime/test_refresh_transaction` 4 · `test_formula_push_note_skip` 4（MagicMock 规则过不了 S5 的来源快照：
`TypeError: 来源摘要不支持 MagicMock 类型`；另一条断言 `is_stale`，引擎已改用 `clear_note_stale`）·
`test_orchestrator_real_mutations` 3 · `formula_settings/test_endpoints` 3 · `test_note_deferred_tax_structure` 3 ·
`test_formula_push_schema_contract` 3（期望 `V237__formula_push_provenance.sql`，该迁移已改号 V248）·
`test_formula_history_rollback_http` 2 · `test_report_freshness` 2 · `test_wp_formula_eval_functions` 2 ·
`test_wp_formula_save_gate` 2 · `test_note_prior_dynamic` 2 · `test_note_formula_execute_tables` 2（S5 来源用例：测试
环境没有 `formula_push_state` 表；以及 9.1-13）· 其余 11 个文件各 1 条（含 `test_formula_push_prior_pl`：叶子口径的
试算表取数得 1.00、用例期望 242169737.06；`test_note_formula_l4_extension::test_exec_unknown_account_returns_zero`：
缺数现在返回 None、用例仍期望 0）。后端全量两边都红 4099 条（多为无库环境），另有 PBT 随机反例
`test_pbt_metadata_roundtrip::test_docx_embed_extract_roundtrip`：元数据写进 docx 再读出，末尾的不换行空格被吃掉
（`'0\xa0'` → `'0'`），HEAD 同一输入同样失败，属 `wp_export/metadata_codec`，未修。

前端 33 条：`d4FourTableWiring` 11（源码写死科目码）· `yearSwitchUpdatesRoute` 3 · `dSalesCycleLabelGuard` 2 ·
`useAgingConfig.property` 2 · `useAiCapabilities` 2 · `formulaPaths` 2 · `ReportView.filesize-invariant` 2 ·
`deepLinkEntryGuard` 2 · 其余 7 个文件各 1 条。另有 3 条 PBT 随机种子红（§6）：同种子在 HEAD 复跑同样红，属于
用例生成器 / 容差缺陷，未归因到具体提交。

INDEX 守卫：`test_spec_index_consistency::test_unindexed_active_specs_only_shrink` 在 HEAD 上即红
（`workpaper-html-onlyoffice-bidirectional-writeback-closure` 目录是活跃的，INDEX 只以反引号文字提及、没有链接），
属并发会话的 spec，不代登记。本批把 `note-table-structure-formula-pull-closure` 从「未收录」基线删掉：它的速递行被
`85caab386` 的 INDEX 整文件覆盖丢掉，随本批三方恢复回来，基线条目随之失效。

## §10　教训

1. **「合并时丢接线」是表象，先查是不是整文件覆盖**：逐提交算「原提交新增的行在 HEAD 还剩多少」与「是否整文件回到
   某个旧版」，一次就把 2 个覆盖提交、18 个整文件回退、12 个删除全部定位；按单个症状逐条修只会修到三组。
2. **覆盖会连测试一起回退**：HEAD 上相关用例是绿的，不能拿「HEAD 绿」当「没回归」。
3. **三方合并的基线必须是覆盖提交的父**；两个覆盖提交首尾相接时，第二步会回退第一步刚恢复的块，要按块一次恢复。
4. **恢复的改动本身也可能是坏的**：`a6c1fa93a` 的 `immediate` 修复从入库起就因 TDZ 失效，靠 vitest 的未处理错误
   计数才看出来 ⇒ 回归比对要比「未处理错误」这一项，不能只比用例红绿。
5. **变异 RED 要核对红在哪条用例上**：`-x` 停在第一个红，红在基线本来就红的用例上不算数（M08）；**被调函数一层的
   用例测不到调用方传参**（M20）。
6. **迁移执行失败先查执行器**：分句器与 PG 词法不一致（BOM、字符串里的分号）会让正确的迁移「失败」；改迁移文件
   会造出 checksum 漂移。
7. **两个 spec 建同名表时，`IF NOT EXISTS` 让后建的那份静默失效**：写入方要按库里真实的那份（V246）写。
8. **全量回归要能按片、按条重跑**：工具删 index（§3.7a）的那段时间里，读 git 状态的用例在哪棵树上都可能变红 ⇒
   candidate-only 逐条单跑再下结论；一个子进程卡在进程初始化（线程停在 Initialized、强杀后仍不退出）会挂住整片 ⇒
   分片清单落盘、可拆成子片重跑；长进程里个别用例比新进程慢几十倍（`test_pytest_import_isolation` 35 分钟以上 vs
   74 秒）⇒ 这类用例单独跑。
