# Implementation Plan: editing-lock-v1-v2-consolidation

## Overview

按设计三阶段零停机方案推进编辑锁 v1→v2 收口。阶段 1 双端点并存（迁移 + v2 acquire 补同人续期 + force 条件化 SSE + 前端 flag 分流 + 测试），flag 默认关不影响现网；阶段 2 灰度 + Playwright 实测（门控阶段 3）；阶段 3 满足四门控后下线 v1。后端 Python（in-process ASGI httpx 直调 + hypothesis `max_examples=5`），前端 TS（vitest）。14 条 properties，每属性单测，注释标 `Feature: editing-lock-v1-v2-consolidation, Property {n}`。

铁律：三层一致（迁移 SQL + ORM Mapped + service）、service 只 flush / router 统一 commit、router_registry 必查、V*/R* 配对且幂等、PG-only SQL 加 dialect 跳过、event_bus `broadcast_raw` 走轻量 SSE、apiProxy 单层解构、mock 真实存在方法 + assert 验真调用禁 `try/except: pass`。

### 已实证锚点（实施直接用，行号为编写时值，以符号锚点为准）
- **v2 service** `backend/app/services/editing_lock_service_v2.py`：
  - `acquire_lock(db, resource_type, resource_id, holder_id, holder_name)` L58；活跃锁冲突 return 在 **L101-110**（`if active_lock is not None: return {"locked":True,...}`）——**同人续期分支插此 return 之前**；无锁建锁在 L112+（SAVEPOINT begin_nested）；`_now()` 返回值写 acquired_at/heartbeat_at
  - `heartbeat_lock` L193（`lock.heartbeat_at=now; return {"refreshed":True,...}`）；`release_lock` L164；`force_acquire_lock` L223（return 含 lock_id/previous_holder_id/previous_holder_name/acquired_at）
  - 有效锁定义：`released_at IS NULL AND heartbeat_at > now-5min`（L6 注释 + `_release_expired` L40+）
- **v2 router** `backend/app/routers/editing_locks.py`：前缀 `/api/editing-locks`；`force_acquire` 端点 **L123-140**，`await db.commit()` 在 **L138**（broadcast_raw 插其后）；acquire L51 / heartbeat L81 / release L102 / active L39
- **router_registry** `backend/app/router_registry/collaboration.py`：v2 注册 §12c **L119-120**（`editing_locks_router`，保留）；v1 注册 §13 **L126**（`from app.routers.editing_lock import router as editlock_router`，阶段3删）
- **v1 文件**（阶段3删）：service `backend/app/services/editing_lock_service.py`、router `backend/app/routers/editing_lock.py`、表 `workpaper_editing_locks`（列 wp_id/staff_id/acquired_at/heartbeat_at/released_at + TimestampMixin）；v1 测试 `backend/tests/test_editing_lock.py`、`test_editing_lock_concurrent.py`
- **前端** `audit-platform/frontend/src/composables/useEditingLock.ts`：`resourceType` L70、`isWorkpaper` L71、`isGenericLock` L74；workpaper 分支端点——acquire L99 `POST /api/workpapers/{id}/editing-lock`、release L129 `DELETE`、heartbeat L148 `PATCH .../heartbeat`（**workpaper 分支当前无 force**）；generic 分支走 `/api/editing-locks/{resourceType}/{id}`；`EditingLockTakenOverPayload` L40（wp_id 字段）；当前**无 feature flag**
- **当前最高迁移 V072** → 本特性用 V073（数据迁移）+ V074（阶段3下线表）
- 迁移执行模型：V*.sql 仅真实 PG 启动由 MigrationRunner 加载，测试 fixture（SQLite in-memory create_all）不加载→迁移类测试必标 `pg_only`

## Tasks

### 阶段 1：双端点并存 + 迁移 + 灰度（可独立交付，不影响现网）

