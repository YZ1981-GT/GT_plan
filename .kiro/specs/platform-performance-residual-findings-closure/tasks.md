# 任务：平台性能收口的范围外发现

> 需求编号 `R1`~`R13` 的定义见 `requirements.md`（2026-11-06 回填；本 spec 立项时缺该文件，`R*` 被引用却无定义处）。
> 规则：标完成须有代码 + 测试证据；未实测标 `[ ]*`；不提交不推送；只改本 spec 拥有的改动块。
> 证据口径：「HEAD 红」= 在 HEAD（841166b57）干净 worktree 上跑同一用例打红；「变异」= 进程内替换被测模块源码（不改磁盘）。

## 批 A 后端路由可达性（R1）

- [x] 1. 全应用遮蔽守卫 `backend/tests/test_route_shadow_guard.py`（允许集为空、双向变异样本）；先在未修代码上跑，确认 13 条全部报出
  - HEAD 上 `test_no_shadowed_route` 逐条报出 13 条（12 GET + POST batch-review），14 个 `_FIXED_CASES` 全红；工作区全绿。变异：collaboration / attachments / report 三处恢复旧顺序、system 恢复 b60 重复注册均打红，只加注释的对照组仍绿
- [x] 2. 同模块调声明顺序：attachments `paperless-health`、disclosure_notes `deleted` / `formula-health`、workhour_entries `summary`；report_config `row-note-mapping` 改为迁出 `routers/report_row_note_mapping.py`（路径不变，见 design §2）
- [x] 3. 跨模块调 include 顺序：report 组 `report_row_note_mapping` / `report_config_baseline` / `note_wp_mapping` / `note_trim` 前置；collaboration `workhour_budget` / `workhour_approval` 前置于 `workhour_entries`
- [x] 4. 归档历史改路径 `/version-archives`（后端 + `useWpExportImport`），版本链列表生效；`test_task9_core_route_gate.py` 两条路径各覆盖放行 / 未委派 / 跨项目（6 例 PG 通过）
- [x] 5. 重复注册逐组删死实现：aging_analysis 三个（鉴权移到 aging_config）、system §53d 的 b60、completion_phase 五个（含 `recommend_supplement`）、ledger_import_v2 retry、pm_dashboard batch-review（含 `pm_service.BatchReviewService`）；`_KNOWN_DUPLICATES` 清空
- [x] 6. 变为可达的接口端点级用例：`test_route_shadow_reachability_endpoints.py`（预算对比 / 审批 / 工时汇总、候选、row-note-mapping 静态、paperless-health、附注 deleted / formula-health、附注裁剪与底稿映射）、`test_aging_config_project_authz.py`（四态）、`test_workhour_approval_completion.py`（外项目经理 403）、`procedure_delegation_visibility/test_completion_dedup_live_endpoints.py`（PG：A18 检查 / 导出、未登记编码 501、问题提示与底稿摘要走服务、非成员 403）
- [x] 7. 台账与基线：`check_drift` 前后对比只多出并发会话 `api/users.py` 的 6 条（项目创建授权 3 + 人员绑定 3），其余各类不变；`wp_bound_entry_coverage.json` 补登；`_IDENTITY_ONLY_BASELINE` 165→153、`_PREFIXED_IDENTITY_ONLY_BASELINE` 232→230；`test_x3_entry_coverage_ledger.py` 通过

## 批 B 报表附注列与调用方（R2 / R3）

