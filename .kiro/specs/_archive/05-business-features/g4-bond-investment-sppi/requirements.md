# Requirements Document

## Introduction

G4债权投资底稿专属HTML精美组件构建（SPPI与业务模式分析+盘点组）。将现有通用渲染升级为独立专属组件 `g4-bond-investment-sppi`，覆盖1个xlsx源模板中的4个sheet。科目1501债权投资（借方/资产类）。**CAS22金融工具分类的核心判定逻辑**：通过业务模式分析确定管理目标，通过SPPI测试验证合同现金流量特征，结合盘点程序确认证券存在性。

**三组拆分方案**：
- g4-bond-investment-main: 程序表+审定表+附注+明细表+调整+利息测算（已完成）
- **本spec (sppi)**: 业务模式分析+合同现金流量特征分析+有价证券盘点+盘点倒轧（4个sheet）
- g4-bond-investment-ecl: 三阶段+减值+ECL+凭证检查（另一个spec）

**源模板sheet清单（本spec覆盖，openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 业务模式分析G4-5 | 49×8 | CAS22业务模式判定（问卷+结论） |
| 2 | 合同现金流量特征分析G4-6 | 80×10 | SPPI测试详细检查表 |
| 3 | 有价证券盘点表G4-7 | 29×7 | 证券实物盘点记录 |
| 4 | 盘点倒轧表G4-8 | 39×18 | 盘点日→报表日倒轧 |

**宽表处理策略**：
- G4-8盘点倒轧表(18列)：拆为3区段Tab（盘点日实存/增减变动/报表日实存+差异）

**子目录组织**：
- classification/: 业务模式G4-5 + SPPI G4-6
- inspection/: 盘点G4-7 + 倒轧G4-8

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ❌ 抽凭引擎: 本组sheet不涉及抽凭
- ❌ 截止自动提取: 本组sheet不涉及截止测试
- ❌ 附注EventBus: 本组sheet不涉及附注联动
- ❌ 行级OCR: 本组sheet不涉及凭证OCR
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **Business_Model_Assessment**: 业务模式分析(G4-5)，CAS22要求对债权投资组合确定管理目标（以收取合同现金流量为目标/以收取和出售为目标/其他）
- **SPPI_Test**: 合同现金流量特征分析(G4-6)，Solely Payments of Principal and Interest测试，验证合同现金流量是否仅为对本金和利息的支付
- **Securities_Inventory**: 有价证券盘点表(G4-7)，对持有的债券实物/电子凭证进行实地盘点记录
- **Inventory_Reconciliation**: 盘点倒轧表(G4-8)，将盘点日实存余额调节至资产负债表日余额
- **AC_Classification**: 以摊余成本计量(Amortized Cost)，业务模式为"以收取合同现金流量为目标"且通过SPPI测试
- **FVOCI_Classification**: 以公允价值计量且变动计入其他综合收益，业务模式为"以收取和出售为目标"且通过SPPI测试
- **FVTPL_Classification**: 以公允价值计量且变动计入当期损益，不满足AC或FVOCI条件的金融资产
- **Questionnaire_Logic**: 问卷决策逻辑，业务模式分析中5道问题的组合答案→确定性输出分类结果
- **Contract_Clause_Analysis**: 合同条款分析，SPPI测试中逐项检查票面利率/提前回售/展期/权益转换/杠杆因素等条款
- **Methodology_Context**: 方法论上下文，G4-6判断逻辑列的参考说明（琥珀色左边线+浅黄背景，不可编辑）
- **Count_Date**: 盘点日，实际执行盘点的日期
- **Report_Date**: 资产负债表日（报表日），通常为12月31日
- **Reconciliation_Formula**: 倒轧公式：资产负债表日实存 = 盘点日实存 ± 增减变动
- **Variance_Formula**: 差异公式：差异 = 资产负债表日实存 - 账面结存
- **G4_SPPI_Component**: g4-bond-investment-sppi专属组件，覆盖4个sheet的SPPI与盘点部分

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G4债权投资底稿(SPPI组)按sheetName prop分发到独立子组件, so that 4个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G4-Bond-Investment-SPPI 组件 SHALL 注册新componentType: `g4-bond-investment-sppi`，主入口为 GtG4BondInvestmentSppi.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE G4-Bond-Investment-SPPI 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（4个sheet按需加载）
1.3 THE G4-Bond-Investment-SPPI 组件 SHALL 在htmlRendererRegistry中注册'g4-bond-investment-sppi'→GtG4BondInvestmentSppi映射
1.4 THE G4-Bond-Investment-SPPI 组件 SHALL 在wp_code_overrides.json中将G4-5、G4-6、G4-7、G4-8的componentType统一映射为'g4-bond-investment-sppi'（4个wp_code条目）
1.5 THE G4-Bond-Investment-SPPI 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g4-bond-investment-sppi'
1.6 IF htmlData prop为null, THEN THE GtG4BondInvestmentSppi.vue SHALL 自行调用render-config?force_component_type=g4-bond-investment-sppi获取渲染数据（selfLoad模式）
1.7 IF sheetName正则提取编码失败或提取的编码不在已迁移子组件列表中, THEN THE GtG4BondInvestmentSppi.vue SHALL 渲染OnlyOffice fallback组件
1.8 THE G4-Bond-Investment-SPPI 组件 SHALL 采用sheetName v-if dispatch模式（非el-tabs），通过正则从sheetName提取编码(G4-5/G4-6/G4-7/G4-8)分发到对应子组件
1.9 THE 子组件 SHALL 按子目录组织：classification/(G4-5+G4-6) / inspection/(G4-7+G4-8)

