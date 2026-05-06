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
- 任务执行后必须自行 grep 核查实际落地，不信子代理报告；发现未落地/部分落地需补全
- 复盘迭代模式：修完→测试覆盖→提交推送→grep 核查→再复盘，找到新建议回到修复，零新建议才真正收尾
- 批量修复时不要每小步都停下来问 hook/确认，一气呵成完成整批再统一更新记忆

## Spec 工作流规范（production-readiness 复盘沉淀）

- design.md 起草必须做"代码锚定"：每个修改点列文件+行号/函数名，npm 包要 `npm view` 验证存在，字段/枚举/端点路径 grep 核对，避免事后大量校正备忘
- tasks.md 只放可被自动化工具推进的编码任务；手动浏览器验证（如"输入公式看结果"）应放 spec 末尾"UAT 验收清单"，不占 taskStatus 工作流
- Sprint 粒度按"验证边界"切分：每个 Sprint ≤10 个任务，强制回归测试+UAT 才进下一 Sprint（反例：production-readiness Sprint 2 塞 20+ 小改）
- 任务描述中引用的依赖包、类名、API 路径，变化后要回填更新（如 0.1/0.2 的 `@univerjs/preset-sheets-formula` 实际不存在）

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- 前端依赖：mitt@3.0.1、nprogress@0.2.0、unplugin-auto-import@21.0.0 + unplugin-vue-components@32.0.0、@univerjs/preset-sheets-core@0.21.1（公式引擎内置）
- PG ~152 张表（实测 Base.metadata，≥ 需求 9.2 要求的 144），Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-06）

