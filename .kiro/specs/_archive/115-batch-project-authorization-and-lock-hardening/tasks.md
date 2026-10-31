# 任务：批量建项授权与拓扑锁加固

完成项必须有生产代码和通过证据；写入验收只用【测试】数据；不自动提交或推送。

- [x] 0. 现状调查与裁定
  - [x] 0.1 现读客户/公司/项目权限、单建与批量旁路、partner 可见性、用户管理和授权缺口
  - [x] 0.2 现读 status/年度锁、跨组环、advisory lock 先例与 Playwright synthetic 基座
  - [x] 0.3 裁定：admin/partner 全局创建，manager 精确 USCC grant，admin-only 管理；年度锁暂不细化

- [x] 1. 授权模型、迁移与管理 API
  - [x] 1.1 V227/R227 `project_creation_grants` + ORM（CHECK、活动唯一索引，SQLite 用 `sqlite_where` 同口径）+ 现有 manager edit 项目幂等回填
  - [x] 1.2 列表 / 批量授予 / 撤销（`expected_version` CAS）、有效期与审计；admin-only 端点挂 users router
  - [x] 1.3 迁移正反向、回填、非 manager 目标 422、重复授予幂等、撤销后重授、partner 管理 403 的 TestClient / PG 测试
  - [x] 1.4 V228/R228：`gt_is_valid_uscc` 与 `validate_uscc` 同算法（368 个样本零差异）、撤销校验码错误的回填授权、未撤销行 CHECK 约束；已经 MigrationRunner 落共享库

- [x] 2. 全创建链统一授权与防枚举
  - [x] 2.1 manager 在任何项目库存查询前校验 create 行 company/parent/ultimate；库存补齐出的新代码先授权再扩大库存查询，计划保存最终代码集合的快照
  - [x] 2.2 apply / legacy 先取年度锁，再锁 actor（标量 FOR SHARE，绕开 identity map）与 grant 并按当前时间重验；撤销、到期、版本漂移统一 `BATCH_PLAN_STALE`
  - [x] 2.3 单项目 POST 收紧角色；年度锁后重验显式代码，`prepare_group_fields` 后按最终代码再授权；manager_id/signing partner 服务端归一，创建与 manager/edit 成员同事务
  - [x] 2.4 Redis actor 限流 + Retry-After；授权拒绝只审计代码集合摘要与数量
  - [x] 2.5 连续审计：锁旧/新年度、来源身份 CAS、grant 重验、成员锁 + 来源只读权限、manager/partner 创建者成员初始化（`copy_team=false` 也有）

- [x] 3. 状态行锁有界等待
  - [x] 3.1 PG 保存点 + 1500ms lock_timeout + SQLSTATE 55P03 → `BATCH_PLAN_STATUS_BUSY` / Retry-After，不回退普通读
  - [x] 3.2 前端 busy 保留计划并有限重试（apply 后恢复与首次打开恢复两条路径）；真 PG「超时 → 随后 applied」与前端回归

- [x] 4. 年度拓扑逻辑锁与量测
  - [x] 4.1 年度 advisory xact lock（空年度用专用锁键）；batch、单建、basic_info、attach、reparent、显式关系、删除/恢复、连续审计、项目配置、准则变更在首次敏感读取前取锁
  - [x] 4.2 AST 守卫：重算调用方清单、三码 / 年度 / 口径写入面冻结并分类、写入前须持年度锁、写路径权限检查须在成员锁之后、永久删除顺序；3 个真实源码内存变异全部打红，阴性对照全绿
  - [x] 4.3 20 / 100 组基准，保持年度粒度（数据见验收记录）
  - [x] 4.4 attach 抽到 `project_subsidiary_attachment_service`：锁后父 / 子身份 CAS、成员锁、最终图无环校验
  - [x] 4.5 删除 / 批删锁后年度 CAS；回收站永久删除 / 批量 / 清空与恢复共用年度锁，独立连接删除前复查已删除状态

- [x] 5. 管理 UI 与正式 Playwright
  - [x] 5.1 用户管理页经理建项授权卡片、授予二次确认、撤销填原因；加载失败态与重新加载、账号变更后刷新、已暂停状态；全中文
  - [x] 5.2 专用零真库 synthetic harness/config + `npm run test:e2e:batch-project`；默认配置 `testIgnore` 该用例（其 globalSetup 会写 seed）
  - [x] 5.3 下载（真实 download 事件 + 字节）、两类恢复竞态、500 节点 DOM / 末项 / Long Task、自检、390px

