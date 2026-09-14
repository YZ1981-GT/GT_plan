# Design Document

## Overview

本设计的核心动作是**把已存在的服务层接进生产链路**，而不是新造能力。7 个零引用模块（`query_orchestrator` / `execute_compatibility` / `export_service` / `writeback_preview` / `param_sql_builder` / `template_service` / `template_scope_adapter`）已包含绝大部分逻辑与预算常量，缺的是 router 侧的唯一调用点与三个 dataclass 的字段对齐。

因此设计遵循两条原则：

1. **不新增第二套真源**。项目可见性只走 `OwnershipGuard`；白名单门禁只走 `table_whitelist.enforce_query_plan`；预算阈值只用 `export_service` / `writeback_preview` / `PivotConfig` 已定义的常量；业务默认列集与 `fields` 并列声明在 `table_whitelist` 内。
2. **接线必须可证伪**。每处接线都要有「唯一消费方 + 真实执行」判据，不能靠 grep 符号存在。已入库的 75 + 5 条红测试即为主判据集。

## Architecture

### 现状执行链（两条各自为政）

```
业务视图  POST /api/custom-query/execute
  → get_current_user
  → ownership_guard.assert_target_accessible      ← 唯一接线的守卫
  → limit = min(body.limit, 2000)                 ← 取数层预截断，total 退化
  → compute_cache_key
  → if/elif × 14 内联分发 _query_*                ← adapter 被绕过
  → except Exception → 200 {"error": ...}         ← fail-open

构建器  POST /api/query/execute
  → require_query_builder_access（仅角色）
  → _build_select（私有白名单路径）               ← enforce_query_plan 被绕过
  → 无 project_id 注入 / 无 ORDER BY / 无超时
  → db.execute(stmt)
```

### 目标执行链（单一路径）

```
业务视图  POST /api/custom-query/execute
  → get_current_user
  → ExecuteCompatibilityAdapter.execute           ← 唯一执行路径（恰好 1 次）
      → to_orchestrator_request(legacy_body)
      → QueryOrchestrator.execute
          step1 Ownership_Check（ownership_guard）
          step2 resolve（ACNR 目标，全有或全无）
          step3 cache（键含 project_id + scope_sig）
          step4 fetch ← business_fetcher = 14 个 _query_* 的注册表（未截断取数）
          step5 group（GroupingEngine）
          step6 pivot（PivotEngine）
          step7 paginate（sort + tie-breaker → total → limit/offset）
          step8 serialize（ColumnMeta 含 source）
      → to_legacy_response(QueryResult)
  → 异常分类：HTTPException 原样上抛 / 其余 rollback + 500 + correlation_id

构建器  POST /api/query/execute
  → require_query_builder_access
  → enforce_query_plan（表/JOIN/算子/聚合单一门禁）
  → enforce_join_business_key（拒绝纯 project_id JOIN）
  → enforce_complexity_budget（JOIN 条数/维度/聚合个数）
  → resolve_project_scope（注入 project_id IN (...)）
  → _build_select（默认业务列集，非全字段）
  → with statement_timeout + 取消传播
```

## Components and Interfaces

### 1. `OwnershipGuard` 接线扩展（R1）

`backend/app/routers/custom_query.py` 三个只读端点增加认证与归属校验依赖：

```python
async def get_indicators(
    project_id: str | None = Query(default=None),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),   # 新增
):
    if project_id:
        await ownership_guard.assert_target_accessible(
            user=current_user, project_id=project_id, db=db
        )   # 必须先于任何 _resolve_* / _build_* 调用
```

`wp_id_by_code` / `wp_sheet_preview` 同构，且 `wp_sheet_preview` 的守卫必须位于 `init_workpaper_from_template` 之前。

`project_id` 为 `None` 时走通用降级树（不含项目数据），保持现有行为但仍要求认证。

### 2. 构建器项目作用域（R2）

新增 `backend/app/services/custom_query/builder_scope.py`：

