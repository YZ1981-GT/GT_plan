# 数据层与部署/基础设施分析报告（模块拆分依据）

> 分析人：data-infra-explorer ｜ 日期：2026-11-09 ｜ 当前分支：sj-dev1.0
> 范围：`backend/app/models/`、`backend/migrations/`、根目录部署变体、非标准目录、scripts/tools
> 目的：为「模块拆分」方案提供数据层与部署侧的事实依据。纯静态分析，未连接数据库。

---

## 1. 结论速览（TL;DR）

1. **单库单 schema**：全平台使用一个 PostgreSQL 库（`audit_platform` / `audit_platform_sj` / `sw_audit_platform`），全部表都在默认 `public` schema，迁移中无 `CREATE SCHEMA` / `search_path` 操作。pgvector 扩展可选启用（V043，失败优雅降级 pgtext）。
2. **中心实体高度辐射**：`users` 被模型层引用 177 次/58 个文件（迁移中 140 处 `REFERENCES users`）；`projects` 被引用 150 次/58 个文件（迁移中 127 处）。**Project 是全域事实上的聚合根**，任何按域拆库都绕不开它。
3. **跨域外键真实存在且成网**：除指向 users/projects 的"轮辐"外，还有 20+ 组域间直连外键（confirmations→working_paper、evidence↔attachment、ai↔evidence、report↔consol 双向等），**按域拆 schema 需要大量外键降级为应用层引用**。
4. **gt / sj / sw 是同一代码库的分支隔离部署形态，不是不同业务线**：三套 compose 均为 `docker-compose.yml` 的 override，只改容器名/卷/端口/库名；sw 是「税务 demo」（注释明示），sj 是 sj-dev1.0 分支专用隔离环境（当前 checkout 即该分支）。
5. **迁移体系自研**：`MigrationRunner`（启动自动应用 V*.sql，checksum 校验 + advisory lock + drift 检测），当前 V001–V260 共 255 个（缺 200/201/209/210/240 号），R*.sql 回滚 200 个且**与 V 一一配对的只有 200/255，V094 之后大量缺失回滚**。
6. **部署上没有微服务化的现实**：单一 FastAPI 进程 + 进程内 21 个后台 worker + 独立 OCR HTTP 服务（可选）；只有 PG/Redis/OnlyOffice/Metabase 等"基础设施容器"。

---

## 2. 模型域聚类（backend/app/models/，114 个文件）

> 说明：目录含 `__init__.py`、`base.py`、约 20 个 `*_schemas.py`（Pydantic，非 ORM）；实际 ORM 文件约 80+。聚类按文件 docstring 与 `__tablename__` 判定。

### 2.1 域聚类表