- [x] 8. ~~`fetchNoteSectionsWithData` 改用目录树端点~~ 按 design §3.4 修订：附注列直接用导出编号方案的格值，`fetchNoteSectionsWithData` 与 notes-tree 取数删除，改为 `fetchRowNoteRefs`（+ `fetchRowNoteRefs.spec.ts`）
- [x] 9. row-note-mapping 加可选 `project_id` / `year`，按导出编号方案给 `display`；`test_report_row_note_mapping_endpoint.py` 6 例：不带参数与静态映射逐项相同、非成员 403 / 只读成员 200、口径不认识 422、方案缺失按静态映射回退（只登记库内有同名行的格）、方案可用取方案格值、导出与端点同一入口同一份 hints；变异 5 处（去鉴权 / 渲染不传方案 / 按编码硬挂 / 跳转编号取模板码 / hints 置空）各打红一例，注释对照组全绿
- [x] 10. ReportView / useReportColumns 改用 `display`，删按金额计数的回退编号与前端写死的映射表（删前全仓零调用；+ `useReportColumns.spec.ts`）
- [x] 11. 真实项目对拍（重药安徽 / 和平 / 华氏，2025）：模板附注格 67 个，页面 65 格与导出逐格一致、0 差异；余 2 格（应收资金集中管理款、油气资产）项目报表无此行，页面不挂。华氏导出把「七、9」写在油气资产行（附注八、25 有表格数据、项目无此行，登记 design §7.3）
- [x] 12. A16：`useAProgramPopups` 读 `recommended_code`（+ `GtAProgramConsoleA16Seq2.spec.ts` 按真实形状）
- [x] 13. A18-2：`a18_check_incomplete` 映射统一契约（+ `test_regulatory_letter_service.py`、PG 端点用例）；GtRegulatoryLetter 导出补 `/api`、按 `complete` / `missing_fields` 提示（+ `GtRegulatoryLetter.requests.spec.ts`，HEAD 红）

## 批 C 公式端点登记（R4）

- [x] 14. barrel 补 4 个导出；新增 4 个访问器并在三个面板使用；`formulaPaths.spec.ts` 全绿（顺带修该 spec 的提取器：按各 router 变量自己的前缀取路径，原先把 `global_router` 的 /coverage 算错；补自检用例）

## 批 D 前端运行时卫生（R5）

- [x] 15. `dict.ts` 标签类型规范化（`normalizeTagType`：`''`→primary、非法→info；两个预览同口径；+ `dictTagType.spec.ts` 用真实 ElTag 告警钩子）；模板里写死空串类型的 `<el-tag>` 现算 14 处（未兜底 9、已 `|| undefined` 兜底 5），按 design §4 只登记不改
- [x] 16. 重复 GET：D2 能力快照两次 → 一次（`useShellCapability` 改按请求主体多源监听；+ 用例含机制自检）；D2 项目详情（store 非静默 vs 静默两种语义）、查账 `ledger/years` 与项目详情（先后发起、参数不同）如实登记不改
- [x] 17. 公式管理首次打开才挂载（4 宿主 + `useMountOnFirstOpen` + `useMountOnFirstOpen.spec.ts`、`ThreeColumnLayout.year.spec.ts` 调整）

## 批 E 测试卫生（R6）

- [x] 18. `tabToRoute` 抽到 `layouts/defaultLayoutRoutes.ts`（用 `hasOwnProperty.call`，与仓库先例一致），生产与测试同一份；顺带修真缺陷：报表页签跳 `'financial-reports'`（路由不存在、落 404）→ `'reports'`；PBT 改按真实路由表 resolve 并自检 NotFound
- [x] 19. guidanceBar 判据改 `textContent` 并调生产 `isGuidanceVisible`；G6 P6 判据按生产语义（+ 反例用例）
- [x] 20. S34-16-1 复现反例定位根因：测试判据假设 C23 = E19，工作簿 C23 实为手填 ⇒ 修判据（+ 次正规数反例用例）
- [x] 21. 金额列探针 `--out`，spec 写临时文件并断言已跟踪产物字节不变

## 批 F 前端请求路径（R7，验收期发现）

