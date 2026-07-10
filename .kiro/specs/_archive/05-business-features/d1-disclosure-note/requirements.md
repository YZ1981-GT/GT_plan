# Requirements Document

## Introduction

D1 应收票据底稿的附注披露组专属组件——覆盖"附注披露信息（上市公司）"和"附注披露信息（国企）"两个sheet。从现有 `useD1NotesReceivable.ts`（1237行）中拆出附注披露相关逻辑为独立子组件+子composable。共用一个 composable `useD1Disclosure.ts`（~300行）通过 variant='listed'|'soe' 区分上市/国企版本；共用一个 Vue 组件 `D1TabDisclosure.vue`（~350行）根据 variant 动态显示/隐藏子节。全部做 HTML 精美组件（el-table + 金额格式化 + 动态行），OnlyOffice 仅作降级模式。

## Glossary

- **Disclosure_Component**: 附注披露组件，渲染上市公司或国企版本的应收票据附注披露信息
- **Listed_Variant**: 上市公司版本（variant='listed'），6个标准子节，119行14列
- **SOE_Variant**: 国企版本（variant='soe'），7个标准子节，89行16列
- **Pledged_Section**: 质押票据子节，期末已质押的应收票据（种类+质押金额，可添加行，SUM合计）
- **Endorsed_Section**: 背书贴现子节，期末已背书或贴现未到期票据（终止/未终止确认金额）+ CAS23判断提示
- **Transfer_Section**: 转应收账款子节，期末因出票人未履约而转为应收账款的票据
- **Bad_Debt_Classification_Section**: 坏账分类子节，按坏账计提方法分类（期末/上年 × 单项/组合 × 明细）
- **Bad_Debt_Movement_Section**: 坏账变动子节，本期坏账准备变动（期初→计提→转回→核销→其他→期末）+ 重要转回明细
- **Write_Off_Section**: 核销子节，本期实际核销的应收票据 + 重要核销明细
- **Category_Summary_Section**: 票据分类子节（国企专有），银行承兑/商业承兑汇总（从审定表D1-1自动取数）
- **Cross_Sheet_Ref**: 跨sheet引用，从审定表D1-1的allResponses Map中读取银行承兑/商业承兑期末/期初余额+坏账准备
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Formula_Engine**: 前端公式引擎，实现比例=IFERROR(x/y,0)、损失率=坏账/余额、账面=余额-坏账、期末=期初+变动 等计算
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑

## Requirements

### Requirement 1: 附注披露组件统一入口与变体切换

**User Story:** As a 审计助理, I want to 通过同一个组件查看上市公司或国企版本的附注披露信息, so that 我能根据被审计单位类型正确编制附注底稿。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 接受 variant='listed'|'soe' 属性，动态显示对应版本的子节结构
2. WHEN variant='listed' 时, THE Disclosure_Component SHALL 按顺序显示6个子节：质押→背书贴现→转应收账款→坏账分类→坏账变动→核销
3. WHEN variant='soe' 时, THE Disclosure_Component SHALL 按顺序显示7个子节：票据分类→坏账分类→坏账变动→质押→背书贴现→转应收账款→核销
4. THE Disclosure_Component SHALL 将每个子节渲染为独立的 el-card 折叠卡片（可展开/收起）
5. THE Disclosure_Component SHALL 默认展开所有子节卡片
6. THE Disclosure_Component SHALL 在组件顶部显示当前变体标识（"上市公司版" 或 "国企版"）

### Requirement 2: 质押票据子节（上市+国企共用）

**User Story:** As a 审计助理, I want to 记录期末已质押的应收票据信息, so that 我能在附注中披露质押相关数据。

#### Acceptance Criteria

1. THE Pledged_Section SHALL 渲染 el-table 包含以下列：票据种类 | 期末已质押金额
2. THE Pledged_Section SHALL 预设"银行承兑汇票"和"商业承兑汇票"两个固定行（不可删除，行类型=fixed）
3. THE Pledged_Section SHALL 在固定行下方显示浮动行区域（行类型=dynamic，用户可无限添加）
4. WHEN 用户点击"添加行"按钮时, THE Pledged_Section SHALL 在合计行上方新增一个可编辑的空行（浮动行）
5. WHEN 用户点击浮动行的删除按钮时, THE Pledged_Section SHALL 移除该行并重新计算合计（固定行不显示删除按钮）
6. THE Formula_Engine SHALL 自动计算合计行（= SUM 所有固定行+浮动行的期末质押金额列）
7. THE Pledged_Section SHALL 对金额列应用 displayPrefs.fmtAmount 格式化