| 业务域 | 模型文件（ORM） | 核心表 |
|---|---|---|
| **核心/身份** | `core.py`、`base.py`、`sys_permission.py`、`user_display_preferences.py`、`temporary_grant_models.py`、`department_schemas.py` | users、projects、project_users、sys_dept、sys_role、sys_role_project、logs、notifications、临时授权、显示偏好 |
| **账表/导入（ledger-data）** | `audit_platform_models.py`(1462行,MVP 10表)、`dataset_models.py`、`account_package_models.py`、`account_note_mapping_models.py`、`note_account_mapping.py`、`t_account_models.py`、`adjustment_import_models.py`、`adjustment_review_models.py`、`aging_segment_model.py`、`bad_debt_models.py`、`column_mapping_models.py`、`cf_verification_models.py`、`share_change_event_models.py`、`audit_phase_models.py` | trial_balances、tb_ledger/tb_aux_ledger、adjustments、import_batches、ledger_datasets、import_event_outbox、account_packages、账龄段、坏账、T型账户、现金流量核查 |
| **底稿（workpaper）** | `workpaper_models.py`、`workpaper_sync_models.py`(1159行,V151 28表)、`workpaper_lifecycle_models.py`、`workpaper_template_version.py`、`workpaper_field_override_models.py`、`workpaper_row_name_mapping_models.py`、`wp_export_models.py`、`wp_generation_models.py`、`wp_optimization_models.py`、`wp_visibility_models.py`、`project_wp_sheet_override.py`、`project_workbook_models.py`、`dispatch_models.py`、`phase12_models.py` | working_paper、wp_template/wp_index、working_paper_artifact/content_version/oo_room/sync_*（28 张回写表）、底稿导出快照、生成 operation/item、分发记录 |
| **报表/附注/出品（report）** | `report_models.py`(812行)、`report_schemas.py`、`phase13_models.py`、`report_generation_models.py`、`note_content_template_models.py`、`note_formula_models.py`、`note_trim_models.py` | financial_report、report_config(+baseline)、audit_report、disclosure_notes、export_task、note_content_templates、note_formula_runs、report_generation_run |
| **合并（consol）** | `consolidation_models.py`、`consol_cell_comment_models.py`、`consol_note_data_models.py`、`consol_note_mapping_models.py`、`consol_operation_models.py`、`consol_push_models.py`、`consol_scope_confirmation_models.py`、`consol_worksheet_data_models.py`、`enterprise_linkage_models.py` | consol_operation、合并范围确认、抵销推送、合并附注数据/模板、企业树三码 |
| **AI** | `ai_models.py`(1428行)、`ai_schemas.py`、`ai_model_options.py`、`ai_task_job_models.py`、`chain_execution.py` | ai_chat_*、ai_model_config、ai_task_jobs、chain_execution |
| **取证/证据（evidence）** | `evidence_governance_models.py`(1254行)、`confirmation_models.py`、`related_party_models.py`、`acnr_overlay_model.py`、`acnr_invalidation_model.py`、`extension_models.py`、`phase16_models.py`、`phase14_models.py` | evidence_refs/citation_snapshots/evidence_links、confirmations（函证）、取证包版本链、统一门禁 |
| **复核/质控（review/qc）** | `collaboration_models.py`、`phase10_models.py`、`review_workflow_models.py`、`review_template_models.py`、`eqcr_models.py`、`qc_case_library_models.py`、`qc_inspection_models.py`、`qc_rating_models.py`、`qc_rule_models.py`、`editing_lock_models.py`、`independence_models.py`、`rotation_models.py`、`handover_models.py`、`gate_acknowledgement_models.py` | review_records/review_threads、EQCR 快照、QC 规则/抽查/评级、编辑锁、独立性签署 |
| **公式** | `formula_setting_models.py`、`formula_push_models.py` | formula_template/formula_push_state/formula_runtime_outbox |
| **知识库（knowledge）** | `knowledge_models.py`、`guidance_publication_models.py`、`guidance_handoff_ack_models.py`、`template_library_models.py`、`gt_coding_models.py`、`shared_config_models.py` | knowledge_folders/documents/index（pgvector）、guidance_publication、模板库三层体系 |
| **附件/资产** | `attachment_models.py`、`attachment_lineage_model.py`、`asset_blob_models.py` | attachments、attachment_versions、attachment_lineage、asset_blobs（跨域不可变字节） |
| **人员/工时** | `staff_models.py`、`workhour_entry_models.py` | staff_members、workhour_entries |
| **审计程序/流程** | `procedure_models.py`、`phase15_models.py`、`audit_log_models.py`（哈希链审计日志）、`archive_models.py` | procedure_row_tasks、任务树事件、app_audit_log、archive_manifests |
| **项目治理杂项** | `batch_project_models.py`、`project_creation_grant_models.py`、`custom_query_models.py`、`enum_dict_override_models.py`、`shared_config_models.py`、`v3_refinement_models.py`、`platform_job_models.py`、`account_note_mapping_models.py` 等 | 批量建项、建项授权、自定义查询模板、平台通用耐久任务 |

另有 `phase14/15/16_enums.py`（枚举）、约 20 个 `*_schemas.py`（Pydantic DTO，与 ORM 同文件域混放）。

