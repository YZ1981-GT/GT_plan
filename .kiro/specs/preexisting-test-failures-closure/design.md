# 设计：46 个预存失败用例逐一收口

判定口径：**生产缺陷**＝生产代码偏离正确行为，修生产代码并补单独抓它的测试；**测试过时**＝后来有意的改动没同步到测试，按现行设计改成精确断言并写明是哪次改动；**测试不封闭**＝真调外部服务或依赖库里恰好有的数据，改成夹具建数据 / 打桩。

现象一栏的失败信息取自干净 HEAD 检出（验证 worktree，`git checkout -- .` 后跑同一批文件）。

## 0. 总表

| 组 | 例数 | 判定 | 修法一句话 |
|----|------|------|-----------|
| G1 WOPI 质控复核 | 15 | 混合（见 §1.1） | SQLite UUID 绑定修正 + QC 就绪夹具 + put_file 被拒后还原磁盘（生产缺陷）+ 列表用例迁真库 |
| G2 index_source | 7 | 测试过时 | 按现行 SELECT / 三类来源 / 13 个枚举值精确断言 |
| G3 ai_content_structured | 4 | 测试过时 | 脚本已迁到 `scripts/migrate/`，改 import |
| G4 task4_run_contract | 3 | 测试过时 | spec 已归档，路径走 `_spec_dir.resolve_spec_dir` |
| G5 g7_sub_integration | 3 | 测试不封闭 | 打桩打在导入期绑定的名字上，不再真调大模型 |
| G6 qc_rule_definitions_loader | 3 | 测试过时 | 按 R7 拒绝清单语义精确断言内置规则集 |
| G7 a16_sign_status_check_auto | 2 | 生产缺陷 | resolver 的 step_status / link / detail 被丢弃，按白名单透传 |
| G8 archive_deprecated | 2 | 测试不封闭 | 覆盖二次确认依赖 + 补「无确认令牌 403」 |
| G9 g1_classification | 2 | 测试过时 | 假底稿补 project_id + 打桩并断言缓存失效 |
| G10 ocr_service | 2 | 生产缺陷 | 大模型结果只补规则未取到且被请求的字段，规则结果优先 |
| G11 startup_registry | 2 | 生产缺陷 | 启动编排两份副本各自漂移；lifespan 改为执行 registry，health 输出启动报告 |
| G12 review_prompt_integration | 1 | 生产缺陷（口径） | 覆盖率按 wp_code 前缀统一计数，扫描范围与加载规则一致 |

## 1. 各组根因与修法

### 1.1 G1 `test_wopi_working_paper_qc_review.py`（15 例）

四个独立根因：

**(a) 可见性 SQLite 兼容层（生产缺陷，10 例）**。现象：get / upload / status / assign / qc-results / reviews 等端点 `assert 404 == 200` ×8，reply / resolve 取上一步响应 `KeyError: 'id'` ×2。`VisibilityQueryService._sqlite_portable_uuid_casts` 把 `CAST(:pid AS uuid)` 换成裸 `:pid`，而参数是 `str(uuid)`（带连字符），SQLAlchemy `Uuid` 在 SQLite 存 32 位十六进制（实测 `'4bdf5453…'`，连字符形式匹配 0 行）⇒ admin 也看不到任何底稿，闸门 404。修法：换成 `REPLACE(:x, '-', '')`；查回来的 `wi.id` 在 SQLite 是文本，`_aggregate` 统一转 `UUID`（否则 `grants_for_project` 的可见集拿 ORM 的 UUID 比对恒不命中）。只在 SQLite 生效，PG 原样。守卫：新增 `test_visibility_query_sqlite_compat.py`（admin 可见集精确等于本项目两张底稿且为 UUID；单底稿 grant 为 admin、他项目底稿不可见）。

**(b) QC 规则不再是桩（测试过时，4 例）**。现象：`passed` 为 False（`assert False is True` ×3，`passed_qc` `0 == 1`）。R7（83614b612）起空登记表 = 20 条内置规则全部启用；裸底稿实测恰好命中 QC-01 结论 / QC-04 复核人 / QC-15 审计说明 / QC-17 附件四条阻断。修法：`_make_qc_ready` 夹具补齐四项（`qc_ready_wp`），通过用例改用它并精确断言零发现；补反向用例：裸底稿恰好这四条、四项各缺一项恰好命中对应那一条。

