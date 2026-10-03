# 任务清单：合并抵销分录单源与差额表推送

> 需求 #[[file:.kiro/specs/consol-elimination-single-source-push/requirements.md]] ·
> 设计 #[[file:.kiro/specs/consol-elimination-single-source-push/design.md]]
> 规则：标 `[x]` 须附证据行（代码 + 测试通过）；依赖外部环境的如实标 `[ ]*`。PBT `max_examples=5`。

- [x] 1. 数据层（V172 / R172）
  - [x] 1.1 `elimination_entries` 增 `origin` / `origin_key` + 部分唯一索引；ORM `Mapped[]` + 响应 schema
  - [x] 1.2 新表 `consol_push_run`、`consol_note_formula`；`consol_note_data` 增 `is_stale`；ORM
  - [x] 1.3 迁移幂等（重复执行）+ 回滚脚本；SQLite 建表测试
  - _需求：1.1, 2.4, 6.1, 8.1_
  - 证据（2026-09-30）：`V172__consol_elimination_single_source_push.sql` / `R172__…`；`consol_push_models.py`；
    `tests/test_consol_push_schema_contract.py` 11 passed；真 PG `run_pending` 执行 `['172']`、`pg_indexes` 核对
    `ux_elim_entries_origin` 部分唯一索引存在；`/api/health` healthy、`applied_count` 172、drift 0

- [x] 2. 计算内核（纯函数）
  - [x] 2.1 `ElimTotals` 按分录类型分桶；`node_measures`（合并数 / 个别数 / 调整 / 权益抵销 / 往来交易抵销）
  - [x] 2.2 `BasisResolver`（前缀口径、年初列与未知列记 unsupported）、`validate_linear`、`report_values`
  - [x] 2.3 `consol_standard(project)` 口径解析
  - [x] 2.4 测试：P2 恒等式 PBT、P3 线性分解 PBT、P5 前缀对照、P9 留空原因
  - _需求：3.1~3.6_
  - 证据（2026-09-30）：`consol_calc_basis.py`（`ElimTotals.add` / `elim_measures` / `node_measures`）+ 新模块
    `consol_report_values.py`（`canonical_formula` / `analyze_formula` / `BasisResolver` / `report_values` /
    `node_report` / `consol_standard`）；`tests/test_consol_report_values.py` 53 passed（P2/P3 hypothesis
    max_examples=5；P3 另用真库公式快照 `fixtures/consol_report_config_snapshot.json` 两套口径逐行精确到分；
    P5 真 SQLite 对照单体 `TrialBalanceResolver`；P9 十类留空原因）；变异 18/18 killed；合并相关回归 43 个文件
    539 passed / 2 skipped / 5 xfailed / 0 failed
  - 补记（任务 7）：快照增加第 5 列行名（真库，前 4 列逐行比对一致后才写）；`data/report_config_seed.json` 的合并口径
    行次编码与真库错位（真库 BS-003 = 交易性金融资产，seed 里 BS-003 = △结算备付金），测试一律以真库快照为准
  - 实现中发现的编排层静默错数（`report_engine.evaluate_formula`，均在合并口径内规避，单体路径未改）：
    ① `-TB(...)` 取到负值拼成 `--30.00` 解析失败 = 0；② `TB( '…' , '…' )` 宽松写法不被预替换 = 0；
    ③ 引号外认不出的字符被词法跳过：`A +－ B`（全角减号）静默变成 `A + B`，其余多为整条 0；
    ④ 极小金额 `str()` 成科学计数 `1E-7`，整条解析失败 = 0。
    真库合并口径 277 条公式全部线性；留空 5 行（soe：IS-030/031/053、CFSS-007/008），原因为权益类「本期发生额」
    与「年初余额」需上年数据

