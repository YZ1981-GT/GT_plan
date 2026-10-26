# 设计文档：高级查询联动闭环（advanced-query-linkage-closure）

## 0. 概览

本设计把业务视图取数从「router 内 14 个文本 SQL 取数器 + 编排器在 ≤5,000 行样本上内存排序 / 分组 / 计数」改为「声明式源注册表 + 数据库内计数、排序、分页与条件」；JSON 类内存源保留内存处理，但触顶即拒、默认保持取数行序。构建器由一个作用域函数为计划中的每张表生成项目、未删、数据集、年度谓词（报表配置另加项目副本行谓词），基表谓词放 WHERE、JOIN 目标谓词并入该 JOIN 的 ON，并逐条声明 JOIN 基数、修正准入。循环级可见性与试算表 / 调整分录 / 附注页同口径。写入面只收窄不扩张：删除 tb / adj / report 写入，回写取行与预览带项目条件，查询路径只读。联动面以「下钻到权威页面 + 复制经地址库校验的公式引用 + 服务端完整导出 + 模板可共享可执行可回收 + 入口带路由上下文」交付。最后按删旧代码铁律删除无入口且接上也不可用的对象。按用户 2026-10-26 决定追加两批：W3 常用审计预置模板（ADR-AQL-05，只读 JSON 定义合入模板列表，载入到条件编辑器，复用 C24 词表、抽凭与截止测试的口径）与 W6 业务页行级「按此查询明细」（ADR-AQL-20，四处页面各挂一个入口组件，映射只在 `queryEntryContext.ts`，科目解析只在后端 `entry_accounts.py`）。本文为第 2 轮设计，评审意见回应见 §13，W3 / W6 的现状核实与裁决见 §14。

技术栈（批准后锁定）：后端 FastAPI + SQLAlchemy 2.x Core（asyncpg）+ PG 16，Excel 经既有 `services/custom_query/export_service.py`（openpyxl write_only）；前端 Vue 3 `<script setup>` + Element Plus + vue-router，业务数据请求走 `@/services/apiProxy` 的 `api`，需要响应头或 blob 时走 `@/utils/http`；测试 pytest（`pg_only` 真 PG；端点权限基于 `tests/authz_world.py`）、hypothesis `max_examples=5`、vitest；浏览器实测用 chrome-devtools / Playwright MCP。不引入新依赖，不新建 router。

## 1. 现状确认（2026-10-26 读码 / grep / 只读 SQL，HEAD b5fc200e0；评估已有事实不重抄）

| 改进点 | 现状确认 | 结论 |
|---|---|---|
| 四表口径 | `_query_account_balance` / `_query_ledger_entries` 只写 `is_deleted = false`；`dataset_query.get_active_filter(db, table, project_id, year)` 只服务单项目单年度，默认 fail-open（查生效数据集失败即回滚并退化为不按数据集过滤）；真库同一项目年度多个 active 数据集 0 组 | 业务视图用 `get_active_filter(strict=True)`；多项目口径在同模块新增可移植谓词 |
| 计数 / 排序 / 分页 | 取数器以 `FETCH_HARD_CAP=5000` 取数，编排器 step5~7 内存分组、排序、计 total、切片；`fetch_cap_warning` 拿本页行数比 5,000；`pagination._tie_breaker_keys` 在结果列里找不到唯一键候选时把全部列按列名排序（附注表格行按金额重排、`cell_ref` 按字符串排序） | 新建注册表 + 分页内核；内存源加隐藏行序列 `_row_index` |
| 条件谓词 | `param_sql_builder.build_filter` / `ParamSQLBuilder.build_where(conditions, *, logic, filter_builder)` 被 `builder_dsl` 使用；方言中立 in / not_in 在 `builder_dsl._build_filter`；like 不转义 `%` `_`；旧筛选键要的前缀、非空判定不在其中；业务视图零使用 | ADR-AQL-03 |
| 导出 | `export_service.stream_xlsx`（硬上限、RFC 5987、来源列、临时文件分块；行迭代与落盘都在首次 yield 前）完整，生产只引用常量；以 `=` 开头的字符串会被 openpyxl 写成公式；无并发限制 | ADR-AQL-14 |
| 下钻深链 | `useLedgerUrlSync.ts`（level / account / voucher / voucherDate / auxType / auxCode + `?year`）；试算表页穿透 `?year=&account=<标准科目码>`；附注编辑器 `?section=&table_index=`；调整分录 `?group=`；底稿编辑器 `?sheet=&cell=`；ReportView 只读 `?year`，而地址库 `build_jump_route` 已生成 `/reports?year=&tab=&highlight=<行次>`、`useResolveLinkageRoute` 用 `?highlight=`；ReportView 普通表 `rvTableRef`、对比表 `compareTableRef`，权益变动表 / 减值准备表是矩阵组件；模板库页签名 `wp-template` / `report-config` / `note-template` | ADR-AQL-01 |
| 公式引用校验 | `POST /api/address-registry/validate`（readonly 项目鉴权，入参 formula / project_id / year / template_type，template_type 缺省 soe）；TB / ROW / NOTE 经 `formula_ref_check` 按项目数据判；WP 只查地址目录（ACNR 种子、交叉引用、自定义格、两参语义引用），选区三参引用大多 `not_found` | ADR-AQL-18 |
| 模板 | 见评估 AQ-16；另：`TemplateForbiddenError` 全仓无 HTTP 映射（执行不可见模板 500）；service 错误码 `TEMPLATE_FORBIDDEN` 与 router `TEMPLATE_NOT_VISIBLE` 两套；`TemplateScopeAdapter` 报错是英文且原样进 422；`update_template` 归一后又执行 `tpl.scope = body.scope`；`MyTemplatesDialog.vue` 三处缺陷（`<script setup>` 内 export、读 `resp.data?.templates`、删除文案「不可恢复」） | ADR-AQL-11 |
| 回收站 | `routers/recycle_bin.py` 通用于带 `is_deleted` 的模型，可见性按项目，无 project_id 的类型只给 admin；`custom_query_templates` 无软删列；平台有 `models.base.SoftDeleteMixin` | 迁移加列 + ORM 用 mixin + 回收站增「按作者可见」类型 |
| 构建器准入 | `_QUERY_BUILDER_ROLES` 只看系统角色；前端 `useQueryBuilderAccess` 与弹窗 `ADVANCED_ROLES` 各一份；`test_p23_*` 正则锁两份清单 | ADR-AQL-08 |
| 构建器作用域与 JOIN | `apply_scope_to_select` 只对基表在 WHERE 追加 `project_id IN`；JOIN 支持 `left`（`outerjoin`）；`JOIN_WHITELIST` 12 条登记都无基数声明；report_config 自 V199 起有 `project:{uuid}` 项目副本行（现库 0 行；报表生成用 `load_effective_report_configs` = 准则行 ⊕ 本项目行）；`report_line_mapping → report_config` 只按行次码关联；account_chart 每码 client + standard 两行（部分唯一索引含 source） | ADR-AQL-09 |
| 循环级可见性 | 试算表、调整分录、附注页按 `deps.get_user_scope_cycles` + `mapping_service.get_codes_by_cycles` / `get_sections_by_cycles` 过滤（本地 HEAD：试算表、调整分录映射为空即无行，附注页映射为空集时不过滤；远端 d0de87a6c 起入口改调 `effective_scope`、附注空范围即空，见 §14.4）；账簿穿透、报表、底稿清单页不按循环过滤；调整分录行 `account_code` 即标准科目码（`adjustment_service` 写入 `li.standard_account_code`）；高级查询各源与附注树都不过滤 | ADR-AQL-19 |
| 回写 | 底稿写路径只认 univer_snapshot（真库 0 / 1,738）；writeback-confirm 直接用 `target.wp_id`，写路径先 `FOR UPDATE` 再比项目，查不到抛 ValueError（router 映射 400）；cell-writeback 的底稿已按 wp_code + 项目定位（跨项目在 HEAD 已 404）；预览对 `missing_target` 仍给 `enter_confirmation=true`；两个回写端点都要求 `X-File-Opened-At` 头；`batch_execute` 直接调 `_query_workpaper` / `_query_workpaper_cell_range`；`write_note_cell` 惰性导入 `module_cell_resolver._NOTE_COLUMNS`；`publish_rows` 生产调用方 6 处（`snapshot_writer_modules` + `event_handlers_cycle_linkage` + `m9_other_comprehensive_income` + `n2_taxes_payable` + `s_transaction_tb_writeback_service` + `s_estimate_tb_writeback_service`）；【UAT】子公司A / B 底稿 0 张，【UAT】合成集团母公司 consol_note_data 2 行 | ADR-AQL-02 |
| 年度 | `list-with-progress` 与 `/api/projects` 已下发审计年度；年度兜底棘轮含 CustomQueryDialog / SheetCellRangePicker / CustomQueryTab / ThreeColumnLayout 各 1；ThreeColumnLayout 的 `currentYear` 同时传给 FormulaManagerDialog（L327）与 GtRefreshScopeDialog（L349） | ADR-AQL-15 |
| 指标树缓存 | 弹窗缓存键 `{schema}:{pid}`（sessionStorage，无过期）；页面版固定 `no-project`；schema 版本经 `X-Indicators-Schema-Version` 下发 | ADR-AQL-16 |
| 零挂载 | 除评估所列外，BatchQueryToolbar、FormulaTracePopover、SnapshotStalenessChip 零挂载；`composables/useBatchQuery.ts` 只剩自身测试 | ADR-AQL-13 |
| 预置模板 | 无实现；6 个归档高级查询 spec grep「预置模板 / 预设模板 / 常用查询」0 处；现成筛选规则在 C24 前端引擎与抽凭 / 截止测试服务（§14.1） | ADR-AQL-05 |
| 业务页入口 | 各页已有穿透：试算表右键「查看明细」→ 账簿页、报表「查看穿透」/「构成科目」弹窗、附注右键「穿透到序时账」、底稿编辑器无科目入口（§14.2） | ADR-AQL-20 |
| 测试耦合 | `test_advanced_query_hardening_wave012.py` monkeypatch router `_query_trial_balance`；指标树测试替身 `_build_disclosure_tree`；`test_note_table_payload_readers_pg.py` 从 router 导入 `_query_disclosure`；`test_query_builder_role_gate_pbt.py` 同步调依赖；`test_query_builder_formula_ref_grammar_v1.py` 断言 tb_balance 生成 `TB(code,'期末')` 并以 `verify_existence=False` 证「期末」可解析（AQ-32 假绿）；`test_advanced_query_scope_budget_tiers.py` 断言 report_config ∈ unscoped_tables；`tests/authz_world.py` 已有 `sqlite_world` / `pg_world`、8 种身份与门禁自检，只建 6 张表 | 改写清单见 §10.1 |
| 性能 | tb_ledger 有 (project_id, year, voucher_date, voucher_no)、(project_id, year, dataset_id) 部分索引等，voucher_date / voucher_no 非空；tb_aux_ledger 有 (project_id, year, account_code, voucher_date, id)；序时账默认排序升降混合，单索引覆盖不了 | ADR-AQL-06 N1 预案 |
| 并发 spec 边界 | `formula-hub-integrity-closure` 不碰高级查询 DSL / acnr_targets，负责中央 TB() 口径与 `COLUMN_ALIASES`，也在改 FormulaManagerDialog 与 GtRefreshScopeDialog；`audit-year-calendar-fallback-ratchet` 负责全平台年度兜底 | TB 列名以地址库词表为准；不动这两个组件的年度 |
| 行数门 | `custom_query.py` 3,086（白名单 2,966，上限约 3,114）；ReportView 1,949 = HARD_CAP；DisclosureEditor HARD_CAP 3,281；ThreeColumnLayout 1,546（白名单 1,515，上限约 1,590） | 先下沉取数器；HARD_CAP 文件净增 ≤ 0 |

## 2. 裁决（ADR；closure.md 原样回显供用户复核）

### ADR-AQL-01 结果下钻到哪些模块
每类结果下钻到它的权威页面，只用页面既有深链契约；报表页改为认地址库已在用的 `?tab=&highlight=`，不新增第三种写法。在新标签打开（`window.open(router.resolve(loc).href)`，不加 noopener 以保留会话）。

| 结果 | 目标页面 | 深链 |
|---|---|---|
| 科目余额（含合并单位） | 账簿查询 LedgerPenetration | `?year=&level=ledger&account=<account_code>` |
| 序时账 | 账簿查询 | `?year=&level=voucher&account=&voucher=<voucher_no>&voucherDate=` |
| 辅助余额 / 辅助明细 | 账簿查询 | `?year=&level=aux_ledger&account=&auxType=&auxCode=` |
| 试算表 | 账簿查询 | `?year=&account=<standard_account_code>`（与试算表页穿透同口径） |
| 报表行 | 报表页 ReportView | `?year=&tab=<report_type>&highlight=<row_code>`：普通 / 对比模式定位到行；权益变动表、减值准备表是矩阵格式，只切页签并提示 |
| 附注目录 / 附注表格行 | 附注编辑器 | `?year=&section=<note_section>&table_index=<i>` |
| 调整分录 | 调整分录页 | `?year=&group=<entry_group_id>` |
| 底稿清单 / 底稿单元格 | 底稿编辑器 | `wp-id-by-code` 取 wpId；`?sheet=&cell=` |
| 报表行次配置 / 工时 / 合并工作底稿 | 不下钻 | — |

构建器结果范围为单个项目时，按表映射到同一目标（trial_balance、tb_balance、tb_ledger、tb_aux_*、adjustments、disclosure_notes、working_paper / wp_index、financial_report）；跨项目结果不下钻。理由：权威页面已有定位能力，复用比在查询框内再造明细视图收敛；advanced-query-module R4 承诺的「结果格经 addr_id + jump_route 下钻」在取数器从不产出 addr_id 的现状下落不了地，以行级深链交付等价联动；`GtIndexChip` 列分支保留（将来出现单源 addr_id 列时自动生效）。

### ADR-AQL-02 查询结果能否回写底稿 / 附注：不能
本 spec 不开放任何回写界面。advanced-query-module R13.6「查询结果引用到底稿」改由两种只读联动交付：①复制经地址库校验的公式引用（ADR-AQL-18），用户粘进底稿 / 附注公式后经各自权威保存链落库；②下钻打开权威编辑器定位后编辑。后端：删除 tb / adj / report 三个写入实现（P0）；cell-writeback 与 writeback-preview / confirm 的 module 收窄为 workpaper、note；取行与预览带项目条件（R4.2），预览有无法定位的目标即不进入确认（R4.5）。workpaper / note 写入代码与三个端点保持现状（无界面），是否下线进 §11 W2。理由：①TB 审定数只经发布门、调整分录只经调整分录服务是平台铁律，tb / adj 写入绕门，report 写的是全库 0 行的 report_snapshot；②底稿写路径依赖 univer_snapshot（0 / 1,738），接上界面对真实底稿恒失败，要可用须改走 workpaper_sync 内容写入，属新能力；③附注写路径只覆盖合并附注 consol_note_data（0 个合并项目），单体 disclosure_notes 无写路径，附注内容的权威写入方是附注编辑器与底稿单项推送；④整体删除回写栈会波及 workpaper_sync 写入者清单与门禁测试（`test_workpaper_writer_inventory.py`、`test_task20_writer_gate.py`、durable outbox 系列），属他域治理。

### ADR-AQL-03 `param_sql_builder`：接线（保留）
作为业务视图结构化条件、旧筛选键与构建器条件共同的唯一谓词来源。新增 `build_portable_filter(col, op, value)`：承接 `builder_dsl._build_filter` 里方言中立的 in / not_in（空集合恒假 / 恒真），并提供两个只供注册表旧筛选键使用的内部算子 `prefix`（转义后 `LIKE value || '%'`）与 `nonempty`（True = 非空且非空串，False = 取反），二者不进 `OPERATOR_WHITELIST`，用户条件仍只认白名单；其余算子委托 `build_filter`。`build_filter` 的 like / not_like 改为先转义 `\ % _` 再包 `%`（`escape="\\"`，构建器同时受益）。`_build_filter` 名称保留为薄委托，既有测试不动。W3 起用户算子白名单增加两项（ADR-AQL-05）：`starts_with` 与 `prefix` 共用同一个谓词函数（同一转义规则），`weekday_in` 为新谓词；`prefix` / `nonempty` 仍只供旧筛选键。

### ADR-AQL-04 `cross_sheet_trace_orchestrator`：删除
它与 `GET /cross-sheet-trace` 只读 univer_snapshot（真库 0 张），端点无前端调用方，配套 `FormulaTracePopover.vue` 零挂载。删除 orchestrator、端点、popover 及其专属测试；保留被 `wp_formula_eval_service` 使用的 `cross_sheet_resolver`。按删旧代码铁律单独提交（§3.9）。公式来源改由下钻到底稿格后编辑器自身展示。

### ADR-AQL-05 常用审计预置模板：做（W3，用户 2026-10-26 决定，原裁决「本轮不做」作废）
候选：(a) 迁移加 `system` 范围与系统用户，预置入库；(b) `backend/data/custom_query_presets.json` 只读定义，服务端校验后作为「系统预置」合入模板列表，载入时按项目解析参数；(c) 前端常量。采用 (b)：用户首选；不需要迁移，也不引入无主的系统账号（它会让模板可见性、审计留痕、回收站「仅作者可见」三处都要加例外）；定义随代码评审；(c) 会让 C24 词表与抽凭口径再多一处维护。

复用现有定义（核实见 §14.1），不另写规则：
- 特殊事件关键词：C24 规则 11 写在 `useC24AnalyticsEngine.screenAnomalies` 的局部常量里 ⇒ 词表搬进本 JSON 的 `keyword_sets.special_event`，由生成器写出 `src/generated/journalEntryRules.ts`，C24 引擎改为 import 它（一处维护，`--check` 防漂移）。
- 大额：平台口径是 `LedgerSamplingService.build_ledger_query` 的「`GREATEST(COALESCE(借,0), COALESCE(贷,0)) >= 阈值`」（抽凭与截止测试共用，注释写明不取绝对值）⇒ 抽成 `ledger_sampling_service.ledger_line_amount(table)`，抽凭与查询共用。C24 规则 4 是前端对导入分录的同义判断（`>`），不改。
- 期末前后窗口：`CutoffTestService.run_cutoff_test` 的期末日规则（显式截止日，否则 `date(年度, 12, 31)`）与默认前后 5 天 ⇒ 抽成 `sampling_enhanced_service.cutoff_window()` 与两个默认值常量，截止测试与预置共用。
- C24「含模糊词」默认词表写在 `GtC24JournalDetail.vue`（2,049 行，超前端默认上限 1,500 且不在白名单，改一行就被行数门拦）⇒ 本轮不做「模糊词」预置，进 §11 W16。

预置清单（数据源都是序时账 `ledger_entries`；条件形状与用户模板的 `config.conditions` 相同：`{field, op, value}`）：

