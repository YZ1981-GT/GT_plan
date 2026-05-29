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

## 实施变更日志（v1.2，代码落地后追溯）

本节记录设计到实施过程中的 **偏差、发现的问题、最终落地方案**，作为 "实装对设计稿的修正"。如未来再做同类设计，这些偏差应回灌到初版 design.md。

### 架构决策微调（与初版差异）

| 初版设计 | 实际落地 | 原因 |
|---------|---------|------|
| 年度独立性声明扩展 R1 `independence_declarations.declaration_scope` | 新建独立表 `annual_independence_declarations` + migration `round5_independence_20260506` | R1 原表尚未建成；等 R1 落地后一次性迁入合并 |
| 归档章节 `register('02', 'eqcr_memo.pdf', ...)` | 章节注册机制在 R1 未就绪；`eqcr_memo_pdf_generator` 作为预留函数接口暴露 | R5 先解耦产出 Word+PDF 文件路径到 `wizard_state.eqcr_memo.files`，等 R1 registry 落地后再接入 |
| "组成部分审计师能力 C/D 评级行高亮" | 代码枚举实际值为 `reliable / additional_procedures_needed / unreliable`，设计稿 A/B/C/D 是业务语义描述 | 前端改按真实枚举高亮（unreliable / additional_procedures_needed 触发红/黄标） |
| "客户名精确匹配" 跨年对比 | 引入 `app/services/client_lookup.normalize_client_name`：去空白、全角→半角、去"有限公司/股份/集团/Co.,Ltd/Inc." 后缀 | 真实审计项目客户名有"XX集团"vs"XX集团有限公司"变体；R6+ 升级模糊匹配 |

### 修复实装发现的 Bug（都不是设计问题，是实施时的错误）

P0 — 阻断性：
1. `gate_engine.evaluate()` 对 `gate_decision.id` 引用在 `db.add` 之后但 `db.flush` 之前，导致 `trace_events.object_id` NOT NULL 违反。**修复**：`db.add(gate_decision)` 后立即 `await db.flush()` 再建 trace_event。
2. `sign_service._transition_report_status()` 改 `report.status` 后未 flush，`await db.refresh(report)` 从 DB 重读时丢失修改。**修复**：状态变更后立即 `await db.flush()`。
3. Task 14 AuditReportEditor.vue 锁定判断只查 `status === 'final'`，漏掉新的 `eqcr_approved` 态。**修复**：提取 `isLocked` computed 统一判断两态。
4. Task 24 年度声明只在对话框弹，用户关闭后仍可正常使用工作台；不满足 "未提交阻断访问" 要求。**修复**：router beforeEach 加 `meta.requiresAnnualDeclaration` 守卫 + 工作台 `load()` 前置检查。

P1 — 功能完整性：
1. Task 18 初版只输出 JSON 结构化存储，未生成 Word/PDF。**修复**：引入 `build_memo_docx_bytes` 纯函数（复用 phase13 同款 python-docx），LibreOffice headless 转 PDF，落盘 `backend/wp_storage/{project_id}/eqcr_memo/`。
2. Task 15 prior-year-comparison 精确匹配 `client_name ==` 实际会漏命中变体。**修复**：`client_lookup.normalize_client_name` 先归一再比。
3. Task 20 metrics 端点无后端角色校验，仅靠前端路由 meta 粗筛（易绕过）。**修复**：后端端点加 `user_role not in ('admin', 'partner') → 403`。
4. EqcrPriorYearCompare 的 `allDiffReasonsProvided` / `getDiffReasons` defineExpose 初版无消费者。**修复**：EqcrProjectView header 加 "EQCR 审批" 按钮，approve 前强制检查差异原因，未填则跳到 prior_year Tab 并提示。

P2 — 清理：
1. `_DEFAULT_QUESTIONS` Python 常量与 JSON 种子文件内容重复。**修复**：删 Python 副本，JSON 为唯一真源。
2. `test_eqcr_state_machine_properties.py` 初版自建 `VALID_TRANSITIONS` 字典（测试数据在测测试数据）。**修复**：从 `app.models.report_models.ReportStatus` 真实枚举推导矩阵；避免使用未安装的 hypothesis，改 `@pytest.mark.parametrize` 覆盖 4×4 状态组合。
3. `frontend apiProxy` 路径实际是 `@/services/apiProxy`（不是 `@/utils/apiProxy`），memory 旧记录误导。**修复**：统一改 `@/services/apiProxy`。

### 跨轮副产物

在本轮复盘时顺带发现 3 个影响全系统的问题（不限 R5）：
1. `backend/data/audit_report_templates_seed.json` 71 处 CJK 字符串内用直双引号 `"XX"` 使 JSON 解析失败。审计报告模板完全加载不进来。**修复**：改用中文方头括号 `「XX」`（U+300C/U+300D）恢复合法性。
2. `qc_engine.py` SamplingCompletenessRule (QC-12) 引用不存在的 `SamplingConfig.working_paper_id` 列。**修复**：按 `project_id` 过滤。
3. `qc_engine.py` PreparationDateRule (QC-14) `datetime.utcnow() - aware_datetime` 类型混用。**修复**：`datetime.now(timezone.utc)` 统一 tz-aware。
4. `backend/tests/conftest.py` 漏导入 15+ 个模型包（phase10/12/14/15/16/archive/dataset/knowledge/note_trim/procedure/shared_config/template_library/eqcr/related_party/independence），导致 SQLite `create_all` 缺表，多处 service 测试时抛 "no such table"。**修复**：补齐所有模型导入。
5. `hypothesis` 未装导致 4 个属性测试文件从未运行（memory 旧说法 "16 个 Hypothesis 测试"是虚假状态）。**修复**：安装 `hypothesis@6.152.4`，101 个属性测试全部通过。

### 关键测试数据

| 测试文件 | 数量 | 状态 |
|---------|------|------|
| test_eqcr_gate_approve.py | 3+ | ✅ |
| test_eqcr_state_machine_lock.py | 8+ | ✅ |
| test_eqcr_workbench.py | 多 | ✅ |
| test_eqcr_notes.py | 多 | ✅ |
| test_eqcr_independence_sod.py | 4 | ✅ |
| test_eqcr_service.py | 多 | ✅ |
| test_eqcr_shadow_compute.py | 多 | ✅ |
| test_eqcr_domain_data.py | 多 | ✅ |
| test_eqcr_full_flow.py | 5 | ✅ 新增 |
| test_eqcr_component_auditor_review.py | 5 | ✅ 新增 |
| test_eqcr_state_machine_properties.py | 8 parametrized | ✅ 新增 |
| test_eqcr_memo_docx.py | 5 | ✅ 新增 |
| test_client_lookup.py | 14 parametrized | ✅ 新增 |
| **EQCR 相关合计** | **122** | **✅ 全通过** |
| 跨轮复盘附加解锁 | 101 | ✅ 属性测试从零运行到全通过 |
| 跨轮复盘附加解锁 | 93 | ✅ phase13/14 既有测试解除误报 |

## 变更日志

- v1.2（2026-05-06，实装追溯）：追加"实施变更日志"章节，记录 P0-P2 修复、跨轮副产物、实装与初版设计的差异
- v1.1（2026-05-05）：补充需求 11~12（组成部分审计师复核 + 年度独立性）
- v1.0（2026-05-05）：初版设计，10 个需求，3 个 Sprint / 20 个任务
