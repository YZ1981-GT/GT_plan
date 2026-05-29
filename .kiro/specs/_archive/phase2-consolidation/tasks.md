# 实现计划：第二阶段集团合并 — 集团架构+组成部分审计师+合并抵消+商誉+少数股东+外币折算+合并报表+合并附注

## 概述

本实现计划将设计文档中的架构和组件拆解为可执行的编码任务，按照数据库→后端服务→前端页面→测试的顺序递进实现。每个任务构建在前序任务之上。技术栈：Python（FastAPI + SQLAlchemy + Celery + Hypothesis）+ TypeScript（Vue 3 + Pinia）。

## 任务

- [x] 1. 数据库迁移：创建12张合并相关表及索引
  - [x] 1.1 创建 Alembic 迁移脚本，定义 `companies` 表（UUID PK、project_id FK、company_code varchar not null、company_name varchar not null、parent_code varchar nullable、ultimate_code varchar not null、consol_level int default 0、shareholding numeric(5,2)、consol_method enum full/equity/proportional、acquisition_date date nullable、disposal_date date nullable、functional_currency varchar default 'CNY'、is_active boolean default true、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, company_code)
    - _需求: 9.1_
  - [x] 1.2 创建 `consol_scope` 表（UUID PK、project_id FK、year int not null、company_code varchar not null、is_included boolean default true、inclusion_reason enum subsidiary/associate/joint_venture/special_purpose、exclusion_reason text nullable、scope_change_type enum none/new_inclusion/exclusion/method_change default none、scope_change_description text nullable、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, company_code)
    - _需求: 9.2_
  - [x] 1.3 创建 `consol_trial` 表（UUID PK、project_id FK、year int not null、standard_account_code varchar not null、account_name varchar、account_category enum、individual_sum numeric(20,2) default 0、consol_adjustment numeric(20,2) default 0、consol_elimination numeric(20,2) default 0、consol_amount numeric(20,2) default 0、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, standard_account_code)
    - _需求: 9.3_
  - [x] 1.4 创建 `elimination_entries` 表（UUID PK、project_id FK、year int not null、entry_no varchar not null、entry_type enum equity/internal_trade/internal_ar_ap/unrealized_profit/other、description text、account_code varchar not null、account_name varchar、debit_amount numeric(20,2) default 0、credit_amount numeric(20,2) default 0、entry_group_id UUID not null、related_company_codes jsonb、is_continuous boolean default false、prior_year_entry_id UUID nullable、review_status enum draft/pending_review/approved/rejected default draft、reviewer_id UUID FK nullable、reviewed_at timestamp nullable、is_deleted boolean、created_at、updated_at、created_by UUID FK）及复合索引 (project_id, year, entry_type) 和 (project_id, entry_group_id)
    - _需求: 9.4_
  - [x] 1.5 创建 `internal_trade` 表（UUID PK、project_id FK、year int not null、seller_company_code varchar not null、buyer_company_code varchar not null、trade_type enum goods/services/assets/other、trade_amount numeric(20,2)、cost_amount numeric(20,2)、unrealized_profit numeric(20,2)、inventory_remaining_ratio numeric(5,4)、description text、is_deleted boolean、created_at、updated_at）及复合索引 (project_id, year)
    - _需求: 9.5_
  - [x] 1.6 创建 `internal_ar_ap` 表（UUID PK、project_id FK、year int not null、debtor_company_code varchar not null、creditor_company_code varchar not null、debtor_amount numeric(20,2)、creditor_amount numeric(20,2)、difference_amount numeric(20,2)、difference_reason text nullable、reconciliation_status enum matched/unmatched/adjusted default unmatched、is_deleted boolean、created_at、updated_at）及复合索引 (project_id, year)
    - _需求: 9.6_
  - [x] 1.7 创建 `goodwill_calc` 表（UUID PK、project_id FK、year int not null、subsidiary_company_code varchar not null、acquisition_date date、acquisition_cost numeric(20,2)、identifiable_net_assets_fv numeric(20,2)、parent_share_ratio numeric(5,4)、goodwill_amount numeric(20,2)、accumulated_impairment numeric(20,2) default 0、current_year_impairment numeric(20,2) default 0、carrying_amount numeric(20,2)、is_negative_goodwill boolean default false、negative_goodwill_treatment text nullable、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, subsidiary_company_code)
    - _需求: 9.7_
  - [x] 1.8 创建 `minority_interest` 表（UUID PK、project_id FK、year int not null、subsidiary_company_code varchar not null、subsidiary_net_assets numeric(20,2)、minority_share_ratio numeric(5,4)、minority_equity numeric(20,2)、subsidiary_net_profit numeric(20,2)、minority_profit numeric(20,2)、minority_equity_opening numeric(20,2)、minority_equity_movement jsonb、is_excess_loss boolean default false、excess_loss_amount numeric(20,2) default 0、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, subsidiary_company_code)
    - _需求: 9.8_
  - [x] 1.9 创建 `forex_translation` 表（UUID PK、project_id FK、year int not null、company_code varchar not null、functional_currency varchar not null、reporting_currency varchar default 'CNY'、bs_closing_rate numeric(10,6)、pl_average_rate numeric(10,6)、equity_historical_rate numeric(10,6)、opening_retained_earnings_translated numeric(20,2)、translation_difference numeric(20,2)、translation_difference_oci numeric(20,2)、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, company_code)
    - _需求: 9.9_
  - [x] 1.10 创建 `component_auditors` 表（UUID PK、project_id FK、company_code varchar not null、firm_name varchar not null、contact_person varchar、contact_info varchar、competence_rating enum reliable/additional_procedures_needed/unreliable、rating_basis text、independence_confirmed boolean default false、independence_date date nullable、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, company_code)
    - _需求: 9.10_
  - [x] 1.11 创建 `component_instructions` 表（UUID PK、project_id FK、component_auditor_id UUID FK、instruction_date date、due_date date、materiality_level numeric(20,2)、audit_scope_description text、reporting_format text、special_attention_items text、instruction_file_path varchar nullable、status enum draft/sent/acknowledged default draft、sent_at timestamp nullable、is_deleted boolean、created_at、updated_at、created_by UUID FK）及索引 (project_id, component_auditor_id)
    - _需求: 9.11_
  - [x] 1.12 创建 `component_results` 表（UUID PK、project_id FK、component_auditor_id UUID FK、received_date date、opinion_type enum unqualified/qualified/adverse/disclaimer、identified_misstatements jsonb、significant_findings text、result_file_path varchar nullable、group_team_evaluation text、needs_additional_procedures boolean default false、evaluation_status enum pending/accepted/requires_followup default pending、is_deleted boolean、created_at、updated_at）及索引 (project_id, component_auditor_id)
    - _需求: 9.12_

