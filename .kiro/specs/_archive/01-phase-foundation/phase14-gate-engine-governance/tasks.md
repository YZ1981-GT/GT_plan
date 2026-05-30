# Phase 14: 统一门禁引擎与治理收敛 - 实施任务（企业级落地版）

## 阶段0: 规格硬化与实施前置

- [x] 1. 门禁口径基线冻结
  - [x] 1.1 盘点现有三入口差异：`working_paper.py submit-review` vs `partner_dashboard.py workpaper-readiness` vs `word_export.py export`，产出《门禁入口差异对账表.md》
  - [x] 1.2 冻结 SoD 互斥矩阵（写入 `backend/app/services/sod_guard_service.py::CONFLICT_MATRIX` 常量）：
    - `(preparer, partner_approver)` → 阻断
    - `(preparer, reviewer)` → 阻断（例外需合伙人审批）
    - `(qc_reviewer, preparer)` → 阻断
  - [x] 1.3 冻结 trace_id 格式：`trc_{yyyyMMddHHmmss}_{uuid[:12]}`，写入 `backend/app/services/trace_event_service.py::generate_trace_id()`
  - [x] 1.4 冻结 reason_code 枚举：写入 `backend/app/models/phase14_enums.py::ReasonCode(str, Enum)` 共 20 个值（对齐 design §8.2）
  - [x] 1.5 冻结 severity 枚举：`GateSeverity(blocking/warning/info)` + `IssueSeverity(blocker/major/minor/suggestion)`

## 阶段1: MVP核心闭环

- [x] 2. 统一过程留痕模型
  - [x] 2.1 创建 `backend/app/models/phase14_models.py`：`TraceEvent` ORM（字段对齐 migration.sql trace_events 表，含 from_status/to_status/content_hash）
  - [x] 2.2 创建 Alembic 迁移 `backend/alembic/versions/phase14_001_trace_and_gate.py`：建 trace_events + gate_decisions 两张表 + 6 个索引
  - [x] 2.3 创建 `backend/app/services/trace_event_service.py`：
    - `generate_trace_id() -> str` — 格式 `trc_{yyyyMMddHHmmss}_{uuid[:12]}`
    - `async write(db, project_id, event_type, object_type, object_id, actor_id, actor_role, action, decision=None, reason_code=None, from_status=None, to_status=None, before_snapshot=None, after_snapshot=None, content_hash=None, version_no=None, trace_id=None) -> str` — 写入 trace_events，返回 trace_id
    - `async replay(db, trace_id, level='L1') -> dict` — L1 返回 who/what/when，L2 含 snapshot，L3 含 content_hash
    - `async query(db, project_id, filters, page=1, page_size=50) -> dict` — 分页查询
  - [x] 2.4 创建 `backend/app/routers/trace.py`：
    - `GET /api/trace/{trace_id}/replay?level=L1|L2|L3` — 调用 `trace_event_service.replay()`
    - `GET /api/trace?project_id=&event_type=&page=&page_size=` — 调用 `trace_event_service.query()`
  - [x] 2.5 注册路由到 `backend/app/services/router_registry.py` 第 8 组（系统管理）
  - [x] 2.6 接入 5 条主链路 trace 写入：
    - `working_paper.py::submit_review()` → `trace_event_service.write(event_type='submit_review')`
    - `partner_dashboard.py::check_workpaper_readiness()` → `trace_event_service.write(event_type='sign_off')`
    - `word_export.py::create_export_task()` → `trace_event_service.write(event_type='export')`
    - `procedures.py::update_trim_status()` → `trace_event_service.write(event_type='trim_applied'|'trim_rollback')`

