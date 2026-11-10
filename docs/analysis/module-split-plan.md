# 模块拆分方案报告（module-split-plan）

> 分析对象：致同审计作业平台（FastAPI + Vue3 单体）
> 分析日期：2026-11-09
> 输入依据：`docs/analysis/backend-structure.md`、`docs/analysis/frontend-structure.md`、`docs/analysis/data-infra-structure.md`（三份探索报告，本文直接引用其数据，不再重复探索）
> 本文回答四个问题：①现状如何；②有哪些梯度的拆分方案；③推荐方案怎么落地；④gt/sj/sw 三种部署形态能否支持「同一代码库按需组装」。

---

## 1. 现状总结（一页概述）

### 1.1 系统形态：单一 FastAPI 进程 + 单库 + 胖前端

| 层 | 规模 | 组织方式 |
|---|---|---|
| 后端 `backend/app/` | 3,086 个 py / ≈103.2 万行 | routers 870 + services 1,969 + models 114 + schemas 34，扁平命名 + 少量子包；技术基建层（core/middleware/security/workers/router_registry）113 文件 ≈2.2 万行 |
| 前端 `audit-platform/frontend/src/` | ≈8,700 文件（.vue 2,523 + .ts 6,175） | components 7,480（87% 集中在 workpaper 巨域）、composables 529、views 357（薄页面层）、stores 11 个（仅 3.3k 行） |
| 数据 | 单 PostgreSQL 库、单 `public` schema、251 张表 | 自研 MigrationRunner 启动自动应用 V001–V260 共 255 个迁移；R 回滚脚本仅 200/255 配对 |
| 后台 | 进程内 21 个 worker（leader lock）+ 独立 OCR 旁挂服务(:9990) | 无微服务；容器只承担 PG/Redis/OnlyOffice/Metabase 等基础设施 |

后端聚为 **19 个业务域**，最大域 wp_core（底稿）43.4%（44.8 万行）；前端聚为 **11 个路由域**（`router/domains/`，有契约测试锁定），最大巨域 components/workpaper 6,545 文件。

### 1.2 部署形态 gt / sj / sw：同一代码库的分支隔离部署

三套 `docker-compose.{gt-plan,sj-plan,sw-plan}.yml` 均为基础 compose 的 **override**，只改容器名/卷/端口/库名（`audit_platform` / `audit_platform_sj` / `sw_audit_platform`），跑同一套迁移。gt=主线 dev1.0，sj=sj-dev1.0 分支隔离环境，sw=税务 demo 分支。后端日常开发在宿主机（`start-dev.bat` :9980/:3030）。**"一份代码 + override + 分支隔离"是拆分方案必须保持的前提。**

### 1.3 共享内核（拆分前必须先固定）

| 类别 | 内容 | 引用强度 |
|---|---|---|
| 核心实体 | `models/core.py`（User/Project/ProjectUser/Log/Notification/Department）+ `models/base.py` | 被 771 个后端文件（25%）引用；DB 层 users/projects 被 58/82 个模型文件挂 FK，迁移中 REFERENCES 140+127 处 |
| 依赖注入 | `deps.py`（认证 + DB session + require_project_access） | ~650 文件直接 import |
| 事实共享模型 | `workpaper_models.py`(1,162行)、`audit_platform_models.py`(1,462行)+schemas、`collaboration_models.py`、`attachment_models.py` | 各被 8+ 个域 import——**名义属业务域，实为第二共享内核**，按目录归域会产生循环 import |
| 前端共享层 | utils（http/eventBus/sse）、全局 5 个 store、components/common+attachment | utils/eventBus 851 行全局事件总线；composables/ 被底稿域渗透（47 个科目专用 composable、88 处引用 workpaper 组件） |
| 文件数据平面 | `backend/data`(133MB 种子/契约)、`wp_templates`(59MB 模板)、`definition_store`(40MB 内容寻址 blob) | 被底稿/报告/ACNR 域运行时强依赖，是"第三数据平面" |

### 1.4 耦合热点 Top 5（拆分阻力从大到小）