| id | 名称 | 条件 | 逻辑 | 参数 / 说明 |
|---|---|---|---|---|
| `je_account_ledger` | 指定科目序时账 | `account_code` 开头是「」 | and | 载入后填科目编码（留空不能查询） |
| `je_reversal` | 摘要含冲销 / 红字 | `summary` 包含 冲销、红字、冲红、冲回 | or | 词表 `keyword_sets.reversal` |
| `je_negative_amount` | 负数金额（红字）分录 | `debit_amount` 小于 0；`credit_amount` 小于 0 | or | — |
| `je_cutoff` | 期末前后 5 天凭证 | `voucher_date` 介于 `cutoff_start`、`cutoff_end` | and | `cutoff_window()`；说明「期后部分在下一年度序时账（如已导入），请切换年度」 |
| `je_large_amount` | 大额分录 | `line_amount` 大于等于 `materiality_performance` | and | 说明「借、贷较大者，与抽凭、截止测试同口径，不取绝对值；负数红字见负数金额分录」 |
| `je_weekend` | 周末分录 | `voucher_date` 星期为 六、日 | and | 说明「只按周六、周日筛选：调休上班日也会列出，法定节假日不在其内」 |
| `je_special_event` | 摘要涉及特殊事件 | `summary` 包含 关联交易、收购、合并、重组、诉讼、处置、清算、破产 | or | 词表 `keyword_sets.special_event`（= C24 规则 11） |

阈值取「实际执行的重要性水平」（`materiality.performance_materiality`）：整体重要性对分录级筛选过高、几乎筛不出；明显微小错报临界值过低、筛出过多；实际执行的重要性是确定进一步审计程序范围的口径。值不大于 0、没有记录或读取失败时留空并给原因，不取绝对值、不给默认值（两个真实记录都是负数，见 §14.1）。最小新能力四项：用户算子 `starts_with`、`weekday_in`（ADR-AQL-03），序时账只作条件的计算列 `line_amount`，条件编辑器补「大于等于」「小于等于」。节假日：平台没有日历来源（§14.1），只做周末，进 §11 W15。预置没有数据库 id，不能直接执行：执行前必须经条件编辑器确认参数；「另存为我的模板」走既有保存（R9.1）。

### ADR-AQL-06 计数分页下推（AQ-03 根因）与 N1 预案
候选：(a) 调大 5,000 上限：只推迟错数，否决；(b) 内存路径触顶即拒：序时账等大表基本不可用，不作主路径；(c) SQL 源声明式注册（列、筛选键、默认排序、唯一键、口径谓词），COUNT、ORDER BY、LIMIT / OFFSET、条件全在数据库内，JSON 内存源保留内存路径但触顶即拒、默认按 `_row_index` 保持取数行序：采用。取数器从 router 下沉到 `services/custom_query/`；编排器继续接受旧的 `(rows, columns)` 返回（既有约 40 个编排器测试不改）。
N1 预案（按序执行，每步后重测）：①辅助明细必须带科目前缀或辅助类型筛选，否则 400（跨维度合计本就会重复，见 R5.6）；②排序项只对可空列加 NULLS LAST（非空列加了会使索引失效、语义相同）；③仍超标：相关任务保持未勾并附 `EXPLAIN ANALYZE` 与实测；为 tb_ledger / tb_aux_ledger 建 `(project_id, year, dataset_id, voucher_date DESC, voucher_no, id)` 索引要在共享库上长时间锁写，列 §11 W12 由用户拍板，不自动执行。

### ADR-AQL-07 分组 / 透视（评估 D4）
不出界面。SQL 源带分组 / 透视时先 COUNT：≤ 5,000 取全量交 grouping_engine / pivot_engine（结果正确）；> 5,000 返回 400 `AGGREGATION_TOO_LARGE`。两个引擎保留。

### ADR-AQL-08 构建器准入与人员表（评估 D1、D2）
D1：允许 = 系统角色 ∈ {admin, partner, manager}，或存在未删 project_users 行（项目未删）role ∈ {manager, partner} 且 permission_level = edit。判定只在 `services/custom_query/builder_access.py`，`require_query_builder_access` 与 `GET /api/query/access` 都调它；作用域仍为 OwnershipGuard 可访问集合（循环受限项目见 ADR-AQL-19）；PII 仍按系统角色判定（项目经理看不到电话、邮箱）。access 接口对 admin / partner 返回 `all_projects: true`、`accessible_project_count: null`。D2：staff_members 只对系统 admin / partner 开放（含作为 JOIN 目标）。

### ADR-AQL-09 构建器作用域与 JOIN
作用域谓词（`builder_scope.scope_predicates`）对计划中每张表生成：项目（projects 用 `id`，其余用 `project_id`；可访问集合恒排除已删项目，admin / partner 为全部未删项目）、`is_deleted = false`（有列时）、四表数据集口径、请求年度（有 `year` 列且请求带年度）、report_config 项目副本行限可访问项目。**基表谓词追加在 WHERE 最后一步（DSL 无法放宽）；JOIN 目标谓词与登记的目标条件一起并入该 JOIN 的 ON**，LEFT JOIN 无匹配时目标列为 NULL、基表行保留。12 条登记逐条裁决（导入期不变式：每条必须声明基数；PG 守卫逐条覆盖）：

| 基表 → 目标 | 现有 ON | 追加目标条件 | 基数 | 处置 |
|---|---|---|---|---|
| trial_balance → account_chart | project_id；standard_account_code = account_code | `source = 'standard'` | 多对一 | 保留 |
| trial_balance → report_line_mapping | project_id；standard_account_code | — | 一对多 | 保留 + warning（现库 2 个科目映射到多行） |
| adjustments → trial_balance | project_id；account_code = standard_account_code | ON 补 year、company_code | 多对一 | 保留 |
| working_paper → wp_index | wp_index_id = id | — | 多对一 | 保留 |
| wp_index → working_paper | id = wp_index_id | — | 一对多 | 保留 + warning |
| tb_balance → account_chart | project_id；account_code | `source = 'client'` | 多对一 | 保留 |
| tb_ledger → account_chart | project_id；account_code | `source = 'client'` | 多对一 | 保留 |
| report_line_mapping → report_config | report_line_code = row_code | — | 一对多（同一行次码在各准则与项目副本各有一行） | **删除登记**：行名已在 report_line_mapping.report_line_name；准则随项目而定，写不成常量条件；恢复进 §11 W13 |
| disclosure_notes → projects | project_id = id | — | 多对一 | 保留 |
| staff_members → work_hours | id = staff_id | — | 一对多 | 保留 + warning（只 admin / partner 可用） |
| work_hours → staff_members | staff_id = id | — | 多对一 | 保留 |
| work_hours → projects | project_id = id | — | 多对一 | 保留 |

### ADR-AQL-10 合并类叶子（评估 D7 修正）
单体项目隐藏 tb_summary 与整组 ws_*，`tb_detail` 更名「试算平衡表（科目）」；不把 tb_summary 改读 trial_balance（与 tb_detail 重复）。合并项目（report_scope = consolidated 或 consol_scope 有数据）保留原叶子，tb_summary 更名「合并试算平衡表（工作底稿）」。

### ADR-AQL-11 模板范围与删除（评估 D8、D9）
D8：前端只给「仅我可见 / 指定项目共享 / 公开」；后端 scope 归一与可见性只留 `TemplateScopeAdapter`，入库规范值 private / project / public，team 只作历史兼容；错误码统一 `TEMPLATE_NOT_VISIBLE`。D9：软删 + 回收站；迁移加 `is_deleted` / `deleted_at`（ORM 用 `SoftDeleteMixin`），回收站增「按作者可见」类型（作者与 admin 可见、可恢复、可彻底删除）。理由：「删除二次确认 + 先进回收站」是用户明示的平台规则。

### ADR-AQL-12 ACNR 选字段（AQ-15）
面板标「开发中」（禁用，说明「当前不影响查询结果」），前端不再发送 acnr_targets；后端 acnr_targets 契约（存在性校验、全有或全无）不改。「选中格成为结果列」进 §11 W4：要接 xlsx 只读取值与 sheet_code → sheet 名映射，属新能力；同类需求由弹窗的底稿 sheet 选区器满足。

### ADR-AQL-13 删除清单（评估 D6 + 新发现）
删：`POST /batch-execute` + 零挂载 `BatchQueryToolbar.vue` + `composables/useBatchQuery.ts` + apiPaths `customQuery.batchExecute`（`batch_execute` 直接调 router 内取数器，必须先于取数器下沉删除，tasks 6）；`report:` / `note:` / `adj:` / `tb:` 跨模块单元格源族（`module_cell_resolver` 取数部分；保留 `parse_source_uri` / `format_source_uri` 与被 `write_note_cell` 惰性导入的 `_NOTE_COLUMNS`）与选区器模块模式（父组件从不传 moduleSource）；零挂载 `SaveAsTemplateButton.vue`、`SnapshotStalenessChip.vue`（依赖 univer_snapshot）；ADR-AQL-04 三件；零调用方常量 `customQuery.cellWriteback`。保留：`/index-health`（运维端点）、grouping / pivot 引擎、export_service、MyTemplatesDialog（修复后接线）、cell-writeback 与 writeback 两端点（ADR-AQL-02）。

### ADR-AQL-14 导出
三处统一服务端导出，经 `export_service.stream_xlsx`：先 COUNT 预检（> 1,000,000 → 400，沿用 advanced-query-module R8.4「不启动导出」，不改为截断，§11 W11），再流式写临时文件；端点内预取第一块（构建阶段在请求会话存活时完成，错误能以 JSON 返回），其余块只读临时文件。中文表头由前端随请求传 `headers`（标签真源仍是前端 `queryColumnLabels.ts`）。两项防护：①以 `= + - @` 开头的字符串（数据、表头、「查询说明」）按文本写入；②进程内导出闸：每个用户同时 1 个、全进程同时 4 个，超出 429 `EXPORT_BUSY`（平台目标并发 6000，而单次导出最多 100 万行、120 s、行写入在事件循环里）。前端 `exportQueryResultToXlsx` 保留为「导出当前页」。

### ADR-AQL-15 年度与入口上下文
弹窗年度只取路由 `?year` 或项目审计年度（后端解析值），取不到要求选择。ThreeColumnLayout 只为弹窗新增计算属性 `customQueryYear`，`currentYear` 不动（它还传给公式管理与一键刷新，两者在并发 spec 范围内），年度兜底棘轮里 ThreeColumnLayout 条目保留。弹窗每次打开以路由项目为准，模板库事件的 project_id 优先；侧栏打开时按当前路由名预选数据源（`queryEntryContext.ts` 一处映射）；行级「按此查询明细」按用户 2026-10-26 决定纳入本 spec，裁决见 ADR-AQL-20（事件带 `entry` 时其项目、年度、数据源优先于路由预选）。

### ADR-AQL-16 指标树
单体项目附注分支按该项目该年度附注生成（indicators 增可选 `year`，缺省取项目审计年度），章节集合与顺序复用附注编辑器同一函数 `DisclosureEngine.get_notes_tree`（含口径过滤）再叠加循环范围；合并项目沿用模板种子树。缓存键改为 `{schema}:{pid}:{year}:{notesVersion}`，`notesVersion` 由响应头 `X-Notes-Version` 下发（附注行数、最近更新时间与循环范围的摘要），附注重新生成 / 对齐或切换年度即失效；弹窗与页面版共用同一缓存模块，弹窗懒加载进 §11 W5。页面版加载「骨架 + 附注分支」并把叶子拍平，不列逐底稿 / 逐 sheet 叶子、只留「底稿清单」：页面版的源选择是 el-select 平铺列表，底稿分支约 640 KB、上千个选项无法在下拉里使用；sheet 级查询仍从弹窗的底稿选区器发起，功能不回退。树形变化 ⇒ schema 版本 10 → 11。W3 给叶子加 `condition_fields: [{key, dtype}]`（可作条件的显示列与只作条件的计算列，由注册表生成，条件编辑器据 dtype 给算子）⇒ schema 版本 11 → 12。

### ADR-AQL-17 模板溯源（AQ-17）
保留右键入口。address-resolve：底稿编码在 `wp_template_registry` 表存在时查表，否则用与指标树同一的 JSON 目录（`_load_wp_mapping` + `_load_step_sheet_mapping`）判定登记；返回模板库真实页签名与 `wp_code`；不再返回 `highlight`（模板页不支持）。TemplateLibraryMgmt 读 `?tab=`，WpTemplateTab 接 `initial-search`。adj / tb 结果无模板定义，返回 `registered=false`、空路由，前端提示「该类结果没有模板定义」。

### ADR-AQL-18 引用（AQ-24 的交付方式、AQ-27）
前端 `queryResultLinks.ts` 按源生成：试算表 `TB('<标准科目码>','<列名>')`（列名取 审定数 / 未审数 / AJE调整 / RJE调整 / 期初余额，与地址库词表一致）、报表 `ROW('<row_code>')`、附注 `NOTE('<章节>','<行标签>','<列表头>')`、底稿单元格 `WP('<wp_code>','<sheet>','<cell>')`。每页结果渲染后对本页引用批量校验一次：把引用以 `+` 连成一条公式调 `POST /api/address-registry/validate`（每次 ≤ 200 个，带 `meta.ref_context` 的 template_type 与年度），按返回 issue 的 `ref` 标记各按钮；校验不通过的按钮不可用并显示首条原因，底稿格 `not_found` 显示「该单元格未登记为可引用地址」（WP 只查地址目录，只对已登记坐标开放；为未登记坐标开放进 §11 W14）。校验请求失败时全部按钮不可用并提示「引用校验暂不可用」。构建器 `_derive_formula_refs` 只给 trial_balance 行，tb_balance 行返回 null（客户科目码不属于 TB 域）。

### ADR-AQL-19 循环级可见性
候选：(a) 高级查询各源与附注树复用原页面的循环过滤；(b) 登记范围外归平台鉴权。采用 (a)：不做等于高级查询绕过试算表 / 调整分录 / 附注页的限制，接上完整导出后范围更大。口径只来自平台唯一入口 `deps.get_user_scope_cycles`，循环范围不另读 `project_users.scope_cycles` / `project_assignments.assigned_cycles`、不改其语义；它的规则在 `services/wp_visibility/effective_scope.resolve_member_scope`：系统 admin / partner 返回 None（不限）；本项目主管——委派角色属合伙人、签字合伙人、项目经理、质控、EQCR（含中文别名，取自 `assignment_service.ROLE_MAP`）且人员记录与成员行链路唯一——返回 None；其余成员返回「团队分配勾选 `assigned_cycles` ∪ `project_users.scope_cycles`」，可以是空列表，空即什么都看不到；查询失败按空集。唯一实现 `services/custom_query/cycle_scope.py`，在该入口之上调 `mapping_service.get_codes_by_cycles` / `get_sections_by_cycles`，与原页面逐项同口径：试算表源按 `standard_account_code ∈ 科目集合`（空集无行）；调整分录源取「分录组内任一行科目在集合内」的整组（取科目集合失败按空集，与调整分录页同）；附注目录、附注章节与附注树按章节集合严格过滤（空集即空，与附注页同）；查询范围外章节 403 `SECTION_OUT_OF_SCOPE`。账簿、辅助、报表、底稿清单、工时源对应页面不按循环过滤，同口径不过滤（是否收紧登记范围外）。构建器对每个可访问项目调同一入口，返回值不为 None 的项目排除出作用域（fail-closed，warnings 写明排除数；显式指定 403 `CYCLE_SCOPED_PROJECT`），这类项目只能在按循环过滤的业务视图里查。前置：上述入口规则在远端提交 d0de87a6c，本地分支尚未包含（§14.4），任务 23 开工前分支须包含该提交。

### ADR-AQL-20 业务页行级「按此查询明细」入口（W6，用户 2026-10-26 纳入）
候选：(a) 每页各自拼查询参数打开弹窗；(b) 页面只挂一个入口组件 `QueryDetailEntry.vue`，上下文 → 查询参数的映射只在 `queryEntryContext.ts`，业务对象 → 科目的解析只在后端 `services/custom_query/entry_accounts.py`；(c) 只用各页现有穿透（账簿查询页），不进高级查询。采用 (b)：用户要求映射一处；目标页面都在行数门附近（ReportView = HARD_CAP、DisclosureEditor 余 16 行、WorkpaperEditor 余 35 行）；(c) 的账簿页不能叠加条件、不能服务端导出全量。现有穿透全部保留，新入口与之并列，不替换。

| 入口（并列的现有能力） | 落点：数据源 + 筛选 | 可切换 / 行内下钻 | 科目解析（复用的现有定义） |
|---|---|---|---|
| 试算表右键菜单（「📊 查看明细」→ 账簿页定位） | 序时账 + `account_code=<标准科目码>`（前缀） | 科目余额 / 辅助余额 / 辅助明细，同一筛选 | 标准码前缀 = 账簿页现有穿透与抽凭的科目口径；三个真实项目的客户科目 100% 以所映射标准码开头（§14.2） |
| 报表「📊 查看穿透」弹窗（`ReportDrilldownDialogs.vue`，ReportView 0 行） | 试算表 `tb_detail` + `report_row=<报表类型>:<行次>` | 结果行「查明细」→ 该科目序时账，可返回上一查询 | 该行 `financial_report.source_accounts`：单码 `LIKE 码%`（= `ReportFormulaParser._get_tb_rows_prefix`），`起~止` → BETWEEN（= `_resolve_sum_tb`） |
| 附注表格右键菜单（「📊 穿透到序时账」） | `disclosure_note:<章节>`（第 0 张表，弹窗内可切表） | 「相关科目（试算表）」：`tb_detail` + `note_section=<章节>` | 章节标题 → `note_account_mappings`（`{准则}_standalone`）→ 底稿编码 → `wp_account_mapping.json` → 科目 |
| 底稿编辑器两个工具栏 | 序时账 + `wp_code=<底稿编码>` | 科目余额 / 辅助余额 / 辅助明细 | `wp_account_mapping.json`：编码精确匹配，没有该编码时取主编码（第一个「-」之前） |

项目取路由 `projectId`；年度取路由 `?year`（页面当前显示的年度，用户在页面上显式切换过时，明细必须与所点的行同一年度），没有时由弹窗按 R10.2 取项目审计年度（`resolve_project_audit_year`），任何一步都不用日历年兜底；入口经 `open-custom-query` 事件带 `entry` 打开弹窗并立即执行；用户手动换数据源即清除上下文（避免把筛选键带到不认它的源而 400）；落到的源按 ADR-AQL-19 过滤。附注落第 0 张表而不取编辑器的 `activeTableTab`：后者是投影后的序号（`resolveProjectedTableIndex`），与 `table_data` 原始序号不一定相同。「底稿格」入口放工具栏：科目是底稿属性（`wp_account_mapping` 按底稿编码登记），37 种 HTML 渲染器没有共用的单元格右键菜单。

## 3. 后端设计

