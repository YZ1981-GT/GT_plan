# Requirements Document

## Introduction

函证替代程序（alternative confirmation）模块存在八套近乎逐字重复的数据 composable——`useAlternativeData`(D0-5)、`useAlternativeD06Data`、`useAlternativeF05Data`、`useAlternativeF06Data`、`useAlternativeH05Data`、`useAlternativeK05Data`、`useAlternativeK06Data`、`useAlternativeL05Data`。它们共享完全相同的核心逻辑（公司 CRUD、四区块行 CRUD、区块合计、完成度、异常检测、看板 metrics、buildPayload/initFromHtmlData 骨架），仅在少数配置点上不同（`_format` 串、`getSumFields` 来源、默认 balance 的 `item_name`、`getCheckRatio` 的 block 映射/基数/字段、payload 比例字段名）。这种重复导致维护面分散（修一处 bug 要改八处）、行为易漂移（如各表 `_format` 已与后端 seed 出现过 drift）。

本 spec 目标：在**不改变任何一套 composable 对外行为**的前提下，将八套收敛为单一配置驱动工厂 `createAlternativeConfirmationData(config)`，八套 composable 退化为「传入各自 config 调用工厂」的薄封装（保持导出名与返回签名不变，68 处 caller 零改动）。收敛必须建立在 characterization 测试安全网之上——先锁定当前行为，收敛后同一批测试全绿即证明等价。

本 spec 属重构（refactor），核心验收标准是**功能等价性**与**零回归**，不新增业务功能。

## Glossary

- **Alt_Composable**: 八套函证替代程序数据 composable 之一（`useAlternative{D05,D06,F05,F06,H05,K05,K06,L05}Data`），对外暴露 companies/CRUD/区块操作/metrics/buildPayload 等。
- **Factory**: 拟新建的配置驱动工厂函数 `createAlternativeConfirmationData(config)`，产出与现有 Alt_Composable 行为等价的返回对象。
- **Alt_Config**: 工厂的配置参数对象，声明各 Alt_Composable 的差异点（见 Requirement 2）。
- **Shared_Core**: 八套 composable 完全相同的逻辑：公司 CRUD、四区块（block1~block4）行 CRUD、`getBlockTotal`、`getCompletionStatus`、`hasAbnormal`、`metrics`、`initFromHtmlData`/`ensureCompanyId`/`ensureRowId`/`watch` 骨架、`generateId`/`precise`。
- **Check_Ratio**: `getCheckRatio(company, type)`，各表按不同 block/基数/字段计算的两个检查比例。
- **Base_Amount**: Check_Ratio 的分母基数（D05/D06=`balance.sales_amount`；F05/F06=`balance.purchase_amount ?? sales_amount`；H05=`balance.closing_balance ?? ending_balance`；K05/K06/L05 待 Design 阶段实测确认）。
- **Extra_Capability**: 部分 Alt_Composable 独有的附加能力——H05/K0/L0 的 `importFromSummary`(async http)、`loadAll`/`persistAll` 别名、`loading` ref，以及 `useH0/K0/L0FormulaEngine`、`useH0/K0/L0ImportExport` 辅助模块。
- **Characterization_Test**: 锁定 Alt_Composable **当前**行为的回归测试；收敛前已为 D05/D06/F05/F06/H05 建立，K05/K06/L05 待补。
- **Caller**: 消费 Alt_Composable 的 `.vue` 组件（如 `GtConfirmationAlternative*.vue`），codegraph 实测 `AlternativeCompany` 相关引用约 68 处。

## Requirements

### Requirement 1: 行为等价（零回归）

**User Story:** As a 平台维护者, I want 八套函证替代 composable 收敛为单一工厂后对外行为逐字不变, so that 68 处 caller 与既有持久化数据无需任何改动、无回归风险。

#### Acceptance Criteria

