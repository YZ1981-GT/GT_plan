# Requirements Document: D5 应收款项融资底稿专属HTML精美组件

## Introduction

D5应收款项融资底稿的专属HTML精美组件构建。将现有 `d-form-table`/`univer` 通用渲染升级为独立专属组件 `d5-receivables-financing`，覆盖源模板7个有效sheet（程序表D5A + 审定表D5-1 + 明细表D5-2 + 调整分录D5-3 + 公允价值测算D5-4 + 附注上市 + 附注国企），合计145个公式。科目编码1124应收款项融资（借方科目/资产类，以公允价值计量且变动计入其他综合收益OCI）。核心特色：FVOCI金融资产公允价值测算（贴现公式：票面×利率×天数/360）、审定表"减：OCI公允价值变动"特殊结构、来源交叉（D1票据业务模式+D2应收账款业务模式→确定归入D5的资产）、公允价值层次判定（第二/第三层次）。结构简洁（7 sheet），不需要嵌套Tab。

## Glossary

- **Adjudication_Table**: 审定表D5-1，含OCI公允价值变动减项结构（52公式），行：应收票据/应收账款/小计/减：OCI公允价值变动/公允价值合计/试算平衡表数/差异数
- **Detail_Table**: 明细表D5-2，17列宽表（40公式），核心数据源，按类别×明细项目记录期初/本期变动/期末
- **Adjustment_Table**: 调整分录汇总表D5-3，10列标准格式（6公式）
- **FairValue_Table**: 公允价值测算表D5-4，13列（18公式），核心贴现公式：贴现利息=票面金额×市场贴现利率×剩余天数/360
- **Disclosure_Listed**: 附注披露信息（上市公司），含减值准备变动子节（21公式）
- **Disclosure_SOE**: 附注披露信息（国企），简化版（8公式）
- **Procedure_Table**: 实质性程序表D5A，7步审计程序+5项审计目标（复用a-program-console）
- **Cross_Sheet_Engine**: 跨sheet公式引擎，D5-2明细→D5-1聚合+D5-4测算→D5-1 OCI变动+D5-3→D5-1 AJE/RJE
- **Formula_Engine**: 前端公式引擎composable，含贴现公式（票面×利率×天数/360）+审定数=未审+AJE+RJE+公允价值合计=小计-OCI变动
- **Discount_Formula**: 贴现利息计算公式：贴现利息=票面金额×市场贴现利率×剩余天数÷360；公允价值=票面金额-贴现利息
- **FV_Hierarchy**: 公允价值层次判定：可观察输入值→第二层次；不可观察输入值→第三层次
- **OCI_Adjustment**: 其他综合收益-公允价值变动，审定表特殊减项（公允价值合计=票面小计-OCI变动）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/公允价值合理性评价等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1124，借方科目/资产类）

## Requirements

### Requirement 1: 组件架构与Tab设计

**User Story:** As a 开发者, I want to D5应收款项融资底稿按sheet拆分为独立Tab, so that 7个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE D5 组件 SHALL 注册新componentType: `d5-receivables-financing`，主入口为 GtD5ReceivablesFinancing.vue（el-tabs容器，6个tab-pane：程序表/审定表/明细表/调整分录/公允价值测算/附注披露）
2. THE D5 组件 SHALL 将每个sheet拆分为独立Vue子组件（D5TabProcedure.vue / D5TabAdjudication.vue / D5TabDetail.vue / D5TabAdjustment.vue / D5TabFairValue.vue / D5TabDisclosure.vue），每文件200-400行
3. THE D5 组件 SHALL 拆分为独立composable：useD5FormData.ts（基础数据加载/保存）+ useD5FormulaEngine.ts（纯函数公式引擎，含贴现公式）+ useD5CrossSheet.ts（跨sheet联动逻辑）
4. THE useD5FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：贴现利息=票面×利率×天数/360、公允价值=票面-贴现利息、审定数=未审+AJE+RJE、公允价值合计=小计-OCI变动、变动率计算、合计行SUM
5. THE D5 组件 SHALL 在htmlRendererRegistry中注册'd5-receivables-financing'→GtD5ReceivablesFinancing映射
6. THE D5 组件 SHALL 在wp_code_overrides.json中将D5/D5-1/D5-2/D5-3/D5-4的componentType统一映射为'd5-receivables-financing'
7. THE D5 组件 SHALL 在VALID_COMPONENT_TYPES中注册'd5-receivables-financing'
8. THE GtD5ReceivablesFinancing.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=d5-receivables-financing）

