# 交付件回填 / 在线编辑保存 / 签发清单完整性 — 任务清单

> 约束：先复现后修复；改一处跑相关回归 + 变异；真库只在事务内验证并回滚；并发会话未提交文件（`note_project_realign_apply.py`、
> `test_note_project_realign_backup_pg.py`、`components.d.ts`、`backend/scripts/analyze/_wr_*` 等）不碰；service 只 flush、router 提交；
> 提交前问用户。

## Phase A 签发一致性清单
- [x] 1. 真库复现：四个真实项目在事务内调用现有 `generate_checklist`，记录「暂不可用」项数与 `can_signoff`。
  - 证据：修前四项目均 `can_signoff=True`，各只返回 5 个 info（试算表 / 调整 / 底稿 / 报告 / AI 均「暂不可用」）；探针在仓库外。
- [x] 2. 重写检查框架：每项 `begin_nested`、失败 ⇒ blocking；六项检查按 design §1.2 口径改用真实 schema / 既有服务；中文意见类型标签。
  - 追加根因：真库 `ai_content_type_enum` 已有 `review_finding` 而旧 ORM 枚举未登记；展示查询改为 cast text，避免合法存量行触发 LookupError。
- [x] 3. 路由：`require_project_access("readonly")`（含 confirm-warning）；年度缺省按 ORM 五级解析，取不到 422；确认留痕失败返回 503，前端不假确认。
- [x] 4. 前端：签字页传 `:year`；`CATEGORY_LABELS` 补 `conflict` / `stale`；路由只用真实页面；请求 `_silent`。
- [x] 5. 表级契约 `_KNOWN_PHANTOM_DEBT` 删 `ai_generated_content` / `event_cascade_health`；鉴权基线现算未越界，无需调常量。
  - 全量表契约目前被并发会话 `note_project_realign_apply.py` 新增的 `json_populate_recordset` 假阳打红（函数式表源清单未同步），不碰并发文件；本 spec 两条 phantom 已清零。
- [x] 6. 测试：SQLite 12 passed；前端 10 passed；pg_only 2 passed（四真实项目六类检查全部执行 + PG 事务 abort 后 SAVEPOINT 恢复）；
  磁盘变异 `remove-savepoint` / `fail-open-info` 均被守卫打红，生产文件逐字节恢复。修后真库：安徽 9 info + 4 warning、其余三项目因无审计报告明确 blocking。

## Phase B 版本文件完整性
- [x] 7. V191 / R191 迁移 + ORM 列（versions 三列 + 唯一索引、section_state 四列、working_paper 两列）；本地库已手动落列（原 V189，2026-10-18 因并发会话占用 V189/V190 改号至 V191；列名未变，本地库已有列不受影响，迁移记录待全量重启补记 V191）。
  - 证据：information_schema 三表 9 列齐全；唯一索引存在；`SchemaDriftDetector.scan()` = 0 项 / critical 0；迁移同号守卫通过。
- [x] 8. `render_and_store`：任务行 `FOR UPDATE` 覆盖「取号→落盘→建记录」全段；`versioned_file_name` 剥 `_v\d+` 再追加；历史版本已认领路径拒绝覆盖。
  - 证据：连续两次用固定展示名生成，得到 `_v1` / `_v2` 两个文件且各自字节、SHA-256 不变；PG 双会话 lock_timeout 证明行锁真实阻塞。
- [x] 9. 下载 / 签名下载共用 `_verified_version_path`：指纹不符 409、缺失 404；`verify_version_immutability` 真校验；路由回执 `file_name` 取真实文件名。
- [x] 10. 测试：Phase B 本地 50 passed；PG 3 passed（历史 19 条共享路径版本 = 16 个 409 + 3 个可下载、行锁、唯一索引）；
  磁盘变异 `fixed-file-name-overwrites-history` / `download-skips-fingerprint` / `task-lock-is-plain-select` 全部被守卫打红并逐字节恢复。

