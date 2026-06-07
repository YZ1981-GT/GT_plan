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
- **🔴 codegraph 优先于 grep（铁律，2026-06-06 强化）**：搜符号/查调用链/看影响面**第一选择永远是 codegraph**（已索引 6.1万节点/13万边，比手动 grep 快且全）——MCP 首选 `codegraph_context "任务描述"`(一次出任务上下文) / `codegraph_search`(符号定位) / `codegraph_callers`+`codegraph_callees`(调用链) / `codegraph_impact`(改动影响面) / `codegraph_trace`(A→B 路径)；CLI 直调 `codegraph query/callers/callees/impact/context`(cwd=D:/GT_plan 自动检测,旧 `C:\tools` 路径已废)。**grep 仅用于**：codegraph 查不到的非符号文本(中文串/注释/配置值)、Python class 引用二次确认(callers 对 class 偏弱)、跨文件字面量统计。改动前 impact、理解代码 context、找定义 search——能用 codegraph 必用，别先 grep
- **触类旁通**：发现一处反模式立即全仓找同类一次修完（codegraph callers/search 优先，grep 补充）
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端；设计阶段必做"现状确认"（codegraph 优先：迁移/端点/依赖是否已有产物，外部依赖标降级方案+切换点）
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；硬编码不接 i18n + ESLint 卡点
- **报表金额统一以"元"为默认单位**：报表主表+穿透弹窗+构成科目弹窗所有金额统一元（不默认万元），避免单位混乱；`line-composition` 端点已改为查 `trial_balance.audited_amount`（审定数，与报表同源），不再查 `tb_balance.closing_balance`（原始导入可能万元单位）
- **中文场景全链路不能崩**：中文文件名下载（Content-Disposition 必 RFC5987）、中文项目名/客户名/底稿名导出、中文数据查询导出均须实测过
- 功能收敛停加新功能，核心 6-8 页做到极致，空壳标 developing；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- **文档/文件夹级 LLM 对话是最实用核心功能**：任意文档/文件夹发起 AI 对话，自动注入当前文档+关联知识库作 RAG 上下文（spec `doc-level-ai-chat`）
- git 单 commit 提交所有变更；**push 前必先 fetch 同步**（stash→fetch --prune→评估 ahead/behind→决策→pop→commit/push）；**协作走 PR 不直推 main**（紧急例外需用户拍板）；默认分支 `main`（非 master）
- 提建议前先验证不引用过时记录；完整复盘诚实暴露问题不粉饰；PDCA：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发 6000 人；底稿编码致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A 报表/调整 B 控制了解 C 控制测试 D 销售收入 E 货币资金 F 采购存货 G 投资 H 固定资产 I 无形资产 J 职工薪酬 K 管理 L 筹资 M 股东权益 N 税费 S 专项
- **循环→审计阶段映射（2026-06-05 最终确认）**：承接与计划=Q+B（B 循环含 B1A 业务承接/B1B 保持/B2 前任沟通/B3 独立性 + B10~B60 计划了解，不可按编号拆循环级聚合） / 控制测试=C / 实质性程序=D~N+S+L+M / 完成与报告=A；前端 4 阶段流程图展示

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`；测试用户 admin/admin123
- **JWT 有效期**：access_token 1440 分钟（24h）/ refresh_token 30 天（开发环境，config.py 已改，旧默认 30min/7d 太短导致频繁踢登录）
- **rtk 0.42.1 已装**（`C:\Users\杨志\.local\bin\rtk.exe`，已加用户 PATH）：CLI token 压缩代理，Windows 原生无 hook 自动重写（需手动 `rtk` 前缀或 WSL）；`rtk git status` 节省 ~80%；pytest 全 pass 时回退 fallback 不额外压缩（正确）；用 `rtk gain` 看统计
- **rtk steering 规则已建**（`.kiro/steering/rtk-proxy.md`，inclusion: always）：executePwsh 跑 git/pytest/vitest/playwright/eslint/tsc/docker 时自动加 `rtk` 前缀；管道/重定向/fetch/stash/需精确解析的除外
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`（勿混）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)/`audit-pgbouncer`(6432, DB_USE_PGBOUNCER=True 时启用)；health `/api/health`
- **新增依赖（2026-06-04 四 spec 落地）**：schemathesis 3.39.16（强制 starlette<1→0.52.1 降级，与 FastAPI 0.135.3 兼容）/ opentelemetry 全家桶 1.42.1 / instructor 1.15.1 / bm25s 0.3.9 / python_calamine（已有）；`_zh_tokenize.py` 中文 bigram 分词（无 jieba）
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）；views/components/composables 在其 `src/`
- **MCP 配置 7 个，2026-06-04 实测仅 Playwright+Codegraph 在线（js-reverse/context7/fetch/thinking/memory 未连接，待排查 mcp.json）**：
  - **codegraph**(10)：`codegraph_context`(首选，任务上下文一次出) / `codegraph_search`(符号定位) / `codegraph_callers`/`codegraph_callees`(调用链) / `codegraph_impact`(重构影响面) / `codegraph_trace`(A→B 路径) / `codegraph_explore`(多符号源码) / `codegraph_node`(单符号详情) / `codegraph_files`(项目文件树) / `codegraph_status`(索引健康)
  - **playwright**(23)：`browser_navigate`/`browser_snapshot`(优于截图，可交互)/`browser_click`/`browser_type`/`browser_fill_form`/`browser_evaluate`(执行 JS)/`browser_network_requests`(抓包)/`browser_console_messages`/`browser_take_screenshot`/`browser_wait_for`/`browser_tabs`/`browser_select_option`/`browser_hover`/`browser_drag`/`browser_file_upload`/`browser_drop`/`browser_press_key`/`browser_handle_dialog`/`browser_navigate_back`/`browser_resize`/`browser_close`/`browser_network_request`(单请求详情)/`browser_run_code_unsafe`
  - **js-reverse**(21)：`set_breakpoint_on_text`/`step`(over/into/out)/`get_paused_info`/`evaluate_script`(断点内求值)/`search_in_sources`(全源码搜索)/`get_script_source`/`save_script_source`(美化保存)/`list_scripts`/`list_network_requests`/`get_request_initiator`(请求调用栈)/`list_console_messages`/`get_websocket_messages`/`navigate_page`/`new_page`/`select_page`/`select_frame`/`take_screenshot`/`list_breakpoints`/`remove_breakpoint`/`break_on_xhr`/`pause_or_resume`
  - **context7**(2)：`resolve_library_id`(库名→ID) + `query_docs`(查官方文档/代码示例，比 web 搜索权威)
  - **fetch**(1)：`fetch`(URL→markdown，max_length/start_index 分页)
  - **thinking**(1)：`sequentialthinking`(复杂竞态/多步推理，可分支/修正)
  - **memory**(9)：`create_entities`/`create_relations`/`add_observations`/`search_nodes`/`read_graph`/`open_nodes`/`delete_entities`/`delete_relations`/`delete_observations`——**与 memory.md 文件体系是两套，勿混用**
