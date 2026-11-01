# 设计文档：S5　取数结果的来源信封（formula-provenance-envelope）

> 需求编号：requirements §1 的 R1（报表 current、附注自动公式、公式推送目标）、R2（`note_wp_mapping` 来源）、R3（最终值展示面）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`）。设计中的计数和字段路径只作启动快照，实施 Task 0 必须重新现算。
> **范围勘误**：本 spec 不实施底稿域信封。底稿公式有效定义统一属于 S1；S1 完成后再复用本设计的信封契约接入底稿域。

## 0. 总体裁定与实施边界

来源信封必须回答两件不同的事：

1. **公式求值结果**：这次按哪版定义、哪些输入算出了什么；
2. **最终值来源**：当前展示的值是否真的采用了这次结果，还是人工值、锁定值、底稿投影或旧值。

因此三个域共用一个信封契约，但必须保存 `value_state` 与 `calculation_applied`，不能把“公式算出来”直接等同于“最终格子采用了公式值”。

本 spec 分为四个可独立验收的交付边界：

- **S5-R：报表域**：`financial_report` 本期值，统一接入 full / affected / stale 三条写入路径；
- **S5-N：附注域**：普通附注自动公式单元格，保留人工、锁定、底稿投影的来源语义；
- **S5-P：公式推送域**：`formula_push_state` 的公式结果和目标最终状态；`consol_note` 既有 `last_formula_run_id` 本 spec 不改；
- **S5-U：统一展示与溯源**：报表本期金额和附注自动公式单元格的来源展示，以及 R2 的 UnifiedLineage 接线。

底稿域不阻塞 S5-R/N/P/U，但必须在 S1 的有效定义统一后另立接入任务，不能在本 spec 用 `wp_formula` 的旧路径猜定义层级。

## 1. 现状复核

| # | 交接结论 | 现算基线 | 设计判断 |
|---|---|---|---|
| 1 | 报表行没有完整信封 | `financial_report` 有 `formula_used`、`source_accounts`、`generated_at`、`calc_version`、`is_stale`、`calc_error`，无 run、定义层级 / hash、输入摘要；`write_row()` 被 full / affected / stale 三路直接调用 | 需要统一运行上下文和定义身份解析器 |
| 2 | 报表有效定义有版本但可能丢来源层 | `ReportConfig` 有 `formula_version`；`load_effective_report_configs()` 合并项目公式时返回复制对象，当前没有稳定的 `definition_layer` / `definition_hash` 契约 | 不能直接从复制后的 ORM 对象推导信封，需返回有效定义元数据 |
| 3 | 推送已有运行记录 | `formula_push_run` 有 `id`、触发来源、触发人和状态；`formula_push_state` 有 `last_run_id`、三态值和 `updated_by`，没有统一 provenance | 沿用 `last_run_id`，新增完整信封并区分公式尝试与最终目标值 |
| 4 | 附注已有执行时间和地址身份 | `execute_note_formulas()` 现写 `_formulas` 中的 `evaluated_at`、`addr_id`；preset / `_user_formulas` / 有效设置版本层级没有统一落在执行结果上 | 用稳定 `addr_id` 键的 `_formula_provenance` 保存执行信封，不污染公式定义记录 |
| 5 | `note_wp_mapping` 表不存在 | `report_trace_service.trace_section()` 仍直接查该表并吞异常；权威注册表由 `note_readiness_service` 提供，项目自定义映射在 `wizard_state` | 改成统一访问器，端点级验证 partial / errors / 多底稿语义 |
| 6 | 来源展示存在两个体系 | `GtFormulaSourceTooltip` 目前只懒解析 ACNR 地址；`ReportView` 未接入；`DisclosureEditor` 已有 `TraceSourcePopover`、`CellTraceDialog`、`get_cell_sources` 和校验 / 批注 tooltip | 报表扩展独立 provenance 展示；附注复用既有来源链，禁止嵌套 tooltip 破坏编辑和校验 |
| 7 | 输入采集点分散 | 报表 TB / SUM_TB / ROW / ADJ / WP / NOTE 由不同预载或 resolver 取数；附注还有表内 cell 和跨表数据；推送有四表、派生和调整来源 | 用 ContextVar 收集器统一规范化，但每个域列出明确接入矩阵 |

## 2. 统一来源信封契约

### ADR-FPE-01：`ProvenanceEnvelopeV1`

三个域的持久化 JSON 使用同一字段集合；字段缺失不能靠读取方猜默认值。推荐形状：

```json
{
  "schema_version": 1,
  "domain": "report|note|push",
  "value_slot": "current",
  "value_state": "auto|manual|locked|kept|pending_confirm|failed",
  "calculation_applied": true,
  "definition_version": 1,
  "definition_hash": "sha256…",
  "definition_layer": "global|project|template|preset|system",
  "run_id": "uuid",
  "computed_at": "ISO-8601 UTC",
  "computed_by": "uuid|null",
  "calc_version": "engine:version",
  "inputs": [{"kind": "TB", "key": "1001|期末余额", "value": "12.34"}],
  "input_count": 1,
  "inputs_truncated": false,
  "input_digest": "sha256…"
}
```

契约规则：

- `definition_hash` 是完整 SHA-256，不使用各模块自行截断的 hash；输入与定义分别有独立 digest；
- `definition_version` 必须来自真实定义记录或稳定的系统预设目录版本，禁止用当前时间、run 次数或随机数冒充；
- `definition_layer` 由域适配器给出，读取方不得凭字段名推断；
- `run_id` 是运行记录权威 ID。报表的关系列和 JSON 镜像必须一致；
- `computed_by=null` 表示系统触发，不表示未知用户；用户 ID 的显示名称由读取 API 按项目权限解析；
- `calc_version` 采用带引擎前缀的稳定字符串，例如 `report:229`、`note:1`、`push:1`，报表既有整数 `financial_report.calc_version` 仍作为 stale 兼容列；
- `value_state` 描述最终值，不描述单纯公式尝试；`calculation_applied=false` 时不得把该信封当作当前值权威来源；
- `value_slot=current` 是本 spec 报表展示的唯一值槽。`prior` / `opening` / `adjustment` 必须有独立的计算结果和信封，不能复用 current 信封；
- `stale` 不重复落在信封中，由读取 API 按当前定义 hash、计算版本和 stale 标记现算返回。

### ADR-FPE-02：定义身份解析器

各域在执行前必须生成一个不可丢失来源层的定义身份：

| 域 | 有效定义来源 | `definition_version` | `definition_hash` | `definition_layer` |
|---|---|---|---|---|
| report | `EffectiveReportDefinition`（准则行 ⊕ 项目行） | 实际采用行的 `formula_version` | `exec_hash("report", definition)` | global / project |
| note | `EffectiveSlot` 或稳定 preset 目录记录 | `FormulaSetting.version`；preset 使用目录版本 | `exec_hash("note", definition)` | global / template / project / preset |
| push | `PushRule` + 规则集版本 | `PushRule.version` | 规则执行字段 + 规则集 digest | system |
| workpaper | S1 完成后接入 | 另行裁定 | 复用同一 canonical hash | 另行裁定 |

`EffectiveReportDefinition` 至少包含公式、实际来源记录 ID、版本、hash、层级和可执行字段。禁止继续只返回丢失项目覆盖来源层的复制 ORM 对象。

所有域的定义 hash 都复用 `formula_settings.definitions.exec_hash()` 的 canonical JSON 规则；推送规则需先映射为同样的执行字段视图，并把规则集版本加入规则身份，避免规则文件整体变化而单条 hash 不变。

## 3. 输入摘要与 canonical digest

### ADR-FPE-03：`formula_inputs` 收集器

新模块 `backend/app/services/formula_inputs.py` 采用 `formula_warnings` 的 `ContextVar` 嵌套收集模式：

- `collect()` 返回当前计算的输入桶，退出时无论成功或异常都 reset；
- `emit(kind, key, value, source_ref=None)` 写入输入原子；嵌套执行同时进入外层桶；
- 同一计算上下文内允许重复 key，digest 按 multiset 处理，不能用 dict 静默覆盖；
- 输入原子值统一转为 JSON 可序列化的 canonical 值，`Decimal` 使用固定小数文本，禁止依赖 Python float repr；
- digest 输入按 `(kind, key, canonical_value, source_ref)` 排序后计算；同一组输入换顺序不改变 digest，任一原子变化都会改变 digest；
- 展示列表最多 200 条，按稳定排序截取；`input_count` 统计全量原子，`inputs_truncated` 表示展示列表是否被截断；`input_digest` 始终按全量原子计算；
- 收集器保存输入值，不保存超出当前项目权限的跨项目原始数据；跨子项目来源使用受权限过滤的稳定引用和脱敏值。

接入矩阵：

| 域 | 输入类型 | 接入点 | 缺数 / 失败语义 |
|---|---|---|---|
| report | TB / SUM_TB | 叶子选择与 resolver 汇总后 emit 叶子依赖和实际列 | 公式失败不生成新信封 |
| report | ROW / SUM_ROW | 从 `row_cache` 取实际参与求值的行值 | 引用未就绪时保留旧信封 |
| report | ADJ / WP / NOTE / AUX / PREV | 各自预载或 resolver 的实际返回处 | 不把报表路径中刻意置 0 的不支持函数伪装成真实输入 |
| note | 表内 cell / SUM、TB / REPORT / NOTE / WP / PRIOR / AGING | `execute_note_formulas` 的 evaluate / cross-data 解析点 | manual / locked / kept 不更新最终值信封 |
| push | TB、四表叶子、派生函数、批准调整、底稿 / 附注来源 | binding source 求值和 note writer 写入前 | 目标未实际写入时 `calculation_applied=false` |

### ADR-FPE-04：报表运行上下文

新增只读数据对象 `ReportGenerationContext`，贯穿 full / affected / stale 三条路径：

```text
run_id / project_id / year / trigger / triggered_by
started_at / calc_version / definition_snapshot
```

`report_row_compute.write_row()` 接收上下文和本行的 `EffectiveReportDefinition`、`RowOutcome.inputs`：

- 成功：写 current 值、当前 run_id、完整 provenance，清 stale 和 calc_error；
- 失败：保留旧金额、旧 `run_id` 和旧 provenance，只写 stale / calc_error；新行金额保持 NULL；
- 当前值未变化但确实重新计算：仍更新 computed_at、run_id 和 input digest，作为一次新的计算运行；
- 三条路径产生同一份 `GenerateSummary` 口径，运行记录状态为 `succeeded` / `partial` / `failed`；
- actor 从 router / 事件 / 系统入口显式传入，不能在 service 内读取全局当前用户。

## 4. 报表域落地

### ADR-FPE-05：迁移、运行记录和原子写入

实施时按当前磁盘迁移最大数字动态取号，生成 V/R 配对迁移，不写死本设计中的版本号。

`financial_report` 增加：

- `run_id uuid NULL`，外键指向 `report_generation_run(id)`，并按项目 / 年度 / run 建索引；
- `provenance jsonb NULL`，存 `ProvenanceEnvelopeV1`；
- 既有 `calc_version` 保留，用于历史 stale 兼容。

新表 `report_generation_run` 至少包含：

```text
id, project_id, year, trigger, triggered_by,
started_at, finished_at, status,
changed_rows, recomputed_rows, failed_rows,
error_summary, calc_version
```

`status` 固定为 `running | succeeded | partial | failed`。运行记录与本次行写入在同一事务内；调用方回滚时不能留下“成功运行”记录。异常导致事务回滚时，另按既有运行记录约定写失败留痕，不能假造成功行信封。

同一项目 / 年度的 full、affected、stale 运行必须有明确的并发策略。默认使用项目年度级运行锁或等价的串行门，避免两个 run 交错写同一行后无法判断最后有效信封。

### ADR-FPE-06：定义 hash stale 判据

报表 freshness 读取当前有效定义的 `definition_hash`：

- 新信封存在时，与 `provenance.definition_hash` 比较；
- 存量行没有 provenance 时，退回现有公式文本 / `calc_version` 判据，并明确标为 legacy；
- 定义 hash 变化只标记受影响闭包，不清除旧信封；
- 成功重算后才用新信封替换旧信封；
- 失败重算不因已有新定义而覆盖旧值来源。

### ADR-FPE-07：来源读取端点

沿用当前 reports router 的路径风格，新增：

```text
GET /api/reports/{project_id}/{year}/{report_type}/rows/{row_code}/provenance
```

端点使用 `require_project_access("readonly")`，返回：

```text
{
  row_code,
  value_slot: "current",
  value,
  envelope,
  run: { id, trigger, triggered_by, started_at, finished_at, status },
  stale,
  legacy,
  computed_by_label
}
```

`row_code`、`report_type`、`year` 必须共同定位单行；不返回其他项目或其他年度输入。新增路由必须注册到 `router_registry`，并有端点级 anon / non-member / readonly 用例，不只测 service。

## 5. 附注域与公式推送域

### ADR-FPE-08：附注执行信封

`execute_note_formulas()` 增加显式 `triggered_by: UUID | None`，由用户入口、事件入口和系统入口分别传递。

- 每次章节执行生成一个 run_id；批量刷新是否跨章节共用 run 必须在编排层显式决定，默认每个章节执行一个 run；
- 公式定义仍由 `_formulas` / `_user_formulas` 保存；执行 provenance 不再混入定义字段，统一存 `table_data["_formula_provenance"][addr_id]`；
- `addr_id` 必须沿用 `_note_cell_addr_id()` 的稳定身份，多表和投影表不能使用仅显示行列；
- preset、global、template、project 的 definition identity 由 `EffectiveSlot` 或稳定 preset 目录提供；不能从 materialized JSON 中缺失的版本字段猜测；
- 只有自动公式实际写入目标值时更新 `calculation_applied=true`；值未变化但重新求值仍更新 computed_at / input digest；
- manual、locked、`kept_workpaper`、公式失败保留原有最终值来源信封，并在执行结果中记录原因；
- `get_cell_sources` / 现有附注来源端点扩展返回 provenance、value_state、calculation_applied，避免再造一条重复的 cell 读取链路。

### ADR-FPE-09：公式推送信封

`formula_push_state.provenance` 存完整 `ProvenanceEnvelopeV1`，`last_run_id` 仍是运行记录外键和查询权威。

- `PushRule.version` 是定义版本；规则的执行字段和规则集版本共同生成 definition hash；
- `triggered_by` 映射为 `computed_by`，引擎触发没有用户时为 NULL；
- auto 且实际写入目标时 `value_state=auto`、`calculation_applied=true`；
- manual / locked / pending_confirm 目标即使算出了新公式值，也必须保留“当前最终值未采用”的状态；
- 公式结果和当前目标值不一致时，信封中必须能区分公式尝试来源与最终值状态；
- 推送保存点回滚、运行失败或目标缺失不能留下成功写入信封。

## 6. R2 溯源注册表替换

### ADR-FPE-10：唯一映射访问器

`report_trace_service.trace_section()` 通过 `note_readiness_service` 的统一访问器取得章节映射，不能自行读取 JSON 或旧常量。

解析顺序：

1. 读取项目 `wizard_state.note_wp_mapping` 自定义映射；
2. 没有自定义映射时，按项目模板类型从 `note_workpaper_sync_registry.json` 读取；
3. 保留一个章节对应多个 `wp_code` 和 `listed_sections` / `soe_sections`；
4. 通过 `NoteAccountMappingService` 读取真实存在的报表行次 / 章节 / 底稿字段，不推导不存在的 `account_codes`。

响应必须区分：

- 映射成功：附注子源正常，`partial=false`；
- 注册表中没有章节：正常的 `not_found`，不吞成数据库异常；
- 注册表不可读：`partial=true`，带稳定错误码；
- 数据库异常：保存点隔离后返回子源错误，不把异常伪装为空映射。

SQL 守卫覆盖 `FROM`、`JOIN`、`INSERT`、`UPDATE`、大小写和引号变体，并配违规样本自检。验收必须从 `GET /api/projects/{project_id}/lineage` 端点验证，而不是只调用 service。

## 7. 最终值展示接入

### ADR-FPE-11：报表和附注分开接线

报表：

- `ReportView` 只对 `current_period_amount` 的最终展示格挂 provenance 展示；
- `prior_period_amount`、compare 派生列、变动率、没有对应 `financial_report.current` 信封的矩阵列不挂本 spec 信封；
- 现有 ACNR 来源地址解析可作为展示内容的一部分，但不能代替 provenance 请求；
- 可扩展 `GtFormulaSourceTooltip`，或新建等价组件，但必须支持异步 provenance loader、版本 / 层级 / 运行 / 输入摘要 / stale 状态。

附注：

- 不在校验 `el-tooltip`、`CommentTooltip`、`GtGridCell` 外再包一层通用 tooltip；
- 复用 `get_cell_sources` / `TraceSourcePopover` 的触发和定位，增加公式定义、运行、输入和最终值状态；
- auto 单元格显示 provenance；manual / locked / 底稿投影显示对应状态和已有穿透入口；
- 悬停或点击只允许一次在途请求，按项目、年度、章节、表、稳定 addr_id 做缓存键；取消请求不能把当前单元格置为错误。

挂载守卫 `finalValueProvenanceMounts.spec.ts` 登记真实最终值展示面：

- 报表普通表格本期金额列；
- 报表矩阵中确实对应 current financial_report 行的金额列；
- 附注编辑器 auto 单元格显示层；
- 两个既有底稿试点只做兼容性回归，不把底稿域信封伪装成 S5 已交付。

守卫既检查组件 / 读取链存在，也检查手工移除接线后会红；不能只 grep 组件名。

## 8. 迁移、权限与并发约束

- V/R 迁移号实施时扫描磁盘、共享库已应用版本和候选树三方结果；不在本 spec 写死版本号；
- `financial_report.run_id` 有外键、索引和可空兼容策略；JSONB 字段和 ORM `Mapped[]` 同步；
- provenance 查询只读项目成员可见；输入列表不能越过当前项目 / 合并项目的现有权限边界泄露子项目原始数据；
- 报表运行、附注执行、公式推送的 run 记录必须与写入事务边界一致；失败和保存点回滚不得产生假成功；
- 新端点必须加入 router registry、OpenAPI / schema 和端点级鉴权配方表。

## 9. 测试与变异矩阵

### 9.1 纯函数 / 单元

- `ProvenanceEnvelopeV1` 字段、枚举、必填关系和 schema_version；
- 定义 hash 的 canonical 规则，空白归一、Decimal 序列化、跨域字段过滤；
- 输入收集器嵌套、重复 key、顺序无关、任一原子变化敏感、200 条截断但全量 digest；
- report / note / push 三个定义身份解析器逐域验证 version / hash / layer；
- `value_state` 与 `calculation_applied` 的表驱动组合。

### 9.2 真 PG / 端点

- 报表 full / affected / stale 三路各有 run；affected 只更新依赖闭包；失败行保留旧信封；
- 项目公式覆盖的 definition layer/version/hash 正确；current 与 prior 不混用；并发运行按锁定策略可重复验证；
- 附注 preset / global / template / project、manual / locked / kept / failed 的信封语义；
- 推送 auto / manual / locked / pending_confirm、目标未写入、保存点回滚；
- provenance 读取端点的 anon / non-member / readonly / 可访问项目输入隔离；
- UnifiedLineage 端点的 registry 成功、not_found、registry error 和多底稿结果。

### 9.3 前端

- 报表 current 值来源展示、懒取一次、过期标记、空信封和 403；
- 附注来源弹窗与校验 / 批注 / 编辑互不破坏；稳定 addr_id 在多表 / 投影表下正确；
- 新挂载守卫；单区域 vue-tsc；注入类型错误必须能报错；
- Playwright 实测 current 值、附注 auto 值、公式变更 stale、输入摘要变化和无信封空态。

### 9.4 磁盘变异

至少覆盖：

1. `compute_row` 删除输入收集 → 输入摘要测试红；
2. 定义 hash 改回只比公式文本 → stale 测试红；
3. 报表 affected / stale 任一路径不创建 run 或不写 run_id → 三路闭环测试红；
4. 失败行覆盖旧 provenance → 失败保留测试红；
5. report 有效配置丢项目层 metadata → definition identity 测试红；
6. note 执行删除 `_formula_provenance` 写入 → 附注信封测试红；
7. push manual / locked 被错误标为 calculation_applied → 状态矩阵测试红；
8. 恢复 `note_wp_mapping` SQL → SQL 守卫和 UnifiedLineage 端点测试红；
9. ReportView 删除 current provenance 接线 → 最终值挂载守卫红；
10. 附注把 provenance tooltip 包在既有 tooltip 外 → 模板结构 / 浏览器行为测试红。

## 10. 实施顺序与任务级依赖

1. **Task 0：现状重算与契约夹具**。先生成三域字段、入口、写入方、路由和挂载面清单；没有清单不进入迁移。
2. **Task 1：统一契约与定义身份**。先实现纯函数 schema、canonical digest 和 report / note / push 三个 identity resolver；本阶段不写业务值。
3. **Task 2：报表迁移与运行上下文**。完成 V/R、ORM、run context、full / affected / stale 三路和 freshness hash；再开放 provenance API。
4. **Task 3：R2 溯源替换**。复用统一 registry accessor，先过 UnifiedLineage 端点和 SQL 守卫。
5. **Task 4A / 4B：附注与推送**。Task 4A 附注执行器依赖 S2 已交付的分类回写和 S3 stale-state 接缝；Task 4B 推送仅依赖 Task 1 的规则 identity 和 input collector，可独立实施。
6. **Task 5：最终值展示**。后端响应契约稳定后，报表扩展 tooltip，附注扩展既有来源弹窗；不得先做 UI 再倒推后端字段。
7. **Task 6：PG、端点、变异、浏览器和干净树收尾**。验证候选树而不是只验证脏工作区。

任务边界：

- S1 只提供底稿有效定义统一；S1 不等待 S5 的报表 / 附注 / 推送实施；
- S2 提供附注执行器既有入口改造；S5 负责把 run / provenance 接到该入口；
- S3 消费本 spec 提供的 definition hash / input digest 做 stale 判据，但 S5 不代替 S3 的唯一写入方裁决；
- 公式推送已有 `FormulaPushRun`，S5 不新建第二套推送运行表；
- `report_generation_run` 只服务报表域，不能拿来承载附注或推送运行。

## 11. 待确认决策的默认实施值

若用户未另行改变 D1~D5，实施按以下默认值：

- D1：底稿域延期；
- D2：存量报表不回填；
- D3：展示输入最多 200 条，digest 全量；
- D4：只展示报表 current provenance；
- D5：附注复用现有来源弹窗，报表单独扩展 provenance 展示。

## 12. 设计复核后的实施闸门（2026-10-31）

本节修订 ADR-FPE-01、08、09 中关于单一 `provenance` JSON 可同时表示“最近计算”和“当前最终值”的表述；若与前文示例冲突，以本节为准。

### ADR-FPE-12：计算尝试与最终值状态的双层模型

`ProvenanceEnvelopeV1` 改为**一次计算尝试的不可变记录**，最少包含：

```json
{
  "schema_version": 1,
  "attempt_id": "uuid",
  "domain": "report|note|push",
  "value_slot": "current",
  "run_id": "uuid",
  "computed_at": "ISO-8601 UTC",
  "computed_by": "uuid|null",
  "calc_version": "engine:version",
  "definition_ref": {"kind": "report_config|formula_setting|push_rule|preset", "id": "stable-id-or-key"},
  "definition_version": 1,
  "definition_layer": "global|project|template|preset|system",
  "definition_snapshot": {"canonical_execution_fields": "..."},
  "definition_hash": "sha256…",
  "inputs": [],
  "input_count": 0,
  "inputs_truncated": false,
  "input_digest": "sha256…",
  "calculated_value": "12.34|null",
  "calculation_status": "succeeded|failed|skipped",
  "error_code": "optional-stable-code"
}
```

`definition_snapshot` 只保留可执行字段的 canonical 投影；其序列化结果必须与 `definition_hash` 一致。定义记录可由管理员覆盖或删除时，读取端不得只依赖 `definition_ref` 回查当前版本。

三个最终值存储位置，即 `financial_report.provenance`、`table_data["_formula_provenance"][addr_id]` 和 `formula_push_state.provenance`，统一存 `FinalValueProvenanceV1`：

```json
{
  "schema_version": 1,
  "value_slot": "current",
  "value_state": "auto|manual|locked|kept|pending_confirm|failed",
  "calculation_applied": true,
  "applied_attempt": "ProvenanceEnvelopeV1|null",
  "last_calculation": "ProvenanceEnvelopeV1|null"
}
```

- `applied_attempt` 只在计算结果实际成为当前最终值时更新；
- `last_calculation` 总是记录最近一次成功、失败或被跳过的尝试；
- manual、locked、kept、pending_confirm 下的未采用计算仅更新 `last_calculation`，不得覆盖 `applied_attempt`；
- `calculation_applied` 仅描述 `last_calculation` 是否被采用。`calculation_status=succeeded` 不能推导为已采用；
- `calculated_value` 是公式求值结果，当前最终值继续从各域既有最终值字段读取，避免把未采用值误展示为当前值；
- 存量没有信封时两个 attempt 都为 `null`，读取端返回 `legacy=true`，不得伪造 auto 来源。

### ADR-FPE-13：定义、运行和输入的可审计边界

1. 各域 identity resolver 必须产生 `definition_ref`、`definition_snapshot`、`definition_version`、`definition_layer` 和 `definition_hash`。hash 投影按域设置显式字段白名单与投影版本测试向量；无关展示字段变化不得改变 hash，实际执行字段变化必须改变 hash。
2. `run_id` 必须指向可查询记录：报表为 `report_generation_run`，推送为既有 `formula_push_run`。附注若没有可复用运行表，新增最小 `note_formula_run` 或等价持久化记录，至少含 project、year、section、trigger、actor、started/finished、status、计数和错误摘要。
3. 输入收集器不得依赖临时 Task 0 清单作为唯一证明。Task 0 的接入矩阵必须沉淀为提交到仓库的测试夹具或代码生成清单；各执行域对每类输入至少有一条漏 emit 变异。
4. 全量输入只用于 count 与 digest。展示原子必须设单项和值长度上限，并以 canonical Decimal 文本保存；不支持的对象类型应明确失败，不能调用 `str()` 后静默纳入 digest。

### ADR-FPE-14：权限、并发与失败提交

- `inputs` 中来自其他项目或子企业的原子必须携带最小来源权限标记。provenance 读取端按**当前请求人**过滤或脱敏这些原子，并返回 `inputs_redacted`；无权访问者只能获得安全的计数、digest 和中文说明，不能看到原始值、项目标识或主体标签。
- 报表使用项目 + 年度粒度的运行锁和 run fence；附注至少使用项目 + 年度 + 章节粒度的运行 fence；推送按目标稳定身份建立等价 fence。旧 run 在新 run 已完成后不得更新 `applied_attempt` 或 `last_calculation`。
- 可预期的单行/单格失败必须在保存点内形成 `partial` 或失败 attempt，不得使调用方事务进入 aborted。成功或部分成功的运行记录与对应 final provenance 在同一事务提交。
- 全局事务回滚后，如需留 `failed` run，必须在新的显式事务中创建失败记录；不得遗留 `succeeded` / `partial` 运行记录、run_id 或 applied provenance。
- 附注 provenance 写入必须经过现有 table_data 保存链的保留性核验。任一编辑器保存、自动同步、刷新或投影回写不得静默剥离 `_formula_provenance`。

### ADR-FPE-15：R2 响应矩阵与任务依赖

`GET /api/projects/{project_id}/lineage` 的附注子源统一使用以下可观测结果：

| 情况 | `partial` | 稳定状态 / 错误码 | 结果 |
|---|---:|---|---|
| 自定义映射或 registry 映射成功 | false | `mapped` | 返回全部 `wp_code`，保留一对多顺序 |
| 注册表中不存在该章节 | false | `not_found` | 成功表达“当前无映射”，不伪装为数据库错误 |
| 项目自定义映射格式非法或指向非法条目 | true | `PROJECT_MAPPING_INVALID` | 保留错误留痕，不退回默认映射掩盖配置错误 |
| registry 无法读取或校验失败 | true | `REGISTRY_UNAVAILABLE` | 保留原因，不能吞成空映射 |
| 数据库查询异常 | true | `NOTE_MAPPING_QUERY_FAILED` | 用保存点隔离子源错误 |

实施依赖重排为：

1. S5 Task 0、Task 1 先完成公共清单与契约；
2. Task 2（报表）、Task 3（R2）和 Task 4B（push）可在 Task 1 后独立推进；
3. Task 4A（附注）必须等待 S2 Task 2 的分类回写完成，并与 S3 的 stale-state 写入/清除边界做接口级联调；
4. Task 5 分为报表和附注两个展示子项，分别等待其后端读取契约稳定；
5. Task 6 不得以“每项都有代码”为完成条件。Task 0、范围决策和收尾动作以清单、测试、变异、浏览器或明确的不实施证据验收。

## 13. Task 0 重新基线（2026-10-31，HEAD `cd45ec129`）

以下是本次启动现算，不替代实施时针对候选树的迁移号复核。完整机器可读清单位于临时目录 `tmp_formula_provenance/baseline/`，其中 `lifecycle_paths.json` 补充运行记录、锁和 table_data 保存链盘点。

| 域 | 实际写入 / 读取入口 | 已有能力 | 本 spec 缺口 |
|---|---|---|---|
| report | `generate_all_reports`、`regenerate_affected`、`recalculate_stale_rows` 均经 `report_row_compute.compute_row/write_row` | 三路共享逐行写入 | 没有 run 记录、provenance 或运行 fence |
| note | `disclosure_notes.apply_formulas`、`note_workpaper_pull_service` → `execute_note_formulas` | 已有稳定 cell addr 与 `cell-sources` 读取链 | 没有可查询 run、provenance 或 fence；多条 table_data 写路径须做保留性验收 |
| push | `run` / `run_and_commit` → `_save_states` | `FormulaPushRun`、`FormulaPushState`、项目年度进程锁和 PG advisory lock | 没有 final provenance、target fence 或旧运行覆盖保护 |
| lineage | `ReportTraceService.trace_section` | `note_workpaper_sync_registry.json` 是当前注册表文件 | 仍直接查询不存在的 `note_wp_mapping` 表 |
| frontend | `ReportView` 本期 `GtAmountCell`；附注既有 `CellTraceDialog` / `TraceSourcePopover` | 附注已有最终来源请求链，两个底稿试点已有 tooltip | 报表未挂来源展示；附注需扩展既有响应而非再套 tooltip |

输入接入的初始矩阵已覆盖：报表 `TB/SUM_TB/ROW/SUM_ROW/ADJ` 与预载；附注表内及跨表 `TB/REPORT/NOTE/WP/PRIOR/AGING`；推送 binding、调整和 note writer。Task 1 必须将这份临时清单提炼为受版本控制的覆盖夹具，不能把这次盘点当作永久证明。

## 14. 实施结果与设计偏离（2026-11-01）

### 14.1 实际交付

| 交付面 | 实际实现 | 验收结论 |
|---|---|---|
| 公共契约 | `formula_provenance.py` 提供不可变 `ProvenanceEnvelopeV1` 与双层 `FinalValueProvenanceV1`；`formula_inputs.py` 负责嵌套输入收集、全量 digest 与 200 项展示截断 | 未采用尝试不会覆盖旧 `applied_attempt`；非法类型 fail-closed |
| 报表 | V236/R236 新增 `report_generation_run`、`financial_report.run_id/provenance`；`report_provenance.py` 给 full / affected / stale 安装同一运行上下文与项目年度锁；读取端点只返回 current | 三路 run 可查询；定义 hash 优先判 stale；prior 未复用 current 信封 |
| R2 | `resolve_section_workpapers()` 统一读取项目覆盖与 `note_workpaper_sync_registry.json`；`ReportTraceService` 与 UnifiedLineage 复用该访问器 | 多章节、一对多底稿、not_found 和三类稳定错误码均有端点证据；旧表 SQL 守卫打红 |
| 附注 | V238/R238 新增 `note_formula_run`；`note_formula_provenance.py` 提供章节锁、运行记录和稳定地址；`_formula_provenance` 经编辑、刷新、投影写入链保留 | auto 更新 applied + last；manual / locked / kept 仅更新 last；S2 类别分流与 S3 stale 边界已联调 |
| 推送 | V237/R237 新增 `formula_push_state.provenance`；继续复用 `FormulaPushRun`；`formula_push/persistence.py` 集中状态、目标 fence 与信封写入 | 不新增第二套 run；目标未写、manual / locked / pending_confirm 不冒充已采用 |
| 前端 | 报表本期格挂 `ReportProvenanceTooltip`；附注扩展既有 `CellTraceDialog` / `cell-sources` | prior 与无 current 对应的矩阵格不挂；没有新增嵌套 tooltip |

迁移号按实施时三路扫描落为 V236、V237、V238，并各有同号 R 文件。它们只在一次性快照库验证，未在共享库 `audit_platform` 执行。

### 14.2 与设计草案的实际差异

1. ADR-FPE-01 的早期单层 JSON 示例已被 ADR-FPE-12 明确取代。生产代码只采用双层模型。
2. 报表定义身份没有改变既有 `ReportConfig` 查询 API；`EffectiveReportDefinition` 元数据作为运行期附加属性保留实际来源行、层级、版本与 hash，避免扩大调用面。
3. 附注 coverage 与 provenance 从大文件拆到 `note_formula_coverage.py`、`note_formula_provenance.py`；推送持久化拆到 `formula_push/persistence.py`；报表运行上下文拆到 `report_provenance.py`。拆分为行数门所需，不改变公开行为。
4. 浏览器写入全部发生在一次性 PG 快照中的【UAT】项目。为了让旧基线前端可运行，临时 worktree 补齐两个该基线缺失的 composable / AI 接口 shim，并拦截已登记且与 S5 无关的 `row-note-mapping` 422 与 `notes-tree` 404。验收仍真实访问 S5 的 report provenance、note cell-sources、生成和公式执行端点；临时覆盖不提交。
5. Task 6 中 403、空信封、legacy、输入截断、跨项目脱敏等分支由端点与组件测试覆盖；浏览器重点验证真实已采用、未采用、stale、输入变化和运行记录，不伪造跨项目业务数据。

### 14.3 验收证据

- 后端：核心 184 passed；附注来源相邻 127 passed。
- 真 PG：迁移与来源场景通过；迁移完整性 / schema 漂移相对 HEAD `added=[]`。双方同有 3 个快照预存失败：V205/V208/V222 checksum 漂移相关两项，以及已过期的 `gt_wp_type` 预期一项。
- 前端：相邻 13 文件 106 passed；ESLint 0 error；区域 vue-tsc baseline 25 / candidate 13，`added=[]`，没有 OOM。
- 变异：契约 3、报表 2、R2 4、附注 4、推送 1、前端挂载 2、类型 1，均按目标形态变红并恢复原 SHA-256。
- 浏览器：BS-002 全量、affected、stale 三个 attempt 不同；TB `1001` 变化后 input digest 变化，未引用 BS-003 attempt 不变；附注 `八、1` 显示 auto 已采用，以及 manual / locked 未采用但保留旧 applied attempt。独立 Playwright 记录 `console_errors=0`、`page_errors=0`。
- 临时原始证据位于 `tmp_formula_provenance/`，关键事实已写入本节；临时目录在提交前清理。

## 15. 五角色复盘

### 业务合伙人

来源浮层现在能回答“当前数从哪里来、哪次计算、哪版定义、哪些输入、这次计算是否真的被采用”。人工值和锁定值不会再被一次成功求值误标成公式值。底稿域仍按 D1 延期，没有用不完整定义冒充已交付。

### 项目经理

范围保持在报表 current、附注自动公式、公式推送与 R2。三个域各有可查询 run，报表和附注有明确串行粒度，推送沿用既有项目年度锁。没有扩到 prior、合并附注或底稿公式，也没有对真实项目做批量回填。

### 质控

最有价值的判据是双向不变量：引用 TB 的 BS-002 digest 随输入变化，未引用 BS-003 attempt 不变；manual / locked 的 `last_calculation` 前进而 `applied_attempt` 保留。单看“接口 200”或“有 provenance 字段”都不足以证明正确。变异逐条验证未采用覆盖、定义 hash、旧表 SQL、运行标签、前端挂载和嵌套 tooltip。

### 审计助理

报表金额格悬停即可看到公式、最终状态、当前值、定义、最近计算和输入摘要；附注沿原右键“溯源到底稿/试算表”进入，不改变单元格编辑、批注和校验交互。manual / locked 状态使用中文标签，并明确“本次计算未采用当前值”。

### EQCR

跨项目输入在读取时按当前访问人过滤，持久信封仍保留可审计 digest；computed_by 由 run 的 actor 解析，不从前端或全局上下文猜测。PG advisory lock、进程锁、run fence 和事务边界均有测试。一次性快照验证后删除，避免把验收数据或新迁移落入共享库。

## 16. 最终裁定与后续边界

S5 的 R1~R3 与 ADR-FPE-01~15 已按上述范围实现。D1~D5 保持默认值：底稿域延期、存量报表不回填、展示最多 200 项但 digest 取全量、报表只展示 current、附注复用既有来源弹窗。

后续只在 S1 完成底稿有效定义统一后另立底稿 provenance 接入；共享库迁移由独立发布窗口执行。本 spec 不修改已归档历史，不吸收 S9 报表公式、S3 写入方治理或其他并发规格的改动。