- [x] 3. 合并报表生成改造
  - [x] 3.1 `generate_consol_reports` 用计算内核、全部报表类型、按项目口径、上年值取上年合并项目
  - [x] 3.2 `/api/consolidation/reports/generate` 口径参数可选；前端不再传 `CAS`（前端改动随任务 9）
  - [x] 3.3 测试：真 ORM 集团生成报表逐行核对；旧测试回归
  - _需求：3.2, 3.4_
  - 证据（2026-09-30）：`consol_report_service.generate_consol_reports` 改为 `load_calc_basis` → `node_measures` 根合并数
    → `report_values`（与试算页 / 差额表同一求值函数），口径 `CONSOL_STANDARDS` 照用、其余按 `template_type` 解析；
    上期取上年同一企业合并项目本期值（无则 NULL）；留空行写 **V173 `financial_report.blank_reason`**（新迁移，真 PG 已
    执行、health healthy applied 173 drift 0，契约测试 `test_v173_blank_reason_three_layers`）；同键复用含软删行
    （唯一索引不带 is_deleted 谓词）、当前口径外的旧行次软删、字典形态 source_accounts（权益变动表矩阵）保留。
    路由：`applicable_standard: str | None`，响应带实际口径、口径说明与各表留空行数；体内项目须与鉴权项目一致。
    `tests/test_consol_push.py::TestGenerateReports` 3 例（前缀含 112201、SUM_TB 含终点子级、跨表 ROW、年初列与权益类
    本期发生额留空、上期 888、草稿不计入、上市口径切换）
  - 设计补充：原 design §4.5 未写留空行如何落库；金额列本身可空，但只存 NULL 说不清「为什么空」⇒ 新增 V173 一列

- [x] 4. 推送服务
  - [x] 4.1 `ConsolPushService.push`：目标集合（本项目 + 上层合并项目自下而上）、四步、锁、运行记录、SSE
  - [x] 4.2 `consol_elimination_recalc_handler` 改调推送；新增 `ELIMINATION_REVOKED`
  - [x] 4.3 审批流增加 `revoke`（已审批 → 草稿，审计日志，锁定拒绝）
  - [x] 4.4 端点：`POST /api/consolidation/{pid}/{year}/push`、`GET .../push-runs`
  - [x] 4.5 子企业试算表变更 ⇒ 广播 `consol.push_stale`（沿用既有 stale handler）
  - [x] 4.6 测试：P1、P8、上层联动、失败留痕、端点鉴权
  - _需求：8.1~8.6_
  - 证据（2026-09-30）：新模块 `consol_push_service.py`（`push_targets` 沿派生链接自下而上 / 每目标四步各自事务 +
    `asyncio.Lock` + `pg_advisory_xact_lock` / 关键步失败后续 skipped、上层照推 / `consol_push_run` running →
    succeeded|partial|failed / SSE `consol.pushed`·`consol.push_failed` 逐推送项目广播 / `request_push` 排队期同键合并）；
    handler 保留函数名、审批与撤销两事件都走推送；`elimination_service.change_review_status` 增 `revoke`（本项目及上层
    任一合并锁定 ⇒ `EntryLockedError` → 423）；审计 `consol.elimination.revoke`；新路由 `consol_push.py` 三端点
    （push / push-runs / push-status，已在 `router_registry/system.py` 登记）；`consol_trial_stale_handler` 广播
    `consol.push_stale`。`tests/test_consol_push.py` TestPush 4 例 + TestEndpoints 3 例（审批 → 推送报表 −50 → 锁定时
    撤销 423 → 撤销 → 推送回到审批前 = P8；审计两条；只读成员推送 403、非成员全 403）；旧测试
    `test_q4_elimination_approved_triggers_both_recalcs` 改为真 SQLite 跑推送编排（原用 MagicMock 会话，推送要写运行记录）；
    `test_consol_trial_stale_handler` 加广播断言。变异 21/21 killed（上层不推 / 关键步不跳过 / 部分失败记成功 / 失败不广播 /
    附注不标过期 / 排队不合并 / 撤销不查锁 / 撤销不发事件 / 撤销不记审计 / 子企业变更不广播过期 …）

