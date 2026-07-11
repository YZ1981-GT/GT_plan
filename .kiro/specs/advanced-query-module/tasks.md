# Implementation Plan: 高级查询模块（Advanced Query Module）

## Overview

本实施计划把 design.md 的统一寻址查询架构拆解为可增量交付、可独立验证的编码任务。实现语言遵循设计：后端 Python 3.12（FastAPI + asyncpg + SQLAlchemy async + Redis），前端 TypeScript + Vue 3 + Element Plus。后端 9980 / 前端 3030。

组织原则：
- 按交付物分组（数据层 → 统一寻址 → 异步编排 → 准入守卫 → 参数化 SQL → 查询编排 → 分组 → 透视 → 缓存 → 导出 → 模板 → 回写 → 路由门禁 → 前端 → 端到端），每组末尾或关键节点设 Checkpoint。
- 每个任务引用具体需求条款（`_Requirements: X.Y_`）与设计属性（`_属性: P#_`）以便追溯。
- 属性测试（后端 Hypothesis / 前端 fast-check）作为独立子任务，逐条映射 P1–P30，每条属性一个测试、运行 ≥ 100 次迭代，注释标签 `Feature: advanced-query-module, Property N`；用 `*` 标记可选（按约定仍会完成）。
- ACNR 引用不重写：`full_resolve` / `resolve_instance` / `list_sheets` / `list_cells` / `useAcnr` 一律消费其出口，不重写 ACNR 核心（`.kiro/specs/acnr/`）。
- 平台铁律：白名单安全模型保留；asyncpg 用 `= ANY(:codes)` + `list(...)`；router_registry 必注册；service 只 flush 不 commit；迁移用 `DO $$ + information_schema` 幂等，ORM 三层同步；Windows 命令用 `;` 连接。

---

## Tasks

- [x] 1. 数据层与三层一致性（V101 + V102 迁移 + ORM 同步）
  - [x] 1.1 编写 V101 迁移脚本（模板分享列）
    - 在 `backend/migrations/V101.sql` 中用 `DO $$ ... information_schema.columns` 检测列存在性后 `ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS shared_project_ids UUID[] NOT NULL DEFAULT '{}'`
    - 列存在性检测通过后再 `CREATE INDEX IF NOT EXISTS idx_cqt_shared_projects ON custom_query_templates USING gin (shared_project_ids)`
    - 确保重复运行幂等，不裸 `CREATE INDEX` 于列不确定表
    - _Requirements: 13.3_
  - [x] 1.2 编写 V102 迁移脚本（回写 addr_id 身份表）
    - 在 `backend/migrations/V102.sql` 中 `CREATE TABLE IF NOT EXISTS advanced_query_writeback`（id/project_id/addr_id/wp_id/old_value/new_value/operator_id/result/created_at，见 design Data Models §2）
    - 在表存在后 `CREATE INDEX IF NOT EXISTS idx_aqw_addr_id` 与 `idx_aqw_project`（project_id, created_at DESC）
    - 全部 `DO $$ + information_schema` 幂等守护
    - _Requirements: 3.1, 14.3_
  - [x] 1.3 同步 ORM 模型
    - 在 `backend/app/models/custom_query_models.py:CustomQueryTemplate` 补 `shared_project_ids: Mapped[list[uuid.UUID]]` 声明，字段与 V101 逐列对齐
    - 新增 `AdvancedQueryWriteback` ORM 模型，字段与 V102 表结构逐列对齐
    - _Requirements: 3.1, 13.3_
  - [x]* 1.4 编写迁移幂等 + ORM 一致性测试
    - 断言 `custom_query_templates.shared_project_ids` 列与 `advanced_query_writeback` 表建成；重复执行迁移不报错（防 schema 漂移）
    - 断言 ORM 声明列与 DDL 列集合一致
    - _Requirements: 3.1, 13.3_

