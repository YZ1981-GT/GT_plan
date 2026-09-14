# Requirements Document: K2 其他流动资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格）。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K其他流动资产循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(1231) + 摊销测算联动
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK2ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K2其他流动资产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `k2-other-current-assets`，覆盖来自 `K2 其他流动资产.xlsx` 的10个有效sheet。科目覆盖1231其他流动资产（借方/资产类）。

**K2核心特殊**：①资产类三角勾稽（期末=期初+借方-贷方）②**合同取得成本明细**（CAS14下的合同取得成本资本化）③**摊销测算引擎**（按合同期直线摊销/按履约进度摊销）。审定表K2-1（85公式！密度极高）+ 合同成本K2-4（57公式）+ 摊销测算K2-5（37公式）。关键公式总数约200+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K2A**: 其他流动资产实质性程序表K2A（复用a-program-console）
- **Adjudication_K2_1**: 审定表K2-1，23行16列85公式，资产类1231审定
- **Disclosure_Listed**: 附注披露信息（上市公司），13行13列
- **Disclosure_SOE**: 附注披露信息（国企），13行13列
- **Detail_K2_2**: 明细表K2-2，30行18列17公式
- **Adjustment_K2_3**: 调整分录汇总K2-3
- **ContractCost_K2_4**: 合同取得成本明细表K2-4，32行23列57公式
- **Amortization_K2_5**: 摊销测算表K2-5，66行28列37公式
- **Check_K2_6**: 其他流动资产检查表K2-6
- **Amortization_Engine**: 摊销测算引擎（直线法/进度法）
- **Formula_Engine**: 前端公式引擎（资产类）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（1231）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K2其他流动资产按sheetName分发, so that 10个sheet有序组织。

#### Acceptance Criteria

1. THE K2 组件 SHALL 注册componentType: `k2-other-current-assets`，主入口GtK2OtherCurrentAssets.vue
2. THE GtK2OtherCurrentAssets.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K2 组件 SHALL defineAsyncComponent懒加载
4. THE K2 组件 SHALL 子目录：k2/core/（审定/明细/调整/附注） + k2/amortization/（合同成本/摊销测算） + k2/inspection/（检查表）
5. THE K2 组件 SHALL composable分层：useK2FormData + useK2FormulaEngine(纯函数) + useK2AmortizationEngine(纯函数) + useK2CrossSheet + useK2DualMode + useK2ImportExport
6. THE K2 组件 SHALL htmlRendererRegistry注册'k2-other-current-assets'
7. THE K2 组件 SHALL wp_code_overrides: K2/K2-1~K2-6/K2A → 'k2-other-current-assets'
8. THE K2 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K2 组件 SHALL selfLoad支持
10. THE K2 组件 SHALL checklist_responses存储，前缀"K2-{sheet}-{field}"

### Requirement 2: 审定表K2-1（85公式，资产类）

**User Story:** As a 审计助理, I want to 在审定表中查看其他流动资产, so that 我能验证各项余额正确。

#### Acceptance Criteria

1. THE Adjudication_K2_1 SHALL 显示：项目(合同取得成本/预付款项/待摊费用/其他)|期初|本期借方|本期贷方|期末|未审|AJE|RJE|审定数|变动率|备注
2. THE Formula_Engine SHALL 期末=期初+借方-贷方（资产类1231）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_K2_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_K2_1 SHALL 与K2-2明细/K2-4合同成本合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance(1231)+发布'substantive:adjudicated'
7. THE Adjudication_K2_1 SHALL 底部审计说明+结论+复核入口

### Requirement 3: 明细表K2-2（18列17公式）

**User Story:** As a 审计助理, I want to 管理其他流动资产明细, so that 各项目可逐项追踪。

#### Acceptance Criteria

