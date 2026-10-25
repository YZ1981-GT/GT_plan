# 11 · 公式能力覆盖矩阵（独立角度：覆盖矩阵）

> 只读调查，2026-10-25。证据全部来自源码现读 + 本机 PG `audit_platform`（5432）只读查询 + 回滚事务内实跑生产执行器（探针放 `C:\gt_wt\_probes\`，交付后已删除）。未参考同目录其余报告。
> 级别口径：**L1 已编码**（有实现代码 / 规则数据）· **L2 已挂载**（有生产入口：路由 / 事件订阅 / 已挂载组件可触达）· **L3 已运行**（真库有运行痕迹，或在真实项目数据上实跑出非「跳过」的结论）· **L4 业务闭环**（用户在真实项目上可用且结果被下游消费 / 落库 / 可追溯）。格内写「最高达到的级别」；`—` = 该能力对该模块不适用或无任何实现。

## 一、结论先行

- **矩阵合格度：不合格。** 90 个格子里达到 L4 的只有 15 格，**全部落在「取数 / 推送 / 引用 / 来源展示」一侧**（试算表 5、余额表 3、序时账 / 辅助余额 / 辅助明细的穿透各 1、报表 2、附注 1、底稿 1）；「逻辑校对 / 提示性规则 / 用户公式 / 跨期」四列在 10 个模块上**没有一格达到 L4**。
- **校对目录 1603 项**：其中 425 项是「跨底稿引用（取数关系，非校对）」，真正的校对类规则 **1178 项**。有执行器（代码会按此规则求值）的 **≤219 项（18.6%）**；在真实项目上实跑出非跳过结论的约 **23 项（2.0%）**；真库持久化痕迹只有质控 1 次运行（`wp_qc_results` 1 行，2026-05-15，findings 为空），表间审核 / 跨科目 / 门禁 **0**（`cross_check_results` 0 行、门禁不落库）。**≥959 项（81.4%）从未被任何代码执行**，其中附注预置勾稽 932 条 **100% 是自然语言伪公式**，没有一条机器可执行。
- **提示性 vs 阻断性：语义没有统一，UI 只在局部区分。** 目录的 `severity` 一列混了两套维度（`logic_check/reasonability` 是公式类别，`blocking/error/warning/info` 是严重度）；表间审核用户规则**根本没有严重度字段**；报表审核把「提示性审核未通过」算进 `consistent=false` 与「未通过」总数；一致性门禁 40 项里 32 项「数据缺失 → `passed=True`」（其中 21 项是阻断级），**阻断级规则缺数即放行**；附注校验的 error / warning 不看规则语义、只看差额是否 > 0.01。
- **最大缺口（按影响排序）**：①附注校对整列空转（附注预置 932 条不可执行；附注公式执行器忽略 `category`，用户存的勾稽公式会被当取数公式**写回单元格**，纯函数实测 `cell(2,0) = cell(0,0) + cell(1,0)` 写入 300）；②一致性门禁缺数即通过 + 试算平衡用错符号口径（真实项目报差额 50.15 亿的假阻断）；③合并报表 / 合并附注全部停在 L2（真库 0 个合并项目、`consol_trial` 0 行）；④跨期 PREV 在真库无法闭环（只有 2025 年度，`financial_report` 无任何 2024 行）；⑤全局 / 项目适配 / 模板三层真库零数据（`formula_setting` 等 6 张表全 0）。

## 二、覆盖矩阵（10 模块 × 9 能力）

图例：格内 `级别 · 证据编号`，证据详见第四节。

| 模块 \ 能力 | 自动取数 | 写入推送 | 逻辑校对 | 提示性规则 | 用户公式 | 跨期 PREV | 跨表/跨模块引用 | 事件刷新 | 来源展示 |
|---|---|---|---|---|---|---|---|---|---|
| 试算表 | **L4** · T1 | **L4** · T2 | L3 · T3 | — · T4 | L2 · T5 | L3 · T6 | **L4** · T7 | **L4** · T8 | **L4** · T9 |
| 余额表 tb_balance | **L4** · F1 | **L4** · F2 | L2 · F3 | — | — · F4 | L2 · F5 | L3 · F6 | L3 · F7 | **L4** · F8 |
| 序时账 tb_ledger | L3 · F9 | L2 · F10 | L2 · F3 | — | — · F4 | — | L2 · F11 | L3 · F7 | **L4** · F8 |
| 辅助余额 tb_aux_balance | L3 · F12 | L2 · F10 | L1 · F13 | — | — · F4 | — | L2 · F11 | L3 · F7 | **L4** · F8 |
| 辅助明细 tb_aux_ledger | L2 · F14 | — | — | — | — · F4 | — | L1 · F14 | L3 · F7 | **L4** · F8 |
| 报表 | **L4** · R1 | L3 · R2 | L3 · R3 | L2 · R4 | L2 · R5 | L2 · R6 | L3 · R7 | L3 · R8 | **L4** · R9 |
| 附注 | L3 · N1 | **L4** · N2 | L2 · N3 | L1 · N4 | L1 · N5 | L2 · N6 | L3 · N7 | L3 · N8 | L3 · N9 |
| 底稿 | **L4** · W1 | L2 · W2 | L3 · W3 | L2 · W4 | L3 · W5 | L2 · W6 | L3 · W7 | L3 · W8 | L2 · W9 |
| 合并报表 | L2 · C1 | L2 · C2 | L2 · C3 | — | L1 · C4 | — | L2 · C5 | L2 · C6 | L2 · C7 |
| 合并附注 | L2 · C8 | L2 · C9 | L2 · C10 | — | L2 · C11 | — | L2 · C12 | L2 · C13 | L2 · C14 |

列汇总（达到 L4 的格数 / 适用格数）：自动取数 4/10 · 写入推送 3/9 · **逻辑校对 0/9** · **提示性规则 0/3** · **用户公式 0/6** · **跨期 0/5** · 跨表引用 1/10 · 事件刷新 1/10 · 来源展示 6/10（合计 15/72）。

## 三、关键量化（现算，禁写死）

真库 `audit_platform` 只读快照（2026-10-25）：projects 142 行（未删 85，`project_type='consolidated'` **0**）；trial_balance 743；tb_balance 117,606；tb_ledger 9,608,941；tb_aux_balance 920,715；tb_aux_ledger 18,241,580；financial_report 2,464（**仅 year=2025、7 个项目**）；disclosure_notes 1,090；working_paper 1,991；consol_trial **0**。

| 指标 | 现算值 | 取证 |
|---|---|---|
| `formula_setting`（全局 / 项目适配层） | **0 行** | `select count(*) from formula_setting` |
| `formula_template` / `_subscription` / `_version` / `formula_publish` / `formula_sync_item` | 全 **0** | 同上逐表 count |
| `report_config` 中 logic_check / reasonability 行 | **0**（318 行有公式，全是 auto_calc；`applicable_standard like 'project:%'` 0 行） | `group by report_type, formula_category` |
| 报表公式函数分布 | TB 234 · SUM_ROW 65 · ROW 15 · SUM_TB 4；**PREV / REPORT / NOTE / WP 0** | 正则数 `report_config.formula` |
| 底稿预填 `prefill_formula_mapping.json` | 306 底稿 / 1402 格：TB 604 · WP 209 · PREV 192 · ADJ 160 · LEDGER 85 · AUX 44 · LEDGER_DETAIL 35 · TB_SUM 19 · NOTE 4 · TB_AUX 2 · PLACEHOLDER 48 | 读 JSON |
| 公式推送规则 `formula_push_rules.json` | 375 条（note 193 / workpaper 182） | 读 JSON |
| `formula_push_run` / `formula_push_state` | 3 次 succeeded / 171 行（**全在和平药房一个项目**） | count + join projects |
| `wp_formula`（底稿用户公式） | 29 行、1 个项目（辽宁卫生服务，最后修改 2026-06-18），formula_source 全 `custom` | 同上 |
| 附注 `_user_formulas` / `_formulas` / `evaluated_at` | **0 / 0 / 0**（1090 条附注一条都没有） | `table_data ? '_user_formulas'` 等 |
| 附注 `_validation_rules` | 78 条，**全在和平药房一个项目** | `table_data::text like '%"_validation_rules"%'` |
| `cross_check_results` / `draft_refresh_audit(scope=formula:report-cross-check)` | **0 / 0** | count |
| `note_validation_results` | 3 行（宜宾 1、和平 2），findings 全空 | `select *` |
| `wp_qc_results` | 1 行（2026-05-15） | count |
| `qc_rule_definitions` / `gate_rule_configs` | **0 / 0** | count |
| `event_cascade_log` | 195 行，`trigger_event` 只有 `trial_balance.updated` 一种 | `group by trigger_event` |
| `trial_balance.wp_published_at` 非空（底稿发布门） | **0** | count |
| `consol_note_formula` | 51 行（soe seed）；`consol_note_data` 2 行（【UAT】合成集团母公司） | count |

## 四、证据索引（格子编号 → 证据）

### 试算表
- **T1 自动取数 L4**：`trial_balance_service`（未审数按映射聚合 tb_balance）；真库 743 行 / 7 个 2025 项目有数。
- **T2 写入推送 L4**：`TRIAL_BALANCE_UPDATED` → `formula_push/triggers.py:on_trial_balance_updated`（推底稿 / 附注）+ `event_handlers/_impl.py` 订阅 `ReportEngine.on_trial_balance_updated`（重生成报表）；真库 `formula_push_run` 中 1 次 trigger=`TRIAL_BALANCE_UPDATED`、`event_cascade_log` 195 次 completed。
- **T3 逻辑校对 L3**：`consistency_gate/_impl.py:check_tb_balance`（阻断级「试算平衡」）。回滚事务内对「重庆医药集团医疗器械」实跑：资产 2,546,171,215.70、负债 **−1,913,177,604.35**、权益 **−555,810,390.88**、差额 **5,015,159,210.93**、未通过。🔴 该检查直接 `资产 − (负债 + 权益)`，而真库 trial_balance 的符号口径**按项目不一致**（医疗器械 / 华氏 / 宜宾 / 四川物流的负债、权益为负，和平药房、安徽骨科为正），负值口径下差额被放大成两倍量级 ⇒ **假阻断**。另有 `TrialBalanceService.check_consistency`（`routers/trial_balance.py` 与签发清单调用）。不到 L4：结论不落库、口径错。
- **T4 提示性**：无。试算表没有任何 reasonability 类规则。
- **T5 用户公式 L2**：`formula_settings` 的 `tb_detail` 域（`routers/tb_detail_formulas.py`）已挂载；真库 `formula_setting` 0 行 = 无人用过。🔴 试算表页「断开公式（手动填写）」只改前端行对象 `row.formula_detached`（`views/TrialBalance.vue:onTbSumCtxDetachFormula`），后端与迁移**零引用**该字段 ⇒ 刷新即丢（代码判定，未浏览器实测）。
- **T6 跨期 L3**：`trial_balance.opening_balance` 743 行中 250 行非零；`trial_balance_full_view_service.reconcile_opening_balance` 需上年项目，真库无 2024 项目 ⇒ 期初只能来自余额表本身。
- **T7 跨表引用 L4**：`TB()` / `SUM_TB()` 被报表 238 处、底稿预填 623 格消费（见第三节）。
- **T8 事件刷新 L4**：同 T2；另 `ADJUSTMENT_APPROVED` → `adjustment_approved_recalc_handler`。
- **T9 来源展示 L4**：`views/TrialBalance.vue` 行菜单「查看公式 / 数据溯源 / 定位底稿」+ 双击穿透序时账（`onTbCellDblClick`）+ `CellFormulaDetail` 引用方弹窗。

### 四库表（余额表 / 序时账 / 辅助余额 / 辅助明细）
- **F1 余额表取数 L4**：导入管线 `ledger_import/pipeline.py` 写入 → 试算表聚合；真库 117,606 行。
- **F2 余额表推送 L4**：经试算表聚合进入报表 / 底稿（同 T1/T2）。
- **F3 逻辑校对 L2**：`import_validation_service.py` BV-01 序时账借贷平衡 / BV-02 重复凭证 / BV-03 年度一致 / BV-04 余额表期初 + 发生 = 期末，唯一调用方 `smart_import_engine.py:2974`；另 `balance_diagnostics/`。**不在校对目录里**，结果不落库（未在真库找到持久化表）。
- **F4 用户公式**：四库表本身没有公式层，只能被引用（自定义查询不算公式）。
- **F5 余额表跨期 L2**：余额表自带期初列；跨年度取上年余额表无函数。
- **F6 余额表被引用 L3**：经 trial_balance 间接被 TB() 引用。
- **F7 事件刷新 L3**：`DATA_IMPORTED` / `LEDGER_DATASET_ACTIVATED` / `ROLLED_BACK` → `_mark_workpapers_stale_all`、地址库失效、stale_engine（`event_handlers/_impl.py`）；真库 `import_event_outbox` 125、`import_event_consumptions` 422。
- **F8 来源展示 L4**：`views/LedgerPenetration.vue` 余额 → 序时 → 凭证、辅助余额 → 辅助明细逐级穿透（`drillToAuxLedgerFromBalance` 等），后端 `ledger_penetration_service.py` / `drilldown_service.py`。
- **F9 序时账取数 L3**：`LEDGER` / `LEDGER_DETAIL` / `COUNT_LEDGER`（`formula_engine._REGISTRY`，类别「底稿取数」），被 120 个预填格引用。
- **F10 推送 L2**：序时账 / 辅助余额本身不推送，只经 prefill 被底稿拉取。
- **F11 被引用 L2**：底稿预填引用（LEDGER 85 格 / AUX 44 格 / TB_AUX 2 格），报表与附注公式 0 处引用。
- **F12 辅助余额取数 L3**：`AUX` / `TB_AUX`（`_REGISTRY`），附注 `note_source_resolvers.resolve_aux_balance`。
- **F13 辅助余额校对 L1**：只有 memory 里的「校验须 GROUP BY aux_type」口径约定，未找到辅助余额 ↔ 余额表的勾稽执行器。
- **F14 辅助明细取数 L2**：没有通用公式函数（全仓 formula 引擎零引用 `TbAuxLedger`）；仅附注账龄 `AGING` / `note_source_resolvers.resolve_aux_ledger_aging` 与 `note_formula_generator._load_cross_table_data` 用到。

### 报表
- **R1 自动取数 L4**：`report_engine.generate_all_reports`；真库 financial_report 2,464 行（7 项目），`formula_used` 非空 574 行、`source_accounts` 全部有值。
- **R2 写入推送 L3**：`REPORTS_UPDATED` → `DisclosureEngine.on_reports_updated`（附注增量）/ `AuditReportService.on_reports_updated`（`event_handlers/_impl.py`）。真库没有报表 → 附注推送的独立运行记录可查。
- **R3 逻辑校对 L3**：两条独立链路——①表间审核 `formula_management/logic_check.py:_CROSS_CHECK_SEEDS` 7 条（+ `formula_settings/cross_check_rules.run_user_rules` 用户规则），入口 `GET /api/projects/{pid}/formula/report-cross-check`（`routers/formula_logic_check.py` → `cross_check_run.execute_cross_check_run`）；②报表页「审核」`routers/reports.py:consistency_check` → `report_audit_checks.run_report_audit`（内置 4 条 `ReportEngine.check_balance` + 配置里的 logic_check / reasonability 行）。回滚事务实跑：医疗器械、华氏两个真实项目表间审核 **7 条执行、6 条未通过**，6 条 issue 的 `left_value/right_value` **全是 None**（界面只能显示描述，显示不了差多少）；报表审核实跑 **4 条，全部来源「内置校验」**。真库 `cross_check_results` 0 行、run 记录 0 条 ⇒ 用户从未执行过（或执行未落库），到不了 L4。
- **R4 提示性 L2**：`report_audit_checks.AUDIT_CATEGORIES=("logic_check","reasonability")`，UI `ReportTraceDialogs.vue` 有「💡 提示性审核」页签；但真库 report_config **0 条 reasonability 公式** ⇒ 永远 0 条。表间审核的 `hints` 通道存在（`CrossCheckResult.hints`），7 条内置全是 logic_check ⇒ 实跑 hints=0。
- **R5 用户公式 L2**：报表公式编辑走 `formula_settings`（项目适配写 report_config `project:` 行）；真库 project 层 0 行、`formula_setting` 0 行。
- **R6 跨期 L2**：`financial_report.prior_period_amount` 由上年项目报表取（`prior_year_context`）；真库只有 2025 年度，2,464 行里上期非零 **20 行**；报表公式里 PREV 0 处。
- **R7 跨表引用 L3**：`REPORT()` / `ROW()` / `SUM_ROW()`；ROW/SUM_ROW 80 处在用，REPORT 在报表内 0 处、被合并附注种子 48 处引用。
- **R8 事件刷新 L3**：TB 更新 → 报表重算（T2）；调整分录 → `_mark_reports_stale_on_adjustment`；真库 `financial_report.is_stale` 8 行。表间审核**不随数据事件重跑**，只随 `FORMULA_CONFIG_CHANGED`（`formula_settings/propagation.py` 内 `execute_report_cross_checks(persist=True)`）。
- **R9 来源展示 L4**：`ReportTraceDialogs` / `ReportDrilldownDialogs` 经 `components/report/ReportDialogs.vue` 挂载，数据来自 `formula_used` + `source_accounts`。

### 附注
- **N1 自动取数 L3**：附注生成链从试算表 / 底稿取数（disclosure_engine + note_source_resolvers）。🔴 附注**公式**执行器 `note_formula_generator.execute_note_formulas` 只读顶层 `table_data.rows` 与 `_formulas`；真库 1,090 条附注里 661 条是多表 `_tables` 结构、**0 条有 `_formulas`、0 条有 `evaluated_at`** ⇒ 附注公式执行器在真库**从未写回过一个格子**。
- **N2 写入推送 L4**：`formula_push` 推附注（193 条规则）；和平药房 `formula_push_state` 171 行（auto 167 / manual 4），附注 `_source` 标记 29 条。只在一个项目闭环。
- **N3 逻辑校对 L2**：`note_validation_engine.NoteValidationEngine.validate_all`（`routers/disclosure_notes.py` 校验端点 + 生成 / 刷新后自动补跑 `note_readiness_service`）。规则来源只有两路：附注里的 `_validation_rules`（`PRESET_TO_RULE` 11 种中文枚举派发）与 `基础数据/附注模版/{国企,上市}版校验公式预设.md`——**这两个 md 在仓库里不存在**（`Test-Path` 均 False）。实跑：医疗器械、华氏 **total_rules = 0**；和平药房（唯一带 `_validation_rules` 的项目）319 条全过。⇒ 7 个真实项目里 6 个附注校验是空转。
- **N4 提示性 L1**：附注预置 reasonability 140 条（soe 70 + listed 70）全是自然语言（例：F4-15「需调用LLM判断是否为公司全称」）；`NoteValidationEngine._finding_from_result` 的严重度只按 `|diff|>0.01 → error 否则 warning` 判，不读规则类别 ⇒ 平台不存在「附注提示性规则」的执行语义。
- **N5 用户公式 L1**：`NoteFormulaDialog.vue` 有 ⚡/🔍/💡 三个页签，保存走 `PUT /api/disclosure-notes/{pid}/{year}/{section}/formulas` → `formula_settings.note_settings`。🔴 **执行器忽略 `category`**：`_user_formula_to_def` 把类别带进 dict，但 `execute_note_formulas` 对所有公式一律求值并 `values[col_idx] = float(calc_value)` 回写。纯函数实测：`_exec_generic("cell(2,0) = cell(0,0) + cell(1,0)", rows, {})` 返回 **300.0**（期望勾稽 150 = 100 + 50，却把三格之和写进合计格）；非 cell 文本返回 **0.0**（同样会写回 0）。真库 `_user_formulas` 0 条 ⇒ 尚未造成数据损坏，但一旦用户在 🔍 页签保存一条勾稽就会改数。
- **N6 跨期 L2**：`PREV/PRIOR` 2/3 参数 + `_index_prior_dynamic_rows` + `validate_all` 装配 `prior_note_data`；真库无 2024 附注 ⇒ 永远取空。
- **N7 跨表引用 L3**：`NOTE()` 被底稿预填 4 格引用；附注引用 TB / REPORT 经 `_resolve_cross_refs_via_acnr`；保存前 `_dangling_note_formula_refs` 悬空校验。
- **N8 事件刷新 L3**：`REPORTS_UPDATED` → 附注增量；`WORKPAPER_SAVED` → `_refresh_note_from_disclosure` / `_mark_disclosure_stale`；真库 `is_stale` 227 条。
- **N9 来源展示 L3**：`NoteSourceBadge` / `CellTraceDialog` / `TraceSourcePopover` 挂在 `views/DisclosureEditor.vue`；`NoteCellSourceDrawer.vue` **0 处挂载**。

### 底稿
- **W1 自动取数 L4**：`prefill_engine` + `prefill_formula_mapping.json`（306 底稿 / 1402 格）；真库 `working_paper.prefill_stale` 190 张。
- **W2 写入推送 L2**：审定数发布门 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`；真库 `trial_balance.wp_published_at` 非空 **0** ⇒ 从未有人发布。底稿 → 附注走 `buildXSyncPayload` 前端推送（见 memory 体检，不重复取证）。
- **W3 逻辑校对 L3**：①跨科目 `wp_cross_check_service.CrossCheckService`（`cross_account_rules.json` 8 条 XR + 项目自定义）实跑医疗器械：**8 条执行，6 skip（数据不足）/ 1 fail / 1 pass**；②一致性门禁 `ConsistencyGate.run_all_checks` 实跑：40 项，循环勾稽 32 项**全部「数据不完整 / 未保存，跳过」且 `passed=True`**；③质控 `QCEngine.check` 实跑一张底稿：5 条发现（blocking 4 / info 1）；④前端循环引擎（`useXxFormulaEngine.ts` / `xxDisclosureConsistency.ts`）浏览器内执行，不落库。真库 `cross_check_results` 0、`wp_qc_results` 仅 1 行（2026-05）。
- **W4 提示性 L2**：XR 与循环规则有 `warning`，QC 有 `info`；`ConsistencyGatePanel.vue` 有「阻断 / 警告」两色，但它**只取 `check_name.startsWith('D4勾稽')` 的 4 条**，其余 36 项门禁结果无专门展示组件（只进签发 / 导出包聚合）。
- **W5 用户公式 L3**：`wp_formula`（`routers/wp_user_formulas.py` / `wp_user_formulas_v2.py`）真库 29 行（1 项目，18 条含 `WP()`）；`WORKPAPER_SAVED` → `_on_workpaper_saved_wp_formula_stale` 标引用方过期。
- **W6 跨期 L2**：预填 PREV 192 格 + 三参 PREV 定位表；真库无上年项目 ⇒ 运行时只能报「取不到上年」。
- **W7 跨表引用 L3**：`WP()` 预填 209 格 + 用户公式 18 条；`cross_wp_references.json` 425 条关系供依赖图 / 过期传播。
- **W8 事件刷新 L3**：`WORKPAPER_SAVED` 订阅 ≥15 个处理器（`event_handlers/_impl.py`、`event_handlers_cycle_linkage.py`、`formula_push/triggers.py`、`acnr/events.py` 等）。
- **W9 来源展示 L2**：`WpFourTableSourcePanel` 56 处挂载（四表来源）；但单元格级公式来源 `GtFormulaSourceTooltip` 只挂在 D3、S34 两个组件，`CellProvenanceTooltip.vue` **0 处挂载**。

