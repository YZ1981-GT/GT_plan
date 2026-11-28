# 三、梳理中发现的问题

> 每条都对着代码核过，给出位置，便于复核和下午解释。代码位置省略前缀 `backend/app/`。
> 「影响」写的是对业务数据或可解释性的影响；「建议」只是方向，没有动代码。

## 一、可能导致数据不对，或规则永远不执行

### F1 10 个事件有人订阅、全后端没人发，对应的处理函数永远不会执行

按 `EventType.X` 和事件字符串值两种写法，在后端、前端、脚本里都查过，没有发布方：

| 事件 | 订阅它的处理 | 实际影响 |
|---|---|---|
| `MATERIALITY_CHANGED` | `services/a13_event_handler.py::_on_materiality_changed`；`services/event_handlers/_impl.py::_invalidate_procedure_table_cache` | 改重要性水平后，A13 错报汇总和程序表缓存不会自动刷新 |
| `WORKPAPER_REVIEW_PASSED` | `_impl.py::_on_workpaper_review_passed`；`_impl.py::on_event_workpaper_reviewed`（标附注过期并后台重算） | 底稿复核通过不会触发附注过期 |
| `PREFILL_MAPPING_CHANGED` | `_impl.py::_stale_engine_on_prefill_mapping_changed` | 改预填映射后相关底稿不标过期 |
| `REPORT_CONFIG_MASTER_UPDATED` | `_impl.py::_mark_cloned_configs_stale` | 主模板更新后，复制出去的项目报表配置不标过期 |
| `CHECKLIST_COMPLETED` | `_impl.py::_on_checklist_completed_b3` | B3 相关联动不执行 |
| `NOTE_UPDATED` | `services/consol_note_stale_handler.py::handle_child_note_updated` | 有 `NOTE_SECTION_SAVED` 兜底，影响小 |
| `WORKPAPER_STALE_DETECTED`、`WORKPAPER_AUDITED_CONFIRMED`、`WORKPAPER_PROCEDURE_COMPLETED`、`CROSS_CHECK_FAILED` | `_impl.py` 1379~1383 行的四个处理函数 | 对应联动不执行 |

建议：逐个确认是「该发没发」还是「功能已废弃」，前者补发布点，后者删订阅。

### F2 自动科目映射不经人工确认，直接计入试算表

- `services/mapping_service.py::auto_match` 把匹配结果直接写进 `account_mapping`，模糊匹配最低到 0.7 分。
- 试算表取映射的 `services/tb_balance_rollup.py::resolved_standard_code` 只过滤已删除，不看映射类型，模糊匹配的结果立刻进未审数。
- 对比：报表行次映射只用 `is_confirmed` 的记录。两处口径不一样。

影响：账套一导入，试算表就按「未确认的模糊映射」出数，用户不一定知道哪些科目是猜的。

### F3 科目映射不分年度

`account_mapping` 只有 `project_id`，没有 `year` 和 `dataset_id`。同一项目跨年度共用一套映射，上一年改的映射会影响今年的试算表。

### F4 报表取数：试算表里没有的科目按 0 计，而且算成功

- `services/report_row_compute.py::_missing_account_notes`：`TB('x')` 在试算表里找不到时，只在计算过程里写一句「按 0 计」，这一行仍按成功写入、不标过期。
- 同一套公式里 `WP()`、`NOTE()` 缺数会报错、不写 0，口径不一致。
- 报表生成接口 `routers/reports.py::generate_reports` 返回的 `failed_rows` 写死为 0，界面摘要看不到失败行。

影响：报表某行为 0 时，分不清是「真的为 0」还是「科目没映射上」。这正是老总说的「数为什么不对说不清」的典型来源。

### F5 读账表时，查「当前数据集」失败会悄悄退化

`services/dataset_query.py::get_active_filter` 默认情况下，查当前生效数据集出错时会回滚调用方的事务，再改成「不按数据集过滤」。后果有两个：调用方前面已经写进去但没提交的数据被撤销；读到的可能是旧版本的账。只有传 `strict=True`（目前公式推送等写入方在用）才会直接报错。

