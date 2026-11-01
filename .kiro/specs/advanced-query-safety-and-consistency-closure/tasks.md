# 实施任务：高级查询安全与一致性收口

> 证据口径：计数一律现算并写明命令；故障注入逐条记形态 + 恢复 sha256 核对；
> 浏览器实测在**候选栈**（前端 3040 → 候选后端 9981）上做，不走共享 3030 / 9980。

- [x] 1. 基线与退役边界
  - 核对三个写端点无前端生产调用方、底层 writer 仍被既有契约引用。
  - 建立后端/前端回归基线，记录与本批无关的预存失败。
  - 三个写端点改无依赖 410，路由表和权限配方表同步更新。
  - **证据**：`POST /api/custom-query/cell-writeback`、`/writeback-preview`、`/writeback-confirm`
    在候选栈浏览器内实测均返回 `410`，响应体 `error_code=ADVANCED_QUERY_WRITEBACK_RETIRED`；
    匿名、空请求体同样 410（证明桩无认证 / 请求体 / 数据库依赖）。
  - **证据**：`SnapshotWriter` / 预览服务未删除（被 workpaper-sync 契约与写入方清册引用），
    仅端点退役；`router_registry/system.py` §7.1 注释改为退役桩说明。
  - **证据**：鉴权矩阵随之收缩 —— 基线 `test_aql_endpoint_authz::test_endpoint_authz_cell`
    的 18 / 19 / 20 号格（3 端点 × 8 身份 = 24 个参数化节点）在候选树不再存在，属预期。

- [x] 2. 项目存活与缓存权限隔离
  - OwnershipGuard 的集合、单项目和跨项目过滤统一排除软删项目。
  - 业务缓存身份加入当前用户循环范围摘要。
  - 端点级测试证明软删项目不触达领域取数。
  - **证据**：`_project_is_live` 为 admin / partner 的 `None` 哨兵补上存活门；
    成员（`project_users`）与分派（`project_assignments` → `staff_members`）两条
    集合查询各 JOIN `projects` 并排除 `is_deleted`；`filter_accessible_rows` /
    `assert_all_targets` 全角色统一过滤。
  - **证据**：真 PG 用例 `test_aqs_safety_closure::test_real_postgres_deleted_project_is_forbidden_to_admin`
    通过；全项目 scope 签名改 `all:{活项目摘要}`（`builder_scope.live_project_signature`），
    软删后 30s 查询缓存与 600s COUNT 凭证不再被复用。

- [x] 3. 语义与超时 fail-closed
  - 分组、透视缺模块或运行异常返回明确错误，不返回原始明细。
  - PostgreSQL 查询保护设置失败返回 503；SQLite 保持可测试降级。
  - 覆盖取消、408 和事务回滚回归。
  - **证据**：`query_orchestrator._transform_error(step)` → 500 `QUERY_TRANSFORM_FAILED`
    （分组 / 透视各两处：ImportError 与运行异常）；`execution_guard` 按
    `db.get_bind().dialect.name` 判定，方言未知或 PG 上 `SET LOCAL` 失败一律
    503 `QUERY_GUARD_UNAVAILABLE`（失败前先 rollback，避免留下 aborted 事务），
    仅明确识别为非 PG 方言才跳过。
  - **证据**：真 PG 用例 `test_aqs_safety_closure::test_real_postgres_statement_timeout_is_enabled` 通过。

- [x] 4. 构建器 DSL 与输出安全
  - 限制字段、条件、排序、JOIN、聚合、分组和 offset。
  - JOIN/聚合使用严格模型；输出别名唯一；普通字段与 GROUP BY 一致。
  - 分组分页补稳定排序；数据库错误响应脱敏并带追踪号。
  - **证据**：`builder_dsl` 上限 `MAX_FIELDS=60 / FILTERS=20 / ORDER_BY=5 / JOINS=3 /
    AGGREGATES=10 / GROUP_BY=5 / OFFSET=100_000`；`JoinSpec` / `AggregateSpec` /
    `FilterCond` / `OrderBy` 继承 `StrictRequestModel`（额外字段即拒）。
  - **证据（浏览器实测）**：`POST /api/query/execute` 带 `offset=200000` → `422`
    「Input should be less than or equal to 100000」；带 9 条 `order_by` → `422`
    「List should have at most 5 items after validation, not 9」。
  - **证据**：构建器与导出的数据库错误改为固定文案 + 32 位 `correlation_id`，
    不再把 SQL / 驱动信息带到响应。