### 合并报表 / 合并附注
- 真库 `project_type='consolidated'` **0**、`consol_trial` **0**、`consol_worksheet_data` 1、`elimination_entries` 2、`consol_note_data` 2（均为【UAT】合成集团）⇒ **整组最高 L2**，不存在 L3 证据。
- **C1~C7 合并报表**：取数 / 线性分解 `consol_report_values.py`（`RowValue` 内核）；推送 `consol_push_run`（0 行）；校对 `routers/consol_trial.py:/consistency-check`；用户公式无独立层（L1）；引用经差额表与 `REPORT()`；事件 `consol_trial_stale_handler`（订阅 `TRIAL_BALANCE_UPDATED`）；来源 `ConsolBreakdownDialog`（`ReportDialogs.vue` 挂载）/ `ConsolReportBreakdownView`（`ConsolidationIndex.vue`）。
- **C8~C14 合并附注**：取数 `consol_note_standalone_reader` + 子树重新汇总；推送 `consol_note_template_push_log`（0 行）；校对 `note_check_rules.load_all_check_rules` 实载 **soe 34 + listed 36 = 70** 条（`ConsolNoteTab.vue` 的 checkRules 调 `routers/consol_note_sections.py:get_check_rules`），但无合并项目 ⇒ 从未对真实集团执行；用户公式 `consol_note_formula` 51 行全是 seed；事件 `consol_note_stale_handler`（`NOTE_UPDATED` + `NOTE_SECTION_SAVED`）。

