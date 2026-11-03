# 设计文档：S6　公式模板双项目试点（formula-template-dual-project-pilot）

> 需求编号：requirements §1 三条记 R1（分层的 PG 契约测试 + 登录态 UAT）、R2（回滚发版、版本对比、新增公式位）、R3（所有订阅 / 退订写入口按目标项目 edit 权限）。
> 现状基线：以 Task 0 在当前候选树现算的探针为准；原设计中的固定 HEAD 已过期。S4 已将模板发版切到 `record_changes` → commit → `publish_pending`，本 spec 不得回到 `publish_events`。

## 0. 结论

模板链路的后端骨架齐全（建模板、发版、订阅 / 退订、待确认、设为全局），但从没有真实数据走过：真库模板、版本、订阅、发布记录都是 0 行。缺的是三件产品能力（回滚发版、版本对比、界面新增公式位）、一处前端权限门控，以及评估报告 P2-4 里没有分派给任何 S spec 的四个小缺口（§1 第 6~9 行，已纳入）。验收分层：先做 A 来源项目 + B/C 两个订阅项目的 PG 契约测试；S4 浏览器传播验收通过后，再用同一拓扑做登录态【测试】项目 UAT；真实项目另待用户明确授权。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | 真库模板链路 0 数据 | `formula_template` 0、`formula_template_version` 0、`formula_template_subscription` 0、`formula_publish` 0、`formula_setting` 0 | 成立 |
| 2 | R2 新增公式位 | 后端 `template_sync._publish_plan` 已支持：变更里模板没有的公式位会作为新增写入并对订阅项目出计划；界面 `FormulaTemplateManager.vue` 详情只能改已有公式位的定义 | 后端已有，缺界面 |
| 3 | R2 版本对比 | `GET /api/formula-templates/{id}/versions` 返回版本列表；每个版本的完整定义存在 `formula_template_version.snapshot`；没有对比端点，界面只显示版本号 | 缺对比 |
| 4 | R2 回滚发版 | 无任何端点；快照已有，可作为回滚内容来源 | 缺 |
| 5 | R3 订阅 / 退订写入口 | `FormulaSettingsToolbar.vue` 的「📑 保存为模板」「🔗 订阅模板」按钮没有任何权限门控。后端订阅 / 退订 preview 与 execute 要求目标项目 edit ⇒ 只读成员能点开写操作、提交时 403。建模板端点对来源项目只要求 readonly，共享范围选 team / group 时另要求归属项目 edit ⇒ 只读成员保存个人 / 事务所范围模板仍是合法操作，不应隐藏保存入口 | 订阅 / 退订待门控；保存模板保留 |
| 6 | （P2-4，未分派）域与适用范围不相容不拒绝 | `template_service.create_template` 只在 `source == "global"` 时用 `global_scope` 判相容；从项目或手工录入建模板时，例如附注域配 `enterprise` 也能建成，订阅时才发现上游取不到 | 成立 |
| 7 | （P2-4，未分派）共享范围收窄不处理既有订阅 | `update_template` 改共享范围（如事务所 → 个人）只校验范围合法，不看已订阅的项目；收窄后订阅方仍按模板生效，但已看不到该模板 | 成立 |
| 8 | （P2-4，未分派）订阅方 N+1 | `_publish_plan` 对每个订阅逐个 `get_project` + `upstream_records` + `list_project` | 成立；订阅数为 0 时无影响 |
| 9 | （P2-4，未分派）引导死路 | 全局设置页「公式模板」只能管理模板，订阅要到公式管理中心；从模板详情没有「去某个项目订阅」的入口 | 成立 |
| 10 | 依赖 S4 | 模板发版对每个订阅项目通过 durable outbox 扇出：写入事务记录 `record_changes`，提交后由 `publish_pending` 消费；浏览器传播验收未闭合前不能做双项目浏览器 UAT | 成立，但有执行门槛 |

## 2. 架构裁定

**ADR-FTP-01 回滚发版 = 以历史快照为内容发一个新版本。** 新端点 `POST /api/formula-templates/{id}/rollback-preview` 与 `POST /api/formula-templates/{id}/rollback`，请求体 `{target_version, expected_version, decisions?, request_id?}`。服务端读 `target_version` 的快照，与当前模板逐公式位求差（新增 / 修改 / 删除），把差集作为普通发版的 `changes` 交给 `template_sync.publish_template`：版本号 +1、订阅项目按同步内核出待确认、审计记 `action=template_rollback` 与源版本。不覆盖历史版本、不回退版本号。`target_version` 不存在 ⇒ 404；等于当前版本 ⇒ 422「已是该版本」；`expected_version` 缺 428、不符 409。权限与发版相同（`viewer.can_manage(tpl)`）。

