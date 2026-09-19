# Design Document

## Overview

E0 精细打磨分三个层次，越往下越"平台级"：

| 层 | 内容 | 影响面 |
|---|---|---|
| L1 E0 专属 | ~~13 要项核对表（已作废）~~ / 品种矩阵 + E0-1 下区四块 / 银行备忘录话术 / E0-3·E0-6→E1 受限联动 / 预设纠偏 | 只动 E0 |
| L2 共享件配置 | E0-1 列集增删（`CYCLE_EXCLUDED_COLUMNS`）/ 可靠性按渠道补 12 列 / ~~meta 补 `reliabilityCode`（已作废，改为修注释）~~ | 七枢纽共用，须零回归 |
| L3 平台缺陷 | `GtConfirmationSummary` 写死 `D0-*` / `handleJumpB50()` 是 stub / ~~一码两表（已自然消歧）~~ | 七枢纽同时受益 |

**✅ 裁决门 A 已裁决 = A-否（2026-08-02 用户）**：
`银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12` / `回函情况汇编` 三张是
**hidden sheet**（`sheet_state` 实证 + `底稿目录` 只索引 9 张，两证一致）、override 已 `skip`
→ **不实现**。原标 `[Cond-A]` 的设计段落（§1 `confirmation/otherItems/`、Property 1/2/3、
`OtherItemsPayload` 数据模型）**已标作废**，正文保留为口径存档。

**最终交付范围**：
- L1 = 品种矩阵 + **E0-1 下区四块** + 银行备忘录话术 + E0-3/E0-6 → E1 受限联动 + 预设纠偏
- L2 = E0-1 列集增删（`CYCLE_EXCLUDED_COLUMNS`）+ **可靠性按渠道补 12 列**
  （**照做** —— 共享件增强，D0-7 等可见表同样受益；只是不给 E0 声明 `reliabilityCode`，
  且其注释必改，见 requirements R7.6）
- L3 = `GtConfirmationSummary` 写死 `D0-*` + `handleJumpB50()` stub
  （**一码两表已随 A-否 自然消歧** —— `wp_render_config.py` L709 的全名 `skip` 判定
  先于 L722 的尾码判定，核对表被拦在 componentType 解析之前；
  遗留的唯一约束是「全名 `skip` 条目不得删」，守卫归 send-list spec 的 Task 14）

**贯穿全局的裁决者是源 xlsx**：任何列名/枚举值/话术/矩阵指标都逐字取自
`backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx`，
守卫用 openpyxl 直读比对。源模板自身的缺陷（`回函情况汇编` O 列 `#REF!`、
E0-2 AA 列把跟函索引写成 `E0-3`、`F1-12` 索引贴错）**按意图实现 + 在 Notes 记录**，
不照抄坏公式、也不"修正"源模板。

## Architecture

### 数据流（新增/修正的边用 ★ 标注）

```
底稿目录 ─────────────────────────────► 各表表头（既有）

E1-3 银行存款明细 ──► E0-3 货币资金发函记录 ─┐★ 账号→E列 键=银行账号，金额=账户余额（原币）
                     E0-4 借款发函记录  ─────┤★ 品种优先读「所属科目」（非「借款类型」）
                     E0-5 应付银行承兑汇票 ──┤★ 金额取「票面金额」；**源表无「是否函证」列**
                     E0-6 理财产品 ──────────┘★ 金额取「产品净值」；**源表无「是否函证」列**
                              │                  单位=开户行名称及收件人，账号位=产品名称
                              ▼ importE0ListsToSummary（per-list 规格；只对有该列的清单筛 是否函证=是）
                                ★ 必填 account_no（E0-1 E 列是源公式匹配键）
                                ★ 去重键含 account_no（否则同行多产品/多账号被丢）
E0-2 核实被函证单位 ──► E0-1 函证结果汇总表
                              │  ★ 补 4 列：抵押质押说明/其他事项相符/不符说明/行级结论
                              │  ★ 剔 4 列：替代程序（源模板在「回函情况汇编」）
                              │  ★ 下区 6品种×6指标矩阵（账面金额从四表预填）
                              │
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
★ 银行函证其他信息核对表E0-5   F1-12 回函可靠性      E0-8 舞弊风险
  13 要项 × 相符/不符          ★ 按渠道补 12 列       ★ handleJumpB50 实装
  异常项派生拼接                                      → B50
        │
        └──► E0-1「其他函证事项回函是否相符」（按索引号取 回函是否异常）

★ E0-3「是否存在冻结、担保或其他使用限制」=是 ──► E1 ②表 受限制的货币资金明细
★ E0-6「是否被用于担保或存在其他使用限制」=是 ─┘（单向、手工优先、确认预览）
                                                  E0-6 侧落点按核算科目由用户点选：
                                                  其他货币资金→E1②表 / 交易性金融资产等→受限资产附注段

E0-7 跟函过程控制 ★ 银行专属五段话术 + 工号 + 公示制度核对
```

### 分层落点

- **13 要项表**：新建 `confirmation/otherItems/`（组件 + 类型 + 纯函数派生），
  componentType 取名 `confirmation-other-items`，只在 E0 启用
- **列集增删**：`confirmationColumnSpec.ts` 加 `CYCLE_EXCLUDED_COLUMNS` + 4 个 E0 variant 列
- **品种矩阵**：纯函数 `e0SummaryMatrix.ts`（`ConfirmationRow[] → 6×6`），
  组件只渲染；账面金额由 render 侧四表预填注入
- **可靠性补列**：`reliabilityTypes.ts` additive 加字段 + `ReliabilityGrid` 按渠道折叠
- **备忘录**：`memoTemplates.ts` 由「单套常量」改为「按循环取模板集」