### 2.2 中心实体引用强度

统计来源：`grep -c 'ForeignKey("…")' backend/app/models/*.py` 与 `grep -o 'REFERENCES …' backend/migrations/V*.sql`。

| 被引用实体 | 模型层 FK 引用次数 | 引用文件数 | 迁移层 REFERENCES 次数 |
|---|---|---|---|
| `users.id` | **177** | 58 | **140** |
| `projects.id` | **150** | 58 | **127** |
| `working_paper.id` | 34 | — | 29 |
| `staff_members.id` | 16 | — | 17 |
| `working_paper_artifact.id` | 12 | — | 12 |
| `attachments.id` / `attachment_versions` | 2 / — | — | 6 / 10 |

**解读**：58/82 个 ORM 文件同时挂 users+projects 外键——Project/User 是全域公共依赖，等价于"每个域都有轮辐指向中心"。拆分时中心域（identity+project）必须独立成公共服务，其余域只保留对它的单向引用。

---

## 3. 迁移分析（backend/migrations/）

### 3.1 基本盘

| 指标 | 数值 |
|---|---|
| V*.sql 前向迁移 | **255 个**（V001–V260，缺号 200/201/209/210/240） |
| R*.sql 回滚脚本 | **200 个**（R001–R260） |
| V↔R 编号配对 | **200/255**；V094 之后基本不再配回滚（V016/V018/V022-V024/V033 等早期也缺） |
| 迁移中 distinct 表 | 251 个（含改名/重建的中间态） |
| 运行机制 | 自研 `MigrationRunner`（`app/core/migration_runner.py`）：启动时按版本号顺序自动应用、sha256 checksum 防篡改、PG advisory lock（多 worker 串行）、`schema_version` 表登记、`schema_migration_failures` 失败登记、`schema_drift_detector` ORM↔DB 漂移自检 |
| 回滚机制 | R 脚本仅手工 CLI 执行（`python -m app.core.migration_runner --rollback NNN`），启动时不自动跑 |

命名规律：`V{NNN}__{snake_case主题}.sql`，主题可直读业务域，如 `V034__consol_schema_baseline`、`V058__confirmations`、`V169__formula_push_engine`、`V241__asset_blob_foundation`。前缀分布：working_paper* 30、consol* 23、workpaper* 14、evidence* 12、ai* 11、project* 10、wp* 9、formula* 9、procedure* 8、note* 8、adjustment* 8……

### 3.2 迁移质量信号（拆分风险评估）

- **修复型迁移**（"补漏"）多次出现：V110/V114（repair_procedure_*_missed_by_V105/V112_conflict）、V134（repair_ai_content_governance_missed_by_v113）、V159（workpaper_sync_required_constraints_repair）、V175（repair_consol_snapshots_schema）、V190（add_missing_columns_fix_orm_drift）、V205（fix_export_schema_drift）。说明"ORM 先行、迁移补齐"的开发模式导致迁移与 ORM 漂移是常态，靠 drift detector 兜底。
- **schema 级修复迁移**：V017/V018/V033/V051（fix_schema_drift 系列）。
- **退役/重建**：V075（drop_workpaper_editing_locks）、V231（drop_contract_dead_tables）、V253（retire_consol_note_v202）。
- **隐含依赖平台特性**：pgvector（V043/V119，优雅降级）、RLS（V005 启用 / R005 禁用）、哈希链审计日志（V007/V050）。

### 3.3 跨域外键证据（按域拆分的硬约束）

统计方法：解析全部 V*.sql 中 `CREATE TABLE`/`ALTER TABLE` 与 `REFERENCES` 的配对，先按表名前缀分域，再剔除指向中心表（users/projects/service_identities）的"轮辐"。

**域间直连外键（非中心表）分布**：