1. **wp_core 是"神域"（星型拓扑中心）**：出边 cycle(294)/qc(144)/ai(141)/ledger(102)，入边 docs(99)/cycle(94)/qc(80)/note(67)/project(66)/ai(64)/report(62)。底稿是全平台工作载体，任何拆分都绕不开。
2. **技术基建反向依赖业务**：core_infra→wp_core 306 次/20 文件（deps.py 内嵌底稿权限语义、startup_registry 组装根挂 ~15 域、audit_log_middleware import 业务模型、wopi 依赖 wp_visibility 门禁）。
3. **事实共享模型散落业务目录**（见 1.3）——按目录归域会立即循环依赖。
4. **note↔report↔consol 三角**经 `report_models`/`report_note_linkage` 焊接（合并/单体共用"报表→附注→导出"管线）；DB 层 V246 甚至存在 report↔consol **双向外键**。
5. **渲染策略焊死 wp 与 cycle_engine**：`routers/wp_render_strategies/`（380 文件）位于 routers/ 下实为渲染库，构成 wp_core→cycle_engine 294 次出边的主体。

前端侧对应障碍：workpaper 巨域内部 110 个科目目录交叉依赖 3,222 个域内 composables；无 import 边界 lint（composables→components 49 文件、components→views ~10 处、utils→components 6 处）；components.d.ts 自动注册 2,447 组件使依赖失真；全量 vue-tsc 需 40GB 堆否则 OOM。

### 1.5 已有可放大的解耦资产

- **event_bus**（进程内 asyncio + Redis Stream 持久化）+ 各域 handler：调整分录→试算重算等 6 类联动已走事件；
- **outbox 模式**：import_event_outbox / formula_runtime_outbox / consol_operation / event_outbox_dlq；
- **ACNR 目录快照**（附注-科目映射解耦）、**workpaper_sync digest 契约**（ContractDriftError）；
- **tools/audit-data-mcp**：零 DB 直连、经 REST + scoped token 的域间访问边界示范；
- **旁挂服务先例**：OCR(:9990)、OnlyOffice、vLLM GPU profile 均为 compose profile 开关；
- 前端 **router/domains 真源 + 契约测试**、**services/apiPaths/ 域化模板**、manualChunks 防循环经验。

---

## 2. 候选拆分方案（三个梯度）

### 方案 A：单体内部模块化（modular monolith）

**做法**：仓库与部署形态完全不动。后端将 `app/` 重排为 `app/{kernel, platform, domains/<域>}/` 包结构；前端保持单包，但建立目录边界规则。两侧均用工具强制 import 约束（import-linter / dependency-cruiser），路由注册改为域声明式清单。

| 维度 | 评估 |
|---|---|
| 改动量 | **小~中**：后端 git mv 重排 + deps/startup_registry/路由校验器改造 + lint 配置；前端只加 lint 与少量搬移（47 个科目 composable 归位）。估算 2~3 人月 |
| 风险 | **低**：不动部署、不动数据层、不动构建链；每步可独立 PR、可 git revert |
| 收益 | 边界显式化、防止继续劣化、为 B/C 铺路；包级归属使"谁能依赖谁"变成机器检查 |
| 局限 | 不解决前端 typecheck OOM（单 tsconfig 全量检查依旧）；不解决资源隔离 |
| 适用场景 | 立即可做；团队规模不变、无独立伸缩诉求时的保底方案 |

### 方案 B：monorepo workspace 化

**做法**：在 A 的基础上，把仓库重组为 workspace：前端 pnpm workspace 按域拆 package（`packages/kernel-ui`、`packages/workpaper`、…），`tsconfig project references` 分域类型检查；后端域包作为独立顶层包（`app/domains/*` 已是 Python package 边界）；共享内核独立成包（后端 `app/kernel/`、前端 `packages/kernel-ui`）。仍是**单仓、单进程部署**。

| 维度 | 评估 |
|---|---|
| 改动量 | **中**：= 方案 A + pnpm workspace 改造 + components.d.ts 按域收敛 + manualChunks 按包 + 构建链调整。估算 6~9 人月（含 A） |
| 风险 | **中**：构建链改造面广（vite/tsconfig/unplugin），components.d.ts 与自动导入需同步；但无运行时架构变化，数据层零改动 |
| 收益 | ① 根治 vue-tsc 40GB 堆 OOM（project references 分域检查）；② 构建按域增量、manualChunks 按包；③ pnpm 严格依赖声明 = 天然 import 门禁；④ 包级复用与并行开发；⑤ 为"按需组装"（见 §4）提供载体 |
| 局限 | 单进程内仍是模块调用；不做资源隔离 |
| 适用场景 | 单团队、前端工具链已到极限、需要长期可持续的边界治理——**与本项目现状最匹配** |

