# Requirements Document

## Introduction

本需求文档定义"高级查询模块"（Advanced Query Module）的彻底增强与重构范围。目标是让用户能够对平台下**任何自定义内容**（底稿单元格、试算表、报表行、附注、调整分录，以及任何自定义登记内容）构建自定义查询，并**完整接入新开发的 ACNR（地址坐标名称注册中心 / Address Coordinate & Naming Registry）**，实现**多维度、可导出、可转置（行列转置 / 透视）**的查询能力。

平台现状（已用 codegraph 全库核查 + 架构提案实证，见各需求"溯源"）：高级查询是当前 7 大全局模块中相对最健康（约 90%）的模块，两套入口边界清晰：

1. **业务视图查询** `backend/app/routers/custom_query.py`（2300+ 行）：跨模块 cell 级查询（`report:` / `note:` / `adj:` / `tb:` URI）+ 模板保存（`CustomQueryTemplate` 表，scope=global/personal）+ 批量执行 + cell 回写（`backend/app/services/custom_query/snapshot_writer.py` 10 步事务）+ 跨 sheet 溯源。面向所有角色。
2. **白名单 DSL 构建器** `backend/app/routers/query_builder.py`（仅 admin/manager）：`TABLE_WHITELIST`（16 张只读 audit/财务表，显式排除 user/role/auth/token）+ `JOIN_WHITELIST`（以 projects 为中心）+ `OPERATOR_WHITELIST`，可视化条件 + SQL 预览 + Excel 导出。当前含 `NotImplementedError` 优雅降级分支（非桩）。

前端：`audit-platform/frontend/src/views/CustomQuery.vue`（`/custom-query`）+ `AdvancedQueryBuilder.vue`（S-3 构建器）+ 模板库内嵌 `CustomQueryTab.vue`；Dashboard 有"高级查询"快捷入口。

本 spec 需彻底治理以下方向、无死角：

- **通用内容查询覆盖**：让业务视图查询能覆盖平台下任意可寻址内容（含自定义登记内容），不留寻址盲区。
- **ACNR 接线与 addr_id 身份统一**（§17.5 / D6 / G13）：回写身份从裸 `(wp_id, sheet_name, cell_ref)` 升级为 `addr_id`；快照结果列携带 `addr_id` 供 `GtIndexChip` 下钻；查询"选字段"复用 ACNR 树（`list_sheets` / `list_cells`，与公式选址同一棵树 `useAcnr`）而非自建下拉；同一物理格单一 `addr_id` 身份，回写值与 `WP()` 公式引用对齐，stale chip 追踪一致。
- **多维度 / 转置**：结果支持多分组维度、行列转置（透视）。
- **导出 / 流式**：结果可导出 Excel；大结果集分页 / 流式导出避免 openpyxl 内存峰值。
- **安全 / IDOR / 权限边界**：注册 / 覆盖 / 回写强制 `project_id` + 底稿归属校验以防 IDOR；SQL 全参数化；明确两套入口权限边界并在 UI 提示。
- **缓存 / 性能**：高频相同查询短 TTL Redis 缓存（6000 并发目标）。
- **模板与分享**：查询结果可存模板、分享给项目组、导出、引用到底稿。
- **回写 + 审计日志 + 预览**：任何回写型查询必须预览确认并记录审计日志。

**与 ACNR 的边界（引用而非重写）**：高级查询是 ACNR"四大消费库"之一，必须消费 ACNR 的单一 `resolve()` / `full_resolve()`，不得自建命名表。ACNR 核心（grammar_v1、resolver、catalog、jump_route）在 `.kiro/specs/acnr/` 与 `.kiro/specs/acnr-consumer-wiring/` 中定义，本 spec 采取引用协调，不重写 ACNR 核心。

**技术栈**：Python 后端（FastAPI + asyncpg + SQLAlchemy）+ Redis；TypeScript/Vue 3 前端（Element Plus）。后端 9980 / 前端 3030。

## Glossary

