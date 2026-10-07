# 设计文档：合并节点隔离、共享上下文与工作底稿联动

> 需求：#[[file:.kiro/specs/consol-node-key-isolation-and-shared-context/requirements.md]]
> 上游：#[[file:.kiro/specs/consol-tree-three-code-autobuild/requirements.md]]、#[[file:.kiro/specs/consol-elimination-single-source-push/requirements.md]]
> 工作底稿边界：当前 `consol_worksheet_data` 的持久化唯一语义仍是 `(project_id, year, sheet_key)`；本 spec 的第一批实现只接通父页有效年度和可观察加载状态，不把 `node_key` 追加到前端请求或数据库唯一键。未来节点级工作底稿必须另提 V/R 配对迁移和旧数据迁移策略。
> 公式/股比边界：公式运行时通过新增 `consol_worksheet` 域读写真实 JSON 持久化；动态股比通过稳定事件集合驱动显示和计算，并在确认/审批后才进入正式抵销链路。

## 一、现状实证（2026-10-03 现读工作树与上游 spec）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 附注表已具备节点列与节点/legacy 部分唯一约束 | `V177__consol_node_key_isolation.sql`、`consol_note_data_models.py` |
| F2 | 附注记录装载用 `node_key.endswith(':consol')` 回退 NULL 行，未先验证当前企业树；GET/PUT 未统一验证节点与有效年度 | `routers/consol_note_sections.py::_load_note_record` 及端点实现 |
| F3 | 公式内核已有共享上下文入口和节点求值能力；填入公式已有节点专属写入及根节点 legacy 复制逻辑 | `services/consol_note_formula_service.py` 的 `load_view_context`、`find_node`、`node_measures`、`fill_by_formula` |
| F4 | 旧 `/refresh`、`/audit-all`、`/audit`、`/apply-formulas`、`/aggregate` 路径仍有直接 SQL，引用不存在的 TB 列且吞异常 | `routers/consol_note_sections.py` |
| F5 | 合并报表视图已集中在 `consol_report_view_service.py`，金额内核位于 `consol_calc_basis.py` 与 `consol_report_values.py` | `load_view_context`、`trial_view`、`breakdown_view`、`node_measures` |
| F6 | 普通报表 GET 只按项目/年度/类型读 `FinancialReport` 物化行；股东权益表另做项目级 enrichment | `routers/consol_report.py::get_consol_report` |
| F7 | `FinancialReport` 唯一键没有 node_key，是项目级物化模型，不适合作为多节点写入表 | `consol_report_service.py`、`FinancialReport` ORM |
| F8 | custom query dispatcher 丢弃 filters；附注 resolver 未按 node_key 过滤且排序不稳定 | `custom_query/business_fetchers.py::_dispatch`、`module_cell_resolver.py::_query_note_cells` |
| F9 | cell writeback 请求没有完整附注归属；writer 只按 id 锁行，不重验项目/年度/章节/节点，且只处理对象行 | `routers/custom_query.py::CellWritebackRequest`、`snapshot_writer_modules.py::write_note_cell` |
| F11 | 合并工作底稿批量读写接口只按项目/年度/表键定位；前端组件从 route/query 或当前日期猜年度，并把加载异常转成空对象 | `routers/consol_worksheet_data.py`、`consolWorksheetDataApi.ts`、`ConsolWorksheetTabs.vue` |
| F12 | 公式 Runtime 的 domain、reader、coordinator scope map 和 mutation adapter 没有 `consol_worksheet`，工作底稿公式结果尚不能真实持久化 | `formula_runtime/contracts.py`、`value_loader.py`、`coordinator.py`、`adapters/` |
| F13 | 动态股比 UI 由固定 `changeTimes: 1 | 2 | 3` 生成列；G7 联动只写工作底稿和建议草稿，不保存稳定股比事件或正式抵销审批关系 | `ShareChangeSheet.vue`、`g7_consol_linkage_service.py`、`consol_worksheet_data.py` |

