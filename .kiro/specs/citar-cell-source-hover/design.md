# 设计：表格单元格悬浮溯源

## 1. 总体
- 后端每类表一个「来源」接口，一次返回整张表每格的来源；来源与格值用**同一套取数 / 公式代码**算出（不另写口径）。
- 前端一个通用卡片组件 + 一个悬停 composable（事件委托、单实例），各表格只在格子上写 `data-src` 键。
- 新代码放新文件：`report_engine.py`（2681 行，白名单 2693）、`ledger_penetration_service.py`（965，基线 942）、
  `routers/ledger_penetration.py`（1713，基线 1634，+5% 上限 1715）、`routers/reports.py`（731，上限 800）都没有余量。

## 2. 统一返回结构（`backend/app/services/cell_source/schema.py`）
```
CellSource = {
  kind: rule | formula | manual | import | derived | synthetic | preset | param | adjustment | none
  title: str            # 来源说明（中文，一句话）
  value: str | None     # 格值（与表格显示同口径）
  items: [SourceItem]   # 构成明细，最多 20 项
  more: int             # 超出 20 项的个数
  linear: bool          # 可做合计核对
  total: str | None     # Σ coef × amount（linear 时）
  diff: str | None      # total − value，|diff| ≥ 0.005 才给
  notes: [str]          # 口径说明、未计入的调整、回退科目等
  issue: str | None     # 取不到 / 过期等问题
  manual: {value, auto, by_name, at} | None
  rule_text: str | None # 税审样表取数规则原文（卡片里默认收起）
}
SourceItem = {label, detail, amount, sign(+1/-1/系数), link: SourceLink | None}
SourceLink = {page, code?, sheet?, ref?, row?, column?, group?, report_type?, tab?}
```
- `page` 取值：`balance` `journal` `mapping` `trial_balance` `adjustments` `reports` `statement` `workpaper` `tax_return` `ledger_import`。
  后端只给语义，路由换算只在前端 `sourceLink`（沿用 `fsIssueSources.ts` 的约定）。
- 每个接口返回 `{year, cells: {cell_key: CellSource}, notices}`；`cell_key` 规则见各节。金额一律字符串（Decimal）。
- 构成项超过 20：按金额绝对值取前 20，`total` 仍按全部项计算。

## 3. 接口（新路由 `backend/app/routers/cell_sources.py`）
前缀 `/api/projects/{project_id}/cell-sources`，全部 `require_project_access("readonly")`；受限成员按有效循环过滤科目（与试算表 GET 同口径 `get_user_scope_cycles`）。

| 端点 | cell_key | 服务 |
|---|---|---|
| `GET /tax-sheet/{code}?year=&domain=workpaper\|tax_return` | `{sheet}!{A1}` | `cell_source/tax_sheet.py` |
| `GET /trial-balance?year=` | `{标准科目}:{列}` | `cell_source/trial_balance.py` |
| `GET /report/{report_type}?year=&mode=audited\|unadjusted` | `{row_code}:{current\|prior}` | `cell_source/report.py` |
| `GET /financial-statements?year=` | `{表key}:{r}:{current\|prior}` | `cell_source/fs.py`（准则格式转调 report） |
| `GET /ledger/balance?year=` | 列：`col:{字段}`；行：`row:{id}` | `cell_source/ledger.py` |
| `GET /ledger/journal-row/{row_id}?year=` | 单行 | `cell_source/ledger.py` |

在 `backend/app/router_registry/system.py` 紧跟 `tax_assurance_router` 注册；前端路径加进 `services/apiPaths.ts` 的 `cellSources`。

## 4. 税审底稿 / 汇算申报表（`cell_source/tax_sheet.py`）
- 复用 `evaluate_keys`：`Evaluation` 增加 `book: AccountBook | None` 字段（只多存一个引用，不改求值）。
  来源接口 = `compute_sheet` 同一 seeds 的 `evaluate_keys` + 逐格组装；不再跑第二遍取数。
