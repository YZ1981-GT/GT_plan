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
- **🔴 codegraph 优先于 grep（铁律）**：搜符号/查调用链/看影响面第一选择永远是 codegraph（已索引 6万+节点/13万边）——MCP `codegraph_context`(任务上下文)/`codegraph_search`(符号)/`codegraph_callers`+`callees`(调用链)/`codegraph_impact`(影响面)/`codegraph_trace`(A→B)；CLI `codegraph query/callers/callees/impact/context`(cwd=D:/GT_plan 自动检测)。**grep 仅用于**：非符号文本(中文串/注释/配置值)、Python class 引用二次确认、跨文件字面量统计
- **触类旁通**：发现一处反模式立即全仓找同类一次修完（codegraph 优先）
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端；设计阶段必做"现状确认"（codegraph 优先，外部依赖标降级方案+切换点）
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；硬编码不接 i18n + ESLint 卡点
- **报表金额统一"元"为默认单位**（不默认万元）；`line-composition` 端点查 `trial_balance.audited_amount`（审定数，与报表同源）
- **中文场景全链路不能崩**：中文文件名下载（Content-Disposition 必 RFC5987）、中文项目名/客户名/底稿名导出均须实测过
- 功能收敛停加新功能，核心 6-8 页做到极致，空壳标 developing；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- **文档/文件夹级 LLM 对话是最实用核心功能**（spec `doc-level-ai-chat`）：自动注入当前文档+关联知识库作 RAG 上下文
- git 单 commit；**push 前必先 fetch 同步**（stash→fetch --prune→评估→pop→commit/push）；**协作走 PR 不直推 main**；默认分支 `main`
- 提建议前先验证不引用过时记录；完整复盘诚实暴露问题；PDCA：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发 6000 人；底稿编码致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A 报表/调整 B 控制了解 C 控制测试 D 销售收入 E 货币资金 F 采购存货 G 投资 H 固定资产 I 无形资产 J 职工薪酬 K 管理 L 筹资 M 股东权益 N 税费 S 专项
- **循环→审计阶段映射**：承接与计划=Q+B（B 含 B1A 承接/B1B 保持/B2 前任沟通/B3 独立性 + B10~B60 计划了解）/ 控制测试=C / 实质性程序=D~N+S+L+M / 完成与报告=A；前端 4 阶段流程图

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`；测试用户 admin/admin123
- **JWT 有效期**：access_token 1440 分钟（24h）/ refresh_token 30 天（开发环境，config.py 已改）
- **rtk 0.42.1 已装**（`C:\Users\杨志\.local\bin\rtk.exe`，已加 PATH）：CLI token 压缩代理，Windows 原生无 hook（需手动 `rtk` 前缀）；规则见 `.kiro/steering/rtk-proxy.md`（git/pytest/vitest/playwright/eslint/tsc/docker 加前缀，管道/重定向/fetch/stash 除外）
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`（勿混）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)/`audit-pgbouncer`(6432)；health `/api/health`
- **🔴 host→Docker 连接全 100% 失败诊断法（2026-06-12 踩坑）**：症状=asyncpg/SQLAlchemy 报 `connection was closed in the middle of operation` / `WinError 10053` / `unexpected connection_lost`，启动时 migration+schema_drift+多 worker 同秒全炸。**根因多为 Docker Desktop vpnkit/WSL2 端口转发代理卡死，非代码 bug**。隔离法：①容器内 `docker exec psql` 正常→DB 本身没问题 ②裸 TCP `socket.create_connection(localhost:5432)` 能连但 ③应用层协议握手被中止 ④**关键：测 redis `PING` 也返空字节→证明是转发层而非 PG 专属**。修复=`docker restart audit-postgres audit-redis` 重建端口绑定（亲测 8/8 恢复），重启 Docker 层非改代码
- **DB_DISABLE_SSL=True（默认，config.py）**：无 TLS 部署显式禁 asyncpg SSL 协商（database.py 直连+pgbouncer 两分支 + migration_runner engine 均加 `connect_args={"ssl":False}`），消除 Windows 下 SSL 握手失败面；生产启 TLS 置 False
- **🟡 连接池上限错配隐患**：`DB_POOL_SIZE=50 + DB_MAX_OVERFLOW=100 = 最多 150` 连接，但 Docker PG `max_connections=100` → 高并发后端连接池超 PG 上限会被拒（当前仅用 15 未触发）；需提 PG max_connections 或降池上限到 100 内
- **依赖**：schemathesis 3.39.16（强制 starlette 0.52.1 降级）/ opentelemetry 1.42.1 / instructor 1.15.1 / bm25s 0.3.9 / python_calamine / markitdown[all] 0.1.6；`_zh_tokenize.py` 中文 bigram 分词（无 jieba）
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）；views/components/composables 在其 `src/`
- **MCP 7 个**：codegraph(10)+playwright(23) 在线；context7(2 库文档)/fetch(1)/thinking(1 sequentialthinking)/memory(9，与 memory.md 文件体系两套勿混)/js-reverse(21 前端断点调试) 详见 `#architecture`
  - **工具选用**：理解代码→`codegraph_context`；查库用法→`context7`；前端 E2E→`playwright browser_snapshot`；前端 runtime bug→`js-reverse set_breakpoint_on_text`+`step`；复杂推演→`thinking`
