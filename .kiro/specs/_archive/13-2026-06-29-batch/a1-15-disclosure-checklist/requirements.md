# Requirements Document

## Introduction

A1-15（企业会计准则有关财务报表列报及披露核对表）需要从通用 `checklist-table` 升级为精美 HTML 专属组件，采用双模式渲染（结构化 HTML + Word 编辑）。

当前状态：`wp_code_overrides.json` 映射为 `skip`（由 A1 Dashboard 内嵌），`useA1SubWorkpapers.ts` 中 componentType 为 `checklist`，通过 GtChecklistTable 渲染。后端已有完整的 `_parse_a1_15` 解析器（35 章节、500~600 actionable 条目、100~200 guidance 子项），但 GtChecklistTable 的通用 UI 不够精美且缺乏科目跳转联动。

本 spec 新增专属 componentType `a1-15-disclosure-checklist`，实现：
1. 精美卡片式 HTML 核查表（分章节导航 + 条目卡片 + 进度可视化 + CAS 准则索引号显示）
2. 科目跳转联动——核对表条目中的科目/ref_index 可点击跳转到对应循环底稿（如"应收账款"→D2）
3. 双模式切换：结构化视图 + Word 编辑（复用 GtOnlyOfficeSheet）

**源模板结构（已验证）：**
- 文件：`A1-15 企业会计准则有关财务报表列报及披露核对表20141021.docx`
- 结构：3 个 Word 表格。表1=封面（25行），表2=目录（35+ 章节适用 Y/N），表3=核对表主体（934行×3列）
- 35 章节覆盖：一般列报要求、资产负债表项目（货币资金、应收票据、应收账款、预付款项、存货、长期股权投资…）、利润表项目、现金流量表项目、所有者权益变动表、附注披露要求等
- 每个 actionable 条目：`准则索引号 | 核查内容描述 | Y/N/NA + 备注 + 关联底稿索引`
- guidance 子项（a~j）：挂在 actionable 条目下，提供详细披露要求说明

## Glossary

- **Disclosure_Checklist**: A1-15 企业会计准则财务报表列报及披露核对表专属组件
- **CAS_Ref**: 中国企业会计准则条文索引号（如"CAS30.15"、"CAS6.13"），标识每条核对要求对应的准则依据
- **Section**: 核对表章节（共 35 个），按报表科目/披露主题分组（如"应收账款"、"固定资产"）
- **Actionable_Item**: 需要审计人员填写 Y/N/NA 结论的核查条目
- **Guidance_Child**: 挂在 actionable 条目下的详细披露要求说明（a~j 编号），辅助理解不可编辑
- **Section_Nav**: 左侧章节导航树，支持快速定位到指定章节
- **Ref_Index_Chip**: 关联底稿索引号（如"D2"、"E1"），渲染为可点击 GtIndexChip 跳转到对应循环底稿
- **Cross_Reference_Map**: 科目到循环底稿的预定义映射（如 应收账款→D2、存货→E1、固定资产→G1）
- **TOC_Applicability**: 目录级章节适用性标记，标记某章节整体不适用时跳过该章节所有条目
- **GtOnlyOfficeSheet**: 现有 OnlyOffice 文档编辑嵌入组件
- **Field_Overrides**: 用户填写数据的持久化机制（scope=a115_disclosure:{wp_id}）
- **GtA1Dashboard**: A1 仪表盘主组件，A1-15 作为其内嵌 Tab 之一渲染

## Requirements

### Requirement 1: 专属组件注册

**User Story:** 作为前端开发者，我需要一个专属 componentType 来实现 A1-15 的精美 HTML 渲染逻辑，使其不与通用 checklist-table 冲突。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 在 htmlRendererRegistry 中注册为 componentType `a1-15-disclosure-checklist`
2. THE wp_code_overrides.json SHALL 将 wp_code `A1-15` 映射为 `a1-15-disclosure-checklist`（替换当前 `skip`）
3. THE useA1SubWorkpapers SHALL 将 A1-15 Tab 的 componentType 更新为 `a1-15-disclosure-checklist`
4. THE GtA1Dashboard SHALL 识别 componentType `a1-15-disclosure-checklist` 并渲染对应的 Disclosure_Checklist 组件
5. THE VALID_COMPONENT_TYPES SHALL 包含 `a1-15-disclosure-checklist`
6. THE RENDERER_DISPATCH SHALL 新增 `a1-15-disclosure-checklist` 条目指向专属渲染策略函数

### Requirement 2: 双模式切换