- **高级查询模块 (Advanced_Query_Module)**：统一治理跨模块自定义查询、ACNR 接线、多维度/转置、导出、回写的功能域。
- **业务视图查询 (Business_View_Query)**：`custom_query.py` 提供的面向所有角色的 cell 级跨模块查询入口，通过 `report:` / `note:` / `adj:` / `tb:` URI 寻址。
- **白名单构建器 (Whitelist_Query_Builder)**：`query_builder.py` 提供的仅 admin/manager 可用的白名单 DSL 可视化查询构建入口。
- **ACNR**：地址坐标名称注册中心（Address Coordinate & Naming Registry），平台级目录真源，收敛命名/坐标/跳转，见 `docs/proposals/address-coordinate-name-registry-architecture.md`。
- **addr_id**：ACNR 稳定主键 `{wp_code}/{sheet_code}/{coordinate_key}`，不因 sheet 改名而变。
- **resolve / full_resolve (Resolve_Service)**：ACNR 统一解析入口，输入任意支持语法（五域 URI / `WP()` 公式 / 索引 `ns:target` / 裸 wp+sheet+cell）返回 canonical addr_id + 物理格 + jump_route + 命中状态。
- **jump_route (Jump_Route)**：ACNR resolve 返回的统一前端跳转出口，供 chip 下钻到具体格。
- **useAcnr (Acnr_Composable)**：前端 ACNR 消费 composable（由 `useAddressRegistry` 演进），提供 `buildAddressTree` / `loadCellNodes` 等选址树能力，与公式选址同源。
- **选字段树 (Field_Picker_Tree)**：查询字段选择器所用的 ACNR 地址树（`list_sheets` / `list_cells`），与公式选址同一棵树。
- **快照写入器 (Snapshot_Writer)**：`snapshot_writer.py` 的 10 步事务，将查询结果 cell 回写到底稿 xlsx / 快照。
- **回写 (Writeback)**：将查询结果值写回目标 cell（底稿 / 快照）的动作。
- **快照结果列 (Snapshot_Result_Column)**：查询结果表的一列，其元数据可携带 addr_id 以支持下钻。
- **GtIndexChip (Index_Chip)**：前端索引跳转组件，prop 名为 `value`，走统一 resolve 拿 addr_id + jump_route 跳转。
- **多维度查询 (Multi_Dimension_Query)**：结果支持多个分组维度（如底稿 × 科目 × 期间）的查询。
- **转置 (Transpose)**：查询结果的行列互换 / 透视（pivot），将某维度从行转为列或反之。
- **透视配置 (Pivot_Config)**：定义行维度、列维度、值字段与聚合方式的转置配置。
- **查询模板 (Query_Template)**：`CustomQueryTemplate` 表存储的可复用查询定义。现有模型 scope 取值为 `private`（个人，等价"personal"）/ `team`（项目组）/ `public`（公开）/ `global`（全局）四值；本 spec 沿用该四值模型，不新增 scope 枚举。
- **项目组分享 (Project_Team_Share)**：将查询模板分享给同一项目组成员可见/可用的范围语义。
- **导出器 (Query_Exporter)**：将查询结果导出为 Excel 的组件。
- **流式导出 (Streaming_Export)**：大结果集分页/流式生成 Excel，避免 openpyxl 一次性全量构建的内存峰值。
- **查询缓存 (Query_Cache)**：高频相同查询的短 TTL Redis 缓存。
- **IDOR (Insecure_Direct_Object_Reference)**：越权直接对象引用；本模块须通过 project_id + 底稿归属校验防止跨项目越权读写。
- **底稿归属校验 (Ownership_Check)**：校验目标 cell 所属底稿属于当前用户可访问项目的准入检查。
- **参数化 SQL (Parameterized_SQL)**：使用绑定参数（而非 f-string 字符串拼接）构造 SQL 的安全实践。
- **审计日志 (Audit_Trail)**：记录操作者身份、时间、操作类型、影响范围与结果的日志（`audit_logger.log_action`）。
- **回写预览 (Writeback_Preview)**：回写执行前展示将被修改的 cell 列表与新旧值供用户确认的界面。
- **自定义登记内容 (Custom_Registered_Content)**：用户在平台自定义登记、可被 ACNR catalog 寻址的任意内容。
- **权限边界提示 (Capability_Guidance)**：前端明确"业务视图（所有角色）"与"高级构建器（admin/manager）"能力差异的说明。

## Requirements

---

### Requirement 1: 通用自定义内容查询覆盖

**User Story:** 作为审计人员，我想对平台下任何可寻址内容（底稿单元格、试算表、报表行、附注、调整分录，以及任何自定义登记内容）构建自定义查询，以便不受限于预置的少数几类内容而留下查询盲区。

#### Acceptance Criteria

