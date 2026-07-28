# Design Document

## Overview

按各枢纽源模板 additive 补齐四个共享行模型（`ConfirmationRow` / `EntityVerifyRow` / `ReliabilityRow` / `DiffReconcileRow`）的字段与对应 UI 列，一次修惠及 D0/E0/F0/G0/H0/K0/L0 七枢纽。

**第一性约束**：既有 `confirmation-v1` / `entity-verify-v1` / `reliability-v1` / `diff-reconcile-v1` 持久化数据必须逐字读回；`syncHubFromSummary` 映射到台账 `confirmation` 表的字段集合不变；`accountTabs` 动态派生不变。补列一律**新增可选字段**，不改既有字段名/类型/语义。

**实证基线（读码确认）**：
- X0-1 明细列在 `ConfirmationMaster.vue` **硬编码 `el-table-column`**（非配置驱动），`GtConfirmationSummary.vue` 是外壳（含 Dashboard/Tabs/Master/Detail/FullGrid 分视图）。故 Cycle_Variant_Column 需引入**列配置驱动层**，不能继续堆 if-else。
- `ConfirmationRow` 28 字段 + `_row_id/_source/_overridden`；`account_type` = 科目大类语义。
- `EntityVerifyRow` 已有 qcc_* 企查查块 + name/address/contact/phone_match 一致性判定 + 两次发函 + 电子函证块，但**回函核实块几乎全缺**。
- `ReliabilityRow` 有 identity/email/phone 三类验证 + `original_returned` 条件控制 + `conclusion_status`。
- `DiffReconcileRow` 15 字段全对应源模板，仅缺「相关支持性证据」。

## Architecture

```
┌── 列配置驱动层（新增，纯数据 + 纯函数）──────────────────────────┐
│ confirmationColumnSpec.ts                                       │
│   BASE_CONFIRMATION_COLUMNS（七枢纽共性列，含本 spec 补的 ~10 列）│
│   CYCLE_VARIANT_COLUMNS: Record<Cycle, ColumnKey[]>             │
│     K0/L0 → ['send_memo_*','row_conclusion']（5段/审计结论）     │
│     E0    → ['account_no','currency','fx_rate','amount_orig',…] │
│     H0    → ['term_confirmation']（条款口径）                    │
│   resolveConfirmationColumns(cycle): ColumnDef[]  (纯函数)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 供
                           ▼
┌── ConfirmationMaster.vue（改：列由 resolveConfirmationColumns 驱动）┐
│   分段表头（发函信息/收到回函/回函金额确认/替代程序/发函询证纪要）  │
│   列显隐设置（宽表，localStorage 持久化）                          │
└──────────────────────────────────────────────────────────────────┘

类型补列（additive，不改既有字段）：
  ConfirmationRow  += ~10 共性列 + Cycle_Variant 列
  EntityVerifyRow  += Reply_Verification_Block ~11 列 + 企查查 5 列
  ReliabilityRow   += ~8 列
  DiffReconcileRow += support_evidence

数据兼容：读旧 payload → 新字段 undefined（可选字段天然兼容）；保存 → 展开既有字段 + 新字段
```

**枢纽标识来源**：Master/Grid 组件需知道当前是哪个枢纽以选列集合。枢纽由 `wp_code`（`D0`/`E0`/…/`L0`）经 props 传入或从 `useConfirmationData` 上下文取；`resolveConfirmationColumns(cycle)` 是纯函数不依赖组件状态。

### 关键决策

**决策 1：引入 `confirmationColumnSpec.ts` 列配置驱动层，Master 组件消费之**

现状 `ConfirmationMaster.vue` 列硬编码。补 ~10 共性列 + 三类 Cycle_Variant 列若继续硬编码 + if-else，会让组件不可维护且 Requirement 2.1「配置驱动而非 if-else」不达标。方案：抽 `ColumnDef`（key/label/group/width/align/editable/render 类型/仅哪些枢纽启用），`resolveConfirmationColumns(cycle)` 返回该枢纽应渲染的列（BASE ∪ 该枢纽 variant）；Master 用 `v-for` 渲染。分段表头按 `ColumnDef.group` 分组。

**决策 2：Cycle_Variant_Column 由 `wp_code` → 列集合映射驱动，源模板清单登记为数据文件**

`CYCLE_VARIANT_COLUMNS` 是纯数据（枢纽 → 列 key 列表），配套 `confirmationColumnSourceManifest.ts`（每枢纽源模板真实列清单 + 每列出处 sheet/列名）作为契约守卫的比对基准。启用哪列只看该枢纽 variant 集合，源模板没有的列不进集合（Requirement 2.5 空列噪声避免）。

**决策 3：原币/本位币双列 —— 本位币参与计算，原币仅记录（E0）**

