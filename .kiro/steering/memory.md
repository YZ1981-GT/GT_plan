---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
**保持本文件 ≤ 200 行**：完成事项 → dev-history / INDEX.md / git 历史；技术决策 → architecture；规范铁律 → conventions。
精简归档历史（含 V3/附注/合并 A-P 系列详细 sprint 日志）见 `git show <旧commit>:.kiro/steering/memory.md` + `docs/proposals/` + `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出控制铁律（反复强调）**：分步输出，一次不要太长，大改动拆小批次；**但要连续做完整个任务直到完成，不要每段都停问**（分步 ≠ 频繁征求确认，只在真正需决策时停）
- **tasks.md `*` 标记任务也要做**：run-all-tasks 时 `*` 可选任务也必须做完，除非用户明确说跳过
- **任务标记不能假绿**：标 completed 必须有实际代码+测试通过证据；外部依赖/待环境如实标 `[ ]*`，用"代码已改但未实测"措辞
- **彻底解决不绕开**：错误必复现+定位根因+修主代码+加防御测试，绝不"换参数避开"
- **触类旁通 grep**：发现一处反模式立即 grep 全仓找同类一次修完
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端 = 先写 spec
- **spec 设计阶段必做"现状 grep 确认"**（G spec 复盘教训）：每项改进先确认迁移/端点/依赖 spec 是否已有产物；外部依赖标明降级方案+切换点；`*` 评估任务在设计阶段直接做 ROI 判断（列改动文件数/收益/风险）
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：所有用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；不接入 i18n 硬编码 + ESLint 卡点
- **中文场景必须支持（用户 2026-06-01 强调）**：功能/数据层中文全链路不能崩——中文文件名下载（Content-Disposition 必 RFC5987）、中文项目名/客户名/底稿名导出、中文数据查询导出均须实测过；区别于"UI 全中文化"（界面文本层）
- 功能收敛停加新功能，核心 6-8 页做到极致，空壳标 developing；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- **文档/文件夹级 LLM 对话是最实用核心功能（2026-05-31 用户强调）**：平台任意文档/文件夹都能发起 AI 对话，自动注入当前文档+关联知识库（同行业/同模板/同科目）作 RAG 上下文；把知识库从"存文件"变"随时可问的专家"；详见 `docs/proposals/global-modules-status-and-improvement-2026-05-31.md` §二十二（spec 名 `doc-level-ai-chat`）
- git 单 commit 提交所有变更；**push 前必先 fetch 同步**（stash → fetch --prune → 评估 ahead/behind → 决策 → pop → commit/push）
- **协作走 PR 不直推 main**（紧急修 main 崩溃可一次性例外，需用户拍板）；默认分支 `main`（非 master）
- 提建议前先验证不引用过时记录；完整复盘诚实暴露问题不粉饰；PDCA：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发 6000 人；底稿编码致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A 报表/调整 / B 控制了解 / C 控制测试 / D 销售收入 / E 货币资金 / F 采购存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 筹资 / M 股东权益 / N 税费 / S 专项

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis 6379；后端 9980 / 前端 3030 / vLLM 8100；DB 名 `audit_platform`；测试用户 admin/admin123
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`（勿混）
- Docker 容器：`audit-postgres`(5432) / `audit-redis`(6379→6379) / `audit-metabase`(3000)；health 端点 `/api/health`
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）；views/components/composables 在其 `src/` 下
- Playwright MCP 已装（workspace `.kiro/settings/mcp.json`）；新增依赖见 #dev-history（locust/marked+dompurify/decimal.js/python-docx/PyYAML/fast-check/Jinja2/jsonpatch + 外部 LibreOffice）
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）；仓库根 `scripts/run.py` 统一入口
- **底稿模板源目录**：`backend/wp_templates/`（按审计循环 A~S 分子目录），scan 脚本 `scripts/analyze/scan_wp_templates.py` 扫描后输出 `backend/data/gt_template_library.json`；ROOT 变量 = `backend/`（parent×3）
- **D6 MigrationRunner 是运行时迁移**（不是 alembic）：启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞名字母序靠后者静默丢失）；**当前最高 V044**；**✅ V040 冲突已修（2026-06-01）**：report_config_baseline 重编号 V040→V044/R044（旧 V040/R040 已删，真实 PG 确认表+is_stale 列存在），且 `scan_migrations` **加同号检测**（重复 version 抛 RuntimeError 根治复发）+ 防御测试；**✅ V043 pgvector 容错化**：原无条件 `CREATE EXTENSION vector` 在标准 PG 镜像（无扩展）硬失败致 health degraded（曾 attempt 11 次）→ 改 `DO $$ ... EXCEPTION WHEN OTHERS RETURN` 优雅跳过，降级 VECTOR_STORE_BACKEND=pgtext（真实 PG 确认 embedding 列未建、failure 已清；装 pgvector 后重跑启用）
- **真实 PG 数据**：5 项目多为 standalone，**0 个 consolidated 项目**（合并模块真实 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全；**⚠️ 首汽租车 audit_period_end 为 NULL**（按年度取数端点 project_year 降级 None）
- **本地 PG schema 漂移已修**（commit 508393da，965→critical=0）：drift detector 用 pkgutil walk import 全 model 子模块 + 过滤 Metabase 共库污染 + health 按 critical_count（orm_extra+enum_mismatch）判 degraded
- **🔴 projects 表无 year / template_version_id 列**（render-config/prefill-context 曾因此对所有底稿普适 500——PG 首条 UndefinedColumn 使事务 aborted 后续全 500，2026-06-01 已修+契约测试守护）：年度须用 `EXTRACT(YEAR FROM audit_period_end)::int`；materiality 年度列名 `overall_materiality`（非 materiality_level）；人员姓名在 `staff_members.name`（users 无 display_name），JOIN 用 `project_assignments.staff_id`（非 user_id）；**database.py 已加 `async_engine = engine` 别名**（dataset_purge/recycle_bin/ledger_import_health 曾 import 不存在的 async_engine）

