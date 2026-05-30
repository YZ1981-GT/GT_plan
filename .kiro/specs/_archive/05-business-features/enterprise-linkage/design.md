# 设计文档：企业级联动

## 概述

本设计实现审计调整分录与底稿、试算平衡表的实时联动，支持企业级多人协同（目标 6000 并发用户）。

核心策略：**复用现有基础设施**（SSE 通道 + EventBus + outbox + useEditingLock 模式 + Redis），在此基础上扩展 Presence 服务、冲突守卫、联动指示器和影响预判能力。

### 设计原则

1. **MVP 优先**：2-3 周可交付，不过度设计
2. **复用优先**：SSE 已有 → 扩展事件类型；editing_locks 表已有 → 扩展为通用锁；usePenetrate 已有 → 扩展返回栈
3. **渐进增强**：先实现核心联动（需求 1-5），再补充监控/权限/降级（需求 7-15）
4. **性能预算驱动**：每个组件设计时明确延迟/吞吐目标

## 架构

### 整体架构图

```mermaid
graph TB
    subgraph Frontend
        A[Adjustments.vue] -->|创建/修改/删除| API
        TB[TrialBalance.vue] -->|自动刷新| SSE_Client
        WP[Workpaper.vue] -->|关联查看| LinkageIndicator
        SSE_Client[SSE Client] -->|sse:sync-event| EventBus_FE[eventBus]
        EventBus_FE --> useProjectEvents
        EventBus_FE --> usePresence
    end

    subgraph Backend
        API[FastAPI Router] -->|写入| DB[(PostgreSQL)]
        API -->|发布事件| EventBus_BE[EventBus]
        EventBus_BE -->|订阅| TBService[TrialBalanceService]
        EventBus_BE -->|订阅| ReportService[ReportService]
        EventBus_BE -->|notify_sse| SSE_Queue[SSE Queues]
        SSE_Queue -->|推送| SSE_Endpoint[/events/stream]
        PresenceService[PresenceService] -->|读写| Redis[(Redis)]
        ConflictGuard[ConflictGuard] -->|读写| DB
    end

    SSE_Endpoint -->|Server-Sent Events| SSE_Client
```

### 架构决策

**D1：SSE 通道复用（需求 1、11）**
- 复用现有 `/api/projects/{project_id}/events/stream` 端点
- 扩展 `EventType` 枚举新增 `presence.*` 和 `linkage.*` 事件
- 前端 `ThreeColumnLayout` 已连接 SSE，新事件自动通过 `eventBus.emit('sse:sync-event')` 分发
- 断连重试已有（maxRetries=5, retryInterval=3000ms），需求 1.7 的 10 秒重连 + 增量拉取通过扩展 `createSSE` 实现

**D2：Presence 基于 Redis Sorted Set（需求 2）**
- 使用 Redis ZSET 存储在线用户，score = 最后心跳时间戳
- Key 设计：`presence:{project_id}:{view_name}` → ZSET(user_id → timestamp)
- 心跳 30 秒一次，60 秒无心跳自动过期（ZRANGEBYSCORE 过滤）
- 编辑状态额外用 Hash：`presence:editing:{project_id}` → Hash(user_id → JSON{view, account_code, started_at})

**D3：冲突守卫复用 editing_locks 模式（需求 5）**
- 扩展现有 `workpaper_editing_locks` 表模式，新建 `adjustment_editing_locks` 表
- 锁粒度：单笔调整分录（entry_group_id 级别）
- 复用 `useEditingLock` composable 模式，新增 `resourceType: 'adjustment'`
- 乐观锁：Adjustment 表新增 `version` 列，UPDATE 时 WHERE version = expected

**D4：联动指示器基于预计算缓存（需求 3）**
- 试算平衡表行 → 调整分录关联：通过 `account_code` JOIN `adjustments` 实时查询（数据量小，129 行 × 平均 5 笔分录）
- 试算平衡表行 → 底稿关联：通过 `wp_account_mapping` 查询
- 不做预计算表，直接 JOIN 查询（单项目数据量可控）

**D5：影响预判基于公式引擎反向查询（需求 4）**
- 输入科目编码 → 查 `account_mapping` 得标准科目 → 查 `report_config` 得报表行次 → 查 `wp_account_mapping` 得底稿
- 前端输入防抖 300ms 后调用，后端 200ms 内返回
- 复用现有 `formula_engine.py` 的 TB()/SUM_TB() 解析逻辑反向查找

