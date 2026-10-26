# 00 · 高级查询联动体检：事实基线与证据索引

> 调查日期：2026-10-26。工作区 `d:\GT_plan`。本步只做诊断：未改生产代码、配置、迁移与 spec；真实（非【测试】）项目数据只做 SELECT 与只读 API 调用。
> 本步唯一的写入：①以 admin 新建 2 个名称带「【测试】AQ探针」的查询模板（public/global 两种 scope）并立即删除；②浏览器里点一次「保存为模板」（后端 500，未落库）。`custom_query_templates` 探针前后均为 0 行（`evidence/export_check.json`）。
> cell-writeback 跨项目探针刻意用会被列校验拒绝的 A1 单元格，并对【UAT】子公司B 的 4 行 trial_balance 做了前后逐值比对：未变化（`evidence/api_writeback_idor_acnr.txt`）。

## 1. 代码与运行基线

| 项 | 事实 |
|---|---|
| HEAD | `b5fc200e0d5bad2c580f5304c1d00caaa5537277`（分支 `spec/disclosure-note-doc-upload-and-batch-fill`） |
| 工作树 | 有并发会话的 S 循环改动；高级查询相关路径 `git status` 为空（routers/custom_query*.py、query_builder.py、services/custom_query/、AdvancedQueryBuilder.vue、CustomQuery.vue、components/query、components/custom-query、CustomQueryTab.vue、useQueryBuilderAccess.ts、ThreeColumnLayout.vue）⇒ 源码结论即 HEAD |
| 运行 | 后端 9980 `/api/health` healthy（setup 步实测）；前端 3030 返回 200；未重启 start-dev |
| 模板表 | `custom_query_templates` 列：id / name / description / data_source / config / scope / created_by / created_at / updated_at / tags / use_count / creator_id / last_used_at / shared_project_ids；约束只有 PK 与 created_by FK，**没有** scope CHECK（`backend/scripts/_ensure_custom_query_tables.py` 声明的 `ck_custom_query_templates_scope` 未落库） |
| 缺失表 | `wp_template_registry` 在库中不存在，迁移目录与 ORM 也无此表（`address-resolve` 引用它） |
| 索引 | `idx_wp_parsed_data_gin` 存在，但 `/index-health` 返回 size_bytes=null |
| LibreOffice | `C:\Program Files\LibreOffice\program\soffice.exe` 存在（查询路径的重算覆盖分支在本机可触发） |

## 2. 对任务前提的更正（影响后续设计）

1. **0ec33ac9（重药控股安徽有限公司_2025）不在 projects 表**。性能与大表用例改用现库最大项目 **重庆和平药房连锁有限责任公司_2025（5942c12e）**：tb_ledger 1,147,414 / tb_aux_balance 127,618 / tb_balance 402（active 数据集）/ 附注 166 节 / 底稿 107。
2. **projects 有 `audit_year` 列**（V055）。平台权威年度是 `backend/app/services/project_audit_year.py::resolve_project_audit_year` 与 `PROJECT_AUDIT_YEAR_SQL`：audit_year → audit_period_end → audit_period_start → wizard_state → 名称 `_YYYY`。现库 85 个未删项目中 audit_year 非空 12、audit_period_end 非空 4；本次用到的数据项目 audit_year 全为 2025、audit_period_end 全为 NULL ⇒ 只用 `EXTRACT(YEAR FROM audit_period_end)` 会得到 NULL。后续修年度问题应复用 resolver，不要另写公式。
3. **Metabase 不在范围内**：`MetabaseDashboard.vue` / `DrillDownNavigator.vue` 在任何路由、页面、模板里零挂载，用户看不到；embed-url 鉴权问题归原 spec。
4. **归档 spec 的「7 个零引用模块」现已全部有生产 importer**；`param_sql_builder` 被 `builder_dsl` 调用，`cross_sheet_trace_orchestrator` 被 `GET /api/custom-query/cross-sheet-trace` 调用（该端点没有前端调用方）。裁决见 `report.md` §4。

## 3. 数据基线（只读 SELECT，现算）

