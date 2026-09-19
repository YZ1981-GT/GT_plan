# Design Document — 高级查询模块（Advanced Query Module）

## Overview

本设计文档定义"高级查询模块"的彻底增强与重构方案，落实 requirements.md 的 14 条需求。核心目标是把当前两套查询入口（业务视图查询 `custom_query.py` + 白名单 DSL 构建器 `query_builder.py`）统一收敛到 **ACNR 单一寻址路径**（`full_resolve` / `resolve_instance`），并在其上叠加多维度分组、行列转置/透视、Excel 导出与流式导出、防 IDOR 权限治理、参数化 SQL、短 TTL 缓存、模板分享与回写预览审计能力。

**设计定位（引用而非重写）**：本模块是 ACNR「四大消费库」之一。所有寻址、命名、跳转均消费 ACNR 已实现的出口，不新建命名/坐标表：

- 解析：`backend/app/services/acnr/resolver.py::full_resolve`（async、kw-only，返回 `ResolveResult`）。
- 实例（wp_id）：`resolver.py::resolve_instance`（async，带 `db` + `project_id`）。
- 目录树：`backend/app/services/acnr/catalog.py::list_sheets / list_cells`（同步，内存 L1 catalog）。
- 前端 SDK：`audit-platform/frontend/src/services/acnr/useAcnr.ts`（`buildAddressTree` / `loadCellNodes` / `resolveIndex`）。

**关键约束与既有实现锚点（已用 codegraph / 文件核查）**：

| 能力 | 现状锚点 | 本设计动作 |
|------|----------|-----------|
| 业务视图 URI 解析 | `custom_query.py`（`report:`/`note:`/`adj:`/`tb:` 各自解析）、`module_cell_resolver.resolve` | 统一走 `full_resolve`（R1.6） |
| 跨 sheet 溯源 | `cross_sheet_resolver.py::CrossSheetResolver.resolve`（**同步 BFS**，读 `parsed_data.univer_snapshot`） | 保留同步公式 BFS，新增 async 编排层调用 `full_resolve` 挂 addr_id（处理 async pitfall，见 §Architecture） |
| 白名单 DSL | `query_builder.py`（`TABLE_WHITELIST` 16 表 / `JOIN_WHITELIST` / `OPERATOR_WHITELIST` / `AGGREGATE_WHITELIST`；`write_only` 导出） | 复用白名单铁律；导出改 StreamingResponse + RFC 5987；`NotImplementedError` 降级分支保留 |
| 回写 | `snapshot_writer.py::SnapshotWriter.write_cell`（乐观锁 + 11 步事务，step 7 `run_in_executor`+openpyxl，step 9 不节流审计） | 身份升级为 addr_id（R3），叠加预览确认窗口（R14） |
| 模板 | `custom_query_models.py::CustomQueryTemplate`（scope=private/team/public/global，**无 project_id 列**） | 新增 project 分享列（V101 迁移，R13） |
| 权限 | `deps.py::require_project_access`（project_users + RLS context + Redis 缓存） | 统一强制到注册/覆盖/回写全路径（R9，修 P0 IDOR 缺口） |
| 审计 | `audit_logger_enhanced.log_action`（async，队列，P95<50ms）；`audit_throttle.should_record` | execute 节流、回写/溯源不节流（R14.4） |
| 迁移版本 | 最高 `V100__formula_management_library.sql` | 本模块从 **V101** 起（避免与公式库 V100 冲突，R9 数据模型） |

**技术栈**：FastAPI + asyncpg + SQLAlchemy（async）+ Redis；Vue 3 + Element Plus。后端 9980 / 前端 3030。

### 与 `acnr-consumer-wiring` spec 的边界与协调（复盘补充，避免重复/冲突）

两个 spec 都触及 `cross_sheet_resolver.py` 与「高级查询选字段树」，必须明确单一归属，防止双实现或相反改法：

| 交叠点 | acnr-consumer-wiring 原计划 | 本 spec 决策（权威） |
|--------|----------------------------|---------------------|
| **CrossSheetResolver** | P1/task 1.1：在**同步 BFS 循环内直接调 async `full_resolve`** | **本 spec 取代之**：`CrossSheetResolver.resolve` 保持同步纯函数（仅公式 BFS），async IO 上浮到 `CrossSheetTraceOrchestrator`（见 §Architecture 异步陷阱处理）。理由：sync BFS 内 `await`/`asyncio.run` 会在运行 loop 抛错，是 memory 已记录的 async pitfall。acnr-consumer-wiring task 1.1 若实施须改用本方案，二者不得同时按各自原样落地。 |
| **高级查询选字段树** | P4/task 7.1：新建 `CustomQueryFieldPicker.vue`（useAcnr.buildAddressTree） | **本 spec 归属**：task 18.1 在 `CustomQuery.vue`/`AdvancedQueryBuilder.vue` 复用 useAcnr。本 spec 的 Field_Picker_Tree 实现即满足 acnr-consumer-wiring Req 8；若 P4 已建 `CustomQueryFieldPicker.vue`，本 spec 直接复用该组件而非重建（择一，不重复）。 |
| **回写身份 / 失效链** | P5–P8：`touch_wp_registry` → canonical `acnr.events.invalidate` 收敛 | 本 spec 只**消费** addr_id 回写身份（R3），失效链收敛仍归 acnr-consumer-wiring；本 spec 回写落 `advanced_query_writeback` 后由既有 orchestrator 触发失效，不重写失效逻辑。 |

**原则**：ACNR 核心与跨消费者失效链归 acnr-consumer-wiring；本 spec 只负责高级查询自身的寻址消费、编排、分组/透视/导出/缓存/回写预览。若两 spec 排期重叠，`cross_sheet_resolver.py` 以本 spec 的 sync-pure + orchestrator 方案为准。

### 内容覆盖白名单 vs 表白名单（R1 与 R10 的正交关系澄清）

