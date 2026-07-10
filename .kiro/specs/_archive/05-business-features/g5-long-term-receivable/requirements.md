# Requirements Document

## Introduction

G5长期应收款底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g5-long-term-receivable`，覆盖1个xlsx源模板中的16个有效sheet。科目1531长期应收款（借方/资产类）。**G循环中涉及融资租赁和保理业务的重要科目**，包含内含利率法摊销、保理终止确认核查、ECL三阶段减值等特色审计内容。

**单spec覆盖全部16个sheet**（超12阈值，采用子目录组织）：

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 27×8 | 目录页 |
| 2 | 长期应收款实质性程序表G5A | 31×14 | a-program-console |
| 3 | 审定表G5-1 | 87×13 | 多层审定（原值+坏账+净值+一年内到期） |
| 4 | 附注披露信息（上市公司） | 113×11 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 109×12 | 国企附注 |
| 6 | 余额明细表G5-2 | 115×22 | 22列宽表，按债务人×到期日×金额分解 |
| 7 | 坏账准备明细表G5-3 | 41×20 | 坏账准备按组合/单项 |
| 8 | 调整分录汇总G5-4 | 24×10 | AJE/RJE |
| 9 | 未实现融资收益测算表（租赁）G5-5 | 48×18 | **特色**：融资租赁内含利率法测算 |
| 10 | 未实现融资收益测算表（销售）G5-6 | 43×11 | 分期收款销售测算 |
| 11 | 长期应收款保理核查表G5-7 | 38×9 | 保理业务核查 |
| 12 | 信用减值损失会计政策检查G5-8 | 46×15 | 会计政策合规检查 |
| 13 | 长期应收款三阶段划分G5-9 | 58×16384 | 三阶段划分（列式转置结构，同G4-9） |
| 14 | 长期应收款坏账准备测算G5-10 | 63×19 | ECL测算（公式链同G4-10） |
| 15 | 减值准备转回（收回）、核销检查表G5-11 | 42×20 | 转回核销检查 |
| 16 | 凭证检查表G5-12 | 99×21 | 凭证检查+OCR |

**科目属性**：
- 科目代码：1531 长期应收款
- 方向：借方（资产类）
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**关键特色（区别于G4）**：
1. **未实现融资收益**：租赁(G5-5)用内含利率法摊销、销售(G5-6)用实际利率法
2. **保理核查**：长期应收款保理是否满足终止确认条件(G5-7)
3. **87行超大审定表**：按债务人/交易类型分层，比G4复杂
4. **G5-9三阶段同样是列式转置结构**（16384列=合并单元格，债务人为列）

**宽表处理策略**：
- G5-2余额明细(22列)：2区段Tab（债务人基础信息/余额分析+账龄）
- G5-3坏账准备(20列)：2区段Tab（未审数+审计调整/审定数）
- G5-5融资租赁测算(18列)：2区段Tab（租赁基础信息/摊销计算）
- G5-10坏账测算(19列)：2区段Tab（未审+调整/审定数）
- G5-11转回核销(20列)：2区段Tab（转回检查/核销检查）
- G5-12凭证检查(21列)：3区段Tab（凭证基础/核对内容/结论）

**子目录组织**（16 sheets > 12 threshold）：
- core/: G5A+G5-1+G5-2+G5-3+G5-4+附注(上市/国企)+底稿目录
- measurement/: G5-5(租赁)+G5-6(销售)+G5-7(保理)+G5-8(政策检查)
- impairment/: G5-9(三阶段)+G5-10(坏账测算)+G5-11(转回核销)
- voucher/: G5-12(凭证检查)

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ✅ 抽凭引擎: G5-12凭证检查表集成GtVoucherSamplingEngine dialog
- ✅ 截止自动提取: G5A程序表集成useCutoffAutoSampling
- ✅ 附注EventBus: subscribe substantive:adjudicated / publish disclosure:note-text-updated
- ✅ 行级OCR: G5-12凭证检查表📎列OCR识别
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **Long_Term_Receivable**: 长期应收款，企业因融资租赁、分期收款销售商品等业务产生的超过1年的应收款项（科目1531）
- **Unrealized_Financing_Income**: 未实现融资收益，长期应收款确认时名义金额与公允价值的差额，在租赁期/收款期内按内含利率法/实际利率法分期摊销确认收入
- **Implicit_Interest_Rate**: 内含利率，使出租人的租赁收款额现值+未担保余值现值=租赁资产公允价值+初始直接费用的折现率
- **Effective_Interest_Rate**: 实际利率，使分期收款销售预期未来现金流量的现值等于合同约定应收总额现值的利率
- **Factoring**: 保理，企业将应收账款/长期应收款转让给保理商获取资金的业务，需判断是否满足终止确认条件
- **Derecognition**: 终止确认，金融资产转移后已将金融资产所有权上几乎所有风险和报酬转移给转入方时终止确认
- **ECL**: Expected Credit Loss，预期信用损失，IFRS9/CAS22要求的金融资产减值计量方法
- **Stage_Classification**: 三阶段划分（Stage1/Stage2/Stage3），根据信用风险变化程度确定减值计提方法
- **Bad_Debt_Provision**: 坏账准备，对长期应收款计提的减值准备
- **Credit_Loss_Rate**: 信用损失率，预期信用损失占账面余额的比率
- **Adjudication_Table**: 审定表(G5-1)，87行多层结构：原值+坏账+净值+一年内到期
- **Detail_Table**: 余额明细表(G5-2)，22列按债务人×到期日×金额分解
- **Lease_Amortization**: 融资租赁摊销测算(G5-5)，内含利率法：利息收入 = 期初净投资额 × 内含利率
- **Installment_Sales**: 分期收款销售测算(G5-6)，实际利率法：利息收入 = 期初摊余成本 × 实际利率
- **Net_Investment**: 净投资额，融资租赁中出租人应收款项总额减去未实现融资收益的净额
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）
- **Formula_Chain**: 公式链，G5-10坏账测算表的审计调整列间计算关系（同G4-10：⑥=⑤×②A+①×(②A-②)）
- **G5_Component**: g5-long-term-receivable专属组件，单spec覆盖全部16个sheet

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G5长期应收款底稿按sheetName prop分发到独立子组件, so that 16个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G5-Long-Term-Receivable 组件 SHALL 注册新componentType: `g5-long-term-receivable`，主入口为 GtG5LongTermReceivable.vue（接收sheetName prop，v-if分发到子组件）
1.2 THE G5-Long-Term-Receivable 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（16个sheet按需加载）
1.3 THE G5-Long-Term-Receivable 组件 SHALL 在htmlRendererRegistry中注册'g5-long-term-receivable'→GtG5LongTermReceivable映射
1.4 THE G5-Long-Term-Receivable 组件 SHALL 在wp_code_overrides.json中将G5A、G5-1~G5-12、附注披露(上市/国企)、底稿目录的componentType统一映射为'g5-long-term-receivable'（16个wp_code条目）
1.5 THE G5-Long-Term-Receivable 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g5-long-term-receivable'
1.6 IF htmlData prop为null, THEN THE GtG5LongTermReceivable.vue SHALL 自行调用render-config?force_component_type=g5-long-term-receivable获取渲染数据（selfLoad模式）
1.7 IF sheetName正则提取编码失败或提取的编码不在已迁移子组件列表中, THEN THE GtG5LongTermReceivable.vue SHALL 渲染OnlyOffice fallback组件
1.8 THE 子组件 SHALL 按子目录组织：core/(G5A+G5-1+G5-2+G5-3+G5-4+附注(上市/国企)+底稿目录) / measurement/(G5-5+G5-6+G5-7+G5-8) / impairment/(G5-9+G5-10+G5-11) / voucher/(G5-12)

### Requirement 2: G5A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行长期应收款实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE G5A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G5A程序表 SHALL 显示31行×14列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G5A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑
2.4 THE G5A程序表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式）
2.5 THE G5A程序表 SHALL 集成useCutoffAutoSampling截止自动提取（序时账±5天）

### Requirement 3: 审定表G5-1（87行多层结构，借方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写长期应收款审定表, so that 我能汇总原值/坏账/净值/一年内到期的审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G5-1审定表 SHALL 显示87行×13列多层结构，按数据分组：
   - **一、长期应收款原值**：按债务人/交易类型分层（融资租赁/分期销售/保理/其他）小计
   - **二、坏账准备**：按组合计提/单项计提/小计
   - **三、长期应收款净值**（= 原值小计 - 坏账准备小计）
   - **四、减：一年内到期非流动资产**（重分类列报）
   - **五、长期应收款报表列示数**（= 净值 - 一年内到期）
3.2 THE G5-1审定表 SHALL 列结构：项目|期初(未审|AJE|RJE|审定)|期末(未审|AJE|RJE|审定)|变动额|变动率|原因分析
3.3 THE G5-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
3.4 THE G5-1审定表 SHALL 实现审定数公式：审定 = 未审 + AJE + RJE
3.5 THE Formula_Engine SHALL 计算长期应收款净值 = 原值小计 - 坏账准备小计
3.6 THE Formula_Engine SHALL 计算报表列示数 = 净值 - 一年内到期
3.7 THE G5-1审定表 SHALL 分组小计自动汇总（按债务人/交易类型小计→原值大计→坏账大计→净值→报表数）
3.8 THE G5-1审定表 SHALL 试算表数从trial_balance自动取数（科目1531）
3.9 THE G5-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.10 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1531', adjudicatedAmount=报表列示数审定数）
3.11 THE G5-1审定表 SHALL 变动率公式：变动率 = (期末审定 - 期初审定) / 期初审定 × 100%
3.12 WHEN |变动率|>20%时, THE 系统 SHALL 以橙色高亮并要求填写原因分析
3.13 THE G5-1审定表 SHALL 87行启用虚拟滚动，支持展开/折叠分组（默认展开）

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑长期应收款附注披露, so that 我能按上市/国企格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示113行×11列结构化表格（启用虚拟滚动）
4.2 THE 附注披露(国企) SHALL 显示109行×12列结构化表格（启用虚拟滚动）
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1531')自动刷新审定数据
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露 SHALL 每个文本区提供AI辅助按钮（section标题行右侧）

### Requirement 5: 余额明细表G5-2（22列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看长期应收款逐笔余额明细, so that 我能检查每笔应收款的债务人/到期日/金额分解和账龄。

#### Acceptance Criteria

5.1 THE G5-2余额明细表 SHALL 显示115行×22列，拆为2区段Tab：
   - **Tab1: 债务人基础信息(10列)**：序号|债务人名称|业务类型(融资租赁/分期销售/保理/其他 下拉)|合同编号|起始日|到期日|合同总额|已收回金额|期末余额(公式)|是否关联方(是/否)
   - **Tab2: 余额分析+账龄(12列)**：序号|债务人名称|未实现融资收益|净额(公式)|1年以内|1-2年|2-3年|3-4年|4-5年|5年以上|账龄合计(公式)|备注
5.2 THE Formula_Engine SHALL 计算期末余额 = 合同总额 - 已收回金额
5.3 THE Formula_Engine SHALL 计算净额 = 期末余额 - 未实现融资收益（长期应收款账面余额减去未摊销的融资收益）
5.4 THE Formula_Engine SHALL 计算账龄合计 = 1年以内 + 1-2年 + 2-3年 + 3-4年 + 4-5年 + 5年以上
5.5 WHEN 账龄合计 ≠ 净额时, THE 系统 SHALL 以红色高亮该行并提示"账龄分布与净额不一致"
5.6 THE G5-2余额明细表 SHALL 115行启用虚拟滚动
5.7 THE G5-2余额明细表 SHALL 底部显示合计行（合同总额合计/已收回合计/期末余额合计/净额合计/各账龄段合计）
5.8 WHEN 用户切换区段Tab时, THE G5-2余额明细表 SHALL 保持当前选中行的行索引不变（行同步）
5.9 THE G5-2余额明细表 SHALL 支持动态行增删（ElMessageBox.prompt输入债务人名称）+ 导入导出

### Requirement 6: 坏账准备明细表G5-3（20列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中填写坏账准备明细, so that 我能按组合/单项核实坏账计提的完整性和准确性。

#### Acceptance Criteria

6.1 THE G5-3坏账准备明细表 SHALL 显示41行×20列，拆为2区段Tab：
   - **Tab1: 未审数+审计调整(11列)**：序号|债务人/组合名称|计提方式(组合/单项 下拉)|期末余额|信用损失率|未审坏账准备(公式)|余额调整|调整后损失率|坏账调整(公式)|调整说明|索引
   - **Tab2: 审定数(9列)**：序号|债务人/组合名称|审定余额(公式)|审定坏账准备(公式)|审定净值(公式)|上年坏账准备|本年计提(公式)|本年转回|备注
6.2 THE Formula_Engine SHALL 计算未审坏账准备 = 期末余额 × 信用损失率
6.3 THE Formula_Engine SHALL 计算坏账调整 = 余额调整 × 调整后损失率 + 期末余额 × (调整后损失率 - 信用损失率)（同G4-10公式：⑥=⑤×②A+①×(②A-②)）
6.4 THE Formula_Engine SHALL 计算审定余额 = 期末余额 + 余额调整
6.5 THE Formula_Engine SHALL 计算审定坏账准备 = 未审坏账准备 + 坏账调整
6.6 THE Formula_Engine SHALL 计算审定净值 = 审定余额 - 审定坏账准备
6.7 THE Formula_Engine SHALL 计算本年计提 = 审定坏账准备 - 上年坏账准备 + 本年转回
6.8 THE G5-3坏账准备明细表 SHALL 按计提方式分组：组合计提行/单项计提行/合计行
6.9 WHEN 用户切换区段Tab时, THE G5-3坏账准备明细表 SHALL 保持当前行索引（行同步）
6.10 THE G5-3坏账准备明细表 SHALL 支持动态行增删（ElMessageBox.prompt输入债务人名称）+ 导入导出

### Requirement 7: 调整分录汇总G5-4

**User Story:** As a 审计助理, I want to 在精美HTML中录入长期应收款调整分录, so that 我能记录AJE/RJE并回写审定表。

#### Acceptance Criteria

7.1 THE G5-4调整分录 SHALL 显示24行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
7.2 THE G5-4调整分录 SHALL 借贷平衡校验：|SUM(借方) - SUM(贷方)| < 0.01
7.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
7.4 THE G5-4调整分录 SHALL 支持动态行增删（ElMessageBox.prompt输入摘要）+ 导入导出
7.5 WHEN 调整分录保存时, THE 系统 SHALL 自动汇总AJE/RJE金额回写G5-1审定表

### Requirement 8: 未实现融资收益测算表（租赁）G5-5（18列→2区段Tab，内含利率法）

**User Story:** As a 审计助理, I want to 在精美HTML中测算融资租赁的未实现融资收益摊销, so that 我能验证企业使用内含利率法确认融资收益的正确性。

#### Acceptance Criteria

8.1 THE G5-5融资租赁测算表 SHALL 显示48行×18列，拆为2区段Tab：
   - **Tab1: 租赁基础信息(8列)**：租赁项目名称|承租人|租赁开始日|租赁到期日|最低租赁收款额|未担保余值|租赁资产公允价值|内含利率
   - **Tab2: 摊销计算(10列)**：期次|期初应收融资租赁款|期初未实现融资收益|期初净投资额(公式)|本期融资收益(公式)|本期收款额|期末应收融资租赁款(公式)|期末未实现融资收益(公式)|期末净投资额(公式)|差异(公式)
8.2 THE Formula_Engine SHALL 计算期初净投资额 = 期初应收融资租赁款 - 期初未实现融资收益
8.3 THE Formula_Engine SHALL 计算本期融资收益 = 期初净投资额 × 内含利率（内含利率法核心公式）
8.4 THE Formula_Engine SHALL 计算期末应收融资租赁款 = 期初应收融资租赁款 - 本期收款额
8.5 THE Formula_Engine SHALL 计算期末未实现融资收益 = 期初未实现融资收益 - 本期融资收益
8.6 THE Formula_Engine SHALL 计算期末净投资额 = 期末应收融资租赁款 - 期末未实现融资收益
8.7 THE Formula_Engine SHALL 计算差异 = 本期融资收益(审计测算) - 本期融资收益(企业账面)，差异>重要性水平时红色高亮
8.8 THE G5-5 SHALL 每个租赁项目独立成组（Tab1一行对应Tab2多行摊销期间），组间以分隔线和项目名称标题区分
8.9 THE G5-5 SHALL 验证期间连续性：第N期的期初值 = 第N-1期的期末值（期初应收=上期期末应收，期初未实现=上期期末未实现）
8.10 THE G5-5 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
8.11 THE G5-5 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示内含利率法公式说明
8.12 THE G5-5 SHALL 支持Tab2动态行增删（新增租赁项目时ElMessageBox.prompt输入项目名称）+ 导入导出

### Requirement 9: 未实现融资收益测算表（销售）G5-6（实际利率法）

**User Story:** As a 审计助理, I want to 在精美HTML中测算分期收款销售的未实现融资收益摊销, so that 我能验证企业使用实际利率法确认融资收益的正确性。

#### Acceptance Criteria

9.1 THE G5-6分期销售测算表 SHALL 显示43行×11列，分为两个section：
   - **(一) 确定初始交易要素(6列)**：销售项目|合同约定应收总额|商品公允价值|未实现融资收益(公式)|实际利率|收款期限
   - **(二) 分期摊销计算(8列)**：期次|期初应收款余额|期初未实现融资收益|期初摊余成本(公式)|本期融资收益(公式)|本期收款额|期末应收款余额(公式)|期末摊余成本(公式)
9.2 THE Formula_Engine SHALL 计算未实现融资收益 = 合同约定应收总额 - 商品公允价值
9.3 THE Formula_Engine SHALL 计算期初摊余成本 = 期初应收款余额 - 期初未实现融资收益
9.4 THE Formula_Engine SHALL 计算本期融资收益 = 期初摊余成本 × 实际利率（实际利率法核心公式）
9.5 THE Formula_Engine SHALL 计算期末应收款余额 = 期初应收款余额 - 本期收款额
9.6 THE Formula_Engine SHALL 计算期末摊余成本 = 期初摊余成本 + 本期融资收益 - 本期收款额
9.7 THE G5-6 SHALL 每个销售项目独立成组，组内section(二)多行代表各收款期间
9.8 THE G5-6 SHALL 验证期间连续性：第N期的期初值 = 第N-1期的期末值
9.9 THE G5-6 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
9.10 THE G5-6 SHALL 支持动态行增删（ElMessageBox.prompt输入销售项目名称）+ 导入导出

### Requirement 10: 长期应收款保理核查表G5-7

**User Story:** As a 审计助理, I want to 在精美HTML中核查长期应收款保理业务, so that 我能判断保理转让是否满足终止确认条件。

#### Acceptance Criteria

10.1 THE G5-7保理核查表 SHALL 显示38行×9列：序号|债务人名称|保理商名称|保理金额|保理方式(有追索/无追索 下拉)|是否满足终止确认(是/否 下拉)|终止确认判断依据(textarea)|审计结论(合理/不合理 下拉)|索引
10.2 THE G5-7 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示终止确认五项条件：
   - ①收取现金流量的合同权利已终止
   - ②已转移金融资产所有权上几乎所有风险和报酬
   - ③既未转移也未保留几乎所有风险和报酬但放弃了控制
   - ④有追索权保理通常不满足终止确认
   - ⑤无追索权保理通常满足终止确认
10.3 WHEN 保理方式为"有追索"且终止确认为"是"时, THE 系统 SHALL 以橙色高亮该行并提示"有追索权保理通常不满足终止确认，请核实"
10.4 THE G5-7 SHALL 底部汇总区：保理总金额/已终止确认金额/未终止确认金额
10.5 THE G5-7 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
10.6 THE G5-7 SHALL 支持动态行增删（ElMessageBox.prompt输入债务人名称）+ 导入导出

### Requirement 11: 信用减值损失会计政策检查G5-8

**User Story:** As a 审计助理, I want to 在精美HTML中检查长期应收款信用减值损失会计政策, so that 我能评价企业ECL会计政策的合规性和一致性。

#### Acceptance Criteria

11.1 THE G5-8会计政策检查 SHALL 显示46行×15列，分为四个section：
   - **(一) ECL计量方法**：概述企业方法（问卷式）
   - **(二) 组合划分**：评价分组合理性
   - **(三) 参数确定**：PD/LGD/EAD来源和方法
   - **(四) 政策一致性**：与上年比较变化情况
11.2 THE G5-8 section(一) SHALL 列结构：检查项目|要求(方法论)|企业政策(textarea)|是否合规(合规/基本合规/不合规 下拉)|说明
11.3 THE G5-8 section(四) SHALL 列结构：政策事项|上年政策|本年政策|是否变更(是/否)|变更理由|合理性评价(下拉)
11.4 THE G5-8 SHALL 每个section标题行右侧提供AI辅助按钮
11.5 THE G5-8 SHALL 底部包含综合审计结论textarea + 编制提示details折叠区
11.6 THE G5-8 SHALL section(二)(三)支持动态行增删（ElMessageBox.prompt输入组合/参数名称）

### Requirement 12: 三阶段划分G5-9（列式转置结构，债务人为列）

**User Story:** As a 审计助理, I want to 在精美HTML中逐项判断每笔长期应收款的ECL阶段分类, so that 我能确认企业对信用风险变化程度的判断是否合理。

#### Acceptance Criteria

12.1 THE G5-9三阶段划分 SHALL 采用**列式转置结构**渲染（源模板中债务人作为列头，行为检查项），前端转换为行式交互视图（同G4-9方案）
12.2 THE G5-9 SHALL 分为三个检查区块：
   - **(一) 信用风险是否显著增加**：考虑因素×每债务人一列(是/否/不适用)
   - **(二) 是否具有较低信用风险**：满足条件×每债务人一列(是/否)
   - **(三) 已发生信用减值的评估**：可观察信息×每债务人一列(是/否)
12.3 THE G5-9 SHALL 转换为行式视图：每个债务人一行，列为：债务人|信用风险显著增加(综合)|较低信用风险(综合)|已发生信用减值(综合)|企业划分阶段(下拉)|审计判断阶段(下拉)|是否一致(公式)|差异说明|索引
12.4 THE Stage_Classification_Logic SHALL 实现三阶段判定规则（同G4-9）：
   - WHEN 部分(三)任一为"是", THEN 建议Stage3
   - WHEN 部分(一)任一为"是"且部分(三)均为"否", THEN 建议Stage2
   - WHEN 部分(一)均为"否"且部分(三)均为"否", THEN 建议Stage1
12.5 THE Formula_Engine SHALL 计算"是否一致" = (企业划分阶段 === 审计判断阶段)
12.6 WHEN 企业划分与审计判断不一致时, THE 系统 SHALL 红色高亮该行并强制要求填写差异说明
12.7 THE G5-9 SHALL 支持展开/折叠详情模式（点击行展开逐项检查明细）
12.8 THE G5-9 SHALL 底部汇总：Stage1/Stage2/Stage3数量/不一致项数
12.9 THE G5-9 SHALL 支持动态债务人增删（ElMessageBox.prompt输入债务人名称）+ 导入导出
12.10 THE G5-9 SHALL 对16384列源模板智能解析：仅取实际有数据的列，忽略空列

### Requirement 13: 坏账准备测算G5-10（19列→2区段Tab，ECL公式链）

**User Story:** As a 审计助理, I want to 在精美HTML中填写坏账准备测算表, so that 我能逐项验证长期应收款的预期信用损失计提金额。

#### Acceptance Criteria

13.1 THE G5-10坏账准备测算表 SHALL 显示63行×19列，拆为2区段Tab：
   - **Tab1: 未审数+审计调整(11列)**：债务人/组合|账面余额①|预计未来现金流量现值|预期信用损失率②|坏账准备③(公式)|账面价值④(公式)|余额调整⑤|调整后损失率②A|坏账调整⑥(公式)|阶段|索引
   - **Tab2: 审定数+差异(8列)**：债务人/组合|审定余额⑦(公式)|审定坏账准备⑧(公式)|审定账面价值⑨(公式)|上年坏账准备|本年计提(公式)|本年转回|差异说明
13.2 THE Formula_Engine SHALL 计算未审坏账准备：③ = ① × ②
13.3 THE Formula_Engine SHALL 计算账面价值：④ = ① - ③
13.4 THE Formula_Engine SHALL 计算坏账调整：⑥ = ⑤ × ②A + ① × (②A - ②)（同G4-10公式链）
13.5 THE Formula_Engine SHALL 计算审定余额：⑦ = ① + ⑤
13.6 THE Formula_Engine SHALL 计算审定坏账准备：⑧ = ③ + ⑥
13.7 THE Formula_Engine SHALL 计算审定账面价值：⑨ = ⑦ - ⑧
13.8 THE Formula_Engine SHALL 计算本年计提 = 审定坏账准备 - 上年坏账准备 + 本年转回
13.9 THE G5-10 SHALL 按Stage分组：Stage1/Stage2/Stage3/合计行
13.10 THE G5-10 SHALL 63行启用虚拟滚动
13.11 WHEN 用户切换区段Tab时, THE G5-10 SHALL 保持当前行索引（行同步）
13.12 THE G5-10 SHALL 支持动态行增删（ElMessageBox.prompt输入债务人名称）+ 导入导出

### Requirement 14: 减值转回核销检查G5-11 + 凭证检查G5-12

**User Story:** As a 审计助理, I want to 在精美HTML中检查减值转回/核销和凭证, so that 我能验证转回核销合规性和会计处理正确性。

#### Acceptance Criteria

14.1 THE G5-11减值转回核销检查表 SHALL 显示42行×20列，拆为2区段Tab：
   - **Tab1: 转回检查(10列)**：序号|单位名称|转回原因|收回方式|原计提依据|转回金额|收回前累计计提|合理性分析(textarea)|是否合理(下拉)|索引
   - **Tab2: 核销检查(10列)**：序号|单位名称|核销性质(下拉)|核销金额|核销原因(textarea)|核销程序(textarea)|是否关联交易(是/否)|合理性分析(textarea)|是否合理(下拉)|索引
14.2 THE G5-11 SHALL 验证：转回金额 ≤ 收回前累计计提（转回不超累计计提）
14.3 WHEN 转回金额 > 收回前累计计提时, THE 系统 SHALL 红色高亮并显示"转回金额超过累计计提"
14.4 THE G5-11 SHALL 关联交易标记"是"的行橙色底色高亮
14.5 THE G5-12凭证检查表 SHALL 显示99行×21列，拆为3区段Tab：
   - **Tab1: 凭证基础(8列)**：日期|凭证编号|业务内容|对方科目|明细科目|借方金额|贷方金额|📎附件
   - **Tab2: 核对内容(8列)**：支持性文件描述|核对1-原始凭证完整|核对2-授权批准|核对3-账务处理正确|核对4-金额计算正确|核对5-融资收益确认正确|核对6-减值计提正确|核对7-期限分类正确
   - **Tab3: 结论(5列)**：索引号|是否异常(是/否)|异常说明(textarea)|风险等级(高/中/低)|备注
14.6 THE G5-12 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog→样本填入借方/贷方区）
14.7 THE G5-12 SHALL Tab1📎附件列支持行级OCR：上传→POST `/d4/contract-ocr`→ElMessageBox确认→填入当前行
14.8 THE G5-12 SHALL 99行启用虚拟滚动
14.9 THE G5-12 SHALL 借贷平衡校验：差额红色显示在顶部汇总区
14.10 WHEN Tab2核对7项中任一为"✗"时, THE 系统 SHALL 自动将"是否异常"设为"是"并红色高亮
14.11 THE G5-11和G5-12 SHALL 各自支持动态行增删 + 导入导出
14.12 THE G5-12 SHALL 支持GtIndexChip索引列跳转

### Requirement 15: 公式引擎（G5专属）

**User Story:** As a 开发者, I want to 实现G5长期应收款公式引擎, so that 内含利率法/实际利率法/ECL公式链/借贷平衡等公式可PBT验证。

#### Acceptance Criteria

15.1 THE Formula_Engine SHALL 实现 `calcDebitBalance(opening, debit, credit): number`，返回 `opening + debit - credit`（借方余额公式）
15.2 THE Formula_Engine SHALL 实现 `calcAdjustedAmount(unadjusted, aje, rje): number`，返回 `unadjusted + aje + rje`（审定数公式）
15.3 THE Formula_Engine SHALL 实现 `calcNetValue(grossValue, badDebtProvision): number`，返回 `grossValue - badDebtProvision`（净值=原值-坏账准备）
15.4 THE Formula_Engine SHALL 实现 `calcReportAmount(netValue, oneYearMaturity): number`，返回 `netValue - oneYearMaturity`（报表列示数=净值-一年内到期）
15.5 THE Formula_Engine SHALL 实现 `calcNetInvestment(receivable, unrealizedIncome): number`，返回 `receivable - unrealizedIncome`（净投资额=应收融资租赁款-未实现融资收益）
15.6 THE Formula_Engine SHALL 实现 `calcLeaseFinancingIncome(netInvestment, implicitRate): number`，返回 `netInvestment × implicitRate`（内含利率法：融资收益=净投资额×内含利率）
15.7 THE Formula_Engine SHALL 实现 `calcInstallmentFinancingIncome(amortizedCost, effectiveRate): number`，返回 `amortizedCost × effectiveRate`（实际利率法：融资收益=摊余成本×实际利率）
15.8 THE Formula_Engine SHALL 实现 `calcEndingReceivable(openingReceivable, periodCollection): number`，返回 `openingReceivable - periodCollection`（期末应收=期初-本期收款）
15.9 THE Formula_Engine SHALL 实现 `calcEndingUnrealizedIncome(openingUnrealized, periodIncome): number`，返回 `openingUnrealized - periodIncome`（期末未实现=期初-本期确认收益）
15.10 THE Formula_Engine SHALL 实现 `calcSalesAmortizedCost(openingCost, income, collection): number`，返回 `openingCost + income - collection`（期末摊余成本=期初+融资收益-收款）
15.11 THE Formula_Engine SHALL 实现 `calcImpairmentProvision(bookBalance, creditLossRate): number`，返回 `bookBalance × creditLossRate`（坏账准备=余额×损失率）
15.12 THE Formula_Engine SHALL 实现 `calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate): number`，返回 `balanceAdj × adjRate + origBalance × (adjRate - origRate)`（坏账调整⑥公式链）
15.13 THE Formula_Engine SHALL 实现 `calcAdjustedBalance(orig, adj): number`，返回 `orig + adj`（审定余额⑦=①+⑤）
15.14 THE Formula_Engine SHALL 实现 `calcAdjustedImpairment(origImpairment, impairmentAdj): number`，返回 `origImpairment + impairmentAdj`（审定坏账⑧=③+⑥）
15.15 THE Formula_Engine SHALL 实现 `calcAdjustedBookValue(adjBalance, adjImpairment): number`，返回 `adjBalance - adjImpairment`（审定账面价值⑨=⑦-⑧）
15.16 THE Formula_Engine SHALL 实现 `determineStage(hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment): 'Stage1'|'Stage2'|'Stage3'`（三阶段判定，同G4-9逻辑）
15.17 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced(debits[], credits[]): boolean`，当 |SUM(debits)-SUM(credits)| < 0.01 时返回true
15.18 THE Formula_Engine SHALL 实现 `isReversalValid(reversalAmount, accumulatedProvision): boolean`，返回 reversalAmount ≤ accumulatedProvision
15.19 THE Formula_Engine SHALL 实现 `calcChangeRate(prior, current): number|null`，prior=0返回null，否则返回(current-prior)/prior
15.20 THE Formula_Engine SHALL 实现 `calcAgingTotal(y1, y2, y3, y4, y5, y5plus): number`，返回各账龄段之和
15.21 IF 任一公式函数接收到null/undefined/空串/NaN作为数值参数, THEN THE Formula_Engine SHALL 通过parseNum转换为0参与计算
15.22 THE Formula_Engine SHALL 导出所有公式函数为纯函数（无副作用），支持fast-check PBT以numRuns≥100验证


