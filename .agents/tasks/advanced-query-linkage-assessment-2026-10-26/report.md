# 高级查询逐功能联动体检报告（2026-10-26）

> 证据位置说明：截图（browser\）与原始证据（evidence\）已移至 `d:\GT_plan\tmp_aql_linkage\assess\`，体检探针脚本位于 `d:\GT_plan\tmp_aql_linkage\probe_assess\`；收尾时将按用户要求删除这些临时文件。

> 阶段：assess（只诊断，未改代码）。代码基线 HEAD `b5fc200e0`，高级查询相关路径与 HEAD 一致。
> 配套文件：`00-ground-truth.md`（基线、库内真值、证据索引）· `10-architecture.md`（入口、端点、执行链、数据源映射、模块接线）· `11-coverage-matrix.md`（功能 × 维度、数据源对账、角色 × 端点、结果去向）· `evidence/`（活体请求与只读 SQL 输出）· `browser/`（15 张截图）。

## 0. 结论

高级查询现在不能用来取证。权限门和构建器的 SQL 层是好的，但全员使用的业务视图里，11 个取数器在真实数据上结果正确的只有 2 个（试算表、底稿清单）；查询结果也走不出查询框：下钻、回写、引用、完整导出全部断开，模板按默认选项保存直接 500。

**断点 37 个：P0 6 · P1 19 · P2 12。**

P0（确定性错数、越权或绕过权威写入）：

| 编号 | 断点 | 一句话证据 |
|---|---|---|
| AQ-02 | 四表查询不经数据集过滤 | 宜宾临港店科目余额 1,624 行 / −1,318,963.36，active 数据集应为 812 行 / −659,481.68 |
| AQ-03 | 业务视图取数 5,000 行截断后在内存排序、分组、计数，且不提示 | 和平药房序时账「共 5000 条」（库内 1,147,414）；科目 1002 分组借方 24,512,071.03（真值 3,245,484,243.16） |
| AQ-04 | 回写目标记录不校验所属项目 | 只在 A 项目有编辑权的审计员，已能定位并锁住【UAT】子公司B 的试算行，只被「只能写 G 列」挡下 |
| AQ-05 | 回写的 tb / adj 模块绕过发布门与调整分录服务 | `write_tb_cell` 直接调 `publish_rows`，无确认、无幂等、无事件 |
| AQ-06 | 构建器对 projects / staff_members 不做项目过滤 | 只能访问 1 个项目的经理读出全部 142 个项目（含已删 57 个）与 152 名员工 |
| AQ-19 | 构建器登记的 account_chart JOIN 使行数翻倍 | 华氏试算表 100 行 JOIN 后 200 行，JOIN 后求和全部翻倍 |

实测可用、后续改动必须保持的部分：业务视图鉴权（匿名 401、非成员 403、成员 200、空项目 403）；审计留痕（本次的越权拒绝 16 条、预算拒绝 2 条、PII 拒绝 1 条、按 60 s 节流的执行 14 条都已落 audit_log_entries）；试算表金额与库一致（华氏 Σ审定 2,033,180,355.49）；构建器 SQL 分组 / 求和与库逐值一致（和平药房借 = 贷 = 10,241,344,771.55）；复杂度预算、PII 分层、语句超时、预览 SQL 带作用域；模板「仅作者可改删」与作者执行；指标树 depth=1 骨架 3.6 KB；`wp-id-by-code`（30 余个底稿 composable 在用，契约不能变）。

对任务前提的更正：
- 0ec33ac9（重药控股安徽有限公司_2025）不在 projects 表中；大项目用例改用现库最大的重庆和平药房连锁（5942c12e，序时账 1,147,414 行）。
- projects 表有 `audit_year` 列；平台权威年度是 `services/project_audit_year.resolve_project_audit_year`。数据项目的 audit_period_end 全为空，只用 `EXTRACT(YEAR FROM audit_period_end)` 会得到 NULL。
- 「前端传日历年」在高级查询里是潜伏问题：回退值是「当年 − 1」= 2025，恰好等于数据年度，2027 年起才会出错（AQ-22）。
- Metabase 两个组件零挂载，用户看不到，不在本轮范围。
- 归档 spec 所说的 7 个零引用服务模块现在都有生产 importer；真正的问题是一批端点没有前端调用方（§4）。

## 1. 口径

- **P0**：生产入口可达（含只需 API 即可调用的端点），正常前提下确定性给出错误业务数值、绕过权威写入门，或破坏项目隔离。
- **P1**：核心功能报错、恒空、输入被静默忽略，或设计承诺的联动缺失，但不会静默给出错误数值。
- **P2**：可用性、提示文案、性能、一致性。
- 证据标注：【实测】活体请求、浏览器或库内对账；【代码】源码确认、未复现；【需实施时验证】本次无法复现。
- 全部数值为 2026-10-26 现算快照，实施时以重算为准，不要写死进判据。

## 2. 断点清单

### 2.1 P0

**AQ-02 四表查询不经 get_active_filter，旧数据集与已删行混入**【实测】
- 证据：宜宾临港店（14fb8c10）科目余额表返回 1,624 行、Σ期末 −1,318,963.36，812 个科目码每个出现两次；按 active 数据集应为 812 行 / −659,481.68（恰好一半）。浏览器 B7：库存现金、银行存款各两行。构建器计数同为 1,624；`is_deleted = true` 的 812 行 tb_balance 也能直接查出。
- 根因：`routers/custom_query.py::_query_account_balance` / `_query_ledger_entries` 只写 `is_deleted = false`，不调用 `services/dataset_query.get_active_filter`；构建器 `table_whitelist.TABLE_WHITELIST` 对 tb_balance / tb_ledger 不注入数据集与 is_deleted 约束。
- 附带：四川物流（299f8a28）1,626 行挂在 ledger_datasets 里不存在的数据集 id 上，get_active_filter 也会回落为不按数据集过滤——数据治理问题，另行处理。
- 应联动：两条入口都改走 get_active_filter；构建器在服务端注入，用户 DSL 不能覆盖。

**AQ-03 业务视图 5,000 行取数上限后内存排序、分组、计数，total 失真且无提示**【实测】
- 证据（和平药房序时账，库内 1,147,414 行）：total = 5,000；offset 6,000 返回 0 行；借方降序首行 11,774,721.42（真值 241,944,666.92）；按科目分组，1002 得 Σ借 24,512,071.03 / 298 行（真值 3,245,484,243.16 / 116,443 行）。warnings 为空。浏览器 B11「本页 100 条 / 共 5000 条」。
- 根因：`services/custom_query/business_fetchers.business_fetcher` 以 `fetch_limit=None` 取数，`_effective_limit` 归一为 `pagination.FETCH_HARD_CAP = 5000`；`QueryOrchestrator` step5~7 在这 ≤5,000 行上分组、透视、排序、计 total、切片。router 的 `fetch_cap_warning(len(本页行))` 拿本页行数（≤2,000）去比 5,000，永远不会触发。序时账 SQL 按 `voucher_date DESC` 截取，5,000 行只覆盖最后几天。
- 应联动：排序、分页、COUNT 下推到 SQL；分组 / 透视要么下推，要么在取数触顶时直接拒绝；触顶必须明示。

**AQ-04 回写目标记录不校验所属项目，可跨项目写**【实测（非变更）+ 代码】
- 证据：审计员 u_011abb97dd2d4101 只在 proj_fa90f498（65a9afa5）有 edit 权限。以 `project_id = 65a9afa5`、`wp_code = 【UAT】子公司B 的试算行 id 31ab9e28…`、`module = tb`、`cell_ref = A1` 调 `POST /api/custom-query/cell-writeback`，得 403「Only audited_amount (column G) is writable in trial_balance」——他项目的行已被定位并加锁，只是被列校验挡下；换随机 uuid 则 400「Trial balance record not found」。cell_ref 改成 G 列就会写入（本次未执行）。探针前后 UAT_B 4 行逐值不变。
- 根因：`cell_writeback` 只校验请求体 `project_id` 可见且为 edit；module 为 tb / adj / report 时把 `wp_code` 当记录 id，`snapshot_writer_modules.write_tb_cell` / `write_adj_cell` 按 `WHERE id = :id` 取行，不带项目条件。`writeback-confirm` 用 `target.wp_id or target.wp_code`，`_assert_writeback_authorized` 只核对调用方自报的 `target.project_id`。
- 应联动：所有回写取行都加 `project_id` 条件并与请求项目一致；非底稿 / 附注模块见 AQ-05。

**AQ-05 tb / adj 回写绕过发布门与调整分录服务**【代码】
- 证据：`write_tb_cell` 直接调 `services/tb_audited_writer.publish_rows(source="custom-query:tb-cell")`：没有二次确认、没有 publish_token 幂等、不发带 `publish_confirmed` 的 WORKPAPER_SAVED，报表 / 附注不会级联。`write_adj_cell` 直接 `UPDATE adjustments SET {列}`，不经调整分录服务（复核状态、ADJUSTMENT_APPROVED、TB 重算）。`write_report_cell` 写的是全库 0 行的 report_snapshot。
- 守卫盲区：`check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate` 只扫前端源码，后端直调 publish_rows 不在视野内。
- 现状：前端没有调用方，但端点对任何持 edit 权限的登录用户开放。
- 应联动：删除 tb / adj / report 三个回写模块；审定数只经 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`；调整分录只经调整分录服务。

