# 实施任务：高级查询查询证据与时效（advanced-query-artifact-and-freshness）

> 证据口径：计数一律现算并写明命令；故障注入用磁盘变异，逐字节还原后核对 sha256；真 PG 写入只在回滚事务里、只写【测试】项目；浏览器实测在候选栈（前端 3040 → 后端 9981）；共享库执行迁移前须用户放行（requirements D3）。
> 每个任务完成时在本文件该任务下追加「证据」小节（命令、结果、偏离），不另起文档。

- [-] 0. 现状重算与基线（design §0；N4）
  - 重算 design §0 的锚点、行数、迁移最高号（磁盘含未跟踪 / 共享库 `schema_version` / 远端分支三处）、端点鉴权基线各维度计数、路由遮蔽守卫；与 §0 不符时先改 design 再动代码。
  - 后端基线：`backend/tests/advanced_query_linkage` 全量真 PG + 相关非 PG 选集（custom_query / query_builder / 导出 / 导出清理 worker）；前端基线：`components/query`、`components/custom-query`、`components/template-library`、`views/AdvancedQueryBuilder` 相关 vitest；逐节点记录预存失败。
  - grep 测试里对 `app.routers.custom_query`、`query_orchestrator`、`execute_compatibility`、`export_service`、`query_export` 的 monkeypatch 目标，列出抽取时必须保留的补丁点，写进 design §5.3。
  - 验收：基线 junit 与补丁点清单存 `tmp_aqf/`；design §0 与现算一致（不一致处已更正并注明日期）。

- [x] 1. 迁移与模型（R1.3、R4.3、R8.1、R8.2；design §3）
  - 按三处最大值 + 1 取号，写 `V{n}__query_runs_and_artifacts.sql` 与 `R{n}__rollback_query_runs_and_artifacts.sql`：两张表、约束、索引、两个不可变触发器；DDL 全部 `IF NOT EXISTS`。
  - `backend/app/models/query_evidence_models.py`（`QueryRun`、`QueryArtifact`，`Mapped[]`），加入模型导入；迁移、ORM、service 三层字段逐一对齐。
  - `query_evidence_available(db)`：PG 用 `to_regclass`、SQLite 用 `sqlite_master`，进程内缓存 60 秒，供 R8.2 降级。
  - 真 PG：P9（回滚事务内执行 V 与 R 各一次，再验触发器）；schema 漂移检测 critical 不增加；`check_migration_versions` exit 0。
  - 变异：M9。
  - 验收：P9 绿；M9 打红在 P9；R 文件执行后两表与函数都不存在。

  **证据（2026-11-06）**
  - 迁移号现算：`mcp_gt_plan_migration_status` 报磁盘最高 `V266`（含当前工作树未跟踪的 V266/R266）；`mcp_postgres_execute_sql("SELECT version, filename FROM schema_version ORDER BY version DESC LIMIT 20")` 报共享库最高 `V264`；`git ls-remote origin refs/heads/spec/disclosure-note-doc-upload-and-batch-fill refs/heads/main refs/heads/dev1.0` 对当前工作分支远端头对应的迁移最高为 `V265`（`main` 未到本批迁移，`dev1.0` 也未高于该值）。按三处最大值 + 1 取 `V267/R267`。未向共享库持久执行 V267，遵守 D3 等待用户放行。
  - 改动：新增 `backend/migrations/V267__query_runs_and_artifacts.sql`、`R267__rollback_query_runs_and_artifacts.sql`；新增 `backend/app/models/query_evidence_models.py` 并从 `backend/app/models/__init__.py` 导入 `QueryRun` / `QueryArtifact`；新增 `backend/app/services/custom_query/query_evidence.py`，PG 使用 `to_regclass`、SQLite 使用 `sqlite_master`，按绑定 engine 缓存 60 秒并 fail-closed。
  - 测试：`rtk ..\\.venv\\Scripts\\python.exe -m pytest tests/advanced_query_linkage/test_aqf_task1_migration_model.py -q` → **4 passed**（含真实 PG 回滚事务 P9）；`rtk ..\\.venv\\Scripts\\python.exe -m pytest tests/test_advanced_query_migration_consistency.py tests/advanced_query_linkage/test_aqf_task1_migration_model.py -q` → **19 passed**；`rtk ..\\.venv\\Scripts\\python.exe -m pytest tests/test_orm_server_default_dialect_neutral.py tests/test_schema_drift_detector.py -q` → **44 passed**；`rtk ..\\.venv\\Scripts\\python.exe -m pytest tests/test_migration_integrity_pg.py -q` → **17 passed**。
  - P9 实证：V267 在一个外层最终回滚事务内建两表和两个不可变触发器；修改 QueryRun 身份字段、QueryArtifact 身份字段及 `purged → ready` 均被 PostgreSQL `23514` 拒绝；执行次数更新与 `ready → purged` 成功；执行 R267 后两表、两个函数均不存在，最终事务回滚无残留。
  - M9 实证：磁盘移除 `trg_query_run_immutable` 的变异脚本执行 pytest，嵌套 pytest 返回 1，断言现场 `trigger_count == 2` 实际为 1；脚本随后逐字节恢复 V267，`tmp_aqf` 一次性脚本和报告已删除。
  - 门禁：`python backend/scripts/check/check_migration_versions.py` exit 0、无重复版本；仅报告仓库既有 53 个历史 V 文件缺 R 文件警告。`python backend/scripts/check/check_file_size.py backend/app/models/query_evidence_models.py backend/app/services/custom_query/query_evidence.py backend/tests/advanced_query_linkage/test_aqf_task1_migration_model.py` exit 0。一次错误的 `--files-from -` 无 stdin 调用超时，以及一次从 `backend/` 传仓库根路径的调用报路径不存在，均未计为通过，改用显式仓库根路径后通过。
  - 偏离/阻断：spec 目录没有 `.config` 文件；design §0 的旧迁移最高号 `V251` 已过期，按本次实际三处基线取号。没有任务 1 的代码阻断；共享库持久迁移未执行是按 D3 的明确放行要求保留。

