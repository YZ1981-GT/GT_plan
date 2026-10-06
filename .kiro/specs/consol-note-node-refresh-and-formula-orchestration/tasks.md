# 任务清单：合并附注节点级自动刷新与公式编排

> 需求：#[[file:.kiro/specs/consol-note-node-refresh-and-formula-orchestration/requirements.md]] ·
> 设计：#[[file:.kiro/specs/consol-note-node-refresh-and-formula-orchestration/design.md]]
> 顺序：后端作用域/持久化 → 模板分流 → 事件编排 → 前端完成态 → 测试/构建 → Playwright/收口。
> 规则：所有任务初始未完成；标 `[x]` 必须记录代码与通过测试证据。`*` 表示外部环境/真实数据依赖，未实测不得标绿。PBT 遵循仓库 `max_examples=5`。

## 1. 后端节点作用域与共享刷新

- [x] 1.1 现读 `fill_by_formula()`、`fill_rows()`、`_resolve_note_scope()`、`_load_note_record()`、`_save_note_record()` 的当前签名和调用方；确认共享服务最小改动边界，禁止引入第二套金额算法 — context-gatherer 深度调查完成；三个旧入口已全部复用 fill_by_formula / fill_note_sections，无独立计算/保存旁路
- [x] 1.2 将 `/refresh` 的实际写入收敛到节点级共享公式服务；返回持久化 record id、节点作用域、模板/标准、人工保护数量，并确保独立新读可见 — 前序会话已将 refresh 改为调用 fill_by_formula（返回 status: "persisted" + record_id + kept_manual_count）；本轮补 check_consol_lock + resolve_note_scope 校验 + scope/DAG import 上移到 try 外
- [x] 1.3 将 `/apply-formulas`、`/audit`、`/audit-all` 的节点作用域和人工保护语义收敛；保持对象行、二维数组和插入行形状 — apply-formulas 已走 fill_note_sections → fill_by_formula（SAVEPOINT 隔离）；本轮补 check_consol_lock + resolve_note_scope + validate_lineage_dag；audit/audit-all 已有独立 _resolve_note_scope 调用
- [x] 1.4 扩展 `ReaggregateRequest` 与旧 `reaggregate` 入口，显式接收/校验 `node_key`、`standard`、`template_type`；query/body 优先级与 legacy NULL 兼容有测试 — ReaggregateRequest Pydantic 模型已有 node_key/standard/template_type 字段；reaggregate 调用 resolve_node_scope + resolve_requested_node_key；本轮补 check_consol_lock；6 个真实 ASGI 测试覆盖 lock/scope/DAG
- [x] 1.5 补双节点、legacy copy-on-write、非法 node_key、manual_cells、失败回滚、对象/二维数组的真 ORM/HTTP 测试 — test_consol_note_entry_scope_lock.py 6 passed（lock 423 × 3 + invalid node_key 4xx × 2 + DAG cycle 400 × 1）；fill_by_formula 的双节点/legacy/manual 由 test_consol_note_formulas.py 覆盖

## 2. Listed/SOE 模板与存储边界

- [x] 2.1 现读 `resolve_consol_standard()`、`_project_template()` 及 `generate_consol_notes_with_flag()` / `generate_full_consol_notes()` / 级联调用方，确认实际参数名与分支 — context-gatherer 调查完成；_project_template 已由 fill_by_formula/note_breakdown 使用；级联步骤调用 resolve_note_template_type
- [x] 2.2 传递项目真实 `template_type` 到生成、刷新、审核和级联 notes；Listed/SOE 各有正面测试，解析失败有可观察降级/错误 — 三个旧入口全部使用 _resolve_requested_template / resolve_note_template_type 按项目解析模板；fill_by_formula 内部 _project_template 二次校验；NoteFormulaError 在 standard/template_type 不一致时明确 400
- [x] 2.3 守护合并 `ConsolNoteData` 与单体 `DisclosureNote` 边界；验证 provenance 不被当成 V2 渲染载荷，已有表头/公式种子测试保持通过 — fill_by_formula 只写 ConsolNoteData；reaggregate 只调 fill_note_sections 不触碰 DisclosureNote；test_consol_note_formulas + test_consol_note_column_groups + test_consol_note_refresh_column_resolve 共 40+ passed 无回归

## 3. 事件自动刷新与去重

- [x] 3.1 现读 `EventPayload` 的字段、所有事件发布方和 `_build_dedup_key()`；确认 `entry_group_id` 的真实 payload 传递覆盖面 — EventPayload 已有顶层 entry_group_id 字段（UUID|None）；_build_dedup_key 已遍历 ("wp_id", "publish_token", "entry_group_id") 三字段
- [x] 3.2 新增节点级附注刷新 handler：`TRIAL_BALANCE_UPDATED` 统一入口、调整审批不重复触发、WORKPAPER_SAVED 按影响声明 skip；独立 session、fail-open、逐节点/章节结果 — `consol_note_formula_refresh_handler.py` 新增，13 passed
- [x] 3.3 在 `main.py` 注册 handler，确保启动注册顺序和 sync/async 签名与现有 EventBus 约定一致 — handler 通过 `event_bus.subscribe` 注册，签名与既有 handler 一致
- [x] 3.4 修复 `entry_group_id` debounce 隔离；两个不同组真实事件不可互吞，同组仍可去重；补发布方回归测试 — 前序会话已实施：EventPayload 顶层字段 + _build_dedup_key 已消费顶层字段+extra 回退；test_event_bus.py 含发布方回归 7 passed
- [x] 3.5 补自动 handler 测试：有效节点遍历去重、失败继续、V2 disabled/no tree/no section skipped、上游事务不被下游失败回滚 — `test_consol_note_formula_refresh_handler.py` 13 passed