### Requirement 3: 背书贴现子节（上市+国企共用）

**User Story:** As a 审计助理, I want to 记录期末已背书或贴现且未到期的应收票据, so that 我能在附注中披露终止确认和未终止确认金额。

#### Acceptance Criteria

1. THE Endorsed_Section SHALL 渲染 el-table 包含以下列：票据种类 | 期末终止确认金额 | 期末未终止确认金额
2. THE Endorsed_Section SHALL 预设"银行承兑汇票"和"商业承兑汇票"两个固定行（不可删除）
3. THE Endorsed_Section SHALL 在固定行下方显示浮动行区域（用户可添加）
4. WHEN 用户点击"添加行"按钮时, THE Endorsed_Section SHALL 在合计行上方新增一个可编辑的浮动行
5. THE Formula_Engine SHALL 自动计算合计行（= SUM 所有固定行+浮动行各列）
6. THE Endorsed_Section SHALL 在表格下方显示"终止确认判断说明"文本区：
   - 首先显示 CAS23 准则引用句（"如根据《企业会计准则第23号——金融资产转移》终止确认的应收票据..."），此句为只读参考
   - 然后显示适用性判断区域：el-radio-group 选择（"终止确认" / "未终止确认" / "两者均有"）
   - 根据用户选择，自动预填对应模板文本（可编辑textarea）：
     - 选"终止确认"→ 预填"用于贴现的银行承兑汇票是由信用等级较高的银行承兑，信用风险和延期付款风险很小..."
     - 选"未终止确认"→ 预填"用于贴现的银行承兑汇票是由信用等级不高的银行承兑，贴现不影响追索权..."
     - 选"两者均有"→ 两段文本均展示，用户可分别编辑
   - textarea 支持🤖AI生成 + 💬复核对话 + 双向回写到附注模块
7. THE Endorsed_Section SHALL 在说明文本区下方以 `<details>` 折叠显示编制提示（蓝色左边线+浅蓝背景，默认收起）：
   - 证监会监管报告提示（绿色文字）
   - 终止确认判断参考依据（红色文字：信用等级高→终止/不高→未终止的判断标准）
8. THE Endorsed_Section SHALL 对金额列应用 displayPrefs.fmtAmount 格式化

### Requirement 4: 转应收账款子节（上市+国企共用）

**User Story:** As a 审计助理, I want to 记录期末因出票人未履约而转为应收账款的票据, so that 我能在附注中披露转入应收账款的金额。

#### Acceptance Criteria

1. THE Transfer_Section SHALL 渲染 el-table 包含以下列：票据种类 | 转应收账款金额
2. THE Transfer_Section SHALL 预设"银行承兑汇票"和"商业承兑汇票"两个固定行
3. THE Formula_Engine SHALL 自动计算合计行（= SUM 所有明细行）
4. THE Transfer_Section SHALL 对金额列应用 displayPrefs.fmtAmount 格式化

### Requirement 5: 坏账分类子节 — 期末/上年分类表

**User Story:** As a 审计助理, I want to 按坏账计提方法对应收票据进行分类披露, so that 我能在附注中展示单项计提和组合计提的分布情况。

#### Acceptance Criteria

1. THE Bad_Debt_Classification_Section SHALL 渲染期末分类表，包含以下列：类别 | 账面余额 | 比例(%) | 坏账准备 | 预期信用损失率(%) | 账面价值
2. THE Bad_Debt_Classification_Section SHALL 渲染上年同期分类表（同期末结构）
3. THE Bad_Debt_Classification_Section SHALL 预设行结构：按单项计提（可展开子行）+ 按组合计提（银行承兑汇票/商业承兑汇票子行）+ 合计
4. THE Formula_Engine SHALL 自动计算比例列（= IFERROR(本行余额 / 合计行余额, 0)）
5. THE Formula_Engine SHALL 自动计算预期信用损失率列（= IFERROR(坏账准备 / 账面余额, 0)）
6. THE Formula_Engine SHALL 自动计算账面价值列（= 账面余额 - 坏账准备）
7. THE Formula_Engine SHALL 自动计算合计行（= SUM 所有明细行各数值列）
8. WHEN variant='soe' 时, THE Bad_Debt_Classification_Section SHALL 将期末和期初分为两个独立子表渲染（R13-18 期末 + R20-25 期初）

