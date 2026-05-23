# Requirements Document — 高级查询模块剩余 P1-P2 增强项

## Introduction

高级查询模块（CustomQueryDialog + AdvancedQueryBuilder + SheetCellRangePicker）已沉淀 18 个 commit（最新 `bc66f48`），完成 9 维度数据接入、3 层底稿树、项目级裁剪、多区域选区、三级数据源策略、snapshot 增量保护、模板浏览模式、缓存自动失效等核心能力。本 Spec 收口剩余 15 项增强（其中 6 项业务驱动 P1、5 项架构升级 P2、4 项体验细节），目标是把"查询 + 编辑回写 + 跨 sheet 追溯 + 数据源治理 + **跨模块统一 + 模板联动 + 模板入口可达性**"七条线一次性彻底闭环，避免折中方案与遗留 fallback。

新增的 Req 13/14/15 直面三个长期能力鸿沟：
- **跨模块查询**（Req 13）：底稿享有 cell 选区 + 公式还原 + 双向写回能力，但报表/附注/调整分录/试算表 4 个同样模板化的模块只能整体查不能 cell 级，能力分裂导致用户在底稿外的查询场景必须切多个工具
- **模板联动**（Req 14）：模板库页面（WpTemplateDetail / 报表模板管理 / 附注模板编辑）和高级查询是两条平行线，从模板看实际数据要切页面、从查询结果回模板溯源没路径，两边数据形态相同却互相隔离
- **模板入口可达性**（Req 15）：现有「我的模板」/「保存为模板」入口在 3 个查询界面中分散且不一致，且底层 `custom_query_templates` 表存在缺失 bug（500 错误），加上保存配置缺关键字段（cell_range / sheet_name / 分页 / 排序），导致模板系统形同虚设

本 Spec 严格遵循已沉淀的判定规则：
- 「项目维度查询参数 + 项目级缓存键 + 递归扁平化 + seed 对齐 + ancestorKeys 精确过滤」五件套
- 「用户编辑后入库 JSONB 优先 → 文件 cache 次之 → 计算引擎兜底」三级数据源策略
- 「openpyxl read_only iter_rows 一次性扫 + 字典缓存 + try-except」三件套
- 6000 并发目标 → 所有同步 IO 必须 `run_in_executor`
- 缓存键禁用手动 v 号，必须用响应头 `X-Indicators-Schema-Version=N` 自动失效
- working_paper 表无 year 列、wp_index 字段是 audit_cycle、report_config 是模板表无金额列
- 死代码立即删除，单 commit 全量提交，停加新功能聚焦核心

## Definition of Done

本 Spec 全部任务完成的判定标准（必须全部满足，缺一不可）：

1. **代码侧**：15 项增强全部落地，主代码合入主干；旧 fallback / DEPRECATED 注释 / `structure.json` 三处写入等死代码全部物理删除（不保留兼容包装）
2. **测试侧**：每项 P1 至少 1 条 e2e + 2 条单测；P2 架构项至少 1 条迁移幂等性测试 + 1 条回滚测试；体验细节至少 1 条 vitest；跨模块 (Req 13) 必须覆盖 4 模块 × 选区/写回/公式还原 共 12 条 e2e；模板入口完整性 (Req 15) 至少 1 条 e2e 覆盖 3 处入口同步状态；总新增 / 修改测试用例 ≥ 55 条且全部 green
3. **数据侧**：`wp_template_registry` 表完成 migrate（206 条 wp_account_mapping + 184 主底稿 / 1040 sheet 全量入库 + version 字段递增）；`parsed_data` GIN 索引上线且 `EXPLAIN ANALYZE` 验证走索引；`report_snapshot.data` / `consol_note_data.data` JSONB 内含公式字段的 cell 数有埋点统计
4. **性能侧**：6000 并发场景下 LibreOffice 实例 ≤ 2、批量查询 5 个 wp_code 并发 P95 ≤ 3s、5000 cell 选区前端首屏 ≤ 500ms；跨模块 cell 查询 P95 ≤ 200ms（走 JSONB 路径）
5. **审计侧**：相同 (user, source, filters) 在 5s 窗口内 audit_log 仅记 1 条；写回操作 + 跨 sheet 追溯 + 跨模块 cell 写回 + 模板联动跳转均产生独立审计事件
6. **文档侧**：`#dev-history` 追加本轮成果摘要、`#conventions` 同步新增红线（含跨模块 source 命名空间统一规约 + 模板联动事件总线契约）、本 Spec 三件套（requirements.md / design.md / tasks.md）完整且互相引用一致；`#architecture` 更新 wp_template_registry 表结构 + GIN 索引 + LibreOffice 池化策略 + 4 模块 cell 提取器架构图
7. **回归侧**：现有 18 commit 已落地能力（项目级裁剪、三级数据源、snapshot 增量、模板浏览、缓存自动失效）测试全 pass，无任何回归；模板库 3 个页面（WpTemplateDetail / 报表模板管理 / 附注模板编辑）原有功能不受影响