```python
GLOBAL_CONFIG_TABLES: frozenset[str] = frozenset({"report_config"})

@dataclass(frozen=True)
class BuilderScope:
    project_ids: frozenset[UUID] | None   # None = 全项目（admin/partner）
    unscoped_tables: tuple[str, ...]      # 命中的全局配置表
    warnings: tuple[str, ...]

async def resolve_builder_scope(*, user, dsl_tables, requested_project_id, db) -> BuilderScope
def apply_scope_to_select(stmt, *, scope, table_meta, model) -> Select
def scope_signature(scope: BuilderScope) -> str   # 纳入缓存键
```

作用域来源复用 `ownership_guard.get_accessible_project_ids`（已存在的公开出口）。`apply_scope_to_select` 在 WHERE 组装的**最后一步**追加，位置保证用户 DSL 无法覆盖。缓存键把 `scope_signature` 拼入，替代当前写死的 `"__query_builder__"`。

### 3. 三个 dataclass 字段对齐（R3）

`query_orchestrator.py`：

```python
@dataclass
class ColumnMeta:
    key: str
    title: str
    addr_id: Optional[str] = None
    drillable: bool = False
    dtype: str = "text"
    semantic_label: Optional[str] = None
    # 新增：{"manual": bool, "provenance": list, "trace": list}
    # 契约测试以 dict 形态断言（source["manual"] / source["trace"][0]["addr_id"]），
    # 非字符串枚举。adapter 据「有 addr_id 或 source 或 semantic_label」决定该列
    # 下发完整 dict 而非退化为列名字符串。
    source: Optional[dict] = None

@dataclass
class QueryRequest:
    entry: str
    project_id: str
    source: Optional[str] = None        # 新增
    year: Optional[int] = None          # 新增
    filters: dict = field(default_factory=dict)      # 新增
    columns: list[str] = field(default_factory=list) # 新增
    sort: list[dict] = field(default_factory=list)   # 新增
    limit: int = DEFAULT_PAGE_SIZE       # 新增
    offset: int = 0                      # 新增
    targets: list[str] = field(default_factory=list)
    dsl: Optional[dict] = None
    group_by: list[str] = field(default_factory=list)
    aggs: list[Agg] = field(default_factory=list)
    pivot: Optional[PivotConfig] = None

@dataclass
class QueryResult:
    columns: list[ColumnMeta] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    total: int = 0
    limit: int = 0                       # 新增（adapter 已在读）
    offset: int = 0                      # 新增（adapter 已在读）
    cache_hit: bool = False
    warnings: list[str] = field(default_factory=list)
```

`page` / `page_size` 保留为 `limit` / `offset` 的派生视图，避免破坏既有绿测试。`to_payload` / `from_payload` 同步补全新字段，`from_payload` 重建 `ColumnMeta` 时必须带 `source`。

### 4. `business_fetcher` 注册表（R3.7 / R4.8）

新增 `backend/app/services/custom_query/business_fetchers.py`，把 14 个 `_query_*` 从 router 下沉为注册表：

```python
BUSINESS_FETCHERS: dict[str, FetcherFn] = {
    "report": _query_report, "trial_balance": _query_trial_balance, ...
}

SOURCE_PREFIX_ROUTES = (
    ("disclosure_note:", _route_disclosure_note),
    ("consol_unit:", _route_consol_unit),
    ("workpaper:", _route_workpaper),
)

async def business_fetcher(req: QueryRequest, resolved, db) -> tuple[list[dict], list[ColumnMeta]]
```

取数器签名从 `(db, pid, year, filters, limit)` 改为接收 `fetch_limit`（预算上限，非展示 `limit`），保证 `total` 反映真实行数。`fetch_limit` 取 `min(FETCH_HARD_CAP, offset + limit + 1)` 的分页探测形态，或在需要精确 `total` 时走独立 `COUNT` 查询。

### 5. `StablePagination`（R4）

新增 `backend/app/services/custom_query/pagination.py`：