**(c) 列表端点（测试过时，1 例）**。现象：`assert 5 == 2`。响应自 procedure-delegation-visibility-isolation Task 8 起是 `{items,total,stats,page,page_size}`，`len(dict)=5`；且列表 SQL 是 PG 专有（`DISTINCT ON` / `ANY(CAST(:ids AS uuid[]))`），SQLite 跑不起来。修法：用例迁到 `test_working_paper_list_api_pg.py`（真库、事务回滚），精确断言键集合、`total=2`、两张底稿编码。真库实跑通过。

**(d) put_file（生产缺陷，1 例）**。现象：`OpaqueBundleNotProvisionedError('lane wopi_put_file: 库里没有 authority model=opaque_single_onlyoffice …')`——夹具库没有该 lane 的 bundle，拒绝停在 bundle 解析，走不到 OOXML 门。排查中发现生产缺陷：`put_file` 先把载荷写进底稿文件，再调 `commit_bytes`（OOXML 结构校验 / bundle 解析 / revision CAS 都在里面）；提交失败只回滚 DB，磁盘上已是被拒的字节（GetFile 照发），首次保存也不删。仓库 `backend/` 下 8 个 `<uuid>/2025/B1-1.xlsx`（每个 7 字节 = `b"content"`）就是旧用例每跑一次留下的被拒载荷。修法：DB 侧准备（updated_at / writer / current_revision / 审计日志）挪到写盘之前；写盘 → 哈希校验 → 提交包在一起，任何异常先 `_restore_pre_save_bytes`（有快照拷回、首次保存删除）再抛出。用例移到 `test_wopi_put_file_rollback.py`：按 provision 宿主脚本的同一入口给 lane 发布 bundle，底稿与 artifact store 落 `tmp_path`，断言 ZIP magic 拒绝 + 磁盘保持保存前字节 / 首次保存不留文件。真库探针（事务回滚）：成功路径 revision 0→1、磁盘为新字节；随后非 OOXML 载荷被拒、磁盘还原为上次保存、revision 不变。8 个残留目录已逐个核对（未跟踪、仅含该 7 字节文件）后删除，重跑不再产生。

### 1.2 G2 `test_index_source.py`（7 例，测试过时）

现象：`index_source.py:240 AttributeError: 'tuple' object has no attribute 'access_level'` ×5；`assert 3 == 2`；`assert 13 == 12`。`KnowledgeDocSource` 的 SELECT 在 601707554 改成返回带 `access_level` 等列的行，用例的 `_doc_row` 还是旧元组；索引源注册表在 55c5e0fe5 加了 `address_coordinate`；枚举现为 13 个成员。修法：`_doc_row` 按现行 SELECT 造 `SimpleNamespace`；注册表精确断言 `["business_data", "knowledge_doc", "address_coordinate"]`；枚举按 13 个成员集合精确断言。

### 1.3 G3 `test_ai_content_structured.py`（4 例，测试过时）

现象：`ModuleNotFoundError: No module named 'scripts.migrate_ai_content_structure'` ×4。脚本在 3979f46cc 按 scripts 子目录规约迁到 `scripts/migrate/`，全仓只剩这 4 处旧 import。修法：改为 `scripts.migrate.migrate_ai_content_structure`。

### 1.4 G4 `dsh_agent_panel/test_task4_run_contract.py`（3 例，测试过时）

现象：`FileNotFoundError: …\.kiro\specs\dsh-agent-panel-integration\design.md` ×3。该 spec 已归档。修法：路径走既有单一来源 `backend/scripts/check/_spec_dir.resolve_spec_dir`（active 优先、回退 `_archive/**`）；同病的 `mutate_dsh_agent_panel_guards.py`（默认输出目录改为解析到的 spec 目录）与 `mutate_frontend_reference_integrity.py` 的 docstring 示例一并改。否决：写死归档路径（下次搬家又红）。

### 1.5 G5 `test_g7_sub_integration.py`（3 例，测试不封闭）

现象：开发环境 `.env` 打开 `WP_AI_SERVICE_ENABLED` 时真调大模型、断言回复内容失败；关着时 `assert 503 == 200`。打桩打在 `app.services.llm_client.chat_completion`，而路由模块在导入期 `from … import chat_completion` 绑定了自己的名字，桩拦不住。修法：桩改打 `_g7_long_term_equity_subsidiary_ai.chat_completion`；autouse 夹具显式开开关并打桩审计日志；5 个 section 参数化、断言正文等于桩的回复；补「开关关闭 ⇒ 503 且不调模型」。

