# 实施计划：S5　取数结果的来源信封（formula-provenance-envelope）

> 以 design.md 为准，需求编号 R1~R3 见 design 页头。启动条件：审计留痕要求「可重算」，或 S3 需要输入摘要做过期判据。
> 通用纪律：临时产物放仓库根 `tmp_formula_provenance/`；迁移号实施时三路合扫；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库；附注执行器部分（任务 4）在 S2 任务 2 之后做。

- [ ] 0. 现状复核
  - 重算 design §1 六行（各域现有来源列、`note_wp_mapping` 表、零挂载组件、来源浮层挂载点、输入采集点），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_formula_provenance/baseline/`

- [ ] 1. 输入收集器（R1，ADR-FPE-02）
  - 新建 `backend/app/services/formula_inputs.py`；试算表叶子取数、`ROW` / `SUM_ROW`、预载取值各接一处 `emit`；`report_row_compute.compute_row` 外包 `collect()`
  - Verify: 单元（嵌套、截断、摘要顺序无关 / 取值敏感）。变异：`compute_row` 不包 `collect()` ⇒ 摘要用例红

- [ ] 2. 报表域信封与运行记录（R1，ADR-FPE-01/03）
  - 迁移 `V{n}` / `R{n}`（`financial_report.run_id`、`provenance`；`report_generation_run`）；ORM 与三层一致；三路生成写运行记录与信封；过期判据改比较 `definition_hash`；provenance 读取端点
  - Verify: 回滚事务 PG（全量生成、affected 重算只改引用行摘要、失败行保留旧信封）；端点权限配方表。变异：过期判据忽略 `definition_hash` ⇒ 判据用例红

- [ ] 3. 溯源改读权威注册表（R2，ADR-FPE-05）
  - `report_trace_service.trace_section` 改读注册表 + 项目自定义映射 + `note_account_mapping`；SQL 守卫
  - Verify: 有映射章节返回底稿编码的用例；UnifiedLineage 附注子源 `partial=false` 的用例；守卫带违规样本自检。变异：恢复查表 ⇒ 守卫红

- [ ] 4. 附注执行器与推送域信封（R1，ADR-FPE-04）
  - 附注执行器回写时写信封字段；`formula_push_state.provenance` 迁移与写入
  - Verify: 回滚事务 PG（【测试】附注执行后公式定义带 `run_id` / `input_digest`；推送一次后目标状态带信封）

- [ ] 5. 来源浮层挂到最终值（R3，ADR-FPE-06）
  - 报表页与附注编辑器数值格挂 `GtFormulaSourceTooltip`（懒取信封）；新挂载守卫 `finalValueProvenanceMounts.spec.ts`
  - Verify: vitest（挂载、懒取一次、过期标记显示）；单区域 vue-tsc 0 错误（注入一处类型错误能报出）。变异：报表页去掉浮层 ⇒ 挂载守卫红

- [ ] 6. 回归、浏览器实测与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：报表页悬停看到公式、版本、计算时间与输入，改试算表后重算再看摘要变化；附注同理；截图放 `tmp_formula_provenance/screenshots/`，用完停 about:blank
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
