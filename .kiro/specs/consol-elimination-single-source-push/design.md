# 设计文档：合并抵销分录单源与差额表推送

> 需求：#[[file:.kiro/specs/consol-elimination-single-source-push/requirements.md]]
> 上游口径：#[[file:.kiro/specs/consol-tree-three-code-autobuild/design.md]] §五（节点金额、符号归一、分录归属）

## 一、现状实证（2026-09-30 现读代码 + 真库）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 两套分录存储互不相通 | 差额面板 → `elimination_entries`；明细表 `EliminationSheet.vue` 的 `$emit('save', allEntries)` → `ConsolWorksheetTabs.onSave` → `PUT /api/consol-worksheet-data/{pid}/{year}/elimination`（JSON） |
| F2 | 明细表同步分录表恒失败 | `_syncEliminationEntries`：`entry_type: entry.source \|\| 'custom'`（枚举无此值，422）、单行一边（`_serialize_lines` 借贷不平 400）、`account_code: entry.subject`（名称当编码）、请求体无 `project_id`（必填 422）；`catch {}` 吞错 |
| F3 | 明细表的「权益/损益/交叉」自动行永远为空 | 保存的是数组，恢复读 `saved.elimination.rows.equity`（对象形状）⇒ 恒 undefined；这三组 props 只来自骨架（值全空） |
| F4 | 试算平衡表页抵销列恒空 | `fill-tb` 读旧 JSON 对象形状 + `SELECT closing_balance FROM trial_balance`（列不存在，PG 事务中止）；页面按「借减贷」算审定数，贷方科目方向反 |
| F5 | 合并报表生成不出来 | `generate_consol_reports_sync(..., applicable_standard="enterprise")`；前端 `generateConsolReports` 传 `CAS`；`report_config` 真库只有 `soe_consolidated`(352) / `listed_consolidated`(260)；两个合并项目 `financial_report` 0 行 |
| F6 | 合并报表取数口径与单体不一致 | `ConsolTrialResolver.resolve_tb` 精确匹配 `standard_account_code == code`，单体 `TrialBalanceResolver` 前缀汇总；且忽略列名（年初余额也取合并数） |
| F7 | 报表只生成两类 | `type_order = [balance_sheet, income_statement]`；真库 `soe_consolidated` 有公式的行：BS 90 / IS 34 / CFS 15 / EQ 2 / CFSS 5 / IMP 13 |
| F8 | 附注抵销恒 0 | `_calculate_elimination_from_rules` 读 `rule["amount"]`，调用方只传 `rule_type` |
| F9 | 合并附注页打不开 | `ConsolNoteTab.vue` 14 处请求地址写成字面量 `` `P_cn.list(props.standard)…` `` |
| F10 | 公式管理合并节点是空壳 | `consol_report_bs/is` 无数据源（`consolSheetRows` 无此键、`allRowsMap` 不填）；`fetchReportRows` 只查 `project:{id}` 与 `{tpl}_standalone` |
| F11 | 审批只重算两张表 | `handle_elimination_approved` → `recalc_full` + `recalculate_trial`；无报表、无附注标记、无上层合并项目、无 SSE |
| F12 | 两处遗留写入是空操作 | `POST /api/report-config/batch-update` 设置 `ReportConfig.current_period_amount`（ORM 无此列）；`/drill-down` 每家企业取同一个 `consol_tb_*` 键 |

报表公式线性性（真库 `soe_consolidated` 159 条 / `listed_consolidated` 118 条有公式行）：ABS/MAX/MIN/IF/ROUND 0、
比较 0、乘除 0；`ROW` 引用 35 / 33，`SUM_ROW` 4（IS 1 + CFS 3），`REPORT` 0；引用年初列 2 条（CFSS-007/008）。
⇒ 报表行值对「节点金额」是线性函数，可逐节点、逐列分解（§四）。

附注：`consol_note_sections_{std}.json` 是纯表样（`rows` 为字符串二维数组、无科目码）。探针：
soe 221 张表中 17 张能靠单体模板行科目码映射、59 张主表可由「章节名 = 报表项目名」取报表行；
listed 282 张中 18 / 43。

