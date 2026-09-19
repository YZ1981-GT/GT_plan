# Requirements Document

## Introduction

替代程序底稿（X0-5 / X0-6）是函证枢纽里**唯一按循环各写一套**的组件（九套：D05 / D06 / F05 / F06 / H05 / K05 / K06 / L05 / G06）。以 D0-5 打磨后的源模板与致同各循环源模板逐 sheet 实测，这九套在结构上有三类偏离：

1. **「本期发生额」未按借方/贷方拆两张表**（源模板 K0-5 / K0-6 / L0-5 的第 ③ 区块是借方、贷方**两张独立表**，组件做成一张）
2. **L0-5 缺源模板第 3 项检查**（「检查期初余额是否与上期期末余额一致」）
3. **G0-6 区块与源模板完全错配**（源为 ①初始投资协议表 ②本期借方/贷方双表 ③期后出售赎回表 + 测试范围 1 行；组件自造「持仓证明 / 股利 / 处置 / 公允价值」4 区块，且多出源模板没有的抽样总体 / 样本量 / 抽样方法 / 抽样过程 / 账面区 / 检查比例）

另有一类**结构债非功能缺**：F05 / F06（各 858 行单文件）未像 D05（887 行，已拆 Dashboard / Master / CheckBlock + composables）拆子组件。

本 spec 只做「结构对齐源模板 + 结构债收敛」，不加源模板没有的能力。

**已实证的现状基线（不得假设）**：

- 八套替代程序数据层已收敛到工厂 `coordination/createAlternativeConfirmationData(config)`（D05/D06/F05/F06/H05/K05/K06/L05），各自只剩薄适配器；`G06` 未纳入工厂
- 区块列定义已配置驱动（`blockColumnConfigs*`），改区块结构主要是改配置 + 模板渲染
- 未回函带入共用能力为 `coordination/importFromSummary.ts`（带入链本身归 `confirmation-hub-workbench-tabs`，本 spec 不动）
- H0-5 源模板「二、检查过程记录」是**空白区**，组件现有 4 区块（验收权属 / 采购证据 / 新增资产 / 抵押租赁）属源外自造；源模板无账面区、无检查比例
- K05 474 行是复用 CheckBlock / Dashboard / Master 的结果，区块不缺；K05/K06 的 block4（往来对账 / 协议）、L05 的 block4（抵质押 / 担保）属源外增强
- D0-5 / F0-5 源模板有检查比例表；K0 / L0 源模板无

**范围边界**：不改替代程序的未回函带入链（归 `confirmation-hub-workbench-tabs` Wave 4）；不改共享行模型（归 `confirmation-shared-model-extension`）；不做 G0 差异核对表三维模型（归 `g0-investment-diff-model`）；**不新增源模板没有的区块/列/检查比例**；不删既有源外增强区块。

## Glossary

| 术语 | 含义 |
|------|------|
| Alternative_Sheet | 替代程序底稿（X0-5 / X0-6），componentType `confirmation-alternative-*` |
| Occurrence_Block | 源模板第 ③ 区块「检查本期发生额」，源为**借方 / 贷方两张表** |
| Alt_Factory | `coordination/createAlternativeConfirmationData(config)` 共享数据层工厂 |
| Block_Column_Config | 区块列定义配置（`blockColumnConfigs*`），决定区块表头与字段 |
| Source_Extra_Block | 现有实现中超出源模板的区块（K05/K06 block4、L05 block4、H05 四区块） |
| Opening_Consistency_Check | L0-5 源模板第 3 项「检查期初余额是否与上期期末余额一致」 |
| Characterization_Test | 重构前先锁定现有行为的测试（不改行为，只固化） |

## Requirements

### Requirement 1: Occurrence_Block 按借方/贷方拆两张表

**User Story:** 作为审计助理，我要按源模板分别检查本期借方发生额和贷方发生额，而不是混在一张表里分不清方向。

#### Acceptance Criteria

1. WHERE 枢纽源模板的 Occurrence_Block 为借方 / 贷方两张表（K0-5 / K0-6 / L0-5）THE 系统 SHALL 渲染为两个独立区块，各自有表头、行、合计
2. WHEN 拆分落地 THEN 每张表的列 SHALL 与源模板该方向的列一致（不共用一套列硬套两个方向）
3. WHEN 既有底稿已在合并的 Occurrence_Block 中录入数据 THEN 系统 SHALL 完整回显该数据（迁移到其中一张表或保留可读），且 SHALL NOT 丢行
4. WHERE 无法确定既有行的借贷方向 THE 系统 SHALL 保留其内容并标注待人工归位，且 SHALL NOT 猜测方向
5. WHERE 枢纽源模板 Occurrence_Block 本就是一张表 THE 系统 SHALL 保持一张表（不强行拆）

### Requirement 2: L0-5 补 Opening_Consistency_Check

**User Story:** 作为审计助理，长期应付款替代程序要先核对期初余额与上期期末一致，这一步现在没有落处。

#### Acceptance Criteria