## Components and Interfaces

### 0. `e0SummaryLowerZone.ts` + `E0SummaryLowerZone.vue`（新建，E0-1 下区四块）

逐格实证 E0-1 下区（`dims=A1:AI54`）共**四块**，第二版只写了矩阵一块
（首轮 dump 只取 A..L 列，漏掉 O/V 列）：

| 块 | 锚点 | 形态 |
|---|---|---|
| 一、函证情况 | `C27` | 6 品种 × 6 指标矩阵（见 §3） |
| 二、样本选择 | `O27` | 3 段固定说明（`O28` / `O29` / `O30+O31` 合并）+ 「未函证账户的理由」录入 |
| 三、审计说明 | `V27` | 3 条小标题（`V28` / `V30` / `V32+V33` 合并），各自独立录入 + AI |
| 四、审计结论 | `V34` | 单一结论录入 + AI |
| 提示 | `A37` + `A38`（合并 `A38:N38`） | 4 条，只读方法论上下文（琥珀色左边线） |

```ts
/** 源模板固定文字的单一真源；label/text 逐字，anchor 供守卫三向比对 */
export interface E0LowerZoneText {
  block: 'sample_selection' | 'audit_note' | 'conclusion' | 'tips'
  key: string
  /** 逐字源模板文字；跨两行的已在此合并（源模板把一句话拆成两格） */
  text: string
  /** 源模板锚点，多格合并时用 '+' 连接，如 'O30+O31' */
  anchor: string
  /** true = 只读方法论上下文；false = 该段下方有录入位置 */
  readonly: boolean
}
export const E0_LOWER_ZONE_TEXTS: readonly E0LowerZoneText[]
```

**两处「一句话被源模板拆成两格」必须合并渲染**（否则界面出现半句话）：
- `O30 审计准则规定的可以不执行银行函证程序的理由是：银行存款、借款及与金融机构`
  + `O31 往来的其他重要信息对财务报表不重要且与之相关的重大错报风险很低。`
- `V32 3.如果银行回函中存在未函证的其他信息（如XX账号未包含在本函证证中，具体信息另函回复等），应考虑`
  + `V33 未函证信息的影响，并考虑实施进一步审计程序`

`V32` 的 `本函证证` 是源模板笔误，**原样保留**（守卫按原文断言，防将来被"顺手修正"后
与源 xlsx 三向比对打红）。

**与 send-list spec 的分工（R3.9）**：`O28` 逐字「所有银行账户全部函证（包括零余额账户和
在本期内注销的账户）。」是 send-list 的 R16（E0-3 函证范围完整性红线）的**第二处源模板依据**
（第一处是 `函证程序表E0A` 程序 1 同款措辞）。
本 spec 只做**说明文字展示 + 未函证理由录入位置**；
「零余额/注销账户是否漏函」的**逐账户校验**归 send-list 的 `sendListScopeChecks.ts`。
守卫加源码级反向断言：本 spec 新增文件里 SHALL NOT 出现零余额/注销账户的判定逻辑
（防两侧各造一份 → 结论打架时无法裁决谁对）。

### 1. ~~`confirmation/otherItems/`（新建，13 要项）~~ —— **已作废（裁决门 A = A-否）**

> 不实现。以下接口设计**保留为存档**：13 要项的 key/label/colRef 与 D7/E7 派生公式口径
> 已逐格核实，将来另立 spec 时可直接取用。

```ts
/** 13 个询证函条款要项 —— key 与 label 均逐字取自源模板 F6:R6 */
export interface OtherItemDef {
  key: string          // 稳定键（不用 label，label 含中文标点易漂移）
  label: string        // 逐字源模板列名，含序号前缀（如 '6.（1）对外担保'）
  colRef: string       // 源模板列号（如 'I'），供守卫三向比对
  /** 该要项若不符，通常牵连哪个循环（供跨底稿提示；null = 仅本循环） */
  relatedCycle: string | null
}

export const OTHER_ITEM_DEFS: readonly OtherItemDef[]  // 13 条，顺序 = 源模板列序

export type ItemMatch = '回函相符' | '回函不符' | ''
export type ReplyStatus = '' | '回函相符' | '回函不符' | '无法判断' | '未回函' | '退函' | '待确认'

export interface OtherItemsRow {
  _row_id?: string
  seq?: number
  confirm_index?: string     // B 列 索引号，与 E0-1 主键同源
  reply_status?: ReplyStatus // C 列 回函情况
  items?: Record<string, ItemMatch>   // 13 要项
  mismatch_reason?: string   // S 列 回函不符原因
  ref_index?: string         // T 列 相关资料索引号
}

/** D 列派生（源模板 D7 公式的纯函数版） */
export function deriveAbnormal(row: OtherItemsRow): '是' | '否'
/** E 列派生（源模板 E7 公式：拼接全部不符要项 label，按列序） */
export function deriveAbnormalItems(row: OtherItemsRow): string
```

**为什么不复用 `confirmation-diff-*`**：那一族管的是**金额差异调节**（账面 vs 回函 → 差异原因 → 调整分录），
而 13 要项是**非金额的相符性清单**，字段形态、派生逻辑、审计意义都不同。

### 2. `confirmationColumnSpec.ts`（扩展）

```ts
/** 枢纽 → 需从 BASE 剔除的列 key（源模板没有该列 → 空列噪声） */
export const CYCLE_EXCLUDED_COLUMNS: Record<ConfirmCycle, string[]> = {
  D0: [], E0: ['use_alternative', 'alt_confirmed', 'alt_unconfirmed', 'alt_ref_index',
               'sample_purpose', 'contact_person', 'contact_phone', 'remark'],
  F0: [], G0: [], H0: [], K0: [], L0: [],
}
```

