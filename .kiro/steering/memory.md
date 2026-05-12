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
- 表格数字列（金额、科目编号等）统一使用 Arial Narrow 字体 + `white-space: nowrap` + `font-variant-numeric: tabular-nums`，通过 `.gt-amt` class 实现
- 表格分页用标准分页组件（左侧 page size 选择器 + 右侧页码导航含 jumper），不用"加载更多"模式
- 四表联查需支持全屏模式 + 行选择（checkbox）+ 右键菜单，右键菜单预留"抽凭到底稿"入口（后续与底稿抽凭模块衔接）
- 表格编辑需支持查看/编辑模式切换
- 复制按钮命名：工具栏"复制整表" vs 右键"复制选中区域"
- 系统打磨采用 PDCA 迭代模式：提建议→成 spec 三件套→实施→复盘→下一轮新需求，直到可改进项穷尽
- 打磨迭代具体化为"5 角色轮转"：合伙人/项目经理/质控/审计助理/EQCR 独立复核，每轮只站单一角色视角找断层，规则见 `.kiro/specs/refinement-round1-review-closure/README.md`
- 每轮 requirements.md 起草后必须做"代码锚定交叉核验"（grep 所有假设的字段/表/端点/枚举），发现硬错立刻回补到文档，避免错误带到 design 阶段
- 标任务 [x] 前必须跑 pytest 或对应测试通过，而非仅因"代码文件存在"就标完成；用户明确要求做完整复盘时要诚实暴露问题而非粉饰
- **账表导入识别引擎设计原则**：通用规则+动态适配，不做"看一个改一个"的定制化；识别处理时表头和列内容同时处理（前 20 行数据量不大）；脚本要支持扩展（声明式 JSON 配置）而非硬编码 if-else

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
- 前端依赖共 22 生产 + 8 开发：关键新增 mitt@3.0.1、nprogress@0.2.0、unplugin-auto-import@21.0.0、unplugin-vue-components@32.0.0、@univerjs/presets@0.21.1、@univerjs/preset-sheets-core@0.21.1（公式引擎内置）、@univerjs/sheets-formula@0.21.1、opentype.js@1.3.5、xlsx@0.18.5；R8-S2 新增 dev 依赖 glob@13（scripts/find-missing-v-permission.mjs 使用）
- 后端新增测试依赖 hypothesis@6.152.4 + ruff@0.11.12（R6 Task 2 写入 requirements.txt）
- PG ~160 张表（152 基线 + R5 新增 6 张 + R6 新增 qc_rule_definitions + review_records.conversation_id 列），Redis 6379，后端 9980，前端 3030
- 前端 HTTP 全局超时 120s（http.ts），detect 端点单独 300s（大文件多文件场景）
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-07 实测核对）

- vue-tsc 0 错误（2026-05-06 全部修复：el-tag type 联合类型标注 + dictStore.type() 返回类型收窄 + 模板 `:type` 绑定加 `|| undefined`），Vite 构建通过
- 后端 **151** 个路由文件，**226** 个服务文件（含子目录 import_engine/、wp_scripts/ 等），**51** 个模型文件，11 个 core 模块，9 个 middleware，~152 张表（此前 memory 记录 127/181/39 已过时）
- 后端 `backend/app/workers/` 模块 4 个：sla_worker、import_recover_worker、outbox_replay_worker、import_worker（每个导出 `async def run(stop_event)`）
- 前端 **86** 个 Vue 页面（views/ 含子目录 ai/eqcr/qc/independence/extension），**194** 个组件（components/ 含所有子目录），16 个 composables，9 个 stores，19 个 services，19 个 utils
- GtPageHeader 接入率 **12/86**（14%）：TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/EqcrMetrics/KnowledgeBase/Misstatements/Projects/Materiality/AuditReportEditor/Adjustments/WorkpaperList
- GtEditableTable 接入率 **0/86**
- v-permission 接入 **5** 个 .vue 文件
- useEditingLock 接入 **3** 个编辑器（WorkpaperEditor/DisclosureEditor/AuditReportEditor）
- ElMessageBox.confirm 直接用法 **0 处**（R8-S1 Day 2-3 全量清零，30+ 处全部替换为 utils/confirm.ts 语义化函数）
- Vue 层 /api/ 硬编码剩余 **~17 处**
- **顶栏已改为致同品牌深紫背景**（#4b2d77），logo 用反白版 gt-logo-white.png，文字/图标/按钮全白色；侧栏底色 #f8f7fc（微紫调）
- **Logo 文件**：public/gt-logo-white.png（反白，顶栏用）、public/gt-logo.png（标准彩色，登录页+favicon）、public/gt.png（旧版保留兼容）
- **页面标题**：致同审计作业平台（index.html title 已更新）
- pytest collection **2830 tests / 0 errors**（2026-05-07 修复后）：之前 7 个 collection error 已通过添加 `wrap_ai_output` 函数、`IndependenceDeclaration` 别名、`build_ai_contribution_statement` 等 4 函数到 pdf_export_engine、`AIContentMustBeConfirmedRule` re-export 到 gate_rules_phase14 全部解决
- 后端测试：98+ 个根目录测试 + 4 个 e2e + 4 个 integration + R5 新增 test_eqcr_full_flow/test_eqcr_state_machine_properties/test_eqcr_component_auditor_review
- git 分支：feature/round8-deep-closure（HEAD = a1b936e，R8 Sprint 1+2 全部完成 + 清理，已推送到 origin）；上游 feature/round7-global-polish（2e72884）
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