### 方案 C：按域拆服务（微服务化）

**做法**：把适合独立进程的域拆为服务。按三份报告的证据，适合先拆的是**重资源、低频交互、已有旁挂先例**的域：AI 推理/向量检索（ai_llm，GPU profile 已有）、文档转换/导出（docs_office，LibreOffice/OnlyOffice 重资源）、OCR（已是独立服务）、知识检索（knowledge，pgvector 独立性强）。其余域强耦合（审计作业内核八域约 80 万行通过 workpaper_models/report_models/事件强联动）不适合拆。

| 维度 | 评估 |
|---|---|
| 改动量 | **大且持续**：每抽一个域 = API 契约设计 + 数据访问改写 + 部署编排 + 可观测性 + 跨服务一致性。每域 2~4 人月，且运维面永久扩大 |
| 风险 | **高**：① 路由发现/启动组装/`_validate_registry_completeness` 假设单进程全量扫描，跨服务失效；② 单库跨域 FK 20+ 组（含 report↔consol 双向）拆库需全部降级为应用层引用；③ users/projects 中心辐射 267 处 FK，任何域都拖着身份/项目服务；④ 迁移启动锁、worker leader lock、SSE 注册表均假设单进程；⑤ R 脚本缺 55/255，回退只能靠快照 |
| 收益 | 资源隔离（GPU/大内存）、独立伸缩、故障隔离、独立发布节奏 |
| 局限 | 单团队下收益不抵复杂度；event_bus→跨服务事件、deps→RPC 的改写量大 |
| 适用场景 | 仅重资源域按需触发；或未来组织拆分为多团队时 |

### 2.4 对比与推荐

| 维度 | A 单体模块化 | B monorepo workspace | C 按域拆服务 |
|---|---|---|---|
| 改动量 | 小（2~3 人月） | 中（6~9 人月） | 大（每域 2~4 人月 + 永续运维） |
| 风险 | 低 | 中 | 高（数据层 FK 网 + 路由机制 + 迁移体系三重失效） |
| 收益 | 边界显式化、防劣化 | +治 OOM、构建按域、按需组装载体 | +资源隔离、独立伸缩 |
| 数据层改动 | 无 | 无 | 拆库需降级 20+ 组跨域 FK |
| 解决前端 40GB OOM | ✗ | ✓ | 无关 |

> ### ✅ 推荐结论：**方案 B（monorepo workspace 化）为目标形态，以方案 A 作为其第一阶段实施路径，方案 C 仅对重资源旁挂域按需触发，数据库不拆库。**
>
> 简言之："**A 先行、B 成型、C 按需**"。理由：
> 1. 前端 vue-tsc 40GB 堆 OOM 是已发生的工程事故级痛点，只有 pnpm workspace + project references 治本——A 治不了，C 与之无关，只有 B 能解决；
> 2. 后端审计作业内核八域约 80 万行强联动 + 单库 20+ 组跨域 FK（含双向）+ users/projects 267 处 FK 辐射，全量服务化（C）成本极高而单团队收益低；但包级分区（A）是一切方案共同的前提，且风险最低；
> 3. gt/sj/sw 的部署本质是"同一代码库 + compose override"，monorepo 的 workspace/包结构天然兼容该工作流，并首次提供了"按需组装"的显式载体（详见 §4）；
> 4. 平台已有 event_bus/outbox/OCR 旁挂/scoped-token 网关四类解耦资产，C 不必一次到位，可作为 B 之上按触发条件逐域启用的增强。

---

## 3. 推荐方案（B）的具体落地

### 3.1 统一域清单（13 域 + 共享内核 + 技术基建）

> 后端域由 19 个业务域归并而来（note/report/consol 合并为一个"报表附注合并管线"域；qc+eqcr 合并；confirmation+evidence_governance+esign 合并；cycle_engine/adjust/formula 并入底稿内核）；前端目录按 `router/domains/` 真源 + components 聚类映射；表前缀取自迁移文件与 `__tablename__`。