- [x] 5. 只读计算端点
  - [x] 5.1 `GET /worksheet/report-trial`（试算平衡表页数据）
  - [x] 5.2 `GET /worksheet/report-breakdown`（报表差额表）
  - [x] 5.3 `GET /worksheet/drill/entries`（行 → 分录明细）
  - [x] 5.4 测试：P4、穿透只计已审批、端点鉴权
  - _需求：4.1~4.4, 5.1~5.2_
  - 证据（2026-09-30）：新模块 `consol_report_view_service.py`（`trial_view` 五列净额 / `breakdown_view` 直接子节点各一列 +
    合计 / `entry_drill_rows` 按 `row_account_terms` 展开的取数项系数计贡献 / `load_individual_drill`）；内核补
    `row_account_terms`（ROW / SUM_ROW 递归代入到科目取数项）与 `term_matches`。另加 `GET /worksheet/drill/individual`
    （审定汇总列穿透，design §五 已写但任务清单漏列）。`TestViews` 2 例：P1 推送落库 == `report-trial` 合并审定数逐行、
    四度量之和 == 合并数；P4 各列之和 == 合计且 == 合并报表；下级合并项目的抵销进上级；穿透贡献之和 == 该行该列、
    草稿不进、前缀 112201 计入 `TB('1122')` 行。合并相关回归 44 个文件 553 passed / 2 skipped / 5 xfailed / 0 failed
  - 回归中见到的红（均与本次改动无关，文件本会话未改）：`test_event_call_site_guards` 7 例（`adjustments.py` /
    `review_workflow_service.py` / `independence_signing_service.py` 仍 import `app.core.event_bus`，后者为并发会话在改）、
    `test_formula_runtime_zero_regression` 3 例（`ADJ` 已于 commit a00e58997 进注册表，守卫基线未更新）、
    `test_lazy_import_resolvability` 1 例（`phase5_d3_*` 已入库、棘轮未收紧）

- [x] 6. 明细表后端
  - [x] 6.1 `GET /eliminations/tree-lines`（本树全部分录明细行 + 归属 + 只读判定）
  - [x] 6.2 `POST /eliminations/generate-from-worksheet`（科目映射、借贷校验、幂等 upsert、软删、已审批不改）
  - [x] 6.3 旧 JSON 自定义行识别与转入（`origin='legacy_sheet'`）
  - [x] 6.4 测试：P6、P7、映射失败原因、端点鉴权
  - _需求：1.2, 1.6, 2.1~2.6_
  - 证据（2026-09-30）：新模块 `consol_elimination_sheet_service.py`：`sheet_lines` / `tree_lines`（与计算口径同一
    `attribute_entries`，`counted` = 已审批且归属成功；下级合并项目承载的只读并给承载项目；坏明细行占位给原因；
    全部 / 已审批 / 计入三行合计；本项目承载的差额节点供表单下拉）；`SubjectMapper`（本集团科目 → 合并报表单科目行 →
    标准科目表，前一处有候选不看后一处；原名优先于别名；同级落在报表取数范围内的优先；「名称+明细」整体匹配 → 子科目 →
    父科目兜底并注明；权益变动表项目、少数股东权益不映射给原因；标准表 4 开头成本类不参与）；`plan_group`（负金额换向、
    0 金额跳过、方向 / 金额认不出、借贷不平、类型与来源不符 ⇒ blocked 逐条原因）；`generate_from_worksheet`（同键同一笔
    更新；已驳回且来源没变不推翻；待审批 / 已审批不动只报告；只软删声明负责来源里消失的键；blocked 不删已有草稿；
    `dry_run` 预演；PG 咨询锁串行 + 唯一索引冲突转 409）；旧版 `legacy_sheet`（自定义行识别、按录入顺序借贷平衡处切分、
    来源键 = 序号 + 内容摘要、转入后不改写不转回）。路由 4 个固定路径声明在 `/{entry_id}` 之前：`GET /tree-lines`、
    `POST /generate-from-worksheet`、`GET /legacy-sheet`、`POST /legacy-sheet/convert`。`tests/test_consol_elimination_sheet.py`
    36 passed（映射 22 例、计划 3 例、P6 / P7 / 软删 / 驳回 / 预演 / 请求错误、明细行、旧版、端点含 403 与独立会话核对已提交）；
    变异 26/26 killed（首轮「生成不提交」存活 ⇒ 补独立会话读断言后 killed）；真 PG 预演 2098 集团三类来源全部映射到报表取数
    范围内编码（`sheet_probe`，回滚不写库）；相关回归 120 passed
  - 真库发现：减值准备表 `IMP-012 十一、在建工程减值准备` 公式是 `TB('1604')`（在建工程本身，非减值准备）⇒ 报表单科目行只取
    资产负债表 / 利润表，附表不作映射依据（该配置错误本身不在本 spec 范围，未改）
  - 设计补充：①科目映射多一层「合并报表单科目行」——标准科目表权益类是 3 开头，而合并报表公式按 4 开头取权益，
    只查标准表会把「资本公积」映到 3002、报表看不到；②映射到的科目不在报表取数范围内 ⇒ 照常生成但给警告（本集团试算用
    3002 时仍用 3002，否则抵销与个别数落在两个编码上抵不掉）；③旧版行没有分录边界 ⇒ 按借贷平衡切分；转入走 `sync=False`
    （来源已冻结，转入后分录归审计师）

