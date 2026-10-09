# 需求文档：合并附注节点级自动刷新与公式编排

> 工作流：Design-First。验收标准采用 EARS 风格；任务完成必须同时具备代码、定向测试和真实运行证据。
> 上游：`consol-tree-three-code-autobuild`、`consol-node-key-isolation-and-shared-context`、`consol-elimination-single-source-push`。
> 相关但不重复：`consol-note-refresh-multi-header-fix`、`consol-note-template-header-unification` 已完成表头列组、合并单元格表头、标题/序号和公式种子修复；本需求消费这些产物，不重新定义表头算法。
> 现有 schema 边界：消费已有 `consol_note_data.node_key`（V177 及现有 ORM/索引）；本需求不偷偷修改合并工作底稿 `(project_id, year, sheet_key)` 唯一语义，也不新增附注金额算法。

## 引言

合并树已经可以从项目中的本企业代码、上级企业代码和最终控制方企业代码自动推导节点。附注页也已经具备一套节点作用域基础和 `fill_by_formula()` 写入内核，但旧刷新、批量套用公式、重新汇总和事件编排仍存在多条未收敛路径：有的只在内存返回结果，有的从模板重建行，有的丢弃 `node_key`，有的没有传递项目实际 Listed/SOE 模板类型。这样会让用户看到刷新成功而数据库未变化，也可能覆盖人工单元格、混用两个节点的同一章节，或在合并附注与单体附注之间写错存储表。

本需求把“当前树节点、当前章节、当前模板、公式来源、持久化结果和刷新完成态”收敛成一条可验证链路。所有能改变合并附注金额的入口必须使用同一节点作用域和同一公式填入内核；事件只负责编排和报告结果，不能创建第二套金额计算。单体附注继续使用 `DisclosureNote`，合并 V2 表格继续使用 `ConsolNoteData`；两者通过既有公式/披露来源联动，不互相替代。

## 现状实证（本 spec 创建前核对）

以下事实来自当前工作树的代码阅读、全仓 grep 和定向测试基线，不是实现完成声明：

| 编号 | 现状 | 证据 | 对本需求的影响 |
|---|---|---|---|
| F1 | `fill_by_formula()` 已具备 `node_key` 校验、节点金额上下文、根节点 legacy 复制和 `manual_cells` 保护 | `backend/app/services/consol_note_formula_service.py` | 作为唯一写入内核，旧入口应委托它 |
| F2 | `refresh_note_by_formula()` 计算 `filled_rows` 后直接返回，没有调用保存流程，也没有复用人工保护 | `backend/app/routers/consol_note_sections.py` | 刷新响应可能假成功且不落库 |
| F3 | `apply_all_formulas()` 从模板行重建 `data`，没有复用节点行定位、插入行和人工格保护 | 同上 | 批量套用可能覆盖用户行 |
| F4 | `ReaggregateRequest` 没有 `node_key`、`standard`、`template_type`；前端 body 中的节点键会被 Pydantic 忽略 | `backend/app/routers/consol_notes.py`、`ConsolNoteTab.vue` | 旧重新汇总入口无法形成节点契约 |
| F5 | 旧 `reaggregate` 调用 `aggregate_section()`，该服务签名没有 `node_key` | `consol_note_aggregation_service.py` | 旧入口与 V2 节点写入链路分裂 |
| F6 | `generate_consol_notes_with_flag()` 未把项目实际模板类型传给 `generate_full_consol_notes()`，后者默认 SOE | `consol_disclosure_service.py` | Listed 项目可能走错附注模板 |
| F7 | `consol_cascade_refresh_service.refresh_all()` 使用全局 V2 flag，notes 步骤未使用项目级开关且未传模板类型 | `consol_cascade_refresh_service.py` | 级联刷新和直接刷新口径不一致 |
| F8 | `TRIAL_BALANCE_UPDATED`、`ADJUSTMENT_APPROVED`、`WORKPAPER_SAVED` 没有节点级附注自动填入 handler | `consol_trial_stale_handler.py`、`adjustment_approved_recalc_handler.py`、`main.py` | 四表/调整变化不会稳定落到附注章节 |
| F9 | EventBus 去重键目前只有 `wp_id`、`publish_token` 等身份字段，没有 `entry_group_id` | `backend/app/services/event_bus.py` | 同项目同期间不同调整组可能在 debounce 窗口内互相吞事件 |
| F10 | 合并页刷新完成只重载树；附注页没有按当前章节重读，stale 快捷入口只切页签而不实际调用重汇总 | `ConsolidationIndex.vue`、`ConsolNoteTab.vue` | 用户看到树完成但当前章节仍是旧快照 |
| F11 | 合并附注 V2 表格渲染使用 `ConsolNoteData`；单体附注写入使用 `DisclosureNote` | `consol_disclosure_service.py` 及对应 ORM | 必须明确存储边界，禁止把单体记录当合并表格数据 |
| F12 | 与表头相关的既有两个 spec 已完成，当前相关定向基线为 **98 passed, 9 warnings** | `test_consol_note_formulas.py` 等四个测试文件 | 新失败必须与该基线和并发改动分离归因 |

