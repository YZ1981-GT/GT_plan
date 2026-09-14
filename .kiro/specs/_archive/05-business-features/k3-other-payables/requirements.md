# Requirements Document: K3 其他应付款底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K其他应付款循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(2241) + 长期挂账/关联方联动
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK3ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K3其他应付款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `k3-other-payables`，覆盖来自 `K3 其他应付款.xlsx` 的11个有效sheet。科目覆盖2241其他应付款（**贷方/负债类**）。

**K3核心特殊**：①**负债类科目**！期末=期初+贷方-借方（与资产类相反）②**完整性认定为主**（负债易少计）+ 反向截止测试③大额其他应付款分析④**长期挂账检查**（长期未偿付款项的真实性/清理必要性）⑤关联方及交易检查。审定表K3-1（50公式）+ 明细表K3-2（19公式）+ 大额分析K3-4（8公式）。关键公式总数约80+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K3A**: 其他应付款实质性程序表K3A（复用a-program-console）
- **Adjudication_K3_1**: 审定表K3-1，48行11列50公式，负债类2241审定
- **Disclosure_Listed**: 附注披露信息（上市公司），45行15列
- **Disclosure_SOE**: 附注披露信息（国企），45行15列
- **Detail_K3_2**: 明细表K3-2，51行27列19公式，按对象/账龄的其他应付款宽表
- **Adjustment_K3_3**: 调整分录汇总K3-3
- **LargeAmount_K3_4**: 大额其他应付款情况分析表K3-4，27行10列8公式
- **LongOutstanding_K3_5**: 长期挂账检查表K3-5，长期未偿付款项检查
- **RelatedParty_K3_6**: 关联方及交易检查表K3-6
- **Payable_Check_K3_7**: 其他应付款检查表K3-7
- **Formula_Engine**: 前端公式引擎（负债类！期末=期初+贷-借）
- **Completeness_Rule**: 完整性认定规则（负债少计风险+反向截止）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（2241）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K3其他应付款底稿按sheetName分发, so that 11个sheet有序组织。

#### Acceptance Criteria

1. THE K3 组件 SHALL 注册componentType: `k3-other-payables`，主入口GtK3OtherPayables.vue
2. THE GtK3OtherPayables.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K3 组件 SHALL defineAsyncComponent懒加载
4. THE K3 组件 SHALL 子目录：k3/core/（审定/明细/调整/附注） + k3/inspection/（大额/长期挂账/关联方/检查）
5. THE K3 组件 SHALL composable分层：useK3FormData + useK3FormulaEngine(纯函数) + useK3CrossSheet + useK3DualMode + useK3ImportExport
6. THE K3 组件 SHALL htmlRendererRegistry注册'k3-other-payables'
7. THE K3 组件 SHALL wp_code_overrides: K3/K3-1~K3-7/K3A → 'k3-other-payables'
8. THE K3 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K3 组件 SHALL selfLoad支持
10. THE K3 组件 SHALL checklist_responses存储，前缀"K3-{sheet}-{field}"

### Requirement 2: 审定表K3-1（50公式，负债类！）

**User Story:** As a 审计助理, I want to 在审定表中查看其他应付款, so that 我能验证负债余额完整正确。

#### Acceptance Criteria

1. THE Adjudication_K3_1 SHALL 显示：项目|期初|本期贷方|本期借方|期末|未审|AJE|RJE|审定数|变动率|备注
2. THE Formula_Engine SHALL 计算期末=期初+贷方-借方（**负债类2241！方向与资产类相反**）
3. THE Formula_Engine SHALL 计算审定=未审+AJE+RJE
4. THE Adjudication_K3_1 SHALL 三角勾稽校验（期末=期初+增加-减少，增加=贷方）+红色高亮
5. THE Adjudication_K3_1 SHALL 与K3-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance(2241)+发布'substantive:adjudicated'
7. THE Adjudication_K3_1 SHALL 底部审计说明+结论（含完整性认定说明）+复核入口

### Requirement 3: 明细表K3-2（27列19公式+账龄）

**User Story:** As a 审计助理, I want to 管理其他应付款明细, so that 每笔款项按对象和挂账时间可追溯。

