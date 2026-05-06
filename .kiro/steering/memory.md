---
inclusion: always
---

# 持久记忆

每次对话自动加载。详细架构见 `#architecture`，编码规范见 `#conventions`，开发历史见 `#dev-history`。
当 memory.md 超过 ~200 行时，自动将已完成事项迁移到 dev-history.md，技术决策迁移到 architecture.md，规范迁移到 conventions.md，保持自身简洁（只留状态摘要+活跃待办）。

## 用户偏好（核心）

- 语言：中文
- 部署：本地优先、轻量方案
- 启动：`start-dev.bat` 一键启动后端 9980 + 前端 3030
- 打包：build_exe.py（PyInstaller），不要 .bat
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致，空壳标记 developing
- 前后端联动：不能只开发后端不管前端
- 删除必须二次确认，所有删除先进回收站
- 一次性脚本用完即删
- 提建议前先验证（不要引用过时记录，vue-tsc exit 0 = 零错误，不要再提已修复的问题）
- 给出建议时必须反复论证，提供最仔细的可落地方案，不能泛泛而谈或停留在表面描述
- 判断前端模块是否存在，必须同时检查 views/ 根目录 + components/ 子目录
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md
- 目标并发规模 6000 人
- 表格列宽要足够大，不折行不省略号截断
- 表格编辑需支持查看/编辑模式切换
- 复制按钮命名：工具栏"复制整表" vs 右键"复制选中区域"
- 系统打磨采用 PDCA 迭代模式：提建议→成 spec 三件套→实施→复盘→下一轮新需求，直到可改进项穷尽
- 打磨迭代具体化为"5 角色轮转"：合伙人/项目经理/质控/审计助理/EQCR 独立复核，每轮只站单一角色视角找断层，规则见 `.kiro/specs/refinement-round1-review-closure/README.md`
- 每轮 requirements.md 起草后必须做"代码锚定交叉核验"（grep 所有假设的字段/表/端点/枚举），发现硬错立刻回补到文档，避免错误带到 design 阶段
- 标任务 [x] 前必须跑 pytest 或对应测试通过，而非仅因"代码文件存在"就标完成；用户明确要求做完整复盘时要诚实暴露问题而非粉饰

## Spec 工作流规范（production-readiness 复盘沉淀）

- design.md 起草必须做"代码锚定"：每个修改点列文件+行号/函数名，npm 包要 `npm view` 验证存在，字段/枚举/端点路径 grep 核对，避免事后大量校正备忘
- tasks.md 只放可被自动化工具推进的编码任务；手动浏览器验证（如"输入公式看结果"）应放 spec 末尾"UAT 验收清单"，不占 taskStatus 工作流
- Sprint 粒度按"验证边界"切分：每个 Sprint ≤10 个任务，强制回归测试+UAT 才进下一 Sprint（反例：production-readiness Sprint 2 塞 20+ 小改）
- 任务描述中引用的依赖包、类名、API 路径，变化后要回填更新（如 0.1/0.2 的 `@univerjs/preset-sheets-formula` 实际不存在）
- **R5 复盘教训**：标 `[x]` 前必须跑 pytest 验证；"代码文件存在"不等于"功能可用"。Task 12/13 初次标完成时其实 gate_engine/sign_service 有隐藏 flush bug，集成测试才能暴露
- **跨文件字段/枚举假设必须 grep 核对**：User.metadata_、WorkHour.status 类型、ProjectStatus.in_progress、CompetenceRating.A 这些都是我凭印象写的错误假设，导致代码 runtime 失败
- **测试 fixture 模板**：每个新 test 文件应复用邻居文件的 `db_session` fixture 模板（见 test_eqcr_gate_approve.py 为样板：本地 _engine + pytest_asyncio.fixture + Base.metadata.create_all）；backend/tests/conftest.py 不提供 db_session

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- 前端依赖共 22 生产 + 7 开发：关键新增 mitt@3.0.1、nprogress@0.2.0、unplugin-auto-import@21.0.0、unplugin-vue-components@32.0.0、@univerjs/presets@0.21.1、@univerjs/preset-sheets-core@0.21.1（公式引擎内置）、@univerjs/sheets-formula@0.21.1、opentype.js@1.3.5、xlsx@0.18.5
- 后端新增测试依赖 hypothesis@6.152.4 + ruff@0.11.12（R6 Task 2 写入 requirements.txt）
- PG ~160 张表（152 基线 + R5 新增 6 张 + R6 新增 qc_rule_definitions + review_records.conversation_id 列），Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-07 实测核对）

