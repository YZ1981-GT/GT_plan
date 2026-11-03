# 设计：批量建项授权与拓扑锁加固

## 1. 现状实证与边界

现读确认：`projects.client_name/company_code` 只是项目快照；`companies` 也带 `project_id`，不是客户主数据；仓库没有 client/company grant、邀请或待分配项目表。`project_users` 只能表达项目创建后的权限。单项目 `POST /api/projects` 当前只要求登录，是批量修复之外的直接旁路。partner 在项目列表中可见全量项目，但无用户管理权。

因此新增最小授权维度，而不把客户主数据、CRM 或审批流一并引入。partner 延续全局创建；manager 精确授权；admin 管理授权。Assignments 路由的既有项目成员管理欠账不作为本 spec 的授权真源，也不以“已有项目 edit 自动推导”替代授权。

## 2. 数据模型

实施时重新扫描迁移号，新增 `ProjectCreationGrant` 独立 ORM 和 V/R 配对迁移：

- `id UUID`；`grantee_user_id`、`granted_by`、`revoked_by` 外键 users。
- `company_code VARCHAR(18)`；`valid_from`、`valid_until`、`revoked_at`。
- `reason/source`、`version >= 1`、`is_deleted/deleted_at`、时间戳。
- 活动唯一索引 `(grantee_user_id, company_code) WHERE is_deleted=false`；grantee/code、到期扫描索引。
- CHECK 只封闭字符集、长度、有效期和版本；USCC checksum 仍由统一 `validate_uscc` 判。

迁移幂等回填：从 active manager 用户、active edit `project_users` 和未删除项目中取合法 company_code；`source='existing_project_edit_backfill'`，`granted_by=NULL`。不从 `manager_id`、客户名称或 partner 全量可见性推导。

## 3. 授权服务与计划基线

`project_creation_grant_service.py` 提供：

- `required_creation_codes(rows)`：create 行的 company/parent/ultimate 去重；update/skip 不纳入。
- `authorize_creation_codes(db, actor, codes, lock=False)`：admin/partner role bypass；manager 一次查询全部 active、有效、精确授权；其他角色拒绝。授权不足在查询 projects 前抛 `COMPANY_CREATION_NOT_AUTHORIZED`。
- `grant_snapshots`：`{id, company_code, version, valid_until}`，写入计划私有 `_plan_dependencies.creation_grants`。
- `revalidate_plan_grants`：apply 在库存读取前按 grant id 排序 `FOR SHARE`，逐值比较；漂移转 `BATCH_PLAN_STALE`。
- `grant_many/list/revoke`：只 flush，由 users router 统一 commit；幂等授予恢复被撤销行时 version+1。

单项目路由改用 admin/partner/manager 角色门并在唯一性查询前授权。manager 请求中的 manager/signing partner 字段由服务端归一为本人/空；项目创建、manager assignment 和 `ProjectUser(edit)` 同事务提交。

## 4. 限流与审计

`project_creation_security.py` 在授权和库存查询前执行 actor 级 Redis 固定窗口：30 次/60秒，可由设置覆盖。使用 Lua 或 `INCR + 首次 EXPIRE` 原子计数；超限 429 `PROJECT_CREATION_RATE_LIMITED` + Retry-After。Redis 不可用只跳过限流，不跳过授权。

授权授予/撤销和拒绝复用 `audit_logger_enhanced.audit_logger`。拒绝详情只含 `sha256(sorted(codes))`、count、entrypoint、role；不写原始代码。审计失败不改变主授权判断。

## 5. 状态锁与拓扑锁

`get_readable_plan_bounded` 只供 status 路由：PG 保存点内 `set_config('lock_timeout','1500ms',true)` 后执行原 `FOR UPDATE`；SQLSTATE 55P03 回滚保存点并抛 typed busy。成功同样回滚保存点会释放行锁，因此不可这样做；实现应在保存点成功后 release，失败 rollback，外层请求结束释放锁。SQLite 走原路径。

`group_topology_lock.py` 提供 `lock_topology_years(db, years)`：PG 按升序调用 `pg_advisory_xact_lock(namespace, year)`；SQLite no-op。年度是当前唯一安全锁域，因为 parent/ultimate 可把两个旧集团合成一个集团，且派生链接按全年度重算。

