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
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：所有用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；不接入 i18n 硬编码 + ESLint 卡点
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
- **D6 MigrationRunner 是运行时迁移**（不是 alembic）：启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞名字母序靠后者静默丢失）
- **真实 PG 数据**：5 项目多为 standalone，**0 个 consolidated 项目**（合并模块真实 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全
- **本地 PG schema 漂移已修**（commit 508393da，965→critical=0）：drift detector 用 pkgutil walk import 全 model 子模块 + 过滤 Metabase 共库污染 + health 按 critical_count（orm_extra+enum_mismatch）判 degraded

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
- 当前分支 `spec/global-modules-AD-implementation`，已 push origin（HEAD `1fe58697`，55 files +8496/-573）；基于 main `0dae057c`；待 PR 合入 main
- 内容：spec A（formula-engine-unification 19 任务）+ spec D（report-config-baseline 11 任务）全量实施
- 历史已闭环：合并模块 Phase0~3 全在 main / 底稿模块 14 spec 已实施归档 / schema drift 三层修复 / git 治理 spec（GIT_MODE 双模式 + 分支命名 hook + 6 维核查 CLI `check_git_sync_state.py`）

### 已完成 spec 总览
- 详见 `.kiro/specs/INDEX.md`（active + _archive 10 分类）；归档/状态核实必须 grep/fileSearch 实证产物存在，不信 README/INDEX 自述
- active = `consol-note-three-level-drilldown`（stub 待真实合并数据）+ **全局模块 7 spec（A formula-engine-unification/B retrieval-kernel/C doc-level-ai-chat/D report-config-baseline/E wp-ai-review-ux-fix/F global-modules-cleanup/G global-modules-p2-polish，A→G 顺序待实施）** + frontend-consistency-m1（merge 带入）；**合并四阶段已归档 `_archive/09-consolidation-phases/`**；底稿模块 13 spec + V3 + 附注 spec + 11 审计循环 + phase1~8 全已归档

### 真正待办（外部依赖）
- LLM 真实接入（6 stub 引擎 `WP_AI_SERVICE_ENABLED` 一键切换）/ 6000 并发压测（Locust+真 PG 大数据）/ 钉集成 / 合并模块真实集团数据 UAT