#### Acceptance Criteria

1. THE Detail_K3_2 SHALL 将27列拆为3区段Tab：基础(序号/往来对象/性质/关联关系/期初/期末) | 账龄(1年内/1-2年/2-3年/3年以上/账龄合计) | 检查(形成原因/预计偿付时间/凭证号/结论/备注)
2. THE Formula_Engine SHALL 计算期末=期初+增加(贷)-减少(借)，账龄合计与期末勾稽
3. THE Detail_K3_2 SHALL 合计行与K3-1审定表交叉验证
4. THE Detail_K3_2 SHALL 动态行新增（ElMessageBox.prompt输入往来对象）+导入导出
5. THE Detail_K3_2 SHALL 对3年以上账龄行标记橙色背景（长期挂账风险）
6. THE Detail_K3_2 SHALL 底部统计：往来笔数/期末合计/3年以上占比

### Requirement 4: 大额其他应付款分析表K3-4（8公式）

**User Story:** As a 审计助理, I want to 分析大额其他应付款, so that 重点款项获得充分关注。

#### Acceptance Criteria

1. THE LargeAmount_K3_4 SHALL 显示：往来对象/期末余额/占比(公式)/性质/形成原因/预计偿付时间/是否长期挂账/后续核查
2. THE Formula_Engine SHALL 计算占比=单项余额/其他应付款合计
3. THE LargeAmount_K3_4 SHALL 按金额降序+超过阈值行高亮
4. THE LargeAmount_K3_4 SHALL 与K3-2明细联动GtIndexChip跳转

### Requirement 5: 长期挂账检查表K3-5

**User Story:** As a 审计助理, I want to 检查长期挂账款项, so that 长期未偿付款项的真实性和清理必要性获得评估。

#### Acceptance Criteria

1. THE LongOutstanding_K3_5 SHALL 显示：往来对象/挂账金额/挂账时间/账龄/形成原因/偿付计划/是否需转营业外收入/核查结论
2. THE LongOutstanding_K3_5 SHALL 对3年以上款项标记+提示评估是否需转销
3. THE LongOutstanding_K3_5 SHALL 逐项"合规/需处理/不适用"+行级抽凭
4. THE LongOutstanding_K3_5 SHALL 与K3-2明细3年以上行联动

### Requirement 6: 关联方及交易检查K3-6 + 其他应付款检查K3-7

**User Story:** As a 审计助理, I want to 完成关联方和综合检查, so that 其他应付款合规性全覆盖。

#### Acceptance Criteria

1. THE RelatedParty_K3_6 SHALL 检查关联方往来+是否公允+是否披露+资金占用
2. THE Payable_Check_K3_7 SHALL 综合检查表，逐项"合规/不合规/不适用"判断
3. THE 检查表组 SHALL 支持行级抽凭（GtVoucherSamplingEngine）+行级OCR
4. THE Payable_Check_K3_7 SHALL 包含反向截止测试（期后偿付/未入账负债检查，完整性认定）
5. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 7: 完整性认定与负债类特殊处理

**User Story:** As a 开发者, I want to 正确实现负债类完整性认定逻辑, so that K3聚焦负债少计风险。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现负债类期末公式：期末=期初+贷方-借方（区别于资产类）
2. THE Completeness_Rule SHALL 提供反向截止测试支持（期后偿付倒查未入账负债）
3. THE 审计说明 SHALL 强调完整性认定（负债易少计）
4. THE Detail_K3_2 SHALL 支持"疑似未入账"标记

### Requirement 8: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市45×15/国企45×15）+按账龄/按性质披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K3_3 SHALL 借贷平衡+双向同步K3-1+publish 'adjustment:created'→A13+导入导出

### Requirement 9: 公式引擎（纯函数）

**User Story:** As a 开发者, I want to 实现公式纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit): 负债类期末=期初+贷-借
3. THE Formula_Engine SHALL calcTriangleReconciliation(begin, inc, dec, end): 三角勾稽差额
4. THE Formula_Engine SHALL calcProportion(item, total): 占比
5. THE Formula_Engine SHALL calcSubtotal(arr): 合计
6. THE Formula_Engine SHALL calcChangeRate(current, prior): 变动率