- [x] 2. 定义 SQLAlchemy ORM 模型与 Pydantic Schema
  - [x] 2.1 在 `backend/app/models/` 下创建 `consolidation_models.py`，定义12张表对应的 SQLAlchemy ORM 模型（Company、ConsolScope、ConsolTrial、EliminationEntry、InternalTrade、InternalArAp、GoodwillCalc、MinorityInterest、ForexTranslation、ComponentAuditor、ComponentInstruction、ComponentResult），包含所有字段、枚举类型、外键关系
    - _需求: 9.1-9.12_
  - [x] 2.2 在 `backend/app/models/` 下创建 `consolidation_schemas.py`，定义所有 API 请求/响应的 Pydantic Schema（CompanyCreate/Update/Tree、ConsolScopeInput、ConsolTrialRow、EliminationCreate/Update/Summary、InternalTradeCreate、InternalArApCreate、TransactionMatrix、GoodwillInput/Result、MinorityInterestResult、ForexRates/TranslationWorksheet、ComponentAuditorCreate、InstructionCreate、ResultCreate、ComponentDashboard 等）
    - _需求: 1-8_

- [x] 3. 检查点 — 确保数据库迁移和模型定义正确
  - 运行 `alembic upgrade head` 确认迁移成功，确保所有测试通过，如有问题请询问用户。