| # | 域 | 后端来源（routers/services/models） | 前端目录 | 表前缀 | 后端规模 | 拆分批次 |
|---|---|---|---|---|---|---|
| K | **kernel 共享内核** | `models/base.py`、`models/core.py`、`audit_platform_models+schemas`（留痕契约）、`attachment_models`、`asset_blob_models`、`schemas/common*`、`deps.py` 拆解（auth_core/project_access）、`services/_decimal_helpers` 等 | `packages/kernel-ui`：stores/{auth,project,dict,roleContext,displayPrefs}、utils/{http,eventBus,sse,confirm,crossWindowAuth,clientInstance}、components/{common,attachment,grid}、shared/contracts | users、projects、project_users、sys_dept、logs、notifications、attachments*、asset_blobs、app_audit_log | ~0.1 万行 + 契约 | Phase 1 |
| P | **platform 技术基建** | `core/ middleware/ security/ api/ workers/ router_registry/ permissions/ main.py` | —（构建/壳层） | schema_version、platform_jobs、event_outbox* | 2.2 万行 | Phase 1 |
| D1 | **workpaper 底稿内核**（wp_core + cycle_engine + adjust + formula） | wp_* 489 routers、cycle 53、adjustment 13；services 710+121+35；`workpaper_models`、`workpaper_sync_models`、`formula_*`、`adjustment_*`；**`wp_render_strategies/`（380 文件）从 routers/ 迁入本域** | `packages/workpaper`：components/workpaper（6,545，内部分层 shell/kit/headless/cycles/composables）、components/{formula,adjustment}、shell/、views/workpaper-editor+workpaper-list | working_paper*、wp_*、formula_*、adjustments、科目表 m1~m10/l1~l8/n1~n5/h5~h9 | ~52.3 万行 | Phase 3 |
| D2 | **ledger 账套数据** | ledger_*/dataset_*/import_*/account_* 27r/179s/5m；子包 import_engine/ledger_import/bulk_tab | `packages/ledger`：components/{ledger-import,trial-balance,ledger,query,custom-query}、views/ledger | trial_balances、tb_ledger、ledger_datasets、import_batches、import_event_outbox、account_packages、t_account | 7.2 万行 | Phase 3 |
| D3 | **report_note_consol 报表附注合并管线**（report + note + consol） | report_*/note_*/disclosure_*/a17/b60/consol_*/goodwill 72r/341s/25m；`report_models` 定为管线契约；子包 acnr/ | `packages/report-suite`：components/{notes,report,consolidation,disclosure} | financial_report、report_*、disclosure_notes、note_*、consol_* | 14.7 万行 | Phase 3 |
| D4 | **qc_review 复核质控**（qc + eqcr） | qc_*/review_*/gate/checklist/consistency/phase10/phase14 + eqcr/ 子包 68r/144s/18m | `packages/qc`：components/{qc,review,eqcr,trust,collaboration}、views/qc | qc_*、review_*、eqcr_*、checklist_*、editing_locks、independence | 6.9 万行 | Phase 2(qc 部分)/3 |
| D5 | **ai_llm AI 能力** | ai_*/llm_*/ocr/semantic/vector + ai_chat/、auto_data_resolvers/ 23r/112s/4m | `packages/ai`：components/{ai,ai-chat} | ai_chat_*、ai_model_config、ai_task_jobs、ai_content_log | 5.2 万行 | Phase 3（服务化候选） |
| D6 | **docs_office 文档导出** | word/docx/pdf/excel/onlyoffice/wopi/libreoffice + wp_export/wp_conversion 16r/58s | —（无独立 UI） | export_task、wp_export_* | 3.0 万行 | Phase 3（服务化候选） |
| D7 | **project 项目协作**（含 procedure） | project_*/deliverable_*/task/workflow/rotation/materiality/risk/procedure/sampling/cutoff/phase15 39r/103s | `packages/project-suite`：components/{deliverable,dashboard,wizard}、views、router/domains/projects | procedure_*、deliverable、rotation、materiality、phase15 任务树 | 4.5 万行 | Phase 2~3 |
| D8 | **evidence_confirmation 取证函证**（confirmation + evidence_governance + esign） | confirmation_*/pbc/evidence_governance//signatures 22r/25s | `packages/confirmation`：components/confirmation | confirmations、evidence_*、signatures | ~1.2 万行 | Phase 2 |
| D9 | **knowledge 知识指引** | knowledge_*/guidance_*/citation/reference/regulatory 6r/27s | handbooks 相关视图 | knowledge_*、guidance_*、template_library | 1.5 万行 | Phase 2（服务化候选） |
| D10 | **archive 归档** | archive_*/recycle/version/time_machine/phase16/legal_hold 10r/20s | time_machine/version 组件 | archive_* | 0.8 万行 | Phase 2 |
| D11 | **notify_event 通知事件** | notification_*/event_*/dispatch/forum/sse/outbox 8r/14s | — | notifications、event_* | 0.7 万行 | Phase 2 |
| D12 | **iam 身份权限** | user_*/role_*/staff/partner/permission/department/sod/workhour/temporary_grant 21r/28s | router/domains/auth | sys_role、sys_role_project、staff_members、workhour_entries、temporary_grants | 1.5 万行 | Phase 2 |
| D13 | **system 系统管理** | system_*/sys_*/admin/feature/i18n/health/platform/metabase/background_jobs 18r/47s | `packages/system`：components/system、router/domains/system | feature_flags、shared_config、background_jobs | 2.0 万行 | Phase 2 |