### F6 附注被两条链同时写

同一次 `TRIAL_BALANCE_UPDATED` 之后，公式推送（`services/formula_push/engine.py::_push_note`）和报表更新后的附注增量刷新（`services/disclosure_engine.py::update_note_values`）都会写 `disclosure_notes.table_data`，两条链各开会话、先后顺序不固定。写权矩阵（`services/note_write_ownership.py::WriteGate`）保护了推送写定的格，矩阵没覆盖的章节仍可能互相覆盖。

## 二、影响性能、留痕或可解释性

### F7 账套激活后，试算表全量重算两到三次

`LEDGER_DATASET_ACTIVATED` 同时触发：
1. `TrialBalanceService.on_data_imported` 全量重算；
2. 自动科目映射 → `MAPPING_CHANGED`（不带科目）→ `on_mapping_changed` 再全量重算未审数；
3. 之后若生成报表，`ReportEngine.generate_all_reports` 开头还会再跑一次 `full_recalc`。

结果一致，但大账套上浪费时间，也让日志里同一件事出现多次。

### F8 调整列只更新已有的试算表行

`services/trial_balance_service.py::recalc_adjustments` 只更新已存在的试算表行。批准路径会先补行（`adjustment_review_coordinator.py::ensure_tb_rows`），撤回复核、批量提交等事件路径不补行。如果调整用到的科目在试算表里还没有行，这部分调整会被跳过且没有提示。

### F9 一些「规则文件」其实不执行

- `backend/data/*_cycle_validation_rules.json`：表达式没有求值器，签字门禁不读它们，只用于展示和覆盖率统计（`services/formula_check_catalog.py` 自己写明了）。
- `backend/data/note_disclosure_balance_rules.json`：执行它的服务没有调用方。

对外说「有多少条校验规则」时，这两类要剔除。

### F10 两个后台任务写好了但没有启动

`workers/qc_rating_worker.py`（每月 1 日项目质量评级）和 `workers/reviewer_metrics_worker.py`（每天复核人指标）不在 `core/startup_registry.py::_WORKER_BINDINGS` 里，全仓也没有别处启动它们。`project_quality_ratings`、`reviewer_metrics_snapshots` 不会自动更新。

### F11 过期传播的留痕写进一张没有建表语句的表

`services/stale_propagation_engine.py::_write_audit_log` 往 `linkage_audit_log` 插数据，但迁移和 ORM 里都没有这张表。生产库如果也没有，每次写都失败，只记一条 warning，过期传播就没有留痕。

### F12 附注模板读不到时静默退化

`services/disclosure_engine.py::_load_templates` 读 `note_template_soe.json` / `note_template_listed.json` 失败时，退回到只有 6 条的旧种子，不报错。上年数兜底 `_get_prior_from_trial_balance` 也只查这 6 条种子，大部分章节取不到上年兜底数。

### F13 函证服务借用「底稿保存」事件当日志

`services/confirmation_service.py`（384、483 行）和 `services/confirmation_evidence_service.py`（999 行）发 `WORKPAPER_SAVED`，注释写着「复用已有事件类型作通用审计日志」。每次函证操作都会把底稿保存的约 20 个处理器跑一遍，它们靠事件里缺 `wp_id` / `wp_code` 才跳过。

## 三、和「线上直接改生产」直接相关

### F14 发版、改库、回滚的几个硬约束

1. 后端启动时自动执行未跑过的 `V*.sql`（`core/startup_registry.py` 的 `run_migrations`），**发版就等于改库**。
2. 146 张表只在 ORM 里有定义，迁移里没有建表语句，也就没有配对的 `R*.sql` 回退脚本。
3. 启动时 `replay_startup_events` 会把积压的事件重新跑一遍，其中包含写库的处理器（过期标记、公式推送、循环联动）。重启本身可能改数据。
4. 多台服务器部署时，`sla_worker`、`outbox_replay_worker`、清理类 worker 还没有选主去重（`startup_registry.py` 里的 TODO），会重复执行。

