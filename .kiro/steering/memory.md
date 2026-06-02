---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。归档历史见 `git show <旧commit>:.kiro/steering/memory.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出分步但连续做完**：一次不要太长、大改动拆小批次，但要做完整个任务不要每段停问（只在真正需决策时停）
- **任务标记不能假绿**：标 completed 必须有实际代码+测试通过证据；外部依赖如实标 `[ ]*`，用"代码已改未实测"措辞；`*` 可选任务也要做完（除非明确跳过）
- **彻底解决不绕开**：错误必复现+定位根因+修主代码+加防御测试，绝不"换参数避开"
- **触类旁通 grep**：发现一处反模式立即 grep 全仓找同类一次修完
- **优先用 codegraph**：改动前先 `node C:\tools\codegraph\dist\bin\codegraph.js impact "符号"` 看影响面；理解调用链用 `callers`/`callees`；搜符号用 `query`；AI 任务上下文用 `context "描述"`——比手动 grep 快且全，能用则必用
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端；设计阶段必做"现状 grep 确认"（迁移/端点/依赖是否已有产物，外部依赖标降级方案+切换点）
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；硬编码不接 i18n + ESLint 卡点
- **中文场景全链路不能崩**：中文文件名下载（Content-Disposition 必 RFC5987）、中文项目名/客户名/底稿名导出、中文数据查询导出均须实测过
- 功能收敛停加新功能，核心 6-8 页做到极致，空壳标 developing；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- **文档/文件夹级 LLM 对话是最实用核心功能**：任意文档/文件夹发起 AI 对话，自动注入当前文档+关联知识库作 RAG 上下文（spec `doc-level-ai-chat`）
- git 单 commit 提交所有变更；**push 前必先 fetch 同步**（stash→fetch --prune→评估 ahead/behind→决策→pop→commit/push）；**协作走 PR 不直推 main**（紧急例外需用户拍板）；默认分支 `main`（非 master）
- 提建议前先验证不引用过时记录；完整复盘诚实暴露问题不粉饰；PDCA：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发 6000 人；底稿编码致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A 报表/调整 B 控制了解 C 控制测试 D 销售收入 E 货币资金 F 采购存货 G 投资 H 固定资产 I 无形资产 J 职工薪酬 K 管理 L 筹资 M 股东权益 N 税费 S 专项

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`；测试用户 admin/admin123
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`（勿混）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)；health `/api/health`
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）；views/components/composables 在其 `src/`
- **MCP 已接入 7 个（2026-06-02 实测全 Connected）**：playwright(23,浏览器实测)/fetch(1,网页转md)/context7(2,`resolve_library_id`+`query_docs` 查第三方库官方文档/版本，比 web 搜权威)/js-reverse(21,JS 逆向断点调试 set_breakpoint/step/evaluate_script/网络+WebSocket 抓包)/thinking(1,`sequentialthinking` 复杂竞态分步推理)/memory(9,知识图谱存储 create_entities/relations/search_nodes/read_graph——**与 memory.md 文件体系是两套，勿混用**)/codegraph(10,代码知识图谱)；依赖：locust/marked+dompurify/decimal.js/python-docx/PyYAML/fast-check/Jinja2/jsonpatch/sqlglot + 外部 LibreOffice
- **codegraph 已装（2026-06-02 重装 v0.9.8 官方 npm 包）**：`npm i -g @colbymchenry/codegraph`（自带 Node runtime 免编译，旧的 `C:\tools` clone+build 路径已不存在）；CLI 在 `~/AppData/Roaming/npm/codegraph`；项目已 `codegraph init -i D:/GT_plan` 索引（59540 节点/131401 边/3205 文件）；CLI 支持 query/callers/callees/impact/affected/context/trace/explore/files/status/serve(MCP)
- **⚠️ codegraph MCP 配置（已修 2026-06-02）**：`.kiro/settings/mcp.json` 用 `command:"npx"` args=`["-y","@colbymchenry/codegraph","serve","--mcp","--no-watch","-p","D:/GT_plan"]`（**勿用 node+绝对路径**：用户名 `杨志` 非 ASCII 易碎；**路径是 `D:/GT_plan` 不是 `D:/GT_workplan`**——旧配置两处错误致 "Connection closed"，真因是包根本没装+路径错，非缺 `--mcp`）；`serve` 必加 `--mcp` 才走 stdio；启动后常驻+stderr "Attached to shared daemon" 即正常；autoApprove 已列全 10 个 codegraph_* 工具
- **callers 对 Python class 引用检测偏弱**（class 无"调用"语义，查模块名常显示无 caller，需配 grep 二次确认，勿仅凭 codegraph 判孤儿）
- **✅ codegraph MCP 全工具链路实测通（2026-06-02）**：status/context/files/explore/callers 均正常返回（59540 节点/131401 边/WAL+FTS5）；explore 每 project 限 2 次调用且每次约 6 文件，超范围用 Read；分析确认 `get_authenticated_container`(core/container.py:65) 是死代码（0 引用 + docstring 自承认无法注入 user，应删，认证容器用 deps.get_current_user 路径）
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）
- **底稿模板源**：`backend/wp_templates/`（按循环 A~S 分目录），`scripts/analyze/scan_wp_templates.py` 扫描输出 `backend/data/gt_template_library.json`
- **干净验证法**：start-dev uvicorn `--reload` 父子进程互拉 kill 不净 → venv 另起端口（如 9981）`python -m uvicorn ... --port 9981` 绕开 reloader；in-process ASGI httpx（`httpx.ASGITransport(app=app)`）直调端点最快

## 迁移与 PG schema（D6 MigrationRunner 运行时迁移，非 alembic）

- 启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞号字母序靠后者静默丢失，scan_migrations 已加同号检测抛 RuntimeError）；**当前最高 V050**
- V040 冲突已修(重编号→V044)；V043 pgvector 容错化（DO/EXCEPTION 优雅跳过，降级 VECTOR_STORE_BACKEND=pgtext）；V045 prior_year_project_id / V046 4 附注懒建表 / V047 note_locks TIMESTAMPTZ / V048 system_settings / V049 report_snapshot.is_stale / V050 app_audit_log
- **⚠️ `CREATE TABLE IF NOT EXISTS audit_log` 是 no-op**：该名被 Metabase 共库占用（真实 schema 无 action 列）→ 应用审计写独立表 `app_audit_log`；建表前先 `to_regclass`+`information_schema.columns` 查真实 schema
- **本地 PG schema 漂移已修**（critical=0）：drift detector pkgutil walk import 全 model + 过滤 Metabase 共库污染 + 按 critical_count 判 degraded
- **🔴 projects 表无 year/template_version_id 列**：年度用 `EXTRACT(YEAR FROM audit_period_end)::int`；materiality 年度列=`overall_materiality`；人员姓名在 `staff_members.name`（users 无 display_name），JOIN 用 `project_assignments.staff_id`；database.py 已加 `async_engine = engine` 别名
- **🟡 底稿名占位脏数据已修（24 条）**：项目 df5b8403 的 wp_index 有 24 条 `底稿{code}` 占位名（B1/D2-2/E1/K14 等细分编码），根因=`wp_standard_conversion_service._generate_one_workpaper` + `chain_orchestrator` 用 `lib_entry.get('name') or f"底稿{code}"` 兜底，而 gt_template_library.json(331条) 不覆盖这些细分编码→兜底成占位；已 UPDATE 真名（按致同体系+wp_templates 文件名推导）；**根治待办**：scan 脚本编码提取正则只取首段编码，细分 sheet 级编码(D2-2/E1-1)未进库→生成时取不到真名（CODE_PATTERN 只匹配文件名首编码）
- **🔴 wp_template_registry 表实际不存在**：gt_template_library.json（331条，scan 重生成路径已更新为 backend/wp_templates/）是唯一权威源；scan 脚本末尾 sync_registry 因表不存在静默跳过（已加白名单不报 drift）
- **🔴 真实列速查**：trial_balance 金额=unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount/opening_balance（无 closing_balance，科目列=standard_account_code）；financial_report=row_code/row_name/current_period_amount/source_accounts（无 amount/line_code）；adjustments=adjustment_no/adjustment_type/account_code/review_status（无 status/entry_type/summary）；adjustment_entries=standard_account_code；working_paper 无 year/wp_code（wp_code 在 wp_index，JOIN wp_index_id）；issue_tickets 负责人=owner_id 不软删；CellAnnotation 作者=author_id
- **🟢 序时账/明细账数据干净**：tb_ledger(82384 行)+tb_aux_ledger 借贷双非零行=0（每分录行单边，converter `safe_decimal` 空→None 非 0）；序时账明细唯一同时显示借+贷的是合成的「N月 本月合计」小计行（正常明细账格式，应显示借贷各自合计）
- **🟢 明细账月小计 off-by-one 已修（2026-06-02）**：`LedgerPenetration.vue` 的 `ledgerDisplay`+`auxLedgerDisplay` 两处月小计 bug——累加 monthDebit/Credit 在月份边界判断**之前**→上月「本月合计」错并入本月首笔（实测 1 月应 140094.82 算成 188423.58）；修复=边界结算移到累加前 + 归零（非赋当前行值）；加 5 条回归测试守护（月分组/守恒/运行余额）
- **🔴 明细账改进待办（2026-06-02 分析，未修）**：①**运行余额/月小计按页算→第2页起全错**（loadLedger offset 分页 page_size=100，但 ledgerDisplay 每页都从整期 currentAccountOpening 重算余额；期初接口只传 year 不传页码）——科目本期>100 笔翻页即余额错+跨页月小计被拆；②筛选/排序后小计对不上（锚点行滤掉但小计按整页原始数据算）；③回归测试是 copy 生产函数到测试里测（改 .vue 忘同步副本仍绿）→建议抽 `utils/ledgerDisplay.ts` 组件+测试共用；④账务计算应下沉后端（已有 get_ledger_entries_cursor 游标接口但 loadLedger 没用，理想后端直接返 running_balance+插好小计行）；⑤主表缺 counterpart_account(对方科目)列+本年累计借贷列；⑥虚拟滚动名不副实（>1000 切 el-table-v2 但仍每页 100 行加载）；**优先级 ①(正确性)+③(让测试真生效)**
- **🔴 system_settings 已建(V048)**；真实 PG 5 项目多 standalone，**0 个 consolidated 项目**（合并 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全但 audit_period_end 为 NULL
- **契约测试守护**（CI 根治整类 schema 漂移 500）：`test_raw_sql_schema_contract.py`(表级纯静态)+`test_raw_sql_column_contract.py`(列级 pg_only sqlglot)；新增裸 SQL 引用不存在表/列即 CI 红；存量债务登记 `_KNOWN_PHANTOM_DEBT`/`_COLUMN_ALLOWLIST`（剩 wp_template_registry）

## 任务状态

### LLM（本地 vLLM 已跑通，2026-06-01 实测）
- vLLM `localhost:8100` 模型 `Kbenkhaled/Qwen3.5-27B-NVFP4`；`.env` `WP_AI_SERVICE_ENABLED=True`（默认 False）
- **两套 LLM 客户端**：①`llm_client.chat_completion()`（httpx+熔断器，多数 wp_llm_prompts/role_ai/pm 用）②`AIService(db).chat_completion()`（OCR/knowledge/contract/wp_fill 用，需真实 DB 会话查 active model）
- **✅ 已修 bug**：get_llm_client 不存在（wp_chat_service/wp_document_recognizer 改用 chat_completion）+ vLLM 拒多条 system 消息（ai_service 加 `_merge_system_messages()`，llm_client RAG 注入改追加首条 system）；doc_ai_chat + wp_chat 端到端实测通
- **🔴 embedding 404**：vLLM 未起 embed task → RAG 向量召回降级 ilike（semantic_search 不崩，build_index 会抛错）；恢复语义检索需另起 vLLM embed 实例
- **🔴 孤儿代码 AIChatService**(ai_chat_service.py)：0 router 引用，被 doc_ai_chat 取代；内部实际用 `KnowledgeIndexService(db).search()` + `AIService(db)`（非"调不存在方法"，旧记录有误）；配套 `AIChatSession`/`AIChatMessage` ORM(ai_models.py)+表 = 完整 DB 持久化方案但全孤儿
- **🟢 知识库收口完成（2026-06-02）**：①旧 `KnowledgeService`(knowledge_service.py)已删（全仓 0 引用）；②孤儿 `AIChatService`(ai_chat_service.py)已删（其 AIChatMessage 用 content/token_count 字段名但模型实为 message_text/tokens_used，接线即崩）；③**doc_ai_chat 内存历史→DB 持久化**：新建 `doc_chat_persistence.py` 复用现成 `ai_chat_session`/`ai_chat_message` 表（用 `context_summary` 存 `{doc_type}:{doc_id}:{user_id}` 定位键，零新增列零漂移），doc_ai_chat 的 `_chat_history` 字典已替换，history 端点改 async DB 读；实测持久化往返+幂等通过（重启不丢历史）
- **🟢 doc-chat "GET history=0" 真因（2026-06-02 实测闭环）**：后端持久化+_stream_chat 自建 `async_session` 全对（in-process ASGI 实测 GET=2/DELETE 后=0）；之前"问题依旧"是 ①stale uvicorn 跑旧代码（FastAPI 不热加载）②**前端 `useDocAiChat.fetchHistory` 读 `data.messages` 顶层，但 `ResponseWrapperMiddleware` 把所有 2xx JSON 包成 `{code,message,data}`→服务端历史永远加载不出**（已修：解信封读 `body.data.messages`，原生 fetch 非 apiProxy 需手动解）；旧单测 mock 的是未包装 shape 从没守住该契约→已改 mock 真实信封；**铁律：原生 fetch 调后端必手动解 `{code,message,data}` 信封**
- **doc-chat 干净验证法**：`httpx.ASGITransport(app=app)` in-process 直调最可靠（跑磁盘当前代码，无 stale server 风险）；隔离测持久化层用两个独立 `async_session`（A 写+commit / B 读）验跨 session 可见性
- `reference_doc_service.load_from_knowledge_base` 已接 `semantic_search(scope=knowledge_doc)` 主路径 + ilike 降级；service-dependency.md 是过时生成物（仍显示已断的边如 reference_doc→knowledge_service / ai_chat_service）
- **部署**：本机既是 vLLM GPU 节点又是后端机，后端内 `LLM_BASE_URL=localhost:8100` 天然可用；多用户访问只需 9980 对外、8100 不对外

### 合并模块（4 Phase 代码+测试完成，归档 `_archive/09-consolidation-phases/`）
- **合并核心模型**：合并数 = 各子企业个别数据汇总 + 差额表（差额表是专填调整+抵销分录的虚拟列，一般负数填列）；代码 `consol_amount = individual_sum + consol_adjustment + consol_elimination`
- 4 Phase 全 ✅ 代码+测试（merge 后 147+ passed）+ 16 ADR + 24 service + 全链路集成测试 `test_consol_full_chain_integration.py` + seed `seed_consol_uat.py`
- **统一卡点 = PG 0 个 consolidated 项目**（真实 UAT 全 data-blocked）+ Phase2/3 Playwright 待环境
- 详细复盘（PK 缺 uuid default bug / worksheet fixture 教训等）→ `#dev-history`

