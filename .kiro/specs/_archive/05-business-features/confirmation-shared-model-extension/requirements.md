# Requirements Document

## Introduction

函证枢纽的四张共享表（X0-1 函证结果汇总、X0-2 核实被函证单位信息、X0-7 回函可靠性核对、X0-4 差异调节）在平台上**各只有一份共享组件**，被 D0/E0/F0/G0/H0/K0/L0 七个枢纽共用。以 D0 打磨后的源模板为尺子逐 sheet 实测，这四份共享行模型相对源模板**缺列**，导致审计师在底稿里无处记录源模板要求的信息（只能塞备注或不记）。

本 spec 只做一件事：**按源模板 additive 补齐这四个共享行模型的字段与对应 UI 列**，一次修惠及七个枢纽。

**已实证的现状基线（不得假设）**：

- `ConfirmationRow`（`confirmation/confirmationTypes.ts`，28 字段）现有：`seq / confirm_index / account_type / entity_name / entity_address / contact_person / contact_phone / amount / currency / confirmation_method / send_date / reply_date / is_replied / reply_method / reply_amount / match_status / difference / confirmed_amount / alt_confirmed / diff_ref_index / alt_ref_index / remark / electronic_reply / reliability_verified / fraud_risk_flag` + 内部标记 `_row_id / _source / _overridden`
- 持久化格式为 `ConfirmationPayload._format = 'confirmation-v1'`，全部七枢纽共用；台账投影经 `coordination/syncHubFromSummary.ts` 映射到 `confirmation` 表
- `accountTabs` 由 `useConfirmationData` 从行数据 `account_type` 动态派生（非硬编码）
- 各枢纽源模板 X0-1 的段数与列数**不同构**：D0-1 4 段 24 列 / F0-1 4 段 27 列 / G0-1·H0-1 4 段 27 列 / **K0-1·L0-1 5 段 28 列**（多「发函询证纪要」段与行级「审计结论」列）/ E0-1 3 段 21~24 列（含原币/本位币双列与汇率）
- `EntityVerifyRow`（`entityVerify/entityVerifyTypes.ts`）现有企查查核查块（`qcc_*`）+ 一致性判定 + 两次发函；源模板 X0-2 为 25~43 列，**回函核实块（是否原件 / 是否直接收到 / 回函发出地址 / 回函寄件人 / 回函电话 / 三项一致性判定 / 不一致说明 / 核实证据索引 / 跟函控制过程索引）几乎全缺**
- `ReliabilityRow`（`reliability/reliabilityTypes.ts`）现有 identity / email / phone 三类验证 + `conclusion_status`；源模板 F0-7·G0-7·H0-6·K0-7·L0-6 均 14 列同构，缺函证索引号 / 被询证单位名称 / 回函方式 / 是否项目组直接接收 / 是否寄回原件 / 传真信息及验证 / 发函与回函邮箱双列 / 可靠性考虑文本
- `DiffReconcileRow`（`diffReconcile/diffReconcileTypes.ts`）8 列全对应源模板，仅缺「相关支持性证据」1 列
- `fraudRisk`（19 条迹象预置）、`followup`（memo 模板 + 3 控制项 + 签名）、`diffChecklist` 经核对**与源模板齐**

**范围边界**：不改 `confirmation` 台账表结构与状态机；不改 Sync_To_Center / Reply_Backflow / Unreplied_Pull 的联动语义（归 `confirmation-hub-workbench-tabs`）；不改替代程序（X0-5/X0-6）区块列结构（归 `confirmation-alternative-structure-alignment`）；不做 G0 特有的证券/非证券差异三维模型（归 `g0-investment-diff-model`）；不新增源模板没有的字段。

## Glossary

| 术语 | 含义 |
|------|------|
| Shared_Row_Model | 被七枢纽共用的行类型：`ConfirmationRow` / `EntityVerifyRow` / `ReliabilityRow` / `DiffReconcileRow` |
| Cycle_Variant_Column | 仅部分枢纽源模板存在的列（如 K0/L0 的行级审计结论、E0 的原币/本位币/汇率、H0 的合同条款口径） |
| Payload_Format | 底稿持久化格式标识（`confirmation-v1` 等），决定既有数据能否被读回 |
| Additive_Extension | 只新增可选字段、不改既有字段名/语义/类型的扩展方式 |
| Term_Confirmation | H0 源模板「金额**或合同条款**」双口径中的条款侧确认（现 `amount` 为 number，条款无载体） |
| Reply_Verification_Block | X0-2 的回函核实块（是否原件 / 直接收到 / 回函发出地址 / 寄件人 / 电话 / 一致性判定 / 不一致说明 / 证据索引 / 跟函索引） |
| Sync_Field_Set | `syncHubFromSummary` 实际映射到台账 `confirmation` 表的字段集合 |

