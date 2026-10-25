# 角度 D 审计：溯源可解释性、治理安全、测试运行证据与 spec 一致性

> 审计基线：`HEAD 779d8b43619c5946c198e11ca35b1ad9330c5dfa`，分支 `spec/disclosure-note-doc-upload-and-batch-fill`。先读 `00-ground-truth.md`，再核对当前 HEAD 源码、现有测试与已运行服务。本报告只新增本文件，未修改产品代码、配置、spec、Git 索引或数据库业务数据。
>
> 证据等级：**E1** = 本次直接运行/探针/当前服务返回；**E2** = HEAD 生产源码、调用签名或静态全仓扫描；**E3** = 现有测试或 spec 文字声称，未独立证明真实运行。结论优先级按 E1 > E2 > E3。
>
> 工作区并发说明：开工基线已有 `.kiro/specs/INDEX.md`、`audit-platform/frontend/src/components.d.ts` 和 S-cycle 文件变更；收尾时另有并发会话新增/暂存 S-cycle 文件。本文不以这些未提交内容证明任何公式能力。本文引用的产品源码路径均未出现在两次 `git status` 的 modified/untracked 清单中，可视为当前 HEAD 内容。

## 一、结论摘要

**总评：公式管理已具备较强的“定义治理”和局部执行可观测能力，但尚未形成用户可依赖的全平台逐值溯源闭环。** 全局/项目/模板层、冲突待确认、公式推送状态、底稿公式 CAS 和项目级门禁已有实质实现；但最终值的来源地址、输入实际值、计算步骤、定义版本、刷新时间和反向跳转分散在互不贯通的组件与数据结构中。统一 lineage 主链当前还有确定性断链，现有测试却全绿。

最高风险如下：

1. **P0：统一 lineage 的 wp 上下游调用签名错误，生产调用恒被 `except Exception` 吞成空列表。** `trace_upstream/trace_downstream` 需要 `(db, project_id, source, identifier)`，`UnifiedLineageService` 只传了三个参数。本次直接调用探针得到上下游均 `[]`；对应 10 余个单测因 mock 接受任意参数而全部通过。【E1+E2】
2. **P0：统一 lineage 的附件查询未按 `project_id` 隔离。** 路由虽校验了请求项目，但 `_query_attachments` 只按 `target_type + target_ref LIKE` 查询；`attachment_lineage` 表本身也没有 `project_id`。相同引用在不同项目出现时可能返回别的项目附件名称、类型与 ID。【E2】
3. **P0：同步审计 helper 的哈希链并发保护缺失。** worker 明确使用 PG advisory transaction lock 防同项目并发分叉，但 `append_audit_log` 没有同款锁；全仓有 **41 个直接调用点、25 个文件** 走该 helper。并发写可读到相同 `prev_hash`，形成分叉。【E1 扫描+E2】
4. **P1：`FORMULA_EXECUTE_TIMEOUT=10` 只是配置，无任何执行路径消费。** 全仓只在配置定义和系统设置展示中出现；公式 AST 无节点数/嵌套深度限制，底稿保存表达式也无长度上限。【E2】
5. **P1：自定义函数治理名义上“全局”，实际是单进程、单请求实例状态。** 注册后 handler 留在模块 `_REGISTRY`，但新 `FormulaEngine()` 的自定义函数列表为空、注销返回 false；参数未代入。自引用函数可递归到 Python 上限后，外层丢弃内层错误并返回 `ok=True,value=0`。本次探针已复现。【E1+E2】
6. **P1：全局公式发布先提交定义，再 best-effort 发事件；事件失败无 durable outbox/retry。** 失败只写 logger；降级记录只在进程内 list，重启丢失。可能出现“全局公式已生效，但项目未标 stale/未重算”的永久不一致。【E2】
7. **P1：公式历史回滚接受客户端提供的 `target_formula`，并在未带版本时自动取当前版本。** 服务只用日志 ID 定位公式位，不校验目标公式等于该日志的 `old_formula`；UI 也不传 `expected_version`。因此“回滚”可写入任意公式，并绕过客户端陈旧版本检测。【E2】
8. **P1：可解释性测试存在典型 mock 假绿。** 来源 tooltip 测试把“底稿/报表/附注”仅作为三组 props 直接挂同一个组件，没有验证三个真实宿主；生产实际只在 D3 和 S34 两个文件挂载。`LineageGraphPanel` 有直接组件测试但生产模板零挂载；`FormulaTracePopover` 则既无生产挂载，也未找到同名测试。【E1 扫描+E2+E3】

