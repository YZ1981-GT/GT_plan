# Requirements Document: L2 应付利息底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **接收L1/L3利息测算+联动L8财务费用** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL2ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L2应付利息底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l2-interest-payable`，覆盖来自 `L2 应付利息.xlsx` 的8个有效sheet。科目覆盖2231应付利息（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L2核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方）②利息计提核对（与L1短期借款/L3长期借款利息测算联动，验证计提准确性）。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L2A**: 应付利息实质性程序表L2A（复用a-program-console）
- **Adjudication_L2_1**: 审定表L2-1，29×15，79公式，科目2231应付利息(贷方/负债)
- **Disclosure_SOE**: 附注披露信息（国有企业），34×5
- **Disclosure_Listed**: 附注披露信息（上市公司），34×16
- **Detail_L2_2**: 明细表L2-2，37×27，17公式，按借款/债券列示应付利息
- **Adjustment_L2_3**: 应付利息调整分录汇总L2-3
- **Interest_Check_L2_4**: 应付利息检查表L2-4
- **Cross_Sheet_Engine**: 跨sheet引擎 + L1/L3/L8联动
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Accrual_Engine**: 利息计提核对引擎（接收L1/L3测算，纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目2231）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L2应付利息底稿按sheetName分发, so that 8个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L2 组件 SHALL 注册新componentType: `l2-interest-payable`，主入口为 GtL2InterestPayable.vue
2. THE GtL2InterestPayable.vue SHALL 接收 `sheetName` prop，正则提取编码(L2-1)，v-if分发
3. THE L2 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L2 组件 SHALL 拆为：l2/core/（审定+明细+调整+附注）、l2/inspection/（检查表）
5. THE L2 组件 SHALL composable分层：useL2FormData + useL2FormulaEngine + useL2AccrualEngine(纯函数) + useL2CrossSheet + useL2DualMode + useL2ImportExport
6. THE L2 组件 SHALL 在htmlRendererRegistry中注册'l2-interest-payable'
7. THE L2 组件 SHALL 在wp_code_overrides.json中将L2/L2-1~L2-4/L2A映射为'l2-interest-payable'
8. THE L2 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l2-interest-payable'
9. THE GtL2InterestPayable.vue SHALL 支持selfLoad
10. THE L2 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L2-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L2-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看应付利息数据, so that 我能验证负债类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_L2_1 SHALL 渲染为单区块：应付利息(贷方/负债，按借款来源：短期借款/长期借款/应付债券分类+小计)
2. THE Adjudication_L2_1 SHALL 显示列：项目 | 期初 | 贷方发生(计提) | 借方发生(支付) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**
5. THE Adjudication_L2_1 SHALL 与L2-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2231)+发布'substantive:adjudicated'
7. THE Adjudication_L2_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表L2-2（按借款/债券列示）

**User Story:** As a 审计助理, I want to 管理应付利息明细, so that 每笔利息可追溯到借款来源。

#### Acceptance Criteria

1. THE Detail_L2_2 SHALL 显示列：借款/债券来源 | 本金 | 年利率 | 计息期间 | 期初应付 | 本期计提 | 本期支付 | 期末应付
2. THE Detail_L2_2 SHALL 自动计算：期末应付=期初+本期计提-本期支付（负债类）
3. THE Detail_L2_2 SHALL 27列宽表拆分：按来源信息/计提金额/支付情况区段Tab（行同步）
4. THE Detail_L2_2 SHALL 支持动态行新增+导入导出
5. THE Detail_L2_2 SHALL 与L2-1审定表交叉验证

### Requirement 4: 利息计提核对（接收L1/L3联动）

**User Story:** As a 审计助理, I want to 核对应付利息计提与L1/L3利息测算, so that 计提准确性得到验证。

#### Acceptance Criteria

1. THE Accrual_Engine SHALL 接收L1短期借款利息测算（订阅'l1:interest-calculated'）
2. THE Accrual_Engine SHALL 接收L3长期借款利息测算（订阅'l3:interest-calculated'）
3. THE L2 SHALL 在明细/检查表显示：来源利息测算 | 账面计提 | 差异
4. THE Accrual_Engine SHALL 计算计提差异=测算利息-账面计提
5. WHEN |计提差异|>阈值时 SHALL 红色高亮
6. THE L2 SHALL 通过cross_wp_references关联L1、L3、L8

### Requirement 5: 检查表L2-4 + 调整分录L2-3 + 附注

**User Story:** As a 审计助理, I want to 完成应付利息检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Interest_Check_L2_4 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Interest_Check_L2_4 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_L2_3 SHALL 借贷平衡校验+EventBus+双向同步L2-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 计提核对引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现利息计提核对纯函数引擎并集成标准能力, so that 计提差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Accrual_Engine SHALL calcAccrualDiff(estimated, booked): 差异=测算-账面
2. THE Accrual_Engine SHALL aggregateBySource(details): 按来源汇总应付利息
3. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit)=begin+credit-debit
4. THE L2 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
5. THE L2 SHALL 支持导入导出三级（useL2ImportExport，http带Authorization）
6. THE L2 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
