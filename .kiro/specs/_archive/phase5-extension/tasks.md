# Phase 8 - 扩展能力与远期规划 任务清单

## 概述

本阶段实现系统的扩展性能力、多准则适配、监管对接、用户自定义模板等高级功能，并为未来的AI能力扩展预留接口。

## 任务清单

### 1. 数据库迁移：扩展表结构

- [x] 1.1 创建 `accounting_standards` 表（UUID PK、standard_code varchar unique、standard_name varchar not null、standard_description text、effective_date date、is_active boolean default true、created_at、updated_at）
    - _需求: 1.1_
- [x] 1.2 扩展 `users` 表，添加 `language` 字段（enum: zh-CN/en-US，默认zh-CN）
    - _需求: 2.2_
- [x] 1.3 扩展 `projects` 表，修改 `audit_type` 枚举值（增加special_audit/ipo_audit/internal_control_audit/capital_verification/tax_audit）
    - _需求: 3.1_
- [x] 1.4 创建 `signature_records` 表（UUID PK、object_type enum working_paper/adjustment/audit_report、object_id UUID、signer_id UUID FK、signature_level enum level1/level2/level3、signature_data jsonb、timestamp timestamp、ip_address varchar、is_deleted boolean default false、created_at）及索引 (object_type, object_id)
    - _需求: 5.2_
- [x] 1.5 创建 `wp_template_custom` 表（UUID PK、user_id UUID FK、template_name varchar、category enum industry/client/personal、template_file_path varchar、is_published boolean、version varchar、is_deleted boolean default false、created_at、updated_at）及索引 (user_id, category)
    - _需求: 4.6_
- [x] 1.6 创建 `regulatory_filing` 表（UUID PK、project_id UUID FK、filing_type enum cicpa_report/archival_standard、filing_status enum submitted/pending/approved/rejected、submission_data jsonb、response_data jsonb、submitted_at timestamp、responded_at timestamp、error_message text、is_deleted boolean default false、created_at、updated_at）及索引 (project_id, filing_type)
    - _需求: 6.6_
- [x] 1.7 创建 `gt_wp_coding` 表（UUID PK、code_prefix varchar、code_range varchar、cycle_name varchar、wp_type enum preliminary/risk_assessment/control_test/substantive/completion/specific/general/permanent、description text、sort_order integer、is_active boolean default true、is_deleted boolean default false、created_at、updated_at）及索引 (code_prefix, wp_type)
    - _需求: 7.7_
- [x] 1.8 扩展 `projects` 表，添加 `accounting_standard` 字段（UUID FK，关联accounting_standards表）
    - _需求: 1.2_

### 2. ORM/Pydantic Schemas：扩展模型

- [x] 2.1 创建 `backend/app/models/extension_models.py`：AccountingStandard、SignatureRecord、WpTemplateCustom、RegulatoryFiling、AIPlugin 模型 + 会计准则种子数据
    - _需求: 1.1, 5.2, 4.6, 6.6, 7.7_
- [x] 2.2 扩展 `backend/app/models/core.py`：User模型添加language字段，Project模型添加accounting_standard_id字段
    - _需求: 1.2, 2.2, 3.1_
- [x] 2.3 创建 `backend/app/schemas/extension.py`：扩展模型的Pydantic schemas（AccountingStandardCreate/Update/Response、SignatureRecordCreate/Response、CustomTemplateCreate/Update/Response、RegulatoryFilingCreate/Update/Response、GTWPCodingCreate/Update/Response）
    - _需求: 1.1, 5.2, 4.6, 6.6, 7.7_
- [x] 2.4 扩展 `backend/app/schemas/core.py`：UserCreate/Response添加language字段，ProjectCreate/Update添加accounting_standard字段，扩展audit_type枚举
    - _需求: 1.2, 2.2, 3.1_

### 3. 多准则适配服务

- [x] 3.1 实现 `backend/app/services/accounting_standard_service.py`：get_standards（获取所有准则列表）、get_standard（获取准则详情）、get_standard_chart（获取准则对应的科目表）、get_standard_report_formats（获取准则对应的报表格式）
    - _需求: 1.1, 1.3, 1.4_
- [x] 3.2 实现准则对应的标准科目表种子数据：企业会计准则、小企业准则、政府会计准则、金融企业准则、国际准则IFRS的一级科目定义
    - _需求: 1.3_
- [x] 3.3 实现准则对应的报表格式配置：每种准则的资产负债表/利润表/现金流量表/权益变动表的行次和取数公式
    - _需求: 1.4_
- [x] 3.4 实现准则对应的附注模版配置：每种准则的附注模版和校验规则
    - _需求: 1.5_
- [x] 3.5 实现项目准则切换逻辑：切换准则时警告用户可能影响报表格式和披露要求
    - _需求: 1.6_
- [x] 3.6 实现多准则 API 路由 `backend/app/routers/accounting_standards.py`：GET /api/accounting-standards（准则列表）、GET /api/accounting-standards/{id}（准则详情）、PUT /api/projects/{id}/accounting-standard（切换项目准则）
    - _需求: 1.1, 1.6_