- [x] 7. 合并附注公式与差额
  - [x] 7.1 `consol_note_formula` CRUD 端点 + 种子（两类，幂等，不覆盖人工）
  - [x] 7.2 附注差额计算端点（四度量 + 子节点贡献）
  - [x] 7.3 「按公式填入」端点（保留手工单元格、清过期）；推送标记过期
  - [x] 7.4 测试：种子覆盖数与真库一致、P10、端点鉴权
  - _需求：6.1~6.4_
  - 证据（2026-09-30）：新模块 `consol_note_formula_service.py`：`plan_seed`（两类种子，见下「设计补充」）、`seed_note_formulas`
    （只写 seed；人工不覆盖；人工删除的不补回；规则不再产出的种子删除）、`ensure_seeded`（读公式 / 求值前按需，模板文件 mtime +
    合并口径报表配置签名，SAVEPOINT 内写）、CRUD（改公式 ⇒ 人工；只差空白不算改；软删）、`note_cell_values`（附注单元格作为排在
    全部报表行之后的伪行交给 `node_report` ⇒ `REPORT('BS-002')` 与合并报表同一次求值；抵销 = 权益 + 往来交易；子节点贡献）、
    `note_breakdown`、`fill_by_formula`（行按项目名定位，已保存数据插删过行也不写错行；手工单元格保留并列出；留空公式不覆盖原值；
    清 `is_stale`）。新路由 `consol_note_formulas.py`（GET 列表 / POST / PUT / DELETE / POST seed；写入 admin / partner / manager），
    已在 `router_registry/system.py` 登记；`consol_note_sections.py` 增 `GET /breakdown/{pid}/{year}/{sid}`、
    `POST /fill-by-formula/{pid}/{year}/{sid}`（edit + 合并锁 423），声明在 `/{standard}/{section_id}` 之前。推送第 4 步标记过期
    沿用任务 4。`tests/test_consol_note_formulas.py` 18 passed（种子规则 12 例、真模板 × 真库快照覆盖数 soe 45 + 5 / listed 32 + 7、
    落库幂等 / 人工不覆盖 / 删除不补回 / 失效删除、求值与报表同值且四度量之和 = 合并数、子节点和 = 合并数、P10 与行定位、端点
    CRUD / 差额 / 填入 / 403 / 423）；变异 24/24 killed（首轮 2 条存活：伪行排序与「填入不提交」——前者补报表行号大于附注行号的
    用例，后者发现内存 SQLite 共用一个连接，「另开会话读」看得见未提交写入 ⇒ 改为回滚后读，同一问题顺带修了任务 6 的端点用例）；
    真 PG 种子计划 soe 50 / listed 39 个单元格（与探针一致），2098 集团「货币资金」章差额端到端求值（回滚不落库）
  - 设计补充（种子可确定性，ADR-CSP-005 的落实）：①(a) 类取「唯一期末列」（资产负债表项目）/「唯一本期列」（利润表项目），
    变动表（期初 / 本期增加 / 本期减少 / 期末）取期末而非第一个含「本期」的列；表头有空列名（多级表头未展开）/ 多个期末列 /
    多个合计行 / 同名报表行公式不一致 ⇒ 不种并记原因；②(b) 类只种「科目都是该章报表行取数项」的行，并按报表公式系数取数
    （固定资产 = `TB('1601') - TB('1602')`，单体模板只写了科目码、照搬会把累计折旧加进去）；单体模板科目码有语义不符的
    （受限资产、供应商融资列报、6701 / 6702 互换）⇒ 这条约束把它们挡在外面