- [x] 5. 构建器审计
  - 成功查询按 60 秒窗口记录用户、表、作用域、条件摘要和行数。
  - 跨项目查询明确写入审计 details；审计失败不改变只读结果。
  - **证据**：`query_builder._audit_query_success(..., db)` 写
    `custom_query.builder_execute`，用 `asyncio.wait_for(..., SUCCESS_AUDIT_TIMEOUT_S=1.0)`
    限时并吞异常；COUNT 凭证主体改 `f"{subject_of(user)}:{scope_signature(scope)}"`，
    跨项目与单项目不互相复用。

- [x] 6. 前端项目上下文与结果时效
  - ACNR picker 显式使用宿主项目。
  - 三个入口引入请求代际，旧响应不得覆盖新状态。
  - 项目、年度、数据源、表或范围变化立即清除旧结果及操作状态。
  - **证据（浏览器实测）**：弹窗内年度 2025 → 2026，结果表与分页**立即清空**并回到
    「选择项目和数据源后点击『▶ 查询』」提示，且**没有**自动重查（拦截 XHR 计数为 0）。
  - **证据（浏览器实测·竞态）**：Slow 3G 下点「▶ 查询」后立刻切项目
    （和平药房_2025 → 陕西华氏_2025），25 秒后迟到响应**未**覆盖新上下文，结果区保持空态。
  - **证据（浏览器实测·构建器）**：选 `trial_balance` 执行得 200 / total=105；
    切「跨项目」开关后结果区立即回到「尚未执行查询」，无新请求。
  - **证据**：`CustomQueryFieldPicker` 的 `projectId` 为显式入参，空值即「无项目」，
    不再 `useCurrentProjectId()` 回退；宿主切项目时清缓存、清已选、重载树。
  - 🔴 **本任务的守卫在首轮故障注入中被证明不足**（见任务 8 的 M7）：原用例只断言
    「无项目时取到空字符串」，而测试环境里真实回退本来也取不到值 ⇒ 注入回退后仍全绿。
    已在 `CustomQueryFieldPicker.spec.ts` 加三条「诱饵」mock
    （`useCurrentProjectId` / `vue-router` / `stores/project` 一律返回非空项目）
    并新增「不传 projectId 也不借用路由/store」用例，注入后即打红。

- [x] 7. 弹窗分页与轻量指标树
  - 弹窗保存并复用 `count_token`，查询定义变化时清空。
  - 指标树改骨架/按需加载，保留底稿选区能力。
  - 无项目模式不得调用必须带项目的执行链。
  - **证据（浏览器实测·骨架）**：弹窗首开只发 `GET /api/custom-query/indicators?branch=workpaper`
    （展开「📋 底稿」时按需发）与 `?project_id=…&depth=1`（选项目后）——全部是
    `depth=1` 骨架，不再拉全量树；底稿分支按需加载后仍可见「底稿清单」与 A~S 循环分组，
    底稿选区能力保留。
  - **证据（浏览器实测·COUNT 复用）**：第 1 页 324 条；第 2 页请求体带
    `count_token`（`offset=100`）；第 3 页（`offset=200`）响应 `count_reused=true`、
    `total` 恒为 324。
  - **证据（浏览器实测·失效）**：年度改回 2025 后重新查询，首个请求
    **不带** `count_token`、`offset=0` —— 陈旧凭证已随上下文变化清空。
  - **证据**：无项目时项目下拉为空、「▶ 查询」禁用；骨架请求不带 `project_id`，
    不进入必须带项目的执行链。