## 二、总体数据流

```
差额节点面板 ─┐
明细表（汇总视图）─┼─► elimination_entries（唯一来源）
底稿生成草稿 ─┘            │ 审批 / 撤销审批
                           ▼
              ConsolPushService.push(root 及全部上层合并项目，自下而上)
                ├─ recalc_full        → consol_worksheet（节点×科目）
                ├─ recalculate_trial  → consol_trial（科目级）
                ├─ report_rows(node=根, measures) → financial_report（合并报表，全部类型）
                ├─ 标记 consol_note_data 待更新（is_stale 标记表）
                └─ consol_push_run 记录 + SSE consol.pushed
按需计算（不落库，读时实时算，与推送同一函数）：
  试算平衡表页  = report_rows(根, [个别数, 权益抵销, 往来抵销, 调整, 合并数])
  报表差额表    = report_rows(汇总节点的每个子节点, 合并数) + 合计
  附注差额表    = note_cells(公式, 同上)
```

读时计算与推送写入用同一函数 `consol_report_values`，保证页面数与落库报表逐分一致（P1）。

## 三、分录模型补充（V172 / R172）

`elimination_entries` 增列：

```sql
ALTER TABLE elimination_entries ADD COLUMN IF NOT EXISTS origin VARCHAR(40);       -- NULL=手工
ALTER TABLE elimination_entries ADD COLUMN IF NOT EXISTS origin_key VARCHAR(200);  -- 来源内确定性键
CREATE UNIQUE INDEX IF NOT EXISTS ux_elim_entries_origin
  ON elimination_entries (project_id, year, origin, origin_key)
  WHERE is_deleted = false AND origin_key IS NOT NULL;
```

`origin` 取值：`ws_equity_sim`（模拟权益法）/ `ws_internal_arap` / `ws_internal_trade` / `legacy_sheet`（旧 JSON 转入）。
`origin_key` 例：`equity_sim:step1:{company_code}`、`internal_arap:{row_hash}`。

新表 `consol_push_run`（推送运行记录，面板「最近推送」）与 `consol_note_formula`（合并附注单元格公式）：

```sql
CREATE TABLE IF NOT EXISTS consol_push_run (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  trigger_source VARCHAR(40) NOT NULL,          -- elimination_approved / elimination_revoked / formula_changed / manual
  triggered_by UUID,
  status VARCHAR(20) NOT NULL DEFAULT 'running' -- running / succeeded / partial / failed
    CHECK (status IN ('running','succeeded','partial','failed')),
  steps JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{step, project_id, status, detail}]
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS consol_note_formula (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_type VARCHAR(20) NOT NULL,           -- soe / listed
  section_id VARCHAR(64) NOT NULL,              -- 合并附注表 id（如 五-5-1）
  row_index INTEGER NOT NULL,
  col_index INTEGER NOT NULL,
  formula TEXT NOT NULL,
  source VARCHAR(20) NOT NULL DEFAULT 'manual'  -- seed / manual
    CHECK (source IN ('seed','manual')),
  description TEXT,
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by UUID
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_note_formula_cell
  ON consol_note_formula (template_type, section_id, row_index, col_index) WHERE is_deleted = false;
```

`consol_note_data` 增列 `is_stale BOOLEAN NOT NULL DEFAULT false`（推送后标记，「按公式填入」清除）。

## 四、报表行级计算（纯函数 `consol_report_values`）

### 4.1 金额度量（measure）

每个节点 × 科目的「度量值」由 `CalcBasis` 与 `node_values` 得到（全部为自然方向归一后的审定数口径）：

| measure | 含义 | 数据节点 | 差额节点 | 汇总节点 |
|---|---|---|---|---|
| `consolidated` | 合并数 | 个别数 | 调整 + 抵销净额 | Σ 子节点合并数 |
| `individual` | 个别数汇总 | 个别数 | 0 | Σ 子树数据叶子个别数 |
| `adjustment` | 调整净额（其他调整） | 0 | 调整净额 | Σ 子树差额节点调整 |
| `elim_equity` | 权益抵销净额 | 0 | `equity` 类型 | Σ |
| `elim_trade` | 往来交易抵销净额 | 0 | `internal_trade` + `internal_ar_ap` + `unrealized_profit` | Σ |

