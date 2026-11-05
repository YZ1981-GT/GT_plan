# 平台发布阻断项收口 — 任务

> 🔴 **2026-11-04 现状更正（阶段 0 收口）**：本文件原记 2/24，属**假红**。
> 实现提交 `bb29a49f6`（tag **v1.0.80**，2026-11-01，60+ 文件）早已合入主线，经
> `git merge-base --is-ancestor bb29a49f6 HEAD` 确认是当前 HEAD 的祖先，只是任务清单没回填。
> 本轮在干净分离头 worktree（基于 `f4674c189`）重新验收这批已入库改动，并修掉
> 40+ 个后续提交造成的 5 处脱节。下方勾选按**本轮实测证据**标注；未实测项保持未勾。
> 验收命令（`DATABASE_URL` 指向不存在的 PG 库，不触达共享库）：
> `python -m pytest tests/test_release_frontend_pipeline.py tests/test_release_output_guards.py
> tests/test_release_readiness_content_snapshot.py tests/test_release_migration_readiness.py
> tests/test_release_lazy_import_closure.py tests/test_release_runtime_import_closure.py
> tests/test_platform_release_security.py tests/test_workpaper_review_submission_service.py
> tests/services/test_consol_note_export_adapter.py tests/test_project_creation_grants.py
> -p no:playwright -q` = **71 passed**（修复前 12 failed / 119 passed）。

## A. 候选基线

- [x] 1. 从最新远端建立锁定 detached worktree，记录代码、DB、浏览器和健康检查基线
- [x] 2. 创建 requirements/design/tasks 三件套，冻结本批边界与共享库写入停点

## B. 可启动与保存真实性

- [x] 3. 修复 AI 笔记导出契约；DshPanel 改首次打开再加载并提供局部失败态
  - 证据：`DshPanelLoadError.vue`、`useMountOnFirstOpen.ts`、`ThreeColumnLayout.vue`
    的按需 `import('@/components/ai/DshPanel.vue')` 均在 HEAD；本轮修复 async
    `errorComponent` 不转发外层 `v-model` 的死路：由宿主显式持有模块/错误状态，错误面板
    的「关闭」真正收起，下一次打开会重新加载。`ThreeColumnLayout.dshLazy.spec.ts`、
    `useMountOnFirstOpen.spec.ts` 已在本轮前端选集通过
- [x] 4. 修复 Univer 非 2xx 假成功、冲突覆盖语义和业务回执校验
  - 证据：`useEditorUniver.ts` / `useEditorToolbar.ts` 改动在 HEAD；
    `useEditorUniver.spec.ts` / `useEditorToolbar.spec.ts` 已在本轮前端选集通过
- [x] 5. 自动保存增加 boolean 失败与编辑代际，保存期间新编辑不得被旧回执清除
  - 证据：`useWorkpaperAutoSave.ts`（+92 行代际逻辑）在 HEAD；
    `useWorkpaperAutoSave.spec.ts` 与 `UniverEditorCore.sheet-context.spec.ts` 已在本轮前端选集通过。
    后者原测试 mock 错把 `onSave` 设成另一个 `vi.fn`，使 `false` 的失败回执永远到不了
    自动保存回调；现已改为同一 spy，真实验证失败保持 false

## C. 复核主链

- [x] 6. 抽取单笔/批量共用的提交复核服务，门禁 fail-closed，程序状态同事务
  - 证据：`services/workpaper_review_submission_service.py` 在 HEAD；`wp_review_router.py`
    与 `wp_batch_router.py` 均 import 同一服务（单笔/批量共用已接线）。
    `test_workpaper_review_submission_service.py` **本轮实测 passed**
- [x] 7. 编辑器与底稿列表切到唯一提交入口；两条旧提交接口返回 410
  - 🔴 **本轮修复前端绕过门禁**：`useEditorSave.onSubmitForReview` 原直接 PUT
    `P_wp.status(..., { status: 'pending_review' })`，绕过后端专用 `submit-review` 的
    edit_complete、SoD、QC、批注与 AI fail-closed 检查。现改 POST `P_wp.submitReview(...)`；
    `can_submit === false` 时显示具体阻断原因、不刷新详情。`reviewSubmissionPaths.spec.ts` 已在本轮前端选集通过，
    旧状态字面量已为 0
