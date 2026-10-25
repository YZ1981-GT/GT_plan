# 公式管理全面评估：统一架构、公式语言与数据闭环

> 审计日期：2026-10-25。起始代码基线 `779d8b43619c5946c198e11ca35b1ad9330c5dfa`；审计结束时 HEAD 因并发 S-cycle 工作前移至 `0da7d590558bfbc2eeac258ab3e8b26ec363de1a`。这三笔并发提交未触及本文核心后端公式文件，本文结论不依赖其未提交内容。审计只执行源码读取、现有测试、只读运行探针及 PostgreSQL `SELECT`；没有修改生产代码、配置、spec 或业务数据。

## 一、证据口径与总体裁决

证据等级：**S 源码**＝已读当前生产实现；**T 测试**＝现有自动化测试实际运行；**R 真实运行**＝调用生产符号、使用真实 PostgreSQL 数据但不提交事务；**D 真实数据**＝对当前 PostgreSQL 只读统计。注释、历史 spec 和测试名称本身不算实现证据。

**总体裁决：平台已形成共享 L1 算术内核和较完整的 V199 公式治理框架，但尚未形成统一公式运行时。** 定义、继承、模板订阅和冲突决策主要统一在 `formula_settings`；解析、引用装载、求值、写入、stale、重算和溯源仍由多条互不等价的执行轨承担。因此当前状态应称为“统一治理框架 + 多运行时”，不能称为“一个公式引擎贯穿全平台”。【S+R+D】

最高风险结论如下：
- **P0：Formula Runtime 对真实底稿公式会算错。** `FormulaRuntimeCoordinator.generate_mutation_plan` 对真实库 29 条 `wp_formula` 生成 29 个 mutation；其中 18 条 `WP(...)` 与正式严格求值器 `evaluate_wp_formula_expression` **18/18 不一致**，runtime 得到 0/1，而严格求值器得到 1000/2001 等真实值。该协调器又是“一键刷新”的生产分派路径，存在把错误值应用到载荷的风险。【S+R+D；`backend/app/services/formula_runtime/coordinator.py`、`backend/app/services/formula_management/engine.py::execute_batch`、表 `wp_formula`；现有 `test_orchestrator_real_mutations.py` 未覆盖真实表达式】
- **P0：中央 `/api/formula/execute` 同时存在口径错和错误吞没。** `FormulaEngine.execute` 只查询 `trial_balance.unadjusted_amount`，却经 `FormulaContext.from_simple_map` 同时冒充“审定数/未审数/期末余额”；华氏项目 1001 的 `TB('1001','审定数')` 返回 0，而 `TrialBalanceResolver.resolve_tb` 返回 100。`EVIL()`、`1/0`、`ROW('MISSING')` 均返回 `value=0,error=null`。【S+R+D；`backend/app/services/formula_engine.py::FormulaEngine.execute`、`backend/app/routers/formula.py::execute_formula`、端点 `/api/formula/execute`、表 `trial_balance`】
- **P0：全局刷新并未调用各域权威生成器。** `DraftRefreshOrchestrator._dispatch` 的 report/note/adjudication/workpaper 分支均只走 Formula Runtime；`ReportEngine.generate_unadjusted_report` 和 `execute_note_formulas` 只出现在 docstring。对和平药房只读分派得到 report `runtime_units=0/page_keys=7`、note `0/0`、adjudication `0/0`、workpaper:D `0/4`，均提示项目 `wp_formula` 无定义；preset 分支只写 marker/audit，不写业务表。【S+R；`backend/app/services/draft_refresh_orchestrator.py::_dispatch`、`backend/app/services/draft_refresh_service.py::RefreshUnit`】
- **P0/P1：报表存量与当前语义明显漂移，且 stale 未识别。** 对 5 个非测试/UAT项目用当前 `ReportFormulaParser.execute_with_status` 重算 410 行，50 行不一致，其中 49 行 `is_stale=false`；最大差额 3,928,889,818.20。和平药房 BS-002 存量 8,607,977.04，当前求值 4,467,536.12，公式文本相同且 false-fresh。【R+D；`backend/app/services/report_engine.py::ReportFormulaParser`、表 `financial_report/report_config`】

## 二、目标架构与实际架构

目标闭环应为：`公式定义 → 有效层级/模板订阅 → 统一解析与引用解析 → 项目/年度上下文装载 → 求值或校验 → 权威写入/提示 → 依赖传播 → stale 重算并确认清除 → 持久化溯源`。