## 二、溯源与可解释性

### 2.1 用户从最终值能看到什么

| 要素 | 后端是否保存/返回 | 前端是否实际展示 | 结论 |
|---|---|---|---|
| 公式表达式 | 报表配置、`formula_setting`、`wp_formula.expression`、附注 JSON/公式表均保存；底稿列表 API 返回 expression【E2】 | 公式管理中心和编辑框展示；D3/S34 tooltip 展示【E2】 | **有，但不是所有最终值都可从值本身点开看到** |
| 输入地址 | `wp_formula.refs/source_scope/binding`、ACNR、依赖解析器均存在【E2】 | tooltip 只显示一个 ACNR `semantic_label`；公式管理中心加载底稿行时丢弃 `refs/source_scope/binding`；依赖面板只显示标签/addr_id，不可点击【E2】 | **后端局部保存，前端大多未消费** |
| 输入实际值 | L1 `FormulaResult.trace` 会写 `TB/ROW/REPORT/... = value`；push state 保存公式值、当前值、已推送值【E2】 | `FormulaDebugPanel` 临时展示 trace；`FormulaPushVerifyPanel` 展示推送专项三值；普通报表/附注/底稿最终值没有统一输入值展开【E2】 | **仅调试器与推送专项可见** |
| 来源模块/项目/年度/底稿/单元格 | `source_scope` 可含项目、年度、节点和域；`wp_formula` 有 project/wp/sheet/cell；路由上下文本身含项目/年度【E2】 | 公式管理中心仅保留 sheet/target/version，覆盖真实 `formula_source` 为“底稿公式(wp_formula)”并丢弃 scope/binding；tooltip 只显示语义标签【E2】 | **保存信息比展示信息完整，无法从最终值一次看全** |
| 计算步骤 | L1 trace 是字符串步骤；debug API 返回【E2】 | 只在公式编辑/调试面板展示，普通结果页不展示，也不持久绑定到最终值版本【E2】 | **临时可调试，不是审计级逐值 lineage** |
| 定义版本/基线版本 | `EffectiveSlot.to_dict()` 返回 global/local/base version；`wp_formula.definition_version` 返回【E2】 | 层级标签会显示“全局/模板/本项目/暂缓采用”；版本主要用于 CAS 和预览，普通最终值不显示其计算所用版本【E2】 | **治理层有版本，结果层无版本绑定** |
| 最后计算/刷新时间 | `wp_formula.last_computed_at` 存储且列表 API 返回；cross-check 返回计算时间；push run/state 有时间【E2】 | 公式管理中心映射底稿行时未保留 `last_computed_at`；生产中 D3/S34 的 tooltip 均未传 `lastComputedAt`，所以只会显示“尚未计算”；表间审核问题面板可显示最近计算【E2】 | **局部有，普通 tooltip 实际未接线** |
| 反向跳转 | Unified lineage/LocateTarget、ACNR jump、依赖图均存在【E2】 | 报表/TB 有专用数字溯源弹窗；依赖面板节点无 click；通用 `LineageGraphPanel` 生产零挂载；`FormulaTracePopover` 生产零挂载【E2】 | **模块内局部可跳，全平台反向跳转未闭环** |

### 2.2 “后端保存了 lineage”与“前端展示了 lineage”必须分开

**后端已有的原材料：**

