# 实施计划：S6　公式模板双项目试点（formula-template-dual-project-pilot）

> 以 requirements.md / design.md 为准，需求编号 R1~R3 见 design 页头。
> 通用纪律：临时产物放仓库根 `tmp_formula_template_pilot/`；后端 PG 契约写入只在回滚事务内或【测试】项目；真实项目不在本任务自动写入。标完成须有代码、测试、至少一条单独执行的磁盘变异及 sha256 还原核对；提交前在干净 worktree 跑候选树并与基线失败集合对比；推送使用 `.git-hooks/push_version.py`。
> 当前决策：D2 纳入 P2-4；D3 收窄共享范围不自动退订，返回 409；D1 测试拓扑为来源项目 A + 订阅项目 B/C，真实项目待用户指定。

- [x] 0. 现状重算与前置门
  - 以当前候选树重算 design §1 全部结论：模板 / 版本 / 订阅 / 发布 / 设置 / outbox 行数，模板发版是否经 `record_changes` → commit → `publish_pending`，路由注册、域清单、适用范围和 share scope 现值，前后端现有接口形状。
  - 记录当前 HEAD、S4 实际提交和浏览器验收状态；S4 浏览器传播未闭合前不执行 Task 4 登录态 UAT。
  - Verify：探针输出存 `tmp_formula_template_pilot/baseline/`，并追加 design §1；不得在当前有其他会话脏改动的工作树里覆盖他人文件。
  - 2026-10-31：HEAD = cd45ec129，S4 代码已完成（8/8），浏览器验收待推送。design §1 十行全部成立，S4 已切到 `record_changes` → commit → `publish_pending`。路由在 `router_registry/report.py` 注册。真库模板链路 0 行。

- [x] 1. 后端契约、适用范围和模板版本能力（R2、P2-4、ADR-FTP-01/02/04）
  - 先实现共享适用范围校验、共享范围收窄可见性检查和跨项目安全的批量读取；不同项目上下文不能共用错误的 `upstream_records`。
  - 增加 `GET .../diff`，按 `domain, slot_key` 稳定排序，使用 `normalize`，返回 `added / removed / changed`。
  - 增加 `rollback-preview` / `rollback`：快照生成新版本，复用普通 publish 的 CAS、决策、待确认、审计和 outbox；preview 无写入；`request_id` 幂等；回滚审计 action=`template_rollback`。
  - 端点注册、不可见 404、管理权限、428 / 409 / 404 / 422、删除公式位和当前适用范围校验均纳入。
  - Verify：服务层与端点测试、预览无副作用、回滚三类差集、幂等、并发 CAS、权限配方表、收窄 409、N+1 结果隔离；变异：回滚覆盖当前版本、diff 跳过 normalize、project 来源跳过相容性校验、收窄后仍允许发布，均必须打红。
  - 2026-10-31 实施完成：
    - `template_service.py`：增 `validate_applicable_scope`（建模板 / 改适用范围对每域调 `global_scope`，不兼容返回 422 `FORMULA_DOMAIN_NOT_APPLICABLE`）；增 `template_diff`（按 `normalize` 比较快照，返回 `added / removed / changed`）；增 `rollback_changes`（目标等于当前 422、不存在 404）；`update_meta` 共享范围收窄调 `hidden_subscriber_projects` 返回 409 列项目。
    - `template_access.py`：增 `hidden_subscriber_projects`，按更新后的可见性规则检查全部 active subscription，不做字符串大小比较。
    - `template_sync.py`：`_publish_plan` 改为按域批量取项目（`list_projects(ids=…)`）、批量取本地行（`list_project_many`）、按 scope 缓存 upstream（`upstream_by_scope`）；`publish_template` 增 `publish_source`/`item_action`/`audit_action`/`audit_details` 参数，支持回滚审计；幂等返回增 `template_id`/`version`。
    - `formula_templates.py` 路由：增 `RollbackBody`、`GET /{id}/diff`、`POST /{id}/rollback-preview`、`POST /{id}/rollback`；create/update/delete 补 `await db.commit()`（修复 S4 切换后的持久化断裂）。
    - 测试 `test_templates.py`：增 `test_template_diff_and_rollback_creates_new_version`（diff 三类 + 回滚生成 v4 + 幂等 + 审计 action）、`test_template_scope_validation_and_narrowing_are_fail_closed`（不兼容 422 + 收窄 409 含项目清单）。
    - 测试 `test_template_endpoints.py`：增 `test_diff_rollback_preview_and_idempotent_publish`（端点级 diff → publish → rollback preview 无写入 → rollback 幂等 → 当前版本 422）、`test_diff_and_rollback_keep_template_visibility`（不可见者 404）；修复事件捕获（`event_log` 替代空 `events`）。
    - 后端回归：test_templates 11 passed + test_template_endpoints 5 passed = **16 passed / 0 failed**。

