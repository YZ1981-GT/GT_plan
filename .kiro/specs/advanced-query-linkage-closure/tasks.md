# 实施计划：高级查询联动闭环（advanced-query-linkage-closure）

> 每个任务 = 一个可独立测试的交付单元；引用 `R x.y` / `ADR-AQL-NN` / 变异 `#N`（design §10.4），不复述。标 `[ ]*` 的任务依赖外部运行环境（start-dev 运行环境 / 合并项目数据），未实测时保持未勾，并在任务下写「代码已改但未实测」。
> 通用纪律：后端测试 `rtk ..\.venv\Scripts\python.exe -m pytest <文件> -q -p no:playwright`（cwd `backend`）；前端 `rtk npx vitest run <文件>`（cwd `audit-platform/frontend`）；改前端后跑单区域 vue-tsc（先例 `tsconfig._g-single-region.json`），并用一条故意的类型错误证明它会报错；真 PG 测试只用回滚事务或【测试】/【UAT】项目；每个任务开工前对涉及文件重跑现状确认（grep / 行数 / 调用方）并写入勾选说明（design §12）；每个断点在根因处修复并配一条防御测试；临时产物放仓库根 `tmp_aql_linkage/`；勾选必须附测试命令与结果摘要，依赖环境的项不得改标星或假绿。
> 依赖：0 → 1 → 全部；2 → 35；1 → 6 → 7；3 → 4 → 5 → 7 → 8；7 → 16~23、26；9 → 10 → 11；9 → 23；12 → 23 → 30；13 → 14、15；24 → 25 → 33；27 → 28~33；11、26 → 28~30；28~34 → 35 → 36 → 40~44（W3）→ 45~47（W6）→ 37*、38* → 39。W3、W6 两批互不依赖，可按实施时的依赖调换先后（两批都改弹窗，先做的一批提交后另一批再开工）；40 → 41 → 43 → 44，42 独立；45 → 46 → 47。
> 与评估 report.md §7 批次表的对应（编号按加入顺序，执行按阶段顺序；阶段 H、I 是用户 2026-10-26 追加的 W3、W6 两批，在批次表之外，排在全部断点任务之后）：
>
> | 阶段 | 任务 | 断点 | 与批次表的差异及理由 |
> |---|---|---|---|
> | 0 | 0 | — | 新增：本地与远端分叉，合入后才开工（第 2 轮评审 #1） |
> | A 测试地基 | 1、2 | AQ-32（夹具部分） | 批 6 → 最先：后面每个任务都要靠能跑的构建器测试与权限配方表验收 |
> | B 口径、计数与隔离 | 3~12 | 批 1 的 AQ-02、03、06、19；另含 AQ-25 的 batch-execute 族（任务 6）、AQ-13 / 18 / 21 / 28 的后端部分、AQ-26 的默认排序、AQ-27、AQ-32 的假绿用例改写 | batch-execute 直接调 router 内取数器，须先于取数器下沉删除（第 1 轮评审 #6）；构建器的准入、作用域、total、公式引用都在 `builder_dsl` / `query_builder` 两个文件里，随作用域一起改省返工 |
> | C 写入安全 | 13~16 | 批 2 的 AQ-04、05、23 | 无 |
> | D 数据源 | 17~23 | 批 3 的 AQ-01、07、08、10、11、12、26、33；另含 AQ-31（任务 19）、AQ-35（任务 22）与 R3.8 循环范围（任务 23） | 指标树与附注源同一处改（AQ-31 随 AQ-10）；列标签跟着新列走（AQ-35 随 AQ-26 / 33）；R3.8 是第 1 轮评审 #14 新增、不在批次表 |
> | E 模板与导出后端 | 24~26 | 批 4 的 AQ-16、30；批 5 的 AQ-20 | 无 |
> | F 前端联动 | 27~33 | 批 4 / 5 的 AQ-09、13、14、15、17、18、20、21、22、24、28、29、31、34（页面级）、36、37；新断点 AQ-38（任务 31） | AQ-38 是第 2 轮评审新发现（模板库按钮源键恒 400），与入口上下文同一处修 |
> | G 收敛与验收 | 34~36 | 批 6 的 AQ-25（其余删除）、AQ-32（e2e 与变异） | 无 |
> | H W3 / I W6 | 40~44 / 45~47 | AQ-34 的行级入口由 W6 交付 | 用户追加 |
> | J 实测与收尾 | 37*、38*、39 | — | — |

## 阶段 0　分支同步（阻塞全部任务）
- [ ] 0. 合入远端与现状重算（requirements A6；design §1、§9、§14.4）
  - `git fetch --prune`，现算 `git rev-list --left-right --count HEAD...origin/spec/disclosure-note-doc-upload-and-batch-fill`；落后数不为 0 时按简报分叉规则暂停（send_message warning），把两边提交列表交用户决定合入方式，用户决定前不开工任何任务；不改写历史、不 stash、不 `--no-verify`
  - 合入后确认 `git merge-base --is-ancestor d0de87a6c HEAD` 为真，重算并写入本条：design §1 的年度 / 行数门 / 循环范围三行、§9 全表的「现状」列（`check_file_size.py` 门限与 HARD_CAPS、`test_hard_cap_ratchet.py` 结果）、年度兜底基线与 `CALENDAR_YEAR_EXEMPT` 中与本 spec 相关的条目、`deps.require_project_audit_year` 与 `effective_scope.resolve_member_scope` 的签名（`inspect.signature` 打印一次）；与 design 不符的数字在本条写明差异，结论不同的停下改 design 再开工
  - 对本 spec 全部目标文件现查 `git status`，有他人未提交改动的文件列入本条，后续任务只改、只提交自己的块