### Requirement 2: 业务模式分析G4-5（问卷式决策）

**User Story:** As a 审计助理, I want to 在精美HTML中完成CAS22业务模式分析问卷, so that 我能通过结构化问题判定债权投资的管理目标并确定分类。

#### Acceptance Criteria

2.1 THE G4-5业务模式分析 SHALL 显示49行×8列问卷式结构，分为两部分：
   - **(一) 以单一业务模式管理所有债权投资**：5道问题(是/否radio+说明textarea)→底部自动结论chip
   - **(二) 将债权投资分拆为次级组合分别确定业务模式**：适用性判断+分组合重复(一)分析
2.2 THE G4-5业务模式分析 SHALL 列结构：序号|检查项目|是否(是/否radio)|说明(textarea autosize)|审计评价
2.3 THE Questionnaire_Logic SHALL 实现业务模式决策：
   - WHEN 5道问题均为"否"（不涉及大额频繁出售+非交易性+不基于公允价值管理）, THEN 结论为"以收取合同现金流量为目标"（AC分类）
   - WHEN 存在一定出售但非频繁（部分问题为"是"但不构成交易性）, THEN 结论为"以收取和出售为目标"（FVOCI分类）
   - WHEN 交易性/频繁出售/基于公允价值管理（关键问题为"是"）, THEN 结论为"其他"（FVTPL分类）
2.4 WHEN 用户修改任一问题的答案时, THE Questionnaire_Logic SHALL 立即重新计算并更新底部结论chip（实时响应）
2.5 THE G4-5业务模式分析 SHALL 底部结论区显示分类结论chip：
   - AC分类：绿色chip"以收取合同现金流量为目标"
   - FVOCI分类：蓝色chip"以收取和出售为目标"
   - FVTPL分类：橙色chip"其他"
   - 未完成：灰色chip"请完成所有问题"