**ADR-FTP-02 版本对比。** `GET /api/formula-templates/{id}/diff?from=a&to=b`（`to` 缺省 = 当前版本）：按域、公式位稳定排序，输出 `added / removed / changed`，每项含 `{domain, slot_key, label, old, new, kind}`；定义比较用 `definitions.normalize`（与同步内核判「是否变化」同一函数，只差空白不算改）。可见性同模板详情。

**ADR-FTP-03 界面三件事（R2、R3）。** `FormulaTemplateManager` 详情：①版本页签每行「与当前对比」「回滚到此版本」（后者走预览 → 待确认弹窗 → 发版，复用现有发版对话框）；②定义页签「新增公式位」（选域、填公式位与定义，提交走现有 `publish`）；③`FormulaSettingsToolbar` 的「订阅模板」按宿主传入的 `canEditProject` 显示（只读成员不显示，tooltip 说明原因）；「保存为模板」照常显示（后端只要求来源项目 readonly），保存对话框在 `canEditProject` 为假时禁用 team / group 两个共享范围并说明需要本项目编辑权限。保存对话框的所属项目就是 `projectId`；服务端仍按来源 / 所属项目真实权限判定，前端不自带角色名单。

**ADR-FTP-04 P2-4 的四个小缺口（§5 D2，已纳入）。** ①建模板 / 改适用范围时对每个域调 `global_scope`，为 `None` 且该域不是 `any` ⇒ 422「{域} 不适用于 {适用范围}」。②收窄共享范围：按更新后的可见性规则检查所有 active subscription，只要订阅项目的有效成员看不到模板就 409，并列出可授权展示的项目；不自动退订。③`_publish_plan` 批量取项目并按完整作用上下文缓存，不能让不同项目的 `scope / domain / local / subscription` 串用；测试验证没有按订阅逐项查询。④模板详情「订阅项目」页签按项目行增「到项目中订阅」入口，跳到公式管理中心并带 `projectId + templateId + action=subscribe` 自动打开指定订阅弹窗。

**ADR-FTP-05 UAT 分层（R1，§7）。** 第一层在 PG 回滚事务内创建来源项目 A、订阅项目 B/C（B 预置本项目适配，C 不预置），走建模板 → 订阅 → 含新增公式位发版 → 待确认 → diff → rollback → 退订，并逐项目断言有效定义和发布链路。第二层仅在 S4 浏览器传播验收通过后，使用专用【测试】项目和真实登录态执行同一流程，跨 HTTP 请求刷新或独立 GET 读回，结束后走平台删除和逐表对账。第三层真实项目试点不在本任务自动执行，必须由用户点名项目、时间并明确写入授权。

## 3. 测试与变异

- 单元（SQLite）：回滚差集计算（新增 / 修改 / 删除三类 + 等于当前版本）；对比输出与 `normalize` 口径（只差空白不算改）；相容性校验矩阵（7 域 × 适用范围）；收窄检测；preview 无副作用与 request_id 幂等。
- 端点：回滚、对比端点权限配方表（拥有者 / 管理员 / 可见非拥有者 / 不可见者）；订阅 / 退订 preview 与 execute 的目标项目权限；回滚 428 / 409 / 404 / 422；收窄 409 的项目清单；路由实际挂载。
- 真 PG（回滚事务内 A/B/C 测试项目）：B 有本项目适配、C 无本项目适配，订阅后发版、回滚，两个项目的有效定义与待确认逐项符合预期；N+1 测试验证结果隔离和无按订阅线性查询。
- 前端 vitest：只读成员不显示「订阅模板」、仍显示「保存为模板」且对话框里 team / group 禁用；版本 diff / 回滚动作；新增公式位提交载荷；`projectId + templateId + action=subscribe` 深链。
- 磁盘变异：回滚改为覆盖当前版本（不 +1）⇒ 版本用例红；对比不经 `normalize` ⇒ 空白用例红；工具栏去掉订阅门控 ⇒ vitest 红；相容性校验跳过 project 来源 ⇒ 矩阵用例红；preview 写入版本或 outbox ⇒ 无副作用用例红。

## 4. 风险

| 风险 | 处理 |
|---|---|
| S4 浏览器传播验收尚未闭合 | 先完成代码 / PG 契约验证；S4 浏览器传播通过后才执行 Task 4 登录态 UAT |
| UAT 在共享库留数据 | 浏览器只用 A/B/C【测试】项目；结束走平台删除路径，逐表核对模板、版本、订阅、设置、同步项、发布记录、outbox / propagation；审计只登记数量 |
| 回滚到很旧的版本，期间全局又变过 | 回滚走普通发版同步内核，订阅项目按待确认处理，不直接覆盖本项目适配；preview 和 execute 都使用当前版本 CAS |
| 真实项目误写 | Task 5 默认不执行；必须有用户点名、时间和明确写入授权，先 preview 后执行 |
| 当前工作树存在并发改动 | 实施 / 验证使用干净候选 worktree，不覆盖其他会话修改 |


## 5. 已裁决事项

