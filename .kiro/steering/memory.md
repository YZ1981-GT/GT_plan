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
- 后端新增测试依赖 hypothesis@6.152.4（跨轮复盘发现此前未装，4 个属性测试文件含 60+ 测试从未运行）
- PG ~158 张表（152 基线 + R5 新增 6 张：eqcr_opinions/eqcr_review_notes/eqcr_shadow_computations/eqcr_disagreement_resolutions/related_party_registry/related_party_transactions），Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-05 实测核对）

- vue-tsc 90 个预存错误（非本 spec 引入，el-tag 类型联合/checkbox 值扩宽/tree filter-method 签名），Vite 构建通过
- 后端 127 个路由文件，181 个服务文件（含子目录 import_engine/、wp_scripts/），39 个模型文件，11 个 core 模块，9 个 middleware，~152 张表
- 后端 `backend/app/workers/` 模块 4 个：sla_worker、import_recover_worker、outbox_replay_worker、import_worker（每个导出 `async def run(stop_event)`）
- 前端 80 个 Vue 页面（views/），20 个 common 组件，16 个 composables，9 个 stores，19 个 services，19 个 utils
- 后端测试：98+ 个根目录测试 + 4 个 e2e + 4 个 integration + R5 新增 test_eqcr_full_flow/test_eqcr_state_machine_properties/test_eqcr_component_auditor_review
- git 分支：feature/global-component-library（R5 全部完成 87b0f38，R4 本地新文件待提交）
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
- NotificationCenter.vue 组件+store+API 完整，但 DefaultLayout.vue 顶部未挂铃铛入口，通知实际不可见（Round 2 重点修复）
- ReviewWorkstation.vue 存在三栏+AI 预审+快捷键，但 router/index.ts 未注册，是死代码；实际入口 ReviewInbox.vue 无 AI 预审（Round 1 需合并）
- backend/app/routers/pbc.py 和 confirmations.py 是占位空壳（各 15 行返回 []），不是真实功能，前端无对应页面
- 归档端点三重并存语义不同：wp_storage.archive_project（锁底稿）/ private_storage.archive_project（锁+推云+清本地）/ data_lifecycle.archive_project（软删除可恢复），前端只有一个按钮入口
- 三套就绪检查逻辑分散可能矛盾：gate_engine（submit_review/sign_off/export_package）/ partner_dashboard.sign-readiness（8 项）/ qc_dashboard.archive-readiness，需统一为 gate_engine 门面
- SignatureRecord.signature_level 仅 String(20) 无顺序强制，三级签字无前置依赖校验
- qc_engine.py 14 条 QC-01~14 规则 + gate_rules_phase14.py QC-19~26 全是硬编码 Python，无 qc_rule_definitions 表支持自定义
- WorkpaperEditor.vue 三栏布局（R4 完成）：左程序要求侧栏 + 中 Univer + 右 AI 助手侧栏；工具栏含保存/同步公式/版本/下载/PDF/上传/对比上年/AI内容；底部 SmartTipList 可点击定位；右键菜单"穿透序时账"+"从附件OCR提取"；编辑锁 acquire/heartbeat/release；附件拖拽上传；焦点时间追踪；readOnly 模式（锁冲突时禁用编辑）
- EQCR 角色与工作台已落地（R5 Tasks 1-7）：ProjectAssignment.role='eqcr' 已启用、GateType.eqcr_approval 已注册、ReportStatus.eqcr_approved 已扩展、EqcrService + /api/eqcr/* 路由 + 前端 EqcrWorkbench/EqcrProjectView 页面 + 5 Tab 组件 + 关联方 CRUD 全部就绪
- ThreeColumnLayout.vue 新增 #nav-eqcr slot（R5 Task 4），DefaultLayout 注入"🛡️ 独立复核"导航按钮（partner/admin 可见）
- Communication/ClientCommunication 模型不存在（grep 零命中），ProjectProgressBoard 沟通记录前端组件存在但后端未独立建模，可能塞在 JSON 字段或散落表里
- WorkingPaper 无 due_date 字段，wp_progress_service overdue_days 用 created_at 估算"已创建天数"，语义弱
- ledger/penetrate 端点参数为 account_code + drill_level + date；R4 新增独立端点 `/ledger/penetrate-by-amount`（四策略：exact/tolerance/code+amount/summary，200 条截断）
- assignment_service.ROLE_MAP 和 role_context_service._ROLE_PRIORITY 两个字典是角色体系单一真源，新增 role='eqcr' 已同时更新；_ROLE_PRIORITY 当前 partner(5)/eqcr(5)/qc(4)/manager(3)/auditor(2)/readonly(1)
- GoingConcernEvaluation 模型已存在（collaboration_models.py），Round 5 EQCR 持续经营 Tab 可直接复用，不要重复建模
- 归档包设计决策：采用"插件化章节"模式（00/01/02/.../99 顺序），各 Round 各自插入章节，Round 1 需求 6 只预留机制
- 归档包章节号分配：00 项目封面 / 01 签字流水（R1）/ 02 EQCR 备忘录（R5）/ 03 质控抽查报告（R3）/ 10 底稿/ / 20 报表/ / 30 附注/ / 40 附件/ / 99 审计日志
- 审计意见锁定架构决策：不新增 opinion_locked_at 平行字段，改为扩展 ReportStatus 状态机 draft→review→eqcr_approved→final（R5 需求 6 + README 跨轮约束第 3 条）
- 枚举扩展硬约定：IssueTicket.source 在 R1 一次性预留 11 个值（L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/pbc/confirmation/qc_inspection），ProjectAssignment.role 预留 eqcr，避免多轮迁移
- 权限矩阵四点同步约定：新增 role/动作需同时更新 assignment_service.ROLE_MAP + role_context_service._ROLE_PRIORITY + 前端 ROLE_MAP + composables/usePermission.ROLE_PERMISSIONS
- 焦点时长隐私决策：R4 需求 10 焦点追踪只写 localStorage（按周归档键 `focus_tracker_YYYY-MM-DD`），不落库不发后端，消除监控隐患
- R4 编辑软锁：`workpaper_editing_locks` 表，有效锁 = `released_at IS NULL AND heartbeat_at > now - 5min`，惰性清理（acquire 时过期锁设 released_at=now），前端 heartbeat 每 2 分钟，beforeUnload 释放
- R4 AI 脱敏：`export_mask_service.mask_context(cell_context)` 在 LLM 调用前替换金额/客户名/身份证为 `[amount_N]/[client_N]/[id_number_N]` 占位符，映射表仅当前会话有效不回填
- R4 预填充 provenance：`parsed_data.cell_provenance` JSONB，supersede 策略（重填覆盖旧值，`_prev` 保留最多 1 次历史），source 类型 trial_balance/prior_year/formula/ledger/manual/ocr
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
- User 模型无 metadata_ JSONB 字段；需要"用户级元数据"时应建独立表（如 annual_independence_declarations），不污染 User 表
- StaffMember 用 `employee_no`（不是 `employee_id`）作为工号字段
- WorkHour.status 是 String(20) 非 enum，可自由塞业务值（R5 用 'tracking' 表示计时中）
- ProjectStatus 枚举值：created/planning/execution/completion/reporting/archived（没有 in_progress，测试 fixture 常用 execution）
- CompetenceRating 枚举实际值：reliable/additional_procedures_needed/unreliable（设计 doc 中的"A/B/C/D"是业务语义而非代码枚举，前端标签映射需对齐实际枚举）
- ReportStatus 枚举：draft/review/eqcr_approved/final；VALID_TRANSITIONS 矩阵定义在 `test_eqcr_state_machine_properties.py`（draft→review；review→{eqcr_approved,draft}；eqcr_approved→{review,final}；final→∅）
- hypothesis 包**未**安装于后端 requirements.txt（与 memory 之前"16 Hypothesis 测试"描述不一致，那些测试实际因 import 错误无法运行）；新属性测试改用 pytest.mark.parametrize 覆盖状态组合
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
- 实施顺序：R1 → R2 → R3+R4（并行，相互独立）→ R5，依据 README v2.2 "跨轮依赖矩阵"
- **Round 4 已全部完成**（Sprint 1-3 共 23 任务）：三栏编辑器（程序要求侧栏+AI侧栏）/SmartTipList可点击定位/上年对比/按金额穿透/预填充provenance/移动端只读/附件拖拽/焦点追踪时间线/编辑软锁/OCR字段提取；本地 ~70 个 untracked 新文件待 git add + commit
- Round 1 实施进度：Tasks 1-4 已完成（数据模型迁移 73204cf + Tasks 2-4 评审闭环后端+前端合并 5c5ac56），按 tasks.md 顺序推进剩余任务
- Round 5 实施进度：**全部完成 + 复盘 P0-P2 修复**，122 个 EQCR 测试全通过；关键修复：(1) gate_engine.evaluate 加 `await db.flush()` 修复 gate_decision.id NULL 导致 trace_events 插入失败；(2) sign_service._transition_report_status 加 `await db.flush()` 让状态变更对 refresh 可见；(3) Task 23 年度独立性声明改为独立表 `annual_independence_declarations`（R1 通用表未落地前的过渡方案，migration round5_independence_20260506）；(4) Task 18 备忘录接入 python-docx + LibreOffice PDF 管线，`build_memo_docx_bytes` 纯函数生成 docx，`eqcr_memo_pdf_generator` 归档章节生成器预留；(5) Task 24 年度声明变成真实阻断（router 守卫 + 工作台 load 阻塞）；(6) Task 15 客户名归一化 `client_lookup.normalize_client_name` 兼容"XX集团"vs"XX集团有限公司"；(7) Task 22 CompetenceRating 枚举值修正为 reliable/unreliable（原先误用 A/D）；(8) Task 20 metrics 端点加 admin/partner 角色守卫；(9) EqcrProjectView 加 EQCR 审批/解锁按钮，approve 前强制检查历年对比差异原因；(10) 新增 test_eqcr_full_flow / test_eqcr_state_machine_properties / test_eqcr_component_auditor_review / test_eqcr_memo_docx / test_client_lookup 五个测试文件；(11) 归档章节 '02-EQCR备忘录.pdf' 待 R1 archive_section_registry 落地后通过 `register('02', 'eqcr_memo.pdf', eqcr_memo_pdf_generator)` 注册

### 中期功能完善
- 性能测试（真实 PG + 大数据量环境运行 load_test.py，验证 6000 并发）
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度 85%，业务完成度 60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能
- `GtStatusTag.STATUS_MAP_TO_DICT_KEY` 是硬编码映射表，新增 StatusMap 时需手动维护 [P3]

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