- [x] 8. 遗留入口处置
  - [x] 8.1 删除 `/fill-tb`、`/report-config/batch-update`（先全仓检索调用方）
  - [x] 8.2 `/report-config/drill-down` 改为企业树子节点贡献
  - [x] 8.3 测试同步调整
  - _需求：9.1, 9.3_
  - 证据（2026-09-30）：全仓检索调用方 —— `/fill-tb` 仅 `ConsolTrialBalanceTab.vue`（任务 11 重写）；`/batch-update` 为
    `ConsolTrialBalanceTab.vue` 与 `FormulaManagerDialog.vue` 执行公式后的「回写」（写的是 `report_config` 上**不存在的**
    `current_period_amount` 列，真 PG `information_schema` 确认无任何 amount 列 ⇒ 从未落库却报成功），后端测试 0 引用。
    删除两个后端端点、`apiPaths.reportConfig.batchUpdate` 与 FormulaManagerDialog 回写段；`/drill-down` 改为
    `consol_report_view_service.child_contributions`（与报表差额表同一求值：`rows` = 汇总节点直接子节点、`leaf_rows` = 子树
    末级，线性行两层之和都 = 合并数；项目在体内 ⇒ `assert_project_permission` 项目级鉴权，原实现只校登录）；
    `ConsolidationIndex.loadDrillDownData` 改读新结构并删除「按持股比例估算」兜底（需求 9.3）。
    `tests/test_consol_legacy_entrypoints.py` 4 passed（已删路由真发请求 404/405；前端源码不再引用已删端点——试算页在任务 11
    重写前暂列白名单；穿透直接下级和 = 末级和 = 合并报表、下级合并项目节点、错误 400/404、403）；变异 4/4 killed
  - 回归中见到的红（与本次无关）：`tests/four_table/test_report_config_account_integrity.py` 6 例 —— 连真库检查 `report_config`
    数据（错码 / 零命中 / 跨行双算 / `SUM_ROW` 未登记…），真库该表最后更新 2026-09-11、本会话未写；其中「IMP-012 在建工程减值准备
    = TB('1604')」即任务 6 记录的同一处配置错误

- [x] 9. 前端 API 与类型
  - [x] 9.1 `consolidationApi.ts`：新端点函数与类型；`apiPaths` 登记
  - [x] 9.2 抽出 `ConsolElimEntryForm.vue`（差额面板与明细表共用；归属节点下拉）
  - _需求：1.3_
  - 证据（2026-09-30）：`apiPaths/report.ts` 登记 `consolidation.eliminations.{treeLines, generateFromWorksheet, legacySheet,
    legacySheetConvert}`、`consolidation.worksheet.{reportTrial, reportBreakdown, drillEntries, drillIndividual}`、
    `consolidation.{push, pushRuns, pushStatus}`、`consolNoteSections.{breakdown, fillByFormula}` 与新组 `consolNoteFormulas`
    （`index.ts` 具名导出 / 聚合 import / `API` 对象三处都加），逐条与后端 router 前缀 + 路由核对一致；
    `consolidationApi.ts` 补类型（明细行 / 生成结果 / 旧版转入 / 试算五列 / 差额表 / 穿透 / 推送运行 / 附注公式与差额）与 17 个函数，
    `EliminationReviewAction` 增 `revoke`、`EliminationEntry` 增 `origin` / `origin_key`；`generateConsolReports` 不再默认传 `CAS`
    （不传 ⇒ 后端按项目口径）。`ConsolElimEntryForm.vue`（新增 / 修改共用：`targets` 下拉只列本项目承载的差额节点、一个时默认选中、
    `lock-target` 面板模式只显示；修改按 `branch_entity_code` 找回节点）；`elimNodePanel.ts` 增 `ElimTarget` / `elimTargetOf` /
    `findTarget` / `canRevoke`，`buildEntryPayload` 改按所选节点取归属；`ConsolElimNodePanel.vue` 改用该组件并加「撤销审批」
    （二次确认）。vitest 3 个文件 29 passed（`ConsolElimEntryForm.spec.ts` 5 例新增：未选节点禁用保存 / 单节点默认选中且合并差额
    归属为空 / 修改找回节点走修改接口 / 无可录入节点 / 重开重置；面板 8 例含新增的修改回填与撤销审批；纯逻辑 16 例含撤销状态机与
    归属选项）；ESLint 9 个文件 0 error 0 warning；单区域 vue-tsc 0 error（注入 `number = 'x'` 报 TS2322，证明新组件确被检查）

