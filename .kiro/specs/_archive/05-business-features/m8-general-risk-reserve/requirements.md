# Requirements Document: M8 一般风险准备底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **一般风险准备按风险资产计提测试** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM8ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M8一般风险准备底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m8-general-risk-reserve`，覆盖来自 `M8 一般风险准备.xlsx` 的9个有效sheet（含1个Q8A修订前sheet+1个针对性测试删除sheet跳过）。科目覆盖4104一般风险准备（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M8核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方）②**金融企业专属**（行业守卫：金融/银行/证券/保险）③**按风险资产计提测试**（金融企业按风险资产期末余额1.5%等标准计提一般风险准备）。关键公式总数约80+（审定表72公式 + 明细M8-2 22公式 + 测试M8-4 13公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M8A**: 一般风险准备实质性程序表M8A（复用a-program-console）
- **Adjudication_M8_1**: 审定表M8-1，25×12，72公式，科目4104一般风险准备(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），11×14
- **Disclosure_SOE**: 附注披露信息（国有企业），11×14
- **Detail_M8_2**: 明细表M8-2，24×18，22公式，一般风险准备计提明细
- **Adjustment_M8_3**: 一般风险准备调整分录汇总M8-3
- **Risk_Test_M8_4**: 一般风险准备测试表M8-4，30×11，13公式，按风险资产计提测试
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Risk_Engine**: 风险资产计提引擎（纯函数）
- **Industry_Guard**: 行业守卫（金融企业）
- **Trial_Balance_Writeback**: 审定数回写（科目4104一般风险准备）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M8一般风险准备底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M8 组件 SHALL 注册新componentType: `m8-general-risk-reserve`，主入口为 GtM8GeneralRiskReserve.vue
2. THE GtM8GeneralRiskReserve.vue SHALL 接收 `sheetName` prop，正则提取编码(M8-1)，v-if分发
3. THE M8 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M8 组件 SHALL 拆为：m8/core/（审定+明细+调整+附注）、m8/calc/（风险测试）
5. THE M8 组件 SHALL composable分层：useM8FormData + useM8FormulaEngine + useM8RiskEngine(纯函数) + useM8CrossSheet + useM8DualMode + useM8ImportExport
6. THE M8 组件 SHALL 在htmlRendererRegistry中注册'm8-general-risk-reserve'
7. THE M8 组件 SHALL 在wp_code_overrides.json中将M8/M8-1~M8-4/M8A映射为'm8-general-risk-reserve'
8. THE M8 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm8-general-risk-reserve'
9. THE GtM8GeneralRiskReserve.vue SHALL 支持selfLoad + 行业守卫（金融企业适用性判断）
10. THE M8 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M8-{sheet}-{field}"
11. THE 未迁移sheet及Q8A修订前/针对性测试删除sheet SHALL 走 OnlyOffice fallback或跳过

### Requirement 2: 审定表M8-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看一般风险准备数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M8_1 SHALL 渲染为单区块：一般风险准备(贷方/权益)
2. THE Adjudication_M8_1 SHALL 显示列：项目 | 期初 | 贷方发生(计提) | 借方发生(转回/使用) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**
5. THE Adjudication_M8_1 SHALL 与M8-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4104一般风险准备)+发布'substantive:adjudicated'
7. THE Adjudication_M8_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M8-2 + 风险资产计提测试M8-4

**User Story:** As a 审计助理, I want to 管理一般风险准备明细并测试计提, so that 计提合规性得到验证。

#### Acceptance Criteria

1. THE Detail_M8_2 SHALL 显示列：项目 | 期初 | 本期计提 | 本期转回 | 期末（22公式实时计算）
2. THE Detail_M8_2 SHALL 自动计算：期末=期初+本期计提-本期转回（权益类）
3. THE Risk_Test_M8_4 SHALL 显示列：风险资产期末余额 | 计提比例(1.5%) | 应计提余额 | 账面余额 | 差异
4. THE Risk_Engine SHALL 计算应计提余额=风险资产期末余额×计提比例
5. THE Risk_Engine SHALL 计算计提差异=应计提余额-账面余额
6. WHEN |计提差异|>阈值时 SHALL 红色高亮
7. THE Risk_Test_M8_4 SHALL 13公式全部前端实时计算
8. THE Detail_M8_2 SHALL 支持动态行新增+导入导出

### Requirement 4: 调整分录M8-3 + 附注

**User Story:** As a 审计助理, I want to 管理调整分录并生成附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_M8_3 SHALL 借贷平衡校验+EventBus+双向同步M8-1
2. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新
4. THE 附注/检查区 SHALL 每个文本section标题行右侧放AI辅助按钮

### Requirement 5: 行业守卫（金融企业适用性）

**User Story:** As a 审计助理, I want to M8仅对金融企业适用, so that 非金融企业不误用。

#### Acceptance Criteria

1. THE Industry_Guard SHALL 判断企业行业属性（金融/银行/证券/保险）
2. WHEN 非金融企业 SHALL 显示"一般风险准备仅适用金融企业"提示并允许标记不适用
3. THE Industry_Guard SHALL 在底稿目录显示适用性状态

### Requirement 6: 风险引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现风险资产计提纯函数引擎并集成标准能力, so that 计提差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Risk_Engine SHALL calcRiskProvision(riskAssets, rate)=riskAssets×rate
2. THE Risk_Engine SHALL calcProvisionDiff(estimated, booked)=estimated-booked
3. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
4. THE Formula_Engine SHALL calcSubtotal(arr)=Σarr
5. THE M8 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M8 SHALL 支持导入导出三级（useM8ImportExport，http带Authorization）
7. THE M8 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
