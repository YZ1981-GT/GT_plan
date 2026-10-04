# 设计：公式推送引擎 + E1 货币资金全链 canary

## 一、设计原则

1. **一个单元格只有一个写入方**。E1 的每个持久化键按归属分三类（§四），前端与后端不抢写。
2. **复用而不新造**：求值走 `formula_engine.execute`（L1 单内核）；四表取数直接调用 E1 渲染策略已有的
   纯函数（`build_e1_slot_leaves` / `build_e1_detail_rows`）；底稿写入复用并修好
   `formula_runtime.adapters.workpaper.WorkpaperMutationAdapter`；地址沿用 ACNR 底稿域 addr_id。
3. **前后端同式、双侧夹具守卫**：后端派生算式与前端 composable 逐式一致，由同一份 JSON 夹具在
   vitest（真 composable 产出）与 pytest（后端产出）两侧同时断言，任一侧改算式另一侧必红。
4. **不静默**：保留、跳过、并发冲突、陈旧试算表都进运行记录与公式管理面板，不只写日志。
5. **canary 先行**：本 spec 只接 E1；引擎按 `wp_code → binding` 注册，后续循环各加一个 binding。

## 二、总体数据流

```
四表入库 ──► TB 重算 ─┐
调整审批 ──► TB 重算 ─┼─► TRIAL_BALANCE_UPDATED ─┐
E1 底稿保存 ─────────┴─► WORKPAPER_SAVED(E1) ────┼─► FormulaPushEngine.run(project, year, trigger)
公式管理「立即推送」────────────────────────────────┘        │
                                                             ├─ S 源值：四表明细行 / 试算表审定数 / 大厅已确认 AJE
                                                             ├─ D 派生：跨表汇总键 / 审定合计 / 语义槽
                                                             ├─ N 附注：按 template_type 选 五、1 / 八、1 主表
                                                             ├─ 三态判定 → 写入（CAS）→ formula_push_state
                                                             └─ formula_push_run + SSE formula.pushed
```

报表审定数、试算表调整列、调整分录大厅三段已由既有链路负责（阶段一 R3 + 审批重算 handler），本引擎不重复写。

## 三、推送规则清单（公式管理可见）

`backend/data/formula_push_rules.json`，每条：

| 字段 | 含义 |
|---|---|
| `rule_id` | 稳定 id，如 `E1.tb_amount.ending` |
| `page_key` | 预设库页键 `workpaper:E1`（公式管理按页展示） |
| `stage` | `source` / `derived` / `note` |
| `policy` | `system` / `derived` / `editable`（§五） |
| `target` | `{domain, item_id | section, selector?, fields?}` |
| `source` | `{kind: formula, context, expression}` 或 `{kind: four_table_leaves, slots, formula_text}` 或 `{kind: derivation, name, params, formula_text}`（`context` 声明取数口径：`tb=trial_balance` / `adj=hall_approved_excluding_workpaper`） |
| `triggers` | `TRIAL_BALANCE_UPDATED` / `WORKPAPER_SAVED` / `manual` |
| `description` | 中文说明（面板显示） |

守卫（`rules.py` 加载即校验，测试钉死）：`formula` 表达式经 `validate_formula` 合法且空上下文试算无错；
**禁用列名 `审定数` / `未审数`**（内核别名把它们与 `期末余额` 折叠为同一键，F-内核事实）；`TB()` 须显式列名；
`policy ∈ 三类` 且与 `stage` 搭配合法；`rule_id` 唯一；两条规则不得写同一目标；每条含 `manual` 触发；
说明文字须中文。任一条不合法整份拒收（不跳过坏规则继续跑，否则那条推送静默消失）。

实施现状（任务 6）：E1 共 30 条 = 源值 7（四表明细行 2 / 试算平衡表数 2 / 大厅调整 3）+ 派生 22 + 附注 1。

## 四、E1 键归属与规则

