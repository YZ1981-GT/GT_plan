# 平台发布阻断项收口 — 设计

## 1. 基线与原则

候选树基于远端 `a142627c9`，在仓库根锁定的 detached worktree 中实施。主工作区的未提交文件不参与候选。修复采用“一个业务动作一个生产入口、服务只 flush、router 统一 commit、失败不清状态”的原则。

## 2. 前端启动与保存

- `ThreeColumnLayout` 将 `DshPanel` 改为 `defineAsyncComponent`，并仅在 `showDshPanel` 为真时挂载；错误组件局部显示“AI 助手加载失败”。
- `useAiNoteCapture` 恢复对话框所需的常量和 DTO 导出，并保留服务端消息 ID、幂等键与中文错误映射。
- `useWorkpaperAutoSave` 将保存回调改为 `Promise<boolean | void>`：仅 `!== false` 视为成功；每次编辑推进 epoch，回执只清除自己起点代际。
- `useEditorSave` 删除 `status < 600`，冲突取消不再解释为强制覆盖；成功回执校验 `success !== false`。

## 3. 复核编排

新增 `workpaper_review_submission_service`：

1. 按 `(project_id, wp_id)` 锁定底稿；
2. 要求 `edit_complete`；退回重提时将 rejected 状态在同一动作内归一到 `not_submitted`；
3. GateEngine、SoD、QC、批注、AI、复核意见任一检查异常均 fail-closed；
4. 通过后写 `pending_level1/under_review`，并同步程序实例；
5. 服务只 flush，不 commit。

单笔 router 与批量 router共用该服务。批量每稿一个 SAVEPOINT，逐项返回 submitted/skipped；跨项目 ID 统一按不存在处理。旧 `batch-status` 仅保留非提交类合法生命周期动作，`submit_review` 返回 410；旧 `workpapers/batch-submit` 返回 410。

复核状态服务在退回时直接归一为 `not_submitted + revision_required`，保留本次退回事实到专用字段/ReviewRecord；这样编制完成后可直接重提。末级通过后的写保护集中到现有 wp gate 的写动作判据，不依赖前端 readonly。

## 4. 安全边界

- Metabase 所有动态 URL 端点要求登录；项目参数转 UUID 后调用 `assert_project_permission(readonly)`，无项目仅 admin；签名密钥成为正式 Settings 字段，生产禁止默认值。
- 删除 main 中三个临时 debug route。
- ledger SSE generator 接收 project_id，查询 `id + project_id`。
- Review request DTO 不再要求 actor UUID；router 一律传 `current_user.id`，service 查询 `review_id + working_paper_id + !deleted`。
- review-config GET 用 readonly，PUT 用 edit + 全局角色；非法 level role 值拒绝。
- user-formulas/v2 三端点统一 410，直到持久化项目隔离版本另行交付。

## 5. 出具链

- 交付中心复用已有 trio API：readiness 通过后创建 trio job，继续使用 trio detail 轮询，不再调用旧 full endpoint。
- 旧 full endpoint 返回 410 和迁移指引，避免第三条影子入口。
- `ReportEngine.generate_all_reports` 的 TB 重算异常直接传播。
- 新增 `consol_note_export_adapter`：按项目口径解析模板，找到企业树根节点，读取 `(project, year, section, root_node_key)` 的 `ConsolNoteData`，构造导出器需要的章节对象。单体导出路径不变；合并项目若根节点或章节数据缺失则 fail-closed。
- readiness 按项目 scope 分流：单体读 `DisclosureNote/FormulaPushRun`，合并读 `ConsolNoteData/ConsolPushRun`。
- snapshot 对每个源加入稳定内容摘要及最后成功 run/version 标识。

## 6. 迁移与就绪

启动上下文保存迁移执行结果。`migration_mark_complete` 改为异步核对：磁盘版本集合减数据库版本集合必须为空，failure 表必须为空；否则抛出 critical 启动错误。reload worker 也执行这项只读核对。

`readyz` 读取迁移状态详情与 critical drift；存在阻断时返回 503。`health` 增加 `pending_versions`。V229 本身不改号，本批在一次性 PG 验证；共享库只在用户放行后执行。

## 7. 发布门

- CI push 分支增加 `spec/**`。
- package scripts补 `bundle:check`、`build:verify`、`preview:verified`。
- Vite `build.outDir` 消费 `GT_FRONTEND_OUT_DIR`。
- stable launcher 使用 `build:verify` 后再切换，并用 `preview:verified`。
- runtime import smoke、前端 build、迁移完整性均为阻断项；浏览器 smoke 无环境时继续诚实标 skip，但 release checklist 不允许以该 CI skip 代替预发验收。

## 8. 验证

验证分四层：纯函数/服务单测、FastAPI 端点测试、一次性 PG 迁移与状态机、独立端口浏览器 smoke。候选与基线按测试节点比对；已有红项不得归因给本批。所有写真库动作留到单独批准点。

