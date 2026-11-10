# 后端结构分析报告（backend-structure）

> 分析对象：`backend/app/`（FastAPI 单体，审计作业平台）
> 分析日期：2026-11-09 ｜ 方法：全量文件扫描 + 前缀/子包聚类 + import 依赖图（基于 `from app.xxx import` 静态抽取）
> 用途：为「模块拆分」提供依据。统计口径见文末附录。

## 1. 总体规模

| 指标 | 数值 |
|---|---|
| `backend/app` Python 文件总数 | 3,086 个 |
| 总代码行数 | ≈ 103.2 万行（不含 migrations/data） |
| routers/ | 870 个 py（含 `wp_render_strategies/` 380 个渲染策略文件） |
| services/ | 1,969 个 py（含 31 个子包） |
| models/ | 114 个 py |
| schemas/ | 34 个 py |
| 技术基建层（core/middleware/security/api/workers/router_registry/permissions/deps/main） | 113 个 py ≈ 2.2 万行 |

单文件最大 5,035 行（`services/workpaper_sync/excel_materialize.py`）；>2000 行的文件 26 个，合计 7.7 万行。

## 2. 目录结构与路由挂载机制

```
backend/app/
├── main.py            # FastAPI 入口：GC/懒加载路由调优、10 层中间件洋葱、异常处理器、register_all_routers()
├── deps.py            # 依赖注入：get_current_user / require_role / require_project_access（JWT+Redis黑名单+SoD撤销）
├── core/              # 32 个：database/config/redis/migration_runner/startup_registry/lazy_api_routes/route_index/sse_registry/事件等
├── middleware/        # 13 个：audit_log/response_wrapper/observability/rate_limiter(LLM)/gzip_offload/body_limit...
├── security/          # 14 个：基线契约/证据清单/go_live_gate/专属组件路由扫描（上线门禁工具）
├── api/               # 7 个：auth/users/health/probes/feature_flags/wopi
├── workers/           # 24 个：后台 worker（ai_task/import/qc_rating/consol_operation/dataset_purge/sla...）
├── router_registry/   # 5 个子模块：workpaper/report/collaboration/system/cycle_engines
├── permissions/       # enforcement.py + permission_matrix.py
├── routers/           # 870 py：扁平命名 + eqcr/、evidence_governance/、wp_render_strategies/ 三个子包
├── services/          # 1969 py：扁平命名 + 31 个子包（acnr、ai_chat、wp_export、consistency_gate、import_engine...）
├── models/            # 114 py：SQLAlchemy ORM（core.py = User/Project/ProjectUser/Log/Notification）
├── schemas/           # 34 py：Pydantic
└── data/ migrations/  # 种子数据 / 迁移
```

**路由挂载**：`main.py → register_all_routers(app)`，按 5 个分组注册（`router_registry/`）：

| 注册模块 | 约注册 router 数 | 覆盖内容 |
|---|---|---|
| `workpaper.py` | ~329 | 底稿管理/深度优化/模板 |
| `report.py` | ~51 | 报表与附注/导出 |
| `collaboration.py` | ~96 | 团队看板/PBC函证/通知/门禁 |
| `system.py` | ~147 | 基础设施/系统管理/账表导入 |
| `cycle_engines.py` | ~24 | D/F/G/H/I/J/K/L/M/N 审计循环计算引擎（挂载时统一附加 `dedicated_wp_gate` 依赖） |

注册后 `_validate_registry_completeness()` 扫描 `routers/` 目录比对遗漏（仅 WARNING）；`core/route_index.py` 按路径段建索引加速匹配；`core/lazy_api_routes.py` 把依赖分析推迟到首次使用。**注册机制按"路径约定 + 全目录扫描"运作，对拆分最敏感的是 `_validate_registry_completeness` 与 `cycle_engines._inc` 的专属门禁注入**。

## 3. 业务域清单（按文件名前缀/子包聚类，共 19 个业务域 + 2 个共享层 + 1 个技术基建层）

审计循环编号约定：D=销售、F=采购存货、G=投资、H=固定资产、I=无形资产、J=职工薪酬、K=管理费用、L=筹资、M=权益、N=税金；m1~m10/l1~l8/n1~n5/h5~h9 等为**科目级底稿**（导入导出/测算）；a17/b60/b5/b50/a18/a21 为**报告文书章节**（A/B 系列）；底稿模板编码 A/B/C/D~N 见 `wp_render_strategies/`。