- **Docker 日常只起 3 个基础服务**：audit-postgres(5432) + audit-redis(6380:6379) + audit-metabase(3000)；backend 容器已从默认 compose 移除（或挂到 profile），本地开发 **唯一** 用 start-dev.bat 跑在宿主机 9980；Docker 里再起后端 = 重复进程 + 重复 worker 循环吃 CPU
- **docker-compose.yml backend 服务 profiles: [docker-backend]**：默认 `docker compose up` 不拉起；需要时 `docker compose --profile docker-backend up -d backend`
- **PG job_status_enum 类型值（2026-05-07 补齐后 12 个）**：pending/running/completed/failed/timed_out/cancelled/retrying（历史遗留）+ queued/validating/writing/activating/canceled（R8 补齐）；Python JobStatus 实际只用 10 个，cancelled(双L)/retrying 是历史数据兼容保留
- **dataset_models.py ImportJob.status 类型名修正**：`sa.Enum(JobStatus, name="job_status_enum", create_type=False)`（之前错写 `name="job_status"` 导致 SQLAlchemy 生成 `$1::job_status` 与 PG 真实类型名不匹配，import_recover_worker 每几毫秒刷 UndefinedFunctionError 死循环吃 89% CPU）
- **PG ALTER TYPE ADD VALUE 事务限制**：同事务内新增的 enum 值不能立即使用（报"unsafe use of new value"），psql 单条命令各自事务时需分多次 docker exec 执行而非分号连写
- **PG schema 已于 2026-05-07 重建（方案 A）**：旧库 alembic_version='035' 与当前 28 个迁移文件完全脱节（Round 1-7 新增列全部缺失），执行 DROP DATABASE + `python backend/scripts/_init_tables.py` 重建 171 张表；admin 用户已恢复（UUID ae9e0523 / admin@gt.cn / admin123）；种子数据需后端启动后调 seed 端点加载
- **PG 重建后待办**：启动后端后需调用 6 个 seed 端点加载基础数据（/api/report-config/seed、/api/gt-coding/seed、/api/ai-models/seed、/api/ai-plugins/seed、/api/accounting-standards/seed、/api/template-sets/seed）
- **admin 密码哈希写入注意**：PowerShell 会吃掉 `$` 符号导致 bcrypt hash 损坏（Invalid salt），必须用 Python + SQLAlchemy 参数化写入，不能通过 docker exec psql 拼 SQL 字符串；passlib 与新版 bcrypt(4.x) 不兼容，直接用 `bcrypt.hashpw` 生成哈希
- **issue_tickets.due_at 是 TIMESTAMP WITHOUT TIME ZONE**：SLA worker 查询时不能传 aware datetime，需 `.replace(tzinfo=None)`；同类问题可能存在于其他 naive 列（created_at/updated_at 是 `WITH TIME ZONE`，但 due_at 不是）
- **全库 timezone-aware 化已彻底完成（2026-05-07）**：曾存在 330+ naive 列导致代码 `datetime.now(timezone.utc)` 与 `TIMESTAMP WITHOUT TIME ZONE` 不兼容；修复方案 = (1) PG 执行 `_fix_timestamptz.sql` 一次性 `ALTER COLUMN ... TYPE TIMESTAMPTZ USING ... AT TIME ZONE 'UTC'` 转 409 列；(2) `base.py` 注册 `Base.registry.update_type_annotation_map({datetime: DateTime(timezone=True)})` 让所有 `Mapped[datetime]` 默认 aware；(3) TimestampMixin 显式加 `DateTime(timezone=True)`；(4) 批量替换 26 处显式 `Column(DateTime,...)` / `sa.DateTime,` 为 `DateTime(timezone=True)`；最终 `Base.metadata.tables` naive 列数 = 0
- **SQLAlchemy datetime 默认类型陷阱**：`Mapped[datetime]` 不加 `DateTime(timezone=True)` 默认生成 naive（`TIMESTAMP WITHOUT TIME ZONE`）；显式传 `sa.DateTime` 也是 naive，必须 `sa.DateTime(timezone=True)`；显式声明会覆盖 `type_annotation_map` 全局默认
- **PG schema 转换铁律**：naive → aware 必须 `USING col_name AT TIME ZONE 'UTC'` 才能保留原值语义；裸 `ALTER ... TYPE TIMESTAMPTZ` 会按服务器时区（如 Asia/Shanghai）解释导致偏移
- **backend/scripts/_fix_timestamptz.sql 已建**：可重跑的幂等脚本，遍历 information_schema 把所有 naive 列转 timestamptz；未来若再遇到零散 naive 列回归，一键修复
- **账表导入 spec 核心策略（ledger-import-unification）**：四表联动关键列（余额表 `account_code`+期初/期末/发生额；序时账 `voucher_date`+`voucher_no`+`account_code`+借贷；辅助表 +`aux_type`+`aux_code`）置信度 ≥ 80 强制人工确认，次关键列（`account_name`/`summary`/`preparer`/`currency_code` 等）≥ 50 自动映射，非关键列进 `raw_extra JSONB` 不校验；错误分级对应：关键列 blocking / 次关键列 warning（值置 NULL）/ 非关键列不校验
- **前端视图/组件实测规模（2026-05-07）**：views/ 含子目录共 86 个 `.vue`（根目录 68 + ai/eqcr/qc/independence/extension）；GtPageHeader 接入率 12/86（14%）；GtEditableTable 接入率 0/86；statusMaps.ts 已删除；components/ai/ 清理后剩余约 14 个文件
- **导航动态化已落地**：`ThreeColumnLayout.vue:360` navItems 已 computed + buildNavForRole 按角色过滤；FALLBACK_NAV 10 项含 roles 字段；后端 get_nav_items 仍可覆盖但前端已不依赖
- **ReviewInbox.vue 是死代码**：router 三条路由（ReviewInbox/ReviewInboxGlobal/review-inbox）全部指向 `ReviewWorkbench.vue`，`ReviewInbox.vue` 文件仍在但无引用，可安全删除
- **PartnerDashboard.vue 两处硬编码**：第 561、582 行 `/api/my/pending-independence?limit=...` 未走 apiPaths；QCDashboard.vue:325 `/api/qc/reviewer-metrics` 同样硬编码；需补 `apiPaths.ts` 的 `my.pendingIndependence` / `qc.reviewerMetrics` 并封装 service
- **EQCR 指标入口权限窄**：`DefaultLayout.vue` 第 132 行 `isEqcrEligible` 只认 partner/admin，`router/index.ts:465` meta.roles 同样窄，建议加 `role === 'eqcr'` 让 EQCR 自己看指标
- **AI 组件重复 + 死代码**：`components/workpaper/AiContentConfirmDialog.vue` 与 `components/ai/AiContentConfirmDialog.vue` 同名共存；`ai/ContractAnalysis / ContractAnalysisPanel / EvidenceChainPanel / EvidenceChainView` 四组件 grep 零引用
- **/confirmation 侧栏指向不存在的路由**：`ThreeColumnLayout.vue:330` 侧栏"函证"指 `/confirmation`，但 router 中无此路径定义，点击走 NotFound 而非 DevelopingPage；已 maturity=developing 但守卫没触发
- **Mobile 系列 5 视图全是 stub**（MobilePenetration/MobileReview/MobileReport/MobileProjectList/MobileWorkpaperEditor），Round 7+ 前可考虑整体删除以减负
- **useCellSelection 接入只 4/73**（TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex），其他表格无 Excel 级选中；行选/列选/Ctrl+A/粘贴入库/单元格撤销全部缺失
- **编辑锁前端只 1 处**：仅 `components/formula/StructureEditor.vue` acquireLock/releaseLock + lockRefreshTimer；WorkpaperEditor/DisclosureEditor/AuditReportEditor 裸奔，两人并发编辑会互覆盖（后端 workpaper_editing_locks 表已就绪）
- **后端联动链路已完整但前端不可见**：event_handlers.py 已订阅 ADJUSTMENT_*→TB→REPORTS→AUDIT_REPORT / WORKPAPER_SAVED→consistency / LEDGER_ACTIVATED→mark_stale；前端 workpaper.is_stale 只判 consistent/inconsistent 没展示 stale
- **穿透端点共 5 套**（reports/drilldown/{row_code}、drilldown/ledger/{code}、ledger/penetrate、consol_worksheet/drill/*、penetrate-by-amount），前端入口散；usePenetrate 应封装统一
- **快捷键已注册 13 个但无 UI**：shortcutManager 全局单例已在 shortcuts.ts 定义 shortcut:save/undo/redo/search/goto/export/submit/escape/refresh/help 等，但 `?` 或 F1 帮助面板未实现
- **单元格编辑不入 operationHistory**：operationHistory 当前只接 `删除` 动作（Adjustments/RecycleBin），单元格误改无 Ctrl+Z 可恢复
- **NotificationCenter 只 30s 轮询 + SSE**，无分类 Tab、无免打扰时段
- **AiAssistantSidebar 与 SmartTipList 职责重叠**：WorkpaperEditor 右栏 AI 提示在两处渲染（AiAssistantSidebar + WorkpaperEditor 内联 smartTip 面板 90-94 行）
- **顶栏工具簇已瘦身**（2026-05-07，14→4 常驻图标）：顶栏只保留 🔔通知 · Aa显示设置 | 视图切换·回收站·设置 | 复核收件箱·独立复核·EQCR 指标 | 用户菜单；SyncStatusIndicator 已从顶栏移除（正常态无交互价值）；移至左侧栏底部"工具"区的 7 个：知识库/私人库/AI 模型/排版模板/吐槽求助/公式管理/自定义查询；`.gt-topbar-btn` 统一 34×34px 圆角 8px，gap 4px，分隔线 margin 8px
- **版面组件唯一位置原则**：GtPageHeader/GtInfoBar/GtToolbar/GtStatusTag/GtAmountCell/CellContextMenu/TableSearchBar/SelectionBar/SyncStatusIndicator/NotificationCenter 等 21 个全局组件必须有唯一归属位置，禁止各视图自写重复；详见 docs/GLOBAL_REFINEMENT_PROPOSAL_v1.md §11.6
- **角色差异化布局已规约**：auditor/manager/qc/partner/eqcr/admin 各自顶栏角色动作簇、左栏导航项数、Detail 默认落地页，实现方式 = §2.2 动态导航 + §1.1 登录角色跳转
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
- apiPaths.ts 当前 **260+** 个 API 端点（2026-05-07），新增 reportConfig/reportMapping/consolNoteSections + eqcr 扩展（memo/independence/componentAuditors/priorYear/metrics）+ admin 扩展（importEventHealth/importEventReplay）+ reports.export
- 前端 service 硬编码路径迁移 **全部完成**（2026-05-07）：9 个文件共 257 处硬编码→0，全部使用 apiPaths 常量
- Vue 文件硬编码迁移进度：322→~90（已消除 ~232 处 / 72%），最新 commit 535f7dd；CI 基线 115（实际已低于基线）；剩余 ~50 文件为零散专用端点（disclosure-notes/workhours/metabase/audit-types/custom-query 等），不再批量修，触碰即修
- apiPaths.ts 新增路径对象（本轮）：knowledgeLibrary(11方法)/noteTemplates/accountChart(含standard)/accountMapping/reportLineMapping/columnMappings/dataLifecycle/consolNoteSections(8方法)/reportConfig扩展(detail/create/executeFormulasBatch/batchUpdate)/reportMapping/reports.export/independenceDeclarations；ledger 从 3 方法扩展到 17 方法；workpapers 新增 batchPrefill/generateFromCodes/wpMappingTsj/versions/univerData/univerSave/exportPdf；attachments 新增 preview/download/associate/ocrStatus
- CI 新增 vue-tsc --noEmit 步骤到 frontend-build job（.github/workflows/ci.yml）
- CI 新增 'API hardcode guard' 卡点（基线 173，grep 统计 Vue 文件 /api/ 硬编码，超基线则 fail）；本地自查脚本 scripts/check-api-hardcode.sh；策略"触碰即修+基线只减不增"
- Vue 硬编码迁移决策：剩余 65 文件 / 173 处不再批量修，采用触碰即修策略自然收敛；下一步优先级转向 UAT 验收 + 性能压测
- docs/API_CHANGELOG.md 记录 R4-R6 端点变更；docs/templates/NEW_API_ENDPOINT.md 三件套模板
- archive 对象已重构：`archive`→`orchestrate`，新增 `job(pid,jobId)` 和 `retry(pid,jobId)`
- AnnualIndependenceDeclaration 模型已扩展：新增 project_id(nullable)/status/attachments/signed_at/signature_record_id/reviewed_by_qc_id/reviewed_at 字段（R1 需求 10 合并）
- wrap_ai_output 函数已实现于 wp_ai_service.py（与 wrap_ai_content 并存，面向前端确认流程，含 id/generated_at/confirm_action/revised_content 字段）
- pdf_export_engine.py 新增 4 函数：build_ai_contribution_statement/get_ai_statement_css/get_ai_statement_html/render_with_ai_statement
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
- role_context_service.get_nav_items 已修复：QC 角色新增 3 个全局导航（规则管理/质控抽查/案例库）；manager 角色新增"项目经理工作台"入口
- workhour_list.py 新建端点：GET /api/workhours（审批人视角聚合列表）+ GET /api/workhours/summary（本周统计，消除 N+1）
- WorkpaperEditor.vue 新增"提交复核"按钮（draft→pending_review）+ 自动保存失败 toast 提示
- workpaper_remind.py 新增 POST /escalate-to-partner 端点（催办 3 次后升级通知签字合伙人）
- 前后端路径修复：WorkpaperWorkbench AI 聊天 /api/chat/stream→/api/workpapers/{wpId}/ai/chat；附件上传 /api/attachments/upload→/api/projects/{pid}/attachments/upload；AiAssistantSidebar /chat→/ai/chat

## 活跃待办

### 最高优先级
- **GLOBAL_REFINEMENT_PROPOSAL_v2.md 已生成**（docs/）：v1 落地核查 + 5 角色深挖 + 21 横切主题 + 联动穿透闭环图 + P0-P3 路线图 41 项
- **Round 8 spec 三件套已创建**（`.kiro/specs/refinement-round8-deep-closure/`）：Sprint 1（P0，42 task，1 周）+ Sprint 2（P1，82 task，3 周）
  - Sprint 1：/confirmation 路由修复 + confirm.ts 补齐 30+ 处替换 + Adjustments 转错报按钮 + projectYear store + http 5xx 容灾 + AI mask_context 审计
  - Sprint 2：WorkpaperSidePanel 7 Tab + useStaleStatus 跨视图 + ShadowCompareRow + EQCR 备忘录版本/Word 导出 + PartnerSignDecision 签字面板 + risk-summary 端点 + ManagerDashboard 4 Tab + QcHub + v-permission 15+ 处 + statusEnum.ts + formRules.ts + 附注穿透 + 重要性联动
  - **三件套一致性分析结论**：覆盖率 100%（v2 P0+P1 20 项全覆盖），2 个中等问题需实施前修补：(1) sprint2-design.md 缺 D11（R8-S2-14 未保存提醒）；(2) PartnerSignDecision PDF 预览依赖 `/api/reports/{pid}/preview-pdf` 端点需确认是否已存在
  - **Sprint 1 已完成（42/42 task，Task 3 浏览器手动验证除外）**：ConfirmationHub.vue 新建 + router 注册 + feedback.ts 新建 + http.ts 超时/断网/5xx 容灾 + confirm.ts 新增 6 函数 + **ElMessageBox.confirm 全量清零**（views 0 + components 0，远超 CI 基线 5）+ **projectStore.changeYear 增加 eventBus year:changed emit**（决策：不新建 projectYear.ts，复用现有 store）+ **AI 脱敏全路径审计**（note_ai 3 端点 + wp_ai_service analytical_review + role_ai_features _llm_polish_report / _llm_generate_summary 全部集成 mask_context）+ 新建 backend/tests/test_ai_masking.py 13 测试
  - **Sprint 2 Week 1 已完成（Task 1-23 / 82）**：新建 `composables/useStaleStatus.ts` + WorkpaperSidePanel 9 Tab（新增"自检"Tab，内联实现避免过度拆分）+ `workpaper:locate-cell` eventBus 事件 + WorkpaperEditor Univer 单元格定位 API + ReportView/DisclosureEditor/AuditReportEditor 三视图 stale 横幅 + .gt-stale-banner 统一样式 + 3 编辑器 onBeforeRouteLeave + beforeunload 未保存拦截
  - **Sprint 2 Week 2 已完成（Task 24-54 / 82）**：新建 `backend/app/services/risk_summary_service.py`（聚合 6 数据源：高严重度工单+未解决复核意见+重大错报+被拒未转AJE+持续经营+AI flags/budget/sla 预留）+ `backend/app/routers/risk_summary.py`（router_registry §21 注册）+ `views/PartnerSignDecision.vue`（三栏：GateReadinessPanel / 报告 HTML 预览 / 风险摘要 + 底栏签字操作）+ EqcrMemoEditor onExportWord（blob 下载）+ EqcrProjectView onShadowVerdict 持久化（pass/flag → agree/disagree 映射到 EqcrOpinion）+ ManagerDashboard 异常告警区块（前端 computed 派生，4 维：高风险/工时超支/逾期底稿/逾期承诺）+ PartnerDashboard 决策面板跳转按钮
  - **Sprint 2 Week 3 已完成（Task 55-82 / 82，Task 52/53/82 保留）**：新建 `scripts/find-missing-v-permission.mjs`（盘点危险操作按钮未加 v-permission，glob@13 作为 devDependency）+ 8 个漏加 v-permission 按钮补齐（ProjectDashboard 催办/PrivateStorage 删除/EqcrMemoEditor 定稿/PDFExportPanel 导出/ReviewConversations 导出/SignatureLevel1-2 签字，从 8 → 1 剩 AiContentConfirmDialog 非危险）+ ROLE_PERMISSIONS 补齐 16 权限码（含 sign:execute/archive:execute/report:export_final/workpaper:submit_review|review_approve|review_reject|escalate/assignment:batch/qc:publish_report/eqcr:approve/independence:edit）+ 新建 `qc` 角色权限组 + 新建 `constants/statusEnum.ts`（18 套状态常量 + TS 类型导出）+ WorkpaperEditor/AuditReportEditor/Adjustments 替换硬编码状态字符串为常量引用 + 新建 `utils/formRules.ts`（12 套 el-form 规则 + makeRules 组合工具）+ 新建 `backend/app/routers/note_related_workpapers.py`（附注行→底稿端点，router_registry §22）+ DisclosureEditor 右键菜单"查看相关底稿" + Misstatements 订阅 materiality:changed 事件 + GateReadinessPanel 组件内自动订阅 materiality:changed（触发父级 onRefresh） + 后端 misstatements.py 新增 POST /recheck-threshold 端点 + apiPaths 新增 misstatements.recheckThreshold
  - **R8 总完成（Sprint 1+2）**：121/124 task（97.6%，Task 52/53 跳过+Task 82 UAT 待真人）；vue-tsc 0 错误；pytest 2848 tests / 0 errors；ElMessageBox.confirm 全量清零（基线 5 合格）；新建 11 文件（后端 3 + 前端 7 + 脚本 1） + 修改 ~50 文件 + 新增 13 AI masking 测试
  - **R8 复盘发现 9 处字段凭印象错误（P0 已修复）**：risk_summary_service 违反"代码锚定"铁律——(1) ReviewRecord 无 project_id/content/wp_id，真实字段 working_paper_id/comment_text（需 join WorkingPaper 反查 project_id）；(2) UnadjustedMisstatement.net_amount→misstatement_amount，description→misstatement_description；(3) Adjustment 无 converted_to_misstatement_id，反向查 UnadjustedMisstatement.source_adjustment_id；(4) total_debit/credit 在 AdjustmentEntry 不在 Adjustment 头表；(5) GoingConcernConclusion 枚举值 no_material_uncertainty；(6) risk_summary_service 所有聚合加 year 参数；修复代码见 commit + 新建 test_risk_summary_service.py 8 smoke test 全部通过（User.hashed_password / WorkingPaper 必填 source_type 也在测试中踩雷并修正）
  - **R8 git 提交策略**：从 feature/round7-global-polish 切出 **feature/round8-deep-closure** 新分支；分组提交 7+2 个 commit（S1 / S2-W1 / S2-W2+P0 / S2-W3 / UI+spec+docs / AI脱敏漏网+v-permission / Office锁文件清理 / 移除临时文件 / .gitignore追加）；**用 COMMIT_MSG_TMP.txt 文件承载多行 commit message**（避免 PowerShell 对 `-m "Task 3 (括号)"` 括号内空格的参数误解析，用完即删）；.gitignore 新增 GT_logo/ + 2025人员情况.xlsx + `~$*` + `~WRL*` + COMMIT_MSG_TMP.txt；**已推送到 origin/feature/round8-deep-closure（a1b936e）**
  - **审计模板 Office 临时文件已清理**：129 个 ~$ 和 ~WRL 锁文件从 git 历史中删除，.gitignore 已追加 `~$*` 和 `~WRL*` 模式防止再次入库；B30 集团审计新准则英文版模板（ISA 600 revised 系列 20+ 文件）也一并从跟踪中移除
  - **Sprint 2 架构决策**：不拆 7 个 SideTab wrapper（Task 1-6 跳过，WorkpaperSidePanel 直接用 AiAssistantSidebar/AttachmentDropZone/ProgramRequirementsSidebar/DependencyGraph 已足够）；自检 Tab 复用 fine-checks/summary 批量端点（不新建 wp_id 专用端点）；stale 横幅共享 CSS class（3 视图继承）；**PartnerSignDecision 中栏 HTML 降级**（不依赖不存在的 /preview-pdf 端点，直接渲染 audit-report.paragraphs 8 节）；**ManagerDashboard 复用 overview 端点**（不新建 manager_matrix，alerts 前端派生）；**QcHub 复用 R7-S3 的 QcInspectionWorkbench 6 Tab**（不重复新建，只加 /qc → /qc/inspections 重定向）；**Task 52-53 跳过**（ProjectDashboard 非 Tab 布局，QCDashboard 降级为 Tab 重构成本过高）；**recheck-threshold 复用 get_summary**（summary 服务内部已基于最新 materiality 计算，无需重写逻辑）；**GateReadinessPanel 内部自动订阅 materiality:changed**（不让每个使用方各自订阅，利用已有 onRefresh prop 回调）
  - **ShadowCompareRow verdict 映射约定**：前端 pass/flag → 后端 EqcrOpinion.agree/disagree，复用 eqcrApi.createOpinion 端点（避免新建专用 verdict 表）
  - **IssueTicket.severity 实际枚举**（本次 grep 核对）：blocker/major/minor/suggestion（不是 memory 之前记录的 high）；risk_summary 取 blocker+major 为高严重度
- **UI 品牌风格已对齐致同内网**：顶栏深紫 #4b2d77 + 反白 logo + 白色文字图标；侧栏 #f8f7fc 微紫调；favicon 改致同 logo；页面标题"致同审计作业平台"
- 全局打磨建议 v1 已补完到 ~1800 行（docs/GLOBAL_REFINEMENT_PROPOSAL_v1.md）：5 角色穿刺 + 32 横切主题 + P0-P3 共 35 项路线图 + 第 11 章"版面位置规约"
- **Round 7 Sprint 1（P0）已完成**：18/18 task 全部执行，vue-tsc 0 错误；删除 12 文件（ReviewInbox + 5 Mobile + 5 AI 死代码 + 1 重复组件）、修改 6 文件（apiPaths/PartnerDashboard/QCDashboard/DefaultLayout/router/auth）、新建 2 文件（GtEmpty.vue + confirm.ts 5 函数）；UAT 待手动验证（角色跳转+函证路由+EQCR 指标）
- **Round 7 Sprint 2（P1）已完成**：42/42 task 全部执行，vue-tsc 0 错误；新建 5 文件（useEditingLock/useWorkpaperAutoSave/errorHandler/ShortcutHelpDialog/stale_summary.py）、修改 20+ 文件（导航动态化/13 处 ElMessageBox 替换/4 视图 useEditMode/3 视图编辑锁/2 视图自动保存/工时 Tab 合并删除 WorkHoursApproval/Stale 三态/5 视图 errorHandler/CI lint）、后端新增 stale-summary 端点；右键菜单 5 视图已在之前 Round 实现无需重做
- **R7 S1+S2 复盘修正已落地（8 项质量改进）**：(1) 角色跳转从 auth.ts 移到 Login.vue（职责单一）；(2) navItems 加 roles 字段按角色过滤+隐藏（auditor 看不到"账号权限"，qc 看不到"工时"等）；(3) WorkpaperEditor 两套自动保存合并为 useWorkpaperAutoSave 60s 单一方案；(4) AuditReportEditor/DisclosureEditor 编辑锁改 autoAcquire:false + watch isEditing 联动 acquire/release；(5) 编辑锁 watch isMine→exitEdit 强制只读；(6) autoSaveMsg/dirty 颜色改 CSS 变量；(7) 导航标签"人员"→"人员档案"/"用户"→"账号权限"；(8) useEditingLock 加 resourceType:'workpaper'|'other' 参数，非底稿资源降级为前端检测避免错误路径 404
- **Round 7 技术债清单（3 项剩余，触碰即修）**：(1) related-workpapers 端点需精确映射（report_config→account→wp_mapping）；(2) resourceType:'other' 降级需后端通用 editing_locks 表支持 resource_type 字段；(3) 4 编辑器未接入 WorkpaperSidePanel
- **已修复技术债**：#1 crossCheckResults 真实数据填充（切换 Tab 时并行加载 BS+IS 按 row_code 计算）；#4 WorkpaperEditor 硬编码颜色→CSS 变量；#5 WorkHoursPage 472→185 行（WorkHourApprovalTab 子组件）；#7 Misstatements 接入 usePasteImport（粘贴→逐行创建错报）
- **Round 8 方向建议**：P0 跨表核对真实数据+编辑锁通用化；P1 http.ts 全局 5xx 默认处理+GtPageHeader CI 指标+WorkpaperWorkbench 右栏替换；P2 related-workpapers 精确映射+vitest 基建；P3 暗色模式+Ctrl+K 全局搜索
- **流程改进沉淀**：Sprint task 数 ≤30（Sprint 3 的 58 太多）；"触碰即修"设 30 天 SLA；每 Sprint 开始前 30 分钟 grep 核对端点/字段假设；关键改动不委托子代理手动做
- **statusMaps.ts 已删除（R7-S3-02 里程碑）**：GtStatusTag 现在唯一数据源是 dictStore（后端 /api/system/dicts），不再有前端硬编码回退；所有 views 中 statusMap prop 用法已清零；后端 9 套字典完整覆盖
- **3 个后端端点确认不存在需新建**：GET /api/qc/rotation/due-this-month（Sprint 3 Task 18）、GET /api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers（Task 46）、GET /api/eqcr/projects/{pid}/memo/export?format=docx（Task 23）
- **后端编辑锁实际路径**：`/api/workpapers/{wp_id}/editing-lock`（POST acquire / PATCH heartbeat / DELETE release / POST force / GET active），不是设计文档假设的 `/api/editing-locks/acquire`；useEditingLock.ts 已适配实际路径
- **后端 stale-summary 端点已新建**：`backend/app/routers/stale_summary.py`，用 `WorkingPaper.prefill_stale` 字段 + join WpIndex 取 wp_code/wp_name，注册在 router_registry.py §18
- **通知端点已新建**：`backend/app/routers/notifications.py`（GET list / GET unread-count / POST read / POST read-all / DELETE），注册在 router_registry.py §23；修复登录后 Dashboard 两个 "Not Found" toast
- **start-dev-log.bat 已创建**：带日志输出的启动脚本（后端→backend_dev.log，前端→frontend_dev.log），便于排查运行时错误
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
- **ledger-import-unification spec 实施进度（2026-05-08）**：Sprint 1-4 全部完成（76/76 task），跳过 Sprint 0（外部依赖）、AI 兜底（53a-d）、UAT（82/83）、可选文档（84/85）；剩余 Sprint 5 测试任务约 8 个
  - Sprint 1 产出（20 task）：`backend/app/services/ledger_import/` 完整骨架（24 文件）+ detection_types.py（9 schema + KEY_COLUMNS/RECOMMENDED_COLUMNS 单一真源）+ errors.py（31 错误码 + make_error 工厂）+ detector.py（detect_file 支持 xlsx/csv/zip + 合并表头 + 标题行跳过）+ encoding_detector.py（BOM→候选→chardet→latin1）+ year_detector.py（5 级优先识别）+ identifier.py（3 级识别 + 置信度聚合 + detection_evidence 决策树）+ 7 适配器（yonyou/kingdee/sap/oracle/inspur/newgrand/generic）+ AdapterRegistry + JSON hot-reload + 19 单测（test_detector + test_identifier + test_adapters）
  - Sprint 2 产出（21 task）：excel_parser/csv_parser/zip_parser（50k chunk 流式）+ aux_dimension（7 格式 + 多维 + detect_aux_columns）+ merge_strategy（auto/by_month/manual + dedup_rows）+ column_mapping_service（CRUD + 跨项目复用 + build_fingerprint）+ ImportColumnMappingHistory ORM model + writer.py（build_raw_extra 8KB 截断 + prepare_rows_with_raw_extra + write_chunk + activate_dataset）+ aux_derivation.py（主表→辅助表分流）+ ledger_raw_extra.py 端点（LATERAL jsonb_each_text 聚合）+ validator.py（L1 分层校验 + L2 借贷平衡/年度/科目 + L3 余额=序时累计/辅助科目一致 + evaluate_activation force 门控）+ 2 Alembic 迁移（column_mapping_history 表 + 四表 raw_extra 列）
  - Sprint 3 产出（15 task）：orchestrator.py（detect/submit/resume 三阶段编排）+ ledger_import_v2.py 路由（6 端点：POST detect/submit + GET stream/diagnostics + POST cancel/retry）+ import_job_runner.py `_execute_v2` 分支（feature flag 驱动）+ feature_flags `ledger_import_v2: False` + EventType.LEDGER_IMPORT_DETECTED 已确认存在 + router_registry §24 注册 v2+raw-extra 路由 + import_recover_worker 已满足超时恢复
  - Sprint 4 产出（20 task）：9 个 Vue 组件（LedgerImportDialog/UploadStep/DetectionPreview/ColumnMappingEditor/ImportProgress/ErrorDialog/DiagnosticPanel/MappingDiff/ImportHistoryEntry）+ ledgerImportV2Api.ts（API service）+ useLedgerImport.ts（composable，含 sessionStorage 缓存 + localStorage chunk 持久化）+ apiPaths.ts 新增 7 个 v2 路径 + vue-tsc 0 错误
  - **后端全链路（Sprint 1-3）+ 前端全链路（Sprint 4）已完成**
  - 剩余 Sprint 5：Tasks 74-86（测试），约 8 coding task
  - 技术决策：SAP 适配器 filename regex 用 `(?<![A-Za-z])SAP(?![A-Za-z])` 替代 `\bSAP\b`（Python `\b` 视 `_` 为 word char）；identifier.py 新增 `default_aliases()` 公共函数供 GenericAdapter 消费；vendor 适配器统一在 `adapters/__init__.py` 注册（避免循环 import）；validate_l2 用 raw SQL 查 staged 数据（按 dataset_id 过滤）；L2_LEDGER_YEAR_OUT_OF_RANGE 是唯一不可 force-skip 的 L2 码；raw_extra 端点用 PG `LATERAL jsonb_each_text` 高效聚合；DatasetService.activate 通过 writer.activate_dataset 薄包装暴露给 ledger_import 模块；SSE 用独立 async_session 每 2s 轮询（避免 request-scoped session 关闭问题）；import_job_runner._execute_v2 是骨架（full pipeline wiring 待集成）；EventType 枚举中 LEDGER_IMPORT_DETECTED/SUBMITTED/FAILED/VALIDATED/ACTIVATED/ROLLED_BACK 6 个事件已全部存在（Phase 17 预注册）
  - **encoding_detector.py 真实样本修复（2026-05-08）**：(1) `_PROBE_BYTES` 从 4KB 增大到 64KB（GBK 双字节在 4KB 边界截断导致 decode 失败）；(2) `latin1` 从 `_CSV_ENCODING_CANDIDATES` 移除（它能 decode 任何字节序列，掩盖真实编码）；(3) chardet CJK 阈值从 0.7 降到 0.3（chardet 对 GBK 短文本常给 0.3-0.5 但结果仍正确）；修复后 411MB GBK CSV 正确识别为 gb18030
  - **真实样本验证结果**：`数据/` 目录含重庆医药集团两家子企业样本——YG36 四川物流（1 xlsx 含余额表+序时账 22717 行）+ 和平药房（1 余额表 xlsx 50463 行 + 2 CSV 序时账共 411MB）；验证发现：(a) 序时账识别率 100%（ledger conf=95, key cols 全命中）；(b) 余额表合并表头（2 行标题横幅 + 2 行合并表头"年初余额.借方金额"）解析不完整导致 key cols 0/0（需增强 _detect_header_row 对 4 行表头的支持）；(c) sheet 名为 "sheet1" 时 L1 无法命中，需依赖 L2 表头特征
  - **Sprint 5 待修复问题**：(1) 合并表头增强——当前只支持 1 行标题+2 行合并，真实样本有 2 行标题+2 行合并（共 4 行 before data）；(2) 模糊匹配对短列名（"状态"/"过账"）误报为 debit_amount，需收紧 _MIN_SUBSTR_ALIAS_LEN 或加排除词表
  - **v2.1 架构演进方向（已写入 design §28 + requirements 需求 2 验收标准 8-11 + tasks 74a-d）**：(1) L1/L2/L3 并行联合打分（权重 0.2/0.5/0.3 可配置）替代串行降级；(2) 合并表头通用算法（基于行间值多样性而非硬编码阈值）；(3) 列内容验证器（date/numeric/code 三种，header_conf×0.7 + content_conf×0.3）；(4) 识别规则声明式 JSON 配置（热加载+用户自定义）。实施路径：Phase A+B 在 Sprint 5 落地，Phase C+D 在 UAT 迭代推进
  - **v2.2 序时账增量追加（已写入 design §29 + requirements 需求 22）**：预审导 1-11 月序时账，年审只追加 12 月；余额表始终全量覆盖；增量模式下系统自动做期间 diff（file_periods - existing_periods），只导入新增月份的行；重叠月份弹窗确认跳过/覆盖；回滚粒度为按期间删除。Phase B 下一轮迭代实施
  - **真实样本 9 家子企业**（`数据/` 目录）：四川物流（1xlsx 2sheet）、四川医药（1xlsx）、宜宾大药房（1xlsx）、和平药房（1余额xlsx + 2序时csv 按日期段拆）、和平物流（1xlsx）、安徽骨科（1xlsx）、辽宁卫生（2xlsx 分开）、医疗器械（2xlsx 分开）、陕西华氏（1余额 + 12月度序时账）；覆盖了单文件多sheet、多文件分开、CSV大文件、按月拆分等所有场景
  - **9 家样本批量验证结果（2026-05-08 修复后）**：全部 9 sheet ✅ 识别成功（0 unknown）——四川物流（balance 60 + ledger 63）、宜宾大药房（balance 60 + ledger 78）、和平药房余额（balance 53）、辽宁余额（balance 53）、器械余额（balance 53）、陕西华氏 2024（balance 53）、陕西华氏 2025（balance 53）；大文件（>10MB）因耗时跳过但逻辑相同
  - **P0 bug 已修复（read_only 回退 + 合并表头子列重复模式）**：(1) `_detect_xlsx` 新增 `_detect_xlsx_with_mode` 辅助函数，先 read_only=True 尝试，检测到行宽 ≤ 2 时自动回退 read_only=False；(2) `_detect_header_row` 合并判定新增第三条件：下行 unique ≥ 2 + fill ≥ 0.5 + non_empty > unique×2（典型"借方/贷方"重复子列模式）；修复后陕西华氏余额表正确返回 14 列 + 合并表头"年初余额.借方金额"等 家样本批量验证结果（2026-05-08 修复后）**：全部 9 sheet ✅ 识别成功（0 unknown）——四川物流（balance 60 + ledger 63）、宜宾大药房（balance 60 + ledger 78）、和平药房余额（balance 53）、辽宁余额（balance 53）、器械余额（balance 53）、陕西华氏 2024（balance 53）、陕西华氏 2025（balance 53）；大文件（>10MB）因耗时跳过但逻辑相同
  - **P0 bug 已修复（read_only 回退 + 合并表头子列重复模式）**：(1) `_detect_xlsx` 新增 `_detect_xlsx_with_mode` 辅助函数，先 read_only=True 尝试，检测到行宽 ≤ 2 时自动回退 read_only=False；(2) `_detect_header_row` 合并判定新增第三条件：下行 unique ≥ 2 + fill ≥ 0.5 + non_empty > unique×2（典型"借方/贷方"重复子列模式）；修复后陕西华氏余额表正确返回 14 列 + 合并表头"年初余额.借方金额"等
  - **复盘 P0-P2 已全部修复（2026-05-08）**：(1) P0 合并表头语义映射：新增 `_match_merged_header` + `_MERGED_HEADER_MAPPING` 配置表，dot-notation 列名精确映射到 closing_debit/opening_credit 等；`_score_table_type` 新增 alternatives 逻辑（opening_debit+opening_credit 替代 opening_balance）；`_detect_by_headers` 将 alternatives 组成字段 tier 提升为 key；(2) P1 文件名 L1 信号：`identify` 中 sheet 名无信号时自动从 file_name 提取 L1（置信度 -10）；(3) P2 子串匹配最长优先：收集所有命中后选最长别名。修复后 key_rate 从 80%→129%（8/9 满分），conf 从 avg 57→71，全部升级到 medium
  - **Sprint 5 测试完成（2026-05-08）**：新增 91 个测试（从 31→91），覆盖 detector/identifier/validator/raw_extra/aux_dimension/adapters 全链路，1.22s 全部通过；Task 74/75/75a/76/77/78 已完成；剩余 Task 79-81（需 PG 环境）+ Task 82-83（UAT 需真人）
  - **~~四川物流序时账已知问题~~已修复**：`looks_like_data_row` 增强三条件（第一值是整数序号 / 含日期格式 / 含金额格式），修复后四川物流+和平药房 CSV 的 debit_amount 都正确识别
  - **大文件支持已实现（2026-05-08）**：新增 `detect_file_from_path(path)` 入口，CSV 只读前 64KB 编码探测 + 流式读前 20 行（392MB GBK CSV 探测 <10ms / 内存 <1MB）；xlsx 直接传路径给 openpyxl 不读入内存；ZIP 仍需全量读取
  - **最终验证（2026-05-08）**：9 家企业全部 sheet 关键列 5/5 命中，表类型 0 误判，置信度 avg 72-78（medium），91 测试零回归
  - **v1→v2 整合完成（2026-05-08）**：(1) 新建 `converter.py`（~250 行）从旧引擎提取 convert_balance_rows/convert_ledger_rows 适配 v2 数据结构；(2) `orchestrator.py` 重构提取 `_finalize_detection` + 新增 `detect_from_paths`；(3) `__init__.py` 统一导出 ImportOrchestrator/detect_file/detect_file_from_path/convert_*/类型定义；(4) 旧 `smart_import_engine.py` 顶部标记 deprecated + 迁移路径注释（不改功能代码）
  - **v2 模块最终结构（25 个 Python 文件）**：detector/identifier/converter/orchestrator/writer/validator/aux_dimension/aux_derivation/merge_strategy/year_detector/encoding_detector/column_mapping_service/content_validators/detection_types/errors + adapters/(7家+registry+json_driven) + parsers/(excel/csv/zip)；统一入口 `from app.services.ledger_import import ImportOrchestrator`
  - **迁移 P0 已完成（2026-05-08）**：`_execute_v2` 全链路实现（detect→parse→convert→validate→write→activate），含流式解析（iter_excel/csv_rows_from_path）、L1 校验、activation gate、bulk insert 5000/batch、rebuild_aux_balance_summary；写入阶段暂复用旧引擎的 `_clear_project_year_tables`（后续迁移到 writer.py）
  - **parsers 新增 path-based 入口**：`iter_csv_rows_from_path(path, encoding, ...)` 和 `iter_excel_rows_from_path(path, sheet_name, ...)` 支持 600MB+ 文件流式解析不全量读入内存
  - **`_execute_v2` 上线前必修已全部完成（2026-05-08）**：(1) 边解析边写入（`_insert_balance/_insert_aux_balance/_insert_ledger` 三个辅助函数，每 chunk 立即 insert，内存从 440MB→10MB）；(2) 辅助表分流（aux_balance 正确写 TbAuxBalance）；(3) 参数超限修复（INSERT_CHUNK_SIZE 从 5000 降到 1000，14×1000=14000 << PG 65535 上限）；(4) col_mapping fallback（confirmed 为空时退回 auto-detection）；(5) 进度精度用 total_est_rows 全局估算（多 sheet 不跳变）；(6) 日志增强（每 sheet 开始/完成 logger.info）
  - **`_execute_v2` 剩余建议修复**：raw_extra 列写入 + 年度验证 warning + Dataset 两阶段切换 + 辅助序时账 _aux_dim_str 拆分
  - **Worker 健壮性已增强（2026-05-08）**：(1) 异常处理 3 次重试 DB transition + 独立 try 保证 release_lock（防止 job 永远停在 running）；(2) 每 chunk 调 `_persist_progress` 自动更新 heartbeat_at（防 20min stale 超时）；(3) 每 5 chunk 检查 job.status==canceled（支持用户取消）
  - **Phase 重排**：Phase 3 合并 Parse+Convert+Validate+Write 流式执行；Phase 4 Activation gate 降级为警告（数据已流式写入无法阻止）；Phase 5 独立 rebuild_aux_summary；Phase 6 result_summary 新增 aux_balance_rows + blocking_findings 字段
  - **feature_flag 已切换为默认 True（2026-05-08）**：`feature_flags.py` 中 `ledger_import_v2: True`（maturity: production），所有项目默认走 v2 引擎；旧引擎代码保留但不再执行，可通过 `set_project_flag(pid, "ledger_import_v2", False)` 单项目回退
  - **v2 真实导入测试发现（2026-05-08）**：detect/identify/parse 全链路本地验证通过，worker 执行时 job 卡在 running/progress=1%。根因链路：(1) bulk insert 缺 `id` UUID 主键；(2) insert values 漏 `company_code` NOT NULL 字段（tb_balance/tb_aux_balance/tb_ledger 都是必填，converter 返回正确但 insert 没传递）。全部已修复：三个 insert 函数都加了 `"id": uuid4()` + `"company_code": r.get("company_code") or "default"`
  - **`_execute_v2` 关键列必填清单**：tb_balance/tb_aux_balance/tb_ledger 的 `company_code` 是 NOT NULL，converter 默认值 "default"，insert 必须传递该字段；tb_aux_balance 的 `aux_type` 也是 NOT NULL，converter 必须跳过 aux_type=None 的无效维度条目
  - **辅助明细账 tb_aux_ledger 已补齐（2026-05-08）**：此前 `_execute_v2` 只写 tb_ledger 漏写 tb_aux_ledger；现已补全：(1) `convert_ledger_rows` 返回值改为 `(ledger, aux_ledger, stats)` 3 元组，对齐旧 `write_four_tables` 逻辑；(2) `_execute_v2` 新增 `_insert_aux_ledger` 函数（完整字段含 aux_type/aux_code/aux_name/aux_dimensions_raw/voucher_type/accounting_period）；(3) ledger sheet 处理同时写主表+辅助明细账；(4) `convert_balance_rows` 辅助余额行加回 `aux_dimensions_raw` 溯源字段
  - **aux_dimension 格式升级（2026-05-08）**：PATTERNS 新增 `colon_code_comma_name` 格式（`类型:编码,名称`，优先于 `colon_code_name`），识别 YG36 真实数据"金融机构:YG0001,工商银行"；`parse_aux_dimension` 智能逗号分隔：只在"逗号后接 `类型:`"时切多维度，避免误切单维度"类型:编码,名称"；PATTERNS 从 7 个增到 8 个；测试覆盖 97 tests / 0 failures（含新建 `test_aux_ledger_split.py` 6 用例）
  - **辅助明细账复盘遗留（P0-P3）**：P0 必做 = 真实样本（YG36 xlsx）端到端 v2 worker smoke test + 断言 tb_aux_ledger 有数据；P0 = `_insert_aux_ledger` 空值策略审查（aux_code/summary 空值应 NULL 不 ""）；P1 = converter 和 aux_derivation 辅助拆分逻辑合一（当前 aux_derivation.py 未被 `_execute_v2` 调用，两套职责重叠）；P1 = 三个 `_insert_*` 独立 session+commit，失败恢复不如旧引擎单事务，考虑改 savepoint；P2 = colon_code_comma_name 的 name 组贪婪吃到行尾，需要边界测试
  - **真实样本 2 bug 修复（2026-05-08）**：(1) `writer.prepare_rows_with_raw_extra` 多列映射到同一 standard_field 时后者会覆盖前者，真实数据"核算维度"+"主表项目"都映射到 aux_dimensions 导致后者 None 覆盖前者有效值，aux_ledger=0；修复为首个非空值保留策略；(2) `excel_parser.iter_excel_rows_from_path` read_only=True 模式对部分 xlsx（合并表头/特殊样式）返回 0 行，加 `_iter_excel_chunks` 辅助函数 + read_only=False 自动回退（bytes 版本 `_iter_excel_bytes_chunks` 同步修复）；影响修复：和平药房/陕西华氏/辽宁/医疗器械余额表全部恢复解析；9 家企业真实样本抽样 5000 行/sheet 验证：辅助维度识别到 20+ 种（客户/金融机构/成本中心/银行账户/税率 等），aux_ledger 从 0~104 升到 6000~15000 不等
  - **和平物流余额表识别 bug（遗留）**：`和平物流25加工账-药品批发.xlsx` 的"余额表" sheet 被误识别为 ledger(conf=34)，sheet 名命中 balance 但 L2 表头置信度打分让 ledger 胜出；根因是该 sheet 含大量非标准列（编码长度/业务循环/底稿项目等 8 列），和常规余额表结构差异较大。下轮修复
  - **ledger_import 模块 import 规约（2026-05-08 踩坑）**：`backend/app/services/ledger_import/` 内部文件之间必须用相对 import `from .xxx import ...`，**禁止**用 `from backend.app.services.ledger_import.xxx import ...`；后端启动时 PYTHONPATH 根是 `backend/` 不是仓库根，写 `backend.app.xxx` 会导致 runtime `ModuleNotFoundError: No module named 'backend'`；v2 worker 首次上线连续 2 次 failed 就是 merge_strategy.py 这一行错误 import 引起（已修复）；Docstring 示例可保留 `backend.app...` 格式（纯字符串不参与 import 解析）
  - **账表导入全链路整体复盘（2026-05-08）架构清洁待办**：(1) `aux_derivation.py` 是死代码，`_execute_v2` 没调用，职责和 converter 重叠，可删；(2) `smart_import_engine.py` 标记 deprecated 但仍被 `_execute_v2` 调用 `_clear_project_year_tables`，需迁移到 writer.py 后才能删；(3) `_execute_v2` 拆出到 `ledger_import/orchestrator.py`，不留在 import_job_runner.py；(4) adapter 机制（8 家 json 适配器）实际未被调用也没增益，要么删要么改为纯别名包；(5) `iter_excel_rows` 和 `iter_excel_rows_from_path` 双实现底层可共用
  - **账表导入功能遗留断点清单**：(a) staged/active 切换未真正走通——`_execute_v2` 直接写活数据没调 `activate_dataset`，design §12 原子激活未落地；(b) incremental 只做了 detect 没做 apply——"只追加新月份"核心功能缺失；(c) `ledger_data_service.delete` 是硬删不是软删，失误无法恢复；(d) `prepare_rows_with_raw_extra` 多列映射同字段时丢弃列值完全丢失不进 raw_extra；(e) 空值策略不统一——aux_code/aux_name 填空串，summary/preparer 为 None，审计穿透时查询语义矛盾；(f) 进度条轮询 `ImportQueueService` 是内存态，后端重启就丢，应轮询 import_jobs 表；(g) 识别失败时前端无手动改 table_type 入口；(h) 辅助维度类型重名冲突（"税率"同时出现在客户/项目下），tb_aux_ledger 只存 aux_type 不区分上下文
  - **v2 引擎 UAT 工作流沉淀**：纯单测 100/100 ≠ 真实数据可用（v2 worker 首次上线因 import 错误连续 2 次 failed 但单测全过）；下轮流程硬约束：(1) 每轮 spec 交付前必须跑一次 9 家真实样本抽样 5000 行验证（5 分钟可完成）；(2) CI 加一个"YG36 端到端 smoke"固定回归（前端上传 → worker 执行 → PG 查 aux_ledger > 0）；(3) 单纯"代码文件存在"/"单测通过"不是验收标准，必须有真实 PG 入库行数断言
  - **Sprint 6 Part 1 完成（2026-05-08，9/20 项）**：(S6-1) 删除 aux_derivation.py 死代码；(S6-2) `_clear_project_year_tables` 从 smart_import_engine 迁到 writer.clear_project_year；(S6-4) `_execute_v2` bootstrap try/except 兜底 + result_summary["phase"]="bootstrap_import"；(S6-5) 5 个 Phase 入口结构化日志；(S6-6) 多对一映射丢弃列保留到 `raw_extra["_discarded_mappings"]`；(S6-7) aux_code/aux_name 空值改 NULL 不填空串；(S6-9) L1 强信号锁定（score ≥ `MATCHING_CONFIG.l1_lock_threshold` 默认 85 时 L1 胜过 L2，修复和平物流"余额表"被误识别为 ledger）；(S6-10) `test_real_samples_smoke.py` 2 用例（和平物流 + YG36）；(S6-11) excel_parser bytes/path 合并 `_iter_from_workbook` + `_iter_with_fallback` 底层共用；测试 102/102 通过；commit d8ac536 推送到 feature/round8-deep-closure
  - **Sprint 6 Part 2 待办（下轮，11 项）**：(S6-3) `_execute_v2` 迁到 `ledger_import/orchestrator.py` 3h；(S6-8) 辅助维度三元组查询端点（解决"税率"跨客户/项目重名）2h；(S6-12) xlsx forward-fill 可选策略 2h；(S6-13) staged 模式事务边界（dataset_id 失败整包 rollback）3h；(S6-14) rebuild_aux_summary 加 dataset_id 过滤 1h；(S6-15) `ledger_data_service.apply_incremental` 真正按期间追加 3h；(S6-16) 前端增量追加 Tab 打通 1.5h；(S6-17) `test_execute_v2_e2e.py` 集成测试 3h；(S6-18) CI v2 smoke step 0.5h；(S6-19/20) 针对性测试扩展 2h
  - **Sprint 6 Part 2 完成（2026-05-08，11/11）**：(S6-8) 三元组查询 `get_aux_by_triplet` + `GET /api/projects/{pid}/ledger/aux/by-triplet` + Alembic `idx_tb_aux_ledger_triplet` partial index；(S6-12) `iter_excel_rows_from_path` 新增 `forward_fill_cols` 参数，`_execute_v2` 对 account_code/account_name 列自动启用合并单元格向下填充；(S6-13) Staged 模式落地：`_execute_v2` 先 `DatasetService.create_staged` → 4 张表 insert 带 `dataset_id=staging_id` + `is_deleted=True` → gate 通过后 `activate_dataset` 原子切换 / gate 阻塞或异常时 `mark_failed` 清理；删除 `clear_project_year` 调用；(S6-14) `rebuild_aux_balance_summary` 新增可选 `dataset_id` 参数；(S6-15) `ledger_data_service.apply_incremental` 实现 skip/overwrite 两种重叠策略（overwrite 真删重叠月份的 tb_ledger/tb_aux_ledger）；(S6-16) `POST /incremental/apply` 端点 + LedgerDataManager Tab 3 加"检测差异"/"执行清理"按钮；(S6-17) `test_execute_v2_e2e.py` 2 用例（YG36 真实样本完整管线，SQLite 内存库，断言四表行数/17 种维度类型/S6-7 空值策略/S6-13 dataset_id 绑定）；(S6-18) CI 新增 `ledger-import-smoke` job；(S6-19/20) 6 个针对性测试（丢弃列边界 3 + 三元组查询 4）；(S6-3) `_execute_v2` 数据管线迁到 `orchestrator.execute_pipeline()`，runner 从 1094 行→573 行（-48%），orchestrator 从 255→709 行；121/121 测试全通过；commits d8ac536 / cb6653c / a461a2d / 1e8b83d 推送
  - **Sprint 6 关键技术决策**：(1) `_execute_v2` 薄包装策略——Worker 只管状态机+锁+artifact，数据流全放 orchestrator，未来换调度器（Celery/RQ）只需改 runner 层；(2) `execute_pipeline` 接收 `progress_cb` + `cancel_check` 异步回调，抽象 Worker 细节，pipeline 不依赖 ImportJobService；(3) Staged 原子激活强制使用 `is_deleted=True` + `dataset_id=staging_id` 双保护，`activate_dataset` 切换后自动 superseded 旧 dataset；(4) 三元组查询多 aux_code 求和时必须用 Decimal 累加不能 float；(5) E2E 测试关键点：SQLite UUID 存 hex 无连字符（查询需 `str(uuid).replace("-","")`）、JSON 序列化需自定义 default 处理 datetime、参数批大小 22 字段×40 行=880 < SQLite 999 上限；(6) L1 锁定置信度直接用 l1_score 不做加权归一化（`MATCHING_CONFIG.l1_lock_threshold` 默认 85 可配）；(7) `_smart_comma_split` 的 lookahead 模式 `,(?=[^:：,，]+[:：])` 只在"逗号后接 `类型:`"时切多维度
  - **TbAuxLedger raw_extra 字段补齐（踩坑）**：Alembic 迁移早已给 PG 4 张表加了 `raw_extra JSONB` 列，但 ORM 模型 `TbAuxLedger` 独缺该字段声明，导致 `insert(TbAuxLedger).values(..., raw_extra=...)` 触发 SQLAlchemy `CompileError: Unconsumed column names: raw_extra`；修复 = 给模型补 `raw_extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`
  - **Sprint 6 流程沉淀**：(1) 大改动拆三批 commit（Part 1/2a/2b+2c），每批 121 测试全绿后才做下一批；(2) E2E 断言"真实 PG 入库行数"+"维度类型分布"比单测更有效；(3) orchestrator 迁移用 Python 脚本精准删除重复代码段（find new_end_line/old_except_line 两个 marker 之间整块删除），避免手工引入语法错误；(4) CI 新增 smoke job 用 `数据/` 目录做可选真实样本回归（缺失则 skip）
  - **Sprint 7 规划（UX+运维，10 项）**：软删除回收站 / LedgerDataManager 多入口挂载 / 前端手动改 table_type / raw_extra GIN 索引 / 进度条改轮询 import_jobs 表 / L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / adapter 机制取舍
  - **Sprint 7 补充待办（Sprint 6 复盘新增，11 项）**：P0=9 家真实样本参数化 E2E（当前只跑 YG36 1 家）；P0=`writer.bulk_insert(table, rows, dataset_id, project_id, year)` 抽象合并 4 个 `_insert_*` 重复闭包；P0=空值策略全量审计（summary/preparer/voucher_type 等仍可能 None vs 空串不一致，当前只修了 aux_code/aux_name）+ 字段规约文档；P0=Alembic 迁移 upgrade→downgrade→upgrade 循环测试；P1=最小合成样本放 `backend/tests/fixtures/` 让 CI smoke 必跑（当前 CI 找不到 `数据/` 目录会 skip）；P1=orchestrator 拆三文件（pipeline.py 主流程 / pipeline_insert.py insert helpers / api.py ImportOrchestrator 类）；P1=integration test 补 10 个（pipeline × runner × PG 真实库）；P1=incremental apply 合并到 submit 阶段（消除前端两步"先清理再上传"体验断裂）；P2=`docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 架构文档（回调契约/PipelineResult/staged 激活流程图）；P2=前端 playwright 最小 E2E UI 测试；P3=commit message 加"验证等级"标注规范（unit/E2E/smoke/manual/not verified）
  - **Sprint 7 轮 1 完成（2026-05-09，4/21）**：(S7-1) `test_9_samples_e2e.py` 参数化 10 用例覆盖全部 9 家企业（抽 1000 行/sheet，~3 分钟跑完），和平物流余额表跨样本验证 S6-9 L1 锁定；(S7-2) `writer.bulk_insert_staged(db_session_factory, table_model, rows, ...)` 通用函数替代 4 个重复 insert 闭包，按 `table_model.__table__.columns` 自省过滤字段 + 自动注入 id/project_id/year/dataset_id/is_deleted 公共字段，orchestrator.py 从 709 行降到 580 行（-18%）；(S7-3) `backend/tests/fixtures/ledger_samples/minimal_balance_ledger.py` 生成最小合成样本（合并表头+8 行 balance+6 行 ledger+核算维度），`test_minimal_sample_smoke.py` 4 用例 0.45s 跑完，CI smoke 主步骤不再依赖真实 `数据/`；(S7-4) converter 里 account_name `""` 改 None（所有表 nullable 字段统一用 None），writer.bulk_insert_staged 同步删除 account_name "" 兜底；125/125 主套测试 + 10/10 E2E 通过；commit b29b7b9 推送
  - **bulk_insert_staged 设计决策（S7-2）**：关键是"按模型列自省过滤"——converter 产出的 row 字典可能含 TbLedger 没有的 aux_type/aux_code（converter 统一 key），但 insert 时 `valid_cols = {c.name for c in table_model.__table__.columns}` 过滤一遍只保留匹配字段；公共字段（id/project_id/year/dataset_id/is_deleted）强制覆盖，NOT NULL 兜底（company_code/currency_code）有 fallback 值；这种设计让未来新增字段只改 converter + ORM，无需改 insert 函数
  - **CI smoke 两层策略（S7-3 沉淀）**：第一层"最小合成样本 smoke"（4 用例，0.45s，必跑）作为质量门禁；第二层"真实 9 家样本 E2E"（10 用例，~3min，可选跑，数据/ 缺失时 `|| true` 跳过）作为深度回归；两层都挂在 `ledger-import-smoke` CI job；下轮可考虑把合成样本放 Docker image 让 E2E 也必跑
  - **Sprint 7 轮 2 完成（2026-05-09，3/21，累计 7/21）**：(S7-6) `orchestrator.py` 拆出 `pipeline.py`（346 行，含 execute_pipeline/PipelineResult/ProgressCallback/CancelChecker），orchestrator.py 从 705 行→361 行只保留 ImportOrchestrator 类，保留 re-export 向后兼容；(S7-8) `test_alembic_migrations.py` 5 用例（3 个 round-trip 需 PG skip + 2 个拓扑/静态检查本地跑）；(S7-5) `test_bulk_insert_staged.py` 8 用例覆盖字段自省/公共字段注入/NOT NULL 兜底/空 rows/分 chunk 等边界；135/135 主套通过；commit a3add4a 推送
  - **Alembic 迁移目录硬 bug（S7-8 重大发现）**：Sprint 2 以来 4 个迁移文件被错放在 `backend/app/migrations/`（仅 sql 脚本+历史遗留位置），而 Alembic `script_location = alembic`（→ `backend/alembic/versions/`），导致这些迁移**从未被 Alembic 执行过**：(1) `ledger_import_column_mapping_20260508`（import_column_mapping_history 表）；(2) `ledger_import_raw_extra_20260508`（4 张表 raw_extra JSONB 列）；(3) `ledger_import_aux_triplet_idx_20260508`（三元组 partial index）；(4) `round7_clients_20260508`（clients + project_tags）。修复 = 4 个文件移到 `backend/alembic/versions/` + 修 `round7_clients` 的 down_revision 从 `round7_section_progress_gin`（缺日期后缀）改为 `round7_section_progress_gin_20260507`。生产环境需审计：这些 schema 对象可能靠 `_init_tables.py` create_all 或手动 ALTER TABLE 补上，纯靠 Alembic 增量升级的环境会缺
  - **Alembic 迁移目录规约**：所有 Python 迁移文件必须放 `backend/alembic/versions/`，不能放 `backend/app/migrations/`（后者只留 SQL 脚本类的历史遗留，如 phase12_001_*.sql）；CI 拓扑检查 `test_no_stray_migrations_in_app_migrations` 会扫 app/migrations/ 下是否有含 `revision =` 和 `down_revision =` 的 .py 文件，有即失败
  - **pipeline.py 架构沉淀（S7-6）**：文件边界=职责边界。`orchestrator.py` 只放 ImportOrchestrator 类（detect/submit/resume 三阶段 API，供路由调用）；`pipeline.py` 只放数据管线 `execute_pipeline` + `PipelineResult` + 回调类型（供 Worker 调用）；runner 直接 `from app.services.ledger_import.pipeline import execute_pipeline`，不再走 orchestrator 中转
  - **Sprint 7 轮 3 完成（2026-05-09，2/21，累计 9/21）**：(S7-9) submit 端点新增 `incremental/overlap_strategy/file_periods` 字段，incremental+overwrite 时 submit 前自动调 `apply_incremental` 清理旧月份（一步到位，消除前端两步体验断裂）；(S7-10) `delete_ledger_data` 默认改软删（UPDATE is_deleted=true）+ 新增 `hard_delete=True` 参数 + `restore_ledger_data` 恢复函数 + `list_trash` 回收站列表 + 路由 GET /trash + POST /restore + apiPaths 新增 trash/restore；135/135 测试通过；commit b3e0dfe 推送
  - **Sprint 7 剩余 12 项（P2-P3，下轮继续）**：integration test 补齐 10 个（需 PG）/ 前端手动改 table_type / raw_extra GIN 索引 / 进度条改轮询 import_jobs / L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric / 大文件性能 CI 门禁 / adapter 机制取舍 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 轮 4 完成（2026-05-09，+3，累计 12/21）**：(1) Alembic 迁移 `ledger_import_raw_extra_gin_20260509`——4 张表 raw_extra 列加 GIN partial index（WHERE raw_extra IS NOT NULL），支持 @>/?/?| JSONB 操作符走索引；(2) 进度条持久化——后端新增 `GET /api/projects/{pid}/ledger-import/jobs/latest`（优先返回活跃 job，无活跃则返回最近 5 分钟完成/失败的，无 job 返回 idle），前端 ThreeColumnLayout.vue pollImportQueue 改调新端点（后端重启不再丢状态）；(3) 前端手动改 table_type 确认已在 Sprint 4 的 DetectionPreview.vue 实现（el-select v-model="row.table_type"），无需额外改动；135/135 测试通过；commit cbc3c84 推送
  - **Sprint 7 剩余 9 项（P2-P3，可选做）**：integration test 补齐 10 个（需 PG，CI 里跑）/ L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric / 大文件性能 CI 门禁 / adapter 机制取舍 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 轮 5 完成（2026-05-09，+3，累计 15/21）**：(1) L2/L3 容差动态化——validator BALANCE_LEDGER_MISMATCH 从固定 1.0 元改为 `min(1.0 + magnitude × 0.00001, 100.0)`（小金额仍约 1 元，亿级最高 100 元，避免浮点精度误报）；(2) force_activate 审批链——pipeline.py 在 force+blocking 时记录 `force_skipped_findings` 到 validation_summary（ActivationRecord 含完整审计轨迹，后续可查"哪些项目强制跳过校验"）；(3) adapter 机制精简——orchestrator 不再调 `detect_best` 自动匹配（真实 9 家从未触发），仅用户显式传 adapter_hint 时才赋 adapter_id，adapter 目录保留作别名包（identifier.default_aliases() 仍从 JSON 读取）；135/135 测试通过；commit beff660 推送
  - **Sprint 7 剩余 6 项（P3，留给后续按需触碰）**：integration test 补齐 10 个（需 PG）/ 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 收尾（2026-05-09，累计 16/21）**：新增 `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md`（176 行，含模块总览/数据流/7 个设计决策/回调契约/PipelineResult 字段/Alembic 迁移链/测试策略/已知限制）；commit 9b4b15d 推送
  - **Sprint 7 剩余 5 项（P3）**：integration test 补齐 10 个（需 PG）/ 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / 前端 playwright E2E / commit 等级规范
  - **L1 企业级宽容策略（2026-05-10，commit 0fde30f）**：`validate_l1` 从"硬阻断"改为两阶段预检：(1) 整行所有字段都空 → 静默跳过不记 finding（空白/尾部行）；(2) 非 exclusive_pair 的 key col 有空 → 记 `ROW_SKIPPED_KEY_EMPTY` warning + 跳过该行但不阻断激活；`EMPTY_VALUE_KEY` blocking 已下线；AMOUNT/DATE 类型错误原语义保留（值非空但不可解析 → blocking/warning）；真实业务数据无法 100% 干净，少量脏行应"跳过 + 告警"而非整批阻断；新增 `ROW_SKIPPED_KEY_EMPTY` 到 errors.py（severity=warning，tier=key）
  - **9 家真实账套批量验证结果（2026-05-10，7/10 成功）**：`scripts/verify_9_companies_pipeline.py` 参数化 10 用例（9 企业 + 陕西华氏拆 2024/2025），按文件大小排序便于快速暴露问题；已通过：YG36 四川物流（39s）/ YG2101 四川医药（1153s，128MB）/ YG4001 宜宾大药房（15s）/ 和平物流（79s，本轮修复后）/ 安徽骨科（592s）/ 辽宁卫生（791s）/ 医疗器械（407s）；未完成：和平药房（392MB CSV，>20min timeout）/ 陕西华氏 2024（13 文件）/ 陕西华氏 2025（12 文件）——皆为大文件耗时问题非 bug
  - **批量测试踩坑（2026-05-10）**：(1) `ImportJob.project_id` FK 到 `projects`，批量测试脚本必须先建 Project；(2) 直接用 `Project()` ORM 构造触发 SQLAlchemy 关系图解析，未 import 的 `accounting_standards` 模型会抛 `NoReferencedTableError`——改用 raw SQL INSERT 绕过关系图；(3) `start-dev.bat` 已启动的 uvicorn dev server + 脚本共用 DATABASE_URL 时，僵尸脚本进程会持续占用 DB 连接池，跑前务必清理（`Get-Process python` 看 CommandLine 过滤）
  - **YG2101 性能基线**：128MB xlsx 单文件 19 分钟入库 650K 序时账 + 1.35M 辅助序时（openpyxl read_only 模式仍需全量解析）；辽宁卫生 78MB xlsx 13 分钟入库 406K 序时账；大致吞吐量 500-800 行/秒（含 aux 维度解析+PG insert）
  - **和平物流序时账 header 特征**：第 1 行列名为 `[凭证号码]#[日期]` / `[日期]` / `[凭证号码]` 等方括号包裹格式（金蝶/用友之外的某软件规范），detector `_score_table_type` 给了 unknown+conf=0 但 pipeline 仍正常识别（fallback 路径），后续可考虑在 detector `_match_merged_header` 增加"方括号包裹字段名"识别规则提升置信度
  - **前端 UI 端到端链路全通（2026-05-10，commit 7f39990）**：YG36 真实账套从浏览器上传→识别→提交→Worker→入库 25 秒完成（balance 1823 / aux_balance 1730 / ledger 22716 / aux_ledger 25813），status=completed。修复 7 个串联 bug：(1) `import_recover_worker` except 分支没 sleep，异常后立即 while 下一轮（11MB/秒 刷日志死循环）；(2) `ImportJobService.check_timed_out` naive datetime 减 aware heartbeat_at 抛 "can't subtract offset-naive and offset-aware"；(3) `recover_jobs` 缺情况 3：started_at+heartbeat_at 双 NULL 的 running job 永久锁定项目（`active_project_job_exists` 永久 True）；(4) `_execute_v2` Phase 5 `writing → completed` 被状态机拒绝（`_VALID_TRANSITIONS` 要求 writing→activating→completed），需加中间过渡；(5) `ledger_import_v2.py /detect` 只读内存 `await f.read()` 不持久化文件，Worker `_load_file_sources(upload_token)` 找不到 bundle → 改调 `LedgerImportUploadService.create_bundle` + `detect_from_paths`；(6) `orchestrator.submit` 只建 job(status=queued) 不触发 worker，靠 30s recover 轮询才跑 → /submit 端点返回前立即 `ImportJobRunner.enqueue(job_id)`；(7) `orchestrator.submit` 重建 ImportArtifact 与 detect 阶段的 bundle artifact unique 冲突 → 改查已存在复用
  - **e2e_http_curl.py**（本轮新建，保留）：可复用的前端 UI 链路 UAT 脚本（登录 → /detect → /submit → 轮询 active-job → /diagnostics → DB 验证），未来 Worker/orchestrator 改动必须先跑此脚本
  - **前端 UI 链路规约（必须同时满足）**：detect 端点必须持久化文件到 bundle（不是只读内存）；submit 端点必须立即 `enqueue(job_id)`（不能靠 recover 兜底）；pipeline 返回后 Worker 层必须按 `_VALID_TRANSITIONS` 走完整状态机（writing→activating→completed）；except 分支必须 sleep 避免死循环
  - **`httpx.AsyncClient` 多次请求可能遇到 502**（原因未完全定位，可能与 keep-alive 或代理相关），UAT 脚本用 `requests.Session()` 同步客户端更稳定
  - **backend/backend.log 检查技巧**：用 `python -m uvicorn ... 2>&1 | Out-File backend.log -Encoding UTF8` 手动启后端可捕获实时日志；PowerShell `Select-String -Pattern` 需防中文编码破坏，必要时 `Get-Content -Encoding UTF8 -Tail N` 就够
  - **僵尸 running job 危害**：PG 里每个 project_id 只允许一个 active job，任何"status in (running,validating,writing,activating) 但 started_at=NULL heartbeat_at=NULL"的遗留数据都会让后续所有新 job 卡在 queued；DB 重建/代码 reload/手动 kill 后必须清理，否则前端永远跑不通
  - **YG36 真实导入最终修复（2026-05-09 晚，commit b07a17f）**：两处关键 bug 修复后 YG36 端到端 **成功**（balance 1823 / aux_balance 1730 / ledger 22716 / aux_ledger 40122，warnings=0 blocking=0，10+ 维度类型正确识别）：(1) **validator `_EXCLUSIVE_KEY_PAIRS` 语义修正**——此前要求"至少一个金额字段非空"，但真实余额表常见"期初期末均为 0 的零余额行"（新开科目），8 字段合法全空被误报 1398 条 EMPTY_VALUE_KEY blocking；改为"互斥组内所有字段不强制 EMPTY blocking"（允许全空），AMOUNT/DATE 类型检查保留；balance/aux_balance 扩展到 8 字段覆盖分列模式；(2) **`tb_aux_balance_summary` 表缺失**——pipeline 93% 调 rebuild_aux_balance_summary 失败，PG 重建后此表从 baseline 缺失（archived 002 已归档），新建 Alembic 迁移 `ledger_aux_balance_summary_20260509.py`；pytest 145 passed / 3 skipped
  - **balance 表零余额行硬约定**：余额表"期初+本期+期末全 0"的科目行合法（新开未用），L1 不应 blocking；任何关于"金额字段必填"的假设在真实数据面前都站不住脚
  - **Git commit message 中文编码规约（2026-05-09）**：PowerShell 7 默认 console OutputEncoding 是 GB2312（chcp 936），`git commit -F file.txt` 会按 GBK 解码文件内容导致中文乱码；修复 = 提交前 `chcp 65001 > $null` 切 UTF-8 codepage，或 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`；git config `i18n.commitEncoding=utf-8` 也要设，双重保险
  - **Alembic 多 head 时硬约定**：当 `heads` 返回多个分支（如 round4_ocr_fields_cache + ledger_aux_balance_summary），不能直接 `alembic upgrade head`，必须指定具体 revision `alembic upgrade <revision_id>` 或按 branchname@head；本轮遇到 alembic_version 与实际 schema 不一致（word_export_task 表已存在），改用 psycopg2 直接 DDL 补表（一次性脚本用完即删）
  - **PG 重建 baseline 遗漏清单**：`_init_tables.py` 只跑 create_all，历史 archived 迁移中的表（如 `tb_aux_balance_summary`）若被 model 层删除但业务代码仍引用，PG 重建后会缺表；未来 baseline 需对照 `grep -r "CREATE TABLE\|FROM tb_" backend/` 确认 SQL raw 表全覆盖
  - **raw_extra JSONB datetime 序列化修复（2026-05-09 真实导入踩坑）**：真实数据的 raw_extra 字典含 datetime/date 对象（如"到期日"列进了 raw_extra），PG JSONB 列 INSERT 时报 `TypeError: Object of type datetime is not JSON serializable`；修复 = 新增 `_sanitize_raw_extra(extra: dict)` 递归遍历：datetime→isoformat / Decimal→float / 其他非标准→str；在 `build_raw_extra` 返回前 + `bulk_insert_staged` 写入前双重调用确保安全；commit 08594c1
  - **PowerShell 批量修改中文文件的铁律（2026-05-09 踩坑 2 小时）**：**禁止**用 PowerShell 的 `Get-Content -Raw | Set-Content` 或 `-replace` 管道做批量文本替换——PS 默认用 UTF-16 读取后再写回，会把 3 字节 UTF-8 中文字符截断成 2 字节（末字节被吞），文件全是 `\xef\xbf\xbd` replacement char 导致 Vue 模板编译失败。正确做法：**用 Python 字节级操作** `open(path, 'rb') → content.replace(b"...", b"...") → open(path, 'wb')`；或用 `strReplace` 工具。踩坑案例：LedgerDataManager.vue 被损坏 30+ 处中文字符，靠 `git show HEAD~1:file | python` 恢复原始字节再做字节级替换
  - **apiPaths.ts ledger.data vs ledger.import.data 路径结构（2026-05-09 修正）**：`ledger.data.*` 是 `ledger` 的直接子属性（不是 `ledger.import.data`），v2 账表数据管理端点位于 `ledger.data.summary/delete/incrementalDetect/incrementalApply/trash/restore`；LedgerDataManager.vue 一度误用 `ledger.import.data.*` 导致 `Cannot read properties of undefined (reading 'summary')` 运行时错误（commit ee2828a 修正）
  - **FastAPI 路由冲突踩坑（2026-05-09）**：`/jobs/latest` 每 10s 返回 422——因为 `backend/app/routers/ledger_datasets.py` 和 `ledger_import_v2.py` 都挂载在 `/api/projects/{pid}/ledger-import` prefix，前者有 `/jobs/{job_id}`（job_id: UUID）路由会拦截吸收 `"latest"` 作为 UUID 参数解析失败；FastAPI 路由匹配是全局按声明顺序，**不同 router 之间的路由也会冲突**。修复 = 把 `/jobs/latest` 改名 `/active-job` 避开 `/jobs/` 命名空间；commit e4883d0。规约：同一 prefix 下多 router 注册时，literal 路由（如 `/latest`）必须**不能**和 `{var_name}` 通配冲突
  - **L1 校验借贷互斥关键列（2026-05-09 真实导入阻断）**：validator.py 的 L1 把 `debit_amount`/`credit_amount` 都列为 key column，任一为空就 blocking；但真实序时账每行**要么借方有值要么贷方有值不可能同时**，导致 22716 行产生 44000+ blocking errors 阻断 activate。修复 = 新增 `_EXCLUSIVE_KEY_PAIRS: dict[table_type, set[str]]`（目前为 `ledger/aux_ledger: {debit_amount, credit_amount}`），对互斥对至少一个非空即通过，不再 blocking；commit c3bc661。规约：未来新增互斥关键列（如余额表 `opening_debit`/`opening_credit`）加到此字典即可
  - **"数据未入库" debug 方法论沉淀（2026-05-09）**：用户看到"导入失败"时多数是"数据被 staged 写入后 activate gate 阻断清理"而非真没写。排查 3 步：(1) `SELECT COUNT(*) FILTER (WHERE is_deleted=true/false) FROM tb_ledger` 区分 active/staged/trash；(2) `SELECT dataset_id, is_deleted` 看是 v2 staged 残留（有 dataset_id）还是旧引擎残留（dataset_id=NULL）；(3) 看 `import_jobs.error_message` 的真实 error chain—datetime 错误/L1 校验失败/路由 422 是不同层级；staged 数据在 gate 失败时会被 `cleanup_dataset_rows` 硬删，所以"失败后数据为空"是预期行为
  - **PowerShell 批量文本替换铁律**：禁止用 `Get-Content -Raw` + `-replace` + `Set-Content` 对含中文的文件做批量修改——PowerShell 默认把文件当 UTF-16 解码，UTF-8 3 字节中文字符会被破坏成 2 字节（第 3 字节被吞），产生 `\xef\xbf\xbd` replacement char；LedgerDataManager.vue 就是这么坏掉的（30+ 处中文被截断，Vue 模板编译直接崩）；正确做法：**必须用 Python `open(path, 'rb')` 字节级读写**，再用 `content.replace(b'old', b'new')`；commit 6a2150e 修复（从 git HEAD~1 取原始字节重做替换）
  - **动态容差设计决策**：公式 `tolerance = min(1.0 + magnitude × 0.00001, 100.0)`，magnitude 取 opening/closing/sum_debit/sum_credit 四者绝对值最大值；设计意图：(a) 小科目（<10 万）容差 ≈ 1-2 元，保持严格；(b) 大科目（亿级）容差 ≈ 10-100 元，容忍浮点/四舍五入差异；(c) 上限 100 元防止超大金额时容差过宽；可通过 `matching_config` 配置化（当前硬编码）
  - **adapter 机制最终定位**：adapter 不再做运行时 match（detect_best 已移除），仅作为"列别名 JSON 配置包"存在——identifier.py 的 `_RAW_HEADER_ALIASES` 可被 `ledger_recognition_rules.json` 的 `column_aliases` 覆盖，adapter JSON 文件提供软件特定别名扩展；未来如需恢复自动匹配，只需在 orchestrator 重新调 `detect_best`
  - **复盘方法论沉淀**：(1) 测试金字塔头重倾向——121 unit + 2 E2E，真实 bug 多在层间集成（ORM vs Alembic、Worker vs Pipeline、FE vs BE），下轮先补 integration 而非 unit；(2) "先跑通再说"会累积架构债，每 Sprint 留 20% 时间还债；(3) commit message 的"声称已修"需人工复核——"真实样本 E2E 通过"实际只测了 YG36 1 家不是 9 家，"Staged 原子激活"没并发验证是否真原子；(4) 前后端联动的 UX 流程测试缺失（后端端点通 + 前端按钮在 ≠ 用户真能走通），需引入 playwright
  - **辅助维度列处理修复（2026-05-08）**：(1) 新增 `aux_dimensions` 字段（混合维度列，含多维度字符串），别名 `["核算维度", "辅助核算", "核算项目", "辅助维度", "多维度"]`；(2) `aux_type` 别名精简为 `["辅助类型", "辅助核算类型"]`（不含"核算类型"避免与 aux_dimensions 冲突）；(3) RECOMMENDED_COLUMNS 的 balance/ledger 加入 aux_dimensions；(4) converter `aux_balance_rows` 分流时跳过 aux_type=None 的条目（否则 NOT NULL 报错）。实测：四川物流 tb_balance=814 + tb_aux_balance=1919 正确入库
  - **前端导入进度条现状**：`ThreeColumnLayout.vue` 顶栏已有"导入中"按钮 + `bgImportStatus` 轮询 `/api/data-lifecycle/import-queue/{projectId}`；问题：`ImportQueueService` 是内存态（重启后丢失），前端看不到后台任务；架构级改进需让 import_queue 状态写 DB 或前端改轮询 import_jobs 表
  - **导入历史改为内嵌 dialog**：`LedgerImportHistory.vue` 独立页面因 Vite 动态 import 缓存问题无法稳定加载，改为 LedgerPenetration 内 el-dialog 弹窗模式（`importHistoryVisible`），避免路由跳转
  - **账表数据管理功能已实现（2026-05-08）**：后端 `ledger_data_service.py` + `routers/ledger_data.py`（router_registry §25）3 个端点：(1) `GET /api/projects/{pid}/ledger-data/summary` 查询年度/月份分布；(2) `DELETE /api/projects/{pid}/ledger-data` 按 year+tables+periods 删除；(3) `POST /api/projects/{pid}/ledger-data/incremental/detect` 增量追加预检（diff: new/overlap/only_existing）；前端 `LedgerDataManager.vue` 组件含 3 Tab（概览/删除/增量追加），apiPaths 新增 `ledger.import.data.*`；余额表按 year 全量，序时账按 year+accounting_period 可追加
  - **`LedgerDataManager` 待挂载**：组件已建但未挂载到具体入口页面（如 LedgerPenetration.vue），需添加"数据管理"按钮打开
  - **迁移剩余步骤（P1-P2）**：P1 迁移 `_clear_project_year_tables` 到 writer.py + application_service 替换 `smart_parse_files`（2.5h）→ P2 观察稳定后删除旧引擎文件
  - **旧引擎外部调用方（3 处，仅回退时触发）**：import_job_runner.py（smart_import_streaming）、ledger_import_application_service.py（smart_parse_files + smart_import_streaming）、account_chart_service.py（_clear_project_year_tables）

### 中期功能完善
- **项目三码体系（待 spec）**：本企业名称+代码、上级企业名称+代码、最终控制方名称+代码 6 字段必填（所有项目，非仅合并），通过 parent_company_code→company_code 构建项目树；可见性基于 ProjectAssignment 派单裁剪（助理看子公司，经理看项目组，合伙人看全部）；需新建 spec 规划
- 性能测试（真实 PG + 大数据量环境运行 load_test.py，验证 6000 并发）
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度 85%，业务完成度 60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能
- `GtStatusTag.STATUS_MAP_TO_DICT_KEY` 是硬编码映射表，新增 StatusMap 时需手动维护 [P3]
- PBC 清单真实实现（R7+ 计划，后端当前 stub）[P2]
- 函证管理真实实现（R7+ 计划，后端当前 stub）[P2]
- Vue 文件绕过 service 层直接调用 API：86 个文件 / 322 处（复盘发现），策略"触碰即修"+CI 卡点防恶化 [P3]
- 函证管理真实实现（R7+ 计划，后端当前 stub）[P2]

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

## 用户偏好（B3 轮新增）

- **死代码立即删除**：不留 DEPRECATED/保留作 fallback 等注释，否则每次复盘都会重复提议（2026-05-10 明确要求）

## B3 大账套加速（2026-05-10）

- **[✅ calamine parser 已落地]**：`backend/app/services/ledger_import/parsers/excel_parser_calamine.py`（~150 行，签名与 openpyxl 版一致），feature flag `ledger_import_use_calamine` 默认 True；实测 3.2-3.4× 加速（YG4001 0.47→0.14s / YG36 1.98→0.63s / YG2101 76.68→22.48s）
- **[✅ 死代码清理]** 删除 `detector._detect_xlsx_from_path_calamine`（~3000 字符）+ `parsers/excel_parser_calamine.detect_sheets_from_path_calamine`（~1700 字符）；detector 永远走 openpyxl read_only（真 SAX）
- **[✅ pipeline 按 sheet 行数切 engine]**：`_CALAMINE_PARSE_MAX_ROWS=500_000` 阈值，< 500k 用 calamine，≥ 500k 用 openpyxl（避免 calamine 大 sheet 全量 decode 问题）
- **[✅ pipeline perf 打点已落地]**：每 phase `_mark` 标记 + parse_write_streaming 内部 7 项累计耗时（parse/dict/prepare/validate/convert/insert/progress/cancel）
- **[✅ scripts/b3_diag_yg2101.py]**（保留）：本进程直接 execute_pipeline 跑 YG2101 拿 perf 日志的诊断脚本；绕过 HTTP 层；踩坑 = projects NOT NULL 列多用 SELECT LIMIT 1 复用 / import_jobs.year NOT NULL / ledger_datasets.job_id FK → 必须先 INSERT ImportJob
- **[❌ 实测无效已回滚] 并行 UPDATE**：4 张 Tb* 表改为 asyncio.gather + 独立 session，YG2101 实测 127s→126s 无加速（PG WAL 串行写入是真瓶颈不是 Python/网络）；已恢复 for loop 串行版，函数 docstring 记录此教训
- **[⏸️ 待做] P1 partial index**：`CREATE INDEX CONCURRENTLY ... on Tb*(dataset_id) WHERE is_deleted=true`；让 activate UPDATE 走索引；预期 activate 127s→40-60s
- **[⏸️ 待做] P2 bulk_copy_staged Python 开销优化**：跳过空 raw_extra / COPY binary format / 传 dict 给 asyncpg 自动编码
- **[⏸️ 待 Sprint] P3 架构重构**：业务查询 30+ 处改走 `v_ledger_active` 视图，activate 只改 metadata；工时 3-5 天；彻底消除 UPDATE 风暴

## YG2101 真实性能数据（128MB / 200 万行，2026-05-10 实测）

- **总耗时 399-482s**（取决于系统负载，calamine 解析 ~20s + parse_write_streaming 270-360s + activate 127s + rebuild 0.7s）
- **parse_write_streaming 内部拆解**：parse 87.6s / dict 化 2.5s / prepare_rows 13.6s / validate_l1 4.7s / convert 9.2s / **insert 151.8s（30 次 COPY）** / progress+cancel 0.0s
- **activate 127s 根因** = `DatasetService._set_dataset_visibility` UPDATE 4 张 Tb* 表（200 万行 is_deleted=false）；PG UPDATE 本质 = 删旧 tuple + 写新 tuple（MVCC）
- **关键架构事实**：业务查询 **全部** 通过 `Tb*.is_deleted=false` 判断可见性，**没有一个**业务查询过滤 `dataset_id`；意味着 activate 必须物理 UPDATE（除非大规模改业务查询走视图层）
- **insert 151.8s 拆解**：aux_ledger 每 100k 行 COPY ~19s（吞吐 ~5200 rows/s），包含 `_sanitize_raw_extra` + `json.dumps` + tuple 构造公共字段的 Python 开销约 30-40s
- **parse 87s 来源**：calamine `get_sheet_by_name` 必须全量 decode sheet XML（Rust 侧），无法避免

## B3 方案对比沉淀（2026-05-10 基于实测推演）

- **[否决] Partial index WHERE is_deleted=false**：预期加速 insert（staged 不进索引），但同时让 activate 变慢（UPDATE 时 200 万行要建索引），净收益 ≈ 0，否决
- **[待评估] 方案 B 业务查询加 dataset_id 过滤**：改 30+ 查询，新建 `active_dataset_id(pid, yr)` PG 函数作 helper；彻底消除 UPDATE 风暴；**5 天工时独立 Sprint**
- **[待评估] 方案 C Tb* 表 partition by dataset_id**：activate 变成 ALTER TABLE ATTACH/DETACH（瞬间）；涉及 schema migration + ORM 适配；**2-3 周工时**
- **[待评估] 方案 D DROP → UPDATE → REBUILD 索引**：200 万行 UPDATE 可能从 127s → 40-60s；缺点 = rebuild 期间业务查询不可用（生产不行）
- **[✅ 推荐立刻做] 方案 E PG 配置调优**（10 分钟，零代码）：`wal_compression=on` / `synchronous_commit=off` / `wal_buffers=64MB` / `checkpoint_timeout=30min` / `max_wal_size=8GB`；预期总省 ~50s（399s→350s）；`synchronous_commit=off` 断电可能丢秒级但审计二次导入可接受
- **[✅ 推荐] 方案 F insert Python 开销优化**：`_sanitize_raw_extra` 对 None/空 dict 快速返回 + bulk_copy_staged tuple 构造合并；预期 insert 再省 20-30s
- **[✅ 推荐核心洞察] 异步 activate**：用户完全不需要等 127s UPDATE 完成，pipeline 写完 insert 就返回 "completed"，activate 后台 worker 异步跑；**用户感知从 400s → 250-280s**（大半时间都省在"不等 activate"）
- **组合建议**：E + F + 异步 activate（0.5 天工时），把 YG2101 用户感知压到 4-5 分钟；再不够再做 C partition

## 关键技术洞察（B3 沉淀，未来大数据优化可复用）

- **PG UPDATE 真瓶颈是 WAL 串行写入**，不是 Python/网络/asyncpg —— 所有基于"并发客户端"的加速方案（多 connection 并行 / 协程 gather）对大批 UPDATE 都无效
- **PG UPDATE 本质 = 删旧 tuple + 写新 tuple + 所有索引的维护**，200 万行 UPDATE ≈ 做 200 万次 INSERT + 200 万次 DELETE + N 倍索引操作
- **"用户感知耗时"≠"后台完成耗时"**：长流程的 metadata 切换（activate/rebuild_summary）都可以后台异步做，用户体验只关心数据写完这一刻

## B3 架构方案深度沉淀（2026-05-10）

- **[否决] 方案 C partition by dataset_id**：PG LIST PARTITION 要求每个 dataset 预建 partition（UUID 动态值会炸），HASH PARTITION 只做静态分片无法按 dataset 切换；**不能用于 activate 切换场景**
- **[否决] 方案 G trigger 自动维护 is_deleted**：trigger 内仍做 200 万行 UPDATE，瓶颈没动只是换位置
- **[推荐 B' 视图方案] 根本方案 activate 从 127s 降到 0.01s**：
  - 4 张 Tb* 表 + 4 个 view（`v_tb_balance` / `v_tb_ledger` / `v_tb_aux_balance` / `v_tb_aux_ledger`）
  - view 定义 = `SELECT * FROM tb_x WHERE EXISTS (SELECT 1 FROM ledger_datasets d WHERE d.id=tb_x.dataset_id AND d.status='active')`
  - 业务查询 30+ 处 `Tb*` → `v_Tb*`（grep 替换）
  - `DatasetService.activate` 只 UPDATE `ledger_datasets.status='active'` 一行
  - `_set_dataset_visibility` 可变 no-op 或保留兼容
  - is_deleted 字段保留作软删除语义（回收站等）
  - **工时 3-4 天，收益 activate 127s→0.01s，YG2101 总耗时 399s→270s**
  - 风险：30+ 业务查询改漏；有些 service 走 raw SQL 可能漏掉；view 复杂 JOIN 性能需测
- **组合推荐路线**：先 E+F+异步 activate（0.5 天，399s→250s 用户感知）验证接受度 → 再评估是否上 B'（4 天）彻底解决
- **核心洞察**：所有跨 session 并发客户端加速（multi-connection / asyncio.gather）对 PG UPDATE 都无效（WAL 串行写）；UPDATE 真正要消灭只有两条路：(1) 数据不动改 metadata 切换（视图/partition）(2) 业务不需要 UPDATE（staged 模式下行直接 is_deleted=false + view 层 JOIN 过滤）

## B3 架构重构调研成果（2026-05-10，开干前盘点）

- **[发现] `backend/app/services/dataset_query.py` 已提供 `get_active_filter(db, table, pid, year)` 过渡抽象**，文档明确写了四步迁移计划：加 dataset_id 列 → 写入填 → 查询迁移 → 去掉 is_deleted；当前阶段业务查询可选用它（有 dataset_id 优先，否则降级 is_deleted）
- **[业务查询直接用 `TbX.is_deleted == False` 统计]**：约 40 处直接查询散落在 15+ 个 service + 2 个 router，绝大多数**没有**走 `get_active_filter`；B' 视图方案的改造面就是这 40 处
- **[否决 B''] computed column 方案**：PG 计算列不能引用其他表（不能 JOIN ledger_datasets），is_deleted 只能是静态列
- **[否决 B'''] 写入 is_deleted=false 靠 dataset_id 区分**：如果所有行都 is_deleted=false，staged 数据对业务查询立即可见（40 处没过滤 dataset_id），会暴露未激活数据
- **[重新推荐] 务实路径 E+F+异步 activate（0.5 天）+ 观察**：0.5 天做 PG 调优 + Python 侧优化 + activate 放后台，用户感知 400s → 250s 即可；若仍不满意再上 3-4 天 B' 视图方案
- **raw SQL 访问点**：`metabase_service.py` / `data_lifecycle_service.py` / `smart_import_engine.py` / `import_intelligence.py` / `consistency_replay_engine.py` / `ledger_import/validator.py` 都有 raw SQL `FROM tb_*`，B' 方案需要一并替换为 `v_tb_*`

## 待用户决策

- **选 1：先做 E+F+异步 activate（1.5 小时）**，见效快；不够再上 B'
- **选 2：直接开 B' 分支做视图方案（3-4 天）**，彻底消除 activate 127s + rollback 127s

## B3 E+F 实测结论（2026-05-10）

- **[E PG 配置已是最优]**：查询 `wal_compression=pglz / synchronous_commit=off / wal_buffers=64MB / checkpoint_timeout=30min / max_wal_size=8GB`，此前有人已调过；**E 方案不需重做**
- **[F Python 优化实测收益 <1s]**：`_json_default` 合并 `_sanitize_raw_extra + json.dumps`；微基准 130 万次 4.61s → 3.76s（省 0.85s）；YG2101 生产实测被 PG 波动噪声淹没（activate 127s→193s 的波动 >> F 收益）；**F 改动保留但收益可忽略**
- **[activate 真实波动 127-193s]**：同一代码同一数据，连续两次跑 YG2101 activate 耗时差 66s；系统负载 / autovacuum / 磁盘缓存等随机因素影响极大；**activate 耗时单次测量不可靠，需多次平均**
- **[关键结论] B2+B3 已到 YG2101 性能极限 ~400-480s**：parse 87s（calamine 不可再降）+ insert 151s（PG COPY 极限）+ activate 127-193s（PG WAL 串行极限）；这些都是底层限制，**小修小补边际收益极低**
- **[下一步唯一选择]**：要么接受 YG2101 ~7 分钟为当前上限，要么直接做 B' 视图方案（3-4 天，activate 从 127s → 0.01s 真正消灭 UPDATE 风暴）
- **[放弃] 异步 activate 方案**：fire-and-forget + 后台任务追踪复杂度高，且不彻底（activate 自身仍 127s 只是用户不等）；不值得投入

## B' 视图重构 spec 三件套已创建（2026-05-10）

- `.kiro/specs/ledger-import-view-refactor/` README + requirements（22 需求）+ design（5 架构决策 + 改造清单按文件分组）+ tasks（3 Sprint ~30 任务 + 10 验收）
- 分支 `feature/ledger-import-view-refactor` 已切出（从 feature/round8-deep-closure 68ba2c8）
- **[关键洞察] Sprint 顺序必须倒过来**：原"先改 activate/写入 → 再迁查询"路径无法独立运行（中间状态破坏数据可见性）；新顺序 = 先 Sprint 1 迁查询（语义不变）→ 再 Sprint 2 一次性改 activate+写入（原子 commit）→ Sprint 3 加固
- **[保留策略] partial index 兼容新架构**：`idx_tb_*_active_queries (project_id, year, dataset_id) WHERE is_deleted=false` 仍然覆盖所有 active 数据，B' 改造后 get_active_filter 的查询直接命中

## PG Docker 容器 shm_size 调整（2026-05-10）

- **docker-compose.yml PG 服务加 `shm_size: 2g`**：默认 64MB 在 YG2101 级别 200 万行聚合查询时触发 `DiskFullError: could not resize shared memory segment`；2G 足够支撑 COUNT/SUM 并发分析
- **PG 容器重建流程**：`docker stop/rm` 后用 `docker run` 显式挂载 `gt_plan_pg_data` volume（而非 `pg_data`，后者是 docker run 默认创建的新 volume 会丢数据）
- **PG 当前调优值**：shared_buffers=1GB / work_mem=64MB / effective_cache_size=6GB / max_connections=200 / random_page_cost=1.1 / effective_io_concurrency=200 / wal_compression=pglz / synchronous_commit=off / wal_buffers=64MB / checkpoint_timeout=30min / max_wal_size=8GB / shm_size=2g
- **四表实际数据量（2026-05-11）**：tb_aux_ledger 1570万行 / tb_ledger 741万行 / tb_aux_balance 70万行 / tb_balance 11万行（总计 2300 万行）
- **查询性能优化索引（2026-05-11）**：`idx_tb_ledger_proj_year_acct_date (project_id, year, account_code, voucher_date, id) WHERE is_deleted=false` + aux_ledger 同款；序时账穿透查询从 Filter 降为纯 Index Scan（17ms）
- **Redis 缓存热查询**：`/balance` 和 `/aux-balance-summary` 端点加 5 分钟 Redis 缓存（key 格式 `ledger:*:{pid}:{year}:*`），导入完成后自动 SCAN+DELETE 失效
- **.env 连接池**：`DB_POOL_SIZE=30` / `DB_MAX_OVERFLOW=100`（最大并发 130 连接）

## B3 Step 1 已落地（partial index）

- `backend/alembic/versions/view_refactor_activate_index_20260510.py`（未走 alembic 执行，手动 CREATE INDEX CONCURRENTLY）
- 已建 8 个 partial index：4 张 Tb* 表 × 2（activate_staged + active_queries）
- 索引总大小 ~150MB（aux_ledger 95MB 最大，128 万行 × 2 索引）

## 用户流程偏好（本轮新增）

- **复杂重构先做 spec 三件套**：体系化、精准、可回滚；"每次单独尝试都要跑 YG2101" 太慢 → 要求"全部改完再跑一次测试"
- **避免折中方案**：要"根本解决"不要"折中"；partial index 类改动收益有限不算根本方案

## B' 视图重构 spec 三件套升级（2026-05-10 第二轮扩展）

- **requirements.md 从 22 需求扩展到 48 需求（8 大维度）**：架构层 A1-A10 / 大文件 B1-B8 / 企业级治理 E1-E8 / 数据库维护 D1-D8 / 可维护性 M1-M6 / 回归 R1-R8 / 边界 B1-B4 / 成功判据表格
- **[新用户偏好] 复杂重构需求必须全面分析现有代码后才给建议**：不能只看单点瓶颈，要从架构/大文件/企业级治理/DB 维护/可维护性 5 个以上维度一起考虑
- **[关键技术洞察] B' 最大企业级收益不是"快 127s"而是"解决表膨胀"**：每次 activate UPDATE 200 万行产生 200 万 dead tuple，autovacuum 追不上会磁盘爆炸；B' 后无 dead tuple，表大小线性增长
- **[发现] 历史已归档的 partition 方案**：`backend/alembic/versions/_archived/017_partition_tables.py`（按 year RANGE partition）是团队之前探索未落地的方案；B' 落地后可复用做 D8 进一步优化

## 新增关键待办（按优先级）

- **P0（本 spec 核心）**：A1-A10 视图/metadata 切换 + A4 purge 定时任务 + A5 `_set_dataset_visibility` 废弃
- **P1 数据库维护**：D2 autovacuum 调优 + D3 superseded 定期清理（保留最近 3 个）+ D4 DROP 废弃索引 `idx_tb_*_activate_staged`（55MB 空间回收）
- **P1 企业级治理**：E1 数据集版本历史路由 + E4 审计日志（谁在什么时间激活哪个版本）
- **P2 独立 Sprint**：B6 分片上传 / B7 Worker 资源隔离 / E2 导入配额 / E5 权限细粒度 / D8 表分区
- **M1 测试脚本分工规约**：`e2e_yg4001_smoke.py`=CI 快跑 / `e2e_full_pipeline_validation.py`=本地/部署前 / `b3_diag_yg2101.py`=大样本性能诊断；`b2_copy_perf_validation.py`/`b3_calamine_smoke.py`/`b3_profile_realistic.py` 后续合并清理

## 新数据库维护规约（B' 后必须确立）

- **表膨胀检测**：每次大导入后跑 `SELECT relname, n_dead_tup, n_live_tup FROM pg_stat_user_tables WHERE relname LIKE 'tb_%'` 确认 dead_tuple_ratio < 10%
- **Tb* 表专用 autovacuum 参数**：`autovacuum_vacuum_scale_factor=0.05 / autovacuum_vacuum_cost_limit=1000` 让 autovacuum 跟上大表变化
- **superseded 保留策略**：同一 project+year 最多保留 1 active + 3 superseded；超过的用 purge 任务物理 DELETE

## 9 家真实样本结构归档（2026-05-10 扫描后）

- **规模差异 600×**：最小 YG4001-30 (0.8MB/4k 行) → 最大陕西华氏 2025 (500MB/2600 万行)
- **5/9 是多文件场景**（"1 文件 1 账套"反而是小概率）：
  - 陕西华氏：单年 13 文件（1 balance + **12 月度序时账**）× 2 年度
  - 和平药房：余额 xlsx + **2 CSV 按日期段切**（20250101-1011 + 20251012-1031）
  - 辽宁卫生 / 医疗器械：2 xlsx 分文件（余额 + 序时账分开）
  - 和平物流：单 xlsx 但**方括号表头** `[凭证号码]#[日期]`