- [x] 2. AddressingService（统一寻址，替换 per-URI-prefix 逻辑）
  - [x] 2.1 实现 ResolvedTarget + resolve_target / resolve_many
    - 在 `backend/app/services/custom_query/addressing_service.py`（新增）定义 `ResolvedTarget` dataclass 与 `AddressingService`
    - `resolve_target` 内 `asyncio.wait_for(full_resolve(uri=/formula_ref=/addr_id=/index_ref=, project_id=, db=), timeout=5.0)`；`found=True` 采用 `ResolveResult.addr_id` 作 canonical 身份并附 `wp_id`；超时 → `error="resolve_unavailable"`
    - `resolve_many` 用 `asyncio.gather` 并发解析；封装 ACNR 出口不重写
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 3.5, 4.2, 4.4_
    - _属性: P1_
  - [x] 2.2 归一 URI 语法糖并归集不可解析清单
    - 将 `report:` / `note:` / `adj:` / `tb:` 用户输入语法糖在入口归一为 ACNR 输入形态，解析逻辑单点收敛（替换 `custom_query.py` 各前缀分支与 `module_cell_resolver.resolve`）
    - `resolve_many` 中任一 `found=False` → 逐项归集无法解析清单、整体不执行、不返回部分结果（`TARGET_UNRESOLVABLE`，含 `unresolved: [...]`）
    - _Requirements: 1.4, 1.6_
  - [x]* 2.3 编写属性测试 P1（通用寻址覆盖）
    - **Property 1: 通用寻址覆盖**
    - **Validates: Requirements 1.1, 1.2**
    - Hypothesis：随机 catalog 五域 sheet/cell 条目生成器，断言均解析为非空 addr_id 且不被固定白名单拒绝
    - _属性: P1_
  - [x]* 2.4 编写属性测试 P2（addr_id 身份对齐与确定性）
    - **Property 2: addr_id 身份对齐与确定性**
    - **Validates: Requirements 2.5, 3.1, 3.2, 3.3**
    - Hypothesis：随机物理格，断言选字段树 / 回写 / `WP()` 三路径解析结果逐字符相同且多次重复恒定
    - _属性: P2_
  - [x]* 2.5 编写属性测试 P3（addr_id 改名不变性）
    - **Property 3: addr_id 改名不变性**
    - **Validates: Requirements 2.6**
    - Hypothesis：sheet 别名/改名扰动生成器，断言 addr_id 与定位结果不变
    - _属性: P3_
  - [x]* 2.6 编写属性测试 P4（不可解析目标全有或全无）
    - **Property 4: 不可解析目标全有或全无**
    - **Validates: Requirements 1.4**
    - Hypothesis：含至少一个不可解析目标的集合，断言不执行、无部分结果、逐项列出全部无法解析标识
    - _属性: P4_

- [x] 3. CrossSheetTraceOrchestrator（异步陷阱处理）
  > **跨 spec 协调**：`cross_sheet_resolver.py` 以本方案（同步纯 BFS + async orchestrator）为准，取代 acnr-consumer-wiring task 1.1「BFS 内直调 async full_resolve」。实现前确认该文件未被 acnr-consumer-wiring 按原样改动；若已改，回退为同步纯函数再叠加 orchestrator。
  - [x] 3.1 保留 CrossSheetResolver 同步 BFS 纯函数
    - 确认 `backend/app/services/custom_query/cross_sheet_resolver.py::CrossSheetResolver.resolve` 仅做公式字符串 BFS（`parse_cross_sheet_refs` + snapshot cell 提取 + 环检测/深度截断），不触碰 ACNR、不引入 async
    - 抽离为可 PBT 的纯逻辑，禁止内部 `run_in_executor` 反向调用异步 resolve
    - _Requirements: 4.2, 4.4_
  - [x] 3.2 新增 async CrossSheetTraceOrchestrator.trace
    - 在新增 orchestrator 中：先同步 `chain = resolver.resolve(...)`（无 IO），再 `await asyncio.gather(*[full_resolve(...) for node in chain])` 批量为链节点解析 addr_id + jump_route，合并回链
    - 异步 IO 全部上浮到 orchestrator（router 层 await），显式规避同步上下文内 `await`/`asyncio.run`
    - _Requirements: 1.6, 4.2, 4.4_
  - [x]* 3.3 编写异步陷阱回归测试
    - 单元测试：同步 BFS 纯函数 + async full_resolve 并发编排，断言不在同步上下文内 `await`/`asyncio.run`（防回归 async pitfall）
    - _Requirements: 1.6, 4.2_

