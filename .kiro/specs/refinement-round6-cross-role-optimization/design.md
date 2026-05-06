# Refinement Round 6 — 设计文档

## 概要

本轮聚焦"跨角色系统级优化"，修补 5 轮独立打磨后暴露的角色接缝问题。核心策略：**门面收敛 + 守门机制 + 死代码清理**，不重写既有实现。

**前置依赖**：R1 全部完成（归档编排、readiness_facade、签字流水）。R5 全部完成（EQCR 门禁、状态机）。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| 归档编排 | 复用 R1 已落地的 `archive.py` + `ArchiveOrchestrator`，修正前端 apiPaths 指向 | R1 已实装编排器，本轮只做前端对齐 + deprecated 标记 |
| 就绪检查门面 | **已由 R1 Task 7 完成**（`readiness_facade.py` + 两个 Service 已改为调 gate_engine），本轮仅补 KAM/Independence GateRule | 代码锚定确认 R1 已落地 |
| 复核批注边界 | ReviewRecord 加 `conversation_id` FK，ReviewConversation 关闭前校验 | 不删表，只划边界 |
| QC 规则定义表 | 新建 `qc_rule_definitions` 表 + seed 22 条，QCEngine 运行前按 enabled 过滤 | 最小改动，为 R3 DSL 铺路 |
| 签字字段清理 | 解耦 `signature_level` 字符串控制流，改用 `required_role` 判断 | 字段保留兼容，控制流解绑 |
| 通知铃铛 | 替换 ThreeColumnLayout 静态 Bell 为 NotificationCenter 组件 | 组件已就绪，只需挂载 |
| CI 骨架 | `.github/workflows/ci.yml` + `.pre-commit-config.yaml` + seed schema 校验 | 最小守门，不引入 mypy/bandit |
| 缓存约定 | 仅落文档（steering/conventions.md 追加章节），不改代码 | 本轮收口不重写 |

## 代码锚定核验结果（设计阶段补充）

| 假设 | 核验结果 | 设计影响 |
|------|----------|----------|
| `readiness_facade.py` 已存在 | ✅ R1 Task 7 已落地，SignReadinessService + ArchiveReadinessService 均已改为调 gate_engine | 需求 2 大幅缩减：仅补 2 个 GateRule + 删除 extra_findings 中的冗余项 |
| `ArchiveOrchestrator` 已存在 | ✅ `backend/app/services/archive_orchestrator.py` + `routers/archive.py`（prefix=`/api/projects/{pid}/archive`）| 需求 1 缩减：前端 apiPaths 对齐 + 旧端点加 deprecated |
| `ReviewWorkstation.vue` 已删除 | ✅ fileSearch 零命中 | 需求 6 AC3 自动 PASS |
| ThreeColumnLayout 已有静态 Bell | ✅ 硬编码 `<el-badge :value="0" :hidden="true">`，非 NotificationCenter 组件 | 需求 6 替换为真实组件 |
| `ReviewRecord` 无 `conversation_id` 字段 | ✅ grep 零命中 | 需求 3 需新增字段 + migration |
| `qc_rule_definitions` 表不存在 | ✅ grep 零命中 | 需求 4 需新建 |
| `hypothesis` 不在 requirements.txt | ✅ grep 零命中 | 需求 7 需追加 |
| `.github/workflows` 不存在 | ✅ 零命中 | 需求 7 需新建 |
| `archive_checklists.status` 字段 | ✅ `collaboration_models.py` ArchiveChecklist 有 `status: String(20)` + `created_at` | 需求 1 幂等查询可行 |
| `wizard_state.kam_confirmed` / `independence_confirmed` | ✅ `partner_service.py:228-249` 的 `_compute_sign_extra_findings` 读取这两个字段 | 需求 2 新增 GateRule 替代 extra_findings |

## 数据模型变更

### 新增表

