# Requirements Document

## Introduction

G4债权投资底稿专属HTML精美组件构建（减值与ECL组）。将现有通用渲染升级为独立专属组件 `g4-bond-investment-ecl`，覆盖1个xlsx源模板中的7个sheet（含2个只读参考材料）。科目1501债权投资（借方/资产类）。**CAS22/CAS24预期信用损失计量的核心逻辑**：三阶段划分确定减值计提基数和方法，ECL测算验证减值准备金额的合理性，凭证检查确认会计处理正确性。

**三组拆分方案**：
- g4-bond-investment-main: 程序表+审定表+附注+明细表+调整+利息测算（已完成）
- g4-bond-investment-sppi: 业务模式分析+SPPI+盘点（已完成）
- **本spec (ecl)**: 三阶段划分+减值准备测算+预期信用损失计量测试+减值转回核销+凭证检查+参考资料（7个sheet）

**源模板sheet清单（本spec覆盖，openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 债权投资三阶段划分G4-9 | 61×16384 | 三阶段(Stage1/2/3)划分检查（16384列为合并单元格造成，实际有效约10~15列） |
| 2 | 债权投资减值准备测算表G4-10 | 37×19 | ECL计提测算（未审/审计调整/审定三栏） |
| 3 | 预期信用损失的计量测试G4-11 | 50×10 | ECL方法评价（组合依据/信用损失率确定） |
| 4 | 减值准备转回（收回）、核销检查表G4-12 | 43×20 | 转回/核销检查 |
| 5 | 凭证检查表G4-13 | 97×19 | 凭证核对检查（抽样+逐笔测试） |
| 6 | 参考-中证协《证券公司金融工具减值指引》 | 178×13 | 参考材料（只读） |
| 7 | 参考-根据剩余期限折算PD | 20×2 | PD折算参考表（只读） |

**宽表处理策略**：
- G4-9三阶段划分：实际列数运行时确认(约10~15列)，合并单元格fallback
- G4-10减值测算(19列)：2区段Tab（未审数+审计调整 / 审定数+差异）
- G4-12转回核销(20列)：2区段Tab（转回检查 / 核销检查）
- G4-13凭证检查(19列)：3区段Tab（记账凭证基础列 / 支持性文件+核对内容 / 结论+备注）