- **MCP 工具选用决策**：改动前理解代码→`codegraph_context`；查第三方库用法→`context7`；前端 E2E 实测→`playwright browser_snapshot`+交互；前端 runtime bug→`js-reverse set_breakpoint_on_text`+`step`+`evaluate_script`；复杂逻辑推演→`thinking sequentialthinking`；跨对话存结论→`memory create_entities`
- **codegraph 已装（2026-06-02 重装 v0.9.8 官方 npm 包）**：`npm i -g @colbymchenry/codegraph`（自带 Node runtime 免编译，旧的 `C:\tools` clone+build 路径已不存在）；CLI 在 `~/AppData/Roaming/npm/codegraph`；项目已 `codegraph init -i D:/GT_plan` 索引（59540 节点/131401 边/3205 文件）；CLI 支持 query/callers/callees/impact/affected/context/trace/explore/files/status/serve(MCP)
- **OnlyOffice 配置变更（2026-06-07）**：`enabled` 判定改为检查 `ONLYOFFICE_URL`（非 JWT_SECRET），有 URL 即启用；JWT 验证变为可选——无 secret 时 callback 直通不签 JWT（测试环境直连 OnlyOffice Docker 无需鉴权）；生产部署须配 `ONLYOFFICE_JWT_SECRET` 启用签名校验；**前端集成方式=JS API**（`new DocsAPI.DocEditor(containerId, config)`），不可用 iframe src 拼 URL（那是错误方式）；`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`（Docker 容器回调主机）；OnlyOffice Docker 版本 9.4.0 已确认可用；**document.url 必须用 signed-download 免 auth 端点**（HMAC 签名 10min 有效），OnlyOffice 不携带 Bearer header；fallback 默认值改为 `host.docker.internal:9980`（容器内 localhost 指向自身非宿主机）；uvicorn `--reload` 不重新读 .env（需完全重启进程）
- **⚠️ codegraph MCP 配置（Cursor 2026-06-04）**：**Cursor 只读 `.cursor/mcp.json`**（非 `.kiro/settings/mcp.json`）；`codegraph install --target cursor --location local` 生成；`command:"codegraph"`（全局 npm，勿 npx 每次拉包）+ `args:["serve","--mcp","--no-watch","--path","D:/GT_plan"]` + `"type":"stdio"`；**勿用 `-p`**（仅 `serve` 子命令支持 `--path`）；Kiro 侧 `.kiro/settings/mcp.json` 已同步；改后 **重启 Cursor / Reload MCP** 才挂载 `codegraph_*` 工具
- **callers 对 Python class 引用检测偏弱**（class 无"调用"语义，查模块名常显示无 caller，需配 grep 二次确认，勿仅凭 codegraph 判孤儿）
- **✅ codegraph MCP 全工具链路实测通（2026-06-02）**：status/context/files/explore/callers 均正常返回（59540 节点/131401 边/WAL+FTS5）；explore 每 project 限 2 次调用且每次约 6 文件，超范围用 Read；分析确认 `get_authenticated_container`(core/container.py:65) 是死代码（0 引用 + docstring 自承认无法注入 user，应删，认证容器用 deps.get_current_user 路径）
- **codegraph 索引自动同步 hook 已建（2026-06-05）**：`.kiro/hooks/codegraph-index-sync`，fileEdited 触发（backend services/routers/models + frontend views/components/composables），runCommand `codegraph sync`（从 cwd 自动检测项目，**不支持 `--path` 参数**），30s 超时；确保 codegraph MCP 工具查到的符号/调用链/影响面始终最新
- **codegraph CLI 直调可用**：`codegraph status/sync/query/callers/callees/impact/context/trace/explore`（全局 npm 装，cwd=D:/GT_plan 自动检测）；CLI 比 MCP 轻量（不走 JSON-RPC），适合 hook 和批量场景
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）
- **开发工具链（dev-tooling-modernization spec，2026-06-04 落地）**：①gitleaks `.gitleaks.toml`+`.git-hooks/pre-commit`(缺 binary 优雅降级)+CI `gitleaks-action@v2` ②SQLFluff `.sqlfluff`(dialect=postgres,raw)+基线 1718 violations/47files+CI warning 级 ③uv 0.10.4 全局已装+CI 5 job `uv pip install --system`+pip fallback+`docs/dev-guide-uv.md` ④Docling 裁掉(torch 2-4GB 致命) ⑤DSPy 仅文档(`docs/dspy-feasibility-evaluation.md`)；验证脚本 `backend/scripts/check/check_gitleaks_config.py`
- **底稿模板源**：`backend/wp_templates/`（按循环 A~S 分目录），`scripts/analyze/scan_wp_templates.py` 扫描输出 `backend/data/gt_template_library.json`
- **干净验证法**：start-dev uvicorn `--reload` 父子进程互拉 kill 不净 → venv 另起端口（如 9981）`python -m uvicorn ... --port 9981` 绕开 reloader；in-process ASGI httpx（`httpx.ASGITransport(app=app)`）直调端点最快
- **LLM 上下文压缩类工具不引入（2026-06-04 决策）**：Headroom/类似（SmartCrusher 压 JSON / CCR 可逆 / Kompress-base）对本项目价值低——本地 vLLM 自带 prefix caching、token 成本=GPU 时间非外部 API 计费、审计金额/科目编码精度敏感不能被通用 NLP 压缩误删；RTK 已覆盖 CLI 输出压缩 90% 价值，不再叠中间件
- **外部 agent harness 配置包不整体引入（2026-06-04，ECC 评估）**：Claude Code/Cursor/Codex 的 plugin/skill 包（如 affaan-m/ECC：63 agent + 249 skill + hook + rules）不在 Kiro 支持列表，install 脚本/hooks.json/plugin.json/marketplace 协议都依赖具体 harness，Kiro 用 `.kiro/steering` + `.kiro/specs` + 自定义 hook 体系另一套；同类问题（rule/skill/memory/spec/token 优化）已用本地方式覆盖；如需取经只能 cherry-pick 单个 markdown（如 rules/common/security.md / tdd-workflow / search-first）抄进 .kiro/steering 改中文+审计场景，**严禁 clone 整仓污染 working tree**
- **markitdown 0.1.6 已装本地（2026-06-04）**：`pip install 'markitdown[all]'` 进 backend venv（带 magika/onnxruntime/pdfplumber/mammoth/python-pptx/markdownify 全套依赖，纯本地无远端调用）；`backend/app/services/markitdown_service.py` 单例 + 延迟初始化 + 扩展名白名单(.pdf/.docx/.xlsx/.pptx/.html/.csv/.json/.epub 等共 17 种) + `convert_stream(BytesIO)` 最窄安全接口（不 fetch URI）；`backend/requirements.txt` 待补 `markitdown[all]`；知识库上传 `_extract_text_with_ocr` 已重构三级降级：MarkItDown 主→MinerU OCR(PDF扫描件)→PyPDF2/python-docx 兜底，覆盖面从原 PDF/docx 扩到全部办公格式