| # | 业务域 | 代表前缀/子包 | routers | services | models | schemas | LOC | LOC占比 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | **底稿核心 wp_core** | `wp_*`、`workpaper_*`、`formula_*`、`linkage_*`、`trim/prefill/writeback`、子包 `wp_fill/wp_scripts/wp_visibility/workpaper_sync/workpaper_capability/formula_runtime/formula_push/formula_management/formula_settings`、`routers/wp_render_strategies/`（380个渲染策略） | 489 | 710 | 21 | 12 | 447,577 | 43.4% |
| 2 | **附注 note** | `note_*`、`disclosure_*`、`a17*/b60/b5/b50/b14`、子包 `acnr/`（科目-附注解析，39文件） | 28 | 206 | 8 | 2 | 82,475 | 8.0% |
| 3 | **账套数据 ledger_data** | `ledger_*`、`dataset_*`、`data_*`、`account_*`、`import_*`、`aging/balance/column_mapping/uscc`、子包 `import_engine/ledger_import/bulk_tab/balance_diagnostics/custom_query` | 27 | 179 | 5 | 1 | 71,634 | 6.9% |
| 4 | **复核质控 qc_review** | `qc_*`、`review_*`、`gate/checklist/consistency/conflict/completeness`、`a21`、`phase10/phase14`、子包 `consistency_gate/audit_chain/state_machines/evidence_governance` | 50 | 135 | 17 | 1 | 62,971 | 6.1% |
| 5 | **循环引擎 cycle_engine** | `wp_[d2f2g~n]_*`、科目底稿 `m1~m10/l1~l8/n1~n5/h5~h9/s34/s_estimate/s_transaction/vr/gt_coding/t_account`、子包 `*_extraction/four_table`、`deferred_tax_shared` | 53 | 121 | 3 | 0 | 58,030 | 5.6% |
| 6 | **AI/LLM ai_llm** | `ai_*`、`llm_*`、`ocr/semantic/vector/indexing/matching/mineru/markitdown/tsj_*`、子包 `ai_chat/`（25文件）/`auto_data_resolvers/`（23文件） | 23 | 112 | 4 | 1 | 52,443 | 5.1% |
| 7 | **项目协作 project** | `project_*`、`deliverable_*`、`task/workflow/rotation/materiality/risk/procedure/sampling/cutoff/dashboard/pm_service/batch_*`、`phase15`（任务树） | 39 | 103 | 5 | 2 | 45,145 | 4.4% |
| 8 | **合并报表 consol** | `consol_*`、`consolidation_*`、`goodwill/minority/equity/elimination/forex/group_*`（集团树）、`parent_company_*` | 23 | 86 | 11 | 3 | 37,086 | 3.6% |
| 9 | **文档办公 docs_office** | `word/docx/pdf/excel/xlsx/onlyoffice/wopi/libreoffice/anydoc/export_*`、子包 `wp_export/wp_conversion` | 16 | 58 | 1 | 2 | 29,614 | 2.9% |
| 10 | **报表 report** | `report_*`、`tb_*`（试算表）、`cfs/cf/financial/trial/ratio/drilldown/analytical/cash`、`a18`、`phase13`（报表快照/Word导出任务） | 21 | 49 | 6 | 0 | 27,939 | 2.7% |
| 11 | **系统管理 system** | `system_*/sys_*/admin/feature/i18n/health/platform/metabase/shared_config/template/background_jobs` | 18 | 47 | 6 | 1 | 20,375 | 2.0% |
| 12 | **调整分录 adjust** | `adjustment_*/reclassification/misstatement/voucher/bad_debt/adjudication` | 13 | 35 | 3 | 1 | 17,374 | 1.7% |
| 13 | **用户权限 iam** | `user_*/role_*/staff/partner/permission/login/department/sod/workhour/my_*/temporary_grant` | 21 | 28 | 10 | 3 | 14,543 | 1.4% |
| 14 | **知识指引 knowledge** | `knowledge_*/guidance_*/citation/reference/regulatory` | 6 | 27 | 3 | 0 | 14,558 | 1.4% |
| 15 | **归档 archive** | `archive_*/recycle/version/time_machine/phase16`（取证包）/`legal_hold` | 10 | 20 | 3 | 0 | 8,209 | 0.8% |
| 16 | **通知事件 notify_event** | `notification_*/event_*/dispatch/forum/issue_ticket/sse/outbox` | 8 | 14 | 3 | 1 | 7,335 | 0.7% |
| 17 | **EQCR 质量复核** | `eqcr/` 子包（workbench/gate/independence/memo/notes...） | 18 | 9 | 1 | 0 | 6,083 | 0.6% |
| 18 | **函证确认 confirmation** | `confirmation_*/pbc/e0_send_list` | 3 | 15 | 1 | 0 | 5,124 | 0.5% |
| 19 | **电子签名 esign** | `signatures/sign_service` | 1 | 1 | 0 | 0 | 342 | 0.03% |
| S1 | 共享内核 shared_kernel | `models/base.py`（Mixin/枚举）+ `models/core.py`（5 张核心表）+ `schemas/common,_common,core` | – | – | 2 | 3 | 754 | – |
| S2 | 共享工具 shared_util | `services/_decimal_helpers/_zh_tokenize/retry_utils/fast_writer/query_cache` | 0 | 5 | 0 | 0 | 797 | – |
| T | 技术基建 core_infra | `core/ middleware/ security/ api/ workers/ router_registry/ permissions/ deps.py main.py` | 2 | 8 | – | – | 21,674 | 2.1% |