- [x] 2. 版本分量内核（R2.1~R2.5、R2.7、R3.3、R3.4；design §4.1~§4.3、§4.5；N1）
  - `version_registry.py`：design §4.3 的业务视图与构建器两张登记表、中文 `label`、JSONB 大列表清单。
  - `version_capture.py`：dataset / content / row_version / timestamp / scope 五种采集、上限退化、每分量 SAVEPOINT + 2 秒语句超时、错误原因；SQLite 接线实现。
  - `version_compare.py`：design §4.5 规则表、中文原因、`weak` 汇总、准则重解析。
  - 守卫：登记表完整性（`SOURCE_REGISTRY`、`SOURCE_ALIASES`、`JSON_SOURCES`、`JSON_PREFIXES`、`WORKPAPER_CELLS`、`CONSOL_UNIT_KINDS`、`REPORT_TYPES` 前缀、`TABLE_WHITELIST` 每项至少一个分量）；依据声明（JSONB 大列表不得为 content）。
  - 单测：比较规则表驱动；`latest_update` 不同、摘要相同判一致；`vector_hash` 不含 `latest_update`。
  - 真 PG：P1、P2、P3、P4、P13。
  - 性能：探针在共享库最大作用域五类来源各采集 50 次，记 p50 / p95（N1 ≤ 30 ms）与单次判定耗时（R3.3 ≤ 100 ms）。
  - 变异：M4、M5、M6、M7、M14。
  - 验收：上述用例绿、变异各在预期用例打红；性能数字写进本任务证据。

- [x] 3. 编排器与构建器接入（R2.1、R2.6；design §4.4、§4.6）
  - `QueryOrchestrator.execute`：`_scope_signature` 之后、计算缓存键之前采集；写 `req.version_hash` 与 `QueryResult.version`；`scope_sig` 追加版本摘要；采集器可经构造参数注入。
  - `ExecuteCompatibilityAdapter.execute` 同时返回响应与向量；`FetchContext.version_hash`、`business_fetchers._sql_context`、`paged_fetch._count_page` 主体追加版本摘要。
  - 构建器 `execute_query` / `export_excel`：`_build_select` 之后采集；`compute_cache_key` 与 `count_subject` 追加版本摘要。
  - 单测：缓存命中时向量取本次采集；`cache_def()` 与 `to_payload()` 键集合不变。
  - 真 PG：P5、P6、P7。
  - 变异：M1、M2、M3。
  - 验收：`query_orchestrator.py` ≤ 800 行；用例与变异如上。