- **codegraph v0.9.8**（`npm i -g @colbymchenry/codegraph`，CLI 在 `~/AppData/Roaming/npm`）：项目已索引（cwd=D:/GT_plan 自动检测）；自动同步 hook `.kiro/hooks/codegraph-index-sync`（fileEdited 触发 `codegraph sync`，不支持 `--path`）；Cursor 配置在 `.cursor/mcp.json`（非 .kiro），`args:["serve","--mcp","--no-watch","--path","D:/GT_plan"]`
- **callers 对 Python class 引用检测偏弱**（class 无"调用"语义，需配 grep 二次确认，勿仅凭 codegraph 判孤儿）
- **OnlyOffice（9.4.0）**：`enabled` 判定查 `ONLYOFFICE_URL`；JWT 可选（无 secret 时 callback 直通，生产须配 `ONLYOFFICE_JWT_SECRET`）；**前端集成=JS API** `new DocsAPI.DocEditor(containerId, config)`（非 iframe src）；`document.url` 用 signed-download 免 auth 端点（HMAC 10min，OnlyOffice 不带 Bearer）；`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`
  - **诊断结论（2026-06-08）**：①"下载失败"=SSRF 拦私有 IP（`host.docker.internal`→192.168.65.254 被拒）→ `local.json` 加 `request-filtering-agent.allowPrivateIPAddress=true`+`docker restart`（容器重建需重做）②"无法保存"=ResponseWrapperMiddleware 包装 callback（OnlyOffice 要原始 `{"error":0}`）→ `_SKIP_CONTAINS=("onlyoffice/callback",)` 跳过
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）
- **开发工具链（dev-tooling-modernization）**：gitleaks `.gitleaks.toml`+pre-commit / SQLFluff `.sqlfluff`(postgres,基线 1718) / uv 0.10.4（CI 5 job）/ Docling 裁掉(torch 太重) / DSPy 仅文档
- **底稿模板源**：`backend/wp_templates/`（按循环 A~S 分目录），`scripts/analyze/scan_wp_templates.py` 扫描输出 `backend/data/gt_template_library.json`(331 条，唯一权威源)
- **审计报告正文模板源**：`审计报告模板正文/`（仓库根），4 意见类型×4 企业类型=17 Word 模板；**架构决策=路径 A**（Word 模板作程序资产+占位符替换，非 Word→JSON→再生成）：`{{field}}` 替换 + `##OPT:id##` 可选段弹窗 + `##NOTE:xxx##` 终版删；模板就位 `backend/data/audit_report_templates/`（report_body 17 docx + financial_statements 4 xlsx + disclosure_notes 4 docx，`template_manifest.json` 版本 2025-v1）；spec=`audit-report-template-integration`
- **干净验证法**：uvicorn `--reload` 父子进程 kill 不净 → venv 另起端口（9981）绕 reloader；**in-process ASGI httpx**（`httpx.ASGITransport(app=app)`）直调端点最快（跑磁盘当前代码，无 stale server 风险）
- **markitdown 单例**：`backend/app/services/markitdown_service.py`（延迟初始化+扩展名白名单 17 种+`convert_stream(BytesIO)` 最窄接口）；知识库 `_extract_text_with_ocr` 三级降级 MarkItDown→MinerU OCR→PyPDF2/python-docx
- **不引入**：LLM 上下文压缩中间件（本地 vLLM 自带 prefix caching+审计精度敏感，RTK 已覆盖 CLI 90% 价值）；外部 agent harness 配置包（ECC 等，依赖具体 harness，Kiro 用 .kiro/steering+specs+hook 另一套；如取经只 cherry-pick 单 markdown 改中文，严禁 clone 整仓）