- vue-tsc 90 个预存错误（非本 spec 引入，el-tag 类型联合/checkbox 值扩宽/tree filter-method 签名），Vite 构建通过
- 后端 ~126 个路由文件（R2 新增 manager_dashboard/batch_assign_enhanced/workpaper_remind/batch_brief/workhour_approve/cost_overview），~178 个服务文件，43 个模型文件，~155 张表（新增 handover_records/system_settings）
- 后端新增 `backend/app/workers/` 模块：sla_worker、import_recover_worker、outbox_replay_worker、budget_alert_worker（每个导出 `async def run(stop_event)`）
- 前端 ~78 页面（R2 新增 ManagerDashboard/WorkHoursApproval），22 个 common 组件（R2 新增 BatchAssignDialog/StaffSelectDialog/CommunicationCommitmentsEditor/CrossProjectBriefExporter），16 个 composables，9 个 stores，19 个 services，19 个 utils
- git 分支：feature/global-component-library（已推送至 02e3731，待合并 master）
- 最新提交 02e3731：Round 1 复盘 14 项修复（bug fix + 改进 + 文档）
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
- 预存 backend 测试失败（与本 spec 无关，不要误判为回归）：test_adjustments.py 23 个测试因 SQLite 不支持 pg_advisory_xact_lock 失败；test_misstatements.py 2 个测试因 UnadjustedMisstatement 缺 soft_delete mixin；test_e2e_chain* 同样 pg_advisory_xact_lock 问题
- 时间戳处理：DB 存 naive TIMESTAMP（SQLite + PG 默认 TIMESTAMP WITHOUT TIME ZONE），service 比较时用 `datetime.now(timezone.utc).replace(tzinfo=None)` 而非 `datetime.utcnow()`（3.12 已废弃）；避免 `datetime.now(tz=None)` 反模式混用
- NotificationCenter.vue 组件+store+API 完整，DefaultLayout.vue 顶部已挂铃铛入口（Round 2 Task 1 完成），通知可见
- ThreeColumnLayout.vue 已有 #nav-notifications slot（Round 2 新增），DefaultLayout 通过 `<template #nav-notifications>` 注入 NotificationCenter
- ReviewWorkstation.vue 存在三栏+AI 预审+快捷键，但 router/index.ts 未注册，是死代码；实际入口 ReviewInbox.vue 无 AI 预审（Round 1 需合并）
- backend/app/routers/pbc.py 和 confirmations.py 是占位空壳（各 15 行返回 []），不是真实功能，前端无对应页面
- 归档端点三重并存语义不同：wp_storage.archive_project（锁底稿）/ private_storage.archive_project（锁+推云+清本地）/ data_lifecycle.archive_project（软删除可恢复），前端只有一个按钮入口
- 三套就绪检查逻辑分散可能矛盾：gate_engine（submit_review/sign_off/export_package）/ partner_dashboard.sign-readiness（8 项）/ qc_dashboard.archive-readiness，需统一为 gate_engine 门面
- SignatureRecord.signature_level 仅 String(20) 无顺序强制，三级签字无前置依赖校验
- qc_engine.py 14 条 QC-01~14 规则 + gate_rules_phase14.py QC-19~26 全是硬编码 Python，无 qc_rule_definitions 表支持自定义
- WorkpaperEditor.vue 工具栏仅保存/同步公式/版本/下载/PDF/上传，无 AI 侧栏、无程序要求侧栏、无右键序时账穿透、无对比上年按钮
- 系统无 EQCR（独立复核合伙人）专属角色与工作台，ProjectAssignment.role 缺 eqcr 枚举，gate_engine 缺 eqcr_approval 阶段
- Communication/ClientCommunication 独立模型不存在，沟通记录存 Project.wizard_state.communications JSONB（R2 已确认并升级 commitments 为结构化数组）
- WorkingPaper 无 due_date 字段，wp_progress_service overdue_days 用 created_at 估算"已创建天数"，语义弱
- ledger/penetrate 端点参数为 account_code + drill_level + date，不支持按 amount 容差匹配；按金额穿透需新增端点
- assignment_service.ROLE_MAP 和 role_context_service._ROLE_PRIORITY 两个字典是角色体系单一真源，新增 role='eqcr' 必须同时更新；_ROLE_PRIORITY 当前 partner(5)/qc(4)/manager(3)/auditor(2)/readonly(1)
- GoingConcernEvaluation 模型已存在（collaboration_models.py），Round 5 EQCR 持续经营 Tab 可直接复用，不要重复建模
- 归档包设计决策：采用"插件化章节"模式（00/01/02/.../99 顺序），各 Round 各自插入章节，Round 1 需求 6 只预留机制
- 归档包章节号分配：00 项目封面 / 01 签字流水（R1）/ 02 EQCR 备忘录（R5）/ 03 质控抽查报告（R3）/ 10 底稿/ / 20 报表/ / 30 附注/ / 40 附件/ / 99 审计日志
- 审计意见锁定架构决策：不新增 opinion_locked_at 平行字段，改为扩展 ReportStatus 状态机 draft→review→eqcr_approved→final（R5 需求 6 + README 跨轮约束第 3 条）
- 枚举扩展硬约定：IssueTicket.source 在 R1 一次性预留 11 个值（L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/pbc/confirmation/qc_inspection），ProjectAssignment.role 预留 eqcr，避免多轮迁移
- 权限矩阵四点同步约定：新增 role/动作需同时更新 assignment_service.ROLE_MAP + role_context_service._ROLE_PRIORITY + 前端 ROLE_MAP + composables/usePermission.ROLE_PERMISSIONS
- 焦点时长隐私决策：R4 需求 10 焦点追踪只写 localStorage（按周归档键），不落库不发后端，消除监控隐患
- 跨轮 SLA 统一按自然日计，不引入节假日日历服务，跨长假由人工 override（README 跨轮约束第 5 条）
- ClientCommunicationService 已存在于 `pm_service.py:481`，沟通记录存 `Project.wizard_state.communications` JSONB，`commitments` 已升级为结构化数组（R2 Task 12 完成），每条 commitment 创建 IssueTicket(source='client_commitment')
- Project 模型已有 budget_hours/contract_amount/budgeted_by/budgeted_at 字段（R2 Task 20）
- HandoverRecord 模型已存在（handover_models.py），POST /api/staff/{id}/handover 端点可用（R2 Task 23）
- system_settings 表存 hourly_rates JSON 配置（partner:3000/manager:1500/senior:900/auditor:500/intern:200）
- cost_overview_service.compute 纯函数：按 approved 工时分 role 乘 rate 得成本，burn_rate = 近 14 天/14
- budget_alert_worker 每日扫描，幂等键 budget_alert:{project_id}:{threshold}:{YYYYMMDD}
- notification_types.py R2 新增：WORKPAPER_REMINDER/WORKHOUR_APPROVED/WORKHOUR_REJECTED/ASSIGNMENT_CREATED/COMMITMENT_DUE/BUDGET_ALERT_80/BUDGET_OVERRUN/HANDOVER_RECEIVED
- BatchAssignStrategy 纯函数三策略（manual/round_robin/by_level），audit_cycle 映射：D/F→初级(1)，K/N→复杂(3)
- 工时审批幂等：Redis `idempotency:workhour_approve:{key}` TTL 5 分钟；SOD 守卫通过 StaffMember.user_id→staff_id 比对
- 催办限流：Redis `remind:{wp_id}:{YYYYMMDD}` 7 天内最多 3 次，超限 429
- 批量简报缓存：WordExportTask(doc_type='batch_brief', template_type=cache_key_sha256)，7 天复用
- manager 前端权限新增：view_dashboard_manager/approve_workhours/send_reminder/batch_brief
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
- Task 2 后端 ReviewInbox 合并无需改代码：`pm_dashboard.get_global_review_inbox` 与 `get_project_review_inbox` 本就共用 `ReviewInboxService.get_inbox`，增补 test 覆盖即可
- Task 3 ReviewWorkbench 中栏未嵌入 Univer 只读版（WorkpaperEditor 无 readonly prop/defineProps），采用元信息卡 + "打开完整编辑器"跳转；ReviewInbox.vue 保留不删（Round 1 回归后清理），ReviewWorkstation.vue 已删
- Task 4 正向联动（review→issue 创建）用 `db.begin_nested()` SAVEPOINT 隔离，工单创建失败不阻断 ReviewRecord，发 REVIEW_RECORD_CREATED 事件走补偿；与 Task 6 反向同步的强一致语义（整体回滚）对立
- Task 4 EventType 新增 `REVIEW_RECORD_CREATED = "review_record.created"`；extra 含 ticket_created 标识，补偿订阅以 source_ref_id 幂等
- Task 5 Univer 红点方案：`FRange.attachPopup({componentKey, isVue3, direction})` + `univerAPI.registerComponent(name, comp, {framework:'vue3'})` 公开 API，canvas-pop-manager 自动跟踪视口；不调 setCellValue 故不污染 dirty；`FWorksheet.scrollToCell(row,col)` 做路由 query 定位
- Task 5 IssueTicket 无 cell_ref 字段，IssueTicketList→WorkpaperEditor 跳转传 `?review_id=<source_ref_id>`，WorkpaperEditor 查到 cell_reference 再滚过去（比手工同步 cell_ref 更准）
- Task 6 反向同步（issue→review/WP）强一致：与工单状态变更同事务，`_sync_review_record_on_status_change` 失败整体回滚；幂等通过"令牌串 `[系统] 已整改，请复验` 探测 + ReviewRecord.status 探测 + WP review_status 非 rejected 不回退"三重保障
- Task 6 reply_text 追加而非覆盖：已有文本换行追加令牌串 `[系统] 已整改，请复验`，保留编制人原回复；审计日志 `review_record.replied_by_ticket / resolved_by_ticket` 记录
- Task 7 gate_eval_id vs trace_id 职责分离：trace_id 是 gate_engine 内部执行链追踪（5s 内部幂等缓存），gate_eval_id 是面向客户端的 5 分钟签字幂等令牌，由 `services/gate_eval_store.py` 独立生成（Redis + 本地字典降级）
- Task 7 readiness 统一响应 schema：`{ready, groups, gate_eval_id, expires_at, checks(legacy), ready_to_sign(legacy)}`；ready 语义 = `gate_decision != 'block' AND 无 blocking finding`（warn 不阻断）；legacy checks/ready_to_sign 保留至 Round 2 前端切 GateReadinessPanel 后移除
- Task 7 readiness_facade `_SIGN_OFF_RULE_CATEGORY` / `_EXPORT_PACKAGE_RULE_CATEGORY` 映射表：未映射的 rule_code 归入 MISC_CATEGORY（id='misc'），保证新规则 UI 不消失
- Task 7 actor_id 兜底顺序：传入 → project.created_by → 随机 UUID（仅用于 trace_events，不影响决策）；新增 service 签名 `check_sign_readiness(project_id, actor_id=None)` 保持向后兼容
- Task 7 签字接口 `POST /api/signatures/sign` 新增可选 `gate_eval_id/project_id/gate_type`；传入则调 `validate_gate_eval` 失败返回 403 `GATE_STALE`，未传走原流程（R1 渐进迁移）
- Task 8 `R1-AJE-UNCONVERTED` rule 按 `Adjustment.entry_group_id` 聚合 rejected AJE 组，用 `UnadjustedMisstatement.source_adjustment_id` 精准判定"已转错报"（字段已存在无需粗粒度回退）；severity=warning，sign_off 注册
- Task 8 `R1-EVENT-CASCADE` rule 查 `ImportEventOutbox` 近 1h 的 pending/failed（覆盖 `workpaper.saved/reports.updated`，**不覆盖 in-memory event_bus.publish** 的事件）；severity 动态：`now<start_date→warning / 已到→blocking`，默认 `start_date=2026-06-05`（R1 上线约 1 个月后，宽容期）；通过 `GateRuleConfig(rule_code, 'enforcement_start_date')` 可配置
- `gate_engine.load_rule_config(db, rule_code, threshold_key, tenant_id=None)` 读平台级/租户级阈值配置，用于规则动态参数（Task 8 使用）
- Task 10 `GateReadinessPanel.vue` 组件 props：`data(必传)/loading/projectId/onRefresh/onFindingJump/defaultOpenGroupIds`；**不自己拉数据**，调用方（Task 12 PartnerDashboard / Task 17 ArchiveWizard）负责拉取；过期自动调 onRefresh 一次（按 gate_eval_id 幂等）
- Task 10 内置跳转映射：`location.wp_id` → WorkpaperEditor / `section=adjustments` 或 `sample_entry_group_ids` → Adjustments / `section=misstatements` → Misstatements / `section=notes/disclosure` → DisclosureNotes / `section=report` → AuditReport / `section=issues/review_comment` → IssueTicketList；其他触发 `@no-target` 事件
- Task 10 Adjustments 转错报按钮只在 `review_status='rejected' AND adjustment_type='aje'` 显示；409 ALREADY_CONVERTED 返回 `err.response.data.detail` 需走 axios `err.response` 而非 apiProxy 解包
- Task 13 ArchiveOrchestrator 串行步骤：gate → wp_storage → push_to_cloud(可选) → purge_local(可选)；失败记 failed_section/failed_reason，retry 从 last_succeeded_section 下一步开始
- Task 14 archive_section_registry API：`register(prefix, filename, generator_func)` / `list_all()` / `generate_all(project_id, db)`；同 prefix 覆盖；R1 注册 00/01/99 三章节
- Task 15 PDF 生成方案：HTML 模板内嵌 → LibreOffice headless 转 PDF（不依赖 python-docx），水印 SHA-256 hash 用占位符"待归档完成后填入"
- Task 16 归档完整性：orchestrate/retry 成功后调 `archive_section_registry.generate_all` 计算各章节 SHA-256 → `export_integrity_service.persist_checks` 持久化 → 拼接所有 hash 再 SHA-256 得 manifest_hash 写入 ArchiveJob；失败不阻断
- Task 19 notification_types.py 常量：ARCHIVE_DONE/SIGNATURE_READY/GATE_ALERT/REPORT_FINALIZED + NOTIFICATION_META 模板字典；前端 notificationTypes.ts 同步 + getNotificationJumpRoute 工具函数
- Task 19 NotificationService 支持两种用法：`NotificationService()` 调用时传 db 或 `NotificationService(db)` 实例化时传；`send_notification_to_many` 批量发送
- Task 22 IndependenceDeclarationCompleteRule (R1-INDEPENDENCE, blocking)：检查项目核心四角色（signing_partner/manager/qc/eqcr）是否都有 submitted/approved 声明；兼容旧 `wizard_state.independence_confirmed=true` 视为 legacy 通过
- Task 24 RotationCheckService：按 `ProjectAssignment WHERE role IN (signing_partner, eqcr)` JOIN `Project WHERE client_name` 聚合连续年数；默认轮换上限上市 5 年/非上市 7 年（当前硬编码 5）
- Task 24 保留期：归档成功后 `Project.archived_at=now + retention_until=archived_at+3652d`；`purge_project_data` 入口硬校验 `now<retention_until` → 403 RETENTION_LOCKED
- Task 26 哈希链属性测试：4 个 hypothesis 属性（正确链通过/篡改 payload 检出/篡改 hash 检出/交换顺序检出），纯算法不依赖 DB
- Round 1 新增后端文件清单（Sprint 3）：audit_log_models.py / independence_models.py / rotation_models.py / audit_logger_enhanced.py(重写) / audit_log_writer_worker.py / audit_logs.py(router) / independence_service.py / independence.py(router) / rotation_check_service.py / rotation.py(router) / independence_questions.json / round1_long_term_compliance_20260508.py(migration)
- Round 1 新增前端文件清单（Sprint 3）：IndependenceDeclarationForm.vue / rotationApi.ts