### 全局 7 模块改进 6 spec 三件套已建（2026-05-31，待实施）
- 据盘点文档生成 6 个 active spec（全 Design-First/bugfix，三件套齐全 0 diagnostics）：**A `formula-engine-unification`**（feature，4套求值器→单内核+审计收口哈希链，4阶段19任务）/ **B `retrieval-kernel-unification`**（feature，检索3套→单内核+pgvector+知识文件入网，3阶段12任务）/ **C `doc-level-ai-chat`**（feature，文档级LLM对话，**依赖B**，4阶段12任务）/ **D `report-config-baseline`**（feature，报表主模板回填+克隆stale通知，3阶段11任务）/ **E `wp-ai-review-ux-fix`**（bugfix，复核显底稿编号+接useCellLocate，8任务）/ **F `global-modules-cleanup`**（bugfix，地址库澄清+33MB死文件+模板JSON→registry+懒建表，10任务）
- 用户拍板**全部 6 个按梯队顺序 A→B→C→D→E→F 实施**；依赖链仅 B→C
- **✅ A `formula-engine-unification` 已实施完成（2026-06-01）**：19 任务全绿（Task 19 Playwright 代码已写待环境实测）；核心产出=L1 单内核(formula_engine.py 递归下降 AST+FunctionRegistry 14 函数)+L2 编排(report_engine 委托)+L3 取数(NoteResolver/WPResolver/DisplayResolver)+审计哈希链收口(formula_changed schema)+cell_formula_evaluator 改名+ADR-FORMULA-001+AddressValidator Protocol+FormulaManagerScope workpaper scope；Q1~Q5 PBT 全绿
- **✅ D `report-config-baseline` 已实施完成（2026-06-01）**：11 任务全绿（Task 11 Playwright stub 待环境）；核心产出=V040 迁移(report_config_baseline 表+is_stale 列)+ORM+4 service 方法(suggest_to_master/review_candidate/diff_vs_master/apply_master_update)+EventBus REPORT_CONFIG_MASTER_UPDATED+_mark_cloned_configs_stale handler+覆盖率 CI 脚本+6 API 端点+前端 ReportConfigBaselineTab+ADR-REPORT-CONFIG-001；E1~E4 PBT 全绿+5 集成测试；**修复联动断裂③（update_config→克隆项目 stale 通知）**
- **下一步 = B `retrieval-kernel-unification`**（A→B→C→D→E→F→G 中 A/D 已完成）
- **🟡 spec A 实施后遗留技术债（复盘 2026-06-01）**：P0=`_PARSE_MODE` 默认切 `"ast"`+修 `safe_eval_expr` float 中间态（commit 前做）；P1=`report_engine._generate_report` 内部求值仍走 ReportFormulaParser 未收口 L1（并入 spec G）；P2=`formula_parser.py` FormulaEvaluator 标 deprecated/改名（spec F）；P2=NoteResolver/WPResolver 缺集成测试（spec B 时顺带）；P3=ADR-FORMULA-001 补底稿语法域裁定段落
- **第 7 个 spec G `global-modules-p2-polish` 已建（2026-05-31，实现文档 100% 覆盖）**：收口全部 P2/P3 = 地址库 Redis 二级缓存 + 地址校验接公式保存流 + 公式变更时间线 UI(依赖A) + 高级查询 Redis 缓存+流式导出 + 枚举扩展业务枚举(EliminationEntryType/审计循环代号/风险等级，与F协调) + enum_dict_overrides 入 D6 + content_text 填充(保障B向量索引) + note_template DB 化(标`*`评估后做)；design-first/feature，4阶段11任务 0 diagnostics；**A~F 落地后启动**；承重锚点实证（AddressRegistryService._slots+invalidate / validate_formula_refs / EliminationEntryType / disclosure_engine._load_templates / wp_document_recognizer / time_machine_service 全在）；**7 spec 实现盘点文档改进项 100% 覆盖，唯一例外=国企/上市 diff 去 mock（卡审计师真实数据，外部依赖非工程可独立完成）**；文档 §二十四 对照表已更新
- **7 spec 跨 spec 一致性复盘修正 2 偏差（2026-05-31）**：①🔴 spec G content_text 提取工具引用错——`wp_document_recognizer` 实为 LLM 结构化凭证字段提取(DocType.VOUCHER 返结构化字段)**不产全文**，改为 `mineru_service.recognize_for_ocr`(返 `{"text":全文}`)/`unified_ocr_service.recognize` ②🔴 spec D 审计 event_type 歧义——"复用 formula-engine 哈希链收口"被误读会把报表配置变更记成公式变更，澄清为复用 `append_audit_log` 机制但用**独立 event_type `report_config_changed`**(非 A 的 formula_changed)；跨 spec 协调点核查通过=B↔C semantic_search 签名一致 / A↔G FormulaManagerDialog 改不同部分且 G 在 A 后 / E↔C useCellLocate 签名统一；**教训：单 spec 复盘抓不到跨 spec 问题，必须查"工具真实产出物"+"schema 复用边界"**
- **6 spec 三件套复盘实证（2026-05-31，承重锚点全属实，修正 4 处偏差）**：✅ formula_engine.execute/FormulaContext/FormulaResult + amount_resolver Protocol + report_engine.evaluate_formula + knowledge_index_service + report_config_service + GroupNoteTemplateBaseline + useCellLocate + 两懒建表 全 readCode 实证存在；🔴 修正 = ①spec B `incremental_update` 真实参 `source_id`(非doc_id) + `KnowledgeSourceType` 枚举无 `knowledge_doc` 需先加成员 ②spec B `semantic_search(project_id,query,top_k)` 无 scope/user 需新增 + "6类"实为"11类"业务数据 ③spec E `useCellLocate` 真实签名 snake_case `{wp_code,sheet_name,cell_ref,component_type}` 且 component_type 必传(非camelCase) ④spec F 死文件/模板 JSON 真实路径 `backend/data/`(非 backend/app/data/)
- **6 spec 覆盖度核查（2026-05-31，两轮复盘）**：完整覆盖文档 P0+P1 核心（单源/联动/澄清）；**P1-7「公式管理覆盖合并+底稿」已补进 spec A 需求8+task17b**——实证发现 `FormulaManagerScope` 现已有 6 scope（note/consol_note/consol_worksheet/consol_report/report/tb，**合并部分已由 consol Phase2 ADR-205 完成**），仅剩"底稿 workpaper scope"半条（需 readCode 定底稿公式语法域归内核 or cell_formula_evaluator）；**第二轮发现文档优先级自相矛盾**（地址库 Redis 缓存 §一标 P1 但 §九 路线图标 P2）→ 已修正 §一 对齐 P2；**未纳入 6 spec 的全是 P2 体验性能（地址库 Redis/公式时间线 UI/高级查询缓存/note_template DB 化/枚举扩展）+ P3 + 外部依赖（diff 去 mock）+ 已属既存 spec（生成链路 populate_parsed_data 归 wp-generation-pipeline）**，非遗漏；文档 §二十四 固化覆盖度对照表 + 建议 P2 批次另起 `global-modules-p2-polish` spec

