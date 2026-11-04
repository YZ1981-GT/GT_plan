# 设计：CITAR 表格数据可人工编写修改保存

并发说明：`citar-audited-balance-and-workpaper-coverage`（另一会话）同改 `report_engine.py`（PL_UNCLOSED）、`tax_workpaper_service.py`（classify / sheet_notes）、生成器与模型 JSON。本设计只动这些文件的其他函数段；生成器改动后按其最新工作树 `--src` 重生成，`--check` 通过即一致。

## 1 税审底稿 / 申报表：手工值盖过公式（R1）

- 存储不变：`tax_workpaper_inputs.inputs`。公式格写进去就是「覆盖」；键不在 = 自动值；值 null = 手工清空成空白。
- `TaxWorkbook.evaluate`：拓扑序逐格求值时，`key in inputs` 的公式格结果直接取手工值（仍照算一次公式记入 `results.auto`，供悬停显示原值）；环上的公式格有手工值也取手工值。手工值 null：计算按空格（与 Excel 空格一致，下游 MIN 忽略），显示空白。`cell_value` / `_Ctx.cell` 不再「公式优先」：公式格有手工值时取手工值。下游公式、申报表导出、报告正文、审核说明都经 `evaluate` / `calc_value`，一处改动全部生效。
- `save_sheet_inputs`：去掉「公式格不能填写」；`readonly_codes`（RN-*）照旧拒收。
- `compute_sheet`：公式格有手工值 ⇒ `cells[ref] = {origin: input, auto: 原公式值}`；常量格有手工值 ⇒ `auto` = 样表原值。
- 样表预置数字：生成器给「被公式引用的数字常量格」与「值为 0 的数字常量格」（表名 / 表头 / 索引号除外）加 `ref` + `role: 'c'`（预置值，可改）。行次 / 序号这类不被引用的非 0 整数不开放。
- 前端 `TaxWorkpaperGrid`：`role` 为 e / f / c 都可点开；有手工值或草稿的格编辑框旁出「恢复自动值」。`useTaxSheetEditor` 记 `restored` 集合，保存时这些键不提交（整表替换语义下即删除）；悬停：「已手工修改，原值：…」。

## 2 报告正文金额（R9）

`report_body.build` 每行金额带 `manual` / `auto`（1-01报告正文 F17~F41 是公式格，按 §1 机制）。新端点 `PUT /tax-assurance/report-body/amounts`：只读改 1-01 一行的这 25 个键（读出现有 inputs → 改 / 删这些键 → `_upsert`，版本取 1-01 行），不碰同表其他手工值。前端报告正文页加「金额」折叠表：可改、恢复，保存后重载预览。税率行（第 28 行）按百分数输入。

## 3 审核说明段落（R8）

- 段落键：规则行号 `r{row}`；※ 标题补的「无。」为 `r{row}-none`。
- 存储：`tax_workpaper_inputs` 保留编号 `__review_notes__`（加进 `RESERVED_SHEET_CODES`），`inputs = {"__review_notes__": {键: {"text": 改后正文 | null(删除), "auto": 改时的自动正文}}}`。
- `layout(rules, overrides)`：显示判断不变；编号之前按键应用：删除的段不出、不占编号；改过的段正文用手工文字（不再做句末标点自动处理），编号前缀照常自动。输出每段带 `key`、`body`（不含编号）、`auto_body`、`edited`、`auto_changed`（改时的自动正文 ≠ 现在的）；另返回 `deleted`（被删且本该显示的段）与 `orphans`（有修改但现在不显示的段）。
- `PUT /tax-assurance/review-notes`：`{version, edits: {键: {text, auto}}}` 整份替换；键格式、文字长度（≤ 2000）、条数（≤ 2000）校验。导出 Word 用同一份段落。
- 前端：段落点「修改」行内改文字、「删除本段」「恢复自动文字」；已删除段落与「数据变化后不再显示的修改」各一个折叠区，可恢复 / 丢弃。

## 4 审定报表手工值（R6）

