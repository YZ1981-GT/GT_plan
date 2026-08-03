# Design Document: E0 发函清单专属 HTML 组件

## Overview

把 E0 的四张发函记录表（E0-3~E0-6）从 grid 兜底渲染改造为**专属 HTML 组件**，对齐 D0/G0/L0 函证循环既有的 `confirmation-*` 范式，并补齐源模板声明的 E1-3 → E0-3 底稿间取数。

### 三个核心设计判断

**判断 1：走 `RENDERER_DISPATCH` 而非 `_CONFIRMATION_COMPONENTS`。**
平台有两套 confirmation 组件路径：
- 旧路径 `_CONFIRMATION_COMPONENTS`（无后端 renderer，靠 `_confirmation_initial_data` 给空载荷）
- 新路径 `RENDERER_DISPATCH`（有 render 策略，如 `_l0_confirmation.py` / `_g0_confirmation.py`）

选新路径，因为本 spec 需要 render 期做两件旧路径做不到的事：**E1-3 取数注入** 与 **legacy grid 载荷迁移**。副作用正是 R2 想要的 —— `wp_render_config.py` 的分发顺序是 `renderer → onlyoffice 改写 → _CONFIRMATION_COMPONENTS 空载荷 → grid 兜底`，一旦 `renderer` 命中就直接返回，`extract_grid(data_only=True)` 永不执行，`XX银行` 示例值自动消失。

**判断 2：三个新 componentType 而非一个带 variant；E0-6 复用已落地组件不换 componentType。**
四张表列集不同构（16/16/10/11），且「是否函证」列只有两张有。平台既有 `confirmation-alternative-d05/d06/f05/f06/g06/h05/k05/k06/l05` 就是「一循环一 componentType + 共享 composable 由 config 声明差异」（`useAlternativeL05Data` 的 `AltConfig` 范式）。沿用它：三个新 componentType 各自独立 `_format`（可逐表迁移/灰度），共享一份声明式 `SendListSpec` 与一个 composable。

🔴 **E0-6 是例外（2026-08-02 复核修正，本 spec 首版基于过时基线）**：并发会话已在
`e0-confirmation-completion` Task 12.5 交付 `confirmation-wealth-list`（override 双键 +
`_CONFIRMATION_COMPONENTS` + `wealth-list-v1` + 前端 registry + `confirmation/wealthList/` +
契约测试硬断言）。新建 `confirmation-send-list-e06` 会造成同一 sheet 两个组件相争、
打红 `test_confirmation_sheet_override_contract.py`、并让 E0-6 已落库的 legacy grid 载荷
（实测项目 `1534c6e3`）被迁移两次。**裁决：E0-6 保留 `confirmation-wealth-list`，
共享引擎的复用发生在组件内部**（`GtConfirmationWealthList` 改用本 spec 的
`sendListSpec.ts` / `useSendListData.ts`），而不是换 componentType。
E0-6 也**不需要**新路径 —— 它无上游底稿取数（理财产品在平台无对应明细底稿，
不像 E0-3←E1-3 / E0-5←F3-2），且旧路径同样在 grid 兜底**之前** return。

**判断 3：金额口径做成可切换的三态，默认「未审期末」，源模板事实由守卫钉死。**
源模板 `E0-3.K ← E1-3.K = 期末对账单余额`，而 E0-3 表头写「账户余额（原币）」。这是口径分叉：发函清单在发函前编制、此时通常无对账单余额，且函证目的是验证账面余额 → 逻辑上应取未审期末（H / 外币版 M）。但也存在"先取对账单余额再发函"的作业顺序可能。**不单方面改口径**：默认未审期末、可切审定数/对账单余额、UI tooltip 明示源模板原公式指向 K，Notes 记为待用户确认。守卫只钉「源模板事实是 K」，不钉「实现必须取 K」。

### 不做的事（明确排除）

- 不改 `e0_send_list_source_manifest.json` 的 `field`/`label`（`type` 有两处已备案变更，见 tasks Notes）
- 不改 `prefill_formula_mapping.json`（归 `e0-confirmation-completion` Task 14）
- 不做 E0-3/E0-6 受限 → E1 的**写入**侧（归该 spec Task 12；本 spec 只保证数据可读 + 勾稽只读校验）
- 不做四清单 → E0-1 的带入纠偏（**该 spec Task 11 实际已落地**，见协调清单；本 spec 只保证行形态兼容）
- 不做全库 grid 兜底示例值污染的批量修复（只交付只读诊断脚本，供独立 spec 决策）
- **不新建 `confirmation-send-list-e06`**（E0-6 已有 `confirmation-wealth-list`，见判断 2）
- **不实现 E0-3 L 列「资金归集」→ 核对表「15.附表(资金归集)」的勾稽**（R17.2 —— 核对表是隐藏
  sheet 且 override 为 `skip`，落点未裁决；只做列标注 + Notes 登记）
- 不做账户完整性四方比对（四表 ∪ E1-10 央行清单 ∪ E0-3 ∪ 回函）—— R16.8，涉及新数据源，够独立 spec

## Architecture

```
┌─────────────────────────────── 源模板（唯一裁决者）────────────────────────────┐
│ E0 货币资金 - 函证（Leap应对措施-函证）.xlsx                                   │
│   ├ 货币资金发函记录表E0-3   16 列 A~P，表头 R5，数据 R6:R24，DV L/O          │
│   ├ 借款发函记录表E0-4        16 列 A~P                                       │
│   ├ 应付银行承兑汇票发函记录表E0-5  10 列 A~J（无「是否函证」）                │
│   └ 理财产品发函记录表E0-6    11 列 A~K（无「是否函证」）                      │
│ E1-1至E1-11 …审定表明细表.xlsx                                                │
│   ├ 银行存款及其他货币资金明细表(仅人民币)E1-3    段起 13/23/27                │
│   └ 银行存款及其他货币资金明细表(人民币及外币)E1-3 段起 13/19/23              │
└───────────────────────────────────┬───────────────────────────────────────────┘
        openpyxl 三向守卫           │        openpyxl 段语义守卫
                                    ▼
┌──────────────────── 后端 ───────────────────────────────────────────────────┐
│ data/e0_send_list_source_manifest.json   ← 既有真源（不改 field/label/type） │
│ data/ledger_adapters/…/generated/E0.yaml ← 既有已审定 dynamic_table（导入导出）│
│                                                                             │
│ routers/wp_render_strategies/_e0_send_list.py           ★新建               │
│   ├ render_e0_send_list_e03 / _e04 / _e05 / _e06  → RENDERER_DISPATCH        │
│   ├ _initial_data(sheet_key)          空载荷（rows: []）                    │
│   ├ migrate_legacy_grid_payload()     纯函数，列字母→field，幂等            │
│   └ build_e03_prefill()               E1-3 段语义取数（双版本分支）          │
│                                                                             │
│ services/e0_send_list/                                  ★新建               │
│   ├ send_list_specs.py    四张表列集声明（镜像 manifest，供后端守卫/取数）   │
│   └ e1_3_segments.py      E1-3 切段纯函数（段起点识别 + 明细行提取）         │
└───────────────────────────────────┬───────────────────────────────────────────┘
                    render-config    │  html_data[sheet] = {_format, rows, conclusion, _prefill}
                                     ▼
┌──────────────────── 前端 ───────────────────────────────────────────────────┐
│ components/workpaper/confirmation/e0-send-list/          ★新建               │
│   ├ sendListSpec.ts          声明式列 spec（唯一前端真源，与后端交叉锁死）   │
│   ├ useSendListData.ts       共享引擎：行 CRUD / 载荷构建 / legacy 兼容      │
│   ├ sendListPrefillPlan.ts   E1-3 带入（委托 shared/adjudicationPrefillPlan）│
│   ├ sendListConsistency.ts   受限勾稽（E1-3 受限金额 ↔ has_restriction）     │
│   ├ SendListTable.vue        共用表格（列显隐/枚举点选/WpAmountInput）       │
│   ├ SendListPrefillPanel.vue 带入预览 + 口径选择器                          │
│   ├ GtE0SendListE03.vue  GtE0SendListE04.vue                                │
│   └ GtE0SendListE05.vue  GtE0SendListE06.vue                                │
│ htmlRendererRegistry.ts      ★注册 4 个 componentType                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### render-config 分发链（改造前后对比）

```
改造前（E0-3）：
  override='d-form-table' → RENDERER_DISPATCH.get('d-form-table') = None
    → 'd-form-table' ∈ _ONLYOFFICE_HTML_WHITELIST（不改写 onlyoffice）
    → 'd-form-table' ∉ _CONFIRMATION_COMPONENTS（不给空载荷）
    → 落最后一档：extract_grid(tpl, sheet, data_only=True) + strip_standard_header
    → 返回 19 行 XX银行/0/0  ← 缺陷

