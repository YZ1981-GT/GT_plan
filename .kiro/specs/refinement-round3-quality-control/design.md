# Refinement Round 3 — 设计文档

## 概要

本轮聚焦质控视角，让质控能自定义规则、抽查项目、评级项目、出案例库/年报。遵守 [README v2.2](../refinement-round1-review-closure/README.md)。

依赖 R1 需求 2 的 `IssueTicket.source='Q' / qc_inspection` 枚举（R1 已预留）。依赖 R2 需求 7 工时审批数据作评级维度。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| 规则 DSL 范围控制 | R3 只做 Python 类型元数据化 + JSONPath | 避免 SQL 白名单 / 前端 SQL 编辑器的工程膨胀（按上轮合伙人建议第 12 条） |
| 既有 14 条规则迁移 | seed 脚本把 QC-01~14 + QC-19~26 写入 `qc_rule_definitions` 表，`expression=<class.module.path>`，保持硬编码行为不变 | 逐步替换 |
| 评级算法 | `QualityRatingService` 纯函数，依赖注入各数据源（QC 通过率 / 意见深度 / gate 失败 / SLA / 承诺响应） | 易测试 |
| 质控抽查 | 独立 `qc_inspection_records` 表，与项目组 `wp_review_records` 并行不干扰 | 不污染项目组流程 |
| 质控整改单 SLA | `sla_worker` 扩 `source='Q'` 分支，独立规则 | 现有 sla_worker 架构可扩 |
| 复核人深度指标 | 定时任务每天凌晨算，落 `reviewer_metrics_snapshots` | 指标只作年度考评参考，非实时 |
| 客户串联 | R3 仍用 client_name 精确匹配，R5 EQCR 用手动指定兜底 | R6+ 统一建客户主数据 |
| 案例库脱敏 | 客户名替换 + 金额 ±5% 扰动 | 留痕但脱敏 |
| 年报生成 | 走 `ExportJobService`，每年至多一个任务 | 复用现有异步导出 |

## 数据模型变更

### 新增表

```python
# backend/app/models/qc_rule_models.py (新建)

class QcRuleDefinition(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "qc_rule_definitions"
    id: UUID (PK)
    rule_code: str (unique, e.g. 'QC-01', 'QC-CUSTOM-001')
    severity: str  # 'blocking' | 'warning' | 'info'
    scope: str  # 'workpaper' | 'project' | 'consolidation'
    category: str | None
    title: str
    description: str
    standard_ref: list[dict] | None  # [{code: '1301', section: '6.2', name: '审计工作底稿'}]
    expression_type: str  # 'python' | 'jsonpath'（本轮仅支持两种，SQL 留后续）
    expression: str  # python: dotted path / jsonpath: $.parsed_data.xxx
    parameters_schema: dict | None  # JSON Schema for params
    enabled: bool (default true)
    version: int
    created_by: UUID

# backend/app/models/qc_inspection_models.py (新建)

class QcInspection(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "qc_inspections"
    id, project_id, strategy, params (JSONB), reviewer_id, status, 
    started_at, completed_at, report_url (str | None)

class QcInspectionItem(Base, TimestampMixin):
    __tablename__ = "qc_inspection_items"
    id, inspection_id (FK), wp_id, status, findings (JSONB), qc_verdict, completed_at

class QcInspectionRecord(Base, TimestampMixin):
    __tablename__ = "qc_inspection_records"  # 质控独立复核记录，不入 wp_review_records
    id, inspection_item_id, comment, severity, cell_ref, created_by, created_at

# backend/app/models/qc_rating_models.py (新建)

class ProjectQualityRating(Base, TimestampMixin):
    __tablename__ = "project_quality_ratings"
    id, project_id, year, rating ('A'|'B'|'C'|'D'),
    score (0-100), dimensions (JSONB), computed_at,
    computed_by_rule_version (int),
    override_by: UUID | None, override_rating: str | None, override_reason: str | None

class ReviewerMetricsSnapshot(Base, TimestampMixin):
    __tablename__ = "reviewer_metrics_snapshots"
    id, reviewer_id, year, snapshot_date,
    avg_review_time_min, avg_comments_per_wp, rejection_rate,
    qc_rule_catch_rate, sampled_rework_rate

# backend/app/models/qc_case_library_models.py (新建)

class QcCaseLibrary(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "qc_case_library"
    id, title, category, severity, description, lessons_learned (text),
    related_wp_refs (JSONB, 脱敏数据),
    related_standards (JSONB),
    published_by, published_at, review_count (int, 阅读计数)
```