- [x] 8. 验收与收尾
  - 后端、前端、真 PG 测试和故障注入通过。
  - 在候选栈完成业务视图与构建器浏览器实测。
  - 更新本文件证据与 INDEX；清理临时产物。

  **8.1 后端（SQLite 口径）**：`tests/advanced_query_linkage/` + 4 个相关文件
  `-m "not pg_only"` → **505 passed / 288 deselected / 0 failed**（`final_be3.log`）。
  其中基线曾红的 2 例（`test_aql_builder_sql_shape::test_total_is_rows_or_groups_and_one_for_ungrouped_aggregates`、
  `::test_staff_members_rejection_is_audited_as_pii_denied`）在补齐他会话未入库模块后转绿，
  证明与本批无关。

  **8.2 前端**：本批 7 个用例文件 → **94 passed**；强化后的
  `CustomQueryFieldPicker.spec.ts` → **9 passed**。

  **8.3 故障注入（8 条缺陷 + 2 条阴性对照，`mutate_aqs.py` / `mutation_results.json`）**
  —— 全部逐条磁盘注入、跑定向用例、随后逐字节恢复并核对 sha256（10/10 恢复一致）：

  | 编号 | 注入形态 | 结果 |
  |---|---|---|
  | M1 | 退役桩 410 → 200 | 注入即打红 |
  | M2 | 删 `_project_is_live` 的 `Project.is_deleted == False` | 注入即打红 |
  | M3 | 分组失败 `raise _transform_error` → 退回原始明细 | 注入即打红 |
  | M4 | PG `SET LOCAL` 失败只记日志、不抛 503 | 注入即打红 |
  | M5 | `MAX_OFFSET` 100_000 → 10_000_000_000 | 注入即打红 |
  | M6 | 弹窗删请求代际守卫（2 处） | 注入即打红 |
  | M7 | 选字段回退路由/store 项目 | 注入即打红（守卫强化后，见任务 6） |
  | M8 | 构建器删请求代际守卫（2 处） | 注入即打红 |
  | N1 | 阴性对照：只改后端日志文案 | 保持绿 |
  | N2 | 阴性对照：只加前端注释 | 保持绿 |

  **8.4 真 PG（`-m pg_only`，按节点 id 逐条对账，不按数量比）**
  - 本批自己的 pg_only 用例全绿：`test_aqs_safety_closure` 的
    `test_real_postgres_deleted_project_is_forbidden_to_admin`、
    `test_real_postgres_statement_timeout_is_enabled`，以及 4 条退役端点用例
    （`test_cell_writeback_endpoint_is_retired_and_trial_balance_rows_unchanged`、
    `test_preview_endpoint_is_retired_without_touching_targets`、
    `test_confirm_endpoint_is_retired_without_writing`、
    `test_retired_confirm_ignores_large_or_invalid_payload`）。
  - 候选 288 收集 / 113 失败，基线（干净 HEAD worktree `base_wt`）313 收集 / 94 失败；
    **共同失败 88 条**，仅候选失败 25 条，仅基线失败 6 条，节点集合差 31 / 6。
  - 🔴 **25 条「仅候选失败」已逐条归因为环境数据缺失，不是本批回归**：
    全部是 `403 FORBIDDEN_PROJECT`。真库现查（`projects` 左连接）证明
    `gold.py` 里 9 个金标准项目 **HS / HP / YB / LN / MD / WL / UA / UB / UP 全部不存在**
    （共享库项目已重建、UUID 全换）。基线下 admin 可以查**不存在的项目**并拿到
    200 / 400，这正是本批存活门要堵的洞；堵上后这些用例改报 403。
    单例对照：`test_aql_adjustment_source_pg::test_rje_without_rows_is_empty_not_error`
    基线 2 passed、候选 2 failed（403），而该用例的前置断言
    「华氏有审计调整分录」在两侧都已失败 ⇒ 原先那两条「通过」是**对着不存在的项目空跑**。
  - 节点集合差已逐条点清：**基线独有 31 = `test_aql_endpoint_authz` 24**
    （退役的 3 个端点 × 8 身份，基线全 passed）**+ `test_aql_writeback_isolation_pg` 7**
    （其中 6 条即「仅基线失败」，1 条 `test_tb_module_is_rejected_*` 基线 passed）；
    **候选独有 6 = 4 条退役端点用例 + 2 条本批 PG 用例，全部 passed**。
    即差异全部由端点退役与其用例替换解释，无悬空节点。
  - **范围外工单（已登记，未改他人用例）**：`tests/advanced_query_linkage` 的 9 个金标准
    项目在共享库已全部不存在 ⇒ 该目录 pg_only 口径用例整体 data-blocked（88 条共同失败）。
    需要重新指认金标准项目或改为用例自建数据；本批不动他 spec 的夹具。

  **8.5 静态检查**：ESLint（改动前端文件）、Ruff（改动后端文件）、
  `vue-tsc --noEmit -p tsconfig._aql-linkage.json`、`check_file_size.py` 全通过。

  **8.6 语义审查**：semantic_reviewer 两轮 —— 第 1 轮 NEEDS_CHANGES（HIGH 2 / MEDIUM 6），
  逐条修复后第 2 轮 APPROVED（0 blocker / high / medium）。报告：
  `semantic-review/2026-11-01-111010-pr-local.md`、`semantic-review/2026-11-01-112906-pr-local.md`。

  **8.7 浏览器实测环境**：候选栈 = 候选 worktree 前端 `127.0.0.1:3040`
  （`.env.local` 把代理目标钉死到 9981）+ 候选后端 `127.0.0.1:9981`
  （`GT_BOOTSTRAP_DONE=1`，不跑迁移、不碰共享栈）。全程 console error **0**。

  **8.8 起栈期间发现的 HEAD 级预存缺陷（非本批引入，已逐条归因）**
  - 🔴 **P0 全平台不可用**：`useAiNoteCapture.ts` 缺 `NOTE_NAME_MAX_LENGTH` /
    `NoteSaveTarget` / `NoteSaveRequest` 三个导出，而 `ChatNoteSaveDialog.vue`
    与 `PlatformAiChatPanel.vue`（静态导入、在已登录初始图里）都依赖它 ⇒
    **登录后路由启动即 SyntaxError，页面空白**。在共享 3030 上同样复现（登录后停在
    /login、console 三条 SyntaxError）。根因是 `stash-1021-lost-changes-recovery`
    的三方合并漏了这一个文件；救援标签
    `rescue/2026-10-21-1756-temp-for-push-reconcile` 里有权威版本。
    **本批已修**：以 `git merge-file --diff3`（ours=HEAD / base=救援 stash 第一父 /
    theirs=救援 stash）三方合并，**0 冲突**，保留 `6f4c5a54a` 的 `copyText` 改动；
    修后候选 SPA 正常启动，`ChatAdoptNoteTarget.spec.ts` + `PhaseBGateGuards.spec.ts`
    **29 passed**（此前 HEAD 红）。
  - 🔴 **17 个前端文件语法/编译错误**（`6f4c5a54a` 机械替换 `crypto.randomUUID` 与
    clipboard 留下的残缺模板字符串、非 async 函数里的 `await`）：用 esbuild 全量解析
    8593 个 `.ts`/`.vue` 得 18 条，排除 1 条探针假阳
    （`MyTemplatesDialog.vue` 的 HTML 注释里写了 `` `<script setup>` ``）后为 17 条。
    主工作区工作副本已由他会话修好（未提交）⇒ **本批不代改**，只在候选树临时拷入以起栈。
  - 🔴 **后端 HEAD 无法导入**：`pm_dashboard.py` 从 `app.services.pm_service` 导入
    已不存在的 `BatchReviewService`（真实位置 `app/services/batch_review_service.py`，
    且构造签名不同）；另有 18 个后端 + 24 个前端模块被已提交代码引用却仍未跟踪。
    ⇒ 干净检出 / CI `pytest -x` 起不来。**本批不代改**，候选树仅临时修补以起栈。
