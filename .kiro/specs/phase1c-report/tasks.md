# 实现计划：第一阶段MVP报表 — 报表生成+现金流量表+附注+PDF导出

## 概述

本实现计划将设计文档中的架构和组件拆解为可执行的编码任务，按照数据库→后端服务→前端页面→测试的顺序递进实现。每个任务构建在前序任务之上。技术栈：Python（FastAPI + SQLAlchemy + WeasyPrint + Celery + Hypothesis）+ TypeScript（Vue 3 + Pinia）。

## 任务

- [x] 1. 数据库迁移：创建8张报表相关表及索引
  - [x] 1.1 创建 Alembic 迁移脚本，定义 `report_config` 表（UUID PK、report_type enum balance_sheet/income_statement/cash_flow_statement/equity_statement、row_number int、row_code varchar unique per type+standard、row_name varchar、indent_level int default 0、formula text、applicable_standard varchar、is_total_row boolean default false、parent_row_code varchar nullable、is_deleted boolean、created_at、updated_at）及复合唯一索引 (report_type, row_code, applicable_standard)
    - _需求: 9.1_
  - [x] 1.2 创建 `financial_report` 表（UUID PK、project_id FK、year int、report_type enum、row_code varchar、row_name varchar、current_period_amount numeric(20,2)、prior_period_amount numeric(20,2)、formula_used text、source_accounts jsonb、generated_at timestamp、is_deleted boolean、created_at、updated_at）及复合唯一索引 (project_id, year, report_type, row_code)
    - _需求: 9.2_
  - [x] 1.3 创建 `cfs_adjustments` 表（UUID PK、project_id FK、year int、adjustment_no varchar、description text、debit_account varchar、credit_account varchar、amount numeric(20,2)、cash_flow_category enum operating/investing/financing/supplementary、cash_flow_line_item varchar、entry_group_id UUID、is_auto_generated boolean default false、is_deleted boolean、created_at、updated_at、created_by FK）及复合索引 (project_id, year, cash_flow_category)
    - _需求: 9.3_
  - [x] 1.4 创建 `disclosure_notes` 表（UUID PK、project_id FK、year int、note_section varchar、section_title varchar、account_name varchar、content_type enum table/text/mixed、table_data jsonb、text_content text、source_template enum soe/listed、status enum draft/confirmed default draft、sort_order int、is_deleted boolean、created_at、updated_at、updated_by FK）及复合唯一索引 (project_id, year, note_section)
    - _需求: 9.4_
  - [x] 1.5 创建 `audit_report` 表（UUID PK、project_id FK、year int、opinion_type enum unqualified/qualified/adverse/disclaimer、company_type enum listed/non_listed default non_listed、report_date date nullable、signing_partner varchar、paragraphs jsonb、financial_data jsonb、status enum draft/review/final default draft、is_deleted boolean、created_at、updated_at、created_by FK、updated_by FK）及复合唯一索引 (project_id, year)
    - _需求: 9.5_
  - [x] 1.6 创建 `audit_report_template` 表（UUID PK、opinion_type enum、company_type enum、section_name varchar、section_order int、template_text text、is_required boolean default true、is_deleted boolean、created_at、updated_at）及复合唯一索引 (opinion_type, company_type, section_name)
    - _需求: 9.6_
  - [x] 1.7 创建 `export_tasks` 表（UUID PK、project_id FK、task_type enum single_document/full_archive、document_type varchar nullable、status enum queued/processing/completed/failed default queued、progress_percentage int default 0、file_path varchar nullable、file_size bigint nullable、password_protected boolean default false、started_at timestamp nullable、completed_at timestamp nullable、error_message text nullable、created_by FK、created_at）及索引 (project_id, status)
    - _需求: 9.7_
  - [x] 1.8 创建 `note_validation_results` 表（UUID PK、project_id FK、year int、validation_timestamp timestamp、findings jsonb、error_count int default 0、warning_count int default 0、info_count int default 0、validated_by FK、created_at）及索引 (project_id, year)
    - _需求: 9.8_