改造后（E0-3）：
  sheet override='confirmation-send-list-e03'
    → RENDERER_DISPATCH 命中 render_e0_send_list_e03
    → 无持久化 → _initial_data() = {_format:'send-list-e03-v1', rows:[], conclusion:{}}
    → legacy grid 载荷 → migrate_legacy_grid_payload()
    → 附 _prefill（E1-3 段语义取数结果，transient 不落库）
    → 直接 return，grid 兜底分支永不到达  ✓
```

### 数据持久化

沿用 confirmation 范式：写在 `working_paper.parsed_data.html_data[sheet_name]`，由前端 `buildPayload()` → `wp_html_save` 写回。**不用 `checklist_responses`** —— 与 D0/G0/L0 一致，且 R5 的 legacy 载荷本就在这里。

## Components and Interfaces

### 后端

#### `services/e0_send_list/send_list_specs.py`

```python
SHEET_E03 = "货币资金发函记录表E0-3"
SHEET_E04 = "借款发函记录表E0-4"
SHEET_E05 = "应付银行承兑汇票发函记录表E0-5"
SHEET_E06 = "理财产品发函记录表E0-6"

FORMAT_VERSION: dict[str, str] = {
    SHEET_E03: "send-list-e03-v1",
    SHEET_E04: "send-list-e04-v1",
    SHEET_E05: "send-list-e05-v1",
    SHEET_E06: "send-list-e06-v1",
}

def column_map(sheet: str) -> dict[str, str]:
    """列字母 → field，直接读 e0_send_list_source_manifest.json（不抄第二份）。"""

def fields(sheet: str) -> list[str]:
    """按源模板列序返回 field 列表。"""
```

#### `services/e0_send_list/e1_3_segments.py`（纯函数，无 DB）

```python
@dataclass(frozen=True)
class E1_3Variant:
    sheet_name: str
    bank_col: str          # 开户银行
    holder_col: str        # 总账银行名称
    account_col: str       # 银行账号
    currency_col: str | None
    unaudited_col: str     # 期末余额（未审）
    audited_col: str       # 期末审定数
    statement_col: str     # 期末对账单余额
    restricted_amt_col: str
    restricted_reason_col: str
    rate_col: str | None

E1_3_CNY  = E1_3Variant("银行存款及其他货币资金明细表(仅人民币)E1-3",
                        "A","B","C",None,"H","J","K","Q","R",None)
E1_3_FX   = E1_3Variant("银行存款及其他货币资金明细表(人民币及外币)E1-3",
                        "A","B","C","E","M","AA","AD","AJ","AK","AL")

SEGMENT_HEADS = ("银行：", "其他金融机构（存放财务公司款项）：", "其他货币资金：")
EXCLUDED_ROWS = ("存款本金小计", "存款应计利息小计", "银行存款小计",
                 "财务公司存款小计", "其他货币资金小计", "合 计")
INTEREST_SECTION_HEAD = "（二）应计利息"

def split_segments(rows: list[dict]) -> list[Segment]:
    """按 SEGMENT_HEADS 识别段起点，段内明细行 = 段头之后到下一段头/小计行之前。
    「（二）应计利息」段整体排除（R4.2）。返回 Segment(head, account_subject, detail_rows)。"""

def account_subject_of(segment_head: str) -> str:
    """银行： → 1002 银行存款；其他金融机构…： → 1002；其他货币资金： → 1012（R4.8）。"""
```

**为什么切段而不按行号**：两版行号完全不同，且真实项目账户数远超模板容量，段内明细行数是浮动的。段头文字是稳定标识（openpyxl 实证两版逐字相同）。

#### `routers/wp_render_strategies/_e0_send_list.py`

```python
async def render_e0_send_list_e03(ctx) -> dict | None
async def render_e0_send_list_e04(ctx) -> dict | None
async def render_e0_send_list_e05(ctx) -> dict | None
async def render_e0_send_list_e06(ctx) -> dict | None

def _initial_data(sheet: str) -> dict:
    return {"_format": FORMAT_VERSION[sheet], "rows": [],
            "conclusion": {"audit_explanation": "", "overall_conclusion": "", "remarks": ""}}

def migrate_legacy_grid_payload(sheet: str, legacy: dict) -> dict:
    """纯函数 / 幂等 / 不写库（R5）。
    - 已有正确 _format → 原样返回
    - legacy grid（有 cells/column_meta/header_rows 而无 _format）→ 按 column_map 转 rows
    - 保留 _row_id 与 conclusion 三键
    - manifest 未声明的列字母 → 收进 row['_unmapped_cells']（不丢）
    """

async def build_e03_prefill(ctx) -> dict | None:
    """E1-3 → E0-3 取数（transient，不落库）。
    返回 {variant, amount_caliber_options, rows: [{bank_name, account_holder,
          bank_account, currency, interest_rate, account_subject,
          amount_unaudited, amount_audited, amount_statement,
          restricted_amount, restricted_reason, _segment}]}
    两版都取不到 → None（R4.7 宁缺勿造）。任一环异常 fail-open。"""