- [x] 4. Checkpoint - 统一寻址与异步编排就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. OwnershipGuard（防 IDOR，P0 缺口修复）
  - [x] 5.1 实现 OwnershipGuard 准入守卫
    - 在 `backend/app/services/custom_query/ownership_guard.py`（新增）实现 `assert_target_accessible` / `filter_accessible_rows` / `assert_all_targets`
    - 复用 `deps.require_project_access`（project_users + RLS + Redis 缓存）并补 `project_assignments` 有效分派校验（列名 `staff_id`）；校验在任何数据读写之前执行，不通过 → 403 且不触达数据层
    - 跨 sheet 回写逐 cell 校验目标 project_id 归属，任一不通过整事务回滚；跨项目聚合仅留可访问行；越权尝试记审计（用户/目标 project_id/操作类型）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 4.7_
  - [x]* 5.2 编写属性测试 P15（归属过滤完整性与跨项目拒绝）
    - **Property 15: 归属过滤完整性与跨项目拒绝**
    - **Validates: Requirements 4.7, 9.2, 9.6, 13.5**
    - Hypothesis：随机 project_id 全集 + 可访问子集，断言返回行 project_id 全属可访问集合、不遗漏可访问行、越权目标 403 且不泄露内容
    - _属性: P15_
  - [x]* 5.3 编写属性测试 P16（归属校验单点强制）
    - **Property 16: 归属校验单点强制**
    - **Validates: Requirements 9.5**
    - Hypothesis/契约：注册/覆盖/回写端点在通过 Ownership_Check 前不触达数据读写层，无绕过路径
    - _属性: P16_

- [x] 6. ParamSQLBuilder（参数化 SQL + 白名单）
  - [x] 6.1 实现参数化绑定 + ANY 集合 + 空集合
    - 在 `backend/app/services/custom_query/param_sql_builder.py`（复用/迁移 `query_builder.py` 逻辑）用 SQLAlchemy core + bindparam 构造 SQL，用户值在最终 SQL 文本出现 0 次，SQL 元字符按字面参数绑定
    - IN 集合用 `= ANY(:codes)` + `list(...)`（asyncpg 不支持 IN tuple）；空集合返回空结果不报错
    - 保留既有 `NotImplementedError` 优雅降级分支（`_coerce_value` 类型不支持时原值传回），不改为抛错
    - _Requirements: 10.1, 10.2, 10.3_
  - [x] 6.2 强制白名单登记 + 敏感表排除
    - 强制 `TABLE_WHITELIST`(16) / `JOIN_WHITELIST` / `OPERATOR_WHITELIST` / `AGGREGATE_WHITELIST`；未登记表/JOIN/操作符执行前拒绝、指明对象、不部分执行（`NOT_WHITELISTED`）
    - 显式排除 user/role/auth/token 敏感表；运行时计划引用敏感表无条件拒绝（`SENSITIVE_TABLE_DENIED`）
    - _Requirements: 10.4, 10.5, 10.6, 10.7_
  - [x]* 6.3 编写属性测试 P17（参数化 SQL 注入安全）
    - **Property 17: 参数化 SQL 注入安全**
    - **Validates: Requirements 10.1, 10.2**
    - Hypothesis：注入负载生成器（`'; DROP TABLE`、`--`、`" OR 1=1`、Unicode 引号），断言原始值在编译 SQL 文本出现 0 次、均作字面参数绑定
    - _属性: P17_
  - [x]* 6.4 编写属性测试 P18（IN 集合形态与空集合）
    - **Property 18: IN 集合形态与空集合**
    - **Validates: Requirements 10.3**
    - Hypothesis：随机集合含空集合边界，断言使用 `= ANY(:codes)` + `list(...)`、空集合返回空结果不抛错
    - _属性: P18_
  - [x]* 6.5 编写属性测试 P19（白名单强制）
    - **Property 19: 白名单强制**
    - **Validates: Requirements 10.4, 10.5**
    - Hypothesis：引用未登记表/JOIN/操作符的请求，断言执行前拒绝、指明对象、无数据行、不部分执行
    - _属性: P19_
  - [x]* 6.6 编写属性测试 P20（敏感表排除）
    - **Property 20: 敏感表排除**
    - **Validates: Requirements 10.6, 10.7**
    - Hypothesis：经登记路径或运行时计划引用 user/role/auth/token，断言无条件拒绝 + 描述性错误
    - _属性: P20_