## 迁移与 PG schema（D6 MigrationRunner 运行时迁移，非 alembic）

- 启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞号字母序靠后者静默丢失，scan_migrations 已加同号检测抛 RuntimeError）；**当前最高 V062**（V059=deliverable_center / V060=temporary_grants / V061=knowledge_index_stale_tracking / V062=review_records_evidence_cols）
- V040 冲突已修(重编号→V044)；V043 pgvector 容错化；V045~V051 见上行；**V052 `wp_formula`**（自定义底稿公式绑定，R052 回滚配对）；**V053/V054 已启用**（2026-06-06 远程 commit 21520278：V053 projecttype enum 加值+R053 回滚 / V054 projects.is_deleted 默认值，原"V053-054 未用"已过时）；**V055 `project_creation_enhancement`**（projects 表加 3 列+unique 约束，R055 回滚配对）
- **⚠️ `CREATE TABLE IF NOT EXISTS audit_log` 是 no-op**：该名被 Metabase 共库占用（真实 schema 无 action 列）→ 应用审计写独立表 `app_audit_log`；建表前先 `to_regclass`+`information_schema.columns` 查真实 schema
- **本地 PG schema 漂移已修**（critical=0）：drift detector pkgutil walk import 全 model + 过滤 Metabase 共库污染 + 按 critical_count 判 degraded
- **🔴 projects 表无 year/template_version_id 列**：年度用 `EXTRACT(YEAR FROM audit_period_end)::int`；materiality 年度列=`overall_materiality`；人员姓名在 `staff_members.name`（users 无 display_name），JOIN 用 `project_assignments.staff_id`；database.py 已加 `async_engine = engine` 别名
- **🟡 底稿名占位脏数据已修（24 条）**：项目 df5b8403 的 wp_index 有 24 条 `底稿{code}` 占位名（B1/D2-2/E1/K14 等细分编码），根因=`wp_standard_conversion_service._generate_one_workpaper` + `chain_orchestrator` 用 `lib_entry.get('name') or f"底稿{code}"` 兜底，而 gt_template_library.json(331条) 不覆盖这些细分编码→兜底成占位；已 UPDATE 真名（按致同体系+wp_templates 文件名推导）；**根治待办**：scan 脚本编码提取正则只取首段编码，细分 sheet 级编码(D2-2/E1-1)未进库→生成时取不到真名（CODE_PATTERN 只匹配文件名首编码）
- **🔴 wp_template_registry 表实际不存在**：gt_template_library.json（331条，scan 重生成路径已更新为 backend/wp_templates/）是唯一权威源；scan 脚本末尾 sync_registry 因表不存在静默跳过（已加白名单不报 drift）
- **🔴 真实列速查**：trial_balance 金额=unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount/opening_balance（无 closing_balance，科目列=standard_account_code）；financial_report=row_code/row_name/current_period_amount/source_accounts（无 amount/line_code）；adjustments=adjustment_no/adjustment_type/account_code/review_status（无 status/entry_type/summary）；adjustment_entries=standard_account_code；working_paper 无 year/wp_code（wp_code 在 wp_index，JOIN wp_index_id）；issue_tickets 负责人=owner_id 不软删；CellAnnotation 作者=author_id
- **🟢 序时账/明细账数据干净（首汽租车 df5b8403）**：tb_ledger(82384 行) 借贷双非零行=0（每分录行单边）；序时账明细唯一同时显示借+贷的是合成的「N月 本月合计」小计行
- **🔴 辽宁卫生服务(37814426) 序时账数据异常**：tb_ledger 每条分录 debit_amount==credit_amount（借贷同值如 1303769.25/1303769.25），明显是导入适配器对该企业格式解析错误（源 Excel 可能"金额"列被同时映射到借贷双方）；待排查具体导入源文件格式+适配器 mapping
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

