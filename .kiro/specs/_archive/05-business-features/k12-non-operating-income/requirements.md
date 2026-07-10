# Requirements Document: K12 营业外收入底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K营业外收入循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6301发生额)
- **美观性**：分组配色 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：编制提示
- **导入导出**：el-dropdown三级 + useK12ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K12营业外收入底稿的专属HTML精美组件构建。覆盖来自 `K12 营业外收入.xlsx` 的9个有效sheet。科目覆盖6301营业外收入（**损益类！取发生额**）。

**K12特点**：K循环损益类最简底稿（9 sheets）。①**损益类科目**！取发生额非余额（从tb_ledger取数，贷方=收入）②营业外收入（与日常活动无关：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等）。审定表K12-1（70公式）+ 明细表K12-2（31公式）。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K12A**: 营业外收入实质性程序表K12A（复用a-program-console）
- **Adjudication_K12_1**: 审定表K12-1，25行11列70公式，损益类6301审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），41行17列
- **Disclosure_SOE**: 附注披露信息（国企），29行5列
- **Detail_K12_2**: 明细表K12-2，27行26列31公式，按来源的营业外收入明细
- **Adjustment_K12_3**: 调整分录汇总K12-3
- **NonOperating_Check_K12_4**: 营业外收入检查表K12-4
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6301，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K12营业外收入按sheetName分发, so that 9个sheet有序组织。

#### Acceptance Criteria

1. THE K12 组件 SHALL 注册componentType: `k12-non-operating-income`，主入口GtK12NonOperatingIncome.vue
2. THE GtK12NonOperatingIncome.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K12 组件 SHALL defineAsyncComponent懒加载
4. THE K12 组件 SHALL 子目录：k12/core/
5. THE K12 组件 SHALL composable分层：useK12FormData + useK12FormulaEngine(纯函数) + useK12CrossSheet + useK12DualMode + useK12ImportExport
6. THE K12 组件 SHALL htmlRendererRegistry注册'k12-non-operating-income'
7. THE K12 组件 SHALL wp_code_overrides: K12/K12-1~K12-4/K12A → 'k12-non-operating-income'
8. THE K12 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K12 组件 SHALL selfLoad支持
10. THE K12 组件 SHALL checklist_responses存储，前缀"K12-{sheet}-{field}"

### Requirement 2: 审定表K12-1（70公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看营业外收入, so that 我能验证各来源收入发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K12_1 SHALL 按来源分行（政府补助/债务重组利得/资产盘盈利得/罚款收入/捐赠利得/无法支付款项转入/其他）
2. THE Adjudication_K12_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期贷方发生额累计（收入类贷方增加），不取期末余额
5. THE Adjudication_K12_1 SHALL 与K12-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6301，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K12_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K12-2（26列31公式）

**User Story:** As a 审计助理, I want to 管理营业外收入明细, so that 每笔收入可逐项核对。

#### Acceptance Criteria

1. THE Detail_K12_2 SHALL 将26列拆为3区段Tab：基础(序号/收入来源/收入类型/对方单位/金额/发生日期) | 分析(占比/同比/说明) | 检查(依据文件/凭证号/是否偶发/结论/备注)
2. THE Formula_Engine SHALL 合计行联动审定表
3. THE Detail_K12_2 SHALL 动态行新增+导入导出
4. THE Detail_K12_2 SHALL 27行虚拟滚动+底部统计

### Requirement 4: 营业外收入检查表K12-4

**User Story:** As a 审计助理, I want to 执行营业外收入检查, so that 收入确认合规、分类正确。

#### Acceptance Criteria

1. THE NonOperating_Check_K12_4 SHALL 逐项检查：真实性/依据合规/分类正确性(与日常活动无关，非其他收益6117)/期间归属/税务处理
2. THE NonOperating_Check_K12_4 SHALL 逐项"合规/不合规/不适用"+行级抽凭+行级OCR
3. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 5: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K12不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（收入类贷方发生累计），非tb_balance期末余额
2. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
3. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 6: 附注披露 + 调整分录 + 公式引擎（纯函数）

**User Story:** As a 审计助理/开发者, I want to 生成附注、管理调整分录并验证公式, so that 披露完整、核心公式可PBT验证。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市41×17/国企29×5）+按来源披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K12_3 SHALL 借贷平衡+双向同步K12-1+publish 'adjustment:created'→A13+导入导出
3. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
4. THE Formula_Engine SHALL calcIncomeStatementOccurrence(creditOcc, debitOcc): 收入类发生额=贷方发生-借方发生
5. THE Formula_Engine SHALL calcYoYChange(current, prior): 同比变动率
6. THE Formula_Engine SHALL calcProportion(item, total): 占比
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