线上改动前的备份必须覆盖数据库全库和文件存储，回滚不能指望迁移回退脚本。

### F15 新版 FastAPI 下，项目里遍历路由表的自检看不到路由

仓库 `.venv` 装的是 FastAPI 0.162.2、Starlette 0.52.1（2026-11-09 安装）；`backend/requirements.txt` 里 `fastapi` 没有锁版本。这个版本的 `include_router` 不再把路由复制进 `app.routes`，而是挂一个 `_IncludedRouter` 包装对象。实测导入应用后，`app.routes` 里只有 5 个普通路由，另外 657 项都是包装对象（展开后才是 2676 个接口，本清单就是展开后抽取的）。

后果：项目里直接遍历 `app.routes` 的自检都只能看到这 5 个路由。

- 已实测：`router_registry/__init__.py` 的「未注册 router 模块」检查，导入时报「共 452 个未注册」，是误报。
- 按代码推断、未实测：安全覆盖扫描（`security/entry_coverage_scanner.py`、`security/coverage_guard.py`）、导出出口登记核对（`services/export_surface_registry.py::validate_registry`）、导入入口登记核对（`services/ledger_import_entrypoints.py::validate_entrypoints`）也会因为看不到路由而失效。前两项是安全检查，看不到路由就可能恒判通过。

建议：确认生产环境装的 FastAPI 版本；锁定 `requirements.txt` 里的版本，或者把这些自检改成先展开包装对象再遍历。

## 四、文档里的数字已经过期

| 项目 | 现算 | 项目记忆文件 `.kiro/steering/memory.md` 里的记录 |
|---|---:|---:|
| 公式推送规则（`formula_push_rules.json`） | 268 | 420 |
| 底稿科目映射（`wp_account_mapping.json`） | 1025 | 206 |
| 公式推送接入的底稿编码 | 81 | 80 |
| 底稿编码覆盖（`wp_code_overrides.json`） | 1531 | 1526 |

另有一处注释与代码不一致：`trial_balance_service.py::recalc_unadjusted` 注释说损益类发生额「须从 `tb_ledger` 取」，实际取的是 `tb_balance` 的借贷发生额列。

## 五、核对后确认没有问题的两处

- **审定表发布到试算表后不会被重算冲掉**。`services/tb_audited_writer.py::publish_rows` 同时写审定数和 `wp_adjustment`（= 审定数 − 未审 − RJE − AJE），之后 `recalc_audited` 按「未审 + RJE + AJE + wp_adjustment」重算，结果不变。项目记忆文件里「发布门直写会被覆盖」的担心不成立。另有一个只写审定数的 `services/formula_management/adjudication_writeback.py`，目前没有任何生产调用方。
- **签字一致性门禁出异常时不再放行**。`services/consistency_gate/` 各检查项出异常时记「未执行」（`passed=False`），阻断类判整体不通过。项目记忆文件里「缺数 / 异常即放行」的说法已经不适用。

## 六、对「要不要上规则引擎」的初步判断（供讨论）

现状分两类：

1. **已经是配置驱动的**：报表公式（`report_config`）、公式设置三层、公式推送规则、底稿预填公式、附注模板与校验预设。这些背后有统一的公式引擎（`services/formula_engine.py`，支持 `TB` / `ROW` / `WP` / `NOTE` / `ADJ` / `PREV` / `AUX` 等函数），已经相当于一个规则引擎。
2. **写死在代码里的**：试算表口径、科目自动匹配算法、40 项一致性门禁、按底稿编码正则过滤的循环联动（C/F/D~N 等）、各后台任务周期。

所以问题不在「有没有规则引擎」，而在**同一套公式在不同地方能力不一致**（报表里不支持 `PREV` / `AUX`，预填支持；缺数时报表按 0、`WP` / `NOTE` 报错），以及**写死规则没有统一登记处**。建议先做两件事：统一公式在各处的缺数口径和函数集；把写死的联动与门禁登记成一张可查的清单（本文 R11、R15 可作底稿），再决定要不要抽成配置。