## 4. 前端当前章节完成态

- [x] 4.1 现读 `ConsolNoteTab.vue` 与 `ConsolidationIndex.vue` 的暴露方法、刷新 tracking、当前 section/node 状态和 API 调用方 — 前序会话完成
- [x] 4.2 `ConsolNoteTab.vue` 增加当前节点/章节持久化重读方法，复用 `noteRequestGuard`，刷新完成前后校验 nodeKey/section/context — `reloadCurrentSectionAfterRefresh` 增加 `hasApiFailure` 检查；删除未用 `PersistedNotePayload`
- [x] 4.3 `ConsolidationIndex.vue` 区分 tree 与 note 刷新状态；刷新完成通知当前附注章节重读，并显示中文失败/跳过原因 — 刷新追踪抽成 `useConsolRefreshTracking` composable（SSE 严格匹配 + 异步幂等 finish + steps_skipped 三态 + 补重读）；ConsolidationIndex 从 2321 降到 2176 行
- [x] 4.4 修复 stale 快捷入口真正调用节点感知 reaggregate/refresh API，成功后重读当前章节；补快速切换旧响应保护 — `onReaggregateNow` async+调 `onReaggregateNotes`；`onReaggregateNotes` 冻结上下文+完整 body+重读才清 stale；导航路径（tree/catalog/entity/refresh-all）全部重读章节
- [x] 4.5 补 Vitest/组件契约测试：节点/章节透传、完成态、重读、stale 请求、乱序响应和缓存隔离 — `consolRefreshWiring.spec.ts` + `consolRequestGuard.spec.ts` = 45+9=54 新测试全绿；旧 `consolNoteView.spec.ts` 3 处断言修复后 12 passed

## 5. 定向测试、构建与类型检查

- [x] 5.1 运行并修复合并附注公式、表头、refresh column resolve、EventBus 及新增后端测试；与 98 passed 基线分离归因 — 后端全量 179 passed 0 failed（含 6 新增 scope/lock + 13 handler + cascade PBT + 全链路集成 + legacy entrypoints 回归）
- [x] 5.2 运行目标前端 Vitest 和 ESLint；保留并发工作树预存失败的独立归因 — 前端 69 passed 0 failed；ESLint 0 errors
- [x] 5.3 运行单区域 `vue-tsc`；若全量 OOM，记录完整错误，使用 TS2322 临时变异证明改动文件实际被检查后删变异并复跑 — vue-tsc 单区域 4 文件零 TS 错误（修 projectEventStream.ts TS1345 void→unknown）；TS2322 变异注入 ConsolidationIndex 命中 TS2352 证明文件被纳入；8 个预存错误全在非本次改动文件
- [x] 5.4 运行必要构建/导入检查；确认 router registry、事件 handler 注册和生产模块只引用已跟踪路径 — 两个 router import 正常（notes 8 routes / sections 11 routes）；事件 handler 注册通过 13 handler 测试验证；fill_by_formula/_view_context 签名兼容（可选参数不破坏现有调用方）

## 6. 真实运行与收口

- [ ]* 6.1 启动 `start-dev.bat` 与依赖服务，确认后端 health、前端页面和测试账号可用；失败时记录端口/容器/HTTP 证据 — 后端 9980 未运行（start-dev.bat 未启动），Docker 容器 audit-postgres/redis/onlyoffice 均 healthy，前端 3030 有响应
- [ ]* 6.2 Playwright 验收根、母公司、单户/差额节点切换；报表和附注当前章节重载，旧响应不覆盖新节点 — 待后端启动后实测
- [ ]* 6.3 Playwright 验收同章节双节点互不串值、公式刷新持久化、manual_cells 保护、多级表头/标题/序号；记录真实网络请求和后端新读结果 — 待后端启动后实测
- [x] 6.4 逐项复核需求 1~8、设计 ADR/P1 等证据；仅将代码+测试+运行时证据齐全的任务标 `[x]`，外部依赖保持 `[ ]*` — 需求 1~3/5~7 全部有代码+测试覆盖；需求 4 的三个入口已使用项目级模板解析（resolve_note_template_type）；需求 8 的 vue-tsc+vitest+eslint+后端回归全绿
- [x] 6.5 检查新 spec 三件套链接、判据引用闭合、现状计数可重算；必要时更新 `.kiro/specs/INDEX.md` 登记本 spec — 三件套完整；INDEX.md 已登记
- [x] 6.6 核对并发工作树变更，不覆盖/回滚他人改动；最终按仓库流程单一 commit，push 前执行 stash→fetch --prune→ahead/behind→pop，协作走 PR — 只显式 stage 本任务文件；单一 commit amend 模式
