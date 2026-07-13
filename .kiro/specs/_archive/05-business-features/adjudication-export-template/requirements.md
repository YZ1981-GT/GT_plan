# Requirements Document

## Introduction

当前全部审定表（D1-1 ~ N5-1，pattern `^[A-N]\d+-1$`）的"导出模板"按钮调用通用端点 `GET /workpapers/{wp_id}/export-template`，直接返回磁盘源 xlsx 文件。该源文件列结构与前端 HTML 审定表的实际多行合并表头不一致，且缺少编制说明 sheet，导致用户导入时列错位、不知填写规则。

本 spec 新建一个**审定表导出模板动态生成器**，在后端按 wp_code 识别审定表后，动态生成含正确多行合并表头 + 编制说明 + 行骨架的空白 xlsx 模板，替代直接返回源 xlsx 的行为。全部 D~N 审定表复用同一生成器，差异部分（标题、科目行、账龄列）通过参数化注入。

## Glossary

- **Adjudication_Table**: 审定表，wp_code 匹配 `^[A-N]\d+-1$` 的底稿（如 D2-1/F1-1/K1-1），列结构为"项目 / 期初四列(未审/AJE/RJE/审定) / 期末四列(未审/AJE/RJE/审定) / 变动额 / 变动率 / 原因分析"
- **Template_Generator**: 审定表导出模板生成器服务，接收 wp_id/wp_code，动态生成空白 xlsx 模板
- **Multi_Row_Header**: 多行合并表头，xlsx 第 2-3 行通过单元格合并实现的多级列头结构（与前端 el-table 多级表头对齐）
- **Instruction_Sheet**: 编制说明 sheet，xlsx 第一个 sheet，包含各列含义、只读列标识、填报规则和导入注意事项
- **Row_Skeleton**: 行骨架，模板的项目列预填该审定表的标准科目行名称（从 account_package_registry / render-schema / html_data 取）
- **Aging_Column**: 账龄列，D2/D3/F1/K1/K3/G5 等审定表特有的动态列，由项目级 AgingConfig 配置决定段数和列头标签
- **Export_Endpoint**: 现有端点 `GET /workpapers/{wp_id}/export-template`（`wp_render_config.py`）

## Requirements

### Requirement 1: 审定表 wp_code 识别与路由

**User Story:** As a 审计助理, I want 当我点击审定表的"导出模板"按钮时系统自动识别并走动态生成路径, so that 我不再收到列结构不匹配的旧模板文件。

#### Acceptance Criteria

1. WHEN Export_Endpoint 接收到请求且底稿 wp_code 匹配正则 `^[A-N]\d+-1$`, THE Export_Endpoint SHALL 将请求委托给 Template_Generator 生成动态模板
2. WHEN Export_Endpoint 接收到请求且底稿 wp_code 不匹配 `^[A-N]\d+-1$`, THE Export_Endpoint SHALL 保持原有逻辑返回磁盘源 xlsx 文件
3. THE Export_Endpoint SHALL 使用 wp_index 表中的 wp_code 字段进行匹配判定

### Requirement 2: 动态模板 xlsx 生成

**User Story:** As a 审计助理, I want 导出的 xlsx 模板包含与前端 HTML 审定表完全一致的多行合并表头结构, so that 我在 Excel 中编辑后导入时列能正确对齐。

#### Acceptance Criteria

1. THE Template_Generator SHALL 使用 openpyxl 库动态生成 xlsx 文件（非读取磁盘源文件）
2. THE Template_Generator SHALL 生成一个包含至少两个 sheet 的 workbook：第 1 个 sheet 为 Instruction_Sheet，第 2 个 sheet 为数据模板 sheet
3. WHEN 生成数据模板 sheet, THE Template_Generator SHALL 在第 1 行写入审定表标题（格式为"{科目名称}审定表 {wp_code}"）
4. WHEN 生成数据模板 sheet, THE Template_Generator SHALL 在第 2-3 行生成 Multi_Row_Header

### Requirement 3: 多行合并表头结构

**User Story:** As a 审计助理, I want 模板表头与前端 el-table 多级表头完全对齐, so that 视觉上一眼能确认列含义且导入时不需手动调整列序。

#### Acceptance Criteria

1. THE Template_Generator SHALL 在第 2 行生成一级列头："项目"、"期初"（合并 4 列）、"期末"（合并 4 列）、"变动额"、"变动率"、"原因分析"
2. THE Template_Generator SHALL 在第 3 行生成二级列头：期初下的"未审"、"AJE"、"RJE"、"审定"，期末下的"未审"、"AJE"、"RJE"、"审定"
3. THE Template_Generator SHALL 对"项目"、"变动额"、"变动率"、"原因分析"列在第 2-3 行进行纵向合并
4. THE Template_Generator SHALL 对"期初"和"期末"列在第 2 行进行横向合并（各跨 4 列）
5. THE Template_Generator SHALL 为表头行设置加粗字体、居中对齐和边框样式

### Requirement 4: 账龄动态列

**User Story:** As a 审计助理, I want 含账龄列的审定表（D2/D3/F1/K1/K3/G5）模板能按当前项目配置动态生成账龄列头, so that 账龄列数量和标签与我在前端看到的一致。

#### Acceptance Criteria