**归属裁决（三份报告中的争议件）**：

- `workpaper_models.py` **不进 kernel，定死在 D1**。它是 D1 的领域模型，"被 8 域引用"是历史欠账；解法是收窄外部依赖到两个契约（`wp_visibility` 底稿读写门禁 + ACNR/快照类模型快照），而非把它提升为共享内核——否则 kernel 会被 43% 的代码拖着走。
- `audit_platform_models.py`（审计留痕 + EventPayload 事件契约）**进 kernel**——它是事件总线的负载契约，属平台语义。
- `collaboration_models.py`（编辑锁/评论）先放 kernel 观察：中间件与多域引用，拆分后按实际引用面决定归 D4 或 D1。
- `attachment_models + asset_blob_models` 进 kernel（跨域不可变资产）。
- 前端 `components/attachment`（被 workpaper 引用 270 次）与 `grid` 升格为 kernel-ui 共享件；`components/adjustment`（被引用 163 次）归 D1。
- 40+ 个前端碎目录按表逐一对号入座；实在无归属的先进 kernel-ui 的 `misc/` 并登记待决。

### 3.2 共享内核抽取清单（kernel 包内容）

| 层 | 抽入 kernel 的内容 | 留在域内的内容 |
|---|---|---|
| 后端实体 | base.py（Base/AuditMixin/SoftDeleteMixin/枚举）、core.py（User/Project/ProjectUser/Log/Notification/Department）、attachment_models、asset_blob_models | 各域领域模型（含 workpaper_models→D1） |
| 后端契约 | audit_platform_models+schemas（EventPayload/EventType 审计留痕）、schemas/common/_common/core（分页/通用响应） | 各域 schemas |
| 后端会话/鉴权 | deps.py 拆解：`get_current_user`/JWT+Redis 黑名单/DB session → `kernel.auth`；`require_project_access` 收窄为"项目成员校验"→ `kernel.project_access`（**底稿级权限语义归还 D1 的 wp_visibility 门禁**） | 各域专属 gate（`_wp_gate` 留 D1，`dedicated_wp_gate` 留 cycle 注册器） |
| 后端工具 | _decimal_helpers/_zh_tokenize/retry_utils/fast_writer/query_cache | — |
| 事件契约 | event_bus 客户端 + EventPayload schema + outbox 基类 | 各域 handler |
| 前端基础设施 | utils/{http,eventBus,sse,confirm,crossWindowAuth,clientInstance} | 域内 utils |
| 前端状态 | stores/{auth,project,dict,roleContext,displayPrefs}（全局 5 个） | addressRegistry/guidancePanel→D1、chatRunState→D5、wizard/drilldown/collaboration→所属域 |
| 前端 UI | components/{common(Gt* 套件),attachment,grid}、shared/contracts、layouts | 域内组件 |

### 3.3 分阶段迁移路线（每阶段独立交付、独立回滚）

**Phase 0 — 基线固定（1~2 周）**
- 产出后端 import 依赖图基线（复用探索者脚本）与前端 dependency-cruiser 依赖图基线；
- 引入 import-linter + dependency-cruiser 配置进 CI，**先 report 模式（只记录不阻断）**，冻结"新增上行依赖"；
- 交付物：依赖基线报告 + lint 配置 + CI 任务。回滚：纯增量，无风险。

