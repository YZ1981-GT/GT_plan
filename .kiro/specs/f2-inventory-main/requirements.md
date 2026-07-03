# Requirements Document

## Introduction

F2存货底稿核心组的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f2-inventory-main`，覆盖4个xlsx源模板/35个有效sheet（程序表F2A + 审定表F2-1 + 附注披露×2 + 明细汇总F2-2 + 原材料~消耗性生物资产明细F2-3~F2-13 + 调整分录F2-14 + 会计政策F2-16 + 总体分析F2-18 + 产销量变动F2-19 + 成本比较F2-20 + 截止测试F2-29~F2-32 + 采购入库检查F2-33 + 材料领用检查F2-34 + 委托加工核查F2-35），合计约500+公式。科目编码1401~1412存货（借方科目/资产类）。

**源模板sheet清单（openpyxl实读确认）**：

### File 1: F2-1至F2-14（20 sheets，有效18个）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 修订说明 | - | skip |
| 2 | 底稿目录 | - | skip |
| 3 | **存货实质性程序表F2A** | 53×14 | 程序表（复用a-program-console） |
| 4 | **存货审定表F2-1** | 148×11 | **三大块**：原值(13类别×3行)+跌价准备(同结构)+净值 |
| 5 | **附注披露(上市)** | 88×14 | 上市公司版附注 |
| 6 | **附注披露(国企)** | 47×8 | 国企版附注 |
| 7 | **明细汇总表F2-2** | 76×17 | 各类别存货汇总 |
| 8 | **原材料明细表F2-3** | 51×21 | 期初+增加+减少+期末+库龄4段 |
| 9 | **材料采购在途F2-4** | 70×23 | 在途物资明细 |
| 10 | **周转材料F2-5** | 69×21 | 低值易耗品/包装物 |
| 11 | **自制半成品F2-6** | 70×21 | 半成品明细 |
| 12 | **委托加工F2-7** | 287×15 | 最多行，委托加工物资 |
| 13 | **库存商品F2-8** | 71×24 | 产成品明细 |
| 14 | **发出商品F2-9** | 73×23 | 发出未确认收入 |
| 15 | **开发产品F2-10** | 95×35 | 最宽，房地产开发 |
| 16 | **开发成本F2-11** | 52×24 | 开发中项目 |
| 17 | **合同履约成本F2-12** | 27×16 | CAS14合同成本 |
| 18 | **消耗性生物资产F2-13** | 79×22 | 农业存货 |
| 19 | **调整分录F2-14** | 23×10 | 标准AJE/RJE |
| 20 | GT_Custom | - | skip |

### File 2: F2-16 会计政策（1 sheet）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **会计政策核算流程F2-16** | 42×10 | 存货计量/核算/跌价政策 |

### File 3: F2-18至F2-20 分析类（3 sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **存货总体分析表F2-18** | 78×12 | 结构/周转/趋势分析 |
| 2 | **存货产销量变动分析表F2-19** | 104×17 | 产量/销量/库存变动 |
| 3 | **产品年度成本比较分析F2-20** | 22×19 | 单位成本同比 |

### File 4: F2-29至F2-35 检查类（7 sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **截止测试-入库(正向)F2-29** | 57×15 | 入库截止正向 |
| 2 | **截止测试-入库(反向)F2-30** | 57×15 | 入库截止反向 |
| 3 | **截止测试-出库(正向)F2-31** | 51×10 | 出库截止正向 |
| 4 | **截止测试-出库(反向)F2-32** | 51×10 | 出库截止反向 |
| 5 | **存货采购入库检查表F2-33** | 43×22 | 大额采购凭证核对 |
| 6 | **材料领用检查表F2-34** | 37×15 | 领用出库凭证核对 |
| 7 | **委托加工物资核查表F2-35** | 41×9 | 委托加工完整性核查 |

**宽表处理策略**：
- F2-3~F2-13明细表(21-35列)：拆为区段Tab（期初/本期增加/本期减少/期末/库龄），每区段5-8列
- F2-10开发产品(35列最宽)：拆为5区段Tab（基础/土地/建安/资本化利息/其他+结转）
- F2-33采购入库检查(22列)：固定凭证列+滚动证据列
- F2-19产销量变动(17列)：拆为产量变动+销量变动+库存变动3区段

核心特色：审定表三大块结构（原值/跌价准备/净值）含13类别存货、11张明细表共享区段Tab模式（期初+增加+减少+期末+库龄）、7张检查表固定列+滚动列、跨sheet净值=原值-跌价三表联动。F循环最大科目底稿（35 sheet）。架构采用sheetName prop + v-if分发（>20个sheet不用el-tabs），子目录按功能分组（core/detail/analysis/inspection）。

## Glossary

- **Adjudication_Table**: 审定表F2-1，三大块结构（一原值/二跌价准备/三净值），148行×11列，每块13类别×3行(未审/账项调整/审定)，核心公式：净值审定=原值审定-跌价审定
- **Detail_Summary**: 明细汇总表F2-2，各类别存货期初/增加/减少/期末汇总，来源于F2-3~F2-13明细表聚合
- **Detail_Tables**: F2-3~F2-13共11张明细表，每张结构相似：期初(数量/单价/金额)+本期增加(同)+本期减少(同)+期末(同)+库龄(1年以内/1-2年/2-3年/3年以上)
- **Adjustment_Table**: 调整分录F2-14，标准AJE/RJE格式（10列×23行）
- **Policy_Table**: 会计政策核算流程F2-16，存货计量方法/发出计价/跌价政策核查
- **Overall_Analysis**: 存货总体分析表F2-18，结构分析/周转分析/趋势分析/异常识别
- **Production_Sales_Analysis**: 产销量变动分析F2-19，产量/销量/库存三维变动对比
- **Cost_Comparison**: 产品年度成本比较F2-20，单位成本同比分析
- **Cutoff_Test**: 截止测试F2-29~F2-32，入库/出库×正向/反向=4张表
- **Purchase_Inspection**: 存货采购入库检查表F2-33，大额采购凭证核对（22列）
- **Material_Usage_Check**: 材料领用检查表F2-34，领用出库凭证核对（15列）
- **Subcontracting_Check**: 委托加工物资核查表F2-35，外协加工完整性
- **Formula_Engine**: 前端公式引擎composable，存货核心公式：期末=期初+增加-减少；净值=原值-跌价准备；审定=未审+AJE；库龄合计=Σ各段
- **Cross_Sheet_Engine**: 跨sheet联动，F2-3~F2-13→F2-2汇总→F2-1审定→TB回写
- **Category_13**: 13类别存货（原材料/材料采购在途/周转材料/自制半成品/委托加工/库存商品/发出商品/开发产品/开发成本/合同履约成本/消耗性生物资产/商品进销差价/存货跌价准备）
- **Segment_Tab**: 区段Tab宽表拆分模式，>15列表横向拆为多区段Tab，行保持同步
- **Net_Value_Formula**: 净值=原值-跌价准备，三大块核心联动公式
- **Aging_4_Segments**: 库龄4段分析（1年以内/1-2年/2-3年/3年以上），每张明细表末尾4列
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片
- **Collapsible_Section**: 可折叠el-card区域，审定表三大块用折叠面板组织

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F2存货核心组底稿按sheetName prop分发到独立子组件, so that 35个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F2 组件 SHALL 注册新componentType: `f2-inventory-main`，主入口为 GtF2InventoryMain.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F2 组件 SHALL 将sheet按功能分为4个子目录：core/（F2A+F2-1+F2-2+F2-14+附注×2）、detail/（F2-3~F2-13共11张明细表）、analysis/（F2-16+F2-18+F2-19+F2-20）、inspection/（F2-29~F2-35共7张检查表）
1.3 THE F2 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（35个sheet按需加载）
1.4 THE useF2FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：期末=期初+增加-减少、净值=原值-跌价准备、审定=未审+AJE、库龄合计=Σ各段、合计行SUM、变动率、周转率、检查比例
1.5 THE F2 组件 SHALL 在htmlRendererRegistry中注册'f2-inventory-main'→GtF2InventoryMain映射
1.6 THE F2 组件 SHALL 在wp_code_overrides.json中将F2/F2-1~F2-14/F2-16/F2-18~F2-20/F2-29~F2-35的componentType统一映射为'f2-inventory-main'（约30个wp_code）
1.7 THE F2 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f2-inventory-main'
1.8 THE GtF2InventoryMain.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f2-inventory-main）
1.9 THE GtF2InventoryMain.vue SHALL 用正则从sheetName提取末尾编码(F2-1/F2-3等)，匹配失败走OnlyOffice fallback

### Requirement 2: 审定表F2-1 HTML渲染（三大块：原值/跌价准备/净值）

**User Story:** As a 审计助理, I want to 在精美HTML中查看和编辑存货审定表三大块结构, so that 我能清晰地看到13类别存货的原值、跌价准备、净值及其勾稽关系。

#### Acceptance Criteria

2.1 THE Adjudication_Table SHALL 渲染为三个可折叠el-card区域（对齐xlsx 148行实际结构）：
   - **一、存货原值**：13类别×3行(未审数/账项调整/审定数) + 合计行，列=项目|期初数|本期增加|本期减少|期末数|索引
   - **二、存货跌价准备**：13类别×3行(同结构) + 合计行，列=同上
   - **三、存货净值**：13类别审定净值行 + 合计行（净值=原值审定-跌价审定，只读计算列）
   - 底部：试算平衡表数 + 差异数 + 审计说明 + 审计结论
2.2 THE Adjudication_Table 每个类别块 SHALL 显示以下列：项目 | 期初数 | 本期增加 | 本期减少 | 期末数 | 索引（共6列×3行per类别）
2.3 WHEN 用户编辑未审数或账项调整时, THE Formula_Engine SHALL 自动计算审定数（= 未审数 + 账项调整）
2.4 THE Formula_Engine SHALL 自动计算每个类别：期末数 = 期初数 + 本期增加 - 本期减少
2.5 THE Formula_Engine SHALL 自动计算净值区域：各类别净值 = 对应原值审定行期末数 - 对应跌价准备审定行期末数
2.6 THE Adjudication_Table SHALL 在底部显示试算平衡表数行（自动取数存货科目组1401~1412）和差异行（=合计审定数-试算表数），差异不为零时红色高亮
2.7 THE Adjudication_Table SHALL 对索引列应用GtIndexChip渲染（跳转到对应明细表）
2.8 THE Adjudication_Table SHALL 底部"审计说明"（textarea+AI按钮）+"审计结论"（textarea+AI按钮）两个文本区域
2.9 THE 三个区域（原值/跌价/净值）SHALL 支持折叠/展开切换（默认展开），净值区域可设为默认折叠
2.10 THE Adjudication_Table SHALL 净值合计=原值合计-跌价合计，不一致时红色警告

### Requirement 3: 审定表F2-1 跨Sheet联动与回写

**User Story:** As a 审计助理, I want to 审定表自动从11张明细表聚合数据并回写TB, so that 13类别存货数据自动同步、减少手工汇总错误。

#### Acceptance Criteria

3.1 THE Cross_Sheet_Engine SHALL 从 Detail_Tables(F2-3~F2-13) 按类别聚合各明细表合计行的期初/增加/减少/期末金额填入 Adjudication_Table 原值区对应类别的未审数行
3.2 THE Cross_Sheet_Engine SHALL 从 Adjustment_Table(F2-14) 自动获取存货相关调整分录的AJE合计填入审定表对应列
3.3 THE Cross_Sheet_Engine SHALL 从 Detail_Summary(F2-2) 获取跌价准备各类别金额填入跌价准备区对应行
3.4 THE Cross_Sheet_Engine SHALL 监听任一明细表(F2-3~F2-13)数据变更 → 自动重新聚合 → 更新审定表未审数行
3.5 THE Cross_Sheet_Engine SHALL 监听调整分录(F2-14)数据变更 → 自动更新审定表AJE行
3.6 THE Adjudication_Table SHALL 实现 EventBus `publishAdjudicated`（发布 'substantive:adjudicated' 事件，payload含 wpCode='F2'/accountCodes=['1401','1402',...'1412']/auditedAmounts/priorAmounts）
3.7 THE Adjudication_Table SHALL 实现 EventBus 监听 `adjustment:created`（AJE → 累加对应列）
3.8 THE Adjudication_Table SHALL 实现 `writebackTrialBalance`（回写 trial_balance.audited_amount 存货科目组1401~1412，按类别映射）
3.9 THE Cross_Sheet_Engine SHALL 提供手动覆盖功能（用户可手动编辑聚合值，覆盖标记为"手动"）
3.10 THE Cross_Sheet_Engine SHALL 净值自动联动：原值或跌价任一变更 → 自动重算净值区全部行

### Requirement 4: 明细汇总表F2-2 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中查看各类别存货的汇总情况, so that 我能快速了解各类存货的增减变动全貌。

#### Acceptance Criteria

4.1 THE Detail_Summary SHALL 显示17列（对齐xlsx）：类别 | 期初数量 | 期初单价 | 期初金额 | 本期增加数量 | 本期增加单价 | 本期增加金额 | 本期减少数量 | 本期减少单价 | 本期减少金额 | 期末数量 | 期末单价 | 期末金额 | 库龄1年以内 | 库龄1-2年 | 库龄2-3年 | 库龄3年以上
4.2 THE Detail_Summary SHALL 自动从F2-3~F2-13各明细表合计行聚合数据（每张明细表→一行汇总）
4.3 THE Detail_Summary SHALL 底部合计行 = SUM各类别行
4.4 THE Formula_Engine SHALL 自动计算期末金额 = 期初金额 + 本期增加金额 - 本期减少金额
4.5 THE Detail_Summary SHALL 库龄合计 = Σ(1年以内 + 1-2年 + 2-3年 + 3年以上)，不等于期末金额时橙色高亮
4.6 THE Detail_Summary SHALL 支持点击类别行跳转到对应明细表（GtIndexChip）
4.7 THE Detail_Summary SHALL 为只读表（数据来自明细表聚合，不可直接编辑）

### Requirement 5: 明细表F2-3~F2-13 通用HTML渲染（区段Tab模式）

**User Story:** As a 审计助理, I want to 在精美HTML中管理各类存货明细数据, so that 我能按品目跟踪存货的收发存及库龄，且宽表不需要大范围横滚。

**设计决策：通用明细表组件** — F2-3~F2-13共11张表结构高度相似（期初+增加+减少+期末+库龄），使用通用子组件F2DetailSheet.vue + 配置参数区分差异列。

#### Acceptance Criteria

5.1 THE Detail_Tables SHALL 使用通用组件F2DetailSheet.vue，通过config prop区分11张表的差异列（F2-10开发产品35列需额外config）
5.2 THE 通用明细结构 SHALL 拆为区段Tab呈现（每区段≤8列）：
   - **期初**：品名/规格/数量/单价/金额（5列）
   - **本期增加**：数量/单价/金额（3列）
   - **本期减少**：数量/单价/金额（3列）
   - **期末**：数量/单价/金额（3列）
   - **库龄**：1年以内/1-2年/2-3年/3年以上（4列）
5.3 THE Formula_Engine SHALL 自动计算：期末数量 = 期初数量 + 增加数量 - 减少数量
5.4 THE Formula_Engine SHALL 自动计算：期末金额 = 期初金额 + 增加金额 - 减少金额
5.5 THE Formula_Engine SHALL 自动计算：单价 = 金额/数量（数量=0时显示'-'）
5.6 THE Detail_Tables SHALL 底部合计行 = SUM各明细行（金额列SUM，单价列=合计金额/合计数量）
5.7 THE Detail_Tables SHALL 库龄合计（Σ4段） = 期末金额，不一致时橙色高亮
5.8 THE Detail_Tables SHALL 支持动态行增删（在合计行上方新增/删除品目行）
5.9 WHEN 新增动态行时, THE 系统 SHALL 弹出ElMessageBox.prompt要求输入品名后再创建行
5.10 THE Detail_Tables SHALL 支持按品名搜索筛选
5.11 THE Detail_Tables SHALL 区段间保持行同步（切换区段不丢失当前行位置）
5.12 THE Detail_Tables SHALL 支持导入导出（导出完整列Excel模板）
5.13 WHEN 库龄"3年以上"列有值时, THE Detail_Tables SHALL 以橙色背景高亮该行（长期积压风险）
5.14 THE F2-10开发产品(35列) SHALL 拆为5区段Tab（基础信息/土地成本/建安成本/资本化利息/其他+结转），每区段6-8列
5.15 THE F2-7委托加工(287行) SHALL 启用虚拟滚动（行数>100时自动开启）

### Requirement 6: 调整分录F2-14 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中录入存货审计调整分录, so that AJE自动联动审定表。

#### Acceptance Criteria

6.1 THE Adjustment_Table SHALL 显示10列（对齐xlsx）：序号 | 调整事项说明 | 科目编码 | 科目名称 | 借方金额 | 贷方金额 | 分录类型(AJE/RJE) | 索引 | 备注 | 附注项目
6.2 THE Adjustment_Table SHALL 对科目名称列应用下拉选择（存货科目组1401~1412+相关对方科目）
6.3 THE Adjustment_Table SHALL 对索引列应用GtIndexChip渲染
6.4 THE Formula_Engine SHALL 自动计算借方合计和贷方合计，显示在底部合计行
6.5 WHEN 借方合计≠贷方合计时, THE Adjustment_Table SHALL 以红色高亮合计行并提示"借贷不平衡"
6.6 THE Adjustment_Table SHALL 支持动态行增删
6.7 THE Adjustment_Table SHALL 实现EventBus发布 `adjustment:created`（新增/修改调整分录时）
6.8 THE Adjustment_Table SHALL 支持与A2调整分录总表的数据联动

### Requirement 7: 会计政策核算流程F2-16 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中核查存货会计政策, so that 我能确认计量方法、发出计价、跌价政策的一致性和恰当性。

#### Acceptance Criteria

7.1 THE Policy_Table SHALL 分为结构化检查区域（对齐xlsx 42行×10列）：存货分类与确认/初始计量方法/发出存货计价方法/存货跌价准备计提政策/存货盘点制度
7.2 THE 每个区域 SHALL 包含：政策描述(textarea) | 是否变更(下拉：是/否) | 变更原因(textarea) | 审计评价(textarea) | 索引
7.3 WHEN 是否变更选择"是"时, THE Policy_Table SHALL 展开变更原因和影响评估字段
7.4 THE Policy_Table SHALL 提供与上年政策的对比功能（高亮变更项）
7.5 THE Policy_Table SHALL 底部"政策评价结论"textarea（支持AI生成）
7.6 THE Policy_Table SHALL 对索引列应用GtIndexChip渲染

### Requirement 8: 存货总体分析表F2-18 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中进行存货总体分析, so that 我能识别存货结构异常、周转下降、库龄集中等风险。

#### Acceptance Criteria

8.1 THE Overall_Analysis SHALL 分为四个区块（对齐xlsx 78行×12列）：结构分析 | 周转分析 | 趋势分析 | 异常识别
8.2 THE 结构分析区块 SHALL 显示各类别存货占总存货比例（本期 vs 上期），比例变动>5%高亮
8.3 THE 周转分析区块 SHALL 计算存货周转率（= 营业成本/平均存货余额）、周转天数、与行业比较
8.4 THE 趋势分析区块 SHALL 显示近3年存货余额趋势及同比增长率
8.5 THE 异常识别区块 SHALL 自动标记：周转率下降>20%/库龄3年以上占比>10%/存货增长率远超收入增长率
8.6 THE Overall_Analysis SHALL 支持图表可视化（结构饼图/趋势折线图/周转柱状图）
8.7 THE Overall_Analysis SHALL 底部"分析结论"textarea（支持AI生成）
8.8 THE Overall_Analysis SHALL 从F2-1审定表和F2-2汇总表自动取数

### Requirement 9: 产销量变动分析F2-19 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析产销量变动, so that 我能理解产量/销量/库存三者的匹配关系。

#### Acceptance Criteria

9.1 THE Production_Sales_Analysis SHALL 拆为3区段Tab（17列→3区段）：产量变动 | 销量变动 | 库存变动
9.2 THE 产量变动区段 SHALL 显示：产品名称/本期产量/上期产量/变动量/变动率/产能利用率
9.3 THE 销量变动区段 SHALL 显示：产品名称/本期销量/上期销量/变动量/变动率/市场占有率
9.4 THE 库存变动区段 SHALL 显示：产品名称/期初库存/本期入库/本期出库/期末库存/产销率
9.5 THE Formula_Engine SHALL 计算产销率 = 销量/产量×100%
9.6 THE Formula_Engine SHALL 计算库存变动 = 期初 + 入库 - 出库 = 期末（不等时红色高亮）
9.7 WHEN 产销率<80%时, THE 系统 SHALL 以橙色高亮该行（滞销风险）
9.8 THE Production_Sales_Analysis SHALL 支持动态行增删（产品维度）
9.9 THE Production_Sales_Analysis SHALL 底部合计行 + 分析结论textarea（AI辅助）

### Requirement 10: 产品年度成本比较F2-20 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中比较产品年度单位成本, so that 我能识别成本异常波动。

#### Acceptance Criteria

10.1 THE Cost_Comparison SHALL 显示19列（对齐xlsx）：产品名称 | 本期产量 | 本期单位成本(材料/人工/制造/合计) | 上期产量 | 上期单位成本(同4列) | 变动额(4列) | 变动率(4列) | 异常说明
10.2 THE Cost_Comparison SHALL 拆为2区段Tab（本期成本/上期成本+变动分析）
10.3 THE Formula_Engine SHALL 计算单位成本合计 = 材料 + 人工 + 制造费用
10.4 THE Formula_Engine SHALL 计算变动额 = 本期 - 上期；变动率 = (本期-上期)/上期
10.5 WHEN 变动率绝对值>20%时, THE 系统 SHALL 以红色高亮并要求填写异常说明
10.6 THE Cost_Comparison SHALL 支持动态行增删（产品维度）
10.7 THE Cost_Comparison SHALL 底部异常汇总 + AI辅助生成异常说明

### Requirement 11: 截止测试F2-29~F2-32 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中执行存货截止测试, so that 我能验证期末存货入库/出库的截止是否正确。

#### Acceptance Criteria

11.1 THE Cutoff_Test SHALL 使用通用组件F2CutoffSheet.vue，通过config prop区分4张表（入库正向/入库反向/出库正向/出库反向）
11.2 THE 入库截止(F2-29/F2-30) SHALL 显示15列：序号 | 供应商 | 入库单号 | 入库日期 | 品名 | 数量 | 金额 | 记账凭证号 | 记账日期 | 是否跨期 | 应归属期间 | 入账期间 | 截止是否正确 | 调整建议 | 备注
11.3 THE 出库截止(F2-31/F2-32) SHALL 显示10列：序号 | 领用部门 | 出库单号 | 出库日期 | 品名 | 数量 | 金额 | 记账日期 | 截止是否正确 | 备注
11.4 THE Formula_Engine SHALL 自动判断是否跨期（入库日期 vs 记账日期 vs 会计期末）
11.5 WHEN 截止不正确时, THE Cutoff_Test SHALL 以红色高亮该行
11.6 THE Cutoff_Test SHALL 底部"截止测试结论"textarea（AI辅助）
11.7 THE Cutoff_Test SHALL 支持动态行增删
11.8 THE Cutoff_Test SHALL 底部汇总：截止正确笔数/截止错误笔数/涉及金额

### Requirement 12: 存货采购入库检查F2-33 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中检查大额采购入库凭证, so that 我能核对采购真实性和完整性。

#### Acceptance Criteria

12.1 THE Purchase_Inspection SHALL 显示22列（固定列+滚动列模式）：
   - 固定列（7列）：序号/供应商名称/日期/凭证编号/业务摘要/借方科目/金额
   - 滚动列（15列）：采购订单号/采购订单日期/采购订单金额/入库单号/入库日期/入库数量/入库金额/采购发票号/发票日期/发票金额/付款凭证号/付款日期/付款金额/索引号/检查结论
12.2 THE Purchase_Inspection SHALL 底部合计行（金额列SUM）
12.3 THE Purchase_Inspection SHALL 底部"检查比例"显示（= 检查金额/账面金额×100%）
12.4 WHEN 检查比例<50%时, THE 系统 SHALL 橙色提示"应扩大样本量"
12.5 THE Purchase_Inspection SHALL 支持动态行增删
12.6 THE Purchase_Inspection SHALL 支持行级OCR上传（📎列复用OCR端点）
12.7 THE Purchase_Inspection SHALL 底部审计说明 + 审计结论textarea
12.8 THE Purchase_Inspection SHALL 支持导入导出

### Requirement 13: 材料领用检查F2-34 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中检查材料领用出库, so that 我能验证领用的真实性和用途合理性。

#### Acceptance Criteria

13.1 THE Material_Usage_Check SHALL 显示15列：序号 | 领用部门 | 日期 | 凭证编号 | 材料名称 | 规格 | 数量 | 单价 | 金额 | 用途 | 领用单号 | 审批人 | 是否合理 | 索引号 | 备注
13.2 THE Material_Usage_Check SHALL 对用途列应用下拉（生产/研发/维修/办公/其他）
13.3 THE Material_Usage_Check SHALL 对是否合理列应用下拉（合理/不合理/存疑）
13.4 WHEN 是否合理为"不合理"或"存疑"时, THE 系统 SHALL 以橙色高亮该行
13.5 THE Material_Usage_Check SHALL 底部合计行 + 检查比例 + 审计说明textarea
13.6 THE Material_Usage_Check SHALL 支持动态行增删
13.7 THE Material_Usage_Check SHALL 支持导入导出

### Requirement 14: 委托加工物资核查F2-35 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中核查委托加工物资, so that 我能验证外协加工的完整性和真实性。

#### Acceptance Criteria

14.1 THE Subcontracting_Check SHALL 显示9列：序号 | 加工单位 | 委托日期 | 材料名称 | 发出数量 | 发出金额 | 收回日期 | 收回数量 | 加工费 | 备注
14.2 THE Subcontracting_Check SHALL 自动计算在外天数（= 收回日期 - 委托日期，未收回显示"在外N天"）
14.3 WHEN 在外天数>180天时, THE 系统 SHALL 以橙色高亮该行（长期未收回风险）
14.4 THE Subcontracting_Check SHALL 底部合计行（发出金额SUM/加工费SUM）
14.5 THE Subcontracting_Check SHALL 底部审计说明textarea
14.6 THE Subcontracting_Check SHALL 支持动态行增删
14.7 THE Subcontracting_Check SHALL 支持导入导出

### Requirement 15: 附注披露HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中编辑存货附注披露, so that 披露信息完整准确。

#### Acceptance Criteria

15.1 THE Disclosure SHALL 支持上市公司版(88行×14列)和国企版(47行×8列)切换
15.2 THE 上市公司版 SHALL 显示：存货分类明细表（类别/期末账面余额/跌价准备/账面价值/期初同）+ 库龄分析表 + 跌价准备变动表(期初/本期计提/本期转回/本期转销/期末)
15.3 THE 国企版 SHALL 显示简化版：存货分类表 + 跌价准备情况
15.4 THE Disclosure SHALL 从审定表F2-1自动取数（原值/跌价/净值）
15.5 THE Disclosure SHALL 从明细表自动取数库龄分布
15.6 THE Formula_Engine SHALL 自动计算占比、账面价值=账面余额-跌价准备
15.7 THE Disclosure SHALL 支持导出为审计报告附注格式

### Requirement 16: 导入导出功能

**User Story:** As a 审计助理, I want to 支持Excel导入导出, so that 我能离线填写明细后导入系统。

#### Acceptance Criteria

16.1 THE Import_Export SHALL 使用useF2ImportExport composable统一管理（后端三端点）
16.2 THE Import_Export SHALL 对以下动态行表格支持导入导出：F2-3~F2-13明细表(11张)/F2-14调整分录/F2-19产销量/F2-20成本比较/F2-29~F2-35检查表(7张)
16.3 THE Import_Export SHALL 导出空模板含填写说明sheet + 数据校验规则
16.4 THE Import_Export SHALL 导入时进行数据验证（日期/金额/必填字段/库龄合计校验）
16.5 THE Import_Export SHALL 导入失败时显示详细错误信息（行号/字段/原因）
16.6 THE Import_Export SHALL StreamingResponse中文文件名RFC5987编码

### Requirement 17: 双模式切换

**User Story:** As a 审计助理, I want to 支持HTML与OnlyOffice模式切换, so that 复杂场景可降级到Excel编辑。

#### Acceptance Criteria

17.1 THE Dual_Mode SHALL 在每个sheet子组件右上角显示"切换到OnlyOffice"按钮
17.2 WHEN 用户点击切换按钮时, THE 系统 SHALL 切换到OnlyOffice编辑当前sheet
17.3 THE Dual_Mode SHALL OnlyOffice模式隐藏非目标sheet tab
17.4 THE Dual_Mode SHALL 切换回HTML时重新渲染Vue组件并同步数据
17.5 THE Dual_Mode SHALL 记住用户选择（localStorage持久化）
17.6 WHEN OnlyOffice加载失败时, THE 系统 SHALL 自动降级到HTML模式并显示提示
17.7 THE Dual_Mode SHALL OnlyOffice sheet名必须与源xlsx tab名完全一致

### Requirement 18: 共享公式引擎

**User Story:** As a 开发者, I want to 纯函数公式引擎易于测试, so that 500+公式清晰无副作用可PBT验证。

#### Acceptance Criteria

18.1 THE Formula_Engine SHALL 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
18.2 THE Formula_Engine SHALL 实现 `calcEndBalance`（期末 = 期初 + 增加 - 减少）
18.3 THE Formula_Engine SHALL 实现 `calcNetValue`（净值 = 原值 - 跌价准备）
18.4 THE Formula_Engine SHALL 实现 `calcAuditedAmount`（审定 = 未审 + AJE）
18.5 THE Formula_Engine SHALL 实现 `calcUnitPrice`（单价 = 金额/数量，数量=0→'-'）
18.6 THE Formula_Engine SHALL 实现 `calcAgingTotal`（库龄合计 = Σ4段）
18.7 THE Formula_Engine SHALL 实现 `calcSubtotal`（合计 = SUM数组）
18.8 THE Formula_Engine SHALL 实现 `calcChangeRate`（变动率：同F1规则）
18.9 THE Formula_Engine SHALL 实现 `calcTurnoverRate`（周转率 = 营业成本/平均存货余额）
18.10 THE Formula_Engine SHALL 实现 `calcCoverageRatio`（检查比例 = 检查金额/账面金额）
18.11 THE Formula_Engine SHALL 实现 `calcProductionSalesRate`（产销率 = 销量/产量×100%）
18.12 THE Formula_Engine SHALL 实现 `calcDaysBetween`（日期差天数计算）
18.13 THE Formula_Engine SHALL 实现 `isCutoffCorrect`（截止正确判定：入库/记账日期 vs 期末）

### Requirement 19: AI辅助生成

**User Story:** As a 审计助理, I want to 点击AI按钮自动生成分析说明, so that 快速完成文本撰写。

#### Acceptance Criteria

19.1 THE AI_Assistant SHALL 在审定表提供"AI生成审计说明"按钮
19.2 THE AI_Assistant SHALL 在分析表(F2-18/F2-19/F2-20)提供"AI生成分析结论"按钮
19.3 THE AI_Assistant SHALL 在截止测试提供"AI生成截止结论"按钮
19.4 THE AI_Assistant SHALL 在会计政策提供"AI生成政策评价"按钮
19.5 THE AI_Assistant SHALL 支持用户编辑AI生成内容
19.6 THE AI_Assistant SHALL 支持重新生成

### Requirement 20: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且大数据量流畅, so that 287行委托加工表或35列开发产品表都能流畅操作。

#### Acceptance Criteria

20.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
20.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
20.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
20.4 THE UI SHALL 编制提示details折叠底部
20.5 THE Performance SHALL 对行数>100的表启用虚拟滚动（F2-7委托加工287行/F2-19产销量104行）
20.6 THE Performance SHALL 跨sheet计算启用debounce（2秒）
20.7 THE Performance SHALL defineAsyncComponent懒加载所有子组件
20.8 THE Performance SHALL 公式计算缓存（相同输入不重复计算）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证公式引擎和跨sheet聚合的正确性。

**P1: 期末余额公式** — ∀ opening, increase, decrease ∈ ℝ: calcEndBalance(opening, increase, decrease) === opening + increase - decrease

**P2: 净值公式** — ∀ originalValue, impairment ∈ ℝ≥0: calcNetValue(originalValue, impairment) === originalValue - impairment

**P3: 审定数公式** — ∀ unadjusted, aje ∈ ℝ: calcAuditedAmount(unadjusted, aje) === unadjusted + aje

**P4: 合计行恒等** — ∀ arr: number[]: calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)

**P5: 库龄合计恒等** — ∀ a,b,c,d ∈ ℝ≥0: calcAgingTotal(a,b,c,d) === a+b+c+d

**P6: 单价公式** — ∀ amount ∈ ℝ, qty ∈ ℝ\{0}: calcUnitPrice(amount, qty) === amount/qty

**P7: 变动率边界** — calcChangeRate(0,0)===''; calcChangeRate(0,x)==='N/A'(x≠0); calcChangeRate(a,b)===(b-a)/a (a≠0)

**P8: 产销率公式** — ∀ sales, production ∈ ℝ>0: calcProductionSalesRate(sales, production) === sales/production*100

**P9: 检查比例公式** — ∀ checked, total ∈ ℝ>0: calcCoverageRatio(checked, total) === checked/total*100

**P10: 明细→汇总聚合正确性** — ∀ detailRows[]: 按类别聚合的合计 === 各明细行对应列之和

**P11: 审定表净值=原值-跌价** — ∀ 13类别: netValueRow[i].endAmount === originalValueRow[i].endAudited - impairmentRow[i].endAudited

**P12: 截止判定幂等** — ∀ date组合: isCutoffCorrect(入库日期, 记账日期, 期末) 结果确定且幂等


### Requirement 21: 抽凭引擎集成

**User Story:** As a 审计助理, I want to 在F2-33/F2-34检查表的抽样参数区使用抽凭引擎, so that 我能利用平台统一的5种抽样算法科学确定采购入库/材料领用检查样本，选中样本自动填入检查行。

#### Acceptance Criteria

21.1 THE F2-33采购入库检查表 SHALL 在抽样参数区提供"使用抽凭引擎"按钮（el-button type="primary" icon）
21.2 THE F2-34材料领用检查表 SHALL 在抽样参数区提供"使用抽凭引擎"按钮
21.3 WHEN 用户点击"使用抽凭引擎"按钮时, THE 系统 SHALL 打开 GtVoucherSamplingEngine 对话框（dialog模式）
21.4 THE GtVoucherSamplingEngine 对话框 SHALL 预填总体金额和科目代码（F2-33预填存货科目1401~1412借方发生/F2-34预填贷方发生）
21.5 WHEN 用户在GtVoucherSamplingEngine中完成抽样并确认时, THE 系统 SHALL 将选中样本自动填入检查表动态行（供应商名称/日期/凭证编号/金额等字段从样本数据映射）
21.6 THE 抽样参数区 SHALL 自动更新为引擎返回的参数（样本量/抽样方法）
21.7 THE 已通过抽凭引擎填入的行 SHALL 显示来源标记（tooltip: "来自抽凭引擎 {algorithm}"）

### Requirement 22: 截止测试自动提取

**User Story:** As a 审计助理, I want to F2-29~F2-32截止测试提供自动提取按钮, so that 我能从序时账按期末日期前后自动提取入库/出库凭证，减少手工逐笔录入。

#### Acceptance Criteria

22.1 THE F2-29~F2-32截止测试组件 SHALL 在表格上方提供"自动提取"按钮（el-button type="primary"，图标为lightning-bolt）
22.2 WHEN 用户点击"自动提取"按钮时, THE 系统 SHALL 调用 useCutoffAutoSampling composable
22.3 THE useCutoffAutoSampling SHALL 从tb_ledger按期末日期前后N天（默认±5天可配置）自动提取入库凭证（F2-29/F2-30）或出库凭证（F2-31/F2-32）
22.4 THE 提取结果 SHALL 显示预览弹窗（ElMessageBox），用户确认后填入截止测试表动态行
22.5 THE 自动提取 SHALL 根据截止测试类型（正向/反向）设定不同的筛选逻辑：正向=期末后N天入库单→检查是否已入账；反向=期末前N天入账→检查是否已入库
22.6 THE 已通过自动提取填入的行 SHALL 显示来源标记（tooltip: "自动提取 {date_range}"）
22.7 THE "自动提取"按钮 SHALL 在无序时账数据时显示为disabled + tooltip提示"需先导入序时账数据"

### Requirement 23: 版本链集成

**User Story:** As a 审计助理, I want to F2存货核心组底稿自动记录版本快照, so that 我能追溯底稿变更历史并对比差异。

#### Acceptance Criteria

23.1 THE GtF2InventoryMain 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
23.2 WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
23.3 THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板
23.4 THE GtWpVersionTrail SHALL 显示版本列表（时间/操作人/摘要），支持差异对比
23.5 THE useVersionTrail SHALL 支持手动创建命名快照
23.6 THE 版本快照 SHALL 记录当前allResponses完整JSON + 操作人 + 时间戳

### Requirement 24: 附注模块EventBus联动

**User Story:** As a 审计助理, I want to F2附注披露Tab自动刷新当审定金额变更时, so that 附注数据始终与审定表保持一致。

#### Acceptance Criteria

24.1 THE F2TabDisclosureListed/F2TabDisclosureSoe SHALL subscribe to `substantive:adjudicated` CustomEvent
24.2 WHEN 收到 `substantive:adjudicated` 事件（wpCode='F2', accountCodes含1401~1412）时, THE Disclosure SHALL 自动刷新附注中的审定金额数据
24.3 THE F2TabAdjudication SHALL 在审定表结论文本变更时 publish `disclosure:note-text-updated` 事件（payload含 wpCode='F2'/section='adjudication'/text）
24.4 THE 附注Tab SHALL 显示"数据已更新"提示条（蓝色info bar 3秒自动消失）
24.5 THE GtF2InventoryMain 主入口 SHALL provide('openReviewDialog', openReviewDialog)，子组件inject使用

### Requirement 25: 行级OCR集成（F2-33采购入库检查）

**User Story:** As a 审计助理, I want to 在F2-33采购入库检查表通过OCR上传采购发票/合同, so that 系统自动识别关键字段填入检查行，减少手工录入。

#### Acceptance Criteria

25.1 THE F2-33采购入库检查表 SHALL 在每行显示📎列（附件上传按钮）
25.2 WHEN 用户点击📎上传文件时, THE 系统 SHALL POST /api/workpapers/{wp_id}/f2/contract-ocr（multipart，复用D4 contract-ocr端点模式）
25.3 THE OCR端点 SHALL 返回extracted_fields（采购订单号/日期/金额/供应商名称/发票号等）
25.4 THE 系统 SHALL 弹出ElMessageBox.confirm显示识别结果，用户确认后merge到当前行对应字段
25.5 WHEN OCR识别置信度<80%的字段, THE 确认弹窗 SHALL 以橙色高亮该字段提示人工核对
25.6 THE 上传成功后 SHALL 在📎列显示已上传图标（el-icon Document），hover可预览附件