- [x] 7. Checkpoint - 准入与 SQL 安全就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. QueryOrchestrator + ColumnMeta（查询编排）
  - [x] 8.1 实现 execute 编排链与结果契约
    - 在 `backend/app/services/custom_query/query_orchestrator.py`（新增）定义 `QueryRequest` / `QueryResult` 并实现 `execute`：`Ownership_Check → resolve → cache → (sql | cell-fetch) → group → pivot → serialize`
    - 统一编排业务视图与白名单两入口；service 只 flush 不 commit
    - _Requirements: 1.6, 9.5, 11.1, 11.2_
  - [x] 8.2 实现 ColumnMeta 与 addr_id 挂载
    - 定义 `ColumnMeta{key, title, addr_id, drillable, dtype}`；单一可解析源格产生的列挂载 addr_id 且 `drillable=True`，多源/无源列不挂 addr_id、渲染为不可下钻普通文本列
    - _Requirements: 4.1, 4.5_
  - [x]* 8.3 编写编排链单元测试
    - 示例测试：两入口编排链顺序、明细结果集（无维度，R5.7）、cache_hit/warnings 字段
    - _Requirements: 5.7_

- [x] 9. GroupingEngine（多维度分组）
  - [x] 9.1 实现 group 分组聚合 + 校验
    - 在 `backend/app/services/custom_query/grouping_engine.py`（新增）实现 0–10 维度分组聚合，按维度组合升序排序；白名单入口走 `AGGREGATE_WHITELIST`，业务视图入口 Python 层分组
    - 维度无效/超 10 → `INVALID_GROUP_DIM`（含 `invalid`）、保留条件、不执行；非数值列施加 sum/avg/min/max → `AGG_TYPE_MISMATCH`（含 field, agg）、保留条件、不执行；无维度 → 明细结果集
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [x]* 9.2 编写属性测试 P6（分组正确性与升序排序）
    - **Property 6: 分组正确性与升序排序**
    - **Validates: Requirements 5.2, 5.3**
    - Hypothesis：随机行集 + 1–10 维度，断言分组行数等于唯一组合数、结果按维度组合升序
    - _属性: P6_
  - [x]* 9.3 编写属性测试 P7（聚合值与参考实现一致）
    - **Property 7: 聚合值与参考实现一致**
    - **Validates: Requirements 5.4, 6.1, 6.7**
    - Hypothesis：随机数值集合 + 五聚合，断言等于朴素参考实现（分组与透视共用）；透视无源值交叉置空值而非 0
    - _属性: P7_
  - [x]* 9.4 编写属性测试 P8（分组维度校验）
    - **Property 8: 分组维度校验**
    - **Validates: Requirements 5.1, 5.5**
    - Hypothesis：含无效/超限维度，断言描述性错误标明无效/超限维度、保留条件、不执行
    - _属性: P8_
  - [x]* 9.5 编写属性测试 P9（非数值聚合拒绝）
    - **Property 9: 非数值聚合拒绝**
    - **Validates: Requirements 5.6**
    - Hypothesis：非数值字段 + sum/avg/max/min，断言描述性错误标明不兼容字段与聚合、保留条件、不执行
    - _属性: P9_