## 五、校对目录 1603 项的执行量化

取证：`app.services.formula_check_catalog.load_source` 在真库会话里逐来源加载（合计 **1603**，与 `GET /api/formula-catalog/check-rules` 同一函数）；「有执行器」= 现读执行代码确认会按该规则求值；「实跑」= 回滚事务内对真实项目（医疗器械 5e193c68 / 华氏 005a6f2d）调用生产执行器；「落库」= 真库运行痕迹。

| 来源 key | 目录条数 | 严重度分布（目录 severity 字段） | 有执行器 | 真实项目实跑 | 真库落库 | 未执行 |
|---|---|---|---|---|---|---|
| report_builtin 报表勾稽（内置） | 7 | logic_check 7 | 7 | **7 执行 / 6 未通过**（两个项目一致） | 0（`cross_check_results` 0） | 0 |
| cross_check_global 表间审核全局层 | 0 | — | — | — | — | 0 |
| cross_check_preset 表间审核预置 | 6 | logic_check 6 | 0（只是「从预置选用」的模板，选用后才成为用户规则） | 0 | 0 | **6** |
| report_audit 报表审核公式 | 0 | — | — | — | — | 0 |
| consol_note_checks 合并附注勾稽 | 70 | logic_check 70 | 70 | 0（0 个合并项目） | 0 | 0（L2 空转） |
| note_preset_checks 附注预置勾稽 / 提醒 | 932 | logic_check 792 · reasonability 140 | **≤72**（前端循环引擎 / 章节映射里按编号引用到的上限：soe 36 + listed 36，含仅注释引用） | 浏览器内，不可从库验证 | 0 | **≥860** |
| note_disclosure_balance 附注披露平衡 | 6 | blocking 4 · warning 2 | 0（`NoteDisclosureBalanceService` 全仓无调用方） | 0 | 0 | **6** |
| wp_cross_account 底稿跨科目 | 8 | blocking 6 · warning 2 | 8 | **8 执行：skip 6 / fail 1 / pass 1** | 0 | 0 |
| cycle_validation 循环校验 | 114 | blocking 64 · warning 50 | **32**（F/G/H/I/J/K/L/M/N 全部 28 + D 的 DV-022~025 共 4，由 `consistency_gate` 手写实现；JSON 本身不被门禁读取） | 32 执行，**32 全部「跳过」且 passed=True** | 0（门禁不落库） | **82** |
| a17_consistency A17 跨章节 | 8 | warning 5 · error 3 | 8（`a17_consistency_checker.check_consistency`，A17 汇总端点 + Word 导出） | 未实跑（需章节正文） | 0 | 0 |
| qc_rules 质控 | 27 | blocking 14 · warning 11 · info 2 | **22**（QC-01~14 在 `QCEngine`；QC-19~26 在 `gate_rules_phase14`） | QCEngine 一张底稿实跑 5 条发现 | `wp_qc_results` 1 行（2026-05） | **5**（AL-01~05：`qc_audit_log_compliance` 只执行 `qc_rule_definitions` 表里 enabled 的 audit_log 规则，该表 0 行） |
| cross_wp_references 跨底稿引用 | 425 | （空） | 不是校对规则，被依赖图 / 过期传播消费 | — | — | 不计 |
| **合计** | **1603**（校对类 1178） | | **≤219（18.6%）** | **非跳过结论 ≈23（2.0%）**：报表 7 + XR 2 + QC-01~14 共 14 条（`QCEngine` 另有 QC-15~18 / 27 / 28 共 6 条不在目录） | 仅 QC 1 次（其余 0） | **≥959（81.4%）** |