实际结构是：`V199 定义/模板层 → effective_slots → publish/sync_item → 各域 propagation`，随后分流到 L1、报表 parser、底稿严格 evaluator、Formula Runtime、附注 generator/binding evaluator、Excel A1 evaluator、合并线性分析器及 prefill 扫描器；这些轨道使用不同语法、上下文、错误语义、精度和持久化方式。【S；迁移 `backend/migrations/V199__formula_global_settings_and_templates.sql`，服务目录 `backend/app/services/formula_settings/`】

| 域 | 定义/存储 | 当前执行与写入 | 闭环裁决及证据 |
|---|---|---|---|
| report | `report_config` + V199 override | `ReportFormulaParser`、`ReportEngine`、propagation | 最接近完整，但全量生成、stale 重算、affected 重算使用不同失败语义；410 行实算有 50 漂移。【S+R+D】 |
| tb_detail | V199 setting，前端 `useTbDetailFormulas` | 管理弹窗调用 `/api/report-config/execute-formulas-batch`，结果只留在 `formulaResults` | 只有管理和预览，没有 TB 权威写入；`propagate_tb_detail` 仅把 WP 标 stale，prefill 不消费定义。【S】 |
| cross_check | V199 setting + 规则目录 | 多个独立校验器/目录 | 目录聚合不等于统一执行；`build_check_catalog` 有 1603 项，其中至少 6 条源码明确“注册但未接执行”。【S+R】 |
| wp | `wp_formula`、prefill 配置、前端 payload | 严格 evaluator、Formula Runtime、prefill、前端 autosync | Runtime 真实 18/18 错值；29/29 `refs=[]`、29/29 `last_computed_at IS NULL`，定义到运行时依赖图断裂。【S+R+D】 |
| note | `disclosure_notes.note_data`、静态 preset、V199 materialized `_user_formulas` | note generator、binding evaluator、push、前端 autosync | 多写方重叠；真实 note 顶层 `_formulas/_user_formulas` 均 0，静态 932 条 preset 不能证明已物化执行。【S+D】 |
| consol_note | `consol_note_formula` | 合并附注公式/填入器 | 真实 51 条 active 公式、2 条 fresh 数据，但唯一 consolidated 项目为 UAT，缺业务项目闭环证据。【S+D】 |
| push | V169 规则、binding、state/run | `formula_push.engine` 四阶段写入 | 当前最完整后端闭环：真实 81 bindings、375 active rules；一次和平药房 run 写 139、unchanged 28、kept 4、skipped 92，并更新 28 章节/44 底稿。【S+R+D；迁移 `V169__formula_push_engine.sql`】 |

V199 治理本身具备七域、项目层→模板层→全局精确/`*`→系统预设的有效定义层级，具备 CAS、发布、订阅、pending conflict、adopt/keep/custom；前端 `FormulaGlobalSettings.vue`、`FormulaTemplateManager` 和常驻 `FormulaPendingSyncDialog` 均已挂载。【S；`formula_settings/definitions.py::DOMAINS`、`effective.py::effective_slots`、`template_service.py`、`template_sync.py`、`ThreeColumnLayout.vue`】

但模板层和全局层没有真实使用证据：当前 `formula_setting/formula_sync_item/formula_publish/formula_template/formula_template_version/formula_template_subscription` 全部 0 行，`report_config` 的 `project:*` override 也为 0。模板订阅项在全局发布时被明确标为 `TEMPLATE_SKIPPED`，全局修改只形成 `global_hints`，必须另行发布模板版本；所以“一处修改自动应用全部”只对未固定、未模板接管且传播成功的项目成立。【S+D；`formula_settings/publish.py`、`template_sync.py`、V199 六表】

## 三、公式语言、函数和求值语义

L1 `formula_engine.py::_REGISTRY` 真实登记 20 个函数：`TB,SUM_TB,PREV,AUX,NOTE,WP,ADJ,ROW,SUM_ROW,REPORT,ABS,ROUND,MAX,MIN,IF,LEDGER,LEDGER_DETAIL,TB_AUX,COUNT_LEDGER,PLACEHOLDER`；默认 AST 模式但仍保留 regex 降级。【S+R；`backend/app/services/formula_engine.py`】

前后端 grammar 不闭合：`formulaSyntaxParser.ts` 登记 21 个函数，多出后端不支持的 `PRIOR`，并接受 `%` 和单 `=`；生产 L1 对 `PRIOR('1001','x')` blocked，对 `5%2`、`1=1` 均报 AST parse error。前端测试 `formulaSyntaxParser.spec.ts` 反而明确要求 `PRIOR` 出现在 `knownFunctions()`。【S+T+R；前端定向 6 files 共 117 passed】

