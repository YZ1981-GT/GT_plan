# 实施计划：S6　公式模板双项目试点（formula-template-dual-project-pilot）

> 以 design.md 为准，需求编号 R1~R3 见 design 页头。
> 通用纪律：临时产物放仓库根 `tmp_formula_template_pilot/`；真 PG 写入只在回滚事务内或【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：S4 `formula-settings-durable-outbox` 已入库（模板发版扇出走 outbox）；母 spec 已入库。

- [ ] 0. 现状复核
  - 重算 design §1 十行（真库模板链路行数、新增公式位前后端、对比与回滚端点、工具栏门控、P2-4 四个缺口），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_formula_template_pilot/baseline/`

- [ ] 1. 回滚发版与版本对比（R2，ADR-FTP-01/02）
  - `template_sync` 增回滚差集；路由 `rollback-preview`、`rollback`、`diff`；审计 `template_rollback`
  - Verify: 单元（差集三类、等于当前版本 422）；端点权限配方表与 428 / 409 / 404；回滚事务 PG（两个【测试】订阅项目回滚后的有效定义与待确认）。变异：回滚改为覆盖当前版本 ⇒ 版本用例红；对比不经 `normalize` ⇒ 空白用例红

- [ ] 2. P2-4 四个小缺口（ADR-FTP-04，仅 design §5 D2 纳入时做；不纳入则本任务标「不做」并写明依据）
  - 相容性校验（建模板 / 改适用范围）；收窄共享范围 409 列项目；`_publish_plan` 去 N+1；模板详情「到项目中订阅」入口
  - Verify: 相容性矩阵用例；收窄 409 用例；N+1 语句数用例（订阅 1 个与 5 个相同）。变异：相容性校验跳过 project 来源 ⇒ 矩阵用例红

- [ ] 3. 界面：版本对比、回滚、新增公式位、按钮门控（R2、R3，ADR-FTP-03）
  - `FormulaTemplateManager.vue` 版本页签两个动作、定义页签「新增公式位」；`FormulaSettingsToolbar.vue` 的「订阅模板」按 `canEditProject` 显示，「保存为模板」保留、对话框在无编辑权限时禁用 team / group 共享范围；`services/formulaSettingsApi.ts` 补接口
  - Verify: vitest（订阅门控、保存为模板仍可用且 team / group 禁用、两个动作、新增载荷）；单区域 vue-tsc 0 错误（注入一处类型错误能报出）；ESLint。变异：工具栏去掉订阅门控 ⇒ vitest 红

- [ ] 4. 【测试】项目双项目 UAT（R1 第一步，ADR-FTP-05）
  - 共享库经平台路径新建两个【测试】项目；按 design ADR-FTP-05 的 8 步走完，每步接口与浏览器（chrome-devtools）双证，刷新或查库确认写入能读回；截图放 `tmp_formula_template_pilot/screenshots/`，用完停 about:blank
  - 清理走平台删除路径，按表对账（模板、版本、订阅、`formula_setting`、`formula_sync_item`；审计条目只登记数量）
  - Verify: 8 步记录与对账表贴入本任务

- [ ] 5. 真实项目试点（R1 第二步，design §5 D1）
  - 用户点名项目与时间后，按任务 4 的步骤执行（不做删除）；保留记录
  - Verify: 试点记录贴入本任务；未获点名前保持 `[ ]`，写明「依赖用户指定试点项目」

- [ ] 6. 回归与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