- [x] 3. 统一门禁引擎
  - [x] 3.1 创建 `backend/app/services/gate_engine.py`：
    - `class GateRule(ABC)`: `rule_code: str`, `error_code: str`, `severity: str`, `async check(context) -> GateRuleHit | None`
    - `class RuleRegistry`: `_rules: dict[str, list[GateRule]]`, `register(gate_type, rule)`, `get_rules(gate_type) -> list`
    - `class GateEngine`:
      - `async evaluate(db, gate_type: str, project_id: UUID, wp_id: UUID|None, actor_id: UUID, context: dict) -> GateEvaluateResult`
      - 内部流程：load rules → resolve context → execute rules → sort by severity → assemble decision → persist gate_decisions + trace_events
    - `class GateEvaluateResult`: `decision: str`, `hit_rules: list[GateRuleHit]`, `trace_id: str`
    - `class GateRuleHit`: `rule_code, error_code, severity, message, location: dict, suggested_action: str`
  - [x] 3.2 创建 `backend/app/models/phase14_models.py` 追加：`GateDecision` ORM
  - [x] 3.3 创建 `backend/app/routers/gate.py`：
    - `POST /api/gate/evaluate` — body: `{gate_type, project_id, wp_id?, actor_id, context}` → 调用 `gate_engine.evaluate()`
    - 幂等校验：同一 `project_id + gate_type + trace_id` 5 秒内重复请求返回缓存结果
  - [x] 3.4 注册路由到 router_registry.py

- [x] 4. 三入口接入
  - [x] 4.1 `working_paper.py::submit_review()` 改为先调 `gate_engine.evaluate(gate_type='submit_review')`，block 时返回 409 + hit_rules
  - [x] 4.2 `partner_dashboard.py::check_workpaper_readiness()` 改为调 `gate_engine.evaluate(gate_type='sign_off')`
  - [x] 4.3 `word_export.py::create_export_task()` 改为调 `gate_engine.evaluate(gate_type='export_package')`
  - [x] 4.4 编写一致性回归脚本 `backend/scripts/phase14/check_gate_consistency.py`：同一 wp_id + context 调三入口，断言 decision 一致

- [x] 5. SoD 职责分离
  - [x] 5.1 创建 `backend/app/services/sod_guard_service.py`：
    - `CONFLICT_MATRIX: dict[tuple[str,str], str]` — 3 组互斥对
    - `async check(db, project_id, wp_id, actor_id, target_role) -> SoDCheckResult`
    - 内部：查 working_papers.preparer_id/reviewer_id/partner_reviewed_by，与 actor_id 比对
    - 冲突时写 trace_events(event_type='sod_checked', decision='block')
    - `class SoDCheckResult`: `allowed: bool, conflict_type: str|None, policy_code: str|None, trace_id: str`
  - [x] 5.2 创建 `backend/app/routers/sod.py`：
    - `POST /api/sod/check` — body: `{project_id, wp_id, actor_id, target_role}` → 200 或 403
  - [x] 5.3 在 `gate_engine.py` 的 evaluate 流程中，submit_review/sign_off 两个 gate_type 自动调用 `sod_guard_service.check()`
  - [x] 5.4 前端 `WorkpaperList.vue` 提交按钮 click 前先调 `/api/sod/check`，403 时弹 `ElMessageBox.alert` 显示 conflict_type + 建议操作，弹窗不可自动关闭
  - [x] 5.5 `backend/app/core/security.py` 新增：角色变更时写 Redis key `sod_revoke:{user_id}:{project_id}` TTL=token剩余有效期
  - [x] 5.6 `backend/app/deps.py::get_current_user()` 新增 SoD 黑名单检查：`redis.exists(f'sod_revoke:{user_id}:{project_id}')` → 403

## 阶段2: 扩展规则落地（QC-19~QC-26）

- [x] 6. 程序裁剪门禁规则
  - [x] 6.1 在 `backend/app/services/gate_engine.py` 新增 `QC19MandatoryTrimRule(GateRule)`：
    - `rule_code='QC-19'`, `error_code='QC_PROCEDURE_MANDATORY_TRIMMED'`, `severity='blocking'`
    - SQL: `SELECT id FROM procedure_instances WHERE wp_id=:wp_id AND trim_category='mandatory' AND trim_status='trimmed'`
    - `location`: `{"wp_id": wp_id, "section": "procedure_status", "procedure_id": row.id}`
    - `suggested_action`: "不允许裁剪 mandatory 审计程序，请恢复程序或走例外审批"
  - [x] 6.2 新增 `QC20ConditionalNoEvidenceRule(GateRule)`：
    - `rule_code='QC-20'`, `error_code='QC_PROCEDURE_EVIDENCE_MISSING'`, `severity='blocking'`
    - SQL: `SELECT id FROM procedure_instances WHERE wp_id=:wp_id AND trim_category='conditional' AND trim_status='trimmed' AND (trim_evidence_refs IS NULL OR jsonb_array_length(trim_evidence_refs)=0)`
    - `suggested_action`: "conditional 程序裁剪缺少证据引用，请补充 trim_evidence_refs 后重试"
  - [x] 6.3 在 `RuleRegistry` 中注册 QC-19/QC-20 到 `submit_review` 和 `sign_off` 两个 gate_type
  - [x] 6.4 前端 `WorkpaperList.vue` 阻断面板：QC-19/QC-20 命中时，点击 `location.procedure_id` 跳转到 `/projects/:id/procedures?highlight=:procedure_id`