R1「不依赖任何预置的固定内容类型白名单」与 R10「TABLE_WHITELIST 表白名单」是**两个正交轴，不矛盾**：

- **R1 面向业务视图查询（cell 级 ACNR 寻址）**：任何在 ACNR catalog 登记的内容都可查，不因"内容类型"被限制——这是**功能覆盖面**。
- **R10 面向白名单构建器（表级原生 SQL DSL）**：`TABLE_WHITELIST` 是**安全控制**，限制原生 SQL 能触达的物理表、显式排除敏感表——这是**攻击面收敛**。
- 二者作用于不同入口：业务视图经 `AddressingService` 走 ACNR，不碰原生表白名单；构建器经 `ParamSQLBuilder` 强制表白名单。用户"查询任意自定义内容"的诉求由业务视图 + ACNR 满足，构建器白名单不因此放开。

---

## Architecture

### 分层与统一寻址路径

本设计的核心是把「按 URI 前缀各自维护解析逻辑」替换为「单一 ACNR 寻址层」。两套入口在寻址层之上共享同一 resolve/权限/缓存/导出管线，仅在「查询构造层」保留差异（业务视图=cell 级寻址查询；白名单构建器=表级 DSL）。

```mermaid
flowchart TB
    subgraph FE[前端 Vue 3]
        CQ[CustomQuery.vue<br/>业务视图入口 · 所有角色]
        AQB[AdvancedQueryBuilder.vue<br/>白名单构建器 · admin/manager]
        FP[Field_Picker_Tree<br/>useAcnr.buildAddressTree/loadCellNodes]
        PIVOT[透视/转置视图 + 结果表]
        CHIP[GtIndexChip value= addr_id]
        CQ --> FP
        AQB --> FP
        CQ --> PIVOT
        AQB --> PIVOT
        PIVOT --> CHIP
    end

    subgraph GATE[准入层 · 统一强制]
        AUTH[认证 401 / 角色 403]
        OWN[Ownership_Check<br/>require_project_access + project_assignments]
    end

    subgraph CORE[查询核心层]
        ROUTER[QueryOrchestrator<br/>业务视图 & 白名单统一编排]
        RESOLVE[AddressingService<br/>→ ACNR full_resolve / resolve_instance]
        SQLB[ParamSQLBuilder<br/>白名单 + bindparam]
        GROUP[GroupingEngine<br/>多维度分组聚合]
        PVT[PivotEngine<br/>转置/透视 · addr_id 保留]
        CACHE[QueryCache<br/>Redis 短 TTL + 击穿保护]
        EXPORT[ExportService<br/>StreamingResponse + openpyxl write_only]
    end

    subgraph WB[回写层]
        PREVIEW[WritebackPreview<br/>新旧值 diff + 确认窗口]
        WRITER[SnapshotWriter.write_cell<br/>addr_id 身份 · 乐观锁 · 11 步事务]
        AUDIT[audit_logger.log_action<br/>回写/溯源不节流]
    end

    subgraph ACNR[ACNR 单一真源 · 引用不重写]
        FR[full_resolve async kw-only]
        RI[resolve_instance wp_id 出口]
        CAT[catalog list_sheets/list_cells]
        JR[jump_route]
    end

    subgraph DB[(PostgreSQL 只读四表 + 模板/审计)]
    end

    FE -->|HTTP| AUTH --> OWN --> ROUTER
    ROUTER --> RESOLVE --> FR
    RESOLVE --> RI
    FP -->|/api/acnr/entries·anchors| CAT
    ROUTER --> SQLB --> DB
    ROUTER --> GROUP --> PVT
    ROUTER --> CACHE
    ROUTER --> EXPORT
    ROUTER --> PREVIEW --> WRITER --> AUDIT
    WRITER --> FR
    CHIP -->|resolveIndex| FR --> JR
    CACHE -.降级.-> DB
```

**满足需求**：R1（统一寻址覆盖）、R2（选字段树复用）、R9（准入统一）、R11（两入口边界）。

### 统一寻址路径决策（替换 per-URI-prefix 逻辑）

`AddressingService.resolve_target(target)` 是唯一寻址入口，替换 `custom_query.py` 中 `report:`/`note:`/`adj:`/`tb:` 各前缀分支与 `module_cell_resolver.resolve`：

1. 归一输入 → 调 `full_resolve(uri=/formula_ref=/addr_id=/index_ref=, project_id=, db=)`。
2. `found=True` → 采用 `ResolveResult.addr_id` 作为 canonical 身份；带 `project_id` 时 `full_resolve` 附 `wp_id`（`_attach_wp_id`）。
3. `found=False` → 归集到无法解析清单（R1.4），不执行查询、不返回部分结果。
4. 五域中 `tb/report/note/aux` 由 `full_resolve` 内部 `_delegate_v1` 委托 V1 返回统一契约；`jump_route` 为 None 时由前端 `useAcnr.resolveIndex` 在带 project context 下补全（R4.4）。

> 业务视图查询保留 `report:`/`note:`/`adj:`/`tb:` 作为**用户输入语法糖**，但语法糖在入口即归一为 ACNR 输入形态，解析逻辑单点收敛（R1.6）。

### 异步陷阱处理（CrossSheetResolver 同步 BFS ↔ async full_resolve）

**问题**：`cross_sheet_resolver.py::CrossSheetResolver.resolve` 是**同步方法**，对 `parsed_data.univer_snapshot` 做 BFS + 环检测；若在其内部直接调用 async `full_resolve` 会在已运行的事件循环中抛错（不能 `asyncio.run`，也不能 `await`）。

**方案（分离纯函数与 IO）**：

