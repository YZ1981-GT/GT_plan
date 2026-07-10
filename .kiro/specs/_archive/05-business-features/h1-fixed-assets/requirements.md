# Requirements Document: H1 固定资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useH1ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双/三模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase0(双源输入)+Phase1(注册)+Phase2(公式引擎)+Phase3(composable)+Phase4(Vue组件)+Phase5(后端)+Phase6(集成)+Phase7(测试)排序

## Introduction

H1固定资产底稿的专属HTML精美组件构建。将现有 `d-form-table`/`audit-sheet` 通用渲染升级为独立专属组件 `h1-fixed-assets`，覆盖来自 `H1 固定资产.xlsx` 的26个有效sheet。科目覆盖1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发，外层GtWpRenderer提供目录行chips导航）。核心关注：资产类三角勾稽（期末=期初+增加-减少）、折旧四种方法计算引擎、减值DCF资产组测试、实物监盘三阶段流程、权属检查逐项核验、跨底稿联动（折旧→D5/K8/K9分摊 + 处置→H10 + C6前置驱动）。关键公式总数约280+。

## Glossary

- **Tab_Index**: 底稿目录，28行8列，sheet导航+进度统计
- **Procedure_Table_H1A**: 固定资产审计程序表H1A，40行13列，审计程序清单（复用a-program-console）
- **Adjudication_H1_1**: 审定表H1-1，74行9列51公式，资产类/借方科目1601+1602双区块审定
- **Disclosure_Listed**: 附注披露信息（上市公司），93行257列，固定资产附注结构
- **Disclosure_SOE**: 附注披露信息（国有企业），78行256列，固定资产附注结构
- **Detail_H1_2**: 明细表H1-2，56行54列12公式，按资产分类的原值/折旧/减值宽表
- **Adjustment_H1_3**: 调整分录汇总H1-3，24行13列，AJE/RJE管理
- **Idle_Check_H1_4**: 闲置检查表H1-4，31行12列，闲置固定资产清查
- **Policy_Check_H1_5**: 会计政策估计检查表H1-5，34行16列，CAS4固定资产段落型
- **Analysis_H1_6**: 分析表H1-6，29行20列8公式，固定资产结构/变动分析
- **Addition_Check_H1_7**: 增加检查表H1-7，61行24列，新增资产凭证核对+OCR+抽凭
- **Disposal_Check_H1_8**: 减少检查表H1-8，43行27列，处置/报废核对+联动H10
- **Stocktake_Plan_H1_9**: 监盘计划H1-9，58行15列，盘点计划与样本选取
- **Stocktake_Check_H1_10**: 盘点检查表H1-10，65行17列，实物盘点逐项核对
- **Stocktake_Summary_H1_11**: 监盘小结H1-11，125行10列，盘点结论与差异分析
- **Depreciation_Straight_H1_12**: 折旧测算表（不含减值）-直线法H1-12，68行28列62公式
- **Depreciation_Impair_H1_12**: 折旧测算表（含减值）H1-12，48行28列86公式
- **Depreciation_Multi_H1_12**: 折旧测算表（多次减值）H1-12，50行29列94公式
- **Depreciation_Alloc_H1_13**: 折旧分配分析表H1-13，23行11列11公式，按部门分摊
- **Impairment_H1_14**: 减值测算表H1-14，40行33列15公式，可收回金额vs账面
- **Recoverable_H1_15**: 可收回金额测试表H1-15，88行28列12公式，DCF资产组
- **Title_Building_H1_16**: 房屋建筑物权属检查表H1-16，98行22列
- **Title_Vehicle_H1_17**: 运输设备权属检查表H1-17，95行18列
- **Related_Party_H1_18**: 关联交易检查表H1-18，106行15列
- **Operating_Lease_H1_19**: 经营租出固定资产检查表H1-19，93行25列23公式
- **Finance_Lease_H1_20**: 融资租出固定资产检查表H1-20，125行22列
- **Cross_Sheet_Engine**: 跨sheet公式引擎，H1-1→H1-2/H1-12/H1-13/H1-14联动
- **Formula_Engine**: 前端公式引擎composable，资产类借方科目公式（期末=期初+借方-贷方；审定=未审+AJE+RJE；三角勾稽期末=期初+增加-减少）
- **Depreciation_Engine**: 折旧计算引擎，4种方法：直线法/双倍余额递减/年数总和法/工作量法
- **Triangle_Reconciliation**: 三角勾稽，期末余额=期初余额+本期增加-本期减少（原值/折旧/减值三层均需满足）
- **Branch_Selector**: 分支选择器，H1-12三版本切换（不含减值-直线法/含减值/多次减值）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动分析/政策评价等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1601+1602，资产类/借方+备抵类/贷方）
- **FixedAssetStocktakeDialog**: 固定资产监盘对话组件（复用F循环InventoryStocktakeDialog模式）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H1固定资产底稿按sheetName prop分发到独立子组件, so that 26个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE H1 组件 SHALL 注册新componentType: `h1-fixed-assets`，主入口为 GtH1FixedAssets.vue
2. THE GtH1FixedAssets.vue SHALL 接收 `sheetName` prop（完整中文名），用正则提取末尾编码(H1-1/H1-2/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE H1 组件 SHALL 使用 defineAsyncComponent 对所有子组件（除H1TabIndex外）进行懒加载
4. THE H1 组件 SHALL 将子组件按功能域拆分为独立子目录：h1/core/、h1/inspection/、h1/stocktake/、h1/depreciation/、h1/impairment/
5. THE H1 组件 SHALL 拆分为composable层：useH1FormData.ts + useH1FormulaEngine.ts(纯函数) + useH1CrossSheet.ts + useH1DualMode.ts + useH1ImportExport.ts + sheet-specific composables
6. THE H1 组件 SHALL 在htmlRendererRegistry中注册'h1-fixed-assets'→GtH1FixedAssets映射
7. THE H1 组件 SHALL 在wp_code_overrides.json中将H1/H1-1~H1-20/H1A映射为'h1-fixed-assets'
8. THE H1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h1-fixed-assets'
9. THE GtH1FixedAssets.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=h1-fixed-assets）
10. THE H1 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H1-{sheet编号}-{field}"格式

### Requirement 2: 审定表H1-1（三角勾稽+双区块原值/折旧）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑固定资产审定表, so that 我能清晰地看到原值+累计折旧双区块的审定数据并自动验证三角勾稽。

#### Acceptance Criteria

1. THE Adjudication_H1_1 SHALL 渲染为双区块固定结构：一、固定资产-原值（资产分类行+小计）→ 二、累计折旧（资产分类行+小计）→ 固定资产净值合计
2. THE Adjudication_H1_1 SHALL 显示以下列：项目 | 期初余额 | 本期借方发生(增加) | 本期贷方发生(减少) | 期末余额 | 未审数 | AJE | RJE | 审定数
3. WHEN 用户编辑未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 对原值区块自动校验：期末余额=期初余额+借方发生-贷方发生（资产类借方科目1601）
5. THE Formula_Engine SHALL 对累计折旧区块自动校验：期末余额=期初余额+贷方发生-借方发生（备抵类贷方科目1602，贷方增加/借方减少）
6. THE Adjudication_H1_1 SHALL 自动计算各区块小计行和净值合计行（=原值小计-累计折旧小计），合计行不可编辑
7. THE Adjudication_H1_1 SHALL 实施三角勾稽校验：原值期末=期初+增加-减少 AND 折旧期末=期初+计提-转回，校验失败时红色高亮并显示差额
8. THE Adjudication_H1_1 SHALL 在底部显示试算平衡表数行（自动从TB取数科目1601+1602）和差异行（=审定数-试算表数），差异不为零时红色高亮
9. WHEN 原值小计的审定数与H1-2合计行不一致时, THE Adjudication_H1_1 SHALL 显示黄色警告"原值审定数≠H1-2合计，差额：±xxx元"
10. THE Adjudication_H1_1 SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮 + GtIndexChip跳转H1-6分析结果）和"审计结论"区域
11. WHEN 审定数计算完成且发生变化时, THE Adjudication_H1_1 SHALL 调用writebackTrialBalance将最新审定数回写trial_balance.audited_amount（科目1601+1602）并通过EventBus发布'substantive:adjudicated'事件
12. THE Adjudication_H1_1 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 3: 明细表H1-2（54列宽表拆分4区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理固定资产明细, so that 我能通过4个区段Tab分别查看基础信息/原值变动/折旧/减值而无需大量横滚。

#### Acceptance Criteria

1. THE Detail_H1_2 SHALL 将54列拆分为4个区段Tab：基础(资产分类/名称/入账日期/使用年限/残值率/折旧方法) | 原值变动(期初原值/本期增加/本期减少/期末原值) | 折旧(累计折旧期初/本期计提/本期转回/累计折旧期末/净值) | 减值(减值准备期初/本期计提/本期转回/减值准备期末)
2. THE Detail_H1_2 SHALL 在4个区段Tab切换时保持行同步（选中行高亮跨Tab一致）
3. THE Formula_Engine SHALL 自动计算每行：期末原值=期初原值+增加-减少；累计折旧期末=期初+计提-转回；减值期末=期初+计提-转回；净值=期末原值-累计折旧期末-减值期末
4. THE Detail_H1_2 SHALL 在底部显示合计行（=SUM所有资产分类行各金额列），合计行不可编辑
5. THE Detail_H1_2 SHALL 对合计行与H1-1审定表进行交叉验证：原值合计=H1-1原值小计审定数；折旧合计=H1-1折旧小计审定数
6. WHEN 用户点击"添加资产行"按钮时, THE Detail_H1_2 SHALL 弹出ElMessageBox.prompt输入资产分类名称后新增一行
7. THE Detail_H1_2 SHALL 在"基础"区段提供"折旧方法"下拉选择（直线法/双倍余额递减/年数总和法/工作量法）
8. THE Detail_H1_2 SHALL 固定前2列（资产分类/名称）使各区段Tab内横滚时仍可辨识行
9. THE Detail_H1_2 SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
10. WHEN 动态行超过30行时, THE Detail_H1_2 SHALL 启用虚拟滚动以保证渲染性能
11. THE Detail_H1_2 SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮）和"审计结论"区域
12. THE Detail_H1_2 SHALL 支持导入导出（el-dropdown三级：导出模板/导出数据/导入数据）

### Requirement 4: 调整分录H1-3

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理固定资产调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_H1_3 SHALL 显示13列：序号 | 调整事项说明 | 类别(AJE/RJE) | 报表项目 | 科目代码 | 科目名称 | 附注项目 | 摘要 | 借方金额 | 贷方金额 | 对方科目 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_H1_3 SHALL 新增一行可编辑空行
3. THE Adjustment_H1_3 SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_H1_3 SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='H1'/entryType/amount）
5. THE Adjustment_H1_3 SHALL 双向同步AJE/RJE合计到 Adjudication_H1_1 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_H1_3 SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_H1_3 SHALL 在底部显示编制提示（`<details>`折叠，琥珀色左边线+浅黄背景，默认收起）
8. THE Adjustment_H1_3 SHALL 支持导入导出（el-dropdown三级）

### Requirement 5: 闲置检查表H1-4

**User Story:** As a 审计助理, I want to 在精美HTML表格中记录闲置固定资产检查情况, so that 我能评估闲置资产是否存在减值迹象并建议处置方案。

#### Acceptance Criteria

1. THE Idle_Check_H1_4 SHALL 显示12列：序号 | 资产名称 | 资产编号 | 原值 | 累计折旧 | 净值 | 闲置原因 | 闲置起始日期 | 是否计提减值 | 减值金额 | 处置建议 | 备注
2. WHEN 用户点击"添加闲置资产"按钮时, THE Idle_Check_H1_4 SHALL 弹出ElMessageBox.prompt输入资产名称后新增一行
3. THE Idle_Check_H1_4 SHALL 在底部显示汇总统计：闲置资产总数/闲置净值合计/已计提减值合计/未计提减值数量
4. WHEN 闲置资产净值>0且未计提减值时, THE Idle_Check_H1_4 SHALL 以黄色高亮该行提示"存在减值迹象"
5. THE Idle_Check_H1_4 SHALL 在"是否计提减值"列提供GtIndexChip跳转至H1-14减值测算表
6. THE Idle_Check_H1_4 SHALL 在底部显示"审计说明"textarea（AI生成按钮）和"审计结论"textarea
7. THE Idle_Check_H1_4 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
8. THE Idle_Check_H1_4 SHALL 支持导入导出（el-dropdown三级）

### Requirement 6: 会计政策H1-5（CAS4固定资产段落型）

**User Story:** As a 审计助理, I want to 在精美HTML组件中完成CAS4固定资产会计政策估计检查, so that 我能逐项评价被审计单位固定资产确认/折旧/减值政策的恰当性。

#### Acceptance Criteria

1. THE Policy_Check_H1_5 SHALL 渲染为CAS4段落型卡片结构：(1)固定资产确认条件 → (2)固定资产分类与使用年限 → (3)折旧方法与残值率 → (4)后续支出资本化/费用化 → (5)减值政策 → (6)处置确认
2. THE Policy_Check_H1_5 SHALL 在每段落卡片内显示3个区域：(a)准则条款引用（只读折叠`<details>`，蓝色左边线+浅蓝背景）(b)被审计单位实际政策（textarea可编辑）(c)审计师评价（textarea + AI生成按钮）
3. THE Policy_Check_H1_5 SHALL 在每段落底部显示结论选择：Y(适当) / N(不适当) / NA(不适用)，结论为N时强制填写说明
4. THE Policy_Check_H1_5 SHALL 在"折旧方法与残值率"段落显示分类参数表：资产分类 | 折旧方法 | 使用年限(年) | 残值率(%) | 是否合理
5. THE Policy_Check_H1_5 SHALL 在页面顶部显示整体完成进度（6段中已完成N段，以进度条展示）
6. THE Policy_Check_H1_5 SHALL 在每段落评价区域放置复核对话入口（💬图标）和AI生成按钮（🤖）
7. THE Policy_Check_H1_5 SHALL 在顶部显示蓝色渐变引导区（序号步骤说明，2列grid布局）

### Requirement 7: 分析表H1-6

**User Story:** As a 审计助理, I want to 在精美HTML组件中查看固定资产结构与变动分析, so that 我能直观判断资产结构是否合理、变动是否异常。

#### Acceptance Criteria

1. THE Analysis_H1_6 SHALL 渲染为双区域结构：(1)资产结构分析（各类资产原值/折旧/净值/占比/成新率）+ (2)变动分析（本期增加率/减少率/净变动率/折旧覆盖率）
2. THE Formula_Engine SHALL 自动计算8个公式：占比=本类净值/总净值；成新率=净值/原值；增加率=本期增加/期初原值；减少率=本期减少/期初原值；净变动率=(期末-期初)/期初；折旧覆盖率=累计折旧/原值；平均使用年限=原值/年折旧额；剩余年限=净值/年折旧额
3. THE Analysis_H1_6 SHALL 从H1-2明细表自动取数（各类期初/期末/增加/减少/折旧合计）
4. WHEN 成新率<20%时, THE Analysis_H1_6 SHALL 以黄色高亮该资产类别提示"老旧资产占比过高"
5. WHEN 增加率或减少率>50%时, THE Analysis_H1_6 SHALL 以红色高亮显示并在审计说明区自动标记需关注项
6. THE Analysis_H1_6 SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于异常项自动生成变动说明）和"审计结论"textarea
7. THE Analysis_H1_6 SHALL 通过GtIndexChip跳转H1-7增加/H1-8减少的对应检查详情
8. THE Analysis_H1_6 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 8: 增加检查表H1-7（含OCR+抽凭）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行固定资产增加检查, so that 我能逐笔核对新增资产的入账依据、金额准确性和资本化合规性。

#### Acceptance Criteria

1. THE Addition_Check_H1_7 SHALL 显示为双区域结构：(1)抽样参数区（测试总体/抽样方法/样本量/覆盖率） + (2)增加明细检查表
2. THE Addition_Check_H1_7 检查表 SHALL 显示24列（拆为固定列+滚动列）：固定列(序号/资产名称/资产编号/入账日期/原值) + 滚动列(合同/发票/验收单/付款凭证/资本化判断/入账科目/折旧起算日/审计结论/备注 等)
3. WHEN 用户点击"添加样本"按钮时, THE Addition_Check_H1_7 SHALL 新增一行可编辑空行
4. THE Addition_Check_H1_7 SHALL 集成抽凭引擎（voucher-sampling-engine），支持自动抽样后填充样本行
5. THE Addition_Check_H1_7 SHALL 在📎附件列支持行级OCR：上传后调用contract-ocr端点识别→ElMessageBox确认弹窗→merge填入对应字段
6. THE Addition_Check_H1_7 SHALL 在底部显示汇总：已检查笔数/检查金额合计/覆盖率(=检查金额/本期增加总额×100%)/发现异常笔数
7. THE Addition_Check_H1_7 SHALL 在底部显示"审计说明"textarea（AI生成按钮）和"审计结论"textarea
8. THE Addition_Check_H1_7 SHALL 在每行提供GtIndexChip，跳转至原始凭证来源
9. THE Addition_Check_H1_7 SHALL 支持导入导出（el-dropdown三级）
10. THE Addition_Check_H1_7 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 9: 减少检查表H1-8（含处置联动H10）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行固定资产减少检查, so that 我能逐笔核对处置/报废资产的审批流程和损益计算，并联动H10处置底稿。

#### Acceptance Criteria

1. THE Disposal_Check_H1_8 SHALL 显示为双区域结构：(1)抽样参数区 + (2)减少明细检查表
2. THE Disposal_Check_H1_8 检查表 SHALL 显示27列（拆为借方/贷方两区块视觉分组）：基础列(序号/资产名称/资产编号/处置日期/处置方式) | 借方区(原值/累计折旧/减值准备/处置收入) | 贷方区(净值/处置费用/处置损益) | 检查列(审批文件/评估报告/收款凭证/结论/备注)
3. THE Formula_Engine SHALL 自动计算每行：处置损益=处置收入-净值-处置费用；净值=原值-累计折旧-减值准备
4. WHEN 处置方式为"出售"且缺少评估报告时, THE Disposal_Check_H1_8 SHALL 以黄色高亮提示"关联方出售需评估定价"
5. WHEN 用户点击"添加样本"按钮时, THE Disposal_Check_H1_8 SHALL 新增一行可编辑空行
6. THE Disposal_Check_H1_8 SHALL 集成抽凭引擎（voucher-sampling-engine），支持自动抽样
7. THE Disposal_Check_H1_8 SHALL 在每行处置损益列提供GtIndexChip跳转至H10固定资产处置底稿
8. THE Disposal_Check_H1_8 SHALL 在底部显示汇总：已检查笔数/处置金额合计/处置损益合计/覆盖率
9. THE Disposal_Check_H1_8 SHALL 通过EventBus发布'h1:disposal-completed'事件通知H10
10. THE Disposal_Check_H1_8 SHALL 在底部显示"审计说明"textarea + AI按钮 + "审计结论"textarea + 复核💬
11. THE Disposal_Check_H1_8 SHALL 支持导入导出（el-dropdown三级）

### Requirement 10: 监盘组H1-9~H1-11（FixedAssetStocktakeDialog）

**User Story:** As a 审计助理, I want to 在精美HTML组件中完成固定资产监盘全流程（计划→盘点→小结）, so that 我能系统性记录盘点过程并追踪盘盈盘亏。

#### Acceptance Criteria

1. THE Stocktake_Plan_H1_9 SHALL 渲染为3区域：(1)监盘基本信息（盘点日期/地点/参与人/盘点范围/盘点方法） + (2)样本选取表（资产分类/选取标准/样本量/金额覆盖率） + (3)监盘时间安排表
2. THE Stocktake_Check_H1_10 SHALL 显示17列检查表：序号 | 资产名称 | 资产编号 | 存放地点 | 账面原值 | 账面净值 | 实际状态(在用/闲置/报废) | 实物照片 | 铭牌核对 | 数量核对 | 成色评估 | 盘点结果(账实相符/盘盈/盘亏) | 差异原因 | 差异金额 | 处理建议 | 盘点人 | 备注
3. THE Stocktake_Summary_H1_11 SHALL 渲染为段落型+表格混合：(1)监盘总体情况（统计仪表板） + (2)盘盈明细表 + (3)盘亏明细表 + (4)其他差异说明 + (5)监盘结论
4. THE Stocktake_Check_H1_10 SHALL 在底部自动汇总：已盘点资产数/盘盈数/盘亏数/账实相符率(=相符/已盘×100%)
5. WHEN 盘点结果为"盘亏"且差异金额>重要性水平时, THE Stocktake_Check_H1_10 SHALL 以红色高亮并标记"需追查"
6. THE 监盘组三sheet SHALL 共享FixedAssetStocktakeDialog组件（复用F循环InventoryStocktakeDialog模式），支持从H1-9计划直接发起盘点→H1-10记录→H1-11汇总
7. THE Stocktake_Summary_H1_11 SHALL 从H1-10自动汇总盘盈/盘亏明细并计算差异金额合计
8. THE Stocktake_Plan_H1_9 SHALL 在顶部显示蓝色渐变引导区（盘点三步流程：计划→执行→小结）
9. THE 监盘组 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
10. THE Stocktake_Check_H1_10 SHALL 支持导入导出（el-dropdown三级）

### Requirement 11: 折旧测算H1-12（4种方法+3分支版本+折旧引擎）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行固定资产折旧测算, so that 我能验证被审计单位折旧计提的准确性，支持4种折旧方法和3个分支版本切换。

#### Acceptance Criteria

1. THE H1-12 SHALL 提供分支选择器（el-segmented），在3个版本间切换：(A)不含减值-直线法 | (B)含减值 | (C)多次减值
2. THE Depreciation_Straight_H1_12 SHALL 显示28列（62公式）：资产分类 | 原值 | 残值率 | 残值 | 使用年限 | 已使用月数 | 月折旧额 | 1~12月折旧 | 本期计提合计 | 累计折旧(期初/本期/期末) | 账面折旧 | 差异 | 结论
3. THE Depreciation_Impair_H1_12 SHALL 在直线法基础上增加减值影响列（86公式）：减值准备 | 减值后净值 | 减值后月折旧额 | 减值前后折旧差异
4. THE Depreciation_Multi_H1_12 SHALL 在含减值基础上支持多次减值时点（94公式）：减值时点1/2/3 | 各时点后剩余年限 | 各时点后月折旧额
5. THE Depreciation_Engine SHALL 实现4种折旧方法的纯函数：
   - 直线法: 月折旧=(原值-残值)/使用年限/12
   - 双倍余额递减: 月折旧=净值×2/使用年限/12（最后两年转直线）
   - 年数总和法: 月折旧=(原值-残值)×剩余年限/年数总和/12
   - 工作量法: 单位折旧=(原值-残值)/预计总工作量; 月折旧=单位折旧×当月工作量
6. THE Formula_Engine SHALL 自动计算：本期计提合计=SUM(1~12月折旧)；累计折旧期末=期初+本期计提；差异=账面折旧-测算折旧
7. WHEN 差异绝对值>月折旧额时, THE H1-12 SHALL 以红色高亮差异单元格
8. THE H1-12 SHALL 月度累计折旧严格单调递增校验（除处置月份外），违反时黄色高亮
9. THE H1-12 SHALL 在底部显示汇总：测算折旧合计/账面折旧合计/总差异/差异率
10. THE H1-12 SHALL 在底部显示"审计说明"textarea + AI生成按钮 + "审计结论"textarea + 复核💬
11. THE H1-12 SHALL 从H1-2明细表自动取数（资产分类/原值/使用年限/残值率/折旧方法）
12. THE H1-12 SHALL 支持导入导出（el-dropdown三级）
13. THE H1-12 折旧引擎结果 SHALL 通过EventBus发布'h1:depreciation-calculated'事件供H1-13分配使用

### Requirement 12: 折旧分配H1-13（按部门分摊→D5/K8/K9）

**User Story:** As a 审计助理, I want to 在精美HTML表格中分析折旧费用的部门分配, so that 我能验证折旧是否正确分摊到制造费用(D5)/管理费用(K8)/销售费用(K9)。

#### Acceptance Criteria

1. THE Depreciation_Alloc_H1_13 SHALL 显示11列：资产分类 | 使用部门 | 对应费用科目 | 折旧金额 | 分配比例 | 分配至制造费用 | 分配至管理费用 | 分配至销售费用 | 账面金额 | 差异 | 备注
2. THE Formula_Engine SHALL 自动计算11个公式：分配比例=本类折旧/折旧总额×100%；各费用=折旧金额×分配比例；差异=分配金额-账面金额；合计行SUM
3. THE Depreciation_Alloc_H1_13 SHALL 从H1-12自动取数本期折旧合计（按资产分类聚合）
4. THE Depreciation_Alloc_H1_13 SHALL 在底部显示核对行：分配合计=H1-12折旧合计；制造费用=D5对应行；管理费用=K8对应行；销售费用=K9对应行
5. WHEN 分配差异≠0时, THE Depreciation_Alloc_H1_13 SHALL 以红色高亮差异行
6. THE Depreciation_Alloc_H1_13 SHALL 通过GtIndexChip提供跳转：制造费用→D5底稿/管理费用→K8底稿/销售费用→K9底稿
7. THE Depreciation_Alloc_H1_13 SHALL 通过EventBus发布'h1:depreciation-allocated'事件通知D5/K8/K9
8. THE Depreciation_Alloc_H1_13 SHALL 在底部显示"审计说明"textarea + AI按钮 + "审计结论"textarea + 复核💬

### Requirement 13: 减值H1-14~H1-15（DCF资产组+可收回金额）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行固定资产减值测试, so that 我能计算可收回金额并与账面价值比较确定是否需要计提减值。

#### Acceptance Criteria

1. THE Impairment_H1_14 SHALL 显示为双区域结构：(1)减值迹象判断区（6项迹象逐项Y/N/NA勾选） + (2)减值测算表（资产组 | 账面价值 | 公允价值减处置费用 | 预计未来现金流现值 | 可收回金额 | 减值金额 | 已计提 | 差异）
2. THE Formula_Engine SHALL 自动计算15个公式：可收回金额=MAX(公允价值减处置费用, 预计未来现金流现值)；减值金额=MAX(账面价值-可收回金额, 0)；差异=应计提-已计提
3. THE Recoverable_H1_15 SHALL 渲染为DCF模型表：(1)基本假设区（折现率/预测期/永续增长率） + (2)自由现金流预测表（Year1~Year5+永续期） + (3)折现计算区（各年折现因子/折现值/合计）
4. THE Formula_Engine SHALL 实现DCF公式：折现因子=1/(1+r)^n；折现值=现金流×折现因子；终值=永续现金流/(r-g)；可收回金额=SUM(折现值)+终值折现值
5. THE Recoverable_H1_15 SHALL 支持敏感性分析（折现率±1%/增长率±0.5%的矩阵表），自动计算各情景下的可收回金额
6. WHEN 账面价值>可收回金额时, THE Impairment_H1_14 SHALL 以红色高亮减值金额并在结论区自动标记"需计提减值"
7. THE Impairment_H1_14 SHALL 从H1-4闲置检查表自动引入有减值迹象的资产列表
8. THE Impairment_H1_14 SHALL 在"减值迹象判断区"提供方法论上下文（琥珀色左边线+浅黄背景，引用CAS8减值准则6项迹象）
9. THE 减值组 SHALL 在底部显示"审计说明"textarea + AI按钮 + "审计结论"textarea + 复核💬
10. THE Impairment_H1_14 SHALL 通过GtIndexChip跳转H1-15 DCF详细计算

### Requirement 14: 权属检查H1-16~H1-17

**User Story:** As a 审计助理, I want to 在精美HTML表格中逐项核验固定资产权属证明, so that 我能确认房屋建筑物的产权证和运输设备的行驶证/登记证信息完整。

#### Acceptance Criteria

1. THE Title_Building_H1_16 SHALL 显示22列检查表：序号 | 资产名称 | 坐落地址 | 建筑面积 | 土地面积 | 产权证号 | 发证日期 | 权利人 | 权利人是否为被审计单位 | 用途 | 是否抵押 | 抵押权人 | 抵押金额 | 抵押到期日 | 在建转固日期 | 账面原值 | 产权证载原值 | 差异 | 差异原因 | 是否限制 | 结论 | 备注
2. THE Title_Vehicle_H1_17 SHALL 显示18列检查表：序号 | 车辆名称 | 车牌号 | 车架号 | 发动机号 | 行驶证号 | 登记证号 | 登记日期 | 所有人 | 所有人是否为被审计单位 | 使用性质 | 是否抵押 | 账面原值 | 登记载明价值 | 差异 | 年检状态 | 结论 | 备注
3. WHEN 权利人/所有人不是被审计单位时, THE 权属检查表 SHALL 以红色高亮该行并标记"权属异常-需追查"
4. WHEN 存在抵押时, THE Title_Building_H1_16 SHALL 以黄色高亮该行并在附注提示区标记"需披露受限资产"
5. WHEN 用户点击"添加资产"按钮时, THE 权属检查表 SHALL 弹出ElMessageBox.prompt输入资产名称后新增一行
6. THE 权属检查表 SHALL 在底部显示汇总：已检查资产数/权属异常数/抵押资产数/抵押金额合计
7. THE Formula_Engine SHALL 自动计算差异=账面原值-证载原值
8. THE 权属检查表 SHALL 在底部显示"审计说明"textarea + AI按钮 + "审计结论"textarea + 复核💬
9. THE 权属检查表 SHALL 支持导入导出（el-dropdown三级）

### Requirement 15: 关联/租赁检查H1-18~H1-20

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查固定资产关联交易和租赁情况, so that 我能评估关联方交易定价公允性和经营/融资租出资产的合规性。

#### Acceptance Criteria

1. THE Related_Party_H1_18 SHALL 显示15列检查表：序号 | 资产名称 | 交易对方 | 关联关系 | 交易类型(购入/出售/租赁) | 交易日期 | 交易金额 | 账面价值 | 评估价值 | 定价依据 | 价格差异率 | 是否公允 | 审批文件 | 结论 | 备注
2. THE Formula_Engine SHALL 自动计算：价格差异率=(交易金额-评估价值)/评估价值×100%
3. WHEN 价格差异率绝对值>10%时, THE Related_Party_H1_18 SHALL 以红色高亮并标记"定价可能不公允"
4. THE Operating_Lease_H1_19 SHALL 显示25列检查表（23公式）：承租方 | 资产名称 | 原值 | 净值 | 租赁起止日 | 租赁期限 | 年租金 | 月租金 | 总租金收入 | 折旧分摊 | 维修费用 | 租赁净收益 | 收益率 | 市场租金参考 | 差异 | 合同编号 | 押金 | 到期日 | 续租条款 | 提前终止条款 | 是否关联 | 是否变更 | 会计处理 | 结论 | 备注
5. THE Formula_Engine SHALL 计算经营租出23公式：月租金=年租金/12；总租金收入=月租金×租赁月数；租赁净收益=总租金-折旧-维修；收益率=净收益/原值×100%；差异=年租金-市场租金
6. THE Finance_Lease_H1_20 SHALL 显示22列检查表：承租方 | 资产名称 | 原值 | 租赁分类依据(5项判断) | 最低租赁付款额 | 现值 | 未确认融资收益 | 分摊利率 | 各期利息收入 | 本金回收 | 期末余额 | 结论 | 备注
7. WHEN 用户点击"添加记录"按钮时, THE 关联/租赁检查表 SHALL 新增一行可编辑空行
8. THE 关联/租赁检查组 SHALL 在底部显示"审计说明"textarea + AI按钮 + "审计结论"textarea + 复核💬
9. THE Operating_Lease_H1_19 SHALL 支持导入导出（el-dropdown三级）
10. THE Related_Party_H1_18 SHALL 通过GtIndexChip跳转至关联方披露底稿

### Requirement 16: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑固定资产附注披露信息, so that 我能按上市公司/国企格式核对附注数据并与审定表自动取数对齐。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染为多子节卡片结构：(1)固定资产情况（原值/累计折旧/减值准备/账面价值，按资产分类×期初/增加/减少/期末矩阵） + (2)暂时闲置资产 + (3)融资租入资产 + (4)经营租出资产 + (5)抵押/担保受限资产 + (6)已全额折旧仍使用资产
2. THE Disclosure_SOE SHALL 渲染为多子节卡片结构（国企格式，与上市版类似但子节编号/格式略不同）
3. THE Cross_Sheet_Engine SHALL 从 Adjudication_H1_1 审定数自动取数填入附注第(1)子节对应行（原值期初/期末/增加/减少）
4. THE Cross_Sheet_Engine SHALL 从 Detail_H1_2 按资产分类聚合自动取数填入附注各分类行
5. WHILE 跨sheet引用值生效时, THE Disclosure_Listed SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
6. THE Disclosure_Listed 和 Disclosure_SOE SHALL 对动态行支持添加/删除（各子节内容行）
7. THE Disclosure_Listed 和 Disclosure_SOE SHALL 自动计算各子节合计行
8. THE Disclosure_Listed SHALL 根据项目applicable_standards（listed_standalone/listed_consolidated）自动显示；THE Disclosure_SOE SHALL 根据项目applicable_standards（soe_standalone/soe_consolidated）自动显示
9. WHEN 两种标准均不适用时, THE 附注sheet SHALL 隐藏对应Tab
10. THE 附注 SHALL 在每个子节底部放置"说明"textarea + EventBus发布'disclosure:note-text-updated'事件 + 编制提示折叠区

### Requirement 17: 跨Sheet/跨底稿联动

**User Story:** As a 审计助理, I want to H1各sheet之间及与其他底稿之间自动联动, so that 数据变更自动传播、无需手动对数。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 实现以下跨sheet computed链：H1-2合计→H1-1原值/折旧审定行；H1-12折旧合计→H1-13分配；H1-4闲置列表→H1-14减值迹象
2. THE Cross_Sheet_Engine SHALL 实现H1-1审定数→TB回写（科目1601借方+1602贷方），回写后发布'substantive:adjudicated'事件
3. THE Cross_Sheet_Engine SHALL 实现H1-12折旧→D5营业成本/K8管理费用/K9销售费用分摊联动（通过EventBus 'h1:depreciation-allocated'）
4. THE Cross_Sheet_Engine SHALL 实现H1-8处置→H10固定资产处置底稿联动（通过EventBus 'h1:disposal-completed'）
5. THE Cross_Sheet_Engine SHALL 监听C6前置完成事件（'control:c6-completed'），驱动H1A程序表前置状态更新
6. THE Cross_Sheet_Engine SHALL 实现附注数据联动：H1-1审定→附注第(1)子节；H1-4闲置→附注第(2)子节；H1-19经营租出→附注第(4)子节；权属检查→附注第(5)子节
7. THE Cross_Sheet_Engine SHALL 监听'adjustment:created'事件，自动将H1-3 AJE/RJE同步到H1-1审定表对应列
8. WHEN 跨sheet数据源值发生变化时, THE Cross_Sheet_Engine SHALL 以浅蓝色背景标记被联动单元格，tooltip显示"来自：H1-X第N行"
9. THE Cross_Sheet_Engine SHALL 监听附注模块subscribe 'substantive:adjudicated'刷新附注取数，并publish 'disclosure:note-text-updated'通知外部

### Requirement 18: 双模式+导入导出+AI辅助

**User Story:** As a 审计助理, I want to 在HTML精美组件与OnlyOffice之间自由切换，并支持导入导出和AI辅助, so that 我能按偏好选择编辑方式且不丢失数据。

#### Acceptance Criteria

1. THE useH1DualMode SHALL 提供HTML↔OnlyOffice切换（el-segmented），切换前自动保存当前数据
2. THE useH1DualMode SHALL 在切换到OnlyOffice前检查健康端点(`/api/workpapers/onlyoffice/health`)，不健康时禁止切换并提示
3. THE useH1ImportExport SHALL 提供el-dropdown三级操作：导出模板(空白结构xlsx)/导出数据(当前数据xlsx)/导入数据(xlsx→解析→确认→写入)
4. THE useH1ImportExport SHALL 对H1-2明细表54列导出时按4区段分sheet（基础/原值变动/折旧/减值）
5. THE AI_Assistant SHALL 支持以下section AI生成：adj-note(审计说明)/adj-conclusion(审计结论)/policy-evaluation(政策评价)/analysis-change(变动分析)/depreciation-summary(折旧汇总)/impairment-conclusion(减值结论)/stocktake-summary(监盘小结)/disposal-note(处置说明)
6. THE AI_Assistant SHALL 在调用/ai-generate端点前弹出确认预览对话框，用户确认后再填入目标textarea
7. THE useH1ImportExport SHALL 使用axios（非原生fetch）确保Authorization header正确传递
8. THE useH1ImportExport SHALL 对StreamingResponse中文文件名使用RFC5987编码

### Requirement 19: 持久化与金额格式化

**User Story:** As a 审计助理, I want to 所有编辑数据自动持久化且金额显示统一规范, so that 数据不丢失且报表阅读体验一致。

#### Acceptance Criteria

1. THE useH1FormData SHALL 实现自动保存：输入变更后debounce 2秒自动保存到checklist_responses（item_id="H1-{sheet}-{field}"）
2. THE useH1FormData SHALL 实现批量保存（saveBatch），支持跨字段原子性写入
3. THE useH1FormData SHALL 从render-config加载allResponses Map并computed响应式分发到各sheet composable
4. THE useH1FormData SHALL 支持projectContext加载（含business_category/applicable_standards用于附注/IPO判断）
5. THE 所有金额列 SHALL 应用统一格式化规则：千分位分隔/负数红色括号/零值显示"-"/右对齐/字体13px
6. THE 所有公式计算列 SHALL 显示虚线下划线+cursor:help+tooltip显示公式来源
7. THE 所有百分比列 SHALL 保留2位小数并加%后缀
8. THE useH1FormData SHALL 在加载时自动从TB取数科目1601+1602的unadjusted_amount填入审定表"未审数"（selfLoad取数）
9. THE useH1FormData SHALL 在保存失败时显示el-message错误提示并保留本地数据不丢失（乐观更新+回滚）