- [x] 6. 综合验收与清理
  - [x] 6.1 后端 SQLite/PG、前端 Vitest / scoped vue-tsc / ESLint、Playwright、迁移、文件行数和 diff 检查
  - [x] 6.2 真实写入验收（授予 → 建项 → 撤销 → 拒绝，另含无人员档案建项）：用户 2026-10-31 放行；【测试】经理账号的人员档案经用户管理页绑定（未直接写库），经理在建项向导操作；清理与残留见验收记录（第二批）
  - [x] 6.3 更新验收记录、INDEX 与开发历史，未提交 / 未推送
  - [x] 6.4 第二轮独立语义复核（2026-10-31 补做，范围限 R6 / R7 与建项被拒修复）：P1 两条、P2 九条，处理见 design §10.2
  - [x] 6.5 前几轮（授权、年度锁、回收站、连续审计）改动的第二轮独立复核：手动审查关键路径（授权门 `_ROLE_BYPASS`、年度锁→重验→成员锁顺序、到期校验、`BATCH_PLAN_STALE` 统一），无 P0/P1

- [x] 7. 人员档案绑定登录账号（R6）
  - [x] 7.1 绑定服务：锁序、唯一性、成员补建与策略版本、解除绑定 CAS 与委派阻断、审计；绑定前 EQCR 独立性校验（R6.7）
  - [x] 7.2 admin-only 接口 + `GET /api/staff` 的 `unbound_only`；`/me/staff-id` 只在完全无同名档案时新建，唯一安全候选才关联且锁内复查委派，不可劫持
  - [x] 7.3 用户管理页人员档案列、绑定弹窗与解除确认，全中文；绑定列表只采用最后一次请求的结果
  - [x] 7.4 后端规则 / 路由 / 真 PG 并发（一对一、与保存团队三种交错顺序、确定时序的防死锁）与前端组件测试；保存团队给本批档案加 FOR SHARE（R6.8）

- [x] 8. 经理没有人员档案时的建项兼容（R7）
  - [x] 8.1 可选档案解析 + 创建者只写成员行；单建、批量执行、旧版导入、自动合并根、连续审计接入
  - [x] 8.2 无档案四条入口只写成员行、多档案仍 403 的测试
  - [x] 8.3 建项被拒提示（R7.4，6.2 实测发现）：向导与「创建下年」403 显示后端原因，接口错误不再冒泡到错误边界，向导保留已填内容

- [x] 9. 创建者可见本项目底稿（R8）
  - [x] 9.1 `resolve_member_scope`：`Project.created_by == user_id` 且有成员行 ⇒ 主管 + 全部循环
  - [x] 9.2 member-scope 契约用例补「创建者无委派 → 主管」与「创建者被移出团队 → 受限」
  - [x] 9.3 单测 5 条 + 契约 12 条（含 R8 2 条）

- [x] 10. 删除项目按项目授权（R9）
  - [x] 10.1 `delete_project` / `batch_delete_projects` 改用 `require_project_access("edit")` / 逐项 `assert_project_permission`
  - [x] 10.2 前端删除按钮：后端收窄后按钮保留（列表不带权限字段），403 由拦截器提示「权限不足」，比原来更安全
  - [x] 10.3 批删逐项校验（无权限的报错但不阻断）

- [x] 11. 建项向导新建分支恢复（R10）
  - [x] 11.1 `handleConfirm` 拆两步：创建 → 引导 / 公式订阅 / 合并弹窗 → `confirmProject`
  - [x] 11.2 用例：新建走引导 → 确认 → planning；引导取消 → created + 提示；公式订阅「去订阅」→ 先确认再跳设置页

- [x] 12. 创建者通知口径一致（R11）
  - [x] 12.1 单建经理有档案改走 `initialize_project_managers(require_pending=False)`

- [x] 13. 回收站永久删除不吞失败（R12）
  - [x] 13.1 `_cascade_delete_project` 按 FK 查询顺序删除、不 except pass、失败回滚报错
  - [x] 13.2 前端永久删除回执：后端级联失败返回 HTTPException 500 + 中文表名，拦截器提示

## 验收记录（2026-10-31）

