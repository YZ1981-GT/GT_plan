# Requirements Document: M5 盈余公积底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **接收M6未分配利润(计提基数) + 联动M1股利分配** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM5ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M5盈余公积底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m5-surplus-reserve`，覆盖来自 `M5 盈余公积.xlsx` 的10个有效sheet。科目覆盖4101盈余公积（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M5核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方）②**法定盈余公积计提测试**（按净利润10%计提，达注册资本50%可不再计提）+ 任意盈余公积③**接收M6未分配利润作为计提基数**，任意盈余公积计提联动M6。关键公式总数约80+（审定表57公式 + 计提检查M5-4 11公式 + 明细M5-2 12公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M5A**: 盈余公积实质性程序表M5A（复用a-program-console）
- **Adjudication_M5_1**: 审定表M5-1，48×12，57公式，科目4101盈余公积(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），12×16
- **Disclosure_SOE**: 附注披露信息（国有企业），12×16
- **Detail_M5_2**: 明细表M5-2，38×17，12公式，法定+任意盈余公积明细
- **Adjustment_M5_3**: 盈余公积调整分录汇总M5-3
- **Accrual_Test_M5_4**: 盈余公积计提检查表M5-4，42×9，11公式，法定10%计提测试
- **Reserve_Check_M5_5**: 盈余公积检查表M5-5
- **Cross_Sheet_Engine**: 跨sheet引擎 + M6/M1联动
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Accrual_Engine**: 盈余公积计提引擎（纯函数，法定10%）
- **Trial_Balance_Writeback**: 审定数回写（科目4101）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M5盈余公积底稿按sheetName分发, so that 10个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M5 组件 SHALL 注册新componentType: `m5-surplus-reserve`，主入口为 GtM5SurplusReserve.vue
2. THE GtM5SurplusReserve.vue SHALL 接收 `sheetName` prop，正则提取编码(M5-1)，v-if分发
3. THE M5 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M5 组件 SHALL 拆为：m5/core/（审定+明细+调整+附注）、m5/calc/（计提测试）、m5/inspection/（检查表）
5. THE M5 组件 SHALL composable分层：useM5FormData + useM5FormulaEngine + useM5AccrualEngine(纯函数) + useM5CrossSheet + useM5DualMode + useM5ImportExport
6. THE M5 组件 SHALL 在htmlRendererRegistry中注册'm5-surplus-reserve'
7. THE M5 组件 SHALL 在wp_code_overrides.json中将M5/M5-1~M5-5/M5A映射为'm5-surplus-reserve'
8. THE M5 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm5-surplus-reserve'
9. THE GtM5SurplusReserve.vue SHALL 支持selfLoad
10. THE M5 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M5-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M5-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看盈余公积数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M5_1 SHALL 渲染为双区块：法定盈余公积 + 任意盈余公积
2. THE Adjudication_M5_1 SHALL 显示列：项目 | 期初 | 贷方发生(计提) | 借方发生(转增/弥补) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**
5. THE Adjudication_M5_1 SHALL 与M5-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4101)+发布'substantive:adjudicated'
7. THE Adjudication_M5_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M5-2（法定+任意盈余公积）

**User Story:** As a 审计助理, I want to 管理盈余公积明细, so that 法定与任意盈余公积可分类追溯。

#### Acceptance Criteria

1. THE Detail_M5_2 SHALL 分两区段：法定盈余公积明细 + 任意盈余公积明细
2. THE Detail_M5_2 SHALL 显示列：项目 | 期初 | 本期计提 | 本期转增资本 | 本期弥补亏损 | 期末
3. THE Detail_M5_2 SHALL 自动计算：期末=期初+本期计提-本期转增-本期弥补（权益类）；12公式实时计算
4. THE Detail_M5_2 SHALL 支持动态行新增+导入导出
5. THE Detail_M5_2 SHALL 与M5-1审定表交叉验证

### Requirement 4: 盈余公积计提检查表M5-4（法定10%计提测试）

**User Story:** As a 审计助理, I want to 测试法定盈余公积计提是否合规, so that 计提准确性、合规性得到验证。

#### Acceptance Criteria

1. THE Accrual_Test_M5_4 SHALL 显示列：净利润 | 弥补以前年度亏损 | 计提基数 | 法定计提比例(10%) | 应计提 | 账面计提 | 差异
2. THE Accrual_Engine SHALL 接收M6未分配利润的净利润/计提基数（订阅'm6:net-profit'）
3. THE Accrual_Engine SHALL 计算应计提法定盈余公积=计提基数×10%
4. THE Accrual_Engine SHALL 校验累计法定盈余公积达注册资本50%时可不再计提
5. THE Accrual_Engine SHALL 计算计提差异=应计提-账面计提
6. WHEN |计提差异|>阈值时 SHALL 红色高亮
7. THE Accrual_Test_M5_4 SHALL 11公式全部前端实时计算

### Requirement 5: 检查表M5-5 + 调整分录M5-3 + 附注

**User Story:** As a 审计助理, I want to 完成盈余公积检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Reserve_Check_M5_5 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Reserve_Check_M5_5 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_M5_3 SHALL 借贷平衡校验+EventBus+双向同步M5-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 计提引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现盈余公积计提纯函数引擎并集成标准能力, so that 计提差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Accrual_Engine SHALL calcStatutoryAccrual(base, rate=0.1)=base×rate
2. THE Accrual_Engine SHALL calcAccrualDiff(estimated, booked)=estimated-booked
3. THE Accrual_Engine SHALL isAccrualCeilingReached(accumulated, registeredCapital): 累计≥注册资本50%
4. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
5. THE M5 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M5 SHALL 支持导入导出三级（useM5ImportExport，http带Authorization）
7. THE M5 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