## 任务状态

### 合并模块（consolidation）四阶段 — 代码+测试完成，未见真实数据
- **🧮 合并核心会计模型（用户 2026-05-31 明确，已对照代码验证）**：**合并数 = 各子企业个别数据汇总（individual_sum）+ 差额表**；差额表与其他子企业列类似，是专门填调整分录 + 抵销分录（以及同控合并重复部分处理）的"虚拟列"，**一般以负数填列**；代码实现 = `consol_amount = individual_sum + consol_adjustment + consol_elimination`（trial 路径）/ 差额表引擎中间节点 = Σ子节点 consolidated + 本级抵销调整（差额表只记调整抵销不含个别数）——两路径同此模型
- **4 Phase spec 全 ✅ 代码+测试**（2026-05-31 merge 后四阶段套件 **147 passed/0 failed**）：Phase0 核心管线（B1 汇总/B2 对账/schema 基线/锁定闭环）+ Phase1 架构锁定（AmountResolver 统一引擎/ELIMINATION_APPROVED 事件重算/全端点锁定+ConsolLockedBanner/B6 负商誉/B7 少数股东/A3 async）+ Phase2 编排接线（cascade_refresh/refresh-all SSE/V2 附注 flag/自动抵销 draft/报表穿透/cross_template/公式联动/签字冻结）+ Phase3 前端穿透（ConsolBreakdownDialog/provenance/双向导航/自动建树）
- **16 ADR**（CONSOL-001~003/101~106/201~206/301~304）+ 24 consol service
- **🔴 四阶段曾最大盲区 = 无全链路集成测试**（各阶段 mock 掉相邻阶段，merge 两次咬人：async 签名漂移 + Phase1 删 _execute_formula + **PK 缺 uuid default 致 B1 链路从未真实落库**）→ 封板①已补 `test_consol_full_chain_integration.py` 守护；**统一卡点 = PG 0 个 consolidated 项目**（真实 UAT 全 data-blocked，封板②seed 脚本待 live PG 解锁）
- **封板已完成（work 分支补，2026-05-31 merge 入 main）**：①✅ 全链路集成测试 `test_consol_full_chain_integration.py`（真 SQLite+真 ORM 行+真 service 跑 aggregate→trial→reconcile + refresh_all report-await 回归守卫 + branch/draft-vs-approved，4 passed）②✅ `seed_consol_uat.py` 幂等造最小合成集团（1母2子+TB+draft/approved抵销+内部交易，--dry-run 离线可验）③🟡 Phase2/3 Playwright 待环境；**收手判断：地基已正确，①②已封板转回核心模块**
- **🐛 封板①抓到真 bug 并修复**：`consolidation_models.py` 全部 14 个主键 `id` 列 `primary_key=True` 但缺 `default=uuid.uuid4`（V034 迁移 `id UUID NOT NULL` 也无 server default），导致 `upsert_trial_row` 等不传 id 的 ORM 插入 NULL 主键 → PG/SQLite 均 NOT NULL 违约；147 旧测试全 mock/纯函数从未真实落库故漏网。根因修复=全列补 `default=uuid.uuid4`，280 consol 测试全绿无回归
- **✅ 预存 worksheet 测试失败已修（commit `ce898e83`）**：`test_consol_worksheet.py` 2 红根因 = seeded_db fixture 抵销用 `review_status=draft`，但 Phase1 引擎改为**只消费 APPROVED**（ADR-CONSOL-102）→ 抵销不生效；**引擎本身正确**（差额表中间节点 consolidated=Σ子节点 consolidated + 本级抵销/调整，不含本级个别数，非"丢本体"bug）；修复=fixture 改 approved；**教训：先读设计文档确认是引擎错还是 fixture 过时，不预设引擎会计 bug**
- **四阶段三件套已归档 `_archive/09-consolidation-phases/`**（work commit `375edd8d`，封板①②完成后归档，非空归档）；**tasks.md 残留未勾项全是外部依赖**（真实集团数据 UAT `*` 卡 PG 0 consolidated + Playwright 待环境 + B6/B7 CAS20 审计专业复核），代码+测试层面已封板

