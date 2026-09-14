# Bugfix Requirements Document

## Introduction

高级查询模块（custom-query）存在三处**已核实**的授权缺陷，均位于 `backend/app/routers/custom_query.py` 及其调用的 `snapshot_writer`。这些端点仅依赖 `Depends(get_current_user)` 完成"是否登录"判断，但**未做"该用户是否有权访问/修改这个项目"的项目级授权**。后果是数据越权读取（IDOR）与跨项目数据污染，属于安全/正确性级别（P0）缺陷。已通过完整调用链阅读核实（docs/architecture-improvement-proposals.md §5.12、§5.13、§17.1）。

本 bugfix 仅聚焦关闭两处具体漏洞（§5.12 + §5.13），复用既有授权基建（`deps.py` 的 `get_visible_project_ids` / `require_project_access` 与 `permission_matrix_service`），不引入新的自研检查逻辑。

受影响的三个端点 / 写路径：

1. `POST /api/custom-query/execute` — `execute_query`（`custom_query.py` ~L972–L1110）
2. `POST /api/custom-query/batch-execute` — `batch_execute`（`custom_query.py` ~L2020–L2104）
3. `POST /api/custom-query/cell-writeback` — `cell_writeback`（`custom_query.py` ~L2121），及其底层 `snapshot_writer.write_cell` / `_write_workpaper_cell`（`backend/app/services/custom_query/snapshot_writer.py`）

### 边界声明（Scope）

**纳入本 spec：**
- `execute` / `batch-execute` / `cell-writeback` 的项目级授权（读权限 / 编辑权限）。
- workpaper 定位查询的 `project_id` 过滤（消除跨项目命中）。
- `snapshot_writer` 所有模块写路径的权限强制。

**排除（属其他 spec）：**
- CI/lint 强制每个敏感端点声明 operation code 的全局基线 → 独立 spec `authorization-enforcement-baseline`（§17.1 全文）。
- 将 cell-writeback 重构为 `WorkpaperSaveOrchestrator`（§5.14 / §2.2）。
- 孤立事件总线问题（§5.7）。

### 关键定义（Bug Condition 方法论）

- **F**：修复前的函数（当前代码）。
- **F'**：修复后的函数。
- **C(X)**：触发缺陷的输入条件。
- **P(result)**：对 C(X) 输入修复后应满足的正确行为。
- **¬C(X)**：不触发缺陷的输入，修复后行为必须与 F 完全一致（回归保护）。
- **可见项目**：`get_visible_project_ids(current_user)` 返回的项目集合（admin/partner 见全部；其他角色仅见自己参与的项目）。
- **编辑权限**：`require_project_access("edit")` / `ProjectUser.permission_level` 达到 edit 层级。

## Bug Analysis

### Current Behavior (Defect)

**§5.12 — execute / batch-execute 缺项目级授权（IDOR）**

1.1 WHEN 已登录用户调用 `POST /api/custom-query/execute` 并传入不属于其可见项目的 `project_id` THEN the system 仍执行查询并返回该项目的报表/试算表/附注/调整/底稿/工时数据（无任何 `project_id ∈ 可见项目` 校验，`current_user` 仅用于缓存 key 与审计日志）

1.2 WHEN 已登录用户调用 `POST /api/custom-query/batch-execute` 并传入不属于其可见项目的 `project_id` THEN the system 仍对该项目逐 `wp_code` 执行查询并返回他人项目的底稿数据

1.3 WHEN 越权的 `execute` 查询命中 Redis 缓存键（key 含 user_id 但不影响越权命中的数据来源）THEN the system 在未做授权校验的情况下直接返回缓存或回写缓存

**§5.13 — cell-writeback 越权写入 + 跨项目写入**

1.4 WHEN 已登录用户调用 `POST /api/custom-query/cell-writeback` 且 `module != "workpaper"` THEN the system 仅校验全局角色白名单（admin/manager/partner/senior/assistant，几乎放行所有角色），不校验该用户对目标项目的成员资格或编辑权限