## 阶段 A　测试地基
- [ ] 1. 测试地基与基线（R12.3、R12.5 底座；在任务 0 合入后的树上跑）
  - `tests/test_query_builder_endpoint.py`、`tests/test_query_builder_joins.py` 夹具改为只建构建器所需表（`Base.metadata.create_all(tables=[…])`），两文件 32 条恢复运行
  - `tests/authz_world.py`：`sqlite_world` / `pg_world` 增可选参数 `extra_tables`（缺省仍只建六张表，`test_world_has_exactly_the_six_tables` 不变）；`test_authz_world.py` 加「extra_tables 建出、缺省仍六张」用例
  - 新建 `tests/advanced_query_linkage/conftest.py`：`pg_only`、金标准 SQL 助手（统计排除软删项目）、真库回滚事务会话夹具
  - 前端 `advancedQueryFrontend-p7.spec.ts`「legacy global 显示为公开」超时：定位 `mountTabForScope('manager')` 不 resolve 的根因并修复（禁止只调大超时）
  - 现跑评估列出的 10 个后端 + 4 个前端测试文件，以及 `tests/scripts/test_hard_cap_ratchet.py`、`auditYearCalendarFallbackRatchet.spec.ts`，结果写入本条作为回归基线（合入前本地已红的棘轮用例合入后应转绿；合入后仍红的写明归属，不算到本 spec 头上）
- [ ] 2. 端点权限配方表骨架（R12.5、N2，design §10.3）
  - 新建 `tests/advanced_query_linkage/test_aql_endpoint_authz.py`：基于 authz_world 表驱动，design §10.3 的 29 行（W3 的第 30~32 行在任务 41 补）逐格按「底座」列选 `sqlite_world` / `pg_world`；PM、SM 按 §10.3 补 `eqcr_assignment("manager")`（每个身份只调一次），PM / SM 走到循环范围的格 `extra_tables` 含 `wp_index`；第 25 / 26 行的世界在 X、Y 各造一行 trial_balance 并断言结果非空；循环受限身份 CR 的子表（23c、25c、26c、28c）一并建好；现已成立的格直接断言，待修复的格 `xfail(strict=True)` 并注明修复任务号
  - 路由对账：custom_query、custom_query_writeback、query_builder 三个 router 的每条路由都出现在表中，缺失即红（新增路由在其任务里补行）

## 阶段 B　口径、计数与隔离（P0）
- [ ] 3. 多项目数据集谓词（R1.2；design §3.4）
  - `services/dataset_query.py` 新增 `active_rows_predicate(db, table, *, project_ids, year)`（先查生效数据集再按 id 过滤，排序同 `DatasetService.get_active_dataset_id`，查询失败原样上抛）
  - PG `test_aql_dataset_predicate_pg.py`：每个活项目年度与 `get_active_filter` 行集合相等（含宜宾临港店与无生效数据集的项目）；SQLite 上编译执行不报错
- [ ] 4. 源注册表与 SQL 分页内核（R2.1~R2.3、R6.1~R6.3、R12.2，ADR-AQL-03 / 06；变异 #14）
  - 新建 `services/custom_query/source_registry.py`（design §3.1 全部 SQL 源）、`services/custom_query/paged_fetch.py`
  - `param_sql_builder.build_portable_filter`（in / not_in / prefix / nonempty）；`build_filter` 的 like / not_like 转义；`builder_dsl._build_filter` 改为委托
  - 单元测试 `test_aql_source_registry.py`：列与 ORM 反射一致；未知筛选键 / 条件字段 / 算子 / 列 400；postgresql 方言编译后断言 WHERE、ORDER BY 末项唯一键、NULLS LAST 只在可空列、用户值参数化；like 按字面匹配 `%` `_`
- [ ] 5. 编排器与 execute 契约接入 FetchPage（R2.1~R2.5、R2.8、N3）
  - `query_orchestrator.py`（FetchPage、conditions / condition_logic 进 cache_def、meta 往返）、`execute_compatibility.py`、`services/query_cache.py`（canonical identity）、`pagination.py`（删 SQL 源默认排序条目；内存源默认 `_row_index`；`TIE_BREAKER_CANDIDATES` 以 `_row_index` 打头）、router `QueryRequest` 新字段
  - 单元测试 `test_aql_orchestrator_fetchpage.py`（含内存源行序与同值保序）；`TestExecuteContractBaseline` 保持全绿