近期接线先覆盖所有调用 `sync_group_links` / `sync_group_links_for` 或直接改三码的生产服务，并用 AST 清单守卫防新增旁路。锁必须在锁前快照失效处前移；不能只在 `sync_group_links` 内补锁。若现有调用方已持项目行，需调整调用顺序为“年度拓扑锁 → 项目行 → 读取/校验 → 写入 → sync”。

20 组基准用独立 PG engine + NullPool、21 连接、barrier 和 100ms 临界区，对比当前项目行锁、年度 advisory、不同年度 advisory。门只断言 coarse 峰值=1、不同年度峰值>1和 watchdog，不把毫秒阈值写进 CI。

## 6. 前端

`UserManagement.vue` 下方增加授权卡片，数据 API 独立为 `projectCreationGrantApi.ts`，路径登记在 `apiPaths/system.ts`。只显示 active manager；授权弹窗校验 18 位精确代码、可选有效期和必填原因；撤销使用危险操作确认。页面仍是 admin-only，不向 partner 开放用户管理。

正式 synthetic harness 直接挂真实 `BatchImportDialog`，context route 只放行 Vite 静态 GET/HEAD，全部 API 显式 fulfill/abort，WebSocket 关闭。专用 `playwright.batch-project.config.ts` 不引用 globalSetup。真实模板 200 已由 opt-in UAT 保留；日常 synthetic 下载用内存 ZIP 证明下载链，不触达认证或数据库。

## 7. 验证与停止条件

- 后端：grant service/route、单项和批量门、撤销 stale、自动根、限流、审计、status busy、拓扑锁、迁移与回填。
- 前端：授权管理、错误码、现有 BatchImportDialog Vitest；专用 Playwright 全绿且 Long Task 自检能打红。
- 真 PG：锁与迁移只用唯一【测试】记录，finally 精确清理；共享库应用迁移前再次确认版本号。
- 量测若证明年度串行明显，但当前无稳定 group identity，则只记录数据，不擅自改成不安全的 group 锁。
- 全部相关文件过 ruff/ESLint/scoped vue-tsc、文件行数门、`git diff --check`，语义复核无 P0/P1 后停止。

## 8. 实施偏差与复盘裁定（2026-10-31）

第一轮语义复核（`semantic-review/2026-10-31-020825-pr-local.md`）给出 15 项，全部按下表处理；第二轮独立复核因子代理访问被拒未能执行，改为逐函数自审。

| 复核项 | 处理 |
|---|---|
| 库存补齐的 parent/ultimate 未授权 | batch：补齐后按最终代码再授权，新代码先授权再扩大库存查询（循环到不再新增），计划保存最终快照；单建：年度锁后重验显式代码，`prepare_group_fields` 后按最终代码再授权 |
| 锁后仍读到旧角色 | `_locked_actor_role` 改为锁定标量列（ORM 对象会命中 Session identity map）；真 PG 双连接降级用例 |
| 年度锁等待前就判定有效期 | apply / legacy 改为年度锁 → actor/grant 重验 → 成员锁 + 权限 → 库存 FOR UPDATE → 模板根；真 PG「等待中到期」用例 |
| 单建 / legacy / 连续审计未锁成员行 | 统一 `lock_actor_and_project_memberships`，只有 admin 跳过（partner 的项目权限同样依赖成员行）；AST 守卫钉住「权限检查在成员锁之后」 |
| 连续审计 | 锁旧 / 新年度、刷新并比对来源身份、grant 重验、来源只读权限、创建者成员初始化 |
| 删除 / attach 身份漂移 | 锁后年度 CAS；attach 抽成服务，父 / 子身份 CAS + 成员锁 |
| restore 与永久删除 | 共用年度锁并锁后复查；独立连接删除前再确认 `is_deleted`，`DELETE` 带 `is_deleted = true`；恢复遇已物理删除返回 409 |
| attach 可成环 | 写入后、提交前对最终图做无环校验，成环 409 且三码不落库 |
| 重授语义与 SQLite 唯一索引 | 撤销后重授新建一行（新 id、version 1），撤销行保留作审计；计划按 id + version 比对，重授后的旧计划仍判 stale。ORM 部分唯一索引补 `sqlite_where`。原设计「恢复撤销行 version+1」未采用 |
| V227 接受校验码错误的代码 | V227 已落共享库，不改原文件；新增 V228/R228（同算法函数、撤销不可用授权、未撤销行 CHECK）。约束依赖 PG 函数，不在 ORM 声明 |
| PG 并发用例必红 | 补 `creation_grants` 基线；同时起跑，断言一方成功、一方 `BATCH_PLAN_STALE` |
| 首次打开遇 busy 不重试 | 首次恢复与 apply 后恢复共用有限重试 |
| synthetic 不是门禁、下载可假绿 | 改真实 download 事件并比对字节；`npm run test:e2e:batch-project`；默认配置 `testIgnore` 该用例。**CI 未接入**：本地无法验证 GitHub Actions 能绿，不加可能永红的门禁，建议单独接入 |
| 授权 UI 状态 | 加载失败态与重新加载、账号变更后刷新、撤销失败刷新、授予二次确认；后端列表对停用 / 改角色经理返回 `suspended` |
| 三码守卫只看 sync 调用方 | 扩为写入面冻结 + 分类 + 写前持锁 + 调用方持锁助手 + 永久删除顺序，配内存变异与阴性对照 |

