# Custom Query Authorization Hardening — Bugfix Design

## Overview

`custom_query.py` 的三个端点（`execute`、`batch-execute`、`cell-writeback`）仅验证用户已登录（`get_current_user`），未做项目级授权。攻击者可通过枚举 `project_id` 实现 IDOR 读取任意项目数据，或通过 `wp_code` 无 `project_id` 过滤实现跨项目写入。

修复策略：**复用既有授权基建**（`get_visible_project_ids` + `require_project_access("edit")`），在端点入口处加装项目可见性/编辑权限校验，并在 workpaper 定位查询中加入 `project_id` 过滤条件。不引入新的自研授权逻辑。

## Glossary

- **Bug_Condition (C)**: 已登录用户对其无权项目发起读/写请求（IDOR / 跨项目写入）
- **Property (P)**: 越权请求被 403/404 拦截，不泄露数据、不写入数据
- **Preservation**: 合法同项目访问（读查询结果、缓存、审计、乐观锁、写入流程）保持不变
- **`get_visible_project_ids`**: `deps.py` ~L352，返回当前用户可见项目 ID 集合（admin/partner 见全部）
- **`require_project_access("edit")`**: `deps.py` ~L176，项目级编辑权限校验工厂（含 Redis 缓存、归档守卫）
- **`snapshot_writer.write_cell`**: `services/custom_query/snapshot_writer.py`，按 module 分派单 cell 写入
- **IDOR**: Insecure Direct Object Reference，通过可预测的 project_id 直接引用他人项目

## Bug Details

### Bug Condition

`execute`/`batch-execute` 在缓存读取和查询分发之前无 `project_id ∈ visible_projects` 校验；`cell-writeback` 对 workpaper 模块零授权，且 `SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1` 无 `project_id` 过滤导致跨项目写。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input = (current_user, project_id, endpoint, wp_code?, module?)
  OUTPUT: boolean

  IF endpoint IN ["execute", "batch-execute"] THEN
    RETURN project_id NOT IN get_visible_project_ids(current_user)
  END IF

  IF endpoint == "cell-writeback" THEN
    RETURN NOT has_edit_permission(current_user, project_id)
        OR (module == "workpaper" AND wp_lookup_ignores_project_id(wp_code, project_id))
  END IF