### Requirement 6: 坏账分类子节 — 按单项明细表

**User Story:** As a 审计助理, I want to 记录按单项计提坏账准备的票据明细, so that 我能披露单项重大计提的依据和金额。

#### Acceptance Criteria

1. THE Bad_Debt_Classification_Section SHALL 渲染按单项明细表（期末+上年），包含以下列：名称 | 账面余额 | 坏账准备 | 预期信用损失率(%) | 计提依据
2. THE Formula_Engine SHALL 自动计算预期信用损失率列（= IFERROR(坏账准备 / 账面余额, 0)）
3. WHEN 用户点击"添加行"按钮时, THE Bad_Debt_Classification_Section SHALL 在合计行上方新增一个可编辑的空行
4. THE Bad_Debt_Classification_Section SHALL 分别显示期末明细和上年明细（两个独立子表）
5. THE Bad_Debt_Classification_Section SHALL 对金额列应用 displayPrefs.fmtAmount 格式化

### Requirement 7: 坏账分类子节 — 按组合明细表

**User Story:** As a 审计助理, I want to 记录按组合计提坏账准备的明细, so that 我能披露银行承兑和商业承兑各组合的坏账计提情况。

#### Acceptance Criteria

1. THE Bad_Debt_Classification_Section SHALL 渲染银行承兑按组合明细表（期末+上年），包含以下列：出票人类型或账龄 | 应收票据余额 | 坏账准备 | 预期信用损失率(%)
2. THE Bad_Debt_Classification_Section SHALL 渲染商业承兑按组合明细表（期末+上年），结构同银行承兑
3. THE Formula_Engine SHALL 自动计算预期信用损失率列（= IFERROR(坏账准备 / 余额, 0)）
4. WHEN 用户点击"添加行"按钮时, THE Bad_Debt_Classification_Section SHALL 在合计行上方新增一个可编辑的空行
5. THE Bad_Debt_Classification_Section SHALL 在最底部显示坏账分类提示文字（不可编辑文本区域）

### Requirement 8: 坏账变动子节

**User Story:** As a 审计助理, I want to 记录本期坏账准备的变动过程, so that 我能在附注中展示坏账准备从期初到期末的完整变动。

#### Acceptance Criteria

1. THE Bad_Debt_Movement_Section SHALL 渲染坏账变动表，包含以下列：项目 | 上年末余额 | 本期计提 | 本期转回 | 本期核销 | 本期转销 | 其他变动 | 期末余额
2. THE Formula_Engine SHALL 自动计算期末余额（= 上年末 + 计提 - 转回 - 核销 - 转销 + 其他）
3. WHEN variant='listed' 时, THE Bad_Debt_Movement_Section SHALL 只显示总数一行
4. WHEN variant='soe' 时, THE Bad_Debt_Movement_Section SHALL 按"单项计提"和"组合计提"分行显示，并有合计行
5. THE Bad_Debt_Movement_Section SHALL 在变动表下方渲染"重要转回明细"子表（单位名称 | 转回原因 | 原确认方式 | 转回依据 | 转回金额）
6. WHEN 用户点击"添加行"按钮时, THE Bad_Debt_Movement_Section SHALL 在重要转回明细表的合计行上方新增一个可编辑的空行
7. THE Formula_Engine SHALL 对重要转回明细表自动计算合计行

### Requirement 9: 核销子节

**User Story:** As a 审计助理, I want to 记录本期实际核销的应收票据信息, so that 我能在附注中披露核销金额和重要核销明细。

#### Acceptance Criteria

1. THE Write_Off_Section SHALL 渲染核销汇总表（核销总金额单行）
2. THE Write_Off_Section SHALL 在汇总表下方渲染"重要核销明细"子表（单位名称 | 票据性质 | 核销金额 | 核销原因 | 履行程序情况）
3. WHEN 用户点击"添加行"按钮时, THE Write_Off_Section SHALL 在重要核销明细表的合计行上方新增一个可编辑的空行
4. THE Formula_Engine SHALL 对重要核销明细表自动计算金额列合计行
5. THE Write_Off_Section SHALL 对金额列应用 displayPrefs.fmtAmount 格式化