```python
DEFAULT_SORT_BY_SOURCE: dict[str, tuple[str, ...]] = {...}
TIE_BREAKER_BY_SOURCE: dict[str, str] = {...}   # 优先 id，退化为复合唯一键

def resolve_sort(source: str, user_sort: list[dict], available_columns: set[str]) -> list[SortKey]
    # 非法字段/方向 → HTTPException 422 INVALID_SORT_FIELD / INVALID_SORT_DIRECTION
def apply_pagination(rows: list[dict], *, sort: list[SortKey], limit: int, offset: int) -> PagedRows
    # 返回 (page_rows, total)；total 在 group/pivot 之后、切片之前计算
```

编排器 step7 调用顺序固定为 group → pivot → resolve_sort → 排序 → `total = len(rows)` → 切片。

`limit` / `offset` 的 422 校验放在两处：`custom_query.QueryRequest`（pydantic `ge/le`）与编排器入口（防绕过 router 直调）。

### 6. JOIN 业务键校验与复杂度预算（R6）

`table_whitelist.py` 新增：

```python
MAX_JOINS_PER_QUERY = 3
MAX_GROUP_DIMS = 5
MAX_AGGREGATES = 10

def enforce_join_business_key(base: str, target: str, on_pairs: list[tuple[str, str]]) -> None
    # ON 全部为 project_id ↔ project_id → 400 JOIN_MISSING_BUSINESS_KEY

def enforce_complexity_budget(*, joins: int, group_dims: int, aggregates: int) -> None
```

同时移除三处纯 `project_id` 的 JOIN 登记：`trial_balance → wp_index`、`adjustments → wp_index`，以及 `projects → 8 张业务表`。`projects` 的正确用法是作为 JOIN 目标（`disclosure_notes → projects` 已是此形态），而非 base 表向下发散；保留 `projects` 在 `TABLE_WHITELIST` 供单表查询与被 JOIN。

导入期不变式扩展：`_assert_no_sensitive_in_whitelist()` 之后追加 `_assert_all_joins_have_business_key()`，使违规登记在模块导入时即失败。

### 7. 语句超时与取消（R6.4 / R6.5）

新增 `backend/app/services/custom_query/execution_guard.py`：

```python
QUERY_TIMEOUT_MS = 30_000
EXPORT_TIMEOUT_MS = 120_000

@asynccontextmanager
async def statement_timeout(db: AsyncSession, timeout_ms: int):
    await db.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": timeout_ms})
    yield
```

`SET LOCAL` 依赖显式事务，需确认 session 处于事务内（`db.in_transaction()`），否则先 `begin`。超时由 asyncpg 抛 `QueryCanceledError`，映射为 408 `QUERY_TIMEOUT`。

取消传播：FastAPI 在客户端断开时取消 task，`asyncpg` 收到 `CancelledError` 后需 `await conn.close()` 或依赖连接池回收；实现上在 `except asyncio.CancelledError` 分支显式 `await db.rollback()` 后重新抛出。

### 8. 技术列与 PII 分层（R7）

`table_whitelist.py` 每张表的 meta 增加两个并列键：

```python
"trial_balance": {
    "model": TrialBalance,
    "label": "试算平衡表",
    "fields": [...],                    # 保持不变（全量白名单，显式请求仍可用）
    "default_fields": [...],            # 新增：业务默认列集
    "technical_fields": [...],          # 新增：id/project_id/is_deleted/created_at/updated_at
    "pii_fields": [],                   # 新增：staff_members 为 email/phone/user_id
}
```

派生规则用一个纯函数集中生成，避免 15 张表逐个手写漂移：

```python
TECHNICAL_FIELD_NAMES = frozenset({"id", "project_id", "is_deleted", "created_at", "updated_at"})
def derive_field_tiers(fields: list[str], *, pii: frozenset[str]) -> FieldTiers
```

`GET /api/query/schema` 下发 `default_fields` / `technical_fields` / `pii_fields`，前端默认只展示 `default_fields`。PII 字段按角色过滤后下发；被显式请求且无权 → 403 `PII_FIELD_FORBIDDEN`。

### 9. 模板治理接线（R8）