> 口径说明：routers/services/models/schemas 四目录合计 2,973 文件入域（另 113 个技术基建文件单列）；域边界按文件名前缀约定聚类，个别横切文件（如 `wp_ai_*` 归 AI、`wp_f2_*` 归循环）按首要职责归类，误差 ±2%。

## 4. 共享内核清单（拆分前必须先固定）

| 类别 | 文件 | 说明 |
|---|---|---|
| 核心实体 | `models/base.py`（Base/AuditMixin/SoftDeleteMixin/枚举）、`models/core.py`（User/Project/ProjectUser/Log/Notification/Department，399 行） | 全部域的 FK 根 |
| **事实共享模型** | `models/workpaper_models.py`（1,162 行） | 被 ≥8 个域 import（project 48 文件、qc 38、ai 36、docs 26、cycle 24、archive 10）— 实际上的第二共享内核 |
| **事实共享契约** | `models/audit_platform_models.py`（1,462 行）+ `models/audit_platform_schemas.py`（1,125 行） | 审计留痕/事件负载（EventPayload/EventType），ledger 55 文件、ai 26、project 26、qc 多处引用 |
| 协作模型 | `models/collaboration_models.py`（746 行）、`models/attachment_models.py`、`models/evidence_governance_models.py` | 中间件/多个域引用 |
| 依赖注入 | `deps.py`（831 行） | **约 650 个文件直接 `from app.deps import`**（认证、DB session、`require_project_access` 项目级鉴权） |
| 技术基建 | `core/database, config, redis, migration_runner, startup_registry, route_index, lazy_api_routes, sse_registry, event 相关`、`middleware/*` | 全域引用；`startup_registry` 是组装根，启动时 import ~15 个域的 handler |
| 横切安全门禁 | `routers/_wp_gate.py`（专属底稿组件 gate）、`services/wp_visibility/`（可见性判定） | cycle_engine 26 处、docs_office、ai_llm、wopi 引用 |
| 解耦机制 | `services/event_bus.py`（进程内 asyncio + Redis Stream 持久化）+ `services/event_handlers/` + 各域 `*_handler` | 已有的事件解耦通道：调整分录→试算重算、导入完成→重算、科目映射变更→重算等 |
| 通用 schema | `schemas/common.py`、`schemas/_common.py`、`schemas/core.py` | 分页/通用响应 |

## 5. 中心实体依赖分析

`app.models.core`（User/Project/ProjectUser/Log/Notification）被 **771 个文件**（25%）引用，按域分布：

| 域 | 引用文件数 | 域 | 引用文件数 |
|---|---:|---|---:|
| wp_core | 252 | system | 20 |
| qc_review | 60 | docs_office | 20 |
| project | 60 | eqcr | 18 |
| note | 49 | archive | 16 |
| ledger_data | 49 | core_infra | 16 |
| consol | 38 | adjust | 15 |
| cycle_engine | 34 | notify_event | 11 |
| iam | 34 | knowledge | 8 |
| report | 27 | confirmation | 2 |
| ai_llm | 23 | esign | 1 |

