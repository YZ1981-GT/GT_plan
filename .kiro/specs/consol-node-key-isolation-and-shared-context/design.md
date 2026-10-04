# 设计文档：合并附注节点隔离与共享上下文

> 需求：#[[file:.kiro/specs/consol-node-key-isolation-and-shared-context/requirements.md]]
> 上游：#[[file:.kiro/specs/consol-tree-three-code-autobuild/requirements.md]]、#[[file:.kiro/specs/consol-elimination-single-source-push/requirements.md]]
> 数据层：消费已存在的 V177 `consol_note_data.node_key` 与部分唯一索引；本 spec 不重复建迁移。

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
| F10 | 合并页缓存 key 已含 nodeKey，但报表请求没发送它且缺旧响应保护；附注 `currentEntity` 类型及多条请求未带 nodeKey | `ConsolidationIndex.vue`、`ConsolNoteTab.vue` |

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