- **保留** `CrossSheetResolver.resolve` 为纯同步：仅做公式字符串 BFS（`parse_cross_sheet_refs` + snapshot cell 提取 + 环检测/深度截断），不触碰 ACNR。此层是可 PBT 的纯逻辑。
- **新增** `async CrossSheetTraceOrchestrator.trace(...)`（在 router 层 await）：
  1. `chain = resolver.resolve(parsed_data, sheet, cell)`（同步，无 IO）。
  2. `await asyncio.gather(*[full_resolve(uri=node.uri_as_acnr, project_id=pid, db=db) for node in chain])` 批量为每个链节点解析 addr_id + jump_route（async 并发，单次一致）。
  3. 合并回 `chain`，返回携带 addr_id 的溯源结果。
- **禁止**在同步 BFS 内部 `run_in_executor` 反向调用异步 resolve；异步 IO 全部上浮到 orchestrator。

**满足需求**：R1.6、R4.2、R4.4；显式规避 requirements 溯源标注的"CrossSheetResolver 同步 BFS 调 async full_resolve"陷阱。

---

## Components and Interfaces

### 1. AddressingService（统一寻址）

替换分散的 URI 前缀解析。所有查询目标、回写目标、结果列下钻都经此层。

```python
# backend/app/services/custom_query/addressing_service.py（新增）
@dataclass
class ResolvedTarget:
    raw: str                 # 用户原始输入（report:/note:/tb:/addr_id/uri/formula_ref）
    found: bool
    addr_id: str | None      # canonical {wp_code}/{sheet_code}/{coordinate_key}
    wp_id: str | None        # 带 project_id 时附加
    jump_route: str | None
    entry_type: str | None   # sheet/cell/runtime/tb/report/note/aux
    error: str | None        # "unresolvable" / "resolve_unavailable" / "ambiguous"

class AddressingService:
    async def resolve_target(self, raw: str, *, project_id: str,
                             db: AsyncSession, timeout_s: float = 5.0) -> ResolvedTarget: ...
    async def resolve_many(self, raws: list[str], *, project_id: str,
                           db: AsyncSession) -> list[ResolvedTarget]: ...
```

- `resolve_target` 内 `asyncio.wait_for(full_resolve(...), timeout=5.0)`；超时 → `error="resolve_unavailable"`（R1.5、R3.5）。
- `resolve_many` 用 `asyncio.gather` 并发解析；任一 `found=False` 时上层按 R1.4 归集清单、整体不执行。
- 满足：R1.1–R1.6、R3.1–R3.5、R4.2、R4.4。

### 2. Field_Picker_Tree（选字段树，复用 useAcnr）

前端不新建下拉，直接复用 `useAcnr`：

```typescript
// AdvancedQueryBuilder.vue / CustomQuery.vue 内
const { buildAddressTree, loadCellNodes, listSheets } = useAcnr()
const tree = await buildAddressTree(cycle)      // sheet 层（R2.1，/api/acnr/entries）
const cellNodes = await loadCellNodes(sheetEntry) // 展开时懒加载（R2.2，/api/acnr/anchors）
// 选中 cell 节点 → 记录 node.addrId 作为查询字段标识（R2.4）
```

- 域内 catalog 登记数为 0 的域不渲染并提示（R1.7、R1.8）：`listSheets(cycle)` 返回空 → 该分组节点隐藏 + 空态提示。
- `list_sheets`/`list_cells` 调用失败或 10s 无响应 → 显示加载失败 + 保留已选 + 重载入口（R2.7），复用 useAcnr 内 `try/catch` 返回 `[]` 的降级 + 组件层 10s `AbortController`。
- addr_id 稳定性：sheet 改名由 catalog `sheet_name_aliases` 吸收，addr_id 不变（R2.6）；同物理格 addr_id 与 `WP()` 公式选址逐字符一致（R2.5，同一 catalog cell 条目）。

### 3. QueryOrchestrator（查询编排）

统一编排两入口的执行链：`Ownership_Check → resolve → cache → (sql | cell-fetch) → group → pivot → serialize`。

```python
class QueryOrchestrator:
    async def execute(self, req: QueryRequest, *, user, db) -> QueryResult: ...
    # QueryRequest: entry("business"|"builder"), targets[]/dsl, group_by[],
    #               pivot: PivotConfig|None, project_id, page, page_size
    # QueryResult: columns[ColumnMeta], rows[], total, cache_hit, warnings[]
```

`ColumnMeta`（快照结果列，R4.1）：

```python
@dataclass
class ColumnMeta:
    key: str
    title: str
    addr_id: str | None       # 单一源格产生时携带，供 GtIndexChip 下钻
    drillable: bool           # addr_id is not None
    dtype: str                # number/text/date
```

### 4. GroupingEngine（多维度分组，R5）

- 支持 0–10 个分组维度，每个维度须为有效 addr_id 或结果集存在列（R5.1）；超 10 或无效 → 描述性错误（R5.5）。
- 白名单入口：`GROUP BY` 走 `query_builder._resolve_field_ref` + `AGGREGATE_WHITELIST`（count/sum/avg/min/max，R5.4，已存在）。
- 业务视图入口：DB 取回后在 Python 层按维度组合分组聚合（cell 级数据非单表）。
- 结果按分组维度组合**升序**排序（R5.3）。
- 数值型聚合校验：对非数值列施加 sum/avg/min/max → 描述性错误标注不兼容字段与聚合（R5.6）。
- 无维度 → 明细结果集（R5.7）。

```python
class GroupingEngine:
    def group(self, rows: list[dict], dims: list[str], aggs: list[Agg]) -> GroupResult: ...
    # Agg: {field, func in {sum,count,avg,max,min}, alias}
```

### 5. PivotEngine（转置/透视，R6）

**服务端 vs 客户端决策**：

| 场景 | 位置 | 理由 |
|------|------|------|
| 分组后结果集（行数 ≤ 透视触发阈值，默认 ≤ 5000 且列 ≤ 512） | **服务端** | 保证与导出一致、addr_id 溯源精确、round-trip 可测 |
| 纯明细结果集的整表行列互换（预览态、行列 ≤ 200×200） | **客户端** | 交互即时性；不落导出 |
| 超阈值 | 服务端拒绝 + 提示缩小范围 | 内存与列基数保护 |