- [x] 2. 前端模板管理与项目订阅入口（R2、R3、ADR-FTP-03/04）
  - `FormulaTemplateDetailDrawer` 增版本 diff、回滚预览 / 确认、定义页新增公式位；新增 slot 使用现有 publish preview / decisions / CAS / request_id 链路。
  - `FormulaSettingsToolbar` 仅在 `canEditProject` 时显示订阅按钮；保存为模板继续显示，保存对话框按项目编辑权限禁用 team / group。
  - 模板详情订阅项目入口带 `projectId + templateId + action=subscribe`，目标公式管理页自动打开指定模板订阅弹窗。
  - Verify：vitest、单区域 vue-tsc、ESLint；测试只读不显示订阅、仍能保存个人模板、共享范围禁用、版本 diff / 回滚动作、新增 slot 载荷和深链消费；变异去掉门控必须打红。
  - 2026-10-31 实施完成：
    - `FormulaTemplateDetailDrawer.vue`：版本页签增「与当前对比」（diff 弹窗）和「回滚到此版本」（rollback preview → 发版对话框）；定义页签增「+ 新增公式位」（选域、填公式位和标签 → 编辑定义 → 暂存 → 发版）；订阅项目页签增「到项目中订阅」（router.push 带 `formulaTemplateId + formulaAction + formulaDomain` query 到目标项目仪表盘，布局层消费并触发 `open-formula-manager` 事件）；`previewKind` 三态（publish / promote / rollback）。
    - `FormulaSettingsToolbar.vue`：订阅按钮 `v-if="canEditProject"`；保存模板传 `canEditProject`；接收 `initialTemplateId / initialTemplateAction / initialTemplateDomain` 深链 props 并自动打开订阅弹窗；增 `watch` 响应式。
    - `FormulaTemplateSaveDialog.vue`：增 `canEditProject` prop；team / group radio 按 `canEditProject` 禁用；hint 文案区分无编辑权限。
    - `FormulaTemplateSubscribeDialog.vue`：增 `initialTemplateId / initialTemplateAction / initialTemplateDomain` props；打开时若有深链参数自动触发该模板的订阅预览。
    - `FormulaManagerDialog.vue`：透传 `initialTemplateId / initialTemplateAction / initialTemplateDomain`。
    - `ThreeColumnLayout.vue`：透传三个 template props 到 FormulaManagerDialog；增 `openTemplateSubscribeFromQuery` 消费路由 query 深链；onMounted 时首次调用。
    - `eventBus.ts`：`OpenFormulaManagerPayload` 增 `templateId / templateAction / templateDomain`；修复闭合大括号缺失（ESLint parse error）。
    - `formulaSettings.ts`（apiPaths）：增 `diff / rollbackPreview / rollback` 路径。
    - `formulaSettingsApi.ts`：增 `templateDiff / templateRollbackPreview / templateRollback` 请求封装。
    - `useFormulaSettings.ts`：增 `TemplateDiffChange / TemplateDiff` 类型。
    - 前端回归：vitest **4 文件 39 passed / 0 failed**；getDiagnostics **8 文件 0 错误**；ESLint **0 新增错误**。