| 键 / 目标 | 归属 | 规则来源 |
|---|---|---|
| `E1-cash-detail-rows[id].{opening,increase,decrease}`（种子行） | 可编辑（三态） | 四表叶子 `cash` 槽 |
| `E1-bank-detail-rows[id].{opening,increase,decrease}`（`-ft-` 行） | 可编辑（三态） | 四表叶子 `bank`→institution、`other`→other |
| `E1-cash-detail-{opening,total}-unaudited` | 派生 | 行存在：Σ期初 / Σ(期初+增−减)×汇率；行不存在：叶子期初/期末合计 |
| `E1-bank-detail-{principal,institution,finance,other}-{opening,total}-unaudited` | 派生 | 行存在：按 `E1-bank-variant` 复刻 `recalcRow` 后分组求和，principal=institution+finance；行不存在：叶子合计 |
| `E1-adj-tb-amount-ending` | 系统 | `Σ TB(c,'期末余额')`，上下文 `tb=trial_balance_audited`（期末余额 = 持久化审定数，按标准码前缀含子级，与报表同源），c∈{1001,1002,1012}（见 ADR-PUSH-002 修订 / 修订二） |
| `E1-adj-tb-amount-opening` | 系统 | `Σ TB(c,'年初余额')`（同上下文，取 `opening_balance`） |
| `E1-hall-adj-{cash,bank_principal,other_mf}-ending` | 系统 | `ADJ(c,'aje_net')`，上下文=大厅已批准且 `origin≠workpaper` |
| `E1-adj-total-{1001,1002,1012}[-opening]` | 派生 | 复刻 `aggregateAuditedByCode`（未审 + E1-5 本地调整 + 大厅已确认调整，后者仅期末） |
| `E1-adj-slot-{finance_co,digital,accrued}[-opening]` | 派生 | 复刻 `buildE1MainRowSlotWrites`（三值全 0 不写） |
| 附注 `五、1`/`八、1` 主表 `货币资金` 行 × 期末/期初 | 附注三态 | 复刻披露主表取数（扣减映射同 `e1MainRowPrefill`） |

前端改动（与上表配套）：

- `getAdjustment(itemKey,'ending')` = E1-5 本地 + `E1-hall-adj-{itemKey}-ending`（新纯函数 `e1AdjustmentFor`，宿主告警/种子同用）。
- 宿主 `seedAdjTotalsFromAggregates` 改为**总是派生**（不再「键已存在就跳过」），消除陈旧审定合计回放。
- `flushSave` 过滤后端独占键（谓词 `isE1BackendOwnedKey`：`E1-adj-tb-amount-*`、`E1-adj-total-*`、`E1-adj-slot-*`），
  用户可编辑的 `E1-adj-{itemKey}-{field}` / `-note` 照常保存。
- 披露主表取数抽成纯函数 `computeE1DisclosureMainRows(variant, getter, openingMap)`，组件与夹具共用。

## 五、三态判定（纯函数 `policy.decide`）

| 策略 | 条件 | 动作 | 新状态 |
|---|---|---|---|
| system / derived | 当前 = 公式值（含两者皆空） | unchanged | auto |
| system / derived | 当前 ≠ 公式值（公式值为空 ⇒ 写空，如语义槽三值全 0） | write | auto |
| editable | 状态 = locked | keep_locked（记差异） | locked |
| editable | 当前 = 公式值 | unchanged | auto |
| editable | 当前为空 | write | auto |
| editable | 有上次推送值且 当前 = 上次推送值 | write | auto |
| editable | 有上次推送值且 当前 ≠ 上次推送值 | keep_manual（记差异） | manual |
| editable | 无上次推送值（首次）且 当前 ≠ 公式值 | keep_pending（记差异） | pending_confirm |