- [ ] 8. 退回→修改→编制完成→重提闭环；复核层级角色真正参与授权
  - 未实测：需真实 PG + 多角色端到端，留待任务 22
- [ ] 9. 复核通过/归档后的所有底稿写入口统一后端锁定
  - 未实测：`_wp_gate.py` 改动在 HEAD，但 608 条写路由的覆盖面需专项核对

## D. 项目隔离

- [x] 10. Metabase 嵌入鉴权、正式密钥配置、删除 A5-1 debug 路由
  - 证据：`main.py` 现算 `_debug/a51` **0 命中**（三个 debug route 已删）；
    `core/config.py` 新增签名密钥字段；`test_platform_release_security.py` **本轮实测 passed**
- [x] 11. 导入 SSE 绑定 project/job；接管请求 reason 与 manager 角色对齐
  - 证据：`ledgerImportV2Api.ts` / `ImportHistoryEntry.vue` 改动在 HEAD；
    安全守卫 `test_platform_release_security.py` **本轮实测 passed**
- [x] 12. 复核意见绑定 wp/review 且 actor 取登录用户；review-config 加项目门
  - 证据：同上安全守卫覆盖（**本轮实测 passed**）
- [x] 13. 用户公式 v2 实验接口 fail-closed 410；补安全端点测试
  - 证据：同上安全守卫覆盖（**本轮实测 passed**）

## E. 出具可信度

- [x] 14. 报表前 TB 重算失败阻断；前端一键全套切正式 trio，旧入口 410
  - 🔴 **本轮修复**：`generate_all_reports` 已被 `report_provenance`
    （consolidation-run spec 的 advisory lock + building run）包裹，原守卫的 AsyncMock
    在 `_advisory_lock` 的 `db.get_bind()` 就抛 `AttributeError: 'coroutine' object has no
    attribute 'dialect'`，**走不到 recalc 断言**（假失败掩盖了真判据）。
    改测试：`get_bind` 返回同步非 PG bind 跳过 advisory lock，并把断言从
    `db.flush.assert_not_awaited()`（provenance 现在会先 flush building run，恒假）
    换成 `_generate_report` 未被 await（报表生成确实没开始）。
    生产 `report_engine.generate_all_reports` 的 fail-closed 逻辑**未改**，
    `test_report_engine_has_no_fail_open_recalc_branch` 始终绿。证据：`test_release_output_guards.py` **3 passed**
- [x] 15. 合并附注导出改读根节点 ConsolNoteData；readiness 按单体/合并分流
  - 🔴 **本轮修复了一个生产 P0（非本 spec 引入）**：陈旧整树提交把
    `DeliverableReadinessService` 的 `_check_trial_balance` / `_check_formula_push` /
    `_check_notes` 换回了**无 `report_scope` / 无 `content_digest`** 的旧版，
    override 掉父类 `ReadinessSourceChecks`（`deliverable_readiness_sources.py`）的正确实现；
    而同文件 `check()` 调用时**却传了 `report_scope=`** ⇒ 生产恒 `TypeError`，
    被 `check()` 的 `try/except` 吞成 `upstream_not_ready` blocker ⇒
    **readiness 恒 blocked、交付件出不了**。处置 = 删掉这 3 个重复 override（-142 行），
    继承父类正确版（父类已有 consol 分流 + `consol_note_export_adapter` 调用 + content_digest）。
    `_check_adjustments` / `_check_reports` 的子类 override 业务口径不同（按分录组 vs 按行、
    含/不含 rejected）且无测试覆盖，**本轮保留不动**，登记为范围外。
    证据：`test_release_readiness_content_snapshot.py` + `test_consol_note_export_adapter.py` 全绿
