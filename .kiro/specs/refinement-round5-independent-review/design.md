# Refinement Round 5 — 设计文档

## 概要

本轮聚焦独立复核（EQCR）视角，补齐独立复核所需的全部工具：专属工作台、判断类事项聚合、意见不一致处理、报告前状态机锁定、独立留痕。遵守 [README v2.2](../refinement-round1-review-closure/README.md)。

**前置依赖**：R1 需求 4 签字流水（`required_order/prerequisite_signature_ids`）。R1 已预留 `ProjectAssignment.role='eqcr'` 枚举值和归档章节前缀 `02`。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| EQCR 角色挂载 | 复用 `ProjectAssignment.role='eqcr'`（R1 已预留）| 不新建角色表 |
| 持续经营 Tab | 复用 `GoingConcernEvaluation` 模型，只做 EQCR 视角渲染 | 模型已存在（代码锚定） |
| 关联方最小建模 | 本轮新增 `related_party_registry` + `related_party_transactions` 两表（仅 CRUD） | R6+ 做自动识别 |
| 独立沟通收窄 | 改为"EQCR 独立复核笔记"，不直接对外联络（采纳合伙人第 10 条建议） | 维持项目组作为对外单一入口 |
| 影子计算 | 复用 `consistency_replay_engine`，加 `caller_context='eqcr'` | 避免重复造 |
| EQCR 门禁新阶段 | `gate_engine` 新增 `GateType.eqcr_approval`，位于 sign_off 与 export_package 之间 | 状态机插入新环 |
| 审计意见锁定 | **扩展 `ReportStatus` 状态机**：`draft → review → eqcr_approved → final`，不加平行字段 | 跨轮约束 3 |
| SOD 规则 | EQCR 不得同时是同项目的 signing_partner/manager/auditor（跨轮约束 4） | `sod_guard_service` 注册 |
| EQCR 工时 purpose | `WorkHourRecord.purpose` 新增字段（`'preparation|review|eqcr|training|admin'`） | 独立统计 |
| 历年对比 | 用 client_name 串联 + 手动指定上年兜底 | R6+ 建客户主数据 |
| 备忘录 | 自动组装 Word，模板 `eqcr_memo.docx`，走 `pdf_export_engine` | 复用归档 PDF 引擎 |

## 数据模型变更

### 新增表

```python
# backend/app/models/eqcr_models.py (新建)

class EqcrOpinion(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "eqcr_opinions"
    id, project_id, 
    domain: str  # 'materiality' | 'estimate' | 'related_party' | 'going_concern' | 'opinion_type'
    verdict: str  # 'agree' | 'disagree' | 'need_more_evidence'
    comment: str
    created_by, created_at

class EqcrReviewNote(Base, SoftDeleteMixin, TimestampMixin):
    """EQCR 独立复核笔记（不对外）"""
    __tablename__ = "eqcr_review_notes"
    id, project_id, title, content (text),
    shared_to_team: bool (default false),
    shared_at: datetime | None

class EqcrShadowComputation(Base, TimestampMixin):
    __tablename__ = "eqcr_shadow_computations"
    id, project_id, computation_type,
    params: JSONB, result: JSONB,
    team_result_snapshot: JSONB | None,  # 项目组结果对比
    has_diff: bool,
    created_by, created_at

class EqcrDisagreementResolution(Base, TimestampMixin):
    __tablename__ = "eqcr_disagreement_resolutions"
    id, project_id, eqcr_opinion_id (FK), 
    participants: list[UUID] (JSONB),  # 合议参与人
    resolution: text, resolution_verdict: str,
    resolved_at: datetime

# 最小关联方建模
class RelatedPartyRegistry(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "related_party_registry"
    id, project_id, name, relation_type: str,
    is_controlled_by_same_party: bool

class RelatedPartyTransaction(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "related_party_transactions"
    id, project_id, related_party_id (FK),
    amount: Decimal, transaction_type: str,
    is_arms_length: bool,
    evidence_refs: JSONB | None
```

### 扩展既有

```python
# ReportStatus 枚举（backend/app/models/report_models.py）
class ReportStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    eqcr_approved = "eqcr_approved"    # 新增
    final = "final"

# GateType 枚举（backend/app/services/gate_engine.py）
class GateType:
    submit_review = "submit_review"
    sign_off = "sign_off"
    eqcr_approval = "eqcr_approval"     # 新增
    export_package = "export_package"

# SignatureRecord 无改（R1 的 required_order 支持 1~5 即可，EQCR=4、归档=5）

# WorkHourRecord 新增字段
purpose: Mapped[str | None]  # 'preparation|review|eqcr|training|admin'

# ProjectAssignment.role 已在 R1 预留 eqcr（本轮落地使用）

# AuditReport 扩展 signature workflow 顺序:
#   order=1 项目组长 → 2 项目经理 → 3 签字合伙人 → 4 EQCR → 5 归档
```

