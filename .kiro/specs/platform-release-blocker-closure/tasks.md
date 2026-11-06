# 平台发布阻断项收口 — 任务

> 实施说明（2026-11-05）：候选基于远端最新 `65709f0b2`（tag v1.0.136），在锁定 detached worktree
> `tmp_platform_release_blocker_closure/verify_wt` 实施，基线 worktree `base_wt` 同一 commit。详见
> design §9 勘误。多数「启动/保存/复核/隔离/出具」任务在远端 `bb29a49f6`(v1.0.80) 起已交付、并经
> v1.0.126/127 修复，本批复核确认而非重做；终态冻结（Task 9）、readiness 六源统一（Task 15/16）为本批新增/补齐。

## A. 候选基线

- [x] 1. 从最新远端建立锁定 detached worktree，记录代码、DB、浏览器和健康检查基线
  - 证据：verify_wt + base_wt 均锁定于 `65709f0b2`；DB 基线 `schema_version` max=264/applied=254/failures=0；
    audit_log_entries 6470 行、哈希链每链恰一未确认链尾；膨胀索引 3 个、invalid index=0。
- [x] 2. 创建 requirements/design/tasks 三件套，冻结本批边界与共享库写入停点

## B. 可启动与保存真实性（远端已交付，本批实测复核）

- [x] 3. 修复 AI 笔记导出契约；DshPanel 改首次打开再加载并提供局部失败态
  - 远端已交付（design §2）；发布门专项 + 受影响域回归覆盖，无本批 2/24 假红。
- [x] 4. 修复 Univer 非 2xx 假成功、冲突覆盖语义和业务回执校验
- [x] 5. 自动保存增加 boolean 失败与编辑代际，保存期间新编辑不得被旧回执清除
  - `useWorkpaperAutoSave`/`useEditorSave` 代际与 boolean 回执语义已在远端，受影响域前端 vitest 覆盖。

## C. 复核主链

- [x] 6. 抽取单笔/批量共用的提交复核服务，门禁 fail-closed，程序状态同事务
  - `workpaper_review_submission_service` 单一入口 + 批量 SAVEPOINT（远端）；发布门专项 103 passed 覆盖。
- [x] 7. 编辑器与底稿列表切到唯一提交入口；两条旧提交接口返回 410
- [x] 8. 退回→修改→编制完成→重提闭环；复核层级角色真正参与授权
  - 本批新增 `test_workpaper_review_lifecycle_pg.py`（真 PG）：退回→编制完成→重提→L1 manager→L2 partner→
    L3 qc 全通，EQCR 被拒；并发内容写与终态按锁串行。裁定保留 `edit_complete` 前置（design §9.3）。
- [x] 9. 复核通过/归档后的所有底稿写入口统一后端锁定 ★本批新增
  - 新建纯判据 service `workpaper_content_freeze`（`WorkpaperContentFrozenError`→423、
    `assert_workpaper_content_writable`/`load_workpaper_status`/`acquire_project_bulk_content_lock`）；
    接入 `_wp_gate`/`wp_sync_router`+`WpGateVisibilityProbe` 真读 status/`repository.lock_workpaper`
    (`to_jsonb(working_paper)->>'status'`)/`excel_html` 5 处 legacy 写/attachments 5 端点/
    `entry_integration`/`formula_settings WpStore`/`wp_structure.batch_generate`/OO 回调(200+error:1)。
    前端 `WorkpaperEditor.effectiveCanEdit` 纳入 review_passed/archived + `useEditorToolbar` 写动作
    requireEdit + 新建 `WorkpaperFrozenBanner.vue`。守卫 `test_workpaper_terminal_freeze_guard.py`。
    内容写统一 423（design §9.2）；3 个旧测试口径 403→423。

## D. 项目隔离（远端已交付，本批实测复核）

- [x] 10. Metabase 嵌入鉴权、正式密钥配置、删除 A5-1 debug 路由
- [x] 11. 导入 SSE 绑定 project/job；接管请求 reason 与 manager 角色对齐
- [x] 12. 复核意见绑定 wp/review 且 actor 取登录用户；review-config 加项目门
- [x] 13. 用户公式 v2 实验接口 fail-closed 410；补安全端点测试