### 4. 多语言支持

- [x] 4.1 实现i18n框架：创建前端语言文件（zh-CN.json、en-US.json），定义所有界面文本的翻译
    - _需求: 2.1_
- [x] 4.2 实现后端多语言支持：创建 `backend/app/i18n/` 目录，定义审计术语的多语言映射（AJE/RJE/TB/PBC等）
    - _需求: 2.5_
- [x] 4.3 实现用户语言偏好设置：扩展用户管理页面，添加语言选择下拉框
    - _需求: 2.2, 2.3_
- [x] 4.4 实现前端语言切换：根据用户语言偏好加载对应语言文件，支持运行时切换
    - _需求: 2.3_
- [x] 4.5 实现双语报表生成：报表导出时提供语言选择（中文/英文），生成对应语言的报表
    - _需求: 2.4_
- [x] 4.6 实现双语审计报告生成：审计报告模版支持中英双语版本
    - _需求: 2.4_
- [x] 4.7 实现多语言 API 路由 `backend/app/routers/i18n.py`：GET /api/i18n/languages（支持的语言列表）、GET /api/i18n/translations/{lang}（获取语言文件）、PUT /api/users/{id}/language（设置用户语言）
    - _需求: 2.1, 2.2_

### 5. 审计类型扩展

- [x] 5.1 实现审计类型特定的底稿模板集：IPO审计专用底稿、专项审计底稿、内控审计底稿、验资底稿、税审底稿
    - _需求: 3.2_
- [x] 5.2 实现审计类型特定的报表模版：验资报告模版、内控审计报告模版等
    - _需求: 3.3_
- [x] 5.3 实现审计类型特定的审计程序框架：不同审计类型的风险评估和程序清单
    - _需求: 3.4_
- [x] 5.4 实现项目创建时的审计类型推荐：根据审计类型自动推荐对应的模板集和程序
    - _需求: 3.5_
- [x] 5.5 扩展项目初始化向导：添加审计类型选择步骤，根据选择推荐模板集
    - _需求: 3.5_

### 6. 用户自定义底稿模板

- [x] 6.1 实现 `backend/app/services/custom_template_service.py`：create_template（创建自定义模板）、update_template（更新模板）、publish_template（发布模板）、get_templates（获取模板列表）、get_template（获取模板详情）、validate_template（验证模板公式语法和区域定义）
    - _需求: 4.1, 4.6_
- [x] 6.2 实现自定义模板上传功能：支持上传.xlsx/.docx文件，解析取数公式和区域标记
    - _需求: 4.1_
- [x] 6.3 实现模板市场/共享机制：用户可以查看其他用户发布的模板，一键复制使用
    - _需求: 4.2_
- [x] 6.4 实现取数公式DSL扩展：允许用户注册自定义函数，扩展公式能力
    - _需求: 4.3_
- [x] 6.5 实现模板版本管理：用户自定义模板支持版本号和版本历史
    - _需求: 4.4_
- [x] 6.6 实现模板分类管理：行业专用/客户专用/个人收藏分类
    - _需求: 4.5_
- [x] 6.7 实现自定义模板 API 路由 `backend/app/routers/custom_templates.py`：POST /api/custom-templates（创建模板）、PUT /api/custom-templates/{id}（更新模板）、POST /api/custom-templates/{id}/publish（发布模板）、GET /api/custom-templates（模板列表）、GET /api/custom-templates/{id}（模板详情）、POST /api/custom-templates/{id}/validate（验证模板）
    - _需求: 4.1, 4.2, 4.6_
- [x] 6.8 实现前端自定义模板管理页面：模板列表、模板上传、模板编辑、模板发布、模板市场
    - _需求: 4.1, 4.2_

### 7. 电子签名方案

- [x] 7.1 实现 `backend/app/services/sign_service.py`：sign_document（签核文档，支持三级签名）、verify_signature（验证签名）、get_signature_records（获取签名记录）、revoke_signature（撤销签名，需审批流程）
    - _需求: 5.1, 5.4, 5.6_
- [x] 7.2 实现Level 1签名（用户名+密码确认）：记录操作人、时间、IP地址
    - _需求: 5.1_
- [x] 7.3 实现Level 2签名（手写签名图片+时间戳）：前端手写签名板组件，保存签名图片
    - _需求: 5.1_
- [x] 7.4 实现Level 3签名（CA数字证书）：预留CA证书接口，支持证书验证和PDF嵌入
    - _需求: 5.1, 5.4, 5.5_
- [x] 7.5 实现签名记录查询：按对象类型和ID查询签名历史
    - _需求: 5.2_
- [x] 7.6 实现签名撤销和重签流程：归档后修改需要审批，保留修改前后对比
    - _需求: 5.6_
- [x] 7.7 实现电子签名 API 路由 `backend/app/routers/signatures.py`：POST /api/signatures/sign（签核文档）、GET /api/signatures/{object_type}/{object_id}（获取签名记录）、POST /api/signatures/{id}/verify（验证签名）、POST /api/signatures/{id}/revoke（撤销签名）
    - _需求: 5.1, 5.2, 5.6_