| 源域 → 目标域 | 次数 | 典型证据 |
|---|---|---|
| evidence → attachment | 4 | V107 `evidence_refs → attachment_versions`；V258 `evidence_links`（挂凭） |
| evidence → workpaper | 1 | **V258 `evidence_links.wp_id REFERENCES working_paper(id) NOT VALID`**（取证挂凭直连底稿） |
| ai ↔ evidence | 2 | V108 `ai_content_log → evidence_refs`、`citation_snapshots → evidence_refs`（AI 内容治理与证据治理互写） |
| ai → attachment | 1 | V241 `ai_chat_run_resources → attachment_versions` |
| review → workpaper | 2 | **V058 `confirmations.wp_id REFERENCES working_paper(id)`**（函证挂底稿）；V085 `checklist_responses → working_paper` |
| review → evidence | 2 | V108 `review_evidence_snapshots → evidence_refs` |
| report ↔ consol | **双向** | V246 `report_generation_run.operation_id → consol_operation` 且 `consol_artifact.report_run_id → report_generation_run`（互为外键，拆分时必须断开一处） |
| consol → report | 1 | 同上 |
| formula → workpaper | 1 | V169 `formula_push_state.wp_id REFERENCES working_paper(id) ON DELETE CASCADE` |
| ledger → staff | 2 | V063 `account_package_program_status.reviewer → staff_members(id)` |
| knowledge → attachment | 2 | V241 `knowledge_evidence_promotions → attachments`、`knowledge_documents → asset_blobs` |
| workpaper 域内派生 → staff | 8 | procedure_row_task_history → staff_members（委派留痕） |
| other（治理/杂项）→ 各域 | ~30 | citation_snapshots→ai_content_log、legacy_attachment_alias→attachments、event_outbox_dlq→import_event_outbox 等 |

**结论**：
1. 指向 users/projects 的轮辐外键占绝对多数（267 处），这部分可通过"公共身份/项目域"保留；
2. 域间直连外键 20+ 组，其中 **report↔consol 双向外键**、**evidence→working_paper**、**confirmations→working_paper**、**ai↔evidence** 是最硬的耦合点；
3. 按域拆分 PG schema（同库不同 namespace）技术上可行——外键可以跨 schema 存在，且无需处理两阶段提交；但拆成独立数据库则上述外键全部要降级为应用层引用 + 一致性由 outbox/对账保障（仓库已有 `import_event_outbox`/`formula_runtime_outbox`/`consol_operation` 事件模式可复用）。
4. 迁移文件本身按业务域前缀清晰可分（consol_*/wp_*/evidence_* 等），"按域切分迁移文件"比"按域拆外键"容易。

---

## 4. 部署变体对比（gt / sj / sw / ocr）

### 4.1 判定：同一代码库的分支隔离部署，非不同业务线

| 变体 | 组成 | 性质 |
|---|---|---|
| `docker-compose.yml`（基础） | postgres(pgvector/pg16)、pgbouncer、redis(+HA profiles)、backend(profile docker-backend)、nginx、onlyoffice(profile)、metabase、paperless(profile，默认禁用)、vllm/vllm-embed/mineru(profile gpu)、ollama | 开发环境基座；PG 卷固定 external `gt_workplan_pg_data`（注释：dev1.0 业务库、**422 张表**） |
| `docker-compose.gt-plan.yml` | 仅 backend 服务的 override：让后端容器以独立项目 `gt-plan` 与 `gt-new-plan` 平级，通过外部网络 `gt-new-plan_default` 接入共享 postgres/redis/onlyoffice；补齐 wp_templates/data/definition_store/audit-platform 只读挂载（ContractDriftError 修复说明） | **同库共享基础设施**的后端容器形态（单机演示/部署用） |
| `docker-compose.sj-plan.yml` + `.env.sj-plan` + `scripts/sj-plan.ps1` | 项目名 `gt-sj-plan`，容器前缀 `gt-sj-*`，独立卷 `gt-sj-plan_sj_*`，库名 `audit_platform_sj`，端口 15433/16380/21010（全部 >15000 避开 Hyper-V 动态段） | **sj-dev1.0 分支**（当前 checkout 即此分支，根 `.env` 的 DATABASE_URL 指向 `127.0.0.1:15433/audit_platform_sj`）的隔离环境。注释明示「与其他分支不共用容器、数据卷、数据库」 |
| `docker-compose.sw-plan.yml` + `.env.sw-plan` + `scripts/sw-plan.ps1` + `start-dev-sw.bat` | 项目名 `sw-plan`，容器前缀 `sw-*`，独立卷，库名 `sw_audit_platform`，端口 5532/6479/8180（+100 偏移）；后端 :9981、前端 :3031 | **sw-dev1.0 分支 = 税务 demo**（`.env.sw-plan` 与脚本注释明示「sw-dev1.0 分支（税务 demo）专用」）。空库首启由 MigrationRunner 建表 |
| `docker-compose.ocr.yml` | 独立 `ocr-service` 容器（Flask + PaddleOCR + Tesseract，:9990），供 worker 进程经 `OCR_SERVICE_URL` 调用，把 OCR 模型从 web worker 内存剥离（限制 2G） | **可选旁挂服务**，与分支无关 |

