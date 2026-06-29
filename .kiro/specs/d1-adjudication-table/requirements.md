# Requirements Document

## Introduction

D1 应收票据底稿的核心数据枢纽组件——审定表D1-1 + 原值明细(按类别)D1-2 + 原值明细(按客户)D1-3 + 坏账准备明细表D1-4。这4个sheet承载D1底稿所有其他Tab的数据来源和回写目标。本spec将这4个sheet从现有 `useD1NotesReceivable.ts`（1237行）中拆出为独立子组件+子composable，每文件200-400行，全部做HTML精美组件（el-table + 金额格式化 + 动态行），OnlyOffice仅作为降级模式。

## Glossary

- **Adjudication_Table**: 审定表D1-1，汇总应收票据原值、坏账准备、净值的审定数据
- **Detail_Category_Table**: 原值明细表（按类别）D1-2，按票据种类分类汇总
- **Detail_Customer_Table**: 原值明细表（按客户）D1-3，按客户维度明细
- **Bad_Debt_Table**: 坏账准备明细表D1-4，按单项/组合分类的坏账准备变动
- **Cross_Sheet_Engine**: 跨sheet公式引擎，自动从D1-2/D1-4取数填入D1-1
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行（对应D1-2票据种类行、D1-3客户行）
- **Summary_Row**: 小计行，自动SUM对应明细行的汇总行（不可编辑）
- **AJE**: 审计调整分录（Audit Journal Entry）
- **RJE**: 重分类调整分录（Reclassification Journal Entry）
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（audited_amount字段）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **Formula_Engine**: 前端公式引擎，在composable中实现行内公式自动计算

## Requirements

### Requirement 1: 审定表D1-1 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑审定表D1-1, so that 我能清晰地看到应收票据原值、坏账准备和净值的审定过程。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为3区块固定结构：一、应收票据原值（银行承兑汇票/商业承兑汇票/小计）→ 二、坏账准备（银行承兑汇票/商业承兑汇票/小计）→ 三、应收票据净值（银行承兑汇票/商业承兑汇票/小计）
2. THE Adjudication_Table SHALL 显示以下列：项目 | 期初未审数 | 期初AJE | 期初RJE | 期初审定数 | 期末未审数 | 期末AJE | 期末RJE | 期末审定数 | 增减变动额 | 增减比例 | 原因分析
3. WHEN 用户编辑期末未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算期末审定数（=未审+AJE+RJE，3参数净额，对应源模板E=B+C+D）
4. WHEN 期初审定数和期末审定数均存在时, THE Formula_Engine SHALL 自动计算增减变动额（=期末审定-期初审定）和增减比例（=(期末-期初)/期初）
5. THE Adjudication_Table SHALL 自动计算小计行（=SUM对应区块明细行），小计行不可手动编辑
6. THE Adjudication_Table SHALL 自动计算净值行（=原值行 - 坏账准备行）
7. WHEN 增减比例绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
8. THE Adjudication_Table SHALL 在表尾显示试算平衡表数行（手填）和差异行（=审定数-试算表数），差异不为零时红色高亮

### Requirement 2: 审定表D1-1 跨Sheet取数

**User Story:** As a 审计助理, I want to 审定表自动从明细表和坏账表取数, so that 我不需要手动在表间复制数据，降低出错风险。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Detail_Category_Table 自动获取银行承兑汇票和商业承兑汇票的期初/期末未审数填入 Adjudication_Table 对应行
2. THE Cross_Sheet_Engine SHALL 从 Bad_Debt_Table 自动获取坏账准备合计的期初/期末数填入 Adjudication_Table 坏账准备区块
3. WHEN Detail_Category_Table 或 Bad_Debt_Table 数据变更时, THE Cross_Sheet_Engine SHALL 在2秒内刷新 Adjudication_Table 中的引用值
4. WHILE 跨sheet引用值生效时, THE Adjudication_Table SHALL 以浅蓝色背景标记自动取数单元格，并在tooltip显示数据来源（如"取自D1-2 银行承兑汇票小计行"）
5. IF 跨sheet数据加载失败, THEN THE Cross_Sheet_Engine SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 3: 审定表D1-1 联动与回写

**User Story:** As a 审计助理, I want to 审定表与调整分录、试算表自动联动, so that 数据在各表间保持一致性。