- **取数格**（`results_meta[key]` 有值）：
  - 每个 `node`：`amount = book.measure([node], measure)`（按月规则 `book.month([node], measure, m)`）；`measure` 为逐节点累加，
    Σ amount = 格值（`_unclosed_pl_leaves` 的扣减也是逐节点的，仍可加总）。测试逐格断言。
  - `title`：`科目余额表（导入数，不含审计调整）· {中文口径}`；中文口径表 `_MEASURE_LABEL` 补齐 `closing_debit` / `closing_credit` / `paid_opening`，
    按月规则写「{m} 月借方 / 贷方发生额（序时账）」。
  - 项：`{编码} {名称}`、`detail = 映射到 {标准码} {标准名}` / `未映射`；链接 `balance`（编码）。
  - 回退：`AccountBook.resolve` 改为内部调用 `resolve_detail(path) -> (nodes, issue, fallback_top | None)`，原签名不变；
    `RuleResult` 加 `fallback: str | None`，来源写「{原一级} 下没有，按 {回退一级} 取数」。
  - 调整未计入：取命中节点的标准码集合，查已批准、非底稿来源的 `adjustment_entries`（与 `_adjustments_by_standard` 同条件），
    有则 `notes` 写「以下已批准调整分录涉及本格科目，未计入本格」并逐组列为项（`sign=0`，不参与合计，链接 `adjustments` + `group`）。
  - `status` / `issue` / `rule` 原样带出；`manual` 规则写「需人工判断后填写」。
- **公式格**：`wb.formula_text[key]` 进 `title`；`iter_refs(ast)` 展开引用（区域按格展开，最多 20 格）；
  每格 `label = {编号} {格子} {行名}`，行名取本行第一个文字常量格；值用 `ev.calc_value`（与 Excel 同口径，空按 0）。
  - 线性判定：AST 只含 `bin +/-`、`neg`、`ref`、`num`、`SUM(...)`、`bin * / ` 一侧为 `num` ⇒ 求每个引用格的系数；否则 `linear=false`。
  - 引用他表：链接 `workpaper` / `tax_return`（按 `code_domain` 判）+ `code` + `sheet` + `ref`；目标表 `isTaxWorkpaperShown` 为假时前端在项上写「该表不显示」。
  - 引用填写参数表：`kind=param`，写「取自填写参数（未填时为项目信息）」。
- **手工值格**：`origin=input`；`manual.auto` 沿用 `compute_sheet` 现有 auto；`by_name / at` 取本表 `TaxWorkpaperInput.updated_by / updated_at`，
  并写明「本表最近保存」（手工值不按格记人）。
- **样表预置常量**：`kind=preset`；空白格不返回。
- 行数：`tax_workpaper_service.py` 430 行，只加 `Evaluation.book` 两行；新模块预计 ≤ 350 行。

## 5. 试算平衡表（`cell_source/trial_balance.py`）
- `standard_balance_view_service` 抽出 `leaf_balance_rows(db, project_id, year)`：返回 tb_balance 末级行
  `(客户编码, 名称, 标准码, 期初借正贷负, 借, 贷, 期末借正贷负)`；`_period_by_standard` 改为对它求和（同一条 SQL，同一 `leaf_condition` / `signed_balance`）。
  再抽 `approved_adjustment_lines(db, project_id, year)`（逐组：编号、摘要、借、贷、标准码），`_adjustments_by_standard` 改为对它求和。
  ⇒ 卡片构成与 `standard-view` 的格值同源，测试断言逐列相等。