## Glossary

- **Advanced_Query_Module**：高级查询模块整体，含前端 `CustomQueryDialog` / `AdvancedQueryBuilder` / `SheetCellRangePicker` 与后端 `/api/custom-query/*` 路由集
- **Batch_Query_Controller**：前端批量查询协调器，负责多 wp_code 并发拆分 + 限流 + 分组渲染
- **Snapshot_Writer**：双向编辑写回管线，写 `parsed_data['univer_snapshot']` + xlsx + 标 prefill_stale + emit cross-ref:updated
- **Cross_Sheet_Resolver**：跨 sheet 公式追溯组件，递归解析 `=Sheet!Cell` 引用链至最深 3 层
- **WP_Template_Registry**：新建 PG 表 `wp_template_registry`，从 `wp_account_mapping.json` + `step_sheet_mapping.json` 双源 migrate 入库的统一模板注册表
- **Snapshot_GIN_Index**：在 `working_papers.parsed_data` 上的 GIN 索引，支持 JSONB 路径查询科目编码 / 公式跨项目检索
- **Single_Source_Snapshot**：univer-save 单源化策略，仅写 `parsed_data['univer_snapshot']` JSONB，废弃 `structure.json` + 重复 xlsx 写
- **Audit_Throttle**：审计日志节流器，对相同 (user_id, source, filters_hash) 在 5s 窗口内只记 1 条
- **LibreOffice_Pool**：LibreOffice 池化管理器，模块级 `asyncio.Semaphore(2)` 限制 + UserInstallation 隔离 + 启动时健康探测
- **Range_Memory**：选区记忆持久化，按 (user_id, wp_code, sheet_name) 维度记录最后选区
- **Snapshot_Staleness_Chip**：snapshot 过期警告 chip，`saved_at > 30 天` 时前端提示
- **Range_Paginator**：大 range 自动分页，单次渲染 ≤ 100 行
- **Formula_Trace_Popover**：formula 列鼠标悬停 popover，展示原始公式 + 引用链路
- **Schema_Version_Header**：响应头 `X-Indicators-Schema-Version=N`，用于前端缓存自动失效
- **Univer_Snapshot**：用户保存底稿时 Univer 写入 `parsed_data['univer_snapshot']` 的 slim IWorkbookData（仅 v + f）
- **Cross_Module_Cell_Picker**：跨模块单元格级查询能力的统一抽象，把底稿的 `wp_code|sheet|cell_range` 路由模式扩展到报表/附注/调整分录/试算表 4 个模块（统一 source 命名空间 `report:` / `note:` / `adj:` / `tb:`）
- **Module_Cell_Resolver**：每个模块对应的 cell 提取器（`_query_report_cells` / `_query_note_cells` / `_query_adj_cells` / `_query_tb_cells`），统一返回 `{cell_ref, value, formula, sheet_name}` 形态供 SheetCellRangePicker 复用
- **Template_Library_Bridge**：模板库 ↔ 高级查询双向桥，左：模板页直接挂「📊 高级查询入口」按钮按当前模板预填 source；右：高级查询结果右键「🔗 跳模板溯源」反查到对应模板项
- **Cross_Module_Tree_Schema**：indicators 树新增「按模板形态分组」视图，跨模块统一以「模板 → 章节 → cell」三层渲染（替代现有「按数据源分类」单一视图，可切换）

## Requirements

---

### Requirement 1（P1-5）多底稿批量查询

**User Story:** 作为审计经理，我希望能在底稿树上 ctrl+点击多选若干 wp_code（例如同一循环下的 D2 / D3 / D5）后一次性发起批量查询，以便横向对比同期数据，无需反复切换 source 重复执行。

#### Acceptance Criteria