- **文件布局多样化**：YG2101 单 xlsx 含 4 sheet（含空 Sheet1）/ YG36/YG4001 2 sheet / 安徽骨科 2 sheet（有维度余额+序时账）
- **非标软件来源**：至少 3 种软件（用友 NC / 金蝶 KIS / 某方括号格式），同一客户同一年度可能混用

## requirements.md 第 9-10 节新增（9 家样本业务需求）

- **U1 多文件拼接**：detect 支持"批量文件一次识别"；13 文件识别为"1 balance + 12 ledger 片段合并为一个 dataset"
- **U2 文件名元信息利用**：当前 detector 只看内容忽略文件名；`-科目余额表.xlsx` / `-序时账.xlsx` / `25年10月` 应作为 detector 置信度加分信号
- **U3 方括号+组合表头**：`[凭证号码]#[日期]` 格式需要 detector 剥壳规则；作为 adapter 声明式规则
- **U4 跨文件时间段合并**：和平药房 2 CSV 按日期段切需合并到同一 dataset
- **U5 月度增量 UX 引导**：陕西华氏场景"预审导 1-9 月，年审追加 10-12 月"；后端 apply_incremental 支持但前端缺引导
- **U6 分片上传（独立 Sprint R6）**：500MB 文件前端一次 POST 不可行
- **U7 导入前预检报告**：detect 返回 `{files_detected, years_found, table_types, total_rows_estimate, estimated_import_time_seconds}` 让用户确认
- **U8 多年度同项目**：同 project 可并存多 year active dataset（陕西华氏 2024+2025）
- **U10 规模分 S/M/L 三档处理**：S < 10k INSERT / M 10k-500k calamine+COPY / L > 500k openpyxl 流式
- **U11 adapter JSON 沉淀**：9 家识别模式写入 `adapters/*.json` 声明式规则
- **U12 人工映射保存**：用户手动调整的 column_mapping 保存为该客户 adapter 模板（column_mapping_service S2 已有基础）
- **U13 多 sheet 分流**：YG2101 4 sheet 场景每个 sheet 独立识别 table_type 分流到 4 表

