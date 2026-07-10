# Requirements Document: H3 投资性房地产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + H3↔H1互转联动
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useH3ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双/三模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase0(双源输入)+Phase1(注册)+Phase2(公式引擎)+Phase3(composable)+Phase4(Vue组件)+Phase5(后端)+Phase6(集成)+Phase7(测试)排序

## Introduction

H3投资性房地产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h3-investment-property`，覆盖来自 `H3 投资性房地产.xlsx` 的22个有效sheet。科目覆盖1503投资性房地产（借方/资产类）+ 成本模式下1504累计折旧（贷方/备抵类）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**H3核心特殊：双计量模式**。成本模式(cost)和公允价值模式(fair_value)决定H3-1/H3-2/H3-5/H3-7的显隐切换——成本模式4sheet可见，公允价值模式对应4sheet可见，互为隐藏。此外，H3-6互转审核表（自用↔投资↔在建三方向转换25公式）是核心审计关注点，H3-8公允价值复核表涉及评估师报告复核，H3-14租金收入测算（月度租金+空置率+到期管理）。关键公式总数约230+。

## Glossary

- **Tab_Index**: 底稿目录，25行8列，sheet导航+进度统计
- **Procedure_Table_H3A**: 投资性房地产实质性程序表H3A，36行12列，审计程序清单（复用a-program-console）
- **Adjudication_Cost_H3_1**: 审定表（成本模式）H3-1，65行10列50公式，科目1503+1504
- **Adjudication_Fair_H3_1**: 审定表（公允价值模式）H3-1，62行10列50公式，科目1503
- **Disclosure_Listed**: 附注披露信息（上市公司），74行250列
- **Disclosure_SOE**: 附注披露信息（国有企业），46行252列
- **Detail_Cost_H3_2**: 明细表（成本模式）H3-2，48行49列14公式
- **Detail_Fair_H3_2**: 明细表（公允价值模式）H3-2，53行31列21公式
- **Adjustment_H3_3**: 调整分录汇总H3-3，21行10列
- **Policy_Check_H3_4**: 会计政策会计估计检查表H3-4，27行15列
- **Addition_Cost_H3_5**: 增减检查表（成本模式）H3-5，46行21列
- **Addition_Fair_H3_5**: 增减检查表（公允价值模式）H3-5，41行20列
- **Transfer_Review_H3_6**: 互转审核表H3-6，62行36列25公式，核心：与H1固定资产互转
- **Depreciation_NoImpair_H3_7**: 折旧测算表（成本模式不含减值）H3-7，40行28列42公式
- **Depreciation_WithImpair_H3_7**: 折旧测算表（成本模式含减值）H3-7，38行28列62公式
- **FairValue_Review_H3_8**: 公允价值复核表H3-8，61行30列15公式，核心：评估报告复核
- **Stocktake_Check_H3_9**: 盘点检查表H3-9，43行13列
- **Impairment_H3_10**: 减值测算表H3-10，42行32列19公式（仅成本模式）
- **Recoverable_H3_11**: 可收回金额测试表H3-11，65行28列12公式（仅成本模式）
- **Title_Check_H3_12**: 产权核对表H3-12，23行16列
- **Related_Party_H3_13**: 关联交易检查表H3-13，36行11列
- **Rental_Income_H3_14**: 租金收入测算表H3-14，39行27列27公式，核心：租金合理性验证
- **Cross_Sheet_Engine**: 跨sheet公式引擎，H3-1→H3-2/H3-6/H3-7/H3-8/H3-14联动
- **Formula_Engine**: 前端公式引擎composable，资产类公式 + 双计量模式公式
- **Measurement_Model_Filter**: 计量模式过滤器，cost/fair_value控制sheet显隐
- **Transfer_Engine**: 互转计算引擎，自用→投资/投资→自用/在建→投资 三方向转换公式
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目1503/成本模式还有1504）
- **Branch_Selector**: 分支选择器，H3-7折旧2分支（不含减值/含减值）
- **CAS3_Policy**: CAS3投资性房地产准则相关政策条款

## Requirements

### Requirement 1: 组件架构与sheetName分发（含measurement_model分支）

**User Story:** As a 开发者, I want to H3投资性房地产底稿按sheetName prop分发到独立子组件且支持计量模式切换, so that 22个sheet在一个统一入口中有序组织，成本/公允价值模式各自显隐。

#### Acceptance Criteria

1. THE H3 组件 SHALL 注册新componentType: `h3-investment-property`，主入口为 GtH3InvestmentProperty.vue
2. THE GtH3InvestmentProperty.vue SHALL 接收 `sheetName` prop（完整中文名），用正则提取末尾编码(H3-1/H3-2/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE H3 组件 SHALL 使用 defineAsyncComponent 对所有子组件（除H3TabIndex外）进行懒加载
4. THE H3 组件 SHALL 将子组件按功能域拆分为独立子目录：h3/core/、h3/inspection/、h3/depreciation/、h3/impairment/、h3/rental/
5. THE H3 组件 SHALL 拆分为composable层：useH3FormData.ts + useH3FormulaEngine.ts(纯函数) + useH3TransferEngine.ts(纯函数) + useH3CrossSheet.ts + useH3DualMode.ts + useH3ImportExport.ts + useH3MeasurementModel.ts + sheet-specific composables
6. THE H3 组件 SHALL 在htmlRendererRegistry中注册'h3-investment-property'→GtH3InvestmentProperty映射
7. THE H3 组件 SHALL 在wp_code_overrides.json中将H3/H3-1~H3-14/H3A映射为'h3-investment-property'
8. THE H3 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h3-investment-property'
9. THE GtH3InvestmentProperty.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=h3-investment-property）
10. THE H3 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H3-{sheet编号}-{field}"格式
11. THE H3 组件 SHALL 实现measurement_model切换逻辑：el-segmented("成本模式"/"公允价值模式")控制H3-1/H3-2/H3-5/H3-7双版本显隐
12. THE measurement_model切换 SHALL 是幂等的：切换后再切回，数据不丢失（两套数据独立存储）

### Requirement 2: 审定表H3-1（双计量模式切换：成本50公式/公允50公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑投资性房地产审定表, so that 我能根据企业采用的计量模式(成本/公允价值)看到对应的审定数据。

#### Acceptance Criteria

1. THE Adjudication_H3_1 SHALL 根据measurement_model渲染对应版本：成本模式(65行10列50公式) / 公允价值模式(62行10列50公式)
2. THE 成本模式H3-1 SHALL 渲染为双区块：一、投资性房地产-原值（分类行+小计）→ 二、累计折旧（分类行+小计）→ 净值合计；列含：项目 | 期初 | 增加 | 减少 | 转换 | 期末 | 未审数 | AJE | RJE | 审定数
3. THE 公允价值模式H3-1 SHALL 渲染为单区块：投资性房地产（分类行+小计）→ 公允价值变动损益汇总；列含：项目 | 期初公允 | 本期增加 | 本期减少 | 转换 | 公允价值变动 | 期末公允 | 未审数 | AJE | RJE | 审定数
4. THE Formula_Engine SHALL 自动计算：审定数=未审+AJE+RJE（两种模式均适用）
5. THE 成本模式 SHALL 校验三角勾稽：原值期末=期初+增加-减少±转换；折旧期末=期初+计提-转回±转换折旧
6. THE 公允价值模式 SHALL 校验：期末公允=期初+增加-减少±转换+公允价值变动
7. THE Adjudication_H3_1 SHALL 在底部显示TB取数行 + 差异行，差异≠0时红色高亮
8. THE Adjudication_H3_1 SHALL 在底部显示审计说明/结论 + AI + 💬复核 + GtIndexChip→H3-6互转
9. WHEN 审定数变化时, THE Adjudication_H3_1 SHALL 回写TB（成本模式科目1503+1504；公允模式科目1503）并发布'substantive:adjudicated'

### Requirement 3: 明细表H3-2（双模式：成本49列/公允31列，宽表拆分）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理投资性房地产明细, so that 我能根据计量模式查看对应的资产明细。

#### Acceptance Criteria

1. THE Detail_Cost_H3_2 SHALL 将49列拆分为3个区段Tab：基本(资产名称/类型/位置/面积/取得日期/入账原值) | 折旧变动(累计折旧期初/本期计提/转回/期末/净值) | 增减转换(本期增加/减少/转入/转出/期末原值)
2. THE Detail_Fair_H3_2 SHALL 将31列拆分为2个区段Tab：基本(资产名称/类型/位置/面积/取得日期/期初公允) | 公允变动(本期增加/减少/转入/转出/公允价值变动/期末公允)
3. THE Detail_H3_2 SHALL 在区段Tab切换时保持行同步
4. THE Formula_Engine SHALL 自动计算：成本模式→净值=原值-折旧-减值；公允模式→期末公允=期初+增加-减少±转换+变动
5. THE Detail_H3_2 SHALL 合计行与H3-1交叉验证
6. WHEN 用户点击"添加资产"按钮时, THE Detail_H3_2 SHALL 弹出ElMessageBox.prompt输入资产名称后新增一行
7. THE Detail_H3_2 SHALL 固定前2列（资产名称/类型）
8. THE Detail_H3_2 SHALL 支持导入导出（el-dropdown三级）
9. THE Detail_H3_2 SHALL 在底部显示审计说明/结论 + AI + 💬复核

### Requirement 4: 调整分录H3-3

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入投资性房地产调整分录, so that 我能管理AJE/RJE并联动审定表。

#### Acceptance Criteria

1. THE Adjustment_H3_3 SHALL 显示10列：序号 | 调整事项说明 | 类别(AJE/RJE) | 科目代码 | 科目名称 | 摘要 | 借方金额 | 贷方金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"时, THE Adjustment_H3_3 SHALL 新增一行
3. THE Adjustment_H3_3 SHALL 底部借贷合计+平衡校验
4. THE Adjustment_H3_3 SHALL 双向同步AJE/RJE到H3-1 + EventBus发布 + 推送A13
5. THE Adjustment_H3_3 SHALL 支持导入导出（el-dropdown三级）

### Requirement 5: 会计政策H3-4（CAS3投资性房地产段落型）

**User Story:** As a 审计助理, I want to 在精美HTML组件中完成CAS3投资性房地产会计政策检查, so that 我能评价计量模式选择的恰当性及后续计量政策的合理性。

#### Acceptance Criteria

1. THE Policy_Check_H3_4 SHALL 渲染为CAS3段落型卡片：(1)投资性房地产确认条件 → (2)计量模式选择(成本/公允价值) → (3)后续计量政策 → (4)转换政策 → (5)处置政策
2. THE Policy_Check_H3_4 SHALL 在"计量模式选择"段落突出显示当前项目采用的模式（来自measurement_model设置）
3. THE Policy_Check_H3_4 SHALL 在每段落内显示：准则条款引用(折叠) + 实际政策(textarea) + 审计师评价(textarea+AI)
4. THE Policy_Check_H3_4 SHALL 每段结论Y/N/NA + 整体进度条
5. THE Policy_Check_H3_4 SHALL 放置复核对话入口（💬图标）

### Requirement 6: 增减检查表H3-5（双模式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行投资性房地产增减检查, so that 我能逐笔核对增减事项的合规性。

#### Acceptance Criteria

1. THE Addition_Cost_H3_5 SHALL 显示21列（成本模式）：序号 | 资产名称 | 日期 | 增减类型(购入/自建转入/自用转入/处置/转出) | 原值 | 累计折旧 | 净值 | 合同 | 发票 | 评估报告 | 产权证 | 审批文件 | 入账科目 | 对方科目 | 损益影响 | 📎附件 | 审计结论 等
2. THE Addition_Fair_H3_5 SHALL 显示20列（公允价值模式）：序号 | 资产名称 | 日期 | 增减类型 | 公允价值 | 评估依据 | 合同 | 发票 | 评估报告 | 产权证 | 公允价值变动 | 损益影响 | 📎附件 | 审计结论 等
3. THE H3-5 SHALL 根据measurement_model显示对应版本
4. THE H3-5 SHALL 集成抽凭引擎 + 行级OCR
5. THE H3-5 SHALL 底部汇总 + 审计说明textarea（AI + 💬复核）
6. THE H3-5 SHALL 支持导入导出（el-dropdown三级）

### Requirement 7: 互转审核表H3-6（25公式，自用↔投资↔在建三方向，核心）

**User Story:** As a 审计助理, I want to 在精美HTML组件中审核投资性房地产互转事项, so that 我能验证自用↔投资↔在建三方向转换的会计处理正确性（含转换日公允价值确定）。

#### Acceptance Criteria

1. THE Transfer_Review_H3_6 SHALL 显示36列62行25公式，按三方向分区渲染：(A)自用→投资性房地产 | (B)投资性房地产→自用 | (C)在建工程→投资性房地产
2. THE 自用→投资(公允模式) SHALL 计算：转换日公允价值 vs 账面价值差额 → 差额计入其他综合收益(公允>账面)或当期损益(公允<账面)
3. THE 投资→自用 SHALL 计算：转换日公允价值作为自用资产的入账价值（无论原计量模式）
4. THE 在建→投资 SHALL 计算：转换日账面价值(成本模式)或公允价值(公允模式)作为入账价值
5. THE Transfer_Review_H3_6 SHALL 对每笔转换验证：转出方金额=转入方金额（差额=0），差异≠0时红色高亮
6. THE Transfer_Review_H3_6 SHALL 在"自用→投资"区提供GtIndexChip跳转H1固定资产对应行
7. THE Transfer_Review_H3_6 SHALL 在"在建→投资"区提供GtIndexChip跳转H2在建工程对应行
8. THE Transfer_Review_H3_6 SHALL 通过EventBus发布'h3:transfer-from-h1'和'h3:transfer-from-h2'事件
9. THE Transfer_Review_H3_6 SHALL 在顶部显示方法论上下文（CAS3第12-15条关于转换的准则摘要）
10. THE Transfer_Review_H3_6 SHALL 底部审计说明textarea（AI + 💬复核）

### Requirement 8: 折旧测算H3-7（成本模式，2分支：不含/含减值）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行投资性房地产折旧测算, so that 我能验证成本模式下折旧计提的准确性。

#### Acceptance Criteria

1. THE Depreciation_H3_7 SHALL 仅在成本模式下显示（measurement_model=cost）
2. THE Depreciation_H3_7 SHALL 使用el-segmented分支选择器切换：(A)不含减值-直线法(40行28列42公式) | (B)含减值(38行28列62公式)
3. THE 不含减值版 SHALL 计算：月折旧=原值×(1-残值率)/使用年限/12；累计折旧；净值
4. THE 含减值版 SHALL 计算：减值后净值重新计算月折旧；减值影响月=min(剩余月数, 原月数)
5. THE Depreciation_H3_7 SHALL 对每行验证：测算累计折旧 vs 账面累计折旧，差异高亮
6. THE Depreciation_H3_7 SHALL 合计行 + 与H3-1折旧小计交叉验证
7. THE Depreciation_H3_7 SHALL 底部审计说明textarea（AI + 💬复核）
8. THE Depreciation_H3_7 SHALL 支持导入导出（el-dropdown三级）

### Requirement 9: 公允价值复核表H3-8（评估复核+假设挑战，核心）

**User Story:** As a 审计助理, I want to 在精美HTML组件中复核投资性房地产公允价值评估, so that 我能验证评估师报告的合理性并挑战关键假设。

#### Acceptance Criteria

1. THE FairValue_Review_H3_8 SHALL 渲染为四区域：(1)评估师信息(机构/资质/独立性) + (2)评估方法与假设(市场法/收益法/成本法关键参数) + (3)复核计算(15公式验证评估结论) + (4)假设挑战清单
2. THE FairValue_Review_H3_8 复核计算列：资产名称 | 评估值 | 账面值 | 差异 | 差异率 | 市场参考价 | 收益法折现率 | 收益法租金假设 | 资本化率 | 独立测算值 | 独立vs评估差异 | 可接受范围 | 是否在范围内 | 结论 | 备注
3. THE Formula_Engine SHALL 计算15公式：差异=评估-账面；差异率=差异/账面×100%；独立测算(收益法)=年租金/(资本化率-增长率)；独立vs评估差异=独立测算-评估值；可接受范围=评估值×±10%
4. WHEN 差异率>20%时, THE FairValue_Review_H3_8 SHALL 以红色高亮提示"公允价值变动幅度大，需进一步分析"
5. WHEN "是否在范围内"=否时, THE FairValue_Review_H3_8 SHALL 以红色高亮该行
6. THE FairValue_Review_H3_8 SHALL 在假设挑战区显示：关键假设 | 评估师假设值 | 审计师独立判断 | 差异 | 合理性结论
7. THE FairValue_Review_H3_8 SHALL 底部审计说明textarea（AI + 💬复核）
8. THE FairValue_Review_H3_8 SHALL 对公允价值变动合计与H3-1"公允价值变动"列交叉验证

### Requirement 10: 盘点检查表H3-9

**User Story:** As a 审计助理, I want to 在精美HTML表格中记录投资性房地产实物盘点, so that 我能核实资产的存在和状态。

#### Acceptance Criteria

1. THE Stocktake_Check_H3_9 SHALL 显示13列：序号 | 资产名称 | 位置/地址 | 产权证号 | 面积(㎡) | 用途(出租/增值) | 租户 | 租赁状态(已出租/空置/到期) | 实物状态 | 维护情况 | 账面值 | 盘点结论 | 备注
2. WHEN 租赁状态为"空置"时, THE Stocktake_Check_H3_9 SHALL 以黄色高亮提示"需评估减值迹象"
3. THE Stocktake_Check_H3_9 SHALL 底部汇总：已盘点数/已出租数/空置数/空置率
4. THE Stocktake_Check_H3_9 SHALL 底部审计说明textarea（AI + 💬复核）
5. THE Stocktake_Check_H3_9 SHALL 支持导入导出（el-dropdown三级）

### Requirement 11: 减值H3-10/H3-11（仅成本模式，DCF）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行投资性房地产减值测试, so that 我能评估成本模式下资产的可收回金额。

#### Acceptance Criteria

1. THE Impairment_H3_10/H3_11 SHALL 仅在成本模式下显示（measurement_model=cost）
2. THE Impairment_H3_10 SHALL 渲染为双区域：(1)减值迹象判断（空置/租金下降/市场恶化/老旧等）+ (2)减值测算表
3. THE Recoverable_H3_11 SHALL 渲染DCF模型：假设区+现金流预测+折现+敏感性矩阵
4. THE Formula_Engine SHALL 计算：可收回金额=MAX(公允-处置费, DCF现值)；减值=MAX(账面-可收回, 0)
5. THE 减值组 SHALL 底部审计说明textarea（AI + 💬复核）

### Requirement 12: 产权核对表H3-12

**User Story:** As a 审计助理, I want to 在精美HTML表格中核对投资性房地产产权, so that 我能验证资产权属的完整性和准确性。

#### Acceptance Criteria

1. THE Title_Check_H3_12 SHALL 显示16列：序号 | 资产名称 | 账面原值 | 产权证号 | 证载面积 | 账面面积 | 面积差异 | 证载所有人 | 是否被审计单位 | 抵押情况 | 查封情况 | 使用限制 | 证载用途 | 实际用途 | 用途是否一致 | 备注
2. THE Formula_Engine SHALL 计算：面积差异=证载面积-账面面积；产权差异=账面原值-按证载面积推算值
3. WHEN 证载所有人非被审计单位时, THE Title_Check_H3_12 SHALL 以红色高亮
4. WHEN 面积差异≠0时, THE Title_Check_H3_12 SHALL 以黄色高亮
5. THE Title_Check_H3_12 SHALL 底部审计说明textarea（AI + 💬复核）

### Requirement 13: 关联交易H3-13

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查投资性房地产关联交易, so that 我能评估关联方租赁/转让的定价合理性。

#### Acceptance Criteria

1. THE Related_Party_H3_13 SHALL 显示11列：序号 | 关联方 | 关联关系 | 交易类型(出租/购入/处置/转换) | 金额 | 定价方式 | 市场价参考 | 差异率 | 审批文件 | 审计结论 | 备注
2. THE Formula_Engine SHALL 计算差异率=(金额-市场价)/市场价×100%
3. WHEN 差异率>10%时, 红色高亮
4. THE Related_Party_H3_13 SHALL 底部审计说明textarea（AI + 💬复核）
5. THE Related_Party_H3_13 SHALL 支持导入导出（el-dropdown三级）

### Requirement 14: 租金收入测算表H3-14（27公式，月度+空置+到期管理）

**User Story:** As a 审计助理, I want to 在精美HTML组件中测算投资性房地产租金收入, so that 我能验证租金收入的完整性和合理性。

#### Acceptance Criteria

1. THE Rental_Income_H3_14 SHALL 渲染为三区域：(1)租赁合同汇总(资产/租户/合同期/月租/年租) + (2)月度租金收入明细(12个月逐月) + (3)到期管理(合同到期日/续租状态/空置预测)
2. THE Formula_Engine SHALL 计算27公式：年租金=月租×12×(1-空置率)；月度应收=约定月租×(实际出租天数/当月天数)；空置损失=月租×空置月数；到期月数=合同到期日-基准日；续租概率调整后收入；租金增长率=(本期-上期)/上期；每平米租金=月租/面积；租金回报率=年租金/账面原值；实际vs测算差异；累计应收=Σ月度应收
3. THE Rental_Income_H3_14 SHALL 对每个资产显示12个月逐月收入行（横向月份列）
4. WHEN 实际收入vs测算差异>5%时, THE Rental_Income_H3_14 SHALL 以黄色高亮提示"需查明差异原因"
5. WHEN 合同到期月数≤3时, THE Rental_Income_H3_14 SHALL 在到期管理区以橙色高亮提示"即将到期"
6. THE Rental_Income_H3_14 SHALL 与H3-1"其他业务收入-租金"交叉验证
7. THE Rental_Income_H3_14 SHALL 底部审计说明textarea（AI + 💬复核）
8. THE Rental_Income_H3_14 SHALL 支持导入导出（el-dropdown三级）

### Requirement 15: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 在精美HTML组件中编制投资性房地产附注披露, so that 我能完成上市公司/国有企业两种格式的附注信息。

#### Acceptance Criteria

1. THE Disclosure SHALL 根据variant参数(listed/soe)渲染对应格式
2. THE Disclosure SHALL 从H3-1/H3-6/H3-14自动取数填充金额字段
3. THE Disclosure SHALL 包含计量模式说明（成本/公允价值及其选择原因）
4. THE Disclosure SHALL 支持动态行+AI辅助+💬复核
5. THE Disclosure SHALL 通过EventBus subscribe 'substantive:adjudicated'刷新

### Requirement 16: 跨Sheet联动+双模式+导入导出+AI+持久化（含measurement_model切换逻辑）

**User Story:** As a 审计助理, I want to H3投资性房地产底稿各sheet之间数据联动且支持计量模式切换/双模式/导入导出/AI辅助, so that 我的工作流高效且数据一致。

#### Acceptance Criteria

1. THE H3 组件 SHALL 支持双模式切换：HTML ↔ OnlyOffice（el-segmented + OO健康检查）
2. THE H3 组件 SHALL 在切换到OnlyOffice前自动保存
3. THE H3 组件 SHALL 支持导入导出composable（useH3ImportExport.ts）
4. THE H3 组件 SHALL 支持AI审计说明生成（/h3/ai-generate端点，8 section）
5. THE H3 组件 SHALL measurement_model切换时：成本模式显示H3-1(成本)/H3-2(成本)/H3-5(成本)/H3-7/H3-10/H3-11；公允模式显示H3-1(公允)/H3-2(公允)/H3-5(公允)/H3-8
6. THE H3 组件 SHALL 支持跨sheet联动：H3-2→H3-1审定表 / H3-6→H3-1转换列 / H3-7→H3-1折旧 / H3-14→收入验证
7. THE H3 组件 SHALL 支持跨底稿联动：H3-6→H1(互转) / H3-6→H2(在建转入)
8. THE H3 组件 SHALL 集成useVersionTrail（autoSnapshot on save）
9. THE H3 组件 SHALL 所有数据存储到checklist_responses表（item_id前缀"H3-"）
10. THE H3 组件 SHALL 集成provide/inject openReviewDialog
11. THE measurement_model切换 SHALL 幂等：切换N次后状态一致（不丢数据，不重复创建）