- [x] 10. PivotEngine（转置/透视）
  - [x] 10.1 实现 transpose 对称纯函数
    - 在 `backend/app/services/custom_query/pivot_engine.py`（新增）实现整表行列互换 `transpose(grid)` 为对称纯函数（单元格值、行/列标签、行列顺序）
    - _Requirements: 6.2, 6.3_
  - [x] 10.2 实现 pivot + 列基数上限 + addr_id 保留
    - 实现 `pivot(rows, cfg, max_cols=512)`：交叉单元格单一源格产生 → 携带 addr_id；多源聚合 → 不携带 addr_id、不可下钻；空组合 → 空值（非 0、非报错）
    - 列数 > 上限 → `PIVOT_COL_LIMIT`（含 actual, limit）、不执行、不返回部分结果
    - _Requirements: 6.1, 6.4, 6.5, 6.6, 6.7_
  - [x]* 10.3 编写属性测试 P5（结果/透视单元格 addr_id ⇔ 单一源格）
    - **Property 5: 结果/透视单元格 addr_id ⇔ 单一源格**
    - **Validates: Requirements 4.1, 4.5, 6.5, 6.6**
    - Hypothesis：随机源格组合，断言携带 addr_id 当且仅当值由单一可解析源格产生
    - _属性: P5_
  - [x]* 10.4 编写属性测试 P11（透视列基数上限）
    - **Property 11: 透视列基数上限**
    - **Validates: Requirements 6.4**
    - Hypothesis：随机列维度基数，断言超上限时描述性错误标明实际列数与上限、不执行、不修改数据、无部分结果
    - _属性: P11_

- [x] 11. Checkpoint - 查询编排与分组透视就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. QueryCache（短 TTL Redis 缓存）
  - [x] 12.1 实现 cache_key + get_or_compute + single-flight + Redis 降级
    - 在 `backend/app/services/custom_query/query_cache.py`（新增）实现缓存键 `aqm:cache:{sha256(canonical_query_def)}:{project_id}:{accessible_scope_sig}`，TTL 默认 30s（5–300 可配）
    - 命中未过期直接返回（≤50ms）；TTL 到期失效重建；可缓存判定：重复次数 ≥ 阈值（默认 5，范围 1–1000）才写缓存
    - single-flight：`SET NX PX` 分布式锁 + 本地 `asyncio.Lock` 兜底，同键并发仅一次 DB 查询；Redis 不可用 → 降级直查 + 记告警、不对调用方报错（复用 `audit_logger` Redis ping 降级范式）
    - _Requirements: 12.1, 12.2, 12.4, 12.5, 12.6, 12.7_
  - [x]* 12.2 编写属性测试 P22（缓存命中一致性）
    - **Property 22: 缓存命中一致性**
    - **Validates: Requirements 12.3**
    - Hypothesis：同 TTL 窗口内，断言缓存命中结果与直查 DB 结果一致
    - _属性: P22_
  - [x]* 12.3 编写属性测试 P23（缓存隔离）
    - **Property 23: 缓存隔离**
    - **Validates: Requirements 12.5**
    - Hypothesis：相同查询定义不同 project_id / 可访问范围，断言缓存键互不相同、不复用
    - _属性: P23_
  - [x]* 12.4 编写属性测试 P24（缓存击穿 single-flight）
    - **Property 24: 缓存击穿 single-flight**
    - **Validates: Requirements 12.6**
    - Hypothesis：`asyncio.gather` N 路同键并发 + mock DB compute 计数，断言 DB 恰查一次、其余复用、返回相同结果
    - _属性: P24_