```

**fail-open 铁律**：取数/迁移任何一环抛错都不阻断 render（记 warning），退化为空载荷或未迁移载荷。

### 前端

#### `sendListSpec.ts`（前端唯一真源，与后端交叉锁死）

```ts
export type SendListSheet = 'e03' | 'e04' | 'e05' | 'e06'
export interface SendListColumn {
  cell: string            // 源模板列字母，供守卫三向比对
  field: string           // 业务 snake_case，存储键
  label: string           // 源模板逐字标签
  type: 'text' | 'enum' | 'date' | 'number'
  enum?: string[]
  render?: 'amount'
  width?: number
  platformEnhanced?: true // R6.4：标注非源模板口径（account_type 枚举）
  sourceHidden?: true     // R6.3：源模板隐藏但平台显式化（E0-3 与 E0-4 的 is_confirm，两张表 E 列都 hidden=True）
}
export interface SendListSpec {
  sheet: SendListSheet
  sheetName: string
  formatVersion: string
  componentType: string
  columns: SendListColumn[]
  hasConfirmFlag: boolean     // e03/e04 = true；e05/e06 = false（R6.2）
  supportsPrefill: boolean    // 仅 e03 = true（R4）
  columnToggle: boolean       // e03/e04 = true（R1.6 宽表）
}
export const SEND_LIST_SPECS: Record<SendListSheet, SendListSpec>
```

#### `useSendListData.ts`

```ts
export function useSendListData(spec: SendListSpec, opts: {
  htmlData: Ref<any>; isReadonly: Ref<boolean>
}) {
  rows: Ref<SendListRow[]>              // 业务键 dict + _row_id
  addRow(): void; removeRow(id): void; moveRow(id, dir): void
  visibleColumns: Ref<SendListColumn[]> // 列显隐
  conclusion: Ref<SendListConclusion>
  buildPayload(): SendListPayload       // { _format, rows, conclusion }
  hasUnmappedCells: ComputedRef<boolean>
}
```

**行 CRUD 铁律**：`_row_id` 稳定键；不预置空行；删行清全字段（R3.1/3.3/3.4）。

#### `sendListPrefillPlan.ts`

```ts
export type AmountCaliber = 'unaudited' | 'audited' | 'statement'
export const DEFAULT_AMOUNT_CALIBER: AmountCaliber = 'unaudited'  // 判断 3

export function planSendListPrefill(
  existing: SendListRow[], prefill: E03PrefillRow[], caliber: AmountCaliber
): PrefillPlan   // 委托 composables/shared/adjudicationPrefillPlan.ts
```

匹配键 `bank_account`；已有值不覆盖（手工优先）；幂等；返回 `{creates, fills, conflicts, skipped}` 供预览与「仅补空值」。

#### `sendListConsistency.ts`

```ts
export function checkSendListConsistency(
  rows: SendListRow[], prefill: E03PrefillRow[] | null
): ConsistencyItem[]
// 规则 R1「受限金额非零 → has_restriction 必须为是」（error）
// 规则 R2「E0-3 有账号但 E1-3 无对应账户」（warning，账号可能新开）
// 规则 R3「E1-3 有账户但 E0-3 未列」（warning，完整性提示）
// prefill 为 null → 全部 skip（不报 error，不拿空当零）
```

#### `services/e0_send_list/f3_2_notes_source.py`（E0-5 上游，与 `e1_3_segments.py` 对称）

```python
BANK_ACCEPTANCE_KEYWORD = "银行"          # 复用 F3TabDetail 口径 noteType.includes('银行')
SUPPLY_CHAIN_KEYWORD = "供应链"

@dataclass(frozen=True)
class F3NoteRow:                            # F3-2 一行（业务键，字段名对齐 useF3Detail.ts）
    ticket_no: str; note_type: str; acceptor: str
    issue_date: str; due_date: str
    face_value: float | None; audited_amount: float | None
    deposit_amount: float | None; deposit_ratio: float | None
    is_confirmed: str

def select_bank_acceptance_to_confirm(rows) -> tuple[list[F3NoteRow], list[str]]:
    """返回 (待函证银承行, hints)。
    只取 is_confirmed=='是' and BANK_ACCEPTANCE_KEYWORD in note_type；
    供应链票据不进结果、只进 hints（承兑人可能非银行 = 会计判断，代码不代替）。"""

def build_e05_prefill(rows, caliber: E05AmountCaliber) -> E05Prefill | None:
    """无 F3-2 数据或无命中行 → None（宁缺勿造）。
    settle_account / currency 恒 None —— F3-2 无这两列。"""
```

`E05AmountCaliber = Literal['face', 'audited']`，`DEFAULT_E05_AMOUNT_CALIBER = 'face'`（R13.5 待裁决）。

#### `sendListE05Checks.ts`（E0-5 专属红线，只读派生）

```ts
export function groupByIndexNo(rows: SendListRow[]): E05IndexGroup[]
// 展示层派生：同 index_no 归组 + 组内票面金额小计；不改 rows 存储形态（Property 22）

export function checkE05Completeness(
  rows: SendListRow[],
  f3Prefill: E05Prefill | null,
  tb2201: number | null,
): ConsistencyItem[]
// 三方勾稽：Σ(E0-5 票面) ↔ Σ(F3-2 银承待函证审定数) ↔ trial_balance 2201
// 任一不可得 → 该项 skip，绝不拿 0 比较（Property 21）

export function checkE05TicketNo(rows, f3Prefill): ConsistencyItem[]
// 票号唯一性（error）+ 与 F3-2/F3-5 一致性（warning：账面未登记 / 可能漏函）

export interface TenorPolicy { maxTenorDays: number }   // 按会计期间可配置，禁写死月数
export function checkE05Tenor(rows, cutoffDate: string, policy: TenorPolicy): ConsistencyItem[]
// 已到期未兑付（与 F3-5 交叉提示）/ 期限异常（Property 23）
```

#### `sendListScopeChecks.ts`（E0-3 函证范围完整性红线，只读派生 —— R16）

源模板明文要求「所有银行账户全部函证（**包括零余额账户和在本期内注销的账户**）」
（`E0A` 程序 1 / `E0-1!O28` / `回函情况汇编` 编制说明 2），未函证的必须记录理由（`E0-1!O29`）。
现状平台侧零校验 —— R14 只覆盖了 E0-5 的票据红线，E0-3 侧一条都没有。

```ts
export interface SendScopeContext {
  /** 审计期间（判「本期内注销」） */
  periodStart: string
  periodEnd: string
  /** 重要性水平（优先取 B15），缺省 → 「发生额大余额小」项 skip */
  materiality?: number | null
  /** 账号 → 本期发生额（来自 E1-3；取不到该账号即 undefined，绝不填 0） */
  turnoverByAccount?: Record<string, number>
}

/**
 * 三条红线（全部 skip-on-missing、只读、不阻断保存）：
 *   1. 零余额未函证且无理由 → error
 *   2. 本期内注销（terminate_date ∈ [periodStart, periodEnd]）未函证且无理由 → error
 *   3. 发生额 ≥ materiality 且 余额 < materiality 且未函证 → warning
 * 「无理由」= `remark`（P 列，源模板唯一可写位）为空；填了理由 → 降为 ok。
 * `terminate_date` 为空视为账户存续，不判定（Property 26）。
 */
export function checkSendScopeCompleteness(
  rows: readonly SendListRow[],
  ctx: SendScopeContext | null,
): ConsistencyItem[]

/** 未函证账户清单（供 E0-1「二、样本选择」汇总理由的跳转提示，R16.5） */
export function unconfirmedAccounts(rows: readonly SendListRow[]): SendListRow[]
```

🔴 **阈值禁写死**（Property 27）：判定线只能来自 `ctx.materiality` / `ctx.threshold`，
源码不得出现金额字面量常量。`bank_account` 作为统一比对键预留给后续的
「账户完整性四方比对」独立 spec（R16.8）。

#### `resolve_sheet_override`（平台级，R15）

```python
def resolve_sheet_override(sheet_name: str | None, wp_code: str | None,
                           overrides: dict[str, str]) -> str | None:
    """全名 → 尾码 → {wp_code}-{sheet_name}（改造前是尾码优先）。
    抽成纯函数供 wp_render_config 调用与守卫直测；skip 过滤仍走既有更早的全名精确匹配路径。"""
