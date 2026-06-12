# Requirements Document

## Introduction

底稿统一导入导出功能为审计作业平台底稿模块提供完整的离线工作流支持。审计人员可将底稿导出为标准办公格式（xlsx/docx）进行离线编辑，编辑完成后回导入系统并自动检测冲突、校验数据完整性、创建新版本。同时支持批量按审计循环打包导出、跨项目模板复制，覆盖全部底稿类型（表格/文字/程序表/审定表）。

## Glossary

- **Export_Engine**: 底稿导出引擎，负责将底稿数据序列化为 xlsx/docx 格式文件
- **Import_Engine**: 底稿导入引擎，负责解析 xlsx/docx 文件并恢复底稿数据
- **Conflict_Detector**: 冲突检测器，基于快照 hash 比对导出时与当前版本差异
- **Format_Validator**: 格式校验器，验证导入文件的结构和数据完整性
- **Template_Copier**: 模板复制器，负责跨项目底稿模板复制
- **Batch_Packager**: 批量打包器，按审计循环筛选并打包多份底稿为 ZIP
- **Version_Manager**: 版本管理器，导入时创建新版本保留历史
- **Metadata_Bundle**: 元数据包，包含底稿编号(wp_code)、编制人、编制日期、复核状态
- **Snapshot_Hash**: 导出快照哈希，导出时对底稿内容计算的摘要值，用于冲突检测
- **Audit_Cycle**: 审计循环代号（A~S），用于筛选和组织底稿

## Requirements

### Requirement 1: 单底稿导出

**User Story:** As a 审计人员, I want to 将单份底稿导出为 xlsx 或 docx 格式, so that 我可以离线编辑底稿内容。

#### Acceptance Criteria

1. WHEN 用户请求导出单份底稿, THE Export_Engine SHALL 根据底稿类型（表格/审定表→xlsx，文字→docx）生成对应格式文件
2. WHEN 导出表格类底稿, THE Export_Engine SHALL 保留全部 sheet 页签结构和单元格数据
3. WHEN 导出文字类底稿, THE Export_Engine SHALL 保留段落结构、标题层级和表格内容
4. THE Export_Engine SHALL 在导出文件中嵌入 Metadata_Bundle（底稿编号、编制人、编制日期、复核状态）
5. WHEN 导出完成, THE Export_Engine SHALL 计算并存储 Snapshot_Hash 到数据库用于后续冲突检测
6. WHEN 底稿文件路径不存在, THE Export_Engine SHALL 回退到模板库查找对应 wp_code 的标准模板并导出

### Requirement 2: 批量打包导出

**User Story:** As a 项目经理, I want to 按审计循环批量打包导出底稿, so that 我可以一次性分发离线工作任务给团队成员。

#### Acceptance Criteria

1. WHEN 用户指定审计循环代号列表, THE Batch_Packager SHALL 查询该循环下全部已生成底稿并打包为 ZIP
2. THE Batch_Packager SHALL 按 `{audit_cycle}/{wp_code}_{wp_name}.{ext}` 目录结构组织 ZIP 内文件
3. THE Batch_Packager SHALL 在 ZIP 根目录生成 manifest.json 包含文件清单、各文件 SHA-256、导出时间和项目元数据
4. WHEN 指定的循环下无可导出底稿, THE Batch_Packager SHALL 返回明确错误信息而非空 ZIP
5. WHEN 单个底稿导出失败, THE Batch_Packager SHALL 跳过该底稿、记录警告日志，并在 manifest.json 中标注失败项
6. THE Batch_Packager SHALL 支持按底稿状态（draft/in_review/approved）过滤导出范围

### Requirement 3: 元数据嵌入与提取

**User Story:** As a 审计人员, I want to 导出文件自带底稿元信息, so that 离线查看时无需系统也能识别底稿归属。

#### Acceptance Criteria

1. THE Export_Engine SHALL 在 xlsx 文件的自定义属性(Custom Properties)中写入 wp_code、project_id、file_version、export_timestamp、preparer、reviewer、review_status
2. THE Export_Engine SHALL 在 docx 文件的 core_properties.comments 字段中以 JSON 格式写入全部元数据（wp_code、project_id、file_version、export_timestamp、preparer、reviewer、review_status），以规避 python-docx 对 custom properties 支持有限的问题
3. WHEN 导入文件时, THE Import_Engine SHALL 从文件属性中提取元数据用于匹配目标底稿
4. IF 导入文件缺少必要元数据(wp_code 或 project_id), THEN THE Import_Engine SHALL 拒绝导入并返回缺失字段列表


### Requirement 4: 离线编辑冲突检测

**User Story:** As a 审计人员, I want to 导入编辑后的底稿时系统自动检测冲突, so that 我不会意外覆盖他人同期修改的内容。

#### Acceptance Criteria

1. WHEN 底稿导出时, THE Export_Engine SHALL 对底稿全部 sheet 内容计算 SHA-256 哈希并存储为 Snapshot_Hash
2. WHEN 用户提交导入请求, THE Conflict_Detector SHALL 比对文件元数据中的 file_version 与服务器当前版本
3. IF 服务器版本高于导入文件携带的 file_version, THEN THE Conflict_Detector SHALL 标记为版本冲突并返回冲突详情（冲突版本号、最后修改人、修改时间）
4. WHEN 检测到冲突, THE Conflict_Detector SHALL 提供三种处理选项：强制覆盖、创建并行版本、取消导入
5. THE Conflict_Detector SHALL 对底稿内容计算当前 hash 并与导出时的 Snapshot_Hash 比对，仅内容实际变更时才标记为实质冲突
6. WHEN 用户选择强制覆盖, THE Import_Engine SHALL 记录覆盖操作到审计日志（操作人、时间、被覆盖版本号）