## 需求 1：所有合并附注入口使用同一节点作用域

**用户故事**：作为合并执行人，我希望在根节点、母公司节点、差额/汇总节点或单体节点之间切换时，同一附注章节始终读取和写入当前节点的数据。

### 验收标准

1. WHEN 请求提供 `node_key` THEN GET、PUT、公式填入、公式刷新、审核、批量套用公式、聚合、差额穿透和重新汇总 SHALL 同时限定项目、有效年度、章节和精确节点键。
2. WHEN 请求的 `node_key` 不存在于当前项目年度的自动企业树 THEN 服务 SHALL 返回明确的中文客户端错误，SHALL NOT 按企业代码前缀、冒号后缀或模糊匹配降级到根节点。
3. WHEN 当前请求是有效根合并节点且没有节点专属行 THEN 读取 MAY 回退到同项目、同年度、同章节的 legacy `node_key IS NULL` 行；该回退必须先由企业树确认根节点身份。
4. WHEN 根节点从 legacy 行读取后执行公式填入、刷新或保存 THEN 服务 SHALL 创建/更新根节点专属行，SHALL NOT 修改 legacy 行；非根节点 SHALL NOT 读取或修改 legacy 行。
5. WHEN 未提供 `node_key` 的旧调用进入兼容路径 THEN 该调用 SHALL 明确保持 NULL legacy 作用域，SHALL NOT 静默改成根节点作用域。
6. THE query 参数中的 `node_key` SHALL 优先于兼容 body 字段；空字符串、格式错误和 body/query 冲突 SHALL 有明确处理结果，不得被当作未提供。
7. WHEN 节点 A、节点 B 先后保存同一章节的不同值 THEN 两个节点重新读取 SHALL 各自返回自己的最后持久化值，且数据库不得出现跨节点覆盖。

## 需求 2：刷新与公式填入必须真实持久化并保护人工内容

**用户故事**：作为合并执行人，我希望点击刷新后数据库真的保存了公式结果，同时我的人工录入、插入行和特殊行形状不被模板重建覆盖。

### 验收标准

1. WHEN `/fill-by-formula`、`/refresh` 或等价旧入口成功 THEN 响应 SHALL 来自提交前已持久化的节点记录，且独立新读事务 SHALL 能读到相同结果。
2. THE `/refresh`、`/audit-all`、`/audit`、`/apply-formulas` 和兼容 `reaggregate` SHALL 复用 `fill_by_formula()` 或具有同等节点行定位、上下文加载、写回和人工保护语义的共享服务；不得保留一条会覆盖人工格的模板重建旁路。
3. WHEN 记录包含 `manual_cells` THEN 自动刷新 SHALL 保留所有人工保护单元格的原值，并在结果中报告保留数量或明细；缺少或损坏的保护元数据 SHALL 进入可观察错误，不得静默清空。
4. THE 填入逻辑 SHALL 支持已有对象行、二维数组行、按标签匹配的插入行和模板公式空值原因；保存后 SHALL 保持原始行形状和非目标字段。
5. WHEN 公式取数失败、节点上下文无效或目标行无法定位 THEN 事务 SHALL 回滚受影响的附注记录，响应 SHALL 返回逐项原因或明确 HTTP 错误，SHALL NOT 以模板值、零值或“成功”替代。
6. WHEN 多个章节批量刷新时 THEN 每个章节 SHALL 有独立结果状态；单个章节失败不得把其余成功章节伪装成全部成功，也不得吞掉失败计数。
7. THE 公式金额 SHALL 继续复用 `load_view_context`、`consol_calc_basis.node_measures` 和现有 `consol_report_values` 口径；本需求不得按 `company_code` 新增第二套合并金额算法。

## 需求 3：旧重新汇总入口与节点公式内核兼容

**用户故事**：作为仍使用旧“重新汇总”按钮的执行人，我希望它和新节点级公式填入产生完全一致的结果。

### 验收标准