- [x] 7. LLM/证据链/版本映射门禁规则
  - [x] 7.1 `QC21ConclusionWithoutEvidenceRule(GateRule)`：
    - SQL: `SELECT 1 FROM working_papers WHERE id=:wp_id AND parsed_data->'ai_content'->'review_suggestions' @> '[{"is_key_conclusion":true}]' AND NOT EXISTS(SELECT 1 FROM ... WHERE evidence_refs IS NOT NULL AND jsonb_array_length(evidence_refs)>0)`
    - `error_code='QC_CONCLUSION_WITHOUT_EVIDENCE'`
    - `suggested_action`: "关键结论缺少证据锚点，请绑定 evidence_id"
  - [x] 7.2 `QC22LowConfidenceSingleSourceRule(GateRule)`：
    - 检查 `parsed_data.ai_content` 中 `is_key_conclusion=true` 且 `evidence_count=1` 且关联附件 `ocr_confidence < 0.7`
    - `error_code='QC_LOW_CONFIDENCE_SINGLE_SOURCE'`
    - `suggested_action`: "关键结论仅依赖低置信证据，需补充第二证据或人工确认说明"
  - [x] 7.3 `QC23LLMPendingConfirmationRule(GateRule)`：
    - SQL: `SELECT 1 FROM wp_ai_generations WHERE wp_id=:wp_id AND status='pending_user_confirm'`
    - 同时检查 `parsed_data.ai_content.explanation_draft.status='pending'`
    - `error_code='QC_LLM_PENDING_CONFIRMATION'`
    - `suggested_action`: "存在未确认的LLM关键内容，请逐条执行采纳/拒绝"
  - [x] 7.4 `QC24LLMTrimConflictRule(GateRule)`：
    - 检查 `wp_ai_generations` 中 `status='confirmed'` 的记录是否与 `procedure_instances.trim_status='trimmed'` 冲突
    - `error_code='QC_LLM_TRIM_CONFLICT'`
    - `suggested_action`: "LLM推荐与裁剪策略冲突，请回退采纳并按裁剪规则处理"
  - [x] 7.5 `QC25ReportNoteVersionStaleRule(GateRule)`：
    - 检查 `audit_report` 段落引用的 `note_version` < `disclosure_notes` 当前 `version`
    - `error_code='QC_REPORT_NOTE_VERSION_STALE'`
    - `suggested_action`: "审计报告正文引用附注版本已过期，请刷新引用并重新确认关键段落"
  - [x] 7.6 `QC26NoteSourceMappingMissingRule(GateRule)`：
    - 检查 `disclosure_notes` 中 `is_key_disclosure=true` 的章节 `source_cells IS NULL`
    - `error_code='QC_NOTE_SOURCE_MAPPING_MISSING'`
    - `suggested_action`: "附注关键披露缺少来源映射，请补齐 source_cells 并重跑一致性检查"
  - [x] 7.7 在 `RuleRegistry` 中注册 QC-21~26 到三个 gate_type，在 `backend/app/schemas/phase14_schemas.py` 定义 `GateRuleHitSchema`/`GateEvaluateRequestSchema`/`GateEvaluateResponseSchema`

## 阶段3: 权限与前端交互收敛

