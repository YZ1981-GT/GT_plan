# Phase 14: 统一门禁引擎与治理收敛 - 设计文档

---

## 1. 核心设计理念

### 1.1 三入口统一判定原则

```
提交复核 / 签字 / 导出
        ↓
   统一 GateEngine
        ↓
 RuleRegistry（QC-01~QC-26）
        ↓
 DecisionAssembler（block/warn/allow）
        ↓
 gate_decisions + trace_events
```

关键原则：
- 同一上下文在三入口必须得到同一判定结果。
- 阻断类规则必须同时返回“定位 + 修复建议”。
- 所有门禁结果必须具备 `trace_id`，可回放、可审计。

### 1.2 规则分层原则

| 层级 | 说明 |
|------|------|
| 平台强制规则 | 不允许租户覆盖（如关键合规阻断） |
| 租户可配置规则 | 允许调整阈值（如告警阈值） |
| 解释模板层 | 规则命中后输出统一修复建议文案 |

---

## 2. 系统架构

### 2.1 逻辑架构

```
API 入口层
  submit-review / sign-off / export
         ↓
GateEngine.evaluate()
         ↓
RuleRegistry + ContextResolver
         ↓
DecisionAssembler
         ↓
Persistence(gate_decisions) + Trace(trace_events)
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| `GateEngine` | 统一调度规则、输出决策 |
| `RuleRegistry` | 注册规则与入口适用范围 |
| `ContextResolver` | 组装规则执行上下文 |
| `DecisionAssembler` | 聚合命中规则并排序 |
| `GateDecisionService` | 门禁结果落库与查询 |

---

## 3. 数据模型变更

```sql
-- 统一过程留痕主表（对齐 v2 WP-ENT-01 / 5.9.3 D-01）
CREATE TABLE trace_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,       -- wp_saved/submit_review/sign_off/export/trim_applied/trim_rollback/gate_evaluated/sod_checked
    object_type VARCHAR(32) NOT NULL,      -- workpaper/adjustment/report/note/procedure/conversation
    object_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    actor_role VARCHAR(32),
    action VARCHAR(100) NOT NULL,
    decision VARCHAR(16),                  -- allow/block/warn（门禁场景）
    reason_code VARCHAR(64),
    before_snapshot JSONB,
    after_snapshot JSONB,
    content_hash VARCHAR(64),              -- 对象内容 hash（取证用）
    version_no INT,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_trace_events_project ON trace_events(project_id, event_type, created_at DESC);
CREATE INDEX idx_trace_events_object ON trace_events(object_type, object_id, created_at DESC);
CREATE INDEX idx_trace_events_trace_id ON trace_events(trace_id);
CREATE INDEX idx_trace_events_actor ON trace_events(actor_id, created_at DESC);

-- 门禁决策记录表
CREATE TABLE gate_decisions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    gate_type VARCHAR(32) NOT NULL, -- submit_review/sign_off/export_package
    decision VARCHAR(16) NOT NULL,  -- allow/warn/block
    hit_rules JSONB NOT NULL,
    actor_id UUID NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_gate_decisions_project_gate
ON gate_decisions(project_id, gate_type, created_at DESC);
```

---

## 4. 核心服务设计

### 4.1 GateEngine 服务

```python
class GateEngine:
    async def evaluate(self, gate_type, project_id, wp_id, actor_id, context) -> dict:
        """
        1. 解析上下文（快照、版本、AI确认状态）
        2. 加载适用规则（入口+租户配置）
        3. 执行规则并按 severity 排序
        4. 生成 decision（allow/warn/block）
        5. 落库 gate_decisions + trace_events（trace_id 贯穿）
        """
```

### 4.2 TraceEventService 服务（对齐 v2 WP-ENT-01）

```python
class TraceEventService:
    async def write(self, project_id, event_type, object_type, object_id,
                    actor_id, actor_role, action, decision=None, reason_code=None,
                    before_snapshot=None, after_snapshot=None, content_hash=None,
                    version_no=None, trace_id=None) -> str:
        """统一写入 trace_events，返回 trace_id"""

    async def replay(self, trace_id) -> dict:
        """
        按 trace_id 查询完整事件链，支持 L1/L2/L3 分级输出：
        - L1: 事件摘要（who/what/when）
        - L2: 含 before/after snapshot
        - L3: 含 content_hash 可复算校验
        """

    async def query(self, project_id, filters, page, page_size) -> dict:
        """按项目/对象/时间/角色检索 trace 事件"""
