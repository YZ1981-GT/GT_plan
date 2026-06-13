# Implementation Plan: editing-lock-v1-v2-consolidation

## Overview

按设计的三阶段零停机方案推进编辑锁 v1→v2 收口。阶段 1 双端点并存（迁移 + v2 acquire 补同人续期 + force 条件化 SSE emit + 前端 flag 分流 + 等价/迁移测试），可独立交付不影响现网；阶段 2 灰度提升 + Playwright 实测（门控阶段 3）；阶段 3 满足四门控后下线 v1。后端 Python（in-process ASGI httpx 直调端点 + hypothesis `max_examples=5`），前端 TypeScript（vitest）。共 14 条 correctness properties，每个属性测试为单个测试，注释标 `Feature: editing-lock-v1-v2-consolidation, Property {n}`。

遵循铁律：三层一致（迁移 SQL + ORM `Mapped[]` + service）、service 只 flush 不 commit / router 统一 commit、router_registry 必查、V073/V074 配对 R 脚本且 `IF NOT EXISTS`/幂等、PG-only SQL 加 SQLite dialect 跳过、event_bus `broadcast_raw` 走轻量 SSE、apiProxy 单层解构、mock 真实存在方法并 assert 验真调用禁 `try/except: pass`。

## Tasks

### 阶段 1：双端点并存 + 迁移 + 灰度（可独立交付，不影响现网）

- [ ] 1. 数据迁移脚本 V073 / R073（存量活跃锁迁入 editing_locks）
  - [ ] 1.1 编写 `backend/migrations/V073__migrate_workpaper_locks_to_editing_locks.sql`
    - 只迁 `workpaper_editing_locks` 中 `released_at IS NULL` 的活跃锁
    - 字段映射：`resource_type='workpaper'`、`resource_id = wp_id::text`、`holder_id = staff_id`，保留 `acquired_at`/`heartbeat_at`
    - `holder_name` 经 `LEFT JOIN users ON staff_id=users.id` 回填（full_name/username），无则 NULL
    - 同 `wp_id` 多活跃锁用 `DISTINCT ON (wp_id) ... ORDER BY wp_id, heartbeat_at DESC` 取最新一条
    - **时区规整**：v1 用 naive UTC（`_now_naive()`）写 acquired_at/heartbeat_at 进 timestamptz 列（被 PG 按 session tz 解释）。**迁移前先实测**：`SHOW timezone` + `SELECT heartbeat_at, heartbeat_at AT TIME ZONE 'UTC' FROM workpaper_editing_locks LIMIT 5` 确认偏移方向，再定规整表达式（**勿武断写 `AT TIME ZONE 'UTC'`**，对 timestamptz 列方向可能反）；若实测 v1 写入与 session 均 UTC 无偏移则直接平移。目标：迁后锁在 v2 `heartbeat_at>now-5min` 判定下不被误判过期/永不过期
    - 幂等：`WHERE NOT EXISTS`（目标表已有同 `(resource_type,resource_id)` 活跃锁则跳过）+ `uq_editing_locks_active` 部分唯一索引兜底
    - 显式写入 `created_at`/`updated_at` 为 `now()`（TimestampMixin 列 NOT NULL）
    - 只读源表，不 UPDATE/DELETE `workpaper_editing_locks` 任何行
    - PG-only 执行模型（已实证）：V*.sql 仅真实 PG 启动时由 MigrationRunner 加载，测试 fixture（SQLite in-memory）用 create_all 不加载迁移→V073 含 `DISTINCT ON`/`::text` 无需 dialect 跳过分支（MigrationRunner 无此分支也不需要）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 6.4 / Properties: 1, 2, 3, 14_
  - [ ] 1.2 编写配对回退脚本 `backend/migrations/R073__migrate_workpaper_locks_to_editing_locks.sql`
    - 删除 V073 迁入的记录：`DELETE FROM editing_locks WHERE resource_type='workpaper'`（仅清理迁入数据，不动其它 resource_type）
    - 幂等保护：删除无匹配行时静默成功
    - _Requirements: 1.6_
  - [ ]* 1.3 编写迁移正确性属性测试（字段映射）
    - **Property 1: 迁移字段映射正确性**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 1`
    - **标 `pg_only`**（V073 是 PG-only SQL，conftest 对非 PG 自动 skip；用 MigrationRunner 在真实 PG 跑 V073 后断言）
    - hypothesis `max_examples=5`；生成随机源活跃锁集合（部分 staff_id 有/无对应 user），断言映射 + 时间保留 + holder_name 回填
  - [ ]* 1.4 编写迁移去重+幂等属性测试
    - **Property 2: 迁移后同资源活跃锁唯一（去重 + 幂等）**
    - **Validates: Requirements 1.4, 1.5**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 2`；**标 `pg_only`**
    - hypothesis `max_examples=5`；生成同 wp_id 多活跃锁 + 随机执行 1/2 次，断言活跃锁=1 且保留 heartbeat_at 最新者
  - [ ]* 1.5 编写迁移非破坏性属性测试
    - **Property 3: 迁移非破坏性**
    - **Validates: Requirements 6.4**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 3`；**标 `pg_only`**
    - hypothesis `max_examples=5`；迁移前后对 `workpaper_editing_locks` 行快照断言相等
  - [ ]* 1.6 编写迁移单元测试（已知数据 example + 幂等 example）
    - 构造已知源数据断言迁移结果字段值精确匹配（与 Property 1/2 互补）
    - 重复执行迁移断言活跃锁=1（需求 8.3）
    - 边界：空 holder_name、无对应 user 的 staff_id
    - **标 `pg_only`**（同上，迁移只在真实 PG 跑）
    - _Requirements: 8.2, 8.3_
  - [ ]* 1.7 编写迁移时区规整属性测试
    - **Property 14: 迁移时区规整后过期判定一致**
    - **Validates: Requirements 1.2**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 14`；hypothesis `max_examples=5`；**标 `pg_only`**
    - 生成 naive heartbeat_at 跨过期窗口（窗口内/外）的源锁→迁移→断言迁后 v2 活跃判定与源语义一致