### 3.1 源注册表与取数内核（新文件）
`services/custom_query/source_registry.py`：
```python
@dataclass(frozen=True)
class SourceColumn:
    key: str                     # 响应列键（英文契约，不变）
    expr: ColumnElement          # 取自 ORM __table__ 的列表达式；nullable 由列定义读出
    dtype: Literal["number", "text", "date", "bool"]
    conditionable: bool = True
    sortable: bool = True

@dataclass(frozen=True)
class FilterKey:                 # 旧 filters 字典允许的键
    key: str
    column: str                  # 对应 SourceColumn.key
    op: Literal["eq", "like", "prefix", "gte", "lte", "nonempty"]

@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str                   # 指标树叶子中文名
    from_clause: Callable[["FetchContext"], FromClause]
    columns: tuple[SourceColumn, ...]   # 显示列，顺序即默认列序
    hidden: tuple[SourceColumn, ...]    # 下钻 / 排序 / 唯一键：随行返回，不进 columns
    base_where: Callable[["FetchContext"], Awaitable[list[ColumnElement]]]
    filter_keys: tuple[FilterKey, ...]
    default_sort: tuple[tuple[str, str], ...]
    unique_key: str                     # hidden 中的唯一列
    required_filters: tuple[frozenset[str], ...] = ()   # 至少满足其一组（辅助明细用）
    tree_scope: Literal["any", "standalone", "consolidated"] = "any"
    warn: Callable[["FetchContext", list[ColumnElement]], Awaitable[list[str]]] | None = None
```
`FetchContext(db, user, project_id: UUID, year: int, filters: dict, company_code: str | None, cycle: CycleScope)`。`resolve_source(key) -> ResolvedSource(spec | json_fetcher, fixed_filters, company_code)` 负责别名、前缀、`consol_unit:{cc}:{kind}`、`workpaper:{code}[|{sheet}]`、`disclosure_note:{sec}` 解析；未知 → 400 `UNKNOWN_SOURCE`（既有错误码）。

| 源键（别名） | 表与口径 | 显示列 | 隐藏列 | 默认排序 |
|---|---|---|---|---|
| report_balance_sheet … report_impairment_provision；report（filters.report_type） | report_config rc：未删、限 report_type，且（applicable_standard = 项目准则，或 = `project:{pid}` 且项目准则下没有同 (report_type, row_code) 的行）；LEFT JOIN financial_report fr（同项目年度、report_type 以 text 比较、row_code、fr 未删）。项目准则 = `ReportConfigService.resolve_applicable_standard`（报表生成用的同一函数），filters.standard 显式传入时以其为准 | row_code, row_name, current_period_amount, prior_period_amount, indent, is_total | rc.id, rc.row_number, fr.is_stale, fr.blank_reason | row_number, row_code |
| trial_balance（tb_detail、consol_unit:{cc}:tb_detail） | trial_balance：项目 + 年度 + 未删（+ company_code）+ 循环范围 | standard_account_code, account_name, opening_balance, unadjusted_amount, rje_adjustment, aje_adjustment, audited_amount | id | standard_account_code |
| account_balance（consol_unit:{cc}:account_balance） | tb_balance + `get_active_filter(strict=True)` | account_code, account_name, opening_direction, opening_balance, debit_amount, credit_amount, closing_direction, closing_balance, currency_code | id | account_code |
| ledger_entries（consol_unit:{cc}:ledger_entries） | tb_ledger + 同上 | voucher_date, voucher_no, account_code, account_name, debit_amount, credit_amount, summary | id, entry_seq, accounting_period | voucher_date desc, voucher_no, entry_seq |
| aux_balance（新） | tb_aux_balance + 同上 | account_code, account_name, aux_type, aux_code, aux_name, opening_direction, opening_balance, debit_amount, credit_amount, closing_direction, closing_balance | id | account_code, aux_type, aux_code |
| aux_ledger（新） | tb_aux_ledger + 同上；`required_filters = ({account_code}, {aux_type})` | voucher_date, voucher_no, account_code, aux_type, aux_code, aux_name, debit_amount, credit_amount, summary | id | voucher_date desc, voucher_no |
| adj_aje / adj_rje（adj_rcl）；adjustment（通用）；consol_unit:{cc}:adjustment | adjustments：项目 + 年度 + 未删 + 类型（adj_aje = aje、adj_rje = rje；通用源不带 filters.adjustment_type = 全部类型 aje / rje / cf，带时 AJE→aje、RJE / RCL→rje，其余 400）+ 循环范围 | adjustment_no, account_code, account_name, debit_amount, credit_amount, description, review_status（通用源另加 adjustment_type） | id, entry_group_id | adjustment_no |
| workpaper；workpaper:{code}[\|{sheet}]（无 cell_range） | working_paper ⋈ wp_index：项目 + 未删；code 精确或子编码前缀 | wp_code, wp_name, audit_cycle, status, review_status, assigned_to | wp.id, sheet_name（回显） | wp_code |
| report_lines | report_config：未删，applicable_standard 不以 `project:` 开头或等于 `project:{pid}` | row_code, row_name, report_type, applicable_standard, indent_level, is_total_row, formula, row_number | id | applicable_standard, report_type, row_number |
| workhours | work_hours：项目 + `EXTRACT(YEAR FROM work_date)` + 未删 | work_date, hours, description, status, staff_id | id | work_date desc |

旧 filters 键（`filter_keys`，未登记 → 400 `UNKNOWN_FILTER_KEY`）：report（report_type、standard）；trial_balance（account_name like、company_code）；account_balance（account_code prefix、account_name like、company_code）；ledger_entries（account_code prefix、voucher_no like、summary like、date_from / date_to、company_code）；aux_balance（account_code prefix、aux_type、aux_code、aux_name like）；aux_ledger（同 aux_balance + voucher_no + date_from / date_to）；adjustments（adjustment_type、account_name like、review_status、company_code）；workpaper（wp_code、sheet_name、status、review_status、cycle）；report_lines（report_type、applicable_standard、has_formula → nonempty、row_name like）；workhours（staff_id、status、date_from / date_to）。谓词一律经 `param_sql_builder.build_portable_filter` 生成。

源级 warnings（`warn`）：四表无生效数据集 → R1.3 文案；辅助余额未按 aux_type 筛选 → R5.6 文案；报表源该项目年度类型无 fr 行 → 「该项目尚未生成此报表，金额为空」，存在 `fr.is_stale` → 「报表数据已过期，请在报表页重新生成」。所有源的响应 `meta.ref_context = {"template_type": "soe" | "listed", "year": 请求年度}`（`_resolve_project_template_type`），供前端校验引用。

`services/custom_query/paged_fetch.py`（新）：
- `build_statement(spec, ctx, *, conditions, logic, columns)`：先查 `required_filters`（都不满足 → 400 `AUX_FILTER_REQUIRED`）；WHERE = `await spec.base_where(ctx)` + 旧 filters + 条件（`ParamSQLBuilder.build_where(..., logic, filter_builder=build_portable_filter)`）；选择列 = 所选显示列（空 = 全部）+ 全部隐藏列。`columns` 含未登记键 → 400 `UNKNOWN_COLUMN`；条件字段非 conditionable 或未登记 → 400 `UNKNOWN_CONDITION_FIELD`。
- `count(...)`：`select(func.count()).select_from(stmt.order_by(None).subquery())`。
- `page(...) -> FetchPage`：排序 = 用户 sort（字段须 sortable，沿用 `pagination` 的 `INVALID_SORT_FIELD` / `INVALID_SORT_FIELD_DIRECTION` 422）→ 否则 default_sort → 末尾追加 unique_key asc；可空列加 `.nulls_last()`，非空列不加（语义相同且保留索引可用）；`MAX_SQL_OFFSET = 100_000`，超出 422 `OFFSET_TOO_DEEP`。
- `all_rows(..., cap=FETCH_HARD_CAP)`：count > cap → 400 `AGGREGATION_TOO_LARGE`；否则不带 LIMIT 取全量。
- `stream(..., batch=2000)`：`await db.stream(stmt.execution_options(yield_per=batch))`，按 `partitions(batch)` 产出。
- 全部包在 `execution_guard.cancellable_query(db, QUERY_TIMEOUT_MS)` 内（导出用 `EXPORT_TIMEOUT_MS`），超时沿用 408 `QUERY_TIMEOUT`；单元格序列化复用 `builder_dsl._serialize_cell`。

### 3.2 JSON 内存源（`services/custom_query/fetchers/`，从 router 迁入）
- 共同：每行带隐藏列 `_row_index`（取数顺序，从 0 起，不进 columns、不导出）；行数 > `FETCH_HARD_CAP` → 400 `RESULT_TOO_LARGE`；带 conditions → 400 `CONDITIONS_UNSUPPORTED`；`columns` 投影与 SQL 源同规则。
- `disclosure.py`：`_query_disclosure`（router 再导出，供 `test_note_table_payload_readers_pg.py`）。章节集合与顺序取 `DisclosureEngine(db).get_notes_tree(project_id, year)` 再叠加循环范围。`disclosure`（附注目录）→ 每「章节 × 表」一行：note_section, section_title, table_name, row_count, is_stale；`disclosure_note:{sec}` → 章节不在循环范围 403 `SECTION_OUT_OF_SCOPE`；`filters.table_index`（默认 0）选一张表，columns = `["note_section", "section_title", "table_name"]` + 该表表头（`_flatten_disclosure_note_rows` 改为按表拆），行序 = `table_data` 原始行序，`meta.tables = [{index, name, row_count}]`。单体读 disclosure_notes，合并沿用 consol_note_data 逻辑。
- `worksheet.py`：`tb_summary`、`ws_*`（逻辑不变，仅合并项目在树上可见）。
- `workpaper_cells.py`：`query_cell_range`、`render_sheet_preview` 及只读重算（§3.7），`_row_index` 按行优先的单元格顺序。

### 3.3 编排器与 execute
- `business_fetchers.business_fetcher`：SQL 源无分组 / 透视 → `paged_fetch.page()` 返回 `FetchPage(paged=True)`；有分组 / 透视 → `all_rows()` 返回 `(rows, columns)`；JSON 源 → `FetchPage(paged=False, rows=全部, total=len, meta=…)`。删除跨模块单元格分支与 `fetch_cap_warning`。
- `query_orchestrator`：新增 `FetchPage(rows, columns, total, paged, meta, warnings)`；`_run_pipeline` 遇 `paged=True` 跳过 step5~7、total 取 `FetchPage.total`，`paged=False` 与 tuple 走原内存路径；`QueryRequest` 增 `conditions: list[dict]`、`condition_logic: str = "and"` 并进 `cache_def()`；`QueryResult` 增 `meta: dict`（`to_payload` / `from_payload` 往返）。
- `pagination`：`DEFAULT_SORT_BY_SOURCE` 删去 SQL 源条目（默认排序唯一所有者 = 注册表），内存源条目一律改为 `(("_row_index", "asc"),)`；`TIE_BREAKER_CANDIDATES` 以 `_row_index` 打头（行里没有时沿用原候选）。
- `execute_compatibility`：映射 conditions / condition_logic（旧请求体缺字段时取默认）；`to_legacy_response` 仅当 meta 非空时加 `meta` 键（既有响应键集合不变）。
- `services/query_cache.build_canonical_query_identity` 增 conditions、condition_logic。
- router `QueryRequest`：增 `conditions: list[ConditionSpec]`（≤ 20；`ConditionSpec{field ≤ 64, op ∈ OPERATOR_WHITELIST, value}`）、`condition_logic: Literal["and", "or"] = "and"`；`year` 加 `ge=2000, le=2100`；`columns` ≤ 60。删除 14 个 `_query_*`，`_legacy_business_fetcher` 保留为委托。

### 3.4 构建器
- `services/custom_query/builder_access.py`（新）：`async resolve_builder_access(user, db) -> BuilderAccess(allowed, basis: "system_role" | "project_manager" | None, reason, all_projects: bool, accessible_project_count: int | None)`。`routers/query_builder.require_query_builder_access` 改为 async 依赖（`get_current_user` + `get_db`），拒绝 → 403 `ROLE_FORBIDDEN`「高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用」。新增 `GET /api/query/access`（`get_current_user`，返回 BuilderAccess）。`_require_admin_or_manager` 与 `_QUERY_BUILDER_ROLES`（系统角色）保留。
- `QueryDSL` 增 `project_id: UUID | None`、`year: int | None (2000..2100)`；preview / execute / export 把 `requested_project_id=body.project_id`、`year=body.year` 传给 `resolve_builder_scope`；导出体 `ExportDSL(QueryDSL)` 增 `headers: dict[str, str]`。
- `builder_scope.resolve_builder_scope(*, user, dsl_tables, requested_project_id, year, db)`：可访问集合 = OwnershipGuard 集合 − 已删项目 − 本人循环范围受限的项目（`cycle_scope.is_cycle_restricted`，即 `deps.get_user_scope_cycles` 不为 None；admin / partner 不调用）（有排除时 warning「已排除 N 个对您设有审计循环范围的项目，请在业务视图中查询」）；显式指定且不可访问 → 403 `FORBIDDEN_PROJECT`，指定的是循环受限项目 → 403 `CYCLE_SCOPED_PROJECT`；staff_members（基表或 JOIN 目标）对非 admin / partner → 403 `TABLE_ROLE_FORBIDDEN`。`BuilderScope` 增 `requested_project_id`、`dataset_predicates: Mapping[str, ColumnElement]`（计划中的四表各一条，由 `dataset_query.active_rows_predicate` 预先算好，使下面的谓词构造保持同步）；`describe()` 增 `requested_project_id`。report_config 仍记入 `unscoped_tables`（无 project_id 列），warning 改为「表 'report_config' 为平台级配置；项目副本行只含可访问项目」。
- `builder_scope.scope_predicates(table_name, scope, *, year) -> list[ColumnElement]`：项目谓词（projects 用 `id`；all-projects 时其余表为 `project_id IN (SELECT id FROM projects WHERE NOT is_deleted)`）、`is_deleted = false`（有列时）、`scope.dataset_predicates[table]`（四表）、`year == :year`（有列且带年度）、report_config 的 `or_(applicable_standard.notlike('project:%'), applicable_standard.in_([f'project:{pid}' for pid in 可访问集合]))`（all-projects 不加）。取代 `apply_scope_to_select`。
- `builder_dsl._build_select(..., for_export=False)`：
  ```python
  on_expr = and_(*on_clauses, *target_where, *scope_predicates(target, scope, year=dsl.year))
  stmt = stmt.outerjoin(target_model, on_expr) if jtype == "left" else stmt.join(target_model, on_expr)
  ...
  stmt = stmt.where(*scope_predicates(dsl.table, scope, year=dsl.year))   # WHERE 最后一步，DSL 无法放宽
  ```
  ORDER BY 对可空列 `.nulls_last()`；`for_export=True` 不加 LIMIT / OFFSET；新增 `build_count(stmt)`。`query_builder.execute`：total = count；计划含一对多 JOIN 时追加 warning「该关联为一对多，结果行数可能多于基表行数」；`_derive_formula_refs` 对 tb_balance 返回 None。
- `table_whitelist`：新增 tb_aux_balance、tb_aux_ledger、financial_report（字段按 ORM 现读）；tb_balance 字段补 opening_direction / closing_direction；JOIN 规格增 `target_where: tuple[tuple[str, Any], ...]`、`cardinality: Literal["many_to_one", "one_to_many"]`，按 ADR-AQL-09 表登记并删 RLM → report_config；导入期不变式 `_assert_all_joins_declare_cardinality()`；常量 `DATASET_SCOPED_TABLES`、`ROLE_RESTRICTED_TABLES = {"staff_members": PII_ALLOWED_ROLES}`；schema 端点下发 JOIN 的 cardinality。超 800 行按 §9 先抽伴生模块。
- `dataset_query.active_rows_predicate(db, table, *, project_ids, year) -> ColumnElement`（async，可移植）：先查 ledger_datasets 中 status = active 的行（按 project_ids / year 收窄），在 Python 里按 `activated_at DESC NULLS LAST, created_at DESC`（与 `DatasetService.get_active_dataset_id` 同序）取每个 (项目, 年度) 最新一条；返回 `and_(is_deleted = false, or_(dataset_id.in_(最新 id), tuple_(project_id, year).notin_(有生效数据集的组合)))`。不用 `DISTINCT ON`，也不用逐行相关子查询（百万行表上逐行求值代价高）；查询失败原样上抛。

### 3.5 导出
- `export_service`：`stream_xlsx(..., info_rows: list[tuple[str, str]] | None = None)` 在数据 sheet 后追加「查询说明」sheet；新增 `_text_safe_cell(ws, value)`：字符串以 `= + - @` 开头时返回 `WriteOnlyCell(ws, value=value)` 并置 `data_type = "s"`，否则原值；`_row_export_values(row, columns, source_cols, *, ws)`、`_header_cells` 与「查询说明」都经它（`export_xlsx` 同路径）。
- `services/custom_query/export_gate.py`（新）：进程内 `_GLOBAL = asyncio.Semaphore(4)` 与在途用户集合；`acquire_export_slot(user_id) -> ExportSlot` 非阻塞（本人已有在途或全局已满 → `HTTPException(429, {"error_code": "EXPORT_BUSY", "message": "已有导出在进行，请稍后再试"})`），`ExportSlot.release()` 幂等。
- `POST /api/custom-query/export`（custom_query router）：请求体 `QueryExportRequest(QueryRequest)` + `headers: dict[str, str]` + `file_name: str | None`。流程：`ownership_guard.assert_target_accessible` → 与 execute 同一个解析校验函数 → 带分组 / 透视 400 `EXPORT_GROUPING_UNSUPPORTED` → `acquire_export_slot` → SQL 源 `count` 后 `export_service.resolve_export_mode(row_count=…, materialized=False)`（超限 400）→ 行迭代 = `paged_fetch.stream()`（排序同 execute）；JSON 源 = 全部行 → `agen = stream_xlsx(...)`、`first = await agen.__anext__()` → `StreamingResponse`（生成器先产出 first 再续 agen，`finally` 里释放导出槽）；首块之前任何失败先释放槽再抛 → `Content-Disposition` = `export_service.build_content_disposition(清洗后的 file_name)` → 审计 `audit_logger.log_action("custom_query.export", …)`，失败只记 WARNING。
- `query_builder.export_excel`：同一导出闸 + COUNT 预检 + `_build_select(for_export=True)` + `db.stream` 分批 → 同一 `stream_xlsx`，表头取 `headers`；删除 router 内自写 Workbook 段与 1,000 行限制。