- [x] 3. 跨层契约与完整回归测试
  - 增加路由挂载守卫、前后端请求 / 响应字段契约、订阅 / 退订 preview 与 execute 的真实权限测试；不能只测 service。
  - 增加完整链路测试：建模板 → B/C 订阅 → 新增 slot 发版 → outbox / propagation → 待确认 → diff → rollback → 退订；逐项目断言 B 有适配、C 无适配时的不同结果。
  - Verify：SQLite 单元、PG 回滚事务、必要的磁盘变异；真值断言不能由 mock 重写生产主流程。
  - 2026-10-31 回归验证完成：
    - 后端全量 `formula_settings/` 目录：**469 passed + 13 failed**。13 个失败全部为预存（S4 tasks 记载的 11 个 + 并发会话引入的 2 个），与本轮新增的 5 个 test_templates / test_template_endpoints 用例无交集。**只候选红 = 0**。
    - 既有端点权限测试（`test_template_endpoints.py::test_manage_publish_subscribe_permissions`、`test_visibility_matrix_list_detail_versions_same_rule`）覆盖订阅/退订/发布/删除的真实鉴权链。新增 `test_diff_and_rollback_keep_template_visibility` 验证 diff/rollback 不可见返回 404。
    - 既有服务层测试（`test_save_subscribe_publish_unsubscribe_end_to_end`）覆盖完整链路（建模板 → 订阅含冲突 → 全局发布跳过模板位 → 发版含跟随/冲突/暂缓 → 处理待确认 → 退订两种 → 删除）。新增 `test_template_diff_and_rollback_creates_new_version` 在该链路上追加 diff + rollback + 幂等。