E0 新增 variant 列（`group` 用新增的 `row_summary`，对应源模板主表尾部四列）：

| key | label（逐字源模板） | 列号 | kind |
|---|---|---|---|
| `pledge_note` | 抵押质押等事项回函说明 | Z | text |
| `other_items_match` | 其他函证事项回函是否相符 | AA | select |
| `mismatch_note` | 函证不符事项说明 | AB | text |
| `row_conclusion` | 审计结论 | AD | text |

`row_conclusion` 已存在于 `VARIANT_COLUMN_DEFS`（K0/L0 用），E0 复用同一 key
但 `group` 需允许按枢纽覆盖 —— 用 `variantOverrides` 而不是复制一份定义。

`resolveConfirmationColumns(cycle)` 改为 `BASE − EXCLUDED ∪ VARIANT`，
七枢纽零回归凭据：`EXCLUDED` 除 E0 外全为空数组 → 结果逐字节不变（守卫用 golden 比对）。

### 3. `e0SummaryMatrix.ts`（新建，纯函数）

```ts
export const E0_MATRIX_CATEGORIES = [
  '银行存款', '其他货币资金', '短期借款', '长期借款', '应付票据', '理财产品',
] as const   // 源模板 E28:J28

export const E0_MATRIX_METRICS = [
  '本期（期末）账面金额', '抽取样本的发函金额', '发函金额占账面金额的比例(%)',
  '回函确认金额', '回函可确认金额占发函金额的比例(%)', '回函可确认金额占账面金额的比例(%)',
] as const   // 源模板 C29:C34

export interface E0MatrixInput {
  rows: readonly ConfirmationRow[]
  /** 账面金额（四表预填或手填），缺省 undefined ≠ 0 */
  bookAmounts?: Partial<Record<E0Category, number>>
}
export function buildE0SummaryMatrix(input: E0MatrixInput): E0MatrixCell[][]
```

- 发函金额 = `Σ amount_orig`（按 `account_type` 分组），对齐 `SUMIF(D:D,品种,F:F)`
- 回函确认 = `Σ confirmed_amount_orig`，对齐 `SUMIF(D:D,品种,X:X)`
- 比例分母 0 → 0（对齐 `ISERROR` 兜底），**绝不产出 NaN/Infinity**
- `bookAmounts` 未提供的品种：比例列返回 `null`（渲染成「—」），**不填 0 冒充**

账面金额取数口径（render 侧注入，取不到就留空）：

| 品种 | 报表行 / 科目 |
|---|---|
| 银行存款 | `TB('1002','期末余额')` |
| 其他货币资金 | `TB('1012','期末余额')` |
| 短期借款 | `TB('2001','期末余额')` |
| 长期借款 | `TB('2501','期末余额')` + 一年内到期部分（口径待 render 侧实证） |
| 应付票据 | `TB('2201','期末余额')` |
| 理财产品 | **无固定科目**（可能在交易性金融资产/其他流动资产）→ 不预填 |

### 4. `memoTemplates.ts`（改为按循环）

```ts
export type MemoScenario =
  | 'immediate' | 'later_follow' | 'later_received'      // 既有（通用）
  | 'bank_counter' | 'bank_department' | 'bank_leave'
  | 'bank_all_responded' | 'bank_later_received'          // E0 新增

export function getTemplate(
  scenario: MemoScenario, opts?: { cycle?: ConfirmationCycle; laterReceived?: boolean },
): string
export function scenariosFor(cycle: ConfirmationCycle): MemoScenario[]
```

E0 五段话术逐字取自源模板 A8/A10/A12/A14/A15，占位统一 `〔xxx〕`
（与既有 `IMMEDIATE_CONFIRM_TPL` 同款），新增占位：
`bank_staff_name` / `bank_staff_no` / `bank_reviewer_name` / `bank_reviewer_no` /
`bank_department` / `gt_office`。

**零回归**：`getTemplate('immediate')` 不传 cycle 时行为逐字不变。

### 5. `reliabilityTypes.ts`（additive 补列）

按源模板 F1-12 的渠道分组补 12 个字段（全部 optional）：

| 渠道 | 新字段 | 源模板列 |
|---|---|---|
| 通用 | `signed_by_both` | D 回函是否分别由经办人和复核人签名 |
| 通用 | `signer_in_public_list` | E 签字人员是否与银行公示名单相符 |
| 邮寄 | `envelope_addr_match` | H 回函信封上名称、地址是否一致 |
| 邮寄 | `postmark_city_match` | I 邮戳显示发出城市或地区是否一致 |
| 邮寄 | `reply_info_complete` | J 回函信息是否完整 |
| 跟函 | `followup_flow_known` | K 是否了解处理函证的通常流程和处理人员 |
| 跟函 | `followup_identity_verified` | L 是否确认询证函处理人员的身份及权限 |
| 跟函 | `followup_normal_process` | M 处理人员是否按正常流程处理 |
| 电子平台 | `esign_match` | N 电子签名信息是否一致 |
| 电子平台 | `ip_match` | O 回函的 IP 地址是否一致 |
| 电子平台 | `platform_op_time` | Q 电子函证平台操作时间 |
| 电子平台 | `platform_feedback` | S 意见反馈（如适用） |

`ReliabilityGrid` 按 `reply_method` 只展开对应渠道列组，其余折叠。
`_format` 保持 `'reliability-v1'`（additive 不升版本），旧载荷读出来新字段为 `undefined`。