### Requirement 2: 审定表D5-1 HTML渲染（52公式，含OCI特殊结构）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑应收款项融资审定表, so that 我能清晰地看到票面小计与OCI公允价值变动的扣减关系和最终公允价值合计。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为固定行结构：应收票据 / 应收账款 / 小计 / 减：其他综合收益-公允价值变动 / 应收款项融资公允价值合计 / 试算平衡表数 / 差异数
2. THE Adjudication_Table SHALL 显示以下列：项目 | 期初数(未审/AJE/RJE/审定) | 期末数(未审/AJE/RJE/审定) | 期末与期初审定数比较(变动额/变动率)
3. WHEN 用户编辑未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动计算：小计=应收票据审定+应收账款审定；公允价值合计=小计-OCI公允价值变动；变动额=期末审定-期初审定；变动率=(期末-期初)/期初（期初=0时显示"N/A"）
5. THE Adjudication_Table SHALL 在"减：OCI公允价值变动"行以浅蓝色背景标记（提示来源于D5-4测算结果），tooltip显示"取自D5-4公允价值测算"
6. THE Adjudication_Table SHALL 在底部显示试算平衡表数行（自动从TB取数科目1124）和差异行（=公允价值合计-试算表数），差异不为零时红色高亮
7. WHEN 变动率绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
8. THE Adjudication_Table SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮 + GtIndexChip跳转D5-4测算结果和D1-6票据业务模式）和"审计结论"区域（textarea + AI生成按钮）

### Requirement 3: 审定表D5-1 跨Sheet联动与回写

**User Story:** As a 审计助理, I want to 审定表自动从明细表聚合、从公允价值测算取OCI变动值, so that 数据在各表间保持一致、减少手工复制错误。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按"类别"列聚合期末审定数：类别=应收票据→填入审定表"应收票据"行；类别=应收账款→填入"应收账款"行
2. THE Cross_Sheet_Engine SHALL 从 FairValue_Table 的期末公允价值合计行取数填入审定表"减：OCI公允价值变动"行（OCI变动=小计票面-D5-4公允价值合计）
3. WHEN Detail_Table 或 FairValue_Table 数据变更时, THE Cross_Sheet_Engine SHALL 在2秒内刷新 Adjudication_Table 中的聚合值（通过allResponses computed链响应式刷新）
4. WHILE 跨sheet引用值生效时, THE Adjudication_Table SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
5. WHEN EventBus发布'adjustment:created'事件时, THE Adjudication_Table SHALL 自动将对应AJE/RJE金额同步到审定表相应行
6. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用writebackTrialBalance将最新审定数回写trial_balance.audited_amount（科目1124）并通过EventBus发布'substantive:adjudicated'事件
7. IF 跨sheet数据加载失败, THEN THE Cross_Sheet_Engine SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 4: 明细表D5-2 HTML渲染（17列宽表40公式）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理应收款项融资明细, so that 我能追踪每笔应收票据/应收账款的期初、本期变动和期末审定余额及OCI减值准备。

#### Acceptance Criteria

1. THE Detail_Table SHALL 以el-table横向滚动渲染17列：类别(A)|明细项目(B)|期初未审(C)|期初AJE(D)|期初RJE(E)|期初审定(F)|OCI减值准备余额(G)|本期增加(H)|本期减少(I)|期末余额(J)|被审计单位重分类(K)|期末未审余额(L)|期末账项调整(M)|期末重分类调整(N)|期末审定余额(O)|期末OCI减值(P)|备注(Q)
2. THE Detail_Table SHALL 对"类别"列应用下拉选择（应收票据/应收账款）
3. THE Formula_Engine SHALL 自动计算每行：期初审定=期初未审+AJE+RJE；期末余额=期初审定+本期增加-本期减少；期末未审余额=期末余额+被审计单位重分类；期末审定余额=期末未审+账项调整+重分类调整
4. THE Detail_Table SHALL 在底部显示按类别的小计行（应收票据小计/应收账款小计）和总合计行，合计行不可编辑
5. WHEN 用户点击"添加明细行"按钮时, THE Detail_Table SHALL 在合计行上方新增一个可编辑空行
6. THE Detail_Table SHALL 固定前2列（类别/明细项目）使横向滚动时仍可辨识行
7. THE Detail_Table SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
8. THE Detail_Table SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于变动情况生成说明）和"审计结论"textarea，各带复核对话入口（💬图标）
9. WHEN 动态行超过30行时, THE Detail_Table SHALL 启用虚拟滚动以保证渲染性能