## 活跃待办

### 最高优先级
- 合并 feature/global-component-library 到 master（用户手动操作）
- **R1 上线前必须修复的 4 个 bug**（Round 1 复盘发现，详见下条）：
  1. 前端 PartnerDashboard 传 `prerequisite_signature_ids` 用 `(s as any).id` 但后端 `get_workflow` 未返回 id 字段 → 前置校验永不触发；修复：`SignService.get_workflow` 返回加 `id: str(r.id)` + 前端读 `s.id`
  2. `GET /api/audit-logs/verify-chain` 缺 `get_current_user` 权限校验，任何登录用户可查任意项目哈希链；修复：限 admin/qc/signing_partner
  3. `audit_log_writer_worker` 多副本场景 prev_hash race → 链断；修复：`_write_batch` 加 PG advisory lock（hash(project_id)）或 README 硬约束单实例
  4. `IndependenceDeclarationCompleteRule` legacy 兼容对老项目未生效，上线瞬间全部老项目 sign_off 阻断；修复：规则加"archived_at IS NOT NULL 跳过"或批量注入 wizard_state.independence_confirmed=true
- 0.3 公式计算浏览器手动验证（启动前端输入 `=SUM(A1:A3)` 看结果）
- R1 UAT 6 条清单从未真人浏览器跑过（连续复核 10 张 / 红点 / 三级签字顺序 / 归档包验证 / PBC 入口移除）——PDCA 闭环硬缺口
- 用真实审计项目进行用户验收测试（UAT）
- 生产环境部署准备（Docker 镜像打包 LibreOffice、PG 环境变量、数据库初始化）
- 打磨路线图已由"4 轮主题"改为"5 角色轮转"：Round 1 合伙人 / Round 2 PM / Round 3 质控 / Round 4 助理 / Round 5 EQCR，5 轮三件套（requirements+design+tasks）全部起草并完成一致性校对
- 实施顺序：R1 → R2 → R3+R4（并行，相互独立）→ R5，依据 README v2.2 "跨轮依赖矩阵"
- **Round 2 已全部完成**（Sprint 1-3 共 24 任务）：通知铃铛/PM 看板/增强委派/催办/承诺升级/简报/工时审批/权限收口/预算成本/人员交接；Round 2 关闭
- Round 1 已全部完成（Sprint 1-3 共 26 任务 + 3 验收，157 测试全绿）+ Batch 1 14 项（02e3731）+ Batch 2 14 项（01881a7）+ Batch 3 14 项（待推送）；Round 1 关闭
- Batch 3 完成：立刻修 5 项（3-1/3-2/3-3/3-4/3-5）+ 尽快修 4 项（3-6/3-7/3-8/3-9）+ 文档 3 项（3-10/3-11/3-12）+ 配套 2 项（3-13/3-14 合并入其他）
- Batch 3 新建 `.kiro/specs/refinement-round1-review-closure/RETROSPECTIVE.md` 汇总 Round 1 原 26 任务 + 42 项 patch 的全貌 + 5 条复盘纪律沉淀
- Batch 3 关键决策：`AUDIT_LOG_WRITE_FAILED` 独立 notification 类型（跳转 `/audit-logs/verify-chain`）、`_send_admin_notification(db, ...)` 复用 session、worker 启动 `logger.info` + `worker_id={host}-{pid}`、`INDEPENDENCE_LEGACY_GRACE_ENABLED` 全局开关、`_resolve_legacy_cutoff` 解析失败统一返回 None+WARNING（不再回退硬编码）、前端 `pendingIndependenceProjects={projects,total,hasMore}` 结构化 + 加载更多按钮
- Batch 2 补 17 个新测试（section_progress/非上市 7 年/legacy 宽容/pending_independence/weasyprint 降级），前端 useApiError 已被 3 个页面实际消费
- Batch 2 技术债清理：`_get_next_section_index` 签名只接 `section_progress`，`last_succeeded_section` 字段仍写但不参与路由判断
- Batch 2 新增 config：`INDEPENDENCE_LEGACY_CUTOFF_DATE`（空串=关闭宽容期），`/api/my/pending-independence` 新增 `limit: int = Query(50, ge=1, le=500)` + `has_more` 字段
- Batch 2 新增 `backend/docs/adr/README.md`（ADR 索引表），`tasks.md` 追加 Round2-Task-A~F 6 条任务候选
- Round 1 复盘新增：`composables/useApiError.ts`、`docs/adr/003-review-issue-transaction-strategy.md`、`tests/README.md`（测试盲点）、`workers/README.md`（单实例约束）
- PDF 生成优先 weasyprint（可选 `pip install weasyprint`），不可用降级 LibreOffice（Fix 9）
- `GET /api/my/pending-independence` 批量端点替代前端 N+1（Fix 7）
- `useApiError.ts`：`parseApiError(err)→{code,message,detail}` + `showApiError(err)` 统一前端错误处理（Fix 8）
- ArchiveOrchestrator `_get_next_section_index` 同时检查 `section_progress` dict（Fix 5）
- `RotationCheckService.check_rotation` 新增 `is_listed_company` 参数，上市 5 年/非上市 7 年（Fix 6）

