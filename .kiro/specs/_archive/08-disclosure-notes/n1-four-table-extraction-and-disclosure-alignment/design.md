# Design Document

## Overview

本设计把 N1 的「四表库 → 底稿 → 附注」链路补成闭环，并把两张披露表与附注两节的结构
回归源模板。核心判断依据全部来自两次只读实证：

**实证 1 —— 科目映射真源（`report_config` DB，4 准则一致）**

| row_code | row_name | formula | 准则覆盖 |
|---|---|---|---|
| `BS-036` | 递延所得税资产 | `TB('1811','期末余额')` | listed_standalone / listed_consolidated / soe_standalone / soe_consolidated |
| `BS-067` | 递延所得税负债 | `TB('2901','期末余额')` | 同上 |

对照发现仓库里三个写法（`BS-036` / `BS-049` / `BS-018`）只有 `BS-036` 正确：
`BS-018` 实为「流动资产合计」(listed) 与「存货」(soe)，`BS-049` 实为「应交税费」。

**实证 2 —— 活体科目表叶子编码（`tb_balance`，跨 9 个项目一致）**

```
1811.01 递延所得税资产_公允价值变动          → 公允价值变动
1811.02 递延所得税资产_资产减值准备          → 资产减值准备
1811.03 递延所得税资产_长期职工薪酬          → 其他
1811.04 递延所得税资产_可抵扣亏损            → 可抵扣亏损
1811.05 递延所得税资产_预提费用相关          → 其他
1811.06 递延所得税资产_递延收益相关          → 其他
1811.07 递延所得税资产_经营租赁和企业年金    → 租赁负债

2901.01 递延所得税负债_公允价值变动          → afs_fv
2901.02 递延所得税负债_固定资产加速折旧      → depreciation
2901.03 递延所得税负债_经营租赁相关          → lease
```

叶子聚合逐分可验（项目 `0ec33ac9` 数据集 A：`.02` 3,983,376.55 + `.04` 1,172,298.25 +
`.05` 2,893,025.00 = 8,048,699.80 = 父级 `1811` 期末余额）。

**关键设计杠杆**：后端 `_N1_ADJUDICATION_CATEGORIES` 的 7 类与前端 `N1_ASSET_ITEMS` 的 7 项
**逐字同构**（两处独立演进却收敛到同一源模板 R13:R19）。因此披露表资产段的四表直通
**不需要新增任何后端取数**，直接复用既有 `adjudication_prefill` 输出即可。负债段才需要新增。

## Architecture

### 取数链路（改造后）

```
ledger 导入 → ledger_datasets(status=active)
  → tb_balance / trial_balance            [四表库]
        │
        │  唯一查询入口
        ▼
  dataset_query.get_active_filter(db, TbBalance.__table__, project_id, year)
        │
        │  科目映射（本次接入）
        ▼
  report_account_mapping.resolve_report_line_account_codes(db, pid, row_code, fallback)
        ├── 'BS-036' → ['1811']   资产侧
        └── 'BS-067' → ['2901']   负债侧
        │
        ▼
  _n1_deferred_tax_assets.render(ctx) → html_data
        ├── trial_balance            资产侧科目级/叶子聚合余额     [已有，改为走映射]
        ├── trial_balance_liability  负债侧科目级/叶子聚合余额     [新增]
        ├── adjudication_prefill     1811 叶子 → 资产段 7 类       [已有，新增消费方]
        ├── liability_prefill        2901 叶子 → 负债段 5 语义槽   [新增]
        └── tb_source_codes          取数溯源                      [新增]
        │
        ▼  GET /workpapers/{id}/render-config
  useN1FormData.selfLoad() → { tbValues, tbLiability, adjudicationPrefill, liabilityPrefill, tbSourceCodes }
        │
        ├──→ N1TabAdjudication   （审定表，已通）
        └──→ N1TabDisclosure{Listed,Soe}
                 useN1DisclosureTables.restore()
                    ├── applyDetailPrefill()      N1-2 明细按类别（优先级 1）
                    ├── applyTbAssetPrefill()     四表 7 类（优先级 2，新增）
                    ├── applyTbLiabilityPrefill() 四表 5 槽（优先级 2，新增）
                    └── applyLossPrefill()        N1-5 亏损
                 │
                 ▼  buildN1SyncPayload
        POST /disclosure-notes/sync-from-workpaper
                 ▼
        disclosure_notes（五、30 / 八、31）→ note_sub_table_projector 读时投影
```