### Requirement 16: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to G5长期应收款底稿集成6大跨模块联动, so that 版本链/抽凭/截止/附注/OCR/复核全部可用。

#### Acceptance Criteria

16.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
16.2 THE 抽凭引擎 SHALL 在G5-12凭证检查表集成GtVoucherSamplingEngine（dialog→样本填入）
16.3 THE 截止自动提取 SHALL 在G5A程序表集成useCutoffAutoSampling（序时账±5天）
16.4 THE 附注EventBus SHALL subscribe `substantive:adjudicated`(accountCode='1531')刷新 + publish `disclosure:note-text-updated`
16.5 THE 行级OCR SHALL 在G5-12 Tab1📎附件列集成：POST `/d4/contract-ocr`→ElMessageBox确认→merge填入当前行
16.6 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮

### Requirement 17: 导入导出与AI辅助

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

17.1 THE Import_Export SHALL 对动态行表格支持导入导出：G5-2/G5-3/G5-4/G5-5/G5-6/G5-7/G5-10/G5-11/G5-12（共9张动态行表格）
17.2 THE Import_Export SHALL 使用useG5ImportExport composable（后端三端点：导出模板/导出数据/导入数据）
17.3 THE Import_Export SHALL 宽表按区段分sheet导出：G5-2(2sheet)/G5-3(2sheet)/G5-5(2sheet)/G5-10(2sheet)/G5-11(2sheet)/G5-12(3sheet)
17.4 THE AI_Assistant SHALL 在每个文本区section标题行右侧提供AI辅助按钮
17.5 THE AI_Assistant SHALL 提供AI辅助section：adjudication-analysis/lease-amortization-conclusion/sales-amortization-conclusion/factoring-conclusion/ecl-policy-conclusion/stage-conclusion/impairment-conclusion/reversal-writeoff-conclusion/voucher-conclusion
17.6 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 18: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且大表流畅, so that 16个sheet的操作体验一致且性能合格。

