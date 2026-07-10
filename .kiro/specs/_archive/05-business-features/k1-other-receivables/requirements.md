# Requirements Document: K1 其他应收款底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/K其他应收款循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射/适用性规则以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写（1221其他应收款/坏账准备）
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useK1ImportExport
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

K1其他应收款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `k1-other-receivables`，覆盖来自 `K1 其他应收款.xlsx` 的16个有效sheet。科目覆盖1221其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）。

**K1核心特殊**：①资产类三角勾稽（期末=期初+借方-贷方）；坏账准备备抵类（期末=期初+贷方-借方）②**ECL三阶段划分引擎**（正常/显著增加/已减值）③**坏账准备测算引擎**（账龄分析+迁徙率+ECL=EAD×PD×LGD）④账龄分析⑤大额其他应收款分析+长期未收回+关联方检查。审定表K1-1（47公式）+ 坏账明细K1-3（21公式）+ 坏账测算K1-8（11公式）。关键公式总数约110+。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_K1A**: 其他应收款实质性程序表K1A（复用a-program-console）
- **Adjudication_K1_1**: 审定表K1-1，89行13列47公式，资产类1221+坏账准备双区块审定
- **Disclosure_Listed**: 附注披露信息（上市公司），166行12列
- **Disclosure_SOE**: 附注披露信息（国企），130行10列
- **Detail_K1_2**: 明细表K1-2，50行36列10公式，按对象/账龄的其他应收款宽表
- **BadDebt_Detail_K1_3**: 坏账准备明细表K1-3，39行13列21公式，坏账准备计提/转回/核销
- **Adjustment_K1_4**: 调整分录汇总K1-4，AJE/RJE管理
- **LargeAmount_K1_5**: 大额其他应收款情况分析表K1-5，26行13列9公式
- **Policy_Check_K1_6**: 信用减值损失会计政策检查K1-6，政策检查段落型
- **Stage_Check_K1_7**: 三阶段划分检查表K1-7，63行11列，ECL阶段划分
- **BadDebt_Calc_K1_8**: 坏账准备测算K1-8，62行19列11公式，账龄+迁徙率+ECL测算
- **Writeoff_Check_K1_9**: 坏账准备转回(收回)核销检查表K1-9
- **Overdue_Check_K1_10**: 长期未收回款项检查表K1-10
- **RelatedParty_Check_K1_11**: 关联方及交易检查表K1-11
- **Receivable_Check_K1_12**: 其他应收款检查表K1-12
- **ECL_Engine**: ECL三阶段引擎（阶段判定+PD/LGD/EAD）
- **BadDebt_Calc_Engine**: 坏账准备测算引擎（账龄/迁徙率/ECL）
- **Aging_Analysis**: 账龄分析（1年内/1-2年/2-3年/3年以上）
- **Dual_Mode**: 双模式切换（HTML ↔ OnlyOffice）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（1221其他应收款 + 坏账准备）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K1其他应收款底稿按sheetName分发, so that 16个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE K1 组件 SHALL 注册componentType: `k1-other-receivables`，主入口为 GtK1OtherReceivables.vue
2. THE GtK1OtherReceivables.vue SHALL 接收 `sheetName` prop，用正则提取编码后v-if分发
3. THE K1 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE K1 组件 SHALL 拆为：k1/core/（审定/明细/调整/附注）、k1/impairment/（坏账明细/阶段/测算）、k1/inspection/（大额/政策/核销/长期/关联方/检查）
5. THE K1 组件 SHALL composable分层：useK1FormData + useK1FormulaEngine(纯函数) + useK1ECLEngine(纯函数) + useK1BadDebtCalcEngine(纯函数) + useK1CrossSheet + useK1DualMode + useK1ImportExport
6. THE K1 组件 SHALL 在htmlRendererRegistry中注册'k1-other-receivables'
7. THE K1 组件 SHALL 在wp_code_overrides.json中将K1/K1-1~K1-12/K1A映射为'k1-other-receivables'
8. THE K1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'k1-other-receivables'
9. THE GtK1OtherReceivables.vue SHALL 支持selfLoad
10. THE K1 组件 SHALL 使用 checklist_responses 存储，item_id前缀"K1-{sheet}-{field}"

### Requirement 2: 审定表K1-1（47公式，资产类+备抵双区块）