- [x] 16. trio snapshot 纳入内容/版本摘要，并补 retry 漂移测试
  - 证据：父类恢复后 `content_digest` 生效，`test_snapshot_digest_changes_when_amount_changes_but_count_does_not`、
    `test_same_count_amount_change_blocks_retry_before_step_runner`、
    `test_trial_balance_query_digest_tracks_amount_with_same_row_count` 均 passed。
  - 🔴 **顺带修 V250 模型与迁移口径不一致**：`user_display_preferences` 的
    `ck_udp_fixed_columns_is_object`（`jsonb_typeof(fixed_columns) = 'object'`）原被完全移出
    ORM `__table_args__`，注释理由是「SQLite `create_all` 会报 no such function」。
    改用 `CheckConstraint(...).ddl_if(dialect="postgresql")`：PG DDL 有该约束、SQLite DDL 没有。
    **实测证明原理由不成立**：该表在 SQLite 上本来就建不了，真实阻碍是
    `JSONB` 类型无法渲染（`CompileError: can't render element of type JSONB`），与 CHECK 无关
    ⇒ 本改动对 SQLite 测试零影响。证据：`PG_HAS_JSONB_CHECK: True`

## F. 迁移与发布

- [x] 17. 启动只读核对磁盘/DB 迁移集合；pending/failed/critical drift 使 readyz 503
  - 证据：`api/probes.py:readyz`、`api/health.py` 的 `pending_versions`、
    `core/startup_migrations.py` 的 `migration_readiness` fail-closed、
    `core/migration_runner.py` 的 `is_complete` 均在 HEAD 完好；
    `test_release_migration_readiness.py` **本轮实测 passed**
- [x] 18. 修复 build:verify、verified preview、Docker package scripts 与 Vite outDir
  - 🔴 **本轮修了一个真 bug（不是只改测试对齐）**：`check-bundle-budget.mjs` 的
    `cliOptions` **只认 `--dist`**，而全仓约定是 `--dir`（`smoke-built-artifact.mjs` 的
    `parseArgs` 只认 `--dir`、传别的直接抛「未知参数」；`update-bundle-budget.mjs`、
    `package.json` 的 `bundle:check` / `smoke:built` 都用 `--dir`）⇒ `bundle:check` 传的
    `--dir dist` 被**静默忽略**、落到 `GT_FRONTEND_OUT_DIR` 兜底，设了该环境变量
    （verified 构建就会设）时会**检查错目录**。处置 = 让它优先认 `--dir`、保留 `--dist` 兼容。
    守卫同步改为 `--dir` 与 `smoke-built`（platform-perf 已把
    `smoke-built-dist.mjs` 演进为 `smoke-built-artifact.mjs`）。
  - 🔴 **本轮再修两处发布链真缺陷**：①`HEAVY_PATTERN` 漏 `heavy-office` /
    `heavy-excel`（Vite 的真实 manualChunks 名），预算守卫无法发现 Office/Excel 重块被静态拉进入口；
    现纳入模式并以 CLI fixture 覆盖。②`build-verified-dist.mjs` 仍调用旧
    `smoke-built-dist.mjs --dist`，而当前权威 smoke 是 `smoke-built-artifact.mjs --dir`；
    同时 `current.json` 直接覆盖写会暴露截断 JSON。现改走权威 smoke、统一 `--dir`，
    并将指针改为临时文件写全后 `renameSync` 原子切换。
  - 证据：`test_release_frontend_pipeline.py` **4 passed**；前端构建管线/预算选集
    **13 passed**；`npm run build:verify` 完整通过（Vite 14,747 modules、预算通过、
    构建产物 smoke 通过、verified artifact 已原子发布）