恒等式（P2）：`individual + adjustment + elim_equity + elim_trade = consolidated`（逐节点逐科目，精确到分）。
实现：`ElimTotals` 增加按类型分桶（`by_type: dict[str, (debit, credit)]`），`elim_net` 不变；新函数
`node_measures(basis) -> {node_key: {measure: {account: Decimal}}}`。

### 4.2 取数（resolver）

`BasisResolver(values: dict[account, Decimal])` 实现 `AmountResolver`：
- `resolve_tb(code, col)`：`col ∈ {期末余额, 审定数, 本期发生额}` ⇒ Σ 以 `code` 为前缀的科目值（与单体前缀口径一致，
  且报表配置已验证无前缀重叠）；`col ∈ {年初余额, 期初余额}` 或未知列 ⇒ 记入 `unsupported` 并返回 0。
  「本期发生额」用于损益类科目：合并口径的损益类审定数即本期发生额（子企业试算表损益类审定数为本年累计）。
- `resolve_sum('a~b', col)`：Σ 科目码 ∈ [a, b] 或以区间端点为前缀的子级（`a <= code[:len(a)] <= b`）。

### 4.3 行求值

`report_values(configs, values, *, report_types) -> {row_code: RowValue}`：按 `(report_type, row_number)` 排序
逐行调用 `report_engine.evaluate_formula(formula, resolver=BasisResolver(values), row_cache=cache)`，
`cache` 在同一次调用内跨报表类型共享（支持跨表 ROW）；行 `unsupported` 非空 ⇒ `RowValue.amount = None` 且带原因。

线性保证（P3）：公式在 §一统计范围内只含 `+ -` 与数值常量；`validate_linear(formula)`（AST 遍历，禁 `* /`、
比较、`ABS/MAX/MIN/IF/ROUND`）在求值前检查，非线性行按「不可分解」留空并说明，不影响合并报表本身
（合并报表对 `consolidated` 直接求值，不需要分解）。

### 4.4 口径解析

`consol_standard(project) = f"{template_type or 'soe'}_consolidated"`（`listed` / 其他 ⇒ `soe`）。
合并报表生成、试算页、差额表、公式管理全部用它；`generate_consol_reports_sync` 默认值改为按项目解析，
`ConsolReportGenerateRequest.applicable_standard` 改为可选（传入非 `*_consolidated` 值按项目解析并在响应中说明）。

### 4.5 合并报表落库

`generate_consol_reports` 改为：`basis = load_calc_basis(db, pid, year)`；`values = node_measures(basis)[root]['consolidated']`；
全部报表类型逐行 `report_values`；`financial_report` upsert（`current_period_amount`，`prior_period_amount` 取上年
合并项目同行已生成值，没有则 NULL）；`indent_level/is_total_row` 从 `report_config` 复制。
`ConsolTrialResolver` 保留（兼容既有测试），但合并报表不再使用；其精确匹配口径在 docstring 标注「已由 BasisResolver 取代」。

## 五、试算平衡表页（只读，`GET /api/consolidation/worksheet/report-trial`）

参数：`project_id, report_type, node_key?`（默认根）。返回每行：
`row_code, row_name, indent_level, is_total_row, individual, elim_equity, elim_trade, adjustment, consolidated, note`。
前端 `ConsolTrialBalanceTab.vue` 列：审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数（净额，一列一值）。
移除编辑、保存、提取填充、生成报表、提取上年数；保留导出；新增「重新推送」（调 `POST /push`）。
穿透：抵销/调整列 → `GET /api/consolidation/worksheet/drill/entries?row_code=&report_type=&measure=`（按行公式涉及的
科目集合过滤本树分录明细行，只计已审批）；审定汇总 → 各数据节点对该行的求值（§六同一函数）。