## 二、设计边界与共享身份

1. `node_key` 是节点身份；`company_code` 仅作企业属性，不能用于授权、数据隔离或节点回退。
2. 本 spec 只改读取、写入、计算编排、请求上下文和前端状态，不新增或修改 V177。若实施时证明需改变 schema，必须另提 V/R 配对迁移，不在本 spec 偷加 DDL。
3. 附注记录的归属元组为 `(project_id, year, section_id, node_key)`；legacy 行的 `node_key IS NULL` 是独立兼容范围，不等同任意合并根节点。
4. 普通合并报表是读时计算；不把 node_key 加到项目级 `FinancialReport`，也不将节点结果写回该表。
5. 金额只由合并共享上下文与现有 `node_measures` / `consol_report_values` 计算；禁止附注或报表另写 company-code 汇总算法。
6. 新版前端始终传 nodeKey；省略节点键只为旧调用保留 NULL legacy 行语义，不隐式选择根节点。

## 三、附注节点上下文解析

在附注路由/service 边界增加一个共用的异步解析流程，所有端点复用，不各自拼 SQL：

1. 解析显式 query `node_key`；只有 query 未提供时才读取兼容 body `node_key`。显式 query 优先，空字符串按无效输入拒绝，不降级成省略。
2. 检查项目存在、可访问，并用统一项目审计年度解析器确认请求年度有效且属于该项目；无效年度返回 400，不跨年读写。
3. 以项目与年度构建当前企业树；显式 node_key 必须经 `find_node_by_key` 精确命中当前树，否则返回 400。禁止冒号前缀、company_code 或 `:consol` 后缀兜底。
4. 命中节点时产生 `NodeScope(project_id, year, section_id, node_key, is_root_consol)`。根身份必须同时满足树根节点本身、role 为 `consol`；不能仅凭字符串推断。
5. 未传 node_key 时产生 `LegacyScope(project_id, year, section_id)`，读写只匹配 `node_key IS NULL`。不会回退到任何节点专属行。
6. 节点读取先精确查询节点行；仅 `is_root_consol` 且节点行不存在时才查询同项目、年度、章节的 NULL 行。非根节点从不读取 NULL 或其他节点行。
7. 写操作永远定位当前作用域的专属行。根节点读到 legacy 行后发生 PUT、公式填入或其他修改时，先以其数据/模板基线创建根 node_key 行，再应用更改；不得对 legacy 行执行 UPDATE/DELETE。旧请求无 node_key 时则维持 NULL 兼容写入。
8. 并发创建服从 V177 唯一索引：冲突时在 SAVEPOINT/事务内重新读取归属行并执行既定更新语义，不能吞掉唯一冲突后报告成功。

## 四、附注公式与旧入口统一

- 节点金额上下文经现有 `consol_report_view_service.load_view_context` 加载，再由 `find_node` 与 `node_measures` 得到当前节点数据；报表/附注公式统一经 `consol_report_values` 的既有求值口径。一次请求尽量只装载一次上下文。
- `/refresh`、`/audit-all`、`/audit`、`/apply-formulas`、`/aggregate` 与 `fill-by-formula` 共用节点解析器、记录装载器和金额上下文。删除这些路径中的直接 TB SQL；TB 字段若仍有直接读取，只能使用 ORM/schema 实际存在的列：`standard_account_code`、`account_name`、`unadjusted_amount`、`audited_amount`、`opening_balance`、`aje_adjustment`、`rje_adjustment`、`wp_adjustment`。
- 公式/解析失败不得回传模板值或伪造 0。单项审计/批量审计响应保留逐项错误原因；请求级上下文失败用明确 HTTP 错误，事务回滚。
- 公式填入仅更新该作用域对应行；手工保护格保持原值，返回准确的保留数/清单。对象行与二维数组按既有存储形态原位更新，不把数组强行改造成对象。
- 兼容 body 的 node_key 仅作为输入解析优先级兼容，不改变现有 HTTP 响应 envelope、端点路径或权限等级。