### 6. `e0RestrictedToE1.ts`（新建，E0-3 → E1 受限联动）

```ts
export interface E0RestrictedCandidate {
  accountNo: string      // E0-3 G 列 银行账号
  bankName: string       // D 列 开户银行
  amount: number         // K 列 账户余额（原币）
  reason: string         // O 列 是否存在冻结、担保或其他使用限制（如是，请注明）
  confirmIndex?: string  // B 列 索引号
}
export function collectE0Restricted(e03Rows: any[]): E0RestrictedCandidate[]
export function planE1RestrictedMerge(
  candidates: readonly E0RestrictedCandidate[],
  existing: readonly E1RestrictedRowLike[],
): { additions: ...; conflicts: ...; skipped: ... }
```

复用本会话已建的 `composables/shared/adjudicationPrefillPlan.ts` 的
plan → resolve → describe 三段式语义（手工优先 / 幂等 / 冲突弹确认）。
**单向**：只从 E0-3 读、只往 E1 写，不反向。

### 7. `GtConfirmationSummary.vue` / `GtConfirmationFraudRisk.vue`（修平台缺陷）

- `CROSS_REF_RULES` 常量删除，改 `computed(() => buildCrossRefRules(props.wpCode))`
- `handleJumpB50()` 实装：复用平台既有底稿跳转（按 `wp_code='B50'` 解析 workpaper id），
  查不到给 `ElMessage.warning`；有"已识别未应对"迹象时先 `ElMessageBox.confirm`

## Data Models

### ~~`OtherItemsPayload`（新表持久化）~~ —— **已作废（裁决门 A = A-否），保留为存档**

```ts
export interface OtherItemsPayload {
  _format: 'other-items-v1'
  rows: OtherItemsRow[]
  audit_note?: string        // 源模板 A15 审计说明
  conclusion?: string        // 源模板 A18 审计结论
}
```

`items` 用 `Record<key, ItemMatch>` 而不是 13 个平铺字段：要项清单是源模板驱动的，
将来源模板改条款号时只改 `OTHER_ITEM_DEFS`，行数据不迁移。

### `E0MatrixCell`

```ts
export interface E0MatrixCell {
  category: E0Category
  metric: E0Metric
  /** null = 无法计算（账面金额缺）→ 渲染「—」 */
  value: number | null
  /** 'ratio' 时渲染百分比 */
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅「本期（期末）账面金额」行） */
  editable: boolean
  /** 取数口径说明（溯源 tooltip） */
  sourceHint?: string
}
```

### `E0ListSpec`（发函清单 → E0-1 的 per-list 字段映射，单一真源）

四张发函记录表**不同构**（列集、有无「是否函证」、汇总匹配键三者都不同），
原实现用一份共用候选表 `AMOUNT_KEYS`/`ENTITY_KEYS` 覆盖四张 = 结构性错误。
改为声明式 per-list 规格，`buildSummaryRowsFromListRows` 只做通用编排：

```ts
export interface E0ListSpec {
  /** 默认品种；仅当源表无「所属科目」列时才作为唯一来源 */
  defaultAccountType: string
  /** 品种列（有则优先读，无则用 defaultAccountType） */
  accountTypeKeys?: string[]
  /** 品种启发式兜底列（如 E0-3 的「账户类型」）+ 判别正则 */
  accountTypeHeuristic?: { keys: string[]; test: RegExp; then: string }
  /** 被询证单位名称列 */
  entityKeys: string[]
  /** E0-1 E 列「账号/理财产品名称」的来源列 —— 源公式匹配键，不可省 */
  accountNoKeys: string[]
  /** 发函金额列（总额口径） */
  amountKeys: string[]
  /** 「是否函证」过滤列；undefined = 源表无此列 → 入表即发函，不过滤 */
  confirmFlagKeys?: string[]
}
```

| 清单 | defaultAccountType | accountTypeKeys | entityKeys | accountNoKeys | amountKeys | confirmFlagKeys |
|---|---|---|---|---|---|---|
| E0-3 | `银行存款` | `所属科目` | `开户银行` | `银行账号` | `账户余额（原币）` | `是否函证` |
| E0-4 | `短期借款` | `所属科目`,`借款类型` | `借款人名称`,`开户银行` | `借款账号` | `余额` | `是否函证` |
| E0-5 | `应付票据` | —（源表无） | `开户银行` | `银行承兑汇票号码` | `票面金额` | **—（源表无）** |
| E0-6 | `理财产品` | —（源表无） | `开户行名称及收件人` | `产品名称` | `产品净值` | **—（源表无）** |

三条钉死点：

1. **E0-5/E0-6 的 `confirmFlagKeys` 必须为 `undefined`** —— 源模板这两张表没有「是否函证」列，
   继续过滤 = 两品种恒 0 候选。这是「自造 fixture 与错误假设同构」的典型：
   单测里手搓一行带 `是否函证:'是'` 就能过，真实模板行必然被滤掉
   → 守卫必须**从源 xlsx 抽真实表头**再构造用例（openpyxl 直读，不手写 fixture）
2. **E0-6 的 `amountKeys` 只含 `产品净值`** —— 不含 `持有份额`，也不做 `份额 × 净值`。
   源模板 E0-1 F 列直接 `SUMIFS(E0-6!$H:$H,…)`，与 E0-3 的 `账户余额（原币）`、
   E0-4 的 `余额`、E0-5 的 `票面金额` 同为总额口径列。守卫加反向断言防后续"优化"成乘积