E0 补 `currency` / `fx_rate` / `amount_orig`（发函金额原币）/ `amount`（复用既有字段作本位币）/ `confirmed_amount_orig`（可确认金额原币）/ `confirmed_amount`（复用既有作本位币）。**既有 `amount` / `confirmed_amount` 语义不变仍是本位币**，覆盖率与差异计算继续用它们（Requirement 2.6）。原币列是新增记录列，不参与既有金额口径。

**决策 4：H0 条款口径 —— 新增 `term_confirmation` 文本载体，不改 `amount` 类型**

H0 源模板「金额**或合同条款**」双口径，现 `amount` 是 number，条款无载体。补 `term_book`（账面条款）/ `term_reply`（回函条款）/ `term_match`（是否一致）/ `term_note`（差异说明）文本字段（仅 H0 variant 启用）。`amount` 保持 number 不变。

**决策 5：X0-2 ↔ X0-7 同义列单一录入位置**

`EntityVerifyRow`（X0-2 回函核实块）与 `ReliabilityRow`（X0-7）都涉及「回函方式 / 是否原件 / 是否直接接收」。定义 **X0-7 可靠性核对为该三项的唯一录入位置**（源模板 X0-7 就是回函可靠性专表），X0-2 若需展示则从 X0-7 只读引用或明示「详见 X0-7」，不做两处可各自编辑（Requirement 3.5）。X0-2 的回函核实块补齐的是 X0-7 没有的项（是否原件 / 直接收到 / 回函发出地址 / 寄件人 / 电话 / 三项一致性判定 / 不一致说明 / 证据索引 / 跟函索引）——**实测两表列清单对照后**，重叠项归 X0-7，X0-2 补差集，避免真造双真源。

**决策 6：Payload_Format 版本不升级（可选字段天然兼容）**

新增全为可选字段（`field?: T`），旧 payload 读回时新字段为 `undefined`，无需版本升级、无需迁移脚本（Requirement 5.2）。`_format` 标识保持 `confirmation-v1` 等不变。保存时展开既有字段 + 新字段，旧字段不丢（Requirement 5.3）。

## Components and Interfaces

### 新增

**`confirmation/confirmationColumnSpec.ts`（纯数据 + 纯函数）**

```ts
export type ConfirmCycle = 'D0'|'E0'|'F0'|'G0'|'H0'|'K0'|'L0'
export type ColumnGroup = 'send_info'|'reply_info'|'reply_amount'|'alternative'|'send_memo'
export interface ColumnDef {
  key: string          // 对应 ConfirmationRow 字段名
  label: string        // 源模板列名（各枢纽用词，不强行统一）
  group: ColumnGroup
  width?: number
  align?: 'left'|'right'|'center'
  editable?: boolean
  kind?: 'text'|'number'|'amount'|'date'|'bool'|'select'
  source: string       // 源模板出处「枢纽·sheet·列名」（Requirement 8.2）
}
export const BASE_CONFIRMATION_COLUMNS: ColumnDef[]         // 七枢纽共性（含补的 ~10 列）
export const CYCLE_VARIANT_COLUMNS: Record<ConfirmCycle, string[]>
export function resolveConfirmationColumns(cycle: ConfirmCycle): ColumnDef[]
```

**`confirmation/confirmationColumnSourceManifest.ts`（契约守卫基准）**

```ts
// 每枢纽源模板 X0-1 真实列清单（人工按源模板逐列录入，作为漂移守卫比对基准）
export const CONFIRMATION_SOURCE_MANIFEST: Record<ConfirmCycle, string[]>
```

### 改造

| 组件 | 动作 |
|---|---|
| `confirmationTypes.ts` | `ConfirmationRow` additive 补 ~10 共性列 + E0/H0/K0/L0 variant 字段；每字段注释源模板出处 |
| `ConfirmationMaster.vue` | 列改由 `resolveConfirmationColumns(cycle)` 驱动 `v-for`；分段表头；列显隐设置 |
| `entityVerifyTypes.ts` | `EntityVerifyRow` additive 补 Reply_Verification_Block 差集 + 企查查 5 列 |
| `entityVerify/` grid 组件 | 渲染新列；一致性判定用点选；不一致要求说明 |
| `reliabilityTypes.ts` | `ReliabilityRow` additive 补 ~8 列 |
| `ReliabilityGrid.vue` | 渲染新列；从 X0-1 带入索引号/单位名去重 |
| `diffReconcileTypes.ts` | `DiffReconcileRow` 补 `support_evidence` |
| `diffReconcile/` grid | 渲染支持性证据列 |
| `syncHubFromSummary.ts` | **不改**（确认新字段不进映射，Sync_Field_Set 不变） |

### 列显隐设置（宽表，复用平台范式）