**子目录组织**：
- impairment/: 三阶段G4-9 + 减值测算G4-10 + ECL计量G4-11 + 转回核销G4-12
- voucher/: 凭证检查G4-13
- reference/: 参考材料（只读显示）

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ✅ 抽凭引擎: G4-13凭证检查表集成GtVoucherSamplingEngine dialog
- ❌ 截止自动提取: 本组sheet不涉及截止测试
- ❌ 附注EventBus: 本组sheet不涉及附注联动
- ✅ 行级OCR: G4-13凭证检查表附件列上传后OCR识别→填入
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **ECL**: Expected Credit Loss，预期信用损失，IFRS9/CAS22要求的金融资产减值计量方法
- **Stage_Classification**: 三阶段划分（Stage1/Stage2/Stage3），根据信用风险变化程度确定减值计提方法
- **Stage1**: 信用风险自初始确认以来未显著增加，按12个月ECL计提减值
- **Stage2**: 信用风险自初始确认以来显著增加但未发生信用减值，按整个存续期ECL计提
- **Stage3**: 已发生信用减值（如违约、重大财务困难），按整个存续期ECL计提且利息按净额确认
- **Credit_Loss_Rate**: 信用损失率(②)，预期信用损失占账面余额的比率
- **Impairment_Provision**: 减值准备(③)，= 账面余额(①) × 信用损失率(②)
- **Book_Balance**: 账面余额(①)，债权投资的账面总额（未扣减值准备）
- **PV_Future_CashFlow**: 预计未来现金流量现值，用于计算ECL的折现后预期回收金额
- **Audit_Adjustment**: 审计调整，审计师识别的账面余额或信用损失率调整
- **Adjudicated_Amount**: 审定数，经审计调整后的最终确认金额
- **PD**: Probability of Default，违约概率，根据信用评级和剩余期限确定
- **LGD**: Loss Given Default，违约损失率，违约后预计无法收回的比例
- **EAD**: Exposure at Default，违约风险敞口，违约时的预计信用风险暴露金额
- **Significant_Increase**: 信用风险显著增加，从Stage1转入Stage2的判定标准
- **Credit_Impaired**: 已发生信用减值，从Stage2转入Stage3的判定标准
- **Reversal**: 减值准备转回，原计提减值的客观证据消失后冲回已计提金额
- **Write_Off**: 核销，确认无法收回的债权直接从账面消除
- **Voucher_Check**: 凭证检查(G4-13)，对会计凭证的完整性/授权/账务处理正确性逐项核对
- **Supporting_Document**: 支持性文件，凭证附件（合同/审批/划款指令等）
- **OCR_Integration**: 行级OCR集成，上传凭证附件→OCR识别→确认弹窗→填入核对结果
- **Formula_Chain**: 公式链，G4-10减值测算表的审计调整列间计算关系
- **G4_ECL_Component**: g4-bond-investment-ecl专属组件，覆盖7个sheet的减值与ECL部分

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G4债权投资底稿(ECL组)按sheetName prop分发到独立子组件, so that 7个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G4-Bond-Investment-ECL 组件 SHALL 注册新componentType: `g4-bond-investment-ecl`，主入口为 GtG4BondInvestmentEcl.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE G4-Bond-Investment-ECL 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（7个sheet按需加载：G4-9、G4-10、G4-11、G4-12、G4-13、参考-减值指引、参考-PD折算）
1.3 THE G4-Bond-Investment-ECL 组件 SHALL 在htmlRendererRegistry中注册'g4-bond-investment-ecl'→GtG4BondInvestmentEcl映射
1.4 THE G4-Bond-Investment-ECL 组件 SHALL 在wp_code_overrides.json中将G4-9、G4-10、G4-11、G4-12、G4-13、参考-减值指引、参考-PD折算的componentType统一映射为'g4-bond-investment-ecl'（7个wp_code条目）
1.5 THE G4-Bond-Investment-ECL 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g4-bond-investment-ecl'
1.6 IF htmlData prop为null, THEN THE GtG4BondInvestmentEcl.vue SHALL 自行调用render-config?force_component_type=g4-bond-investment-ecl获取渲染数据（selfLoad模式）
1.7 IF sheetName正则提取编码失败或提取的编码不在已迁移子组件列表中, THEN THE GtG4BondInvestmentEcl.vue SHALL 渲染OnlyOffice fallback组件
1.8 THE G4-Bond-Investment-ECL 组件 SHALL 采用sheetName v-if dispatch模式（非el-tabs），通过正则从sheetName提取编码(G4-9/G4-10/G4-11/G4-12/G4-13/参考-减值指引/参考-PD折算)分发到对应子组件
1.9 THE 子组件 SHALL 按子目录组织：impairment/(G4-9+G4-10+G4-11+G4-12) / voucher/(G4-13) / reference/(参考-减值指引+参考-PD折算)

### Requirement 2: 三阶段划分G4-9（列式结构：投资项目为列）

**User Story:** As a 审计助理, I want to 在精美HTML中逐项判断每个债权投资的ECL阶段分类, so that 我能确认企业对信用风险变化程度的判断是否合理并确定减值计提方法。

#### Acceptance Criteria

2.1 THE G4-9三阶段划分 SHALL 采用**列式转置结构**渲染（源模板中投资项目作为列头：投资1/投资2/投资3/...，行为"需要考虑的信息"检查项），前端转换为行式交互视图
2.2 THE G4-9三阶段划分 SHALL 分为三个检查区块（对应源模板三部分）：
   - **(一) 信用风险是否显著增加**：13项考虑因素（内部价格/利率条款/外部指标/评级/经营/监管/逾期等）×每投资项目一列(是/否/不适用)
   - **(二) 是否具有较低信用风险**：3项同时满足条件×每投资项目一列(是/否)
   - **(三) 已发生信用减值的评估**：8项可观察信息×每投资项目一列(是/否)