数值比较容差 0.005（与 `e1AdjudicationPrefill.TOLERANCE` 同口径：前端冲突 = `abs(差) > 0.005`，
故相等 = `abs(差) <= 0.005`）；「空」= `None` / 空白串（`0` 不是空，同前端 `isBlank`）；非数值按同类型全等。
`unchanged` 同样把上次推送值记为公式值（当前已与公式一致，等同刚推送过；否则公式后续变化时旧的上次推送值
会把这个一致值误判为人工改动）；`keep_*` 一律不动上次推送值。可编辑目标公式值为空（来源缺失）由调用方跳过，
不交给判定。
「采用公式值」= 以本次**重新算出**的公式值写入并置 auto（不用 `last_formula_value`：它是上次运行的值，可能已过时）；
「锁定」置 locked；「解锁」置 pending_confirm（下次重判）。

附注单元格：`_manual_override=True` → 整节 keep_locked；`_cell_modes[col] ∈ {manual,locked}` → keep；
其余**跟随公式值**（与「同步到附注」同效，不按推送状态表的上次推送值判 —— 实施裁定见 §十一·补2，
初稿「按 editable 规则判」已否决：真库 F2 章节首推会整表变待确认）。只认 `_source ∈ {workpaper, workpaper_html}`
的章节；F1 章节跳过，报告「由模板取数维护」。

## 六、存储（V169 + R169，运行时迁移）

> 勘误：初稿写 V167；实施时现算最高号，V167 / V168 已被并行工作占用（合并树三码自建 / knowledge_doc 枚举补回），
> 故用 V169。列 `trigger` 改名 `trigger_source`（避开 SQL 关键字，裸 SQL 不必加引号）。

```sql
formula_push_state(id, project_id, year, addr_id, UNIQUE(project_id, year, addr_id), rule_id, domain, wp_id, note_section,
                   last_pushed_value JSONB, last_formula_value JSONB, current_value JSONB,
                   state VARCHAR(20) DEFAULT 'auto' CHECK(auto/manual/locked/pending_confirm),
                   last_run_id → formula_push_run ON DELETE SET NULL, updated_at, updated_by)
formula_push_run(id, project_id, year, trigger_source, triggered_by, status CHECK(running/succeeded/partial/failed),
                 written_count, unchanged_count, kept_count, skipped_count,
                 detail JSONB, started_at, finished_at)
```

两表 `project_id → projects ON DELETE CASCADE`；state 的 `wp_id → working_paper ON DELETE CASCADE`。
`dry_run` 在事务内执行后整体回滚，不留运行记录。

不复用 `draft_marker`：它无「上次推送值」列，三态判据无从落地；不复用 `draft_refresh_audit`：
`operator_id NOT NULL` + 指纹幂等会让同指纹的第二次推送被短路。

addr_id：底稿域 `E1/{sheet_code}/{item_id}` 或 `E1/{sheet_code}/{item_id}[{row_id}].{field}`；
附注域 `note://{section}/货币资金/{row_label}.{end|prior}`（ACNR 非底稿域前缀形态）。

## 七、写入

- **底稿**：修复 `WorkpaperMutationAdapter`（UPSERT 补 `project_id`、`content_version+1`、时间戳用 datetime
  而非 isoformat 字符串——asyncpg 对 `timestamptz` 严格拒收 str）。引擎按条目整体写（适配器 `@raw` 模式：
  叠加层里的行 JSON 原样落库），一个条目一次 CAS，避免同条目多字段逐次写导致第二次 CAS 自冲突。
  CAS 期望版本取**读快照时**的版本（不在写前重读），整张底稿一个保存点：任一条目冲突 ⇒ 该底稿全部条目回滚、
  附注不推、运行状态 partial（见 §十一·补2）。
- **冻结**：只看 `working_paper.status ∈ {review_passed, archived, review_level1_passed, review_level2_passed}`
  ⇒ 整张底稿跳过（`review_status` 的 `levelN_passed` 是流程中间态，不作冻结判据；见 §十一·补2）。