#### Acceptance Criteria

1. WHEN EventBus发布'adjustment:created'事件时, THE Adjudication_Table SHALL 自动将对应AJE/RJE金额同步到审定表相应行的AJE/RJE列
2. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用 writebackTrialBalance 将最新审定数回写 trial_balance.audited_amount
3. THE Adjudication_Table SHALL 在审定数回写成功后通过EventBus发布'substantive:adjudicated'事件（payload含wpCode/accountCode/auditedAmount）
4. THE Adjudication_Table SHALL 在底部显示"1.审计说明"区域，包含：
   - (1) 自动生成的变动百分比句子（"公司应收票据期末净值较期初净值增加/减少：xx%"）
   - "主要原因（比例超过30%的）：" 红色提示标签 + textarea（手填/AI生成）
   - (2) 质押、贴现情况说明 textarea（手填/AI生成）
5. THE Adjudication_Table SHALL 在审计说明区域的每个 textarea 旁显示🤖AI生成按钮，点击调用 AI 生成审计说明文本（基于当前数据变动情况）
6. THE Adjudication_Table SHALL 在底部显示"2.审计结论"区域（textarea + AI生成按钮）
7. THE Adjudication_Table SHALL 通过 `useReviewDialogProvider`（inject）集成通用复核对话能力：
   - 在"1.审计说明"和"2.审计结论"区域各放置一个固定入口按钮（💬图标），点击调用 `openReviewDialog({ sectionId: 'D1-adj-audit-note', sectionLabel: 'D1-1 审计说明', relatedData: {...} })`
   - 表格单元格支持右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId 自动生成为 `D1-adj-{rowKey}-{field}`）
   - 有活跃对话线程的位置显示蓝/红圆点标记（从 `/api/review-threads/active?wp_id=` 获取）

### Requirement 4: 原值明细表(按类别)D1-2 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中管理按类别分类的票据明细, so that 我能按银行承兑/商业承兑分类记录票据原值变动。

#### Acceptance Criteria

1. THE Detail_Category_Table SHALL 显示以下列：票据种类 | 期初未审数 | 期初AJE | 期初RJE | 期初审定数 | 本期增加 | 本期减少 | 期末未审数 | 期末AJE | 期末RJE | 期末审定数
2. THE Detail_Category_Table SHALL 预设"银行承兑汇票"和"商业承兑汇票"两个固定种类行
3. WHEN 用户点击"添加种类"按钮时, THE Detail_Category_Table SHALL 在小计行上方新增一个可编辑的空行
4. WHEN 用户点击动态行的删除按钮时, THE Detail_Category_Table SHALL 移除该行并重新计算小计
5. THE Formula_Engine SHALL 自动计算每行的期初审定数（=期初未审+AJE+RJE）和期末审定数（=期末未审+AJE+RJE）
6. THE Detail_Category_Table SHALL 在底部显示小计行（=SUM所有明细行各列），小计行不可编辑
7. THE Detail_Category_Table SHALL 对所有金额列应用金额格式化（千分位分隔、负数红色括号显示）

### Requirement 5: 原值明细表(按客户)D1-3 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中管理按客户分类的票据明细, so that 我能追踪每个客户的应收票据余额和变动。

#### Acceptance Criteria

1. THE Detail_Customer_Table SHALL 显示以下列：客户名称 | 公司代码 | 关联关系 | 期初未审数 | 期初AJE | 期初RJE | 期初审定数 | 本期增加 | 本期减少 | 期末余额 | 重分类 | 期末未审数 | 期末AJE | 期末RJE | 期末审定数
2. WHEN 用户点击"添加客户"按钮时, THE Detail_Customer_Table SHALL 在小计行上方新增一个可编辑的空行
3. WHEN 用户输入客户名称时, THE Detail_Customer_Table SHALL 自动匹配 related_parties 表中的关联方信息并填充"关联关系"列
4. WHEN 关联关系列为"关联方"时, THE Detail_Customer_Table SHALL 以橙色背景高亮该行
5. THE Formula_Engine SHALL 自动计算每行的期初审定数（=期初未审+AJE+RJE）和期末审定数（=期末未审+AJE+RJE）
6. THE Detail_Customer_Table SHALL 在底部显示小计行（=SUM所有明细行各金额列）
7. THE Detail_Customer_Table SHALL 支持按客户名称模糊搜索筛选行（搜索框在表头上方）
8. WHEN 动态行超过20行时, THE Detail_Customer_Table SHALL 启用虚拟滚动（visible area + buffer）以保证渲染性能

