# Requirements Document

## Introduction

本功能对审计作业平台（FastAPI 后端 + Vue3 前端 + PostgreSQL 16）的建项流程进行增强，覆盖六块需求：企业代码必填与统一社会信用代码（USCC）格式校验、项目简称必填、项目唯一性校验、合并/单户同存的前端区分显示、批量建项（模板导出 + 导入 + 数据导出）、以及独立账套导入页。

目标是在新建项目时强制采集结构化、可校验的关键信息（企业代码、项目简称、报表类型），避免重复建项，并改善账套导入与多项目展示的用户体验。所有校验在前端与后端双侧执行；存量项目（多数 company_code 为空）不受新约束影响。

本文档仅描述功能需求（WHAT），具体技术实现（迁移脚本、ORM、组件接线等 HOW）留待设计阶段。

## Glossary

- **Project_Service**: 后端建项服务，负责创建单个或批量项目并执行校验（对应 `project_wizard_service.create_project()`）。
- **USCC_Validator**: 统一社会信用代码格式与校验码校验组件，前后端各有一份等价实现。
- **Uniqueness_Checker**: 项目唯一性校验组件，按企业代码 + 审计年度 + 报表类型三元组判重。
- **Batch_Import_Service**: 批量建项服务，解析导入文件并逐行复用单项目建项校验逻辑。
- **Template_Exporter**: 建项模板导出组件，生成含「说明事项」工作表的 Excel 模板。
- **Project_Data_Exporter**: 项目数据导出组件，将已存在项目内容导出为 Excel。
- **Project_Form**: 前端建项表单（对应 `BasicInfoStep.vue`）。
- **Project_List_View**: 前端项目列表与下拉展示组件（对应 `Projects.vue` 及相关下拉）。
- **Ledger_Import_Page**: 独立账套导入页面（新增独立路由），完成上传→识别→列映射→预览→入库流程。
- **USCC**: 统一社会信用代码（Unified Social Credit Code），标准 18 位法人和其他组织身份代码。
- **USCC_Charset**: USCC 允许的字符集，由数字 0-9 与大写字母组成，且不含字母 I、O、Z、S、V。
- **Company_Code**: 企业代码，存储于 `projects.company_code`，取值为 USCC。
- **Short_Name**: 项目简称，新增字段 `projects.short_name`，用于审计报告正文及其他文档引用。
- **Audit_Year**: 审计年度，对应建项数据中的 `audit_year`。
- **Report_Scope**: 报表类型，取值为 `standalone`（单户）或 `consolidated`（合并）。
- **Uniqueness_Triple**: 唯一性三元组，即 Company_Code + Audit_Year + Report_Scope 的组合。
- **Parent_Standalone**: 作为合并母公司的单户项目，即与某合并项目共享相同企业代码、年度且报表类型为 `standalone` 的项目。
- **Legacy_Project**: 存量项目，即本功能上线前已存在的项目（多数 Company_Code 为空）。

## Requirements

### Requirement 1: 企业代码必填与 USCC 格式校验

**User Story:** 作为审计项目经理，我希望建项时企业代码必填且符合统一社会信用代码格式，以便每个项目都能用规范的企业身份标识进行唯一定位和后续引用。

#### Acceptance Criteria

1. WHEN 用户在 Project_Form 提交建项请求且 Company_Code 为空, THEN THE Project_Service SHALL 拒绝创建并返回提示"企业代码为必填项"
2. WHEN 用户在 Project_Form 提交建项请求且 Company_Code 为空, THEN THE Project_Form SHALL 阻止提交并在企业代码字段显示提示"企业代码为必填项"
3. WHEN 提交的 Company_Code 长度不等于 18 个字符, THEN THE USCC_Validator SHALL 判定为非法并返回提示"统一社会信用代码必须为 18 位"
4. WHEN 提交的 Company_Code 包含 USCC_Charset 之外的字符, THEN THE USCC_Validator SHALL 判定为非法并返回提示"统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）"
5. WHEN 提交的 Company_Code 第 18 位校验码与前 17 位按模 31 算法计算出的校验码不一致, THEN THE USCC_Validator SHALL 判定为非法并返回提示"统一社会信用代码校验码错误"
6. WHEN 提交的 Company_Code 为 18 位、字符全部属于 USCC_Charset 且第 18 位校验码通过模 31 校验, THEN THE USCC_Validator SHALL 判定为合法
7. THE USCC_Validator SHALL 在前端与后端各提供一份等价的校验实现，且对同一输入返回一致的合法性判定
8. FOR ALL 提交的 Company_Code 字符串，前端 USCC_Validator 的合法性判定结果 SHALL 与后端 USCC_Validator 的合法性判定结果一致（一致性属性）

### Requirement 2: 项目简称必填

**User Story:** 作为审计助理，我希望建项时填写项目简称，以便在审计报告正文及其他文档中以简短一致的名称引用该项目。

#### Acceptance Criteria

1. THE Project_Service SHALL 在项目数据模型中持久化 Short_Name 字段
2. WHEN 用户在 Project_Form 提交建项请求且 Short_Name 为空, THEN THE Project_Service SHALL 拒绝创建并返回提示"项目简称为必填项"
3. WHEN 用户在 Project_Form 提交建项请求且 Short_Name 为空, THEN THE Project_Form SHALL 阻止提交并在项目简称字段显示提示"项目简称为必填项"
4. WHEN 用户提交的 Short_Name 经去除首尾空白后为非空字符串, THEN THE Project_Service SHALL 将该 Short_Name 与项目一同持久化
5. WHEN 已创建的项目存在 Short_Name, THEN THE Project_Service SHALL 在项目数据读取响应中返回该 Short_Name 供审计报告正文及其他文档引用

### Requirement 3: 项目唯一性校验

