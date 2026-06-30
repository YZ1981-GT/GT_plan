# Requirements Document: D6 合同资产底稿专属HTML精美组件

## Introduction

D6合同资产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `d6-contract-assets`，覆盖源模板12个有效sheet（程序表D6A + 审定表D6-1 + 明细表D6-2 + 减值准备明细D6-3 + 调整分录D6-4 + 关联方检查D6-5 + 检查表D6-6 + 减值政策D6-7 + 减值测算D6-8 + 转回核销D6-9 + 附注上市 + 附注国企），合计约649个公式。科目编码1402合同资产（借方科目/资产类）。核心特色：三区块审定表（原值/坏账准备/净值，各含"减：列示于其他非流动资产的合同资产"扣减行）、30列明细表（平台最宽）、ECL双组合减值测算（单项计提+账龄组合×多组合）、段落式会计政策检查（非表格）、163公式最复杂附注（5子节含按组合分组明细）、净值=原值-坏账跨区块联动。D循环中第二复杂底稿（仅次于D4营业收入）。结构复杂（12有效sheet），1级el-tabs 11个tab-pane：程序表/审定表/明细表/减值准备明细/调整分录/关联方/检查表/减值政策/减值测算/减值转回核销/附注。附注含上市+国企切换。

## Glossary

- **Adjudication_Table**: 审定表D6-1，三区块结构（合同资产原值/坏账准备/净值），177个公式，各区块含"减：列示于其他非流动资产的合同资产"扣减行
- **Detail_Table**: 明细表D6-2，30列最宽表（69公式），核心数据源，按合同×客户×账龄×收款权×信用风险组合记录
- **Impairment_Detail_Table**: 合同资产减值准备明细表D6-3，14列（63公式），双分类行结构（按单项/按组合）+本期增减变动公式
- **Adjustment_Table**: 调整分录汇总表D6-4，10列标准格式动态行
- **Related_Party_Check**: 关联关系及交易检查D6-5，14列（含坏账准备+账面价值）
- **Inspection_Table**: 合同资产检查表D6-6，双区块（本期增减变动+期后贴现/背书/调整检查）+抽样参数区，19公式
- **Policy_Check**: 合同资产减值准备会计政策检查D6-7，段落式（非表格），左右分栏描述+同行业比较
- **ECL_Calculation**: 减值准备测算D6-8，ECL双组合测算（单项计提+账龄组合×多组合），58公式
- **Writeoff_Check**: 减值准备转回、核销检查表D6-9，双段表（转回检查+核销检查）
- **Disclosure_Listed**: 附注披露信息（上市公司），5子节163公式，含减值准备计提/单项/组合/减值变动
- **Disclosure_SOE**: 附注披露信息（国企），3子节简化版
- **Procedure_Table**: 实质性程序表D6A，审计程序+审计目标（复用a-program-console）
- **Cross_Sheet_Engine**: 跨sheet公式引擎，D6-2→D6-1原值聚合+D6-3→D6-1坏账聚合+净值=原值-坏账+D6-8→D6-3测算回写
- **Formula_Engine**: 前端公式引擎composable，借方科目核心公式：期末=期初+借方-贷方；审定数=未审+AJE+RJE；净值=原值-坏账准备；应计提=余额×损失率
- **Three_Block_Structure**: 三区块审定表结构（一、原值/二、坏账准备/三、净值），每区块含动态行+小计+"减：列示于其他非流动资产"+XX小计
- **Net_Value_Formula**: 净值跨区块公式：净值各行=原值对应行-坏账准备对应行（跨区块联动）
- **Non_Current_Deduction**: "减：列示于其他非流动资产的合同资产"扣减行，三个区块都出现
- **ECL_Dual_Group**: ECL双组合结构：(一)单项计提坏账准备 + (二)账龄组合计提坏账准备（支持多组合，如业务类型组合/客户类型组合）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动原因/减值合理性/政策评价等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1402，借方科目/资产类）
- **Paragraph_Style**: 段落式渲染（D6-7专用），左右分栏描述+textarea，非el-table

## Requirements

### Requirement 1: 组件架构与Tab设计

**User Story:** As a 开发者, I want to D6合同资产底稿按sheet拆分为独立Tab, so that 12个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE D6 组件 SHALL 注册新componentType: `d6-contract-assets`，主入口为 GtD6ContractAssets.vue（el-tabs容器，11个tab-pane：程序表/审定表/明细表/减值准备明细/调整分录/关联方/检查表/减值政策/减值测算/减值转回核销/附注披露）
2. THE D6 组件 SHALL 将每个sheet拆分为独立Vue子组件（D6TabProcedure.vue / D6TabAdjudication.vue / D6TabDetail.vue / D6TabImpairmentDetail.vue / D6TabAdjustment.vue / D6TabRelatedParty.vue / D6TabInspection.vue / D6TabPolicyCheck.vue / D6TabEclCalculation.vue / D6TabWriteoffCheck.vue / D6TabDisclosure.vue），每文件200-400行
3. THE D6 组件 SHALL 拆分为独立composable：useD6FormData.ts（基础数据加载/保存）+ useD6FormulaEngine.ts（纯函数公式引擎）+ useD6CrossSheet.ts（跨sheet联动逻辑）
4. THE useD6FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：借方科目期末=期初+借方-贷方、审定数=未审+AJE+RJE、净值=原值-坏账准备、应计提=余额×损失率、变动率计算、合计行SUM、"减：列示于其他非流动资产"扣减计算、各区块小计=SUM(动态行)、XX小计=小计-非流动扣减
5. THE D6 组件 SHALL 在htmlRendererRegistry中注册'd6-contract-assets'→GtD6ContractAssets映射
6. THE D6 组件 SHALL 在wp_code_overrides.json中将D6/D6-1/D6-2/D6-3/D6-4/D6-5/D6-6/D6-7/D6-8/D6-9的componentType统一映射为'd6-contract-assets'
7. THE D6 组件 SHALL 在VALID_COMPONENT_TYPES中注册'd6-contract-assets'
8. THE GtD6ContractAssets.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=d6-contract-assets）