### 4.2 关键推断

1. **同一业务代码，三种分支形态**：sj/sw 的 compose 全部是基础文件的 override（不改镜像内容，只改 `container_name`/volumes/ports/`PG_DB`），且 sj/sw 各自跑同一套 V001–V260 迁移。即 gt=主线 dev1.0（审计），sj=分支（sj-dev1.0，用途未在文档中明示，仅作为分支隔离环境），sw=税务 demo 分支。**拆分方案必须以"一份代码多形态部署"为前提**——拆分后的部署编排也要支持同样的 override 模式。
2. **数据面完全按分支物理隔离**（独立 PG 卷+独立库名），但**文件系统不完全隔离**：sw 的 `STORAGE_ROOT=./storage` 与 dev1.0 共用（.env.sw-plan 注释自认），`wp_templates/data/definition_store` 三目录跨分支共享同一份源码。
3. 后端日常开发不进容器：`start-dev.bat`（宿主机 :9980/:3030，dev/stable 双模式）与 `start-dev-sw.bat`（:9981/:3031，用真实环境变量覆盖 backend/.env）。容器 backend 仅 profile `docker-backend` 手动拉起。
4. 前端在 `audit-platform/frontend`（Vue3+Vite），由 Vite 代理指向 9980；OnlyOffice 承担 Word/附件 WOPI 预览（底稿编辑已迁 Univer，仅保留兼容）。

### 4.3 服务拓扑小结（一次完整启动）

```
[宿主机] start-dev.bat → uvicorn :9980 (FastAPI, 内含 21 个后台 worker 线程/任务)
                      ↘ vite :3030 (Vue3)
[容器] postgres(pgvector) :5432/15433/5532 ← pgbouncer :6432
       redis :6379 (+ sentinel/replica 可选 profile redis-ha)
       onlyoffice :8080 (WOPI, profile onlyoffice)
       metabase :3000 (直连同一业务库做看板)
       ocr-service :9990 (可选, docker-compose.ocr.yml)
       vllm/vllm-embed/mineru/ollama (可选 GPU profile)
```

---

## 5. 非标准目录盘点