- [x] 7.8 实现前端签名组件：Level 1确认弹窗、Level 2手写签名板、Level 3证书签名界面
    - _需求: 5.1_

### 8. 监管对接

- [x] 8.1 实现 `backend/app/services/regulatory_service.py`：submit_cicpa_report（提交中注协审计报告备案）、submit_archival_standard（提交电子底稿归档标准）、check_filing_status（查询备案状态）、handle_filing_response（处理备案响应）、retry_filing（重试失败的备案）
    - _需求: 6.1, 6.2, 6.4, 6.6_
- [x] 8.2 实现中注协审计报告备案接口：按照中注协要求的数据格式（XML/JSON）转换和提交
    - _需求: 6.1, 6.3_
- [x] 8.3 实现电子底稿归档标准接口：按照电子底稿归档标准格式转换和提交
    - _需求: 6.2, 6.3_
- [x] 8.4 实现备案状态跟踪：submitted/pending/approved/rejected状态流转
    - _需求: 6.4_
- [x] 8.5 实现备案日志记录：记录所有备案操作的详细日志
    - _需求: 6.5_
- [x] 8.6 实现备案失败处理：提供详细错误信息和重试机制
    - _需求: 6.6_
- [x] 8.7 实现监管对接 API 路由 `backend/app/routers/regulatory.py`：POST /api/regulatory/cicpa-report（提交审计报告备案）、POST /api/regulatory/archival-standard（提交归档标准）、GET /api/regulatory/filings/{id}/status（查询备案状态）、POST /api/regulatory/filings/{id}/retry（重试备案）
    - _需求: 6.1, 6.2, 6.4, 6.6_
- [x] 8.8 实现前端监管对接页面：备案列表、备案状态查看、错误信息展示、重试操作
    - _需求: 6.4, 6.6_

### 9. 致同底稿编码体系

- [x] 9.1 实现致同底稿编码体系种子数据：B类（初步业务活动+风险评估）、C类（控制测试）、D-N类（实质性程序）、Q类（关联方）、A类（完成阶段）、S类（特定项目）、T类（通用）、Z类（永久性档案）
    - _需求: 7.1_
- [x] 9.2 实现三测联动结构：每个审计循环的B类（穿行测试）→C类（控制测试）→D-N类（实质性程序）关联关系
    - _需求: 7.2_
- [x] 9.3 实现致同标准底稿模板库：内置600+个底稿模板，按编码体系组织
    - _需求: 7.3_
- [x] 9.4 实现底稿编码自定义：允许用户为特定项目或事务所自定义编码体系
    - _需求: 7.4_
- [x] 9.5 实现项目创建时的底稿索引自动生成：根据致同编码体系自动生成底稿索引
    - _需求: 7.5_
- [x] 9.6 实现致同底稿编码 API 路由 `backend/app/routers/gt_coding.py`：GET /api/gt-coding（编码体系列表）、GET /api/gt-coding/{id}（编码详情）、POST /api/projects/{id}/generate-index（生成底稿索引）
    - _需求: 7.1, 7.5_

### 10. 致同品牌视觉规范详细实现

- [x] 10.1 实现GT品牌色系CSS变量：定义所有品牌色的CSS变量
    - _需求: 8.1_
- [x] 10.2 实现CSS类命名规范：所有自定义样式使用`gt-{component}-{modifier}`命名
    - _需求: 8.2_
- [x] 10.3 实现间距系统：基于4px网格，主节奏单位8px
    - _需求: 8.3_
- [x] 10.4 实现圆角规范：小4px、中8px、大12px
    - _需求: 8.4_
- [x] 10.5 实现阴影规范：GT紫色调阴影（rgba(75, 45, 119, 0.075/0.15/0.175)）
    - _需求: 8.5_
- [x] 10.6 实现字体规范：中文和英文的字体降级链
    - _需求: 8.6_
- [x] 10.7 实现底稿视觉标记：AI生成内容、复核意见、审定数等的视觉标记
    - _需求: 8.7_
- [x] 10.8 实现打印样式：A4、黑白配色、避免分页断裂
    - _需求: 8.8_
- [x] 10.9 实现可访问性：WCAG 2.1 AA标准（对比度、焦点样式、ARIA标签）
    - _需求: 8.9_
- [x] 10.10 实现暗色模式CSS变量映射：预留暗色模式的CSS变量
    - _需求: 8.10_

### 11. 附注模版体系完善

- [x] 11.1 实现国企版附注模版完整配置：科目对照模板、校验公式预设、宽表公式预设、正文模版
    - _需求: 9.1_
- [x] 11.2 实现上市版附注模版完整配置：科目对照模板、校验公式预设、宽表公式预设、正文模版
    - _需求: 9.1_
- [x] 11.3 实现附注校验公式引擎：支持8种公式类型（余额核对、宽表横向、纵向勾稽、交叉校验、其中项校验、账龄衔接、完整性检查、LLM审核）
    - _需求: 9.2_
- [x] 11.4 实现双层架构：本地规则引擎优先+LLM兜底
    - _需求: 9.3_