- `PivotConfig{row_dims[], col_dims[], value_field, agg}`（R6.1）。
- 列数 > 上限（默认 512，可配置）→ 描述性错误标明实际列数与上限，不执行、不返回部分结果（R6.4）。
- **addr_id 保留**：交叉单元格由单一源格产生 → 携带该源格 addr_id（R6.5）；多源聚合 → 不携带 addr_id、渲染为不可下钻普通文本（R6.6）。
- 空组合交叉格 → 空值（非 0、非报错，R6.7）。
- **round-trip**：`transpose(transpose(R)) == R`（单元格值、行/列标签、行列顺序完全一致，R6.3）；整表转置为对称实现，纯函数，可 PBT。

```python
class PivotEngine:
    def transpose(self, grid: Grid) -> Grid: ...          # 整表行列互换（R6.2/6.3）
    def pivot(self, rows, cfg: PivotConfig, *, max_cols=512) -> Grid: ...  # R6.1/6.4/6.5/6.6/6.7
# Grid: {row_labels[], col_labels[], cells[[Cell]]}; Cell:{value, addr_id|None}
```

### 6. ExportService（导出 + 流式，R7/R8）

复用 `query_builder.export_excel` 既有 `Workbook(write_only=True)` + `WriteOnlyCell` + `fetchmany` 模式，补齐流式与文件名：

- `.xlsx` 导出保留列标题/顺序/分组透视结构/显示值，与界面一致（R7.2）；含数据来源标识列（addr_id + 可读名 `semantic_label`，R7.4）。
- **RFC 5987 文件名**（R7.3，当前 `filename="query_{table}.xlsx"` 未编码需修复）：
  ```python
  from urllib.parse import quote
  fn_ascii = "query.xlsx"
  fn_utf8 = quote(f"高级查询_{label}.xlsx")
  headers = {"Content-Disposition": f"attachment; filename=\"{fn_ascii}\"; filename*=UTF-8''{fn_utf8}"}
  ```
- **流式导出**（R8）：行数 > 阈值（默认 5000，可配置）→ `StreamingResponse` 生成器分块（默认 1000 行/块，R8.1/R8.2）；单次驻留 ≤ 配置上限（默认 1000 行，R8.3）。
- 硬上限：> 1,000,000 行（且 ≤ xlsx 1,048,576）→ 拒绝启动导出，提示缩小范围（R8.4）；> 1,048,576 行或 > 16,384 列 → 容量超限错误（R7.6）。
- 0 行 → 仅标题行文件 + 空提示（R7.5）；中途错误 → 终止传输并标示未完成，不产生可误认为完整的部分文件（R7.7/R8.6，用生成器 `raise` 中断 + `X-Export-Incomplete` trailer/头标记）。
- **一致性**：流式与非流式对同一结果集行内容一致（R8.5，model-based）。

```python
class ExportService:
    async def export_xlsx(self, result: QueryResult) -> bytes: ...             # 非流式（小结果）
    async def stream_xlsx(self, result_iter, columns) -> AsyncIterator[bytes]: ...  # 流式
    def build_content_disposition(self, display_name: str) -> str: ...         # RFC 5987
```

### 7. OwnershipGuard（防 IDOR，R9）

统一准入，任何注册/覆盖/回写路径不得绕过。复用 `deps.require_project_access` 的 project_users + RLS 机制，并补充 `project_assignments` 有效分派校验：

```python
class OwnershipGuard:
    async def assert_target_accessible(self, *, user, project_id, db) -> None: ...  # 403 if not
    async def filter_accessible_rows(self, rows, *, user, db) -> list: ...          # 跨项目聚合仅留可访问行
    async def assert_all_targets(self, targets: list[ResolvedTarget], *, user, db) -> None: ...
```

- 校验在任何数据读写**之前**执行（R9.1/R9.5）；不通过 → 403 且不触达数据层（R9.2）。
- 跨 sheet 回写逐 cell 校验目标底稿 project_id 归属；任一不通过 → 整事务回滚（R9.3/R9.4）。
- 跨项目聚合仅返回可访问项目行，过滤其余（R9.6）。
- 越权尝试记录审计（用户标识 + 目标 project_id + 操作类型，R9.7）。

> **P0 缺口修复**：当前 `custom_query.py` 未一致强制归属校验。本设计将 `OwnershipGuard` 作为 router 依赖注入到全部查询/回写端点，作为单点。

### 8. ParamSQLBuilder（参数化 SQL，R10）

保留 `query_builder.py` 白名单铁律，全部经 SQLAlchemy core + bindparam：

- 用户值（条件值/集合值/字段表标识）在最终 SQL 文本出现 0 次（R10.1）；SQL 元字符按字面参数绑定（R10.2）。
- IN 集合用 `= ANY(:codes)` + `list(...)`；空集合返回空结果不报错（R10.3，asyncpg 不支持 IN tuple）。
- `TABLE_WHITELIST`(16) / `JOIN_WHITELIST` / `OPERATOR_WHITELIST` / `AGGREGATE_WHITELIST` 强制；新增须显式登记（R10.4）；未登记表/JOIN/操作符 → 执行前拒绝、指明对象、不部分执行（R10.5）。
- 显式排除 user/role/auth/token 敏感表；运行时计划若引用敏感表无条件拒绝（R10.6/R10.7）。
- 保留既有 `NotImplementedError` 优雅降级分支（`_coerce_value` 中 `col.type.python_type` 不支持时原值传回），不作为桩。

### 9. QueryCache（短 TTL Redis 缓存，R12）

```python
class QueryCache:
    def cache_key(self, query_def: dict, project_id: str, scope_sig: str) -> str: ...
    async def get_or_compute(self, key, compute: Callable, *, ttl=30, singleflight=True): ...
```

