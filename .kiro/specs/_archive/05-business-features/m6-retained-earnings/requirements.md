# Requirements Document: M6 未分配利润底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **利润分配结转核心（接收本年利润+分配盈余公积M5+分配股利M1）** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM6ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M6未分配利润底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m6-retained-earnings`，覆盖来自 `M6 未分配利润.xlsx` 的9个有效sheet（含1个Q6A修订前sheet跳过）。科目覆盖4104利润分配-未分配利润（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M6核心特殊（利润分配结转核心！）**：①**贷方权益类科目**（期末=期初+贷方-借方）②**利润分配结转公式链核心**：期末未分配利润=期初未分配利润+本年净利润-提取盈余公积(M5)-应付股利(M1)③**上游接收本年利润，下游驱动M5盈余公积计提+M1股利分配**，是M股东权益循环的枢纽。关键公式总数约80+（审定表33公式 + 明细M6-2 13公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M6A**: 未分配利润实质性程序表M6A（复用a-program-console）
- **Adjudication_M6_1**: 审定表M6-1，47×12，33公式，科目4104利润分配-未分配利润(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），30×19
- **Disclosure_SOE**: 附注披露信息（国有企业），19×18
- **Detail_M6_2**: 明细表M6-2，32×19，13公式，利润分配结转明细
- **Adjustment_M6_3**: 未分配利润调整分录汇总M6-3
- **Retained_Check_M6_4**: 未分配利润检查表M6-4
- **Cross_Sheet_Engine**: 跨sheet引擎 + M5/M1联动
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Distribution_Engine**: 利润分配结转引擎（纯函数，核心！）
- **Trial_Balance_Writeback**: 审定数回写（科目4104）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M6未分配利润底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M6 组件 SHALL 注册新componentType: `m6-retained-earnings`，主入口为 GtM6RetainedEarnings.vue
2. THE GtM6RetainedEarnings.vue SHALL 接收 `sheetName` prop，正则提取编码(M6-1)，v-if分发
3. THE M6 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M6 组件 SHALL 拆为：m6/core/（审定+明细+调整+附注）、m6/inspection/（检查表）
5. THE M6 组件 SHALL composable分层：useM6FormData + useM6FormulaEngine + useM6DistributionEngine(纯函数) + useM6CrossSheet + useM6DualMode + useM6ImportExport
6. THE M6 组件 SHALL 在htmlRendererRegistry中注册'm6-retained-earnings'
7. THE M6 组件 SHALL 在wp_code_overrides.json中将M6/M6-1~M6-4/M6A映射为'm6-retained-earnings'
8. THE M6 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm6-retained-earnings'
9. THE GtM6RetainedEarnings.vue SHALL 支持selfLoad
10. THE M6 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M6-{sheet}-{field}"
11. THE 未迁移sheet及Q6A修订前sheet SHALL 走 OnlyOffice fallback或跳过

### Requirement 2: 审定表M6-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看未分配利润数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M6_1 SHALL 渲染为单区块：利润分配-未分配利润(贷方/权益)
2. THE Adjudication_M6_1 SHALL 显示列：项目 | 期初 | 贷方发生(净利润转入) | 借方发生(分配) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**
5. THE Adjudication_M6_1 SHALL 与M6-2明细结转合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4104)+发布'substantive:adjudicated'
7. THE Adjudication_M6_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M6-2（利润分配结转核心公式链！）

**User Story:** As a 审计助理, I want to 完整呈现利润分配结转过程, so that 期末未分配利润的形成可逐项追溯。

#### Acceptance Criteria

1. THE Detail_M6_2 SHALL 按利润分配顺序列示：期初未分配利润 | +本年净利润 | -提取法定盈余公积 | -提取任意盈余公积 | -应付普通股股利 | =期末未分配利润
2. THE Distribution_Engine SHALL 计算**期末未分配利润=期初+本年净利润-提取盈余公积-分配股利**（核心公式链！）
3. THE Detail_M6_2 SHALL 显示前期差错更正/会计政策变更调整行（调整年初）
4. THE Detail_M6_2 SHALL 13公式全部前端实时计算并逐行勾稽
5. THE Detail_M6_2 SHALL 与M6-1审定表交叉验证
6. THE Detail_M6_2 SHALL 支持动态行新增+导入导出

### Requirement 4: 跨底稿联动（M5盈余公积计提 + M1股利分配）

**User Story:** As a 审计助理, I want to 未分配利润与盈余公积计提、股利分配联动, so that 利润分配全链一致。

#### Acceptance Criteria

1. THE M6 SHALL 向M5发布本年净利润/计提基数（publish 'm6:net-profit'）
2. THE M6 SHALL 向M1发布分配股利（publish 'm6:profit-distributed'）
3. THE M6 SHALL 接收M5实际提取盈余公积（订阅'm5:accrual-confirmed'）核对
4. THE M6 SHALL 接收M1实际宣告股利（订阅'm1:declared-confirmed'）核对
5. THE Distribution_Engine SHALL 校验M6分配的盈余公积=M5计提、M6分配的股利=M1宣告
6. WHEN 联动差异>阈值时 SHALL 红色高亮
7. THE M6 SHALL 通过cross_wp_references关联M5、M1、A(本年利润/净利润来源)

### Requirement 5: 检查表M6-4 + 调整分录M6-3 + 附注

**User Story:** As a 审计助理, I want to 完成未分配利润检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Retained_Check_M6_4 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Retained_Check_M6_4 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_M6_3 SHALL 借贷平衡校验+EventBus+双向同步M6-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 分配结转引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现利润分配结转纯函数引擎并集成标准能力, so that 结转公式链可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Distribution_Engine SHALL calcRetainedEnd(begin, netProfit, surplusAccrual, dividend)=begin+netProfit-surplusAccrual-dividend
2. THE Distribution_Engine SHALL calcDistributable(begin, netProfit)=begin+netProfit（可供分配利润）
3. THE Distribution_Engine SHALL calcLinkageDiff(m6Value, sourceValue)=m6Value-sourceValue
4. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
5. THE M6 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M6 SHALL 支持导入导出三级（useM6ImportExport，http带Authorization）
7. THE M6 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