### Requirement 6: 坏账准备明细表D1-4 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑坏账准备明细, so that 我能清晰地追踪坏账准备的计提、转回和核销变动。

#### Acceptance Criteria

1. THE Bad_Debt_Table SHALL 显示以下列：项目 | 期初未审数 | 期初AJE | 期初RJE | 期初审定数 | 本期计提 | 本期收回 | 本期转回 | 本期核销 | 本期其他 | 期末未审数 | 期末AJE | 期末RJE | 期末审定数
2. THE Bad_Debt_Table SHALL 预设固定行结构：按单项计提（可展开子行）+ 按组合计提（可展开子行）+ 小计
3. THE Formula_Engine SHALL 自动计算每行的期初审定数（=期初未审+AJE+RJE）和期末审定数（=期末未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动计算期末未审数（=期初审定+本期计提-本期收回-本期转回-本期核销+本期其他）
5. THE Bad_Debt_Table SHALL 在底部显示小计行（=SUM按单项行+按组合行），小计行不可编辑
6. WHEN 坏账准备合计数与ECL测试Tab(D1-ecl)结果不一致时, THE Bad_Debt_Table SHALL 在小计行旁显示黄色警告提示"与ECL测试差异: ±xxx元"

### Requirement 7: 双模式切换

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个sheet的Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件），OO模式下用户仍可查看跨sheet公式计算结果

### Requirement 8: 持久化与数据存储

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-adj-"
2. THE Detail_Category_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-cat-"
3. THE Detail_Customer_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-cust-"
4. THE Bad_Debt_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-bd-"
5. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
6. WHEN 用户切换结论/选择类字段时, THE Formula_Engine SHALL 立即保存该字段
7. THE Detail_Customer_Table SHALL 将动态行数据以JSON数组格式存储于单个remark字段（item_id="D1-cust-rows"），每行含所有列值

### Requirement 9: 导入导出三级

**User Story:** As a 审计助理, I want to 支持从Excel导入数据和导出模板, so that 我能利用已有的离线填写的数据批量录入。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Import_Export_Three_Level SHALL 生成当前sheet对应的空白xlsx模板（含表头+格式+公式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Import_Export_Three_Level SHALL 生成包含当前数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Import_Export_Three_Level SHALL 使用openpyxl解析文件内容，识别动态行数量，并将数据回写到checklist_responses
4. IF 导入的xlsx格式不符合模板结构, THEN THE Import_Export_Three_Level SHALL 显示错误提示并列出不匹配的列名
5. WHEN 导入D1-3（按客户）xlsx且行数超过模板预设行时, THE Import_Export_Three_Level SHALL 自动扩展动态行以容纳全部数据
6. THE Import_Export_Three_Level SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）

### Requirement 10: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将审定表相关逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 拆分为独立Vue子组件 D1TabAdjudication.vue（200-400行）
2. THE Detail_Category_Table SHALL 拆分为独立Vue子组件 D1TabDetailCategory.vue（200-400行）
3. THE Detail_Customer_Table SHALL 拆分为独立Vue子组件 D1TabDetailCustomer.vue（200-400行）
4. THE Bad_Debt_Table SHALL 拆分为独立Vue子组件 D1TabBadDebt.vue（200-400行）
5. THE Cross_Sheet_Engine SHALL 拆分为独立composable useD1Adjudication.ts（200-400行），包含跨sheet取数+公式引擎+EventBus联动逻辑
6. THE Detail_Category_Table SHALL 有独立composable useD1DetailCategory.ts，包含动态行CRUD+公式计算
7. THE Detail_Customer_Table SHALL 有独立composable useD1DetailCustomer.ts，包含动态行CRUD+关联方匹配+搜索筛选
8. THE Bad_Debt_Table SHALL 有独立composable useD1BadDebt.ts，包含固定行结构+变动公式计算

### Requirement 11: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Adjudication_Table SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Detail_Customer_Table SHALL 对"客户名称"列左对齐、对金额列右对齐
6. WHILE 数据正在加载时, THE Adjudication_Table SHALL 在表格区域显示el-skeleton占位动画