3. **E0-6 的 `entityKeys` 不含 `产品名称`** —— 原 `ENTITY_KEYS` 里 `产品名称` 排在
   `开户行名称及收件人` 之前（后者压根不在候选表里）→ 被询证单位被填成产品名称。
   源模板契约：被询证单位 = 银行（E0-1 C 由 E0-2 VLOOKUP 得），产品名称 → E0-1 E 列

### `dedupeSummaryRows` 去重键（修正）

键 SHALL 为 `entity_name || account_type || account_no`（三元组）。
旧二元键 `entity_name || account_type` 在「同一家银行多只理财产品 / 多个银行账号」时
把第 2..N 行判为重复**静默丢弃**；源模板的匹配键本身就是二元组
（E0-6 = 索引号 + 产品名称，E0-3 = 银行账号）→ 去重键必须含账号位。

### `confirmation-wealth-list`（E0-6 专属组件，已落地）

**🔴 与 `e0-send-list-dedicated-components` 的互斥裁决（2026-08-02 定论）**：
那份 spec 原计划把四张发函清单统一命名为 `confirmation-send-list-e03/e04/e05/e06`。
E0-6 那一条**已撤回** —— 本 spec 的 wealth-list 先落地且带完整契约测试
（`test_confirmation_sheet_override_contract.py` 硬断言 `E0-6` 与
`理财产品发函记录表E0-6` 两个 override 键都必须是 `confirmation-wealth-list`）。
故最终形态是**三 + 一**：send-list spec 只做 E0-3/E0-4/E0-5 三个专属 componentType，
E0-6 保留 wealth-list，那边改为「符合度核查」（其 Task 17：11 列真源 / `_format` /
`WpAmountInput` 只用于金额列 / 合计行按 `column.property` / 看板指标不臆造，共 8 项）。

**为什么不为了"命名一致"而统一**：改名要付三笔代价 ——
① 改上述硬断言契约；② `_format` 由 `wealth-list-v1` 换 `send-list-e06-v1`
（E0-6 的 legacy 载荷会被迁移两次）；③ 删 `confirmation/wealthList/` 七件套并重写。
收益仅"命名整齐"，不值。**命名不一致这件事本身要在两份 spec 的 Glossary 里写明**，
否则下一个会话会再提一次统一。

用户裁决（2026-08-02）：E0-6 走通用 `d-form-table` **太丑**，要按 D0 函证家族的专属 HTML 形态打磨。
分层完全对齐 `confirmation/reliability/`（D0-7）这一既有范式：

```
confirmation/wealthList/
├─ GtConfirmationWealthList.vue   宿主：旧格式降级只读 / 看板+网格+结论 / 导入导出 / defineExpose
├─ WealthListDashboard.vue        看板：7 张指标卡 + 质量告警条
├─ WealthListGrid.vue             11 列网格：点选 + WpAmountInput + 派生状态列 + 合计行
├─ WealthListConclusion.vue       审计说明 3 段 + 结论三选一 + 按表内数据生成草稿
├─ wealthListTypes.ts             行/指标/说明/结论/payload + WEALTH_LIST_COLUMN_SOURCE（列真源）
├─ wealthListEnums.ts             产品类型 / 是否受限 / 币种建议 / 结论枚举
└─ composables/useWealthListData.ts  CRUD + 指标 + 行质量（纯函数全部单独导出供单测）
```

**注册五处**（缺一即静默失效）：

| 位置 | 内容 |
|---|---|
| `htmlRendererRegistry.ts` | 联合类型 + `defineAsyncComponent` + registry 条目（icon 💰） |
| `wp_render_config_helpers._CONFIRMATION_FORMAT_MAP` | `confirmation-wealth-list` → `wealth-list-v1` |
| `wp_render_config._CONFIRMATION_COMPONENTS` | 加入集合（否则被重写成 `onlyoffice-sheet`） |
| `wp_classification_service` 专属类型清单 | 加入 |
| `wp_code_overrides.json` | **两处**：编码尾码 `E0-6` + **sheet_name `理财产品发函记录表E0-6`** |

**🔴 sheet_name override 优先于编码尾码**（同 D0-7 范式）→ 只改编码那一处会被
`"理财产品发函记录表E0-6": "d-form-table"` 静默遮蔽。守卫
`test_e06_both_override_paths_point_to_dedicated` 同时钉死两处。

**看板指标的审计意图**（都由源模板可判定，不臆造）：

| 指标 | 判据 | 为什么值得单独立一张卡 |
|---|---|---|
| 发函金额合计 | Σ `产品净值` | 这就是汇入 E0-1 F 列的数，与 E0-1 对不上即有问题 |
| **汇总键缺失** | 缺 `索引号` 或 `产品名称` | 源 `SUMIFS` 的两个 criteria，缺一则该笔在 E0-1 显示 0 —— **最隐蔽的错**，通用表格永远看不出来 |
| 受限笔数 / 金额 | `是否被用于担保…` = 是 | 直接指向 E1 受限资金 / 受限资产附注段 |
| 期末已到期 | `到期日` ≤ `报表截止日` | 已到期仍列示 → 应终止确认 |
| 封闭式 / 开放式 | `产品类型` | 开放式期后可赎回，影响现金等价物判断 |

**行质量三态**：汇总键缺失 = danger（红底行 + 输入框红框 + 状态列「键缺失」tag）；
已到期或金额为 0 = warning；全空白新行不打警示（避免刚点新增就一片红）。

**合计行按 `column.property` 判别**，不按 label/width —— 产品净值列用自定义 `#header`
插槽（要挂口径 tooltip），`label` 为空，靠 width 判别会在改列宽时静默失效。

### `functional_type` 迁移