**AQ-06 构建器对无 project_id 列的表不做项目过滤**【实测】
- 证据：e2e_manager（系统角色 manager，可访问 1 个项目）用构建器查 projects 得 142 行（含已删 57 个），可选 client_name、contract_amount、budget_hours 等字段；查 staff_members 得 152 行（姓名、工号、部门）。同一用户 `GET /api/projects/{华氏}` 返回 404「项目不存在」，`list-with-progress` 返回 0 个项目。
- 根因：`builder_scope.resolve_builder_scope` 把没有 `project_id` 列的表一律记入 `unscoped_tables`、不加过滤，并提示「平台级配置」。projects 以 `id` 为项目键、staff_members 是全员花名册，都不是配置表；真正的平台级配置只有 report_config。已删项目也不过滤。
- 应联动：projects 按 `id IN 可访问集合` 过滤并默认排除已删；staff_members 仅 admin / partner 可查，或只能经 work_hours 关联到可访问项目。

**AQ-19 构建器 account_chart JOIN 行数翻倍**【实测】
- 证据：华氏 `trial_balance LEFT JOIN account_chart` 返回 200 行（试算表 100 行），4101 盈余公积出现两次；库内华氏 100 个科目码各有 client、standard 两行。JOIN 后任何求和都翻倍。
- 根因：`table_whitelist.JOIN_WHITELIST` 中 trial_balance / tb_balance / tb_ledger → account_chart 只按（project_id, 科目码）关联，未限定 `account_chart.source`。
- 应联动：trial_balance 只连 standard，tb_balance / tb_ledger 只连 client；加「登记的 N:1 JOIN 不改变基表行数」守卫。

### 2.2 P1

**AQ-01 报表数据源金额恒空**【实测】
- 证据：华氏资产负债表 129 行，本期 / 上期金额全为 null；浏览器 B2 货币资金显示「-」，库内 financial_report BS-002 = 822,999,085.83。跨模块单元格 `report:balance_sheet|A1:C5` 0 行。
- 根因：`_query_report` 与 `module_cell_resolver._query_report_cells` 从 `report_snapshot` 取金额，该表全库 0 行；权威结果在 `financial_report`（2,464 行）。适配器还丢弃了取数器返回的 `source: "template_only"` 标记，用户无从得知金额不可用。
- 应联动：金额改读 financial_report；结果行下钻到报表页对应行次。

**AQ-07 调整分录数据源恒 500（枚举大小写）**【实测】
- 证据：华氏「审计调整分录(AJE)」「重分类调整(RCL)」均 500 INTERNAL_ERROR，同项目以小写 `aje` 查得 2 行；浏览器 B3 / B3b。`adj:aje|A1:F5` 返回 0 行（报错被吞）。
- 根因：PG 枚举 `adjustment_type` = {aje, cf, rje}；`_query_adjustments` 绑定 'AJE' / 'RCL'（来自 `CustomQueryDialog.executeQuery` 与 consol_unit 路由的大写值），`module_cell_resolver._query_adj_cells` 映射成大写；「RCL」在枚举中不存在（重分类是 rje）。叶子声明列 entry_number，实际列 adjustment_no。
- 应联动：统一小写枚举，RCL → rje；结果行下钻到调整分录页对应分录。

**AQ-08 报表行次数据源恒 500**【实测】
- 证据：500；浏览器 B4。
- 根因：`_query_report_lines` 选取并排序 `sort_order`，report_config 没有该列（实为 row_number）；`pagination.DEFAULT_SORT_BY_SOURCE['report_lines']` 同样写了 sort_order。

**AQ-09 弹窗把接口错误显示成「暂无数据」**【实测】
- 证据：AQ-07 / AQ-08 的 500 在弹窗里显示为提示「查询无结果」和空状态「当前项目「陕西华氏医药有限公司_2025」2025 年度暂无该数据源记录」（B3 / B3b / B4）；华氏实际有 2 条 AJE。
- 根因：`CustomQueryDialog.executeQuery` 设 `validateStatus: (s) => s < 600`，4xx / 5xx 响应体被当成数据，rows 为空即走无数据分支。页面版走 handleApiError，不受影响。
- 应联动：错误显示原因与追踪号，不落到空状态。