**D6：批量操作合并事件（需求 9）**
- 现有 `batch_commit` 端点已支持批量写入
- 扩展：写入完成后发布单条 `ADJUSTMENT_BATCH_COMMITTED` 事件（含 affected_account_codes 列表）
- `event_handlers.py` 订阅此事件，触发一次性 TB 重算（非逐条）

**D7：跨年度隔离（需求 14）**
- 所有联动查询强制带 `project_id + year` 条件
- SSE 事件 payload 已含 `year` 字段，前端过滤当前年度事件
- 期初数据独立于期末联动链路（已有 `tbSumPeriod` 切换）

**D8：通知疲劳控制（需求 15）**
- 前端 localStorage 存储通知偏好（实时/5 分钟汇总/仅手动）
- 合并逻辑在前端实现：5 分钟窗口内同项目 >10 条事件 → 合并为一条汇总
- 冲突守卫通知不受静默模式影响

**D9：权限过滤（需求 12）**
- SSE 推送时后端按 `ProjectAssignment.role` 过滤
- 助理只收到与自己负责科目相关的事件（通过 `workpaper_assignments` 关联的 account_code 过滤）
- 前端联动指示器根据 `ROLE_PERMISSIONS` 决定是否显示底稿徽章

**D10：审计轨迹（需求 8）**
- 复用现有 `audit_log_entries` 表（哈希链审计日志）
- 调整分录 CRUD 时自动记录 `audit_logger.log_action`
- 试算平衡表变更历史：新建 `tb_change_history` 表记录每次审定数变化

## 组件和接口

### 后端新增模块

```
backend/app/services/
├── presence_service.py          # Redis Presence 服务
├── conflict_guard_service.py    # 调整分录冲突守卫
├── linkage_service.py           # 联动查询（指示器 + 影响预判）
└── event_cascade_monitor.py     # 级联健康监控

backend/app/routers/
├── presence.py                  # Presence API
├── linkage.py                   # 联动查询 API
└── admin_event_health.py        # 管理后台事件健康
```

### 前端新增模块

```
audit-platform/frontend/src/
├── composables/
│   ├── usePresence.ts           # 在线感知 composable
│   ├── useConflictGuard.ts      # 冲突守卫 composable（扩展 useEditingLock）
│   ├── useLinkageIndicator.ts   # 联动指示器数据
│   ├── useImpactPreview.ts      # 影响预判
│   └── useNavigationStack.ts    # 穿透导航返回栈
├── components/
│   ├── PresenceAvatars.vue      # 在线成员头像列表
│   ├── LinkageBadge.vue         # 联动徽章（调整分录数/底稿数）
│   ├── LinkagePopover.vue       # 联动详情弹出面板
│   ├── ImpactPreviewPanel.vue   # 影响预判面板
│   └── ConflictDialog.vue       # 冲突提示对话框
```

### API 端点设计

#### Presence API（`/api/projects/{project_id}/presence`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/heartbeat` | 心跳上报（含 view_name, editing_info） |
| GET | `/online` | 获取当前在线成员列表 |
| GET | `/editing` | 获取当前编辑状态列表 |

#### Linkage API（`/api/projects/{project_id}/linkage`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tb-row/{row_code}/adjustments` | 试算表行关联的调整分录 |
| GET | `/tb-row/{row_code}/workpapers` | 试算表行关联的底稿 |
| GET | `/impact-preview` | 影响预判（query: account_code, amount） |
| GET | `/change-history/{row_code}` | 审定数变更历史时间线 |

#### Conflict Guard API（`/api/projects/{project_id}/adjustments`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/{entry_group_id}/lock` | 获取编辑锁 |
| PATCH | `/{entry_group_id}/lock/heartbeat` | 续期 |
| DELETE | `/{entry_group_id}/lock` | 释放锁 |

#### 批量重分类 API（`/api/projects/{project_id}/adjustments`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/reclassification/template` | 导出重分类 Excel 模板 |
| POST | `/reclassification/import` | 导入重分类 Excel |
| POST | `/reclassification/inline-submit` | 多行录入一键提交 |

#### 管理后台（`/api/admin`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/event-health` | 事件级联健康列表（最近 100 条） |

## 数据模型

### 新增表

#### `adjustment_editing_locks`

