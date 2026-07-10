# Requirements Document: N4 税金及附加底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/N税费循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **N2应交税费计提对应联动** + **A类利润表勾稽** + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 各税种统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级 + useN4ImportExport composable
- **AI辅助**：多section按区域AI + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

N4税金及附加底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `n4-taxes-and-surcharges`，覆盖来自 `N4 税金及附加.xlsx` 的9个sheet（其中O2A原底稿为辅助sheet标记skip）。科目覆盖6403税金及附加（**损益类科目**）。

**N4核心特殊**：①**损益类科目**！取本期发生额（从tb_ledger借方发生额，与H10资产处置损益、I6研发费用同款）②各税种费用确认：消费税/城建税/教育费附加/地方教育附加/房产税/土地使用税/车船税/印花税/资源税等 ③与N2应交税费计提对应（cross_wp_ref联动，费用确认=计提额）④与A类利润表勾稽。审定表83公式、明细表18公式。关键公式总数约110+。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_N4A**: 税金及附加审计程序表N4A，审计程序清单（复用a-program-console）
- **Adjudication_N4_1**: 审定表N4-1，24行14列83公式，损益类科目6403审定（各税种分行，取发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），18行12列
- **Disclosure_SOE**: 附注披露信息（国有企业），17行11列
- **Detail_N4_2**: 明细表N4-2，34行11列18公式，各税种发生额明细
- **Adjustment_N4_3**: 调整分录汇总N4-3，AJE/RJE管理
- **Multi_Tax_Engine**: 多税种测算引擎（各税种计税依据×税率，纯函数，与N2同源）
- **Formula_Engine**: 前端公式引擎composable（**损益类！发生额**）
- **Cross_Sheet_Engine**: 跨sheet引擎 + N2计提对应联动 + A利润表勾稽
- **Trial_Balance_Writeback**: 审定数回写（科目6403，本期发生额）
- **Skip_Sheet**: 辅助sheet标记skip（O2A原底稿）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to N4税金及附加底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE N4 组件 SHALL 注册新componentType: `n4-taxes-and-surcharges`，主入口为 GtN4TaxesAndSurcharges.vue
2. THE GtN4TaxesAndSurcharges.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(N4-1/N4-2等)，v-if分发到子组件
3. THE N4 组件 SHALL 使用 defineAsyncComponent 懒加载各子组件
4. THE N4 组件 SHALL 拆为：n4/core/（审定+明细+调整+附注）
5. THE N4 组件 SHALL composable分层：useN4FormData + useN4FormulaEngine(纯函数) + useN4MultiTaxEngine(纯函数) + useN4CrossSheet + useN4DualMode + useN4ImportExport
6. THE N4 组件 SHALL 在htmlRendererRegistry中注册'n4-taxes-and-surcharges'
7. THE N4 组件 SHALL 在wp_code_overrides.json中将N4/N4-1~N4-3/N4A映射为'n4-taxes-and-surcharges'
8. THE N4 组件 SHALL 在VALID_COMPONENT_TYPES中注册'n4-taxes-and-surcharges'
9. THE GtN4TaxesAndSurcharges.vue SHALL 支持selfLoad（bundle内嵌htmlData为null时自加载）
10. THE N4 组件 SHALL 使用 checklist_responses 存储，item_id前缀"N4-{sheet}-{field}"
11. THE O2A原底稿 SHALL 标记skip（走OnlyOffice fallback，不做HTML组件化）

### Requirement 2: 审定表N4-1（损益类！83公式，取发生额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看税金及附加, so that 我能验证各税种费用的审定发生额。

#### Acceptance Criteria

1. THE Adjudication_N4_1 SHALL 按税种分行（消费税/城建税/教育费附加/地方教育附加/房产税/土地使用税/车船税/印花税/资源税/其他）
2. THE Adjudication_N4_1 SHALL 显示列：税种 | 本期发生额 | 未审数 | AJE | RJE | 审定数 | 上期数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：取本期发生额（从tb_ledger借方发生额，而非期末余额）
5. THE Adjudication_N4_1 SHALL 与N4-2明细合计交叉验证
6. THE Adjudication_N4_1 SHALL 与N2应交税费各税种本期计提额交叉验证（费用确认=计提）
7. WHEN 审定数变化时 SHALL 回写trial_balance（科目6403，本期发生额）+发布'substantive:adjudicated'
8. THE Adjudication_N4_1 SHALL 在底部显示审计说明+结论+复核入口