四张发函记录表（`货币资金发函记录表E0-3` / `借款发函记录表E0-4` /
`应付银行承兑汇票发函记录表E0-5` / `理财产品发函记录表E0-6`）
→ 结论待 Task 1 核实；若适用则幂等迁移 `UPDATE ... WHERE wp_code IN (...) AND functional_type IS NULL`。

## Correctness Properties

> **裁决门 A = A-否（2026-08-02 用户）** → **Property 1 / 2 / 3 已作废，不实现守卫**。
> 明确记一条：**SHALL NOT 用 `@pytest.mark.skip` / `it.skip` 让这三条先绿** ——
> 绿色守卫会被下个会话当成"已实现"的证据。不写就是不写。
>
> 新增一条**无条件**守卫 Property 28（替代原来靠 Property 1~3 覆盖的那部分风险面）：
> 隐藏底稿的 `skip` 状态本身必须被钉死，否则某天有人删掉 `skip` 条目，
> 这三张表会以错误的 componentType 悄悄出现在页签上。

### Property 1: ~~13 要项定义与源模板逐字一致~~ —— **已作废（A-否），不实现**
`OTHER_ITEM_DEFS` 的 13 条 `label` 与 `colRef` SHALL 逐字命中源 xlsx
`银行函证其他信息核对表E0-5` 的 F6:R6，顺序相同。

**Validates: Requirements 1.1, 12.1**

### Property 2: ~~异常项派生与源模板公式等价~~ —— **已作废（A-否），不实现**
对任意 `OtherItemsRow`，`deriveAbnormal` / `deriveAbnormalItems` 的输出 SHALL 与源模板
D7/E7 公式在相同输入下一致（含三种回函情况短路、拼接顺序、`无异常` 兜底）。

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 3: ~~派生列只读（13 要项表）~~ —— **已作废（A-否），不实现**
`回函是否异常` 与 `异常项目` SHALL 不出现在任何可编辑控件里。
（注：**「派生列只读」这条原则本身仍然有效**，由 Property 7（品种矩阵只读边界）
与 Property 25（E0-6 行质量）承载，只是不再适用于这张不实现的表。）

**Validates: Requirements 1.6**

### Property 4: E0-1 列集与源模板等值
E0 的列集 SHALL 包含四个新增列、SHALL NOT 包含替代程序四列，
且列集与源 xlsx E0-1 的 30 列（去掉纯表头装饰列）SHALL 一一对应。

**Validates: Requirements 2.1, 2.2, 2.5, 2.6**

### Property 5: 列集剔除机制的零回归
对 D0/F0/G0/H0/K0/L0，`resolveConfirmationColumns(cycle)` 的输出 SHALL 与引入
`CYCLE_EXCLUDED_COLUMNS` 之前逐字节相同（golden 比对）。

**Validates: Requirements 2.3, 2.4**

### Property 6: 品种矩阵的求和与比例
`buildE0SummaryMatrix` SHALL 满足：按品种求和 = 主表同品种行之和；
分母为 0 时比例为 0；`bookAmounts` 缺该品种时比例为 `null`；
输出中 SHALL NOT 出现 `NaN` / `Infinity`。

**Validates: Requirements 3.2, 3.3, 3.4, 3.5**

### Property 7: 矩阵只读边界
除「本期（期末）账面金额」行外，全部单元 `editable` SHALL 为 `false`。

**Validates: Requirements 3.6**

### Property 8: 跨表引用无写死 D0
`confirmation/**` 的共享组件源码（`stripComments` 后）SHALL NOT 含写死的 `D0-` sheet 编码；
`buildCrossRefRules('E0-1')` 的输出 SHALL NOT 含 `D0-`，且 SHALL NOT 含 E0 为 null 的表。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 9: 发函清单带入的品种与金额
对四张清单的代表性行，`buildSummaryRowsFromListRows` SHALL 产出：
E0-5 金额 = 票面金额；E0-6 金额 = 产品净值（**非** 持有份额 × 产品净值）；
E0-4 品种优先按「所属科目」分流、其次「借款类型」、皆缺时回退并标注；
E0-5 命中核对表时产出空。

**Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6**

### Property 18: 「是否函证」过滤只作用于有该列的清单
用**源 xlsx 真实表头**构造的 E0-5 / E0-6 行（不含「是否函证」键）
SHALL 产出非空候选；E0-3 / E0-4 的行在该列非「是」时 SHALL 被跳过。
反向自检：给 E0-6 spec 加上 `confirmFlagKeys` 后该品种候选数 SHALL 归零。

**Validates: Requirements 5.7**

### Property 19: `account_no` 必填且按清单取对列
四张清单的产出行 SHALL 均带非空 `account_no`，取值分别来自
`银行账号` / `借款账号` / `银行承兑汇票号码` / `产品名称`；
E0-6 的 `entity_name` SHALL 是 `开户行名称及收件人` 且 SHALL NOT 等于 `产品名称`。

**Validates: Requirements 5.8, 5.9**

### Property 20: 去重不丢同银行多账号/多产品
对「同一 `entity_name` + 同一 `account_type` + 不同 `account_no`」的 N 行，
`dedupeSummaryRows` SHALL 保留 N 行；
反向自检：退回二元键 SHALL 只剩 1 行（证明三元键必要）。

**Validates: Requirements 5.10**

### Property 21: E0-6 列集与录入形态逐字对齐源模板
`理财产品发函记录表E0-6` 的 11 列 label SHALL 逐字命中源 xlsx 第 5 行 A5:K5；
`是否被用于担保或存在其他使用限制` SHALL 为整数据区可选「是/否」；
`产品类型（封闭式/开放式）` SHALL 为点选；
SHALL NOT 出现合计行或两级表头（源模板均无）。