1. THE Factory SHALL 产出与被替换 Alt_Composable **完全一致的返回对象形状**（相同的属性名、方法名、类型签名与返回值语义）。
2. WHEN 任一 Alt_Composable 被改为调用 Factory 后, THE Alt_Composable SHALL 保持其原有导出名与导入路径不变（如 `export function useAlternativeF05Data(...)` 仍存在且签名不变），并**完整保留所有对外契约**：导出名/导入路径、Caller 调用代码、持久化 payload 结构、后端 seed 格式一律不变。
3. THE Factory SHALL 保留各套 composable 各自独立的 TypeScript 返回类型（如 `buildPayload` 返回 `AlternativeF05Payload`、`AlternativeF06Payload` 等 literal `_format` 类型），不得因收敛而将返回类型泛化为丢失 literal 区分的宽类型。
4. THE Factory SHALL 对每套配置产出的 `buildPayload()._format` 与收敛前逐字相同（D05=`alternative-d05-v1`、F05=`alternative-f05-v1`、…）。
5. THE Factory SHALL 对每套配置产出的 `getCheckRatio` 在相同输入下返回与收敛前逐字相同的数值（含 null/N-A 边界与浮点精度 `precise`）。
6. WHEN 收敛完成后运行全部 Characterization_Test 时, THE 测试套件 SHALL 全部通过且无需修改任何断言（测试仅切换被测目标为工厂产出的 composable，断言不变）。
7. THE 收敛 SHALL NOT 改变任何 Caller 的调用代码、任何持久化 payload 的结构、任何后端 seed 格式。

### Requirement 2: 配置驱动的差异点收敛

**User Story:** As a 平台维护者, I want 八套之间的差异被完整、显式地抽取为工厂配置, so that Shared_Core 只写一份、差异一目了然、新增替代表只需新增配置。

#### Acceptance Criteria

1. THE Alt_Config SHALL 至少包含以下差异字段：`format`（payload `_format` 串）、`getSumFields`（区块合计字段来源函数）、`defaultBalance`（新增/导入公司时的默认 balance，如 `{}` 或 `{ item_name: '预付账款' }`）。
2. THE Alt_Config SHALL 以数据结构声明 Check_Ratio 的计算规则：每个比例的 `key`（type 名，如 `receipt`/`payment`/`ownership`）、目标 `block`、求和字段优先级列表（如 `['payment_amount','bank_amount']`）、`payloadKey`（写回 balance 的字段名，如 `payment_check_ratio`）。
3. THE Alt_Config SHALL 声明 Base_Amount 的取值规则（分母来源字段及其回退顺序）。
4. THE Alt_Config SHALL 声明 metrics 中 `ratio_distribution` 的 `receipt_ratio`/`shipment_ratio` 分别映射到哪个 Check_Ratio key（各表映射不同，如 H05 的 `receipt_ratio=acceptance`、`shipment_ratio=ownership`）。
5. WHERE 某差异点在所有八套中取值相同, THE Alt_Config SHALL 为该项提供合理默认值以减少每套配置的样板。
6. THE Shared_Core 逻辑（公司/区块 CRUD、getBlockTotal、getCompletionStatus、hasAbnormal、metrics 骨架、init/ensure/watch、generateId/precise）SHALL 在工厂内只实现一份，不再在任何 Alt_Composable 中重复。
7. THE 收敛后的 Alt_Composable SHALL NOT 重复实现任何 Shared_Core 逻辑（Shared_Core 只在工厂内一份）。变体差异优先经 Alt_Config 表达；**仅** Requirement 3 明确列举的、无法配置化的异质面（命名比例方法别名、构造签名适配、K06 的 http load/persist、importFromSummary、balanceSummary 及各套独有导出）允许作为薄旁挂保留在适配器中。除此之外，适配器不得含额外业务逻辑。

### Requirement 3: 边界——附加能力的处置

**User Story:** As a 平台维护者, I want 明确 Extra_Capability（importFromSummary/loadAll/persistAll/loading 及 FormulaEngine/ImportEngine 辅助模块）在收敛中的归属, so that 收敛范围清晰、不误伤 H05/K0/L0 的额外功能。

#### Acceptance Criteria

1. THE spec SHALL 在 Design 阶段对每项 Extra_Capability 明确处置策略：纳入工厂（作为可选配置/可选返回）或保留在各 Alt_Composable 中旁挂于工厂返回对象之上。
2. WHERE Alt_Composable 提供 `loadAll`/`persistAll` 别名（H05）, THE 收敛后实现 SHALL 保留这些别名且语义不变（`persistAll` 等价 `buildPayload`）。
3. WHERE Alt_Composable 提供 `importFromSummary`(async http) 与 `loading` ref（H05/K0/L0）, THE 收敛 SHALL 保留其行为不变；此能力依赖 `wpId`/`projectId` props 与 http 调用，工厂设计须兼容"有/无该能力"两种形态。
4. THE 收敛 SHALL NOT 修改 `useH0/K0/L0FormulaEngine`、`useH0/K0/L0ImportExport`、`blockColumnConfigs*`、`alternative*Types.ts` 的对外契约（这些是工厂消费的输入，不在收敛范围内）。IF 任一对外契约将被破坏, THEN 收敛 SHALL 整体停止（不做部分收敛+记录 breaking change 的折中）。
5. WHERE K05/K06/L05 的 composable 位于 `k0-confirmation`/`l0-confirmation` 目录且与 D/F/H 结构存在差异, THE Design 阶段 SHALL 实测其 getCheckRatio/base/format/默认 balance 后再纳入工厂，不得凭猜测收敛；IF 某套的差异实测未完成, THEN 该套 SHALL NOT 被收敛（阻断直至实测完成）。

