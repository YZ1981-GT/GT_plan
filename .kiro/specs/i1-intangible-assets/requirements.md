# Requirements Document: I1 无形资产、累计摊销及减值准备底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + I2资本化转入联动
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useI1ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，AC引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase排序

## Introduction

I1无形资产、累计摊销及减值准备底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `i1-intangible-assets`，覆盖来自 `I1 无形资产、累计摊销及减值准备.xlsx` 的18个有效sheet。科目覆盖1701无形资产（借方/资产类）+ 1702累计摊销（贷方/资产备抵类）+ 1703无形资产减值准备（贷方/资产备抵类）。

核心关注：资产类三角勾稽（期末=期初+增加-减少）、摊销引擎（直线法为主/剩余年限法）、减值DCF测试、使用寿命检查、权属逐项核验、摊销分支选择器（I1-10不含减值 vs I1-11含减值）、I2资本化转入联动。关键公式总数约200+。

## Glossary

- **Tab_Index**: 底稿目录，32行13列，sheet导航+进度统计
- **Procedure_Table_I1A**: 无形资产实质性程序表I1A，28行11列，审计程序清单（复用a-program-console）
- **Adjudication_I1**: 审定表I1，93行9列51公式，三科目审定（1701+1702+1703）
- **Disclosure_Listed**: 附注披露信息（上市公司），64行22列34公式
- **Disclosure_SOE**: 附注披露信息（国有企业），67行14列26公式
- **Detail_I1_2**: 明细表I1-2，41行56列18公式 — 宽表需拆分
- **Adjustment_I1_3**: 调整分录汇总I1-3，21行10列
- **Policy_Check_I1_4**: 无形资产摊销减值政策检查表I1-4，32行15列
- **Addition_Check_I1_5**: 无形资产增加检查表I1-5，37行19列
- **Disposal_Check_I1_6**: 无形资产减少明细表I1-6，41行14列
- **UsefulLife_Check_I1_7**: 使用寿命检查表I1-7，27行17列
- **Title_Check_I1_8**: 无形资产权属检查表I1-8，94行21列
- **Amortization_Alloc_I1_9**: 摊销分配分析表I1-9，29行10列7公式
- **Amortization_NoImpair_I1_10**: 摊销测算表（不含减值）I1-10，33行28列30公式（剩余年限法）
- **Amortization_WithImpair_I1_11**: 摊销测算表（含减值）I1-11，32行28列63公式
- **Impairment_Test_I1_12**: 减值准备测试表I1-12，43行32列14公式
- **Recoverable_Test_I1_13**: 可收回金额测试I1-13，51行28列10公式
- **Branch_Selector**: 分支选择器，I1-10/I1-11两版本切换（不含减值/含减值）
- **Amortization_Engine**: 摊销计算引擎，直线法（剩余年限法）
- **Triangle_Reconciliation**: 三角勾稽，期末=期初+增加-减少（原值/摊销/减值三层）
- **Cross_Sheet_Engine**: 跨sheet公式引擎
- **Formula_Engine**: 前端公式引擎composable
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转芯片
- **Review_Dialog**: 通用复核对话组件
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1701+1702+1703）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I1无形资产底稿按sheetName prop分发到独立子组件, so that 18个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE I1 组件 SHALL 注册新componentType: `i1-intangible-assets`，主入口为 GtI1IntangibleAssets.vue
2. THE GtI1IntangibleAssets.vue SHALL 接收 `sheetName` prop（完整中文名），用正则提取末尾编码(I1-2/I1-3/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE I1 组件 SHALL 使用 defineAsyncComponent 对所有子组件懒加载
4. THE I1 组件 SHALL 将子组件按功能域拆分为：i1/core/、i1/inspection/、i1/amortization/、i1/impairment/
5. THE I1 组件 SHALL 拆分为composable层：useI1FormData + useI1FormulaEngine(纯函数) + useI1AmortizationEngine(纯函数) + useI1CrossSheet + useI1DualMode + useI1ImportExport
6. THE I1 组件 SHALL 在htmlRendererRegistry中注册'i1-intangible-assets'→GtI1IntangibleAssets映射
7. THE I1 组件 SHALL 在wp_code_overrides.json中将I1/I1-2~I1-13/I1A映射为'i1-intangible-assets'
8. THE I1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'i1-intangible-assets'
9. THE GtI1IntangibleAssets.vue SHALL 支持selfLoad
10. THE I1 组件 SHALL 使用 checklist_responses 存储，item_id前缀"I1-{sheet编号}-{field}"

### Requirement 2: 审定表I1（三科目审定+三角勾稽）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看无形资产审定数据, so that 我能清晰地看到三科目(原值+累计摊销+减值准备)的审定数并验证三角勾稽。

#### Acceptance Criteria

1. THE Adjudication_I1 SHALL 渲染为三区块固定结构：一、无形资产-原值（分类行+小计）→ 二、累计摊销（分类行+小计）→ 三、减值准备（分类行+小计）→ 无形资产净值合计
2. THE Adjudication_I1 SHALL 显示以下列：项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额 | 未审数 | AJE | RJE | 审定数
3. WHEN 用户编辑未审数/AJE/RJE时, THE Formula_Engine SHALL 自动计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 对原值区块自动校验：期末=期初+增加-减少（资产类借方科目1701）
5. THE Formula_Engine SHALL 对累计摊销区块自动校验：期末=期初+贷方发生-借方发生（备抵类1702）
6. THE Formula_Engine SHALL 对减值准备区块自动校验：期末=期初+贷方发生-借方发生（备抵类1703）
7. THE Adjudication_I1 SHALL 自动计算净值合计=原值小计-摊销小计-减值小计
8. THE Adjudication_I1 SHALL 实施三角勾稽校验，失败时红色高亮并显示差额
9. THE Adjudication_I1 SHALL 在底部显示TB取数行（科目1701+1702+1703）和差异行
10. WHEN 审定数变化时, THE Adjudication_I1 SHALL writebackTrialBalance（科目1701+1702+1703）并发布'substantive:adjudicated'事件
11. THE Adjudication_I1 SHALL 在底部显示"审计说明"+"审计结论"+复核对话入口

### Requirement 3: 明细表I1-2（56列宽表拆分）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理无形资产明细, so that 我能通过区段Tab分别查看基础信息/原值变动/摊销/减值。

#### Acceptance Criteria

1. THE Detail_I1_2 SHALL 将56列拆分为4区段Tab：基础(类型/名称/取得日期/使用寿命/残值率/摊销方法) | 原值变动(期初/增加/减少/期末) | 摊销(累计摊销期初/本期摊销/摊销转出/期末/净值) | 减值(减值期初/计提/转回/期末)
2. THE Detail_I1_2 SHALL 切换Tab时保持行同步
3. THE Formula_Engine SHALL 自动计算每行：期末原值=期初+增加-减少；累计摊销期末=期初+摊销-转出；减值期末=期初+计提-转回；净值=原值期末-摊销期末-减值期末
4. THE Detail_I1_2 SHALL 显示合计行（不可编辑），与I1审定表交叉验证
5. WHEN 合计行与审定表不一致时, THE Detail_I1_2 SHALL 显示黄色警告
6. THE Detail_I1_2 SHALL 支持动态行添加（弹ElMessageBox.prompt输入名称）
7. THE Detail_I1_2 SHALL 支持导入导出三级

### Requirement 4: 调整分录I1-3

**User Story:** As a 审计助理, I want to 管理无形资产调整分录, so that AJE/RJE能联动审定表。

#### Acceptance Criteria

1. THE Adjustment_I1_3 SHALL 显示10列：序号|调整事项|类别(AJE/RJE)|科目代码|科目名称|摘要|借方|贷方|索引|备注
2. THE Adjustment_I1_3 SHALL 新增行+借贷平衡校验
3. WHEN 保存时, THE Adjustment_I1_3 SHALL EventBus发布'adjustment:created'并同步至审定表
4. THE Adjustment_I1_3 SHALL 支持推送至A13错报汇总
5. THE Adjustment_I1_3 SHALL 支持导入导出三级

### Requirement 5: 摊销减值政策检查表I1-4

**User Story:** As a 审计助理, I want to 检查无形资产摊销和减值政策, so that 我能验证会计政策的适当性和一致性。

#### Acceptance Criteria

1. THE Policy_Check_I1_4 SHALL 渲染为段落型检查（CAS6+CAS8段落引用）
2. THE Policy_Check_I1_4 SHALL 包含：摊销方法/使用寿命/残值率/减值迹象判断/减值测试频率等检查项
3. THE Policy_Check_I1_4 SHALL 提供逐项勾选(是/否/不适用)结论选择
4. THE Policy_Check_I1_4 SHALL 顶部蓝色引导区+琥珀色方法论

### Requirement 6: 增加检查表I1-5

**User Story:** As a 审计助理, I want to 检查无形资产新增项目, so that 我能验证入账价值和取得方式的正确性。

#### Acceptance Criteria

1. THE Addition_Check_I1_5 SHALL 显示：序号|名称|取得方式|入账日期|入账金额|合同/发票号|支付方式|审查结论
2. THE Addition_Check_I1_5 SHALL 支持动态行+OCR附件列
3. THE Addition_Check_I1_5 SHALL 增加合计行，联动审定表"本期增加"
4. THE Addition_Check_I1_5 SHALL 支持抽凭引擎

### Requirement 7: 减少明细表I1-6

**User Story:** As a 审计助理, I want to 记录无形资产减少明细, so that 我能追踪处置/报废项目。

#### Acceptance Criteria

1. THE Disposal_Check_I1_6 SHALL 显示14列：序号|名称|原值|累计摊销|减值|净值|处置方式|处置收入|处置损益|审批文件|日期|结论
2. THE Disposal_Check_I1_6 SHALL 计算处置损益=收入-净值
3. THE Disposal_Check_I1_6 SHALL 合计联动审定表"本期减少"
4. THE Disposal_Check_I1_6 SHALL 支持动态行

### Requirement 8: 使用寿命检查表I1-7

**User Story:** As a 审计助理, I want to 检查各无形资产使用寿命估计, so that 我能评估寿命估计的合理性。

#### Acceptance Criteria

1. THE UsefulLife_Check_I1_7 SHALL 显示：名称|原始寿命|已用年限|剩余年限|寿命依据|本期是否变更|变更原因|结论
2. THE UsefulLife_Check_I1_7 SHALL 对使用寿命不确定的项标注"不摊销"并与减值测试关联
3. THE UsefulLife_Check_I1_7 SHALL 联动I1-10/I1-11摊销测算的使用寿命参数

### Requirement 9: 权属检查表I1-8

**User Story:** As a 审计助理, I want to 逐项核查无形资产权属, so that 我能确认所有权归属和法律效力。

#### Acceptance Criteria

1. THE Title_Check_I1_8 SHALL 显示21列（94行大表）：序号|名称|类型|证书编号|登记日期|有效期|权利人|是否与账面一致|差异说明|结论...
2. THE Title_Check_I1_8 SHALL 支持按类型分组（专利/商标/著作权/土地使用权/软件等）
3. THE Title_Check_I1_8 SHALL 计算差异金额=账面-权证
4. THE Title_Check_I1_8 SHALL 支持虚拟滚动(94行大表)

### Requirement 10: 摊销分配分析表I1-9

**User Story:** As a 审计助理, I want to 分析摊销费用在各部门间的分配, so that 我能验证摊销计入正确的费用科目。

#### Acceptance Criteria

1. THE Amortization_Alloc_I1_9 SHALL 显示：资产名称|摊销总额|管理费用|销售费用|制造费用|研发费用|其他|合计|分配比例
2. THE Formula_Engine SHALL 校验各行分配合计=摊销总额
3. THE Amortization_Alloc_I1_9 SHALL 通过GtIndexChip联动K8/K9/D5/I6
4. THE Amortization_Alloc_I1_9 SHALL 底部合计行自动SUM

### Requirement 11: 摊销测算分支选择器（I1-10/I1-11）

**User Story:** As a 审计助理, I want to 在两种摊销测算版本间切换, so that 我能根据是否存在减值选择正确的测算表。

#### Acceptance Criteria

1. THE Branch_Selector SHALL 使用el-segmented切换："不含减值（I1-10）" / "含减值（I1-11）"
2. WHEN 选择"不含减值"时, THE 组件 SHALL 渲染I1TabAmortizationNoImpair.vue（剩余年限法，30公式）
3. WHEN 选择"含减值"时, THE 组件 SHALL 渲染I1TabAmortizationWithImpair.vue（63公式）
4. THE Amortization_Engine SHALL 计算：月摊销额=（原值-残值-累计摊销-减值准备）÷剩余月数
5. THE Amortization_Engine SHALL 对含减值版本在减值发生月重新计算剩余摊销基数
6. THE 摊销测算表 SHALL 显示每资产每月摊销额横向矩阵（28列宽表）
7. THE 摊销测算表 SHALL 底部合计行联动I1-9摊销分配

### Requirement 12: 减值准备测试I1-12

**User Story:** As a 审计助理, I want to 对无形资产执行减值测试, so that 我能识别需计提减值的资产。

#### Acceptance Criteria

1. THE Impairment_Test_I1_12 SHALL 显示：资产名称|账面原值|累计摊销|减值准备|账面净值|可收回金额|应计提减值|已计提|差额|结论
2. THE Formula_Engine SHALL 计算：账面净值=原值-摊销-已有减值；应计提=MAX(账面净值-可收回金额, 0)
3. THE Impairment_Test_I1_12 SHALL 可收回金额列链接I1-13详细测试结果
4. THE Impairment_Test_I1_12 SHALL 差额≠0时红色高亮

### Requirement 13: 可收回金额测试I1-13（DCF）

**User Story:** As a 审计助理, I want to 通过DCF模型测算无形资产可收回金额, so that 我能确定减值金额。

#### Acceptance Criteria

1. THE Recoverable_Test_I1_13 SHALL 显示DCF测算表：预测期现金流(5年) + 折现率 + 终值 + 现值合计
2. THE Formula_Engine SHALL 计算：PV=Σ(CF_i/(1+r)^i) + TV/(1+r)^n
3. THE Recoverable_Test_I1_13 SHALL 计算可收回金额=MAX(公允价值-处置费用, 使用价值DCF)
4. THE Recoverable_Test_I1_13 SHALL 联动I1-12填入可收回金额
5. THE Recoverable_Test_I1_13 SHALL 提供敏感性分析（折现率±1%/增长率±0.5%对结果影响）

### Requirement 14: 附注披露（上市+国企双版本）

**User Story:** As a 审计助理, I want to 自动生成无形资产附注披露内容, so that 我能快速产出符合格式的披露信息。

#### Acceptance Criteria

1. THE Disclosure SHALL 提供variant双版本（上市64×22/国企67×14），根据projectContext.business_category自动选择
2. THE Disclosure SHALL 从审定表/明细表/摊销表自动取数填入对应附注位置
3. THE Disclosure SHALL 支持AI辅助生成文字描述部分
4. THE Disclosure SHALL EventBus发布'disclosure:note-text-updated'联动报表附注