**Validates: Requirements 8.1, 8.8, 8.9, 8.10**

### Property 23: E0-6 专属组件的注册完整性与列真源
`confirmation-wealth-list` SHALL 出现在前端 registry、两个后端集合、format map，
且 `wp_code_overrides` 的**编码尾码与 sheet_name 两处**同时指向它；
`WEALTH_LIST_COLUMN_SOURCE` 的 11 条 label SHALL 逐字命中源 xlsx `A5:K5`，
`field` 唯一，且 SHALL NOT 含「是否函证」。

**Validates: Requirements 8.1, 8.8, 8.11**

### Property 24: E0-6 指标口径与数值安全
`buildWealthListMetrics` SHALL 满足：`net_value_total` = Σ`产品净值`（**不等于** Σ(份额×净值)）；
`restricted_amount` = 受限行金额之和；各计数 ∈ [0, 行数]；
任意输入下输出 SHALL NOT 含 `NaN` / `Infinity`（含 PBT）。

**Validates: Requirements 8.12, 8.15, 8.16**

### Property 25: E0-6 行质量三态判据
汇总键缺失 → `danger`；键完整但已到期或金额为 0 → `warning`；全空白行 → `ok`；
`isMatured` 在 `到期日` 或 `报表截止日` 任一为空时 SHALL 返回 false（不猜测）。

**Validates: Requirements 8.13, 8.14**

### Property 22: 受限来源覆盖两列且落点由用户裁决
受限来源枚举 SHALL 同时含 `E0-3·是否存在冻结、担保或其他使用限制（如是，请注明）`
与 `E0-6·是否被用于担保或存在其他使用限制`；
E0-6 受限行在未指定核算科目归属前 SHALL NOT 自动写入任一落点。

**Validates: Requirements 9.7, 9.8**

### Property 10: 备忘录话术按循环且零回归
`scenariosFor('E0')` SHALL 返回五个 bank_* 场景；
`getTemplate('immediate')` 在不传 cycle 时 SHALL 与改造前逐字相同；
E0 话术 SHALL 含「工号」与「公示内容一致」两处断言。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 11: 可靠性补列的向后兼容（**无条件** —— 共享件增强）
旧 `reliability-v1` 载荷经新模型读写一次 SHALL 逐字节不变（新字段不写入 `undefined` 键）；
`reply_method` 已知时 SHALL 只展开该渠道列组。
A-否时本 Property 仍然生效（D0-7 等可见的可靠性表同样受益），
只是 `cycleConfirmationMeta.E0.reliabilityCode` 保持 `null`
且其注释 SHALL 改为「源模板有 F1-12，但为 hidden sheet 且 override 置 skip，故不启用」
（现注释「E0 无回函可靠性验证 sheet」是**错的**，A-是/A-否两种裁决下都必须改）。

**Validates: Requirements 7.2, 7.3, 7.4**

### Property 26: E0-1 下区四块齐备且固定文字逐字（含两处跨格合并）
E0-1 下区渲染 SHALL 同时呈现 `一、函证情况` / `二、样本选择` / `三、审计说明` /
`四、审计结论` 四块与 `提示` 区；
`E0_LOWER_ZONE_TEXTS` 的每条 `text` SHALL 逐字命中源 xlsx 对应 `anchor` 的单元格值
（`anchor` 含 `+` 的按顺序拼接后比对）；
`V32` 的源模板笔误 `本函证证` SHALL 原样保留。
**反向自检**：把 `O30+O31` 拆回两条独立文本 SHALL 打红（证明合并是必要约束）。

**Validates: Requirements 3.7, 3.8, 3.10, 3.11, 12.1**

### Property 28: 隐藏底稿的 `skip` 与 meta 不可漂移（A-否 的执行性保障）
`sheet_state` 为 `hidden` 的 E0 sheet SHALL 在 `wp_code_overrides` 里为 `skip`
（判据以 openpyxl 直读为准，非硬编码清单）；
`银行函证其他信息核对表E0-5` 的**完整 sheet_name** `skip` 条目 SHALL 存在
（**不能只依赖尾码 `E0-5`** —— `wp_render_config.py` 的 componentType 解析在 L749 是
**尾码优先**，一旦全名条目被删，该 hidden sheet 会被解析成 `应付银行承兑汇票发函记录表E0-5`
的 componentType 并渲染出一个列集完全不符的多余页签）；
override 里 `skip` 的 sheet 集合 ∩ 任一 `cycleConfirmationMeta` 的非 null code = ∅。
**反向自检**：把全名 `skip` 条目改成任意 componentType SHALL 打红；
把 `E0.reliabilityCode` 填成 `邮件传真回函核对记录F1-12` SHALL 打红。

**Validates: Requirements 7.5, 7.6, 8.4, 8.5, 12.3**

### Property 27: 完整性判定逻辑不双写
本 spec 新增文件（`e0SummaryLowerZone.*` / `E0SummaryLowerZone.vue`）源码
（`stripComments()` 后）SHALL NOT 含零余额/注销账户的逐账户判定逻辑
（`零余额` / `注销` 作为**判定条件**出现；作为源模板固定文字常量的一部分是允许的
→ 判据 = 是否出现在 `if`/`filter`/`some` 等表达式里）；
「二、样本选择」块 SHALL 提供「未函证账户的理由」录入位置且该位置非只读。
**反向自检**：把校验逻辑复制进本 spec 的文件 SHALL 打红。

**Validates: Requirements 3.9**