```

## Data Models

### 新格式载荷（写库形态）

```jsonc
{
  "_format": "send-list-e03-v1",
  "rows": [
    {
      "_row_id": "row-1785215449506-ce4keh",
      "account_subject": "1002 银行存款",
      "index_no": "E0-3",
      "report_date": "2025-12-31",
      "bank_name": "招商银行金华分行",
      "is_confirm": "是",
      "account_holder": "重药控股安徽有限公司",
      "bank_account": "801xxxxxxxx",
      "currency": "CNY",
      "interest_rate": 0.35,
      "account_type": "基本存款账户",
      "balance_orig": 20751212.11,
      "is_pooling": "否",
      "start_date": null,
      "end_date": null,
      "has_restriction": "否",
      "remark": ""
    }
  ],
  "conclusion": {
    "audit_explanation": "",
    "overall_conclusion": "",
    "remarks": ""
  }
}
```

### transient prefill（render 下发，不落库）

```jsonc
{
  "_prefill": {
    "variant": "银行存款及其他货币资金明细表(仅人民币)E1-3",
    "source_caliber_note": "源模板 E0-3.K 原公式指向 E1-3.K「期末对账单余额」",
    "rows": [
      { "bank_name": "招商银行金华分行", "account_holder": "…", "bank_account": "801…",
        "currency": null, "interest_rate": null, "account_subject": "1002 银行存款",
        "amount_unaudited": 20751212.11, "amount_audited": 20751212.11,
        "amount_statement": 20751212.11,
        "restricted_amount": 0, "restricted_reason": "", "_segment": "银行：" }
    ]
  }
}
```

`_prefill` 前缀标明 transient；`buildPayload()` **不得**把它写回（守卫断言）。

E0-5 侧同构（上游是 F3-2，不是 E1-3）：

```jsonc
{
  "_prefill": {
    "source": "明细表F3-2",
    "caliber": "face",
    "caliber_note": "默认取 F3-2「票面金额」（与 E0-5 表头同名同义）；可切「期末审定数」",
    "tb_2201": 30058093.28,          // trial_balance 2201，供三方勾稽；取不到则 null
    "bank_unconfirmed_count": 2,     // F3-2 银承未函证笔数（R14.5 反向提示）
    "hints": ["F3-2 含 1 张供应链票据未自动带入，承兑人是否为银行需人工判断"],
    "rows": [
      { "bill_no": "BA001", "bank_name": "招商银行金华分行",
        "face_amount": 1000000, "audited_amount": 1000000,
        "issue_date": "2025-07-01", "due_date": "2025-12-31",
        "settle_account": null, "currency": null,
        "deposit_amount": 300000, "deposit_ratio": 0.3,
        "note_type": "银行承兑汇票" }
    ]
  }
}
```

`settle_account` / `currency` 恒 `null`（F3-2 无这两列，Property 20）；`deposit_*` 供 R14.6 的展开行呈现与 R7.6 勾稽，**不落新列**。

### legacy grid 载荷（迁移输入，实测存在）

```jsonc
{
  "rows": [{ "_row_id": "row-1785215449506-ce4keh" }],
  "cells": {},                 // { "C6": {"v": "招商银行"}, … }
  "column_meta": {}, "header_rows": 1, "merged_cells": [],
  "col_widths": { "A": 6.22, "…": 0 }, "max_col": 11, "max_row": 0,
  "context": {},
  "conclusion": { "remarks": "", "audit_explanation": "", "overall_conclusion": "" }
}
```

迁移映射：`cells["{col}{row}"].v` → `rows[i][column_map[col]]`，行序按 `row` 升序对齐 `rows[]` 的 `_row_id`；`conclusion` 三键原样搬；未声明列字母进 `_unmapped_cells`。

## Error Handling

统一原则：**render 路径一律 fail-open，写入路径一律 fail-closed。**

| 场景 | 处理 | 用户可见 |
|---|---|---|
| 源模板文件缺失 / sheet 缺失 | 返回 `_initial_data()`（空表），记 warning | 空可编辑表，不报错 |
| legacy 迁移抛错 | 返回**未迁移的原载荷**（不吞数据、不返空），记 warning | 提示条「历史数据形态未识别，已原样保留」 |
| legacy `cells` 出现未声明列字母 | 收进 `row._unmapped_cells`，不丢不报错 | 提示条「存在 N 个未识别列，已保留」 |
| E1-3 两版都不存在 / 无明细行 | `build_e03_prefill` 返回 `None`，省略 `_prefill` 键 | 带入按钮 disabled + 「上游 E1-3 暂无账户明细」 |
| E1-3 取数中任一步抛错 | 省略 `_prefill`，**不阻断 render** | 带入按钮 disabled，其余功能正常 |
| 仅人民币版无币种/利率列 | 输出 `null`（不填 0、不猜） | 该列留空 |
| 勾稽的 `prefill == null` | 全部 `skip`（**不产 error**） | 面板显示「暂无可比对数据」 |
| 勾稽分母为 0 | 结果 `null` 渲染「—」 | 不显示 0%（会误导） |
| AI 请求 4xx/5xx | 捕获后 `ElMessage.warning` 明示失败原因 | **不静默吞**（平台已知反例） |
| 导入部分区块失败 | 返回 `{ok:false, errors:[...]}`，UI 逐项列出 | **不提示「导入成功」** |
| 保存批次出现重复 `item_id` | 按 key 去重后再发（后写覆盖先写） | 无感 |
| 跨主体类型 / 只读态 | 组件 `isReadonly` 时全列禁用，动作按钮 disabled | 按钮灰显 |

**绝不做的降级**：不把取数失败退化成"填 0"；不把迁移失败退化成"返空表"；不把 `_prefill` 写回库。

## Testing Strategy

四层，每层都要有反向自检（断言"引入缺陷必红"），防止守卫空转。

**1. 源模板事实层（后端，openpyxl 直读）**
- `test_e0_send_list_source_facts.py`：四张 sheet 的 tab 名/表头行/列数/逐字标签/隐藏列/DV 范围/E0-3 三列公式目标与行映射；三向比对 源 xlsx ↔ manifest ↔ `E0.yaml`
- `test_e1_3_segment_facts.py`：两版 E1-3 的段头文字、段内明细行区间、小计行、应计利息段起点、两组列语义
- 反向自检：改一字必红 / 给 E0-5 加 `is_confirm` 必红 / 段头判定改按行号必红
- 跳过 `~$` 锁文件；先比对 `backend/wp_templates/` 与参考副本 size（运行时权威只认前者）

**2. 纯函数层（后端单测 + PBT，hypothesis `max_examples=5`）**
- `split_segments`：随机插入小计行/空行/应计利息段 → 输出恒不含它们（Property 7）
- `migrate_legacy_grid_payload`：随机 legacy 载荷 → 幂等 + `_row_id` 集合不缩小 + 非空 cells 值全部可追溯（Property 5）
- `planSendListPrefill`（前端 PBT）：随机已有值 → 不覆盖 + 连续两次结果逐字节相同（Property 9）
- `checkSendListConsistency`：`prefill=null` → 全 skip（Property 13）

**3. 契约 / 交叉锁死层**
- 前端 `sendListSpec.spec.ts` 用 `fs.readFileSync` 读**后端** manifest 逐字比对五元组（跨前后端唯一可靠手段）
- 注册四处交叉（registry / `RENDERER_DISPATCH` / `wp_classification_service` / `wp_code_overrides.json`）+ 反向自检
- **平台级** `test_confirmation_component_backend_claimed.py`：前端 `confirmation-*` ⊆ 后端两集合
- AI 接线：文本区键集 ↔ 后端 `_SECTION_PROMPTS` 无缺无余；marker stub 检测（`stripComments()` 后函数体不得只含 `emit`/`console.log`）
- 导入导出往返自检：导出模板 → 导入校验器 → 无「缺少列」
- 源码型守卫一律先 `stripComments()`，且 `stripComments` 自身用**内联 fixture** 自检（不依赖某真实文件恰好有反例）

**4. 集成 / 实测层**
- 组件挂载 smoke（对齐 `alternativeCallerMount.smoke.spec.ts`）：挂载不抛 + legacy `htmlData` 载入 + `buildPayload()._format` 正确且不含 `_prefill`
- 浏览器实测（chrome-devtools MCP）+ postgres 只读比对，目标项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877`（同时具备"无持久化"与"有 legacy 载荷"两个条件）
- 实测核心验收：**界面不再出现 `XX银行`**；E0-6 legacy 往返无损；金额 `1234567.5` → `1,234,567.50`；`el-input-number` 计数 0
- 先快照后改、按 md5 逐字节复原；不可复原字段如实记录