## Requirements

### Requirement 1: ConfirmationRow 按源模板补齐共性缺列

**User Story:** 作为审计助理，我要在 X0-1 汇总表里记录源模板要求的发函单号、地址核查、回函快递单号等信息，而不是塞进备注。

#### Acceptance Criteria

1. WHEN 扩展 `ConfirmationRow` THEN 系统 SHALL 以 Additive_Extension 方式补齐七枢纽共性缺列：选取样本目的、发函单号、收件地址核查是否一致、回函快递单号、回函发出地址、发函地址与回函地址是否一致、是否采取替代程序（布尔）、替代后不可确认金额
2. WHEN 补列 THEN 系统 SHALL NOT 改动既有 28 字段的字段名、类型与语义（`account_type` 保持「科目大类」语义，不复用为「账户或交易」）
3. WHERE 源模板某列在现有字段中已有等价载体 THE 系统 SHALL 复用既有字段而 SHALL NOT 新增同义字段
4. WHEN 补列落地 THEN X0-1 组件 SHALL 在对应表格段内渲染这些列，且列顺序 SHALL 与源模板段内顺序一致
5. WHERE 某列为源模板派生列（如差异、可确认金额）THE 系统 SHALL 保持既有自动计算规则不变

### Requirement 2: Cycle_Variant_Column 按枢纽差异呈现

**User Story:** 作为审计助理，我在其他应收款函证要能填「发函询证纪要」和行级审计结论，在银行函证要能填原币/本位币和汇率，但不希望这些列在不需要的循环里也占屏。

#### Acceptance Criteria

1. WHEN 渲染 X0-1 THEN 系统 SHALL 支持按枢纽启用 Cycle_Variant_Column，且 SHALL 由配置（枢纽 → 列集合）驱动而非在组件内硬编码 if-else 分支
2. WHERE 枢纽为 K0 / L0 THE 系统 SHALL 提供「发函询证纪要」段与行级「审计结论」列（源模板 5 段 28 列）
3. WHERE 枢纽为 E0 THE 系统 SHALL 提供 账号或理财产品名称 / 币种 / 汇率 / 发函金额（原币）/ 发函金额（本位币）/ 可确认金额（原币）/ 可确认金额（本位币）
4. WHERE 枢纽为 H0 THE 系统 SHALL 支持 Term_Confirmation（合同条款口径）的文本载体，使「金额或合同条款」双口径的条款侧差异可被记录
5. WHERE 某 Cycle_Variant_Column 在当前枢纽源模板不存在 THE 系统 SHALL NOT 渲染该列（避免空列噪声）
6. WHEN 启用原币/本位币双列 THEN 系统 SHALL 明确哪一列参与覆盖率与差异计算（本位币），且 SHALL NOT 因新增原币列改变既有金额口径

### Requirement 3: EntityVerifyRow 补齐 Reply_Verification_Block 与企查查块缺列

**User Story:** 作为审计助理，我要在 X0-2 记录回函是否原件、是否项目组直接收到、回函寄件人与地址一致性，这是评估回函可靠性的核心证据。

#### Acceptance Criteria

1. WHEN 扩展 `EntityVerifyRow` THEN 系统 SHALL 以 Additive_Extension 补齐 Reply_Verification_Block 全部列
2. WHEN 扩展 THEN 系统 SHALL 补齐企查查块缺列：邮编、邮箱/传真、不一致说明是否合理、支持性文件索引、备注
3. WHERE 一致性判定类列 THE 系统 SHALL 以点选（是/否/不适用）而非自由文本录入
4. WHEN 判定为「不一致」THEN 系统 SHALL 要求或提示填写不一致说明（合规提示，不静默通过）
5. WHERE X0-2 与 X0-7 存在同义列（回函方式 / 是否原件 / 是否直接接收）THE 系统 SHALL 定义单一录入位置并在另一侧只读引用或明示口径，且 SHALL NOT 形成两处可各自编辑的双真源

### Requirement 4: ReliabilityRow 与 DiffReconcileRow 补齐

**User Story:** 作为质量控制复核合伙人，我要在回函可靠性核对表看到函证索引号、被询证单位、回函方式与验证过程，而不是只有三个验证勾选。

#### Acceptance Criteria

1. WHEN 扩展 `ReliabilityRow` THEN 系统 SHALL 以 Additive_Extension 补齐：函证索引号、被询证单位名称、回函方式、是否项目组直接接收、是否寄回原件、传真信息及验证、发函邮箱与回函邮箱双列、可靠性考虑文本
2. WHERE 函证索引号与被询证单位名称可从 X0-1 取得 THE 系统 SHALL 提供从 X0-1 带入并去重，且 SHALL NOT 要求审计师重抄
3. WHEN 扩展 `DiffReconcileRow` THEN 系统 SHALL 补「相关支持性证据」列
4. WHEN 上述补列落地 THEN 各组件 SHALL 按源模板 14 列 / 9 列顺序渲染