- [ ] 1b. v2 acquire_lock 补"同人重复 acquire 自动续期"分支（行为对齐 v1）
  - [ ] 1b.1 改造 `backend/app/services/editing_lock_service_v2.py` 的 `acquire_lock`
    - 在"查到活跃锁"分支前插入同人判断：若 `active_lock.holder_id == holder_id` → 刷新 `heartbeat_at` + flush，返回 `{"locked": False, "lock_id": str(active_lock.id), "acquired_at": ...}`
    - 仅当持有人为**他人**时才返回 `locked=True`（router 转 409）
    - 保持 service 只 flush 不 commit
    - _Requirements: 3.2a / Properties: 13_
  - [ ]* 1b.2 编写同人 acquire 续期属性测试
    - **Property 13: 底稿锁同人重复 acquire 续期（不冲突）**
    - **Validates: Requirements 3.2a**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 13`；hypothesis `max_examples=5`
    - 持锁后同人再 acquire → 断言 locked=False + 活跃锁数=1 + heartbeat 刷新（区别于他人 acquire 的 409）

- [ ] 2. v2 force 端点补 emit `editing_lock.force_acquired` SSE
  - [ ] 2.1 在 `backend/app/routers/editing_locks.py` 的 force 端点补 broadcast_raw
    - force-acquire `await db.commit()` 后调 `event_bus.broadcast_raw('editing_lock.force_acquired', {...})`
    - **`wp_id` 字段条件化**：仅当 `resource_type == 'workpaper'` 时填 `wp_id = resource_id`，其它 resource_type 省略/置 null（不把非底稿 resource_id 塞进 wp_id）
    - `resource_type`、`resource_id`、`new_holder_id`、`new_holder_name`、`previous_holder_id` 始终填
    - 用 broadcast_raw（轻量 SSE，不触发 _handlers）；广播失败 best-effort 不阻断 DB 操作
    - _Requirements: 5.1, 5.2 / Properties: 10_
  - [ ]* 2.2 编写 force SSE 事件属性测试
    - **Property 10: force-acquire SSE 事件完整性**
    - **Validates: Requirements 5.1, 5.2**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 10`
    - hypothesis `max_examples=5`；mock `broadcast_raw`（真实存在方法）用 `assert` 验恰调用一次 + payload 三字段完整且 `wp_id==resource_id`；禁 `try/except: pass`
  - [ ]* 2.3 编写 force SSE 单元测试（payload 字段值精确匹配 example）
    - in-process ASGI httpx 直调 force 端点，assert broadcast_raw 调用参数精确匹配
    - _Requirements: 5.1, 5.2_