**AQ-10 附注数据源对真实项目恒空**【实测】
- 证据：指标树附注叶子 251 个，编号形如「五-1-1」；华氏、和平药房 disclosure_notes 章节形如「一、1」「八、1」，交集 0 / 251。点「五-1-1 货币资金」得 0 行（B5），而项目有「八、1 货币资金」。「附注（全部）」1,810 行，列名取第一张表的表头，其余表字段对不上列。`note:八、1|A1:D5` 0 行。
- 根因：`_build_disclosure_tree` 用合并附注模板种子编号；`_query_disclosure` 按 `note_section = :sid` 精确匹配；`_flatten_disclosure_note_rows` 只把第一张表的表头作为 columns；跨模块 note: 只读 consol_note_data。叶子声明列为 ['headers', 'rows']。
- 应联动：附注树按项目实际章节生成；按章节逐表返回、列随表头；结果行下钻到附注编辑器对应章节。

**AQ-11 「试算平衡表」「工作底稿」叶子读合并工作底稿表，单体项目恒空**【实测】
- 证据：华氏 tb_summary 0 行，ws_info / ws_elimination / ws_consol_tb 均 0 行；全库 consol_worksheet_data 只有辽宁卫生（37814426）1 行，查得 129 行。
- 根因：`_query_tb_summary` / `_query_worksheet` 只读 consol_worksheet_data；指标树对所有项目都展示这两组叶子，「试算平衡表」会被理解为单体试算。
- 应联动：单体项目的「试算平衡表」改读 trial_balance（与试算表页同口径）；合并类叶子只对合并项目展示。

**AQ-12 缺辅助核算、报表结果、合并数据源**【实测】
- 证据：构建器查 tb_aux_balance 得 400 TABLE_NOT_ALLOWED；业务视图没有辅助核算叶子。库内 tb_aux_balance 920,715 行，未删项目 tb_aux_ledger 4,470,438 行。
- 根因：`business_fetchers.EXACT_SOURCE_FETCHERS` 与 `TABLE_WHITELIST` 都没有登记辅助表；构建器也没有 financial_report 与合并表。设计（advanced-query-module R1）要求覆盖 tb / report / note / wp / aux 五域。
- 应联动：新增辅助余额 / 辅助明细数据源（按 aux_type 分组、走 get_active_filter），下钻到辅助账页面。

**AQ-13 页面版条件与字段选择被静默忽略**【实测】
- 证据：条件「借方发生额 > 100,000,000」请求体发出 `debit_amount_min`，结果首行仍是借方为空、贷方 12,436.99 的折旧凭证，与不加条件时相同（B12）；`audited_amount_min = 1e12`、`standard_account_code = 1001` 都返回全部 100 行；`columns = ['account_name']` 仍返回 6 列；AND / OR 选择不随请求发送。条件值输入框渲染宽度为 0，鼠标无法输入（B12a）。
- 根因：`CustomQueryTab.buildFilters` 生成 `{字段}_min / _max / __is_null / _from / _to` 等键，取数器只认 account_name、account_code、company_code、voucher_no、summary、date_from / date_to、status、cycle、wp_code 等固定键，其余键丢弃不报错；`columns` 参数无人消费；条件行 `el-input` 设 `flex:1; min-width:0`，在 301 px 的行里被挤到 0。指标树声明列与实际列不符（AQ-26），条件下拉里还会列出不存在的字段。
- 应联动：条件统一转为参数化谓词（复用 param_sql_builder），不认识的字段 / 算子返回 400；列选择生效。

**AQ-14 结果下钻全部断开**【实测 + 代码】
- 证据：页面版与构建器结果里下钻标记 GtIndexChip 0 个（B8）；弹窗底稿结果没有 cell_ref 链接（B10）。
- 根因：取数器从不给 ColumnMeta 挂 addr_id，编排器 `_finalize_columns` 只能得出 drillable = false；弹窗 `jumpToCell` 只在单元格选区结果里出现，且以 `?highlight=` 跳 WorkpaperEditor，而编辑器只读 `?sheet=` 与 `?cell=`（WorkpaperEditor.vue L495、L1319-1320）；余额、试算、序时账行没有到穿透页、凭证、辅助账、报表行、附注章节的跳转。
- 应联动：按数据源定义下钻目标——科目余额 / 试算 → 序时账穿透（LedgerPenetration）；序时账 → 凭证；报表行 → 报表页行次；附注 → 附注编辑器章节；底稿格 → WorkpaperEditor `?sheet=&cell=`。

**AQ-15 「ACNR 选字段」对查询没有作用**【实测】
- 证据：同一查询带 / 不带 `acnr_targets = ['D1/D1-2/F50']`，结果逐行相同（total 100）；构建器请求带非法 acnr_targets 仍返回 200。
- 根因：编排器 `_resolve_targets` 只校验 acnr_targets（非法 → 400），`business_fetcher` 忽略已解析的目标；构建器 `QueryDSL` 没有该字段，被 pydantic 丢弃。
- 应联动：选中的格要么成为结果列（按 addr_id 取值且可下钻），要么移除控件。

**AQ-16 查询模板：默认保存 500，公开模板他人不可见**【实测】
- 证据：scope = private / project 保存得 500「服务器内部错误」；浏览器「保存为模板（仅我可见）」500 且对话框不关（B13）；弹窗 💾 保存固定发 private，同样 500。public / global 保存成功，入库 scope 都是 public；admin 列表能看到自己的 2 条，审计员列表 0 条、按 id 读取 403 TEMPLATE_NOT_VISIBLE。team 不带 config.project_id 得 422。全库 custom_query_templates 0 行。
- 根因：router 先经 `TemplateScopeAdapter` 归一为 private / team / project / public，`template_service.save_template` 再用 `VALID_INPUT_SCOPES = {global, personal, team, public}` 校验，private / project 抛 TemplateInvalidError 且未被捕获；`list_templates` / `get_template` 以 `scope == 'global'` 判定公开，而入库值是 public；前端从不填 team 锚点；`templates/{id}/execute` 没有调用方；MyTemplatesDialog / SaveAsTemplateButton 零挂载。
- 应联动：scope 归一只留一处；可见性统一走 `template_service.is_visible`；执行模板走服务端 execute 端点（重新鉴权）。

**AQ-17 右键「跳模板溯源」恒 500**【实测】
- 证据：底稿 A1 行右键 → `address-resolve?uri=workpaper:A1` 500，提示「服务器暂时异常，正在重试...」，页面不跳转（B10）。
- 根因：`address_resolve` 查询 `wp_template_registry`，库里没有这张表，迁移与 ORM 也没有。
- 应联动：改用现有模板目录解析（实施时确认 `wp_template_registry_service` 的真实数据源），或改走 ACNR resolve。

