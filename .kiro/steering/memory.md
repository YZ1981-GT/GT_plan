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
- **OnlyOffice 诊断结论（2026-06-08）**：容器 JWT 全部禁用（inbox/outbox/browser=false）；**"下载失败"真因=SSRF 防护拦截私有 IP**（OnlyOffice 9.4.0 默认禁止从 192.168.x.x 下载，`host.docker.internal` 解析到 `192.168.65.254` 被拒）；修复=`local.json` 加 `request-filtering-agent.allowPrivateIPAddress=true` + `docker restart`；**"无法保存"真因=ResponseWrapperMiddleware 包装 callback 响应**（OnlyOffice 要求原始 `{"error":0}` 但被包成 `{code,message,data}` 导致 OnlyOffice 认为 callback 失败）→ `_SKIP_CONTAINS=("onlyoffice/callback",)` 跳过包装；**容器重建后需重新执行 allowPrivateIPAddress 配置**；DeliverablePreview 降级预览已加 `requestOptions` auth header
- **⚠️ codegraph MCP 配置（Cursor 2026-06-04）**：**Cursor 只读 `.cursor/mcp.json`**（非 `.kiro/settings/mcp.json`）；`codegraph install --target cursor --location local` 生成；`command:"codegraph"`（全局 npm，勿 npx 每次拉包）+ `args:["serve","--mcp","--no-watch","--path","D:/GT_plan"]` + `"type":"stdio"`；**勿用 `-p`**（仅 `serve` 子命令支持 `--path`）；Kiro 侧 `.kiro/settings/mcp.json` 已同步；改后 **重启 Cursor / Reload MCP** 才挂载 `codegraph_*` 工具
- **callers 对 Python class 引用检测偏弱**（class 无"调用"语义，查模块名常显示无 caller，需配 grep 二次确认，勿仅凭 codegraph 判孤儿）
- **✅ codegraph MCP 全工具链路实测通（2026-06-02）**：status/context/files/explore/callers 均正常返回（59540 节点/131401 边/WAL+FTS5）；explore 每 project 限 2 次调用且每次约 6 文件，超范围用 Read；分析确认 `get_authenticated_container`(core/container.py:65) 是死代码（0 引用 + docstring 自承认无法注入 user，应删，认证容器用 deps.get_current_user 路径）
- **codegraph 索引自动同步 hook 已建（2026-06-05）**：`.kiro/hooks/codegraph-index-sync`，fileEdited 触发（backend services/routers/models + frontend views/components/composables），runCommand `codegraph sync`（从 cwd 自动检测项目，**不支持 `--path` 参数**），30s 超时；确保 codegraph MCP 工具查到的符号/调用链/影响面始终最新
- **codegraph CLI 直调可用**：`codegraph status/sync/query/callers/callees/impact/context/trace/explore`（全局 npm 装，cwd=D:/GT_plan 自动检测）；CLI 比 MCP 轻量（不走 JSON-RPC），适合 hook 和批量场景
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）
- **开发工具链（dev-tooling-modernization spec，2026-06-04 落地）**：①gitleaks `.gitleaks.toml`+`.git-hooks/pre-commit`(缺 binary 优雅降级)+CI `gitleaks-action@v2` ②SQLFluff `.sqlfluff`(dialect=postgres,raw)+基线 1718 violations/47files+CI warning 级 ③uv 0.10.4 全局已装+CI 5 job `uv pip install --system`+pip fallback+`docs/dev-guide-uv.md` ④Docling 裁掉(torch 2-4GB 致命) ⑤DSPy 仅文档(`docs/dspy-feasibility-evaluation.md`)；验证脚本 `backend/scripts/check/check_gitleaks_config.py`
- **底稿模板源**：`backend/wp_templates/`（按循环 A~S 分目录），`scripts/analyze/scan_wp_templates.py` 扫描输出 `backend/data/gt_template_library.json`
- **审计报告正文模板源**：`审计报告模板正文/`（仓库根），致同 4 意见类型×4 企业类型(A 上市/B 三板金融/C 其他公众利益/D 非公众)=17 个 Word 模板 + `年度审计报告模板使用对照表.xlsx`；当前 `CompanyType` 枚举只有 listed/non_listed（待扩为 4 级）
- **🟢 审计报告正文架构决策（2026-06-08）**：采用**路径 A = Word 模板直接作为程序资产+占位符替换**（非路径 B 的 Word→JSON→再生成 Word）；理由=格式保真(致同格式要求极严)+OnlyOffice 天然兼容(所见即所得)+占位符方案成熟；实现=模板 copy 到 `backend/data/audit_report_templates/` → python-docx 替换 `{{field}}` 占位符 → `##OPT:section_id##` 标记可选段落弹窗确认 → `##NOTE:xxx##` 指引注释最终版删除 → OnlyOffice 编辑/导出；**附注和财务报表导出也同路径**（Word/Excel 模板+填数据）；模板已就位：`report_body/`(17 docx) + `financial_statements/`(4 xlsx) + `disclosure_notes/`(4 docx) + `template_manifest.json`(版本`2025-v1`)；spec=`audit-report-template-integration`(11 需求)
- **干净验证法**：start-dev uvicorn `--reload` 父子进程互拉 kill 不净 → venv 另起端口（如 9981）`python -m uvicorn ... --port 9981` 绕开 reloader；in-process ASGI httpx（`httpx.ASGITransport(app=app)`）直调端点最快
- **LLM 上下文压缩类工具不引入（2026-06-04 决策）**：Headroom/类似（SmartCrusher 压 JSON / CCR 可逆 / Kompress-base）对本项目价值低——本地 vLLM 自带 prefix caching、token 成本=GPU 时间非外部 API 计费、审计金额/科目编码精度敏感不能被通用 NLP 压缩误删；RTK 已覆盖 CLI 输出压缩 90% 价值，不再叠中间件
- **外部 agent harness 配置包不整体引入（2026-06-04，ECC 评估）**：Claude Code/Cursor/Codex 的 plugin/skill 包（如 affaan-m/ECC：63 agent + 249 skill + hook + rules）不在 Kiro 支持列表，install 脚本/hooks.json/plugin.json/marketplace 协议都依赖具体 harness，Kiro 用 `.kiro/steering` + `.kiro/specs` + 自定义 hook 体系另一套；同类问题（rule/skill/memory/spec/token 优化）已用本地方式覆盖；如需取经只能 cherry-pick 单个 markdown（如 rules/common/security.md / tdd-workflow / search-first）抄进 .kiro/steering 改中文+审计场景，**严禁 clone 整仓污染 working tree**
- **markitdown 0.1.6 已装本地（2026-06-04）**：`pip install 'markitdown[all]'` 进 backend venv（带 magika/onnxruntime/pdfplumber/mammoth/python-pptx/markdownify 全套依赖，纯本地无远端调用）；`backend/app/services/markitdown_service.py` 单例 + 延迟初始化 + 扩展名白名单(.pdf/.docx/.xlsx/.pptx/.html/.csv/.json/.epub 等共 17 种) + `convert_stream(BytesIO)` 最窄安全接口（不 fetch URI）；`backend/requirements.txt` 待补 `markitdown[all]`；知识库上传 `_extract_text_with_ocr` 已重构三级降级：MarkItDown 主→MinerU OCR(PDF扫描件)→PyPDF2/python-docx 兜底，覆盖面从原 PDF/docx 扩到全部办公格式

