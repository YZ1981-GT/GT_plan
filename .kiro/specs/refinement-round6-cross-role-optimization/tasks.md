# Refinement Round 6 — 任务清单

按 README 约定：一轮 ≤ 20 任务，分 **2 个 Sprint**。前置依赖：R1 全部完成（归档编排、readiness_facade、签字流水），R5 全部完成（EQCR 门禁）。

## Sprint 1：基础设施 + 低风险清理（需求 7, 5, 6）

- [x] 1. CI 骨架：`.github/workflows/ci.yml`
  - 新建 `.github/workflows/ci.yml`，触发 `push / pull_request to master`
  - 4 个并发 job：`backend-tests`（pytest 排除 integration/e2e）、`backend-lint`（ruff check + check_signature_level_usage.py）、`seed-validate`（validate_seed_files.py）、`frontend-build`（npm ci && npm run build）
  - 使用 `actions/setup-python@v5` + `actions/setup-node@v4`
  - _需求 7 AC1_

- [x] 2. pre-commit 配置 + hypothesis/ruff 入 requirements
  - 新建 `.pre-commit-config.yaml`：`check-json`（对 `backend/data/*.json`）+ 自定义 `json-template-lint`
  - `backend/requirements.txt` 追加 `hypothesis==6.152.4` + `ruff==0.11.12`
  - 验证：`python -m pytest backend/tests/test_production_readiness_properties.py -x --tb=short` 通过
  - 验证：`python -m ruff check backend/ --select E,F --ignore E501` 可运行（不要求零 error，仅确认工具可用）
  - _需求 7 AC2, AC3_

- [x] 3. seed schema 校验脚本
  - 新建 `backend/data/_seed_schemas.py`：每个 seed 文件对应一个 Pydantic BaseModel
  - 新建 `scripts/validate_seed_files.py`：加载 6 个 seed 文件 + schema 校验，失败 exit 1
  - seed 文件：`audit_report_templates_seed.json` / `report_config_seed.json` / `note_templates_seed.json` / `wp_account_mapping.json` / `independence_questions_annual.json` / `qc_rule_definitions_seed.json`（Task 9 产物，本任务先校验前 5 个）
  - _需求 7 AC4_

- [x] 4. 模型注册完整性测试
  - `backend/tests/conftest.py` 新增 `test_all_models_registered`：反射遍历 `backend/app/models/` 下所有 `.py`，断言 `Base.metadata.tables` 已注册每个 `class ... (Base)` 的 `__tablename__`
  - 验证：`python -m pytest backend/tests/conftest.py::test_all_models_registered -v` 通过
  - _需求 7 AC5_

- [x] 5. README CI 章节
  - 根目录 `README.md` 追加 `## CI / pre-commit` 章节：本地 `pre-commit install` 使用说明 + CI 失败排查路径
  - _需求 7 AC7_

- [x] 6. 签字字段控制流解耦
  - `sign_service.py:170` 的 `if record.signature_level == "level3"` 改为 `if record.required_role == 'signing_partner' and record.required_order == 3`
  - `extension_models.py:48` 更新 `signature_level` 字段 docstring 为 legacy 标记
  - 新建 `scripts/check_signature_level_usage.py`：grep `signature_level\s*==|!=` 在 `backend/app/` 下（排除 `extension_models.py` 字段定义），>0 则 exit 1
  - 新建 `backend/tests/test_signature_level_decoupled.py`：断言 CA 验证走 required_role 而非字符串
  - 验证：`python scripts/check_signature_level_usage.py` exit 0
  - _需求 5 AC1-5_

- [x] 7. 通知铃铛挂载
  - `ThreeColumnLayout.vue`：静态 Bell 替换为 `<slot name="nav-notifications" />`
  - `DefaultLayout.vue`：在 `#nav-notifications` slot 注入 `<NotificationCenter />`
  - 顶部导航顺序：复核收件箱 → 🔔通知 → 🛡️独立复核 → 📊EQCR指标
  - 验证：前端编译通过（`npm run build`）
  - _需求 6 AC1, AC2_

- [x] 8. 死代码清理 + deprecated 标记
  - `backend/app/routers/pbc.py`：返回 `{"status": "developing", "items": [], "note": "Feature not implemented; scheduled for R7+"}`
  - `backend/app/routers/confirmations.py`：同上
  - `ThreeColumnLayout.vue` 函证导航项 `maturity: 'pilot'` 改为 `maturity: 'developing'`；模板新增 `v-else-if="item.maturity === 'developing'"` 分支 + `.gt-maturity-dev` 样式（蓝灰色 #909399）
  - `apiPaths.ts`：整个 `archive` 对象重写，所有路径从 `/api/archive/${pid}/...` 改为 `/api/projects/${pid}/archive/...`（对齐后端 `routers/archive.py` 的 prefix）
  - `collaborationApi.ts`：`archiveApi` 对象同步重写路径
  - 旧端点 A/B/C 的 `response.headers["X-Deprecated"]` 改为标准 `Deprecation: version="R6"` 头
  - 确认 `ReviewWorkstation.vue` 已删除（自动 PASS）
  - _需求 6 AC3-6 + 需求 1 AC3-5_

## Sprint 2：服务重构 + 新表（需求 4, 3, 1, 2）

- [x] 9. QC 规则定义表：数据模型 + migration
  - 新建 `backend/app/models/qc_rule_models.py`（`QcRuleDefinition` 模型）
  - Alembic migration `round6_qc_rule_definitions_20260507.py`
  - 导入 `app/models/__init__.py`
  - _需求 4 AC1_

