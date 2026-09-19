# Requirements Document

## Introduction

G9其他非流动金融资产底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g9-other-noncurrent-financial`，覆盖1个xlsx源模板中的10个有效sheet。科目1504其他非流动金融资产（借方/资产类）。**G循环中第三层次公允价值计量审计最突出的科目**，含公允价值三层次测试、第三层次调节表（reconciliation）等特色审计内容。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 23×8 | 目录页 |
| 2 | 其他非流动金融资产实质性程序表G9A | 30×10 | a-program-console |
| 3 | 审定表G9-1 | 74×15 | 多层审定（以公允价值计量+以摊余成本计量分组） |
| 4 | 附注披露信息（上市公司） | 13×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 13×5 | 国企附注 |
| 6 | 明细表G9-2 | 47×28 | 28列超宽表，金融资产分类×公允价值变动 |
| 7 | 调整分录汇总G9-3 | 24×10 | AJE/RJE |
| 8 | 公允价值测试表G9-4 | 38×21 | 公允价值Level1/2/3测试+估值技术 |
| 9 | 第三层次公允价值计量的调节表G9-5 | 22×13 | **特色**：L3期初→期末变动调节 |
| 10 | 凭证检查表G9-6 | 99×20 | 凭证检查+OCR |

**科目属性**：
- 科目代码：1504 其他非流动金融资产
- 方向：借方（资产类）
- 计量属性：混合（公允价值计量+摊余成本计量，按业务模式分类）
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**关键特色（区别于G8）**：
1. **74行超大审定表**：按计量属性分组（公允价值FVTPL/FVOCI/摊余成本），比G8(29行)复杂
2. **28列超宽明细表**：需3区段Tab拆分
3. **第三层次调节表(G9-5)**：L3公允价值从期初到期末的完整变动分析（购入/处置/公允价值变动/转入转出）
4. **21列公允价值测试**：比G8-4(19列)更多，含利得损失验证

**宽表处理策略**：
- G9-1审定表(15列)：按分组折叠（公允价值/摊余成本）
- G9-2明细表(28列)：3区段Tab（基础信息/期初+变动/期末+公允价值）
- G9-4公允价值测试(21列)：2区段Tab（基础+未审审定/估值详情+层次）
- G9-6凭证检查(20列)：3区段Tab（凭证基础/核对内容/结论）

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ✅ 抽凭引擎: G9-6凭证检查表集成GtVoucherSamplingEngine dialog
- ✅ 截止自动提取: G9A程序表集成useCutoffAutoSampling
- ✅ 附注EventBus: subscribe substantive:adjudicated / publish disclosure:note-text-updated
- ✅ 行级OCR: G9-6凭证检查表📎列OCR识别
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **Other_Noncurrent_Financial_Assets**: 其他非流动金融资产，不满足交易性金融资产、债权投资、其他债权投资分类条件的非流动金融资产
- **Mixed_Measurement**: 混合计量，同一科目内按业务模式不同分别以公允价值/摊余成本计量
- **Level3_Reconciliation**: 第三层次调节表，从期初到期末的L3公允价值变动全面分析
- **FVTPL**: Fair Value Through Profit or Loss，以公允价值计量且变动计入当期损益
- **FVOCI**: Fair Value Through Other Comprehensive Income，以公允价值计量且变动计入OCI
- **Amortized_Cost**: 摊余成本，按实际利率法计量的金融资产账面价值
- **Fair_Value_Hierarchy**: 公允价值层次，Level1/Level2/Level3
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G9其他非流动金融资产底稿按sheetName prop分发到独立子组件, so that 10个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G9组件 SHALL 注册新componentType: `g9-other-noncurrent-financial`，主入口为 GtG9OtherNoncurrentFinancial.vue（接收sheetName prop，v-if分发到子组件）
1.2 THE G9组件 SHALL 使用defineAsyncComponent懒加载所有子组件（10个sheet按需加载）
1.3 THE G9组件 SHALL 在htmlRendererRegistry中注册'g9-other-noncurrent-financial'→GtG9OtherNoncurrentFinancial映射
1.4 THE G9组件 SHALL 在wp_code_overrides.json中将G9A、G9-1~G9-6、附注披露(上市/国企)、底稿目录的componentType统一映射为'g9-other-noncurrent-financial'（10个wp_code条目）
1.5 THE G9组件 SHALL 在VALID_COMPONENT_TYPES中注册'g9-other-noncurrent-financial'
1.6 IF htmlData prop为null, THEN SHALL selfLoad模式获取渲染数据
1.7 IF sheetName不在已迁移列表中, THEN SHALL 渲染OnlyOffice fallback组件

### Requirement 2: G9A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中执行其他非流动金融资产实质性程序, so that 我能按步骤完成审计程序。

#### Acceptance Criteria

2.1 THE G9A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G9A程序表 SHALL 显示30行×10列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G9A程序表 SHALL 集成抽凭引擎+截止自动提取

### Requirement 3: 审定表G9-1（74行多层结构，混合计量）

**User Story:** As a 审计助理, I want to 在精美HTML中填写其他非流动金融资产审定表, so that 我能按计量属性分组汇总审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G9-1审定表 SHALL 显示74行×15列多层结构，按计量属性分组：
   - **一、以公允价值计量且变动计入当期损益(FVTPL)**
   - **二、以公允价值计量且变动计入其他综合收益(FVOCI)**
   - **三、以摊余成本计量**
   - **合计**
3.2 THE G9-1审定表 SHALL 列结构：项目|期初(未审|AJE|RJE|审定)|期末(未审|AJE|RJE|审定)|变动额|变动率|原因分析|索引
3.3 THE G9-1审定表 SHALL 实现借方科目公式+审定数公式
3.4 THE G9-1审定表 SHALL 试算表数从trial_balance自动取数（科目1504）
3.5 THE G9-1审定表 SHALL 差异≠0时红色高亮
3.6 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1504'）
3.7 THE G9-1审定表 SHALL 74行启用虚拟滚动，支持展开/折叠分组（默认展开）
3.8 WHEN |变动率|>20%时, THE 系统 SHALL 橙色高亮+要求填写原因分析

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 编辑其他非流动金融资产附注披露, so that 我能按格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示13行×5列结构化表格
4.2 THE 附注披露(国企) SHALL 显示13行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1504')自动刷新
4.4 THE 附注披露 SHALL 发布 `disclosure:note-text-updated` 联动附注模块

### Requirement 5: 明细表G9-2（28列→3区段Tab）

**User Story:** As a 审计助理, I want to 查看其他非流动金融资产逐笔明细, so that 我能检查每笔资产的分类和公允价值变动。

#### Acceptance Criteria

5.1 THE G9-2明细表 SHALL 显示47行×28列，拆为3区段Tab：
   - **Tab1: 基础信息(8列)**：资产名称|金融资产分类(FVTPL/FVOCI/摊余成本 下拉)|初始投资日|到期日|持有数量|面值/成本|计量属性|是否关联方
   - **Tab2: 期初+本期变动(10列)**：资产名称|期初余额|期初调整|期初审定|本期增加|本期减少|本期公允价值变动|本期利息收入|本期减值|本期OCI变动
   - **Tab3: 期末+公允价值(10列)**：资产名称|期末余额|调整数|审定数|公允价值层次(L1/L2/L3)|估值方法|发函情况|OCI累计|减值准备|备注
5.2 THE Formula_Engine SHALL 计算期末余额 = 期初审定 + 增加 - 减少 + 公允价值变动 + 利息收入 - 减值
5.3 THE G9-2 SHALL 底部按分类分组小计+总计
5.4 WHEN 用户切换区段Tab时, THE G9-2 SHALL 行同步
5.5 THE G9-2 SHALL 支持动态行增删（ElMessageBox.prompt输入资产名称）+ 导入导出

### Requirement 6: 调整分录汇总G9-3

**User Story:** As a 审计助理, I want to 录入其他非流动金融资产调整分录, so that 记录AJE/RJE并回写审定表。

#### Acceptance Criteria

6.1 THE G9-3调整分录 SHALL 显示24行×10列标准AJE/RJE结构
6.2 THE G9-3 SHALL 借贷平衡校验+动态行增删+导入导出
6.3 WHEN 保存时 SHALL 汇总回写G9-1审定表

### Requirement 7: 公允价值测试表G9-4（21列→2区段Tab）

**User Story:** As a 审计助理, I want to 测试其他非流动金融资产的公允价值, so that 我能验证公允价值计量的合理性。

#### Acceptance Criteria

7.1 THE G9-4公允价值测试表 SHALL 显示38行×21列，拆为2区段Tab：
   - **Tab1: 基础+审定(11列)**：资产名称|初始投资日|期末未审(数量/单价/公允价值)|期末审定(数量/单价/公允价值)|差异|公允价值层次(下拉)
   - **Tab2: 估值详情(10列)**：资产名称|估值方法|与上期一致性|来源机构|输入值来源(textarea)|估值技术|不可观察输入值|数值|非流通折价率|估值文件索引
7.2 WHEN 公允价值层次为"Level3" THEN Tab2必填校验
7.3 THE G9-4 SHALL 顶部方法论上下文+底部审计结论textarea+AI辅助
7.4 THE G9-4 SHALL 行同步+动态行增删+导入导出

### Requirement 8: 第三层次公允价值计量调节表G9-5

**User Story:** As a 审计助理, I want to 编制第三层次公允价值调节表, so that 我能完整追踪L3资产从期初到期末的公允价值变动。

#### Acceptance Criteria

8.1 THE G9-5调节表 SHALL 显示22行×13列，列结构：资产名称|期初公允价值|本期购入|本期处置|转入第三层次|转出第三层次|公允价值变动(计入损益)|公允价值变动(计入OCI)|利息收入|减值损失|其他变动|期末公允价值|差异(公式)
8.2 THE Formula_Engine SHALL 计算期末公允价值 = 期初 + 购入 - 处置 + 转入 - 转出 + FV变动(损益) + FV变动(OCI) + 利息 - 减值 + 其他
8.3 THE Formula_Engine SHALL 计算差异 = 计算的期末 - 企业报告的期末
8.4 WHEN |差异| > 0.01时, THE 系统 SHALL 红色高亮
8.5 THE G9-5 SHALL 底部包含审计结论textarea（带AI辅助按钮）+ 编制提示details折叠区
8.6 THE G9-5 SHALL 支持动态行增删（ElMessageBox.prompt输入资产名称）

### Requirement 9: 凭证检查表G9-6（20列→3区段Tab）

**User Story:** As a 审计助理, I want to 检查其他非流动金融资产凭证, so that 验证会计处理正确性。

#### Acceptance Criteria

9.1 THE G9-6凭证检查表 SHALL 显示99行×20列，拆为3区段Tab：
   - **Tab1: 凭证基础(7列)**：日期|凭证编号|业务内容|对方科目|借方金额|贷方金额|📎附件
   - **Tab2: 核对内容(7列)**：支持性文件|核对1-原始凭证|核对2-授权批准|核对3-账务处理|核对4-分类正确|核对5-公允价值|核对6-减值计提
   - **Tab3: 结论(6列)**：索引号|是否异常(是/否)|异常说明|风险等级|处理建议|备注
9.2 THE G9-6 SHALL 集成抽凭引擎+行级OCR+虚拟滚动(99行)+借贷平衡校验
9.3 THE G9-6 SHALL 支持动态行增删+导入导出+GtIndexChip

### Requirement 10: 公式引擎+联动+导入导出+UI

**User Story:** As a 开发者, I want to 实现G9公式引擎和完整集成, so that 所有公式可PBT验证且6大联动可用。

#### Acceptance Criteria

10.1 THE Formula_Engine SHALL 实现：calcDebitBalance / calcAdjustedAmount / calcEndingBalance / calcFairValueDiff / calcChangeRate / isDebitCreditBalanced / calcL3Reconciliation / parseNum（共8个纯函数）
10.2 THE calcL3Reconciliation SHALL 计算：期初+购入-处置+转入-转出+FV损益+FV_OCI+利息-减值+其他 = 期末
10.3 THE 6大集成 SHALL 全部集成（版本链/抽凭/截止/附注EventBus/OCR/复核）
10.4 THE Import_Export SHALL 对G9-2/G9-3/G9-4/G9-5/G9-6支持导入导出（5张表）
10.5 THE AI辅助 SHALL 提供：adjudication-analysis/fair-value-conclusion/l3-reconciliation-conclusion/voucher-conclusion
10.6 THE 虚拟滚动 SHALL 对G9-1(74行)/G9-6(99行)启用
10.7 THE UI SHALL 统一底稿表格规范+双模式切换

## Correctness Properties

**P1: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P2: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P3: L3调节表恒等** — ∀ 各变动项 ∈ ℝ: calcL3Reconciliation(期初,购入,处置,转入,转出,FV损益,FV_OCI,利息,减值,其他) === 期初+购入-处置+转入-转出+FV损益+FV_OCI+利息-减值+其他

**P4: 变动率方向性** — ∀ current > prior > 0: calcChangeRate(prior, current) > 0；calcChangeRate(0, any) === null

**P5: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P6: parseNum健壮性** — ∀ input ∈ {null, undefined, '', NaN}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n

**P7: 期末余额多因子加法交换律** — calcEndingBalance对各变动因子的求和与顺序无关

**P8: L3差异为零时平衡** — WHEN calcL3Reconciliation(...) === 企业期末 THEN 差异 === 0