- [x] 19. CI 覆盖 spec/**，将本批安全、runtime import、迁移完整性测试接成阻断门
  - 证据：`ci.yml` / `governance-checks.yml` 的 `'spec/**'` 触发在 HEAD，
    `test_ci_push_runs_for_spec_branches` passed；`test_release_runtime_import_closure.py`、
    `test_release_lazy_import_closure.py` **本轮实测 passed**

## G. 验收

- [ ] 20. 后端相关单元/端点测试、前端相关 vitest、类型与 runtime import 通过
  - 后端已过：本轮 10 个文件 **71 passed**；`import app.main` 成功（**2628** 条路由）
  - 前端已过：release-blocker 相关 10 个前端用例 + 2 个构建管线用例，
    **12 files / 101 passed**；`npm run build:verify` 完整通过。
  - 类型检查：本轮文件无新增错误。`typecheck-region` 仍报 **12 条 HEAD 既有错误**：
    `ConsolFormulaManagementPanel` 2、`FormulaManagerDialog` 4、`FormulaRefPicker` 1、
    `useEntrySyncReadiness` 2、`usePlatformAiChat` 2、`ThreeColumnLayout` 的
    `sync.completed` 事件联合类型 1。后者在本轮基线 `989010f42` 已存在；本轮动态 Dsh
    组件首次引入的类型错误已修复。因全量类型检查未全绿，本项保持未勾
- [x] 21. 一次性 PostgreSQL 从空库跑全迁移并验证 V229/readiness；不写共享库
  - 证据（2026-11-05，随机临时库 `gt_stage0_mig_<12hex>`）：先按历史 V001 基线执行
    全部 ORM `create_all`（**365** 张表），再补 `service_identities.id` 的
    `gen_random_uuid()` default，最后由当前 worktree 的 `MigrationRunner` 执行全部增量。
    严格递归导入 `app.models.*`，不把 `import app.models` 误当作全量注册：首次失败发现
    `extension_models.AccountingStandard` 未被聚合包导入，`Project.accounting_standard_id`
    的 FK 在 `create_all` 报 `NoReferencedTableError`；改为 `pkgutil.walk_packages` +
    `importlib.import_module` fail-closed 后通过。结果：磁盘 **251**、执行 **250**
    （V001 是 create_all 基线）、失败 **0**、pending `[]`、failure `[]`、checksum drift `[]`、
    `MigrationReadiness.is_complete=True`。进程 migration_state 标完成后真实调用 `/readyz`：
    **200** `{"status":"ready","degraded":false}`。finally 已 terminate 临时库连接并
    `DROP DATABASE` 成功；全程不触达 `audit_platform`
- [ ] 22. 独立端口浏览器验证登录、项目、TB、底稿、复核、报表、附注、trio 主链
  - [x] 22.1 无写入页面烟测（2026-11-05）：以【E2E】公式管理运行时门禁_2025
    (`b71db997-0bca-4528-9a03-0b92e6a6b4e0`，2025) 登录后完成项目、TB、底稿列表、报表、
    附注和交付中心加载。每次导航前拦截非 `GET/HEAD/OPTIONS` 请求；平台业务 API 实际请求均为
    GET，无 POST/PUT/PATCH/DELETE。TB 0 个科目、底稿列表 2 张、报表 129 行、交付中心完整性
    缺失空态均可见。附注无数据时 404 被页面接住，提示生成附注；已取消确认框，未生成。
  - [ ] 22.2 HTML 编辑、保存失败注入、OnlyOffice 往返、复核和 trio 生成会写入共享库【测试】项目；
    V250 迁移前置已解除，但仍须先取得用户明确授权。
- [ ] 23. 五角色复核、语义审查、INDEX 登记；同步最新远端后单 commit 与版本化推送
  - 本轮完成「单 commit + 版本化推送」与本文件回填；五角色复核与语义审查未做

## 外部停点

- [ ]* 24. 调查审计链 10 个分叉、重建膨胀索引与验证 invalid constraints（迁移应用部分已销案）
  - 2026-11-05 只读预检确认共享库 `schema_version` 已有 V235~V251、V261~V263，
    `schema_migration_failures=[]`，V250 相关列/约束与 vector 扩展均存在；**无需申请或执行共享库迁移写入**。
  - 发现既有 V233/V234 checksum 与候选树规范化 checksum 不同（登记保留旧值）；未修改共享
    `schema_version` 或 schema。若要校正这两条共享记账记录，须另备份、写回退 SQL 并单独取得用户批准。

## 范围外（本轮查证但未改，留给对应 owner）

- `batch-project-import-and-consol-tree-closure`（阶段 3）：`test_batch_project_security_closure`
  3 条、`test_batch_project_status_lock` 1 条、`test_group_topology_lock` 1 条失败。
  其中 `app.routers.batch_project` 缺 `with_status_lock_timeout`（守卫按名字 monkeypatch 即
  AttributeError）、500≠503、`empty_recycle_bin` 断言属真实脱节；另有 1 条是
  `MissingGreenlet`（隔离库下的连库假失败）。本轮未动其生产代码
- `DeliverableReadinessService._check_adjustments` / `_check_reports` 仍 override 父类含
  `content_digest` 的版本，口径不同且无测试覆盖，需 owner 裁定保留哪一套