参数元数和实际执行也不统一：前端 NOTE 2~3、AUX 2~3、ADJ 1~2、PREV 2~3；严格预载支持 AUX 2/3/4；L1 registry 元数据没有执行时 arity 强校验。公式可在编辑器显示为合法，却在另一执行轨失败或被代 0。【S】

错误策略呈三类：L1 对缺 TB/ROW/WP/NOTE/AUX 多数代 0，`1/0` 也返回 0 且 `ok=true`；`wp_formula_eval_service.evaluate_wp_formula_expression` 对 PREV/AUX/ROW/REPORT/NOTE 采用 strict 并返回 blocked；`note_formula_generator._load_cross_table_data` 范围内有 8 个 `except Exception: pass`，装载失败变空 map，求值为空时保留旧值。相同公式无法获得统一的“失败、空值、保留旧值、代 0、阻止写入”语义。【S+R】

循环检测不成立：给 Runtime 构造 A↔B 引用后仍得到 A=21、B=22、`errors=[]`；`_topological_sort_formulas` 对环节点按原顺序追加，而非返回循环错误。现有 `test_orchestrator_real_mutations.py` 多处只断言 list、空循环或 `len>=1 or scope_failures==0`，可在未证明公式正确时通过。【S+T+R】

精度不统一：报表/L1主轨偏向 Decimal，`note_formula_generator` 和 `cell_formula_evaluator` 使用 float 与各自 `_safe_eval`；跨轨链路没有统一舍入边界。方向口径在 TB 主链较可靠：`TrialBalanceService.recalc_unadjusted/recalc_adjustments/recalc_audited` 使用叶子聚合和 `audited=unadjusted+rje+aje+wp_adjustment`；真实 743 行仅 8 行不符且全属 UAT，排除测试/UAT后的 519 业务行 0 不符。【S+D；`backend/app/services/trial_balance_service.py`、表 `trial_balance`】

跨年与缺引用同样多轨：PREV 严格预载可按上年项目取值，前端却暴露未被 L1 支持的 PRIOR，附注又有独立 PRIOR 装载；因此跨年能力“局部存在”，但语言和失败语义没有统一。项目/年度参数普遍进入各 loader，但本轮没有执行越权写或跨用户测试，本文不对端点权限隔离作通过背书。【S】

自定义函数 API 当前不可用：`routers/formula.py::register_custom_function` 传 `param_names`，`FormulaEngine.register_custom_function` 不接收；注册表还是每个 request 新建 engine 的实例私有状态，handler 也未做参数替换。现有 `TestFormulaDSLAPI` 三项和 `TestFormulaCustomFunctions::test_execute_custom_function` 一项均为 xfail。【S+T；3 xfailed + 1 xfailed】

## 四、引用装载、地址体系与真实运行时断裂

Formula Runtime 的根因不是算术，而是地址到表达式没有闭合：`_build_batch_definitions` 只为 `domain=='workpaper'` 构造 target；loader 把 `addr_id→value` 放入 `FormulaContext.row_cache`，但表达式中的 `TB/WP/NOTE/REPORT` 没有转换为 addr_id，函数 handler 仍读取空的 `tb_data/wp_data/note_data`。`WpStore.write_project` 对全局/模板同步写 `refs=[]`，表达式改变还会清空 refs。【S；`formula_runtime/coordinator.py`、`formula_management/engine.py`、`formula_settings/stores/wp.py`】

Runtime adapter 还与真实 schema 不符：report adapter 只认 `BS/IS/CFS/EQ/CFSS/IMP`，真实 PG enum 是 `balance_sheet/income_statement/cash_flow_statement/equity_statement/cash_flow_supplement/impairment_provision`；note adapter 只认 `{rows:{...}}` 或 `[{key/id,cells}]`，真实 292 个 note 顶层 `rows` 是 array，其中 255 个首行有 `values`，0 个有 `cells/key/id`。`test_note_adapter.py` 使用 MagicMock 和人造 `{key,cells}`，report 测试使用自建 SQLite String model 与 `BS`，所以绿测没有覆盖生产形状。【S+T+D】

平台目前同时维护 V1 Address Registry、ACNR 和 V2 静态依赖图，并另有 V199 regex dependency：ACNR 1215 sheets/474 cells，registry version `20260727115337`；V2 有 181 wp codes、42,163 dependencies，unified graph 39,421 edges。地址目录规模不小，但四套标识/依赖解析尚未收敛为执行器的单一入口。【S+R；`address_registry`、`address_registry_v2`、ACNR、`formula_settings/dependencies.py`】

## 五、报表、附注、底稿和推送闭环