- 缓存键 = `sha256(canonical(query_def)) : project_id : accessible_scope_sig`（R12.1/R12.5，不跨项目/跨权限复用）。
- 命中未过期直接返回，服务端 ≤ 50ms（R12.2）；TTL 到期失效并重建（R12.4）。
- **缓存击穿保护**（R12.6）：single-flight 分布式锁（`SET NX PX` + 本地 `asyncio.Lock` 兜底），同 TTL 窗口内并发相同请求仅一次 DB 查询，其余等待复用。
- **Redis 降级**（R12.7）：不可用 → 直接查库返回正确结果 + 记录告警，不向调用方报错（复用 `audit_logger` 的 Redis ping 降级范式）。
- 可缓存判定：TTL 窗口内重复次数 ≥ 阈值（默认 5，范围 1–1000）才写缓存（R12.1）。

### 10. TemplateService（模板/分享/引用，R13）

- 持久化到 `custom_query_templates`；名称 1–200 字符、scope ∈ {global, personal(=private), team, public}（R13.1）；非法 → 描述性错误、不建部分记录（R13.2）。
- 分享语义（R13.3）：`global/public` 全员可见；`personal` + 显式分享 → 仅对 `shared_project_ids` 有访问权的项目组成员可见可执行（需 V101 新增列，见 Data Models）。
- 无分享/访问权 → 403（R13.4）；执行模板按当前用户可访问范围套 Ownership_Check，仅返回有权行（R13.5）。
- 结果引用到底稿走回写路径，遵循 R14（R13.6）。
- 模板引用已失效 addr_id → 跳过该失效引用、结果标注失效项并保留其 addr_id、返回其余有效结果（R13.7，非整体失败）。

### 11. WritebackPreview + SnapshotWriter（回写预览与审计，R14 + addr_id 身份 R3）

复用 `SnapshotWriter.write_cell`（乐观锁 + 11 步事务，step 7 `run_in_executor`+openpyxl，step 9 不节流审计）：

- **预览**（R14.1）：5s 内返回 `WritebackPreview{items[≤10000]{addr_id, old_value, new_value}}`；空预览 → 提示无可回写、不进入确认（R14.6）。
- **确认窗口**（R14.2）：默认 600s；确认时校验预览未过期且目标 cell 旧值与预览一致，否则拒绝并提示重新预览（R14.7）。
- **addr_id 身份升级**（R3）：写回前经 `full_resolve` 解析目标为 `{wp_code}/{sheet_code}/{coordinate_key}` 并以此为回写身份存储（取代裸 `(wp_id, sheet_name, cell_ref)`，R3.1）；同物理格任意次回写解析为同一 addr_id 且与 `WP()` 公式引用一致（R3.2/R3.3）；无法解析 → 中止、不改数据、描述性错误（R3.4）；resolve 不可用/5s 无响应 → 中止、数据不变、错误（R3.5）；11 步事务原子性保持，任一步失败回滚（R3.6/R14.5）。
- **审计**（R14.3/R14.4）：回写与跨 sheet 溯源逐次记录（不节流），记录操作者/UTC 秒级时间戳/操作类型/目标 addr_id 集合/新旧值/结果；查询执行按 60s 窗口节流为 1 条（`audit_throttle.should_record`）。
- **无审计不回写**（R14.8）：回写成功但审计写入失败 → 回滚回写改动并提示审计失败（把 `log_action` 纳入回写事务成功判定）。

---

## Data Models

### 迁移版本协调

- 现状最高：`V100__formula_management_library.sql`（公式管理库已占用 V100）。
- **本模块从 `V101` 起**，避免与 formula-management-library 冲突。建议顺序：
  - `V101__advanced_query_template_sharing.sql`（模板分享列）
  - `V102__advanced_query_writeback_addr_id.sql`（回写记录 addr_id）
- 迁移遵循平台铁律：`DO $$ + information_schema` 幂等检测列/表存在性再 `ALTER`，禁止裸 `CREATE INDEX` 于列不确定表。

### 1. CustomQueryTemplate 扩展（R13.3 分享）

现表 `custom_query_templates` 无 project 维度分享列。V101 新增：

```sql
-- V101（幂等）
ALTER TABLE custom_query_templates
  ADD COLUMN IF NOT EXISTS shared_project_ids UUID[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_cqt_shared_projects
  ON custom_query_templates USING gin (shared_project_ids);
```

ORM 同步（`custom_query_models.py`）：`shared_project_ids: Mapped[list[uuid.UUID]]`。

`config` JSONB 扩展（无需迁移，schema 演进）新增可选键：

```jsonc
{
  "group_by": ["<addr_id|col>"],          // R5
  "pivot": {                               // R6
    "row_dims": [], "col_dims": [],
    "value_field": "", "agg": "sum",
    "max_cols": 512
  },
  "targets": ["<addr_id|uri|report:|note:|tb:>"]  // R1，统一寻址输入
}
```

### 2. 回写记录 addr_id 身份（R3）

回写落点为 `working_papers.parsed_data.univer_snapshot`（cell 值原地更新，无独立回写表）。为满足「存 addr_id 身份 + 快照列可下钻」，新增回写审计/身份记录表（V102）：

```sql
-- V102（幂等）
CREATE TABLE IF NOT EXISTS advanced_query_writeback (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL,
  addr_id       TEXT NOT NULL,          -- {wp_code}/{sheet_code}/{coordinate_key}（R3.1）
  wp_id         UUID,                   -- resolve_instance 附加
  old_value     JSONB,
  new_value     JSONB,
  operator_id   UUID NOT NULL,
  result        TEXT NOT NULL,          -- success/failed
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_aqw_addr_id ON advanced_query_writeback (addr_id);
CREATE INDEX IF NOT EXISTS idx_aqw_project ON advanced_query_writeback (project_id, created_at DESC);
```

> `addr_id` 是与 `WP()` 公式引用同一身份（R3.2/R3.3），stale chip 追踪据此对齐。审计明细同时经 `audit_logger.log_action`（R14.3）落 audit trail，本表为查询身份与下钻的结构化索引。