其他裁定：

- 连续审计路由由「仅登录」收紧为 admin/partner/manager + 来源项目只读权限。上年项目通常已归档，编辑级门禁会返回 423，所以来源只要求只读；建项权限由角色 + grant 决定。
- attach 保留既有口径：admin/partner 可整理任意同年度单体项目；其他角色须对合并项目和每个下级有编辑权限（原先下级只要是成员即可、合并项目不校验）。
- `project_wizard.py` 因加固超过 800 行门，attach 编排抽到 `project_subsidiary_attachment_service.py`，未抬白名单。

范围外、需要拍板的事项：

1. 平台没有「人员绑定登录账号」入口，共享库 99 个审计员与 8 个管理员中只有 1 个管理员绑定了人员。经理建项（单建与批量）要写 `ProjectAssignment`，要求唯一绑定人员，否则 403「用户未唯一绑定人员」。新建经理账号因此无法建项，6.2 真实写入验收也走不通平台路径。可选：补人员绑定入口；或无人员时只写 `ProjectUser(manager, edit)`、不写委派记录。**→ 用户 2026-10-31 两项都要，见 §9（R6 / R7）。**
2. 删除等端点的权限在依赖层校验、写入在之后，撤权可落在两者之间。这是全平台共性，未在本 spec 处理。
3. assignments 写入口既有鉴权欠账（见 §1），仍不作为建项授权来源。

## 9. 人员档案绑定与无档案经理兼容（R6 / R7）

### 9.1 现状

`staff_members.user_id` 可空、无唯一约束；平台原先只有 `GET /api/staff/me/staff-id` 隐式绑定：先按 `user_id` 找，找不到按“人员姓名 = 用户名”找到即改写 `user_id`（不检查该档案是否已绑定他人，可把别人的档案改绑到自己名下），再找不到自动新建档案。委派同步 `_sync_project_users` 跳过未绑定账号的档案，所以后绑定的账号拿不到既有委派对应的项目成员行；`procedure_authorization` 却按“账号 → 唯一档案 → 委派”判委派权限，二者会脱节。共享库现有 2 个已删除的测试账号分别挂着 2、4 个未删除档案，不能直接加数据库唯一索引。

### 9.2 绑定服务 `staff_account_binding_service.py`

- 锁序：目标账号 `FOR NO KEY UPDATE` → 该档案的有效委派 `FOR SHARE` → 档案 `FOR NO KEY UPDATE` → 重新读取有效委派 → 写成员行。用 `NO KEY UPDATE` 不与外键检查的 `KEY SHARE` 冲突，避免与委派保存、建项写成员行死锁；建项期间持有的账号共享锁会让绑定等待提交，反之亦然。
- 唯一性在锁内校验：账号已有其他未删除档案、档案已绑定其他账号均 409（错误码 `STAFF_ACCOUNT_ALREADY_BOUND`）。不建数据库唯一索引，原因见 9.1。
- 绑定后按档案在未删除项目上的委派角色，经 `resolve_member_mapping` 为缺失的成员行补建，已有行不改，逐项目 `bump_policy_epoch("membership")`。
- 解除绑定：请求带当前档案 ID 做 CAS（不符 409 `STAFF_ACCOUNT_BINDING_STALE`）；仍有有效委派 409 `STAFF_HAS_ASSIGNMENTS` 并列出项目；否则清空 `user_id`。
- 只 flush，由路由提交后写审计（失败不影响主操作）。
- `/me/staff-id` 改走同一服务：已绑定多个档案 409；同名候选只认未绑定、未离职、无有效委派且唯一的档案；有候选但不满足条件 409；完全无候选才自动新建。