**Phase 1 — 止血与内核固定（2~4 周）**
- 后端：`deps.py` 拆解进 `app/kernel/`（**保留 `app.deps` 兼容 re-export**，650 处引用零改动）；`audit_log_middleware` 改依赖 kernel 契约；`phase10~16_*.py` 模型按真实归属重命名迁移（phase10=复核、12=AI、13=报表、14=门禁、15=任务树、16=取证包）；
- 前端：三条上行禁令转 error（composables→components、components→views、utils→components，共 65 处修复）；47 个科目专用 composable 迁入 `components/workpaper/composables/`；
- 交付物：backend `app/kernel/` + frontend `packages/kernel-ui` 雏形 + 上行依赖清零。回滚：re-export 兼容层随时可退。

**Phase 2 — 小域先行，验证拆包流程（4~6 周，每域一周）**
- 后端 8 个低耦合域按依赖从少到多迁入 `app/domains/<域>/`：esign → confirmation(+evidence) → notify_event → system → iam → knowledge → archive → eqcr（合计约 7.7 万行）；
- 路由注册改造：`router_registry` 增加**域声明式清单**（每域 `__init__.py` 导出 `routers`/`handlers`/`workers`），`_validate_registry_completeness` 改为按清单校验，`startup_registry` 改为各域自声明 + 汇编器模式；
- 前端：auth/system/extension/workhour/eqcr/dashboard 等无争议域 → `packages/*`；拆解 `commonApi.ts`（2,381 行）到 apiPaths 域文件；
- import-linter 对已迁域启用 forbidden **硬约束**（error）。
- 交付物：8 个后端域包 + 5~7 个前端包，逐域独立 PR。回滚：单域 git revert 即可。

**Phase 3 — 内核分区（8~12 周，最大工作量）**
- 后端 D1：`wp_render_strategies/`（380 文件）移出 routers/ → `domains/workpaper/render_strategies/`，以"渲染策略注册表"契约收敛 wp→cycle 的 294 边；`workpaper_sync` 独立子模块；wp_core 内部按 wp_fill/wp_scripts/wp_visibility/workpaper_sync/formula_runtime 分层；
- 后端 D3：以 `report_models` 为管线契约封口 note↔report↔consol 三角（域内自由引用，域外只经契约出口）；
- 前端 D1：workpaper 巨域内部分层 shell(框架)/kit(基础件)/headless(registry)/cycles(110 科目目录)/composables(域内共享)；`components.d.ts` 按域 resolver 收敛；`main.ts` 启动副作用显式化为各包 `init()` 协议；
- 交付物：D1~D7 域包全部成型（仍单进程部署）。回滚：按包 revert；此阶段不动 schema。

**Phase 4 — monorepo 成型（4~8 周）**
- pnpm workspace + `tsconfig project references`（**根治 40GB 堆 vue-tsc OOM**，删除 10 份 `tsconfig._*.json` 残留与 region typecheck 工具）；
- 后端目录定稿 `app/{kernel,platform,domains/*}/`（git mv 保留历史）；
- vite `manualChunks` 从"按 node_modules"改为"按包"，沿用 `onlyExplicitManualChunks` 防循环；`bundle:check`/`build:verify` 门禁沿用；
- 交付物：monorepo 布局 + 类型检查/构建耗时可量化下降。回滚：workspace 配置单独一个 commit，可整体回退。

**Phase 5 — 按需服务化（长期，触发条件驱动，不预设时间表）**
- 触发条件（满足其一才启动）：① 资源瓶颈（AI GPU 排队、LibreOffice 转换拖垮 web worker）；② 独立伸缩诉求；③ 团队拆分；
- 候选顺序：AI 推理/向量检索 → 文档转换 → 知识检索；
- 每域三步走：先 event_bus/outbox 异步化 → 再 HTTP 契约（**复用 tools/audit-data-mcp 的 scoped token 模式**）→ 最后物理拆分 + compose profile（复用 OCR/OnlyOffice 先例）；
- **数据库不拆库**。若单库出现资源瓶颈，中间态是 PG schema 分域（同库跨 schema FK 可保留、无需两阶段提交），最终态才是拆库 + outbox 对账。

### 3.4 import 约束的工具强制

**后端：import-linter**（`backend/.importlinter`，pre-commit + CI 双跑）：

```ini
[importlinter]
root_package = app

# 分层契约：domains → platform → kernel，禁止逆向
[importlinter:contract:layers]
name = 平台分层
type = layers
layers =
    app.domains
    app.platform
    app.kernel

# kernel 不得反向依赖任何域（startup_registry/router_registry 列入 ignore 组装根白名单）
[importlinter:contract:kernel-independence]
name = 内核无业务依赖
type = forbidden
source_modules =
    app.kernel
forbidden_modules =
    app.domains.*

# 已拆域之间禁止互引 internals（每完成一个域加一条；域间只允许 import 对方 public 契约出口）
[importlinter:contract:domain-report-no-workpaper-internals]
name = 报表域不得引底稿域内部
type = forbidden
source_modules =
    app.domains.report_note_consol
forbidden_modules =
    app.domains.workpaper.internals
```

