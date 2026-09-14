# Requirements Document

## Introduction

G8其他权益工具投资底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g8-other-equity-instruments`，覆盖1个xlsx源模板中的10个有效sheet（排除参考资料sheet）。科目1503其他权益工具投资（借方/资产类）。**G循环中指定适当性审计最突出的科目**，包含非交易性权益工具指定合规性判断、公允价值Level1-3层次测试（含第三层次估值技术验证）等特色审计内容。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 21×8 | 目录页 |
| 2 | 其他权益工具投资实质性程序表G8A | 30×9 | a-program-console |
| 3 | 审定表G8-1 | 29×11 | 公允价值计量审定 |
| 4 | 附注披露信息（上市公司） | 18×7 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 20×7 | 国企附注 |
| 6 | 明细表G8-2 | 39×24 | 24列宽表，被投资单位×公允价值变动 |
| 7 | 调整分录汇总G8-3 | 24×10 | AJE/RJE |
| 8 | 公允价值测试表G8-4 | 40×19 | **特色**：Level1/2/3分层测试+估值技术 |
| 9 | 指定的适当性检查表G8-5 | 36×19 | **特色**：非交易性权益工具指定合规检查 |
| 10 | 凭证检查表G8-6 | 102×18 | 凭证检查+OCR |

**排除sheet**：参考中证协《非上市公司股权估值指引》(4×13) — 仅参考资料，不渲染

**科目属性**：
- 科目代码：1503 其他权益工具投资
- 方向：借方（资产类）
- 计量属性：公允价值计量且其变动计入其他综合收益（OCI）
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**关键特色（区别于G1交易性金融资产）**：
1. **指定适当性**：管理层将非交易性权益工具"指定"为其他权益工具投资，审计需验证指定是否合规(G8-5)
2. **OCI核算**：公允价值变动计入其他综合收益，不进损益（处置时OCI可转入留存收益）
3. **公允价值三层次**：Level1(活跃市场报价)/Level2(可观察输入)/Level3(不可观察输入，需估值技术)
4. **第三层次估值**：市场法(可比公司EBITDA乘数)+收益法(DCF)+资产基础法，需验证输入值

**宽表处理策略**：
- G8-2明细表(24列)：2区段Tab（被投资单位基础信息/公允价值变动+OCI）
- G8-4公允价值测试(19列)：2区段Tab（基础信息+未审/审定数+差异/估值详情）
- G8-5适当性检查(19列)：单表（问卷式，列数虽多但多为合并单元格textarea）
- G8-6凭证检查(18列)：3区段Tab（凭证基础/核对内容/结论）

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ✅ 抽凭引擎: G8-6凭证检查表集成GtVoucherSamplingEngine dialog
- ✅ 截止自动提取: G8A程序表集成useCutoffAutoSampling
- ✅ 附注EventBus: subscribe substantive:adjudicated / publish disclosure:note-text-updated
- ✅ 行级OCR: G8-6凭证检查表📎列OCR识别
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **Other_Equity_Instruments**: 其他权益工具投资，企业持有的非交易性权益工具投资，指定为以公允价值计量且其变动计入其他综合收益
- **Designation**: 指定，管理层在初始确认时做出的不可撤销选择，将非交易性权益工具指定为以公允价值计量且变动计入OCI
- **OCI**: Other Comprehensive Income，其他综合收益，公允价值变动不进损益而计入所有者权益
- **Fair_Value_Hierarchy**: 公允价值层次，Level1(活跃市场报价)/Level2(可观察输入值)/Level3(不可观察输入值)
- **Level3_Valuation**: 第三层次估值，使用不可观察输入值的估值技术（市场法/收益法/资产基础法）
- **EBITDA_Multiple**: 可比公司EBITDA乘数法，第三层次市场法估值的常用方法
- **Non_Marketability_Discount**: 非流通折价(DLOM)，非上市公司股权因缺乏流动性的折扣（通常10%-30%）
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G8其他权益工具投资底稿按sheetName prop分发到独立子组件, so that 10个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G8组件 SHALL 注册新componentType: `g8-other-equity-instruments`，主入口为 GtG8OtherEquityInstruments.vue（接收sheetName prop，v-if分发到子组件）
1.2 THE G8组件 SHALL 使用defineAsyncComponent懒加载所有子组件（10个sheet按需加载）
1.3 THE G8组件 SHALL 在htmlRendererRegistry中注册'g8-other-equity-instruments'→GtG8OtherEquityInstruments映射
1.4 THE G8组件 SHALL 在wp_code_overrides.json中将G8A、G8-1~G8-6、附注披露(上市/国企)、底稿目录的componentType统一映射为'g8-other-equity-instruments'（10个wp_code条目）
1.5 THE G8组件 SHALL 在VALID_COMPONENT_TYPES中注册'g8-other-equity-instruments'
1.6 IF htmlData prop为null, THEN THE GtG8OtherEquityInstruments.vue SHALL 自行调用render-config?force_component_type=g8-other-equity-instruments获取渲染数据（selfLoad模式）
1.7 IF sheetName正则提取编码失败或不在已迁移列表中, THEN SHALL 渲染OnlyOffice fallback组件

### Requirement 2: G8A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行其他权益工具投资实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE G8A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G8A程序表 SHALL 显示30行×9列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G8A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑
2.4 THE G8A程序表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式）
2.5 THE G8A程序表 SHALL 集成useCutoffAutoSampling截止自动提取（序时账±5天）

### Requirement 3: 审定表G8-1（公允价值计量，借方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写其他权益工具投资审定表, so that 我能汇总公允价值计量的审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G8-1审定表 SHALL 显示29行×11列，列结构：项目|期初(未审|账项调整|审定)|期末(未审|账项调整|审定)|变动额|变动率|原因分析
3.2 THE G8-1审定表 SHALL 第一行分组标题"公允价值"，下方按被投资单位逐项列示
3.3 THE G8-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
3.4 THE G8-1审定表 SHALL 实现审定数公式：审定 = 未审 + 账项调整
3.5 THE G8-1审定表 SHALL 试算表数从trial_balance自动取数（科目1503）
3.6 THE G8-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.7 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1503', adjudicatedAmount=合计审定数）
3.8 THE G8-1审定表 SHALL 变动率公式：变动率 = (期末审定 - 期初审定) / 期初审定 × 100%
3.9 WHEN |变动率|>20%时, THE 系统 SHALL 以橙色高亮并要求填写原因分析

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑其他权益工具投资附注披露, so that 我能按上市/国企格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示18行×7列结构化表格
4.2 THE 附注披露(国企) SHALL 显示20行×7列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1503')自动刷新审定数据
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露 SHALL 每个文本区提供AI辅助按钮（section标题行右侧）

### Requirement 5: 明细表G8-2（24列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看其他权益工具投资逐笔明细, so that 我能检查每笔投资的公允价值变动和OCI计入情况。

#### Acceptance Criteria

5.1 THE G8-2明细表 SHALL 显示39行×24列，拆为2区段Tab：
   - **Tab1: 被投资单位基础信息(12列)**：被投资单位名称|投资比例|期初余额|期初调整数|期初审定数|本期变动(增加)|本期变动(减少)|本期变动(公允价值变动)|期末余额|调整数|审定数|指定为OCI的原因
   - **Tab2: 公允价值+OCI(12列)**：被投资单位名称|OCI累计变动|本期OCI变动|OCI转入留存收益金额|转入原因|发函情况|公允价值层次(L1/L2/L3)|估值方法|持股数量|每股公允价值|公允价值合计|备注
5.2 THE Formula_Engine SHALL 计算审定数 = 期末余额 + 调整数
5.3 THE Formula_Engine SHALL 计算期末余额 = 期初审定 + 本期增加 - 本期减少 + 公允价值变动
5.4 THE G8-2 SHALL 底部显示合计行
5.5 WHEN 用户切换区段Tab时, THE G8-2 SHALL 保持当前选中行的行索引不变（行同步）
5.6 THE G8-2 SHALL 支持动态行增删（ElMessageBox.prompt输入被投资单位名称）+ 导入导出

### Requirement 6: 调整分录汇总G8-3

**User Story:** As a 审计助理, I want to 在精美HTML中录入其他权益工具投资调整分录, so that 我能记录AJE/RJE并回写审定表。

#### Acceptance Criteria

6.1 THE G8-3调整分录 SHALL 显示24行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE G8-3调整分录 SHALL 借贷平衡校验：|SUM(借方) - SUM(贷方)| < 0.01
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE G8-3调整分录 SHALL 支持动态行增删（ElMessageBox.prompt输入摘要）+ 导入导出
6.5 WHEN 调整分录保存时, THE 系统 SHALL 自动汇总AJE/RJE金额回写G8-1审定表

### Requirement 7: 公允价值测试表G8-4（19列→2区段Tab，三层次测试）

**User Story:** As a 审计助理, I want to 在精美HTML中测试其他权益工具投资的公允价值, so that 我能验证企业公允价值计量的合理性并判断层次划分正确性。

#### Acceptance Criteria

7.1 THE G8-4公允价值测试表 SHALL 显示40行×19列，拆为2区段Tab：
   - **Tab1: 基础信息+审定(10列)**：被投资单位名称|初始投资日期|期末未审数(数量/单价/公允价值)|期末审定数(数量/单价/公允价值)|差异|公允价值层次(L1/L2/L3 下拉)
   - **Tab2: 估值详情(9列)**：被投资单位名称|估值方法(下拉)|估值方法与上期是否一致(是/否)|公允价值来源机构|输入值来源及调整考虑因素(textarea)|估值技术(市场法/收益法/资产基础法)|不可观察输入值描述|数值|估值文件索引号
7.2 THE G8-4 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示三层次定义说明
7.3 WHEN 公允价值层次为"Level3"时, THE 系统 SHALL Tab2估值详情必填校验（估值技术+不可观察输入值不能为空）
7.4 THE Formula_Engine SHALL 计算差异 = 审定公允价值 - 未审公允价值
7.5 WHEN |差异| > 重要性水平时, THE 系统 SHALL 红色高亮差异列
7.6 THE G8-4 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
7.7 WHEN 用户切换区段Tab时, THE G8-4 SHALL 保持当前行索引（行同步）
7.8 THE G8-4 SHALL 支持动态行增删（ElMessageBox.prompt输入被投资单位名称）+ 导入导出

### Requirement 8: 指定的适当性检查表G8-5

**User Story:** As a 审计助理, I want to 在精美HTML中检查其他权益工具投资的指定适当性, so that 我能评价管理层将非交易性权益工具指定为OCI计量的合规性。

#### Acceptance Criteria

8.1 THE G8-5适当性检查表 SHALL 显示36行×19列，分为多个检查section（问卷式）：
   - **(一) 指定是否符合准则要求**：CAS22/IFRS9关于非交易性权益工具指定条件
   - **(二) 管理层持有目的验证**：获取书面声明+检查历史行为一致性
   - **(三) 金融资产分类合规性**：与CAS22分类要求对比检查
   - **(四) 指定的不可撤销性**：确认初始确认时即做出不可撤销指定
8.2 THE G8-5 SHALL 列结构（问卷式）：序号|检查项目|审计要求(方法论)|管理层回复/审计获取证据(textarea)|是否合规(合规/不合规/不适用 下拉)|审计结论(textarea)|索引
8.3 THE G8-5 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示CAS22指定条件：
   - ①该金融资产非为交易目的而持有
   - ②在初始确认时做出不可撤销的选择
   - ③公允价值变动计入其他综合收益
   - ④处置时累计OCI可转入留存收益（不经损益）
8.4 THE G8-5 SHALL 每个section标题行右侧提供AI辅助按钮
8.5 THE G8-5 SHALL 底部包含综合审计结论textarea + 编制提示details折叠区

### Requirement 9: 凭证检查表G8-6（18列→3区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中检查其他权益工具投资凭证, so that 我能验证会计处理正确性和原始凭证支持性。

#### Acceptance Criteria

9.1 THE G8-6凭证检查表 SHALL 显示102行×18列，拆为3区段Tab：
   - **Tab1: 凭证基础(7列)**：日期|凭证编号|业务内容|对方科目|借方金额|贷方金额|📎附件
   - **Tab2: 核对内容(6列)**：支持性文件描述|核对1-原始凭证完整|核对2-授权批准|核对3-账务处理正确|核对4-公允价值计量正确|核对5-OCI计入正确
   - **Tab3: 结论(5列)**：索引号|是否异常(是/否)|异常说明(textarea)|风险等级(高/中/低)|备注
9.2 THE G8-6 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog→样本填入借方/贷方区）
9.3 THE G8-6 SHALL Tab1📎附件列支持行级OCR：上传→POST `/d4/contract-ocr`→ElMessageBox确认→填入当前行
9.4 THE G8-6 SHALL 102行启用虚拟滚动
9.5 THE G8-6 SHALL 借贷平衡校验：差额红色显示在顶部汇总区
9.6 WHEN Tab2核对5项中任一为"✗"时, THE 系统 SHALL 自动将"是否异常"设为"是"并红色高亮
9.7 THE G8-6 SHALL 支持动态行增删 + 导入导出
9.8 THE G8-6 SHALL 支持GtIndexChip索引列跳转

### Requirement 10: 公式引擎（G8专属）

**User Story:** As a 开发者, I want to 实现G8其他权益工具投资公式引擎, so that 公允价值变动/OCI/借贷平衡等公式可PBT验证。

#### Acceptance Criteria

10.1 THE Formula_Engine SHALL 实现 `calcDebitBalance(opening, debit, credit): number`，返回 `opening + debit - credit`（借方余额公式）
10.2 THE Formula_Engine SHALL 实现 `calcAdjustedAmount(unadjusted, adjustment): number`，返回 `unadjusted + adjustment`（审定数公式，注意G8只有账项调整无AJE/RJE分列）
10.3 THE Formula_Engine SHALL 实现 `calcEndingBalance(openingAdjusted, increase, decrease, fvChange): number`，返回 `openingAdjusted + increase - decrease + fvChange`（期末余额=期初审定+增加-减少+公允价值变动）
10.4 THE Formula_Engine SHALL 实现 `calcFairValueDiff(audited, unadjusted): number`，返回 `audited - unadjusted`（公允价值差异）
10.5 THE Formula_Engine SHALL 实现 `calcChangeRate(prior, current): number|null`，prior=0返回null，否则返回(current-prior)/prior
10.6 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced(debits[], credits[]): boolean`，当 |SUM(debits)-SUM(credits)| < 0.01 时返回true
10.7 IF 任一公式函数接收到null/undefined/空串/NaN作为数值参数, THEN THE Formula_Engine SHALL 通过parseNum转换为0参与计算
10.8 THE Formula_Engine SHALL 导出所有公式函数为纯函数（无副作用），支持fast-check PBT以numRuns≥100验证