- `WpFormula` 保存 `refs`、`source_scope`、`binding`、`formula_source`、`reference_formula_id`、稳定 sheet/row/field key、`definition_version`、`last_computed_at`。【E2】
- `FormulaResult.trace` 记录函数及实际值；debug API 返回 `trace/errors/warnings/context_summary`。【E2】
- `EffectiveSlot` 返回当前层、全局/本地/基线定义与版本、模板来源 ID、pending/pinned/disabled。【E2】
- push state 保存 `last_formula_value/current_value/last_pushed_value/state`，这是目前最接近“公式值—现值—推送值”闭环的专项实现。【E2】

**前端实际消费缺口：**

- `FormulaManagerDialog.loadWpFormulas()` 只保留 expression、分类说明、sheet/cell、stable key、definition_version；没有保留后端返回的 refs、source_scope、binding、last_computed_at、created/updated 信息，还把真实三态 `formula_source` 替换成固定中文字符串。【E2】
- `GtFormulaSourceTooltip` 自身只支持“表达式 + 一个来源标签 + 最近计算时间”，不支持输入值列表、项目/年度、定义版本、计算步骤或跳转。【E2】
- 全仓生产模板只有 **2 个文件**使用该 tooltip：D3 的 4 个静态挂点和 S34 的 1 个循环挂点；没有报表或附注宿主。【E1 静态扫描】
- 两个生产宿主均没有传 `lastComputedAt`，因此该组件的“最近计算”能力在真实挂点上恒显示“尚未计算”。【E2】
- `FormulaHistoryTab` DTO 含 `trace`，模板却完全不渲染 `entry.trace`；且 `specAReady` 永久写死 `false`，用户始终看到“哈希链尚未完成/当前是懒建表”的过期警告，而后端实际已查询 `audit_log_entries` 哈希链。【E2】

### 2.3 统一 lineage 主链的确定性故障

1. `wp_trace_service.trace_upstream` 签名为 `(db, project_id, source, identifier)`；`trace_downstream` 同样需要四参。【E2】
2. `UnifiedLineageService._query_wp_upstream/_downstream` 只调用 `(db, project_id, identifier)`，必抛 `TypeError`。【E2】
3. 两个方法都用 broad `except Exception` 写 debug 日志后返回空数组，API 因此把故障伪装成“无上下游”。该服务共有 **5 个 broad catch**，各子源失败都降为空数据。【E2】
4. 本次直接探针打印真实签名，并调用两个 wrapper，结果均为 `[]`。【E1】
5. `tests/services/test_unified_lineage_service.py` 用 patch 替换了 trace 函数，mock 不校验真实签名，所以该文件随本次 146 例测试一起通过。【E1+E3】
6. 对 `report_row` 和 `note_cell`，统一服务都调用 `ReportTraceService.trace_section`；报表行代码被当成附注章节号处理，类型语义也未真正统一。【E2】

### 2.4 依赖图与失败定位的边界

- 依赖面板目标只支持 `report:*` 和 `tb:*`，不能把 wp/note/push 公式作为中心节点；虽会扫描六域下游，但不是通用任意节点图。【E2】
- 依赖解析使用只认**单引号**的正则；L1 parser 明确支持单双引号。本次用 `TB("1001","期末余额")` 直接求值得到 `123` 且 `ok=True`，但 `upstream_refs()` 返回空列表。【E1+E2】
- 这会漏报合法双引号公式的依赖，进而削弱删除影响分析、下游计数和责任定位。【E2】
- `GtFormulaIssuePanel` 能展示校对项的 description、左右实际值、差异和原始 `addr_id`，这是有效的责任数据线索；但 `addr_id` 只是文本，无 resolve 后语义、无项目/年度/版本、无点击跳转。【E2】
- 严格预载路径会把 NOTE/PREV/AUX 等缺数原因写入 warnings/errors，调试面板能看见；普通业务页面是否展示取决于各自调用方，尚无统一错误责任对象。【E2】

### 2.5 自动值、人工覆盖、推送值、模板继承值的区分