### Requirement 10: 票据分类子节（国企专有）

**User Story:** As a 审计助理, I want to 查看国企版本的票据分类汇总信息, so that 我能看到银行承兑和商业承兑汇票的期末/期初余额和坏账准备。

#### Acceptance Criteria

1. WHEN variant='soe' 时, THE Category_Summary_Section SHALL 渲染票据分类表，包含以下列：票据种类 | 期末余额 | 期末坏账准备 | 期末账面价值 | 期初余额 | 期初坏账准备 | 期初账面价值
2. THE Cross_Sheet_Ref SHALL 从 allResponses Map 中的审定表D1-1数据自动获取银行承兑/商业承兑的期末/期初余额和坏账准备
3. THE Formula_Engine SHALL 自动计算账面价值列（= 余额 - 坏账准备）
4. THE Formula_Engine SHALL 自动计算合计行（= SUM 银行承兑 + 商业承兑）
5. THE Category_Summary_Section SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示"取自审定表D1-1"
6. WHEN variant='listed' 时, THE Category_Summary_Section SHALL 不显示此子节（上市版通过顶部表R9-11自动取数，不作为独立子节）

### Requirement 11: 跨Sheet自动取数（顶部引用）

**User Story:** As a 审计助理, I want to 附注披露自动从审定表引用关键数据, so that 我不需要手动在表间复制数据。

#### Acceptance Criteria

1. WHEN variant='listed' 时, THE Cross_Sheet_Ref SHALL 在组件顶部显示自动取数区域（银行承兑/商业承兑的期末/期初余额+坏账准备），数据来自审定表D1-1
2. THE Cross_Sheet_Ref SHALL 从同一个 allResponses Map 中读取 D1-adj- 前缀的数据（纯 computed 响应式，不走 API）
3. WHEN 审定表D1-1数据变更时, THE Cross_Sheet_Ref SHALL 通过 computed 响应式自动刷新附注中的引用值
4. THE Cross_Sheet_Ref SHALL 以浅蓝色背景标记自动取数单元格，并在 tooltip 显示数据来源
5. IF 审定表D1-1数据未加载, THEN THE Cross_Sheet_Ref SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 12: 双模式切换

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在组件顶部显示 el-segmented 切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet，只显示当前变体对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载 checklist_responses 数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示 tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件）

### Requirement 13: 持久化与数据存储

**User Story:** As a 审计助理, I want to 所有附注编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-disc-listed-"（上市版）和"D1-disc-soe-"（国企版）
2. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Disclosure_Component SHALL 触发 debounce 自动保存
3. WHEN 用户切换选择类字段时, THE Disclosure_Component SHALL 立即保存该字段
4. THE Disclosure_Component SHALL 将各子节的动态行数据以 JSON 数组格式存储于对应 item_id 的 remark 字段
5. FOR ALL 有效的动态行JSON数组, THE Disclosure_Component SHALL 满足序列化后反序列化产生等价对象的 round-trip 性质

### Requirement 14: 导入导出三级

**User Story:** As a 审计助理, I want to 支持从Excel导入附注数据和导出模板, so that 我能利用已有的离线填写的数据批量录入。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Disclosure_Component SHALL 生成当前变体对应的空白xlsx模板（含表头+格式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Disclosure_Component SHALL 生成包含当前数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Disclosure_Component SHALL 解析文件内容并将数据回写到 checklist_responses
4. IF 导入的xlsx格式不符合模板结构, THEN THE Disclosure_Component SHALL 显示错误提示并列出不匹配的列名
5. THE Disclosure_Component SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）

### Requirement 15: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将附注披露逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 拆分为独立Vue子组件 D1TabDisclosure.vue（~350行）
2. THE Disclosure_Component SHALL 有独立composable useD1Disclosure.ts（~300行），通过 variant 区分上市/国企逻辑
3. THE useD1Disclosure composable SHALL 包含所有子节的数据模型、公式计算、动态行CRUD、跨sheet取数逻辑
4. THE Disclosure_Component SHALL 复用已有 useD1FormulaEngine.ts 中的纯函数（parseNum/calcSubtotal等）