### 3.6 模板与回收站
- `template_service`：删除自有的 `_normalize_scope` / `VALID_INPUT_SCOPES` / `_SCOPE_ALIASES` / `_is_template_visible` / `_normalize_shared_project_ids`，改用 `TemplateScopeAdapter.normalize(scope, shared_project_ids, config_project_id=…)`（`TemplateScopeValidationError` 转 `TemplateInvalidError`）与 `TemplateScopeAdapter.is_visible(*, scope, owner_id, user_id, shared_project_ids, config_project_id, accessible_project_ids)`（纯关键字参数）；`TemplateForbiddenError` 的错误码改为 `TEMPLATE_NOT_VISIBLE`、文案「无权访问该模板」；新增 `soft_delete(tpl)`（调 `SoftDeleteMixin.soft_delete()`，只 flush）、`visible_templates(user, db)`（SQL 取未删且（作者 = 本人或 scope ∈ public / global / project / team）的候选，按 updated_at 倒序逐条判可见，凑满 500 条为止——先过滤后截断）、`config_to_request(config, *, project_id, year, limit, offset)`（execute 唯一翻译：source、filters 并入 cell_range / sheet_name、conditions、condition_logic、selected_columns → columns、sort_field / sort_order → sort、page_size；`filter_text` 是前端显示过滤，不进请求）。
- `TemplateScopeAdapter` 四条报错改中文（「scope 必须是字符串」「不支持的模板范围：{scope}」「指定项目共享至少需要一个项目」「共享项目标识非法：{raw}」），`_normalize_template_scope` 原样放进 422 `TEMPLATE_SCOPE_INVALID`。
- router：list / get / execute 都走 template_service（删除两处 `scope == 'global'`）；get / execute 捕获 `TemplateForbiddenError` → 403 `{"error_code": "TEMPLATE_NOT_VISIBLE", "message": "无权访问该模板"}`（`_assert_template_visible` 同文案）；create / update 捕获 `TemplateInvalidError` → 400 `TEMPLATE_INVALID`；`update_template` 删除末尾 `if body.scope is not None: tpl.scope = body.scope`；delete → `soft_delete` + commit；execute 请求体增 `year`（可选）、`limit`、`offset`，年度 = body.year 或 `fetch_project_audit_year`（None → 422 `YEAR_REQUIRED`）；已软删模板一律 404 `TEMPLATE_NOT_FOUND`。
- ORM `CustomQueryTemplate(Base, SoftDeleteMixin)`（`is_deleted` / `deleted_at` 由 mixin 声明，与迁移列一致）。
- `routers/recycle_bin.py`：`_RECYCLABLE_TABLES` 增 `"custom_query_template": (CustomQueryTemplate, "查询模板", "name")`；`_OWNER_SCOPED = {"custom_query_template": "created_by"}`；`_visibility_filter(tbl_key, model, visible, user)` 对该类型 = `created_by == user.id`（admin 不限）；`_authorize_row` 对该类型 = 作者或 admin；`_deleted_by` 对该类型返回 created_by。

### 3.7 写入收窄与只读查询
- 删除 `snapshot_writer_modules.write_report_cell / write_adj_cell / write_tb_cell` 与 `SnapshotWriter` 对应薄委托及 `write_cell` 三个分支（未知 module → ValueError）；`CellWritebackRequest.module` 与 writeback 目标 module 改 `Literal["workpaper", "note"]`。
- 取行带项目：底稿 `… WHERE wp.id = :wp_id AND wp.project_id = :pid FOR UPDATE OF wp`（缺 pid → ValueError → 400），查不到抛新异常 `WritebackTargetNotFound`；附注 `select(ConsolNoteData).where(ConsolNoteData.id == target_id, ConsolNoteData.project_id == note_project_id).with_for_update()`，查不到 `NoteRecordNotFound`。两者都不会锁他项目行。cell-writeback 与 writeback-confirm 同口径映射：`WritebackTargetNotFound` → 404 `WRITEBACK_TARGET_NOT_FOUND`「目标不存在或不属于本项目」，`NoteRecordNotFound` → 404 `NOTE_RECORD_NOT_FOUND`，`NoteOwnershipMismatch` → 403（只剩同项目内年度 / 章节 / 节点不一致），不再以未捕获异常变 500。
- 预览门（R4.5）：`WritebackPreviewService._build_item` 先核对目标归属（workpaper 按 wp_id 读 `working_paper.project_id`，note 按 note_record_id 读 `consol_note_data.project_id`，只读、不加锁），不属于请求项目或查不到 → `found=False, error="target_not_in_project"`，不解析地址、不读旧值；`_read_workpaper_value` 的取行加 `project_id = :pid`。`generate` 中只要有 `found=False` 条目就 `enter_confirmation=False`，`notice`「有 N 个目标无法定位，请修正后重新预览」，条目照常返回；writeback-confirm 按同一组目标重建预览，既有确认门（`not preview.enter_confirmation`）抛 `WritebackConfirmationConflict` → 409 `WRITEBACK_CONFLICT`，写入循环不执行。
- `fetchers/workpaper_cells.py` 结构写死：写盘只出现在 `_temp_copy(src: Path, tmpdir: Path) -> Path`（`shutil.copy2(src, tmpdir / src.name)`），调用方只传 `tempfile.TemporaryDirectory()` 的目录；`recompute_with_libreoffice(src: Path) -> bytes | None` 在临时目录里复制、转换、读回字节，函数体内无写调用、不触碰 storage；无文件 → 预览返回 `available: false, reason: "该底稿尚未生成文件，请先在底稿编辑器中打开一次"`，区域取数返回同文案（400 `QUERY_FAILED`）；重算失败 warnings「公式未能重算，显示的是文件缓存值」。router `wp_sheet_preview` 改调本模块。

### 3.8 指标树与模板溯源（router 内，函数名保持以兼容既有测试）
- `get_indicators` 增 `year: int | None`；`_build_disclosure_tree(template_type, *, db=None, project_id=None, year=None, report_scope="standalone", user=None)`：有项目且单体 → `DisclosureEngine(db).get_notes_tree(project_id, year)` 叠加循环范围；按章节号首个「、」之前分组，组名取同号章节节点的标题，没有该节点时用章节号；叶子 `disclosure_note:{note_section}`、标签「{章节号} {标题}」，组前置「附注目录」（`disclosure`）；否则沿用种子树。
- 有 project_id 的 indicators 响应（depth=1、branch、全量）都带 `X-Notes-Version` = `sha1(f"{行数}|{max(updated_at)}|{循环章节集合或 *}")[:12]`（disclosure_notes 未删行，ORM 查询）；无项目为 `none`。
- 叶子 `columns` 由注册表生成（JSON 源为 []），叶子增 `supports_conditions`；trial_balance 组增 aux_balance、aux_ledger；adjustment 组改为 adj_aje、adj_rje；单体隐藏 tb_summary 与 worksheet 组；`_INDICATORS_SCHEMA_VERSION = 11`。
- `address_resolve`：按 ADR-AQL-17；目录读取异常记 WARNING 并返回 `registered=false`，不再 500。

### 3.9 删除清单（各自单独提交；删前 grep 0 调用方，删前后跑同一组测试）
| 对象 | 连带处理 |
|---|---|
| `POST /batch-execute` + `BatchQueryToolbar.vue` + `useBatchQuery.ts` + `customQuery.batchExecute`（tasks 6，先于取数器下沉） | 删 `test_batch_query.py`、`useBatchQuery.test.ts`；`test_custom_query_auth_bug_condition.py`、`test_advanced_query_audit_helper.py` 的 batch 用例删除；`test_function_global_names_ratchet.py` 同步跑 |
| `GET /cross-sheet-trace` + `cross_sheet_trace_orchestrator.py` + `FormulaTracePopover.vue` | 删 `test_cross_sheet_trace_orchestrator.py`、`test_cross_sheet_trace_wiring.py`、`useFormulaTrace.test.ts`；`audit_helper.record_cross_sheet_trace` 若 0 调用方一并删并改 `test_audit_helper_pbt.py` / `test_audit_throttle.py` 对应用例 |
| 跨模块单元格源族 + 选区器模块模式 | `module_cell_resolver.py` 只留 `parse_source_uri` / `format_source_uri` / `_NOTE_COLUMNS`（`_REPORT_COLUMNS` / `_ADJ_COLUMNS` 随 tasks 13 写入实现删除）；删前后跑 `test_lazy_import_resolvability.py`（覆盖 `write_note_cell` 的惰性导入名）；`test_module_cell_resolver.py` 只留解析用例并下调白名单基线；删 `test_formula_tb_sign_passthrough.py::test_module_cell_resolver_tb_columns_pure` |
| tb / adj / report 写入 | `test_snapshot_writer.py` 对应用例删除并按实际行数下调白名单基线 1,418；`test_custom_query_auth_*` 的 tb 用例改为断言 422；`test_project_endpoint_authz_body_carried.py` 证明链不变（`_assert_writeback_authorized` 保留） |
| `SaveAsTemplateButton.vue`、`SnapshotStalenessChip.vue`、`customQuery.cellWriteback` | 删 `useSnapshotStaleness.test.ts`；`components.d.ts` 随构建工具重新生成 |

### 3.10 循环范围（`services/custom_query/cycle_scope.py`，新）
```python
@dataclass(frozen=True)
class CycleScope:
    codes: frozenset[str] | None      # None = 不限
    sections: frozenset[str] | None   # None = 不限；空集 = 什么都看不到

async def resolve_cycle_scope(user, project_id: UUID, db) -> CycleScope
async def is_cycle_restricted(user, project_id: UUID, db) -> bool
```
`resolve_cycle_scope`：`cycles = await deps.get_user_scope_cycles(user, project_id, db)`；None → `CycleScope(None, None)`；列表（可为空）→ `codes = get_codes_by_cycles(...)`、`sections = get_sections_by_cycles(...)`，任一调用异常按空集并记 WARNING（与调整分录页「取不到不放行」同）。`is_cycle_restricted` = 同一入口返回值不为 None。注册表在 `FetchContext` 里带上它：试算表源 `standard_account_code IN codes`（空集 = 无行，与试算表页同）；调整分录源 `entry_group_id IN (SELECT entry_group_id FROM adjustments WHERE 项目 + 年度 + 未删 AND account_code IN codes)`；附注目录、附注章节与附注树按 sections 严格过滤（空集即空）。构建器的循环受限项目排除在 `resolve_builder_scope`（§3.4）里逐个可访问项目调 `is_cycle_restricted`。

### 3.11 W3 常用审计预置模板（ADR-AQL-05）
- `backend/data/custom_query_presets.json`（新）：`{version, keyword_sets: {reversal: [...], special_event: [...]}, presets: [{id, name, category, description, notes: [str], config: {source, condition_logic, conditions, sort_field?, sort_order?, page_size?}}]}`。`conditions` 是条件数组，或 `{"$keyword_set": <名>, "field": <字段>, "op": "like"}`（展开为每个词一条）；条件值是字面量，或 `{"$param": <参数名>}`。参数只有三个：`materiality_performance`、`cutoff_start`、`cutoff_end`。
- `services/custom_query/template_presets.py`（新，≤ 300 行）：
  - `load_presets() -> tuple[Preset, ...]`（`lru_cache`）：读 JSON 并逐条 `validate_preset`；不合格的条目记 ERROR（id + 原因）并跳过，其余照常返回（数据文件一处写错不拖垮模板列表）。
  - `validate_preset(p) -> list[str]`：id 符合 `^[a-z0-9_]{1,40}$` 且唯一；数据源经 `source_registry.resolve_source` 可解析；字段是该源可作条件的列（显示列或 `condition_only`）；算子 ∈ `OPERATOR_WHITELIST`；`$param` / `$keyword_set` 已登记；展开后条件 ≤ 20；`condition_logic` ∈ and / or。
  - `list_presets() -> list[dict]`：`{id, name, category, description, data_source, params: [参数名], read_only: True}`。
  - `async resolve(db, preset_id, *, project_id, year) -> dict`：展开词表；`materiality_performance` = `MaterialityService(db).get_current(project_id, year).performance_materiality`，> 0 时取 `str(值)`，否则值为 None 并给 `missing_reason`（无记录「本项目 {year} 年度未设置重要性水平，请填写阈值」/ ≤ 0「本项目重要性水平为负数（{值}），不能作为阈值，请填写」/ 读取异常「重要性水平读取失败，请填写阈值」并记 WARNING）；`cutoff_start` / `cutoff_end` = `cutoff_window(year, cutoff_date=项目 audit_period_end（与 year 同年时）)` 的起止日（ISO 字符串）。返回 `{id, name, config（参数已代入，缺失值为 ""）, params: [{key, label, value, basis, missing_reason}], notes}`；`basis` 例：「本项目 2025 年度实际执行的重要性水平」「期末日 2025-12-31 前后各 5 天（与截止性测试同一默认值）」。
- router `custom_query.py`（只写薄路由，≤ 30 行，逻辑在上面的模块；路由前缀不与 `/templates/{template_id}` 冲突）：
  - `GET /api/custom-query/template-presets`（`get_current_user`）→ `{presets}`。
  - `GET /api/custom-query/template-presets/{preset_id}/resolve?project_id=&year=`：`ownership_guard.assert_target_accessible(project_id)`（与 execute 同一判定）→ year 缺省取 `fetch_project_audit_year`，仍取不到 422 `YEAR_REQUIRED` → `resolve`；未知 id 404 `TEMPLATE_PRESET_NOT_FOUND`。
- `param_sql_builder`：抽出 `_prefix_predicate(col, value)`（转义后 `LIKE value || '%'`），`build_portable_filter` 的 `prefix` 与 `build_filter` 的 `starts_with` 都调它；新增 `_weekday_predicate(col, value)`：列的 `python_type` 不是 date / datetime → 400 `WEEKDAY_FIELD_INVALID`「星期条件只能用于日期字段」；值不是 1~7 个不重复的 0~6 整数 → 400 `INVALID_WEEKDAY_VALUE`；否则 `extract('dow', col).in_(values)`（PG 的 `EXTRACT(DOW)` 与 SQLite 的 `strftime('%w')` 都是 0 = 周日，绑定参数，不拼 SQL；同形先例 `build_ledger_query` 的 `extract('month', …).in_(…)`）。`table_whitelist.OPERATOR_WHITELIST` 增 `starts_with`、`weekday_in`（构建器同时可用）。
- `paged_fetch.build_statement`：除 `is_null` / `is_not_null` 外，值为 None 或去空白后为空串的条件（`between` 任一端、`weekday_in` 的空数组同样算）→ 400 `CONDITION_VALUE_REQUIRED`「条件「{字段中文名}」未填写值」（缺失参数在服务端同样拦住，不只靠前端）；`in` / `not_in` 的空数组保持 ADR-AQL-03 的恒假 / 恒真语义。
- `source_registry`：`SourceSpec` 增 `condition_only: tuple[SourceColumn, ...] = ()`（可作条件、不返回、不导出、不可排序）；`ledger_entries` 增 `line_amount`（`expr = ledger_sampling_service.ledger_line_amount(TbLedger.__table__)`，dtype number）。
- `ledger_sampling_service.ledger_line_amount(table) -> ColumnElement`（新）= `func.greatest(func.coalesce(table.c.debit_amount, 0), func.coalesce(table.c.credit_amount, 0))`；`build_ledger_query` 的阈值与上限两处改调它（SQL 不变）。
- `sampling_enhanced_service`：`DEFAULT_CUTOFF_DAYS_BEFORE = 5`、`DEFAULT_CUTOFF_DAYS_AFTER = 5`、`cutoff_window(year, cutoff_date=None, days_before=…, days_after=…) -> CutoffWindow(period_end, start, end)`（规则照搬 `run_cutoff_test` 现有代码）；`run_cutoff_test` 的默认值与窗口计算改用它们（行为不变）。
- 指标树叶子 `condition_fields`（ADR-AQL-16，schema 12）。
- 生成器 `backend/scripts/gen/gen_journal_entry_rules_ts.py`（新，先例 `gen_account_to_wp_ts.py`）：`render(presets_json) -> str` 写出 `audit-platform/frontend/src/generated/journalEntryRules.ts`（`export const SPECIAL_EVENT_KEYWORDS = [...] as const`，文件头写「由 custom_query_presets.json 生成，禁止手改」）；`--write` 幂等（无时间戳）、`--check` 漂移 exit 2。

### 3.12 W6 业务对象 → 科目（ADR-AQL-20）
- `services/custom_query/entry_accounts.py`（新，≤ 250 行）：
  - `codes_for_wp_code(wp_code) -> tuple[str, ...]`：读 `wp_account_mapping.json`（路径取 `mapping_service._get_wp_mapping_path()`，与循环映射同一文件；按文件 mtime 缓存索引）；编码精确匹配，没有该编码时取主编码；都没有或 `account_codes` 为空 → `()`。
  - `async codes_for_note_section(db, *, project_id, year, section, template_type) -> NoteSectionAccounts(title, wp_codes, codes)`：取本项目年度该章节的 `disclosure_notes.section_title`（ORM，未删；没有 → `NoteSectionNotFound`）→ `note_account_mappings`（ORM `models/note_account_mapping.NoteAccountMapping`；`template_type = f"{准则}_standalone"`——表里只有两种 standalone 变体，合并版无底稿映射，与 `linkage_graph_builder._from_note_account_mapping` 同口径；`note_section_code` 存的是章节业务名称，按标题等值匹配；`wp_code` 非空）→ 底稿编码集合 → 逐个 `codes_for_wp_code` 求并集。
  - `async report_row_predicate(db, *, project_id, year, report_type, row_code, column) -> tuple[ColumnElement, dict]`：取 `financial_report`（项目、年度、`report_type::text`、行次、未删）的 `source_accounts` 与 `formula_used`；没有该行 → `ReportRowNotGenerated`；不是数组或为空 → `ReportRowNoAccounts`；否则单码 → `_prefix_predicate(column, 码)`、`起~止` → `column.between(起, 止)`，`or_` 连接；返回谓词与 `{codes, formula}`。
- 注册表筛选键（`FilterKey` 增可选 `resolver: Callable[[FetchContext, value], Awaitable[ColumnElement]]`，有 resolver 的键不走 `build_portable_filter`）：
  - `account_code`（account_balance、ledger_entries、aux_balance、aux_ledger）：值可为字符串或 ≤ 50 项的数组，多值按前缀 `or_`。
  - `wp_code`（同上四源）：`codes_for_wp_code` → 前缀列表；空 → 400 `WP_CODE_NO_ACCOUNTS`「该底稿没有登记对应科目」；`aux_ledger.required_filters` 增 `{wp_code}`。
  - `report_row`（trial_balance）：值 `<报表类型>:<行次>`，经 `report_row_predicate`；两类异常 → 400 `REPORT_ROW_NOT_GENERATED`「该报表行尚未生成，请先在报表页生成报表」/ `REPORT_ROW_NO_ACCOUNTS`「该报表行没有直接取数的科目（合计行或矩阵报表），请在报表页查看公式」；warnings「构成科目按报表公式 {formula} 的取数科目列出（含减项）」。
  - `note_section`（trial_balance）：先按 ADR-AQL-19 判章节是否在本人范围（范围外 403 `SECTION_OUT_OF_SCOPE`），再 `codes_for_note_section` → `standard_account_code IN codes`；章节不存在 / 没有科目 → 400 `NOTE_SECTION_NOT_FOUND`「本项目该年度没有这个附注章节」/ `NOTE_SECTION_NO_ACCOUNTS`「该附注章节没有登记对应科目」。
- 响应 `meta.entry_accounts`：本次解析出的科目码（排序，最多 50 个）供弹窗显示；`meta` 键仅在非空时出现（N3）。

## 4. 前端设计