#### Acceptance Criteria

18.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
18.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
18.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
18.4 THE UI SHALL 编制提示details折叠底部
18.5 THE UI SHALL 动态行新增需ElMessageBox.prompt输入名称确认后创建
18.6 THE Performance SHALL 对行数>50的表启用虚拟滚动（G5-1:87行/G5-2:115行/G5-9:58行/G5-10:63行/G5-12:99行/附注上市:113行/附注国企:109行）
18.7 THE Performance SHALL defineAsyncComponent懒加载所有16个子组件
18.8 THE UI SHALL 区段Tab切换流畅（Tab切换无闪烁/行同步无延迟）
18.9 THE UI SHALL 底稿目录索引号列渲染为GtIndexChip可点击跳转

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G5长期应收款公式引擎的正确性。

**P1: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P2: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P3: 内含利率法核心公式** — ∀ netInvestment ∈ ℝ≥0, implicitRate ∈ (0,1): calcLeaseFinancingIncome(netInvestment, implicitRate) === netInvestment × implicitRate

**P4: 实际利率法核心公式** — ∀ amortizedCost ∈ ℝ≥0, effectiveRate ∈ (0,1): calcInstallmentFinancingIncome(amortizedCost, effectiveRate) === amortizedCost × effectiveRate

**P5: 融资租赁期间连续性** — ∀ openingReceivable, collection, openingUnrealized, income ∈ ℝ≥0: calcNetInvestment(calcEndingReceivable(openingReceivable, collection), calcEndingUnrealizedIncome(openingUnrealized, income)) === (openingReceivable - collection) - (openingUnrealized - income)（期末净投资=期末应收-期末未实现）