- [x] 10. 合并抵消分录明细表重写
  - [x] 10.1 `EliminationSheet.vue`：分录明细汇总表、状态操作、合计、只读行前往链接
  - [x] 10.2 待生成预览 + 「生成草稿分录」；`ConsolWorksheetTabs` 传 `sourceGroups`，删除旧同步与旧 JSON 恢复
  - [x] 10.3 旧 JSON 提示条 + 转入
  - [x] 10.4 vitest
  - _需求：1.1~1.6, 2.1~2.3, 9.2_
  - 证据（2026-10-01）：`EliminationSheet.vue` 全部重写 —— 只读 `tree-lines`（分录级列跨明细行合并、计入 / 未归属原因、
    下级合并项目承载的行只读 + 「前往」）、合计三行（全部 / 已审批 / 计入合并数，各带借贷差额与平衡标记）、按状态的
    提交审批 / 审批 / 驳回 / 撤销审批（二次确认）/ 删除（二次确认）、新增与修改用 `ConsolElimEntryForm`（归属 = `hosted_nodes`）、
    导出；「待生成」区挂载即 `dry_run` 预演（静默失败在页面上说明，403 给权限提示）、来源变化 600ms 去抖重预演、
    会删草稿时先二次确认再真生成；旧版自定义行提示条（原文「检测到旧版自定义抵销行 N 条，旧版数据未参与合并计算」）+
    「转为草稿分录」+ 逐组原因明细。新纯函数模块 `elimSourceGroups.ts`（模拟权益法三步 × 企业、来源键
    `equity_sim:step{n}:{企业代码}`；内部往来按科目对抵销 —— **借负债方、贷资产方**，原实现按本方 / 对方顺序会把
    「本方应收」抵成借应收 —— 加本方 / 对方坏账冲回；内部交易收入成本 + 未实现利润显式 `unrealized_profit`；全部 Decimal，
    原 `InternalTradeSheet` 用浮点 `Number(decSub(...))` 累加；内部现金流无会计科目不生成）与 `elimSheet.ts`（行合并、
    动作文案、摘要、删除确认文案、导出行）。`InternalArApSheet` / `InternalTradeSheet` 底部预览改用同一函数（表内预览 =
    明细表待生成，不再各算各的），并接收已保存行（原先两表从不恢复数据 ⇒ 刷新后表空）。`ConsolWorksheetTabs`：删除
    `_syncEliminationEntries`（87 行）、`internalEntries` / `equitySimEntries` / `allImportedEntries`、`buildElimCross`、
    elimination 的 `onSave` 分支与 Excel 导入列、旧 elimination JSON 恢复；新增 `sourceGroups` / `sourceOrigins`。
  - 设计补充（声明负责的来源）：只声明「该表有已保存数据或本次算出了分组」的来源 —— 内部往来 / 交易表的数据只在打开后
    才在前端，若一律声明三类来源，没打开过、没保存过的表会被当成「算出来是空的」而删掉它以前生成的草稿；保存过空表才删
    （测试钉死这一边界）。旧 JSON 恢复的处置：`data.elimEquity / elimIncome` 仍是骨架（下游抵消后长投 / 投资收益 / 少数股东 /
    资本公积继续读），因旧恢复读对象形状而保存的是数组，**从未恢复成功**（F3），删除恢复不改变这些表的现有行为；真库
    `consol_worksheet_data` 现为 0 行。
  - vitest：新增 `elimSourceGroups.spec.ts` 14 例（含 fast-check `numRuns: 5`：任意金额下每组借贷平衡、来源键唯一、
    无零金额行）、`EliminationSheet.spec.ts` 7 例、`ConsolWorksheetTabs.elimination.spec.ts` 2 例（真挂载父组件：已保存行
    恢复进分组与子表、旧 JSON 不恢复、不调任何分录写接口、清空未保存不声明 / 保存空表才声明）；合并组件与视图测试
    49 个文件 762 passed；变异 17/17 killed（首轮 4 条存活 ⇒ 补「还原分红」步、浮点累加、撤销审批确认、保存后才声明
    四处断言）；单区域 vue-tsc 改动文件 0 error（注入 TS2322 证明新组件被检查）；ESLint 改动文件 0 error，余下 warning
    均在未改动的既有行