## Phase C 在线编辑保存
- [x] 11. `handle_callback`：status 2+6 都落版本、`_parse_base_version` 校验回调体 key（无效 / 跨 task 写安全日志拒绝）、规范化后字节与最新版本
  同 hash 幂等、陈旧底版（底版后非本会话版本）仍保存并写 `deliverable_oo_stale_base_save` 审计、`base_version_no` / `oo_doc_key` 落库、
  `render_and_store(base_version_no=...)` 继承底版快照与 render_context。
- [x] 12. `_resolve_verified_editor` 两道闸：在册有效用户（未删除 + is_active）+ 项目权限同口径（admin 免成员表，其余查 project_users）。
- [x] 13. `onlyoffice_docx_normalize.normalize_onlyoffice_docx` 剥 numbering.xml 显式 false 的 `w:isLgl`，接入回调下载后；LibreOffice 复验真 v15「七、」。
- [x] 14. 回调路由席位释放集合改为 `{2,3,4}`（6=强制保存=仍在编辑，保持占用）。
- [x] 15. 版本链视图算 `base_version_no` / `overwrote_versions`，DTO additive 下发；`DeliverableVersionList` 显示「基于第 N 版编辑，覆盖了第 M 版」标签 + tooltip。
- [x] 16. 测试：`test_onlyoffice_callback_integrity.py`（status6 / key / 幂等 / 陈旧底版 / 会话内多次不陈旧 / admin+成员+停用+非成员编辑人 / 非保存 noop /
  席位 AST 契约）17 例 + `test_onlyoffice_docx_normalize.py`（含 LibreOffice 复验）；更新 55/isolation PBT 带 key；前端标签 vitest（32 例）。
  磁盘变异 6 处（status6 忽略 / key 不校 / 去幂等 / 陈旧不留痕 / admin 丢弃 / isLgl 不剥）全部被守卫打红并逐字节恢复。
  - 旁证：`test_property_54` / `test_unsupported_format_downgrade` 两条红在 HEAD 干净检出同样红（预存失败，非本轮引入，已用临时 worktree 核实）。

## Phase D 附注回填下线 + 报告正文保留 + 导出前一致性闸门
> 方向裁定（2026-10-17 用户确认）：附注是底稿单项推送的只读下游，交付中心禁止逆写附注；报告正文回填保留；
> 导出附注前列出与底稿不一致章节让用户确认或去同步。原「正文区书签 + 行级补丁 + 冲突裁决」整体不做。
- [x] 17. 附注回填下线：`supports_writeback("disclosure_notes")=False`（从 `WRITEBACK_SUPPORTED_DOC_TYPES` 移除）；
  `DeliverableWritebackService._resolve_adapter` 对 disclosure_notes 返回 None；删 `ASYNC_SECTION_THRESHOLD` / `_delegate_to_async_job`
  异步分支。
- [x] 18. 报告正文回填保留 + 路由补 commit：`audit_report` 路径不变，`/writeback` 成功后 `await db.commit()`，回执分组。
- [x] 19. `deliverable_note_consistency.check_note_consistency`：复用 `note_readiness_service.build_readiness` 的 `needs_sync` / `is_stale`，
  按 `selected_sections` 过滤，查询异常 fail-open 返回 consistent=True。
- [x] 20. `render_disclosure_notes` 接一致性闸门：请求体 additive `confirm_inconsistent`；不一致且未确认 ⇒ 不落版本、返回
  `requires_confirmation=true` + 清单；一致 / 已确认 ⇒ 照常导出带 `consistency` 回执。全套生成标记 needs_confirmation 不阻断其余步骤。
- [x] 21. 前端：附注交付件（`supportsWriteback=false`）不渲染回填面板、改渲染只读说明；生成附注响应 `requires_confirmation` 时
  `ElMessageBox` 列出 never_synced / stale 章节，「返回同步」/「仍要导出」（再发 `confirm_inconsistent=true`）。