### git 当前状态（2026-06-01）
- 当前分支 `work/2026-05-30-wp-specs`，已与 `origin/work/2026-05-30-wp-specs` 同步（ahead 0）；最新 commit `bb7ea6cf`（107 文件 +14635/-465 = B/C/E/F/G spec 实施 + 实施后真实 PG 复盘 4 类 bug 修复 + rollback 收口 + 防御测试）；**已 push，尚未建 PR**（待走 PR 合入 main）
- **协作态势实证（2026-06-01）**：work→main 纯快进零分叉（main 落后 4，无冲突可合）；feature/disclosure-note + spec/frontend-consistency-m1 均已并入 main（领先 main 0=陈旧分支可删）；当前无他人未合改动
- **🔴 远程默认分支隐患**：`origin/HEAD → origin/master`，但 **master 落后 main 298 commit**（master 是陈旧遗留，实际活跃主干是 main）；新人克隆默认 checkout master 会严重过时，误在 master 开发合回会巨量冲突 → 需在 GitHub Settings 改默认分支为 main（Agent 无法改远程仓库设置）
- **文档类冲突预防策略**：memory.md / INDEX.md / append-only 复盘文档是多人必改高发区，冲突时取并集（保留双方），走 PR 让 GitHub 先暴露冲突，不本地直推 main 覆盖
- **git 工具环境（2026-06-01 实证）**：远程 `origin = https://github.com/YZ1981-GT/GT_plan.git`（HTTPS，非 SSH，每次推拉可能要凭证）；**gh CLI 已装(2.89.0)但未登录**（`gh auth login` 需用户本人浏览器授权，Agent 无法代登）→ 建 PR 当前只能走网页 compare 链接或先登录；提速可选 `git config --global credential.helper manager` 或换 SSH；**work→main 零分叉时直推快进 `git push origin work:main` 最快但违"不直推 main"铁律，仅用户拍板例外可用**

### 已完成 spec 总览
- 详见 `.kiro/specs/INDEX.md`（active + _archive 10 分类）
- **全局模块 7 spec 全部 ✅ 已实施完成（2026-06-01）**：A formula-engine-unification / B retrieval-kernel-unification / C doc-level-ai-chat / D report-config-baseline / E wp-ai-review-ux-fix / F global-modules-cleanup / G global-modules-p2-polish；残留仅 Playwright E2E 待 start-dev.bat 环境
- active 仅剩 `consol-note-three-level-drilldown`（stub 待真实合并数据）+ frontend-consistency-m1；**合并四阶段已归档 `_archive/09-consolidation-phases/`**

### 真正待办（外部依赖）
- LLM 真实接入（6 stub 引擎 `WP_AI_SERVICE_ENABLED` 一键切换）/ 6000 并发压测（Locust+真 PG 大数据）/ 钉集成 / 合并模块真实集团数据 UAT