- [ ] 6. 删除 batch-execute 族（R12.1，ADR-AQL-13；单独提交，必须先于任务 7）
  - 删前 grep 生产调用方为 0（结论写入本条），跑 `test_batch_query.py`、`test_function_global_names_ratchet.py` 等作基线
  - 删 `POST /batch-execute` 及其请求 / 响应模型、`BatchQueryToolbar.vue`、`composables/useBatchQuery.ts` 与 `useBatchQuery.test.ts`、`customQuery.batchExecute`；按 design §3.9 删改相关用例
  - `auditYearCalendarFallbackBaseline.json` 删 `composables/useBatchQuery.ts` 一行（只改这一行；该文件是共享文件，提交前 `git diff --cached` 只含这一块），删后跑 `auditYearCalendarFallbackRatchet.spec.ts`
  - 删后同组测试全绿；提交前打 tag
- [ ] 7. 取数分派切换与取数器下沉（R2、N4）
  - `business_fetchers.py` 改为注册表分派，删跨模块单元格分支与 `fetch_cap_warning`；同时删 `routers/custom_query.py` 里它的导入与调用（现 L1145 导入、L1200 调用，行号开工时现查），删后跑 `test_function_global_names_ratchet.py` 与 `test_lazy_import_resolvability.py`
  - 新建 `services/custom_query/fetchers/{__init__,disclosure,worksheet,workpaper_cells}.py`（行为原样迁移，只读改造在任务 16）；router 删 14 个 `_query_*`，`_query_disclosure` 由 fetchers 再导出
  - 改写依赖旧分派的测试（`test_advanced_query_hardening_wave012.py` 的 `_query_trial_balance` 替身用例），理由写入本条
  - `backend/scripts/file_size_whitelist.txt` 中 `custom_query.py` 基线下调为真实行数（只改这一行）
- [ ] 8. 业务视图口径真 PG 回归（R1.1、R1.3、R2.1~R2.5、R2.7、R5.8，ADR-AQL-07；变异 #1、#3、#4）
  - `test_aql_business_view_pg.py`：宜宾临港店科目余额；和平药房序时账 total、借方降序首行、第 N 页与相邻页不重叠、offset 超限 422；科目 1002 分组 > 5,000 ⇒ 400；华氏试算表首行与 Σ审定；底稿清单；无生效数据集的 warnings；查生效数据集失败（在下一层注入异常）⇒ 500 而不是退化为不过滤
  - 记录和平药房序时账首页耗时（N1）
- [ ] 9. 构建器作用域（R1.2、R3.1~R3.3、R3.5 后端；变异 #2、#5、#16）
  - `builder_scope.py`（`resolve_builder_scope` 新参数、`scope_predicates`、已删项目排除、projects 按 id、staff 角色门、report_config 副本行、数据集谓词预先算好）、`builder_dsl.py`（QueryDSL `project_id` / `year`；基表谓词进 WHERE 最后一步、JOIN 目标谓词进 ON）、`table_whitelist.py`（`DATASET_SCOPED_TABLES`、`ROLE_RESTRICTED_TABLES`）、`routers/query_builder.py`（三端点传 `requested_project_id` 与 `year`）
  - 测试：方言编译断言（目标谓词在 ON）+ PG（宜宾计数、e2e_manager 的 projects 先按「可访问 − 已删」断言（循环受限排除在任务 23 加上后改为 design §10.2 的金标准）、指定不可访问项目 403、staff 对 manager 403、design §10.2「LEFT JOIN 无匹配行」、report_config 副本行只给可访问项目）
- [ ] 10. JOIN 基数登记（R3.4；变异 #6）
  - `table_whitelist.JOIN_WHITELIST` 按 design ADR-AQL-09 表逐条加 target_where 与 cardinality，删除 report_line_mapping → report_config；导入期不变式；schema 下发 cardinality；一对多 warning
  - PG 守卫 `test_aql_join_cardinality_pg.py`：逐条覆盖保留的 11 条登记——多对一在活项目上 LEFT JOIN 后行数不变，一对多产生 warning；被删登记请求返回 400 `JOIN_NOT_REGISTERED`
- [ ] 11. 构建器 total、排序与公式引用（R2.2、R2.6 后端、R3.7，ADR-AQL-18）
  - `builder_dsl.build_count`；可空列 `.nulls_last()`；`query_builder.execute` 的 total = COUNT；`_derive_formula_refs` 对 tb_balance 返回 None
  - 改写 `test_query_builder_formula_ref_grammar_v1.py`（design §10.1）
  - 测试：和平药房 total = 金标准、借方降序首行非空；PG 校验华氏每条 formula_ref 经地址库有效
- [ ] 12. 构建器准入（R3.6 后端、R11.3，ADR-AQL-08；变异 #13）
  - 新建 `services/custom_query/builder_access.py`；`require_query_builder_access` 改 async；新增 `GET /api/query/access`（admin / partner 返回 `all_projects`；其余身份的计数先按「可访问 − 已删」，循环受限排除与空作用域 reason 在任务 23 补）；`tests/authz_world.py` 把新门禁登记进 `PRODUCTION_GATES` 与 `_GUARDED_MODULES`
  - 改写 `test_query_builder_role_gate_pbt.py`（await 异步依赖）；新测试覆盖系统角色、项目经理、只读成员、已删项目成员