### 9.3 无档案经理

`resolve_user_active_staff_id_optional`：0 个档案返回 None，多个仍 403。`AssignmentService.initialize_creator_members(role_key=...)` 为创建者写成员行而不写委派（partner 原逻辑改为调用它）。单建、批量执行、旧版导入、自动合并根、连续审计在经理无档案时都改用它。

### 9.4 接口与界面

- `GET /api/users/staff-bindings`、`POST /api/users/{user_id}/staff-binding`、`POST /api/users/{user_id}/staff-binding/unbind`，均仅 admin。
- `GET /api/staff` 增加 `unbound_only`，供绑定弹窗按姓名 / 工号搜索未绑定档案。
- 用户管理页加“人员档案”列；绑定弹窗与解除确认放在独立组件，页面只负责刷新。

### 9.5 验收

后端覆盖绑定规则、成员补建与不改既有行、解除被委派阻断、`/me/staff-id` 不可劫持、经理无档案的四条创建入口、真 PG 并发绑定互斥；前端覆盖列表、绑定、解除与 409 提示。真实写入验收按 6.2 用【测试】经理账号走一遍，并验证无档案建项只写成员行。

## 10. 6.2 真实验收与第二轮复核（2026-10-31）

### 10.1 实测发现并修复

经理授权被撤销后在向导点「确认创建」：拦截器对 403 只显示固定的「权限不足，无法执行此操作」，后端原因（缺哪些代码的授权）没有显示；接口错误经 `useFormSubmit` 重新抛出，冒泡到外层 `ErrorBoundary`，整页换成「页面渲染出错」，已填内容丢失。修法：`creationDeniedMessage` 从错误信封取原因（取不到时兜底「没有建项权限，请联系管理员」）；`wizard.createProject(…, { onForbidden })` 作为请求级 `_forbiddenHandler` 交给拦截器（替代通用提示）；向导 `persistKeepingForm` 只吞接口错误、程序错误照常冒泡。项目概览「创建下年」同口径，不再叠加 `handleApiError` 的「无权操作」。

### 10.2 第二轮复核处理

| 复核项 | 处理 |
|---|---|
| P1 `/me/staff-id` 同名判定与 R6.6 不符（同名都已绑定他人时仍新建、多份同名只剩一份未绑定时自动关联） | 同名候选为 0 才新建；恰好 1 份且未绑定、未离职才关联，并在锁内复查无有效委派；其余 409 |
| P1 绑定 / 解绑与保存团队并发（保存团队读档案账号不加锁） | `lock_staff_rows_for_share`：保存团队软删旧委派之后、写新委派之前给本批档案加 FOR SHARE（与 NO KEY UPDATE 冲突），与绑定方「委派 → 档案」同序。放在软删之前会成环，确定时序用例可证 |
| P2 自助关联在锁外检查委派 | `bind_staff_to_user(require_no_assignments=True)` 锁内复查 |
| P2 解绑不失效、未计程序行任务 | 绑定、解绑对档案作为程序行执行人 / 复核人的项目也递增策略版本；行任务不阻断解绑（R6.4 以团队委派为准） |
| P2 绑定不做 EQCR 独立性校验 | 绑定后同一账号在同一项目一边是 EQCR、另一边不是（含无档案经理建项写入的成员行）⇒ 409 并列出项目 |
| P2 自助关联重入仍写「已绑定」审计 | 加锁后发现已是本人（`changed=False`）不再报自动关联、不写审计 |
| P2 绑定列表响应乱序 | 请求序号，只采用最后一次的结果 |
| P2 无原因的 403 被说成缺企业代码授权 | 兜底文案改为「没有建项权限，请联系管理员」 |
| P2 删除人员与绑定并发 | 未改：`remove_staff` 用加锁前读到的账号，并发绑定时不会撤销刚补建的成员行；两边锁委派行的顺序也不同，可能死锁（PG 会中止一方）。两者都是 admin 操作同一份档案，概率低，记为后续加固 |
| P2 已删除账号上的绑定在界面解除不了 | 未改：共享库 2 个已删除测试账号挂着 6 份档案，需另行清理口径 |
| P2 无档案经理看不到自己项目的底稿 | 待用户确认：`resolve_member_scope` 要求唯一档案链且有主管委派，无档案经理不是主管、可见循环为空（partner 创建者原本如此） |