### ✅ display_name + issue_tickets + 中文文件名 三类 bug 已实测修复（2026-06-01，真实 PG HTTP 端到端验证）
- ✅ `project_wizard.py:207`（list-with-progress）+ `qc_report_export.py:244` display_name → username（实测 9981 端到端 200）
- 🔴 **新发现并修**：`issue_tickets` 表**无 is_deleted/deleted_at/assigned_to 列**（负责人=`owner_id`，这张表根本不做软删除）；`qc_report_export.py` 3 段 SQL 都有 `AND is_deleted=FALSE`（首条 UndefinedColumn→事务 aborted→连带全 500）+ rect 段 JOIN `it.assigned_to` 应为 `it.owner_id`；`wp_risk_trace_service.py:56` 同样 `is_deleted=false` → 已全修
- 🔴 **新发现并修**：`qc_report_export.py` 中文文件名直塞 `Content-Disposition` → Starlette latin-1 编码 HTTP 头 `UnicodeEncodeError` → 500（SQL 全过、docx 生成成功后崩在最后响应头）；修=RFC5987 `filename*=UTF-8''{quote(name)}`（范例 `working_paper.py:529`/`wp_template_download.py:77`）
- ✅ **Content-Disposition 中文文件名全仓修复（2026-06-01，触类旁通 grep 一次清完 + HTTP 实测）**：中文直塞 header → latin-1 编码崩 500。统一改 RFC5987 `filename="{ascii回退}"; filename*=UTF-8''{quote(name)}`，修复 10 处含中文来源端点（qc_report_export/note_export/eqcr·memo/report_export·reports·export-excel/procedures/wp_download/chain_workflow·审计终稿zip/attachments附件名×2/office_preview·inline/wp_template_download·inline）+ reports.py 防御统一；ASCII 安全的（adjustment/validation/wp_offline/{uuid}/枚举）未动；**HTTP 实测 9981：qc-export + reports/export-excel 均 200，CD 头正确编码 首汽租车/年度财务报表(未审)**
- **实测教训（2026-06-01）**：①`audit-backend` 容器跑 6 天**旧代码**（无 list-with-progress 路由，请求 fallback 到 `/{project_id}` 当 UUID 解析→422）——实测必须用加载新代码的实例 ②start-dev 的 uvicorn `--reload` 父子进程互拉，taskkill 端口立即被接管 kill 不净 ③**干净验证法 = venv 另起端口（9981）`python -m uvicorn ... --port 9981`**，绕开纠缠的 reloader ④500 被 generic_exception_handler 吞 body，定位根因用脚本**直接调用端点函数**捕完整栈（`_diag_qc_endpoint.py` mock user+真 session）
- 系统性防御建议：加 CI「SQL 列引用 ⊆ 真实 schema」+「Content-Disposition 含非 ASCII 必经 RFC5987」契约检查
- 🟡 `docker-compose.yml` 注释整段 GBK 乱码（疑历史 Set-Content/-replace 写中文）；README 信息过时（V001-V026/143 测试 → 实际 V044/682 测试文件）

### ✅ 模块巡检 + 2 个 500 + ORM 类型漂移修复（2026-06-01，9981 真实 PG 巡检 25 端点）
- **巡检法**：venv 起 9981，admin 登录后逐打各模块代表性只读端点，按状态码筛 500（422=缺必填 query 参数非 bug / 405=方法不符非 bug）；最终 500 清单清零
- ✅ **schema drift type_mismatch 归零**：`evidence_hash_checks.export_id` ORM=UUID 但 DB=VARCHAR + 真实值是 `exp_rc_日期_hex`/`str(job.id)` 非 UUID → ORM 改 `String(64)` + `export_integrity_service` 去掉 `UUID(export_id)` 转换 + trace 调用用 uuid5 派生（48→47 drift，critical 类彻底归零）
- ✅ **qc_open_issues 500**：`qc_dashboard_service.get_open_issues` 查 `CellAnnotation.created_by`，真实字段是 `author_id`（ORM 无 created_by）→ 已修
- ✅ **sign_readiness 500（耗时最久，多轮定位）**：根因 = R4-CROSS-CHECK gate 规则查 `SELECT year FROM working_paper`（**working_paper 无 year 列**），首条 SQL 失败 → PG 事务 aborted → 后续所有 rule 的 `SAVEPOINT`/gate_decisions INSERT 全级联崩 500。改用 `trial_balance.year`。**连带修** consistency_replay_engine（layer2 financial_report 用虚构列 fr.amount/line_code/account_code→真实 current_period_amount+source_accounts JSONB；layer5 wp_account_mapping 表不存在→改空占位）+ QC-25(report_snapshots 表不存在→to_regclass 守卫)/QC-26(disclosure_notes 无 is_key_disclosure/source_cells→列存在性守卫) + cross_check_service 全量列修正（trial_balance 无 closing_balance→audited_amount/unadjusted_amount；adjustment_entries.account_code→standard_account_code；adjustments.status→review_status）
- 🔴 **关键技术发现（asyncpg 事务污染）**：①PG 事务一旦 aborted，**连 `SAVEPOINT` 命令都被拒**，故 gate_engine 给 rule.check 加 savepoint 隔离**无法挽救已被前序 rule 污染的事务**（savepoint 须在失败 SQL 前成功建立才有效）②根治之道 = 修最先失败的那条 SQL 让其不污染（不是兜异常）③规则内 `try/except` 吞 SQL 异常但不 rollback = 反模式：吞掉的是 Python 异常，PG 连接仍 aborted，后续全崩 ④定位法 = 拦 `db.execute` 记**第一个**失败 SQL（cascade 的 InFailedSQLTransaction 都是噪音）⑤service 直接调用过但 HTTP 500 = 多 rule 共享同一 session 致污染跨 rule 传播，单 rule 独立 session 测不出
- gate_engine 已加 rule.check savepoint 隔离（commit 失败则 rollback savepoint）作纵深防御，但**首要仍是修根因 SQL**