## 阶段 C　写入安全（P0 / P1）
- [ ] 13. 删除 tb / adj / report 回写实现（R4.1，ADR-AQL-02；单独提交）
  - 删前 grep 调用方（结论写入本条）并跑基线；`snapshot_writer_modules.py`、`snapshot_writer.py` 删三模块；`CellWritebackRequest` 与 writeback 目标的 module 改 `Literal["workpaper", "note"]`
  - 改写 `test_snapshot_writer.py`、`test_custom_query_auth_bug_condition.py`、`test_custom_query_auth_preservation.py` 中依赖三模块的用例（改为断言 422）；`file_size_whitelist.txt` 里 `test_snapshot_writer.py` 的基线按实际行数下调；删后同组测试全绿；提交前打 tag
- [ ] 14. 回写取行带项目条件与预览门（R4.2、R4.5；变异 #11、#21）
  - `snapshot_writer.py` 底稿取行（新异常 `WritebackTargetNotFound`）、`write_note_cell` 取行、`writeback_preview.py`（`_build_item` 归属核对、`_read_workpaper_value` 带项目、有 `found=False` 即不可确认）；cell-writeback 与 writeback-confirm 异常映射（design §3.7）
  - 改写 `test_writeback_preview.py` / `test_writeback_pbt.py` 中固化缺陷的断言；单测覆盖「全部可定位 → 可确认」「一个不可定位 → 不可确认」
  - PG `test_aql_writeback_isolation_pg.py`：design §10.2「回写不锁他项目行」「回写预览门」两行
- [ ] 15. `publish_rows` 调用方棘轮（R4.3；变异 #9）
  - 新建 `tests/advanced_query_linkage/test_aql_publish_rows_callers.py`：AST 收集 `publish_rows` 的导入与调用，登记集 = design §1 所列的 5 个他域调用方（任务 13 删掉 `snapshot_writer_modules` 那一处之后）；高级查询包零调用；登记集多一个或少一个都红
- [ ] 16. 查询路径只读（R4.4；变异 #10、#10b）
  - `fetchers/workpaper_cells.py`：无文件提示、写盘只在 `_temp_copy`、`recompute_with_libreoffice` 只返回字节；router `wp_sheet_preview` 改调它
  - AST 守卫：模块内无 `init_workpaper_from_template`；`shutil.copy*` / `.write_bytes` / `.write_text` / 写模式 `open` / `os.replace` / `shutil.move` 只出现在 `_temp_copy`；`_temp_copy` 的调用点都传 `tempfile` 目录；`recompute_with_libreoffice` 返回 bytes 且函数体无写调用
  - PG：前后 sha256 与 mtime 不变；LibreOffice 不可用时的 warnings

## 阶段 D　数据源（P1）
- [ ] 17. 报表源与报表行次（R5.1、R5.3；变异 #8、#20）
  - 注册表 report 源（准则 = `resolve_applicable_standard`，准则行 ∪ 本项目独有行，LEFT JOIN financial_report，未生成 / 过期 warnings）与 report_lines 源（row_number，项目副本行限本项目）
  - PG：华氏 BS-002 = financial_report 值；design §10.2「报表源结构」行；无报表的项目金额为空且有 warnings；报表行次可查且按行号排序
- [ ] 18. 调整分录源（R5.2；变异 #7）
  - adj_aje / adj_rje、adj_rcl 兼容、大写值归一、通用源全部类型 + 类型列、entry_group_id 隐藏列；consol_unit 调整分录改小写枚举
  - PG：华氏 AJE 行数 = 金标准；无 RJE 的项目返回 0 行不报错；通用源行数 = 全部类型金标准
- [ ] 19. 附注源与项目章节树（R5.4，ADR-AQL-16；变异 #17）
  - `fetchers/disclosure.py`（附注目录、按表返回、`meta.tables`、`_row_index`、章节集合取 `get_notes_tree`）；router `get_indicators` 增 `year` 与 `X-Notes-Version`，`_build_disclosure_tree` 增项目分支（函数名不变，更新测试替身签名）
  - PG：华氏叶子与 `get_notes_tree` 章节集合、顺序一致；「八、1」第一张表行数与行序 = `table_data`（合计行最后）；表切换返回第二张表；附注更新后 `X-Notes-Version` 变化
- [ ] 20. 指标树按项目形态（R5.5、R5.7 叶子列，ADR-AQL-10 / 16）
  - 单体隐藏 tb_summary / ws_* 并更名；叶子 columns 与 supports_conditions 由注册表生成；调整分录叶子改名；schema 版本 11
  - 单元测试：叶子列 == 注册表显示列；单体 / 合并两种树形
- [ ] 21. 辅助核算源与构建器白名单扩充（R5.6）
  - 注册表 aux_balance / aux_ledger（`required_filters`、跨维 warnings）；`table_whitelist` 增 tb_aux_balance / tb_aux_ledger / financial_report（超 800 行按 design §9 先抽伴生模块）
  - PG：和平药房某科目带 aux_type 筛选的行数 = 金标准；辅助明细不带筛选 400；构建器查 tb_aux_balance 的口径同 R1；辅助明细首页耗时记录（N1）