- **附注**：ORM 读 `DisclosureNote`（PG 下 `FOR UPDATE`），按 F2（`end_amount/prior_amount`）或
  F3（`values[i]`，列序取 `_sub_table_columns`）写目标行；合计行 = 合计行之前非合计行之和；
  不建行、不改标签、不动叙述与受限资金表；写后记 `last_sync_source='formula_push'`、`last_sync_wp_id`、`last_sync_at`。
- **并发**：同进程按 (project, year) 串行；PG 另加 `pg_advisory_xact_lock`。

## 八、触发与防回环

- 订阅 `TRIAL_BALANCE_UPDATED`：`account_codes` 为空或与 {1001,1002,1012} 相交才跑 E1。
- 订阅 `WORKPAPER_SAVED`：`extra.wp_code == 'E1'` 才跑，且只跑该 wp。
- 引擎写入**不发布** `WORKPAPER_SAVED`，只 `broadcast_raw('formula.pushed')`；handler 独立会话、失败记
  stale-degraded 不冒泡。
- 注册点：`main._register_phase_handlers`（与审批重算 handler 同处）。

## 九、接口（`/api/projects/{project_id}/formula-push`，登记 `router_registry/report.py`）

| 方法 | 路径 | 权限 | 作用 |
|---|---|---|---|
| GET | `/rules?wp_code=E1` | readonly | 规则清单 |
| POST | `/run` | edit | 立即推送（`dry_run` 可试跑，事务回滚） |
| GET | `/latest?year=` | readonly | 最近一次运行 + 状态计数 |
| GET | `/states?year=&state=` | readonly | 目标级状态（当前值 / 公式值 / 差异） |
| POST | `/states/adopt` | edit | 采用公式值 |
| POST | `/states/lock` | edit | 锁定 / 解锁 |

## 十、ADR

- **ADR-PUSH-001 调整分录进审定表的口径**：E1-5 仍是「账项调整」本地写入方；大厅已批准且非底稿来源的
  AJE 另存 `E1-hall-adj-*`，审定表按主行相加。否决「大厅全部已批准分录直接替换本地调整」——底稿来源分录
  （`origin=workpaper`，由 E1-5 汇入大厅）会被计两次；否决「写回 E1-5 行」——会被再次汇入大厅形成回环。
  RJE 不进 E1-1：模板只有「账项调整」一列（F3），与 E1-5 只归集 `category=账项调整` 一致。
- **ADR-PUSH-002 试算平衡表数取审定数**：模板差异数在审定列（F3）。现渲染种子（叶子未审）保留为
  「尚未推送过」时的兜底，首推后以后端值为准。陈旧试算表（F10）会在差异数行如实暴露，不做遮掩。
  - **修订（任务 7 实施时）**：审定数取 `trial_balance.audited_amount` 持久化列（上下文
    `tb=trial_balance_audited`，与报表引擎审定模式 `_COLUMN_MAP` 同口径：`TB(c,'期末余额')`=审定数），
    **不**用「未审数 + AJE调整 + RJE调整」现算。实证：试算表 AJE 列按 V124 **排除** `origin=workpaper`
    分录（它们只经审定表发布门写进 `audited_amount`），现算会让 E1-5 录入的调整永远显示为差异；取持久化
    列则「未发布 → 显示差异提示发布；发布后 → 与报表一致」，正是该行的核对意义。试算表该年度无任何行 ⇒
    跳过并注明「试算表尚未生成」，不写 0。
  - **修订二（任务 16 真库试跑时）**：试算表与大厅调整都按**标准码前缀**汇总（科目及其子级标准码），与报表
    `ReportFormulaParser._get_tb_rows_prefix`（`LIKE 'code%'`）逐值同口径。实证：真库和平药房_2024 客户
    `1012.02` / `1012.03` 映射到子级标准码 `101202` / `101203`，试算表 `1012` 本行为 0、子级合计 52,475,713.77；
    首版按本码精确取数得试算平衡表数 848,871.86，而报表货币资金与 E1 审定合计都是 53,324,585.63 ⇒ 审定表凭空
    多出 5,247 万的差异。大厅调整同理（记到 `101202` 的 AJE 被报表 `TB('1012')` 计入）。守卫
    `test_tb_context_matches_report_engine_including_sub_level_codes`（与 `ReportFormulaParser` 逐值相等 + `1003`
    不被 `1001` 吞；变异 3/3 红）。