1. THE Advanced_Query_Module SHALL 支持对 ACNR 五域（tb / report / note / wp / aux）下所有已在 ACNR catalog 登记的内容构建查询，且不依赖任何预置的固定内容类型白名单。
2. WHEN 用户选择一项自定义登记内容（Custom_Registered_Content）作为查询目标, THE Advanced_Query_Module SHALL 通过 Resolve_Service 解析其 addr_id 并将其纳入可查询字段集合、在字段选择器中展示。
3. WHEN 用户提交查询目标, THE Advanced_Query_Module SHALL 在 5 秒内完成对该目标的 addr_id 解析。
4. IF 用户指定的查询目标无法被 Resolve_Service 解析为有效 addr_id, THEN THE Advanced_Query_Module SHALL 逐项列出无法解析的目标标识、指示解析失败，且不执行查询、不返回部分结果。
5. IF Resolve_Service 不可用或在 5 秒内无响应, THEN THE Advanced_Query_Module SHALL 中止查询、返回指示解析服务不可用的错误，且不返回部分结果。
6. THE Business_View_Query SHALL 通过 Resolve_Service 统一寻址，而非各 URI 前缀（`report:` / `note:` / `adj:` / `tb:`）各自维护独立解析逻辑。
7. WHERE 某内容域在 ACNR catalog 中已登记内容数量为 0, THE Advanced_Query_Module SHALL 在字段选择器中不展示该域。
8. WHERE 某内容域在 ACNR catalog 中已登记内容数量为 0, THE Advanced_Query_Module SHALL 提示该域暂不可查询。

> 溯源：`custom_query.py`（2300+ 行，report:/note:/adj:/tb: URI）；ACNR §17 四库共用一个 `resolve()`。

---

### Requirement 2: ACNR 选字段树复用

**User Story:** 作为查询构建者，我想在选择查询字段时复用与公式选址相同的 ACNR 地址树，以便字段来源与公式引用完全一致，不再面对自建下拉与公式选址两套不一致的界面。

#### Acceptance Criteria

1. WHEN 用户打开字段选择器, THE Field_Picker_Tree SHALL 调用 ACNR 的 `list_sheets` 构建 sheet 层级节点树。
2. WHEN 用户展开一个 sheet 节点, THE Field_Picker_Tree SHALL 调用 ACNR 的 `list_cells` 按需加载该 sheet 下的单元格节点。
3. THE Field_Picker_Tree SHALL 复用前端 Acnr_Composable（`useAcnr`）的 `buildAddressTree` 与 `loadCellNodes`，而非自建独立下拉组件。
4. WHEN 用户在 Field_Picker_Tree 中选中一个单元格节点, THE Advanced_Query_Module SHALL 记录该节点的 addr_id（形如 `{wp_code}/{sheet_code}/{coordinate_key}`）作为查询字段标识。
5. THE Field_Picker_Tree 中同一物理格的节点 addr_id SHALL 与公式选址器（如 `WP()` 公式引用）对该格的 addr_id 逐字符一致。
6. WHERE ACNR catalog 中某 sheet 被改名, THE Field_Picker_Tree SHALL 仍通过稳定 addr_id 定位该 sheet 下单元格，且已保存的查询字段 addr_id 不因改名而失效或改变。
7. IF `list_sheets` 或 `list_cells` 调用失败或在 10 秒内无响应, THEN THE Field_Picker_Tree SHALL 显示加载失败提示、保留已选字段不变，并提供重新加载入口。

> 溯源：ACNR §17.5 "选字段：自建下拉 → 复用 list_sheets/list_cells（与公式选址同一棵树）"。

---

### Requirement 3: 回写身份升级为 addr_id

**User Story:** 作为平台架构维护者，我想让查询结果回写时存储 addr_id 而非裸 `(wp_id, sheet_name, cell_ref)`，以便回写值与公式引用共享单一身份，stale chip 追踪能对齐同一物理格。

#### Acceptance Criteria