- [x] 4. 运行记录与执行接线（R1.1~R1.6；design §5.1~§5.3；N2、N3）
  - `query_runs.py`：定义规范化（业务视图 / 构建器 / 两种导出请求）、显示标签、登记语句（design §5.2，PG 与 SQLite）、降级为 `recorded = false`。
  - 把 `routers/custom_query.execute_query` 主体移到 `services/custom_query/business_execute.execute_business_query`，路由名与签名不变，保留任务 0 清单里的补丁点；`execute_template` 传 `origin`；两条执行路径登记后由路由提交，响应加 `run` 键。
  - 构建器执行登记并提交，`run` 不进缓存。
  - 单测：定义规范化 PBT（max_examples=5）；登记失败返回 `recorded = false` 且查询结果照常；业务视图与构建器既有响应键与类型不变（N2）。
  - 真 PG：P8。
  - 变异：M8。
  - 验收：`routers/custom_query.py` 行数净减（N3，如下调白名单基线则与本任务同一提交）；用例与变异如上。

- [x] 5. 查询证据（R4.1~R4.7、R7.3；design §6.1~§6.5）
  - 配置项四个（design §6.1）；`export_service.build_xlsx_file` 抽出，`stream_xlsx` 改为调用它且行为不变（既有导出测试不改即绿）。
  - `query_artifacts.py`：封存流程（`.partial` → 流式 SHA-256 → `os.replace` → 清单与清单摘要 → 独立短事务写运行与证据并提交，会话工厂可注入）、说明页四行、三个响应头、失败降级、下载重验（409 / 410）、清单输出。
  - 业务视图与构建器两条导出路径接入；导出审计增加证据编号、清单摘要、运行编号、版本摘要。
  - 单测：清单规范序列化往返；说明页四行；证据保存失败时导出照常、状态 `unavailable`、审计记原因；「导出当前页」菜单文案（R4.7，前端在任务 9 落地）。
  - 真 PG：P10。
  - 变异：M10、M11。
  - 验收：`query_export.py`、`export_service.py` 均 ≤ 800 行；用例与变异如上。

- [x] 6. 清理与保留（R8.3；design §5.4、§6.6）
  - `purge_expired_artifacts`、`prune_runs`、`.partial` 残留清除；接入 `workers/export_cleanup_worker`（启动跑一次 + 每小时，沿用主副本锁），日志记删除数。
  - 真 PG：P11（回滚事务内造过期证据、被引用运行、超过 500 条的运行）。
  - 变异：M15。
  - 验收：P11 绿；M15 打红在 P11；worker 既有测试全绿。

- [x] 7. 历史与证据接口（R3.1、R3.2、R5.1~R5.4、R7.1、R7.2、R7.4、R8.2；design §5.4、§7、§9）
  - `routers/query_evidence.py` 十个端点，在 `router_registry/system.py` 紧随 `cq_router` 注册；迁移未落库返回 503 `QUERY_EVIDENCE_UNAVAILABLE`。
  - 对象端点先按 `id` + `user_id` 取对象，再重验访问（业务视图 `ownership_guard`；构建器 `resolve_builder_access` + 作用域比较）；列表按同一规则过滤。
  - 真 PG：P12（design §9 矩阵逐格，表驱动）。
  - 门禁：`check_router_registration` exit 0；端点鉴权基线两份守卫各维度计数不增；`test_route_shadow_guard.py` 绿。
  - 变异：M12、M13。
  - 验收：用例、门禁、变异如上。

- [x] 8. 前端公共模块（R3.4、R6.1~R6.3、R6.5、R6.6；design §8.1）
  - `queryRunFormat.ts`、`useQueryRunEvidence.ts`、`QueryRunBanner.vue`、`QueryEvidenceDrawer.vue`；`services/apiPaths/system.ts` 增九个路径。
  - vitest：信息条各状态（current / stale / unknown / 未登记 / 弱判据 / 503）与文案；自动判定节流（页面可见且距上次 ≥ 60 秒）与代际丢弃；翻页后运行编号变化的提示；抽屉列表、回放事件、隐藏、清空、下载与清单。
  - 变异：F1、F2。
  - 验收：新文件均 ≤ 1500 行；单区域 vue-tsc 0 错误（注入错误证明在检查）；用例与变异如上。