- 后端：9 个相关文件 148 passed（`DATABASE_URL`=PG、`GT_REQUIRE_PG=1`，无跳过）；真 PG + 迁移组 8 个文件 74 passed；ruff、文件行数门、`git diff --check` 通过。测试后共享库测试用户 / 项目 / 计划 / 授权 / 临时 schema 均为 0。
- 迁移：V227 checksum `cb12947f…`、V228 checksum `b33179f1…` 已落共享库，共享库授权 0 行。
- 前端：Vitest 5 个文件 43 passed；scoped vue-tsc 0 错（修复前真实报出 TS7053，非空转）；ESLint 15 个文件无问题；专用 Playwright 6 passed；默认配置列出 1750 条且不含该用例。
- 浏览器只读走查（127.0.0.1:3030 + 真实 9980）：admin 打开 `/settings/users`，授权列表 GET 200、空态正确、未选经理时提交被拦截；授权写请求 0、控制台错误 0、页面错误 0。
- 年度锁基准（100ms 临界区）：20 组同年 total 2433.5ms、p95 2205.5ms、峰值 1；不同年 total 401.5ms、峰值 20。100 组同年 total 11948.3ms、p95 11187.1ms、峰值 1；不同年 total 1529.8ms、峰值 100。另有一次 20 组同年在共享环境负载下 total 11584.4ms，说明同年串行对外部负载敏感。结论：保持年度粒度，等有稳定集团拓扑标识后再细化。
- 偏差与范围外事项见 design.md §8。

## 验收记录（2026-10-31 第二批：R6 / R7、6.2、第二轮复核）

- 后端：相关 43 个文件 502 条回归（`DATABASE_URL`=PG、`GT_REQUIRE_PG=1`，无跳过），唯一失败 `test_project_creation_validation::test_concurrent_create_at_most_one_succeeds` 在 HEAD 干净 worktree 3/3 同样失败（标 pg_only 却用内存 SQLite 夹具，ORM 无三码唯一索引），非本 spec 引入。绑定用例 SQLite 11 条 + 真 PG 3 条（隔离 schema，结束整体 DROP）。变异：绑定锁 M1 / M2（第一批）与本批 S1–S3、E1–E2、V1–V3、L1、L2 共 10 条全部打红，对照全绿；L2（档案锁挪到软删旧委派之前）靠确定时序用例才打红。ruff 无新增，行数门、`git diff --check` 通过。
- 前端：本批改动相关 38 条通过；两次选集（118 文件 930 条、82 文件 1057 条）的 8 条失败（authTokenSingleSource、rawRequestAuth、cloneable、parseIndexRef）在 HEAD worktree 逐条同样失败。组件变异 31 条（绑定弹窗 9、用户管理页 10、建项被拒 12）全部打红。限定 vue-tsc（24GB 堆）HEAD 1231 / 工作区 1219，相对 HEAD 新增 0，本次改动文件 0 条；ESLint 0 错（`DetailProjectPanel.vue` 19 条警告与 HEAD 相同）；synthetic Playwright 6 passed。
- 6.2 真实验收（127.0.0.1:3030 + 真实 9980，脚本在仓库外，分阶段截图）：admin 建【测试】经理账号 `test_bpah_manager` 与人员档案「【测试】批量授权验收经理」→ 用户管理页绑定（候选只列未绑定档案、二次确认写明档案与账号）→ 授予 `91110000BPAH62011M` → 经理在向导建 2097 项目甲：成员行经理 / 编辑 + 经理委派 1 行 → 解除绑定被拒 409（提示列出项目甲）→ 撤销授权 → 经理再建（2096）403；修复后提示「有 1 个企业代码暂无建项授权，请联系管理员授权」、表单保留、可再次提交 → 删项目甲后解除绑定 200 → 授予第二个代码 → 经理无档案建项丙：成员行经理 / 编辑，委派 0。经理会话全程未调用 `/api/staff/me/staff-id`，该账号档案 0 份。控制台错误只有被拒请求的浏览器网络日志，页面错误 0。
- 清理（平台路径）：软删项目丙 → 回收站永久删除甲、丙 → 撤销第二条授权 → 软删人员档案 → 停用账号（停用后登录被拒）。按外键逐表对账：两个项目及引用它们的子表行全部为 0。如实残留：停用账号 1 行（平台无删账号入口）、软删档案 1 行、已撤销授权 2 行、`notifications` 1 行（建项甲时 `save_assignments` 发给经理本人的委派通知）、操作日志 `logs` 20 行、审计哈希链 7 行（绑定 2、解除 2、建项被拒 2、停用 1）。
- 偏差、复核处理与范围外事项见 design.md §10。
