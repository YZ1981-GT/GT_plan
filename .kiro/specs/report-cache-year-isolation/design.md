# Report Cache Year Isolation Bugfix Design

## Overview

`ReportEngine._cache_key` 构造 Redis 键为 `report:{project_id}:{report_type}`，缺少 year 维度。同一项目不同年度的报表共享同一 key，导致 10 分钟 TTL 内跨年度返回错误数据。修复方案：将 year 纳入 key 构建，变更为 `report:{project_id}:{year}:{report_type}`。影响范围仅 `report_engine.py` 内 4 个私有方法 + 1 个公共方法，约 20 行变更。

## Glossary

- **Bug_Condition (C)**: 缓存中存在不同年度写入的同 project_id + report_type 数据，请求年度与缓存年度不一致
- **Property (P)**: 缓存键包含 year 维度，不同年度的报表永远不会互相命中
- **Preservation**: 同项目同年度同类型的缓存命中、TTL、失效通配符等行为保持不变
- **_cache_key**: `report_engine.py` ~L757 的私有方法，负责构造 Redis 缓存键
- **REPORT_CACHE_TTL**: 报表缓存过期时间（10 分钟 / 600 秒）
- **event_handlers._invalidate_report_redis**: 事件处理器中使用 `report:{pid}:*` 通配符删除缓存的函数

## Bug Details

### Bug Condition

`_cache_key(project_id, report_type)` 返回的键不含 year，导致 `get_report_cached(project_id, year, report_type)` 中 year 参数被忽略。不同年度的同一类型报表写入/读取同一个 Redis key。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input = (project_id, year_requested, report_type)
  OUTPUT: boolean

  cached_year ← year_of_last_write(project_id, report_type)
  RETURN cached_year IS NOT NULL
         AND cached_year ≠ year_requested