### 全局 7 模块盘点 + 多源治理（2026-05-31，文档 `docs/proposals/global-modules-status-and-improvement-2026-05-31.md` 六轮代码实证复盘）
- **7 横切支撑模块**=地址库/公式管理/高级查询/枚举字典/底稿模板库/报告模板库/知识库；ROI 高于合并模块（天天用不卡真实数据）
- **必须单源（删旧代码）**：①公式求值 ~~3 套~~→**已收口为单内核 formula_engine.py**（report_engine 委托 L1/formula_parser 求值器已删/formula_unified→cell_formula_evaluator 改名独立）②审计留痕 ~~3 处~~→**已收口为唯一哈希链**（formula_audit_log 懒建表已废/core.Log formula_updated 已删/统一 append_audit_log action='formula.changed'）③知识库旧 KnowledgeService（仅 1 处降级调用，删）
- **多源但正交（不合并只澄清）**：地址库 V1(公式编辑目录)/V2(stale 影响图) 正交；formula_unified 实际是底稿 Cell 公式（Excel 语法非报表 DSL，改名 cell_formula_evaluator 保持独立）；note_formula_engine 是 validator 非 evaluator（排除收敛）
- **🔴 3 处联动断裂必修**：①知识文件→向量索引（KnowledgeDocument CRUD 不触发 incremental_update，上传后 AI 搜不到）②底稿模板 JSON→registry（scan 不写 wp_template_registry 表）③~~报表主模板→已克隆项目~~**已修复（spec D，EventBus+handler+is_stale）**；正解=单一权威源+EventBus 单向派生（平台已有 stale 传播骨架）
- **删旧代码铁律**：删前 grep 0 调用方 + 删前后测试全绿 + 独立 commit+tag 防回滚 + deprecated 超 1 sprint 必删
- **向量存储选型裁定 pgvector**（同库事务一致+零运维+数据量数千条；ChromaDB 现仅 health check 闲置，留 Plan B）；三大内核统一（公式/检索/审计）各立 Design-First spec
- **底稿 AI 复核弹窗 UX 缺陷（待修）**：TsjReviewFindings 不显示底稿编号 + SideStandardsTab onLocateCell 只 emit 未接 useCellLocate（wp-locate-foundation 已实现）+ 复核按钮无底稿名；~1 天，并入 `doc-level-ai-chat` 或 `wp-ai-review-ux-fix`

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
- **hypothesis PBT 调速**：max_examples 10~15（禁默认 100）；async+SQLite schema 重建场景必加 `deadline=None, suppress_health_check=[HealthCheck.too_slow]`（单次迭代 ~700ms 超默认 200ms deadline）
- **spec 三件套改进（D 复盘）**：①design.md 加"边界条件与冲突处理"段落（哪怕 V1 不处理也显式声明）②跨前后端任务必须拆为纯后端+纯前端两个子任务（避免 Task 9 式大任务）③集成测试至少一条走真实 EventBus 分发路径④"仿成熟范式"策略优先：先找系统中最接近的已有模式映射，再补差异
- 详细规约（UI 视觉 17 条 / ESLint AST / 测试 fixture / 启动 lifecycle / CI 卡点 / EventBus / 中间件 等）→ `#conventions` + `#dev-history`

## 关键引用指南
- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，体量符合参考文档定位**无需裁剪**（dev-history 还是 append-only 审计轨迹）
- 技术事实 / 端点速查 / PG schema / spec 历史详细 → `#dev-history` grep 关键词
- 架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 视觉补充 / 操作铁律详解 / PG 运维 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`
- 合并模块完整体检 → `docs/proposals/consolidation-module-status-and-proposal.md`
- 全局 7 横切模块盘点 + 多源治理 → `docs/proposals/global-modules-status-and-improvement-2026-05-31.md`（六轮复盘 + 三大内核统一 + 单源/联动裁定）