```

### 4.3 SoDGuardService 服务（对齐 v2 WP-ENT-04 + 4.5.14）

```python
class SoDGuardService:
    """编制/复核/签字/放行职责分离守卫"""

    # 互斥矩阵（对齐 v2 4.5.14）
    CONFLICT_MATRIX = {
        ("preparer", "partner_approver"): "同人编制+终审同一底稿",
        ("preparer", "reviewer"): "经理复核本人编制底稿（需合伙人审批例外）",
        ("qc_reviewer", "preparer"): "质控人员参与被抽查底稿修改",
    }

    async def check(self, project_id, wp_id, actor_id, target_role) -> dict:
        """
        校验角色冲突：
        1. 查询 actor_id 在该底稿上的已有角色
        2. 与 target_role 做互斥矩阵比对
        3. 冲突时返回 403 + policy_code + conflict_type
        4. 写入 trace_events（event_type=sod_checked）
        """
```

### 4.4 规则执行顺序

1. 合规阻断（mandatory）— 含 QC-19/QC-20 程序裁剪门禁
2. SoD 职责分离阻断（sod）— 编制/复核/签字互斥
3. 数据一致性阻断（consistency）  
4. AI确认与冲突阻断（ai/rule-conflict）  
5. 警告与提示（warning/info）

---

## 5. API 设计

### 5.1 门禁评估 API

```yaml
POST /api/gate/evaluate
  body:
    gate_type: submit_review|sign_off|export_package
    project_id: uuid
    wp_id: uuid?
    actor_id: uuid
    context: object
  response:
    decision: allow|warn|block
    hit_rules[]:
      - rule_code
      - error_code
      - severity
      - message
      - location: { wp_id, section, procedure_id? }
      - suggested_action
    trace_id: string
```

### 5.2 Trace 回放 API（对齐 v2 5.9.3 A-02）

```yaml
GET /api/trace/{trace_id}/replay
  query:
    level: L1|L2|L3  # L1=摘要, L2=含快照, L3=含hash可复算
  response:
    trace_id: string
    events[]:
      - id: uuid
      - event_type: string
      - object_type: string
      - object_id: uuid
      - actor_id: uuid
      - actor_role: string
      - action: string
      - decision: string?
      - reason_code: string?
      - before_snapshot: object?  # L2+
      - after_snapshot: object?   # L2+
      - content_hash: string?     # L3
      - version_no: int?
      - created_at: datetime
    replay_status: complete|partial|broken
```

### 5.3 SoD 校验 API（对齐 v2 WP-ENT-04）

```yaml
POST /api/sod/check
  body:
    project_id: uuid
    wp_id: uuid
    actor_id: uuid
    target_role: preparer|reviewer|partner_approver|qc_reviewer
  response:
    allowed: boolean
    conflict_type: string?       # 如 "同人编制+终审同一底稿"
    policy_code: string?         # 如 "SOD_PREPARER_APPROVER_CONFLICT"
    trace_id: string
