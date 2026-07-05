# Requirements Document: M9 其他综合收益底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **OCI核对（接收G8其他权益工具投资公允变动+J2重计量+外币折算）** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM9ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M9其他综合收益底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m9-other-comprehensive-income`，覆盖来自 `M9 其他综合收益.xlsx` 的9个有效sheet。科目覆盖4103其他综合收益（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M9核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方，OCI增加在贷方）②**OCI核对（核心！）**：其他综合收益汇聚多来源——G8其他权益工具投资公允价值变动、J2设定受益计划重计量、外币财务报表折算差额、现金流量套期损益等，需分"以后不能重分类"和"以后能重分类进损益"两大类核对③**税后净额列示**（OCI各项目按税前-所得税影响=税后净额）。关键公式总数约80+（审定表41公式 + 明细M9-2 34公式 + 核对表M9-4 13公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M9A**: 其他综合收益实质性程序表M9A（复用a-program-console）
- **Adjudication_M9_1**: 审定表M9-1，47×12，41公式，科目4103其他综合收益(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），30×18
- **Disclosure_SOE**: 附注披露信息（国有企业），67×21，20公式
- **Detail_M9_2**: 明细表M9-2，46×30，34公式，OCI分项明细（不可/可重分类）
- **Adjustment_M9_3**: 其他综合收益调整分录汇总M9-3
- **OCI_Reconcile_M9_4**: 其他综合收益核对表M9-4，42×9，13公式，多来源核对
- **Cross_Sheet_Engine**: 跨sheet引擎 + G8/J2联动
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **OCI_Engine**: OCI核对引擎（纯函数，税后净额+多来源汇聚）
- **Trial_Balance_Writeback**: 审定数回写（科目4103）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M9其他综合收益底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M9 组件 SHALL 注册新componentType: `m9-other-comprehensive-income`，主入口为 GtM9OtherComprehensiveIncome.vue
2. THE GtM9OtherComprehensiveIncome.vue SHALL 接收 `sheetName` prop，正则提取编码(M9-1)，v-if分发
3. THE M9 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M9 组件 SHALL 拆为：m9/core/（审定+明细+调整+附注）、m9/inspection/（核对表）
5. THE M9 组件 SHALL composable分层：useM9FormData + useM9FormulaEngine + useM9OciEngine(纯函数) + useM9CrossSheet + useM9DualMode + useM9ImportExport
6. THE M9 组件 SHALL 在htmlRendererRegistry中注册'm9-other-comprehensive-income'
7. THE M9 组件 SHALL 在wp_code_overrides.json中将M9/M9-1~M9-4/M9A映射为'm9-other-comprehensive-income'
8. THE M9 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm9-other-comprehensive-income'
9. THE GtM9OtherComprehensiveIncome.vue SHALL 支持selfLoad
10. THE M9 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M9-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M9-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看其他综合收益数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M9_1 SHALL 渲染为双区块：以后不能重分类进损益的OCI + 以后能重分类进损益的OCI
2. THE Adjudication_M9_1 SHALL 显示列：项目 | 期初 | 贷方发生(增加) | 借方发生(减少) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**
5. THE Adjudication_M9_1 SHALL 与M9-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4103)+发布'substantive:adjudicated'
7. THE Adjudication_M9_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M9-2（OCI分项+税后净额）

**User Story:** As a 审计助理, I want to 管理OCI分项明细并计算税后净额, so that 每个OCI项目可追溯到来源。

#### Acceptance Criteria

1. THE Detail_M9_2 SHALL 分两大类列示：
   - 不能重分类：其他权益工具投资公允变动(G8)、设定受益计划重计量(J2)
   - 能重分类：其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额
2. THE Detail_M9_2 SHALL 显示列：OCI项目 | 期初 | 本期税前发生 | 所得税影响 | 本期税后净额 | 期末
3. THE OCI_Engine SHALL 计算本期税后净额=本期税前发生-所得税影响
4. THE Detail_M9_2 SHALL 30列宽表拆分：按不可重分类/可重分类/税额区段Tab（行同步）
5. THE Detail_M9_2 SHALL 34公式全部前端实时计算
6. THE Detail_M9_2 SHALL 支持动态行新增+导入导出
7. THE Detail_M9_2 SHALL 与M9-1审定表交叉验证

### Requirement 4: OCI核对表M9-4（多来源核对，核心！）

**User Story:** As a 审计助理, I want to 核对OCI与各来源底稿一致性, so that OCI完整性、准确性得到验证。

#### Acceptance Criteria

1. THE OCI_Reconcile_M9_4 SHALL 显示各来源：来源底稿 | 来源金额(税后) | 账面OCI增加 | 差异
2. THE OCI_Engine SHALL 接收G8其他权益工具投资公允价值变动（订阅'g8:fair-value-changed'）
3. THE OCI_Engine SHALL 接收J2设定受益计划重计量（订阅'j2:remeasured'）
4. THE OCI_Engine SHALL 接收外币财务报表折算差额
5. THE OCI_Engine SHALL 计算核对差异=来源金额-账面OCI增加
6. WHEN |核对差异|>阈值时 SHALL 红色高亮
7. THE OCI_Reconcile_M9_4 SHALL 13公式全部前端实时计算
8. THE M9 SHALL 通过cross_wp_references关联G8、J2

### Requirement 5: 调整分录M9-3 + 附注

**User Story:** As a 审计助理, I want to 管理调整分录并生成附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_M9_3 SHALL 借贷平衡校验+EventBus+双向同步M9-1
2. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板（国企版67×21含20公式）
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新
4. THE 核对表/附注 SHALL 每个文本section标题行右侧放AI辅助按钮

### Requirement 6: OCI引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现OCI核对纯函数引擎并集成标准能力, so that 税后净额与核对差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE OCI_Engine SHALL calcAfterTaxNet(preTax, taxEffect)=preTax-taxEffect
2. THE OCI_Engine SHALL calcReconcileDiff(source, booked)=source-booked
3. THE OCI_Engine SHALL aggregateOci(items): 不可重分类+可重分类汇总
4. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
5. THE M9 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M9 SHALL 支持导入导出三级（useM9ImportExport，http带Authorization）
7. THE M9 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