## 关键技术事实更新

- **陕西华氏场景暴露 pipeline 单文件语义缺陷**：当前每个 file 独立 detect/identify/convert/insert，没有"多文件属于同一 dataset"概念；需求 U1/U4 是下一轮重大改造点
- **9 家样本表类型识别率 97.8%**（1 家遗漏 = 和平物流方括号表头）；U3 adapter 规则可拉到 100%
- **CSV 大文件性能已验证**：和平药房 392MB CSV detect <5s、parse 内存 <200MB（已有流式实现）
- **scripts/ 清理**：当前 b2_copy_perf_validation/b3_calamine_smoke/b3_profile_realistic 已整合到 requirements M1；下轮可考虑合并或删除

## ledger-import-view-refactor spec 范围最终确定（2026-05-10）

- **F 系列 10 条发现分级处理**：本 spec 纳入 6 项识别引擎强化（F2 文件名识别 / F3 方括号表头 / F5 跨年度 / F7 CSV 大文件验证 / F8 表类型鲁棒 / F9 合并表头快照）+ B' 视图重构；独立 Sprint 留 4 项（F1 多文件拼接 / F4 分片上传 / F6 月度增量 UX / F10 企业级 UX）
- **requirements.md 增加"十一、9 家样本深度发现"和"十二、F 系列落地映射表"**，每条明确本 spec 决策（★必做/☆可选/⏸独立 Sprint）+ 实现位置
- **最终指标表增加 F2-F9 可量化验收**：辽宁卫生 sheet1 文件名识别置信度 ≥60 / 和平物流方括号表头 ≥85 / YG36 有核算维度余额表分流正确 / 392MB CSV detect <5s / 跨年度双 active 集成测试 / 9 家 header 快照测试全绿
- **本 spec 排除的场景已有过渡方案**：多文件拼接走 apply_incremental、分片上传靠 nginx 调大 client_max_body_size、月度增量前端缺引导但后端就绪