未执行清单（按来源）：
- **note_preset_checks ≥860 条**：932 条 logic_check / reasonability **100% 自然语言**（正则 `cell\(|TB\(|REPORT\(|NOTE\(|WP\(|SUM\(` 命中 0；soe 387 + 70、listed 405 + 70）。目录 `runs_in` 写「导入为附注公式后执行」，但导入后由 N5 所述执行器当取数公式求值——**导入比不导入更糟**（会把 0.0 写回单元格）。前端已人工移植的只有 D1 / E1 / F1 / F2 等少数循环（引用上限 72 条）。
- **cycle_validation 82 条**：BCAS-VR-01~25（25）、DV-001~021（21）、DV-101~136（36）只在 `routers/wp_step_mapping.py` 作「底稿校验规则展示」与 `routers/vr_coverage.py` 统计覆盖度（按 JSON 条数算「达标」⇒ **覆盖度看板把未实现的规则算作已覆盖**）。
- **note_disclosure_balance 6 条**：ar / fa / rp 的期末、期初勾稽，服务类存在但无调用方（目录自己也写明）。
- **cross_check_preset 6 条**：模板；`formula_setting` 0 行 ⇒ 无人选用过。
- **qc AL-01~05 5 条**：依赖 `qc_rule_definitions` 登记，表为空 ⇒ 永不执行（而 python 规则在空表时「全部启用」，两套启停语义相反，见 `qc_engine.py` `_get_enabled_rule_ids` 注释）。