### 3. 结果列元数据（运行时，非持久化）

`ColumnMeta{key, title, addr_id, drillable, dtype}` 随 `QueryResult` 返回；`addr_id` 由单一源格产生时挂载（R4.1），前端据 `drillable` 决定渲染 `GtIndexChip(value=addr_id)`（R4.3）或普通文本列（R4.5）。

### 4. 缓存键 schema（运行时，Redis）

```
aqm:cache:{sha256(canonical_query_def)}:{project_id}:{accessible_scope_sig}
```

- `canonical_query_def`：稳定序列化（键排序）的 `{entry, targets|dsl, group_by, pivot, page, page_size}`。
- `accessible_scope_sig`：当前用户可访问项目集合的稳定签名（R12.5 隔离）。
- 值：序列化 `QueryResult`（含 columns/rows/total）；TTL 默认 30s（5–300 可配）。
- single-flight 锁键：`aqm:lock:{同上 hash}`（R12.6）。

### 5. Pivot 配置 schema（运行时/模板持久化）

见上 `config.pivot`；`PivotConfig` dataclass 与 JSON schema 双向映射；`max_cols` 默认 512（R6.4）。

**满足需求**：R3（回写身份）、R4（列元数据下钻）、R5/R6（分组透视 schema）、R12（缓存键）、R13（模板分享列）。

---

## Correctness Properties

*属性（property）是系统在所有有效执行下都应成立的特征或行为——即对"系统应该做什么"的形式化陈述。属性是人类可读规格与机器可验证正确性保证之间的桥梁。*

本模块涉及大量纯逻辑（分组/转置/透视/参数化 SQL 构造/缓存键/身份对齐），非常适合基于属性的测试（PBT）。以下属性经 prework 分析与冗余合并后得出，覆盖所有可属性化的验收标准；UI 渲染、性能上限、故障降级等归为示例/边界测试（见 Testing Strategy）。

### Property 1: 通用寻址覆盖

*For any* ACNR catalog 中已登记的内容条目（五域 tb/report/note/wp/aux 的 sheet 或 cell），`AddressingService.resolve_target` 都应成功解析为非空 canonical addr_id 并纳入可查询字段集，不因内容类型被任何固定白名单拒绝。

**Validates: Requirements 1.1, 1.2**

### Property 2: addr_id 身份对齐与确定性

*For any* 物理格，无论经选字段树、回写路径还是 `WP()` 公式引用解析，得到的 addr_id 都逐字符相同；且对同一格重复多次解析，结果恒定（确定性）。回写以该 addr_id 作为存储身份。

**Validates: Requirements 2.5, 3.1, 3.2, 3.3**

### Property 3: addr_id 改名不变性

*For any* sheet 与任意 sheet 改名/别名变动，该 sheet 及其下单元格的 addr_id 保持不变，且仍能通过稳定 addr_id 定位；已保存的查询字段 addr_id 不因改名失效或改变。

**Validates: Requirements 2.6**

### Property 4: 不可解析目标全有或全无

*For any* 查询目标集合，只要其中存在至少一个无法被 Resolve_Service 解析为有效 addr_id 的目标，系统就不执行查询、不返回任何部分结果，并逐项列出全部无法解析的目标标识。

**Validates: Requirements 1.4**

### Property 5: 结果/透视单元格 addr_id ⇔ 单一源格

*For any* 查询结果列或透视交叉单元格，该单元格携带 addr_id（且可下钻）当且仅当其值恰由单一可解析源格产生；由多个源格聚合或无源格产生的单元格不携带 addr_id 且渲染为不可下钻的普通文本。

**Validates: Requirements 4.1, 4.5, 6.5, 6.6**

### Property 6: 分组正确性与升序排序

*For any* 结果行集与 1–10 个分组维度，分组结果的行数等于维度值唯一组合的数量，且结果行按分组维度组合升序排列。

**Validates: Requirements 5.2, 5.3**

### Property 7: 聚合值与参考实现一致

*For any* 数值型值字段与 sum/count/avg/max/min 聚合方式，无论用于多维度分组还是透视交叉表，聚合结果都等于对同一源值集合的朴素参考实现计算结果；透视中无对应源值的交叉组合置为空值（而非 0）。

**Validates: Requirements 5.4, 6.1, 6.7**

### Property 8: 分组维度校验

*For any* 分组维度集合，若包含无法解析为有效 addr_id/有效列的维度或维度数超过 10，则系统返回描述性错误并标明无效/超限维度，保留原始查询条件不变，且不执行查询。

**Validates: Requirements 5.1, 5.5**

### Property 9: 非数值聚合拒绝

*For any* 非数值型值字段与 sum/avg/max/min 聚合方式的组合，系统返回描述性错误并标明不兼容的字段与聚合方式，保留原始查询条件不变，且不执行查询。

**Validates: Requirements 5.6**

### Property 10: 转置 round-trip

*For any* 查询结果网格，连续转置两次（先转置再转置回来）得到的网格在单元格值、行标签、列标签及行列顺序上与原网格完全一致。

**Validates: Requirements 6.2, 6.3**

### Property 11: 透视列基数上限

*For any* Pivot_Config，若其列维度产生的列数超过配置上限（默认 512），系统返回描述性错误标明实际列数与上限，且不执行透视、不修改数据、不返回任何部分结果。

**Validates: Requirements 6.4**

### Property 12: 导出结构与显示值 round-trip

*For any* 查询结果集（含分组/透视形态），导出为 `.xlsx` 后再读回，其列标题文本、列顺序、行列结构与单元格显示值与导出前的结果视图完全一致。

**Validates: Requirements 7.2**

### Property 13: RFC 5987 文件名编码

*For any* 含非 ASCII 字符（含中文）的导出显示名，响应 `Content-Disposition` 头都包含符合 RFC 5987 的 `filename*=UTF-8''` 编码段，且可被正确解码还原为原显示名。