- [x] 13. ExportService（导出 + 流式）
  - [x] 13.1 实现非流式 export_xlsx
    - 在 `backend/app/services/custom_query/export_service.py`（新增，复用 `query_builder` 的 `Workbook(write_only=True)` + `WriteOnlyCell` + `fetchmany`）保留列标题/顺序/分组透视结构/显示值，与界面一致；含数据来源标识列（addr_id + `semantic_label`）
    - 0 行 → 仅标题行 + 空提示；> 1,048,576 行或 > 16,384 列 → `EXPORT_CAPACITY`、不返回文件
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6_
  - [x] 13.2 实现 RFC 5987 文件名编码
    - `build_content_disposition(display_name)`：`filename="query.xlsx"; filename*=UTF-8''{quote(name)}`（修复当前未编码），中文安全（StreamingResponse 中文文件名铁律）
    - _Requirements: 7.3_
  - [x] 13.3 实现流式导出 stream_xlsx
    - 流式仅适用于**明细/未透视**的平铺结果集：行数 > 阈值（默认 5000，可配）→ `StreamingResponse` 生成器分块（默认 1000 行/块）；单次驻留 ≤ 配置上限（默认 1000 行）
    - 分组/透视结果为**物化导出**（非流式，受 PivotEngine 512 列 / 行上限约束，已在内存成型）；ExportService 按结果形态自动择路（透视→物化 export_xlsx，平铺大集→stream_xlsx）
    - > 1,000,000 行 → `EXPORT_ROW_HARD_LIMIT`、不启动导出；中途错误 → 生成器 `raise` 中断 + `X-Export-Incomplete: 1`，不产生可误认为完整的文件
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 7.7_
  - [x]* 13.4 编写属性测试 P12（导出结构与显示值 round-trip）
    - **Property 12: 导出结构与显示值 round-trip**
    - **Validates: Requirements 7.2**
    - Hypothesis：随机结果网格（含分组/透视形态、Unicode 标签），导出 .xlsx 再读回，断言列标题/顺序/行列结构/显示值一致
    - _属性: P12_
  - [x]* 13.5 编写属性测试 P13（RFC 5987 文件名编码）
    - **Property 13: RFC 5987 文件名编码**
    - **Validates: Requirements 7.3**
    - Hypothesis：含中文/非 ASCII 显示名，断言 `Content-Disposition` 含 `filename*=UTF-8''` 且可解码还原
    - _属性: P13_
  - [x]* 13.6 编写属性测试 P14（流式与非流式导出一致）
    - **Property 14: 流式与非流式导出一致**
    - **Validates: Requirements 8.5**
    - Hypothesis（model-based）：随机结果集，断言流式行内容序列与非流式一致
    - _属性: P14_

- [x] 14. TemplateService（模板/分享/引用）
  - [x] 14.1 实现模板保存与分享
    - 在 `backend/app/services/custom_query/template_service.py`（新增/迁移）持久化到 `custom_query_templates`；名称 1–200、scope ∈ {global, personal, team, public}；非法 → `TEMPLATE_INVALID`、不建部分记录
    - `global/public` 全员可见；`personal` + 显式分享 → 写 `shared_project_ids`，仅对有访问权的项目组成员可见可执行
    - _Requirements: 13.1, 13.2, 13.3_
  - [x] 14.2 实现可见性规则 + 执行 + 失效引用降级
    - 无分享/访问权 → `TEMPLATE_FORBIDDEN`(403)；执行按当前用户可访问范围套 Ownership_Check 仅返回有权行
    - 失效 addr_id → 跳过该引用、结果标注失效项并保留其 addr_id、返回其余有效结果（非整体失败）
    - _Requirements: 13.4, 13.5, 13.6, 13.7_
  - [x]* 14.3 编写属性测试 P25（模板保存校验）
    - **Property 25: 模板保存校验**
    - **Validates: Requirements 13.2**
    - Hypothesis：非法名称（空/超 200）或非法 scope，断言描述性错误 + 不建部分记录
    - _属性: P25_
  - [x]* 14.4 编写属性测试 P26（模板可见性规则）
    - **Property 26: 模板可见性规则**
    - **Validates: Requirements 13.3, 13.4**
    - Hypothesis：随机 scope + 分享集合 + 可访问集合，断言可见可执行当且仅当规则成立、否则 403
    - _属性: P26_
  - [x]* 14.5 编写属性测试 P27（模板失效引用部分降级）
    - **Property 27: 模板失效引用部分降级**
    - **Validates: Requirements 13.7**
    - Hypothesis：含 k 个失效 addr_id，断言跳过失效、标注并保留 addr_id、返回其余有效结果
    - _属性: P27_