**AQ-18 构建器不带项目上下文**【实测】
- 证据：在华氏试算表页打开构建器查 trial_balance，请求体无 project_id，结果跨项目，提示「当前角色可访问全部项目，本次查询未限定项目范围」（B8）。admin / partner 只能手写 `project_id eq <UUID>` 条件。
- 根因：`AdvancedQueryBuilder.buildPayload` 不发 project_id，`QueryDSL` 没有该字段，三个端点调用 `resolve_builder_scope` 都不传已实现的 `requested_project_id`。年度同样不带。
- 应联动：在项目页打开时默认限定当前项目与审计年度，可显式切到「跨项目」。

**AQ-20 导出不完整且无标注**【实测】
- 证据：页面版导出 100 行（结果共 5,000，库内 1,147,414），文件里没有截断说明；构建器导出和平药房序时账恰好 1,000 行，表头是英文键（voucher_no、debit_amount）。
- 根因：前端 `exportQueryResultToXlsx` 只导浏览器里已有的行；构建器 `export_excel` 复用 `_build_select`，受 DSL `limit ≤ 1000` 约束，文件内截断说明只在超过 `EXPORT_ROW_HARD_LIMIT`（100 万）时追加；表头直接写列键。`export_service`（流式 / 物化两种模式、来源列）只被引用了一个常量。
- 应联动：服务端全量流式导出，中文表头、来源与 addr_id 列，截断时在文件内写明。

**AQ-21 构建器只认系统角色，现场经理用不了**【实测】
- 证据：系统角色 auditor、项目角色 manager（edit）的 u_011abb97dd2d4101 调构建器 403；系统角色 manager 全库只有 e2e_manager 一个测试账号。另：e2e_manager 在构建器里可访问 1 个项目（OwnershipGuard 含 project_assignments），而 list-with-progress 给他 0 个项目，两套可见性口径不一致（根因需实施时确认）。
- 根因：`query_builder._QUERY_BUILDER_ROLES` 只看 `users.role`，平台的现场经理是系统 auditor + 项目 manager。弹窗另写一份 `ADVANCED_ROLES`，直接比对未归一的 `authStore.user.role`，不用 `useQueryBuilderAccess`；后端 403 文案「仅 admin / manager 可访问」漏了合伙人。
- 应联动：需要拍板构建器准入按什么判定（§6），前后端只留一处判据。

**AQ-23 查询会改写底稿文件**【代码，需实施时验证】
- 证据：`wp_sheet_preview` 与 `_query_workpaper_cell_range` 在 storage 无文件时调 `init_workpaper_from_template` 生成文件；单元格有未求值公式时 `_sync_recompute_xlsx_with_libreoffice` 把 LibreOffice 转换结果 `shutil.copy` 覆盖到原 storage 文件。全程不经保存协调器（无版本号、无事件、无锁），转换可能丢 xlsm 宏与数据验证。全库 1,738 张底稿没有一张带 univer_snapshot，选区查询都会走 xlsx 路径；本机已装 LibreOffice。本次未触发。
- 应联动：查询路径只读；重算结果放临时文件，不回写 storage。

**AQ-24 查询结果无法回写或引用到底稿 / 附注**【实测】
- 证据：cell-writeback、writeback-preview、writeback-confirm 在前端都没有调用方（apiPaths 只登记了 cellWriteback 常量），结果表没有「回写 / 引用到底稿」操作。writeback-preview 对试算目标返回 `found: false, error: missing_target`，同时给出 `enter_confirmation: true`。
- 根因：设计（advanced-query-module R13.6 / R14、enhancements-p1p2 R2）只落地了后端。
- 应联动：先修 AQ-04 / AQ-05；只开放底稿单元格与附注两类目标，流程为预览 → 确认（旧值复核）→ 审计留痕。

**AQ-32 既有测试守卫起不来或假绿**【实测】
- 证据：10 个后端测试文件 159 passed / 32 errors，错误全部是 `test_query_builder_endpoint.py`（16）与 `test_query_builder_joins.py`（16）的夹具：SQLite 建不了 `consol_note_template_push_log`（server_default `gen_random_uuid()`），构建器 HTTP 行为在 HEAD 上没有一条能跑的测试。前端 4 个文件 32 passed / 1 failed（advancedQueryFrontend-p7「legacy global 显示为公开」15 s 超时）。两个 e2e spec（advanced-query-module-e2e、advanced-query-consolidation-critical-path）在默认 `playwright.config.ts`（testDir ./e2e、无 testMatch）范围内，本次未运行，是否过期需实施时验证。
- 假绿：`test_query_builder_ref_both_column_variants_resolve` 以 `verify_existence=False` 断言 TB('1001','期末') 可解析，地址库实际判它无效；SQLite 夹具表达不了 PG 枚举、缺表、多数据集，AQ-01 / 02 / 07 / 08 / 16 / 17 都没有守卫。
- 应联动：口径类断言改用 PG 测试（`pg_only`），以本报告的库内真值为基线。

**AQ-37 弹窗不跟随当前项目页**【实测】
- 证据：在华氏试算表页打开弹窗，项目为「陕西华氏医药有限公司_2025 · 2025」；关闭后在应用内切到和平药房试算表页（路由 `/projects/5942c12e…/trial-balance`），再打开弹窗，项目仍是华氏（B14）。从仪表盘等非项目页打开时，弹窗自动选中项目列表的第一个项目。
- 根因：`CustomQueryDialog` 的 `watch(() => props.projectId)` 只在 `localProjectId` 为空时才采用路由项目；`loadProjectList` 在没有项目时取列表第一项。路由上下文被静默忽略，审计人员可能对着别的客户的数据查询。
- 应联动：每次打开都以当前路由项目为准（用户在弹窗内手动切换的除外）；非项目页打开时不自动选项目。

### 2.3 P2

**AQ-22 年度上下文回退到日历年（潜伏）**【代码 + 实测】ThreeColumnLayout 传 `route.query.year || 当年 − 1`；弹窗只在项目选项带 audit_year 时覆盖（list-with-progress 85 个项目中 73 个 audit_year 为空）；SheetCellRangePicker 回退 `new Date().getFullYear()`（2026）。数据项目当前都是 2025，暂不出错；2027 年起缺 audit_year 的项目会默认查错年度。应统一用后端 resolve_project_audit_year 下发的年度。

