# 实施计划：S5　取数结果的来源信封（formula-provenance-envelope）

> 以 requirements.md 与 design.md 为准，需求编号 R1~R3；交付边界为 S5-R（报表 current）、S5-N（附注自动公式）、S5-P（公式推送）、S5-U（最终值展示与 R2 溯源）。
> **本 spec 不实施底稿域信封**：底稿有效定义统一属于 S1，S1 完成后另立接入任务。
> 实施顺序按 design §10：契约与身份 → 报表 → R2 → 附注 / 推送 → UI → PG / 端点 / 变异 / 浏览器收尾。

## 通用纪律

- 临时产物、探针、日志、截图、变异备份统一放仓库根 `tmp_formula_provenance/`；完成后清理。
- 迁移号实施时扫描磁盘迁移、共享库已应用版本和候选树三方结果，生成 V/R 配对文件；不写死版本号。
- 真 PG 写入只在回滚事务内的【测试】项目；不得把 provenance 验收数据留在真实项目。
- 新 API 必须同步 router registry、Pydantic / OpenAPI 契约、service / ORM / migration，并做端点级鉴权测试。
- 每个**改变运行时行为**的任务必须有生产代码、正向测试和至少一条磁盘变异；Task 0、范围决策和收尾动作以清单、测试、变异、浏览器或明确的不实施证据验收。变异单独运行，逐字节 / sha256 恢复。
- 提交前在干净候选树运行相关测试，按（文件、错误码、信息）与 HEAD 基线比较；浏览器使用 `http://127.0.0.1:3030`，写入验收只用【测试】项目。
- 不修改 `formula-hub-integrity-closure` 或其他已归档历史文档；交接勘误只写本 spec。

## [x] 0. 现状复核、契约夹具与启动门

- 重新现算 design §1：`financial_report` / `ReportConfig` 有效定义、三条报表写入路径、`formula_push_run/state`、附注 `_formulas` / `_user_formulas` / preset、`note_wp_mapping` SQL、registry、多表 / 投影表、报表和附注最终值挂载面。
- 产出清单：`write_paths.json`、`definition_identity_sources.json`、`input_sources.json`、`final_value_mounts.json`、`route_registry.json`，保存到 `tmp_formula_provenance/baseline/`；计数只记录现算值，不写死源码行号。
- 从 `input_sources.json` 提炼受版本控制的输入接入矩阵夹具或生成规则；后续单测必须据此验证每类实际输入均能 emit，临时目录不能成为唯一证据。
- 为报表、附注、推送分别确认可查询的运行记录、最终值写入位置、并发 fence / 锁和所有会写 `table_data` 的保存链。
- 校验 S1 / S2 / S3 的实际依赖状态：S1 只阻塞底稿后续接入，S2 只提供附注既有执行入口，S3 消费 hash / digest 不反向改变本 spec 范围。
- Verify：清单可从代码 / 路由 / ORM / registry 双向对账；没有清单不得开始迁移。

## [x] 1. 统一信封契约、定义身份与输入摘要（ADR-FPE-01~03）

- 建立不可变计算尝试 `ProvenanceEnvelopeV1` 与最终值包装 `FinalValueProvenanceV1` 的后端 schema / 纯函数构造器：`attempt_id`、`calculated_value`、`calculation_status`、`definition_ref`、canonical `definition_snapshot`、`applied_attempt`、`last_calculation`、`value_slot`、`value_state`、`calculation_applied`、`schema_version` 及必填关系。
- 新建 `backend/app/services/formula_inputs.py`：ContextVar 嵌套收集、重复 key、多域输入原子、Decimal canonical 序列化、稳定排序、全量 digest、最多 200 条展示输入、`input_count` / `inputs_truncated`、单项和值长度限制、来源权限标记；不支持的对象类型必须显式失败，不能 `str()` 后静默入摘要。
- 建立三个定义身份适配器：
  - report：返回含实际来源行、稳定 `definition_ref`、不可变执行字段投影、版本、hash、layer 的 `EffectiveReportDefinition`，修正项目覆盖行丢 metadata 的问题；
  - note：从 `EffectiveSlot` / 稳定 preset 目录取得稳定 `definition_ref`、不可变执行字段投影、版本、hash、layer；
  - push：从 `PushRule.version` 和规则集 digest 取得稳定 `definition_ref`、不可变规则执行投影、版本、hash、system layer。