目录外的执行器（目录看不见，形成「执行了但没登记」的反向盲区）：一致性门禁里的非 VR 检查 8 项（试算平衡 / 报表平衡 / 利润表勾稽 / 附注完整性 / 数据新鲜度 / E1↔CFS×2 / E1↔TB）· `report_audit_checks` 内置 4 项 · `note_validation_engine.PRESET_TO_RULE` 11 种派发（和平药房实例化 319 条）· `import_validation_service` BV-01~04 · `gate_rules_phase14` 的 CONSISTENCY-BLOCK / GATE-MISSTATEMENT / 独立性声明 · 前端 `*DisclosureConsistency.ts` 自带规则 · `b60_plan_service` QcFinding · `consistency_replay_engine` / `cross_cycle_breakage_service`。

## 六、提示性（不阻断）与阻断性：语义与 UI 是否区分

结论：**部分区分，且口径互相矛盾**。逐条证据：

1. **目录层把两个维度混在一列**：`formula_check_catalog._SEVERITY_LABEL` 同时收 `blocking/error/warning/info`（严重度）与 `logic_check/reasonability`（公式类别）。1603 项按该列分布：logic_check 875 · reasonability 140 · blocking 88 · warning 70 · error 3 · info 2 · 空 425 ⇒ **1015 条（报表 / 附注 / 合并附注）没有严重度，只有类别**；用户无法从目录判断哪条会挡签字。
2. **表间审核用户规则没有严重度字段**：`formula_settings/cross_check_rules.py` 定义只有 label / left_ref / operator / right_ref / tolerance（全文 grep `severity|hint|blocking` 0 命中）⇒ 用户新增的每条规则都是 issue，不能声明「只提示」。内置 7 条里「有效税率 ≈ 25%」「货币资金 ≥ 0」本是合理性判断，却登记为 logic_check，实跑时作为 issue 计入未通过；`CrossCheckResult.hints` 通道存在但内置规则从不产出 ⇒ 实跑 hints = 0。
3. **报表审核把提示算成失败**：`routers/reports.py:consistency_check` 的 `consistent = all(c["passed"] for c in checks)` 不分类别；前端 `ReportTraceDialogs.vue` 第 21 行「未通过」= `total − logic_passed − reasonability_passed` ⇒ 提示性审核没过也计入「未通过」。页签上虽有「🔍 逻辑审核 / 💡 提示性审核」两栏，但总状态不区分。
4. **阻断级规则缺数即放行**：`consistency_gate` 源码 `passed=True` 82 处 / `passed=False` 3 处 / 「跳过」46 处；实跑 40 项中 32 项（全部循环 VR 勾稽）文案为「数据不完整 / 未保存，跳过」且 `passed=True`，其中 **21 项 severity=blocking**。签字门禁（`gate_rules_chain.py` 调 `run_all_checks`）看到的是「通过」。`gate_rules_phase14` 各规则异常时 `return None`（= 不报 = 放行）。
5. **门禁 UI 只为 D4 区分**：`ConsistencyGatePanel.vue` 有「阻断 / 警告」标签与「存在阻断级差异，无法签字确认」横幅，但过滤 `check_name.startsWith('D4勾稽')`，且未取到数据时自行补 4 条 `passed: true`「数据不完整，跳过检查」（第 106~109 行）——UI 层再一次把「没查」显示为通过。
6. **跨科目 XR 区分到位但「跳过」不计入**：`CrossCheckPanel.vue` 按规则 severity 着色（blocking 红 / warning 黄），状态区分 pass / fail / skip / error；`check_for_sign_off` 签字门禁只看 blocking 失败 ⇒ 实跑 6/8 skip 时签字照样放行。
7. **附注校验严重度与规则无关**：`note_validation_engine._finding_from_result` 只按差额 > 0.01 定 error、否则 warning；附注预置 140 条 reasonability 没有执行路径；附注公式执行器忽略 category（N5）⇒ 附注域**不存在**提示性规则语义。
8. **编辑端有区分、执行端不认**：`GtFormulaEditDialog.vue` 写明「logic_check 不通过时产出问题清单，绝不修改任何数据值 / reasonability 触发条件成立时产出提醒」，并要求填 `issue_description` / `hint_text`；`FormulaDefinitionEditDialog.vue`、`NoteFormulaDialog.vue`、`StructureEditor.vue` 都有三类选项。但报表执行端只有 `report_audit_checks` 认类别，附注执行端完全不认 ⇒ **编辑界面承诺的语义在附注上是假的**。