## spec 工作流规约新增（本轮沉淀）

- **大 spec 必须对"关键发现"做 F 系列编号 + 处理决策表**：避免需求范围模糊，每条发现必须标 ★本 spec 必做 / ☆可选 / ⏸独立 Sprint 三选一
- **F 系列映射表必须列 3 列**：对应需求编号（U2/U3/A11）+ 实现位置（具体文件/函数）+ 本 spec 处理状态

## ledger-import-view-refactor requirements.md 结构重构（2026-05-10）

- **requirements.md 从 650 行重构为 430 行**（信息密度+35%）：统一编号 F1-F12（必做）+ O1-O9（独立 Sprint），消除 U 系列和 F 系列 60% 重复、B1-B8 和 B1-B4 编号冲突
- **新 6 章结构**：前言（业务/技术根因/定位）→ §1 范围边界（1 张表看清做/不做）→ §2 功能需求（A 核心架构+B 识别引擎+C 企业级治理）→ §3 非功能需求（性能/DB 健康/可维护性/兼容性）→ §4 测试矩阵（单测/集成/E2E/CI/UAT）→ §5 成功判据汇总 → §6 术语表 + 附录 9 家样本表
- **[规约] 大 spec requirements.md 结构模板**（从本次重构沉淀）：
  1. 前言必写"为什么做"（业务痛点 + 技术根因 + 本 spec 边界）
  2. §1 范围边界必须用表格罗列做什么（F 编号）和不做什么（O 编号作独立 Sprint）
  3. 功能需求分组避免按章节分散（相关需求聚在一起）
  4. 测试矩阵必须单独成章（禁止散落在 M / R / F 多处）
  5. 成功判据用量化表格 + 对应需求编号
  6. 术语表解决新概念混淆（staged / active / superseded / legacy）
  7. 附录放真实样本归档等支撑性资料
- **[规约] 避免 3 种常见重复模式**：
  - 同一主题两套编号（U 系列 vs F 系列 → 只用一套）
  - 同一字母不同章节（B 大文件 vs B 边界 → 改其中一套为 NF 章节）
  - 决策散落多处（本 spec 做/不做的判断应集中 §1.1 和 §1.2 两张表）
- **本次需求核心锚定**：大文档处理为主，保证总体架构 / 可维护性 / 企业级治理 / 数据库维护 4 个维度同步落地

## ledger-import-view-refactor requirements.md 12 缺口补强（2026-05-10）

- **大文档处理的 5 个关键路径都缺硬指标**：解析/写入/进度/内存/超时；只靠 F1 activate <1s 不够，需要超大档基线（陕西华氏 500MB total <30min / 单 worker 峰值 <2GB / 单 sheet parse >10min 自动 timeout）
- **P0 必加 4 项**（任何大文档系统 table stakes）：F13 进度精度（每 5% 或 10k 行至少更新 + 30s 无更新才算卡）/ F15 cancel 清理保证（30s 内停 + 自动 cleanup_dataset_rows + Artifact 清理）/ F18 迁移策略（Day 0 deploy / Day 7 一次性 UPDATE / Day 30 DROP 废弃索引）/ 超大档基线
- **P1 补强 6 项**：F14 checkpoint 可恢复（staged 写完立即 checkpoint / resume_from_checkpoint 接口）/ F16 Prometheus 最小埋点（duration histogram / status counter / dead_tuple gauge）/ F17 耗时预估（从 O7 拆出，前端显示"预计 8 分钟"）/ F19 灰度回滚（feature flag + 项目级开关）/ 索引膨胀治理（purge 后 REINDEX CONCURRENTLY）/ 连接池隔离（B' 后 activate 瞬时释放 / pipeline 单 worker ≤3 连接）
- **P2 补强 2 项**：Artifact 保留期 90 天 expires_at 文档化 / autovacuum VACUUM 锁冲突（cost_delay=5ms + 发布窗口避高峰）
- **[重要技术决策] 迁移策略三阶段**：B' 代码与 is_deleted=true 老数据可以并存（fallback 兜底），不需要一次性迁移；Day 7 再做一次大 UPDATE 清理老数据，换 B' 后永久不再 UPDATE；Day 30 DROP `idx_tb_*_activate_staged`

## 云平台协同是硬需求（用户明确 2026-05-10）

- **核心诉求**：一个项目组成员 A 处理账套后，B/C/D/E 其他成员自动看到更新（而非手动刷新）
- **现有架构 80% 就绪**：ProjectAssignment 模型 / outbox event / WebSocket 通道 / get_active_dataset_id 单一真源
- **缺的 20%**：激活广播（WS 推送给项目组）/ 锁透明（导入中显示 holder+进度+预计耗时）/ 数据新鲜度（B 页面自动 re-fetch）
- **典型用例 3 类**：(1) A 导入 B 实时看到激活完成刷新 / (2) A 导入死机 B 接管 / (3) 并发 activate vs rollback 互斥

## ledger-import-view-refactor 第三轮补全建议（F20-F37，共 18 条）

**深度补全分 4 组**：
- **2.F 云平台协同**（F20-F25，6 条）—— 对应用户云平台诉求
- **2.G 数据正确性保障**（F26-F30，5 条）—— 企业级兜底
- **2.H UX 补强**（F31-F35，5 条）
- **2.I 平台工程**（F36-F37，2 条）

**优先级分级**：
- **P0 必做 8 条**：F20 激活广播 / F21 锁透明 / F23 rollback 走锁 / F25 审计溯源 / F26 孤儿扫描 / F27 integrity check / F31 激活确认 / F28 恢复剧本文档
- **P1 强推 5 条**：F22 接管 / F24 只读旁观 / F29 事务隔离 ADR / F32 错误友好 / F28 完整演练
- **P2/P3 独立 Sprint 5 条**：F30 CRC 校验 / F33 内存警告 / F34 diff 预览 / F36 API 版本化 / F37 CLI

## 关键技术决策（第三轮沉淀）

- **rollback 必须走 ImportQueue 锁**：activate 和 rollback 互斥（当前 rollback 没走锁是 bug）
- **接管（takeover）机制**：heartbeat 超 5min → 自动允许其他成员接管；ImportJob.created_by 扩展为数组记录链路
- **激活前 integrity check**：metadata 切换前 COUNT(*) 校验 staged 行数符合 record_summary；<1s 成本换防静默损坏
- **staged 孤儿清理周期**：定时任务每小时扫 > 24h 的 staged 无 job 关联 → 自动 cleanup
- **接口按角色成员可见**：项目组 ProjectAssignment 成员都能看 `GET /jobs/{id}` 实时进度（不只是 holder）
- **激活意图确认 UX**：ElMessageBox 二次确认 + 可选"理由"字段 → 进 ActivationRecord.reason 审计

## ledger-import-view-refactor requirements.md F20-F37 补全完成（2026-05-10）

- **13 条 P0+P1 需求已全部入 requirements.md**（F20-F32，不含 F30/F33-F37 进独立 Sprint O10-O14）
- §1.1 必做清单表从 19 行扩至 32 行；§1.2 排除表从 O1-O9 扩至 O1-O14
- **新增 3 个章节**：§2.F 云平台协同（F20-F25 共 6 条）/ §2.G 数据正确性保障（F26-F29 共 4 条）/ §2.H UX 补强（F31-F32 共 2 条）
- §3.5 可观测性表追加 WebSocket 通道 + 项目组锁状态行；§4.2 集成测试追加 6 项（test_ws_dataset_broadcast/test_import_takeover/test_activate_rollback_mutex/test_staged_orphan_cleanup/test_activate_integrity_check/test_job_readonly_access）
- §4.5 UAT 回归清单追加 6 项手动验收；§5 成功判据汇总追加云协同 5 项 + 正确性 3 项 + UX 2 项 + 运维 2 项（ADR-003/004）
- **requirements.md 最终状态**：~650 行覆盖 F1-F32 + O1-O14，下一步可同步 design.md / tasks.md
- 整体优先级排序：F1/F2 是核心瓶颈（activate 127s→<1s），F14/F15/F27 是大文档健壮性底线，F20-F25 是云协同基建，F28-F29 是文档交付

## ledger-import-view-refactor requirements.md 第 4 轮补全（2026-05-10）

- **第 4 轮深度复盘发现 8 个覆盖漏洞**（安全/多租户/数据质量/运维健康/事件可靠性/下游联动/规模异常/graceful shutdown）
- **新增 7 条 P0/P1 需求 F40-F46 进 §2.I 安全与健壮性**：F40 上传安全（MIME+zip bomb+宏拦截）/ F41 项目权限+tenant_id 预留 / F42 零行/异常规模拦截 / F43 健康检查端点 / F44 graceful shutdown / F45 事件广播 outbox 重试+DLQ / F46 rollback 下游 Workpaper/Report stale 联动
- **新增 3 条独立 Sprint 排除项 O15-O17**：完整多租户 / 性能基线 CI 门禁 / 告警渠道适配
- 编号策略修正：避开 F33-F39（排除表已占位引用），P0+P1 新条目从 F40 起编号
- **新增 §3.6 安全 + §3.7 健壮性**两个非功能章节独立呈现
- §4.2 集成测试追加 7 项（test_upload_security/test_cross_project_isolation/test_empty_ledger_rejection/test_health_endpoint/test_worker_graceful_shutdown/test_broadcast_retry_with_outbox/test_rollback_downstream_stale）
- §4.5 UAT 追加 6 项手动验收；§5 成功判据追加 11 行（安全 3 + 数据质量 2 + 健壮性 4 + UX 2）
- **requirements.md 最终覆盖需求数 F1-F46 合计 39 条（去掉预留间隔 F33-F39，实际 32 条必做）+ O1-O17 独立 Sprint 17 条**
- **关键技术决策沉淀**：(1) Tb* 表加 tenant_id NOT NULL DEFAULT 'default'（不启用但预留）；(2) SIGTERM → stop_event → cancel_check 回调链；(3) F20 WS 广播必须走 event_outbox 才可靠（直推丢事件）；(4) rollback 必须发 DATASET_ROLLED_BACK 事件级联 stale（复用 R1/R7 机制）；(5) get_active_filter 签名强制带 current_user 参数（当前签名缺失是潜在越权漏洞）

## requirements.md 校验透明化补全（F47-F49，2026-05-10）

- 用户截图点出「数据校验」入口痛点（1002 银行存款期末差异但不知公式/代入/来源）
- 新增 §2.J 数据校验透明化章节（F47-F49 共 3 条）：
  - **F47 每条 finding 附 explanation 字段**：公式（英文+中文）+ inputs 代入值 + computed 中间值 + diff_breakdown 差异来源分解 + hint 建议；适用 L1/L2/L3 所有 finding code
  - **F48 校验规则说明文档**：`GET /api/ledger-import/validation-rules` 返回全量规则 catalog（公式+容差+示例），前端独立页面 `/ledger-import/validation-rules` 分组展示；catalog 必须与 validator.py 双向一致
  - **F49 差异下钻到明细**：finding.location 扩展 drill_down 字段，复用现有 LedgerPenetration 穿透组件展示该科目全部凭证
- **关键技术决策**：(1) validator.py 每个 finding code 对应一个 Pydantic explanation model 严格 schema；(2) 新增模块级 VALIDATION_RULES_CATALOG 做单一真源；(3) 容差公式 `min(1.0 + magnitude × 0.00001, 100.0)` 从代码字面量暴露到前端规则说明页
- §4.2 追加 3 项集成测试；§4.5 追加 3 项 UAT；§5 成功判据追加「校验」分类 3 行
- requirements.md 最终覆盖 F1-F49（35 条必做，预留 F33-F39 间隔）+ O1-O17（17 条独立 Sprint）

## requirements.md 第 5 轮业务闭环补全（F50-F53，2026-05-10）

- 从「审计合规 + 系统稳定性 + UX 自然闭环」3 个维度发现 4 个关键盲点，新增 §2.K 业务闭环与合规章节
- **F50 下游对象快照绑定（最关键合规需求）**：Workpaper/AuditReport/Note 新增 bound_dataset_id + dataset_bound_at；AuditReport 转 final 时自动锁定；签字后的报表 rollback 被拒绝（409）；解决"签字后数字仍可被 rollback 篡改"的严重合规风险
- **F51 全局并发限流**：基于 Redis semaphore 的平台级 worker 上限（默认 3）+ FIFO 排队；内存逼近 3GB 时 pipeline 降级到 openpyxl + 小 chunk；防 100 并发打爆 PG/内存
- **F52 列映射历史智能复用**：detect 阶段按 file_fingerprint 查 ImportColumnMappingHistory 自动应用；第二次导入效率节省 > 50%；跨项目同软件匹配降级为"建议"
- **F53 留档合规保留期差异化**：ImportArtifact 新增 retention_class（transient/archived/legal_hold）；final 报表引用的 dataset 自动升级 archived（10 年）；purge 任务尊重 bound_dataset_id 绑定；对齐《会计档案管理办法》合规要求
- 新增 5 条独立 Sprint 排除项 O18-O22（审批链配置/差异对比/底稿回滚快照/模板市场/定时抓取）
- §3.2 数据库健康补强 purge 描述"尊重下游绑定与 retention 类别"
- §4.2 追加 7 项集成测试；§4.5 追加 5 项 UAT；§5 成功判据追加 5 行
- **关键架构决策**：(1) `get_active_filter` 新增 `force_dataset_id` 参数支持下游绑定查询；(2) Workpaper 首次生成即绑定、AuditReport 到 final 才锁定（粒度差异化）；(3) retention_class 自动决策基于 F50 绑定状态联动，不让用户手工设；(4) 并发限流走 Redis semaphore 而非 DB 乐观锁（性能）
- requirements.md 最终覆盖 F1-F53（38 条必做，预留 F33-F39 间隔）+ O1-O22（22 条独立 Sprint）

## ledger-import-view-refactor design.md + tasks.md 扩展（2026-05-10）

- **design.md** 从 Sprint 1-3 的 5 个架构决策 D1-D5 扩展到 22 个决策 D6-D22，新增 13 个架构决策对齐 §2.D-§2.K：D6 大文档健壮性 / D7 运维灰度 / D8 云协同 / D9 数据正确性 / D10 UX / D11 安全 / D12 校验透明化 / D13 业务闭环，8 组各带代码骨架和 Pydantic model / Alembic DDL 示例；新增风险 6-8（rollback 死锁 / 并发过严 / fingerprint 碰撞）
- **tasks.md** 从原 Sprint 1-3 共 40 任务扩展到 Sprint 1-9 共 171 任务，新增 6 个 Sprint：Sprint 4 大文档+运维（18 任务）/ Sprint 5 云协同（20）/ Sprint 6 数据正确性+UX（16）/ Sprint 7 安全（23）/ Sprint 8 校验+合规闭环（44）/ Sprint 9 最终验收（10）；每任务标 P0/P1/P2 优先级
- **工期估算 35 人天**（单人串行），引入并行化策略（主 + 两副开发 3 人团队可压缩到 ~15 天）
- **里程碑拆分**：M1 B' 核心（1-3）→ M2 企业级可用（4-5）→ M3 生产合规门槛（6-7）→ M4 审计业务完备（8-9）
- **关键架构文件清单**：metrics.py / error_hints.py / global_concurrency.py / validation_rules_catalog.py / staged_orphan_cleaner.py（worker）/ duration_estimator.py 6 个新建模块 + 5 个 Alembic 迁移（cleanup_old_deleted / tenant_id / dataset_binding / creator_chain / event_outbox_dlq）
- **Sprint 7 批次 B 重点决策**：tenant_id 迁移的"40+ 调用点补 current_user"与 Sprint 1 合并做（不单独拆），避免二次改同一批文件

## ledger-import-view-refactor 三件套一致性审查（2026-05-10）

- **审查方法沉淀（可复用规约）**：大 spec 三件套必须逐条需求对照矩阵审查 design/tasks 覆盖度，分 ✅ 完整覆盖 / ⚠️ 设计薄弱 / ❌ 完全遗漏 三档；审查表应在 tasks.md 末尾归档便于后续查
- **审查发现 18 条缺口**：F6-F11 识别引擎 6 条原在 design/tasks 完全遗漏（只做 B' 视图改造忽略 9 家样本识别引擎需求）；F3/F4/F5 基础运维设计薄弱；F28/F29/F31/F42/F43/F44 占位式任务无对应设计
- **补齐动作**：design.md 追加 D23-D32 共 10 个新架构决策（含代码骨架）；tasks.md 追加 Sprint 10 共 53 任务分 A/B/C 三批次
- **关键技术决策**：(1) Sprint 10 批次 B（识别引擎 F6-F11）必须前置到 Sprint 4 之前，否则 detect 相关任务隐性依赖风险；(2) F5 跨年度风险点 = `mark_previous_superseded` 查询必须加 year 条件；(3) F29 配套 `@retry_on_serialization_failure` 装饰器 + 幂等键双重保护
- **三件套最终状态**：F1-F53 × design/tasks 双向覆盖率 100%，总任务 224 / 总工时 43 人天 / 10 Sprint
- **spec 工作流新规约**：requirements 每次扩展后，必须做一次三件套一致性对照审查才能进入实施

## ledger-import-view-refactor 二次一致性审查（2026-05-10）