### 10.3 范围外发现（未改）

1. `DELETE /api/projects/{id}` 与批量删除只按系统角色放行（admin / partner / manager），不校验项目成员。
2. 回收站永久删除用独立连接 + `session_replication_role = replica`，只追加表的禁改触发器不触发、可以删掉失效发件箱行；逐表删除失败被 `except: pass` 吞掉。
3. 建项向导 `handleConfirm`：新建后 `projectId` 已有值，「建项引导 / 公式模板订阅提示 / 合并项目配置合并范围」分支对新项目永远执行不到。
4. 单建（经理有档案）走 `save_assignments`：给本人发「您已被委派」通知并递增策略版本；批量 / 连续审计走 `initialize_project_managers` 不发，两条口径不一致。
5. `test_project_creation_validation::test_concurrent_create_at_most_one_succeeds` 标 pg_only 却用内存 SQLite 夹具，`GT_REQUIRE_PG=1` 时必红（HEAD 同样）。
6. 前端守卫 authTokenSingleSource、rawRequestAuth、cloneable、parseIndexRef 在 HEAD 上就是红的（并发提交引入）。

## 11. 第三批：创建者可见、删除授权、向导分支、通知口径、级联删除（R8–R12）

### 11.1 创建者可见（R8）

`resolve_member_scope` 增加一个分支：用户是本项目 `Project.created_by` 且有至少一条有效成员行（`is_member`）⇒ `is_supervisor=True` + 全部循环。`created_by` 是同事务写入、不可更改（请求体里的 `manager_id` 被服务端归一），因此只需读一次 `Project.created_by`。创建者后来被移出团队（成员行全部软删）时 `is_member=False`，不再按创建者放行。

契约影响：`docs/contracts/procedure-chain/cases/member-scope.json` 需加一组「创建者无委派但有成员行 → 主管」的用例。

### 11.2 删除项目按项目授权（R9）

`delete_project` 与 `batch_delete_projects` 把手写的系统角色检查换成 `Depends(require_project_access("edit"))`。`require_project_access` 已处理 admin 跳过、归档 423、RLS 设置；edit 权限要求 `ProjectUser.permission_level` 为 edit 级（经理、合伙人、审计员的 edit 成员行都满足）。批量删除按每个项目逐一校验，无权限的报错但不阻断其他项目。

### 11.3 向导新建分支恢复（R10）

`handleConfirm` 拆成两步：先 `persistKeepingForm`（创建项目、设 `projectId`），然后在 `if (justCreated)` 分支里依次走引导、公式订阅、合并项目弹窗；最后统一 `confirmProject`。`justCreated` 从 `persistKeepingForm` 返回的 boolean 判断（`wizardStore.projectId` 在调用前为 null）。用例覆盖：新建走引导 → 确认进 planning → 合并项目弹窗；引导取消 → 项目仍创建但停在 created（等下次进入再确认）。

### 11.4 创建者通知口径（R11）

`project_creation_coordinator.create_project_for_actor` 在经理有档案时改调 `initialize_project_managers`（与批量同口径）。`save_assignments` 改为只在**非新建上下文**使用（保存团队页）。新项目在事务内无缓存、无可见性历史，不需要 `bump_policy_epoch` / `broadcast_raw` / 通知。

### 11.5 回收站永久删除（R12）

`_cascade_delete_project` 改为：在同一连接上按 FK 拓扑排序（先删叶子、最后删 projects）逐表删除，禁用 FK 检查仍保留（避免跨表 ON DELETE RESTRICT 中途失败），但不再 `except: pass`。单条 DELETE 失败立即中断、整个事务回滚。删除前的 `is_deleted` 二次确认保留。自引用处理移到正式删除顺序之前。前端在回执里显示后端的 `detail` 字段。