### Requirement 16: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Disclosure_Component SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Disclosure_Component SHALL 显示"-"而非"0.00"
4. THE Disclosure_Component SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Disclosure_Component SHALL 对表格标题列左对齐、金额列右对齐
6. WHILE 数据正在加载时, THE Disclosure_Component SHALL 在表格区域显示 el-skeleton 占位动画

### Requirement 17: 提示文字展示规范

**User Story:** As a 审计助理, I want to 在编辑过程中看到源模板中的编制提示, so that 我能按照准则要求正确编制附注内容。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 将源模板中所有红色/绿色提示文字（如"【提示：..."、"可无限量添加行"、CAS准则引用等）以 `<details>` 折叠区域展示
2. THE Disclosure_Component SHALL 对提示文字使用蓝色左边线+浅蓝色背景样式，默认收起不干扰编辑
3. THE Disclosure_Component SHALL 在以下位置显示提示文字：
   - 顶部说明区（R12-13）：关于"云信"/"融信"等数字化应收账款债权的提示
   - 背书贴现子节下方（R27-30）：CAS23终止确认判断 + 证监会监管报告提示
   - 坏账分类子节下方（R90-91）：关于票据逾期转应收账款的提示
   - 核销子节下方（R118）：逐项披露要求提示
4. THE Disclosure_Component SHALL 在每个"可无限量添加行"位置显示浅灰色占位提示行（点击即可添加新行）
5. WHEN 用户点击折叠提示文字的标题时, THE Disclosure_Component SHALL 展开/收起该提示区域

### Requirement 17b: 说明文本区域与附注模块双向回写

**User Story:** As a 审计助理, I want to 在披露表的"说明"处编辑的内容自动同步到附注模块, so that 我不需要在两个地方重复输入同一段话。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 在每个子节的"说明："标签处渲染可编辑的 textarea（区别于不可编辑的【提示】折叠区）
2. THE "说明" textarea SHALL 支持手填文本和🤖AI生成按钮（基于上方表格数据 context 自动生成说明文字）
3. WHEN 用户在披露表"说明" textarea 中编辑内容并保存时, THE Disclosure_Component SHALL 通过 EventBus 发布 `disclosure:note-text-updated` 事件（payload含 wpCode/variant/sectionKey/content）
4. WHEN 附注模块对应科目节的说明段落发生变更时, THE Disclosure_Component SHALL 通过 EventBus 监听 `note:section-updated` 事件，自动更新本地 textarea 内容（双向同步）
5. THE "说明" textarea 的数据 SHALL 使用独立 item_id 存储（格式 `D1-disc-{variant}-note-{sectionKey}`），与附注模块通过 cross_wp_references 的 ref_id 关联
6. IF 披露表和附注模块的同一段文字存在冲突（两端同时编辑）, THEN THE Disclosure_Component SHALL 以最后保存时间为准，并在 tooltip 中显示"最近由{用户}在{时间}更新"
7. THE "说明" textarea SHALL 集成复核对话能力（inject openReviewDialog，固定💬入口按钮）

### Requirement 18: 附注模块联动与跳转

**User Story:** As a 审计助理, I want to 从附注披露跳转到相关底稿查看详细数据, so that 我能追溯数据来源并核对附注内容与底稿的一致性。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 在跨sheet自动取数区域（银行承兑/商业承兑余额+坏账）显示 GtIndexChip（跳转到审定表D1-1 Tab）
2. THE Disclosure_Component SHALL 在坏账分类子节显示 GtIndexChip（跳转到坏账准备D1-4 Tab）
3. THE Disclosure_Component SHALL 在坏账变动子节显示 GtIndexChip（跳转到坏账准备D1-4 Tab）
4. WHEN 项目已有附注编辑模块数据时, THE Disclosure_Component SHALL 在组件顶部显示"查看附注全文"按钮（GtIndexChip 跳转到附注模块对应科目节）
5. THE Disclosure_Component SHALL 通过 EventBus 发布 'disclosure:updated' 事件（payload 含 wpCode/variant/sections），供附注模块感知披露底稿变更
6. THE Disclosure_Component SHALL 对所有跨sheet取数单元格的 tooltip 中包含可点击的"跳转到来源"链接（emit 'jump-to-section' 切换到审定表 Tab）

### Requirement 19: 行类型规范与导入识别

