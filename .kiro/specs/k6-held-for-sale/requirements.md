# Requirements Document: K6 持有待售资产和负债底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K持有待售循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(持有待售资产/负债) + 分类条件联动减值
- **美观性**：分组配色 + 五条件核对清单 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK6ImportExport
- **AI辅助**：多section AI（分类判断/减值结论）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K6持有待售资产和负债底稿的专属HTML精美组件构建。覆盖来自 `K6 持有待售资产和负债.xlsx` 的11个有效sheet。科目覆盖持有待售资产（借方/资产类）+ 持有待售负债（贷方/负债类）。

**K6核心特殊**：①**CAS42五条件分类判断**（可立即出售+出售极可能：已作出决议/已签协议/预计1年内完成/不太可能变更等）②**减值测试孰低法引擎**（账面价值与公允价值减去出售费用后的净额孰低）③处置组减值测试④不再满足持有待售条件的检查。审定表K6-1（45公式）+ 减值测试K6-5（16公式）+ 处置组减值K6-6（13公式）。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K6A**: 持有待售实质性程序表K6A（复用a-program-console）
- **Adjudication_K6_1**: 审定表K6-1，22行14列45公式，持有待售资产+负债审定
- **Disclosure_Listed**: 附注披露信息（上市公司），79行11列
- **Disclosure_SOE**: 附注披露信息（国企），61行8列
- **Detail_K6_2**: 明细表K6-2，40行15列12公式
- **Adjustment_K6_3**: 调整分录汇总K6-3
- **Initial_Recognition_K6_4**: 初始确认检查表K6-4（CAS42五条件）
- **Impairment_Test_K6_5**: 减值准备测试表(后续计量)K6-5，23行14列16公式
- **Group_Impairment_K6_6**: 处置组减值测试表(后续计量)K6-6，55行11列13公式
- **NoLonger_Check_K6_7**: 检查表(不再满足持有待售)K6-7
- **Classification_Engine**: CAS42五条件分类判断引擎
- **Impairment_Engine**: 减值孰低法引擎（账面价值 vs 公允价值减出售费用净额）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（持有待售资产+负债）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K6持有待售按sheetName分发, so that 11个sheet有序组织。

#### Acceptance Criteria

1. THE K6 组件 SHALL 注册componentType: `k6-held-for-sale`，主入口GtK6HeldForSale.vue
2. THE GtK6HeldForSale.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K6 组件 SHALL defineAsyncComponent懒加载
4. THE K6 组件 SHALL 子目录：k6/core/（审定/明细/调整/附注） + k6/impairment/（初始确认/减值测试/处置组减值/不再满足检查）
5. THE K6 组件 SHALL composable分层：useK6FormData + useK6FormulaEngine(纯函数) + useK6ClassificationEngine(纯函数) + useK6ImpairmentEngine(纯函数) + useK6CrossSheet + useK6DualMode + useK6ImportExport
6. THE K6 组件 SHALL htmlRendererRegistry注册'k6-held-for-sale'
7. THE K6 组件 SHALL wp_code_overrides: K6/K6-1~K6-7/K6A → 'k6-held-for-sale'
8. THE K6 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K6 组件 SHALL selfLoad支持
10. THE K6 组件 SHALL checklist_responses存储，前缀"K6-{sheet}-{field}"

### Requirement 2: 审定表K6-1（45公式，资产+负债双区块）

**User Story:** As a 审计助理, I want to 在审定表中查看持有待售资产和负债, so that 我能验证净额审定正确。

#### Acceptance Criteria

1. THE Adjudication_K6_1 SHALL 渲染双区块：持有待售资产(借方)区块 + 持有待售负债(贷方)区块
2. THE Adjudication_K6_1 SHALL 显示：项目|期初|本期增加|本期减少|减值准备|期末账面|未审|AJE|RJE|审定数|备注
3. THE Formula_Engine SHALL 资产类期末=期初+增加-减少-减值；负债类期末=期初+增加-减少
4. THE Formula_Engine SHALL 审定=未审+AJE+RJE
5. THE Adjudication_K6_1 SHALL 三角勾稽校验+红色高亮
6. WHEN 审定数变化时 SHALL 回写trial_balance（持有待售资产+负债）+发布'substantive:adjudicated'
7. THE Adjudication_K6_1 SHALL 与K6-2明细/K6-5减值测试交叉验证
8. THE Adjudication_K6_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K6-2（15列12公式）

**User Story:** As a 审计助理, I want to 管理持有待售明细, so that 各处置组/资产可逐项追踪。

#### Acceptance Criteria