**User Story:** 作为审计项目经理，我希望系统阻止重复建项，以便同一单位同一年度同一报表类型不会被建立多个项目。

#### Acceptance Criteria

1. WHEN 用户提交建项请求且已存在 Uniqueness_Triple 相同的非删除项目, THEN THE Uniqueness_Checker SHALL 拒绝创建并返回提示"已存在该单位该年度的[单户/合并]项目"
2. WHERE 提交的 Report_Scope 为 `standalone`, WHEN 检测到 Uniqueness_Triple 重复, THEN THE Uniqueness_Checker SHALL 在提示中使用"单户"字样
3. WHERE 提交的 Report_Scope 为 `consolidated`, WHEN 检测到 Uniqueness_Triple 重复, THEN THE Uniqueness_Checker SHALL 在提示中使用"合并"字样
4. WHEN 用户提交建项请求且不存在 Uniqueness_Triple 相同的非删除项目, THEN THE Uniqueness_Checker SHALL 允许创建
5. WHEN 提交的两个建项请求 Company_Code 与 Audit_Year 相同但 Report_Scope 不同, THEN THE Uniqueness_Checker SHALL 允许两个项目同时存在
6. THE Uniqueness_Checker SHALL 仅对新建项目执行唯一性校验，且 SHALL NOT 修改或拒绝 Legacy_Project
7. WHILE 校验唯一性, THE Uniqueness_Checker SHALL 排除已软删除（is_deleted = true）的项目

### Requirement 4: 合并/单户同存的前端区分显示

**User Story:** 作为审计人员，我希望在项目列表和下拉中区分合并项目与作为合并母公司的单户项目，以便在两者公司名称和企业代码相同时不产生歧义。

#### Acceptance Criteria

1. WHERE 项目的 Report_Scope 为 `consolidated`, WHEN Project_List_View 展示该项目, THEN THE Project_List_View SHALL 在公司名称后追加后缀"（合并）"
2. WHERE 项目为 Parent_Standalone, WHEN Project_List_View 展示该项目, THEN THE Project_List_View SHALL 在公司名称后追加后缀"（母公司）"
3. WHERE 项目的 Report_Scope 为 `standalone` 且不是 Parent_Standalone, WHEN Project_List_View 展示该项目, THEN THE Project_List_View SHALL 展示公司名称且不追加合并或母公司后缀
4. THE Project_List_View SHALL 在项目列表与项目下拉两处使用一致的后缀规则
5. WHEN 同一 Company_Code 与 Audit_Year 下同时存在合并项目与 Parent_Standalone, THEN THE Project_List_View SHALL 通过后缀使两者在显示上可区分

### Requirement 5: 批量建项（模板导出、批量导入、数据导出）

**User Story:** 作为审计项目经理，我希望导出建项模板、批量导入多个项目，并能将已填好的项目内容一次性导出，以便高效创建项目并备份或迁移项目信息。

#### Acceptance Criteria

1. WHEN 用户请求导出建项模板, THEN THE Template_Exporter SHALL 生成一个 Excel 文件，包含一个数据填写工作表与一个名为「说明事项」的工作表
2. THE Template_Exporter SHALL 在「说明事项」工作表中说明各字段填写规则、USCC 格式要求以及 Report_Scope 的可选值（单户 standalone / 合并 consolidated）
3. WHEN 用户上传已填写的建项模板文件并发起批量导入, THEN THE Batch_Import_Service SHALL 解析文件中的每一行并为每一行执行与单项目建项相同的校验逻辑（含企业代码必填、USCC 格式校验、项目简称必填、唯一性校验）
4. WHEN 批量导入的某一行未通过校验, THEN THE Batch_Import_Service SHALL 跳过该行的创建并在导入结果中返回该行的行号与具体错误原因
5. WHEN 批量导入的某一行通过全部校验, THEN THE Batch_Import_Service SHALL 创建对应项目
6. WHEN 批量导入完成, THEN THE Batch_Import_Service SHALL 返回成功创建数量与失败行明细
7. WHEN 用户请求导出已存在的项目内容, THEN THE Project_Data_Exporter SHALL 将所选项目的建项字段一次性导出为 Excel 文件
8. WHERE 导出的 Excel 文件再次作为批量导入输入, THE Batch_Import_Service SHALL 能够解析该文件的每一行（导出与导入字段结构一致）
9. WHEN 导出内容包含中文项目名称或中文客户名称, THEN THE Project_Data_Exporter SHALL 在导出文件中正确保留中文字符

### Requirement 6: 独立账套导入页

**User Story:** 作为审计助理，我希望有一个独立的账套导入页面完成上传到入库的完整流程，以便新建项目时不必进入查账页就能干净地导入账套，避免接口缺失导致的报错提示。

#### Acceptance Criteria

1. THE Ledger_Import_Page SHALL 提供一个独立于查账页的路由页面用于账套导入
2. WHEN 用户进入 Ledger_Import_Page, THEN THE Ledger_Import_Page SHALL 依次提供上传、识别、列映射、预览、入库五个步骤
3. WHEN 用户在 Ledger_Import_Page 上传账套文件, THEN THE Ledger_Import_Page SHALL 调用账套识别接口并展示识别结果与列映射界面
4. WHEN 用户在 Ledger_Import_Page 确认列映射并提交, THEN THE Ledger_Import_Page SHALL 调用入库接口并展示导入进度
5. WHEN 账套导入成功完成, THEN THE Ledger_Import_Page SHALL 跳转至查账页
6. IF 账套识别或入库接口返回错误, THEN THE Ledger_Import_Page SHALL 在当前页面以可读的中文错误信息展示该错误
7. THE Ledger_Import_Page SHALL 复用既有 `components/ledger-import/` 组件库完成上传、识别、列映射、预览、进度与错误展示