- [ ] 22. 列补齐与标签（R5.7、R6.6）
  - 试算表 rje_adjustment、余额方向列；`queryColumnLabels.ts`（summary「摘要」、ws_consol_tb 覆盖为「汇总数」、新列中文）+ `queryColumnLabels.spec.ts`
- [ ] 23. 循环范围（R3.1、R3.5、R3.6 计数、R3.8，ADR-AQL-08 / 19；变异 #19、#19b、#36）
  - 二次确认分支含远端提交 d0de87a6c（`git merge-base --is-ancestor d0de87a6c HEAD`，任务 0 已合入）；不在本 spec 里复制 `effective_scope`
  - 新建 `services/custom_query/cycle_scope.py`（`CycleScopeCache`、`resolve_cycle_scope` / `is_cycle_restricted`，只调 `deps.get_user_scope_cycles`）；接入试算表、调整分录、附注目录 / 章节与附注树（严格过滤，`SECTION_OUT_OF_SCOPE`）；`resolve_builder_scope` 逐个可访问项目排除受限项目（`CYCLE_SCOPED_PROJECT`，同一请求共用缓存）；access 接口计数改为排除后、作用域为空时给 reason（design §3.4）
  - PG：design §10.2「循环范围」行（团队分配勾选、主管不限、勾选为空即无行三种，带缓存与不带结果相同）；e2e_manager 用例改为 §10.2 金标准（现库期望 0 行 + 排除 warning）并加 u_011abb97dd2d4101 正例；配方表 CR 子表与第 23 行计数列转正

## 阶段 E　模板与导出后端（P1 / P2）
- [ ] 24. 模板后端（R9.1~R9.3，ADR-AQL-11；变异 #12）
  - `template_service.py`（只用 adapter 归一与可见性、`visible_templates`、`config_to_request`、错误码 `TEMPLATE_NOT_VISIBLE`）；`template_scope_adapter.py` 报错改中文；router 模板端点（list / get / execute 走 service、`TemplateForbiddenError` → 403、`TemplateInvalidError` → 400、删 update 末尾的原值覆盖、execute 分页，年度经 `deps.require_project_audit_year`；参数占位的取值在任务 41 接入）
  - 改写固化旧 scope 模型的断言（design §10.1 所列三个文件），逐条写明理由；新用例：非作者执行私有模板 403、更新 `scope=global` 入库为 public、adapter 报错为中文
- [ ] 25. 模板软删与回收站（R9.5，ADR-AQL-11；迁移 design §8）
  - 迁移 V{n} / R{n}（号实施时现扫并写入本条）；ORM 混入 `SoftDeleteMixin`；`template_service.soft_delete`；`routers/recycle_bin.py` 作者类型（作者 = `coalesce(creator_id, created_by)`，列表逐行 `can_restore` / `can_purge`）；`views/RecycleBin.vue` 按钮改 `canRowAct`（design §3.6，行数 ≤ §9）；`MigrationRunner(...).run_pending()` 落本地库
  - 测试：软删后列表 / 详情 / 执行 404；回收站作者与 admin 可见、可恢复、可彻底删除，他人 403；列表里模板行带 `can_restore` / `can_purge`、其余类型不带；vitest：系统 auditor 作者看得到并能点「恢复」，其余类型照旧按权限表（design §10.1 回收站条）；列 / 索引 / 约束存在，R 文件可回放
- [ ] 26. 服务端完整导出（R8.1~R8.6，ADR-AQL-14；变异 #18）
  - `export_service`（`info_rows`、`_text_safe_cell` 接入数据行 / 表头 / 查询说明）；新建 `services/custom_query/export_gate.py`；`POST /api/custom-query/export`（首块预取、导出槽在生成器 finally 释放、审计）；`query_builder.export_excel` 改用 export_service（同一导出闸、COUNT 预检、headers、去掉 1,000 行限制）
  - 单元：导出闸 429 / 释放 / 幂等；PG：design §10.2「导出」行；10 万行导出耗时记录（N1）

## 阶段 F　前端联动（P1 / P2）
- [ ] 27. 前端公共模块（R7.1~R7.3、R10.3、R10.4、R11.1~R11.2，ADR-AQL-01 / 16 / 18；变异 #15）
  - 新建 `queryResultLinks.ts`（含 `validatePageRefs`）、`queryErrorText.ts`、`queryEntryContext.ts`（含 `resolveDialogOpenContext`）、`queryTemplateCache.ts`、`queryIndicatorCache.ts`；`useLedgerUrlSync.ts` 抽出 `buildLedgerQuery`
  - vitest：ADR-AQL-01 每一行一条用例；四种引用语法；批量校验按 `ref` 回填、WP `not_found` 文案、请求失败全部不可用；422 / 429 / 500 / 信封对象文案；缓存键含年度与附注版本、版本变化不命中