- 只完成契约和纯函数，不在本任务写 `financial_report` / 附注 / 推送业务值。
- Verify：单测覆盖双层 schema、未采用尝试不覆盖 applied attempt、hash 空白归一、字段白名单、Decimal、顺序无关、重复 key、任一输入敏感、截断仍按全量 digest、非法对象拒绝；三域 identity 的 ref / snapshot / version / hash / layer 逐值断言。
- 变异：删除 `collect()` 接线或任一已登记输入 emit、改 hash 只取公式文本或纳入无关展示字段、把重复 key 改成 dict 覆盖、把 Decimal 改 float、删除 definition ref / snapshot；对应测试必须逐条打红。

## [x] 2. 报表运行记录、三路写入与 provenance API（ADR-FPE-04~07）

- 动态取号并新增 V/R：`financial_report.run_id` 外键 / 索引、`financial_report.provenance`（`FinalValueProvenanceV1`），`report_generation_run` 运行记录及 status / 计数 / error 字段；ORM、迁移、service 三层一致。
- 建立 `ReportGenerationContext`，显式携带 run_id、project_id、year、trigger、triggered_by、started_at、calc_version、run fence 和 definition snapshot；禁止 service 内读全局当前用户。
- 改造 `report_row_compute.write_row()` 与 `ReportEngine`：full、`regenerate_affected`、`recalculate_stale_rows` 三路共用上下文；成功时原子更新 current 值、`applied_attempt` 与 `last_calculation`，失败只更新失败 attempt 而保留旧值 / 旧 run_id / 旧 applied attempt；值未变但重算仍更新运行时间和输入 digest。
- 明确项目 / 年度运行锁与 run fence；可预期行失败用保存点生成 partial / failed attempt，成功或 partial run 与对应最终来源同事务提交；整体回滚后的 failed run 仅在新事务留痕，不能留下成功 run、run_id 或 applied attempt。
- freshness 改为优先比较当前有效定义 hash；存量无信封行退回旧公式 / calc_version 判据并标 legacy；hash 变化只扩闭包，不清旧信封。
- 新增 `GET /api/reports/{project_id}/{year}/{report_type}/rows/{row_code}/provenance`：返回 current 值、最终值包装、run 摘要、stale / legacy、`inputs_redacted` 和受权限过滤的 computed_by 文案；读取时按当前访问人脱敏跨项目输入，注册到 router registry，响应加入 schema。
- Verify：真 PG 回滚事务覆盖 full / affected / stale、项目公式覆盖层级、current / prior 不混用、失败行保留旧 applied attempt、未采用/失败 attempt 可追溯、整体回滚留失败 run 的规则、并发 fence、anon / non-member / readonly 端点鉴权和跨项目输入脱敏。
- 变异：任一路径不创建 run / 不写 run_id；失败覆盖旧 applied attempt；effective config 丢 project metadata / definition ref；stale 恢复只比公式文本；端点删项目权限或跳过跨项目输入脱敏；每项都必须打红。

## [x] 3. `note_wp_mapping` 改读 registry 与 UnifiedLineage 接线（ADR-FPE-10）

- `report_trace_service.trace_section()` 只通过 `note_readiness_service` 统一访问器取映射；项目 `wizard_state.note_wp_mapping` 优先，模板类型、listed / soe 复数章节和一对多 `wp_code` 按契约处理。
- 通过 `NoteAccountMappingService` 使用真实字段，不新增或推导不存在的 `account_codes`；明确 registry `not_found`、registry 不可读、项目自定义映射非法和数据库异常四种结果。
- 按 design ADR-FPE-15 固定响应矩阵：mapped / not_found 为 `partial=false`；`PROJECT_MAPPING_INVALID`、`REGISTRY_UNAVAILABLE`、`NOTE_MAPPING_QUERY_FAILED` 为 `partial=true`，错误不得降级成默认映射或空映射。
- 清理旧 `FROM/JOIN/INSERT/UPDATE note_wp_mapping` 运行路径；守卫覆盖大小写、引号和 SQL 变体，并做违规样本自检。
- Verify：端点级 `GET /api/projects/{project_id}/lineage` 验证映射成功 `partial=false`、多底稿、not_found、registry error 和错误留痕；不能只测 service。
- 变异：恢复旧表 SQL、只取一个多底稿、忽略项目自定义映射、把 registry error 吞成空映射；SQL 守卫和端点测试必须打红。

## [x] 4A. 附注执行信封（ADR-FPE-08、12~14）