2.3 THE G4-9 SHALL 将列式源结构转换为用户友好的**行式交互视图**：每个投资项目一行，列为：投资项目|信用风险显著增加判定(综合)|较低信用风险(综合)|已发生信用减值(综合)|企业划分阶段(下拉)|审计判断阶段(下拉)|是否一致(公式)|差异说明|索引
2.4 THE G4-9 SHALL 支持**展开/折叠详情模式**：点击投资项目行可展开显示该项目的13+3+8项逐项检查明细（源模板原始列式数据的逐项填写）
2.5 THE Stage_Classification_Logic SHALL 实现三阶段判定规则：
   - WHEN 部分(三)任一可观察信息为"是", THEN 审计判断阶段建议为Stage3
   - WHEN 部分(一)任一考虑因素为"是"（即信用风险显著增加）且部分(三)均为"否", THEN 审计判断阶段建议为Stage2
   - WHEN 部分(二)全部为"是"（具有较低信用风险）且部分(三)均为"否", THEN 审计判断阶段建议为Stage1
   - WHEN 部分(一)均为"否"且部分(三)均为"否", THEN 审计判断阶段建议为Stage1
2.6 THE Formula_Engine SHALL 计算"是否一致" = (企业划分阶段 === 审计判断阶段)，一致显示绿色"✓一致"，不一致显示红色"✗不一致"
2.7 WHEN 企业划分阶段与审计判断阶段不一致时, THE 系统 SHALL 以红色高亮该行并强制要求填写差异说明
2.8 THE G4-9三阶段划分 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示：
   - Stage1判定标准：信用风险自初始确认以来未显著增加（或具有较低信用风险）
   - Stage2判定标准：信用风险显著增加但未发生信用减值
   - Stage3判定标准：已发生信用减值（出现8项可观察信息之一）
2.9 THE G4-9三阶段划分 SHALL 底部汇总区显示各阶段统计：Stage1数量/Stage2数量/Stage3数量/不一致项数量
2.10 THE G4-9三阶段划分 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
2.11 THE G4-9三阶段划分 SHALL 支持动态投资项目增删（ElMessageBox.prompt输入投资项目名称，新增即增加一列→转换为行式视图新增一行）+ 导入导出
2.12 THE G4-9 SHALL 对源模板16384列（合并单元格造成的虚列）进行智能解析：仅取实际有数据的列（投资1~投资N），忽略空列
2.13 THE G4-9 SHALL 支持参考材料侧边弹出（点击行可查看对应中证协减值指引原文）

### Requirement 3: 减值准备测算表G4-10（ECL计提测算，19列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中填写减值准备测算表, so that 我能逐项验证企业计提的预期信用损失金额并记录审计调整。

#### Acceptance Criteria

3.1 THE G4-10减值准备测算表 SHALL 显示37行×19列，拆为2区段Tab：
   - **Tab1: 未审数+审计调整(11列)**：投资项目|账面余额①|预计未来现金流量现值|预期信用损失率②|减值准备③(公式)|账面价值④(公式)|账面余额调整⑤|调整后信用损失率②A|减值准备调整⑥(公式)
   - **Tab2: 审定数+差异(8列)**：投资项目|审定账面余额⑦(公式)|审定减值准备⑧(公式)|审定账面价值⑨(公式)|上年减值准备|本年计提(公式)|本年转回(公式)|差异说明
3.2 THE Formula_Engine SHALL 计算未审减值准备：③ = ① × ②（账面余额 × 信用损失率），结果保留2位小数
3.3 THE Formula_Engine SHALL 计算未审账面价值：④ = ① - ③（账面余额 - 减值准备），结果保留2位小数
3.4 THE Formula_Engine SHALL 计算减值准备调整：⑥ = ⑤ × ②A + ① × (②A - ②)（账面余额调整×调整后损失率 + 原余额×损失率差异），结果保留2位小数
3.5 THE Formula_Engine SHALL 计算审定账面余额：⑦ = ① + ⑤（原余额 + 余额调整），结果保留2位小数
3.6 THE Formula_Engine SHALL 计算审定减值准备：⑧ = ③ + ⑥（未审减值 + 减值调整），结果保留2位小数
3.7 THE Formula_Engine SHALL 计算审定账面价值：⑨ = ⑦ - ⑧（审定余额 - 审定减值），结果保留2位小数
3.8 THE G4-10减值准备测算表 SHALL 按Stage分组显示：Stage1项目/Stage2项目/Stage3项目/合计行
3.9 THE G4-10减值准备测算表 SHALL 分组小计自动汇总（各Stage小计+总计）
3.10 WHEN 用户切换区段Tab时, THE G4-10减值准备测算表 SHALL 保持当前选中行的行索引不变（行同步）
3.11 THE G4-10减值准备测算表 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
3.12 THE G4-10减值准备测算表 SHALL 支持动态行增删（ElMessageBox.prompt输入投资项目名称）+ 导入导出
3.13 THE G4-10减值准备测算表 SHALL 公式列tooltip显示完整公式来源（如"⑥ = ⑤×②A + ①×(②A-②)"）

