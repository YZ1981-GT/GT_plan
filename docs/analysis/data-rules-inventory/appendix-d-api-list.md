# 附录 D：后端接口清单（全部）

> 由脚本从运行时的 FastAPI 应用对象抽取（`app.main.app.routes`，含路由前缀），不是按源码猜的路径。
> 「鉴权」列 = 该接口依赖链里的鉴权类依赖（如 `get_current_user`、`require_project_access(edit)`）；为空表示依赖链里没有识别到鉴权依赖，
> 不一定等于没鉴权（可能在函数体内校验、或靠令牌参数），见正文 4.4。
> 「前端」列 = 前端源码里能找到同形路径字面量的文件数；0 表示没找到直接写出的路径，可能是拼接出来的，也可能确实没人调。
> 现算：2676 个接口，分布在 621 个代码文件。Excel 版见同目录 `appendix-d-api-list.csv`。

## D11 合并（177 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| PUT | `/api/cell-comments/{project_id}/{year}` |  | `routers/consol_cell_comments.py:131` `save_cell_comment` | get_current_user、require_project_access(edit) | 2 |
| DELETE | `/api/cell-comments/{project_id}/{year}/{comment_id}` |  | `routers/consol_cell_comments.py:186` `delete_cell_comment` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/cell-comments/{project_id}/{year}/{module}` |  | `routers/consol_cell_comments.py:91` `get_module_comments` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/cell-comments/{project_id}/{year}/{module}/{sheet_key}` |  | `routers/consol_cell_comments.py:111` `get_sheet_comments` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consol-note-formulas` | 按章节列出合并附注公式（单元格位置、公式、来源：自动种子 / 人工）。 | `routers/consol_note_formulas.py:51` `get_note_formulas` | get_current_user | 1 |
| POST | `/api/consol-note-formulas` |  | `routers/consol_note_formulas.py:73` `add_note_formula` | get_current_user、require_role | 1 |
| POST | `/api/consol-note-formulas/seed` | 按当前模板与合并口径报表配置重新种子化（幂等；不覆盖人工公式、不补回人工删除的）。 | `routers/consol_note_formulas.py:131` `reseed_note_formulas` | get_current_user、require_role | 1 |
| DELETE | `/api/consol-note-formulas/{formula_id}` | 删除（软删；自动种子不再补回该单元格）。须带 ``expected_version``。 | `routers/consol_note_formulas.py:112` `remove_note_formula` | get_current_user、require_role | 1 |
| PUT | `/api/consol-note-formulas/{formula_id}` | 改公式 ⇒ 来源变为「人工」（之后自动种子不再覆盖该单元格）。须带 ``expected_version``。 | `routers/consol_note_formulas.py:92` `edit_note_formula` | get_current_user、require_role | 1 |
| POST | `/api/consol-note-sections/aggregate/{project_id}/{year}` | 汇总指定单位的数据到目标单元格：只取各下级已保存的合并附注（个别数由「📋 明细映射」/「🔄 重新汇总」 | `routers/consol_note_sections.py:948` `aggregate_data` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consol-note-sections/apply-formulas/{project_id}/{year}` | 逐章节按共享公式内核刷新所有附注，并隔离单章节失败。 | `routers/consol_note_sections.py:894` `apply_all_formulas` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consol-note-sections/audit-all/{project_id}/{year}` | 对所有附注表格执行公式审核 | `routers/consol_note_sections.py:555` `audit_all_notes` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consol-note-sections/audit/{project_id}/{year}/{section_id}` | 对指定附注表格执行公式审核（前端传入当前编辑的数据） | `routers/consol_note_sections.py:719` `audit_single_note` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consol-note-sections/breakdown/{project_id}/{year}/{section_id}` | 有公式的单元格：个别数汇总 / 调整 / 抵销 / 合并数，及所选汇总节点各直接子节点贡献（需求 6.3）。 | `routers/consol_note_sections.py:143` `get_note_breakdown` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consol-note-sections/check-rules/{project_id}/{year}/{section_id}` | 返回指定章节的 check_rules 声明 + 按所选节点已保存合并附注的执行结果。 | `routers/consol_note_sections.py:1047` `get_check_rules` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consol-note-sections/data/{project_id}/{year}/{section_id}` | 加载用户已保存的附注数据。根节点无专属行时兼容读取历史项目级行。 | `routers/consol_note_sections.py:395` `get_note_data` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/consol-note-sections/data/{project_id}/{year}/{section_id}` | 保存用户编辑的附注数据，带节点键时只写节点专属行。 | `routers/consol_note_sections.py:420` `save_note_data` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consol-note-sections/fill-by-formula/{project_id}/{year}/{section_id}` | 把合并数写入该章节已保存数据；按项目标准解析模板并清除待更新标记。 | `routers/consol_note_sections.py:163` `fill_note_by_formula` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consol-note-sections/refresh/{project_id}/{year}/{section_id}` | 刷新并持久化当前节点章节，保留旧 rows/message 字段兼容客户端。 | `routers/consol_note_sections.py:512` `refresh_note_by_formula` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consol-note-sections/{standard}` | 获取所有章节（按父章节分组的树形结构） | `routers/consol_note_sections.py:194` `get_all_sections` | — | 2 |
| GET | `/api/consol-note-sections/{standard}/{section_id}` | 获取单个表格节点详情（含表头和模板行） | `routers/consol_note_sections.py:226` `get_section_detail` | — | 2 |
| GET | `/api/consol-note-templates` | 列出合并附注明细模板。 | `routers/consol_note_detail_templates.py:124` `api_list_templates` | get_current_user | 1 |
| POST | `/api/consol-note-templates` | 创建合并附注明细模板（附首版本 v1）。 | `routers/consol_note_detail_templates.py:99` `api_create_template` | get_current_user | 1 |
| DELETE | `/api/consol-note-templates/{template_id}` | 软删除模板。 | `routers/consol_note_detail_templates.py:206` `api_delete_template` | get_current_user | 1 |
| GET | `/api/consol-note-templates/{template_id}` | 获取单个合并附注明细模板详情。 | `routers/consol_note_detail_templates.py:141` `api_get_template` | get_current_user | 1 |
| POST | `/api/consol-note-templates/{template_id}/check-row-deletion` | 检测删除模板行的影响（受影响规则数和企业数）。 | `routers/consol_note_detail_templates.py:222` `api_check_row_deletion` | get_current_user | 1 |
| GET | `/api/consol-note-templates/{template_id}/versions` | 查看模板版本历史。 | `routers/consol_note_detail_templates.py:176` `api_get_versions` | get_current_user | 1 |
| POST | `/api/consol-note-templates/{template_id}/versions` | 追加模板新版本（不可变）。 | `routers/consol_note_detail_templates.py:154` `api_add_version` | get_current_user | 1 |
| PUT | `/api/consol-note-templates/{template_id}/visibility` | 修改模板可见范围。 | `routers/consol_note_detail_templates.py:189` `api_change_visibility` | get_current_user | 0 |
| POST | `/api/consol-worksheet-data/g7-linkage/{project_id}/{year}/import` | 确认导入 G7 基础数据；默认只填空值，不覆盖合并侧已有值。 | `routers/consol_worksheet_data.py:95` `apply_g7_linkage_import` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consol-worksheet-data/g7-linkage/{project_id}/{year}/preview` | 预览 G7→合并工作底稿映射，不产生写入。 | `routers/consol_worksheet_data.py:79` `get_g7_linkage_preview` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consol-worksheet-data/g7-linkage/{project_id}/{year}/stale` | G7 联动 stale 只读薄端点（Task 6.1）。 | `routers/consol_worksheet_data.py:64` `get_g7_linkage_stale` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/consol-worksheet-data/{project_id}/{year}` |  | `routers/consol_worksheet_data.py:303` `get_all_worksheet_data` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/consol-worksheet-data/{project_id}/{year}/prior-year/{sheet_key}` | 提取上年数：从 year-1 的期末数据中提取，作为本年期初 | `routers/consol_worksheet_data.py:328` `get_prior_year_data` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/consol-worksheet-data/{project_id}/{year}/{sheet_key}` |  | `routers/consol_worksheet_data.py:176` `get_worksheet_data` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/consol-worksheet-data/{project_id}/{year}/{sheet_key}` |  | `routers/consol_worksheet_data.py:197` `save_worksheet_data` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/component-auditor/auditors` |  | `routers/component_auditor.py:46` `list_auditors` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/component-auditor/auditors` |  | `routers/component_auditor.py:55` `create_auditor_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/component-auditor/auditors/{auditor_id}` |  | `routers/component_auditor.py:79` `delete_auditor_route` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/consolidation/component-auditor/auditors/{auditor_id}` |  | `routers/component_auditor.py:65` `update_auditor_route` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/component-auditor/dashboard` |  | `routers/component_auditor.py:183` `get_dashboard_route` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/component-auditor/instructions` |  | `routers/component_auditor.py:91` `list_instructions` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/component-auditor/instructions` |  | `routers/component_auditor.py:101` `create_instruction_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/component-auditor/instructions/{instruction_id}` |  | `routers/component_auditor.py:125` `delete_instruction_route` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/consolidation/component-auditor/instructions/{instruction_id}` |  | `routers/component_auditor.py:111` `update_instruction_route` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/component-auditor/results` |  | `routers/component_auditor.py:137` `list_results` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/component-auditor/results` |  | `routers/component_auditor.py:147` `create_result_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/component-auditor/results/{result_id}` |  | `routers/component_auditor.py:171` `delete_result_route` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/consolidation/component-auditor/results/{result_id}` |  | `routers/component_auditor.py:157` `update_result_route` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/eliminations` |  | `routers/consolidation.py:38` `list_eliminations` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/eliminations` |  | `routers/consolidation.py:203` `create_elimination` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/consolidation/eliminations/auto-generate` | 内部抵消表自动汇总 [R11.3 / Phase 2 B3] | `routers/consolidation.py:353` `auto_generate_eliminations` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/consolidation/eliminations/equity-method/calculate` | 模拟权益法计算 [R11.1] | `routers/consolidation.py:397` `calculate_equity_method_route` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/consolidation/eliminations/generate-from-worksheet` | 旧版客户端分组预览兼容入口；写入已迁移到服务端版本化接口。 | `routers/consolidation.py:78` `generate_eliminations_from_worksheet` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/eliminations/legacy-sheet` | 旧版明细表（``consol_worksheet_data['elimination']``）自定义行检测：条数、分组预 | `routers/consolidation.py:166` `elimination_legacy_sheet` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/eliminations/legacy-sheet/convert` | 旧版自定义行转为草稿分录（``origin='legacy_sheet'``）；转不了的逐条返回原因，重复调用不重复转入 | `routers/consolidation.py:182` `convert_elimination_legacy_sheet` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/eliminations/summary-center/year` | 合并抵消分录表汇总中心 [R11.2] — 5 个区域分类汇总 | `routers/consolidation.py:342` `elimination_summary_center` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/consolidation/eliminations/summary/year` |  | `routers/consolidation.py:332` `elimination_summary` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/eliminations/tree-lines` | 本企业树全部未删分录的明细行（含下级合并项目承载的，只读）+ 合计 + 本项目承载的差额节点。 | `routers/consolidation.py:62` `elimination_tree_lines` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/eliminations/worksheet-generate` | 锁定并复核工作表版本后，服务端重算 canonical groups 并生成草稿。 | `routers/consolidation.py:130` `generate_eliminations_from_server_worksheets` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consolidation/eliminations/worksheet-preview` | 按服务端当前工作表和期望版本预览，不信任浏览器计算结果。 | `routers/consolidation.py:104` `preview_eliminations_from_server_worksheets` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| DELETE | `/api/consolidation/eliminations/{entry_id}` |  | `routers/consolidation.py:246` `delete_elimination` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/consolidation/eliminations/{entry_id}` |  | `routers/consolidation.py:216` `get_elimination` | get_current_user、require_project_access(readonly) | 4 |
| PUT | `/api/consolidation/eliminations/{entry_id}` |  | `routers/consolidation.py:229` `update_elimination` | get_current_user、require_project_access(edit) | 4 |
| POST | `/api/consolidation/eliminations/{entry_id}/review` | 复核：提交审批 / 审批 / 驳回 / 撤销审批。审批与撤销审批记审计日志，并触发合并推送 | `routers/consolidation.py:263` `review_elimination` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/forex` |  | `routers/forex.py:17` `list_forex` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/forex` |  | `routers/forex.py:27` `create_or_update_forex_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/forex/{forex_id}` |  | `routers/forex.py:42` `delete_forex_route` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/consolidation/goodwill` |  | `routers/goodwill.py:24` `list_goodwill` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/goodwill` |  | `routers/goodwill.py:34` `create_goodwill_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/goodwill/{goodwill_id}` |  | `routers/goodwill.py:72` `delete_goodwill_route` | get_current_user、require_project_access(edit) | 4 |
| PUT | `/api/consolidation/goodwill/{goodwill_id}` |  | `routers/goodwill.py:44` `update_goodwill_route` | get_current_user、require_project_access(edit) | 4 |
| POST | `/api/consolidation/goodwill/{goodwill_id}/impairment` |  | `routers/goodwill.py:58` `record_impairment_route` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/consolidation/internal-trade/arap` |  | `routers/internal_trade.py:84` `list_arap` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/internal-trade/arap` |  | `routers/internal_trade.py:94` `create_arap_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/internal-trade/arap/{arap_id}` |  | `routers/internal_trade.py:118` `delete_arap_route` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/consolidation/internal-trade/arap/{arap_id}` |  | `routers/internal_trade.py:104` `update_arap_route` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/internal-trade/matrix` |  | `routers/internal_trade.py:130` `get_matrix` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/internal-trade/trades` |  | `routers/internal_trade.py:38` `list_trades` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/internal-trade/trades` |  | `routers/internal_trade.py:48` `create_trade_route` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/consolidation/internal-trade/trades/{trade_id}` |  | `routers/internal_trade.py:72` `delete_trade_route` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/consolidation/internal-trade/trades/{trade_id}` |  | `routers/internal_trade.py:58` `update_trade_route` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/minority-interest` |  | `routers/minority_interest.py:23` `list_mi` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/minority-interest` |  | `routers/minority_interest.py:44` `create_or_update_mi_route` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/consolidation/minority-interest/calculate` | 计算少数股东权益（仅计算，不存储） | `routers/minority_interest.py:33` `calculate_mi_route` | — | 0 |
| DELETE | `/api/consolidation/minority-interest/{mi_id}` |  | `routers/minority_interest.py:56` `delete_mi_route` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/consolidation/notes/local-export` | 合并附注本地数据导出（data_exchange）。 | `routers/consol_notes.py:436` `export_consol_notes_local` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/consolidation/notes/{project_id}/config/consol-note-gray` | 读取试算表事件自动刷新合并附注的开关（项目级 opt-in / 全局 / 生效值）。 | `routers/consol_notes.py:250` `get_consol_note_gray` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/consolidation/notes/{project_id}/config/consol-note-gray` | 设置试算表事件自动刷新合并附注的项目级 opt-in（现场经理+ 编辑权限）。 | `routers/consol_notes.py:286` `update_consol_note_gray` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/consolidation/notes/{project_id}/{year}/push-template` | 下推集团附注模板到各子企业：在子企业单体附注对应的表上打行身份、补缺的模板行（不改已有行名与数值）。 | `routers/consol_notes.py:357` `push_template_to_subsidiaries` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consolidation/notes/{project_id}/{year}/reaggregate` | 重新汇总：所选节点（缺省为根合并节点）子树逐节点更新 —— 数据叶子按已确认映射从单体附注拉数、 | `routers/consol_notes.py:151` `reaggregate_consol_notes` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consolidation/notes/{project_id}/{year}/reaggregate-async` | 提交耐久重新汇总任务；实际执行时 worker 会重新校验权限、合并锁、节点范围和 DAG。 | `routers/consol_notes.py:63` `reaggregate_consol_notes_async` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/post-elimination/{project_id}/{year}` | 四张抵销后表的只读 canonical projection（自动列来自 approved 分录，manual over | `routers/consol_post_elimination.py:27` `get_post_elimination_projection` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/readiness/{project_id}/{year}` | 七域五态 readiness：事实与阻断分离，不执行重算。 | `routers/consol_readiness.py:21` `get_consol_readiness` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/readiness/{project_id}/{year}/role-views` | 角色视图：编制 / 审批 / 重大判断 / 质控四桶待办（批 6.4 / ADR-CRW-006 R8）。 | `routers/consol_readiness.py:42` `get_consol_role_views` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/report/{project_id}/{year}/{account_code}/consol-breakdown` | 获取某合并报表行次 / 科目的下级构成（报表级穿透）. | `routers/consol_report_breakdown.py:33` `get_report_breakdown` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/reports/generate` | 兼容入口：把“生成合并报表”收敛到持久 operation，不再直接覆盖正式报表。 | `routers/consol_report.py:46` `generate_consol_reports` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/reports/{project_id}/{year}` | 获取合并报表数据（支持按节点读时计算）。 | `routers/consol_report.py:126` `get_consol_report` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/reports/{project_id}/{year}/artifacts` | 为指定已发布 report run 一次生成不可变 Excel artifact；重复请求复用同一文件。 | `routers/consol_report.py:417` `create_consol_artifact` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/reports/{project_id}/{year}/artifacts/{artifact_id}/download` | 下载既有 ready artifact；重验 size/hash，绝不现场重算。 | `routers/consol_report.py:436` `download_consol_artifact` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/reports/{project_id}/{year}/balance-check` | 合并资产负债表平衡校验 | `routers/consol_report.py:337` `balance_check` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/reports/{project_id}/{year}/workpaper` | 兼容入口：为最近已发布 report run 生成不可变合并工作底稿。 | `routers/consol_report.py:465` `create_consol_workpaper` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/reports/{project_id}/{year}/workpaper/download` | 兼容入口：下载最近正式 run 的既有工作底稿；没有 artifact 时明确失败，不重算。 | `routers/consol_report.py:496` `download_consol_workpaper` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/scope` |  | `routers/consol_scope.py:31` `list_scope` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/consolidation/scope` |  | `routers/consol_scope.py:41` `create_scope` | get_current_user、require_project_access(edit) | 3 |
| POST | `/api/consolidation/scope/batch` |  | `routers/consol_scope.py:116` `batch_update` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/scope/summary` |  | `routers/consol_scope.py:139` `scope_summary` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/consolidation/scope/{scope_id}` |  | `routers/consol_scope.py:93` `delete_scope` | get_current_user、require_project_access(edit) | 4 |
| PUT | `/api/consolidation/scope/{scope_id}` |  | `routers/consol_scope.py:67` `update_scope` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/consolidation/trial` |  | `routers/consol_trial.py:24` `get_trial_balance_list` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/trial/consistency-check` | 一致性校验：按科目自然方向汇总借方性质与贷方性质合计判平衡。 | `routers/consol_trial.py:62` `check_consistency` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/trial/diff/local-export` | 合并差额表本地导出（data_exchange）。 | `routers/consol_trial.py:206` `export_diff_local` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/consolidation/trial/local-export` | 合并试算表本地数据导出（data_exchange：原始元值 + marker）。 | `routers/consol_trial.py:177` `export_trial_local` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/consolidation/trial/recalculate` | 触发全量重算 | `routers/consol_trial.py:38` `trigger_recalculate` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/trial/reconciliation` | B2 单一事实源对账：worksheet 根节点 consolidated_amount vs consol_trial | `routers/consol_trial.py:93` `get_reconciliation` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/consolidation/trial/stale-status` | 合并 trial 陈旧状态（P1）：子公司 TB 变更后母公司 trial 是否需重算。 | `routers/consol_trial.py:73` `get_trial_stale_status` | get_current_user、require_project_access(readonly) | 0 |
| DELETE | `/api/consolidation/trial/{trial_id}` |  | `routers/consol_trial.py:119` `delete_trial_row` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/consolidation/worksheet/accounts` | 差额录入可选科目（需求 9.3）：本树数据叶子试算表科目 ∪ 本树分录明细行科目。 | `routers/consol_worksheet.py:103` `get_accounts` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/aggregate` | 节点汇总查询（mode=self\|children\|descendants） | `routers/consol_worksheet.py:267` `aggregate_node` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/drill/companies` | 穿透到企业构成 | `routers/consol_worksheet.py:285` `drill_companies` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/drill/eliminations` | 穿透到抵消分录 | `routers/consol_worksheet.py:301` `drill_eliminations` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/drill/entries` | 报表行 → 分录明细（§五 穿透）：只计已审批、已归属到该节点子树的分录；贡献之和 = 该行该列。 | `routers/consol_worksheet.py:209` `drill_entries` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/drill/individual` | 报表行 → 各数据节点个别数（§五 审定汇总列穿透）：子树内每个数据叶子对该行的求值。 | `routers/consol_worksheet.py:231` `drill_individual` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/drill/trial-balance` | 穿透到末端企业试算表 | `routers/consol_worksheet.py:317` `drill_trial_balance` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/entry-summary` | 合并抵销分录汇总表（spec consol-autotree-linkage-closure R9）：与合并试算同一计算 | `routers/consol_worksheet.py:412` `get_entry_summary` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/node-amounts` | 某节点按科目归一后的金额（需求 9.3）：实时按计算口径求值，与重算写入差额表的数一致，不写库。 | `routers/consol_worksheet.py:126` `get_node_amounts` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/worksheet/pivot` | 透视查询 | `routers/consol_worksheet.py:331` `pivot_query` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/pivot/export` | Excel 导出透视表 | `routers/consol_worksheet.py:351` `pivot_export` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/pivot/templates` | 列出查询模板 | `routers/consol_worksheet.py:399` `get_templates` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/worksheet/pivot/templates` | 保存查询模板 | `routers/consol_worksheet.py:379` `create_template` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/consolidation/worksheet/recalc` | 全量重算差额表 | `routers/consol_worksheet.py:251` `recalc_worksheet` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/worksheet/report-breakdown` | 报表差额表（§六）：列 = 汇总节点的直接子节点（数据 / 差额 / 下级汇总），合计 = 该节点合并数。 | `routers/consol_worksheet.py:186` `get_report_breakdown` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/report-trial` | 合并试算平衡表页（spec consol-elimination-single-source-push §五）：按报表行 | `routers/consol_worksheet.py:159` `get_report_trial` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/worksheet/tree` | 企业树 + 合并方式识别 + 诊断 + 年度（consol-tree-three-code-autobuild 需求 3 | `routers/consol_worksheet.py:81` `get_tree` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/completeness-check` | 子公司数据完整度前置校验（需求 6 / T5 / EH5）. | `routers/report_trace.py:117` `consol_completeness_check` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/lock` |  | `routers/report_trace.py:54` `lock_project` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/{project_id}/lock-status` |  | `routers/report_trace.py:96` `check_lock` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/module-status` | 合并模块开发状态（P3 防误用标记） | `routers/report_trace.py:102` `get_module_status` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/consolidation/{project_id}/scope-confirmation/confirm` |  | `routers/consol_scope_confirmation.py:43` `post_scope_confirmation` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/{project_id}/scope-confirmation/preview` |  | `routers/consol_scope_confirmation.py:28` `get_scope_confirmation_preview` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/snapshots` | 列出项目的合并快照（最近 20 条），附 v2 manifest 概要（批 7 任务 7.4）。 | `routers/report_trace.py:263` `list_snapshots` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/snapshots` | 创建合并签字冻结快照（ADR-CONSOL-206 / 需求 8 / 5E.2+5E.4；批 7 任务 7.2+7.3） | `routers/report_trace.py:304` `create_snapshot` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/{project_id}/snapshots/{snapshot_id}/compare` | 对比"签字时合并数" vs 当前实时合并数，逐科目展示差异（只读，5E.3）。 | `routers/report_trace.py:435` `compare_snapshot` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/snapshots/{snapshot_id}/download` | 下载签字快照的还原后 JSON（只读，批 7 任务 7.4）。 | `routers/report_trace.py:447` `download_snapshot` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/snapshots/{snapshot_id}/restore` | 还原"签字时合并数" + SHA-256 完整性校验（只读，5E.3 / S8）。 | `routers/report_trace.py:420` `restore_snapshot` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/unlock` |  | `routers/report_trace.py:75` `unlock_project` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/consolidation/{project_id}/{year}/operations` |  | `routers/consol_operation.py:80` `get_operations` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/{year}/operations` |  | `routers/consol_operation.py:44` `create_operation` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/{project_id}/{year}/operations/{operation_id}` |  | `routers/consol_operation.py:96` `get_operation_status` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/{year}/operations/{operation_id}/cancel` |  | `routers/consol_operation.py:117` `cancel_operation_route` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/consolidation/{project_id}/{year}/push` |  | `routers/consol_push.py:56` `trigger_push` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/{project_id}/{year}/push-runs` |  | `routers/consol_push.py:98` `get_push_runs` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/{year}/push-status` |  | `routers/consol_push.py:109` `get_push_status` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/{year}/refresh-all` | 兼容入口：立即持久化 queued operation，后台数据库 worker 认领。 | `routers/consol_refresh.py:36` `trigger_refresh_all` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/consolidation/{project_id}/{year}/refresh-status/{job_id}` | 先查持久 operation；保留旧进程内 job 作为迁移期只读兼容。 | `routers/consol_refresh.py:75` `get_refresh_status` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/consolidation/{project_id}/{year}/workpaper-shell` | 读取合并底稿壳（负责人 / 复核状态 / 版本 / 指针）。不含业务 JSON。 | `routers/consol_workpaper.py:101` `read_shell` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/ensure` | 幂等创建合并底稿壳（无 artifact 时建占位壳），便于先指派负责人 / 发起复核。 | `routers/consol_workpaper.py:186` `ensure_shell` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/evidence-target` | 把合并某 sheet/node/row/col 解析成稳定证据坐标（身份构造是纯函数，不写库）。 | `routers/consol_workpaper.py:119` `resolve_evidence_target` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/consolidation/{project_id}/{year}/workpaper-shell/owner` | 指派 / 取消合并底稿壳负责人（编制人）。 | `routers/consol_workpaper.py:210` `assign_owner` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/recycle` | 把合并底稿壳（两层）移入回收站（kind=consol）。 | `routers/consol_workpaper.py:326` `recycle_shell` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/restore` | 从回收站恢复合并底稿壳（只恢复因 kind=consol 移入的）。 | `routers/consol_workpaper.py:348` `restore_shell` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/review` | 复核处理：通过（level1_passed）或退回修改（level1_rejected + 原因）。 | `routers/consol_workpaper.py:292` `review_shell` | check_consol_lock、get_current_user、require_project_access(re | 0 |
| PUT | `/api/consolidation/{project_id}/{year}/workpaper-shell/reviewer` | 指派 / 取消合并底稿壳复核人。 | `routers/consol_workpaper.py:235` `assign_reviewer` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/consolidation/{project_id}/{year}/workpaper-shell/submit-review` | 编制人提交复核（not_submitted / 退回修改 → 待一级复核）。 | `routers/consol_workpaper.py:263` `submit_review` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/projects/{project_id}/consol-note-detail-refresh/apply` | 按已确认映射规则将来源行转换后写入合并附注。409 表示来源已变化。 | `routers/consol_note_detail_templates.py:558` `api_apply_detail_refresh` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/consol-note-detail-refresh/auto-map` | ⚡ 自动映射：未绑定的章节按来源建议建模板并绑定，能自动确认的结构组确认映射；其余组回报待人工确认 | `routers/consol_note_detail_templates.py:344` `api_auto_map` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/consol-note-detail-refresh/confirm-mapping` | 确认映射——校验 + 写规则 + 批量绑定。409 表示来源已变化需重新预览。 | `routers/consol_note_detail_templates.py:468` `api_confirm_mapping` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/consol-note-detail-refresh/preview` | 预览明细刷新：读取来源、检测 stale、生成建议。只读不写数据（stale 标记除外）。 | `routers/consol_note_detail_templates.py:299` `api_preview_detail_refresh` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/consol-note-detail-refresh/suggest-template` | 扫描来源并生成模板行建议（按频率和金额排序）。 | `routers/consol_note_detail_templates.py:321` `api_suggest_template` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/consol-note-mapping/rules` | 列出项目的活跃映射规则。 | `routers/consol_note_detail_templates.py:396` `api_get_rules` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/consol-note-mapping/rules` | 创建映射规则（v1）。 | `routers/consol_note_detail_templates.py:408` `api_create_rule` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| PUT | `/api/projects/{project_id}/consol-note-mapping/rules/{rule_id}/deactivate` | 停用映射规则。 | `routers/consol_note_detail_templates.py:435` `api_deactivate_rule` | check_consol_lock、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/consol-note-mapping/rules/{rule_id}/versions` | 查看映射规则版本历史。 | `routers/consol_note_detail_templates.py:454` `api_get_rule_versions` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/consol-note-template-binding` | 查看当前项目所有章节的模板绑定。 | `routers/consol_note_detail_templates.py:262` `api_get_bindings` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/consol-note-template-binding/{section_id}` | 查看单个章节的模板绑定。 | `routers/consol_note_detail_templates.py:272` `api_get_binding` | get_current_user、require_project_access(readonly) | 3 |
| PUT | `/api/projects/{project_id}/consol-note-template-binding/{section_id}` | 项目绑定/切换合并附注明细模板版本。切换已有绑定需 confirm=true。 | `routers/consol_note_detail_templates.py:236` `api_bind_template_version` | check_consol_lock、get_current_user、require_project_access(ed | 3 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/i3/goodwill-impairment` | I-F4 商誉减值 DCF 模型辅助分析（LLM stub 实现） | `routers/wp_i_goodwill.py:393` `i3_goodwill_impairment_analysis` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |

## D10 底稿在线编辑同步（52 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/adopt-substrate` | 反向收敛：以**已发布** substrate 为准，覆盖本 entry 的 HTML store。 | `routers/wp_sync_router.py:1160` `adopt_substrate` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/first-publication` | 该 (wp, entry) 尚无 published representation 时**按需发布首版**；已有则原样返 | `routers/wp_sync_router.py:1096` `ensure_first_publication` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/materialize` | 唯一 `EditorLaunchDescriptor`（Property 11）。签名 `document.url` 在 | `routers/wp_sync_router.py:1247` `materialize` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/materialize-from-store` | store 型 entry：服务端直取投影 + store 指纹直通（业务见 `store_materialize`）。 | `routers/wp_sync_router.py:1353` `materialize_from_store` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/operations/{operation_id}` | 按**调用方给的** id 授权，再 canonicalize（禁止授权前 canonical 跳转）。 | `routers/wp_sync_router.py:2549` `get_operation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/operations/{operation_id}/conflicts` | canonical primary 的冲突分组。requested/canonical ids 都留在响应里。 | `routers/wp_sync_router.py:2667` `get_operation_conflicts` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/operations/{operation_id}/resolve` | 人工裁决。八项乐观锁 → 折叠 → 唯一 commit 边界发布（Task 27）。 | `routers/wp_sync_router.py:2791` `resolve_conflicts` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/operations/{operation_id}/retry` | 从 `application.incoming_artifact_id` 重试 —— 零 forcesave、不新建 o | `routers/wp_sync_router.py:2883` `retry_operation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/operations/{operation_id}/timeline` | 脱敏 append-only timeline。 | `routers/wp_sync_router.py:2700` `get_operation_timeline` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/pending-mutations` | `flushHtml()` 的落点。**不推进 revision**（AC 3.1）。 | `routers/wp_sync_router.py:983` `create_pending_mutation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/readiness` | 只读返回静态裁决、目标底稿运行时供给和最新验收证据。 | `routers/wp_sync_router.py:1024` `read_entry_readiness` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases` | read-mode guard 通过后才查 case（AC 5.8 / Property 45）。 | `routers/wp_sync_router.py:2100` `list_recovery_cases` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/claim` | authorization-first claim：一个事务里 request + shell + applicatio | `routers/wp_sync_router.py:2139` `claim_recovery_case` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/download` | download-only 签发的 claim 的**唯一**消费方。 | `routers/wp_sync_router.py:2377` `download_recovery_artifact` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/download-only` | 只终结 case 并签发**短期最小权限**下载 claim；三实体保持为 0（AC 5.8）。 | `routers/wp_sync_router.py:2321` `terminate_recovery_download_only` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/timeline` | recovery case 的**独立** timeline（AC 13.5 / 13.6）。 | `routers/wp_sync_router.py:2746` `get_recovery_case_timeline` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/rooms/{room_id}/close-intents` | clean close 的唯一入口。leader 仲裁与 exactly-one close-capture 在 Tas | `routers/wp_sync_router.py:1885` `create_close_intent` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/rooms/{room_id}/confirm-descriptor` | `onDocumentReady` 之后的幂等确认。成功前不得 forcesave（Property 11）。 | `routers/wp_sync_router.py:1687` `confirm_descriptor` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/rooms/{room_id}/forcesave` | 202 accepted：frozen request + `application_id=NULL` shell 先落 | `routers/wp_sync_router.py:1733` `request_forcesave` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/rooms/{room_id}/participants/{participant_id}/leave` | participant **主动离开**：只释放这一条 lease（`active/closing → left`）。 | `routers/wp_sync_router.py:1952` `leave_room` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/store-projection` | G4-0c：store-backed entry 的 projection **服务端现算**（只读）。 | `routers/wp_sync_router.py:1056` `read_store_projection` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/versions/{version_id}/rollback` | `version_id` 是 immutable opaque content-version UUID。 | `routers/wp_sync_router.py:2920` `rollback_version` | get_current_user | 0 |
| GET | `/api/workpaper-sync/rooms/{room_id}/contents` | OO `document.url` 消费方：短 TTL token → representation artifact  | `routers/wp_sync_router.py:1503` `get_room_contents` | — | 0 |
| POST | `/api/workpaper-sync/rooms/{room_id}/onlyoffice-callback` | DocServer 回调。**只**委派 Task 22 的 `CallbackDeliveryService`。 | `routers/wp_sync_router.py:2988` `post_room_onlyoffice_callback` | — | 0 |
| GET | `/api/workpapers/onlyoffice/health` | 底稿模块 OnlyOffice 健康预检。 | `routers/wp_onlyoffice_router.py:528` `get_onlyoffice_health` | — | 97 |
| POST | `/api/workpapers/{wp_id}/d2-sync/forcesave` | 命令 OnlyOffice 把当前编辑**落盘**，并等到磁盘文件真的变化才返回。 | `routers/d2_sync_router.py:359` `d2_forcesave` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d2-sync/pull-from-excel` | OnlyOffice → 结构化视图：读回 Excel 的受管值并落库。 | `routers/d2_sync_router.py:572` `d2_pull_from_excel` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d2-sync/push-to-excel` | 结构化视图 → OnlyOffice：把明细行写进 OO 打开的那份 xlsx。 | `routers/d2_sync_router.py:301` `d2_push_to_excel` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/d2-sync/status` | 两侧真实状态 —— 前端据此显示能力，**不再读硬编码常量**。 | `routers/d2_sync_router.py:264` `d2_sync_status` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/import-structured` | 导入离线填写的 docx，解析占位符值并写回 checklist_responses。 | `routers/wp_onlyoffice_router.py:1707` `import_structured_docx` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback` | OnlyOffice 编辑回调端点。 | `routers/wp_onlyoffice_router.py:1232` `post_sheet_onlyoffice_callback` | — | 0 |
| GET | `/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-config` | 返回 OnlyOffice 编辑器配置（doc_key / download_url / callback_url /  | `routers/wp_onlyoffice_router.py:656` `get_sheet_onlyoffice_config` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents` | WOPI GetFile — JWT 鉴权后返回 xlsx 内容。 | `routers/wp_onlyoffice_router.py:1004` `get_sheet_wopi_contents` | — | 0 |
| GET | `/api/workpapers/{wp_id}/template-structure` | 返回 word-template 底稿的解析后模板结构 + 已填数据。 | `routers/wp_onlyoffice_router.py:562` `get_template_structure` | dedicated_wp_gate、get_current_user | 19 |
| GET | `/api/workpapers/{wp_id}/whole-excel-grid` | 完整Excel 降级展示：按整册 wp_code 取模板 xlsx，抽取指定 sheet 网格。 | `routers/wp_onlyoffice_router.py:916` `get_whole_excel_grid` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/wp-template-overrides/edit-sessions/{session_id}/callback` | OnlyOffice 保存回调 —— 把编辑结果落成新的覆盖版本。 | `routers/wp_template_override_router.py:404` `session_callback` | — | 0 |
| GET | `/api/wp-template-overrides/edit-sessions/{session_id}/contents` | DocServer 拉取工作副本。**机对机，不带 Bearer。** | `routers/wp_template_override_router.py:383` `get_session_contents` | — | 0 |
| DELETE | `/api/wp-template-overrides/{wp_code}/current` | 删除覆盖 —— 该作用域下不再有当前版本，解析回落下一层（Requirement 4.5）。 | `routers/wp_template_override_router.py:610` `delete_current_override` | get_current_user、require_role | 1 |
| POST | `/api/wp-template-overrides/{wp_code}/edit-session` | 建立 OnlyOffice 模板编辑会话（整本模式）。 | `routers/wp_template_override_router.py:318` `create_edit_session` | get_current_user、require_role | 1 |
| GET | `/api/wp-template-overrides/{wp_code}/resolution` | 当前生效的模板来自哪一层（Requirement 2.2 / 5.3）。 | `routers/wp_template_override_router.py:213` `get_template_resolution` | get_current_user | 1 |
| POST | `/api/wp-template-overrides/{wp_code}/upload` | 上传替换 —— 给 127 份不可在线编辑的模板同样的覆盖能力（AC 5.5）。 | `routers/wp_template_override_router.py:493` `upload_replacement` | get_current_user、require_role | 1 |
| GET | `/api/wp-template-overrides/{wp_code}/versions` | 某作用域下的全部版本，新的在前。非当前版本仍可读（Requirement 4.2）。 | `routers/wp_template_override_router.py:230` `list_versions` | get_current_user | 1 |
| POST | `/api/wp-template-overrides/{wp_code}/versions/{version_id}/promote` | 回滚 —— 把某个历史版本置为当前，不删任何版本记录（Requirement 4.3）。 | `routers/wp_template_override_router.py:566` `promote_version` | get_current_user、require_role | 1 |
| POST | `/wopi/ds-callback/{file_id}` | Document Server 保存回调端点（向后兼容）。 | `api/wopi.py:430` `ds_callback` | — | 0 |
| GET | `/wopi/files/{file_id}` | CheckFileInfo — 返回文件元信息 JSON。 | `api/wopi.py:115` `wopi_check_file_info` | — | 0 |
| POST | `/wopi/files/{file_id}` | Lock/Unlock/RefreshLock — 通过 X-WOPI-Override 头区分操作。 | `api/wopi.py:238` `wopi_lock_operations` | — | 0 |
| GET | `/wopi/files/{file_id}/contents` | GetFile — 返回文件二进制内容。 | `api/wopi.py:161` `wopi_get_file` | — | 0 |
| POST | `/wopi/files/{file_id}/contents` | PutFile — 接收原始字节并保存文件内容。 | `api/wopi.py:192` `wopi_put_file` | — | 0 |
| DELETE | `/wopi/files/{file_id}/lock` | 管理员强制解锁（不需要 lock_id） | `api/wopi.py:284` `force_unlock` | get_current_user | 0 |
| GET | `/wopi/files/{file_id}/lock-status` | 查询文件锁状态（运维监控用） | `api/wopi.py:315` `get_lock_status` | get_current_user | 0 |
| GET | `/wopi/health` | WOPI 服务健康检查 — 前端用于探测在线编辑可用性 | `api/wopi.py:363` `wopi_health` | — | 0 |
| GET | `/wopi/stats` | WOPI 运维统计（锁数量、活跃编辑会话） | `api/wopi.py:383` `wopi_stats` | get_current_user | 0 |

## D07 附注（135 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/account-note-mapping/{project_id}` |  | `routers/account_note_mapping.py:56` `get_mappings` | get_current_user、require_project_access(readonly) | 0 |
| PUT | `/api/account-note-mapping/{project_id}` |  | `routers/account_note_mapping.py:65` `save_mapping` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/account-note-mapping/{project_id}/auto-generate` | 自动生成映射：从试算表科目名和附注模板行名进行模糊匹配 | `routers/account_note_mapping.py:90` `auto_generate_mappings` | get_current_user、require_project_access(edit) | 0 |
| DELETE | `/api/account-note-mapping/{project_id}/{mapping_id}` |  | `routers/account_note_mapping.py:83` `delete_mapping` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/disclosure-notes/capabilities` | 附注模块能力清单（供前端按真实能力决定入口是否可用）。 | `routers/disclosure_notes.py:1249` `get_capabilities` | get_current_user | 3 |
| PUT | `/api/disclosure-notes/findings/{validation_id}/confirm` | 确认校验发现为"已确认-无需修改" | `routers/disclosure_notes.py:1142` `confirm_finding` | get_current_user | 8 |
| GET | `/api/disclosure-notes/format-config` | 致同附注 Word 排版规范单一真源（21 项参数）. | `routers/disclosure_notes.py:164` `get_format_config` | get_current_user | 2 |
| POST | `/api/disclosure-notes/generate` | 生成附注初稿。 | `routers/disclosure_notes.py:229` `generate_notes` | get_current_user | 2 |
| PUT | `/api/disclosure-notes/{note_id}` | 更新附注章节内容。 | `routers/disclosure_notes.py:902` `update_note` | get_current_user | 3 |
| GET | `/api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace` | 单元格溯源：返回 binding 元数据 + 公式展开 + 命中数据行采样. | `routers/disclosure_notes.py:623` `trace_cell` | get_current_user | 1 |
| POST | `/api/disclosure-notes/{project_id}/ai/check-completeness` | 披露完整性建议（typed LLM 结果；失败不伪装成建议）。 | `routers/note_ai.py:394` `check_completeness` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/ai/check-expression` | 表述规范性检查（接入 vLLM） | `routers/note_ai.py:436` `check_expression` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/ai/complete` | 智能续写（POST body，接入 vLLM + RAG：用户点选的知识文档 + 上年附注）。 | `routers/note_ai.py:479` `ai_complete` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/ai/generate-analysis` | 基于服务端权威事实包生成变动分析草稿。 | `routers/note_ai.py:311` `generate_analysis` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/ai/generate-policy` | 会计政策草稿（typed LLM 结果；失败不返回占位正文）。 | `routers/note_ai.py:245` `generate_policy` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/ai/rewrite` | 改写选中文本（接入 vLLM + RAG：用户点选的知识文档 + 上年附注）。 | `routers/note_ai.py:564` `ai_rewrite` | get_current_user、require_project_access(readonly) | 7 |
| PUT | `/api/disclosure-notes/{project_id}/formula-gray` | 设置项目级附注公式灰度开关。 | `routers/disclosure_notes.py:370` `set_formula_gray` | get_current_user、require_role | 3 |
| GET | `/api/disclosure-notes/{project_id}/sections` |  | `routers/note_trim.py:35` `get_sections` | get_current_user、require_project_access(readonly) | 4 |
| PUT | `/api/disclosure-notes/{project_id}/sections/trim` |  | `routers/note_trim.py:49` `save_trim` | get_current_user、require_note_edit_access(False) | 9 |
| GET | `/api/disclosure-notes/{project_id}/sections/trim-scheme` |  | `routers/note_trim.py:64` `get_trim_scheme` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/upload-history` | 历史附注文件（Word/PDF）上传与解析 —— **尚未实现**，恒返回机器可读 501。 | `routers/disclosure_notes.py:1223` `upload_history` | — | 3 |
| GET | `/api/disclosure-notes/{project_id}/wp-mapping` |  | `routers/note_wp_mapping.py:28` `get_mapping` | get_current_user、require_project_access(readonly) | 4 |
| PUT | `/api/disclosure-notes/{project_id}/wp-mapping` |  | `routers/note_wp_mapping.py:38` `update_mapping` | get_current_user、require_note_edit_access(False) | 4 |
| GET | `/api/disclosure-notes/{project_id}/{year}` | 获取附注目录树 | `routers/disclosure_notes.py:297` `get_notes_tree` | get_current_user、require_project_access(readonly) | 6 |
| POST | `/api/disclosure-notes/{project_id}/{year}/auto-trim` | 自动裁剪：扫描 binding 列出科目，TrialBalance 全 0 → 标 not_applicable. | `routers/note_trim.py:78` `auto_trim` | get_current_user、require_note_edit_access(False) | 8 |
| POST | `/api/disclosure-notes/{project_id}/{year}/batch-ai-fill` | 兼容入口：创建 DB-backed 附注预填任务并立即返回 snapshot。 | `routers/disclosure_notes.py:1773` `batch_ai_fill_notes` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/disclosure-notes/{project_id}/{year}/deleted` | 列出已软删除的附注章节，供恢复使用。 | `routers/disclosure_notes.py:765` `list_deleted_sections` | get_current_user、require_project_access(readonly) | 8 |
| POST | `/api/disclosure-notes/{project_id}/{year}/export-word` | 导出附注为 Word 文档。 | `routers/disclosure_notes.py:1175` `export_word` | get_current_user | 7 |
| GET | `/api/disclosure-notes/{project_id}/{year}/formula-health` | 附注公式/校验管线健康度诊断（只读，不跑规则、不写库）。 | `routers/disclosure_notes.py:786` `formula_health` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/{year}/headless-refresh` | 离屏刷新附注（底稿披露表 → 附注），返回执行器逐章节结果：``ok`` / ``stage`` / ``outcome | `routers/note_headless_refresh.py:34` `headless_refresh` | get_current_user、require_note_edit_access(False) | 7 |
| GET | `/api/disclosure-notes/{project_id}/{year}/linkage-gaps` | 只读诊断：列出「有报表↔附注勾稽但无写值 linkage」的章节（spec R5 / Task 5.1）。 | `routers/disclosure_notes.py:421` `get_linkage_gaps` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/disclosure-notes/{project_id}/{year}/note-linkage/consistency` | 校验附注合计与试算表审定数一致性（按 account_name 匹配）。 | `routers/disclosure_notes.py:1547` `note_linkage_consistency` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/disclosure-notes/{project_id}/{year}/note-linkage/one-click-preview` | 一键取数预览（只读）：列出每节可从试算表带入的审定数。 | `routers/disclosure_notes.py:1565` `note_linkage_one_click_preview` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/disclosure-notes/{project_id}/{year}/offline-export` | 导出附注离线编辑包 (C.0.17). | `routers/note_offline.py:24` `export_offline_package` | get_current_user、require_project_access(readonly) | 8 |
| POST | `/api/disclosure-notes/{project_id}/{year}/offline-import/execute` | 执行导入 (C.0.18). | `routers/note_offline.py:84` `execute_import` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/disclosure-notes/{project_id}/{year}/offline-import/preview` | 校验并预览导入 (C.0.18). | `routers/note_offline.py:60` `preview_import` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers` | 附注从底稿取数（「🔄 刷新 / 🔁 全部刷新 / 📝 生成附注」前调用；spec note-pull-header-fo | `routers/disclosure_notes.py:457` `pull_from_workpapers` | get_current_user、require_note_edit_access(False) | 9 |
| GET | `/api/disclosure-notes/{project_id}/{year}/readiness` | 附注「披露同步 / 校验就绪度」看板（只读，附注联动复盘 P0-1）。 | `routers/disclosure_notes.py:338` `get_notes_readiness` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/{year}/refresh-all-bindings` | 全量 binding 取数刷新：对所有已有 binding 的章节走 _build_with_binding 重取数。 | `routers/note_wp_mapping.py:72` `refresh_all_bindings` | get_current_user、require_note_edit_access(False) | 8 |
| POST | `/api/disclosure-notes/{project_id}/{year}/refresh-from-disclosure` | 底稿披露表 → 附注的同步状态（只读）。 | `routers/disclosure_notes.py:490` `refresh_from_disclosure` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers` |  | `routers/note_wp_mapping.py:52` `refresh_from_workpapers` | get_current_user、require_note_edit_access(False) | 8 |
| PATCH | `/api/disclosure-notes/{project_id}/{year}/restore/{note_id}` | 恢复已删除的附注章节。 | `routers/disclosure_notes.py:1067` `restore_section` | get_current_user | 6 |
| GET | `/api/disclosure-notes/{project_id}/{year}/section-numbers` | 获取附注章节编号映射（供前端渲染序号）。 | `routers/disclosure_notes.py:683` `get_section_numbers` | get_current_user、require_project_access(readonly) | 8 |
| DELETE | `/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}` | 软删除指定附注章节。 | `routers/disclosure_notes.py:965` `delete_section` | get_current_user | 6 |
| PATCH | `/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}` | 部分更新附注章节字段（如 status → 用 is_empty 标记排除导出）。 | `routers/disclosure_notes.py:1010` `patch_section` | get_current_user | 6 |
| POST | `/api/disclosure-notes/{project_id}/{year}/validate` | 执行附注校验 | `routers/disclosure_notes.py:1118` `validate_notes` | get_current_user、require_note_edit_access(False) | 8 |
| GET | `/api/disclosure-notes/{project_id}/{year}/validation-results` | 获取最新校验结果。 | `routers/disclosure_notes.py:591` `get_validation_results` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/disclosure-notes/{project_id}/{year}/wp-sync-status` | 某底稿对应附注章节的同步状态（只读，附注联动复盘 P0-2）。 | `routers/disclosure_notes.py:520` `get_wp_sync_status` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode` | 改单元格模式 = 用户编辑附注：附注编辑门禁 + 只认本项目本年度的章节 + 以当前用户盖「最近一次编辑」 | `routers/note_wp_mapping.py:225` `toggle_mode` | get_current_user、require_note_edit_access(False) | 2 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}` | 获取指定附注章节详情 | `routers/disclosure_notes.py:833` `get_note_detail` | get_current_user、require_project_access(readonly) | 14 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/ai-fill` | 单章节 AI 填充 / 参照文档填充（**不落库**，仅返回预览供采纳，Property 11）。 | `routers/disclosure_notes.py:1626` `ai_fill_note_section` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas` | 执行附注表格中的自动运算公式（逐表），回填计算结果。 | `routers/disclosure_notes.py:1400` `apply_formulas` | get_current_user、require_note_edit_access(True) | 3 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}/auto-pull` | 获取附注章节的 cross_ref auto_pull 只读联动值. | `routers/disclosure_notes.py:1343` `get_auto_pull` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}/cell-sources` | 单元格最终来源诊断（只读，spec note-chain-followup-optimizations R2）：最终来源 | `routers/disclosure_notes.py:740` `get_cell_sources` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas` | 一键清除指定附注章节的所有自动公式，切换为手动编辑模式。 | `routers/disclosure_notes.py:1290` `clear_formulas` | get_current_user、require_note_edit_access(True) | 3 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}/formulas` | 列出附注章节的当前公式集（已保存用户编辑集优先，否则 generator 预览）。 | `routers/disclosure_notes.py:1442` `list_note_formulas` | get_current_user、require_project_access(readonly) | 3 |
| PUT | `/api/disclosure-notes/{project_id}/{year}/{note_section}/formulas` | 保存附注章节的公式集（Req 15.2/15.3）。 | `routers/disclosure_notes.py:1481` `upsert_note_formulas` | get_current_user、require_note_edit_access(True) | 3 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}/prior-year` | 获取上年同一附注章节数据，用于前端双列对比。 | `routers/disclosure_notes.py:726` `get_prior_year_note` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/refresh-from-workpaper` | 只重算单个章节的科目数据（当前页面刷新）。 | `routers/note_wp_mapping.py:194` `refresh_section_from_workpaper` | get_current_user、require_note_edit_access(False) | 3 |
| POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto` | 恢复指定附注章节的自动提数模式。 | `routers/disclosure_notes.py:1317` `restore_auto_mode` | get_current_user、require_note_edit_access(True) | 2 |
| GET | `/api/disclosure-notes/{project_id}/{year}/{note_section}/template-structure` | 获取附注章节某张表的原始模板结构（用于"恢复模板结构"操作）。 | `routers/disclosure_notes.py:1264` `get_template_structure` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/financial-reports/{project_id}/{year}/{row_code}/note-references` | 反查所有引用 ``row_code`` 的附注章节（双向溯源跳转）. | `routers/report_note_references.py:183` `get_note_references_for_row` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/group-note-baselines` | List all available group note baselines. | `routers/group_note_baseline.py:61` `list_baselines` | get_current_user | 1 |
| POST | `/api/group-note-baselines` | Save current project notes as a group baseline. | `routers/group_note_baseline.py:71` `save_baseline` | get_current_user | 1 |
| GET | `/api/group-note-baselines/{baseline_id}/preview-diff` | Preview diff between child project notes and baseline. | `routers/group_note_baseline.py:107` `preview_diff` | get_current_user | 1 |
| GET | `/api/group-note-baselines/{baseline_id}/versions` | Get all baseline versions for the parent project of this bas | `routers/group_note_baseline.py:92` `get_baseline_versions` | get_current_user | 0 |
| GET | `/api/note-templates/custom` | 列出自定义模版 | `routers/note_templates.py:95` `list_custom_templates` | get_current_user | 2 |
| POST | `/api/note-templates/custom` | 创建自定义模版 | `routers/note_templates.py:105` `create_custom_template` | get_current_user、require_role | 2 |
| DELETE | `/api/note-templates/custom/{template_id}` | 删除自定义模版 | `routers/note_templates.py:149` `delete_custom_template` | get_current_user、require_role | 1 |
| GET | `/api/note-templates/custom/{template_id}` | 获取自定义模版详情 | `routers/note_templates.py:121` `get_custom_template` | get_current_user | 1 |
| PUT | `/api/note-templates/custom/{template_id}` | 更新自定义模版 | `routers/note_templates.py:134` `update_custom_template` | get_current_user、require_role | 1 |
| POST | `/api/note-templates/custom/{template_id}/rollback` | 回滚模版到指定版本 | `routers/note_templates.py:175` `rollback_template` | get_current_user、require_role | 0 |
| GET | `/api/note-templates/custom/{template_id}/versions` | 获取模版版本历史 | `routers/note_templates.py:162` `get_template_versions` | get_current_user | 0 |
| GET | `/api/note-templates/listed` | 获取上市版附注模版 | `routers/note_templates.py:84` `get_listed_template` | get_current_user | 1 |
| GET | `/api/note-templates/preset-formulas/{template_type}` | 获取附注校验预设公式列表（从 check_presets 生成） | `routers/note_templates.py:191` `get_note_preset_formulas` | get_current_user | 2 |
| GET | `/api/note-templates/soe` | 获取国企版附注模版 | `routers/note_templates.py:75` `get_soe_template` | get_current_user | 1 |
| POST | `/api/note-templates/validate` | 校验附注数据（双层架构：本地规则 + LLM兜底） | `routers/note_templates.py:57` `validate_note_data` | get_current_user | 1 |
| GET | `/api/notes/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers` | 返回附注行关联的底稿列表 | `routers/note_related_workpapers.py:27` `get_note_row_related_workpapers` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/apply-group-baseline` | Apply a group baseline to a child project（以当前用户盖「最近一次编辑」）. | `routers/group_note_baseline.py:120` `apply_group_baseline` | get_current_user、require_note_edit_access(False) | 3 |
| GET | `/api/projects/{project_id}/baseline-sync-status` | Get sync status between child project and baseline. | `routers/group_note_baseline.py:135` `baseline_sync_status` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/data-lock/lock` | 签字后锁定报表和附注数据 | `routers/note_data_lock.py:43` `lock_on_sign_off` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/data-lock/snapshot` | 手动创建数据快照 | `routers/note_data_lock.py:81` `create_snapshot` | get_current_user、require_note_edit_access(False) | 2 |
| GET | `/api/projects/{project_id}/data-lock/snapshots` | 获取版本快照历史链 | `routers/note_data_lock.py:95` `get_snapshot_chain` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/data-lock/status` | 获取锁定状态 | `routers/note_data_lock.py:108` `get_lock_status` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/data-lock/unlock` | 管理员解锁（需填写原因） | `routers/note_data_lock.py:62` `unlock_data` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/disclosure-note-import/parse-knowledge` | 逐篇判权后解析知识库文档（不落库） | `routers/note_text_batch.py:108` `parse_knowledge` | get_current_user、require_note_edit_access(True) | 2 |
| POST | `/api/projects/{project_id}/disclosure-note-import/parse-upload` | 解析上传的 Word / PDF 附注文档（不落库） | `routers/note_text_batch.py:90` `parse_upload` | get_current_user、require_note_edit_access(True) | 2 |
| POST | `/api/projects/{project_id}/disclosure-note-text-batch/apply` | 原子批量写入附注正文（X-Mutation-Id 幂等） | `routers/note_text_batch.py:143` `apply_text_batch` | get_current_user、require_note_edit_access(True) | 2 |
| POST | `/api/projects/{project_id}/disclosure-note-text-batch/preview` | 服务端重算批量写入预览（不落库） | `routers/note_text_batch.py:124` `preview_text_batch` | get_current_user、require_note_edit_access(True) | 2 |
| GET | `/api/projects/{project_id}/disclosure-note-text-batch/sources` | 各章最近一次批量写入的来源（只读，供编辑器来源标记；不进导出正文） | `routers/note_text_batch.py:77` `list_text_sources` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/disclosure-note-text-sections` | 当前项目附注章节列表（scope=narrative\|all，不下发正文） | `routers/note_text_batch.py:62` `list_text_sections` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/disclosure-notes/edit-permission` | 附注编辑权限判定查询：返回当前用户能否编辑该项目附注及原因。 | `routers/note_edit_permission.py:31` `get_note_edit_permission` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/disclosure-notes/sync-batch-from-workpaper` | 多章节一次事务同步（国企 G7 等跨章节编排器用）。 | `routers/wp_disclosure_sync.py:311` `sync_disclosure_batch_from_workpaper` | dedicated_wp_gate、get_current_user、require_project_access(ed | 5 |
| POST | `/api/projects/{project_id}/disclosure-notes/sync-from-workpaper` | C 类附注 sheet 保存触发的单向同步端点。 | `routers/wp_disclosure_sync.py:242` `sync_disclosure_from_workpaper` | dedicated_wp_gate、get_current_user、require_project_access(ed | 140 |
| GET | `/api/projects/{project_id}/disclosure-sync-coverage` | 返回项目级披露同步覆盖率（只读）。 | `routers/disclosure_sync_coverage.py:32` `get_disclosure_sync_coverage` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/note-content-templates` | 列表：当前用户在本项目可见的附注内容模板（分页，只含元数据） | `routers/note_content_templates.py:41` `list_templates_endpoint` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/projects/{project_id}/note-content-templates` | 保存：创建或复用不可变版本 | `routers/note_content_templates.py:66` `save_template_endpoint` | get_current_user、require_note_edit_access(False) | 3 |
| POST | `/api/projects/{project_id}/note-content-templates/snapshot-preview` | 预检：全套快照质量摘要与 digest（不落库） | `routers/note_content_templates.py:53` `snapshot_preview_endpoint` | get_current_user、require_note_edit_access(False) | 2 |
| DELETE | `/api/projects/{project_id}/note-content-templates/{template_id}` | 软删除模板目录（版本与应用记录保留） | `routers/note_content_templates.py:111` `delete_template_endpoint` | get_current_user、require_note_edit_access(False) | 4 |
| GET | `/api/projects/{project_id}/note-content-templates/{template_id}` | 详情：模板与当前版本元数据（不含正文） | `routers/note_content_templates.py:85` `get_template_endpoint` | get_current_user、require_project_access(readonly) | 4 |
| GET | `/api/projects/{project_id}/note-content-templates/{template_id}/versions` | 版本列表：不可变版本元数据 | `routers/note_content_templates.py:98` `list_versions_endpoint` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/note-template` | 读取当前自定义模板主文件；不存在返回 ``{}``. | `routers/note_custom_template.py:70` `load_custom_template` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/note-template/restore` | 回滚到指定历史版本（产生新版本，不覆盖历史快照）. | `routers/note_custom_template.py:82` `restore_custom_template` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/note-template/save` | 保存自定义模板（产生新版本 v{N+1}.json）. | `routers/note_custom_template.py:50` `save_custom_template` | get_current_user、require_note_edit_access(False) | 2 |
| GET | `/api/projects/{project_id}/note-template/versions` | 历史版本清单；主文件不存在 → ``[]``. | `routers/note_custom_template.py:104` `list_custom_template_versions` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/conversion/execute` | 执行国企版↔上市版转换 | `routers/note_conversion.py:181` `execute_conversion` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/conversion/preview` | 预览转换影响（新增/删除/保留数量） | `routers/note_conversion.py:102` `preview_conversion` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/notes/conversion/rollback` | 撤销最近一次转换（从快照恢复） | `routers/note_conversion.py:225` `rollback_conversion` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/notes/conversion/{year}/preview` | 附注**章节映射**预览：将改写 X 个 / 归档 Y 个 / 新建 Z 个 / 保留 N 处人工编辑。 | `routers/note_conversion.py:132` `preview_note_section_conversion` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/notes/cross-references` | Get cross-reference mappings between report rows and note se | `routers/note_advanced.py:101` `get_cross_references` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/notes/cross-references/update` | 章节重排后重算全部交叉引用（系统重算，不盖「最近一次编辑」）。 | `routers/note_advanced.py:115` `update_cross_references` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/custom-sections/apply-template` | 从模板库应用模板到项目 | `routers/note_custom_section.py:98` `apply_template` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/custom-sections/create` | 创建自定义附注章节 | `routers/note_custom_section.py:49` `create_custom_section` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/custom-sections/save-as-template` | 保存章节为模板。门禁之后校验章节属于路径中的项目，不属于返回 404。 | `routers/note_custom_section.py:70` `save_as_template` | get_current_user、require_note_edit_access(False) | 2 |
| GET | `/api/projects/{project_id}/notes/custom-sections/templates` | 列出所有章节模板 | `routers/note_custom_section.py:116` `list_templates` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/export-word` | 导出附注为 Word 文档（致同标准格式） | `routers/note_export.py:44` `export_word` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/generate-variation-analysis` | Generate variation analysis paragraphs for accounts exceedin | `routers/note_advanced.py:136` `generate_variation_analysis` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/notes/group-template/detach` | 脱离集团模板 | `routers/note_group_template.py:84` `detach_from_group_template` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/group-template/distribute` | 下发集团模板到子企业项目 | `routers/note_group_template.py:60` `distribute_template` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/notes/group-template/list` | 列出所有集团模板 | `routers/note_group_template.py:97` `list_templates` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/group-template/save` | 保存当前附注结构为集团模板 | `routers/note_group_template.py:41` `save_as_group_template` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/import-prior-year` | 上传上年附注 .docx，按标题匹配本年章节，填入正文与表格期初列（上年期末 → 本年期初，只填空格）。 | `routers/note_advanced.py:32` `import_prior_year_notes` | get_current_user、require_note_edit_access(True) | 2 |
| POST | `/api/projects/{project_id}/notes/inherit-prior-year` | 连续审计：从本库上一年度附注继承正文（标记待更新）。 | `routers/note_advanced.py:80` `inherit_prior_year_notes` | get_current_user、require_note_edit_access(True) | 2 |
| POST | `/api/projects/{project_id}/notes/locks/acquire` | 获取章节编辑锁 | `routers/note_section_lock.py:45` `acquire_lock` | get_current_user、require_note_edit_access(False) | 2 |
| GET | `/api/projects/{project_id}/notes/locks/active` | 获取项目所有活跃锁 | `routers/note_section_lock.py:131` `get_active_locks` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/locks/force-release` | 项目经理强制解锁 | `routers/note_section_lock.py:88` `force_release_lock` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/notes/locks/heartbeat` | 心跳续期 | `routers/note_section_lock.py:112` `heartbeat` | get_current_user、require_note_edit_access(False) | 2 |
| POST | `/api/projects/{project_id}/notes/locks/release` | 释放章节编辑锁 | `routers/note_section_lock.py:69` `release_lock` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/notes/trace-source` | 追溯附注 cell 的数据来源。 | `routers/note_trace.py:148` `trace_note_source` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/report-config/row-note-mapping` | 报表行次 → 附注编号。 | `routers/report_row_note_mapping.py:27` `get_row_note_mapping` | get_current_user | 2 |
| GET | `/api/report-templates/excel-formulas/{template_type}` | 获取报表Excel模板中的计算公式 | `routers/note_templates.py:219` `get_report_excel_formulas` | get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/disclosure/export-data` | 导出含当前数据的xlsx（基础版：含表头的模板作为基础） | `routers/wp_render_strategies/_d1_disclosure_export.py:612` `export_disclosure_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d1/disclosure/export-template` | 导出空白xlsx模板（含表头+格式，每section一个sheet） | `routers/wp_render_strategies/_d1_disclosure_export.py:591` `export_disclosure_template` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d1/disclosure/import-data` | 解析xlsx回写checklist_responses | `routers/wp_render_strategies/_d1_disclosure_export.py:645` `import_disclosure_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/wp-disclosure-sync/{wp_id}/sync-html` | HTML 渲染器 C 类底稿保存后触发的附注同步端点。 | `routers/wp_disclosure_sync.py:405` `sync_html_to_disclosure` | dedicated_wp_gate、get_current_user | 0 |

## D05 调整分录与错报（112 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/projects/{project_id}/adjustments` | 分录组服务端分页、搜索、筛选和稳定排序。 | `routers/adjustments.py:110` `list_adjustments` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/adjustments` | 创建调整分录（合并锁定期间禁止，需编辑权限） | `routers/adjustments.py:190` `create_adjustment` | check_consol_lock、get_current_user、require_project_permissio | 2 |
| GET | `/api/projects/{project_id}/adjustments/account-dropdown` | 科目下拉选项（全部标准科目，已确认映射的带报表项目） | `routers/adjustments.py:885` `get_account_dropdown` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/batch-commit` | 批量提交：统一触发一次重算事件（配合 batch_mode=true 使用） | `routers/adjustments.py:450` `batch_commit` | get_current_user、require_project_permission(adjustment:submi | 1 |
| POST | `/api/projects/{project_id}/adjustments/batch-delete` | 批量软删除调整分录组（ids 为分录组 id；合并锁定期间禁止，需编辑权限）。 | `routers/adjustments.py:585` `batch_delete_adjustments` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/by-source-ref` | 回流：按 source_ref 返回集中登记复核状态（供底稿侧只读展示）。 | `routers/adjustments.py:437` `get_adjustment_by_source_ref` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/adjustments/client-booking/suggestions` |  | `routers/adjustment_client_booking.py:134` `get_adjustment_client_booking_suggestions` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/adjustments/collaboration/inbox` | 被指派人待办：当前用户在该项目下的活跃协作。 | `routers/adjustments.py:283` `collaboration_inbox` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/collaboration/{collaboration_id}/acknowledge` |  | `routers/adjustments.py:368` `collaboration_acknowledge` | get_current_user、require_project_permission(adjustment:edit) | 1 |
| POST | `/api/projects/{project_id}/adjustments/collaboration/{collaboration_id}/confirm` |  | `routers/adjustments.py:404` `collaboration_confirm` | get_current_user、require_project_permission(adjustment:edit) | 1 |
| POST | `/api/projects/{project_id}/adjustments/collaboration/{collaboration_id}/contribute` |  | `routers/adjustments.py:384` `collaboration_contribute` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/collaboration/{collaboration_id}/reject` |  | `routers/adjustments.py:420` `collaboration_reject` | get_current_user、require_project_permission(adjustment:edit) | 1 |
| GET | `/api/projects/{project_id}/adjustments/export-summary` | 导出审计调整汇总表（AJE + RJE） | `routers/adjustments.py:923` `export_adjustment_summary` | get_current_user、require_project_permission(adjustment:expor | 1 |
| GET | `/api/projects/{project_id}/adjustments/export-template` | 导出调整分录空白模板 Excel (按项目实际数据生成,支持国企/上市两版). | `routers/adjustments.py:970` `export_adjustment_template` | get_current_user、require_project_permission(adjustment:expor | 1 |
| POST | `/api/projects/{project_id}/adjustments/import` | 导入：逐笔保存点，一笔失败不影响其他笔。 | `routers/adjustment_import.py:75` `import_adjustments_file` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/import/preview` | 预检：逐笔解析结果与问题，不写库。 | `routers/adjustment_import.py:53` `preview_adjustment_import` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/preview-impact` | 模拟调整分录影响（**不写 DB**） | `routers/adjustments.py:486` `preview_adjustment_impact` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/reclassification/import` | 导入重分类 Excel，按连续借贷平衡组拆分为多笔独立分录。 | `routers/reclassification.py:192` `import_reclassification` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/adjustments/reclassification/inline-submit` | 多行录入一键提交为一笔重分类调整（RJE 草稿）。 | `routers/reclassification.py:272` `inline_submit_reclassification` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| GET | `/api/projects/{project_id}/adjustments/reclassification/template` | 导出重分类 Excel 模板（预填科目列表）。 | `routers/reclassification.py:112` `export_reclassification_template` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/adjustments/review-batch` | 批量通过 / 驳回（逐笔独立），通知编制人与受影响底稿负责人。 | `routers/adjustment_review.py:172` `review_adjustments_batch` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/review-tasks` | 调整分录复核任务；默认只返回分配给当前用户的待办。 | `routers/adjustment_review.py:82` `list_adjustment_review_tasks` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/adjustments/reviewers` | 本项目可复核调整分录的成员（提交复核时选择通知谁）。 | `routers/adjustment_review.py:123` `list_adjustment_reviewers` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/submit-review` | 草稿 / 已驳回分录提交复核（批量逐笔），并创建持久化任务。 | `routers/adjustment_review.py:133` `submit_adjustments_for_review` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/summary` | 汇总统计（按用户循环范围过滤，与列表端点同口径） | `routers/adjustments.py:864` `get_summary` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/sync-from-workpaper` | 底稿调整分录组 → 集中式登记（幂等 by source_ref，origin='workpaper'）。 | `routers/adjustments.py:209` `sync_from_workpaper` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/wp-summary/{wp_code}` | 旧底稿调整汇总已退役；保留鉴权后的 410 兼容壳。 | `routers/adjustments.py:899` `get_wp_summary` | get_current_user、require_project_access(readonly) | 2 |
| DELETE | `/api/projects/{project_id}/adjustments/{entry_group_id}` | 软删除调整分录（合并锁定期间禁止，需编辑权限） | `routers/adjustments.py:561` `delete_adjustment` | check_consol_lock、get_current_user、require_project_permissio | 4 |
| PUT | `/api/projects/{project_id}/adjustments/{entry_group_id}` | 修改调整分录（合并锁定期间禁止，需编辑权限） | `routers/adjustments.py:542` `update_adjustment` | check_consol_lock、get_current_user、require_project_permissio | 4 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/client-booking` |  | `routers/adjustment_client_booking.py:49` `mark_adjustment_client_booked` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/{entry_group_id}/client-booking/history` |  | `routers/adjustment_client_booking.py:121` `get_adjustment_client_booking_history` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/client-booking/revoke` |  | `routers/adjustment_client_booking.py:87` `revoke_adjustment_client_booking` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/{entry_group_id}/collaboration` | 分录组当前协作 + 事件时间线。 | `routers/adjustments.py:331` `get_group_collaboration` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/collaboration/assign` | 转派/重派分录组给项目成员补充+确认。 | `routers/adjustments.py:306` `collaboration_assign` | get_current_user、require_project_permission(adjustment:edit) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/convert-to-misstatement` | 将被驳回的 AJE 组一键转为《未更正错报汇总表》的一条记录。 | `routers/adjustments.py:734` `convert_adjustment_to_misstatement` | get_current_user、require_project_permission(adjustment:conve | 1 |
| DELETE | `/api/projects/{project_id}/adjustments/{entry_group_id}/lock` | 释放编辑锁。 | `routers/conflict_guard.py:76` `release_lock` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/lock` | 获取调整分录编辑锁。 | `routers/conflict_guard.py:34` `acquire_lock` | get_current_user、require_project_access(edit) | 1 |
| PATCH | `/api/projects/{project_id}/adjustments/{entry_group_id}/lock/heartbeat` | 续期编辑锁心跳。 | `routers/conflict_guard.py:56` `heartbeat_lock` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/adjustments/{entry_group_id}/related-workpapers` | R10 Spec B / F8：根据调整分录组中所有 line_items 的科目反查关联底稿（项目成员只读权限）。 | `routers/adjustments.py:1636` `get_adjustment_related_workpapers` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/review` | 批准/驳回一笔已提交的复核任务；无任务或草稿直批均拒绝。 | `routers/adjustments.py:613` `review_adjustment` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/revoke-review` | 撤回复核并在同一事务回退手工调整列；底稿来源只回退复核状态。 | `routers/adjustments.py:678` `revoke_adjustment_review` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/adjustments/{entry_group_id}/treatment` |  | `routers/adjustment_treatment.py:51` `get_adjustment_treatment` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/adjustments/{entry_group_id}/treatment/history` |  | `routers/adjustment_treatment.py:67` `get_adjustment_treatment_history` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/treatment/include` |  | `routers/adjustment_treatment.py:113` `include_adjustment_in_working_tb` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/treatment/unadjusted` |  | `routers/adjustment_treatment.py:80` `mark_adjustment_unadjusted` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/treatment/withdraw` |  | `routers/adjustment_treatment.py:135` `withdraw_adjustment_treatment` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/withdraw-submission` | 撤回提交：待复核 → 草稿，同时关闭持久化复核任务。 | `routers/adjustment_review.py:154` `withdraw_adjustment_submission` | check_consol_lock、get_current_user、require_project_permissio | 1 |
| GET | `/api/projects/{project_id}/linkage/tb-row/{row_code}/adjustments` | 获取试算平衡表某行关联的调整分录列表。 | `routers/linkage.py:32` `get_tb_row_adjustments` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/misstatements` | 未更正错报列表 | `routers/misstatements.py:37` `list_misstatements` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/misstatements` | 创建未更正错报 | `routers/misstatements.py:50` `create_misstatement` | get_current_user、require_project_permission(adjustment:conve | 2 |
| POST | `/api/projects/{project_id}/misstatements/communication-draft` | A13 Req 5.1-5.7: 生成管理层沟通函草稿。 | `routers/misstatements.py:212` `generate_communication_draft_endpoint` | get_current_user、require_project_permission(adjustment:conve | 1 |
| GET | `/api/projects/{project_id}/misstatements/for-letter` | 返回 A16 管理层声明书用的未更正错报摘要文本 | `routers/misstatements.py:133` `get_for_representation_letter` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/misstatements/from-aje/{group_id}` | 从被拒绝AJE创建未更正错报 | `routers/misstatements.py:64` `create_from_aje` | get_current_user、require_project_permission(adjustment:conve | 2 |
| POST | `/api/projects/{project_id}/misstatements/recheck-threshold` | R8-S2-13：重新评估所有错报 vs 当前重要性阈值 | `routers/misstatements.py:161` `recheck_threshold` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/misstatements/summary` | 汇总视图：按类型分组 + 与重要性水平对比 | `routers/misstatements.py:148` `get_summary` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/projects/{project_id}/misstatements/{misstatement_id}` | 软删除未更正错报 | `routers/misstatements.py:116` `delete_misstatement` | get_current_user、require_project_permission(adjustment:conve | 4 |
| PUT | `/api/projects/{project_id}/misstatements/{misstatement_id}` | 更新未更正错报 | `routers/misstatements.py:98` `update_misstatement` | get_current_user、require_project_permission(adjustment:conve | 4 |
| POST | `/api/projects/{project_id}/misstatements/{misstatement_id}/mark-reversed` | A13 Req 4.3: 将结转错报标记为已转回，从累计中排除。 | `routers/misstatements.py:195` `mark_as_reversed` | get_current_user、require_project_permission(adjustment:conve | 1 |
| GET | `/api/projects/{project_id}/misstatements/{misstatement_id}/related-workpapers` | R10 Spec B / F7：根据错报关联的科目编码反查底稿。 | `routers/misstatements.py:232` `get_misstatement_related_workpapers` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/workpapers/{project_id}/{year}/misstatement-communication` | A13 沟通记录；兼容旧 adjustment_id，但只更新正式错报表。 | `routers/wp_misstatement.py:65` `post_misstatement_communication` | get_current_user、require_project_permission(adjustment:conve | 7 |
| GET | `/api/workpapers/{project_id}/{year}/misstatement-evaluation` | A13-3 评价错报（汇总 vs 重要性） | `routers/wp_misstatement.py:40` `get_misstatement_evaluation` | get_current_user、require_project_access(readonly) | 8 |
| GET | `/api/workpapers/{project_id}/{year}/misstatement-for-letter` | A16 声明书用错报摘要文本 | `routers/wp_misstatement.py:52` `get_misstatement_for_letter` | get_current_user、require_project_access(readonly) | 6 |
| GET | `/api/workpapers/{project_id}/{year}/misstatement-summary` | A13-1 未更正错报汇总 | `routers/wp_misstatement.py:28` `get_misstatement_summary` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/workpapers/{wp_id}/client-booked-adjustments` |  | `routers/wp_client_booked_adjustments.py:21` `get_workpaper_client_booked_adjustments` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/l2/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l2/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l2/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l6/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l6/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l6/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m1/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m1/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m1/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m10/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m10/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m10/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m2/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m2/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m2/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m3/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/m3/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/m3/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/m4/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m4/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m4/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m5/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m5/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m5/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m6/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m6/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m6/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m7/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m7/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m7/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m8/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m8/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m8/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m9/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m9/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/m9/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n1/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n1/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n1/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n2/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n2/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n2/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n3/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n3/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n3/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n5/export-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1665` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n5/export-template` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1656` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/n5/import-data` |  | `routers/wp_render_strategies/_x3_adjustment_import_export.py:1677` `import_data` | dedicated_wp_gate、get_current_user | 0 |

## D03 账表导入与数据集（96 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| POST | `/api/datasets/{dataset_id}/force-unbind` | F50 合规例外 — 强制解除下游对象的 dataset 绑定。 | `routers/dataset_force_unbind.py:78` `force_unbind_dataset` | get_current_user | 0 |
| GET | `/api/import-templates/types` | 获取所有支持的导入类型及其列定义 | `routers/import_templates.py:38` `list_import_types` | get_current_user | 0 |
| GET | `/api/import-templates/{import_type}/download` | 下载标准导入模板 Excel 文件 | `routers/import_templates.py:57` `download_template` | get_current_user | 1 |
| POST | `/api/import-templates/{import_type}/import` | 校验 + 导入数据到系统（调整分录逐笔保存点：一笔失败不影响其他笔） | `routers/import_templates.py:106` `import_data` | get_current_user | 0 |
| POST | `/api/import-templates/{import_type}/validate` | 上传 Excel 文件并校验格式（不入库） | `routers/import_templates.py:93` `validate_file` | get_current_user | 1 |
| GET | `/api/ledger-import/validation-rules` | 返回全量校验规则目录（F48）。 | `routers/validation_rules.py:31` `list_validation_rules` | get_current_user | 1 |
| GET | `/api/ledger-import/validation-rules/{code}` | 按 ``code`` 查询单条规则（F48）。 | `routers/validation_rules.py:44` `get_validation_rule` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/data-quality/check` | 执行数据质量检查套件 | `routers/data_quality.py:24` `run_data_quality_check` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/datasets/{dataset_id}/sign-convention/anomalies` | 获取方向异常列表。 | `routers/sign_convention.py:96` `list_sign_anomalies` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/datasets/{dataset_id}/sign-convention/anomalies/batch-confirm` | 批量确认异常为正确（真实业务余额）。 | `routers/sign_convention.py:152` `batch_confirm_anomalies` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/datasets/{dataset_id}/sign-convention/direction-override` | 用户覆盖方向，记录原因和留痕。 | `routers/sign_convention.py:122` `create_direction_override` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/drilldown/aux-balance/{account_code}` | 穿透到辅助余额表 | `routers/drilldown.py:80` `drill_to_aux_balance` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/drilldown/aux-ledger/{account_code}` | 穿透到辅助明细账 | `routers/drilldown.py:93` `drill_to_aux_ledger` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/drilldown/balance` | 科目余额表（分页+筛选） | `routers/drilldown.py:30` `get_balance_list` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/drilldown/ledger/{account_code}` | 穿透到序时账 | `routers/drilldown.py:51` `drill_to_ledger` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/drilldown/verify-consistency` | 校验余额表与序时账的一致性（发生额核对+期末公式校验） | `routers/drilldown.py:169` `verify_balance_ledger_consistency` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/drilldown/voucher/{voucher_no}` | 一张凭证的完整分录（借贷明细 + 合计 + 平衡状态），凭证键 = 主体 + 日期 + 凭证字 + 号。 | `routers/drilldown.py:119` `get_voucher_detail` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/drilldown/vouchers` | 凭证列表（按凭证号分组聚合，支持大数据量分页） | `routers/drilldown.py:142` `list_vouchers` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/import` | Upload file and start import (multipart form). | `routers/data_import.py:42` `upload_and_import` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/import-intelligence/enhance-mapping` | 增强列映射：对未匹配的列尝试模糊匹配 | `routers/import_intelligence.py:40` `enhance_mapping` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/import-intelligence/overview` | 导入结果概览（供前端可视化） | `routers/import_intelligence.py:88` `import_overview` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/import-intelligence/prepare-incremental` | 准备增量导入：分析现有数据，返回追加策略 | `routers/import_intelligence.py:69` `prepare_incremental` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/import-intelligence/quality-check` | 深度数据质量校验（导入后执行） | `routers/import_intelligence.py:54` `quality_check` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/import/batches` | List all import batches for a project. | `routers/data_import.py:106` `list_import_batches` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/import/check-duplicates` | 导入前检查是否存在重复数据。 | `routers/data_import.py:116` `check_duplicates` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/import/preview` | 预览上传文件：返回 sheet 列表、每个 sheet 的表头和前 20 行数据。 | `routers/data_import.py:146` `preview_file` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/import/{batch_id}/progress` | Get import progress for a batch. | `routers/data_import.py:92` `get_import_progress` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/import/{batch_id}/rollback` | Rollback an import batch. | `routers/data_import.py:131` `rollback_import` | get_current_user | 0 |
| DELETE | `/api/projects/{project_id}/ledger-data` | 按维度删除账表数据。 | `routers/ledger_data.py:107` `delete_ledger` | check_consol_lock、get_current_user | 2 |
| POST | `/api/projects/{project_id}/ledger-data/dedup` | 对 active 数据集做整行去重（保留每组最小 id，软删字节级完全相同的重复行）。 | `routers/ledger_data.py:160` `dedup_ledger` | check_consol_lock、get_current_user | 1 |
| POST | `/api/projects/{project_id}/ledger-data/incremental/apply` | 旧的 active 数据预删入口永久退役；追加只允许在 staged 内合并。 | `routers/ledger_data.py:307` `apply_incremental_endpoint` | check_consol_lock、get_current_user、require_project_access(ed | 0 |
| POST | `/api/projects/{project_id}/ledger-data/incremental/detect` | 增量追加预检：返回期间差异。 | `routers/ledger_data.py:256` `detect_incremental` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ledger-data/restore` | S7-10: 从回收站恢复数据（is_deleted=true → false）。 | `routers/ledger_data.py:217` `restore_ledger` | check_consol_lock、get_current_user | 1 |
| GET | `/api/projects/{project_id}/ledger-data/summary` | 查询项目已导入账表数据概览。 | `routers/ledger_data.py:92` `get_ledger_summary` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-data/trash` | S7-10: 列出回收站中已软删除的数据。 | `routers/ledger_data.py:202` `get_trash` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/ledger-import/activation-records` | 查询激活/回滚操作历史 | `routers/ledger_datasets.py:206` `list_activation_records` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/active-job` | S7: 获取项目最新的导入作业状态（替代 ImportQueueService 内存态轮询）。 | `routers/ledger_import_v2.py:694` `get_latest_job` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/projects/{project_id}/ledger-import/artifacts` | 查询上传产物历史 | `routers/ledger_datasets.py:268` `list_import_artifacts` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/datasets` | 查询数据集版本历史 | `routers/ledger_datasets.py:29` `list_datasets` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/datasets/active` | 查询当前 active 数据集 | `routers/ledger_datasets.py:55` `get_active_dataset` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/datasets/history` | F25 / Sprint 5.19: 账套导入历史时间轴。 | `routers/ledger_datasets.py:84` `get_datasets_history` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ledger-import/datasets/{dataset_id}/rollback` | 回滚到上一版本数据集。 | `routers/ledger_datasets.py:162` `rollback_dataset` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger-import/detect` | Multipart file upload → 持久化到 bundle → 识别 → 返回 LedgerDetectio | `routers/ledger_import_v2.py:104` `detect_files` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/ledger-import/jobs` | 查询导入作业历史 | `routers/ledger_datasets.py:229` `list_import_jobs` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/jobs/{job_id}` | 查询单个导入作业状态 | `routers/ledger_datasets.py:293` `get_import_job` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/cancel` | 取消导入作业。 | `routers/ledger_datasets.py:347` `cancel_import_job` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/diagnostics` | Return diagnostic details for a job (admin/support use). | `routers/ledger_import_v2.py:433` `get_job_diagnostics` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/resume` | 从最后一个 checkpoint 恢复失败/超时的导入作业（F14）。 | `routers/ledger_import_v2.py:661` `resume_from_checkpoint` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry` | 重试失败的导入作业 | `routers/ledger_datasets.py:324` `retry_import_job` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry` | Retry a failed job using ImportOrchestrator.resume(). | `routers/ledger_import_v2.py:507` `retry_job` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/stream` | SSE endpoint for real-time job progress updates. | `routers/ledger_import_v2.py:405` `stream_job_progress` | get_current_user_stream、require_project_access_stream(readon | 2 |
| POST | `/api/projects/{project_id}/ledger-import/jobs/{job_id}/takeover` | F22 / Sprint 5.10-5.11: 接管导入作业。 | `routers/ledger_import_v2.py:570` `takeover_job` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger-import/submit` | Accept confirmed mappings, create ImportJob, return job info | `routers/ledger_import_v2.py:228` `submit_import` | get_current_user、require_project_access(edit) | 3 |
| GET | `/api/projects/{project_id}/ledger/account-workpapers` | 科目 → 对应底稿清单（审定表优先），供查账页右键「跳转到底稿」；``wp_id`` 为空 = 本项目尚未生成。 | `routers/ledger_penetration.py:675` `get_account_workpapers` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux-balance-all` | 全量辅助余额（所有科目的辅助核算维度） | `routers/ledger_penetration.py:468` `get_all_aux_balance` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/ledger/aux-balance-detail` | 辅助余额明细查询（树形展开时按需加载） | `routers/ledger_penetration.py:434` `get_aux_balance_detail` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/ledger/aux-balance-paged` | 辅助余额表分页查询（后端筛选+分页，前端不加载全量数据） | `routers/ledger_penetration.py:377` `get_aux_balance_paged` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux-balance-summary` | 辅助余额汇总（预计算，按维度+科目+辅助编码分组，Redis 缓存 5 分钟）。 | `routers/ledger_penetration.py:301` `get_aux_balance_summary` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux-balance/{account_code}` | 辅助余额（按科目穿透到辅助维度） | `routers/ledger_penetration.py:480` `get_aux_balance` | get_current_user、require_project_access(readonly) | 5 |
| GET | `/api/projects/{project_id}/ledger/aux-entries/{account_code}` | 辅助明细账（按辅助维度穿透）— 支持游标分页和传统分页 | `routers/ledger_penetration.py:494` `get_aux_ledger_entries` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux-window-export/{account_code}` | 流式读取完整辅助明细并生成 write-only XLSX。 | `routers/ledger_penetration.py:191` `export_aux_ledger_window` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux-window/{account_code}` | 辅助明细窗口；不选 aux_type 为浏览模式（不累计期初）；整页响应读 Redis 缓存。 | `routers/ledger_penetration.py:136` `get_aux_ledger_window` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/aux/by-triplet` | S6-8 三元组精确穿透（account_code + aux_type + aux_code）。 | `routers/ledger_penetration.py:521` `get_aux_by_triplet` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/balance` | 科目余额汇总（Redis 缓存 5 分钟） | `routers/ledger_penetration.py:68` `get_balance` | get_current_user、require_project_access(readonly) | 4 |
| GET | `/api/projects/{project_id}/ledger/balance-tree` | 科目余额树形视图（Layer 2 v2 / Sprint 8 P3 分页）。 | `routers/ledger_penetration.py:1354` `get_balance_tree` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/projects/{project_id}/ledger/cache` | 清除穿透查询缓存 | `routers/ledger_penetration.py:545` `clear_cache` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/ledger/entries-all` | 全量序时账分录（不限科目）— 供 C24 会计分录细节测试四表联动 | `routers/ledger_penetration.py:220` `get_all_ledger_entries` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/entries/{account_code}` | 序时账明细（按科目穿透）— 支持游标分页和传统分页 | `routers/ledger_penetration.py:244` `get_ledger_entries` | get_current_user、require_project_access(readonly) | 15 |
| GET | `/api/projects/{project_id}/ledger/export-aux-balance` | 导出辅助余额表为 Excel（支持当前视图条件） | `routers/ledger_penetration.py:1048` `export_aux_balance_excel` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/export-balance` | 导出科目余额表为 Excel | `routers/ledger_penetration.py:970` `export_balance_excel` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/export-ledger/{account_code}` | 导出序时账为 Excel（含期初余额行+月小计+累计余额） | `routers/ledger_penetration.py:803` `export_ledger_excel` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/opening-balance/{account_code}` | 获取科目期初余额（用于序时账 running_balance 计算） | `routers/ledger_penetration.py:97` `get_opening_balance` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/penetrate` | 统一穿透查询（带缓存） | `routers/ledger_penetration.py:46` `penetrate` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/ledger/penetrate-by-amount` | 按金额穿透序时账 | `routers/penetrate_by_amount.py:36` `penetrate_by_amount` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/ledger/raw-extra-fields` | Aggregate raw_extra field distribution across ledger tables. | `routers/ledger_raw_extra.py:33` `get_raw_extra_fields` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/ledger/sample-voucher` | 挂凭到底稿（单张）：记录到抽样凭证清单（手工侧，batch_id 为空）。必须指定底稿，且要能编辑该底稿。 | `routers/voucher_links.py:226` `sample_voucher` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger/sample-vouchers/batch` | 多张凭证 × 多张底稿一次挂（需求 5.1）：逐个「凭证 × 底稿」一个保存点，单条失败不影响其余。 | `routers/voucher_links.py:442` `attach_vouchers_batch` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/ledger/sampled-vouchers` | 抽样凭证清单。每行带凭证键各列（日期 / 凭证字 / 主体）与阶段，回拉分录按凭证键定位单张凭证。 | `routers/voucher_links.py:309` `list_sampled_vouchers` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/projects/{project_id}/ledger/sampled-vouchers/{sampled_id}` | 取消挂凭（软删）。只删手工挂凭；年审阶段不删预审挂凭（任务 15）。 | `routers/voucher_links.py:351` `delete_sampled_voucher` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger/smart-import` | 智能导入（异步后台）：解析多个文件并写入数据库。 | `routers/ledger_penetration.py:627` `smart_import` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/ledger/smart-preview` | 智能预览：轻量解析前 N 行，返回识别结果 + 列映射 + 总行估算。 | `routers/ledger_penetration.py:594` `smart_preview` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/stats` | 获取四表数据统计（行数、最后导入时间） | `routers/ledger_penetration.py:765` `get_data_stats` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/ledger/upload` | 上传四表数据文件（支持历史年度）. | `routers/ledger_penetration.py:559` `upload_data` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/ledger/upload-multi` | 上传多个四表数据文件（支持多个序时账文件合并导入）. | `routers/ledger_penetration.py:574` `upload_multi_files` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/ledger/validate` | 四表数据一致性校验（入库后按需触发）。 | `routers/ledger_penetration.py:1192` `validate_data` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ledger/voucher-conclusions/query` | 凭证键 → 本项目各可见底稿检查表里这张凭证的结论（spec voucher-workflow-linkage-line | `routers/voucher_links.py:696` `query_voucher_conclusions` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ledger/voucher-evidence/query` | 凭证键 → 本项目各底稿已取得的这张凭证的证据（附件），只列当前用户可见的底稿；单次最多 500 个键。 | `routers/voucher_links.py:755` `query_voucher_evidence` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ledger/voucher-links/query` | 凭证键 → 该凭证已挂 / 已抽于哪些底稿（手工挂凭与抽凭引擎登记合并），单次最多 500 个键。 | `routers/voucher_links.py:510` `query_voucher_links` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/voucher/{voucher_no}` | 一张凭证的分录（凭证键 = 主体 + 日期 + 凭证字 + 号）；命中多张凭证时 409 VOUCHER_KEY_AMB | `routers/ledger_penetration.py:278` `get_voucher_entries` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/window-export/{account_code}` | 流式读取完整普通序时账并生成 write-only XLSX；不依赖浏览器当前窗口。 | `routers/ledger_penetration.py:164` `export_ledger_window` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/window/{account_code}` | 普通序时账窗口：签名 keyset 游标，首窗精确摘要，后窗不重复 COUNT；整页响应读 Redis 缓存。 | `routers/ledger_penetration.py:111` `get_ledger_window` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/workpapers/{wp_id}/attached-voucher-status` | 本底稿手工挂凭里还没导入凭证检查表的凭证（spec voucher-workflow-linkage-lineage-c | `routers/voucher_links.py:636` `attached_voucher_status` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/ledger/years` | 获取该项目有数据的年度列表 + 同客户其他项目有数据的年份（供年度切换参考） | `routers/ledger_penetration.py:697` `get_available_years` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/workpapers/{wp_id}/d1-ecl/import-data` | D1-ECL导入xlsx数据（D1-15 hardcoded） | `routers/wp_render_strategies/_d1_import_export/_impl.py:3129` `d1_ecl_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/import-aux-balance` | 从 tb_aux_balance（应收票据原值科目，客户维度）归集导入 D1-3 明细表。 | `routers/wp_render_strategies/_d1_import_export/_impl.py:3559` `d1_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d1_import_export/_impl.py:2674` `d1_import_data` | dedicated_wp_gate、get_current_user | 5 |

## D04 科目映射与试算表（109 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/aging/inventory-presets` | 获取存货库龄预设方案 | `routers/aging_analysis.py:120` `list_inventory_presets` | get_current_user | 0 |
| GET | `/api/aging/presets` | 获取预定义账龄段列表。 | `routers/aging_config.py:100` `get_aging_presets` | get_current_user | 1 |
| GET | `/api/aging/presets` | 获取账龄预设方案 | `routers/aging_analysis.py:25` `list_presets` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/account-chart/batch-update` | 批量更新客户科目（名称、借贷方向） | `routers/account_chart.py:466` `batch_update_accounts` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/account-chart/client` | 获取客户科目表（树形结构按类别分组）。 | `routers/account_chart.py:265` `get_client_chart` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/account-chart/import` | 旧同步科目表导入入口**永久退役**，固定返回 410。 | `routers/account_chart.py:111` `import_client_chart` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/account-chart/import-async` | 异步导入（多文件支持）：立即返回，后台处理，前端轮询进度。 | `routers/account_chart.py:219` `import_async` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/account-chart/import-reset` | 强制释放导入锁 + 清理卡住的任务。 | `routers/account_chart.py:152` `reset_import` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/account-chart/preview` | Preview uploaded file: return first 20 rows per sheet + auto | `routers/account_chart.py:85` `preview_file` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/account-chart/standard` | 获取项目的标准科目表。 | `routers/account_chart.py:57` `get_standard_chart` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/aging/calculate` | 计算账龄坏账计提 | `routers/aging_analysis.py:86` `calculate` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/aging/config` | 获取项目级账龄配置。 | `routers/aging_config.py:33` `get_aging_config` | get_current_user | 4 |
| GET | `/api/projects/{project_id}/aging/config` | 获取项目账龄配置 | `routers/aging_analysis.py:38` `get_config` | get_current_user、require_project_access(readonly) | 4 |
| PUT | `/api/projects/{project_id}/aging/config` | 保存项目级账龄配置。 | `routers/aging_config.py:48` `put_aging_config` | get_current_user | 4 |
| PUT | `/api/projects/{project_id}/aging/config` | 保存项目账龄配置 | `routers/aging_analysis.py:58` `save_config` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/projects/{project_id}/column-mappings` | 获取已保存的列映射 | `routers/account_chart.py:333` `get_column_mappings` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/projects/{project_id}/column-mappings` | 保存用户确认的列映射（持久化到项目 wizard_state） | `routers/account_chart.py:300` `save_column_mapping` | get_current_user、require_project_access(edit) | 3 |
| POST | `/api/projects/{project_id}/column-mappings/reference-copy` | 从其他项目参照复制列映射；来源只能是当前用户能读的项目（spec consol-autotree-residual-cl | `routers/account_chart.py:400` `reference_copy_mappings` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/column-mappings/reference-projects` | 获取可参照的项目列表（有已保存列映射、当前用户能读的其他项目）。 | `routers/account_chart.py:362` `get_reference_projects` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/linkage/tb-row/{row_code}/workpapers` | 获取试算平衡表某行关联的底稿列表。 | `routers/linkage.py:46` `get_tb_row_workpapers` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/mapping` | 获取映射列表。 | `routers/mapping.py:77` `get_mappings` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/mapping` | 保存单条映射。 | `routers/mapping.py:93` `save_mapping` | get_current_user、require_project_access(edit) | 2 |
| POST | `/api/projects/{project_id}/mapping/auto-match` | 自动匹配并直接保存映射结果。 | `routers/mapping.py:46` `auto_match` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/mapping/auto-suggest` | 自动匹配建议：编码前缀→名称精确→名称模糊。 | `routers/mapping.py:29` `auto_suggest` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/mapping/batch-confirm` | 批量确认映射。 | `routers/mapping.py:132` `batch_confirm` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/mapping/completion-rate` | 获取映射完成率。 | `routers/mapping.py:149` `get_completion_rate` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/projects/{project_id}/mapping/{mapping_id}` | 修改映射。 | `routers/mapping.py:111` `update_mapping` | get_current_user、require_project_access(edit) | 3 |
| GET | `/api/projects/{project_id}/materiality` | 获取当前重要性水平 | `routers/materiality.py:34` `get_materiality` | get_current_user | 5 |
| GET | `/api/projects/{project_id}/materiality/benchmark` | 从试算表自动取基准金额 | `routers/materiality.py:109` `get_benchmark` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/materiality/calculate` | 计算重要性水平 | `routers/materiality.py:49` `calculate_materiality` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/materiality/history` | 变更历史 | `routers/materiality.py:96` `get_history` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/materiality/override` | 手动覆盖重要性水平 | `routers/materiality.py:71` `override_materiality` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/report-line-mapping` | 获取报表行次映射列表。 | `routers/report_line_mapping.py:175` `get_mappings` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/report-line-mapping/ai-suggest` | AI建议报表行次映射(数据驱动 + 项目维度感知). | `routers/report_line_mapping.py:28` `ai_suggest` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/report-line-mapping/batch-confirm` | 批量确认报表行次映射。 | `routers/report_line_mapping.py:224` `batch_confirm` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/report-line-mapping/fix-bad-debt` | 修复 account_mapping 中 1231 坏账准备总分类→二级分项错配. | `routers/report_line_mapping.py:49` `fix_bad_debt` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/report-line-mapping/manual` | 手动创建单条报表行次映射（用户从下拉选择报表项目）。 | `routers/report_line_mapping.py:257` `create_manual_mapping` | get_current_user、require_project_access(edit) | 2 |
| POST | `/api/projects/{project_id}/report-line-mapping/reference-copy` | 集团内企业一键参照复制；来源只能是当前用户能读的项目（spec consol-autotree-residual-clo | `routers/report_line_mapping.py:319` `reference_copy` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/report-line-mapping/report-lines` | 获取已确认的报表行次列表（供调整分录下拉）。 | `routers/report_line_mapping.py:346` `get_report_lines` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/projects/{project_id}/report-line-mapping/{mapping_id}` |  | `routers/report_line_mapping.py:242` `delete_mapping` | check_consol_lock、get_current_user、require_project_access(ed | 4 |
| PUT | `/api/projects/{project_id}/report-line-mapping/{mapping_id}` |  | `routers/report_line_mapping.py:192` `update_mapping` | check_consol_lock、get_current_user、require_project_access(ed | 4 |
| PUT | `/api/projects/{project_id}/report-line-mapping/{mapping_id}/confirm` | 确认单条报表行次映射。 | `routers/report_line_mapping.py:207` `confirm_mapping` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/report-mapping` | 获取已保存的映射规则 | `routers/report_mapping.py:39` `get_saved_mapping` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/report-mapping` | 保存映射规则 | `routers/report_mapping.py:53` `save_mapping` | check_consol_lock、get_current_user、require_project_access(ed | 2 |
| GET | `/api/projects/{project_id}/report-mapping/preset` | 获取预设映射规则（按行名自动匹配） | `routers/report_mapping.py:26` `get_preset_mapping` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/t-accounts` |  | `routers/t_accounts.py:92` `list_t_accounts` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/t-accounts` |  | `routers/t_accounts.py:79` `create_t_account` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/t-accounts/{t_account_id}` |  | `routers/t_accounts.py:101` `get_t_account` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/projects/{project_id}/t-accounts/{t_account_id}/calculate` |  | `routers/t_accounts.py:134` `calculate_net_change` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/t-accounts/{t_account_id}/entries` |  | `routers/t_accounts.py:114` `add_entry` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/t-accounts/{t_account_id}/integrate` |  | `routers/t_accounts.py:163` `integrate_to_cfs` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/t-accounts/{t_account_id}/reconcile` |  | `routers/t_accounts.py:146` `reconcile` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/trial-balance` | 获取试算表（四列结构），含重要性水平高亮标记。 | `routers/trial_balance.py:34` `get_trial_balance` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/projects/{project_id}/trial-balance/balance-check` | 试算平衡校验：直接从 tb_balance 原始数据验证(保持与入库数据同源)。 | `routers/trial_balance.py:264` `check_trial_balance` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/trial-balance/consistency-check` | 数据一致性校验 | `routers/trial_balance.py:414` `consistency_check` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/trial-balance/export` | 导出试算表 xlsx（正式件，按项目 `amount_unit` 折算 + 标注单位）。 | `routers/trial_balance.py:538` `export_trial_balance` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/projects/{project_id}/trial-balance/freeze` | 锁定/解锁试算表（需编辑权限：现场经理及以上角色）。 | `routers/trial_balance.py:478` `set_freeze_status` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/trial-balance/freeze-status` | 获取试算表锁定状态（任何已认证用户可查看）。 | `routers/trial_balance.py:451` `get_freeze_status` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/trial-balance/recalc` | 手动触发全量重算（合并锁定期间禁止，需编辑权限） | `routers/trial_balance.py:181` `recalc_trial_balance` | check_consol_lock、get_current_user、require_project_access(ed | 3 |
| GET | `/api/projects/{project_id}/trial-balance/snapshots` | List snapshots for project+year. | `routers/tb_snapshot.py:47` `list_snapshots` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/trial-balance/snapshots` | Create a trial balance snapshot (dedup by content hash). | `routers/tb_snapshot.py:25` `create_snapshot` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/trial-balance/snapshots/diff` | Compare two snapshot versions. | `routers/tb_snapshot.py:61` `diff_snapshots` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/trial-balance/snapshots/{version_no}` | Get full snapshot detail. | `routers/tb_snapshot.py:77` `get_snapshot` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/trial-balance/snapshots/{version_no}/restore` | Restore trial balance to a historical snapshot. Requires man | `routers/tb_snapshot.py:92` `restore_snapshot` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/trial-balance/summary-with-adjustments` | 试算平衡表汇总（按报表行次），AJE/RJE 从 adjustments 表自动汇总。 | `routers/trial_balance.py:396` `get_summary_with_adjustments` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/trial-balance/trace` | 数据溯源：查询标准科目对应的所有客户科目及其余额表原始数据。 | `routers/trial_balance.py:334` `trace_to_balance` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/all` | 获取全部底稿-科目映射 | `routers/wp_mapping.py:24` `get_all_mappings` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/wp-mapping/assign/{wp_code}` | 已下线（410）：按姓名写 ``working_paper.assigned_to``（用户 id 外键列写进姓名字符串 | `routers/wp_mapping.py:219` `assign_workpaper_gone` | — | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/by-account/{account_code}` | 根据科目编码查找关联底稿 | `routers/wp_mapping.py:34` `find_by_account` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/wp-mapping/by-note/{note_section:path}` | 根据附注章节查找关联底稿 | `routers/wp_mapping.py:56` `find_by_note` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/by-wp/{wp_code}` | 根据底稿编码查找映射 | `routers/wp_mapping.py:45` `find_by_wp` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/prefill/{wp_code}` | 获取底稿预填充数据（从试算表取数） | `routers/wp_mapping.py:67` `get_prefill_data` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/wp-mapping/progress-overview` | 获取项目底稿进度总览（按循环分组统计） | `routers/wp_mapping.py:169` `get_progress_overview` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/progress-report` | AI 生成项目进度简报 | `routers/wp_mapping.py:240` `generate_progress_report` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/recommend` | 根据试算表有余额的科目，智能推荐需要编制的底稿清单 | `routers/wp_mapping.py:83` `recommend_workpapers` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/wp-mapping/review-inbox` | 获取当前用户待复核的底稿列表 | `routers/wp_mapping.py:122` `get_review_inbox` | get_current_user、require_project_access(review) | 0 |
| GET | `/api/projects/{project_id}/wp-mapping/tsj/{account_name}` | 获取科目对应的 TSJ 审计复核提示词 | `routers/wp_mapping.py:98` `get_tsj_prompts` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/report-config/tb-detail-formulas/{project_id}` | 读取本项目生效的科目明细公式覆盖 + 自定义新增（全局 + 本项目）；无配置时返回空结构。 | `routers/tb_detail_formulas.py:56` `get_tb_detail_formulas` | get_current_user、require_project_access(readonly) | 2 |
| PUT | `/api/report-config/tb-detail-formulas/{project_id}` | 保存科目明细公式（整表语义；按载入时的版本令牌差量写本项目适配，缺令牌 428、过期 409）。 | `routers/tb_detail_formulas.py:68` `save_tb_detail_formulas` | get_current_user、require_project_access(edit) | 2 |
| POST | `/api/security/lock-account` | 锁定账户 = 停用（与用户管理页「停用」同一逻辑：不能锁自己、至少保留一个启用的管理员）。 | `routers/security.py:34` `lock_account` | get_current_user、require_role | 0 |
| GET | `/api/t-account-templates` | 静态模版清单（不含任何项目数据，无需项目鉴权）。 | `routers/t_accounts.py:175` `get_templates` | — | 0 |
| POST | `/api/trial-balance/{project_id}/{year}/sync-from-workpaper` | 以底稿审定数覆盖试算表，触发级联更新 | `routers/tb_sync.py:25` `sync_from_workpaper` | get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows` | 获取完整嵌套树（父行嵌套 children + Summary 合计）。 | `routers/bad_debt_rows.py:99` `get_tree` | dedicated_wp_gate、get_current_user | 21 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/aging-segments` | 获取当前底稿的账龄段配置（不存在返回 null）。 | `routers/bad_debt_rows.py:374` `get_aging_segments` | dedicated_wp_gate、get_current_user | 1 |
| PUT | `/api/workpapers/{wp_id}/bad-debt-rows/aging-segments` | 保存账龄段配置 + 同步 CREDIT_RISK_AGING 子行。 | `routers/bad_debt_rows.py:394` `save_aging_segments` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/aging-segments/has-amounts` | 检查 CREDIT_RISK_AGING 子行是否有已填金额（用于前端保存前警告）。 | `routers/bad_debt_rows.py:451` `aging_segments_has_amounts` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/aje-suggestion` | 获取坏账准备调整分录建议（零差额返回 null）。 | `routers/bad_debt_rows.py:169` `get_aje_suggestion` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/deserialize` | 从 JSON 恢复完整嵌套结构。校验失败 → 422（返回详细错误列表）。 | `routers/bad_debt_rows.py:191` `deserialize_tree` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/export-data` | 导出含数据的完整坏账准备表 xlsx（父行汇总 + 子行明细 + 合计行）。 | `routers/bad_debt_rows.py:242` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/export-template` | 导出空模板 xlsx（坏账树结构 + 列标题，金额列留空供离线填写）。 | `routers/bad_debt_rows.py:217` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/import-commit` | 将匹配到的行金额批量写入（仅 matched 行的非 None 值覆盖原值）。 | `routers/bad_debt_rows.py:336` `import_commit` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/import-parse` | 上传 xlsx 文件，解析并与当前坏账树 row_label 行匹配。 | `routers/bad_debt_rows.py:285` `import_parse` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/parents` | 新增父行（计提类别）。同一底稿 provision_method 重复 → 409。 | `routers/bad_debt_rows.py:110` `create_parent_row` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/prefill` | 从试算表科目 1231 预填 Summary 期初/期末未审数（no-op 时仍 200）。 | `routers/bad_debt_rows.py:152` `prefill_summary` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/provision-methods` | 查可用坏账计提方法枚举列表及中文显示名（Req 1.4）。 | `routers/bad_debt_rows.py:87` `list_provision_methods` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/serialize` | 导出完整嵌套结构为 JSON。 | `routers/bad_debt_rows.py:180` `serialize_tree` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/{parent_id}/children` | 在指定父行下新增子行（明细行）。父行不存在 → 404。 | `routers/bad_debt_rows.py:128` `create_child_row` | dedicated_wp_gate、get_current_user | 0 |
| DELETE | `/api/workpapers/{wp_id}/bad-debt-rows/{row_id}` | 删除行。删父行级联删子行；拒删最后一个父行 → 400；行不存在 → 404。 | `routers/bad_debt_rows.py:496` `delete_row` | dedicated_wp_gate、get_current_user | 7 |
| PUT | `/api/workpapers/{wp_id}/bad-debt-rows/{row_id}` | 更新单行金额/标签（乐观锁）。version 冲突 → 409；父行有子行编辑金额 → 400。 | `routers/bad_debt_rows.py:474` `update_row` | dedicated_wp_gate、get_current_user | 7 |
| POST | `/api/workpapers/{wp_id}/row-name-mapping/confirm` | 批量确认行名映射（单事务全回滚、幂等、版本冲突 409；Requirement 3.6）。 | `routers/row_name_alignment_router.py:178` `confirm_row_name_mapping` | dedicated_wp_gate、get_current_user、require_wp_edit_permissio | 1 |
| GET | `/projects/{project_id}/account-packages` | 获取工作包列表 | `routers/account_packages.py:105` `list_account_packages` | get_current_user | 0 |
| POST | `/projects/{project_id}/account-packages/import-template` | 导入自定义科目模板：解析 + 校验 + 登记为项目级/事务所级工作包。 | `routers/account_packages.py:309` `import_account_package_template` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{package_id}` | 获取工作包详情 | `routers/account_packages.py:130` `get_account_package` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{package_id}/confirmation-summary` | 获取函证摘要（只读消费 confirmation_service） | `routers/account_packages.py:186` `get_confirmation_summary` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{package_id}/program-status` | 获取工作包下所有程序状态 | `routers/account_packages.py:204` `list_program_statuses` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{package_id}/program-status/{program_code}` | 获取单个程序状态 | `routers/account_packages.py:217` `get_program_status` | get_current_user | 0 |
| PATCH | `/projects/{project_id}/account-packages/{package_id}/program-status/{program_code}` | 更新程序状态（upsert） | `routers/account_packages.py:233` `update_program_status` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{package_id}/summary` | 获取工作包摘要 | `routers/account_packages.py:157` `get_account_package_summary` | get_current_user | 0 |
| GET | `/projects/{project_id}/account-packages/{wp_code}/export-template` | 导出科目工作包结构为可编辑 YAML（含 sheet_type + 字段定义）。 | `routers/account_packages.py:284` `export_account_package_template` | get_current_user | 0 |

## D08 公式、取数与查询（173 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/acnr/anchors` | 列出某 sheet 下的坐标锚点（cell 条目）。 | `routers/acnr.py:337` `acnr_anchors` | get_current_user | 3 |
| GET | `/api/acnr/coverage` | 覆盖度报表 — 标记 semantic_only=true 需补 A1 的条目。 | `routers/acnr.py:459` `acnr_coverage` | get_current_user | 0 |
| GET | `/api/acnr/entries` | 列出 sheet 目录条目（支持按 cycle / import_export 过滤；停用条目默认不列，design § | `routers/acnr.py:325` `acnr_entries` | get_current_user | 3 |
| GET | `/api/acnr/lookup` | 正向查找：按 wp_code / sheet / cell_desc 组合查询。 | `routers/acnr.py:127` `acnr_lookup` | get_current_user | 2 |
| GET | `/api/acnr/metrics` | ACNR 可观测性 — 返回近期 resolve 聚合指标与告警事件。 | `routers/acnr.py:558` `acnr_metrics` | get_current_user、require_role | 0 |
| DELETE | `/api/acnr/overlay` | 删除项目 overlay（受控删除入口）。 | `routers/acnr.py:714` `acnr_overlay_remove` | get_current_user | 1 |
| GET | `/api/acnr/overlay` | 列出项目全部 overlay（read-through：内存缓存缺失时从 PG 加载）。 | `routers/acnr.py:655` `acnr_overlay_list` | get_current_user | 1 |
| POST | `/api/acnr/overlay` | 创建/更新项目 overlay（受控写入口）。 | `routers/acnr.py:670` `acnr_overlay_apply` | get_current_user | 1 |
| GET | `/api/acnr/resolve` | 兼容旧 GET 接口 — 内部也调 full_resolve（无 project_id/wp_id 时等价纯 L1）。 | `routers/acnr.py:286` `acnr_resolve_get` | get_current_user | 3 |
| POST | `/api/acnr/resolve` | 统一解析：接受四种语法之一，返回 canonical addr_id + 物理格。 | `routers/acnr.py:143` `acnr_resolve` | get_current_user | 3 |
| POST | `/api/acnr/resolve-batch` | 批量解析多个地址 — 单次 HTTP 请求解析多条（减少 RTT）。 | `routers/acnr.py:221` `acnr_resolve_batch` | get_current_user | 1 |
| GET | `/api/acnr/resolve-instance` | 项目实例解析 — 唯一 wp_id 出口 (R13.1)。 | `routers/acnr.py:364` `acnr_resolve_instance` | get_current_user | 10 |
| GET | `/api/acnr/workpapers/{wp_id}/locate` | 短链 ``/workpapers/{wp_id}`` 的定位：底稿 id → 所属项目（T16 / RV7.5-01）。 | `routers/acnr.py:421` `acnr_locate_workpaper` | get_current_user | 1 |
| GET | `/api/address-registry` | 搜索可引用地址（支持按域单独加载，减少首次加载量）。 | `routers/address_registry.py:44` `search_addresses` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/address-registry/invalidate` | 精准失效地址缓存（L1 内存 + L2 Redis 同步删除） | `routers/address_registry.py:185` `invalidate_cache` | get_current_user | 1 |
| POST | `/api/address-registry/jump` | 根据URI或公式引用获取前端跳转路由 | `routers/address_registry.py:159` `get_jump_route` | get_current_user | 1 |
| GET | `/api/address-registry/parse` | 工具接口：解析URI或公式引用 | `routers/address_registry.py:223` `parse_address` | get_current_user | 0 |
| GET | `/api/address-registry/resolve` | 解析单个URI为地址详情 | `routers/address_registry.py:112` `resolve_uri` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/address-registry/stats` | 获取注册表统计 | `routers/address_registry.py:100` `get_stats` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/address-registry/v2/anchors` | 查询某底稿（或某 sheet）的语义锚点列表 | `routers/address_registry_v2.py:175` `list_anchors` | get_current_user | 1 |
| GET | `/api/address-registry/v2/dependencies` | 获取某底稿的全部依赖（上游+下游） | `routers/address_registry_v2.py:297` `get_dependencies` | get_current_user | 1 |
| POST | `/api/address-registry/v2/notify-cell-change` | 已停用（spec acnr-foundation-defect-closure D8 / 需求 10）。 | `routers/address_registry_v2.py:358` `notify_cell_change` | get_current_user | 0 |
| GET | `/api/address-registry/v2/resolve` | 语义描述 → 物理坐标。 | `routers/address_registry_v2.py:90` `resolve_address` | get_current_user | 1 |
| GET | `/api/address-registry/v2/stale-impact` | 计算单元格变更的下游影响范围（BFS） | `routers/address_registry_v2.py:203` `stale_impact` | get_current_user | 1 |
| GET | `/api/address-registry/v2/stats` | 全局地址注册表统计 | `routers/address_registry_v2.py:72` `get_stats` | get_current_user | 1 |
| POST | `/api/address-registry/validate` | 校验公式中引用的地址是否有效 | `routers/address_registry.py:136` `validate_formula` | get_current_user | 1 |
| GET | `/api/custom-query/address-resolve` | URI 反查模板信息（模板溯源，ADR-AQL-17；R7.4）。 | `routers/custom_query.py:1941` `address_resolve` | get_current_user | 1 |
| GET | `/api/custom-query/artifacts` | 本人证据列表（含已清理的，标明状态）。 | `routers/query_evidence.py:189` `list_artifacts` | get_current_user | 1 |
| GET | `/api/custom-query/artifacts/{artifact_id}` | 证据详情（不含文件）。 | `routers/query_evidence.py:228` `get_artifact` | get_current_user | 2 |
| GET | `/api/custom-query/artifacts/{artifact_id}/download` | 下载证据文件（先重验摘要）。 | `routers/query_evidence.py:242` `download_artifact` | get_current_user | 1 |
| GET | `/api/custom-query/artifacts/{artifact_id}/freshness` | 按证据记录的版本向量判定时效。 | `routers/query_evidence.py:296` `get_artifact_freshness` | get_current_user | 1 |
| GET | `/api/custom-query/artifacts/{artifact_id}/manifest` | 返回清单 JSON，响应头 X-Manifest-SHA256。 | `routers/query_evidence.py:276` `get_artifact_manifest` | get_current_user | 1 |
| POST | `/api/custom-query/cell-writeback` | 高级查询不再提供写入口；保留路径让旧客户端得到可诊断的 410。 | `routers/custom_query.py:1540` `cell_writeback_gone` | — | 0 |
| GET | `/api/custom-query/cross-sheet-trace` | 跨 sheet 公式追溯（BFS 最深 3 层）。 | `routers/custom_query.py:1795` `cross_sheet_trace` | get_current_user | 0 |
| POST | `/api/custom-query/execute` | 执行自定义查询 —— 经 ExecuteCompatibilityAdapter 的唯一执行路径。 | `routers/custom_query.py:995` `execute_query` | get_current_user | 3 |
| POST | `/api/custom-query/export` | 业务视图「导出全部」：按当前查询（条件、列、排序）服务端流式导出全量结果（R8，ADR-AQL-14，design §3 | `routers/custom_query.py:1029` `export_query` | get_current_user | 1 |
| GET | `/api/custom-query/index-health` | Get GIN index health status (building state + size alert). | `routers/custom_query.py:1762` `get_index_health` | get_current_user | 0 |
| GET | `/api/custom-query/indicators` | 获取可查询指标库（树形结构） | `routers/custom_query.py:133` `get_indicators` | get_current_user | 1 |
| GET | `/api/custom-query/runs` | 本人历史（按定义去重，返回各定义最近一次）。 | `routers/query_evidence.py:49` `list_runs` | get_current_user | 1 |
| POST | `/api/custom-query/runs/clear` | 隐藏本人全部运行记录（`entry` 可选）。 | `routers/query_evidence.py:166` `clear_runs` | get_current_user | 1 |
| DELETE | `/api/custom-query/runs/{run_id}` | 隐藏运行记录（软删除）。 | `routers/query_evidence.py:148` `hide_run` | get_current_user | 2 |
| GET | `/api/custom-query/runs/{run_id}` | 运行详情：定义、范围、版本分量、该定义下的证据列表。 | `routers/query_evidence.py:109` `get_run` | get_current_user | 2 |
| GET | `/api/custom-query/runs/{run_id}/freshness` | 过期判定：按运行记录保存的分量范围重新采集并比较。 | `routers/query_evidence.py:134` `get_run_freshness` | get_current_user | 1 |
| GET | `/api/custom-query/template-presets` |  | `routers/custom_query.py:1279` `list_template_presets` | get_current_user | 1 |
| GET | `/api/custom-query/template-presets/{preset_id}/resolve` |  | `routers/custom_query.py:1284` `resolve_template_preset` | get_current_user | 1 |
| GET | `/api/custom-query/template-share-targets` | 「保存为模板」里「指定项目共享」可选的项目（AQ-39）：与保存时逐项目 edit 鉴权同一口径，只列本人能分享到的项目 | `routers/custom_query.py:1265` `template_share_targets` | get_current_user | 1 |
| GET | `/api/custom-query/templates` | 列出当前用户可见的模板（本人、公开、指定项目共享、历史 team；R9.2），最近修改在前，最多 500 条（先过滤后截 | `routers/custom_query.py:1252` `list_templates` | get_current_user | 1 |
| POST | `/api/custom-query/templates` | 创建查询模板（R8.1~R8.4）。 | `routers/custom_query.py:1301` `create_template` | get_current_user | 1 |
| DELETE | `/api/custom-query/templates/{template_id}` | 删除模板 —— **仅创建者**，admin 亦不可删他人模板（R8.5）。 | `routers/custom_query.py:1427` `delete_template` | get_current_user | 2 |
| GET | `/api/custom-query/templates/{template_id}` | 获取模板详情：可见性与列表、执行同一判定（R9.2）。 | `routers/custom_query.py:1361` `get_template` | get_current_user | 2 |
| PUT | `/api/custom-query/templates/{template_id}` | 更新模板（仅创建者）。 | `routers/custom_query.py:1373` `update_template` | get_current_user | 2 |
| POST | `/api/custom-query/templates/{template_id}/execute` | 执行模板 —— 复用 execute 主链路并对目标项目重新鉴权（R8.6；R9.3）。 | `routers/custom_query.py:1443` `execute_template` | get_current_user | 1 |
| GET | `/api/custom-query/templates/{template_id}/resolve` |  | `routers/custom_query.py:1343` `resolve_user_template` | get_current_user | 1 |
| GET | `/api/custom-query/wp-id-by-code` | wp_code → working_paper.id 映射（供前端穿透跳转 WorkpaperEditor 用） | `routers/custom_query.py:836` `wp_id_by_code` | get_current_user | 35 |
| GET | `/api/custom-query/wp-sheet-preview` | 高级查询 sheet 选区器专用端点：返回 cellData 用于网格预览（只读，R4.4）。 | `routers/custom_query.py:868` `wp_sheet_preview` | get_current_user | 1 |
| POST | `/api/custom-query/writeback-confirm` |  | `routers/custom_query_writeback.py:51` `writeback_confirm_gone` | — | 0 |
| POST | `/api/custom-query/writeback-preview` |  | `routers/custom_query_writeback.py:46` `writeback_preview_gone` | — | 0 |
| GET | `/api/formula-audit-log/{project_id}/{year}` | 查询公式变更历史（需求 11.1，ADR-FHIC-12）。 | `routers/formula_audit_log.py:71` `get_audit_log` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/formula-audit-log/{project_id}/{year}` | 人工补记（需求 11.2，ADR-FHIC-12）。 | `routers/formula_audit_log.py:228` `add_audit_log` | get_current_user、require_project_access(edit) | 2 |
| POST | `/api/formula-audit-log/{project_id}/{year}/rollback` | 一键回滚：把这条历史对应的公式位在**本项目**写回 ``target_formula``（spec formula-g | `routers/formula_audit_log.py:276` `rollback_formula` | get_current_user、require_role | 1 |
| GET | `/api/formula-catalog/check-rules` | 各处校对 / 勾稽 / 质控规则的只读目录（spec formula-governance-coverage-closu | `routers/formula_catalog.py:70` `check_rules_catalog` | get_current_user | 1 |
| GET | `/api/formula-functions` | 已注册函数清单（供前端语法高亮 / 自动补全消费）。 | `routers/formula_catalog.py:97` `formula_functions` | get_current_user | 0 |
| GET | `/api/formula-health/{project_id}/{year}` | 返回项目公式健康度六维度指标。 | `routers/formula_health.py:19` `get_formula_health` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/formula-management/import-export/export-data` | 导出当前页面/模块已有公式（预设库条目，含最近计算时间列，Req 23.3）。 | `routers/formula_import_export.py:108` `export_data` | get_current_user | 0 |
| POST | `/api/formula-management/import-export/export-template` | 导出公式模板：首区块=编报说明（单一源）+ 示例公式行（Req 23.2）。 | `routers/formula_import_export.py:97` `export_template` | get_current_user | 0 |
| POST | `/api/formula-management/import-export/import-data` | 导入公式：逐条经 ACNR full_resolve 校验，悬空报告并跳过（Req 23.4）。 | `routers/formula_import_export.py:137` `import_data` | get_current_user | 0 |
| POST | `/api/formula-management/presets/custom` | 新增/更新一条平台级自定义预设（存数据库，隔离于 seed）。 | `routers/formula_import_export.py:263` `create_custom_preset` | get_current_user、require_role | 1 |
| GET | `/api/formula-management/presets/inventory` | 返回 Preset Inventory 逐页登记 + 覆盖度摘要（供 GtFormulaPresetDialog 浏览） | `routers/formula_import_export.py:208` `get_preset_inventory` | get_current_user | 1 |
| GET | `/api/formula-management/presets/page` | 返回某页面（page_key）的预设公式条目（供弹窗浏览/编辑，Req 25.4）。 | `routers/formula_import_export.py:238` `get_preset_page` | get_current_user | 1 |
| GET | `/api/formula-management/reporting-instructions` | 返回公式管理编报说明/说明文档（单一源，与导出模板编报说明同源，Req 23.6/25.3）。 | `routers/formula_import_export.py:338` `get_reporting_instructions_doc` | get_current_user | 1 |
| GET | `/api/formula-push/coverage` | 推送覆盖率：分母 = 编码表 D~N 带科目码的主编码（剔除判为不适用的），分子 = 已登记推送的主编码。 | `routers/formula_push.py:303` `push_coverage` | get_current_user | 1 |
| GET | `/api/formula-push/{project_id}/{year}/verify` | 反向校验：对比源头值与已推送目标值的一致性。deep=true 时重跑推送引擎取实时源头值。 | `routers/formula_push_verify.py:18` `verify_formula_push` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/formula-scope/{project_id}/formulas` | 按 Formula_Scope 过滤公式列表；省略 scope 时返回全局并集（按作用域分组）。 | `routers/formula_scope_query.py:34` `list_formulas_by_scope` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/formula-settings/candidates/{publish_id}/preview` |  | `routers/formula_settings.py:225` `preview_candidate` | get_current_user | 1 |
| POST | `/api/formula-settings/candidates/{publish_id}/review` |  | `routers/formula_settings.py:235` `review_candidate` | get_current_user | 1 |
| GET | `/api/formula-settings/domains` |  | `routers/formula_settings.py:188` `list_domains` | get_current_user | 1 |
| GET | `/api/formula-settings/publishes` | 发布记录：任何登录用户可调，结果按查看人过滤并裁掉他项目信息（需求 7.4，ADR-FHIC-20）。 | `routers/formula_settings.py:213` `get_publishes` | get_current_user | 1 |
| GET | `/api/formula-settings/{domain}/global` |  | `routers/formula_settings.py:251` `get_global` | get_current_user | 1 |
| POST | `/api/formula-settings/{domain}/global/preview` |  | `routers/formula_settings.py:266` `preview` | get_current_user | 1 |
| POST | `/api/formula-settings/{domain}/global/publish` |  | `routers/formula_settings.py:278` `publish` | get_current_user | 1 |
| GET | `/api/formula-templates` |  | `routers/formula_templates.py:143` `list_templates` | get_current_user | 1 |
| POST | `/api/formula-templates` |  | `routers/formula_templates.py:170` `create_template` | get_current_user | 1 |
| DELETE | `/api/formula-templates/{template_id}` |  | `routers/formula_templates.py:234` `delete_template` | get_current_user | 1 |
| GET | `/api/formula-templates/{template_id}` |  | `routers/formula_templates.py:187` `get_template` | get_current_user | 1 |
| PUT | `/api/formula-templates/{template_id}` |  | `routers/formula_templates.py:219` `update_template` | get_current_user | 1 |
| GET | `/api/formula-templates/{template_id}/diff` |  | `routers/formula_templates.py:202` `get_diff` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/global-hints/keep` | 「保留模板」：只把基线换成当前全局，提示消失；不发新版本、不影响订阅项目（所有者或 admin；R6.2）。 | `routers/formula_templates.py:327` `keep_baseline` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/promote` |  | `routers/formula_templates.py:349` `promote` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/promote-preview` |  | `routers/formula_templates.py:339` `promote_preview` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/publish` |  | `routers/formula_templates.py:316` `publish` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/publish-preview` |  | `routers/formula_templates.py:255` `publish_preview` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/rollback` |  | `routers/formula_templates.py:293` `rollback` | get_current_user | 1 |
| POST | `/api/formula-templates/{template_id}/rollback-preview` |  | `routers/formula_templates.py:277` `rollback_preview` | get_current_user | 1 |
| GET | `/api/formula-templates/{template_id}/subscribers` |  | `routers/formula_templates.py:212` `get_subscribers` | get_current_user | 1 |
| GET | `/api/formula-templates/{template_id}/versions` |  | `routers/formula_templates.py:195` `get_versions` | get_current_user | 1 |
| GET | `/api/formula-timeline/{project_id}/{year}` | 返回项目公式版本时间轴（聚合五数据源，按时间倒序）。 | `routers/formula_timeline.py:18` `get_formula_timeline` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/formula/batch-execute` | 批量执行取数公式（同一项目与年度、至多 ``BATCH_LIMIT`` 条，整批一个时限） | `routers/formula.py:133` `batch_execute_formulas` | get_current_user | 1 |
| GET | `/api/formula/custom-functions` | 列出所有自定义函数 | `routers/formula.py:65` `list_custom_functions` | get_current_user | 0 |
| POST | `/api/formula/custom-functions` | 注册自定义公式函数 —— 停用（501）。 | `routers/formula.py:80` `register_custom_function` | get_current_user、require_role | 0 |
| DELETE | `/api/formula/custom-functions/{name}` | 注销自定义函数 —— 停用（501），原因同注册。 | `routers/formula.py:95` `unregister_custom_function` | get_current_user、require_role | 1 |
| POST | `/api/formula/debug` | 调试运行公式：构造上下文 → 执行 → 返回 trace。 | `routers/formula_debug.py:50` `debug_formula` | get_current_user | 1 |
| POST | `/api/formula/execute` | 执行单个取数公式（中央执行合同，ADR-FHIC-19：失败 ``ok=false`` / ``value=null`` | `routers/formula.py:105` `execute_formula` | get_current_user | 1 |
| GET | `/api/formula/functions` | 列出所有可用函数（内置 + 自定义） | `routers/formula.py:58` `list_all_functions` | get_current_user | 0 |
| GET | `/api/linkage-bus/formula-usage` | 从公式找引用方：查询谁引用了指定 URI。 | `routers/linkage_bus.py:405` `get_formula_usage` | get_current_user | 1 |
| GET | `/api/linkage-bus/formulas-for` | 从文档找公式：查询指定文档/模块的所有公式边。 | `routers/linkage_bus.py:459` `get_formulas_for` | get_current_user | 1 |
| GET | `/api/my/procedure-row-tasks` | 跨项目"我的程序任务"分页查询（可选 project 收窄，纯读）。 | `routers/procedure_task_query.py:89` `list_my_row_tasks` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/auto-data/{source}` | 调用注册的 auto_data_source resolver 返回结果。 | `routers/auto_data.py:50` `get_auto_data` | get_current_user、require_project_access(readonly) | 8 |
| POST | `/api/projects/{project_id}/cross-check/execute` | 执行校验（全量或指定规则） | `routers/wp_cross_check.py:55` `execute_cross_check` | get_current_user、require_project_access(readonly)、require_pr | 2 |
| GET | `/api/projects/{project_id}/cross-check/results` | 获取最近校验结果 | `routers/wp_cross_check.py:90` `get_results` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/cross-check/rules` | 获取规则库（内置 + 项目自定义） | `routers/wp_cross_check.py:102` `get_rules` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/cross-check/rules/custom` | 新增项目级自定义规则 | `routers/wp_cross_check.py:113` `add_custom_rule` | get_current_user、require_project_access(edit)、require_projec | 2 |
| POST | `/api/projects/{project_id}/custom-fetch/execute` | 执行自定义取数规则（支持跳行跳列、任选单元格） | `routers/data_fetch_custom.py:45` `execute_fetch_rules` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/custom-fetch/rules` | 获取项目的自定义取数规则 | `routers/data_fetch_custom.py:147` `get_custom_rules` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/custom-fetch/save-rules` | 保存自定义取数规则到项目配置 | `routers/data_fetch_custom.py:105` `save_custom_rules` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/custom-fetch/trace-backward` | 反向溯源：数据源变更 → 显示哪些目标引用了它 | `routers/data_fetch_custom.py:88` `trace_backward` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/custom-fetch/trace-forward` | 正向溯源：点击目标单元格 → 显示数据来源 + 跳转链接 | `routers/data_fetch_custom.py:71` `trace_forward` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/formula-catalog` | 本项目有效公式的扁平目录，可按域筛选。 | `routers/formula_catalog.py:26` `formula_catalog` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/formula-catalog/stats` | 按域 / 层级 / 函数的计数摘要。 | `routers/formula_catalog.py:56` `formula_catalog_stats` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/formula-push/bindings` | 返回公式推送 binding 接入清单；清单本身不依赖项目数据。 | `routers/formula_push.py:88` `list_bindings` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/formula-push/latest` |  | `routers/formula_push.py:188` `latest` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/formula-push/rules` | 本项目有效规则（含已停用 / 失效的）：每条带层级与可用操作（spec formula-governance-cover | `routers/formula_push.py:105` `list_rules` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/formula-push/run` | 试跑同步返回明细；实际写入提交 durable job，避免公式推送占住 Web 请求。 | `routers/formula_push.py:130` `run_push` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula-push/runs` | 返回公式推送运行历史列表（最近优先）。 | `routers/formula_push.py:259` `list_runs` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/formula-push/runs/{run_id}/items` | 按 run_id 返回逐项推送明细，可按 outcome 筛选 skip/failed 等。 | `routers/formula_push.py:276` `run_items` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/formula-push/states` |  | `routers/formula_push.py:205` `states` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/formula-push/states/adopt` |  | `routers/formula_push.py:220` `adopt` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/formula-push/states/lock` |  | `routers/formula_push.py:237` `lock` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/formula-settings/apply-targets` | 「应用到指定项目」可选的目标：当前用户有 edit 权限、未归档的其他项目（R7.3）。 | `routers/formula_settings.py:337` `apply_targets` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/formula-settings/dependencies` | 一条公式的上游引用与下游被引用（按本项目有效定义精确匹配，只读）。 | `routers/formula_settings.py:469` `formula_dependencies` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/formula-settings/pending` |  | `routers/formula_settings.py:294` `get_pending` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/formula-settings/pending/resolve` | 处理待确认：每条回传列表里的 ``revision``；缺 428、已被覆盖或已处理 409，整体回滚（需求 8.2）。 | `routers/formula_settings.py:319` `resolve` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula-settings/propagation` | 项目级只读：派发状态与业务回执分开，可按年度、域或耐久事件身份精确查询。 | `routers/formula_settings.py:304` `get_propagation` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/formula-settings/{domain}/apply` |  | `routers/formula_settings.py:440` `apply` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/formula-settings/{domain}/apply-preview` |  | `routers/formula_settings.py:419` `apply_preview` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula-settings/{domain}/effective` |  | `routers/formula_settings.py:362` `get_effective` | get_current_user、require_project_access(readonly) | 1 |
| DELETE | `/api/projects/{project_id}/formula-settings/{domain}/overrides` |  | `routers/formula_settings.py:386` `restore_global` | get_current_user、require_project_access(edit) | 1 |
| PUT | `/api/projects/{project_id}/formula-settings/{domain}/overrides` |  | `routers/formula_settings.py:375` `save_overrides` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/formula-templates/subscribe` |  | `routers/formula_templates.py:385` `subscribe` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/formula-templates/subscribe-preview` |  | `routers/formula_templates.py:378` `subscribe_preview` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula-templates/subscriptions` |  | `routers/formula_templates.py:366` `list_subscriptions` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/formula-templates/unsubscribe` |  | `routers/formula_templates.py:400` `unsubscribe` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/formula-templates/unsubscribe-preview` |  | `routers/formula_templates.py:394` `unsubscribe_preview` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula/cross-check-history` | 本项目本年度最近 N 次表间审核：每次的计数 + 仍保留的逐条结论（只读）。 | `routers/formula_logic_check.py:242` `cross_check_history` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/formula/cross-check-rules` | 读取项目生效的表间审核规则（全局 + 本项目，按树节点 key 分组，带层级与版本令牌）。 | `routers/formula_logic_check.py:189` `get_cross_check_rules` | get_current_user、require_project_access(readonly) | 1 |
| PUT | `/api/projects/{project_id}/formula/cross-check-rules` | 整体替换项目的用户表间审核规则，返回保存后的生效集合。 | `routers/formula_logic_check.py:204` `save_cross_check_rules` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/formula/report-cross-check` | 执行报表勾稽（7 条 logic_check 公式）→ 返回 Issue_List + run_id。 | `routers/formula_logic_check.py:102` `run_report_cross_check` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/procedure-row-tasks` | 项目级"我的程序任务"分页查询（当前 user 的 assignee/reviewer 任务，纯读）。 | `routers/procedure_task_query.py:66` `list_project_row_tasks` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/procedure-row-tasks/{task_id}` | 单任务详情（纯读）。 | `routers/procedure_task_query.py:112` `get_row_task_detail` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/prefill/apply` | Prefill 应用 — 将用户确认的 cell 写入底稿 | `routers/wp_prefill_preview.py:134` `prefill_apply` | dedicated_wp_gate、get_current_user、require_project_access(ed | 0 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/prefill/preview` | Prefill 预览 — 执行公式计算但不写入，返回 diff 列表 | `routers/wp_prefill_preview.py:80` `prefill_preview` | dedicated_wp_gate、get_current_user、require_project_access(ed | 0 |
| GET | `/api/projects/{project_id}/workpapers/prefill-context` | 获取项目级预填充上下文（公司名/年度/合伙人/重要性等） | `routers/wp_prefill_context.py:12` `get_prefill_context` | get_current_user | 1 |
| GET | `/api/query/access` | 当前用户能否使用构建器（前端入口据此置灰并显示原因，与后端门禁同一判定，R3.6）。 | `routers/query_builder.py:189` `get_access` | get_current_user | 1 |
| POST | `/api/query/execute` | 执行查询，返回结构化结果（``total`` 为全量行数，分组时为组数）。 | `routers/query_builder.py:337` `execute_query` | get_current_user、require_query_builder_access | 1 |
| POST | `/api/query/export-excel` | 导出全部（advanced-query-linkage-closure R8，ADR-AQL-14）：与 execute | `routers/query_builder.py:512` `export_excel` | get_current_user、require_query_builder_access | 1 |
| POST | `/api/query/preview` | 仅生成 SQL（不执行），用于前端"SQL 预览"。 | `routers/query_builder.py:219` `preview_query` | get_current_user、require_query_builder_access | 1 |
| GET | `/api/query/schema` | 返回白名单表/字段元信息（前端用于构造可视化选择器）。 | `routers/query_builder.py:144` `get_schema` | get_current_user、require_query_builder_access | 1 |
| GET | `/api/system/dicts` | 返回所有枚举字典，前端启动时加载一次并缓存到 sessionStorage | `routers/system_dicts.py:328` `get_system_dicts` | get_current_user | 3 |
| POST | `/api/system/dicts/{dict_key}/items` | 拒绝新增枚举项 — value 由代码硬编码（DT-3 / D13 ADR）。 | `routers/system_dicts.py:684` `reject_dict_item_create` | — | 1 |
| DELETE | `/api/system/dicts/{dict_key}/items/{item_value}` | 拒绝物理删除枚举值 — 已被代码引用不可删（DT-3 / D13 ADR）。 | `routers/system_dicts.py:697` `reject_dict_item_delete_value` | — | 1 |
| PUT | `/api/system/dicts/{dict_key}/items/{item_value}` | DT-3 方案 B：仅修改 label/color（value 锁定，admin 可改） | `routers/system_dicts.py:505` `update_dict_item` | get_current_user | 1 |
| DELETE | `/api/system/dicts/{dict_key}/items/{item_value}/override` | DT-3 方案 B：清除 label/color 覆盖，恢复代码默认值（不删除枚举值本身） | `routers/system_dicts.py:619` `reset_dict_item_override` | get_current_user | 0 |
| GET | `/api/system/dicts/{dict_key}/usage-count` | 返回某字典各枚举值的引用计数。 | `routers/system_dicts.py:453` `get_dict_usage_count` | get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/formulas` | 列出该底稿的全部自定义公式（含 D-cycle 四表库提取分层，灰度开关 + 仅 D1–D7）。 | `routers/wp_formula.py:745` `list_formulas` | dedicated_wp_gate、get_current_user | 21 |
| PUT | `/api/workpapers/{wp_id}/formulas` | 保存（upsert）一条底稿公式；悬空引用返回 422。 | `routers/wp_formula.py:875` `save_formula` | dedicated_wp_gate、get_current_user | 21 |
| PUT | `/api/workpapers/{wp_id}/formulas/batch` | 批量 upsert 底稿公式——**单事务 + CAS + 行数限额**（Task 5.4 / design §5 步骤 | `routers/wp_formula.py:1217` `save_formulas_batch` | dedicated_wp_gate、get_current_user | 2 |
| DELETE | `/api/workpapers/{wp_id}/formulas/{formula_id}` | 删除单条底稿公式。 | `routers/wp_formula.py:1396` `delete_formula` | dedicated_wp_gate、get_current_user | 7 |
| GET | `/api/workpapers/{wp_id}/user-formulas` |  | `routers/wp_user_formulas.py:243` `list_user_formulas` | dedicated_wp_gate、get_current_user | 20 |
| PUT | `/api/workpapers/{wp_id}/user-formulas` |  | `routers/wp_user_formulas.py:293` `update_user_formulas` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/user-formulas/v2` |  | `routers/wp_user_formulas_v2.py:33` `list_user_formulas_v2` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/user-formulas/v2/{formula_id}/history` |  | `routers/wp_user_formulas_v2.py:52` `user_formula_v2_history` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/user-formulas/v2:batchMutate` |  | `routers/wp_user_formulas_v2.py:42` `batch_mutate_user_formulas_v2` | dedicated_wp_gate、get_current_user | 1 |
| DELETE | `/api/workpapers/{wp_id}/user-formulas/{cell_key:path}` |  | `routers/wp_user_formulas.py:615` `restore_preset_formula` | dedicated_wp_gate、get_current_user | 6 |
| POST | `/api/workpapers/{wp_id}/validate-formula` | 校验公式语法并可选预览结果 | `routers/wp_user_formulas.py:700` `validate_formula` | dedicated_wp_gate、get_current_user | 20 |

## D06 报表、审计报告与交付件（169 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/accounting-standards` | 准则列表 | `routers/accounting_standards.py:34` `list_standards` | — | 1 |
| POST | `/api/accounting-standards/seed` | 加载种子数据（幂等） | `routers/accounting_standards.py:51` `load_seed_data` | — | 1 |
| GET | `/api/accounting-standards/{standard_code}/chart` | 获取准则对应的标准科目表 | `routers/accounting_standards.py:77` `get_standard_chart` | — | 0 |
| GET | `/api/accounting-standards/{standard_code}/note-templates` | 获取准则对应的附注模版配置 | `routers/accounting_standards.py:91` `get_standard_note_templates` | — | 0 |
| GET | `/api/accounting-standards/{standard_code}/report-formats` | 获取准则对应的报表格式配置 | `routers/accounting_standards.py:84` `get_standard_report_formats` | — | 0 |
| GET | `/api/accounting-standards/{standard_id}` | 准则详情 | `routers/accounting_standards.py:41` `get_standard` | — | 1 |
| GET | `/api/audit-logs/export` | 导出审计日志。 | `routers/security.py:66` `export_audit_logs` | get_current_user、require_role | 0 |
| POST | `/api/audit-report/generate` | 从模板生成审计报告 | `routers/audit_report.py:71` `generate_report` | get_current_user | 1 |
| GET | `/api/audit-report/templates` | 获取审计报告模板列表 | `routers/audit_report.py:58` `get_templates` | get_current_user | 1 |
| POST | `/api/audit-report/templates/load-seed` | 加载审计报告模板种子数据 | `routers/audit_report.py:42` `load_seed_templates` | get_current_user | 2 |
| GET | `/api/audit-report/{project_id}/{year}` | 获取审计报告 | `routers/audit_report.py:126` `get_report` | get_current_user | 3 |
| POST | `/api/audit-report/{project_id}/{year}/refresh-financial-data` | 刷新审计报告中的财务数据引用。 | `routers/audit_report.py:224` `refresh_financial_data` | get_current_user | 1 |
| PUT | `/api/audit-report/{report_id}/paragraphs/{section}` | 更新审计报告指定段落内容 | `routers/audit_report.py:141` `update_paragraph` | get_current_user | 1 |
| PUT | `/api/audit-report/{report_id}/status` | 更新审计报告状态（draft→review→eqcr_approved→final） | `routers/audit_report.py:179` `update_status` | get_current_user | 1 |
| POST | `/api/cfs-worksheet/adjustments` | 创建CFS调整分录 | `routers/cfs_worksheet.py:70` `create_adjustment` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/cfs-worksheet/adjustments/{adjustment_id}` | 删除CFS调整分录 | `routers/cfs_worksheet.py:120` `delete_adjustment` | get_current_user、require_project_access(edit) | 2 |
| PUT | `/api/cfs-worksheet/adjustments/{adjustment_id}` | 修改CFS调整分录 | `routers/cfs_worksheet.py:99` `update_adjustment` | get_current_user、require_project_access(edit) | 2 |
| POST | `/api/cfs-worksheet/auto-generate` | 自动生成常见调整项 | `routers/cfs_worksheet.py:160` `auto_generate_adjustments` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/cfs-worksheet/generate` | 生成工作底稿 | `routers/cfs_worksheet.py:43` `generate_worksheet` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/cfs-worksheet/{project_id}/{year}` | 获取工作底稿数据 | `routers/cfs_worksheet.py:58` `get_worksheet` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/cfs-worksheet/{project_id}/{year}/adjustments` | 列出所有CFS调整分录 | `routers/cfs_worksheet.py:135` `list_adjustments` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/cfs-worksheet/{project_id}/{year}/indirect-method` | 获取间接法补充资料 | `routers/cfs_worksheet.py:180` `get_indirect_method` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/cfs-worksheet/{project_id}/{year}/main-table` | 获取现金流量表主表数据 | `routers/cfs_worksheet.py:204` `get_main_table` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/cfs-worksheet/{project_id}/{year}/reconciliation` | 获取工作底稿平衡状态 | `routers/cfs_worksheet.py:148` `get_reconciliation` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/cfs-worksheet/{project_id}/{year}/verify` | 勾稽校验 | `routers/cfs_worksheet.py:192` `verify_reconciliation` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/export/create` | 创建导出任务并同步执行（MVP 无 Celery） | `routers/export.py:42` `create_export_task` | get_current_user | 1 |
| GET | `/api/export/{project_id}/history` | 获取项目导出历史 | `routers/export.py:117` `get_export_history` | get_current_user | 1 |
| GET | `/api/export/{task_id}/download` | 下载导出文件 | `routers/export.py:90` `download_export` | get_current_user | 1 |
| GET | `/api/export/{task_id}/status` | 查询导出任务状态 | `routers/export.py:76` `get_task_status` | get_current_user | 1 |
| GET | `/api/exports/{export_id}/download` | 下载导出包（校验一次性令牌） | `routers/export_integrity.py:121` `download_export` | get_current_user | 0 |
| POST | `/api/exports/{export_id}/download-token` | 生成一次性下载令牌（TTL=600s），下载时校验并删除 | `routers/export_integrity.py:86` `create_download_token` | get_current_user | 0 |
| GET | `/api/exports/{export_id}/integrity` | 校验导出包完整性：逐文件比对 SHA-256 | `routers/export_integrity.py:18` `verify_export_integrity` | get_current_user | 1 |
| GET | `/api/exports/{export_id}/manifest` | 获取导出包的 manifest（文件列表 + hash） | `routers/export_integrity.py:40` `get_export_manifest` | get_current_user | 0 |
| GET | `/api/exports/{task_id}` | 下载 artifact；查询和项目权限校验的 session 在返回 FileResponse 前已关闭。 | `routers/batch_export_progress.py:255` `download_export` | get_current_user_stream | 0 |
| GET | `/api/exports/{task_id}/status` | 状态恢复端点：优先 durability DB，退役窗口内再读旧内存任务。 | `routers/batch_export_progress.py:229` `get_export_status` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/accounting-standard` | 切换项目会计准则 | `routers/accounting_standards.py:60` `switch_project_standard` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/ai/annual-diff-report` | 年度差异分析报告 — 对比当年与上年试算表 | `routers/report_trace.py:544` `annual_diff_report` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/ai/recommend-workpapers` | LLM 推荐底稿优先级 — 基于风险评估和项目进度 | `routers/report_trace.py:490` `recommend_workpapers` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/attachments/classify` | 附件智能分类（stub） | `routers/report_trace.py:602` `classify_attachment` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/cash-equivalents` | 现金及现金等价物列示 + BS 货币资金勾稽 | `routers/cf_verification.py:29` `get_cash_equivalents` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/cf-verification/{year}/create-adjustment` | 旧现金流差异自动建分录入口已退役；保留墓碑帮助旧客户端迁移。 | `routers/cf_verification.py:100` `create_cf_adjustment` | get_current_user、require_project_access(edit)、require_projec | 0 |
| POST | `/api/projects/{project_id}/cf-verification/{year}/explanation` | 保存用户差异说明 | `routers/cf_verification.py:84` `save_explanation` | get_current_user、require_project_access(edit)、require_projec | 1 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/export` | 导出 A5-1 格式 Excel（现金流量表核查底稿） | `routers/cf_verification.py:120` `export_a5_excel` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/main-table` | 主表逆算验证 | `routers/cf_verification.py:51` `verify_main_table` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/reconcile` | BS-CF 勾稽核对 | `routers/cf_verification.py:40` `reconcile_bs_cf` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/results` | 获取已缓存的核查结果 | `routers/cf_verification.py:73` `get_saved_results` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/cf-verification/{year}/supplementary` | 附表间接法核对 | `routers/cf_verification.py:62` `verify_supplementary` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/check-delete-permission` | 检查删除权限 — 从当前用户角色判断 | `routers/report_trace.py:249` `check_delete_permission` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/data-validation/export` | 导出校验结果。 | `routers/data_validation.py:64` `export_findings` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/` |  | `routers/deliverable.py:251` `list_deliverables` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/deliverables/archive` |  | `routers/deliverable.py:1575` `archive_deliverables` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/completeness` |  | `routers/deliverable.py:945` `check_completeness` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/deliverables/disclosure-notes/render` | 选择性导出附注 Word 并双路径存储 | `routers/deliverable.py:699` `render_disclosure_notes` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/financial-reports/render` | 选择性导出财务报表 Excel 并双路径存储 | `routers/deliverable.py:880` `render_financial_reports` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/onlyoffice/callback/{task_id}` |  | `routers/deliverable.py:1784` `onlyoffice_callback` | — | 0 |
| GET | `/api/projects/{project_id}/deliverables/onlyoffice/config/{task_id}/{version_no}` |  | `routers/deliverable.py:1692` `onlyoffice_config` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/onlyoffice/health` |  | `routers/deliverable.py:1762` `onlyoffice_health` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/deliverables/package` |  | `routers/deliverable.py:1648` `create_package` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/package/{job_id}/download` |  | `routers/deliverable.py:1669` `download_package` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/deliverables/report-body/confirm` | 报告正文两阶段生成 — confirm 阶段（design §11 / §4）。 | `routers/deliverable.py:518` `confirm_report_body` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/report-body/load-template` |  | `routers/deliverable.py:443` `load_report_body_template` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/report-body/preview` | 报告正文两阶段生成 — preview 阶段（design §11 / §4）。 | `routers/deliverable.py:461` `preview_report_body` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/report-body/preview-html` |  | `routers/deliverable.py:1844` `preview_report_body_html` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/report-body/render` | [DEPRECATED — 旧单阶段路径] 渲染并存储审计报告正文。 | `routers/deliverable.py:569` `render_report_body` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/report-body/report-date-compliance` |  | `routers/deliverable.py:1447` `report_date_compliance` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/deliverables/trio` | 一键出具三件套 — 创建 deliverable_trio job。 | `routers/deliverable.py:1097` `create_trio_job` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/trio/history` | 获取项目/年度维度的全部三件套 job 历史。 | `routers/deliverable.py:1048` `get_trio_history` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/trio/items/{item_id}/attempts` | 获取某 item 的全部 attempt 历史。 | `routers/deliverable.py:1013` `get_trio_item_attempts` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/trio/items/{item_id}/download` | 下载三件套单项文件 — 下载前校验物理文件和 hash。 | `routers/deliverable.py:1294` `download_trio_item` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/trio/jobs/{job_id}` | 获取三件套 job 详情（含 items + 最新 attempt）。 | `routers/deliverable.py:990` `get_trio_job` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/deliverables/trio/jobs/{job_id}/recover` | 恢复中断/超时的 running 状态（fail-closed）。 | `routers/deliverable.py:1067` `recover_stale_running` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/deliverables/trio/jobs/{job_id}/retry` | 重试三件套失败步骤 — 真实调用 executor 步骤入口。 | `routers/deliverable.py:1212` `retry_trio_job` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/trio/readiness` | 交付中心三件套 readiness 检查。 | `routers/deliverable.py:969` `check_trio_readiness` | get_current_user | 2 |
| DELETE | `/api/projects/{project_id}/deliverables/{task_id}` | 删除交付物（仅 draft/editing 态且非归档可删） | `routers/deliverable.py:1860` `delete_deliverable` | get_current_user | 5 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/approve` |  | `routers/deliverable.py:1498` `approve_deliverable` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/integrity-verify` |  | `routers/deliverable.py:1625` `verify_integrity` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/reject` |  | `routers/deliverable.py:1536` `reject_deliverable` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/sign` |  | `routers/deliverable.py:1417` `sign_deliverable` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/snapshot-stale` |  | `routers/deliverable.py:1393` `check_snapshot_stale` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/submit-approval` |  | `routers/deliverable.py:1462` `submit_approval` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/unarchive` |  | `routers/deliverable.py:1594` `unarchive_deliverable` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions` |  | `routers/deliverable.py:279` `get_version_chain` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/deliverables/{task_id}/versions/compare` |  | `routers/deliverable.py:298` `compare_versions` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/download` |  | `routers/deliverable.py:325` `download_version` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/guidance-download` | 下载「编制参考版」（含内部 ##NOTE## 提示的 with_notes 副本，§13.2）。 | `routers/deliverable.py:361` `download_guidance_version` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/preview-url` |  | `routers/deliverable.py:405` `preview_version` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/signed-download` | OnlyOffice 专用免认证下载（通过 HMAC 签名验证，10 分钟有效） | `routers/deliverable.py:1908` `signed_download_version` | — | 0 |
| POST | `/api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-section` | 单章节增量刷新。 | `routers/deliverable_lineage.py:399` `refresh_section` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-stale` | 批量刷新所有过期章节。 | `routers/deliverable_lineage.py:467` `refresh_stale` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/deliverables/{word_export_task_id}/section-states` | 出品物章节状态列表查询。 | `routers/deliverable_lineage.py:198` `get_section_states` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/projects/{project_id}/deliverables/{word_export_task_id}/trace` | 出品物章节溯源查询。 | `routers/deliverable_lineage.py:149` `trace_deliverable` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/deliverables/{word_export_task_id}/writeback` | 出品物报告正文回填（显式按钮触发）。 | `routers/deliverable_lineage.py:323` `writeback_deliverable` | get_current_user | 3 |
| GET | `/api/projects/{project_id}/findings-summary` | 项目发现汇总（要求项目成员；原先只校验登录，R9.1）。 | `routers/report_trace.py:41` `findings_summary` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/ledger/aux-summary` |  | `routers/report_trace.py:199` `aux_summary` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/reports/cell` | 更新报表单元格值（权益表/减值表矩阵编辑）。 | `routers/reports.py:744` `update_report_cell` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/reports/export-excel` | 导出报表 Excel 文件 | `routers/report_export.py:46` `export_excel` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/reports/line-composition` | 查询报表行的构成科目列表。 | `routers/reports.py:630` `get_line_composition` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/reports/multi-year` | 多年度对比查询 API | `routers/reports.py:521` `get_multi_year_report` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/word-exports/audit-report/generate` | 生成审计报告 Word 草稿并创建 ExportTask | `routers/word_export.py:60` `generate_audit_report` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/word-exports/disclosure-notes/generate` | 生成附注 Word 草稿 | `routers/word_export.py:121` `generate_disclosure_notes` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/word-exports/financial-reports/generate` | 生成财务报表 Word 并绑定最新快照 | `routers/word_export.py:91` `generate_financial_reports` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/word-exports/full-deliverables` | 旧全套入口已退役；正式出具只走带 readiness/snapshot 的 trio。 | `routers/word_export.py:409` `create_full_deliverables` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/word-exports/full-package` | 全套导出：审计报告+4张报表+附注 → ZIP打包 | `routers/word_export.py:294` `create_full_package` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/word-exports/history` | 获取项目 Word 导出历史 | `routers/word_export.py:188` `get_export_history` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/word-exports/jobs/{job_id}` | 获取后台任务状态 | `routers/word_export.py:432` `get_job_status` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/word-exports/jobs/{job_id}/retry` | 重试失败项 | `routers/word_export.py:459` `retry_failed_items` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/word-exports/report-snapshot/create` | 创建报表数据快照 | `routers/word_export.py:206` `create_report_snapshot` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/word-exports/report-snapshot/latest` | 获取最新快照（含过期检测） | `routers/word_export.py:238` `get_latest_snapshot` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/word-exports/report-snapshot/stale-check` | 检测报表快照是否过期（trial_balance 数据已变更） | `routers/word_export.py:268` `check_snapshot_stale` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/word-exports/{task_id}/confirm` | 人工确认导出任务 | `routers/word_export.py:151` `confirm_export` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/word-exports/{task_id}/download` | 下载已生成的导出文件 | `routers/word_export.py:490` `download_export_file` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/working-papers/batch-export-async` | 提交耐久导出 job；请求路径只做权限/预算/INSERT，不在 Web 事件循环压缩 ZIP。 | `routers/batch_export_progress.py:176` `batch_export_async` | get_current_user、require_project_access(readonly) | 12 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/export-word` | 导出 Word 文档。 | `routers/wp_export_word.py:58` `get_export_word` | dedicated_wp_gate、get_current_user、require_project_access(re | 3 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete` | 导出前完整性检查。 | `routers/wp_export_word.py:91` `get_check_incomplete` | dedicated_wp_gate、get_current_user、require_project_access(re | 0 |
| POST | `/api/projects/{project_id}/workpapers/batch-export-enhanced` | 批量增强导出为 ZIP（含 manifest.json + SHA-256 + 元数据嵌入） | `routers/wp_export_import_router.py:125` `batch_export_enhanced` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 1 |
| POST | `/api/projects/{project_id}/workpapers/import-enhanced` | 增强导入（元数据提取+校验+哈希冲突+归档+上传） | `routers/wp_export_import_router.py:336` `import_enhanced` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/import/resolve` | 冲突解决端点 | `routers/wp_export_import_router.py:394` `import_resolve` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/export-history` | 查询底稿导出历史（WpExportSnapshot 列表） | `routers/wp_export_import_router.py:252` `get_export_history` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/export-with-metadata` | 导出单份底稿（嵌入元数据 + 记录快照哈希）— 流式路径：响应体发送前 commit 并释放 DB 会话。 | `routers/wp_export_import_router.py:74` `export_with_metadata` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/import-validate` | 仅校验导入文件（不执行实际导入） | `routers/wp_export_import_router.py:290` `import_validate` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/version-archives` | 查询底稿版本归档历史（WpVersionArchive 列表；底稿侧栏「历史版本」面板）。 | `routers/wp_export_import_router.py:459` `get_version_history` | dedicated_wp_gate、get_current_user、require_project_access(re | 0 |
| POST | `/api/regulatory/archival-standard` | 提交电子底稿归档标准 | `routers/regulatory.py:74` `submit_archival_standard` | get_current_user | 1 |
| POST | `/api/regulatory/cicpa-report` | 提交中注协审计报告备案 | `routers/regulatory.py:54` `submit_cicpa_report` | get_current_user | 1 |
| GET | `/api/regulatory/filings` | 列出所有备案记录 | `routers/regulatory.py:124` `list_filings` | get_current_user | 1 |
| POST | `/api/regulatory/filings/{filing_id}/response` | 处理备案响应（状态更新） | `routers/regulatory.py:142` `handle_filing_response` | get_current_user | 0 |
| POST | `/api/regulatory/filings/{filing_id}/retry` | 重试失败的备案 | `routers/regulatory.py:108` `retry_filing` | get_current_user | 1 |
| GET | `/api/regulatory/filings/{filing_id}/status` | 查询备案状态 | `routers/regulatory.py:94` `get_filing_status` | get_current_user | 0 |
| GET | `/api/report-config` | 查询报表配置列表。 | `routers/report_config.py:122` `list_report_configs` | get_current_user | 3 |
| POST | `/api/report-config` | 新增配置行。 | `routers/report_config.py:366` `create_report_config` | get_current_user | 3 |
| POST | `/api/report-config/apply-master-update` | 主模板更新同步到项目（V199：经同步内核；改过且不同的行生成待确认事项，不再静默保留）。 | `routers/report_config_baseline.py:148` `apply_master_update` | get_current_user | 1 |
| GET | `/api/report-config/candidates` | 待审核候选列表（admin） | `routers/report_config_baseline.py:175` `list_candidates` | get_current_user、require_role | 1 |
| POST | `/api/report-config/clone` | 克隆标准配置到项目。 | `routers/report_config.py:243` `clone_report_config` | get_current_user | 1 |
| GET | `/api/report-config/diff-vs-master/{project_id}` | 项目级 vs 主模板差异（V199 补项目 readonly 鉴权，原只校验登录） | `routers/report_config_baseline.py:119` `diff_vs_master` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/report-config/drill-down` | 汇总穿透：合并报表某行由企业树各节点怎样构成（spec consol-elimination-single-source | `routers/report_drill_down.py:21` `report_drill_down` | get_current_user | 1 |
| POST | `/api/report-config/execute-formula` | 公式试算：请求体 ``project_id`` / ``year``（必填）/ ``formula`` / ``row_ | `routers/report_config.py:480` `execute_formula` | get_current_user | 1 |
| POST | `/api/report-config/execute-formulas-batch` | 批量公式试算：请求体 ``project_id`` / ``year``（必填）/ ``formulas: [{row_ | `routers/report_config.py:496` `execute_formulas_batch` | get_current_user | 1 |
| POST | `/api/report-config/fill-formulas` | 填充报表公式（幂等，admin 权限）。 | `routers/report_config.py:442` `fill_formulas` | get_current_user、require_role | 1 |
| POST | `/api/report-config/review-candidate` | admin 审核候选：通过则作为全局发布（经同步内核，冲突交项目确认），commit 后发变更事件。 | `routers/report_config_baseline.py:89` `review_candidate` | get_current_user、require_role | 1 |
| POST | `/api/report-config/seed` | 加载种子数据并填充公式（全局模板写操作，仅 admin）。 | `routers/report_config.py:413` `load_seed_data` | get_current_user、require_role | 2 |
| GET | `/api/report-config/stale-status/{project_id}` | 查询项目是否有 stale 配置行 + 报表公式待确认事项（V199 补项目 readonly 鉴权） | `routers/report_config_baseline.py:213` `stale_status` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/report-config/suggest-to-master` | 项目级优化提交为主模板候选（写 ReportConfigBaseline pending）。 | `routers/report_config_baseline.py:62` `suggest_to_master` | get_current_user | 1 |
| GET | `/api/report-config/types` | 返回当前项目（标准）下的报表子类列表及每类公式行数。 | `routers/report_config.py:172` `list_report_types` | get_current_user | 2 |
| DELETE | `/api/report-config/{config_id}` | 删除配置行。 | `routers/report_config.py:385` `delete_report_config` | get_current_user | 4 |
| GET | `/api/report-config/{config_id}` | 查询单行配置详情。 | `routers/report_config.py:222` `get_report_config` | get_current_user | 4 |
| PUT | `/api/report-config/{config_id}` | 修改配置行。 | `routers/report_config.py:291` `update_report_config` | get_current_user | 4 |
| GET | `/api/report-format-templates` |  | `routers/report_trace.py:626` `list_format_templates` | get_current_user | 1 |
| POST | `/api/report-format-templates` |  | `routers/report_trace.py:646` `create_format_template` | get_current_user | 1 |
| GET | `/api/report-review/{project_id}/trace/{section_number}` | 附注章节溯源（读项目的试算表与序时账：要求项目成员；原先只校验登录，spec voucher-workflow-link | `routers/report_trace.py:29` `trace_section` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/reports/generate` | 生成/重新生成四张报表 | `routers/reports.py:85` `generate_reports` | get_current_user、require_operation(report:edit) | 1 |
| GET | `/api/reports/{project_id}/{year}/consistency-check` | 公式审核——内置平衡校验 + 本项目有效配置里的 logic_check / reasonability 公式（真实求值 | `routers/reports.py:154` `consistency_check` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/reports/{project_id}/{year}/{report_type}` | 获取指定报表数据（支持未审/已审切换+国企/上市切换）；只认项目成员（spec consol-autotree-resi | `routers/reports.py:283` `get_report` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/reports/{project_id}/{year}/{report_type}/drilldown/{row_code}` | 报表行穿透查询（只认项目成员） | `routers/reports.py:385` `drilldown_report_row` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/reports/{project_id}/{year}/{report_type}/export-excel` | 导出单张报表为 Excel（只认项目成员） | `routers/reports.py:402` `export_report_excel` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/reports/{project_id}/{year}/{report_type}/rows/{row_code}/provenance` | 读取报表本期最终值来源；输入明细按当前请求人权限脱敏。 | `routers/reports.py:206` `get_report_row_provenance` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/reports/{project_id}/{year}/{report_type}/{row_code}/related-workpapers` | 返回与报表行关联的底稿列表。 | `routers/report_related_workpapers.py:22` `get_related_workpapers` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/staff/{staff_id}/check-in` |  | `routers/report_trace.py:160` `check_in` | get_current_user | 1 |
| GET | `/api/staff/{staff_id}/check-ins` |  | `routers/report_trace.py:176` `list_check_ins` | get_current_user | 1 |
| POST | `/api/temp-project` |  | `routers/report_trace.py:139` `create_temp_project` | get_current_user | 0 |
| GET | `/api/workpapers/{project_id}/{year}/bs-trend` |  | `routers/wp_report_analysis.py:67` `get_bs_trend` | get_current_user、require_project_access(readonly) | 6 |
| GET | `/api/workpapers/{project_id}/{year}/financial-ratios` |  | `routers/wp_report_analysis.py:89` `get_financial_ratios` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/workpapers/{project_id}/{year}/full-tb` |  | `routers/wp_report_analysis.py:31` `get_full_tb` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/workpapers/{project_id}/{year}/opening-reconcile` |  | `routers/wp_report_analysis.py:51` `get_opening_reconcile` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/workpapers/{project_id}/{year}/pl-trend` |  | `routers/wp_report_analysis.py:78` `get_pl_trend` | get_current_user、require_project_access(readonly) | 6 |
| GET | `/api/workpapers/{project_id}/{year}/tb-balance-check` |  | `routers/wp_report_analysis.py:41` `check_tb_balance` | get_current_user、require_project_access(readonly) | 7 |
| POST | `/api/workpapers/{wp_id}/d1-ecl/export-data` | D1-ECL导出含数据的xlsx（D1-15 hardcoded） | `routers/wp_render_strategies/_d1_import_export/_impl.py:3119` `d1_ecl_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1-ecl/export-template` | D1-ECL导出空白模板（D1-15 hardcoded） | `routers/wp_render_strategies/_d1_import_export/_impl.py:3100` `d1_ecl_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/export-data` | 导出含当前数据的xlsx | `routers/wp_render_strategies/_d1_import_export/_impl.py:2432` `d1_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/export-template` | 导出空白xlsx模板（含表头+格式+编制说明，无业务数据行） | `routers/wp_render_strategies/_d1_import_export/_impl.py:2405` `d1_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/export-xlsx` | 导出底稿 xlsx（致同模板填值还原）。 | `routers/wp_xlsx_export.py:41` `export_xlsx` | dedicated_wp_gate、get_current_user、get_current_user_stream | 19 |

## D12 附件、证据、函证与归档（130 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/attachments/paperless-health` | 检查 Paperless-ngx 服务是否可用 | `routers/attachments.py:243` `check_paperless_health` | get_current_user | 2 |
| GET | `/api/attachments/search` |  | `routers/attachments.py:224` `search_attachments` | get_current_user | 2 |
| DELETE | `/api/attachments/{attachment_id:uuid}` | 软删除附件（进回收站，不物理删除文件）。 | `routers/attachments.py:821` `delete_attachment` | get_current_user | 2 |
| GET | `/api/attachments/{attachment_id:uuid}` |  | `routers/attachments.py:267` `get_attachment` | get_current_user | 2 |
| POST | `/api/attachments/{attachment_id:uuid}/associate` |  | `routers/attachments.py:282` `associate_with_wp` | get_current_user | 1 |
| POST | `/api/attachments/{attachment_id:uuid}/classify` |  | `routers/attachments.py:514` `classify_document` | get_current_user | 0 |
| GET | `/api/attachments/{attachment_id:uuid}/download` |  | `routers/attachments.py:550` `download_attachment` | get_current_user_stream | 3 |
| POST | `/api/attachments/{attachment_id:uuid}/extract-confirmation` |  | `routers/attachments.py:531` `extract_confirmation_reply` | get_current_user | 0 |
| POST | `/api/attachments/{attachment_id:uuid}/ocr-confirm` | 核对后确认识别结果：base 与当前全文一致才写，否则 409 且库内不变。 | `routers/attachments.py:381` `confirm_ocr` | get_current_user | 1 |
| PUT | `/api/attachments/{attachment_id:uuid}/ocr-status` |  | `routers/attachments.py:402` `update_ocr_status` | get_current_user | 1 |
| GET | `/api/attachments/{attachment_id:uuid}/ocr-text` | 识别全文 + sha256 + 确认状态（确认弹窗打开时取；列表里的 ocr_text 只是 200 字预览）。 | `routers/attachments.py:369` `get_ocr_text` | get_current_user | 1 |
| GET | `/api/attachments/{attachment_id:uuid}/preview` |  | `routers/attachments.py:667` `preview_attachment` | get_current_user_stream | 1 |
| POST | `/api/attachments/{attachment_id:uuid}/retry-ocr` | 重新识别：状态重置为待识别并调度识别任务（与 ``POST ocr-fields`` 同一个后台识别）。 | `routers/attachments.py:787` `retry_ocr` | get_current_user | 1 |
| GET | `/api/attachments/{attachment_id:uuid}/versions` | 列出附件版本链（按 version 降序）。 | `routers/attachments.py:857` `list_attachment_versions` | get_current_user | 1 |
| POST | `/api/attachments/{attachment_id:uuid}/versions/{version_id}/rollback` | 回滚到 ``version_id``：追加一个新版本复制目标版本内容，旧版本保留。 | `routers/attachments.py:883` `rollback_attachment_version` | get_current_user | 1 |
| POST | `/api/attachments/{attachment_id}/link` | 将附件关联到具体位置（wp_cell / report_row / note_section）；要求附件所属项目 edi | `routers/attachment_lineage.py:67` `link_attachment` | get_current_user | 1 |
| DELETE | `/api/attachments/{attachment_id}/link/{link_id}` | 删除附件溯源关联；要求附件所属项目 edit。 | `routers/attachment_lineage.py:122` `unlink_attachment` | get_current_user | 1 |
| GET | `/api/attachments/{attachment_id}/links` | 查询附件的所有溯源关联；要求附件所属项目 readonly。 | `routers/attachment_lineage.py:103` `get_attachment_links` | get_current_user | 0 |
| POST | `/api/attachments/{attachment_id}/ocr-fields` | 获取或触发 OCR 字段提取。 | `routers/ocr_fields.py:31` `extract_ocr_fields` | get_current_user | 1 |
| GET | `/api/evidence-governance/metrics` | 返回治理低基数指标 + 近期告警聚合（design §9.3）。 | `routers/evidence_governance/__init__.py:152` `get_evidence_governance_metrics` | get_current_user | 1 |
| GET | `/api/ocr-jobs/{job_id}` | 查询异步 OCR 任务状态（前端轮询用）；要求任务所属附件的项目 readonly（结果里有识别出的字段）。 | `routers/ocr_fields.py:73` `get_ocr_job_status` | get_current_user | 1 |
| PUT | `/api/process-record/ai-content/{content_id}/confirm` | 确认/拒绝 AI 内容 | `routers/process_record.py:136` `confirm_ai_content` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/process-record/attachments/{attachment_id}/workpapers` | 获取附件出现的底稿（侧栏「关联底稿数」悬停时取）。 | `routers/process_record.py:82` `get_attachment_workpapers` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/process-record/projects/{project_id}/ai-content/pending` | 获取待确认的 AI 内容 | `routers/process_record.py:124` `get_pending_ai_content` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/process-record/projects/{project_id}/workpapers/{wp_id}/ai-check` | 检查底稿是否有未确认的 AI 内容（提交复核前检查） | `routers/process_record.py:154` `check_unconfirmed_ai` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/process-record/projects/{project_id}/workpapers/{wp_id}/attachments` | 获取底稿关联的附件 | `routers/process_record.py:70` `get_workpaper_attachments` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/process-record/projects/{project_id}/workpapers/{wp_id}/edit-history` | 获取底稿编辑历史 | `routers/process_record.py:37` `get_edit_history` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/process-record/projects/{project_id}/workpapers/{wp_id}/record-edit` | 记录底稿编辑 | `routers/process_record.py:50` `record_edit` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/projects/{pid}/sampling/cutoff-extract` | 按截止测试条件提取凭证 | `routers/cutoff_sampling.py:99` `cutoff_extract` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/cutoff-fill` | 记录填充日志（含 before_data 快照） | `routers/cutoff_sampling.py:205` `cutoff_fill` | get_current_user | 2 |
| GET | `/api/projects/{pid}/sampling/cutoff-history` | 获取指定底稿的提取历史列表（按时间倒序，仅截止测试类型） | `routers/cutoff_sampling.py:161` `cutoff_history` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/cutoff-undo` | 撤销指定提取记录，返回 before_data（仅截止测试类型范围内判定最新） | `routers/cutoff_sampling.py:182` `cutoff_undo` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/interim-survival` | 按 ADR-VK-11 四步顺序核对预审分录，并 upsert 当前账套版本的汇总。 | `routers/sampling_phase.py:128` `run_interim_survival` | get_current_user | 1 |
| GET | `/api/projects/{pid}/sampling/interim-survival/status` | 当前 active 账套与本底稿在该版本上的最近存续核对汇总（只读）。 | `routers/sampling_phase.py:111` `interim_survival_status` | get_current_user | 2 |
| PATCH | `/api/projects/{pid}/sampling/interim-survival/{check_id}` | 行元数据已持久化后，用剩余未确认数幂等刷新汇总；旧账套版本 409，避免污染当前概览。 | `routers/sampling_phase.py:156` `acknowledge_interim_survival` | get_current_user | 2 |
| GET | `/api/projects/{pid}/sampling/phase-context` | 年审抽凭口径弹窗的上下文。底稿须属于路径项目，调用人须是该项目成员（只读级即可）。 | `routers/sampling_phase.py:38` `phase_context` | get_current_user | 1 |
| GET | `/api/projects/{pid}/sampling/phase-evaluation` | 全年合并评价（任务 16，ADR-VK-10）：各分量、口径、科目范围是否一致；不可用时 available=false | `routers/sampling_phase.py:55` `phase_evaluation_view` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/voucher-compare` | 对比两次抽凭记录的差异 | `routers/voucher_sampling.py:775` `voucher_compare` | get_current_user | 1 |
| GET | `/api/projects/{pid}/sampling/voucher-coverage` | 项目级抽样登记概览（R5.6）。 | `routers/voucher_sampling.py:642` `voucher_coverage` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/voucher-evaluation` | 持久化抽样评价结果（CAS 1314 样本评价输出）到目标批次。 | `routers/voucher_sampling.py:512` `voucher_evaluation` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/voucher-extract` | 执行抽凭算法 | `routers/voucher_sampling.py:117` `voucher_extract` | get_current_user | 2 |
| GET | `/api/projects/{pid}/sampling/voucher-history` | 获取指定底稿的抽凭历史列表（按时间倒序） | `routers/voucher_sampling.py:570` `voucher_history` | get_current_user | 1 |
| POST | `/api/projects/{pid}/sampling/voucher-undo` | 撤销指定抽凭操作 | `routers/voucher_sampling.py:677` `voucher_undo` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/archive-completeness-report` | 获取归档前完整性自检报告。 | `routers/archive_completeness.py:35` `get_completeness_report` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/archive/jobs/{job_id}` | 查询归档作业状态。 | `routers/archive.py:84` `get_archive_job` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/archive/jobs/{job_id}/package` | 下载归档包：作业须已成功；文件不在或 sha256 与完整性记录不符 ⇒ 409。 | `routers/archive.py:116` `download_archive_package` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/archive/jobs/{job_id}/retry` | 重试失败的归档作业（从第一个未成功的步骤继续；与启动同级鉴权）。 | `routers/archive.py:95` `retry_archive_job` | get_current_user、require_confirmation_token、require_operatio | 1 |
| POST | `/api/projects/{project_id}/archive/orchestrate` | 启动归档编排（需二次密码确认）：gate → package → push_to_cloud? → lock → pur | `routers/archive.py:56` `orchestrate_archive` | get_current_user、require_confirmation_token、require_operatio | 1 |
| POST | `/api/projects/{project_id}/archived-exception/{action}` | 归档项目例外通道。 | `routers/archived_exception.py:101` `archived_exception_access` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/attachments` |  | `routers/attachments.py:193` `list_attachments` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/projects/{project_id}/attachments/upload` |  | `routers/attachments.py:113` `upload_attachment` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/confirmations` | 获取项目函证列表（含批量附件计数：outbound_count/inbound_count） | `routers/confirmations.py:82` `list_confirmations` | confirmation_project_gate、get_current_user | 7 |
| POST | `/api/projects/{project_id}/confirmations` | 创建函证 | `routers/confirmations.py:208` `create_confirmation` | confirmation_project_gate、get_current_user | 7 |
| POST | `/api/projects/{project_id}/confirmations/attachments/{attachment_id}/extract-compare` | OCR 识别回函件 + 与所属函证 book_amount 比对。 | `routers/confirmations.py:755` `extract_and_compare` | confirmation_project_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/confirmations/auto-match` | 批量/单件自动匹配回函件到函证记录。 | `routers/confirmations.py:845` `auto_match` | confirmation_project_gate、get_current_user | 3 |
| POST | `/api/projects/{project_id}/confirmations/batch-sync` | 批量同步函证（前端一次调用替代 N+1 逐行 create/update/transition）。 | `routers/confirmations.py:419` `batch_sync_confirmations` | confirmation_project_gate、get_current_user | 4 |
| GET | `/api/projects/{project_id}/confirmations/candidates` | 从底稿（辅助余额表）提取指定类型的候选函证对象，供「从底稿导入」批量创建。 | `routers/confirmations.py:112` `list_confirmation_candidates` | confirmation_project_gate、get_current_user | 3 |
| GET | `/api/projects/{project_id}/confirmations/match-queue` | 列出项目下待人工指派的回函件（人工匹配队列）。 | `routers/confirmations.py:144` `list_match_queue` | confirmation_project_gate、get_current_user | 3 |
| POST | `/api/projects/{project_id}/confirmations/match-queue/{attachment_id}/assign` | 人工把队列中的回函件指派到指定函证 + 绑发函件。 | `routers/confirmations.py:164` `assign_match` | confirmation_project_gate、get_current_user | 2 |
| DELETE | `/api/projects/{project_id}/confirmations/{confirmation_id}` | 删除函证 | `routers/confirmations.py:263` `delete_confirmation` | confirmation_project_gate、get_current_user | 6 |
| GET | `/api/projects/{project_id}/confirmations/{confirmation_id}` | 获取函证详情 | `routers/confirmations.py:224` `get_confirmation` | confirmation_project_gate、get_current_user | 6 |
| PUT | `/api/projects/{project_id}/confirmations/{confirmation_id}` | 更新函证 | `routers/confirmations.py:244` `update_confirmation` | confirmation_project_gate、get_current_user | 6 |
| POST | `/api/projects/{project_id}/confirmations/{confirmation_id}/apply-reply` | 人工确认后回填台账（写 confirmed_amount / reply_date / diff_amount / st | `routers/confirmations.py:792` `apply_reply` | confirmation_project_gate、get_current_user、require_role | 1 |
| GET | `/api/projects/{project_id}/confirmations/{confirmation_id}/attachments` | 列出某笔函证关联的全部附件（发函件 + 回函件，含角色/配对/OCR状态/文件信息）。 | `routers/confirmations.py:737` `list_attachments` | confirmation_project_gate、get_current_user | 2 |
| POST | `/api/projects/{project_id}/confirmations/{confirmation_id}/attachments` | 挂附件到函证记录。 | `routers/confirmations.py:661` `link_attachment` | confirmation_project_gate、get_current_user | 2 |
| POST | `/api/projects/{project_id}/confirmations/{confirmation_id}/attachments/upload` | 一次请求完成文件存储、函证挂载和留痕；失败补偿本次新写的物理对象。 | `routers/confirmations.py:576` `upload_and_link_attachment` | confirmation_project_gate、get_current_user | 1 |
| DELETE | `/api/projects/{project_id}/confirmations/{confirmation_id}/attachments/{link_id}` | 解绑附件（清 reference/删 link，不物理删附件，留痕）。 | `routers/confirmations.py:709` `unlink_attachment` | confirmation_project_gate、get_current_user | 3 |
| POST | `/api/projects/{project_id}/confirmations/{confirmation_id}/reverse` | 撤回函证状态（反向回退，支持一步退到底至待发函）。 | `routers/confirmations.py:337` `reverse_confirmation` | confirmation_project_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/confirmations/{confirmation_id}/transition` | 状态推进 | `routers/confirmations.py:280` `transition_confirmation` | confirmation_project_gate、get_current_user | 2 |
| POST | `/api/projects/{project_id}/document-recognize` | 已退役：返回 410。 | `routers/wp_document_recognize.py:31` `recognize_documents` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/document-recognize/types` | 已退役：返回 410。 | `routers/wp_document_recognize.py:37` `get_doc_types` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/sampling-configs` | 抽样配置列表 | `routers/sampling.py:115` `list_sampling_configs` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/sampling-configs` | 创建抽样配置 | `routers/sampling.py:126` `create_sampling_config` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/sampling-configs/calculate` | 计算样本量 | `routers/sampling.py:169` `calculate_sample_size` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/sampling-configs/{config_id}` | 更新抽样配置 | `routers/sampling.py:147` `update_sampling_config` | get_current_user | 3 |
| GET | `/api/projects/{project_id}/sampling-records` | 抽样记录列表 | `routers/sampling.py:191` `list_sampling_records` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/sampling-records` | 创建抽样记录 | `routers/sampling.py:207` `create_sampling_record` | get_current_user | 2 |
| PUT | `/api/projects/{project_id}/sampling-records/{record_id}` | 更新抽样记录 | `routers/sampling.py:228` `update_sampling_record` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/sampling-records/{record_id}/mus-evaluate` | MUS评价计算 | `routers/sampling.py:250` `mus_evaluate` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/sampling/aging-analysis` | 账龄分析 — FIFO 先进先出核销 | `routers/sampling_enhanced.py:79` `aging_analysis` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/sampling/cutoff-test` | 截止性测试 — 提取期末前后 N 天交易。 | `routers/sampling_enhanced.py:57` `cutoff_test` | get_current_user、require_project_access(readonly) | 4 |
| POST | `/api/projects/{project_id}/sampling/monthly-detail` | 月度明细填充 — 按月汇总序时账 | `routers/sampling_enhanced.py:96` `monthly_detail` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/unarchive` | 解除归档端点。 | `routers/archived_exception.py:149` `unarchive_project` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/evidence` | 获取底稿证据链接（附件已软删的不返回）。 | `routers/wp_evidence.py:134` `get_evidence_links` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/batch-link` | 批量链接：任一附件不在本底稿或字段不合法 ⇒ 整批不写。 | `routers/wp_evidence.py:223` `batch_link_evidence` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| PUT | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/contract-link` | 给本底稿既有附件的位置链接绑定或改绑合同身份；重复请求幂等。 | `routers/wp_evidence.py:275` `bind_contract_evidence_endpoint` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/contract-query` | 批量查询本项目可见底稿上的合同证据；目标底稿须属于路径项目。 | `routers/wp_evidence.py:259` `query_contract_evidence_endpoint` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/contract-reuse` | 把另一张可见底稿上同一合同的证据附件引用到本底稿（不复制文件；重复引用返回已有链接， | `routers/wp_evidence.py:305` `reuse_contract_evidence_endpoint` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/link` | 把本底稿已有附件链接到表页 / 单元格（附件不在本底稿 ⇒ 404，需求 3.2）。 | `routers/wp_evidence.py:188` `create_evidence_link` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/sufficiency` | 证据充分性检查 | `routers/wp_evidence.py:326` `check_evidence_sufficiency` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/upload` | 上传新证据：不带位置 ⇒ 整稿关联；带表页、单元格或凭证键/合同键 ⇒ 只写行级证据链接（需求 1.1）。 | `routers/wp_evidence.py:148` `upload_evidence` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/voucher-reuse` | 把另一张可见底稿上同一凭证的证据附件引用到本底稿（不复制文件；重复引用返回已有链接， | `routers/wp_evidence.py:241` `reuse_voucher_evidence_endpoint` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| DELETE | `/api/projects/{project_id}/workpapers/{wp_id}/evidence/{link_id}` | 删除证据链接（链接须属路径底稿；不删附件）。 | `routers/wp_evidence.py:206` `delete_evidence_link` | dedicated_wp_gate、get_current_user、require_project_access(ed | 2 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/archive/manifests` | 列出本 scope 的归档清单（只读）。 | `routers/archive_manifest_router.py:321` `list_manifests` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/archive/manifests` | 构建并封存归档清单（capability archive.seal；两阶段 watermark + P24 版本递增）。 | `routers/archive_manifest_router.py:146` `build_manifest` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/archive/manifests/{manifest_id}` | 清单详情（含 entries/edges；仅失败阻断时含 blocking_difference_report）。 | `routers/archive_manifest_router.py:371` `get_manifest` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/archive/preflight` | 归档前置门禁（冻结 UnifiedGraph + policy 证据 watermark；只读，不落库）。 | `routers/archive_manifest_router.py:116` `archive_preflight` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/archive/verify` | 离线校验封存包（R11；独立重算 member/manifest/package hash，不连业务库）。 | `routers/archive_manifest_router.py:457` `verify_package` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/attachments` | 治理安全上传（design §5.1）。 | `routers/evidence_governance/attachments_router.py:163` `upload_attachment` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/attachments/versions/{version_id}/content` | 按 AttachmentVersion id 安全读取（R1/R12/R15）。 | `routers/evidence_governance/attachments_router.py:317` `read_attachment_version_content` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/attachments/{attachment_id}/content` | 安全读取附件内容（design §5.1 read path）。 | `routers/evidence_governance/attachments_router.py:279` `read_attachment_content` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/attachments/{attachment_id}/impact` | 评估替换/删除某版本的直接与传递影响（R2.3 / R9.1；只读）。 | `routers/evidence_governance/attachments_router.py:481` `assess_attachment_impact` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/attachments/{attachment_id}/versions` | 替换附件内容 → 生成新版本 vN+1（R2/R9；capability attachment.replace）。 | `routers/evidence_governance/attachments_router.py:421` `replace_attachment_version` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/citations` | 列出本 scope 的引用快照（只读）。 | `routers/citation_router.py:86` `list_citations` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/citations` | 注册引用快照（R7.1；capability ``ai.generate``）。 | `routers/citation_router.py:145` `create_citation` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/citations/validate` | 批量校验引用集合（供 FormalOutput 门禁；只读）。 | `routers/citation_router.py:345` `validate_citations` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/citations/{citation_id}/locate` | 定位/打开引用 — 打开时重新鉴权（R7.3 / P15）。 | `routers/citation_router.py:305` `locate_citation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/commands/{command_root_id}` | 返回某 command-root 的脱敏状态 + transition 时间线。 | `routers/evidence_governance/__init__.py:77` `get_command_status` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/legal-holds` | 列出本 scope 的法定保全（只读）。 | `routers/legal_hold_router.py:166` `list_legal_holds` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/legal-holds` | 创建法定保全并固化统一图闭包（R13.1，capability legal_hold.create）。 | `routers/legal_hold_router.py:105` `create_legal_hold` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/legal-holds/purge-jobs` | 清理任务：强制 P27 四条件门禁（capability retention.purge）。 | `routers/legal_hold_router.py:357` `create_purge_job` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/legal-holds/{hold_id}/release` | 解除法定保全（R13.3，capability legal_hold.release，released_by 独立人工  | `routers/legal_hold_router.py:290` `release_legal_hold` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/legal-holds/{hold_id}/scope` | 列出保全固化的 direct/transitive 保护范围（只读，P26）。 | `routers/legal_hold_router.py:224` `get_hold_scope` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs` | 提交 OCR 任务（R5.1: 创建持久 OCR_Job）。 | `routers/ocr_governance_router.py:206` `submit_ocr_job` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}` | 获取 OCR 任务详情 + 当前状态。 | `routers/ocr_governance_router.py:272` `get_ocr_job` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/results/{result_id}` | 获取 OCR 结果详情（R6.1: 不可变 OCR_Result）。 | `routers/ocr_governance_router.py:437` `get_ocr_result` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/results/{result_id}/confirmations` | 列出 OCR 结果的所有确认记录（diff view）。 | `routers/ocr_governance_router.py:578` `list_confirmations` | get_current_user | 0 |
| PUT | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/results/{result_id}/confirmations` | 添加字段确认（R6.2: 人工确认 accepted/corrected/rejected）。 | `routers/ocr_governance_router.py:498` `add_confirmation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/results/{result_id}/mapping` | 预览写回映射（确认前查看哪些字段会写入目标）。 | `routers/ocr_governance_router.py:713` `preview_mapping` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/results/{result_id}/writeback` | 执行 OCR 写回（R6.4: 原子提交全部字段）。 | `routers/ocr_governance_router.py:625` `execute_writeback` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/retry` | 重试失败的 OCR 任务（R5.3: 需 ocr.retry 能力）。 | `routers/ocr_governance_router.py:310` `retry_ocr_job` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ocr/jobs/{job_id}/timeline` | 获取 OCR 任务的状态迁移时间线（R5.2: 保存每次状态迁移）。 | `routers/ocr_governance_router.py:372` `get_job_timeline` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/refs/impact` | 查询证据影响范围 — 直接 + 传递引用（R4.4）。 | `routers/evidence_ref_router.py:320` `query_impact` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/refs/references` | 双向查询 EvidenceRef（R4.3: 从源端与目标端查询相同引用）。 | `routers/evidence_ref_router.py:184` `list_evidence_refs` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/refs/references` | 创建 EvidenceRef（R3.1: 持久保存引用）。 | `routers/evidence_ref_router.py:373` `create_evidence_ref` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/refs/references/{ref_id}` | 获取单个 EvidenceRef 详情。 | `routers/evidence_ref_router.py:245` `get_evidence_ref` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/refs/references/{ref_id}/deactivate` | 停用 EvidenceRef（R3.4: 要求原因、保留历史、停止参与新 FormalOutput）。 | `routers/evidence_ref_router.py:472` `deactivate_evidence_ref` | get_current_user | 0 |
| GET | `/api/working-papers/{wp_id}/attachments` |  | `routers/attachments.py:309` `get_wp_attachments` | get_current_user | 3 |
| DELETE | `/api/working-papers/{wp_id}/attachments/{attachment_id}/link` | 解除附件↔底稿关联（权威链表 + matching reference）。 | `routers/attachments.py:321` `unlink_wp_attachment` | get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/confirmation-alternative/doc-ocr` | 识别替代程序行内的单据，返回该类单据的字段（待用户逐项确认后只填入本行空白列）。 | `routers/wp_render_strategies/_confirmation_alt_doc_ocr.py:180` `confirmation_alternative_doc_ocr` | dedicated_wp_gate、get_current_user | 1 |

## D13 复核、质控与签字门禁（186 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/attachments/{attachment_id:uuid}/preview-pdf` | Office 文件在线预览 — 转 PDF 流式返回。 | `routers/office_preview.py:111` `preview_office_as_pdf` | get_current_user | 1 |
| POST | `/api/consistency/replay` |  | `routers/consistency_replay.py:22` `replay_consistency` | get_current_user | 1 |
| GET | `/api/consistency/report/{project_id}` |  | `routers/consistency_replay.py:59` `get_consistency_report` | get_current_user | 2 |
| GET | `/api/eqcr/constants` | 返回 EQCR 模块使用的枚举常量，供前端下拉/校验使用。 | `routers/eqcr/constants.py:8` `get_eqcr_constants` | — | 0 |
| GET | `/api/eqcr/independence/annual/check` | 检查当前用户是否已提交本年度独立性声明（需求 12）。 | `routers/eqcr/independence.py:17` `check_annual_declaration` | get_current_user | 2 |
| GET | `/api/eqcr/independence/annual/questions` | 获取年度独立性声明问题集（需求 12）。 | `routers/eqcr/independence.py:33` `get_annual_questions` | get_current_user | 1 |
| POST | `/api/eqcr/independence/annual/submit` | 提交年度独立性声明（需求 12）。 | `routers/eqcr/independence.py:46` `submit_annual_declaration` | get_current_user | 1 |
| GET | `/api/eqcr/metrics` | EQCR 年度指标仪表盘（需求 10）。仅 admin / partner 可见。 | `routers/eqcr/metrics.py:17` `get_eqcr_metrics` | get_current_user | 1 |
| GET | `/api/eqcr/metrics/trends` | 返回近 5 年 EQCR 趋势数据。 | `routers/eqcr_trends.py:59` `get_eqcr_trends` | get_current_user | 0 |
| POST | `/api/eqcr/notes/{note_id}/share-to-team` | 分享单条笔记到项目组。 | `routers/eqcr/notes.py:142` `share_note_to_team` | get_current_user | 1 |
| POST | `/api/eqcr/opinions` | 新建一条 EQCR 判断域意见（对应需求 2.7）。 | `routers/eqcr/opinions.py:84` `create_eqcr_opinion` | get_current_user | 1 |
| PATCH | `/api/eqcr/opinions/{opinion_id}` | 更新一条 EQCR 意见。只有创建人（或 admin）可改。 | `routers/eqcr/opinions.py:107` `update_eqcr_opinion` | get_current_user | 2 |
| GET | `/api/eqcr/projects` | 返回本人作为 EQCR 的项目卡片列表（签字日升序）。 | `routers/eqcr/workbench.py:16` `list_my_eqcr_projects` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/approve` | EQCR 审批入口（需求 5）。 | `routers/eqcr/gate.py:20` `eqcr_approve` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/component-auditors` | EQCR 视角的组成部分审计师聚合（需求 11）。 | `routers/eqcr/prior_year.py:190` `get_eqcr_component_auditors` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/estimates` | 需求 2.3：会计估计 Tab 数据（底稿维度聚合）。 | `routers/eqcr/opinions.py:35` `get_eqcr_estimates` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/going-concern` | 需求 2.5：持续经营 Tab 数据（复用 GoingConcernEvaluation 模型）。 | `routers/eqcr/opinions.py:57` `get_eqcr_going_concern` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/link-prior-year` | 手动指定上年项目（兜底，当 client_name 匹配失败时使用）。 | `routers/eqcr/prior_year.py:139` `link_prior_year` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/materiality` | 需求 2.2：重要性 Tab 数据聚合 + 本域意见历史。 | `routers/eqcr/opinions.py:24` `get_eqcr_materiality` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/memo` | 生成 EQCR 备忘录（需求 9）。 | `routers/eqcr/memo.py:19` `generate_eqcr_memo` | get_current_user | 1 |
| PUT | `/api/eqcr/projects/{project_id}/memo` | 保存编辑后的 EQCR 备忘录。 | `routers/eqcr/memo.py:67` `save_eqcr_memo` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/memo/export` | 导出 EQCR 备忘录为 Word 文档 [R7-S3-04 Task 23]。 | `routers/eqcr/memo.py:109` `export_eqcr_memo` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/memo/finalize` | 定稿 EQCR 备忘录（需求 9）。 | `routers/eqcr/memo.py:86` `finalize_eqcr_memo` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/memo/preview` | 预览已保存的 EQCR 备忘录。 | `routers/eqcr/memo.py:38` `preview_eqcr_memo` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/memo/versions` | R10 Spec C / F8：列出 EQCR 备忘录历史版本（最多 5 版）。 | `routers/eqcr/memo.py:157` `list_eqcr_memo_versions` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/notes` | 列出本人在该项目的 EQCR 独立复核笔记。 | `routers/eqcr/notes.py:35` `list_eqcr_notes` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/notes` | 创建一条 EQCR 独立复核笔记。 | `routers/eqcr/notes.py:56` `create_eqcr_note` | get_current_user | 1 |
| DELETE | `/api/eqcr/projects/{project_id}/notes/{note_id}` | 软删除一条 EQCR 独立复核笔记。只有创建人可删。 | `routers/eqcr/notes.py:112` `delete_eqcr_note` | get_current_user | 1 |
| PATCH | `/api/eqcr/projects/{project_id}/notes/{note_id}` | 更新一条 EQCR 独立复核笔记。只有创建人可改。 | `routers/eqcr/notes.py:77` `update_eqcr_note` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/opinion-type` | 需求 2.6：审计意见类型 Tab 数据（AuditReport 视角 + 本域意见历史）。 | `routers/eqcr/opinions.py:68` `get_eqcr_opinion_type` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/overview` | 返回项目 EQCR 总览数据（用于 EqcrProjectView 详情页壳）。 | `routers/eqcr/workbench.py:26` `get_eqcr_project_overview` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/prior-year-comparison` | 获取历年 EQCR 意见对比（需求 7）。 | `routers/eqcr/prior_year.py:18` `get_prior_year_comparison` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/related-parties` | 需求 2.4：关联方 Tab 数据（注册表 + 交易明细）。 | `routers/eqcr/opinions.py:46` `get_eqcr_related_parties` | get_current_user | 6 |
| POST | `/api/eqcr/projects/{project_id}/related-parties` | 新建关联方注册记录（经理级可写）。 | `routers/eqcr/related_parties.py:100` `create_related_party` | get_current_user | 6 |
| DELETE | `/api/eqcr/projects/{project_id}/related-parties/{party_id}` | 软删除关联方注册记录（经理级可写）。 | `routers/eqcr/related_parties.py:172` `delete_related_party` | get_current_user | 1 |
| PATCH | `/api/eqcr/projects/{project_id}/related-parties/{party_id}` | 更新关联方注册记录（经理级可写）。 | `routers/eqcr/related_parties.py:129` `update_related_party` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/related-party-transactions` | 新建关联方交易记录（经理级可写）。 | `routers/eqcr/related_parties.py:204` `create_related_party_transaction` | get_current_user | 2 |
| DELETE | `/api/eqcr/projects/{project_id}/related-party-transactions/{txn_id}` | 软删除关联方交易记录（经理级可写）。 | `routers/eqcr/related_parties.py:302` `delete_related_party_transaction` | get_current_user | 1 |
| PATCH | `/api/eqcr/projects/{project_id}/related-party-transactions/{txn_id}` | 更新关联方交易记录（经理级可写）。 | `routers/eqcr/related_parties.py:246` `update_related_party_transaction` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/shadow-computations` | 返回该项目所有影子计算记录列表。 | `routers/eqcr/shadow_compute.py:66` `list_shadow_computations` | get_current_user | 1 |
| GET | `/api/eqcr/projects/{project_id}/time-summary` | 获取 EQCR 在该项目的工时汇总（需求 8）。 | `routers/eqcr/time_tracking.py:140` `eqcr_time_summary` | get_current_user | 1 |
| POST | `/api/eqcr/projects/{project_id}/time-track/start` | EQCR 开始复核计时（需求 8）。 | `routers/eqcr/time_tracking.py:21` `eqcr_time_track_start` | get_current_user | 0 |
| POST | `/api/eqcr/projects/{project_id}/time-track/stop` | EQCR 结束复核计时，生成正式工时记录（需求 8）。 | `routers/eqcr/time_tracking.py:81` `eqcr_time_track_stop` | get_current_user | 0 |
| POST | `/api/eqcr/projects/{project_id}/unlock-opinion` | EQCR 显式回退审计报告到 review 态（需求 6.4）。 | `routers/eqcr/gate.py:185` `eqcr_unlock_opinion` | get_current_user | 1 |
| POST | `/api/eqcr/shadow-compute` | EQCR 影子计算：独立跑一遍勾稽，不依赖项目组结果。 | `routers/eqcr/shadow_compute.py:21` `eqcr_shadow_compute` | get_current_user | 1 |
| POST | `/api/gate/evaluate` | 统一门禁评估入口 | `routers/gate.py:44` `evaluate_gate` | get_current_user | 1 |
| GET | `/api/gate/rules` | 查询当前生效的门禁规则配置 | `routers/gate.py:104` `list_gate_rules` | get_current_user | 0 |
| PUT | `/api/gate/rules/{rule_code}` | 修改租户级规则阈值（平台级不可修改） | `routers/gate.py:135` `update_gate_rule_config` | get_current_user | 1 |
| GET | `/api/independence/questions` | 返回独立性问题模板（20 条）。 | `routers/independence.py:54` `get_independence_questions` | get_current_user | 1 |
| GET | `/api/my/pending-independence` | 返回当前用户尚未提交独立性声明的项目列表。 | `routers/independence.py:153` `get_my_pending_independence` | get_current_user | 1 |
| GET | `/api/my/signing-tasks` | 获取当前用户待签署任务（要求登录，且只能查本人） | `routers/review_workflow.py:292` `get_my_signing_tasks` | get_current_user | 1 |
| GET | `/api/office-preview/health` | 检测 LibreOffice 是否可用（前端在加载时调用以决定是否展示 iframe）。 | `routers/office_preview.py:249` `office_preview_health` | get_current_user | 1 |
| POST | `/api/projects/{pid}/ai-batch-review` | 兼容入口：创建 DB-backed 底稿复核任务并立即返回 snapshot。 | `routers/review_prompt.py:527` `batch_review` | get_current_user | 1 |
| GET | `/api/projects/{pid}/batch-review-progress` | 兼容旧轮询：从 DB-backed job snapshot 投影进度。 | `routers/review_prompt.py:484` `get_batch_review_progress` | get_current_user | 1 |
| GET | `/api/projects/{pid}/procedure-row-tasks/{task_id}/conversation` | 只读复核视图（对话 + 消息 + 未解决问题单）。严格只读。 | `routers/procedure_review.py:69` `get_procedure_conversation` | get_current_user | 1 |
| POST | `/api/projects/{pid}/procedure-row-tasks/{task_id}/issues/{issue_id}/close` | 关闭程序行 review_comment IssueTicket（仅当前参与者可写）。 | `routers/procedure_review.py:123` `close_procedure_issue` | get_current_user | 1 |
| POST | `/api/projects/{pid}/procedure-row-tasks/{task_id}/messages` | 追加程序行复核消息（仅当前参与者可写；历史只读参与者 403）。 | `routers/procedure_review.py:104` `post_procedure_message` | get_current_user | 1 |
| GET | `/api/projects/{pid}/review-export` | 导出复核结果为 Excel — 从已持久化的数据库结果读取，不重跑 LLM（项目只读级；原先无任何鉴权） | `routers/review_prompt.py:556` `export_review_report` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/analytical-review/eps-roe` | 保存 EPS-ROE 参数并重新计算。返回计算结果。 | `routers/analytical_review_save.py:68` `save_eps_roe_endpoint` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/analytical-review/industry-comparison` | 保存同行业对比分析数据（可比公司 + 财务指标 + 对比数据 + 数据来源）。 | `routers/analytical_review_save.py:50` `save_industry_comparison_endpoint` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/audit-checks/export` | 导出审计检查结果为 xlsx（Req7，留痕）。 | `routers/audit_check.py:750` `export_audit_checks` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/audit-checks/recompute` | 主动触发审计检查重算（Req2）。 | `routers/audit_check.py:328` `recompute_audit_checks` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/audit-checks/signoff` | 读最近一次复核签认（Req8）。 | `routers/audit_check.py:676` `get_latest_audit_check_signoff` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/audit-checks/signoff` | 复核签认——把项目概览「审计检查」当作复核最后一次检查的签认留痕（Req8）。 | `routers/audit_check.py:616` `create_audit_check_signoff` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/audit-checks/summary` | 批量获取项目所有底稿的统一审计检查结果 + 新鲜度 + 项目汇总。 | `routers/audit_check.py:197` `get_audit_checks_summary` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/batch-review` | 批量复核（通过或退回）。 | `routers/batch_review.py:78` `batch_review` | get_current_user、require_project_access(review) | 2 |
| GET | `/api/projects/{project_id}/consistency-check` | 获取全链路一致性校验结果 | `routers/consistency.py:20` `get_consistency` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/consistency-check/run` | 手动触发全链路校验 | `routers/consistency.py:33` `run_consistency` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/eqcr-evaluation` | 查询 EQCR 评价列表 | `routers/wp_eqcr_evaluation.py:81` `list_eqcr_evaluations` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/eqcr-evaluation` | 创建 EQCR 充分性评价 | `routers/wp_eqcr_evaluation.py:46` `create_eqcr_evaluation` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/eqcr-issues` | 列出 EQCR 问题单（仅 EQCR + 项目团队可见）。 | `routers/eqcr_issues.py:88` `list_eqcr_issues` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/eqcr-issues` | 创建 EQCR 问题单（自动设置 source='eqcr'）。 | `routers/eqcr_issues.py:154` `create_eqcr_issue` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/eqcr-issues/{issue_id}/reply` | 回复 EQCR 问题单。 | `routers/eqcr_issues.py:205` `reply_eqcr_issue` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/eqcr-judgment` | 获取当前 EQCR 判断（只读）。 | `routers/eqcr_judgment.py:232` `get_judgment` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/eqcr-judgment` | 提交 EQCR 5 维度结构化判断。 | `routers/eqcr_judgment.py:124` `submit_judgment` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/eqcr/snapshot` | 获取当前 EQCR 快照 | `routers/eqcr_snapshot.py:49` `get_current_snapshot` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/eqcr/snapshot` | 创建 EQCR 快照 | `routers/eqcr_snapshot.py:24` `create_snapshot` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/eqcr/snapshot/refresh` | 刷新 EQCR 快照 | `routers/eqcr_snapshot.py:78` `refresh_snapshot` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/independence-declarations` | 列出项目的独立性声明。 | `routers/independence.py:68` `list_declarations` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/independence-declarations` | 创建一份 draft 状态的独立性声明。 | `routers/independence.py:85` `create_declaration` | get_current_user | 2 |
| PATCH | `/api/projects/{project_id}/independence-declarations/{declaration_id}` | 更新 draft 状态的声明（answers / attachments）。 | `routers/independence.py:103` `update_declaration` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/independence-declarations/{declaration_id}/submit` | 提交声明：draft → submitted，触发 SignatureRecord + 审计日志。 | `routers/independence.py:127` `submit_declaration` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/linkage/consistency-check` | 一致性校验：全量重算对比增量结果。 | `routers/linkage.py:89` `run_consistency_check` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/linkage/impact-preview` | 影响预判：输入科目编码，返回受影响的 TB 行/报表行/底稿。 | `routers/linkage.py:60` `get_impact_preview` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/my-reviews` | 返回当前用户负责底稿上的批注列表。 | `routers/my_reviews.py:31` `get_my_reviews` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/qc-dashboard/archive-readiness` | 归档前 readiness 门面（R1 Task 7）： | `routers/qc_dashboard.py:59` `check_archive_readiness` | get_current_user、require_project_access(review) | 1 |
| POST | `/api/projects/{project_id}/qc-dashboard/archive-readiness` | 重新执行归档前检查（同 GET 但语义为"立即重跑并生成新 gate_eval_id"） | `routers/qc_dashboard.py:72` `run_archive_readiness_check` | get_current_user、require_project_access(review) | 1 |
| GET | `/api/projects/{project_id}/qc-dashboard/open-issues` | 未解决的复核意见汇总 | `routers/qc_dashboard.py:48` `get_open_issues` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/qc-dashboard/overview` | QC 质量总览看板 | `routers/qc_dashboard.py:26` `get_qc_overview` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/qc-dashboard/staff-progress` | 按人员统计底稿进度 | `routers/qc_dashboard.py:37` `get_staff_progress` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/qc-report/export` | 导出 QC 报告 Word 文件（三线表格式） | `routers/qc_report_export.py:177` `export_qc_report` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/qc-summary` | 项目级QC汇总 | `routers/qc.py:77` `get_qc_summary` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/qc/vr-heatmap` | QC 风险热力图 — 按循环×severity 聚合 VR 检查结果 | `routers/qc_vr_heatmap.py:44` `get_vr_heatmap` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/review-config` | 获取项目复核链配置 | `routers/review_config.py:103` `get_review_config` | get_current_user、require_project_access(readonly) | 4 |
| PUT | `/api/projects/{project_id}/review-config` | 更新复核链配置 | `routers/review_config.py:130` `update_review_config` | get_current_user、require_project_access(edit) | 4 |
| GET | `/api/projects/{project_id}/review-recommend` | 推荐复核人（Top 3） | `routers/review_recommend.py:56` `recommend_reviewer` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/review-workflow/{year}/archive` | 导出 A21~A25 归档 Excel | `routers/review_workflow.py:97` `export_archive` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/review-workflow/{year}/completion-checklist` | A17-5 完成核对表 | `routers/review_workflow.py:85` `get_completion_checklist` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/review-workflow/{year}/export-blank` | 导出空白复核模板 Excel（供线下填写） | `routers/review_workflow.py:175` `export_blank_template` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/review-workflow/{year}/import` | 导入已填写的复核 Excel 回写系统 | `routers/review_workflow.py:158` `import_review_excel` | get_current_user、require_project_access(readonly)、require_pr | 0 |
| POST | `/api/projects/{project_id}/review-workflow/{year}/link-conversation` | 将复核对话关联到检查要点 | `routers/review_workflow.py:115` `link_conversation` | get_current_user、require_project_access(readonly)、require_pr | 1 |
| GET | `/api/projects/{project_id}/review-workflow/{year}/panel` | 获取复核面板数据（复核模板按项目自身的质控业务分类，不接受客户端 query 覆盖，R4） | `routers/review_workflow.py:51` `get_review_panel` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/review-workflow/{year}/progress` | 获取复核阶段进度 | `routers/review_workflow.py:147` `get_review_progress` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/review-workflow/{year}/save` | 保存复核记录 | `routers/review_workflow.py:68` `save_review` | get_current_user、require_project_access(readonly)、require_pr | 1 |
| POST | `/api/projects/{project_id}/review-workflow/{year}/unlink-conversation` | 取消关联 | `routers/review_workflow.py:131` `unlink_conversation` | get_current_user、require_project_access(readonly)、require_pr | 1 |
| POST | `/api/projects/{project_id}/signing/{year}/initiate` | 为项目成员创建签署任务 | `routers/review_workflow.py:244` `initiate_signing` | get_current_user、require_project_access(readonly)、require_pr | 2 |
| GET | `/api/projects/{project_id}/signing/{year}/progress` | 获取签署进度 | `routers/review_workflow.py:280` `get_signing_progress` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/signing/{year}/sign` | 成员电子签署（只要求是项目成员，由路由级 readonly 保证；且只能签本人） | `routers/review_workflow.py:262` `sign` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/standard/preview` | 准则切换影响预览（只读，需求 5.1/5.3）。 | `routers/standard_conversion.py:53` `preview_standard_conversion` | get_current_user、require_project_access(readonly) | 0 |
| PUT | `/api/projects/{project_id}/working-papers/{wp_id}/assign` | 分配编制人/复核人（需 review 权限） | `routers/wp_review_router.py:112` `assign_workpaper` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/qc-check` | 执行质量自检 | `routers/qc.py:30` `qc_check` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/qc-results` | 获取自检结果（最新一次） | `routers/qc.py:47` `get_qc_results` | dedicated_wp_gate、get_current_user | 1 |
| PUT | `/api/projects/{project_id}/working-papers/{wp_id}/review-status` | 更新底稿复核任务状态（需 review 权限） | `routers/wp_review_router.py:230` `update_review_status` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/submit-review` | 提交复核；单笔和批量入口共用同一服务与门禁。 | `routers/wp_review_router.py:193` `submit_review` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| GET | `/api/projects/{project_id}/workpapers/review-status` | 返回循环级复核状态统计。 | `routers/wp_review_status.py:26` `get_review_status` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/audit-checks/report` | 前端上报运行时勾稽真源（S6），按 `source` 命名空间 upsert 到该底稿的 | `routers/audit_check.py:490` `report_audit_checks` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/html` | 获取底稿 HTML 预览（只读，移动端使用） | `routers/workpaper_html_preview.py:103` `get_workpaper_html_preview` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/reviews/completion-block` | QC/EQCR/partner 完成是否被 re_review_required 阻断（R10.3；只读）。 | `routers/review_evidence_router.py:466` `completion_block` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}` | 复核状态 + 证据展示（版本/hash/OCR-AI 确认/stale/locator；R10.4）。 | `routers/review_evidence_router.py:501` `get_review_state` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/close` | 关闭复核（R10.2 / P21：权限 + 充分说明 + 至少一个非 stale ref；capability revi | `routers/review_evidence_router.py:246` `close_review` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/evidence` | 绑定证据到复核意见并冻结 raised 快照（R10.1）。 | `routers/review_evidence_router.py:140` `bind_evidence` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/reopen` | 依据失效后自动重开复核 → re_review_required（R10.3 / P22）。 | `routers/review_evidence_router.py:386` `reopen_review` | get_current_user | 0 |
| GET | `/api/qc/annual-reports` | 列出历史年报。 | `routers/qc_annual_reports.py:55` `list_annual_reports` | get_current_user、require_role | 1 |
| POST | `/api/qc/annual-reports` | 触发年度质量报告异步生成。 | `routers/qc_annual_reports.py:35` `create_annual_report` | get_current_user、require_role | 1 |
| GET | `/api/qc/annual-reports/{report_id}/download` | 下载年度质量报告文件。 | `routers/qc_annual_reports.py:70` `download_annual_report` | get_current_user、require_role | 1 |
| GET | `/api/qc/audit-log-compliance/findings` | 获取日志合规命中条目列表。 | `routers/qc_audit_log_compliance.py:94` `get_audit_log_findings` | get_current_user、require_role | 1 |
| PATCH | `/api/qc/audit-log-compliance/findings/{finding_id}/status` | 标记日志合规命中条目的审查状态。 | `routers/qc_audit_log_compliance.py:217` `update_finding_status` | get_current_user、require_role | 1 |
| POST | `/api/qc/audit-log-compliance/run` | 手动触发日志合规规则执行。 | `routers/qc_audit_log_compliance.py:120` `run_audit_log_compliance` | get_current_user、require_role | 1 |
| GET | `/api/qc/audit-log-compliance/summary` | 获取日志合规抽查摘要（用于报告生成）。 | `routers/qc_audit_log_compliance.py:246` `get_compliance_summary` | get_current_user、require_role | 1 |
| GET | `/api/qc/cases` | 列出案例库（所有登录用户可访问）。 | `routers/qc_cases.py:64` `list_cases` | get_current_user | 1 |
| POST | `/api/qc/cases` | 手动创建案例（仅 QC/admin）。 | `routers/qc_cases.py:97` `create_case` | get_current_user、require_role | 1 |
| GET | `/api/qc/cases/{case_id}` | 获取案例详情（所有登录用户可访问，同时增加阅读计数）。 | `routers/qc_cases.py:83` `get_case` | get_current_user | 2 |
| GET | `/api/qc/clients/{client_name}/quality-trend` | 获取客户近 N 年质量趋势。 | `routers/qc_ratings.py:158` `get_client_quality_trend` | get_current_user、require_role | 1 |
| GET | `/api/qc/inspections` | 列出质控抽查批次。 | `routers/qc_inspections.py:84` `list_inspections` | get_current_user、require_role | 1 |
| POST | `/api/qc/inspections` | 创建质控抽查批次，按策略生成抽查子项。 | `routers/qc_inspections.py:66` `create_inspection` | get_current_user、require_role | 1 |
| GET | `/api/qc/inspections/{inspection_id}` | 获取抽查批次详情（含子项）。 | `routers/qc_inspections.py:101` `get_inspection` | get_current_user、require_role | 2 |
| POST | `/api/qc/inspections/{inspection_id}/items/{item_id}/preview-case` | 预览脱敏后的案例内容（质控合伙人确认前）。 | `routers/qc_cases.py:113` `preview_case` | get_current_user、require_role | 0 |
| POST | `/api/qc/inspections/{inspection_id}/items/{item_id}/publish-as-case` | 确认发布案例（脱敏后入库）。 | `routers/qc_cases.py:131` `publish_as_case` | get_current_user、require_role | 1 |
| POST | `/api/qc/inspections/{inspection_id}/items/{item_id}/verdict` | QC 复核人录入结论（pass / fail / conditional_pass）。 | `routers/qc_inspections.py:111` `record_verdict` | get_current_user、require_role | 1 |
| GET | `/api/qc/inspections/{inspection_id}/report` | 生成质控抽查报告 Word 文件并返回下载流。 | `routers/qc_inspections.py:131` `generate_inspection_report` | get_current_user、require_role | 1 |
| GET | `/api/qc/projects/{project_id}/rating/{year}` | 获取项目评级 + 各维度得分 + 推导过程（透明性）。 | `routers/qc_ratings.py:58` `get_project_rating` | get_current_user、require_role | 1 |
| POST | `/api/qc/projects/{project_id}/rating/{year}/override` | 人工覆盖评级（必须附文字说明）。 | `routers/qc_ratings.py:78` `override_project_rating` | get_current_user、require_role | 0 |
| POST | `/api/qc/ratings/compute` | 手动触发全所评级计算（仅 admin）。 | `routers/qc_ratings.py:106` `compute_all_ratings` | get_current_user、require_role | 0 |
| GET | `/api/qc/reviewer-metrics` | 获取复核人深度指标。 | `routers/qc_ratings.py:130` `get_reviewer_metrics` | get_current_user、require_role | 1 |
| GET | `/api/qc/rotation/due-this-month` | 返回本月应抽查的项目列表 | `routers/qc_rotation_due.py:25` `get_due_this_month` | get_current_user | 1 |
| GET | `/api/qc/rules` | 列出 QC 规则定义，支持过滤与分页。 | `routers/qc_rules.py:82` `list_rules` | get_current_user、require_role | 1 |
| POST | `/api/qc/rules` | 创建新 QC 规则，version 初始为 1。 | `routers/qc_rules.py:104` `create_rule` | get_current_user、require_role | 1 |
| DELETE | `/api/qc/rules/{rule_id}` | 软删除 QC 规则。 | `routers/qc_rules.py:167` `delete_rule` | get_current_user、require_role | 2 |
| GET | `/api/qc/rules/{rule_id}` | 获取单条 QC 规则详情。 | `routers/qc_rules.py:129` `get_rule` | get_current_user、require_role | 2 |
| PATCH | `/api/qc/rules/{rule_id}` | 更新 QC 规则，每次更新 version+1。 | `routers/qc_rules.py:139` `update_rule` | get_current_user、require_role | 2 |
| POST | `/api/qc/rules/{rule_id}/dry-run` | 规则试运行 — 需求 2 | `routers/qc_rules.py:224` `dry_run_rule` | get_current_user、require_role | 1 |
| GET | `/api/qc/vr-coverage` | 返回各循环 VR 规则覆盖度统计 | `routers/vr_coverage.py:153` `get_vr_coverage` | get_current_user | 1 |
| GET | `/api/review-conversations` | 列出项目的复核对话 | `routers/review_conversations.py:44` `list_conversations` | get_current_user | 1 |
| POST | `/api/review-conversations` | 创建复核对话 | `routers/review_conversations.py:26` `create_conversation` | get_current_user | 1 |
| PUT | `/api/review-conversations/{conversation_id}/close` | 关闭对话（仅发起人可关闭） | `routers/review_conversations.py:95` `close_conversation` | get_current_user | 1 |
| POST | `/api/review-conversations/{conversation_id}/export` | 导出对话记录 | `routers/review_conversations.py:113` `export_conversation` | get_current_user | 1 |
| GET | `/api/review-conversations/{conversation_id}/messages` | 获取对话消息 | `routers/review_conversations.py:56` `get_messages` | get_current_user | 1 |
| POST | `/api/review-conversations/{conversation_id}/messages` | 发送消息（Phase 15: 关闭态消息写入阻断） | `routers/review_conversations.py:67` `send_message` | get_current_user | 1 |
| GET | `/api/review-dialog/recipients` | 返回当前底稿所属项目可选接收人列表。 | `routers/review_dialog.py:239` `list_review_recipients` | dedicated_wp_gate、get_current_user | 1 |
| PATCH | `/api/review-findings/{finding_id}/status` | 更新单条复核发现的状态 | `routers/review_prompt.py:434` `update_finding_status` | get_current_user | 1 |
| GET | `/api/review-prompts/coverage` | 获取提示词覆盖率统计（全局只读诊断，不含项目数据：须登录） | `routers/review_prompt.py:368` `get_review_prompt_coverage` | get_current_user | 0 |
| GET | `/api/review-prompts/metrics` | LLM 复核运行指标（仅管理员，不返回项目正文）。 | `routers/review_prompt.py:387` `get_review_metrics` | get_current_user、require_role | 0 |
| GET | `/api/review-records` | 全局复核记录列表（按项目+底稿编码过滤） | `routers/review_records_global.py:26` `list_review_records` | get_current_user | 1 |
| GET | `/api/review-templates` | 列出模板（支持搜索+循环过滤） | `routers/review_templates.py:131` `list_templates` | get_current_user | 1 |
| POST | `/api/review-templates` | 创建模板 | `routers/review_templates.py:175` `create_template` | get_current_user | 1 |
| DELETE | `/api/review-templates/{template_id}` | 软删除模板 | `routers/review_templates.py:272` `delete_template` | get_current_user | 0 |
| PUT | `/api/review-templates/{template_id}` | 更新模板 | `routers/review_templates.py:219` `update_template` | get_current_user | 0 |
| POST | `/api/review-templates/{template_id}/use` | 递增使用次数 | `routers/review_templates.py:304` `increment_use_count` | get_current_user | 1 |
| GET | `/api/review-threads` | 获取线程（含消息列表）。若不存在则自动创建。 | `routers/review_dialog.py:184` `get_or_create_thread` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/review-threads/active` | 返回某底稿的所有活跃线程列表（section_id + has_unread）。 | `routers/review_dialog.py:131` `list_active_threads` | dedicated_wp_gate、get_current_user | 10 |
| POST | `/api/review-threads/{thread_id}/messages` | 发送消息 + broadcast_raw SSE 推送。 | `routers/review_dialog.py:269` `create_message` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/rotation/check` | 检查指定人员对指定客户的连续审计年数。 | `routers/rotation.py:24` `check_rotation` | get_current_user | 1 |
| POST | `/api/rotation/overrides` | 创建轮换 override 申请。 | `routers/rotation.py:50` `create_rotation_override` | get_current_user | 1 |
| POST | `/api/signatures/sign` | 签署文档（需二次密码确认） | `routers/signatures.py:39` `sign_document` | get_current_user、require_confirmation_token、require_operatio | 2 |
| GET | `/api/signatures/{object_type}/{object_id}` | 获取签名记录 | `routers/signatures.py:68` `get_signatures` | get_current_user | 3 |
| POST | `/api/signatures/{signature_id}/revoke` | 撤销签名 | `routers/signatures.py:93` `revoke_signature` | get_current_user | 2 |
| POST | `/api/signatures/{signature_id}/verify` | 验证签名 | `routers/signatures.py:78` `verify_signature` | get_current_user | 2 |
| GET | `/api/working-papers/{wp_id}/reviews` | 获取复核意见列表 | `routers/wp_review.py:58` `list_reviews` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/working-papers/{wp_id}/reviews` | 添加复核意见 | `routers/wp_review.py:83` `add_comment` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/working-papers/{wp_id}/reviews/template-categories` | 获取模板分类列表 | `routers/wp_review.py:164` `get_template_categories` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/working-papers/{wp_id}/reviews/templates` | 获取复核意见模板列表 | `routers/wp_review.py:154` `get_review_templates` | dedicated_wp_gate、get_current_user | 1 |
| PUT | `/api/working-papers/{wp_id}/reviews/{review_id}/reply` | 回复复核意见 | `routers/wp_review.py:104` `reply_review` | dedicated_wp_gate、get_current_user | 1 |
| PUT | `/api/working-papers/{wp_id}/reviews/{review_id}/resolve` | 标记为已解决 | `routers/wp_review.py:128` `resolve_review` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/batch-assign-enhanced` | 增强批量委派：支持策略分配 + override 微调 + 通知 | `routers/batch_assign_enhanced.py:84` `batch_assign_enhanced` | get_current_user | 6 |
| POST | `/api/workpapers/{wp_id}/review` | 单底稿 AI 复核 | `routers/review_prompt.py:173` `review_workpaper` | get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/review-dialog/ai-generate` | AI 生成审计说明/结论文本。 | `routers/review_dialog.py:1124` `ai_generate_review_text` | dedicated_wp_gate、get_current_user | 4 |

## D14 AI 与知识库（191 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| POST | `/api/ai-chat/adopt` | 采纳 AI 生成内容 — server-authoritative + 幂等 + fail-closed（Task 7） | `routers/doc_ai_chat.py:765` `adopt_ai_content` | get_current_user | 3 |
| POST | `/api/ai-chat/attachments` | 上传会话附件 | `routers/doc_ai_chat.py:962` `upload_attachment` | get_current_user | 1 |
| DELETE | `/api/ai-chat/attachments/{attachment_id}` | 删除会话附件 | `routers/doc_ai_chat.py:1035` `delete_attachment` | get_current_user | 2 |
| GET | `/api/ai-chat/capabilities` | 查询当前 AI 引擎能力与服务健康 | `routers/doc_ai_chat.py:1325` `get_ai_capabilities` | get_current_user | 1 |
| POST | `/api/ai-chat/doc/{doc_type}/{doc_id}` | 文档级 AI 对话 — SSE streaming 响应 | `routers/doc_ai_chat.py:511` `doc_ai_chat` | get_current_user_stream | 3 |
| DELETE | `/api/ai-chat/doc/{doc_type}/{doc_id}/history` | 清除文档级对话历史（前端 clearHistory 调用，DB 持久化清除） | `routers/doc_ai_chat.py:732` `clear_chat_history` | get_current_user | 0 |
| GET | `/api/ai-chat/doc/{doc_type}/{doc_id}/history` | 获取文档级对话历史（DB 持久化，重启不丢） | `routers/doc_ai_chat.py:699` `get_chat_history` | get_current_user | 0 |
| POST | `/api/ai-chat/dsh-llm/v1/chat/completions` |  | `routers/dsh_model_forward.py:62` `forward_chat_completions` | — | 0 |
| GET | `/api/ai-chat/mcp/budget/{run_id}` | 查询 run 的 MCP 配额状态。 | `routers/ai_chat_mcp.py:468` `get_budget` | _extract_mcp_token、_validate_mcp_token | 0 |
| POST | `/api/ai-chat/mcp/tokens` | 创建 MCP scoped token（由 ChatRunCoordinator 在 run 启动时调用）。 | `routers/ai_chat_mcp.py:222` `create_mcp_token` | get_current_user | 0 |
| POST | `/api/ai-chat/mcp/tokens/child` | 为子 Agent 创建 child token（Property 29：只能收窄）。 | `routers/ai_chat_mcp.py:268` `create_child_token` | _extract_mcp_token、_validate_mcp_token | 0 |
| POST | `/api/ai-chat/mcp/tokens/revoke` | 撤销指定 token（cancel / run terminal 时调用）。 | `routers/ai_chat_mcp.py:296` `revoke_mcp_token` | get_current_user | 0 |
| GET | `/api/ai-chat/mcp/tools` | 列出可用的 MCP 工具。 | `routers/ai_chat_mcp.py:489` `list_available_tools` | _extract_mcp_token、_validate_mcp_token | 0 |
| POST | `/api/ai-chat/mcp/tools/call` | MCP 工具调用入口。 | `routers/ai_chat_mcp.py:311` `mcp_tool_call` | _extract_mcp_token、_validate_mcp_token | 0 |
| GET | `/api/ai-chat/mentionable` | Mention 聚合搜索 | `routers/doc_ai_chat.py:877` `search_mentionable` | get_current_user | 1 |
| GET | `/api/ai-chat/metrics` | AI Chat 结构化指标（prometheus text format） | `routers/doc_ai_chat.py:1252` `ai_chat_metrics` | get_current_user | 0 |
| POST | `/api/ai-chat/notes` | 项目笔记转存 | `routers/doc_ai_chat.py:1094` `save_ai_note` | get_current_user | 1 |
| GET | `/api/ai-chat/quota` | 获取 AI Chat 配额配置（服务端单一真源） | `routers/doc_ai_chat.py:1294` `get_quota_info` | get_current_user | 0 |
| GET | `/api/ai-chat/review-prompt` | 复核模式提示词预览 | `routers/doc_ai_chat.py:1178` `get_review_prompt_preview` | get_current_user | 1 |
| POST | `/api/ai-chat/runs` | 创建幂等 Chat Run | `routers/doc_ai_chat.py:176` `create_chat_run` | get_current_user | 1 |
| POST | `/api/ai-chat/runs/{run_id}/cancel` | 取消 Chat Run（幂等） | `routers/doc_ai_chat.py:426` `cancel_run` | get_current_user | 1 |
| GET | `/api/ai-chat/runs/{run_id}/events` | 订阅 Chat Run 事件（SSE，支持 Last-Event-ID 回放） | `routers/doc_ai_chat.py:322` `stream_run_events` | get_current_user_sse | 0 |
| POST | `/api/ai-content/{log_id}/confirm` | 确认 AI 内容（confirm_action=confirmed）。 | `routers/ai_content.py:472` `confirm_ai_content` | get_current_user | 3 |
| POST | `/api/ai-content/{log_id}/reject` | 拒绝 AI 内容（confirm_action=rejected）。需项目 review 级，不写入任何文档。 | `routers/ai_content.py:512` `reject_ai_content` | get_current_user | 3 |
| POST | `/api/ai-content/{log_id}/revise` | 修订 AI 内容（confirm_action=revised + 写 revised_content）。 | `routers/ai_content.py:493` `revise_ai_content` | get_current_user | 2 |
| POST | `/api/ai-content/{log_id}/undo` | 撤销本次 AI 写回；目标版本已变化时拒绝覆盖后续人工修改。 | `routers/ai_content.py:544` `undo_ai_content` | get_current_user | 1 |
| GET | `/api/ai-models` |  | `routers/ai_models.py:164` `list_models` | get_current_user、require_role | 1 |
| POST | `/api/ai-models` |  | `routers/ai_models.py:176` `create_model` | get_current_user、require_role | 1 |
| GET | `/api/ai-models/health` |  | `routers/ai_models.py:122` `ai_health` | get_current_user、require_role | 1 |
| GET | `/api/ai-models/providers` | provider registry 的前端投影。 | `routers/ai_models.py:113` `list_providers` | get_current_user、require_role | 1 |
| GET | `/api/ai-models/routes` | 各类「本机 → 服务器」路由的候选、状态与当前生效（ADR-ROUTE-010）。 | `routers/ai_models.py:554` `model_routes` | get_current_user、require_role | 1 |
| POST | `/api/ai-models/seed` |  | `routers/ai_models.py:130` `seed_models` | get_current_user、require_role | 1 |
| DELETE | `/api/ai-models/{model_id}` |  | `routers/ai_models.py:413` `delete_model` | get_current_user、require_role | 1 |
| PUT | `/api/ai-models/{model_id}` |  | `routers/ai_models.py:237` `update_model` | get_current_user、require_role | 1 |
| POST | `/api/ai-models/{model_id}/activate` | 启用模型参与路由：只替换同类型（OCR 同能力槽）同部署位置的那一条（ADR-ROUTE-002）。 | `routers/ai_models.py:479` `activate_model` | get_current_user、require_role | 1 |
| POST | `/api/ai-models/{model_id}/deactivate` | 停用：退出路由；该类型没有任何启用模型时回落 `.env` / 本机进程内 OCR。 | `routers/ai_models.py:535` `deactivate_model` | get_current_user、require_role | 1 |
| POST | `/api/ai-models/{model_id}/test` |  | `routers/ai_models.py:438` `test_model_connection` | get_current_user、require_role | 1 |
| GET | `/api/ai-plugins` | 插件列表 | `routers/ai_plugins.py:47` `list_plugins` | get_current_user、require_role | 1 |
| POST | `/api/ai-plugins` | 注册插件 | `routers/ai_plugins.py:77` `register_plugin` | get_current_user、require_role | 1 |
| GET | `/api/ai-plugins/presets` | 预设插件列表 | `routers/ai_plugins.py:56` `get_preset_plugins` | get_current_user、require_role | 0 |
| POST | `/api/ai-plugins/seed` | 加载预设插件（幂等） | `routers/ai_plugins.py:99` `load_preset_plugins` | get_current_user、require_role | 0 |
| GET | `/api/ai-plugins/{plugin_id}` | 插件详情 | `routers/ai_plugins.py:63` `get_plugin` | get_current_user、require_role | 0 |
| PUT | `/api/ai-plugins/{plugin_id}/config` | 更新插件配置 | `routers/ai_plugins.py:145` `update_config` | get_current_user、require_role | 0 |
| POST | `/api/ai-plugins/{plugin_id}/disable` | 禁用插件。 | `routers/ai_plugins.py:130` `disable_plugin` | get_current_user、require_role | 0 |
| POST | `/api/ai-plugins/{plugin_id}/enable` | 仅已实现的自定义插件可以启用；预设插件保持开发中。 | `routers/ai_plugins.py:111` `enable_plugin` | get_current_user、require_role | 0 |
| GET | `/api/ai/health` | 统一AI+OCR+缓存健康检查 | `routers/ai_unified.py:23` `unified_health_check` | — | 68 |
| GET | `/api/cache/stats` | 缓存统计 | `routers/ai_unified.py:44` `cache_stats` | — | 0 |
| DELETE | `/api/knowledge-library/documents/{doc_id}` | 删除文档（单个版本）。 | `routers/knowledge_folders.py:530` `delete_document` | get_current_user | 2 |
| PUT | `/api/knowledge-library/documents/{doc_id}` | 重命名文档（作用于整条版本链；spec knowledge-base-retrieval-and-authz-closu | `routers/knowledge_folders.py:688` `rename_document` | get_current_user | 2 |
| GET | `/api/knowledge-library/documents/{doc_id}/download` | 下载文档文件。不可读 → 404 同构。 | `routers/knowledge_folders.py:813` `download_document` | get_current_user | 1 |
| PUT | `/api/knowledge-library/documents/{doc_id}/move` | 移动文档到其他文件夹（整条版本链一起移动）。 | `routers/knowledge_folders.py:727` `move_document` | get_current_user | 1 |
| POST | `/api/knowledge-library/documents/{doc_id}/ocr-retry` | 扫描件重新识别：失败 / 没识别出文字 / 存量无正文的 PDF 与图片重新排队（与删除同一管理权限）。 | `routers/knowledge_folders.py:555` `retry_document_ocr` | get_current_user | 1 |
| GET | `/api/knowledge-library/documents/{doc_id}/preview` | 文档预览（返回文本内容或下载链接）。不可读 → 404 同构（旧实现任何登录用户可读任意文档）。 | `routers/knowledge_folders.py:780` `preview_document` | get_current_user | 1 |
| POST | `/api/knowledge-library/folders` | 创建文件夹（子文件夹须先通过父文件夹的知识资产写权限门） | `routers/knowledge_folders.py:282` `create_folder` | get_current_user | 1 |
| DELETE | `/api/knowledge-library/folders/{folder_id}` | 删除文件夹（含子文件夹和文档）。 | `routers/knowledge_folders.py:511` `delete_folder` | get_current_user | 2 |
| GET | `/api/knowledge-library/folders/{folder_id}/documents` | 列出文件夹下的文档（权限过滤；每行带 ``can_manage``，前端据此显示删除/改名/移动） | `routers/knowledge_folders.py:328` `list_documents` | get_current_user | 2 |
| POST | `/api/knowledge-library/folders/{folder_id}/documents` | 创建文档（文本内容；先过知识资产写权限门） | `routers/knowledge_folders.py:363` `create_document` | get_current_user | 2 |
| PUT | `/api/knowledge-library/folders/{folder_id}/rename` | 重命名文件夹（不可读 → 404；非创建者且非管理员 / readonly → 403） | `routers/knowledge_folders.py:669` `rename_folder` | get_current_user | 1 |
| POST | `/api/knowledge-library/folders/{folder_id}/upload` | 批量上传文档文件（先过知识资产写权限门） | `routers/knowledge_folders.py:426` `upload_documents` | get_current_user | 1 |
| POST | `/api/knowledge-library/init-presets` | 初始化预制分类文件夹（幂等；只读账号不可执行） | `routers/knowledge_folders.py:581` `init_preset_folders` | get_current_user | 1 |
| POST | `/api/knowledge-library/projects/{project_id}/evidence/from-document/{doc_id}` | 把当前可读的知识文档版本显式快照为项目证据。 | `routers/knowledge_folders.py:466` `promote_document_to_project_evidence` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/knowledge-library/projects/{project_id}/upload` | 上传到项目知识文件夹（``{项目名}（项目资料）/ {槽位名}``，项目组可见）。 | `routers/knowledge_folders.py:439` `upload_project_documents` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/knowledge-library/search` | 知识库页面全文搜索（文档名 / 正文 / 标签；browse 模式：当前用户可读即可见）。 | `routers/knowledge_folders.py:595` `search_documents` | get_current_user | 2 |
| GET | `/api/knowledge-library/tree` | 获取知识库完整文件夹树（权限过滤；每个节点带 ``can_manage`` / ``can_create``） | `routers/knowledge_folders.py:270` `get_folder_tree` | get_current_user | 2 |
| GET | `/api/knowledge/libraries` | 获取全局知识库分类列表（含文档计数） | `routers/knowledge_base.py:121` `list_libraries` | get_current_user | 1 |
| GET | `/api/knowledge/tsj` | 列出 TSJ 目录下所有可用的提示词文件名（供调试/索引使用）。 | `routers/knowledge_tsj.py:183` `list_tsj_prompts` | get_current_user | 0 |
| GET | `/api/knowledge/tsj/{cycle_name}` | 返回指定 cycle 的审计复核提示词 Markdown。 | `routers/knowledge_tsj.py:143` `get_tsj_prompt` | get_current_user | 2 |
| GET | `/api/knowledge/{category}/documents` | 列出全局知识库某分类下的文档（合并文件系统 + PG 数据源） | `routers/knowledge_base.py:132` `list_global_documents` | get_current_user | 1 |
| POST | `/api/knowledge/{category}/documents` | 上传文档到全局知识库（委托 KnowledgeFolderService + 触发索引流水线） | `routers/knowledge_base.py:192` `upload_global_document` | get_current_user | 1 |
| DELETE | `/api/knowledge/{category}/documents/{filename}` | 删除全局知识库文档 | `routers/knowledge_base.py:252` `delete_global_document` | get_current_user | 0 |
| GET | `/api/knowledge/{category}/documents/{filename}/download` | 下载全局知识库文档 | `routers/knowledge_base.py:271` `download_global_document` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/ai-assist/project-summary` | 项目复核人员：一页纸项目摘要（含 LLM 生成叙述） | `routers/role_ai_features.py:59` `project_summary` | get_current_user、require_project_access(review) | 0 |
| GET | `/api/projects/{project_id}/ai-assist/qc-trend` | 质控/复核人员：QC 问题趋势 | `routers/role_ai_features.py:48` `qc_trend` | get_current_user、require_project_access(review) | 0 |
| GET | `/api/projects/{project_id}/ai-assist/stale-reminders` | 审计员：超期底稿提醒 | `routers/role_ai_features.py:24` `stale_reminders` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/ai-assist/weekly-report` | 项目成员：项目周报自动生成（含 LLM 润色） | `routers/role_ai_features.py:37` `weekly_report` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/ai-content/pending` | 返回项目下未确认的 AI 内容清单 + 总数（前端 banner / badge 用）。 | `routers/ai_content.py:446` `list_pending_ai_content` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/ai-task-jobs` |  | `routers/ai_task_jobs.py:141` `create_job` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/ai-task-jobs/{job_id}` |  | `routers/ai_task_jobs.py:179` `get_job` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/ai-task-jobs/{job_id}/cancel` |  | `routers/ai_task_jobs.py:193` `cancel_job` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/ai-task-jobs/{job_id}/items/{item_id}/retry` |  | `routers/ai_task_jobs.py:215` `retry_job_item` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/b14/chapters/{chapter_id}/ai-generate` | 为 B1-4 尽调报告指定章节生成 AI 建议稿. | `routers/b14_ai_generate.py:78` `b14_ai_generate` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/consistency-gate/acknowledgements` | 列出项目 + 年度的全部确认记录 | `routers/gate_acknowledgements.py:61` `list_acknowledgements` | get_current_user、require_project_access(review) | 1 |
| POST | `/api/projects/{project_id}/consistency-gate/acknowledgements` | 新建确认 | `routers/gate_acknowledgements.py:72` `create_acknowledgement` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/consistency-gate/acknowledgements/{ack_id}/revoke` | 撤销确认 | `routers/gate_acknowledgements.py:124` `revoke_acknowledgement` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/knowledge/documents` | 列出项目级知识库文档 | `routers/knowledge_base.py:298` `list_project_documents` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/knowledge/documents` | 上传文档到项目级知识库 | `routers/knowledge_base.py:308` `upload_project_document` | get_current_user | 0 |
| DELETE | `/api/projects/{project_id}/knowledge/documents/{filename}` | 删除项目级知识库文档 | `routers/knowledge_base.py:334` `delete_project_document` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/knowledge/documents/{filename}/download` | 下载项目级知识库文档 | `routers/knowledge_base.py:349` `download_project_document` | get_current_user | 0 |
| PATCH | `/api/projects/{project_id}/workpapers/{wp_id}/ai-confirm` | 确认/拒绝/修订底稿中的 AI 生成内容。 | `routers/wp_ai_confirm.py:66` `confirm_ai_content` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/ai/interview-summary` | LLM 生成客户访谈摘要 | `routers/wp_ai_interview.py:40` `interview_summary` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/ai/stocktake-summary` | LLM 生成存货监盘差异分析摘要 | `routers/wp_ai_stocktake.py:112` `stocktake_summary` | dedicated_wp_gate、get_current_user | 3 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/formal-output/finalize` | FormalOutput 终态门禁（重跑校验 + watermark 比对；变更即失败重试）。 | `routers/ai_evidence_gate_router.py:526` `formal_output_finalize` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/formal-output/preflight` | FormalOutput 前置门禁（R8/R11；返回 watermark 供 finalize 比对）。 | `routers/ai_evidence_gate_router.py:501` `formal_output_preflight` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/generations` | 登记 AI 生成（R8.1，capability ai.generate）。默认落 draft 生命周期状态。 | `routers/ai_evidence_gate_router.py:129` `register_generation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}` | 查询 AI 内容治理记录（只读）。 | `routers/ai_evidence_gate_router.py:197` `get_generation` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/confirm` | 人工确认 AI 内容 draft→confirmed（capability ai.confirm；Service Ide | `routers/ai_evidence_gate_router.py:246` `confirm_generation` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/eligibility` | 检查 AI 内容能否进入 FormalOutput（R8.3 / P17；只读）。 | `routers/ai_evidence_gate_router.py:435` `check_eligibility` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/reject` | 人工拒绝 AI 内容 draft→rejected（capability ai.confirm）。 | `routers/ai_evidence_gate_router.py:371` `reject_generation` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/revise` | 人工修订 AI 内容（创建新版本，原记录标 revised；capability ai.confirm）。 | `routers/ai_evidence_gate_router.py:306` `revise_generation` | get_current_user | 0 |
| POST | `/api/workpapers/projects/{project_id}/ai/generate-ledger-analysis` | 台账分析底稿生成（读项目序时账：要求项目成员）。 | `routers/wp_chat.py:46` `generate_ledger_analysis` | dedicated_wp_gate、get_current_user、require_project_access(re | 20 |
| POST | `/api/workpapers/{wp_id}/a171/ai-generate` | A17-1 章节 AI 生成 | `routers/a171_ai_generate.py:50` `a171_ai_generate` | dedicated_wp_gate、get_current_user | 13 |
| POST | `/api/workpapers/{wp_id}/a171/generate-docx` | 结构化→Word：从 checklist_responses 生成 docx 文件，返回 onlyoffice-conf | `routers/a171_ai_generate.py:264` `a171_generate_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/a171/sync-from-docx` | Word→结构化：从项目存储的 docx 解析内容回写到 checklist_responses | `routers/a171_ai_generate.py:293` `a171_sync_from_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/a177/ai-generate` | A17-7 章节 AI 生成 | `routers/a177_ai_generate.py:51` `a177_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/a177/generate-docx` | 结构化→Word：从 checklist_responses 生成 docx | `routers/a177_ai_generate.py:125` `a177_generate_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/a177/sync-from-docx` | Word→结构化：从 docx 解析回写 checklist_responses | `routers/a177_ai_generate.py:153` `a177_sync_from_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/ai-chat` | 底稿级 AI 对话 — SSE streaming 响应 | `routers/wp_guidance_chat.py:407` `workpaper_ai_chat` | dedicated_wp_gate、get_current_user | 19 |
| DELETE | `/api/workpapers/{wp_id}/ai-chat/history` | 清除底稿 AI 对话历史 | `routers/wp_guidance_chat.py:564` `clear_wp_chat_history` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/ai-chat/history` | 获取底稿 AI 对话历史 | `routers/wp_guidance_chat.py:541` `get_wp_chat_history` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai-generate-notes` | 根据函证统计数据，调用 LLM 生成审计说明初稿 | `routers/wp_guidance_chat.py:632` `generate_confirmation_notes` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/ai/analytical-review` |  | `routers/wp_ai.py:104` `analytical_review` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/audit-conclusion` | E1 spec F6.3 场景 1：审计说明生成 | `routers/wp_ai.py:186` `ai_audit_conclusion` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/chat` | 底稿 LLM SSE：请求期准备/鉴权，响应期只流 LLM，不持有数据库连接。 | `routers/wp_chat.py:30` `wp_chat` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/ai/check-conclusion` | E1 spec F6.3 场景 3：检查清单结论 | `routers/wp_ai.py:259` `ai_check_conclusion` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/check-consistency` |  | `routers/wp_ai.py:148` `check_consistency` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/cutoff-conclusion` | E1 spec F6.3 场景 4：截止测试结论 | `routers/wp_ai.py:298` `ai_cutoff_conclusion` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/extract-confirmations` |  | `routers/wp_ai.py:129` `extract_confirmations` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/ai/generate-text` | 通用底稿级 AI 文本生成 — 单次调用返回生成内容 | `routers/wp_guidance_chat.py:333` `workpaper_ai_generate_text` | dedicated_wp_gate、get_current_user | 181 |
| POST | `/api/workpapers/{wp_id}/ai/review-questions` | Task 2.22: 合伙人打开复核模板时一键生成"建议关注问题清单"。 | `routers/wp_ai.py:350` `ai_review_questions` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/ai/review-reply` | Task 2.23: 审计助理收到问题后 LLM 基于底稿+序时账草拟回复。 | `routers/wp_ai.py:403` `ai_review_reply` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/ai/suggest` | US-5: LLM 辅助填写 — 返回 AI 建议文本（≤2000 字符） | `routers/wp_ai.py:44` `suggest_fill` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/ai/tsj-review` | TSJ 提示词驱动 LLM 复核（已迁移至底稿级 ReviewPrompt 链路） | `routers/wp_ai.py:498` `tsj_review` | dedicated_wp_gate、get_current_user、require_wp_edit_permissio | 1 |
| POST | `/api/workpapers/{wp_id}/ai/variance-analysis` | E1 spec F6.3 场景 2：差异原因分析（同时用于 WorkpaperAuditNav 关键风险提示） | `routers/wp_ai.py:224` `ai_variance_analysis` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d1/ai-generate` |  | `routers/wp_render_strategies/_d1_ai_generate.py:152` `d1_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d2/ai-generate` | D2 应收账款 AI 辅助生成 | `routers/wp_render_strategies/_d2_ai_generate.py:116` `d2_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d3/ai-generate` | D3 预收账款 AI 辅助生成 | `routers/wp_render_strategies/_d3_ai_generate.py:102` `d3_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d4/ai-generate` | D4 营业收入 AI 辅助生成 | `routers/wp_render_strategies/_d4_ai_generate.py:140` `d4_ai_generate` | dedicated_wp_gate、get_current_user | 35 |
| POST | `/api/workpapers/{wp_id}/d5/ai-generate` | D5 应收款项融资 AI 辅助生成 | `routers/wp_render_strategies/_d5_ai_generate.py:110` `d5_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d6/ai-generate` | D6 合同资产 AI 辅助生成 | `routers/wp_render_strategies/_d6_ai_generate.py:104` `d6_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d7/ai-generate` | D7 合同负债 AI 辅助生成 | `routers/wp_render_strategies/_d7_ai_generate.py:94` `d7_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f1/ai-generate` | F1 预付账款 AI 辅助生成 | `routers/wp_render_strategies/_f1_ai_generate.py:172` `f1_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-spe/ai-generate` |  | `routers/wp_render_strategies/_f2_special_ai.py:356` `f2_spe_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-st/ai-generate` |  | `routers/wp_render_strategies/_f2_stocktake_ai.py:106` `f2_stocktake_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-val/ai-generate` |  | `routers/wp_render_strategies/_f2_valuation_ai.py:213` `f2_val_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2/ai-generate` |  | `routers/wp_render_strategies/_f2_inventory_main_ai.py:273` `f2_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f3/ai-generate` |  | `routers/wp_render_strategies/_f3_notes_payable_ai.py:178` `f3_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f4/ai-generate` |  | `routers/wp_render_strategies/_f4_accounts_payable_ai.py:268` `f4_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f5/ai-generate` |  | `routers/wp_render_strategies/_f5_cost_of_sales_ai.py:161` `f5_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g0/ai-generate` |  | `routers/wp_render_strategies/_g0_confirmation_ai.py:141` `g0_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g1/ai/{section}` |  | `routers/wp_render_strategies/_g1_trading_financial_assets_ai.py:92` `g1_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g10/ai/{section}` |  | `routers/wp_render_strategies/_g10_trading_financial_liabilities_ai.py:68` `generate_g10_ai` | dedicated_wp_gate、get_current_user | 8 |
| POST | `/api/workpapers/{wp_id}/g11/ai/{section}` |  | `routers/wp_render_strategies/_g11_investment_income_ai.py:57` `generate_g11_ai` | dedicated_wp_gate、get_current_user | 5 |
| POST | `/api/workpapers/{wp_id}/g2/ai/{section}` |  | `routers/wp_render_strategies/_g2_interest_receivable_ai.py:132` `g2_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g3/ai/{section}` |  | `routers/wp_render_strategies/_g3_dividend_receivable_ai.py:107` `g3_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g4-ecl/ai/{section}` |  | `routers/wp_render_strategies/_g4_bond_investment_ecl_ai.py:114` `g4_ecl_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g4-main/ai/{section}` |  | `routers/wp_render_strategies/_g4_bond_investment_main_ai.py:109` `g4_main_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g4-sppi/ai/{section}` |  | `routers/wp_render_strategies/_g4_bond_investment_sppi_ai.py:104` `g4_sppi_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g6-ecl/ai/{section}` |  | `routers/wp_render_strategies/_g6_other_bond_investment_ecl_ai.py:126` `g6_ecl_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g6-main/ai/{section}` |  | `routers/wp_render_strategies/_g6_other_bond_investment_main_ai.py:129` `g6_main_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g6-sppi/ai/{section}` |  | `routers/wp_render_strategies/_g6_other_bond_investment_sppi_ai.py:166` `g6_sppi_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g7-equity-method/ai/{section}` |  | `routers/wp_render_strategies/_g7_long_term_equity_method_ai.py:153` `g7_equity_method_ai_generate` | dedicated_wp_gate、get_current_user | 7 |
| POST | `/api/workpapers/{wp_id}/g7-main/ai/{section}` |  | `routers/wp_render_strategies/_g7_long_term_equity_main_ai.py:111` `g7_main_ai_generate` | dedicated_wp_gate、get_current_user | 3 |
| POST | `/api/workpapers/{wp_id}/g7-sub/ai/{section}` |  | `routers/wp_render_strategies/_g7_long_term_equity_subsidiary_ai.py:156` `g7_subsidiary_ai_generate` | dedicated_wp_gate、get_current_user | 8 |
| POST | `/api/workpapers/{wp_id}/g8/ai/{section}` |  | `routers/wp_render_strategies/_g8_other_equity_instruments_ai.py:109` `generate_g8_ai` | dedicated_wp_gate、get_current_user | 6 |
| POST | `/api/workpapers/{wp_id}/g9/ai/{section}` |  | `routers/wp_render_strategies/_g9_other_noncurrent_financial_ai.py:65` `generate_g9_ai` | dedicated_wp_gate、get_current_user | 6 |
| GET | `/api/workpapers/{wp_id}/guidance` | 获取版本化、render-membership 约束的编制说明。 | `routers/wp_guidance_chat.py:77` `get_workpaper_guidance` | dedicated_wp_gate、get_current_user | 19 |
| PUT | `/api/workpapers/{wp_id}/guidance/custom` | 保存项目级自定义编制说明（P4 预留端点） | `routers/wp_guidance_chat.py:291` `save_custom_guidance` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h0/ai-generate` |  | `routers/wp_render_strategies/_h0_confirmation_ai.py:119` `h0_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h1/ai-generate` |  | `routers/wp_render_strategies/_h1_ai_generate.py:189` `h1_ai_generate` | dedicated_wp_gate、get_current_user | 7 |
| POST | `/api/workpapers/{wp_id}/h10/ai/{section}` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_ai.py:51` `generate_h10_ai` | dedicated_wp_gate、get_current_user | 3 |
| POST | `/api/workpapers/{wp_id}/h2/ai-generate` |  | `routers/wp_render_strategies/_h2_ai_generate.py:139` `h2_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/h3/ai-generate` |  | `routers/wp_render_strategies/_h3_ai_generate.py:106` `h3_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i1/ai-generate` |  | `routers/wp_render_strategies/_i1_ai_generate.py:114` `i1_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i2/ai-generate` |  | `routers/wp_render_strategies/_i2_ai_generate.py:108` `i2_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i3/ai-generate` |  | `routers/wp_render_strategies/_i3_ai_generate.py:132` `i3_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i4/ai-generate` |  | `routers/wp_render_strategies/_i4_ai_generate.py:108` `i4_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i5/ai-generate` |  | `routers/wp_render_strategies/_i5_ai_generate.py:152` `i5_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i6/ai-generate` |  | `routers/wp_render_strategies/_i6_ai_generate.py:127` `i6_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/j1/ai-generate` | AI生成J1各section的分析文本. | `routers/wp_render_strategies/_j1_ai_generate.py:73` `ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/j2/ai/generate` | AI辅助生成精算分析内容（与同族 J1 一致：须登录；模型走平台本机优先路由）。 | `routers/wp_render_strategies/_j2_ai_generate.py:61` `ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/j3-ai/bs-analysis` | AI分析BS参数合理性. | `routers/wp_render_strategies/_j3_ai_generate.py:35` `analyze_bs_params` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/j3-ai/check-assist` | AI辅助检查表各section结论生成. | `routers/wp_render_strategies/_j3_ai_generate.py:90` `check_section_assist` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k0/ai/{section}` |  | `routers/wp_render_strategies/_k0_confirmation_ai.py:124` `k0_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/k1/ai-generate` |  | `routers/wp_render_strategies/_k1_ai_generate.py:135` `k1_ai_generate` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/k10/ai-generate` |  | `routers/wp_render_strategies/_k10_ai_generate.py:131` `k10_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k11/ai-generate` |  | `routers/wp_render_strategies/_k11_ai_generate.py:96` `k11_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k12/ai-generate` |  | `routers/wp_render_strategies/_k12_ai_generate.py:112` `k12_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k13/ai-generate` |  | `routers/wp_render_strategies/_k13_ai_generate.py:121` `k13_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k2/ai-generate` |  | `routers/wp_render_strategies/_k2_ai_generate.py:81` `k2_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k3/ai-generate` |  | `routers/wp_render_strategies/_k3_ai_generate.py:96` `k3_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k4/ai-generate` |  | `routers/wp_render_strategies/_k4_ai_generate.py:91` `k4_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k5/ai-generate` |  | `routers/wp_render_strategies/_k5_ai_generate.py:123` `k5_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k6/ai-generate` |  | `routers/wp_render_strategies/_k6_ai_generate.py:122` `k6_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k7/ai-generate` |  | `routers/wp_render_strategies/_k7_ai_generate.py:104` `k7_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k8/ai-generate` |  | `routers/wp_render_strategies/_k8_ai_generate.py:116` `k8_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k9/ai-generate` |  | `routers/wp_render_strategies/_k9_ai_generate.py:118` `k9_ai_generate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l0/ai/{section}` |  | `routers/wp_render_strategies/_l0_confirmation_ai.py:67` `l0_ai_generate` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/workpapers/{wp_id}/g12/ai/{section}` |  | `routers/wp_render_strategies/_g12_net_hedge_gains_ai.py:58` `generate_g12_ai` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/workpapers/{wp_id}/g13/ai/{section}` |  | `routers/wp_render_strategies/_g13_fair_value_changes_ai.py:50` `generate_g13_ai` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/workpapers/{wp_id}/g14/ai/{section}` |  | `routers/wp_render_strategies/_g14_credit_impairment_loss_ai.py:50` `generate_g14_ai` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/workpapers/{wp_id}/g5/ai/{section}` |  | `routers/wp_render_strategies/_g5_long_term_receivable_ai.py:88` `generate_g5_ai` | dedicated_wp_gate、get_current_user | 0 |

## D09 底稿（804 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/a17/a176/agenda-prefill` | 为 A17-6 总结会议程提供自动预填建议 | `routers/a17_summary.py:240` `a176_agenda_prefill` | get_current_user | 1 |
| GET | `/api/a17/a176/agenda-stale-check` | A17-6 议程相对上游是否过期 | `routers/a17_summary.py:262` `agenda_stale_check` | get_current_user | 2 |
| GET | `/api/a17/applicable-versions` | 返回项目适用的 A17-5 核对表版本列表。 | `routers/a17_summary.py:133` `list_applicable_versions` | get_current_user | 1 |
| GET | `/api/a17/chapter-definitions` | 返回 A17-1 全部章节定义（16 章） | `routers/a17_summary.py:61` `list_chapter_definitions` | get_current_user | 1 |
| GET | `/api/a17/chapters/stale-check` | A17-1 各章相对上游底稿是否过期 | `routers/a17_summary.py:251` `chapters_stale_check` | get_current_user | 2 |
| POST | `/api/a17/chapters/{chapter_id}/ai-generate` | 为指定章节生成 AI 建议稿（A17-plus） | `routers/a17_summary.py:643` `ai_generate_chapter` | get_current_user | 1 |
| POST | `/api/a17/chapters/{chapter_id}/pull` | 拉取指定章节的上游数据 | `routers/a17_summary.py:161` `pull_chapter` | get_current_user | 2 |
| GET | `/api/a17/check-completeness` | 检查 A17-1 所有必填章节是否完整可导出 | `routers/a17_summary.py:575` `check_completeness` | get_current_user | 0 |
| POST | `/api/a17/consistency-check` | 跨章节一致性校验：检查 A17-1 各章节结论之间的逻辑一致性。 | `routers/a17_summary.py:369` `consistency_check` | get_current_user | 3 |
| GET | `/api/a17/cross-alerts` | A13 超重要性 / A10-1 未沟通 联动告警 | `routers/a17_summary.py:293` `a17_cross_alerts` | get_current_user | 1 |
| GET | `/api/a17/export-word` | 导出 A17-1 为 Word 文档 | `routers/a17_summary.py:586` `export_word_endpoint` | get_current_user | 0 |
| GET | `/api/a17/independence-drift` | 检测 A17-7 与 B3 独立性期间字段是否一致 | `routers/a17_summary.py:226` `independence_drift_check` | get_current_user | 1 |
| POST | `/api/a17/independence/import-b3-periods` | 从 B3 导入独立性期间字段到 A17-7 | `routers/a17_summary.py:319` `independence_import_b3_periods` | get_current_user | 1 |
| POST | `/api/a17/kam/push-to-report` | 将 A17-2-1 KAM 数据推送至审计报告 KAM 段落（单向覆写） | `routers/a17_summary.py:188` `push_kam_to_report_endpoint` | get_current_user | 1 |
| GET | `/api/a17/kam/stale-check` | 检测 A17-2-1 KAM 与审计报告 KAM 段落是否同步 | `routers/a17_summary.py:208` `kam_stale_check` | get_current_user | 1 |
| POST | `/api/a17/kam/{item_id}/ai-generate` | 为 KAM 条目生成三要素描述建议稿（A17-plus） | `routers/a17_summary.py:704` `ai_generate_kam` | get_current_user | 1 |
| GET | `/api/a17/partner-summary` | 合伙人/EQCR 一页摘要 | `routers/a17_summary.py:283` `partner_summary` | get_current_user | 1 |
| GET | `/api/a17/report-date-timeline` | 总结会 / 独立性签署 / 审计报告日时间轴 | `routers/a17_summary.py:273` `report_date_timeline` | get_current_user | 1 |
| GET | `/api/a17/review-sign-hints` | A17-5 核对项 preset A22/A23/A24/A25 → 读 A21~A25 子码 -sign 状态。 | `routers/a17_summary.py:146` `list_review_sign_hints` | get_current_user | 1 |
| GET | `/api/a17/signoff-self-check` | 归档/签发前自检（含跨底稿联动） | `routers/a17_summary.py:303` `a17_signoff_self_check` | get_current_user | 1 |
| GET | `/api/a17/sub-documents` | 查询项目 wp_index 中 A17-2-1 ~ A17-7 的存在状态。 | `routers/a17_summary.py:76` `list_sub_documents` | get_current_user | 1 |
| GET | `/api/b50/scope-accounts` | 返回试算表重要科目（报表项目级聚合）+ 建议业务循环。 | `routers/b50_scope.py:28` `get_scope_accounts` | get_current_user | 1 |
| GET | `/api/b60/b50-risk-rows` | 从 B50 风险评估读取结构化风险行（单一真源 checklist_responses）。 | `routers/b60_data_pull.py:89` `get_b50_risk_rows` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/b60/chapter-definitions` | 加载静态章节定义 JSON. | `routers/b60_chapters.py:36` `get_chapter_definitions` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/b60/chapters/{chapter_id}/pull` | 从关联底稿提取数据填入章节。 | `routers/b60_data_pull.py:124` `pull_chapter_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/custom-template-ingestion/actions` | 返回三条 action 的稳定 id 与语义（Requirement 1.4）。 | `routers/custom_template_ingestion.py:81` `list_actions` | get_current_user | 0 |
| GET | `/api/custom-template-ingestion/artifacts/{artifact_id}` | 查询隔离产物状态。 | `routers/custom_template_ingestion.py:204` `get_artifact` | get_current_user | 1 |
| POST | `/api/custom-template-ingestion/ingest` | 上传 Excel 自定义模板，进入 private quarantine。 | `routers/custom_template_ingestion.py:146` `ingest_excel_template` | get_current_user | 0 |
| GET | `/api/custom-template-ingestion/quota` | 返回组织级隔离区用量与配额，供前端做准入提示。 | `routers/custom_template_ingestion.py:223` `get_quota` | get_current_user | 0 |
| GET | `/api/custom-templates` |  | `routers/custom_templates.py:72` `list_my_templates` | get_current_user | 1 |
| POST | `/api/custom-templates` |  | `routers/custom_templates.py:64` `create_template` | — | 1 |
| GET | `/api/custom-templates/market` |  | `routers/custom_templates.py:81` `list_market` | get_current_user | 1 |
| POST | `/api/custom-templates/validate` |  | `routers/custom_templates.py:160` `validate_template` | — | 1 |
| DELETE | `/api/custom-templates/{template_id}` |  | `routers/custom_templates.py:113` `delete_template` | — | 1 |
| GET | `/api/custom-templates/{template_id}` |  | `routers/custom_templates.py:90` `get_template` | — | 1 |
| PUT | `/api/custom-templates/{template_id}` |  | `routers/custom_templates.py:99` `update_template` | get_current_user | 1 |
| POST | `/api/custom-templates/{template_id}/publish` |  | `routers/custom_templates.py:124` `publish_template` | — | 1 |
| POST | `/api/custom-templates/{template_id}/unpublish` |  | `routers/custom_templates.py:135` `unpublish_template` | — | 0 |
| POST | `/api/custom-templates/{template_id}/version` |  | `routers/custom_templates.py:146` `create_version` | get_current_user | 0 |
| GET | `/api/data-lifecycle/capacity` | 全局容量统计（各表行数、大小、按项目分布） | `routers/data_lifecycle.py:17` `get_capacity` | get_current_user | 0 |
| GET | `/api/data-lifecycle/import-queue` | 查看当前用户可见项目的导入队列。 | `routers/data_lifecycle.py:60` `get_import_queue` | get_current_user | 0 |
| GET | `/api/data-lifecycle/import-queue/{project_id}` | 查看项目导入状态 | `routers/data_lifecycle.py:71` `get_import_status` | get_current_user | 2 |
| DELETE | `/api/data-lifecycle/projects/{project_id}/purge` | 物理删除已归档数据（不可恢复，仅管理员） | `routers/data_lifecycle.py:49` `purge_project` | get_current_user、require_role | 0 |
| POST | `/api/data-lifecycle/projects/{project_id}/restore` | 恢复已归档的项目数据（仅管理员） | `routers/data_lifecycle.py:38` `restore_project` | get_current_user、require_role | 0 |
| GET | `/api/data-lifecycle/projects/{project_id}/stats` | 单个项目数据统计 | `routers/data_lifecycle.py:27` `get_project_stats` | get_current_user | 0 |
| GET | `/api/gt-coding` | 编码体系列表 | `routers/gt_coding.py:58` `list_codings` | get_current_user | 1 |
| POST | `/api/gt-coding` | 创建自定义编码条目 | `routers/gt_coding.py:115` `create_custom_coding` | get_current_user、require_role | 1 |
| GET | `/api/gt-coding/linkage` | 三测联动关系 | `routers/gt_coding.py:77` `get_three_test_linkage` | — | 1 |
| POST | `/api/gt-coding/seed` | 加载种子数据（幂等） | `routers/gt_coding.py:104` `load_seed_data` | — | 2 |
| GET | `/api/gt-coding/template-library` | 获取致同标准底稿模板库目录 | `routers/gt_coding.py:84` `get_template_library` | — | 1 |
| GET | `/api/gt-coding/tree` | 编码树形结构 | `routers/gt_coding.py:70` `get_coding_tree` | — | 1 |
| DELETE | `/api/gt-coding/{coding_id}` | 删除自定义编码条目 | `routers/gt_coding.py:159` `delete_custom_coding` | get_current_user、require_role | 2 |
| GET | `/api/gt-coding/{coding_id}` | 编码详情 | `routers/gt_coding.py:94` `get_coding` | — | 2 |
| PUT | `/api/gt-coding/{coding_id}` | 更新自定义编码条目 | `routers/gt_coding.py:140` `update_custom_coding` | get_current_user、require_role | 2 |
| POST | `/api/h5/export-data` | 导出H5当前数据xlsx | `routers/h5_oil_gas_assets.py:220` `h5_export_data` | get_current_user | 0 |
| POST | `/api/h5/export-template` | 导出H5空白xlsx模板 | `routers/h5_oil_gas_assets.py:173` `h5_export_template` | get_current_user | 0 |
| POST | `/api/h5/import-data` | 导入xlsx数据到H5底稿 | `routers/h5_oil_gas_assets.py:288` `h5_import_data` | get_current_user | 0 |
| GET | `/api/h9-lease-liabilities/{wp_id}/export-data` | 导出含当前数据的xlsx | `routers/h9_lease_liabilities.py:412` `h9_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/h9-lease-liabilities/{wp_id}/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/h9_lease_liabilities.py:387` `h9_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/h9-lease-liabilities/{wp_id}/generate-amortization` | 生成租赁负债摊销表（实际利率法） | `routers/h9_lease_liabilities.py:522` `h9_generate_amortization` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/h9-lease-liabilities/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses | `routers/h9_lease_liabilities.py:445` `h9_import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/i18n/audit-terms/{lang}` | 审计术语翻译 | `routers/i18n.py:48` `get_audit_terms` | — | 1 |
| GET | `/api/i18n/languages` | 支持的语言列表 | `routers/i18n.py:31` `get_languages` | — | 0 |
| GET | `/api/i18n/translations/{lang}` | 翻译字典 | `routers/i18n.py:38` `get_translations` | — | 1 |
| GET | `/api/l2-interest-payable/{wp_id}/accrual-check` | 获取计提核对数据（L1/L3利息测算 vs L2账面计提） | `routers/l2_interest_payable.py:437` `l2_accrual_check` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l2-interest-payable/{wp_id}/export-data` | 导出含当前数据的xlsx | `routers/l2_interest_payable.py:308` `l2_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/l2-interest-payable/{wp_id}/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/l2_interest_payable.py:279` `l2_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/l2-interest-payable/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses | `routers/l2_interest_payable.py:362` `l2_import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/l6-special-payables/{wp_id}/export-data` | 导出含当前数据的xlsx（多sheet） | `routers/l6_special_payables.py:186` `l6_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l6-special-payables/{wp_id}/export-template` | 导出空白xlsx模板（多sheet，按动态行表格分sheet） | `routers/l6_special_payables.py:145` `l6_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/l6-special-payables/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持多sheet） | `routers/l6_special_payables.py:255` `l6_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l7-other-noncurrent-liabilities/{wp_id}/export-data` | 导出含当前数据的xlsx（多sheet） | `routers/l7_other_noncurrent_liabilities.py:69` `l7_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l7-other-noncurrent-liabilities/{wp_id}/export-template` | 导出空白xlsx模板（多sheet，按动态行表格分sheet） | `routers/l7_other_noncurrent_liabilities.py:46` `l7_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/l7-other-noncurrent-liabilities/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持多sheet） | `routers/l7_other_noncurrent_liabilities.py:92` `l7_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l8-financial-expenses/{wp_id}/cutoff-extract` | 截止自动提取 — 序时账±N天 | `routers/l8_financial_expenses.py:201` `l8_cutoff_extract` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/l8-financial-expenses/{wp_id}/export-data` | 导出含当前数据的xlsx（多sheet） | `routers/l8_financial_expenses.py:112` `l8_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l8-financial-expenses/{wp_id}/export-template` | 导出空白xlsx模板（多sheet，按动态行表格分sheet） | `routers/l8_financial_expenses.py:84` `l8_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/l8-financial-expenses/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持多sheet） | `routers/l8_financial_expenses.py:140` `l8_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/l8-financial-expenses/{wp_id}/interest-summary` | 利息测算汇总 — 从L1/L3/L4/L5底稿取利息值 | `routers/l8_financial_expenses.py:173` `l8_interest_summary` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m1-dividends-payable/{wp_id}/dividend-calculation` | 股利测算计算结果（M1-5应付股利测算表） | `routers/m1_dividends_payable.py:374` `m1_dividend_calculation` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m1-dividends-payable/{wp_id}/export-data` | 导出含当前数据的xlsx（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算） | `routers/m1_dividends_payable.py:241` `m1_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m1-dividends-payable/{wp_id}/export-template` | 导出空白xlsx模板（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算） | `routers/m1_dividends_payable.py:210` `m1_export_template` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m1-dividends-payable/{wp_id}/fx-calculation` | 外币折算计算结果（M1-4外币汇率测算表） | `routers/m1_dividends_payable.py:342` `m1_fx_calculation` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m1-dividends-payable/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持3个sheet：M1-2/M1-4/M1-5） | `routers/m1_dividends_payable.py:272` `m1_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m1-dividends-payable/{wp_id}/validate-formulas` | 校验负债类公式方向（期末=期初+贷方-借方） | `routers/m1_dividends_payable.py:313` `m1_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m10-other-equity-instruments/{wp_id}/classification-summary` | 获取CAS37负债权益区分汇总 | `routers/m10_other_equity_instruments.py:273` `m10_classification_summary` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m10-other-equity-instruments/{wp_id}/export-data` | 导出含当前数据的xlsx（M10-2明细表 当前永续债/优先股数据） | `routers/m10_other_equity_instruments.py:161` `m10_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m10-other-equity-instruments/{wp_id}/export-template` | 导出空白xlsx模板（M10-2明细表 永续债/优先股） | `routers/m10_other_equity_instruments.py:131` `m10_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m10-other-equity-instruments/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（M10-2明细表动态行 永续债/优先股） | `routers/m10_other_equity_instruments.py:191` `m10_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m10-other-equity-instruments/{wp_id}/validate-formulas` | 校验权益类公式：期末=期初+贷方-借方 | `routers/m10_other_equity_instruments.py:226` `m10_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m2-paid-in-capital/{wp_id}/export-data` | 导出含当前数据的xlsx（3个sheet：M2-2上市明细/M2-2非上市明细/M2-4外币投资） | `routers/m2_paid_in_capital.py:127` `m2_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m2-paid-in-capital/{wp_id}/export-template` | 导出空白xlsx模板（3个sheet：M2-2上市明细/M2-2非上市明细/M2-4外币投资） | `routers/m2_paid_in_capital.py:99` `m2_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m2-paid-in-capital/{wp_id}/fx-calculate` | 批量计算外币折算（M2-4外币投资汇率测算表） | `routers/m2_paid_in_capital.py:188` `m2_fx_calculate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m2-paid-in-capital/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持3个sheet：M2-2上市/M2-2非上市/M2-4） | `routers/m2_paid_in_capital.py:155` `m2_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m2-paid-in-capital/{wp_id}/investor-summary` | 按出资人汇总实收资本数据 | `routers/m2_paid_in_capital.py:250` `m2_investor_summary` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m2-paid-in-capital/{wp_id}/validate-formulas` | 校验权益类公式方向（期末=期初+贷方-借方） | `routers/m2_paid_in_capital.py:281` `m2_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m2-paid-in-capital/{wp_id}/verify-calculate` | 批量计算验资核对（M2-5检查表） | `routers/m2_paid_in_capital.py:218` `m2_verify_calculate` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m3-treasury-stock/{wp_id}/export-data` | 导出含当前数据的xlsx（3个sheet：M3-2明细/M3-4外币/M3-5检查表） | `routers/m3_treasury_stock.py:134` `m3_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m3-treasury-stock/{wp_id}/export-template` | 导出空白xlsx模板（3个sheet：M3-2明细/M3-4外币/M3-5检查表） | `routers/m3_treasury_stock.py:104` `m3_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m3-treasury-stock/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持3个sheet：M3-2/M3-4/M3-5） | `routers/m3_treasury_stock.py:164` `m3_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m3-treasury-stock/{wp_id}/tb-seed` | 获取TB科目4201库存股的种子数据 | `routers/m3_treasury_stock.py:231` `m3_tb_seed` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/m3-treasury-stock/{wp_id}/validate-formulas` | 校验权益备抵类公式方向（期末=期初+借方-贷方） | `routers/m3_treasury_stock.py:199` `m3_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/m4-capital-reserve/{wp_id}/export-data` | 导出含当前数据的xlsx（2个sheet：M4-2明细表/M4-4检查表） | `routers/m4_capital_reserve.py:135` `m4_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m4-capital-reserve/{wp_id}/export-template` | 导出空白xlsx模板（2个sheet：M4-2明细表/M4-4检查表） | `routers/m4_capital_reserve.py:105` `m4_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m4-capital-reserve/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持2个sheet：M4-2明细/M4-4检查表） | `routers/m4_capital_reserve.py:165` `m4_import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m4-capital-reserve/{wp_id}/j3-linkage` | 获取J3股份支付权益结算联动数据 | `routers/m4_capital_reserve.py:268` `m4_j3_linkage` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m4-capital-reserve/{wp_id}/reserve-changes` | 获取资本公积变动明细（M4-2数据汇总） | `routers/m4_capital_reserve.py:200` `m4_reserve_changes` | dedicated_wp_gate、get_current_user | 1 |
| PUT | `/api/m4-capital-reserve/{wp_id}/validate-formulas` | 校验权益类贷方公式方向（期末=期初+贷方-借方） | `routers/m4_capital_reserve.py:236` `m4_validate_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m5-surplus-reserve/{wp_id}/accrual-test` | 法定盈余公积计提测试（10%计提验证 + 50%上限判断） | `routers/m5_surplus_reserve.py:202` `m5_accrual_test` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m5-surplus-reserve/{wp_id}/export-data` | 导出含当前数据的xlsx（M5-2明细表/M5-4计提检查表） | `routers/m5_surplus_reserve.py:137` `m5_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m5-surplus-reserve/{wp_id}/export-template` | 导出空白xlsx模板（M5-2明细表/M5-4计提检查表） | `routers/m5_surplus_reserve.py:107` `m5_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m5-surplus-reserve/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（支持M5-2明细/M5-4计提检查表） | `routers/m5_surplus_reserve.py:167` `m5_import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m6-retained-earnings/{wp_id}/distribution-summary` | 获取利润分配结转汇总（用于M5/M1联动核对） | `routers/m6_retained_earnings.py:316` `m6_distribution_summary` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m6-retained-earnings/{wp_id}/export-data` | 导出含当前数据的xlsx（多sheet：M6-2明细表 + M6-1审定表） | `routers/m6_retained_earnings.py:187` `m6_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m6-retained-earnings/{wp_id}/export-template` | 导出空白xlsx模板（多sheet：M6-2明细表 + M6-1审定表） | `routers/m6_retained_earnings.py:157` `m6_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m6-retained-earnings/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（仅M6-2明细表动态行） | `routers/m6_retained_earnings.py:217` `m6_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m6-retained-earnings/{wp_id}/validate-formulas` | 校验权益类公式方向（期末=期初+贷方-借方） | `routers/m6_retained_earnings.py:252` `m6_validate_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m7-special-reserve/{wp_id}/accrual-test` | 安全生产费计提测试 | `routers/m7_special_reserve.py:206` `m7_accrual_test` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m7-special-reserve/{wp_id}/export-data` | 导出含当前数据的xlsx（M7-2明细：输入列 + 公式列 + 合计行） | `routers/m7_special_reserve.py:141` `m7_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m7-special-reserve/{wp_id}/export-template` | 导出空白xlsx模板（M7-2明细表，含「编制说明」页） | `routers/m7_special_reserve.py:111` `m7_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m7-special-reserve/{wp_id}/import-data` | 导入xlsx整表替换 M7-2 明细行（写 checklist_responses，与界面同一组键） | `routers/m7_special_reserve.py:171` `m7_import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m8-general-risk-reserve/{wp_id}/export-data` | 导出含当前数据的xlsx（M8-2明细/M8-4风险测试） | `routers/m8_general_risk_reserve.py:141` `m8_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m8-general-risk-reserve/{wp_id}/export-template` | 导出空白xlsx模板（M8-2明细表 / M8-4风险测试表） | `routers/m8_general_risk_reserve.py:111` `m8_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m8-general-risk-reserve/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（M8-2明细表动态行） | `routers/m8_general_risk_reserve.py:171` `m8_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m8-general-risk-reserve/{wp_id}/risk-provision-test` | 风险资产计提测试 | `routers/m8_general_risk_reserve.py:232` `m8_risk_provision_test` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m8-general-risk-reserve/{wp_id}/validate-formulas` | 验证公式一致性（审定表vs明细表 / 计提测试差异） | `routers/m8_general_risk_reserve.py:206` `m8_validate_formulas` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m9-other-comprehensive-income/{wp_id}/export-data` | 导出含当前数据的xlsx（M9-2明细：输入列 + 公式列 + 合计行） | `routers/m9_other_comprehensive_income.py:169` `m9_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m9-other-comprehensive-income/{wp_id}/export-template` | 导出空白xlsx模板（M9-2明细表，含「编制说明」页） | `routers/m9_other_comprehensive_income.py:139` `m9_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m9-other-comprehensive-income/{wp_id}/import-data` | 导入xlsx整表替换 M9-2 明细行（写 checklist_responses，与界面同一组键） | `routers/m9_other_comprehensive_income.py:199` `m9_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/m9-other-comprehensive-income/{wp_id}/tb-writeback` | 审定数回写到 trial_balance（科目4003其他综合收益） | `routers/m9_other_comprehensive_income.py:306` `m9_tb_writeback` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/m9-other-comprehensive-income/{wp_id}/validate-formulas` | 校验权益类公式方向（期末=期初+贷方-借方） | `routers/m9_other_comprehensive_income.py:234` `m9_validate_formulas` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/n1-deferred-tax-assets/{wp_id}/export-data` | 导出含当前数据的xlsx（N1-2明细表动态行数据） | `routers/n1_deferred_tax_assets.py:383` `n1_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n1-deferred-tax-assets/{wp_id}/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/n1_deferred_tax_assets.py:355` `n1_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n1-deferred-tax-assets/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（N1-2明细表动态行） | `routers/n1_deferred_tax_assets.py:436` `n1_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n2-taxes-payable/{wp_id}/ai-assist` | AI辅助生成（section-based） | `routers/n2_taxes_payable.py:389` `n2_ai_assist` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n2-taxes-payable/{wp_id}/contract-ocr` | OCR识别（行级附件） — 税费缴纳凭证/纳税申报表附件 | `routers/n2_taxes_payable.py:536` `n2_contract_ocr` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n2-taxes-payable/{wp_id}/export-data` | 导出含当前数据的xlsx（多税种分sheet） | `routers/n2_taxes_payable.py:229` `n2_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n2-taxes-payable/{wp_id}/export-template` | 导出空白xlsx模板（多税种分sheet） | `routers/n2_taxes_payable.py:189` `n2_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n2-taxes-payable/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（多税种分sheet） | `routers/n2_taxes_payable.py:269` `n2_import_data` | dedicated_wp_gate、get_current_user | 0 |
| PUT | `/api/n2-taxes-payable/{wp_id}/tb-writeback` | 审定数回写到 trial_balance（科目2221应交税费） | `routers/n2_taxes_payable.py:445` `n2_tb_writeback` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n3-deferred-tax-liabilities/{wp_id}/export-data` | 导出含当前数据的xlsx（N3-2明细表动态行数据） | `routers/n3_deferred_tax_liabilities.py:251` `n3_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n3-deferred-tax-liabilities/{wp_id}/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/n3_deferred_tax_liabilities.py:223` `n3_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n3-deferred-tax-liabilities/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（N3-2明细表动态行） | `routers/n3_deferred_tax_liabilities.py:303` `n3_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n4/export-data` | 导出含当前数据的xlsx | `routers/n4_taxes_and_surcharges.py:341` `n4_export_data` | get_current_user | 0 |
| POST | `/api/n4/export-template` | 导出空白xlsx模板（含表头+格式+编制说明） | `routers/n4_taxes_and_surcharges.py:305` `n4_export_template` | get_current_user | 0 |
| POST | `/api/n4/import-data` | 导入xlsx解析写入checklist_responses | `routers/n4_taxes_and_surcharges.py:387` `n4_import_data` | get_current_user | 0 |
| GET | `/api/n5-income-tax-expense/{wp_id}/export-data` | 导出含当前数据的xlsx（纳税调整分sheet导出） | `routers/n5_income_tax_expense.py:337` `n5_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/n5-income-tax-expense/{wp_id}/export-template` | 导出空白xlsx模板（纳税调整分sheet） | `routers/n5_income_tax_expense.py:297` `n5_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/n5-income-tax-expense/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses | `routers/n5_income_tax_expense.py:400` `n5_import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/projects/actions/registry` | 获取完整动作注册表（前端缓存用） | `routers/wp_functional_actions.py:159` `get_action_registry` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/projects/{pid}/procedure-delegations/apply` | 委派应用：消费 preview，真实 assign/reassign；默认原子，best_effort 逐任务结果。 | `routers/procedure_delegations.py:129` `delegation_apply` | get_current_user、require_project_delegator_pid | 1 |
| GET | `/api/projects/{pid}/procedure-delegations/member-loads` | 成员负载批量视图（**只读**，供委派界面与底稿主编下拉展示）。 | `routers/procedure_delegations.py:77` `delegation_member_loads` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-delegations/preview` | 委派预览：materialize 前置 + 目标分类 + 一次性 preview 凭证。 | `routers/procedure_delegations.py:99` `delegation_preview` | get_current_user、require_project_delegator_pid | 1 |
| GET | `/api/projects/{pid}/procedure-delivery/dead-letters` | 列出本项目投递失败进入 dead-letter 的事件（纯读）。 | `routers/procedure_delivery.py:35` `list_dead_letters` | get_current_user、require_project_delegator_pid | 0 |
| GET | `/api/projects/{pid}/procedure-delivery/metrics` | 投递指标：backlog/oldest age/lease/失败/延迟/dead-letter（纯读）。 | `routers/procedure_delivery.py:47` `delivery_metrics` | get_current_user、require_project_delegator_pid | 0 |
| POST | `/api/projects/{pid}/procedure-delivery/{event_id}/replay` | 把 dead-letter 事件重置为可领取（保留事件，清 dead_letter/lease/backoff）。 | `routers/procedure_delivery.py:58` `replay_dead_letter` | get_current_user、require_project_delegator_pid | 0 |
| POST | `/api/projects/{pid}/procedure-row-tasks/reconcile/apply` | reconcile 应用：消费 preview，显式迁移 matched + resolution 项。 | `routers/procedure_reconcile.py:76` `reconcile_apply` | get_current_user、require_project_delegator_pid | 0 |
| POST | `/api/projects/{pid}/procedure-row-tasks/reconcile/preview` | reconcile 预览：分类 + 一次性 preview 凭证。 | `routers/procedure_reconcile.py:54` `reconcile_preview` | get_current_user、require_project_delegator_pid | 0 |
| POST | `/api/projects/{pid}/procedure-trim/apply` | 方案应用：消费 preview，真实 applied/unchanged/conflict；legacy UUID 无法 | `routers/procedure_trim.py:174` `trim_apply` | get_current_user、require_project_delegator_pid | 1 |
| GET | `/api/projects/{pid}/procedure-trim/completeness-scope` | 读回本项目完整性敏感清单的项目级覆盖（含理由与最后修改留痕）。 | `routers/procedure_trim.py:276` `trim_list_completeness_scope` | get_current_user、require_project_delegator_pid | 1 |
| PUT | `/api/projects/{pid}/procedure-trim/completeness-scope` | 写一条完整性敏感清单的项目级覆盖（``Y``/``N`` 都算已表态）。 | `routers/procedure_trim.py:293` `trim_set_completeness_scope` | get_current_user、require_project_delegator_pid | 1 |
| DELETE | `/api/projects/{pid}/procedure-trim/completeness-scope/{cycle}` | 撤销某循环的项目级覆盖 → 该循环退回平台默认清单。 | `routers/procedure_trim.py:323` `trim_clear_completeness_scope` | get_current_user、require_project_delegator_pid | 1 |
| GET | `/api/projects/{pid}/procedure-trim/note-linkage` | 只读预览：本次程序裁剪会把哪些附注章节标为本期不适用 / 撤销 / 只提示（R13.1）。 | `routers/procedure_trim.py:346` `trim_note_linkage_preview` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/note-linkage/apply` | 应用联动：**只写** ``disclosure_notes.is_empty`` + provenance 面包屑。 | `routers/procedure_trim.py:365` `trim_note_linkage_apply` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/preview` | 方案预览：解析计划 + 一次性 preview 凭证。 | `routers/procedure_trim.py:154` `trim_preview` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/rows/{task_id}/not-applicable` | 细裁 → not_applicable：经 TransitionService cancel（applicability | `routers/procedure_trim.py:222` `trim_row_not_applicable` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/rows/{task_id}/restore` | 细裁恢复 → execute：经 TransitionService reopen（cancelled→unassign | `routers/procedure_trim.py:390` `trim_row_restore` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/schemes` | 保存裁剪方案（canonical key + revision + 文本快照）。 | `routers/procedure_trim.py:201` `trim_save_scheme` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/suggestions/reject` | 驳回裁剪建议：只写 ``suggestion_state.rejected``，**不改适用性状态**（R6.4）。 | `routers/procedure_trim.py:248` `trim_reject_suggestions` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/not-applicable` | 程序表某一行 → 不适用（自加的行 / 无模板的程序表 422）。 | `routers/procedure_trim.py:436` `trim_program_row` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/restore` | 程序表某一行恢复执行（任务回到待委派，须重新委派）。 | `routers/procedure_trim.py:494` `restore_program_row` | get_current_user、require_project_delegator_pid | 1 |
| POST | `/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/task` | 取 / 建这一程序行的任务（控制台逐行委派用；程序行任务开关关闭时也可用，spec procedure-chain-fo | `routers/procedure_trim.py:469` `ensure_program_row_task` | get_current_user、require_project_delegator_pid | 1 |
| PUT | `/api/projects/{pid}/workpaper-leads` | 批量设置底稿主编（``WorkingPaper.assigned_to`` 权威 + 投影 + 历史 + epoch + | `routers/workpaper_leads.py:61` `set_workpaper_leads` | get_current_user、require_project_delegator_pid | 2 |
| GET | `/api/projects/{pid}/workpapers/{wp_id}/versions` | 分页获取快照列表（按 created_at DESC）。 | `routers/version_trail.py:111` `list_versions` | get_current_user | 3 |
| POST | `/api/projects/{pid}/workpapers/{wp_id}/versions` | 创建版本快照。 | `routers/version_trail.py:72` `create_version` | get_current_user | 3 |
| POST | `/api/projects/{pid}/workpapers/{wp_id}/versions/compare` | 计算两个快照间的 field-level diff。 | `routers/version_trail.py:179` `compare_versions` | get_current_user | 0 |
| GET | `/api/projects/{pid}/workpapers/{wp_id}/versions/{vid}` | 获取快照详情（含 data_json）。 | `routers/version_trail.py:147` `get_version_detail` | get_current_user | 2 |
| POST | `/api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback` | 回滚到指定快照（仅现场经理及以上）。 | `routers/version_trail.py:212` `rollback_version` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/a16/recommended-version` | 根据项目质控分类 / 专项场景推荐 A16 声明书版本。 | `routers/wp_editor_router.py:1084` `get_a16_recommended_version` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| GET | `/api/projects/{project_id}/a18/generate-summary` | 从 A17-1 章节生成 A18-1 审计小结框架（P2，依赖 A17-core） | `routers/a18_regulatory.py:37` `get_a18_generated_summary` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/a18/suggestions` | 获取 A18-2 议题填写建议（issue_hints + A8 步骤映射） | `routers/a18_regulatory.py:22` `get_a18_suggestions` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/a21/applicable-review-templates` |  | `routers/a21_review.py:63` `applicable_review_templates` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/a21/prefill-suggestions` |  | `routers/a21_review.py:86` `prefill_suggestions` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/a21/resolve-wp-code` | 将父码 A21/A22… 解析为当前项目适用的子码（如 A21-1）。 | `routers/a21_review.py:96` `resolve_wp_code` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/projects/{project_id}/a21/review-definitions` |  | `routers/a21_review.py:72` `review_definitions` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/a21/review-sign-status` |  | `routers/a21_review.py:108` `review_sign_status` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/b5/recommended-version` | 推荐 B5 约定书主版本（基于项目 business_category + signals） | `routers/b5_version.py:29` `get_b5_recommended_version` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/b60/attachment-flags` |  | `routers/b60_plan.py:35` `get_b60_attachment_flags` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/b60/attachment-flags` |  | `routers/b60_plan.py:44` `put_b60_attachment_flags` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/b60/b60d-archive` |  | `routers/b60_plan.py:116` `put_b60_b60d_archive` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/b60/plan-update` | 第十五章重大更新：须 confirm_major_change + reason，递增 plan_version。 | `routers/b60_plan.py:56` `post_b60_plan_update` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/b60/qc-status` |  | `routers/b60_plan.py:128` `get_b60_qc_status` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/b60/scot-rows` |  | `routers/b60_plan.py:95` `get_b60_scot_rows` | get_current_user | 2 |
| PUT | `/api/projects/{project_id}/b60/scot-rows` |  | `routers/b60_plan.py:104` `put_b60_scot_rows` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/bulk-tab/export-data` | 批量导出底稿 Tab **数据**为 ZIP（含已填写数据快照）。 | `routers/wp_bulk_router.py:555` `bulk_export_data` | get_current_user_stream、require_project_access_stream(readon | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/export-data/async` | 大项目异步导出**数据** ZIP：立即返回 task_id，后台生成，SSE 推进度。 | `routers/wp_bulk_router.py:661` `bulk_export_data_async` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/export-templates` | 批量导出底稿 Tab **模板**为 ZIP（空表结构 + 编制提示）。 | `routers/wp_bulk_router.py:494` `bulk_export_templates` | get_current_user_stream、require_project_access_stream(readon | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/export-templates/async` | 大项目异步导出**模板** ZIP：立即返回 task_id，后台生成，SSE 推进度。 | `routers/wp_bulk_router.py:628` `bulk_export_templates_async` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/bulk-tab/export/{task_id}/download` | 下载已完成的异步导出 ZIP（Req 6.1）。 | `routers/wp_bulk_router.py:698` `bulk_export_download` | get_current_user_stream、require_project_access_stream(readon | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/import` | 批量导入底稿 Tab 数据（multipart ZIP）。 | `routers/wp_bulk_router.py:748` `bulk_import` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/import/async` | 大项目异步导入：立即返回 task_id，后台跑导入，SSE 推进度（Req 6.1）。 | `routers/wp_bulk_router.py:832` `bulk_import_async` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/import/rollback` | 按 import_id 回滚批量导入（恢复到快照状态）。 | `routers/wp_bulk_router.py:1040` `bulk_import_rollback` | _require_manager_role、get_current_user | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/import/{task_id}/cancel` | 请求取消自己的耐久导入；运行中任务在安全边界协作式收口。 | `routers/wp_bulk_router.py:1012` `cancel_bulk_import` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/bulk-tab/import/{task_id}/result` | 查询耐久导入结果；DB snapshot 是断线/重启后的权威状态。 | `routers/wp_bulk_router.py:964` `bulk_import_result` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/projects/{project_id}/bulk-tab/preview-manifest` | Preview manifest.json from uploaded ZIP without importing. | `routers/wp_bulk_router.py:459` `preview_manifest` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/bulk-tab/progress/{task_id}` | SSE 进度流 — 实时推送批量导入/导出进度。 | `routers/wp_bulk_router.py:60` `get_bulk_progress_stream` | get_current_user_stream、require_project_access_stream(readon | 0 |
| GET | `/api/projects/{project_id}/bulk-tab/scenarios` | 四场景语义 + 当前项目状态下的可用性（R3.7 / R3.8）。 | `routers/wp_bulk_router.py:403` `list_bulk_scenarios` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/child-companies` | 获取合并项目下的子公司列表 | `routers/workpaper_summary.py:26` `get_child_companies` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/clone-coding` | 克隆标准编码体系到项目级自定义 | `routers/gt_coding.py:175` `clone_coding_for_project` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/cross-cycle-breakage` | 获取跨循环断裂清单。 | `routers/cross_cycle_breakage.py:36` `get_breakage_list` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/excel-html/cell-info/{file_stem}` | 获取单元格详细信息（地址/公式/合并范围/取数规则） | `routers/excel_html.py:543` `get_cell_info` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/excel-html/confirm-template/{file_stem}` | 确认为正式模板（编辑完成后） | `routers/excel_html.py:249` `confirm_as_template` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/excel-html/download/{file_stem}` | 下载文件（支持三种格式） | `routers/excel_html.py:352` `download_file` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/excel-html/execute-formulas/{file_stem}` | 执行 structure.json 中所有公式并回填计算结果 | `routers/excel_html.py:710` `execute_formulas` | get_current_user、require_project_access(edit) | 1 |
| DELETE | `/api/projects/{project_id}/excel-html/lock/{file_stem}` | 释放编辑锁 | `routers/excel_html.py:680` `release_lock` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/excel-html/lock/{file_stem}` | 获取编辑锁（防止多人同时编辑冲突） | `routers/excel_html.py:665` `acquire_lock` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/excel-html/lock/{file_stem}/refresh` | 刷新编辑锁（用户仍在编辑时定期调用） | `routers/excel_html.py:693` `refresh_lock` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/excel-html/module/{module}/export-excel` | 统一接口：任意模块导出 Excel | `routers/excel_html.py:450` `export_module_excel` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/excel-html/module/{module}/export-word` | 统一接口：任意模块导出 Word（致同三线表排版） | `routers/excel_html.py:497` `export_module_word` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/excel-html/module/{module}/html` | 统一接口：获取任意模块的 HTML 渲染 | `routers/excel_html.py:419` `get_module_html` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/excel-html/module/{module}/structure` | 统一接口：获取任意模块的 structure.json | `routers/excel_html.py:385` `get_module_structure` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/excel-html/preview/{file_stem}` | 获取 HTML 预览（可编辑模式，支持大表格分页） | `routers/excel_html.py:127` `get_html_preview` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/excel-html/save-edits/{file_stem}` | 保存在线编辑结果 → 更新 structure.json + 回写 Excel | `routers/excel_html.py:166` `save_edits` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/excel-html/sync-from-onlyoffice/{file_stem}` | 编辑器保存后同步 structure.json（向后兼容端点） | `routers/excel_html.py:307` `sync_from_onlyoffice` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/excel-html/upload-parse` | 上传 Excel → 解析为 structure.json + 返回 HTML 预览 | `routers/excel_html.py:55` `upload_and_parse` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/excel-html/versions/{file_stem}` | 列出文件的所有版本快照 | `routers/excel_html.py:606` `list_file_versions` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/excel-html/versions/{file_stem}/diff` | 对比两个版本的差异 | `routers/excel_html.py:618` `diff_file_versions` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/excel-html/versions/{file_stem}/rollback/{version}` | 回滚到指定版本 | `routers/excel_html.py:632` `rollback_file_version` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/fine-checks/summary` | 批量获取项目所有底稿的精细化检查结果（避免前端 N+1 请求） | `routers/wp_fine_rules.py:140` `get_fine_checks_summary` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/projects/{project_id}/generate-index` | 根据致同编码体系为项目自动生成底稿索引 | `routers/gt_coding.py:196` `generate_project_index` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/my-lead-workpapers` | 我的主编底稿（MyLeadWorkpapers，组件 C13 / Req 11.12–11.13）。 | `routers/working_paper.py:183` `list_my_lead_workpapers` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| GET | `/api/projects/{project_id}/procedure-scope/confirmations` | 各循环粗裁状态：未打开 / 未保存 / 已保存（最近一次保存人与时间）。只读。 | `routers/procedures.py:133` `get_scope_confirmations` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/procedure-scope/data-availability` | 科目/循环数据可用性，供智能裁剪精确到科目底稿级。 | `routers/procedures.py:76` `get_procedure_data_availability` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/procedure-scope/generation-plan` | 生成计划（spec trim-generation-plan-linkage R1，只读）：按循环给出每个模板编码这次生 | `routers/procedures.py:111` `get_generation_plan` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/procedure-scope/trim-decision-context` | 裁剪三维判据上下文（风险 / 重要性 / 数据存在性）+ 完整性覆盖 + 底稿录入探测。 | `routers/procedures.py:90` `get_trim_decision_context` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/procedure-tables/batch` | 批量获取多个程序表数据（一次请求返回多表） | `routers/wp_procedure_tables.py:45` `get_procedure_tables_batch` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/procedure-tables/custom-items` | 持久化用户自定义程序行（存入 field_overrides 表） | `routers/wp_procedure_tables.py:91` `create_custom_item` | get_current_user、require_project_access(edit)、require_projec | 4 |
| DELETE | `/api/projects/{project_id}/procedure-tables/custom-items/{item_id}` | 删除用户自定义程序行 | `routers/wp_procedure_tables.py:123` `delete_custom_item` | get_current_user、require_project_access(edit)、require_projec | 0 |
| GET | `/api/projects/{project_id}/procedure-tables/{table_code}` | 获取指定程序表的完整数据（模板 + 自动值 + 用户覆盖） | `routers/wp_procedure_tables.py:68` `get_procedure_table` | get_current_user、require_project_access(readonly) | 6 |
| PUT | `/api/projects/{project_id}/procedures/assign` | 已下线：底稿主编写入口统一为 PUT /api/projects/{pid}/workpaper-leads。 | `routers/procedures.py:530` `assign_procedures_gone` | — | 1 |
| PUT | `/api/projects/{project_id}/procedures/instance/{procedure_id}/execution` | 已下线：执行进度是程序行任务真源，只走 ProcedureRowTask 状态机 transitions。 | `routers/procedures.py:558` `update_execution_status_gone` | — | 1 |
| GET | `/api/projects/{project_id}/procedures/{cycle}` |  | `routers/procedures.py:149` `get_procedures` | get_current_user、require_project_access(readonly) | 4 |
| POST | `/api/projects/{project_id}/procedures/{cycle}/apply-scheme` | 已下线：参照项目必须读源项目当前 wp_code/status 构造 canonical entries 再走 prev | `routers/procedures.py:546` `apply_scheme_gone` | — | 1 |
| POST | `/api/projects/{project_id}/procedures/{cycle}/batch-apply` | 已下线：批量套用改为逐目标项目调用 canonical preview/apply（真实 applied 可核）。 | `routers/procedures.py:552` `batch_apply_gone` | — | 0 |
| GET | `/api/projects/{project_id}/procedures/{cycle}/blank-template` | 生成并下载空白底稿模板 Excel. | `routers/procedures.py:266` `download_blank_template` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/procedures/{cycle}/custom` |  | `routers/procedures.py:187` `add_custom` | get_current_user、require_project_delegator | 1 |
| POST | `/api/projects/{project_id}/procedures/{cycle}/custom-with-template` | 新增自定义程序 + 上传底稿模板文件（multipart）. | `routers/procedures.py:217` `add_custom_with_template` | get_current_user、require_project_delegator | 1 |
| DELETE | `/api/projects/{project_id}/procedures/{cycle}/custom/{proc_id}` | 删除自定义程序（软删 ProcedureInstance + 清理 WpIndex 占位）。 | `routers/procedures.py:202` `delete_custom_procedure` | get_current_user、require_project_delegator | 2 |
| POST | `/api/projects/{project_id}/procedures/{cycle}/init` |  | `routers/procedures.py:164` `init_procedures` | get_current_user、require_project_delegator | 1 |
| PUT | `/api/projects/{project_id}/procedures/{cycle}/trim` | 已下线：粗裁写入口统一为 procedure-trim/preview\|apply（canonical scope k | `routers/procedures.py:181` `save_trim_gone` | — | 1 |
| GET | `/api/projects/{project_id}/procedures/{cycle}/trim-scheme` |  | `routers/procedures.py:536` `get_trim_scheme` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/review-context` |  | `routers/a21_review.py:54` `review_context` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/s34-checklist` | 返回 S34 核查事项清单 — 41 条专项底稿的法规溯源 + 适用性 + 完成状态. | `routers/s34_checklist_router.py:72` `get_project_s34_checklist` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/signoff/checklist` | 获取签发一致性清单（每次实时计算，不走缓存）。 | `routers/signoff_checklist.py:39` `get_signoff_checklist` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/signoff/confirm-warning` | 确认 warning 项并写审计日志（``app_audit_log``）。 | `routers/signoff_checklist.py:64` `confirm_warning` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/working-papers` | 底稿列表（服务端强制可见性 + 正式分页 / 状态拆分）。 | `routers/working_paper.py:98` `list_workpapers` | dedicated_wp_gate、get_current_user、require_project_access(re | 3 |
| GET | `/api/projects/{project_id}/working-papers-all` | 全部可见底稿（不分页）：与 ``/working-papers`` 同一鉴权 / 可见性 / 过滤 / 项结构，返回 ` | `routers/working_paper.py:150` `list_all_workpapers` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| GET | `/api/projects/{project_id}/working-papers-kanban` | 底稿看板视图 — 按状态分组 + 按人聚合（服务端强制可见性隔离）。 | `routers/wp_batch_router.py:113` `get_workpapers_kanban` | dedicated_wp_gate、get_current_user、require_project_access(re | 3 |
| POST | `/api/projects/{project_id}/working-papers/batch-assign` | 批量分配底稿（编制人/复核人）。 | `routers/wp_batch_router.py:255` `batch_assign` | dedicated_wp_gate、get_current_user、require_project_access(re | 12 |
| POST | `/api/projects/{project_id}/working-papers/batch-export` | 批量导出底稿为 ZIP | `routers/wp_batch_router.py:367` `batch_export_zip` | dedicated_wp_gate、get_current_user、require_project_access(re | 11 |
| POST | `/api/projects/{project_id}/working-papers/batch-status` | 兼容的批量编制状态操作；提交复核必须走统一门禁入口。 | `routers/workpaper_batch_status.py:59` `batch_status_change` | get_current_user | 12 |
| POST | `/api/projects/{project_id}/working-papers/batch-submit` | 批量提交复核；每稿一个保存点，但全部复用单笔提交服务与五项门禁。 | `routers/wp_batch_router.py:314` `batch_submit_review` | dedicated_wp_gate、get_current_user、require_project_access(ed | 13 |
| POST | `/api/projects/{project_id}/working-papers/create-custom` | 创建自定义底稿（用户自建，非模板生成） | `routers/wp_template.py:695` `create_custom_workpaper` | get_current_user、require_project_access(edit) | 11 |
| POST | `/api/projects/{project_id}/working-papers/create-custom-batch` | 批量创建自定义底稿。 | `routers/wp_template.py:815` `create_custom_workpaper_batch` | get_current_user、require_project_access(edit) | 12 |
| POST | `/api/projects/{project_id}/working-papers/create-custom-batch/preview` | 批量创建**预览**（只读）。 | `routers/wp_template.py:735` `preview_custom_workpaper_batch` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/working-papers/download-pack` |  | `routers/working_paper.py:229` `download_workpaper_pack` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 11 |
| POST | `/api/projects/{project_id}/working-papers/generate` | 从模板集生成项目底稿 | `routers/wp_template.py:271` `generate_project_workpapers` | get_current_user、require_project_access(edit) | 11 |
| POST | `/api/projects/{project_id}/working-papers/generate-from-codes` | 从推荐的底稿编码列表直接生成底稿文件（不需要模板集） | `routers/wp_template.py:360` `generate_from_codes` | get_current_user、require_project_access(edit) | 11 |
| GET | `/api/projects/{project_id}/working-papers/generation-operations/{operation_id}` | 读取持久生成 operation；路径项目与 operation 归属同时匹配。 | `routers/wp_template.py:336` `get_workpaper_generation_operation` | get_current_user、require_project_access(readonly) | 15 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}` | 底稿详情（需项目成员权限） | `routers/working_paper.py:263` `get_workpaper` | dedicated_wp_gate、get_current_user、require_project_access(re | 17 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/b2-12/export-docx` | B2-12 对前任注册会计师的评价底稿 → docx 导出（供打印签字归档）。 | `routers/wp_editor_router.py:912` `export_b2_12_docx` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/cross-links` | 获取底稿间可点击的穿透链接 | `routers/wp_relation_router.py:112` `get_cross_links` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/download` | 下载底稿（需项目成员权限） | `routers/working_paper.py:295` `download_workpaper` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/edit-time` | 获取底稿编制时间统计 | `routers/wp_batch_router.py:416` `get_edit_time` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/export-pdf` | 导出底稿为 PDF（使用 LibreOffice headless 转换）— 需求 16 | `routers/wp_editor_router.py:820` `export_workpaper_pdf` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/file-info` | 返回底稿文件信息 + 签发状态（A16 声明书用；optional version 按子码隔离） | `routers/working_paper.py:331` `get_workpaper_file_info` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/online-session` | 获取在线编辑会话配置。 | `routers/wp_editor_router.py:41` `get_online_edit_session` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/onlyoffice-config` | 返回底稿的 OnlyOffice 编辑器配置（复用 deliverable 模块的 signed-download 机制 | `routers/wp_editor_router.py:468` `get_wp_onlyoffice_config` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/parse` | 手动触发解析回写（需编辑权限）— 真正打开 .xlsx 提取关键数据 | `routers/wp_editor_router.py:1060` `parse_workpaper` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| PUT | `/api/projects/{project_id}/working-papers/{wp_id}/parsed-data` | 更新底稿 parsed_data（结构化组件数据持久化）。 | `routers/working_paper.py:441` `update_parsed_data` | dedicated_wp_gate、get_current_user、require_project_access(ed | 8 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/prefill` | 手动触发预填充（需编辑权限）— 真正打开 .xlsx 扫描公式并写入 | `routers/wp_editor_router.py:1021` `prefill_workpaper` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| PATCH | `/api/projects/{project_id}/working-papers/{wp_id}/procedure-status` | 更新程序行状态（filled→reviewed→approved 三档晋级）。 | `routers/wp_procedure_status.py:52` `update_procedure_status` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/relation-graph` | 获取底稿关系图数据（基于 cross_wp_references.json） | `routers/wp_relation_router.py:189` `get_wp_relation_graph` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/sign-status` | 更新 word-template 底稿签署状态（通用化，支持所有 word-template wp_code）。 | `routers/wp_editor_router.py:343` `update_sign_status` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| PUT | `/api/projects/{project_id}/working-papers/{wp_id}/status` | 更新底稿编制生命周期状态 | `routers/working_paper.py:481` `update_status` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 2 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/sync-procedure` | 底稿状态与审计程序联动 | `routers/wp_relation_router.py:284` `sync_procedure_status` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| GET | `/api/projects/{project_id}/working-papers/{wp_id}/univer-data` | 获取底稿的 Univer IWorkbookData 格式数据（含所有 Sheet、样式、公式） | `routers/wp_editor_router.py:99` `get_univer_data` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/univer-save` | Univer 编辑器保存 — 完整保存链路 | `routers/wp_editor_router.py:126` `save_univer_data` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/upload` | 上传离线编辑的底稿 | `routers/working_paper.py:389` `upload_workpaper` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| POST | `/api/projects/{project_id}/working-papers/{wp_id}/upload-file` | 上传离线编辑后的底稿文件（正式主链路）。 | `routers/working_paper.py:410` `upload_workpaper_file` | check_consol_lock、dedicated_wp_gate、get_current_user、require | 1 |
| GET | `/api/projects/{project_id}/workpaper-summaries/{key}` | 获取底稿摘要（ready=false 时 HTTP 200 + reason） | `routers/workpaper_summaries.py:22` `get_project_workpaper_summary` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/workpaper-summary` | 生成跨企业底稿汇总 | `routers/workpaper_summary.py:37` `generate_summary` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/workpaper-summary/export` | 导出跨企业汇总 Excel | `routers/workpaper_summary.py:56` `export_summary_excel` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/D2/business-pattern-analysis` | D2 业务模式分析 | `routers/wp_business_pattern.py:50` `business_pattern_analysis` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/workpapers/batch-export` | 批量导出 PDF — 逐个转换+ZIP 打包+页眉页脚（Stub） | `routers/wp_batch_ops.py:102` `batch_export_pdf` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/batch-prefill` | 批量预填充 — 并行执行多个底稿的预填充 | `routers/wp_batch_ops.py:54` `batch_prefill` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/batch-structure` | 批量为项目所有底稿生成 structure.json | `routers/wp_structure.py:180` `batch_generate` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/batch-submit` | 退役不写库的假成功入口；旧客户端稳定得到 410。 | `routers/wp_batch_ops.py:139` `batch_submit_review` | get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/cross-refs` |  | `routers/wp_progress.py:41` `get_cross_refs` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/download-pack` | 批量打包下载底稿为 ZIP | `routers/wp_download.py:26` `download_pack` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 0 |
| POST | `/api/projects/{project_id}/workpapers/escalate-to-partner` | 将逾期底稿升级通知合伙人。 | `routers/workpaper_remind.py:83` `escalate_to_partner` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/overdue` |  | `routers/wp_progress.py:30` `get_overdue` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/workpapers/prerequisite-status` | 返回前置底稿状态聚合：``{items: [{wp_code, wp_name, state, conclusion,  | `routers/wp_prerequisite_status.py:134` `get_prerequisite_status` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/workpapers/progress` |  | `routers/wp_progress.py:20` `get_progress` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/workpapers/search` | 底稿全文搜索 | `routers/wp_search.py:22` `search_workpapers` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/workpapers/template-copy` | 跨项目模板复制 | `routers/wp_template_copy_router.py:65` `template_copy` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/actions` | 获取底稿可用的功能行为动作列表 | `routers/wp_functional_actions.py:67` `get_workpaper_actions` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/actions/execute` | 执行底稿功能行为动作（取数→填回 parsed_data） | `routers/wp_functional_actions.py:102` `execute_workpaper_action` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/check-version` | 检查版本冲突 | `routers/wp_download.py:104` `check_version` | dedicated_wp_gate、get_current_user、require_project_access(ed | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/cloud-url` | 获取底稿的云端访问 URL（供其他用户直接打开原始文档） | `routers/wp_download.py:150` `get_cloud_url` | dedicated_wp_gate、get_current_user、require_project_access(re | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/dependencies` | 检查底稿的前置依赖是否已完成 | `routers/wp_dependencies.py:25` `get_wp_dependencies` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/download-file` | 单个底稿下载 | `routers/wp_download.py:67` `download_single` | dedicated_wp_gate、get_current_user、get_current_user_stream、r | 0 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/f2/impairment-analysis` | F-F12 跌价准备分析（确定性 CAS1 孰低法，同 G-ECL 模式 is_llm_stub=False） | `routers/wp_f2_impairment.py:72` `f2_impairment_analysis` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/f2/valuation-sample` | F-F11 自动抽样：按金额分层抽取 sample_size 笔明细行。 | `routers/wp_f2_valuation.py:170` `f2_valuation_sample` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/fine-extract` | 使用精细化规则从底稿提取结构化数据 | `routers/wp_fine_rules.py:90` `fine_extract` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/g/ecl-calc` | G-F5 ECL 三阶段模型计算（IFRS 9 / CAS 22） | `routers/wp_g_ecl.py:149` `g_ecl_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/g/fair-value-test` | G-F4 公允价值层级测试（Level 1/2/3） | `routers/wp_g_fair_value.py:290` `g_fair_value_test` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/g1/classification-check` | G-F11 金融资产分类辅助（CAS 22 / IFRS 9 决策树） | `routers/wp_g_classification.py:139` `g1_classification_check` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/h1/depreciation-calc` | H-F11 折旧自动测算引擎：4 种方法计算月度折旧序列。 | `routers/wp_h_depreciation.py:295` `h1_depreciation_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/h1/impairment-analysis` | H-F12 减值 DCF 模型辅助分析（LLM stub 实现） | `routers/wp_h_impairment.py:142` `h1_impairment_analysis` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/i1/amortization-calc` | I1 无形资产摊销自动测算（剩余年限法 / 工作量法） | `routers/wp_i_amortization.py:190` `i1_amortization_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/i2/capitalization-check` | I-F5 开发支出资本化时点判断（CAS 6 五条件） | `routers/wp_i_capitalization.py:163` `i2_capitalization_check` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/i4/amortization-calc` | I4 长期待摊费用摊销自动测算（直线法 / 工作量法） | `routers/wp_i_amortization.py:208` `i4_amortization_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/j1/payroll-calc` | J-F7 薪酬计提引擎：计算月度明细 + 年度汇总。 | `routers/wp_j_payroll_calc.py:218` `j1_payroll_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/j3/share-payment-calc` | J-F8 股份支付公允价值计算（Black-Scholes） | `routers/wp_j_share_payment.py:215` `j3_share_payment_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/k11/impairment-summary` | K-F8 K11 资产减值损失跨循环汇总 | `routers/wp_k_impairment_summary.py:205` `k11_impairment_summary` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/k8/expense-analysis` | K-F7 销售/管理费用 3 维度分析 | `routers/wp_k_expense_analysis.py:508` `k_expense_analysis` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/l/interest-calc` | L-F7 利息自动测算引擎：3 种计息基准 × 3 种复利频率。 | `routers/wp_l_interest_calc.py:243` `l_interest_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/l5/bond-amortization` | L-F8 应付债券摊余成本引擎：实际利率法 + 收敛性尾差调整。 | `routers/wp_l_bond_amortization.py:187` `l_bond_amortization` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/m6/equity-movement` | M-F7 权益变动表引擎：6 列变动汇总 + apply_to_sheet + RBAC。 | `routers/wp_m_equity_movement.py:161` `m_equity_movement` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/n5/income-tax-calc` | N-F7 所得税费用测算引擎：税率调节表 + 递延调整 + apply_to_sheet + RBAC。 | `routers/wp_n_income_tax_calc.py:242` `n_income_tax_calc` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/prior-year` | 获取上年同底稿的元数据和文件 URL | `routers/workpaper_prior_year.py:24` `get_prior_year` | dedicated_wp_gate、get_current_user | 6 |
| PATCH | `/api/projects/{project_id}/workpapers/{wp_id}/procedure-trim` | 执行程序裁剪或恢复操作。 | `routers/wp_procedure_trim.py:34` `patch_procedure_trim` | dedicated_wp_gate、get_current_user、require_role | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/procedure-trim/history` | 获取裁剪操作历史（所有角色可见）。 | `routers/wp_procedure_trim.py:118` `get_procedure_trim_history` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/procedure-trim/summary` | 获取裁剪汇总统计（所有角色可见）。 | `routers/wp_procedure_trim.py:100` `get_procedure_trim_summary` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/procedures` | 获取程序清单（含裁剪状态） | `routers/wp_procedures.py:60` `get_procedures` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/procedures/copy-from-prior` | 从上年复制程序清单 | `routers/wp_procedures.py:145` `copy_from_prior` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/procedures/custom` | 新增自定义程序 | `routers/wp_procedures.py:124` `create_custom_procedure` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| PATCH | `/api/projects/{project_id}/workpapers/{wp_id}/procedures/{proc_id}/complete` | 标记程序完成 | `routers/wp_procedures.py:76` `complete_procedure` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| PATCH | `/api/projects/{project_id}/workpapers/{wp_id}/procedures/{proc_id}/trim` | 裁剪程序（经理/合伙人权限） | `routers/wp_procedures.py:96` `trim_procedure` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/remind` | 催办底稿编制人。 | `routers/workpaper_remind.py:47` `remind_workpaper` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/requirements` | 获取底稿的程序要求聚合信息 | `routers/workpaper_requirements.py:24` `get_requirements` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/structure` | 获取底稿的 structure.json（缓存优先，支持强制重建） | `routers/wp_structure.py:26` `get_structure` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/structure` | 保存编辑后的 structure.json 并回写 Excel | `routers/wp_structure.py:64` `save_structure` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/structure/addresses` | 获取底稿中可引用的地址坐标列表 | `routers/wp_structure.py:206` `get_addresses` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/structure/html` | 获取底稿的 HTML 预览（支持分页） | `routers/wp_structure.py:144` `get_structure_html` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/structure/rebuild` | 强制从 Excel 重建 structure.json（丢弃缓存） | `routers/wp_structure.py:119` `rebuild_structure` | dedicated_wp_gate、get_current_user、require_project_access(ed | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/template-file` | 获取底稿 xlsx 文件（供 Univer importXLSX 加载） | `routers/wp_template_files.py:76` `get_workpaper_xlsx` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/available-templates` | 列出所有可用模板（供前端展示） | `routers/wp_template_files.py:164` `get_available_templates` | dedicated_wp_gate、get_current_user、require_project_access(re | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/docx-to-json` | 将底稿 docx 模板转换为 Univer Doc IDocumentData JSON snapshot。 | `routers/wp_template_docx.py:30` `convert_docx_to_univer_doc` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/init` | 手动触发从模板初始化底稿文件（覆盖已有文件） | `routers/wp_template_files.py:140` `init_from_template` | dedicated_wp_gate、get_current_user、require_project_access(ed | 2 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/sheet/{sheet_name}` | proposal-remaining-18 D-1：按需加载单个 sheet 完整数据 | `routers/wp_template_files.py:245` `get_single_sheet_data` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/to-json` | 将 xlsx 转换为 Univer workbook JSON（含格式信息） | `routers/wp_template_xlsx.py:548` `convert_xlsx_to_json` | dedicated_wp_gate、get_current_user、require_project_access(re | 0 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/template-file/xlsx-to-json` | 直接读 storage 中的 xlsx 文件转 Univer JSON。 | `routers/wp_template_xlsx.py:605` `convert_xlsx_storage_to_json` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| POST | `/api/projects/{project_id}/workpapers/{wp_id}/upload-file` | 上传离线编辑的底稿文件 | `routers/wp_download.py:120` `upload_file` | dedicated_wp_gate、get_current_user、require_project_access(ed | 0 |
| POST | `/api/projects/{project_id}/wp-ai/{wp_id}/confirm-explanation` | 确认审计说明并写回工作簿 | `routers/wp_explanation.py:58` `confirm_explanation` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/wp-ai/{wp_id}/generate-explanation` | 生成审计说明草稿 | `routers/wp_explanation.py:32` `generate_explanation` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/wp-ai/{wp_id}/refine-explanation` | 基于用户修改优化草稿 | `routers/wp_explanation.py:82` `refine_explanation` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/wp-ai/{wp_id}/review-content` | AI预审底稿内容 | `routers/wp_explanation.py:106` `review_content` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/wp-cross-refs` | 交叉索引关系（需项目成员权限） | `routers/wp_relation_router.py:88` `list_wp_cross_refs` | dedicated_wp_gate、get_current_user、require_project_access(re | 2 |
| GET | `/api/projects/{project_id}/wp-index` | 底稿索引列表（需项目成员权限） | `routers/wp_relation_router.py:35` `list_wp_index` | dedicated_wp_gate、get_current_user、require_project_access(re | 5 |
| GET | `/api/projects/{project_id}/wp-templates/download-all` | 批量下载全部底稿模板（ZIP，按循环分目录） | `routers/wp_template_download.py:601` `download_all_templates` | get_current_user_stream、require_project_access_stream(readon | 1 |
| GET | `/api/projects/{project_id}/wp-templates/list` | 列出所有可用底稿模板（供树形展示） | `routers/wp_template_download.py:406` `list_all_templates` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/wp-templates/{wp_code}/download` | 下载单个科目的模板文件（从 wp_templates/ 目录） | `routers/wp_template_download.py:45` `download_template_by_code` | get_current_user_stream、require_project_access_stream(readon | 1 |
| GET | `/api/projects/{project_id}/wp-templates/{wp_code}/prefilled-download` | 下载预填充后的 docx 模板（替换公司名/年度/事务所等占位符） | `routers/wp_template_download.py:100` `download_template_prefilled` | get_current_user_stream、require_project_access_stream(readon | 3 |
| GET | `/api/projects/{project_id}/wp-templates/{wp_code}/preview-pdf` | 模板主文件转 PDF 在线预览。 | `routers/wp_template_download.py:658` `preview_template_as_pdf` | get_current_user_stream、require_project_access_stream(readon | 1 |
| GET | `/api/recycle-bin` | 查询回收站中的已删除记录（只含当前用户是成员的项目，admin 全部） | `routers/recycle_bin.py:261` `list_recycle_bin` | get_current_user | 1 |
| POST | `/api/recycle-bin/batch-delete` | 批量永久删除回收站中的记录（不可恢复） | `routers/recycle_bin.py:617` `batch_permanently_delete` | get_current_user | 1 |
| POST | `/api/recycle-bin/empty` | 清空回收站（永久删除所有已软删除的记录，仅管理员；底稿不清除） | `routers/recycle_bin.py:679` `empty_recycle_bin` | get_current_user | 1 |
| GET | `/api/recycle-bin/stats` | 回收站统计（各类型数量；只含当前用户是成员的项目，admin 全部） | `routers/recycle_bin.py:814` `recycle_bin_stats` | get_current_user | 1 |
| DELETE | `/api/recycle-bin/{item_type}/{item_id}` | 永久删除记录（不可恢复） | `routers/recycle_bin.py:532` `permanently_delete` | get_current_user | 2 |
| POST | `/api/recycle-bin/{item_type}/{item_id}/restore` | 恢复已删除的记录 | `routers/recycle_bin.py:421` `restore_item` | get_current_user | 0 |
| POST | `/api/s-estimate/{wp_id}/auto-data` | S 类自动取数：通过 resolver 获取未审数+调整分录，用户可 field_overrides 覆盖. | `routers/s_estimate_calculation.py:317` `s_estimate_auto_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/s-estimate/{wp_id}/export-data` | 导出含当前数据的xlsx（S21-2/S20-unrelated/S20-noSubstance） | `routers/s_estimate_calculation.py:402` `s_estimate_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/s-estimate/{wp_id}/export-template` | 导出空白xlsx模板（S21-2/S20-unrelated/S20-noSubstance） | `routers/s_estimate_calculation.py:369` `s_estimate_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/s-estimate/{wp_id}/import-data` | 导入xlsx解析写入checklist_responses（S21-2/S20动态行明细） | `routers/s_estimate_calculation.py:435` `s_estimate_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/s-estimate/{wp_id}/tb-writeback` | S 类审定金额回写 trial_balance（v2 正数口径）. | `routers/s_estimate_calculation.py:119` `s_estimate_tb_writeback` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/s-estimate/{wp_id}/tb-writeback-batch` | S 类审定金额批量回写（多科目同时写入）. | `routers/s_estimate_calculation.py:222` `s_estimate_tb_writeback_batch` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/s-transaction/{wp_id}/auto-data` | S 类交易型自动取数：通过 resolver 获取未审数+调整分录，用户可 field_overrides 覆盖. | `routers/s_transaction_calculation.py:321` `s_transaction_auto_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/s-transaction/{wp_id}/disclosure-notify` | S4/S5 非经常性损益披露文本更新通知. | `routers/s_transaction_calculation.py:373` `s_transaction_disclosure_notify` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/s-transaction/{wp_id}/tb-writeback` | S 类交易型审定金额回写 trial_balance（v2 正数口径）. | `routers/s_transaction_calculation.py:124` `s_transaction_tb_writeback` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/s-transaction/{wp_id}/tb-writeback-batch` | S 类交易型审定金额批量回写（多科目同时写入）. | `routers/s_transaction_calculation.py:225` `s_transaction_tb_writeback_batch` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/template-library-mgmt/cross-wp-references` | 返回 cross_wp_references.json 全部规则（数量动态读取）。 | `routers/template_library_mgmt.py:288` `get_cross_wp_references` | get_current_user | 1 |
| PUT | `/api/template-library-mgmt/cross-wp-references/{ref_id}` | 拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。 | `routers/template_library_mgmt.py:306` `reject_cross_wp_references_mutation` | — | 1 |
| GET | `/api/template-library-mgmt/formula-acnr-migration` | 模板库预设公式引用 ACNR 迁移 Ledger（Req 24.3/24.4）。 | `routers/template_library_mgmt.py:237` `get_formula_acnr_migration` | get_current_user | 1 |
| GET | `/api/template-library-mgmt/formula-coverage` | 公式覆盖率统计： | `routers/template_library_mgmt.py:351` `get_formula_coverage` | get_current_user | 1 |
| GET | `/api/template-library-mgmt/prefill-formulas` | 返回 prefill_formula_mapping.json 全部映射（数量动态读取）。 | `routers/template_library_mgmt.py:214` `get_prefill_formulas` | get_current_user | 1 |
| DELETE | `/api/template-library-mgmt/prefill-formulas/{wp_code}` | 拒绝删除（D13 ADR + Property 17）。 | `routers/template_library_mgmt.py:271` `reject_prefill_formulas_delete` | — | 1 |
| PUT | `/api/template-library-mgmt/prefill-formulas/{wp_code}` | 拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。 | `routers/template_library_mgmt.py:258` `reject_prefill_formulas_mutation` | — | 1 |
| POST | `/api/template-library-mgmt/seed-all` | 一键加载全部种子（D15 SAVEPOINT 边界，每个 seed 独立事务）。 | `routers/template_library_mgmt.py:943` `seed_all` | get_current_user、require_role | 1 |
| GET | `/api/template-library-mgmt/seed-status` | 各种子数据加载状态（运行时聚合，不硬编码任何条目数）。 | `routers/template_library_mgmt.py:604` `get_seed_status` | get_current_user | 1 |
| GET | `/api/template-library-mgmt/version-info` | 返回版本标识 + seed_load_history 最近 N 条记录（按 loaded_at DESC）。 | `routers/template_library_mgmt.py:1036` `get_version_info` | get_current_user | 1 |
| GET | `/api/template-library/available` | 获取可用模板列表（事务所默认 + 集团定制） | `routers/template_library.py:35` `get_available_templates` | get_current_user | 1 |
| GET | `/api/template-library/firm` | 列出事务所默认模板 | `routers/template_library.py:49` `list_firm_templates` | get_current_user | 1 |
| POST | `/api/template-library/group` | 从事务所模板派生集团定制模板 | `routers/template_library.py:64` `create_group_template` | get_current_user | 1 |
| GET | `/api/template-library/group/{group_id}` | 列出集团定制模板 | `routers/template_library.py:85` `list_group_templates` | get_current_user | 2 |
| POST | `/api/template-library/projects/{project_id}/pull/{template_id}` | 拉取模板文件到项目目录 | `routers/template_library.py:133` `pull_template` | get_current_user | 1 |
| POST | `/api/template-library/projects/{project_id}/select` | 为项目选择模板 | `routers/template_library.py:101` `select_template` | get_current_user | 1 |
| GET | `/api/template-library/projects/{project_id}/templates` | 获取项目已选择的模板 | `routers/template_library.py:122` `get_project_templates` | get_current_user | 1 |
| GET | `/api/template-sets` | 模板集列表 | `routers/wp_template.py:185` `list_template_sets` | get_current_user | 1 |
| POST | `/api/template-sets` | 创建模板集 | `routers/wp_template.py:209` `create_template_set` | get_current_user | 1 |
| POST | `/api/template-sets/seed` | 幂等初始化内置模板集（全局数据，只许 admin / partner；启动任务已自动初始化，同种子一键加载 D7） | `routers/wp_template.py:254` `seed_template_sets` | get_current_user、require_role | 2 |
| GET | `/api/template-sets/{set_id}` | 模板集详情 | `routers/wp_template.py:195` `get_template_set` | get_current_user | 2 |
| PUT | `/api/template-sets/{set_id}` | 更新模板集 | `routers/wp_template.py:229` `update_template_set` | get_current_user | 2 |
| GET | `/api/templates` | 模板列表（支持按循环、准则筛选） | `routers/wp_template.py:112` `list_templates` | get_current_user | 1 |
| POST | `/api/templates` | 上传模板文件（MVP: 仅保存元数据） | `routers/wp_template.py:91` `upload_template` | get_current_user | 1 |
| GET | `/api/templates/{code}` | 获取模板详情（默认最新版本） | `routers/wp_template.py:128` `get_template` | get_current_user | 1 |
| POST | `/api/templates/{code}/versions` | 创建新版本 | `routers/wp_template.py:143` `create_version` | get_current_user | 1 |
| DELETE | `/api/templates/{template_id}` | 删除模板（校验无引用）。模板库是全平台共用的，删除只许管理员。 | `routers/wp_template.py:164` `delete_template` | get_current_user、require_role | 1 |
| PUT | `/api/users/{user_id}/language` | 设置用户语言偏好（本人或 admin；原先任何登录用户都能改别人的语言） | `routers/i18n.py:58` `set_user_language` | get_current_user | 1 |
| GET | `/api/working-papers/{wp_id}/versions/search` | 历史版本搜索 — 在快照 + 当前 parsed_data 中模糊匹配关键词 | `routers/wp_version_search.py:31` `search_workpaper_versions` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/batch-refresh` | 批量刷新底稿取数：对 wp_ids 逐个执行行名对齐 + 自动确认。 | `routers/row_name_alignment_router.py:272` `batch_refresh` | dedicated_wp_gate、get_current_user | 6 |
| GET | `/api/workpapers/cycle-prerequisites/{cycle_code}` | 获取指定循环的前置依赖配置。 | `routers/wp_step_mapping.py:458` `get_cycle_prerequisites` | dedicated_wp_gate、get_current_user | 449 |
| GET | `/api/workpapers/dependency-graph` | 获取全部底稿依赖关系图谱（供前端 SVG 渲染圆形依赖图） | `routers/wp_step_mapping.py:300` `get_dependency_graph` | dedicated_wp_gate、get_current_user | 6 |
| POST | `/api/workpapers/draft-refresh` | 全局一键刷新统一入口（合伙人专属，Global_Refresh，公式管理库 Req 1）。 | `routers/draft_refresh.py:79` `one_click_draft_refresh` | get_current_user、require_role | 6 |
| POST | `/api/workpapers/draft-refresh/{run_id}/rollback` | 回滚指定 Execution_Run（合伙人专属）。 | `routers/draft_refresh.py:204` `rollback_draft_refresh` | get_current_user、require_role | 6 |
| GET | `/api/workpapers/field-overrides` | 获取指定 scope 下所有覆盖值（项目成员可读；原先只校验登录，可读任意项目） | `routers/wp_field_overrides.py:70` `get_field_overrides` | get_current_user | 12 |
| POST | `/api/workpapers/field-overrides` | Upsert 单个覆盖值（项目 edit 级；程序表行只能写派给本人的，spec procedure-trim-gene | `routers/wp_field_overrides.py:84` `set_field_override` | get_current_user | 12 |
| POST | `/api/workpapers/field-overrides/batch` | 批量 upsert 覆盖值：一次鉴权、每项一个保存点、一次提交；不能写的项逐条回报原因（不吞错）。 | `routers/wp_field_overrides.py:117` `set_field_overrides_batch` | get_current_user | 19 |
| POST | `/api/workpapers/generate-from-index` | 手动从 wp_index 幂等生成 working_paper。 | `routers/wp_render_config.py:528` `generate_workpaper_from_index` | dedicated_wp_gate、get_current_user | 5 |
| GET | `/api/workpapers/i4/peer-ltpa-industries` |  | `routers/wp_render_strategies/_i4_peer_policies.py:77` `list_peer_ltpa_industries` | dedicated_wp_gate、get_current_user | 18 |
| GET | `/api/workpapers/i4/peer-ltpa-policies` |  | `routers/wp_render_strategies/_i4_peer_policies.py:40` `get_peer_ltpa_policies` | dedicated_wp_gate、get_current_user | 19 |
| GET | `/api/workpapers/index-resolve/{wp_code}` | 解析底稿实例 — 转发至 ACNR resolve_instance（唯一 wp_id 出口）。 | `routers/wp_workpaper_index_resolve.py:35` `resolve_workpaper_index` | get_current_user | 450 |
| GET | `/api/workpapers/mapping-rules` | 获取映射规则配置（供前端展示规则说明） | `routers/wp_step_mapping.py:116` `get_mapping_rules` | dedicated_wp_gate、get_current_user | 6 |
| POST | `/api/workpapers/mapping-rules/custom` | 用户添加自定义映射规则 | `routers/wp_step_mapping.py:130` `add_custom_rule` | dedicated_wp_gate、get_current_user | 19 |
| GET | `/api/workpapers/refresh-scopes` | 列出全局刷新可勾选范围项（合伙人专属，Req 20）。 | `routers/refresh_scopes.py:43` `list_refresh_scopes` | get_current_user、require_role | 6 |
| GET | `/api/workpapers/render-registry` | 返回完整注册表（含 render_types + entries） | `routers/wp_render_registry.py:31` `get_render_registry` | — | 6 |
| GET | `/api/workpapers/render-registry/{wp_code}` | 查找单个 wp_code 的注册信息 — 转发至 ACNR resolve 统一出口。 | `routers/wp_render_registry.py:40` `get_registry_entry` | — | 449 |
| GET | `/api/workpapers/template-list` | 返回全部模板列表，按项目业务分类标注 applicable 状态。 | `routers/wp_template_list.py:32` `get_template_list` | get_current_user、require_project_access(readonly) | 5 |
| GET | `/api/workpapers/template-list/reference` | 返回业务分类参考数据（A/B/C 定义+质控措施） | `routers/wp_template_list.py:62` `get_category_reference` | get_current_user | 19 |
| GET | `/api/workpapers/trace` | 报表/附注/底稿溯源端点。 | `routers/wp_trace.py:58` `trace_workpaper` | get_current_user、require_project_access(readonly) | 6 |
| POST | `/api/workpapers/{wp_id}/a176/generate-docx` | 结构化→Word：从 checklist_responses 生成 docx 文件 | `routers/a176_docx_sync.py:23` `a176_generate_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/a176/sync-from-docx` | Word→结构化：从项目存储的 docx 解析内容回写到 checklist_responses | `routers/a176_docx_sync.py:50` `a176_sync_from_docx` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/audit-determination/publish-to-tb` | 把审定表审定数**显式发布**到 trial_balance（P0-项3）。 | `routers/wp_html_save.py:695` `publish_determination_to_tb` | dedicated_wp_gate、get_current_user | 75 |
| GET | `/api/workpapers/{wp_id}/audit-flow-graph` | 获取程序表的审计逻辑流程图数据。 | `routers/wp_audit_flow_graph.py:107` `get_audit_flow_graph` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/audit-sheet-refresh` | 一键刷新（模块/循环级，Module_Refresh）：从四表库（试算表/辅助余额表）预填充审定表/明细表数据。 | `routers/wp_render_config.py:380` `refresh_audit_sheet_from_ledger` | dedicated_wp_gate、get_current_user、require_wp_edit_permissio | 20 |
| GET | `/api/workpapers/{wp_id}/c24-journal/export-data` | 导出当前已导入的分录数据xlsx。 | `routers/wp_render_strategies/_c24_import_export.py:210` `c24_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/c24-journal/export-template` | 导出空白分录模板xlsx（含表头+编制说明，无数据行）。 | `routers/wp_render_strategies/_c24_import_export.py:172` `c24_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/c24-journal/import-data` | 解析上传的分录xlsx，校验格式，写入 checklist_responses。 | `routers/wp_render_strategies/_c24_import_export.py:256` `c24_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/capability-assert` | 按当前认证用户和数据库归属重新计算能力，不信任客户端 snapshot 决策。 | `routers/wp_capability_snapshot.py:91` `assert_capability_action` | dedicated_wp_gate、get_current_user | 19 |
| GET | `/api/workpapers/{wp_id}/capability-snapshot` | 按认证用户与数据库归属签发能力快照；不信任客户端角色/成员/可见性标志。 | `routers/wp_capability_snapshot.py:66` `get_capability_snapshot` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/checklist-responses` | 获取指定底稿的所有核对表填写响应（含稳定版本和集合 ETag）。 | `routers/checklist_responses.py:92` `get_checklist_responses` | dedicated_wp_gate、get_current_user | 354 |
| PUT | `/api/workpapers/{wp_id}/checklist-responses` | 原子批量 UPSERT；可选 if_match 冲突保护，缺省保持 LWW 兼容。 | `routers/checklist_responses.py:140` `batch_save_checklist_responses` | dedicated_wp_gate、get_current_user、require_wp_edit_permissio | 354 |
| PUT | `/api/workpapers/{wp_id}/custom-cells` | 写入自定义底稿单元格（先落 xlsx，再刷投影）。 | `routers/custom_workpaper_cells.py:129` `update_custom_cells` | dedicated_wp_gate、get_current_user | 21 |
| POST | `/api/workpapers/{wp_id}/custom-refresh-projection` | 从 xlsx 重新投影（不改 xlsx）。 | `routers/custom_workpaper_cells.py:256` `refresh_custom_projection_endpoint` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/d2/derecognition-judge` | 针对终止确认某一步骤，结合证据文本与知识库引用给出 AI 判断建议（仅建议，人工确认为准）。 | `routers/wp_render_strategies/_d2_derecognition.py:139` `d2_derecognition_judge` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/derecognition-ocr` | 上传保理合同/协议附件 → OCR 识别文本（供 AI 判断与人工核对）；文件先入附件表并关联本底稿，识别结果写回附件。 | `routers/wp_render_strategies/_d2_derecognition.py:52` `d2_derecognition_ocr` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/export-data` | 导出含当前数据的xlsx | `routers/wp_render_strategies/_d2_import_export.py:1555` `export_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/export-template` | 导出空白xlsx模板（含表头+格式） | `routers/wp_render_strategies/_d2_import_export.py:1498` `export_template` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/import-aux-balance` | 从 `tb_aux_balance`（科目由 BS-006 报表映射解析，兜底 1122）按客户维度归集导入 D2-2. | `routers/wp_render_strategies/_d2_import_export.py:1718` `d2_import_aux_balance` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/import-data` | 解析xlsx回写checklist_responses | `routers/wp_render_strategies/_d2_import_export.py:1606` `import_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/vc-export-data` | 按前端当前双区数组导出 D2-7 凭证检查表数据。 | `routers/wp_render_strategies/_d2_vc_import_export.py:314` `export_voucher_check_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/vc-export-template` | 导出 D2-7 凭证检查表空白模板（两个标准工作表）。 | `routers/wp_render_strategies/_d2_vc_import_export.py:290` `export_voucher_check_template` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d2/vc-import-data` | 解析 D2-7 双区 xlsx 并返回可导入行，不直接写入 checklist。 | `routers/wp_render_strategies/_d2_vc_import_export.py:344` `import_voucher_check_data` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d3/export-data` | 导出当前数据xlsx | `routers/wp_render_strategies/_d3_import_export.py:239` `d3_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d3/export-template` | 导出空白模板xlsx（含表头+格式，无数据行） | `routers/wp_render_strategies/_d3_import_export.py:192` `d3_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d3/import-aux-balance` | 从 `tb_aux_balance`（科目由 BS-046 报表映射解析，兜底 2203）按往来单位维度归集导入 D3- | `routers/wp_render_strategies/_d3_import_export.py:447` `d3_import_aux_balance` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/d3/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d3_import_export.py:315` `d3_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d4/contract-ocr` | 上传合同附件，OCR识别并提取字段；文件先入附件表并关联本底稿（spec attachment-evidence-int | `routers/wp_render_strategies/_d4_contract_ocr.py:138` `d4_contract_ocr` | dedicated_wp_gate、get_current_user | 67 |
| POST | `/api/workpapers/{wp_id}/d4/export-data` | 导出当前数据xlsx | `routers/wp_render_strategies/_d4_import_export.py:555` `d4_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d4/export-template` | 导出空白模板xlsx（含表头+格式+编制说明，无数据行） | `routers/wp_render_strategies/_d4_import_export.py:445` `d4_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d4/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d4_import_export.py:1206` `d4_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d5/export-data` | 导出当前数据xlsx | `routers/wp_render_strategies/_d5_import_export.py:152` `d5_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d5/export-template` | 导出空白模板xlsx（含表头+格式+编制说明，无数据行） | `routers/wp_render_strategies/_d5_import_export.py:104` `d5_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d5/import-aux-balance` | 从 `tb_aux_balance`（科目由 BS-007 报表映射解析，兜底 1124）按明细维度归集导入 D5-2. | `routers/wp_render_strategies/_d5_import_export.py:319` `d5_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d5/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d5_import_export.py:213` `d5_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d6/export-data` | 导出当前数据xlsx | `routers/wp_render_strategies/_d6_import_export.py:180` `d6_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d6/export-template` | 导出空白模板xlsx（含表头+格式+编制说明，无数据行） | `routers/wp_render_strategies/_d6_import_export.py:138` `d6_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d6/import-aux-balance` | 从 `tb_aux_balance`（科目由 BS-011 报表映射解析，兜底 1141）按客户/合同维度归集导入 D6 | `routers/wp_render_strategies/_d6_import_export.py:366` `d6_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d6/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d6_import_export.py:243` `d6_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d7/export-data` | 导出当前数据xlsx | `routers/wp_render_strategies/_d7_import_export.py:370` `d7_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d7/export-template` | 导出空白模板xlsx（含表头+格式+编制说明，无数据行） | `routers/wp_render_strategies/_d7_import_export.py:319` `d7_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d7/import-aux-balance` | 从 `tb_aux_balance`（科目由 BS-047 报表映射解析，兜底 2205）按往来单位维度归集导入 D7- | `routers/wp_render_strategies/_d7_import_export.py:573` `d7_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/d7/import-data` | 解析上传xlsx，校验格式，写入 checklist_responses | `routers/wp_render_strategies/_d7_import_export.py:454` `d7_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/account-list-ocr` | 上传《已开立银行结算账户清单》，OCR + AI 提取账户行供 E1-10 确认回填。 | `routers/wp_render_strategies/_e1_account_list_ocr.py:125` `e1_account_list_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/commit-ocr` | 上传银行账户完整性承诺函，OCR + AI 提取 E1-11 字段与账户清单。 | `routers/wp_render_strategies/_e1_commit_ocr.py:145` `e1_commit_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/credit-ocr` | 上传企业信用报告打印件，OCR + AI 提取 E1-18 表单字段。 | `routers/wp_render_strategies/_e1_credit_ocr.py:88` `e1_credit_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/cutoff-ocr` | 上传凭证影像，OCR + AI 提取截止测试所需字段；文件先入附件表并关联本底稿，识别结果写回附件。 | `routers/wp_render_strategies/_e1_cutoff_ocr.py:106` `e1_cutoff_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/export-data` |  | `routers/wp_render_strategies/_e1_import_export.py:479` `e1_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/export-template` |  | `routers/wp_render_strategies/_e1_import_export.py:469` `e1_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/import-data` |  | `routers/wp_render_strategies/_e1_import_export.py:519` `e1_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/large-check-ocr` | 上传收支单据/审批影像，OCR + AI 提取大额收支检查所需字段；文件先入附件表并关联本底稿，识别结果写回附件。 | `routers/wp_render_strategies/_e1_large_check_ocr.py:113` `e1_large_check_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/e1/statement-ocr` | 上传银行对账单/流水，OCR + AI 提取明细供 E1-31 确认回填。 | `routers/wp_render_strategies/_e1_statement_ocr.py:162` `e1_statement_ocr` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/workpapers/{wp_id}/export-review-xlsx` |  | `routers/a21_review.py:167` `export_review_xlsx` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/export-template` | 导出底稿对应的原始 xlsx 模板文件 — 流式路径：响应体发送前已释放 DB 会话。 | `routers/wp_render_config.py:565` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 21 |
| POST | `/api/workpapers/{wp_id}/f0/export-data` |  | `routers/wp_render_strategies/_f0_import_export.py:421` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f0/export-template` |  | `routers/wp_render_strategies/_f0_import_export.py:409` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f0/import-data` |  | `routers/wp_render_strategies/_f0_import_export.py:437` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f1/export-data` |  | `routers/wp_render_strategies/_f1_import_export.py:574` `f1_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f1/export-template` |  | `routers/wp_render_strategies/_f1_import_export.py:555` `f1_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f1/import-aux-balance` | 从 tb_aux_balance（科目 1123，按往来单位维度）归集导入 F1-2 明细表。 | `routers/wp_render_strategies/_f1_import_export.py:1000` `f1_import_aux_balance` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/f1/import-data` |  | `routers/wp_render_strategies/_f1_import_export.py:602` `f1_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-spe/contract-ocr` |  | `routers/wp_render_strategies/_f2_special_contract_ocr.py:133` `f2_spe_contract_ocr` | dedicated_wp_gate、get_current_user | 3 |
| POST | `/api/workpapers/{wp_id}/f2-spe/export-data` |  | `routers/wp_render_strategies/_f2_special_import_export.py:1118` `f2_spe_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-spe/export-template` |  | `routers/wp_render_strategies/_f2_special_import_export.py:1106` `f2_spe_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-spe/import-data` |  | `routers/wp_render_strategies/_f2_special_import_export.py:1158` `f2_spe_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-st/contract-ocr` |  | `routers/wp_render_strategies/_f2_stocktake_contract_ocr.py:134` `f2_stocktake_contract_ocr` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/f2-st/export-data` |  | `routers/wp_render_strategies/_f2_stocktake_import_export.py:269` `f2_st_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-st/export-template` |  | `routers/wp_render_strategies/_f2_stocktake_import_export.py:257` `f2_st_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-st/import-data` |  | `routers/wp_render_strategies/_f2_stocktake_import_export.py:286` `f2_st_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-st/plan-sync-from-oo` | OnlyOffice → 结构化：解析 docx 缓存写回 F2-22-fields。 | `routers/wp_render_strategies/_f2_stocktake_plan_sync.py:227` `f2_st_plan_sync_from_oo` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-st/plan-sync-to-oo` | 结构化 → OnlyOffice：用 F2-22-fields 填充 docx 缓存。 | `routers/wp_render_strategies/_f2_stocktake_plan_sync.py:191` `f2_st_plan_sync_to_oo` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-st/summary-sync-from-oo` | OnlyOffice → 结构化：解析 docx 缓存写回 F2-23-fields。 | `routers/wp_render_strategies/_f2_stocktake_summary_sync.py:218` `f2_st_summary_sync_from_oo` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-st/summary-sync-to-oo` | 结构化 → OnlyOffice：用 F2-23-fields 填充 docx 缓存。 | `routers/wp_render_strategies/_f2_stocktake_summary_sync.py:182` `f2_st_summary_sync_to_oo` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-val/contract-ocr` |  | `routers/wp_render_strategies/_f2_valuation_contract_ocr.py:88` `f2_valuation_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f2-val/export-data` |  | `routers/wp_render_strategies/_f2_valuation_import_export.py:340` `f2_val_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-val/export-template` |  | `routers/wp_render_strategies/_f2_valuation_import_export.py:328` `f2_val_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2-val/import-data` |  | `routers/wp_render_strategies/_f2_valuation_import_export.py:357` `f2_val_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2/contract-ocr` |  | `routers/wp_render_strategies/_f2_contract_ocr.py:110` `f2_contract_ocr` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/f2/export-data` |  | `routers/wp_render_strategies/_f2_import_export.py:591` `f2_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2/export-template` |  | `routers/wp_render_strategies/_f2_import_export.py:571` `f2_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f2/import-data` |  | `routers/wp_render_strategies/_f2_import_export.py:616` `f2_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/f3/contract-ocr` | 上传票据附件，OCR识别并提取相关字段；可选回流已关联附件证据链。 | `routers/wp_render_strategies/_f3_contract_ocr.py:177` `f3_contract_ocr` | dedicated_wp_gate、get_current_user | 3 |
| POST | `/api/workpapers/{wp_id}/f3/export-data` |  | `routers/wp_render_strategies/_f3_import_export.py:233` `f3_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f3/export-template` |  | `routers/wp_render_strategies/_f3_import_export.py:221` `f3_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f3/import-data` |  | `routers/wp_render_strategies/_f3_import_export.py:250` `f3_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f4/contract-ocr` | 识别F4-5/F4-7/F4-8/F4-9附件并返回待用户预览、编辑和确认的字段。 | `routers/wp_render_strategies/_f4_contract_ocr.py:253` `f4_contract_ocr` | dedicated_wp_gate、get_current_user | 5 |
| POST | `/api/workpapers/{wp_id}/f4/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/f4/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/f4/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f5/contract-ocr` | 上传出库单附件，OCR识别并提取数量字段；可选回流已关联附件证据链。 | `routers/wp_render_strategies/_f5_contract_ocr.py:89` `f5_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/f5/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/f5/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/f5/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g0/export-data` |  | `routers/wp_render_strategies/_g0_confirmation_import_export.py:338` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g0/export-template` |  | `routers/wp_render_strategies/_g0_confirmation_import_export.py:324` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g0/import-data` |  | `routers/wp_render_strategies/_g0_confirmation_import_export.py:357` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g1/contract-ocr` | 上传合同/协议附件，OCR识别并提取衍生变量；可选回流已关联附件证据链。 | `routers/wp_render_strategies/_g1_contract_ocr.py:98` `g1_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g1/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g1/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g1/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g10/contract-ocr` |  | `routers/wp_render_strategies/_g10_contract_ocr.py:82` `g10_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g10/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g10/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g10/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g10/validate-formulas` |  | `routers/wp_render_strategies/_g10_trading_financial_liabilities_validate.py:35` `validate_g10_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g11/contract-ocr` |  | `routers/wp_render_strategies/_g11_contract_ocr.py:81` `g11_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g11/export-data` |  | `routers/wp_render_strategies/_g11_investment_income_import_export.py:471` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g11/export-template` |  | `routers/wp_render_strategies/_g11_investment_income_import_export.py:450` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g11/import-data` |  | `routers/wp_render_strategies/_g11_investment_income_import_export.py:510` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g11/save-adjudication` |  | `routers/wp_render_strategies/_g11_investment_income_validate.py:168` `save_g11_adjudication` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g11/validate-formulas` |  | `routers/wp_render_strategies/_g11_investment_income_validate.py:139` `validate_g11_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g12/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g12/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g12/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g13/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g13/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g13/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g14/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g14/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g14/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g2/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g2/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g2/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g3/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g3/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g3/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-ecl/export-data` |  | `routers/wp_render_strategies/_g4_bond_investment_ecl_import_export.py:1072` `g4_ecl_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-ecl/export-template` |  | `routers/wp_render_strategies/_g4_bond_investment_ecl_import_export.py:1034` `g4_ecl_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-ecl/import-data` |  | `routers/wp_render_strategies/_g4_bond_investment_ecl_import_export.py:1119` `g4_ecl_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-main/export-data` |  | `routers/wp_render_strategies/_g4_bond_investment_main_import_export.py:500` `g4_main_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-main/export-template` |  | `routers/wp_render_strategies/_g4_bond_investment_main_import_export.py:442` `g4_main_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-main/import-data` |  | `routers/wp_render_strategies/_g4_bond_investment_main_import_export.py:562` `g4_main_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-sppi/export-data` |  | `routers/wp_render_strategies/_g4_bond_investment_sppi_import_export.py:755` `g4_sppi_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-sppi/export-template` |  | `routers/wp_render_strategies/_g4_bond_investment_sppi_import_export.py:711` `g4_sppi_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g4-sppi/import-data` |  | `routers/wp_render_strategies/_g4_bond_investment_sppi_import_export.py:802` `g4_sppi_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g5/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g5/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g5/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-ecl/export-data` | 导出已填写数据. | `routers/wp_render_strategies/_g6_other_bond_investment_ecl_import_export.py:1353` `g6_ecl_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-ecl/export-template` | 导出空模板（含表头+编制说明）. | `routers/wp_render_strategies/_g6_other_bond_investment_ecl_import_export.py:1312` `g6_ecl_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-ecl/import-data` | 导入xlsx数据. | `routers/wp_render_strategies/_g6_other_bond_investment_ecl_import_export.py:1462` `g6_ecl_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-main/export-data` |  | `routers/wp_render_strategies/_g6_other_bond_investment_main_import_export.py:482` `g6_main_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-main/export-template` |  | `routers/wp_render_strategies/_g6_other_bond_investment_main_import_export.py:447` `g6_main_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-main/import-data` |  | `routers/wp_render_strategies/_g6_other_bond_investment_main_import_export.py:516` `g6_main_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-sppi/export-data` |  | `routers/wp_render_strategies/_g6_other_bond_investment_sppi_import_export.py:1599` `g6_sppi_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-sppi/export-template` |  | `routers/wp_render_strategies/_g6_other_bond_investment_sppi_import_export.py:1525` `g6_sppi_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g6-sppi/import-data` |  | `routers/wp_render_strategies/_g6_other_bond_investment_sppi_import_export.py:1667` `g6_sppi_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-equity-method/export-data` | 导出数据：G7-4按原底稿单sheet，其余按既有宽表规则。 | `routers/wp_render_strategies/_g7_long_term_equity_method_import_export.py:1741` `g7_equity_method_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-equity-method/export-template` | 导出空模板：G7-4按原底稿单sheet，其余按既有宽表规则。 | `routers/wp_render_strategies/_g7_long_term_equity_method_import_export.py:1709` `g7_equity_method_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-equity-method/import-data` | 导入数据：多sheet或宽表(G7-4/G7-13/G7-14/G7-16) / 单sheet(G7-5/G7-15/G | `routers/wp_render_strategies/_g7_long_term_equity_method_import_export.py:1804` `g7_equity_method_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-main/export-data` | 导出数据：G7-2(三业务区多sheet含数据) / G7-3(单sheet含数据)。 | `routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py:629` `g7_main_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g7-main/export-template` | 导出空模板：G7-2(三业务区多sheet) / G7-3(单sheet)。 | `routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py:601` `g7_main_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g7-main/import-data` | 导入数据：G7-2(系统三业务区或原始工作簿) / G7-3(单sheet)。 | `routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py:657` `g7_main_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g7-main/validate-detail` | 校验G7-2三业务区公式链；wp_id用于路由归属和权限上下文。 | `routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py:589` `g7_main_validate_detail` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g7-sub/export-data` | 导出数据：G7-8/G7-9/G7-10/G7-12/G7-18按业务区段拆分。 | `routers/wp_render_strategies/_g7_long_term_equity_subsidiary_import_export.py:1721` `g7_sub_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-sub/export-template` | 导出空模板：G7-8/G7-9/G7-10/G7-12/G7-18按业务区段拆分。 | `routers/wp_render_strategies/_g7_long_term_equity_subsidiary_import_export.py:1687` `g7_sub_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7-sub/import-data` | 导入数据：G7-8/G7-9/G7-10/G7-12/G7-18支持多区段工作簿。 | `routers/wp_render_strategies/_g7_long_term_equity_subsidiary_import_export.py:1762` `g7_sub_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g7/import-aux-balance` | 从 tb_aux_balance（科目 1511，按被投资单位维度）归集导入 G7-2 明细表。 | `routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py:903` `g7_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g8/contract-ocr` |  | `routers/wp_render_strategies/_g8_contract_ocr.py:82` `g8_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g8/export-data` |  | `routers/wp_render_strategies/_g8_other_equity_instruments_import_export.py:544` `g8_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g8/export-template` |  | `routers/wp_render_strategies/_g8_other_equity_instruments_import_export.py:506` `g8_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g8/import-data` |  | `routers/wp_render_strategies/_g8_other_equity_instruments_import_export.py:580` `g8_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g8/validate-formulas` |  | `routers/wp_render_strategies/_g8_other_equity_instruments_validate.py:36` `validate_g8_formulas` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/g9/contract-ocr` |  | `routers/wp_render_strategies/_g9_contract_ocr.py:82` `g9_contract_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/g9/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g9/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/g9/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/g9/validate-formulas` |  | `routers/wp_render_strategies/_g9_other_noncurrent_financial_validate.py:34` `validate_g9_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h0/export-data` |  | `routers/wp_render_strategies/_h0_confirmation_import_export.py:360` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h0/export-template` |  | `routers/wp_render_strategies/_h0_confirmation_import_export.py:349` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h0/import-data` |  | `routers/wp_render_strategies/_h0_confirmation_import_export.py:375` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/h0/unreplied-entities` | 从 H0-1 函证结果汇总表获取未回函被函证单位列表（供 importFromSummary）。 | `routers/wp_render_strategies/_h0_confirmation_import_export.py:274` `unreplied_entities` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h1/depreciation/calculate` | 批量计算固定资产折旧（4方法+含减值+多次减值）. | `routers/wp_render_strategies/_h1_depreciation_engine.py:271` `h1_depreciation_calculate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h1/depreciation/validate` | 验证账面折旧与测算折旧的差异. | `routers/wp_render_strategies/_h1_depreciation_engine.py:294` `h1_depreciation_validate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h1/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h1/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h1/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h1/property-title-ocr` | 上传权证附件，OCR识别并提取权属字段供 H1-16 预填 | `routers/wp_render_strategies/_h1_property_ocr.py:78` `h1_property_title_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h1/stocktake-plan-export` |  | `routers/wp_render_strategies/_h1_stocktake_plan_export.py:146` `h1_stocktake_plan_export` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h1/stocktake-summary-ocr` |  | `routers/wp_render_strategies/_h1_stocktake_summary_ocr.py:113` `h1_stocktake_summary_ocr` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/h1/vehicle-title-ocr` | 上传行驶证/登记证书附件，OCR识别并提取车辆权属字段供 H1-17 预填 | `routers/wp_render_strategies/_h1_property_ocr.py:208` `h1_vehicle_title_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h10/export-data` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_import_export.py:94` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h10/export-template` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_import_export.py:80` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h10/import-data` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_import_export.py:113` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h10/save-adjudication` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_validate.py:155` `save_h10_adjudication` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h10/validate-formulas` |  | `routers/wp_render_strategies/_h10_asset_disposal_income_validate.py:126` `validate_h10_formulas` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h2/export-data` |  | `routers/wp_render_strategies/_h2_import_export.py:489` `h2_export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h2/export-template` |  | `routers/wp_render_strategies/_h2_import_export.py:467` `h2_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h2/import-data` |  | `routers/wp_render_strategies/_h2_import_export.py:516` `h2_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h2/interest-cap/calculate` | 利息资本化计算（2分支：无/有专门借款）. | `routers/wp_render_strategies/_h2_interest_cap_engine.py:257` `h2_interest_cap_calculate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h2/interest-cap/validate` | 验证账面利息资本化金额与测算差异. | `routers/wp_render_strategies/_h2_interest_cap_engine.py:277` `h2_interest_cap_validate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h3/contract-ocr` | 上传租赁合同附件，OCR识别并提取租赁要素；可选回流已关联附件证据链。 | `routers/wp_render_strategies/_h3_contract_ocr.py:130` `h3_contract_ocr` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/h3/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h3/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h3/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h3/real-estate-title-ocr` | 上传不动产权证附件，OCR识别并提取权属字段供 H3-12 预填 | `routers/wp_render_strategies/_h3_property_ocr.py:79` `h3_real_estate_title_ocr` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h3/transfer/calculate` | 互转三方向计算（自用→投资 / 投资→自用 / 在建→投资）. | `routers/wp_render_strategies/_h3_transfer_engine.py:184` `h3_transfer_calculate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h3/transfer/validate` | 验证转出=转入一致性. | `routers/wp_render_strategies/_h3_transfer_engine.py:214` `h3_transfer_validate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h4/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h4/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h4/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/h6/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h6/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h6/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/h7/export-data` | 导出H7底稿数据（含已填数据）. | `routers/h7_biological_assets.py:50` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/h7/export-template` | 导出H7底稿模板（空表结构）. | `routers/h7_biological_assets.py:34` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h7/import-data` | 导入H7底稿数据. | `routers/h7_biological_assets.py:66` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/h8/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h8/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/h8/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i1/amortization/calculate-dcf` | 服务端DCF计算验证. | `routers/wp_render_strategies/_i1_amortization_engine.py:361` `i1_amortization_calculate_dcf` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i1/amortization/validate` | 验证前端摊销计算结果与后端引擎的差异. | `routers/wp_render_strategies/_i1_amortization_engine.py:312` `i1_amortization_validate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i1/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i1/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i1/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i2/capitalization/evaluate` | CAS6五条件资本化评估. | `routers/wp_render_strategies/_i2_capitalization_engine.py:130` `i2_capitalization_evaluate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i2/capitalization/validate-split` | 费用化+资本化=研发总额校验（VR-I6-01）. | `routers/wp_render_strategies/_i2_capitalization_engine.py:146` `i2_capitalization_validate_split` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i2/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i2/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i2/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i3/dcf/calculate` | 服务端DCF完整计算（与validate相同逻辑，语义区分用于首次计算场景）. | `routers/wp_render_strategies/_i3_dcf_engine.py:397` `i3_dcf_calculate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i3/dcf/validate` | 验证前端DCF计算结果. | `routers/wp_render_strategies/_i3_dcf_engine.py:355` `i3_dcf_validate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i3/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i3/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i3/impairment/allocate` | 减值分摊验证：先冲商誉再按比例分摊至资产组其他资产. | `routers/wp_render_strategies/_i3_dcf_engine.py:411` `i3_impairment_allocate` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/i3/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i4/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i4/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i4/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i5/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i5/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/i5/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/i6/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 2 |
| POST | `/api/workpapers/{wp_id}/i6/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 2 |
| POST | `/api/workpapers/{wp_id}/i6/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 3 |
| GET | `/api/workpapers/{wp_id}/import-export/export` | 导出当前数据. | `routers/wp_render_strategies/_j3_import_export.py:89` `export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/import-export/import` | 导入 Excel 数据（按位置解析，回写 J3-1-plans）. | `routers/wp_render_strategies/_j3_import_export.py:126` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/import-export/template` | 导出空白模板（含表头 + 示例行）. | `routers/wp_render_strategies/_j3_import_export.py:67` `export_template` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/workpapers/{wp_id}/j1/export-data` | 导出数据（含现有数据）. | `routers/wp_render_strategies/_j1_import_export.py:661` `export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/j1/export-data` | 导出数据（含现有数据）. | `routers/wp_render_strategies/_j1_import_export.py:661` `export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/j1/export-template` | 导出模板（空表头 + 默认行骨架 + 编制说明）. | `routers/wp_render_strategies/_j1_import_export.py:603` `export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/j1/export-template` | 导出模板（空表头 + 默认行骨架 + 编制说明）. | `routers/wp_render_strategies/_j1_import_export.py:603` `export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/j1/import-data` | 导入数据. | `routers/wp_render_strategies/_j1_import_export.py:814` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/j2/export-data` | 导出J2当前数据. | `routers/wp_render_strategies/_j2_import_export.py:87` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/j2/export-template` | 导出J2设定受益计划空白模板. | `routers/wp_render_strategies/_j2_import_export.py:31` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/j2/import-data` | 导入J2数据. | `routers/wp_render_strategies/_j2_import_export.py:130` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k0/export-data` |  | `routers/wp_render_strategies/_k0_confirmation_import_export.py:452` `export_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/k0/export-template` |  | `routers/wp_render_strategies/_k0_confirmation_import_export.py:440` `export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/k0/import-data` |  | `routers/wp_render_strategies/_k0_confirmation_import_export.py:468` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/k0/unreplied-entities` | 从 K0-1 函证结果汇总表获取未回函被函证单位列表（供 importFromSummary）。 | `routers/wp_render_strategies/_k0_confirmation_import_export.py:368` `unreplied_entities` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/workpapers/{wp_id}/k1/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k1/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k1/import-aux-balance` | 从 `tb_aux_balance`（科目 1221，按往来单位维度）归集导入 K1-2 明细表。 | `routers/wp_render_strategies/_k1_import_export.py:1398` `k1_import_aux_balance` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/k1/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k10/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k10/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k10/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k11/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k11/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k11/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k12/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k12/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k12/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k13/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k13/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k13/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k2/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/k2/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 1 |
| POST | `/api/workpapers/{wp_id}/k2/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/k3/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k3/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k3/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k4/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k4/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k4/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k5/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 4 |
| POST | `/api/workpapers/{wp_id}/k5/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 4 |
| POST | `/api/workpapers/{wp_id}/k5/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 4 |
| POST | `/api/workpapers/{wp_id}/k6/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k6/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k6/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k7/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k7/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k7/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k8/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k8/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k8/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/k9/export-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:746` `export_data` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k9/export-template` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:720` `export_template` | dedicated_wp_gate、get_current_user、get_current_user_stream | 0 |
| POST | `/api/workpapers/{wp_id}/k9/import-data` |  | `routers/wp_render_strategies/_cycle_import_export_common.py:796` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l0/export-data` |  | `routers/wp_render_strategies/_l0_confirmation_import_export.py:378` `export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l0/export-template` |  | `routers/wp_render_strategies/_l0_confirmation_import_export.py:367` `export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l0/import-data` |  | `routers/wp_render_strategies/_l0_confirmation_import_export.py:393` `import_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/l0/unreplied-entities` | 从 L0-1 函证结果汇总表获取未回函被函证单位列表（供 importFromSummary）。 | `routers/wp_render_strategies/_l0_confirmation_import_export.py:299` `unreplied_entities` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/l1/export-data` | 导出含当前数据的xlsx | `routers/l1_short_term_loans.py:288` `l1_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/l1/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/l1_short_term_loans.py:263` `l1_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/l1/import-data` | 导入xlsx解析写入checklist_responses | `routers/l1_short_term_loans.py:338` `l1_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/l3/calculate-interest` | 利息测算API：批量计算各合同利息 | `routers/l3_long_term_loans.py:498` `l3_calculate_interest` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/l3/export-data` | 导出含当前数据的xlsx | `routers/l3_long_term_loans.py:363` `l3_export_data` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/l3/export-template` | 导出空白xlsx模板（含表头+格式，无数据行） | `routers/l3_long_term_loans.py:338` `l3_export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/l3/import-data` | 导入xlsx解析写入checklist_responses | `routers/l3_long_term_loans.py:413` `l3_import_data` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/l3/reclass-current-portion` | 一年内到期重分类API | `routers/l3_long_term_loans.py:533` `l3_reclass_current_portion` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/export-data` | 导出含当前数据的xlsx（多sheet） | `routers/l4_bonds_payable.py:119` `l4_export_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/export-template` | 导出空白xlsx模板（多sheet，L4-2区段89列分sheet） | `routers/l4_bonds_payable.py:100` `l4_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/generate-schedule` | 生成EIR后续计量表（2分支） | `routers/l4_bonds_payable.py:159` `l4_generate_schedule` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/import-data` | 导入xlsx解析写入checklist_responses（支持多sheet区段合并） | `routers/l4_bonds_payable.py:138` `l4_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/solve-eir` | 求解实际利率（IRR二分法） | `routers/l4_bonds_payable.py:201` `l4_solve_eir` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l4/validate-formulas` | 校验公式方向（负债类贷方：期末=期初+贷方-借方） | `routers/l4_bonds_payable.py:229` `l4_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/l5/export-data` | 导出含当前数据的xlsx（多sheet） | `routers/l5_long_term_payables.py:105` `l5_export_data` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/l5/export-template` | 导出空白xlsx模板（多sheet，按动态行表格分sheet） | `routers/l5_long_term_payables.py:82` `l5_export_template` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l5/generate-amortization` | 生成未确认融资费用摊销表（实际利率法） | `routers/l5_long_term_payables.py:153` `l5_generate_amortization` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l5/import-data` | 导入xlsx解析写入checklist_responses（支持多sheet） | `routers/l5_long_term_payables.py:128` `l5_import_data` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/l5/validate-formulas` | 校验公式方向 | `routers/l5_long_term_payables.py:189` `l5_validate_formulas` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/offline/export-template` | 导出底稿填写模板 (15.9). | `routers/wp_offline.py:22` `export_template` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/offline/import-apply` | 执行导入 (15.9). | `routers/wp_offline.py:80` `import_apply` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/workpapers/{wp_id}/offline/import-preview` | 校验并预览导入 diff (15.9). | `routers/wp_offline.py:59` `import_preview` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/preparation-info` | workpaper 级编制信息（7 字段，无 accounting_period）。 | `routers/wp_render_config.py:506` `get_preparation_info` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/procedure-categories` | 读取当前勾选的程序分类。 | `routers/wp_procedure_status.py:191` `get_procedure_categories` | dedicated_wp_gate、get_current_user | 20 |
| PUT | `/api/workpapers/{wp_id}/procedure-categories` | 持久化用户勾选的程序分类（F1.8）。 | `routers/wp_procedure_status.py:151` `update_procedure_categories` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/program-row-access` |  | `routers/wp_program_row_access.py:29` `get_program_row_access` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/references` | 获取底稿的跨模块引用关系（上游依赖+下游影响） | `routers/wp_step_mapping.py:169` `get_wp_references` | dedicated_wp_gate、get_current_user | 21 |
| GET | `/api/workpapers/{wp_id}/render-config` | 获取底稿渲染 schema + 项目数据 + 跨底稿引用（dispatch 模式）。 | `routers/wp_render_config.py:593` `get_render_config` | dedicated_wp_gate、get_current_user | 207 |
| POST | `/api/workpapers/{wp_id}/review-sign` |  | `routers/a21_review.py:117` `review_sign` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/review-unlock` | 解锁已签字的复核表（仅合伙人可操作）. | `routers/a21_review.py:197` `review_unlock` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/row-name-alignment` | 底稿级刷新的名称对齐：逐行返回 match_state + 候选 + 映射来源（Requirement 1.1 / 1. | `routers/row_name_alignment_router.py:135` `row_name_alignment` | dedicated_wp_gate、get_current_user、require_wp_edit_permissio | 20 |
| POST | `/api/workpapers/{wp_id}/save` | 保存 HTML 数据到 parsed_data['html_data'][sheet_name]。 | `routers/wp_html_save.py:138` `save_html_data` | dedicated_wp_gate、get_current_user、require_operation(wp:edit | 23 |
| POST | `/api/workpapers/{wp_id}/save-version` |  | `routers/wp_storage.py:40` `save_version` | dedicated_wp_gate、get_current_user | 19 |
| GET | `/api/workpapers/{wp_id}/sheet-locks` | 查询底稿所有活跃 sheet 锁。 | `routers/wp_sheet_lock.py:119` `get_wp_sheet_locks` | dedicated_wp_gate、get_current_user | 19 |
| DELETE | `/api/workpapers/{wp_id}/sheets/{sheet_name}/lock` | 释放 sheet 锁。页面关闭/切 tab 时调用。 | `routers/wp_sheet_lock.py:85` `release_sheet_lock` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/sheets/{sheet_name}/lock` | 查询 sheet 锁持有者。无锁时返回 null。 | `routers/wp_sheet_lock.py:106` `get_sheet_lock_holder` | dedicated_wp_gate、get_current_user | 0 |
| POST | `/api/workpapers/{wp_id}/sheets/{sheet_name}/lock` | 获取 sheet 级编辑锁。 | `routers/wp_sheet_lock.py:29` `acquire_sheet_lock` | dedicated_wp_gate、get_current_user | 0 |
| PATCH | `/api/workpapers/{wp_id}/sheets/{sheet_name}/lock/heartbeat` | 续期 sheet 锁心跳。前端每 2 分钟调用一次。 | `routers/wp_sheet_lock.py:64` `heartbeat_sheet_lock` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/workpapers/{wp_id}/stale-chain` | 获取底稿的stale传播链（如果本底稿数据变更，哪些下游会受影响） | `routers/wp_step_mapping.py:381` `get_stale_chain` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/step-mapping` | 获取底稿的程序步骤→Sheet映射 | `routers/wp_step_mapping.py:74` `get_step_mapping` | dedicated_wp_gate、get_current_user | 21 |
| GET | `/api/workpapers/{wp_id}/validation-rules` | 获取底稿适用的校验规则 | `routers/wp_step_mapping.py:252` `get_wp_validation_rules` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/workpapers/{wp_id}/versions` |  | `routers/wp_storage.py:20` `list_versions` | dedicated_wp_gate、get_current_user | 20 |
| GET | `/api/wp-classifications` | 查询底稿 9 类归属（前端组件路由依据）。 | `routers/wp_classification.py:60` `get_wp_classifications` | get_current_user | 1 |
| GET | `/api/wp-data-rules/mapping` | 获取完整的底稿-科目-报表-附注映射表 | `routers/wp_data_rules.py:32` `get_all_mappings` | get_current_user | 0 |
| GET | `/api/wp-data-rules/mapping/by-account/{account_code}` | 根据科目编码查询映射关系 | `routers/wp_data_rules.py:52` `get_mapping_by_account` | get_current_user | 0 |
| GET | `/api/wp-data-rules/mapping/by-note/{note_section}` | 根据附注章节号查询映射关系 | `routers/wp_data_rules.py:64` `get_mapping_by_note` | get_current_user | 0 |
| GET | `/api/wp-data-rules/mapping/by-wp/{wp_code}` | 根据底稿编号查询映射关系 | `routers/wp_data_rules.py:40` `get_mapping_by_wp` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/batch-extract` | 批量提取一个循环下所有底稿的数据 | `routers/wp_data_rules.py:122` `batch_extract` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/consistency/{wp_code}` | 校验底稿审定数与附注合计的一致性 | `routers/wp_data_rules.py:109` `check_consistency` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/extract/{wp_code}` | 提取底稿关联的全部数据（试算表+调整分录+附注映射） | `routers/wp_data_rules.py:76` `extract_data_for_wp` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-data/{note_section}` | 提取附注章节关联的数据（从底稿/试算表） | `routers/wp_data_rules.py:96` `extract_data_for_note` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-table/{note_section}/cell` | 固定单元格取数：NOTE_CELL(section, row_label, col_header) | `routers/wp_data_rules.py:163` `note_cell` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-table/{note_section}/column` | 整列取数：NOTE_COL(section, col_header) → 支持浮动行填充 | `routers/wp_data_rules.py:180` `note_column` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-table/{note_section}/dynamic-rows` | 生成浮动行数据（从辅助余额表/底稿明细动态生成） | `routers/wp_data_rules.py:212` `note_dynamic_rows` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-table/{note_section}/row` | 整行取数：NOTE_ROW(section, row_label) → 支持变动表多列 | `routers/wp_data_rules.py:196` `note_row` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/note-table/{note_section}/style` | 获取附注章节的表格样式（fixed_rows/dynamic_rows/mixed） | `routers/wp_data_rules.py:151` `get_note_table_style` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/parse-all-workpapers` | 批量解析项目下所有底稿（通用规则） | `routers/wp_data_rules.py:277` `parse_all_workpapers` | get_current_user | 0 |
| GET | `/api/wp-data-rules/projects/{project_id}/parse-workpaper/{wp_code}` | 通用底稿解析 — 自动识别所有Sheet结构并提取数据 | `routers/wp_data_rules.py:237` `parse_workpaper_generic` | get_current_user | 0 |
| GET | `/api/wp-dependencies/cycle/{cycle}` | 获取循环的B→C→D依赖关系图（供前端可视化） | `routers/wp_dependencies.py:49` `get_cycle_graph` | dedicated_wp_gate、get_current_user | 3 |
| GET | `/api/wp-dependencies/cycles` | 列出所有循环的依赖定义 | `routers/wp_dependencies.py:58` `list_all_cycles` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/wp-dependencies/effectiveness-impact` | 获取控制测试结论对实质性程序的影响定义 | `routers/wp_dependencies.py:71` `get_effectiveness_impact` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/wp-dependencies/generation-order` | 按B→C→D-N→A顺序排列底稿编码 | `routers/wp_dependencies.py:77` `get_order` | dedicated_wp_gate、get_current_user | 0 |
| GET | `/api/wp-fine-rules` | 列出所有精细化规则 | `routers/wp_fine_rules.py:29` `list_rules` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/wp-fine-rules/summary` | 精细化规则汇总统计（按循环分组） | `routers/wp_fine_rules.py:49` `rules_summary` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/wp-fine-rules/system-map` | 底稿体系全景图 | `routers/wp_fine_rules.py:68` `get_system_map` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/wp-fine-rules/{wp_code}` | 获取指定底稿的精细化规则 | `routers/wp_fine_rules.py:81` `get_rule` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/wp-index-resolve` | 解析底稿索引引用并校验存在性 — 转发至 ACNR 统一 resolve 出口。 | `routers/wp_index_resolve.py:154` `resolve_wp_index` | get_current_user | 2 |
| GET | `/api/wp-manuals` | 获取所有循环的md文件索引 | `routers/wp_manuals.py:23` `list_all_manuals` | get_current_user | 1 |
| GET | `/api/wp-manuals/stats` | 操作手册统计 | `routers/wp_manuals.py:34` `manual_stats` | get_current_user | 1 |
| GET | `/api/wp-manuals/{cycle}` | 获取指定循环的md文件列表 | `routers/wp_manuals.py:40` `list_cycle_manuals` | get_current_user | 1 |
| GET | `/api/wp-manuals/{cycle}/context` | 获取LLM上下文（操作手册+模板库+控制底稿合并，供AI面板使用） | `routers/wp_manuals.py:76` `get_llm_context` | get_current_user | 1 |
| GET | `/api/wp-manuals/{cycle}/manual` | 获取操作手册内容（审计程序步骤、检查要点） | `routers/wp_manuals.py:50` `get_cycle_manual` | get_current_user | 1 |
| GET | `/api/wp-manuals/{cycle}/template` | 获取底稿模板库内容（底稿结构说明、填写指引） | `routers/wp_manuals.py:63` `get_cycle_template_lib` | get_current_user | 0 |
| GET | `/api/wp-manuals/{cycle}/{filename}` | 获取指定md文件内容 | `routers/wp_manuals.py:93` `get_file_content` | get_current_user | 2 |
| GET | `/api/wp-template-metadata` | 查询模板元数据（支持按阶段/组件类型/循环筛选） | `routers/wp_template_metadata.py:28` `list_template_metadata` | — | 0 |
| POST | `/api/wp-template-metadata/seed` | 加载种子数据到 wp_template_metadata 表（幂等） | `routers/wp_template_metadata.py:68` `seed_template_metadata` | — | 1 |
| GET | `/api/wp-template-metadata/{wp_code}` | 获取单个底稿的模板元数据 | `routers/wp_template_metadata.py:53` `get_template_metadata` | — | 1 |
| GET | `/api/wp-template-versions` | 列出所有模板版本，按 release_date 降序排列。 | `routers/wp_template_version.py:77` `list_template_versions` | get_current_user | 0 |
| GET | `/api/wp-template-versions/current` | 获取当前活跃模板版本（is_current=TRUE）。 | `routers/wp_template_version.py:52` `get_current_template_version` | get_current_user | 0 |

## D01 用户、组织与权限（95 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| POST | `/api/auth/login` | 用户登录，返回 access_token + refresh_token。 | `api/auth.py:18` `login` | — | 2 |
| POST | `/api/auth/logout` | 登出，将 refresh_token 加入黑名单使其失效。 | `api/auth.py:60` `logout` | — | 2 |
| POST | `/api/auth/refresh` | 使用 refresh_token 获取新的 token 对（Token Rotation）。 | `api/auth.py:36` `refresh` | — | 2 |
| POST | `/api/auth/register` | 用户注册（公开接口，不需要认证）。 | `api/auth.py:76` `register` | — | 1 |
| POST | `/api/auth/verify-password` | 验证密码并返回一次性 confirmation_token。 | `routers/password_confirm.py:52` `verify_password_endpoint` | get_current_user | 2 |
| GET | `/api/departments` | 获取部门列表 | `routers/departments.py:58` `list_departments` | get_current_user | 1 |
| POST | `/api/departments` | 创建部门 | `routers/departments.py:109` `create_department` | get_current_user | 1 |
| DELETE | `/api/departments/{department_id}` | 删除部门（软删除） | `routers/departments.py:223` `delete_department` | get_current_user | 1 |
| GET | `/api/departments/{department_id}` | 获取部门详情 | `routers/departments.py:88` `get_department` | get_current_user | 1 |
| PUT | `/api/departments/{department_id}` | 更新部门信息 | `routers/departments.py:156` `update_department` | get_current_user | 1 |
| GET | `/api/departments/{department_id}/tree` | 获取部门树（包含所有子部门） | `routers/departments.py:273` `get_department_tree` | get_current_user | 0 |
| POST | `/api/merge` | 合并同项目同日多条工时为一条 | `routers/workhours.py:456` `merge_hour_entries` | get_current_user | 0 |
| GET | `/api/my/work-hour-entries` | 当前用户跨项目工时条目查询。 | `routers/workhours.py:366` `my_work_hour_entries` | get_current_user | 1 |
| GET | `/api/projects/my/assignments` | 获取当前用户被委派的项目列表 | `routers/assignments.py:23` `my_assignments` | get_current_user | 3 |
| GET | `/api/projects/{project_id}/assignments` |  | `routers/assignments.py:33` `list_assignments` | get_current_user | 4 |
| POST | `/api/projects/{project_id}/assignments` |  | `routers/assignments.py:43` `save_assignments` | get_current_user | 4 |
| GET | `/api/projects/{project_id}/my-permissions` | 返回当前用户在该项目的合并权限列表。 | `routers/project_permissions.py:25` `get_my_permissions` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/my-role` | 返回当前用户在该项目的角色和系统角色。 | `routers/project_permissions.py:40` `get_my_role` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/permission-matrix` | 返回当前用户在该项目的权限矩阵。 | `routers/permission_matrix.py:27` `get_project_permission_matrix` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/role-workbench` | 获取角色作业台数据。 | `routers/role_workbench.py:22` `get_role_workbench` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/temporary-grants` | 列出项目的临时授权。 | `routers/temporary_grants.py:57` `list_temporary_grants` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/temporary-grants` | 创建临时授权。仅项目经理/合伙人/admin 可操作。 | `routers/temporary_grants.py:36` `create_temporary_grant` | get_current_user | 1 |
| DELETE | `/api/projects/{project_id}/temporary-grants/{grant_id}` | 撤销临时授权。 | `routers/temporary_grants.py:73` `revoke_temporary_grant` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/work-hours` |  | `routers/workhours.py:157` `project_hours` | get_current_user | 3 |
| GET | `/api/projects/{project_id}/workhours` | 列出工时条目（支持日期+状态过滤） | `routers/workhour_entries.py:154` `list_entries` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/workhours` | 创建工时条目（校验日合计 ≤ 24h） | `routers/workhour_entries.py:126` `create_entry` | get_current_user | 3 |
| GET | `/api/projects/{project_id}/workhours/approval` | 列出待审批工时（含底稿进度列） | `routers/workhour_approval.py:115` `list_pending_approvals` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/workhours/approval/approve` | 批量审批工时（submitted → approved） | `routers/workhour_approval.py:189` `approve_entries` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workhours/approval/reject` | 批量退回工时（submitted → rejected） | `routers/workhour_approval.py:221` `reject_entries` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workhours/batch-quick` | 快速批量工时填报（WeeklyTimesheet 专用）。 | `routers/workhour_entries.py:372` `batch_quick_save` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workhours/batch-submit` | 批量提交工时（draft → submitted，单事务） | `routers/workhour_entries.py:326` `batch_submit` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/workhours/budget-vs-actual` | 返回预算 vs 实际对比数据 | `routers/workhour_budget.py:30` `get_budget_compare` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/workhours/summary` | 工时汇总统计 | `routers/workhour_entries.py:186` `get_summary` | get_current_user | 1 |
| DELETE | `/api/projects/{project_id}/workhours/{entry_id}` | 删除工时条目（仅 draft 状态可删） | `routers/workhour_entries.py:297` `delete_entry` | get_current_user | 5 |
| GET | `/api/projects/{project_id}/workhours/{entry_id}` | 获取单条工时条目 | `routers/workhour_entries.py:218` `get_entry` | get_current_user | 5 |
| PUT | `/api/projects/{project_id}/workhours/{entry_id}` | 更新工时条目（仅 draft 状态可改） | `routers/workhour_entries.py:243` `update_entry` | get_current_user | 5 |
| GET | `/api/role-context/me` | 获取当前用户的全局角色上下文（系统角色+所有项目角色+最高角色） | `routers/role_context.py:18` `get_my_context` | get_current_user | 1 |
| GET | `/api/role-context/me/homepage` | 获取首页个性化内容 | `routers/role_context.py:38` `get_my_homepage` | get_current_user | 1 |
| GET | `/api/role-context/me/nav` | 获取当前用户可见的导航菜单 | `routers/role_context.py:28` `get_my_nav` | get_current_user | 1 |
| GET | `/api/role-context/project/{project_id}` | 获取当前用户在特定项目中的角色 | `routers/role_context.py:48` `get_project_role` | get_current_user | 2 |
| GET | `/api/staff` |  | `routers/staff.py:30` `list_staff` | get_current_user | 1 |
| POST | `/api/staff` |  | `routers/staff.py:131` `create_staff` | get_current_user | 1 |
| GET | `/api/staff/export-template` | 下载人员档案导入模板（xlsx 格式，含数据验证） | `routers/staff.py:66` `download_import_template` | get_current_user | 1 |
| POST | `/api/staff/import-excel` | 从Excel批量导入人员 | `routers/staff.py:250` `import_staff_from_excel` | get_current_user | 1 |
| GET | `/api/staff/me/staff-id` | 获取当前登录用户关联的人员档案 ID。 | `routers/staff.py:224` `get_my_staff_id` | get_current_user | 1 |
| GET | `/api/staff/stats` | 获取人员统计汇总（总人数/CPA/合伙人/在项目） | `routers/staff.py:56` `get_staff_stats` | get_current_user | 1 |
| DELETE | `/api/staff/{staff_id}` | 删除人员（仅 admin；仅允许删除 source=custom 的自定义人员）。 | `routers/staff.py:188` `delete_staff` | get_current_user、require_role | 1 |
| PUT | `/api/staff/{staff_id}` |  | `routers/staff.py:143` `update_staff` | get_current_user | 1 |
| POST | `/api/staff/{staff_id}/handover` | 执行人员交接 — 批量转移底稿/工单/项目委派。 | `routers/staff.py:350` `execute_handover` | get_current_user、require_role | 1 |
| GET | `/api/staff/{staff_id}/handover/preview` | 预览交接将影响的数据量（不执行实际变更）。 | `routers/staff.py:428` `preview_handover` | get_current_user、require_role | 1 |
| GET | `/api/staff/{staff_id}/projects` |  | `routers/staff.py:178` `get_projects` | get_current_user | 1 |
| GET | `/api/staff/{staff_id}/resume` |  | `routers/staff.py:158` `get_resume` | get_current_user | 1 |
| GET | `/api/staff/{staff_id}/work-hours` | 兼容层：从 work_hour_entries 读取并返回旧格式 | `routers/workhours.py:29` `list_hours` | get_current_user | 1 |
| POST | `/api/staff/{staff_id}/work-hours` | 兼容层：写入 work_hour_entries | `routers/workhours.py:79` `create_hour` | get_current_user | 1 |
| POST | `/api/staff/{staff_id}/work-hours/batch` | 批量保存工时（upsert 语义：同 staff+project+date 有记录则更新，无则创建）。 | `routers/workhours.py:183` `batch_save_hours` | get_current_user | 0 |
| GET | `/api/system/roles` | 角色列表（仅未删除），含 data_scope（Req 3.6）。 | `routers/sys_role.py:118` `list_roles` | get_current_user、require_role | 1 |
| POST | `/api/system/roles` | 创建角色（Req 3.1/3.2/3.3/3.4）。 | `routers/sys_role.py:128` `create_role` | get_current_user、require_role | 1 |
| DELETE | `/api/system/roles/{role_id}` | 软删角色 + 清关联 + 失效受影响账号缓存（Req 3.6 / 5.4）。 | `routers/sys_role.py:191` `delete_role` | get_current_user、require_role | 2 |
| PUT | `/api/system/roles/{role_id}` | 修改角色（Req 3.2~3.5）+ 失效受影响账号的缓存（Req 5.4）。 | `routers/sys_role.py:151` `update_role` | get_current_user、require_role | 2 |
| GET | `/api/system/roles/{role_id}/projects` | 取角色的自定义项目 id 列表（已过滤软删项目）。 | `routers/sys_role.py:181` `get_role_projects` | get_current_user、require_role | 1 |
| GET | `/api/system/user-project-role-tree/users` | 树的**根层**：未删除账号分页列表（Req 1.1~1.5）。 | `routers/project_role_tree.py:42` `list_user_nodes` | get_current_user、require_role | 1 |
| GET | `/api/system/user-project-role-tree/users/{user_id}/subtree` | 树的**第 2/3 层**：某账号的项目层 + 角色层 + 数据权限视角（Req 2.1~2.5, 5.1~5.4）。 | `routers/project_role_tree.py:65` `get_user_subtree` | get_current_user、require_role | 1 |
| GET | `/api/system/user-roles/{user_id}` | 查该账号绑定的全部未删除角色（Req 4.2）。 | `routers/user_role.py:51` `get_user_roles` | get_current_user、require_role | 2 |
| PUT | `/api/system/user-roles/{user_id}/roles` | 覆盖写该账号的角色绑定（Req 4.1/4.3）+ 失效其缓存（Req 5.4）。 | `routers/user_role.py:62` `assign_user_roles` | get_current_user、require_role | 1 |
| GET | `/api/timeline` | 获取指定日期的工时时间轴数据（带时间段） | `routers/workhours.py:502` `get_timeline_data` | get_current_user | 1 |
| GET | `/api/users/` | 获取用户列表（用于底稿分配、复核人选择等下拉框；须登录）。 | `api/users.py:49` `list_users` | get_current_user | 3 |
| POST | `/api/users/` | 创建用户（仅 admin 角色）。 | `api/users.py:200` `create_user` | get_current_user、require_role | 3 |
| GET | `/api/users/me` | 获取当前用户信息（含角色权限列表，供前端权限检查使用）。 | `api/users.py:226` `get_me` | get_current_user | 1 |
| GET | `/api/users/me/display-preferences` | 获取当前账号的显示偏好。 | `routers/user_display_preferences.py:39` `get_display_preferences` | get_current_user | 1 |
| PATCH | `/api/users/me/display-preferences` | 部分更新当前账号的显示偏好。 | `routers/user_display_preferences.py:51` `patch_display_preferences` | get_current_user | 1 |
| GET | `/api/users/project-creation-grants` | 列出经理精确 USCC 建项授权（仅 admin）。 | `api/users.py:91` `get_project_creation_grants` | get_current_user、require_role | 1 |
| POST | `/api/users/project-creation-grants/{grant_id}/revoke` | 撤销一条经理建项授权（仅 admin）。 | `api/users.py:128` `revoke_project_creation_grant` | get_current_user、require_role | 1 |
| POST | `/api/users/project-creation-grants/{manager_user_id}` | 批量授予经理精确企业代码建项权（仅 admin，重复请求幂等）。 | `api/users.py:101` `create_project_creation_grants` | get_current_user、require_role | 2 |
| GET | `/api/users/staff-bindings` | 列出人员档案与登录账号的绑定（仅 admin）。 | `api/users.py:151` `get_staff_bindings` | get_current_user、require_role | 1 |
| DELETE | `/api/users/{user_id}` | 删除用户（混合删除，仅 admin 角色）。 | `api/users.py:256` `delete_user` | get_current_user、require_role | 1 |
| PUT | `/api/users/{user_id}` | 修改用户（仅 admin）：邮箱 / 角色 / 启用状态 / 重置密码。不能停用或降级自己；至少保留一个启用的管理员。 | `api/users.py:213` `update_user` | get_current_user、require_role | 1 |
| GET | `/api/users/{user_id}/private-storage` |  | `routers/private_storage.py:27` `list_private_files` | get_current_user | 1 |
| GET | `/api/users/{user_id}/private-storage/quota` |  | `routers/private_storage.py:62` `get_quota` | get_current_user | 1 |
| POST | `/api/users/{user_id}/private-storage/upload` |  | `routers/private_storage.py:34` `upload_private_file` | get_current_user | 1 |
| DELETE | `/api/users/{user_id}/private-storage/{filename}` |  | `routers/private_storage.py:49` `delete_private_file` | get_current_user | 1 |
| POST | `/api/users/{user_id}/staff-binding` | 把人员档案绑定到账号（仅 admin）：一对一，绑定后该人员的有效委派对账号生效。 | `api/users.py:160` `bind_user_staff` | get_current_user、require_role | 1 |
| POST | `/api/users/{user_id}/staff-binding/unbind` | 解除账号与人员档案的绑定（仅 admin）；人员仍在项目团队中时拒绝。 | `api/users.py:181` `unbind_user_staff` | get_current_user、require_role | 1 |
| POST | `/api/work-hours/ai-suggest` |  | `routers/workhours.py:145` `ai_suggest` | get_current_user | 1 |
| GET | `/api/work-hours/edit-time-suggest` | 基于底稿编辑时间自动生成工时建议 | `routers/workhours.py:248` `edit_time_suggest` | get_current_user | 1 |
| PUT | `/api/work-hours/{hour_id}` | 兼容层：更新 work_hour_entries | `routers/workhours.py:118` `update_hour` | get_current_user | 1 |
| GET | `/api/workhours` | 审批人视角的工时列表（查询 work_hour_entries 表）。 | `routers/workhour_list.py:24` `list_workhours_for_approval` | get_current_user、require_role | 1 |
| POST | `/api/workhours/auto-collect` | 触发工时自动采集（从平台操作轨迹推断草稿） | `routers/workhours.py:346` `auto_collect_hours` | get_current_user | 1 |
| POST | `/api/workhours/batch-approve` | 工时批量审批 | `routers/workhour_approve.py:50` `batch_approve_workhours` | get_current_user、require_role | 1 |
| POST | `/api/workhours/parse-natural-language` | 自然语言解析工时描述为结构化条目（预览，不落库） | `routers/workhours.py:423` `parse_natural_language` | get_current_user | 1 |
| GET | `/api/workhours/stats/export` | 月报 xlsx 导出 | `routers/workhours.py:675` `stats_export` | get_current_user | 1 |
| GET | `/api/workhours/stats/heatmap` | 负载热力数据：近N周每天×项目工时 | `routers/workhours.py:634` `stats_heatmap` | get_current_user | 1 |
| GET | `/api/workhours/stats/weekly` | 周报数据：按项目/活动类型分组 + 本周vs上周同比 | `routers/workhours.py:570` `stats_weekly` | get_current_user | 1 |
| GET | `/api/workhours/summary` | 本周工时统计（查询 work_hour_entries），返回已审批+待审批小时数。 | `routers/workhour_list.py:93` `workhours_weekly_summary` | get_current_user、require_role | 1 |
| POST | `/api/{entry_id}/cross-day` | 跨日转移部分工时 | `routers/workhours.py:474` `cross_day_transfer` | get_current_user | 48 |
| POST | `/api/{entry_id}/split` | 拆分一条工时为多条（总时长守恒） | `routers/workhours.py:437` `split_hour_entry` | get_current_user | 48 |

## D02 项目与项目管理（141 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/dashboard/available-staff` | 查询未来一周可用人员（本周工时低于阈值的人员）。 | `routers/dashboard.py:308` `available_staff` | get_current_user | 1 |
| GET | `/api/dashboard/group-progress` | 集团审计子公司进度对比 | `routers/dashboard.py:102` `group_progress` | get_current_user | 1 |
| GET | `/api/dashboard/hours-heatmap` | 工时热力图数据 | `routers/dashboard.py:72` `hours_heatmap` | get_current_user | 1 |
| GET | `/api/dashboard/manager/assignment-status` | 委派已读回执 — 返回近 N 天委派记录及通知已读状态 | `routers/manager_dashboard.py:61` `get_assignment_status` | get_current_user | 1 |
| GET | `/api/dashboard/manager/overview` | 项目经理看板总览 — 项目卡片 + 跨项目待办 + 团队负载 | `routers/manager_dashboard.py:37` `get_manager_overview` | get_current_user | 1 |
| GET | `/api/dashboard/manager/projects-overview` | 经理项目群总览 — 按 urgency_score 降序排列 | `routers/manager_dashboard.py:136` `get_projects_overview` | get_current_user | 1 |
| GET | `/api/dashboard/overview` | 关键指标聚合 | `routers/dashboard.py:32` `overview` | get_current_user | 1 |
| GET | `/api/dashboard/project-progress` | 项目进度列表 | `routers/dashboard.py:42` `project_progress` | get_current_user | 1 |
| GET | `/api/dashboard/project-staff-hours` | 按项目维度查询人员及工时情况 | `routers/dashboard.py:115` `project_staff_hours` | get_current_user | 1 |
| GET | `/api/dashboard/quality-metrics` | 审计质量指标 | `routers/dashboard.py:92` `quality_metrics` | get_current_user | 1 |
| GET | `/api/dashboard/risk-alerts` | 风险预警 | `routers/dashboard.py:82` `risk_alerts` | get_current_user | 1 |
| GET | `/api/dashboard/schedule` | 人员排期甘特图数据 | `routers/dashboard.py:62` `schedule` | get_current_user | 0 |
| GET | `/api/dashboard/staff-detail` | 按人员查询负责的项目、工时和未来一周安排 | `routers/dashboard.py:197` `staff_detail` | get_current_user | 1 |
| GET | `/api/dashboard/staff-workload` | 人员负荷排行 | `routers/dashboard.py:52` `staff_workload` | get_current_user | 1 |
| GET | `/api/dashboard/stats/compare` | KPI 环比：最近 window 天 vs 前 window 天，返回 current/previous/delta_p | `routers/dashboard.py:388` `stats_compare` | get_current_user | 1 |
| GET | `/api/dashboard/stats/trend` |  | `routers/dashboard.py:377` `stats_trend` | get_current_user | 1 |
| GET | `/api/issues` |  | `routers/issues.py:49` `list_issues` | get_current_user | 1 |
| POST | `/api/issues/from-conversation` |  | `routers/issues.py:38` `create_issue_from_conversation` | get_current_user | 1 |
| POST | `/api/issues/{issue_id}/escalate` |  | `routers/issues.py:78` `escalate_issue` | get_current_user | 1 |
| PUT | `/api/issues/{issue_id}/status` |  | `routers/issues.py:66` `update_issue_status` | get_current_user | 1 |
| DELETE | `/api/metabase/cache/{project_id}` | 清除项目仪表板缓存。 | `routers/metabase.py:79` `clear_cache` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/metabase/dashboards` | 预置仪表板列表 | `routers/metabase.py:36` `list_dashboards` | — | 1 |
| GET | `/api/metabase/drilldown-config` | 获取下钻路径配置 | `routers/metabase.py:93` `get_drilldown_config` | — | 1 |
| GET | `/api/metabase/drilldown-url` | 构建下钻目标 URL。 | `routers/metabase.py:99` `build_drilldown_url` | get_current_user | 1 |
| GET | `/api/metabase/embed-url` | 获取 Metabase 嵌入 URL。项目资源要求只读权限，全局资源仅管理员可签发。 | `routers/metabase.py:42` `get_embed_url` | get_current_user | 1 |
| GET | `/api/metabase/sql-templates` | SQL 查询模板 | `routers/metabase.py:73` `list_sql_templates` | — | 0 |
| GET | `/api/notifications` | 获取当前用户的通知列表 | `routers/notifications.py:26` `list_notifications` | get_current_user | 1 |
| POST | `/api/notifications/read-all` | 将当前用户所有未读通知标为已读 | `routers/notifications.py:108` `mark_all_read` | get_current_user | 1 |
| GET | `/api/notifications/unread-count` | 获取当前用户未读通知数量 | `routers/notifications.py:69` `get_unread_count` | get_current_user | 1 |
| DELETE | `/api/notifications/{notification_id}` | 删除单条通知 | `routers/notifications.py:127` `delete_notification` | get_current_user | 1 |
| POST | `/api/notifications/{notification_id}/read` | 标记单条通知为已读 | `routers/notifications.py:88` `mark_read` | get_current_user | 1 |
| GET | `/api/partner/overview` | 合伙人全局总览 — 我负责的所有项目+风险预警+待签字 | `routers/partner_dashboard.py:22` `get_partner_overview` | get_current_user | 1 |
| GET | `/api/partner/projects/urgency` | 返回合伙人负责项目的紧急度评分排序 | `routers/partner_urgency.py:79` `get_partner_urgency` | get_current_user | 1 |
| GET | `/api/partner/team-efficiency` | 团队效能分析 | `routers/partner_dashboard.py:93` `get_team_efficiency` | get_current_user | 1 |
| GET | `/api/projects` | 获取项目列表（按用户可见性过滤） | `routers/project_wizard.py:78` `list_projects` | get_current_user | 7 |
| POST | `/api/projects` | 创建审计项目；manager 须持精确 USCC 授权并在同事务成为项目经理。 | `routers/project_wizard.py:277` `create_project` | get_current_user、require_role | 7 |
| PUT | `/api/projects/annotations/{annotation_id}` |  | `routers/annotations.py:76` `update_annotation` | get_current_user | 80 |
| POST | `/api/projects/annotations/{annotation_id}/link-conversation` |  | `routers/annotations.py:106` `link_to_conversation` | get_current_user | 33 |
| POST | `/api/projects/batch-apply` |  | `routers/batch_project.py:120` `batch_apply_projects` | get_current_user、require_role | 32 |
| POST | `/api/projects/batch-delete` | 批量软删除项目（R9：admin 任意；其余须是本项目 edit 级成员。无权限的报错但不阻断其他项目）。 | `routers/project_wizard.py:749` `batch_delete_projects` | get_current_user | 31 |
| POST | `/api/projects/batch-export` |  | `routers/batch_project.py:262` `batch_export_projects` | get_current_user | 32 |
| POST | `/api/projects/batch-import` | 兼容入口：错误行隔离且回执准确；新前端走持久计划的整批原子 apply。 | `routers/batch_project.py:223` `batch_import_projects` | get_current_user、require_role | 31 |
| GET | `/api/projects/batch-imports/{validation_id}` |  | `routers/batch_project.py:181` `get_batch_import_status` | get_current_user | 80 |
| GET | `/api/projects/batch-imports/{validation_id}/errors.xlsx` |  | `routers/batch_project.py:207` `download_batch_import_errors` | get_current_user | 34 |
| GET | `/api/projects/batch-template` |  | `routers/batch_project.py:74` `download_batch_template` | get_current_user、require_role | 32 |
| POST | `/api/projects/batch-validate` |  | `routers/batch_project.py:101` `batch_validate_projects` | get_current_user、require_role | 32 |
| POST | `/api/projects/briefs/batch` | 创建批量简报异步任务 | `routers/batch_brief.py:77` `create_batch_brief` | get_current_user | 1 |
| GET | `/api/projects/briefs/batch/{job_id}` | 轮询批量简报任务状态 | `routers/batch_brief.py:126` `get_batch_brief_status` | get_current_user | 1 |
| GET | `/api/projects/list-with-progress` | 仪表盘甘特视图专用：项目列表 + 进度 + 派生时间窗 + 负责人姓名。 | `routers/project_wizard.py:128` `list_projects_with_progress` | get_current_user | 31 |
| GET | `/api/projects/tree` |  | `routers/batch_project.py:88` `get_group_tree` | get_current_user | 33 |
| DELETE | `/api/projects/{project_id}` | 软删除单个项目（R9：admin 任意；其余须是本项目 edit 级成员）。 | `routers/project_wizard.py:715` `delete_project` | get_current_user、require_project_access(edit) | 35 |
| GET | `/api/projects/{project_id}` |  | `routers/project_wizard.py:247` `get_project` | get_current_user | 35 |
| GET | `/api/projects/{project_id}/annotations` |  | `routers/annotations.py:60` `list_annotations` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/annotations` |  | `routers/annotations.py:24` `create_annotation` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/attach-subsidiaries` | 把选中的已有单体项目纳入本合并项目（需求 5.1；consol-tree-three-code-autobuild 需求 | `routers/project_wizard.py:369` `attach_subsidiaries` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/audit-phase` |  | `routers/project_audit_phase.py:44` `get_audit_phase` | get_current_user、require_project_access(readonly) | 2 |
| PUT | `/api/projects/{project_id}/audit-phase` |  | `routers/project_audit_phase.py:54` `put_audit_phase` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/available-subsidiaries` | 列出可纳入本合并项目的候选单体项目（需求 5.1；consol-tree-three-code-autobuild 任务 | `routers/project_wizard.py:299` `list_available_subsidiaries` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/checklist-templates/{wp_code}` | Bundle Tab 嵌入核对表 — 按 wp_code 取模板 + wp_id 取填写数据. | `routers/completion_phase.py:45` `get_checklist_template_bundle` | dedicated_wp_gate、get_current_user | 3 |
| GET | `/api/projects/{project_id}/communications` | 获取客户沟通记录列表 | `routers/pm_dashboard.py:107` `list_communications` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/communications` | 新增客户沟通记录 | `routers/pm_dashboard.py:118` `add_communication` | get_current_user、require_project_access(edit) | 2 |
| DELETE | `/api/projects/{project_id}/communications/{comm_id}` | 删除客户沟通记录 | `routers/pm_dashboard.py:132` `delete_communication` | get_current_user、require_project_access(edit) | 3 |
| PATCH | `/api/projects/{project_id}/communications/{comm_id}/commitments/{commitment_id}` | 标记客户承诺完成：关闭关联 ticket + 时间线追加'✅ 已完成' | `routers/pm_dashboard.py:148` `complete_commitment` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/completion-flags` | 项目级完成标记（供 A1-11 等签发入口解锁）。 | `routers/completion_phase.py:87` `get_completion_flags` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/config` | 获取项目配置（项目成员只读）。 | `routers/project_config.py:37` `get_project_config` | get_current_user、require_project_access(readonly) | 2 |
| PUT | `/api/projects/{project_id}/config` | 更新项目配置。 | `routers/project_config.py:50` `update_project_config` | get_current_user、require_project_permission(project:edit) | 2 |
| GET | `/api/projects/{project_id}/cross-ref-check` | 检查底稿交叉引用完整性 | `routers/pm_dashboard.py:94` `check_cross_refs` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/dashboard/summary` | 聚合端点：返回项目仪表盘全量数据。 | `routers/dashboard_aggregator.py:32` `get_dashboard_summary` | get_current_user、require_project_access(readonly) | 3 |
| GET | `/api/projects/{project_id}/group-import-template` |  | `routers/batch_project.py:238` `export_group_import_template` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/issue-hints` | 舞弊/违规 issue_tickets 计数提示（不写入正文）. | `routers/completion_phase.py:186` `get_issue_hints` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/issue-hints` | 获取项目舞弊/违规问题提示（启发式，仅供提示） | `routers/issue_hints.py:20` `get_project_issue_hints` | get_current_user | 2 |
| PATCH | `/api/projects/{project_id}/parent-code` | 调整项目的上级企业（「合并」总览页拖拽调层级，spec consol-autotree-linkage-closure  | `routers/project_wizard.py:440` `update_parent_code` | get_current_user、require_project_access(edit) | 2 |
| GET | `/api/projects/{project_id}/parent-code-history` | 查询项目的上级企业代码变更历史（读 app_audit_log，Task 16.1 读侧）。 | `routers/project_wizard.py:526` `get_parent_code_history` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/partner/workpaper-readiness` | Phase 12 P1-7: 签字前底稿专项检查（5项）+ Phase 14 门禁引擎 | `routers/partner_dashboard.py:46` `check_workpaper_readiness` | get_current_user、require_project_access(review) | 1 |
| GET | `/api/projects/{project_id}/pbc` | 获取项目 PBC 清单 | `routers/pbc.py:21` `list_pbc` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/pbc` | 创建 PBC 项 | `routers/pbc.py:44` `create_pbc` | dedicated_wp_gate、get_current_user | 1 |
| GET | `/api/projects/{project_id}/pbc/by-workpaper/{wp_id}` | 获取底稿关联的 PBC 项（侧栏证据收集 tab 用） | `routers/pbc.py:119` `get_pbc_by_workpaper` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/pbc/check-overdue` | 检测逾期 PBC 项并自动建 IssueTicket | `routers/pbc.py:130` `check_overdue` | dedicated_wp_gate、get_current_user | 0 |
| DELETE | `/api/projects/{project_id}/pbc/{item_id}` | 删除 PBC 项 | `routers/pbc.py:89` `delete_pbc` | dedicated_wp_gate、get_current_user | 2 |
| PUT | `/api/projects/{project_id}/pbc/{item_id}` | 更新 PBC 项 | `routers/pbc.py:68` `update_pbc` | dedicated_wp_gate、get_current_user | 2 |
| POST | `/api/projects/{project_id}/pbc/{item_id}/receive` | 标记 PBC 项已收到（pending→received） | `routers/pbc.py:104` `receive_pbc` | dedicated_wp_gate、get_current_user | 1 |
| POST | `/api/projects/{project_id}/procedure-row-tasks/materialize` | 显式物化 ProcedureRowTask（批量 active partial unique upsert）。只给本项目 | `routers/procedure_row_tasks.py:60` `materialize_row_tasks` | get_current_user、require_project_delegator | 1 |
| POST | `/api/projects/{project_id}/procedure-row-tasks/materialize-jobs` | 同步物化（兼容旧 materialize-jobs POST 签名，直接返回 succeeded）。只给本项目委派人（原 | `routers/procedure_row_tasks.py:81` `create_materialize_job` | get_current_user、require_project_delegator | 1 |
| GET | `/api/projects/{project_id}/procedure-row-tasks/materialize-jobs/{job_id}` | 已下线（410）：进程内 job store 不再作为可追踪生产真源。 | `routers/procedure_row_tasks.py:111` `get_materialize_job` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/procedure-row-tasks/{task_id}/transitions` | 程序行任务状态转换（单一状态机入口）。 | `routers/procedure_row_tasks.py:204` `transition_row_task` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/progress-board` | 项目底稿进度看板（按循环分组 + 看板列） | `routers/pm_dashboard.py:67` `get_progress_board` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/progress-brief` | 生成项目进度简报（polish=true 时调用 LLM 润色） | `routers/pm_dashboard.py:80` `get_progress_brief` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/review-inbox` | 项目级待复核收件箱 | `routers/pm_dashboard.py:52` `get_project_review_inbox` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/risk-summary` | 返回项目的风险摘要（签字决策面板用） | `routers/risk_summary.py:24` `get_risk_summary` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/sign-readiness` | 签字前 readiness 门面（R1 Task 7）： | `routers/partner_dashboard.py:32` `check_sign_readiness` | get_current_user、require_project_access(review) | 2 |
| GET | `/api/projects/{project_id}/subsequent-events` | 获取后续事项列表 | `routers/subsequent_events.py:27` `list_events` | get_current_user | 2 |
| POST | `/api/projects/{project_id}/subsequent-events` | 创建后续事项 | `routers/subsequent_events.py:58` `create_event` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/template-recommendation` | 根据项目属性推荐企业子类型（模板 A/B/C/D）。 | `routers/project_wizard.py:589` `get_template_recommendation` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/wizard` | 获取向导当前状态（支持断点续做）。 | `routers/project_wizard.py:641` `get_wizard_state` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/wizard/confirm` | 确认创建项目，状态 created → planning。 | `routers/project_wizard.py:690` `confirm_project` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/wizard/validate/{step}` | 校验指定步骤是否满足前进条件。 | `routers/project_wizard.py:673` `validate_step` | get_current_user | 1 |
| PUT | `/api/projects/{project_id}/wizard/{step}` | 更新指定步骤数据并持久化。 | `routers/project_wizard.py:654` `update_step` | get_current_user、require_project_access(edit) | 3 |
| GET | `/api/projects/{project_id}/workflow-status` | 从数据层推导 6 步工作流进度 | `routers/workflow_status.py:24` `get_workflow_status` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/workflow/compare/{execution_id}` | 版本对比 — 返回执行前后每行变化 | `routers/chain_workflow.py:415` `compare_execution` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/workflow/consistency-check` | 一致性检查 — 5 项检查 | `routers/chain_workflow.py:359` `consistency_check` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/workflow/data-health` | 全局数据一致性实时监控 — 数据健康度 | `routers/chain_workflow.py:490` `get_data_health` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/workflow/execute-full-chain` | 执行全链路生成 | `routers/chain_workflow.py:117` `execute_full_chain` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/workflow/executions` | 执行历史列表 | `routers/chain_workflow.py:238` `get_executions` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/workflow/export-package` | 组合导出包（ZIP） | `routers/chain_workflow.py:282` `export_package` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/workflow/notes/sync-from-report` | 同步报表数据到附注 | `routers/chain_workflow.py:522` `sync_notes_from_report` | get_current_user、require_project_access(edit) | 1 |
| POST | `/api/projects/{project_id}/workflow/notes/trim-and-sort` | 附注智能裁剪与排序 | `routers/chain_workflow.py:542` `trim_and_sort_notes` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/workflow/progress/{execution_id}` | SSE 进度流 — 实时推送步骤状态 | `routers/chain_workflow.py:188` `get_progress_stream` | get_current_user_stream、require_project_access_stream(readon | 1 |
| POST | `/api/projects/{project_id}/workflow/retry/{execution_id}` | 重试失败步骤 | `routers/chain_workflow.py:562` `retry_execution` | get_current_user、require_project_access(edit) | 1 |
| GET | `/api/projects/{project_id}/workpaper-summaries/{key}` | 摘要 API 骨架 — plus 阶段扩展各 key 取数. | `routers/completion_phase.py:107` `get_workpaper_summary` | dedicated_wp_gate、get_current_user | 2 |
| GET | `/api/projects/{project_id}/workpapers/{wp_id}/archive-checklist/suggestions` | A30 电子底稿归档检查表「按项目底稿建议」（spec attachment-archive-and-a-class-e | `routers/completion_phase.py:211` `get_archive_checklist_suggestions` | dedicated_wp_gate、get_current_user、require_project_access(re | 1 |
| GET | `/api/review-inbox` | 全局待复核收件箱 — 跨项目 | `routers/pm_dashboard.py:40` `get_global_review_inbox` | get_current_user | 1 |
| GET | `/api/share-change-events/{project_id}/{year}/events` | 列出项目/年度的股比变动事件。 | `routers/share_change_events.py:115` `list_events` | get_current_user、require_project_access(readonly) | 0 |
| POST | `/api/share-change-events/{project_id}/{year}/events` | 手动创建股比变动事件。 | `routers/share_change_events.py:128` `create_event` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/share-change-events/{project_id}/{year}/events/from-g7` | 将 G7-10 建议归一为事件并幂等 upsert。 | `routers/share_change_events.py:166` `upsert_from_g7` | get_current_user、require_project_access(edit) | 0 |
| DELETE | `/api/share-change-events/{project_id}/{year}/events/{event_id}` | 删除 draft 状态的事件。 | `routers/share_change_events.py:224` `delete_event` | get_current_user、require_project_access(edit) | 0 |
| PUT | `/api/share-change-events/{project_id}/{year}/events/{event_id}/approve` | 审批事件（draft → approved）。 | `routers/share_change_events.py:186` `approve_event` | get_current_user、require_project_access(edit) | 0 |
| PUT | `/api/share-change-events/{project_id}/{year}/events/{event_id}/revoke` | 撤回事件（approved → revoked）。 | `routers/share_change_events.py:205` `revoke_event` | get_current_user、require_project_access(edit) | 0 |
| POST | `/api/shared-config/apply` | 引用模板到项目 | `routers/shared_config.py:144` `apply_template` | get_current_user | 1 |
| GET | `/api/shared-config/references/{project_id}` | 查询项目的模板引用历史 | `routers/shared_config.py:170` `list_references` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/shared-config/templates` | 查询当前用户可用的模板列表 | `routers/shared_config.py:43` `list_templates` | get_current_user | 1 |
| POST | `/api/shared-config/templates` | 保存当前配置为共享模板 | `routers/shared_config.py:62` `save_template` | get_current_user | 1 |
| DELETE | `/api/shared-config/templates/{template_id}` | 删除模板 | `routers/shared_config.py:127` `delete_template` | get_current_user | 2 |
| GET | `/api/shared-config/templates/{template_id}` | 获取模板详情（含配置数据） | `routers/shared_config.py:88` `get_template` | get_current_user | 2 |
| PUT | `/api/shared-config/templates/{template_id}` | 更新模板 | `routers/shared_config.py:99` `update_template` | get_current_user | 2 |
| GET | `/api/task-events` |  | `routers/task_events.py:45` `list_events` | get_current_user | 1 |
| POST | `/api/task-events/replay` |  | `routers/task_events.py:24` `replay_event` | get_current_user | 1 |
| GET | `/api/task-tree` |  | `routers/task_tree.py:29` `list_task_tree` | get_current_user | 1 |
| POST | `/api/task-tree/reassign` |  | `routers/task_tree.py:76` `reassign_node` | get_current_user | 1 |
| GET | `/api/task-tree/stats` |  | `routers/task_tree.py:45` `get_tree_stats` | get_current_user | 1 |
| GET | `/api/task-tree/{node_id}` |  | `routers/task_tree.py:54` `get_node` | get_current_user | 1 |
| PUT | `/api/task-tree/{node_id}/status` |  | `routers/task_tree.py:64` `transit_status` | get_current_user | 1 |
| GET | `/api/tasks` |  | `routers/task_center.py:11` `list_all_tasks` | get_current_user | 0 |
| GET | `/api/tasks/stats` |  | `routers/task_center.py:22` `task_stats` | get_current_user | 0 |
| GET | `/api/tasks/{task_id}` |  | `routers/task_center.py:27` `get_task_detail` | get_current_user | 0 |
| POST | `/api/tasks/{task_id}/retry` | 人工重试失败任务 | `routers/task_center.py:36` `retry_failed_task` | get_current_user | 0 |
| GET | `/api/version-line/{project_id}` |  | `routers/version_line.py:16` `query_version_line` | get_current_user | 1 |
| POST | `/api/workflow/batch-execute` | 批量项目执行全链路 | `routers/chain_workflow.py:619` `batch_execute` | get_current_user | 1 |
| GET | `/api/workpapers/{wp_id}/annotations` |  | `routers/wp_cell_annotations.py:99` `list_annotations` | dedicated_wp_gate、get_current_user | 20 |
| POST | `/api/workpapers/{wp_id}/annotations` |  | `routers/wp_cell_annotations.py:47` `create_annotation` | dedicated_wp_gate、get_current_user | 20 |
| PATCH | `/api/workpapers/{wp_id}/annotations/{annotation_id}/reply` |  | `routers/wp_cell_annotations.py:68` `reply_annotation` | dedicated_wp_gate、get_current_user | 0 |
| PATCH | `/api/workpapers/{wp_id}/annotations/{annotation_id}/resolve` |  | `routers/wp_cell_annotations.py:85` `resolve_annotation` | dedicated_wp_gate、get_current_user | 0 |

## D15 后台任务、事件与系统基础设施（106 个）

| 方法 | 路径 | 说明 | 处理函数 | 鉴权 | 前端 |
|---|---|---|---|---|---:|
| GET | `/api/admin/event-health` | 返回最近 100 条级联记录 + 健康统计。 | `routers/admin_event_health.py:24` `get_event_health` | — | 0 |
| GET | `/api/admin/import-alerts` | 获取导入域告警规则评估结果。 | `routers/performance.py:62` `get_import_alerts` | get_current_user | 0 |
| GET | `/api/admin/import-event-health` | 获取导入激活/回滚事件一致性与 replay 证据。 | `routers/performance.py:82` `get_import_event_health` | get_current_user | 1 |
| POST | `/api/admin/import-event-replay` | 重放导入域 outbox 中 pending/failed 的激活与回滚事件。 | `routers/performance.py:93` `replay_import_events` | get_current_user | 1 |
| GET | `/api/admin/import-runner-health` | 获取导入 runner/worker 健康状态，识别 queued 堆积与失联作业。 | `routers/performance.py:73` `get_import_runner_health` | get_current_user | 0 |
| GET | `/api/admin/import-slo` | 获取导入域 SLO 摘要（JSON，可被外部告警脚本轮询）。 | `routers/performance.py:49` `get_import_slo` | get_current_user | 0 |
| GET | `/api/admin/llm-metrics` | 获取 LLM 调用监控指标（仅 admin）。 | `routers/performance.py:150` `get_llm_metrics` | get_current_user | 1 |
| GET | `/api/admin/logs` | 读取最近 N 行 JSON 日志（admin only） | `routers/logs_viewer.py:130` `get_recent_logs` | get_current_user | 1 |
| GET | `/api/admin/performance-metrics` | 获取详细性能指标。 | `routers/performance.py:32` `get_performance_metrics` | get_current_user | 2 |
| GET | `/api/admin/performance-stats` | 获取性能统计摘要。 | `routers/performance.py:24` `get_performance_stats` | get_current_user | 1 |
| GET | `/api/admin/slow-queries` | 获取慢查询列表。 | `routers/performance.py:40` `get_slow_queries` | get_current_user | 1 |
| GET | `/api/admin/storage-stats` | 存储统计（仅 admin；原先不鉴权） | `routers/private_storage.py:71` `get_storage_stats` | get_current_user、require_role | 0 |
| GET | `/api/admin/workpaper-health` | 底稿健康监控仪表盘 | `routers/wp_health_dashboard.py:22` `get_workpaper_health` | get_current_user | 0 |
| GET | `/api/admin/wp-metrics` | 底稿模块性能指标（Design §10）。 | `routers/performance.py:164` `get_wp_metrics` | get_current_user | 0 |
| GET | `/api/audit-logs/verify-chain` | 校验审计日志哈希链完整性。 | `routers/audit_logs.py:33` `verify_chain_endpoint` | get_current_user | 0 |
| GET | `/api/audit-types` | 审计类型列表 | `routers/audit_types.py:20` `list_audit_types` | — | 0 |
| GET | `/api/audit-types/{audit_type}/recommendation` | 审计类型推荐配置 | `routers/audit_types.py:27` `get_type_recommendation` | — | 1 |
| POST | `/api/conflicts/{conflict_id}/resolve` | 用户调解一条 pending 冲突（keep_manual / accept_new / merge）。 | `routers/cross_module_conflicts.py:119` `resolve_conflict` | get_current_user | 1 |
| GET | `/api/editing-locks/active` | 获取活跃锁列表（可选 ?resource_type= 过滤）。跨项目可见 ⇒ 只给 admin（前端无调用方）。 | `routers/editing_locks.py:115` `list_active_locks` | get_current_user | 0 |
| DELETE | `/api/editing-locks/{resource_type}/{resource_id}` | 释放编辑锁（只认锁持有者：service 按 holder_id 过滤） | `routers/editing_locks.py:194` `release` | get_current_user | 2 |
| POST | `/api/editing-locks/{resource_type}/{resource_id}` | 获取编辑锁（先判资源：看不见 / 无编辑权不建锁行、不清理他人过期锁） | `routers/editing_locks.py:129` `acquire` | get_current_user | 2 |
| POST | `/api/editing-locks/{resource_type}/{resource_id}/force` | 强制获取锁（释放原锁 + 创建新锁）。只给全权身份；新锁记录窗口标识（原先不记 ⇒ 本人所有窗口都能续期）。 | `routers/editing_locks.py:217` `force_acquire` | get_current_user | 1 |
| PATCH | `/api/editing-locks/{resource_type}/{resource_id}/heartbeat` | 续期 heartbeat。撤权后续期被拒 ⇒ 先放掉本人在该资源上的锁再拒绝（别人不用等锁过期）。 | `routers/editing_locks.py:162` `heartbeat` | get_current_user | 1 |
| GET | `/api/feature-flags` | 获取所有功能开关状态（已废弃，请迁移到 /api/feature-flags-v2） | `routers/feature_flags.py:21` `list_flags` | — | 4 |
| GET | `/api/feature-flags-v2` | 列出所有 DB feature flags。 | `api/feature_flags.py:45` `list_flags` | _require_admin、get_current_user | 1 |
| GET | `/api/feature-flags-v2/{key}` | 获取单个 flag。 | `api/feature_flags.py:55` `get_flag` | _require_admin、get_current_user | 1 |
| PUT | `/api/feature-flags-v2/{key}` | 设置 flag（即时生效 ≤ TTL 无需重部署）。 | `api/feature_flags.py:68` `update_flag` | _require_admin、get_current_user | 1 |
| GET | `/api/feature-flags/check/{flag}` | 检查单个功能是否启用（已废弃，请迁移到 /api/feature-flags-v2） | `routers/feature_flags.py:31` `check_flag` | — | 2 |
| GET | `/api/feature-flags/maturity` | 获取所有功能成熟度分级（已废弃，请迁移到 /api/feature-flags-v2） | `routers/feature_flags.py:38` `get_maturity` | — | 1 |
| PUT | `/api/feature-flags/projects/{project_id}` | 设置项目级功能开关（已废弃，请迁移到 /api/feature-flags-v2） | `routers/feature_flags.py:45` `set_flag` | get_current_user | 1 |
| GET | `/api/forum/posts` |  | `routers/forum.py:31` `list_posts` | — | 1 |
| POST | `/api/forum/posts` |  | `routers/forum.py:21` `create_post` | get_current_user | 1 |
| DELETE | `/api/forum/posts/{post_id}` |  | `routers/forum.py:64` `delete_post` | — | 1 |
| GET | `/api/forum/posts/{post_id}/comments` |  | `routers/forum.py:39` `get_comments` | — | 1 |
| POST | `/api/forum/posts/{post_id}/comments` |  | `routers/forum.py:44` `create_comment` | get_current_user | 1 |
| POST | `/api/forum/posts/{post_id}/like` |  | `routers/forum.py:54` `like_post` | — | 1 |
| GET | `/api/health` | 检查 PostgreSQL / Redis / 迁移状态 / schema 漂移。 | `api/health.py:46` `health_check` | — | 1 |
| GET | `/api/health/ledger-import` | Sprint 10.46-10.48: ledger-import 子系统健康检查。 | `routers/ledger_import_health.py:133` `health_ledger_import` | — | 0 |
| GET | `/api/health/redis` | Redis 健康检查端点。 | `routers/health_redis.py:112` `redis_health_check` | — | 0 |
| POST | `/api/instances/{instance_type}/{instance_id}/time-machine/restore/{snapshot_id}` | 恢复到指定快照时刻。 | `routers/time_machine.py:130` `restore_snapshot` | get_current_user | 1 |
| GET | `/api/instances/{instance_type}/{instance_id}/time-machine/snapshots` | 列出指定实例的快照列表。 | `routers/time_machine.py:95` `list_snapshots` | get_current_user | 2 |
| POST | `/api/instances/{instance_type}/{instance_id}/time-machine/snapshots` | 创建时光机快照。 | `routers/time_machine.py:51` `create_snapshot` | get_current_user | 2 |
| GET | `/api/linkage-bus/audit-log` | 获取联动传播审计日志（分页）。 | `routers/linkage_bus.py:287` `get_audit_log` | get_current_user | 1 |
| GET | `/api/linkage-bus/cell-detail` | 单元格完整公式详情：上游来源、下游去向、公式文本、stale 状态。 | `routers/linkage_bus.py:514` `get_cell_detail` | get_current_user | 1 |
| GET | `/api/linkage-bus/graph` | 获取统一依赖图（全局）。 | `routers/linkage_bus.py:158` `get_unified_graph` | get_current_user | 1 |
| GET | `/api/linkage-bus/header-rule` | 列出所有表头规则。 | `routers/linkage_bus.py:277` `list_header_rules` | get_current_user | 1 |
| POST | `/api/linkage-bus/header-rule` | 设置表头规则（用户指定 data_start_row）。 | `routers/linkage_bus.py:259` `create_header_rule` | get_current_user | 1 |
| GET | `/api/linkage-bus/health` | 引擎健康检查。 | `routers/linkage_bus.py:357` `health_check` | get_current_user | 1 |
| POST | `/api/linkage-bus/impact` | BFS 下游影响分析（替代 /v2/notify-cell-change）。 | `routers/linkage_bus.py:75` `stale_impact` | get_current_user | 1 |
| GET | `/api/linkage-bus/impact-by-addr` | 按 ACNR addr_id 查询下游影响（只读 BFS 预览）。 | `routers/linkage_bus.py:117` `stale_impact_by_addr` | get_current_user、require_project_access(readonly) | 0 |
| DELETE | `/api/linkage-bus/override` | 删除用户手动校正。 | `routers/linkage_bus.py:244` `delete_override` | get_current_user | 1 |
| GET | `/api/linkage-bus/override` | 列出所有用户手动校正。 | `routers/linkage_bus.py:234` `list_overrides` | get_current_user | 1 |
| POST | `/api/linkage-bus/override` | 用户手动校正：指定 label 对应的物理坐标。 | `routers/linkage_bus.py:217` `create_override` | get_current_user | 1 |
| GET | `/api/linkage-bus/resolve` | 语义 URI → 物理坐标解析。 | `routers/linkage_bus.py:188` `resolve_label` | get_current_user | 1 |
| GET | `/api/offline/conflicts` |  | `routers/offline_conflicts.py:51` `list_conflicts` | get_current_user | 1 |
| POST | `/api/offline/conflicts/detect` |  | `routers/offline_conflicts.py:30` `detect_conflicts` | get_current_user | 1 |
| POST | `/api/offline/conflicts/resolve` |  | `routers/offline_conflicts.py:39` `resolve_conflict` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/conflicts` | 按项目列出冲突记录，可选 status / target_module 过滤 + 分页。 | `routers/cross_module_conflicts.py:87` `list_conflicts` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/conflicts/pending` | 返回项目下未调解（status='pending'）的冲突列表 + 总数。 | `routers/cross_module_conflicts.py:66` `list_pending` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/cost-overview` | 获取项目成本概览。 | `routers/cost_overview.py:26` `get_cost_overview` | get_current_user、require_project_access(readonly) | 2 |
| POST | `/api/projects/{project_id}/create-next-year` | 一键创建当年项目（继承上年配置和数据）。 | `routers/continuous_audit.py:24` `create_next_year` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/data-validation` | 运行全部数据校验。 | `routers/data_validation.py:18` `validate_project` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/data-validation/findings` | 获取校验结果（支持筛选）。 | `routers/data_validation.py:31` `get_findings` | get_current_user | 0 |
| POST | `/api/projects/{project_id}/data-validation/fix` | 一键修复常见错误。 | `routers/data_validation.py:52` `fix_findings` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/dispatch-records` | 查询分发记录（可选过滤） | `routers/dispatch_records.py:178` `list_dispatch_records` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/dispatch-records` | 批量创建分发记录（去重：ON CONFLICT DO NOTHING） | `routers/dispatch_records.py:132` `create_dispatch_records` | get_current_user | 1 |
| DELETE | `/api/projects/{project_id}/dispatch-records/{record_id}` | 撤回分发记录 | `routers/dispatch_records.py:196` `revoke_dispatch_record` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/event-cascade/health` | 聚合事件级联健康度。 | `routers/event_cascade_health.py:26` `get_event_cascade_health` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/events/since` | 增量事件拉取 — 供前端 SSE 重连后拉取遗漏事件。 | `routers/events.py:157` `get_events_since` | get_current_user | 2 |
| GET | `/api/projects/{project_id}/events/stream` | SSE 事件流：客户端订阅后接收试算表更新等事件通知 | `routers/events.py:57` `sse_stream` | get_current_user_sse | 2 |
| GET | `/api/projects/{project_id}/jobs/{job_id}` | 获取后台任务状态 | `routers/background_jobs.py:19` `get_job_status` | get_current_user | 3 |
| POST | `/api/projects/{project_id}/jobs/{job_id}/retry` | 重试失败项 | `routers/background_jobs.py:35` `retry_job` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/lineage` | 统一溯源查询：返回 upstream / downstream / current（LocateTarget 格式）+  | `routers/lineage.py:30` `get_lineage` | get_current_user、require_project_access(readonly) | 7 |
| GET | `/api/projects/{project_id}/linkage-panorama/graph-data` | 聚合全量 CWR 图数据 + 当前项目 stale 状态。 | `routers/linkage_panorama.py:97` `get_graph_data` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/linkage/change-history/{row_code}` | 获取试算平衡表某行的变更历史时间线。 | `routers/linkage.py:75` `get_change_history` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/linkage/resolve-route` | 解析 LinkageContract 目标为可跳转前端路由。 | `routers/linkage_resolve.py:55` `resolve_route` | get_current_user、require_project_access(readonly) | 0 |
| GET | `/api/projects/{project_id}/linkage/trace` | 统一穿透查询 — 返回 LinkageContract 列表。 | `routers/linkage_trace.py:29` `get_linkage_trace` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/my-todo` | 获取当前用户的待办聚合列表。 | `routers/my_todo.py:31` `get_my_todo_list` | get_current_user、require_project_access(readonly) | 2 |
| GET | `/api/projects/{project_id}/platform-jobs/{job_id}` | 权威恢复路径：SSE 断线、刷新和新标签页都从这条状态端点恢复。 | `routers/platform_jobs.py:56` `get_platform_job` | get_current_user、require_project_access(readonly) | 3 |
| POST | `/api/projects/{project_id}/platform-jobs/{job_id}/cancel` | 取消自己的 queued/running job；worker 在下一进度/阶段边界检查 fence。 | `routers/platform_jobs.py:68` `cancel_platform_job` | get_current_user、require_project_access(readonly) | 1 |
| POST | `/api/projects/{project_id}/platform-jobs/{job_id}/retry` | 失败/取消的 job 创建一个新逻辑运行，保留原 attempt 审计轨迹。 | `routers/platform_jobs.py:89` `retry_platform_job` | get_current_user、require_project_access(readonly) | 1 |
| GET | `/api/projects/{project_id}/presence/editing` | 获取当前编辑状态列表。 | `routers/presence.py:98` `get_editing_states` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/presence/heartbeat` | 心跳上报：更新用户在线状态和编辑状态。 | `routers/presence.py:67` `heartbeat` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/presence/online` | 获取当前在线成员列表。 | `routers/presence.py:86` `get_online_members` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/prior-year-data` | 获取上年同科目数据（跨年对比） | `routers/continuous_audit.py:53` `get_prior_year_data` | get_current_user | 1 |
| GET | `/api/projects/{project_id}/stale-summary` | 返回项目中标记为 stale 的底稿列表 | `routers/stale_summary.py:22` `get_stale_summary` | get_current_user | 4 |
| GET | `/api/projects/{project_id}/stale-summary/full` | Spec A R2: 多模块聚合 stale 摘要 | `routers/stale_summary.py:68` `get_stale_summary_full` | get_current_user | 1 |
| POST | `/api/projects/{project_id}/standard/convert` | 执行准则切换（用户确认后执行，需求 5.2）。 | `routers/standard_conversion.py:139` `convert_standard` | get_current_user、require_project_access(edit) | 0 |
| GET | `/api/projects/{project_id}/trust-score` | 获取指定上下文的数据信任度聚合信息。 | `routers/trust_score.py:31` `get_trust_score` | get_current_user | 2 |
| GET | `/api/search/global` | 全局搜索 — 聚合底稿/科目/报表行/项目四类实体 | `routers/global_search.py:24` `search_global` | get_current_user | 1 |
| GET | `/api/security/login-attempts` | 获取登录尝试记录。 | `routers/security.py:24` `get_login_attempts` | get_current_user、require_role | 0 |
| GET | `/api/security/sessions` | 获取活跃会话列表。 | `routers/security.py:57` `get_sessions` | get_current_user、require_role | 0 |
| GET | `/api/settings` | 获取当前系统配置（敏感字段脱敏） | `routers/system_settings.py:63` `get_system_settings` | get_current_user、require_role | 1 |
| PUT | `/api/settings` | 更新可修改的配置项（仅 admin） | `routers/system_settings.py:106` `update_system_settings` | get_current_user、require_role | 1 |
| GET | `/api/settings/health` | 各外部服务连通性检查 | `routers/system_settings.py:161` `check_services_health` | get_current_user、require_role | 1 |
| POST | `/api/sod/check` | 校验 SoD 职责分离冲突 | `routers/sod.py:33` `check_sod` | get_current_user | 1 |
| GET | `/api/trace` | 按项目/对象/时间/角色检索 trace 事件 | `routers/trace.py:43` `query_traces` | get_current_user | 1 |
| GET | `/api/trace/{trace_id}/replay` | 按 trace_id 回放完整事件链 | `routers/trace.py:20` `replay_trace` | get_current_user | 1 |
| GET | `/api/version` |  | `main.py:163` `api_version` | — | 1 |
| GET | `/api/{module}/{instance_id}/allowed-actions` | 获取指定业务实例的允许/禁止操作列表。 | `routers/status_machine.py:29` `get_allowed_actions` | get_current_user | 45 |
| GET | `/docs` |  | `core/openapi_runtime.py:94` `swagger_docs` | — | 0 |
| GET | `/livez` | 存活探针：只要事件循环能响应即 200。不查 DB/依赖。 | `api/probes.py:86` `livez` | — | 0 |
| GET | `/metrics` | Prometheus /metrics 端点（F16 / Sprint 4.10）。 | `main.py:174` `metrics_endpoint` | — | 0 |
| GET | `/openapi.json` |  | `core/openapi_runtime.py:83` `openapi_json` | — | 0 |
| GET | `/readyz` | 就绪探针：draining→503 / unhealthy 或迁移未完成→503 / 否则 200。 | `api/probes.py:92` `readyz` | — | 0 |
| GET | `/redoc` |  | `core/openapi_runtime.py:97` `redoc_docs` | — | 0 |