2.6 THE G4-5业务模式分析 SHALL 部分(二)包含适用性判断radio（"是，需分拆为次级组合"/"否，单一业务模式适用"），默认选"否"
2.7 WHEN 部分(二)适用性选择"是"时, THE 系统 SHALL 展开次级组合编辑区，支持通过ElMessageBox.prompt新增组合名称并为每个组合重复部分(一)的5道问题
2.8 THE G4-5业务模式分析 SHALL 顶部审计目标区域显示方法论上下文（琥珀色左边线+浅黄背景）："确定管理债权投资的业务模式，以此为基础对债权投资进行分类"
2.9 THE G4-5业务模式分析 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
2.10 THE G4-5业务模式分析 SHALL 跨组校验提示：WHEN 结论不为"AC"（以收取合同现金流量为目标）时, THE 系统 SHALL 在结论chip下方显示橙色警告"注：债权投资(G4)科目适用以摊余成本计量(AC)分类。若业务模式判定为FVOCI或FVTPL，该投资应归入G6其他债权投资或G1交易性金融资产，请确认分类是否正确。"

### Requirement 3: 合同现金流量特征分析G4-6（SPPI测试）

**User Story:** As a 审计助理, I want to 在精美HTML中完成SPPI测试检查表, so that 我能逐项验证每项债权投资的合同现金流量是否仅为对本金和利息的支付。

#### Acceptance Criteria

3.1 THE G4-6合同现金流量特征分析 SHALL 显示80行×10列，按投资类型分两部分：
   - **(一) 债券投资（国债/公司债/企业债）及委托贷款**：逐项SPPI条款检查
   - **(二) 银行理财产品**：三步分析（保本保收益→浮动收益不现实→穿透底层资产）
3.2 THE G4-6部分(一) SHALL 列结构：投资项目|票面价值|票面利率|提前回售选择权(是/否)|展期选择权(是/否)|权益转换特征(是/否)|杠杆因素(是/否)|结论(通过/不通过/需进一步分析 下拉)|分析项目(下拉)|判断逻辑(方法论上下文，不可编辑)
3.3 THE G4-6部分(一)分析项目 SHALL 提供下拉选项：简单条款直接分析|浮动利率|利率调整|提前偿付特征|展期选择权|无追索权|合同挂钩工具
3.4 WHEN 用户选择分析项目时, THE 系统 SHALL 在判断逻辑列显示对应的方法论上下文说明（琥珀色左边线+浅黄背景，内容根据分析项目类型动态切换）
3.5 THE G4-6部分(二)第一步 SHALL 列结构：投资项目|投资总额|保证本金(是/否)|固定收益(是/否)|固定收益率|约定浮动收益(是/否)|浮动收益率|结论(通过/不通过 下拉)
3.6 THE G4-6部分(二)第二步 SHALL 列结构：投资项目|固定收益率|浮动收益确定方式|基础变量历史变动|是否不现实(是/否)|结论(通过/不通过 下拉)
3.7 THE G4-6部分(二)第三步 SHALL 穿透底层资产分析：投资项目|底层资产类型|底层资产SPPI特征|穿透结论(通过/不通过 下拉)
3.8 THE SPPI_Decision_Logic SHALL 实现SPPI结论推导：
   - WHEN 债券投资无提前回售/展期/权益转换/杠杆因素（4项均为"否"）, THEN 结论自动设为"通过"
   - WHEN 债券投资存在权益转换特征或杠杆因素（任一为"是"）, THEN 结论自动设为"不通过"
   - WHEN 债券投资仅存在提前回售或展期选择权（但无权益转换/杠杆）, THEN 结论自动设为"需进一步分析"
3.9 THE G4-6 SHALL 对80行启用虚拟滚动
3.10 THE G4-6 SHALL 部分(一)和部分(二)各自底部包含审计结论textarea（带AI辅助按钮）
3.11 THE G4-6 SHALL 支持动态行增删（部分(一)新增投资项目需ElMessageBox.prompt输入投资项目名称）+ 导入导出
3.12 THE G4-6 SHALL 编制提示details折叠区（底部）

### Requirement 4: 有价证券盘点表G4-7（证券盘点记录）

**User Story:** As a 审计助理, I want to 在精美HTML中记录有价证券盘点, so that 我能确认持有的债权投资实际存在并与账面记录一致。

#### Acceptance Criteria