**P6: 分期销售摊余成本递推** — ∀ openingCost, rate ∈ (0,1), collection ∈ ℝ≥0: calcSalesAmortizedCost(openingCost, calcInstallmentFinancingIncome(openingCost, rate), collection) === openingCost + openingCost×rate - collection === openingCost×(1+rate) - collection

**P7: ECL公式链一致性** — ∀ ①,②,⑤,②A ∈ ℝ≥0: calcAdjustedBookValue(calcAdjustedBalance(①,⑤), calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②))) === (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))（审定账面价值=审定余额-审定坏账）

**P8: 坏账调整公式展开** — ∀ balanceAdj, adjRate, origBalance, origRate ∈ ℝ: calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate) === balanceAdj×adjRate + origBalance×(adjRate-origRate)

**P9: 三阶段划分确定性** — ∀ (hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment) ∈ boolean³: determineStage输出确定性映射到Stage1/Stage2/Stage3之一

**P10: 三阶段划分优先级** — ∀ inputs where hasCreditImpairment=true: determineStage(...) === 'Stage3'（信用减值事件优先级最高）

**P11: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P12: 转回有效性** — ∀ reversal ∈ ℝ≥0, accumulated ∈ ℝ≥0: isReversalValid(reversal, accumulated) ↔ (reversal ≤ accumulated)

**P13: 净值=原值-坏账** — ∀ gross ∈ ℝ≥0, provision ∈ ℝ≥0: calcNetValue(gross, provision) === gross - provision

**P14: 报表数=净值-一年内** — ∀ net ∈ ℝ≥0, oneYear ∈ ℝ≥0: calcReportAmount(net, oneYear) === net - oneYear

**P15: 账龄合计加法交换律** — ∀ y1~y5plus ∈ ℝ≥0: calcAgingTotal(y1,y2,y3,y4,y5,y5plus) === calcAgingTotal(permutation(y1~y5plus))（求和与顺序无关）

**P16: parseNum健壮性** — ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n

**P17: 变动率方向性** — ∀ current > prior > 0: calcChangeRate(prior, current) > 0；∀ current < prior, prior > 0: calcChangeRate(prior, current) < 0；calcChangeRate(0, any) === null

**P18: 净投资额恒等** — ∀ receivable ∈ ℝ≥0, unrealized ∈ ℝ≥0 where unrealized ≤ receivable: calcNetInvestment(receivable, unrealized) === receivable - unrealized ≥ 0