- [ ] 1. 数据迁移 V073 / R073（存量活跃锁迁入 editing_locks）
  - [x] 1.1 编写 `backend/migrations/V073__migrate_workpaper_locks_to_editing_locks.sql`
    - 源 `workpaper_editing_locks` 仅迁 `released_at IS NULL` 活跃锁；`INSERT INTO editing_locks(...)` 字段映射：`resource_type='workpaper'`、`resource_id=wp_id::text`、`holder_id=staff_id`、保留 `acquired_at`/`heartbeat_at`
    - `holder_name` 经 `LEFT JOIN users ON staff_id=users.id` 回填（COALESCE full_name/username），无则 NULL
    - 同 wp_id 多活跃锁：`DISTINCT ON (wp_id) ... ORDER BY wp_id, heartbeat_at DESC` 取最新
    - **时区规整（实施前必实测）**：先在真实 PG 跑 `SHOW timezone` + `SELECT heartbeat_at, heartbeat_at AT TIME ZONE 'UTC' FROM workpaper_editing_locks LIMIT 5` 确认偏移方向，再定规整表达式（**勿武断 `AT TIME ZONE 'UTC'`**，对 timestamptz 列方向可能反）；v1 写入与 session 均 UTC 无偏移则直接平移
    - 幂等：`WHERE NOT EXISTS (SELECT 1 FROM editing_locks WHERE resource_type='workpaper' AND resource_id=wp_id::text AND released_at IS NULL)` + `uq_editing_locks_active` 部分唯一索引兜底
    - 显式写 `created_at`/`updated_at = now()`（TimestampMixin NOT NULL）
    - 只读源表，不 UPDATE/DELETE `workpaper_editing_locks`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 6.4 / Properties: 1, 2, 3, 14_
  - [x] 1.2 编写 `backend/migrations/R073__migrate_workpaper_locks_to_editing_locks.sql`
    - `DELETE FROM editing_locks WHERE resource_type='workpaper'`（仅清迁入数据，不动其它 resource_type）；无匹配静默成功
    - _Requirements: 1.6_
  - [x]* 1.3 迁移字段映射属性测试（pg_only）
    - **Property 1: 迁移字段映射正确性** — **Validates: 1.1, 1.2, 1.3**
    - 新建 `backend/tests/migrations/test_v073_migrate_locks.py`，标 `pg_only`；用 MigrationRunner 在真实 PG 跑 V073 后断言；`max_examples=5`；随机源活跃锁（部分 staff_id 有/无 user），断言映射+时间保留+holder_name 回填；注释标 Property 1
  - [x]* 1.4 迁移去重+幂等属性测试（pg_only）
    - **Property 2: 迁移后同资源活跃锁唯一** — **Validates: 1.4, 1.5**
    - 同文件；`max_examples=5`；同 wp_id 多活跃锁 + 跑 1/2 次，断言活跃锁=1 且保留 heartbeat 最新；标 Property 2 / `pg_only`
  - [x]* 1.5 迁移非破坏性属性测试（pg_only）
    - **Property 3: 迁移非破坏性** — **Validates: 6.4**
    - 迁移前后 `workpaper_editing_locks` 全行快照断言相等；标 Property 3 / `pg_only` / `max_examples=5`
  - [x]* 1.6 迁移单元测试（已知 example + 幂等 + 边界，pg_only）
    - 已知源数据断言字段精确匹配；重复执行断言活跃锁=1；边界：空 holder_name、staff_id 无对应 user
    - _Requirements: 8.2, 8.3_
  - [x]* 1.7 迁移时区规整属性测试（pg_only）
    - **Property 14: 迁移时区规整后过期判定一致** — **Validates: 1.2**
    - 生成 naive heartbeat_at 跨过期窗口（窗口内/外）源锁→迁移→断言迁后 v2 `heartbeat_at>now-5min` 活跃判定与源语义一致；标 Property 14 / `pg_only` / `max_examples=5`

- [ ] 1b. v2 acquire_lock 补"同人重复 acquire 自动续期"（对齐 v1）
  - [x] 1b.1 改 `editing_lock_service_v2.py` `acquire_lock`（L101 冲突 return 之前插同人分支）
    - 在 L101 `if active_lock is not None:` 块内、`return {"locked":True,...}` **之前**插入：`if active_lock.holder_id == holder_id:` → `active_lock.heartbeat_at = _now(); await db.flush(); return {"locked": False, "lock_id": str(active_lock.id), "acquired_at": active_lock.acquired_at.isoformat() if active_lock.acquired_at else ""}`
    - 仅他人持锁才走原 `return {"locked":True,...}`（router L69 转 409）
    - 保持 service 只 flush 不 commit（commit 由 router L66 统一做）
    - _Requirements: 3.2a / Properties: 13_
  - [x]* 1b.2 同人 acquire 续期属性测试
    - **Property 13: 底稿锁同人重复 acquire 续期** — **Validates: 3.2a**
    - 新建 `backend/tests/services/test_editing_lock_v2_renewal.py`（SQLite 可跑）；持锁后同人再 acquire → 断言 locked=False + 活跃锁=1 + heartbeat 刷新；他人 acquire → 409；标 Property 13 / `max_examples=5`