### 全局 7 模块改进 7 spec 全部 ✅ 实施完成（2026-06-01）
- A formula-engine-unification / B retrieval-kernel-unification / C doc-level-ai-chat / D report-config-baseline / E wp-ai-review-ux-fix / F global-modules-cleanup / G global-modules-p2-polish；残留仅 Playwright E2E 待环境
- 治理裁定：公式求值单内核(formula_engine)、审计只写哈希链、知识库删旧 KnowledgeService；向量存储选 pgvector；3 处联动断裂已修（知识文件→索引/模板 JSON→registry/报表主模板→克隆 stale）
- 详细盘点 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`

### git 状态（2026-06-02，最新 `cf69e50c` 已 push）
- 分支 `work/2026-05-30-wp-specs`（最新 `cf69e50c`，已 push origin）；本批 = **明细账月小计 off-by-one 修复**（LedgerPenetration.vue 两处 + 5 回归测试）；上批 `59994536` 知识库收口（删孤儿 + doc_chat_persistence + 前端信封解析 + codegraph MCP）；`f34a515a` schema drift 55→0 + 手册视图 ca713614；**待走 PR 合 main**
- **schema drift 修复细节**：55 项全 db_extra（DB 有 ORM 无），18 deleted_at（软删表）+ 其余按真实 PG 类型补 ORM Mapped[]；11 张基础设施表（app_audit_log/system_settings/note_section_*/review_conversation_*/wp_sheet_locks/wp_migration_snapshots/data_snapshots/group_note_templates/tb_aux_balance_summary）裸 SQL 管理无 ORM→加 KNOWN_ALLOWLIST；drift detector in-process 验证 TOTAL=0
- **🟢 手册视图已用 ca713614 完整版**（1201 行）：4 子页签全丰富 + count 真实计算 + 工作台/列表/手册 CSS 全（孤儿扫描 0）；ca713614 父=3df0fd61，merge-base=ea788c24；切勿被旧版覆盖
- **🔴 分叉分支隐患 `feature/report-module-enhancement-closure`(3df0fd61)**：含 WorkpaperWorkbenchView.vue **旧版**（365 行/41 guide CSS 类残缺/count 硬编码假数字），缺 work 分支的工作台+手册孤儿CSS全补(761c320a)和真实计数(fb58ac77)修复 → 合并时勿用其覆盖 work 版（726 行/79 CSS），否则回归
- **🔴 远程默认分支隐患**：`origin/HEAD→origin/master` 但 master 落后 main 298 commit（活跃主干是 main）→ 需 GitHub Settings 改默认分支（Agent 无法改远程设置）
- 远程 `origin = https://github.com/YZ1981-GT/GT_plan.git`（HTTPS）；gh CLI 已装(2.89.0)未登录（需用户本人浏览器授权）→ 建 PR 走网页 compare
- 文档类（memory/INDEX/复盘）冲突取并集，走 PR 让 GitHub 先暴露冲突，不本地直推 main

