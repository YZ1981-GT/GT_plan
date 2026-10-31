# 设计文档：S7　合并附注公式的范围与角色（consol-note-formula-scope-and-roles）

> 需求编号：requirements §1 两条记 R1（只列合并项目）、R2（全局写只给 admin）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`）。本 spec 涉及的文件母 spec 都没有改动语义（只有 `validator.py` 新增了 consol_note 校验转发），两棵树行为一致。数字为 2026-10-29 现算。

## 0. 结论

合并附注公式（consol_note 域）的作用范围按「模板类型」划分，没有区分合并 / 单体，所以全局发布、预览计数、传播都把单体项目算进来；全局写权限有两个入口、两套口径：公式设置中心只给 admin，旧端点 `/api/consol-note-formulas` 给 admin / partner / manager。修法：作用范围加「必须是合并项目」一层；旧端点写操作收口到 admin，前端按后端返回的能力字段显示编辑入口，不再自带角色名单。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：consol_note 列全部项目 | `formula_settings/projects.scope_of` 对 `scope_kind="template_type"` 只看 `template_type`（缺省 soe），`list_projects(db, "consol_note", scope="soe")` 返回全部未删的 soe 项目，与 `report_scope` 无关。真库未删项目：`consolidated` 1、`standalone` 11、`report_scope` 为空 73（`scope_of` 按 standalone 处理）⇒ 全局发布的预览与传播最多算进 84 个单体项目 | 成立 |
| 2 | 受影响的调用方 | `publish._context`（全局发布：预览计数 + 逐项目计划 + 事件）、`apply_ops`（应用到其他项目的目标）、`template_sync`（订阅项目）、`project_ops.require_project`（项目层读写）、`routers/formula_settings.py` 的「可应用项目」列表与项目有效定义端点。传播处理器 `propagate_consol_note` 对每个收到事件的项目跑 `fill_note_sections`，单体项目也会被跑一遍 | 新增（影响面） |
| 3 | R2：partner / manager 也能写全局 | 公式设置中心全局写 `_require_admin`（只 admin）；旧端点 `routers/consol_note_formulas.py` 的新增 / 修改 / 删除 / 重新种子化是 `require_role(["admin","partner","manager"])`，而 `consol_note_settings` 的文档写明旧端点的增删改就是全局发布（版本 +1、按同步内核影响所有订阅模板类型的项目） | 成立 |
| 4 | 前端口径 | `ConsolFormulaManagementPanel.vue` 自带 `managerRoles = {admin, partner, manager}` 判 `canManage`，提示文案「只有管理员、合伙人和经理可以新增、修改…」；它是公式管理中心合并附注节点的唯一编辑面板，只调旧端点（全局写），没有写本项目层的入口 | 成立；前端是第二份权限口径 |
| 5 | 真库数据 | `consol_note_formula` 未删 51 行，全部 soe；V199 `formula_setting` 0 行（没有任何项目层适配） | 收紧不影响存量 |

### §1 复核（Task 0，2026-10-29 现算）

五行逐条重算，结论与上表全部一致，无偏差。补充：

- **行 2 调用方补充**：`stores.py::project_scope` 也经 `scope_of` 取单项目域内作用范围（design 撰写时未列出，不影响改动计划——`scope_of` 改为 `consolidated_template_type` 后 `project_scope` 自动走新口径）。
- **行 5 项目分布明细**：`report_scope=NULL / template_type=NULL` 73 个 + `consolidated / NULL` 1 个 + `standalone / soe` 9 个 + `standalone / NULL` 2 个 = 85 总计（`template_type` 为 NULL 的 76 个在 `scope_of` 里缺省 soe）。数字与原表一致。
- 探针输出：`tmp_consol_note_scope/baseline/probe_results.txt`

## 2. 架构裁定

**ADR-CNS-01 作用范围 = 模板类型 + 合并项目。** `definitions.DomainSpec` 的 `scope_kind` 增值 `consolidated_template_type`，consol_note 改用它。`projects.scope_of` 对该口径：`report_scope != "consolidated"` ⇒ 返回 `None`（不适用），否则同 `template_type` 口径。`list_projects` 跳过 `scope is None` 的项目（`scope="*"` 时也跳过，因为该域对它们不适用）；`get_project` 对单体项目返回 `None`。调用方处理：

| 调用方 | 改动 |
|---|---|
| `publish._context` / `template_sync` | 自动只计合并项目（经 `list_projects`），不改代码，用例钉住 |
| `apply_ops.apply_to_projects` | 目标里的单体项目不再静默消失：结果逐个列入 `skipped[{project_id, reason:"该项目不是合并项目，不适用合并附注公式"}]` |
| `project_ops.require_project` | 区分「项目不存在」与「不适用」：后者 422 `FORMULA_DOMAIN_NOT_APPLICABLE`、中文原因同上 |
| `routers/formula_settings.py` 可应用项目列表 | 单体项目不列出 |
| `propagation.propagate_consol_note` | 入口再判一次项目是否合并（防旧事件、防 Redis Stream 重放），不是则返回 `{"skipped": "not_consolidated"}` |

**ADR-CNS-02 全局写只给 admin，能力字段单一来源。** 旧端点四个写操作改 `require_role(["admin"])`（读不变）。列表响应 `GET /api/consol-note-formulas` 增 `can_edit_global`（与公式设置中心 `_is_admin` 同口径，抽成 `formula_settings/permissions.py::can_edit_global(user)`，两处共用）。前端删掉 `managerRoles`，`canManage` 改读该字段；提示文案改为「只有管理员可以修改合并附注公式（修改会影响所有同模板的合并项目）」。权限测试按母 spec 的端点配方表方式：partner / manager / qc / eqcr / auditor / readonly 写 ⇒ 403 且 `consol_note_formula` 行与内容哈希不变，admin 写 ⇒ 成功。

**ADR-CNS-03 非 admin 的修改途径（§4 D2 待拍板）。** 收紧后 partner / manager 在界面上只能看。默认方案 A：不新增入口，需要改公式的项目找 admin 改全局，或由 admin 发布模板供项目订阅（现有能力）。备选 B：面板在合并项目上下文里给非 admin 提供「本项目适配」保存（写 `formula_setting` 项目层，经同步内核，只影响本项目），需要新增保存分派与「恢复为全局」按钮，约 1 个前端任务 + 1 个后端用例组。

## 3. 测试与变异

- 单元（SQLite）：`scope_of` 四种组合（soe / listed × 合并 / 单体）+ 空 `report_scope`；`list_projects("consol_note")` 只返回合并项目；`apply_to_projects` 单体目标进 `skipped`；`require_project` 对单体 422、对不存在 404。
- 端点：旧端点写操作权限配方表（9 种身份）；`can_edit_global` 字段 admin 为真、其余为假。
- 前端 vitest：`ConsolFormulaManagementPanel` 按 `can_edit_global` 显示 / 隐藏新增、删除、重新种子化与可编辑单元格；源码守卫：组件内不得再出现角色名字面量集合。
- 真 PG（回滚事务）：在【测试】合并项目与【测试】单体项目各一的夹具上做一次全局发布预览，受影响项目只含合并项目；共享库只读统计 consol_note 作用范围内项目数 = 未删合并项目数（现为 1）。
- 磁盘变异：`scope_of` 去掉合并判断 ⇒ 预览用例红；旧端点恢复三角色 ⇒ 配方表红；前端恢复角色集合 ⇒ 守卫红。

## 4. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 合并附注全局公式谁能改（requirements §3 触发条件） | 只给 admin（母 spec 评估报告 §10 的默认） |
| D2 | 非 admin 的修改途径 | 方案 A（不新增入口）；需要项目自定义时选 B |
| D3 | `report_scope` 为空的 73 个项目 | 按单体处理（与 `scope_of` 现有缺省一致），不改数据 |
