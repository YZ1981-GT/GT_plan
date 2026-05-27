---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
保持本文件 ≤ 200 行：完成事项 → dev-history，技术决策 → architecture，规范/铁律 → conventions。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller，不要 .bat）
- **UI 全中文化铁律**（2026-05-26）：所有用户可见 UI 文本（label/title/placeholder/按钮/弹窗/状态/API 错误消息）必须中文；技术术语保留英文（SQL/PDF/OCR/LLM/AI/API/UUID/Qwen/CAS/编号 D2-1 等）；不接入 i18n（仅 2 视图用），直接硬编码中文 + ESLint 卡点防退化
- **输出控制**：分步输出/修改，大改动拆小批次；不一次出过多内容
- 功能收敛：停加新功能，核心 6-8 页做到极致，空壳标 developing
- 前后端必须联动；删除二次确认 + 先进回收站；一次性脚本用完即删
- git 提交不分多区，单 commit 提交所有变更
- 提建议前先验证（不引用过时记录），反复论证给最仔细可落地方案
- 判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录
- 文档同步：功能变更后同步更新需求文档；死代码立即删除，不留 DEPRECATED/fallback 注释
- 复杂重构先做 spec 三件套（体系化、精准、可回滚，"全部改完再跑一次测试"）
- 避免折中方案，要"根本解决"
- **彻底解决问题不调整错误呈现**：错误绝不"换个参数避开"，必须复现 + 定位根因 + 修主代码 + 加防御测试
- **文档标 ⚠️ 必须配套修复**：标注前评估能否本轮修复，可修则一次修完代码+文档+测试+memory；设计选择类用中性 📌 替代
- 完整复盘要诚实暴露问题不粉饰；PDCA 迭代模式：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- **改动前先 spec 三件律**：>500 行文件 / 涉及 3+ 组件 / 跨前后端 = 必须先写 spec 再动手
- **改动后必 Playwright 实测铁律**：`getDiagnostics` 通过 ≠ 运行时无错；声称"修复完成"前必须有 Playwright 证据，否则用"代码已改但未实测"措辞
- **触类旁通 grep 铁律**：发现一处反模式立即 grep 全仓找同类一次修完，修完强制问"项目里还有同类问题吗"
- 目标并发规模 6000 人
- 底稿编码：致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序

## UI 视觉偏好（详 #conventions）

