# Phase 15: 四级任务树与事件编排补偿 - 设计文档

---

## 1. 核心设计理念

### 1.1 编排驱动原则

```
业务动作（裁剪/恢复/转派/升级）
          ↓
      TaskEventBus
          ↓
   TaskTreeOrchestrator
          ↓
   状态机变更 + 补偿队列
          ↓
  问题线程升级（L2/L3/Q）
```

设计原则：
- 任务状态统一，不允许业务侧自定义同义状态。
- 所有事件先入总线，再执行业务动作，失败统一进入补偿池。
- 问题线程与任务节点强绑定，保证“讨论 -> 处置 -> 关闭”闭环。

---

## 2. 系统架构

### 2.1 模块结构

| 模块 | 职责 |
|------|------|
| `TaskTreeService` | 节点增删改查、层级聚合、状态统计 |
| `TaskEventBus` | 事件发布、消费、幂等与重试 |
| `TaskCompensationService` | 失败事件补偿、人工重放 |
| `IssueTicketService` | 对话转问题单、SLA升级与通知 |

### 2.2 状态流转

| 当前状态 | 触发条件 | 下一状态 |
|------|---------|---------|
| `pending` | 开始执行 | `in_progress` |
| `in_progress` | 阻断命中 | `blocked` |
| `blocked` | 阻断解除 | `in_progress` |
| `in_progress` | 校验通过 | `done` |

---

## 3. 数据模型变更

```sql
CREATE TABLE task_tree_nodes (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    node_level VARCHAR(16) NOT NULL, -- unit/account/workpaper/evidence
    parent_id UUID NULL,
    ref_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,      -- pending/in_progress/blocked/done
    assignee_id UUID NULL,
    due_at TIMESTAMP NULL,
    meta JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE task_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,  -- trim_applied/trim_rollback/task_reassigned/...
    task_node_id UUID NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL,      -- queued/replaying/succeeded/failed
    retry_count INT DEFAULT 0,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 4. 核心服务设计

### 4.1 TaskTreeService

```python
class TaskTreeService:
    async def build_tree(self, project_id): ...
    async def list_nodes(self, project_id, filters, page, page_size): ...
    async def transit_status(self, node_id, next_status, operator_id): ...
    async def reassign(self, node_id, assignee_id, operator_id, reason_code): ...
```

### 4.2 TaskEventBus / Compensation

```python
class TaskEventBus:
    async def publish(self, event_type, payload, trace_id): ...
    async def consume(self, event_id): ...
    async def replay(self, event_id, operator_id, reason_code): ...
```

幂等键：`project_id + event_type + ref_id + version`  
重试策略：`1m -> 5m -> 15m`，超限进入 dead-letter 队列。

---

## 5. API 设计

```yaml
GET /api/task-tree
  - query: project_id, root_level, status, assignee_id, page, page_size
  - response: { items[], total, page, page_size, trace_id }

POST /api/task-tree/reassign
  - body: { task_node_id, assignee_id, operator_id, reason_code }
  - response: { item, trace_id }

POST /api/task-events/replay
  - body: { event_id, operator_id, reason_code }
  - response: { event_id, status, trace_id }

POST /api/issues/from-conversation
  - body: { conversation_id, task_node_id, operator_id, sla_level }
  - response: { issue_id, status, trace_id }
```

关键错误码：
- `TASK_NODE_NOT_FOUND`
- `TASK_STATUS_INVALID_TRANSITION`
- `TASK_EVENT_REPLAY_LIMIT`
- `ISSUE_SLA_POLICY_MISSING`

---

## 6. 关键机制

### 6.1 事件 SLA 策略

| 级别 | 首次处理时限 | 升级动作 |
|------|-------------|---------|
| P0 | 15分钟 | 通知值班 + 项目经理 |
| P1 | 2小时 | 通知模块负责人 |
| P2 | 1工作日 | 周会汇总处理 |

### 6.2 线程升级机制

1. 对话转问题单后写入 `task_node_id`。  
2. 到期未处理自动升级（L2->L3->Q）。  
3. 升级与回滚动作必须写入 `reason_code` 与 `trace_id`。

---

## 7. 测试与回滚策略

| 测试层 | 用例 | 通过标准 |
|------|------|---------|
| UT | 树构建/状态迁移/幂等键 | 核心分支覆盖 >= 80% |
| IT | trim 事件联动与补偿 | 状态一致性 >= 99% |
| E2E | 对话升级到关闭全链路 | 留痕完整、SLA生效 |
| REL | dead-letter 重放恢复 | 重放成功率 >= 99% |

回滚策略：
- 事件处理异常时仅回滚本次事件，不回滚已成功节点。
- 重放失败保留在补偿池，禁止直接删除。