```python
# backend/app/models/qc_rule_models.py (新建)

class QcRuleDefinition(Base, TimestampMixin):
    """QC 规则定义表 — 元数据 + 开关"""
    __tablename__ = "qc_rule_definitions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # QC-01 ~ QC-26
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # blocking | warning | info
    scope: Mapped[str] = mapped_column(String(30), nullable=False)  # workpaper | project | submit_review | sign_off | export_package | eqcr_approval
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # 分类标签
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard_ref: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # ["CAS 1301.12", ...]
    expression_type: Mapped[str] = mapped_column(String(20), nullable=False, default="python")  # python | jsonpath | sql | regex
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)  # Python dotted path 或表达式
    parameters_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
```

### 扩展既有

```python
# backend/app/models/workpaper_models.py — ReviewRecord 新增字段
class ReviewRecord(Base, SoftDeleteMixin, TimestampMixin):
    # ... 既有字段 ...
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("review_conversations.id"),
        nullable=True,
        comment="关联的多轮讨论链（可选）"
    )
```

### Alembic 迁移

- `round6_qc_rule_definitions_20260507.py`：新建 `qc_rule_definitions` 表
- `round6_review_binding_20260507.py`：`review_records` 新增 `conversation_id` 列 + FK

## 服务层变更

### 需求 1：归档前端对齐 + deprecated 标记

**现状**：`ArchiveOrchestrator` + `routers/archive.py` 已由 R1 实装，端点为 `POST /api/projects/{pid}/archive/orchestrate`。前端 `apiPaths.ts` 的 `archive.archive` 仍指向不存在的 `/api/archive/{pid}/archive`。

**变更**：
1. `apiPaths.ts` 的 `archive` 对象重写，`archive` 方法指向 `/api/projects/${pid}/archive/orchestrate`
2. 旧端点 A/B/C 各自路由函数加 `deprecated=True` + `Deprecation` 响应头
3. 前端 `collaborationApi.ts` 的归档调用对齐新路径

### 需求 2：就绪检查补充 GateRule（门面已就绪）

**现状**：`readiness_facade.py` 已存在，`SignReadinessService` 和 `ArchiveReadinessService` 已改为调 `gate_engine.evaluate`。但 KAM 确认 / 独立性确认仍走 `extra_findings`（`_compute_sign_extra_findings` 读 `wizard_state`），不是 gate 规则。

**变更**：
1. 新增 `gate_rules_round6.py`：`KamConfirmedRule` + `IndependenceConfirmedRule`，注册到 `sign_off` + `export_package`
2. `partner_service.py:_compute_sign_extra_findings` 移除 KAM/独立性两项（已由 gate 规则覆盖）
3. `qc_dashboard_service.py:_compute_archive_extra_findings` 同步移除
4. `readiness_facade.py:_SIGN_OFF_RULE_CATEGORY` 追加新规则映射

### 需求 3：复核批注边界

**变更**：
1. `ReviewRecord` 新增 `conversation_id` FK
2. `ReviewConversationService.close_conversation` 加前置校验
3. `IssueTicketService.create_from_conversation` / `wp_review_service.add_comment(is_reject=True)` 加去重
4. 前端 `ReviewInbox.vue` 显示 💬N 角标

### 需求 4：QC 规则定义表

**变更**：
1. 新建 `qc_rule_models.py` + migration
2. 新建 `backend/data/qc_rule_definitions_seed.json`（22 条）
3. `QCEngine.run` 启动前读 `qc_rule_definitions WHERE enabled=true`，过滤 `self.rules`
4. `register_phase14_rules` 同样 check enabled
5. 前端新增 `/qc/rules` 只读页面

### 需求 5：签字字段控制流解耦

**变更**：
1. `sign_service.py:170` 的 `if record.signature_level == "level3"` 改为 `if record.required_role == 'signing_partner' and record.required_order == 3`（或封装为 `record.requires_ca_certificate()`）
2. `extension_models.py:48` 更新 docstring
3. 新增 `scripts/check_signature_level_usage.py` 静态检查脚本

### 需求 6：通知铃铛 + 死代码清理

**变更**：
1. `ThreeColumnLayout.vue` 静态 Bell 替换为 `<slot name="nav-notifications" />`
2. `DefaultLayout.vue` 注入 `NotificationCenter` 组件到该 slot
3. `ReviewWorkstation.vue` 已删除（自动 PASS）
4. `pbc.py` / `confirmations.py` 加 deprecated 响应
5. `ThreeColumnLayout.vue` maturity 标签修正
6. `apiPaths.ts` 清理不存在的端点常量