**AQ-25 不可达端点与组件**【实测】batch-execute、cross-sheet-trace、index-health、templates/{id}/execute、cell-writeback、writeback-preview / confirm 没有前端调用方；MyTemplatesDialog、SaveAsTemplateButton 零挂载；SheetCellRangePicker 的模块模式不可达（父组件从不传 moduleSource）；分组 / 透视没有界面，弹窗「转置」只在前端转前 50 行；`tb:detail|A1:G5` 把列名当 A1 格返回。裁决见 §4。

**AQ-26 试算表数据源缺 RJE 列、排序回落到科目名称**【实测】返回列只有期初、未审、审计调整、审定，没有重分类调整；华氏结果按科目名称排序（4301 专项储备、2711 专项应付款、1101 交易性金融资产…，B6）。根因：`_query_trial_balance` 未选 rje_adjustment；`DEFAULT_SORT_BY_SOURCE['tb_detail'] = account_code` 不在结果列，tie-breaker 候选（id / addr_id / account_code / row_code / voucher_no）也都不在，`_tie_breaker_keys` 回落为「全部列按列名排序」，首列 account_name 覆盖了 SQL 的科目码排序。指标树 tb_detail 声明的 account_code、closing_balance、debit_amount、credit_amount 在实际结果里都不存在。

**AQ-27 构建器生成的 tb_balance 公式引用无效**【实测】地址库 validate 判 TB('1001','审定数') 有效、TB('1122','期末') 无效（「列名「期末」无法识别」）。根因：`query_builder._derive_formula_refs` 对 tb_balance 生成 `TB('{客户科目码}','期末')`，「期末」不是登记的 TB 列名，tb_balance 也只有客户科目码。业务视图不生成公式引用。跨模块观察（需实施时验证）：legacy `/api/formula/execute` 对华氏求 TB('1001','审定数') 得 0.0（行内审定 100.00），TB('1002','审定数') 得 −297,771,168.89（等于未审数）——该执行器只加载 unadjusted_amount；无前端调用方，归公式管理域核对 L1 引擎口径。

**AQ-28 构建器 total 等于本页行数、无翻页、降序空值在前**【实测】和平药房序时账 offset 1,000 返回 total 1,000；借方降序首行借方为 NULL（1,147,414 行中 543,615 行借方为空）。前端没有翻页控件、从不发 offset。

**AQ-29 错误文案**【实测】422 返回 pydantic 英文明细（「Input should be greater than or equal to 1」）；模板保存 500 只有「服务器内部错误」；http 拦截器对确定性 5xx 自动重试并提示「服务器暂时异常，正在重试...」；构建器 403 文案漏了合伙人。

**AQ-30 模板删除是硬删除**【代码】`delete_template` 直接 `db.delete`；平台约定删除要二次确认并先进回收站（前端已有二次确认）。

**AQ-31 指标树加载**【实测】页面版用 depth=1 只做缓存探测，随后拉不带项目的全量树（698 KB / 0.9 s），报表与底稿树都是通用版；弹窗缓存未命中时同样拉全量；后端 branch 懒加载已实现（branch=workpaper 640 KB），前端没用。

**AQ-33 余额方向与符号口径没有带出**【代码 + 实测】`_query_account_balance` 不选 opening_direction / closing_direction；tb_balance 是 v1 带符号口径（贷方为负），trial_balance 是 v2 正数口径，两者在同一界面并列且无说明；构建器 tb_balance 字段清单也不含方向列。

**AQ-34 业务页面没有带上下文的查询入口**【代码】试算表、报表、附注、底稿、调整分录、合并页都没有「按此查询明细」类入口；模板库按钮传的 project_id 被 `onOpenCustomQueryEvent` 丢弃；仪表盘入口不带任何上下文。

**AQ-35 序时账「摘要」被标成「审定汇总」**【实测】`queryColumnLabels.ts` 把 summary 映射为「审定汇总」（本意是合并试算表的汇总列）；页面版表头与导出文件（第 7 列表头「审定汇总」）都受影响。

**AQ-36 弹窗无翻页、忽略后端 total**【实测】弹窗只有 200 / 500 / 1000 / 2000 四档上限，不发 offset、不显示 total；B7 显示「500 行 × 7 列，已达上限 500 行，可能被截断」，接口 total 为 1,624。

## 3. 逐功能体检：设计意图 → 实测 → 断点 → 应有的联动去向

设计出处简称：**M** = `_archive/05-business-features/advanced-query-module`；**C** = `advanced-query-consolidation`；**P** = `advanced-query-enhancements-p1p2`；**H** = `advanced-query-hardening-wiring-closure`；**DI** = `_archive/04-infra/advanced-query-disclosure-integration-hardening`（与 §6 的决定编号 D1–D9 无关）。证据文件均在 `evidence/`，截图在 `browser/`。

### 3.1 前端入口与交互