---

## 9. 实施勘误（2026-11-05，platform-release-blocker-closure 收口）

> design §1~§8 写于 spec 起草时，基线记为 `a142627c9`。实施时发现本地落后远端 13 个提交，
> 若在旧基线重做会重复实现远端 `bb29a49f6`(v1.0.80) 起已交付、并经 v1.0.126/127 修复的内容。
> 故**候选改基于远端最新 `65709f0b2`（tag v1.0.136）**，在仓库根锁定 detached worktree
> `tmp_platform_release_blocker_closure/verify_wt` 实施；基线 worktree `base_wt` 同一 commit。

### 9.1 已在远端交付、非本批 2/24 假红（实测确认）
§2（DshPanel 异步 + 局部失败态 / useAiNoteCapture 常量与 DTO / 自动保存 boolean+代际 / useEditorSave
删 `status<600`）、§3（`workpaper_review_submission_service` 单一入口 + 批量 SAVEPOINT + 旧两端点 410）、
§4（Metabase 鉴权 / debug route 删除 / SSE 绑 project / 复核意见 actor 取登录用户 / review-config 门 /
user-formulas v2 410）、§5 的交付中心 trio 切换与旧 full endpoint 410 —— 这些对应 tasks 3-7、10-14、
17-19，实测均已在 `65709f0b2` 存在，本批仅复核不重做。

### 9.2 本批实际新增/补齐
- **Task 9 终态冻结（新增）**：原 §3「末级通过后写保护集中到 wp gate 写动作判据」只覆盖部分路由。
  本批新增纯判据 service `workpaper_content_freeze`（`WorkpaperContentFrozenError` 继承 HTTPException→423、
  `assert_workpaper_content_writable` / `load_workpaper_status` / `acquire_project_bulk_content_lock`），
  并接入多个写入适配点（`_wp_gate.raise_if_workpaper_frozen`、`wp_sync_router._enforce_entry_edit_lock` +
  `WpGateVisibilityProbe` 真读 `WorkingPaper.status`、`repository.lock_workpaper` 同 `FOR UPDATE` 行读
  `to_jsonb(working_paper)->>'status'`、`excel_html` 5 处 legacy 写、attachments 5 个 OCR/删除/回滚端点经
  `attachment_access.assert_linked_workpapers_writable`、`entry_integration.make_bulk_preflight`、
  `formula_settings/domain_stores.WpStore`、`wp_structure.batch_generate`、OnlyOffice 回调协议例外返 200+error:1）。
  前端终态只读：`WorkpaperEditor.vue` 的 `effectiveCanEdit` 纳入 `review_passed/archived` +
  `useEditorToolbar.ts` 写动作 `requireEdit` + 新建 `WorkpaperFrozenBanner.vue`（因行数门从 EditorBanners 抽出）。
  **裁定：内容写端点统一 423（`SyncWorkflowLockedError` 映射 423）；`ActionNotPermittedError` 仍 403。**
  按此更新 3 个旧测试口径（403→423），拒绝把实现降级回 403。
- **Task 15/16 补齐**：删 `DeliverableReadinessService` 的 `_check_adjustments`/`_check_reports` 子类 override，
  六源统一走 `deliverable_readiness_sources.ReadinessSourceChecks.content_digest`；`_check_adjustments` 改
  按分录组计数 + 全行摘要 + `line_count`。§5 的 `consol_note_export_adapter` 已在远端存在。

### 9.3 §3 口径裁定：edit_complete vs draft 直提
§3 写「要求 `edit_complete`」。实测远端 `workpaper_review_submission_service` 即按此：提交复核前底稿须
`edit_complete`，退回（rejected）在同一动作归一到 `not_submitted` 后方可重提。**保留 edit_complete 前置**，
不放开 draft 直提（draft 直提会绕过编制完成这一必要状态）。`test_workpaper_review_lifecycle_pg.py` 覆盖
退回→编制完成→重提→L1 manager→L2 partner→L3 qc、EQCR 被拒、并发内容写与终态按锁串行。

### 9.4 §6 口径裁定：Task 21「当前全部迁移」
§6 写「V229 本身不改号，本批在一次性 PG 验证」。实测远端迁移已推进到磁盘 252 / 库登记 254，V229 早已落库，
当前最高 V264。故 Task 21 的一次性 PG 验证口径改为**从空库跑「当前全部迁移」**（CREATE_ALL 365 表、
磁盘迁移 252 执行 251 失败 0、pending=[]、failures=[]、checksum drift 全部已登记解释、V229+V264 均登记、
readiness.is_complete=True、/readyz=200），而非只验 V229 单条。一次性库 `gt_release_blocker_*` 用后即 DROP，
**未写共享库**。