- [x] 11.5 实现附注模版自定义：允许用户为特定行业或客户自定义附注模版
    - _需求: 9.4_
- [x] 11.6 实现附注模版版本管理：模版版本号和版本历史
    - _需求: 9.5_

### 12. T型账户法（现金流量表编制）

- [x] 12.1 实现 `backend/app/services/t_account_service.py`：create_t_account（创建T型账户）、add_entry（添加分录）、calculate_net_change（计算净变动）、reconcile_with_balance_sheet（与资产负债表勾稽）、integrate_to_cfs（集成到现金流量表）
    - _需求: 10.1, 10.4, 10.5_
- [x] 12.2 实现T型账户数据表：`t_accounts`（T型账户主表）、`t_account_entries`（T型账户分录）
    - _需求: 10.1_
- [x] 12.3 实现T型账户创建功能：支持为特定科目创建T型账户（固定资产、累计折旧、债务重组等）
    - _需求: 10.2_
- [x] 12.4 实现分录入账功能：支持输入借方和贷方分录
    - _需求: 10.3_
- [x] 12.5 实现净变动计算和勾稽：自动计算净变动并与资产负债表变动勾稽
    - _需求: 10.4_
- [x] 12.6 实现T型账户结果集成：将分析结果集成到现金流量表工作底稿
    - _需求: 10.5_
- [x] 12.7 实现T型账户模版：提供常见复杂交易的T型账户模版
    - _需求: 10.6_
- [x] 12.8 实现T型账户 API 路由 `backend/app/routers/t_accounts.py`：POST /api/projects/{id}/t-accounts（创建T型账户）、POST /api/projects/{id}/t-accounts/{id}/entries（添加分录）、GET /api/projects/{id}/t-accounts/{id}（获取T型账户）、POST /api/projects/{id}/t-accounts/{id}/calculate（计算净变动）、POST /api/projects/{id}/t-accounts/{id}/integrate（集成到现金流量表）
    - _需求: 10.1, 10.3, 10.4, 10.5_
- [x] 12.9 实现前端T型账户组件：T型账户可视化、分录入账界面、计算结果展示
    - _需求: 10.2, 10.3, 10.4_

### 13. AI能力预留接口

- [x] 13.1 实现 `backend/app/services/ai_plugin_service.py`：插件注册、插件加载、插件卸载、插件配置
    - _需求: 11.2_
- [x] 13.2 实现插件架构：每个AI能力作为独立插件，统一接口规范
    - _需求: 11.1, 11.2_
- [x] 13.3 实现外部API集成接口：支持对接外部API（税务局发票查验、天眼查/企查查、银行对账等），包含限流和错误处理
    - _需求: 11.1, 11.3_
- [x] 13.4 实现模型切换接口：通过配置切换不同LLM模型，无需代码修改
    - _需求: 11.4_
- [x] 13.5 实现AI能力开关配置：项目级别的AI能力启用/禁用配置
    - _需求: 11.5_
- [x] 13.6 预留电子发票真伪验证插件接口：对接税务局发票查验接口
    - _需求: 11.1_
- [x] 13.7 预留工商信息实时查询插件接口：对接天眼查/企查查API或定期导入缓存
    - _需求: 11.1_
- [x] 13.8 预留银行对账单自动对账插件接口：银行流水与账面逐笔自动对账
    - _需求: 11.1_
- [x] 13.9 预留印章/签名真伪检测插件接口：对比历史印章样本
    - _需求: 11.1_
- [x] 13.10 预留语音审计笔记插件接口：语音转文字
    - _需求: 11.1_
- [x] 13.11 预留审计底稿智能复核插件接口：AI辅助检查底稿完整性
    - _需求: 11.1_
- [x] 13.12 预留持续审计/实时监控插件接口：对接被审计单位ERP
    - _需求: 11.1_
- [x] 13.13 预留多人团队AI群聊协作插件接口：项目组成员在同一对话空间中与AI协同讨论
    - _需求: 11.1_
- [x] 13.14 实现AI插件管理 API 路由 `backend/app/routers/ai_plugins.py`：GET /api/ai-plugins（插件列表）、POST /api/ai-plugins/{id}/enable（启用插件）、POST /api/ai-plugins/{id}/disable（禁用插件）、PUT /api/ai-plugins/{id}/config（配置插件）
    - _需求: 11.2, 11.5_
- [x] 13.15 实现前端AI插件管理页面：插件列表、插件开关、插件配置
    - _需求: 11.2, 11.5_

### 14. Metabase数据可视化集成

**冲突说明：**

本任务组与Phase 4 AI功能存在潜在功能重叠，与前端三栏布局存在iframe嵌入冲突。实施时需遵循design.md"与以往需求的冲突及解决方案"章节中的解决方案，明确功能边界、统一嵌入规范、提供用户引导。

- [x] 14.1 部署Metabase服务：Docker部署、连接审计系统PostgreSQL数据库、配置数据库连接
    - _需求: 13.1_
- [x] 14.2 创建预置仪表板模板：项目进度看板、账套总览、科目穿透、辅助账分析、凭证趋势
    - _需求: 13.2_