- [ ] 28. 弹窗改造（R2.6、R7、R8.3、R10.1~R10.2、R11、N5，ADR-AQL-15）
  - `CustomQueryDialog.vue` 按 design §4.2，年度以合入后的 `localYear = ref<number | null>(props.year ?? null)` 为起点；`SheetCellRangePicker.vue` 年度改由父组件传入（合入后年度兜底基线已无这两个文件的条目，基线不动）
  - vitest：换路由后项目跟随、非项目页不自动选、年度为空禁用查询、错误不落空态、翻页显示 total、「仅筛选本页」、操作列打开 / 复制引用（不可用时显示原因）、结果区没有回写入口（R7.5）；操作、翻页、导出控件带 aria-label（N5，页面版与构建器同口径断言）
- [ ] 29. 页面版改造（R6.1~R6.5、R7、R10.2、R10.4、N5，ADR-AQL-12 / 16）
  - `CustomQueryTab.vue` 按 design §4.2，条件区做成独立组件 `components/query/QueryConditionEditor.vue`（W3 在弹窗复用）；改写 `advancedQueryFrontend.spec.ts` 的「今年 − 1」断言；删掉 `defaultAuditYear()` 后同步删除 `auditYearCalendarFallbackRatchet.spec.ts` 的 `CALENDAR_YEAR_EXEMPT` 中 `components/template-library/CustomQueryTab.vue` 一条（只改这一条，提交时只含这一块），跑该棘轮 spec
  - vitest：结构化条件与 AND / OR 进请求、未知字段提示、条件值框可输入、中文列名、ACNR 面板「开发中」且请求不带 acnr_targets、指标树带项目与年度加载
- [ ] 30. 构建器前端（R2.6、R3.5、R3.6、R6.5、N5，ADR-AQL-08 / 12）
  - `AdvancedQueryBuilder.vue`、`useQueryBuilderAccess.ts`（access 接口）、`services/apiPaths/system.ts`（queryBuilder 组）；改写 `test_advanced_query_hardening_properties_scope.py::test_p23_*`
  - vitest：无权禁用 + 原因、准入通过但作用域为空（`accessible_project_count = 0`）时禁用并显示接口 reason、默认当前项目、跨项目开关（计数 > 1 或 all_projects）、翻页
- [ ] 31. 入口上下文与模板库按钮（R10.1~R10.3、R10.5，ADR-AQL-15；AQ-38；变异 #33）
  - `ThreeColumnLayout.vue`：只新增 `customQueryYear`（`currentYear` 不动），经 `resolveDialogOpenContext` 处理 override / 侧栏预选 / 模板库源映射 / 关闭清空，弹窗增 `:initial-notice`；行数 ≤ design §9；年度兜底基线中 ThreeColumnLayout 条目保留
  - `queryEntryContext.resolveTemplateLibrarySource`；弹窗显示 `initialNotice`；三个模板宿主与 `TemplateLibraryButton` 不改（`TemplateLibraryButton.test.ts` 保持通过）
  - vitest：`resolveDialogOpenContext` 各分支；模板库三种载荷（design §10.1）；静态守卫用 `@vue/compiler-sfc` 解析模板，断言 CustomQueryDialog 的 `:year` 绑定 `customQueryYear`、FormulaManagerDialog 与 GtRefreshScopeDialog 的年度绑定仍含 `currentYear`
- [ ] 32. 报表与模板库深链、模板溯源（R7.1 报表行、R7.4，ADR-AQL-17）
  - 新建 `composables/useReportRouteFocus.ts`（`?tab=&highlight=`）；`ReportView.vue` 净增 ≤ 0（现跑 HARD_CAP 门禁）；`TemplateLibraryMgmt.vue`、`WpTemplateTab.vue`；router `address_resolve`
  - 测试：`wp_template_registry` 表不存在时 address-resolve 用 JSON 目录且不 500、页签名正确；vitest 覆盖普通模式、对比模式、矩阵报表三种情况与找不到行次
- [ ] 33. 模板选择组件（R9.3、R9.4）
  - 修复 `MyTemplatesDialog.vue` 并接入弹窗（载入 / 执行，执行走 `templateExecute`）与页面版（替换内联模板对话框）
  - vitest：列表解包、载入还原状态、执行与翻页、删除提示进回收站

## 阶段 G　收敛与验收
- [ ] 34. 删除其余收敛对象（R12.1，ADR-AQL-04 / 13；按 design §3.9 一类一提交）
  - 每类删前 grep 0 调用方、删前后跑同一组测试（跨模块单元格源族另跑 `test_lazy_import_resolvability.py`）、提交前打 tag；下调 `test_module_cell_resolver.py` 白名单基线；`SheetCellRangePicker.vue` 删模块模式
- [ ] 35. 权限配方表全部转正与磁盘变异（R12.5、N2，design §10.3 / §10.4）
  - 删除全部 xfail，路由对账通过；变异 #1~#21、#10b、#19b、#33、#35、#36 逐条打红（单独一条命令跑，在 `tmp_aql_verify` 里做，逐字节恢复后 sha256 核对），结果写入本条；W3 / W6 的变异 #22~#32、#34 在阶段 H、I 各自任务内按同样方式跑
