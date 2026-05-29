# Refinement Round 1 — 设计文档

## 概要

本轮修复"复核 → 整改 → 签字 → 归档"闭环与合规文档缺口。所有设计遵守 [README v2.2](./README.md) 的"跨轮依赖矩阵 / 数据库迁移约定 / 跨轮约束"。

设计以**复用为主、新增为辅**：`ReviewInboxService / gate_engine / SignService / ExportIntegrityService / wp_storage / private_storage / data_lifecycle / pdf_export_engine / archive_section_registry` 等既有能力直接嵌入，不另造。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| 复核批注单一真源 | 用 `ReviewRecord`，`review_conversations` 仅保留讨论 | 单行绑定 `cell_reference` 天然适合转工单，避免两套系统同步 |
| 就绪检查合一 | `SignReadiness/ArchiveReadiness` 改门面包 `gate_engine.evaluate` | 已有 gate 规则是唯一真理，readiness 不再独立判断 |
| 三级签字流水 | 在 `SignatureRecord` 扩 `required_order/required_role/prerequisite_signature_ids` | 不新建表，不破坏现有验签 |
| 签字→状态机联动 | `SignService.sign` 检测最高级签字后同事务切 `AuditReport.status=final` | 避免"签完字报告停在 review" |
| 归档三入口合并 | 新编排服务 `ArchiveOrchestrator`，旧端点 deprecated | 前端只改向导，不改三个内部服务 |
| 归档包章节化 | `archive_section_registry` + 前缀排序 | 为 R3/R5 预留插入位（跨轮约束 6） |
| 断点续传 | `archive_jobs.last_succeeded_section` 基于章节前缀 | 章节级粒度够用，无需文件级 |
| ExportIntegrity 语义 | 导出时记 → 下载不重算 → 可疑时 verify | 对齐现有 `export_integrity_service.py:53` |
| AJE→错报联动 | 新增 gate 规则 + `Adjustments.vue` 一键转换按钮 | 后端 `create_from_rejected_aje` 已实现，补前端即可 |
| 级联完整性 | 新增 `EventCascadeHealthRule` 检查 `WORKPAPER_SAVED/REPORTS_UPDATED` pending | 防止 sign_off 时下游未更新 |

## 数据模型变更

### 新增枚举值（一次迁移全轮预留）

依据 README v2.2 数据库迁移约定第 4 条：

```python
# backend/app/models/workpaper_models.py 或 issue_ticket_service 所在模型
IssueTicket.source ENUM 扩展:
  既有: 'L2' | 'L3' | 'Q'
  新增: 'review_comment' | 'consistency' | 'ai' | 'reminder' 
       | 'client_commitment' | 'pbc' | 'confirmation' | 'qc_inspection'

# backend/app/models/staff_models.py AssignmentRole
  既有: signing_partner | manager | auditor | qc
  新增: eqcr  (R5 用，R1 预留)
```

### 新增字段

```python
# SignatureRecord (backend/app/models/extension_models.py)
required_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
required_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
prerequisite_signature_ids: Mapped[list[UUID] | None] = mapped_column(JSONB, nullable=True)

# IssueTicket
source_ref_id: Mapped[UUID | None]  # 源对象 ID，用于双向追溯（如对应 ReviewRecord.id）

# ReviewRecord
status: Mapped[str] = mapped_column(String(20), server_default="'open'")  # open | resolved
reply_text: Mapped[str | None]  # 编制人回复（整改说明）
```

### 新增表

```python
# backend/app/models/archive_models.py (新建)

class ArchiveJob(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "archive_jobs"
    id: UUID (PK)
    project_id: UUID (FK -> projects)
    scope: str  # 'final' | 'interim'
    status: str  # 'queued' | 'running' | 'succeeded' | 'failed' | 'partial'
    last_succeeded_section: str | None  # 章节前缀如 '01'
    failed_section: str | None
    failed_reason: str | None
    output_url: str | None
    manifest_hash: str | None  # 关联 evidence_hash_checks
    started_at: datetime | None
    finished_at: datetime | None
```

### 新增/扩展规则类