- 各列：
  - 期初 `opening`：格值取 `trial_balance.opening_balance`（与页面同），构成 = 末级行期初；不等时 `diff` + 「试算表需重算」。
  - 本期借 / 贷 `period_debit` / `period_credit`：构成 = 末级行借 / 贷，链接 `balance`。
  - 借 / 贷调整 `adj_debit` / `adj_credit`：构成 = 已批准调整逐组（链接 `adjustments` + `group`）；未批准组另列 `sign=0` 写「不计入」。
  - 调整后期末 `adj_closing`：项 = 未审期末（末级合计）、借方调整、−贷方调整、底稿发布调整。
  - 审定数 `audited`：同上式；与 `audited_amount`（按方向转借正贷负）不等时 `diff` + 「试算表需重算」。
  - 底稿取数余额表的本期借 / 贷 `src_debit` / `src_credit` = 本期 + 调整，两项。
- 页脚文字按 R4.6 改。

## 6. 审定报表 / 报表分析（`cell_source/report.py`）
- **取数记录**：`ReportFormulaParser` 加可选 `recorder: list | None`（默认 None，行为不变）。`_resolve_tb` / `_resolve_sum_tb` / `resolve_pl_unclosed`
  在返回前追加 `{fn, arg, column, field, rows:[(标准码, 名称, 值)], value}`；`_resolve_tb` 的「按列与模式选字段」循环抽成 `_row_amount(row, column)`，求值与记录共用。
  `TB_PATTERN` 会误匹配 `SUM_TB` 后半段 ⇒ 记录时跳过含 `~` 的 code。
- **逐项拆分**：对原公式 `parse_to_ast(formula)`（TB 仍是函数节点），遍历 AST 传递正负号与常数系数；叶子：
  TB / SUM_TB / PL_UNCLOSED 取记录值，ROW / SUM_ROW / REPORT 取同一次重算的 row_cache（`SUM_ROW` 展开为各行），ADJ 取 `adj_data`，
  NOTE / WP 取预载值，PREV / AUX 写「报表生成时按 0」。非线性（IF / MIN / MAX / ABS / ROUND / 比较 / 两引用相乘除）⇒ `linear=false`。
- **重算快照**：仿 `_compute_unadjusted_report_rows` 在内存里按 `evaluation_order` 重算资产负债表 + 利润表（两表共用 row_cache，ROW 可能跨表），
  **不写库、不调 `full_recalc`**；审定口径读手工值（`load_manual`），生效值进 row_cache。重算值与库里 `current_period_amount` 不等 ⇒ `issue = 报表已过期，请重新生成`。
- **上期 / 期初**：`PriorPeriodResolver.prior_amount` 增加 `last_source`（`opening` 本年试算表期初 / `same_prior` 本项目上年试算表 /
  `prior_report` 上年项目「{名称}」报表同行 / `prior_tb` 上年项目试算表 / `None` + 原因）。`opening` / `same_prior` / `prior_tb` 三种用带 recorder 的 parser 逐项拆分；
  `prior_report` 只给一项，链接到不了（跨项目）只写名称。
- **手工值**：`manual_amounts.{col}.{value, auto}` + `by`（用户 id → `resolve_user_display_names`）+ `at`。
- 未审口径（`mode=unadjusted`）不读手工值；对比模式前端分别取两份。
- 新模块预计 ≤ 450 行；`report_engine.py` 只加 recorder 参数与 `_row_amount` 抽取（净增 ≤ 10 行，留在白名单 2693 内）。

## 7. 单体财务报表（`cell_source/fs.py`）
- `financial_statements.build_enterprise_system` 里的 `column_pair` 抽成模块级 `compute_columns(ctx, stmt, values, with_manual)`，
  `ctx` 装 `closing / opening / pl_close / prior_closing / cf_cur / cf_prior / cf_generated / saved`；报表与来源共用。
- 逐行：
  - `accounts` 行：每个 term 展开到命中的标准码（`account_total` 的前缀 + 剔除规则抽成 `account_terms(balances, term) -> [(code, amount)]`，
    `account_total` 改为对它求和）；系数 = `flip × (negate ? −1 : 1)`；`PL_CLOSE` 单独一项「未结转损益」。链接 `trial_balance`。
  - `formula` 行：解析 `_TERM_RE`，`SUM(a:b)` 展开为各行，项值取生效值，链接 `statement`（本页格子）。
  - `cf` 行：命中的平台现金流量表行名与值，链接 `reports`。
  - `from` 行：一项，链接 `statement`。
  - 手工格：手工值与 auto；`by / at` 取 `__fs__` 行的 `updated_by / updated_at`（整份保存）。