### Requirement 11: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to G8其他权益工具投资底稿集成6大跨模块联动, so that 版本链/抽凭/截止/附注/OCR/复核全部可用。

#### Acceptance Criteria

11.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
11.2 THE 抽凭引擎 SHALL 在G8-6凭证检查表集成GtVoucherSamplingEngine（dialog→样本填入）
11.3 THE 截止自动提取 SHALL 在G8A程序表集成useCutoffAutoSampling（序时账±5天）
11.4 THE 附注EventBus SHALL subscribe `substantive:adjudicated`(accountCode='1503')刷新 + publish `disclosure:note-text-updated`
11.5 THE 行级OCR SHALL 在G8-6 Tab1📎附件列集成：POST `/d4/contract-ocr`→ElMessageBox确认→merge填入当前行
11.6 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮

### Requirement 12: 导入导出与AI辅助

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

12.1 THE Import_Export SHALL 对动态行表格支持导入导出：G8-2/G8-3/G8-4/G8-6（共4张动态行表格）
12.2 THE Import_Export SHALL 使用useG8ImportExport composable（后端三端点：导出模板/导出数据/导入数据）
12.3 THE Import_Export SHALL 宽表按区段分sheet导出：G8-2(2sheet)/G8-4(2sheet)/G8-6(3sheet)
12.4 THE AI_Assistant SHALL 在每个文本区section标题行右侧提供AI辅助按钮
12.5 THE AI_Assistant SHALL 提供AI辅助section：adjudication-analysis/fair-value-conclusion/designation-conclusion/voucher-conclusion
12.6 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 13: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且大表流畅, so that 10个sheet的操作体验一致且性能合格。

