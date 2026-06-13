# Requirements Document

## Introduction

审计作业平台当前存在两套并存且均为现役的编辑软锁实现：

- **v1（底稿专用锁）**：service `editing_lock_service`、router `editing_lock.py`（前缀 `/api/workpapers`）、表 `workpaper_editing_locks` / ORM `WorkpaperEditingLock`，以 `wp_id` 为锁维度，持有者字段 `staff_id`，`wp_id` 有 FK 约束指向 `working_paper.id`。仅底稿编辑器 `WorkpaperEditor.vue` 使用。
- **v2（通用资源锁）**：service `editing_lock_service_v2`、router `editing_locks.py`（前缀 `/api/editing-locks`）、表 `editing_locks` / ORM `EditingLock`，以 `(resource_type, resource_id)` 为锁维度，部分唯一索引 `uq_editing_locks_active` 保证同资源活跃锁 ≤ 1，持有者字段 `holder_id` + `holder_name`，`resource_id` 为纯字符串无 FK。附注编辑器、审计报告编辑器使用。

前端 composable `useEditingLock.ts` 按 `resourceType` 分流：`workpaper` 走 v1 专用端点，其它资源走 v2 通用端点。两个 router 都在 `backend/app/router_registry/collaboration.py` 注册（§12c 注册 v2，§13 注册 v1）。

本特性的目标是把 v1 的行为收口并入 v2 的 `resource_type='workpaper'`，统一到通用锁端点，迁移存量锁数据，改造前端分流逻辑使底稿锁也走 v2，最终下线 v1 的 service、router 与表，且整个过程满足零停机与向后兼容。

### 收口目标（Migration Goals）

1. 把 v1 底稿锁的全部行为（acquire / heartbeat / release / force-acquire / 活跃锁列表）通过 v2 的 `resource_type='workpaper'` 提供等价能力。
2. 将 `workpaper_editing_locks` 存量活跃锁迁移到 `editing_locks`。
3. 切换前端 `useEditingLock` 的 workpaper 分支到 v2 通用端点。
4. 保持 force-acquire SSE 通知字段对前端的兼容。
5. 在迁移与灰度验证完成后下线 v1 的 service、router 与表。
6. 迁移或替换 v1 的测试，保持锁功能测试覆盖不降低。

### 向后兼容与灰度策略（Backward Compatibility & Rollout）

- **灰度切换点**：以可配置开关（环境变量 / feature flag）控制前端 `useEditingLock` 的 workpaper 分支走 v1 还是 v2 端点，默认 v1，灰度阶段切 v2。
- **双端点并存窗口**：灰度期间 v1 与 v2 端点同时可用，v1 router 保留至 v2 路径验证通过。
- **回退方案**：灰度中若发现底稿锁异常，将开关切回 v1 端点即可恢复，数据迁移采用幂等可重跑的方式，不破坏 v1 表数据。
- **下线条件**：v1 下线仅在前端全量切换 v2、存量数据迁移完成核对、Playwright 全链路实测通过、测试覆盖迁移完成后执行。

## Glossary

- **Editing_Lock_System**：编辑软锁的逻辑系统总称，迁移后由 v2 通用实现统一承载。
- **V1_Service**：底稿专用锁服务 `editing_lock_service`（表 `workpaper_editing_locks`）。
- **V2_Service**：通用资源锁服务 `editing_lock_service_v2`（表 `editing_locks`）。
- **Migration_Script**：将 `workpaper_editing_locks` 存量锁迁移到 `editing_locks` 的迁移脚本（V073 配对 V073/R073）。
- **Active_Lock**：满足 `released_at IS NULL AND heartbeat_at > now - 5min` 的有效锁。
- **Workpaper_Lock**：迁移后 `editing_locks` 表中 `resource_type='workpaper'` 的锁记录。
- **Frontend_Composable**：前端编辑锁 composable `useEditingLock.ts`。
- **Rollout_Flag**：控制前端 workpaper 锁分支走 v1 或 v2 端点的灰度开关。
- **Force_Acquired_Event**：强抢锁时通过 SSE 推送的 `editing_lock.force_acquired` 事件。
- **Holder_Name**：v2 持有者显示名（v1 无此字段，迁移时按用户记录回填）。