### 预填优先级（手工优先，三级回退）

```
手工录入        （任一值非空 → 全行锁定，不覆盖）
   ↑
N1-2 明细派生    （含暂时性差异列，信息最全）
   ↑
四表叶子聚合      （只有递延所得税金额，暂时性差异留 null）
   ↑
空骨架           （null，不写 0）
```

### 结构对齐的施加位置

| 层 | 载体 | 手段 |
|---|---|---|
| 附注模板 JSON | `note_template_{listed,soe}.json` | 扩展既有幂等脚本 `fix_note_deferred_tax_structure.py`（`--dry-run` / `--check`） |
| 披露表行骨架 | `useN1DisclosureTables.ts` | 纯函数常量 + 派生 computed |
| 同步载荷 | `n1NoteSectionMap.ts` | `buildN1SyncPayload` 加 `_removed_table_keys` |
| 公式预设 | `prefill_formula_mapping.json` | 删除误挂块 + 补齐 cells |

## Components and Interfaces

### 后端

#### `_n1_deferred_tax_assets.py`（改造）

```python
_ASSET_ROW_CODE = "BS-036"          # DB 实证：递延所得税资产
_LIABILITY_ROW_CODE = "BS-067"      # DB 实证：递延所得税负债
_ASSET_FALLBACK = ["1811"]
_LIABILITY_FALLBACK = ["2901"]

# 负债段 5 语义槽（源模板 R23:R27；两版第 4 项中文名不同故用英文键）
_N1_LIABILITY_SLOTS = ["depreciation", "afs_fv", "investment_property_fv", "lease", "other"]

def _classify_n1_liability_subaccount(name: str | None) -> str:
    """负债侧子科目名 → 语义槽（纯函数，可单测）。

    判定顺序有意如此：`投资性房地产` 必须先于泛化的 `公允价值`，
    否则 2901.01「公允价值变动」与投资性房地产条目会互相抢占。
    """

async def _resolve_account_codes(ctx, row_code, fallback) -> list[str]:
    """走 resolve_report_line_account_codes，异常/空一律回退 fallback（fail-open）。"""

async def _fetch_tb_for_codes(ctx, codes) -> dict[str, Any]:
    """科目级优先 → 无则叶子聚合。资产/负债共用，避免双写。"""

async def _build_liability_prefill(ctx, codes) -> dict[str, dict[str, float]]:
    """叶子子科目 → 语义槽聚合；全零槽跳过；只有父级时返回 {}。

    负债类为贷方科目，tb_balance 存在「负数 + 方向列」与「绝对值 + 方向列」两种
    约定并存（活体实测 2901 期末既有 -233512.19 也有 200530.32）→ 统一取 abs()
    归一为披露口径的正数。
    """
```

`render()` 返回值新增 4 键（既有键不动，保证零回归）：

```python
{
  ...
  "trial_balance_liability": {...},
  "liability_prefill": {"lease": {"opening": 528013.88, "closing": 233512.19}, ...},
  "tb_source_codes": {
      "asset":     {"row_code": "BS-036", "codes": ["1811"]},
      "liability": {"row_code": "BS-067", "codes": ["2901"]},
  },
}
```

> **不设 `resolved` 标志位**：`resolve_report_line_account_codes` 内部 `return codes or list(fallback)`，
> 命中映射与回退 fallback 在返回值上**不可区分**（`BS-036` 解析结果恰好等于 fallback `['1811']`）。
> 要区分就得在本模块重实现一遍它的项目级/标准级优先级查询 —— 得不偿失且必然漂移。
> 故只输出 `{row_code, codes}`，前端展示「取数科目 1811（报表行 BS-036）」，不谎报来源。

#### `fix_note_deferred_tax_structure.py`（扩展）

复用既有 `_row` / `_subtotal` / `_total` / `_unoffset_table` / `_flat_table` 构造器，
改动集中在行常量与 `report_row_code`：