1. WHEN 用户在底稿树上按住 ctrl 键点击主底稿节点，THE Advanced_Query_Module SHALL 把该节点加入多选集合并视觉高亮（紫底白字 chip 列在工具栏左侧）
2. WHEN 多选集合非空且用户点击「批量查询」按钮，THE Batch_Query_Controller SHALL 按多选集合中的 wp_code 拆分为 N 次 `/api/custom-query/execute` 请求，并以最大并发 5 提交（超过 5 个时排队等待）
3. WHEN 任意一次子请求失败，THE Batch_Query_Controller SHALL 在结果区对应 wp_code 分组下展示该次错误信息（不阻塞其它子请求结果渲染），并记录单独 audit_log 条目
4. WHEN 全部子请求返回，THE Advanced_Query_Module SHALL 按 wp_code 分组渲染结果（每组独立 el-table + 折叠面板，组头显示 wp_code + 行数），并暴露「合并导出」按钮把所有分组合并到单 xlsx 多 sheet
5. IF 多选集合为空且用户点击「批量查询」，THEN THE Advanced_Query_Module SHALL 弹出 ElMessage warning 提示「请先 ctrl+点击至少一个底稿节点」并阻断请求

---

### Requirement 2（P1-6）双向编辑写回

**User Story:** 作为审计助理，我希望在选区结果表里直接编辑某个 cell 后能写回底稿，并自动触发交叉引用刷新，避免在查询页和底稿编辑器之间反复切换。

#### Acceptance Criteria

1. WHEN 用户在选区结果表的 cell value 列双击进入编辑态并提交新值，THE Snapshot_Writer SHALL 在单一事务内同步更新 `working_papers.parsed_data['univer_snapshot']` JSONB 与 xlsx 文件 cache，写入失败时整体回滚
2. WHEN 写回成功，THE Snapshot_Writer SHALL 把对应 working_paper 的 `prefill_stale` 标记置 true，并通过事件总线 emit `cross-ref:updated` 事件携带 `{wp_code, sheet_name, cell_ref, new_value}` payload
3. WHEN 用户提交编辑时携带的 `X-File-Opened-At` 时间戳早于当前 `working_papers.updated_at`，THE Snapshot_Writer SHALL 拒绝写入并返回 HTTP 409 + 冲突详情（latest_updated_at + latest_editor），前端弹出冲突对话框引导用户重载
4. WHEN 写回完成，THE Advanced_Query_Module SHALL 调用 `audit_logger.log_action(custom_query.cell_writeback)` 记录 (user, wp_code, sheet, cell_ref, old_value, new_value) 完整轨迹
5. IF 当前 source 不属于 workpaper:* 命名空间或当前用户对该 wp_code 无写权限，THEN THE Snapshot_Writer SHALL 禁用 cell 编辑入口（双击不进入编辑态）并 tooltip 说明原因

---

### Requirement 3（P1-X）跨 sheet 公式追溯

**User Story:** 作为审计经理，我希望鼠标悬停含跨 sheet 引用的 formula 单元格时能自动展开引用链（例如 `=底稿目录!A2` → 目标 sheet 真实值），递归到第 3 层就停止，以便快速排查公式来源。

#### Acceptance Criteria

1. WHEN 选区结果表的 formula 列 cell 公式形如 `=Sheet_Name!Cell_Ref` 或含多个跨 sheet 引用，THE Cross_Sheet_Resolver SHALL 调用 `address_registry.parse_uri` 解析每个引用片段并构建有向引用图
2. WHEN 用户鼠标悬停该 cell ≥ 300ms，THE Formula_Trace_Popover SHALL 展开引用链并展示「原始公式 → 第 1 层引用值 → 第 2 层引用值 → 第 3 层引用值」共 4 层信息
3. WHILE 引用链递归深度超过 3 层，THE Cross_Sheet_Resolver SHALL 在第 3 层之后用 `…(更多 N 层)` 占位且不再发起请求
4. IF 引用链中出现循环引用（A → B → A），THEN THE Cross_Sheet_Resolver SHALL 检测到环并在 popover 标红「⚠ 检测到循环引用」并停止递归
5. WHEN 引用的 sheet 不存在或 cell 越界，THE Formula_Trace_Popover SHALL 在该层显示「⚠ 引用目标缺失」红色提示且不阻塞其它分支展开

---

### Requirement 4（P2-7）双源合并入 DB

**User Story:** 作为平台架构师，我希望把 `wp_account_mapping.json` + `step_sheet_mapping.json` 双源合并到 `wp_template_registry` 表，根治双源漂移 logger.warning，并支持版本号追踪。

#### Acceptance Criteria

