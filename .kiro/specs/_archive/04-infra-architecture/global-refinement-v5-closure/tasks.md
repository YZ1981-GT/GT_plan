# Implementation Plan: global-refinement-v5-closure

## Overview

将 v5.0 全局复盘确认的 4 个真实缺口转化为可增量交付的编码任务。遵循"能复用绝不新建"原则，每个任务在前序任务基础上推进并最终接线，无悬空代码。

实现语言：**后端 Python（FastAPI + SQLAlchemy async + D6 运行时迁移），前端 TypeScript（Vue 3 + Composition API）**——与现有仓库一致，设计文档已使用具体语言，无需另选。

### 批次划分（可独立交付验收）

- **批次①｜能力域 C — 通用编辑锁**：独立后端子系统（V057 + ORM + service + router）+ 前端 useEditingLock 扩展 + 附注/报告编辑器接真锁。任务 1~4。
- **批次②｜能力域 D — 函证模块**：独立后端子系统（V058 + ORM + service + 重写 router）+ 填充 ConfirmationHub.vue。任务 5~8。
- **批次③｜能力域 A — 单元格溯源接线**：纯前端，零新建后端。任务 9~10。
- **批次④｜能力域 B — stale 全局刷新范式**：纯前端，零新建后端。任务 11~12。

建议实施顺序：**①C → ②D → ③A → ④B**（先交付后端并发安全硬需求与三层一致子系统，再做前端接线；A/B 可与 C/D 并行）。

### 勘察补充（避免重复造轮子，执行前必读）

- **D 域 ConfirmationHub.vue 已存在**（`views/ConfirmationHub.vue`，标题"函证管理" + GtEmpty preset="developing" 空壳，路由已挂）→ 任务"填充现有 ConfirmationHub.vue"，**不另建 ConfirmationList.vue**（设计文档中 `ConfirmationList` 一律指 `ConfirmationHub`）。
- **D 域已有 `components/collaboration/ConfirmationPanel.vue`**（含 `confirmations` ref + `confirmationApi`，类型枚举 BANK/AR/AP/LAWYER、状态 PENDING/SENT/RECEIVED/EXCEPTION，与本设计 receivable/payable/bank/loan + pending/sent/returned/matched/discrepancy **不一致**）→ 执行前须勘察决策：对齐到新枚举 / 沿用旧前端 API / 二者择一，避免函证数据结构重复定义。
- **D 域 `GtDForm/composables/useConfirmationFields.ts`**（`ConfirmationData extends DFormData`）是**底稿 D-form 字段** composable，与函证模块数据模型不同源，勘察确认不可直接复用其接口。
- **C 域 `composables/useEditingLock.ts` 已有契约形状**（`EditingLockOptions`/`EditingLockTakenOverPayload` + `useEditingLock(options)`，`resourceType?: 'workpaper' | 'other'`）+ `views/workpaper-editor/EditorBanners.vue` 已有 `EditingLockAPI` 接口 → C 域前端是**基于现有接口扩展 resourceType**，不是重写。

## Tasks


---

## 批次①｜能力域 C — 通用编辑锁（后端新建 + 前端改造）

- [x] 1. 编辑锁三层基建：迁移 + ORM（三层一致，缺一不可）
  - [x] 1.1 创建 V057 迁移 + R057 回滚配对
    - 新建 `backend/migrations/V057__editing_locks.sql`：`CREATE TABLE IF NOT EXISTS editing_locks`（id/resource_type/resource_id/holder_id FK users/holder_name/acquired_at/heartbeat_at/released_at）
    - 加索引 `idx_editing_locks_resource` (resource_type, resource_id) + `idx_editing_locks_heartbeat` (heartbeat_at)
    - 加**部分唯一索引** `uq_editing_locks_active ON editing_locks (resource_type, resource_id) WHERE released_at IS NULL`（活跃锁≤1 最终防线）
    - 新建 `backend/migrations/R057__editing_locks_rollback.sql`：`DROP TABLE IF EXISTS editing_locks`
    - 所有 CREATE 用 `IF NOT EXISTS`；version 数字排号 V057 不撞当前最高 V056
    - _Requirements: 6.1, 6.2, 6.4, 8.1_
    - _Design: Data Models — C — editing_locks（V057）_
  - [x] 1.2 创建 EditingLock ORM 模型
    - 新建 `backend/app/models/editing_lock_models.py`：`EditingLock(Base, TimestampMixin)`，全字段 `Mapped[]` 类型标注，`__table_args__` 含两个 Index
    - 确保 model 被 metadata 注册（pkgutil walk 可发现）
    - _Requirements: 6.3_
    - _Design: Data Models — C — editing_locks ORM_