- **审查方法论升级（重要规约）**：三件套审查必须**双向**做——既从 requirements 向 design/tasks 查覆盖，也从 design/tasks 的编号反查 requirements 是否真定义了对应条目；单向只做前者会漏"引用了不存在条目"这类内部不一致问题
- **二次审查发现 16 处新遗漏**：(1) 9 个测试任务在 tasks.md 无编号（§4.1/§4.2 列的 test_dataset_service_activate/rollback_view_refactor/test_progress_callback_granularity/test_duration_estimator/test_dataset_concurrent_isolation/test_rollback_full_flow/test_resume_from_activation_checkpoint/test_metrics_endpoint/test_migration_day7_update）；(2) 7 处 requirements 内部引用错误（O10-O14/O15/O17 引用了从未定义的 F30/F33/F34/F36/F37/F38）
- **F 编号跳号陷阱**：第 4 轮扩展时为避开冲突跳过 F33-F39 间隔，但排除表里占位符"（F30）等"没同步清理；下次 spec 扩展时如果跳号，必须同步清理所有引用该编号的位置
- **修正动作**：requirements 修正 7 处内部引用（O15→F41 / O17→F45 / O10-O14 去除无效占位）；tasks.md 追加 Sprint 11（9 测试任务 + 修正记录归档）
- **三件套最终状态**：233 任务 / 44 人天 / 11 Sprint；F1-F53 × design + tasks 双向覆盖率 100%；O1-O22 零内部引用残留；§4 测试矩阵 32 个测试文件全部有任务编号

## ledger-import-view-refactor 实施进度（2026-05-10）

- **Sprint 1 完成（26/26 task，业务查询迁移）**：15 个 service + 2 个 router 的 40+ 处 `TbX.is_deleted == False` 全部迁移到 `get_active_filter`；6 处 raw SQL 改为 EXISTS 子查询；grep 验证通过（剩余 6 处是 year=None 兜底分支 Template B 模式，设计文档明确保留）；82+ 测试通过
- **Sprint 2 核心完成（tasks 2.1-2.5）**：`get_filter_with_dataset_id` 同步版本新增（dataset_query.py）；`DatasetService.activate/rollback` 去除 `_set_dataset_visibility` 调用；`_set_dataset_visibility` 改 no-op + logger.warning；pipeline `_insert` 写入改 `is_deleted=False`；36 测试通过
- **Sprint 2 剩余（2.6-2.8）**：E2E 验证需真实 PG + 样本数据（YG4001 smoke / YG36 / YG2101 perf），需手动执行
- **Sprint 3-11 待执行**：加固+文档 / 大文档健壮性 / 云协同 / 数据正确性 / 安全 / 校验透明化 / 最终验收 / 一致性补齐 / 测试矩阵，共 ~200 任务
- **关键发现**：`dataset_service.py` 和 `dataset_query.py` 已经是 B' 架构（代码在之前的 Sprint 中已部分实现），本轮实施主要是确认+补全+验证
- **taskStatus 多行任务名限制**：tasks.md 中含换行的任务描述无法被 taskStatus 工具匹配，需用精确单行文本；Sprint 2 的 2.1-2.4 因多行描述无法直接标记状态

## ledger-import-view-refactor Sprint 3-4 进度（2026-05-10）

- **Sprint 3 完成（5/6 task，加固 + 文档）**：(1) CI backend-lint job 新增 B' guard 扫 `Tb(Balance|Ledger|AuxBalance|AuxLedger)\.is_deleted\s*==` 命中 > baseline(6) 即 fail；(2) `backend/tests/integration/test_dataset_rollback_view_refactor.py` 4 用例（rollback 语义 + 并发项目隔离）；(3) `docs/adr/ADR-002-ledger-view-refactor.md` 归档 B' 视图重构架构决策；(4) architecture.md 新增"账表导入可见性架构"章节；(5) conventions.md 新增"账表四表查询规约"（强制 `get_active_filter` + raw SQL EXISTS 模板 + year=None 允许清单）
- **Sprint 4 P0 完成（13/18 task）**：4.1 `ProgressState`/`_maybe_report_progress` 按 5%/10k 行节流（F13）/ 4.2 `phases.py` + pipeline `_mark` 透过 `phase_marker` 回调异步写 `ImportJob.current_phase`（F14）/ 4.3 `ImportJobRunner.resume_from_checkpoint` 路由表 + `POST /jobs/{id}/resume` 端点 / 4.6 `pipeline._handle_cancel` 清理链（cleanup_rows + mark_failed + artifact consumed）/ 4.7 `recover_jobs` 扫 canceled+staged 孤儿清理 / 4.8 `test_cancel_cleanup_guarantee.py` 4 用例 / 4.9 `backend/app/services/ledger_import/metrics.py` 5 Prometheus 指标 + stub fallback（不强制装 prometheus_client）/ 4.10 `/metrics` 端点挂 main.py / 4.13 `duration_estimator.py` 4 档估算 + detect 响应扩展 `total_rows_estimate/estimated_duration_seconds/size_bucket` / 4.15 feature_flag `ledger_import_view_refactor_enabled=True` / 4.16 Alembic `view_refactor_cleanup_old_deleted_20260517.py` 分块 UPDATE / 4.18 `test_b_prime_feature_flag.py` 9 用例
- **Sprint 4 剩余**：4.4/4.5 前端（"恢复导入"按钮 + 卡住阈值 30s）/ 4.11/4.12 `/health/ledger-import` 端点 / 4.14 前端 DetectionPreview"预计耗时 X 分钟"展示
- **测试全绿**：120 passed + 3 skipped（PG-only Alembic round-trip）；Sprint 1-4 backend P0 代码改动 zero getDiagnostics errors
- **关键技术决策**：
  - (1) `_set_dataset_visibility` 已在之前 sprint 中 no-op 化，本次 Sprint 2 完成 activate/rollback 去除调用路径（三件套所列"2.2/2.3"在代码层是验证而非新改）
  - (2) `phase_marker` 采用 fire-and-forget `asyncio.create_task`：phase 持久化失败不阻断主管线（业务逻辑优先级 > 可观测性）
  - (3) `resume_from_checkpoint` 策略：标记 queued + enqueue 全量重跑；pipeline 的 activate/rebuild 都是幂等操作（metadata UPDATE + summary rebuild），已完成阶段重跑安全
  - (4) `ImportArtifact` 无 `job_id` 列，cancel 清理链需走 `ImportJob.artifact_id` 反查（而非 `ImportArtifact.job_id`）
  - (5) metrics 模块 `_PROMETHEUS_AVAILABLE` 双分支 + `_Stub` 类：即使 `prometheus_client` 未装也不破坏 import，`/metrics` 返回说明文案
  - (6) 4.15 feature_flag 默认 `True`（因为 B' 代码已部分上线），实际意义是"项目级降级开关"而非"启用开关"
- **taskStatus 工具限制发现**：多行任务描述（带 `\n  - 细节`）无法被精确匹配，必须用单行文本或直接编辑 tasks.md 的 `- [ ]` → `- [x]`
- **property-based 测试速度规约（2026-05-10 扩展）**：`test_production_readiness_properties.py` + `test_phase0_property.py` + `test_phase1a_property.py` + `test_remaining_property.py` 已降到 `max_examples=3-5`；`test_audit_log_hash_chain_property.py` 50→10、`test_aux_dimension_property.py` 200→20/100→20/50→10；MVP 阶段速度优先，新增 PBT 默认 `max_examples=5`（算法测试）/ 10-20（加密/哈希链等需更多反例），稳定后再调高；全部 116 PBT 测试从 backend/ cwd 跑 ~7.3s 全绿
- **pytest cwd 硬约定**：`test_phase0_property.py::TestFrontendIntegrationProperty` 用相对路径 `../audit-platform/frontend/...` 检查前端 token/store 存在，**必须** 从 `backend/` cwd 跑（repo root 跑会 2 failed，artifact 非 bug）；CI 和本地统一 `cd backend; pytest` 或 `pytest` + `cwd=backend`
- **ledger-import-view-refactor Sprint 10 批次 B 完成（F6-F11 识别引擎强化）**：
  - F6 文件名元信息：`detector._extract_filename_hints(filename)` 返回 `{table_type, table_confidence, matched_keyword, year, month, file_stem}`；`identify()` 在 L1 sheet 名得分 < 60 且 filename_hint.table_type 存在时覆盖 L1 score
  - F7 方括号/组合表头：`detector._normalize_header(cell)` 剥 `[]`/`【】` + 识别 `#|@` 分隔的组合字段；`_normalize_header_row` 返回 `(normalized_cells, compound_headers)`；`identify()` 对未映射的 compound 列用子字段试别名（只选未占用的 standard_field，避免抢占已映射列）
  - F8 表类型鲁棒性：`_GENERIC_SHEET_NAMES` = `{sheet1, sheet2, 列表数据, 数据, data, 工作表1, sheet}` 查询时不扣分只不加分；L1 锁定机制加入 aux variant 例外——当 L1=balance 但 L2=aux_balance（L2 score ≥ 60）时不锁，让更具体的 L2 胜出（"科目余额表（有核算维度）" 修复）
  - F9 unknown 透明化：`_derive_skip_reason(sheet)` 生成 `{code, message_cn}`，3 档 code = `ROWS_TOO_FEW` / `HEADER_UNRECOGNIZABLE` / `CONTENT_MISMATCH`；写入 `detection_evidence["skip_reason"]` + `warnings` 追加 `SKIPPED_UNKNOWN:<code>` tag
  - F10 CSV 大文件：`iter_csv_rows_from_path` 已有流式实现，新增 `test_large_csv_smoke.py` 合成 100MB 验收（slow 标记）
  - F11 9 家样本 header 快照：`backend/tests/fixtures/header_snapshots.json` 5 家（YG36/YG4001/和平药房/和平物流/安徽骨科）+ `test_9_samples_header_detection.py` 参数化；`scripts/_gen_header_snapshots.py` 用于再生（未来样本增加时跑）
- **关键技术决策（F6-F11 落地沉淀）**：
  - (1) `detection_evidence` 作为 dict 扩展点比 Pydantic 字段更灵活，新增 `filename_hint` / `compound_headers` / `skip_reason` / `header_cells_raw` 等不需要改 schema
  - (2) 组合表头子字段匹配只在"主列未映射"时触发，避免 `[凭证号码]#[日期]` 抢占独立列 `[日期]` 的 voucher_date 映射（和平物流曾因此产出 0 ledger 行）
  - (3) L1 lock 例外的 aux variant pair：`{(balance, aux_balance), (ledger, aux_ledger)}` —— L1 sheet 名对这两对来说覆盖过宽（"余额表" 正则也匹配 "有核算维度余额表"），须让 L2 具体列（aux_type）决定
  - (4) 文件名年月正则必须按优先级列出多条（`\d{2}年\d{1,2}月` 优先于 `\d{2,4}[./\-_]\d{1,2}`），单一模糊正则会把 "25年10月" 错解为 year=2510/month=1
  - (5) `_DIRECTION_VALUES` 包含 `{'1','-1','借','贷','d','c'}`，纯数字序号列会误触发 L3 direction 信号；测试用例写非数字占位符（`xx/yy/zz`）避免
- **ledger-import-view-refactor Sprint 10 批次 A + 批次 C 完成**（20 tasks / 254 passed / 0 regression）：
  - **批次 A（F3 purge / F4 审计轨迹 / F5 跨年度）**：`DatasetService.purge_old_datasets(pid, *, year=None, keep_count=3)` + `purge_all_projects` + `dataset_purge_worker.py`（每晚 03:00 + REINDEX CONCURRENTLY 4 个 `active_queries` 索引，PG only / SQLite 跳过）+ 注册到 `_start_workers`；`activate()` 补齐 `ip_address/duration_ms/before_row_counts/after_row_counts/reason` 5 字段；`mark_previous_superseded` 查询必须**同时带 project_id + year**（否则跨年误标 — F5 风险点）；修复 `ledger_datasets.py` 重复定义 `GET /datasets/history` 端点（FastAPI 静默覆盖导致 bug）
  - **批次 C（F28/F29/F43/F44 补齐）**：`ADR-003-ledger-import-recovery-playbook.md`（8 故障场景 copy-paste 诊断+恢复命令）+ `ADR-004-ledger-activate-isolation.md`（REPEATABLE READ + 幂等 + 重试 3 决策）+ `backend/app/services/retry_utils.py` 的 `@retry_on_serialization_failure(max_retries, initial_delay_ms, max_delay_ms)` 装饰器（识别 SQLSTATE 40001/40P01 + asyncpg `SerializationError` 类名 / 指数退避 + 抖动 0.5-1.5x）+ activate 幂等保护（`dataset.status == active` 直接返回不抛异常，resume 场景友好）+ `ImportJobRunner.run_forever(stop_event=...)` 协同停机（`asyncio.wait_for(stop_event.wait(), timeout=interval)` 可中断睡眠）+ `/api/health/ledger-import` 端点（queue_depth / active_workers / p95_duration_seconds / pool 使用率 → 3 态 healthy/degraded/unhealthy + 同步 `HEALTH_STATUS` gauge）
- **Sprint 10 架构决策（新增）**：
  - (1) `dataset_purge_worker` 保留策略 = 同 `(project_id, year)` 最近 N=3 superseded，active/staged/rolled_back/failed 永不触碰（rolled_back 作 UAT 审计证据保留）
  - (2) 幂等 activate 入口第一行判断：`if dataset.status == DatasetStatus.active: return dataset`；`resume_from_checkpoint` 重跑 activate 不再因"not staged"失败
  - (3) `JobStatus.interrupted` 新状态**延后不做**（需 PG enum migration + 全状态机改造），依赖现有 `recover_jobs` heartbeat 超时兜底 95% 场景足够
  - (4) `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` 同样延后（需 PG-only 代码路径，SQLite 无等价），先用项目级锁 + 幂等键保证一致性
  - (5) 健康端点 `_estimate_p95_seconds()` 用 Histogram bucket 边界近似 P95（prometheus_client 不直接暴露分位数），第一个 cumulative count >= 0.95*total 的 bucket `le` 值即近似
  - (6) REINDEX CONCURRENTLY 需 AUTOCOMMIT 模式（不能在 transaction 中），用 `async_engine.connect()` + `raw_connection.driver_connection.execute` 绕过事务
- **FastAPI 路由重复定义陷阱（新）**：同一 path + HTTP method 定义两次时，后者静默覆盖前者**没有警告**；code review 或 `scripts/dead-link-check.js` 都不会捕捉；本轮发现 `ledger_datasets.py` 重复了 `GET /datasets/history`（Sprint 5.19 和更早版本重复了），修复时只保留一份即可
- **Sprint 6 数据正确性 + UX（12 tasks 后端完成）**：`staged_orphan_cleaner` worker 每小时扫 staged >24h + 无活跃 job 关联 → mark_failed；`DatasetService.activate` 加 integrity check（record_summary 各表预期行数 vs 实际 COUNT(*) dataset_id 过滤，不符抛 `DatasetIntegrityError`）；`error_hints.py` 32 条 ErrorHint（title/description/suggestions 2-4 条/severity）与 `ErrorCode` 枚举 1:1 CI 强制；`/jobs/{id}/diagnostics` 响应 findings + blocking_findings 数组每条附 hint 字段（`enrich_finding_with_hint`）
- **ImportJob / LedgerDataset 关联方向硬约定**：`ImportJob` **没有** `dataset_id` 字段；关联是单向 `LedgerDataset.job_id → ImportJob.id`（一个 job 产一个 dataset）；孤儿扫描 SQL 必须用 `NOT EXISTS (SELECT 1 FROM import_jobs WHERE id = LedgerDataset.job_id AND status IN active_statuses)`，方向反了会 TypeError
- **ImportJob 无 upload_token 字段**：`upload_token` 在 `ImportArtifact` 表；ImportJob 通过 `artifact_id` FK 关联到 artifact；测试 fixture 构造 ImportJob 时不要传 upload_token
- **ErrorCode 实际 32 条不是 31 条**（requirements spec 历史写错）：5 fatal + 9 blocking + 11 warning + 3 info + 4 通用码；F32 的 error_hints 对应覆盖全 32 条
- **integrity check 语义规约**：activate 前 `record_summary` 含 `tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger` 四 key 时才触发 check；其他 key 如 `validation_warnings`/`aux_types_detected` 被静默忽略；不传 record_summary 则跳过（向后兼容）
- **`enrich_finding_with_hint(dict)` 合约**：未登记的 code / 无 code 字段 / hint=None 都静默原样返回（不抛异常），用于安全的 findings 数组 map；避免 lookup miss 导致整个 diagnostics 端点失败
- **CI grep 卡点 baseline 硬约定**：B' `TbX.is_deleted==` baseline=6（year=None 兜底分支），新增查询必须走 `get_active_filter`，不能给这 6 个允许清单扩容
- **`test_property_14_no_hasattr_patch_remaining` 路径兼容性**：用 `Path(__file__).resolve().parent` 解析 router_registry.py，支持 cwd=repo root 或 cwd=backend 两种运行方式
- **`test_property_14_all_business_routes_under_api` 新增 `/metrics` 例外**：Prometheus 标准路径不是业务路由，跟 `/wopi/docs/openapi.json/redoc` 同级加入例外列表
- **临时文件清理**：`scripts/_analyze_9_samples.py` + `sample_analysis.txt` 是 2026-05-10 下午 17:45 留的一次性分析产物，未来下一轮启动时可删除

## ledger-import-view-refactor Sprint 7 批次 A/B/C 完成（2026-05-10）

- **批次 A（F40 上传安全，4 tasks / 7.1-7.4）**：新建 `backend/app/services/ledger_import/upload_security.py`（~370 行）+ `test_upload_security.py` 8 用例全绿；MIME magic（python-magic 可选，PK\x03\x04 字节签名兜底）+ 大小上限（xlsx ≤ 500MB / csv ≤ 1GB / zip ≤ 200MB）+ xlsx 宏（vbaProject.bin）/ 外链（externalLinks/）/ zip bomb（解压/压缩 > 100×）拒绝；集成到 `ledger_import_v2.py::detect_files` + `ledger_import_application_service.py::resolve_file_sources`；audit log 走 `audit_logger_enhanced.audit_logger.log_action`（哈希链落 `audit_log_entries` 表）
- **批次 B（F41 tenant_id 预留，2 tasks / 7.5+7.8）**：Alembic `view_refactor_tenant_id_20260518`（down=view_refactor_activation_record_20260523）5 表（tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger/ledger_datasets）加 `tenant_id VARCHAR(64) NOT NULL DEFAULT 'default'` + `idx_{table}_tenant_project_year` 复合索引；ORM 模型同步；`test_cross_project_isolation.py` 4 用例验证 project_id 过滤仍是隔离底线；**7.6/7.7 `get_active_filter` 签名 + 40+ 调用点改造延后**（触发面太大独立 Sprint）
- **批次 C（F42 scale warnings + force_submit 门控，6 tasks / 7.9-7.11+10.42-10.44）**：新建 `backend/app/services/ledger_import/scale_warnings.py`（`EMPTY_ROW_THRESHOLD=10` / `SUSPICIOUS_MIN_RATIO=0.1` / `SUSPICIOUS_MAX_RATIO=10.0`，历史均值从 `LedgerDataset.record_summary` 四表行数累加，首次导入无基线跳过 SUSPICIOUS）；`ImportJob.force_submit` 字段 + Alembic `view_refactor_force_submit_20260524`（down=view_refactor_tenant_id_20260518）；`/detect` 响应追加 `scale_warnings`；`/submit` 端点**服务端重新跑 detect_from_paths 再算一次 warnings**（防前端伪造 force_submit 绕过），warnings+!force_submit → HTTP 400 `SCALE_WARNING_BLOCKED`；`test_empty_ledger_rejection.py` 7 用例
- **测试全绿**：ledger_import 套件 222+ passed / 4 skipped（PG-only Alembic round-trip）；所有新建文件 getDiagnostics 零错误

## Sprint 7 关键技术决策沉淀

- **submit 门控服务端重新计算原则**：凡是"前端可绕过"的 boolean flag（force_submit / skip_validation 等），后端必须独立重算触发条件，不能只信任请求体字段；防客户端伪造（修改 js）绕过 gate
- **tenant_id 预留迁移不等于启用**：只加列 + 索引，`get_active_filter` 签名保持不变；40+ 调用点补 `current_user` 是独立 Sprint（触发面大，需整体 review）；ORM 模型和 Alembic 保持 server_default='default'，老行自动填充无需数据迁移
- **python-magic 可选依赖策略**：Windows 部署难装 libmagic，upload_security.py 用"try import + 字节签名兜底"双分支；`_try_magic` 捕获所有异常降级，`_detect_type` 用 `PK\x03\x04` 魔数 + 文件扩展名兜底
- **审计日志入口**：`audit_logger_enhanced.audit_logger.log_action(user_id, action, object_type, object_id, project_id, details, ip_address)` 是全平台审计唯一入口，哈希链落 `audit_log_entries` 表；`audit_logs` 是简单日志表历史遗留，新代码不要用
- **ErrorCode 复用（non-upload 场景）**：上传拒绝的 `reason` 映射表已在 upload_security.py 内部维护（`_REASON_TO_ERROR_CODE`），macro_detected / external_links_detected 暂复用 `UNSUPPORTED_FILE_TYPE` 近似（ErrorCode 无专用枚举）

## PBT 测试速度二次优化（2026-05-10）

- `test_audit_log_hash_chain_property.py` 4 个 tests 从 `max_examples=10` 降到 `5`；`test_aux_dimension_property.py` 3 个 tests 从 `20` 降到 `10`，1 个 tests 从 `10` 降到 `5`
- **116 PBT 测试 6.14s 通过**（从 7.3s 降到 6.14s，-16%）
- **MVP 阶段 PBT 速度规约更新**：算法测试默认 5 / 加密哈希链等需更多反例的降到 5-10（原 10-20 偏慢）；新增 PBT 建议 `max_examples=5` 起步，有误报率问题再调高
- **微调 PowerShell 输出捕获**：大命令输出被 shell 截断时用 `Tee-Object -FilePath x.log | Select-Object -Last 20` 保证能看到尾部测试结果；完成后 `deleteFile` 清理临时 log

## Subagent 调用可靠性观察（2026-05-10）

- **subagent 高并发期间会报 `read ECONNRESET` / `Encountered unexpectedly high load`**：临时服务错误，等 30s 后重试通常能通过；不需要降低任务粒度
- **建议每批 subagent 任务数 ≤ 6**：单次 prompt 太长会触发 token 超限；拆分成"批次 A/批次 B/批次 C" 3-4 任务一批更稳
- **subagent 任务描述关键节点**：(1) 明确告知 `down_revision` 具体值（当前 HEAD 不让 subagent 猜）；(2) 列出"skip tasks"避免它自作主张做延后任务；(3) 文件路径用相对仓库根；(4) 指明测试要跑通 + getDiagnostics 兜底

## ledger-import-view-refactor Sprint 9 + 11 完成（2026-05-10）

**Sprint 11（测试矩阵补齐）9 / 9 文件全绿，合计 62 测试 + 2 skip（本地缺 prometheus_client）**：
- 11.1 `test_dataset_service_activate_view_refactor.py`（6 用例）：activate metadata 翻转 + 物理行 is_deleted 不变 + 幂等 + ActivationRecord 审计 + outbox 事件 + 非 staged 拒绝
- 11.2 `test_dataset_service_rollback_view_refactor.py`（5 用例）：rollback metadata 翻转 + 物理行不动 + ActivationRecord + DATASET_ROLLED_BACK outbox + 无 previous 返回 None
- 11.3 `test_progress_callback_granularity.py`（8 用例）：ProgressState 按 5%/10k 行节流 + cb=None no-op + total=0 不触发 + 幂等 + 2M 行大文档 10k 行阈值
- 11.4 `test_duration_estimator.py`（扩展）：9 家真实样本参数化覆盖 S/M/L/XL 四档（YG4001/YG36/宜宾大药房/和平药房/辽宁卫生/医疗器械/安徽骨科/陕西华氏/和平物流/YG2101）
- 11.5 `test_dataset_concurrent_isolation.py`（4 用例）：A staged + B active 不互污 + 同项目 staged 不影响 active 视图 + 多项目 active 隔离 + 多年度 active 并存
- 11.6 `test_rollback_full_flow.py`（2 用例）：V1→V2→rollback→V1 + rollback→reactivate V3 链式；全程 is_deleted=false、物理行不减、ActivationRecord 3 条
- 11.7 `test_resume_from_activation_checkpoint.py`（5 用例）：phase=activation_gate_done → resume_from_activate_dataset 路径；staged dataset 可重新 activate；activate 幂等；phase_routes 完备性
- 11.8 `test_metrics_endpoint.py`（5 用例）：/metrics 200 响应 + 3 核心指标名 + observe_phase_duration 数据点可见 + prometheus_client 缺失时降级
- 11.9 `test_migration_day7_update.py`（10 用例）：迁移源代码结构检查 + SQLite 环境 no-op + 等价 UPDATE 幂等 + 只翻转 active dataset 行（superseded/rolled_back 不动）

