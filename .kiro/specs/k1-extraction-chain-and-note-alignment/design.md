# Design: K1 取数级联补齐 + 披露/附注结构对齐

## Overview

三条主线，彼此弱耦合：

- **主线 A（取数级联）**：`tb_aux_balance` → K1-2 明细（新端点 + 自动 seed）→ 级联 K1-1 / K1-5 / K1-7 / K1-8 / K1-10 / 两个披露表；`tb_balance` 备抵叶子 → K1-3 transient seed。**不造轮子**：复用 F1 的 `import-aux-balance` 范式与 `four_table/` 共享件，把 `pick_aux_type` 提升为共享件。
- **主线 B（结构对齐）**：源 xlsx 为唯一裁决者，修订三处真源 —— 附注模板 `columns`/`rows`（seed 路径，幂等脚本）、同步载荷 `columns`/行映射（推送路径）、底稿行模型（`defaultStageMovements` / `defaultBalanceStageMovements`）。**两级表头只改 `label`/`group`，`key` 不动**。
- **主线 C（公式预设）**：`prefill_formula_mapping.json` 的 K1 块由 2 → 6，覆盖 K1-1/2/3/5/7/8/10。

A 与 B 可并行；C 依赖 A（K1-3 seed 语义决定 K1-3 预设的 `cell_ref`）。

### 关键设计取舍

**取舍 1：国企账龄表保持源模板 3 列（不回退到 5 列）**
`note_check_preset_formulas.json` 的 F8-50/F8-51/F8-52 用「合计行.期末账面余额 / 期末坏账准备」的**列式**措辞，而源 xlsx R6:C15 明确是**单级 3 列 + 行式**（`小  计` / `减：坏账准备` / `合  计`）。两者信息等价：
`合计行.期末账面余额` ≡ `小  计` 行、`合计行.期末坏账准备` ≡ `减：坏账准备` 行、`(账面余额 − 坏账准备)` ≡ `合  计` 行。
本 spec 按源 xlsx 保持 3 列，并在该表 `guidance` 里写明 F8-* 的行式映射，供校验引擎与人工复核对齐。**不改校验预设 JSON**（跨章节共享真源，改动面过大）。

**取舍 2：源模板笔误保留语义、修正措辞**
上市 R116 列头写 `应收账款性质`（该 sheet 是其他应收款，属源模板复制粘贴笔误）。保留现有 `其他应收款性质`（语义正确），但把 `是否由关联交易产生` 改为源模板措辞 `款项是否由关联交易产生`。此判断在 `guidance` 与守卫注释中显式记录，避免后续会话反复推翻。

**取舍 3：汇总表按条件表语义推送、不进 `_removed_table_keys`**
附注 §五、8 / §八、9 顶部汇总表同时承载 应收利息（G2）/ 应收股利（G3）/ 其他应收款（K1）。K1 只在 `fs_reconciliation` 有值时推送整表；无值不推、**且不 removed**（该表可能由 G2/G3 承载，越权删会打断对方）。

## Architecture

```
四表库                        共享件                        K1 底稿                     披露                附注
──────────────────────────────────────────────────────────────────────────────────────────────────────────
report_config BS-009 ──┐
                       ├─► four_table/report_line_accounts ──► tb_source_codes ──┐
account_mapping  ──────┘        （已存在，K1 已消费）                            │
                                                                                 │
tb_balance (叶子) ─────► four_table/leaf_aggregation ─────► K1-1 adjudication_prefill
                                （已存在）              └─► K1-3 detail seed  ◄── 新增 k1_detail_seed.py
                                                                                 │
tb_aux_balance 1221 ──► four_table/aux_aggregation ──────► K1-2-detail-rows       │
                        （新建：pick_aux_type 提升）        ▲ 新端点              │
                        + k1_aux_detail.build_rows          │ /k1/import-aux-balance
                                                            │
                                              useK1DetailAutoSeed（空表自动触发）
                                                            │
                                     ┌──────────────────────┴───────────────────┐
                                     ▼                                          ▼
                        K1-1 审定表 / K1-5 / K1-7 / K1-8 / K1-10      K1TabDisclosureListed/Soe
                                     │                                          │
                                     └─► fs_reconciliation ─► 汇总表 ───────────┤
                                                                                ▼
                                                          buildK1{Listed,Soe}SyncPayloads
                                                                                │
                                                          POST /disclosure-notes/sync-from-workpaper
                                                                                ▼
                                                       note_template_{listed,soe} §五、8 / §八、9
                                                       （seed 路径 columns 由幂等脚本修订）
```