- [x] 14.3 创建SQL查询模板：总账查询、明细账查询、凭证查询、辅助账查询
    - _需求: 13.3_
- [x] 14.4 实现Metabase嵌入前端：使用Embedding API或iframe嵌入前端三栏布局（左侧栏"仪表盘"功能、右侧栏"关键指标"Tab）
    - _需求: 13.4_
- [x] 14.5 实现仪表板下钻功能：从可视化图表穿透到明细数据（总账→明细账→凭证）
    - _需求: 13.5_
- [x] 14.6 实现仪表板查询结果缓存：Redis缓存（TTL=5分钟）
    - _需求: 13.6_
- [x] 14.7 实现前端Metabase组件：仪表板嵌入组件、下钻导航组件
    - _需求: 13.4, 13.5_

### 15. Paperless-ngx附件文档管理集成

**冲突说明：**

本任务组与Phase 3协作功能的附件管理存在重叠，与Phase 4 PaddleOCR存在OCR引擎选择冲突，与现有文件存储机制存在冲突。实施时需遵循design.md"与以往需求的冲突及解决方案"章节中的解决方案，统一附件管理架构、明确OCR引擎分工、统一文件存储。

- [x] 15.1 部署Paperless-ngx服务：Docker部署、配置OCR引擎（Tesseract）、配置文件存储
    - _需求: 14.1_
- [x] 15.2 创建 `attachments` 表（UUID PK、project_id UUID FK、file_name varchar、file_path varchar、file_type varchar、file_size bigint、paperless_document_id integer、ocr_status enum pending/processing/completed/failed、ocr_text text、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, ocr_status)
    - _需求: 14.8_
- [x] 15.3 实现附件管理服务 `backend/app/services/attachment_service.py`：upload_to_paperless（上传到Paperless-ngx）、get_from_paperless（从Paperless-ngx获取）、search_attachments（全文搜索）、associate_with_working_paper（关联到底稿）、extract_ocr_result（提取OCR结果）
    - _需求: 14.2, 14.5, 14.8_
- [x] 15.4 实现OCR识别集成：调用Paperless-ngx的OCR接口、异步处理OCR任务、OCR状态跟踪
    - _需求: 14.3_
- [x] 15.5 实现自动文档分类：按客户、期间、文档类型自动分类（基于文件名、内容分析）
    - _需求: 14.4_
- [x] 15.6 实现函证回函OCR识别：提取回函金额、回函日期、回函单位名称
    - _需求: 14.6_
- [x] 15.7 实现附件管理 API 路由 `backend/app/routers/attachments.py`：POST /api/projects/{id}/attachments（上传附件）、GET /api/projects/{id}/attachments（附件列表）、GET /api/attachments/{id}（附件详情）、POST /api/attachments/{id}/associate（关联到底稿）、GET /api/attachments/search（全文搜索）
    - _需求: 14.2, 14.5_
- [x] 15.8 安装vue-office组件：@vue-office/docx、@vue-office/excel、@vue-office/pdf
    - _需求: 14.7_
- [x] 15.9 实现前端附件预览组件：使用vue-office组件快速预览附件（合同、发票、回函等）
    - _需求: 14.7_
- [x] 15.10 实现前端附件管理页面：附件列表、附件上传、附件预览、附件关联底稿
    - _需求: 14.5, 14.7_

### 16. 大数据处理优化（账套数据联动查询）

**冲突说明：**

本任务组与现有数据库结构存在冲突（需要分区表迁移），与现有查询API存在功能重叠，与前端现有组件存在一致性冲突。实施时需遵循design.md"与以往需求的冲突及解决方案"章节中的解决方案，平滑数据迁移、API兼容性设计、前端组件渐进式升级。

- [x] 16.1 创建journal_entries表分区：按年度分区（tb_ledger + tb_aux_ledger，2023-2027共5个年度分区）
    - _需求: 15.6_
- [x] 16.2 创建穿透查询索引：idx_journal_entries_project_year_company_account、idx_journal_entries_project_year_company_date、idx_journal_entries_voucher、idx_auxiliary_balance_project_year_company_account、idx_auxiliary_balance_dimension
    - _需求: 15.7_
- [x] 16.3 实现穿透查询服务 `backend/app/services/ledger_penetration_service.py`：get_penetrate_data（使用CTE一次性查询多层级数据）、get_penetrate_data_cached（Redis缓存版本）
    - _需求: 15.1, 15.3, 15.4_
- [x] 16.4 实现穿透查询 API 路由 `backend/app/routers/ledger_penetration.py`：GET /api/projects/{id}/ledger/penetrate（穿透查询）
    - _需求: 15.1_
- [x] 16.5 实现Redis缓存策略：穿透查询结果缓存（TTL=5分钟）、缓存键设计、缓存失效策略
    - _需求: 15.4_
- [x] 16.6 实现前端虚拟滚动组件：处理大量数据的渲染性能（只渲染可见行）
    - _需求: 15.5_
- [x] 16.7 实现前端穿透查询页面：穿透查询结果展示、下钻导航、虚拟滚动表格
    - _需求: 15.1, 15.5, 15.8_