### 9.5 Task 24 外部停点（调查完成，执行待批准）
审计链「10 个分叉」实测已于 2026-11-04 由 11 条 `audit.fork_ack` 全部确认（当前每条链恰一个未确认链尾、
无阻断），**无待办**。迁移 pending=0/failures=0/漂移全部已登记解释（本批新登记 V233/V234 两条 checksum
漂移，逐对象核验在库全部生效、仅 V234 函数注释版本号文字未生效，纯文档不补迁移）。10 条 NOT VALID 约束
现有数据 0 违反（VALIDATE 安全）、3 个膨胀索引（invalid index=0）。VALIDATE 与 REINDEX 属共享库 DDL 写，
整理为 `task24-change-order.md` 待用户逐项批准，本批不执行。

### 9.6 Task 22 诚实状态
- Dev 模式渲染正常：共享 dev server（127.0.0.1:3030，vite dev）登录页表单完整（用户名 / 密码 / 登录按钮齐全）。
- 🔴 **生产构建 `build:verify` 产物浏览器白屏（既有发布阻断项，非本批引入）**：用 `preview:verified` 预览
  候选 `.verified-dist` 登录页，`vendor-core-*.js:30:11317` 抛 `Uncaught ReferenceError: Cannot access 'Rt'
  before initialization`，根组件未挂载即白屏。**在干净 base worktree（远端 HEAD、无本批改动）重建 `build:verify`
  并以同样方式预览，登录页报完全相同的错**（chunk hash 不同，符号 `Rt` 与位置 `30:11317` 一致）⇒ 远端 HEAD
  65709f0b2/b05f12995 既有的生产构建 vendor-core 分块（TDZ 循环初始化）缺陷，与本批 35 个改动文件无关
  （均不触及 vendor-core = vue/element-plus/pinia/vue-router，`vite.config.ts` 与 base 逐字节相同）。
  `build:verify` 的 smoke（`smoke-built-artifact.mjs`）只校验产物文件 / 动态块 / 代理可达、不在浏览器执行 JS，
  故未捕获此运行时错误。修复须重排 `heavyFeatureChunk` 的 vendor-core 分组，而 `vite.config.ts` 注释已明确
  「拆成 core/ui 会形成 Element Plus → Vue 的循环 chunk」⇒ 高 blast radius，属独立聚焦工作，不在本批 24 项
  （Task 18 口径 = build:verify / preview / package scripts 与 Vite outDir **存在且可运行**，这些已满足）内冒险改。
  **建议另立 spec 修 vendor-core 分块并给 smoke 增加无头浏览器执行步**（否则生产白屏对 smoke 不可见会复发）。
- 因上条，生产构建的只读浏览器 smoke（登录 / 项目 / TB / 底稿 / 复核 / 报表 / 附注 / trio readiness）无法在
  候选 verified-dist 上执行；终态冻结（本批核心）由后端真 PG `test_workpaper_review_lifecycle_pg.py` +
  一次性库 `PARTIAL_STATUS_STUB=OK` + 守卫 `test_workpaper_terminal_freeze_guard.py`（17 passed）覆盖，前端
  只读 / 冻结横幅由 vitest（`WorkpaperFrozenBanner.spec.ts` / `WorkpaperEditorShell.spec.ts` / `useEditorToolbar.spec.ts`
  隔离 54 passed）覆盖。
- 写入型（复核 / trio / HTML 保存）需用户授权写共享库【测试】项目后才做。
- OO→HTML 往返依赖上游 `wp-sync-conflict-adjudication-and-d4-32-modeling`：其代码已在 v1.0.136，但 Task 12
  真库 UAT 与 definition re-provision 未执行 ⇒ 仍无可通路径。本项如实标未完成 + 登记依赖。

### 9.7 终态冻结读取对 V151 隔离桩的兼容（收尾修复）
`workpaper_content_freeze.load_workpaper_status` 初版用 `sa.select(WorkingPaper.status)`，而
`workpaper_sync` 的隔离测试桩手工 `CREATE TABLE working_paper (...)` 常刻意只建 id/project_id/revision
（`aos8_endpoint_world`、`test_first_publication_on_demand_pg` 等），缺 status / is_deleted 列 ⇒ 运行时
`UndefinedColumn`。已与 `repository.lock_workpaper` 统一为安全读法：PostgreSQL 走
`to_jsonb(working_paper)->>'status'` / `->>'is_deleted'`（缺键返回 NULL，按非终态 / 未删除处理），SQLite
仍走 ORM `select(status)` 路径（普通单测 schema 含该列、且 PG 专有 `to_jsonb` 不能进 SQLite）。新增四条回归：
mock 缺列桩可写、SQLite 不走 to_jsonb、已删除行在冻结判据外、真 PG 一次性库建缺列桩实测可写
（`PARTIAL_STATUS_STUB=OK`）。