### Requirement 5: 明细表D5-2 自动提取与跨底稿导入

**User Story:** As a 审计助理, I want to 明细表支持从D1票据和D2应收账款底稿按业务模式自动导入, so that 确定归入应收款项融资的资产不需要手工逐笔录入。

#### Acceptance Criteria

1. WHEN 用户点击"从D1导入(出售模式票据)"按钮时, THE Detail_Table SHALL 通过EventBus请求D1底稿中业务模式为"出售"的票据数据，导入为类别=应收票据的明细行
2. WHEN 用户点击"从D2导入(出售模式账款)"按钮时, THE Detail_Table SHALL 通过EventBus请求D2底稿中业务模式为"出售"的应收账款数据，导入为类别=应收账款的明细行
3. THE Detail_Table SHALL 在导入完成后显示摘要（"成功导入N笔应收票据/M笔应收账款"）
4. THE Detail_Table SHALL 支持从tb_aux_balance（科目1124，按明细维度）批量导入期初/期末未审余额（"从余额表导入"按钮）
5. THE Detail_Table SHALL 支持"导出空模板"（含表头+格式，无数据行）和"导入数据"（解析上传xlsx回写checklist_responses）
6. IF 导入的xlsx格式不符合模板结构, THEN THE Detail_Table SHALL 显示错误提示并列出不匹配的列名
7. THE Detail_Table SHALL 在"类别"列旁提供GtIndexChip：应收票据行→跳转D1-6票据业务模式；应收账款行→跳转D2-13应收账款业务模式

### Requirement 6: 公允价值测算表D5-4 HTML渲染（13列18公式，核心贴现计算）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行应收款项融资公允价值测算, so that 我能基于贴现公式计算每笔资产的期末公允价值并判定公允价值层次。

#### Acceptance Criteria

1. THE FairValue_Table SHALL 以el-table渲染13列：类别(A)|明细项目(B)|票据号(C)|票面金额(D)|计量日(E)|到期日(F)|剩余天数(G)|市场贴现利率(H)|贴现利息/保理费用(I)|贴现金额/保理金额(J)|应收款项融资期末公允价值(K)|公允价值层次(L)|备注(M)
2. THE Formula_Engine SHALL 自动计算：剩余天数=到期日-计量日（天数）；贴现利息=票面金额×市场贴现利率×剩余天数÷360；贴现金额=票面金额-贴现利息（即公允价值）；期末公允价值=贴现金额
3. THE FairValue_Table SHALL 对"公允价值层次"列应用下拉选择（第二层次/第三层次），并在tooltip提示判定规则："可观察输入值(如银行公布贴现利率)→第二层次；不可观察输入值→第三层次"
4. THE FairValue_Table SHALL 对"市场贴现利率"列提供默认值配置能力（全表统一默认利率，用户可逐行覆盖）
5. THE FairValue_Table SHALL 在底部显示合计行：票面金额合计/贴现利息合计/公允价值合计
6. WHEN 用户点击"添加测算行"按钮时, THE FairValue_Table SHALL 新增一个可编辑空行（类别/明细项目/票据号/票面金额/到期日为必填）
7. THE FairValue_Table SHALL 对"计量日"列默认填充资产负债表日（period_end），用户可修改
8. WHEN 公允价值合计与D5-2期末审定合计存在差异时, THE FairValue_Table SHALL 在合计行下方显示黄色差异提示"D5-4公允价值合计≠D5-2期末审定合计，差额=OCI公允价值变动：±xxx元"
9. THE FairValue_Table SHALL 在底部显示"审计说明"textarea（AI生成按钮，评价贴现利率合理性+公允价值层次判定依据）和"审计结论"textarea
10. THE FairValue_Table SHALL 对"市场贴现利率"列右键提供复核对话入口（💬图标），sectionId为"D5-4-discount-rate"（贴现利率是核心争议点）

### Requirement 7: 调整分录汇总表D5-3 HTML渲染与联动

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理应收款项融资调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示10列：调整事项说明 | 类别(报表调整/账项调整/其他) | 报表项目 | 科目名称 | 附注项目 | … | 借方调整金额 | 贷方调整金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_Table SHALL 新增一行可编辑空行
3. THE Adjustment_Table SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='D5'/entryType/amount）
5. THE Adjustment_Table SHALL 双向同步AJE/RJE合计到 Adjudication_Table 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_Table SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_Table SHALL 在底部显示编制提示（`<details>`折叠，蓝色左边线+浅蓝背景，默认收起）