END FUNCTION
```

### Examples

- **IDOR 读**：`assistant` 角色用户传入他人项目 `project_id` 调用 `execute` → 返回该项目的试算表/报表数据（应 403）
- **跨项目写**：项目 A 和项目 B 都有 `wp_code = "D2-1"`，用户有项目 A 权限但传 B 的 `wp_code` → `LIMIT 1` 可能命中项目 B 底稿（应只命中本项目或 404）
- **workpaper 零授权**：无任何项目成员资格的用户对 `module=workpaper` 调用 `cell-writeback` → 绕过角色白名单（在 `if body.module != "workpaper"` 分支之外）直接写入
- **admin 合法访问**：admin 对任意项目调用 `execute` → `get_visible_project_ids` 返回全部 → 正常放行（不变）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 已授权用户对可见项目的 `execute`/`batch-execute` 正常返回查询结果（3.1）
- Redis 短 TTL 缓存命中/回写逻辑不变（3.2）
- 审计日志节流写入行为不变（3.3）
- 乐观锁冲突 409 / 成功 200 / JSONB 写入 / `prefill_stale` / xlsx 同步逻辑不变（3.4, 3.5）
- admin/partner 角色可见全部项目、可编辑全部项目（3.6）
- tb 模块非 `audited_amount` 列返回 `WritebackPermissionDenied` 不变（3.7）

**Scope:**
已通过项目级授权的请求进入后续逻辑时，行为与修复前完全一致（缓存 key 不变、查询分发不变、写入路径不变）。

## Hypothesized Root Cause

1. **设计遗漏 — 端点缺少项目授权 Depends**：`execute` / `batch-execute` 未注入 `require_project_access` 或等价校验，仅用 `get_current_user` 做登录态验证。
2. **workpaper 分支逻辑反转**：`cell-writeback` 中 `if body.module != "workpaper"` 分支做角色白名单，workpaper 模块反而跳过全部检查。
3. **角色白名单过于宽松**：非 workpaper 模块的白名单几乎放行所有角色（admin/manager/partner/senior/assistant），等同无效检查。
4. **workpaper 定位查询缺 project_id**：`SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1` 无 `project_id` 条件 + 无 `ORDER BY`，多项目同码时命中不可预测。

## Correctness Properties

Property 1: Bug Condition — 越权读/写必须被拒

_For any_ input where the user's `project_id` is NOT in their visible projects (for reads) or the user lacks edit permission on `project_id` (for writes), the fixed endpoints SHALL return 403 without executing any query, reading/writing cache, or writing data.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.8**

Property 2: Bug Condition — 跨项目 workpaper 写入不可能

_For any_ `cell-writeback` input where `module == "workpaper"`, the fixed endpoint SHALL locate the working paper using `WHERE wp_code = :code AND project_id = :pid`; if no row matches, return 404 rather than falling through to another project's workpaper.

**Validates: Requirements 2.5, 2.6**

Property 3: Preservation — 合法同项目访问不变

_For any_ input where the bug condition does NOT hold (user has visibility/edit permission on the target project AND workpaper belongs to that project), the fixed endpoints SHALL produce identical results to the original code, preserving query results, cache behavior, audit logging, optimistic lock conflict handling, and write-through logic.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming root cause analysis is correct:

**File**: `backend/app/routers/custom_query.py`

**1. execute_query — 加项目可见性校验（BEFORE cache read）**:
- 在 `source = body.source` 赋值之前插入：
  ```python
  visible_ids = await get_visible_project_ids(current_user, db)
  if UUID(body.project_id) not in visible_ids:
      raise HTTPException(403, detail={"error_code": "PROJECT_NOT_VISIBLE"})
  ```
- 调用一次 `get_visible_project_ids`（已内置缓存），开销可忽略。

**2. batch_execute — 同样加项目可见性校验**:
- 在 for 循环之前：
  ```python
  visible_ids = await get_visible_project_ids(current_user, db)
  if UUID(body.project_id) not in visible_ids:
      raise HTTPException(403, detail={"error_code": "PROJECT_NOT_VISIBLE"})
  ```

**3. CellWritebackRequest — 添加 project_id 必填字段**:
- `project_id: str` 加入请求体 schema（破坏性变更，前端须同步更新）。

**4. cell_writeback — 统一项目编辑权限校验（替代角色白名单）**:
- 删除 `if body.module != "workpaper"` 角色白名单分支。
- 替换为对所有模块统一校验：
  ```python
  from app.deps import require_project_access
  # 或 inline: 查 ProjectUser 确认 edit 权限
  visible_ids = await get_visible_project_ids(current_user, db)
  if UUID(body.project_id) not in visible_ids:
      raise HTTPException(403, detail={"error_code": "PROJECT_NOT_VISIBLE"})
  # 编辑权限（非 admin/partner 需检查 permission_level >= edit）
  if current_user.role.value not in ("admin", "partner"):
      pu = await db.execute(
          select(ProjectUser).where(
              ProjectUser.project_id == UUID(body.project_id),
              ProjectUser.user_id == current_user.id,
              ProjectUser.is_deleted == False,
          )
      )
      member = pu.scalar_one_or_none()
      if not member or member.permission_level not in ("edit", "admin", "owner"):
          raise HTTPException(403, detail={"error_code": "NO_EDIT_PERMISSION"})
  ```

**5. workpaper 定位查询加 project_id 过滤**:
- 改：`SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1`
- 为：`SELECT id FROM working_paper WHERE wp_code = :code AND project_id = :pid LIMIT 1`
- 用 `body.project_id` 绑定 `:pid`。
- 无匹配行 → 404 `"Working paper not found in this project"`。

**6. snapshot_writer — belt+suspenders 校验（可选但推荐）**:

**File**: `backend/app/services/custom_query/snapshot_writer.py`

- `_write_workpaper_cell` 的 `SELECT FOR UPDATE` 结果中提取 `project_id`：
  ```sql
  SELECT updated_at, parsed_data, wp_code, file_path, project_id
  FROM working_paper WHERE id = :wp_id FOR UPDATE
  ```
- 对比传入的 `expected_project_id` 参数，不匹配则抛 `WritebackPermissionDenied`。
- `write_cell` 签名新增 `project_id: str | None = None` 可选参数。

## Testing Strategy

### Validation Approach

两阶段验证：先在未修复代码上运行探索性测试确认 bug 可复现，再在修复后验证 fix checking + preservation checking。

### Exploratory Bug Condition Checking

**Goal**: 在未修复代码上复现 IDOR 和跨项目写入，确认根因假设。

**Test Plan**: 模拟低权限用户传入不可见 `project_id` 调用三个端点，断言当前代码错误地返回 200 而非 403。

**Test Cases**:
1. **IDOR execute**: 创建 user A（仅项目 P1 成员），传项目 P2 的 `project_id` → 当前返回 200 + 数据（应 403）
2. **IDOR batch-execute**: 同上，batch 路径 → 当前返回 200
3. **Workpaper 零授权**: user 无任何项目成员资格，`module=workpaper` writeback → 当前不拦截
4. **跨项目 wp_code 命中**: 项目 P1 和 P2 都有 `wp_code="D2-1"`，user 仅在 P1，未传 `project_id` → 当前代码 `LIMIT 1` 可能命中 P2

**Expected Counterexamples**:
- 端点返回 200 + 数据泄露（execute / batch-execute）
- 端点写入他人项目底稿（cell-writeback workpaper）

### Fix Checking

**Goal**: 验证修复后，所有越权输入均被拒绝。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := endpoint_fixed(input)
  ASSERT result.status IN [403, 404]
      AND no_data_returned(result)
      AND no_cache_read_or_write(input)
      AND no_db_write(input)
END FOR
```