报表定义规模为 318 条 active `report_config` 公式，函数调用 TB 264、SUM_ROW 65、ROW 28、SUM_TB 4；`financial_report` 物化 574 行、83 个 distinct `(row_code,formula_used)`、覆盖 7 项目。全量 `_generate_report_type` 用 `parser.execute()` 丢弃 `FormulaResult` 状态并可能以 0 清 stale，`recalculate_stale_rows` 用 `execute_with_status` 保留旧值/stale，`regenerate_affected` 又回到 `execute()`；同一域三条重算路径语义不一致。【S+D；`backend/app/services/report_engine.py`】

报表执行溯源也可能与结果矛盾：`report_config.py::execute_formula` 的值来自真实 resolver，但 trace 用空 `FormulaContext` 重跑原式；和平药房 BS-002 的 resolver 值为 4,467,536.12，路由同构 trace 值为 0，三个 TB trace 均写 `=0`，而 route 仍 `trace_ok=true`；batch resolver 路径 trace 直接为空数组。【S+R；端点 `/api/report-config/execute-formula` 与 batch 端点】

附注存在两套重叠写方：全仓有 67 个 `build*SyncPayload` 定义、57 个文件，144 个生产文件引用 `useDisclosureAutoSync`，70 个 watch+schedule，141 文件含 `/disclosure-notes/sync-from-workpaper`；可解析 builder wp_code 56 个全部与 81 个 push binding 重叠，50 个 autosync code 中 46 个与 push 重叠。push note stage 覆盖 75 codes，其中 builder overlap 52、autosync overlap 46。这里能确定的是章节/wp_code 所有权重叠；字段级是否冲突仍受 `_source`、manual、locked 规则协调，不能据此断言每格都会双写。【S+R】

Formula Push 是正向样板：source loader 不吞 TB/adjustment 错误，binding 检查 `FormulaResult.errors/blocked`，写入走 CAS/savepoint，成功 note 会清 stale。真实 3 次 run 中，和平药房 manual run 成功；安徽骨科 manual 与 `TRIAL_BALANCE_UPDATED` 各 0 write/78 skip，原因是底稿不存在。真实 state 171 条：workpaper auto 99、note auto 68、note manual 4。【S+D；`backend/app/services/formula_push/`、表 `formula_push_run/formula_push_state`】

stale 不能稳定收敛：当前 `financial_report` 2456 fresh/8 stale，`disclosure_notes` 863 fresh/227 stale，`working_paper` 1801 fresh/190 stale；227 个 stale note 来自 2 项目且 `stale_source` 全 NULL，最早 2026-05-13。report propagation 能标记、重算并在成功后清；note propagation 只物化/标 stale，`execute_note_formulas` 不清；`NoteStaleService.refresh_stale_sections` 只清 `sections_recomputed`，而值未变化时 section 不进入该集合；WP 手工 prefill 也不清，只有 TB recalc 的额外流程会清。【S+D；`formula_settings/propagation.py`、`note_stale_service.py`、`DisclosureEngine.refill_sections`】

EventBus 不能作为可靠提交日志：`publish` 先 debounce 500ms，真正 `_dispatch` 才 `ensure_future(_persist_to_stream)`，调用返回时尚未持久化；handler 错误被吞后仅发 `SYNC_FAILED`，Redis 写也是 fire-and-forget。`formula_runtime_outbox`（迁移 `V104__formula_runtime_outbox.sql`）只保护 draft runtime，不保护 V199 settings propagation。好的一面是 pending conflict 持久化在 `formula_sync_item`，项目打开时对话框主动 GET，可恢复通知丢失。【S】

## 六、溯源、模板共享与“所见即所算”

溯源信息分散在 report 的 `formula_used/source_accounts`、push state、WP `refs`、note JSON 元数据和临时 `FormulaResult.trace`。`UnifiedLineageService` 不读取 `formula_setting/formula_push_state/FormulaResult.trace`，部分查询异常仅 debug；前端 `<LineageGraphPanel>` 生产挂载为 0，唯一命中是 `useLineagePanel.ts` docstring 示例。`GtFormulaSourceTooltip` 仅 2 个生产组件、5 个挂载，`FormulaDependencyPanel` 只在 FormulaManagerDialog 一处。因此“数据来源和计算过程随处可知”尚未成立。【S+R】

预设库 `build_preset_library()` 生成 4250 条：report 343、workpaper 1300、note 2607，但无 wide-table source。`note_wide_table_engine.py` 指向不存在的 `D:/GT_plan/附注模版/*.md`；真实文件在 `D:/GT_plan/数据/附注模版/*.md`，且内容用 `公式：...`，解析器只认 `- 横向:`/`- 纵向:`，即使改传正确目录也返回 0。`test_note_sprint4.py` 只测试文件不存在时返回 `[]`，没有成功解析真实文件的测试。【S+T+R】