## 五、custom query 附注读写

### 5.1 读取

`business_fetchers._dispatch` 将 filters 完整传递给 module-cell resolver；resolver 将 `filters.node_key` 传入附注取数器。`note:{section}|{range}` 查询约束项目、有效年度、section 和节点：有 node_key 时精确等值匹配；没有 node_key 时只查 NULL legacy 行。节点请求不套用附注 GET 的根节点 legacy 回退，以保持 custom query 的精确身份契约。结果按稳定主键排序，并保留 range 与原 writer 所需行形状。

### 5.2 写回

- note cell writeback schema 显式带 `project_id`、`year`、`section_id`、`node_key`、附注记录 ID、单元格定位信息及既有乐观锁字段；不得把记录 ID 视作权限边界。
- 路由先执行项目编辑权限校验。writer 在事务内 `SELECT ... FOR UPDATE`，再逐项比较请求与数据库记录的 project/year/section/node_key；任何缺失、越权、归属不一致或记录已删除均拒绝并回滚。
- 写节点记录时只允许精确 node_key 行；找不到该节点记录即拒绝，不将写入重定向到 NULL legacy 行。
- 更新前校验 row/column 边界；支持 dict 对象行与二维数组行，保留其他值、键、列顺序和行形状。越界或不支持的数据形状返回明确客户端错误。
- 保留现有乐观锁冲突响应、项目编辑权限和审计字段；不降低调用方校验。

## 六、普通合并报表读时计算

1. `get_consol_report` 增可选 query `node_key`。缺省时选当前树的根合并节点以保持旧页面默认行为；显式值必须由当前项目/年度企业树精确验证，不存在返回 400。这里的默认根语义仅适用于报表 endpoint，不改变附注旧调用的 NULL 语义。
2. 通过 `consol_report_view_service` 统一加载树、计算 basis 和 report config，取得该 node_key 的 `node_measures`，再调用 `consol_report_values` 求所选 `report_type` 行值。不得按 company_code 求值，也不读取根节点物化金额充当其他节点金额。
3. 继续返回原 `ConsolReportRow[]` 及字段：行编码/名称、缩进、合计标记、本期/上期、公式、来源科目、留空原因、过期标记。行次与元数据沿既有 report config/已生成报表元数据；金额由共享求值器提供。无法支持的公式返回 amount=null 与明确 blank_reason，不以 0 代替。
4. 本期金额按请求 node_key 计算。上期金额只允许用上一有效审计年度同一 node_key 的树与共享计算上下文计算；若上一年度节点不存在或公式不支持则置 null 并给原因，禁止复用根项目级 `FinancialReport.prior_period_amount` 到非根节点。
5. 股东权益表不再用项目级 `ReportEngine.enrich_equity_statement_rows` 覆盖节点金额；其节点行仍由同一合并 report-values 路径求值，原有字段契约保留。
6. 读取为只读，不改变 `/generate` 的写库语义、`FinancialReport` 唯一键或物化数据。有效 node_key 下即使项目级物化报表缺行，仍依据 report config 生成兼容行数组；无对应报表配置才按既有明确错误处理。

## 七、前端共享上下文与过期响应保护

- `ConsolidationIndex.vue` 将 `{code, name, nodeKey}` 作为当前实体单一上下文传入报表加载器和 `ConsolNoteTab`；附注实体类型的 nodeKey 必需。
- 报表请求显式发送当前 nodeKey。普通报表与附注缓存 key 均包含 projectId、有效 year、nodeKey、report/template 维度；刷新只清除当前节点对应项。
- 每次异步加载捕获请求时的 project/year/nodeKey 和单调递增序号；响应提交前四者仍与当前上下文一致且序号仍最新，否则丢弃。取消旧请求可作为资源优化，但不能替代提交前校验。
- 附注所有节点级 GET/PUT、公式填入、refresh、audit、audit-all、apply-formulas、aggregate 和 drill-through 请求均传 nodeKey。差额穿透独立节点选择初始为当前节点；用户另选只变更穿透参数，不反向改写页面当前 nodeKey。
- API 函数兼容旧调用签名：新增参数可选且仅新版合并页面传入；所有用户可见错误使用中文。