### 17. 检查点 — 确保所有后端服务正确

- 运行单元测试确认：多准则适配、多语言支持、审计类型扩展、自定义模板、电子签名、监管对接、致同编码体系、T型账户法、AI插件接口、Metabase集成、Paperless-ngx集成、大数据处理优化。

### 18. 后端测试

- [x] 18.1 编写 `backend/tests/test_accounting_standard_service.py`：测试多准则适配（准则列表、准则详情、准则对应科目表、准则对应报表格式、准则切换警告）
    - _需求: 1.1-1.6_
- [x] 18.2 编写 `backend/tests/test_i18n_service.py`：测试多语言支持（语言文件加载、用户语言偏好、双语报表生成）
    - _需求: 2.1-2.6_
- [x] 18.3 编写 `backend/tests/test_custom_template_service.py`：测试自定义模板（模板创建、模板验证、模板发布、模板市场）
    - _需求: 4.1-4.6_
- [x] 18.4 编写 `backend/tests/test_sign_service.py`：测试电子签名（三级签名、签名验证、签名撤销、签名记录）
    - _需求: 5.1-5.6_
- [x] 18.5 编写 `backend/tests/test_regulatory_service.py`：测试监管对接（备案提交、状态跟踪、错误处理、重试机制）
    - _需求: 6.1-6.6_
- [x] 18.6 编写 `backend/tests/test_gt_coding_service.py`：测试致同编码体系（编码数据、三测联动、底稿索引生成）
    - _需求: 7.1-7.5_
- [x] 18.7 编写 `backend/tests/test_t_account_service.py`：测试T型账户法（T型账户创建、分录入账、净变动计算、勾稽、集成）
    - _需求: 10.1-10.6_
- [x] 18.8 编写 `backend/tests/test_ai_plugin_service.py`：测试AI插件接口（插件注册、插件加载、外部API集成、模型切换、能力开关）
    - _需求: 11.1-11.5_
- [x] 18.9 编写 `backend/tests/test_attachment_service.py`：测试附件管理（上传到Paperless-ngx、OCR识别、全文搜索、关联底稿）
    - _需求: 14.1-14.8_
- [x] 18.10 编写 `backend/tests/test_ledger_penetration_service.py`：测试穿透查询（CTE查询、Redis缓存、虚拟滚动）
    - _需求: 15.1-15.8_

### 19. 前端：多准则和多语言支持

- [x] 19.1 创建 `frontend/src/i18n/` 目录：zh-CN.json、en-US.json语言文件
    - _需求: 2.1_
- [x] 19.2 创建 `frontend/src/components/extension/LanguageSwitcher.vue`：语言切换组件
    - _需求: 2.3_
- [x] 19.3 创建 `frontend/src/components/extension/StandardSelector.vue`：会计准则选择组件
    - _需求: 1.3, 1.6_
- [x] 19.4 创建 `frontend/src/components/extension/AuditTypeSelector.vue`：审计类型选择组件
    - _需求: 3.5_
- [x] 19.5 扩展用户设置页面：添加语言选择、默认准则设置
    - _需求: 2.2, 1.2_

### 20. 前端：自定义模板管理

- [x] 20.1 创建 `frontend/src/views/extension/CustomTemplateList.vue`：自定义模板列表页面
    - _需求: 4.2_
- [x] 20.2 创建 `frontend/src/views/extension/CustomTemplateEditor.vue`：自定义模板编辑页面
    - _需求: 4.1_
- [x] 20.3 创建 `frontend/src/views/extension/TemplateMarket.vue`：模板市场页面
    - _需求: 4.2_
- [x] 20.4 创建 `frontend/src/components/extension/TemplateUpload.vue`：模板上传组件
    - _需求: 4.1_
- [x] 20.5 创建 `frontend/src/components/extension/TemplateValidator.vue`：模板验证组件（公式语法检查、区域定义检查）
    - _需求: 4.6_

### 21. 前端：电子签名

- [x] 21.1 创建 `frontend/src/components/extension/SignatureLevel1.vue`：Level 1签名组件（用户名+密码确认）
    - _需求: 5.1_
- [x] 21.2 创建 `frontend/src/components/extension/SignatureLevel2.vue`：Level 2签名组件（手写签名板）
    - _需求: 5.1_
- [x] 21.3 创建 `frontend/src/components/extension/SignatureLevel3.vue`：Level 3签名组件（CA证书签名）
    - _需求: 5.1_
- [x] 21.4 创建 `frontend/src/components/extension/SignatureHistory.vue`：签名历史查看组件
    - _需求: 5.2_
- [x] 21.5 创建 `frontend/src/views/extension/SignatureManagement.vue`：签名管理页面
    - _需求: 5.2, 5.6_

### 22. 前端：监管对接

- [x] 22.1 创建 `frontend/src/views/extension/RegulatoryFiling.vue`：监管备案页面
    - _需求: 6.4, 6.6_
- [x] 22.2 创建 `frontend/src/components/extension/FilingStatus.vue`：备案状态组件
    - _需求: 6.4_