- [x] 2. EditingLockService（5min heartbeat 惰性清理，service 只 flush）
  - [x] 2.1 实现 EditingLockService 核心方法
    - 新建 `backend/app/services/editing_lock_service.py`，复刻现有 `editing_lock_service` 的 5min heartbeat 惰性清理模式，锁维度改 `(resource_type, resource_id)`
    - 实现 `acquire_lock`：先惰性清理过期锁（heartbeat_at < now-5min 置 released_at=now）→ 查活跃锁 → 无则创建；冲突返回当前持有人信息
    - 实现 `release_lock` / `heartbeat_lock`（刷新 heartbeat_at）/ `force_acquire_lock`（释放原锁+创建新锁+返回前持有人）/ `get_active_locks`
    - service 只 `flush` 不 `commit`（项目铁律，router 统一 commit）
    - acquire 写入前用 `SELECT ... FOR UPDATE` 行锁；唯一索引冲突用 SAVEPOINT 捕获 `IntegrityError` 转 409（不污染事务）
    - 可选字段写库用 `(data.get(k) or None)` 显式兜底
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3_
    - _Design: Components and Interfaces — C — 后端 / Error Handling — C_
  - [x]* 2.2 编写 Property 3 属性测试：活跃锁唯一不变量
    - **Property 3: 编辑锁活跃数唯一不变量**
    - **Validates: Requirements 7.1, 8.1, 8.2**
    - 位置 `backend/tests/services/test_editing_lock_service.py`，hypothesis `@settings(max_examples=5)`
    - 随机 acquire 序列（不同持有人）断言活跃锁数≤1，第二持有人被拒并返回当前持有人
    - 标 `pg_only` marker（部分唯一索引 `WHERE released_at IS NULL` + SAVEPOINT 需真 PG）
    - 标签 `# Feature: global-refinement-v5-closure, Property 3`
  - [x]* 2.3 编写 Property 4 属性测试：锁获取-释放往返
    - **Property 4: 锁获取-释放往返**
    - **Validates: Requirements 7.2**
    - hypothesis `@settings(max_examples=5)`，acquire→release→acquire 成功
    - 标签 `# Feature: global-refinement-v5-closure, Property 4`
  - [x]* 2.4 编写 Property 5 属性测试：心跳续约保持锁有效
    - **Property 5: 心跳续约保持锁有效并刷新时间**
    - **Validates: Requirements 7.3**
    - hypothesis `@settings(max_examples=5)`，heartbeat 后 heartbeat_at 不早于调用前且锁仍活跃
    - 标签 `# Feature: global-refinement-v5-closure, Property 5`
  - [x]* 2.5 编写 Property 6 属性测试：强制获取转移持有权
    - **Property 6: 强制获取转移持有权**
    - **Validates: Requirements 7.4**
    - hypothesis `@settings(max_examples=5)`，force-acquire 后新持有人唯一活跃锁 + 返回前持有人标识
    - 标签 `# Feature: global-refinement-v5-closure, Property 6`
  - [x]* 2.6 编写 Property 7 属性测试：过期锁不阻塞新获取
    - **Property 7: 过期锁不阻塞新获取**
    - **Validates: Requirements 8.3**
    - hypothesis `@settings(max_examples=5)`，注入过期 heartbeat_at 后其他持有人 acquire 成功
    - 标 `pg_only` marker；标签 `# Feature: global-refinement-v5-closure, Property 7`

