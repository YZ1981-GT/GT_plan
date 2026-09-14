# Requirements Document

## Introduction

G6其他债权投资(ECL组)底稿专属HTML精美组件构建。组件 `g6-other-bond-investment-ecl`，覆盖源模板21个sheet中的5个sheet（ECL减值+凭证检查组）。**本组聚焦预期信用损失(ECL)三阶段减值全流程**：三阶段划分(G6-11)→减值测算(G6-12)→ECL计量测试(G6-13)→转回核销(G6-14)→凭证检查(G6-15)。

**本组(ECL)sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 其他债权投资三阶段划分G6-11 | 61×16384 | **列式转置结构**（同G4-9/G5-9） |
| 2 | 其他债权投资减值准备测算表G6-12 | 37×22 | ECL公式链测算 |
| 3 | 预期信用损失的计量测试G6-13 | 49×10 | ECL计量方法合规检查 |
| 4 | 减值准备转回（收回）、核销检查表G6-14 | 42×8 | 转回核销合规检查 |
| 5 | 凭证检查表G6-15 | 100×22 | 凭证检查+OCR |

**关键特色**：
1. **G6-11列式转置**：16384列=合并单元格，投资项目为列（同G4-9/G5-9方案，前端转行式）
2. **G6-12 ECL公式链**：22列含公允价值口径的减值（区别于G4/G5的摊余成本口径），公式链⑥=⑤×②A+①×(②A-②)
3. **G6-13 ECL计量测试**：49行问卷检查PD/LGD/EAD参数合理性
4. **G6-15凭证检查**：22列超宽→3区段Tab

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G6-15) / ❌ 截止 / ❌ 附注EventBus / ✅ 行级OCR(G6-15) / ✅ 复核对话

## Glossary

- **ECL_Three_Stage**: ECL三阶段（Stage1:12个月/Stage2:整个存续期/Stage3:已减值），同G4-9/G5-9
- **FVOCI_Impairment**: FVOCI减值特殊性，减值准备计入损益但不减少账面价值，通过OCI调整
- **ECL_Measurement_Test**: ECL计量测试，验证PD/LGD/EAD参数的合理性和数据来源
- **Transposed_Structure**: 列式转置结构，源模板中投资项目作为列头，前端需转为行式视图

## Requirements

### Requirement 1: 组件架构

**User Story:** As a 开发者, I want to G6其他债权投资(ECL组)按sheetName prop分发, so that 5个sheet通过统一入口组织。

#### Acceptance Criteria

1.1 THE G6-ECL组件 SHALL 注册componentType: `g6-other-bond-investment-ecl`，主入口GtG6OtherBondInvestmentEcl.vue
1.2 THE G6-ECL组件 SHALL defineAsyncComponent懒加载5个子组件
1.3 THE G6-ECL组件 SHALL 注册四件套（5条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: 三阶段划分G6-11（列式转置，同G4-9/G5-9）

**User Story:** As a 审计助理, I want to 逐项判断每笔其他债权投资的ECL阶段分类。

#### Acceptance Criteria

2.1 THE G6-11 SHALL 采用**列式转置结构**渲染（源模板投资项目为列），前端转换为行式交互视图
2.2 THE G6-11 SHALL 行式视图：投资项目|信用风险显著增加(综合)|较低信用风险|已发生信用减值|企业划分阶段(下拉)|审计判断阶段(下拉)|是否一致(公式)|差异说明|索引
2.3 THE Stage_Classification_Logic SHALL 同G4-9/G5-9三阶段判定规则
2.4 WHEN 企业与审计判断不一致 SHALL 红色高亮+强制差异说明
2.5 THE G6-11 SHALL 展开/折叠详情+底部汇总(S1/S2/S3数量)+动态增删+导入导出
2.6 THE G6-11 SHALL 对16384列智能解析仅取有数据列

### Requirement 3: 减值准备测算G6-12（22列→2区段Tab）

**User Story:** As a 审计助理, I want to 填写减值准备测算表, so that 逐项验证ECL计提金额。

#### Acceptance Criteria