```sql
CREATE TABLE adjustment_editing_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    entry_group_id UUID NOT NULL,
    locked_by UUID NOT NULL REFERENCES users(id),
    locked_by_name VARCHAR(100),
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at TIMESTAMPTZ,
    CONSTRAINT idx_adj_lock_active UNIQUE (entry_group_id) 
        -- 部分唯一索引在 PG 中用 WHERE released_at IS NULL 实现
);
CREATE INDEX idx_adj_lock_heartbeat ON adjustment_editing_locks(heartbeat_at);
CREATE INDEX idx_adj_lock_project ON adjustment_editing_locks(project_id);
```

#### `tb_change_history`

```sql
CREATE TABLE tb_change_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    year INT NOT NULL,
    row_code VARCHAR(20) NOT NULL,
    operation_type VARCHAR(30) NOT NULL,  -- adjustment_created/modified/deleted/manual_edit/reclassification
    operator_id UUID NOT NULL REFERENCES users(id),
    operator_name VARCHAR(100),
    delta_amount NUMERIC(20,2),
    audited_after NUMERIC(20,2),
    source_adjustment_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tb_history_row ON tb_change_history(project_id, year, row_code, created_at DESC);
```

#### `event_cascade_log`

```sql
CREATE TABLE event_cascade_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT,
    trigger_event VARCHAR(50) NOT NULL,
    trigger_payload JSONB,
    steps JSONB NOT NULL DEFAULT '[]',  -- [{step, status, started_at, completed_at, error}]
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- running/completed/degraded/failed
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    total_duration_ms INT
);
CREATE INDEX idx_cascade_log_project ON event_cascade_log(project_id, started_at DESC);
CREATE INDEX idx_cascade_log_status ON event_cascade_log(status) WHERE status != 'completed';
```

### 现有表修改

#### `adjustments` 表新增列

```sql
ALTER TABLE adjustments ADD COLUMN version INT NOT NULL DEFAULT 1;
```

### Redis Key 设计

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `presence:{project_id}:{view}` | ZSET | 无（靠 score 过期） | 在线用户，score=unix_ts |
| `presence:editing:{project_id}` | HASH | 无（心跳维护） | 编辑状态，field=user_id, value=JSON |
| `linkage:notify:{project_id}` | LIST | 300s | 通知合并缓冲区 |
| `linkage:cascade:{cascade_id}` | STRING | 60s | 级联执行锁（防重复触发） |

### SSE 事件 Schema 扩展

新增 EventType 枚举值：

```python
# 联动事件
ADJUSTMENT_BATCH_COMMITTED = "adjustment.batch_committed"
LINKAGE_CASCADE_DEGRADED = "linkage.cascade_degraded"

# Presence 事件
PRESENCE_JOINED = "presence.joined"
PRESENCE_LEFT = "presence.left"
PRESENCE_EDITING_STARTED = "presence.editing_started"
PRESENCE_EDITING_STOPPED = "presence.editing_stopped"
```

事件 payload 扩展（通过 `extra` 字段）：

```json
// adjustment.created/updated/deleted
{
  "event_type": "adjustment.created",
  "project_id": "...",
  "year": 2025,
  "account_codes": ["1001", "6001"],
  "entry_group_id": "...",
  "extra": {
    "operator_name": "张三",
    "adjustment_no": "AJE-001",
    "affected_row_codes": ["BS-002", "IS-001"]
  }
}

// trial_balance.updated（增量刷新）
{
  "event_type": "trial_balance.updated",
  "project_id": "...",
  "year": 2025,
  "extra": {
    "affected_row_codes": ["BS-002", "BS-003", "IS-001"],
    "trigger": "adjustment.created"
  }
}

// presence.joined
{
  "event_type": "presence.joined",
  "project_id": "...",
  "extra": {
    "user_id": "...",
    "user_name": "李四",
    "avatar": "...",
    "view": "trial_balance"
  }
}
```

## 正确性属性

*属性（Property）是在系统所有合法执行中都应成立的特征或行为——本质上是对系统应做什么的形式化陈述。属性是人类可读规格说明与机器可验证正确性保证之间的桥梁。*

### Property 1: 调整分录 CRUD 操作产生正确事件类型

*For any* 调整分录 CRUD 操作（create/update/delete），EventBus 应发布与操作类型完全对应的事件（adjustment.created / adjustment.updated / adjustment.deleted），且事件 payload 包含正确的 project_id、year 和 account_codes。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 事件级联链路完整性

