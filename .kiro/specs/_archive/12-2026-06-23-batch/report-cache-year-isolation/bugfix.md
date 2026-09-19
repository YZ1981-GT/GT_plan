# Bugfix Requirements Document

## Introduction

报表生成引擎（`report_engine.py`）的 Redis 缓存键 `_cache_key` 构造为 `report:{project_id}:{report_type}`——**不含 year**。平台支持多年度共存（同一项目的 2024 和 2025 年度数据并行），缓存键缺失年度维度导致**跨年度串数据**（10 分钟 TTL 内持续错误）。

已通过代码阅读核实（docs/architecture-improvement-proposals.md §9.1）：`get_report_cached(project_id, year, report_type)` 入参含 year 但从不传入 `_cache_key`。

受影响代码：
- `backend/app/services/report_engine.py`：`_cache_key`（~L757）、`_get_cached_report`、`_set_cached_report`、`_invalidate_report_cache`、`get_report_cached`
- `backend/app/services/event_handlers.py`：`_invalidate_report_redis`（使用 `report:{pid}:*` 模式删键）

### 边界声明

**纳入**：`_cache_key` 补 year；所有调用方适配；失效逻辑兼容新 key 结构。

**排除**：报表生成逻辑重构（§9.3）；公式正则统一（§9.2）。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户先查看项目 P 年度 2024 的 balance_sheet 报表，缓存 TTL 10 分钟内再查看同项目年度 2025 的 balance_sheet THEN the system 返回 2024 的缓存数据（因 key `report:{P}:balance_sheet` 相同，缓存命中但年度错误）

1.2 WHEN `generate_all_reports` 为年度 2024 执行后回写缓存，随后年度 2025 的 `get_report_cached` 被调用 THEN the system 读到 2024 的数据并认为"缓存已有，无需查库"

1.3 WHEN `_invalidate_report_cache(project_id, report_type)` 被调用 THEN the system 只删除一个无年度的 key，而非按年度精确失效

### Expected Behavior (Correct)

2.1 WHEN 用户查看项目 P 年度 Y 的报表类型 T THEN the system SHALL 使用缓存键 `report:{project_id}:{year}:{report_type}`，仅在 (project_id, year, report_type) 三元组完全匹配时返回缓存数据

2.2 WHEN `_set_cached_report` / `_get_cached_report` 被调用 THEN the system SHALL 将 year 纳入 key 构建，缓存的报表数据仅服务同年度请求

2.3 WHEN `_invalidate_report_cache(project_id, report_type=None)` 被调用 THEN the system SHALL 失效该项目所有年度所有类型的缓存键（通过 wildcard `report:{pid}:*` 或遍历已知年度×类型组合）

2.4 WHEN `_invalidate_report_cache(project_id, report_type='balance_sheet')` 被调用 THEN the system SHALL 失效该项目所有年度的 balance_sheet 缓存

2.5 WHEN event_handlers 的 `_invalidate_report_redis` 用 `report:{pid}:*` 模式 THEN the system SHALL 继续正确匹配新 key 结构 `report:{pid}:{year}:{rt}`（wildcard 兼容）

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 同一项目同一年度同一报表类型在 TTL 内重复请求 THEN the system SHALL CONTINUE TO 返回缓存命中（性能不退化）

3.2 WHEN 缓存未命中时 THEN the system SHALL CONTINUE TO 从 DB 加载 `FinancialReport` 行并回写缓存，TTL = 10 分钟

3.3 WHEN event_handlers 的调整/导入/回滚事件触发 `_invalidate_report_redis` THEN the system SHALL CONTINUE TO 删除该项目所有报表缓存（`report:{pid}:*` 模式仍匹配新 key）

3.4 WHEN `ReportEngine` 以 `redis=None` 初始化（Redis 不可用） THEN the system SHALL CONTINUE TO 直接查库，不触发缓存路径

## Bug Condition Derivation

```pascal
FUNCTION isBugCondition_9_1(X)
  INPUT: X = (project_id, year_requested, report_type)
  OUTPUT: boolean

  // 缓存中存在不同年度写入的同 project_id + report_type 数据
  cached_year ← year_of_data_in_cache(project_id, report_type)
  RETURN cached_year IS NOT NULL AND cached_year != year_requested
END FUNCTION
```

```pascal
// Fix Checking — 跨年度串数据不可能
FOR ALL X WHERE isBugCondition_9_1(X) DO
  result ← get_report_cached'(X.project_id, X.year_requested, X.report_type)
  ASSERT result IS NULL OR year_of(result) = X.year_requested
  // 缓存 key 含 year → 不同年度的 key 不同 → 永不互相命中
END FOR
```

```pascal
// Preservation Checking — 同年度缓存行为不变
FOR ALL X WHERE NOT isBugCondition_9_1(X) DO
  ASSERT get_report_cached(X) = get_report_cached'(X)
END FOR
```

## Fix Verification Criteria

- `_cache_key` 签名变为 `_cache_key(self, project_id, year, report_type)` → key 含年度
- 同项目不同年度的报表缓存互不干扰（验证 2.1/2.2）
- 失效逻辑覆盖所有年度（验证 2.3/2.4/2.5）
- event_handler wildcard `report:{pid}:*` 仍能匹配新结构（验证 3.3）
- 测试：连续 `set(pid, 2024, bs, data_2024)` + `get(pid, 2025, bs)` = None（而非 data_2024）