### ✅ 广覆盖 GET 巡检 + 14 个 500 全清零（2026-06-01，429 个仅 project_id 的 GET 端点）
- **巡检法升级**：从 OpenAPI 自动取「路径参数仅 {project_id}」的 GET 端点（429 个），httpx 逐打筛 500，结果写文件防 PowerShell 截断；最终 500 清单清零（仅剩 events/stream SSE ReadTimeout 非 bug）
- **批量定位法**：in-process ASGI httpx（`httpx.ASGITransport(app=app)`）+ logging 一次命中拿全部根因；或拦 `db.execute` 记第一个失败 SQL
- **14 个 500 分 6 类**：①缺列：prior-year-data(projects 无 prior_year_project_id→**V045 补列**)/qc-trend(WpQcResult 无 project_id→JOIN working_paper→wp_index)/batch-extract(Adjustment.entry_number/entry_type→adjustment_no/adjustment_type，AdjustmentEntry.account_code→standard_account_code)/cross-references(DisclosureNote.section_code→note_section) ②缺表：notes group-template/custom-sections/locks-active/data-lock-snapshots(4 表从未迁移但有 INSERT 路径→**V046 补建**) ③SQL 逻辑：import-intelligence quality-check/overview(HAVING 无 GROUP BY→改 WHERE) ④代码错：office-preview/health(模块缺 `import os`)/parse-all-workpapers(缺 `import sqlalchemy as sa`)/qc-rotation(import `app.models.project_models` 不存在→core)/eqcr memo-export(`build_memo_docx_bytes(sections, project_name=)` 传参错，签名实为 `(project_name, client_name, sections)`) ⑤类型不匹配：notes/locks/active(V046 建表用 TIMESTAMP 但 service 传 tz-aware datetime→asyncpg "offset-naive vs aware"→**V047 改 TIMESTAMPTZ**) ⑥事务污染：cost-overview(`_get_hourly_rates` 查 system_settings 缺表→吞异常但污染事务→后续 work_hours 查询级联崩→加 to_regclass 守卫)
- **新增迁移 V045/V046/V047**（均配 R 回滚）；当前最高迁移 **V047**
- 🔴 **system_settings 表不存在**（cost-overview 已 to_regclass 绕过，但该表被多处引用，是潜在隐患——可能其它端点也踩）
- **巡检教训**：①429 端点串行巡检超 180s，需调 per-request timeout=25s + 写文件 ②events/stream 是 SSE 长连接，巡检会 ReadTimeout 属正常 ③"缺表但有 INSERT 路径"=曾设计懒建表但从未真正建（同 wp_template_registry 模式），补迁移是正解 ④422(缺必填 query)/405(方法不符)非 bug，巡检要排除