### Requirement 8: 附注披露信息（上市公司+国企）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑应收款项融资附注披露, so that 我能按子节结构核对附注数据并与审定表自动取数对齐。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染为多子节卡片结构：(1)应收款项融资分类（项目/期末余额/上年年末余额，子行：应收票据/应收账款/小计/减:OCI变动/公允价值）→ (2)减值准备变动（上年末余额/本期计提/收回转回/核销/期末余额）→ (3)披露说明文字段
2. THE Disclosure_SOE SHALL 渲染为简化版卡片结构：(1)应收款项融资分类（项目/期末余额/期初余额，子行：应收票据/应收账款/合计）
3. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table 审定数自动取数填入附注第(1)子节对应行（应收票据/应收账款/公允价值合计）
4. WHILE 跨sheet引用值生效时, THE Disclosure_Listed SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
5. THE Disclosure_Listed SHALL 对第(2)子节减值准备变动支持动态行添加/删除，并自动计算：期末余额=上年末+本期计提-收回转回-核销
6. THE Disclosure_Listed SHALL 根据项目applicable_standards（listed_standalone/listed_consolidated）自动显示；THE Disclosure_SOE SHALL 根据项目applicable_standards（soe_standalone/soe_consolidated）自动显示
7. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在同一Tab内通过el-segmented切换（"上市公司版" | "国企版"），不适用的版本隐藏
8. THE Disclosure_Listed SHALL 在每个子节底部放置"说明"textarea（可编辑，双向回写附注模块，EventBus `disclosure:note-text-updated`）和编制提示折叠区（`<details>`默认收起）

### Requirement 9: 实质性程序表D5A 集成

**User Story:** As a 审计助理, I want to 程序表D5A集成到统一入口并联动各子sheet索引, so that 我能从程序表出发逐步执行审计步骤并跳转到对应底稿。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 复用`a-program-console` componentType渲染7步审计程序（常规5+IPO1+列报1）+5项审计目标（存在/完整性/权利和义务/准确性计价分摊/列报）
2. THE Procedure_Table SHALL 在每步程序的"底稿索引号"列提供GtIndexChip，点击跳转至对应目标：D5-1/D5-2/D1-6/D2-13/D0/D1-7/D1-10/D5-4/A1-1/A1-15/A1-16
3. THE Procedure_Table SHALL 特别标注步骤3"确定业务模式"引用D1-6(票据业务模式)和D2-13(应收账款业务模式)的跨底稿GtIndexChip
4. THE Procedure_Table SHALL 特别标注步骤4"结合应收票据、应收账款科目审计执行函证、监盘等程序"引用D0/D1-7/D1-10的跨底稿GtIndexChip
5. WHEN B50风险评估更新时, THE Procedure_Table SHALL 通过EventBus接收'risk:updated'事件并更新程序步骤状态标记
6. THE Procedure_Table SHALL selfLoad渲染数据（当htmlData prop为null时自行调render-config?force_component_type=a-program-console）

### Requirement 10: 跨底稿EventBus联动与GtIndexChip交叉索引

**User Story:** As a 审计助理, I want to D5应收款项融资底稿与D1/D2/D0/A13等底稿自动联动并提供交叉索引跳转, so that 审定数变化和业务模式判断能实时传递到相关底稿。

#### Acceptance Criteria

1. WHEN D5-1审定数变化时, THE Cross_Sheet_Engine SHALL 通过EventBus发布'substantive:adjudicated'事件回写trial_balance科目1124（payload含wpCode='D5'/accountCode='1124'/auditedAmount）
2. WHEN D5-3调整分录创建时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件联动A13错报汇总
3. WHEN EventBus收到'risk:updated'事件时（B50风险评估更新）, THE Procedure_Table SHALL 更新程序步骤状态标记
4. THE Adjudication_Table SHALL 在"应收票据"行提供GtIndexChip跳转D1-6票据业务模式
5. THE Adjudication_Table SHALL 在"应收账款"行提供GtIndexChip跳转D2-13应收账款业务模式
6. THE Adjudication_Table SHALL 在审计说明区域提供GtIndexChip跳转D5-4公允价值测算
7. THE FairValue_Table SHALL 在"公允价值层次"列旁提供GtIndexChip跳转附注披露对应说明
8. THE Procedure_Table SHALL 在各步骤索引号列提供GtIndexChip跳转：D5-1/D5-2/D1-6/D2-13/D0/D1-7/D1-10/D5-4/A1-1/A1-15/A1-16
9. WHEN 用户点击GtIndexChip时, THE Cross_Sheet_Engine SHALL 切换到目标Tab并高亮定位到目标行