- [x] 3. 通用锁 router + 注册（router_registry 必查否则 404）
  - [x] 3.1 实现通用编辑锁 router
    - 新建 `backend/app/routers/editing_locks.py`，prefix `/api/editing-locks`
    - 端点：`POST /{resource_type}/{resource_id}`（acquire）/ `PATCH .../heartbeat` / `DELETE .../{resource_type}/{resource_id}`（release）/ `POST .../force` / `GET /active`
    - router 统一 `commit`；锁冲突返回 409 `{error_code:"LOCK_HELD", locked_by, locked_by_name, acquired_at}`（中文持有人名）；heartbeat/release 无活跃锁返回 404 中文"无活跃锁"
    - 在 `backend/app/router_registry/collaboration.py`（或 workpaper.py）注册新 router
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
    - _Design: Components and Interfaces — C — 后端 router / Error Handling — C_
  - [x]* 3.2 编写 router 单元测试
    - 测 acquire/release/heartbeat/force/active 各端点正常路径 + 409/404 错误路径
    - in-process ASGI（httpx ASGITransport）全 app 加载避免 FK NoReferencedTableError
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 4. 前端 useEditingLock 扩展 + 附注/报告编辑器接真锁
  - [x] 4.1 扩展 useEditingLock 支持任意 resourceType
    - 改造现有 `frontend/src/composables/useEditingLock.ts`（基于现有 `EditingLockOptions`/`EditingLockTakenOverPayload` 接口扩展，不重写）
    - `resourceType` 从 `'workpaper' | 'other'` 改为接受任意字符串：`workpaper` 仍走旧底稿专用端点保持兼容，其余（`disclosure_note`/`audit_report`）走新通用端点 `/api/editing-locks/{resourceType}/{resourceId}`
    - acquire/release/heartbeat/force 对非 workpaper 类型走通用端点；保留 `editing-lock:taken-over` eventBus 通知
    - _Requirements: 9.1, 9.2, 9.4_
    - _Design: Components and Interfaces — C — 后端 / Architecture — C 设计要点_
  - [x] 4.2 DisclosureEditor 接入真后端锁
    - `DisclosureEditor.vue` 通过 `useEditingLock({ resourceType: 'disclosure_note', resourceId })` 替换原前端降级检测
    - 第二人打开已锁定附注进入只读 + 中文锁持有人提示（复用 EditorBanners 的 `EditingLockAPI`）
    - _Requirements: 9.1, 9.3, 9.4_
    - _Design: Architecture — C 设计要点_
  - [x] 4.3 AuditReportEditor 接入真后端锁
    - `AuditReportEditor.vue` 通过 `useEditingLock({ resourceType: 'audit_report', resourceId })` 替换原前端降级检测
    - 第二人只读 + 中文锁持有人提示 + 强抢 `editing-lock:taken-over` 通知
    - _Requirements: 9.2, 9.3, 9.4_
    - _Design: Architecture — C 设计要点_

- [x] 5. 能力域 C 实测验收（getDiagnostics 过≠运行时无错）
  - 后端 `python -m pytest backend/tests/services/test_editing_lock_service.py -v`（PG 环境跑 pg_only 属性测试）
  - 前端 `npx vitest run` 相关 useEditingLock/编辑器测试
  - 跑 `python backend/scripts/check/check_file_size.py`（exit 0）
  - 三层一致校验：V057+R057 迁移 + EditingLock ORM `Mapped[]` + EditingLockService 方法齐全 + router 已在 router_registry 注册
  - _Requirements: 14.1, 14.2, 14.4_
  - _Design: Testing Strategy — 跨能力域门禁_


---

## 批次②｜能力域 D — 函证模块（全新建）

- [x] 6. 函证三层基建：迁移 + ORM + 枚举（三层一致，缺一不可）
  - [x] 6.1 创建 V058 迁移 + R058 回滚配对
    - 新建 `backend/migrations/V058__confirmations.sql`：`CREATE TABLE IF NOT EXISTS confirmations`（id/project_id FK projects/confirm_type/counterparty/status default 'pending'/wp_id FK working_paper/account_code/book_amount/confirmed_amount/diff_amount/diff_note/created_by FK users/created_at/updated_at）
    - 加索引 `idx_confirmations_project` (project_id) + `idx_confirmations_status` (status)
    - 新建 `backend/migrations/R058__confirmations_rollback.sql`：`DROP TABLE IF EXISTS confirmations`
    - CREATE 用 `IF NOT EXISTS`；version 数字排号 V058 不撞 V056/V057
    - _Requirements: 10.1, 10.2, 12.1, 12.2_
    - _Design: Data Models — D — confirmations（V058）_
  - [x] 6.2 创建 Confirmation ORM 模型 + 枚举
    - 新建 `backend/app/models/confirmation_models.py`：`ConfirmationType`（receivable/payable/bank/loan）+ `ConfirmationStatus`（pending/sent/returned/matched/discrepancy）枚举 + `Confirmation(Base, TimestampMixin)` 全字段 `Mapped[]`
    - 确保 model 被 metadata 注册
    - _Requirements: 10.1, 10.2, 11.1_
    - _Design: Data Models — D — confirmations ORM_