1. WHEN 审定表 wp_code 属于含账龄的科目（D2-1/D3-1/F1-1/K1-1/K3-1/G5-1）, THE Template_Generator SHALL 读取项目级 AgingConfig 获取账龄段列表
2. WHEN 账龄段列表可用, THE Template_Generator SHALL 在"审定"列之后、"变动额"列之前插入账龄动态列头
3. THE Template_Generator SHALL 复用 `_cycle_import_export_common.build_aging_headers` 生成账龄列标签
4. IF AgingConfig 读取失败, THEN THE Template_Generator SHALL 回退到该科目的默认预设账龄段生成列头

### Requirement 5: 编制说明 sheet

**User Story:** As a 审计助理, I want 模板 xlsx 的第一个 sheet 是编制说明, so that 我能了解每列的含义、哪些列只读自动计算、以及导入时的注意事项。

#### Acceptance Criteria

1. THE Template_Generator SHALL 在 Instruction_Sheet 中说明数据列含义（项目/期初四列/期末四列/变动额/变动率/原因分析）
2. THE Template_Generator SHALL 在 Instruction_Sheet 中标识只读自动计算列：期初审定 = 期初未审 + 期初AJE + 期初RJE，期末审定 = 期末未审 + 期末AJE + 期末RJE，变动额 = 期末审定 - 期初审定，变动率 = 变动额 / 期初审定
3. THE Template_Generator SHALL 在 Instruction_Sheet 中说明填报规则：用户仅需填写未审/AJE/RJE 列和原因分析列
4. THE Template_Generator SHALL 在 Instruction_Sheet 中说明导入注意事项：按项目列名称匹配行、只读列导入时忽略、空行跳过

### Requirement 6: 行骨架（项目列预填）

**User Story:** As a 审计助理, I want 模板的项目列已预填该审定表的标准科目行, so that 导入时能按行名称正确匹配数据、不需我手动输入科目名。

#### Acceptance Criteria

1. THE Template_Generator SHALL 从 account_package_registry 或 render-schema yaml 或后端 html_data 中获取该审定表的标准科目行定义
2. THE Template_Generator SHALL 将标准科目行名称按顺序填入数据模板 sheet 的"项目"列（从第 4 行开始）
3. WHEN 科目行包含分节标题行（如"流动资产"/"非流动资产"）, THE Template_Generator SHALL 保留分节结构并对标题行设置加粗样式
4. IF 行定义获取失败, THEN THE Template_Generator SHALL 生成仅含表头的空模板（项目列留空）并在 Instruction_Sheet 中注明"请手动填写项目列"

### Requirement 7: 中文文件名 RFC5987

**User Story:** As a 审计助理, I want 下载的模板文件名包含中文审定表名称, so that 我能在下载文件夹中一眼识别这是哪个审定表的模板。

#### Acceptance Criteria

1. THE Template_Generator SHALL 生成文件名格式为 `{wp_code}_{科目中文名}审定表_模板.xlsx`（如 "D2-1_应收账款审定表_模板.xlsx"）
2. THE Export_Endpoint SHALL 使用 RFC5987 编码规范设置 Content-Disposition header 中的 filename* 参数（格式为 `filename*=UTF-8''{encoded_filename}`）
3. THE Export_Endpoint SHALL 设置 Content-Type 为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### Requirement 8: 全审定表覆盖

**User Story:** As a 审计助理, I want 所有 D~N 审定表都能获得正确的动态模板, so that 无论哪个循环的审定表我都能导出结构正确的模板进行填报。

#### Acceptance Criteria

1. THE Template_Generator SHALL 覆盖以下全部审定表：D1-1/D2-1/D3-1/D4-1/D5-1/D6-1/D7-1/E1-1/F1-1/F2-1/F3-1/F4-1/F5-1/G1-1~G14-1/H1-1~H10-1/I1-1~I6-1/J1-1~J3-1/K1-1~K13-1/L1-1~L8-1/M1-1~M10-1/N1-1~N5-1
2. THE Template_Generator SHALL 通过统一的生成逻辑处理所有审定表，差异部分（标题、科目行、账龄列）通过 wp_code 参数化注入
3. WHEN 新增审定表 wp_code 满足 `^[A-N]\d+-1$` 模式, THE Template_Generator SHALL 自动适配生成模板（无需额外编码）

### Requirement 9: 不改变前端与其他导入导出逻辑

**User Story:** As a 开发者, I want 本功能仅改造"导出模板"按钮的后端响应, so that "导出数据"和"导入数据"功能不受影响、前端代码无需修改。

#### Acceptance Criteria

1. THE Export_Endpoint SHALL 保持原有 HTTP 接口签名不变（GET 方法、路径参数 wp_id、返回 xlsx 文件流）
2. THE Template_Generator SHALL 不修改"导出数据"端点（`export-data`）的任何逻辑
3. THE Template_Generator SHALL 不修改"导入数据"端点（`import-data`）的任何逻辑
4. THE Template_Generator SHALL 不要求前端代码做任何改动（前端已有"导出模板"按钮接通用端点）

### Requirement 10: 服务层架构规范

**User Story:** As a 开发者, I want 生成器作为独立服务模块实现并遵循平台架构规范, so that 代码可维护、可测试、符合工程铁律。

#### Acceptance Criteria

1. THE Template_Generator SHALL 作为独立服务文件实现（如 `adjudication_export_template_service.py`）
2. THE Template_Generator SHALL 遵循"service 只 flush 不 commit"的工程铁律（本服务为只读无需写库，但若需读取 AgingConfig 则只读查询）
3. THE Template_Generator SHALL 使用 openpyxl 库生成 xlsx（与项目已有依赖一致，不引入新依赖）
4. THE Template_Generator SHALL 返回 `io.BytesIO` 流供 Export_Endpoint 通过 StreamingResponse 返回