```

### 5.4 关键错误码

| 错误码 | http | 含义 |
|------|---:|------|
| `QC_PROCEDURE_MANDATORY_TRIMMED` | 409 | mandatory 程序被裁剪（对齐 v2 QC-19） |
| `QC_PROCEDURE_EVIDENCE_MISSING` | 409 | conditional 裁剪缺少证据引用（对齐 v2 QC-20） |
| `QC_CONCLUSION_WITHOUT_EVIDENCE` | 409 | 关键结论缺少证据锚点（QC-21） |
| `QC_LOW_CONFIDENCE_SINGLE_SOURCE` | 409 | 低置信单点依赖（QC-22） |
| `QC_LLM_PENDING_CONFIRMATION` | 409 | 关键LLM内容未确认（QC-23） |
| `QC_LLM_TRIM_CONFLICT` | 409 | LLM采纳与裁剪冲突（QC-24） |
| `QC_REPORT_NOTE_VERSION_STALE` | 409 | 正文引用附注版本过期（QC-25） |
| `QC_NOTE_SOURCE_MAPPING_MISSING` | 409 | 关键披露缺来源映射（QC-26） |
| `SOD_CONFLICT_DETECTED` | 403 | 职责分离冲突（对齐 v2 WP-ENT-04） |
| `TRACE_NOT_FOUND` | 404 | trace_id 不存在 |
| `TRACE_REPLAY_INCOMPLETE` | 422 | 回放链路不完整 |
| `GATE_CONTEXT_INVALID` | 400 | 上下文字段缺失 |

---

## 6. 关键规则与机制

| 规则 | 触发条件 | 结果 |
|------|---------|------|
| `QC-19` | `mandatory` 程序 `trim_status=trimmed` | 阻断（对齐 v2 校验9） |
| `QC-20` | `conditional` 程序 `trim_status=trimmed` 且 `trim_evidence_refs` 为空 | 阻断（对齐 v2 校验10） |
| `QC-21` | 关键结论 `evidence_refs` 为空 | 阻断 |
| `QC-22` | 单证据且低置信支撑关键结论 | 阻断 |
| `QC-23` | `pending_user_confirm` 存在 | 阻断 |
| `QC-24` | LLM采纳与裁剪策略冲突 | 阻断 |
| `QC-25` | 正文引用附注版本过期 | 阻断 |
| `QC-26` | 关键披露缺 `source_cells` | 阻断 |

---

## 7. 测试与灰度策略

### 7.1 测试矩阵

| 测试层 | 用例 | 通过标准 |
|------|------|---------|
| UT | `QC-19~QC-26` 分支覆盖 | 每条规则通过/阻断各1例 |
| UT | SoD 互斥矩阵校验 | 每种冲突场景通过/阻断各1例 |
| UT | trace_events 写入与查询 | 字段完整性校验 |
| IT | 三入口一致性 | 判定一致率=100% |
| IT | trace 回放 L1/L2/L3 | 回放成功率>=99% |
| E2E | 前端阻断定位+修复后重提 | 可定位、可修复、可通过 |
| SEC | 越权写入攻击回归 | 越权写入=0 |
| SEC | SoD 绕过攻击回归 | SoD 冲突放行=0 |

### 7.2 灰度放量

- `10% -> 30% -> 100%` 项目放量，每阶段观察 24h。  
- 任一阶段误阻断率 > 3% 即回滚到上一阶段。  
- 回滚不清理 `gate_decisions`，仅回滚执行路径与规则配置。

---

## 8. 跨阶段字段契约（Phase 14/15/16 统一定义）

> Phase 15/16 引用本节定义，不重复定义。任何变更必须先回写本节再进入编码。

### 8.1 trace_id 生成规则

- 格式：`trc_{yyyyMMddHHmmss}_{uuid_short_12}`，如 `trc_20260428143500_a1b2c3d4e5f6`
- 长度：固定 32 字符（`trc_` 4 + 日期时间 14 + `_` 1 + uuid_short 12 = 31，补齐到 32）
- 唯一性：应用层生成，数据库不加 UNIQUE 约束（允许同一 trace_id 关联多条 trace_events）
- 跨表关联：trace_events.trace_id = gate_decisions.trace_id = task_events.trace_id = offline_conflicts.trace_id = version_line_stamps.trace_id
- 透传规则：API 请求入口生成，全链路透传到所有下游写入，禁止中途重新生成

### 8.2 reason_code 统一枚举（最小集，对齐 v2 4.5.6）

| reason_code | 适用场景 | 说明 |
|---|---|---|
| `DATA_MISMATCH` | 门禁/冲突/一致性 | 数据不一致 |
| `EVIDENCE_MISSING` | 门禁/问题单 | 证据不足 |
| `EXPLANATION_INCOMPLETE` | 门禁/QC | 审计说明不完整 |
| `PROCEDURE_INCOMPLETE` | 门禁/裁剪 | 程序执行未完成 |
| `POLICY_VIOLATION` | SoD/权限 | 权限或合规策略冲突 |
| `LLM_PENDING_CONFIRM` | 门禁/AI | LLM 内容未确认 |
| `LLM_TRIM_CONFLICT` | 门禁/AI | LLM 采纳与裁剪冲突 |
| `VERSION_STALE` | 门禁/版本链 | 引用版本过期 |
| `SOURCE_MAPPING_MISSING` | 门禁/附注 | 来源映射缺失 |
| `TRIM_MANDATORY` | 裁剪 | mandatory 程序被裁剪 |
| `TRIM_NO_EVIDENCE` | 裁剪 | conditional 裁剪无证据 |
| `SOD_CONFLICT` | SoD | 职责分离冲突 |
| `CONFLICT_ACCEPT_LOCAL` | 冲突合并 | 采纳本地值 |
| `CONFLICT_ACCEPT_REMOTE` | 冲突合并 | 采纳远程值 |
| `CONFLICT_MANUAL_MERGE` | 冲突合并 | 人工合并 |
| `SLA_TIMEOUT` | 问题单升级 | SLA 超时升级 |
| `RC_CREATE_MANUAL` | 复核对话 | 手动创建会话 |
| `RC_MSG_NORMAL` | 复核对话 | 普通消息 |
| `RC_RESOLVED_EVIDENCE_COMPLETE` | 复核对话 | 证据补齐后解决 |
| `RC_EXPORT_EVIDENCE` | 复核对话 | 取证导出 |

### 8.3 status 统一枚举

| 表 | status 枚举 | 说明 |
|---|---|---|
| trace_events | 无 status 字段 | 仅记录事件，不管理状态 |
| gate_decisions | `allow/warn/block` | 门禁判定结果 |
| task_tree_nodes | `pending/in_progress/blocked/done` | 任务节点状态（对齐 v2 5.7A） |
| task_events | `queued/replaying/succeeded/failed/dead_letter` | 事件处理状态 |
| issue_tickets | `open/in_fix/pending_recheck/closed/rejected` | 问题单状态（对齐 v2 4.5.15A） |
| offline_conflicts | `open/resolved/rejected` | 冲突处置状态 |
| review_conversations | `open/resolved/closed` | 会话状态 |
| evidence_hash_checks | `passed/failed` | 校验结果 |

### 8.4 severity 统一枚举

| 值 | 适用范围 | 说明 |
|---|---|---|
| `blocking` | gate_decisions.hit_rules | 阻断，必须修复后才能通过 |
| `warning` | gate_decisions.hit_rules | 警告，可确认后通过 |
| `info` | gate_decisions.hit_rules | 提示，不阻断 |
| `blocker` | issue_tickets | 重大问题，阻断签字 |
| `major` | issue_tickets | 一般问题，需限期修复 |
| `minor` | issue_tickets | 轻微问题 |
| `suggestion` | issue_tickets | 建议改进 |

---

## 9. 运维监控与告警（企业级）

### 9.1 Phase 14 监控指标

| 指标 | 采集方式 | 告警阈值 | 告警级别 |
|---|---|---|---|
| gate_engine 评估 QPS | Prometheus counter | — | 仅观测 |
| gate_engine 评估 P95 延迟 | Prometheus histogram | > 500ms 持续 5min | P1 |
| 门禁阻断率 | gate_decisions 统计 | — | 仅观测（异常波动人工排查） |
| 误阻断率 | 申诉通过数 / 阻断总数 | > 3% 持续 1 周 | P1 |
| trace_events 写入失败率 | 应用层 error counter | > 0.1% 持续 10min | P0 |
| SoD 校验 P95 延迟 | Prometheus histogram | > 200ms 持续 5min | P2 |

### 9.2 Phase 15 监控指标（Phase 15 实施时接入）

| 指标 | 告警阈值 | 告警级别 |
|---|---|---|
| dead-letter 队列深度 | > 10 条持续 30min | P1 |
| 事件补偿成功率 | < 95% 持续 1h | P1 |
| 任务树查询 P95 延迟 | > 2s 持续 5min | P2 |
| SLA 超时未升级数 | > 0 持续 4h | P0 |

### 9.3 Phase 16 监控指标（Phase 16 实施时接入）

| 指标 | 告警阈值 | 告警级别 |
|---|---|---|
| 取证包构建 P95 耗时 | > 60s | P1 |
| hash 校验失败率 | > 0 | P0 |
| 冲突检测漏检率 | > 0 | P0 |
| 一致性复算阻断级差异数 | > 0 且未联动签字门禁 | P0 |

---

## 10. 数据迁移与兼容策略

### 10.1 trace_events 历史数据处理

- 上线前历史操作无 trace 记录，审计日志完整率统计从上线日起算
- 可选：编写一次性脚本从现有 audit_logs 表回填关键事件到 trace_events（event_type 映射表需预定义）
- 回填脚本必须标记 `reason_code='BACKFILL_MIGRATION'`，与正常事件区分

### 10.2 gate_decisions 兼容

- 上线前的提交/签字/导出操作无 gate_decisions 记录
- 上线后所有三入口操作必须经过 gate_engine，不允许绕过
- 灰度期间未接入 gate_engine 的项目，其操作不写 gate_decisions

### 10.3 SoD 存量数据

- 上线前已完成的底稿（status=archived）不追溯 SoD 校验
- 上线后所有 in_progress/submitted 状态的底稿，下次状态流转时触发 SoD 校验

---

## 11. 前端交互规范

### 11.1 门禁阻断面板状态机

| 页面状态 | 触发条件 | UI 表现 | 允许操作 |
|---|---|---|---|
| `normal` | gate_engine 返回 allow | 提交/签字/导出按钮可用 | 正常操作 |
| `blocked` | gate_engine 返回 block | 按钮禁用，顶部红色阻断面板展开 | 查看阻断项、跳转修复、重新评估 |
| `warned` | gate_engine 返回 warn | 按钮可用但显示橙色警告面板 | 确认警告后操作，或先修复 |
| `evaluating` | 正在调用 gate_engine | 按钮 loading 态 | 等待 |
| `error` | gate_engine 调用失败 | 显示系统错误 + trace_id | 重试 |

### 11.2 阻断面板交互规范

- 阻断项按"可自动修复 → 需人工处理"排序
- 同一规则多次触发时展示聚合计数（如"QC-16 数据不一致 ×3"）
- 每条阻断项必须可点击跳转到定位位置（说明区/差异面板/附件区/程序裁剪列表）
- 所有错误弹窗必须显示 trace_id（可复制）
- 阻断类错误不得自动消失，需用户显式处理或关闭
- 防重复提交：按钮点击后立即 disable，等待响应后恢复

### 11.3 SoD 冲突提示

- 提交/签字按钮点击时先调用 `/api/sod/check`
- 冲突时弹窗显示冲突类型 + policy_code + 建议操作（如"请联系合伙人指定替补复核人"）
- 弹窗不可自动关闭，必须用户确认

---

## 12. 安全增强

### 12.1 SoD 变更后 Token 失效

- 角色变更（如从 preparer 变为 reviewer）后，旧 Token 必须在 5 秒内失效
- 实现方式：角色变更时写入 Redis 黑名单（key=`sod_revoke:{user_id}:{project_id}`，TTL=token 剩余有效期）
- deps.py get_current_user 增加 SoD 黑名单检查

### 12.2 取证包脱敏规则（Phase 16 实施时引用）

| 角色 | 默认脱敏字段 | 完整导出条件 |
|---|---|---|
| 审计助理 | 客户统一社会信用代码、联系人手机号、身份证号 | 不允许完整导出 |
| 项目经理 | 同上 + 金额明细可按阈值脱敏 | 需项目合伙人审批 |
| 质控人员 | 客户识别信息默认脱敏 | 需质控负责人审批 |
| 项目合伙人 | 默认不脱敏（内部合规场景） | 对外完整导出需安全负责人审批 |

- 导出链接采用一次性令牌，默认 10 分钟失效
- 所有导出文件写入 SHA-256 哈希并入审计日志（trace_events）

