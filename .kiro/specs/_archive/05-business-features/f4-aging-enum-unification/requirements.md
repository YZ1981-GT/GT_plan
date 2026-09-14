# Requirements Document

## Introduction

F4 应付账款是全平台**最后一个未接入账龄枚举单一真源**的循环。D1/D2/D3/D7/F1/G2/G3/G5/K1/K3 等已统一到 `useAgingConfig`（3年段 / 5年段 / 自定义，段 key `within1/y1to2/y2to3/y3to4/y4to5/over3/over5`），而 F4 自带一套固定 5 行 `F4_AGING_DEFAULTS`（`within1year / 1to2year / 2to3year / 3yearplus / aging-other`），明细表 F4-2 用**扁平 4+4 字段**（`unadjustedAgingLt1/1to2/2to3/Gt3` + `auditedAgingLt1/1to2/2to3/Gt3`）而非平台 nested keyed 结构。

现状**读写同源故无静默算错**（不同于 D2 修复前的"nested 存扁平读→恒 0"），问题是：项目在「项目设置 → 底稿配置」把账龄改成 5 年段或自定义时，**F4 不跟随**——F4-2 明细仍只有 4 档、F4-1 审定表按账龄区块仍是固定 4 行 + 其他、F4-5（账龄 1 年以上）与两个附注披露表仍按固定档位判定，导致同一项目内 F4 与其余循环账龄口径分裂，且导入导出列头也是固定 4 档。

本 spec 的目标是把 F4 接入平台账龄枚举单一真源，且**在 3 年段（与现有 4 档一一对应）下逐字节零回归**。这是一次数据模型迁移（扁平 → nested keyed），涉及 1 个明细 composable、1 个审定 composable、3 个下游 composable、2 张披露表、明细/审定表组件、后端 F4 导入导出与账龄期间注册，以及 5 个既有测试文件，故先出 spec 后实现。

## Glossary

- **Aging_Config**：平台账龄配置单一真源 `composables/useAgingConfig`（前端）/ `app/services/aging_config_service`（后端），项目级 `GET|PUT /api/projects/{id}/aging/config`，预设 `THREE_YEAR | FIVE_YEAR | CUSTOM`。
- **Segment**：账龄段 `{ key, label, dayFrom, dayTo }`；3 年段 = within1/y1to2/y2to3/over3；5 年段 = within1/y1to2/y2to3/y3to4/y4to5/over5。
- **Nested_Aging**：平台 nested keyed 账龄存储结构 `agingPrior | agingCurrent | agingAudited` → `Record<segKey, number>`（见 `composables/useAgingMigration`）。
- **Legacy_Flat_Fields**：F4-2 迁移前的扁平账龄字段 `unadjustedAgingLt1|1to2|2to3|Gt3`、`auditedAgingLt1|1to2|2to3|Gt3`（含更早别名 `aging1Year/agingLt1/adjustedAging1` 等）。
- **F4_Aging_Rows**：F4-1 审定表「按账龄分类」区块行，存储键 `F4-1-adj-aging-rows`，当前固定 5 行（4 档 + `aging-other`）。
- **Residual_Row**：`aging-other`（其他/未分类）行——F4 特有的**残差行**，承接"明细账龄四档合计 ≠ 期末余额"的差额与未按账龄拆分的 RJE，不是账龄段。
- **Aging_Periods**：后端导入导出的账龄期间集合；三期科目 = `prior/current/audited`，D3 = `prior/audited`，**F4 = `current/audited`**（期末未审账龄 + 期末审定账龄，无期初账龄）。
- **Over_One_Year_Keys**：账龄超过 1 年的段集合，按 `dayFrom >= 366` 从生效段动态派生（禁止硬编码"除 within1year 外"）。

## Requirements

### Requirement 1: F4 明细表账龄接入枚举单一真源

**User Story:** 作为审计助理，我希望 F4-2 应付账款明细表的账龄档位随项目账龄配置（3年段/5年段/自定义）变化，这样 F4 与其他循环的账龄口径一致。

#### Acceptance Criteria

