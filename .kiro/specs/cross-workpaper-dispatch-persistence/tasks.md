# Implementation Plan: Cross-Workpaper Dispatch Persistence

## Overview

为 D0-1 函证汇总表的跨底稿分发逻辑实现后端持久化。按依赖顺序：迁移 → ORM → Service → Router → EventBus → 前端 API → composable 改造 → 下游 composable。每步构建在前一步之上，最终集成联调。

## Tasks

- [ ] 1. 数据库迁移：创建 dispatch_records 表
  - [ ] 1.1 创建 V092__create_dispatch_records.sql 迁移文件
    - 在 `backend/migrations/` 下新建 `V092__create_dispatch_records.sql`
    - 包含 `CREATE TABLE IF NOT EXISTS dispatch_records`（全字段 + 唯一约束 + 索引）
    - 包含 `CREATE INDEX IF NOT EXISTS ix_dispatch_project_target`
    - _Requirements: 1.1, 1.2_
  - [ ] 1.2 创建 R092__create_dispatch_records.sql 回滚文件
    - `DROP TABLE IF EXISTS dispatch_records;`
    - _Requirements: 1.1_

- [ ] 2. 后端 ORM 模型
  - [ ] 2.1 创建 dispatch_models.py
    - 在 `backend/app/models/dispatch_models.py` 定义 `DispatchRecord(Base, TimestampMixin)`
    - 字段：id(UUID PK), project_id(FK), confirm_index, target, entity_name, account_type, amount, reason, dispatched_by(FK), dispatched_at
    - `__table_args__` 含 UniqueConstraint('project_id','confirm_index','target') + Index
    - _Requirements: 1.1, 2.4_
  - [ ]* 2.2 Property test: dispatch record field round-trip
    - **Property 1: Dispatch record field round-trip**
    - 使用 hypothesis 生成随机 DispatchEntry，验证 create→query 字段一致
    - **Validates: Requirements 1.1, 2.4**

- [ ] 3. 后端业务服务
  - [ ] 3.1 创建 dispatch_service.py
    - 在 `backend/app/services/dispatch_service.py` 实现 `DispatchService` 类
    - `batch_create(db, project_id, entries, user_id)` → INSERT ON CONFLICT DO NOTHING + 二次查询得 skipped（PG 不返回跳过行），返回 BatchResult(dispatched, skipped)
    - `list_records(db, project_id, *, target=None, confirm_index=None)` → 带可选过滤的查询
    - `revoke(db, record_id, user_id, is_manager=False)` → 权限校验 + 删除
    - service 只 flush 不 commit（由 router 层 commit）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 6.1, 6.3_
  - [ ]* 3.2 Property test: dedup idempotence
    - **Property 2: Dedup idempotence**
    - 生成随机 entry，连续 insert 两次，验证第二次 skipped + 总数不变
    - **Validates: Requirements 1.2, 4.3**
  - [ ]* 3.3 Property test: batch atomicity
    - **Property 3: Batch atomicity**
    - 构造包含非法 entry 的批次，验证原子回滚（零记录写入）
    - **Validates: Requirements 1.3, 1.4**
  - [ ]* 3.4 Property test: query filter correctness
    - **Property 4: Query filter correctness**
    - 生成多项目/多 target 记录集，验证各种 filter 组合返回正确子集
    - **Validates: Requirements 2.1, 2.2, 2.3, 4.1**
  - [ ]* 3.5 Property test: revoke removes record
    - **Property 8: Revoke removes record**
    - 生成记录后 revoke，验证 query 不再包含 + count 减一
    - **Validates: Requirements 6.1**
  - [ ]* 3.6 Property test: revoke access control
    - **Property 10: Revoke access control**
    - 生成 (record, user, role) 组合，验证权限判定正确
    - **Validates: Requirements 6.3**

- [ ] 4. Checkpoint - 后端服务层验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. 后端 REST Router
  - [ ] 5.1 创建 dispatch_records.py router
    - 在 `backend/app/routers/dispatch_records.py` 实现：
    - `POST /projects/{pid}/dispatch-records`：Pydantic schema 校验 entries（非空、target 白名单）→ 调用 batch_create → publish EventBus → commit → 返回 dispatched+skipped
    - `GET /projects/{pid}/dispatch-records`：可选 query params target/confirm_index → 调用 list_records
    - `DELETE /projects/{pid}/dispatch-records/{id}`：权限校验 → 调用 revoke → publish EventBus → commit
    - 错误处理：空 entries→400, target 非法→422, 不存在→404, 权限不足→403
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 6.1, 6.3_
  - [ ] 5.2 注册 router 到主 app
    - 在 `backend/app/main.py` 或 router_registry 中注册 dispatch_records router
    - _Requirements: 2.1_