| # | 功能 / 入口 | 设计意图（出处） | 实测现状（证据） | 断点 | 应联动去向 |
|---|---|---|---|---|---|
| F1 | 侧栏「高级查询」弹窗 · 业务视图 | 全员可用的跨模块查询，带当前项目与年度（M R1 / R11.1） | 项目页打开带入项目与 2025（B1）；换项目页后仍停在旧项目（B14）；11 类数据源 2 类正确（覆盖矩阵 §2）；5xx 显示为「暂无数据」（B3 / B4）；无翻页（B7） | AQ-01 02 03 07 08 09 10 11 36 37 | 按当前页对象（科目、报表行、附注章节、底稿）预选数据源与过滤 |
| F2 | 弹窗「高级构建器」页签 | admin / manager 可用的白名单 DSL；权限不足可见不可点并给原因（M R11.2 / R11.6，H R2 / R11） | 只对 admin / manager / partner 系统角色渲染（v-if 隐藏，不是禁用）；不带项目，跨项目查询（B8）；SQL 聚合与库逐值一致 | AQ-06 18 19 21 28 | 项目页内默认限定当前项目与审计年度 |
| F3 | `/custom-query` 页面版（含模板库「自定义查询」页签） | 条件、字段选择、模板、导出、下钻（M R2 / R4 / R7 / R13，H R11.4） | 翻页可用；条件、列选择、AND / OR 被忽略，条件值框宽 0（B12 / B12a）；total ≤ 5,000（B11）；导出只导本页；模板默认保存 500（B13） | AQ-03 13 16 20 31 35 | 同 F1；模板可分享、可执行 |
| F4 | 页面版「高级构建器」按钮 | 同 F2 | 角色不足时禁用并显示中文原因，与后端 403 一致（vitest 通过） | AQ-21 | — |
| F5 | 仪表盘快捷操作、模板库「高级查询」按钮 | 从模板页一键查询该模板数据（P R14） | 能打开弹窗并预选数据源；传入的 project_id 被丢弃 | AQ-34 37 | 带项目打开 |
| F6 | ACNR 选字段（CustomQueryFieldPicker） | 与公式选址同一棵树，选中格作为查询字段（M R2） | 树能加载；选中的 addr_id 对结果零影响 | AQ-15 | 选中格成为结果列，且可下钻 |
| F7 | 底稿选区器（SheetCellRangePicker、wp-sheet-preview、cell_range） | 底稿 sheet 网格选区取数（P R9 / R11 / R13） | 1,738 张底稿没有一张带 univer_snapshot，全部走 xlsx；查询路径会生成或覆盖底稿文件（代码）；模块模式不可达 | AQ-23 25 | 只读预览；选区结果可回写、可引用 |
| F8 | 结果操作：转置、复制、导出 | 列标签单一真源、导出收敛（C R1 / R2），转置（M R6），流式导出（M R7 / R8） | 转置只在前端转前 50 行；中文表头可用，但「摘要」被标成「审定汇总」；所有导出都不完整 | AQ-20 25 35 | 服务端全量流式导出 |
| F9 | 结果下钻：cell_ref 链接、右键溯源、GtIndexChip、公式引用复制 | 结果格经 jump_route 下钻；cell_ref 跳底稿编辑器并高亮；右键跳模板详情（M R4，C R3） | 下钻标记 0 个；cell_ref 传 `?highlight=`，编辑器只读 `?cell=`；右键溯源 500（B10）；tb_balance 的公式引用无效 | AQ-14 17 27 | 余额 / 试算 → 序时账穿透；序时账 → 凭证；报表行 → 报表页行次；附注 → 附注编辑器章节；底稿格 → 编辑器定位 |
| F10 | 查询历史（弹窗 🕘） | 选区记忆（P R9） | 未实测（只存 localStorage） | — | — |
| F11 | 查询模板：页面版列表 / 保存 / 加载 / 删除，弹窗 💾 / 📑 | 保存、分享给项目组、执行时重新鉴权（M R13，H R8） | 私有 / 项目分享 500；公开模板他人不可见；没有任何预置模板（表 0 行）；硬删除；执行端点无调用方 | AQ-16 25 30 | 在弹窗内选用模板并按当前项目执行 |
| F12 | 构建器角色判据（useQueryBuilderAccess、弹窗 ADVANCED_ROLES、后端 _QUERY_BUILDER_ROLES） | 单一来源（H R11.1） | 三处集合逐值相同，但弹窗另写一份；只认系统角色 | AQ-21 | — |

### 3.2 后端端点与服务

| # | 端点 / 服务 | 设计意图（出处） | 实测现状（证据） | 断点 | 应联动去向 |
|---|---|---|---|---|---|
| B1 | `GET /api/query/schema` | 白名单 + 列分层 + PII 按角色（H R7） | 15 张表；PII 对 manager 隐藏 ✅；没有辅助核算、报表结果表 | AQ-12 | — |
| B2 | `POST /api/query/preview` | 预览 SQL 与实际执行一致（H R2） | 带作用域约束 ✅ | — | — |
| B3 | `POST /api/query/execute` | 项目作用域、JOIN 业务键、复杂度预算、语句超时（H R2 / R6） | SQL 层正确（api_builder_sql_join）；projects / staff 不过滤；account_chart JOIN 翻倍；四表不过滤数据集；total = 本页行数 | AQ-02 06 19 28 | — |
| B4 | `POST /api/query/export-excel` | 流式导出、截断在文件内标注（H R6.6，M R8） | write_only 流式写出 ✅；受 limit ≤ 1000 约束；英文表头 | AQ-20 | — |
| B5 | `GET /api/custom-query/indicators` | 骨架 + 分支懒加载（H R12） | depth=1 3.6 KB / 0.7 s ✅；附注叶子编号与项目不匹配；叶子声明列与实际列不符 | AQ-10 11 26 31 | — |
| B6 | `POST /api/custom-query/execute`（编排器） | 单一执行路径、真实分页、错误不以 2xx 返回（H R3 / R4 / R5） | 归属校验先行 ✅；未知源 / 非法排序中文错误码 ✅；5,000 行截断 | AQ-03 14 15 | — |
| B7 | 跨模块单元格源 `report:` / `note:` / `adj:` / `tb:` | 跨模块单元格级查询（P R13） | 报表、附注、调整 0 行；`tb:` 把列名当 A1 格返回 | AQ-01 07 10 25 | 见 D6 |
| B8 | `GET /wp-id-by-code` | 平台公用的编码 → 底稿 id | ✅（30 余处底稿 composable 在用） | — | 契约不能变 |
| B9 | `GET /wp-sheet-preview` | 只读网格预览（H R1.4） | 鉴权 ✅；无文件时调 init_workpaper_from_template 生成文件 | AQ-23 | — |
| B10 | 模板 CRUD、`templates/{id}/execute` | M R13，H R8 | 见 F11 | AQ-16 30 | — |
| B11 | `POST /batch-execute` | 多底稿批量查询（P R1） | 鉴权 ✅；无前端调用方 | AQ-25 | 见 D6 |
| B12 | `POST /cell-writeback` | 双向写回 + 审计（P R2，M R3 / R9 / R14）；对象归属与 edit 权限（DI R1 / R2） | 记录 id 不校验项目；tb / adj 绕过权威写入门；无前端调用方 | AQ-04 05 24 | 只写底稿格与附注 |
| B13 | `POST /writeback-preview` · `/writeback-confirm` | 预览 + 确认门（H R9） | 鉴权顺序 ✅；对试算目标给出 `found: false` 却仍 `enter_confirmation: true`；无前端调用方 | AQ-04 24 | — |
| B14 | `GET /cross-sheet-trace`（cross_sheet_trace_orchestrator） | 跨 sheet 公式追溯（P R3） | 鉴权 ✅；只读 univer_snapshot（全库 0）；无前端调用方 | AQ-25 | 见 D5 |
| B15 | `GET /index-health` | GIN 索引健康（P R5） | 200，size_bytes 为 null | AQ-25 | — |
| B16 | `GET /address-resolve` | 右键溯源到模板详情（C R3.3） | 500，`wp_template_registry` 表不存在 | AQ-17 | — |
| B17 | 审计留痕（audit_helper） | 回写 / 溯源逐次记录，执行按 60 s 节流（M R14.4，P R7） | ✅ 本次会话产生的越权拒绝 16、预算拒绝 2、PII 拒绝 1、执行 14 条均已落 audit_log_entries，Redis 队列积压 0（audit_log_check.json） | — | — |
| B18 | 查询缓存（query_cache） | 高频短 TTL，键含项目与作用域（M R12） | 未实测命中 | — | — |

## 4. 零引用 / 不可达模块裁决（接线或删除）

归档 spec 所说的 7 个零引用模块现在都有生产 importer（全仓现扫，`evidence/api_source_matrix.txt` 末段）。真正的问题换成了「有端点、没入口」和「有入口、没效果」。