- vue-tsc 0 错误（2026-05-06 全部修复：el-tag type 联合类型标注 + dictStore.type() 返回类型收窄 + 模板 `:type` 绑定加 `|| undefined`），Vite 构建通过
- 后端 **151** 个路由文件，**226** 个服务文件（含子目录 import_engine/、wp_scripts/ 等），**51** 个模型文件，11 个 core 模块，9 个 middleware，~152 张表（此前 memory 记录 127/181/39 已过时）
- 后端 `backend/app/workers/` 模块 4 个：sla_worker、import_recover_worker、outbox_replay_worker、import_worker（每个导出 `async def run(stop_event)`）
- 前端 **93** 个 Vue 页面（views/），**186** 个组件（components/ 含所有子目录），16 个 composables，9 个 stores，19 个 services，19 个 utils（此前 memory 记录 80/20 已过时，components 统计之前只数 common/ 子目录）
- pytest collection 2741 tests / 7 errors（2026-05-07 实测）：7 个测试模块因 3 个符号漂移 ImportError：`wrap_ai_output` 不存在（真实名 `wrap_ai_content`，影响 test_ai_content_structured.py + test_ai_content_confirm_flow.py）、`build_ai_contribution_statement` 不存在于 pdf_export_engine（真实位置 ai_contribution_watermark.generate_short_statement，影响 test_ai_contribution_statement.py）、`IndependenceDeclaration` 不存在（真实名 `AnnualIndependenceDeclaration`，影响 test_independence_service.py + test_my_pending_independence.py + test_handover_e2e.py + test_handover_service.py）
- 后端测试：98+ 个根目录测试 + 4 个 e2e + 4 个 integration + R5 新增 test_eqcr_full_flow/test_eqcr_state_machine_properties/test_eqcr_component_auditor_review
- git 分支：feature/global-component-library（R6 实施 + 复盘修复已推送，最新 commit 4194e88）
- 本分支相对 master 新增前端依赖（后端 requirements.txt 无变化）：生产 7 个（@univerjs/presets、@univerjs/preset-sheets-core、@univerjs/sheets-formula、mitt、nprogress、opentype.js、xlsx）+ 开发 3 个（@types/nprogress、unplugin-auto-import、unplugin-vue-components）；已在 audit-platform/frontend 执行 npm install 安装完成
- .gitignore 已排除 backend/ 下 wp_storage 运行时 UUID 目录（glob `backend/[0-9a-f]*-[0-9a-f]*-[0-9a-f]*-[0-9a-f]*-[0-9a-f]*/`）
- **production-readiness spec 全部完成**（4 Sprint / 46 需求）：
  - Sprint 1（P0 数据正确性）：底稿保存事件→附注同步、Dashboard 趋势图真实 API、Dirty 标记完整覆盖、QC 项目汇总 N+1 优化、审计报告 final 保护、QC-16 字段修正、ReviewInbox 跳转修正、报表两张表数据驱动、AuditCheckDashboard 批量接口、PBC/函证路由注册、看板卡片跳转、个人工作台待办工时
  - Sprint 2（P1+P2 核心体验）：复核收件箱导航+badge、UUID→姓名映射、进度百分比、借贷平衡含损益、错报超限门禁、重要性变更联动、账套导入通知、抽样/汇总年度从上下文、导出 Word 入口、QC-17 改 ORM、批量驳回逐条原因、工时编辑修正、知识库预览认证、QC 归档缓存、编制人筛选下拉、版本历史抽屉、自动保存、并发冲突检测、预填充保留公式
  - Sprint 3（P2+P3 前置）：项目启动步骤引导、xlsx 公式值预加载、底稿导出 PDF、路由前缀规范（删除 hasattr 补丁）、Worker 拆分（3 模块）、AI 分析缓存、对比视图上年列、序时账异常标记
  - Sprint 4（P3 核心）：PostgreSQL 连接池配置、.env.example 迁移示例、Alembic 迁移完整性验证、load_test.py 压测完善（Locust + asyncio 双模式）
  - 属性测试：16 个 Hypothesis 测试覆盖全部 14 条属性（`backend/tests/test_production_readiness_properties.py`）
  - 剩余：0.3 公式计算手动浏览器验证（代码已确认 UniverSheetsCorePreset 未禁用公式，功能正确）

## 关键技术事实（查阅/排查专用）