1. THE WP_Template_Registry SHALL 持久化 184 条主底稿记录，字段包含 `wp_code` (PK) / `wp_name` / `cycle` (A~N+S) / `account_codes` JSONB / `sheets` JSONB / `applicable_standard` JSONB / `version` INTEGER / `updated_at` TIMESTAMPTZ
2. WHEN Alembic migration 执行，THE WP_Template_Registry SHALL 从 `wp_account_mapping.json` (206 条 v2025-R5) 与 `step_sheet_mapping.json` (179 底稿 / 1040 sheet) 全量入库且行数 = SQL `SELECT count(*)` 与 JSON 双源去重并集一致
3. WHEN 应用启动加载模板树，THE Advanced_Query_Module SHALL 优先从 `wp_template_registry` 读取（不再读 JSON 文件），且 JSON 文件保留为种子源仅 migration 使用
4. IF migration 检测到双源同 wp_code 的字段冲突（例如 sheets 列表差异），THEN THE WP_Template_Registry SHALL 以 `step_sheet_mapping.json` 为准（sheet 全集权威源）写入并把差异写到 migration 日志
5. WHEN 模板内容更新（例如新增底稿），THE WP_Template_Registry SHALL 在 `version` 字段 +1 且新版本响应头 `X-Indicators-Schema-Version` 同步递增触发前端缓存失效

---

### Requirement 5（P2-9）parsed_data GIN 索引

**User Story:** 作为数据分析师，我希望能跨项目查询「全平台所有底稿中含某科目编码（如 1122）的 cell」，以便做横向数据穿透，目前没有索引会全表扫描。

#### Acceptance Criteria

1. THE Snapshot_GIN_Index SHALL 在 `working_papers.parsed_data` 上建立 GIN 索引覆盖 `parsed_data->'univer_snapshot'->'sheets'` JSONB 路径
2. WHEN Alembic migration 创建该索引，THE Snapshot_GIN_Index SHALL 使用 `CREATE INDEX CONCURRENTLY` 避免锁表，且失败时清理 `_ccnew` 残骸
3. WHEN 用户提交跨项目科目编码检索请求，THE Advanced_Query_Module SHALL 通过 `parsed_data @> '{...}'` 形式 SQL 查询，且 `EXPLAIN ANALYZE` 输出包含 `Bitmap Index Scan on idx_wp_parsed_data_gin`
4. WHILE 索引尚在构建中（CREATE CONCURRENTLY 进行时），THE Advanced_Query_Module SHALL 降级走顺序扫描并在响应头加 `X-Index-Status=building`
5. IF GIN 索引体积超过 500MB，THEN THE Snapshot_GIN_Index SHALL 在监控指标 `pg_index_size` 触发告警提示 DBA 评估 jsonb_path_ops 替代 jsonb_ops

---

### Requirement 6（P2-10）structure.json 单源化

**User Story:** 作为平台架构师，我希望 univer-save 接口不再写 3 处（xlsx + structure.json + parsed_data），改成只写 `parsed_data` JSONB，三式联动改读 JSONB，减少磁盘 IO。

#### Acceptance Criteria

1. WHEN 前端调用 `POST /api/working-papers/{id}/univer-save`，THE Single_Source_Snapshot SHALL 仅写 `working_papers.parsed_data['univer_snapshot']` JSONB（保留 xlsx 落盘作为下载源），不再写 `structure.json` 文件
2. WHEN 三式联动（底稿 ↔ 报表 ↔ 附注）任一端读取结构数据，THE Single_Source_Snapshot SHALL 从 `parsed_data['univer_snapshot']` 解析（不读 `structure.json`）
3. THE Single_Source_Snapshot SHALL 在迁移完成后物理删除所有 `structure.json` 文件 + 相关读写代码 + 单元测试 mock，不保留 fallback 逻辑
4. WHEN 旧项目残留 `structure.json` 文件存在，THE Single_Source_Snapshot SHALL 通过一次性脚本 `scripts/_migrate_structure_to_jsonb.py` 把内容回填至 `parsed_data['univer_snapshot']` 后删除文件，脚本执行完即删
5. IF `parsed_data['univer_snapshot']` 缺失或损坏，THEN THE Single_Source_Snapshot SHALL 由查询路径走 LibreOffice 重算兜底（不再退回 structure.json）并记录监控指标 `snapshot_missing_total`

---

### Requirement 7（P2-11）审计日志洪泛节流

**User Story:** 作为合规审计员，我希望用户连续点击 sheet 节点时不会产生高频重复 audit_log，避免日志洪泛掩盖真正的敏感操作。

#### Acceptance Criteria