- [x] 11. 试算平衡表页改造
  - [x] 11.1 `ConsolTrialBalanceTab.vue` 读 `report-trial`，五列净额，只读，穿透，重新推送
  - [x] 11.2 vitest
  - _需求：4.1~4.4_
  - 证据（2026-10-01）：`ConsolTrialBalanceTab.vue` 全部重写为只读 —— 六类报表切换、汇总节点下拉（取自页面已加载的
    企业树、只列 `kind=aggregate`，与报表差额表同一判定；树变化后所选节点消失则回到根）、五列净额直接显示后端值
    （合并审定数不再按「借减贷」在前端重算 —— 原实现对贷方科目方向反，design F4）、无公式行（标题行）不显示 0、
    取不到数的列显示「留空」并悬浮原因；每格可穿透：权益 / 往来交易抵销、报表调整、合并审定数 → `drill/entries`（分录
    编号、归属节点、科目、借贷、对该行贡献，合计与本格对照），审定汇总 → `drill/individual`（各数据节点个别数）；
    「重新推送」调 `POST /push`（`trigger=manual`）；顶部显示最近一次推送（时间、触发来源、状态）与子企业数据变化后的
    过期提示；保留导出（数字列）；「审核」改为逐行核对恒等式（审定汇总 + 权益抵销 + 往来交易抵销 + 报表调整 = 合并
    审定数，Decimal 精确到分；非线性行只计数，取不到数的行列原因）。删除编辑 / 保存 / 提取填充（`/fill-tb`）/ 生成报表
    （`/batch-update`）/ 提取上年数 / `consol_tb_*` JSON 读写。新纯函数模块 `consolTrialView.ts`。`ConsolidationIndex`：
    传 `:year="treeYear"`（企业树的审计年度，与明细表 / 差额面板一致）+ `:tree`，删 `@generate-report-done` 与
    `onTbGenerateReportDone`、`consolTbLoading`；右键「汇总穿透」改读 `row.consolidated`（原读已不存在的 `row.summary`）
    并带上试算页所选汇总节点；进入本页每次重读（读时计算）。`test_consol_legacy_entrypoints.py` 去掉试算页白名单
    （全仓零引用已删端点）并新增 `test_trial_tab_reads_report_trial_only`（源码钉死不再读写旧 JSON / 前端重算）。
    vitest `ConsolTrialBalanceTab.spec.ts` 8 passed（纯逻辑 2 例 + 组件 6 例：五列取后端值、留空、节点下拉与按节点穿透、
    两类穿透、重新推送与过期提示、审核、未打开不读 / 年度变化重读）；变异 10/10 killed；后端相关 5 个文件 125 passed；
    单区域 vue-tsc 0 error（注入 TS2322 证明被检查）；ESLint 新文件 0 error 0 warning（`ConsolidationIndex.vue` 4 条为既有）

- [x] 12. 报表差额表与合并附注
  - [x] 12.1 合并报表页「差额表」视图（节点选择、差额列样式）
  - [x] 12.2 `ConsolNoteTab.vue` 修复 14 处未插值地址；「按公式填入」「查看差额」
  - [x] 12.3 vitest
  - _需求：5.3~5.4, 6.3~6.5_
  - 证据（2026-10-01）：新增 `ConsolReportBreakdownView.vue` + `consolReportBreakdown.ts`，合并报表页可在六类报表下切换
    「合并报表 / 差额表」；默认根汇总节点、可切换/下钻下级汇总节点，直接子节点按树序逐列，差额节点浅黄标识且可穿透到
    已审批调整/抵销分录，合计为该汇总节点合并数；非线性行只给合计，线性行用 Decimal 核对各列之和，支持导出。
    `ConsolNoteTab.vue` 现扫实际为 **16** 处（任务原记 14 已过期）未插值 `` `P_xxx...` ``，已全部归零并由源码守卫锁死；
    重新汇总改走 `P_consol.notes.reaggregate` 且回载传 `props.standard`（不再误传企业代码）；新增章节/全模板「按公式填入」，
    未保存编辑先落库，手工单元格随插删行重排并持久化 `manual_cells`、导入数据同样标手工，填入后显式列出 filled / kept_manual /
    blank；400 模板口径与 423 合并锁定显示后端具体原因。新增「查看差额」显示个别数汇总/调整/抵销/合并数四列并可展开
    直接子节点贡献；页首「查看」也改走该内核，不再读旧 info JSON / 持股比例估算；附注年度改用企业树年度。
    定向 vitest 2 文件 **18 passed**，整个 `components/consolidation` **18 files / 151 passed**；后端同源
    `test_consol_push + test_consol_note_formulas + test_consol_legacy_entrypoints` **35 passed**；变异 **21/21 killed**；
    单区域 vue-tsc 改动文件 0 error，分别向差额组件/附注组件注入错误均命中 TS2322；ESLint 新增与任务 12 改动文件 0 issue
    （`ConsolidationIndex.vue` 仍为既有 4 warnings）。