---

## 10. 五角色复核与语义审查（2026-11-05 收口）

### 10.1 语义审查（主会话执行；semantic_reviewer 子代理工具当次报错 `e.filter is not a function`，改由主会话逐关注点审）
本批语义审查是实质产出，按关注点组织，抓到并处置如下（非语法级）：
1. **终态冻结读取对隔离桩缺列不安全（已修）**：`load_workpaper_status` 初版 `sa.select(WorkingPaper.status)`，
   而 `workpaper_sync` 隔离桩手工建的 `working_paper` 常缺 status/is_deleted 列 ⇒ 运行时 UndefinedColumn。
   改为与 `repository.lock_workpaper` 同口径：PG 走 `to_jsonb(working_paper)->>…`（缺键 NULL=非终态/未删除），
   SQLite 走 ORM。真 PG 一次性库建缺列桩实测 `PARTIAL_STATUS_STUB=OK`。
2. **终态集合比平台既有冻结定义更窄（已修，铁律㉗）**：平台 `formula_push.engine.FROZEN_WP_STATUSES` +
   bulk_tab / workhour_approval / wp_prerequisite_status / wp_mapping 共 5 处把 **4 个**值当冻结 / 完成态
   （review_passed / archived / review_level1_passed / review_level2_passed），我的 `TERMINAL_CONTENT_STATUSES`
   与 `lock_workpaper` 只用 2 个 ⇒ 被 formula_push 视为冻结的旧值底稿仍可经内容写端点改写。已把 4 值冻结定义
   收敛为基础模块 `workpaper_content_freeze` 的**单一来源**（方向正确：formula_push 等是上层），`lock_workpaper`
   引用之，并加跨模块一致性守卫 `test_terminal_set_matches_platform_frozen_status_definition`（断言本集合值集
   == `FROZEN_WP_STATUSES` 键集，任一侧漂移即红）。现查共享库活跃底稿全 3820 draft、无这 4 态，故今日零行为变化、
   只消除潜在越写。
3. **生产构建 vendor-core TDZ（既有，非本批，已记 §9.6）**：base worktree 重建复现，honest 登记而非掩盖。
4. 锁顺序：`load_workpaper_status(for_update)` 与 `lock_workpaper` 都按 advisory(`workpaper_sync:{wp_id}`)→row
   FOR UPDATE；批量 `acquire_project_bulk_content_lock(workpaper_bulk:{project_id})` 在逐稿锁之前，WpStore 多目标
   按 `sorted(wp_ids, key=str)` 固定序，无交叉死锁。
5. 绕过面：内容写入口（dedicated 路由 / legacy excel_html 5 处 / attachments OCR 5 端点 / formula 项目写 /
   batch_generate / sync 编辑入口 / OO 回调）全部经冻结判据，守卫 `test_all_primary_content_choke_points_*`
   / `test_attachment_content_mutations_*` / `test_legacy_excel_html_*` 逐处 AST 断言。
6. 状态码分型：终态 423（`SyncWorkflowLockedError`）、权限不足 403（`ActionNotPermittedError`）、不可见 404
   三者清晰分型；OO 回调按协议例外返 200+error:1。

### 10.2 五角色复核
- **业务合伙人**：复核通过 / 归档后内容冻结符合审计底稿完整性；423 文案「请先按流程创建新修订」给出正确出路。
- **现场经理**：仅终态触发，draft/edit_complete/under_review/revision_required 仍可写；退回（revision_required）
  重开编辑，不阻断在途工作。
- **质控（QC）**：所有内容写入口 fail-closed；advisory+row 锁串行化「冻结判定」与「状态流转」，无竞态；
  跨模块一致性守卫防冻结集合漂移。
- **审计助理 / 现场**：由真 PG 生命周期（退回→编制完成→重提→L1/L2/L3 + EQCR 拒）+ 一次性库 + 守卫覆盖，
  证据可复现；迁移漂移 V233/V234 逐对象核验在库全生效。
- **EQCR 技术复核**：to_jsonb 安全读 / 方言分支 / 单一来源终态集合 / 无 import 环（freeze 为基础层）；
  既有 vendor-core TDZ 诚实暴露并建议另立 spec，不在本批高 blast radius 冒险改。

## 11. Task 24 执行与 Task 22 写入型 UAT（2026-11-05，用户授权后执行）

> 证据分级：**【第一手】**=本会话（v1.0.139 这一轮）亲自跑 / 查到的输出；**【引用】**=前序 turn / Task 21
> 的结果，本会话未重跑，不冒充亲验。

### 11.1 Task 24 共享库 DDL —— 已执行，本会话第一手复核
VALIDATE 10 约束 + REINDEX 3 索引由 apply 脚本（`tmp_release_blocker_apply/apply_validate.py`、
`apply_reindex.py`；Python asyncpg 写连接，REINDEX 走 autocommit 非事务块）在前序 turn 执行。本会话用
**只读** MCP 现查复核（2026-11-05）：