| 目录 | 内容与作用 | 规模 |
|---|---|---|
| `backend/ocr_service/` | 独立 Flask HTTP 服务（`POST /recognize`，PaddleOCR+Tesseract，engine 参数），`docker-compose.ocr.yml` 构建部署；worker 通过 `OCR_SERVICE_URL` 调用，降低 web worker 内存 | 3 文件（app.py/Dockerfile/requirements.txt） |
| `backend/app/workers/` | **进程内**后台 worker 集合（21 个）：ai_task_worker、audit_log_writer（哈希链）、budget_alert、consol_operation、dataset_purge、export_cleanup、import_worker/import_recover、invalidation_dispatcher、knowledge_ocr、oo_apply_redrive、outbox_replay、platform_job_worker、procedure_dispatcher、qc_rating、reviewer_metrics、sla_worker、staged_orphan_cleaner、time_machine_cleanup；带 `_leader_lock.py`（领导者选举） | 随主进程启动，非独立部署单元 |
| `backend/data/` | **种子/契约/规则 JSON 大仓**（249 项）：审计报告模板（`audit_report_templates/`）、ACNR 地址目录（`acnr/`）、wp 解析规则/LLM prompt/微规则（`wp_parse_rules*`、`wp_llm_prompts/`、`wp_fine_rules/`、`wp_guidance/`）、workpaper_sync 50+ 份契约与治理 JSON、枚举/权限/账套种子。**业务代码运行时读取，属于"文件型配置/种子层"** | 133 MB |
| `backend/wp_templates/` | 致同底稿模板库，按 A–S 审计循环分目录（A 97 / B 137 / C 36 / S 90 …共 483 文件），xlsx/xlsm/docx；`_index.json` 元数据；workpaper-sync 对模板做 digest 校验（模板漂移即 ContractDriftError） | 59 MB，git 内 |
| `backend/definition_store/` | **内容寻址（sha256 文件名）不可变 blob 存储**：bundles/（已发布定义包）、contracts/（workpaper-sync 契约）、templates/（.ooxml 模板块）、instrumentation/、authority-models/；provisioning 的写入目标，compose 中要求"真实可写且与宿主一致" | 40 MB |
| `backend/app/data/` | 小型运行时 JSON（10 项）：风险评定预设、章节定义、公式管理豁免表、wp 渲染 schema、组件能力声明 | 与 backend/data 是两套，勿混淆 |

**对拆分的含义**：`backend/data`+`wp_templates`+`definition_store` 是第三个"数据平面"（文件型），与 DB 数据、Redis 状态并列；它们被底稿/报告/ACNR 域强依赖，拆分时建议归入"底稿域"或独立"模板/定义服务"。

---

## 6. scripts/ 与 tools/

| 目录 | 内容 |
|---|---|
| `scripts/`（根） | 开发/运维脚本：`sj-plan.ps1`、`sw-plan.ps1`（分支容器编排固定参数）；`deploy/`（rolling_update.sh、inject_build_version.sh）；`check/`（check_endpoint_auth.py、candidate_tree_identity.py 守卫）；`e2e/`（ensure_e2e_project.py）+ 4 个 e2e_*.py（全链路/批量建项冒烟）；种子与模板工具（extract_report_seed.py、generate_note_template_bindings.py、migrate_global_kb_to_pg.py、validate_seed_files.py）；`build-mineru.sh` |
| `backend/scripts/` | 更大的运维/修复脚本集（backfill_*、diagnose_*、clean_*、_mutation_kit 等），围绕 DB 数据修复与模板处理 |
| `tools/` | 三个独立子项目：`audit-data-mcp/`（stdio-only MCP server，给 DSH Agent 供数，**零 DB 直连**，全部经平台受权 REST API + scoped token）、`gt-plan-mcp/`（另一个 MCP server）、`officecli/`（Office CLI 安装器 install.ps1/sh） |

**对拆分的含义**：tools 下两个 MCP server 已经示范了"经 API 网关访问数据"的边界模式（零 DB 直连、scoped token、平台端二次鉴权），是模块拆分后域间访问的理想模板。

---

## 7. 单库现状结论

1. **单库**：`.env`（DATABASE_URL=`postgresql+asyncpg://…:15433/audit_platform_sj`）、`.env.sw-plan`（`sw_audit_platform`）、compose（`PG_DB: audit_platform`）——每个部署形态一个库，库内不分 schema（迁移零 `CREATE SCHEMA`）。Metabase 也直连同一业务库。
2. **单 schema**：所有 251 张表同处 `public`；"域"只体现在表名前缀与迁移文件名上，物理上无隔离。
3. **唯一例外**：pgvector 扩展（向量列在 knowledge_index 等表内），属于库级特性不是独立存储；附件字节流在本地磁盘/MinIO/OSS（`ATTACHMENT_PRIMARY_STORAGE`），不在 PG。