### Requirement 4: 预期信用损失计量测试G4-11（ECL方法评价）

**User Story:** As a 审计助理, I want to 在精美HTML中评价企业的ECL计量方法, so that 我能判断组合划分依据和信用损失率确定方法是否合理。

#### Acceptance Criteria

4.1 THE G4-11预期信用损失计量测试 SHALL 显示50行×10列，分为四个section：
   - **(一) ECL计量方法评价**：概述企业采用的ECL方法（问卷/叙述混合）
   - **(二) 组合划分依据**：评价企业对金融资产的组合分组是否合理
   - **(三) 信用损失率的确定**：评价PD/LGD/EAD参数来源和计算方法
   - **(四) 审计结论**：综合评价
4.2 THE G4-11 section(一) SHALL 列结构：检查项目|检查内容(方法论上下文)|企业采用方法(textarea)|审计评价(合理/基本合理/不合理 下拉)|说明(textarea)
4.3 THE G4-11 section(二) SHALL 列结构：组合名称|划分依据|信用风险特征|样本量|审计评价(合理/不合理 下拉)|说明(textarea)
4.4 THE G4-11 section(三) SHALL 列结构：参数名称(PD/LGD/EAD)|数据来源|计算方法|审计验证结果|审计评价(合理/基本合理/不合理 下拉)|说明(textarea)
4.5 THE G4-11 section(四) SHALL 包含综合审计结论textarea（带AI辅助按钮）
4.6 THE G4-11 SHALL 每个section标题行右侧提供AI辅助按钮
4.7 THE G4-11 SHALL 顶部方法论上下文（琥珀色左边线+浅黄背景）显示ECL计量的三种方法简介（个别评估/组合评估/简化方法）
4.8 THE G4-11 SHALL 底部编制提示details折叠区
4.9 THE G4-11 SHALL section(二)和section(三)支持动态行增删（ElMessageBox.prompt输入组合名称/参数名称）

### Requirement 5: 减值准备转回核销检查表G4-12（20列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中检查减值准备的转回和核销, so that 我能验证转回/核销的合理性和合规性。

#### Acceptance Criteria

5.1 THE G4-12减值转回核销检查表 SHALL 显示43行×20列，拆为2区段Tab：
   - **Tab1: 转回（收回）检查(10列)**：序号|单位名称|转回原因|收回方式|原确定坏账准备依据|收回或转回金额|收回前累计计提|合理性分析(textarea)|是否合理(合理/不合理 下拉)|索引
   - **Tab2: 核销检查(10列)**：序号|单位名称|核销性质(到期/逾期/其他 下拉)|核销金额|核销原因(textarea)|核销程序(textarea)|是否关联交易(是/否)|合理性分析(textarea)|是否合理(合理/不合理 下拉)|索引
5.2 THE G4-12 Tab1转回检查 SHALL 验证：转回金额 ≤ 收回前累计计提（转回金额不得超过原计提金额）
5.3 WHEN 转回金额 > 收回前累计计提时, THE 系统 SHALL 以红色高亮该行并显示校验错误"转回金额超过累计计提"
5.4 THE G4-12 Tab2核销检查 SHALL 对关联交易标记为"是"的行以橙色底色高亮提示关注
5.5 WHEN 用户切换区段Tab时, THE G4-12减值转回核销检查表 SHALL 保持当前行索引（行同步）
5.6 THE G4-12 SHALL 各Tab底部显示合计行（转回金额合计/核销金额合计）
5.7 THE G4-12 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
5.8 THE G4-12 SHALL Tab1和Tab2各自支持动态行增删（ElMessageBox.prompt输入单位名称）+ 导入导出
5.9 THE G4-12 SHALL 支持GtIndexChip索引列跳转

### Requirement 6: 凭证检查表G4-13（97行×19列→3区段Tab+行级OCR）

**User Story:** As a 审计助理, I want to 在精美HTML中完成凭证检查并集成OCR自动识别, so that 我能高效核对凭证完整性和会计处理正确性。

