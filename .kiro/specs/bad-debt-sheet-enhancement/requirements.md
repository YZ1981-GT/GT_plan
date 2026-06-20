# Requirements Document

## Introduction

为坏账准备明细表组件（GtBadDebtSheet，componentType=bad-debt-sheet）增加四项增强功能：导出空模板、导出含数据的完整表、Excel 导入（预览+确认写入）、以及账龄段枚举字典弹窗（预设段 + 自定义编辑 + 自动更新坏账组合子行）。该组件已在 D2-3/D1-4/G2-3 等循环坏账准备底稿中复用。

## Glossary

- **GtBadDebtSheet**：前端坏账准备明细表 Vue 组件，嵌套两层结构（父行=计提类别 → 子行=明细 → 合计行）
- **BadDebtExportService**：后端已有的坏账表致同 14 列模板 xlsx 导出引擎
- **AMOUNT_COLS**：13 个金额列常量数组（amount_b ~ amount_n），对应期初/本期增加/本期减少/期末四组
- **Tree**：坏账准备嵌套树结构（parents[] → children[] + summary）
- **NestedTableService**：后端坏账准备嵌套表 CRUD 服务
- **Aging_Segment**：账龄分段（如"1年以内"/"1-2年"等），用于信用风险组合-账龄分析法的子行分类
- **Preview_Dialog**：导入预览弹窗，用户确认后方写入数据
- **Aging_Dictionary_Dialog**：账龄段枚举字典弹窗，供用户选择预设段或自定义编辑
- **Credit_Risk_Combination**：信用风险组合计提类别（provision_method=CREDIT_RISK_AGING），其子行按账龄段分类

## Requirements

### Requirement 1: 导出空模板

**User Story:** As a 审计人员, I want to 从坏账准备明细表导出一份空模板 xlsx, so that 我可以离线填写数据后再导入系统。

#### Acceptance Criteria

1. WHEN 用户点击工具栏"导出模板"按钮, THE GtBadDebtSheet SHALL 调用后端导出模板端点并下载一份 xlsx 文件
2. THE BadDebtExportService SHALL 生成包含当前坏账树父行层级结构的空模板（父行标签 + 子行标签，金额列为空）
3. THE 空模板 SHALL 保留 14 列标题结构（项目 + 13 金额列列标题）与分组表头（期初/本期增加/本期减少/期末）
4. THE 空模板 SHALL 按当前树结构输出父行（加粗）和子行（缩进两空格前缀）的项目名，金额单元格留空供用户填写
5. IF 当前树为空（无父行）, THEN THE BadDebtExportService SHALL 生成仅含列标题的空模板（无数据行）

### Requirement 2: 导出含数据的完整表

**User Story:** As a 审计人员, I want to 导出含当前已填金额的完整坏账准备表 xlsx, so that 我可以存档或离线审阅。

#### Acceptance Criteria

1. WHEN 用户点击工具栏"导出数据"按钮, THE GtBadDebtSheet SHALL 调用后端导出数据端点并下载一份 xlsx 文件
2. THE BadDebtExportService SHALL 生成包含全部已填金额的完整坏账表（父行汇总 + 子行明细 + 合计行）
3. THE 导出数据 xlsx SHALL 与现有 BadDebtExportService.export_workbook 输出格式一致（14 列 + 元信息表头）
4. WHEN 金额列值为空（null）, THE 导出引擎 SHALL 输出空单元格（不填 0）

### Requirement 3: Excel 导入

**User Story:** As a 审计人员, I want to 导入一份填写完毕的坏账准备 Excel 文件, so that 批量数据可以快速录入系统，避免逐行手动输入。

#### Acceptance Criteria