### 1.6 G6 `test_qc_rule_definitions_loader.py`（3 例，测试过时）

现象：`assert 20 == 22` ×2；`Expected 21 enabled codes, got 19`。R7（83614b612）把登记表改成拒绝清单语义：未登记 = 启用，只有登记且 `enabled=false` 才关；内置规则为 QC-01~18、QC-27、QC-28 共 20 条。修法：按该语义精确断言；补「空登记表执行全部内置规则并告警」与「内置规则集合钉死」两条。否决：把代码改回允许清单（会重新引入空表 = 全部规则不执行的 P0）。

### 1.7 G7 `test_a16_sign_status_check_auto.py`（2 例，生产缺陷）

现象：`KeyError: 'step_status'` ×2。26fe57a69 把 resolver 分发拆成注册式时只搬了 `summary`，各 resolver 声明会带回的 `step_status`（程序行状态建议）/ `link` / `detail` 全被丢弃。修法：`procedure_table_auto_service._RESOLVER_PASSTHROUGH_KEYS = ("step_status", "link", "detail")` 按白名单透传；补 `TestRegisteredResolverPassthrough`。否决：全量透传（会把 `levels` 等内部键泄到程序表行）。

### 1.8 G8 `test_archive_deprecated.py`（2 例，测试不封闭）

现象：`Expected 200, got 403: {"detail":"X-Confirmation-Token header required"}`；`assert 503 == 200`。b98cdc51f 给归档编排加了二次密码确认依赖，用例没覆盖。修法：用例覆盖 `require_confirmation_token`；补「不带确认令牌 ⇒ 403 且不建归档作业」。

### 1.9 G9 `test_g1_classification.py`（2 例，测试过时）

现象：`AttributeError: '_FakeWorkpaper' object has no attribute 'project_id'` ×2。e81fea54e 起写回提交后按 `wp.project_id` 让 WP 域地址缓存失效。修法：替身补 `project_id`；`wp_cache_touches` 夹具打桩 `wp_parsed_data_service.touch_wp_registry` 并断言恰好失效一次本项目（测试保持封闭，不跑真实 ACNR invalidate）。

### 1.10 G10 `test_ocr_service.py`（2 例，生产缺陷 · 字段清单待确认）

现象：`assert 8 == 3` ×2。30a6a489e 起 `extract_fields` 先走规则层、LLM 只补缺失字段，但合并写成 `rule_fields + llm_fields`：规则已取到的字段被 LLM 再给一遍时出现两次（值 / 置信度各异，下游取哪个看顺序），没请求的字段也混进来。修法：规则结果优先，LLM 只补「被请求且规则没取到」的字段、同名只取第一个。用例精确钉死字段与来源顺序、提示词里只列缺失字段；LLM 多给的未请求字段（`seller_name`）不得并入。字段清单按规则层现行输出钉住（含规则层算出的 `total`、银行回单把交易日期也报成 `invoice_date`），列入 §3 待确认。


### 1.11 G11 `test_startup_registry.py`（2 例，生产缺陷）

现象：`assert 'startup' in {...}`（`/api/health` 无 `startup` 键）；`assert <function _start_workers> is <function start_all_workers>`。

根因：platform-architecture-convergence（已归档，标 22/22）要求 lifespan 改为执行 `STARTUP_TASKS`、`/api/health` 输出启动报告。`startup_registry.py` 是新文件随 62cb462ea 入库，而 `main.py` / `health.py` 是共享已跟踪文件，该提交按「Method A」刻意不收 ⇒ 接线从未入库（`git log --all -S startup_registry -- main.py health.py probes.py` 为空）。结果是启动编排有两份：`main.lifespan`（真在跑）和 `STARTUP_TASKS`（只被测试看），之后两边各自漂移：

| 漂移 | 真在跑的 main | 只被测试看的 registry |
|------|--------------|---------------------|
| 调整分录审批 / 撤回重算、公式推送 ×2、合并附注公式刷新 ×2（事件总线 6 个订阅） | 有（139 个订阅） | 缺（133 个） |
| workpaper-sync 冷注册后台预热 | 有 | 缺 |
| 启动 schema 漂移自检的 critical 口径 | 手写 `orm_extra/enum_mismatch`，漏 `checksum_drift` | `count_critical`（正确） |
| 后台 worker 清单 | 一份 | 两份（`start_all_workers` + `_worker_specs`） |