1. WHEN Snapshot_Writer 执行回写, THE Snapshot_Writer SHALL 通过 Resolve_Service 将目标 cell 解析为形如 `{wp_code}/{sheet_code}/{coordinate_key}` 的 addr_id，并以该 addr_id 作为回写身份存储（取代裸 `(wp_id, sheet_name, cell_ref)`）。
2. THE Snapshot_Writer SHALL 使同一物理格在任意次回写中被解析为完全相同的 addr_id，且该 addr_id 与该格的 `WP()` 公式引用 addr_id 一致。
3. WHEN 一个 cell 同时被查询回写值与公式引用, THE Advanced_Query_Module SHALL 保证二者解析到同一 addr_id，以支持 stale chip 对齐。
4. IF 回写目标 cell 因字段缺失、格式非法或目标格不存在而无法被 Resolve_Service 解析为有效 addr_id, THEN THE Snapshot_Writer SHALL 中止该回写、返回指示解析失败的描述性错误，且不修改任何数据。
5. IF Resolve_Service 不可用或在 5 秒内无响应, THEN THE Snapshot_Writer SHALL 中止回写、保持数据不变，并返回指示解析服务不可用的错误。
6. WHILE 回写事务进行中, THE Snapshot_Writer SHALL 保持原有 10 步事务的原子性，任一步失败则回滚至事务开始前状态，不残留部分写入。

> 溯源：ACNR §17.5 / D6 / G13 "回写身份 snapshot_writer 裸 (wp_id, sheet_name, cell_ref) → 存 addr_id"。

---

### Requirement 4: 快照结果列可下钻

**User Story:** 作为审计人员，我想在查询结果表中直接点击结果单元格下钻到其对应的底稿格，以便从查询结果快速追溯到数据来源。

#### Acceptance Criteria

1. WHERE 结果列的值由单一可解析源格产生, THE Snapshot_Result_Column SHALL 在列元数据中携带该源格对应的 addr_id。
2. WHEN 用户在查询结果中点击一个携带 addr_id 的单元格, THE Advanced_Query_Module SHALL 通过 Resolve_Service 获取 jump_route 并经 Index_Chip 跳转到对应底稿格，同时保持当前查询结果视图不变。
3. THE Advanced_Query_Module SHALL 使用 Index_Chip（prop 名 `value`）渲染可下钻的结果单元格。
4. THE Index_Chip 的跳转 SHALL 使用 Resolve_Service 返回的 jump_route，而非前端自行拼接路由。
5. IF 某结果列无对应 addr_id, THEN THE Advanced_Query_Module SHALL 将该列渲染为不含 Index_Chip、不可点击的普通文本列。
6. IF 单元格的 addr_id 可解析但其 jump_route 已失效（目标底稿/格已删除）, THEN THE Advanced_Query_Module SHALL 中止跳转、提示目标已失效，并保持当前查询结果视图不变。
7. IF 下钻目标底稿的 project_id 不属于当前用户可访问项目, THEN THE Advanced_Query_Module SHALL 拒绝跳转、返回 HTTP 403，且不泄露该目标底稿的任何内容。

> 溯源：ACNR §17.5 "快照列溯源：无跳转 → 列元数据挂 addr_id，chip 可下钻到格"；§7.5 铁律"用 resolve 返回的 jump_route"。

---

### Requirement 5: 多维度查询

**User Story:** 作为审计人员，我想按多个维度（如底稿 × 科目 × 期间）对查询结果分组，以便从不同角度分析平台数据。

#### Acceptance Criteria

1. THE Advanced_Query_Module SHALL 支持用户指定 0 到 10 个分组维度，其中每个维度须为有效 addr_id 或结果集中存在的有效列。
2. WHEN 用户指定 1 个或多个分组维度, THE Advanced_Query_Module SHALL 按维度值的唯一组合对结果进行分组聚合，并返回分组后的结果集。
3. WHEN 返回分组后的结果集, THE Advanced_Query_Module SHALL 按分组维度组合的升序对结果行进行排序。
4. THE Advanced_Query_Module SHALL 支持对数值型值字段应用求和、计数、平均、最大、最小五种聚合方式。
5. IF 用户指定的分组维度字段无法解析为有效 addr_id 或有效列, THEN THE Advanced_Query_Module SHALL 返回描述性错误信息并标明无效维度，保留原始查询条件不变，且不执行查询。
6. IF 用户对非数值型值字段应用求和、平均、最大或最小聚合方式, THEN THE Advanced_Query_Module SHALL 返回描述性错误信息并标明不兼容的字段与聚合方式，保留原始查询条件不变，且不执行查询。
7. WHERE 用户未指定任何分组维度, THE Advanced_Query_Module SHALL 返回未分组的明细结果集。

---