### 修改既有

```python
# IssueTicket (R1 已预留 source='Q' 和 'qc_inspection')
# sla_worker 扩展：识别 source='Q' 分支的专属 SLA

# ReviewRecord 无改
```

## API 变更

### 新增端点

```
# 规则管理
GET/POST/PATCH/DELETE /api/qc/rules
POST /api/qc/rules/{rule_id}/dry-run       body: {scope, project_ids?, sample_size?}

# 抽查
POST /api/qc/inspections                    body: {project_id, strategy, params, reviewer_id}
GET  /api/qc/inspections/{id}
GET  /api/qc/inspections/{id}/items
POST /api/qc/inspections/{id}/items/{item_id}/verdict
POST /api/qc/inspections/{id}/report        触发 Word 生成（异步）

# 评级
GET  /api/qc/projects/{project_id}/rating/{year}
POST /api/qc/projects/{project_id}/rating/{year}/override   body: {rating, reason}
POST /api/qc/ratings/compute?year=          手动触发全所计算（admin）

# 复核人指标
GET  /api/qc/reviewer-metrics?year=&reviewer_id=

# 客户趋势
GET  /api/qc/clients/{client_name}/quality-trend?years=3

# 案例库
GET/POST /api/qc/cases
POST /api/qc/inspections/{inspection_id}/items/{item_id}/publish-as-case

# 年报
POST /api/qc/annual-reports?year=           异步生成
GET  /api/qc/annual-reports                 历史列表
```

### 修改既有

```
# sla_worker.py 新增 source='Q' 分支：48h 响应、7d 完成、逾期升级
```

## 前端变更

### 新增页面

```
src/views/qc/QcRuleList.vue            规则管理
src/views/qc/QcRuleEditor.vue          规则编辑 + 试运行
src/views/qc/QcInspectionWorkbench.vue 抽查工作台
src/views/qc/QcCaseLibrary.vue         案例库
src/views/qc/QcAnnualReports.vue       年报管理
src/views/qc/ClientQualityTrend.vue    客户趋势
```

### 修改

```
src/views/QCDashboard.vue            新增"评级"列 + "复核人画像" Tab
src/views/IssueTicketList.vue        source='Q' 行加🛡️图标与红左边框
src/router/index.ts                  新增 /qc/* 路由
src/composables/usePermission.ts     role='qc' 新动作
```

## 评级算法细节

```python
class QualityRatingService:
    async def compute(self, project_id: UUID, year: int) -> ProjectQualityRating:
        # 权重从 system_settings 读，可配置
        weights = await settings.get('qc_rating_weights', default={
            'qc_pass_rate': 0.30,
            'review_depth': 0.25,
            'gate_failures': 0.20,
            'remediation_sla': 0.15,
            'client_response': 0.10,
        })
        
        dims = {
            'qc_pass_rate': await self._qc_pass_score(project_id),
            'review_depth': await self._review_depth_score(project_id),
            'gate_failures': await self._gate_failure_score(project_id),
            'remediation_sla': await self._remediation_sla_score(project_id),
            'client_response': await self._client_response_score(project_id),
        }
        
        score = sum(weights[k] * dims[k] for k in weights)
        rating = 'A' if score >= 90 else 'B' if score >= 75 else 'C' if score >= 60 else 'D'
        
        return ProjectQualityRating(...)
```

## 跨轮约束遵守