- **模板/全局/项目层：较好。** EffectiveSlot 有 `global/template/project/pinned/preset`，公式管理表显示层级标签和 pending；模板订阅/冲突弹窗有三方定义与决策。【E2，相关测试本次 21+66 例通过 E1】
- **底稿公式来源：后端有、管理中心展示失真。** 后端 `formula_source ∈ preset/custom/reference`，编辑对话框也支持三种来源；但公式管理中心组装列表时统一改为“底稿公式(wp_formula)”，看不到真实来源。【E2】
- **人工覆盖：分散。** D1/D4 等业务组件和 push verify 能标人工覆盖；公式管理中心没有全域统一覆盖标识。【E2】
- **推送值：仅 push 专项完整。** `FormulaPushVerifyPanel` 能显示当前值、已推送值及 consistent/diverged/manual_override/stale；普通附注、报表和底稿结果没有统一推送来源标记。【E2】
- **自动值：依赖具体业务组件。** 一些单元格有“自动计算/只读”样式，但没有统一 provenance 字段绑定到最终值。【E2】

## 三、治理与安全

### 3.1 鉴权、对象归属与跨项目隔离

**公式主链的已完成部分：**

- `/api/formula/execute` 和 batch 按请求体 `project_id` 调 `assert_project_permission(readonly)`；batch 拒绝混合项目/年度。【E2】
- debug 按请求体项目判 readonly；底稿公式按 `wp_id → wp.project_id` 反查后判 readonly/edit，并校验 body/query 项目一致；formula settings 项目端点使用 readonly/edit；全局发布/候选审核用 admin；模板可见、管理、订阅分别按 viewer/owner/admin/项目权限；push 路由按 readonly/edit。【E2】
- 本次包含真实权限世界的公式鉴权测试通过；拒绝请求的业务调用次数为 0 的断言仍绿。【E1】

**全仓同类反模式规模：**

- 路径含 `{project_id}` 的端点现算 **424** 个；其中 **200** 个只有登录/角色门、没有项目级门禁。无任何鉴权的 6 个都是已登记 410/501 桩端点。【E1】
- 项目在 body/query 的端点现算 **227** 个；项目级门禁 133、仅登录/角色 88、无会话门 6。6 个无门项里 1 个 MCP 自签名，另外 5 个为已登记 Metabase/feature flag/B60 欠账。【E1】
- 公式命名路由在两套扫描结果中没有残留“非项目级”项，说明 formula-governance 的定向收口有效；但平台整体项目隔离仍不能以“有全局守卫”替代逐对象验证。【E1】

**当前确定性对象隔离缺陷：**

- `UnifiedLineageService._query_attachments(project_id, ...)` 完全不使用 `project_id`；SQL 只过滤 target type/ref。路由上的项目门禁无法防止“已获 A 项目权限的用户，通过 A 的 lineage 请求读到 B 项目相同 target_ref 的附件”。【E2】
- `attachment_lineage` V029/ORM 无 project_id；若修复只能通过 join attachment/target 对象反查项目，或迁移补 project_id 并回填。【E2】

### 3.2 公式注入与危险求值

- L1 使用自定义递归下降 AST 和 `safe_eval_expr(ast.parse)` 白名单节点，不调用 Python `eval/exec`；公式相关生产文件全仓搜索没有实际 `eval()`/`exec()` 调用。【E2】
- `formula_state` 会拦截 eval/exec/import/open/os/sys/subprocess/反射/URL/UNC，并按 `_REGISTRY` 拒绝未登记函数；底稿保存路径在写库前调用该分类器。【E2】
- 风险不在任意代码执行，而在**验证口径分裂**：全局设置的 report/tb_detail/cross_check 定义写入没有统一调用 `validate_definition/classify_formula`；`validate_definition` 只对模板创建/发布及 wp/push/note/consol_note 做域校验。管理员可把结构损坏或语义无效定义传播到大量项目，执行期才失败。【E2】
- `RegisterFunctionRequest` 的 name/expression/param_names 无长度和数量约束；表达式校验只做关键词和简化 AST，handler 不代入参数。【E2】

### 3.3 资源上限、循环与超时

