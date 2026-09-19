# Requirements Document: K11 资产减值损失底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K资产减值损失循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(6701发生额) + 汇总联动F2/H1/I1/I3各资产减值
- **美观性**：分组配色 + 减值来源汇总仪表板
- **跳转溯源**：GtIndexChip跳转各减值来源底稿 + tooltip + 公式列虚线
- **易操作**：编制提示
- **导入导出**：el-dropdown三级 + useK11ImportExport
- **AI辅助**：审计说明生成
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K11资产减值损失底稿的专属HTML精美组件构建。覆盖来自 `K11 资产减值损失.xlsx` 的7个有效sheet。科目覆盖6701资产减值损失（**损益类！取发生额**）。

**K11特点**：K循环损益类减值汇总底稿（7 sheets，最简）。①**损益类科目**！取发生额非余额（从tb_ledger取数）②**减值汇总**：汇总各类资产减值损失（存货F2/固定资产H1/无形资产I1/商誉I3/在建工程等），与各源底稿减值计提交叉验证。审定表K11-1（61公式）+ 明细表K11-2（17公式）。关键公式总数约80+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K11A**: 资产减值损失实质性程序表K11A（复用a-program-console）
- **Adjudication_K11_1**: 审定表K11-1，37行12列61公式，损益类6701审定（发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），30行27列
- **Disclosure_SOE**: 附注披露信息（国企），29行27列
- **Detail_K11_2**: 明细表K11-2，50行18列17公式，按资产类别的减值损失明细
- **Adjustment_K11_3**: 调整分录汇总K11-3
- **Impairment_Summary_Engine**: 减值汇总引擎（汇总各资产减值+源底稿核对）
- **Income_Statement_Rule**: 损益类取数规则：从tb_ledger取发生额
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（6701，发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K11资产减值损失按sheetName分发, so that 7个sheet有序组织。

#### Acceptance Criteria

1. THE K11 组件 SHALL 注册componentType: `k11-asset-impairment-loss`，主入口GtK11AssetImpairmentLoss.vue
2. THE GtK11AssetImpairmentLoss.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K11 组件 SHALL defineAsyncComponent懒加载
4. THE K11 组件 SHALL 子目录：k11/core/
5. THE K11 组件 SHALL composable分层：useK11FormData + useK11FormulaEngine(纯函数) + useK11ImpairmentSummaryEngine(纯函数) + useK11CrossSheet + useK11DualMode + useK11ImportExport
6. THE K11 组件 SHALL htmlRendererRegistry注册'k11-asset-impairment-loss'
7. THE K11 组件 SHALL wp_code_overrides: K11/K11-1~K11-3/K11A → 'k11-asset-impairment-loss'
8. THE K11 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K11 组件 SHALL selfLoad支持
10. THE K11 组件 SHALL checklist_responses存储，前缀"K11-{sheet}-{field}"

### Requirement 2: 审定表K11-1（61公式，损益类！取发生额）

**User Story:** As a 审计助理, I want to 在审定表中查看资产减值损失, so that 我能验证各类资产减值发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_K11_1 SHALL 按资产类别分行（存货跌价/固定资产减值/无形资产减值/商誉减值/在建工程减值/长期股权投资减值/其他）
2. THE Adjudication_K11_1 SHALL 显示：项目|本期发生额|上期发生额|未审|AJE|RJE|审定数|同比变动|来源底稿|备注
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：从tb_ledger取本期借方发生额累计（减值损失借方增加），不取期末余额
5. THE Adjudication_K11_1 SHALL 与K11-2明细/各源底稿减值计提交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（6701，**发生额**）+发布'substantive:adjudicated'
7. THE Adjudication_K11_1 SHALL 各来源行GtIndexChip跳转对应减值底稿（F2/H1/I1/I3等）
8. THE Adjudication_K11_1 SHALL 底部审计说明+结论+复核入口，37行虚拟滚动

### Requirement 3: 明细表K11-2（18列17公式）

**User Story:** As a 审计助理, I want to 管理资产减值损失明细, so that 各类减值可逐项核对至源底稿。

#### Acceptance Criteria

1. THE Detail_K11_2 SHALL 将18列拆为2区段Tab：基础(序号/资产类别/减值项目/本期计提/本期转回(仅非商誉)/本期发生额) | 核对(来源底稿/源底稿计提金额/差异(公式)/凭证/结论)
2. THE Formula_Engine SHALL 计算差异=本期发生额-源底稿计提金额
3. THE Detail_K11_2 SHALL 合计行与K11-1审定表交叉验证
4. THE Detail_K11_2 SHALL 动态行新增+导入导出+50行虚拟滚动
5. THE Detail_K11_2 SHALL 对差异非零行红色标记

### Requirement 4: 减值汇总引擎与源底稿联动

**User Story:** As a 开发者, I want to 实现减值汇总引擎并联动源底稿, so that K11减值损失可追溯至各资产减值来源。

#### Acceptance Criteria

1. THE Impairment_Summary_Engine SHALL 汇总各资产类别减值损失=Σ各来源计提
2. THE K11 SHALL subscribe各减值源底稿（F2存货/H1固定资产/I1无形资产/I3商誉等）的减值计提事件
3. THE Impairment_Summary_Engine SHALL 计算源底稿核对差异
4. WHEN 差异>阈值时 SHALL 红色标记提示核对
5. THE K11 SHALL 商誉减值不可转回的特殊处理（不显示转回列）

### Requirement 5: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类取数逻辑, so that K11不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 从tb_ledger取本期发生额（减值损失借方发生累计），非tb_balance期末余额
2. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额
3. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 6: 附注披露 + 调整分录 + 公式引擎（纯函数）

**User Story:** As a 审计助理/开发者, I want to 生成附注、管理调整分录并验证公式, so that 披露完整、核心公式可PBT验证。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市30×27/国企29×27）+按资产类别披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K11_3 SHALL 借贷平衡+双向同步K11-1+publish 'adjustment:created'→A13+导入导出
3. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
4. THE Formula_Engine SHALL calcIncomeStatementOccurrence(debitOcc, creditOcc): 减值损失发生额=借方发生-贷方发生
5. THE Impairment_Summary_Engine SHALL calcImpairmentSummary(sources[]): 减值汇总=Σ各来源
6. THE Formula_Engine SHALL calcSourceVariance(k11Amount, sourceAmount): 源底稿核对差异
7. THE Formula_Engine SHALL calcSubtotal(arr): 合计