#### Acceptance Criteria

6.1 THE G4-13凭证检查表 SHALL 显示97行×19列，拆为3区段Tab：
   - **Tab1: 记账凭证基础列(8列)**：日期|凭证编号|业务内容|对方科目|明细科目|借方金额|贷方金额|📎附件
   - **Tab2: 支持性文件+核对内容(7列)**：支持性文件描述|核对1-原始凭证完整(✓/✗)|核对2-有授权批准(✓/✗)|核对3-账务处理正确(✓/✗)|核对4-初始成本计算正确(✓/✗)|核对5-利息计算正确(✓/✗)|核对6-减值计提正确(✓/✗)
   - **Tab3: 结论+备注(4列)**：索引号|是否异常(是/否)|异常说明(textarea)|备注
6.2 THE G4-13凭证检查表 SHALL 分为两个区块：(一)借方区 和 (二)贷方区，分别记录借方凭证和贷方凭证
6.3 THE G4-13 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog→抽样结果填入借方/贷方区）
6.4 THE G4-13 SHALL Tab1📎附件列支持行级OCR：
   - 点击📎图标上传附件文件
   - 上传后调用 `/d4/contract-ocr` 端点进行OCR识别
   - 识别完成后弹出ElMessageBox确认弹窗展示识别结果
   - 用户确认后将识别结果自动填入当前行的业务内容/对方科目/金额等字段
6.5 THE G4-13 SHALL 对97行启用虚拟滚动
6.6 THE G4-13 SHALL 借贷平衡校验：SUM(借方金额) vs SUM(贷方金额)，差额以红色显示在顶部汇总区
6.7 WHEN 核对内容6项中任一项为"✗"时, THE 系统 SHALL 自动将该行"是否异常"设为"是"并以红色高亮
6.8 WHEN 用户切换区段Tab时, THE G4-13凭证检查表 SHALL 保持当前选中行的行索引不变（行同步）
6.9 THE G4-13 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
6.10 THE G4-13 SHALL 支持动态行增删（ElMessageBox.prompt输入凭证编号）+ 导入导出
6.11 THE G4-13 SHALL 支持GtIndexChip索引列跳转
6.12 THE G4-13 SHALL Tab2核对内容列使用checkbox组（6项勾选），全部✓时显示绿色"全部通过"badge

### Requirement 7: 参考材料（只读显示）

**User Story:** As a 审计助理, I want to 在底稿中查阅减值指引和PD折算参考, so that 我能在填写减值相关底稿时随时参考标准文件。

#### Acceptance Criteria

7.1 THE 参考-减值指引 SHALL 以只读HTML表格渲染178行×13列的中证协金融工具减值指引内容
7.2 THE 参考-PD折算 SHALL 以只读HTML表格渲染20行×2列的剩余期限→PD折算对照表
7.3 THE 参考材料 SHALL 启用全文搜索（Ctrl+F高亮匹配）
7.4 THE 参考-减值指引 SHALL 对178行启用虚拟滚动
7.5 THE 参考材料 SHALL 不支持编辑（所有单元格为只读状态，无保存按钮）
7.6 THE 参考材料 SHALL 顶部显示蓝色信息条"本sheet为参考材料，仅供查阅"

### Requirement 8: 公式引擎（G4-ECL专属）

**User Story:** As a 开发者, I want to 实现G4债权投资(ECL组)公式引擎, so that ECL计算/审计调整公式链/借贷平衡/三阶段判定等公式可PBT验证。

#### Acceptance Criteria