- 期初列（资产负债表）写「本年试算表期初数」；利润表上期写上年项目名称或无来源原因（`resolve_prior_source`）。
- 企业会计准则格式：转调 §6（`statement.key` 即报表类型）。
- 隐藏页签不在本轮（R5.7），接口照返回，前端不渲染。

## 8. 账务查询（`cell_source/ledger.py`）
- 映射记录：本年 active 数据集 → `job_id` → `import_jobs.custom_mapping.confirmed_mappings[]`，按 `table_type` 分组
  （余额表：`balance` / `aux_balance`；序时账：`ledger` / `aux_ledger`）。每个标准字段给 `[{file, sheet, header, column_index, confirmed_by_user}]`。
  文件名去掉存储前缀 `NN_`（`strip_store_prefix`）。数据集 `activated_at / activated_by`（显示名）。
  没有 `job_id` 或 `custom_mapping` 为空 ⇒ `notes` 写「本数据集没有保存字段映射记录（旧导入或迁移数据）」。
- **列级**（`col:{字段}`，前端按列取，同列各格共用）：
  - 科目编码 / 名称 / 凭证号 / 日期 / 摘要：直接映射，列出来源表头。
  - 期初 / 期末：推导说明按 `converter.convert_balance_rows` 的分支写死成文字常量（分列 / 余额 + 方向列 / 年初优先），
    在该列有对应字段映射时才列出该分支；方向依据取行上的 `*_direction_source`（行级）。
  - 本期借 / 贷：「本年累计」映射存在时写「取本年累计，未取本期发生额」。
  - 序时账借 / 贷：映射了单金额列时写「单金额列按借贷标识拆分」；会计期间未映射时写「取自凭证日期的月份」。
  - 辅助核算 / 币种：写取自哪个未映射表头（前端 `pickExtra` 的匹配结果，前端自行填表头名）。
- **行级**（`row:{id}`，只返回有特殊情况的行）：
  - `raw_extra._discarded_mappings`：逐字段列出被舍弃的表头与值，`issue = 同一字段映射了多列，导入只取了第一列，请核对映射`。
  - `raw_extra._aggregated_from_aux`：「由 {n} 条辅助核算明细汇总」。
  - `ledger_manual_edits`：导入原值、修改人、时间、原因（取最后一次 edit）。
  - 方向来源 `closing_direction_source` 为类别推断时写「方向按科目类别推断」。
- 页面补出的上级行（`_is_synthetic`）在前端算：「按下级合计」+ 下级科目列表（数据就在页面上，不请求）。
- 序时账一页 200 行、全年可能十万行 ⇒ 不整表返回行级信息：列级随首次悬停取一次；行级按 `journal-row/{row_id}` 悬停时单取，前端按 id 缓存。
- 新文件，不动 `ledger_penetration_service.py` / `routers/ledger_penetration.py`。

## 9. 前端
- **`citar/components/CitarSourceCard.vue`**：纯展示，props `source: CellSource | null`、`loading`、`error`、`anchor: DOMRect`；
  `position: fixed`，按视口翻转（下方放不下放上方、右侧溢出左移）；**不 Teleport 到 body**（`--citar-*` / `--tw-*` 变量只在页面根下生效），
  挂在使用它的页面根元素内；样式写在组件内、颜色用变量并给回退值。项超过 8 条时列表区滚动。
- **`citar/useCellSourceHover.ts`**：`useCellSourceHover(container: Ref<HTMLElement|null>, load: () => Promise<Record<string, CellSource>>, opts)`
  - 在容器上委托 `mouseover` / `mouseout`，`closest('[data-src]')` 取键；400 ms 显示、200 ms 延迟关闭（移入卡片取消关闭）；
    `scroll`（捕获）/ `keydown Esc` / 容器卸载时关闭；`opts.disabled(key)`（编辑中的格）为真不弹。
  - `load` 单飞 + 缓存；`invalidate()` 供表格刷新后调用。序时账行级用 `opts.loadOne(key)`。
  - 返回 `{ card, close, invalidate }` 给模板绑定。