### 三处真源必须同改（本 spec 反复出现的约束）

| 真源 | 影响路径 | 修订入口 |
|------|----------|----------|
| `note_template_{listed,soe}.json` 的 `columns`/`rows` | **seed 路径**（新建项目 / 重新生成附注 / Word 导出） | `fix_note_k_complex_structure.py`（幂等，带 `--dry-run`/`--check`） |
| `k1DisclosureSyncPayload.ts` 的 `K1_{LISTED,SOE}_COLUMNS` + 行映射 | **推送路径**（真实用户路径） | 直接改 TS |
| `useK1BadDebt.defaultStageMovements` / `k1DisclosureModel.defaultBalanceStageMovements` | 底稿行模型（决定推送的行标签） | 直接改 TS + 迁移函数 |

只改其中一处 = 另一条路径继续错（H8 只改模板漏载荷、F2 只改载荷漏模板，两个方向都踩过）。

## Components and Interfaces

### 后端新增 / 修改

#### `backend/app/services/four_table/aux_aggregation.py`（新建）

把 F1 的 `pick_aux_type` 提升为共享件，语义逐字不变。

```python
def pick_aux_type(candidates: Iterable[tuple[str, int, float]]) -> str | None:
    """从 (aux_type, 行数, 金额) 候选里挑唯一维度（防 aux_type 冗余双算）。

    与 `_f1_import_export.pick_aux_type` 语义**逐字一致**（F1 改为薄壳委托）。
    """

async def aggregate_aux_by_name(
    db, table, project_id: str, year: int, account_prefixes: Sequence[str],
) -> tuple[list[AuxEntry], str | None, int]:
    """① get_active_filter 只取 active dataset；② 先锁定单一 aux_type；
    ③ 再按 aux_name 归集 opening/debit/credit/closing。

    Returns: (entries, aux_type, total_units)
    """
```

`_f1_import_export.pick_aux_type` 改为 `from app.services.four_table.aux_aggregation import pick_aux_type`（保留原名再导出，G7 的 `from ._f1_import_export import pick_aux_type` 零改动）。

#### `backend/app/services/four_table/k1_aux_detail.py`（新建，纯函数）

```python
K1_NATURE_RULES: list[tuple[str, str]]   # 与 _k1_other_receivables._NATURE_RULES 同源

def classify_k1_nature(name: str) -> str:
    """备用金 / 保证金、押金 / 往来款 / 其他 —— 返回**中文性质名**（写入行 nature 字段）。"""

def build_k1_detail_rows_from_aux(
    entries: Sequence[AuxEntry],
    segments: Sequence[AgingSegmentLike],
    related_party_names: Set[str],
    *,
    row_limit: int = 500,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """归集条目 → K1-2 行 dict（字段名逐字对齐前端 `K1DetailRow`）。

    - 账龄：金额整笔落 `segments[0].key`（agingPrior 用期初、agingCurrent/agingAudited 用期末）
    - relatedParty：名称命中 related_party_names → '是'，否则 '否'
    - nature：classify_k1_nature(aux_name)
    - stage：默认 1；badDebtProvision 0；netValue = endBalance
    - remark：'由辅助余额表({prefix}·{aux_type})导入'
    """
```

#### `backend/app/services/four_table/k1_detail_seed.py`（新建，纯函数 + 编排）

```python
def build_k1_bad_debt_seed_from_tb(
    leaves: Sequence[LeafRow], provision_prefixes: Sequence[str],
) -> dict | None:
    """备抵叶子 → K1-3 payload 片段（mainRows 的 portfolio/total 行 + stageMovements 首尾）。

    净减（贷方备抵减少）→ 转回；净增 → 计提，保证
    期初审定 + 计提 − 转回 = 期末账面（roll-forward 自洽）。
    无数据返 None（宁缺勿造）。
    """

def seed_k1_bad_debt(responses_snapshot: dict, payload: dict) -> None:
    """transient seed 进 `responses_snapshot['K1-3-baddebt-rows']`；
    已有非空手工数据时**不覆盖**（手工优先）。"""
```

#### `backend/app/routers/wp_render_strategies/_k1_import_export.py`（修改）

1. 新增 `POST /api/workpapers/{wp_id}/k1/import-aux-balance`（编排 `aggregate_aux_by_name` + `build_k1_detail_rows_from_aux`，merge 语义按 `counterparty` 去重）。
2. `_K1_SPECS` 四处 `item_id` 改正 + K1-2 `field_keys` 改 `beginBalance`/`endBalance`。

#### `backend/app/routers/wp_render_strategies/_k1_other_receivables.py`（修改）