1. THE `ReaggregateRequest` SHALL 显式声明并校验 `node_key`、有效年度、标准/模板口径及章节范围；前端 body 中的节点键不得因 Pydantic 忽略字段而丢失。
2. WHEN 旧 `reaggregate` 被调用且提供 `node_key` THEN 服务 SHALL 进入与 `fill_by_formula()` 相同的节点作用域和持久化路径；不得只调用不带节点键的旧 `aggregate_section()`。
3. WHEN 旧调用省略节点键 THEN 服务 SHALL 遵循兼容 NULL 作用域，并在响应中标示兼容模式，禁止暗中选择其他节点。
4. THE `/refresh`、`/fill-by-formula`、`reaggregate` 在相同输入、同一数据快照和相同模板下 SHALL 产生相同节点金额与人工保护结果；差异只能来自各入口明确声明的章节过滤。
5. WHEN 节点范围、标准或模板参数不一致 THEN 服务 SHALL 返回可定位的校验错误，SHALL NOT 以默认 SOE 或根节点静默替代。

## 需求 4：Listed/SOE 模板真实分流与单体/合并存储边界

**用户故事**：作为不同标准项目的执行人，我希望上市公司和国企项目使用各自附注模板，且单体附注与合并附注数据不会互相覆盖。

### 验收标准

1. THE `generate_consol_notes_with_flag()`、`generate_full_consol_notes()`、级联 `notes` 步骤及其调用方 SHALL 使用 `resolve_consol_standard()` / `_project_template()` 的实际项目口径传递 `template_type`；不得依赖 `generate_full_consol_notes()` 的默认 SOE。
2. WHEN 项目标准解析为 Listed THEN 生成、刷新、公式填入和附注审核 SHALL 使用 Listed 模板绑定；WHEN 解析为 SOE THEN SHALL 使用 SOE 绑定；解析失败 SHALL 返回明确错误或使用现有、可观测的安全降级，不得静默互换。
3. THE 合并 V2 表格渲染数据 SHALL 继续写入/读取 `ConsolNoteData`；单体附注路径 SHALL 继续写入/读取 `DisclosureNote`。`_persist_consol_sections_v2()` 的 provenance 写入不得被误当作 V2 表格渲染载荷。
4. WHEN 同一项目同时存在单体附注和合并附注刷新 THEN 两条路径 SHALL 使用各自表和作用域；一条路径失败不得伪造另一条路径已完成。
5. THE 已完成的多级表头、合并单元格、标题/序号和公式种子契约 SHALL 保持通过；本需求只修复它们上游的模板选择与节点刷新编排。

## 需求 5：数据变化后的附注自动刷新边界

**用户故事**：作为执行人，我希望四表入库、调整审批或底稿保存触发既有公式编排后，相关合并附注节点能够自动更新，并且上游事务不被附注刷新失败拖垮。

### 验收标准

1. WHEN `TRIAL_BALANCE_UPDATED` 完成并且项目启用合并附注 V2 THEN 编排器 SHALL 在独立数据库会话中为该项目/年度遍历当前企业树的有效节点，按已启用的标准/模板和章节策略执行节点级公式刷新，并记录每个节点/章节结果。
2. WHEN `ADJUSTMENT_APPROVED` 经过现有调整重算并发布下游 `TRIAL_BALANCE_UPDATED` THEN 附注刷新 SHALL 通过该下游统一入口触发一次；不得因审批事件和 TB 事件重复写同一章节。
3. WHEN `WORKPAPER_SAVED` 只影响与附注无关的字段或项目未启用 V2 THEN handler SHALL 跳过并记录原因；不得为每次保存无条件重写所有附注。
4. WHEN 同一事件在 debounce 窗口内重复到达 THEN 去重键 SHALL 至少区分项目、年度、事件类型、底稿/发布身份和调整 `entry_group_id`（当事件携带该字段时）。不同 `entry_group_id` 的调整事件不得互相吞并。
5. WHEN 某个节点或章节自动刷新失败 THEN handler SHALL 记录失败状态、异常摘要和可重试上下文，SHALL NOT 回滚或阻断已经提交的上游 TB/调整/底稿事务；失败不得伪装为全量成功。
6. THE 自动刷新 SHALL 使用现有公式管理/附注公式内核，不得通过前端页面打开、模板复制或第二套金额聚合完成“自动刷新”。
7. THE 节点遍历 SHALL 以当前树的有效节点为准；重复企业代码但角色不同的节点必须分别刷新，树上同一节点不得重复写入。
8. WHEN 项目没有有效合并树、没有可刷新的章节或 V2 开关关闭 THEN handler SHALL 返回可观察的 skipped 状态及原因，不得把 skipped 记为 success。

## 需求 6：前端刷新完成态、章节重载和旧入口联动

**用户故事**：作为合并页用户，我希望点击刷新后看到的就是当前树节点最新章节，并能区分树计算完成、节点附注持久化完成和失败。

### 验收标准