**User Story:** As a 审计助理, I want to 在审定表中查看其他应收款和坏账准备, so that 我能验证净额审定正确。

#### Acceptance Criteria

1. THE Adjudication_K1_1 SHALL 渲染双区块：其他应收款(1221借方)区块 + 坏账准备(贷方备抵)区块 + 账面净值
2. THE Adjudication_K1_1 SHALL 显示列：项目|期初|本期借方|本期贷方|期末|未审|AJE|RJE|审定数|变动率|备注
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 计算其他应收款期末=期初+借方-贷方（资产类）
5. THE Formula_Engine SHALL 计算坏账准备期末=期初+贷方-借方（备抵类）
6. THE Formula_Engine SHALL 计算账面净值=其他应收款-坏账准备
7. THE Adjudication_K1_1 SHALL 三角勾稽校验+红色高亮
8. WHEN 审定数变化时 SHALL 回写trial_balance（1221+坏账准备）+发布'substantive:adjudicated'
9. THE Adjudication_K1_1 SHALL 与K1-2明细/K1-3坏账明细合计交叉验证
10. THE Adjudication_K1_1 SHALL 底部显示审计说明+结论+复核入口，89行虚拟滚动

### Requirement 3: 明细表K1-2（36列+账龄）

**User Story:** As a 审计助理, I want to 管理其他应收款明细, so that 每笔款项按对象和账龄可追溯。

#### Acceptance Criteria

1. THE Detail_K1_2 SHALL 将36列拆为3区段Tab：基础(序号/往来对象/性质/关联关系/期初/期末) | 账龄(1年内/1-2年/2-3年/3年以上/账龄合计) | 减值(阶段/坏账准备/净值/凭证号/结论/备注)
2. THE Formula_Engine SHALL 计算账龄合计=各账龄区间之和，与期末余额勾稽
3. THE Detail_K1_2 SHALL 合计行与K1-1审定表交叉验证
4. THE Detail_K1_2 SHALL 支持动态行新增（ElMessageBox.prompt输入往来对象）+导入导出
5. THE Detail_K1_2 SHALL 对3年以上账龄行标记橙色背景
6. THE Detail_K1_2 SHALL 底部统计：往来笔数/期末合计/3年以上占比

### Requirement 4: 坏账准备明细表K1-3（21公式）

**User Story:** As a 审计助理, I want to 管理坏账准备的计提转回核销, so that 坏账变动完整可核对。

#### Acceptance Criteria

1. THE BadDebt_Detail_K1_3 SHALL 显示：项目|期初坏账|本期计提|本期转回|本期核销|期末坏账|计提比例
2. THE Formula_Engine SHALL 计算期末坏账=期初+计提-转回-核销
3. THE Formula_Engine SHALL 计算计提比例=期末坏账/其他应收款期末
4. THE BadDebt_Detail_K1_3 SHALL 与K1-8测算结果交叉验证（企业计提 vs 测算应计提）
5. THE BadDebt_Detail_K1_3 SHALL 与K1-1审定坏账准备合计一致

### Requirement 5: 三阶段划分检查表K1-7（ECL阶段）

**User Story:** As a 审计助理, I want to 划分ECL三阶段, so that 减值计量基础正确。

#### Acceptance Criteria

1. THE Stage_Check_K1_7 SHALL 显示：往来对象/期末余额/信用风险是否显著增加/是否已发生信用减值/划分阶段(公式)/上期阶段/变动说明
2. THE ECL_Engine SHALL 阶段判定：已减值→Stage3；显著增加→Stage2；否则→Stage1
3. THE Stage_Check_K1_7 SHALL 对Stage3行红色、Stage2行橙色高亮
4. THE Stage_Check_K1_7 SHALL 与K1-2明细阶段列联动
5. THE Stage_Check_K1_7 SHALL 63行虚拟滚动

### Requirement 6: 坏账准备测算K1-8（11公式，账龄+迁徙率+ECL）

**User Story:** As a 审计助理, I want to 测算坏账准备, so that 我能独立复核企业计提充分性。

#### Acceptance Criteria