*For any* adjustment 变更事件被 EventBus 发布后，event_handlers 应依次触发 TB 重算，且 TB 重算完成后应发布 trial_balance.updated 事件（含 affected_row_codes 列表）。

**Validates: Requirements 1.4, 1.5**

### Property 3: 试算平衡表增量刷新正确性

*For any* trial_balance.updated 事件，其 extra.affected_row_codes 列表应恰好包含被变更调整分录影响的所有试算表行次编码（不多不少）。

**Validates: Requirements 1.6**

### Property 4: Presence 视图记录一致性

*For any* 用户进入某视图并发送心跳，Presence_Service 的在线列表应包含该用户且 view 字段正确；心跳超过 60 秒未更新后，该用户应从在线列表中消失。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 5: 编辑锁定状态广播

*For any* 用户获取调整分录编辑锁，Presence_Service 的 editing 状态应包含该用户的 user_id、account_code 和 entry_group_id；释放锁后该记录应消失。

**Validates: Requirements 2.5**

### Property 6: 联动指示器零值隐藏

*For any* 试算平衡表行，当该行关联的调整分录数量为 0 时，联动查询接口应返回空列表（前端据此不渲染徽章）。

**Validates: Requirements 3.5**

### Property 7: 影响预判完整性

*For any* 在 account_mapping 中存在映射的科目编码，影响预判接口应返回非空的 affected_tb_rows 列表；且返回的报表行次应与 report_config 中引用该标准科目的公式行一致。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 8: 已锁定报表警告

*For any* 影响预判结果中包含 status=final 的报表，响应应包含 `has_final_report_warning: true` 标记。

**Validates: Requirements 4.5**

### Property 9: 编辑锁互斥性

*For any* 已被用户 A 锁定的调整分录（entry_group_id），用户 B 尝试获取锁时应返回 409 状态码及锁定者信息；用户 A 释放锁后，用户 B 应能成功获取。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 10: 心跳过期自动释放

*For any* 编辑锁记录，若 heartbeat_at 距当前时间超过 60 秒，该锁应被视为过期（后续 acquire 请求应成功）。

**Validates: Requirements 5.4**

### Property 11: 乐观锁版本冲突检测

*For any* 调整分录更新请求，若请求中的 version 与数据库当前 version 不一致，应返回 409 VERSION_CONFLICT 错误。

**Validates: Requirements 5.5**

### Property 12: 穿透导航栈正确性（Round-trip）

*For any* 穿透跳转操作，导航栈应增加一条记录（含 source_view、row_index、scroll_position）；执行 Backspace 返回后，应恢复到跳转前的视图和位置（栈减少一条）。

**Validates: Requirements 6.5, 6.6**

### Property 13: 事件级联日志记录

*For any* 事件级联执行（无论成功或失败），event_cascade_log 表应新增一条记录，包含 trigger_event、steps 数组和最终 status。

**Validates: Requirements 7.1, 7.2**

### Property 14: 审计轨迹完整性

*For any* 调整分录 CRUD 操作，tb_change_history 表应新增对应记录，包含 operator_id、operation_type、delta_amount 和 audited_after 五个必填字段。

**Validates: Requirements 8.1, 8.2, 8.4**

### Property 15: 批量操作单次级联

*For any* 批量提交 N 笔调整分录，系统应只触发一次 TB 重算（非 N 次），且只发布一条 SSE 汇总事件。

**Validates: Requirements 9.1, 9.2, 9.3**

### Property 16: 批量操作原子性

*For any* 批量提交中某笔分录校验失败，整批操作应回滚（数据库无任何写入），且返回失败原因。

**Validates: Requirements 9.5**

### Property 17: 试算平衡表恒等式不变量

*For all* 调整分录变更操作完成后，试算平衡表每行的审定数必须满足：`audited = unadjusted + aje_dr - aje_cr + rcl_dr - rcl_cr`。

**Validates: Requirements 10.6**

### Property 18: 一致性校验差异检测

*For any* 一致性校验执行，若增量计算结果与全量重算结果存在差异，应返回差异明细列表（含 row_code、incremental_value、full_value、diff）。

**Validates: Requirements 10.4**

### Property 19: 跨年度隔离