- 前置：S2 Task 2 的 `execute_note_formulas()` 分类回写已合入；与 S3 明确 stale 标记、清除和公式失败边界后才接线。本任务不重新实现 S2 的公式执行能力。
- `execute_note_formulas()` 增加显式 `triggered_by`，区分用户、事件和系统入口；每个章节执行关联可查询的运行记录。若无可复用记录，动态取号新增 `note_formula_run` 的 V/R、ORM 和 service，而非生成无归属 UUID。
- 公式定义继续由 `_formulas` / `_user_formulas` 保存；`table_data["_formula_provenance"][addr_id]` 写 `FinalValueProvenanceV1`，其中 `last_calculation` 是完整计算尝试，`applied_attempt` 仅代表当前最终值的真实自动来源。
- 版本 / hash / layer / ref / snapshot 使用 Task 1 的 note identity resolver；preset 必须有稳定目录版本；多表和投影表使用 `_note_cell_addr_id()` 稳定身份。
- 自动公式实际写入时更新 applied attempt；值未变化仍更新 last calculation 的计算时间和输入 digest。manual、locked、`kept_workpaper`、失败只更新 last calculation / 状态，绝不覆盖已应用来源或当前值。
- 以项目 + 年度 + 章节 run fence 防止旧执行覆盖新执行；通过所有 table_data 保存、自动同步、刷新和投影写入链做保留性回读，任何路径不得剥离 `_formula_provenance`。
- 扩展既有 `get_cell_sources` / `TraceSourcePopover` 响应，返回最终值状态、applied attempt、last calculation、`inputs_redacted`，不新造第二条附注 cell 来源读取链路。
- Verify：真 PG 回滚事务覆盖 preset / global / template / project、auto / manual / locked / kept / failed、可查询 run、fence、保存点回滚、computed_by、input digest、table_data 往返保留和 S3 stale 边界。
- 变异：删除 `_formula_provenance` 写入或任一已登记 input emit、将 manual / locked 未采用尝试覆盖 applied attempt、丢失 preset ref / layer / version、移除 run fence、让保存链剥离 provenance；对应测试必须逐条打红。

## [x] 4B. 公式推送信封（ADR-FPE-09、12~14）

- 动态取号新增 V/R、ORM 与 service：`formula_push_state.provenance` 存 `FinalValueProvenanceV1`，NULL 兼容历史行；`last_run_id` 仍指向既有 `FormulaPushRun`，不新建第二套推送运行表。
- 推送 rule version、规则集 digest、稳定 definition ref / snapshot、输入收集和 `triggered_by` 接入 Task 1 契约；`FormulaPushRun` 作为所有计算尝试的可查询 run。
- auto 且实际写入时原子更新 applied attempt 和 last calculation；manual / locked / pending_confirm、目标缺失、保存点回滚、运行失败或仅求值未写入时，只保留计算尝试与真实最终值状态，绝不把未采用值标作当前来源。
- 用目标稳定身份的 run fence / CAS 保证慢的旧推送不能覆盖新推送的 applied attempt 或 last calculation；所有成功状态、run 与 provenance 遵守同一事务边界。
- Verify：真 PG 回滚事务覆盖 auto / manual / locked / pending_confirm、目标未写入、保存点回滚、失败、computed_by、input digest、last run 可查询、旧 run 不能覆盖新 run 和跨项目输入脱敏。
- 变异：把未采用状态改成 `calculation_applied=true`、推送失败后保留成功 applied attempt、删除动态迁移/ORM 字段、移除目标 fence、只保存当前值不保存 calculated value；对应测试必须逐条打红。

## [x] 5. 最终值展示面与前端接线（ADR-FPE-11）

- 报表只接 `current_period_amount` 最终展示格；prior、compare 派生列和没有 current financial_report 信封的矩阵值不复用本信封。
- 扩展 `GtFormulaSourceTooltip` 或新建等价 provenance 组件，支持异步读取最终值包装、`applied_attempt`、`last_calculation`、版本 / 层级 / 运行 / 输入摘要 / `inputs_redacted` / stale；ACNR 地址解析只能作为附加信息，不能代替 provenance。
- 附注复用现有 `TraceSourcePopover` / `get_cell_sources` 的触发、定位和缓存；不得把通用 tooltip 包在校验 `el-tooltip`、`CommentTooltip` 或 `GtGridCell` 外面。
- 挂载守卫 `finalValueProvenanceMounts.spec.ts` 登记并验证：报表普通本期金额、确有 current 对应的矩阵金额、附注 auto 单元格；两个既有底稿试点只做兼容回归，不计入底稿域交付。
- 请求按项目 / 年度 / 章节 / 表 / 稳定 addr_id single-flight；取消请求不显示错误，不污染另一个单元格；手工、锁定、底稿投影、未采用计算、空信封和 legacy 行显示真实中文状态，未经授权的跨项目输入只显示脱敏状态。
- Verify：vitest、组件结构守卫、单区域 vue-tsc（注入类型错误必须报错）、前端权限 / 403 / 跨项目输入脱敏 / 空态；浏览器验证 current 报表值、附注 auto 值、已应用与未采用计算的区分、输入摘要和 stale。
- 变异：删除 ReportView current 接线；把附注来源包到既有 tooltip 外；使用显示行列替代稳定 addr_id；把未采用计算误显示为当前来源；任一变异均必须打红。