- [ ] 36. 性能与 e2e 静态复核（N1、R12.4）
  - N1 三项实测，`EXPLAIN ANALYZE` 摘要写入本条；不达标按 ADR-AQL-06 预案①②处理后重测，仍不达标保持本条未勾并附实测与执行计划，索引迁移只提 W12 不执行
  - 两个高级查询 e2e spec 只做静态核对（路由、选择器是否还在）：过期的更新或删除，保留的写入任务 37 清单；实际运行归 37*

## 阶段 H　W3 常用审计预置模板（用户 2026-10-26 追加；R13，ADR-AQL-05；design §3.11、§4.3）
- [ ] 40. 条件能力扩展（R13.5，ADR-AQL-03；变异 #22、#23、#29、#30、#32）
  - `param_sql_builder`：抽 `_prefix_predicate`，`starts_with` 与 `prefix` 共用；新增 `_weekday_predicate`、`_blank_predicate`（`nonempty` 的 False 分支改调它）；`table_whitelist.OPERATOR_WHITELIST` 增三项；`paged_fetch` 的 `CONDITION_VALUE_REQUIRED`（含未解析的 `$param`）与 `BLANK_FIELD_INVALID`
  - `ledger_sampling_service.ledger_line_amount`（带 `type_`；`build_ledger_query` 两处改调，SQL 文本改前改后一致，`test_cutoff_sampling_pbt.py` 保持通过）；注册表 `SourceSpec.condition_only` 与序时账 `line_amount`；指标树叶子 `condition_fields`，schema 12
  - `QueryConditionEditor.vue`：按 dtype 给算子（含开头是、为空或空白、大于等于、小于等于、星期为）、条件行 `params` 标记、`toSavedConditions`、`incompleteReason`、`notices`、`EDITOR_OPS`；`queryColumnLabels.ts` 增 `line_amount`
  - 测试：单元（编译 SQL 与绑定参数、`coerce_value(ledger_line_amount(t), "1000000")` 为 Decimal、`weekday_in` 用于文本列 400、`is_blank` 用于数值列 400、空值 400）；PG design §10.2「新条件能力」行（字符串阈值经 TestClient、【UAT】空白摘要三行）；vitest（算子随 dtype、未填值禁用查询与保存、改值去掉 `params` 标记、`toSavedConditions`）
- [ ] 41. 预置定义与服务端解析（R13.1~R13.4、R13.8，ADR-AQL-05；变异 #24、#31）
  - `backend/data/custom_query_presets.json`（10 条，design ADR-AQL-05 表）；`services/custom_query/template_presets.py`（加载、校验含排序与每页行数、列表、`resolve_config` / `resolve`、`PARAM_NAMES`；重要性读取包 `begin_nested`）；`sampling_enhanced_service.cutoff_window` 与默认值常量（`run_cutoff_test` 改用，行为不变）
  - router 薄路由 `GET /template-presets`、`GET /template-presets/{preset_id}/resolve`、`GET /templates/{template_id}/resolve`，年度经 `deps.require_project_audit_year`；模板执行接入 `resolve_config`（任务 24 的执行管线前加一步）；保存 / 更新校验 `$param` 已登记；权限配方表补第 30~32 行，路由对账通过
  - 测试：单元（JSON 每条校验通过；坏条目逐类被跳过并记 ERROR；`cutoff_window` 与 `run_cutoff_test` 同窗、默认值相等；`config_to_request` 拒收未解析占位；未登记 `$param` 保存 400）；PG design §10.2「预置参数」「参数占位跨项目」两行
- [ ] 42. C24 词表单一来源（R13.3、R13.9；变异 #25）
  - 生成器 `backend/scripts/gen/gen_journal_entry_rules_ts.py`（`--write` / `--check`）→ `src/generated/journalEntryRules.ts`（`SPECIAL_EVENT_KEYWORDS`、`VAGUE_KEYWORDS_DEFAULT`）；`useC24AnalyticsEngine.ts` 规则 11 改为 import（只换常量）；`GtC24JournalDetail.vue` 默认 `vagueKeywordsText` 改读 `VAGUE_KEYWORDS_DEFAULT`（改 1 行 + 1 行 import，开工前现查白名单门限与 `git status`）
  - 测试：pytest 比对 `render(JSON)` 与磁盘文件；vitest：每个特殊事件词都被 `screenAnomalies` 标为「与特殊事件有关」、组件默认模糊词等于生成常量；C24 既有 spec（`useC24AnalyticsEngine.spec.ts` / `.pbt.spec.ts`、`GtC24JournalDetail.integration.spec.ts`）全绿
- [ ] 43. 模板列表「系统预置」与载入（R13.1、R13.2、R13.6）
  - `MyTemplatesDialog.vue` 预置分区（只读，「载入」「另存为我的模板」先调 resolve，emit `load(config, item, notices)` / `save-as`）；含参数占位的用户模板「载入」先调 `templates/{id}/resolve`；弹窗嵌入 `QueryConditionEditor` 并发 `conditions`；页面版与弹窗处理这两个事件（另存为默认名「{预置名}（我的）」，保存用 `toSavedConditions`）；周末、大额、模糊词说明经 `notices` 显示
  - vitest：预置行没有编辑 / 删除 / 执行；载入后不自动执行；留空阈值时查询与保存不可用并显示原因；无项目时按钮不可用；另存为后保存的 config 里阈值是 `{"$param": "materiality_performance"}`、用户改过的值是字面值；读 `backend/data/custom_query_presets.json` 断言每条预置的算子都在 `EDITOR_OPS` 内（R13.8）