- [x] 22. 测试：`test_deliverable_note_consistency.py`（从未同步 / stale / 全同步 / selected 过滤 / fail-open）；端点级（不一致未确认不建版本、
  确认后建版本、一致直接建）；能力矩阵（附注 False / 报告正文 True，/writeback 对附注 400）；前端 vitest（附注无回填按钮 + 确认框）；
  变异（闸门短路 / 附注 supports_writeback 改回 True）打红。
- [x] 23. 真库（事务回滚）：安徽附注 `check_note_consistency` 列出 never_synced / stale 章节。

## Phase E 列契约与溯源
- [x] 28. `test_raw_sql_unqualified_column_contract.py`（pg_only）+ 基线；现算违规清单逐条核调用链（活 / 死）。
- [x] 29. 修活路径高影响点（含 quality_score 两列已由 V191 补齐后的三个读方 / 两个写方实测），修一条删一条基线。
  - 活路径 3 条（Task 28 建基线时即修、从未入基线）：`export_integrity.py` 下载 `output_path→file_path`（原每次 GET 500）、
    `eqcr_shadow_compute_service._get_team_result` 借贷平衡 `trial_balance→tb_balance`（原 team 侧恒取不到值 / has_diff 恒 True）、
    `wp_quality_score_service.get_dashboard` 删死列 `wp_status`（原接线后首调 500）。逐条裁决见 design §10.1。
  - 修一条删一条守护：磁盘把 `file_path` 改回 `output_path` ⇒ `test_no_new_unqualified_column_violations` 立即打红报
    `🔴 export_tasks.output_path`；恢复后 7 passed，`git diff --stat` 空（逐字节还原）。
  - quality_score / procedure_completion_rate（V191 已补列，非无限定基线项）真库实测（事务内 + rollback，零落库，探针在仓库外 `d:\_wr29_probe.py`）：
    3 读方（get_dashboard 324 底稿 avg 0.0 / wp_health_dashboard AVG / calculate_score SELECT proc_rate）全部对真实 schema 有效；
    2 写方（calculate_score UPDATE quality_score 读回=47 / recalc_quality_score UPDATE 两列读回 (47,0.00)）事务内生效；
    rollback 后新会话读回 (NULL,NULL) 确认未落库。
  - 回归：`test_raw_sql_unqualified_column_contract` 7 passed（pg_only 真库，基线 ⊆ 现算 + 每条仍出现）；
    `test_eqcr_shadow_compute` 6 passed（`test_shadow_compute_basic` 旧断言 `has_diff is True` 建立在「team 查询恒失败」的 bug 上，
    修复后改断言 `team_result_snapshot is not None`（source=tb_balance）+ `has_diff is False`，顺带守护活路径修复）；
    `test_deliverable_version_file_integrity` + `test_wp_optimization_properties` 24 passed。
  - 死代码 / 守卫降级 / pgvector 条件路径保留基线（§9「只登记不删」），逐条调用链核实登记 design §10.1。