## 八、正确性属性

| # | 属性 | 验证方式 |
|---|---|---|
| P1 | 两个 node_key 对同一 project/year/section 的读写互不覆盖 | 真 ORM 行 SQLite 集成测试 |
| P2 | 非法 node_key、跨项目/年度/章节或非根节点均不能命中 NULL/其他节点行 | service + HTTP 真请求拒绝测试 |
| P3 | 仅树根 consol 节点可读时回退 NULL；首次修改创建专属行且 NULL 行字节/字段不变 | SQLite legacy 回退集成测试 |
| P4 | 省略节点键的旧附注调用只访问 NULL 行 | 路由契约测试 |
| P5 | 节点附注金额与同节点 report/trial/breakdown 共享求值一致，精确到现有分币精度 | 真 ORM/SQLite 合成集团对拍 |
| P6 | custom query 节点读取仅返回对应项目/年度/章节/node_key；无键请求只返回 NULL 行 | resolver 查询集成测试 |
| P7 | writer 归属不符、越界、缺行均无任何 consol_note_data 更新；dict/二维数组均只改目标 cell | 锁行 writer 集成测试，独立事务复读 |
| P8 | 普通报表返回原行数组契约；同 node_key 的本期金额与试算/差额读端逐行一致 | FastAPI + SQLite 真 ORM 测试 |
| P9 | 请求响应乱序或快速切节点时，旧上下文结果不能覆盖新节点 | 前端组件/API 测试 |

## 九、架构决策

- **ADR-CNSC-001：节点身份只认当前树精确 node_key。** 拒绝按 company_code、键后缀或前缀推断，避免同企业多角色及伪造键命中。
- **ADR-CNSC-002：legacy NULL 是显式兼容作用域。** 根节点 GET 可经树验证回退，写入复制为节点行；省略 node_key 的旧调用只操作 NULL。拒绝把所有旧请求自动映射根节点。
- **ADR-CNSC-003：FinancialReport 继续项目级物化，节点报表读时计算。** 复用已存在金额内核，避免扩展唯一键和多节点写库生命周期。
- **ADR-CNSC-004：custom query 不继承附注根 fallback。** 有键精确取节点，无键精确取 NULL；读写遵从同一归属元组，拒绝“读能看到 legacy、写却可能误改 legacy”的模糊授权。
- **ADR-CNSC-005：异步结果按完整请求上下文提交。** 缓存分区与过期响应保护是两个独立条件，二者都必须满足。

## 十、范围外与风险

- 不新增 migration；不改企业树角色生成、抵销审批、报表生成/推送策略；不改变项目级 `FinancialReport` 数据模型。
- V177 实际索引/约束与 ORM 名称须在实施前现读确认；若索引对节点/NULL 作用域不满足并发 upsert，先停止并另提迁移设计。
- 旧公式端点的调用方和空 body 行为需实施前全仓 grep；兼容请求不等于保留错误 SQL 或吞异常。
- SQLite 可验证事务、ORM 与真实行形状；生产 PG 的并发/锁行为需额外测试环境。浏览器或后端不可运行时，相关验收任务保持未完成并记录具体阻塞。

## 十一、父页有效年度与合并工作底稿契约

### 11.1 页面上下文

`ConsolidationIndex.vue` 是合并页年度的唯一拥有者。工作底稿子组件接收显式 `projectId` 与 `year` props；`year` 使用页面已有的有效年度（优先 `treeYear`，并遵守 `projectInfo.year` 的更新契约），子组件不得读取 `route.query.year`、当前日期或自行减一年。报表、附注、试算表和工作底稿的年度请求必须由同一父页状态产生。

左树节点和右侧页签是两条独立状态轴：