- [x] 4. 集团架构服务 (GroupStructureService)
  - [x] 4.1 实现 `backend/app/services/group_structure_service.py`：create_company（自动计算consol_level和ultimate_code）、update_company（parent_code变更时级联更新子树）、delete_company（软删除+子公司检查）
    - _需求: 1.1, 1.2, 1.4_
  - [x] 4.2 实现 get_group_tree（递归构建集团架构树）和 validate_structure（循环引用检测DFS、孤立节点检测、parent_code有效性校验）
    - _需求: 1.3, 1.7_
  - [x] 4.3 实现 manage_consol_scope（批量更新合并范围，排除时强制填写exclusion_reason）和 get_consol_scope
    - _需求: 1.5, 1.6_
  - [x] 4.4 实现年中收购/处置逻辑：根据acquisition_date/disposal_date过滤损益表数据的合并期间
    - _需求: 1.8_
  - [x] 4.5 实现集团架构 API 路由 `backend/app/routers/companies.py`：公司CRUD、架构树、结构校验、合并范围管理
    - _需求: 1.1-1.8_

- [x] 5. 组成部分审计师服务 (ComponentAuditorService)
  - [x] 5.1 实现 `backend/app/services/component_auditor_service.py`：create_auditor（强制competence_rating和rating_basis）、update_auditor、get_dashboard（指令/结果状态汇总）
    - _需求: 2.1, 2.2_
  - [x] 5.2 实现 create_instruction、send_instruction（锁定内容+记录sent_at）、get_instructions
    - _需求: 2.3, 2.4_
  - [x] 5.3 实现 receive_result、accept_result（使组成部分审定数可用于合并）、非标准意见高亮逻辑
    - _需求: 2.5, 2.6, 2.7_
  - [x] 5.4 实现组成部分审计师 API 路由 `backend/app/routers/component_auditors.py`：审计师CRUD、指令管理、结果管理、看板
    - _需求: 2.1-2.7_

- [x] 6. 检查点 — 确保集团架构和组成部分审计师服务正确
  - 运行单元测试确认架构树构建、循环引用检测、指令锁定逻辑正确。

- [x] 7. 合并试算表服务 (ConsolTrialService)
  - [x] 7.1 实现 `backend/app/services/consol_trial_service.py`：aggregate_individual（汇总各公司审定数，外币子公司使用折算后金额）
    - _需求: 3.1, 3.2_
  - [x] 7.2 实现 recalc_elimination（增量/全量重算抵消列）和 recalc_consol_amount（合并数=汇总+调整+抵消）
    - _需求: 3.4_
  - [x] 7.3 实现 full_recalc（全量重算兜底）和 check_consistency（一致性校验：汇总数=各公司之和、抵消列=分录汇总、公式正确）
    - _需求: 3.4_
  - [x] 7.4 注册EventBus事件处理器：ELIMINATION_CREATED/UPDATED/DELETED → on_elimination_changed、CONSOL_SCOPE_CHANGED → on_scope_changed、FOREX_TRANSLATED → on_forex_translated、COMPONENT_RESULT_ACCEPTED → on_component_accepted
    - _需求: 3.4_
  - [x] 7.5 实现合并试算表 API 路由 `backend/app/routers/consol_trial.py`：获取合并试算表、触发汇总、全量重算、一致性校验
    - _需求: 3.1-3.4_

- [x] 8. 抵消分录服务 (EliminationService)
  - [x] 8.1 实现 `backend/app/services/elimination_service.py`：create_entry（借贷平衡校验+自动编号CE-001+发布事件）、update_entry（仅draft/rejected可改）、delete_entry（软删除+发布事件）
    - _需求: 3.3, 3.5_
  - [x] 8.2 实现 carry_forward_prior_year（连续编制核心逻辑：复制上年approved分录→设置is_continuous=true→损益科目替换为未分配利润年初→批量写入→触发重算）
    - _需求: 3.6, 3.7_
  - [x] 8.3 实现 change_review_status（复核状态机：draft→pending_review→approved/rejected→draft）和 get_summary（按entry_type分组汇总）
    - _需求: 3.8_
  - [x] 8.4 实现抵消分录 API 路由 `backend/app/routers/eliminations.py`：CRUD、复核、连续编制结转、汇总
    - _需求: 3.3-3.8_