- [x] 30. `supports_lineage` 能力标志与面板文案；能力矩阵与门控守卫扩第三个标志。
  - 后端早已完整：`deliverable_capabilities.LINEAGE_SUPPORTED_DOC_TYPES = {disclosure_notes, audit_report}` + `supports_lineage()` + `lineage_unsupported_message()`；
    `DeliverableDTO`/`DeliverableDTOSchema` additive `supports_lineage`（默认 False，`deliverable_service` 由能力函数派生）；透传链
    `DeliverableCenter → OnlyOfficeEditor → LineagePanel` 已接。
  - 🔴 真实根因（非「旧文案未同步」）：`supportsLineage` 是 **Vue Boolean prop**，父组件不传时被 Vue 转换规则转成 `false`（而非 `undefined`），
    于是 `lineageUnsupported = props.supportsLineage === false` 恒真 ⇒ 面板把所有交付件当「不支持溯源」、`loadSections` 提前 return 不打
    /section-states。这正是原记录里 5 例红的机理（`LineagePanel.spec.ts` 未选章节/无锚点各 1、`LineagePanel.refresh.spec.ts` 刷新所有过期 2、
    `LineagePanel.autofollow.spec.ts` 多分隔符精确匹配 1）。修复 = `withDefaults(defineProps<…>(), { supportsLineage: true })`
    （缺省按支持 = 兼容旧后端；`=== false` 判据不变，`deliverableCapabilityGating` 的源码级断言仍绿）。
  - 守卫扩第三个标志：后端 `test_deliverable_capabilities_matrix.py` 已含 `supports_lineage` 三态值表 + `test_financial_report_never_lineage_capable`
    + DTO schema 字段断言（17 passed）；前端 `deliverableCapabilityGating.spec.ts` 已含 US-8 block（透传链 + `lineageUnsupported` 源码断言 +
    「缺省按 true」反向自检）。新增**行为级**守卫 `LineagePanel.spec.ts` 三例：supportsLineage=false ⇒ onMounted / onBookmarkDetected 都**不请求**
    /section-states（断言请求未发出，非只验文案）+ 显报表穿透文案；缺省（不传）⇒ 会请求 /section-states（守住 Boolean prop 转换坑）。
  - 变异（均逐字节恢复）：①后端把 `financial_report` 加进 `LINEAGE_SUPPORTED_DOC_TYPES` ⇒ `test_property_11[financial_report-…]` +
    `test_financial_report_never_lineage_capable` 2 例打红；②前端删 `withDefaults` 的 `supportsLineage: true` 默认 ⇒ `LineagePanel.spec.ts` 3 例
    （缺省行为 + 未选章节 + 无锚点）打红；③单区域 `tsconfig._lineage-panel-t30.json`（用完即删）注入 `number = string` ⇒ vue-tsc 报 TS2322。
  - 回归：前端 5 文件 91 passed（LineagePanel 3 文件 36 + capabilityGating 25 + lineageDisplay 27，其中 LineagePanel.spec 10 含 3 新例）；
    后端能力矩阵 17 passed；`vue-tsc -p` 单区域对 `LineagePanel.vue` 0 错。改动仅 `LineagePanel.vue` + `LineagePanel.spec.ts`，未碰并发会话文件。