### Round 1 Batch 4 待修（复盘锁定的 14 项，按优先级）

**P0 合规必修（3 项）**：
- `IndependenceDeclarationCompleteRule._all_core_roles_declared` 查询异常 return True 静默放行 → 改 raise/降级为 warning 并 `logger.error`
- `IndependenceService._check_conflict_answers` 对任何 yes/true 打 `pending_conflict_review` 误判 → `independence_questions.json` 加 `is_conflict_signal: true` 字段，只对标注的问题触发
- `ArchiveOrchestrator._set_project_retention` 重试覆盖 `archived_at` 导致保留期重新计时 → `if project.archived_at is None:` 再写

**P1 性能（3 项）**：
- `audit_log_entries` 加 JSONB 复合索引 `(payload->>'project_id', ts DESC)` 供 `_get_prev_hash` 查询
- `issue_tickets` 加复合索引 `(source, source_ref_id)` 供 Task 4/6 反向同步查询
- `archive_jobs.section_progress` GIN 索引（Round2-Task-E 已登记）

**P1 可观测性（4 项）**：
- `_write_batch` advisory lock 失败静默 fallback to lock-free → 加 env `AUDIT_LOG_REQUIRE_ADVISORY_LOCK=True` 默认，失败 raise 让 worker 重启
- `_html_to_pdf_weasyprint` ImportError 完全静默 → 模块级 flag 首次 ImportError 记 warning 一次
- PDF 水印"待归档完成后填入"语义矛盾 → 改为"本 PDF 的 SHA-256: <自哈希>"或去掉 hash 部分归入 manifest.json
- `audit_logger_enhanced.query_logs` 改名 `_query_recent_cache` 私有化或加 @deprecated_for_audit 装饰器