### 需求 7：CI 骨架

**变更**：
1. `.github/workflows/ci.yml`（4 job）
2. `.pre-commit-config.yaml`（check-json + seed lint）
3. `backend/requirements.txt` 追加 `hypothesis==6.152.4`
4. `scripts/validate_seed_files.py` + `backend/data/_seed_schemas.py`
5. `backend/tests/conftest.py` 新增 `test_all_models_registered`
6. 根目录 `README.md` 追加 CI 章节

## 前端变更

### 新增页面
- `src/views/qc/QcRuleList.vue`：QC 规则定义只读列表（需求 4）

### 修改页面
- `DefaultLayout.vue`：挂载 NotificationCenter（需求 6）
- `ThreeColumnLayout.vue`：新增 `#nav-notifications` slot，替换静态 Bell（需求 6）
- `ReviewInbox.vue`：显示 conversation_id 角标（需求 3）
- `apiPaths.ts`：归档路径对齐 + 清理死链（需求 1、6）
- `collaborationApi.ts`：归档调用对齐（需求 1）

### 路由新增
- `/qc/rules`：QC 规则列表（权限 qc/admin/partner）

## API 变更

| 方法 | 路径 | 变更类型 | 说明 |
|------|------|----------|------|
| GET | `/api/qc/rules` | 新增 | QC 规则定义列表 |
| GET | `/api/qc/rules/{rule_code}` | 新增 | 单条规则详情 |
| POST | `/api/workpapers/projects/{pid}/archive` | 修改 | 加 deprecated 标记 |
| POST | `/api/projects/{pid}/archive` | 修改 | 加 deprecated 标记 |
| POST | `/api/data-lifecycle/projects/{pid}/archive` | 修改 | 加 deprecated 标记 |
| GET | `/api/projects/{pid}/pbc` | 修改 | 返回 developing 状态 |
| GET | `/api/projects/{pid}/confirmations` | 修改 | 返回 developing 状态 |

## 测试策略

| 测试文件 | 覆盖需求 | 场景数 |
|----------|----------|--------|
| `test_archive_deprecated.py` | 需求 1 | 3：deprecated 头存在、前端新路径可达、幂等 |
| `test_gate_rules_round6.py` | 需求 2 | 4：KAM 未确认阻断、独立性未确认阻断、两者都确认通过、extra_findings 不再含冗余项 |
| `test_review_record_conversation_binding.py` | 需求 3 | 3：绑定→关闭失败、解决→关闭成功、去重 |
| `test_qc_rule_definitions_loader.py` | 需求 4 | 3：seed 22 条、enabled=false 跳过、非 python warning |
| `test_signature_level_decoupled.py` | 需求 5 | 2：CA 验证走 required_role、静态检查脚本 exit 0 |
| `test_all_models_registered` (conftest) | 需求 7 | 1：模型注册完整性 |
| `scripts/validate_seed_files.py` | 需求 7 | 6 个 seed 文件 schema 校验 |

## 实施顺序

```
Sprint 1（基础设施 + 低风险清理）：需求 7 → 需求 5 → 需求 6
Sprint 2（服务重构 + 新表）：需求 4 → 需求 3 → 需求 1 → 需求 2
```

先建 CI 骨架（需求 7）确保后续改动有守门，再做低风险的签字清理和死代码（需求 5、6），最后做涉及新表和服务改动的需求（4、3、1、2）。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 旧端点加 deprecated 后前端未切换完导致用户困惑 | deprecated 只加响应头 + warning log，不改返回结构 |
| QC 规则 enabled=false 后业务方不知道 | 前端 `/qc/rules` 页面明确展示开关状态 |
| ReviewRecord.conversation_id FK 对既有数据的影响 | nullable=True，既有记录不受影响 |
| CI 在 GitHub Actions 上首次跑可能因环境差异失败 | 使用 `services: postgres` 容器 + SQLite fallback |