### Requirement 6: 结果转置（行列转置 / 透视）

**User Story:** 作为审计人员，我想将查询结果进行行列转置或透视，以便把某个维度从行方向转到列方向查看对比。

#### Acceptance Criteria

1. WHEN 用户提供 Pivot_Config（指定行维度、列维度、值字段与聚合方式，聚合方式取自求和、计数、平均、最大、最小）, THE Advanced_Query_Module SHALL 按该配置将结果透视为行列交叉表，并对落入同一交叉单元格的多个源值应用所指定的聚合方式。
2. WHEN 用户请求对结果集整体行列转置, THE Advanced_Query_Module SHALL 将结果集的行与列互换并返回转置后的结果集。
3. FOR ALL 查询结果集，先转置再转置回来 SHALL 产生与原结果集在单元格值、行标签、列标签及行列顺序上完全一致的数据（round-trip 属性）。
4. IF Pivot_Config 指定的列维度产生的列数超过配置上限（默认 512 列，可配置）, THEN THE Advanced_Query_Module SHALL 返回描述性错误，标明实际列数与上限并提示列维度基数过大，且不执行透视、不修改任何数据、不返回部分结果。
5. WHERE 交叉单元格由单一源格产生, THE Advanced_Query_Module SHALL 在透视结果中保留该交叉单元格对应源数据的 addr_id 以支持下钻。
6. IF 交叉单元格由多个源格聚合产生, THEN THE Advanced_Query_Module SHALL 不为该交叉单元格携带 addr_id，并将其渲染为不可下钻的普通文本单元格。
7. WHEN 某行维度与列维度的组合在源数据中无对应值, THE Advanced_Query_Module SHALL 将对应交叉单元格置为空值，而非填充 0 或返回错误。

---

### Requirement 7: 结果导出 Excel

**User Story:** 作为审计人员，我想将查询结果导出为 Excel，以便离线分析与归档。

#### Acceptance Criteria

1. WHEN 用户请求导出查询结果, THE Query_Exporter SHALL 在 30 秒内将当前结果集（含分组/透视后的形态）导出为 `.xlsx` 文件。
2. THE Query_Exporter SHALL 在导出的 Excel 中保留列标题文本、列顺序、分组/透视后的行列结构与单元格显示值，与界面完全一致。
3. WHEN 导出文件名包含任何非 ASCII 字符（含中文）, THE Query_Exporter SHALL 使用 RFC 5987 编码设置响应文件名。
4. THE Query_Exporter SHALL 在导出内容中包含数据来源标识（addr_id 及其可读名称）以便追溯。
5. WHERE 结果集为 0 行, THE Query_Exporter SHALL 导出仅含标题行的文件并提示结果为空。
6. IF 结果集行数或列数超过 Excel 原生上限（1,048,576 行或 16,384 列）, THEN THE Query_Exporter SHALL 中止导出、不返回文件，并返回指示容量超限的错误。
7. IF 导出过程中发生错误, THEN THE Query_Exporter SHALL 返回描述性错误、不返回损坏或部分文件，并保留原查询结果不受影响。

---

### Requirement 8: 大结果集流式 / 分页导出

**User Story:** 作为审计人员，我想在导出大结果集时不触发服务端内存峰值，以便在 6000 并发目标下导出稳定不崩。

#### Acceptance Criteria

1. WHILE 结果集行数超过流式触发阈值（默认 5000 行，可配置）, THE Streaming_Export SHALL 以分页/流式方式生成 Excel，而非一次性全量构建。
2. THE Streaming_Export SHALL 通过 StreamingResponse 以默认每块 1000 行的方式分块返回导出数据。
3. WHILE 流式导出进行中, THE Streaming_Export SHALL 将单次驻留内存的行数限制在配置上限内（默认 1000 行）。
4. IF 结果集行数超过导出硬上限（默认 1,000,000 行，且不超过 xlsx 单表 1,048,576 行上限）, THEN THE Advanced_Query_Module SHALL 返回描述性错误提示缩小查询范围，且不启动导出。
5. FOR ALL 结果集，流式导出的行内容 SHALL 与非流式导出对同一结果集的行内容一致（model-based 一致性）。
6. IF 流式传输在中途发生错误, THEN THE Streaming_Export SHALL 终止传输并标示导出未完成，不产生可被误认为完整的部分文件。