### 4.1 新模块
- `components/query/queryResultLinks.ts`：`buildRowDrill(ctx: {kind: "source" | "table", key, projectId, year}, row) -> {location, label} | null`（ADR-AQL-01 的唯一实现；账簿查询的 query 由 `useLedgerUrlSync.ts` 新导出的纯函数 `buildLedgerQuery(state, year)` 生成，`syncToUrl` 也改用它）；`buildFormulaRef(source, row, columnKey) -> string | null`；`validatePageRefs(refs, {projectId, year, templateType}) -> Map<ref, {ok, reason}>`（ADR-AQL-18 的批量校验，每批 ≤ 200）；常量 `TB_REF_COLUMNS`。
- `components/query/queryErrorText.ts`：`describeQueryError(err) -> {message, correlationId?}`：读响应体（信封 `message` 为对象时取其 `message` / `error_code`；响应头 `X-Correlation-ID` 兜底）；422 detail 按 pydantic `type`（greater_than_equal / less_than_equal / missing / literal_error / string_too_long / too_long / int_parsing）译成中文，字段名用 `resolveColumnLabel` 与内置请求字段名表；429 `EXPORT_BUSY` 原样显示后端文案。
- `components/query/queryEntryContext.ts`：`resolveQueryEntryContext(route) -> {projectId?, year?, source?}`（TrialBalance → tb_detail；Reports → `report_<?tab 或 balance_sheet>`；DisclosureNotes → 有 `?section` 时 `disclosure_note:<section>`，否则 disclosure；Adjustments → adj_aje；LedgerPenetration → level ∈ {ledger, voucher} 为 ledger_entries、aux_balance / aux_ledger 同名、其余 account_balance；AuxSummary → aux_balance；WorkpaperEditor → workpaper）；纯函数 `resolveDialogOpenContext({route, eventPayload, previous}) -> {projectId, year, initialSource}`（事件 project_id 优先于路由、非项目页不给项目、关闭后清空），供 ThreeColumnLayout 调用与 vitest。
- `components/query/queryTemplateCache.ts`：模板列表 sessionStorage 缓存读写与失效（从 MyTemplatesDialog 挪出）。
- `components/query/queryIndicatorCache.ts`：`indicatorCacheKey({schema, projectId, year, notesVersion})` = `gt:custom-query:indicators:{schema}:{pid}:{year}:{notesVersion}`、读 / 写 / 清理旧版本；弹窗与页面版共用。
- `composables/useReportRouteFocus.ts`：`useReportRouteFocus({route, activeTab, reportMode, rows, compareRows, rvTableRef, compareTableRef, notify}) -> {routeYear, initialTab}`：`?tab` 是合法页签名时作初始页签；首次加载完行后读 `?highlight`：矩阵报表（equity_statement、impairment_provision）只提示「该报表为矩阵格式，已打开对应报表」；对比模式在 `compareTableRef`、其余在 `rvTableRef` 上按 row_code `setCurrentRow` 并滚动居中；找不到该行次提示「未找到行次 {code}」；同一路由只执行一次。

### 4.2 组件改造
- `CustomQueryDialog.vue`：打开时 `localProjectId = props.projectId || ""`（不再取列表第一项）；年度 = `props.year ?? 所选项目 audit_year ?? null`，null 时禁用查询并提示「请选择审计年度」；请求加 `_silent: true`、删 `validateStatus`，失败在结果区 `el-alert` 显示 `describeQueryError` + 「复制追踪号」；分页（100 / 200 / 500）+ 真实 total，删除「已达上限」判断；本地文字筛选占位文案改「仅筛选本页」；结果表首列「操作」：「打开」（buildRowDrill）、「复制引用」（buildFormulaRef + validatePageRefs 结果）；`jumpToCell` 改走 buildRowDrill（`?cell=`）；源键 `adj_rcl` → `adj_rje`；`meta.tables` 多于 1 张时显示表格切换；「导出 ▾」= 导出全部（服务端）/ 导出当前页；「📑 模板」改为打开 MyTemplatesDialog（载入 / 执行）；构建器页签按 `useQueryBuilderAccess` 渲染，无权时 disabled + 原因，向内嵌构建器传 projectId / year；指标树缓存改用 `queryIndicatorCache`（`notesVersion` 取 depth=1 探测的 `X-Notes-Version`）。
- `CustomQueryTab.vue`：条件 → `conditions`（eq / like / gt / lt / between / is_null / is_not_null）+ `condition_logic`，条件区做成独立组件 `components/query/QueryConditionEditor.vue`（v-model `{conditions: {field, op, value}[], logic}`，与模板 `config.conditions` 同形，W3 起弹窗复用）；字段下拉与勾选框用 `resolveColumnLabel`；条件值框 `min-width: 120px`、条件行可换行；年度规则同弹窗；源下拉按 ADR-AQL-16 拍平并带项目、年度加载（缓存同弹窗）；`supports_conditions=false` 时禁用条件区并提示；操作列与导出同弹窗；删除内联模板列表对话框，改用 MyTemplatesDialog；ACNR 面板「开发中」。
- `views/AdvancedQueryBuilder.vue`：props `projectId?` / `year?`；「跨项目」开关（`accessible_project_count > 1` 或 `all_projects` 时出现）；payload 带 project_id / year；翻页（offset）+ total；导出带 headers；单项目范围时结果操作列下钻与复制引用；ACNR 面板「开发中」。
- `composables/useQueryBuilderAccess.ts`：首次调用 `GET /api/query/access`（模块级缓存，登出清空），返回 `canUseBuilder` / `builderDisabledReason` / `accessibleProjectCount` / `allProjects` / `loading`；删除 `QUERY_BUILDER_ROLES` 常量。
- `layouts/ThreeColumnLayout.vue`：新增 `const customQueryYear = computed(() => { const v = Number(route.query.year); return Number.isFinite(v) && v > 2000 ? v : undefined })`，只用于 `<CustomQueryDialog :year>`；`currentYear` 与它传给 FormulaManagerDialog / GtRefreshScopeDialog 的绑定不动；打开 / 关闭经 `resolveDialogOpenContext`（事件 project_id 存入 override、侧栏打开预选数据源、关闭清空 override 与 initialSource）。
- `components/query/MyTemplatesDialog.vue`：命名导入 `api`、读 `{templates, total}`、缓存走 queryTemplateCache、删除确认文案「删除后可在回收站恢复」；每行「载入」emit `load(config, tpl)`、「执行」emit `run(tpl)`（`allowRun` 控制显示）。
- `views/ReportView.vue`：`routeYear` 计算属性移入 useReportRouteFocus，`activeTab` 初值取 `initialTab`，净增 ≤ 0 行。
- `views/TemplateLibraryMgmt.vue`：挂载时 `?tab` 合法则设 activeTab，向 WpTemplateTab 传 `initial-search = ?wp_code`；`WpTemplateTab.vue` 增 `initialSearch` prop 种入 searchInput。
- `components/query/SheetCellRangePicker.vue`：删除模块模式（moduleSource、isModuleMode、moduleLabel 与 module 分支）；年度改由父组件传入，未传时禁用预览并提示「请先选择审计年度」。
- `components/query/queryColumnLabels.ts`：`summary` → 「摘要」；新增 `QUERY_SOURCE_LABEL_OVERRIDES = { ws_consol_tb: { summary: "汇总数" } }` 与 `resolveColumnLabel(key, title?, source?)`；补 aux_type、aux_code、aux_name、aux_type_name、opening_direction、closing_direction、entry_group_id、adjustment_type 中文。
- `services/apiPaths/system.ts`：customQuery 增 `export`、`templateExecute(id)`，删 `batchExecute`、`cellWriteback`；新增 `queryBuilder = { access, schema, preview, execute, exportExcel }`，构建器改用。`types/custom-query-template.ts` 增 `condition_logic?: "and" | "or"`。
- `__tests__/auditYearCalendarFallbackBaseline.json`：删除 CustomQueryDialog、SheetCellRangePicker、CustomQueryTab 三条（只动这三行；ThreeColumnLayout 条目保留）。

### 4.3 W3 / W6 前端（ADR-AQL-05 / 20；页面文件只加最小接线，逻辑在新组件与 composable）
- `QueryConditionEditor.vue`（W3 扩展）：props `fields: {key, dtype}[]`（来自叶子 `condition_fields`，缺省按 `columns` 当文本）、`notices?: string[]`（预置参数说明，显示在条件区上方）、`disabled?`；算子按 dtype 给：文本 等于 / 包含 / 开头是 / 为空 / 不为空，数值 等于 / 大于 / 大于等于 / 小于 / 小于等于 / 介于 / 为空 / 不为空，日期 再加「星期为」（多选 周一…周日 ⇒ 1…6、0）；导出 `incompleteReason`（首个未填值的条件：「条件「{字段}」未填写值」），宿主据此禁用「查询」「💾 保存」；导出常量 `EDITOR_OPS`（vitest 用它核对预置 JSON 的算子都在编辑器选项内）。
- `MyTemplatesDialog.vue`（W3）：props 增 `projectId`、`year`；顶部「系统预置」分区（`GET /template-presets`，列表缓存走 `queryTemplateCache` 的独立键），每行只有「载入」「另存为我的模板」，不显示编辑、删除、执行；两个操作都先调 `resolve`（带 props 的项目与年度；没有项目时按钮不可用，提示「请先选择项目」），再 emit 与用户模板同名的 `load(config, item, notices)`，或新增的 `save-as(config, item, notices)`；`notices` = 每个参数一行（有值：「当前阈值：{basis} {value} 元」/「截止窗口：{basis}」；缺失：`missing_reason`）+ 预置 `notes`（用户模板的 `load` 不带第三个参数）。
- `CustomQueryDialog.vue`：W3 嵌入 `QueryConditionEditor`（「条件」折叠面板，`supports_conditions=false` 的源禁用），请求带 `conditions` / `condition_logic`；处理 `load`（带 `notices` 时交给编辑器显示）/ `save-as`（载入后打开既有 💾 保存对话框，默认名「{预置名}（我的）」）。W6 新 prop `entry?: QueryEntryRequest | null`，打开时交给 `useQueryEntry`；结果区上方挂 `QueryEntryBanner`；试算表结果行的操作列增「查明细」。
- `CustomQueryTab.vue`（W3）：处理 MyTemplatesDialog 的两个事件，同弹窗。
- `queryEntryContext.ts`（W6，ADR-AQL-20 映射的唯一实现）：`buildQueryEntry(kind, target, route) -> QueryEntryRequest | {disabledReason}`，`QueryEntryRequest = {kind, projectId, year?, source, filters, label, switches: {source, label}[]}`；`tb_row`（合计 / 小计行 → `disabledReason`「合计行请在高级查询中按科目查询」）、`report_row`（读 `drilldownData` 的 `report_type` / `row_code` / `row_name`）、`note_section`（读当前附注的 `note_section` / `section_title`）、`workpaper`（读 `wp_code` / `wp_name`）；`tbRowDrill(row, entry)` 生成行内「查明细」的下一跳。
- `composables/useQueryEntry.ts`（W6，≤ 250 行）：应用 entry（项目、年度、数据源、筛选，随后执行）、切换（保留筛选换源）、行内下钻（压栈，最多 5 层，「← 返回上一查询」出栈）、清除；用户手动换数据源时自动清除；保存模板时把 entry 的筛选写进 `config.filters`（`types/custom-query-template.ts` 增 `filters?: Record<string, string | string[]>`）。
- `QueryEntryBanner.vue`（W6，≤ 150 行）：显示 `label`、`meta.entry_accounts`、切换按钮、「清除上下文」「← 返回上一查询」；按钮带 aria-label（N5）。
- `QueryDetailEntry.vue`（W6，≤ 120 行，放 `components/query/`；页面显式 import，与各页现有写法一致，不依赖由构建工具重写、且常被并发会话改动的 `components.d.ts`）：props `kind`、`target`、`variant: 'ctx' | 'button'`；项目、年度读当前路由；点击 `eventBus.emit('open-custom-query', { entry })` 并 emit `opened`（页面用它关右键菜单）；不可用时置灰并 title 显示原因。`utils/eventBus.ts` 的 `open-custom-query` 载荷类型增 `entry?: QueryEntryRequest`；`ThreeColumnLayout.vue` 增 `customQueryEntry` 引用并绑 `:entry`（经 `resolveDialogOpenContext` 传递，关闭清空；+≤ 3 行）。
- 页面接线（每页另加 1 行 import）：`TrialBalance.vue` 右键菜单插槽 1 行 `<QueryDetailEntry kind="tb_row" variant="ctx" :target="tbCtx.contextMenu.rowData" @opened="tbCtx.closeContextMenu()" />`（放在「📊 查看明细」之后）；`DisclosureEditor.vue` 右键菜单 1 行（`kind="note_section"`、`:target="currentNote"`、`@opened="deCtx.closeContextMenu()"`，放在「📊 穿透到序时账」之后）；`WorkpaperEditor.vue` 两个工具栏各 1 行（`kind="workpaper"`、`variant="button"`、`:target="wpDetail"`）；`ReportView.vue` 0 行——入口放 `components/report/ReportDrilldownDialogs.vue` 穿透弹窗内（`:target="drilldownData"`），`views/composables/useReportDrilldown.ts` 的 `onDrilldown` 给 `drilldownData` 加 `report_type`（当前页签）、`year`、`project_id`，`ReportDrilldownData` 类型增这三个可选字段。
- `queryColumnLabels.ts`：`line_amount`「发生额（借贷较大者）」。`composables/useC24AnalyticsEngine.ts`（W3）：特殊事件词表改为 `import { SPECIAL_EVENT_KEYWORDS } from '@/generated/journalEntryRules'`，其余不动。

## 5. 错误处理（失败条件 → 可恢复性 → 调用方收到 → 日志）

| 操作 | 失败条件 | 可恢复 | 调用方收到 | 日志 |
|---|---|---|---|---|
| execute / export / indicators / 模板执行 | 项目不可访问或标识无效 | 否（权限） | 403 `FORBIDDEN_PROJECT`「无权访问该项目数据」 | 审计 `advanced_query.ownership_denied`（既有） |
| 同上 | 未知数据源 | 是（改参数） | 400 `UNKNOWN_SOURCE`（既有） | 不记 |
| 同上 | 未登记筛选键 / 条件字段 / 算子 / 列 | 是 | 400 `UNKNOWN_FILTER_KEY` / `UNKNOWN_CONDITION_FIELD` / `OP_NOT_ALLOWED` / `UNKNOWN_COLUMN`，message 指明对象与可用项 | 不记 |
| 同上 | 条件值无法转换（日期、金额、UUID） | 是 | 400 `INVALID_DATE` / `INVALID_DECIMAL` / `INVALID_UUID` / `INVALID_BETWEEN_VALUE` / `INVALID_IN_VALUE`（param_sql_builder 既有） | 不记 |
| 同上 | 排序字段 / 方向非法 | 是 | 422 `INVALID_SORT_FIELD` / `INVALID_SORT_FIELD_DIRECTION`（既有） | 不记 |
| 辅助明细 | 未按科目或辅助类型筛选 | 是 | 400 `AUX_FILTER_REQUIRED`「辅助明细请先按科目或辅助类型筛选」 | 不记 |
| 附注章节 | 章节不在本人循环范围 | 否 | 403 `SECTION_OUT_OF_SCOPE` | 不记 |
| SQL 源分页 | offset > 100,000 | 是 | 422 `OFFSET_TOO_DEEP`「请缩小范围或使用导出」 | 不记 |
| SQL 源分组 / 透视 | 参与行数 > 5,000 | 是 | 400 `AGGREGATION_TOO_LARGE`（带实际行数） | 不记 |
| 内存源 | 行数 > 5,000 / 带 conditions | 是 | 400 `RESULT_TOO_LARGE` / `CONDITIONS_UNSUPPORTED` | 不记 |
| SQL 执行 | 语句超时 | 是（缩小范围） | 408 `QUERY_TIMEOUT` 中文 | WARNING + `record_query_rejected` |
| SQL 执行 | 其他数据库异常（含查生效数据集失败） | 否 | 500 `INTERNAL_ERROR` + `correlation_id`（体与 `X-Correlation-ID` 头，既有路径） | ERROR（带追踪号） |
| 四表 / 报表源 | 无生效数据集 / 未生成 / 已过期 | — | 200 + warnings | 不记 |
| 导出 | 行数 > 1,000,000 或列超 Excel 上限 | 是 | 400 `EXPORT_ROW_HARD_LIMIT` / `EXPORT_CAPACITY`（首字节前，既有） | 不记 |
| 导出 | 带分组 / 透视 | 是 | 400 `EXPORT_GROUPING_UNSUPPORTED` | 不记 |
| 导出 | 本人已有在途导出或全进程已满 4 个 | 是（稍后重试） | 429 `EXPORT_BUSY`「已有导出在进行，请稍后再试」 | 不记 |
| 导出 | 首块之后读临时文件失败 | 否 | 连接中断，前端提示「导出未完成，请重试」；导出槽在生成器 finally 释放 | ERROR |
| 导出审计 | 审计写入失败 | — | 不影响下载 | WARNING |
| 构建器 | 准入不足 | 否 | 403 `ROLE_FORBIDDEN`（中文原因含合伙人） | 不记 |
| 构建器 | staff_members 越权 | 否 | 403 `TABLE_ROLE_FORBIDDEN` | 审计 `custom_query.pii_denied` 同路径 |
| 构建器 | 指定不可访问项目 / 指定循环受限项目 | 否 | 403 `FORBIDDEN_PROJECT` / `CYCLE_SCOPED_PROJECT`「该项目对您设有审计循环范围，请在业务视图中查询」 | 审计（既有守卫） |
| 回写 | module 为 tb / adj / report | 是 | 422（pydantic Literal） | 不记 |
| 回写 | 缺 / 错 `X-File-Opened-At` | 是 | 400（既有） | 不记 |
| 回写 | 目标不属于请求项目 | 否 | 404 `WRITEBACK_TARGET_NOT_FOUND`（底稿）/ 404 `NOTE_RECORD_NOT_FOUND`（附注）；不加锁 | 不记 |
| 回写预览 / 确认 | 有目标无法定位 | 是（修正后重新预览） | 预览 200 `enter_confirmation=false` + notice；确认 409 `WRITEBACK_CONFLICT`，不写入 | 不记 |
| 模板保存 / 更新 | scope、名称、分享项目非法 | 是 | 422 `TEMPLATE_SCOPE_INVALID` / 400 `TEMPLATE_INVALID`，中文原因（不再 500） | 不记 |
| 模板读取 / 执行 | 不可见 / 已删除 | 否 | 403 `TEMPLATE_NOT_VISIBLE`「无权访问该模板」/ 404 `TEMPLATE_NOT_FOUND` | 不记 |
| 模板执行 | 目标项目审计年度不可解析且未传 year | 是 | 422 `YEAR_REQUIRED` | 不记 |
| 回收站恢复 / 彻底删除模板 | 非作者且非 admin | 否 | 403 | 不记 |
| address-resolve | URI 非法 / 模板目录读取失败 | 是 / — | 400（既有）/ 200 `registered=false` | 不记 / WARNING |
| 底稿预览 / 区域取数 | storage 无文件 | 是（先打开底稿） | 200 `available=false` / 400 `QUERY_FAILED` 中文 | 不记 |
| 底稿区域取数 | LibreOffice 不可用或失败 | — | 200 + warnings「公式未能重算」 | WARNING |
| 前端复制引用 | 校验接口失败 / 引用无效 | 是 | 按钮不可用并显示原因 | 不记 |
| execute（W3 条件） | 条件值为空（为空 / 不为空除外） | 是（填写） | 400 `CONDITION_VALUE_REQUIRED`「条件「{字段}」未填写值」 | 不记 |
| 同上 | 星期条件用于非日期字段 / 值不是 1~7 个不重复的 0~6 整数 | 是 | 400 `WEEKDAY_FIELD_INVALID` / `INVALID_WEEKDAY_VALUE` | 不记 |
| 预置列表 | JSON 中某条不合格 | — | 200，该条不出现 | ERROR（id + 原因） |
| 预置解析 | id 未知 / 项目不可访问 / 年度不可解析 | 否 / 否 / 是 | 404 `TEMPLATE_PRESET_NOT_FOUND` / 403 `FORBIDDEN_PROJECT` / 422 `YEAR_REQUIRED` | 不记 / 审计（既有守卫）/ 不记 |
| 预置解析 | 没有重要性记录、值 ≤ 0、读取异常 | 是（填写阈值） | 200，该参数 `value=null` + `missing_reason`，条件值为空串 | 不记 / 不记 / WARNING |
| execute（W6 筛选键） | 报表行未生成 / 无直接取数科目 | 是（先生成报表 / 改看公式） | 400 `REPORT_ROW_NOT_GENERATED` / `REPORT_ROW_NO_ACCOUNTS` | 不记 |
| 同上 | 附注章节不存在 / 没有登记科目 / 章节在本人范围外 | 是 / 是 / 否 | 400 `NOTE_SECTION_NOT_FOUND` / 400 `NOTE_SECTION_NO_ACCOUNTS` / 403 `SECTION_OUT_OF_SCOPE` | 不记 |
| 同上 | 底稿没有登记科目 | 是 | 400 `WP_CODE_NO_ACCOUNTS` | 不记 |
| 同上 | `account_code` 多于 50 项或含空值；`report_row` 不是「类型:行次」或类型非法 | 是 | 400 `INVALID_FILTER_VALUE`（指明键与规则） | 不记 |
| 前端入口（W6） | 合计 / 小计行、目标对象为空 | 是 | 入口置灰并显示原因，不发请求 | 不记 |