- 渐进策略：Phase 0 全部 `warn`（CI 报告不阻断）→ Phase 1 kernel 契约转 `error` → Phase 2 起每迁一域即转 `error`；
- 域公共出口约定：每域 `__init__.py` 只暴露 `routers/handlers/契约类型`，域内 `internals/` 子包不可被跨域 import（forbidden 契约逐域登记）。

**前端：dependency-cruiser（规则表达力优先）+ pnpm 严格依赖**（`frontend/.dependency-cruiser.cjs`）：

```js
module.exports = {
  forbidden: [
    { name: 'no-upward-composables-to-components',
      from: { path: '^src/composables' }, to: { path: '^src/components' } },
    { name: 'no-upward-components-to-views',
      from: { path: '^src/components' }, to: { path: '^src/views' } },
    { name: 'no-upward-utils-to-components',
      from: { path: '^src/utils' }, to: { path: '^src/components' } },
    { name: 'pkg-boundary-only-public-api',   // workspace 后生效
      from: { path: '^packages/(?!$1)' }, to: { path: '^packages/([^/]+)/((?!public).*)$' } },
  ],
};
```

- workspace 化后叠加两道天然门禁：**pnpm 未声明依赖不可 import**（phantom dependency 报错）+ `package.json exports` 只暴露 `./public`；
- 配套：`components.d.ts` 按域分片生成（unplugin-vue-components 每包独立 resolver），恢复显式 import 的依赖可见性；
- CI 挂载点：pre-commit（增量）+ CI 全量 + PR 评论违规清单。

### 3.5 风险与回滚

| # | 风险 | 缓解 | 回滚手段 |
|---|---|---|---|
| 1 | `deps.py` 650 处引用断裂 | 拆解后保留 `app.deps` re-export 兼容层，脚本化逐步替换 | 删除 re-export 层即回到原状 |
| 2 | 路由发现机制失效（`_validate_registry_completeness` 全目录扫描、`cycle_engines._inc` 动态门禁、lazy_api_routes/route_index） | Phase 2 改域声明式清单；每域 PR 跑**全量路由快照测试**（移植前端 routeDomainProjection 契约测试思路） | 清单回退 = 域包回退 |
| 3 | `workpaper_models` 落位错误导致循环 import | 定死 D1 不进 kernel；域外依赖走 wp_visibility 门禁 + 模型快照契约 | —（决策性护栏，无回滚需求） |
| 4 | report↔consol 双向外键（V246） | D3 同域同库，拆分前不触碰；未来若拆域先断 `report_generation_run.operation_id` 或 `consol_artifact.report_run_id` 其一 | 同库保留 FK，无影响 |
| 5 | vue-tsc OOM 迁移期恶化 | Phase 4 前沿用 region typecheck 工具过渡；Phase 4 后 project references 根治 | workspace 配置独立 commit 可整体 revert |
| 6 | components.d.ts 分片后自动导入漏注册 | 每包保留 spec 断言组件可解析；分批切换 | resolver 配置按包回退 |
| 7 | eventBus/main.ts 隐式运行时协议断裂 | 启动副作用显式化 `init()` 协议 + 事件契约测试（gc0 先例推广） | init 顺序回归原 main.ts |
| 8 | 迁移回滚纪律缺失（R 配对 200/255，V094 后基本缺失） | **拆分期禁止破坏性 schema 变更**（只加不改）；DB 回退靠快照（workpaper_snapshots/consol_snapshots 模式已有） | 快照恢复 |
| 9 | 长周期迁移与业务并行冲突 | 每阶段独立 PR、独立交付、revert 粒度=包；Phase 2/3 期间冻结 routers/ 根目录新增（新路由必须入域） | git revert 按包 |
| 10 | 未来多服务时的迁移启动竞争 / worker leader lock / RLS | Phase 5 才处理：MigrationRunner 独立为 migrate job（advisory lock 已有）；不拆库则 RLS/漂移检测零影响 | 不拆库即无此风险 |

---

