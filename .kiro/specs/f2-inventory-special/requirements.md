# Requirements Document

## Introduction

F2存货底稿第三组——合同履约成本专项+IPO/舞弊应对专项的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f2-inventory-special`，覆盖2个xlsx源模板/18个有效sheet（合同履约成本实质性程序表F2-55A + 合同履约成本构成明细F2-55 + 合同履约成本检查F2-56 + 减值准备测算F2-57 + 亏损合同预计损失测算F2-58 + IPO存货程序表F2-61A + 原材料采购价格分析F2-61 + 原材料单价分析F2-62 + 产量与产能/能耗分析F2-63 + 生产成本及单耗分析F2-64 + 关联方采购定价核查-询价函F2-65 + 关联方采购定价核查-市场价F2-66 + 识别未披露的关联方F2-67 + 重要供应商结构分析F2-68 + 供应商核查清单F2-69 + 供应商信息核查表F2-70 + 供应商访谈记录汇总表F2-71 + 供应商访谈记录F2-72）。

**核心特色**：
- **合同履约成本子组(F2-55~F2-58)**：F2-55明细表37列最宽→拆为6区段Tab（基础信息/期初/本期增加/本期减少/期末/审计调整+审定）；F2-57/F2-58含减值/亏损测算核心公式
- **IPO/舞弊应对子组(F2-61~F2-72)**：仅IPO/上市/新三板/重组项目可见（business_category控制）；F2-64单耗分析232行最多需虚拟滚动；F2-68供应商结构25列固定+滚动；F2-70/F2-72多公司Master-Detail模式
- 架构：sheetName prop + v-if分发，子目录分contract/(F2-55~F2-58) + ipo/(F2-61~F2-72)

**源模板sheet清单（openpyxl实读确认）**：

### File 1: F2-55至F2-58 合同履约成本（5 effective sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **合同履约成本实质性程序表F2-55A** | 30×13 | 程序表（复用a-program-console） |
| 2 | **合同履约成本构成明细表F2-55** | 40×37 | **最宽表！**6区段Tab拆分 |
| 3 | **合同履约成本检查表F2-56** | 37×23 | 抽样参数+凭证核对 |
| 4 | **合同履约成本减值准备测算表F2-57** | 30×14 | 减值测算核心公式 |
| 5 | **亏损合同预计损失测算表F2-58** | 26×15 | 亏损判定+预计损失 |

### File 2: F2-61至F2-72 IPO/舞弊应对（13 effective sheets）

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **程序表F2-61A** | 29×12 | IPO存货程序表（复用a-program-console） |
| 2 | **原材料采购价格分析表F2-61** | 118×17 | 逐月采购金额/数量/单价比较 |
| 3 | **原材料单价分析F2-62** | 58×18 | 单价趋势分析 |
| 4 | **存货产量与产能、能耗分析表F2-63** | 51×16 | 产能利用率/能耗分析 |
| 5 | **主要产品生产成本及单耗分析表F2-64** | 232×18 | **最多行！**单耗分析(极重要IPO底稿) |
| 6 | **关联方采购定价公允性核查（询价函）F2-65** | 46×8 | 询价函验证 |
| 7 | **关联方采购定价公允性核查（市场价）F2-66** | 46×7 | 市场价验证 |
| 8 | **识别未披露的关联方F2-67** | 45×20 | 未披露关联方核查 |
| 9 | **重要供应商结构分析F2-68** | 47×25 | 供应商集中度+变动分析 |
| 10 | **供应商核查清单F2-69** | 49×19 | 供应商核查项目清单 |
| 11 | **供应商信息核查表F2-70** | 79×14 | 单个供应商核查(Master-Detail) |
| 12 | **供应商访谈记录汇总表F2-71** | 41×9 | 访谈汇总 |
| 13 | **供应商访谈记录F2-72** | 71×8 | 单次访谈记录(Master-Detail) |

## Glossary

- **Contract_Cost_Detail**: 合同履约成本构成明细表F2-55，37列最宽表，项目维度的成本构成（设备材料/建安分包/人工/其他）×4阶段（期初/增加/减少/期末）+审计调整+审定金额
- **Contract_Cost_Check**: 合同履约成本检查表F2-56，抽样参数设定+凭证核对表（23列）
- **Impairment_Calculation**: 合同履约成本减值准备测算表F2-57，核心公式：预计总成本-已发生成本=待发生成本；减值=max(0, 已发生成本-(已确认收入/预计总收入)×预计总成本)
- **Loss_Contract_Calculation**: 亏损合同预计损失测算表F2-58，亏损判定：预计总成本>预计总收入；预计损失=(预计总成本-预计总收入)×(1-完工进度)
- **Purchase_Price_Analysis**: 原材料采购价格分析表F2-61，报告期逐月采购金额/数量/单价比较（118行×17列）
- **Unit_Price_Analysis**: 原材料单价分析F2-62，单价趋势分析（58行×18列）
- **Capacity_Energy_Analysis**: 产量与产能/能耗分析表F2-63，产能利用率=实际产量/设计产能；单位能耗=能耗总量/产量
- **Unit_Consumption_Analysis**: 主要产品生产成本及单耗分析表F2-64，232行最多，按产品分组的材料/人工/制造费单耗分析
- **Related_Party_Inquiry**: 关联方采购定价公允性核查-询价函F2-65，向第三方询价验证关联方定价公允性
- **Related_Party_Market**: 关联方采购定价公允性核查-市场价F2-66，市场价格验证关联方定价公允性
- **Undisclosed_Related_Party**: 识别未披露的关联方F2-67，通过工商/天眼查等核查未披露关联方（20列）
- **Supplier_Structure**: 重要供应商结构分析F2-68，供应商集中度分析+各期变动（25列固定+滚动模式）
- **Supplier_Checklist**: 供应商核查清单F2-69，供应商核查项目清单（19列）
- **Supplier_Info_Check**: 供应商信息核查表F2-70，单个供应商详细核查(多公司Master-Detail)
- **Supplier_Interview_Summary**: 供应商访谈记录汇总表F2-71，访谈汇总（9列）
- **Supplier_Interview_Detail**: 供应商访谈记录F2-72，单次访谈记录(多公司Master-Detail)
- **IPO_Visibility**: IPO组条件可见性，仅IPO/上市/新三板/重组项目显示F2-61~F2-72（business_category字段控制）
- **Master_Detail_Card**: 多公司Master-Detail卡片模式，参照D4合同检查三模式中的卡片模式（左侧公司列表+右侧详情）
- **Segment_Tab_6**: F2-55六区段Tab拆分：基础信息(4列)/期初余额(5列)/本期增加(5列)/本期减少(5列)/期末余额(5列)/审计调整+审定(13列)
- **Fixed_Scroll_Columns**: 固定列+滚动列模式（F2-68：基础5列固定+各期采购金额变动列横滚）
- **Virtual_Scroll**: 虚拟滚动（F2-64单耗分析232行+按产品分组折叠必须启用）
- **Loss_Contract_Formula**: 亏损合同公式：亏损判定=预计总成本>预计总收入；预计损失=(总成本-总收入)×(1-完工进度)
- **Impairment_Formula**: 减值公式：待发生成本=预计总成本-已发生成本；减值=max(0, 已发生-(已确认收入/预计总收入)×预计总成本)

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F2存货特殊组底稿按sheetName prop分发到独立子组件, so that 18个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F2-Special组件 SHALL 注册新componentType: `f2-inventory-special`，主入口为 GtF2InventorySpecial.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F2-Special组件 SHALL 将sheet按功能分为2个子目录：contract/（F2-55A+F2-55+F2-56+F2-57+F2-58）、ipo/（F2-61A+F2-61~F2-72共13张）
1.3 THE F2-Special组件 SHALL 使用defineAsyncComponent懒加载所有子组件（18个sheet按需加载）
1.4 THE useF2SpecialFormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：减值测算公式/亏损判定公式/完工进度/产能利用率/单位能耗/采购单价变动率/集中度计算/在外天数
1.5 THE F2-Special组件 SHALL 在htmlRendererRegistry中注册'f2-inventory-special'→GtF2InventorySpecial映射
1.6 THE F2-Special组件 SHALL 在wp_code_overrides.json中将F2-55A/F2-55~F2-58/F2-61A/F2-61~F2-72的componentType统一映射为'f2-inventory-special'（共18个wp_code）
1.7 THE F2-Special组件 SHALL 在VALID_COMPONENT_TYPES中注册'f2-inventory-special'
1.8 THE GtF2InventorySpecial.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f2-inventory-special）
1.9 THE GtF2InventorySpecial.vue SHALL 用正则从sheetName提取末尾编码(F2-55A/F2-55/F2-61等)，匹配失败走OnlyOffice fallback

### Requirement 2: IPO组条件可见性控制

**User Story:** As a 现场经理, I want to IPO/舞弊应对底稿仅在IPO/上市/新三板/重组类项目中显示, so that 非IPO项目不会看到不相关的底稿降低工作效率。

#### Acceptance Criteria

2.1 THE IPO_Visibility SHALL 根据项目 business_category 字段判定可见性：仅当 business_category ∈ ['IPO', '上市公司年审', '新三板', '重大资产重组'] 时显示F2-61~F2-72
2.2 WHEN business_category 不在IPO类别集合中时, THE 系统 SHALL 在底稿目录中隐藏F2-61A~F2-72相关条目（不渲染chips）
2.3 THE 后端render策略 SHALL 在返回sheets配置时过滤非IPO项目的F2-61~F2-72 sheet（不返回sheets数据）
2.4 WHEN 项目类型从非IPO变更为IPO时, THE 系统 SHALL 动态显示F2-61~F2-72（无需刷新页面，通过project info watcher响应）
2.5 THE 合同履约成本子组(F2-55~F2-58) SHALL 对所有项目类型可见（不受business_category限制）

### Requirement 3: 合同履约成本构成明细表F2-55 HTML渲染（37列→6区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中管理合同履约成本构成明细, so that 我能按项目跟踪各类成本（设备/建安/人工/其他）的增减变动和审定金额，且37列不需要大范围横滚。

#### Acceptance Criteria

3.1 THE Contract_Cost_Detail SHALL 拆为6区段Tab呈现（每区段≤13列）：
   - **基础信息**（4列）：项目编码/项目名称/收入合同名称/收入合同金额
   - **期初余额**（5列）：设备材料/建安分包/人工/其他/小计
   - **本期增加**（5列）：设备材料/建安分包/人工/其他/小计
   - **本期减少**（5列）：设备材料/建安分包/人工/其他/小计
   - **期末余额**（5列）：设备材料/建安分包/人工/其他/小计
   - **审计调整+审定**（13列）：是否与合同直接相关/是否预期能收回 + 审计调整(5列) + 期末审定金额(5列) + 备注
3.2 THE Formula_Engine SHALL 自动计算：期末小计 = 期初小计 + 本期增加小计 - 本期减少小计
3.3 THE Formula_Engine SHALL 自动计算各子列：期末设备材料 = 期初设备材料 + 增加设备材料 - 减少设备材料（人工/建安/其他同理）
3.4 THE Formula_Engine SHALL 自动计算小计列 = 设备材料 + 建安分包 + 人工 + 其他
3.5 THE Formula_Engine SHALL 自动计算审定金额 = 期末余额 + 审计调整
3.6 THE Contract_Cost_Detail SHALL 底部合计行 = SUM各项目行
3.7 THE Contract_Cost_Detail SHALL 支持动态行增删（在合计行上方新增项目行）
3.8 WHEN 新增动态行时, THE 系统 SHALL 弹出ElMessageBox.prompt要求输入项目名称后再创建行
3.9 THE Contract_Cost_Detail SHALL 区段间保持行同步（切换区段不丢失当前行位置）
3.10 THE Contract_Cost_Detail SHALL 对"是否与合同直接相关"/"是否预期能收回"列应用下拉（是/否）
3.11 WHEN "是否预期能收回"为"否"时, THE 系统 SHALL 以橙色高亮该行（减值风险）
3.12 THE Contract_Cost_Detail SHALL 支持导入导出

### Requirement 4: 合同履约成本检查表F2-56 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中执行合同履约成本凭证核对, so that 我能检查抽样选取的成本凭证是否真实完整。

#### Acceptance Criteria

4.1 THE Contract_Cost_Check SHALL 分为两个区域：抽样参数设定区 + 凭证核对表（对齐xlsx 37行×23列）
4.2 THE 抽样参数设定区 SHALL 包含：总体金额/重要性水平/可容忍错报/预计错报/样本量/抽样方法/抽样范围
4.3 THE 凭证核对表 SHALL 显示23列（固定列+滚动列模式）：
   - 固定列（6列）：序号/项目名称/凭证日期/凭证编号/摘要/金额
   - 滚动列（17列）：成本类型/合同名称/合同编号/入库单号/入库日期/发票号/发票日期/发票金额/付款凭证/付款日期/审批流程/是否合规/会计处理正确性/期间归属正确性/金额准确性/索引号/检查结论
4.4 THE Contract_Cost_Check SHALL 支持动态行增删
4.5 THE Contract_Cost_Check SHALL 底部合计行（金额SUM） + 检查比例（检查金额/总体金额×100%）
4.6 WHEN 检查结论为"异常"时, THE 系统 SHALL 以红色高亮该行
4.7 THE Contract_Cost_Check SHALL 底部审计说明+审计结论textarea（AI辅助）
4.8 THE Contract_Cost_Check SHALL 支持导入导出
4.9 THE Contract_Cost_Check SHALL 支持行级OCR上传（📎列复用OCR端点）

### Requirement 5: 合同履约成本减值准备测算表F2-57 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中测算合同履约成本减值, so that 我能准确计算各项目的减值准备并验证管理层的减值金额。

#### Acceptance Criteria

5.1 THE Impairment_Calculation SHALL 显示14列（对齐xlsx 30行×14列）：项目编码/项目名称/合同预计总收入/已确认收入/完工进度/预计总成本/已发生成本/待发生成本/可收回金额/账面价值/减值金额/管理层计提/差异/备注
5.2 THE Formula_Engine SHALL 自动计算完工进度 = 已确认收入/合同预计总收入（预计总收入=0时显示'N/A'）
5.3 THE Formula_Engine SHALL 自动计算待发生成本 = 预计总成本 - 已发生成本
5.4 THE Formula_Engine SHALL 自动计算可收回金额 = (已确认收入/预计总收入) × 预计总成本（预计总收入=0时=0）
5.5 THE Formula_Engine SHALL 自动计算减值金额 = max(0, 账面价值 - 可收回金额)
5.6 THE Formula_Engine SHALL 自动计算差异 = 减值金额 - 管理层计提
5.7 WHEN 差异≠0时, THE 系统 SHALL 以红色高亮差异列
5.8 THE Impairment_Calculation SHALL 底部合计行 + 审计说明textarea（AI辅助）
5.9 THE Impairment_Calculation SHALL 支持动态行增删
5.10 WHEN 新增动态行时, THE 系统 SHALL 弹出ElMessageBox.prompt要求输入项目名称后再创建行

### Requirement 6: 亏损合同预计损失测算表F2-58 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中判定亏损合同并测算预计损失, so that 我能识别预计总成本超过总收入的亏损项目并计算应确认的预计负债。

#### Acceptance Criteria

6.1 THE Loss_Contract_Calculation SHALL 显示15列（对齐xlsx 26行×15列）：项目编码/项目名称/合同预计总收入/预计总成本/是否亏损/亏损金额/完工进度/已确认预计损失/应确认预计损失/本期应计提/管理层计提/差异/是否需调整/调整建议/备注
6.2 THE Formula_Engine SHALL 自动判定是否亏损 = 预计总成本 > 预计总收入（是/否）
6.3 THE Formula_Engine SHALL 自动计算亏损金额 = 预计总成本 - 预计总收入（非亏损时=0）
6.4 THE Formula_Engine SHALL 自动计算应确认预计损失 = 亏损金额 × (1 - 完工进度)
6.5 THE Formula_Engine SHALL 自动计算本期应计提 = 应确认预计损失 - 已确认预计损失
6.6 THE Formula_Engine SHALL 自动计算差异 = 本期应计提 - 管理层计提
6.7 WHEN 是否亏损="是"时, THE 系统 SHALL 以红色高亮该行
6.8 WHEN 差异≠0时, THE 系统 SHALL 以橙色高亮差异列并将"是否需调整"自动设为"是"
6.9 THE Loss_Contract_Calculation SHALL 底部合计行 + 审计说明textarea（AI辅助）
6.10 THE Loss_Contract_Calculation SHALL 支持动态行增删
6.11 THE Loss_Contract_Calculation SHALL 与F2-57共享项目数据（项目编码/名称/预计总收入/预计总成本联动）

### Requirement 7: 原材料采购价格分析表F2-61 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析报告期各月原材料采购价格, so that 我能识别采购价格异常波动和舞弊迹象。

#### Acceptance Criteria

7.1 THE Purchase_Price_Analysis SHALL 显示17列（对齐xlsx 118行×17列）：材料名称/规格/单位 + 12个月(金额/数量/单价) + 年度均价/年度变动率
7.2 THE Purchase_Price_Analysis SHALL 拆为4区段Tab：材料基础(3列) / 上半年1~6月(各月3列=18列→每月金额数量单价) / 下半年7~12月(同) / 年度汇总(均价+变动率)
7.3 THE Formula_Engine SHALL 自动计算各月单价 = 金额/数量（数量=0时'-'）
7.4 THE Formula_Engine SHALL 自动计算年度均价 = 年度总金额/年度总数量
7.5 THE Formula_Engine SHALL 自动计算年度变动率 = (本年均价-上年均价)/上年均价
7.6 WHEN 任一月份单价变动超过年度均价±30%时, THE 系统 SHALL 以橙色高亮该单元格（价格异常）
7.7 THE Purchase_Price_Analysis SHALL 启用虚拟滚动（118行）
7.8 THE Purchase_Price_Analysis SHALL 支持按材料名称搜索筛选
7.9 THE Purchase_Price_Analysis SHALL 支持动态行增删 + 导入导出
7.10 THE Purchase_Price_Analysis SHALL 底部审计说明textarea（AI辅助）

### Requirement 8: 原材料单价分析F2-62 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析原材料单价趋势, so that 我能通过趋势分析识别异常定价。

#### Acceptance Criteria

8.1 THE Unit_Price_Analysis SHALL 显示18列（对齐xlsx 58行×18列）：材料名称/规格/单位 + 报告期各期单价(T/T-1/T-2共3年) + 各期采购量 + 各期采购额 + 同比变动率 + 环比变动率 + 行业均价 + 偏离度 + 分析结论
8.2 THE Formula_Engine SHALL 自动计算同比变动率 = (T期单价 - T-1期单价)/T-1期单价
8.3 THE Formula_Engine SHALL 自动计算偏离度 = (公司单价 - 行业均价)/行业均价
8.4 WHEN 偏离度绝对值>20%时, THE 系统 SHALL 以红色高亮偏离度列（定价异常风险）
8.5 THE Unit_Price_Analysis SHALL 支持动态行增删 + 导入导出
8.6 THE Unit_Price_Analysis SHALL 底部分析结论textarea（AI辅助）

### Requirement 9: 存货产量与产能/能耗分析表F2-63 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析产能利用率和能耗, so that 我能验证产量合理性并识别产能虚报或能耗异常。

#### Acceptance Criteria

9.1 THE Capacity_Energy_Analysis SHALL 显示16列（对齐xlsx 51行×16列）：产品名称/生产线/设计产能/实际产量/产能利用率 + 电耗总量/单位电耗/水耗总量/单位水耗/气耗总量/单位气耗 + 上期产量/上期利用率/上期单位电耗 + 变动说明/审计关注
9.2 THE Formula_Engine SHALL 自动计算产能利用率 = 实际产量/设计产能（设计产能=0时'N/A'）
9.3 THE Formula_Engine SHALL 自动计算单位电耗 = 电耗总量/实际产量（产量=0时'-'）
9.4 THE Formula_Engine SHALL 自动计算单位水耗、单位气耗（同理）
9.5 WHEN 产能利用率>100%时, THE 系统 SHALL 以红色高亮（产能数据异常）
9.6 WHEN 本期单位电耗较上期变动>20%时, THE 系统 SHALL 以橙色高亮（能耗异常）
9.7 THE Capacity_Energy_Analysis SHALL 支持动态行增删 + 导入导出
9.8 THE Capacity_Energy_Analysis SHALL 底部分析结论textarea（AI辅助）

### Requirement 10: 主要产品生产成本及单耗分析表F2-64 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中分析各产品的单耗情况, so that 我能验证生产成本合理性，这是IPO审计最重要的底稿之一。

#### Acceptance Criteria

10.1 THE Unit_Consumption_Analysis SHALL 显示18列（对齐xlsx 232行×18列）：产品名称/材料名称/规格/单位/标准单耗/实际单耗/差异率/本期投入量/本期产出量/投入产出比/上期单耗/单耗变动率/金额影响/合理性说明 + T-1期/T-2期对比列 + 审计关注/备注
10.2 THE Unit_Consumption_Analysis SHALL 必须启用虚拟滚动（232行）+ 按产品分组折叠
10.3 THE Formula_Engine SHALL 自动计算差异率 = (实际单耗 - 标准单耗)/标准单耗
10.4 THE Formula_Engine SHALL 自动计算投入产出比 = 本期投入量/本期产出量
10.5 THE Formula_Engine SHALL 自动计算单耗变动率 = (本期单耗 - 上期单耗)/上期单耗
10.6 THE Formula_Engine SHALL 自动计算金额影响 = (实际单耗 - 标准单耗) × 本期产出量 × 材料单价
10.7 WHEN 差异率绝对值>10%时, THE 系统 SHALL 以橙色高亮（单耗异常）
10.8 WHEN 投入产出比<0.9 或 >1.1时, THE 系统 SHALL 以红色高亮（投入产出失衡）
10.9 THE Unit_Consumption_Analysis SHALL 支持按产品名称分组折叠/展开
10.10 THE Unit_Consumption_Analysis SHALL 支持动态行增删 + 导入导出
10.11 THE Unit_Consumption_Analysis SHALL 底部分析结论textarea（AI辅助）

### Requirement 11: 关联方采购定价公允性核查F2-65/F2-66 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中核查关联方采购定价公允性, so that 我能通过询价函和市场价两种方式验证关联方交易价格的公允。

#### Acceptance Criteria

11.1 THE Related_Party_Inquiry(F2-65) SHALL 显示8列：序号/关联方名称/采购品名/关联方报价/第三方名称/第三方报价/价差率/结论
11.2 THE Related_Party_Market(F2-66) SHALL 显示7列：序号/关联方名称/采购品名/关联方报价/市场参考价/价差率/结论
11.3 THE Formula_Engine SHALL 自动计算价差率 = (关联方报价 - 参考价)/参考价（F2-65用第三方报价，F2-66用市场参考价）
11.4 WHEN 价差率绝对值>10%时, THE 系统 SHALL 以红色高亮（定价不公允风险）
11.5 THE F2-65/F2-66 SHALL 支持动态行增删
11.6 THE F2-65/F2-66 SHALL 底部"定价公允性结论"textarea（AI辅助）
11.7 THE 结论列 SHALL 提供下拉：公允/基本公允/不公允/待核实

### Requirement 12: 识别未披露的关联方F2-67 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中核查未披露的关联方, so that 我能通过工商/天眼查等公开信息识别客户未披露的关联关系。

#### Acceptance Criteria

12.1 THE Undisclosed_Related_Party SHALL 显示20列（对齐xlsx 45行×20列）：序号/供应商名称/统一社会信用代码/法定代表人/股东信息/注册地址/成立日期/注册资本/实际控制人/与客户关联关系/关联类型/是否已披露/核查来源/核查日期/核查人员/核查结论/风险等级/跟进措施/索引号/备注
12.2 THE Undisclosed_Related_Party SHALL 对关联类型列提供下拉：控股股东/共同控制/重大影响/近亲属/其他关联/疑似关联
12.3 THE Undisclosed_Related_Party SHALL 对核查来源列提供多选：天眼查/企查查/工商登记/裁判文书/企业年报/实地走访
12.4 THE Undisclosed_Related_Party SHALL 对风险等级列提供下拉：高/中/低
12.5 WHEN 风险等级为"高"时, THE 系统 SHALL 以红色高亮该行
12.6 WHEN 是否已披露为"否"且关联类型非"疑似关联"时, THE 系统 SHALL 以橙色高亮（确认关联但未披露）
12.7 THE Undisclosed_Related_Party SHALL 支持动态行增删 + 导入导出
12.8 THE Undisclosed_Related_Party SHALL 底部"关联方核查结论"textarea（AI辅助）

### Requirement 13: 重要供应商结构分析F2-68 HTML渲染（25列固定+滚动）

**User Story:** As a 审计助理, I want to 在精美HTML中分析重要供应商结构, so that 我能评估供应商集中度和各期变动情况。

#### Acceptance Criteria

13.1 THE Supplier_Structure SHALL 显示25列（固定列+滚动列模式）：
   - 固定列（5列）：序号/供应商名称/主要采购品类/合作起始年份/是否关联方
   - 滚动列（20列）：T期采购金额/T期占比/T期排名 + T-1期同3列 + T-2期同3列 + 金额变动(T vs T-1)/变动率 + 金额变动(T-1 vs T-2)/变动率 + 新增/退出标记 + 集中度评价 + 索引号 + 备注
13.2 THE Formula_Engine SHALL 自动计算各期占比 = 供应商采购金额/当期采购总额
13.3 THE Formula_Engine SHALL 自动计算变动率 = (T期金额 - T-1期金额)/T-1期金额
13.4 THE Formula_Engine SHALL 自动计算排名（按金额降序排列自动编号）
13.5 THE Formula_Engine SHALL 自动判定新增/退出：T期有值且T-1期=0为"新增"；T期=0且T-1期有值为"退出"
13.6 WHEN 单一供应商占比>30%时, THE 系统 SHALL 以橙色高亮（供应商集中度高）
13.7 WHEN 标记为"新增"且金额排名前5时, THE 系统 SHALL 以红色高亮（重大新增供应商风险）
13.8 THE Supplier_Structure SHALL 支持动态行增删 + 导入导出
13.9 THE Supplier_Structure SHALL 底部集中度汇总（前5大/前10大占比）+ 分析结论textarea（AI辅助）

### Requirement 14: 供应商核查清单F2-69 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中管理供应商核查清单, so that 我能系统跟踪每个供应商的核查项目完成情况。

#### Acceptance Criteria

14.1 THE Supplier_Checklist SHALL 显示19列（对齐xlsx 49行×19列）：序号/供应商名称/核查项1-工商登记/核查项2-实地走访/核查项3-交易真实性/核查项4-定价公允性/核查项5-关联方核查/核查项6-资金流水/核查项7-物流验证/核查项8-合同条款/核查项9-结算方式/核查项10-信用评价/核查完成度/整体评价/风险分类/跟进事项/负责人/完成日期/索引号/备注
14.2 THE 各核查项列 SHALL 提供下拉：已完成/进行中/未开始/不适用
14.3 THE Formula_Engine SHALL 自动计算核查完成度 = 已完成项数/(总项数-不适用项数)×100%
14.4 WHEN 核查完成度<100%且完成日期已到时, THE 系统 SHALL 以橙色高亮（逾期未完）
14.5 THE Supplier_Checklist SHALL 支持动态行增删
14.6 THE Supplier_Checklist SHALL 底部核查进度汇总（已完成/进行中/未开始数量）

### Requirement 15: 供应商信息核查表F2-70 HTML渲染（多公司Master-Detail）

**User Story:** As a 审计助理, I want to 在精美HTML中逐个核查供应商详细信息, so that 我能对每个重要供应商进行深入背景调查。

#### Acceptance Criteria

15.1 THE Supplier_Info_Check SHALL 采用多公司Master-Detail卡片模式：左侧供应商列表面板 + 右侧当前供应商详情区
15.2 THE 左侧列表面板 SHALL 显示供应商名称列表，支持搜索筛选，当前选中高亮
15.3 THE 右侧详情区 SHALL 显示14列核查项（对齐xlsx）：供应商名称/统一社会信用代码/法定代表人/注册资本/成立日期/经营范围/实际经营地址/员工人数/主要客户/财务状况/合作年限/交易金额/核查方式/核查结论
15.4 THE 右侧详情区 SHALL 分为3个el-card区域：基础工商信息(6项) / 经营情况(4项) / 审计核查(4项)
15.5 THE Supplier_Info_Check SHALL 支持新增供应商（ElMessageBox.prompt输入名称）
15.6 THE Supplier_Info_Check SHALL 支持删除供应商（确认弹窗）
15.7 THE Supplier_Info_Check SHALL 底部（当前供应商的）核查结论textarea（AI辅助）
15.8 THE Supplier_Info_Check SHALL 支持导入导出（批量导入多供应商数据）

### Requirement 16: 供应商访谈记录汇总表F2-71 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML中汇总供应商访谈情况, so that 我能统览所有供应商访谈的关键信息和结论。

#### Acceptance Criteria

16.1 THE Supplier_Interview_Summary SHALL 显示9列（对齐xlsx 41行×9列）：序号/供应商名称/访谈日期/访谈方式/受访人/受访人职务/主要内容摘要/关注事项/结论
16.2 THE 访谈方式列 SHALL 提供下拉：现场访谈/视频访谈/电话访谈/书面问询
16.3 THE 结论列 SHALL 提供下拉：无异常/存在疑点/需进一步核查/异常
16.4 WHEN 结论为"异常"或"存在疑点"时, THE 系统 SHALL 以橙色高亮该行
16.5 THE Supplier_Interview_Summary SHALL 支持动态行增删
16.6 THE Supplier_Interview_Summary SHALL 支持点击供应商名称跳转到F2-72对应访谈详情（GtIndexChip）
16.7 THE Supplier_Interview_Summary SHALL 底部汇总：访谈总数/无异常/存在疑点/需核查/异常数量

### Requirement 17: 供应商访谈记录F2-72 HTML渲染（多公司Master-Detail）

**User Story:** As a 审计助理, I want to 在精美HTML中记录每次供应商访谈详情, so that 我能详细记录访谈问答内容作为审计证据。

#### Acceptance Criteria

17.1 THE Supplier_Interview_Detail SHALL 采用多公司Master-Detail卡片模式：左侧供应商/访谈列表 + 右侧当前访谈记录详情
17.2 THE 左侧列表 SHALL 按供应商分组显示（供应商→多次访谈），支持搜索+折叠
17.3 THE 右侧详情区 SHALL 显示8列核查项（对齐xlsx）：供应商名称/访谈日期/受访人/访谈主题/问题1~N/回答1~N/审计关注点/访谈结论
17.4 THE 右侧详情区 SHALL 支持多组问答（QA pair动态增删，每组：问题textarea + 回答textarea）
17.5 THE Supplier_Interview_Detail SHALL 支持新增访谈记录（选择供应商→输入访谈日期）
17.6 THE Supplier_Interview_Detail SHALL 底部（当前访谈的）审计关注点+访谈结论textarea（AI辅助）
17.7 THE Supplier_Interview_Detail SHALL 支持导入导出

### Requirement 18: 共享公式引擎 useF2SpecialFormulaEngine

**User Story:** As a 开发者, I want to 纯函数公式引擎易于测试, so that 合同履约成本+IPO专项的核心公式清晰无副作用可PBT验证。

#### Acceptance Criteria

18.1 THE Formula_Engine SHALL 实现 `calcRemainingCost`（待发生成本 = 预计总成本 - 已发生成本）
18.2 THE Formula_Engine SHALL 实现 `calcImpairment`（减值 = max(0, 账面价值 - 可收回金额)）
18.3 THE Formula_Engine SHALL 实现 `calcRecoverableAmount`（可收回金额 = (已确认收入/预计总收入) × 预计总成本）
18.4 THE Formula_Engine SHALL 实现 `isLossContract`（亏损判定 = 预计总成本 > 预计总收入）
18.5 THE Formula_Engine SHALL 实现 `calcExpectedLoss`（预计损失 = (总成本-总收入) × (1-完工进度)）
18.6 THE Formula_Engine SHALL 实现 `calcCompletionRate`（完工进度 = 已确认收入/预计总收入）
18.7 THE Formula_Engine SHALL 实现 `calcCapacityUtilization`（产能利用率 = 实际产量/设计产能）
18.8 THE Formula_Engine SHALL 实现 `calcUnitConsumption`（单位能耗 = 能耗总量/产量）
18.9 THE Formula_Engine SHALL 实现 `calcPriceDeviation`（价差率 = (实际价-参考价)/参考价）
18.10 THE Formula_Engine SHALL 实现 `calcConcentrationRatio`（集中度 = 供应商金额/采购总额）
18.11 THE Formula_Engine SHALL 实现 `calcChecklistCompletion`（核查完成度 = 已完成/(总数-不适用)）
18.12 THE Formula_Engine SHALL 实现 `calcSubtotalByCategory`（分类小计 = 设备材料+建安分包+人工+其他）
18.13 THE Formula_Engine SHALL 实现 `calcEndBalance`（期末 = 期初 + 增加 - 减少）
18.14 THE Formula_Engine SHALL 实现 `calcAuditedAmount`（审定 = 期末 + 审计调整）
18.15 THE Formula_Engine SHALL 实现 `calcInputOutputRatio`（投入产出比 = 投入量/产出量）

### Requirement 19: 导入导出功能

**User Story:** As a 审计助理, I want to 支持Excel导入导出, so that 我能离线填写数据后导入系统。

#### Acceptance Criteria

19.1 THE Import_Export SHALL 使用useF2SpecialImportExport composable统一管理（后端三端点）
19.2 THE Import_Export SHALL 对以下动态行表格支持导入导出：F2-55明细/F2-56检查/F2-57减值/F2-58亏损/F2-61采购价格/F2-62单价/F2-63产能/F2-64单耗/F2-65询价/F2-66市场价/F2-67关联方/F2-68供应商结构/F2-69核查清单/F2-70信息核查/F2-71访谈汇总/F2-72访谈记录
19.3 THE Import_Export SHALL 导出空模板含填写说明sheet + 数据校验规则
19.4 THE Import_Export SHALL 导入时进行数据验证（日期/金额/必填字段/公式校验）
19.5 THE Import_Export SHALL 导入失败时显示详细错误信息（行号/字段/原因）
19.6 THE Import_Export SHALL StreamingResponse中文文件名RFC5987编码

### Requirement 20: AI辅助生成

**User Story:** As a 审计助理, I want to 点击AI按钮自动生成分析说明, so that 快速完成文本撰写。

#### Acceptance Criteria

20.1 THE AI_Assistant SHALL 在减值测算(F2-57)提供"AI生成减值分析"按钮
20.2 THE AI_Assistant SHALL 在亏损合同(F2-58)提供"AI生成亏损分析"按钮
20.3 THE AI_Assistant SHALL 在采购价格分析(F2-61/F2-62)提供"AI生成价格分析结论"按钮
20.4 THE AI_Assistant SHALL 在产能能耗分析(F2-63)提供"AI生成产能分析结论"按钮
20.5 THE AI_Assistant SHALL 在单耗分析(F2-64)提供"AI生成单耗分析结论"按钮
20.6 THE AI_Assistant SHALL 在关联方核查(F2-65/F2-66/F2-67)提供"AI生成关联方核查结论"按钮
20.7 THE AI_Assistant SHALL 在供应商分析(F2-68/F2-69)提供"AI生成供应商分析结论"按钮
20.8 THE AI_Assistant SHALL 支持用户编辑AI生成内容 + 重新生成

### Requirement 21: 双模式切换

**User Story:** As a 审计助理, I want to 支持HTML与OnlyOffice模式切换, so that 复杂场景可降级到Excel编辑。

#### Acceptance Criteria

21.1 THE Dual_Mode SHALL 在每个sheet子组件右上角显示"切换到OnlyOffice"按钮
21.2 WHEN 用户点击切换按钮时, THE 系统 SHALL 切换到OnlyOffice编辑当前sheet
21.3 THE Dual_Mode SHALL OnlyOffice模式隐藏非目标sheet tab
21.4 THE Dual_Mode SHALL 切换回HTML时重新渲染Vue组件并同步数据
21.5 THE Dual_Mode SHALL 记住用户选择（localStorage持久化）
21.6 WHEN OnlyOffice加载失败时, THE 系统 SHALL 自动降级到HTML模式并显示提示
21.7 THE Dual_Mode SHALL OnlyOffice sheet名必须与源xlsx tab名完全一致

### Requirement 22: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且大数据量流畅, so that 232行单耗分析表或37列合同履约成本明细表都能流畅操作。

#### Acceptance Criteria

22.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
22.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
22.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
22.4 THE UI SHALL 编制提示details折叠底部
22.5 THE Performance SHALL 对行数>100的表启用虚拟滚动（F2-64单耗232行/F2-61采购价格118行/F2-70供应商核查79行/F2-72访谈记录71行）
22.6 THE Performance SHALL F2-64按产品分组折叠（默认折叠，展开时虚拟滚动组内）
22.7 THE Performance SHALL defineAsyncComponent懒加载所有子组件
22.8 THE Performance SHALL 公式计算缓存（相同输入不重复计算）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证公式引擎的正确性。

**P1: 待发生成本公式** — ∀ totalCost, incurredCost ∈ ℝ≥0: calcRemainingCost(totalCost, incurredCost) === totalCost - incurredCost

**P2: 减值公式非负性** — ∀ bookValue, recoverableAmount ∈ ℝ≥0: calcImpairment(bookValue, recoverableAmount) >= 0

**P3: 亏损判定一致性** — ∀ totalRevenue, totalCost ∈ ℝ≥0: isLossContract(totalRevenue, totalCost) === (totalCost > totalRevenue)

**P4: 预计损失公式** — ∀ totalRevenue, totalCost ∈ ℝ≥0 where totalCost>totalRevenue, completionRate ∈ [0,1]: calcExpectedLoss(totalRevenue, totalCost, completionRate) === (totalCost - totalRevenue) × (1 - completionRate)

**P5: 完工进度范围** — ∀ recognizedRevenue, totalRevenue ∈ ℝ≥0 where totalRevenue>0: 0 ≤ calcCompletionRate(recognizedRevenue, totalRevenue) ≤ (recognizedRevenue可能>totalRevenue时允许>1)

**P6: 产能利用率公式** — ∀ actual, designed ∈ ℝ>0: calcCapacityUtilization(actual, designed) === actual/designed

**P7: 价差率公式** — ∀ actualPrice, refPrice ∈ ℝ where refPrice≠0: calcPriceDeviation(actualPrice, refPrice) === (actualPrice - refPrice)/refPrice

**P8: 集中度公式** — ∀ supplierAmount, totalAmount ∈ ℝ>0: calcConcentrationRatio(supplierAmount, totalAmount) === supplierAmount/totalAmount

**P9: 期末余额公式** — ∀ opening, increase, decrease ∈ ℝ: calcEndBalance(opening, increase, decrease) === opening + increase - decrease

**P10: 分类小计公式** — ∀ equipment, construction, labor, other ∈ ℝ: calcSubtotalByCategory(equipment, construction, labor, other) === equipment + construction + labor + other

**P11: 投入产出比公式** — ∀ input, output ∈ ℝ>0: calcInputOutputRatio(input, output) === input/output

**P12: 核查完成度公式** — ∀ completed, total, notApplicable ∈ ℤ≥0 where total>notApplicable: calcChecklistCompletion(completed, total, notApplicable) === completed/(total-notApplicable)×100


### Requirement 23: 抽凭引擎集成

**User Story:** As a 审计助理, I want to 在F2-56合同履约成本检查表的抽样参数区使用抽凭引擎, so that 我能利用平台统一抽样算法科学确定合同成本检查样本。

#### Acceptance Criteria

23.1 THE F2-56合同履约成本检查表 SHALL 在抽样参数设定区提供"使用抽凭引擎"按钮（el-button type="primary" icon）
23.2 WHEN 用户点击"使用抽凭引擎"按钮时, THE 系统 SHALL 打开 GtVoucherSamplingEngine 对话框（dialog模式）
23.3 THE GtVoucherSamplingEngine 对话框 SHALL 预填总体金额（从抽样参数区取）和科目代码（1405合同履约成本）
23.4 WHEN 用户在GtVoucherSamplingEngine中完成抽样并确认时, THE 系统 SHALL 将选中样本自动填入F2-56凭证核对表动态行（项目名称/凭证日期/编号/金额等字段从样本映射）
23.5 THE 抽样参数区 SHALL 自动更新为引擎返回的参数（样本量/抽样方法）
23.6 THE 已通过抽凭引擎填入的行 SHALL 显示来源标记（tooltip: "来自抽凭引擎 {algorithm}"）

### Requirement 24: 版本链集成

**User Story:** As a 审计助理, I want to F2特殊组底稿自动记录版本快照, so that 我能追溯底稿变更历史并对比差异。

#### Acceptance Criteria

24.1 THE GtF2InventorySpecial 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
24.2 WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照（POST /api/workpapers/{wp_id}/versions/snapshot）
24.3 THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板
24.4 THE GtWpVersionTrail SHALL 显示版本列表（时间/操作人/摘要），支持差异对比
24.5 THE useVersionTrail SHALL 支持手动创建命名快照
24.6 THE 版本快照 SHALL 记录当前allResponses完整JSON + 操作人 + 时间戳
24.7 THE GtF2InventorySpecial 主入口 SHALL provide('openReviewDialog', openReviewDialog)，子组件inject使用

### Requirement 25: 附注模块联动

**User Story:** As a 审计助理, I want to 合同履约成本审定数变更时自动通知附注模块, so that 跨模块数据保持一致。

#### Acceptance Criteria

25.1 THE F2-55合同履约成本明细表 SHALL 在审定金额变更时 publish `substantive:adjudicated` 事件（payload含 wpCode='F2-special'/accountCode='1405'/auditedAmount）
25.2 THE F2-57减值准备测算 SHALL 在减值金额确定时 publish `substantive:adjudicated` 事件（payload含 accountCode='1405'/impairmentAmount）
25.3 THE GtF2InventorySpecial SHALL subscribe to `substantive:adjudicated` 事件（来自其他模块），用于刷新关联数据
25.4 THE F2-55/F2-57 SHALL 在审计结论textarea变更时 publish `disclosure:note-text-updated` 事件
25.5 THE EventBus联动 SHALL 支持去重（同一payload 2秒内不重复发布）

### Requirement 26: 行级OCR集成（F2-56检查表）

**User Story:** As a 审计助理, I want to 在F2-56合同履约成本检查表通过OCR上传合同/发票, so that 系统自动识别关键字段填入检查行。

#### Acceptance Criteria

26.1 THE F2-56合同履约成本检查表 SHALL 在每行显示📎列（附件上传按钮）
26.2 WHEN 用户点击📎上传文件时, THE 系统 SHALL POST /api/workpapers/{wp_id}/f2-special/contract-ocr（复用D4 contract-ocr端点模式）
26.3 THE OCR端点 SHALL 返回extracted_fields（合同编号/金额/供应商/发票号/日期等）
26.4 THE 系统 SHALL 弹出ElMessageBox.confirm显示识别结果，用户确认后merge到当前行对应字段
26.5 WHEN OCR识别置信度<80%的字段, THE 确认弹窗 SHALL 以橙色高亮提示人工核对
26.6 THE 上传成功后 SHALL 在📎列显示已上传图标，hover可预览附件
