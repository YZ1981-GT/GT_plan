# 需求文档：合并节点隔离、共享上下文与工作底稿联动

> 工作流：Design-First。验收标准采用 EARS 风格；正确性属性见设计 §六。
> 上游：`consol-tree-three-code-autobuild`（node_key 树身份）与 `consol-elimination-single-source-push`（统一合并计算内核）。
> 数据层前提：当前工作树已有 V177 `consol_note_data.node_key` 与两套部分唯一索引；本 spec 消费该变更，不重复创建同一迁移。
> 工作底稿边界：合并工作底稿当前仍按 `(project_id, year, sheet_key)` 持久化，不属于附注的 `node_key` 隔离范围。第一批修复只统一父页有效年度和错误语义，不在前端伪造 `node_key`；若未来需要按合并节点保存工作底稿，必须另提 schema/迁移和兼容设计。
> 公式与股比边界：公式管理必须通过真实 `consol_worksheet` reader、mutation adapter 和持久化审计接入；动态股比必须以 1~N 个稳定事件建模，不能把固定三次列或 G7 建议草稿当作正式抵销链路。

## 引言

合并树已用 `node_key = {企业代码}:{角色}` 区分同企业的合并节点、母公司/本部和差额节点；附注表也已开始按节点保存。但读写路径、custom query 单元格访问与普通合并报表仍有项目级或仅按企业代码取数的路径，导致切换树节点后数据串用、缓存串用或读取项目级旧报表。附注旧公式端点还查询 `TrialBalance` 中不存在的列，并将 SQL 错误吞掉后返回模板数据。

本需求将 `node_key` 作为合并报表和合并附注共同的节点身份：附注行按项目、年度、章节、节点隔离；需要旧数据兼容时仅允许经企业树确认的根合并节点读取 legacy `node_key IS NULL` 行，写入始终落到当前节点专属行；custom query 的附注 cell 读写必须保持同一归属；普通合并报表按所选节点实时计算；前端树节点选择、请求和缓存使用同一个 `nodeKey`。

## 需求 1：附注数据按节点身份隔离

**用户故事**：作为合并执行人，我希望不同树节点上的同一附注章节互不覆盖，且切换节点后只看到该节点的数据。

### 验收标准

1. WHEN 请求提供 `node_key` THEN 附注数据读取和写入 SHALL 同时限定 `project_id`、有效审计年度、`section_id` 与该 `node_key`；SHALL NOT 仅按 `company_code` 推断节点身份。
2. WHEN 请求提供不存在于该合并项目企业树的 `node_key` THEN 服务 SHALL 返回明确的客户端错误，SHALL NOT 将其降级为项目根节点或按冒号前缀继续查询。
3. WHEN 请求提供有效根合并节点 `node_key` 且该章节没有节点专属行 THEN 读取 MAY 回退到同项目、同年度、同章节的 legacy `node_key IS NULL` 行；该回退 SHALL 先由当前企业树确认节点确为根合并节点。写入、公式填入或后续修改 SHALL 创建或更新节点专属行，SHALL NOT 修改 legacy 行。
4. WHEN 请求针对非根节点或未提供 `node_key` THEN 读取 SHALL 只匹配精确节点行或旧调用专用的 NULL 行，SHALL NOT 读取其他节点的行。
5. THE 附注节点级 GET、PUT、公式填入、公式刷新、全审、单审、批量套用公式、聚合及差额穿透端点 SHALL 使用一致的节点身份解析与校验规则；兼容旧 body 中的 `node_key` 时，明确的 query 参数 SHALL 优先。
6. WHEN 节点 A 与节点 B 对同一章节先后保存不同数据 THEN 两节点各自重读 SHALL 返回各自最后保存的数据；根节点 legacy 回退不得改变节点 A/B 的写入结果。

## 需求 2：附注公式使用真实合并计算口径

**用户故事**：作为合并执行人，我希望附注公式刷新和审核读取真实试算表数据，并按当前合并树节点计算。

### 验收标准