### Requirement 2: 审定表D6-1 三区块HTML渲染（177公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑合同资产审定表, so that 我能清晰地看到原值、坏账准备、净值三个维度的审定数据及其扣减关系。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为三区块固定结构：一、合同资产原值（动态行/小计/减：列示于其他非流动资产的合同资产/合同资产原值小计）→ 二、合同资产坏账准备（动态行/小计/减：列示于其他非流动资产的合同资产坏账准备/合同资产坏账准备小计）→ 三、合同资产净值（动态行/小计/减：列示于其他非流动资产的合同资产净值/合同资产净值合计/试算平衡表数/差异数）
2. THE Adjudication_Table SHALL 显示以下列：项目 | 期初数(未审/账项调整/重分类调整/审定) | 期末数(未审/账项调整/重分类调整/审定) | 变动额 | 变动率 | 原因分析
3. WHEN 用户编辑未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动计算各区块：小计=SUM(动态行)；XX小计=小计-"减：列示于其他非流动资产"；变动额=期末审定-期初审定；变动率=(期末-期初)/期初（期初=0且期末=0→空,期初=0→'N/A'）
5. THE Adjudication_Table SHALL 在"三、合同资产净值"区块中自动计算：净值各行=原值对应行审定数-坏账准备对应行审定数（跨区块公式）
6. THE Adjudication_Table SHALL 在三个区块的"减：列示于其他非流动资产"行以浅蓝色背景标记（可手动编辑），tooltip显示"列示于其他非流动资产的合同资产部分"
7. WHEN 变动率绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
8. THE Adjudication_Table SHALL 在"三、净值"区块底部显示试算平衡表数行（自动取数科目1402）和差异行（=合同资产净值合计-试算表数），差异不为零时红色高亮
9. THE Adjudication_Table SHALL 对三个区块的小计行进行交叉验证：净值小计=原值小计-坏账准备小计，不一致时显示黄色警告"净值≠原值-坏账准备，差额：±xxx元"
10. THE Adjudication_Table SHALL 在每个区块头部显示区块标题（带序号如"一、合同资产原值"），区块间以2px深灰分割线隔开

### Requirement 3: 审定表D6-1 跨Sheet联动与回写

**User Story:** As a 审计助理, I want to 审定表自动从明细表聚合原值、从减值准备明细聚合坏账、自动计算净值, so that 三区块数据在各表间保持一致、减少手工复制错误。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按分类聚合期末审定数填入 Adjudication_Table "一、合同资产原值"区块对应动态行
2. THE Cross_Sheet_Engine SHALL 从 Impairment_Detail_Table 按分类聚合期末审定数填入 Adjudication_Table "二、合同资产坏账准备"区块对应动态行
3. THE Cross_Sheet_Engine SHALL 自动计算"三、合同资产净值"区块各行：净值=原值对应行-坏账准备对应行（跨区块联动）
4. WHEN Detail_Table 或 Impairment_Detail_Table 数据变更时, THE Cross_Sheet_Engine SHALL 在2秒内刷新 Adjudication_Table 中的聚合值（通过allResponses computed链响应式刷新）
5. WHILE 跨sheet引用值生效时, THE Adjudication_Table SHALL 以浅蓝色背景标记自动取数单元格，并在tooltip显示数据来源（如"取自D6-2按分类聚合"/"取自D6-3按分类聚合"/"净值=原值-坏账"）
6. WHEN EventBus发布'adjustment:created'事件时, THE Adjudication_Table SHALL 自动将对应AJE/RJE金额同步到审定表相应行
7. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用writebackTrialBalance将最新审定数（净值合计）回写trial_balance.audited_amount（科目1402）并通过EventBus发布'substantive:adjudicated'事件（payload含wpCode='D6'/accountCode='1402'/auditedAmount）
8. IF 跨sheet数据加载失败, THEN THE Cross_Sheet_Engine SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 4: 审定表D6-1 审计说明与AI辅助