- [x] 9. 内部交易与往来服务 (InternalTradeService)
  - [x] 9.1 实现 `backend/app/services/internal_trade_service.py`：create_trade（自动计算unrealized_profit）、create_ar_ap（自动计算差异和reconciliation_status）
    - _需求: 4.1, 4.2, 4.3, 4.4_
  - [x] 9.2 实现 auto_generate_eliminations（根据内部交易自动生成抵消分录：商品→收入成本抵消+未实现利润抵消，往来→应收应付抵消）
    - _需求: 4.5, 4.6_
  - [x] 9.3 实现 get_transaction_matrix（内部交易矩阵）和 reconcile_ar_ap（批量核对内部往来）
    - _需求: 4.7_
  - [x] 9.4 实现内部交易/往来 API 路由 `backend/app/routers/internal_trades.py`：交易CRUD、往来CRUD、自动生成抵消、交易矩阵、批量核对
    - _需求: 4.1-4.7_

- [x] 10. 商誉计算服务 (GoodwillService)
  - [x] 10.1 实现 `backend/app/services/goodwill_service.py`：calculate_goodwill（商誉=合并成本-净资产公允价值×持股比例，负商誉处理）、record_impairment（记录减值+自动生成减值抵消分录）
    - _需求: 5.1, 5.2, 5.3, 5.4_
  - [x] 10.2 实现 carry_forward（结转上年商誉+累计减值）和 generate_equity_elimination（生成权益抵消分录：借实收资本/资本公积/盈余公积/未分配利润/商誉，贷长期股权投资/少数股东权益）
    - _需求: 5.8_
  - [x] 10.3 实现商誉 API 路由（集成到 `backend/app/routers/consolidation.py`）：商誉列表、计算、减值记录
    - _需求: 5.1-5.4_

- [x] 11. 少数股东权益服务 (MinorityInterestService)
  - [x] 11.1 实现 `backend/app/services/minority_interest_service.py`：calculate（少数股东权益=净资产×少数持股比例，少数股东损益=净利润×少数持股比例，超额亏损处理）
    - _需求: 5.5, 5.6, 5.7_
  - [x] 11.2 实现 batch_calculate（批量计算所有全额合并子公司）和 generate_elimination（生成少数股东权益/损益抵消分录）
    - _需求: 5.5, 5.8_
  - [x] 11.3 实现少数股东权益 API 路由（集成到 `backend/app/routers/consolidation.py`）：列表、批量计算
    - _需求: 5.5-5.8_

- [x] 12. 外币折算服务 (ForexTranslationService)
  - [x] 12.1 实现 `backend/app/services/forex_translation_service.py`：translate（资产负债→期末汇率、损益→平均汇率、权益→历史汇率、未分配利润→公式推算、折算差额→其他综合收益）
    - _需求: 6.1, 6.2, 6.3, 6.4_
  - [x] 12.2 实现 get_translation_worksheet（折算工作表：原币|汇率|折算额）和 apply_to_consol_trial（折算后金额替换到合并试算表）
    - _需求: 6.5, 6.6_
  - [x] 12.3 实现外币折算 API 路由（集成到 `backend/app/routers/consolidation.py`）：折算列表、执行折算、折算工作表
    - _需求: 6.1-6.6_

- [x] 13. 检查点 — 确保所有后端服务正确
  - 运行单元测试确认：商誉计算、少数股东权益计算、外币折算、内部交易抵消分录自动生成、连续编制逻辑。