*For any* 调整分录变更事件（project_id=P, year=Y），联动链路只应影响同一 P+Y 范围内的试算平衡表数据；期初试算表（opening）不受当年调整影响。

**Validates: Requirements 14.1, 14.2, 14.3**

### Property 20: 通知合并

*For any* 5 分钟窗口内同一项目产生超过 10 条事件，前端通知系统应将其合并为一条汇总通知；但冲突守卫类通知不受合并影响。

**Validates: Requirements 15.2, 15.4**

### Property 21: 角色权限过滤

*For any* SSE 事件推送和联动查询，系统应根据用户的 ProjectAssignment.role 过滤内容：助理不可见合伙人/EQCR 编辑状态，无底稿权限用户不可见底稿关联。

**Validates: Requirements 12.1, 12.2, 12.3, 12.4**

### Property 22: 重分类导入拆分正确性

*For any* 导入的重分类 Excel 数据，系统应按连续借贷平衡组拆分为独立分录：每组内 sum(debit) = sum(credit)；不平衡组应标记为"待修正"。

**Validates: Requirements 16.2, 16.3, 16.4**

### Property 23: 多行录入借贷平衡门控

*For any* 多行录入提交请求，当 sum(debit_amount) ≠ sum(credit_amount) 时应拒绝提交（返回 400）。

**Validates: Requirements 16.6**

### Property 24: SSE 降级轮询

*For any* SSE 连接断开超过 10 秒的状态，前端应切换为 30 秒轮询模式；SSE 恢复后应停止轮询并拉取断连期间的增量事件。

**Validates: Requirements 11.2, 11.3**

## 错误处理

### 后端错误处理

| 场景 | 处理方式 |
|------|----------|
| Redis 不可用 | Presence 降级为"不显示在线状态"，不阻断业务操作 |
| SSE 推送失败 | 记录日志，不影响数据写入（最终一致性） |
| TB 重算超时 | 标记级联为 degraded，前端显示黄色横幅 |
| 编辑锁获取失败（DB 异常） | 返回 500，前端提示"系统繁忙" |
| 版本冲突 | 返回 409 + 最新版本数据，前端自动刷新 |
| 批量操作部分失败 | 整批回滚，返回失败行号和原因 |
| 影响预判查询超时 | 返回部分结果 + `incomplete: true` 标记 |

### 前端错误处理

| 场景 | 处理方式 |
|------|----------|
| SSE 断连 | 3 秒重试 × 5 次，超过后降级为轮询 + 橙色横幅 |
| Presence 心跳失败 | 静默重试，不影响用户操作 |
| 联动查询失败 | 隐藏徽章，不阻断主视图 |
| 影响预判超时 | 显示"计算中..."，3 秒后显示"暂无法计算" |
| 编辑锁心跳失败 | 连续 3 次失败后提示"锁可能已失效" |

## 测试策略

### 属性测试（Property-Based Testing）

- 使用 **Hypothesis** 库（已安装 v6.152.4）
- 每个属性测试最少 100 次迭代
- 测试文件：`backend/tests/test_enterprise_linkage_properties.py`
- 标签格式：`# Feature: enterprise-linkage, Property {N}: {title}`

重点属性测试：
1. **Property 17（恒等式不变量）**：生成随机调整分录集合，执行 recalc，验证每行 audited = formula
2. **Property 9（锁互斥性）**：生成随机用户对和 entry_group_id，验证并发锁行为
3. **Property 15（批量单次级联）**：生成 1-50 笔随机分录，验证只触发一次 recalc
4. **Property 22（重分类拆分）**：生成随机借贷行序列，验证拆分正确性
5. **Property 19（跨年度隔离）**：生成跨年度调整分录，验证隔离性

### 单元测试

- 编辑锁获取/释放/过期的具体场景
- SSE 事件 payload 结构验证
- Presence Redis 操作的 mock 测试
- 影响预判的边界情况（未映射科目、空映射等）
- 通知合并的时间窗口边界

### 集成测试

- 调整分录创建 → SSE 事件 → TB 重算 → 前端刷新 全链路
- 批量提交 → 单次级联 → 汇总事件 全链路
- 编辑锁 + Presence 联动（锁定时 Presence 显示编辑状态）

### 性能测试

- TB 增量重算 < 500ms（129 行，单笔调整）
- 影响预判 < 200ms
- Presence 心跳 Redis 操作 < 1ms
- 50 笔批量操作联动 < 10s