- [x] 15. WritebackPreview + SnapshotWriter（回写预览与审计 + addr_id 身份）
  - [x] 15.1 实现回写预览生成
    - 在 `backend/app/services/custom_query/writeback_preview.py`（新增）实现 5s 内返回 `WritebackPreview{items[≤10000]{addr_id, old_value, new_value}}`；空预览 → 提示无可回写、不进入确认
    - _Requirements: 14.1, 14.6_
  - [x] 15.2 实现确认窗口 + 乐观锁 stale 校验
    - 默认 600s 确认窗口；确认时校验预览未过期且目标 cell 旧值与预览一致，否则 `WRITEBACK_CONFLICT`(409)、数据不变、提示重新预览
    - _Requirements: 14.2, 14.7_
  - [x] 15.3 SnapshotWriter addr_id 身份升级 + 11 步事务 + 无审计不回写
    - 在 `backend/app/services/custom_query/snapshot_writer.py` 写回前经 `full_resolve` 解析目标为 `{wp_code}/{sheet_code}/{coordinate_key}` 并以此为回写身份存储（落 `advanced_query_writeback`），取代裸 `(wp_id, sheet_name, cell_ref)`
    - 无法解析 → 中止、不改数据、`TARGET_UNRESOLVABLE`；resolve 不可用/5s 无响应 → 中止、数据不变、`RESOLVE_UNAVAILABLE`；11 步事务原子性保持
    - 把 `log_action` 纳入回写事务成功判定：审计写入失败 → 回滚回写改动（`AUDIT_WRITE_FAILED`）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 14.5, 14.8_
  - [x] 15.4 实现审计节流策略
    - 回写与跨 sheet 溯源逐次记录（不节流），记录操作者/UTC 秒级时间戳/操作类型/目标 addr_id 集合/新旧值/结果；查询执行按 60s 窗口节流为 1 条（`audit_throttle.should_record`）
    - _Requirements: 14.3, 14.4_
  - [x]* 15.5 编写属性测试 P28（审计节流策略）
    - **Property 28: 审计节流策略**
    - **Validates: Requirements 14.4**
    - Hypothesis：随机操作序列，断言每次回写/溯源恰一条、同 60s 窗口内多次查询聚合为恰一条
    - _属性: P28_
  - [x]* 15.6 编写属性测试 P29（回写乐观锁 stale 拒绝）
    - **Property 29: 回写乐观锁 stale 拒绝**
    - **Validates: Requirements 14.7**
    - Hypothesis：预览后确认前旧值被改动或预览过期，断言拒绝回写、数据不变、提示重新预览
    - _属性: P29_
  - [x]* 15.7 编写属性测试 P30（回写事务原子性）
    - **Property 30: 回写事务原子性**
    - **Validates: Requirements 3.6, 9.4, 14.8**
    - Hypothesis：11 步中随机某步注入异常（含归属校验/数据步/审计写入失败），断言全回滚、无部分写入（无审计不回写）
    - _属性: P30_

- [x] 16. 路由注册与权限门禁
  - [x] 16.1 端点注册 + OwnershipGuard 依赖注入 + 角色门禁
    - 在 `custom_query.py` / `query_builder.py` 端点统一注入 `OwnershipGuard` 为依赖（注册/覆盖/回写全路径单点）；`router_registry` 必注册
    - Business_View_Query 对所有已认证角色开放；Whitelist_Query_Builder 仅 admin/manager（`ROLE_FORBIDDEN` 403）；未认证 → `UNAUTHENTICATED` 401
    - _Requirements: 9.5, 11.1, 11.2, 11.3, 11.4_
  - [x]* 16.2 编写属性测试 P21（两入口角色门禁）
    - **Property 21: 两入口角色门禁**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4**
    - Hypothesis：随机角色，断言构建器成立当且仅当角色 ∈ {admin, manager}、业务视图对所有已认证角色开放、未认证 401
    - _属性: P21_