**P2 架构（2 项）**：
- `sign_service._maybe_transition_report_status` 对象类型硬编码 `audit_report` → 抽 `_STATE_MACHINE_HOOKS: dict[str, Callable]` 注册表，R3/R5 rotation_override 复用
- `rotation_check_service` 按 client_name 精确匹配，客户改名/并购后年数重置漏洞 → Round 3+ 引入 `client_alias_history` 表按 client_id 聚合

**P2 工程（2 项）**：
- Worker 单实例约束仅靠 README + worker_id 肉眼巡检 → 启动 Redis `SETNX audit_log_writer:lock <worker_id> EX 30`，已有则 exit(1)
- `sign_document` 未强制绑定 `gate_eval_id.project_id` → 签字时强制 `validate_gate_eval(project_id=report.project_id)`，不匹配返回 403 `GATE_PROJECT_MISMATCH`

### Round 2 复盘锁定 37 项待修（分 8 类，按优先级）

**P0 合规/安全（6 项）必修**：
- [x] `assignment_service.py:143` message_type 硬编码 `"ASSIGNMENT_CREATED"` 大写违反跨轮约束 1 → 改用 `notification_types.ASSIGNMENT_CREATED` 常量，删除 `manager_dashboard_service.get_assignment_status` 的双写兼容（Batch 1 P0.1 完成，21 测试通过）
- [x] `POST /api/staff/{id}/handover` 只要 `get_current_user` → 加 `require_role(["admin","partner","manager"])`，manager 限 by_project 范围内自己的项目（Batch 1 P0.2 完成，preview 端点同样收紧）
- `POST /api/workpapers/batch-assign-enhanced` 缺 project_access 校验 → 所有 wp_ids 必属同一项目且当前用户对该项目有 `edit` 权限
- `POST /api/workhours/batch-approve` 只限 role 不限项目 → 校验 hour_ids 对应 project_id 都在当前用户的 manager/signing_partner 项目列表
- Sprint 2 验收要求的 `test_pm_workflow_e2e.py`（委派→催办→重新分配→承诺→审批→简报）未写
- Sprint 3 验收要求的 `test_handover_e2e.py`（建 staff→分底稿→离职交接→验证数据迁移+留痕）未写