**Sprint 9 文档 + 运维（4/4 任务完成）**：
- 9.4 `docs/EXPLAIN_ANALYZE_VIEW_REFACTOR.md`：5 条代表性查询（Q1 单科目/Q2 年度聚合/Q3 辅助多维/Q4 L3 比对/Q5 integrity check）+ 改造前后 SQL + 索引使用 + YG2101 基准 + Day 0/7/30 灰度验证 checklist
- 9.5 `.github/workflows/ci.yml` 新增 3 个 backend-lint gate：(a) F40 upload_security call grep（ledger_import_v2.py + ledger_import_application_service.py 必须命中 validate_upload_safety）；(b) F48 validation_rules_catalog 双向一致性测试（test_validation_rules_catalog.py）；(c) F32/F48 错误提示覆盖率（test_error_hints.py）。既有 F2 Tb*.is_deleted== baseline=6 保持不变
- 9.6 `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 扩展章节 9（可见性架构）+ 10（下游绑定）：127s→<1s 对比、get_active_filter 签名、force_dataset_id 语义、rollback 保护、retention_class 三档、force-unbind 逃生舱、下游 stale 联动
- 9.7 memory.md（本文）归档 Sprint 9+11 完成 + 待完成项清单；architecture.md + conventions.md 既有"账表导入可见性架构"+"账表四表查询规约"章节无需更新（Sprint 3 已落地）

**Sprint 9 跳过项（运维/真实环境范畴）**：
- 9.1 `test_huge_ledger_smoke.py` 500MB 合成样本（需 PG + 真实环境）
- 9.2 9 家真实样本 E2E（需 `数据/` 目录）
- 9.3 `b3_diag_yg2101.py` activate <1s + total <250s（需真实 YG2101 xlsx + PG）
- 9.8 UAT 手动清单
- 9.9 / 9.10 灰度部署 Day 0/3/7/30 + DROP 废弃索引

**本 spec 已归档状态**：F1-F53 双向覆盖 design + tasks + 测试；主干代码走 get_active_filter；pipeline 写 is_deleted=false；activate/rollback 只改 metadata；CI 三层卡点（F2 + F40 + F48）防回归；下游绑定 F50 合规闭环；retention_class F53 保留期策略；event_outbox 云协同（activate/rollback 广播）

**spec 工作流规约再沉淀**：
- 大 spec 有 40+ 需求时，任务执行子 agent 每批 ≤ 9 任务，给明确 "Skip tasks" 列表避免僭越
- 测试文件任务描述里必须指明 SQLite in-memory fixture 复用邻居模板（避免每文件独立造轮）
- TbLedger/TbAuxLedger 插入必须带 voucher_date + voucher_no（NOT NULL），SQLite 报错 "NOT NULL constraint failed" 是常见踩坑
- ActivationRecord 时间字段是 `performed_at` 不是 `created_at`（无 `created_at` 列）；涉及时间排序时查准字段名
- 迁移源码 downgrade 常含 docstring 提及"UPDATE"等关键字，test 做反向检查时需先剥离 docstring 再 grep

## ledger-import-view-refactor Sprint 7 D/E + Sprint 8/11 + Sprint 9 文档完成（2026-05-10）

- **Sprint 7 批次 D（F44 graceful shutdown）**：`import_worker._install_signal_handlers(stop_event)` 双路径（Unix 走 `loop.add_signal_handler`，Windows 抛 `NotImplementedError` 时回退 `signal.signal` + `call_soon_threadsafe`）；`ImportJobRunner._stop_event` 类级指针供 pipeline `_cancel_check` 读；`test_worker_graceful_shutdown.py` 8 用例；7.14/7.15 `JobStatus.interrupted` 枚举依赖 PG migration 延后，依赖 `recover_jobs` heartbeat 兜底 95% 场景
- **Sprint 7 批次 E（F45 DLQ + F46 rollback 下游 stale）**：`event_outbox_dlq` 表（original_event_id FK→outbox ON DELETE SET NULL + partial index `resolved_at IS NULL`）；`ImportEventOutboxService._move_to_dlq` + `dlq_depth()`；`outbox_replay_worker` 每轮调 `set_dlq_depth()` 刷新 gauge；同 Alembic 迁移里 `audit_report`+`disclosure_notes` 新增 `is_stale` 列（Workpaper 已有 `prefill_stale` 复用）；`DatasetService.rollback` outbox payload 双键（历史键 `rolled_back_dataset_id/restored_dataset_id` + F46 新键 `project_id/year/old_dataset_id/new_active_dataset_id`）；`_mark_downstream_stale_on_rollback` handler 订阅 `LEDGER_DATASET_ROLLED_BACK`
- **Sprint 8 批次 A（F47 validation explanation，6 tasks）**：5 个 Pydantic explanation 子 model（`ExplanationBase` / `BalanceMismatchExplanation` / `UnbalancedExplanation` / `YearOutOfRangeExplanation` / `L1TypeErrorExplanation`）；`ValidationFinding.explanation: SerializeAsAny[ExplanationBase] | None`（`SerializeAsAny` 是关键，否则子类特有字段 `diff_breakdown/sample_voucher_ids/year_bounds` 在 API JSON 输出中被基类 schema 截断）；validator 函数实际命名是 `validate_l1/l2/l3`（spec 文案的 `validate_l3_cross_table/validate_l2_balance_check/validate_l2_ledger_year` 是描述性名称，非真实函数名）；13 测试全绿
- **Sprint 8 批次 B+C（F48 catalog + F49 drill_down，6 tasks）**：`VALIDATION_RULES_CATALOG` 实际 **10 条规则**（spec 写的 "31 条" 是历史错估；validator.py 实际只 emit 10 个 code，文件上传/detect 阶段 fatal 码已由 `error_hints.py` 覆盖不重复）；`ValidationRuleDoc` Pydantic model 11 字段；`test_validation_rules_catalog.py` 用 regex grep validator.py 源码做 **双向一致性** 测试（catalog ↔ validator emit 集合完全相等）；`location["drill_down"] = {target, filter, sample_ids, expected_count}` 仅 L3 填充；`/api/ledger-import/validation-rules` + `/{code}` 两端点
- **Sprint 8 批次 D（F50 下游绑定，10 tasks，合规关键）**：Alembic 迁移给 4 张下游表（`working_paper/audit_report/disclosure_notes/unadjusted_misstatements`）加 `bound_dataset_id UUID FK → ledger_datasets ON DELETE RESTRICT` + `dataset_bound_at TIMESTAMPTZ` + partial index `WHERE bound_dataset_id IS NOT NULL`；ActivationType 枚举扩展 `force_unbind`（PG enum ALTER 需 `autocommit_block()`）；`bind_to_active_dataset(db, obj, pid, year)` async + `bind_to_active_dataset_sync` 老 service 用；实际 workpaper 创建函数是 `generate_project_workpapers`（不是 spec 写的 `generate_workpaper`，批量生成模板后统一 bind）；`AuditReport.transition_to_final` + `sign_service._transition_report_status` order=5 双入口绑定，幂等保护（`bound_dataset_id is None` 才覆盖）；`DatasetService.rollback` 409 `SIGNED_REPORTS_BOUND`；`POST /api/datasets/{id}/force-unbind` 双人授权端点（自审批拒绝/非 admin 审批拒绝/成功后 final→review + bound 字段清空 + ActivationRecord action=`force_unbind`）；13 测试全绿
- **Sprint 8 批次 E（F51 全局并发限流 + 内存降级，6 tasks）**：`GlobalImportConcurrency` 双路径（Redis `INCR/DECR/EXPIRE 7200s` + asyncio.Lock 本地 fallback，Redis 一次失败永久降级）；env `LEDGER_IMPORT_MAX_CONCURRENT` 默认 3；**enqueue 签名保持 sync classmethod 不变**——`try_acquire` 放在 `_execute` 内而非 `enqueue`，对所有 caller 零侵入；slot 粒度 = claim 之后（避免同项目排队占用全局槽）；claim 失败/异常/完成三路径都 release；`/active-job` 端点 queued/pending 时附 `queue_position`（1-indexed）+ `global_max_concurrent`；`pipeline._detect_memory_pressure` 读 `psutil.virtual_memory().percent > 80` → `use_calamine_global=False` + `CHUNK_SIZE=10_000`，psutil 未装/查询失败静默跳过；fakeredis.aioredis + monkeypatch `_get_redis` 避开真 Redis
- **Sprint 8 批次 F+G（F52 mapping 复用 + F53 retention，9 tasks）**：`ColumnMappingService.build_file_fingerprint(sheet, cells, hint)` = `SHA1(normalized_sheet + "|" + "|".join(normalized_first_20_cells) + "|" + normalized_hint)`，`normalized = str(x or "").strip().lower()`；`ImportColumnMappingHistory` 加 `file_fingerprint VARCHAR(40)` + `override_parent_id UUID FK self ON DELETE SET NULL`；30 天命中窗口 `DEFAULT_FINGERPRINT_REUSE_WINDOW = timedelta(days=30)`；`ColumnMatch` 加 `auto_applied_from_history: bool = False` + `history_mapping_id: str | None` + source 枚举加 `"history_reuse"`；mapping 字典方向判定用 ASCII snake_case 启发式（原版用 `isalnum()` 对中文误判有 bug）；`ImportArtifact` 加 `retention_class VARCHAR(20) DEFAULT 'transient'` + `retention_expires_at TIMESTAMPTZ NULL`；`compute_retention_class(db, dataset)` 优先级 legal_hold > archived > transient；`compute_expires_at` 三档（transient 90d / archived 10y / legal_hold None）；**LedgerDataset.legal_hold_flag 不存在（grep 零匹配）**，过渡用 `source_summary["legal_hold"]` JSON 键（支持 bool / "true"/"1"/"yes"/"y"/"on"）；`purge_old_datasets` 扩展两道过滤：`skipped_due_to_binding`（4 张下游表 bound_dataset_id）+ `skipped_due_to_retention`（archived/legal_hold 不动）；33 测试全绿
- **Sprint 11 测试矩阵 + Sprint 9 文档（13 tasks）**：9 个 Sprint 11 测试文件共 **62 passed + 2 skipped**（prometheus_client 未装时 skip 2 个 /metrics 测试）；`docs/EXPLAIN_ANALYZE_VIEW_REFACTOR.md`（323 行 / 11.1 KB 新建）；`docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 新增 §9 可见性架构 + §10 下游绑定（408 行 / 16.6 KB）；CI `backend-lint` job 3 gate 全激活（F2 `Tb*.is_deleted==` baseline=6 / F40 `validate_upload_safety` 调用 grep / F48 `test_validation_rules_catalog.py` 双向一致性）

## 关键技术事实（Sprint 7-11 沉淀）

- **Alembic 迁移链（本 spec 完整序列）**：`view_refactor_activation_record_20260523` → `view_refactor_tenant_id_20260518` → `view_refactor_force_submit_20260524` → `event_outbox_dlq_20260521` → `view_refactor_dataset_binding_20260519` → `view_refactor_mapping_history_fp_20260525` → `view_refactor_retention_class_20260526`
- **HTTPException.detail 到响应字段映射**：全局 `http_exception_handler` 把 `HTTPException.detail` 放到 **`message` 字段**（不是 `detail`），前端/测试读 `resp.json()["message"]["error_code"]` 而非 `resp.json()["detail"]["error_code"]`；2xx 成功响应被 `ResponseWrapperMiddleware` 包装为 `{code, message, data}` 结构，数据在 `data` 字段
- **Pydantic SerializeAsAny 硬约定**：基类字段类型为 `SomeBase | None`，赋子类实例时 `model_dump()` 默认只序列化基类 schema（子类字段丢失）；必须用 `SerializeAsAny[SomeBase | None]` 才保留子类特有字段——本 spec explanation 字段、Tasks future 任何 base+subclass discriminator 场景都必须用此 pattern
- **PG enum ALTER 硬约定**：`ALTER TYPE xxx ADD VALUE` 不能在 transaction 内执行，Alembic 迁移用 `with op.get_context().autocommit_block(): op.execute(...)` 绕过；SQLite 不支持原生 enum（建表时按字符串存），跳过此步
- **workpaper 实际创建函数命名**：`generate_project_workpapers`（不是 spec 文案的 `generate_workpaper`），批量按 template_set_id 生成，绑定时批量调 `bind_to_active_dataset` 后统一 flush
- **ActivationRecord 时间字段**：`performed_at`（不是 `created_at`；此模型没有 `created_at` 列），写 fixture 时注意
- **TbLedger/TbAuxLedger 必填列差异**：TbLedger `voucher_date/voucher_no` 都是 NOT NULL；TbAuxLedger 这两列 nullable；SQLite fixture 会按此报 IntegrityError
- **psutil 依赖状态**：当前 venv 已装 7.2.2，但 `requirements.txt` 未强制；`pipeline._detect_memory_pressure` 用 try/except 兜底，未装则永不降级
- **prometheus_client 依赖状态**：metrics 模块有 `_Stub` 类双分支，未装不阻断 import；`/metrics` 端点返回降级说明；test_metrics_endpoint.py 有 `_prom_available()` helper 优雅 skip
- **fakeredis 测试依赖**：`fakeredis.aioredis` 用于 test_global_concurrency_limit.py 避开真 Redis；若 CI 未装该依赖，tests 会 skip 而非 fail

## Spec 工作流沉淀（本次大批量执行）

- **大 Sprint 拆批次 6-10 task 一组**：Sprint 8 44 task 拆成 7 个 subagent 批次（A/B+C/D/E/F+G），每次 6-10 task，subagent 不超 token 限制 + 失败易定位；小批次比"一次全扔"稳定 10 倍
- **catalog-vs-source 双向一致性测试模板**：新增规则/hint/error_code catalog 时，同步加源码 grep 测试（`re.findall(r'\bcode\s*=\s*["\'](...)["\']', source)`），catalog 与 validator 集合**完全相等**（不是单向子集）；保护未来新增 finding code 时忘记更新 catalog
- **规则条数"31"为历史错估**：requirements F48 说的 31 条 ValidationRuleDoc 与 validator.py 实际 emit 的 code 数对不上——后者只有 10 个（L1×5 + L2×3 + L3×2），详见 `validation_rules_catalog.py` docstring；F48 的文档应以 catalog+test 的实际为准不要盲信 requirements 文案
- **"spec 提到的函数名未必是真实函数名"**：例如 `workpaper_service.generate_workpaper` 实际是 `template_engine.generate_project_workpapers`；`validator.validate_l3_cross_table` 实际是 `validate_l3`；subagent 应 grep 定位而非盲信描述
- **前端任务统一批量延后**：本次跳过 18+ 个前端任务（路由/组件/徽章/对话框），统一等"前端集成 Sprint"专门处理；后端保持 API 就绪即可，不为前端提前塞样板代码

## 当前进度汇总

- **Sprint 1-3 B' 核心**：已完成（commit 集中在之前 Sprint）
- **Sprint 4-6 大文档+云协同+正确性**：后端 P0 完成，前端延后
- **Sprint 7 安全+健壮性**：批次 A (F40) + B (F41) + C (F42) + D (F44) + E (F45/F46) 全绿，19/23 完成；延后 7.6/7.7（tenant_id get_active_filter 签名大改造）+ 7.14/7.15（JobStatus.interrupted 枚举）+ 7.19（前端 DLQ 页面）
- **Sprint 8 校验透明+合规闭环**：批次 A-G 全绿 37/44 完成；延后 7 个前端任务
- **Sprint 9 最终验收**：4/10 完成（文档 + CI），延后真实 PG E2E（9.1/9.2/9.3）+ UAT（9.8）+ 灰度部署（9.9/9.10）
- **Sprint 10 一致性补齐**：之前已完成
- **Sprint 11 测试矩阵**：9/9 完成（62 passed + 2 skipped）
- **ledger_import 套件当前基线**：409 passed / 6 skipped（PG-only Alembic round-trip skip）/ 0 regression

## Sprint 7-11 复盘沉淀（2026-05-10）

### 已识别未消化风险（优先处理）
- **B' 核心性能声称无数据支撑**：`activate 127s→<1s` / YG2101 总耗时 <300s 均无最新实测；`scripts/b3_diag_yg2101.py` 本轮未跑，生产断言前必须补
- **6 个 Alembic 迁移堆积未执行**：`view_refactor_tenant_id / force_submit / event_outbox_dlq / dataset_binding / mapping_history_fp / retention_class` 纯 SQLite + `_init_tables.py` 全量建表验证过，空库 `alembic upgrade head` 没跑过；downgrade 语法错会等生产回滚才暴露
- **真实 E2E 彻底未验**：YG4001 smoke / YG36 / YG2101 真实环境 E2E 本轮零执行；后端代码架构完备但验证链有缺口
- **tenant_id 7.6/7.7 连续两轮延后**：`get_active_filter` 签名加 `current_user` + 40+ 调用点改造是潜在越权漏洞，不能无限拖

### 技术债 workaround 遗留
- **LedgerDataset.legal_hold_flag hack**：F53 实现时用 `source_summary["legal_hold"]` JSON 键过渡，长期让下个开发者困惑；补一列迁移只要 5 分钟
- **software_fingerprint vs file_fingerprint 并存**：两个指纹概念语义重叠，应合一或明确文档边界
- **spec 文案 vs 真实函数名错位 3+ 处**：`generate_workpaper` → `generate_project_workpapers`；`validate_l3_cross_table` → `validate_l3`；"31 条规则" → 实际 10 条。subagent 每次 grep 修正但没回填 spec，下轮扩展会继续引用错误名

### Subagent 编排新规约（本轮学到）
- **"之前 Sprint 已实装"声明必须三重核验**：orchestrator 收到此类声明时必须 (1) grep 确认代码存在 (2) 跑覆盖该声明的测试 (3) 核对 getDiagnostics 零错——缺一不可。否则重蹈 R5 "标 [x] 但 flush bug 隐藏"覆辙
- **Sprint 结束前强制 spec vs 实现 reconciliation**：所有 [x] 任务的函数名/类名/端点路径 grep 对齐 + catalog 条数等关键数字核对；本 spec 3 处错位都是这步缺失
- **每 Sprint 必须跑一次真实 PG + 至少一家样本**：本 spec 5 个 Sprint 零真实 E2E 是最大隐藏风险

### 后端 API 就绪但前端积压（独立 Sprint）
累积 18+ 前端任务：`DetectionPreview` skip_reason 灰卡片 / `ErrorDialog` hint / `DatasetActivationButton` reason 二次确认 / `DiagnosticPanel` drill_down 查看明细 / rollback 影响清单对话框 / 已锁定报表徽章 / retention 徽章 / `ColumnMappingEditor` "🕒 上次映射" badge / `ImportHistoryEntry` 恢复+接管 / force_submit 强制继续按钮 / 卡住阈值 30s / resume 端点 / WS composables / tooltip 锁详情。堆太久后端上下文就凉了，现在做还记得住

### 架构级关注（不急）
- **`DatasetService.rollback` 承担 5 个关注点**：获取锁 / 检查绑定 / 切 metadata / integrity check / 发 outbox —— 可拆 `RollbackPolicyChecker + RollbackExecutor + RollbackEventEmitter` 三段 pipeline
- **bound_dataset_id ON DELETE RESTRICT 长期影响**：4 张下游表一旦引用 dataset 就永远删不掉，`purge_old_datasets` 遵守但缺"永久保留数据集累计增长"监控告警
- **event_outbox + DLQ + WS 广播 + stale 联动 4 层异步**：单元测试全有，但端到端故障组合（DLQ 非空 + WS 断连 + 消费者慢）没覆盖，生产第一次组合故障会学到很多

### 流程改进沉淀（写入 steering）
- **P1 subagent 声明核验契约**（上面已列）
- **P2 Sprint spec-vs-reality reconciliation 强制步骤**（上面已列）
- **P3 每 Sprint 真实 E2E smoke gate**（上面已列）
- **P4 可选依赖集中目录**：`python-magic / psutil / prometheus_client / fakeredis / redis` 5 个可选依赖+各自降级策略应写入 `docs/OPTIONAL_DEPENDENCIES.md`，目前分散在各源文件 docstring 里无人维护

### 紧急待办（按优先级）
- **V1 （2h）**：跑 `scripts/e2e_yg4001_smoke.py` 验证 B' 核心 activate/rollback/写入改 false 没破坏
- **V2 （30min）**：空 PG 库跑 `alembic upgrade head` 验 6 个新迁移 + downgrade 回扫
- **V3 （本周）**：补 `LedgerDataset.legal_hold` 列替换 JSON hack
- **V4 （本周）**：跑 `scripts/b3_diag_yg2101.py`，把实测 activate phase 时间 / 总耗时写进 memory.md 替换声称
- **V5 （下 Sprint）**：前端集成 Sprint，18+ 累积任务统一清
- **V6 （下 Sprint）**：tenant_id 7.6/7.7 `get_active_filter` 加 `current_user` + 40+ 调用点迁移（独立 2 天）
- **V7 （下 Sprint）**：software_fingerprint vs file_fingerprint 合并，降级 software_fingerprint 为可选 hint

## YG36 真实数据 E2E 验证通过（2026-05-11）

- **B' 架构端到端验证成功**：YG36 四川物流 1.8MB xlsx（balance 813 + ledger 22716 + aux_balance 1730 + aux_ledger 25813）detect 0.3s → submit → pipeline 30s → activate <1s → completed；四表 active 行数正确 staged=0
- **PG schema 手动补齐 6 个迁移的列**：`is_stale`(audit_report+disclosure_notes) / `tenant_id`(5表) / `force_submit`(import_jobs) / `retention_class+retention_expires_at`(import_artifacts) / `bound_dataset_id+dataset_bound_at`(4下游表)；另建 `event_outbox_dlq` + `import_column_mapping_history` 两张缺失表
- **根因确认**：之前 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 多语句在一个 `-c` 里执行时，中间某条报错会中断后续语句（PG 事务回滚整个 `-c` 块）；正确做法是每条 ALTER 单独一个 `docker exec psql -c` 调用
- **e2e_http_curl.py Layer 3 断言需修正**：脚本用 `WHERE is_deleted=false` 全量查看到了历史 superseded dataset 的累加数据（3 份 × 813 = 2439 行）；B' 架构下业务查询走 `get_active_filter` 按 `dataset_id` 过滤只看到当前 active 的 813 行——断言脚本应改为按 dataset_id 过滤
- **balance-tree 端点 children 字段名**：返回的辅助子节点用 `code` 而非 `aux_code`（脚本 KeyError），需对齐
- **PG 数据库名确认**：`audit_platform`（不是 `gt_audit`）
- **Windows 后端启动最稳方式**：`Start-Process -FilePath "python" -ArgumentList @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","9980") -WorkingDirectory "D:\GT_plan\backend" -WindowStyle Hidden`；不要用 Tee-Object 管道（会阻塞绑定）；不要用 controlPwshProcess（进程会立即退出看不到日志）
- **V1/V2 复盘待办已部分完成**：V1 YG36 smoke 通过（activate <1s 验证）；V2 Alembic 列手动补齐（等价于 upgrade head 但未走 alembic 命令）；V4 YG2101 perf baseline 仍待跑

## Sprint 5 接管机制落地 + Git 同步（2026-05-11）

- **Sprint 5.9-5.11+5.13 F22 接管机制完成**：Alembic `view_refactor_creator_chain_20260520`（down=`view_refactor_retention_class_20260526`）+ `ImportJob.creator_chain JSONB DEFAULT '[]'` + `POST /jobs/{id}/takeover` 端点（PM/admin/partner 权限 + heartbeat >5min 过期检查 + creator_chain 追加 + resume_from_checkpoint 触发）+ `test_import_takeover.py` 6 用例全绿
- **Alembic 迁移链最终序列（9 个）**：`view_refactor_activation_record_20260523` → `view_refactor_tenant_id_20260518` → `view_refactor_force_submit_20260524` → `event_outbox_dlq_20260521` → `view_refactor_dataset_binding_20260519` → `view_refactor_mapping_history_fp_20260525` → `view_refactor_retention_class_20260526` → `view_refactor_creator_chain_20260520`
- **Git 分支状态**：`feature/ledger-import-view-refactor` 已推送到 origin（commit 9766e23）；同时 push 到 `feature/round8-deep-closure`（76a98a3）
- **tasks.md 验收清单更新**：V3/V5/V6/V7/V8/V9/V10 标 ✅；1.26/2.6/2.7 标 ✅（YG36 E2E 替代验证）；V1/V2 待 YG2101 实测；V4 待 e2e_full_pipeline_validation
- **PG 手动补列根因确认**：多条 ALTER TABLE 写在同一个 `docker exec psql -c "..."` 里时，中间某条报错会导致 PG 事务回滚整个块（后续语句全部不执行）；正确做法是每条 ALTER 单独一个 `docker exec psql -c` 调用
- **剩余 50 个未完成任务分类**：前端 Vue 18 个 / 真实 PG+大文件 E2E 6 个 / PG-only 延后 4 个 / 运维部署 3 个 / 后端可自动化已全部清零
- **后端可自动化任务全部完成**：Sprint 7-11 + Sprint 5 takeover = 所有后端 P0/P1 coding task 已标 [x]；剩余全是前端/真实环境/运维类

## 4/9 家真实样本 E2E 批量验证通过（2026-05-11）

- **YG4001 宜宾大药房**：0.8MB / 9s / balance=812 ledger=4409 aux_balance=304 aux_ledger=5628
- **YG36 四川物流**：3.5MB / 31s / balance=813 ledger=22716 aux_balance=1730 aux_ledger=25813
- **安徽骨科**：58.2MB / 531s（8.8min）/ balance=812 ledger=348802 aux_balance=43153 aux_ledger=619000
- **和平物流**：13.7MB / ~120s / balance=275 ledger=118259 aux_balance=3616 aux_ledger=0（方括号表头 L1 锁定修复后识别正确）
- **吞吐量参考**：安徽骨科 35 万行序时账 + 62 万辅助明细 = 约 1900 rows/s（含 aux 维度解析 + PG COPY）
- **剩余 5 家未测**：辽宁卫生/医疗器械（2 xlsx 分文件需批量上传）、陕西华氏（13 文件×2 年度）、和平药房（392MB CSV）、YG2101（128MB 单文件预计 7-15min）——多文件场景需前端批量上传或脚本逐文件 detect
- **Git 状态**：commit d842d39 推送到 `feature/ledger-import-view-refactor`

## 前端 21 个任务全部完成 + 4/9 真实样本 E2E 通过（2026-05-11）