- [ ] 3. v2 service 承载 workpaper 锁的等价测试（替换待下线的 v1 测试覆盖）
  - [ ]* 3.1 编写底稿锁 acquire 属性测试
    - **Property 4: 底稿锁 acquire 创建**
    - **Validates: Requirements 3.1**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 4`；hypothesis `max_examples=5`
    - in-process ASGI httpx 直调 `POST /api/editing-locks/workpaper/{id}`，断言无锁→活跃锁=1 且 locked=False
  - [ ]* 3.2 编写底稿锁 acquire 冲突属性测试
    - **Property 5: 底稿锁 acquire 冲突**
    - **Validates: Requirements 3.2**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 5`；hypothesis `max_examples=5`
    - 他人持锁→断言 HTTP 409 + 持有者信息
  - [ ]* 3.3 编写底稿锁 heartbeat 续期属性测试
    - **Property 6: 底稿锁 heartbeat 续期**
    - **Validates: Requirements 3.3**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 6`；hypothesis `max_examples=5`
    - 持锁 heartbeat→断言 heartbeat_at 增大 + refreshed=True
  - [ ]* 3.4 编写底稿锁 heartbeat 无锁失败属性测试
    - **Property 7: 底稿锁 heartbeat 无锁失败**
    - **Validates: Requirements 3.4**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 7`；hypothesis `max_examples=5`
    - 无锁 heartbeat→断言 HTTP 404（refreshed=False）
  - [ ]* 3.5 编写底稿锁 release 释放属性测试
    - **Property 8: 底稿锁 release 释放**
    - **Validates: Requirements 3.5**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 8`；hypothesis `max_examples=5`
    - 持锁 release→断言 released_at 设置 + 无活跃锁
  - [ ]* 3.6 编写底稿锁 force 抢占属性测试
    - **Property 9: 底稿锁 force 抢占**
    - **Validates: Requirements 3.6**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 9`；hypothesis `max_examples=5`
    - 他人持锁 force→断言新持有者唯一 + previous_holder_id 正确
  - [ ]* 3.7 编写 v2 workpaper 锁并发 + 边界单元测试
    - 并发 acquire（SELECT FOR UPDATE + SAVEPOINT）等价 v1 `test_editing_lock_concurrent.py` 覆盖——**真实并发冲突分支标 `pg_only`**（SQLite 忽略 FOR UPDATE、SAVEPOINT 语义有差异，无法真验唯一索引冲突）
    - 边界：同一用户重复 acquire 的等价语义、空 holder_name（可 SQLite）
    - service 只 flush 不 commit 由 router 统一 commit 验证
    - _Requirements: 3.7, 8.1_