- **【第一手】** 10 条目标约束（`ck_adjustment_entries_nonnegative` / `_one_side`、
  `ck_adjustments_audit_phase` / `_content_revision`、`fk_evidence_links_wp` / `_attachment`、
  `chk_extraction_log_fill_mode` / `_status` / `_type`、`fk_extraction_log_user`）全部 `convalidated = True`；
  public schema 剩余 NOT VALID 约束 = 0。
- **【第一手】** 3 索引 `indisvalid = indisready = True`；public schema `*_ccnew` 残留 = 0、invalid 索引 = 0。
- **【第一手·尺寸真相，不粉饰】** `tb_aux_ledger_pkey` 现 **470 MB**（变更单实测基线 602 MB，回收约 132 MB，
  但**未达**变更单 pgstattuple **估算**的 183 MB）；`idx_tb_aux_ledger_active_window` 现 **1799 MB**、
  `idx_tb_ledger_active_window` 现 **660 MB** —— 两个 window 索引**基本原地不变**（变更单估算要降到
  368 / 129 MB 属乐观估计，实际并不膨胀）。
  ⇒ 诚实结论：REINDEX 三条都成功执行且无 `*_ccnew` 残留、索引全有效；但**只有主键索引有实质回收，
  两个 window 索引重建无害、几乎零收益**。不写成「膨胀整体下降」。

### 11.2 Task 22 写入型主链 UAT —— 四重证据（分级）
- **【第一手】①** aos8 真 HTTP：`test_aos_adopt_endpoint_http.py` **13 passed**（共享 PG 隔离 scratch schema，
  真 `wp_sync_router` + `ResponseWrapperMiddleware`）。workflow_locked → **423** `sync_workflow_locked`，
  digest 正向采纳成功写审计链。修前 4 failed 分两类：**我的下游漏改 2 处**（可达码集合断言 + 五分支码序断言
  仍写 403，而本批 Task 9 已把 `SyncWorkflowLockedError` 的 guard 映射 403→423）；**既有 harness 2 处**
  （`aos8_endpoint_world.py` 的 `STUB_DDL` 由 spec `workpaper-multi-window-lock-gaps`（commit 6de7b67dd）
  维护、漏建 `audit_chain_head` 伴生表，digest 正向路径写审计哈希链时 UndefinedTable）。两类均在本 commit 修。
- **【第一手】②** freeze 逻辑：`test_workpaper_terminal_freeze_guard` + `test_release_readiness_content_snapshot`
  **31 passed**（无需 DB）。
- **【第一手】③** 共享库 public schema freeze 探针（`tmp_release_blocker_apply/freeze_probe.py`，回滚事务）：
  对现有【测试】项目一个 draft 底稿，逐个翻成 4 个终态调真 `assert_workpaper_content_writable(for_update=True)`
  —— 全部抛 **423**（中文冻结消息正确）、draft 放行；走完整 advisory xact lock + FOR UPDATE 路径；
  **回滚后状态复原 draft，零残留、零审计链写入**（全程不经复核服务）。验证的是真 `working_paper` 表 /
  真 `WpFileStatus` PG 枚举（aos8 用 STUB schema，此探针补上真实 public schema 维度）。
- **【引用·本会话未重跑】④** 全复核链→终态→423：依据 Task 21 一次性库回归「90 passed 含 lifecycle」
  （前序 turn 记录，本会话未复现其输出）；`test_workpaper_review_lifecycle_pg.py` 自带
  `_require_disposable_database` 守卫，**禁止对共享库跑**（防追加型 `audit_log_entries` 哈希链被测试数据
  污染）。本会话未重建一次性库重跑，理由：本 commit 的 5 处改动全是测试文件（aos8）+ 1 处 endpoint_guard
  消息字符串（cosmetic），**均不触及复核服务 / freeze 服务的生产逻辑**，该链行为相对预推送未变。

### 11.3 本 commit（v1.0.139）的 2 个代码文件改动
- `app/services/workpaper_sync/endpoint_guard.py`：`SyncWorkflowLockedError` raise 消息里的「403」→
  「423 Locked」（Task 9 把 guard 映射改 423 后遗留的陈旧文案；其余「403，与 404 分型」是真正的 403
  授权拒绝 = ConflictResolution / Materialize / ScopeAuthorization，保持不动——grep 确认无测试断言该文案）。
- `tests/workpaper_sync/test_aos_adopt_endpoint_http.py`：① 可达码 `named` {401,403,409,422}→
  {401,409,422,423}、`extra` [404,500,503]→[403,404,500,503]（403 从命名 AC 退为通用
  `SyncActionForbiddenError` 一支）；② 五分支码序 [401,403,…]→[401,423,…]；③ import + 建 `AuditChainHead`
  伴生表（修既有 harness 缺陷，使 digest 正向控制真正跑通）。