- [x] 14. 合并报表服务 (ConsolReportService)
  - [x] 14.1 实现 `backend/app/services/consol_report_service.py`：generate_consol_reports（复用Phase 1 Report_Engine，数据源切换为consol_trial.consol_amount，新增商誉/少数股东权益/少数股东损益行次）
    - _需求: 7.1, 7.2_
  - [x] 14.2 实现 generate_consol_workpaper（生成合并底稿.xlsx：各公司审定数并列+抵消分录汇总+合并试算表+勾稽校验）
    - _需求: 7.3_
  - [x] 14.3 实现 verify_balance（合并资产负债表平衡校验）和 export_to_excel（导出合并报表和底稿）
    - _需求: 7.4, 7.5, 7.6_
  - [x] 14.4 实现合并报表 API 路由 `backend/app/routers/consol_reports.py`：生成合并报表、获取报表、生成底稿、导出Excel
    - _需求: 7.1-7.6_

- [x] 15. 合并附注服务 (ConsolDisclosureService)
  - [x] 15.1 实现 `backend/app/services/consol_disclosure_service.py`：generate_consol_notes（生成合并范围说明、子公司信息表、范围变动说明、商誉披露、少数股东权益披露、内部交易抵消说明、外币折算披露）
    - _需求: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  - [x] 15.2 实现 integrate_with_notes（将合并附注插入Phase 1附注体系的适当位置）
    - _需求: 8.7_
  - [x] 15.3 实现合并附注 API 路由 `backend/app/routers/consol_notes.py`：生成合并附注、获取合并附注
    - _需求: 8.1-8.7_

- [x] 16. 前端：集团架构管理页面
  - [x] 16.1 创建 `frontend/src/components/consolidation/GroupStructureTree.vue`：集团架构树组件（可展开/折叠、节点显示公司名+持股比例+合并方法色标、右键菜单新增/编辑/删除）
    - _需求: 1.3_
  - [x] 16.2 创建 `frontend/src/components/consolidation/CompanyForm.vue`：公司信息表单（三码+持股比例+合并方法+收购/处置日期+功能货币）
    - _需求: 1.1_
  - [x] 16.3 创建 `frontend/src/components/consolidation/ConsolScopeTable.vue`：合并范围管理表格（纳入/排除状态+批量操作+变动说明）
    - _需求: 1.5, 1.6_

- [x] 17. 前端：组成部分审计师管理页面
  - [x] 17.1 创建 `frontend/src/components/consolidation/ComponentAuditorPanel.vue`：三栏布局（审计师列表|指令管理|结果管理），审计师卡片含资质评级色标
    - _需求: 2.1, 2.2_
  - [x] 17.2 创建 `frontend/src/components/consolidation/InstructionForm.vue`：审计指令创建/发送表单
    - _需求: 2.3, 2.4_
  - [x] 17.3 创建 `frontend/src/components/consolidation/ComponentResultForm.vue`：审计结果录入/评价表单，非标准意见红色高亮
    - _需求: 2.5, 2.6, 2.7_

- [x] 18. 前端：合并试算表与抵消分录页面
  - [x] 18.1 创建 `frontend/src/components/consolidation/ConsolTrialBalance.vue`：合并试算表（科目编码|名称|各公司审定数可展开|汇总|调整|抵消|合并数，按类别分组+小计+借贷平衡校验）
    - _需求: 3.1, 3.4_
  - [x] 18.2 创建 `frontend/src/components/consolidation/EliminationEntryForm.vue`：抵消分录创建/编辑弹窗（类型选择+动态借贷行+关联公司选择+借贷平衡实时校验）
    - _需求: 3.3, 3.5_
  - [x] 18.3 创建 `frontend/src/components/consolidation/EliminationList.vue`：抵消分录列表（Tab按类型切换+复核状态标签+连续编制结转按钮+批量审批）
    - _需求: 3.6, 3.8_

- [x] 19. 前端：内部交易/往来页面
  - [x] 19.1 创建 `frontend/src/components/consolidation/InternalTradePanel.vue`：内部交易管理（表格+交易矩阵视图切换+自动生成抵消分录按钮）
    - _需求: 4.1, 4.5, 4.7_
  - [x] 19.2 创建 `frontend/src/components/consolidation/InternalArApPanel.vue`：内部往来对账（对账表格+差异高亮+一键核对+自动生成抵消分录）
    - _需求: 4.3, 4.4, 4.7_