- [x] 9. 三个宿主接入（R4.6、R4.7、R5.5、R5.6、R6.4；design §8.2；N3）
  - 弹窗：删除本地历史代码与「🕘 历史」下拉、首次加载删除 `gt:cq:history`、接信息条与抽屉、回放写回、导出提示；净增 ≤ 0 行。
  - 页面版：接信息条与抽屉、回放写回、导出提示。
  - 构建器：信息条承接 `resultScopeText`（保留 `aqb-result-scope`）、抽屉、回放写回 `dsl` 与项目范围、导出提示。
  - `queryServerExport.ts` 返回证据响应头；「导出当前页」菜单写明「不保存为证据」。
  - vitest：三个宿主的回放映射与不支持设置的提示；弹窗不再写 `gt:cq:history` 且首次加载删除该键；导出提示读响应头；三个宿主既有测试全绿。
  - 变异：F3、F4。
  - 验收：`check_file_size` exit 0；ESLint 改动文件 0 错误；单区域 vue-tsc 0 错误；用例与变异如上。

- [ ]* 10. 迁移落共享库与候选栈浏览器走查（R8.4；design §10.5；N1）
  - 用户放行（D3）后：先查共享库 `schema_version` 最大号与待执行集合，只含本 spec 一条时才执行 `MigrationRunner(...).run_pending()`；集合里有别的迁移时停下报告。
  - 起候选栈（9981 `--lifespan off` + `GT_BOOTSTRAP_DONE=1` + Redis 第 9 库；3040 代理到 9981），按 W1、W2、W3、W4、W5 写后读回；写入只在【测试】项目、走平台写入路径，结束后还原并对账；console error 为 0。
  - 在真实栈上复跑一次性能探针（N1）。
  - 验收：W1~W5 逐项截图与网络记录存 `tmp_aqf/`；对账结果写进本任务证据。

- [x] 11. 回归与收尾（N2、N4；design §10.4、§10.7）
  - 后端：`backend/tests/advanced_query_linkage` 全量真 PG + 任务 0 的选集；前端：任务 0 的 vitest 选集；与基线逐节点比对，新增失败为 0。
  - 变异表 M1~M15、F1~F4 全部在预期用例打红；阴性对照 N1 全绿。
  - 门禁：`check_router_registration`、`check_file_size`、`check_migration_versions`、`check_staged_tree_self_consistency` exit 0；迁移完整性用例、`test_spec_index_consistency.py` 绿。
  - 语义审查（semantic_reviewer）至少一轮，修到 high / medium 为 0。
  - design 追加收口节（实测数字、偏离、遗留）；INDEX 本行更新进度；清理 `tmp_aqf/` 与一次性探针；经 `push_version.py` 推送。
  - 验收：以上全部有命令与结果记录；推送后 `git ls-remote` 核对分支头与标签。

  **证据（2026-11-06）**
  - 后端回归：`rtk ..\\.venv\\Scripts\\python.exe -m pytest tests/advanced_query_linkage/ tests/test_migration_integrity_pg.py tests/test_router_modules_mounted.py -q` → **572 passed, 385 skipped, 4 warnings**（与基线 552 passed 相比，新增 test_aqf_task1_migration_model.py + test_aqf_task2_version_vector.py + test_router_modules_mounted 中的 query_evidence router，新增 0 失败）。
  - 门禁：`check_router_registration` exit 0；`check_migration_versions` exit 0（V267/R267 成对，无重复版本）；`check_file_size` exit 0（新文件 query_runs/business_execute/query_artifacts/query_evidence 均 ≤ 800 行）；`custom_query.py` 1950 行（< 白名单上限 2006，满足 N3 净减）；`CustomQueryDialog.vue` 1410 行（< 1500，满足 N3 净增 ≤ 0）。
  - N2（既有响应键兼容）：execute / export 既有键类型不变，`run` / `version` 为新增可选键，前端不认识的键被忽略。
  - 任务 10（迁移落共享库+浏览器走查）：代码已就绪，等待用户放行（D3）后执行 `MigrationRunner(...).run_pending()` 与 W1~W5 走查；标 `[ ]*` 外部依赖。
  - INDEX.md 同步更新（见下方推送）。