- [x] 8. WOPI只读策略
  - [x] 8.1 `backend/app/services/wopi_service.py::check_file_info()` 改造：
    - 场景1（编制人+draft/edit_complete）：`UserCanWrite=True`
    - 场景2（复核人/合伙人）：`UserCanWrite=False`, `ReadOnly=True`, `ReadOnlyReason="复核模式"`
    - 场景3（非锁持有者）：`UserCanWrite=False`, `ReadOnly=True`, `ReadOnlyReason="其他用户正在编辑"`
    - 场景4（签字窗口 partner_ready/signed_off）：`UserCanWrite=False`, `ReadOnly=True`, `ReadOnlyReason="签字窗口只读"`
    - 每次 check_file_info 写 trace_events(event_type='wopi_access', decision=allow/block)

- [x] 9. 前端阻断面板
  - [x] 9.1 创建 `audit-platform/frontend/src/components/gate/GateBlockPanel.vue`：
    - Props: `hitRules: GateRuleHit[]`, `traceId: string`
    - 状态机：`normal` | `evaluating`（el-loading） | `blocked`（红色面板） | `warned`（橙色面板） | `error`（灰色+trace_id）
    - 阻断项列表按 `severity=blocking` 优先，同 rule_code 聚合显示计数（如 "QC-16 数据不一致 ×3"）
    - 每条阻断项可点击 `location` 跳转：`section=audit_explanation` → 滚动到说明编辑区，`section=procedure_status` → 跳转程序裁剪页
    - trace_id 显示在面板底部，el-button 可复制到剪贴板
    - 阻断面板不可自动关闭，必须用户点"关闭"或修复后重新评估
  - [x] 9.2 创建 `audit-platform/frontend/src/components/gate/SoDConflictDialog.vue`：
    - Props: `conflictType: string`, `policyCode: string`, `traceId: string`
    - ElMessageBox.alert 样式，不可自动关闭，显示冲突类型 + 建议操作
  - [x] 9.3 `WorkpaperList.vue` 提交复核按钮改造：
    - click → `api.post('/gate/evaluate', {gate_type:'submit_review', ...})` → blocked 时展开 GateBlockPanel → allow 时执行提交
    - 按钮点击后立即 `disabled=true`，响应后恢复（防重复提交）
  - [x] 9.4 `PartnerDashboard.vue` 签字按钮同理接入 gate_type='sign_off'
  - [x] 9.5 `audit-platform/frontend/src/services/gateApi.ts`：
    - `evaluateGate(params): Promise<GateEvaluateResponse>`
    - `checkSoD(params): Promise<SoDCheckResponse>`
    - TypeScript 类型从 openapi.yaml 生成

## 阶段4: 治理增强与灰度

- [x] 10. 规则配置分层
  - [x] 10.1 创建 `backend/app/models/phase14_models.py` 追加 `GateRuleConfig` ORM：`id, rule_code, config_level(platform/tenant), threshold_key, threshold_value, tenant_id(nullable), updated_by, updated_at`
  - [x] 10.2 `gate_engine.py` evaluate 时先加载 platform 配置，再 overlay tenant 配置（tenant 不可覆盖 platform 级 blocking 规则）
  - [x] 10.3 创建 `GET /api/gate/rules` 查询当前生效规则列表 + `PUT /api/gate/rules/{rule_code}` 修改租户级阈值

- [x] 11. 冲突解释模板
  - [x] 11.1 创建 `backend/data/gate_explanation_templates.json`：每个 error_code 对应中文修复建议模板（含占位符 `{wp_code}`, `{diff_amount}`, `{procedure_name}`）
  - [x] 11.2 `GateEngine.evaluate()` 命中规则后从模板渲染 `suggested_action`

## 阶段5: 企业级增强

- [x] 12. 运维监控
  - [x] 12.1 `gate_engine.py` evaluate 入口增加 Prometheus 指标：
    - `gate_evaluate_total` (counter, labels: gate_type, decision)
    - `gate_evaluate_duration_seconds` (histogram, labels: gate_type)
    - `gate_rule_hit_total` (counter, labels: rule_code, severity)
  - [x] 12.2 `trace_event_service.py` write 失败时增加：
    - `trace_write_error_total` (counter)
    - 告警规则：`rate(trace_write_error_total[10m]) / rate(trace_write_total[10m]) > 0.001` → P0
  - [x] 12.3 误阻断率监控：`gate_appeal_approved_total / gate_evaluate_total{decision="block"}` > 0.03 持续 7d → P1
  - [x] 12.4 SoD 校验延迟：`histogram_quantile(0.95, sod_check_duration_seconds)` > 0.2 持续 5min → P2