## Phase F 收尾
- [x] 31. 全量相关回归 + HEAD 干净检出（临时 worktree）复跑守卫；文件行数门 / 迁移同号 / lazy import 守卫。
  - **后端回归**（HEAD=3e82df9bf，PG 健康 84 项目）：本 spec SQLite 套件 78 passed（signoff_service / version_file_integrity /
    onlyoffice_callback_integrity / onlyoffice_docx_normalize / note_consistency / note_export_gate / capabilities_matrix /
    writeback_receipt）；相邻套件 deliverable_onlyoffice+center_integration+hash_pbt+writeback_rowcount+untouched_blocks+
    writeback_target_adapters+full_deliverables_executor = **50 passed / 6 failed**；authz/schema 批 eqcr_shadow_compute+
    project_endpoint_authorization_baseline+phase8_endpoint_auth_fires+raw_sql_schema_contract = **42 passed / 1 failed**；
    pg_only 逐文件（跨文件 asyncio teardown 污染，须单跑）signoff_pg 2 + version_file_integrity_pg 3 + unqualified_column_contract 7
    = **12 passed**；本 spec 新增 `TestDisclosureNotesConsistencyFlag` 2 passed。
  - **前端回归**：vitest 6 文件 **101 passed**（LineagePanel.spec + .refresh + .autofollow、deliverableCapabilityGating、
    deliverableLineageDisplay、SignoffChecklist）。未跑全量 vue-tsc（OOM，memory ㉔）。
  - **文件行数门**：仅 `deliverable_service.py` 超限（924 splitlines > 800；HEAD 735，本 spec +170 = render_and_store 版本完整性
    收口 design §2.1~2.3，核心功能非冗余）⇒ 按既有白名单范式登记 `file_size_whitelist.txt` baseline 924（不加余量，再加一行即打红），
    `check_file_size.py` 对 14 个本 spec 后端文件 + 全部前端 .vue/.ts + 新建 note_* 服务全部 EXIT=0。
  - **迁移同号守卫**：V189/V190 = 并发 trio（已在 HEAD），V191 + R191 = 本 spec（untracked），**无重复版本号**；
    `test_migration_integrity_pg` 15 passed / 2 failed（见下预存）。
  - **lazy import 守卫**：`test_no_new_unresolved_lazy_import` **PASS**（本 spec 零新增幽灵引用）；全文件 8 passed / 1 failed（见下预存）。
  - **HEAD 干净检出（临时 worktree D:\_gt_head_wt @ 3e82df9bf）复跑** —— 所有红全部 **预存于干净 HEAD、非本 spec 引入**：
    | 红项 | 归因（clean HEAD 复跑结论） |
    |---|---|
    | `test_property_54_onlyoffice_unavailable_degradation` | 预存（Phase C Task 16 已记）；HEAD 同红 |
    | `test_full_deliverables_executor` 5 例（all_steps_succeed done=3≠4 / single_step / first_step / unadjusted_step / progress_increments） | 预存，HEAD 逐例同红；来自 HEAD 的 16b 合并提交。本 spec 对该文件只**新增** `TestDisclosureNotesConsistencyFlag`（2 passed），未改这 5 例 |
    | `test_raw_sql_tables_are_known`（`json_populate_recordset` 幽灵表） | 并发会话 `note_project_realign_apply.py`（已 staged、HEAD 含 2 处）；tasks.md Phase A #5 已记，不碰并发文件；HEAD 同红 |
    | `test_migration_integrity_pg::test_no_unexplained_checksum_drift` + `::test_checksum_comparison_actually_ran` | 活库对版本 **189**（并发 trio V189）校验和漂移、未登记 `KNOWN_CHECKSUM_DRIFTS`；与本 spec V191 无关；HEAD 复跑逐字同红（`assert [('189',...)]==[]`） |
    | `test_lazy_import_resolvability::test_baseline_has_no_zombie_entries` | 僵尸基线项 `phase5_f4_accounts_payable.py → phase5_f4_01_adjudication`（F 循环 workpaper-sync）；该 3 文件本 spec 未改、目标模块已在 HEAD ⇒ 基线陈旧，HEAD 即红 |
  - worktree 已 `git worktree remove --force` + `prune` 清理（`git worktree list` 仅余主树）；一次性探针（仓库外）已删。
  - 唯一改动：`file_size_whitelist.txt` +8 行（deliverable_service.py 登记）；未提交（Task 33 问用户）。未碰并发会话未提交文件。