### Requirement 4: 收敛前置——Characterization 安全网

**User Story:** As a 平台维护者, I want 在动任何收敛代码前，八套 composable 均有锁定当前行为的测试, so that 收敛是"红-绿"可验证的等价变换而非盲改。

#### Acceptance Criteria

1. THE spec SHALL 在收敛任一 Alt_Composable 前确认其 Characterization_Test **完整覆盖全部八个行为面**（init 格式判定、公司 CRUD、区块行 CRUD、区块合计、getCheckRatio 各比例、completionStatus、hasAbnormal、metrics、buildPayload）；任一面缺失覆盖时 SHALL NOT 开始该套收敛（不接受部分覆盖）。
2. WHERE K05/K06/L05 尚无专门的 Characterization_Test, THE spec SHALL 先为其补齐测试（锁定当前行为）再收敛。THE 全部八套 Alt_Composable SHALL 在**任何一套开始收敛之前**均已具备完整 Characterization_Test（八套测试全部就位是收敛启动的前置门）。
3. WHEN 为某 Alt_Composable 补 Characterization_Test 时, THE 测试 SHALL 针对**收敛前的现有实现**编写并通过（证明测试正确反映当前行为）。
4. THE Characterization_Test SHALL 在收敛后不加修改地重新运行并全绿（除非仅切换 import 目标）。

### Requirement 5: 增量、可回退的收敛顺序

**User Story:** As a 平台维护者, I want 收敛按一套一套增量推进而非一次性重写八套, so that 每步都可独立验证、出问题可精确定位与回退。

#### Acceptance Criteria

1. THE Factory SHALL 作为全局前置先建立（不依附于任一具体套），随后用**结构最简、已有测试**的一套（D05）作为首个迁移试点，试点全绿后再推广。
2. WHEN 每套 Alt_Composable 迁移到工厂后, THE 该套的 Characterization_Test SHALL 立即全绿，随后才迁移下一套。
3. IF 某套迁移导致其 Characterization_Test 失败, THEN 收敛 SHALL 停止并定位根因（工厂逻辑或配置缺陷），不得放宽测试断言绕过。
4. THE 每套迁移 SHALL 是独立提交单元（便于精确回退）。
5. WHEN 某套因失败被暂停调查时, THE 已迁移且测试全绿的套数 SHALL 保持已收敛状态（不回退），而失败的该套 SHALL 保持其收敛前的原实现（不得在测试红的情况下被标记为"已收敛"）；整体 spec 的"完成"判定仍以 Requirement 6 的全套全绿为准。
6. WHILE 某套处于失败暂停状态, THE 调查过程 SHALL 保持进行中（仅定位到根因不算完成），直至根因被修复且该套测试转绿或该套被明确移出收敛范围。

### Requirement 6: 校验与文档

**User Story:** As a 平台维护者, I want 收敛完成后有明确的验证证据与配置文档, so that 后续新增替代表能直接复用工厂、维护者能快速理解差异矩阵。

#### Acceptance Criteria

1. WHEN 收敛全部完成后, THE 全部函证模块 vitest（含八套 Characterization_Test + coordination + 其它 confirmation 测试）SHALL 全绿。
2. THE 收敛后代码 SHALL 通过 `get_diagnostics` 无错误（工厂、八套薄封装、被改动测试文件）。
3. THE spec SHALL 产出一份差异矩阵文档（八套 × 配置项），作为工厂配置的单一参考。
4. THE 收敛 SHALL 保持前端 Vite 可正常 transform 八套 composable 及其 caller（无 import 解析失败/命名导出缺失）。
5. WHERE 收敛消除了重复代码, THE 结果 SHALL 使八套 Alt_Composable 各自的文件行数显著下降（每套退化为 config + 工厂调用）。