8.1 THE Formula_Engine SHALL 实现 `calcImpairmentProvision(bookBalance: number, creditLossRate: number): number`，返回 `bookBalance × creditLossRate`（减值准备③ = 账面余额① × 信用损失率②），结果保留2位小数
8.2 THE Formula_Engine SHALL 实现 `calcBookValue(bookBalance: number, impairmentProvision: number): number`，返回 `bookBalance - impairmentProvision`（账面价值④ = 账面余额① - 减值准备③），结果保留2位小数
8.3 THE Formula_Engine SHALL 实现 `calcImpairmentAdjustment(balanceAdj: number, adjRate: number, origBalance: number, origRate: number): number`，返回 `balanceAdj × adjRate + origBalance × (adjRate - origRate)`（减值调整⑥ = ⑤×②A + ①×(②A-②)），结果保留2位小数，返回值可为负数（当②A < ②即审计师调低信用损失率时，代表减值准备冲回）
8.4 THE Formula_Engine SHALL 实现 `calcAdjustedBalance(origBalance: number, balanceAdj: number): number`，返回 `origBalance + balanceAdj`（审定账面余额⑦ = ① + ⑤），结果保留2位小数
8.5 THE Formula_Engine SHALL 实现 `calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number`，返回 `origImpairment + impairmentAdj`（审定减值准备⑧ = ③ + ⑥），结果保留2位小数
8.6 THE Formula_Engine SHALL 实现 `calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number`，返回 `adjBalance - adjImpairment`（审定账面价值⑨ = ⑦ - ⑧），结果保留2位小数
8.7 THE Formula_Engine SHALL 实现 `determineStage(hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean): 'Stage1' | 'Stage2' | 'Stage3'`：
   - WHEN hasCreditImpairment=true, THEN 返回'Stage3'（部分三任一可观察信息为"是"）
   - WHEN hasSignificantIncrease=true AND hasCreditImpairment=false, THEN 返回'Stage2'（部分一有显著增加但未减值）
   - WHEN hasLowCreditRisk=true AND hasCreditImpairment=false, THEN 返回'Stage1'（具有较低信用风险）
   - WHEN hasSignificantIncrease=false AND hasCreditImpairment=false, THEN 返回'Stage1'（无显著增加且未减值）
