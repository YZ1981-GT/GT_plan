# 设计文档：S5　取数结果的来源信封（formula-provenance-envelope）

> 需求编号：requirements §1 三条记 R1（最终值带定义版本 / run_id / 输入摘要）、R2（`note_wp_mapping` 的来源）、R3（零挂载组件裁决）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`，含 ADR-FHIC-04 计算版本、ADR-FHIC-16 溯源子源隔离）。数字为 2026-10-29 共享库只读现算。

## 0. 结论

「这个数是谁按哪版公式、用哪些输入算的」现在只有公式推送域答得上来（每个目标记 `last_run_id` 指向运行记录）；报表行只记了用的公式文本与生成时间，附注执行器只记 `evaluated_at`，而且真库从没写过。本设计以报表域为主体落地信封（列 + 运行记录 + 取数输入收集），附注执行器在公式定义 JSON 里写同一组字段，推送域补齐缺的两项；底稿域的信封依赖 S1 把底稿公式统一到有效定义之后再做（§4 D1）。`note_wp_mapping` 表不存在，溯源改读已有的权威注册表。零挂载组件在 `components/formula` 下现算为 0，R3 改为把「三处通用」的来源浮层挂到报表与附注的最终值上。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：最终值没有定义版本 / run_id / 输入摘要 | `financial_report`（3168 行）有 `formula_used`、`source_accounts`、`generated_at`、`is_stale`、`blank_reason`、`calc_version`、`calc_error`（后两列为母 spec V229，2026-10-31 由 V220 重编号）；无定义版本、无运行标识、无输入摘要、无计算人 | 成立 |
| 2 | 其他域现状 | 推送：`formula_push_state`（388 行）有 `last_run_id`（→ `formula_push_run`，54 行，含触发来源与触发人）、`last_formula_value`、`updated_by`；合并附注：`consol_note_data` 有 `last_formula_run_id`、`last_formula_value`；附注执行器：公式定义里写 `evaluated_at`、`addr_id`，真库活项目 0 节写过；底稿：`wp_formula` 有 `definition_version`、`definition_hash`、`last_computed_at`（29 行全是夹具） | 推送域已基本具备 |
| 3 | R2：`note_wp_mapping` 表不存在 | 共享库 `to_regclass('note_wp_mapping')` 为空；`report_trace_service.trace_section` 仍按表查（母 spec 已用保存点隔离，不再拖垮同请求其他子源，但该子源恒为部分结果）。权威映射是 `backend/data/note_workpaper_sync_registry.json`（由前端各底稿 `*NoteSectionMap.ts` 生成，`note_readiness_service` 已以它为唯一来源）；另有旧口径 `note_wp_mapping_service.DEFAULT_WP_MAPPING`（章节号是老体系）与项目级 `wizard_state.note_wp_mapping` | 成立；改读注册表 |
| 4 | R3：零挂载组件待裁决 | `components/formula` 下 42 个组件、未被生产代码引用的 0 个（挂载守卫 `formulaComponentMounts.spec.ts` 断言为空，本次独立复算一致） | 已由前序 spec 清零 |
| 5 | （交接未列）来源浮层未挂到最终值 | `GtFormulaSourceTooltip.vue` 自述「底稿 / 报表 / 附注三处通用」，生产挂载只有 `D3TabDetail.vue` 与 `GtS34SubCheckTable.vue` 两个底稿试点；报表页与附注编辑器的数值格都没有 | 新增：R3 的真正缺口 |
| 6 | 输入摘要的采集点 | L1 求值的 `trace` 是展示文本；母 spec 已有 `ContextVar` 收集器先例 `formula_warnings`（`collect()` / `emit()`）；报表三路共用 `report_row_compute.compute_row` | 可按同一模式加输入收集 |

## 2. 架构裁定

**ADR-FPE-01 信封字段（各域同名）。** `definition_version`（生效定义的版本号）、`definition_hash`（生效公式规范化文本的 sha256，与同步内核判「是否变化」同一规范化函数）、`definition_layer`（global / project / template / preset）、`run_id`、`computed_at`、`computed_by`（触发人，系统触发为空）、`calc_version`（母 spec 的计算语义版本）、`inputs`（本次实际取到的输入，见 ADR-02）、`input_digest`（`inputs` 规范化 JSON 的 sha256）。

**ADR-FPE-02 输入收集器。** 新模块 `backend/app/services/formula_inputs.py`，模式同 `formula_warnings`：`collect()` 产出列表，取数点 `emit(kind, key, value)`。接入点：试算表叶子取数（母 spec `tb_leaf_codes` 的调用方，记 `("TB", "科目码|列名", 叶子合计)`）、`ROW` / `SUM_ROW`（记被引用行与值）、`REPORT` / `NOTE` / `WP` / `AUX` / `ADJ` / `PREV` 的预载取值。`compute_row` 外包 `collect()`，结果进 `RowOutcome.inputs`。每行最多保留 200 条输入，超出记 `inputs_truncated: true`（摘要仍对全量计算）。

**ADR-FPE-03 报表域落地。** 迁移：`financial_report` 增 `run_id uuid NULL`（带索引）、`provenance jsonb NULL`（ADR-01 其余字段）；新表 `report_generation_run(id, project_id, year, trigger, triggered_by, started_at, finished_at, calc_version, changed_rows, recomputed_rows, failed_rows, status)`。三路生成（全量、affected、stale）各开一条运行记录，成功写入的行带 `run_id` 与 `provenance`，失败保留旧值的行只更新 `calc_error`、不改信封（信封描述的是旧值的来源）。母 spec 的逐行过期判据「规范化公式文本与当前生效公式不同」改为比较 `provenance.definition_hash`（旧行 `provenance` 为空时退回原判据）。读取：`GET /api/projects/{pid}/reports/{report_type}/rows/{row_code}/provenance?year=`（readonly），返回信封、运行记录摘要与输入列表。

**ADR-FPE-04 附注执行器与推送域。** 附注执行器（S2 改造后的回写路径）在公式定义 JSON 里写 ADR-01 字段（`run_id` = 每次执行生成的 uuid；现在唯一的生产入口是附注页「执行公式」端点，以后新增入口同样各自生成），不新增表；推送域 `formula_push_state` 增 `provenance jsonb NULL`（补 `definition_hash`、`inputs`、`input_digest`，运行标识沿用 `last_run_id`）。合并附注沿用 `last_formula_run_id`，本 spec 不改。

**ADR-FPE-05 溯源改读权威注册表（R2）。** `report_trace_service.trace_section` 删除对 `note_wp_mapping` 表的查询，改为：章节 → 底稿编码取 `note_workpaper_sync_registry.json`（按项目模板类型选国企 / 上市，读取函数复用 `note_readiness_service` 的注册表加载）；项目 `wizard_state.note_wp_mapping` 有自定义映射时优先；章节 → 科目码取 `note_account_mapping`。守卫：`backend/app` 内 SQL 文本不得再出现 `FROM note_wp_mapping`。UnifiedLineage 的附注子源由「恒部分结果」变为正常。

**ADR-FPE-06 来源浮层挂到最终值（R3）。** 报表页数值格与附注编辑器数值格（有公式的格）挂 `GtFormulaSourceTooltip`，悬停时懒取 ADR-03 / ADR-04 的信封，显示公式、版本与层级、计算时间与人、主要输入（前 10 条）、是否过期。挂载守卫扩展：`formulaComponentMounts.spec.ts` 之外新增 `finalValueProvenanceMounts.spec.ts`，登记「最终值展示面」清单（报表页、附注编辑器、两个底稿试点），每个都必须引用该组件，清单不得为空且条目真实存在。

## 3. 测试与变异

- 单元：`formula_inputs` 嵌套收集与截断；`input_digest` 对输入顺序不敏感、对任一取值敏感；`definition_hash` 与同步内核规范化同口径（只差空白不变）。
- 真 PG（回滚事务内【测试】项目）：全量生成后每个有公式的行都有 `run_id` 与信封、`report_generation_run` 计数与结果一致；改一个试算表叶子金额后 affected 重算，只有引用它的行 `input_digest` 变化；失败行保留旧信封；过期判据按 `definition_hash`。
- 端点：provenance 端点权限配方表（成员 readonly 可读、非成员 403）。
- 溯源：`trace_section` 对注册表里有映射的章节返回底稿编码；SQL 守卫带违规样本自检。
- 前端 vitest：报表格与附注格挂浮层、懒取一次；新挂载守卫。
- 磁盘变异：`compute_row` 不包 `collect()` ⇒ 输入摘要用例红；过期判据改回比较公式文本而忽略 `definition_hash` ⇒ 判据用例红；`trace_section` 恢复查表 ⇒ SQL 守卫红；报表页去掉浮层 ⇒ 挂载守卫红。

## 4. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 底稿域信封 | 放到 S1（底稿公式统一读有效定义）之后再做，本 spec 不做；理由：底稿公式现在有 `wp_formula`、预设、全局三条读取路径，信封记哪一版定义要等 S1 统一后才有唯一答案 |
| D2 | 存量报表行没有信封 | 不回填；重新生成时自然补齐（与母 spec D13-A 一致） |
| D3 | 输入列表的保存上限 | 每行 200 条（摘要算全量）；超大公式实际不存在（真库报表公式只用 TB / SUM_TB / ROW / SUM_ROW） |