3.1 THE G6-12 SHALL 37行×22列，2区段Tab：
   - **Tab1: 未审+调整(12列)**：投资项目|摊余成本余额①|公允价值|预期信用损失率②|坏账准备③(公式)|账面价值④(公式)|余额调整⑤|调整后损失率②A|坏账调整⑥(公式)|阶段|OCI影响|索引
   - **Tab2: 审定数(10列)**：投资项目|审定余额⑦(公式)|审定坏账⑧(公式)|审定账面价值⑨(公式)|审定公允价值|上年坏账|本年计提(公式)|本年转回|OCI调整|差异说明
3.2 THE Formula_Engine SHALL ECL公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧
3.3 THE G6-12 SHALL 注意：其他债权投资减值按**摊余成本口径**计算（非公允价值口径）
3.4 THE G6-12 SHALL 按Stage分组+行同步+动态行增删+导入导出

### Requirement 4: ECL计量测试G6-13

**User Story:** As a 审计助理, I want to 检查ECL计量方法, so that 验证PD/LGD/EAD参数合理性。

#### Acceptance Criteria

4.1 THE G6-13 SHALL 49行×10列问卷式：
   - **(一) PD（违约概率）**：数据来源/估计方法/前瞻性调整
   - **(二) LGD（违约损失率）**：抵押品/回收率/优先级
   - **(三) EAD（违约风险暴露）**：余额口径/表外承诺
   - **(四) 折现率**：使用原始实际利率/近似利率
   - **(五) 前瞻性信息**：宏观经济情景/权重
4.2 THE G6-13 SHALL 列：序号|检查区域|检查项目|审计要求|企业参数(textarea)|是否合理(下拉)|审计结论(textarea)|风险等级|索引|备注
4.3 THE G6-13 SHALL 顶部方法论上下文(ECL三要素定义)+每section AI辅助

### Requirement 5: 转回核销G6-14 + 凭证检查G6-15

**User Story:** As a 审计助理, I want to 检查转回核销合规性和凭证。

#### Acceptance Criteria

5.1 THE G6-14 SHALL 42行×8列：序号|投资项目|转回/核销类型(下拉)|金额|原因(textarea)|审批程序|合理性结论(下拉)|索引
5.2 THE G6-15 SHALL 100行×22列，3区段Tab（凭证基础/核对内容/结论）：
   - Tab1(8列)：日期|凭证号|业务内容|对方科目|明细|借方|贷方|📎附件
   - Tab2(8列)：支持性文件|核对1-原始凭证|核对2-授权|核对3-账务|核对4-金额|核对5-分类|核对6-减值|核对7-利息
   - Tab3(6列)：索引|是否异常|异常说明|风险等级|处理建议|备注
5.3 THE G6-15 SHALL 抽凭引擎+行级OCR+虚拟滚动(100行)+借贷平衡+GtIndexChip
5.4 THE G6-14/G6-15 SHALL 动态行增删+导入导出

### Requirement 6: 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 实现G6-ECL组公式引擎和完整集成, so that 三阶段/ECL公式链/借贷平衡可PBT验证。

#### Acceptance Criteria

6.1 THE Formula_Engine SHALL：determineStage/calcImpairmentProvision/calcImpairmentAdjustment/calcAdjustedBalance/calcAdjustedImpairment/calcAdjustedBookValue/isDebitCreditBalanced/parseNum
6.2 THE 集成 SHALL（版本链+抽凭(G6-15)+OCR(G6-15)+复核）
6.3 THE Import_Export SHALL G6-12/G6-14/G6-15（3张表）
6.4 THE AI辅助 SHALL：stage-conclusion/impairment-conclusion/ecl-measurement-conclusion/voucher-conclusion
6.5 THE 虚拟滚动 SHALL G6-11(61行)/G6-15(100行)
6.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: ECL公式链一致性** — ⑨=(①+⑤)-(①×②+⑤×②A+①×(②A-②))

**P2: 三阶段确定性** — determineStage输出∈{Stage1,Stage2,Stage3}

**P3: Stage3优先级** — hasCreditImpairment=true → Stage3

**P4: 坏账调整展开** — ⑥=⑤×②A+①×(②A-②)

**P5: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P6: parseNum** — null/undefined/NaN → 0