- [x] 13. 公式管理
  - [x] 13.1 合并报表节点接 `{tpl}_consolidated`（六类报表）可编辑，保存后推送
  - [x] 13.2 合并附注节点（附注公式增删改）
  - [x] 13.3 「合并推送」页（最近运行、步骤、警告、立即推送）
  - [x] 13.4 vitest
  - _需求：7.1~7.4_
  - 证据（2026-10-01）：新增 `ConsolFormulaManagementPanel.vue` + `consolFormulaManagement.ts`；公式中心「合并报表」完整列出
    资产负债表/利润表/现金流量表/所有者权益变动表/现金流附表/资产减值准备表六类，逐类精确读取
    `{soe|listed}_consolidated`（不走 `project:*` / `*_standalone`），可编辑并 `PUT /api/report-config/{id}`；保存前明确提示
    模板级全项目影响，成功后仅一次 `pushConsolidation(projectId, year, 'formula_changed')`，推送启动失败与公式已保存分开提示。
    「合并附注」改走 `consol_note_formula` 独立 CRUD：完整章节选择、自动种子/人工来源、1-based 行号转后端 0-based、增改软删、
    幂等重新种子化；admin/partner/manager 可写，其他角色只读；每次真实变更后推送。`ThreeColumnLayout` 不再以 `wpId` 作为
    保留上下文的条件，project/year/scope/template/note section/report type 可完整透传；合并页、附注页、工作底稿入口均发送显式上下文。
    新增 `ConsolPushPanel.vue`：由当前项目发起的最近 10 次运行、逐项目四步、每次警告、过期状态、立即推送；`queued=false`
    按「并入排队」展示而非失败；与 E1 公式推送引擎保持独立。

- [x] 14. 前端事件
  - [x] 14.1 合并页订阅 `consol.pushed` / `consol.push_stale` / `consol.push_failed`：刷新当前视图、提示
  - _需求：8.3, 8.5_
  - 证据（2026-10-01）：三事件是 `broadcast_raw`（事件名只在 SSE event channel，data 无 `event_type`），故合并页直接复用
    `subscribeProjectEvent` 的项目共享连接逐事件名订阅，并按 project + 企业树年度双重过滤；`consol.pushed` 强制刷新当前工作底稿 /
    企业树 / 试算 / 报表或差额表 / 附注树（报表明确 `force=true` 绕过缓存），partial 刷新并警告；`push_stale` 重查权威
    push-status 并显示「子企业数据已变化，建议重新推送」；`push_failed` 持久错误横幅 + Notification，不刷新旧数据冒充成功。
    组件卸载及项目/年度切换均关闭并重绑三订阅；`SSEEventType` 已登记三事件；`ConsolWorksheetTabs` 暴露统一 `reload()`。
    定向 **6 files / 31 passed**；公式管理+合并组件整区 **44 files / 404 passed**；后端 push/note/schema/legacy
    **47 passed**；变异 **25/25 killed**；ESLint 新增文件 0 issue；单区域 vue-tsc 新增文件 0 error，向两个新面板分别注入
    类型错误均命中 TS2322（全区仍报告 FormulaManagerDialog/ThreeColumnLayout/ConsolidationIndex 等既有非本任务错误）。

- [ ] 15. 验证收尾
  - [ ] 15.1 回归：合并、报表、附注、分录、公式管理相关测试；变异证明关键判据
  - [ ] 15.2 浏览器实测：录入 → 审批 → 试算/报表/差额表/附注联动 → 撤销审批回退；截图；清理数据
  - [ ] 15.3 INDEX.md 登记；memory 更新；清理一次性脚本
  - _需求：10.1~10.5_