8.8 THE Formula_Engine SHALL 实现 `isStageConsistent(companyStage: string, auditStage: string): boolean`，返回 `companyStage === auditStage`
8.9 THE Formula_Engine SHALL 实现 `isReversalValid(reversalAmount: number, accumulatedProvision: number): boolean`，返回 `reversalAmount <= accumulatedProvision`（转回金额不得超过累计计提）
8.10 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced(debits: number[], credits: number[]): boolean`，当 `|SUM(debits) - SUM(credits)| < 0.01` 时返回true
8.11 THE Formula_Engine SHALL 实现 `calcDebitCreditDifference(debits: number[], credits: number[]): number`，返回 `SUM(debits) - SUM(credits)`，结果保留2位小数
8.12 THE Formula_Engine SHALL 实现 `isVoucherNormal(checks: boolean[]): boolean`，当6项核对内容全部为true时返回true（任一false则异常）
8.13 THE Formula_Engine SHALL 实现 `calcSumColumn(values: number[]): number`，返回数组元素之和（用于合计行），空数组返回0
8.14 IF 任一公式函数接收到 null、undefined、空串或 NaN 作为数值参数, THEN THE Formula_Engine SHALL 通过 `parseNum` 将其转换为 0 后参与计算，不得抛出异常或返回 NaN
8.15 THE Formula_Engine SHALL 导出所有公式函数为纯函数（无副作用、无 Vue 响应式依赖、无外部状态访问），支持 fast-check PBT 以 numRuns≥100 验证各公式的代数恒等性

### Requirement 9: 跨模块联动（版本链+抽凭+OCR+复核）

**User Story:** As a 开发者, I want to G4(ECL组)底稿集成跨模块联动, so that 版本链/抽凭/OCR/复核全部可用。

#### Acceptance Criteria

9.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
9.2 THE 抽凭引擎 SHALL 在G4-13凭证检查表集成GtVoucherSamplingEngine（dialog→抽样结果样本填入）
9.3 THE 行级OCR SHALL 在G4-13 Tab1📎附件列集成：POST `/d4/contract-ocr` → ElMessageBox确认 → merge填入当前行字段
9.4 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
9.5 THE G4(ECL组) SHALL 不集成截止自动提取（本组sheet不涉及截止测试）
9.6 THE G4(ECL组) SHALL 不集成附注EventBus（本组sheet不涉及附注联动）

### Requirement 10: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

10.1 THE Import_Export SHALL 对动态行表格支持导入导出：G4-9三阶段划分/G4-10减值测算/G4-12转回核销(Tab1+Tab2)/G4-13凭证检查（共4张）
10.2 THE Import_Export SHALL 使用useG4EclImportExport composable（后端三端点：导出模板/导出数据/导入数据）
10.3 THE Import_Export SHALL G4-10按2区段分sheet导出、G4-12按2个Tab分sheet导出、G4-13按3区段分sheet导出（多区块分sheet导出）
10.4 THE AI_Assistant SHALL 提供AI辅助section：stage-classification-conclusion（三阶段结论）/ecl-measurement-conclusion（ECL测算结论）/ecl-method-evaluation（ECL方法评价）/reversal-writeoff-conclusion（转回核销结论）/voucher-check-conclusion（凭证检查结论）
10.5 THE AI_Assistant SHALL 在每个文本区section标题行右侧提供AI辅助按钮
10.6 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 11: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且减值测算和凭证检查表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

11.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
11.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源（如"③ = ① × ②"、"⑥ = ⑤×②A + ①×(②A-②)"）
11.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
11.4 THE UI SHALL 编制提示details折叠底部
11.5 THE UI SHALL 动态行新增需ElMessageBox.prompt输入名称确认后创建
11.6 THE Performance SHALL 对行数>50的表启用虚拟滚动（G4-9约61行/G4-13为97行/参考-减值指引178行）
11.7 THE Performance SHALL defineAsyncComponent懒加载所有子组件
11.8 THE UI SHALL G4-10和G4-12区段Tab切换流畅（Tab切换无闪烁/行同步无延迟）
11.9 THE UI SHALL G4-13凭证检查表Tab2核对内容使用checkbox交互（勾选即✓），全通过时绿色badge
11.10 THE UI SHALL G4-9三阶段划分不一致行红色高亮+强制差异说明
11.11 THE UI SHALL 参考材料sheet显示蓝色信息条+只读模式（无编辑/保存UI）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G4(ECL组)公式引擎的正确性。

**P1: 减值准备公式** — ∀ bookBalance ∈ ℝ≥0, rate ∈ [0,1]: calcImpairmentProvision(bookBalance, rate) === round(bookBalance × rate, 2)

**P2: 账面价值恒等** — ∀ bookBalance ∈ ℝ≥0, impairment ∈ ℝ≥0 where impairment ≤ bookBalance: calcBookValue(bookBalance, impairment) === round(bookBalance - impairment, 2)

**P3: 审计调整公式链一致性** — ∀ ①,②,⑤,②A ∈ ℝ: calcAdjustedBookValue(calcAdjustedBalance(①,⑤), calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②))) === round((①+⑤) - (①×② + ⑤×②A + ①×(②A-②)), 2)（即 ⑨ = ⑦ - ⑧ 恒等成立）

**P4: 审计调整公式展开** — ∀ balanceAdj, adjRate, origBalance, origRate ∈ ℝ: calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate) === round(balanceAdj×adjRate + origBalance×(adjRate-origRate), 2)

**P5: 三阶段划分确定性** — ∀ (hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment) ∈ boolean³: determineStage的输出仅取决于3个布尔输入，确定性映射到Stage1/Stage2/Stage3之一

**P6: 三阶段划分优先级** — ∀ inputs where hasCreditImpairment=true: determineStage(...) === 'Stage3'（信用减值事件优先级最高，无论其他条件如何）

**P7: Stage1必要条件** — ∀ inputs: determineStage(...) === 'Stage1' → (hasSignificantIncrease=false AND hasCreditImpairment=false)（Stage1要求无显著增加且未减值）

**P8: 阶段一致性判定** — ∀ s1, s2 ∈ {'Stage1','Stage2','Stage3'}: isStageConsistent(s1, s2) ↔ (s1 === s2)

**P9: 转回有效性单调性** — ∀ reversal ∈ ℝ≥0, accumulated ∈ ℝ≥0: isReversalValid(reversal, accumulated) ↔ (reversal ≤ accumulated)

**P10: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P11: 凭证异常判定完备性** — ∀ checks ∈ boolean[6]: isVoucherNormal(checks) ↔ (checks[0] AND checks[1] AND checks[2] AND checks[3] AND checks[4] AND checks[5])

**P12: 合计行加法交换律** — ∀ values ∈ ℝ[]: calcSumColumn(values) === calcSumColumn(shuffle(values))（求和与顺序无关）

**P13: parseNum健壮性** — ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n（有效数字透传）

**P14: 审定减值准备=未审+调整** — ∀ ①,②,⑤,②A ∈ ℝ≥0: calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②)) === round(①×② + ⑤×②A + ①×(②A-②), 2)