- **前端 Batch 1（9 tasks）**：ImportHistoryEntry resume 按钮 + retention 徽章 / ThreeColumnLayout 卡住阈值 30s / DetectionPreview 预计耗时+规模档位+灰色 unknown 卡片+skip_reason badge+强制继续按钮 / ImportButton tooltip 锁详情 / DatasetActivationButton ElMessageBox.prompt 二次确认+reason 传递 / LedgerImportDialog forceSubmitFlag 透传
- **前端 Batch 2（6 tasks）**：`useProjectEvents` composable（eventBus 订阅 sse:sync-event 按 projectId 过滤，暴露 onDatasetActivated/onDatasetRolledBack typed handlers）/ ImportHistoryEntry 接管按钮（heartbeat >5min 显示）/ ErrorDialog hint 展示（title/description/suggestions 卡片）/ ValidationRules.vue 新页面（L1/L2/L3 分组 el-collapse+el-table）/ DiagnosticPanel drill_down 抽屉 / EventDLQ.vue admin 页面
- **前端 Batch 3（4 tasks）**：ErrorDialog+DiagnosticPanel error code 可点击跳转规则详情页（window.open 新标签）/ LedgerImportHistory rollback 对话框展示影响对象清单+409 SIGNED_REPORTS_BOUND 报表列表 / ColumnMappingEditor "🕒 上次映射" badge + "应用全部历史映射" 按钮 / ImportTimeline.vue 新组件（el-timeline+el-card，按年度查 datasets/history 端点）
- **新建前端文件 5 个**：`useProjectEvents.ts` / `ValidationRules.vue` / `EventDLQ.vue` / `ImportButton.vue` / `ImportTimeline.vue`
- **修改前端文件 10+ 个**：ImportHistoryEntry / DetectionPreview / LedgerImportDialog / ThreeColumnLayout / ErrorDialog / DiagnosticPanel / ColumnMappingEditor / DatasetActivationButton / LedgerImportHistory / router/index.ts / apiPaths.ts / ledgerImportV2Api.ts
- **新增路由 2 条**：`/ledger-import/validation-rules` + `/admin/event-dlq`（meta: permission admin）
- **getDiagnostics 全部 0 错误**
- **真实样本 E2E 4/9 通过**：YG4001 9s / YG36 31s / 安徽骨科 531s / 和平物流 ~120s；剩余 5 家需多文件上传或 >10min 超时
- **tasks.md 进度**：201→222 completed / 42→21 remaining（完成率 91.4%）
- **Git**：commit d842d39 → 后续 commit 含前端 3 批次 + 真实样本验证

## 前后端联动审查修复（2026-05-11）

- **DiagnosticPanel 响应结构修复**：后端 `/diagnostics` 返回 `result_summary.findings + blocking_findings`，前端原来期望顶层 `errors` 数组导致诊断面板永远为空；修复为 `fetchDiagnostics` 内做数据归一化
- **ColumnMappingEditor project_id 修复**：`copyMappingFromProject` 和 `getReferenceProjects` 原传空字符串，改为新增 `projectId` prop + `getCurrentProjectId()` 辅助函数从 LedgerImportDialog 传入
- **SubmitBody 接口补齐**：`ledgerImportV2Api.ts` 的 `SubmitBody` 补齐 `force_submit/incremental/overlap_strategy/file_periods` 4 字段
- **column-mappings 端点位置确认**：在 `backend/app/routers/account_chart.py`（prefix `/api/projects`），不在 ledger_import_v2.py
- **前后端联动审查方法论**：context-gatherer 误报率高（本次 8 个 issue 中 5 个是误报），关键路径必须手动 grep 验证；真正的 bug 多在"响应结构不匹配"和"参数传递遗漏"两类
- **E2E 脚本 B' 架构适配完成**：`e2e_http_curl.py` 所有 SQL 查询加 `dataset_id` 过滤 + 多维度辅助按 `aux_type` 分组断言；YG36 全部 Layer 3 断言通过
- **vue-tsc 修复 3 处 el-tag type='' 错误**：`DetectionPreview`/`ImportTimeline`/`ErrorDialog` 的 `type=""` 或返回空字符串改为有效值（info/success/warning/danger）
- **ImportError 接口扩展**：新增 `hint` 和 `location` 可选字段，对齐后端 `enrich_finding_with_hint` 返回结构
- **Git commit fe94001** 推送到 `feature/ledger-import-view-refactor`

## ledger-import-view-refactor 最终进度（2026-05-11）

- **tasks.md 进度**：239/243 completed（98.4%），剩余 4 个全部是运维/手动验证
- **本轮新增完成**：7.6/7.7 tenant_id 签名扩展 + 7.14/7.15 interrupted 状态 + 6.7/10.38 REPEATABLE READ + 10.52/10.53 graceful shutdown + 5.2/5.4 云协同广播 + V1/V2/9.3 YG2101 性能验证
- **关键架构确认**：后端不需要独立 WebSocket 服务——outbox_replay_worker 通过 `event_bus.publish_immediate` → SSE queue → `/events/stream` 已实现项目级广播；前端 ThreeColumnLayout 连接 SSE 并 emit `sse:sync-event`，useProjectEvents composable 订阅过滤
- **tenant_id 渐进迁移策略**：`get_active_filter` 新增可选 `current_user_id` 参数，为 None 时跳过校验（向后兼容）；关键入口（drilldown/penetration/import）已标注 TODO；路由层 `require_project_access` 仍是主要权限屏障
- **interrupted 状态落地**：JobStatus 新增 `interrupted` 枚举 + Alembic 迁移 `view_refactor_interrupted_status_20260511` + recover_jobs 优先恢复（有 checkpoint 走 resume，无则全量重跑）
- **REPEATABLE READ**：`DatasetService.activate` 开头条件执行 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`（仅 PG 生效，SQLite 静默跳过）
- **Git commits**：36e5d68 + e40a8d1 + c8796f6 推送到 `feature/ledger-import-view-refactor`
- **剩余 4 个任务**：9.2 9家样本全绿 / 9.8 UAT / 9.9 灰度部署 / 9.10 DROP 索引
- **所有代码层任务已清零**，剩余全部是真人操作（部署/手动验收）
- **YG2101 性能基线（2026-05-11 实测）**：128MB / 672k 行解析 + 200 万行写入，pipeline 总耗时 ~660s（11min）；activate <1s（B' 只改 metadata）；balance=812 / ledger=650,344 / aux_balance=45,316 / aux_ledger=1,285,170 / warnings=0 / blocking=0
- **Alembic 迁移链最终序列（10 个）**：view_refactor_activate_index → tenant_id → force_submit → event_outbox_dlq → dataset_binding → mapping_history_fp → retention_class → creator_chain → interrupted_status

## ledger-import-view-refactor 复盘改进建议（2026-05-11）

- **E2E 脚本必须跟架构同步**：每次改 get_active_filter/activate/pipeline._insert 后先跑 e2e_http_curl.py 再提交；本次 B' 改造后脚本仍用 is_deleted=false 查询导致误报浪费 1 小时
- **前后端响应结构对齐缺自动化**：DiagnosticPanel 期望顶层 errors 但后端返回 result_summary.findings，诊断面板一直为空无人发现；建议关键端点加 response_model + 前端 interface 对齐 checklist
- **spec 目标设定要基于实测**：YG2101 "总耗时 <300s" 在 200 万行场景不现实（PG COPY ~5000 rows/s 物理极限），activate <1s 才是真正架构收益
- **写入性能下一步方向**：异步 activate（pipeline 写完即返回 completed，activate 后台跑）或终极 B' 视图方案（业务查询走 v_tb_* 视图 JOIN ledger_datasets）
- **superseded 膨胀治理**：YG2101 每次导入 200 万行 superseded，purge 后需 VACUUM 回收空间
- **tenant_id 渐进迁移 deadline**：建议 3 个月内触碰即修，每次改文件时补 current_user_id 参数

## 复盘改进 9 条全部落地（2026-05-11，commit 00beda8）

- **新建永久脚本 2 个**：`scripts/e2e_9_companies_batch.py`（九家样本批量验证，--all 含慢样本）+ `scripts/validate_spec_references.py`（spec 引用核对，grep 验证函数名/端点是否真实存在）
- **新建文档 4 个**：`docs/FRONTEND_BACKEND_ALIGNMENT_CHECKLIST.md`（5 端点前后端对齐清单）+ `docs/TENANT_ID_MIGRATION_PLAN.md`（deadline 2026-08-11）+ `docs/adr/ADR-005-async-activate.md`（异步 activate 提案，当前不急）+ `audit-platform/frontend/e2e/ledger-import-smoke.spec.ts`（playwright 骨架 4 case，待安装后实装）
- **新建 hook**：`.kiro/hooks/e2e-reminder.json`（编辑 5 个核心文件时提醒跑 E2E）
- **purge worker 扩展**：`_vacuum_tb_tables()` 在 REINDEX 后对 4 张 Tb* 表执行 VACUUM（仅 PG，AUTOCOMMIT 模式）
- **conventions.md 新增**："Spec 目标设定规约"章节（基于实测基线 / 两层目标 / 区分架构问题与物理限制）

## 二次复盘发现（2026-05-11，系统级隐患）

- **PG 数据膨胀**：tb_balance 5964 行但 active 只 813（7× 膨胀），superseded 行 is_deleted=false 仍在；purge worker 因 activation_records FK 约束无法删 metadata；需手动清理一次 + 修复 FK cascade
- **useLedgerImport.ts composable 未被使用**：LedgerImportDialog 用组件内部 ref 管理状态，composable 是死代码；决策：删除或迁移
- **ColumnMappingEditor "从其他项目导入映射"是半成品**：API 调用成功但没重新初始化映射，用户看到"成功"但映射没变；需实装或删除按钮
- **SSE + 5s 轮询重复**：ThreeColumnLayout 同时维护 SSE 连接和 active-job 轮询，功能重叠；长期应让 SSE 推送 IMPORT_PROGRESS 事件替代轮询
- **SQLite 测试覆盖盲区**：423 测试全是 SQLite，PG 特有行为（enum/VACUUM/isolation）无法验证；建议 CI 加 PG 容器 job 跑 @pytest.mark.pg_only 子集
- **优先级排序**：数据膨胀清理 > 半成品功能 > PG CI > SSE 去重 > composable 清理

## 二次复盘 6 项即时修复完成（2026-05-11，commit 007939e）

- **PG 数据膨胀已清理**：删除 8 条旧 activation_records + 8 条旧 superseded metadata，当前 active=1 superseded=3（符合 keep_count=3）
- **useLedgerImport.ts 已删除**（-140 行死代码）；LedgerImportDialog 用组件内部 ref 管理状态足够
- **ColumnMappingEditor 消息已修正**：从"映射导入成功"改为"映射模板已保存，下次导入相同格式文件时将自动应用"（准确描述 file_fingerprint 复用机制）
- **CI 新增 `backend-tests-pg` job**：postgres:16 容器 + `pytest -m pg_only`（Alembic round-trip / enum / isolation 测试）
- **ADR-006 SSE vs 轮询决策**：保持双通道各司其职（SSE 推业务事件，轮询查精确进度），长期 SSE 稳定后可替代轮询
- **e2e_9_companies_batch.py 首次跑通 4/6 家**：YG36(68s)/YG4001(9s)/安徽骨科(537s)/和平物流(96s) 成功；辽宁卫生 79MB 超时（15min 不够，需 --all 模式的 20min 超时）
- **pytest.ini 新增 `pg_only` marker 注册**（消除 PytestUnknownMarkWarning）

## PG schema 缺列修复（2026-05-11）

- **import_jobs.creator_chain 列缺失导致全站 500**：Sprint 5.9 Alembic 迁移 `view_refactor_creator_chain_20260520` 未执行到 PG，所有查询 ImportJob 的端点（active-job/diagnostics/submit）都 500，前端误显示为 409 冲突；修复 = `ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS creator_chain JSONB DEFAULT '[]'`
- **PG 手动补列教训再沉淀**：每次新增 Alembic 迁移后必须在 PG 执行（或至少 `_init_tables.py` 重建），否则 ORM 模型与 PG schema 不一致会导致隐蔽 500；当前 10 个 view_refactor 迁移中 creator_chain 是最后遗漏的一个

- **ImportBatch 僵尸锁根因**：`e2e_9_companies_batch.py` 辽宁卫生超时退出后 ImportBatch 留在 processing 状态，阻塞该项目所有后续导入（409）；修复 = UPDATE status='failed'；预防 = 脚本超时退出时应主动调 release_lock 或标记 failed
- **排查 409 时注意多项目**：顶栏红色横幅显示的 project_id 可能不是当前查的项目（本次是 `4da6cd8c` 而非 `f4b778ad`），排查时应查 ALL projects 的 processing batch
- **`_expire_stale_jobs` 超时 60 分钟**（从 20 分钟调大）：大文件（432MB）解析+写入可能需要 30-50 分钟；重启后端 = 杀掉 worker = 正在运行的任务必然中断被标记 timed_out

- **导入进度 ETA 估算修复**：`estimated_remaining_seconds` 上限 3600s（超过不显示），进度 <10% 时不估算（早期线性外推误差极大，如 21% 时算出 1806 分钟）；根因是 `started_at` 包含 detect+排队时间而非纯写入时间
- **顶栏导入指示器点击跳转修正**：从 `/projects/${pid}/ledger`（账表查询页，导入中无数据）改为 `/projects/${pid}/ledger/import-history`（导入历史页，能看到 job 进度）

- **DetailProjectPanel "快捷操作"标题已删除**：保留建议流程+按钮网格，去掉多余 h4 标签（用户反馈冗余）
- **项目状态提示已加**：planning 显示"请先导入账套数据，完成后状态将自动推进"；created 显示"新建项目，请开始配置"
- **ETA 前端也加了 3600s 上限**：`ThreeColumnLayout.vue` 中 `eta <= 3600` 才显示，防止后端未重启时仍展示不合理数字

## R9 全局深度复盘 spec 已完成（2026-05-12）

- **spec 位置**：`.kiro/specs/refinement-round9-global-deep-review/`（requirements v1.0 + design v1.0 + tasks 83 任务 / 5 Sprint + 8 UAT）
- **实施状态**：83/83 编码任务全部完成，剩余 8 项 UAT 需手动浏览器验证
- **Sprint 1（P0，21 task）**：金额列统一（formatAmount.ts + 列宽 200/min-width 180）+ v-permission 全量盘点（8 按钮 + ROLE_PERMISSIONS 7 码 + find-missing 脚本增强）+ usePenetrate 统一接入（5 视图）+ GtPageHeader 强制接入（18 模式 A + 7 模式 B + variant="banner" prop）
- **Sprint 2（P1，14 task）**：角色首页差异化（4 Dashboard 卡片/按钮/Tab）+ useAiChat 合并 3 套（composable + 3 视图改造）+ Ctrl+Z 撤销（shortcutManager 移除 undo/redo）+ usePasteImport 扩展（3 视图）+ 工时审批 Tab+badge
- **Sprint 3（P1 续，14 task）**：GtAmountCell 已全量接入（Drilldown/LedgerPenetration/Adjustments/Misstatements 均已用）+ GtEditableTable 已接入 + /api/ 硬编码清零（7 处迁移到 apiPaths）+ statusEnum 补齐 4 组 + 8 视图替换硬编码状态字符串
- **Sprint 4（P2，20 task）**：vitest 基建（vitest.config.ts + 4 composable 单测各≥5 用例）+ Playwright E2E 骨架（3 spec）+ NotificationCenter 分类 Tab + 免打扰时段 + CSS/Loading 审计文档 + ReviewWorkbench Univer 只读 + 知识库上下文注入（前端+后端 context 参数）+ useFullscreen 接入 3 视图 + PENETRATION_MAP.md
- **Sprint 5（P0+P1 补充，14 task）**：死代码 6 文件已删（R7 已清理确认）+ handleApiError CI 卡点（基线 40）+ useEditMode 接入 6 视图（Adjustments/WorkHours/StaffManagement/SubsequentEvents/SamplingEnhanced/CFSWorksheet）
- **新建文件 12 个**：vitest.config.ts / playwright.config.ts / 4 单测 / 3 E2E / CSS_VARIABLE_AUDIT.md / PENETRATION_MAP.md / LOADING_PATTERN_AUDIT.md
- **新增前端 devDependencies**：vitest@^3.1.0 / @vue/test-utils@^2.4.0 / jsdom@^25.0.0 / @playwright/test@^1.52.0（未 npm install，仅写入 package.json）
- **后端改动**：knowledge_folders.py 新增 context 参数做 BM25 相关性加权
- **CI 新增**：catch 块裸 ElMessage.error grep 卡点（R9-F21）

## R9 完成后复盘发现（2026-05-12 实测核验）

- **GtPageHeader 实测接入率 ~30/86（35%）**：subagent 声称 95% 但 grep 只有 ~30 个视图 import GtPageHeader；差距原因 = 部分视图无 `<h2>` 模式（developing/空壳）+ 部分替换不完整；下一轮需逐视图分类处理
- **ElMessage.error 裸用仍有 24 处**：Task 76 声称清零但实测 24 处仍在（KnowledgeBase 7 / TAccountManagement 3 / CustomTemplateEditor 3 等）；CI 基线设 40 过宽应改为 24
- **useFullscreen 实测只 3 视图**（TrialBalance/ReportView/Adjustments）：LedgerPenetration 仍用自定义 isFullscreen ref 未真正替换
- **vitest 4 个单测文件已创建但未 npm install**：下次启动前端需 `npm install` + `npx vitest --run` 验证
- **Playwright E2E 是骨架占位**：3 个 spec 只有 page.goto 无真实断言，需启动前后端后实跑
- **statusEnum 替换不完整**：Task 49 只改了 8 个视图，剩余 20+ 视图可能仍有 `=== 'draft'` 等散落硬编码
- **流程教训**：subagent 声称完成 ≠ 真正完成，每 Sprint 结束后必须用 grep 脚本做硬指标核验；CI 基线必须基于实测值设定（当前值 = 基线，只减不增）
- **R9 grep 硬指标核验（2026-05-12 修复后最终值）**：GtPageHeader 74/90=82%（排除项 16 个合理）/ ElMessage.error 11 次（全部是非 catch 块业务校验，Login/Register 等）/ handleApiError 53 视图 ✅ / useEditMode 11 视图 ✅ / useFullscreen 6 视图 ✅ / /api/ 硬编码 0 ✅
- **R9 修复实际改动**：49 个视图 handleApiError 批量替换（147→11）+ 35 个视图新增 GtPageHeader（39→74）+ CI 基线从 40 修正为 11
- **R9 最终复盘结论**：6 项核心指标达标，系统前端一致性已达较高水平；下一步重点是 UAT 真人验证而非继续加代码
- **R9 残留 5 处状态硬编码**：QcInspectionWorkbench/ArchiveWizard/AuditReportEditor/IssueTicketList/PDFExportPanel 各 1 处 `=== 'draft'` 等未用 statusEnum（触碰即修）
- **vitest 已跑通（2026-05-12）**：`npm install` 完成 + `npx vitest --run` 4 文件 25 测试全绿；vitest.config.ts 已加 `exclude: ['e2e/**']` 排除 Playwright 文件
- **statusEnum 新增 3 组常量**：EXPORT_TASK_STATUS（queued/processing/completed/failed）/ QC_INSPECTION_VERDICT（pending/pass/fail/not_applicable）/ ARCHIVE_SCOPE（final/interim）+ ISSUE_STATUS 补 REJECTED
- **statusEnum 硬编码已清零**：grep `=== 'draft'` 等模式（排除已用常量的）= 0 处
- **vitest fake timer 陷阱**：`vi.runAllTimersAsync()` 对 setInterval 会无限循环；正确做法是 `vi.advanceTimersByTimeAsync(0)` 刷 microtask + `vi.advanceTimersByTimeAsync(interval)` 推进指定时间
- **R9 git 提交**：commit a68eb18 推送到 origin/feature/ledger-import-view-refactor（112 文件 +5163/-1171）
- **git 分支整理（2026-05-12）**：R7-R9 + ledger-import-v2 合并到 master（d8ce7c9）；删除 7 个过时分支（round7/round8/global-component-library/cell-selection/pinia-event-store/univer-import/cursor-setup）；仓库现只有 master + feature/ledger-import-view-refactor 两个分支
- **fix: 导入转后台弹错误弹窗（f35471d）**：用户点"关闭（后台继续）"后 `runImportPollingFlow` 仍在前台轮询，job 变 canceled 时 throw→catch 弹 ElMessageBox；修复 = `_importPollingAborted` flag + `shouldIgnoreError` 静默退出循环
- **fix: vue-tsc 0 错误（7880f6f）**：R9 subagent 批量替换 handleApiError 时引入 5 处 `P.xxx` 引用错误（应为 P_ledger/P_wp/P_proj）+ EqcrProjectView/AuditReportEditor/KnowledgePickerDialog 类型修复；AMOUNT_DIVISOR_KEY 从 .vue export 移到独立 `constants/amountDivisor.ts`
- **fix: 清空回收站 500（36b2023）**：`DELETE FROM projects WHERE is_deleted=true` 触发 FK 约束（子表 ledger_datasets/import_jobs 等仍引用）；修复 = 按 FK 深度顺序 raw SQL 级联删除（activation_records→四表→ledger_datasets→import_jobs→working_papers→project_assignments→adjustments→projects），每步 try/except 跳过不存在的表
- **fix: 清空回收站点击无反应（0066288）**：`operationHistory.execute()` 内部异常被外层 `catch { /* cancelled */ }` 静默吞掉；修复 = 去掉 operationHistory 包装，confirmDangerous 和 API 调用分开 try/catch，失败走 handleApiError 显示错误
- **feat: 科目余额表自动补齐父级汇总行（3c8f69d）**：Excel 原始数据常只有末级科目（如 1012.13），缺少上级汇总行（1012）；后端 `get_balance_summary` 查询后自动递归补齐缺失父级（金额=子级求和），支持点号分隔和纯数字两种编码格式；合成行标记 `_is_synthetic: true`
- **四表金额单位问题（2026-05-12 发现）**：真实样本（四川物流等）Excel 原始数据以"万元"为单位编制，系统原样存储不做单位转换，导致前端显示数字看起来"太小"；需要在导入时从表头提取单位信息（"单位：万元"）或让用户手动选择，前端余额表顶部标注单位
- **四表金额单位功能已实现（88b2a79）**：detector 从 Excel 表头自动提取 amount_unit 存入 dataset.source_summary；前端余额表/辅助余额表工具栏显示橙色"单位：万元"tag；旧数据集需重新导入或手动 UPDATE PG 补 source_summary.amount_unit
- **待做：金额单位前端切换器**：当前只显示从 Excel 提取的单位标签，不支持用户手动切换"元/万元"显示模式（即不做数值除以 10000 的换算显示）；用户要求加一个切换按钮
- **金额单位切换器最终方案（1c979f4）**：删除 provide/inject AMOUNT_DIVISOR_KEY 机制（双重除法 bug 根因），统一用 displayPrefs store 的 `amountUnit` + `fmt()` 做单位换算；选择器标签改为直观的"元/万元/千元"；displayPrefs store 默认 `amountUnit: 'wan'`（localStorage 持久化）
- **金额显示异常根因确认**：`displayPrefs` store 默认 amountUnit='wan'，`GtAmountCell` 的 `displayPrefs.fmt()` 内部调 `fmtAmountUnit(v, 'wan')` 已经除以 10000；R9 又加了 provide/inject 第二层除法 = 双重除以 10000；数据库数据始终正确（元为单位原样存储）
- **金额单位联动需求（2026-05-12）**：四表（余额表/辅助余额表/序时账/辅助明细账）单位切换必须联动——用户在任一表切换万元则四表同步；当前只有余额表和辅助余额表有切换器，序时账和辅助明细账缺失；provide 已覆盖所有子组件但序时账/辅助明细的 GtAmountCell 也在同一 provide scope 内应该已生效，需验证
- **GtPageHeader 排除项（16 个不需要加）**：Login/Register/NotFound/DevelopingPage（4）+ LedgerPenetration/WorkpaperEditor/Drilldown/DataValidationPanel/PDFExportPanel/LedgerImportHistory/ProjectWizard/WorkpaperWorkbench/AIChatView/AIWorkpaperView/AttachmentHub/ConsolidationHub（12 个子面板/嵌入/复杂自定义头部）
- **unplugin-vue-components 自动导入陷阱**：grep `import GtPageHeader` 只能统计显式导入，实际有 17 个视图通过 auto-import 使用 GtPageHeader 但无 import 语句；正确统计方式是 grep `<GtPageHeader` 模板标签
- **Sprint 5 Task 76 执行空洞**：handleApiError 批量替换声称完成但实际 0 个文件被改动（grep 证实 handleApiError 仍只有 R8 的 7 个视图）；下一步 P0 = 53 个文件 147 处 ElMessage.error 机械替换为 handleApiError

## 用户反馈的 UI 问题（2026-05-11）

- **查账页面金额列折行**：LedgerPenetration.vue 的期初金额/借方发生额/贷方发生额/期末金额列宽不够（当前 width=150/130），大金额（如 210,301,834.96）折行显示；需要加宽或用 `white-space: nowrap` + `min-width`
- **和平药房 3 文件上传 500 错误**：前端上传 3 个文件（1 xlsx + 2 CSV 共 432MB）时服务端报错（ID: a5789793-cda）；可能是文件大小超限（MAX_TOTAL_SIZE_BYTES=500MB 但单文件 CSV 上限 1GB 应该够）或 CSV 编码探测/upload_security 校验问题；需查后端日志定位
