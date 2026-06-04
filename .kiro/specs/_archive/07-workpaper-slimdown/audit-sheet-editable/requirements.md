# Requirements: 审定表可编辑升级 (GtAuditSheet)

## Introduction

将审定表从只读 `GtGridSheet`（HTML `<table>` 死网格 + formula_hint 图标）升级为参照合并工作底稿 `NetAssetSheet` 的**结构化可编辑表**。所有科目共用一个通用组件 `GtAuditSheet.vue`，行项目从底稿 xlsx 模板动态解析。

现状问题：
- GtGridSheet 纯只读，用户无法编辑调整数/原因分析
- 公式标注(formula_hint)仅展示图标 + tooltip，不执行实际计算
- TB 取数列全显示「-」，没有从 formula_engine/TB() 填值
- 无保存/导入导出能力

目标：审定表可直接编辑（调整数/原因），自动计算列实时联动，TB 取数自动填充，支持保存/导入导出——与合并工作底稿体验一致。

## Glossary

- **AuditSheet（审定表）**: 审计底稿中的 F 类/审定表 sheet，class_code 以 `F-审定表` 分类，当前 componentType=`univer`
- **GtAuditSheet**: 新建通用可编辑审定表 Vue 组件，替代 univer/GtGridSheet 渲染
- **AuditSheetRow（审定表行）**: 结构化行数据，含项目名 + 8 列数值（从模板 xlsx 动态解析行项目名）
- **固定列语义**: 期初未审数 / 期初审定数 / 本期未审数 / 账项调整 / 重分类调整 / 审定数 / 变动额 / 变动率 / 原因分析
- **自动计算列**: 审定数=未审+调整+重分类；变动额=期末审定-期初审定；变动率=变动额÷期初审定
- **TB 取数列**: 未审数列，从 formula_engine TB() 自动填充
- **可编辑列**: 账项调整 / 重分类调整 / 原因分析（用户手动输入）

## Requirements

### Requirement 1: 通用可编辑审定表组件

**User Story:** As an 审计助理, I want 审定表以可编辑表格形式展示, so that 我能直接在表内编辑调整数和原因分析，无需切换到外部工具。

#### Acceptance Criteria
1. WHEN 底稿 sheet 的 componentType 为 `audit-sheet`, THE 系统 SHALL 渲染 GtAuditSheet 组件（el-table 结构化表格）。
2. THE GtAuditSheet SHALL 展示固定列：序号 / 项目 / 期初未审数 / 期初审定数 / 本期未审数 / 账项调整 / 重分类调整 / 审定数 / 变动额 / 变动率 / 原因分析。
3. THE GtAuditSheet SHALL 允许用户编辑"账项调整"/"重分类调整"/"原因分析"列（el-input-number / el-input）。
4. THE GtAuditSheet SHALL 在未审数/调整数变更时实时计算：审定数=未审+调整+重分类、变动额=期末审定-期初审定、变动率=变动额÷期初审定。
5. THE GtAuditSheet SHALL 对自动计算列用 GT 紫色标识（与 NetAssetSheet 的 `ws-auto-cell` 一致）。

### Requirement 2: 行项目从模板动态解析

**User Story:** As an 审计助理, I want 审定表的行项目自动从底稿模板解析, so that 不同科目（应收票据/固定资产/无形资产等）自动展示对应的行结构。

#### Acceptance Criteria
1. WHEN GtAuditSheet 加载, THE 后端 SHALL 从模板 xlsx 解析出行项目名列表（如"应收票据-原值"/"坏账准备"/"净值"）。
2. THE 行解析 SHALL 复用/扩展现有 `wp_grid_extract.extract_grid_from_sheet` 能力，提取项目列（A 列）非空行作为行项目。
3. IF 模板不存在或解析失败, THEN 返回空行列表，前端显示空态+手动新增行入口。
4. THE 行项目结构 SHALL 支持层级缩进（如"一、应收票据"/"  原值"/"  坏账"/"  净值"/"合计"）。

### Requirement 3: TB 自动取数填充

**User Story:** As an 审计助理, I want 未审数列自动从试算表取数填充, so that 我无需手动抄写数据。

#### Acceptance Criteria
1. WHEN 审定表加载, THE 后端 SHALL 调用 formula_engine TB() 按科目编码+列语义批量取数，填充期初未审/本期未审列。
2. THE TB 取数 SHALL 使用 `wp_account_mapping.json` 中该底稿 wp_code 对应的科目编码映射。
3. IF TB 数据不存在（项目未导入账套）, THEN 未审数列显示"—"，不影响用户手动编辑调整列。
4. WHEN 用户重新导入 TB 数据后刷新, THE 未审数列 SHALL 更新为最新 TB 值。

### Requirement 4: 保存与持久化

**User Story:** As an 审计助理, I want 编辑的调整数和原因能保存, so that 下次打开底稿时数据不丢失。

#### Acceptance Criteria
1. THE GtAuditSheet SHALL 提供保存按钮，点击后将结构化行数据写回 `working_paper.parsed_data`。
2. THE 持久化格式 SHALL 为 `parsed_data.html_data[sheet_name].audit_rows: AuditSheetRow[]`（结构化 JSON，非 cells 扁平 dict）。
3. WHEN 下次加载该 sheet, THE GtAuditSheet SHALL 优先读取 `audit_rows` 持久化数据；无持久化时从模板生成默认行。
4. THE 保存 SHALL 触发 `touch_after_parsed_data_commit` 使注册表缓存失效。

### Requirement 5: 导入导出

**User Story:** As an 审计助理, I want 能导出审定表模板填写后再导入, so that 我可以离线批量填写数据。

#### Acceptance Criteria
1. THE GtAuditSheet SHALL 提供"导出模板"按钮，生成含行项目名 + 列标题的 xlsx 模板。
2. THE GtAuditSheet SHALL 提供"导入 Excel"按钮，按行名匹配导入数据。
3. WHEN 导入完成, THE 系统 SHALL 显示匹配预览（匹配行数/跳过行数），用户确认后更新表格。

### Requirement 6: 行操作

**User Story:** As an 审计助理, I want 能新增/删除/还原行, so that 我可以根据实际情况调整审定表结构。

#### Acceptance Criteria
1. THE GtAuditSheet SHALL 提供"+新增行"按钮，在尾部追加空行。
2. THE GtAuditSheet SHALL 提供多选+批量删除能力。
3. THE GtAuditSheet SHALL 提供"还原"按钮，恢复为模板默认行结构。
4. THE 合计行 SHALL 自动汇总明细行（computed，不可编辑）。

### Requirement 7: componentType 注册与分类切换

**User Story:** As a 开发者, I want 审定表有独立的 componentType, so that 与 univer/GtGridSheet 解耦，可独立迭代。

#### Acceptance Criteria
1. THE 系统 SHALL 新增 componentType=`audit-sheet` 并注册进 `htmlRendererRegistry`。
2. THE `wp_classification_service` SHALL 将 class_code=`F-审定表` 的 sheet 映射到 componentType=`audit-sheet`（原映射为 `univer`）。
3. THE GtWpRenderer SHALL 按 componentType=`audit-sheet` 分发到 GtAuditSheet 组件。
4. WHERE class_code 非 `F-审定表` 的 F/G 类 sheet（如 `F-明细表`/`G-测算`），仍保持 componentType=`univer` 不变。