END FUNCTION
```

### Examples

- 用户查看项目 P 年度 2024 的 balance_sheet → 缓存写入 key `report:P:balance_sheet`。随后查看 2025 的 balance_sheet → 命中同一 key，返回 2024 数据（**错误**）
- `generate_all_reports(P, 2024)` 回写缓存后，`get_report_cached(P, 2025, 'income_statement')` 拿到 2024 的利润表（**错误**）
- `_invalidate_report_cache(P)` 删除 4 个无年度 key，但新 key 含年度后不匹配（**失效失败**）
- 同年度重复请求 `get_report_cached(P, 2024, 'cash_flow_statement')` → 缓存命中，返回正确数据（**正常，无 bug**）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 同项目同年度同类型报表在 TTL 内重复请求仍返回缓存命中（性能不退化）
- 缓存未命中时仍从 DB 加载 FinancialReport 并回写缓存，TTL = 600s
- `event_handlers._invalidate_report_redis` 使用 `report:{pid}:*` 通配符仍能匹配新 key 结构（`report:{pid}:{year}:{rt}` 被 `report:{pid}:*` 覆盖）
- Redis 不可用时（`self.redis = None`）直接查库，不触发缓存路径

**Scope:**
同年度请求（`year_requested == cached_year`）的缓存行为完全不受影响。event_handler 的通配符失效逻辑因 `*` 匹配任意后续段，无需改动。

## Hypothesized Root Cause

根因已确认（非假设）：

1. **`_cache_key` 缺少 year 参数**: 方法签名为 `_cache_key(self, project_id, report_type)` → 格式化字符串无 year 占位
2. **`get_report_cached` 未传递 year**: 方法接收 year 参数但调用 `_cache_key` 时未传入
3. **`_get_cached_report` / `_set_cached_report` 无 year 参数**: 整条调用链均无 year 透传
4. **`_invalidate_report_cache` 遍历固定类型列表无 year**: 按 4 种 report_type 逐个删 key，无年度维度

## Correctness Properties

Property 1: Bug Condition - 跨年度缓存隔离

_For any_ input `(project_id, year_A, year_B, report_type)` where `year_A ≠ year_B`，在年度 A 写入缓存后，使用年度 B 读取 SHALL 返回 cache miss（None），不返回年度 A 的数据。

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - 同年度缓存命中

_For any_ input `(project_id, year, report_type, data)` where 先 set 再 get 使用相同的 (project_id, year, report_type) 三元组，固定函数 SHALL 返回与原始函数相同的缓存命中行为，即返回之前写入的 data。

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

**File**: `backend/app/services/report_engine.py`

**Specific Changes**:

1. **`_cache_key` 添加 year 参数**:
   - 签名变为 `_cache_key(self, project_id: UUID, year: int, report_type: str) -> str`
   - 返回值变为 `f"report:{project_id}:{year}:{report_type}"`

2. **`_get_cached_report` 添加 year 参数**:
   - 签名加 `year: int`
   - 内部调用 `self._cache_key(project_id, year, report_type)`

3. **`_set_cached_report` 添加 year 参数**:
   - 签名加 `year: int`
   - 内部调用 `self._cache_key(project_id, year, report_type)`

4. **`_invalidate_report_cache` 改用通配符**:
   - 改为 `pattern = f"report:{project_id}:*"` + `SCAN` 或保持逐类型删除但加年度参数
   - 推荐方案：使用 `await self.redis.delete(*keys)` 配合 SCAN pattern `report:{pid}:*`（与 event_handler 一致）
   - 备选：接受 `year: int | None` 参数，None 时通配符删全部，有值时只删指定年度

5. **更新所有内部调用方**:
   - `get_report_cached` 将已有的 year 参数传递到 `_get_cached_report` / `_set_cached_report`
   - `generate_all_reports` 中回写缓存处传入 year

**File**: `backend/app/services/event_handlers.py`

**无需改动**: `_invalidate_report_redis` 已使用 `report:{pid}:*` 通配符，可匹配新 key 格式 `report:{pid}:{year}:{rt}`。

## Testing Strategy

### Validation Approach

变更仅涉及 key 构建逻辑，测试策略以单元测试为主，用 mock Redis 验证 key 格式和缓存隔离。

### Exploratory Bug Condition Checking

**Goal**: 在未修复代码上复现跨年度串数据。

**Test Cases**:
1. **跨年度串数据复现**: `_set_cached_report(pid, 'bs', data_2024)` → `_get_cached_report(pid, 'bs')` 返回 data_2024 而非区分年度（当前函数无 year 参数，此即 bug 本身）

**Expected Counterexamples**:
- 任何 year_A ≠ year_B 的 set/get 组合都返回错误数据

### Fix Checking

**Goal**: 验证跨年度缓存完全隔离。

**Pseudocode:**
```
FOR ALL (pid, year_A, year_B, rt, data) WHERE year_A ≠ year_B DO
  _set_cached_report(pid, year_A, rt, data)
  result := _get_cached_report(pid, year_B, rt)
  ASSERT result IS NULL
END FOR
```

### Preservation Checking

**Goal**: 验证同年度缓存行为不变。

**Pseudocode:**
```
FOR ALL (pid, year, rt, data) DO
  _set_cached_report(pid, year, rt, data)
  result := _get_cached_report(pid, year, rt)
  ASSERT result == data
END FOR
```

**Testing Approach**: 此场景输入空间小（4 种 report_type × 有限年度范围），参数化测试即可覆盖，无需完整 PBT。

### Unit Tests

- `test_cache_key_includes_year`: 验证 `_cache_key(pid, 2024, 'balance_sheet')` 返回 `report:{pid}:2024:balance_sheet`
- `test_cross_year_isolation`: set year=2024 → get year=2025 = None
- `test_same_year_hit`: set year=2024 → get year=2024 = data
- `test_invalidate_clears_all_years`: invalidate(pid) 后所有年度缓存均失效
- `test_event_handler_wildcard_matches`: `report:{pid}:*` 匹配 `report:{pid}:2024:balance_sheet`

### Property-Based Tests

- 生成随机 (project_id, year_A, year_B, report_type) 组合，验证 year_A ≠ year_B 时缓存隔离
- 生成随机 data payload，验证同年度 set/get roundtrip 一致性

### Integration Tests

- 端到端调用 `get_report_cached(pid, 2024, 'bs')` + `get_report_cached(pid, 2025, 'bs')` 验证返回不同数据
- 触发 event_handler 失效后验证所有年度缓存均被清除