1. WHEN F4-2 明细表渲染 THEN 系统 SHALL 以 `useAgingConfig(projectId, 'F4')` 的生效段作为账龄列的唯一来源（期末未审账龄、期末审定账龄各一组，按段顺序）。
2. WHEN 项目账龄配置为 3 年段 THEN F4-2 SHALL 呈现 4 档（1年以内/1-2年/2-3年/3年以上），与迁移前列数与顺序一致。
3. WHEN 项目账龄配置为 5 年段或自定义 THEN F4-2 SHALL 呈现对应段数的账龄列，不出现固定 4 档残留。
4. WHEN F4-2 行数据存在 Legacy_Flat_Fields 而无 Nested_Aging THEN 系统 SHALL 迁移为 Nested_Aging（`agingCurrent`=期末未审、`agingAudited`=期末审定），并以 Nested_Aging 为准。
5. WHEN 行同时存在 Nested_Aging 与 Legacy_Flat_Fields THEN 系统 SHALL 以 Nested_Aging 为准，忽略扁平字段。
6. WHEN 账龄配置从 A 段集切换到 B 段集 THEN 系统 SHALL 保留同 key 段金额、对新增段补 0、对已废弃段丢弃（复用平台 `remapRowAgingData`）。
7. WHEN 未获取到账龄配置（加载中或接口失败）THEN 系统 SHALL 回退到 F4 默认预设并保证段数稳定，不得首帧 4 档、配置到达后跳变。
8. WHEN 审计师使用「账龄分配」快捷按钮 THEN 候选档位 SHALL 来自生效段（不再是固定 4 个枚举值）。
9. WHEN 双账龄勾稽校验运行 THEN 系统 SHALL 以生效段求和（期末未审账龄合计 = 期末未审余额；期末审定账龄合计 = 审定数），不得只累加固定 4 档。

### Requirement 2: F4-1 审定表按账龄区块段驱动

**User Story:** 作为现场经理，我希望 F4-1 审定表「按账龄分类」区块的行随账龄配置生成，且残差行仍能兜住明细与余额的差额。

#### Acceptance Criteria

1. WHEN F4-1 渲染按账龄区块 THEN 行 SHALL 由生效段动态生成，并在末尾保留 Residual_Row（`aging-other`）。
2. WHEN 生效段为 3 年段 THEN 行 rowKey SHALL 沿用既有存储键（`within1year/1to2year/2to3year/3yearplus`，经 Legacy 映射表），使既有 `F4-1-adj-aging-rows` 数据零迁移可读。
3. WHEN 生效段包含既有映射表未覆盖的段（如 y3to4/y4to5/over5/自定义段）THEN 该行 rowKey SHALL 直接使用段 key。
4. WHEN 从 F4-2 明细聚合到 F4-1 按账龄区块 THEN 聚合 SHALL 按生效段逐段求和（读 Nested_Aging），未落入任何段的差额与未拆分 RJE 仍归入 Residual_Row。
5. WHEN 按性质区块与按账龄区块交叉核对 THEN 两者合计（含 Residual_Row）SHALL 保持迁移前的核对语义与容差。
6. WHEN 账龄配置变化 THEN 已存在的按账龄行 SHALL 按同 key 保留金额、新增段补 0、废弃段丢弃，并持久化一次。

### Requirement 3: 下游消费方按 dayFrom 派生"1 年以上"

**User Story:** 作为审计助理，我希望 F4-5（账龄 1 年以上检查表）与附注披露的"1 年以上"判定在任何账龄配置下都正确。

#### Acceptance Criteria

1. WHEN F4-5 从 F4-2 同步"账龄 1 年以上"的债权人 THEN 判定 SHALL 按 Over_One_Year_Keys（`dayFrom >= 366`）汇总，不得硬编码 1-2/2-3/3年以上 三档。
2. WHEN F4-5 展示某债权人账龄 label THEN label SHALL 取生效段 label（占比最大的超 1 年段），不得输出配置中不存在的档位名。
3. WHEN 国企披露表计算"1 年以上账龄合计" THEN 计算 SHALL 按 Over_One_Year_Keys 汇总，不得用"除 within1year 外全部行"（该写法会把 Residual_Row 计入）。
4. WHEN 国企披露表「按账龄披露」渲染 THEN 行 SHALL 跟随生效段（联动 F4-1 按账龄审定数），Residual_Row 仅在有余额时展示（保持迁移前行为）。
5. WHEN F4 关联方检查表填写账龄 THEN 账龄输入 SHALL 为生效段枚举（保留 allow-create 以容纳"借方余额"等非段说明），不得是完全自由文本。

### Requirement 4: 后端 F4 导入导出动态账龄列

**User Story:** 作为审计助理，我希望 F4-2 导出模板/数据的账龄列与项目账龄配置一致，导入时按列头匹配段。

