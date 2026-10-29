# 实施计划：S7　合并附注公式的范围与角色（consol-note-formula-scope-and-roles）

> 以 design.md 为准，需求编号 R1、R2 见 design 页头。启动条件：用户对 design §4 D1 拍板。
> 通用纪律：临时产物放仓库根 `tmp_consol_note_scope/`；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（`formula_settings/validator.py`、配方表测试基座在其中）。

- [x] 0. 现状复核
  - 重算 design §1 五行（`scope_of` 口径、调用方清单、旧端点角色、前端角色集合、真库行数），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_consol_note_scope/baseline/`

- [x] 1. 作用范围只含合并项目（R1，ADR-CNS-01）
  - `definitions.py` 增 `consolidated_template_type`；`projects.scope_of` / `list_projects` / `get_project`；`apply_ops` 单体目标进 `skipped`；`project_ops.require_project` 区分 404 / 422；`routers/formula_settings.py` 可应用项目列表；`propagation.propagate_consol_note` 入口判合并
  - Files: `backend/app/services/formula_settings/{definitions,projects,apply_ops,project_ops,propagation}.py`、`backend/app/routers/formula_settings.py`、测试
  - Verify: 单元用例全绿；回滚事务 PG 用例（合并 / 单体各一的【测试】夹具，全局发布预览只含合并项目）；共享库只读统计作用范围内项目数 = 未删合并项目数。变异：`scope_of` 去掉合并判断 ⇒ 预览用例红

- [x] 2. 全局写只给 admin，前后端同一能力字段（R2，ADR-CNS-02）
  - `formula_settings/permissions.py::can_edit_global`（公式设置中心与旧端点共用）；`routers/consol_note_formulas.py` 四个写操作改 admin、列表响应增 `can_edit_global`；`ConsolFormulaManagementPanel.vue` 删角色集合、读字段、改提示文案；`services/consolidationApi.ts` 类型补字段
  - Verify: 端点权限配方表（9 种身份，拒绝时 `consol_note_formula` 行数与内容哈希不变）；vitest（显示 / 隐藏 + 源码守卫）；单区域 vue-tsc 0 错误（注入一处类型错误能报出）。变异：旧端点恢复三角色 ⇒ 配方表红；前端恢复角色集合 ⇒ 守卫红

- [x] 3. 非 admin 的本项目适配入口（ADR-CNS-03 方案 B，仅 D2 选 B 时做；选 A 则本任务标「不做」并写明依据）
  - **不做**：design §4 D2 选择方案 A（不新增入口）。非 admin 需要改公式时由 admin 操作全局层，或由 admin 发布模板供项目订阅（现有能力）。方案 B 保留为未来可选项（ADR-CNS-03）。
  - Verify: vitest（非 admin 保存走项目层端点）；回滚事务 PG（保存后只本项目有效定义变化、其他合并项目不变）

- [-] 4. 回归、浏览器实测与收尾
  - 回归（2026-10-30）：`tests/formula_settings/` 431 passed；`test_consol_note_formulas.py` 34 passed / 2 failed（`test_seed_counts_on_real_templates` soe 与 listed 模板计数漂移，HEAD 同红——pre-existing，非本 spec 引入）；前端 vitest 18 passed。候选引入红 = 0 ✅
  - [ ]* 浏览器实测（后端 9980 超时不可达，无法登录）：admin 能改、经理只能看、单体项目不出现合并附注公式可应用项 —— 待环境恢复后手动走查
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