- [x] 7. ConfirmationService（CRUD + 状态机，service 只 flush）
  - [x] 7.1 实现 CRUD 方法
    - 新建 `backend/app/services/confirmation_service.py`
    - 实现 `create_confirmation`（持久化返回标识）/ `list_confirmations`（项目级）/ `get_confirmation`（含关联+差异）/ `update_confirmation` / `delete_confirmation`
    - 可选字段写库用 `(data.get(k) or None)` 显式兜底（避免 NOT NULL 插入崩）；支持关联 wp_id + account_code + 差异金额/说明持久化
    - service 只 `flush` 不 `commit`
    - _Requirements: 10.3, 10.4, 10.5, 12.1, 12.2, 12.3_
    - _Design: Components and Interfaces — D — 后端 / Error Handling — D_
  - [x] 7.2 实现状态机 transition_status
    - 定义 `_ALLOWED_TRANSITIONS = {pending:{sent}, sent:{returned}, returned:{matched, discrepancy}, matched:set(), discrepancy:set()}`
    - `transition_status(db, confirmation_id, target)` 仅允许合法转换，非法转换抛中文 `ValueError`（如"不能从『已发函』直接转为『相符』"），状态保持不变
    - 函证不存在抛 404 语义中文"函证记录不存在"
    - _Requirements: 11.1, 11.2, 11.3_
    - _Design: Data Models — D — 合法状态转换表 / Error Handling — D_
  - [x]* 7.3 编写 Property 8 属性测试：函证持久化往返
    - **Property 8: 函证持久化往返**
    - **Validates: Requirements 10.3, 10.4, 10.5, 12.1, 12.3**
    - 位置 `backend/tests/services/test_confirmation_service.py`，hypothesis `@settings(max_examples=5)`
    - 随机函证创建/更新/删除，列表或详情查询字段一致；更新反映新值；删除后不在列表
    - 标签 `# Feature: global-refinement-v5-closure, Property 8`
  - [x]* 7.4 编写 Property 9 属性测试：函证状态机合法性
    - **Property 9: 函证状态机合法性**
    - **Validates: Requirements 11.2, 11.3**
    - hypothesis `@settings(max_examples=5)`，随机 (当前, 目标) 组合：属于 `_ALLOWED_TRANSITIONS` 才成功，其余拒绝并返回中文错误且状态不变
    - 标签 `# Feature: global-refinement-v5-closure, Property 9`

- [x] 8. 重写 confirmations router（替换 18 行 stub，沿用既有注册）
  - [x] 8.1 重写 confirmations.py router
    - 重写 `backend/app/routers/confirmations.py`（替换 developing stub），prefix `/projects/{project_id}/confirmations`
    - 端点：`GET ""`（列表，替换 `{status:"developing"}`）/ `POST ""`（创建）/ `GET /{confirmation_id}`（详情含关联+差异）/ `PUT /{confirmation_id}` / `DELETE /{confirmation_id}` / `POST /{confirmation_id}/transition`（状态推进）
    - router 统一 `commit`；非法转换 service `ValueError` 转 400；函证不存在 404 中文；创建缺必填 confirm_type/counterparty 走 Pydantic 422 或 service 显式中文校验
    - 沿用 `router_registry/collaboration.py §12` 既有注册（确认 prefix 与端点匹配）
    - _Requirements: 10.3, 10.4, 10.5, 11.2, 11.3, 12.3_
    - _Design: Components and Interfaces — D — 后端 router / Error Handling — D_
  - [x]* 8.2 编写 router 单元测试
    - 测 CRUD + transition 正常路径 + 非法转换 400 + 不存在 404 + 缺必填 422
    - in-process ASGI 全 app 加载
    - _Requirements: 10.3, 10.4, 10.5, 11.2, 11.3_