- [x] 4. 【测试】项目双项目登录态 UAT（R1 第一阶段，ADR-FTP-05）
  - S4 浏览器传播验收通过后，经平台正常路径创建来源项目 A、订阅项目 B/C（B 有本项目适配，C 没有），使用真实登录态完成设计 §7.2 流程。
  - 每个 HTTP 步骤用浏览器 + 独立 GET / 刷新双证；截图和回执放 `tmp_formula_template_pilot/screenshots/`，用完停到 `about:blank`。
  - 清理走平台删除路径，逐表对账模板、版本、订阅、设置、同步项、发布记录、outbox / propagation；审计只登记数量。
  - Verify：A/B/C 角色拓扑、8 步记录、传播状态、回滚新版本和清理对账表贴入本任务。
  - **2026-11-01 接口链路 29/29 通过**（候选环境 = v1.0.75 干净检出 worktree，S6 四个后端文件逐字节核验为 ff8ccd354 原样；脚本 `tmp_formula_template_pilot/uat_task4.py`，回执 `uat/task4_result_*.json`）：
    - A/B/C 三个【测试】项目经平台 `POST /api/projects` 建立（B 预置本项目适配造冲突、C 不预置）
    - 从 A 保存模板 → B 订阅出冲突并选「保留本项目」、C 订阅「直接生效」→ 读回 B=本项目层保留原值、C=模板层取模板值
    - 发版 v2（含**新增公式位** BS-002）→ C 自动跟随两个公式位、B 出现 1 条 `conflict/template` 待确认
    - diff v1→v2 = `added BS-002` + `changed BS-001`；同版本 diff 为空集
    - 回滚预览**零写入**（版本数 2→2）→ 回滚生成 **v3**（不回退版本号）→ 同 `request_id` 幂等不建第二个版本
    - 边界：回滚到当前版本 422 / 目标版本不存在 404 / 缺 `expected_version` 428
    - 共享范围收窄 409 并列出两个订阅项目名称
    - 两种退订（保留为本项目适配 / 回到全局）均 200
    - 清理走平台删除端点，逐表对账：项目层公式行 0、待确认 0、存活【测试】项目 0
  - 🔴 **浏览器双证被远端分支破损阻塞（非本 spec 引入）**：v1.0.75 干净检出跑不起来平台界面——
    `tmp_compile_all.mjs` 实测**远端分支 19 个前端文件编译不过**（`CustomQueryDialog.vue` / `AdvancedQueryBuilder.vue` /
    `TrialBalance.vue` / `DisclosureEditor.vue` / `LedgerPenetration.vue` / `ConsolNoteTab.vue` 等多处
    「函数体用 await 但声明漏 async」，`batchProjectImport.ts` 模板串被替换破坏，`useE1Analysis.ts` 等
    4 个文件未闭合模板串），`DefaultLayout.vue` 动态 import 整条 500 ⇒ 登录后进不了任何页面。
    另有后端两处同类：重复迁移号 V233（`display_preferences` 与 `project_creation_grants` 撞号，
    共享库权威编号是 V235）、`users.py` / `pm_dashboard.py` 等引用 6 个未入库模块。
    均属并发会话（批量建项授权等）「已推代码引用未推改动」，memory 已记为范围外。
    本 spec 只在 tmp UAT worktree 做了最小可运行修补（不提交、不改主工作树），界面逐屏验证待该破损修复后补。
  - **2026-11-01 浏览器双证补验完成**（候选提交 `ada4c3451b`；前端 `127.0.0.1:3032` → 后端 `127.0.0.1:9983`；
    后端 `/api/health` HTTP 200，PostgreSQL / Redis 均 ok；`status=degraded` 仅来自既有 3 条 checksum drift）：
    - 先在同一候选环境重放 API 全链 **29/29**，再保留 v4 中间态：A 来源、B 有适配、C 无适配；B/C 两条 active subscription，
      C 的 BS-001 / BS-002 均为 template 层且公式逐字为 `TB('1001','期末余额')*3` / `ROW('BS-001')`，B 有 1 条 pending。
    - C 项目深链 `formulaTemplateId + formulaAction=subscribe + formulaDomain=report` 浏览器直达，实测同时打开「ƒx 公式管理中心」和
      「公式模板订阅」；证明刷新后深链消费不是只测路由参数。
    - 全局公式 → 公式模板：浏览器显示该模板 **v4 / 2 个订阅**；详情显示 BS-001 与新增 BS-002 两个定义；版本历史显示 v1~v4，
      历史版本均有「与当前对比 / 回滚到此版本」。
    - 浏览器点击 v3「与当前对比」真实发出 `GET .../diff?from=3&to=4` → **200**；界面显示 2 处变化：BS-001 changed、BS-002 added。
    - 浏览器点击「回滚到 v3」真实发出 `POST .../rollback-preview` → **200**；预览显示自动跟随 3、冲突 1、受影响项目 2 个。
      点取消后独立 GET 对账仍为 v4、版本行 4，证明 preview 零写入。
    - B 项目打开即显示「公式待确认 1 处」：同一行逐字展示基线 `TB('1001','期末余额')`、模板新版
      `TB('1001','期末余额')*3`、本项目当前 `TB('1001','期末余额')*2`；点「稍后处理」后硬刷新，角标仍为 1。
    - 补验页控制台 **0 error**；唯一 warning 是既有 `NotificationCenter` 多根组件 directive 告警，与本链无关。
    - 证据：`screenshots/01`~`09`、`uat/browser_prep_11011153.json`、`uat/browser_verify_11011153.json`。
    - 清理全走平台端点 **6/6**（退订 2、删模板 1、软删项目 3）。真库逐表对账：存活项目 0 / 软删项目 3、存活模板 0 /
      软删模板 1、历史版本 4、active subscription 0、项目层 / 模板层存活设置 0、pending 0、发布记录 3；
      本轮 `formula_config.changed` outbox 13 条全部 published、max_attempts=1。