- [x] 32. Playwright 实测（design §8）；LibreOffice 复验。
  - **环境**（2026-10-18，HEAD 工作树未提交 1-31 全部改动）：手动拉起 start-dev（后端 `run_uvicorn` :9980 冷启动跑迁移 applied_count=**191**、V191 已落、health=degraded 仅因并发会话 V189 checksum_drift（与本 spec 无关）、postgres/redis 均 ok；前端 vite 绑 `127.0.0.1:3030`——localhost 默认解析到 ::1 而浏览器取 IPv4，故显式绑 IPv4）；admin/admin123 登录（POST /api/auth/login 200）。实测项目 = **重药控股安徽有限公司_2025**（0ec33ac9，note/report/financial 三交付件齐全，即 v15 LibreOffice 夹具所在项目）。浏览器用 chrome-devtools MCP；进 OnlyOffice 编辑器只观察面板、**不输入不保存**，看完关闭，Playwright 旁路浏览器已 park about:blank。
  - **① 签字页清单显示真实阻断项**（design §1.2）✅：`GET /api/projects/0ec33ac9/signoff/checklist?year=2025` → 200，**13 项（info 9 + warning 4）全是真实 schema 口径**：trial_balance「196 科目审定数=未审+调整一致」、adjustment、conflict、report「意见类型：无保留意见」、4 条 warning（7 底稿过期 / 2 报表行过期 / 19 附注章节过期 / 138 条 AI 内容待确认）；**`hasOldDegradation=false`——全程无「暂不可用」info 降级项**（旧 fail-open 已消除）。注：`/partner/sign-decision/:pid/:year` 路由在未选项目上下文时被守卫重定向回项目页，故签发清单经 service 端点 + SignoffChecklist vitest（Task 6 前端 10 passed）覆盖，未在该路由页做可视渲染截图。
  - **② 交付中心生成两次附注→两版各自可下载（版本文件完整性）**（design §2）✅：交付中心「生成附注」经 API 两次 `POST …/disclosure-notes/render {confirm_inconsistent:true, selected_sections:['八、1','八、4']}` → **v17 / v18**，文件名 `disclosure_notes_2025_v17.docx` / `_v18.docx`（各带 `_v{n}`），两版 `download` 端点均 200、**内容哈希不同**（57e9b420 ≠ a2490cb2）、`content-disposition` 文件名与磁盘一致；DB 两行 file_hash 不同（ef1090… / c72d9a…）。另真库历史证据：共享文件名的被覆盖版本 **v6~v12 下载 409**「该版本文件已被后续生成覆盖（历史缺陷）…」、v13（末次写入方，指纹相符）200、新版 v14/v15/v16 各 200 且字节=各自记录（§2.2 指纹校验真实生效）。
  - **③ 在线编辑改一处正文→生成附注弹一致性确认框→确认后落版本**（design §4.3）✅：交付中心「生成附注」选 165 章「确认生成」→ 弹 **ElMessageBox「附注质量检查」**：「• 未从底稿同步 **25** 章 • 上游已变更(stale) **19** 章 • 无数据 1 章 / 仍可继续生成，但导出文档可能存在缺失或过时数据。」按钮「返回检查 / 仍然生成」（文案与 design「附注与底稿可能不一致 / 仍要导出」措辞不同但语义与计数一致）。API 直证：`confirm_inconsistent:false` → 200 `requires_confirmation=true`、`task_id=null`、`version_no=null`（**不落版本**）、never_synced=25 / stale=19 结构化清单；`confirm_inconsistent:true` → 200 落版本（v17/v18，`consistency.confirmed=true`）。
  - **④ 附注交付件无回填面板、报告正文有**（design §4.1 / §7）✅：能力矩阵 API——audit_report `supports_writeback=true` / disclosure_notes `false` / financial_report `false`；附注 `/writeback` → **400**「附注不支持从交付件回填：附注内容来源于底稿披露表的推送（底稿 → 附注）。请回对应底稿修改并点「同步到附注」…」。UI：打开附注 v18 OnlyOffice 编辑器弹窗——**无回填按钮 / 无 writeback 面板 class**（只有「查看溯源 / 下载 / 关闭」，溯源因附注 supports_lineage=true 保留）；打开报告 v15 编辑器——可编辑 OnlyOffice（非只读）。报告正文「有回填」的正向面板为 WritebackResultPanel（回填动作结果区，`v-if=supportsWriteback` 门控），由能力标志 true + `deliverableCapabilityGating.spec.ts`（Task 30，25 passed）覆盖；未在浏览器触发真实回填（会触发 OnlyOffice 保存，memory 禁）。
  - **⑤ 版本链陈旧底版标签**（design §3.5）🟡 部分：版本链 DTO `GET …/versions` 对全部 18 版**正确下发 additive 字段** `base_version_no` / `overwrote_versions`（schema 透传生效）；但真库现有 OnlyOffice-edit 版本（v3/v15）早于 V191 的 base 追踪，**无 overwrote_versions 非空的陈旧底版样本**，故「基于第 N 版编辑，覆盖了第 M 版」标签的可视渲染无真实数据可触发（需构造一次夹在 base 与当前之间的他人刷新 + OnlyOffice 回调，风险高未做）。标签渲染逻辑由 `DeliverableVersionList` vitest（Task 16，32 例）覆盖。DTO 管道 = 浏览器实证；标签可视 = 守卫覆盖、无真实数据。
  - **⑥ 财务报表溯源面板文案 + 不请求 /section-states**（design §7）✅：打开 financial_report 编辑器→点「查看溯源」→面板显示 **「财务报表按报表行取数，没有章节溯源；数字来源请在「财务报表」页穿透查看」**（`lineage-panel__no-anchor` 渲染，即 `lineageUnsupported=true`）；**全会话网络仅 1 次 /section-states 请求、目标是 audit_report 任务（98369004，supports_lineage=true，应当请求）**，financial_report 任务（a0ea2012）**零 /section-states 请求**（`loadSections` 的 `if(lineageUnsupported) return false` 早退生效）。
  - **LibreOffice 复验**（design §0 / §3.3）✅：`python -m pytest tests/test_onlyoffice_docx_normalize.py` **8 passed**（含 `test_islgl_libreoffice_restores_chinese_chapter`：真 v15 → `normalize_onlyoffice_docx` → 真 soffice.exe 转 txt → 章标题 `七、`）。独立探针再证：真 v15（90 个 `<w:isLgl w:val="false"/>`）LibreOffice 转文本 = **「7、 财务报表主要项目注释」**；规范化后（isLgl-false=0）= **「七、 财务报表主要项目注释」**。
  - **收尾**：浏览器编辑器全程未输入未保存、逐个关闭；两个测试版本 v17/v18 的 DB 行 + 磁盘文件已清理（max 版本回到 16 / count 16，与实测前一致）；一次性探针（仓库外 `d:\_wr32_*`）与临时 cleanup 脚本已删；本会话拉起的 start-dev 两进程已停（环境恢复为实测前「未运行」状态）。未改任何生产代码 / 未提交。