- **跳转**：`fsIssueSources.ts` 的 `FsSourcePage` 扩成 §2 的 `page` 全集（类型改名 `SourcePage`，旧名保留别名），`sourceLink(link)` 增加：
  - `workpaper` / `tax_return`：写 `pendingCellLocate`（sessionStorage `gt.tax-cell-locate.{pid}` = `{code, sheet, ref}`）+ `saveActiveTaxSheet` / 申报表同类函数，再跳页；
  - `adjustments`：`?locate={group}`；`reports`：`?tab={report_type}&locate={row_code}`；`statement`：本页定位（沿用 `locate()`）。
- **格级定位**：`TaxWorkpaperGrid` 的 `td` 加 `:data-src="{sheet}!{ref}"`（悬停与定位共用）与高亮 class `tw-cell--located`；
  `TaxWorkpaperSheetPanel` / `TaxReturnSheetPanel` 读完值后消费 `pendingCellLocate`（只消费一次），滚到格子；找不到时提示。
- **新增行定位**：`CitarAdjustment.vue` 读 `?locate=` 定位分录组卡片；`CitarAuditedReports.vue` 读 `?tab=` + `?locate=`（`CitarReportTable` 行加 `data-locate`）。
- **离开确认**：跳页前若当前页 `dirty`，沿用 `ElMessageBox.confirm`（单体财务报表、税审底稿、汇算申报表已有 dirty 状态）。
- **去掉原生 title**：`TaxWorkpaperGrid.tooltip()`、`CitarAmountCell.tip`、`CitarTrialBalance` 金额格 `title` 的内容并入卡片
  （卡片底部「操作」一行：点击修改 / 已恢复，保存后生效 / 无权修改）；按钮上的 title 保留。

## 10. 补项目鉴权（R7）
| 端点 | 现状 | 改为 |
|---|---|---|
| `reports.py::get_report` | `get_current_user` | `require_project_access("readonly")` |
| `reports.py::drilldown_report_row` | 同上 | 同上 |
| `reports.py::export_report_excel` | 同上 | 同上 |
| `report_related_workpapers.py::get_related_workpapers` | 同上 | 同上 |
| `report_export.py::export_excel`（前缀带 project_id） | 同上 | 同上 |
| `reports.py::generate_reports`（project_id 在请求体） | `require_operation("report:edit")`，拿不到 project_id ⇒ 只按系统角色判 | 函数体首句 `assert_project_permission(db, user, data.project_id, "edit")`，再判操作权限（先写复现测试再定是否保留 `require_operation`） |
| `wp_report_analysis.py::get_opening_reconcile` 的 `prior_project_id` | 不校验 | 传了就 `assert_project_permission(..., prior_project_id, "readonly")` |
- 鉴权基线：`_IDENTITY_ONLY_BASELINE`（现 183）与 `_PREFIXED_IDENTITY_ONLY_BASELINE`（现 270）改为补完后的现算值；
  `test_note_edit_gate_endpoints.py` 要求第二维**严格相等**，实施时跑扫描取精确值，注释加一行日期与 spec 名。
- 既有测试：`test_report_engine.py` 用 admin 替身不受影响；`test_report_manual_values.py` 的非 admin 身份是项目成员，GET 应仍 200，实施时跑一遍确认。