- Univer 公式引擎：@univerjs/preset-sheets-formula **不存在于 npm**，公式引擎内置在 preset-sheets-core（UniverSheetsFormulaPlugin + UniverSheetsFormulaUIPlugin 自动注册），只需 UniverSheetsCorePreset 未传 workerURL（否则 notExecuteFormula=true 禁用计算）
- ThreeColumnLayout.vue 无 #header/#nav-icons slot（顶部导航硬编码）；新入口需先添加自定义 slot（已加 #nav-review-inbox），再在 DefaultLayout 通过 `<template #nav-review-inbox>` 注入
- eventBus 新增事件：`workpaper:saved`（WorkpaperSavedPayload: projectId/wpId/year?）、`materiality:changed`（MaterialityChangedPayload: projectId/year?）
- 后端 AccountCategory 枚举实际值：asset/liability/equity/revenue/expense（无 income/cost）；前端借贷平衡 liabEquityTotal 过滤时需兼容 `['revenue','income','cost','expense']`
- 后端错报模型：`UnadjustedMisstatement`（表名 unadjusted_misstatements），不是 Misstatement
- GateRule 注册模式：继承 GateRule + `rule_registry.register_all([GateType.submit_review, GateType.sign_off], Rule())`；错报超限规则必须注册到 submit_review（仅 sign_off 不够）
- 账套导入状态端点：`GET /api/projects/{project_id}/ledger-import/jobs/{job_id}`（通过 getImportJob service）；作业状态枚举 completed/failed/timed_out/canceled（轮询四个都要判断）
- apiProxy：api.get/post 返回 unwrapped data；validateStatus=s<600 放行 4xx/5xx 时返回 FastAPI `{detail: {...}}`；409 冲突判断 `data?.detail?.error_code === 'VERSION_CONFLICT'`
- apiProxy 不导出 http 原始客户端；blob 下载需 `import http from '@/utils/http'` 直接用 axios（已用于 onExportPdf）
- PDF 导出依赖 LibreOffice headless（libreoffice/soffice which 检测 + subprocess --headless --convert-to pdf --outdir），超时 60s；Windows 需装 LibreOffice，Docker 镜像需打包 libreoffice-core
- Worker 拆分架构：每模块导出 `async def run(stop_event: asyncio.Event)`，用 `asyncio.wait_for(stop_event.wait(), timeout=interval)` 实现可中断 sleep；lifespan 中由 `_run_migrations / _register_phase_handlers / _replay_startup_events / _start_workers` 四个私有函数编排
- database.py 按 DATABASE_URL.startswith("postgresql") 分支：PG 生产 pool_size≥20 / max_overflow≥80 / pool_timeout=30 / pool_recycle=1800；SQLite 开发保留 pool_recycle=3600
- DB_POOL_SIZE/DB_MAX_OVERFLOW 默认 10/20（config.py），database.py 用 max() 确保 PG 分支至少 20/80（向下兼容旧 env）
- Schema bootstrap ADR：不走 Alembic 全量 autogenerate，baseline=create_all（`_init_tables.py` 一次建所有表），增量=autogenerate 补丁；MIGRATION_GUIDE.md 记录
- 属性测试策略：backend Python hypothesis 复刻前端 TS 算法（setTimeout 防抖、COMPLETED_STATUSES、resolveUserName、_DIRTY_PATTERNS 等），因前端未装 vitest/fast-check
- load_test.py 双模式：Locust UI（探索式）+ 独立 asyncio/httpx 批量压测（CI/CD，输出 JSON 报告含 TPS/P95/P99/error_rate/bottlenecks/slow_queries，未达标退出码 1）
- useAutoSave composable 保存到 sessionStorage 用于草稿恢复，不适合 Univer 大型 snapshot 后端自动保存；底稿编辑器自动保存需独立 setInterval 调用 onSave
- 项目未安装 @vueuse/core，防抖用原生 setTimeout/clearTimeout 实现
- Project 模型无 audit_type 字段，不可依赖做期中/期末判断
- commonApi.getMyStaffId 直接返回 `string | null`；staffApi.getMyStaffId 返回对象，两者不同
- router_registry.py 路由前缀规范：路由器内部只声明业务路径（如 /gate），注册时统一加 prefix="/api"；例外：dashboard.py 内部带 /api/dashboard 注册时不加、/wopi 不加、/api/version 直接在 main.py
- 预存 backend 测试失败（与本 spec 无关，不要误判为回归）：test_adjustments.py 23 个测试因 SQLite 不支持 pg_advisory_xact_lock 失败；test_misstatements.py 2 个测试因 UnadjustedMisstatement 缺 soft_delete mixin；test_e2e_chain* 同样 pg_advisory_xact_lock 问题；test_audit_report.py 12 个 API endpoint 测试 401 Unauthorized（test client 未配置 auth override，与 JSON 种子修复无关）
- NotificationCenter.vue 已挂载到 DefaultLayout.vue 顶部导航（R6 Task 7），通知铃铛可见；导航顺序：复核收件箱→🔔通知→🛡️独立复核→📊EQCR指标
- ReviewWorkstation.vue 已确认删除（R6 Task 8 验证 fileSearch 零命中）
- backend/app/routers/pbc.py 和 confirmations.py 返回 `{"status": "developing", "items": [], "note": "..."}`，maturity 标记为 developing（R6 Task 8）
- 归档编排已统一：ArchiveOrchestrator（R1 落地）+ 幂等逻辑（R6 Task 16，24h 内 succeeded/running 不重复打包）；前端 apiPaths.ts archive 对象已重写指向 /api/projects/${pid}/archive/...；旧端点 A/B/C 加 `Deprecation: version="R6"` 头
- 三套就绪检查已统一：gate_engine 为唯一真源，SignReadinessService + ArchiveReadinessService 均调 readiness_facade（R1 落地），R6 补充 KamConfirmedRule + IndependenceConfirmedRule 注册到 sign_off + export_package
- SignatureRecord.signature_level 控制流已解耦（R6 Task 6）：CA 验证走 required_role='signing_partner' + required_order=3，字段保留兼容但禁止用于控制流；scripts/check_signature_level_usage.py 静态检查纳入 CI
- qc_rule_definitions 表已建（R6 Task 9），22 条 seed 规则（QC-01~14 + QC-19~26），QCEngine.check 启动前按 enabled 过滤；前端 /qc/rules 只读页面已就绪
- WorkpaperEditor.vue 工具栏仅保存/同步公式/版本/下载/PDF/上传，无 AI 侧栏、无程序要求侧栏、无右键序时账穿透、无对比上年按钮
- EQCR 角色与工作台已落地（R5 Tasks 1-7）：ProjectAssignment.role='eqcr' 已启用、GateType.eqcr_approval 已注册、ReportStatus.eqcr_approved 已扩展、EqcrService + /api/eqcr/* 路由 + 前端 EqcrWorkbench/EqcrProjectView 页面 + 5 Tab 组件 + 关联方 CRUD 全部就绪
- ThreeColumnLayout.vue 新增 #nav-eqcr slot（R5 Task 4），DefaultLayout 注入"🛡️ 独立复核"导航按钮（partner/admin 可见）
- Communication/ClientCommunication 模型不存在（grep 零命中），ProjectProgressBoard 沟通记录前端组件存在但后端未独立建模，可能塞在 JSON 字段或散落表里
- WorkingPaper 无 due_date 字段，wp_progress_service overdue_days 用 created_at 估算"已创建天数"，语义弱
- ledger/penetrate 端点参数为 account_code + drill_level + date，不支持按 amount 容差匹配；按金额穿透需新增端点
- assignment_service.ROLE_MAP 和 role_context_service._ROLE_PRIORITY 两个字典是角色体系单一真源，新增 role='eqcr' 已同时更新；_ROLE_PRIORITY 当前 partner(5)/eqcr(5)/qc(4)/manager(3)/auditor(2)/readonly(1)
- GoingConcernEvaluation 模型已存在（collaboration_models.py），Round 5 EQCR 持续经营 Tab 可直接复用，不要重复建模
- 归档包设计决策：采用"插件化章节"模式（00/01/02/.../99 顺序），各 Round 各自插入章节，Round 1 需求 6 只预留机制
- EQCR 路由架构（f333788 重构后）：`backend/app/routers/eqcr/` 包含 12 子模块（workbench/opinions/notes/related_parties/shadow_compute/gate/memo/time_tracking/independence/prior_year/metrics/constants），`__init__.py` 聚合导出 router + 所有端点函数（向后兼容测试）
- EQCR 服务拆分（50b034f）：`eqcr_workbench_service.py`（EqcrWorkbenchService: list_my_projects/get_project_overview）+ `eqcr_domain_service.py`（EqcrDomainService: 5 域聚合 + opinion CRUD）+ `eqcr_service.py` 薄组合类（MRO 继承向后兼容）
- EQCR 枚举端点：`GET /api/eqcr/constants` 返回 domains/verdicts/progress_states，前端启动时拉取避免硬编码漂移
- R5 Alembic 迁移链：round5_eqcr_20260505 → round5_independence_20260506 → round5_eqcr_check_constraints_20260506（PG CHECK domain+verdict）
- R6 Alembic 迁移链：round6_qc_rule_definitions_20260507 → round6_review_binding_20260507（conversation_id 列）
- R6 CI 骨架：`.github/workflows/ci.yml`（4 job: backend-tests/backend-lint/seed-validate/frontend-build）+ `.pre-commit-config.yaml`（check-json + json-template-lint）
- R6 seed schema 校验：`scripts/validate_seed_files.py` + `backend/data/_seed_schemas.py`（6 个 seed 文件 Pydantic v2 校验）
- R6 死链检查：`scripts/dead-link-check.js`（Node 脚本，扫描 apiPaths.ts 231 端点 vs router_registry 130 前缀，纳入 CI seed-validate job）
- R6 gate_rules_round6.py：KamConfirmedRule（R6-KAM）+ IndependenceConfirmedRule（R6-INDEPENDENCE）+ SubsequentEventsReviewedRule（R7-SUBSEQUENT）+ GoingConcernEvaluatedRule（R7-GOING-CONCERN）+ MgmtRepresentationRule（R7-MGMT-REP），模块导入时自动注册到 sign_off + export_package
- R6 复核批注边界：ReviewRecord.conversation_id FK → review_conversations.id；close_conversation 前校验未解决记录；IssueTicket 去重（source='review_comment' + source_ref_id）
- ThreeColumnLayout.vue 新增 #nav-notifications slot（R6 Task 7）+ developing maturity badge 样式 .gt-maturity-dev（蓝灰 #909399）
- router_registry.py §15 注册 qc_rules_router（内部 prefix="/api/qc/rules"）；前端路由 /qc/rules → QcRuleList.vue（权限 qc/admin/partner）
- conftest.py test_all_models_registered：AST 遍历 backend/app/models/*.py 断言所有 __tablename__ 已注册到 Base.metadata.tables
- R3 Sprint 4 AI 溯源：gate_rules_ai_content.py（AIContentMustBeConfirmedRule rule_code="R3-AI-UNCONFIRMED" 注册到 sign_off）+ wp_ai_confirm.py 端点（PATCH /ai-confirm 确认/拒绝/修订）+ ai_contribution_watermark.py 工具函数 + audit_log_rules_seed.json（AL-01~05）
- R3 前端 QC 6 页面已就绪：QcRuleList（R6 创建）+ QcRuleEditor + QcInspectionWorkbench（含日志合规 Tab）+ ClientQualityTrend + QcCaseLibrary + QcAnnualReports，路由均在 /qc/* 下注册
- 归档章节完整性：00 封面 ✓ / 01 签字流水 ✓ / 02 EQCR 备忘录 ✓ / 03 质控抽查报告 ✓ / 04 独立性声明 ✓ / 99 审计日志 ✓（全部有真实 generator）
- Alembic 迁移链（14 个 round* 文件）：round1_review_closure → round1_long_term_compliance → round2_budget_handover → round2_batch3_arch_fixes → round3_qc_governance → round5_eqcr_20260506 → round4_editing_lock → round4_ocr_fields_cache（分支终点）；主链 round5_eqcr_20260505 → round5_independence → round5_eqcr_check_constraints → round6_qc_rule_definitions → round6_review_binding → round7_section_progress_gin
- jsonpath-ng 已写入 requirements.txt，qc_rule_executor.py 的 jsonpath 分支已实装（execute_jsonpath_rule 函数）
- qc_annual_report_service.py 导入修正：`build_ai_contribution_statement` 来自 `ai_contribution_watermark.generate_short_statement`（非 pdf_export_engine）
- router_registry.py §17 注册 4 个 QC router（qc_inspections/qc_ratings/qc_cases/qc_annual_reports），内部已含完整 prefix 不加额外前缀
- IssueTicket Q 整改单 SLA：Q_SLA_RESPONSE_HOURS=48 / Q_SLA_COMPLETE_HOURS=168，逾期走 _handle_q_sla_timeout 通知签字合伙人
- datetime.utcnow() 已全局清理（81 文件），统一 `datetime.now(timezone.utc)`；后续新代码禁止使用 utcnow()
- 归档包章节号分配：00 项目封面 / 01 签字流水（R1）/ 02 EQCR 备忘录（R5，已注册）/ 03 质控抽查报告（R3）/ 04 独立性声明（R1）/ 10 底稿/ / 20 报表/ / 30 附注/ / 40 附件/ / 99 审计日志
- 审计意见锁定架构决策：不新增 opinion_locked_at 平行字段，改为扩展 ReportStatus 状态机 draft→review→eqcr_approved→final（R5 需求 6 + README 跨轮约束第 3 条）
- 枚举扩展硬约定：IssueTicket.source 在 R1 一次性预留 11 个值（L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/pbc/confirmation/qc_inspection），ProjectAssignment.role 预留 eqcr，避免多轮迁移
- 权限矩阵四点同步约定：新增 role/动作需同时更新 assignment_service.ROLE_MAP + role_context_service._ROLE_PRIORITY + 前端 ROLE_MAP + composables/usePermission.ROLE_PERMISSIONS
- 焦点时长隐私决策：R4 需求 10 焦点追踪只写 localStorage（按周归档键 `focus_tracker_YYYY-MM-DD`），不落库不发后端，消除监控隐患
- R4 编辑软锁：`workpaper_editing_locks` 表，有效锁 = `released_at IS NULL AND heartbeat_at > now - 5min`，惰性清理（acquire 时过期锁设 released_at=now），前端 heartbeat 每 2 分钟，beforeUnload 释放
- R4 AI 脱敏：`export_mask_service.mask_context(cell_context)` 在 LLM 调用前替换金额/客户名/身份证为 `[amount_N]/[client_N]/[id_number_N]` 占位符，映射表仅当前会话有效不回填；脱敏阈值 >= 100000（非 10000）；人名匹配需"联系人：/客户："等前缀标记，公司名匹配后缀"公司/集团/有限/科技"等
- R4 预填充 provenance：`parsed_data.cell_provenance` JSONB，supersede 策略（重填覆盖旧值，`_prev` 保留最多 1 次历史），source 类型 trial_balance/prior_year/formula/ledger/manual/ocr；实现位于 `prefill_engine.py` 末尾四个函数
- R4 按金额穿透：`backend/app/routers/penetrate_by_amount.py`（本次新建），prefix="/api/projects/{project_id}/ledger"，MAX_RESULTS=200 截断
- R4 router 注册：router_registry.py §13 "审计助理(R4)" tag，6 个 router 内部已含完整 /api prefix 不加额外前缀
- R4 Alembic 迁移 2 个：`round4_editing_lock_20260506`（workpaper_editing_locks 表）+ `round4_ocr_fields_cache_20260506`（attachments.ocr_fields_cache JSONB 列）
- 跨轮 SLA 统一按自然日计，不引入节假日日历服务，跨长假由人工 override（README 跨轮约束第 5 条）
- ClientCommunicationService 已存在于 `pm_service.py:481`，沟通记录存 `Project.wizard_state.communications` JSONB，`commitments` 当前是字符串；R2 需求 5 无需"调研"，直接升级为结构化数组
- ReviewInboxService.get_inbox(user_id, project_id=None) 已支持全局+单项目双模式（`pm_service.py:26`），R1 需求 1 不新增后端端点
- 复核批注并存两套：ReviewRecord（单行绑定 wp_id+cell_reference）与 review_conversations（跨对象多轮）；R1 需求 2 选定 ReviewRecord 为工单转换真源，conversations 只用于后续讨论
- AuditEvidence 模型不存在（grep 零命中），附件与底稿关联统一用 attachment_service + workpaper_attachment_link
- AJE 被拒→错报联动：后端 misstatement_service.create_from_rejected_aje 已实现，但 Adjustments.vue 前端入口缺失；R1 需求 3 新增 UnconvertedRejectedAJERule 到 sign_off gate
- event_handlers.py:173 订阅 WORKPAPER_SAVED 级联更新试算表/报表/附注，但无补偿机制；R1 需求 3 新增 EventCascadeHealthRule gate 规则
- ExportIntegrityService 语义：导出时 persist_hash_checks 记哈希（`export_integrity_service.py:53`），下载不重算，可疑时显式 verify_package；R1 需求 6 措辞对齐
- 签字状态机联动决策：最高级签字完成后由 SignService.sign 内部同事务自动切 AuditReport.status 到 final（R1 需求 4），避免"签完字但报告停在 review"困惑
- 归档断点续传：archive_jobs 表记 last_succeeded_section，重试从下一章节开始（R1 需求 5）
- R3 规则 DSL 本轮范围收窄：只实现 expression_type='python'+'jsonpath'，SQL/regex 枚举保留但执行器 NotImplementedError，留 Round 6+
- R5 EQCR 独立性边界：不直接对外联络客户（维持项目组作为对外单一入口），只做内部独立笔记，可选择分享给项目组
- 签字状态机联动分两情形：无 EQCR 项目 order=3 partner 签完直接切 review→final；启用 EQCR 则 order=3 不切、order=4 EQCR 签完切 review→eqcr_approved、order=5 归档签字完切 eqcr_approved→final
- notification_types.py 由 R1 tasks 19 唯一创建，R2+ 只向其追加常量不重复新建；前端 notificationTypes.ts 同理
- AuditReportEditor.vue 状态处理已完善：isLocked computed 统一判断 eqcr_approved/final，编辑器头部四态标签（draft→可编辑/review→⚠审阅中/eqcr_approved→🔒EQCR已锁/final→🔒已定稿），opinion_type 下拉在锁定态 disabled
- EqcrProjectView.vue 现有 10 个 Tab：materiality/estimate/related_party/going_concern/opinion_type/shadow_compute/review_notes/prior_year/memo/component_auditor（最后一个仅 consolidated 项目显示）
- EQCR 备忘录存储：Project.wizard_state.eqcr_memo JSONB（sections dict + status draft/finalized），不独立建表
- EQCR 工时追踪：WorkHour.status='tracking' 表示计时中，stop 时计算时长并切回 draft
- 年度独立性声明：独立表 `annual_independence_declarations`（R1 通用表落地前的过渡方案），唯一约束 `(declarant_id, declaration_year)`；问题集 backend/data/independence_questions_annual.json（32 题）是唯一真源，Python 侧不再维护副本
- EqcrMetrics.vue 路由 /eqcr/metrics 已注册，后端加 admin/partner 角色守卫；DefaultLayout #nav-eqcr 插槽内挂两个按钮（独立复核工作台 + EQCR 指标）
- apiProxy 实际路径 `@/services/apiProxy`（不是 `@/utils/apiProxy`）；默认导出和命名导出 `{ api }` 都可用；memory 此前记录有误已更正
- `stores/auth.ts` login 方法：后端返回 `{code, message, data: {access_token, refresh_token, user}}`，authHttp（原始 axios）不经过 apiProxy 解包，需 `data.data ?? data` 取 payload
- `apiPaths.ts` 新增 `signatures`（/api/signatures/*）和 `rotation`（/api/rotation/*）导出（R1 需求 4/11 前端 service 依赖）
- 新 PG 库初始化流程：`python scripts/_init_tables.py`（需先 `pip install psycopg2-binary`）→ 手动建 admin 用户（INSERT 需含 email 字段 NOT NULL）
- `backend/migrations/V003__example_add_comment.sql` 已修复 `DO $` → `DO $$`（PG dollar-quoting 语法）
- User 模型无 metadata_ JSONB 字段；需要"用户级元数据"时应建独立表（如 annual_independence_declarations），不污染 User 表
- StaffMember 用 `employee_no`（不是 `employee_id`）作为工号字段
- WorkHour.status 是 String(20) 非 enum，可自由塞业务值（R5 用 'tracking' 表示计时中）
- ProjectStatus 枚举值：created/planning/execution/completion/reporting/archived（没有 in_progress，测试 fixture 常用 execution）
- CompetenceRating 枚举实际值：reliable/additional_procedures_needed/unreliable（设计 doc 中的"A/B/C/D"是业务语义而非代码枚举，前端标签映射需对齐实际枚举）
- ReportStatus 枚举：draft/review/eqcr_approved/final；VALID_TRANSITIONS 矩阵定义在 `test_eqcr_state_machine_properties.py`（draft→review；review→{eqcr_approved,draft}；eqcr_approved→{review,final}；final→∅）
- hypothesis 包已写入 requirements.txt（R6 Task 2），ruff@0.11.12 同步写入；CI 可正常运行属性测试
- SQLAlchemy 异步模式下 `db.add(obj)` 不立即生成 PK，引用 obj.id 前必须 `await db.flush()`；gate_engine 此前因缺 flush 导致 trace_events.object_id NOT NULL 违反
- SQLAlchemy `session.refresh(obj)` 会从 DB 重读覆盖内存中的未 flush 修改；业务代码变更字段后希望 refresh 可见时必须先 flush
- python-docx 已装可用（phase13 note_word_exporter.py 同款），Word 生成遵循 `build_*_docx_bytes(...)→bytes` 纯函数模式便于单测；PDF 转换走 LibreOffice headless `soffice --headless --convert-to pdf`（memory 之前关于 LibreOffice 路径检测记录正确）
- 客户名归一化 `app/services/client_lookup.normalize_client_name` + `client_names_match`：去空白、全角→半角、去"有限公司/股份/集团/Co.,Ltd/Inc." 后缀，归一后精确相等。R3 正式落地后迁入 R3 模块
- 前端路由 beforeEach 新增 `meta.requiresAnnualDeclaration` 守卫：访问 EQCR 相关路由前调 `/api/eqcr/independence/annual/check`，未声明则强制跳 EqcrWorkbench 弹对话框；同时支持 `meta.roles` 角色粗筛

## 活跃待办

### 最高优先级
- 合并 feature/global-component-library 到 master（用户手动操作）
- 0.3 公式计算浏览器手动验证（启动前端输入 `=SUM(A1:A3)` 看结果）
- 用真实审计项目进行用户验收测试（UAT）
- 生产环境部署准备（Docker 镜像打包 LibreOffice、PG 环境变量、数据库初始化）
- 打磨路线图已由"4 轮主题"改为"5 角色轮转"：Round 1 合伙人 / Round 2 PM / Round 3 质控 / Round 4 助理 / Round 5 EQCR，5 轮三件套（requirements+design+tasks）全部起草并完成一致性校对
- 实施顺序：R1 → R2 → R3+R4（并行，相互独立）→ R5 → R6，依据 README v2.2 "跨轮依赖矩阵"
- **Round 4 已修复并验证通过（2026-05-06）**：修复 4+2 个真实缺口后 128 个测试全绿，app 870 路由正常启动。修复内容：(a) `get_prior_year_workpaper` 函数新增到 continuous_audit_service（通过 WpIndex join 获取 wp_code）；(b) prefill provenance 四函数追加到 prefill_engine.py；(c) 6 个 R4 router 注册到 router_registry.py §13；(d) 3 个 Sprint 集成测试创建；(e) ExportMaskService 新增 mask_context/mask_text/_is_sensitive_amount；(f) Attachment 模型新增 ocr_fields_cache；(g) wp_chat_service 脱敏集成
- **Round 6 实施完成（2026-05-07）**：18 任务 / 2 Sprint 全部完成，主题"跨角色系统级优化"。Sprint 1（CI骨架+签字解耦+铃铛挂载+死代码清理）+ Sprint 2（QC规则表+复核批注边界+归档幂等+GateRule补充+死链检查）
- **R1-R6 复盘断点清单（2026-05-07 发现，P0-P3 已修复）**：
  - ✅ R3 前端 5 页面补完（QcRuleEditor/QcInspectionWorkbench/ClientQualityTrend/QcCaseLibrary/QcAnnualReports）+ 路由注册 + 编译通过
  - ✅ R3 Sprint 4 AI 溯源 5 任务实装（gate_rules_ai_content + AiContentConfirmDialog + wp_ai_confirm 端点 + ai_contribution_watermark + audit_log_rules_seed + 日志合规 Tab）
  - ✅ 归档章节 03（质控抽查报告）+ 04（独立性声明）真实 generator 落地
  - ✅ Archive PDF SHA-256 水印修正（占位符改为引用 manifest_hash）
  - ✅ section_progress GIN 索引迁移（round7_section_progress_gin_20260507）
  - ✅ 就绪检查 extra_findings 完全消灭（subsequent_events/going_concern/mgmt_representation 升级为 GateRule R7-*）
  - ✅ jsonpath-ng 写入 requirements.txt，jsonpath 执行器已确认实装
  - ✅ Alembic 迁移链核验通过（14 个 round* 迁移，无分叉冲突）
  - 🔲 R3 tasks.md 状态回填（后端已就绪+前端已补，需批量标 [x]）
  - 🔲 R1 UAT-1~6 浏览器手动验证（需真人执行）
  - 🔲 Round2-Task-A 测试盲点 11 项（并发/Worker/PBT）需真实 PG 环境
  - 🔲 性能压测真实环境跑（6000 并发验收）
  - 🔲 ReviewWorkbench 中栏只读 Editor（R1 已知妥协，低优先级）
- **R3 深度复盘（2026-05-07）新发现的断点 — 已全部修复**：
  - ✅ 4 个 QC router 注册到 router_registry.py §17（qc_inspections/qc_ratings/qc_cases/qc_annual_reports）
  - ✅ sla_worker Q 整改单 SLA 分支（_handle_q_sla_timeout：标记 sla_breached + 通知签字合伙人）
  - ✅ QCDashboard.vue 新增"项目评级"Tab（A/B/C/D badge）+ "复核人画像"Tab（5 维度指标表）
  - ✅ IssueTicketList source='Q' 特殊 UI（🛡️图标 + .q-source-row 红左边框）
  - ✅ QcRuleEditor 强制试运行（hasRunDryRun flag，保存按钮 disabled 直到试运行完成）
  - ✅ 年报 Word 模板真实渲染（python-docx 5 章节填充，不可用时降级文本）
  - ✅ QcInspectionWorkbench "生成质控报告"按钮（选中批次后下载 Word）
- Round 1 实施进度：Tasks 1-4 已完成（数据模型迁移 73204cf + Tasks 2-4 评审闭环后端+前端合并 5c5ac56），按 tasks.md 顺序推进剩余任务
- Round 5 实施进度：**全部完成 + 复盘 P0-P2 修复**，122 个 EQCR 测试全通过；R5 关闭

### 中期功能完善
- 性能测试（真实 PG + 大数据量环境运行 load_test.py，验证 6000 并发）
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度 85%，业务完成度 60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能
- `GtStatusTag.STATUS_MAP_TO_DICT_KEY` 是硬编码映射表，新增 StatusMap 时需手动维护 [P3]
- PBC 清单真实实现（R7+ 计划，后端当前 stub）[P2]
- 函证管理真实实现（R7+ 计划，后端当前 stub）[P2]
- 统一 commonApi.ts / collaborationApi.ts / aiApi.ts 硬编码路径到 apiPaths 常量（257 处，大工作量）[P3]

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）

## 跨轮复盘发现（R5 完成后）

- 跨轮复盘发现 3 个真实代码 bug + 2 个环境/配置问题：
  (A) `backend/data/audit_report_templates_seed.json` 71 处 CJK 字符串内用直双引号 `"XX"` 导致 JSON 解析失败，改用中文方头括号「XX」（全角 U+300C/U+300D）恢复；直接影响 `POST /api/audit-report/templates/load-seed` 端点，任何审计报告生成都走不通
  (B) `qc_engine.py` SamplingCompletenessRule (QC-12) 引用 `SamplingConfig.working_paper_id`，但该列不存在——SamplingConfig 只有 `project_id`，改为按 project 过滤
  (C) `qc_engine.py` PreparationDateRule (QC-14) `datetime.utcnow() - aware_datetime` 类型混用抛 TypeError，统一 `datetime.now(timezone.utc)` 解决
  (D) `backend/tests/conftest.py` 漏导入 phase10/12/14/15/16/archive/dataset/knowledge/note_trim/procedure/shared_config/template_library/eqcr/related_party/independence 等 15+ 个 model 包，导致 SQLite create_all 缺表（如 cell_annotations），多处 service 调用时抛 "no such table"
  (E) backend 无 hypothesis 依赖，导致 test_phase0_property/test_phase1a_property/test_remaining_property/test_production_readiness_properties 共 101 个属性测试从未执行（memory 之前的"16 Hypothesis 测试"说法实际是零运行）；安装 hypothesis@6.152.4 后全部通过
- **跨轮复盘方法沉淀**：pytest --collect-only 先查 collection error；按 file glob 分组跑避免超时；grep `db.add(...).id` 找 flush 缺失；grep `datetime.utcnow()` 找 tz 混用；readCode 所有被标 [x] 的 Sprint 核心表/字段；脆性根因多是"模型已建但测试 conftest 未注册"或"字段假设未 grep 核对"
- 跨轮复盘后测试总数：EQCR 122 + Phase13/14 93 + phase property 101 = 316 个已验证通过（只包含核心受影响文件，未跑全量）
- test_audit_report.py 剩余 12 个失败是 401 Unauthorized（test client 未配置 auth override，代码本身逻辑正确）；test_wopi_working_paper_qc_review.py QC 规则失败是测试假设"所有 stub 规则返回空"已过时（规则已实装），属测试设计漂移不是代码 bug