- 表格列宽充足不折行，数字列 `.gt-amt`，所有 el-table 必须 `border + resizable`，固定宽度优先 `min-width`
- 表格选中行 ≥14% 透明度 + 左 3px 紫竖线 + hover 浅反馈
- 工具栏按钮合并到 Tab 栏右侧（不独占行）；简单 CRUD 不用 GtPageHeader 紫渐变
- 所有表格统一 el-table（底稿编辑器仍 Univer，不引入 AG Grid）
- 标准分页非"加载更多"；四表联查支持全屏+行选择+右键菜单
- 溯源/穿透跳转支持 Backspace 返回（DefaultLayout `initGlobalBackspace`）
- 表格编辑支持查看/编辑模式切换；复制按钮命名"复制整表" vs 右键"复制选中区域"
- 详细规则（GtToolbar slot 契约 / 全屏三件套 / Teleport 脱离 transform 祖先 / el-table flex 高度 / Tab 栏同行工具按钮 / Dashboard 视觉 / 借贷成对展示 等 17 条）→ 详见 `#conventions`「UI 视觉偏好补充」
- **底稿模块 Tab 顺序**（2026-05-24）：生命周期→委派矩阵→列表→工作台→看板→依赖图→手册（生命周期第一位=先裁剪程序）；树默认折叠
- **程序裁剪页面**（2026-05-24 重写）：`ProcedureTrimming.vue` 三大功能 = 一键智能裁剪 / 自定义裁剪 / 自定义新增程序；`chain_orchestrator` 步骤 5b 尊重裁剪 + 步骤 5c 加入自定义程序

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，PG 16（188 表），Redis 6379；后端 9980 / 前端 3030 / vLLM 8100
- 测试用户 admin/admin123（role=admin）；git 分支 fea2e-business-flow（HEAD）
- **本地 Docker 容器名**（2026-05-24）：`audit-redis`（端口 6380→6379）/ `audit-postgres` (5432) / `audit-metabase` (3000)；命令 `docker exec audit-redis redis-cli ping`
- **Playwright MCP 已装**（2026-05-27，workspace 级 `.kiro/settings/mcp.json`）：npx @playwright/mcp@latest，autoApprove 全部 browser_* 工具
- **5 真项目 PG 数据规模**（2026-05-27 实测）：首汽租车_2025（df5b8403）= tb_balance 1654 / tb_ledger 30324（最完整）/ 重庆和平药房_2025（2aa00f57）= 774 / 52060 / 其他 3 项目（首汽股份×2 + 重庆医药）= 0 / 0；**disclosure_notes / wp_index / ledger_datasets 全为 0**（未走过附注生成 / 底稿生成 / dataset 入库）
- **后端 health 端点是 `/api/health`**（不是 `/health`，404）
- **backend/ cwd 跑 python 必须 `..\.venv\Scripts\python.exe`**（仓库根 venv，不在 backend 子目录）
- **数据库初始化**：`python backend/scripts/init_tables.py` + `python backend/scripts/create_admin.py`
- **4 项目底稿数据已就位**（2026-05-25）：`python backen year=..., force=True)`
- **scripts 命名规约**：`_` 前缀 = 一次性脚本（用完即删），无前缀 = 正式工具
- **docs 目录结构**（2026-05-23 重组）：8 子目录（adr / architecture / deployment / reference / frontend / operations / proposals / templates）+ 顶层 README.md 索引；新增文档按子目录归类
- **双 storage 目录职责**：仓库根 `storage/projects/{UUID}/workpapers/` = 底稿文件；`backend/storage/{knowledge,projects,users,ledger_uploads}/` = 附件/上传；两边 gitignored 但代码 hardcode
ts 353 / composables 91
- **数据规模**：模板 456 / cross_wp_ref 400 / prefill 1035 cells / VR 114 / Spec 70+
- **代码规模实测**（2026-05-26）：views 99 / components 381 / composables 132 / stores 9 / routers 281 / models 62 / services 369
- **代码健康度实测**（2026-05-26）：`except Exception` 1162 处 / `float()` services 420 处 / `console.log` 74 处 / `datetime.utcnow()` 19 处 / statusEnum 硬编码残留 17 视图 / `year:changed` 仅 3 视图订阅 / autoSave 间隔 120s / el-skeleton 10 视图 / 虚拟滚动 0 处 / 表单无 rules 39 视图 / 删除无确认 23 处 / 路由参数变化仅 1 视图 watch / GtEmpty 仅 3 处 / GtStatusTag 仅 6 处 / 分页仅 7 视图 / 响应式仅 7 处（固定宽度 57 视图）
- **高阶治理盲区**（2026-05-26）：归档项目 0 视图检查 isArchived（CAS 1131 合规风险）/ PBC router 仍 stub / 0 客户端 portal / 跨年继承散落 53 服务无统一 / 硬编码 URL 25 处 / 0 UserPreference 表 / 通知仅邮件 1 处（0 微信/钉钉）/ 软删除 33 服务硬删除仅 2 处（已成熟）/ Bundle visualizer 未配置
- **新增依赖**：locust / marked + dompurify / Storybook 8.6.14 / xlsx-js-style / decimal.js / python-docx / prometheus_client / **PyYAML**（workpaper-html-renderer 引入）/ **fast-check v4.8.0**（前端 PBT）；外部 LibreOffice（4 路径 fallback）
- **文档/表格生成职责边界**（2026-05-23）：Univer Sheets = 底稿在线编辑 / Univer Docs+TipTap+textarea 三级降级 /楷体_GB2312/宋体/Arial Narrow）必装
- **Dashboard 视觉规约**（2026-05-23）：5 dashboard 统一 `GtPageHeader variant="banner"` + dark 主题；DashboardViewSwitcher 共享组件挂 banner #actions slot
- **查询入口统一**（2026-05-23）：用户可见名称 = 「高级查询」；CustomQueryDialog 内 el-tabs 分两层「业务视图」+「高级构建器」（仅 admin/manager/partner）
- **高级查询白名单覆盖 9 维度**（2026-05-23）：TABLE_WHITELIST 16 张表全维度入栏；users 显式排除 hashed_password；JOIN_WHITELIST 以 projects 为中心辐射

## 任务状态

### 全部已完成 spec ✅

11 审计循环（D~N，548/548）/ phase 1~7（239/239）/ phase 8（116 tests）/ proposal-remaining-18（30/30）/ k-admin-cycle-post-review-fix / partner-dashboard / procedure-trimming / role-view-switching / 角色体系治理（145 vitest）/ e2e-business-flow（58/58）/ template-library-coordination（64/64）/ audit-chain-generation（101/101）/ enterprise-linkage（56/56）/ **ledger-import-view-refactor（243/243）** / **advanced-query-enhancements-p1p2（212 tests）** / **workpaper-html-renderer（40/40 tasks，413 tests，2026-05-26 commits fd95ae1+46fa4b5+8fd847d）** / **disclosure-note-full-revamp（44/47 tasks 核心完成，pytest 430/430 全绿，2026-05-27 commits 6b6731c+65fc11a+3c5067c+e1477b2+1729c38f+58cff337+736cf1d4+551835b6；剩 F-1 真项目 UAT/F-2 dev-history/F-3 文档收口）** —— 详见 INDEX.md。

### workpaper-html-renderer 关键沉淀（详见 #dev-history）

- 1788 单体真底稿（A/B/C/D/E 共 1346 sheet）从 Univer 切到 HTML，F/G 558 sheet 保留 Univer
- 9 类 componentType 路由 + 禁止 Univer 兜底铁律 + 11 命名空间 4 层级跳转
- 方案 C openpyxl 加载致同模板 + 4 路径写入策略 1:1 还原
- 9 PBT 属性测试覆盖（hypothesis + fast-check 双框架）
- 性能基准全部 ×18+ 余量（HTML 冷启动 27.7ms / xlsx 导出 275.7ms / classification 1.2μs）
- 详细技术决策、新依赖（PyYAML）、测试模式（fake-timers / 子组件 stub / FakeDB）已下沉到 #dev-history

### V3 Spec 进展（global-refinement-v3，2026-05-27 进行中）