- [ ] 44. 预置真库对账（R13.7）
  - 新建 `tests/advanced_query_linkage/test_aql_presets_pg.py`：design §10.2「预置执行对账」行，10 条预置的项目分配按 R13.7（含辽宁卫生服务的借贷双边、没有摘要的 0 行与【UAT】造数）；金标准写成独立 SQL，结果与快照差异写入本条
  - 浏览器验收归 37*（design §10.5 的 W3 段落）

## 阶段 I　W6 业务页行级「按此查询明细」（用户 2026-10-26 追加；R14，ADR-AQL-20；design §3.12、§4.3）
- [ ] 45. 业务对象 → 科目解析与筛选键（R14.2~R14.4、R14.6；变异 #26、#27）
  - 新建 `services/custom_query/entry_accounts.py`；注册表筛选键 `account_code`（可多值）、`wp_code`、`report_row`、`note_section`（`FilterKey.resolver`）；`meta.entry_accounts`；错误码按 design §5
  - 测试：单元（`codes_for_wp_code` 各情形、谓词编译、非法值 400）；PG design §10.2「报表行构成科目」「附注章节与底稿」两行（含回滚事务子科目夹具、范围外 403、直接调接口传合计行得 400 `REPORT_ROW_NO_ACCOUNTS`）
- [ ] 46. 入口上下文与弹窗（R14.1、R14.2 前端；变异 #28）
  - `queryEntryContext.buildQueryEntry`（`hostYear` 参数、`_isSubtotal` / `_isTotal` 判据）/ `tbRowDrill`；`composables/useQueryEntry.ts`；`QueryEntryBanner.vue`；弹窗 `entry` prop 与试算表结果行「查明细」；`utils/eventBus.ts` 载荷类型；`ThreeColumnLayout.vue` 经 `resolveDialogOpenContext` 传 `entry`（+≤ 3 行，`currentYear` 不动）；`types/custom-query-template.ts` 增 `filters`
  - vitest：ADR-AQL-20 表逐行一条落点用例；年度取 `target.year ?? hostYear`；切换保留筛选；手动换源清除上下文；下钻压栈与返回；`resolveDialogOpenContext` 带 entry 时其项目与年度优先
- [ ] 47. 四处页面接线（R14.1、R14.5；变异 #34）
  - 开工前对每个目标文件重跑 `git status` 与行数（design §9，合入后的树）；有他人未提交改动时只改、只提交自己的块
  - 新建 `QueryDetailEntry.vue`（`year` prop）；按 design §4.3 接线：`TrialBalance.vue` +2；`DisclosureEditor.vue` 净 0（穿透项 4 行压成 2 行，HARD_CAP 不动）；`WorkpaperEditor.vue` +3（两个工具栏在合入后的 `projectYear != null` 门控内）；`ReportDrilldownDialogs.vue` + `useReportDrilldown.ts`（`drilldownData` 加 `report_type` / `year` / `project_id`）+ `ReportDrilldownData` 类型，ReportView 0 行
  - 门禁：`rtk ..\.venv\Scripts\python.exe -m pytest tests/scripts/test_hard_cap_ratchet.py -q -p no:playwright`（cwd `backend`）与 `check_file_size.py --staged` 都通过，结果写入本条
  - vitest：组件在合计行与空目标时置灰并显示原因、点击发出带 `entry` 的事件并 emit `opened`、`year` prop 变化后发出的 entry 年度随之变化（附注编辑器页内切年）；单区域 vue-tsc 覆盖改动文件（含一条故意类型错误的变异证明）
  - 浏览器验收归 37*（design §10.5 的 W6 段落）

## 阶段 J　全链路实测与收尾
- [ ]* 37. 浏览器全链路实测（写后读回，design §10.5，含 W3 / W6 段落）：需 start-dev 运行环境；未实测时写「代码已改但未实测」
- [ ]* 38. 合并项目路径实测（tb_summary / ws_* / consol_unit / 合并附注）：现库 0 个合并项目；未实测时写「代码已改但未实测」
- [ ] 39. 收尾
  - `.kiro/specs/INDEX.md` 只更新本 spec 行；写 `closure.md`，逐条回显 design §2 全部裁决（ADR-AQL-01~20）与 §11 待拍板（W1、W2、W4、W5、W7~W16；W3 / W6 标「已纳入」），写明只做周末、不做节假日的原因、design §14.5 的范围外登记、新断点 AQ-38 的处置、e2e_manager 构建器基线按 design §10.2 口径的结果（现库 0 行 + 排除提示），供用户复核；清理 `tmp_aql_linkage/` 与验证 worktree；核对任务数（0~47，共 48 个）与 INDEX 一致