**P1 数据正确性（6 项）**：
- `manager_dashboard_service._get_manager_project_ids` 每请求调 2 次（router 权限守卫 + service 内部）→ 权限判断返回 project_ids，service 接可选入参
- `manager_dashboard_service` 用 `datetime.now(tz=None)` 与 UTC aware created_at 比较在 PG 生产会抛 TypeError → 统一 `datetime.now(timezone.utc)`
- `workpaper_remind_service._increment_remind_count` INCR + 单独循环 SUM 非原子 → Redis pipeline 或 Lua 脚本，或改单 key `remind_count:{wp_id}` TTL 7d
- `workpaper_remind_service` Redis INCR 在 db.commit() 之前 → 移到 commit 后，失败不计入
- `handover_service.execute` 只 flush 不 commit，依赖 router 隐式 commit → service 末尾显式 `await db.commit()` + try/except rollback
- `ManagerDashboard.vue` 前端 N+1：每个项目独发 `/cost-overview` 请求 → 批量端点或并入 `/manager/overview` 响应

**P1 性能（3 项）**：
- `manager_dashboard.get_overview` 顺序跑三个聚合 → `asyncio.gather` 并发
- `_aggregate_projects` 底稿状态查 + overdue 查两次 SQL → 合并成一次 CASE WHEN
- `WordExportTask.template_type` 存 cache_key_sha256 无索引 → 加 `idx_word_export_task_template_type`