1. WHEN `audit_logger.log_action(custom_query.execute)` 被调用且 (user_id, source, filters_hash) 三元组在最近 5 秒窗口内已记录，THE Audit_Throttle SHALL 跳过本次写入并把内存计数器 `audit_throttle_skipped_total` +1
2. WHEN 5 秒窗口过期或三元组任一字段变化，THE Audit_Throttle SHALL 正常写入并刷新窗口起点
3. THE Audit_Throttle SHALL 使用 Redis 键 `audit:throttle:{user_id}:{sha1(source+filters)}` 设 TTL=5s 实现分布式节流（避免单进程内存方案在多 worker 失效）
4. WHEN 写回操作 (`custom_query.cell_writeback`) 或跨 sheet 追溯 (`custom_query.cross_sheet_trace`) 触发，THE Audit_Throttle SHALL 不参与节流（敏感操作必须每次记录）
5. WHILE Redis 不可用，THE Audit_Throttle SHALL 降级为「不节流，全部记录」并产生 logger.warning 不阻塞请求

---

### Requirement 8（P2-12）LibreOffice 池化 + 健康检查

**User Story:** 作为运维工程师，我希望 LibreOffice 重算路径在 6000 并发场景下不会被打挂，需要进程数限制 + Windows 用户配置隔离 + 启动健康探测。

#### Acceptance Criteria

1. THE LibreOffice_Pool SHALL 在模块级声明 `asyncio.Semaphore(2)` 限制同一时刻最多 2 个 soffice 子进程
2. WHEN 在 Windows 平台启动 soffice 子进程，THE LibreOffice_Pool SHALL 为每个调用拼接 `-env:UserInstallation=file:///tmp/soffice_<pid>_<tid>` 参数避免 user profile 冲突
3. WHEN FastAPI 应用启动 (`startup` 事件)，THE LibreOffice_Pool SHALL 探测 4 个候选路径并执行 `soffice --version` 验证响应，失败时记录 logger.error 但不阻塞应用启动（保留三级数据源前两级仍可用）
4. WHEN soffice 子进程超过 60s 未返回，THE LibreOffice_Pool SHALL 强制 kill 子进程 + 释放 semaphore 并返回 HTTP 504 Gateway Timeout
5. IF semaphore 等待队列长度 ≥ 10，THEN THE LibreOffice_Pool SHALL 在响应头加 `X-Recompute-Queue-Depth=N` 并产生 metric `libreoffice_queue_depth` 暴露给 Prometheus

---

### Requirement 9（体验细节 P2-13）选区记忆

**User Story:** 作为审计助理，我希望同一 wp_code/sheet 重新打开选区器时能自动回填上次的选区，节省手动重复拖选的时间。

#### Acceptance Criteria

1. WHEN 用户在 SheetCellRangePicker 完成选区并点击「应用」，THE Range_Memory SHALL 把选区表达式按 (user_id, wp_code, sheet_name) 维度持久化（前端 localStorage 键 `gt:cqd:range-memory:{user_id}:{wp_code}:{sheet_name}`）
2. WHEN 用户再次以相同 (wp_code, sheet_name) 打开 SheetCellRangePicker，THE Range_Memory SHALL 自动回填最近一次选区表达式且光标定位到首个区域
3. THE Range_Memory SHALL 保留每个 (wp_code, sheet_name) 最近 1 条记录（超过自动覆盖），且单个 user 最多保留 50 条 LRU 淘汰
4. WHEN 用户点击工具栏「清除记忆」按钮，THE Range_Memory SHALL 清空当前 (wp_code, sheet_name) 的记忆条目
5. IF 回填的选区表达式因 sheet 结构变化（行数减少）而越界，THEN THE Range_Memory SHALL 自动 clamp 到现有范围并提示「上次选区已部分调整」

---

### Requirement 10（体验细节 P2-14）snapshot 过期警告

**User Story:** 作为审计经理，我希望选区结果上方能看到 snapshot 数据是否过期（saved_at > 30 天），避免引用陈旧数据做判断。

#### Acceptance Criteria