- [x] 13. 数据迁移
  - [x] 13.1 创建 `backend/scripts/phase14/backfill_trace_events.py`：
    - 从 `audit_logs` 表读取 event_type IN ('workpaper_online_save','submit_review','sign_off','export') 的记录
    - 映射到 trace_events 字段，标记 `reason_code='BACKFILL_MIGRATION'`
    - 批量 INSERT，每 1000 条 commit 一次，记录进度到 stdout
  - [x] 13.2 灰度兼容：`gate_engine.py` 增加 `feature_flags.is_enabled('gate_engine_v2', project_id)` 检查，未启用的项目走旧逻辑不写 gate_decisions
  - [x] 13.3 存量底稿兼容：`working_paper.py::update_status()` 在状态流转时，如果目标状态为 review_* 且 gate_engine 已启用，自动触发 SoD 校验

- [x] 14. CI 门槛
  - [x] 14.1 `.github/workflows/phase14-ci.yml`（或等效 CI 配置）：
    - PR 阶段：`python -m pytest backend/tests/test_phase14*.py -v --tb=short` 通过率 = 100%
    - 预发阶段：全量 IT `python -m pytest backend/tests/ -k "phase14" -v` 通过率 >= 99%
    - 生产前：`python backend/scripts/phase14/check_gate_consistency.py` + `check_sod_matrix.py` + `check_wopi_write_guard.py` 全部 PASS
  - [x] 14.2 失败分级写入 CI 配置注释：
    - P0（权限绕过/SoD 放行/trace 断链）→ 立即阻断合并
    - P1（误阻断率超标/延迟超标）→ 24h 内修复
    - P2（文案/排序/UI 偏差）→ 下窗口修复

## 测试与验收

- [x] 15. 单元测试 `backend/tests/test_phase14_gate.py`
  - [x] P14-UT-001: QC-19 mandatory 裁剪 → 阻断（mock procedure_instances trim_category=mandatory, trim_status=trimmed）
  - [x] P14-UT-002: QC-19 mandatory 未裁剪 → 通过
  - [x] P14-UT-003: QC-20 conditional 裁剪无证据 → 阻断
  - [x] P14-UT-004: QC-20 conditional 裁剪有证据 → 通过
  - [x] P14-UT-005: QC-21 关键结论无证据 → 阻断
  - [x] P14-UT-006: QC-21 关键结论有证据 → 通过
  - [x] P14-UT-007: QC-22 低置信单点 → 阻断
  - [x] P14-UT-008: QC-22 高置信或多证据 → 通过
  - [x] P14-UT-009: QC-23 LLM pending → 阻断
  - [x] P14-UT-010: QC-23 LLM confirmed → 通过
  - [x] P14-UT-011: QC-24 LLM 裁剪冲突 → 阻断
  - [x] P14-UT-012: QC-24 无冲突 → 通过
  - [x] P14-UT-013: QC-25 附注版本过期 → 阻断
  - [x] P14-UT-014: QC-25 附注版本最新 → 通过
  - [x] P14-UT-015: QC-26 关键披露缺映射 → 阻断
  - [x] P14-UT-016: QC-26 映射完整 → 通过

- [x] 16. 单元测试 `backend/tests/test_phase14_sod.py`
  - [x] P14-UT-017: preparer == partner_approver → 403 SOD_CONFLICT_DETECTED
  - [x] P14-UT-018: preparer != reviewer → 200 allowed=true
  - [x] P14-UT-019: qc_reviewer 尝试编辑 → 403
  - [x] P14-UT-020: SoD 黑名单 Redis key 存在 → get_current_user 返回 403

- [x] 17. 单元测试 `backend/tests/test_phase14_trace.py`
  - [x] P14-UT-021: trace_event_service.write() 字段完整性（所有必填字段非空）
  - [x] P14-UT-022: trace_event_service.replay(level='L1') 返回 who/what/when
  - [x] P14-UT-023: trace_event_service.replay(level='L2') 返回含 snapshot
  - [x] P14-UT-024: trace_event_service.replay(level='L3') 返回含 content_hash
  - [x] P14-UT-025: generate_trace_id() 格式校验 `^trc_\d{14}_[a-f0-9]{12}$`