- [x] 25. 工时页「预算对比」下拉恒空：工时页与「我的填报」同时取 `/api/projects/my/assignments`，utils/http 去重取消了先发的那次 ⇒ `staffApi.getMyAssignments` 改经 apiProxy 共享在途、各拿数组副本（+ `staffApiMyAssignmentsShared.spec.ts` 含机制自检，HEAD 红）；浏览器：下拉默认首个项目、预算对比 200
- [x] 26. 少 /api 前缀的请求 15 处全部修复：A18-2 读写 / 建议 / 表头带出（检查表改走 `/api/workpapers/{wp}/checklist-responses`、请求体 `{project_id, items}`、未选适用性存 null、年度取 `audit_year`、先取签字合伙人）、I1/I3~I6 健康检查改用统一探针 `fetchOnlyOfficeHealthy`、H3 两处勾稽取对方底稿（静默 404）、K10 两处识别（按底稿调 D4、读 `ocr_text`、附件挂本行 + 小眼睛）、H5 自取渲染配置、侧栏 PBC、凭证识别弹窗（未挂载）
- [x] 27. 守卫 `apiPathPrefixGuard.spec.ts`（全仓字面量调用须带 /api、apiPaths 字面量须带前缀、扫描面 ≥ 2000、自检 4 例）+ `GtRegulatoryLetter.requests.spec.ts` / `iCycleDualModeHealth.spec.ts` / `k10OcrContract.spec.ts`（跨语言取后端响应字段）；四个文件在 HEAD 上均打红
- [ ]* 28. 批 F 界面走查（**本 spec 界面走查的唯一承载处**，见 requirements R13.1）：PBC 页签已实测（200、空态）；A16 推荐标记、A18-2（检查 / 导出 / 读写）、I 循环在线编辑切换、H3 勾稽、K10 识别五项所需底稿在存活的【测试】项目里都没有（真实项目打开 A18-2 会占编辑锁），只有单测 / 契约证据。解除条件：在【测试】项目里按平台路径生成这五类底稿（R13.2）
  - 2026-11-11 联合浏览器验证（`127.0.0.1:3030` + 共享后端，【测试】公式同步甲有限公司_2025 已生成 A16 / A18-2 / H3 / I1 / I3 / K10，前置条件 R13.2 已满足）：
    - ✅ **A18-2 读写**：选「1. 舞弊 · 适用」→ 自动保存 `PUT /api/workpapers/{wp}/checklist-responses` 落库 `a182-matter1-applicability.remark='Y'` → F5 回读仍选中，console error 0；随后经同一端点写回 null 复原。
    - ⚠️ **A18-2 检查 / 导出**：界面上没有入口。该底稿 render-config 的 componentType 是 `a18-2-regulatory-communication`（`GtA182RegulatoryCommunication.vue`），任务 26 修的是另一个组件 `GtRegulatoryLetter.vue`（`regulatory-letter`，工具栏里才有「导出 Word」与 `check-incomplete`）。后端 `GET …/export-word/check-incomplete` 接口单独调用 200（`{"incomplete":[],"count":0}`）。⇒ 修复落在了用户看不到的组件上。
    - 🔴 **A16 推荐标记**：编辑器只显示工具栏，正文空白、无报错。`GtA16Bundle` 只显示 wp_index 里存在 `A16-1`~`A16-7` 子底稿的页签，而该项目只有 `A16` 一张 ⇒ 页签全空；推荐标记无从显示。
    - 🔴 **I 循环在线编辑切换**：I1 页面没有「在线编辑」切换。实测 OnlyOffice `GET /api/workpapers/onlyoffice/health` = `healthy: true`，但 `useI1DualMode.ts` 仍请求 `/workpapers/onlyoffice/health`（无 /api）⇒ 拿到首页 HTML（200 text/html）⇒ 判为不健康 ⇒ 切换被隐藏。
    - 🔴 **H3 勾稽**：`h3TransferReconcile.ts` / `h3MortgageReconcile.ts` 仍请求 `/custom-query/wp-id-by-code`（无 /api），实测返回首页 HTML，取不到对方底稿。
    - 🔴 **K10 识别**：`K10TabOtherIncomeCheck.vue` / `K10TabReceivableGrant.vue` 仍 `POST /d4/contract-ocr`，实测 404。
  - 结论：任务 28 **不能勾选**。原因不是缺数据，而是下一条勘误：任务 26 / 27 的产物不在当前分支。

