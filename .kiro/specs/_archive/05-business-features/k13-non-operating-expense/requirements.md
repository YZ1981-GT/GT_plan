# Requirements Document: K13 营业外支出底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K营业外支出循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6711发生额)
- **美观性**：分组配色 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：编制提示
- **导入导出**：el-dropdown三级 + useK13ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K13营业外支出底稿的专属HTML精美组件构建。覆盖来自 `K13 营业外支出.xlsx` 的9个有效sheet。科目覆盖6711营业外支出（**损益类！取发生额**）。

**K13特点**：K循环损益类最简底稿（9 sheets）。①**损益类科目**！取发生额非余额（从tb_ledger取数，借方=支出）②营业外支出（与日常活动无关：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等）。审定表K13-1（69公式）+ 明细表K13-2（31公式）。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K13A**: 营业外支出实质性程序表K13A（复用a-program-console）
- **Adjudication_K13_1**: 审定表K13-1，19行11列69公式，损益类6711审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），30行14列
- **Disclosure_SOE**: 附注披露信息（国企），18行5列
- **Detail_K13_2**: 明细表K13-2，27行26列31公式，按去向的营业外支出明细
- **Adjustment_K13_3**: 调整分录汇总K13-3
- **NonOperating_Check_K13_4**: 营业外支出检查表K13-4
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6711，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K13营业外支出按sheetName分发, so that 9个sheet有序组织。

#### Acceptance Criteria

1. THE K13 组件 SHALL 注册componentType: `k13-non-operating-expense`，主入口GtK13NonOperatingExpense.vue
2. THE GtK13NonOperatingExpense.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K13 组件 SHALL defineAsyncComponent懒加载
4. THE K13 组件 SHALL 子目录：k13/core/
5. THE K13 组件 SHALL composable分层：useK13FormData + useK13FormulaEngine(纯函数) + useK13CrossSheet + useK13DualMode + useK13ImportExport
6. THE K13 组件 SHALL htmlRendererRegistry注册'k13-non-operating-expense'
7. THE K13 组件 SHALL wp_code_overrides: K13/K13-1~K13-4/K13A → 'k13-non-operating-expense'
8. THE K13 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K13 组件 SHALL selfLoad支持
10. THE K13 组件 SHALL checklist_responses存储，前缀"K13-{sheet}-{field}"

### Requirement 2: 审定表K13-1（69公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看营业外支出, so that 我能验证各去向支出发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K13_1 SHALL 按去向分行（非流动资产毁损报废损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失/其他）
2. THE Adjudication_K13_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期借方发生额累计（支出类借方增加），不取期末余额
5. THE Adjudication_K13_1 SHALL 与K13-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6711，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K13_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K13-2（26列31公式）

**User Story:** As a 审计助理, I want to 管理营业外支出明细, so that 每笔支出可逐项核对。

#### Acceptance Criteria

1. THE Detail_K13_2 SHALL 将26列拆为3区段Tab：基础(序号/支出去向/支出类型/对方单位/金额/发生日期) | 分析(占比/同比/说明) | 检查(依据文件/审批/凭证号/税前扣除性/结论/备注)
2. THE Formula_Engine SHALL 合计行联动审定表
3. THE Detail_K13_2 SHALL 动态行新增+导入导出
4. THE Detail_K13_2 SHALL 27行虚拟滚动+底部统计

### Requirement 4: 营业外支出检查表K13-4

**User Story:** As a 审计助理, I want to 执行营业外支出检查, so that 支出确认合规、分类正确。

#### Acceptance Criteria

1. THE NonOperating_Check_K13_4 SHALL 逐项检查：真实性/依据合规/审批完整/分类正确性(与日常活动无关)/期间归属/税前扣除性(捐赠/罚款税务处理)
2. THE NonOperating_Check_K13_4 SHALL 逐项"合规/不合规/不适用"+行级抽凭+行级OCR
3. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 5: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K13不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（支出类借方发生累计），非tb_balance期末余额
2. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
3. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 6: 附注披露 + 调整分录 + 公式引擎（纯函数）

**User Story:** As a 审计助理/开发者, I want to 生成附注、管理调整分录并验证公式, so that 披露完整、核心公式可PBT验证。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市30×14/国企18×5）+按去向披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K13_3 SHALL 借贷平衡+双向同步K13-1+publish 'adjustment:created'→A13+导入导出
3. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
4. THE Formula_Engine SHALL calcIncomeStatementOccurrence(debitOcc, creditOcc): 支出类发生额=借方发生-贷方发生
5. THE Formula_Engine SHALL calcYoYChange(current, prior): 同比变动率
6. THE Formula_Engine SHALL calcProportion(item, total): 占比
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