- **ADR-PUSH-003 附注准则按 `template_type`**：与附注模块渲染同一权威，推送即所见；与
  `applicable_standard_v2` 不一致时运行记录给 warning（F11），不猜。
- **ADR-PUSH-004 不建行不建节**：种子口径（账户级 / 叶子级）与章节结构分别归前端与附注生成，后端只刷新已存在的目标。

## 十一·补、E1 binding 实施裁定（任务 7~9）

- **只推四表带入的行**：后端按宿主同口径（账户级优先、叶子兜底）算出种子行 id，**只**推送 id 命中已保存行的
  行；用户自加行不动；种子行不在表里 ⇒ 跳过并提示「在底稿『重新取数』后纳入」。
- **默认占位行视为空**：`fixed-rmb` 且四个金额全 0、备注为空 = composable `createDefaultRmbRow` 的占位，
  金额按「空」判 ⇒ 首推直接写入（否则每个「先打开底稿、后导入四表」的项目首推都卡在待确认）。有备注即视为用户数据。
- **E1-3 多币种**：`rmb` 版与本位币恒等行推本位币三列；原币权威且本位币、汇率 1 的行推原币三列并**镜像**本位币列；
  外币行（原币 × 汇率派生，四表只有本位币金额）不推并注明原因；应计利息段不推。variant 未保存时按宿主缺省
  `multi` 计算并在运行记录给告警。
- **派生「目标应为空」**：语义槽三值全 0 ⇒ 写空串（清掉陈旧值），不写 0（Property 35：「无此科目」≠「余额为 0」）。
- **取数严格**：`_build_four_table_extraction` / `fetch_tb_subtree` / `fetch_e1_bank_accounts` / `_fetch_currency_map` /
  `_build_account_prefill` 新增 `strict` 关键字参数（缺省 False，render 行为逐字不变）；引擎一律 `strict=True`，
  失败上抛整次推送判失败 —— fail-open 的空结果与「本项目无该科目」不可区分，拿它推送会把真实金额刷成 0。
- **前后端同式**：`e1_calc`（后端）↔ `useE1CashDetail` / `useE1BankDetail` / `useE1Adjudication` /
  `buildE1MainRowSlotWrites` / `computeE1DisclosureMainRows`（前端）；夹具 `backend/tests/fixtures/formula_push_e1_parity.json`
  由 vitest 用真 composable 产出。前端为此新增 `e1AdjustmentFor`（本地 + 大厅，接入 `useE1Adjudication.getAdjustment`）、
  抽出 `computeE1DisclosureMainRows`（`E1TabDisclosure` 改为调用它，行为不变）。
- **已发现的前端第二口径（任务 13 收口）**：宿主 `reconcileCashAggregateFromRows` 用 `num(fxRate) || 1`，与 composable
  `parseNum(fxRate)`（外币待录入保持 0）不一致；后端派生按 composable 口径，宿主该处须对齐，否则两写入方来回覆盖。

## 十一·补2、引擎实施裁定（任务 10）

- **附注单元格以附注自身标记为准，不用推送状态判人工**（修订 §五 附注段）：底稿来源章节（`_source=workpaper`）的
  `sub_table_data` 只有「同步到附注」类写入方 —— 附注编辑器保存落在 `_tables`，读时投影每次从 `sub_table_data`
  重建 `_tables`（`get_note_detail`），`sub_table_data` 里不存在未带标记的人工值。故无 `_cell_modes` / `_manual_override`
  标记即跟随（与点「同步到附注」同效，需求 3.5「底稿同步写入不视为人工修改」）；否决按「上次推送值」判：真库 F2
  章节全是前端同步产物，首推会整表变「待确认」。面板对附注目标**不提供**采用 / 锁定（否则两处各有一套「人工」口径，
  且面板锁定会在用户去掉附注标记后冒充标记继续挡住推送）。