registry 的顺序锁 / 关键性锁守的是一份不执行的副本；若有人照 spec 原意直接把 lifespan 切到 registry，6 个事件订阅会静默丢失。`test_schema_drift_detector` 里那条 strict xfail 也是同一根因（其理由原文：「修掉后本用例 XPASS ⇒ strict 失败，届时删除 xfail 标记」）。

修法（单一来源）：
1. registry 补齐上表三个 handler 注册与后台预热任务 `warm_workpaper_sync_registry`（best_effort，只建后台任务、引用进 `ctx.worker_tasks`）；worker 清单收成一份 `_WORKER_BINDINGS`，`start_all_workers` 直接执行同一组 worker spec。
2. `main.lifespan` 启动段改为 `ctx = StartupContext(); await run_startup_tasks(context=ctx)`，关闭阶段用 `ctx.stop_event` / `ctx.worker_tasks`；删掉 main.py 里 14 个重复的启动辅助函数（837 → 287 行，移出行数白名单）；`main._start_workers` 改为再导出 `start_all_workers`。
3. 预热包装（日志 + 吞异常 + 放行 CancelledError）原样移到 `workpaper_sync/startup_prewarm.warm_workpaper_sync_registry`。
4. `/api/health` 增加 `startup: startup_report_as_dict()`，不参与 status 判定。

守卫：lifespan 在 `yield` 前只调 `StartupContext` 与 `run_startup_tasks`、main.py 不得再定义任何启动任务体（AST）；lifespan 行为测试（关闭阶段置 stop_event、cancel 掉 registry 放进来的任务）；phase handler 任务把 10 个注册函数各调一次；预热不被 await 且引用进 `ctx.worker_tasks`；`start_all_workers` 恰好启动 `_WORKER_BINDINGS`（含 / 不含 ImportJobRunner）；移除 strict xfail 使其成为真守卫。跟随改动的他组测试：`test_formula_push_triggers`（注册点迁移）、`test_sync_registration_prewarm`（预热位置迁移，接线判据由读源码改为行为断言）、`probe_platform_baseline.py`（只读探针按新位置取数）；docstring 里指向 `main._register_phase_handlers` / `_start_workers` 的 4 处同步。

验证：事件总线订阅改前（旧 main）与改后（registry）逐项相等（139 = 139）；worktree 在 9981 起第二个实例跑真实 lifespan，`startup` 37 项全部 ok（`run_migrations` 按 `GT_BOOTSTRAP_DONE=1` 跳过）；共享开发后端热重载到新 lifespan 后同样 37 项、0 失败，预热日志「29 个 adapter / 暖 11 个 / 失败 0 个」与改前一致。

### 1.12 G12 `test_review_prompt_integration.py`（1 例，生产缺陷 · 口径待确认）

现象：`assert data["total_subjects"] >= data["subjects_with_sheet_prompts"]` → `67 >= 82` 失败。

根因：`ReviewPromptService.get_coverage` 两个数用的不是同一单位——`total_subjects` 数根目录科目级文件（67 个，命名不统一，另有 3 个不含「审计复核提示词」的根文件不计），`subjects_with_sheet_prompts` 数 sheet 级目录里的 wp_code 前缀（82 个）；而 `sheet_breakdown` 与 `missing_gaps` 本来就按前缀。另外扫描范围 `_CYCLE_LETTERS` 只有 D~N+S，而加载规则 `load_prompt` 按 `wp_code[0]` 取任意字母目录 ⇒ A/B/C 三个目录 106 个 sheet 级提示词能被加载却不进覆盖率（现扫全部目录 141 个前缀）。

选项：
- A（采纳）：全部按前缀计。`total_subjects` = 已知前缀（`_AUDIT_CYCLE_ALIASES` 键 ∪ 有 sheet 级文件的前缀），`subjects_with_sheet_prompts` = 有 sheet 级文件的前缀数，`missing_gaps` = 二者之差；扫描范围改为全部单字母目录（与 `load_prompt` 同一规则）。恒等式 `total = with_sheet + len(missing_gaps)` 成立。现值 142 / 141 / `["S1 (审计方案)"]`。
- B（否决）：全部按科目文件计。科目 ↔ 前缀只能靠 `_AUDIT_CYCLE_ALIASES` 的关键词映射，而该表大面积错位（见 §2），算出来的数本身就不可信（按它映射只得 59，且 8 个科目映射不到任何前缀）。