1.5 WHEN 已登录用户调用 `cell-writeback` 且 `module == "workpaper"` THEN the system 完全跳过授权检查（角色检查被包在 `if body.module != "workpaper"` 分支内），`snapshot_writer._write_workpaper_cell` 收到 `user` 但仅做乐观锁、从不校验任何权限

1.6 WHEN 多个项目存在相同 `wp_code`（如各项目都有 D2-1）且用户提交 workpaper 写回 THEN the system 用 `SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1`（无 `project_id` 过滤、无 `ORDER BY`）定位底稿，写回命中任意项目的同码底稿，造成跨项目数据污染

### Expected Behavior (Correct)

**§5.12 修复目标**

2.1 WHEN 已登录用户调用 `POST /api/custom-query/execute` 并传入不属于其可见项目的 `project_id` THEN the system SHALL 在任何查询分发之前、且在读取缓存之前返回 403，不泄露任何数据

2.2 WHEN 已登录用户调用 `POST /api/custom-query/batch-execute` 并传入不属于其可见项目的 `project_id` THEN the system SHALL 在执行任何 `wp_code` 子查询之前返回 403

2.3 WHEN `execute` 因越权被拒绝 THEN the system SHALL 不读取且不回写 Redis 查询缓存（授权校验先于缓存读写）

**§5.13 修复目标**

2.4 WHEN 已登录用户调用 `cell-writeback`（任意 `module`，含 `workpaper`）且其对目标 `project_id` 无编辑权限 THEN the system SHALL 返回 403，并且不写入任何数据

2.5 WHEN 用户调用 workpaper 模块的 `cell-writeback` THEN the system SHALL 要求请求体携带 `project_id`，并以 `WHERE wp_code = :code AND project_id = :project_id` 定位底稿（含 `project_id` 过滤），从而只可能命中该项目自己的底稿

2.6 WHEN 用户提交的 `project_id` + `wp_code` 在该项目下不存在对应底稿 THEN the system SHALL 返回 404，而不是回退到其他项目的同码底稿

2.7 WHEN `snapshot_writer.write_cell` / `_write_workpaper_cell`（及 report/note/adj/tb 各模块写路径）被调用 THEN the system SHALL 强制项目成员 + 编辑权限校验（复用 `require_project_access("edit")` 或 `ProjectUser` 权限层级 / `permission_matrix_service` 单一真源），权限不足时抛 `WritebackPermissionDenied`

2.8 WHEN 对所有模块做授权 THEN the system SHALL 采用统一的项目级授权（成员资格 + 编辑权限），不再以全局角色白名单作为兜底

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 已登录用户调用 `execute`/`batch-execute` 且 `project_id` 属于其可见项目 THEN the system SHALL CONTINUE TO 正常分发 14 个 `_query_*` 并返回相同的查询结果

3.2 WHEN 同一用户对同一可见项目重复发起相同查询 THEN the system SHALL CONTINUE TO 命中并回写 Redis 短 TTL 缓存（`X-Cache: HIT` 行为不变）

3.3 WHEN 命中既有审计路径（workpaper/consol_unit/disclosure_note/adj/disclosure 等敏感源）THEN the system SHALL CONTINUE TO 按现有节流策略写 `audit_log`（user_id / action / project_id / details 字段不变）

3.4 WHEN 用户对目标项目有编辑权限并对 workpaper 模块做 cell-writeback THEN the system SHALL CONTINUE TO 执行乐观锁比对（`updated_at` vs `X-File-Opened-At`），冲突时返回 409 `{conflict: true, ...}`，成功时返回 `{success: true, updated_at: ...}`

3.5 WHEN 写回成功 THEN the system SHALL CONTINUE TO 写入 `parsed_data` JSONB、标记 `prefill_stale`、同步 xlsx 缓存，并记录 `custom_query.cell_writeback` 审计日志（行为不变）