## [ ] 6. 回归、浏览器实测、候选树与收尾

- 在候选树中运行本 spec 后端单元、真 PG、端点鉴权、前端 vitest / 组件守卫 / 单区域 vue-tsc；按文件、错误码、信息与 HEAD 失败集合对比，只允许候选树自身新增红为 0。
- 真 PG【测试】项目浏览器验收：
  - 报表 current 值悬停 / 点击显示定义 ref / snapshot、版本、层级、运行、计算人、输入摘要、跨项目输入脱敏和 stale；
  - 修改一个 TB 叶子后 affected / stale 重算，引用行 input digest 变化，未引用行不变；
  - 附注 auto 单元格显示 applied attempt 与 last calculation；manual / locked / 底稿投影 / 未采用计算显示真实最终值状态，且保存后 provenance 仍可读；
  - 公式定义改变后旧值显示 stale，失败重算或未采用计算保留旧 applied attempt 并展示 last calculation；
  - 403、空信封、legacy 行和输入截断均有中文空态。
- 变异清单逐条单独运行并 sha256 校验恢复；截图放 `tmp_formula_provenance/screenshots/`，实测后浏览器停回 `about:blank`。
- 迁移、ORM、service、router、OpenAPI、前端 API path 和 router registry 做双向对账；检查 report / note / push 都有可查询 run、正确的迁移与 fence，没有重复推送运行表或底稿信封假交付。
- 更新 `.kiro/specs/INDEX.md` 与 memory 只记录实际交付状态；不在本 spec 代勾 S1 / S2 / S3 / 底稿域任务。
- Verify：需求 R1~R3、design ADR-FPE-01~15、D1~D5 默认值逐项具有代码、测试、浏览器或明确不实施证据；S2 / S3 接缝按 ADR-FPE-15 完成联调记录；推送前按仓库约定运行版本号工具并注明主要变动。

## 实施验收记录（2026-11-01，Task 6 收尾前）

- 迁移在一次性快照库 `fh_snap_fpe_20261101030456` 执行到 V238；未迁移共享库 `audit_platform`，未回填真实项目 provenance。
- 后端最终相关回归：核心 184 passed；附注来源相邻 127 passed；迁移 / schema 候选与 HEAD 失败集合相同（3 个预存项，`added=[]`）。
- 前端相关回归：13 个文件 106 passed；ESLint 0 error（`CellTraceDialog.vue` 保留 5 个既有金额单元格 warning）；单区域 vue-tsc baseline 25 / candidate 13，`added=[]`、`resolved=12`，类型变异得到 TS2322。
- 磁盘变异：公共契约 3/3、报表 2/2、R2 4/4、附注 4/4、推送 1/1、前端挂载 2/2 均按预期红并经 SHA-256 恢复。
- 独立 Playwright 写入仅落一次性快照中的【UAT】项目：报表 full → affected → stale 三路 attempt 可查询；修改 TB `1001` 后 BS-002 input digest 变化、BS-003 attempt 不变；定义 hash 失配显示 stale，stale 重算后清除。附注 `八、1` 的 auto 已采用、manual / locked 未采用且旧 applied attempt 保留；两个 note run 可查询。`console_errors=0`、`page_errors=0`。
- 浏览器证据：`tmp_formula_provenance/browser_acceptance.json` 与 `tmp_formula_provenance/screenshots/` 六张截图。临时前端为避开 HEAD 已登记的无关缺口，补齐两个已提交但旧基线缺失的 composable / AI shim，并拦截 `row-note-mapping` 422、`notes-tree` 404；这些临时覆盖不进入交付。
- 大文件门：`note_formula_generator.py` 1547、`report_engine.py` 2572、`formula_push/engine.py` 997、`ReportView.vue` 1940，均未抬白名单。