**Project（项目/业务约定）是全域中心实体**：所有 19 个域都直接或间接依赖；第二中心是 `Workpaper`（workpaper_models）与审计留痕（audit_platform_models）。`app.deps` 被 653 个文件引用，其中 wp_core 239、cycle_engine 52、qc_review 49、project 45。

## 6. 耦合热点（Top 5，附证据）

跨域 import 边（按模块×目标计数，第一层全量扫描结果）：

```
wp_core -> core_infra 598 | wp_core -> cycle_engine 294 | wp_core -> shared_kernel 278
wp_core -> qc_review 144 | wp_core -> ai_llm 141 | wp_core -> ledger_data 102 | wp_core -> project 81
docs_office -> wp_core 99 | cycle_engine -> wp_core 94 | qc_review -> wp_core 80
note -> wp_core 67 | project -> wp_core 66 | ai_llm -> wp_core 64 | report -> wp_core 62
core_infra -> wp_core 306（集中在 20 个文件） | note -> report 49 | ai_llm -> qc_review 48
ledger_data -> qc_review 52 | project -> qc_review 54 | consol -> note ~30 | consol -> report ~21
```

### 热点 1：wp_core 是"神域"（星型拓扑中心）
43% 的代码集中在底稿域，且双向耦合所有域：出边 cycle_engine(294)/qc_review(144)/ai_llm(141)/ledger_data(102)/project(81)/report(62)/docs_office(52)；入边 docs_office(99)/cycle_engine(94)/qc_review(80)/note(67)/project(66)/ai_llm(64)/report(62)/archive(33)。任何拆分方案都无法绕开它。原因：底稿是全平台的工作载体，报表/附注/AI/门禁/归档全部围绕底稿数据（`workpaper_models`、`parsed_data`、`wp_visibility`）展开。

### 热点 2：技术基建反向依赖业务（core_infra → wp_core 306 次/20 文件）
- `deps.py`：`require_project_access` 内嵌项目-底稿权限语义；
- `core/startup_registry.py`：启动组装根，import a13(附注事件)/adjustment 重算/consol 四个重算 handler/ai_chat/formula_push/gate_rules×4/import_runner/libreoffice 等 ~15 个域；
- `middleware/audit_log_middleware.py`：import `app.models.collaboration_models.OpType` 与 `app.models.core.Log`；
- `api/wopi.py`：import `services.wp_visibility.wp_bound_gate`（底稿可见性门禁）；
- `router_registry/*`：注册层全量 import 各域 router（该层属组装根，可接受）。
原因：中间件/启动序列把"审计留痕、门禁、事件注册"等业务语义硬编码进了基建层。

### 热点 3：事实共享模型分散在业务目录
`workpaper_models.py`、`audit_platform_models.py/_schemas.py`、`collaboration_models.py`、`attachment_models.py` 名义上属于 wp/qc 域，实际被几乎所有域 import（见 §4）。拆分时若按目录归域会立即产生循环依赖。原因：历史上按"最先使用者"落位，而非按共享语义。

### 热点 4：报表-附注-合并三角（note ↔ report ↔ consol）
- note→report 49 次：核心是 `report_models`（62 处 import，报表-附注联动/取数绑定），另有 `report_note_linkage`、`analytical_review_service`；
- consol→note ~30 次：`note_total_terms(8)/note_section_catalog(6)/note_table_header_library(5)`——合并附注生成复用单体附注章节引擎；
- consol→report ~21 次：`report_models(12)/report_generation_models(5)`——合并报表走报表生成链路。
原因：合并/单体共用同一套"报表→附注→导出"数据管线，report_models 是管线契约。

### 热点 5：渲染策略与科目导入导出把 wp/cycle 焊死
- `routers/wp_render_strategies/`（380 个文件，底稿模板 A~N 系列专属渲染策略）位于 routers/ 目录下却是"渲染库"，wp_core→cycle_engine 的 294 次出边大部分来自这里（每科目渲染策略 import 对应 extraction/测算服务）；
- 科目底稿路由（m1~m10/l1~l8/n1~n5/h5~h9，共 30+ 文件）每个都 import `_wp_gate` + `workpaper_models` + `wp_parsed_data_service`（cycle→wp 94 次的主体）。
原因：底稿模板体系（编码 A/B/C/D~N）与审计循环引擎按科目一一对应，天然同生命周期。