前端统一：查询类请求带 `_silent: true`（拦截器在 5xx 重试之前返回），由 `describeQueryError` 渲染；`AbortError` / 取消不提示。

## 6. 外部输入校验

| 输入 | 必填 | 类型与上限 | 失败行为 |
|---|---|---|---|
| execute `project_id` | 是 | UUID 字符串 | 无效 → 403（OwnershipGuard，既有） |
| execute `year` | 是 | int 2000..2100 | 422 |
| execute `source` | 是 | 注册源键 / 别名 / `consol_unit:` / `workpaper:` / `disclosure_note:` 形态 | 400 `UNKNOWN_SOURCE` |
| execute `filters` | 否 | dict，键 ∈ 源 `filter_keys`，值标量；辅助明细至少含 account_code 或 aux_type | 400 `UNKNOWN_FILTER_KEY` / `AUX_FILTER_REQUIRED` |
| execute `conditions` | 否 | ≤ 20 项；field ≤ 64 且为可条件列；op ∈ `OPERATOR_WHITELIST`；between 为 2 元数组；in / not_in 数组 ≤ 500 | 400 / 422（见 §5） |
| execute `condition_logic` | 否 | `and` / `or` | 422 |
| execute `columns` | 否 | ≤ 60，⊆ 源显示列 | 400 `UNKNOWN_COLUMN` |
| execute `sort` | 否 | ≤ 5 项，字段可排序 | 422（既有） |
| execute `limit` / `offset` | 否 | 1..2000 / ≥ 0（SQL 源 ≤ 100,000） | 422 |
| export `headers` | 否 | ≤ 60 项，键 ⊆ 输出列，值 1..100 字符 | 422 |
| export `file_name` | 否 | ≤ 100 字符，服务端清洗非法字符 | 清洗后使用，空则用「数据源_年度」 |
| QueryDSL `project_id` / `year` | 否 | UUID / int 2000..2100 | 422；不可访问或循环受限 403 |
| ExportDSL `headers` | 否 | 同 export | 422 |
| 模板 `name` | 是 | 去首尾空白 1..200 | 400 `TEMPLATE_INVALID` |
| 模板 `scope` | 否（默认 private） | private / project / public（及兼容 personal、global、team） | 422 `TEMPLATE_SCOPE_INVALID` |
| 模板 `shared_project_ids` | project 时必填 | 1..50 个 UUID，逐个 edit 鉴权 | 422 / 403 |
| 模板 `config` | 是 | dict，序列化 ≤ 64 KB | 422 |
| 模板执行 `project_id` / `year` / `limit` / `offset` | project_id 必填 | UUID / 可选 int 2000..2100 / 1..2000 / ≥ 0 | 422；年度不可解析 422 `YEAR_REQUIRED` |
| indicators `year` | 否 | int 2000..2100，缺省取项目审计年度 | 422 |
| address-resolve `uri` | 是 | ≤ 500 字符且 `parse_source_uri` 可解析 | 400 |
| execute `conditions[].op = starts_with` | — | value 字符串 1..64 | 400 `CONDITION_VALUE_REQUIRED` / 422 |
| execute `conditions[].op = weekday_in` | — | value 为 1..7 个不重复的 0..6 整数；字段为日期列 | 400 `INVALID_WEEKDAY_VALUE` / `WEEKDAY_FIELD_INVALID` |
| execute `filters.account_code` | 否 | 字符串 1..40，或 1..50 项的字符串数组 | 400 `INVALID_FILTER_VALUE` |
| execute `filters.wp_code` / `note_section` | 否 | 字符串 1..40 / 1..80 | 400 `INVALID_FILTER_VALUE` |
| execute `filters.report_row` | 否 | `<FinancialReportType 值>:<行次>`，≤ 80 字符 | 400 `INVALID_FILTER_VALUE` |
| 预置解析 `preset_id` | 是 | `^[a-z0-9_]{1,40}$` 且在已加载清单中 | 404 `TEMPLATE_PRESET_NOT_FOUND` |
| 预置解析 `project_id` / `year` | project_id 必填 | UUID / 可选 int 2000..2100 | 403（OwnershipGuard）/ 422；年度不可解析 422 `YEAR_REQUIRED` |

## 7. 不变量与所有者

| 不变量 | 所有者（唯一实现处） | 为什么在这一层 |
|---|---|---|
| 四表只读当前生效数据集 | `services/dataset_query.py`（`get_active_filter` 单项目、`active_rows_predicate` 多项目，同模块） | 平台已规定四表读路径唯一入口；两种形态放一起由 PG 等价测试互证 |
| 构建器只见可访问未删项目的未删行，用户 DSL 不能放宽，LEFT JOIN 不丢基表行 | `builder_scope.scope_predicates`：基表谓词在 WHERE 最后一步，JOIN 目标谓词在该 JOIN 的 ON | 构建器所有端点必经；WHERE 末端 AND 追加使 DSL 无法覆盖，目标表放 ON 才不把左连接变成内连接 |
| JOIN 不静默翻倍 | `table_whitelist` 登记的 target_where + cardinality（导入期不变式） | 登记即声明，未声明不能导入 |
| 业务视图项目隔离 | `OwnershipGuard.assert_target_accessible`（编排器 step1，既有） | 执行、导出、模板执行三条入口共用 |
| 循环范围与原页面一致 | `services/custom_query/cycle_scope.py`（业务视图；构建器排除经它的 `is_cycle_restricted`），两者都只调 `deps.get_user_scope_cycles` | 平台口径（`effective_scope`）只有这一个入口，复用它口径不会分叉 |
| SQL 源 total 与排序在全量上成立 | `paged_fetch`（COUNT 与 ORDER BY 同一 WHERE） | 只有数据库能对全量排序计数 |
| 内存分页只用于确认完整的行集，默认保持行序 | 取数层判触顶；编排器 `_run_pipeline` 分页；`pagination` 以 `_row_index` 为默认排序与 tie-breaker | 触顶判定在取数层，分页在编排层，二者分离 |
| 默认排序 | SQL 源 = 注册表；内存源 = `pagination.DEFAULT_SORT_BY_SOURCE` | 一个源只有一个所有者 |
| 条件谓词参数化 | `param_sql_builder`（`build_filter` / `build_portable_filter` / `build_where`） | 构建器、业务视图条件、旧筛选键共用一处 |
| 报表源结构 = 报表生成结构 | 注册表报表源谓词（PG 测试与 `load_effective_report_configs` 逐集合对拍） | 报表生成是金额的写入方，结构以它为准 |
| TB 审定数只经发布门 | AST 棘轮 `test_aql_publish_rows_callers.py` | 防回归的唯一可执行判据 |
| 查询路径不写 storage | `fetchers/workpaper_cells.py`（写盘只在 `_temp_copy`）+ AST 守卫 | 预览与区域取数唯一实现处 |
| 回写不碰他项目行 | `snapshot_writer` 两个取行语句（WHERE 含项目）+ `writeback_preview._build_item` 归属核对 | 加锁发生在取行，项目条件必须在同一语句；预览不读他项目旧值 |
| 模板可见性 | `TemplateScopeAdapter.is_visible`（template_service 委托，router 不自判） | 列表、详情、执行三处结论一致 |
| 构建器准入 | `builder_access.resolve_builder_access`（依赖与 access 接口共用） | 前后端同源 |
| 导出并发 | `export_gate`（业务视图与构建器导出共用） | 一处计数才有上限 |
| 下钻路由与引用语法 | 前端 `queryResultLinks.ts`（账簿 query 由 `buildLedgerQuery` 生成） | 三个结果表共用一处 |
| 列中文标签 | 前端 `queryColumnLabels.ts`（导出表头也由它经请求传入） | advanced-query-consolidation R1 既定真源 |
| 预置定义与特殊事件词表 | `backend/data/custom_query_presets.json`（C24 经生成文件读同一词表，`--check` 守住） | 用户首选 JSON；一处改动两处生效 |
| 预置参数取值（重要性、截止窗口） | 服务端 `template_presets.resolve`（缺失留空 + 原因，不给默认） | 要读项目数据；前端不该决定审计阈值 |
| 大额口径「借、贷较大者」 | `ledger_sampling_service.ledger_line_amount`（抽凭、截止测试、查询共用） | 原表达式就在这里，抽出后三处同一实现 |
| 期末前后窗口 | `sampling_enhanced_service.cutoff_window` 与两个默认值常量 | 截止性测试是该口径的原所有者 |
| 业务对象 → 科目（报表行、附注章节、底稿） | 后端 `custom_query/entry_accounts.py` | 依赖库内报表结果与映射表；前端只传对象键 |
| 业务页入口 → 查询参数 | 前端 `queryEntryContext.buildQueryEntry` | 用户要求一处映射；四个页面只挂组件 |
| 空条件值不执行 | 前端 `QueryConditionEditor.incompleteReason` + 后端 `paged_fetch` 的 `CONDITION_VALUE_REQUIRED` | 前端给即时提示，后端是不可绕过的那一道 |

## 8. 迁移（实施时现扫 `backend/migrations/V*.sql` 取 MAX+1，现最高 V205）
`V{n}__custom_query_template_soft_delete.sql`：
```sql
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS deleted_at timestamptz NULL;
CREATE INDEX IF NOT EXISTS idx_cqt_live_updated ON custom_query_templates (is_deleted, updated_at DESC);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_custom_query_templates_scope') THEN
    ALTER TABLE custom_query_templates ADD CONSTRAINT ck_custom_query_templates_scope
      CHECK (scope IN ('private', 'team', 'project', 'public', 'global', 'personal'));
  END IF;
END $$;
```
`R{n}__custom_query_template_soft_delete.sql`：`ALTER TABLE … DROP CONSTRAINT IF EXISTS ck_custom_query_templates_scope; DROP INDEX IF EXISTS idx_cqt_live_updated; ALTER TABLE … DROP COLUMN IF EXISTS deleted_at, DROP COLUMN IF EXISTS is_deleted;`。三层：迁移 + ORM（`SoftDeleteMixin` 声明两列，§3.6）+ `template_service.soft_delete` / `visible_templates`。开发服务器热重载不跑迁移 ⇒ 落库用 `MigrationRunner(...).run_pending()`，不重启共享 start-dev。

## 9. 行数门与文件预算（splitlines 口径；门禁 = 白名单 × 1.05）

| 文件 | 现状 | 预期 | 处置 |
|---|---|---|---|
| `routers/custom_query.py` | 3,086（白名单 2,966） | ≈ 1,900 | 先删 batch-execute、再下沉取数器，再做其余改动；完成后白名单基线下调为真实行数 |
| `services/custom_query/table_whitelist.py` | 700 | ≤ 800 | 超 800 先把列分层 / 敏感表段抽到同包 `table_whitelist_tiers.py` |
| `snapshot_writer.py` / `snapshot_writer_modules.py` / `writeback_preview.py` | 759 / 385 / 710 | ≈ 700 / ≈ 200 / ≤ 760 | 前两者只减 |
| 新文件 `source_registry.py` / `paged_fetch.py` / `fetchers/*.py` / `builder_access.py` / `cycle_scope.py` / `export_gate.py` | — | 各 ≤ 800 | — |
| `ReportView.vue`（HARD_CAP 1,949） | 1,949 | ≤ 1,949 | 先把 `routeYear` 移入 `useReportRouteFocus` |
| `ThreeColumnLayout.vue`（白名单 1,515，上限约 1,590） | 1,546 | ≤ 1,565 | 映射与开合逻辑放 `queryEntryContext.ts` |
| `CustomQueryDialog.vue` / `CustomQueryTab.vue` / `AdvancedQueryBuilder.vue` | 1,061 / 1,245 / 900 | 各 ≤ 1,450 | 超出先把操作列 / 分页条抽成 `QueryResultActions.vue`；W3 / W6 在弹窗里净增 ≤ 40 行（逻辑在 `useQueryEntry.ts` 与三个新组件） |
| `TrialBalance.vue`（白名单 4,491，上限约 4,715） | 4,626 | ≤ 4,628 | W6 只加 2 行 |
| `DisclosureEditor.vue`（HARD_CAP 3,281） | 3,265 | ≤ 3,267 | W6 只加 2 行；开工前现跑门禁 |
| `WorkpaperEditor.vue`（默认上限 1,500，不在白名单） | 1,465 | ≤ 1,468 | W6 只加 3 行 |
| `ReportDrilldownDialogs.vue` / `useReportDrilldown.ts` | 173 / 196 | ≤ 200 / ≤ 205 | ReportView 不动 |
| `ledger_sampling_service.py`（白名单 1,044，上限约 1,096） | 1,044 | ≤ 1,060 | 只加 `ledger_line_amount` 并改两处调用 |
| `sampling_enhanced_service.py` / `useC24AnalyticsEngine.ts` | 388 / 470 | ≤ 420 / ≤ 470 | 只抽函数与常量 / 只换 import |
| 新文件 `template_presets.py` / `entry_accounts.py` / `gen_journal_entry_rules_ts.py` | — | ≤ 300 / ≤ 250 / ≤ 150 | — |
| 新文件 `QueryConditionEditor.vue` / `QueryDetailEntry.vue` / `QueryEntryBanner.vue` / `useQueryEntry.ts` | — | ≤ 350 / ≤ 120 / ≤ 150 / ≤ 250 | — |
| `GtC24JournalDetail.vue`（2,049，超默认上限且不在白名单） | 2,049 | 不改 | 改一行即被行数门拦，W16 |

## 10. 测试计划

新增后端测试放 `backend/tests/advanced_query_linkage/`（共享 `conftest.py`：`pg_only` 标记、金标准 SQL 助手、真库回滚事务会话）；命令 `rtk ..\.venv\Scripts\python.exe -m pytest tests/advanced_query_linkage -q -p no:playwright`（cwd `backend`）。

### 10.1 单元 / SQLite
- 注册表：每个源的 columns / hidden / filter_keys / default_sort 键都存在于其表（ORM 列反射）；指标树叶子列 == 注册表显示列。
- paged_fetch 语句：编译为 postgresql 方言后断言 WHERE 含项目、年度、数据集谓词，ORDER BY 末项为唯一键、可空列带 NULLS LAST、非空列不带，用户值不出现在 SQL 文本；同一语句以 sqlite 方言编译不报错。
- 条件：未知字段 / 算子 / 筛选键 / 列 → 400；between、in 空集合语义；prefix / nonempty；like 输入 `50%_` 按字面匹配；`build_portable_filter` 与 `_build_filter` 等价。
- 编排器：`FetchPage(paged=True)` 跳过内存分页且 total 原样；tuple 路径不变；内存源默认按 `_row_index`、用户排序同值保持原序；conditions 进 cache_def（不同条件不同键）；meta 往返无损。
- 模板：adapter 归一（含中文报错）；`visible_templates` 四类可见性与「先过滤后截断」；`config_to_request`；软删后列表不见；更新传 `scope=global` 入库为 public。
- 构建器：准入判定（系统角色 / 项目经理 / 只读成员 / 已删项目成员）；`scope_predicates` 的基表谓词在 WHERE、目标谓词在 ON（编译 SQL 断言）；JOIN 基数不变式；report_config 副本行谓词；`_derive_formula_refs` 对 tb_balance 为 None。
- 导出：`_text_safe_cell` 对字符串 `=1+1`、`+1`、`-1`、`@x` 置文本，数值 -1 不受影响；导出闸：同一用户第 2 个 429、第 5 个全局 429、释放后可再取、`release` 幂等。
- W3：`validate_preset` 对 JSON 每条为空列表；逐类构造坏条目（未知源、不可条件字段、白名单外算子、未登记参数、超 20 条）各得对应原因且被 `load_presets` 跳过并记 ERROR；`starts_with` / `weekday_in` 编译为 postgresql 方言后用户值只在绑定参数里，`weekday_in` 用于文本列 400；`cutoff_window` 与 `run_cutoff_test` 的窗口一致（同一函数），`DEFAULT_CUTOFF_DAYS_*` 等于 `run_cutoff_test` 签名默认值；`build_ledger_query` 的 SQL 文本改前改后一致；生成器 `render(JSON)` 等于磁盘上的 `journalEntryRules.ts`（先例 `test_wp_account_mapping_single_source.py`，不走子进程）；vitest 读预置 JSON，断言每条的算子都在 `QueryConditionEditor.EDITOR_OPS` 内（先例 `noteEditCoverage.ts` 的 JSON 比对）。
- W6：`codes_for_wp_code`（E1 → 1001 / 1002 / 1012，E1-2 → 1001，A1 → 空，未登记子编码取主编码）；`report_row_predicate` 单码编译为转义后的 `LIKE`、区间为 `BETWEEN`；筛选键非法值 400；`buildQueryEntry` 四种对象的落点与切换（vitest，ADR-AQL-20 表逐行一条）、合计行不可用、手动换源清除上下文、下钻压栈与返回。
- 依赖旧内部形态而需改写的测试（任务内逐条写明「旧断言固化了缺陷 / 内部形态」）：`test_advanced_query_hardening_wave012.py` 的 `_query_trial_balance` 替身用例；`test_template_service_pbt.py`、`test_advanced_query_template_service.py`、`test_advanced_query_template_execution.py` 的旧 scope 模型、`_is_template_visible` / `_normalize_scope` 用法与 `TEMPLATE_FORBIDDEN` 断言；`test_query_builder_role_gate_pbt.py`（改为 await 异步依赖）；`test_advanced_query_hardening_properties_scope.py::test_p23_*`（改为断言前端不再持有角色清单且经 access 接口判定）；指标树测试的 `_build_disclosure_tree` 替身签名；`advancedQueryFrontend.spec.ts` 中「今年 − 1」断言；`test_query_builder_formula_ref_grammar_v1.py`（tb_balance 形态断言改为全 None、参数化去掉 tb_balance；双列名用例改到真 PG，用 `address_registry.validate_formula_refs` 断言 `TB('1001','审定数')` 有效、`TB('1001','期末')` 无效）；`test_writeback_preview.py` / `test_writeback_pbt.py` 中「含不可定位条目仍可确认」的断言；`test_advanced_query_scope_budget_tiers.py` 的 report_config 用例保持不变（仍在 unscoped_tables，warning 仍含表名）。