- `currentConsolEntity = { code, name, nodeKey }` 只由左树点击更新；报表和附注消费它。
- 右侧切换报表、附注、工作底稿只改变 `activeTab`，不重置或改写 `currentConsolEntity`。
- 工作底稿当前保持 `(project_id, year, sheet_key)` 项目/年度级语义。即使左树选中单户或母公司，工作底稿也不得拼出伪 `node_key`，不得把某节点数据误当成另一节点数据。

### 11.2 加载状态

工作底稿 API 层必须保留 HTTP 失败和成功空结果的区别。推荐返回结构：

```ts
interface WorksheetLoadResult {
  status: 'loaded' | 'empty' | 'error'
  data: Record<string, Record<string, unknown>>
  errorMessage?: string
}
```

后端成功返回零行是 `loaded + empty`；非 2xx、网络异常、响应不是数组或 item 不是可解析对象是 `error`。组件在 `error` 状态显示中文错误且不覆盖已加载的有效年度数据；在 `empty` 状态显示中文空提示并保留可编辑默认行。保存失败同样必须向用户报告，不能返回 `false` 后静默丢失。

G7 预览、导入、上年提取和公式重载使用同一父页年度。页面年度变化时先清理或标记旧年度数据，再加载新年度，避免旧年度内容在等待期间继续显示为当前数据。

### 11.3 总分提示

`isBranchMode` 只能来自已验证的企业树合并模式（`treeMode === 'branch'`）和明确的项目级语义。它不应由当前节点的 `company_code`、节点后缀或默认根节点推断。单户/母公司节点点击不会改变项目是否为纯总分汇总项目；若产品要求提示只在合并模式 tab 展示，组件需使用 mode/context 条件而不是左树选中状态猜测。

## 十二、公式 Runtime 的 `consol_worksheet` 领域

### 12.1 规范身份

扩展 `CanonicalFormulaTarget.domain` 为 `consol_worksheet`，其 locator 至少包含：

```text
project_id, year, sheet_key, row_identity, cell_identity
```

`node_key` 只有在未来节点级工作底稿 schema 落地后才可作为可选扩展，当前不得用它拼接伪地址来模拟隔离。地址的稳定部分是表键和行/列身份，不是数组下标；若表格只有 JSON 路径，必须同时记录可审计的路径和数据版本。

### 12.2 读取

新增 `ConsolWorksheetDomainReader`，按 `(project_id, year)` 批量装载相关 `consol_worksheet_data`，在内存中按 `sheet_key`、row identity 和 cell identity 解析对象行/二维数组。reader 必须返回可区分的 miss/error：行或单元格不存在是 miss；数据库表、JSON 解析或版本读取失败是 error，并进入 `LoadIssue`，不能把两者都当成空值。

### 12.3 变更与持久化

新增 `ConsolWorksheetMutationAdapter`，实现 `prepare_many/apply_many/restore_many/read_versions`。apply 必须在当前事务内锁定工作底稿行，检查 `updated_at` 或等价版本/CAS，再按原 JSON 形状更新目标 cell；冲突时不覆盖用户数据并返回 conflict。写入应记录公式 ID、run ID、目标地址、前后值、版本和操作者审计信息。Coordinator 只生成计划，调用方统一提交；fresh read 必须能看到成功结果。

第一批实现可复用现有 JSON 表存储，但不得把 adapter 降级为“只改内存 dict”。若当前表缺少可可靠比较的版本字段，应先使用已存在的 `updated_at` 并明确精度/并发限制；不足时另提迁移，不伪造 CAS 成功。

### 12.4 长投与关联交易取数范围

公式绑定的 source scope 结构化表示：

```text
{ project_id, year, node_key?, include_descendants: true,
  domains: ['report', 'note', 'workpaper', 'consol_worksheet'] }
```

节点解析必须调用企业树和 `consol_calc_basis` 的现有服务，按精确 node_key 取得当前节点及子树，不使用 company code 前缀匹配。长投、关联往来、关联交易只是不同 binding/template，不复制金额算法。用户编辑绑定后先生成可审阅计划，再执行和记录结果。