### Property 12: meta ↔ override 交叉锁死
对 7 个循环，meta 的每个非 null code SHALL 在 override 表有映射；
meta 为 `null` 的 SHALL NOT 要求映射；临时删掉 `E0-7` 映射守卫 SHALL 失败（反向自检）。
**补一条无条件断言**：override 里被置 `skip` 的 sheet SHALL NOT 出现在任何 meta 的非 null code
（否则 meta 声称有那张表、渲染层却 skip 掉 = 静默失效）；
该断言使 A-否裁决在守卫层可执行（`reliabilityCode` 若被填成 F1-12 会立刻打红）。

**Validates: Requirements 6.6, 6.7, 8.1, 8.2, 12.3**

### Property 13: E0-3 → E1 受限联动的手工优先与单向
E1 侧已有同账号行 SHALL NOT 被静默覆盖（进 `conflicts`）；
E0-3 无受限行 SHALL 产出空 `additions`；联动 SHALL NOT 产生任何对 E0-3 的写入。

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

### Property 14: B50 跳转不再是 stub
`handleJumpB50` 的函数体（`stripComments` 后）SHALL NOT 只含 `console.log`，
SHALL 含真实导航调用；查不到 B50 时 SHALL 有可见提示。

**Validates: Requirements 10.1, 10.2, 10.4**

### Property 15: 公式预设指向真实 tab
E0 预设块的 `sheet` 与 `wp_name` SHALL 逐字命中源 xlsx 的某个 tab 名；
纠偏脚本 `--check` SHALL 输出 0 项欠账且重复运行幂等。

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 16: sheet 名逐字（含易错字）
守卫引用的 sheet 名 SHALL 是真实 tab 名：`银行函证其他信息核对表E0-5`（**无**「询证」）、
`跟函函证过程控制E0-7`（**两个**「函」）、`附注`类不涉及。

**Validates: Requirements 12.2**

### Property 17: functional_type 改动的定向性
迁移后，E0 循环内**只有**四张发函记录表的 `functional_type` 发生变化，
其余 sheet 逐字不变；结论为不适用时 SHALL 无任何 DB 写入。

**Validates: Requirements 11.5, 11.6, 11.7**

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 品种矩阵的 `bookAmounts` 取不到 | 该品种账面金额留空、三个比例返 `null` 渲染「—」 | 宁缺勿造，填 0 会让覆盖率显示成 0% 误导 |
| `E0-5` wp_code 命中核对表 | `importE0ListsToSummary` 该张返 0 候选 + `emptyReason` 说明，不抛 | 一码两表是源模板事实，不能因此让整个带入失败 |
| E0-4 缺「所属科目」与「借款类型」 | 回退「短期借款」并在结果里标 `fallback: true`，UI 提示 | 静默归类会让长期借款品种恒空且无人察觉 |
| E0-5/E0-6 无「是否函证」列 | 不过滤，入表即视为发函对象；结果里标 `noConfirmFlagColumn: true` 供 UI 说明 | 源模板事实；过滤即两品种整表归零 |
| 清单行缺 `account_no` | 该行仍带入但标 `missingAccountNo: true` 并提示「E0-1 发函金额将无法自动汇总」 | 账号是源公式匹配键；静默带入会让金额恒 0 且看不出原因 |
| E0-6 受限行但核算科目未知 | 进「待归属」清单让用户点选（其他货币资金 / 交易性金融资产等），不自动落任一处 | 四表推不出归属，猜测=造假 |
| E0-1 品种矩阵「本期（期末）账面金额」 | 保持手工录入 | 源模板 R29 本身无公式；理财产品在四表里无独立科目，无法干净映射 → 宁缺勿造 |
| E0-3 → E1 联动冲突 | 进 `conflicts` 弹确认（可选「仅补空值」），绝不静默覆盖 | 手工优先铁律 |
| B50 底稿不存在 / 无权限 | `ElMessage.warning` 可见提示，不跳转 | 静默失败 = 用户以为推过去了 |
| 旧 `reliability-v1` 载荷缺新字段 | 读为 `undefined`，写回不产生 `undefined` 键 | additive 兼容，避免载荷膨胀 |
| 源模板 `回函情况汇编` O 列 `#REF!` | 按意图实现（按索引号汇总 E0-3 受限金额），Notes 记录源模板缺陷 | 照抄坏公式会让该列永远报错 |
| 幂等脚本 round-trip 自检失败 | 退出非 0，不写盘 | 防全文件重排与并发会话冲突 |

## Testing Strategy

- **后端守卫** `backend/tests/test_e0_source_template_facts.py`：openpyxl 直读源 xlsx，
  钉死 13 要项列名/列号、E0-1 的 30 列、6 品种 6 指标、E0-7 五段关键词、真实 tab 名；
  含**反向自检**（把 `银行函证其他信息核对表E0-5` 写成带「询证」的名字必红）
- **后端** `test_e0_formula_presets.py`（预设 sheet/wp_name/科目）+
  `test_confirmation_meta_override_alignment.py`（7 循环交叉锁死 + 反向自检）
- **前端纯函数** `otherItemsDerive.spec.ts`（Property 2 含 PBT：随机 13 要项组合下
  `deriveAbnormal` 与「存在不符 ∨ 回函情况异常」等价）/ `e0SummaryMatrix.spec.ts`（Property 6 含 PBT）
  / `importE0Lists.spec.ts` / `memoTemplates.spec.ts` / `e0RestrictedToE1.spec.ts`
- **前端源码型守卫** `confirmationSharedNoHardcodedD0.spec.ts`（Property 8，含 `stripComments` 自检）
  / `confirmationColumnSpecGolden.spec.ts`（Property 5 golden）
- **实测**：真实项目打开 E0 各 sheet（挂载 + 无 console error + 派生列正确）；
  写库前快照、按 md5 复原