- [x] 17. Checkpoint - 后端全链路就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. 前端（Field_Picker_Tree + 结果下钻 + 客户端转置）
  > **跨 spec 协调**：本组归属高级查询选字段树（满足 acnr-consumer-wiring Req 8）。实现前先检查 `audit-platform/frontend/src/components/custom-query/CustomQueryFieldPicker.vue` 是否已由 acnr-consumer-wiring P4 创建——若存在则直接复用该组件（挂载到 CustomQuery.vue/AdvancedQueryBuilder.vue），不重建；若不存在则在此实现。
  - [x] 18.1 Field_Picker_Tree 复用 useAcnr
    - 在 `audit-platform/frontend/src/views/CustomQuery.vue` 与 `AdvancedQueryBuilder.vue` 复用 `useAcnr` 的 `buildAddressTree`/`loadCellNodes`/`listSheets`（不自建下拉）；选中 cell 节点记录 `node.addrId` 作查询字段标识
    - 域内登记数为 0 → 隐藏该分组节点 + 空态提示；`list_sheets`/`list_cells` 失败或 10s 无响应（`AbortController`）→ 加载失败提示 + 保留已选 + 重载入口
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 1.7, 1.8, 2.7_
  - [x] 18.2 结果列 GtIndexChip 下钻
    - 结果列 `drillable` 为真 → 渲染 `GtIndexChip(value=addr_id)`，点击经 `resolveIndex` 拿 jump_route 跳转、保持当前查询结果视图不变；无 addr_id → 普通文本列
    - jump_route 已失效 → 提示目标已失效、视图不变；下钻目标 project_id 越权 → 403、不泄露内容
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
  - [x] 18.3 Capability_Guidance + 构建器禁用态
    - 展示"业务视图（所有角色）"与"高级构建器（admin/manager）"能力差异说明；角色不足时构建器入口显示为禁用（可见不可点）+ 原因提示
    - _Requirements: 11.5, 11.6_
  - [x] 18.4 客户端整表转置纯函数
    - 实现前端纯函数整表行列互换（预览态，行列 ≤ 200×200），对称实现供 fast-check round-trip 测试
    - _Requirements: 6.2, 6.3_
  - [x]* 18.5 编写属性测试 P10（转置 round-trip，fast-check）
    - **Property 10: 转置 round-trip**
    - **Validates: Requirements 6.2, 6.3**
    - fast-check：随机结果网格（含 Unicode 标签、空值），断言 `transpose(transpose(R)) === R`（单元格值、行/列标签、行列顺序完全一致）
    - _属性: P10_
  - [x]* 18.6 编写前端 Vitest 单元测试
    - 字段树复用 useAcnr（R2）、`GtIndexChip(value)` 渲染与 `resolveIndex` 跳转（R4）、构建器禁用态（R11.6）
    - _Requirements: 2.3, 4.3, 11.6_

- [x] 19. Final Checkpoint - 全部单元/属性测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. 端到端验证（Playwright，平台铁律）
  - [x] 20.1 编写 Playwright 端到端测试脚本
    - 编写覆盖业务视图/构建器两入口全链路的 Playwright 测试：选字段 → 查询 → 分组 → 透视 → 导出 → 下钻 → 回写预览确认，断言中文场景全链路不崩
    - _Requirements: 2.1, 4.2, 5.2, 6.1, 7.1, 14.1, 14.2_

## Notes

- 标记 `*` 的子任务为可选（属性测试/单元测试/集成测试），按用户约定仍会全部完成，保留 `*` 供 UI 区分。
- 顶层任务（无小数编号）与 Checkpoint 不做 `*` 标记，且不纳入依赖图。
- 每个任务引用具体需求条款与设计属性（`_属性: P#_`）以便追溯；30 条属性逐条一个测试、≥100 次迭代、标签 `Feature: advanced-query-module, Property N`。
- 后端属性测试用 Hypothesis（`.hypothesis/` 已存在，`max_examples ≥ 100`）；前端客户端转置纯函数用 fast-check（P10）。
- 三层一致性：迁移（V101/V102）+ ORM（custom_query_models.py）+ service 同步；ACNR 出口引用不重写。
- 每组末尾/关键节点设 Checkpoint 做增量验证。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1", "5.1", "6.1", "12.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "6.2", "8.1", "9.1", "10.1", "13.1", "14.1"] },
    { "id": 3, "tasks": ["8.2", "10.2", "13.2", "14.2", "15.1"] },
    { "id": 4, "tasks": ["13.3", "15.2", "15.3", "15.4", "16.1", "18.1", "18.2", "18.3", "18.4"] },
    { "id": 5, "tasks": ["1.4", "2.3", "2.4", "2.5", "2.6", "3.3", "5.2", "5.3", "6.3", "6.4", "6.5", "6.6", "8.3", "9.2", "9.3", "9.4", "9.5", "10.3", "10.4", "12.2", "12.3", "12.4"] },
    { "id": 6, "tasks": ["13.4", "13.5", "13.6", "14.3", "14.4", "14.5", "15.5", "15.6", "15.7", "16.2", "18.5", "18.6"] },
    { "id": 7, "tasks": ["20.1"] }
  ]
}
```