| 对象 | 生产调用方 | 用户可达 | 建议 | 理由 |
|---|---|---|---|---|
| `param_sql_builder` | builder_dsl（谓词构造、取值转换、WHERE 组合） | 是（构建器条件实测有效） | **保留**，并作为业务视图条件的唯一谓词来源 | 「值 → 参数化谓词」的单一真源；AQ-13 的修法正好复用它 |
| `cross_sheet_trace_orchestrator` + `GET /cross-sheet-trace` | 仅该端点 | 否 | **删除**（待 D5 拍板） | 只读 univer_snapshot，全库 0 / 1,738 张底稿有此数据，接线也只能返回空链；`cross_sheet_resolver` 被 `wp_formula_eval_service` 使用，保留 |
| 指标树 `depth` / `branch` 懒加载 | indicators 端点 | 部分：前端只把 depth=1 当缓存探测 | **接线** | 首屏改用骨架，展开附注 / 底稿大类时按分支取；附注分支同时改为按项目章节生成（AQ-10 / 31） |
| `grouping_engine` / `pivot_engine` | 编排器惰性导入 | 否（前端从不发 group / pivot） | **保留并加门禁** | 现在基于 ≤ 5,000 行样本计算（AQ-03）；取数触顶即拒绝，界面按 D4 |
| `export_service` | query_builder 只引用常量 EXPORT_ROW_HARD_LIMIT | 否 | **接线** | 服务端全量流式导出（AQ-20）需要它的流式 / 物化两种模式 |
| `writeback_preview` + `snapshot_writer`（workpaper、note） | cell-writeback、writeback-confirm、workpaper_save_orchestrator | 否 | **接线**（先修 AQ-04 / 05） | 「查询结果回写到底稿 / 附注」是设计承诺（M R13.6 / R14），底稿与附注两条写路径实现完整 |
| `snapshot_writer_modules` 的 tb / adj / report 写回 | snapshot_writer | 否（API 可调） | **删除**（D3） | 绕过发布门与调整分录服务；report_snapshot 是空表 |
| `POST /batch-execute` | — | 否 | **删除**（D6） | 无入口；逐底稿走 xlsx 路径，带 AQ-23 的改写风险 |
| `GET /index-health` | — | 否 | **不动**（运维端点，不在联动范围） | size_bytes 为 null 记为已知问题 |
| `POST /templates/{id}/execute` | — | 否 | **接线** | 模板执行应走服务端重新鉴权、复用主链路（H R8.6） |
| `MyTemplatesDialog` | 零挂载 | 否 | **接线**到弹窗，替代「📑 模板」跳页 | 弹窗是主入口，跳页会丢项目上下文 |
| `SaveAsTemplateButton` | 零挂载 | 否 | **删除** | 弹窗已有 💾 保存，页面版已有保存对话框 |
| 选区器模块模式 + `report:` / `note:` / `adj:` / `tb:` 源族 | 编排器分派、选区器 | 否 | **删除**（D6） | 与常规数据源重复且全部断开（AQ-01 / 07 / 10）；删除前核对 module_cell_resolver 中被回写复用的列映射 |
| `MetabaseDashboard` / `DrillDownNavigator` | 零挂载 | 否 | 不在本轮范围 | 用户不可见；embed-url 鉴权归原 spec |

## 5. 九个维度结论

| 维度 | 结论 | 断点 |
|---|---|---|
| ① 可达性与上下文 | 入口齐全（侧栏、仪表盘、模板库、独立页），但只带项目、不带对象；弹窗换项目页后不更新；年度回退日历年（潜伏） | AQ-18 22 34 37 |
| ② 数据源与口径 | 11 个取数器 2 个正确；四表不经数据集过滤；无辅助核算；报表金额读空表；合并类叶子对单体恒空；方向列不带出 | AQ-01 02 07 08 10 11 12 26 33 |
| ③ 查询构建 | 构建器 SQL 层逐值正确；业务视图 5,000 行截断后在内存里排序、分组、计数；条件与列选择被忽略；JOIN 翻倍；预算与超时提示正常，没有误拦正常查询 | AQ-03 13 19 28 |
| ④ 模板 | 默认保存 500、公开模板他人不可见、硬删除、没有预置模板 | AQ-16 30 |
| ⑤ 结果去向 | 下钻全断；没有完整导出；回写无入口且 tb / adj 绕门；公式引用一半无效 | AQ-04 05 14 17 20 24 27 |
| ⑥ 零引用模块 | 见 §4 | AQ-25 |
| ⑦ 权限 | 业务视图项目隔离有效；构建器 projects / staff 泄露；回写记录不校验项目；准入只认系统角色；前后端角色集合逐值相同，但弹窗多了一份 | AQ-04 06 21 |
| ⑧ Metabase | 两组件零挂载，不在范围 | — |
| ⑨ 可用性 | 5xx 显示为无数据；422 英文明细；摘要列标错；响应 0.7–1.8 s（但被截断掩盖了真实体量）；指标树全量 698 KB | AQ-09 29 31 35 36 |

## 6. 需要拍板的决定（交 design 步骤确认）

| # | 决定 | 建议 | 理由 |
|---|---|---|---|
| D1 | 构建器准入按什么判定 | 放开到「至少一个项目的 project_users.role = manager 且 permission_level = edit」的成员，作用域限其可访问项目；admin / partner 不变 | 现场经理在系统里是 auditor，现规则下构建器只有一个测试账号能用 |
| D2 | staff_members 是否留在构建器 | 只对 admin / partner 开放（manager 403） | 全员花名册不属于项目数据，PII 分层已把 manager 排除在电话 / 邮箱外 |
| D3 | 回写保留哪些模块 | 只保留底稿单元格（workpaper）与合并附注（note）；删除 tb / adj / report | 审定数只经 publish-to-tb、调整分录只经调整分录服务是平台铁律；report_snapshot 是空表 |
| D4 | 业务视图分组 / 透视 | 本轮不出界面；后端在取数触顶时直接 400，提示改用构建器 | 构建器的 SQL 聚合已与库逐值一致；内存分组在大表上必错 |
| D5 | 跨 sheet 公式追溯 | 删除端点与 orchestrator，保留 cross_sheet_resolver | 数据源全库为空；公式来源改在下钻到底稿格后由编辑器展示 |
| D6 | 无入口的跨模块单元格源、选区器模块模式、batch-execute、SaveAsTemplateButton | 删除 | 与常规数据源重复或无人使用，且全部断开；符合「功能收敛、核心做到极致」 |
| D7 | 合并类叶子 | 单体项目隐藏合并工作底稿类叶子；「试算平衡表」叶子对单体改读 trial_balance | 单体项目点了恒空，名称又会被理解成单体试算表 |
| D8 | 模板可见范围 | 对外只保留「仅我可见 / 指定项目共享 / 公开」三档，team 不出现在前端（后端兼容读取历史值） | 前端从不提供 team 锚点，后端又要求必填 |
| D9 | 模板删除 | 软删 + 回收站（需确认平台回收站是否支持模板类型） | 平台约定删除要二次确认并先进回收站 |