## Requirements

### Requirement 1: 存量活跃锁数据迁移

**User Story:** 作为平台运维人员，我想把底稿专用锁表中的存量活跃锁迁移到通用锁表，以便底稿锁统一由 v2 承载且不丢失现有锁。

#### Acceptance Criteria

1. WHEN Migration_Script 执行，THE Migration_Script SHALL 将 `workpaper_editing_locks` 中所有满足 `released_at IS NULL` 的锁记录写入 `editing_locks`，映射为 `resource_type='workpaper'`、`resource_id = wp_id::text`、`holder_id = staff_id`。
2. WHEN Migration_Script 写入迁移记录，THE Migration_Script SHALL 保留源记录的 `acquired_at` 与 `heartbeat_at` 值，且 WHERE 源值为 naive timestamp（v1 service 用 `_now_naive()` 写入无时区值，v2 service 用 aware UTC），THE Migration_Script SHALL 将其按 UTC 规整为 aware 值，使迁移后的锁在 v2 的 `heartbeat_at > now-5min` 过期判定下与源语义一致（不因时区偏移被立即判过期或永不过期）。
3. WHERE 源活跃锁缺少 `holder_name`，THE Migration_Script SHALL 从 `users` 表按 `staff_id` 回填 `holder_name`，且 WHEN 无法解析用户名 THEN THE Migration_Script SHALL 将 `holder_name` 写为 NULL。
4. WHEN 同一 `wp_id` 在源表存在多条 `released_at IS NULL` 的活跃锁，THE Migration_Script SHALL 仅保留 `heartbeat_at` 最新的一条迁入 `editing_locks`，并将其余源活跃锁视为已释放不迁入，以满足 v2 同资源活跃锁 ≤ 1 的约束。
5. WHEN Migration_Script 重复执行，THE Migration_Script SHALL 对已迁移的 `(resource_type='workpaper', resource_id)` 不产生重复活跃锁记录。
6. THE Migration_Script SHALL 提供配对的回退脚本（V073 与 R073），且建表/插入语句 SHALL 使用 `IF NOT EXISTS` 或等价幂等保护。

### Requirement 2: 三层一致校验

**User Story:** 作为后端开发者，我想确保迁移涉及的数据库、ORM 与服务三层定义一致，以便避免伪绿和 schema 漂移。

#### Acceptance Criteria

1. THE Migration_Script SHALL 与 `EditingLock` ORM 模型的列定义保持一致。
2. THE V2_Service SHALL 通过 `EditingLock` ORM 读写迁移后的 Workpaper_Lock 记录。
3. WHERE 迁移引入新增列或索引，THE EditingLock ORM 模型 SHALL 包含对应的 `Mapped[]` 定义。
4. THE Migration_Script SHALL 对 TimestampMixin 涉及的 `created_at` 与 `updated_at` 列显式声明 `TIMESTAMPTZ NOT NULL DEFAULT now()`。

### Requirement 3: 通用端点承载底稿锁行为

**User Story:** 作为底稿编辑用户，我想通过通用编辑锁端点完成底稿的获取、续期、释放与强抢，以便底稿锁与其它资源锁使用统一接口。

#### Acceptance Criteria