```python
# backend/app/services/gate_rules_phase14.py 追加
class UnconvertedRejectedAJERule(GateRule):
    """扫描 Adjustment.review_status=rejected 且未关联 UnadjustedMisstatement 的 AJE 组"""

class EventCascadeHealthRule(GateRule):
    """检查最近 1 小时的 WORKPAPER_SAVED/REPORTS_UPDATED 事件是否都完成消费"""

# 注册：
rule_registry.register_all([GateType.sign_off], UnconvertedRejectedAJERule())
rule_registry.register_all([GateType.sign_off, GateType.export_package], EventCascadeHealthRule())
```

## API 变更

### 新增端点

```
POST  /api/projects/{project_id}/archive/orchestrate
  body: {scope, confirm_gate_pass, push_to_cloud, purge_local}
  resp: {archive_job_id, status, estimated_seconds}

GET   /api/projects/{project_id}/archive/jobs/{job_id}
  resp: ArchiveJob dict + current section

POST  /api/projects/{project_id}/archive/jobs/{job_id}/retry
  从 last_succeeded_section 下一章节续跑

GET   /api/signatures/workflow/{project_id}
  resp: [{order, role, required_user_id, status, signed_at, signed_by}]

POST  /api/adjustments/{group_id}/convert-to-misstatement
  封装现有 misstatement_service.create_from_rejected_aje
```

### 重构端点

```
GET   /api/projects/{id}/sign-readiness
  → 内部改调 gate_engine.evaluate("sign_off")
  resp schema 统一: {ready, groups, findings[], gate_eval_id}

GET   /api/qc/archive-readiness  
  → 内部改调 gate_engine.evaluate("export_package")

POST  /api/signatures/sign
  请求体新增 gate_eval_id (5 分钟过期)
  内部：校验前置 signatures + 最高级签完后切 AuditReport.status
```

### Deprecated（保留向后兼容）

```
POST  /api/projects/{project_id}/archive         (wp_storage 版)
POST  /api/projects/{id}/archive                 (private_storage 版)  
POST  /api/projects/{project_id}/archive         (data_lifecycle 版)
  → 响应头加 X-Deprecated: true
  → warning log 告知使用 /archive/orchestrate
```

## 前端变更

### 新增页面

```
src/views/ReviewWorkbench.vue           (合并 ReviewInbox + 废弃 ReviewWorkstation)
src/views/ArchiveWizard.vue             (3 步向导)
src/components/gate/GateReadinessPanel.vue  (公共组件)
src/components/signature/SignatureWorkflowLine.vue  (签字流水可视化)
```

### 修改页面

```
src/views/Adjustments.vue         (新增"转错报"按钮，source='rejected' 行显示)
src/views/PartnerDashboard.vue    (签字弹窗内嵌 GateReadinessPanel + SignatureWorkflowLine，就地签字)
src/views/WorkpaperEditor.vue     (根据 ReviewRecord.cell_reference 渲染红点)
src/views/IssueTicketList.vue     (source 筛选新增 review_comment)
src/router/index.ts                (替换 ReviewInbox 组件；新增 ArchiveWizard 路由)
```

### 删除

```
src/views/ReviewWorkstation.vue   (死代码清理)
```

## 跨轮约束遵守

| 约束 | 本轮落地方式 |
|------|--------------|
| 1 Notification type 统一字典 | 新增 `notification_types.py` 常量 + 前端 map，本轮落地"gate_alert / archive_done / signature_ready" |
| 2 权限四点同步 | `ArchiveOrchestrator` 权限 `role='partner' or assignment.role='signing_partner'`，同步 4 处字典 |
| 3 状态机不重叠 | `AuditReport.status` 由签字驱动，不新增 opinion_locked_at |
| 4 SOD | 复用现有 `sod_guard_service`，本轮不新增 SOD 规则 |
| 5 自然日 SLA | gate_eval_id 5 分钟硬超时按自然日分钟计 |
| 6 归档章节化 | 新建 `archive_section_registry` 机制，本轮占用 `00/01/99` |
| 7 i18n | `required_role` 新增中文映射到 `ROLE_MAP` 字典 |
| 8 焦点时长隐私 | 本轮不涉及 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 旧归档端点前端残留调用 | 本轮改所有前端调用点到 orchestrate，deprecated 端点加 warning log 便于发现漏改 |
| gate_eval_id 过期导致用户体验差 | 弹窗里显示"剩余 N 秒"，过期前 30 秒后台自动刷新；过期后 toast 提示并自动重跑检查 |
| 最高级签字同事务切 status 失败 | 整体事务回滚，签字动作失败；告警 `signature_status_sync_failed` |
| 级联事件健康检查误报 | 阈值"1 小时"可配置；首次部署时预热阶段 gate 仅 warning 不阻断 |
| ReviewRecord 与 IssueTicket 双向同步死锁 | IssueTicket 创建失败不阻断 ReviewRecord，用后台 event 补偿 |
| 三个 deprecated 端点的潜在破坏 | 加单元测试验证旧端点仍能返回（向后兼容保 1 轮） |