## 迁移与 PG schema（D6 MigrationRunner 运行时迁移，非 alembic）

- 启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞号字母序靠后者静默丢失，scan_migrations 已加同号检测抛 RuntimeError）；**当前最高 V071**（V070=bad-debt / V071=wp_export_import 两表）
- **⚠️ `CREATE TABLE IF NOT EXISTS audit_log` 是 no-op**：该名被 Metabase 共库占用（真实 schema 无 action 列）→ 应用审计写独立表 `app_audit_log`；建表前先 `to_regclass`+`information_schema.columns` 查真实 schema
- **本地 PG schema 漂移已修**（critical=0）：drift detector pkgutil walk import 全 model + 过滤 Metabase 共库污染
- **🔴 projects 表无 year/template_version_id 列**：年度用 `EXTRACT(YEAR FROM audit_period_end)::int`；materiality 年度列=`overall_materiality`；人员姓名在 `staff_members.name`（users 无 display_name），JOIN 用 `project_assignments.staff_id`；database.py 已加 `async_engine = engine` 别名
- **🔴 真实列速查**：trial_balance 金额=unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount/opening_balance（无 closing_balance，科目列=standard_account_code）；financial_report=row_code/row_name/current_period_amount/source_accounts（无 amount/line_code）；adjustments=adjustment_no/adjustment_type/account_code/review_status（无 status/entry_type/summary）；adjustment_entries=standard_account_code；working_paper 无 year/wp_code（wp_code 在 wp_index，JOIN wp_index_id）；issue_tickets 负责人=owner_id 不软删；CellAnnotation 作者=author_id
- **🔴 wp_template_registry 表实际不存在**：gt_template_library.json 是唯一权威源；scan 脚本末尾 sync_registry 因表不存在静默跳过（已加白名单不报 drift）
- **真实 PG 数据**：5 项目多 standalone，**0 个 consolidated 项目**（合并 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全（序时账/明细账数据干净，82384 行借贷单边）但 audit_period_end 为 NULL
- **契约测试守护**（CI 根治整类 schema 漂移 500）：`test_raw_sql_schema_contract.py`(表级)+`test_raw_sql_column_contract.py`(列级 pg_only sqlglot)；新增裸 SQL 引用不存在表/列即 CI 红；存量债务 `_KNOWN_PHANTOM_DEBT`/`_COLUMN_ALLOWLIST`（剩 wp_template_registry）
- **🟡 account_package_registry 兼容缺口**：D2 工作包依赖 wp_code D2-5/D2-6，但 `wp_account_mapping.json` 206 条只有 D2/D2-2/D2-3/D2-4 → 工作包摘要标 `missing_sources` 不阻塞；后续 `ledger-import-smart-header-recognition` 需求 11 补全

## 任务状态

### LLM（本地 vLLM 已跑通）
- vLLM `localhost:8100` 模型 `Kbenkhaled/Qwen3.5-27B-NVFP4`；`.env` `WP_AI_SERVICE_ENABLED=True`（默认 False）；本机既是 vLLM GPU 节点又是后端机（`LLM_BASE_URL=localhost:8100` 天然可用，9980 对外/8100 不对外）
- **两套 LLM 客户端**：①`llm_client.chat_completion()`（httpx+熔断器，多数 wp_llm_prompts/role_ai/pm）②`AIService(db).chat_completion()`（OCR/knowledge/contract/wp_fill，需真实 DB 会话查 active model）；vLLM 拒多条 system 消息（已加 `_merge_system_messages()`）
- **🔴 embedding 404**：vLLM 未起 embed task → RAG 向量召回降级 ilike（semantic_search 不崩，build_index 会抛错）；恢复需另起 vLLM embed 实例
- **🟢 知识库收口完成**：旧 `KnowledgeService` + 孤儿 `AIChatService` 已删；doc_ai_chat 内存历史→DB 持久化（`doc_chat_persistence.py` 复用 `ai_chat_session`/`ai_chat_message` 表，`context_summary` 存 `{doc_type}:{doc_id}:{user_id}` 定位键，零新增列）；**铁律：原生 fetch 调后端必手动解 `{code,message,data}` 信封**（ResponseWrapperMiddleware 包装所有 2xx JSON）