**User Story:** As a 审计助理, I want to 审定表底部有结构化的审计说明和结论区域并支持AI生成, so that 我能快速记录审计发现并获得AI辅助撰写建议。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在表尾显示"审计说明"区域，包含：(1)合同资产变动分析（自动生成变动百分比句子 + textarea手填/AI生成）(2)坏账准备计提充分性评价（textarea + GtIndexChip跳转D6-8减值测算）(3)长期合同资产挂账原因说明（textarea + GtIndexChip跳转D6-6检查表）
2. THE Adjudication_Table SHALL 在审计说明区域的每个textarea旁显示🤖AI生成按钮，点击调用AI生成审计说明文本（基于当前数据变动情况+D6-8测算结果+D6-6检查发现作为context）
3. THE Adjudication_Table SHALL 在底部显示"审计结论"区域（textarea + AI生成按钮）
4. THE Adjudication_Table SHALL 在"审计说明"和"审计结论"区域各放置一个固定复核对话入口按钮（💬图标），点击调用openReviewDialog
5. THE Adjudication_Table SHALL 支持表格单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D6-adj-{block}-{rowKey}-{field}`）
6. WHEN 有活跃复核线程时, THE Adjudication_Table SHALL 在对应位置显示蓝/红圆点标记
7. THE Adjudication_Table SHALL 显示编制提示折叠区（`<details>`蓝色左边线+浅蓝背景，默认收起，内容为"借方科目：期末=期初+借方-贷方"+"净值=原值-坏账准备"公式说明）

### Requirement 5: 明细表D6-2 30列HTML渲染（69公式）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理合同资产明细, so that 我能在语义化的横向滚动表格中编辑30列数据，追踪每笔合同资产的期初、本期变动、期末审定余额及账龄和信用风险组合。

#### Acceptance Criteria

1. THE Detail_Table SHALL 以el-table横向滚动渲染30+列：序号|合同名称/项目名称|类型|客户名称|公司代码|关联关系|期初未审数|期初账项调整|期初重分类调整|期初审定余额|期初审定账龄(1年以下/1~2年/2~3年/3年以上)|借方发生|贷方发生|期末未审余额|账项调整|重分类调整|期末审定余额|期末审定账龄(1年以下/1~2年/2~3年/3年以上)|1年以内收款权|1年以上收款权|是否在建设期或质保期内|信用风险组合方式|是否函证|期后结转金额
2. THE Detail_Table SHALL 对"类型"列应用下拉选择（工程施工/质量保证金/其他等合同资产类别）
3. THE Detail_Table SHALL 对"关联关系"列应用下拉选择（非关联方/实际控制人/控股股东/控股股东附属企业/持有5%以上/联营/合营/董高监/其他关联方）
4. THE Formula_Engine SHALL 自动计算每行（借方科目）：期初审定=期初未审+AJE+RJE；期末未审=期初审定+借方发生-贷方发生（借方科目！）；期末审定=期末未审+账项调整+重分类调整
5. THE Detail_Table SHALL 在底部显示按分类的小计行和总合计行（=SUM所有明细行各金额列），合计行不可编辑
6. THE Detail_Table SHALL 在底部显示附加分类行（合并范围内关联方/合并范围外关联方/非关联方 + 单项计提坏账准备/业务类型组合/客户类型组合），附加分类行从对应明细行自动聚合
7. WHEN 用户点击"添加明细行"按钮时, THE Detail_Table SHALL 在合计行上方新增一个可编辑空行
8. THE Detail_Table SHALL 对"信用风险组合方式"列应用下拉选择（单项计提坏账准备/业务类型组合/客户类型组合/…动态组合）
9. THE Detail_Table SHALL 对"是否在建设期或质保期内"列应用下拉选择（是/否）
10. WHEN 关联关系列为非"非关联方"时, THE Detail_Table SHALL 以橙色背景高亮该行
11. THE Detail_Table SHALL 固定前4列（序号/合同名称/类型/客户名称）使横向滚动时仍可辨识行
12. WHEN 动态行超过30行时, THE Detail_Table SHALL 启用虚拟滚动以保证渲染性能
13. THE Detail_Table SHALL 支持按合同名称/客户名称模糊搜索筛选行（搜索框在表头上方）
14. THE Detail_Table SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）

### Requirement 6: 明细表D6-2 自动提取与联动

**User Story:** As a 审计助理, I want to 明细表支持从辅助余额表批量导入和跨底稿联动, so that 我不需要逐行手工录入大量合同资产明细数据。

#### Acceptance Criteria

1. WHEN 用户点击"从余额表导入"按钮时, THE Detail_Table SHALL 从tb_aux_balance（科目1402，按客户/合同维度）批量导入合同名称、客户名称和期初/期末未审余额
2. WHEN 导入数据行数超过现有行时, THE Detail_Table SHALL 自动扩展动态行以容纳全部数据
3. THE Detail_Table SHALL 在导入完成后显示摘要（"成功导入N行数据，M个新合同"）
4. WHEN EventBus发布'confirmation:completed'事件时（D0函证完成）, THE Detail_Table SHALL 自动将对应客户行的"是否函证"列标记为"Y"
5. THE Detail_Table SHALL 支持"导出空模板"（含表头+格式+公式，无数据行）和"导出数据"（含当前数据的xlsx文件）
6. WHEN 用户上传已填写的xlsx文件时, THE Detail_Table SHALL 使用openpyxl解析文件内容并将数据回写到checklist_responses
7. IF 导入的xlsx格式不符合模板结构, THEN THE Detail_Table SHALL 显示错误提示并列出不匹配的列名
8. WHEN 用户输入客户名称时, THE Detail_Table SHALL 自动从related_parties表模糊匹配关联方信息并填充"关联关系"列

### Requirement 7: 明细表D6-2 审计说明与复核

**User Story:** As a 审计助理, I want to 明细表底部有结构化审计说明区域, so that 我能记录期末变动原因、账龄分布情况、信用风险组合判断等关键审计发现。

#### Acceptance Criteria

1. THE Detail_Table SHALL 在底部显示3条审计说明textarea：(1)期末变动原因分析 (2)账龄分布及信用风险组合划分说明 (3)期后结转情况说明（含GtIndexChip跳转D6-6检查表）
2. THE Detail_Table SHALL 在每条审计说明textarea旁显示🤖AI生成按钮，基于当前明细数据变动+账龄分布+信用风险组合自动生成说明文本
3. THE Detail_Table SHALL 在底部显示"审计结论"区域（textarea + AI生成按钮）
4. THE Detail_Table SHALL 在审计说明和结论区域放置复核对话入口（💬图标）
5. WHEN 有活跃复核线程时, THE Detail_Table SHALL 在对应区域显示蓝/红圆点标记

### Requirement 8: 合同资产减值准备明细表D6-3 HTML渲染（14列63公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中管理合同资产减值准备明细, so that 我能追踪按单项评估和按信用风险组合两种分类的坏账准备期初、本期增减和期末情况。

#### Acceptance Criteria

1. THE Impairment_Detail_Table SHALL 以el-table渲染14列：项目 | 期初数(未审余额/账项调整/重分类调整/审定余额) | 本期增加(计提/其他增加) | 本期减少(转回/核销/其他减少) | 期末数(未审余额/账项调整/重分类调整/审定余额)
2. THE Impairment_Detail_Table SHALL 渲染为双分类行结构：按单项评估计提（其中：动态行）+ 按信用风险组合计提（其中：动态行）+ 合计行
3. THE Formula_Engine SHALL 自动计算每行：期初审定=期初未审+AJE+RJE；期末未审=期初审定+计提+其他增加-转回-核销-其他减少；期末审定=期末未审+账项调整+重分类调整
4. THE Impairment_Detail_Table SHALL 在"按单项评估计提"和"按信用风险组合计提"各显示小计行（=SUM对应分类下动态行），合计行=按单项小计+按组合小计
5. WHEN 用户点击"添加单项计提行"或"添加组合计提行"按钮时, THE Impairment_Detail_Table SHALL 在对应分类的小计行上方新增一个可编辑空行
6. THE Impairment_Detail_Table SHALL 在底部显示核对行（=D6-3合计 vs D6-1坏账准备区块合计），差异不为零时红色高亮
7. THE Impairment_Detail_Table SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
8. THE Impairment_Detail_Table SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于计提/转回/核销变动分析）和"审计结论"textarea

### Requirement 9: 调整分录D6-4 渲染与联动

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理合同资产调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示10列：调整事项说明 | 类别(报表调整/账项调整/其他) | 报表项目 | 科目名称 | 附注项目 | … | 借方调整金额 | 贷方调整金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_Table SHALL 新增一行可编辑空行
3. THE Adjustment_Table SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='D6'/entryType/amount/accountCode='1402'）
5. THE Adjustment_Table SHALL 双向同步AJE/RJE合计到 Adjudication_Table 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_Table SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_Table SHALL 在底部显示编制提示（`<details>`折叠，蓝色左边线+浅蓝背景，默认收起）

### Requirement 10: 关联关系及交易检查D6-5 HTML渲染（14列）

**User Story:** As a 审计助理, I want to 在精美HTML表格中记录合同资产关联方交易检查, so that 我能追踪每个关联方的合同资产余额、坏账准备和账面价值。

#### Acceptance Criteria

1. THE Related_Party_Check SHALL 显示14列：关联方名称 | 关联关系 | 期初余额 | 借方发生 | 贷方发生 | 期末余额 | 坏账准备 | 账面价值 | 发生时间及账龄 | 未结转或未偿还的原因 | 至审计日结转或偿还金额 | 处理计划 | 索引号 | 备注
2. THE Related_Party_Check SHALL 对"关联关系"列应用下拉选择（实际控制人/控股股东/控股股东附属企业/持有5%以上/联营/合营/董高监/其他关联方）
3. THE Formula_Engine SHALL 自动计算每行：期末余额=期初余额+借方发生-贷方发生（借方科目）；账面价值=期末余额-坏账准备
4. WHEN 用户点击"从D6-2导入"按钮时, THE Related_Party_Check SHALL 自动从 Detail_Table 筛选"关联关系≠非关联方"的行导入（取客户名称/关联关系/期初余额/借方/贷方/期末余额）
5. WHEN 用户点击"添加关联方"按钮时, THE Related_Party_Check SHALL 新增一行，并自动从项目关联方清单下拉匹配
6. THE Related_Party_Check SHALL 在底部显示合计行（期初/借方/贷方/期末/坏账准备/账面价值各列SUM）
7. THE Related_Party_Check SHALL 在底部显示"审计说明"textarea（AI生成按钮，结合关联方清单+交易性质评价合理性）和"审计结论"textarea
8. THE Related_Party_Check SHALL 在每行提供GtIndexChip，点击跳转至D6-2对应客户明细行
9. THE Related_Party_Check SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 11: 合同资产检查表D6-6 HTML渲染（双区块+抽样参数19公式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行合同资产凭证抽样检查（含本期增减变动和期后贴现/背书/调整两个维度）, so that 我能记录抽样参数和逐笔核对凭证信息。

#### Acceptance Criteria

1. THE Inspection_Table SHALL 分为3区域：抽样参数区（测试总体/特定样本/抽样总体/确定的抽样样本量/抽样方法/抽样过程）+ (1)本期增减变动检查 + (2)期后贴现/背书/调整等检查
2. THE Inspection_Table "(1)本期增减变动检查"区块 SHALL 显示列：客户名称|日期|凭证编号|业务内容|对方科目|对方明细科目|借方金额|贷方金额|支持性文件|核对内容(1-5)|索引号|是否异常|备注说明
3. THE Inspection_Table "(2)期后贴现/背书/调整等检查"区块 SHALL 显示列（无借方金额列）：客户名称|日期|凭证编号|业务内容|对方科目|对方明细科目|贷方金额|支持性文件|核对内容(1-5)|索引号|是否异常|备注说明
4. WHEN 用户点击"添加样本"按钮时, THE Inspection_Table SHALL 在对应区块新增一行凭证抽样明细
5. THE Inspection_Table SHALL 在底部显示检查比例汇总（方向/账面金额/检查金额/检查比例），自动从D6-2取账面金额合计计算比例
6. THE Inspection_Table SHALL 在抽样参数区显示进度条：已抽取样本数/目标样本量
7. THE Inspection_Table SHALL 集成抽凭引擎（voucher-sampling-engine），支持从D6-2选定客户后自动进入抽凭流程
8. THE Inspection_Table SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
9. WHEN "(2)期后贴现/背书/调整"区块的对方科目为主营业务收入时, THE Inspection_Table SHALL 提供GtIndexChip跳转D4营业收入底稿对应位置

### Requirement 12: 合同资产减值准备会计政策检查D6-7 HTML渲染（段落式）

**User Story:** As a 审计助理, I want to 在段落式精美HTML组件中记录合同资产减值准备会计政策检查, so that 我能以结构化文档形式评价被审计单位ECL模型的合理性并与同行业比较。

#### Acceptance Criteria

1. THE Policy_Check SHALL 以段落式卡片布局渲染4个节：(一)合同资产减值准备计提会计政策（textarea段落描述，左右分栏：左=被审计单位政策/右=准则要求）→ (二)被审计单位历史坏账损失情况（textarea段落描述）→ (三)前瞻性信息的来源及其影响（textarea段落描述）→ (四)同行业公司的会计政策（对比表：公司名称/会计政策摘要/预期信用损失率对比）
2. THE Policy_Check 第(一)节 SHALL 以左右分栏布局（左60%=被审计单位实际政策textarea/右40%=CAS22准则要求只读灰底），双栏对照便于评价偏离
3. THE Policy_Check 第(四)节 SHALL 以el-table渲染同行业对比：公司名称|ECL模型描述|账龄组合比例|单项计提标准|与被审计单位差异分析，支持动态添加行
4. THE Policy_Check SHALL 在每节底部显示"审计评价"textarea（AI生成按钮，评价政策合理性/一致性/前瞻性信息充分性）
5. THE Policy_Check SHALL 在底部显示"三、审计说明"textarea（AI生成按钮）和"四、审计结论"textarea
6. THE Policy_Check SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
7. THE Policy_Check SHALL 在第(一)节提供GtIndexChip跳转D6-8减值测算（验证政策执行一致性）
8. THE Policy_Check SHALL 对所有textarea应用自动高度调整（min-height:120px, auto-grow）

### Requirement 13: 减值准备测算D6-8 HTML渲染（ECL双组合58公式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行合同资产ECL减值准备测算, so that 我能基于单项计提和账龄组合两种方式计算应计提坏账准备并与账面余额比较差异。

#### Acceptance Criteria

1. THE ECL_Calculation SHALL 渲染为双区块布局：(一)单项计提坏账准备 + (二)账龄组合计提坏账准备（支持多组合） + 合计
2. THE ECL_Calculation "(一)单项计提"区块 SHALL 以el-table显示列：债务人名称 | 审定账面余额① | 预期信用损失率② | 期末应计提坏账准备③=①×② | 期末坏账准备账面余额④ | 差异⑤=③-④ | 计提依据及文件 | 索引号
3. THE Formula_Engine SHALL 自动计算单项计提每行：应计提③=审定余额①×损失率②；差异⑤=应计提③-账面余额④
4. THE ECL_Calculation "(二)账龄组合"区块 SHALL 支持多组合（如业务类型组合/客户类型组合），每组合独立子表：账龄 | 审定账面余额① | 预期信用损失率② | 期末应计提坏账准备③=①×② | 期末坏账准备账面余额④ | 差异⑤=③-④
5. THE ECL_Calculation 每个账龄组合 SHALL 显示固定账龄段行：1年以内/1年-2年/2年-3年/3年-4年/4年-5年/5年以上/小计
6. WHEN 用户点击"添加组合"按钮时, THE ECL_Calculation SHALL 新增一个空的账龄组合子表（含6个账龄段行+小计行）
7. THE ECL_Calculation SHALL 在底部显示合计行：合计应计提=单项合计+各组合合计；合计账面=单项账面合计+各组合账面合计；总差异=合计应计提-合计账面
8. WHEN 总差异不为零时, THE ECL_Calculation SHALL 以黄色el-alert显示"应计提坏账准备与账面余额存在差异，差额：±xxx元，需关注是否需要调整"
9. THE ECL_Calculation SHALL 在单项计提区块支持"添加债务人"按钮新增动态行
10. THE ECL_Calculation SHALL 在底部显示"审计说明"textarea（AI生成按钮，评价ECL模型参数合理性+损失率选取依据+前瞻性调整）和"审计结论"textarea
11. THE ECL_Calculation SHALL 在审计说明/结论区域放置复核对话入口（💬图标），复核重点为损失率选取合理性
12. THE ECL_Calculation SHALL 提供GtIndexChip跳转D6-7会计政策检查（验证损失率与政策一致性）和D6-3减值准备明细（核对账面余额）

### Requirement 14: 减值准备转回核销检查D6-9 HTML渲染（双段）

**User Story:** As a 审计助理, I want to 在精美HTML组件中记录合同资产减值准备的转回和核销检查, so that 我能逐笔审核转回合理性和核销程序合规性。

#### Acceptance Criteria

1. THE Writeoff_Check SHALL 渲染为双段结构：(一)本期重要的减值准备转回检查 + (二)核销的合同资产检查
2. THE Writeoff_Check "(一)转回检查"区块 SHALL 显示8列：客户名称 | 转回原因 | 收回方式 | 原确定减值准备的依据 | 转回金额 | 转销前累计已计提坏账准备金额 | 合理性分析 | 索引号
3. THE Writeoff_Check "(二)核销检查"区块 SHALL 显示8列：客户名称 | 核销金额 | 核销原因 | 履行的核销程序 | 是否由关联交易产生 | 合理性分析 | 索引号 | 备注
4. WHEN 用户点击"添加转回记录"或"添加核销记录"按钮时, THE Writeoff_Check SHALL 在对应区块新增一行可编辑空行
5. THE Writeoff_Check SHALL 在各区块底部显示合计行（转回金额合计/核销金额合计）
6. THE Writeoff_Check "(二)核销检查"区块 SHALL 对"是否由关联交易产生"列应用下拉选择（是/否），选"是"时橙色高亮该行
7. THE Writeoff_Check SHALL 在底部显示"审计说明"textarea（AI生成按钮，评价转回合理性+核销程序充分性）和"审计结论"textarea
8. THE Writeoff_Check SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
9. THE Writeoff_Check SHALL 在转回记录每行提供GtIndexChip跳转D6-3对应项目（验证转回后余额正确）

### Requirement 15: 附注披露信息（上市公司）HTML渲染（5子节163公式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑上市公司合同资产附注披露, so that 我能按5个子节结构核对附注数据并与审定表、减值测算自动取数对齐。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染为5子节卡片结构：(1)合同资产分类（项目/期末余额(账面余额/减值准备/账面价值)/上年年末余额(同结构)，子行：单项计提/按组合计提/其中各组合/小计/减:列示于其他非流动/合计）→ (2)合同资产减值准备计提情况（类别/期末余额(账面余额/比例%/减值准备金额/预期信用损失率%)/上年年末余额(同结构)，子行：按单项/按组合/合计）→ (3)按单项计提坏账准备明细（期末+上年年末续表：名称/账面余额/坏账准备/预期信用损失率%/计提理由）→ (4)按组合计提坏账准备明细（按组合分组：组合名→账龄/合同资产/坏账准备/预期信用损失率%，期末+上年）→ (5)本期计提、收回或转回（项目/本期计提/本期转回/本期转销核销/原因）
2. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table 三区块审定数自动取数填入附注第(1)子节对应行（原值→账面余额，坏账→减值准备，净值→账面价值）
3. THE Cross_Sheet_Engine SHALL 从 ECL_Calculation 自动取数填入附注第(2)(3)(4)子节（单项/各组合的余额和损失率）
4. THE Cross_Sheet_Engine SHALL 从 Impairment_Detail_Table 自动取数填入附注第(5)子节（计提/转回/核销变动金额）
5. WHILE 跨sheet引用值生效时, THE Disclosure_Listed SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
6. THE Disclosure_Listed SHALL 对第(3)子节（单项明细）和第(4)子节（组合明细）支持动态行添加/删除
7. THE Disclosure_Listed SHALL 对第(4)子节按组合分组显示（每个组合独立子表，组合名称为分组标题），支持添加新组合
8. THE Disclosure_Listed SHALL 自动计算各子节合计行和比例列（比例%=该类别金额/合计金额×100%）
9. THE Disclosure_Listed SHALL 在每个子节底部放置"说明"textarea（可编辑，双向回写附注模块，EventBus `disclosure:note-text-updated`）和编制提示折叠区（`<details>`默认收起）

### Requirement 16: 附注披露信息（国企）HTML渲染（3子节）

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑国企合同资产附注披露, so that 我能按3个子节核对附注数据。

#### Acceptance Criteria

1. THE Disclosure_SOE SHALL 渲染为3子节卡片结构：(1)合同资产情况（项目/期末数(账面余额/减值准备/账面价值)/期初数(同结构)）→ (2)合同资产减值准备（项目/期初数/本期变动(计提/转回/转销核销)/期末数/原因）→ (3)本期账面价值重大变动（项目/变动金额/变动原因）
2. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table 自动取数填入Disclosure_SOE第(1)子节对应行
3. THE Cross_Sheet_Engine SHALL 从 Impairment_Detail_Table 自动取数填入Disclosure_SOE第(2)子节对应行
4. WHILE 跨sheet引用值生效时, THE Disclosure_SOE SHALL 以浅蓝色背景标记自动取数单元格
5. THE Disclosure_SOE SHALL 对第(2)(3)子节支持动态添加/删除行
6. THE Disclosure_SOE SHALL 自动计算各子节合计行
7. THE Disclosure_SOE SHALL 在每个子节底部放置"说明"textarea（可编辑，双向回写附注模块）和编制提示折叠区

### Requirement 17: 附注适用性切换与双向回写

**User Story:** As a 审计助理, I want to 附注披露根据项目类型自动适配并与附注模块双向同步, so that 我无需在两处重复维护相同数据。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 根据项目applicable_standards（listed_standalone/listed_consolidated）自动显示
2. THE Disclosure_SOE SHALL 根据项目applicable_standards（soe_standalone/soe_consolidated）自动显示
3. WHEN 两种标准均不适用时, THE Disclosure_Listed 和 Disclosure_SOE SHALL 隐藏对应版本
4. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在同一Tab内通过el-segmented切换（"上市公司版" | "国企版"），不适用的版本隐藏
5. WHEN 附注"说明"textarea编辑后, THE Disclosure_Listed SHALL 通过EventBus发布'disclosure:note-text-updated'事件双向回写附注模块（payload含wpCode='D6'/section/text）
6. WHEN EventBus收到'note:section-updated'事件时, THE Disclosure_Listed SHALL 同步更新对应子节文本（last-write-wins冲突策略）
7. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在每个子节提供GtIndexChip，点击跳转至D6-1审定表对应数据来源行

### Requirement 18: 实质性程序表D6A 集成

**User Story:** As a 审计助理, I want to 程序表D6A集成到统一入口并联动各子sheet索引, so that 我能从程序表出发逐步执行审计步骤并跳转到对应底稿。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 复用 `a-program-console` componentType渲染审计程序+审计目标（存在/完整性/权利和义务/准确性计价分摊/列报）
2. THE Procedure_Table SHALL 在每步程序的"底稿索引号"列提供GtIndexChip，点击跳转至对应子sheet（D6-1/D6-2/D6-3/D6-5/D6-6/D6-7/D6-8/D6-9/D0/D4/A1-1/A1-15/A1-16）
3. THE Procedure_Table SHALL 特别标注涉及ECL减值测算的步骤，提供GtIndexChip跳转D6-7会计政策+D6-8测算
4. THE Procedure_Table SHALL 特别标注涉及函证程序的步骤，提供GtIndexChip跳转D0函证底稿
5. WHEN B50风险评估更新时, THE Procedure_Table SHALL 通过EventBus接收'risk:updated'事件并更新程序步骤状态标记
6. THE Procedure_Table SHALL selfLoad渲染数据（当htmlData prop为null时自行调render-config?force_component_type=a-program-console）

### Requirement 19: 跨底稿EventBus联动

**User Story:** As a 审计助理, I want to D6合同资产底稿与其他底稿自动联动, so that 审定数变化、调整分录、减值差异等信息能实时传递到相关底稿。

#### Acceptance Criteria

1. WHEN D6-1审定数变化时, THE Cross_Sheet_Engine SHALL 通过EventBus发布'substantive:adjudicated'事件回写trial_balance科目1402（payload含wpCode='D6'/accountCode='1402'/auditedAmount）
2. WHEN D6-4调整分录创建时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件联动A13错报汇总
3. WHEN EventBus收到'confirmation:completed'事件时（D0函证完成）, THE Detail_Table SHALL 自动将对应客户的"是否函证"列标Y
4. WHEN EventBus收到'risk:updated'事件时（B50风险评估更新）, THE Procedure_Table SHALL 更新程序步骤状态标记
5. THE Inspection_Table SHALL 与D4营业收入底稿进行期后结转交叉验证（合同资产结转 vs 收入确认），通过GtIndexChip跳转D4相关底稿
6. THE Cross_Sheet_Engine SHALL 支持接收D5应收款项融资底稿的SPPI业务模式判断事件（合同资产vs应收款项的区分联动）

### Requirement 20: GtIndexChip交叉索引

**User Story:** As a 审计助理, I want to 底稿各处有可点击的交叉索引芯片, so that 我能快速跳转到相关底稿查看关联信息。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在审计说明区域提供GtIndexChip跳转：D6-8（减值测算详情）、D6-3（减值明细）、D6-6（检查表）、D6-2（明细表）
2. THE ECL_Calculation SHALL 在每行提供GtIndexChip跳转：D6-7（政策一致性验证）、D6-3（核对账面余额）
3. THE Related_Party_Check SHALL 在每行提供GtIndexChip跳转：D6-2（明细行定位）
4. THE Inspection_Table SHALL 提供GtIndexChip跳转：D4（营业收入期后结转联动）、抽凭引擎（voucher-sampling-engine集成）
5. THE Writeoff_Check SHALL 在转回记录每行提供GtIndexChip跳转：D6-3（核对余额）
6. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在数据来源处提供GtIndexChip跳转：D6-1（审定数来源）、D6-8（测算来源）、D6-3（减值明细来源）
7. THE Procedure_Table SHALL 在每步程序索引号列提供GtIndexChip跳转：各子sheet（D6-1/D6-2/D6-3/D6-5/D6-6/D6-7/D6-8/D6-9/D0/D4/D5/A1-1/A1-15/A1-16）
8. WHEN 用户点击GtIndexChip时, THE Cross_Sheet_Engine SHALL 切换到目标Tab并高亮定位到目标行（如从D6-8跳转到D6-3的特定项目行）

### Requirement 21: 双模式切换与持久化

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换且所有编辑自动保存, so that 我不会因为意外关闭页面而丢失数据且能根据需要选择编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE D6 组件 SHALL 使用 checklist_responses 表存储所有sheet数据，item_id前缀为"D6-{sheetCode}-{field}"格式（如D6-1-adj-block1-row1-currentUnadjusted, D6-2-rows, D6-3-rows, D6-8-groups）
6. THE Dynamic_Row 类型sheet（D6-2/D6-3/D6-4/D6-5/D6-6/D6-8/D6-9）SHALL 以JSON数组格式存储动态行于remark字段
7. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
8. WHEN 用户切换结论/选择类字段时, THE Formula_Engine SHALL 立即保存该字段

### Requirement 22: 复核对话集成

**User Story:** As a 现场经理, I want to 在D6底稿任意位置发起和查看复核对话, so that 我能针对具体数据点与审计助理进行复核讨论。

#### Acceptance Criteria

1. THE 各sheet审计说明/结论区域 SHALL 固定放置复核对话入口按钮（💬图标），点击调用openReviewDialog（sectionId自动生成为`D6-{sheetCode}-note`）
2. THE 各sheet表格 SHALL 支持单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D6-{sheetCode}-{rowKey}-{field}`）
3. WHEN 有活跃复核线程时, THE 各sheet SHALL 在对应位置显示蓝色圆点（待回复）或红色圆点（有新回复）标记
4. THE 复核对话 SHALL 特别关注以下高风险区域（红色圆点优先级更高）：D6-8 ECL损失率选取合理性、D6-7会计政策一致性评价、D6-1净值=原值-坏账跨区块验证、D6-9核销程序合规性
5. THE 各sheet SHALL 通过inject方式获取openReviewDialog函数（由GtD6ContractAssets.vue在provide层统一注入）