### 🔴 GET 巡检复盘暴露的待办与风险（2026-06-01，诚实不粉饰）
- **🔴 本轮 31 文件+3 迁移全程零测试**：仅靠"启动后端 HTTP 命中 200"冒烟验证，违反自身铁律"标 completed 须有测试证据"+"修主代码加防御测试"——字段名修正(如 Adjustment.entry_number→adjustment_no)正是契约测试该守护的，一个都没补
- **✅ 已补契约测试 + V048 根治 system_settings（2026-06-01）**：①`test_raw_sql_schema_contract.py`（3 测试全绿）= 纯静态扫全仓 `text()` 裸 SQL 的 FROM/JOIN 表引用，比对「ORM metadata ∪ 迁移 CREATE TABLE ∪ 懒建 ∪ 基础设施」权威表集，CI 阶段无需 live DB 一次兜住整类「查不存在表」500（drift detector 只比对 ORM↔DB 抓不到裸 SQL）②**V048 建 system_settings 键值表**根治 cost/rotation/quality 三处缺表事务污染（cost-overview 实测 200）③修一处既存假红 `test_schema_drift_detector.test_type_mismatch`（TIMESTAMP↔TIMESTAMPTZ 被 detector 刻意判兼容，测试却期望 mismatch→改用 INTEGER vs VARCHAR + 补兼容用例）
- **🔴 契约测试揪出 10 个存量 phantom 表引用债务**（登记进测试 `_KNOWN_PHANTOM_DEBT` 白名单守增量，存量待逐个清零）：`ai_contents`(疑→ai_content_log)/`consolidation_adjustments`/`gate_evaluations`(疑→gate_decisions)/`report_snapshots`(已 to_regclass 守卫不崩但表未建)/`tb_account_chart`/`template_sets`/`trial_balance_entries`(疑→trial_balance)/`working_papers`(真实表是单数 working_paper)/`wp_account_mapping`(映射在 JSON+服务层无表)/`wp_template_registry`(服务层 table_exists 懒判未迁移)——均真实 PG 不存在，对应代码多被 try/except 包裹故未在巡检命中，是定时炸弹
- **🟡 200≠逻辑正确**：很多端点返 200 因首汽租车数据稀疏(financial_report 0行/QC 0条)走空路径；重写的 consistency layer2(source_accounts JSONB join)+cross_check 列映射在真实数据下算得对否未验证
- **🟡 改动未提交**：本轮累计 ~34 文件+V045/46/47/48(配R)+2 测试全在工作区未 commit，当前分支 `work/2026-05-30-wp-specs`，该独立成 commit 走 PR；components.d.ts 被工具改(无害)提交前 checkout 掉
- **当前最高迁移 V048**（V045 prior_year_project_id / V046 4 张附注懒建表 / V047 note_locks TIMESTAMPTZ / V048 system_settings）
- **元反思（系统性根因）**：连续多轮逐个救火 500，根因是"代码库大量基于想象 schema 写的查询，ORM/裸 SQL 列名与真实 PG 长期漂移无人发现——因这些端点从未被测试覆盖也没真实数据跑过"。**真正根治 = CI「SQL/ORM 列引用 ⊆ 真实 schema」契约检查**（一次兜住整类，ROI 远高于逐个修），否则下批同类 bug 还会冒