字段名 `total_subjects` 不变（前端无消费方，只有该路由与测试），`get_coverage` docstring 与 `CoverageReport` 字段注释改为前缀口径（路由文件 `review_prompt.py` 触碰前已 882 行且未登记行数白名单，响应模型不动）。需求原文「total subjects (69)」指科目级文件数，口径变化列入 §3 待确认。

守卫：集成测试改为精确恒等式 + A/B/C 前缀进入 `sheet_breakdown`；新增夹具目录单测钉死精确值（含不在别名表的前缀、无前缀文件、非单字母目录）。

## 2. 排查中发现、不在本轮范围的问题（如实登记，未修）

| # | 位置 | 现象 / 证据 | 不修的原因 |
|---|------|------------|-----------|
| 1 | `tests/test_auto_data_resolvers.py::test_resolver_success_contract` | 干净 HEAD 上 3 例失败：`a15_financial_ratios` 裸抛 `decimal.InvalidOperation`；`h1_depreciation_by_counterpart`（返回 `available/reason/by_counterpart`）与 `review_dashboard_status`（返回 `levels`）缺 `summary` | 不在 46 例内，需对照各 resolver 的返回契约单独定根因 |
| 2 | 约 74 个测试文件 | 写死已归档 spec 的路径（如 `test_task32_bridge_state_domain`、`test_render_schema_coverage`、`acnr/test_resolve_contract` 报错；`test_n_foundation_p4_closeout` 静默跳过） | 批量改路径会触及他人 spec 守卫，应按 G4 同一修法（`_spec_dir.resolve_spec_dir`）另立一轮 |
| 3 | 约 100 处 `sa.Enum(..., create_type=False)` | `create_type` 对通用 `sa.Enum` 静默无效（已记于 dsh-kb-ocr-local-first-routing design §1.3） | 与迁移体系相关，需单独评估 |
| 4 | `test_pm_workflow_e2e`（1）/ `test_property_archived_invariant`（1）/ `test_onlyoffice_word_template_callback`（5） | G1 修复的相邻回归里失败；干净 HEAD 逐例同样失败（与本轮改动无关） | 不在 46 例内 |
| 5 | `review_prompt_service._AUDIT_CYCLE_ALIASES` | 科目级降级用的关键词与 sheet 级提示词标题对不上：40 个前缀错位（如 G1 映射「长期股权投资」而 G1 是交易性金融资产，M1 映射「实收资本」而 M1 是应付股利），另 4 个标题不含科目名无法判定 ⇒ sheet 级缺失时会加载别的科目的提示词 | 需按致同 2025 编码逐条复核业务含义 |
| 6 | WOPI 锁用例 `test_unlock_wrong_id` / `test_refresh_lock` | 非严格 xfail，单跑 xfail、与其他文件同跑 XPASS（依赖 Redis 可用性）；xfail 理由本身描述了真实缺陷（锁写 Redis、unlock / refresh 只查内存） | 不在 46 例内 |
| 7 | `test_put_file_version_contract_moved_to_real_postgres` 的 docstring | 声称版本单调契约已搬到 `tests/workpaper_sync/test_task19_writer_migration_pg.py`，该文件不在 HEAD（只在另一引用上的 42d2f6e6f）⇒ put_file 成功路径在 HEAD 上没有真库测试（本轮用探针实测过一次） | 恢复该真库用例属 workpaper-sync spec |
| 8 | `app/main.py` 的 `/api/_debug/a51-*` 三个临时端点（4198a4d8f 入库） | 无鉴权：可按任意 wp_id 读 content_revision、可触发注册表 `register_from_manifest` | 属 canary 排障遗留，需端点所有者决定删除或加管理员鉴权；本轮只把它们周围的启动代码移走，未动端点本身 |

## 3. 待确认事项

1. G12 覆盖率口径：`total_subjects` 由「根目录科目级文件数（67）」改为「已知 wp_code 前缀数（142）」，四个字段同一单位；扫描范围扩到 A/B/C。
2. G10 字段清单：按规则层现行输出钉住，包括规则层算出的 `total`（价税合计）与银行回单同时报出的 `invoice_date`。若这两项不应出现，属规则层（`ocr_rule_engine`）的口径问题，另行修。
