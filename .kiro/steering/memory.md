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
  - **降级预览链路（2026-06-12 修）**：OnlyOffice 不可用→`OnlyOfficeEditor` 组件 `degraded=true`→渲染 `DeliverablePreview`。**previewType 必须按实际文件后缀动态传**（docx→'docx' 可 VueOfficeDocx 渲染，xlsx→'unsupported' 显示下载提示）；旧 hardcode `preview-type="docx"` 导致 xlsx 被当 docx 解析→既不 @rendered 也不 @error→loading 永转圈。`DeliverablePreview` loading watch 也需对 'unsupported' 立即关闭 loading（否则遮罩盖住"不支持"提示）。**`item.file_name` 可能为空**（task.file_path=NULL 时无后缀可提取）→ `openPreview` 须从 `doc_type` 推导默认后缀（`financial_report*`→xlsx, `audit_report`/`disclosure_notes`→docx）。`.env` 本地 dev 须 `ONLYOFFICE_URL=http://localhost:8080`（非 `http://onlyoffice:80`，后者是 Docker 内部名主机不可达→health 永 false→degraded）；`docker restart` 后 `local.json` 的 `allowPrivateIPAddress=true` 丢失需重配
  - **OnlyOffice 本地 dev 三件套 .env**（缺一则预览/编辑异常）：`ONLYOFFICE_URL=http://localhost:8080` / `ONLYOFFICE_JWT_SECRET=xXxtvR7DFmIfCH9wNpHsZP2Ft71slaqZ`（须与容器 local.json secret 一致,空值→"文档安全令牌格式不正确"）/ `ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`。容器内 `local.json` 须含 `"request-filtering-agent":{"allowPrivateIPAddress":true,"allowMetaIPAddress":true}`（`supervisorctl restart all` 生效;docker restart 后丢失需重注入——用 `python3 | docker exec -i` 改 JSON）
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）
- **开发工具链（dev-tooling-modernization）**：gitleaks `.gitleaks.toml`+pre-commit / SQLFluff `.sqlfluff`(postgres,基线 1718) / uv 0.10.4（CI 5 job）/ Docling 裁掉(torch 太重) / DSPy 仅文档
- **底稿模板源**：`backend/wp_templates/`（按循环 A~S 分目录），`scripts/analyze/scan_wp_templates.py` 扫描输出 `backend/data/gt_template_library.json`(331 条，唯一权威源)
- **审计报告正文模板源**：`审计报告模板正文/`（仓库根），4 意见类型×4 企业类型=17 Word 模板；**架构决策=路径 A**（Word 模板作程序资产+占位符替换，非 Word→JSON→再生成）：`{{field}}` 替换 + `##OPT:id##` 可选段弹窗 + `##NOTE:xxx##` 终版删；模板就位 `backend/data/audit_report_templates/`（report_body 17 docx + financial_statements 4 xlsx + disclosure_notes 4 docx，`template_manifest.json` 版本 2025-v1）；spec=`audit-report-template-integration`
- **干净验证法**：uvicorn `--reload` 父子进程 kill 不净 → venv 另起端口（9981）绕 reloader；**in-process ASGI httpx**（`httpx.ASGITransport(app=app)`）直调端点最快（跑磁盘当前代码，无 stale server 风险）
- **markitdown 单例**：`backend/app/services/markitdown_service.py`（延迟初始化+扩展名白名单 17 种+`convert_stream(BytesIO)` 最窄接口）；知识库 `_extract_text_with_ocr` 三级降级 MarkItDown→MinerU OCR→PyPDF2/python-docx
- **不引入**：LLM 上下文压缩中间件（本地 vLLM 自带 prefix caching+审计精度敏感，RTK 已覆盖 CLI 90% 价值）；外部 agent harness 配置包（ECC 等，依赖具体 harness，Kiro 用 .kiro/steering+specs+hook 另一套；如取经只 cherry-pick 单 markdown 改中文，严禁 clone 整仓）

## 迁移与 PG schema（D6 MigrationRunner 运行时迁移，非 alembic）