router 的 5 个模板端点改为委托 `TemplateService`，`scope` 读写经 `TemplateScopeAdapter`。`delete_template` 移除 admin 例外分支（R8.5 明确要求 admin 亦不可删他人模板）。`shared_project_ids` 逐个经 `ownership_guard.assert_target_accessible` 鉴权，全部通过后才 `flush`，任一失败先 `rollback` 再抛 403。

### 10. 回写预览/确认端点（R9）

router 新增：

```python
@router.post("/writeback-preview")
async def writeback_preview(body: WritebackPreviewRequest, db=Depends(get_db), current_user=Depends(get_current_user))

@router.post("/writeback-confirm")
async def writeback_confirm(body: WritebackConfirmRequest, request: Request, db=Depends(get_db), current_user=Depends(get_current_user))
```

测试以 `SimpleNamespace` 直调这两个函数，故参数名必须为 `body` / `request` / `db` / `current_user`，且 `get_visible_project_ids` 必须以模块级名字被引用（`router_module.get_visible_project_ids`）以便 monkeypatch 生效。校验顺序：只读角色 403 → 项目可见性 403 → 逐目标 `assert_target_accessible` 403 → 才调用 `writeback_preview_service.generate` / `snapshot_writer.write_cell`。

### 11. 建表脚本（R10）

新建 `backend/scripts/_ensure_custom_query_tables.py`，模块级导出 `DDL` / `INDEXES_DDL` / `CHECK_SQL` / `ALTER_ADD_COLUMNS` / `main`。DDL 内容以 `V101__advanced_query_template_sharing.sql` 为准反向对齐，并加一条守卫测试比对两者列集，防止第二套真源漂移。导入无副作用（`main` 仅在 `__main__` 下执行）。

### 12. 前端改动（R11 / R12）

| 文件 | 改动 |
|---|---|
| `composables/useQueryBuilderAccess.ts`（新增） | 构建器可用性单一判据，与后端 `_QUERY_BUILDER_ROLES` 对齐 |
| `CustomQueryTab.vue` | 改用 `useQueryBuilderAccess`；接入翻页；技术列开关 |
| `AdvancedQueryBuilder.vue` | 字段下拉分「业务字段 / 技术字段」两组，默认只选业务列 |
| `CustomQueryDialog.vue` | 指标树改 `el-tree` lazy load；翻页 |
| `components/query/queryFieldTiers.ts`（新增） | 消费后端下发的列分层，不在前端硬编码列名 |
| `advancedQueryFrontend.spec.ts` | mock 补 `canDo` / `isReadonlyFor` 等实际消费成员 |

指标树懒加载：`GET /indicators` 增加 `depth` 与 `branch` 参数，默认 `depth=1` 返回骨架；展开时按 `branch` 取子树。`X-Indicators-Schema-Version` 递增至 10，前端缓存键自动失效。

## Data Models

### `FieldTiers`

```python
@dataclass(frozen=True)
class FieldTiers:
    default_fields: tuple[str, ...]
    technical_fields: tuple[str, ...]
    pii_fields: tuple[str, ...]
```

### `SortKey`

```python
@dataclass(frozen=True)
class SortKey:
    field: str
    direction: Literal["asc", "desc"]
    is_tie_breaker: bool = False
```

### 迁移

本 spec 不新增表结构变更。`V101` / `V102` 已提供 `shared_project_ids` 与 `advanced_query_writeback`；如实测发现运行库未应用，补一条幂等 `IF NOT EXISTS` 迁移而非改写既有 V 号。

## Error Handling