- [x] 9. 填充前端 ConfirmationHub.vue（中文 UI + GtAmountCell + GT 紫令牌）
  - [x] 9.1 勘察并对齐函证前端数据契约
    - 勘察现有 `components/collaboration/ConfirmationPanel.vue`（旧枚举 BANK/AR/AP/LAWYER + PENDING/SENT/RECEIVED/EXCEPTION + `confirmationApi`）与本设计新枚举（receivable/payable/bank/loan + pending/sent/returned/matched/discrepancy）差异
    - 决策并记录：对齐到新后端枚举（推荐，单一真源）/ 或适配层映射；避免函证数据结构重复定义
    - _Requirements: 10.2, 11.1_
    - _Design: 勘察补充_
  - [x] 9.2 填充 ConfirmationHub.vue 函证清单 + 状态机 UI
    - 填充现有 `views/ConfirmationHub.vue`（替换 GtEmpty 空壳，不另建 ConfirmationList.vue）：函证清单表格（类型/对手方/状态/账面金额/回函金额/差异）+ 新建/编辑/删除 + 状态推进按钮（合法转换可用）
    - 金额列用 GtAmountCell；全中文文本；GT 紫令牌（`--gt-color-primary` 等），禁 Element 默认蓝 fallback
    - 接入本 spec 新 `/projects/{pid}/confirmations` 端点
    - 回函登记（→已回函）成功后 emit eventBus `confirmation:received`
    - _Requirements: 10.4, 11.4, 12.3, 13.1, 13.2, 13.3_
    - _Design: Architecture — D 设计要点 / 勘察补充_
  - [x]* 9.3 编写 ConfirmationHub 前端单元测试
    - 测清单渲染 + 状态推进按钮可用性（合法转换）+ confirmation:received emit + 金额 GtAmountCell 展示
    - _Requirements: 11.4, 13.2_

- [x] 10. 能力域 D 实测验收
  - 后端 `python -m pytest backend/tests/services/test_confirmation_service.py -v`
  - 前端 `npx vitest run` ConfirmationHub 相关测试；必要时 Playwright 实测函证清单页渲染 + 状态推进
  - 跑 `python backend/scripts/check/check_file_size.py`（exit 0）
  - 三层一致校验：V058+R058 迁移 + Confirmation ORM `Mapped[]` + ConfirmationService 方法齐全 + router 已重写并注册
  - _Requirements: 14.1, 14.2, 14.3, 14.4_
  - _Design: Testing Strategy — 跨能力域门禁_


---

## 批次③｜能力域 A — 单元格数字溯源（纯前端接线，零新建后端）

- [x] 11. 六大页已有 CellContextMenu 加"数字溯源"项（复用既有右键菜单，不改 GtAmountCell）
  - [x] 11.1 勘察六大页已有 CellContextMenu 用法
    - 先跑 `codegraph query "CellContextMenu"` 确认六大页已有的右键菜单绑定点（ReportView onReportCellContextMenu / TrialBalance / DisclosureEditor onDeCellContextMenu / ConsolidationIndex onConsolCtxDrillDown 等）
    - 记录每页的 CellContextMenu 实例 + 当前菜单项 + 传入的 row/cell 上下文（决定如何构造 lineage 请求参数）
    - **复盘改进**：原设计"GtAmountCell 加 prop"会改全仓 30+ 引用点；实际六大页已有 CellContextMenu 组件渲染右键菜单，只需在其 slot 加一项"数字溯源"即可，**零改 GtAmountCell 组件本身**（最小风险）
    - _Requirements: 1.1_
    - _Design: Architecture — A 设计要点_
  - [x] 11.2 六大页 CellContextMenu 加"数字溯源"菜单项
    - 在各页已有的 `<CellContextMenu>` 组件 slot 里加一项"🔍 数字溯源"（仿现有"📊 汇总穿透" / "📊 查看" 等已有项的模式）
    - 点击时从当前行/单元格上下文构造 lineage 请求参数（object_type + object_id）：报表行用 `report_row` + row_code；TB 用 `tb_row` + standard_account_code；附注用 `note_cell` + section_number；底稿用 `wp_cell` + wp_code!cell_ref；调整用 `adjustment` + adjustment_no
    - 调 `GET /api/projects/{pid}/lineage?object_type=...&object_id=...&direction=both`（复用现有端点）
    - **不修改 GtAmountCell.vue**（保持核心共用组件零风险、既有 30+ 引用不受影响）
    - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.2, 13.1_
    - _Design: Components and Interfaces — A — 前端 / Architecture — A_
  - [x]* 11.3 编写 Property 1 属性测试：溯源请求载荷完整性
    - **Property 1: 溯源请求载荷完整性**
    - **Validates: Requirements 1.3**
    - 位置 `frontend/src/views/__tests__/cellTrace.spec.ts`，fast-check `{ numRuns: 5 }`
    - 随机 object_type + object_id + 可选 cellRef 验证构造的 lineage 请求参数完整
    - mock api.get，不依赖真实后端
    - 标签 `// Feature: global-refinement-v5-closure, Property 1`