1. THE BadDebt_Calc_K1_8 SHALL 将19列拆为2区段Tab：账龄迁徙(账龄/期末余额/迁徙率/预期损失率) | ECL测算(EAD/PD/LGD/ECL(公式)/企业计提/差异(公式)/测算结论)
2. THE BadDebt_Calc_Engine SHALL 计算ECL=EAD×PD×LGD
3. THE BadDebt_Calc_Engine SHALL 计算账龄组预期损失=期末余额×预期损失率
4. THE BadDebt_Calc_Engine SHALL 计算测算差异=测算应计提-企业计提
5. WHEN 差异>重要性水平时 SHALL 红色标记并提示调整
6. THE BadDebt_Calc_K1_8 SHALL 62行虚拟滚动+底部合计

### Requirement 7: 大额其他应收款分析表K1-5（9公式）

**User Story:** As a 审计助理, I want to 分析大额其他应收款, so that 重点款项获得充分关注。

#### Acceptance Criteria

1. THE LargeAmount_K1_5 SHALL 显示：往来对象/期末余额/占比(公式)/性质/形成原因/预计收回时间/收回可能性/后续核查
2. THE Formula_Engine SHALL 计算占比=单项余额/其他应收款合计
3. THE LargeAmount_K1_5 SHALL 按金额降序+超过阈值行高亮
4. THE LargeAmount_K1_5 SHALL 与K1-2明细联动GtIndexChip跳转

### Requirement 8: 检查表组（K1-9核销/K1-10长期未收回/K1-11关联方/K1-12检查）

**User Story:** As a 审计助理, I want to 完成各专项检查, so that 其他应收款的合规性全覆盖。

#### Acceptance Criteria

1. THE Writeoff_Check_K1_9 SHALL 核对坏账转回/收回/核销的审批依据+凭证+合规判断
2. THE Overdue_Check_K1_10 SHALL 检查长期未收回款项+账龄+收回措施+可回收性评估
3. THE RelatedParty_Check_K1_11 SHALL 检查关联方及交易+是否公允+是否披露
4. THE Receivable_Check_K1_12 SHALL 综合检查表，逐项"合规/不合规/不适用"判断
5. THE 检查表组 SHALL 支持行级抽凭（GtVoucherSamplingEngine）+行级OCR
6. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 9: 会计政策检查K1-6

**User Story:** As a 审计助理, I want to 检查信用减值损失会计政策, so that 减值政策合规。

#### Acceptance Criteria

1. THE Policy_Check_K1_6 SHALL 段落型检查：ECL模型选择/账龄组合划分/预期损失率确定依据/前瞻性调整
2. THE Policy_Check_K1_6 SHALL 提供AI辅助生成+琥珀色方法论上下文

### Requirement 10: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 生成其他应收款附注, so that 披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市166×12/国企130×10）
2. THE Disclosure SHALL 包含按账龄/按性质/按坏账计提方法披露
3. THE Disclosure SHALL 自动取数+AI辅助+subscribe 'substantive:adjudicated'刷新

### Requirement 11: 调整分录K1-4

**User Story:** As a 审计助理, I want to 管理调整分录, so that 联动审定表和A13。

#### Acceptance Criteria

1. THE Adjustment_K1_4 SHALL 借贷平衡校验+双向同步K1-1+publish 'adjustment:created'→A13+导入导出

### Requirement 12: ECL引擎与坏账测算引擎（纯函数）

**User Story:** As a 开发者, I want to 实现ECL与坏账测算纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE ECL_Engine SHALL determineStage(isImpaired, significantIncrease): 阶段判定∈{1,2,3}，isImpaired=true→3
2. THE BadDebt_Calc_Engine SHALL calcECL(ead, pd, lgd): ECL=EAD×PD×LGD
3. THE BadDebt_Calc_Engine SHALL calcAgingLoss(balance, lossRate): 账龄损失=余额×损失率
4. THE Formula_Engine SHALL calcAssetEndBalance(begin, debit, credit): 资产类期末=期初+借方-贷方
5. THE Formula_Engine SHALL calcContraEndBalance(begin, credit, debit): 备抵类期末=期初+贷方-借方
6. THE Formula_Engine SHALL calcBadDebtEnd(begin, provision, reversal, writeoff): 期末坏账=期初+计提-转回-核销
7. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
8. THE Formula_Engine SHALL calcNetValue(receivable, badDebt): 净值=应收-坏账
9. THE Formula_Engine SHALL calcProportion(item, total): 占比
10. THE Formula_Engine SHALL calcSubtotal(arr): 合计