| 场景 | 状态码 | error_code |
|---|---|---|
| 未认证 | 401 | （框架默认） |
| 项目不可访问 | 403 | `FORBIDDEN_PROJECT` |
| 构建器角色不足 | 403 | `ROLE_FORBIDDEN` |
| 请求无权 PII 字段 | 403 | `PII_FIELD_FORBIDDEN` |
| 只读角色回写 | 403 | `WRITEBACK_FORBIDDEN` |
| 非模板 owner 改删 | 403 | `TEMPLATE_NOT_OWNER` |
| 表/JOIN/算子/聚合未登记 | 400 | `NOT_WHITELISTED` |
| 敏感表 | 400 | `SENSITIVE_TABLE_DENIED` |
| JOIN 缺业务键 | 400 | `JOIN_MISSING_BUSINESS_KEY` |
| JOIN/维度/聚合超预算 | 400 | `COMPLEXITY_BUDGET_EXCEEDED` |
| ACNR 目标不可解析 | 400 | `TARGET_UNRESOLVABLE` |
| sort 字段非法 | 422 | `INVALID_SORT_FIELD` |
| sort 方向非法 | 422 | `INVALID_SORT_FIELD_DIRECTION`（契约测试断言 `"INVALID_SORT_FIELD" in error_code`，故须含该前缀） |
| limit/offset 越界 | 422 | （pydantic）/ `INVALID_PAGINATION` |
| 语句超时 | 408 | `QUERY_TIMEOUT` |
| 预览项超限 | 400 | `PREVIEW_LIMIT_EXCEEDED` |
| 未预期异常 | 500 | `INTERNAL_ERROR` + `correlation_id` |

**禁止形态**：2xx 响应体携带 `error` 字段。当前 `custom_query.py` 的 `except Exception → 200 {"error": ...}` 必须移除。

## Properties

### Property 1: 只读端点认证不可绕过
对三个只读端点的任意参数组合，未认证请求恒返回 401，且数据库执行计数为 0。
**Validates: Requirements 1.1**

### Property 2: 归属校验先于取数
对任意不可访问的 project_id，端点返回 403 且树构建器 / 单元格读取 / 模板初始化的调用计数恒为 0。
**Validates: Requirements 1.2**

### Property 3: 无认证端点无写副作用
`wp_sheet_preview` 在归属校验失败时，`init_workpaper_from_template` 调用计数恒为 0。
**Validates: Requirements 1.4**

### Property 4: 构建器项目过滤不可覆盖
对任意含 project_id 列的表与任意用户 DSL（含用户自写的 project_id 过滤条件），生成的 SQL 恒包含作用域约束，且结果行的 project_id 集合恒 ⊆ 可访问集合。
**Validates: Requirements 2.1**

### Property 5: 作用域纳入缓存键
两个可访问项目集合不同的用户，对同一 DSL 恒不共享缓存条目。
**Validates: Requirements 2.4**

### Property 6: 单一执行路径
对任意合法业务视图请求体，adapter 的 execute 调用计数恒为 1；adapter 抛错时取数器调用计数恒为 0。
**Validates: Requirements 3.1, 3.2**

### Property 7: adapter 往返无损
对任意 legacy 请求体，`to_orchestrator_request` → `to_legacy_response` 往返后，原有字段恒保留；缺失字段恒被安全默认值填充。
**Validates: Requirements 3.3**

### Property 8: 列元数据往返无损
对任意 `ColumnMeta` 列表，`to_payload` → `from_payload` 往返后全部字段（含 `source`）恒相等。
**Validates: Requirements 3.5, 3.6**

### Property 9: total 反映聚合后行数
对任意原始行集与任意分组/透视配置，`total` 恒等于聚合后行数，而非原始行数。
**Validates: Requirements 4.1**

### Property 10: tie-breaker 追加不替换
对任意用户 sort，结果排序键序列恒以用户 sort 为前缀，tie-breaker 恒在末位。
**Validates: Requirements 4.2**

### Property 11: 排序确定性
对任意行集（含排序键完全重复的行），重复执行同一查询恒得到相同行顺序。
**Validates: Requirements 4.3**

### Property 12: 分页完备且不重叠
对任意行集与任意 `limit`，逐页取完的并集恒等于全集，任两页交集恒为空。
**Validates: Requirements 4.5**

### Property 13: 分页边界一律 422
对 `limit ≤ 0`、`limit > 上限`、`offset < 0` 的任意组合，router 与编排器两处入口恒返回 422。
**Validates: Requirements 4.6**