### git 状态（2026-06-06）
- 分支 `work/2026-05-30-wp-specs`；HEAD `5e9b7f3b` 已推远程；deliverable-center P0 完成+4 spec 归档+INDEX 更新；CI 可过待 PR 合 main
- 旧里程碑：`8ed2d45c`=audit-sheet-editable 归档 / `350ff25d`=5 tech specs 归档 / `0c0bae1a`=5 tech specs 实施代码
- **schema drift 二次修复（V051）**：方向=orm_extra（ORM 有 DB 缺），51 列 ALTER ADD + 2 enum ADD VALUE + 列级 KNOWN_COLUMN_ALLOWLIST（cell_annotations.sheet_name/adjustments.status/projects.template_version_id）+ 表级加 linkage_audit_log/seed_load_history；evidence_hash_checks.export_id 保持 VARCHAR（ORM 业务定义非 UUID）
- **🟢 B-Index 底稿目录"No Data"修复（2026-06-02，Playwright 实测通过）**：`wp_render_config.py` 新增 `_generate_b_index_data()`——当 B-Index sheet html_data 为空时自动从项目元数据生成 preparation_info（entity_name/period_end/preparer/reviewer）+ navigation_rows（同底稿其他 sheet 列表）；GtBIndex.vue 加 `empty-text="暂无索引数据"` 中文化
- **🟢 底稿全页签空态中文化（2026-06-02）**：GtAProgramConsole 加 empty-text / GtWpRenderer univer placeholder 改"表格底稿…数据尚未导入" / GtCNoteTable 加 el-empty 空态 / D-form 系列已有中文无需改
- **🟢 编制信息表头 4 处优化（2026-06-04，Playwright 实测通过，未提交）**：①**去重**——B-Index sheet 之前同时渲染 workpaper 级 `GtWpPreparationHeader`(表头顶部)+`GtBIndex` 内置编制信息块两个 → GtWpRenderer 加 `v-if="componentType !== 'b-index'"` 跳过顶部，B-Index 只留内置块；②**可折叠**——两个组件都加折叠条(点标题栏切 `is-collapsed`+收起/展开文案+收起时显示概要)；③**索引号移右上角**——表内单独「索引号」行删除，移到标题栏右上角常显，表头压成 3 列(GtWpPreparationHeader)/2 列(GtBIndex) 更紧凑；④**索引号 sheet 级**——GtWpRenderer 新增 `activeSheetIndexNo` 从 `activeSheetName` 末尾正则 `([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$` 提取(与后端 `_SHEET_INDEX_PATTERN` 同口径)，经 `:index-no-override` 传入 header，随 sheet 切换更新(底稿目录→D1/程序表→D1A/审定表→D1-1)，提取不到回退 wp_code；⑤**删完成度圈**——`gt-wp-renderer__completion` 进度圈(右上角 0%)与索引号重叠，用户不需要 → 模板块+CSS+`useWpCompletionRate` import/call 全删；测试 GtWpPreparationHeader.spec(8)+GtBIndex.spec(14 重写，原 12 全红=测旧表格式 API 已被 GtBArchitectureTree 取代)+workpaper 全量 33 文件 464 passed
- **🟢 render-config 模板路径回退修「暂无审计程序」回归（2026-06-04，in-process+Playwright 实测，未提交）**：根因=A 程序表/审定表/univer 网格三个自动生成器只用 `working_paper.file_path`，该字段为空(底稿未初始化文件)时取不到模板内容→程序表空。修复=`wp_render_config.py` 加闭包 `_resolve_template_file_path()`：file_path 缺失/文件不存在时回退 `find_template_file_any(wp_code)`(wp_templates/ 标准模板库)；三处生成器改用 `_template_file_path`；加 `from pathlib import Path` import。实测 D1A→18 程序/审定表→14 行/univer→cells 正常；新增 test_wp_program_extract 3 个回退回归测试(共 9 passed)+render pipeline 59 passed/1 skip；**注意**：route wpId 是 working_paper.id 非 wp-index 节点 id(后者 render-config 报「底稿不存在」404)；项目 37814426 的 D1 working_paper id=e56062ae
- **前端富文本编辑器现状（2026-06-02 grep 实证）**：已用 **TipTap 3**（`@tiptap/vue-3`+`starter-kit`+`extension-placeholder` 全 `^3.22.3`）；三块文字编辑区——附注 `DisclosureEditor.vue`→`NoteRichTextEditor.vue`（StarterKit 文字/混合型）、文字底稿 `WorkpaperWordEditor.vue`（三级降级 Univer Docs→mammoth→TipTap→textarea）、审计报告 `AuditReportEditor.vue`（报告状态+后端 PDF 导出任务+`@vue-office/docx` 预览+mammoth 解析）；表格底稿走 Univer（`@univerjs/preset-*`）；导出依赖 mammoth/xlsx/`@vue-office`；**均无 Word 式 A4 分页**。调研过 Umo Editor（`@umoteam/editor`，Vue3+Tiptap3，要求界面保留版权标识否则侵权，完整 Office 导入导出/协作属付费 Next/Server）拟补分页导出，**用户已决定暂不引入**
- **🟢 B-Index 索引导航改架构流程图（2026-06-02，Playwright 实测通过）**：删表格式索引导航（GtBIndex el-table+多选/无需打印逻辑全移除），重写 `GtBArchitectureTree.vue` 为流程图卡片（默认展示+完整 20 节点+点击跳转）；修 3 个原 bug：①原 v-show 默认折叠 ②原 buildTreeFromHtmlData 找 wp_code/wp_name 字段名不匹配致树空 ③原 onNodeClick 用 wpCode 当 wpId 跳转会 404→改 emit navigate(sheetName) 冒泡到 GtWpRenderer 切 activeSheetName（jump-to-section 事件之前根本没接线，已在 component 上补 @jump-to-section）
- **🟢 B-Index 底稿目录已覆盖整个审计循环（2026-06-06，commit 9e1bb066，in-process 实测）**：根因=`_generate_b_index_data` 只遍历当前 working_paper 的 classifications（仅当前 xlsx 内 sheets）。修复=新建 `wp_cycle_directory.build_cycle_workpapers`（查同 `audit_cycle` 全部 wp_index LEFT JOIN working_paper，wp_code 自然排序 D2-1<D2-10，标 is_current，wp_id 为空=未生成文件）+ `_generate_b_index_data` 加 `cycle_workpapers` 字段（透传 `wp_index.audit_cycle`）+ GtBIndex 新增「本循环底稿目录」卡片区（点击 router.push 跨底稿跳 WorkpaperEditor，当前底稿/未生成不跳）。测试=后端 5（test_wp_cycle_directory）+前端 5（GtBIndex.spec 新增循环目录块，补 useRouter mock）+既有 14 全绿。**实测**：D1 底稿 navigation_rows=20 内部 sheet + cycle_workpapers=8（D0~D7，D1 标当前）。**澄清纠偏**：D1A/D1-1~D1-16 是 sheet 级索引（已在 navigation_rows），D0~D7 才是同循环兄弟底稿（wp_index 表 wp_code，audit_cycle='D'）；memory 旧记录"D1 目录应含 D1A~D1-16"理解有误——那些本就在内部 sheet 列表里，真缺的是跨底稿 D0~D7
- **🟢 sheet 级索引号提取（2026-06-02）**：`_generate_b_index_data` 原用 `cls.wp_code`（永远父级 D1）→ 改用正则 `([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$` 从 sheet_name **末尾**提取真实索引（审定表D1-1→D1-1 / 应收票据审计程序表D1A→D1A），提取不到回退父 wp_code（如「附注披露信息（国企）」无尾码→D1，正确）；与 `_WP_CODE_PATTERN`（匹配文件名首段）方向相反——sheet 名索引在尾部
- **🟢 手册视图已用 ca713614 完整版**（1201 行）：4 子页签全丰富 + count 真实计算 + 工作台/列表/手册 CSS 全（孤儿扫描 0）；ca713614 父=3df0fd61，merge-base=ea788c24；切勿被旧版覆盖
- **🔴 分叉分支隐患 `feature/report-module-enhancement-closure`(3df0fd61)**：含 WorkpaperWorkbenchView.vue **旧版**（365 行/41 guide CSS 类残缺/count 硬编码假数字），缺 work 分支的工作台+手册孤儿CSS全补(761c320a)和真实计数(fb58ac77)修复 → 合并时勿用其覆盖 work 版（726 行/79 CSS），否则回归
- **🔴 远程默认分支隐患**：`origin/HEAD→origin/master` 但 master 落后 main 298 commit（活跃主干是 main）→ 需 GitHub Settings 改默认分支（Agent 无法改远程设置）
- 远程 `origin = https://github.com/YZ1981-GT/GT_plan.git`（HTTPS）；gh CLI 已装(2.89.0)未登录（需用户本人浏览器授权）→ 建 PR 走网页 compare
- 文档类（memory/INDEX/复盘）冲突取并集，走 PR 让 GitHub 先暴露冲突，不本地直推 main