### Preservation Checking

**Goal**: 验证修复后，合法同项目访问行为完全不变。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT endpoint_original(input) = endpoint_fixed(input)
  // 返回值、状态码、缓存头、审计日志内容一致
END FOR
```

**Testing Approach**: Property-based testing (Hypothesis) 推荐用于 preservation checking：
- 随机生成合法 user+project 组合，验证返回值一致性
- 随机生成 wp_code + project_id 组合（项目内存在），验证 writeback 行为一致

**Test Cases**:
1. **合法 execute 结果不变**: admin/有权用户对可见项目查询 → 结果集与修复前一致
2. **缓存行为不变**: 同一合法查询第二次调用 → `X-Cache: HIT` 头存在
3. **乐观锁不变**: 合法 writeback 传过期 `X-File-Opened-At` → 仍返回 409 conflict
4. **admin 全项目访问不变**: admin 对任意项目 execute/writeback → 正常放行

### Unit Tests

- `test_execute_rejects_invisible_project`: 非可见项目 → 403 + `PROJECT_NOT_VISIBLE`
- `test_batch_execute_rejects_invisible_project`: 同上 batch 路径
- `test_cell_writeback_rejects_no_edit_permission`: 无编辑权限 → 403
- `test_cell_writeback_requires_project_id`: 请求体缺 `project_id` → 422 validation error
- `test_workpaper_lookup_with_project_id_filter`: 多项目同 wp_code → 仅命中本项目
- `test_workpaper_not_in_project_returns_404`: 本项目无此 wp_code → 404
- `test_admin_bypasses_visibility`: admin 对任意项目 → 放行
- `test_partner_bypasses_visibility`: partner 对任意项目 → 放行
- `test_auth_before_cache`: mock cache hit，越权请求仍 403（不从缓存返回数据）

### Property-Based Tests

- **PBT fix-checking**: 随机生成 (user_role, visible_projects, target_project_id)，当 target ∉ visible 时断言 403
- **PBT preservation**: 随机生成合法 (user, project ∈ visible, source, filters)，断言 fixed endpoint 返回与 original 相同结构
- **PBT cross-project isolation**: 随机生成多项目含同 wp_code 场景，验证 writeback 只命中 target project 的底稿

### Integration Tests

- 全流程 `execute → cache → re-execute`（合法用户）验证缓存正常
- 全流程 `cell-writeback → commit → re-read` 验证数据写入正确位置
- 混合场景：用户先 execute（合法），再 execute 另一项目（越权）→ 第一个成功第二个 403
- admin 跨项目操作全流程验证