1. THE 合并附注公式取数 SHALL 复用现有 `consol_report_view_service.load_view_context`、`consol_calc_basis` 与合并公式求值能力，或其既有同口径接口；SHALL NOT 另建一套只按 `company_code` 的合并金额算法。
2. THE 任何从 `trial_balance` 取值的路径 SHALL 只引用真实 ORM/schema 字段，包括 `standard_account_code`、`account_name`、`unadjusted_amount`、`audited_amount`、`opening_balance`、`aje_adjustment`、`rje_adjustment`、`wp_adjustment`；SHALL NOT 引用不存在的 `account_code`、`closing_balance`、`debit_amount` 或 `credit_amount` 列。
3. WHEN 取数失败或数据无法解析 THEN 端点 SHALL 返回可观察的错误或逐项原因，SHALL NOT 吞异常并报告成功、静默回传模板值或伪造为零。
4. WHEN 节点级公式填入成功 THEN 结果 SHALL 只写回该节点附注行；存在手工保护的单元格时 SHALL 保留其原值，并在响应中如实报告保留数量。
5. THE legacy 的刷新与批量套用入口 SHALL 与 `fill-by-formula` 的节点行读写行为一致；旧请求不传节点仍可走项目级 NULL 兼容路径。
## 需求 3：custom query 附注 cell 读写归属

**用户故事**：作为自定义查询使用者，我希望 `note:{section}|{range}` 只读取所选节点附注，并且 cell writeback 只能修改该节点所属项目、年度和章节的数据。

### 验收标准

1. WHEN custom query 请求的 `filters.node_key` 有值 THEN module-cell resolver SHALL 将该值传到附注取数器；其 SQL SHALL 同时限定项目、年度、章节和节点键，查询结果不得包含另一节点或另一项目的行。
2. WHEN custom query 使用不带 `node_key` 的旧请求 THEN resolver SHALL 只读取 legacy NULL 行；当请求带节点键时 resolver SHALL 精确匹配该键。节点专属写回不得因记录缺失而改写 legacy 行。
3. THE note cell writeback 请求 SHALL 显式携带并校验项目、年度、章节、节点键和附注记录 ID；记录 ID 对应行的全部归属字段 SHALL 与请求逐项相等，否则拒绝且数据库内容保持不变。
4. THE note writer SHALL 在事务锁定记录后再次执行归属校验，并继续遵守既有乐观锁、项目编辑权限与审计要求；不得把可猜测的记录 ID 当作项目或节点授权。
5. THE note writer SHALL 支持实际持久化形态：对象行与二维数组行；更新指定单元格时保留其他值和原行形状，行列越界返回明确错误。
6. WHEN writeback 被拒绝、记录不存在或归属不匹配 THEN 事务 SHALL 回滚；SHALL NOT 更新任何 `consol_note_data` 行。

## 需求 4：普通合并报表共享节点计算

**用户故事**：作为合并报表查看者，我希望普通合并报表与试算/差额计算一样按当前选中的树节点展示，而不是始终读取根项目的物化报表。

### 验收标准

1. THE 普通合并报表读取端点 SHALL 接受 `node_key`，并通过当前合并项目的企业树验证该键；未提供时 SHALL 采用当前根合并节点作为兼容默认值。
2. THE 报表行金额 SHALL 复用 `consol_report_view_service.load_view_context`、`consol_calc_basis.node_measures` 与 `consol_report_values` 的现有求值口径；SHALL NOT 为附注/普通报表另造独立金额公式，也 SHALL NOT 把节点 `company_code` 当作节点主键。
3. THE 普通合并报表 SHALL 保持现有报表行数组响应契约及字段语义，同时使当前节点的合并数成为页面显示值；节点不存在、年度无效或公式不支持 SHALL 按明确错误/留空原因表达。
4. FOR ALL 有效节点和报表行，普通报表节点金额 SHALL 与同节点报表试算/差额读端点采用同一公式计算所得金额一致（金额精度按现有到分规则）。
5. THE 前端报表请求 SHALL 发送 `currentConsolEntity.nodeKey`，响应缓存键 SHALL 包含该 nodeKey；在同企业不同角色节点间切换时 SHALL NOT 命中另一节点缓存。

## 需求 5：前端附注与报表共享所选节点

**用户故事**：作为合并执行人，我希望在合并树切换节点后，报表和附注编辑上下文自动一致，保存与重读都留在当前节点。

### 验收标准