### 合并模块（4 Phase 代码+测试完成，归档 `_archive/09-consolidation-phases/`）
- **合并核心模型**：合并数 = 各子企业个别数据汇总 + 差额表（专填调整+抵销分录的虚拟列）；代码 `consol_amount = individual_sum + consol_adjustment + consol_elimination`
- 4 Phase 全 ✅ 代码+测试（147+ passed）+ 16 ADR + 24 service + 全链路集成测试 + seed；**统一卡点 = PG 0 个 consolidated 项目**（真实 UAT 全 data-blocked）+ Phase2/3 Playwright 待环境

### 全局 7 模块改进（7 spec 全 ✅ 实施完成）
- A formula-engine-unification / B retrieval-kernel-unification / C doc-level-ai-chat / D report-config-baseline / E wp-ai-review-ux-fix / F global-modules-cleanup / G global-modules-p2-polish；残留仅 Playwright E2E 待环境
- 治理裁定：公式求值单内核(formula_engine)、审计只写哈希链、向量存储选 pgvector；详细 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`

### git 状态（2026-06-12）
- 分支 `work/2026-05-30-wp-specs`，最高迁移 **V071**；HEAD 已同步远程
- **铁律**：push 前必 fetch（stash→ff→pop）；PowerShell 下 git push/fetch 把进度写 stderr 报 exit 1 但实为成功，看 `xxx..yyy -> branch` 确认
- **🔴 远程默认分支隐患**：`origin/HEAD→origin/master` 但 master 落后 main 298 commit（活跃主干是 main）→ 需 GitHub Settings 改默认分支（Agent 无法改远程设置）
- 远程 `origin = https://github.com/YZ1981-GT/GT_plan.git`（HTTPS）；gh CLI 已装(2.89.0)未登录（需用户本人浏览器授权）→ 建 PR 走网页 compare
- 文档类（memory/INDEX/复盘）冲突取并集，走 PR 让 GitHub 先暴露冲突，不本地直推 main
- 已完成修复明细（B-Index 目录/架构图、sheet 级索引号、试算表借贷方向、明细账月小计、2026-06-07 三处回归等）→ `#dev-history`

### 真正待办（2026-06-12，所有代码实施任务清零）
- **🟢 active spec=1**：audit-report-template-integration 181/184，剩 3 项运维（17.3 灰度 flip + 17.4 旧路径下线 + 人工验收）；archived=140；待建 spec=无
- **外部依赖**：LLM embedding 实例 / 合并 UAT / GitHub 默认分支改 main / 走 PR 合入 / 钉集成
- **后续按需**：附注 96 个 OPT 章节条件化标注（等灰度反馈，611 块 99.5% 已有块级占位符，TEXT 整块填充够用）
- **结构优化候选（2026-06-12 codegraph 体检，非任务待决策）**：①编辑锁 v1/v2 双实现并存（`editing_lock_service`+`WorkpaperEditingLock`/`editing_lock`router vs `editing_lock_service_v2`+`EditingLock`/`editing_locks`router，两 router 均在 collaboration.py 注册，v1 仅自身 router+测试引用）→ 收口到 v2 下线 v1（最干净）②`check_file_size.py` 报 19 文件超红线，最重 `report_engine`1996(+60%)/`smart_import_engine`2787/`custom_query`router2162(LibreOffice重算+预览本应下沉 service)/前端 TrialBalance2931/DisclosureEditor2126(超hard cap)③AI 服务 4 入口(AIService/UnifiedAIService/WpAIService/NoteAIAssistantService)边界未文档化；`ai_plugin_service` 8 个 Executor 全 stub 应标 developing
- **✅ 近期归档**：workpaper-bad-debt（V070+108后端+7前端 vitest）/ workpaper-unified-import-export（V071+80 tests+全链路联调+前端接入+Playwright E2E）/ 符号约定统一（V064+215 passed）/ deliverable-lineage-and-writeback（92/92）