## 迁移与 PG schema（D6 MigrationRunner 运行时迁移，非 alembic）

- 启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞号字母序靠后者静默丢失，scan_migrations 已加同号检测抛 RuntimeError）；**当前最高 V063**（V059=deliverable_center / V060=temporary_grants / V061=knowledge_index_stale_tracking / V062=review_records_evidence_cols / V063=account_package_program_status）
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
- **✅ V063 account_package_program_status 已实测（2026-06-07）**：15 列/PK/2 索引/3 FK 与 ORM 零 drift；schema_version checksum 已修正为文件真实值；前端路由 `/projects/:id/account-packages/:packageId` 联通确认（AccountPackageView 正常渲染）
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

### git 状态（2026-06-12，HEAD `794f170c` 已 ff 拉取远程最新）
- 分支 `work/2026-05-30-wp-specs`；commit `794f170c` feat: workpaper-unified-import-export + bad-debt-nested-structure 全面实施（82 files, +15880/-181）；远程 `origin/HEAD origin/master` 落后 main 298 commit 需改默认分支
- 2026-06-02~06-10 修复明细（B-Index/编制表头/render-config/架构流程图/循环目录/手册视图/富文本编辑器等）已归档 `#dev-history`

### 真正待办
- **外部依赖**：LLM embedding 实例 / 6000 并发压测 / 钉集成 / 合并 UAT / GitHub 默认分支改 main / 走 PR 合入 / V052~V062 生产迁移
- **✅ `workpaper-content-semantic-contract` spec 全部完成+归档（2026-06-08）**：57/57 tasks；归档至 `_archive/05-business-features/`
- **✅ `workpaper-account-package-d1-d2-pilot` spec 全部完成+归档（2026-06-08）**：81/81 tasks；归档至 `_archive/05-business-features/`
- **✅ `workpaper-ai-conclusion-copilot` spec 全部完成+归档（2026-06-08）**：58/58 tasks；归档至 `_archive/05-business-features/`
- **待建 spec**：consol_disclosure_service 瘦身(1736行) / migration_runner 瘦身(1026行) / `workpaper-content-semantic-system`（底稿内容平台化，2026-06-06 提案+codegraph 分析；真空白=SheetContentType 声明式枚举替换 wp_generic_processor._detect_sheet_type 启发式 + account_package 科目工作包逻辑对象 + 字段级 requires_confirmation registry；**已有勿重建**=函证 callback 已铺 D2/F2/G7 三循环 + ai_content_log_service+ai_content_gate_rule 草稿阻断签发已闭环 + confirmation:received→useWorkpaperRefresh 已接线；试点选 D2 非 D1；硬伤=科目包程序状态须持久化不能纯前端聚合） / `deliverable-lineage-and-writeback`（出品物溯源与回填，**2026-06-09 三件套 requirements+design+tasks 全部生成完成，待实施**，现状分析存 `audit-report-template-integration/LINEAGE-全链路溯源回填-现状分析.md`）：用户要全链路双向数据流（调整分录→审定表→报表→附注→出品物 + 反向回填）。**三决策**：①仅附注 MVP(报表/报告正文列附录D未来扩展)②允许新建数据结构(deliverable_section_state 表,V067)③回填显式按钮触发(非OnlyOffice自动保存)。**80% 基础设施已存在勿重建**：LinkageFacadeService(加 deliverable source_type 分支)/StalePropagationEngine(加 DELIVERABLE: URI 前缀)/event_handlers(加 1 handler+自触发防护)/TraceEventService(复用留痕)/word_doc_utils.scan_section_blocks(回填分块)/NoteWordExporter._export_template_mode(增量刷新复用)。**真实空白=出品物层未接入**：段落锚点(confirm 写隐藏书签 sec_xxx,需 D1 POC 验证 OnlyOffice+python-docx 双方可读)+章节级 stale(新表,现 disclosure_notes.is_stale 本就是章节级行——每 note_section 单独行,但 handler UPDATE WHERE project+year 全标粒度粗暴;出品物层才真无章节状态须新表)+OnlyOffice 回填管道。**审计合规底线(需求6/Property16)=仅 text_content 文字可回填,table_data 金额严禁倒灌(走调整分录),标题忽略**。design 含 27 条正确性属性。**P0**(deliverable溯源+锚点+面板)/P1(stale感知+增量刷新)/P2(合规护栏+回填+冲突检测+留痕)。**🚨 START GATE 硬阻塞**：全部编码任务阻塞于 G1(task 0.6 模板整理)+G2(task 10.2/10.4 灰度 USE_TEMPLATE_FILL_SERVICE=true)；仅 D1 锚点 POC 不受门控。用户明确先出 spec 不开发,实施须在模板整理后。**🔴 2026-06-09 复盘发现 3 处 spec↔程序不符待修(实施前必改)**：**🔴→🟢 2026-06-09 复盘 3 处修正已全部落地三件套(requirements/design/tasks)**：①身份模型 deliverable_id→word_export_task_id 全文统一(表/API/URI/签名),章节状态绑 task 级+version_no 记录列不入唯一约束 ②is_stale 表述纠正(上游本就章节级行,新表必要性=出品物层全新维度非上游缺粒度) ③快照分层 D9(复用 DeliverableSnapshotService.tb_hash doc 级闸门+章节级 hash 细化 section_code+text_content,先比 tb_hash 整份变了才逐章算) ④新增需求 11+Property 28 终态(signed/confirmed/archived)禁回填/刷新(复用 create_version 归档锁)+前端终态只读 ⑤新表字段不绑死附注 doc_type 留报表/报告正文扩展口子。属性 27→28 条。LinkageContract.route 已验证存在✅。**子代理调用偶发 BAD_DECRYPT 传输错误,重试即可**——DeliverableService.capture_snapshot_refs + DeliverableSnapshotService 已存在,**实证=doc 级 tb_hash(整张试算表 MD5)绑 WordExportTask.source_snapshot_refs,不覆盖 text_content、不区分章节**；故**分层方案**：doc 级 tb_hash 复用作廉价闸门(判整份变没变)+ 新表只存 P2 回填真正需要的(word_export_task_id+section_code→章节文字基线 hash+可选章节 stale)；检测顺序 tb_hash 变了才逐章算 section hash。**章节级判断结论(2026-06-09)**：P0 溯源不需要章节状态(按需计算)；P1 stale 可先复用 doc 级 tb_hash；**唯 P2 文字回填+冲突检测必须章节级**(逐章 text_content 基线,tb_hash 不覆盖文字)。LinkageContract.route 字段已验证存在(linkage_contract.py:89)✅
- **✅ ledger 三 spec 全部完成+归档（2026-06-08）**：header-adapter(7组+MVP-5+CI-7) + sign-convention(7组+MVP-6+CI-7+V064) + diagnostics(8组+MVP-7+CI-9)；186 核心测试 passed；归档至 `_archive/05-business-features/`
- **🟢 spec 状态**：active=2（audit-report-template-integration implementing 179/184 剩5项人工运维 + deliverable-lineage-and-writeback completed 92/92）/ archived=137（zero-downtime-deployment+ledger-sign-convention-unify 已归档 2026-06-10）；INDEX.md 已更新
- **🟢 附注多表格 per-table export toggle 已实现（2026-06-10）**：前端 DisclosureEditor 多表格 tab 栏右侧⚙按钮→popover checkbox 勾选导出表格；数据存 `table_data._tables[N].export_enabled`(JSONB 无需迁移，默认 true)；后端 `NoteWordExporter._note_tables()` + `_render_note_content()` 两处过滤 `export_enabled=False` 跳过导出
- **🟡 无感版本迭代**：zero-downtime-deployment spec ✅ 已归档（V068）；剩余待定=生产 Docker Compose+nginx 单机滚动 vs K8s，用户决策后出 spec
- **✅ 2026-06-07~06-10 完成事项已迁入 `#dev-history`**：zero-downtime-deployment / ledger 三 spec / 导入系列修复 / deliverable-center / report-view-slimdown / 符号约定统一 / 去重加固 / audit-report-template 代码任务 / 附注打标+template 模式 / 报表模板占位 → 详见 dev-history.md "2026-06-07~06-10" 节
- **🟢 spec 状态（2026-06-12）**：active=4（audit-report-template-integration 180/184 剩 4 项运维 + deliverable-lineage-and-writeback 92/92 completed + workpaper-unified-import-export 27/27 completed + **workpaper-bad-debt-nested-structure 14/14 completed**）/ archived=137；INDEX.md 待同步
- **🔴→🟡 报表新占位代码支持（2026-06-11 实证）**：续表✅+imp✅+note_ref✅，**仅剩 `{{eq:}}` 权益变动表待矩阵存储方案**
- **🟡 附注模板 SECTION 块内部细化待做**：~600 块×4 变体，待用户确认启动
- **已知 Bug**：辽宁卫生服务序时账 debit==credit / 明细账翻页余额第 2 页起错 / 试算差额 44M（源数据符号问题）
- **外部依赖**：LLM embedding / 合并 UAT / GitHub 默认分支改 main / 钉集成
- **待建 spec**：consol_disclosure_service 瘦身(1736行) / migration_runner 瘦身(1026行) / workpaper-content-semantic-system
- **✅ workpaper-bad-debt-nested-structure 全部完成（2026-06-12，14/14 任务组）**：D2-3 坏账嵌套子表 V070；产物=bad_debt 全链路(后端108测试+前端7 vitest)+GtBadDebtSheet(层级/展折/右键/只读/GT紫)+`wp_classification_service` sheet名级路由 bad-debt-sheet+`resolve_wp_index_id` id语义兼容；**11.3 Playwright 实测通过**：`e2e/bad-debt-d2-3.spec.ts` 辽宁卫生 D2→tab「坏账准备明细表D2-3」→展折+右键增删子行+bad-debt-rows API 全2xx无404/307，1 passed/11s
- **🟡 bad-debt spec 剩余改进项（非阻塞，后续排期）**：①科目编码 1231坏账准备/6701信用减值损失硬编码在 service→多企业不通用，应走 account_chart_service 编码+名称双保险 ②12 条 PBT 全用 in-process SQLite，唯一偏索引/级联/乐观锁建议补真 PG 冒烟 ③前端"上方/下方插入子行"是近似实现(都调新增到末尾，后端无 position 排序端点)，要么补端点要么去掉菜单项 ④迁移号应实施第一步才分配(spec 生成时快照易撞号，本次 V069 被占临时改 V070/V071)
- **✅ workpaper-unified-import-export 全部实施完成（2026-06-11）**：8 Phase 27 任务组；产物=V071 迁移(wp_export_snapshot+wp_version_archive)+ORM+DTO 10 类+service 层 9 模块(MetadataCodec/serialization/export_engine/import_engine/format_validator/version_manager/conflict_detector/batch_packager/template_copier)+router 2 文件 8 端点(已注册 workpaper registry)+前端 7 Vue 组件+1 composable(useWpExportImport)；**80 测试全绿**（25 PBT max5 + 17 E2E + 9 unit + 6 vitest + 23 其他）；修 import 路径 bug（backend. 前缀→app.）+ hypothesis 策略控制字符过滤；**P0-P3 修复已落地**：①event_bus.publish(WORKPAPER_SAVED)已加 ②FormatValidator 已传 render_schema ③version_manager raw SQL→ORM ④ConflictDetector 统一集成 ⑤requirements 3.2 docx 对齐；**in-process httpx 联调通过**（export-with-metadata 200 OK，TemplateNotFoundError 回退空白 wb 生效，5272bytes valid xlsx+RFC5987中文名+snapshot_hash写入DB）；**待做**=前端7组件接入页面+import-enhanced联调
## 操作铁律（详见 `#conventions`）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册否则前端 404；FastAPI 不热加载 router（改后重启）；**路由注册顺序铁律**：含静态路径的 router（如 `/batch-template`）必须注册在同前缀通配 router（如 `/{project_id}`）之前，否则通配截获静态路径→422 UUID parse error（2026-06-10 batch-template 被 project_wizard 的 `/{project_id}` 截获踩坑）
- **http.ts extractErrorDetail 已修**：FastAPI 422 validation errors 的 `detail` 是数组（`[{msg,loc,type}]`），旧代码 `String(d)` → `[object Object]`→已修为 `.map(item => item.msg).join('；')`
- **service 只 flush 不 commit**：跨 service 编排由 router 统一 commit 保原子
- **asyncpg 事务污染**：事务 aborted 后连 SAVEPOINT 都被拒 → 根治=修最先失败的 SQL（非兜异常）；规则内 try/except 吞 SQL 异常不 rollback=反模式
- **"返回第一个→返回全部"重构必查全消费侧**：`_resolve_sheet`→`_resolve_sheets` 类重构，所有调用方（fill/keep/delete 三类消费）都要适配，尤其删除/清理逻辑必须验证"不该删的还在"（2026-06-10 sheets_to_keep 踩坑）
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL 必加 SQLite dialect 检测
- **历史档案不回填修改**：dev-history / spec-tasks 是 append-only
- **PowerShell**：写中文/emoji 用 fsWrite（禁 `-replace`/`Set-Content` 处理中文）；长 commit msg 用 `git commit --% -m "..."`；读中文输出先 `chcp 65001 + [Console]::OutputEncoding=UTF8`
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；`http.get/post`（utils/http）返完整响应体需 `.data`
- **枚举成员引用前实证**：`python -c "getattr(Enum,'X','MISSING')"` 核对大小写（小写 draft/approved）
- **`dict.get(k, default)` 陷阱**：key 存在但值为 None 时返回 None 不返回 default（Pydantic 可选字段未填即 None）→ NOT NULL 列插入崩。写库前必用 `(data.get(k) or fallback)` 显式兜底，勿依赖 `.get(k, default)`（已咬过：procedure custom add 的 procedure_code=None 致 500）
- **merge 跨阶段签名变更必 grep 调用方**（sync↔async / 删公开方法）
- **🔴 后台作业类 bug 必先查 DB 真实状态再读代码（2026-06-08 复盘血泪）**：导入反复 IMPORT_FAILED 我分四轮才逼近根因，前三轮全在读代码+片段日志做推断（修 tenant_id 漏 INSERT 路径/SSE 误报/终态幂等都是外围补丁），直到查 `ImportJob` 表发现"连续 8 个 job 全 timed_out 卡在后置阶段、心跳停在开始后 2-3 分钟"才一眼定位根因（后置长阶段无心跳）。教训：①后台作业/异步任务出错，第一步就 query 状态表(status/phase/heartbeat/error_message 分布)看现场，别用读代码代替复现；②中间层补丁（幂等保护/防御性跳过）≠ 根治，别用"修复完整"措辞过度自信；③修一处反模式立刻 grep 全仓同类（tenant_id 第一轮就该查全部写入路径）；④"逻辑推断+单测通过"≠"端到端实测"，大改动后须真实跑通 staged→completed 才算闭环
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；FastAPI 无尾斜杠路由 307 重定向绝对 URL 会跨域→前端路径匹配后端尾斜杠；**禁止 `window.open` 下载认证资源**（新标签页不携带 sessionStorage token→401），必须用 `downloadFile`（axios blob + Bearer header）
- **UI 必用 GT 紫令牌**（`styles/gt-tokens.css`）：核心紫 `--gt-color-primary:#4b2d77` / 浅紫底 `--gt-color-primary-bg:#f4f0fa` / 紫边框 `--gt-color-border-purple` / 浅紫边框 `--gt-color-border-purple-light:#d8b8ee`；**禁用 Element 默认蓝 `--el-color-primary`/#409eff 作 fallback**；global.css 已映射 `--el-color-primary→GT紫`，但 `el-tag type="primary"` 仍渲染默认蓝（light-9 变量未全量重映）→ 需组件内 `:deep(.el-tag--primary)` scoped 覆盖三色，勿动全局级联
- **hypothesis PBT 调速**：max_examples 5（用户明确要求，禁默认 100）；用户可临时要求降到 3 进一步提速（sign-convention spec 的 converter/direction_resolver PBT 已降 5→3，24 测试 0.92s 全绿）
- **TimestampMixin 列必须同步到手写 DDL**：ORM 继承 `TimestampMixin` 自动加 `created_at`/`updated_at` Mapped 列，但手写 V*.sql CREATE TABLE 不会自动加→漏写就 schema drift critical。铁律：凡 ORM 用 TimestampMixin 的表，DDL 必须显式写 `created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`（V057 editing_locks 踩过此坑 2026-06-06）
- **useExcelIO.exportTemplate existingData 必须等宽**：`existingData: any[][]` 所有行必须 pad 到相同列数（maxCols），否则 `xlsx-js-style` 写 cell 引用越界致 xlsx 损坏打不开；多子表导出用 `applyStyles: false`（style template 迭代 columns×rows 在非均匀数据上越界）
- **底稿生成跳过 wizard 前置（2026-06-07）**：`wp_template.py` `generate_project_workpapers` 改为请求体带 `template_set_id` 时跳过 `PrerequisiteChecker`（不强制要求 wizard_state.template_set 已配）；前端 `WorkpaperList.vue` 新增"生成底稿"按钮→弹窗 select 选模板集→选完直接调 API 生成；**BUILTIN_TEMPLATE_SETS 改为动态读取 `wp_account_mapping.json` 206 条致同编码**（标准年审/上市/IPO=全量206，精简版=核心循环一级无dash，附注=仅A循环）；seed 幂等逻辑改为"已存在但 codes 变化则更新"覆盖旧占位；前端点生成前先自动调 seed 确保编码最新；`workpaper_template_analysis.json`(349模板/2602sheet)证实 206 wp_code 全有效（占位 sheet 在渲染层跳过不影响生成）
- **底稿生成性能重写（2026-06-07）**：`template_engine.py` `generate_project_workpapers` 从逐个查 DB+复制文件（206 次 flush+文件 IO=30s+）改为纯元数据批量 INSERT（批量预加载 WpTemplate map+幂等跳过已存在 wp_code+循环内只 add 不 flush+结束后 2 次批量 flush=<2s）；**不再复制模板文件到项目目录**（file_path 直接引用模板库原始路径或空串兜底，打开底稿时按需加载）；砍掉 fill_workpaper_header/多文件底稿 rglob 等非关键路径；**修复 2 个 500**：①`max(uuid)` PG 不支持→改 `max(created_at)` + wp_template 表空时跳过 ②`file_path NOT NULL` 约束→空串兜底；seed 只保留"标准年审"1 个内置模板集（206 条），其余 5 个占位删除；前端弹窗过滤只显示标准年审+用户自建；**in-process 实测 206 份生成成功**
- **🟢 去重功能审计加固完成（2026-06-08）**：诊断确认真重复在序时账（active 内 tb_ledger 1751 行 + tb_aux_ledger 71 行整行字节级完全相同，余额表 812 行全 distinct 无重复——截图"重复"是清理前 superseded+active 双 dataset 都显示的显示层现象）。**后端** `ledger_data_service.dedup_ledger_data`：窗口函数 ROW_NUMBER() PARTITION BY 全部业务列（排除 id/created_at/updated_at/deleted_at/import_batch_id，raw_extra 用 ::text 比较）保留最小 id，只作用 active dataset。3 审计底线已加固：①**默认软删**（is_deleted=true+deleted_at，复用回收站可恢复，保留 hard_delete 选项，软删 CTE 加 is_deleted=false 过滤）②**写 app_audit_log**（audit_logger.log_action action=ledger_dedup 记录 year/mode/各表删除数/id样例≤50/可恢复标志）③**回归测试** test_ledger_dedup.py（3 passed，PG 真库验证软删 visible=3+soft_deleted=2）。**端点** `POST /ledger-data/dedup`（manager+，传 user_id+ip，dry_run 预览）。**前端** LedgerPenetration.vue 工具栏红色"数据去重"按钮（dry_run 预览→确认→执行→刷新）。剩余未做（评估后建议不改）：TOCTOU 用返回真实删除数兜底 / raw_extra::text 键序漏删偏保守安全。**根因仍是流式写入路径无去重，本功能是入库后补救**
- **✅ 符号约定统一 spec 全部完成（2026-06-08）**：`ledger-sign-convention-unify` 8 主任务+22 子任务全部 done。全量回归 215 passed / 0 failed / 0 xfailed。核心改动：converter v2 自然正数入库→trial_balance 去二次翻转（3 处旧约定取反移除）→recalc_adjustments 按 direction_resolver 归一→data_quality/consol/cfs 确认目标态+容差统一→公式层确认纯取列无翻转（negate 存量=0）→迁移脚本 migrate_sign_convention_v2.py（dry-run/幂等/快照回退/审计留痕/negate 防御扫描）→sign_convention_guard 过渡期 v1 检测→Playwright E2E 脚本（需 dev server 手动跑）。附带修复 4 预存 bug：①CfsAdjustment.soft_delete()→is_deleted=True ②test_indirect_method 补 IS-019 seed ③account-dropdown 断言修正 ④guard ASGI Windows 崩→service 层直测
- **🔴 复盘二次修复：ADJ 净额 3 处旁路口径未跟上 recalc_adjustments 归一（2026-06-08）**：Task 3.3 把 `trial_balance.aje_adjustment` 改为按 direction_resolver 方向归一（贷方类取反）后，下游 3 处**独立重算** ADJ 净额的旁路仍用原始 `SUM(debit-credit)`（借正贷负），对贷方类（负债/权益/收入）反号——①`wp_cross_check_service._get_adj_value`（`=ADJ()` 公式+XR-07 勾稽）②`data_validation_engine._validate_adjustment_report`（原始净额 vs 归一 tb_aje 比较→每个贷方类调整误报不一致）③`prefill_engine._resolve_adj_formula`（底稿 `=ADJ()` 预填）。全部改为同 direction_resolver 归一（cross_check/prefill 查 MAX(account_name) 传入；data_validation 用 SQL CASE WHEN account_category IN liability/equity/revenue THEN 取反）。+1 测试 test_adj_credit_account_normalized_positive。**根因=Task 1.5 下游清单只 grep 读取派关键词(audited_amount/unadjusted_amount)，漏了重算派(`SUM(debit-credit)`)**
- **🔴 铁律：核心计算口径变更必查"重算旁路"（2026-06-08 复盘）**：当某指标的口径变更（如方向归一/符号约定/单位换算），不能只改写入点，必须 grep/codegraph 找出所有"自己重算同一指标"的旁路。某 DB 列（如 trial_balance.aje_adjustment）常有多个独立生产者/比较者（写入 recalc + 校验 cross_check/data_validation + 取数 prefill）。下游消费点清单必须分两类 grep：①**读取派** audited_amount/unadjusted_amount/closing_balance ②**重算派** `SUM(debit-credit)`/`debit_amount - credit_amount`（最危险，不读现成列而自算，最易与口径变更脱节）。**补充铁律：判定某处"无关"前必须 readCode 确认它消费哪个字段，不能凭公式形态印象判断**——validator.py L3 `closing = opening + debit - credit` 形态像凭证级校验，实际消费 v2 改过的 closing_balance，第一轮口头判"无关"是错的
- **🔴 第三轮复盘修复：validator L3 BALANCE_LEDGER_MISMATCH 是 Task 2 连带遗漏（2026-06-08）**：v2 把 tb_balance.closing/opening_balance 改为自然正数后，L3 校验恒等式 `closing=opening+SUM(debit)-SUM(credit)` 对贷方类（负债/权益/收入）失效——发生额仍借正贷负，平衡的贷方类科目被全部误报 blocking。修复=按 closing_direction+sign_convention_version 判断：v2 贷方类用 `credit-debit`，借方类和 v1 旧数据保持 `debit-credit`。+4 回归测试 test_l3_balance_ledger_v2_sign.py。`import_intelligence.py` DQ-04（凭证级借贷合计平衡）确认无关不改。顺带修 3 个 stale 测试：sign_convention_api/migration 断言旧默认 v1→v2（Task 1 翻默认时漏改）、test_huge_ledger_smoke 用 `TableType.LEDGER`（TableType 是 Literal 非 Enum 本就跑不通）→ 字符串 `"ledger"`。全量 683 passed/22 skipped
- **🟡 account_package_registry 兼容缺口**：注册表 D2 工作包依赖 wp_code D2-5/D2-6，但 `wp_account_mapping.json` 206 条里只有 D2/D2-2/D2-3/D2-4 无 D2-5/D2-6 → 工作包摘要会标 `missing_sources` 不阻塞使用；后续 `ledger-import-smart-header-recognition` spec 需求 11（seed 全覆盖）一并补全

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，无需裁剪（dev-history 是 append-only 审计轨迹）
- 技术事实/端点速查/PG schema/spec 历史/近期修复明细 → `#dev-history` grep 关键词
- 架构/系统规模/数据流 → `#architecture`；编码规范/UI 视觉/操作铁律详解/PG 运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`；合并模块体检 → `docs/proposals/consolidation-module-status-and-proposal.md`；全局 7 模块 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`