## 4. 特别回答：gt / sj / sw 是否支持「同一代码库按需组装」？

**结论：支持，而且现有架构已经隐含了这种模式；推荐方案 B 会把它从"隐式约定"升级为"显式机制"。**

### 4.1 依据

1. **三形态本就是同一代码库**：gt/sj/sw 的 compose 全是基础文件的 override，只改容器名/卷/端口/库名，跑同一套 V001–V260 迁移。分支隔离发生在 git 层，代码组装发生在部署层——这正是"按需组装"的雏形。
2. **旁挂能力已是 profile 开关**：OCR(:9990)、OnlyOffice、vLLM/vllm-embed/mineru/ollama、paperless 全部是 compose profile，按形态启用/禁用。sw（税务 demo）已经在用这种方式裁剪能力面。
3. **前端路由域有真源**：`router/domains/` 11 个域文件 + 契约测试，天然支持按 profile 过滤注册。
4. **后端有 feature_flags 与注册分组**：`router_registry` 五分组注册 + `api/feature_flags.py`，具备加"组装开关"的挂点。

### 4.2 方案 B 下的三层组装机制（建议显式化）

| 层 | 机制 | 现状基础 |
|---|---|---|
| 代码层（域开关） | `router_registry` 域声明式清单 + `ASSEMBLED_DOMAINS` 环境变量/profile → `main.py` 按清单挂载域路由、注册 handler/worker；未选装的域不 import（配合 lazy_api_routes 已有的延迟加载） | 五分组注册 + startup_registry 改造（Phase 2） |
| 部署层（旁挂开关） | AI 推理/文档转换/知识检索等服务化产物沿用 compose profile；三形态各自决定启用哪些旁挂 | OCR/OnlyOffice/GPU profile 已有 |
| 前端层（路由域开关） | `router/domains` 真源按 profile 过滤 + 未选装域的包不进构建（manualChunks 按包天然支持） | router/domains 契约测试已有 |

### 4.3 约束与注意事项

1. **组装 ≠ 任意裁剪**：Project/User 是全域中心、workpaper 是星型中心——"审计作业内核"（D1–D4）是所有形态的最小必备集。可组装裁剪的对象是旁挂能力（AI/OCR/文档/知识/Metabase）与边缘域（archive/knowledge/notify），不是内核。
2. **域间事件契约必须版本化向后兼容**：组装变体之间（如 sw 不启用 AI 域）不能出现隐式断裂——所有跨域 event_bus 事件要有 schema 版本，消费方对缺失生产方优雅降级（pgvector→pgtext 的降级先例可推广）。
3. **文件数据平面要跟版本走**：`wp_templates`(59MB)/`data`(133MB)/`definition_store`(40MB) 跨分支共享同一份源码，sw 的 `STORAGE_ROOT` 与主线共用已是自认隐患。definition_store 已内容寻址；建议把 workpaper_sync 的 digest 契约（ContractDriftError）扩展覆盖三目录，使"组装变体 × 数据平面版本"可校验。
4. **数据层不受影响**：每形态一库、库内单 schema 的模式与按需组装正交；若未来做 PG schema 分域，三形态各自库内适用同一模式，无需改变分支工作流。
5. **分支工作流保持不变**：monorepo 化不改变"sj-dev1.0 / sw-dev1.0 分支 + override compose"的隔离模型——包结构是仓库内的组织方式，分支照常整库 checkout。

---

## 5. 附：三份输入报告的关键结论索引

| 报告 | 关键结论 |
|---|---|
| backend-structure.md | 103 万行/19 域；wp_core 43.4% 神域；core_infra 反向依赖 306 次；事实共享模型 4 件；8 小域可先拆；内核八域约 80 万行短期整体保留；event_bus/outbox 可放大 |
| frontend-structure.md | 8,700 文件；workpaper 巨域 6,545（87%）；拆分友好度 3/5；router/domains 真源 + store 极少是最大有利项；上行依赖无门禁 + components.d.ts 失真 + 40GB OOM 是最大障碍；不推荐微前端，推荐 pnpm workspace 四步路径 |
| data-infra-structure.md | 单库单 schema 251 表；users/projects 267 处 FK 辐射；跨域直连 FK 20+ 组含双向；255 迁移/R 配对 200/255；gt/sj/sw = 同库 override 分支隔离；文件数据平面 232MB；outbox 与 scoped-token 网关是现成的拆分基础设施 |