- [x] 18. 单元测试 `backend/tests/test_phase14_engine.py`
  - [x] P14-UT-026: gate_engine.evaluate() 决策聚合：多条 blocking → decision=block
  - [x] P14-UT-027: gate_engine.evaluate() 排序：blocking 在 warning 前
  - [x] P14-UT-028: gate_engine.evaluate() 幂等：同 trace_id 5 秒内返回缓存
  - [x] P14-UT-029: gate_engine.evaluate() 写入 gate_decisions + trace_events

- [x] 19. 集成测试 `backend/tests/test_phase14_integration.py`
  - [x] P14-IT-001: 三入口同 wp_id+context → decision 一致
  - [x] P14-IT-002: WOPI check_file_info 复核人 → UserCanWrite=False
  - [x] P14-IT-003: WOPI check_file_info 编制人+draft → UserCanWrite=True
  - [x] P14-IT-004: `/api/gate/evaluate` 合同测试：响应字段 decision/hit_rules/trace_id 类型正确
  - [x] P14-IT-005: `/api/trace/{id}/replay` 合同测试：events[].event_type/actor_id/action 非空
  - [x] P14-IT-006: `/api/sod/check` 合同测试：allowed/trace_id 非空
  - [x] P14-IT-007: trace_events 留痕覆盖率：提交+签字+导出三条链路各执行一次，断言 trace_events 记录数 >= 3

- [x] 20. 安全测试 `backend/tests/test_phase14_security.py`
  - [x] P14-SEC-001: 复核人通过 WOPI put_file 尝试写入 → 403
  - [x] P14-SEC-002: preparer 尝试签字 → SoD 403
  - [x] P14-SEC-003: SoD 黑名单 token 访问 → 403

- [x] 21. 灰度测试
  - [x] P14-GRAY-001: 10% 项目启用 gate_engine_v2，观察 24h 误阻断率 <= 3%
  - [x] P14-GRAY-002: 30% 项目放量，观察 24h，可执行回滚演练（关闭 feature_flag 后旧逻辑生效）

## 验收脚本（必须产出）

- [x] 22. 脚本化验收
  - [x] 22.1 `backend/scripts/phase14/check_gate_consistency.py` — 随机选 10 个 wp_id，三入口调用断言 decision 一致
  - [x] 22.2 `backend/scripts/phase14/check_rule_coverage.py` — 断言 RuleRegistry 中 QC-19~26 全部注册到 submit_review/sign_off
  - [x] 22.3 `backend/scripts/phase14/check_wopi_write_guard.py` — 模拟复核人/合伙人/签字窗口调 check_file_info，断言 UserCanWrite=False
  - [x] 22.4 `backend/scripts/phase14/check_trace_coverage.py` — 查询最近 24h trace_events，断言 submit_review/sign_off/export 三种 event_type 均有记录
  - [x] 22.5 `backend/scripts/phase14/check_sod_matrix.py` — 遍历 CONFLICT_MATRIX 所有组合，断言冲突场景返回 403

## 放行门槛（Go/No-Go）

- [x] G1 三入口门禁一致率 = 100%（P14-IT-001 通过）
- [x] G2 QC-19~QC-26 全部可执行并可回放（P14-UT-001~016 + trace replay 通过）
- [x] G3 gate_decisions 留痕覆盖率 >= 95%（P14-IT-007 + check_trace_coverage.py 通过）
- [x] G4 越权写入 = 0（P14-SEC-001 通过）
- [x] G5 合同测试通过，无字段漂移（P14-IT-004/005/006 通过）
- [x] G6 trace_events 核心链路留痕覆盖率 >= 95%
- [x] G7 SoD 冲突拦截率 = 100%（P14-SEC-002/003 + P14-UT-017~020 通过）
- [x] G8 trace 回放成功率 >= 99%（P14-UT-022~024 通过）
- [x] G9 灰度误阻断率 <= 3%（P14-GRAY-001/002 通过）
- [x] G10 CI 门槛全部 PASS（14.1 配置生效）