## E. 出具可信度

- [x] 14. 报表前 TB 重算失败阻断；前端一键全套切正式 trio，旧入口 410（远端已交付）
- [x] 15. 合并附注导出改读根节点 ConsolNoteData；readiness 按单体/合并分流 ★本批补齐
  - `consol_note_export_adapter`（远端）；本批删 `DeliverableReadinessService._check_adjustments/_check_reports`
    子类 override，六源统一走 `deliverable_readiness_sources.ReadinessSourceChecks.content_digest`。
- [x] 16. trio snapshot 纳入内容/版本摘要，并补 retry 漂移测试 ★本批补齐
  - `_check_adjustments` 改按分录组计数 + 全行摘要 + `line_count`；发布门专项覆盖 retry 漂移。

## F. 迁移与发布

- [x] 17. 启动只读核对磁盘/DB 迁移集合；pending/failed/critical drift 使 readyz 503
  - 一次性 PG 实测 `/readyz`=200（is_complete=True）；共享库只读核对 pending=[]/failures=[]/漂移全部已登记。
- [x] 18. 修复 build:verify、verified preview、Docker package scripts 与 Vite outDir
  - `build:verify`（vite 生产构建 → bundle budget `--check` → smoke → 发布 `.verified-dist`）在候选跑通。
- [x] 19. CI 覆盖 spec/**，将本批安全、runtime import、迁移完整性测试接成阻断门（远端已交付，`.github/workflows` 核对）

## G. 验收

- [x] 20. 后端相关单元/端点测试、前端相关 vitest、类型与 runtime import 通过
  - 后端发布门专项 103 passed；受影响域 737 passed + 修复前 4 failed/2 error 六项经修复后复跑全绿
    （逻辑 25 passed + 真 PG 27 passed）；真 PG 迁移完整性 17 passed + 漂移登记 56 passed。
  - 前端全量类型检查（40GB 堆 vue-tsc）候选 2958 / 基线 2958，ADDED=0 RESOLVED=0。
  - 前端 vitest：同树两次运行（run1/run2，代码完全相同）对称差 204（102+102 翻转 + 81 两次都红）⇒ 套件
    ~200 级 flaky（worker 崩溃级联）；base-vs-候选 ADDED=108 落在该 flaky 包络内、净 -1。唯一确定性 ADDED
    （`ReportView.vue` 1954>cap 1944）经证基线日志同红=远端 HEAD 既有，非本批。我 3 个改动文件
    (WorkpaperEditorShell/WorkpaperFrozenBanner/useEditorToolbar/line-budget) 隔离跑 54 passed。
- [x] 21. 一次性 PostgreSQL 从空库跑全迁移并验证；不写共享库
  - 临时库 `gt_release_blocker_*`：CREATE_ALL 365 表、磁盘迁移 252 执行 251 失败 0、pending=[]、failures=[]、
    checksum drift=[]、V229+V264 已登记、is_complete=True、/readyz=200、90 passed、DROP=OK。口径「当前全部迁移」
    （V229 早已落库，见 design §9.4）。
- [ ]* 22. 独立端口浏览器验证登录、项目、TB、底稿、复核、报表、附注、trio 主链
  - 写入型主链已完成（见下 ✅）；浏览器生产构建 smoke 与 OO→HTML 往返仍外部阻断，故整条标 `[ ]*`。
  - Dev 模式渲染正常：共享 dev server（127.0.0.1:3030）登录页表单完整。
  - 🔴 生产构建 `build:verify` 产物浏览器白屏（`vendor-core:30:11317` TDZ `Cannot access 'Rt' before
    initialization`）= **远端 HEAD 既有缺陷**，干净 base worktree 重建后同样白屏（符号 / 位置一致），非本批
    35 文件引入（均不触 vendor-core）；smoke 不执行 JS 故漏检。⇒ 候选 verified-dist 的只读浏览器 smoke 无法执行。
    建议另立 spec 修 vendor-core 分块 + smoke 加无头浏览器步（见 design §9.6）。
  - 终态冻结（本批核心）由真 PG `test_workpaper_review_lifecycle_pg.py` + 一次性库 `PARTIAL_STATUS_STUB=OK`
    + 守卫 `test_workpaper_terminal_freeze_guard.py`（17 passed）覆盖；前端只读 / 冻结横幅由 vitest 隔离 54 passed 覆盖。
  - ✅ 写入型主链（复核→终态→内容写 423）已在用户授权后于候选代码（v1.0.139）验证，四重证据（design §11）：
    ① aos8 真 HTTP（`test_aos_adopt_endpoint_http.py` 13 passed，共享 PG 隔离 scratch schema，真 router +
    ResponseWrapperMiddleware）——workflow_locked→**423** + digest 正向采纳成功写审计链（修前 4 failed：我的
    下游漏改 2 处 403→423 断言 + 既有 harness 漏建 `audit_chain_head` 伴生表 2 处，均已修）；
    ② freeze 逻辑 `test_workpaper_terminal_freeze_guard` + `test_release_readiness_content_snapshot` 31 passed；
    ③ 共享库 public schema freeze 探针（回滚事务、零残留、零审计污染）：真 `working_paper` 表 / 真 `WpFileStatus`
    PG 枚举，4 个终态（review_passed/archived/review_level1_passed/review_level2_passed）全 423、draft 放行、
    走 for_update=True 完整路径（advisory xact lock + FOR UPDATE），回滚后状态复原 draft；
    ④ 全复核链→终态→423 由一次性库 lifecycle 覆盖（Task 21 的 90 passed 含 lifecycle）；
    `test_workpaper_review_lifecycle_pg` 自带 `_require_disposable_database` 守卫，禁止对共享库跑（防追加型
    `audit_log_entries` 哈希链被测试数据污染）——故不对共享库做完整复核链 UAT，是设计意图而非遗漏。
  - OO→HTML 往返依赖上游 `wp-sync-conflict-adjudication-and-d4-32-modeling`（代码在 v1.0.136，但其 Task 12
    真库 UAT + definition re-provision 未执行）⇒ 无可通路径。如实标未完成 + 登记依赖。
- [x] 23. 五角色复核、语义审查、INDEX 登记；同步最新远端后单 commit 与版本化推送
  - 两阶段版本化推送：阶段一 v1.0.138（commit f73449c3b，Task 1–21 + Task 24 调查 + Task 22 非写入证据）；
    阶段二 v1.0.139（本 commit，Task 22 写入型 UAT 的 2 文件下游收口 + Task 24 执行结果 + 本翻牌）。
  - 阶段二推送前 ls-remote 核对远端分支头 = f73449c3b（阶段一头，无并发漂移），干净快进。

## 外部停点

- [x]* 24. 共享库执行待迁移、调查审计链分叉、重建膨胀索引与验证 invalid constraints——执行前单独取得用户批准
  - 调查完成（design §9.5 + `task24-change-order.md`）：审计链 9 分叉点/10+1 确认条目已于 11-04 全部确认、无待办；
    迁移 pending=0/failures=0/漂移全部已登记（本批新登记 V233/V234，逐对象核验在库全生效）；10 条 NOT VALID 约束
    现有数据 0 违反（VALIDATE 安全）；3 个膨胀索引 invalid=0。
  - ✅ 用户已授权，变更单已对共享库 `audit_platform` 执行并复核（Python asyncpg 写连接，脚本在
    `tmp_release_blocker_apply/`，执行证据见 design §11）：
    ① VALIDATE 10 条 NOT VALID 约束逐条成功，convalidated 全 True，public schema 剩余 NOT VALID 约束归零；
    ② REINDEX INDEX CONCURRENTLY（autocommit、非事务块）3 个膨胀索引——`tb_aux_ledger_pkey` 602→470MB
    （回收 132MB），两个 window 索引基本无变化（原膨胀估算偏乐观，重建无害）；无 `*_ccnew` 残留、全部 valid/ready。