> 溯源：全局模块改进 P3 "query_builder 导出大结果集分页/流式，避免 openpyxl 全量构建内存峰值"。

---

### Requirement 9: 防 IDOR 的项目与归属校验

**User Story:** 作为平台安全负责人，我想在注册、覆盖、回写路径上强制 project_id 与底稿归属校验，以便防止用户越权读取或修改其他项目的数据。

#### Acceptance Criteria

1. WHEN 用户发起查询注册/覆盖/回写请求, THE Advanced_Query_Module SHALL 在执行任何数据读写之前，校验目标 cell 所属底稿的 project_id 是否属于当前用户可访问的项目集合（即该用户在 project_assignments 中存在有效分派记录的项目）。
2. IF 目标底稿的 project_id 不属于当前用户可访问项目, THEN THE Advanced_Query_Module SHALL 返回 HTTP 403、拒绝该操作、不读取或不修改任何数据，并向调用方返回指示越权访问的错误信息。
3. WHEN Snapshot_Writer 执行跨 sheet 回写, THE Ownership_Check SHALL 在写入前逐一校验每个目标 cell 所属底稿的 project_id 归属。
4. IF 跨 sheet 回写中任一目标 cell 的 project_id 不属于当前用户可访问项目, THEN THE Ownership_Check SHALL 拒绝整个回写事务并回滚，使所有目标 cell 均不被修改。
5. THE Advanced_Query_Module SHALL 对查询注册、覆盖、回写全部路径统一强制执行 Ownership_Check，且未通过 Ownership_Check 的请求不得触达数据读写层。
6. WHEN 查询涉及跨项目数据聚合, THE Advanced_Query_Module SHALL 仅返回当前用户有权访问项目的数据行，并过滤掉所有不可访问项目的数据行。
7. IF 发生 project_id 归属校验失败的越权访问尝试, THEN THE Advanced_Query_Module SHALL 记录一条包含请求用户标识、目标 project_id 与操作类型的审计日志。

> 溯源：架构文档标 IDOR + 跨项目写 为 P0（§5.12/§5.13）。

---

### Requirement 10: 参数化 SQL

**User Story:** 作为平台安全负责人，我想让所有查询 SQL 使用参数化绑定，以便消除 SQL 注入面。

#### Acceptance Criteria

1. THE Advanced_Query_Module SHALL 使用参数化绑定（Parameterized_SQL）构造所有含用户输入的 SQL，使用户提供的值（条件值、集合值、字段/表标识）在最终发送到数据库的 SQL 文本中出现 0 次。
2. THE Advanced_Query_Module SHALL 将用户输入中的 SQL 元字符与关键字作为字面参数值绑定，不将其解释为 SQL 语法。
3. WHEN 查询条件包含 IN 集合参数, THE Advanced_Query_Module SHALL 使用 `= ANY(:codes)` + `list(...)` 形式而非 IN tuple 参数；WHERE 集合为空, THE Advanced_Query_Module SHALL 返回空结果集且不报错。
4. THE Whitelist_Query_Builder SHALL 继续强制 TABLE_WHITELIST / JOIN_WHITELIST / OPERATOR_WHITELIST，新增表、JOIN 或操作符必须经显式登记。
5. IF 查询请求引用未登记的表、JOIN 或操作符, THEN THE Whitelist_Query_Builder SHALL 在执行前拒绝该请求、指明未登记的具体对象、返回描述性错误，且不返回任何数据行、不部分执行。
6. THE Whitelist_Query_Builder SHALL 显式排除 user / role / auth / token 相关敏感表，不允许经任何登记路径纳入白名单。
7. IF 运行时查询计划引用了敏感表（user / role / auth / token）, THEN THE Whitelist_Query_Builder SHALL 无条件拒绝该查询并返回描述性错误。

> 溯源：架构文档标 SQL f-string 为 P0（§5.1）；白名单安全模型是标杆铁律。

---

### Requirement 11: 两套入口权限边界与提示

**User Story:** 作为普通审计人员，我想清楚知道业务视图查询与高级构建器的能力差异与权限边界，以便不误用超出我权限的入口。

#### Acceptance Criteria

