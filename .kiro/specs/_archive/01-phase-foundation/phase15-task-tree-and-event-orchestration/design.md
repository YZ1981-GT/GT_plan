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
-- 四级任务树节点
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

-- 事件总线与补偿队列
CREATE TABLE task_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,  -- trim_applied/trim_rollback/task_reassigned/...
    task_node_id UUID NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL,      -- queued/replaying/succeeded/failed/dead_letter
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    next_retry_at TIMESTAMP NULL,     -- 下次重试时间（指数退避）
    error_message TEXT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 统一问题单（对齐 v2 4.5.15A）
CREATE TABLE issue_tickets (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    task_node_id UUID NULL REFERENCES task_tree_nodes(id),
    conversation_id UUID NULL,         -- 关联复核对话
    source VARCHAR(16) NOT NULL,       -- L2/L3/Q（对齐 v2 4.5.15A）
    severity VARCHAR(16) NOT NULL,     -- blocker/major/minor/suggestion
    category VARCHAR(64) NOT NULL,     -- data_mismatch/evidence_missing/explanation_incomplete/procedure_incomplete/policy_violation
    title VARCHAR(200) NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL,
    due_at TIMESTAMP NULL,
    entity_id UUID NULL,
    account_code VARCHAR(20) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- open/in_fix/pending_recheck/closed/rejected
    thread_id UUID NULL,               -- 关联对话线程
    evidence_refs JSONB DEFAULT '[]'::jsonb,
    reason_code VARCHAR(64) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP NULL
);

-- RC 会话表增强（对齐 v2 5.9.16.4）
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'medium';
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS sla_due_at TIMESTAMP NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_by UUID NULL REFERENCES users(id);
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(64) NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL;

-- RC 消息表增强（对齐 v2 5.9.16.3）
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reply_to UUID NULL REFERENCES review_messages(id);
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS mentions JSONB NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP NULL;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS redaction_flag BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS message_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reason_code VARCHAR(64) NULL;

-- RC 参与者表（对齐 v2 5.9.16.1）
CREATE TABLE review_conversation_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES review_conversations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    participant_role VARCHAR(32) NOT NULL, -- initiator/target/reviewer/observer
    is_required_ack BOOLEAN NOT NULL DEFAULT false,
    joined_at TIMESTAMP NOT NULL DEFAULT now(),
    left_at TIMESTAMP NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, user_id, is_deleted)
);

-- RC 导出留痕表（对齐 v2 5.9.16.2）
CREATE TABLE review_conversation_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    export_id VARCHAR(64) NOT NULL UNIQUE,
    conversation_id UUID NOT NULL REFERENCES review_conversations(id),
    project_id UUID NOT NULL REFERENCES projects(id),
    requested_by UUID NOT NULL REFERENCES users(id),
    export_scope VARCHAR(32) NOT NULL,  -- full_timeline/summary/attachments_only
    purpose VARCHAR(200) NOT NULL,
    receiver VARCHAR(200) NOT NULL,
    mask_policy VARCHAR(64) NOT NULL,
    include_hash_manifest BOOLEAN NOT NULL DEFAULT true,
    file_path TEXT NULL,
    file_hash VARCHAR(128) NULL,
    trace_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created', -- created/ready/failed
    error_code VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP NULL
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
重试策略：`1m -> 5m -> 15m`，超限进入 dead-letter 队列（status=dead_letter）。  
dead-letter 告警：进入 dead-letter 后立即触发 P1 告警通知值班。

### 4.3 IssueTicketService（对齐 v2 4.5.15A）

```python
class IssueTicketService:
    """统一问题单：L2/L3/Q 问题统一管理"""

    async def create_from_conversation(self, conversation_id, task_node_id,
                                        operator_id, sla_level) -> dict:
        """
        对话转问题单：
        1. 从 review_conversations 提取上下文（project_id/wp_id/title）
        2. 创建 issue_ticket（source 从对话发起角色推断 L2/L3/Q）
        3. 绑定 task_node_id（可选）
        4. 设置 due_at（按 sla_level: P0=4h, P1=24h, P2=72h，对齐 v2 5.7A）
        5. 写入 trace_events
        """

    async def update_status(self, issue_id, status, operator_id, reason_code,
                            evidence_refs=None) -> dict:
        """
        状态流转：open -> in_fix -> pending_recheck -> closed/rejected
        - 关键动作（退回/关闭/驳回）必须带 reason_code 和 evidence_refs
        - 超时未结论（48h）自动升级给项目经理与合伙人（对齐 v2 4.5.15A）
        """

    async def escalate(self, issue_id, from_level, to_level, reason_code) -> dict:
        """
        升级链路：L2 -> L3 -> Q
        - 同一底稿同类问题被退回>=2次，自动升级为 L3 必审
        - Q 轨道驳回项目组关闭结论时，生成争议处理单
        """

    async def list_issues(self, project_id, filters, page, page_size) -> dict:
        """按项目/状态/severity/source/owner 检索"""
```

### 4.4 RC 增强服务（对齐 v2 5.9.14~5.9.17）

```python
class ReviewConversationEnhancedService:
    """复核对话增强：参与者管理 + 导出留痕 + 关闭态门禁"""

    async def add_participant(self, conversation_id, user_id, role, is_required_ack=False): ...
    async def export_evidence(self, conversation_id, purpose, receiver,
                               export_scope, mask_policy, include_hash_manifest) -> dict:
        """
        取证导出（对齐 v2 5.9.14.6）：
        1. 校验必填字段（purpose/receiver/mask_policy）
        2. 构建导出内容（按 export_scope）
        3. 计算 file_hash
        4. 写入 review_conversation_exports
        5. 写入 trace_events
        """

    # 关闭态门禁：status=closed/resolved 时普通消息阻断（对齐 v2 5.9.16.5 触发器逻辑）
```

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

GET /api/issues
  - query: project_id, status, severity, source, owner_id, page, page_size
  - response: { items[], total, page, page_size, trace_id }

PUT /api/issues/{issue_id}/status
  - body: { status, operator_id, reason_code, evidence_refs[] }
  - response: { issue_id, status, trace_id }

POST /api/issues/{issue_id}/escalate
  - body: { from_level, to_level, reason_code }
  - response: { issue_id, escalated_to, trace_id }

POST /api/review-conversations/{id}/export-evidence
  - body: { purpose, receiver, export_scope, mask_policy, include_hash_manifest }
  - response: { export_id, file_url, hash, trace_id }
  - 对齐 v2 5.9.14.6
```

关键错误码：
- `TASK_NODE_NOT_FOUND`
- `TASK_STATUS_INVALID_TRANSITION`
- `TASK_EVENT_REPLAY_LIMIT`
- `ISSUE_SLA_POLICY_MISSING`
- `ISSUE_NOT_FOUND`
- `ISSUE_STATUS_INVALID_TRANSITION`
- `RC_PERMISSION_DENIED` — 非参与者访问会话（对齐 v2 5.9.14.7）
- `RC_CONVERSATION_CLOSED` — 关闭态发送普通消息（对齐 v2 5.9.14.7）
- `RC_EXPORT_COMPLIANCE_BLOCKED` — 导出条件未满足（对齐 v2 5.9.14.7）
- `RC_REQUIRED_FIELD_MISSING` — 关闭/导出必填字段缺失（对齐 v2 5.9.14.7）

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