- debug 单条公式上限 2000 字符；合并附注公式也有限长；底稿 `FormulaSaveRequest.expression`、批量 item expression、中央 `FormulaRequest.params` 没有公式文本长度上限。【E2】
- 底稿批量保存有 `_BATCH_MAX_ROWS`；formula settings 发布最多 2000 个 change、应用最多 500 项目；中央 `/batch-execute` 的请求 list 没有上限且逐条串行执行。【E2】
- `parse_to_ast` 只有 2048 条 LRU 缓存容量，不是表达式复杂度限制；无 AST 节点数、嵌套深度或执行预算。【E2】
- `FORMULA_EXECUTE_TIMEOUT` 仅有 **2 处引用**：配置定义、系统设置展示；执行器没有 `wait_for`、deadline 或取消逻辑。【E2】
- 自定义函数没有依赖图/循环检测。本次注册 `SELF_AUDIT() = SELF_AUDIT()`，执行到 Python recursion limit；最内层记录错误，外层 handler 只取 value，最终返回 `ok=True,state=ok,value=0`。【E1】
- 公式行的 ROW/SUM_ROW 本身从预载 cache 取值，不会递归求值；跨公式循环风险主要落在自定义函数、外部预载/传播图，不是 L1 行引用递归。【E2】

### 3.4 并发 CAS

- 全局发布有 domain lock、request_id 幂等、逐位 expected version，缺版本 428、冲突 409；项目设置和模板发布也有版本令牌。【E2，本次相关测试通过 E1】
- `wp_formula` 更新使用 `UPDATE ... WHERE definition_version=:expected RETURNING`，是数据库原子 CAS；批量保存任一冲突整批回滚。【E2】
- **删除缺口：** `DELETE /workpapers/{wp_id}/formulas/{formula_id}` 不接受 expected_version，读取后直接删除；并发编辑后仍可被旧界面删除。【E2】
- **回滚缺口：** UI 不传 expected_version；服务自动读取当前版本再写，因此陈旧页面发出的回滚也会覆盖当前定义。【E2】
- legacy `/user-formulas` 批量更新由服务端读取当前版本后代客户端提交，能防同一事务窗口竞争，但不能证明用户编辑基于哪个旧版本，仍有顺序式 lost update 风险。【E2】

### 3.5 审计不可抵赖性

**已有能力：**

- formula 变更统一写 `audit_log_entries`，记录真实 user/project/action/old/new/result/trace 等；表无应用层 update/delete 路径；verify-chain 能重算哈希并定位断点。【E2】
- formula history 按项目过滤，回滚前再验证 source log 属于本项目。【E2】

**不能称为“不可抵赖”的原因：**

1. `append_audit_log` 缺 worker 已有的 advisory transaction lock；41 个直接调用点均可能并发分叉。【E1+E2】
2. `_get_prev_hash` 吞掉任何异常并返回 genesis，查询故障可静默开启新链。【E2】
3. verify-chain 对第一条 `prev_hash != genesis` 会直接接受并把它设为期望值；删除链前缀后仍可通过。时间范围查询也无法证明与范围外前序链连接。【E2】
4. 没有外部签名、WORM 存储或可信时间戳；拥有 DB 写权限的人可重算后重写整条链。它是**防无痕篡改哈希链**，不是密码学不可抵赖。【E2】
5. helper 写入的 `session_id/ip/ua/trace_id` 均为 None；身份只有应用 user_id。【E2】
6. `POST /formula-audit-log/{project}/{year}` 允许项目 edit 成员自行提交任意 old/new/result/trace，内容未绑定一次真实公式变更事务；虽能追到提交人，但日志事实可被合法用户注入误导记录。【E2】
7. 历史路径中的 `year` 没有存入哈希 payload，GET 明确忽略 year，因此用户选 2025 仍会看到该项目所有年度的同类记录。【E2】

### 3.6 发布、回滚、删除影响与批量传播