#### Acceptance Criteria

13.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
13.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
13.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
13.4 THE UI SHALL 编制提示details折叠底部
13.5 THE UI SHALL 动态行新增需ElMessageBox.prompt输入名称确认后创建
13.6 THE Performance SHALL 对行数>50的表启用虚拟滚动（G8-6:102行）
13.7 THE Performance SHALL defineAsyncComponent懒加载所有10个子组件
13.8 THE UI SHALL 区段Tab切换流畅（Tab切换无闪烁/行同步无延迟）
13.9 THE UI SHALL 底稿目录索引号列渲染为GtIndexChip可点击跳转

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G8其他权益工具投资公式引擎的正确性。

**P1: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P2: 审定数公式** — ∀ unadjusted, adjustment ∈ ℝ: calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment

**P3: 期末余额公式** — ∀ openingAdj, increase, decrease, fvChange ∈ ℝ: calcEndingBalance(openingAdj, increase, decrease, fvChange) === openingAdj + increase - decrease + fvChange

**P4: 公允价值差异** — ∀ audited, unadjusted ∈ ℝ: calcFairValueDiff(audited, unadjusted) === audited - unadjusted

**P5: 变动率方向性** — ∀ current > prior > 0: calcChangeRate(prior, current) > 0；∀ current < prior, prior > 0: calcChangeRate(prior, current) < 0；calcChangeRate(0, any) === null

**P6: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P7: parseNum健壮性** — ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n

**P8: 期末余额与审定一致性** — ∀ openingAdj, increase, decrease, fvChange, adjustment ∈ ℝ: calcAdjustedAmount(calcEndingBalance(openingAdj, increase, decrease, fvChange), adjustment) === openingAdj + increase - decrease + fvChange + adjustment