4.1 THE G4-7有价证券盘点表 SHALL 显示29行×7列，包含盘点信息头和盘点明细两部分
4.2 THE G4-7盘点信息头 SHALL 显示以下字段（el-form布局）：盘点单位|盘点日期(date-picker)|会计主管|出纳|监盘人|盘点人
4.3 THE G4-7盘点明细 SHALL 列结构：序号|证券名称|面值|数量|总计(公式)|票面利率|到期日
4.4 THE Formula_Engine SHALL 计算总计 = 面值 × 数量，结果保留2位小数（四舍五入）
4.5 THE G4-7盘点明细 SHALL 底部显示合计行（面值合计/数量合计/总计合计）
4.6 THE G4-7 SHALL 底部包含审计说明textarea和审计结论textarea（各带AI辅助按钮），el-card包裹
4.7 THE G4-7 SHALL 支持动态行增删（ElMessageBox.prompt输入证券名称）+ 导入导出
4.8 THE G4-7 SHALL 编制提示details折叠区（底部）

### Requirement 5: 盘点倒轧表G4-8（盘点日→报表日调节）

**User Story:** As a 审计助理, I want to 在精美HTML中编制盘点倒轧表, so that 我能将盘点日实存调节至资产负债表日并验证与账面结存一致。

#### Acceptance Criteria

5.1 THE G4-8盘点倒轧表 SHALL 显示39行×18列，拆为3区段Tab：
   - **盘点日实存(6列)**：证券名称|数量|面值|总计(公式)|票面利率|到期日
   - **增减变动(2列)**：资产负债表日到盘点日增减数量|增减面值总额
   - **报表日实存+差异(10列)**：报表日数量(公式)|报表日面值|报表日总计(公式)|报表日票面利率|报表日到期日|账面结存数量|账面结存面值|账面结存总计|差异(公式)|备注
5.2 THE Formula_Engine SHALL 计算盘点日总计 = 面值 × 数量，结果保留2位小数
5.3 THE Formula_Engine SHALL 计算报表日数量 = 盘点日数量 + 增减数量
5.4 THE Formula_Engine SHALL 计算报表日总计 = 报表日面值 × 报表日数量，结果保留2位小数
5.5 THE Formula_Engine SHALL 计算差异 = 报表日总计 - 账面结存总计，结果保留2位小数
5.6 WHEN |差异|>0时, THE 系统 SHALL 以红色高亮差异单元格并要求填写备注说明原因
5.7 WHEN 用户切换区段Tab时, THE G4-8盘点倒轧表 SHALL 保持当前选中行的行索引不变（行同步）
5.8 THE G4-8盘点倒轧表 SHALL 底部显示合计行（数量合计/面值合计/总计合计/差异合计）
5.9 THE G4-8盘点倒轧表 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
5.10 THE G4-8盘点倒轧表 SHALL 支持动态行增删（ElMessageBox.prompt输入证券名称）+ 导入导出

### Requirement 6: 公式引擎（G4-SPPI专属）

**User Story:** As a 开发者, I want to 实现G4债权投资(SPPI组)公式引擎, so that 业务模式决策/SPPI结论推导/盘点倒轧等公式可PBT验证。

#### Acceptance Criteria

6.1 THE Formula_Engine SHALL 实现 `determineBusinessModel(answers: {q1:boolean, q2:boolean, q3:boolean, q4:boolean, q5:boolean}): 'AC' | 'FVOCI' | 'FVTPL' | 'INCOMPLETE'`：
   - WHEN q1~q5全为false, THEN 返回'AC'
   - WHEN q1或q2为true且q3~q5全为false, THEN 返回'FVOCI'
   - WHEN q3或q4或q5为true, THEN 返回'FVTPL'
   - WHEN 任一答案为null/undefined, THEN 返回'INCOMPLETE'
   - 注：上述为简化决策模型，实现时须以源模板G4-5实际问题语义为准（如q3=是+q4=是可能仍为FVOCI而非FVTPL），开发阶段需逐题对照模板确认完整决策矩阵