1. WHEN 用户对 `resource_type='workpaper'` 调用 acquire 端点且该底稿无 Active_Lock，THE V2_Service SHALL 创建活跃锁并返回获取成功结果。
2. IF 用户对 `resource_type='workpaper'` 调用 acquire 端点且该底稿已被**他人**持有 Active_Lock，THEN THE V2_Service SHALL 返回 HTTP 409 与持有者信息。
2a. IF 用户对 `resource_type='workpaper'` 调用 acquire 端点且该底稿已被**该用户本人**持有 Active_Lock，THEN THE V2_Service SHALL 续期（刷新 `heartbeat_at`）并返回获取成功结果（不返回 409）。（对齐 v1 `acquire_lock` 的"同人重复 acquire 自动续期"语义，前端 watch(resourceId)/组件重挂载会重复 acquire，缺此语义会导致本人被自己的锁挡在 409 外。）
3. WHEN 用户对持有的 Workpaper_Lock 调用 heartbeat 端点，THE V2_Service SHALL 更新 `heartbeat_at` 并返回续期成功结果。
4. IF 用户对无 Active_Lock 的底稿调用 heartbeat 端点，THEN THE V2_Service SHALL 返回 HTTP 404。
5. WHEN 用户对持有的 Workpaper_Lock 调用 release 端点，THE V2_Service SHALL 设置 `released_at` 并返回释放成功结果。
6. WHEN 用户对 `resource_type='workpaper'` 调用 force 端点，THE V2_Service SHALL 释放现有活跃锁并创建新锁，且返回前持有者标识。
7. THE V2_Service SHALL 在所有底稿锁操作中遵循 service 只 flush 不 commit、由 router 统一 commit 的约束。
8. THE V2_Service 的活跃锁列表端点（`GET /api/editing-locks/active?resource_type=workpaper`）SHALL 仅返回 `editing_locks` 现有列字段（holder_id/holder_name/resource_id/acquired_at/heartbeat_at），不要求复刻 v1 的 `wp_code`/`wp_name`/`staff_name` JOIN 富字段。（已核实：v1 `/active` 富字段端点无任何前端消费者，属死端点，下线时直接废弃。）

### Requirement 4: 前端分流切换到 v2

**User Story:** 作为底稿编辑用户，我想前端在灰度开启后将底稿锁请求发往 v2 通用端点，以便底稿锁链路与附注、报告统一。

#### Acceptance Criteria

1. WHERE Rollout_Flag 启用 v2，THE Frontend_Composable SHALL 对 `resourceType='workpaper'` 调用 `/api/editing-locks/workpaper/{wpId}` 系列端点完成 acquire、heartbeat、release 与 force。
2. WHERE Rollout_Flag 未启用 v2，THE Frontend_Composable SHALL 对 `resourceType='workpaper'` 继续调用 `/api/workpapers/{wpId}/editing-lock` 系列端点。
3. WHEN Rollout_Flag 由 v1 切换为 v2，THE Frontend_Composable SHALL 在不修改调用方组件参数的前提下完成底稿锁端点切换。
3a. THE Frontend_Composable SHALL 在执行 acquire 前 await 解析完 `v2Enabled`（异步读 `/api/feature-flags-v2/{key}`，仅取全局 `enabled` 布尔，不做前端百分比灰度），且单个锁的完整生命周期（acquire → heartbeat → release）SHALL 锁定同一个 `v2Enabled` 快照、不中途重读，以避免"acquire 走 v2、release 走 v1"导致跨表锁泄漏。
4. WHEN 底稿锁切换到 v2 后用户进入底稿编辑，THE Frontend_Composable SHALL 通过 Playwright 实测验证 acquire、heartbeat、release、force-acquire 全链路成功。

### Requirement 5: SSE 强抢通知兼容

**User Story:** 作为被强抢锁的底稿编辑用户，我想在底稿锁迁移到 v2 后仍能收到强抢通知，以便及时感知锁被他人接管。

#### Acceptance Criteria

1. WHEN 他人对 `resource_type='workpaper'` 执行 force-acquire，THE Editing_Lock_System SHALL 推送包含 `event_type='editing_lock.force_acquired'` 的 Force_Acquired_Event。
2. THE Force_Acquired_Event SHALL 在 `resource_type='workpaper'` 时同时包含 `wp_id`、`resource_type` 与 `resource_id` 字段（`wp_id == resource_id`），使前端按 `wp_id` 匹配与按 `(resource_type, resource_id)` 匹配均可识别底稿锁被强抢；WHERE `resource_type != 'workpaper'`，THE Force_Acquired_Event SHALL 省略 `wp_id` 或置为 null（不得把非底稿的 resource_id 误塞进 `wp_id` 字段）。
3. WHEN 原持有者收到匹配本人持锁底稿的 Force_Acquired_Event，THE Frontend_Composable SHALL 将本地持锁状态标记为非持有并展示新持有者信息。

### Requirement 6: 零停机与向后兼容