### Requirement 11: 自动提取填充与AI辅助

**User Story:** As a 审计助理, I want to 审定表从试算平衡表自动获取数据且各sheet支持AI生成审计说明, so that 未审数不需要手工录入且专业文本有AI辅助建议。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 通过auto_data_source resolver从trial_balance（科目1124）自动获取期初/期末未审数
2. WHILE TB数据尚未导入时, THE Adjudication_Table SHALL 在未审数单元格显示"待导入TB"灰色占位文字
3. THE FairValue_Table SHALL 对"市场贴现利率"列支持从项目配置获取默认值（被审计单位提供的贴现利率或市场公开利率）
4. THE Adjudication_Table SHALL 在审计说明/结论textarea旁提供🤖AI生成按钮，基于变动情况+D5-4测算结果+业务模式判断作为context生成审计说明
5. THE FairValue_Table SHALL 在审计说明textarea旁提供🤖AI生成按钮，评价贴现利率选取合理性+公允价值层次判定依据+与市场利率对比分析
6. THE Detail_Table SHALL 在审计说明textarea旁提供🤖AI生成按钮，基于期初期末变动分析+各类别余额变化生成说明
7. THE AI生成按钮 SHALL 调用POST /api/workpapers/{wp_id}/d5/ai-generate端点，传入sectionId+existingContent+relatedContext

### Requirement 12: 双模式切换与持久化

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice之间切换且所有编辑自动保存, so that 我不会丢失数据且能根据需要选择编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE D5 组件 SHALL 使用 checklist_responses 表存储所有sheet数据，item_id前缀为"D5-{sheetCode}-{field}"格式（如D5-1-adj-note-audited, D5-2-rows, D5-4-rows）
6. THE Dynamic_Row 类型sheet（D5-2/D5-3/D5-4）SHALL 以JSON数组格式存储动态行于remark字段
7. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
8. WHEN 用户切换结论/选择类字段时, THE Formula_Engine SHALL 立即保存该字段

### Requirement 13: 复核对话集成

**User Story:** As a 现场经理, I want to 在D5底稿任意位置发起和查看复核对话, so that 我能针对具体数据点与审计助理进行复核讨论。

#### Acceptance Criteria

1. THE 各sheet审计说明/结论区域 SHALL 固定放置复核对话入口按钮（💬图标），点击调用openReviewDialog（sectionId自动生成为`D5-{sheetCode}-note`）
2. THE 各sheet表格 SHALL 支持单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D5-{sheetCode}-{rowKey}-{field}`）
3. WHEN 有活跃复核线程时, THE 各sheet SHALL 在对应位置显示蓝色圆点（待回复）或红色圆点（有新回复）标记
4. THE 复核对话 SHALL 特别关注以下高风险区域（红色圆点优先级更高）：D5-4贴现利率选取、D5-4公允价值层次判定、D5-1 OCI变动合理性
5. THE 各sheet SHALL 通过inject方式获取openReviewDialog函数（由GtD5ReceivablesFinancing.vue在provide层统一注入）

### Requirement 14: 后端Render策略与Resolver注册

**User Story:** As a 开发者, I want to D5底稿的后端渲染策略和auto_data resolver正确注册, so that render-config API能返回正确数据且TB自动取数功能正常工作。

#### Acceptance Criteria

1. THE RENDERER_DISPATCH SHALL 注册'd5-receivables-financing' componentType对应的render策略函数`_render_d5_receivables_financing`
2. THE render策略函数 SHALL 返回包含审定表OCI结构+明细表行数据+公允价值测算行数据+各sheet配置的完整html_data
3. THE auto_data_resolvers._REGISTRY SHALL 注册`d5_tb_unadjusted` resolver（从trial_balance科目1124取期初/期末未审数）
4. THE account_package_registry.json SHALL 包含D5_receivables_financing工作包定义（sheets清单对齐源模板7个有效sheet：D5A/D5-1/D5-2/D5-3/D5-4/附注上市/附注国企）
5. THE render策略函数 SHALL 读取D5.yaml render schema中的fixed_cells和dynamic_table配置生成初始结构化数据