1. WHEN 渲染 L0-5 THEN 系统 SHALL 提供 Opening_Consistency_Check 检查项，位置与源模板第 3 项一致
2. WHEN 该检查项有结论 THEN 系统 SHALL 持久化并在刷新后回显
3. WHERE 期初余额与上期期末数据可从平台取得 THE 系统 SHALL 提示取数来源或提供带入，且取不到 THEN SHALL 允许手工录入并明示未取到
4. WHEN 判定不一致 THEN 系统 SHALL 要求填写说明（合规提示，不静默通过）

### Requirement 3: G0-6 区块对齐源模板

**User Story:** 作为审计助理，投资循环替代程序要按源模板的初始投资协议、本期借贷发生额、期后出售赎回来做，现在的四个区块跟源模板对不上。

#### Acceptance Criteria

1. WHEN 渲染 G0-6 THEN 系统 SHALL 按源模板结构提供：测试范围（1 行）、①初始投资协议检查表、②本期发生额借方表与贷方表、③期后出售/赎回检查表
2. WHERE 现有区块（持仓证明 / 股利 / 处置 / 公允价值）与源模板区块语义可对应 THE 系统 SHALL 迁移其数据到对应源区块，且 SHALL NOT 丢弃已录内容
3. WHERE 现有区块无源模板对应 THE 系统 SHALL 保留为 Source_Extra_Block 并登记，且 SHALL NOT 静默删除已录数据
4. WHERE 源模板 G0-6 无抽样总体 / 样本量 / 抽样方法 / 抽样过程 / 账面区 / 检查比例 THE 系统 SHALL 保留现有这些能力为 Source_Extra_Block 但 SHALL NOT 扩展它们
5. WHEN G0-6 改造落地 THEN 系统 SHALL 将其数据层纳入 Alt_Factory（与其余八套一致），除非有实测证明其 IO 行为异质无法纳入（异质面按既有范式旁挂并注明依据）

### Requirement 4: H0-5 与源外区块的处置口径

**User Story:** 作为业务合伙人，源模板留白的地方不要凭空造表，但已经做出来在用的也不要删掉。

#### Acceptance Criteria

1. WHERE H0-5 源模板「二、检查过程记录」为空白区 THE 系统 SHALL NOT 新增区块或列
2. WHEN 现有 H0-5 四区块保留 THEN 系统 SHALL 登记为 Source_Extra_Block（含依据说明）
3. WHERE 源模板无账面数据区 / 无检查比例 THE 系统 SHALL NOT 为该枢纽新增这些区
4. WHEN 登记 Source_Extra_Block THEN 系统 SHALL 以数据文件形式集中登记（可被守卫读取），而 SHALL NOT 只写在代码注释里

### Requirement 5: F05 / F06 结构债收敛（Characterization 先行）

**User Story:** 作为平台维护者，采购/预付两套替代程序各 858 行单文件难维护，但收敛不能改行为。

#### Acceptance Criteria

1. WHEN 拆分 F05 / F06 前 THEN 系统 SHALL 先有 Characterization_Test 锁定其现有可观察行为（区块渲染、合计、完成度、带入、持久化 payload 形状）
2. WHEN 拆分落地 THEN 系统 SHALL 复用 D05 已有的子组件与 composables（Dashboard / Master / CheckBlock 等）而 SHALL NOT 新造第二套等价子组件
3. WHEN 拆分落地 THEN F05 / F06 的持久化 payload 形状与字段 SHALL 逐字不变
4. WHEN 拆分落地 THEN Characterization_Test SHALL 全部通过
5. WHERE 拆分过程发现现有行为与源模板不符 THE 系统 SHALL 记录为独立缺陷项而 SHALL NOT 在重构中夹带行为变更

### Requirement 6: 逐套独立可发布与零回归

**User Story:** 作为平台维护者，九套替代程序是生产在用的，要能一套一套发、一套一套回退。

#### Acceptance Criteria

1. WHERE 改造按套（K05 / K06 / L05 / G06 / F05 / F06）实施 THE 每套 SHALL 独立可发布且可单独回退
2. WHEN 任一套改造落地 THEN 其余套的行为 SHALL 逐字不变
3. WHEN 改造落地 THEN Alt_Factory 的公共面（导出名、构造签名、返回形状）SHALL 不变，除非有对应契约测试同步更新且说明理由
4. WHEN 改造落地 THEN 既有替代程序 characterization 测试（八套）SHALL 全部通过
5. WHEN 改造落地 THEN 未回函带入（`importFromSummary`）行为 SHALL 不变

### Requirement 7: 属性化可测

**User Story:** 作为平台维护者，结构对齐要有守卫，避免下次改模板又漂移。

#### Acceptance Criteria

1. WHEN 定义区块结构 THEN 系统 SHALL 具备契约测试：每套 Alternative_Sheet 的区块集合与列集合 SHALL 与源模板清单（数据文件登记）一致，漂移即失败
2. WHEN 定义 Occurrence_Block 拆分 THEN 系统 SHALL 具备属性测试：借方表与贷方表的行不互相污染，合计各自独立正确
3. WHEN 定义既有数据回显 THEN 系统 SHALL 具备 round-trip 属性测试（旧 payload 读取→保存→读取，已录内容不丢）
4. WHEN 定义 Source_Extra_Block THEN 系统 SHALL 具备守卫：每个源外区块都在登记文件中有条目与依据