- **Sprint 0 横切基础设施 ✅**（5/5）：useAuditContext composable + V017 迁移 3 表（ai_content_log/cross_module_conflicts/time_machine_snapshots）+ ORM models + 7 ESLint 规则骨架（gt-audit plugin）+ audit_log_helper（6 event_type schemas）
- **Sprint 1 Req 1 归档只读 ✅**（7/7）：`_check_project_not_archived` hook 注入 require_project_access + 例外通道 + unarchive 二次确认 + ArchivedBanner.vue + canEdit 按钮 disabled + 7 视图接入 + Property 1 hypothesis
- **Sprint 1 Req 2 金额 Decimal 化 ✅**（9/9）：`_decimal_helpers.py`（to_decimal/quantize/amount_tolerance）+ Pydantic `AmountDecimal` Annotated type + 5 schema 切换 + note_validation_engine/note_formula_engine 容差替换 + `scripts/_check_no_float_amount.py`（baseline 15）+ 前端 `utils/decimal.ts` + GtAmountCell Decimal 切换 + Property 2 hypothesis + 全量回归（132 errors/1 fail 全部预存 SQLite vs PG schema 问题，无 Decimal 回归）
- **Sprint 1 Req 3 表单校验全覆盖 ✅**（6/6）：formRules.ts 扩展（projectName 新增）+ `useFormSubmit` composable（防重复点击 + short-circuit）+ 5 核心表单接入（Adjustments/Misstatements/ProjectWizard/UserManagement/WorkpaperEditor）+ ESLint `el-form-must-have-rules` 规则实现（AST 通过 defineTemplateBodyVisitor）+ 44 文件批量加 :rules（baseline 50→0，100% 清零）+ Property 3 fast-check 测试（含 baselines.json 守门断言）
- **Sprint 1 Req 4 删除二次确认 ✅**（4/4）：`confirm.ts` 扩展 confirmDelete/confirmDangerous（options 对象 + impact + recoverable + requireInputMatch 输入校验）+ 5 处补 confirm（ItemAttachment/ReportLineMappingDialog/SEChecklistPanel/FormulaManagerDialog × 2）+ ESLint `no-delete-without-confirm` AST 规则（function-scoped 窗口 + services/*.ts 整目录豁免，baseline 0）+ `scripts/_check_no_delete_without_confirm.py` 静态扫描卡点（Property 4）
- **Sprint 1 Req 5 年度切换响应（部分）**：5.1 ✅ 7 视图接入 useAuditContext.onContextChange（Adjustments/Misstatements/ReportView/DisclosureEditor/WorkpaperList/TrialBalance/LedgerPenetration）；3 视图通过 `reloadXxxContext()` 函数提取 + 顶层直调替代 `watch(..., {immediate:true})` 双角色避免重复触发；4 视图保留 onMounted 直接追加 onContextChange
- **关键技术决策**：
  - 单一迁移 V017 同时建 3 表（ADR-08）+ R017 一次性回滚
  - `_resolve_tolerance(rule.tolerance, *refs) = max(下限, amount_tolerance(max_abs))` 兼容小金额（<1万 仍 0.01）+ 大金额放宽，避免破坏既有测试
  - 前端 `utils/decimal.ts` 镜像后端 `_decimal_helpers.py`（precision=28 + ROUND_HALF_UP）
  - GtAmountCell 实际路径在 `components/common/`（非 `components/gt/`，spec 文档笔误）；ArchivedBanner 同
  - `note_formula_generator.py` 0 处 `> 0.01`，实际目标是 `note_formula_engine.py`（spec 文档笔误已修正）
  - AmountDecimal = `Annotated[Decimal, BeforeValidator(to_decimal)]` 拒绝 NaN/Infinity（Pydantic v2 范式）
  - **wp_classification_service fallback 策略**（2026-05-27）：`workpaper_sheet_classification` 表为空时（项目未跑分类入库），`_fallback_by_wp_code_prefix` 根据 wp_code 首字母（D2→D→`d-form-table`）静态推断 componentType，避免所有底稿 fallback 到 Univer；F/G 前缀仍返回 `univer`
  - **render-config 500 修复**（2026-05-27）：`projects.template_version_id` 列由 V018 迁移添加但本地 PG 未执行 V018；已通过 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 补齐 + `wp_render_config.py` Step 3 加 try/except 降级（不 rollback 避免 session 失效）
  - useFormSubmit 三大契约：validate 失败 short-circuit / submitting 防重复点击 / action 抛异常时 submitting 重置
  - el-form rule.required:true 仅在 value=='' || null || undefined 时报错，**单空格 ` ` 视为有效**（element-plus 默认行为，PBT 测试需对齐）
  - 测试路径修复铁律：跨工作区/子目录的 pytest fixture 文件路径要么用 `Path(__file__).resolve().parent` 推断，要么 baseline.json 兜底多候选路径（避免 cwd 切换导致 `open("backend/migrations/...")` 失败）
  - **ESLint AST 规则窗口策略**：纯行号窗口（前 3 行）会漏报 `try { confirmDelete } catch { return } try { api.delete }` 模式（间隔 5+ 行）；正确做法是 AST 沿 `node.parent` 链向上查 enclosing function（FunctionDeclaration/Expression/ArrowFunctionExpression/MethodDefinition）作为窗口起点，找不到时回退 8 行兜底；同函数内任意位置 confirm 即视为已确认
  - **ESLint 文件级豁免用 RegExp 数组而非 Set**：`/\/src\/services\/[^/]+\.ts$/` 一条正则覆盖整个 services 目录，比 EXEMPT_FILES Set 列举具体文件名更稳健（避免新增 service 文件需同步更新规则）
  - **watch immediate:true 双角色重构**：旧代码用 `watch([...], { immediate: true }, body)` 同时承担首次加载 + 后续监听，迁移到 useAuditContext.onContextChange 时必须先把 watch 体提取为独立函数（如 `reloadXxxContext()`）顶层直调一次替代 immediate，再通过 onContextChange 订阅，否则 watch 旧路径与 onContextChange 新路径会双触发

### 真正待办（外部依赖）

- LLM 真实接入：phase3 UAT-3 + K-1 / 6 stub 引擎（H/I/G/K/J/N，`settings.WP_AI_SERVICE_ENABLED` 一键切换）
- 6000 并发压测：phase3 UAT-5（需真 PG 大数据量 + Locust）
- W-3 钉集成（外部对接）
- Sentinel failover 真实验证：phase4 UAT-8
- WorkpaperEditor 瘦身（当前 2631 行，目标 ≤1000）：useEditorActions let→ref + template dialog 配置驱动 + 删冗余别名
- **scripts 命名实例**（2026-05-27）：本 spec 系列工具脚本统一无 `_` 前缀（`cleanup_note_templates.py` / `migrate_disclosure_notes_to_v2.py` / `generate_note_template_bindings.py` / 对应 report.txt），因均幂等可重复跑（不是用完即删的一次性）；CI 卡点单测放 `backend/tests/services/test_note_*` 命名空间
- **附注 spec 关键技术沉淀**（disclosure-note-full-revamp，2026-05-27 完成 44/47）：DSL 入口 `note_formula_generator.generate_formulas_for_table`，5 函数 = `TB(account, period)` / `WP(wp_code, sheet, cell)` / `REPORT(row_code, period)` / `cell(row, col)` / `SUM(start:end, col)`；本 spec 新建 `=PRIOR / =AGING`；`DisclosureNote.is_stale` 字段已存在（F46/Sprint 7.22）+ `event_handlers._mark_downstream_stale_on_rollback` 已订阅 `LEDGER_DATASET_ROLLED_BACK`；新建 `useNoteStale.ts`（不是改 `useLinkageEvents`，后者不存在）；`NoteTrimService` 原 5 方法 + 新增 `auto_trim`；scripts 命名 = 幂等工具 `cleanup_note_templates.py` / `migrate_disclosure_notes_to_v2.py` / `generate_note_template_bindings.py`；公式存储 = `table_data._formulas` 顶层 dict（`row_idx:col_idx` → {type, expression, description, category, source}）；致同 Word 排版规范（21 项 + 11 项视觉断言）+ NoteFormatConfig 21 字段 frozen dataclass / GTNote* 命名空间样式 / fill_multi_header 多层表头
- **vLLM / httpx 链路 3 个待修复 bug**（spec 已沉淀到本 memory，待动手）：
  - **httpx 系统代理陷阱**：Windows Clash 类系统代理（127.0.0.1:7897）让 `httpx.AsyncClient()` 默认读取代理把 localhost 请求路由到代理返回 502；修复 = 创建 client 时显式 `mounts={}, trust_env=False`；需修 4 文件：`llm_client.py`（_sync/_stream_completion）/ `ai_service.py`（_get_ollama_client + _get_llm_client + _get_chromadb_client）/ `availability_fallback_service.py`（check_llm_available）/ `routers/system_settings.py`（check_url）
  - **vLLM `chat_template_kwargs` 必须 payload 顶层**：嵌套 `extra_body.chat_template_kwargs` 被 vLLM 静默忽略，`enable_thinking=False` 不生效导致 content=None reasoning 有值；`llm_client.py:107` 改顶层 `"chat_template_kwargs": {"enable_thinking": settings.LLM_ENABLE_THINKING}`
  - **LLM thinking content=None 处理**：finish_reason=length 时返回"思考超 token，请简化提问或增大 max_tokens"，**禁止**回退到 reasoning 字段；`llm_client.py:_sync_completion` 需补此分支
- **本地 PG schema 漂移已修复**（2026-05-27 完成，commit db403d7b）：alembic 当前 `a2f355648e85`，下游多个 head 因 `phase17_001` `CREATE TYPE IF NOT EXISTS` 不被 PG 支持而中断（已用 DO 块 + DuplicateObject EXCEPTION 修复）；**根因**：`MigrationRunner`（D6 版本化 SQL 脚本）= 启动时实际跑的迁移系统，`alembic` 仅历史遗留运行时不跑，导致 alembic chain 中后续 spec 改动需手工补；**修复方案** = 新增 `V017__fix_schema_drift.sql`（`job_status`→`job_status_enum` 重命名 + `interrupted` 值 + `import_jobs.{version,force_submit,creator_chain}`） + `V018__fix_schema_drift_full.sql`（自动从 ORM 反推生成 65 缺列 + 10 缺表 + idempotent CREATE/ALTER；workpaper_template_version 必须早于 workpaper_sheet_classification）；**0 漂移确认**（`_full_schema_diff.py` 反查工具）；alembic chain 整链尚未 upgrade 完（多个 stamp 跳过 + cell_annotations 等已存在），但运行时 D6 SQL 路径已通；**alembic chain 修复** = 另立 spec 工作（不在附注 spec 范围）
- **首汽租车_2025 / 重庆和平药房_2025 默认 is_deleted=True**（2026-05-27 实测）：5 项目中 4 个软删除，只有「重庆医药集团四川物流_2025」可见但 tb_balance/tb_ledger 都 0；UAT 前必须 `UPDATE projects SET is_deleted=false WHERE id=...` 恢复
- **LibreOffice 已装**（`C:\Program Files\LibreOffice\program\soffice.exe`）：后端启动健康检查 15s 超时是 LO 启动慢导致，**不影响附注 docx 导出**（python-docx 不依赖 LO）
- **D6 迁移系统铁律**（2026-05-27）：启动时跑 `backend/migrations/V*.sql`（MigrationRunner），不是 alembic；新加列/表写 `V0XX__*.sql` + `R0XX__*.sql` 配对；alembic 是历史遗留，schema 漂移走 D6 SQL 修而不去拉通 alembic chain；CREATE TABLE/ALTER COLUMN 必须 `IF NOT EXISTS` idempotent
- **disclosure-notes format-config 端点 405**（2026-05-27 待修，spec 自带 bug）：`GET /api/disclosure-notes/format-config` 被同 prefix 下其他 router（note_wp_mapping/note_trim/note_ai）的 path 拦截，FastAPI router 注册顺序问题；解决方案 = 把 `dn_router` 提到所有同 prefix router 之前 include
- **本地 git 状态**（2026-05-27）：master 领先 origin/master 178 commit + 落后 4 commit，**从未 push 过**；远端只有 origin/master + origin/feature/{e2e-business-flow,ledger-import-view-refactor}；按 git_safety 铁律应推到新分支 `feature/disclosure-note-full-revamp` 不直推 master

## 关键引用指南

- 详细技术事实 / 端点速查 / PG schema / spec 历史详细 → `#dev-history` grep 关键词
- 项目架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 视觉补充 / 操作铁律 / Spec 工作流 / PG 运维 / 批量入库 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`

## 操作铁律（标题级，详见 #conventions）

- **彻底解决不绕开**：错误必须复现+根因+修主代码+防御测试
- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **可复用脚本沉淀**：批量入库/UAT/迁移工具放 `backend/scripts/{name}.py` 配 docstring + 多场景
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ superuser bypass RLS / CONCURRENTLY 必须 asyncpg raw conn + lock_timeout
- **router_registry 必查铁律**：新建 router 文件后必须在 `backend/app/router_registry/{group}.py` 注册，否则 endpoint 写好但前端 404
- **WpFileStatus 完成语义**：「底稿已完成」= `status in (review_passed, archived)`，不要猜不存在的枚举
- **临时文件不进 commit**：commit-msg.txt 必须 `git rm --cached` 清掉；优选 `git commit --% -m "..."` stop-parsing token
- **agent 调 service 优于 Playwright UI**：大文件入库直调 ledger_import 管线快 10x
- **历史档案不回填修改**：dev-history.md / spec/tasks.md 等是 append-only 审计轨迹，目录重组时不回填旧路径
- **vue-tsc 类型债务清理 SOP**：mitt Events 类型表必须显式补 key；SyncEventPayload 用 escape hatch；FUniver/xlsx SDK 用 `(api as any)` cast
- **Vue setup const 声明顺序铁律**（2026-05-25）：`const X = useY(..., Z)` 引用的 Z 必须在 X 之前已定义；典型实例 = WorkpaperEditor commit 79f7936 把 6 个 cycle composable 实例化放在 cycleDialogs 之前触发 ReferenceError；判定 = const 链式依赖必须按拓扑顺序写
- **顶层 v-if 守卫拦 init 死锁铁律**：依赖 template ref 触发 init 的组件不能加顶层 `v-if="loading"` 守卫，改 overlay 模式（容器永远渲染 + 内部蒙层）
- **useWpDetailGuard 三态默认接入铁律**（2026-05-25）：依赖 wpId 的视图必须 `useWpDetailGuard(wpId)` 三态（loading/error/ready），不允许直接 `goBack()` 跳转处理异常
- **append-to-body :deep() 失效铁律**：el-dialog/el-drawer/Teleport 内容到 body 下脱离组件作用域，`<style scoped>` 的 `:deep()` 选不到，需独立全局 `<style>` 块
- **前端硬编码假数据铁律**：UI 中的"演示数据"在产品成熟阶段全部移除改 API 驱动；任何 wp_code 维度可视化必须根据 `props.wpCode` 动态获取
- **apiProxy 单层解构铁律**：`api.get/post` 已直接返回业务数据，调用方禁止再 `const { data } = await api.X(...)` 二次解构
- **真实 PG 诊断铁律**：用户截图问题三步走 = ①连真 PG SELECT 看数据 ②对照 service 代码追路径 ③定位真因再动手
- **后台 worker 心跳完整性铁律**：`event_cascade_health_service._WORKER_NAMES` 4 worker 缺一即 degraded；DegradedBanner 异常先 `docker exec audit-redis redis-cli keys "worker_heartbeat:*"` 看真实心跳
- **year 必传参数三级 fallback 铁律**：项目维度业务接口前端取 year = `projectStore.year || Number(route.query.year) || new Date().getFullYear() - 1`，apiProxy 第三参 `{ params: { year } }`
- **PowerShell**：写中文/emoji 用 fsWrite；多 -m 长 commit 含 ()/→/中文冒号必须 `git commit --% -m "..."` stop-parsing token；`commit-msg.txt` 临时文件方案不进 commit 是底线
- **SQLite 测试 set_rls_context 兼容**：mock `app.deps.set_rls_context` 绕开（admin 路径仍会触发）
- **FastAPI dep_overrides 闭包陷阱**：`require_project_access("readonly")` 工厂每次返新闭包，dep_overrides 不命中；正确做法 = 仅 override `get_current_user` + `get_db`
- **hypothesis PBT 调速铁律**（2026-05-27）：大列表 PBT（min_size 100-2000 + max_examples 50-100）单测 7-8s 偏慢；调到 max_examples=15-30 + 列表 size 50-300 可降至 1-2s（~6x 加速）且不丢覆盖；快速 unit 类 PBT（quantize/tolerance）max_examples=30 足够
- **ESLint vue 模板 AST 铁律**（2026-05-27）：自定义 ESLint 规则若直接 `return { VElement(node) {...} }` 在 vue-eslint-parser 解析的 .vue 文件中**不会触发**（默认 visitor 不走模板 AST）；必须用 `context.parserServices.defineTemplateBodyVisitor({...})` 包装；既有 `no-dialog-without-append.cjs` 同 bug 待修
- **fast-check PBT 反例对齐铁律**（2026-05-27）：当反例失败时优先调整测试期望对齐**实际系统行为**而非"理想行为"（如 element-plus required 不拒绝单空格）；mock validate 函数要补全 type=email/number 等校验分支匹配生产 async-validator 行为
- **ESLint Program-level visitor 铁律**（2026-05-27）：脚本 AST 规则用 `Program(node)` + 自定义 walker 跳过 `parent/loc/range` 防环；不需要 `defineTemplateBodyVisitor`（仅 vue 模板才需）；典型实例 = `must-watch-route-or-context.cjs` 同时检测 onMounted body 内 fetch+year + 文件级 watch/onContextChange 守卫
- **broadcast_raw fan-out 铁律**（2026-05-27）：`event_bus.broadcast_raw(type, extra)` 需双路推送 = ①Redis Stream xadd 持久化 + ②内存 sse_queues fan-out（dict 形式带 `_raw=True` 标记）；events.py event_generator 用 `isinstance(payload, dict) and payload.get('_raw')` 区分 raw vs EventPayload；不触发 _handlers 避免双发
- **业务异常 = ValueError 子类铁律**（2026-05-27）：service 层业务异常（如 `AiContentLogNotFoundError` / `ConflictAlreadyResolvedError` / `ConflictMergeValueRequiredError`）继承 `ValueError`，router 层捕获 ValueError 即统一映射 422，避免每类异常单独写 except 分支
- **AI 内容生成强制溯源铁律**（2026-05-27）：6.2 起新增 `wrap_ai_output_with_log(...)` 异步版（保留同步 `wrap_ai_output` 向后兼容）；`db + project_id + user_id + instance_type + instance_id` 五参齐全自动调 `ai_content_log_service.create()` 写表 + 返回 `ai_content_log_id` + `confirm_action='pending'`；任一缺失静默跳过；`AIContentMustBeConfirmedRule` 双路径检查（ai_content_log 表优先 + parsed_data fallback），`location.via='ai_content_log'/'parsed_data'` 标识来源
- **subagent 中文截断修复铁律**（2026-05-27）：subagent 写入含中文注释的 .ts/.vue 文件时可能因 context window 截断产生 `U+FFFD`（�?）乱码；修复方法 = `git checkout origin/{branch} -- {file}` 从远程恢复干净版本；发现后用 `Get-ChildItem -Recurse | Select-String "\uFFFD"` 全仓扫描确保无残留
- **wp_classification 治本铁律**（2026-05-27）：底稿 sheet 类型选择跟项目数据**无关**，只跟模板结构有关；`workpaper_sheet_classification` 表必须由 `seed_workpaper_sheet_classification.py` 从 `workpaper_template_analysis.json`（349 模板/2602 sheet 扫描结果）全量灌入；运行后 D2-3 等 wp_code 正确路由到 b-index/a-program-console/d-form-table/c-note-table/univer 等 9 类；废弃 `_fallback_by_wp_code_prefix` 兜底（合成假 sheet_name="(fallback)" 跟真实 parsed_data.html_data keys 不匹配，是错误方向）
- **wp_code → 模板文件解析铁律**（2026-05-27）：模板文件名"D2-1至D2-4 应收账款.xlsx"覆盖 wp_codes [D2-1,D2-2,D2-3,D2-4]，每个 wp_code 都灌入完整 11 sheet 分类；范围正则 `^([A-Z])(\d+)(?:-(\d+))?至(?:[A-Z])?(\d+)(?:-(\d+))?` + 单 wp_code `^([A-Z]\d+(?:-\d+)*[A-Z]?)`；服务层 `_build_wp_code_candidates` 三级回退（精确 → umbrella+`-1` → strip trailing `-N`）保证 D2/D4/F2 等 umbrella code 也能命中
- **V019 迁移种子数据铁律**（2026-05-27）：表建好后必须配套 V019/V020 等种子数据迁移（INSERT 初始版本/枚举/配置），ON CONFLICT DO NOTHING 保证幂等；与 D6 SQL 配对 R0XX 回滚脚本同步上传 git 避免其他用户拉取后表为空
- **target_cell 前缀化编码铁律**（2026-05-27）：`ai_content_log.target_cell` 保存为 `{instance_type}:{instance_id}[:{field}]` 三段式，便于 `list_by_project(instance_type='workpaper')` 通过 `LIKE 'workpaper:%'` 过滤；service 层 create() 自动前缀化，调用方传原始 field 即可
- **section registry 注册即用铁律**（2026-05-27）：archive_section_registry 模块加载即 `register('05', filename, generator_func, description)`，无需手动调用；generator 通过 lazy import 委托避免循环依赖；§01-04 既占位（EQCR/QC/独立性等），新加章节按 prefix 自然排序

### Sprint 1 Req 5/6/7 进展（2026-05-27 完成）

- **Sprint 1 全部 30 任务 ✅**（2026-05-27 完成）
- **Sprint 1 Req 5 ✅**（3/3）：5.1 7 视图接入 onContextChange + 5.2 ESLint `must-watch-route-or-context` AST 规则（baseline 3：AuditReportEditor/Drilldown/Materiality）+ 5.3 Property 5 fast-check（5 properties × ~20 runs）+ 7 视图静态守门 + Playwright e2e 骨架（默认 skip）
- **Sprint 1 Req 6 AI 内容溯源 ✅**（7/7）：6.1 ai_content_log_service（7 API + 17 tests）+ 6.2 wrap_ai_output_with_log（12 tests）+ 6.3 AIContentMustBeConfirmedRule 双路径（13 tests）+ 6.4 AiContentTag/Banner（5 视图顶部接入 + 14 vitest）+ 6.5 router 4 端点 + AiContentBadge 组件（8+11 tests）+ 6.6 §05 AI 贡献明细归档章节 + 6.7 Property 6 hypothesis（3 PBT 不变量）
- **Sprint 1 Req 7 跨模块冲突调解 ✅**（7/7）：7.1 conflict_resolution_service（6 API + 19 tests）+ 7.2 manual_override hook 三态注入（10 tests）+ 7.3 SSE broadcast_raw fan-out（13 tests）+ 7.4 ConflictResolutionPanel.vue（el-drawer + 三选一 + 10 vitest）+ 7.5 ConflictBanner 5 视图接入（8 vitest）+ 7.6 QC 规则 V3-CROSS-MODULE-CONFLICT-UNRESOLVED（4 tests）+ 7.7 Property 7 hypothesis（4 PBT + 1 sanity）
- **新增 ESLint 规则 baseline 实测**：no-amount-without-decimal=15 / el-form-must-have-rules=0 / no-delete-without-confirm=0 / must-watch-route-or-context=3 / no-bare-amount-cell=92 / no-status-string-literal=202 / 其余 2 个 TBD（no-english-ui-label / console-log）

### Sprint 2 Req 8 进展（2026-05-27 完成）

- **8.1 GtAmountCell 全量覆盖 ✅**（4/4）：扫描脚本 baseline=109 → Top 3 视图接入后降至 92 + ESLint AST 规则 `no-bare-amount-cell` + Property 8 displayPrefs 一致性 4 不变量
- **8.2 加载状态统一 ✅**（3/3）：死代码不存在（跳过）+ 3 视图 first-load+v-loading 示范（ExportDialog/MyReviewsPanel/GtTraceabilityDialog）+ GtLoadingOverlay 5s 超时提示（5 vitest 全绿）+ 新增 `useFirstLoad.ts` composable
- **8.3 穿透导航面包屑 ✅**（4/4）：useNavigationStack（MAX_DEPTH=20 + push/pop/jumpTo/clear）+ usePenetrate 10 种穿透方法自动 push + GtPageHeader 自动渲染 DrilldownBreadcrumb + initGlobalBackspace 已接入 + Property 9 fast-check 4 不变量（25 tests 全绿）
- **8.4 GtEmpty/GtStatusTag/statusEnum ✅**（4/4）：GtEmpty 5 preset + 13 处替换（baseline 182→169）+ GtStatusTag 4 视图接入 + ESLint `no-status-string-literal`（baseline 202）+ statusEnum.ts 中文 label 全量映射 + getStatusLabel/getStatusColor 工具函数（15 vitest）
- **8.5 错误处理统一 ✅**（2/2）：handleApiError 扩展 423/422 AI/422 冲突 3 种中文映射（11 vitest）+ Top 15 文件 ~30 处 ElMessage.error 替换（views 内剩余 6 处为特殊处理）
- **8.6 分页统一 ✅**（1/1 必需）：WorkpaperList + Adjustments + Misstatements 3 视图新增 el-pagination（page_size=50 客户端分页）；IssueTicketList + StaffManagement 已有

### Sprint 2 Req 13 全平台中文化（2026-05-27 完成）

- **13.1 术语表 ✅**：`docs/i18n/business-glossary.md`（60+ 审计术语 + 40+ UI 通用术语 + 技术白名单 8 类）
- **13.2 扫描脚本 ✅**：`scripts/_chinese_localize.py`（--scan/--dry-run/--apply 三模式 + 完整白名单）
- **13.3-13.7 批次替换 ✅**（合并 Top 20）：7 视图中文化（ConsistencyDashboard/SubsequentEventsPanel/VRCoverageTab/EnumDictManager/LogViewerPanel/EnumDictTab/WpTemplateTab），baseline 337→0
- **13.8 后端双语化 ✅**：10 个 router 文件 14 处 HTTPException.detail 改为 `{message: 中文, message_en: English}`
- **13.9 ESLint `no-english-ui-text` ✅**：defineTemplateBodyVisitor + 白名单 + 程序值排除，**baseline=0**
- **13.10 Property 10 ✅**：`test_property_10_chinese_coverage.py`（2 tests：静态扫描=0 + baselines.json 守门）
- **13.11 验收 [~]**：待真实项目 UAT（需 start-dev.bat）
- **13.12 清理 [~]**：保留扫描脚本供后续复用
- **Sprint 2 全部完成**（Req 8 + Req 13）

### Sprint 3 Req 9/10/11 进展（2026-05-27 完成）

- **Req 9 数据信任度可视化 ✅**（7/7）：trust_score_service（5 层并行查询 + Redis 60s TTL 缓存 + invalidate）+ router §124 + TrustScorePanel.vue（5 Tab el-drawer + 5 子组件）+ CellContextMenu "📋 数字信任度" + 5 视图接入 + 14 pytest + 8 vitest
- **Req 10 可解释状态机 ✅**（5/5）：allowed_actions_service（5 模块 SM + guard 预查询）+ router §125 + StatusMachinePanel.vue + 5 视图接入 + Property 11（6 tests）+ 新增 `state_machines/` 目录
- **Req 11 时光机自动快照 ✅**（8/8 必需）：time_machine_service（RFC 6902 jsonpatch 反向 diff）+ router §126 + cleanup_worker（每日 03:00）+ TimeMachineDrawer.vue + 3 视图接入 + useWorkpaperAutoSave 5 分钟快照 + Property 12（4 tests）
- **新增依赖**：jsonpatch（RFC 6902 JSON Patch）
- **新增目录**：`backend/app/services/state_machines/` + `backend/app/workers/`
- **Sprint 3 全部完成**，下一步 Sprint 4（Req 12 编辑器与性能）

### Sprint 4 Req 12 编辑器与性能（2026-05-27 完成）

- **12.1 WorkpaperEditor 瘦身 [~]**：4 个 composable 骨架已建（useEditorToolbar/useEditorCycles/useEditorMode/editorDialogConfig）+ 12 处冗余别名已识别；完整迁移需独立 Sprint（依赖拓扑风险高）
- **12.2 序时账虚拟滚动 [~]**：el-table-v2 条件渲染（>1000 行切换）+ 后端 page_size Query(100, ge=1, le=1000)；列宽/右键/排序待后续迭代
- **12.3 autoSave 60s ✅**（3/3）：intervalMs 120→60s + recordEdit 10 次切 30s + 失败重试 + beforeunload sendBeacon + Property 13（7 vitest）
- **12.4 console.log 清零 [~]**：logger.ts wrapper + ESLint no-console error + Top 28 处替换（8 文件）；余下渐进治理
- **12.5 Property 13 ✅**：7 tests 全绿（60s 触发 / 快速模式 / 重试 / beforeunload / 恢复）
- **Sprint 4 全部完成**（核心功能 + 骨架 + 渐进治理模式）

### V3 Spec 总体状态（2026-05-27）

- **Sprint 0-4 全部完成**：98 必需任务中 ~85 标 [x] + ~13 标 [~]（渐进治理/待真实环境）
- **Sprint 回归 14.1/14.2/14.3 已通过**：后端 145 passed (29.70s) + 前端 126 passed (4.61s) + Playwright E2E 登录→仪表盘→项目→底稿核心链路通过；14.4 待合伙人验收
- **Sprint 回归 14.3/14.4 待真实环境**：Playwright E2E + UAT 需 start-dev.bat（localhost:3030/9980 未启动时 ERR_CONNECTION_REFUSED）
- **新增 composable**：useEditorToolbar / useEditorCycles / useEditorMode / useFirstLoad / useNavigationStack
- **新增配置**：editorDialogConfig.ts（11 dialog 声明式配置）
- **autoSave 新契约**：默认 60s + 10 次编辑切 30s + 保存成功恢复 60s + 失败重试 1 次 + beforeunload sendBeacon
- **gin_index_monitor 表名 bug 修复**（2026-05-27）：`TABLE_NAME` 从 `"working_papers"`（复数，错误）改为 `"working_paper"`（单数，与 ORM `__tablename__` 一致）+ 已在 PG 创建 `idx_wp_parsed_data_gin` GIN 索引（jsonb_path_ops）
