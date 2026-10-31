# 设计文档：S6　公式模板双项目试点（formula-template-dual-project-pilot）

> 需求编号：requirements §1 三条记 R1（双项目真 PG + 登录态 UAT）、R2（回滚发版、版本对比、新增公式位）、R3（订阅按钮按 edit 权限）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`）。模板相关代码母 spec 只改了发布记录可见性与删除 CAS，其余两棵树一致。数字为 2026-10-29 现算。

## 0. 结论

模板链路的后端骨架齐全（建模板、发版、订阅 / 退订、待确认、设为全局），但从没有真实数据走过：真库模板、版本、订阅、发布记录都是 0 行。缺的是三件产品能力（回滚发版、版本对比、界面新增公式位）、一处前端权限门控，以及评估报告 P2-4 里没有分派给任何 S spec 的四个小缺口（§1 第 6~9 行，建议一并纳入，§5 D2）。验收分两步：先用两个【测试】项目在共享库里走完整条登录态链路，再按用户选定的真实项目试点。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | 真库模板链路 0 数据 | `formula_template` 0、`formula_template_version` 0、`formula_template_subscription` 0、`formula_publish` 0、`formula_setting` 0 | 成立 |
| 2 | R2 新增公式位 | 后端 `template_sync._publish_plan` 已支持：变更里模板没有的公式位会作为新增写入并对订阅项目出计划；界面 `FormulaTemplateManager.vue` 详情只能改已有公式位的定义 | 后端已有，缺界面 |
| 3 | R2 版本对比 | `GET /api/formula-templates/{id}/versions` 返回版本列表；每个版本的完整定义存在 `formula_template_version.snapshot`；没有对比端点，界面只显示版本号 | 缺对比 |
| 4 | R2 回滚发版 | 无任何端点；快照已有，可作为回滚内容来源 | 缺 |
| 5 | R3 订阅按钮 | `FormulaSettingsToolbar.vue` 的「📑 保存为模板」「🔗 订阅模板」按钮没有任何权限门控。后端 `subscribe-preview` / `subscribe` / `unsubscribe-preview` / `unsubscribe` 要求项目 edit ⇒ 只读成员能点开订阅、提交时 403。建模板端点 `POST /api/formula-templates` 对来源项目只要求 readonly，共享范围选 team / group 时另要求归属项目 edit ⇒ 只读成员「保存为模板」（个人 / 事务所范围）是合法操作，不应隐藏 | 订阅成立；保存为模板不在 R3 范围 |
| 6 | （P2-4，未分派）域与适用范围不相容不拒绝 | `template_service.create_template` 只在 `source == "global"` 时用 `global_scope` 判相容；从项目或手工录入建模板时，例如附注域配 `enterprise` 也能建成，订阅时才发现上游取不到 | 成立 |
| 7 | （P2-4，未分派）共享范围收窄不处理既有订阅 | `update_template` 改共享范围（如事务所 → 个人）只校验范围合法，不看已订阅的项目；收窄后订阅方仍按模板生效，但已看不到该模板 | 成立 |
| 8 | （P2-4，未分派）订阅方 N+1 | `_publish_plan` 对每个订阅逐个 `get_project` + `upstream_records` + `list_project` | 成立；订阅数为 0 时无影响 |
| 9 | （P2-4，未分派）引导死路 | 全局设置页「公式模板」只能管理模板，订阅要到公式管理中心；从模板详情没有「去某个项目订阅」的入口 | 成立 |
| 10 | 依赖 S4 | 模板发版对每个订阅项目扇出传播（现走提交后 `publish_events`） | 成立；本 spec 在 S4 之后实施 |

## 2. 架构裁定

**ADR-FTP-01 回滚发版 = 以历史快照为内容发一个新版本。** 新端点 `POST /api/formula-templates/{id}/rollback-preview` 与 `POST /api/formula-templates/{id}/rollback`，请求体 `{target_version, expected_version, decisions?, request_id?}`。服务端读 `target_version` 的快照，与当前模板逐公式位求差（新增 / 修改 / 删除），把差集作为普通发版的 `changes` 交给 `template_sync.publish_template`：版本号 +1、订阅项目按同步内核出待确认、审计记 `action=template_rollback` 与源版本。不覆盖历史版本、不回退版本号。`target_version` 不存在 ⇒ 404；等于当前版本 ⇒ 422「已是该版本」；`expected_version` 缺 428、不符 409。权限与发版相同（`viewer.can_manage(tpl)`）。

**ADR-FTP-02 版本对比。** `GET /api/formula-templates/{id}/diff?from=a&to=b`（`to` 缺省 = 当前版本）：按域、公式位输出 `added / removed / changed[{slot_key, label, old, new}]`，定义比较用 `definitions.normalize`（与同步内核判「是否变化」同一函数，只差空白不算改）。可见性同模板详情。

**ADR-FTP-03 界面三件事（R2、R3）。** `FormulaTemplateManager` 详情：①版本页签每行「与当前对比」「回滚到此版本」（后者走预览 → 待确认弹窗 → 发版，复用现有发版对话框）；②定义页签「新增公式位」（选域、填公式位与定义，提交走现有 `publish`）；③`FormulaSettingsToolbar` 的「订阅模板」按宿主传入的 `canEditProject` 显示（只读成员不显示，tooltip 说明原因）；「保存为模板」照常显示（后端只要求来源项目 readonly），保存对话框在 `canEditProject` 为假时禁用 team / group 两个共享范围并说明需要本项目编辑权限（实施时现读对话框传的归属项目是否就是当前项目，不是则按归属项目的权限判）。前端不自带角色名单。

**ADR-FTP-04 P2-4 的四个小缺口（§5 D2，默认纳入）。** ①建模板 / 改适用范围时对每个域调 `global_scope`，为 `None` 且该域不是 `any` ⇒ 422「{域} 不适用于 {适用范围}」。②收窄共享范围：有订阅项目且收窄后订阅项目的成员看不到该模板 ⇒ 409 并列出项目，界面提示先让这些项目退订（不自动退订，避免改别人项目的公式）。③`_publish_plan` 按作用范围缓存 `upstream_records`、批量取项目（一次 `list_projects(ids=…)`），用例断言 SQL 次数不随订阅数线性增长。④模板详情「订阅项目」页签增「到项目中订阅」入口（跳到公式管理中心并带 `projectId` 打开订阅对话框）。

**ADR-FTP-05 UAT 分两步（R1，§5 D1）。** 第一步在共享库用两个【测试】项目（经平台正常路径新建，名称带「【测试】」）走完：建模板 → 两个项目订阅（一个有本项目适配，一个没有）→ 发版（含新增公式位）→ 两个项目分别出现「已更新 / 待确认」→ 处理待确认 → 对比 → 回滚发版 → 退订（保留 / 回全局各一）。每一步用接口与浏览器双证（chrome-devtools，刷新或查库确认写入能读回），清理走平台删除路径并按表对账（模板、版本、订阅、`formula_setting`、`formula_sync_item`、审计条目只追加不删）。第二步真实项目试点由用户点名项目后执行，步骤同第一步、不做删除。

## 3. 测试与变异

- 单元（SQLite）：回滚差集计算（新增 / 修改 / 删除三类 + 等于当前版本）；对比输出与 `normalize` 口径（只差空白不算改）；相容性校验矩阵（7 域 × 适用范围）；收窄检测。
- 端点：回滚、对比端点权限配方表（拥有者 / 管理员 / 可见非拥有者 / 不可见者）；回滚 428 / 409 / 404 / 422；收窄 409 的项目清单。
- 真 PG（回滚事务内两个【测试】项目）：订阅后发版、回滚，两个项目的有效定义与待确认逐项符合预期；N+1 用例数 SQL（订阅 1 个与 5 个时语句数相同）。
- 前端 vitest：只读成员不显示「订阅模板」、仍显示「保存为模板」且对话框里 team / group 禁用；版本页签两个动作；新增公式位提交载荷。
- 磁盘变异：回滚改为覆盖当前版本（不 +1）⇒ 版本用例红；对比不经 `normalize` ⇒ 空白用例红；工具栏去掉订阅门控 ⇒ vitest 红；相容性校验跳过 project 来源 ⇒ 矩阵用例红。

## 4. 风险

| 风险 | 处理 |
|---|---|
| S4 未完成时发版扇出仍是提交后发事件 | 本 spec 排在 S4 之后；UAT 第一步观察传播状态（S4 的 `propagation` 字段） |
| UAT 在共享库留数据 | 只用【测试】项目；审计表只追加，清理清单里登记审计条目数不删除 |
| 回滚到很旧的版本，期间全局又变过 | 回滚走普通发版的同步内核，订阅项目按待确认处理，不直接覆盖本项目适配 |

## 5. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 真实项目试点选哪两个项目、何时做（requirements §3 触发条件） | 第一步【测试】项目 UAT 先做；真实项目由用户点名 |
| D2 | P2-4 的四个小缺口是否纳入本 spec | 纳入（都属模板链路、各自改动小） |
| D3 | 收窄共享范围时是否自动退订 | 不自动，409 列出项目 |