- [ ] 4. 前端 useEditingLock workpaper 分支按 feature flag 分流 v1/v2
  - [ ] 4.1 改造 `audit-platform/frontend/src/composables/useEditingLock.ts`
    - 初始化时从 `useFeatureFlags().isEnabled('editing_lock_v2_workpaper')` 解析 `v2Enabled`，本地兜底默认 false
    - workpaper 分支 URL 构造改为：`isWorkpaper && v2Enabled` → `/api/editing-locks/workpaper/{id}` 系列；否则 `/api/workpapers/{id}/editing-lock` 系列
    - acquire/heartbeat/release/force 四操作均据 flag 切换端点
    - **flag 竞态防护**：`onMounted` 的 acquire 必须 await `v2Enabled` 解析完成再发请求；单个锁生命周期（acquire→heartbeat→release）锁定首次 acquire 时冻结的 `v2Enabled` 快照，不中途重读（防 acquire 走 v2/release 走 v1 跨表锁泄漏）
    - 不修改调用方组件参数（仍传 `resourceType:'workpaper'`）
    - apiProxy 单层解构（`api.post/patch/delete` 已返业务数据）
    - _Requirements: 4.1, 4.2, 4.3, 4.3a / Properties: 11_
  - [ ]* 4.2 编写 flag 路由属性测试（vitest）
    - **Property 11: 前端按 Rollout_Flag 路由底稿锁端点**
    - **Validates: Requirements 4.1, 4.2**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 11`
    - mock `useFeatureFlags`（真实存在方法）+ `api`，flag on/off × 四操作断言 URL 前缀；用 assert 验真调用，禁 `try/except: pass`
  - [ ]* 4.3 编写强抢状态更新属性测试（vitest）
    - **Property 12: 前端强抢状态更新**
    - **Validates: Requirements 5.3**
    - 单个属性=单个测试；注释标 `Feature: editing-lock-v1-v2-consolidation, Property 12`
    - 随机持锁状态 + 匹配/不匹配 `editing_lock.force_acquired` 事件，断言 isMine/lockedBy 更新；非匹配/非持锁不变

- [ ] 5. 阶段 1 双端点并存可用性验证
  - [ ]* 5.1 编写双端点并存可用性测试
    - in-process ASGI httpx 断言 v1 `/api/workpapers/{id}/editing-lock` 与 v2 `/api/editing-locks/workpaper/{id}` 两路由均非 404
    - _Requirements: 6.1, 6.2_

- [ ] 6. 阶段 1 检查点
  - Ensure all tests pass, ask the user if questions arise.

### 阶段 2：前端全量切 v2 + 实测（门控阶段 3）

- [ ]* 7. Playwright 全链路实测（需真实环境）
  - 灰度提升至 100% 后进入底稿编辑，验证 acquire → heartbeat → release → force-acquire 全链路成功
  - 两个用户并发验证强抢通知（`editing_lock.force_acquired` SSE）到达原持有者
  - _Requirements: 4.4, 6.1, 6.2_

- [ ]* 8. 存量数据迁移核对（需真实环境）
  - 在真实 DB 核对 V073 迁移后 `editing_locks` 中 workpaper 锁与源表活跃锁一致、活跃锁数量匹配去重预期
  - _Requirements: 1.1, 1.4, 7.1_

### 阶段 3：下线 v1（前置：阶段 2 四门控全满足）

- [ ] 9. 移除 v1 router 注册
  - 删除 `backend/app/router_registry/collaboration.py` §13 的 v1 `editing_lock` router 注册
  - 保留 §12c 的 v2 注册不动
  - _Requirements: 7.1_

- [ ] 10. 删除 v1 service 与 router 文件
  - 删除 `backend/app/services/editing_lock_service.py`
  - 删除 `backend/app/routers/editing_lock.py`
  - grep 确认无残留 import 引用（codegraph 优先核对调用链）
  - _Requirements: 7.2_

- [ ] 11. V074 / R074 下线 v1 表
  - [ ] 11.1 编写 `backend/migrations/V074__drop_workpaper_editing_locks.sql`
    - `DROP TABLE IF EXISTS workpaper_editing_locks`
    - PG-only 必要时加 SQLite dialect 跳过
    - _Requirements: 7.3_
  - [ ] 11.2 编写配对回退脚本 `backend/migrations/R074__drop_workpaper_editing_locks.sql`
    - `CREATE TABLE IF NOT EXISTS workpaper_editing_locks (...)` 重建表结构（含 wp_id/staff_id/acquired_at/heartbeat_at/released_at + TimestampMixin 列 `created_at`/`updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`）
    - _Requirements: 7.3_

- [ ] 12. 移除/迁移 v1 测试
  - 删除 `backend/tests/test_editing_lock.py` 与 `backend/tests/test_editing_lock_concurrent.py`
  - 确认任务 3 的 v2 等价测试已覆盖 acquire/heartbeat/release/force/并发，测试覆盖不降低
  - _Requirements: 8.1, 8.5_

- [ ] 12b. 前端移除 v1 回退分支（避免下线后 404）
  - 改 `useEditingLock.ts`：删除 workpaper 的 v1 端点分支，`v2Enabled` 默认改 true（或直接移除分流、workpaper 统一走 `/api/editing-locks/workpaper/{id}`）
  - 确保 flag 端点读失败时不再有任何代码路径指向已删除的 v1 `/api/workpapers/{id}/editing-lock`
  - 更新/精简 Property 11 的 flag 路由测试（v1 分支已不存在）
  - _Requirements: 6.3a_

- [ ] 13. 阶段 3 最终检查点
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标 `*` 的子任务为可选（测试 / 需真实环境），核心实现任务不标 `*`；标 `*` 且注明"需真实环境"的（任务 7、8）依赖灰度环境与多用户并发，不在 in-process 测试范围。
- 阶段 1 可独立交付，flag 默认关闭不影响现网；阶段 3 仅在前端全量切 v2、存量数据核对、Playwright 全链路通过、测试覆盖迁移完成四门控全满足后执行（需求 7.4）。
- 后端属性测试分两类执行环境：迁移类（Property 1/2/3/14）+ 并发冲突分支标 `pg_only`（V073 是 PG-only SQL，测试 fixture 用 SQLite in-memory 不加载迁移，只真实 PG 跑）；v2 锁行为类（Property 4-9/13）走 SQLite in-memory ORM 路径即可。前端用 vitest。
- 每条 Correctness Property 由单个属性测试实现，注释标 Feature + Property number。
- V073/V074 均配对 R 脚本，建表/插入用 `IF NOT EXISTS` 或 `WHERE NOT EXISTS` 幂等保护。