### Property 14: 失败不伪装成功
对任意抛错路径，响应恒不是「2xx 且响应体含 error」；`HTTPException` 的状态码恒被保留。
**Validates: Requirements 5.1, 5.3**

### Property 15: JOIN 必须含业务键
对 `JOIN_WHITELIST` 中任意登记项，ON 条件恒不为「仅 project_id ↔ project_id」；违规登记恒在模块导入期失败。
**Validates: Requirements 6.1**

### Property 16: 复杂度预算生效
对任意超出 JOIN 条数 / 分组维度 / 聚合个数上限的 DSL，恒返回 400 且不执行 SQL。
**Validates: Requirements 6.2, 6.3**

### Property 17: 默认列集不含技术列
对任意表，未显式选字段时返回的列集恒与 `default_fields` 相等，且与 `technical_fields` 交集恒为空。
**Validates: Requirements 7.1**

### Property 18: PII 按角色收敛
对任意无 PII 权限的角色，schema 下发的字段集恒不含 `pii_fields`；显式请求恒返回 403。
**Validates: Requirements 7.4**

### Property 19: 分享目标逐个鉴权且写前回滚
对任意 `shared_project_ids` 列表，鉴权调用次数恒等于去重后元素个数；任一失败时落库记录数恒为 0。
**Validates: Requirements 8.3, 8.4**

### Property 20: 非 owner 恒不可改删
对任意非创建者身份（含 admin），update 与 delete 恒返回 403。
**Validates: Requirements 8.5**

### Property 21: 回写全有或全无
对任意多目标回写请求，若存在任一不可访问目标，则 `write_cell` 调用计数恒为 0。
**Validates: Requirements 9.3, 9.4**

### Property 22: 建表脚本幂等
对任意执行次数 n ≥ 1，DDL 与索引 DDL 的最终结构恒一致，且导入模块恒无副作用。
**Validates: Requirements 10.2, 10.3**

### Property 23: 前后端权限判据一致
对 5 个平台角色的任意取值，前端 `canUseBuilder` 恒与后端是否返回 403 一致。
**Validates: Requirements 11.1**

### Property 24: 指标树骨架显著收敛
对任意项目，`depth=1` 响应的节点数恒小于全量树节点数的一个明确比例阈值，且展开任一分支恒只返回该分支子节点。
**Validates: Requirements 12.1, 12.2, 12.5**

## Testing Strategy

**基线**：以已入库的 75 条后端红 + 5 条前端红为主验收判据。任务完成的定义是对应测试转绿，而非「代码已写」。

**分层**：

1. 契约层 — 复用 `test_advanced_query_hardening_wave012.py`（60）、`test_custom_query_template_scope_hardening.py`（7）、`test_custom_query_templates.py::TestEnsureCustomQueryTables`（8）。
2. 属性层 — 24 条 Property 逐条一个 Hypothesis 测试，`max_examples ≥ 100`，标签 `Feature: advanced-query-hardening-wiring-closure, Property N`。
3. 接线层 — 新增守卫测试断言 7 个模块的 router 引用数 > 0（判据用「唯一消费方 + 真实执行」，不用符号 grep）。
4. 真库层 — 对真实 PG 验证 `statement_timeout` 生效、构建器结果 project_id 集合受限、JOIN 移除后无笛卡尔积回归。
5. 浏览器层 — Playwright 实测三个只读端点未认证 401、构建器默认列无 UUID、业务视图可翻第 2 页、指标树首屏体积收敛。

**变异检验**：每写完一条守卫做一次变异（改一字/删一调用/改一常量），要求恰好打红预期那条测试。四态判别 RED / GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）/ WRONG-TEST（锚点错行），只看退出码会把后三态误判为 RED。

**回归面**：不跑全量 `backend/tests`（1522 文件）。按引用关系反查辐射面：扫测试文件对 `custom_query` / `query_builder` / `services/custom_query/*` / `query_cache` 的实际引用，得到目标集后执行。