**User Story:** 作为审计助理，我需要在精美 HTML 结构化视图和 Word 原始编辑之间自由切换，以便根据工作需要选择合适的编辑方式。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 在组件顶部提供 el-segmented 模式切换控件（「结构化视图」/「Word 编辑」）
2. WHEN 用户点击「结构化视图」选项, THE Disclosure_Checklist SHALL 切换到 HTML 结构化渲染模式
3. WHEN 用户点击「Word 编辑」选项, THE Disclosure_Checklist SHALL 切换到 OnlyOffice DOCX 编辑模式
4. THE Disclosure_Checklist SHALL 默认选中「结构化视图」模式
5. WHILE 模式切换进行中, THE Disclosure_Checklist SHALL 显示 loading 状态防止重复操作
6. WHEN 用户从 Word 编辑模式切换回结构化视图, THE Disclosure_Checklist SHALL 重新请求后端获取最新解析数据

### Requirement 3: Word 编辑模式

**User Story:** 作为审计助理，我需要直接在浏览器中编辑 A1-15 原始 Word 文档，以便保留完整格式进行自由编辑。

#### Acceptance Criteria

1. WHEN 用户选择 Word 编辑模式, THE Disclosure_Checklist SHALL 加载 GtOnlyOfficeSheet 渲染 A1-15 底稿的 DOCX 文件
2. THE GtOnlyOfficeSheet SHALL 使用 sheet-name="A1-15" 和 whole-workbook=true 参数
3. IF GtOnlyOfficeSheet 降级（健康检查失败）, THEN THE Disclosure_Checklist SHALL 显示降级提示且禁用 Word 编辑模式入口

### Requirement 4: 章节导航

**User Story:** 作为审计助理，我需要快速定位到目标章节，因为核对表有 35 个章节和 500+ 条目，逐页翻找效率很低。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 在 HTML 模式下提供左侧固定章节导航面板（Section_Nav）
2. THE Section_Nav SHALL 显示全部 35 个章节标题，按 TOC 顺序排列
3. WHEN 用户点击 Section_Nav 中的某个章节, THE Disclosure_Checklist SHALL 滚动到对应章节内容区域
4. THE Section_Nav SHALL 为每个章节显示完成进度（已填/总 actionable 数）
5. THE Section_Nav SHALL 高亮当前可视区域所在的章节
6. THE Section_Nav SHALL 支持 TOC_Applicability 标记，标记为不适用的章节显示为灰色禁用态
7. WHEN 用户标记某章节为不适用, THE Section_Nav SHALL 将该章节所有 actionable 条目自动置为 NA

### Requirement 5: 精美 HTML 结构化渲染

**User Story:** 作为审计助理，我需要以精美的卡片式 UI 查看和操作核对表内容，以便高效、清晰地逐项填写结论和备注。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 为每个 Actionable_Item 渲染为独立的核查卡片
2. THE 核查卡片 SHALL 显示：CAS_Ref 准则索引号（左上角标签）、核查内容描述、Y/N/NA 三选一结论按钮、备注输入框
3. THE 核查卡片 SHALL 根据结论状态显示不同视觉风格：Y=绿色左边框、N=红色左边框、NA=灰色半透明、未填=白底无边框
4. THE Disclosure_Checklist SHALL 为 Guidance_Child 子项提供折叠展开交互，默认折叠
5. WHEN 用户展开 guidance 子项, THE Disclosure_Checklist SHALL 显示详细披露要求文本（只读）
6. THE Disclosure_Checklist SHALL 为 header 类型条目渲染为章节内小节分隔标题
7. THE Disclosure_Checklist SHALL 在章节顶部显示该章节的进度统计条（Y/N/NA/未填各数量 + 完成百分比进度条）

### Requirement 6: 科目跳转联动

**User Story:** 作为审计助理，我需要从核对表的科目条目直接跳转到对应的循环底稿，以便快速交叉验证披露完整性。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 为每个 actionable 条目提供 Ref_Index_Chip 关联底稿输入区域
2. THE Ref_Index_Chip SHALL 渲染为 GtIndexChip 组件，支持点击跳转到对应循环底稿
3. THE Disclosure_Checklist SHALL 预置 Cross_Reference_Map（科目章节→建议关联底稿编码），在用户未手动填写时显示为建议 chip（虚线边框）
4. WHEN 用户点击建议 chip, THE Disclosure_Checklist SHALL 将该建议值确认为正式关联并保存
5. THE Disclosure_Checklist SHALL 支持用户手动输入/修改关联底稿索引号（el-autocomplete 联想已有 wp_code）
6. THE Cross_Reference_Map SHALL 至少覆盖以下映射：应收账款→D2、应收票据→D1、存货→E1、固定资产→G1、无形资产→H1、货币资金→D0、长期股权投资→I1、应付账款→F1、应付职工薪酬→F2、收入→K1