X0-1/X0-2 补列后达 28~43 列，复用平台 `useXDetailColumnPrefs` 范式：列显隐 popover + 预设方案（全部/核心/审定）+ localStorage 持久化（key `confirmation-{cycle}-column-prefs`）；关键列（confirm_index/entity_name）`fixed="left"`。

## Data Models

### ConfirmationRow additive 补列（决策 1/3/4）

| 新字段 | 类型 | group | 启用枢纽 | 源模板出处 |
|---|---|---|---|---|
| `sample_purpose` | string | send_info | 全部 | X0-1 首列「选取样本目的」 |
| `send_doc_no` | string | send_info | 全部 | X0-1「发函单号」 |
| `send_addr_match` | 'consistent'\|'inconsistent'\|'pending' | send_info | 全部 | X0-1「收件地址核查是否一致」 |
| `reply_courier_no` | string | reply_info | 全部 | X0-1「回函快递单号」 |
| `reply_from_addr` | string | reply_info | 全部 | X0-1「回函发出地址」 |
| `send_reply_addr_match` | 'consistent'\|'inconsistent'\|'pending' | reply_info | 全部 | X0-1「发函地址与回函地址是否一致」 |
| `use_alternative` | boolean | alternative | 全部 | X0-1「是否采取替代程序」 |
| `alt_unconfirmed` | number | alternative | 全部 | X0-1「替代后不可确认金额」 |
| `row_conclusion` | string | send_memo | K0/L0 | K0-1/L0-1「审计结论」 |
| `send_memo` | string | send_memo | K0/L0 | K0-1/L0-1「发函询证纪要」段 |
| `account_no` | string | send_info | E0 | E0-1「账号或理财产品名称」 |
| `currency` | string | reply_amount | E0（复用既有 currency） | E0-1「币种」 |
| `fx_rate` | number | reply_amount | E0 | E0-1「汇率」 |
| `amount_orig` | number | send_info | E0 | E0-1「发函金额（原币）」 |
| `confirmed_amount_orig` | number | reply_amount | E0 | E0-1「可确认金额（原币）」 |
| `term_book` | string | reply_amount | H0 | H0-1「金额或合同条款」账面侧 |
| `term_reply` | string | reply_amount | H0 | H0-1 回函侧条款 |
| `term_match` | 'consistent'\|'inconsistent'\|'pending' | reply_amount | H0 | H0-1 条款一致性 |
| `term_note` | string | reply_amount | H0 | H0-1 条款差异说明 |

> `account_type` 保持科目大类语义不复用为「账户或交易」（Requirement 1.2）；「账户或交易」若源模板独立成列，作 E0 variant 新增 `account_or_txn`（实施时按 E0 源模板逐列核对确定，不确定则不加）。

### EntityVerifyRow additive 补列（Reply_Verification_Block 差集 + 企查查缺列）

实施 Wave 时先对照 X0-2 与 X0-7 源模板列清单，重叠项（回函方式/是否原件/是否直接接收）归 X0-7 唯一录入，X0-2 补差集：`is_original`（是否原件，若归 X0-7 则此处只读引用）、`direct_received`（是否项目组直接收到）、`reply_from_addr`、`reply_sender`（回函寄件人）、`reply_phone`（回函电话）、`reply_name_match`/`reply_addr_match`/`reply_phone_match`（三项一致性判定）、`reply_inconsistent_note`（不一致说明）、`verify_evidence_index`（核实证据索引）、`followup_control_index`（跟函控制过程索引）；企查查块补 `qcc_zipcode`/`qcc_email_fax`/`qcc_inconsistent_reasonable`/`qcc_support_index`/`qcc_remark`。

### ReliabilityRow additive 补列

`reply_index`（函证索引号，已有 confirm_index 可复用则不加）、`direct_received`（是否项目组直接接收）、`fax_info_verify`（传真信息及验证）、`send_email`/`reply_email`（发函/回函邮箱双列，现仅 email_domain）、`reliability_consideration`（可靠性考虑文本）——**逐列对照源模板，已有等价字段复用不新增**（Requirement 1.3）。

### DiffReconcileRow additive 补列

`support_evidence`（相关支持性证据，group 归差异说明区）。

## Correctness Properties

### Property 1: additive 读取 round-trip 保真
任意既有版本 payload 经读取→保存→读取，既有字段值 SHALL 逐字不变（新字段为 undefined 不影响）。
**Validates: Requirements 5.1, 5.3, 9.1**

### Property 2: 新字段不进 Sync_Field_Set
`syncHubFromSummary` 对含新字段的行同步后，台账 `confirmation` 表列取值 SHALL 与不含新字段时逐字一致。
**Validates: Requirements 5.4, 5.5, 7.3, 9.3**

### Property 3: Cycle_Variant_Column 契约一致
`resolveConfirmationColumns(cycle)` 的列 key 集合 SHALL 等于 `BASE ∪ CYCLE_VARIANT_COLUMNS[cycle]`，且每列 key SHALL 在 `CONFIRMATION_SOURCE_MANIFEST[cycle]` 中有出处；漂移即失败。
**Validates: Requirements 2.1, 2.5, 8.1, 9.2**