1. WHEN 选区结果返回的 `source = univer_snapshot` 且其 `saved_at` 距当前时间 > 30 天，THE Snapshot_Staleness_Chip SHALL 在结果区顶部显示橙色 chip「⚠ 数据可能过时（XX 天前保存）」
2. WHEN `saved_at` ≤ 30 天，THE Snapshot_Staleness_Chip SHALL 不显示提示
3. WHEN 用户点击 chip，THE Snapshot_Staleness_Chip SHALL 弹出对话框展示 saved_at 精确时间戳 + 最后编辑人 + 「立即重算」按钮（调用 LibreOffice 兜底路径）
4. WHEN `source = xlsx_recomputed` 或 `xlsx_cache`，THE Snapshot_Staleness_Chip SHALL 显示对应蓝色「⚙ 重算结果」/ 灰色「📋 模板数据」中性 chip 替代过期警告
5. IF `saved_at` 字段缺失（旧数据未含该字段），THEN THE Snapshot_Staleness_Chip SHALL 显示灰色「数据时间未知」chip 不报错

---

### Requirement 11（体验细节 P2-15）大 range 自动分页

**User Story:** 作为审计助理，我希望选了 5000 cell 时前端不一次性渲染卡死，而是按 100 行翻页提供流畅体验。

#### Acceptance Criteria

1. WHEN 选区结果行数 > 100，THE Range_Paginator SHALL 启用前端分页器（每页 100 行）且首屏只渲染第 1 页
2. THE Range_Paginator SHALL 在结果表底部展示 el-pagination（页码 + 每页大小 50/100/200/500 可选 + 跳转输入框）
3. WHEN 用户切换页码，THE Range_Paginator SHALL 在 16ms 内完成切换（已下载数据本地分页，不重发请求）
4. WHEN 用户点击「全部展开」按钮，THE Range_Paginator SHALL 在确认对话框警告「将渲染 N 行，可能卡顿」后允许一次性渲染
5. IF 选区结果行数 > 5000，THEN THE Range_Paginator SHALL 强制启用分页且禁用「全部展开」按钮

---

### Requirement 12（体验细节 P2-16）公式溯源 popover

**User Story:** 作为审计经理，我希望鼠标悬停 formula 列时直接看到原始公式 + 引用链路概览，无需双击 cell 才能看公式。

#### Acceptance Criteria

1. WHEN 鼠标悬停 formula 列 cell ≥ 300ms 且该 cell 有公式（非纯值），THE Formula_Trace_Popover SHALL 显示 popover 包含「原始公式（橙色 ƒ 前缀斜体）」「第 1 层引用列表（最多 5 个）」「数据源标识 chip」三块信息
2. WHEN 公式包含跨 sheet 引用，THE Formula_Trace_Popover SHALL 把跨 sheet 引用渲染为可点击链接（点击调用 Cross_Sheet_Resolver 展开第 2~3 层）
3. WHEN 公式纯本 sheet 引用（如 `=A1+B1`），THE Formula_Trace_Popover SHALL 仅显示原始公式 + 引用单元格当前值列表（不递归）
4. WHEN 用户鼠标移出 cell，THE Formula_Trace_Popover SHALL 在 200ms 延迟后关闭（避免快速划过抖动）
5. IF cell formula 解析失败（语法错误等），THEN THE Formula_Trace_Popover SHALL 显示「⚠ 公式解析失败」红色提示 + 原始字符串方便调试

---

### Requirement 13（P1，新增）跨模块单元格级查询能力

**User Story:** 作为审计经理，我希望报表 / 附注 / 调整分录 / 试算表 4 个模块都能像底稿一样在 SheetCellRangePicker 选区，把"单元格级查询 + 公式还原 + 双向写回"能力从底稿一处扩展到全部模板化模块，不再有"只有底稿才行"的能力鸿沟。

**业务场景**：
- 报表场景：用户选「资产负债表 BS-002 货币资金行」想查所有项目同行的金额对比 → 当前只能查模板结构，无法选 cell 级
- 附注场景：用户选「五-1-1 货币资金 表头第 2 列」想查实际填表数据 → 当前 `disclosure_note:五-1-1` 只能整章节查
- 调整分录场景：用户想查所有 D2 应收账款 AJE 调整的借方金额 → 当前 `adj_aje` 只能列分录不能选 cell
- 试算表场景：用户想查 1122 应收账款的「审定数」列 → 当前 `tb_detail` 只能列科目不能选列维度

#### Acceptance Criteria