### 11.4 诚实登记：仍未完成（非假绿）
- 浏览器**生产构建** smoke：vendor-core TDZ（`Rt before initialization`）既有缺陷阻断（§9.6），Task 22 标 `[ ]*`。
- OO→HTML 往返：上游 `wp-sync-conflict-adjudication-and-d4-32-modeling` Task 12 真库 UAT 未执行，无通路。
- Task 22 字面目标是**浏览器**验证主链；本会话完成的是**后端写入型 HTTP + 探针**维度，浏览器维度仅 dev
  登录页可渲染、生产构建受阻，故整条仍标 `[ ]*`。

### 9.6 追加（2026-11-11）：生产构建白屏已由后续 spec 修复
- 白屏根因与修复见 `frontend-prod-build-white-screen-closure`：①`vendor-core` 反向 import 入口 `index`（element-plus 传递依赖与 CJS 辅助落在 index）②`WorkpaperEditor ↔ heavy-univer` 懒加载环（Univer 第三方依赖落在编辑器块，打开底稿编辑器报 `Cannot access 'Kp' before initialization`）。两处均已改 `heavyFeatureChunk` 分组修复。
- 修复后 `build:verify` 通过（预算、严格无环、浏览器首屏 smoke），并在独立端口对【测试】项目只读走查登录 / 试算表 / 报表 / 附注 / 底稿列表 / 底稿 E1 编辑器，console error 为 0。
- 本 spec Task 22 于 **2026-11-16 补做完成**（16/16 通过，见 §12）：生产构建首屏与底稿编辑器重块均已实测正常，
  trio readiness 在生产构建下返回六源结构与内容摘要。仍未覆盖的仅「复核→终态链的浏览器**写入型**走查」与
  「OO 往返的本 spec 视角复测」（上游 spec 174 已独立实测），如实登记在 §12.6。

---

## 12. Task 22 浏览器主链走查补做（2026-11-16，归档前收口）

> 背景：spec 实施期（2026-11-05）Task 22 标 `[ ]*`，理由是「浏览器生产构建 smoke 与 OO→HTML 往返仍外部阻断」。
> 归档前复核发现**两个阻断均已由后续 spec 解除**，故按「`*` 任务也要做」补做，不再以旧阻断为由挂账。

### 12.1 阻断解除的两条证据
1. **生产构建白屏**（原 `vendor-core:30:11317` TDZ `Cannot access 'Rt' before initialization`）：
   `frontend-prod-build-white-screen-closure`（`_archive/160-…`，7/7）已修两处环并给 smoke 加无头浏览器步 ——
   ①`vendor-core` 反向 import 入口 `index`（element-plus 传递依赖与 CJS 辅助落在 index）；
   ②`WorkpaperEditor ↔ heavy-univer` 懒加载环（Univer 第三方依赖落在编辑器块，打开编辑器报 `Cannot access 'Kp'`）。
2. **OO→HTML 往返**：上游 `wp-sync-conflict-adjudication-and-d4-32-modeling`（`_archive/174-…`）的 Task 12 真库 UAT
   与 12.e OO iframe 完整往返已于 **2026-11-15** 实测通过（三方一致 / 冲突 0 / A 列序号保留）。

### 12.2 环境与方法
- 干净检出 worktree：`HEAD=6e6bc5dc8` / `tree=de87804f4`（不参与主工作区的 32 个脏文件）。
- `npm ci --prefer-offline` 装独立依赖（不建 node_modules 联接，避免 vitest / vite 双实例与联接误删）。
- `npm run build:verify`：vite 生产构建 → 包体预算 `--check` → **`check-chunk-cycles --strict`** → built smoke
  （含 `smoke-browser-mount.mjs` 无头浏览器首屏挂载断言）→ 发布 `.verified-dist/<manifest-sha256>`。
- `preview:verified` 起独立端口 **3041**，`VITE_API_BASE_URL=http://127.0.0.1:9980` 同源代理到共享后端（只读）。
- Playwright chromium 无头浏览器，1600×1000；采集 `console` error 与 `pageerror`。
- 导航用 `domcontentloaded` 而非 `networkidle`：工作台 / 交付中心带 SSE 与轮询，网络永不 idle（这是探针口径，
  不是页面缺陷；首轮误用 `networkidle` 导致 90 秒超时）。

### 12.3 build:verify 结果（全绿）
| 项 | 结果 |
| --- | --- |
| vite 生产构建 | 3m48s，14828 modules transformed |
| 入口 gzip | **566,436 B**（预算通过） |
| chunk 静态 import 图 | **2501 块，严格无环** |
| built smoke | 通过（主页 / SPA 深链 / 动态块 / API 与 WOPI 代理） |
| 浏览器首屏挂载 | 通过（`smoke-browser-mount.mjs` 默认不跳过，仅 `GT_SMOKE_SKIP_BROWSER=1` 才跳过并告警） |
| 验证产物 | `.verified-dist/c851dacdb880f9eb28e3c0b84df1b08c8e6d242358a4a2a22924d3d1de21c793` |