- 全局发布前端通常先 preview，并对 inherit/follow/conflict/pinned/frozen 分类；冲突可采用、保留或待确认。后端 publish API 本身不要求携带“已预览摘要哈希”，管理员可直接调用发布。【E2】
- 一次发布最多 2000 公式位，并扫描适用范围全部项目；`apply_to_projects` 最多 500 目标且逐项目验证 edit。限制存在，但影响面仍大，缺少发布审批双人复核或最大受影响项目硬阈值。【E2】
- 定义事务成功后才发 `FORMULA_CONFIG_CHANGED` 是正确顺序；但发布事件失败被吞，且没有 formula-settings outbox。`stale_degraded_logger` 只存在进程内存，重启后证据消失。【E2】
- 报表传播会先提交 stale 再重算，失败保留 stale；这是正确的 fail-visible 设计。wp/note/consol/push 也按项目和归档状态处理。【E2】
- 依赖面板可以做局部影响预览，但解析只支持 report/tb 目标并漏双引号；不能作为删除安全门。【E1+E2】
- 底稿公式删除只弹“删除某单元格公式”的通用二次确认，不展示下游依赖数量；删除后的 reference dependent 失效传播还是 fail-soft，失败不阻止删除。【E2】
- 模板有活跃订阅时禁止删除，优于普通底稿公式删除；合并附注删除是软删且要求版本。【E2】

## 四、测试与运行证据

### 4.1 本次实际执行结果