**User Story:** As a 开发者, I want to 对每个表格的行类型有清晰定义, so that 导入时能正确识别固定行与浮动行的边界。

#### Acceptance Criteria

1. THE Disclosure_Component SHALL 对每个子节的表格行区分三种类型：
   - fixed: 固定行（银行承兑/商业承兑等预设行，不可删除，始终存在）
   - dynamic: 浮动行（用户动态添加的行，可删除，导入时自动扩展）
   - summary: 合计行（自动计算，不可编辑，始终位于最底部）
2. THE Disclosure_Component SHALL 在每个表格的 JSON 存储中标记每行的 rowType（'fixed'|'dynamic'|'summary'）
3. WHEN 导入 xlsx 时, THE Import_Engine SHALL 通过以下规则识别行类型：
   - 第一行/第二行若为"银行承兑汇票"/"商业承兑汇票"→ fixed
   - 最后一行若为"合计"/"合 计"/"小计" → summary
   - 其余行 → dynamic
4. WHEN 导入行数超过模板固定行数时, THE Import_Engine SHALL 自动创建浮动行以容纳全部数据
5. THE Disclosure_Component SHALL 在固定行左侧显示锁定图标（表示不可删除），浮动行左侧显示拖拽句柄+删除按钮


### Requirement 20: 从后续底稿自动提取数据（auto_pull联动）

**User Story:** As a 审计助理, I want to 附注披露表自动从D1-12质押检查表、D1-8贴现背书明细表、D1-16转回核销检查表提取数据, so that 我不需要手动在底稿间复制数据到附注表中。

#### Acceptance Criteria

1. THE Pledged_Section SHALL 提供"从D1-12提取"按钮，点击后自动从allResponses Map中读取D1-pledge-rows JSON数据，按票据类型分组聚合质押金额填入质押子节（对应cross_ref CW-C-D1-disclosure-003, auto_pull:true）
2. THE Endorsed_Section SHALL 提供"从D1-8提取"按钮，点击后自动从allResponses Map中读取D1-endorse-discount-rows和D1-endorse-transfer-rows JSON数据，按终止确认判断分组聚合填入背书贴现子节（对应cross_ref CW-C-D1-disclosure-004, auto_pull:true）
3. THE Bad_Debt_Movement_Section SHALL 提供"从D1-16提取"按钮，点击后自动从allResponses Map中读取D1-writeoff-reversal-total和D1-writeoff-writeoff-total数据，填入坏账变动表的"本期转回"和"本期核销"列
4. THE Write_Off_Section SHALL 提供"从D1-16提取"按钮，点击后自动从allResponses Map中读取D1-writeoff-writeoff-rows JSON数据，将核销明细行映射到附注核销子节的重要核销明细表
5. WHEN 用户点击任意"从XX提取"按钮时, THE Disclosure_Component SHALL 显示确认弹窗"将从{来源底稿}提取最新数据覆盖当前内容，是否继续？"
6. WHEN 提取完成后, THE Disclosure_Component SHALL 以浅蓝色背景标记自动填充的单元格 + tooltip显示数据来源底稿名
7. IF 来源底稿数据未填写(JSON为空或item_id不存在), THEN THE Disclosure_Component SHALL 在按钮旁显示黄色提示"来源底稿尚未填写数据"

### Requirement 20b: 附注分类表从D1-15 ECL测算自动取数

**User Story:** As a 审计助理, I want to 附注坏账分类子节自动从D1-15 ECL测算表提取各组合的损失率和坏账准备金额, so that 附注中的坏账分类数据与ECL测算保持一致。

#### Acceptance Criteria

1. THE Bad_Debt_Classification_Section SHALL 提供"从D1-15提取"按钮，点击后自动从allResponses Map中读取D1-ecl-portfolio-rows JSON数据
2. THE Bad_Debt_Classification_Section SHALL 将D1-15组合计提各行的(debtor→类别, balance→账面余额, lossRate→预期信用损失率, actualProvision→坏账准备)映射到坏账分类表的"按组合计提"区域
3. THE Bad_Debt_Classification_Section SHALL 将D1-15单项计提各行(D1-ecl-individual-rows)映射到坏账分类表的"按单项计提"区域
4. WHEN D1-15数据变更时, THE Disclosure_Component SHALL 在"从D1-15提取"按钮旁显示蓝色圆点标记"来源数据已更新"