## 七、最大缺口（按影响排序）与本次未能验证的部分

1. **附注校对 / 提示两列整列空转，且用户勾稽公式会改数**（N3/N4/N5）：预置 932 条不可执行、校验预设 md 缺失、6/7 个真实项目附注校验 0 条规则、执行器不分类别回写。这是「公式贯通」最薄的一段。
2. **门禁「缺数 = 通过」+ 试算平衡符号口径错**（T3、第六节 4~6）：签字前最后一道公式校验在真实项目上要么假通过（32/40 跳过），要么假阻断（差额 50.15 亿）。
3. **合并报表 / 合并附注零真实运行**（C1~C14）：代码最全的一组，没有一条 L3 证据。
4. **跨期 PREV 无法闭环**（T6/R6/N6/W6）：只有 2025 年度数据；预填 192 格 PREV、报表上期列、附注上年均取不到。
5. **全局 / 项目适配 / 模板三层在真库零数据**：`formula_setting`、`formula_template*`、`formula_publish`、`formula_sync_item` 全 0 ⇒「一处改全处生效 + 冲突弹窗」没有任何一次真实发生过（矩阵「用户公式」列 0/6 到 L4 的直接原因）。
6. **来源展示在单元格级断层**：底稿 `CellProvenanceTooltip`、附注 `NoteCellSourceDrawer` 0 处挂载；`GtFormulaSourceTooltip` 只在 2 个底稿组件。
7. **校对结论不落库**：表间审核、XR、门禁在真库都没有任何结论行，复核 / 归档 / 质量评分读不到历史。

未能验证（如实标注）：前端各循环引擎（`useXxFormulaEngine.ts`）只在浏览器执行，本次未开浏览器，「≤72」是静态引用上限；A17 8 条未实跑；报表 → 附注推送、合并链路没有真实数据可跑；表间审核 6/7 未通过是真实差异还是报表行映射问题（issue 的左右值全是 None）未继续追查；试算表「断开公式」不持久是代码判定、未浏览器复现。