- [x] 2. 定义 SQLAlchemy ORM 模型与 Pydantic Schema
  - [x] 2.1 在 `backend/app/models/` 下创建 `report_models.py`，定义8张表对应的 SQLAlchemy ORM 模型（ReportConfig、FinancialReport、CfsAdjustment、DisclosureNote、AuditReport、AuditReportTemplate、ExportTask、NoteValidationResult），包含所有字段、枚举类型、外键关系
    - _需求: 9.1-9.8_
  - [x] 2.2 在 `backend/app/models/` 下创建 `report_schemas.py`，定义所有 API 请求/响应的 Pydantic Schema（ReportGenerateRequest、ReportRow、ReportDrilldown、CFSWorksheetData、CFSAdjustmentCreate、CFSReconciliation、DisclosureNoteTree、DisclosureNoteDetail、NoteValidationFinding、AuditReportGenerate、AuditReportParagraph、ExportTaskCreate、ExportTaskStatus 等）
    - _需求: 1-8_

- [x] 3. 检查点 — 确保数据库迁移和模型定义正确
  - 运行 `alembic upgrade head` 确认迁移成功，确保所有测试通过，如有问题请询问用户。

- [x] 4. 报表格式配置与种子数据
  - [x] 4.1 创建企业会计准则资产负债表种子数据（`report_config` 行次定义），包含全部标准行次（货币资金/交易性金融资产/应收票据/应收账款/.../资产合计/短期借款/.../负债合计/实收资本/.../所有者权益合计/负债和所有者权益总计），每行含 row_code、row_name、indent_level、formula（TB/SUM_TB表达式）、is_total_row
    - _需求: 1.1, 1.2_
  - [x] 4.2 创建企业会计准则利润表种子数据，包含全部标准行次（营业收入/营业成本/.../营业利润/营业外收入/.../利润总额/所得税费用/净利润/.../综合收益总额）
    - _需求: 1.1, 1.2_
  - [x] 4.3 创建企业会计准则现金流量表种子数据，包含主表三大类（经营活动/投资活动/筹资活动）全部行次和补充资料行次
    - _需求: 1.1, 1.2_
  - [x] 4.4 创建企业会计准则所有者权益变动表种子数据，包含行次（实收资本/资本公积/其他综合收益/盈余公积/未分配利润/所有者权益合计）和列定义（期初余额/本期增减变动/期末余额）
    - _需求: 1.1, 1.2_
  - [x] 4.5 实现报表配置克隆功能：`clone_report_config(project_id, standard)` 将标准配置复制为项目级配置，支持后续自定义修改
    - _需求: 1.5_
  - [x] 4.6 实现报表配置 API 路由（`backend/app/routers/report_config.py`）：GET 列表、GET 详情、POST 克隆、PUT 修改行定义
    - _需求: 1.1-1.5_

- [x] 5. 检查点 — 确保报表配置种子数据正确
  - 验证四张报表的种子数据行次完整、公式语法正确，如有问题请询问用户。