## 六、报表差额表（`GET /api/consolidation/worksheet/report-breakdown`）

参数：`project_id, report_type, node_key?`（默认根合并节点）。
列 = 目标汇总节点的直接子节点（按树序），每列 `report_values(values = measures[child]['consolidated'])`；
合计列 = `report_values(measures[node]['consolidated'])`。P4：各列之和 = 合计（非线性行除外，标注）。
前端：合并报表页工具栏新增视图切换「合并报表 / 差额表」；差额表视图有节点选择（只列汇总节点），
差额列（`kind='elim'`）用浅黄底色。

## 七、合并附注差额表

### 7.1 公式存储与种子

`consol_note_formula` 按 `(template_type, section_id, row_index, col_index)` 唯一。种子（`seed_consol_note_formulas`，
幂等、只写 `source='seed'` 且不覆盖 `manual`）：
- (a) 章节名规范化后 = 合并报表 BS/IS 项目名规范化 ⇒ 该章第一张表「合计」行、第一个期末类列 ⇒ `REPORT('{row_code}')`
  （求值时由 §4.3 的 cache 提供，即对同一节点度量先算报表行）。
- (b) 表行首列标签对上单体附注模板行（章节名 + 表名 + 行标签规范化）且该行有 `account_codes` ⇒ 期末列
  `TB('c1','期末余额') + TB('c2','期末余额')…`。
规范化：去空白与全角空格、去「（1）」类序号、去「减：/其中：/△▲*#」前缀。

### 7.2 求值

`note_breakdown(section_id, node_key?)`：对每个有公式的单元格按 §4 的四个度量求值 → 个别数汇总 / 调整 / 抵销 / 合并数；
可展开子节点贡献（同 §六）。

### 7.3 按公式填入

`POST /api/consol-note-sections/fill-by-formula/{pid}/{year}/{section_id}`：读 `consol_note_data`（无则用模板行），
对有公式的单元格写入合并数（两位小数字符串）；`data.manual_cells` 中的单元格保留并在响应列出；清除 `is_stale`。
前端 `ConsolNoteTab` 修复 14 处 URL（改用 `P_cn.*` 路径函数），工具栏增加「按公式填入」「查看差额」。

## 八、推送（`ConsolPushService`）

- 入口：`push(db, project_id, year, trigger, user_id)`；事件 handler 与 `POST /api/consolidation/{pid}/{year}/push` 共用。
- 目标集合：`[project_id] + ancestors(project_id)`；上层用企业树反查：从当前项目企业代码沿 `parent_company_code`
  链找同年度合并项目（与 `sync_group_links` 同一派生规则，读 `parent_project_id` 派生值即可，已保证与三码一致）。
- 每个目标：`recalc_full` → `recalculate_trial` + commit → `generate_consol_reports`(按口径) + commit →
  `consol_note_data.is_stale = true` → 记步骤；关键步失败则该目标后续跳过，上层继续（上层数据仍按库内下层结果算）。
- 并发：进程内 `asyncio.Lock` 按 `(project_id, year)` + PG `pg_advisory_xact_lock(hashtext('consol_push:'||pid||':'||year))`；
  防抖：handler 层按 `(project_id, year)` 合并 1 秒内的重复触发（`EventBus` 已有 500ms debounce，这里再在排队期合并）。
- 结果：`consol_push_run` 一行；SSE `consol.pushed` `{project_id, year, run_id, status, pushed_projects}`；
  失败另记 `failed` 运行并广播 `consol.push_failed`。
- 触发：`ELIMINATION_APPROVED`、新增 `ELIMINATION_REVOKED`、`REPORT_CONFIG_CHANGED`（合并口径公式保存，由公式管理保存后
  前端调 `POST /push`，避免全局监听所有报表配置变更）、`TRIAL_BALANCE_UPDATED`（子企业）⇒ 只标过期不推送（沿用
  `consol_trial_stale_handler`，另广播 `consol.push_stale`）。