### 真正待办
- **外部依赖**：LLM embedding 实例 / 6000 并发压测 / 钉集成 / 合并 UAT / GitHub 默认分支改 main / 走 PR 合入 / V052~V058 生产迁移
- **待建 spec**：底稿统一导入导出(`workpaper-unified-import-export`) / D1-4 坏账嵌套结构（枚举+auto-SUM+辅助预填）/ consol_disclosure_service 瘦身(1736行) / migration_runner 瘦身(1026行) / `workpaper-content-semantic-system`（底稿内容平台化，2026-06-06 提案+codegraph 分析；真空白=SheetContentType 声明式枚举替换 wp_generic_processor._detect_sheet_type 启发式 + account_package 科目工作包逻辑对象 + 字段级 requires_confirmation registry；**已有勿重建**=函证 callback 已铺 D2/F2/G7 三循环 + ai_content_log_service+ai_content_gate_rule 草稿阻断签发已闭环 + confirmation:received→useWorkpaperRefresh 已接线；试点选 D2 非 D1；硬伤=科目包程序状态须持久化不能纯前端聚合）
- **✅ deliverable-center 全量完成**：P0(0-8)+P1(9-15)+P2(16-22)+收尾(23,25) 全部 done，含原标 `*` 的 task 21(OnlyOffice)；93+ 后端测试+42 前端测试全绿；过程修 5 bug（ReportSnapshot.created_at→generated_at / CompletenessService 漏 ProjectType / 通知漏 title / archive-lock gap on create_version / render_and_store 卡 generating 态）；task 24 Playwright E2E 需启动 dev 后手动验证；**PBT 全部 max_examples≤5**
- **✅ 已完成 spec**：`report-view-slimdown`（2944→965 行，15 任务全部完成+3 项技术债已清，HARD_CAP 1110 已登记）；技术债修复：①纯函数(getRowType/formatReportAmount/equitySpanMethod/computeCrossCheckResults)提升为模块级 export ②useReportCellActions→aggregator+useReportDrilldown/useReportTrace/useReportContextMenu 三子 composable ③ReportDialogs→wrapper+ReportDrilldownDialogs/ReportTraceDialogs/ReportMappingDialog 三子组件
- **瘦身已完成**：disclosure_engine 1949→1601 / note_validation_engine 995→740 / 明细账翻页余额 P0 已修 / 功能空洞全消除 / 前端 CI 门禁失真已修回绿
- **铁律补充**：composable 抽取后必同步改其单测；spec 改一个文档必同步检查其余两个一致性；死代码删前必查 spec 历史决策；composable 实例传递不可重新 new（否则状态分裂）；4 个 Workpaper*Editor 故意保留素材勿删