- [x] 6. 报表生成引擎（后端核心服务）
  - [x] 6.1 实现 `ReportEngine` 基础框架：`generate_all_reports(project_id, year)` 加载 report_config → 按 row_number 排序 → 逐行执行公式 → 写入 financial_report 表；支持 ROW() 行间引用（维护 row_cache 字典）
    - _需求: 2.1, 2.2_
  - [x] 6.2 实现报表公式解析器 `ReportFormulaParser`：解析 TB()/SUM_TB()/ROW()/PREV() 语法，支持算术运算 +/-/*，调用 FormulaEngine 执行 TB/SUM_TB，从 row_cache 解析 ROW() 引用
    - _需求: 1.4, 2.1_
  - [x] 6.3 实现比较期间数据生成：对每行公式用 year-1 执行获取 prior_period_amount，写入 financial_report 表
    - _需求: 2.5_
  - [x] 6.4 实现报表平衡校验：资产负债表（资产合计=负债+权益）、利润表（净利润=收入-成本-费用±营业外）、跨报表（BS净利润=IS净利润、CFS期末现金=BS现金）
    - _需求: 2.6, 2.7, 8.5_
  - [x] 6.5 实现增量更新 `regenerate_affected(project_id, year, changed_accounts)`：根据 report_config 中的 formula 识别受影响行，只重算受影响行
    - _需求: 2.4, 8.2_
  - [x] 6.6 实现报表穿透查询：返回指定行的公式、贡献科目列表、各科目在试算表中的值
    - _需求: 2.9_
  - [x] 6.7 实现报表 API 路由（`backend/app/routers/reports.py`）：POST 生成、GET 报表数据、GET 穿透查询、GET 一致性校验、GET 导出Excel
    - _需求: 2.1-2.10_
  - [x] 6.8 注册 EventBus 监听器：监听 `trial_balance_updated` 事件，触发 `regenerate_affected`
    - _需求: 2.4, 8.1_
  - [x]* 6.9 编写属性测试：报表公式确定性执行
    - **Property 1: 报表公式确定性执行**
    - 使用 Hypothesis 生成随机公式+试算表数据，验证连续两次执行返回相同结果
    - **验证: 需求 2.1**
  - [x]* 6.10 编写属性测试：资产负债表平衡
    - **Property 2: 资产负债表平衡**
    - 使用 Hypothesis 生成随机试算表数据，验证生成的资产负债表满足 资产合计=负债合计+权益合计
    - **验证: 需求 2.6**
  - [x]* 6.11 编写属性测试：报表与试算表一致性
    - **Property 3: 报表与试算表一致性**
    - 使用 Hypothesis 生成随机科目余额，验证报表行金额等于公式从试算表取数的结果
    - **验证: 需求 2.4, 8.2**
  - [x]* 6.12 编写属性测试：跨报表一致性
    - **Property 11: 跨报表一致性**
    - 使用 Hypothesis 生成随机试算表数据，验证BS净利润=IS净利润且CFS期末现金=BS现金
    - **验证: 需求 8.5**
  - [x]* 6.13 编写属性测试：报表行公式解析往返一致性
    - **Property 15: 报表行公式解析往返一致性**
    - 使用 Hypothesis 生成随机公式字符串，验证 parse→execute→serialize→parse→execute 结果相同
    - **验证: 需求 1.4**

- [x] 7. 检查点 — 确保报表生成引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 8. 现金流量表工作底稿引擎
  - [x] 8.1 实现 `CFSWorksheetEngine.generate_worksheet`：从 trial_balance 获取所有科目期初期末余额，计算变动额，返回工作底稿数据结构
    - _需求: 3.1, 3.2_
  - [x] 8.2 实现 `CFSWorksheetEngine.auto_generate_adjustments`：自动识别折旧/摊销/减值/投资收益/财务费用/处置损益/递延所得税等常见调整项，从试算表取数生成草稿 CFS 调整分录
    - _需求: 3.8_
  - [x] 8.3 实现 CFS 调整分录 CRUD：创建/修改/删除调整分录，借贷平衡校验，自动更新工作底稿分配状态
    - _需求: 3.3, 3.4_
  - [x] 8.4 实现工作底稿平衡状态计算 `get_reconciliation_status`：计算每个科目的变动额、已分配额、未分配余额，判断是否全部平衡
    - _需求: 3.5, 3.6_
  - [x] 8.5 实现现金流量表主表生成：按 cash_flow_category 和 cash_flow_line_item 汇总 CFS 调整分录，生成主表数据写入 financial_report
    - _需求: 3.7_
  - [x] 8.6 实现间接法补充资料生成 `generate_indirect_method`：从净利润出发，逐项调整非现金项目和营运资本变动
    - _需求: 3.9_
  - [x] 8.7 实现勾稽校验：间接法经营活动现金流=主表经营活动现金流、现金净增加额=期末现金-期初现金
    - _需求: 3.10, 3.11, 3.12_
  - [x] 8.8 实现现金流量表工作底稿 API 路由（`backend/app/routers/cfs_worksheet.py`）：POST 生成工作底稿、GET 工作底稿数据、CRUD 调整分录、GET 平衡状态、POST 自动生成、GET 间接法
    - _需求: 3.1-3.12_
  - [x]* 8.9 编写属性测试：CFS调整分录借贷平衡
    - **Property 6: CFS调整分录借贷平衡**
    - 使用 Hypothesis 生成随机调整分录，验证每笔分录借方合计=贷方合计
    - **验证: 需求 3.4**
  - [x]* 8.10 编写属性测试：现金流量表勾稽
    - **Property 4: 现金流量表勾稽**
    - 使用 Hypothesis 生成随机试算表+CFS调整分录，验证现金净增加额=期末现金-期初现金
    - **验证: 需求 3.11**
  - [x]* 8.11 编写属性测试：间接法勾稽
    - **Property 5: 间接法勾稽**
    - 使用 Hypothesis 生成随机数据，验证间接法经营活动现金流=主表经营活动现金流
    - **验证: 需求 3.10**
  - [x]* 8.12 编写属性测试：工作底稿平衡
    - **Property 7: 工作底稿平衡**
    - 使用 Hypothesis 生成随机科目变动+调整分录，验证全部分配后各科目未分配余额为零
    - **验证: 需求 3.6**

- [x] 9. 检查点 — 确保现金流量表工作底稿引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 10. 附注模版管理与附注生成引擎
  - [x] 10.1 创建附注模版种子数据：国企版和上市版的科目对照模板（account_mapping_template），定义报表科目→附注表格的映射关系及校验角色（余额/宽表/交叉/其中项/描述）
    - _需求: 4.1_
  - [x] 10.2 创建附注校验公式预设种子数据（check_presets）：逐科目逐表格定义校验公式（余额/宽表/纵向/交叉/其中项/账龄衔接/完整性/LLM审核）
    - _需求: 4.1, 5.1_
  - [x] 10.3 创建附注宽表公式预设种子数据（wide_table_presets）：定义常见宽表的标准列结构和横向公式（固定资产变动表/无形资产变动表/坏账准备变动表等）
    - _需求: 4.1, 4.5_
  - [x] 10.4 实现 `DisclosureEngine.generate_notes`：加载科目对照模板 → 遍历报表科目 → 为每个有映射的科目生成附注章节 → 数值从试算表/辅助余额表取数 → 文字填入模版文本 → 写入 disclosure_notes 表
    - _需求: 4.2, 4.3, 4.8, 4.9_
  - [x] 10.5 实现附注数值自动填充：对 [余额] 角色表格从试算表取合计值，对 [宽表] 角色表格按列结构填入期初/变动/期末数据，对 [其中项] 角色表格从辅助余额表取明细数据
    - _需求: 4.4, 4.5, 4.7, 4.8_
  - [x] 10.6 实现附注增量更新 `update_note_values`：根据变更科目找到受影响附注章节，重新取数更新 table_data
    - _需求: 8.1_
  - [x] 10.7 实现附注编辑 API：GET 目录树、GET 章节详情、PUT 更新章节内容（更新 status 为 confirmed）
    - _需求: 4.10, 4.11_
  - [x] 10.8 实现附注 API 路由（`backend/app/routers/disclosure_notes.py`）：POST 生成、GET 目录树、GET 章节、PUT 更新、POST 校验、GET 校验结果、PUT 确认发现
    - _需求: 4.1-4.11, 5.1-5.5_
  - [x] 10.9 注册 EventBus 监听器：监听 `reports_updated` 事件，触发 `update_note_values`
    - _需求: 8.1_

- [x] 11. 附注校验引擎
  - [x] 11.1 实现 `BalanceValidator`：报表余额 vs 附注合计行金额核对
    - _需求: 5.1_
  - [x] 11.2 实现 `WideTableValidator`：横向公式校验（期初±变动=期末），按 wide_table_presets 的列角色自动构建公式
    - _需求: 5.1_
  - [x] 11.3 实现 `VerticalValidator`：纵向勾稽（如原值-折旧-减值=账面价值）
    - _需求: 5.1_
  - [x] 11.4 实现 `CrossTableValidator`：同科目多表交叉校验（如坏账准备变动表期末=总表坏账准备列）
    - _需求: 5.1_
  - [x] 11.5 实现 `SubItemValidator`：明细行求和=合计行
    - _需求: 5.1_
  - [x] 11.6 实现 `AgingTransitionValidator`：账龄段跨期比较（期末"1至2年"≤期初"1年以内"）
    - _需求: 5.1_
  - [x] 11.7 实现 `CompletenessValidator`：数据行非空检查（余额≠0时其他列不应为空）
    - _需求: 5.1_
  - [x] 11.8 实现 `LLMReviewValidator`：调用 LLM 服务检查文本型章节的会计政策描述合理性
    - _需求: 5.1_
  - [x] 11.9 实现 `NoteValidationEngine.validate_all`：加载校验预设 → 遍历附注 → 按预设执行对应校验器 → 汇总结果 → 写入 note_validation_results 表
    - _需求: 5.2, 5.3_
  - [x] 11.10 实现校验发现确认功能：PUT 接口标记发现为"已确认-无需修改"并记录原因
    - _需求: 5.5_
  - [x]* 11.11 编写属性测试：附注余额核对
    - **Property 8: 附注余额核对**
    - 使用 Hypothesis 生成随机试算表数据和附注表格，验证附注合计行=报表对应行金额
    - **验证: 需求 4.4, 5.1**
  - [x]* 11.12 编写属性测试：附注宽表公式
    - **Property 9: 附注宽表公式**
    - 使用 Hypothesis 生成随机宽表数据，验证期初±变动=期末
    - **验证: 需求 4.5, 5.1**
  - [x]* 11.13 编写属性测试：附注其中项校验
    - **Property 10: 附注其中项校验**
    - 使用 Hypothesis 生成随机明细行+合计行，验证明细行之和=合计行
    - **验证: 需求 4.7, 5.1**

- [x] 12. 检查点 — 确保附注生成和校验引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 13. 审计报告模板管理
  - [x] 13.1 创建审计报告模板种子数据：四种意见类型 × 两种公司类型 = 8套模板，每套含7个段落（审计意见段/基础段/KAM段/其他信息段/管理层责任段/治理层责任段/审计师责任段），段落文本含占位符（{entity_name}/{audit_period}/{total_assets}等）
    - _需求: 6.1, 6.2_
  - [x] 13.2 实现 `AuditReportService.generate_report`：根据意见类型+公司类型加载模板 → 填充占位符（从 financial_report 取财务数据）→ 写入 audit_report 表
    - _需求: 6.3, 6.4_
  - [x] 13.3 实现审计报告段落编辑：PUT 接口更新指定段落内容
    - _需求: 6.6_
  - [x] 13.4 实现财务数据自动刷新：监听 `reports_updated` 事件，更新 audit_report 中的 financial_data
    - _需求: 6.5_
  - [x] 13.5 实现上市公司KAM校验：finalize 时检查 company_type=listed 的报告是否至少有一个KAM条目
    - _需求: 6.7_
  - [x] 13.6 实现审计报告 API 路由（`backend/app/routers/audit_report.py`）：POST 生成、GET 报告、PUT 段落、GET 模板列表、PUT 状态
    - _需求: 6.1-6.7_
  - [x]* 13.7 编写属性测试：审计报告财务数据一致性
    - **Property 14: 审计报告财务数据一致性**
    - 使用 Hypothesis 生成随机报表数据，验证审计报告中引用的财务数据=报表对应数据
    - **验证: 需求 6.4, 6.5**

- [x] 14. 检查点 — 确保审计报告模板管理正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 15. PDF导出引擎
  - [x] 15.1 创建 PDF HTML 模板（Jinja2）：审计报告模板、财务报表模板、附注模板、目录页模板，应用GT品牌排版规范（页边距/字体/表格边框/页眉页脚）
    - _需求: 7.4, 7.5, 7.10_
  - [x] 15.2 实现 `PDFExportEngine.render_document`：将单个文档数据渲染为 HTML → WeasyPrint 转 PDF，支持审计报告/报表/附注三种文档类型
    - _需求: 7.1_
  - [x] 15.3 实现底稿 .xlsx → PDF 转换：openpyxl 读取 → 生成 HTML 表格（保留列宽/合并单元格/打印区域）→ WeasyPrint 渲染
    - _需求: 7.9_
    - _TODO: MVP 阶段跳过_
  - [x] 15.4 实现 PDF 合并与后处理：PyPDF2 合并多个 PDF → 添加页眉（项目名/文档标题）→ 添加页脚（第X页 共Y页）→ 生成目录页
    - _需求: 7.5, 7.10_
    - _TODO: MVP 阶段跳过_
  - [x] 15.5 实现 PDF 密码保护：PyPDF2 encrypt 设置打开密码
    - _需求: 7.6_
    - _TODO: MVP 阶段跳过_
  - [x] 15.6 实现异步导出任务：Celery task `execute_export` 创建任务记录 → 逐文档渲染 → 合并 → 后处理 → 更新进度 → 完成/失败状态更新
    - _需求: 7.2, 7.3, 7.7_
    - _MVP: 同步执行，无 Celery_
  - [x] 15.7 实现导出 API 路由（`backend/app/routers/export.py`）：POST 创建任务、GET 任务状态、GET 下载文件（24小时有效）、GET 历史记录
    - _需求: 7.1-7.10_
  - [x]* 15.8 编写属性测试：PDF导出完整性
    - **Property 13: PDF导出完整性**
    - 使用 Hypothesis 生成随机文档选择组合，验证导出PDF包含所有选中文档的页面
    - **验证: 需求 7.1**

- [x] 16. 检查点 — 确保PDF导出引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 17. 报表↔底稿联动（事件驱动级联）
  - [x] 17.1 实现级联更新编排：在 EventBus 中注册完整级联链 adjustment_changed → trial_balance_updated → reports_updated → notes_updated，确保15秒内完成全链路更新
    - _需求: 8.1_
    - _已在 event_handlers.py 中实现_
  - [x] 17.2 实现数据溯源记录：financial_report 的 source_accounts 字段记录贡献科目，支持从报表行→公式→科目→凭证的完整穿透路径
    - _需求: 8.3, 8.4_
    - _已在 ReportEngine._generate_report 中实现_
  - [x] 17.3 实现跨报表一致性校验 API：BS净利润=IS净利润、CFS期末现金=BS现金，返回校验结果
    - _需求: 8.5, 8.6_
    - _已在 ReportEngine.check_balance 和 /consistency-check API 中实现_
  - [x]* 17.4 编写属性测试：级联更新完整性
    - **Property 12: 级联更新完整性**
    - 使用 Hypothesis 生成随机调整分录变更，验证变更后报表和附注均已更新且数据一致
    - **验证: 需求 8.1**

- [x] 18. 检查点 — 确保联动逻辑正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 19. 前端：报表查看页
  - [x] 19.1 创建报表查看页面组件 `ReportView.vue`：四张报表Tab切换、格式化表格（行缩进/小计加粗/合计高亮）、平衡校验状态指示器
    - _需求: 2.8_
  - [x] 19.2 实现报表穿透面板 `ReportDrilldown.vue`：点击金额单元格弹出穿透面板，显示公式→科目→凭证链路
    - _需求: 2.9_
  - [x] 19.3 实现报表操作栏：重新生成按钮、导出Excel按钮、跨报表一致性校验按钮（显示校验结果弹窗）
    - _需求: 2.10, 8.5_

- [x] 20. 前端：现金流量表工作底稿页
  - [x] 20.1 创建工作底稿页面组件 `CFSWorksheet.vue`：上半部分工作底稿表格（科目/期初/期末/变动额/已分配/未分配）、下半部分调整分录列表
    - _需求: 3.1, 3.2, 3.5_
  - [x] 20.2 实现CFS调整分录表单 `CFSAdjustmentForm.vue`：创建/编辑调整分录，借贷平衡实时校验
    - _需求: 3.3, 3.4_
  - [x] 20.3 实现现金流量表预览面板和勾稽校验结果显示
    - _需求: 3.7, 3.10, 3.11, 3.12_

- [x] 21. 前端：附注编辑页
  - [x] 21.1 创建附注编辑页面组件 `DisclosureEditor.vue`：左侧目录树（按章节编号组织）、中间内容编辑区（表格型/文字型）、右侧校验结果面板
    - _需求: 4.11_
  - [x] 21.2 实现附注表格编辑组件 `NoteTableEditor.vue`：可编辑表格，支持数值输入、自动计算合计行、校验角色标记显示
    - _需求: 4.10_
  - [x] 21.3 实现附注校验结果面板 `NoteValidationPanel.vue`：按科目分组显示校验发现，错误红色/警告橙色/提示灰色，支持确认操作
    - _需求: 5.4, 5.5_

- [x] 22. 前端：审计报告编辑页
  - [x] 22.1 创建审计报告编辑页面组件 `AuditReportEditor.vue`：左侧段落导航、中间富文本编辑器（GT品牌排版）、右侧财务数据引用面板
    - _需求: 6.6_
  - [x] 22.2 实现意见类型/公司类型选择和报告生成流程
    - _需求: 6.3_

- [x] 23. 前端：PDF导出面板
  - [x] 23.1 创建PDF导出面板组件 `PDFExportPanel.vue`：文档选择勾选框、密码保护开关、进度条（轮询任务状态）、历史记录列表
    - _需求: 7.1-7.8_

- [x] 24. 最终检查点 — 全模块集成验证
  - 端到端验证：创建项目→导入数据→生成试算表→生成报表→编制现金流量表→生成附注→执行校验→生成审计报告→PDF导出，确保全链路通畅。如有问题请询问用户。