### Property 4: K0/L0 五段与审计结论
`resolveConfirmationColumns('K0')` 与 `('L0')` SHALL 含 `send_memo` group 列与 `row_conclusion`。
**Validates: Requirements 2.2**

### Property 5: E0 原币/本位币口径
E0 启用 `amount_orig` 后，覆盖率与差异计算 SHALL 仍用 `amount`（本位币），SHALL NOT 因新增原币列改变既有金额口径。
**Validates: Requirements 2.3, 2.6**

### Property 6: H0 条款载体
`resolveConfirmationColumns('H0')` SHALL 含 `term_*` 列，且 `amount` 类型 SHALL 仍为 number。
**Validates: Requirements 2.4**

### Property 7: 一致性判定点选 + 不一致要求说明
X0-2 一致性判定列 SHALL 为点选（是/否/不适用）；判定为不一致时 SHALL 提示/要求填说明。
**Validates: Requirements 3.3, 3.4**

### Property 8: X0-2 ↔ X0-7 单一真源
回函方式/是否原件/是否直接接收 SHALL 仅在 X0-7 可编辑，X0-2 只读引用或明示，SHALL NOT 两处各自可编辑。
**Validates: Requirements 3.5**

### Property 9: 每字段可追溯源模板出处
`ConfirmationRow` / `EntityVerifyRow` / `ReliabilityRow` / `DiffReconcileRow` 每个字段 SHALL 在源出处清单中有条目或被显式登记为源外增强。
**Validates: Requirements 8.1, 8.2, 8.4, 9.4**

### Property 10: 各枢纽用词不强行统一
同一语义在不同枢纽源模板用词不同时，`ColumnDef.label` SHALL 各按自身源模板用词。
**Validates: Requirements 8.3**

### Property 11: accountTabs 派生不变
补列后 `accountTabs` 派生结果 SHALL 与补列前一致。
**Validates: Requirements 7.3**

### Property 12: 替代程序适配器读 X0-1 行不变
`createAlternativeConfirmationData` 八套读取 X0-1 行的行为 SHALL 不变。
**Validates: Requirements 7.5**

## Error Handling

| 场景 | 处理 |
|---|---|
| 旧 payload 缺新字段 | 新字段 undefined，正常渲染空，不报错不丢行 |
| 一致性判定为「不一致」无说明 | 提示要求填说明（不静默通过） |
| 宽表列超阈值 | 列显隐设置 + 分段表头 + 关键列 fixed |
| 枢纽 wp_code 无对应 variant 集合 | 回退 BASE 列（不崩） |
| 新字段在台账无列 | 仅底稿侧持久化，不改台账表 |

## Testing Strategy

- **属性测试（fast-check）**：Property 1 round-trip 保真、Property 2 Sync_Field_Set 不变
- **契约测试**：Property 3 列集合 = BASE∪variant 且出处齐全、Property 9 字段可追溯、Property 4/5/6 各枢纽 variant、Property 12 适配器读取不变
- **单元测试**：Property 7 点选+不一致说明、Property 8 单一真源、Property 11 accountTabs
- **零回归门**：函证域前端全量测试 + `htmlRendererRegistry.spec` + 八套 alternative characterization 全绿；改动文件 `get_diagnostics` 清 + Vite transform 200
- **Playwright**：D0/K0/E0/H0 各一次，验证补列渲染（K0 审计结论列、E0 原币/汇率、H0 条款、共性 ~10 列）、宽表列显隐、旧数据回显不丢

## Migration / Phasing

| 阶段 | 内容 | 可回退 |
|---|---|---|
| **M0** | 逐枢纽逐 sheet 对照源模板列清单，落 `CONFIRMATION_SOURCE_MANIFEST` + X0-2↔X0-7 重叠项判定 + 现有源外字段登记（纯只读+数据文件） | 无风险 |
| **M1** | `confirmationColumnSpec.ts` + `ConfirmationMaster.vue` 列配置驱动改造（共性 ~10 列，不动 variant）+ 列显隐设置 | 单组件可回退 |
| **M2** | Cycle_Variant_Column（K0/L0 五段+审计结论 / E0 原币汇率 / H0 条款） | 按 variant 分批 |
| **M3** | `EntityVerifyRow` 补列 + X0-2↔X0-7 单一真源 | 独立可回退 |
| **M4** | `ReliabilityRow` + `DiffReconcileRow` 补列 | 独立可回退 |
| **M5** | 属性/契约/守卫测试 + 零回归门 + Playwright | 仅测试 |

**M0 是硬前置**：源模板列清单未逐列核实前不得进 M1（避免臆造列或漏列）。