### Requirement 23: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Adjudication_Table SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Detail_Table SHALL 对"合同名称/项目名称"列左对齐、对金额列右对齐
6. WHILE 数据正在加载时, THE D6 组件 SHALL 在表格区域显示el-skeleton占位动画
7. THE D6 组件 SHALL 统一使用displayPrefs.fmtDateTime格式化所有时间戳显示

### Requirement 24: 自动提取填充（TB取数）

**User Story:** As a 审计助理, I want to 审定表从试算平衡表自动获取数据, so that 期初/期末未审数不需要手工录入。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 通过auto_data_source resolver从trial_balance（科目1402）自动获取期初/期末未审数
2. WHILE TB数据尚未导入时, THE Adjudication_Table SHALL 在未审数单元格显示"待导入TB"灰色占位文字
3. THE Detail_Table SHALL 支持从tb_aux_balance（科目1402，按客户/合同维度）批量导入客户级明细数据
4. WHEN TB数据更新时, THE Cross_Sheet_Engine SHALL 自动刷新依赖TB的单元格值
5. THE ECL_Calculation SHALL 对"审定账面余额"列支持从D6-2期末审定数按信用风险组合自动取数
6. THE Impairment_Detail_Table SHALL 支持从tb_aux_balance（坏账准备科目，按客户维度）自动获取期初/期末未审余额