1. THE Business_View_Query SHALL 对所有已认证角色开放访问与执行查询。
2. THE Whitelist_Query_Builder SHALL 仅对 admin 与 manager 角色开放访问与执行查询。
3. IF 非 admin/manager 的已认证角色访问 Whitelist_Query_Builder 入口, THEN THE Advanced_Query_Module SHALL 返回 HTTP 403、不加载构建器界面、不执行任何查询，并提示该入口仅限管理员/经理。
4. IF 未认证请求访问任一查询入口, THEN THE Advanced_Query_Module SHALL 返回 HTTP 401 并拒绝访问。
5. WHEN 用户进入高级查询模块, THE Advanced_Query_Module SHALL 展示 Capability_Guidance，明确说明"业务视图（所有角色）"与"高级构建器（admin/manager）"的能力差异。
6. WHILE 当前用户角色不满足高级构建器权限, THE Advanced_Query_Module SHALL 在 UI 中将高级构建器入口显示为禁用（可见但不可点击）并给出原因提示。

> 溯源：全局模块改进 P2 "前端明确业务视图（所有人）vs 高级构建器（admin/manager）能力差异"；合伙人评审 §4.11。

---

### Requirement 12: 高频查询缓存

**User Story:** 作为平台性能负责人，我想让高频相同查询走短 TTL Redis 缓存，以便在 6000 并发目标下降低数据库压力。

#### Acceptance Criteria

1. WHERE 查询在单个 TTL 窗口内的重复请求次数达到或超过可配置阈值（默认 5 次，范围 1 至 1000 次）而被标识为可缓存, THE Query_Cache SHALL 以查询定义与作用范围（含 project_id 与用户可访问范围）组合为唯一键在 Redis 中缓存结果，并设置短 TTL（默认 30 秒，可配置范围 5 至 300 秒）。
2. WHEN 收到与已缓存键完全一致的查询请求且该缓存条目未过期, THE Query_Cache SHALL 直接返回缓存结果而不访问数据库，且在服务端处理耗时不超过 50 毫秒。
3. FOR ALL 缓存命中，缓存返回的结果 SHALL 与直接查询数据库对同一查询定义的结果一致（同一 TTL 窗口内）。
4. WHEN 缓存条目的 TTL 到期, THE Query_Cache SHALL 使该条目失效，并对该键的后续请求重新查询数据库、按 Criterion 1 重建缓存条目。
5. THE Query_Cache SHALL 将不同 project_id 或不同用户可访问范围的查询分别缓存，不跨项目或跨权限复用缓存结果。
6. IF 请求命中的缓存条目不存在或已过期，且在同一 TTL 窗口内存在针对同一缓存键的并发相同请求, THEN THE Query_Cache SHALL 仅向数据库发起一次查询，其余并发请求复用该次查询结果，避免缓存击穿导致的重复数据库访问。
7. IF Redis 不可用或读写缓存失败, THEN THE Query_Cache SHALL 降级为直接查询数据库并返回正确结果，同时记录一次缓存不可用的告警指示，不向调用方返回错误。

> 溯源：全局模块改进 P2 "高频相同查询加 Redis 短 TTL 缓存，减 DB 压力（6000 并发目标）"。

---

### Requirement 13: 查询模板保存、分享与引用

**User Story:** 作为审计人员，我想把查询结果存为模板、分享给项目组、导出并引用到底稿，以便复用查询与沉淀分析成果。

#### Acceptance Criteria

1. WHEN 用户以合法名称（长度 1 至 200 字符）与合法 scope（`private` / `team` / `public` / `global` 之一）保存查询为模板, THE Advanced_Query_Module SHALL 将其持久化到 `CustomQueryTemplate` 表。
2. IF 模板保存失败（名称非法、scope 不属于 `private` / `team` / `public` / `global` 或持久化异常）, THEN THE Advanced_Query_Module SHALL 返回描述性错误、指明失败原因，且不创建部分模板记录。
3. WHERE 模板 scope 为 `global` 或 `public`, THE Project_Team_Share SHALL 使其对所有已认证用户可见；WHERE 模板 scope 为 `team` 且所有者显式分享给项目组（写入 `shared_project_ids`）, THE Project_Team_Share SHALL 仅使对该 project_id 有访问权限的项目组成员可见并可执行；WHERE 模板 scope 为 `private`, THE Project_Team_Share SHALL 仅使所有者本人可见。
4. IF 用户对无分享权限的模板发起分享或对无访问权限的模板发起执行, THEN THE Advanced_Query_Module SHALL 返回 HTTP 403 并拒绝操作。
5. WHEN 用户执行已保存模板, THE Advanced_Query_Module SHALL 依据当前用户的可访问项目范围应用 Ownership_Check，仅返回有权访问项目的数据行。
6. THE Advanced_Query_Module SHALL 支持将查询结果引用到底稿（cell 回写路径），并遵循 Requirement 14 的预览与审计要求。
7. IF 用户执行的模板引用了已不可解析的 addr_id, THEN THE Advanced_Query_Module SHALL 跳过该失效引用、在结果中标注失效项并保留其 addr_id、返回其余有效结果，而非整体失败。