6.2 THE Formula_Engine SHALL 实现 `determineSPPIConclusion(hasEarlyRedemption: boolean, hasExtension: boolean, hasEquityConversion: boolean, hasLeverage: boolean): 'PASS' | 'FAIL' | 'FURTHER_ANALYSIS'`：
   - WHEN 4项均为false, THEN 返回'PASS'
   - WHEN hasEquityConversion或hasLeverage为true, THEN 返回'FAIL'
   - WHEN 仅hasEarlyRedemption或hasExtension为true（无equity/leverage）, THEN 返回'FURTHER_ANALYSIS'
6.3 THE Formula_Engine SHALL 实现 `calcInventoryTotal(faceValue: number, quantity: number): number`，返回 `faceValue × quantity`（盘点总计 = 面值 × 数量），结果保留2位小数
6.4 THE Formula_Engine SHALL 实现 `calcReportDateQuantity(countDateQty: number, change: number): number`，返回 `countDateQty + change`（报表日数量 = 盘点日数量 + 增减数量）
6.5 THE Formula_Engine SHALL 实现 `calcReportDateTotal(reportFaceValue: number, reportQuantity: number): number`，返回 `reportFaceValue × reportQuantity`（报表日总计），结果保留2位小数
6.6 THE Formula_Engine SHALL 实现 `calcReconciliationVariance(reportDateTotal: number, bookTotal: number): number`，返回 `reportDateTotal - bookTotal`（差异 = 报表日实存 - 账面结存），结果保留2位小数
6.7 THE Formula_Engine SHALL 实现 `isReconciliationBalanced(reportDateTotal: number, bookTotal: number): boolean`，当 `|reportDateTotal - bookTotal| < 0.01` 时返回true
6.8 THE Formula_Engine SHALL 实现 `calcSumColumn(values: number[]): number`，返回数组元素之和（用于合计行计算），空数组返回0
6.9 IF 任一公式函数接收到 null、undefined、空串或 NaN 作为数值参数, THEN THE Formula_Engine SHALL 通过 `parseNum` 将其转换为 0 后参与计算，不得抛出异常或返回 NaN
6.10 THE Formula_Engine SHALL 导出所有公式函数为纯函数（无副作用、无 Vue 响应式依赖、无外部状态访问），支持 fast-check PBT 以 numRuns≥100 验证各公式的确定性和代数恒等性

### Requirement 7: 跨模块联动（版本链+复核对话）

**User Story:** As a 开发者, I want to G4(SPPI组)底稿集成版本链和复核对话, so that 审计过程有版本追溯和复核记录。

#### Acceptance Criteria

7.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
7.2 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
7.3 THE G4(SPPI组) SHALL 不集成抽凭引擎（本组sheet不涉及凭证抽样）
7.4 THE G4(SPPI组) SHALL 不集成截止自动提取（本组sheet不涉及截止测试）
7.5 THE G4(SPPI组) SHALL 不集成附注EventBus（本组sheet不涉及附注联动）
7.6 THE G4(SPPI组) SHALL 不集成行级OCR（本组sheet不涉及凭证OCR）

### Requirement 8: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

8.1 THE Import_Export SHALL 对动态行表格支持导入导出：G4-6合同现金流量(部分一+部分二)/G4-7盘点表/G4-8倒轧表（共3张）
8.2 THE Import_Export SHALL 使用useG4SppiImportExport composable（后端三端点：导出模板/导出数据/导入数据）
8.3 THE Import_Export SHALL G4-8倒轧表按3区段分sheet导出（多区块分sheet导出）
8.4 THE AI_Assistant SHALL 提供AI辅助section：business-model-conclusion（业务模式结论）/sppi-bond-conclusion（SPPI债券结论）/sppi-financial-conclusion（SPPI理财结论）/inventory-conclusion（盘点结论）/reconciliation-conclusion（倒轧结论）
8.5 THE AI_Assistant SHALL 在每个文本区section标题行右侧提供AI辅助按钮
8.6 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 9: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且SPPI检查表和倒轧表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