### 10.2 真 PG（`pg_only`，金标准现算，统计排除软删项目）
| 用例 | 金标准 |
|---|---|
| 宜宾临港店科目余额（业务视图与构建器） | `get_active_filter` 行数与 Σ期末 |
| 和平药房序时账 total / 借方降序首行 / 第 N 页与相邻页不重叠 | `COUNT(*)` / `MAX(debit_amount)` / 独立 SQL 分页 |
| 和平药房科目 1002 分组 | 行数 > 5,000 ⇒ 400；改用构建器 SQL 分组 = 独立 `SUM` |
| 序时账「借方 > 100,000,000」 | 独立 `COUNT(*) WHERE debit_amount > 1e8` |
| `active_rows_predicate` 与 `get_active_filter` | 每个活项目年度两者行集合相等 |
| 构建器 LEFT JOIN 无匹配行 | 回滚事务里给【UAT】子公司A 插一行没有对应标准科目的试算行：`trial_balance LEFT JOIN account_chart` 行数 = 基表行数，该行目标列为空 |
| 全部登记 JOIN | 多对一登记在活项目上 LEFT JOIN 后行数 = 基表行数；一对多登记产生 warning |
| e2e_manager 构建器 projects / trial_balance | = OwnershipGuard 可访问集合 ∩ 未删项目 |
| 报表源结构 | 回滚事务里给华氏插一条覆盖行与一条本项目独有行：每个活项目的 (report_type, row_code) 集合 == `load_effective_report_configs` 的集合；独有行出现、金额为空；报表行次源只含准则行与本项目副本 |
| 华氏 BS-002 / AJE / 「八、1」/ 报表行次 | financial_report 值 / adjustments 行数 / 第一张表的行数与行序（与 `table_data` 一致，合计行在最后）/ report_config 行数 |
| 辅助余额 / 辅助明细 | 带 aux_type / 科目筛选的独立 COUNT；辅助明细不带筛选 400 |
| 循环范围（分支须含 d0de87a6c） | 回滚事务里建临时用户（系统 manager）与其人员记录，在华氏建成员行（`scope_cycles` 为空）与委派（角色 auditor、`assigned_cycles=['D']`）：金标准 = `deps.get_user_scope_cycles` 的返回值（应为 `['D']`）；试算表源 = `get_codes_by_cycles(该返回值)` 内科目；调整分录按分录组；附注树与附注目录只含 `get_sections_by_cycles` 章节，范围外章节 403；该用户构建器作用域不含华氏。同一用户委派角色改为 manager ⇒ 返回 None、三源不限；勾选改为空 ⇒ 三源都无行 |
| 预置执行对账（只读） | 每条预置经 resolve + execute（TestClient、真实依赖链，项目分配见 R13.7）：total = 独立 SQL `COUNT`；第一页逐值 = 独立 SQL 同排序 `LIMIT`；结果 ≤ 5,000 行的逐页取全量后 Σ借 / Σ贷 = 独立 `SUM` |
| 预置参数 | 回滚事务给【UAT】子公司A 插重要性记录：正数 ⇒ 阈值 = 该数；负数 ⇒ 留空 + 负数原因；无记录 ⇒ 留空 + 未设置原因；华氏（真实负数）只读验证负数原因；`audit_period_end` 为空时截止窗口 = 年度 12-31 前后各 5 天 |
| 新条件能力 | 和平药房：周末 total = 独立 `EXTRACT(DOW FROM voucher_date) IN (0, 6)` 计数；`account_code` 开头是 1002 = `LIKE '1002%'` 计数；华氏 `line_amount` 大于等于 1,000,000 = 独立 `GREATEST(COALESCE(借,0), COALESCE(贷,0)) >= 1000000` 计数；空阈值 400 |
| 报表行构成科目（W6） | 华氏每个「公式只含 TB / SUM_TB 相加、列为 期末余额 / 审定数」的报表行：`report_row` 结果 Σ审定 = 该行 `current_period_amount`；回滚事务给【UAT】子公司A 造试算表 1002 与 100201 两行及 `source_accounts=['1002']` 的报表行 ⇒ 结果两行都在；未生成 / 合计行 400 |
| 附注章节与底稿（W6） | 华氏「八、1」相关科目 = {1001, 1002, 1012} ∩ 本项目试算表；没有映射的章节 400；范围外章节 403（循环范围夹具）；和平药房 `wp_code=E1` total = 三个前缀的独立计数；`account_code=1002` total = 前缀计数 = 经 account_mapping 计数；`wp_code=A1` 400 |
| 构建器 formula_refs | 华氏每条非空 ref 经 `validate_formula_refs` 有效 |
| 回写不锁他项目行 | 目标：活项目中 updated_at 最早的一张已提交底稿、【UAT】合成集团母公司的一条 consol_note_data；会话 A 以【UAT】子公司A 直调 `snapshot_writer.write_cell` / `write_note_cell`，分别得 `WritebackTargetNotFound` / `NoteRecordNotFound`（A 事务未结束）；会话 B 对目标行 `SELECT … FOR UPDATE NOWAIT` 成功；两会话回滚，目标行前后指纹一致 |
| 回写预览门 | 同一底稿目标经 writeback-preview：条目 `target_not_in_project`、`enter_confirmation=false`；writeback-confirm 409，写入方未被调用 |
| 查询路径只读 | 预览与区域取数前后 storage 文件 sha256 与 mtime 不变 |
| 导出 | 和平药房序时账按月导出行数 = COUNT（openpyxl 读回）、超限 400 且不产生文件、中文表头、「查询说明」sheet；回滚事务造一行摘要为 `=1+1` 的序时账（经 TestClient、`get_db` 指向该会话）导出后读回 `data_type == "s"` |
| 迁移 | `run_pending` 后列、索引、约束存在；R 文件可回放 |

### 10.3 端点权限配方表（`test_aql_endpoint_authz.py`，基于 `tests/authz_world.py`，TestClient 走真实依赖链，只 override `get_current_user` / `get_db`）
身份都用 authz_world 工厂建在同一世界（X = `TARGET_PROJECT_ID`，Y = `OTHER_PROJECT_ID`）：匿名 = `user=None`；A = `world.user(auditor)`（无成员行）；R = `readonly_member()`；E = `member("edit", "auditor")`；PM = `edit_member()`（manager, edit，系统 auditor）；SM = `non_member_with_other_project(global_role=manager)`（系统 manager，只在 Y 有成员行）；P = `world.user(partner)`；AD = `admin_non_member()`。模板：T = AD 公开；S = PM 共享给 X；Q = AD 私有。底座：S = `sqlite_world`（纯门禁格）；P = `pg_world`（依赖文本 SQL 定位或断言结果内容的格——SQLite 存 32 位十六进制 UUID，文本 SQL 绑定 `str(uuid)` 永远匹配不上，会假绿）；所需业务表经 `extra_tables` 补齐，缺表即该格失败、不降级跳过。回写两类请求一律带 `X-File-Opened-At`（缺头即 400，会掩盖门禁结论）。

| # | 端点 | 底座 | 匿名 | A | R | E | PM | SM | P | AD |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | GET /api/custom-query/indicators?project_id=X&depth=1 | S | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 2 | GET /api/custom-query/wp-id-by-code（X 的底稿） | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 3 | GET /api/custom-query/wp-sheet-preview（X 的底稿、无文件；200 时 available=false） | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 4 | POST /api/custom-query/execute（X，试算表） | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 5 | POST /api/custom-query/export（X，试算表） | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 6 | GET /api/custom-query/templates：含 T / S / Q | P | 401 | 是/否/否 | 是/是/否 | 是/是/否 | 是/是/否 | 是/否/否 | 是/是/否 | 是/是/是 |
| 7 | POST /api/custom-query/templates（scope=private） | S | 401 | 201 | 201 | 201 | 201 | 201 | 201 | 201 |
| 8 | POST /api/custom-query/templates（scope=project，共享 X） | S | 401 | 403 | 403 | 201 | 201 | 403 | 403 | 201 |
| 9 | GET /api/custom-query/templates/{S} | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 10 | GET /api/custom-query/templates/{Q} | P | 401 | 403 | 403 | 403 | 403 | 403 | 403 | 200 |
| 11 | PUT /api/custom-query/templates/{S} | P | 401 | 403 | 403 | 403 | 200 | 403 | 403 | 403 |
| 12 | DELETE /api/custom-query/templates/{S} | P | 401 | 403 | 403 | 403 | 204 | 403 | 403 | 403 |
| 13 | POST /api/custom-query/templates/{S}/execute（X） | P | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |
| 14 | GET /api/recycle-bin?item_type=custom_query_template：含已删的 S | P | 401 | 否 | 否 | 否 | 是 | 否 | 否 | 是 |
| 15 | POST /api/recycle-bin/custom_query_template/{S}/restore | P | 401 | 403 | 403 | 403 | 200 | 403 | 403 | 200 |
| 16 | DELETE /api/recycle-bin/custom_query_template/{S} | P | 401 | 403 | 403 | 403 | 200 | 403 | 403 | 200 |
| 17 | POST /api/custom-query/cell-writeback（module=tb） | S | 401 | 422 | 422 | 422 | 422 | 422 | 422 | 422 |
| 18 | POST /api/custom-query/cell-writeback（workpaper，body X，wp_code 只在 Y） | P | 401 | 403 | 403 | 404 | 404 | 403 | 404 | 404 |
| 19 | POST /api/custom-query/writeback-preview（body X，target.wp_id 属 Y） | P | 401 | 403 | 403 | 200† | 200† | 403 | 200† | 200† |
| 20 | POST /api/custom-query/writeback-confirm（同 19） | P | 401 | 403 | 403 | 409 | 409 | 403 | 409 | 409 |
| 21 | GET /api/custom-query/index-health | S | 401 | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| 22 | GET /api/custom-query/address-resolve?uri=workpaper:A1 | S | 401 | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| 23 | GET /api/query/access：allowed / all_projects | S | 401 | 否/否 | 否/否 | 否/否 | 是/否 | 是/否 | 是/是 | 是/是 |
| 24 | GET /api/query/schema、POST /api/query/preview（trial_balance） | S | 401 | 403 | 403 | 403 | 200 | 200 | 200 | 200 |
| 25 | POST /api/query/execute、POST /api/query/export-excel（trial_balance） | P | 401 | 403 | 403 | 403 | 200 仅 X | 200 仅 Y | 200 | 200 |
| 26 | POST /api/query/execute（projects） | P | 401 | 403 | 403 | 403 | 仅 X | 仅 Y | 全部未删 | 全部未删 |
| 27 | POST /api/query/execute（staff_members） | S | 401 | 403 | 403 | 403 | 403 | 403 | 200 | 200 |
| 28 | POST /api/query/execute（project_id=Y） | P | 401 | 403 | 403 | 403 | 403 | 200 | 200 | 200 |
| 29 | POST /api/custom-query/batch-execute、GET /api/custom-query/cross-sheet-trace（已删） | S | 404 | 404 | 404 | 404 | 404 | 404 | 404 | 404 |
| 30 | GET /api/custom-query/template-presets（W3） | S | 401 | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| 31 | GET /api/custom-query/template-presets/je_large_amount/resolve?project_id=X&year=2025（W3） | S | 401 | 403 | 200 | 200 | 200 | 403 | 200 | 200 |

† 200 且 `enter_confirmation=false`、条目 `error=target_not_in_project`。定级依据：只读类跟 execute 行（OwnershipGuard 成员即可）；分享到项目按该项目 edit 级（`require_project_access("edit")`，合伙人非成员同样 403）；改删仅作者（admin 亦不例外）；构建器各端点跟 access 判定；index-health、address-resolve 只校验登录。先建表、以 `xfail(strict=True)` 钉住尚未修复的格，各任务修完即删对应 xfail；全部转正后做路由对账：custom_query、custom_query_writeback、query_builder 三个 router 的每条路由（含新增 export / access 与 W3 的两条 template-presets）都在表里出现，已删路由只出现在第 29 行；第 31 行显式带 `year`（缺省年度走的 `PROJECT_AUDIT_YEAR_SQL` 是 PG 专用写法）。

### 10.4 磁盘变异（单独一条命令跑，变异备份放 `tmp_aql_linkage/mut/`，逐字节恢复后 sha256 核对）
| # | 变异 | 期望打红 |
|---|---|---|
| 1 | 业务视图科目余额改回只写 `is_deleted = false` | 宜宾临港店 PG 用例 |
| 2 | 构建器去掉数据集谓词 | 构建器宜宾计数用例 |
| 3 | `paged_fetch` 以本页行数代替 COUNT | 和平药房 total 用例 |
| 4 | 排序退回内存 | 借方降序首行用例 |
| 5 | projects 作用域去掉 | SM / PM 项目数用例 |
| 6 | account_chart JOIN 去掉 source 条件 | 基数守卫 |
| 7 | 调整分录枚举改回大写 | AJE PG 用例 |
| 8 | 报表金额改回 report_snapshot | BS-002 用例 |
| 9 | `snapshot_writer_modules` 恢复 `publish_rows` 调用 | AST 棘轮 |
| 10 | `workpaper_cells` 恢复 `init_workpaper_from_template` | 只读守卫 |
| 10b | 重算结果 `shutil.copy` 回原文件 | 只读守卫（写调用不在 `_temp_copy`）+ sha256 用例 |
| 11 | 底稿写入取行去掉项目条件 | NOWAIT 加锁用例 |
| 12 | 模板可见性改回只认 global | 审计员看公开模板用例 |
| 13 | 准入去掉项目经理分支 | PM 准入用例 |
| 14 | 未知条件字段改为静默忽略 | 400 用例 |
| 15 | `queryResultLinks` 底稿格改回 `?highlight=` | vitest 下钻用例 |
| 16 | JOIN 目标表作用域谓词移回 WHERE | LEFT JOIN 无匹配行用例 |
| 17 | 内存源默认排序去掉 `_row_index` | 「八、1」行序用例 |
| 18 | 导出去掉文本强制 | 读回 `data_type` 用例 |
| 19 | 试算表源去掉循环过滤 | 循环范围 PG 用例 |
| 20 | 报表源去掉本项目独有行 | 报表源集合等价用例 |
| 21 | 预览去掉 `target_not_in_project` 判定 | 预览门 PG 用例与配方表第 19、20 行 |
| 19b | `cycle_scope` 改为自读 `project_users.scope_cycles`（绕开平台入口） | 循环范围 PG 用例（团队分配勾选 D、成员行为空的成员只见 D） |
| 22 | `starts_with` 不转义，或改成「包含」 | `50%_` 字面匹配用例 / 开头是 1002 计数用例 |
| 23 | 星期映射错位（0 当周一）或改为拼接 SQL 文本 | 周末计数 PG 用例 / 绑定参数断言 |
| 24 | 重要性缺失时代入 1,000,000 | 预置参数用例（留空 + 原因） |
| 25 | C24 引擎改回内联词表并删掉一个词 | 生成文件渲染比对用例 + C24 特殊事件 vitest |
| 26 | `report_row` 单码改精确匹配 | 子科目夹具用例 |
| 27 | 附注章节改按章节号匹配 `note_account_mappings` | 「八、1」相关科目用例 |
| 28 | `buildQueryEntry` 试算表行落点改为科目余额 | vitest 落点用例 |
| 29 | `paged_fetch` 去掉 `CONDITION_VALUE_REQUIRED` | 空阈值 400 用例 |

### 10.5 浏览器实测（写后读回；需 start-dev 环境）
复测评估 B1–B14 场景，并逐类验证：每类结果「打开」落点与定位（报表行分普通、对比、矩阵三种）；「复制引用」：试算表 / 报表 / 附注各一条粘到公式编辑器校验通过，底稿格选一个已登记坐标（D 循环种子坐标）可复制、一个未登记单元格按钮不可用并显示原因；和平药房序时账翻到第 100 页、借方降序、打开凭证；按月导出文件行数 = COUNT（openpyxl 读回）；页面版「借方 > 1 亿」与字段选择；模板三档保存 → 审计员账号可见公开模板 → 弹窗执行 → 删除 → 回收站恢复 → 列表读回；PM 身份构建器默认当前项目、projects 只见可访问项目、JOIN 行数不变、翻页 total；右键跳模板溯源到底稿模板页签；从试算表页切到另一项目再开弹窗，项目随路由；错误态显示中文与追踪号。W3：页面版与弹窗各载入一次全部 7 条预置（和平药房）——条件填进编辑器、未自动执行；大额预置显示「未设置重要性水平」提示且查询按钮不可用，填 1,000,000 后可查；周末预置显示节假日说明；「另存为我的模板」改名为【测试】开头后保存，出现在「我的模板」，再删除并从回收站彻底删除。W6：试算表 1002 右键 → 序时账并切到辅助余额；报表货币资金「查看穿透」→ 构成科目 → 「查明细」→ 返回；附注「八、1」右键 → 附注表格 → 相关科目；底稿 E1 工具栏 → 序时账；在 A1 底稿上点入口显示「该底稿没有登记对应科目」；关键点击前校验 `location.pathname`。写入只用名称带【测试】的模板，结束后走删除 → 回收站彻底删除并核对表内无残留。改带自动保存页面的源码前浏览器先停 about:blank。

## 11. 待拍板（推荐默认值；本 spec 均不做）

| # | 事项 | 推荐默认 |
|---|---|---|
| W1 | 查询结果真回写到底稿格 / 附注（底稿改走 workpaper_sync 内容写入、附注走附注编辑门禁与合并锁） | 不做，以「引用 + 下钻」交付 |
| W2 | cell-writeback / writeback-preview / writeback-confirm 是否整体下线 | 保留现状（已收窄并隔离），下一轮随 workpaper_sync 写入者清单评估 |
| W4 | ACNR 选中格成为结果列（跨底稿单元格取数） | 不做，控件「开发中」 |
| W5 | 弹窗指标树懒加载（advanced-query-hardening-wiring-closure R12 前端部分） | 不做（缓存按附注版本失效已覆盖重复打开） |
| W7 | 多底稿批量取数（advanced-query-enhancements-p1p2 R1）重做 | 不做（端点与工具条删除） |
| W8 | 构建器纳入合并表 | 不做（0 个合并项目无法验收） |
| W9 | 业务视图分组 / 透视界面 | 不做（ADR-AQL-07） |
| W10 | team 范围彻底下线（含历史数据迁移） | 保留读写兼容，前端不出现 |
| W11 | 导出超过 100 万行改为截断并在文件内写明 | 不改，按 R8.2 拒绝并提示缩小范围 |
| W12 | 序时账 / 辅助明细复合索引迁移（仅在 N1 预案①②后仍不达标时提出） | 须用户批准后执行（共享库建索引长时间锁写） |
| W13 | 恢复「报表行次映射 → 报表配置」JOIN（按项目准则关联） | 不做，行名已在映射表上 |
| W14 | 底稿单元格对未登记坐标也提供引用（需先把选区坐标批量登记进地址目录） | 不做，只对已登记坐标开放 |
| W15 | 节假日凭证（需平台节假日日历：逐年维护的节假日与调休表） | 不做，W3 只做周末；若要做，先定日历的维护人与年度更新流程 |
| W16 | C24「含模糊词」默认词表并入共享定义，并增加「摘要含模糊词」预置 | 随 `GtC24JournalDetail.vue` 瘦身（2,049 行，先拆到 1,500 以内或登记白名单）一起做 |