- [x] 33. 更新本 tasks / design（实测证据、未修登记）、`.kiro/specs/INDEX.md`、memory；问用户是否提交。
  - tasks 1~32 复核：除本任务外全 `[x]`，证据行齐全（Task 29~32 实测证据已逐条写入上方）。
  - design §10 补登跨会话预存红（§10.2，见下）；§10.1 活/死路径裁决本任务未改（Task 29 已登）。
  - INDEX.md：本 spec 条目从「0/33 从 stash 恢复」更新为完成状态（29 必做全绿 + 3 处诚实部分：Task 32 flow⑤ 陈旧底版标签无真实数据、全量 vue-tsc OOM 未跑、Playwright 签发清单经 service+vitest 覆盖未在路由页截图）；CRLF 安全编辑（`read_bytes().decode` + `write_bytes`）。
  - memory.md：在「交付中心」族新增一条 ≤300 行约束内的精简条目（范围 / V191 / 教训 / 未修）。
  - 提交就绪报告已交 orchestrator 转述用户（本 spec 改动文件清单、并发会话禁提清单、建议 commit msg、CI `pytest -x` 预存红 caveat）；**本任务不提交**。
  - 复盘追加（2026-10-19，design §10.3）：548318fb1 漏提交 5 个模型文件 ⇒ 补提交 6c262c06f；主工作区暂存区按路径对齐；安徽验收残留已修（审计日志 `deliverable_data_repair`）；前端被拒原因与一致性确认框转义已修；待拍板 2 项（needs_confirmation 无消费方、生成附注两次确认）。
  - 待拍板处理（2026-10-19，design §10.4）：一键全套接导出前一致性闸门（409 `notes_inconsistent` → 同一确认框 → `confirm_inconsistent` 重发），删除无消费方的 `needs_confirmation`；生成附注只确认一次（预检保留校验错误 / 无数据，出具提醒去掉「从未同步」）；`check_note_consistency` 改保存点隔离（PG 上 fail-open 才真正成立）。