## 11. 测试
- 后端（每个模块一个测试文件，SQLite 夹具 + 真 service）：
  - 税审：取数格 Σ 节点金额 = 格值（amount / month / list_amount / others_sum / classify 各一）、回退科目、取不到原因、公式格线性系数与合计、
    非线性公式、引用他表链接、手工值、调整未计入。
  - 试算表：各列构成之和 = `standard-view` 同列；审定数不等时 diff；未批准调整不计入。
  - 报表：线性公式逐项之和 = 重算值；SUM_ROW 展开；PL_UNCLOSED；上期四种来源；过期提示；手工值；`recorder=None` 时生成结果逐行不变（回归）。
  - 单体财务报表：accounts / formula / cf / from 各一，negate 与剔除下级；`compute_columns` 抽取后 `build` 输出逐字节不变。
  - 账务：映射记录、无映射记录、舍弃映射、辅助汇总、人工修改。
  - 鉴权：每个新端点与补鉴权端点「非成员 403 / 成员 200 / admin 200」。
  - 真库只读核对脚本（一次性，放仓库外）：ABC餐饮、北京激光、辽宁、宜宾各抽格断言构成之和 = 格值。
- 前端（`citar/__tests__`、`views/tax-workpapers/__tests__`）：卡片渲染（合计核对、差额、非线性、手工值）、悬停延时 / 移入不关 / Esc / 编辑中不弹、
  单飞缓存与作废、`sourceLink` 新页面换算、格级定位（pendingCellLocate 只消费一次）、调整分录 / 审定报表 `?locate=`。
- 浏览器实测：前端 `node_modules/playwright-core` 独立无头脚本（MCP 浏览器与并发会话共用），按 R8 抽格。

## 12. 风险与取舍
- 报表来源接口每次重算两张表（约 200 行公式），按需在首次悬停时请求，可接受；不做缓存，避免与报表生成不一致。
- 序时账不整表返回行级信息（行数大）；列级信息一次取。
- 卡片不 Teleport：父容器 `overflow: hidden` 时用 `position: fixed` 仍能显示在内容区之上；若被 `transform` 祖先裁切，实施时在浏览器里核对。
- 不提供源文件行号：导入时没存，补存要改导入管线，不在本范围。

## 13. 账务查询来源项点开导入记录（R9，批 6）
- **定位键单一来源**：`services/ledger_import/job_mapping_view.py` 的 `locate_key(file_name, sheet_name, column_index)`
  = `去存储前缀文件名 | sheet 名 | 列序号`；卡片链接与详情页每一行都用它，前端只比字符串，不在前端拼。
- **卡片链接**：`cell_source/ledger._dataset` 多取 `LedgerDataset.job_id`；`_mapping_index` 多带 `locate`；
  `_column_sources` 每个映射项 `link_to=link("ledger_import", code=<job_id>, ref=<locate>)`（没有 job 时不给链接）。
  行级「未采用」项不给链接（原值里没有文件 / sheet）。
- **详情接口**：`GET /api/projects/{pid}/ledger-import/jobs/{job_id}/mappings`（`routers/ledger_datasets.py`，readonly；
  作业不属于本项目 404）。返回 `job`（状态、时间、导入人）、`dataset`（id、状态、是否当前生效、各表行数）、
  `file_retained`（上传目录是否还在）、`sheets[]`（`file`、`sheet`、`table_type` + 中文名、`confirmed_by_user`、
  `columns[]`：`column_index`、列字母、`header`、`field`、`field_label`、`locate`）。字段中文名与卡片同一张表（`ledger.FIELD_LABELS` 补齐缺项）。
- **前端**：`cellSourceLink` 给 `ledger_import` 单独分支 ⇒ `{segment:'ledger-import', query:{job, locate}}`（无 job 仍为 `{}`，既有测试不变）。
  `CitarDataImport.vue` 有 `?job=` 时显示新组件 `CitarImportJobDetail.vue`（向导不动）；高亮用 `useCitarRowLocate(locate)` + `data-locate`。
  科目余额表 / 序时账的卡片补 `@open`：有正在修改的行先提示，否则 emit `open-source` 给 `CitarLedgerQuery`，由它 `cellSourceLink` + `goSegment`。
- 不改导入管线（不保存原文件 / 行号）；不做导入历史列表。