> 2026-06-02~06-06 已完成修复/spec 详细明细已归档 → `#dev-history` grep 关键词查阅

- **🟢 markitdown 接入完成**（知识库三级降级链路已接好）

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
- **`dict.get(k, default)` 陷阱**：key 存在但值为 None 时返回 None 不返回 default（Pydantic 可选字段未填即 None）→ NOT NULL 列插入崩。写库前必用 `(data.get(k) or fallback)` 显式兜底，勿依赖 `.get(k, default)`（已咬过：procedure custom add 的 procedure_code=None 致 500）
- **merge 跨阶段签名变更必 grep 调用方**（sync↔async / 删公开方法）
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；FastAPI 无尾斜杠路由 307 重定向绝对 URL 会跨域→前端路径匹配后端尾斜杠；**禁止 `window.open` 下载认证资源**（新标签页不携带 sessionStorage token→401），必须用 `downloadFile`（axios blob + Bearer header）
- **UI 必用 GT 紫令牌**（`styles/gt-tokens.css`）：核心紫 `--gt-color-primary:#4b2d77` / 浅紫底 `--gt-color-primary-bg:#f4f0fa` / 紫边框 `--gt-color-border-purple` / 浅紫边框 `--gt-color-border-purple-light:#d8b8ee`；**禁用 Element 默认蓝 `--el-color-primary`/#409eff 作 fallback**；global.css 已映射 `--el-color-primary→GT紫`，但 `el-tag type="primary"` 仍渲染默认蓝（light-9 变量未全量重映）→ 需组件内 `:deep(.el-tag--primary)` scoped 覆盖三色，勿动全局级联
- **hypothesis PBT 调速**：max_examples 5（用户明确要求，禁默认 100）
- **TimestampMixin 列必须同步到手写 DDL**：ORM 继承 `TimestampMixin` 自动加 `created_at`/`updated_at` Mapped 列，但手写 V*.sql CREATE TABLE 不会自动加→漏写就 schema drift critical。铁律：凡 ORM 用 TimestampMixin 的表，DDL 必须显式写 `created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`（V057 editing_locks 踩过此坑 2026-06-06）
- **useExcelIO.exportTemplate existingData 必须等宽**：`existingData: any[][]` 所有行必须 pad 到相同列数（maxCols），否则 `xlsx-js-style` 写 cell 引用越界致 xlsx 损坏打不开；多子表导出用 `applyStyles: false`（style template 迭代 columns×rows 在非均匀数据上越界）

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，无需裁剪（dev-history 是 append-only 审计轨迹）
- 技术事实/端点速查/PG schema/spec 历史/近期修复明细 → `#dev-history` grep 关键词
- 架构/系统规模/数据流 → `#architecture`；编码规范/UI 视觉/操作铁律详解/PG 运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`；合并模块体检 → `docs/proposals/consolidation-module-status-and-proposal.md`；全局 7 模块 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`