```python
# 源模板 R13:R19（与前端 N1_ASSET_ITEMS、后端 _N1_ADJUDICATION_CATEGORIES 三处同构）
_SRC_ASSET_ITEMS = ["资产减值准备", "可抵扣亏损", "内部交易未实现利润", "公允价值变动",
                    "租赁负债", "购入摊销年限小于税法规定的资产", "其他"]
# 源模板 R23:R27（第 4 项分变体）
_SRC_LIABILITY_ITEMS = {
    "listed": [..., "使用权资产", "其他"],
    "soe":    [..., "租赁形成", "其他"],
}
_ASSET_ROW_CODE = "BS-036"
_LIABILITY_ROW_CODE = "BS-067"
# 白名单：附注行只许挂递延所得税科目
_ALLOWED_ACCOUNT_CODES = {"1811", "2901"}
```

新增动作：`drop_placeholder_rows()`（删 `……`）、`retitle_report_row_codes()`、
`strip_underlying_account_codes()`、`drop_text_section()`（删截断段）。

### 前端

#### `useN1DisclosureTables.ts`（改造）

```ts
/** 负债段语义槽 → 两版显示名（单一真源，禁在别处写字面量） */
export const N1_LIABILITY_SLOT_LABEL: Record<N1LiabilitySlot, Record<N1DisclosureVariant, string>>

/** 语义槽顺序 = 源模板 R23:R27 行序 */
export const N1_LIABILITY_SLOTS = ['depreciation','afs_fv','investment_property_fv','lease','other'] as const

/** 亏损到期骨架：源模板 6 行 = auditYear .. auditYear+5 */
export function defaultLossExpiryRows(auditYear: number): LossExpiryRowModel[]

/** 国企 (2)A 行标签镜像表 (1)（源模板 A36='=A13'） */
export function mirrorNetOffsetRows(
  src: readonly UnoffsetRowModel[],
  prev: readonly NetOffsetRowModel[],
): NetOffsetRowModel[]

/** 披露分支模式（源模板国企 R7 二选一 / 上市 R33「不适用的删除」） */
export type N1OffsetMode = 'gross' | 'net'
```

新增 options：`adjudicationPrefill` / `liabilityPrefill`（`Ref`，由宿主从 render-config 透传）。

#### `n1NoteSectionMap.ts`（改造）

`buildN1SyncPayload` 增加 `offsetMode` 与 `netOffsetApplicable`，据此：
- 跳过未选分支的子表；
- 通过既有 `buildRemovedTableKeys({previouslySynced, legacyObsolete, pushed})` 输出
  `_removed_table_keys`。

## Data Models

### `liability_prefill`（render-config → 前端）

```ts
type N1LiabilitySlot =
  | 'depreciation'            // 购入摊销年限大于税法规定的资产
  | 'afs_fv'                  // 可供出售金融资产公允价值变动
  | 'investment_property_fv'  // 投资性房地产公允价值变动
  | 'lease'                   // 使用权资产(listed) / 租赁形成(soe)
  | 'other'                   // 其他

interface N1LiabilityPrefill {
  [slot: string]: { opening: number; closing: number }
}
```

### `tb_source_codes`

```ts
interface N1TbSourceEntry {
  row_code: string   // 'BS-036' | 'BS-067'
  codes: string[]    // 解析出的科目集
  resolved: boolean  // false = 走了 fallback
}
interface N1TbSourceCodes { asset: N1TbSourceEntry; liability: N1TbSourceEntry }
```

### 披露分支持久化

| item_id | 字段 | 值 |
|---|---|---|
| `N1-disclosure-soe-offset-mode` | `conclusion` | `'gross'` \| `'net'` |
| `N1-disclosure-listed-netoffset-applicable` | `conclusion` | `'1'` \| `'0'` |

### 附注模板行契约（seed 路径）