#### Acceptance Criteria

1. WHEN 导出 F4-2 模板或数据 THEN 账龄列头 SHALL 由 `build_aging_headers(segments, periods)` 动态生成，periods = Aging_Periods(F4) = `['current','audited']`（列头后缀「期末未审」「期末审定」）。
2. WHEN 导出 F4-2 数据 THEN 账龄值 SHALL 由 `aging_export_values` 从 Nested_Aging 读取（缺失取 0）。
3. WHEN 导入 F4-2 THEN 账龄列 SHALL 由 `match_import_aging` 按列头匹配生效段；未匹配的账龄列 SHALL 跳过并在返回中给出 `skipped_columns` 提示（对齐 D2-2 行为）。
4. WHEN F4 未在后端 `subject_aging_periods` 注册 THEN 该函数 SHALL 返回 `['current','audited']`（新增 F4 分支），不得落到默认 `['prior','audited']`（F4 无期初账龄，落错会产出错误列头）。
5. WHEN 导出模板包含编制说明 THEN 说明 SHALL 列出当前项目生效账龄段，便于审计师核对。
6. WHEN 项目未配置账龄 THEN 后端 SHALL 使用 F4 默认预设（见 Req 6.2），与前端回退一致。

### Requirement 5: 3 年段下零回归

**User Story:** 作为质量控制复核合伙人，我要求这次迁移在既有项目（3 年段 = 现有 4 档）上不改变任何金额、勾稽结论与导入导出往返结果。

#### Acceptance Criteria

1. WHEN 项目生效段为 3 年段且行数据为 Legacy_Flat_Fields THEN F4-1 按账龄各行金额、按性质/按账龄交叉核对结论、F4-5 同步结果、两张披露表金额 SHALL 与迁移前逐项一致。
2. WHEN F4-2 导出→导入往返（3 年段）THEN 往返后 F4-2 各账龄金额 SHALL 与往返前一致（Round_Trip 不丢段）。
3. WHEN 既有 `F4-1-adj-aging-rows` 存储（rowKey 为 `within1year` 等）被读取 THEN 系统 SHALL 原样识别，不得因段 key 改名而丢数据。
4. WHEN 迁移完成 THEN F4 既有测试（useF4Detail / useF4Adjudication / useF4LongOutstanding / useF4RelatedParty / useF4DisclosureSOE / useF4DisclosureListed / GtF4AccountsPayable.integration / useF4FormulaEngine.pbt）SHALL 全部通过；断言若因段驱动而必须调整，SHALL 保留"3 年段结果与迁移前相同"的显式断言。
5. WHEN 迁移完成 THEN 平台其它循环（D1/D2/D3/D7/F1/G/K）的账龄行为 SHALL 不受影响（共享 `useAgingMigration`/`_cycle_import_export_common` 的改动必须是 additive）。

### Requirement 6: F4 在账龄配置中显式注册

**User Story:** 作为开发者，我希望 F4 的默认账龄预设在前后端一致且显式登记，避免两端默认不同导致段数不一致。

#### Acceptance Criteria

1. WHEN 前端 `useAgingConfig` 对 subject='F4' 应用默认 THEN 默认预设 SHALL 显式登记（不落匿名兜底）。
2. WHEN 后端 `DEFAULT_SUBJECT_PRESETS` 解析 subject='F4' THEN 默认预设 SHALL 与前端一致；鉴于 F4 源模板为 4 档（1年以内/1-2/2-3/3年以上），默认 SHALL 为 `THREE_YEAR`。
3. WHEN 项目在 subject_overrides 中为 F4 指定预设 THEN 前后端 SHALL 一致地以该覆盖为准。

### Requirement 7: 正确性属性可测

**User Story:** 作为开发者，我希望迁移的关键不变量以属性化测试锁定，防止后续回归。

#### Acceptance Criteria

1. WHEN 实现完成 THEN 系统 SHALL 提供覆盖以下不变量的测试：段驱动聚合 = 逐行逐段求和；nested 优先于 legacy；段切换保同 key/补新段/丢废段；Over_One_Year_Keys 按 dayFrom 派生；Residual_Row 不计入"1 年以上"；3 年段与迁移前逐字节一致；导入导出 Round_Trip 保值；未匹配账龄列跳过并提示。
2. WHEN 任一属性被破坏 THEN 测试 SHALL 失败并指明破坏的属性编号。