### Requirement 5: 既有数据零丢失与格式兼容

**User Story:** 作为平台维护者，七个枢纽已有在编制的底稿，补列不能让已录数据读不回来。

#### Acceptance Criteria

1. WHEN 读取 Payload_Format 为既有版本的持久化数据 THEN 系统 SHALL 完整回显既有字段，新增字段 SHALL 为空而非报错或整行丢弃
2. WHERE 需要提升 Payload_Format 版本 THE 系统 SHALL 同时保留对旧版本的读取兼容（旧值原样载入），且 SHALL NOT 要求数据迁移脚本作为可用前提
3. WHEN 保存 THEN 系统 SHALL NOT 因新增字段导致既有字段被丢弃或改写
4. WHEN 补列落地 THEN Sync_Field_Set 的映射结果 SHALL 逐字不变（台账既有列取值不受影响）
5. WHERE 新增字段在台账 `confirmation` 表无对应列 THE 系统 SHALL 仅在底稿侧持久化，且 SHALL NOT 改台账表结构

### Requirement 6: 列宽与可读性（宽表可操作）

**User Story:** 作为审计助理，X0-1/X0-2 补列后会到 28~43 列，我不能被迫一直横向滚动。

#### Acceptance Criteria

1. WHERE 表格列数超过平台宽表阈值 THE 系统 SHALL 提供列显隐设置（含预设方案与本地持久化），且默认方案 SHALL 覆盖最常用列
2. WHEN 渲染分段表头 THEN 系统 SHALL 按源模板分段（发函信息 / 收到回函 / 回函金额确认 / 未收到回函的替代程序 / 发函询证纪要）分组呈现
3. WHERE 数值列 THE 系统 SHALL 右对齐并按平台金额格式（千分符 + 两位小数）显示
4. WHEN 关键列（函证索引号、被询证单位名称）被横向滚动 THEN 系统 SHALL 保持其可辨识（固定列或等效手段），且 SHALL NOT 因固定列造成表格布局错位

### Requirement 7: 零回归

**User Story:** 作为平台维护者，四张共享表是七个枢纽在用的，补列不能破坏既有能力。

#### Acceptance Criteria

1. WHEN 本 spec 改动落地 THEN 既有函证域前端测试 SHALL 全部通过
2. WHEN 本 spec 改动落地 THEN Sync_To_Center / Reply_Backflow / Unreplied_Pull / 覆盖率指标计算 SHALL 行为不变
3. WHEN 本 spec 改动落地 THEN `accountTabs` 动态派生行为 SHALL 不变
4. WHERE 补列按 Shared_Row_Model 分批实施 THE 每批 SHALL 独立可发布且可单独回退
5. WHEN 本 spec 改动落地 THEN 替代程序适配器（`createAlternativeConfirmationData` 八套）读取 X0-1 行的行为 SHALL 不变

### Requirement 8: 不臆造（宁缺勿造）

**User Story:** 作为业务合伙人，底稿列必须能对上致同源模板，不能凭常识加列。

#### Acceptance Criteria

1. WHERE 某列在任一枢纽源模板中均不存在 THE 系统 SHALL NOT 新增该列
2. WHEN 新增任一字段 THEN 系统 SHALL 在字段注释中标注其源模板出处（枢纽 + sheet + 列名）
3. WHERE 源模板对同一语义在不同枢纽用词不同 THE 系统 SHALL 各枢纽按自身源模板用词呈现，且 SHALL NOT 强行统一为其中一种
4. WHERE 现有实现存在超出源模板的字段 THE 系统 SHALL 保留（不做破坏性删除）并登记为源外增强

### Requirement 9: 属性化可测

**User Story:** 作为平台维护者，我要补列规则以可测属性表达，避免"看着对"。

#### Acceptance Criteria

1. WHEN 定义 Additive_Extension THEN 系统 SHALL 具备属性测试：任意既有版本 payload 经读取→保存→读取后，既有字段值 SHALL 不变（round-trip 保真）
2. WHEN 定义 Cycle_Variant_Column THEN 系统 SHALL 具备契约测试：每个枢纽启用的列集合 SHALL 与该枢纽源模板列清单一致（清单以数据文件形式登记，漂移即失败）
3. WHEN 定义 Sync_Field_Set THEN 系统 SHALL 具备契约测试锁定映射不变
4. WHEN 定义 Requirement 8 THEN 系统 SHALL 具备守卫：Shared_Row_Model 中每个字段都能追溯到源模板出处或被显式登记为源外增强
