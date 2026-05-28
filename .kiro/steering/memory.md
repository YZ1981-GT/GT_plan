---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
保持本文件 ≤ 200 行：完成事项 → dev-history，技术决策 → architecture，规范/铁律 → conventions。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller，不要 .bat）
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
- **新增依赖**：locust / marked + dompurify / Storybook 8.6.14 / xlsx-js-style / decimal.js / python-docx / prometheus_client / **PyYAML**（workpaper-html-renderer 引入）/ **fast-check v4.8.0**（前端 PBT）；外部 LibreOffice（4 路径 fallback）；**xlsx-js-style 已 npm install**（2026-05-28，报表/附注 Excel 导入导出依赖，之前 package.json 有但 node_modules 缺）
- **文档/表格生成职责边界**（2026-05-23）：Univer Sheets = 底稿在线编辑 / Univer Docs+TipTap+textarea 三级降级 /楷体_GB2312/宋体/Arial Narrow）必装
- **Dashboard 视觉规约**（2026-05-23）：5 dashboard 统一 `GtPageHeader variant="banner"` + dark 主题；DashboardViewSwitcher 共享组件挂 banner #actions slot
- **查询入口统一**（2026-05-23）：用户可见名称 = 「高级查询」；CustomQueryDialog 内 el-tabs 分两层「业务视图」+「高级构建器」（仅 admin/manager/partner）
- **高级查询白名单覆盖 9 维度**（2026-05-23）：TABLE_WHITELIST 16 张表全维度入栏；users 显式排除 hashed_password；JOIN_WHITELIST 以 projects 为中心辐射

## 任务状态

### 全部已完成 spec ✅

11 审计循环（D~N，548/548）/ phase 1~7（239/239）/ phase 8（116 tests）/ proposal-remaining-18（30/30）/ k-admin-cycle-post-review-fix / partner-dashboard / procedure-trimming / role-view-switching / 角色体系治理（145 vitest）/ e2e-business-flow（58/58）/ template-library-coordination（64/64）/ audit-chain-generation（101/101）/ enterprise-linkage（56/56）/ **ledger-import-view-refactor（243/243）** / **advanced-query-enhancements-p1p2（212 tests）** / **workpaper-html-renderer（40/40 tasks，413 tests，2026-05-26 commits fd95ae1+46fa4b5+8fd847d）** / **disclosure-note-full-revamp（46/47 tasks 实质完成，pytest 430/430 全绿 + F-1 双真实项目 UAT 通过：首汽租车_2025 173章节/138.8KB docx + 重庆和平药房_2025 40章节/38.2KB docx 含前端 UI Playwright 全自动化，2026-05-27 commits 6b6731c+65fc11a+3c5067c+e1477b2+1729c38f+58cff337+736cf1d4+551835b6+9a4e0bc2+52885362+df072352+f706de4b）** —— 详见 INDEX.md。

### workpaper-html-renderer 关键沉淀（详见 #dev-history）

- 1788 单体真底稿（A/B/C/D/E 共 1346 sheet）从 Univer 切到 HTML，F/G 558 sheet 保留 Univer
- 9 类 componentType 路由 + 禁止 Univer 兜底铁律 + 11 命名空间 4 层级跳转
- 方案 C openpyxl 加载致同模板 + 4 路径写入策略 1:1 还原
- 9 PBT 属性测试覆盖（hypothesis + fast-check 双框架）
- 性能基准全部 ×18+ 余量（HTML 冷启动 27.7ms / xlsx 导出 275.7ms / classification 1.2μs）
- 详细技术决策、新依赖（PyYAML）、测试模式（fake-timers / 子组件 stub / FakeDB）已下沉到 #dev-history

### 真正待办（外部依赖）