**回归门**：本 spec 改动的共享面只有 `htmlRendererRegistry`（加法）与 `wp_code_overrides.json`（加法）→ 验收门 = 其余循环的 render-config 输出与既有 registry 契约测试逐字节不变。前端全量失败判定用 `--reporter=json --outputFile=<abs>.json`（cmd 重定向会腌坏中文）。

## Correctness Properties

### Property 1: 四张 sheet 的渲染列集逐字等于源模板

对每张 sheet，前端 `SEND_LIST_SPECS[x].columns` 的 `(cell, field, label, type, enum)` 五元组序列 == `e0_send_list_source_manifest.json` 的 `cell_columns` == `E0.yaml` 的 `dynamic_table.columns` == openpyxl 直读源 xlsx 表头行。三向比对含反向自检（改任一处必红）。

**Validates: Requirements 1.3, 6.1, 6.6, 12.1**

### Property 2: 初始载荷为空表，绝不含模板缓存示例值

`_initial_data(sheet)` 对四张 sheet 均返回 `rows == []`；序列化后不含 `XX银行` / `XX财务公司`。反向自检：以模板缓存值构造的 fixture 断言必红。

**Validates: Requirements 2.1, 2.3, 3.1**

### Property 3: 三个 componentType 在 RENDERER_DISPATCH 命中，且 render 源码不触 grid 兜底

`RENDERER_DISPATCH` 含三个 key（`confirmation-send-list-e03/-e04/-e05`）；
`_e0_send_list.py` 源码 `stripComments()` 后不含 `extract_grid` / `data_only`。
**E0-6 的 `confirmation-wealth-list` 显式豁免**：它走旧路径 `_CONFIRMATION_COMPONENTS`
（无 render 期取数需求、源模板数据区 R6:R20 全空故无示例值污染），
守卫 SHALL 正向断言它在 `_CONFIRMATION_COMPONENTS` 而**不在** `RENDERER_DISPATCH`，
并断言 `wp_render_config_helpers._FORMAT['confirmation-wealth-list'] == 'wealth-list-v1'`
（防被误改成 `send-list-e06-v1`）。

**Validates: Requirements 1.1, 1.2, 2.2, 10.4, 10.5**

### Property 4: 前端 registry 的 confirmation-* 全部被后端认领

前端 `htmlRendererRegistry` 中所有 `confirmation-*` componentType ⊆ (`RENDERER_DISPATCH` ∪ `_CONFIRMATION_COMPONENTS`)。豁免须在守卫内逐条登记理由。反向自检：把某个 key 从后端两处删掉必红。

**Validates: Requirements 2.4, 10.1, 10.5**

### Property 5: legacy grid 迁移零丢数且幂等

对任意 legacy 载荷 L：`migrate(migrate(L)) == migrate(L)`；`migrate(L)` 的 `_row_id` 集合 ⊇ L 的 `_row_id` 集合；`conclusion` 三键逐字保留；L 中所有非空 `cells` 值都出现在 `rows[i][field]` 或 `rows[i]._unmapped_cells` 之一（无静默丢弃）。含 PBT。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 6: 迁移与取数不写库

render 路径对四张 sheet 的执行不产生任何 `INSERT`/`UPDATE`；`_prefill` 键不出现在 `buildPayload()` 的输出中。

**Validates: Requirements 4.6, 5.5**

### Property 7: E1-3 切段只取明细行

`split_segments` 的输出不含三个段头 SUM 行、不含 `EXCLUDED_ROWS` 任一行、不含「（二）应计利息」段任何行。对两版 E1-3 的真实结构（openpyxl 直读）分别验证：仅人民币版三段明细起于 13/23/27，人民币及外币版起于 13/19/23。反向自检：把段头判定改成按行号必红。

**Validates: Requirements 4.2, 4.3, 12.3**

### Property 8: 取数按项目实际版本分支且宁缺勿造

WHEN 项目只有仅人民币版 E1-3 THEN `currency` 与 `interest_rate` 为 `null`（该版无这两列），不臆造；WHEN 两版都无数据 THEN `build_e03_prefill` 返回 `None` 且零写入。

**Validates: Requirements 4.3, 4.4, 4.7**

### Property 9: 带入手工优先且幂等

`planSendListPrefill` 对已有非空值的字段只产 `conflicts` 不产 `fills`；对同一输入连续两次 plan→apply 的结果逐字节相同；「仅补空值」模式下 `conflicts` 全部降级为 `skipped`。含 PBT。

**Validates: Requirements 4.6**

### Property 10: 金额口径三态可切换，默认未审期末

`DEFAULT_AMOUNT_CALIBER === 'unaudited'`；三个口径分别映射到 prefill 的 `amount_unaudited` / `amount_audited` / `amount_statement`；源模板事实（`E0-3.K ← E1-3.K = 期末对账单余额`）由 openpyxl 守卫独立钉死，且该守卫**不**要求实现取 K。

**Validates: Requirements 4.5, 12.2**

### Property 11: 「是否函证」列只在 E0-3/E0-4

`SEND_LIST_SPECS.e03.hasConfirmFlag === true` ∧ `e04 === true` ∧ `e05 === false` ∧ `e06 === false`；且 e05/e06 的 `columns` 中不存在 `field === 'is_confirm'`。openpyxl 交叉验证两表源模板表头确无该列。反向自检：给 e06 加该列必红。

**Validates: Requirements 6.2**

### Property 12: 源模板差异有意登记

**E0-3 与 E0-4 两张表**的 `is_confirm` 列都标 `sourceHidden: true`（两表各自 `E: hidden=True`，平台显式化）；`account_type` 的 5 项枚举标 `platformEnhanced: true`（源模板该列无数据验证）；E0-6 的 `has_restriction` 在平台整列启用而非照抄源模板残缺的 `K6:K10` 范围。三条均由守卫正向断言 + 注释写明依据。

🔴 守卫必须**同时**断言两组互斥事实，否则「列被隐藏」会与「列不存在」混成一种：
`sourceHidden === true` 的表恰为 `{e03, e04}`（且它们的 `hasConfirmFlag === true`）；
`hasConfirmFlag === false` 的表恰为 `{e05, e06}`（且源模板 `hidden cols == {}`、表头里确实无 `是否函证`）。
反向自检：给 e04 去掉 `sourceHidden` 必红；给 e05 加 `sourceHidden` 必红。