**Validates: Requirements 7.3**

### Property 14: 流式与非流式导出一致

*For any* 结果集，流式导出产生的行内容序列与非流式导出对同一结果集产生的行内容序列完全一致（model-based 一致性）。

**Validates: Requirements 8.5**

### Property 15: 归属过滤完整性与跨项目拒绝

*For any* 混合多项目的数据行集与任意用户可访问项目集合，查询/模板执行返回的所有行的 project_id 都属于用户可访问集合，且不遗漏任何可访问项目的行；对不属于可访问集合的下钻/访问目标一律拒绝（HTTP 403）且不泄露内容。

**Validates: Requirements 4.7, 9.2, 9.6, 13.5**

### Property 16: 归属校验单点强制

*For any* 查询注册、覆盖、回写端点，请求在通过 Ownership_Check 之前都不触达任何数据读写层；不存在绕过 Ownership_Check 的路径。

**Validates: Requirements 9.5**

### Property 17: 参数化 SQL 注入安全

*For any* 用户提供的输入值（含 SQL 元字符、关键字、引号等注入负载），最终编译发送到数据库的 SQL 文本中该原始值出现 0 次，输入值均作为字面参数经 bindparam 绑定，不被解释为 SQL 语法。

**Validates: Requirements 10.1, 10.2**

### Property 18: IN 集合形态与空集合

*For any* IN 集合条件，查询使用 `= ANY(:codes)` + `list(...)` 形态构造；当集合为空时返回空结果集且不抛出错误。

**Validates: Requirements 10.3**

### Property 19: 白名单强制

*For any* 引用了未登记表、JOIN 或操作符的查询请求，Whitelist_Query_Builder 在执行前拒绝该请求、指明未登记的具体对象、返回描述性错误，且不返回任何数据行、不部分执行。

**Validates: Requirements 10.4, 10.5**

### Property 20: 敏感表排除

*For any* 试图经任何登记路径或运行时查询计划引用 user/role/auth/token 敏感表的查询，系统都无条件拒绝并返回描述性错误。

**Validates: Requirements 10.6, 10.7**

### Property 21: 两入口角色门禁

*For any* 请求角色，Whitelist_Query_Builder 的可访问与执行权限成立当且仅当角色属于 {admin, manager}；Business_View_Query 对所有已认证角色开放；未认证请求对任一入口返回 HTTP 401。

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 22: 缓存命中一致性

*For any* 查询定义，在同一 TTL 窗口内，缓存命中返回的结果与直接查询数据库对同一查询定义得到的结果一致。

**Validates: Requirements 12.3**

### Property 23: 缓存隔离

*For any* 相同查询定义但不同 project_id 或不同用户可访问范围，其缓存键互不相同，且不复用彼此的缓存结果。

**Validates: Requirements 12.5**

### Property 24: 缓存击穿 single-flight

*For any* 一组针对同一缓存键的并发相同请求（缓存缺失/过期时），底层数据库查询恰好被发起一次，其余并发请求复用该次查询结果，且所有并发请求返回相同结果。

**Validates: Requirements 12.6**

### Property 25: 模板保存校验

*For any* 非法模板名称（空/长度超 200）或非法 scope，保存操作返回描述性错误并指明失败原因，且不创建任何部分模板记录。

**Validates: Requirements 13.2**

### Property 26: 模板可见性规则

*For any* 模板 scope、分享项目集合与用户可访问项目集合，模板对用户可见可执行当且仅当：scope 为 global/public，或 scope 为 personal 且模板分享的某 project_id 属于用户有访问权的项目集合；否则对分享/执行返回 HTTP 403。

**Validates: Requirements 13.3, 13.4**

### Property 27: 模板失效引用部分降级

*For any* 引用了 k 个已不可解析 addr_id 的模板执行，系统跳过这 k 个失效引用、在结果中标注失效项并保留其 addr_id、返回其余有效结果，而非整体失败。

**Validates: Requirements 13.7**

### Property 28: 审计节流策略

*For any* 操作序列，每次回写与每次跨 sheet 溯源都产生恰好一条审计记录（不节流）；而同一 60 秒窗口内的多次查询执行聚合为恰好一条节流审计记录。

**Validates: Requirements 14.4**

### Property 29: 回写乐观锁 stale 拒绝

*For any* 在预览之后、确认之前被外部改动（旧值与预览时不一致）或预览已过期的回写确认，系统拒绝执行回写、保持数据不变，并提示需重新预览。

**Validates: Requirements 14.7**

### Property 30: 回写事务原子性

*For any* 回写事务，若其 11 步中任一步失败（含跨 sheet 归属校验失败、数据步失败或审计写入失败），事务回滚至开始前状态，所有目标 cell 均不被修改，不残留部分写入（"无审计不回写"）。

**Validates: Requirements 3.6, 9.4, 14.8**

---

## Error Handling

统一错误契约（复用平台 `ResponseWrapperMiddleware` 的 `{code, message, data}` 信封 + `error_code` 明细，与 `query_builder.py` 既有 `detail={error_code, message, ...}` 一致）：