| 约束 | 本轮落地 |
|------|----------|
| 1 通知字典 | 新增 `qc_rule_published / qc_inspection_assigned / qc_remediation_overdue / qc_rating_ready` |
| 2 权限四点 | role='qc' 新动作 `publish_rule / run_inspection / override_rating / publish_case / export_annual_report` |
| 3 状态机不重叠 | QcInspection 状态独立于 wp_review_records |
| 4 SOD | 质控人不能对自己参与的项目做评级 override |
| 5 SLA 自然日 | Q 整改单 48h/7d 按自然日 |
| 6 归档章节化 | 质控抽查报告归档时占用前缀 `03-质控抽查报告.pdf`（R3 注册章节） |
| 7 i18n | 无新 role |
| 8 焦点时长 | 不涉及 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 规则 DSL 执行不当崩溃 | Python 类型走沙箱 Timeout；JSONPath 只读 `parsed_data` 安全 |
| 评级误判大量低分项目 | 首年先跑 dry-run 出报告，合伙人确认权重后正式上线；前半年只显示不对外公布 |
| 定时任务压力 | 评级每月 1 日凌晨计算；复核人指标每日凌晨；错峰 |
| 案例库脱敏不彻底 | 双重脱敏：客户名 replace + 金额 ±5% 扰动 + 人工发布前预览；质控合伙人审批后才进库 |
| 客户名匹配失败 | 页面显示"未找到历史项目，请手动关联"；R6+ 建客户主数据解决 |
| 抽查工作台性能 | 每批次抽样上限 50 张底稿 |

## 测试策略

- 单元测试：`QualityRatingService` 5 维度各 3 用例
- 集成测试：`test_qc_rule_dry_run.py` + `test_qc_inspection_e2e.py`
- 回归：现有 QC-01~26 规则行为不变（迁移后跑同一批底稿比对结果）

## 补充设计（v1.1，需求 11~12）

### 需求 11 AI 内容标记

```python
# parsed_data.ai_content 结构规范化（既有字段，重定义 schema）
{
  "id": "uuid",
  "type": "ai_generated",
  "source_model": "qwen-27b-nvfp4",
  "source_prompt_version": "v1.2",
  "generated_at": "datetime",
  "confidence": 0.85,
  "content": "…LLM 输出文本…",
  "target_cell": "E5" | null,
  "target_field": "conclusion" | null,
  "confirmed_by": "user_id" | null,
  "confirmed_at": "datetime" | null,
  "confirm_action": "accept" | "revise" | "reject" | null,
  "revised_content": "str" | null
}
```

迁移老数据：`wp_ai_service` 历史写入可能缺新字段，迁移脚本补 `confirmed_by=null`，等审计师逐张确认。

门禁：`AIContentMustBeConfirmedRule` 扫描 `ai_content where confirmed_by is null and target_cell is not null`，非空则阻断 sign_off。简报/年报类独立产物不入 `parsed_data`，规则不检。

### 需求 12 日志审查规则

扩展 `qc_rule_definitions.scope` 枚举加 `audit_log`。执行器：

```python
class AuditLogJsonPathExecutor:
    async def run(self, rule: QcRuleDefinition, context):
        # scope='audit_log' 时 context 含 (project_id, time_window)
        stmt = select(AuditLogEntry).where(
            AuditLogEntry.project_id == context.project_id,
            AuditLogEntry.ts.between(context.time_window_start, context.time_window_end),
        )
        entries = (await db.execute(stmt)).scalars().all()
        hits = []
        for e in entries:
            if jsonpath_ng.parse(rule.expression).find(e.payload):
                hits.append(e)
        return hits
```

预置 5 条（seed `backend/scripts/seed_qc_rules.py` 扩展）：

```
AL-01: $[?(@.action_type == 'workpaper_modified' && @.ts_hour in [22,23,0,1,2,3,4,5])]
       参数: threshold_per_hour=10  → warning
AL-02: 同 IP 24h 内多 account_type 登录 (Python 类型规则，非 jsonpath)
AL-03: action_type in ['retention_override', 'rotation_override']  → info
AL-04: action_type == 'gate_override' 近 30 天同 user > 5  → warning
AL-05: verify-chain 失败  → blocking (注册 gate_rules_phase14 而不是 QC)
```

AL-02 和 AL-04 不是纯 jsonpath，需 Python 类型执行器辅助。本轮 AL-01/AL-03 先用 jsonpath，AL-02/AL-04/AL-05 留 Round 6+ 升级时再做（需求中明示）。