## API 变更

### 新增端点

```
# EQCR 工作台
GET  /api/eqcr/projects                        返回本人作为 EQCR 的项目
GET  /api/eqcr/projects/{project_id}/overview  项目 EQCR 总览

# 5 个判断域 Tab 数据
GET  /api/eqcr/projects/{project_id}/materiality
GET  /api/eqcr/projects/{project_id}/estimates
GET  /api/eqcr/projects/{project_id}/related-parties
GET  /api/eqcr/projects/{project_id}/going-concern   # 复用 GoingConcernEvaluation
GET  /api/eqcr/projects/{project_id}/opinion-type

# 录入意见
POST /api/eqcr/opinions                         body: {project_id, domain, verdict, comment}
PATCH /api/eqcr/opinions/{id}

# 独立复核笔记
GET/POST /api/eqcr/projects/{project_id}/notes
POST /api/eqcr/notes/{id}/share-to-team         共享到项目组沟通记录

# 影子计算
POST /api/eqcr/shadow-compute
GET  /api/eqcr/projects/{project_id}/shadow-computations

# 关联方 CRUD
GET/POST /api/projects/{project_id}/related-parties
GET/POST /api/projects/{project_id}/related-party-transactions

# EQCR 审批（门禁入口）
POST /api/eqcr/projects/{project_id}/approve
  body: {verdict, comment, shadow_comp_refs?, attached_opinion_ids?}
  内部: gate_engine.evaluate(eqcr_approval) → 通过则切 AuditReport.status→eqcr_approved
POST /api/eqcr/projects/{project_id}/unlock-opinion   附原因

# 历年对比
GET  /api/eqcr/projects/{project_id}/prior-year-comparison

# 备忘录
POST /api/eqcr/projects/{project_id}/memo        生成 Word
GET  /api/eqcr/projects/{project_id}/memo/preview
PUT  /api/eqcr/projects/{project_id}/memo         用户编辑后保存
POST /api/eqcr/projects/{project_id}/memo/finalize  定稿 + 生成 PDF

# 指标仪表盘
GET  /api/eqcr/metrics?year=
```

### 修改既有

```
POST /api/signatures/sign
  扩展 required_order 可到 4（EQCR 签）
  完成 order=4 签字时同步切 AuditReport.status → eqcr_approved（跨轮约束 3）

PUT /api/audit-report/{id}/status
PUT /api/audit-report/{id}/paragraphs/{section}
  在 eqcr_approved 状态下禁止修改 opinion_type 和段落（扩展现有 final 锁定规则）
  返回 403 OPINION_LOCKED_BY_EQCR
```

## 前端变更

### 新增页面

```
src/views/eqcr/EqcrWorkbench.vue              工作台
src/views/eqcr/EqcrProjectView.vue            项目详情 + 5 Tab
src/views/eqcr/EqcrMetrics.vue                管理员仪表盘
src/components/eqcr/EqcrOpinionForm.vue       意见录入
src/components/eqcr/EqcrMateriality.vue       重要性 Tab
src/components/eqcr/EqcrEstimates.vue         估计 Tab
src/components/eqcr/EqcrRelatedParties.vue    关联方 Tab
src/components/eqcr/EqcrGoingConcern.vue      持续经营 Tab
src/components/eqcr/EqcrOpinionType.vue       意见类型 Tab
src/components/eqcr/EqcrReviewNotesPanel.vue  独立笔记
src/components/eqcr/EqcrShadowCompute.vue     影子计算
src/components/eqcr/EqcrPriorYearCompare.vue  历年对比
src/components/eqcr/EqcrMemoEditor.vue        备忘录编辑
```

### 修改

```
src/views/AuditReportEditor.vue   状态标签：draft→可编辑/review→审阅中/eqcr_approved→🔒EQCR已锁/final→🔒已定稿
src/layouts/DefaultLayout.vue     EQCR 角色导航入口
src/composables/usePermission.ts  role='eqcr' 新动作
src/router/index.ts               新增 /eqcr/* 路由
```

### 后端归档集成

```python
# R1 已建的 archive_section_registry，R5 本轮注册章节：
archive_section_registry.register('02', 'eqcr_memo.pdf', eqcr_memo_pdf_generator)
# 归档包将自动包含 EQCR 备忘录
```

## 跨轮约束遵守