- [ ] 2. v2 force 端点补 emit `editing_lock.force_acquired` SSE
  - [x] 2.1 `editing_locks.py` `force_acquire`（L138 `await db.commit()` 之后）插 broadcast_raw
    - `db.commit()` 后：`from app.services.event_bus import event_bus`（**实证统一路径，非 app.utils**）
    - **project_id 解析**：broadcast_raw 的 SSE 队列路由依赖 `extra["project_id"]`（与现有 `report.stale`/`note.synced` 等惯例一致）。force 端点按 resource_id 解析——`resource_type=='workpaper'` 时查 `WorkingPaper.project_id`（resource_id=WorkingPaper.id，`WorkingPaper` 有 project_id 列）；非 workpaper（disclosure_note/audit_report）按对应资源查 project_id（解析失败则置 None，best-effort）
    - 构造 payload `{project_id: str|None, resource_type, resource_id, new_holder_id:str(current_user.id), new_holder_name:_holder_name(current_user), previous_holder_id: result.get("previous_holder_id")}`
    - **wp_id 条件化**：`if resource_type == 'workpaper': payload["wp_id"] = resource_id`（前端 `useEditingLock` 实证只按 `wp_id` 匹配强抢事件，故 workpaper 必须带 wp_id；非 workpaper 不塞）
    - `event_bus.broadcast_raw('editing_lock.force_acquired', payload)`；best-effort 包 try，except 记 `logger.warning`（**禁 `try/except: pass` 静默**）
    - _Requirements: 5.1, 5.2 / Properties: 10_
  - [x]* 2.2 force SSE 事件属性测试
    - **Property 10: force-acquire SSE 事件完整性** — **Validates: 5.1, 5.2**
    - 新建 `backend/tests/routers/test_editing_locks_force_sse.py`；mock `event_bus.broadcast_raw`（真实方法）`assert_called_once` + payload 字段完整（project_id/resource_type/resource_id/new_holder_id/previous_holder_id）且 workpaper 时 `wp_id==resource_id` + `project_id` 等于该 wp 所属项目；禁 `try/except:pass`；标 Property 10 / `max_examples=5`
  - [x]* 2.3 force SSE 单元测试（payload 精确匹配）
    - in-process ASGI httpx 直调 `POST /api/editing-locks/workpaper/{id}/force`，assert broadcast_raw 参数精确（含 project_id 来自 WorkingPaper）；非 workpaper resource_type 断言无 wp_id 键
    - _Requirements: 5.1, 5.2_

- [ ] 3. v2 service 承载 workpaper 锁等价测试（替换待下线 v1 测试覆盖）
  - [x]* 3.1 底稿锁 acquire 创建属性测试
    - **Property 4** — **Validates: 3.1**；in-process httpx `POST /api/editing-locks/workpaper/{id}`，无锁→活跃锁=1 且 locked=False；标 Property 4 / `max_examples=5`
  - [x]* 3.2 底稿锁 acquire 冲突属性测试
    - **Property 5** — **Validates: 3.2**；他人持锁→409 + 持有者信息；标 Property 5 / `max_examples=5`
  - [x]* 3.3 底稿锁 heartbeat 续期属性测试
    - **Property 6** — **Validates: 3.3**；持锁 heartbeat→heartbeat_at 增大 + refreshed=True；标 Property 6 / `max_examples=5`
  - [x]* 3.4 底稿锁 heartbeat 无锁失败属性测试
    - **Property 7** — **Validates: 3.4**；无锁 heartbeat→404（refreshed=False）；标 Property 7 / `max_examples=5`
  - [x]* 3.5 底稿锁 release 释放属性测试
    - **Property 8** — **Validates: 3.5**；持锁 release→released_at 设置 + 无活跃锁；标 Property 8 / `max_examples=5`
  - [x]* 3.6 底稿锁 force 抢占属性测试
    - **Property 9** — **Validates: 3.6**；他人持锁 force→新持有者唯一 + previous_holder_id 正确；标 Property 9 / `max_examples=5`
  - [x]* 3.7 v2 workpaper 锁并发 + 边界单元测试
    - 并发 acquire（SELECT FOR UPDATE + begin_nested SAVEPOINT）等价 v1 `test_editing_lock_concurrent.py`——**真实并发冲突分支标 `pg_only`**（SQLite 忽略 FOR UPDATE、SAVEPOINT 语义差异，无法真验唯一索引冲突）
    - 边界：空 holder_name（可 SQLite）；service 只 flush 由 router 统一 commit
    - _Requirements: 3.7, 8.1_