| 章节 | 表 | 行数 | 结构 |
|---|---|---|---|
| 五、30 | 未经抵销… | 1+7+1+1+5+1 = 16 | 资产段标题 + 7 项 + 小计 + 负债段标题 + 5 项 + 小计 |
| 五、30 | 以抵销后净额… | 2 | 递延所得税资产 / 递延所得税负债 |
| 五、30 | 未确认…明细 | 3 | 2 项 + 合计 |
| 五、30 | 亏损到期 | 7 | 6 年 + 合计 |
| 八、31 | 未经抵销… | 16 | 同上（负债段第 4 项「租赁形成」） |
| 八、31 | 以抵销后净额… | 16 | 镜像表 1 |
| 八、31 | 互抵明细 | 0 | 纯动态行区域（源模板 R56:R58 全空） |
| 八、31 | 未确认…明细 | 3 | 2 项 + 合计 |
| 八、31 | 亏损到期 | 7 | 6 年 + 合计 |

## Correctness Properties

### Property 1: 科目映射解析恒不阻断渲染

对任意 `row_code` 与任意 DB 状态（含查询抛错、无记录、公式为 `null`），
`_resolve_account_codes` 恒返回非空科目集：命中映射时返回解析结果，
其余一切情况返回 `fallback`。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 叶子聚合不双算

对任意科目集与任意 `tb_balance` 层级结构，若存在科目级精确行则只用它；
否则取的行集中不存在任何两行 `a`、`b` 满足 `b.account_code` 以 `a.account_code + '.'` 为前缀。

**Validates: Requirements 2.1, 2.2**

### Property 3: 负债槽分类全覆盖且互斥

`_classify_n1_liability_subaccount` 对任意字符串输入恒返回 `_N1_LIABILITY_SLOTS` 之一；
且含「投资性房地产」的名称恒归 `investment_property_fv`（优先于泛化 `公允价值` 判定）。

**Validates: Requirements 2.3, 2.7**

### Property 4: 预填手工优先且不写 0

对任意预填输入与任意现有行状态，若某行存在任一非空值则该行四个值均不被修改；
且预填值为 0 或缺失时写入 `null` 而非 `0`。

**Validates: Requirements 3.1, 3.2, 3.5, 3.6**

### Property 5: 预填优先级单调

同一行同时可由 N1-2 明细与四表叶子供数时，结果恒等于 N1-2 明细派生值。

**Validates: Requirements 3.3**

### Property 6: 亏损到期骨架年度连续且为 6 行

对任意 `auditYear`，`defaultLossExpiryRows(auditYear)` 返回恰好 6 行，
标签依次为 `auditYear年` … `auditYear+5年`。

**Validates: Requirements 4.1**

### Property 7: 净额表行镜像幂等且保值

`mirrorNetOffsetRows(src, prev)` 的输出行数与标签恒等于 `src`；
对 `src` 中标签未变的行，`prev` 中同标签行的金额恒被保留；重复调用结果不变。

**Validates: Requirements 4.2**

### Property 8: 二选一分支的推送与清理互补

对任意 `offsetMode`，同步载荷推送的子表键集与 `_removed_table_keys` 恒无交集，
且两者并集恒覆盖该变体全部分支表键。

**Validates: Requirements 4.3, 4.4, 4.5**

### Property 9: 附注模板行集逐字等于源模板

对两个变体，seed 出的资产段/负债段明细行标签序列，
恒逐字等于直读源模板 xlsx 对应单元格区段（`openpyxl` 交叉比对）。

**Validates: Requirements 5.1, 5.2, 5.5**

### Property 10: 附注模板无占位假行且科目白名单成立

seed 出的任何表的任何行标签不含 `……`；
任何携带 `account_codes` 的行，其科目集 ⊆ `{1811, 2901}`；
任何携带 `report_row_code` 的行，其值 ∈ `{BS-036, BS-067}`。

**Validates: Requirements 5.3, 5.4, 5.6, 5.7, 5.8**

### Property 11: 幂等脚本幂等

连续两次 `apply()` 的结果字节相同；`apply()` 后 `--check` 恒报 0 欠账。

**Validates: Requirements 5.9**

### Property 12: N1 公式预设科目纯净且可解析