1. THE `ConsolidationIndex.vue` SHALL 将当前选中树节点的 `{code, name, nodeKey}` 传给报表加载器与 `ConsolNoteTab`；`ConsolNoteTab` 的实体类型 SHALL 包含必需的 `nodeKey`。
2. WHEN 切换树节点 THEN 当前报表和附注数据 SHALL 使用同一 `nodeKey` 重新加载；异步旧请求完成时 SHALL NOT 覆盖新节点页面数据。
3. THE 附注组件所有节点级读取/写入/公式填入/刷新/审核/聚合请求 SHALL 传当前 `nodeKey`；独立的差额穿透节点选择 SHALL 以当前节点作为初始值，用户显式另选后仅影响该穿透视图。
4. THE 普通报表缓存键与附注缓存键 SHALL 同时包含项目、有效年度、nodeKey 和报表/模板维度；节点刷新 SHALL 只清理该节点缓存。
5. THE API path/service 参数 SHALL 保留现有调用方式的兼容性，并使 `node_key` 可明确传递到后端；用户可见错误提示 SHALL 为中文。

## 需求 6：测试与运行时验证

1. THE 后端 SHALL 提供真实 ORM/SQLite 或适用真实 PG 测试，覆盖至少两个节点、legacy NULL 行、错误 node_key、跨项目/跨年度/跨章节记录 ID、对象行和数组行写回，以及节点报表金额一致性。
2. THE HTTP 端点测试 SHALL 经真实 FastAPI 请求和权限依赖链验证成功与拒绝行为；只测 service 或 mock writer 不满足验收。
3. THE 前端 SHALL 提供 API/组件契约测试，覆盖 nodeKey 透传、节点切换缓存隔离和旧请求不覆盖新节点。
4. WHEN 本地后端与前端可运行 THEN SHALL 使用 Playwright 实测树节点切换、普通报表重载、附注数据保存后重读、两个节点之间互不串值；若环境不可运行，任务 SHALL 保持未完成并记录具体阻塞，不得将静态检查当作浏览器实测。
5. THE 定向回归 SHALL 覆盖现有合并附注公式、合并报表视图、module-cell resolver 与 snapshot writer 测试；不得把并行工作树既有失败误归因于本 spec。
## 需求 7：合并工作底稿共享年度与加载状态

**用户故事**：作为合并执行人，我希望右侧切换到合并工作底稿时，使用合并页当前有效年度加载同一套数据；当接口失败时，我能区分“没有数据”和“加载失败”。

### 验收标准

1. THE `ConsolidationIndex.vue` SHALL derive one effective year from the parent page (`treeYear`/`projectInfo.year` according to the existing page contract) and pass it explicitly to `ConsolWorksheetTabs`; the child SHALL NOT derive year from `route.query.year` or `new Date()`.
2. WHEN the user clicks a node in the left enterprise tree THEN report/note views SHALL use that exact current `nodeKey`; the worksheet SHALL continue using its current `(project_id, effective_year, sheet_key)` scope until a separately designed node-scoped worksheet schema exists. Selecting a single-company node SHALL NOT fabricate a worksheet `node_key` or silently switch the worksheet data to another scope.
3. WHEN the user only switches the right-side report, note or worksheet tab THEN the page SHALL preserve the left-tree `currentConsolEntity`; a tab switch SHALL NOT mutate the tree node or report/note node context.
4. WHEN worksheet batch loading succeeds with no matching rows THEN the component SHALL show a Chinese empty state and keep editable defaults; WHEN the request fails, returns a non-2xx response, or the payload cannot be parsed THEN the component SHALL show a distinct Chinese load-error state and SHALL NOT silently replace the response with `{}`.
5. THE worksheet save, batch load, prior-year extraction, G7 preview/import and formula-reload calls SHALL use the same parent-provided effective year; changing the page year SHALL invalidate the previous worksheet display before loading the new year.
6. THE total-branch notice SHALL depend on the verified consolidation mode and current worksheet context, not merely on a root/default node or a truthy company code; a single-company/mother-company selection SHALL NOT display the pure branch-consolidation notice unless the mode contract says the project is branch-only.

## 需求 8：合并工作底稿接入公式运行时

**用户故事**：作为公式管理使用者，我希望从当前合并项目/年度的工作底稿、单体报表、附注和相关底稿取数，并把公式结果真实写回工作底稿，而不是只在前端缓存中显示。

### 验收标准