模板 CRUD、版本、发布、promote、订阅和冲突 UI 已实现；但 live 六张治理表全 0，故只能判定“能力已编码并挂载”，不能判定“已供他人真实引用并与全局变更联动”。要达到用户目标，模板发布、项目订阅、全局升级冲突和一次真实公式重算必须形成可复验数据链。【S+D】

## 七、测试可信度与假绿说明

本轮现有核心后端定向套件运行结果为 **166 passed, 1 warning, 8.37s**；前端 6 files 为 **117 passed**。自定义函数为 3+1 xfailed。另一次把整份 `test_custom_dsl_coding.py` 加入组合后为 175 passed、4 xfailed、19 errors；19 errors 来自该测试 SQLite setup 的 `sqlite3.OperationalError: unrecognized token`，拆分后得到上述干净结果。【T】

这些绿测不能抵消真实运行反证：166+117 全绿仍未发现 WP runtime 18/18 错值、report 50/410 漂移、route trace 4,467,536.12→0、真实 enum/note shape 不兼容。主要原因是 SQLite、MagicMock、人造载荷、结构断言以及允许空结果的断言。后续门禁必须至少包含真实 PostgreSQL schema、真实 JSON shape、生产函数调用和“预期数值逐值一致”四层。【T+R+D】

## 八、整改顺序与验收标准

1. **P0 冻结 Formula Runtime 写入**：在修复前，一键刷新不得应用 runtime mutation；先让表达式引用通过统一 resolver 解析，补真实 `wp_formula` 的逐条对拍、真实 report enum/note payload 契约和环检测。验收：当前 18 个 WP 引用与严格 evaluator 18/18 相等，环明确 blocked，report/note adapter 对真实快照零拒读。【基于 S+R+D】
2. **P0 修中央 API 和报表 trace**：`/api/formula/execute` 必须使用 TrialBalanceResolver/统一上下文，保留 `errors/blocked`，按表达式实际函数做能力校验；trace 必须来自同一次求值而非空上下文重演。验收：审定数=100 的探针返回 100，除零/未知函数/缺引用不再 `error=null`，BS-002 的 value 与 trace 完全一致。【基于 S+R】
3. **P0 让全局刷新调用各域权威实现**：report 调 ReportEngine，note 调已裁定的附注执行链，adjudication/workpaper 只在该域有效定义存在时执行；marker 不得冒充业务刷新。验收：四域各选一个真实项目，对业务表 before/after、audit、stale、lineage 做事务内对账。【基于 S+R】
4. **P1 收敛语言与失败语义**：建立一份可执行 grammar/arity/function registry，前后端生成或共享；明确 missing、null、blocked、divide-by-zero、旧值保留、舍入、PREV/PRIOR 的唯一语义。验收：同一公式在预览、批量、报表、WP、note 和 push 的状态与数值一致。【基于 S+T+R】
5. **P1 建立单一写方与 stale 协议**：按 `domain+target` 明确权威 writer；对 note 的前端 autosync 与 push 做字段所有权清单，未交集处保留、交集处只留一条生产写路。stale 清除应以“重算成功”而非“值发生变化”为条件，并记录 source/version/error。【基于 S+D】
6. **P1 统一依赖和溯源**：选定 ACNR addr_id 为稳定身份，V1/V2/V199 dependency 均转为其视图；把 definition version、resolved refs、输入值、计算步骤、writer、run id、stale 原因持久化到统一 lineage read model，并实际挂载 LineageGraphPanel。【基于 S+R】
7. **P1 用真实订阅证明模板闭环**：建立测试专用全局公式、模板版本、两个项目订阅；执行全局变更→模板 hint→模板发布→项目冲突→adopt/keep/custom→实际重算。验收不只看六表有行，还要验证业务目标值、版本、冲突记录和 lineage 同步变化。【基于 S+D】

## 九、最终回答

平台目前**没有一个统一公式引擎贯穿试算表、四库表、报表、附注和底稿**。它有可复用的 L1 算术层、较成熟的 V199 定义/模板治理层，以及当前最可靠的 Formula Push 闭环；但引用装载、执行器、写入权威、错误语义、stale 清理和溯源尚未统一。关键主链中已经存在真实错值、false-fresh 和假刷新，必须先封住 P0 写入风险，再谈扩大模板共享和“一处修改、全部应用”。【综合 S+T+R+D】