`render()` 在算完 `leaves` / `accounts` 后追加 K1-3 seed（fail-open，不改既有输出键）。

### 前端新增 / 修改

#### `composables/useK1DetailAutoSeed.ts`（新建）

```ts
export function shouldAutoSeedK1Detail(allResponses: Map<string, any>): boolean
/** K1-2-detail-rows 缺失 / 空数组 / 解析失败 → true */

export async function autoSeedK1DetailFromAux(opts: {
  wpId: string; allResponses: Map<string, any>; reload: () => Promise<void>
}): Promise<{ imported: number; skipped: boolean }>
/** 调 /k1/import-aux-balance 落库后 reload 级联；fail-open 不抛。 */
```

挂在 `GtK1OtherReceivables.selfLoad()` 尾部。

#### `composables/k1StageMovementRows.ts`（新建，纯函数 + 单一真源）

```ts
export type K1MovementVariant = 'listed' | 'soe'

/** 源模板 12 行（坏账准备三阶段） */
export function buildK1ProvisionMovementRows(variant: K1MovementVariant): K1StageMovementRow[]
/** 源模板 10 行（国企账面余额三阶段） */
export function buildK1BalanceMovementRows(): K1StageMovementRow[]

/** 历史数据迁移：旧 13/11 行 → 新 12/10 行，按 key 对齐；
 *  被折叠的迁移行（s2-s3 / s3-s1 等）按方向合并进 4 个目标行；金额不丢。 */
export function migrateK1MovementRows(
  raw: unknown, kind: 'provision' | 'balance', variant: K1MovementVariant,
): K1StageMovementRow[]
```

`useK1BadDebt.defaultStageMovements` 与 `k1DisclosureModel.defaultBalanceStageMovements` 改为委托本模块（保留导出名，既有引用零改动）。

#### `composables/k1NoteSectionMap.ts`（修改）

新增 `summary` 子表键与逐表合计行字面表：

```ts
export const K1_LISTED_SUBTABLE = { summary: '其他应收款', ... }  // 追加
export const K1_SOE_SUBTABLE    = { summary: '其他应收款', ... }  // 追加

/** 逐表合计行字面（源 xlsx 实证；禁全局硬套） */
export const K1_TOTAL_LABEL_BY_TABLE: Record<string, string>
```

#### `composables/k1DisclosureSyncPayload.ts`（修改）

- 列头按 R6 逐字修订（只改 `label`/`group`）。
- 新增汇总表映射 `buildK1SummaryRows(fs)`（条件表：无值不推、不 removed）。
- `noteTextRows` 改为接受 `[section, title, text]` 三元组，补齐中文标题。

#### `backend/scripts/fix/fix_note_k_complex_structure.py`（修改）

扩 `K1_LISTED_PLAN` / `K1_SOE_PLAN`：列头 label/group 修订、行标签修订、`合  计` 双空格、ECL 表头全称、政府补助首列括注、终止确认列名；`ensure_text_sections` 补 R9 所列缺段。

## Data Models

### `AuxEntry`（共享件）

```python
class AuxEntry(NamedTuple):
    aux_name: str
    opening: float
    debit: float
    credit: float
    closing: float
```

### K1-2 明细行（`K1-2-detail-rows`，JSON 数组存 `remark`）

```jsonc
{
  "id": "K1-2-r-...",
  "seq": 1,
  "counterparty": "某公司",          // ← aux_name
  "nature": "保证金、押金",           // ← classify_k1_nature
  "relatedParty": "否",              // ← related_party_registry 命中
  "beginBalance": 0.0,               // ← aux opening（注意：不是 openingBalance）
  "endBalance": 0.0,                 // ← aux closing
  "agingPrior":    { "within1": 0.0, "y1to2": 0.0 },   // 段 key 随项目配置
  "agingCurrent":  { "within1": 0.0 },
  "agingAudited":  { "within1": 0.0 },
  "stage": 1,
  "badDebtProvision": 0.0,
  "netValue": 0.0,
  "voucherNo": "", "conclusion": "",
  "remark": "由辅助余额表(1221·客户)导入"
}
```

### 三阶段变动行（统一模型，两处共用）

```ts
interface K1StageMovementRow {
  key: 'opening' | 'openingInPeriod' | 'to2' | 'to3' | 'back2' | 'back1'
     | 'provision' | 'reversal' | 'writeOffTransfer' | 'writeOff'
     | 'addition' | 'derecognition' | 'other' | 'closing'
  label: string      // 变体相关（listed 首两行「上年年末余额」口径）
  stage1: number; stage2: number; stage3: number
  editable: boolean  // 结构行（openingInPeriod）与 closing 不可编辑
}
```