**Validates: Requirements 6.3, 6.4, 6.5**

### Property 13: 受限勾稽不拿空当零

`checkSendListConsistency(rows, null)` 返回全 `skip`（无 error）；WHEN E1-3 受限金额非零且对应行 `has_restriction !== '是'` THEN 恰好产生一条 error；匹配不上的账号产 warning 不产 error。

**Validates: Requirements 7.1, 7.2**

### Property 14: 金额控件语义正确

四张组件中 `render: 'amount'` 的列（`balance_orig` / `balance` / `face_amount` / `net_value` / `accrued_interest`）使用 `WpAmountInput`；`interest_rate` / `holding_shares` **不**使用；全组件 `el-input-number :formatter` 计数为 0。

**Validates: Requirements 1.4, 1.7**

### Property 15: AI section 四处登记齐备

每个文本区的 `section` 键都在后端 `_SECTION_PROMPTS` 有条目；每条 prompt 含「不得虚构」；无孤儿 prompt；AI 调用体的 `context` 值全为字符串且用驼峰 `existingContent`；`handleAi*` 函数体 `stripComments()` 后不得只含 `emit('save'` 或 `console.log`。

**Validates: Requirements 8.3, 8.4, 8.5, 8.6**

### Property 16: 导入导出往返自检

对四张 sheet：导出模板 → 立即经导入校验器 → 无「缺少列」类错误；导入部分失败时返回值含失败项且 UI 提示非「导入成功」。列映射来自 `E0.yaml` 的 `dynamic_table`，守卫断言前端未另写一份列表。

**Validates: Requirements 9.2, 9.3, 9.4**

### Property 17: override 映射用全名 sheet 键消歧 E0-5

`wp_code_overrides.json` 中 `应付银行承兑汇票发函记录表E0-5` → `confirmation-send-list-e05`；**不存在** `E0-5` 短键指向该 componentType（一码两表，短键两张 sheet 都会命中）。E0-3/E0-4 同时登记短键与全名键；**E0-6 的双键保持 `confirmation-wealth-list` 原样**（已由 `test_confirmation_sheet_override_contract.py` 断言，本 spec 不得改动）。

🔴 **原写「依赖 Property 24（查表全名优先）」已作废（2026-08-02 实证）** ——
componentType 判定（L749）是**尾码优先**，而 `应付银行承兑汇票发函记录表E0-5`
**本就靠尾码 `E0-5` 命中**、不需要全名键；被拦掉的是那张 hidden 的核对表
（走 L709 更早的全名 `skip` 路径）。
故本 Property 的正确断言是：尾码键 `E0-5` == `confirmation-send-list-e05`
**且** 全名键 `应付银行承兑汇票发函记录表E0-5` 也登记同值（冗余但自解释），
核对表的全名 `skip` 不被删则由 **Property 24** 保证。
守卫 SHALL 断言 `resolve_sheet_override('应付银行承兑汇票发函记录表E0-5', 'E0', overrides)
== 'confirmation-send-list-e05'`（走真实解析路径），而不是只查 JSON 里有没有这个键。

**Validates: Requirements 10.2, 10.3, 15.4**

### Property 18: 未向 manifest 注入取数列

`e0_send_list_source_manifest.json` 的列数与 `field` 集合改造前后逐字节不变；既有守卫 `test_no_fabricated_pull_or_source_columns` 继续通过（取数结果写进既有 field，不新增列）。

**Validates: Requirements 4.9, 11.2**

### Property 19: F3-2 → E0-5 带入只取银承且已决定函证的行

对任意 F3-2 行集，`build_e05_prefill` 的输出行数 == 满足 `isConfirmed=='是' and '银行' in noteType` 的行数；商业承兑汇票与供应链票据恒不出现在输出中（后者只进 `hints`）。反向自检：把 `noteType` 过滤去掉必红。

**Validates: Requirements 13.1, 13.2, 13.3**

### Property 20: F3-2 无对应列的字段恒留空

`settle_account`（结算账户账号）与 `currency`（币种）在 F3-2 侧无来源列 → 带入结果中该两字段恒为 `null`，绝不由别的列推断。

**Validates: Requirements 13.4, 13.7**

### Property 21: 发函完整性三方勾稽在数据缺失时全 skip

`Σ(E0-5 票面金额)` / `Σ(F3-2 银承待函证审定数)` / `trial_balance 2201` 三者中任一不可得时，对应校验项返回 `skip` 而非 `0` 比较；三者齐备时前两者不等报 error、与 2201 差异报 warning。

**Validates: Requirements 14.1**

### Property 22: 一函多票分组是展示层派生

按 `索引号` 分组后，`buildPayload()` 的 `rows` 仍是扁平数组、顺序与 `_row_id` 不变；分组结果的票面金额小计之和 == 全表合计。

**Validates: Requirements 14.2**

### Property 23: 票据期限阈值可配置且无硬编码月数

`due_date − issue_date` 的期限异常阈值取自配置（按会计期间），源码中不出现字面月数常量。反向自检：注入不同阈值时同一行的标记结果随之改变。

**Validates: Requirements 14.4**

### Property 24: `E0-5` 全名 `skip` 不变式（原「查表全名优先」已作废）

**2026-08-02 重写**：原 Property 假设「componentType 查表尾码优先 ⇒ 全名级 override 无效
⇒ 必须翻转查表顺序」。实证 `wp_render_config.py` 后作废 —— **两条判定顺序相反**，
恰好使当前配置正确：**skip 判定（L709）按完整 sheet_name 精确匹配、先于尾码判定（L722）**；
componentType 判定（L749）才是尾码优先。故 hidden 的核对表在 L709 就被 `skip` 拦下，
**永不进入** componentType 解析。

`wp_code_overrides.json` 的 `银行函证其他信息核对表E0-5` **全名键** SHALL 存在且值为 `skip`
（**不接受「尾码键也是 skip」的论证** —— 本 spec 要把尾码值改成 `confirmation-send-list-e05`）；
全库「同时命中全名键与尾码键且取值不同」的 sheet 集合 SHALL == 已知 2 条
（`银行函证其他信息核对表E0-5`、`长期应付职工薪酬实质性程序表 L2A`，两者全名值均 `skip`），
集合变大即红（迫使重新评估是否又出现新的一码两表）。
**反向自检**：在与任何真实循环无关的替身 sheet（`替身核对表XX-9` + `替身清单XX-9`）上断言
「全名 `skip` 在 → 不渲染；移除 → 按尾码解析」。
本 Property SHALL NOT 修改 L709 / L722 / L749 的实现，只加断言
（误改 skip 过滤路径会让 `长期应付职工薪酬实质性程序表 L2A` 之类历史遗留表重新出现）。

🔴 与 `e0-confirmation-completion` 的 **Property 28 / Task 19** 是**同一条不变式**，
两侧择一实现、另一侧引用文件路径，**不得各写一份**（改一处另一处不红 = 没守卫）。
建议由本 spec 实现 —— 它才是把尾码值从 `d-form-table` 改成 `confirmation-send-list-e05`、
真正让这条不变式变关键的一方。

**Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.6**

### Property 25: E0-6 保持已落地组件且不被本 spec 改动

`wp_code_overrides.json` 的 `E0-6` 与 `理财产品发函记录表E0-6` 两键 SHALL 均为 `confirmation-wealth-list`；
`RENDERER_DISPATCH` SHALL NOT 含 `confirmation-send-list-e06`；
前端 `htmlRendererRegistry` SHALL NOT 出现 `confirmation-send-list-e06`；
`wp_render_config_helpers._FORMAT['confirmation-wealth-list'] == 'wealth-list-v1'`。
反向自检：把任一处改成 `confirmation-send-list-e06` 必红。