> **2026-11-11 勘误（任务 26 / 27 假绿，append-only，原勾选文字不改）**：联合浏览器验证发现两项交付不在当前分支 `spec/disclosure-note-doc-upload-and-batch-fill`（HEAD `8655d07ee` / v1.0.165）。
> - 守卫 `src/__tests__/apiPathPrefixGuard.spec.ts`、`k10OcrContract.spec.ts`、`iCycleDualModeHealth.spec.ts` 在 HEAD 与工作区都不存在；统一探针 `fetchOnlyOfficeHealthy` 全仓 0 处。`GtRegulatoryLetter.requests.spec.ts` 在库（随批 G 提交 `cd0a8fe1f` 进入）。
> - `git log --all -S` 只在 4 个快照提交里找到它们：`8eed682ec`（10-31 gt-sync backup）、`227dfb429` / `dceb889c1` / `50736413a`（11-01 SAFETY SNAPSHOT before pull），四者都**不是 HEAD 的祖先**、也不在任何远端分支上。⇒ 产物只在当时的工作区里，主工作区同步时没有带进分支。
> - HEAD 现扫仍不带 /api 的字面量请求 7 组 / 13 处（扫描脚本口径：`api|http|apiProxy` 的 `get/post/put/delete/patch` 首参以 `/` 开头且首段不是 `api`，排除测试）：`/custom-query/wp-id-by-code`（H3 两处）、`/d4/contract-ocr`（K10 两处）、`/workpapers/onlyoffice/health`（I1、I3~I6 五处）、`/workpapers/${wpId}/render-config`（H5）、`/projects/${pid}/pbc/by-workpaper/${wpId}`（侧栏 PBC）、`/projects/{pid}/trial-balance/writeback`（`useE1Adjudication.ts`）、`/items`（`useFirstLoad.ts`）。逐个实测：PBC / H5 / H3 / I 健康检查都返回首页 HTML（200），K10 POST 404。最后两组未判定是否为死代码。
> - 处置建议：另立恢复 spec，从快照 `50736413a` 按文件三方合并恢复任务 26 / 27（不整文件 checkout：快照之后这些文件可能已被改过），并补「A18-2 实际组件是 `GtA182RegulatoryCommunication`」与「A16 子底稿缺失时的空态」两处。恢复前任务 26 / 27 / 28 都不应计入完成度。

## 批 G §8 裁决项（R8~R12，design §9）

- [x] 29. R8 A16：删旧格式分支；补充声明开关先读字段覆盖 `enabled` 再按 `always_required`；`WorkpaperWordEditor.spec.ts` mock 改真实形状 + 旧形状反向用例 + 记录优先用例 — 3+19 例绿，变异 R8a/b 红
- [x] 30. R9 A18-2：挂载流程不保存、改动才防抖保存、改回原值不保存、读已存内容失败不自动保存并提示；`GtRegulatoryLetter.requests.spec.ts` 补 4 用例（HEAD 红→绿），变异 R9a-d 红
- [x] 31. R10 附注编辑页切年度写路由、自动生成交给重挂后的挂载流程、未保存拦截挂离开 + 更新；`yearSwitchUpdatesRoute.spec.ts` `KNOWN_GAPS={}` + 附注页 4 断言；DisclosureEditor 3160/3164；变异 R10a-c 红
- [x] 32. R11 GET 共享在途：抽内核 `utils/getSingleFlight.ts`；utils/http 包装 `get`、GET 不进去重表、写请求与项目事件推进屏障；apiProxy 改用内核；`httpGetShare.spec.ts` 19 例 + 改写旧语义用例 6 + apiProxy 2 + projectEventStream 1；变异 M1-M8+M5 全红
- [x] 33. 批 G 回归：后端 428 passed 0 failed；前端 53/54（1 红是并发会话改 WorkpaperEditor.vue 尾部换行，HEAD 复现同红）；ESLint 全通过；8 个前端文件行数全在门限；单区域 tsc TS2307 是 include 不全的已知局限。浏览器：附注页正常加载（199 节），R10/R8/R9/R11 因无多年度项目 / 无【测试】底稿无法实测，标 `[ ]*`
- [x] 34. R12 复核工作台（用户选方案 A：F8 配置驱动状态机；34.1~34.5 已完成，34.6 为可选浏览器实测，缺 pending_level1 底稿，另见任务 28）
  - [x] 34.1 后端：`update_review_status` 的 `REVIEW_TRANSITIONS` 改为按项目 `review_config.levels` 动态生成（`pending_levelN` / `levelN_in_progress` 都可直接通过或退回；非末级通过自动推下一级待复核；末级通过标 `review_passed`；退回标 `revision_required` + 必填原因 + ReviewRecord）；删零调用的 `ReviewStateMachine`
  - [x] 34.2 后端：`POST /api/projects/{pid}/batch-review`（逐张走同一状态机，接受 action=approve/reject，跳过不符合的并写原因回报）；AI 批量复核改路径 `/ai-batch-review` 消除冲突
  - [x] 34.3 前端 ReviewWorkbench：`approveCurrent` / `rejectCurrent` 改发当前级的 `levelN_passed` / `levelN_rejected`；`reviewStatusLabel` 补 L3/L4；批量通过改调 `batchReview()`；删 `api` 直调
  - [x] 34.4 前端项目设置：底稿配置 tab 加「复核层级」卡片（2/3/4 + 各级角色 + 保存），onMounted 加载 review-config，409 提示
  - [x] 34.5 测试：`test_review_state_machine.py` 19 passed（转换表 8 + 状态机集成 6 + 批量端点 5）；回归 386 passed 0 failed；_IDENTITY_ONLY_BASELINE 153→152（batch_review 从 readonly 提升到 review）；route_shadow_guard fixed case 改 /ai-batch-review
  - [ ]* 34.6 浏览器实测：复核配置入口正常、接口端到端 3 项全通过；提交→通过→退回全流程因无 pending_level1 底稿未实测（编号原与 34.5 重复，2026-11-06 按 requirements R13.3 改为 34.6；前置条件见 R13.2）