### Requirement 25: D6-2期后结转与D6-6联动

**User Story:** As a 审计助理, I want to D6-2明细表的"期后结转金额"列与D6-6检查表第二区块自动联动, so that 期后结转金额在两处保持一致。

#### Acceptance Criteria

1. WHEN D6-6"(2)期后贴现/背书/调整等检查"区块有新增样本且客户名称匹配D6-2行时, THE Detail_Table SHALL 自动将对应行的"期后结转金额"列累加该笔贷方金额
2. WHEN D6-2"期后结转金额"列手动编辑时, THE Inspection_Table SHALL 在"(2)期后贴现/背书/调整"区块显示黄色提示"D6-2已有期后结转金额xxx，请确认是否已录入对应凭证"
3. THE Detail_Table SHALL 在"期后结转金额"列的合计值与D6-6"(2)期后贴现/背书/调整"贷方金额合计进行交叉验证，不一致时黄色el-alert显示差额

### Requirement 26: 净值=原值-坏账跨区块联动

**User Story:** As a 审计助理, I want to 审定表三区块之间的净值=原值-坏账准备自动计算并实时校验, so that 跨区块数据始终保持一致。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在"三、合同资产净值"区块的每个动态行自动计算：净值期初审定=原值对应行期初审定-坏账准备对应行期初审定；净值期末审定=原值对应行期末审定-坏账准备对应行期末审定
2. THE Adjudication_Table SHALL 在"三、净值"区块的小计行自动计算：净值小计=原值小计-坏账准备小计
3. THE Adjudication_Table SHALL 在"三、净值"区块的"减：列示于其他非流动资产"行自动计算：净值非流动=原值非流动-坏账准备非流动
4. THE Adjudication_Table SHALL 在"三、净值"区块的净值合计行自动计算：净值合计=净值小计-净值非流动扣减
5. WHEN 区块一（原值）或区块二（坏账准备）的任意审定数发生变化时, THE Formula_Engine SHALL 在200ms内重新计算区块三（净值）所有相关行
6. IF 净值合计≠原值合计-坏账准备合计（浮点误差>0.01元）, THEN THE Adjudication_Table SHALL 在净值合计行以红色高亮并显示tooltip"净值校验不通过，请检查跨区块数据"