**旧 key → 新 key 迁移表**

| 旧 key | 新 key | 说明 |
|--------|--------|------|
| `opening` | `opening` | 不变 |
| `s1-s2` | `to2` | 转入第二阶段 |
| `s1-s3`, `s2-s3` | `to3` | 两行折叠（按方向求和） |
| `s3-s2` | `back2` | 转回第二阶段 |
| `s2-s1`, `s3-s1` | `back1` | 两行折叠 |
| `provision`（本年计提） | `provision`（本期计提） | key 不变、label 改 |
| `reversal` | `reversal` | 同上 |
| `writeoff` | `writeOff` | 本期核销 |
| `fx`（汇兑差异） | `other` | 源模板无此行 → 并入其他变动 |
| `other` | `other` | 与 `fx` 合并求和 |
| （无） | `openingInPeriod` / `writeOffTransfer` | 新增结构行 / 本期转销 |
| `collection`（本期收回或核销，balance 表） | `derecognition`（本期终止确认） | key 改、金额沿用 |
| `closing` | `closing` | 不变 |

### 附注汇总表行（`fs_reconciliation` → 子表 `其他应收款`）

| 行 | 上市列 `期末余额` | 国企列 `期末余额` | 来源 |
|----|------------------|------------------|------|
| 应收利息 | ✓ | ✓ | `fs.interest`（叶子 1132 期末） |
| 应收股利 | ✓ | ✓ | `fs.dividend`（叶子 1131 期末） |
| 其他应收款 / 其他应收款项 | ✓ | ✓ | K1-1 净值审定（回退 `fs.report_total − interest − dividend`） |
| 合计 | ✓ | ✓ | `fs.report_total`（按 BS-009 公式符号加权） |

## Correctness Properties

### Property 1: 归集口径守恒

K1-2 归集行的 `endBalance` 之和 == 归集所用 aux 条目 `closing` 之和；`beginBalance` 之和 == `opening` 之和。被 `row_limit` 截断时，返回值 `total_units > len(rows)` 且显式标 `truncated`。

**Validates: Requirements 1.1, 1.6, 12.1**

### Property 2: 手工优先幂等

对已存在同名 `counterparty` 的行重复调用归集端点，任意次数后行集与首次调用后逐字相同，且已录字段值不变。

**Validates: Requirements 1.5, 2.3**

### Property 3: K1-3 seed roll-forward 自洽

`build_k1_bad_debt_seed_from_tb` 产出的片段满足 `期初审定 + 本期计提 − 本期转回 == 期末账面`（容差 0.005 元）；备抵叶子为空时返回 `None`。

**Validates: Requirements 2.1, 2.2, 2.4**

### Property 4: 三阶段行集与模板逐字一致

`buildK1ProvisionMovementRows(variant)` 的 `label` 序列 == 附注模板对应表 `rows[].label` 序列；`buildK1BalanceMovementRows()` 同理。行标签集合内**无重复**。

**Validates: Requirements 5.1, 5.2, 5.3, 6.5**

### Property 5: 迁移不丢金额

对任意旧行集（含 13 行 provision / 11 行 balance 形态），`migrateK1MovementRows` 前后**各阶段列的总额守恒**（Σ stage1 / Σ stage2 / Σ stage3 分别相等，不含 `closing` 派生行）。

**Validates: Requirements 5.4**

### Property 6: 账龄档数 == 项目段数

对任意 2~10 段账龄配置，上市①、国企账龄表、国企账龄组合三处的数据行数均等于段数（结构行另计），且不含空档行。

**Validates: Requirements 8.1, 8.2**

### Property 7: 列元数据双路径表态

对 R6 所列每张表，附注模板 `columns` 与同步载荷 `columns` 均存在、列 `key` 序列逐字相等、且每张表要么有 `group` 要么标签列有 `flat`（三态不得为 `None`）。

**Validates: Requirements 6.9, 6.10, 11.2**

### Property 8: `_note_texts` 标题齐备

同步载荷 `_note_texts` 的每条都有非空中文 `title`；空文本被过滤；全空时不产生该键。

**Validates: Requirements 9.1, 9.2**

### Property 9: 汇总表条件推送

`fs_reconciliation` 三项全为 0 / 缺失时，汇总表**不出现**在 `sub_table_data` 中，且不出现在 `_removed_table_keys` 中。

**Validates: Requirements 4.4**

### Property 10: item_id 一致性