- [x] 35. §8.2 另立 spec `project-pid-path-authz-coverage` 并登记 INDEX — 三件套已写（tasks 1-6），INDEX 第 7 行，Active 14

## 收尾

- [x] 22. 回归：后端 42 个文件 488 passed / 11 failed（均 HEAD 同红：workhour_batch_approve 5、workhour_list 2、version_trail_integration 3、task9 checklist_put_allow_admin 1）/ 5 skipped（已归档 spec 的永红守卫）；前端最终合并选集 212 个文件 2929 passed / 6 failed，6 例均在 HEAD worktree 上同样失败（gCycleProcedureConsole、GtAuditSheet 行数、rawRequestAuth 的 GtA51 原生 fetch、controlledInputCommitRatchet 的 HEAD 已 1749 > 1748、hostSheetDispatchChain 的 GtH10 ×2）；单区域类型检查三组相对 HEAD 新增 0（1488→1477、24→22、0）；ESLint 0 error、warning 相对 HEAD 新增 0；行数门 99 个文件通过（ReportView 上限压低 1 的对照组打红）
- [x] 23. 浏览器实测（127.0.0.1:3030）：报表页 /api 全 200、附注列编号、切年度写 `?year=&tab=` 并按新年度取数、console error 0；项目树标签无 warn；版本链抽屉 5 条快照、「历史版本」页签走 `/version-archives`（全库 `wp_version_archive` 0 行，空数组为真实状态）；工时预算对比；公式管理四宿主首次打开才加载；D2 能力快照 1 次请求
- [ ]* 23a. A16 推荐标记、A18-2 导出的界面走查：只在页面内调接口验证（A16 推荐 A16-1、A18-2 检查 4 项未填、导出 17,965 字节 docx）；打开真实项目底稿会占编辑锁，未做界面层。**不单独验收**，结论引用任务 28（requirements R13.1）
- [x] 24. 更新本 spec 证据、INDEX（第 6 行）、memory（1 行，共 300 行）；删仓库外探针目录与基线 worktree；待裁决项见 design §8
> **2026-11-14 勘误（上一条 2026-11-11 勘误已过期，append-only，原勾选与原文均不改）**：用户「整体分析下未归档完成的 spec，逐一修复完成」时对该条逐句现算复核，**「任务 26 / 27 的产物不在当前分支」这一判断已不成立**。
> - 三个守卫**全部在库且已被跟踪**，同一提交 `d7d7515f5`（`chore(root): 同步隔离树改动并清理临时产物`）入库：`src/__tests__/apiPathPrefixGuard.spec.ts`、`src/components/workpaper/__tests__/k10OcrContract.spec.ts`、`src/components/workpaper/composables/__tests__/iCycleDualModeHealth.spec.ts`；`GtRegulatoryLetter.requests.spec.ts` 亦在库。
> - 统一探针 `fetchOnlyOfficeHealthy` 有**生产定义**：`src/components/workpaper/sync/onlyOfficeHealth.ts`，被 20+ 个 `useXxDualMode` 引用（`useI1DualMode` / `useI3DualMode` / `useK10DualMode` / `useN1DualMode` / `useD4SyncMode` / `useHSyncMode` / `useARenderModeSwitch` 等）。
> - 「HEAD 现扫仍不带 /api 的 7 组 / 13 处」**现算为 0 处**。复核口径按 memory 铁律 ㉖（注释会骗过文本扫描器）：先把 `/* */` `//` `<!-- -->` 换成等量空格再扫。首版探针（不剔注释）命中 2 处，逐处现读**全在注释里**——`useFirstLoad.ts:8` 是 JSDoc 用法示例 `useFirstLoad(() => api.get('/items'))`，`useE1Adjudication.ts:538` 是说明「原写 `/projects/{pid}/trial-balance/writeback` 已消除该反模式」的历史注释。
> - 任务 28 记录的五个阻断点**逐项现算均已修复**（同一剔除注释的探针）：
>   | 阻断点 | 当时记录 | 2026-11-14 现算 |
>   |---|---|---|
>   | I1 / I3~I6 在线编辑切换 | 请求 `/workpapers/onlyoffice/health`（无 /api，拿到首页 HTML ⇒ 恒判不健康） | 走 `fetchOnlyOfficeHealthy()` 统一探针，**代码内无任何字面量路径**（`/api` 前缀在 `onlyOfficeHealth.ts` 里一处收口） |
>   | H3 划转 / 抵押勾稽 | 请求 `/custom-query/wp-id-by-code`（无 /api） | 两处均已是 `/api/custom-query/wp-id-by-code`（各 1 处，非 /api 形态 0） |
>   | K10 其他收益 / 应收补助识别 | `POST /d4/contract-ocr`（404） | 两处均已是 `/api/workpapers/${wpId}/d4/contract-ocr`（各 1 处，非 /api 形态 0），并按底稿挂载 |
>   | A18-2 检查 / 导出入口 | 修在 `GtRegulatoryLetter` 而实际组件是 `GtA182RegulatoryCommunication` | 实际组件 `GtA182RegulatoryCommunication.vue` 已含 `export-word` 请求（`/api` 形态 1、非 /api 0），即「修在用户看到的组件上」这一项已补 |
>   | A16 推荐标记 | `GtA16Bundle` 只显示存在 `A16-1`~`A16-7` 子底稿的页签 ⇒ 页签全空 | 未在本轮复核范围（属界面层，需【测试】项目里有 A16 子底稿才能验；`api-prefix-fix-recovery` 任务 5 已补「子底稿缺失时的空态」） |
> - ⇒ **任务 26 / 27 的交付状态已具备分支级证据**（在库 + 可执行守卫 + 剔除注释后 0 处缺失前缀），原「不计入完成度」的处置不再成立。任务 28 的**代码侧**五条阻断全部消除；剩下的只是**界面走查**本身（需在【测试】项目里按平台路径生成 A16 子底稿后逐项点开），因此仍保持 `[ ]*`，但阻断原因由「产物不在分支」更正为「仅缺界面层实测与 A16 子底稿数据」。
> - 复核方法留痕：探针 `tmp_spec_audit/probe_api_prefix_ast.py`（全仓剔注释扫描）、`tmp_spec_audit/probe_residual_task28.py`（不剔注释，用于对照假阳）、`tmp_spec_audit/probe_residual_task28_strict.py`（剔注释，出上表数据）。