- [ ] 6. EventBus 事件类型扩展
  - [ ] 6.1 新增 DISPATCH_CREATED / DISPATCH_REVOKED 事件类型
    - 在 EventType 枚举中添加 `DISPATCH_CREATED = "dispatch.created"` 和 `DISPATCH_REVOKED = "dispatch.revoked"`
    - Router 中 publish EventPayload(event_type, project_id, extra={confirm_indices, target, dispatched_by})
    - _Requirements: 7.1, 7.3_
  - [ ]* 6.2 Property test: event payload correctness
    - **Property 13: Event payload correctness**
    - 验证 batch_create/revoke 后 EventBus 收到正确 event_type + payload 结构
    - **Validates: Requirements 7.1, 7.3**

- [ ] 7. Checkpoint - 后端完整验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 前端 API 封装
  - [ ] 8.1 创建 dispatchApi.ts
    - 在 `audit-platform/frontend/src/api/dispatchApi.ts` 封装：
    - `batchCreateDispatch(projectId, entries)` → POST
    - `listDispatchRecords(projectId, params?)` → GET
    - `revokeDispatchRecord(projectId, recordId)` → DELETE
    - 类型定义：DispatchEntry, DispatchRecord, BatchDispatchResponse
    - _Requirements: 1.1, 2.1, 6.1_

- [ ] 9. 改造 useConfirmationDispatch.ts
  - [ ] 9.1 接入后端 API 替代纯内存 dispatchedMap
    - `onMounted` → 调用 `listDispatchRecords` 初始化 dispatchedMap
    - `executeDispatch` → 调用 `batchCreateDispatch`，用 response 更新本地 Map（dispatched ∪ skipped）
    - 新增 `revokeDispatch` → 调用 `revokeDispatchRecord`，成功后从 Map 移除
    - 加载中禁用分发按钮 + loading 状态
    - 失败处理：ElMessage.warning + dispatchedMap 保持空/不变
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.2_
  - [ ]* 9.2 Property test: dispatchedMap reconstruction
    - **Property 5: DispatchedMap reconstruction from backend**
    - 使用 fast-check 生成随机 DispatchRecord[]，验证 Map 重建正确性
    - **Validates: Requirements 5.1**
  - [ ]* 9.3 Property test: pending list exclusion
    - **Property 6: Pending list exclusion**
    - 生成随机 rows + dispatchedMap，验证 pending 列表排除逻辑
    - **Validates: Requirements 4.2**
  - [ ]* 9.4 Property test: map sync after batch response
    - **Property 7: Map sync after batch response**
    - 生成随机 API response，验证 Map 包含 dispatched ∪ skipped
    - **Validates: Requirements 5.2, 5.3**
  - [ ]* 9.5 Property test: revoke restores pending eligibility
    - **Property 9: Revoke restores pending eligibility**
    - 生成 Map 状态 + revoke entry，验证移除后 pending 恢复
    - **Validates: Requirements 6.2**

- [ ] 10. 新建 useDownstreamDispatch.ts
  - [ ] 10.1 创建下游底稿通用 composable
    - 在 `audit-platform/frontend/src/composables/useDownstreamDispatch.ts`
    - `onMounted` → 调用 `listDispatchRecords(projectId, {target: selfTarget})` 加载分发记录
    - SSE 监听 `DISPATCH_CREATED` / `DISPATCH_REVOKED`，target 匹配时增量更新
    - 合并逻辑：跳过本地已存在 confirm_index 的行（前端去重）
    - 加载失败提示 + 不阻断底稿使用
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.2, 7.4_
  - [ ]* 10.2 Property test: downstream dedup merge
    - **Property 11: Downstream dedup merge**
    - 生成 dispatch records + local rows，验证 merge 只添加不重复的记录
    - **Validates: Requirements 3.3**
  - [ ]* 10.3 Property test: event target filtering
    - **Property 12: Event target filtering**
    - 生成 event + composable target，验证仅匹配 target 时触发刷新
    - **Validates: Requirements 7.2**

- [ ] 11. Final checkpoint - 全量验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端使用 Python (hypothesis for PBT)，前端使用 TypeScript (fast-check for PBT)
- Service 层只 flush 不 commit，commit 在 router 层执行
- EventBus publish 只传 EventPayload，遵循现有事件总线规范
- 迁移为 V092，接续当前最高 V091
- Property tests 使用 `@settings(max_examples=5)` 符合项目约定