- 既有 `consol_elimination_recalc_handler` 改为调用 `ConsolPushService.push`（保留函数名与注册点，测试不断）。

### 8.1 撤销审批

`EliminationReviewAction.action` 增 `revoke`：`approved → draft`，需 edit 权限，记审计日志 `consol.elimination.revoke`，
发布 `ELIMINATION_REVOKED`。合并项目锁定（`projects.consol_lock` / 签字冻结，沿用 Phase 1 锁定判定函数）时拒绝。

## 九、明细表（`EliminationSheet.vue` 重写）

- 数据：`GET /api/consolidation/eliminations/tree-lines?project_id&year`（新）：本树全部未删分录展开为明细行，
  每行带 `entry_id, entry_no, origin, node_key, node_label, host_project_id, readonly, entry_type, account_code,
  account_name, debit, credit, description, review_status, counted, orphan_reason`。
- 工具栏：新增分录（弹出与差额面板同一表单组件，抽出 `ConsolElimEntryForm.vue`，增加「归属节点」下拉）、
  生成草稿分录、刷新、导出；行操作：修改 / 提交审批 / 审批 / 驳回 / 撤销审批 / 删除（按状态）。
- 预览区「待生成」：由 `ConsolWorksheetTabs` 传入模拟权益法 / 内部往来 / 内部交易的计算结果（`sourceGroups`，
  每组 `{origin, origin_key, description, lines[{subject, detail, direction, amount}], related_company_codes}`），
  点击「生成草稿分录」调 `POST /api/consolidation/eliminations/generate-from-worksheet`。
- 旧 JSON：`GET /api/consol-worksheet-data/{pid}/{year}/elimination` 有自定义行 ⇒ 提示条 + 「转为草稿分录」
  （同一生成接口，`origin='legacy_sheet'`）。

### 9.1 生成接口（`generate_from_worksheet`）

输入 `groups[]`；逐组：科目映射（§9.2）→ 借贷平衡校验 → 按 `(origin, origin_key)` upsert：
- 无记录 ⇒ 新建草稿（`branch_entity_code = suggest_branch_entity(tree, pid, related)`）；
- 草稿 / 已驳回 ⇒ 更新明细行与说明，状态置草稿；
- 待审批 / 已审批 ⇒ 不动，若明细行不同记 `changed_after_review`；
- 本次请求中同一 `origin` 未出现的 `origin_key` 的草稿 ⇒ 软删。
返回 `{created, updated, unchanged, deleted, blocked:[{origin_key, reason}], changed_after_review:[...]}`。

### 9.2 科目映射

`map_subject(name, detail, options)`：规范化后先匹配本树科目清单（`load_account_options`，名称或「名称-明细」），
再匹配标准科目表（`resolve_standard_account_by_name`，`preferred_codes` 取本树科目清单编码），
都不中 ⇒ 不映射并给原因。长期股权投资的明细（损益调整 / 投资成本 / 其他权益变动）按标准表子科目名匹配，
匹配不上用父科目 `1511`。权益变动表项目（如 `2-3股份支付计入所有者权益的金额`）不是科目 ⇒ 不映射，报原因。

## 十、公式管理

- `FormulaManagerDialog.vue`：`consol_report_bs/is` 改为报表节点：数据源 `report_config`（`{tpl}_consolidated`），
  加 `consol_report_cfs/eq/cfss/imp`；`reportTypeOfNode` 识别 `consol_report_*`；保存沿用 `PUT /api/report-config/{id}`，
  成功后若 `projectId` 为合并项目则调 `POST /push`。
- 新节点「合并附注」→ 子节点按合并附注章节；行 = `consol_note_formula` 记录（单元格位置显示为「第 r 行 · 列名」），
  可增删改（`/api/consol-note-formulas`，edit 权限：admin/partner/manager）。
- 新页签「合并推送」（`ConsolPushPanel.vue`，合并项目可见）：最近 10 次运行、步骤明细、警告、「立即推送」。

## 十一、遗留处置