1. THE Detail_K2_2 SHALL 将18列拆为2区段Tab：基础(序号/项目/性质/期初/期末) | 检查(增减原因/凭证号/核查结论/备注)
2. THE Formula_Engine SHALL 期末=期初+增加-减少，合计行联动审定表
3. THE Detail_K2_2 SHALL 动态行新增（ElMessageBox.prompt）+导入导出
4. THE Detail_K2_2 SHALL 底部统计：项目数/期末合计

### Requirement 4: 合同取得成本明细表K2-4（57公式）

**User Story:** As a 审计助理, I want to 管理合同取得成本, so that 资本化和摊销可追溯。

#### Acceptance Criteria

1. THE ContractCost_K2_4 SHALL 将23列拆为3区段Tab：合同(合同编号/客户/合同金额/取得成本类型/是否资本化) | 摊销(期初余额/本期增加/本期摊销/期末余额) | 检查(摊销方法/摊销期/凭证/结论)
2. THE Formula_Engine SHALL 期末余额=期初+增加-摊销
3. THE ContractCost_K2_4 SHALL 判断资本化条件（预期可收回+与合同直接相关+增量成本）
4. THE ContractCost_K2_4 SHALL 与K2-5摊销测算交叉验证（企业摊销 vs 测算摊销）
5. THE ContractCost_K2_4 SHALL 合计与K2-1审定合同取得成本一致
6. THE ContractCost_K2_4 SHALL 动态行+导入导出

### Requirement 5: 摊销测算表K2-5（37公式，摊销引擎）

**User Story:** As a 审计助理, I want to 测算合同取得成本摊销, so that 我能复核摊销金额合理性。

#### Acceptance Criteria

1. THE Amortization_K2_5 SHALL 将28列拆为区段Tab：基础(合同/取得成本/摊销方法/摊销期/起始日) | 测算(本期应摊销(公式)/累计摊销/摊余成本/企业摊销/差异(公式)/结论)
2. THE Amortization_Engine SHALL 直线法摊销=取得成本/摊销期总期数×本期期数
3. THE Amortization_Engine SHALL 进度法摊销=取得成本×(本期履约进度-上期履约进度)
4. THE Amortization_Engine SHALL 计算摊余成本=取得成本-累计摊销
5. THE Amortization_Engine SHALL 计算测算差异=测算摊销-企业摊销
6. WHEN 差异>重要性水平时 SHALL 红色标记提示调整
7. THE Amortization_K2_5 SHALL 66行虚拟滚动+底部合计

### Requirement 6: 其他流动资产检查表K2-6

**User Story:** As a 审计助理, I want to 执行检查, so that 分类正确性和可回收性获得关注。

#### Acceptance Criteria

1. THE Check_K2_6 SHALL 逐项检查：分类正确性/流动性判断(是否仍为流动)/可回收性/资本化合理性
2. THE Check_K2_6 SHALL 逐项"合规/不合规/不适用"+行级抽凭+行级OCR
3. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 7: 附注披露 + 调整分录

**User Story:** As a 审计助理, I want to 生成附注和管理调整分录, so that 披露完整、调整联动。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市13×13/国企13×13）+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K2_3 SHALL 借贷平衡+双向同步K2-1+publish 'adjustment:created'→A13+导入导出

### Requirement 8: 摊销引擎与公式引擎（纯函数）

**User Story:** As a 开发者, I want to 实现摊销与公式纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcAssetEndBalance(begin, debit, credit): 资产类期末=期初+借-贷
3. THE Amortization_Engine SHALL calcStraightLineAmort(cost, totalPeriods, currentPeriods): 直线法摊销
4. THE Amortization_Engine SHALL calcProgressAmort(cost, currentProgress, priorProgress): 进度法摊销
5. THE Amortization_Engine SHALL calcAmortizedBalance(cost, accumulated): 摊余成本=取得成本-累计摊销
6. THE Formula_Engine SHALL calcTriangleReconciliation(begin, inc, dec, end): 三角勾稽差额
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