- V260：`financial_report.manual_amounts JSONB NULL`，`{"current": {"value": "…", "auto": "…"}, "prior": {…}, "by", "at"}`；`current_period_amount` / `prior_period_amount` 始终是生效值（手工优先），下游（导出、单体 CAS 格式、跨表 ROW()、交付件）零改动即读到手工值。
- 生成（`_generate_report` / 增量重算 / 过期重算三个写入点）：读出本表手工值，手工列不覆盖、只刷新 `auto`；手工的本期值写进 `global_row_cache`，合计行与跨表 ROW() 按手工值算；手工上期值经 `PriorPeriodResolver.override()` 写进上期缓存，上期合计同样按手工值算。
- `PUT /api/projects/{pid}/reports/{year}/manual`：`{items: [{report_type, row_code, column: current|prior, value | restore}]}`，edit 权限、合并锁检查；报表未生成返回 409「请先生成报表」；写完调 `generate_all_reports` 重算合计，commit，发 `REPORTS_UPDATED`。`GET /reports/...` 的行带 `manual_amounts`。
- 前端 `CitarReportTable` 加 `editable`：点金额改、草稿、保存 / 放弃、手工标记与悬停自动值、恢复；审定报表页传 `editable`。

## 5 单体财务报表（R7）

- 企业会计制度格式：手工值存 `tax_workpaper_inputs` 保留编号 `__fs__`，`{"__fs__": {表 key: {行 r: {"current"|"prior": 值}}}}`。`compute_statement(..., overrides)`：取数行与合计行有手工值都取手工值（合计在手工明细之上重算）；`from` 跨表取数读生效值；平衡校验与导出读生效值。另算一份无手工值的结果作 `auto`。
- 企业会计准则格式：行带 `row_code` 与 `report_type`，前端改动走 §4 端点（与审定报表同一处）。
- `PUT /tax-assurance/financial-statements`：`{version, values: {表: {行: {列: 值}}}}` 整份替换；标题行 / 说明行拒收。

## 6 余额表 / 序时账（R3 R4 R5）

- 直接改当前数据集的行（试算表、底稿取数、报表等十余个读取方不用改），另记修改日志：V260 `ledger_manual_edits`（project_id, year, dataset_id, table_name, row_id, action edit/restore/cascade, before JSONB, after JSONB, reason, edited_by, edited_at）。
- 余额表：只改末级行（数据集内没有下级）；可改期初 / 借方 / 贷方 / 期末（按行原有存法：有方向列存正数 + 方向，无方向列存借正贷负）。数据集里真实存在的上级行按借正贷负差额同步（记 `cascade`）。恢复 = 取该行第一条修改的 `before` 再走一次修改（上级随之回调）。改完 `full_recalc` + 发 `TRIAL_BALANCE_UPDATED`（与重算端点同链路），清 `ledger:*:{pid}:{year}:*` 缓存。
- 序时账：可改日期、凭证号、摘要、科目编码 / 名称、借方、贷方；不回写余额表、不重算试算表。主键 (id, year)。
- 读：`GET /ledger/balance` 行带 `id`（合成行无）；新端点 `GET /ledger/manual-edits?table=` 返回本项目年度当前数据集里被改过的行（最后动作是 edit 的 row_id、修改人、时间、原值）；`GET /ledger/manual-edits/summary` 给导入页提示用。
- 写：`PUT /ledger/balance-rows/{id}`、`PUT /ledger/entries/{id}`、`POST /ledger/{table}/{id}/restore`，edit 权限、合并锁检查；service 只 flush，router commit。
- 前端：余额表末级行「修改」行内编辑（期末随期初 + 借 − 贷自动算，可再改），改过的行标「已修改」，上级标「下级已修改」；序时账每行「修改」；数据导入页当前账套有修改时提示「重新导入后这些修改不会保留」。

## 7 试算表改数 → 调整分录草稿（R2）

纯前端：点审定数弹窗（科目、当前审定数、目标方向 + 金额、对方科目、摘要），差额（借正贷负）> 0 借本科目贷对方，< 0 反之；`POST /adjustments`（AJE，草稿），成功提示「已生成调整分录草稿 编号，批准后进入试算表」并可跳转。审定数旁标该科目未批准分录数（读 `/adjustments` 列表）。期初、本期发生额列悬停提示「请在账务查询 → 科目余额表修改」。

## 8 不做

见 requirements「不改」。