后端 `_K1_SPECS` 的每个 `item_id` 都出现在前端非测试源码的 item_id 字面量集合中；反之守卫允许前端有额外键。

**Validates: Requirements 3.1, 3.5**

### Property 11: 公式预设不撞键

K1 各块的 `(page_key, cell_ref)` 全局唯一（`convert_prefill_presets` 按此去重，撞键静默丢弃）；K1-2 / K1-3 块的公式串不含 `WP(`。

**Validates: Requirements 10.2, 10.4, 10.6**

### Property 12: 共享件提升零回归

`four_table/aux_aggregation.pick_aux_type` 对 F1 既有测试用例的返回值与提升前逐字相同；F1 / G7 的既有测试全绿。

**Validates: Requirements 11.5**

## Error Handling

所有四表取数路径一律 **fail-open**：依赖缺失时退回改动前行为，绝不让页面崩或让保存失败。

| 失败点 | 处理 | 用户可见 |
|--------|------|----------|
| `resolve_report_line_accounts` 查不到 `BS-009` | 退兜底码 `1221` / `1231-03`，`resolved_from='fallback'` | 溯源面板显示「兜底」彩色 tag |
| `tb_aux_balance` 无 active 数据集 / 查询异常 | 归集返回 `([], None, 0)`，端点返 `imported_count=0` 不写库 | toast「未找到科目 1221 的辅助余额数据」 |
| 归集单位数超 `row_limit` | 截断 + `truncated=True` | toast 明示「已截断，请按重要性补录其余单位」 |
| K1-3 备抵叶子为空 | `build_k1_bad_debt_seed_from_tb` 返 `None`，不写 seed | 无（宁缺勿造） |
| K1-2 已有手工行 | 同名 `counterparty` 跳过 | toast 报「新增 N 行」而非「导入 N 行」 |
| 自动 seed 端点 500 / 网络失败 | `useK1DetailAutoSeed` 静默吞（console.warn），页面正常渲染 | 无（用户可手动点按钮重试） |
| 同步到附注返回 409 `STANDARD_MISMATCH` | 前端静默不写（宁可不写也不写错章节） | 无 |
| 历史三阶段行迁移遇到未知 key | 该行金额并入 `other`（其他变动），不丢弃 | 无 |

**明确不做的兜底**：`_note_texts` 缺 `title` 时后端会回退到英文 `section` 键——本 spec
把它当**缺陷**修掉，而不是继续依赖兜底。

## Testing Strategy

四层，逐层收窄到「只有浏览器才暴露」的那类缺陷。

**1. 纯函数单测（Wave 1 / 4）** —— 无 I/O，跑得快，覆盖 Property 1~5、11。
`backend/tests/four_table/test_k1_aux_detail.py`、`test_k1_detail_seed.py`、
`test_aux_aggregation.py`；前端 `k1StageMovementRows.spec.ts`。
含 hypothesis PBT（`max_examples=5`）：归集守恒、迁移金额守恒、任意账龄段数。

**2. 结构守卫（Wave 7）** —— 三向比对，锁死 Property 4、7。
`test_note_k_complex_structure.py` 的 K1 专项用 openpyxl **直读源 xlsx** 交叉比对，
不信任任何中间产物。**每条守卫必须配反向自检**（抹 columns / 塞假行 / 改一个 label
必须打红），防守卫空转。

**3. 契约测试（Wave 7）** —— `k1NoteSubtableContract.spec.ts` 跑共享 helper 的
P1~P6 全量真断言，`columnsPending` 必须为空。读 `.ts` 源码的断言先 `stripComments()`
并对 `stripComments` 本身加反向自检（用内联 fixture，不依赖真实文件的注释）。

**4. 端到端实测（Wave 8）** —— chrome-devtools 驱动浏览器 + postgres 只读比对落库。
只有这一层能抓到三类静默缺陷：
- `fmtAmount` 误当模块导出 → 整页「页面渲染出错」（vitest 与 `get_diagnostics` 全绿）；
- 宿主无 `@save` 处理器 → 录入只在内存，刷新即丢（判据只能查 `checklist_responses`）；
- `watch(props.allResponses)` 重新 hydrate 覆盖刚录入的值。

**回归口径**：改动文件逐个 `curl http://localhost:3030/src/.../X.vue` 验 Vite transform
返 200（`get_diagnostics` 查不出 SFC 结构损坏）；前端全量失败判定只用 JSON reporter。

**上市侧限制**：8 个在册项目 `entity_type` 全为 soe → 上市变体只能靠第 2、3 层双向锁死，
Wave 8 只实测国企侧，并在 tasks.md 显式记录该限制。