- 启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞号字母序靠后者静默丢失，scan_migrations 已加同号检测抛 RuntimeError）；**当前最高 V072**（V070=bad-debt / V071=wp_export_import / V072=word_export_task.doc_type VARCHAR(20)→50）
- **⚠️ `CREATE TABLE IF NOT EXISTS audit_log` 是 no-op**：该名被 Metabase 共库占用（真实 schema 无 action 列）→ 应用审计写独立表 `app_audit_log`；建表前先 `to_regclass`+`information_schema.columns` 查真实 schema
- **本地 PG schema 漂移已修**（critical=0）：drift detector pkgutil walk import 全 model + 过滤 Metabase 共库污染
- **🔴 projects 表无 year/template_version_id 列**：年度用 `EXTRACT(YEAR FROM audit_period_end)::int`；materiality 年度列=`overall_materiality`；人员姓名在 `staff_members.name`（users 无 display_name），JOIN 用 `project_assignments.staff_id`；database.py 已加 `async_engine = engine` 别名
- **🔴 真实列速查**：trial_balance 金额=unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount/opening_balance（无 closing_balance，科目列=standard_account_code）；financial_report=row_code/row_name/current_period_amount/source_accounts（无 amount/line_code）；adjustments=adjustment_no/adjustment_type/account_code/review_status（无 status/entry_type/summary）；adjustment_entries=standard_account_code；working_paper 无 year/wp_code（wp_code 在 wp_index，JOIN wp_index_id）；issue_tickets 负责人=owner_id 不软删；CellAnnotation 作者=author_id
- **🔴 wp_template_registry 表实际不存在**：gt_template_library.json 是唯一权威源；scan 脚本末尾 sync_registry 因表不存在静默跳过（已加白名单不报 drift）
- **🟢 schema drift 白名单已补 `_category_correction_backup`（2026-06-13）**：该表是 `migrate_account_category_correction.py` 的回滚备份(快照 project_id/table/record_id/old_category 供 --rollback)，`_` 前缀故意无 ORM 映射，与 `_sign_migration_backup`(V064) 同类→加进 `schema_drift_detector.KNOWN_ALLOWLIST` 消除 db_extra 误报(非删表，删表丢回滚能力)；24 drift 测试全绿。**铁律：一次性迁移脚本的 `_` 前缀备份表一律加 KNOWN_ALLOWLIST，不删不映射**
- **🔴 `tb_aux_balance_summary` 真实列是 `dim_type` 非 `aux_type`（2026-06-13 修，纠正历史误判）**：辅助余额表 Tab 500 根因=commit `314a6fe4` **基于错误现状判断反向改坏**(当时 memory 误记"真实表列名是 aux_type"，实测 `SELECT aux_type FROM tb_aux_balance_summary`→`column does not exist`)。该 commit 把原本正确的 `dim_type` 全改成 `aux_type`→入库 `smart_import_engine.rebuild_aux_balance_summary` INSERT 崩溃(summary 0 行)+查询 `ledger_penetration.get_aux_balance_summary` 500。修=两侧回退 `dim_type`(注意源表 `tb_aux_balance` 确有 `aux_type` 列，SELECT 端 `ab.aux_type` 对，只 summary 表目标列名改)。用 12.7万行真实数据项目 `5942c12e` 端到端验证(rebuild 31295 行+查询 21 维度组)+契约测试全过。**教训：改列名前必 `docker exec psql \d 表名` 实证，勿信旧 memory 记录**
- **真实 PG 数据**：5 项目多 standalone，**0 个 consolidated 项目**（合并 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全（序时账/明细账数据干净，82384 行借贷单边）但 audit_period_end 为 NULL
- **🟢 recalc_unadjusted v2 正数化已修（2026-06-13）**：`tb_balance.closing_balance` 入库时是 v1 口径(借正贷负,`convert_balance_rows` 对贷方 `-abs()`)，但 `recalc_unadjusted` 构建 `trial_balance.unadjusted_amount` 时旧代码直接传递(注释误称"入库已是 v2 正数")→ 负债/权益行在试算平衡表显示负数。修法：对非损益类(1~4xxx)贷方方向科目取 `abs(closing)`/`abs(opening)` 完成 v2 正数化。触发 `full_recalc` 即可修复存量数据(已在重庆和平药房项目浏览器实测验证 ✓ 借贷平衡)。其他项目如有同问题,点"一键重算"或重新导入即可。**铁律：`tb_balance` 保留原始 v1 口径,`trial_balance` 必须 v2 正数**。**recalc_unadjusted 两条路径**：①资产负债权益类(1~4xxx)从 `tb_balance.closing_balance` 取+贷方类取 abs ②损益类(5/6xxx)从 `tb_ledger` 取单边发生额(收入取贷方,费用取借方)——因为损益类在余额表 closing 通常=0,值在发生额里。**balance-check 端点**(`/trial-balance/balance-check`)用 `tb_balance` 原始数据验证(SUM(正)=SUM(|负|),同源恒等)——`trial_balance` 经 v2 变换后不保持算术平衡,不能用它做平衡校验。前端 `trialBalanceTotals` 改为调后端 API 取权威结果。后端 `get_trial_balance` 返回 `direction` 权威字段(direction_resolver 判定),前端 `getDirection` 优先用后端 direction。6xxx 中收入科目(6001/6111/6115/6117/6301)由名称含"收入/收益/利得"判贷方
- **🔴 recalc_unadjusted 叶子过滤+v2 正数化（2026-06-13 修）**：`tb_balance` 多级树（L1父=L2+L3子之和），mapping 映射每级→旧代码全层级 SUM 父子重复累加（试算表翻倍）。**修法**：只汇总叶子（NOT EXISTS `child LIKE parent||'.%'`）+贷方取 abs+损益取发生额。`balance-check` 用 tb_balance 原始数据验证。**回归测试** `test_recalc_leaf_only_no_parent_child_double_count`
- **🟡 贷方科目负数=存量未重算非代码回归（2026-06-13 复发诊断）**：若试算表负债/权益/收入类显示负数,先查 `projects.updated_at` vs 修复上线日(06-13)——06-13 前导入的存量 `trial_balance` 是旧 v1 逻辑算的负数,修复代码完好但未对存量重跑。**诊断铁律**:先 `SELECT unadjusted_amount FROM trial_balance` 看符号 + 比对 `tb_balance.closing_balance`(原始 v1 借正贷负,负数正确不动)→确认是 stale 非回归→对项目跑 `recalc_unadjusted`(in-process 实跑验证)即转正(和平药房 5942c12e 实测 2201/2202 负数→正,liability/revenue negative 清零,仅剩资产备抵/费用红冲合理负数)。**两表口径勿混**:`tb_balance` 余额表保留借正贷负(前端方向列显示)、`trial_balance` 试算表必 v2 正数。其它 06-13 前项目同理,点"一键重算"即可
- **🔴 报表引擎取数铁律（2026-06-13）**：报表统一从 trial_balance 取数（审定=audited_amount/未审=unadjusted_amount），纯公式路径 TB()/SUM_TB()，**不从四表库重新聚合、不走 report_line_mapping**（mapping 有历史错配）。`data_quality_service` 平衡检查用 row_code OR 匹配（BS-039/BS-099）
- **🟡 报表公式已补 6 行（DB 数据）**：BS-005/006/009 加坏账扣减+应收股利；BS-027 减累折；BS-028 加清理；BS-050 加应付利息。差额 2594万→249万（剩余=2221 应交税费方向边界 case）
- **tb_balance 方向入库**：`_apply_sign_convention` 改为存**余额实际方向**（归一后>=0 存科目正常方向，<0 存反方向）；balance-tree 端点返回 `opening_direction`/`closing_direction`；前端期初/期末余额左侧各有方向列（优先读 DB 字段，降级按符号判）
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
- **🟢 active spec=2**：①audit-report-template-integration 181/184，剩 3 项运维（17.3 灰度 flip + 17.4 旧路径下线 + 人工验收）②editing-lock-v1-v2-consolidation（2026-06-13 新建，requirements-first，**三件套二轮复盘已修订待实施，14 properties**）：编辑锁 v1→v2 收口三阶段零停机。**一轮5缺陷已补**：v2 acquire补同人续期(任务1b/需求3.2a/P13)、v1`/active`死端点降级、迁移naive→aware时区、force SSE的wp_id条件化、前端flag竞态。**二轮再发现3问题已修**：①前端`useFeatureFlags.isEnabled`实测只读全局`enabled`布尔**不消费rollout_percentage/whitelist**→前端灰度只能全开/全关(非百分比)，design措辞已纠正,百分比灰度需下沉后端`is_enabled(user_id=)`不在范围 ②`isEnabled`catch→false保守回退v1,但阶段3删v1后flag抖动会回退到已删端点→404(需求6.3a+任务12b:阶段3移除前端v1回退分支默认改v2) ③时区规整SQL`AT TIME ZONE 'UTC'`对timestamptz列方向会反→改"迁移前先`SHOW timezone`+抽样实测确认偏移再定表达式"。**三轮再发现**:V*.sql 仅真实PG启动跑(测试fixture用`sqlite+aiosqlite:///:memory:`+create_all不加载迁移),MigrationRunner无per-script dialect跳过分支也不需要→迁移类测试(P1/2/3/14)+并发冲突测试必须标`pg_only`(conftest非PG自动skip),v2纯ORM锁行为测试(P4-9/13)可SQLite。**元结论:连续3轮缺陷同根因=spec写未实证下游假设,纯文档复盘边际收益见底,该进实施用真实PG跑V073一次性证伪所有时区/dialect/映射假设**；archived=140
- **外部依赖**：LLM embedding 实例 / 合并 UAT / GitHub 默认分支改 main / 走 PR 合入 / 钉集成
- **后续按需**：附注 96 个 OPT 章节条件化标注（等灰度反馈，611 块 99.5% 已有块级占位符，TEXT 整块填充够用）
- **🟡 待确认（附注富文本"删表格标题行"，2026-06-13 暂挂）**：用户要附注第八章富文本里的"表格小标题行"(如"应收票据分类"/"按账龄披露应收账款"/`####`/`（1）`编号标题,多与下方表格名重复)删掉,但保留"（注/提示/【】）指引"和政策正文段落。**坑**:三类内容(表格小标题/披露指引/正文段落)靠规则自动判别会误删(八、84 指引被误判匹配表名),我先误清空过全部 text_content 已从 `_note_text_ch8_backup` 表完整恢复(77条)。**待用户明确删除边界后**:写带预览(先打印将删/将留清单核对)的脚本再执行,范围(仅辽宁卫生 vs 全项目)也需确认。**`disclosure_engine.py` 优先级3"模板默认文字"改动已注释掉(无上年/LLM 时正文默认留空)但更合理做法是"表格标题只写进表名不灌正文"——此改动悬而未决,确认边界后一并定**。`text_sections` 仍用于 `_infer_table_names_from_text` 给表格命名(印证这些就是表格标题)。**关联设计待决(同源)**:附注 `text_content` 混装两类内容——提示性指引(`（注…）`/`（提示…）`/`【…】`/`注：`)vs 实质正文,系统分不清→导出两处出错(`note_word_exporter`:①`should_skip_empty_section` 只要 text_content 非空就判"不跳过"→纯提示+空表章节被误导出 ②programmatic 1144行/template 占位符把 text_content 整段原样塞进 Word→提示语进交付件)。给了用户 3 方案待选:A 新增 `guidance_text` 列分流(推荐,text_content 只留正文,溯源哈希更准,但需迁移列+存量拆分→走 spec 三件套) / B 约定标记导出时过滤(轻量无迁移,规则边界有误判风险) / C 仅修判空(最小,提示语仍进交付件治标)。**用户已选 A→建 spec `note-guidance-text-separation`(feature/requirements-first,需求阶段✅完成,8条EARS需求,待用户审阅进设计)**。真实数据:全库906非空text_content章节=62%含正文/28%纯提示/9%纯标题(约37%导出会污染交付件);**纯前缀规则不可靠**(大量指引是`（说明…）`/`（企业应…）`无固定前缀的括号祈使句)→存量拆分须预览-人工核对-执行+备份回滚+"识别不可靠则不拆分"硬约束。3个待设计权衡:①指引识别方式(启发式/人工/LLM)②独立列vs JSON子字段③stale抑制粒度
- **🟢 服务边界已文档化（2026-06-13）→ `.kiro/steering/service-boundaries.md`（manual `#service-boundaries`）**：①**编辑锁 v1/v2 误判已纠正**——两套均现役非"v1 可删"：v1(`editing_lock_service`/`editing_lock`router 前缀`/api/workpapers`/表`workpaper_editing_locks`/按`wp_id`)管底稿(`WorkpaperEditor.vue`)，v2(`editing_lock_service_v2`/`editing_locks`router 前缀`/api/editing-locks`/表`editing_locks`/按`resource_type+resource_id`)管附注/报告(`DisclosureEditor`/`AuditReportEditor`)，前端 `useEditingLock` 按 `resourceType` 分流；**直接删 v1→底稿锁 404**，收口须 spec 三件套+迁前端路径+迁存量锁数据+Playwright，未迁完前 v1 不得删 ②AI 5 入口各司其职不可合并：`llm_client`(httpx+熔断无DB)/`AIService(db)`(底层抽象查active model)/`UnifiedAIService(db)`(门面包核心+插件+OCR)/`WpAIService`(底稿域+溯源包装)/`NoteAIAssistantService(db)`(附注域)；选用决策见文档 ③schema 漂移自检+迁移弹性是**优点非bug**不动
- **结构优化候选（2026-06-12 codegraph 体检，非任务待决策）**：`check_file_size.py` 报 19 文件超红线，最重 `report_engine`1996(+60%)/`smart_import_engine`2787/`custom_query`router2162(LibreOffice重算+预览本应下沉 service)/前端 TrialBalance2931/DisclosureEditor2126(超hard cap)；`ai_plugin_service` 8 个 Executor 全 stub 应标 developing
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
- **🔴 附注导出按 `sort_order` 排序铁律（2026-06-13 修）**：附注章节号是中文（一/二/七/九/十、N），`ORDER BY note_section` 字符串排序按 Unicode 码点（七<三<九<二<五）→导出 Word 章节**完全乱套**。必用 `ORDER BY sort_order ASC NULLS LAST, note_section`（DB sort_order 列 99/100/199/200... 编码正确章节序）。已修 `note_word_exporter._load_notes`(programmatic+template+html 三路径) + `word_template_filler`(同病)；consol_disclosure/note_offline_export 本就对。**`disclosure_notes` 导出/列表排序一律 sort_order 优先,禁中文 note_section 字符串排序**。纯代码逻辑问题(非数据)，对所有项目生效下次导出即正确。注:export-word 端点走 programmatic 模式(致同格式重排版,非 1:1 复制模板 docx);template docx 填充是另一链路(USE_TEMPLATE_FILL_SERVICE+交付件中心)
- **🟢 紧凑表格全局类 `gt-compact-table`（2026-06-13）**：用户偏好数据表行间距小。在 `styles/gt-table.css` 定义复用类(cell padding→0/行高24px/line-height20px/编辑态输入框压22px)，目标 `<el-table>` 加 `class="gt-compact-table"` 即生效(非 scoped 无需 :deep)。已应用:附注科目表(DisclosureEditor)/试算表(detail+summary)/报表(普通+对比)。**合并工作底稿 worksheet(SubsidiaryInfoSheet等20+，各有 cellStyle/headerStyle+整行 el-input)暂未套**(待确认录入表是否要同等紧凑，避免压扁影响录入)。新表格要紧凑直接加此类，勿到处复制 CSS。**🔴 特异性陷阱（2026-06-13 复发修）**：`gt-polish.css` 有全局 `.el-table td.el-table__cell{padding:10px 14px!important}`(特异性0,2,1)，原紧凑类 `.gt-compact-table .el-table__cell{padding:0}`(仅0,2,0)即便带 !important 也被 polish 盖回(td 行高仍46.8px，.cell 压了但 td padding 没压)→表现像"改动丢失/又回去了"，实为特异性输了。修=紧凑类 td/th 必带 `td.`/`th.` 限定符提到0,2,1 与 polish 持平，靠 gt-table.css 在 gt-polish.css 之后导入(同级后者胜)。实测行高46.8→26.8px。**铁律:写覆盖 el-table 默认样式的类必带 td./th. 限定符,否则被 gt-polish 全局规则反盖**
- **去重功能**：`ledger_data_service.dedup_ledger_data`（窗口函数 ROW_NUMBER PARTITION BY 业务列保留最小 id，默认软删+写 app_audit_log+只作用 active dataset）；详细 → `#dev-history`
- **🔴 contenteditable + Vue v-model 回写循环铁律（2026-06-13 修附注富文本表格不可编辑）**：`NoteRichTextEditor.vue` contenteditable + `@input`emit + `watch(modelValue)` 比较 `innerHTML!==newVal` 重设——但浏览器规范化 HTML(属性序/`&nbsp;`/`var()`)使 innerHTML 永不等于父组件原始串→**每次 keystroke 重设 innerHTML→光标丢失/单元格无法连续输入**。修=watch 加 guard：`isInternalChange` 标记跳过自身 emit 回写 + 编辑器聚焦期间(`document.activeElement===ed`)不重设。另:`execCommand insertHTML` 内联 style **不解析 `var(--xxx)`**(边框丢)，表格 HTML 用具体色值+`<td><br></td>`保证可聚焦。Playwright 实测键盘逐字输入单元格文字保留。**铁律:任何 contenteditable 组件接 v-model 必加 isInternalChange/focus guard**：`disclosure_notes.table_data` JSON 结构=`{name, headers:["项目","期末余额","期初余额"], rows:[{label, values:[...], is_total, row_type, _cell_meta:{"0":{semantic,binding_id}}, _cell_modes:{"0":"auto"}}], _tables:[多表]}`。**铁律**：单元格值字段是 `values`（非 `cells`）；`_cell_meta`/`_cell_modes` 按**列索引**键内嵌每行（非 section 级 `行:列` 键）；`headers[0]` 是 label 列头其余才是数据列头；多表章节读 `_tables`。**`section_id` 列 DB 几乎全空**，前端勾选/过滤传的是 `note_section`（"八、1"）→ 过滤必须 `note_section IN(...)` 不能用 `section_id IN(...)`(全空→0条→导出全空)。`note_offline_export_service._build_section_sheet`/`_calc_completeness` 曾误读 cells+headers+section级meta+section_id过滤→导出全空已修(重写 `_render_section_table`)。**改附注导出/解析前必先 `psql` 看真实 table_data 结构**。**🔴 openpyxl→WPS 兼容铁律**：openpyxl `Comment`(单元格批注)会生成 legacy VML drawing，与 `ws.protection.sheet=True` 组合→**WPS 报"无法打开指定的文件"**(Excel 宽容 WPS 严格)。空表无批注能开、填了 binding 数据后 124 comment+62 vml 就崩。修=移除 Comment(溯源信息由 4 色着色+隐藏 `_meta_` sheet 承载，批注冗余)。**诊断法**:zip testzip/xml/openpyxl reload 全过≠WPS 能开,须二分关 comment/protection;查 `[n for n in zipfile.namelist() if 'comment' in n or n.endswith('.vml')]`
- **🟢 附注离线导出弹窗树形勾选（2026-06-13）**：`NoteOfflineExportDialog.vue` 自定义勾选从扁平 checkbox 改两级树——`buildSectionTree()` 按 `note_section` 章节号前缀（首个「、」前中文数字）分组，裸章节号(如"四")作父、`四、xxx`作子；父复用真实章节 id，无裸章节用合成 `__group__:前缀` id 提交时过滤。加全选/全不选/展开收起/已选计数。el-tree 原生父子级联(勾父带全部子)。Playwright 实测辽宁卫生187节:勾"四"→自动选37节(36子+自身)。`DisclosureEditor` 传 `sections=noteList.map(section_id:note_section)`

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载（dev-history append-only 审计轨迹）
- 技术事实/端点速查/PG schema/spec 历史/近期修复明细 → `#dev-history` grep 关键词
- 架构/系统规模/数据流/MCP 工具全清单 → `#architecture`；编码规范/UI 视觉/操作铁律详解/PG 运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`；合并模块体检 → `docs/proposals/consolidation-module-status-and-proposal.md`