| 约束 | 本轮落地 |
|------|----------|
| 1 通知字典 | 新增 `eqcr_approved / eqcr_disagreement / opinion_locked` |
| 2 权限四点 | `role='eqcr'` 新动作 `view_eqcr / record_opinion / shadow_compute / approve_eqcr` 同步 4 处字典 |
| 3 状态机不重叠 | **关键**：审计意见锁定改走 `ReportStatus.eqcr_approved`，不加平行字段 |
| 4 SOD | **关键**：注册 EQCR SOD 规则到 `sod_guard_service` |
| 5 SLA 自然日 | 无本轮 SLA |
| 6 归档章节化 | **关键**：注册 `02-EQCR备忘录.pdf` 到 R1 的 `archive_section_registry` |
| 7 i18n | `ROLE_MAP` 新增 `eqcr=独立复核合伙人` |
| 8 焦点时长 | 不涉及 |

## SOD 规则细节

```python
# backend/app/services/sod_guard_service.py 新增规则
class EqcrIndependenceRule:
    """EQCR 不得同时是同项目的 signing_partner/manager/auditor"""
    def check(self, project_id: UUID, staff_id: UUID, new_role: str):
        if new_role != 'eqcr':
            # 若已有 eqcr 角色，新增冲突角色也拒绝
            existing = query.filter(role='eqcr', staff_id=staff_id, project_id=project_id).exists()
            if existing and new_role in ('signing_partner', 'manager', 'auditor'):
                raise SodViolation("EQCR 不能同时担任该角色")
        else:
            existing_conflict = query.filter(
                role__in=['signing_partner', 'manager', 'auditor'],
                staff_id=staff_id, project_id=project_id
            ).exists()
            if existing_conflict:
                raise SodViolation("已是项目组成员，不能担任 EQCR")
```

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| EQCR 卡签字进度 | EQCR 工作台突出显示"签字前置等我"的项目，避免延误 |
| 意见不一致合议死锁 | 合议 7 天无结论自动升级到事务所首席风控合伙人 |
| 影子计算与项目组计算冲突 | 限流每项目每天 20 次；结果独立存档不写入项目组数据 |
| ReportStatus 新增态破坏既有流程 | 所有读状态的地方加 `if status in (review, eqcr_approved):` 兜底，灰度上线 |
| 客户名匹配历年对比失败 | UI 显示"未找到上年项目，请手动关联"，提供项目选择器兜底 |
| SOD 规则破坏既有委派数据 | 上线前跑一次数据扫描，标记已有冲突数据人工确认 |

## 测试策略

- 单元测试：`EqcrIndependenceRule` SOD 4 场景用例（EQCR→冲突 / 冲突→EQCR / 同人不同项目 / 正常）
- 集成测试：`test_eqcr_full_flow.py`（委派 → 各 Tab 录入 → 影子计算 → 审批 → 状态切 eqcr_approved → 签字 → final）
- 属性测试：状态机转移安全（hypothesis 生成随机 status transitions，验证 eqcr_approved 不能反向回 draft 除非显式 unlock）
- 回归：`AuditReport` 既有 draft/review/final 流程不受影响

## 补充设计（v1.1，需求 11~12）

### 需求 11 组成部分审计师

已有模型：`ComponentAuditor / Instruction / InstructionResult`（`consolidation_models.py`），router 完整 CRUD。本轮不改模型，只新增 EQCR 聚合 API + 前端 Tab。

```python
# backend/app/services/eqcr_service.py 扩展
async def get_component_auditor_review_data(project_id: UUID):
    auditors = await get_auditors(project_id)
    result = []
    for a in auditors:
        instructions = await get_instructions(project_id, a.id)
        results_ = await get_results(project_id, a.id)
        eqcr_opinion = await select(EqcrOpinion).where(
            project_id=project_id, 
            domain='component_auditor',
            # opinion payload 关联 auditor_id
        )
        result.append({...})
    return result
```

`eqcr_opinions.domain` 枚举扩展 `component_auditor`，opinion payload 里带 `{auditor_id, auditor_name}` 区分。

### 需求 12 年度独立性声明

扩展 R1 `independence_declarations` 表，新增 `declaration_scope` 字段（R1 原始 schema 只支持项目级，本轮扩 enum）。旧数据 `declaration_scope='project'` 默认值。

年度声明特殊规则：
- `project_id` 可为 null（年度声明非项目级）
- `declaration_year` 必填，唯一约束 `(declarant_id, declaration_year, declaration_scope='annual')`
- 登录守卫：用户首次登录检查当年度 annual 声明 → 无 → 强制跳转 `/independence/annual` 
- `backend/data/independence_questions_annual.json` 预置 30+ 题（含持股、家庭成员、过去服务等）

抽查：复用 R3 需求 4 的 `QcInspection` 框架，strategy='annual_independence'，params={sample_rate: 10%}，items 指向 `IndependenceDeclaration`。

备忘录章节追加：`eqcr_memo_generator` 模板新增 `component_auditors_section` 子模板，动态渲染组成部分评估结果。