- [x] 10. QC 规则 seed 数据
  - 新建 `backend/data/qc_rule_definitions_seed.json`：22 条规则（QC-01~14 + QC-19~26）
  - 每条含 `rule_code / severity / scope / category / title / description / standard_ref / expression_type='python' / expression(dotted path) / enabled=true / version=1`
  - `standard_ref` 填入 CICPA 准则号（QC-01~14 对应 CAS 1301 具体条款）
  - 更新 Task 3 的 `validate_seed_files.py` 加入此文件校验
  - _需求 4 AC2_

- [x] 11. QCEngine 按 enabled 过滤 + gate 规则同步
  - `qc_engine.py:run` 方法启动前读 `qc_rule_definitions WHERE enabled=true`，用 `rule_code` 交集过滤 `self.rules`
  - `gate_rules_phase14.py:register_phase14_rules` 注册时 check enabled，disabled 的规则不 register
  - 非 python 类型规则 warning log "R6 stub: non-python rule ignored"
  - 新建 `backend/tests/test_qc_rule_definitions_loader.py`：3 场景（seed 22 条、enabled=false 跳过、非 python warning）
  - _需求 4 AC3-7_

- [x] 12. QC 规则前端只读页面
  - 新建 `src/views/qc/QcRuleList.vue`：表格展示规则列表（rule_code / title / severity / scope / standard_ref / enabled）
  - 新建后端路由 `backend/app/routers/qc_rules.py`：`GET /api/qc/rules`（权限 qc/admin/partner）
  - 路由注册到 `router_registry.py`
  - 前端路由 `/qc/rules` 注册
  - _需求 4 AC5_

- [x] 13. 复核批注边界：数据模型 + migration
  - `ReviewRecord` 新增 `conversation_id: UUID | null`（FK → `review_conversations.id`）
  - Alembic migration `round6_review_binding_20260507.py`
  - _需求 3 AC1_

- [x] 14. 复核批注边界：服务层逻辑
  - `ReviewConversationService.close_conversation`：关闭前校验是否有未解决的 ReviewRecord（`conversation_id == cid AND status != 'resolved'`），有则拒绝并返回 `CONVERSATION_HAS_OPEN_RECORDS`
  - `IssueTicketService.create_from_conversation` / `wp_review_service.add_comment(is_reject=True)`：去重校验，已存在 `IssueTicket(source='review_comment', source_ref_id=record.id)` 则返回已有工单 id
  - 新建 `backend/tests/test_review_record_conversation_binding.py`：3 场景
  - _需求 3 AC2-5_

- [x] 15. 复核批注边界：前端角标
  - `ReviewInbox.vue`：每条 ReviewRecord 显示 💬N 角标（N = conversation 消息数），点击跳转会话详情
  - _需求 3 AC4_

- [x] 16. 归档幂等 + 测试
  - `ArchiveOrchestrator.orchestrate` 加幂等逻辑：同一 `project_id` 24h 内有 `status in ('completed','running')` 的 ArchiveJob 则直接返回（不重复打包）
  - 新建 `backend/tests/test_archive_deprecated.py`：3 场景（Deprecation 头存在且值为 `version="R6"`、新路径 `/api/projects/{pid}/archive/orchestrate` 可达、幂等返回同 job_id）
  - _需求 1 AC6, AC7_

- [x] 17. 就绪检查补充 GateRule
  - 新建 `backend/app/services/gate_rules_round6.py`：`KamConfirmedRule`（读 `wizard_state.kam_confirmed`）+ `IndependenceConfirmedRule`（读 `wizard_state.independence_confirmed`）
  - 注册到 `sign_off` + `export_package` gate
  - `readiness_facade.py:_SIGN_OFF_RULE_CATEGORY` + `_EXPORT_PACKAGE_RULE_CATEGORY` 追加映射
  - `partner_service.py:_compute_sign_extra_findings` 移除 KAM/独立性两项（已由 gate 覆盖）
  - `qc_dashboard_service.py:_compute_archive_extra_findings` 同步移除
  - 新建 `backend/tests/test_gate_rules_round6.py`：4 场景（KAM 未确认阻断、独立性未确认阻断、两者确认通过、extra_findings 无冗余）
  - _需求 2 AC1-7_

- [x] 18. 前端死链检查脚本
  - 新建 `scripts/dead-link-check.js`（Node 脚本）：扫描 `apiPaths.ts` 所有端点常量，断言均能在 `router_registry.py` 注册树中找到对应 prefix；找不到则 exit 1
  - 纳入 CI `seed-validate` job
  - _需求 6 AC7_

---

## 验证检查点

### Sprint 1 完成后
```bash
# 后端测试
python -m pytest backend/tests/test_signature_level_decoupled.py -v --tb=short
python scripts/check_signature_level_usage.py
python scripts/validate_seed_files.py

# 前端编译
npm run build  # in audit-platform/frontend

# 属性测试确认
python -m pytest backend/tests/test_production_readiness_properties.py -x --tb=short
```

### Sprint 2 完成后
```bash
# 全量后端测试（排除 integration/e2e）
python -m pytest backend/tests/ --ignore=backend/tests/integration --ignore=backend/tests/e2e -x --tb=short

# 新增测试
python -m pytest backend/tests/test_qc_rule_definitions_loader.py backend/tests/test_review_record_conversation_binding.py backend/tests/test_archive_deprecated.py backend/tests/test_gate_rules_round6.py -v --tb=short

# 前端编译
npm run build  # in audit-platform/frontend

# 死链检查
node scripts/dead-link-check.js
```