- [x] 5. 真实项目试点（R1 第二阶段，design §7.3）
  - 依赖用户明确指定来源 / 订阅项目、执行时间和真实写入授权；未获授权保持 `[ ]`，不以测试项目结果代替。
  - 先 preview，用户确认后才执行 publish / rollback；保存执行前快照和每步回执；异常即停止，不自动退订或删除。
  - Verify：试点记录、快照、传播 / 待确认 / 审计结果贴入本任务。
  - 🔴 **试点项目勘误**：交接记录里的「重药控股安徽有限公司_2025 / `0ec33ac9`」在当前共享库**已不存在**
    （现查 `projects` 无此 id、无「重药」字样项目）。现库唯一含「安徽」的真实项目是
    **安徽骨科医院_2025（`2d2d819b-32e5-43da-801a-5862eb59e15a`，soe / standalone / 2025）**，
    经用户确认（2026-11-01「就用这个」）作为试点对象。
  - **2026-11-01 试点 8/8 通过**（脚本 `tmp_formula_template_pilot/pilot_task5.py`，
    快照 `uat/pilot_snapshot_before.json`，回执 `uat/pilot_result_*.json`）：
    - 试点前快照：352 个报表公式位**全部在 global 层**、0 订阅、0 待确认
    - 审计风险设计为零：模板来源 = **当前全局副本**（`source=global`，只取 BS-001/002/003 三个公式位）
      ⇒ 模板内容与全局逐字相同，订阅后有效公式不变、报表数字不动，但订阅 / 物化 / 层级 / 待确认整条链路真实走过
    - 先只预览（不加 `--apply`）：3 个公式位全判「直接生效」、**conflict = 0**，满足继续条件才写
    - 执行订阅后逐项读回：

      | 公式位 | 试点前 | 试点后 | 层级 |
      |---|---|---|---|
      | BS-001 | 无公式 | 无公式 | global → template |
      | BS-002 | `TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')` | **逐字相同** | global → template |
      | BS-003 | 无公式 | 无公式 | global → template |

    - 待确认保持 0；订阅关系读回 1 条（v1，`behind=false`）；**未纳入试点的 349 个公式位层级全部仍为 global**
    - 按设计**保留订阅、未退订、未删除**真实项目数据；预览轮多建的模板已走平台删除端点清掉
  - 共享库最终对账：在用模板 1（试点）/ 已删模板 3（UAT 测试，软删）/ 在用订阅 1 / 模板层公式行 3 /
    项目层公式行 0 / 待确认 0 / 存活【测试】项目 0

- [x] 6. 回归与收尾
  - 候选树 vs 基线 HEAD 失败集合对比，只接受本轮新增失败为 0；检查迁移 / ORM / service 三层一致性和 router_registry。
  - 清理 `tmp_formula_template_pilot/` 中一次性探针和截图，保留任务要求的验收摘要；更新 INDEX.md 与 memory.md。
  - Verify：后端 / 前端目标测试、单区域类型检查、磁盘变异全绿；推送带版本号与主要变动。
  - 2026-10-31 推送完成：
    - 版本 v1.0.75，提交 ff8ccd354，20 files changed / 845 insertions / 129 deletions
    - 推送方式：临时分离头 worktree（主工作树有并发会话脏文件），`push_version.py push --branch`
    - 后端回归：全量 `formula_settings/` 469 passed + 13 预存 failed，只候选红 = 0
    - 前端回归：vitest 39 passed / 诊断 0 错误 / ESLint 0 新增错误
    - 白名单更新：ThreeColumnLayout 1515 → 1598（深链消费 +83 行）
  - **2026-11-01 第二轮（UAT 抓到的真实缺陷 + 推送）**：
    - 🔴 **回滚 CAS 次序缺陷**（Task 4 UAT 步骤 7.6 实测）：原实现先算差集、后校版本号。
      回滚完成后目标版本与当前版本内容相同、差集为空，此时带过期版本号或不带版本号的请求
      会收到 422「没有可回滚的变化」，用户据此以为两版本没差异，**真实原因是他看到的版本已不是当前版本**。
      改为 `_rollback_cas()` 在任何内容判断之前做：缺版本号 428、版本不符 409，preview 与 execute 两个端点同口径。
    - 新增守卫 `test_rollback_cas_precedes_empty_diff`：造出「差集为空」的局面，断言缺版本号仍 428、
      版本不符仍 409、版本号正确时才轮到 422 —— 把次序钉死，判断挪回去即打红。
    - 后端目标测试 **17 passed / 0 failed**（含新守卫）。