### 全局 7 模块改进 7 spec 全部完成（2026-06-01）
- 据盘点文档生成 6 个 active spec（全 Design-First/bugfix，三件套齐全 0 diagnostics）：**A `formula-engine-unification`**（feature，4套求值器→单内核+审计收口哈希链，4阶段19任务）/ **B `retrieval-kernel-unification`**（feature，检索3套→单内核+pgvector+知识文件入网，3阶段12任务）/ **C `doc-level-ai-chat`**（feature，文档级LLM对话，**依赖B**，4阶段12任务）/ **D `report-config-baseline`**（feature，报表主模板回填+克隆stale通知，3阶段11任务）/ **E `wp-ai-review-ux-fix`**（bugfix，复核显底稿编号+接useCellLocate，8任务）/ **F `global-modules-cleanup`**（bugfix，地址库澄清+33MB死文件+模板JSON→registry+懒建表，10任务）
- 用户拍板**全部 7 个按梯队顺序 A→B→C→D→E→F→G 实施**；依赖链仅 B→C；**全部 7 spec 已实施完成（2026-06-01）**
- **✅ A `formula-engine-unification` 已实施完成（2026-06-01）**：19 任务全绿；核心产出=L1 单内核(formula_engine.py 递归下降 AST+FunctionRegistry 14 函数)+L2 编排(report_engine 委托) PBT 全绿
- **✅ B `retrieval-kernel-unification` 已实施完成（2026-06-01，110 测试全绿 R1~R4 PBT + 零回归）**：阶段1 删 B（KnowledgeService deprecated 限期 2026-07-01）+ 阶段2 IndexSource 注册表+KnowledgeDocSource+semantic_search scope/user+CRUD 联动钩子+reference_doc_service 改调 + 阶段3 VectorStore Protocol+PgVectorStore(pgvector ivfflat)+feature flag(`VECTOR_STORE_BACKEND=pgtext|pgvector`)+ADR-RETRIEVAL-001
- **✅ C `doc-level-ai-chat` 已实施+UAT 通过（2026-05-31）**
- **✅ D `report-config-baseline` 已实施完成（2026-06-01）**：11 任务全绿；核心产出=V040 迁移(report_config_baseline 表+is_stale 列)+ORM+4 service 方法(suggest_to_master/review_candidate/diff_vs_master/apply_master_update)+EventBus REPORT_CONFIG_MASTER_UPDATED+_mark_cloned_configs_stale handler+覆盖率 CI 脚本+6 API 端点+前端 ReportConfigBaselineTab+ADR-REPORT-CONFIG-001；E1~E4 PBT 全绿；**修复联动断裂③**
- **✅ E `wp-ai-review-ux-fix` 已实施完成（2026-05-31）**：C1 卡片底稿编号 el-tag + C2 useCellLocate 接线 + C3 复核按钮底稿名；36 vitest 全绿
- **✅ F global-modules-cleanup 已实施完成（2026-06-01，35 测试全绿）**：删 33MB L1 死文件 + V1/V2 命名澄清 + sync_registry_from_json 联动 + 枚举注释修正 + V040 迁移
- **✅ G global-modules-p2-polish 已实施完成（2026-06-01，57 测试全绿）**
- **UAT 修复**：`services/apiProxy.ts` 缺 `apiProxy` named export 致前端白屏（5 个组件 import `{ apiProxy }` from services 路径）→ 已加兼容别名 `export const apiProxy = api`
- **7 spec 跨 spec 一致性复盘修正 2 偏差（2026-05-31）**：①🔴 spec G content_text 提取工具引用错——`wp_document_recognizer` 实为 LLM 结构化凭证字段提取(DocType.VOUCHER 返结构化字段)**不产全文**，改为 `mineru_service.recognize_for_ocr`(返 `{"text":全文}`)/`unified_ocr_service.recognize` ②🔴 spec D 审计 event_type 歧义——"复用 formula-engine 哈希链收口"被误读会把报表配置变更记成公式变更，澄清为复用 `append_audit_log` 机制但用**独立 event_type `report_config_changed`**(非 A 的 formula_changed)；跨 spec 协调点核查通过=B↔C semantic_search 签名一致 / A↔G FormulaManagerDialog 改不同部分且 G 在 A 后 / E↔C useCellLocate 签名统一；**教训：单 spec 复盘抓不到跨 spec 问题，必须查"工具真实产出物"+"schema 复用边界"**
- **6 spec 三件套复盘实证（2026-05-31，承重锚点全属实，修正 4 处偏差）**：✅ formula_engine.execute/FormulaContext/FormulaResult + amount_resolver Protocol + report_engine.evaluate_formula + knowledge_index_service + report_config_service + GroupNoteTemplateBaseline + useCellLocate + 两懒建表 全 readCode 实证存在；🔴 修正 = ①spec B `incremental_update` 真实参 `source_id`(非doc_id) + `KnowledgeSourceType` 枚举无 `knowledge_doc` 需先加成员 ②spec B `semantic_search(project_id,query,top_k)` 无 scope/user 需新增 + "6类"实为"11类"业务数据 ③spec E `useCellLocate` 真实签名 snake_case `{wp_code,sheet_name,cell_ref,component_type}` 且 component_type 必传(非camelCase) ④spec F 死文件/模板 JSON 真实路径 `backend/data/`(非 backend/app/data/)
- **6 spec 覆盖度核查（2026-05-31，两轮复盘）**：完整覆盖文档 P0+P1 核心（单源/联动/澄清）；**P1-7「公式管理覆盖合并+底稿」已补进 spec A 需求8+task17b**——实证发现 `FormulaManagerScope` 现已有 6 scope（note/consol_note/consol_worksheet/consol_report/report/tb，**合并部分已由 consol Phase2 ADR-205 完成**），仅剩"底稿 workpaper scope"半条（需 readCode 定底稿公式语法域归内核 or cell_formula_evaluator）；**第二轮发现文档优先级自相矛盾**（地址库 Redis 缓存 §一标 P1 但 §九 路线图标 P2）→ 已修正 §一 对齐 P2；**未纳入 6 spec 的全是 P2 体验性能（地址库 Redis/公式时间线 UI/高级查询缓存/note_template DB 化/枚举扩展）+ P3 + 外部依赖（diff 去 mock）+ 已属既存 spec（生成链路 populate_parsed_data 归 wp-generation-pipeline）**，非遗漏；文档 §二十四 固化覆盖度对照表 + 建议 P2 批次另起 `global-modules-p2-polish` spec