| 命令 | 结果 | 说明 |
|---|---:|---|
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/test_formula_engine.py tests/test_formula_audit_pbt.py tests/services/test_unified_lineage_service.py tests/formula_settings/test_endpoints.py tests/formula_settings/test_formula_endpoint_authz.py tests/test_project_endpoint_authorization_baseline.py tests/test_project_endpoint_authz_body_carried.py -q -p no:playwright`（cwd `backend`） | **146 passed**, 4 warnings，124.32s | 引擎、审计属性、lineage service、settings 端点、公式鉴权及两维鉴权基线 |
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/test_formula_push_coverage.py tests/test_formula_push_rules.py tests/test_formula_push_account_single_source.py tests/test_formula_push_k1_integration.py -q -p no:playwright` | **98 passed**, 213 warnings，22.09s | 当前 81 个 push binding 的清册/规则/科目单源与 K1 SQLite 集成 |
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/formula_settings/test_templates.py tests/formula_settings/test_template_endpoints.py tests/formula_settings/test_propagation.py -q -p no:playwright` | **21 passed**, 1 warning，12.29s | 模板订阅/发布、端点与传播 |
| `rtk npx vitest --run src/components/formula/__tests__/GtFormulaSourceTooltip.spec.ts src/components/formula/__tests__/formulaHistoryRollbackGate.spec.ts src/__tests__/LineageGraphPanel.spec.ts src/components/formula/__tests__/formulaComponentMounts.spec.ts`（cwd frontend） | **4 files / 33 tests passed**, 39.52s | tooltip、历史回滚门、lineage 组件、formula 目录挂载守卫 |
| `rtk npx vitest --run src/components/formula/settings/__tests__ src/components/formula/__tests__/FormulaTemplateManage.spec.ts src/components/formula/__tests__/FormulaTemplateSubscribeDialog.spec.ts src/components/formula/__tests__/FormulaPushPanel.spec.ts` | **9 files / 66 tests passed**, 28.29s | 全局/项目/模板冲突 UI 与 push 面板 |
| live `GET /api/health`、`GET /openapi.json` | health `code=200,status=healthy,migrations=203`；OpenAPI 含 **111** 个路径名带 formula，且含统一 lineage 路由 | 只证明当前服务健康和路由注册，不证明进程与 HEAD 字节一致 |

本次还执行了只读/进程内探针：

- 鉴权扫描：path 424 / identity-only 200 / unauthorized 6（均为桩）；body/query 227 / project 133 / identity 88 / none 6。【E1】
- push 注册表：81 个 wp_code。【E1】
- `append_audit_log` AST 调用点：41 calls / 25 files。【E1】
- unified lineage 真实签名对照：wrapper 调用结果 upstream/downstream 均空。【E1】
- 自引用 custom function：最终 `ok=True,value=0`，新 engine list 空、unregister false。【E1】
- 双引号公式：L1 求值 `123`，依赖解析 `[]`。【E1】

### 4.2 这些绿灯没有证明什么

- unified lineage 测试把下游函数全部 patch 掉，未调用真实签名；因此 146 绿里包含确定性假绿。【E1+E3】
- `GtFormulaSourceTooltip.spec.ts` 的“三处挂载”只循环三组 props 直接 mount 组件，不读任何真实宿主；不能证明报表/附注接线。【E2】
- `LineageGraphPanel.spec.ts` 直接 mount 一个生产零挂载组件；`formulaComponentMounts.spec.ts` 只扫 `components/formula`，不会发现位于 `components/workpaper` 的 LineageGraphPanel 死链。【E2】
- FormulaDependencyPanel、FormulaDebugPanel、GtFormulaIssuePanel 没有找到同名组件测试；它们的关键展示/跳转行为没有本轮直接组件证据。【E2】
- 98 个 push 用例证明当前规则和 SQLite 集成一致，不等于 81 个 binding 都经过真实 PG、真实项目数据和浏览器逐项验收。【E1】
- 21 个 settings 模板/传播测试没有证明 post-commit EventBus 故障后的恢复，因为当前实现没有 durable retry。【E1+E2】

### 4.3 未验证项及原因

- **未做登录态 Playwright。** 本步严格只读；登录、刷新 token、打开自动保存页面可能写 Redis/session、审计日志或业务数据。源码和现有组件测试足以确定上述接线缺口，但不能替代用户实际视觉走查。
- **未运行 pg_only/CAS 真 PG 写入测试。** 用户明确要求 DB 仅只读；临时 schema、事务写入即使回滚也不符合本步边界。
- **未调用有写副作用的 publish/apply/rollback/delete/push API。** 仅检查源码、现有测试和无认证健康/OpenAPI。
- **未跑全量 pytest/vitest。** 本步目标是公式治理、溯源和相关 spec 的代表性证据；全量测试耗时大且部分测试会改写跟踪快照/连接真实环境。
- **未对 live 公式数据逐值查询。** 需要登录或 DB 读凭据；当前任务没有提供安全的只读项目会话，且不能确认运行 worker 精确对应 HEAD。

## 五、重点 spec 与 HEAD 一致性

| spec | 历史声称 | HEAD/本次证据 | 判定 |
|---|---|---|---|
| `formula-global-settings-sync` | checkbox 36/36；文首又写“35/36 + 8.2 完整 UI 未做” | 全局/项目/模板层、CAS、冲突、订阅和传播代码在 HEAD；相关后端 21、前端 66、端点组均绿。但 tasks 的 8.2 明文仍称完整登录态 UI 未做；S5 明文称旧 `wp_formula_service.save` 写路径未接同步内核，当前该 service 仍独立写 `wp_formula`【E1+E2+E3】 | **文档假绿 + 产品闭环部分完成。** `[x]*` 与“未做”并存；“一处改全处”对旧底稿写路径仍是双轨 |
| `formula-governance-coverage-closure` | 36/36 | 关键公式端点项目鉴权、push 治理、目录、模板/传播当前存在；实施提交 `74c7c0a8f` 与 `645a79b8f` 均是 HEAD ancestor；本轮鉴权/settings/push 目标测试全绿【E1+E2】 | **主张大体与 HEAD 一致，但范围不能外推到全平台。** 全仓仍有 200/424 路径型及 88/227 body/query 型 identity-only 端点；lineage 漏项目过滤不在该守卫口径 |
| `formula-fetch-and-wp-generation-defect-closure` | 19/19，实施 commit `d9f08b55c` | `d9f08b55c` 是 HEAD ancestor；相关 preload/debug/push 当前代码存在，本轮引擎/push 代表测试绿【E1+E2】 | **未发现依赖未提交代码。** 本轮未重跑其 103 文件/真实数据全套，不能重新背书历史数量 |
| `formula-fetch-followup-defect-closure` | active 30/34 | tasks 明确未完成 3.6、4.2、4.3、4.5；4.2/4.3 后端门禁依赖另一个未入库 spec，2026-10-25 复查仍未入库；当前工作区也没有这些产品文件的未提交修改【E2+E3】 | **状态诚实，非假绿。** 但“前端已隐藏入口、后端未门禁”的阶段性不一致仍是发布风险 |
| phase2 formula-push engine | 18/18 | 当前 81 binding，规则/清册/K1 集成 98 例通过；phase2 E1 能力已被后续扩展【E1+E2】 | **当前 HEAD 有实质实现。** 历史真实写入证据不在本步复验范围 |
| `formula-push-all-subjects-rollout` | tasks 26/26 `[x]` | 同一 tasks 内 17/18/19/22/23/25/26 明文写“待补/待实施/未真实推送/后端 stale 仅拦截验证”，与 `[x]` 冲突。后续 HEAD 已补到 81 binding、TierA/D4 与 K1 editable rules；但 `_k1_1_import_handler` 当前仍只写数据，没有声称的 `run_and_commit(codes=['K1'])`【E1+E2+E3】 | **历史 spec 明确假绿。** 后续代码修复了大部分交付缺口，但至少 K1 导入后自动推送仍与 task 18 声称不一致 |
| `disclosure-payload-authority-source` | 25/26，Playwright optional 未完成 | tasks 对 2.5 明确 `[ ]*`，状态诚实；权威源仍是前端 69 个 payload builder。该架构意味着这批披露计算不自动成为 formula-settings 全局层的可治理公式【E2+E3】 | **无假绿，但揭示产品边界。** “公式贯穿整个平台”尚不能覆盖前端权威载荷计算 |

### 5.1 依赖未提交改动清单

- `formula-fetch-followup-defect-closure` 4.2/4.3/4.5 明确依赖 `procedure-trim-generation-delegation-chain` 的未入库后端门禁；不得把前端按钮隐藏当成安全完成。【E3，当前 HEAD 未见对应完成证据】
- 当前 `.kiro/specs/INDEX.md` 有并发未提交修改，本报告不使用其状态数字作实现证据。【E1】
- 当前 `audit-platform/frontend/src/components.d.ts` 有未提交修改，本报告不使用自动组件声明证明任何生产挂载。【E1】
- 其余本报告引用的公式产品源码未出现在 status 变更清单中；上述结论不是依赖当前未提交产品代码得出。【E1】

## 六、建议的收口顺序

1. **先修统一 lineage 真调用链与项目隔离。** 建立不 patch 生产 wrapper 的契约测试；显式映射 `object_type → source`；附件查询必须通过附件或目标对象 join 校验 project；子源异常返回 `partial/errors`，不能伪装为空。
2. **建立“最终值 provenance envelope”。** 每个可计算结果统一带 `formula/definition_version/evaluated_at/run_id/input[{addr_id,semantic_label,value,project,year,version}]/write_source/manual_override`；前端值组件直接消费，避免每域另拼。
3. **把现有 tooltip 从示例组件变成平台挂载契约。** 真实扫描报表、附注、TB、底稿宿主；测试必须验证生产宿主传入 timestamp/addr/version，而不是三组 synthetic props。
4. **修审计链并发与验证边界。** `append_audit_log` 复用稳定 advisory lock；查询失败 fail-closed；verify 全链首条必须 genesis，时间片必须校验 boundary；关键发布可做外部定期签名/封存。禁止客户端直接写任意 formula audit event，改为业务事务内自动写。
5. **收口 custom function。** 若不需要则删除该伪全局 API；若需要，必须持久化、版本化、参数替换、函数依赖 DAG、循环检测、深度/节点/时间预算和多 worker 一致性。
6. **给传播加 durable outbox。** 定义提交与 outbox 同事务；worker 重试并在 UI 显示 propagation pending/failed；不能依赖内存降级列表。
7. **删除/回滚统一走影响预览 + CAS。** 删除前展示下游、受影响项目和最后计算值；delete 必须 expected_version。回滚目标公式从日志服务端读取并校验 hash，不接受客户端任意 target_formula。
8. **spec 完成门禁改为机器判定。** `[x]*` 但正文“未做/待实施/拦截验证”的任务禁止归档为 100%；生产调用签名、真实挂载、目标 commit 已入 HEAD 应成为完成检查项。