### Requirement 27: ECL测算→D6-3→D6-1联动链

**User Story:** As a 审计助理, I want to ECL减值测算结果自动传导到减值准备明细再传导到审定表坏账区块, so that 减值准备的计算链路完整闭环。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 ECL_Calculation 的"期末应计提坏账准备"合计自动填入 Impairment_Detail_Table 的期末应计提参考值（用于对比，不直接覆盖账面余额）
2. THE Cross_Sheet_Engine SHALL 从 Impairment_Detail_Table 按分类聚合期末审定余额填入 Adjudication_Table "二、坏账准备"区块对应行
3. WHEN ECL_Calculation 数据变更时, THE Cross_Sheet_Engine SHALL 通过computed链自动刷新 Impairment_Detail_Table 的参考值列和 Adjudication_Table 的坏账区块
4. THE ECL_Calculation SHALL 在差异列不为零时，提供GtIndexChip跳转 Impairment_Detail_Table 对应行（便于核查差异原因）
5. THE Impairment_Detail_Table SHALL 在核对行显示：D6-3合计 vs D6-1坏账区块合计 vs D6-8应计提合计，三方核对不一致时分别标注黄色差异提示

### Requirement 28: 后端Render策略与Resolver注册

**User Story:** As a 开发者, I want to D6底稿的后端渲染策略和auto_data resolver正确注册, so that render-config API能返回正确数据且TB自动取数功能正常工作。

#### Acceptance Criteria

1. THE RENDERER_DISPATCH SHALL 注册'd6-contract-assets' componentType对应的render策略函数`_render_d6_contract_assets`
2. THE render策略函数 SHALL 返回包含审定表三区块结构+明细表行数据+减值准备明细+ECL测算组合数据+各sheet配置的完整html_data
3. THE auto_data_resolvers._REGISTRY SHALL 注册`d6_tb_unadjusted` resolver（从trial_balance科目1402取期初/期末未审数）
4. THE auto_data_resolvers._REGISTRY SHALL 注册`d6_impairment_tb` resolver（从trial_balance坏账准备相关科目取期初/期末未审数）
5. THE account_package_registry.json SHALL 包含D6_contract_assets工作包定义（含sheets清单对齐源模板12个有效sheet：D6A/D6-1/D6-2/D6-3/D6-4/D6-5/D6-6/D6-7/D6-8/D6-9/附注上市/附注国企）
6. THE render策略函数 SHALL 读取D6.yaml render schema中的fixed_cells和dynamic_table配置生成初始结构化数据

