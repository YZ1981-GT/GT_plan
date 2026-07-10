# Requirements Document: K4 其他流动负债底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K其他流动负债循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(2245)
- **美观性**：分组配色 + 统计仪表板
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：编制提示
- **导入导出**：el-dropdown三级 + useK4ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K4其他流动负债底稿的专属HTML精美组件构建。覆盖来自 `K4 其他流动负债.xlsx` 的8个有效sheet。科目覆盖2245其他流动负债（**贷方/负债类**）。

**K4特点**：K循环负债类最简标准底稿（8 sheets）。负债类三角勾稽（期末=期初+贷方-借方）+审定表+明细表+检查表模式。完整性认定为主。审定表K4-1（72公式）+ 明细表K4-2（17公式）。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K4A**: 其他流动负债实质性程序表K4A（复用a-program-console）
- **Adjudication_K4_1**: 审定表K4-1，21行14列72公式，负债类2245审定
- **Disclosure_Listed**: 附注披露信息（上市公司），41行12列
- **Disclosure_SOE**: 附注披露信息（国企），14行12列
- **Detail_K4_2**: 明细表K4-2，25行18列17公式
- **Adjustment_K4_3**: 调整分录汇总K4-3
- **Check_K4_4**: 其他流动负债检查表K4-4
- **Formula_Engine**: 前端公式引擎（负债类！期末=期初+贷-借）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（2245）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K4其他流动负债按sheetName分发, so that 8个sheet有序组织。

#### Acceptance Criteria

1. THE K4 组件 SHALL 注册componentType: `k4-other-current-liabilities`，主入口GtK4OtherCurrentLiabilities.vue
2. THE GtK4OtherCurrentLiabilities.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K4 组件 SHALL defineAsyncComponent懒加载
4. THE K4 组件 SHALL 子目录：k4/core/
5. THE K4 组件 SHALL composable分层：useK4FormData + useK4FormulaEngine(纯函数) + useK4CrossSheet + useK4DualMode + useK4ImportExport
6. THE K4 组件 SHALL htmlRendererRegistry注册'k4-other-current-liabilities'
7. THE K4 组件 SHALL wp_code_overrides: K4/K4-1~K4-4/K4A → 'k4-other-current-liabilities'
8. THE K4 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K4 组件 SHALL selfLoad支持
10. THE K4 组件 SHALL checklist_responses存储，前缀"K4-{sheet}-{field}"

### Requirement 2: 审定表K4-1（72公式，负债类！）

**User Story:** As a 审计助理, I want to 在审定表中查看其他流动负债, so that 我能验证负债余额完整正确。

#### Acceptance Criteria

1. THE Adjudication_K4_1 SHALL 显示：项目|期初|本期贷方|本期借方|期末|未审|AJE|RJE|审定数|变动率|备注
2. THE Formula_Engine SHALL 计算期末=期初+贷方-借方（**负债类2245**）
3. THE Formula_Engine SHALL 计算审定=未审+AJE+RJE
4. THE Adjudication_K4_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_K4_1 SHALL 与K4-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance(2245)+发布'substantive:adjudicated'
7. THE Adjudication_K4_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K4-2（18列17公式）

**User Story:** As a 审计助理, I want to 管理其他流动负债明细, so that 各项目可逐项追踪。

#### Acceptance Criteria

1. THE Detail_K4_2 SHALL 将18列拆为2区段Tab：基础(序号/项目/性质/期初/期末) | 检查(增减原因/凭证号/核查结论/备注)
2. THE Formula_Engine SHALL 期末=期初+增加(贷)-减少(借)，合计行联动审定表
3. THE Detail_K4_2 SHALL 动态行新增（ElMessageBox.prompt）+导入导出
4. THE Detail_K4_2 SHALL 底部统计：项目数/期末合计

### Requirement 4: 其他流动负债检查表K4-4

**User Story:** As a 审计助理, I want to 执行检查, so that 分类正确性和完整性获得关注。

#### Acceptance Criteria

1. THE Check_K4_4 SHALL 逐项检查：分类正确性(应否归入其他负债)/流动性判断/完整性(反向截止)/合规性
2. THE Check_K4_4 SHALL 逐项"合规/不合规/不适用"+行级抽凭+行级OCR
3. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 5: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市41×12/国企14×12）+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K4_3 SHALL 借贷平衡+双向同步K4-1+publish 'adjustment:created'→A13+导入导出

### Requirement 6: 公式引擎（纯函数）

**User Story:** As a 开发者, I want to 实现公式纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit): 负债类期末=期初+贷-借
3. THE Formula_Engine SHALL calcTriangleReconciliation(begin, inc, dec, end): 三角勾稽差额
4. THE Formula_Engine SHALL calcSubtotal(arr): 合计
5. THE Formula_Engine SHALL calcChangeRate(current, prior): 变动率