- [x] 22.3 创建 `frontend/src/components/extension/FilingError.vue`：备案错误信息组件
    - _需求: 6.6_
- [x] 22.4 创建 `frontend/src/components/extension/CICPAReportForm.vue`：中注协审计报告备案表单
    - _需求: 6.1_
- [x] 22.5 创建 `frontend/src/components/extension/ArchivalStandardForm.vue`：电子底稿归档标准表单
    - _需求: 6.2_

### 23. 前端：致同底稿编码体系

- [x] 23.1 创建 `frontend/src/views/extension/GTCodingSystem.vue`：致同编码体系查看页面
    - _需求: 7.1_
- [x] 23.2 创建 `frontend/src/components/extension/GTWPCodingTree.vue`：致同底稿编码树形组件
    - _需求: 7.1, 7.2_
- [x] 23.3 创建 `frontend/src/components/extension/WPIndexGenerator.vue`：底稿索引自动生成组件
    - _需求: 7.5_
- [x] 23.4 创建 `frontend/src/components/extension/CustomCodingEditor.vue`：自定义编码编辑器
    - _需求: 7.4_

### 24. 前端：T型账户法

- [x] 24.1 创建 `frontend/src/components/extension/TAccountEditor.vue`：T型账户编辑器（可视化T型账户）
    - _需求: 10.2, 10.3_
- [x] 24.2 创建 `frontend/src/components/extension/TAccountEntryForm.vue`：分录入账表单
    - _需求: 10.3_
- [x] 24.3 创建 `frontend/src/components/extension/TAccountResult.vue`：T型账户计算结果展示
    - _需求: 10.4_
- [x] 24.4 创建 `frontend/src/views/extension/TAccountManagement.vue`：T型账户管理页面
    - _需求: 10.1, 10.6_

### 25. 前端：AI插件管理

- [x] 25.1 创建 `frontend/src/views/extension/AIPluginManagement.vue`：AI插件管理页面
    - _需求: 11.2, 11.5_
- [x] 25.2 创建 `frontend/src/components/extension/PluginList.vue`：插件列表组件
    - _需求: 11.2_
- [x] 25.3 创建 `frontend/src/components/extension/PluginConfig.vue`：插件配置组件
    - _需求: 11.5_
- [x] 25.4 创建 `frontend/src/components/extension/ExternalAPIConfig.vue`：外部API配置组件
    - _需求: 11.3_
- [x] 25.5 创建 `frontend/src/components/extension/ModelSwitcher.vue`：模型切换组件
    - _需求: 11.4_

### 26. 前端：外部系统集成

- [x] 26.1 创建 `frontend/src/components/extension/MetabaseDashboard.vue`：Metabase仪表板嵌入组件
    - _需求: 13.4_
- [x] 26.2 创建 `frontend/src/components/extension/DrillDownNavigator.vue`：仪表板下钻导航组件
    - _需求: 13.5_
- [x] 26.3 创建 `frontend/src/views/extension/AttachmentManagement.vue`：附件管理页面
    - _需求: 14.5, 14.7_
- [x] 26.4 创建 `frontend/src/components/extension/AttachmentPreview.vue`：附件预览组件（使用vue-office）
    - _需求: 14.7_
- [x] 26.5 创建 `frontend/src/components/extension/VirtualScrollTable.vue`：虚拟滚动表格组件
    - _需求: 15.5_
- [x] 26.6 创建 `frontend/src/views/extension/LedgerPenetration.vue`：穿透查询页面
    - _需求: 15.1, 15.5, 15.8_

### 27. 前端：品牌视觉规范

- [x] 27.1 创建 `frontend/src/styles/gt-variables.scss`：GT品牌色系CSS变量
    - _需求: 8.1_
- [x] 27.2 创建 `frontend/src/styles/gt-mixins.scss`：GT样式混入（间距、圆角、阴影）
    - _需求: 8.3, 8.4, 8.5_
- [x] 27.3 创建 `frontend/src/styles/gt-typography.scss`：GT字体规范
    - _需求: 8.6_
- [x] 27.4 创建 `frontend/src/styles/gt-markers.scss`：底稿视觉标记样式
    - _需求: 8.7_
- [x] 27.5 创建 `frontend/src/styles/gt-print.scss`：打印样式
    - _需求: 8.8_
- [x] 27.6 创建 `frontend/src/styles/gt-dark-mode.scss`：暗色模式CSS变量映射
    - _需求: 8.10_
- [x] 27.7 更新所有现有组件以遵循GT命名规范和视觉规范
    - _需求: 8.2, 8.9_

### 28. 集成测试

- [x] 28.1 编写端到端测试：多准则项目创建、准则切换、准则对应报表生成
    - _需求: 1.1-1.6_
- [x] 28.2 编写端到端测试：多语言界面切换、双语报表导出
    - _需求: 2.1-2.6_
- [x] 28.3 编写端到端测试：自定义模板创建、发布、使用
    - _需求: 4.1-4.6_
- [x] 28.4 编写端到端测试：电子签名流程（三级签名）
    - _需求: 5.1-5.6_
- [x] 28.5 编写端到端测试：监管备案流程
    - _需求: 6.1-6.6_