**P1 可观测性（4 项）**：
- `budget_alert_worker.run` 开头缺 `logger.info("started") + worker_id` 纪律
- Notification metadata 字段名散落各 service 无单一真源 → 加 `META_SCHEMA: Record<type, required_fields[]>` 校验
- `batch_brief` AI 失败回退无响应字段 → 加 `ai_fallback_reason: str | null` 给前端展示
- Round 2 `RETROSPECTIVE.md` 未建（R1 有对齐格式参考）

**P2 UX（6 项）**：
- `ProjectDashboard.vue` 催办 `remindCounts` 只存内存，刷新丢失 → 从后端 list/preview 端点同步
- `BatchAssignDialog.vue` by_level 前端自实现策略与后端 `CYCLE_COMPLEXITY_MAP` 会漂移 → 前端只提交，后端返预览
- `CommunicationCommitmentsEditor` 不支持编辑已存在承诺（id/ticket_id 会被覆盖）
- `ManagerDashboard.vue` elapsedTimer 常驻 setInterval 浪费 CPU → 超 1 小时停 timer 或 requestIdleCallback
- `BatchAssignDialog` 候选人未排序 → 按 role(manager→senior→auditor) + 姓名排序
- `WorkHoursApproval.vue` 加载打 3 次 `/api/workhours` → 后端加 `/api/workhours/summary?week` 一次返回