## 十三、动态股比事件与抵销链路

### 13.1 事件模型

建议新增独立事件实体（ORM、V/R 配对迁移和 API），至少包含：`id`、`project_id`、`year`、`company_code`、`node_key`、`effective_date`、`sequence`、`before_ratio`、`after_ratio`、`ratio_delta`、`source_type`、`source_row_id`、`source_sheet_key`、`review_status`、`calculation_version`、`created_by`、`updated_at`。`node_key` 用于明确承载合并项目/节点；在节点级 schema 尚未落地前，不把当前工作底稿的项目级 JSON 当作事件表替代品。

同一公司事件的排序键为 `(effective_date, sequence, id)`。日期缺失、同一公司同一期间日期重复且没有明确 sequence、比例超出 0~100 或前后比例无法闭合，均返回可见校验错误。事件 ID 永不因排序或插行变化。

### 13.2 期间追溯

服务把期间切成：期初至事件 1、事件 1 至事件 2、……、最后事件至期末。每段保存适用净资产快照/来源、期初比例、期末比例、比例变动和计算结果。事件 2、3 以及第 N 次事件均从集合动态生成列/行，不创建只支持 `share_change_2`、`share_change_3` 的业务分支。

结果至少提供：

- 每个事件前后比例与比例差；
- 事件对应期间净资产和权益法模拟值；
- 长投、资本公积、投资收益、NCI 影响；
- 来源行、计算版本、计算时间；
- 对应正式抵销建议的状态和审批 ID。

### 13.3 G7 规范化与正式审批

G7-10 及其他 G7 股比来源行映射为相同事件 DTO，`source_type/source_row_id/source_sheet_key` 必填。重复导入以来源身份幂等 upsert，不能按显示名称追加重复事件。G7 linkage 仍可写入工作底稿和建议草稿，但只有用户确认后创建的正式 suggestion 才能进入现有 elimination review/recalc/push；建议带项目、年度、node_key、事件 ID 集合、计算版本和 review status。

正式抵销链路保持现有审批门：draft 只展示和可编辑，approved 才能被 `consol_calc_basis` 消费并触发下游推送。三次变动验收必须能从事件 1/2/3 追到净资产区间、比例、调整建议和最终审批状态。

## 十四、扩展正确性属性

| # | 属性 | 验证方式 |
|---|---|---|
| P10 | 工作底稿使用父页有效年度；成功空结果与 HTTP/解析错误在 API 和 UI 上可区分 | API/组件测试 + Playwright |
| P11 | 公式工作底稿 mutation fresh read 可见，CAS 冲突不覆盖用户值 | 真 ORM/SQLite 或 PG 集成测试 |
| P12 | 1~N 股比事件排序稳定；4 次事件不被固定三列截断；重复 G7 导入幂等 | service/HTTP/UI 测试 |
| P13 | 三次事件的每段净资产、比例、调整和正式抵销审批状态可追溯 | 合成集团集成测试 + 页面验收 |

## 十五、架构决策补充

- **ADR-CNSC-006：父页持有有效年度。** 子组件不从路由或日期猜年度；工作底稿当前项目/年度级，节点切换不伪造工作底稿节点隔离。
- **ADR-CNSC-007：加载失败不等同空数据。** API 层保留非 2xx/解析失败，UI 只能在真正成功零行时展示空状态。
- **ADR-CNSC-008：工作底稿公式必须真实持久化。** `consol_worksheet` reader/adapter/版本检查和 fresh read 是完成条件，前端缓存不是持久化。
- **ADR-CNSC-009：动态股比以事件集合为真源。** 1~N 次事件由稳定 ID 和日期/序号排序驱动，固定 `share_change_1/2/3` 只能作为兼容投影，不能作为模型上限。
- **ADR-CNSC-010：G7 建议与正式抵销分离。** G7 来源和建议草稿不能绕过用户确认、审批状态和现有抵销重算链。