**Validates: Requirements 1.1, 10.1, 10.2, 10.4, 10.5**

### Property 26: E0-3 函证范围完整性红线的判定与 skip 边界

`checkSendScopeCompleteness(rows, ctx)` SHALL 满足：
零余额未函证且无理由 → 恰好一条 error；本期内注销未函证且无理由 → 恰好一条 error；
`终止日期` 为空 → 不判定；发生额取不到 → 该项 `skip` 而非用 0 比较；
阈值缺省时「发生额大余额小」项 `skip`；已填理由（`备注` 非空）→ 由 error 降为 `ok`；
输出中 SHALL NOT 出现 `NaN` / `Infinity`；`checkSendScopeCompleteness([], null)` 全 `skip`。

**Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.6, 16.7**

### Property 27: 完整性红线不写死金额且不阻断保存

`sendListScopeChecks.ts` 源码 `stripComments()` 后 SHALL NOT 含金额字面量常量
（判定阈值只能来自入参 `ctx.materiality` / `ctx.threshold`）；
红线结果 SHALL 为只读派生，SHALL NOT 出现在任何 `save` / `persist` 调用的前置条件里。

**Validates: Requirements 16.1, 16.6**

### Property 28: 资金归集链路只标注不实现（**对侧表永久不存在**）

E0-3 的 `is_cash_pooling`（L 列）SHALL 在列定义里带风险标记与源模板 tooltip
（`E0A` 程序 2 原文：集团资金管理协议 / 控股股东资金池安排）；
`sendListConsistency.ts` / `sendListScopeChecks.ts` SHALL NOT 引用
`银行函证其他信息核对表E0-5` 或「附表(资金归集)」字样。

**2026-08-02 更新**：勾稽对侧表 `银行函证其他信息核对表E0-5` 已由用户裁决**不实现**
（hidden + `skip`）→ 该链路从「暂不实现」变为**永久留遗留**，
Notes SHALL 登记为已裁决状态（含 `sheet_state` + `底稿目录` 双证与用户裁决原话），
**SHALL NOT 写成"待裁决"**（否则下个会话会再问一次）。
**宁缺勿造**：不得为了"有个勾稽"而自造一张对侧表。
`E0A` 程序 2 的要求原文 SHALL 留存 —— 它是 L 列存在的唯一依据。

**Validates: Requirements 17.1, 17.2, 17.3, 17.4**

## Notes

### 与 `e0-confirmation-completion` 的协调清单（执行前必读）

| 该 spec 任务 | 与本 spec 的关系 | 处理 |
|---|---|---|
| Task 11 `importE0ListsToSummary` 纠偏 | **依赖本 spec** 的行存储形态 | 本 spec 先做；该 Task 读 `html_data[sheet].rows` 的业务键 dict |
| Task 12 E0-3/E0-6 受限 → E1 | **依赖本 spec** 的 `has_restriction` 可读 | 本 spec 只做只读勾稽，写入侧留给它 |
| Task 12 **需扩围**：F3-2 承兑保证金 / E0-5 抵（质）押品 → E1 受限货币资金 ②表 | 该 Task 原只覆盖 E0-3/E0-6，**漏了这条链路** | 本 spec 出只读勾稽（R7.6）+ `deposit_*` 可读；写入侧请该 spec 扩 Task 12（依据：F3-2 R9 源模板原文要求与其他货币资金勾稽） |
| Task 11 `importE0ListsToSummary` | **实际已落地但 tasks 仍标 `[ ]`（假红）** —— 文件已由 124 行改到 357 行，含 `票面金额`/`产品净值`/`借款类型`/`E0_LIST_SPEC`/`hasConfirmFlag`/`account_no` | 请该 spec 更正标记为 `[x]`（或拆出剩余子项）；否则批量执行器会重复实现 |
| Task 4（CrossRef 按循环）/ Task 10（品种矩阵） | **确认未做** —— `GtConfirmationSummary.vue` 里 `buildCrossRefRules` 0 命中、`D0-5`/`D0-7` 字面仍在、`其他货币资金`/`应付票据`/`占账面` 全 0 命中 | 本 spec 不接管；该 spec 自行完成 |
| ~~Task 13 「E0-6 渲染形态落地」子项~~ | ~~硬冲突~~ → **已解**：该 spec 的 **Task 12.5 已交付 `confirmation-wealth-list`**（全链 + 契约测试），原文写的「计划落 `d-form-table`」已过时 | **E0-6 保留 `confirmation-wealth-list`**；本 spec 改为「三张新组件 + E0-6 符合度核查（R1.1b）」，不新建 `confirmation-send-list-e06`、不改其 `_format` |
| Requirement 3 E0-1 品种矩阵 | **新增依赖**：矩阵的「抽取样本的发函金额」最终来自四张清单 | 本 spec 的行形态变更会影响其取数，两者验收要串 |
| Task 13 其余子项（E0-7 / 其他信息核对表 / meta 交叉守卫） | 无冲突 | 不动 |
| Task 14 E0 公式预设纠偏 | 无冲突 | 不动（本 spec R11.1 明确排除） |
| Task 2 一码两表消歧结论 | 需一致 | 本 spec Property 17 用全名 sheet 键；结论不一致时以源模板 sheet 名为准 |

### 源模板事实基线（2026-08-02 openpyxl 实证，守卫据此钉死）

- E0-3：`A1:S26`，合并区仅 `A1:P1`/`A2:P2`，表头 R5 共 16 列，数据 R6:R24 有公式、DV 到 R26；`E` 列 `hidden=True`；DV 仅 `L6:L26 O6:O26` = `"是,否"`；`print_area=$A$1:$P$29`；`max_col=19`（Q/S/T 仅有列宽残留，表头到 P 为止 → `extract_grid` 的 `effective_max_col` 会按有内容的列收敛，别把 S/T 当数据列）
- **E0-4：`A1:P20`，合并区仅 `A1:P1`/`A2:P2`，表头 R5 共 16 列（A~P），`E` 列 `hidden=True`（与 E0-3 同）；数据区 R6:R20 共 15 行**空白带边框，`print_area=$A$1:$P$21`；**零数据有效性**；**R16 残留孤立 `G16=0 / H16=0`**（借款账号/币种两列的 0，源模板残留数据行，迁移与渲染都要按空行处理，不得当成一条借款记录）；无冻结窗格
- **E0-5：`A1:J20`，表头 R5 共 10 列，`hidden cols == {}`，数据区 R6:R20（15 行），`print_area=$A$1:$J$21`，零 DV**
- **E0-6：`A1:K20`，表头 R5 共 11 列，`hidden cols == {}`，数据区 R6:R20（15 行），`print_area=$A$1:$K$20`，DV 仅 `K6:K10` = `"是,否"`（范围残缺，见 R6.5）**
- **四张表的空白数据行都带边框且 `print_area` 覆盖 → 那是打印骨架，不是数据**（对齐 R3.1「不预置空占位行」；平台侧一律动态行，初始 `rows == []`）
- **「列被隐藏」≠「列不存在」**：E0-3/E0-4 的 `是否函证` 是隐藏列（Excel 里列字母从 D 跳到 F，肉眼数只有 15 列），E0-5/E0-6 才是真的没有该列 → 判定只认 `column_dimensions[x].hidden`，禁按截图/肉眼数列
- E0-3 三列公式：`D←'[43]…(仅人民币)E1-3'!$A` / `G←$C` / `K←$K`；行映射 `6→13…14→21, 15→23, 16→24, 17→25, 18→27…24→33`（跳 22/26）
- E0-3 身份区：`A3=底稿目录!A2` / `A4=!A3` / `G3=!A4` / `G4=!A6` / `L3=!A5` / `L4=!A7` / `P3=!F6`
- E1-3 仅人民币版：表头 R9/R10 两级（`E9:H9 未审数` 下 `期初余额/本期增加/本期减少/期末余额`），段头 `A12 银行：`(SUM 13:21) / `A22 其他金融机构（存放财务公司款项）：`(SUM 23:25) / `A26 其他货币资金：`(SUM 27:33)，`A34 存款本金小计`，`A35 （二）应计利息…`
- E1-3 人民币及外币版：表头 R8/R9/R10 三级，段头 `A12`(13:17) / `A18`(19:21) / `A22`(23:28)，`A29 存款本金小计`，`A45 合 计`
- 四张表均**无合计行**（发函清单不需要）
- `~$E0 …xlsx` 锁文件存在（用户开着 WPS）→ 读模板前跳过，并注意可能有未保存改动