| 场景 | error_code | HTTP | 数据副作用 | 需求 |
|------|-----------|------|-----------|------|
| 目标无法解析 | `TARGET_UNRESOLVABLE`（含 `unresolved: [...]`） | 400 | 不执行、无部分结果 | 1.4, 3.4 |
| Resolve 不可用/超时 | `RESOLVE_UNAVAILABLE` | 503 | 中止、数据不变 | 1.5, 3.5 |
| 字段树加载失败/超时 | 前端 `field_tree_load_failed`（保留已选 + 重载） | — | 已选不变 | 2.7 |
| 无效分组维度/超 10 | `INVALID_GROUP_DIM`（含 `invalid: [...]`） | 400 | 保留条件、不执行 | 5.5 |
| 非数值聚合 | `AGG_TYPE_MISMATCH`（含 `field`,`agg`） | 400 | 保留条件、不执行 | 5.6 |
| 透视列超上限 | `PIVOT_COL_LIMIT`（含 `actual`,`limit`） | 400 | 不执行、无部分结果 | 6.4 |
| 导出容量超限 | `EXPORT_CAPACITY`（xlsx 上限） | 400 | 不返回文件 | 7.6 |
| 导出硬上限 | `EXPORT_ROW_HARD_LIMIT` | 400 | 不启动导出 | 8.4 |
| 导出/流式中途错误 | `EXPORT_FAILED` + `X-Export-Incomplete: 1` | 500/流中断 | 无可误认为完整的文件 | 7.7, 8.6 |
| 越权访问 | `FORBIDDEN_PROJECT`（403）+ 审计 | 403 | 不读写、记审计 | 9.2, 9.7, 4.7 |
| 未登记表/JOIN/op | `NOT_WHITELISTED`（含对象名） | 400 | 不部分执行 | 10.5 |
| 引用敏感表 | `SENSITIVE_TABLE_DENIED` | 400 | 无条件拒绝 | 10.7 |
| 构建器角色不足 | `ROLE_FORBIDDEN` | 403 | 不加载构建器 | 11.3 |
| 未认证 | `UNAUTHENTICATED` | 401 | 拒绝 | 11.4 |
| Redis 不可用 | 降级直查 + 告警（不对外报错） | 200 | 正确结果 | 12.7 |
| 模板保存非法 | `TEMPLATE_INVALID`（含原因） | 400 | 不建部分记录 | 13.2 |
| 无分享/访问权 | `TEMPLATE_FORBIDDEN` | 403 | 拒绝 | 13.4 |
| 回写冲突（乐观锁/预览过期） | `WRITEBACK_CONFLICT`（`WritebackConflict`） | 409 | 数据不变、提示重新预览 | 14.7 |
| 回写事务失败 | `WRITEBACK_FAILED` + 审计 failed | 500 | 全回滚 | 14.5, 3.6 |
| 审计写入失败 | `AUDIT_WRITE_FAILED`（回滚回写） | 500 | 全回滚（无审计不回写） | 14.8 |

**降级原则**：
- Resolve/Redis/审计等外部依赖故障，遵循平台既有降级范式（`audit_logger` 的 Redis ping + asyncio.Queue 兜底、`require_project_access` 的 Redis 缓存降级直查），但**回写型审计失败不降级**——审计是回写事务成功的必要条件（R14.8）。
- 保留 `query_builder.py` 既有 `NotImplementedError`（`_coerce_value` 中类型不支持时原值传回）作为优雅降级，不改为抛错。

---

## Testing Strategy

### 双轨测试

- **属性测试（PBT）**：验证上述 30 条 Correctness Properties 的普遍正确性。
- **单元/示例测试**：验证具体示例、性能上限、UI 渲染、故障降级等非属性化验收标准。
- **契约测试**：端点归属守卫（R9.5）、白名单登记、ACNR 调用单点（R1.6）。

### 属性测试配置

- 库：Python 后端用 **Hypothesis**（平台既有，`.hypothesis/` 已存在，`max_examples` ≥ 100）；前端纯函数（transpose/pivot 客户端态）用 **fast-check**。不自研 PBT 框架。
- 每条属性用**单个**属性测试实现，运行 ≥ 100 次迭代。
- 每个属性测试注释标签：`Feature: advanced-query-module, Property {number}: {property_text}`。
- 生成器要点：
  - catalog 条目生成器（P1/P2/P3/P5）：随机 `{wp_code}/{sheet_code}/{coordinate_key}` + 别名扰动。
  - 结果网格生成器（P6/P7/P10/P12/P14）：随机维度基数、稀疏度、数值/文本/空值、Unicode 标签。
  - 注入负载生成器（P17）：`'; DROP TABLE`、`--`、`" OR 1=1`、Unicode 引号、`= ANY` 边界（含空集合 P18）。
  - 项目/权限集合生成器（P15/P16/P23/P26）：随机 project_id 全集 + 可访问子集 + scope。
  - 并发生成器（P24）：`asyncio.gather` N 路同键，mock DB compute 计数。
  - 故障步生成器（P30）：随机选择 11 步中某步注入异常。

### 单元 / 集成 / 边界测试（非 PBT）

- **示例**：1.3/1.6/1.7/1.8、2.1–2.4、4.2–4.4、5.7、7.1/7.4、8.1–8.3、9.7、11.5/11.6、12.1/12.2、13.1/13.6、14.1/14.3。
- **边界/故障注入**：1.5、2.7、3.5、4.6、7.5/7.6/7.7、8.4/8.6、12.4/12.7、14.2/14.5/14.6。
- **异步陷阱回归**：针对 `CrossSheetTraceOrchestrator`，测试同步 BFS 纯函数 + async full_resolve 并发编排，断言不在同步上下文内 `await`/`asyncio.run`（防回归 requirements 溯源标注的 async pitfall）。
- **ACNR 消费边界**：`full_resolve`/`resolve_instance`/`list_sheets`/`list_cells` 一律 mock 或走真实 catalog，不重写 ACNR 核心；断言仅消费其出口。
- **迁移测试**：V101/V102 幂等性（重复执行不报错）、ORM 与 DDL 列一致（防 schema 漂移）。

### 前端测试（Vitest + Playwright）

- Vitest：字段树复用 useAcnr（R2）、结果列 `GtIndexChip(value)` 渲染与 `resolveIndex` 跳转（R4）、能力边界禁用态（R11.6）、客户端转置纯函数（R6.2/6.3 fast-check）。
- Playwright 实测（平台铁律）：业务视图/构建器两入口全链路、选字段→查询→分组→透视→导出→下钻→回写预览确认，中文场景不崩。

**满足需求**：R1–R14 全覆盖（属性 30 条 + 示例/边界/契约测试补齐不可属性化项）。