## 测试策略

- **单元测试**：新增 gate 规则 (`UnconvertedRejectedAJERule / EventCascadeHealthRule`) 各 3 个用例（命中/不命中/边界）
- **集成测试**：`test_archive_orchestrate_e2e.py` 走 happy path + 断点续传 + 失败重试
- **属性测试**：签字流水 `required_order` 前置依赖校验，hypothesis 生成随机签字顺序验证永远遵守 order 约束
- **回归测试**：旧归档 3 端点 + `SignReadinessService` 旧 schema 兼容

## 补充设计（v1.1，需求 9~11）

### 需求 9 审计日志落库 + 哈希链

```python
# backend/app/models/audit_log_models.py (新建)
class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"
    id: UUID
    ts: datetime (with tz, indexed)
    user_id: UUID (indexed)
    session_id: str | None
    action_type: str (indexed)   # signature_signed / gate_evaluated / archive_retention_override / ...
    object_type: str
    object_id: UUID | None
    payload: JSONB (脱敏)
    ip: str | None
    ua: str | None
    trace_id: str | None
    prev_hash: str (64 chars, sha256)
    entry_hash: str (64 chars, sha256, unique indexed)
    # 无 updated_at / 无 is_deleted (不可改不可删)
```

**异步缓冲**：`log_action` 写入"待写入队列"（Redis List），`audit_log_writer_worker`（新 worker）批量 flush 到 DB。写失败进重试队列，3 次失败触发告警 `AUDIT_LOG_WRITE_FAILED`。

**哈希链计算**：`entry_hash = sha256(f"{ts.isoformat()}|{user_id}|{action_type}|{object_id}|{json.dumps(payload, sort_keys=True)}|{prev_hash}")`，`prev_hash` 取该 `project_id` 上一条日志的 `entry_hash`（跨项目不链）。

**verify-chain 端点**：逐条重算 `entry_hash` 比对，第一条断链停下返回。O(N) 耗时对项目级（通常 N < 5 万）可接受。

### 需求 10 独立性声明

```python
# backend/app/models/independence_models.py (新建)
class IndependenceDeclaration(Base, TimestampMixin):
    __tablename__ = "independence_declarations"
    id, project_id, declarant_id, declaration_year,
    answers: JSONB,
    attachments: JSONB,
    signed_at: datetime | None,
    signature_record_id: UUID | None (FK -> signatures.id),
    reviewed_by_qc_id: UUID | None,
    reviewed_at: datetime | None,
    status: str  # 'draft' | 'submitted' | 'pending_conflict_review' | 'approved'

# gate_rules_phase14.py 新增规则
class IndependenceDeclarationCompleteRule(GateRule):
    """sign_off gate 要求项目核心四角色均已 submitted 或 approved"""
```

**问题模板**：`backend/data/independence_questions.json`（20 条，按准则整理）。首版由合伙人审核后入库，提供 admin UI 维护（Round 6+ 做）。

### 需求 11 保留期 + 轮换

```python
# Project 表扩展
archived_at: datetime | None  # 签字归档时间
retention_until: datetime | None  # archived_at + 10 years

# 新增 partner_rotation_overrides 表
class PartnerRotationOverride(Base, TimestampMixin):
    id, staff_id, client_name, original_years, override_reason,
    approved_by_compliance_partner, approved_by_chief_risk_partner,
    override_expires_at

# API
GET /api/rotation/check?staff_id=&client_name=
  resp: {continuous_years, next_rotation_due_year, current_override_id?}
```

**查询策略**：按 `client_name` 精确匹配聚合（复用 R3/R5 的客户串联策略）`project_assignments`，查同一 `staff_id` 担任 `signing_partner / eqcr` 的连续年数。R6+ 引入客户主数据后可替换为 `client_id`。

**purge 拦截**：`data_lifecycle.purge_project_data` 入口函数首行加 retention 校验，R1 tasks 21 覆盖。