- [x] 12. 来源链展示接线 + 六大页注入 traceContext
  - [x] 12.1 CellTraceDialog 对接 lineage 端点 + 空来源提示
    - 复用现有 `CellTraceDialog`（`components/notes/CellTraceDialog.vue`）+ `useCellLocate`，新增 `openTrace(ctx)` 内部 `GET /api/projects/{pid}/lineage?object_type=&object_id=&direction=both`
    - 按层级展示来源节点（报表行→TB→序时账/凭证）；点击节点 emit eventBus `workpaper:locate-cell` 定位
    - 空来源链显示中文"该数字暂无溯源信息"，不渲染空白弹窗；GET 失败经 handleApiError 中文提示，弹窗保持可用
    - 不新增重复 composable / 不新增溯源 router（复用现有基建）
    - _Requirements: 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2_
    - _Design: Architecture — A 时序图 / Error Handling — A_
  - [x] 12.2 验证已有页面无需额外 GtAmountCell 改动
    - **复盘调整**：溯源触发点已改为 CellContextMenu slot（任务 11.2），不再需要 GtAmountCell 传 prop
    - 确认各页 CellContextMenu 的 slot 能从行/单元格上下文获取 object_type + object_id（已在 11.2 实现）
    - 确认 GtAmountCell.vue **零改动**（零回归风险），grep 确认无新增 enableTrace/traceContext prop 引用
    - _Requirements: 1.1, 3.2_
  - [x]* 12.3 编写溯源接线单元测试
    - 测空来源中文提示 + 来源链层级展示 + locate-cell emit + GET 失败 handleApiError
    - _Requirements: 1.4, 2.2, 2.3, 2.4_

- [x] 13. 能力域 A 实测验收
  - 前端 `npx vitest run` GtAmountCell.trace + CellTraceDialog 相关测试
  - 必要时 Playwright 实测：金额单元格右键→数字溯源→来源链展示/空提示
  - 跑 `python backend/scripts/check/check_file_size.py`（exit 0）
  - 确认零新建后端端点（复用 `GET /lineage`），既有 GtAmountCell 调用零回归
  - _Requirements: 3.1, 3.2, 14.2, 14.3_
  - _Design: Testing Strategy — 跨能力域门禁_

---

## 批次④｜能力域 B — stale 全局自动刷新范式（纯前端，零新建后端）

- [x] 14. useStaleRefresh 通用范式 composable
  - [x] 14.1 实现 useStaleRefresh composable
    - 新建 `frontend/src/composables/useStaleRefresh.ts`：`useStaleRefresh(projectId, { events, mode, onRefresh })`
    - 内部委托现有 `useProjectEvents`（SSE 项目级过滤）+ 直接订阅 eventBus 业务事件（`trial-balance:updated`/`adjustment:saved`/`dataset:activated`/`dataset:rolledback`/`year:changed`）
    - 暴露 `isStale: Ref<boolean>` + `refresh()` + `markFresh()`；`mode='auto'` 事件到达直接调 onRefresh，`mode='prompt'` 置 isStale=true
    - projectId 匹配复用 useProjectEvents 过滤逻辑（payload.project_id !== projectId 忽略）；eventBus 业务事件 payload 缺 projectId 视为不匹配忽略
    - onRefresh 抛错时捕获并保持 isStale=true（由页面 handleApiError 提示），不影响事件订阅
    - 不新增重复 composable / 不新建后端
    - _Requirements: 4.2, 4.4, 5.1, 5.2_
    - _Design: Components and Interfaces — B — 前端 / Architecture — B / Error Handling — B_
  - [x]* 14.2 编写 Property 2 属性测试：项目级事件分发不变量
    - **Property 2: 项目级事件分发不变量**
    - **Validates: Requirements 4.2, 4.4, 5.1, 5.2**
    - 位置 `frontend/src/composables/__tests__/useStaleRefresh.spec.ts`，fast-check `{ numRuns: 5 }`
    - 随机上游事件 + projectId：匹配则触发刷新/置 stale，不匹配则忽略不触发
    - mock eventBus 与 useProjectEvents
    - 标签 `// Feature: global-refinement-v5-closure, Property 2`