> 溯源：`CustomQueryTemplate` 表 scope=global/personal；合伙人评审 §4.11 "保存为模板、分享给项目组、导出、引用到底稿"。

---

### Requirement 14: 回写预览与审计日志

**User Story:** 作为审计人员，我想在任何回写型查询执行前预览将被修改的内容，并在执行后留下审计日志，以便回写可控且可追溯。

#### Acceptance Criteria

1. WHEN 用户发起回写型查询, THE Advanced_Query_Module SHALL 在 5 秒内返回 Writeback_Preview，列出将被修改的每个目标 cell（不超过 10,000 条）及其新值与旧值。
2. THE Advanced_Query_Module SHALL 仅在用户于确认有效窗口（默认 600 秒）内确认 Writeback_Preview 后执行回写。
3. WHEN 回写执行完成, THE Audit_Trail SHALL 记录操作者身份、UTC 时间戳（精确到秒）、操作类型、目标 addr_id 集合、新旧值与执行结果（成功/失败）。
4. THE Audit_Trail SHALL 对每次回写与跨 sheet 溯源操作逐次记录（不节流），而查询执行按 60 秒窗口聚合为 1 条节流记录。
5. IF 回写在事务中途失败, THEN THE Advanced_Query_Module SHALL 回滚全部改动、返回失败原因，并在 Audit_Trail 中记录失败结果。
6. WHERE Writeback_Preview 为空（无任何 cell 将被修改）, THE Advanced_Query_Module SHALL 提示无可回写内容且不进入确认流程。
7. IF 确认时 Writeback_Preview 已过期或目标 cell 旧值与预览时不一致, THEN THE Advanced_Query_Module SHALL 拒绝执行回写、保持数据不变，并提示需重新预览。
8. IF 回写成功但 Audit_Trail 写入失败, THEN THE Advanced_Query_Module SHALL 回滚回写改动并提示审计记录失败，以保证"无审计不回写"。

> 溯源：合伙人评审 §4.11 "任何回写型查询必须记录审计日志，并有预览确认"；`audit_logger.log_action` 节流策略（回写/溯源不节流）。

---

## 溯源与关联

- 现状实证：`docs/proposals/global-modules-status-and-improvement-2026-05-31.md` §三（高级查询相对最健康，两套入口，P2/P3 改进）。
- ACNR 关联统一：`docs/proposals/address-coordinate-name-registry-architecture.md` §17（四库共用一个 resolve）、§17.5（高级查询回写身份升级为 addr_id / 选字段复用 list_sheets|list_cells / G13）、§7.5（jump_route 铁律）。
- 合伙人评审：`docs/proposals/platform-partner-review-2026-06-06.md` §4.11（模板/分享/导出/引用 + 回写审计 + 预览确认 + 权限分层）。
- 消费者接线协调：`.kiro/specs/acnr-consumer-wiring/`。**边界决策（复盘）**：(1) `cross_sheet_resolver.py` 以本 spec 的「同步纯 BFS + async orchestrator」方案为准，取代 acnr-consumer-wiring task 1.1「BFS 内直调 async full_resolve」（规避 async pitfall），二者不得同时按各自原样落地；(2) 高级查询选字段树归本 spec（Req 2），满足 acnr-consumer-wiring Req 8，若 P4 已建 `CustomQueryFieldPicker.vue` 则复用不重建；(3) 回写身份（addr_id）本 spec 消费，跨消费者失效链收敛仍归 acnr-consumer-wiring。ACNR 核心 `.kiro/specs/acnr/`（不重写）。
- 相关代码锚点：`backend/app/routers/custom_query.py`、`backend/app/routers/query_builder.py`、`backend/app/services/custom_query/snapshot_writer.py`、`audit-platform/frontend/src/views/CustomQuery.vue`、`AdvancedQueryBuilder.vue`、`CustomQueryTab.vue`。
