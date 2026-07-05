# Requirements Document: L7 其他非流动负债底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL7ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L7其他非流动负债底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l7-other-noncurrent-liabilities`，覆盖来自 `L7 其他非流动负债.xlsx` 的8个有效sheet。科目覆盖2801其他非流动负债（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L7核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方）②L筹资循环最简标准负债底稿，无复杂计算引擎，按项目列示+审定+调整+附注。关键公式总数约90+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L7A**: 其他非流动负债实质性程序表L7A（复用a-program-console）
- **Adjudication_L7_1**: 审定表L7-1，18×12，72公式，科目2801其他非流动负债(贷方/负债)
- **Disclosure_Listed**: 附注披露信息（上市公司），12×7
- **Disclosure_SOE**: 附注披露信息（国有企业），12×7
- **Detail_L7_2**: 明细表L7-2，25×27，12公式，按项目列示
- **Adjustment_L7_3**: 调整分录L7-3
- **Other_Check_L7_4**: 其他非流动负债检查表L7-4
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Trial_Balance_Writeback**: 审定数回写（科目2801）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L7其他非流动负债底稿按sheetName分发, so that 8个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L7 组件 SHALL 注册新componentType: `l7-other-noncurrent-liabilities`，主入口为 GtL7OtherNoncurrentLiabilities.vue
2. THE GtL7OtherNoncurrentLiabilities.vue SHALL 接收 `sheetName` prop，正则提取编码(L7-1)，v-if分发
3. THE L7 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L7 组件 SHALL 拆为：l7/core/（审定+明细+调整+附注）、l7/inspection/（检查表）
5. THE L7 组件 SHALL composable分层：useL7FormData + useL7FormulaEngine(纯函数) + useL7CrossSheet + useL7DualMode + useL7ImportExport
6. THE L7 组件 SHALL 在htmlRendererRegistry中注册'l7-other-noncurrent-liabilities'
7. THE L7 组件 SHALL 在wp_code_overrides.json中将L7/L7-1~L7-4/L7A映射为'l7-other-noncurrent-liabilities'
8. THE L7 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l7-other-noncurrent-liabilities'
9. THE GtL7OtherNoncurrentLiabilities.vue SHALL 支持selfLoad
10. THE L7 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L7-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L7-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看其他非流动负债数据, so that 我能验证负债类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_L7_1 SHALL 渲染为单区块：其他非流动负债(贷方/负债，按项目分类+小计)
2. THE Adjudication_L7_1 SHALL 显示列：项目 | 期初 | 贷方发生(增加) | 借方发生(减少) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**
5. THE Adjudication_L7_1 SHALL 与L7-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2801)+发布'substantive:adjudicated'
7. THE Adjudication_L7_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表L7-2（按项目列示）

**User Story:** As a 审计助理, I want to 管理其他非流动负债明细, so that 每个项目可追溯。

#### Acceptance Criteria

1. THE Detail_L7_2 SHALL 显示列：项目名称 | 性质 | 形成原因 | 期初 | 本期增加 | 本期减少 | 期末余额 | 到期情况
2. THE Detail_L7_2 SHALL 自动计算：期末余额=期初+本期增加-本期减少（负债类）
3. THE Detail_L7_2 SHALL 27列宽表拆分：项目信息/金额变动区段Tab（行同步）
4. THE Detail_L7_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入项目名称）+导入导出
5. THE Detail_L7_2 SHALL 与审定表L7-1交叉验证

### Requirement 4: 检查表L7-4 + 调整分录L7-3 + 附注

**User Story:** As a 审计助理, I want to 完成其他非流动负债检查并管理调整和附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Other_Check_L7_4 SHALL 提供核对清单+审计结论区（el-card包裹）+ AI辅助
2. THE Other_Check_L7_4 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_L7_3 SHALL 借贷平衡校验+EventBus+双向同步L7-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 5: 公式引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现负债类纯函数引擎并集成标准能力, so that 期末余额可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(u, a, r)=u+a+r
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit)=begin+credit-debit
3. THE Formula_Engine SHALL calcSubtotal(arr)=Σarr
4. THE L7 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
5. THE L7 SHALL 支持导入导出三级（useL7ImportExport，http带Authorization）
6. THE L7 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