- [x] 15. 六大数据页接入 useStaleRefresh（6→12+）
  - [x] 15.1 四表 / 报表 / 底稿页接入
    - TrialBalance / ReportView / WorkpaperEditor `onMounted` 调用 `useStaleRefresh`，上游变更后自动刷新或显示中文 stale 横幅（如"上游数据已变更，建议重新计算"）+ 刷新入口
    - 年度切换 `year:changed` 匹配时按新年度重拉 + 中文加载状态
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.3_
    - _Design: Architecture — B 设计要点_
  - [x] 15.2 调整 / 错报 / 附注页接入
    - 调整页 / 错报页 / DisclosureEditor `onMounted` 调用 `useStaleRefresh`，同上刷新/stale 提示 + 年度联动
    - 接入后 `useProjectEvents` 接入文件数从 6 增至 12+
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.3_
    - _Design: Architecture — B 设计要点_
  - [x]* 15.3 编写接入页 stale 提示单元测试
    - 测某代表页：上游事件 projectId 匹配触发刷新/stale 横幅，不匹配忽略
    - _Requirements: 4.2, 4.4_

- [x] 16. 能力域 B 实测验收
  - 前端 `npx vitest run` useStaleRefresh + 接入页相关测试
  - grep 确认 `useProjectEvents` 接入文件数 ≥12
  - 必要时 Playwright 实测：上游变更后数据页 stale 横幅出现 + 年度切换联动刷新
  - 跑 `python backend/scripts/check/check_file_size.py`（exit 0）
  - _Requirements: 4.1, 14.2, 14.3_
  - _Design: Testing Strategy — 跨能力域门禁_

---

## 可选增强（非核心，可跳过）

- [x]* 17. Playwright E2E 端到端覆盖
  - C 域：两浏览器并发编辑附注/报告，第二人只读 + 锁持有人提示 + 强抢通知
  - D 域：函证清单创建→状态推进全流程
  - A 域：六大页金额单元格右键溯源
  - B 域：上游变更 stale 横幅 + 年度联动
  - _Requirements: 9.3, 9.4, 11.4_

- [x]* 18. 非核心页溯源接入扩展
  - 将 GtAmountCell 溯源 prop 接入六大页之外的金额展示页（如合并工作底稿、看板）
  - _Requirements: 1.1_

## Notes

- 标记 `*` 的子任务为可选（测试/E2E/非核心接入），可为更快 MVP 跳过；顶层任务不带 `*`，必须实现。
- 每条 Correctness Property（共 9 条）各对应一个独立属性测试子任务，标注属性号 + 验证的 requirements 条款；后端 hypothesis `max_examples=5`，前端 fast-check `numRuns: 5`，标签 `Feature: global-refinement-v5-closure, Property N`。
- 三层一致（C/D 域）：DB 迁移（V057/V058 + R 回滚）+ ORM `Mapped[]` + service 方法是各自独立可验收子任务，缺一视为伪绿。
- 关键约束已写入相关任务验收：codegraph impact 先查（GtAmountCell）、check_file_size 门禁、UI 中文/GtAmountCell/GT 紫令牌、service 只 flush router commit、迁移 `IF NOT EXISTS` + 数字排号避撞 V056、PG-only 测试标 `pg_only` marker。
- 每个能力域末尾含"实测验收"任务（pytest/vitest/必要时 Playwright），对齐"getDiagnostics 过≠运行时无错"铁律。
- 本工作流仅产出规划工件。开始执行可打开 tasks.md 点击任务项旁的"Start task"。