### 真正待办（外部依赖）
- LLM embedding 实例（恢复 RAG 语义检索）/ 6000 并发压测（Locust+真 PG）/ 钉集成 / 合并模块真实集团数据 UAT / GitHub 默认分支改 main / 走 PR 合入
- **架构 review 4 条已实证收口（2026-06-02，结论：多为设计取舍非 bug）**：①**死代码 `get_authenticated_container` 已删**（core/container.py，0 引用+自承认无法注入 user+指向不存在的 `get_container_with_user`；同时清理误导 docstring，health.py 仍用 `ServiceContainer`/`get_container` 不动）；认证 DI 事实标准是 deps.py 的 get_current_user/require_role/require_project_access（带 RLS+Redis 权限缓存），勿再造 user 容器 ②ServiceContainer 全 301 router 0 处用（仅 health.py 1 处），不补轮子 ③启动链路：部署是**单 worker** `uvicorn --reload`（start-dev.bat 无 --workers），当前不存在"多 worker 抢迁移"；但 `MigrationRunner.run_pending` **无 PG advisory lock**，仅靠 SQL `IF NOT EXISTS` 幂等+schema_version 去重→**上 gunicorn 多 worker 前必加 advisory lock**（DML 数据迁移竞态，届时开 spec）④301 router 文件 vs 134 include_router，孤儿已由 `check_router_registration.py` pre-commit hook 守护（§128 漏注册已补）；前端 developing:true 仅 5 个 ⑤LLMRateLimit 在 AuditLog 外层→429 不留痕，且 AuditLogMiddleware 本就 `非2xx 不记`+只记成功业务写操作（与 audit_decorator 分工），限流拒绝不留痕是一致设计；**待用户拍板：LLM 限流拒绝是否算需留痕的安全事件**（要则在 429 前单打一条安全日志，勿动中间件顺序）
- **专业裁定（2026-06-02）**：上述 4 条中前 3 条关闭（设计取舍非 bug，工程纪律已在线：失败不阻塞+契约测试+router hook+哈希链），**唯一值得现在动手=迁移并发锁**（挡在 6000 并发多 worker 目标前的真实前置阻断）；3 步方案：①最小=`pg_advisory_lock` 包 `run_pending`（十几行，抢锁者跑迁移其余跳过，立即让多 worker 安全+可回归测试，不牵动部署）②正解=迁移移出 lifespan 做独立部署步骤（`python -m app.core.migration_runner` 先跑，app 进程只 serve；改部署脚本+build_exe→开小 spec）③同把 drift/LibreOffice 一次性检查用同锁收敛为持锁进程独做；建议先做①
- **🟢 advisory lock 第①步完成（2026-06-02，真 PG 实测通过）**：`migration_runner.py` 加 `_MIGRATION_ADVISORY_LOCK_KEY=0x47544D4947`（b"GTMIG"）+ `_advisory_lock()` asynccontextmanager（PG 独立连接 `pg_advisory_lock`/`unlock`，非 PG 方言直接 yield 跳过，获取锁失败降级不加锁不阻塞启动）；`run_pending` 拆为外层加锁 + `_run_pending_inner` 主体；新增 `test_migration_runner_advisory_lock.py`（5 SQLite 层+2 `pg_only` 真竞态）；**实测**：连 docker audit-postgres 跑 7 passed（持锁阻塞第二 acquirer + 两 runner 并发建表恰执行一次不崩）+ 全 migration_runner 套件 68 passed 零回归。**竞态测试用高版本号 99001/99002+独立表名 `_test_advlock_t1`**（避免与真实库 V001-V050 撞号致 pending 空测不出）。第②③步（迁移移出 lifespan+一次性检查收敛）仍待，触发条件=决定上多 worker 时