| # | 事项 | 裁决 |
|---|---|---|
| D1 | 测试 / 真实项目拓扑与时间 | 测试阶段使用来源 A + 订阅 B/C；真实项目和时间待用户指定，代码阶段不执行真实写入 |
| D2 | P2-4 的四个小缺口是否纳入本 spec | 纳入 |
| D3 | 收窄共享范围时是否自动退订 | 不自动退订；按新可见性规则返回 409 和项目清单 |

## 6. 实施前契约补全

### 6.1 rollback / diff HTTP 契约

- `GET /api/formula-templates/{id}/diff?from=<version>&to=<version>`：`to` 缺省取请求开始时的当前版本；`from`、`to` 不存在按 404；`from == to` 返回空 `changes`，不写任何记录。
- diff 返回 `{template_id, from_version, to_version, changes}`。`changes` 按 `domain, slot_key` 排序，每项为 `{domain, slot_key, label, old, new, kind}`，`kind` 只能是 `added / removed / changed`；`old` 或 `new` 缺失的一侧为 `null`。两端定义先经 `normalize` 比较，但返回原始快照定义。
- `POST /api/formula-templates/{id}/rollback-preview` 与 `rollback` 请求体为 `{target_version, expected_version, decisions, request_id?, note?}`。缺 `expected_version` 返回 428，版本不符返回 409，目标版本不存在返回 404，目标等于当前版本返回 422。
- preview 只读：不得增加版本、发布记录、审计记录、待确认项或 outbox 行。响应至少含 `{template_id, target_version, current_version, next_version, changes, summary, items}`。
- rollback 只生成新版本，不改写历史快照；其差集交给普通 `publish_template`，并使用同一套 CAS、项目决策、待确认、审计和 outbox。审计 action 为 `template_rollback`，details 必须含 `source_version`、`created_version`、`publish_id`。
- `request_id` 沿用 `formula_publish.request_id` 唯一约束。相同模板、请求号和已完成发布再次提交返回原 `publish_id` 与 `idempotent=true`，不得创建第二个版本；preview 不占用请求号。
- 回滚目标快照必须经过当前模板域 / 适用范围的定义校验；删除公式位使用现有 `definition=null` 语义。回滚不自动退订、不直接覆盖订阅项目本地改动。

### 6.2 共享范围和适用范围

- 创建模板、修改模板适用范围或修改模板域集合时，对每个域调用同一 `global_scope(domain, applicable_scope)` 校验；`scope_kind != any` 且无法解析时返回 422。
- 更新共享范围不做字符串大小比较，而是用更新后的可见性规则检查所有 active subscription。只要订阅项目的有效成员无法继续看见模板，返回 409，事务不写入。
- `_publish_plan` 的批量项目查询和缓存必须保证不同项目的 `scope / domain / local / subscription` 上下文不会串用；SQL 数量测试只验证没有按订阅逐项读取项目，而不能牺牲结果隔离。

### 6.3 前端深链和权限

- 模板详情「到项目中订阅」必须携带 `projectId + templateId + action=subscribe`；目标公式管理页消费后自动打开指定模板的订阅弹窗，缺少任一参数时只进入普通页面。
- `FormulaSettingsToolbar` 仅在 `canEditProject` 为真时展示订阅按钮；保存为模板继续展示。保存对话框按来源 / 所属项目的真实 edit 能力禁用 `team / group`，事务所仍由服务端 admin 判定。
- UI 门控不代替后端鉴权。订阅、退订的 preview / execute，以及 diff / rollback 均须使用真实依赖链测试未登录、只读、可编辑、不可见和管理员场景。

## 7. UAT 方案

### 7.1 PG 契约测试

在测试夹具创建来源项目 A、订阅项目 B/C；B 有本项目适配，C 没有。事务内完成建模板、订阅、含新增 slot 的发版、待确认处理、diff、rollback、退订，并逐项目断言有效定义、订阅版本、pending、发布记录、outbox 和审计摘要。

### 7.2 登录态浏览器 UAT

S4 浏览器传播验收通过后，使用专用【测试】项目和真实登录态执行同样流程。每个 HTTP 步骤都刷新或独立 GET 读回；产物写入 `tmp_formula_template_pilot/`。结束后走平台删除路径，逐表核对模板、版本、订阅、设置、同步项、发布记录、outbox / propagation 状态；审计只登记数量，不物理删除。

### 7.3 真实项目试点

当前任务不执行。用户指定项目、时间并明确授权后，先 preview，再由用户确认执行 publish / rollback；保存执行前快照和每一步回执，出现传播失败、版本冲突或待确认数量异常即停止。

## 8. 设计决策

- D1：测试阶段采用 A + B/C 三项目拓扑；真实试点项目和时间另待用户指定。
- D2：纳入 P2-4 四个小缺口。
- D3：共享范围收窄不自动退订，按新可见性规则返回 409。