1. THE Detail_K6_2 SHALL 显示：序号/处置组或资产名称/类别/账面原值/累计折旧摊销/减值准备/账面价值(公式)/公允价值净额/持有待售确认日/预计出售日/凭证/结论
2. THE Formula_Engine SHALL 账面价值=原值-累计折旧摊销-减值准备
3. THE Detail_K6_2 SHALL 合计行与K6-1审定表交叉验证
4. THE Detail_K6_2 SHALL 动态行新增（ElMessageBox.prompt）+导入导出
5. THE Detail_K6_2 SHALL 底部统计：处置组数/账面价值合计

### Requirement 4: CAS42五条件分类判断引擎（初始确认K6-4）

**User Story:** As a 审计助理, I want to 判断持有待售分类条件, so that 分类符合CAS42。

#### Acceptance Criteria

1. THE Initial_Recognition_K6_4 SHALL 逐条核对CAS42五条件：①可立即出售 ②已就出售作出决议 ③已与购买方签订不可撤销转让协议 ④出售预计一年内完成 ⑤售价合理不太可能变更/撤销
2. THE Classification_Engine SHALL 全部条件满足→'classified'(可分类为持有待售)；否则→'not_classified'
3. THE Initial_Recognition_K6_4 SHALL 五条件用核对清单（满足/不满足/不适用）
4. WHEN 任一条件不满足时 SHALL 红色提示不符合分类
5. THE Initial_Recognition_K6_4 SHALL AI辅助生成分类判断结论

### Requirement 5: 减值测试孰低法引擎（K6-5）

**User Story:** As a 审计助理, I want to 测试持有待售减值, so that 计量符合孰低法。

#### Acceptance Criteria

1. THE Impairment_Test_K6_5 SHALL 显示：项目/账面价值/公允价值/预计出售费用/公允价值净额(公式)/减值金额(公式)/已计提减值/本期应补提/结论
2. THE Impairment_Engine SHALL 计算公允价值净额=公允价值-预计出售费用
3. THE Impairment_Engine SHALL 计算减值金额=MAX(0, 账面价值-公允价值净额)（孰低法）
4. THE Impairment_Engine SHALL 计算本期应补提=减值金额-已计提减值
5. THE Impairment_Test_K6_5 SHALL 与K6-1审定减值准备交叉验证
6. THE Impairment_Test_K6_5 SHALL 23行虚拟滚动+AI辅助

### Requirement 6: 处置组减值测试表K6-6（13公式）

**User Story:** As a 审计助理, I want to 测试处置组减值, so that 处置组整体减值分摊正确。

#### Acceptance Criteria

1. THE Group_Impairment_K6_6 SHALL 显示：处置组/组内资产/账面价值/组整体减值/分摊比例(公式)/分摊减值(公式)/分摊后账面/结论
2. THE Impairment_Engine SHALL 处置组减值先抵商誉再按比例分摊至组内非流动资产
3. THE Group_Impairment_K6_6 SHALL 计算分摊比例=组内资产账面/组账面合计
4. THE Group_Impairment_K6_6 SHALL 55行虚拟滚动+与K6-5联动

### Requirement 7: 不再满足持有待售检查表K6-7

**User Story:** As a 审计助理, I want to 检查不再满足持有待售的情形, so that 终止确认处理正确。

#### Acceptance Criteria

1. THE NoLonger_Check_K6_7 SHALL 显示：项目/不再满足原因/重分类日/账面价值调整/结论
2. THE NoLonger_Check_K6_7 SHALL 判断不再满足时按较低者计量（可收回金额与假设未分类账面）
3. THE NoLonger_Check_K6_7 SHALL 逐项"合规/不合规/不适用"+行级抽凭
4. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 8: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市79×11/国企61×8）+持有待售分类披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K6_3 SHALL 借贷平衡+双向同步K6-1+publish 'adjustment:created'→A13+导入导出

### Requirement 9: 公式引擎与专项引擎（纯函数）

**User Story:** As a 开发者, I want to 实现公式与专项纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcBookValue(cost, dep, impairment): 账面价值=原值-折旧摊销-减值
3. THE Classification_Engine SHALL classifyHeldForSale(conditions[]): 全满足→'classified'否则'not_classified'
4. THE Impairment_Engine SHALL calcFairValueNet(fairValue, sellingCost): 公允净额=公允-出售费用
5. THE Impairment_Engine SHALL calcImpairment(bookValue, fairValueNet): 减值=MAX(0, 账面-公允净额)
6. THE Impairment_Engine SHALL calcAllocationRatio(itemBook, groupBook): 分摊比例
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