### Requirement 3: 明细表N4-2（11列18公式，各税种发生额明细）

**User Story:** As a 审计助理, I want to 管理税金及附加明细, so that 各税种费用发生额可逐项核对。

#### Acceptance Criteria

1. THE Detail_N4_2 SHALL 显示列：序号/税种/计税依据/税率/本期发生额/上期发生额/同比变动/N2计提额/差异/核查结论
2. THE Multi_Tax_Engine SHALL 自动计算每行：本期发生额=计税依据×税率；同比变动=(本期-上期)/上期；差异=本期发生额-N2计提额
3. THE Detail_N4_2 SHALL 合计行与N4-1审定表交叉验证
4. THE Detail_N4_2 SHALL 支持动态行新增（ElMessageBox.prompt输入税种）+导入导出
5. THE Detail_N4_2 SHALL 对费用确认与N2计提额存在差异的行标记红色背景
6. THE Detail_N4_2 SHALL 在底部统计：税种数/发生额合计/同比变动率

### Requirement 4: 各税种计算（计税依据×税率，与N2同源）

**User Story:** As a 审计助理, I want to 测算各税种费用, so that 城建税/房产税/印花税等计算正确。

#### Acceptance Criteria

1. THE Multi_Tax_Engine SHALL 计算城建税及附加=(增值税+消费税)×税率(7%/5%/1%、3%、2%)
2. THE Multi_Tax_Engine SHALL 计算房产税从价=原值×(1-扣除比例)×1.2%；从租=租金×12%
3. THE Multi_Tax_Engine SHALL 计算印花税=计税金额×适用税率（按合同类型不同税率）
4. THE Multi_Tax_Engine SHALL 计算土地使用税=占地面积×单位税额
5. THE N4 SHALL 各税种计税依据取自N2应交税费测算结果（联动）

### Requirement 5: 调整分录N4-3 + 附注

**User Story:** As a 审计助理, I want to 录入调整分录并生成附注, so that 审计调整和披露有据可循。

#### Acceptance Criteria

1. THE Adjustment_N4_3 SHALL 借贷平衡校验 + EventBus发布'adjustment:created' + 双向同步N4-1
2. THE Disclosure_Listed/SOE SHALL 按上市(18×12)/国企(17×11)模板渲染税金及附加附注结构（各税种明细）
3. THE Disclosure SHALL subscribe 'substantive:adjudicated' 自动刷新 + publish 'disclosure:note-text-updated'
4. THE 附注 SHALL 展示各税种本期/上期发生额明细及同比变动说明

### Requirement 6: 跨底稿联动（N2计提对应+A利润表勾稽）

**User Story:** As a 审计助理, I want to N4税金及附加与N2计提正确联动, so that 费用确认与计提一致。

#### Acceptance Criteria

1. THE N4 SHALL subscribe 'tax-accrual:updated'（N2各税种计提额）并对费用确认交叉验证
2. THE N4 SHALL 提供GtIndexChip跳转：N4-1税金及附加项 ↔ N2-1应交税费对应税种行
3. THE N4 SHALL 与N2对城建税/教育费附加/房产税/土地使用税/印花税等计提额交叉验证（费用确认=计提额）
4. THE N4 SHALL publish 'expense:taxes-surcharges-updated' 供A类利润表勾稽
5. WHEN 费用确认与N2计提额不一致时 SHALL 红色差异提示

### Requirement 7: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类科目的取数和计算逻辑, so that N4不会错误地取期末余额（应取本期发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现损益类取数：取本期发生额（借方发生额），而非期末余额
2. THE TB取数 SHALL 从tb_ledger取本期发生额（损益类专用取数逻辑，与H10/I6同款）
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为本期发生额
4. THE Formula_Engine SHALL 区分：本期发生额（损益类用）vs 期末余额（资产/负债用），N4用本期发生额