**E0-5 上游 = `F3 应付票据.xlsx`（2026-08-02 补充实证）**

- `明细表F3-2` 两级表头 R13:R14（19 列 A:W，合并区 `A13:A14`…`W13:W14` + `D13:F13 票据关系人` + `G13:I13 票据期限`）：
  `票据号|票据类别|关联方类型|票据关系人(出票人/承兑人/收款人)|票据期限(出票日/到期日/期限)|票面利率|是否承兑|`
  `期初余额|本期开票|本期承兑|期末未审数|账项调整|重分类调整|期末审定数|已计利息|**是否函证**|**票据保证金比例**|**保证金金额**|备注`
- 派生公式：`O=L+M-N`（期末未审 = 期初 + 本期开票 − 本期承兑）、`R=O+P+Q`（期末审定 = 未审 + 账项 + 重分类）
- `R9`「二、审计过程」第 1 条逐字含「……**复核其应存人银行的承兑保证金，并与其他货币资金科目勾稽**」
  → 保证金 → 其他货币资金/受限货币资金的联动是**源模板要求**，不是平台自拟（R7.6 的依据）
- `逾期票据检查F3-5` 两级表头 R5:R6：`票据类别|票据号|票据关系人(出票人/承兑人/收款人)|票据期限(出票日/到期日/期限)|`
  `票面利率|票面金额|期后支付金额|借款条件|是否调整|抵押情况(物品名称/金额)` → 到期日风险与票号一致性的交叉对象
- 平台侧 F3 已有字段（`composables/useF3Detail.ts`）：`ticketNo/noteType/relatedPartyType/issueDate/dueDate/`
  `drawer/acceptor/payee/isAccepted/isOverdue/isConfirmed/faceValue/depositAmount/remark`；
  `F3TabDetail.vue` 已算 `confirmSummary.bankUnconfirmed`（R14.5 直接复用）

**override 查表顺序（2026-08-02 实证，R15 的依据；⚠️ 下方是 componentType 路径，
`skip` 路径顺序相反 —— L709 全名精确优先，见 Property 24。两条顺序相反正是当前配置
恰好正确、无需翻转的原因）**

- `wp_render_config.py` 多 sheet 分支：`_SHEET_CODE_RE` 尾码 → 全名 `sheet_name` → `{wp_code}-{sheet_name}`，**尾码优先**
- `skip` 判定是**另一条更早的路径**（按全名精确匹配，在 sheet 过滤处），与上面的 componentType 解析顺序不同
  —— 这就是「核对表的 `skip` 生效、但全名指向真 componentType 时会被尾码遮蔽」的原因
- `derive_component_type` 只查 `_WP_CODE_OVERRIDE[wp_code]`（不查 sheet 名），单 sheet 底稿走这条
- 实测：全库 1797 个 classification sheet 名中，同时命中全名键与尾码键且取值不同的仅 2 条
  （`银行函证其他信息核对表E0-5`、`长期应付职工薪酬实质性程序表 L2A`，全名值均 `skip`）

### 平台侧基线（改造前）

| 事实 | 证据 |
|---|---|
| `d-form-table` 不在 `RENDERER_DISPATCH` | grep `"d-form-table":` 全后端仅命中 `batch_generate_render_schemas.py` 的 YAML 模板 |
| `d-form-table` 在 `_ONLYOFFICE_HTML_WHITELIST` | `wp_render_config.py:197` |
| 走 grid 兜底 | `wp_render_config.py:868` 分支；`extract_grid` 用 `data_only=True`（`wp_grid_extract.py:353`） |
| `strip_standard_header` 剥行 1~4 | 关键词 `致同/被审计单位/编制人/编制日/截止日/复核人`，E0-3 命中 R4 → skip=4 |
| `E0.yaml` 的 `dynamic_table` 只用于导入导出 | 消费方仅 `wp_xlsx_export_service` / `wp_export/{serialization,format_validator,template_copier}` |
| E0-6 已有 legacy grid 载荷 | 项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877` 的 `parsed_data.html_data.理财产品发函记录表E0-6`，键 `rows/cells/context/max_col/max_row/col_widths/conclusion/column_meta/header_rows/merged_cells`，无 `_format` |
| E0-3~E0-5 无持久化载荷 | 同项目 `html_data` 仅有 E0-6 一个键 |
| `confirmation-alternative-l05` 有独立 render 策略 | `_l0_confirmation.py` + `RENDERER_DISPATCH`；**不是**登记遗漏（一度误判，此处留证） |

### 关键踩坑预防

- **sheet 名逐字**：`应付银行承兑汇票发函记录表E0-5`、`银行函证其他信息核对表E0-5`（一码两表）；一律以 openpyxl `wb.sheetnames` 为准，GBK 控制台会腌坏中文
- **`_prefill` 不得写回**：transient 键混进 `buildPayload()` 会让它落库并在下次 render 与新取数打架
- **宿主传参**：新组件由 `GtWpRenderer` 按 per-sheet componentType 分发，需确认 `html_data` / `projectId` / `wpId` 都传到；漏传 `projectId` 是平台已知的静默锁死形态
- **`fmtAmount` 是 store 成员**：`inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 后 `displayPrefs.fmtAmount(v)`；写成 `import { fmtAmount } from '@/stores/displayPrefs'` 整页崩且四层验证全绿
- **`watch` 依赖数组在 setup 期求值**：被监听的顶层 `const` 必须声明在 `watch(` 之前，否则 TDZ 让整个组件挂不上（`get_diagnostics` 零诊断）
- **组件解构不存在的 composable 返回值** = 运行时崩溃，四层验证查不出 → 比对「composable `return {}` 键集」vs「组件解构键集」
- **`el-input` 只绑 `@change` 会抹掉键入** → 文本列一律 `@input` 回写
- **守卫读源码先 `stripComments()`** 并配反向自检（本 spec 注释里会写反例）
- **PowerShell `>` 重定向腌坏 UTF-8 中文** → 诊断脚本用 Python 自己写盘；vitest 用 `--reporter=json --outputFile=<abs>`
- **`read_file` 对本会话改过的文件返回陈旧版本** → 判落盘真相用 Python 直读