- [ ] 4. 前端 useEditingLock workpaper 分支按 feature flag 分流 v1/v2
  - [x] 4.1 改 `useEditingLock.ts`（L70-74 分支判定 + L75/114/135 三函数 workpaper 端点）
    - 顶部从 `useFeatureFlags()` 取 `isEnabled('editing_lock_v2_workpaper')` → `v2Enabled`（本地兜底 false）；**注意实证铁律**：`useFeatureFlags.isEnabled` 实测只读全局 `enabled` 布尔，不消费 rollout_percentage/whitelist（百分比灰度需后端下沉，不在本任务范围）
    - 新增 workpaper 端点构造：`isWorkpaper && v2Enabled` → `/api/editing-locks/workpaper/{id}`（+`/heartbeat`、`/force`、DELETE）；否则原 `/api/workpapers/{id}/editing-lock` 系列
    - acquire（L99）/ release（L129）/ heartbeat（L148）三处 workpaper 端点据 flag 切换；补 workpaper 的 force（当前缺）走对应端点
    - **flag 竞态防护**：`onMounted` acquire 前 await `v2Enabled` 解析完成；单锁生命周期（acquire→heartbeat→release）冻结首次 acquire 的 `v2Enabled` 快照不中途重读（防 acquire 走 v2 / release 走 v1 跨表泄漏）
    - 不改调用方组件参数（仍传 `resourceType:'workpaper'`）；apiProxy 单层解构
    - _Requirements: 4.1, 4.2, 4.3, 4.3a / Properties: 11_
  - [x]* 4.2 flag 路由属性测试（vitest）
    - **Property 11: 前端按 Rollout_Flag 路由底稿锁端点** — **Validates: 4.1, 4.2**
    - 新建 `useEditingLock.spec.ts`；mock `useFeatureFlags`（真实方法）+ `api`，flag on/off × acquire/heartbeat/release/force 断言 URL 前缀；assert 验真调用禁 `try/except:pass`；标 Property 11 / `numRuns=5`
  - [x]* 4.3 强抢状态更新属性测试（vitest）
    - **Property 12: 前端强抢状态更新** — **Validates: 5.3**
    - 随机持锁状态 + 匹配/不匹配 `editing_lock.force_acquired` 事件，断言 isMine/lockedBy 更新；非匹配/非持锁不变；标 Property 12 / `numRuns=5`

- [ ] 5. 阶段 1 双端点并存可用性验证
  - [x]* 5.1 双端点并存测试
    - in-process httpx 断言 v1 `/api/workpapers/{id}/editing-lock` 与 v2 `/api/editing-locks/workpaper/{id}` 两路由均非 404
    - _Requirements: 6.1, 6.2_

- [ ] 6. 阶段 1 检查点
  - 跑 `python -m pytest backend/tests/services/test_editing_lock_v2_renewal.py backend/tests/routers/test_editing_locks_force_sse.py` + 前端 vitest；非 pg_only 全绿、pg_only 在真实 PG 跑过再继续。有问题问用户。

### 阶段 2：前端全量切 v2 + 实测（门控阶段 3）

- [x]* 7. Playwright 全链路实测（需真实环境）
  - 灰度提至 100% 后进底稿编辑，验证 acquire→heartbeat→release→force 全链路成功
  - 两用户并发验证强抢通知（`editing_lock.force_acquired` SSE）到达原持有者
  - _Requirements: 4.4, 6.1, 6.2_