## 7. 建议修复顺序与实施约束（供 design / plan）

| 批次 | 内容 | 验收基线（库内真值，实施时重算） |
|---|---|---|
| 批 1 口径与隔离（P0） | AQ-02 四表统一走 get_active_filter（业务视图与构建器）；AQ-03 排序 / 分页 / COUNT 下推 SQL，取数触顶时分组 / 透视 / 排序直接拒绝；AQ-06 projects 按可访问 id 过滤并默认排除已删，staff 按 D2；AQ-19 account_chart JOIN 限定 source | 宜宾临港科目余额 812 行 / −659,481.68；和平药房序时账 total 1,147,414、借方降序首行 241,944,666.92；e2e_manager 构建器 projects 只返回其可访问项目；华氏 trial_balance ⋈ account_chart 100 行 |
| 批 2 写入安全（P0 / P1） | AQ-04 回写取行一律带 project_id 并与请求一致；AQ-05 按 D3 删除 tb / adj / report 回写，后端加守卫：`tb_audited_writer.publish_rows` 只允许登记的发布门调用方；AQ-23 查询路径不写 storage | 跨项目回写 403 / 404 且不锁他项目行；publish_rows 调用点守卫的变异能打红 |
| 批 3 数据源（P1 / P2） | AQ-01 报表金额读 financial_report；AQ-07 调整分录小写枚举、重分类映射 rje；AQ-08 报表行次用 row_number；AQ-10 附注树按项目实际章节生成、逐表返回列；AQ-11 按 D7；AQ-12 新增辅助余额 / 辅助明细源（按 aux_type）；AQ-26 试算加 RJE、按科目码排序；AQ-33 余额带方向 | 华氏 BS-002 货币资金 822,999,085.83；华氏 AJE 2 行；华氏「八、1 货币资金」有表数据；华氏 TB Σ审定 2,033,180,355.49 保持不变 |
| 批 4 交互、上下文与模板（P1 / P2） | AQ-09 错误显示原因与追踪号；AQ-13 条件转参数化谓词、未知字段 400、列选择生效；AQ-15 ACNR 选字段生效或移除；AQ-16 / 30 模板 scope 合并为一处、可见性统一、软删；AQ-17 溯源改用现有模板目录；AQ-18 构建器默认当前项目与审计年度；AQ-21 准入按 D1，判据只留一处；AQ-37 / 22 弹窗跟随路由项目，年度统一取 resolve_project_audit_year；AQ-28 / 36 翻页并显示真实 total；AQ-29 422 中文化；AQ-31 指标树按项目骨架 + 分支 | 浏览器复测 B3 / B4 / B12 / B13 / B14 场景 |
| 批 5 结果去向（P1 / P2） | AQ-14 下钻：余额 / 试算 → 序时账穿透（LedgerPenetration），序时账 → 凭证，报表行 → 报表页行次，附注 → 附注编辑器章节，底稿格 → WorkpaperEditor `?sheet=&cell=`；AQ-20 服务端全量流式导出（中文表头、来源列、截断标注）；AQ-24 结果回写底稿格 / 附注（预览 → 确认 → 审计）；AQ-27 公式引用只生成地址库认可的语法；AQ-34 业务页加「查询此对象」入口；AQ-35 摘要标签 | 和平药房序时账可完整导出 1,147,414 行（或按上限截断并在文件内写明）；每类结果行至少一条下钻浏览器实测落到目标页并定位 |
| 批 6 收敛与守卫（P1 / P2） | AQ-25：按 §4、D5、D6 删除或接线；AQ-32 修 SQLite 夹具让构建器测试能跑，口径类守卫用 pg_only；两个 e2e spec 复核后纳入 | 构建器端点 / JOIN 测试恢复运行；口径守卫基于真 PG |

实施约束：

- `backend/app/routers/custom_query.py` 现 3,086 行，`backend/scripts/file_size_whitelist.txt` 基线 2,966，门禁上限为基线 × 1.05 ≈ 3,114，只剩约 28 行余量。改取数器前要先把 14 个 `_query_*` 下沉到 `services/custom_query/fetchers/`（白名单注释里已规划的拆分方向），新文件 ≤ 800 行。
- 接近上限的文件（门禁同口径 `splitlines` 计数）：`snapshot_writer.py` 759 行（上限 800）、`writeback_preview.py` 710、`table_whitelist.py` 700、`query_orchestrator.py` 668；前端 `CustomQueryTab.vue` 1,245、`CustomQueryDialog.vue` 1,061、`AdvancedQueryBuilder.vue` 900（上限 1,500）。
- 不能改的契约：`wp-id-by-code` 的请求与响应（30 余处底稿 composable 在用）；`execute` 响应形状（`TestExecuteContractBaseline`）。
- 口径测试必须用真 PG：SQLite 表达不了枚举、缺表、多数据集，本报告的 P0 / P1 大多在 SQLite 下测不出来。
- 写入型验收只用【测试】/【UAT】项目；共享开发环境不重启 start-dev，改带自动保存页面的源码前先把浏览器停在 about:blank，临时产物放 `tmp_<任务名>/`。

## 8. 需实施时验证

- 两个 e2e spec 是否过期（在默认 playwright 配置范围内，本次未运行）。
- 查询缓存命中与失效（未实测）；弹窗查询历史（localStorage，未实测）。
- writeback-confirm 的确认门对非底稿目标的放行情况；cell-writeback 的 G 列真实写入（本次刻意未执行）。
- 合并项目查询（consol_unit、ws_*、合并附注）：现库 consol_scope 为 0。
- 查询路径的 LibreOffice 重算覆盖 storage xlsx（AQ-23）：代码确认，未触发。
- legacy `/api/formula/execute` 的 TB() 只读未审数（AQ-27 跨模块观察）：无前端调用方，归公式管理域核对。
- qc / readonly / eqcr 三个角色：库内没有此类用户，只按代码判定。
- e2e_manager 在构建器可访问 1 个项目、list-with-progress 却为 0 个：两套可见性口径的差异来源。
- `/index-health` 的 size_bytes 为 null 的原因。

## 9. 证据索引

完整索引见 `00-ground-truth.md` §4：`evidence/` 下 16 个文件（活体 API 输出、只读 SQL 结果、测试结果、审计日志核对），`browser/` 下 15 张截图（B1–B14）。