- LLM 真实接入：phase3 UAT-3 + K-1 / 6 stub 引擎（H/I/G/K/J/N，`settings.WP_AI_SERVICE_ENABLED` 一键切换）
- 6000 并发压测：phase3 UAT-5（需真 PG 大数据量 + Locust）
- W-3 钉集成（外部对接）
- Sentinel failover 真实验证：phase4 UAT-8
- WorkpaperEditor 瘦身（当前 2631 行，目标 ≤1000）：useEditorActions let→ref + template dialog 配置驱动 + 删冗余别名
- **附注模块全维度增强** spec 三件套 v0.6.2（`.kiro/specs/note-dynamic-tables-and-template-inheritance/`，commits 75a73008+b30e0531+3585cba2+89f97c86+dfc19013+db603bb9+a1a77c51+4ee4ec37+**14d46b9b**，2026-05-28）：v0.1→v0.2→v0.3→v0.4→v0.5→v0.6→v0.6.1→**v0.6.2 = 151 验收 / 38.5 人天 + 外部 5 人天 / 3 Phase 17 Sprint**；**v0.6.2 新增 D15 离线分发与一键导入**（commit 14d46b9b，用户原话「最好要支持用户的离线处理」「这个功能全面体现了人机互补的作用」）= ①xlsx 包含注意事项 sheet（6 节使用说明 + partner 联系人）/ 章节清单 sheet（TOC）/ N 章节 sheet（4 色单元格语义：黄=可填/灰=公式/红=锁定/绿=必填 + DataValidation）/ 隐藏 _meta_ sheet（base64+gzip 压缩 binding/formula/row_meta JSON 用于回传匹配）②按章节子集导出（partner/manager 权限）+ 可选 AES 加密 ③一键导入字段级 diff（值/公式/manual 三类）+ 章节级冲突选择（覆盖/保留/合并/丢弃）+ 30 天文件归档 + 审计日志 ④与 D6/D9/D11/D13/D14 联动（lineage/协作锁/版本树/section_id 匹配/template_type 校验）；**新增 Sprint C.0**（Phase 3，2 人天 / 23 子任务）；**CI +2** = CI-21（_meta_ 完整性）+ CI-22（导出→导入 round-trip PBT）；**ADR-022** 离线分发包格式标准；**v0.6.1 一致性修复** = ①删 v0.5 旧表 ②D1-D14 编号顺序 ③验收 92→140 ④F 章节拆 F-Consol/F-Compat ⑤必做加 D14 ⑥P-7 模板差异清单 ⑦CI-20 ⑧ADR-021 ⑨Sprint A.5 工作量 2→2.5；**15 维度** = D1 行动态/D2 列动态/D3 wp_data/D4 多源 fallback/D5 三级 trim/D6 集团基线/D7 Jinja 段落/D8 合并附注完整开发/D9 协作锁/D10 AI/D11 版本图/D12 合并↔单体映射/D13 章节序号动态/D14 国企↔上市丝滑切换/**D15 离线分发**（v0.6.2）；**Phase 化分层** = Phase 1 单体附注修复（17 人天，含 D1-D7+D9+D13+D14）/ Phase 2 合并附注完整+联动（10 人天，B.0 先于 B.1）/ Phase 3 高级特性+收尾（11 人天，含 D15+D10+D11+前端 UI+Word）；**Phase 2 启动门槛 = Sprint A.8 单体 UAT 通过**；**重大现状盘点**（grep 实测）= 后端 `consol_disclosure_service.py` 7 章节生成完整但**完全不消费子公司单体附注** + 前端 `ConsolNoteTab.vue` 1466 行 UI 框架完整但**章节树只有 7 项** + `consol_tree_service.build_tree` 已存在但**附注模块未调用** + `note_conversion_service` preview/execute 已存在但**未集成 section_id 也未支持跨模板合并**；**外部前置 P-1~P-7 总 5 人天**；待用户决策启动节奏
- **scripts 命名实例**（2026-05-27）：本 spec 系列工具脚本统一无 `_` 前缀（`cleanup_note_templates.py` / `migrate_disclosure_notes_to_v2.py` / `generate_note_template_bindings.py` / 对应 report.txt），因均幂等可重复跑（不是用完即删的一次性）；CI 卡点单测放 `backend/tests/services/test_note_*` 命名空间
- **附注 spec Sprint A.0 完成 ✅**（2026-05-28，D13 章节序号重构 9/9 子任务全绿）：V019 migration（7 列+2 索引+CHECK）/ 模板 JSON 注入（SOE 187 / Listed 204，合成 chapter `content_type='text'`）/ `note_section_numbering_service.py`（5 级 LEVEL_FORMATS + DFS 树遍历 + orphan 提升为 root 兼容 parent 不在 DB 场景）/ DB backfill 213 行全匹配 0 fallback / Jinja `ref()` + `make_jinja_ref_function` 闭包 / 47 测试全绿（25 service + 4 ref + 18 CI-18/CI-19）/ ADR-019+020 / 新增依赖 **Jinja2**（pip install）；**关键修复**：section_id 总长限 ≤95 字符（VARCHAR(100) 约束 + `-N` 后缀余量）；render_sections 对 parent 不在集合中的 orphan 节点自动提升为 root（DB 中 173 行 parent 指向合成 chapter 但 chapter 仅在模板 JSON 中）
- **fsWrite 适用场景实证**（2026-05-28）：fsWrite 可单次写 ≤200 行 Python 服务文件（`note_section_numbering_service.py` 240 行一次性创建无截断），与之前「fsWrite 50 行」铁律是不同场景 — 50 行限制针对 markdown 大改写场景的累积截断风险；新建文件类一次性写 200 行内 ok
- **PG 数据库名**（2026-05-28 确认）：`audit_platform`（不是 `audit_db`）；docker exec 命令用 `-d audit_platform`
- **附注 spec 关键技术沉淀**（disclosure-note-full-revamp，2026-05-27 完成 44/47）：DSL 入口 `note_formula_generator.generate_formulas_for_table`，5 函数 = `TB(account, period)` / `WP(wp_code, sheet, cell)` / `REPORT(row_code, period)` / `cell(row, col)` / `SUM(start:end, col)`；本 spec 新建 `=PRIOR / =AGING`；`DisclosureNote.is_stale` 字段已存在（F46/Sprint 7.22）+ `event_handlers._mark_downstream_stale_on_rollback` 已订阅 `LEDGER_DATASET_ROLLED_BACK`；新建 `useNoteStale.ts`（不是改 `useLinkageEvents`，后者不存在）；`NoteTrimService` 原 5 方法 + 新增 `auto_trim`；scripts 命名 = 幂等工具 `cleanup_note_templates.py` / `migrate_disclosure_notes_to_v2.py` / `generate_note_template_bindings.py`；公式存储 = `table_data._formulas` 顶层 dict（`row_idx:col_idx` → {type, expression, description, category, source}）；致同 Word 排版规范（21 项 + 11 项视觉断言）+ NoteFormatConfig 21 字段 frozen dataclass / GTNote* 命名空间样式 / fill_multi_header 多层表头
- **vLLM / httpx 链路 3 个待修复 bug**（spec 已沉淀到本 memory，待动手）：
  - **httpx 系统代理陷阱**：Windows Clash 类系统代理（127.0.0.1:7897）让 `httpx.AsyncClient()` 默认读取代理把 localhost 请求路由到代理返回 502；修复 = 创建 client 时显式 `mounts={}, trust_env=False`；需修 4 文件：`llm_client.py`（_sync/_stream_completion）/ `ai_service.py`（_get_ollama_client + _get_llm_client + _get_chromadb_client）/ `availability_fallback_service.py`（check_llm_available）/ `routers/system_settings.py`（check_url）
  - **vLLM `chat_template_kwargs` 必须 payload 顶层**：嵌套 `extra_body.chat_template_kwargs` 被 vLLM 静默忽略，`enable_thinking=False` 不生效导致 content=None reasoning 有值；`llm_client.py:107` 改顶层 `"chat_template_kwargs": {"enable_thinking": settings.LLM_ENABLE_THINKING}`
  - **LLM thinking content=None 处理**：finish_reason=length 时返回"思考超 token，请简化提问或增大 max_tokens"，**禁止**回退到 reasoning 字段；`llm_client.py:_sync_completion` 需补此分支
- **本地 PG schema 漂移已修复**（2026-05-27 完成，commit db403d7b）：alembic 当前 `a2f355648e85`，下游多个 head 因 `phase17_001` `CREATE TYPE IF NOT EXISTS` 不被 PG 支持而中断（已用 DO 块 + DuplicateObject EXCEPTION 修复）；**根因**：`MigrationRunner`（D6 版本化 SQL 脚本）= 启动时实际跑的迁移系统，`alembic` 仅历史遗留运行时不跑，导致 alembic chain 中后续 spec 改动需手工补；**修复方案** = 新增 `V017__fix_schema_drift.sql`（`job_status`→`job_status_enum` 重命名 + `interrupted` 值 + `import_jobs.{version,force_submit,creator_chain}`） + `V018__fix_schema_drift_full.sql`（自动从 ORM 反推生成 65 缺列 + 10 缺表 + idempotent CREATE/ALTER；workpaper_template_version 必须早于 workpaper_sheet_classification）；**0 漂移确认**（`_full_schema_diff.py` 反查工具）；alembic chain 整链尚未 upgrade 完（多个 stamp 跳过 + cell_annotations 等已存在），但运行时 D6 SQL 路径已通；**alembic chain 修复** = 另立 spec 工作（不在附注 spec 范围）
- **首汽租车_2025 / 重庆和平药房_2025 默认 is_deleted=True**（2026-05-27 实测）：5 项目中 4 个软删除，只有「重庆医药集团四川物流_2025」可见但 tb_balance/tb_ledger 都 0；UAT 前必须 `UPDATE projects SET is_deleted=false WHERE id=...` 恢复
- **附注 spec F-1 UAT 通过**（2026-05-27 commits df072352+f706de4b）：**双项目实证** = 首汽租车_2025（df5b8403）service 直调 173章节/138.8KB docx + 重庆和平药房_2025（2aa00f57）**前端 UI Playwright 全自动化** 40章节/38.2KB docx；**40 vs 173 差异 = Sprint 3 NoteTrimService.auto_trim 真起作用**（业务集中型企业附注按 TB 科目存在性自动精简，零售药房无投资性房地产/在建工程等行业不相关章节被裁掉）；UAT 报告 + 2 docx + UI 截图留存 `docs/uat/`；TB recalc 用 `full_recalc(project_id, year, "001")` 三参；NoteWordExporter.export 返回 BytesIO 不写文件；docs 目录新增 `uat/` 子目录（之前 8 子目录变 9）；前端 Playwright 流程 = login 拿 token 写 localStorage → navigate `/projects/{id}/disclosure-notes` → 点「📝 生成附注」+ 「开始生成」 → 等 8s+15s → 点「📤 导出Word」自动下载到 `.playwright-mcp/`
- **附注表样编辑器真数据验证**（2026-05-28 Playwright 实测）：首汽租车_2025 货币资金章节 = 银行存款 42,772,704.06 / 合计 42,772,704.06（期末）+ 47,151,610.42（期初）= 从 TB 自动取数填充；表样编辑器支持类 Excel 网格（A/B/C 列 + 行号）+ 公式栏 + 插入删除行列 + 版本历史 + 三个可视化开关（显示公式/显示数据源/显示状态）；公式管理中心 6 数据源 Tab + 行级公式编辑 + 分类筛选 + 健康度指标
- **LibreOffice 已装**（`C:\Program Files\LibreOffice\program\soffice.exe`）：后端启动健康检查 15s 超时是 LO 启动慢导致，**不影响附注 docx 导出**（python-docx 不依赖 LO）
- **D6 迁移系统铁律**（2026-05-27）：启动时跑 `backend/migrations/V*.sql`（MigrationRunner），不是 alembic；新加列/表写 `V0XX__*.sql` + `R0XX__*.sql` 配对；alembic 是历史遗留，schema 漂移走 D6 SQL 修而不去拉通 alembic chain；CREATE TABLE/ALTER COLUMN 必须 `IF NOT EXISTS` idempotent
- **disclosure-notes format-config 端点 405**（2026-05-27 待修，spec 自带 bug）：`GET /api/disclosure-notes/format-config` 被同 prefix 下其他 router（note_wp_mapping/note_trim/note_ai）的 path 拦截，FastAPI router 注册顺序问题；解决方案 = 把 `dn_router` 提到所有同 prefix router 之前 include
- **本地 git 状态**（2026-05-27）：master 领先 origin/master 178 commit + 落后 4 commit，**已 push 到 feature 分支** `feature/disclosure-note-full-revamp`（commit 52885362 含 V018 顺序修正 + memory 沉淀；含 179 commit；按 git_safety 不直推 master）；当前 HEAD 切到该 feature 分支并 tracking origin；PR 链接 = https://github.com/YZ1981-GT/GT_plan/pull/new/feature/disclosure-note-full-revamp

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
- **fsWrite 大文件覆盖铁律**（2026-05-28）：fsWrite 单次仅写 50 行内容，**禁止**用 fsWrite 重写 ≥100 行 markdown / 代码（如 spec requirements.md 681 行）会被截断丢内容；正确做法 = 用多次 strReplace 精确修复 + 必要时 `git checkout HEAD -- {path}` 恢复后再修复
- **PowerShell `--%` stop-parsing 单行铁律**（2026-05-28）：`git commit --% -m "..."` 后**禁止再用 `;` 接续命令**（`--%` 会把后续 token 全部当字面量传给 git 导致 pathspec 错误）；多命令拆成多次 executePwsh 调用
- **Spec 三件套一致性复盘 SOP**（2026-05-28，note-dynamic v0.6→v0.6.1，v0.6.2 复盘扩展）：每次大版本演进后必查 12 项 = ①问题陈述无残留旧表 ②维度按编号顺序 ③验收标题数字同步 ④章节编号无冲突（如 F 章节拆 F-Consol/F-Compat）⑤必做范围含全部新维度 ⑥依赖前置含全部新 P-N + 三件套数字一致 ⑦CI 卡点表数字同步 ⑧ADR 列表数字同步 ⑨Sprint 工作量与子任务数对齐（≥10 子任务=2.5 人天最低）⑩**Phase 工作量必校加总 = 各 Sprint 之和**（tasks.md header 写 17/10/11 但实际加总 15/7.5/11 是死亡陷阱）⑪**版本变更块对比基线必逐版本升级**（v0.6.2 新加块若仍写「v0.5 → 数字」就是错引基线）⑫**新维度必在 design 正文 §一 加详细设计 + feature_flag 列表加项**（D15 加进 ADR/CI/影响范围但 design §一无 D15 章节是高频遗漏）；**残留版本号陷阱** = `v0.4 关键路径` / `Sprint 0~13 线性` 这类章节标题在 v0.6 Phase 化后必同步删/改，否则 Sprint 编号体系自相矛盾
- **SQLite 测试 set_rls_context 兼容**：mock `app.deps.set_rls_context` 绕开（admin 路径仍会触发）
- **FastAPI dep_overrides 闭包陷阱**：`require_project_access("readonly")` 工厂每次返新闭包，dep_overrides 不命中；正确做法 = 仅 override `get_current_user` + `get_db`