---

## 8. 数据层拆分难点清单（供方案评估）

| # | 难点 | 证据 | 影响 |
|---|---|---|---|
| 1 | **Project/User 中心辐射**：58/82 模型文件、267 处 FK 指向它们 | §2.2 | 任何拆分都必须先把 identity+project 独立为公共服务；否则每个域都拖着全量迁移 |
| 2 | **域间直连外键 20+ 组，含双向外键** | V246 report↔consol、V258 evidence→working_paper、V058/V085 →working_paper、V108 ai↔evidence | 拆库需全部降级为应用层引用；拆 schema（同库）可保留 FK 但破坏了 schema 级权限隔离的意义 |
| 3 | **单迁移流水线 255 步、无域边界** | V001–V260 串行；修复型迁移 6+ 次 | 拆分需按域重切迁移（前缀已可分），但"中途修复"类迁移与 V017/V033/V051 全局 drift 修复无法归属单一域 |
| 4 | **回滚纪律缺失**：55/255 无 R 配对 | §3.1 | 拆分期间的回退策略不能依赖 R 脚本，需要快照级回退（workpaper_snapshots/consol_snapshots 模式已存在可借鉴） |
| 5 | **文件型数据平面与 DB 混编** | backend/data 133MB、wp_templates 59MB、definition_store 40MB；compose 需挂载宿主目录防止 ContractDriftError | 拆服务后这三目录的发布/版本化要跟代码走或做成制品仓库 |
| 6 | **事件/outbox 模式已部分存在** | import_event_outbox、formula_runtime_outbox、consol_operation、event_outbox_dlq、platform_jobs、ai_task_jobs | 域间异步化的基础设施已具雏形，拆分可复用而非新建 |
| 7 | **启动即迁移的部署耦合** | MigrationRunner 在 FastAPI lifespan 自动跑全部迁移（冷启动 20–40s） | 拆分后多服务同时启动竞争迁移锁；advisory lock 已处理串行，但"谁拥有哪些迁移"需要新约定 |
| 8 | **多分支多形态部署** | gt/sj/sw override 模式 + 分支独立库 | 拆分方案的部署编排必须继续支持"同一份代码 + override"形态，否则分支工作流（当前 sj-dev1.0 即例）会失效 |
| 9 | **进程内 worker 群** | app/workers 21 个 + leader lock | 若拆出独立 worker 进程/服务，需处理领导者锁与 outbox 的跨进程语义 |
| 10 | **可选重依赖**：pgvector（降级 pgtext）、vLLM/Ollama/MinerU（GPU profile）、OnlyOffice WOPI 回调 | V043、compose gpu/onlyoffice profile | 拆分后的"最小可部署单元"要保留这些可选旁挂的降级路径 |

---

## 附：关键文件索引

- 迁移运行器：`backend/app/core/migration_runner.py`；漂移登记：`backend/app/core/migration_drift_ledger.py`
- 模型基类/枚举：`backend/app/models/base.py`；中心实体：`backend/app/models/core.py`
- 部署：`docker-compose.yml`（基座）、`docker-compose.{gt-plan,sj-plan,sw-plan,ocr}.yml`、`.env{,.sj-plan,.env.sw-plan}`、`start-dev.bat`、`start-dev-sw.bat`
- 分支编排脚本：`scripts/sj-plan.ps1`、`scripts/sw-plan.ps1`
- OCR 旁挂：`backend/ocr_service/app.py` + `docker-compose.ocr.yml`
- worker 群：`backend/app/workers/`（README.md 有说明）
- MCP 边界示范：`tools/audit-data-mcp/server.py`（零 DB、经 REST + scoped token）