### 12.4 浏览器走查 16/16 通过（`ok=true`）
项目：【测试】公式同步甲有限公司_2025（`4c77f3e8-…`，15 份底稿）。

| # | 项 | 结果 |
| --- | --- | --- |
| 1 | 生产构建首屏挂载 | `#app` children=1（**白屏已消**） |
| 2 | 登录页表单完整 | inputs=2 |
| 3 | 登录成功并跳转 | `/` |
| 4 | 项目列表 | len=728，含【测试】 |
| 5 | 项目工作台 | len=281，newPageError=0 |
| 6 | 试算表 | len=8788，newPageError=0 |
| 7 | 报表 | len=3432，newPageError=0 |
| 8 | 附注 | len=769，newPageError=0 |
| 9 | 底稿列表 | len=500，newPageError=0 |
| 10 | 调整分录 | len=623，newPageError=0 |
| 11 | 交付中心 | len=351，newPageError=0 |
| 12 | `/api/health` | 200 |
| 13 | trio readiness 端点 | 200（见 §12.5） |
| 14 | 底稿编辑器（D1-1 应收票据审定表） | len=1450，`heavy-univer` 重块动态加载正常（**原 `Kp` TDZ 已消**） |
| 15 | console error | **0**（排除资源 404） |
| 16 | pageerror | **0** |

### 12.5 trio readiness 实取证据（Task 15/16 在真实栈生效）
`GET /api/projects/{pid}/deliverables/trio/readiness?year=2025` → **HTTP 200**，返回六源结构与逐源 `content_digest`：

```
data.status = "blocked"
data.sources = { dataset{available:false, content_digest:4f53cda1…},
                 tb{available:true, count:174, content_digest:e5ff19fc…},
                 formula_push{available:true, count:88, run_id:93f7fc14…}, report…, notes…, adjustment… }
data.hard_blockers = [ {code:"stale_source", component:"financial_report",
                        evidence:{stale_count:9,total_count:258,calc_error_count:7}},
                       {code:"stale_source", component:"disclosure_notes",
                        evidence:{stale_count:165,total_count:199}} ]
```

两点结论：
1. **六源统一 + 内容摘要在生产构建下真实生效** —— 正是 Task 15（删子类 override、六源走
   `deliverable_readiness_sources.ReadinessSourceChecks.content_digest`）与 Task 16（snapshot 纳入内容/版本摘要）的交付面。
2. `status=blocked` 是**业务正确行为**，不是缺陷：该【测试】项目报表 9/258 行过期（其中 7 行计算失败）、
   附注 165/199 章 `is_stale`，readiness 如实阻断出具而非假放行 —— 这正是 R5「出具权威源」要的 fail-closed。

### 12.6 复核→终态链浏览器写入型走查（2026-11-16 补做，10/10 通过）

> 12.5 之前此项登记为「未覆盖」。归档后按用户「这个你也要完成」补做，已全通过，故改写本节。

**方法**：方案 A —— 用 admin 走完整链（`assert_review_level_actor` 对 admin 直接放行，是设计内的应急通道），
不做完整角色矩阵（「角色不匹配被拒」已由真 PG `test_workpaper_review_lifecycle_pg.py` 的 EQCR 被拒用例覆盖）。

**环境**：共享开发环境（前端 3030 / 后端 9980），Playwright chromium 无头浏览器，真实 UI 打开底稿编辑器 +
真实 HTTP 写 + 真实 PG 落库。目标：【测试】公式同步甲有限公司_2025（`4c77f3e8`）的 D1-1 应收票据审定表
（`9af57e14`）。

**最小数据准备**（备份后仅两项，均走查后回滚）：
① `working_paper.reviewer` = admin（原 NULL）；② 插一条 `wp_qc_results`（`blocking_count=0` / `passed=true`）。
未改 `review_config` / `manager_id` / `partner_id`，未启用任何停用账号。

**10 步全部通过**：

| # | 步骤 | 结果 |
| --- | --- | --- |
| 1 | 登录 | 成功 |
| 2 | 底稿编辑器打开（真实 UI） | len=1418 |
| 3 | 提交前状态 | `draft` / `not_submitted` |
| 4 | **旧 `batch-status` 的 `submit_review`** | **HTTP 410**（R3.3「不得假成功」实测生效） |
| 5 | **唯一提交入口 `working-papers/batch-submit`** | HTTP 200，`submitted=1 skipped=0` |
| 6 | 提交后状态 | `under_review` / `pending_level1` |
| 7 | **L1 通过**（`batch-review` action=approve） | HTTP 200 `success_count=1` → `pending_level2` |
| 8 | **L2 通过** | HTTP 200 `success_count=1` → **`review_passed` / `level2_passed`（终态）** |
| 9 | 🔴 **终态内容写 `PUT /api/workpapers/{wp}/checklist-responses`** | **HTTP 423**（终态冻结真实生效） |
| 10 | 前端刷新后的提示 | 命中「复核通过」「只读」 |