### Requirement 7: 自动保存与数据持久化

**User Story:** 作为审计助理，我填写的 Y/N/NA 结论、备注和关联索引号需要自动保存，避免手动保存操作和数据丢失。

#### Acceptance Criteria

1. WHEN 用户修改任何条目的结论/备注/关联索引, THE Disclosure_Checklist SHALL 在 2 秒 debounce 后自动保存到 Field_Overrides
2. THE Disclosure_Checklist SHALL 通过 `POST /api/workpapers/field-overrides` 保存用户填写数据，scope 为 `a115_disclosure:{wp_id}`
3. THE Disclosure_Checklist SHALL 在保存成功后显示"已保存"状态指示（右上角小文字）
4. IF 保存失败, THEN THE Disclosure_Checklist SHALL 重试最多 3 次，失败后显示 warning 提示
5. WHEN Disclosure_Checklist 加载时, THE 组件 SHALL 从 Field_Overrides 恢复所有已保存的用户填写数据
6. THE Disclosure_Checklist SHALL 保存 TOC_Applicability 章节适用性标记到 Field_Overrides

### Requirement 8: 全局进度与搜索

**User Story:** 作为审计助理，我需要快速了解整体填写进度，以及在 500+ 条目中搜索特定内容。

#### Acceptance Criteria

1. THE Disclosure_Checklist SHALL 在顶部显示全局进度统计：已填写数/总 actionable 数 + 完成百分比环形进度
2. THE Disclosure_Checklist SHALL 按结论类别显示统计：Y 数量（绿）、N 数量（红）、NA 数量（灰）、未填数量
3. THE Disclosure_Checklist SHALL 提供全局搜索功能，支持按关键词筛选条目内容
4. WHEN 用户输入搜索关键词, THE Disclosure_Checklist SHALL 高亮匹配的条目并隐藏不匹配的条目
5. THE Disclosure_Checklist SHALL 支持按结论状态筛选（全部/已填/未填/Y/N/NA）

### Requirement 9: 后端专属渲染策略

**User Story:** 作为系统，render-config API 需要为 `a1-15-disclosure-checklist` componentType 返回专属结构的数据。

#### Acceptance Criteria

1. WHEN render-config API 被请求且 componentType 为 `a1-15-disclosure-checklist`, THE 后端 SHALL 调用现有 `_parse_a1_15` 解析器获取模板数据
2. THE 后端 SHALL 从 Field_Overrides 查询用户已保存的 responses 数据（scope=`a115_disclosure:{wp_id}`）
3. THE 后端 SHALL 返回 `{template: {...}, responses: {...}, cross_reference_map: {...}}` 结构
4. THE template 字段 SHALL 包含：wp_code、title、sections（含 items）、toc、stats
5. THE responses 字段 SHALL 包含：items（每个 item_id 对应 conclusion/remark/wp_ref）、toc_applicability（章节适用性）
6. THE cross_reference_map 字段 SHALL 包含科目章节到建议关联底稿的预定义映射

### Requirement 10: 后端 DOCX 解析——Pretty Print 与 Round-Trip

**User Story:** 作为系统，我需要确保 A1-15 解析结果的数据完整性可验证。

#### Acceptance Criteria

1. THE 后端 SHALL 提供 `format_a115_to_summary` 方法将解析结果格式化为可读文本摘要
2. FOR ALL 合法的 A1-15 解析输出, 解析然后格式化然后再验证 SHALL 保留所有章节标题和条目数量（round-trip property）
3. THE 解析器 SHALL 保留 DOCX 中的原始 CAS_Ref 准则索引号文本（不截断不修改）
4. THE 解析器 SHALL 保留 actionable 条目的完整描述文本（含换行和特殊字符）

### Requirement 11: render-config 自加载支持

**User Story:** 作为 A1 Dashboard 内嵌子组件，A1-15 需要支持仅传入 wpId 即可自行加载数据。

#### Acceptance Criteria

1. WHEN Disclosure_Checklist 仅接收 wpId prop（无 htmlData prop）, THE 组件 SHALL 自行调用 `GET /api/workpapers/{wpId}/render-config?force_component_type=a1-15-disclosure-checklist` 获取数据
2. WHILE 数据加载中, THE Disclosure_Checklist SHALL 显示骨架屏占位
3. IF render-config 请求失败, THEN THE Disclosure_Checklist SHALL 显示错误提示并提供重试按钮
4. THE GtA1Dashboard SHALL 仅传递 wpId 和 readonly 给 Disclosure_Checklist（不传 htmlData）