1. THE formula runtime SHALL recognize `consol_worksheet` as a first-class domain with an explicit locator containing at least `project_id`, `year`, `sheet_key` and cell/row identity; it SHALL NOT infer worksheet scope from a static `${nodeKey}_${index}` string.
2. THE `consol_worksheet` reader SHALL batch-load persisted `consol_worksheet_data` under the exact project/year/sheet scope, distinguish missing cells from database/query errors, and preserve JSON object/array row shapes.
3. THE `consol_worksheet` mutation adapter SHALL prepare and apply real persisted mutations with optimistic version/CAS checks, transaction rollback on failure, and an auditable source formula/run identity; a successful plan SHALL be observable after a fresh database read.
4. Formula definitions for long-term investment, related-party balances and related-party transactions SHALL be able to reference the current tree node and its descendants as an explicit source scope. The source scope SHALL resolve through the enterprise-tree/node calculation services and existing report/note/workpaper readers, not by matching company-code prefixes.
5. Users SHALL be able to review and edit formula bindings before execution; execution results SHALL report applied, skipped, missing and failed cells separately in Chinese UI messages.
6. A formula run SHALL carry `project_id`, effective `year`, optional `node_key`, source scope, trigger and version/CAS metadata through planning, mutation, persistence and audit records; no front-end-only formula result qualifies as a completed write.

## 需求 9：动态股比事件与正式抵销链路

**用户故事**：作为合并执行人，我希望同一被投资单位在一个期间内发生 1 次、2 次或 3 次以上股比变动时，系统按事件顺序追溯每一段净资产和股比影响，并在确认后进入正式抵销建议/审批链路。

### 验收标准

1. THE share-change model SHALL support 1..N events for a company in a project/year; the UI SHALL generate columns/rows from persisted events and SHALL NOT treat `1 | 2 | 3` as the business limit.
2. Each event SHALL have a stable event ID, effective date, sequence/order, before ratio, after ratio, source/provenance, review status and optional linked G7 source item; reordering display rows SHALL NOT change event identity.
3. Events SHALL be sorted deterministically by effective date, then explicit sequence, then stable event ID; missing/duplicate dates or sequence conflicts SHALL be visible validation errors, not silently reordered into a different accounting meaning.
4. The period model SHALL expose opening net assets, each event-period net assets, ratio delta and closing net assets. The second and later events SHALL be inserted/rendered from the event collection and SHALL not depend on hard-coded `share_change_2/3` sheets.
5. The dynamic share-change calculation SHALL reconcile to the equity-method simulation and consolidation elimination suggestion chain, including disposal/additional investment, capital reserve/investment income effects and NCI where applicable; a suggestion draft SHALL remain non-posting until user confirmation and approval.
6. G7-10 and other G7 source rows SHALL be normalized into the same event model with source row identity and provenance; re-import SHALL be idempotent and SHALL not duplicate events.
7. Formal elimination suggestions SHALL carry project/year/node/source event IDs, calculation version and review status; only approved suggestions may enter the existing elimination recalculation/push chain. G7 linkage metadata alone SHALL NOT be treated as a formal elimination entry.
8. THE model SHALL provide a trace for three changes in one period: event 1, event 2 and event 3 each show their source data, applicable net-asset period, ratio before/after, calculated adjustment and downstream suggestion/approval state.

## 需求 10：新增范围的测试与运行时验证

1. THE worksheet frontend/backend contract tests SHALL cover parent-year propagation, successful empty data, distinguishable HTTP/load error, prior-year/G7 year propagation and preservation of the left-tree node across right-tab switches.
2. THE formula runtime tests SHALL use a real persisted worksheet row/object or array shape and verify reader miss/error distinction, adapter persistence, CAS conflict and fresh-read visibility; mocking only a front-end result is insufficient.
3. THE share-change tests SHALL cover 1, 2, 3 and at least 4 events, deterministic date/sequence ordering, stable IDs, duplicate import idempotency, three-event trace and draft-versus-approved elimination behavior.
4. WHEN local services are available THEN Playwright SHALL verify root, parent and single-company node behavior, effective-year worksheet request, distinct empty/error states, right-tab context preservation and dynamic 1/2/3-event rendering. Unavailable external data or services SHALL remain explicitly unverified.
5. Existing requirements 1~6 and properties P1~P9 remain in force; these additions do not mark implementation tasks complete.