**端点口径（现查 openapi 纠正，供后续复用）**：
- 提交复核：`POST /api/projects/{pid}/working-papers/batch-submit`，body `{wp_ids:[...]}`（**不是** `batch-status`，
  后者对 `submit_review` 返回 410）。
- 层级通过：`POST /api/projects/{pid}/batch-review`，body `{wp_ids, action:'approve'|'reject', comment}`，
  回执判据是 **`success_count`**（不是 `approved`/`passed`）。逐张走 `WorkingPaperService.update_review_status`
  （F8 配置驱动状态机，层级数由 `project.review_config.levels` 决定，None ⇒ 默认 2 级）。
- ⚠️ `POST /api/workpapers/{wp}/review` 是**单底稿 AI 复核**（会写 `ai_content` 的 `review_finding` 并生成
  `checklist_responses` 的 `D1-review-session-*` 行），**不是**状态流转端点 —— 走查时误用过一次，副作用已清理。
- ⚠️ `POST /api/workpapers/{wp}/review-sign` 是**复核签字表**（需 `project_id` + `wp_code` + 复核模板），
  action 取值是 `pass|reject`；该项目无复核模板 ⇒ 422「未知复核模板」，与本链无关。

**回滚与对账（CLEAN）**：
- 目标底稿逐字段零漂移：`status=draft` / `review_status=not_submitted` / `reviewer=NULL` /
  `workflow_status=draft`（与备份 `backup_before.json` 完全一致）。
- 备份时已知 22 份底稿状态变化 **0 份**。
- 本走查直接触碰的表全部归零：`wp_qc_results=0` / `review_records=0` / `checklist_responses(该底稿)=0` /
  `pending ai_content=0` / `procedure_instances(该项目)=0`。
- 清理的自身副作用（逐项登记）：1 条 `uat-probe` checklist 行、3 条误用 `/review` 产生的 `review_finding`、
  3 条 `D1-review-session-*` 复核会话行、76 条 `procedure_instances`（打开 A1 程序表触发的自动生成）、
  1 份 A1 底稿（`0630aca0`）。
- 已知环境噪声（不属本走查、未触碰）：并发会话在 11:25 新建了底稿 `cfa1edae`。

**仍未覆盖（如实登记）**：
- **完整角色矩阵**：本走查用 admin 应急通道走通，未用真实 manager/partner/qc 账号逐级验证
  「角色不匹配被拒」（该负向路径由真 PG lifecycle 用例覆盖，浏览器层未重复）。
- **退回→修改→重提闭环的浏览器层**：后端已由 `test_workpaper_review_lifecycle_pg.py` 覆盖，
  本走查聚焦「提交→逐级通过→终态→423」主链。
- **OO 在线编辑 iframe 的本 spec 视角往返**：上游 spec 174 已于 2026-11-15 独立实测通过，本 spec 不重复。

### 12.7 `/readyz` 503 已修复（V273 漂移登记，2026-11-16）

12.6 原记「`/readyz` 503 属范围外」。归档后已实际修复：按 `migration_drift_ledger` 的处置顺序先现查真库
逐对象核验 V273 的编辑内容**全部已在库生效**（三列 / 外键 `convalidated=True` / CHECK
`ck_wpsc_abandon_triplet` `convalidated=True` 且定义与文件逐字一致 / 三列注释齐备 / 数据面 392 行中 283 行
已带 `abandoned_at`）⇒ **无需补迁移**，按 V248/V249 同型先例登记到 `app/core/migration_drift_ledger.py`，
不改写共享 `schema_version` 的应用时 checksum。验证：`test_migration_drift_ledger.py` 62 passed、
`test_migration_integrity_pg.py` 17 passed；**变异证明**摘掉 V273 登记后
`test_no_unexplained_checksum_drift` 精确打红 `[('273','c5a…','608d…')]`，逐字节还原 sha256 一致
⇒ 判据非恒绿。推送 `v1.0.281`。

🔴 剩余未决（非本 spec）：`/readyz` 仍报 `pending_versions=['274']` —— 另一会话未跟踪的在途迁移
`V274__workpaper_legacy_drain_ledger.sql`（其 SQL 中文已损坏：699 个 `?` / 0 个 CJK 字符），属
`onlyoffice-sheet-open-via-published-artifact` Task 4.2，交该 spec 作者补齐后执行。