- **读写口径对齐投影器**：只认 `_source ∈ {workpaper, workpaper_html}`（投影器只对这两种来源渲染 `sub_table_data`，
  其余来源写了也看不见）；行里已有业务键优先于 `values[i]`（投影器逆投影「已存在的业务键不被覆盖」）；标签列 =
  首个 `is_label` 否则首列（`_pick_label_def`）。
- **底稿冻结只看 `working_paper.status`**（修订 §七「或 review_status 为复核通过态」）：与平台编辑锁同口径
  （wopi / wp_sync_router：`review_passed` / `archived` 只读）+ 旧值 `review_level{1,2}_passed`。`review_status`
  的 `levelN_passed` 是逐级中间态（下一步即 `pending_level{N+1}`），不是整张底稿通过；`pm_service` 批量通过也写 `status`。
- **整张底稿一个保存点**：任一条目 CAS 冲突 ⇒ 回滚整张底稿、附注本次不推、记「并发修改」（修订「该条目跳过」）。
  派生值与附注都依赖本底稿已落库的值，只写一部分会让汇总键与明细不一致。
- **只作用于项目审计年度**：事件年度 ≠ 审计年度（如上年比较数导入触发的重算）⇒ 不推、不留运行记录；手动触发报 400。
  底稿 / 附注只属于审计年度，把上年试算表推进本年底稿是错数。
- **空写不算写入**：判定为写但存储值不变（composable 占位行 0 → 四表 0）⇒ 记 unchanged、不落库、不推进版本、
  不进 SSE `changed_items`（否则每次推送都让打开底稿的用户看到假提示条）。
- **事件触发且无目标底稿 ⇒ 不留运行记录**（每次重算都记一条空记录会淹没面板「最近推送」）；手动触发照记并给告警。
- 唯一约束 `uq_wp_index_project_code` / `uq_working_paper_project_index` 不带 `is_deleted` 条件（真库现查）⇒ 一个项目
  一个编码至多一张底稿；多于一张视为约束被破坏，中止并报错（推送地址不含 wp_id，会串）。

## 十一、测试与变异

| 判据 | 测试 | 变异 |
|---|---|---|
| 三态判定表 | `test_formula_push_policy.py`（逐行 + PBT max_examples=5） | 把 keep_manual 改 write 必红 |
| 前后端同式 | vitest 产出夹具 / pytest 对夹具 | 任一侧改算式必红 |
| E1 端到端 | SQLite 真 ORM：导入值变化 → 行/汇总/审定合计/附注；人工改值保留；锁定；冻结底稿跳过 | 删写入 / 去掉 origin 过滤必红 |
| 真 PG 写入 | 一次性 schema：适配器 UPSERT、content_version、CAS | 去掉 project_id 必红 |
| 端点 | TestClient 真请求 + 无权限 403 | 去掉鉴权依赖必红 |
| 触发 | 事件 → run 调用；引擎写入不发 WORKPAPER_SAVED | — |
| 死区（需求 5） | 端点级两向 | 恢复旧逻辑必红 |

## 十二、风险

| 风险 | 缓解 |
|---|---|
| 用户打开底稿期间后台推送，随后用旧内存值保存覆盖 | 提示条 + 「载入最新数据」；覆盖后下次推送判 manual 并展示差异，不丢数 |
| 前端算式后续被改而后端未跟 | 双侧夹具守卫 |
| 首推时大量「待确认」 | 等值静默采纳；仅真实不等者待确认，面板一键批量采用 |
| 他人工作树并行改动 | 本 spec 触达文件先 `git status` 核对无他人改动再改 |
