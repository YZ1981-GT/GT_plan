# Requirements Document: M1 应付股利（利润）底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **接收M6利润分配（分配股利）+ 外币汇率测算** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM1ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M1应付股利（利润）底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m1-dividends-payable`，覆盖来自 `M1 应付股利（利润）.xlsx` 的10个有效sheet。科目覆盖2232应付股利（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M1核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方，宣告分配在贷方增加，实际支付在借方减少）②**外币汇率测算**（对外币股东应付股利按汇率折算）③**股利测算**（接收M6利润分配的分配股利联动，验证应付股利宣告准确性）。关键公式总数约100+（M1-4外币汇率13公式 + M1-5股利测算13公式 + 审定表73公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M1**: 应付股利实质性程序表M1（复用a-program-console）
- **Adjudication_M1_1**: 审定表M1-1，56×12，73公式，科目2232应付股利(贷方/负债)
- **Disclosure_Listed**: 附注披露信息（上市公司），20×17
- **Disclosure_SOE**: 附注披露信息（国有企业），16×8
- **Detail_M1_2**: 明细表M1-2，38×27，7公式，按股东列示应付股利
- **Adjustment_M1_3**: 应付股利调整分录汇总M1-3
- **FX_Rate_M1_4**: 外币汇率测算表M1-4，25×7，13公式，外币应付股利折算
- **Dividend_Calc_M1_5**: 应付股利(利润)测算表M1-5，29×14，13公式，宣告股利测算
- **Dividend_Check_M1_6**: 应付股利(利润)检查表M1-6
- **Cross_Sheet_Engine**: 跨sheet引擎 + M6联动
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **FX_Engine**: 外币汇率折算引擎（纯函数）
- **Dividend_Engine**: 股利测算引擎（纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目2232）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M1应付股利底稿按sheetName分发, so that 10个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M1 组件 SHALL 注册新componentType: `m1-dividends-payable`，主入口为 GtM1DividendsPayable.vue
2. THE GtM1DividendsPayable.vue SHALL 接收 `sheetName` prop，正则提取编码(M1-1)，v-if分发
3. THE M1 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M1 组件 SHALL 拆为：m1/core/（审定+明细+调整+附注）、m1/calc/（外币汇率+股利测算）、m1/inspection/（检查表）
5. THE M1 组件 SHALL composable分层：useM1FormData + useM1FormulaEngine + useM1FxEngine(纯函数) + useM1DividendEngine(纯函数) + useM1CrossSheet + useM1DualMode + useM1ImportExport
6. THE M1 组件 SHALL 在htmlRendererRegistry中注册'm1-dividends-payable'
7. THE M1 组件 SHALL 在wp_code_overrides.json中将M1/M1-1~M1-6映射为'm1-dividends-payable'
8. THE M1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm1-dividends-payable'
9. THE GtM1DividendsPayable.vue SHALL 支持selfLoad
10. THE M1 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M1-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M1-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看应付股利数据, so that 我能验证负债类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M1_1 SHALL 渲染为单区块：应付股利(贷方/负债，按股东分类+小计)
2. THE Adjudication_M1_1 SHALL 显示列：项目 | 期初 | 贷方发生(宣告) | 借方发生(支付) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**（宣告在贷方，支付在借方）
5. THE Adjudication_M1_1 SHALL 与M1-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2232)+发布'substantive:adjudicated'
7. THE Adjudication_M1_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M1-2（按股东列示）

**User Story:** As a 审计助理, I want to 管理应付股利明细, so that 每笔股利可追溯到股东。

#### Acceptance Criteria

1. THE Detail_M1_2 SHALL 显示列：股东名称 | 持股比例 | 期初应付 | 本期宣告 | 本期支付 | 期末应付 | 币种
2. THE Detail_M1_2 SHALL 自动计算：期末应付=期初+本期宣告-本期支付（负债类）
3. THE Detail_M1_2 SHALL 27列宽表拆分：按股东信息/宣告金额/支付情况区段Tab（行同步）
4. THE Detail_M1_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入股东名）+导入导出
5. THE Detail_M1_2 SHALL 与M1-1审定表交叉验证

### Requirement 4: 外币汇率测算表M1-4（外币应付股利折算）

**User Story:** As a 审计助理, I want to 对外币股东应付股利按汇率折算, so that 期末外币余额折算准确。

#### Acceptance Criteria

1. THE FX_Rate_M1_4 SHALL 显示列：股东 | 原币金额 | 币种 | 期末汇率 | 折算本位币 | 账面本位币 | 汇兑差异
2. THE FX_Engine SHALL 计算折算本位币=原币金额×期末汇率
3. THE FX_Engine SHALL 计算汇兑差异=折算本位币-账面本位币
4. WHEN |汇兑差异|>阈值时 SHALL 红色高亮+提示调整
5. THE FX_Rate_M1_4 SHALL 13公式全部前端实时计算

### Requirement 5: 应付股利测算表M1-5（接收M6联动）

**User Story:** As a 审计助理, I want to 测算应宣告股利并核对账面, so that 应付股利宣告准确性得到验证。

#### Acceptance Criteria

1. THE Dividend_Calc_M1_5 SHALL 显示列：可供分配利润 | 分配比例 | 应宣告股利 | 账面宣告 | 差异
2. THE Dividend_Engine SHALL 接收M6利润分配的分配股利（订阅'm6:profit-distributed'）
3. THE Dividend_Engine SHALL 计算应宣告股利=可供分配利润×分配比例
4. THE Dividend_Engine SHALL 计算宣告差异=测算宣告-账面宣告
5. WHEN |宣告差异|>阈值时 SHALL 红色高亮
6. THE M1 SHALL 通过cross_wp_references关联M6

### Requirement 6: 检查表M1-6 + 调整分录M1-3 + 附注

**User Story:** As a 审计助理, I want to 完成应付股利检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Dividend_Check_M1_6 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Dividend_Check_M1_6 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_M1_3 SHALL 借贷平衡校验+EventBus+双向同步M1-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 7: 引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现外币折算+股利测算纯函数引擎并集成标准能力, so that 差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE FX_Engine SHALL calcFxConverted(amount, rate)=amount×rate
2. THE FX_Engine SHALL calcFxDiff(converted, booked)=converted-booked
3. THE Dividend_Engine SHALL calcDeclaredDividend(profit, ratio)=profit×ratio
4. THE Dividend_Engine SHALL calcDeclareDiff(estimated, booked)=estimated-booked
5. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, credit, debit)=begin+credit-debit
6. THE M1 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
7. THE M1 SHALL 支持导入导出三级（useM1ImportExport，http带Authorization）
8. THE M1 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
