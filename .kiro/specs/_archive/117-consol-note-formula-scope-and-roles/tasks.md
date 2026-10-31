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

- [x] 4. 回归、浏览器实测与收尾
  - 回归（2026-10-30）：`tests/formula_settings/` 431 passed；`test_consol_note_formulas.py` 34 passed / 2 failed（`test_seed_counts_on_real_templates` soe 与 listed 模板计数漂移，HEAD 同红——pre-existing，非本 spec 引入）；前端 vitest 18 passed。候选引入红 = 0 ✅
  - [x] 任务 1 单元用例入库（2026-10-31）：主工作树未跟踪的 `backend/tests/formula_settings/test_consol_note_scope.py`（232 行，sha256 `a0e0ced2…`）原样复制进待提交树；在 v1.0.58（`434e87972`）上 `python -m pytest -p no:playwright tests/formula_settings/test_consol_note_scope.py` → 23 passed
    - 磁盘变异（单独一条命令，`tmp_spec_closure/item_a/mutate_scope_of.py`）：`projects.scope_of` 删去 `if report_scope != "consolidated": return None` ⇒ 11 failed / 12 passed，失败集合与预期逐条一致（单体 / 空范围的 scope 不再是 None、`list_projects` 混进单体、`get_project` 返回单体、`require_project` 对单体 DID NOT RAISE `DomainNotApplicable`）；还原后 sha256 逐字节一致（`45a96052…`，git blob `b93c97e1` = HEAD）
    - 勘误：该文件文件头写了「`apply_to_projects` 单体目标进 skipped」「`propagate_consol_note` 非合并返回 skipped」两项，文件里没有对应用例 —— 这两项不由本文件覆盖
  - 回归复算（2026-10-31，v1.0.58 + 上述测试文件）：`tests/formula_settings/` 434 collected → 432 passed / 2 failed；2 failed 都在 `test_wp_formula_save_gate.py`（`no such table: audit_log_entries`），单独跑该文件同红，与本 spec 无关。不含新文件时 411 collected —— 10-30 记的「431 passed」在已提交的树上复现不出来
  - [x] 浏览器实测（2026-10-31 补测；原记录：「后端 9980 超时不可达，无法登录」）：admin 能改、经理只能看、单体项目不出现合并附注公式可应用项
    - 环境：node playwright 自起无头 chromium → 候选前端 3093（worktree v1.0.58，代理写死 9993、关 HMR）→ 候选后端 9993。共享 9980 不能只读浏览：回滚事务试跑现算，`GET /api/consol-note-formulas` 的读时种子化会改写全局表 `consol_note_formula`（soe 新建 39 / 更新 3 / 删除 39）。候选后端用启动器给所有 PG 连接加 `default_transaction_read_only=on`（探针写入被拒 `ReadOnlySQLTransactionError`），并把读时种子化换成空操作；走查前后共享库 9 张相关表逐表 md5 一致
    - admin 能改（全局层，只核对控件，未保存）：全局公式设置页「合并附注公式 · 国企版」51 个公式位都有「编辑」、有「预览并发布」；暂存一处改动后预览显示「受影响项目 1 个」、逐项目处理只列【UAT】合成集团母公司，点「取消」再「清空」，没有发出 publish 请求。公式管理中心合并附注面板：列表响应 `can_edit_global=true`，有「重新种子化」「+ 新增公式」「删除」，双击单元格出编辑器、Esc 退出，没有写请求
    - 经理只能看（现成测试账号 `e2e_manager`，系统角色 manager；未新建、未改账号）：列表响应 `can_edit_global=false`；面板显示「当前角色可查看合并附注公式；只有管理员可以修改合并附注公式…」，没有重新种子化 / 新增 / 删除 / 操作列，单元格全只读、双击不出编辑器；全局设置页显示只读提示，没有编辑与预览。接口层同账号对新增 / 修改 / 删除 / 重新种子化四个写操作都是 403，全局预览 403
    - 单体项目不出现：以【UAT】子公司A（单体）为来源，`apply-targets?domain=consol_note` 只返回【UAT】合成集团母公司 1 个；`domain=note` 返回 85 个（含【UAT】子公司B、【测试】附件小眼睛走查_2025 两个单体）；以合并项目为来源时 consol_note 为 0 个（库里只有它一个合并项目）。全局发布预览的逐项目处理同样只列合并项目
    - 证据：`tmp_spec_closure/item_a/`（`browser_s7.json`、`api_checks_9993.json`、`snapshot_before.json` / `snapshot_after.json`、`mutation_report.json`），截图 `tmp_spec_closure/screenshots/s7_*.png`
  - [x] INDEX.md 本行与 memory.md 任务状态（2026-10-31 收尾：INDEX 本行改 5/5，memory 补一句；与本 spec 收尾同一提交推送，版本号见该提交的标签）
  - Verify: 只候选红 = 0；推送带版本号与主要变动