- 删除：`consol_note_sections.fill_trial_balance`（`/fill-tb`）、`report_config.batch_update_report_config`
  （`/batch-update`，前端唯一调用方随试算页改造移除）、`ConsolWorksheetTabs._syncEliminationEntries` 与旧 JSON 恢复、
  `apiPaths.reportConfig.batchUpdate`。
- 改造：`report_config.report_drill_down`（`/drill-down`）改为返回差额表子节点贡献（按企业树，不读 info JSON）。
- `ConsolTrialBalanceTab` 删除 `consol_tb_*` JSON 读写；历史数据保留在库中不再读取。

## 十二、正确性属性

| # | 属性 | 测试 |
|---|---|---|
| P1 | 推送写入的合并报表 = 读时计算的合并数（同行同分） | SQLite 真 ORM：push 后比对 `financial_report` 与 `report-trial` |
| P2 | 逐节点逐科目 `individual + adjustment + elim_equity + elim_trade = consolidated` | hypothesis（随机树 + 随机分录，max_examples=5） |
| P3 | 线性行：`Σ 子节点行值 = 汇总节点行值`（容差 0.01） | hypothesis + 真库公式快照 |
| P4 | 报表差额表各列之和 = 合计列；根节点合计 = 合并报表值 | SQLite 真 ORM |
| P5 | 前缀口径：`TB('1122')` 含 `112201`，与单体 `TrialBalanceResolver` 同值 | 单元 + 对照 |
| P6 | 生成草稿幂等：同输入两次 ⇒ 第二次 `created=0 updated=0` | SQLite |
| P7 | 已审批分录不被生成接口改写 | SQLite |
| P8 | 撤销审批后推送：合并数回到审批前 | SQLite |
| P9 | 年初列 / 非线性公式行留空并给原因，不静默 0 | 单元 |
| P10 | 附注按公式填入不改手工单元格 | SQLite |
| P11 | 端点鉴权：无项目权限 403，readonly 调写接口 403 | 端点测试 |

## 十三、架构决策

- **ADR-CSP-001 分录唯一来源 `elimination_entries`**。否决：让明细表 JSON 与分录表双写同步（已证实同步必然漂移，
  且 JSON 是名称不是编码）。
- **ADR-CSP-002 报表/试算/差额表同一求值函数，差额表读时计算**。否决：把差额表落库成独立表（需要额外失效机制，
  且线性分解可随时重算，数据量为「节点数 × 行数」，读时计算成本可接受：100 节点 × 400 行 < 50ms 纯内存）。
- **ADR-CSP-003 合并报表改用 BasisResolver（前缀口径）**，`ConsolTrialResolver` 仅兼容保留。否决：修 `ConsolTrialResolver`
  改前缀——它读 `consol_trial` 落库值，推送链路中报表生成紧跟试算重算，改读口径对象可去掉一次 DB 往返，且与读时计算同源。
- **ADR-CSP-004 不复用 E1 公式推送引擎**。E1 引擎以底稿为中心（`_find_workpapers`、CAS 写 `checklist_responses`、
  domain CHECK 只有 workpaper/note），合并推送目标是整张表派生值，没有「人工改过」三态问题（附注除外，由手工单元格标记处理）。
  二者在公式管理里共用入口与展示风格，引擎分开。
- **ADR-CSP-005 附注只种子化两类可确定公式**，其余保持手工。否决：按名称猜测全部单元格（172 张表无科目码，猜错写入是错数）。
- **ADR-CSP-006 新增撤销审批**。审批后金额可能需要更正；没有撤销路径只能删库。撤销受锁定约束并留审计。

## 十四、风险

- 公式管理保存合并口径 `report_config` 会影响所有合并项目（模板级）；沿用既有「项目级克隆」机制不在本 spec 范围，
  保存确认框提示影响范围。
- 旧 JSON 自定义行多为名称，转入成功率取决于科目映射；无法映射的逐条列出，不自动猜。
- `ELIMINATION_APPROVED` 上已有测试依赖 `handle_elimination_approved` 调 `recalc_full` + `recalculate_trial`；
  改为经推送服务后仍先调这两步，测试以真实调用验证。
