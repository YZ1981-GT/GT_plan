# Requirements Document: M7 专项储备底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **安全生产费计提测试（按产量/收入）+ 使用核对** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM7ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M7专项储备底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m7-special-reserve`，覆盖来自 `M7 专项储备.xlsx` 的9个有效sheet。科目覆盖4201专项储备（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M7核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方，计提在贷方增加，使用在借方减少）②**安全生产费计提测试**（高危行业按产量/营业收入分档计提）③**专项储备支出检查**（资本性支出转固定资产 vs 费用性支出直接冲减）。关键公式总数约90+（审定表66公式 + 明细M7-2 22公式 + 计提测试M7-4 9公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M7A**: 专项储备实质性程序表M7A（复用a-program-console）
- **Adjudication_M7_1**: 审定表M7-1，32×12，66公式，科目4201专项储备(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），11×7
- **Disclosure_SOE**: 附注披露信息（国有企业），13×7
- **Detail_M7_2**: 明细表M7-2，24×27，22公式，专项储备计提+使用明细
- **Adjustment_M7_3**: 专项储备调整分录汇总M7-3
- **Accrual_Test_M7_4**: 专项储备计提测试表M7-4，37×19，9公式，安全生产费计提测试
- **Expenditure_Check_M7_5**: 专项储备支出检查表M7-5
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Accrual_Engine**: 安全生产费计提引擎（纯函数，按产量/收入）
- **Trial_Balance_Writeback**: 审定数回写（科目4201）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M7专项储备底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M7 组件 SHALL 注册新componentType: `m7-special-reserve`，主入口为 GtM7SpecialReserve.vue
2. THE GtM7SpecialReserve.vue SHALL 接收 `sheetName` prop，正则提取编码(M7-1)，v-if分发
3. THE M7 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M7 组件 SHALL 拆为：m7/core/（审定+明细+调整+附注）、m7/calc/（计提测试）、m7/inspection/（支出检查）
5. THE M7 组件 SHALL composable分层：useM7FormData + useM7FormulaEngine + useM7AccrualEngine(纯函数) + useM7CrossSheet + useM7DualMode + useM7ImportExport
6. THE M7 组件 SHALL 在htmlRendererRegistry中注册'm7-special-reserve'
7. THE M7 组件 SHALL 在wp_code_overrides.json中将M7/M7-1~M7-5/M7A映射为'm7-special-reserve'
8. THE M7 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm7-special-reserve'
9. THE GtM7SpecialReserve.vue SHALL 支持selfLoad
10. THE M7 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M7-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M7-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看专项储备数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M7_1 SHALL 渲染为单区块：专项储备(贷方/权益，按类别分类+小计)
2. THE Adjudication_M7_1 SHALL 显示列：项目 | 期初 | 贷方发生(计提) | 借方发生(使用) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**（计提在贷方，使用在借方）
5. THE Adjudication_M7_1 SHALL 与M7-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4201)+发布'substantive:adjudicated'
7. THE Adjudication_M7_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M7-2（计提+使用明细）

**User Story:** As a 审计助理, I want to 管理专项储备计提与使用明细, so that 每笔变动可追溯。

#### Acceptance Criteria

1. THE Detail_M7_2 SHALL 显示列：项目 | 期初 | 本期计提 | 本期使用(费用化) | 本期使用(资本化) | 期末
2. THE Detail_M7_2 SHALL 自动计算：期末=期初+本期计提-本期使用（权益类）；22公式实时计算
3. THE Detail_M7_2 SHALL 27列宽表拆分：按计提/费用化使用/资本化使用区段Tab（行同步）
4. THE Detail_M7_2 SHALL 支持动态行新增+导入导出
5. THE Detail_M7_2 SHALL 与M7-1审定表交叉验证

### Requirement 4: 专项储备计提测试表M7-4（安全生产费按产量/收入）

**User Story:** As a 审计助理, I want to 测试安全生产费计提是否合规, so that 计提准确性得到验证。

#### Acceptance Criteria

1. THE Accrual_Test_M7_4 SHALL 显示列：计提基础(产量/营业收入) | 计提标准(分档) | 应计提 | 账面计提 | 差异
2. THE Accrual_Engine SHALL 支持按产量计提：应计提=Σ(各档产量×档位标准)
3. THE Accrual_Engine SHALL 支持按营业收入计提：应计提=营业收入×计提比例
4. THE Accrual_Engine SHALL 计算计提差异=应计提-账面计提
5. WHEN |计提差异|>阈值时 SHALL 红色高亮
6. THE Accrual_Test_M7_4 SHALL 9公式全部前端实时计算

### Requirement 5: 专项储备支出检查表M7-5

**User Story:** As a 审计助理, I want to 检查专项储备支出的会计处理, so that 资本化/费用化处理合规。

#### Acceptance Criteria

1. THE Expenditure_Check_M7_5 SHALL 区分：费用性支出(直接冲减专项储备) vs 资本性支出(形成固定资产同时冲减专项储备计入累计折旧特殊科目)
2. THE Expenditure_Check_M7_5 SHALL 提供核对清单+审计结论区（el-card包裹）
3. THE Expenditure_Check_M7_5 SHALL 每个文本section标题行右侧放AI辅助按钮

### Requirement 6: 调整分录M7-3 + 附注

**User Story:** As a 审计助理, I want to 管理调整分录并生成附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_M7_3 SHALL 借贷平衡校验+EventBus+双向同步M7-1
2. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 7: 计提引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现安全生产费计提纯函数引擎并集成标准能力, so that 计提差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Accrual_Engine SHALL calcAccrualByOutput(tiers): 分档产量×标准求和
2. THE Accrual_Engine SHALL calcAccrualByRevenue(revenue, rate)=revenue×rate
3. THE Accrual_Engine SHALL calcAccrualDiff(estimated, booked)=estimated-booked
4. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
5. THE M7 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M7 SHALL 支持导入导出三级（useM7ImportExport，http带Authorization）
7. THE M7 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