1. WHEN 用户点击工具栏"导入"按钮并选择 xlsx 文件, THE GtBadDebtSheet SHALL 将文件上传至后端解析端点
2. THE Import_Service SHALL 按 A 列项目名与当前树的 row_label 进行行匹配（去除子行缩进空格后精确匹配）
3. WHEN 匹配成功, THE Import_Service SHALL 返回匹配结果列表（包含每行的匹配状态：matched/unmatched/new）
4. WHEN 后端返回匹配结果, THE GtBadDebtSheet SHALL 弹出 Preview_Dialog 展示匹配预览（行名 + 各金额列将写入的值 + 匹配状态标记）
5. WHILE Preview_Dialog 显示中, THE 用户 SHALL 可以查看每行的匹配状态并确认或取消导入
6. WHEN 用户在 Preview_Dialog 点击"确认导入", THE GtBadDebtSheet SHALL 调用后端写入端点，将匹配到的行金额批量更新
7. IF Excel 中某行的项目名在当前树中无匹配, THEN THE Preview_Dialog SHALL 将该行标记为"未匹配"并高亮显示，该行不参与写入
8. IF Excel 文件格式不合法（缺少 A 列或列数不足 14）, THEN THE Import_Service SHALL 返回 422 错误并附带错误描述
9. WHEN 批量写入完成, THE GtBadDebtSheet SHALL 刷新树数据并显示导入成功提示

### Requirement 4: 账龄段枚举字典弹窗

**User Story:** As a 审计人员, I want to 通过弹窗选择或自定义账龄分段方案, so that 信用风险组合（账龄分析法）的子行分类能灵活适配不同企业的账龄政策。

#### Acceptance Criteria

1. WHEN 用户点击工具栏"账龄段设置"按钮, THE GtBadDebtSheet SHALL 打开 Aging_Dictionary_Dialog
2. THE Aging_Dictionary_Dialog SHALL 预设"三年段"方案（1年以内 / 1-2年 / 2-3年 / 3年以上）
3. THE Aging_Dictionary_Dialog SHALL 预设"五年段"方案（1年以内 / 1-2年 / 2-3年 / 3-4年 / 4-5年 / 5年以上）
4. WHEN 用户选择某个预设方案, THE Aging_Dictionary_Dialog SHALL 在列表中高亮选中方案并实时预览账龄段列表
5. THE Aging_Dictionary_Dialog SHALL 支持自定义编辑模式：用户可新增账龄段、删除已有段、调整段的排序和名称
6. WHILE 自定义编辑模式中, THE Aging_Dictionary_Dialog SHALL 实时校验段名非空且不重复
7. WHEN 用户点击"确认"按钮, THE Aging_Dictionary_Dialog SHALL 将选定的账龄段列表保存至后端
8. WHEN 账龄段保存成功, THE GtBadDebtSheet SHALL 自动更新 Credit_Risk_Combination（信用风险组合-账龄分析法）父行下的子行：删除旧子行，按新账龄段列表依次创建新子行
9. IF Credit_Risk_Combination 父行不存在, THEN THE GtBadDebtSheet SHALL 先创建该父行再创建账龄段子行
10. IF 更新子行时原子行已有金额数据, THEN THE Aging_Dictionary_Dialog SHALL 在确认前警告"切换账龄段将清除已有金额数据，是否继续？"
11. THE 账龄段配置 SHALL 持久化至后端（关联 wp_index_id），重新打开底稿时加载上次配置

### Requirement 5: 导出与导入的往返一致性

**User Story:** As a 审计人员, I want to 导出模板→离线填写→导入 的完整流程数据准确无丢失, so that 线上线下协作可靠。

#### Acceptance Criteria

1. FOR ALL 已填写的坏账表, 导出数据后再导入 SHALL 产生与原始金额等价的结果（round-trip 一致性）
2. THE Import_Service 解析金额列 SHALL 支持整数和小数两种格式（如 100 和 100.00 均视为有效金额）
3. WHEN 导出模板后离线填写金额再导入, THE 匹配写入结果 SHALL 仅覆盖非空单元格对应的金额列，空单元格不覆盖原有值