**已有的缓解机制**：`event_bus`（调整分录→试算重算等 6 类联动已走事件）、ACNR 目录快照（附注-科目映射解耦）、outbox 模式（invalidation_outbox/import_event_outbox）。拆分可以放大这类模式。

## 7. 自然边界建议（按耦合密度分三档）

1. **立即可拆（出边少、入边少）**：`esign`、`confirmation`、`knowledge`、`archive`、`notify_event`、`eqcr`、`system`、`iam` —— 8 个小域合计 ~27 万 LOC，对外依赖主要是 core_infra + 核心模型，先迁出验证流程。
2. **需先立契约再拆**：`ai_llm`（依赖 wp_visibility/evidence_governance 门禁与 workpaper_models）、`docs_office`（深度绑定 workpaper_sync/wp_visibility）、`project`（依赖 workpaper_models/audit_platform_models）—— 三者把对 wp 的依赖收敛到"底稿读写门禁 + 底稿模型快照"两个契约接口后即可独立。
3. **短期作为一个"审计作业内核"保留**：`wp_core + cycle_engine + ledger_data + report + note + consol + adjust + qc_review`（合计 ~87 万 LOC）—— 它们通过 workpaper_models/report_models/事件总线强联动，是产品主线；内部可先做**包级分区**（如 wp_render_strategies 移出 routers/、workpaper_sync 独立子模块），再借 event_bus 逐步切断运行时直调。

## 8. 拆分风险点

| # | 风险 | 证据/位置 |
|---|---|---|
| 1 | `deps.py` 被 ~650 文件直接 import（鉴权+DB+项目访问），必须先降级为独立共享库，否则任何拆分都会产生对"平台内核"的网状依赖 | §5 |
| 2 | 事实共享模型（workpaper_models/audit_platform_models/collaboration_models/attachment_models）落位错误会造成拆分后循环 import | 热点 3 |
| 3 | `startup_registry` 组装根集中注册 ~15 个域的事件 handler/worker/健康检查；拆分后需改为各域自声明+汇编器模式 | core/startup_registry.py |
| 4 | 路由发现机制假设 routers/ 目录可全量扫描：`_validate_registry_completeness`（pkgutil.walk_packages）、`cycle_engines._inc` 动态注入 dedicated_wp_gate、`core/lazy_api_routes`、`route_index`；跨服务拆分后这套机制失效 | router_registry/__init__.py、cycle_engines.py |
| 5 | 中间件/审计留痕直接 import 业务模型（Log/OpType），中间件需改为依赖契约 | middleware/audit_log_middleware.py |
| 6 | `_wp_gate`/`wp_visibility` 属安全横切，各域路由拆分后必须保证同一实现与一致覆盖（defense in depth 注释明确要求） | routers/_wp_gate.py、security/dedicated_component_routers.py |
| 7 | `models/phase10~16_*.py` 命名掩盖归属（phase10=复核协作、12=AI/后台任务、13=报表快照、14=门禁、15=任务树、16=取证包），横跨 5 个域，拆分前需重命名归类 | models/ |
| 8 | 单 Postgres 库 + `set_rls_context`（deps 内做 RLS 上下文）+ 迁移框架 migration_runner/schema_drift_detector 绑定单库；按服务拆库需重设计 | deps.py、core/migration_runner.py |
| 9 | workers（24 个）与 SSE 注册表（sse_registry）、优雅停机（graceful_shutdown/reload_handoff）假设单进程模型 | core/、workers/ |
| 10 | wp_render_strategies（380 文件）放在 routers/ 下但本质是渲染库；科目底稿路由 m/l/n/h 与循环引擎同生命周期——归域错误会放大热点 5 | routers/wp_render_strategies/ |

## 9. 附录：分析方法与口径

- 聚类规则：按文件名首段前缀 + 31 个 services 子包 + 3 个 routers 子包映射到域；规则脚本可复现（前缀表见分析过程，如有争议以 router_registry 五分组 + services 子包名为准）。
- import 图：正则抽取 `from app.xxx import` / `import app.xxx`（含相对导入解析），映射模块→域后聚合边权重；未解析动态 import（字符串拼接）不在统计内。
- LOC：按 UTF-8 逐行计数，含空行注释。
- 局限：`wp_ai_*`/`wp_f2_*` 等横切前缀按首要职责归 AI/循环域；`goodwill_*` 归合并域（其渲染策略仍在 wp_render_strategies）。