- [x] 20. 前端：商誉/少数股东/外币折算页面
  - [x] 20.1 创建 `frontend/src/components/consolidation/GoodwillPanel.vue`：商誉计算表（合并成本/净资产公允价值/商誉/减值/账面价值）+减值录入
    - _需求: 5.1-5.4_
  - [x] 20.2 创建 `frontend/src/components/consolidation/MinorityInterestPanel.vue`：少数股东权益明细（净资产/持股比例/权益/损益/变动）+批量计算
    - _需求: 5.5-5.7_
  - [x] 20.3 创建 `frontend/src/components/consolidation/ForexTranslationPanel.vue`：外币折算工作表（原币|汇率|折算额|折算差额）+汇率输入
    - _需求: 6.1-6.6_

- [x] 21. 前端：合并报表与附注页面
  - [x] 21.1 创建 `frontend/src/views/consolidation/ConsolReportView.vue`：合并报表展示（复用Phase 1报表组件，新增商誉/少数股东行次+合并底稿下载+同比分析）
    - _需求: 7.1-7.6_
  - [x] 21.2 创建 `frontend/src/views/consolidation/ConsolNotesView.vue`：合并附注展示（合并范围+子公司信息+商誉+少数股东+内部交易+外币折算披露）
    - _需求: 8.1-8.7_

- [x] 22. 前端：路由与状态管理
  - [x] 22.1 在 `frontend/src/router/` 中注册合并模块路由（/projects/{id}/consolidation/*），在 `frontend/src/stores/` 中创建 consolidation store（Pinia）管理合并相关状态
    - _需求: 1-8_
  - [x] 22.2 在项目详情页面添加"集团合并"导航入口，根据项目是否为集团项目动态显示
    - _需求: 1-8_

- [x] 23. 前端：API服务层
  - [x] 23.1 在 `frontend/src/services/` 中创建 `consolidationApi.ts`，封装所有合并相关API调用（companies、consol-scope、consol-trial、eliminations、internal-trades、internal-ar-ap、goodwill、minority-interest、forex-translation、consol-reports、consol-notes、component-auditors）
    - _需求: 1-8_

- [x] 24. 检查点 — 确保前端页面和API集成正确
  - 运行前端开发服务器 `npm run dev`，在浏览器中逐一测试：集团架构树的增删改查、合并范围状态切换、抵消分录录入和复核流程、内部交易自动生成抵消、交易矩阵展示、商誉和少数股东权益计算、外币折算、合并报表生成。

- [x] 25. 后端单元测试
  - [x] 25.1 编写 `backend/tests/test_group_structure.py`：测试集团架构树构建、循环引用检测、consol_level自动计算、合并范围管理
    - _需求: 1.2, 1.4, 1.7_
  - [x] 25.2 编写 `backend/tests/test_elimination_service.py`：测试抵消分录CRUD、借贷平衡校验、连续编制结转（损益科目替换）、复核状态机
    - _需求: 3.3-3.8_
  - [x] 25.3 编写 `backend/tests/test_consol_trial.py`：测试合并试算表汇总计算、抵消列重算、公式不变量、一致性校验
    - _需求: 3.1, 3.2, 3.4_
  - [x] 25.4 编写 `backend/tests/test_internal_trade.py`：测试未实现利润计算、内部往来差异计算、自动生成抵消分录
    - _需求: 4.2, 4.4, 4.5_
  - [x] 25.5 编写 `backend/tests/test_goodwill_minority.py`：测试商誉计算公式（含负商誉）、少数股东权益计算（含超额亏损）、权益抵消分录生成
    - _需求: 5.2, 5.3, 5.6, 5.7_
  - [x] 25.6 编写 `backend/tests/test_forex_translation.py`：测试外币折算规则（资产负债→期末汇率、损益→平均汇率、权益→历史汇率）、折算差额计算、折算后平衡校验
    - _需求: 6.2, 6.3_
  - [x] 25.7 编写 `backend/tests/test_component_auditor.py`：测试指令发送锁定、结果接收、非标准意见处理
    - _需求: 2.4, 2.6_