**P2 架构/一致性（8 项）**：
- `batch_brief._generate_ai_summary` prompt 无 token 上限 → 按模型能力截断 combined_text
- `cost_overview_service._TITLE_TO_RATE_KEY` 依赖 `StaffMember.title` 自由文本 → `StaffMember` 加 `role_level` 枚举
- `batch_brief` 用 `WordExportTask.template_type` 存 cache_key 是字段复用 → 加专用 `cache_key` 字段或 metadata JSONB
- `IssueTicket.source='reminder'` 无自动关闭机制 → workpaper review_passed 事件时自动关或设 `auto_close_at`
- `IndependenceDeclaration.status='superseded_by_handover'` 值未在枚举声明 → 回补 R1 枚举
- `batch_assign_enhanced` 不走 WpEventService → 每条发 `WP_ASSIGNED` 事件或显式 audit_logger 记录
- `manager_dashboard._compute_risk_level` 查询时算不落库 → 未来"高风险项目趋势"需持久化
- `handover_service` audit_log `details` 里的 from/to_staff_id 未索引 → 合并到 R1 Batch 4 的 `audit_log_entries` JSONB 索引

**P2 测试覆盖（4 项）**：
- `batch_assign_enhanced` 路由层端点 + DB 变更 + 通知发送闭环未测
- `cost_overview` 端点层无集成测试（只有 service 层）
- 催办/重新分配/承诺的跨角色权限矩阵未测
- `budget_alert_worker._check_all_projects` 主循环未测（幂等键/阈值触发）

### 中期功能完善
- 性能测试（真实 PG + 大数据量环境运行 load_test.py，验证 6000 并发）
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度 85%，业务完成度 60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能
- `GtStatusTag.STATUS_MAP_TO_DICT_KEY` 是硬编码映射表，新增 StatusMap 时需手动维护 [P3]

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