### 全局 7 模块盘点 + 多源治理（2026-05-31，文档 `docs/proposals/global-modules-status-and-improvement-2026-05-31.md` 六轮代码实证复盘）
- **7 横切支撑模块**=地址库/公式管理/高级查询/枚举字典/底稿模板库/报告模板库/知识库；ROI 高于合并模块（天天用不卡真实数据）
- **必须单源（删旧代码）**：①公式求值 3 套报表 DSL（formula_engine+report_engine+formula_parser，formula_engine 升级为唯一内核，其余委托/删求值器）②审计留痕 3 处（formula_audit_log 懒建表+core.Log+哈希链 → 只写哈希链）③知识库旧 KnowledgeService（仅 1 处降级调用，删）
- **多源但正交（不合并只澄清）**：地址库 V1(公式编辑目录)/V2(stale 影响图) 正交；formula_unified 实际是底稿 Cell 公式（Excel 语法非报表 DSL，改名 cell_formula_evaluator 保持独立）；note_formula_engine 是 validator 非 evaluator（排除收敛）
- **🔴 3 处联动断裂必修**：①~~知识文件→向量索引~~（✅ 已修 spec B：CRUD 钩子 incremental_update）②底稿模板 JSON→registry（scan 不写 wp_template_registry 表，✅ 已修 spec F）③报表主模板→已克隆项目（update_config 不通知 project:{pid} 克隆，待 spec D）；正解=单一权威源+EventBus 单向派生（平台已有 stale 传播骨架）
- **删旧代码铁律**：删前 grep 0 调用方 + 删前后测试全绿 + 独立 commit+tag 防回滚 + deprecated 超 1 sprint 必删
- **向量存储选型裁定 pgvector**（同库事务一致+零运维+数据量数千条；ChromaDB 现仅 health check 闲置，留 Plan B）；三大内核统一（公式/检索/审计）各立 Design-First spec
- **底稿 AI 复核弹窗 UX 缺陷已修（spec E `wp-ai-review-ux-fix`）**：C1 底稿编号 tag + C2 useCellLocate 接线 + C3 复核按钮底稿名；**已知阻塞：render-config 端点 500（所有底稿均如此，预存后端问题）**→ 待排查修复后可 E2E 实测

## 操作铁律（标题级，详见 #conventions）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册，否则前端 404；FastAPI 不热加载 router（改后需 start-dev.bat 重启）
- **service 只 flush 不 commit**：跨 service 编排的 router 端点各 service 只 flush，router 统一 commit 保原子
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL（jsonb cast/advisory lock/set_config）必加 SQLite dialect 检测
- **历史档案不回填修改**：dev-history / spec-tasks 是 append-only 审计轨迹
- **PowerShell**：写中文/emoji 用 fsWrite（禁 `-replace`/`Set-Content` 处理中文会乱码，用 `python -c read_text/write_text`）；长 commit msg 用 `git commit --% -m "..."` 后不接 `;`；读中文输出先 `chcp 65001 + [Console]::OutputEncoding=UTF8`
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend；大块结构删除用临时 python 脚本动态定位边界
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；但 `http.get/post`（utils/http）返完整响应体需 `.data`
- **ReviewStatusEnum 等枚举成员核对**：引用前用 `python -c "getattr(Enum,'X','MISSING')"` 实证大小写（小写 draft/approved），不信测试与代码哪个对
- **xfail 标"production code bug"= 根因修复信号**：先验证真实定义，修根因后去 xfail 让其真实通过，不留假绿
- **merge 跨阶段签名变更必 grep 调用方**：sync↔async 改 / 删公开方法时全仓 grep 调用点同步改（单阶段 mock 测试全绿不代表跨阶段不断裂）
- **改动后必 Playwright 实测**（运行时 bug 单测/getDiagnostics 抓不到，如包装体解包/CSS 样式孤儿）；改动前后 6 维 git 核查
- **hypothesis PBT 调速**：max_examples 5（用户 2026-06 明确要求降速，禁默认 100）
- 详细规约（UI 视觉 17 条 / ESLint AST / 测试 fixture / 启动 lifecycle / CI 卡点 / EventBus / 中间件 等）→ `#conventions` + `#dev-history`

## 关键引用指南
- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，体量符合参考文档定位**无需裁剪**（dev-history 还是 append-only 审计轨迹）
- 技术事实 / 端点速查 / PG schema / spec 历史详细 → `#dev-history` grep 关键词
- 架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 视觉补充 / 操作铁律详解 / PG 运维 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`
- 合并模块完整体检 → `docs/proposals/consolidation-module-status-and-proposal.md`
- 全局 7 横切模块盘点 + 多源治理 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`（六轮复盘 + 三大内核统一 + 单源/联动裁定）