1. THE Cross_Module_Cell_Picker SHALL 把现有 `workpaper:{wp_code}|{sheet}|{cell_range}` source 命名空间扩展为统一 4 模块格式：`report:{report_type}|{cell_range}` / `note:{section_id}|{cell_range}` / `adj:{adjustment_type}|{cell_range}` / `tb:{aux_dim}|{cell_range}`，前端 SheetCellRangePicker 透明识别走同一选区器
2. WHEN 用户在树上点击 4 模块任一叶子节点，THE Module_Cell_Resolver SHALL 按对应模块加载真实 cellData：报表→`report_snapshot.data` JSONB / 附注→`consol_note_data.data` JSONB / 调整分录→`adjustments` 表 row 拼成虚拟 sheet / 试算表→`trial_balance` 行列拼成虚拟 sheet
3. THE Module_Cell_Resolver SHALL 统一返回 `{cell_ref, value, formula, sheet_name, module}` 形态供 SheetCellRangePicker 复用，4 模块 module 字段分别为 `report` / `note` / `adj` / `tb`
4. WHEN 4 模块的 cell 含公式（如报表行 formula 字段、附注 cross-ref 引用），THE Module_Cell_Resolver SHALL 走 Cross_Sheet_Resolver 引用链解析（最深 3 层），公式还原优先从 `report_snapshot.data` / `consol_note_data.data` 读 cache，缺失时降级 LibreOffice 重算
5. WHEN 用户对 4 模块任一模块的 cell 做双向写回（Req 2），THE Snapshot_Writer SHALL 按模块路由：报表写 `report_snapshot.data` / 附注写 `consol_note_data.data` / 调整分录走 `adjustments` 表 UPDATE / 试算表走 `trial_balance.audited_amount` UPDATE，单一事务保证一致性

---

### Requirement 14（P1，新增）模板页面双向联动

**User Story:** 作为审计师，我希望模板库（wp-templates / 报表模板管理 / 附注模板编辑）页面能直接跳到高级查询查实际数据，反向也能从查询结果回到模板溯源，让两边不再"各走各的"。

**业务场景**：
- 正向（模板 → 查询）：用户在 `WpTemplateDetail` 浏览 D2 应收账款审定表模板时，想看「张三项目实际填了多少」 → 当前只能跳 WorkpaperEditor，无法直达高级查询多项目对比
- 反向（查询 → 模板）：用户在高级查询结果看到 D2-1 cell B7 异常值，想看「这个 cell 模板原始定义是什么 / 为什么会有这个值」 → 当前只能脑补，无路径回到模板视图

#### Acceptance Criteria

1. WHEN 用户在 `WpTemplateDetail` / 报表模板管理页 / 附注模板编辑页 任一模板查看页面，THE Template_Library_Bridge SHALL 在工具栏挂「📊 高级查询」按钮，点击 `eventBus.emit('open-custom-query', { tab: 'basic', source, project_id? })` 自动预填当前模板对应 source 打开高级查询
2. WHEN 用户在高级查询结果表上某 cell 右键，THE Template_Library_Bridge SHALL 弹出菜单含「🔗 跳模板溯源」选项，点击调用 `address_registry.parse_uri(uri)` 解析得目标模板信息，用 `router.push` 跳到 `WpTemplateDetail` / 报表模板 / 附注模板对应详情页且 query 参数标识 highlight 行/cell
3. WHEN 跳模板溯源时目标模板已在 `wp_template_registry` 注册（Req 4），THE Template_Library_Bridge SHALL 直接跳并 highlight 目标行；未注册时降级提示「该模板未在 registry，请先 migrate」
4. THE Cross_Module_Tree_Schema SHALL 提供「按数据源分类」（默认，现有 9 维度）/ 「按模板形态分组」（新增，按底稿/报表/附注/调整分录 4 模板形态聚合）两种树视图，工具栏 toggle 切换，记忆用户偏好到 sessionStorage
5. WHEN 用户从模板页跳查询触发 `open-custom-query` 事件，THE Advanced_Query_Module SHALL 自动选中预填的 source 并展开树到对应叶子节点（reveal + scroll-into-view），无需用户手动定位

---

### Requirement 15（P1，新增）「我的模板」可达性 + 选区器保存为模板 + CustomQueryTemplate 表完整性

**User Story:** 作为审计经理，我希望「我的模板」入口在所有查询入口（CustomQueryTab / CustomQueryDialog / SheetCellRangePicker 选区结果）都触手可及，并且能直接从当前选区状态一键保存为模板，模板包含完整查询配置（含 cell_range / sheet_name / 分页 / 排序），下次加载能完全还原。

