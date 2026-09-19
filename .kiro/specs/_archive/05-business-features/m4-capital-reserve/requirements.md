# Requirements Document: M4 资本公积底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **接收J3股份支付权益结算 + 接收M2外币出资折算差异** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM4ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M4资本公积底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m4-capital-reserve`，覆盖来自 `M4 资本公积.xlsx` 的9个有效sheet。科目覆盖4002资本公积（**贷方/权益类！**，注：与库存股同为4002科目但资本公积为贷方权益）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M4核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方）②**资本溢价+其他资本公积双明细结构**（资本溢价/股本溢价 + 其他资本公积）③**接收J3股份支付权益结算**（等待期确认的股份支付计入其他资本公积）。关键公式总数约90+（审定表41公式 + 明细表31公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M4A**: 资本公积实质性程序表M4A（复用a-program-console）
- **Adjudication_M4_1**: 审定表M4-1，44×12，41公式，科目4002资本公积(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），16×15
- **Disclosure_SOE**: 附注披露信息（国有企业），13×15
- **Detail_M4_2**: 明细表M4-2，50×24，31公式，资本溢价+其他资本公积明细
- **Adjustment_M4_3**: 资本公积调整分录汇总M4-3
- **Reserve_Check_M4_4**: 资本公积检查表M4-4
- **Cross_Sheet_Engine**: 跨sheet引擎 + J3/M2联动
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Reserve_Engine**: 资本公积变动引擎（纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目4002资本公积）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M4资本公积底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M4 组件 SHALL 注册新componentType: `m4-capital-reserve`，主入口为 GtM4CapitalReserve.vue
2. THE GtM4CapitalReserve.vue SHALL 接收 `sheetName` prop，正则提取编码(M4-1)，v-if分发
3. THE M4 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M4 组件 SHALL 拆为：m4/core/（审定+明细+调整+附注）、m4/inspection/（检查表）
5. THE M4 组件 SHALL composable分层：useM4FormData + useM4FormulaEngine + useM4ReserveEngine(纯函数) + useM4CrossSheet + useM4DualMode + useM4ImportExport
6. THE M4 组件 SHALL 在htmlRendererRegistry中注册'm4-capital-reserve'
7. THE M4 组件 SHALL 在wp_code_overrides.json中将M4/M4-1~M4-4/M4A映射为'm4-capital-reserve'
8. THE M4 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm4-capital-reserve'
9. THE GtM4CapitalReserve.vue SHALL 支持selfLoad
10. THE M4 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M4-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M4-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看资本公积数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M4_1 SHALL 渲染为双区块：资本溢价(股本溢价) + 其他资本公积
2. THE Adjudication_M4_1 SHALL 显示列：项目 | 期初 | 贷方发生(增加) | 借方发生(减少) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**
5. THE Adjudication_M4_1 SHALL 与M4-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4002资本公积)+发布'substantive:adjudicated'
7. THE Adjudication_M4_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M4-2（资本溢价+其他资本公积）

**User Story:** As a 审计助理, I want to 管理资本公积明细, so that 溢价与其他资本公积可分类追溯。

#### Acceptance Criteria

1. THE Detail_M4_2 SHALL 分两区段：资本溢价明细（出资超面值部分）+ 其他资本公积明细
2. THE Detail_M4_2 SHALL 显示列：来源项目 | 期初 | 本期增加 | 本期减少 | 期末 | 变动原因
3. THE Detail_M4_2 SHALL 自动计算：期末=期初+本期增加-本期减少（权益类）；31公式实时计算
4. THE Detail_M4_2 SHALL 24列宽表拆分：按资本溢价/其他资本公积区段Tab（行同步）
5. THE Detail_M4_2 SHALL 支持动态行新增+导入导出
6. THE Detail_M4_2 SHALL 与M4-1审定表交叉验证

### Requirement 4: J3股份支付权益结算联动

**User Story:** As a 审计助理, I want to 核对J3股份支付权益结算计入其他资本公积, so that 股份支付确认准确。

#### Acceptance Criteria

1. THE Reserve_Engine SHALL 接收J3股份支付权益结算金额（订阅'j3:equity-settled'）
2. THE M4 SHALL 在明细/检查表显示：J3等待期确认金额 | 账面其他资本公积增加 | 差异
3. THE Reserve_Engine SHALL 计算股份支付确认差异=J3确认金额-账面增加
4. WHEN |确认差异|>阈值时 SHALL 红色高亮
5. THE M4 SHALL 接收M2外币出资折算差异（订阅'm2:fx-diff'）计入资本溢价
6. THE M4 SHALL 通过cross_wp_references关联J3、M2

### Requirement 5: 检查表M4-4 + 调整分录M4-3 + 附注

**User Story:** As a 审计助理, I want to 完成资本公积检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Reserve_Check_M4_4 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Reserve_Check_M4_4 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_M4_3 SHALL 借贷平衡校验+EventBus+双向同步M4-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 变动引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现资本公积变动纯函数引擎并集成标准能力, so that 差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Reserve_Engine SHALL calcShareBasedDiff(j3Amount, booked)=j3Amount-booked
2. THE Reserve_Engine SHALL aggregateReserve(details): 资本溢价+其他资本公积汇总
3. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
4. THE M4 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
5. THE M4 SHALL 支持导入导出三级（useM4ImportExport，http带Authorization）
6. THE M4 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