3.6 WHEN admin / partner 角色访问任意项目 THEN the system SHALL CONTINUE TO 可见全部项目（`get_visible_project_ids` 对 admin/partner 返回全部项目，授权校验对其放行）

3.7 WHEN tb 模块写回非 audited_amount 列 THEN the system SHALL CONTINUE TO 返回现有的 `WritebackPermissionDenied`（仅 G 列 audited_amount 可写的既有约束不变）

## Bug Condition Derivation

### §5.12 — execute / batch-execute IDOR

```pascal
FUNCTION isBugCondition_5_12(X)
  INPUT: X = (current_user, project_id)  // execute / batch-execute 请求
  OUTPUT: boolean

  // 已登录但目标项目不在可见集合内
  RETURN project_id NOT IN get_visible_project_ids(current_user)
END FUNCTION
```

```pascal
// Property: Fix Checking — 越权读取必须被拒
FOR ALL X WHERE isBugCondition_5_12(X) DO
  result ← execute_query'(X)            // 或 batch_execute'(X)
  ASSERT result.status = 403
      AND no_data_returned(result)
      AND no_cache_read(X)              // 授权先于缓存
      AND no_query_dispatch(X)          // 授权先于 _query_* 分发
END FOR
```

```pascal
// Property: Preservation Checking — 合法同项目访问不变
FOR ALL X WHERE NOT isBugCondition_5_12(X) DO
  ASSERT execute_query(X) = execute_query'(X)   // 结果、缓存、审计行为一致
END FOR
```

### §5.13 — cell-writeback 越权 + 跨项目写

```pascal
FUNCTION isBugCondition_5_13(X)
  INPUT: X = (current_user, project_id, wp_code, module, cell)
  OUTPUT: boolean

  // (a) 对目标项目无编辑权限，或
  // (b) workpaper 定位未按 project_id 过滤（跨项目命中风险）
  RETURN (NOT has_edit_permission(current_user, project_id))
      OR (module = "workpaper" AND lookup_ignores_project_id(X))
END FUNCTION
```

```pascal
// Property: Fix Checking — 越权写 / 跨项目写必须不可能
FOR ALL X WHERE isBugCondition_5_13(X) DO
  result ← cell_writeback'(X)
  ASSERT (result.status = 403 AND no_write_occurred(X))          // 无编辑权限
      OR (result.status = 404 AND no_cross_project_write(X))     // 本项目无此底稿，绝不命中他项目
  // 任一情况下：写入仅可能落在 (project_id, wp_code) 唯一确定的本项目底稿上
  ASSERT written_workpaper(X).project_id = X.project_id OR no_write_occurred(X)
END FOR
```

```pascal
// Property: Preservation Checking — 合法同项目编辑不变
FOR ALL X WHERE NOT isBugCondition_5_13(X) DO
  ASSERT cell_writeback(X) = cell_writeback'(X)
  // 乐观锁 409 / 成功 200 / JSONB 写入 / prefill_stale / xlsx 同步 / 审计 均不变
END FOR
```

## Fix Verification Criteria

修复完成后必须满足（与正确行为条款对应）：

- **越权读返回 403**：非可见项目的 `execute` / `batch-execute` 一律 403，且在缓存读取与查询分发之前拒绝（验证 2.1 / 2.2 / 2.3）。
- **跨项目写不可能**：workpaper 定位查询带 `project_id`，多项目同 `wp_code` 场景下写回只可能命中本项目底稿；本项目无此底稿则 404，绝不回退他项目（验证 2.5 / 2.6）。
- **越权写返回 403**：无编辑权限的任意模块写回（含 workpaper）一律 403 且无任何写入（验证 2.4 / 2.7 / 2.8）。
- **合法同项目访问不变**：可见项目的读查询结果、缓存命中、审计日志、乐观锁 409、成功写入与下游 stale/xlsx 同步行为全部与修复前一致（验证 3.1–3.7）。
