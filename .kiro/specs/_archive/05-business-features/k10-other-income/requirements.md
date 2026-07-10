# Requirements Document: K10 其他收益底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K其他收益循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6117发生额) + 政府补助核对联动K7递延收益
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK10ImportExport
- **AI辅助**：多section AI（补助核对结论）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K10其他收益底稿的专属HTML精美组件构建。覆盖来自 `K10 其他收益.xlsx` 的10个有效sheet。科目覆盖6117其他收益（**损益类！取发生额**）。

**K10核心特殊**：①**损益类科目**！取发生额非余额（从tb_ledger取数）②**政府补助收益核对**（与日常活动相关的政府补助计入其他收益，与K7递延收益分摊去向核对一致性）③应收政府补助检查。审定表K10-1（69公式）+ 明细表K10-2（11公式）。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K10A**: 其他收益实质性程序表K10A（复用a-program-console）
- **Adjudication_K10_1**: 审定表K10-1，27行11列69公式，损益类6117审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），38行17列
- **Disclosure_SOE**: 附注披露信息（国企），17行6列
- **Detail_K10_2**: 明细表K10-2，43行12列11公式，按补助项目的其他收益明细
- **Adjustment_K10_3**: 调整分录汇总K10-3
- **Grant_Reconcile_K10_4**: 政府补助核对表K10-4，与K7递延收益分摊核对
- **Receivable_Grant_K10_5**: 应收政府补助检查表K10-5
- **OtherIncome_Check_K10_6**: 其他收益检查表K10-6
- **Grant_Reconcile_Engine**: 政府补助核对引擎（与递延收益分摊/直接计入核对）
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6117，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K10其他收益按sheetName分发, so that 10个sheet有序组织。

#### Acceptance Criteria

1. THE K10 组件 SHALL 注册componentType: `k10-other-income`，主入口GtK10OtherIncome.vue
2. THE GtK10OtherIncome.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K10 组件 SHALL defineAsyncComponent懒加载
4. THE K10 组件 SHALL 子目录：k10/core/（审定/明细/调整/附注） + k10/inspection/（补助核对/应收补助/检查）
5. THE K10 组件 SHALL composable分层：useK10FormData + useK10FormulaEngine(纯函数) + useK10GrantReconcileEngine(纯函数) + useK10CrossSheet + useK10DualMode + useK10ImportExport
6. THE K10 组件 SHALL htmlRendererRegistry注册'k10-other-income'
7. THE K10 组件 SHALL wp_code_overrides: K10/K10-1~K10-6/K10A → 'k10-other-income'
8. THE K10 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K10 组件 SHALL selfLoad支持
10. THE K10 组件 SHALL checklist_responses存储，前缀"K10-{sheet}-{field}"

### Requirement 2: 审定表K10-1（69公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看其他收益, so that 我能验证各类补助收益发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K10_1 SHALL 按收益来源分行（政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他）
2. THE Adjudication_K10_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期贷方发生额累计（收益类贷方增加），不取期末余额
5. THE Adjudication_K10_1 SHALL 与K10-2明细/K10-4补助核对交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6117，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K10_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K10-2（12列11公式）

**User Story:** As a 审计助理, I want to 管理其他收益明细, so that 每笔补助收益可逐项核对。

#### Acceptance Criteria

1. THE Detail_K10_2 SHALL 显示：序号/补助项目/批文号/补助类型/来源(直接计入/递延分摊)/本期计入金额/计入依据/凭证号/结论/备注
2. THE Formula_Engine SHALL 合计行联动审定表
3. THE Detail_K10_2 SHALL 动态行新增+导入导出
4. THE Detail_K10_2 SHALL 43行虚拟滚动+底部统计

### Requirement 4: 政府补助核对表K10-4（补助核对引擎）

**User Story:** As a 审计助理, I want to 核对政府补助收益, so that 与递延收益分摊一致、分类正确。

#### Acceptance Criteria

1. THE Grant_Reconcile_K10_4 SHALL 显示：补助项目/收到金额/直接计入其他收益/递延分摊计入/合计计入(公式)/递延收益期末/是否与K7一致(公式)/结论
2. THE Grant_Reconcile_Engine SHALL 计算合计计入=直接计入+递延分摊
3. THE Grant_Reconcile_Engine SHALL 核对递延分摊金额与K7递延收益(2401)本期分摊一致性
4. WHEN 与K7分摊不一致时 SHALL 红色标记提示
5. THE Grant_Reconcile_K10_4 SHALL 与K7通过GtIndexChip双向跳转

### Requirement 5: 应收政府补助检查表K10-5 + 其他收益检查表K10-6

**User Story:** As a 审计助理, I want to 完成应收补助和综合检查, so that 补助确认完整合规。

#### Acceptance Criteria

1. THE Receivable_Grant_K10_5 SHALL 检查应收政府补助：批文依据/收款权利确凿性/预期可收回/确认时点
2. THE OtherIncome_Check_K10_6 SHALL 综合检查表，逐项"合规/不合规/不适用"判断（含分类正确性：与日常活动相关计其他收益 vs 与日常活动无关计营业外收入）
3. THE 检查表组 SHALL 支持行级抽凭+行级OCR（批文）
4. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 6: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K10不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（收益类贷方发生累计），非tb_balance期末余额
2. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
3. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 7: 附注披露 + 调整分录 + 公式引擎（纯函数）

**User Story:** As a 审计助理/开发者, I want to 生成附注、管理调整分录并验证公式, so that 披露完整、核心公式可PBT验证。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市38×17/国企17×6）+按补助类型披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K10_3 SHALL 借贷平衡+双向同步K10-1+publish 'adjustment:created'→A13+导入导出
3. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
4. THE Formula_Engine SHALL calcIncomeStatementOccurrence(creditOcc, debitOcc): 收益类发生额=贷方发生-借方发生
5. THE Grant_Reconcile_Engine SHALL calcTotalRecognized(direct, deferred): 合计计入=直接+递延分摊
6. THE Formula_Engine SHALL calcYoYChange(current, prior): 同比变动率
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