**User Story:** 作为平台运维人员，我想在迁移期间底稿锁始终可用，以便用户不感知切换、不出现锁丢失或接口报错。

#### Acceptance Criteria

1. WHILE 迁移与灰度处于双端点并存窗口，THE Editing_Lock_System SHALL 同时保持 v1 与 v2 底稿锁端点可用。
2. WHILE 双端点并存窗口，THE Editing_Lock_System SHALL 保证底稿锁请求不返回 HTTP 404 路由缺失错误。
3. IF 灰度阶段（阶段 1/2，v1 端点尚在）底稿锁出现异常，THEN THE Rollout_Flag SHALL 支持把 `editing_lock_v2_workpaper` 置 false 切回 v1 端点以恢复底稿锁服务。
3a. WHEN v1 已下线（阶段 3 完成），THE Frontend_Composable SHALL NOT 保留指向 v1 端点的回退分支（默认走 v2），以避免 flag 读失败回退到已删除的 v1 端点产生 404。
4. WHEN Rollout_Flag 切回 v1，THE Migration_Script 的执行结果 SHALL 不破坏 `workpaper_editing_locks` 表中的源数据。

### Requirement 7: v1 下线条件

**User Story:** 作为后端开发者，我想在满足明确条件后安全下线 v1，以便消除重复实现且不引发回归。

#### Acceptance Criteria

1. WHERE 前端已全量切换 v2、存量数据迁移已核对、Playwright 全链路实测通过且测试覆盖迁移完成，THE Editing_Lock_System SHALL 移除 v1 router 在 `router_registry/collaboration.py` 中的注册。
2. WHEN v1 下线执行，THE Editing_Lock_System SHALL 删除 `editing_lock_service` 与 `editing_lock.py` router。
3. WHEN v1 表下线执行，THE Migration_Script SHALL 通过配对的迁移与回退脚本移除 `workpaper_editing_locks` 表。
4. IF v1 下线条件中任一项未满足，THEN THE Editing_Lock_System SHALL 保留 v1 实现不删除。

### Requirement 8: 测试覆盖迁移

**User Story:** 作为质控人员，我想 v1 测试在下线前迁移或替换为 v2 等价测试，以便锁功能的测试覆盖不因下线而丢失。

#### Acceptance Criteria

1. WHEN v1 测试 `test_editing_lock.py` 与 `test_editing_lock_concurrent.py` 被移除，THE Editing_Lock_System SHALL 为 `resource_type='workpaper'` 提供 V2_Service 上的等价 acquire、heartbeat、release、force-acquire 与并发测试。
2. THE Editing_Lock_System SHALL 包含验证存量锁迁移正确性的测试，覆盖字段映射（`staff_id→holder_id`、`wp_id→resource_id`、`holder_name` 回填）与多活跃锁去重。
3. THE Editing_Lock_System SHALL 包含验证迁移幂等性的测试，重复执行 Migration_Script 后同资源活跃锁数量保持为 1。
4. WHERE 编写 Property-Based Test，THE Editing_Lock_System SHALL 将 `max_examples` 设置为 5。
5. WHEN 测试套件执行，THE Editing_Lock_System SHALL 使迁移后底稿锁相关测试全部通过。

## 待澄清问题（Open Questions）

1. **历史锁是否迁移**：`workpaper_editing_locks` 中 `released_at IS NOT NULL` 的历史锁是否需要迁入 `editing_locks`？当前需求草案仅迁移活跃锁。若历史锁用于审计追溯或监控统计，则需追加历史数据迁移策略（含 `released_at` 保留），并评估对 v2 部分唯一索引的影响（历史锁不受活跃锁唯一约束）。
2. **FK 丢失影响评估**：v1 的 `wp_id` 有 FK 指向 `working_paper.id`（底稿删除时锁记录受约束保护），v2 的 `resource_id` 为纯字符串无 FK。收口后底稿锁失去 FK 校验，需评估：底稿被删除后遗留的孤儿 workpaper 锁如何清理（依赖 heartbeat 过期惰性清理是否足够），以及是否需要额外的清理任务或在 acquire 时校验底稿存在性。