W3（常用审计预置模板）、W6（业务页行级「按此查询明细」）已按用户 2026-10-26 决定纳入本 spec，裁决见 ADR-AQL-05 / ADR-AQL-20，编号不复用。

## 12. 实施纪律
- 每个任务开工前对本任务涉及的文件重跑现状确认（grep / 行数 / 调用方），结论写入任务勾选说明；评估数值只作参考。
- 临时产物（探针、截图、变异备份、验证 worktree）一律放仓库根 `tmp_aql_linkage/`；验证 worktree 用 `git worktree lock`，用完 unlock + 删目录 + prune，不留 node_modules 联接。
- 共享文件（`.kiro/specs/INDEX.md`、`backend/scripts/file_size_whitelist.txt`、`auditYearCalendarFallbackBaseline.json`、`tests/authz_world.py`、权限基线测试）只提交本 spec 改动块，提交前 `git diff --cached -- <路径>` 核对；底层 git 操作放子进程并显式传环境变量，不在共享终端设 `GIT_INDEX_FILE`；不 stash、不 `--no-verify`。
- 删除类提交按 §3.9 一类一提交，提交前打 tag 备份；新模块与调用方同一次提交；提交前在干净 worktree 跑「将要提交的那棵树」。
- 写入型验收只用【测试】/【UAT】项目、回滚事务与【测试】模板；共享开发环境不重启 start-dev。
- 收尾写 `closure.md`：逐条回显 §2 全部裁决（ADR-AQL-01~20）与 §11 待拍板（W1、W2、W4、W5、W7~W16，W3 / W6 标「已纳入」），并写明只做周末、不做节假日的原因（§14.1），供用户复核。

## 13. 评审意见回应（第 1 轮评审：`design-review.md`，HIGH 2 / MEDIUM 16 / NIT 17）

| # | 级别 | 处置 | 落点 |
|---|---|---|---|
| 1 | HIGH | 采纳：只为弹窗加 `customQueryYear`，`currentYear` 不动；ThreeColumnLayout 基线保留、只删三条 | ADR-AQL-15、§4.2、R10.2、tasks 31 |
| 2 | HIGH | 采纳：基表谓词在 WHERE、JOIN 目标谓词并入 ON；LEFT JOIN 无匹配守卫 + 变异 #16 | ADR-AQL-09、§3.4、§7、tasks 9 |
| 3 | MEDIUM | 采纳并扩展：构建器限项目副本行；报表源与 `load_effective_report_configs` 同口径（准则改用 `resolve_applicable_standard`）；同类问题的报表行次源一并修 | §3.1、§3.4、tasks 9 / 17 |
| 4 | MEDIUM | 采纳：12 条逐条裁基数与处置；RLM → report_config 删除登记（W13） | ADR-AQL-09、tasks 10 |
| 5 | MEDIUM | 采纳：保留 `_NOTE_COLUMNS`；删前后跑惰性导入守卫 | ADR-AQL-13、§3.9、tasks 34 |
| 6 | MEDIUM | 采纳（前移）：batch-execute 族单列 tasks 6，在取数器下沉之前单独提交 | §3.9、tasks 6 |
| 7 | MEDIUM | 采纳：跨项目目标在预览标 `target_not_in_project` ⇒ 确认 409；表头注明请求头；直测写入方 404 + NOWAIT | §3.7、§10.2、§10.3、tasks 14 |
| 8 | MEDIUM | 采纳：配方表覆盖三个 router 全部路由；基于 authz_world（新增 `extra_tables`，缺省仍六张表）；逐行标底座 | §10.3、tasks 1 / 2 |
| 9 | MEDIUM | 采纳：get / execute 映射 403 `TEMPLATE_NOT_VISIBLE`、错误码统一；adapter 报错中文；删除原值覆盖 | §3.6、tasks 24 |
| 10 | MEDIUM | 采纳：内存源隐藏列 `_row_index` 作默认排序与 tie-breaker | §3.2、§3.3、tasks 5 / 19 |
| 11 | MEDIUM | 采纳：统一 `?tab=&highlight=`；普通、对比、矩阵三种情况分别处理 | ADR-AQL-01、§4.1、tasks 32 |
| 12 | MEDIUM | 采纳：写盘只在 `_temp_copy`；守卫三条 + 变异 #10b | §3.7、tasks 16 |
| 13 | MEDIUM | 采纳：底稿格只对已登记坐标开放；整页批量校验；验收选已登记坐标 + 未登记反例 | ADR-AQL-18、§10.5、tasks 27 |
| 14 | MEDIUM | 采纳方案 (a)，并补构建器排除循环受限项目 | ADR-AQL-19、§3.10、tasks 23 |
| 15 | MEDIUM | 采纳并调整：辅助明细强制筛选；非空列不加 NULLS LAST；索引迁移须用户拍板（W12），不达标任务不勾 | ADR-AQL-06、tasks 36 |
| 16 | MEDIUM | 采纳：语法测试改写，双列名用例改真 PG 判有效 / 无效 | §10.1、tasks 11 |
| 17 | MEDIUM | 采纳：缓存键加年度与附注版本（版本含循环范围）；两处共用缓存模块 | ADR-AQL-16、§3.8、§4.1、tasks 27 |
| 18 | MEDIUM | 采纳：文本强制 + 每人 1 / 每进程 4 的导出闸 | ADR-AQL-14、§3.5、tasks 26 |
| 19 | NIT | 采纳（换写法）：先查生效数据集再按 id 过滤，不用 DISTINCT ON，也不用逐行相关子查询 | §3.4 |
| 20 | NIT | 采纳：补 7 → 16、27 → 31、27 → 33 依赖；入口上下文抽纯函数 + vitest | tasks 依赖行、31 |
| 21 | NIT | 采纳：`useBatchQuery.ts` 一并删；写作 `customQuery.batchExecute` | ADR-AQL-13、tasks 6 |
| 22 | NIT | 采纳：删用例后下调 `test_snapshot_writer.py` 基线 | §3.9、tasks 13 |
| 23 | NIT | 采纳：附注 404（403 只用于同项目内不一致）；已删路由 404 | R4.2、§10.3 |
| 24 | NIT | 采纳：prefix / nonempty 进 `build_portable_filter`，like 转义 | ADR-AQL-03 |
| 25 | NIT | 采纳：先按可见性过滤，再取前 500 | §3.6 |
| 26 | NIT | 采纳：经 `meta.ref_context` 下发 template_type 与年度 | §3.1、ADR-AQL-18 |
| 27 | NIT | 采纳：复用 `DisclosureEngine.get_notes_tree`，写明分组与缺省组名 | ADR-AQL-16、§3.8 |
| 28 | NIT | 采纳：tasks 36 只做静态核对，运行归 37* | tasks 36 |
| 29 | NIT | 采纳：补理由（el-select 平铺不可用，sheet 级查询走弹窗选区器） | ADR-AQL-16 |
| 30 | NIT | 不改，登记范围外：该处传的是分录溯源键 `source_ref` 而非单元格，改成 `?cell=` 反而错 | requirements §3 |
| 31 | NIT | 采纳：ORM 用 `SoftDeleteMixin` | §3.6、§8 |
| 32 | NIT | 采纳：按纯关键字签名 `accessible_project_ids` 书写 | §3.6 |
| 33 | NIT | 采纳：通用调整分录源不带类型返回全部类型（含 cf）并带类型列 | §3.1、R5.2 |
| 34 | NIT | 采纳：本地文字筛选标注「仅筛选本页」 | §4.2、R2.6 |
| 35 | NIT | 采纳：admin / partner 返回 `all_projects: true`、计数为 null | ADR-AQL-08、§3.4 |

## 14. W3 / W6 纳入说明（用户 2026-10-26 决定；只读源码与只读查库核实，HEAD bb7aff842）

只读查库每条查询独立只读事务，探针在 `tmp_aql_linkage/probe/w36_*.py` / `w6_*.py` / `w3_*.py`（收尾删除，结论以本节为准）。数值是 2026-10-26 快照，测试一律现算。

### 14.1 W3：现成筛选规则与数据
- C24：`composables/useC24AnalyticsEngine.ts`（470 行）`screenAnomalies` 有 13 条规则，其中可用 SQL 条件表达的是大额（`Math.max(debit, credit) > largeAmountThreshold`）、特殊事件（函数内局部常量 8 个词）、含模糊词（`rules.vagueKeywords`）、无摘要；参数默认值写在 `GtC24JournalDetail.vue` 的 `ruleParams`（`largeAmountThreshold: 1000000`、`vagueKeywordsText: '调整,暂估,其他,冲销'`）；假期清单逐底稿手填（`C24HolidaySheet.vue`，存 `checklist_responses.item_id = 'C24-holidays'`）；分录由前端整库拉取序时账（`loadFromLedger` → `useLedgerCache`）后在浏览器里筛，后端没有 C24 规则（`backend/app` 搜 `c24|journal_entry|anomal` 0 处）。归档 spec `_archive/05-business-features/c23-c24-journal-entry-testing` 的 `AnomalyRules` 即此。
- 抽凭 / 截止：`ledger_sampling_service.LedgerQueryFilters` + `LedgerSamplingService.build_ledger_query`（日期、科目前缀列表、`GREATEST(COALESCE(借,0), COALESCE(贷,0)) >= 阈值`、离散月份 `extract('month').in_`、摘要关键词转义 `ilike`）；`sampling_enhanced_service.CutoffTestService.run_cutoff_test`（期末日 = 显式截止日，否则 `date(year, 12, 31)`；默认前后各 5 天；界面请求 `CutoffExtractRequest` 另有 5 / 10 的默认）。
- 重要性：`audit_platform_models.Materiality`（项目 + 年度唯一，三档 NOT NULL）与 `MaterialityService.get_current(project_id, year)`。
- 节假日：后端代码与 `backend/data` 没有节假日日历（搜 `holiday|节假日|法定假日` 只命中模板文字）；`wp_templates/C/C24 会计分录 - 细节测试.xlsx` 的「2025假期清单」sheet 有 33 行，全是 2025 年（法定假日 28、调休上班 5），没有任何代码读取；库内 `C24-holidays` 0 行 ⇒ 没有可用来源，只做周末（W15）。
- 只读查库：`custom_query_templates` 0 行；重要性记录只有 2 条——华氏 2025 实际执行的重要性 −507,095,295.59、辽宁 2025 为 −2,616,403.90（三档都是负数），和平药房没有记录；和平药房 2025 序时账 1,147,414 行，日期 2025-01-01 ~ 2025-10-31。
- 金标准快照（和平药房，生效数据集）：周末 156,462 行（周日 95,515 + 周六 60,947）；摘要含冲销 / 红字 / 冲红 / 冲回 5,064 行（分别 3,118 / 6 / 10 / 1,935）；负数金额 36,597 行（借负 22,726、贷负 13,871）；特殊事件 44 行；科目 1002 开头 116,443 行、Σ借 3,245,484,243.16。宜宾临港店 2025-12-26 ~ 2026-01-05 窗口 326 行（华氏、和平药房 0 行）。华氏借、贷较大者 ≥ 1,000,000 有 3,157 行。

### 14.2 W6：各页现有穿透与科目口径
- 试算表：`TrialBalance.vue`（4,626 行）右键菜单有「📊 查看明细」（`onTbCtxDrillDown` → `onUnadjustedClick` → `/ledger?year=&account=<标准码>`，账簿页 `_scrollToAccount` 按精确或前缀定位）、「查看调整分录」等；双击金额走 `usePenetrate.toLedger`（见 §14.5）。
- 报表：`ReportView.vue`（1,949 = HARD_CAP）的穿透在 `views/composables/useReportDrilldown.ts`：`onDrilldown` → `GET /api/reports/{pid}/{year}/{type}/drilldown/{row}`（`ReportEngine.drilldown`，按 `financial_report.source_accounts`）；`onLineComposition` → `line-composition`（按 `report_line_mapping`）；弹窗在 `components/report/ReportDrilldownDialogs.vue`（173 行）。报表取数：`ReportFormulaParser._get_tb_rows_prefix`（`LIKE 'code%'`）、`_resolve_sum_tb`（起止区间）。华氏 BS-002：`source_accounts = ["1001", "1002", "1012"]`，公式三个 `TB(…,'期末余额')` 相加，本期 822,999,085.83 = 前缀匹配的 3 行试算表审定数之和；华氏 60 个报表行的 `source_accounts` 是数组，其中 57 行公式只含相加的 TB / SUM_TB。
- 附注：`DisclosureEditor.vue`（3,265 / HARD_CAP 3,281）右键菜单有「查看相关底稿」「📊 穿透到序时账」（`useNoteCellActions.onDeCtxPenetrateToLedger`）等。附注 → 科目没有现成的完整解析：`note_related_workpapers.py` 注明「完整实现需 note_account_mapping 表」，模板 JSON 只有 `account_name`，`table_data._bindings` 全库 0 行，`wp_account_mapping.json` 的 `note_section` 只有上市版「五、x」（37 个）。可用的是 `note_account_mappings`（ORM `NoteAccountMapping`，280 行，soe_standalone / listed_standalone 各 140，`note_section_code` 存章节名称，`linkage_graph_builder` 已按此使用）：按标题匹配华氏 186 个章节中的 77 个、和平药房 166 个中的 73 个（如「八、1 货币资金」→ E1、E1-1、E1-2、E1-3）。三个真实项目都是国企单体。
- 底稿：`WorkpaperEditor.vue`（1,465 / 默认上限 1,500）两个工具栏都没有科目入口；`wp_account_mapping.json` 1,025 个编码各一条，619 条有科目（D~N），A / B / C / S 为空，子编码有自己的条目（E1-2 → 1001）。
- 科目口径：和平药房、华氏、宜宾临港店的 `account_mapping` 客户科目全部以所映射的标准码开头（402 / 402、812 / 812、812 / 812），序时账科目 100% 有精确映射（270 / 193 / 88），和平药房试算表标准码都是 4 位（53 行）；和平药房 1002 前缀计数 = 经映射计数 = 116,443，E1 三前缀 116,562 ⇒ 序时账按标准码前缀与按科目映射在三个项目上结果相同，采用账簿页现有的前缀口径。
- 并发与行数：2026-10-26 现查 `git status`，W3 / W6 要改的文件（TrialBalance、ReportView 及其 composable、DisclosureEditor、WorkpaperEditor、ThreeColumnLayout、CustomQueryDialog、CustomQueryTab、MyTemplatesDialog、CellContextMenu、`components/report/`、useC24AnalyticsEngine、eventBus、`services/custom_query/`、`routers/custom_query.py`、两个抽凭服务、重要性服务、`backend/data/`）都没有他人未提交改动；并发 spec `formula-hub-integrity-closure` 的三件套不涉及这些文件（它改 `components/formula/**`、FormulaManagerDialog、GtRefreshScopeDialog 等）；工作树里 `auto-imports.d.ts`、`components.d.ts` 有他人改动 ⇒ 新组件显式 import，这两个文件不提交。每个 W 任务开工前重查。

### 14.3 裁决
- W3 做（ADR-AQL-05）：7 条预置，JSON 定义合入列表，不建系统用户、不加迁移；载入到条件编辑器、不自动执行；阈值 = 实际执行的重要性，缺失留空；复用 C24 特殊事件词表、抽凭的大额表达式、截止测试的窗口函数；最小新能力 4 项；只做周末（W15），「模糊词」预置随 C24 瘦身做（W16）。
- W6 做（ADR-AQL-20）：四处入口与现有穿透并列；映射只在 `queryEntryContext.ts`，科目解析只在 `entry_accounts.py`；页面净增 TrialBalance 2 / DisclosureEditor 2 / WorkpaperEditor 3 / ReportView 0 行。

### 14.4 ADR-AQL-19 口径对齐与分支前置
- 平台可见性规则 `effective_scope`（主管看全部循环、审计员按团队分配）在远端 `origin/spec/disclosure-note-doc-upload-and-batch-fill` 的提交 d0de87a6c（2026-10-26 13:10）：新增 `services/wp_visibility/effective_scope.py`，`deps.get_user_scope_cycles` 改调 `resolve_member_scope`，附注目录树与就绪度改为空范围即空，调整分录取科目失败不再放行。本地 HEAD 的 `get_user_scope_cycles` 仍只读 `project_users.scope_cycles` 且为空即不限；`git merge-base --is-ancestor d0de87a6c HEAD` 为否，`git rev-list --left-right --count HEAD...origin/spec/disclosure-note-doc-upload-and-batch-fill` = 9 / 10（分叉）。
- 第 2 轮设计里「构建器排除本人成员行设有循环范围的项目」「附注页映射为空集时不过滤」是旧口径，本轮改为只调平台入口（ADR-AQL-19、§3.4、§3.10、R3.8、§10.2 循环范围行、任务 23），不复制 `effective_scope` 的逻辑，不改平台权限语义。
- 任务 23 开工前分支须包含 d0de87a6c；合并分叉按简报规则由用户决定（推送时同样会遇到）。

### 14.5 顺带发现（归各自模块，登记不改）
1. `composables/usePenetrate.ts` 的 `toLedger` 推 `/ledger?code=&year=`，账簿页只读 `account` / `level`（`useLedgerUrlSync.readFromUrl` 与 `LedgerPenetration` 的 onMounted）⇒ 试算表双击金额、错报金额、辅助汇总、附注右键「穿透到序时账」四处都停在余额表、不定位科目。归账簿穿透。
2. `ReportEngine.drilldown` 单码按 `standard_account_code == code`，报表取数按前缀；试算表有子科目时「查看穿透」列出的科目少于金额实际构成。归报表。
3. 华氏、辽宁的重要性水平三档都存为负数。归重要性水平。
4. `mapping_service.get_sections_by_cycles` 只返回上市版章节号，国企项目受限成员的附注目录为空（附注页与高级查询同口径）。归平台鉴权 / 附注循环映射。
5. `line-composition` 端点不传年度时取 `tb_balance` 最大年度，报表页调用时没有传年度。归报表。
6. 「大额」在平台已有两处实现：C24 前端对导入分录 `Math.max(借, 贷) > 阈值`，抽凭 / 截止测试后端 `GREATEST(…) >= 阈值`，只在等于阈值时结论不同；W3 预置复用后端那一处（抽成 `ledger_line_amount`），不新增第三处；两处是否统一归 C24 / 抽凭。