## 操作铁律（详见 `#conventions`）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿；TimestampMixin 表的手写 DDL 必显式写 `created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`（V057 踩坑）
- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册否则前端 404；FastAPI 不热加载 router（改后重启）；**注册顺序**：含静态路径的 router（`/batch-template`）必在同前缀通配 router（`/{project_id}`）之前，否则通配截获→422 UUID parse error
- **service 只 flush 不 commit**：跨 service 编排由 router 统一 commit 保原子
- **asyncpg 事务污染**：事务 aborted 后连 SAVEPOINT 都被拒 → 根治=修最先失败的 SQL（规则内 try/except 吞 SQL 异常不 rollback=反模式）
- **"返回第一个→返回全部"重构必查全消费侧**：所有调用方（fill/keep/delete）都要适配，尤其删除逻辑必须验证"不该删的还在"
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL 必加 SQLite dialect 检测
- **历史档案不回填修改**：dev-history / spec-tasks 是 append-only
- **PowerShell**：写中文/emoji 用 fsWrite（禁 `-replace`/`Set-Content` 处理中文）；长 commit msg 用 `git commit --% -m "..."`；读中文输出先 `chcp 65001 + [Console]::OutputEncoding=UTF8`；含 regex 特殊字符的超长行用按行号切片删除（勿 strReplace）
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；`http.get/post`（utils/http）返完整响应体需 `.data`；http.ts extractErrorDetail 已修（422 detail 是数组 `.map(i=>i.msg).join('；')`）
- **🔴 后端端点返回形态不统一陷阱**：`get_trial_balance` 正常返纯 list，但过渡期(sign_convention has_legacy)返 `{data:[...], warning:..., sign_convention_ready:false}`→经 ResponseWrapperMiddleware 后信封 `data` 是对象而非数组→前端 `rows.value.map` 崩(`rows.value.map is not a function`)；已修：`getTrialBalance` 检测 `data.data` 嵌套提取+`Array.isArray` 兜底。**教训：端点双态返回（纯 list vs 包装对象）必须在前端 API 函数层统一归一化，不可裸传给 ref 赋值**
- **枚举成员引用前实证**：`python -c "getattr(Enum,'X','MISSING')"` 核对大小写（小写 draft/approved）
- **`dict.get(k, default)` 陷阱**：key 存在但值为 None 时返 None 不返 default（Pydantic 可选字段未填即 None）→ NOT NULL 列插入崩；写库前用 `(data.get(k) or fallback)` 显式兜底
- **merge 跨阶段签名变更必 grep 调用方**（sync↔async / 删公开方法）
- **🔴 event_bus 两条发布路径勿混**：①`event_bus.publish(payload: EventPayload)`/`publish_immediate` 单个 EventPayload 位置参数，走 debounce+_handlers+SSE（联动主链用）②`event_bus.broadcast_raw(event_type: str, extra: dict)` 同步、纯 SSE 推送、不触发 _handlers（轻量通知用）。**禁止传裸 dict 或关键字参数给 publish()**（`_build_dedup_key` 访问 `.event_type` 会抛异常，常被 `try/except:pass` 静默吞掉→联动断裂）。2026-06-12 已修 3 处：`deliverable_writeback._emit_note_saved`（误用 `publish(event_type=,payload=)`→回写后其他出品物章节不标 stale，回写闭环断裂；测试 mock 把错误签名编码进去才漏抓）+ `annotations`×2/`review_conversation` 裸 dict→改 broadcast_raw。**复盘再修第 4 处(最严重)**：`working_paper.save_univer_data` 第 7 步(Univer 保存底稿核心入口)裸 dict + `asyncio.create_task`+`try/except:pass` 双重静默→`WORKPAPER_SAVED` 从未分发(一致性比对/B51高风险/底稿域地址失效/prefill stale 全失联)；改真 EventPayload + 从 `Project.audit_period_end` 推导 year(year-dependent handler 如 B514/B515/H-lease/I-RD 缺 year 静默跳过)+失败 warning。至此全仓 publish 裸 dict 残留=0(version_manager/wopi 的 create_task publish 已确认是真 EventPayload)
- **🔴 后台作业类 bug 必先查 DB 真实状态再读代码**：第一步 query 状态表(status/phase/heartbeat/error_message 分布)看现场，别用读代码代替复现；中间层补丁（幂等保护/防御性跳过）≠ 根治；"逻辑推断+单测通过"≠"端到端实测"（须真实跑通终态才算闭环）
- **🔴 联动失效域审计（2026-06-12 修 3 类）**：①公式管理—`FormulaEngine` 的 `formula:*` Redis 缓存是死代码(无写入点)，真缓存=`FormulaReverseIndex` 单例(`build_from_report_config` 直查 DB)；`FORMULA_CONFIG_CHANGED`/`PREFILL_MAPPING_CHANGED` 已补 `invalidate_reverse_index()`(否则 /formula-usage、/cell-detail 引用面板陈旧到进程重启)+漏标(on_change affected=0 非降级)记 degraded ②高级查询 `custom_query`—`_query_trial_balance` 误查 account_code/closing_balance/debit_amount/credit_amount(全不存在)→改 standard_account_code/unadjusted_amount/aje_adjustment/audited_amount；`_query_adjustments` entry_number→adjustment_no、status→review_status(裸 SQL 列漂移用 `test_raw_sql_column_contract` 守) ③地址坐标库 `address_registry` 5 域(tb/report/note/wp/aux)—补 `NOTE_SECTION_SAVED→note 域`/`WORKPAPER_SAVED→wp 域`/`LEDGER_DATASET_ROLLED_BACK→全量`(此前 note/wp 域仅全量导入才刷新→穿透跳旧坐标)
- **🟢 既有缺口已修（2026-06-12）**：①`word_export_tasks` 幽灵表→真名 `word_export_task`(单数，ORM `WordExportTask.__tablename__`)，3 处裸 SQL 终态检查误写复数已修正(deliverable_writeback `_check_terminal_status`/deliverable_refresh `_check_terminal`/deliverable_lineage 路由)，`test_raw_sql_schema_contract` 转绿 ②query_builder 安全契约违反—`users` 表被误加进 `TABLE_WHITELIST`(为 项目→经理 join)破坏 3 测试(schema 暴露/preview 返 200/join 错误码)，已移除 users 白名单项+清掉 JOIN_WHITELIST 全部 users 引用(projects→users/disclosure_notes→users/staff_members↔users)，安全契约(不暴露 user/role/auth)优先于 join 便利，36 测试全绿 ③`deliverable_refresh_service.refresh_section` 第5步调不存在的 `DeliverableService.store_version_file`→运行时 AttributeError(单章节刷新必 500)，正确落盘 API=`render_and_store`(一次建版本+写盘+绑哈希)，已改；`refresh_all_stale_sections` 透传修复(遗留设计点：每章节传同一原始 docx 各建版本，多章节刷新后者可能覆盖前者编辑，待优化)
- **🔴 测试掩盖运行时 bug 反模式（同源 4 例铁律）**：`deliverable_writeback._emit_note_saved`(mock 把错误签名 `publish(event_type=,payload=)` 编进去)/univer-save(`try/except:pass` 吞)/`refresh_section`(mock 不存在的 `store_version_file`+e2e `try/except (AttributeError):pass` 显式吞)——**mock 一个不存在的方法/错误签名 = 把 bug 编码进测试**，测试永绿但生产必崩。改测试铁律：①mock 必须 mock 真实存在的方法(用 `assert_awaited_once` 验真调用)②禁止 `try/except: pass` 包住被测调用③service 间调用优先 `inspect.signature`/源码静态检查守护契约
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；FastAPI 无尾斜杠路由 307 重定向绝对 URL 会跨域→前端路径匹配后端尾斜杠；**禁止 `window.open` 下载认证资源**（新标签页不带 token→401），必用 `downloadFile`（axios blob + Bearer header）
- **UI 必用 GT 紫令牌**（`styles/gt-tokens.css`）：核心紫 `#4b2d77` / 浅紫底 `#f4f0fa` / 浅紫边框 `#d8b8ee`；**禁用 Element 默认蓝 `#409eff` 作 fallback**；`el-tag type="primary"` 仍渲默认蓝需组件内 `:deep(.el-tag--primary)` scoped 覆盖
- **hypothesis PBT 调速**：max_examples 5（用户明确要求，禁默认 100），可临时降 3
- **useExcelIO.exportTemplate existingData 必须等宽**：所有行 pad 到相同列数（maxCols），否则 `xlsx-js-style` 写 cell 越界致 xlsx 损坏；多子表导出用 `applyStyles: false`
- **🔴 口径变更必查"重算旁路"**：写入点+校验+取数全部 grep 同步；分读取派(`audited_amount`)和重算派(`SUM(debit-credit)`)两类
- **底稿生成**：`generate_project_workpapers` 纯元数据批量 INSERT（不复制模板文件，file_path 引用模板库原始路径或空串兜底）；BUILTIN_TEMPLATE_SETS 动态读 `wp_account_mapping.json` 206 条；详细 → `#conventions`/`#dev-history`
- **去重功能**：`ledger_data_service.dedup_ledger_data`（窗口函数 ROW_NUMBER PARTITION BY 业务列保留最小 id，默认软删+写 app_audit_log+只作用 active dataset）；详细 → `#dev-history`

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载（dev-history append-only 审计轨迹）
- 技术事实/端点速查/PG schema/spec 历史/近期修复明细 → `#dev-history` grep 关键词
- 架构/系统规模/数据流/MCP 工具全清单 → `#architecture`；编码规范/UI 视觉/操作铁律详解/PG 运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`；合并模块体检 → `docs/proposals/consolidation-module-status-and-proposal.md`