9.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
9.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源（如"总计 = 面值 × 数量"）
9.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
9.4 THE UI SHALL 编制提示details折叠底部
9.5 THE UI SHALL 动态行新增需ElMessageBox.prompt输入名称确认后创建
9.6 THE UI SHALL G4-5业务模式分析采用问卷式交互（是/否radio+说明textarea），非传统表格
9.7 THE UI SHALL G4-6判断逻辑列方法论上下文使用琥珀色左边线+浅黄背景（不可编辑）
9.8 THE Performance SHALL 对G4-6(80行)启用虚拟滚动
9.9 THE Performance SHALL defineAsyncComponent懒加载所有子组件
9.10 THE UI SHALL G4-8盘点倒轧表18列区段Tab切换流畅（Tab切换无闪烁/行同步无延迟）
9.11 THE UI SHALL G4-5底部结论chip根据分类结果动态变色（AC绿/FVOCI蓝/FVTPL橙/未完成灰）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G4(SPPI组)公式引擎的正确性。

**P1: 业务模式决策确定性** — ∀ answers ∈ {q1~q5: boolean}: determineBusinessModel(answers) 的输出仅取决于输入组合，相同输入永远产出相同分类结果（AC/FVOCI/FVTPL）

**P2: 业务模式决策完备性** — ∀ answers ∈ {q1~q5: boolean}: determineBusinessModel(answers) ∈ {'AC', 'FVOCI', 'FVTPL'}（5个布尔问题的32种组合均有确定输出，不存在未定义状态）

**P3: 业务模式决策互斥性** — ∀ answers ∈ {q1~q5: boolean}: determineBusinessModel(answers) 恰好属于AC/FVOCI/FVTPL之一（三种分类互斥，不可能同时属于两类）

**P4: SPPI结论推导确定性** — ∀ (earlyRedemption, extension, equityConversion, leverage) ∈ boolean⁴: determineSPPIConclusion的输出仅取决于4个布尔输入，确定性映射到PASS/FAIL/FURTHER_ANALYSIS之一

**P5: SPPI失败条件充分性** — ∀ inputs where hasEquityConversion=true OR hasLeverage=true: determineSPPIConclusion(...) === 'FAIL'（权益转换或杠杆因素必导致SPPI不通过）

**P6: SPPI通过条件必要性** — ∀ inputs: determineSPPIConclusion(...) === 'PASS' → (hasEarlyRedemption=false AND hasExtension=false AND hasEquityConversion=false AND hasLeverage=false)（通过SPPI必须4项均为否）

**P7: 盘点总计公式** — ∀ faceValue ∈ ℝ≥0, quantity ∈ ℤ≥0: calcInventoryTotal(faceValue, quantity) === round(faceValue × quantity, 2)

**P8: 报表日数量加法恒等** — ∀ countDateQty ∈ ℤ≥0, change ∈ ℤ: calcReportDateQuantity(countDateQty, change) === countDateQty + change

**P9: 倒轧差异公式** — ∀ reportTotal, bookTotal ∈ ℝ≥0: calcReconciliationVariance(reportTotal, bookTotal) === round(reportTotal - bookTotal, 2)

**P10: 倒轧平衡判定一致性** — ∀ reportTotal, bookTotal ∈ ℝ≥0: isReconciliationBalanced(reportTotal, bookTotal) ↔ (|reportTotal - bookTotal| < 0.01)

**P11: 合计行加法交换律** — ∀ values ∈ ℝ[]: calcSumColumn(values) === calcSumColumn(shuffle(values))（求和与顺序无关）

**P12: parseNum健壮性** — ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n（有效数字透传）

**P13: SPPI与业务模式组合分类** — ∀ businessModel ∈ {AC, FVOCI, FVTPL}, sppi ∈ {PASS, FAIL, FURTHER_ANALYSIS}: 当businessModel='AC'且sppi='PASS'时最终分类为AC；当sppi='FAIL'时最终分类必为FVTPL（无论业务模式如何）