### Requirement 5: 导入格式校验与数据完整性检查

**User Story:** As a 系统管理员, I want to 导入时自动校验文件格式和数据完整性, so that 损坏或被篡改的文件不会污染系统数据。

#### Acceptance Criteria

1. WHEN 收到导入文件, THE Format_Validator SHALL 验证文件扩展名与 MIME 类型一致（xlsx→application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, docx→application/vnd.openxmlformats-officedocument.wordprocessingml.document）
2. WHEN 导入 xlsx 文件, THE Format_Validator SHALL 验证 sheet 页签名称与目标底稿的 classification 结构匹配
3. WHEN 导入 xlsx 文件, THE Format_Validator SHALL 检查必填单元格（由底稿 render_schema 定义的 required 字段）是否有值
4. IF 文件解析失败（文件损坏、加密、格式不支持）, THEN THE Format_Validator SHALL 返回具体错误原因而非通用异常
5. THE Format_Validator SHALL 检查导入数据中数值型字段的类型正确性（非数值内容填入金额单元格应标记为警告）
6. WHEN 校验完成, THE Format_Validator SHALL 返回结构化校验报告（passed/warnings/errors 三级分类，每项含位置和描述）

### Requirement 6: 导入创建新版本

**User Story:** As a 审计人员, I want to 导入操作创建新版本而非覆盖当前内容, so that 我可以随时回溯历史版本。

#### Acceptance Criteria

1. WHEN 导入成功, THE Version_Manager SHALL 递增 working_paper.file_version 并保留原版本文件
2. THE Version_Manager SHALL 记录版本元数据（版本号、创建时间、创建人、来源=import、文件大小、content_hash）
3. WHEN 导入创建新版本, THE Version_Manager SHALL 将旧版本文件移至归档路径 `storage/projects/{project_id}/archive/{wp_id}/v{n}/`
4. THE Version_Manager SHALL 保留最近 10 个版本的文件，超出部分仅保留元数据记录
5. WHEN 导入完成, THE Version_Manager SHALL 发布 WORKPAPER_SAVED 事件触发下游级联更新（试算表重算、stale 标记）
6. IF 版本归档失败（磁盘空间不足）, THEN THE Version_Manager SHALL 记录错误日志但不阻塞导入操作本身

### Requirement 7: 跨项目底稿模板复制

**User Story:** As a 项目经理, I want to 将一个项目的底稿作为模板复制到另一个项目, so that 类似客户的审计可以复用已有工作成果。

#### Acceptance Criteria

1. WHEN 用户选择源底稿和目标项目, THE Template_Copier SHALL 复制底稿文件和索引记录到目标项目
2. THE Template_Copier SHALL 清除源底稿的业务数据（金额、日期、具体描述）仅保留结构和程序步骤
3. THE Template_Copier SHALL 重新生成目标底稿的 wp_index 记录（新 UUID、关联目标 project_id）
4. WHEN 目标项目已存在相同 wp_code 的底稿, THE Template_Copier SHALL 提示用户选择跳过或覆盖
5. THE Template_Copier SHALL 支持批量复制整个审计循环的全部底稿
6. WHEN 复制完成, THE Template_Copier SHALL 将新底稿状态设为 draft 并清除复核状态

### Requirement 8: 程序表底稿导出

**User Story:** As a 审计人员, I want to 导出程序表底稿时保留程序步骤和执行状态, so that 离线填写程序执行结果后可以回导。

#### Acceptance Criteria

1. WHEN 导出程序表类底稿, THE Export_Engine SHALL 将程序步骤导出为 xlsx 中独立 sheet（程序编号、程序描述、执行状态、执行结论、执行人）
2. THE Export_Engine SHALL 标记只读列（程序编号、程序描述）和可编辑列（执行状态、执行结论）
3. WHEN 导入程序表, THE Import_Engine SHALL 仅更新可编辑列的值，只读列用于匹配定位而非覆盖
4. IF 导入的程序表行数与服务器不一致（程序被新增或删除）, THEN THE Import_Engine SHALL 按程序编号匹配现有行并报告不可匹配的新增行

### Requirement 9: 审定表底稿导出

**User Story:** As a 审计人员, I want to 导出审定表底稿时保留科目明细和调整分录关联, so that 离线可以查看完整审定数据。

#### Acceptance Criteria

1. WHEN 导出审定表类底稿, THE Export_Engine SHALL 导出科目明细行（科目编码、科目名称、未审数、调整数、审定数）
2. THE Export_Engine SHALL 在审定表 sheet 中标注调整分录来源引用（adjustment_id）作为只读批注
3. WHEN 导入审定表, THE Import_Engine SHALL 忽略审定数列（由系统自动计算）仅接受备注和工作结论字段的更新
4. THE Export_Engine SHALL 在审定表 sheet 末尾附加汇总行（合计、借贷平衡校验）

### Requirement 10: 导出导入 Round-Trip 一致性

**User Story:** As a 开发者, I want to 确保导出再导入后底稿数据无损, so that 离线工作流不会引入数据偏差。

#### Acceptance Criteria

1. FOR ALL 底稿类型, 导出后未修改直接导入 SHALL 产生与原始内容逐 sheet 逐单元格一致的结果（Round-Trip 属性）
2. THE Export_Engine SHALL 使用确定性序列化（固定列顺序、固定数值精度 decimal(20,4)、固定日期格式 ISO-8601）
3. THE Import_Engine SHALL 使用与 Export_Engine 相同的列映射和类型转换规则
4. WHEN Round-Trip 校验检测到数据差异, THE Import_Engine SHALL 在校验报告中列出差异位置和值对比