- [x]* 8. 存量数据迁移核对（需真实环境）
  - 真实 DB 核对 V073 迁后 `editing_locks` 中 workpaper 锁与源表活跃锁一致、活跃锁数匹配去重预期
  - _Requirements: 1.1, 1.4, 7.1_

### 阶段 3：下线 v1（前置：阶段 2 四门控全满足）

- [x] 9. 移除 v1 router 注册
  - 删 `backend/app/router_registry/collaboration.py` §13 L126 的 `from app.routers.editing_lock import router as editlock_router` + 对应 `app.include_router(editlock_router...)`；保留 §12c L119-120 v2 注册
  - _Requirements: 7.1_

- [x] 10. 删除 v1 service 与 router 文件
  - 删 `backend/app/services/editing_lock_service.py`、`backend/app/routers/editing_lock.py`
  - codegraph `codegraph_callers`/grep 确认无残留 import（含 router_registry 外的引用）
  - _Requirements: 7.2_

- [ ] 11. V075 / R075 下线 v1 表（⚠️ V074 已被 note-guidance-text-separation 占用 `V074__disclosure_notes_guidance_text.sql`，本特性下线表改用 V075/R075，避免同号静默丢失）
  - [x] 11.1 `backend/migrations/V075__drop_workpaper_editing_locks.sql`：`DROP TABLE IF EXISTS workpaper_editing_locks`
    - _Requirements: 7.3_
  - [x] 11.2 `backend/migrations/R075__drop_workpaper_editing_locks.sql`：`CREATE TABLE IF NOT EXISTS workpaper_editing_locks(...)` 重建（含 wp_id/staff_id/acquired_at/heartbeat_at/released_at + `created_at`/`updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`）
    - **注**：R074 重建空表仅为迁移系统 V/R 配对完整性要求，**单跑 R074 不能恢复 v1 功能**——v1 service/router/注册已在任务 9/10 删除，真正回退到阶段 3 之前还须配合 git revert 代码 + 恢复 V073 迁入的锁数据。避免"跑 R074 即回滚 v1"的错觉。
    - _Requirements: 7.3_

- [x] 12. 移除 v1 测试
  - 删 `backend/tests/test_editing_lock.py`、`test_editing_lock_concurrent.py`
  - 确认任务 3 的 v2 等价测试已覆盖 acquire/heartbeat/release/force/并发，覆盖不降低
  - _Requirements: 8.1, 8.5_

- [x] 12b. 前端移除 v1 回退分支（避免下线后 404）
  - 改 `useEditingLock.ts`：删 workpaper 的 v1 端点分支，`v2Enabled` 默认改 true（或直接移除分流、workpaper 统一走 `/api/editing-locks/workpaper/{id}`）
  - 确保 flag 端点读失败时无任何代码路径指向已删 v1 `/api/workpapers/{id}/editing-lock`
  - 精简 Property 11 测试（v1 分支已不存在）
  - _Requirements: 6.3a_

- [x] 13. 阶段 3 最终检查点
  - 跑全量后端测试 + 前端 vitest；全绿再收尾。有问题问用户。

## Notes

- 标 `*` 子任务为可选（测试/需真实环境）；核心实现任务不标 `*`。任务 7、8 依赖灰度+多用户并发，不在 in-process 范围。
- 阶段 1 可独立交付，flag 默认关不影响现网；阶段 3 仅在四门控（前端全量切 v2 / 存量核对 / Playwright 全链路 / 测试覆盖迁移）全满足后执行（需求 7.4）。
- pg_only：迁移类（Property 1/2/3/14 + 任务 1.3-1.7）+ 并发冲突分支（3.7）标 `pg_only`（V*.sql 仅真实 PG 跑，fixture SQLite 不加载）；v2 锁行为类（Property 4-9/13）+ 前端（11/12）走 SQLite/vitest。
- 每条 Property 单测，注释标 Feature + Property number；mock 真实存在方法 + assert 验真调用，禁 `try/except: pass`。
- V073/V074 均配对 R 脚本，插入/建表用 `WHERE NOT EXISTS`/`IF NOT EXISTS` 幂等。
- 行号为编写时实证值，实施以最近符号锚点为准。