`workpaper:N1` 的全部预设表达式中出现的科目码恒以 `1811` / `2901` / `4104` 之一开头
（`4104` 未分配利润是源模板 N1-5 R14「期末未分配利润」的账面金额列口径，
报表行 `BS-088` 已 DB 实证）；区间求和的首尾恒属同一科目大类；
`cell_ref` 在 `wp_code=N1` 内恒唯一（因 `page_key` 忽略 sheet，同名必互相遮蔽）；
每条表达式经 `validate_formula` 无错误 —— 其中 `ADJ()` 属 prefill 引擎专属函数
（未注册进 `formula_engine._REGISTRY`），按 prefill 词汇表放行并配反向自检防豁免长挂。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**

## Error Handling

| 失败点 | 策略 | 理由 |
|---|---|---|
| `resolve_report_line_account_codes` 抛错 / 无记录 / 公式为 null | 回退 fallback 科目集，`logger.warning` | 取数是渲染的增强项，不得阻断底稿打开 |
| `tb_balance` 查询抛错 | 返回空 dict，`logger.warning` | 同上；前端表现为「无预填」而非白屏 |
| 只有父级科目无子科目 | 返回 `{}`（不虚构分类） | 宁缺勿造；审定表 TB 核对行仍显总额做反向校验 |
| 负债类符号约定不一致 | 统一 `abs()` 归一 | 活体实测 `2901` 期末同时存在 `-233512.19` 与 `200530.32` 两种约定 |
| 前端 render-config 缺新键 | `?? {}` 兜底，预填静默跳过 | 后端未重启时不能让披露表报错 |
| 同步 POST 返 409 `STANDARD_MISMATCH` | 静默吞（既有平台行为） | 宁可不写也不写错章节 |
| 幂等脚本目标章节不存在 | 报错并 exit 非 0 | 章节缺失是真问题，不能静默跳过 |

## Testing Strategy

**后端**

| 文件 | 覆盖 |
|---|---|
| `backend/tests/test_n1_account_mapping.py`（新增） | Property 1/2/3：映射 fail-open、叶子不双算、负债槽分类（含「投资性房地产」优先级与反向自检） |
| `backend/tests/test_n1_liability_prefill.py`（新增） | Requirement 2 全条：槽聚合、全零跳过、只有父级返回 `{}`、异常 fail-open、`abs()` 归一 |
| `backend/tests/services/test_note_deferred_tax_structure.py`（扩展） | Property 9/10/11：`openpyxl` 直读源模板交叉比对行集、`……` 归零、科目/报表行白名单、幂等 |
| `backend/tests/formula_management/test_n1_preset_purity.py`（新增） | Property 12：`workpaper:N1` 预设科目纯净 + `validate_formula` 全通 |

**前端**

| 文件 | 覆盖 |
|---|---|
| `composables/__tests__/n1DisclosurePrefill.spec.ts`（新增） | Property 4/5：手工优先、不写 0、N1-2 优先于四表 |
| `composables/__tests__/n1LossExpirySkeleton.spec.ts`（新增） | Property 6：6 行连续年度（PBT） |
| `composables/__tests__/n1NetOffsetMirror.spec.ts`（新增） | Property 7：镜像幂等保值（PBT） |
| `composables/__tests__/n1NoteSectionMap.spec.ts`（扩展） | Property 8：分支推送与 `_removed_table_keys` 互补 |
| `composables/__tests__/n1NoteSubtableContract.spec.ts`（扩展） | 共享 helper P1~P6 + 新增分支表键断言 |

**实测**（chrome-devtools MCP 驱动 + postgres MCP 只读比对）

活体项目候选：`0ec33ac9`（1811 期末 8,048,699.80，含 `.02/.04/.05` 三个非零叶子；
`§五、23` 的 `source_template=listed` → 可测上市变体）与 `2aa00f57`（国企模板，
2901 有非零余额 `233,512.19`）。

验证点：披露表打开即有数 → 「推送到附注」→ `disclosure_notes.last_sync_at` 前移、
`sub_table_data` 表数与列元数据正确、切换二选一后孤儿表被清。**验证后复原测试数据**。

**已知不可验项**：`trial_balance` 在项目 `2aa00f57` 上是 `tb_balance` 的 2 倍
（1,633,716.86 vs 816,858.43），系该项目存在两份数据集的既有数据卫生问题，
非本 spec 引入，实测时改用 `0ec33ac9` 规避。