| 表 / 指标 | 值 |
|---|---|
| projects | 142 行（未删 85、已删 57） |
| tb_balance / tb_ledger / tb_aux_balance | 117,606 / 9,608,941 / 920,715 |
| 未删项目的 tb_aux_ledger | 4,470,438 |
| trial_balance | 743（全部 is_deleted=false） |
| financial_report | 2,464（7 个项目 × 352） |
| report_snapshot | **0** |
| disclosure_notes | 1,090 |
| adjustments | 37（未删项目仅华氏 2 条 aje / draft） |
| consol_worksheet_data / consol_scope（未删）/ consol_trial | 1 / 0 / 0 |
| custom_query_templates / work_hours | 0 / 0 |
| ledger_datasets | active 44 · superseded 26 · failed 19 |
| working_paper（未删项目） | 1,738，其中带 `univer_snapshot` 的 **0** |
| users | admin 9 · auditor 114 · manager 1（e2e_manager）· partner 1（e2e_partner_na）；无 qc / readonly / eqcr 用户 |
| project_users | 105 行 / 69 个项目；下表 7 个数据项目都没有 project_users 行 |

本次用到的项目：

| 代号 | 项目 | id 前缀 | 用途 |
|---|---|---|---|
| HS | 陕西华氏医药有限公司_2025 | 005a6f2d | TB 100 行、报表 352 行、附注 186 节、AJE 2 条、底稿 172 |
| HP | 重庆和平药房连锁有限责任公司_2025 | 5942c12e | 序时账 1,147,414 行（现库最大） |
| YB | 重庆医药集团宜宾医药有限公司新健康大药房临港店_2025 | 14fb8c10 | tb_balance：812 行无数据集 + 812 行 active 数据集 |
| UAT_A / UAT_B | 【UAT】子公司A / 子公司B | 0c0f8b87 / a3132905 | 模板执行、跨项目回写探针目标（合成数据） |
| PM | proj_fa90f498 | 65a9afa5 | u_011abb97dd2d4101（系统角色 auditor，项目角色 manager，edit） |

对账用的库内真值（`evidence/db_ground_truth.json`、`db_dataset_visibility.json`、`api_source_matrix.txt`）：

- HS trial_balance：100 行，Σ审定数 2,033,180,355.49；1001 审定 100.00 / 未审 0.00；1002 审定 −297,771,268.89 / 未审 −297,771,168.89；1122 审定 6,290,044,665.30。
- HS financial_report：BS-002 货币资金本期 822,999,085.83；资产负债表 129 行（32 行非零）、利润表 78 行（14 行非零）。
- YB tb_balance：只按 is_deleted=false 取 1,624 行 / Σ期末 −1,318,963.36；按 active 数据集取 812 行 / −659,481.68。
- HP tb_ledger：1,147,414 行；Σ借 = Σ贷 = 10,241,344,771.55；最大单笔借方 241,944,666.92（2025-03-31 #0223 科目 1651.02）；科目 1002：Σ借 3,245,484,243.16 / 116,443 行；日期 2025-01-01 至 2025-10-31。
- HS / HP 附注章节编号为「一、1」「八、1」体系；指标树附注叶子为「五-1-1」体系，交集 0（`evidence/disclosure_id_mismatch.json`）。
- HS account_chart：100 个科目码各有 client + standard 两行（如 4101 盈余公积）⇒ `trial_balance LEFT JOIN account_chart` 100 行变 200 行（`evidence/db_join_fanout_nulls.json`）。
- HP tb_ledger：借方为 NULL 的行 543,615 / 1,147,414（贷方分录）。
- 构建器 SQL 聚合本身口径正确：HP 科目 1002 Σ借 3,245,484,243.16 / 116,443 行、全表 Σ借 = Σ贷 = 10,241,344,771.55 / 1,147,414 行，与库内逐值一致（`evidence/api_builder_sql_join.txt`）。
- 四川物流（299f8a28）tb_balance 1,626 行挂在 2 个 ledger_datasets 里不存在的数据集 id 上——属数据治理问题，get_active_filter 也会回落到不过滤，记录备查。

## 4. 证据索引

活体 API 探针（除注明外均为 admin token 实发请求，输出在 `evidence/`）：