**业务场景**：
- 当前 bug：`/api/custom-query/templates` 端点返回 500，根因是 `custom_query_templates` 表未通过 init_tables.py 扫描创建（DB 早期初始化未含此模型，alembic 也未跑），导致用户点「我的模板」按钮就崩
- 入口分裂：保存为模板按钮目前只在 `CustomQueryTab`（独立页）有，`CustomQueryDialog`（弹窗）有按钮但不带 cell_range 上下文，`SheetCellRangePicker` 选区器完全没有保存入口 → 用户在选区器里点了 50 个单元格后想保存只能切回弹窗重新选
- 配置不完整：现有 `config` 字段只存 `project_id / year / source / filter_text`，**缺 `cell_range / sheet_name / 列宽 / 分页大小 / 排序字段`**，加载模板回到不完整状态

#### Acceptance Criteria

1. THE `custom_query_templates` SHALL 在所有运行时环境（开发/测试/生产）均存在，缺失时由启动检查工具 `scripts/_ensure_custom_query_tables.py` 一次性补建（含 PK、FK、scope+updated_at 复合索引、creator+updated_at 复合索引），首次部署/旧 DB 升级也能自动恢复
2. THE Advanced_Query_Module SHALL 在 3 个查询入口都暴露完整模板按钮组（「📚 我的模板」+「💾 保存为模板」）：CustomQueryTab 独立页 / CustomQueryDialog 工具栏 / SheetCellRangePicker 选区结果区，3 处共用同一份模板状态（loadTemplates 缓存到 sessionStorage 5 分钟）
3. WHEN 用户从 SheetCellRangePicker 选区状态点击「保存为模板」，THE Advanced_Query_Module SHALL 把完整选区上下文写入 `config` JSONB：`{project_id, year, source, sheet_name, cell_range, filter_text, conditions[], selected_columns[], available_columns[], page_size, sort_field, sort_order}`，加载时按字段顺序还原所有控件状态
4. WHEN 用户在「我的模板」对话框点击某模板的「加载」按钮，THE Advanced_Query_Module SHALL 自动还原至模板保存时的查询状态（含选区器自动打开 + range 回填 + 树节点 reveal + 列宽恢复），并 emit 一次审计 `audit_logger.log_action('custom_query.template_loaded', { template_id, scope })`
5. IF 模板的 `config.cell_range` 引用的 sheet 已不存在（底稿被裁剪 / sheet 被改名），THEN THE Advanced_Query_Module SHALL 弹出对话框提示「模板引用的 sheet「XX」已不存在，是否清空选区后加载其它配置」，用户确认后保留 source/filters 但清空 cell_range

---

## 优先级一览

| 编号 | 优先级 | 类别 | 工时估算 |
|------|--------|------|----------|
| Req 1 | P1 | 业务驱动 | 1-2 天 |
| Req 2 | P1 | 业务驱动 | 2-3 天 |
| Req 3 | P1 | 业务驱动 | 1-2 天 |
| Req 13 | P1 | 跨模块扩展 | 3-4 天 |
| Req 14 | P1 | 模板联动 | 2-3 天 |
| Req 15 | P1 | 模板入口/保存 | 1-2 天 |
| Req 4 | P2 | 架构升级 | 2-3 天 |
| Req 5 | P2 | 架构升级 | 1 天 |
| Req 6 | P2 | 架构升级 | 1-2 天 |
| Req 7 | P2 | 架构升级 | 0.5 天 |
| Req 8 | P2 | 架构升级 | 1 天 |
| Req 9 | 体验 | 体验细节 | 0.5 天 |
| Req 10 | 体验 | 体验细节 | 0.5 天 |
| Req 11 | 体验 | 体验细节 | 0.5 天 |
| Req 12 | 体验 | 体验细节 | 0.5 天 |

合计估算 ≈ 18-25 天，建议拆 4 轮迭代：① P1 业务三件（4-7 天） ② P1 跨模块+模板联动+入口完善（6-9 天） ③ P2 架构五件（5-7 天） ④ 体验细节四件批量（2 天）。

**依赖关系（落地顺序敏感）**：
- Req 13（跨模块查询）依赖 Req 4（wp_template_registry 入库）已完成 → 建议 Req 4 先于 Req 13 落地
- Req 14（模板联动）依赖 Req 13 的统一 source 命名空间 + Req 4 的 registry → 必须 Req 4/13 先落
- Req 2（双向写回）需扩展到 Req 13 的 4 模块写回路由 → 建议 Req 2 v1 先支持底稿，v2 再扩展 4 模块
- Req 3（跨 sheet 追溯）+ Req 12（公式 popover）共用 Cross_Sheet_Resolver → 一起落地
- 推荐路径：Req 4 → Req 5/6/7/8（架构） → Req 13（跨模块）→ Req 14（联动）→ Req 1/2/3（业务）→ 体验细节