### 已清零的近期修复（明细 → `#dev-history` 2026-06-01 节）
- 14 个 GET 500 全清零（429 端点巡检）+ sign_readiness/qc_open_issues/cost-overview 等 500 + ORM 类型漂移 + Content-Disposition 中文文件名全仓 RFC5987 + 回收站删不掉(app_audit_log V050)+ CORS(3030 白名单+尾斜杠)
- **WorkpaperWorkbenchView.vue 孤儿 CSS 全修**（Playwright 实测）：`<style scoped>` 原只定义 container 一个类，工作台进度卡片 + 手册视图 4 子页签(体系总览/审计流程/底稿关系/循环详解) + 默认列表共 ~40 个 gt-wp* 类无 CSS→无样式堆叠 div；已用 --gt-* 令牌补全；**教训：补孤儿样式必脚本扫"模板用到但 CSS 未定义"的类一次兜全，勿只看当前可视区**

## 操作铁律（详见 `#conventions`）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册否则前端 404；FastAPI 不热加载 router（改后重启）
- **service 只 flush 不 commit**：跨 service 编排由 router 统一 commit 保原子
- **asyncpg 事务污染**：事务 aborted 后连 SAVEPOINT 都被拒 → 根治=修最先失败的 SQL（非兜异常）；规则内 try/except 吞 SQL 异常不 rollback=反模式
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL 必加 SQLite dialect 检测
- **历史档案不回填修改**：dev-history / spec-tasks 是 append-only
- **PowerShell**：写中文/emoji 用 fsWrite（禁 `-replace`/`Set-Content` 处理中文）；长 commit msg 用 `git commit --% -m "..."`；读中文输出先 `chcp 65001 + [Console]::OutputEncoding=UTF8`
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；`http.get/post`（utils/http）返完整响应体需 `.data`
- **枚举成员引用前实证**：`python -c "getattr(Enum,'X','MISSING')"` 核对大小写（小写 draft/approved）
- **merge 跨阶段签名变更必 grep 调用方**（sync↔async / 删公开方法）
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；FastAPI 无尾斜杠路由 307 重定向绝对 URL 会跨域→前端路径匹配后端尾斜杠
- **hypothesis PBT 调速**：max_examples 5（用户明确要求，禁默认 100）

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，无需裁剪（dev-history 是 append-only 审计轨迹）
- 技术事实/端点速查/PG schema/spec 历史/近期修复明细 → `#dev-history` grep 关键词
- 架构/系统规模/数据流 → `#architecture`；编码规范/UI 视觉/操作铁律详解/PG 运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`；合并模块体检 → `docs/proposals/consolidation-module-status-and-proposal.md`；全局 7 模块 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`