| 文件 | 内容 |
|---|---|
| `api_builder_admin.txt` | 构建器 schema / preview / execute / export；TB 对账；默认列；aux 400 |
| `api_business_view_admin.txt` | 指标树（depth=1 / 全量 / branch）；各数据源 execute 与 DB 对账；500 复现；module-cell；wp-id-by-code / address-resolve / index-health / cross-sheet-trace / batch-execute；构建器大表与跨项目；地址库校验 TB() |
| `api_roles_templates.txt` | 未登录、审计员（非成员 / 项目成员）、系统 manager、partner、admin 逐端点状态码；模板五种 scope 的增删改查与执行 |
| `api_writeback_idor_acnr.txt` | cell-writeback 跨项目定位探针（非变更）与 UAT_B 前后比对；ACNR acnr_targets 有无对比 |
| `api_source_matrix.txt` | 指标树每个非懒加载叶子的执行矩阵（声明列 vs 实际列）；条件键 / columns 参数；module-cell 区间；manager 隔离；TB() 求值；模板 scope 归一函数；服务模块 importer 扫描 |
| `api_builder_sql_join.txt` | 构建器 SQL 分组 / 求和与库内对账；DESC 排序空值在前；JOIN account_chart 行重复；between；预算 400；limit>1000 → 422；offset |
| `audit_log_check.json` | 本次探针触发的高级查询审计事件在 audit_log_entries 中的落库情况；Redis 审计队列积压 |
| `db_*.json` | 只读 SELECT：数据集可见性、库内真值、500 根因复现、杂项计数 |
| `disclosure_id_mismatch.json` / `export_check.json` | 附注编号交集；导出文件行数与表头、模板表计数 |
| `tests_pytest.txt` / `tests_vitest.txt` | 既有测试现跑结果 |

浏览器实测（自建标签页、admin，截图在 `browser/`）：

| 截图 | 场景 |
|---|---|
| B1-dialog-open-from-project-page | 华氏试算表页打开侧栏「高级查询」：项目、年度 2025、构建器页签 |
| B2-report-balance-sheet-amounts-blank | 资产负债表 129 行，货币资金本期金额「-」 |
| B3 / B3b-adjustment-*-500 | AJE / 重分类：接口 500，界面「查询无结果」「暂无该数据源记录」 |
| B4-report-lines-500 | 报表行次：同上 |
| B5-disclosure-columns-misaligned | 附注叶子「五-1-1 货币资金」0 行 |
| B6-tb-summary-empty-for-standalone | 科目明细 100 行，按科目名称排序 |
| B7-account-balance-double-count | 临港店科目余额表：1001 / 1002 各出现两次；「已达上限 500 行」而接口 total=1,624 |
| B8-builder-all-projects-no-project-context | 项目页内构建器查 trial_balance：全项目范围提示、下钻 0 处、公式引用 100 处 |
| B10-trace-to-template-500 | 底稿 A1 行右键「跳模板溯源」：500 +「服务器暂时异常，正在重试…」 |
| B11-tab-ledger-total-5000 | /custom-query 页序时账：「本页 100 条 / 共 5000 条」 |
| B12 / B12a-tab-condition-* | 条件「借方发生额 > 1 亿」不生效；条件值输入框宽度 0 |
| B13-template-save-private-500 | 「保存为模板 / 仅我可见」→ 500，对话框不关 |
| B14-dialog-stale-project-after-navigation | 华氏页打开并关闭弹窗，应用内切到和平药房页再打开：项目仍是华氏 |

## 5. 没能实测、留待实施时验证

- 真实写入：cell-writeback 的 G 列写入、writeback-confirm 均未执行（避免改写数据）；跨项目问题以「已定位并加锁他项目行、仅被列校验拦下」的非变更探针证明。writeback-confirm 的确认门对非底稿目标是否放行，未实测。
- 合并项目查询（`consol_unit:*`、`ws_*`、合并附注）：现库 consol_scope 0 行，无法实测。
- LibreOffice 重算覆盖 storage xlsx：代码确认，未触发（避免改写真实底稿）。
- 公式管理 / 底稿公式对 `TB('code','审定数')` 的实际求值口径：legacy `/api/formula/execute` 对 1001 返回 0.0（行内审定 100.00），但该端点没有前端调用方。
- qc / readonly / eqcr：库内没有此类用户，只按代码判定（均不在构建器角色内）。
- 分组 / 透视：前端没有入口，只做了 API 实测。
- 指定的最大项目 0ec33ac9 不存在，性能以和平药房代替：本次所有查询 0.7–1.1 s（序时账被 5,000 行上限截断，详见 AQ-03）。