- [x] 28.6 编写端到端测试：致同编码体系底稿索引生成
    - _需求: 7.1-7.5_
- [x] 28.7 编写端到端测试：T型账户法完整流程
    - _需求: 10.1-10.6_
- [x] 28.8 编写端到端测试：AI插件注册、启用、配置
    - _需求: 11.1-11.5_
- [x] 28.9 编写端到端测试：Metabase仪表板嵌入和下钻
    - _需求: 13.1-13.6_
- [x] 28.10 编写端到端测试：附件上传、OCR识别、关联底稿
    - _需求: 14.1-14.8_
- [x] 28.11 编写端到端测试：穿透查询完整流程
    - _需求: 15.1-15.8_

### 29. 文档

- [x] 29.1 编写《多准则适配指南》：如何使用多准则功能、准则切换注意事项
- [x] 29.2 编写《多语言使用指南》：如何切换语言、如何生成双语报表
- [x] 29.3 编写《自定义模板开发指南》：如何创建自定义模板、公式DSL扩展
- [x] 29.4 编写《电子签名使用指南》：三级签名的使用场景和操作流程
- [x] 29.5 编写《监管对接配置指南》：如何配置中注协备案接口、如何处理备案错误
- [x] 29.6 编写《致同底稿编码体系说明》：编码体系结构、三测联动、自定义编码
- [x] 29.7 编写《T型账户法使用指南》：T型账户适用场景、操作步骤、注意事项
- [x] 29.8 编写《AI插件开发指南》：如何开发AI插件、插件接口规范
- [x] 29.9 编写《Metabase集成指南》：如何部署Metabase、如何创建仪表板、如何嵌入前端
- [x] 29.10 编写《Paperless-ngx集成指南》：如何部署Paperless-ngx、如何配置OCR、如何集成附件管理
- [x] 29.11 编写《穿透查询优化指南》：如何使用穿透查询API、如何优化数据库索引、如何实现虚拟滚动

### 30. 前端三栏布局（对应需求16）

**状态：已完成初版**

- [x] 30.1 实现 `ThreeColumnLayout.vue` 核心三栏布局组件：顶部导航栏（Logo+面包屑+通知+用户信息）+ 左侧1级功能导航（9项菜单，可折叠56px/展开220px）+ 中间栏（340px默认）+ 右侧栏（自适应）+ 两条拖拽分隔线 + localStorage偏好保存 + 响应式适配（<1200px自动折叠）+ ESC退出全屏
    - _需求: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_
- [x] 30.2 实现 `MiddleProjectList.vue` 中间栏项目列表组件：新建项目按钮 + 搜索框 + 状态/年度筛选 + 项目卡片列表（左侧状态色条+标题+客户名+状态标签）+ 选中高亮
    - _需求: 16.8_
- [x] 30.3 实现 `DetailProjectPanel.vue` 右侧栏项目详情面板：5个Tab页签（概览/指标/底稿/试算表/报表）+ 项目基本信息el-descriptions + 6个快捷操作入口（试算表/调整分录/底稿/报表/附注/重要性）+ 指标卡片占位
    - _需求: 16.8_
- [x] 30.4 重写 `DefaultLayout.vue` 为三栏容器：首页(/)和项目列表(/projects)显示三栏浏览模式（中间栏项目列表+右侧栏项目详情），具体项目子页面(/projects/:id/xxx)隐藏中间栏、右侧栏全宽显示router-view内容
    - _需求: 16.8, 16.9_
- [x] 30.5 实现中间栏内容切换：根据左侧导航选中项动态切换中间栏内容（项目情况→项目列表、人员委派→人员列表、知识库→文档树、工时管理→工时录入等）
    - _需求: 16.8_
- [x] 30.6 实现右侧栏Tab页签内容填充：底稿索引Tab（按致同编码体系组织的底稿树）、试算表预览Tab（只读表格）、报表预览Tab（四表只读预览）
    - _需求: 16.8_

### 31. vue-office 轻量级文档预览（对应需求17）

- [x] 31.1 安装 vue-office 依赖：@vue-office/docx、@vue-office/excel、@vue-office/pdf
    - _需求: 17.1_
- [x] 31.2 实现 `AttachmentPreview.vue` 统一预览组件：根据文件类型自动选择vue-office-docx/excel/pdf渲染，scoped样式隔离
    - _需求: 17.2, 17.4_
- [x] 31.3 集成到附件列表页面：附件列表中点击预览按钮→弹窗显示vue-office预览，点击编辑按钮→打开ONLYOFFICE
    - _需求: 17.3, 17.5_

### 32. Teable/Grist 评估（对应需求18）

- [x] 32.1 评估 Teable 和 Grist 的部署复杂度、API集成可行性、数据同步方案、UI嵌入选项、许可证兼容性
    - _需求: 18.1, 18.3_
- [x] 32.2 选择一个用例（PBC清单管理/函证管理/底稿索引管理）进行POC验证
    - _需求: 18.2, 18.4_
- [x] 32.3 输出评估报告（采纳/推迟/拒绝）及理由
    - _需求: 18.5_