1. THE `ConsolidationIndex.vue` SHALL 保存当前 `{code, name, nodeKey}` 和当前章节标识，并在级联刷新完成后通知 `ConsolNoteTab` 重读当前节点/当前章节；只刷新树不满足完成态。
2. WHEN 当前节点或章节在刷新期间变化 THEN 旧响应 SHALL NOT 覆盖新上下文；附注组件 SHALL 继续使用 `noteRequestGuard` 或等价的上下文序列保护。
3. THE 页面状态 SHALL 至少区分 `tree_pending/tree_done`、`note_pending/note_done` 和 `note_failed/skipped`；用户可见状态使用中文，且失败原因可定位到节点/章节。
4. WHEN 当前章节刷新完成 THEN `ConsolNoteTab` SHALL 重新读取持久化记录，而不是只把内存中的 `filled_rows` 当作完成证据；重读失败必须显示错误。
5. WHEN 用户从 stale 快捷入口执行重新汇总 THEN 页面 SHALL 真正调用节点感知的 `reaggregate`/刷新 API，并在成功后重读当前章节；只清除 stale 标记或切换页签不满足需求。
6. THE 附注 API 请求 SHALL 继续携带当前 `nodeKey`；快速切节点时，旧章节响应、旧刷新结果和旧完成态不得提交到新节点。

## 需求 7：刷新响应、审计与可观察性

1. EVERY 刷新/公式编排结果 SHALL 包含项目、有效年度、节点键（或明确 `legacy_null`）、模板/标准、章节或章节范围、状态、持久化记录标识及保留人工格数量。
2. 自动 handler SHALL 记录触发事件 ID、去重键、开始/结束时间、节点/章节结果和异常摘要；日志不得包含不必要的附注正文或敏感凭据。
3. HTTP 端点 SHALL 保持现有 ResponseWrapperMiddleware 信封和中文消息契约；成功响应不得把失败章节放在无状态的普通 rows 字段中掩盖。
4. 节点公式刷新 SHALL 可通过独立新读、审计结果或测试数据库快照确认，不能只凭 HTTP 200、前端 toast 或内存对象判定完成。

## 需求 8：测试、构建与真实运行验收

1. THE backend SHALL add real ORM/SQLite or适用真实 PG tests for two node keys, legacy NULL fallback/copy-on-write, refresh persistence, manual cell protection, object/2D rows, old reaggregate node contract, Listed/SOE routing, and per-node failure reporting.
2. THE HTTP tests SHALL issue real FastAPI requests for valid/invalid node key, query/body precedence, refresh persistence, reaggregate payload, permission dependency and response envelope; service-only mocks are insufficient for endpoint acceptance.
3. THE event tests SHALL cover `TRIAL_BALANCE_UPDATED` automatic node refresh, adjustment downstream de-duplication, `WORKPAPER_SAVED` skip boundary, independent-session fail-open behavior and `entry_group_id` isolation.
4. THE frontend tests SHALL cover current node/section reload on refresh completion, stale entry invoking an API, completion-state transitions and out-of-order response protection; target Vitest and ESLint SHALL pass.
5. WHEN the frontend can run THEN a single-region `vue-tsc` SHALL pass for changed files and a TS2322 mutation SHALL prove the target files are included; if full typecheck OOMs, the exact limitation SHALL remain recorded.
6. WHEN `start-dev.bat` and required services are available THEN Playwright SHALL verify root/parent/single-company node switching, current report/note reload, two-node same-section isolation, persisted formula refresh, manual cell protection, and header/title/sequence display; unavailable external services remain explicitly unverified.
7. ALL counts and file/endpoint inventories in the spec SHALL be recomputable from current files or database probes; no line-number-only acceptance criterion is valid.

## 非功能约束与降级

- 首选已有服务、ORM、EventBus 和公式管理；不得新建第二个合并金额计算器。
- handler 的 fail-open 只允许隔离自动下游失败；节点作用域、权限、归属和公式数据错误仍须可见，不能改成静默成功。
- PostgreSQL 并发和真实树数据需要环境；无真实 PG 时使用真 ORM/SQLite 验证事务与行形状，同时把 PG/Playwright 保持未完成。
- `start-dev.bat` 不可启动时，保留 API/组件证据并明确浏览器验收阻塞；不得用静态检查替代浏览器实测。
- 全量 `vue-tsc` 在历史环境中可能 OOM；采用单区域 tsconfig + TS2322 变异证明，不能把 OOM 的零错误输出报告为通过。
- 尚未完成的 formula-push note rollout 不得被本需求顺带宣称为所有科目闭环；自动刷新范围以已有模板/章节绑定和项目开关为准。

## 范围外

- 不修改已有 V177 或偷偷增加工作底稿 node_key schema。
- 不重做企业树三代码自动构建、表头合并单元格算法、标题序号算法或单体附注数据模型。
- 不把 Listed/SOE 模板差异用前端标签猜测替代后端项目标准解析。
- 不把自动刷新失败转成上游业务事务失败；不绕过现有调整审批、TB 显式发布门或公式管理权限。
