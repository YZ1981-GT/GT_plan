# Design Document

## Overview

E1 货币资金的四表取数与披露/附注对齐。设计原则三条：

1. **不造轮子** —— 后端取数全部委托 `app/services/four_table/`（D1/K1/K2/F1/G7 已四次验证），删掉 E1 自造的 `_fetch_leaf_accounts`/`_is_leaf`
2. **单一真源 + 双向锁死** —— 科目走 `BS-002` 报表行解析；币种/受限类别走 per-cycle scope 模块；附注结构由 openpyxl 直读源 xlsx 的守卫三向锁死
3. **宁缺勿造** —— 受限类别无法从叶子名自动分类（活体叶子名是银行户名/支付渠道名）→ 只做关键字命中建议；外币章节跨循环共享 → 只推「货币资金」段、不扩列

与已完成循环的差异点：

| 维度 | E1 特殊性 | 处理 |
|------|----------|------|
| 备抵科目 | **无**（货币资金不计提减值） | `ReportLineAccountSpec` 不设 `provision_row_code`，溯源面板不传 `provisionLabel` |
| 枚举维度 | 无账龄，改为**币种 + 受限类别** | 同款「枚举驱动 + 动态插行 + 稳定 key」 |
| 外币表落点 | **跨循环共享章节** 五、73 / 八、92 | 只推「货币资金」段，投影为附注 4 列 |
| 三层科目 | `1012.014` + `.01/.02` 实证存在 | 共享件 `select_leaves` 天然处理 |
| 零余额账户 | 银行账户完整性核对**需要**零余额账户 | `account_list` 不过滤，金额预填才过滤 |

## Architecture

```
四表入库 (tb_balance / trial_balance)
   │
   ├─ report_config: BS-002 = TB('1001')+TB('1002')+TB('1012')   ← 科目单一真源（四准则一致）
   │       │
   │       ▼
   │  four_table.resolve_report_line_accounts(ctx, E1_ACCOUNT_SPEC)
   │       │  → ReportLineAccounts{gross_standard, gross(原始码), resolved_from}
   │       ▼
   │  four_table.select_leaves / aggregate_leaves   ← 叶子和 == 父额（点号边界安全）
   │       │
   ▼       ▼
_e1_monetary_fund.render()
   ├─ project_context.tb_source_codes  (平台标准 dict)  ──┐
   ├─ project_context.tb_amount / tb_amount_opening       │
   ├─ four_table_prefill{cash,bank,other,account_list}    │
   └─ adjudication_prefill{cash,bank,other × 期初/期末}   │
           │                                              │
           ▼                                              ▼
   E1TabCashDetail / E1TabBankDetail        WpFourTableSourcePanel (平台共用件)
   E1TabDigitalCurrency                     ← 消除 dead output
           │
           ▼
   E1TabAdjudication (E1-1)  ←「从四表库带入未审数」+ 溯源条
           │  E1-adj-total-{1001|1002|1012}(-opening)
           ▼
   E1TabDisclosure (两变体)
     ├─ 主表   ← 跨 sheet 只读取数
     ├─ 外币性货币项目表 (7列两级, 派生)
     ├─ 货币资金原币表   (7列两级, 录入)   ← 币种枚举驱动
     └─ 受限制的货币资金明细 (soe / listed待裁决) ← 受限类别枚举驱动
           │
           │ buildE1SyncPayload / buildE1FxSyncPayload
           ▼
   POST /api/projects/{id}/disclosure-notes/sync-from-workpaper
           │
           ├─ 五、1 / 八、1「货币资金」   (主表 + ②受限表 + _note_texts)
           └─ 五、73 / 八、92「外币货币性项目」(仅「货币资金」段)
```

### 关键链路：四表入库 → 底稿有数据

用户要求「四表入库后能刷新取数的底稿就都有数据」。E1 的级联根有两条：

- **金额链**：`tb_balance` 叶子 → `four_table_prefill` → E1-2/E1-3/E1-4 明细表（transient seed，手工优先）→ E1-1 审定表汇总 → `E1-adj-total-*` → 披露表主表
- **账户链**：`tb_balance` 的 `1002` 叶子（**含零余额**）→ `account_list` → E1-10 已开立银行账户清单核对

> **重要：E1 明细表读的是 transient seed（`four_table_prefill`）还是持久化？** 现状 `E1FourTableSourcePanel` 提供「🔄 重新从四表取数」按钮做 persist 覆盖，说明明细表读持久化 + 按钮触发落库。F1 的教训是「下游读持久化则必须落库，transient 不级联」。E1-1 审定表读的是 `E1-adj-total-*`（持久化），因此**保留现有 persist 语义**，只补：①空表时自动 seed（同 `useF1DetailAutoSeed` 范式）②`findRowForPrefill` **科目码优先于行名**（改名不重复插行）③已有金额有变化时弹确认（同 K2 `previewSeedFromPrefill`）。

## Components and Interfaces

### 后端

**`backend/app/routers/wp_render_strategies/_e1_monetary_fund.py`（重写取数段）**

```python
E1_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-002",
    fallback_gross=("1001", "1002", "1012"),
    # 货币资金无备抵科目 → 不设 provision_row_code / fallback_provision
)

# 三个语义槽（对应披露主表行），由解析出的标准码分派
E1_SLOTS = {"cash": "1001", "bank": "1002", "other": "1012"}

async def _load_e1_leaves(ctx, year) -> dict[str, list[LeafRow]]: ...      # 一次查询 + 按槽分组
def build_e1_tb_values(leaves) -> dict[str, float]: ...                    # 纯函数
def build_e1_account_list(leaves) -> list[dict]: ...                       # 纯函数，含零余额
def build_e1_adjudication_prefill(leaves) -> dict: ...                     # 纯函数
def build_e1_source_codes(resolved) -> dict: ...                           # 平台标准 tb_source_codes
```

**删除**：`_CASH_PREFIX` / `_BANK_PREFIX` / `_OTHER_PREFIX` / `_fetch_leaf_accounts` / `_is_leaf`

**`backend/app/services/four_table/e1_restricted_buckets.py`（受限分类单一真源，新建共享件）**

```python
@dataclass(frozen=True)
class E1RestrictedBucket:
    key: str
    label: str                      # 逐字取自源 xlsx
    keywords: tuple[str, ...]       # 名称命中词
    exclude_keywords: tuple[str, ...]  # 否决词
    source_ref: str                 # 如 "附注披露信息(国企)!A17"，供 openpyxl 守卫反查

# 顺序即优先级（守卫钉死）：含包含关系的必须先声明
E1_RESTRICTED_BUCKETS: tuple[E1RestrictedBucket, ...] = (
    # 「信用证保证金」先于「银行承兑汇票保证金」——两者都含「保证金」
    E1RestrictedBucket("letter_of_credit", "信用证保证金", ("信用证",), (), "…!A18"),
    E1RestrictedBucket("bank_acceptance",  "银行承兑汇票保证金", ("银行承兑", "承兑汇票"), (), "…!A17"),
    E1RestrictedBucket("performance",      "履约保证金", ("履约",), (), "…!A19"),
    # 「担保」先于泛「定期存款/通知存款」
    E1RestrictedBucket("pledged_deposit",  "用于担保的定期存款或通知存款",
                       ("担保", "质押", "冻结", "定期存款", "通知存款"), ("结构性",), "…!A20"),
    E1RestrictedBucket("overseas",         "放在境外且资金汇回受到限制的款项",
                       ("境外", "海外"), (), "…!A21"),
    E1RestrictedBucket("other",            "其他受限资金", ("受限", "保证金"), (), "(平台补充)"),
)

def classify_e1_restricted_leaf(name: str) -> str | None: ...   # 未命中返 None（宁缺勿造）
def bucket_defs_payload() -> list[dict]: ...                    # 下发前端，中文标签只一份
```

**`backend/scripts/fix/fix_note_e1_monetary_fund_structure.py`（幂等脚本）**

复用 `_note_structure_kit`：`flat_columns` / `rule` / `run_section` / `build_cli`。作用域 = `五、1` + `八、1`（外币 `五、73`/`八、92` **只补 columns 不动 rows**，因跨循环共享）。

**`backend/scripts/fix/fix_e1_prefill_presets.py`（幂等脚本）**

纠正 `1502` / `分析程序E1-3` / `TB_SUM('1001~1012')`，补两张披露 sheet 块 + E1-1 的 `WP()` 联动。

### 前端

| 文件 | 动作 | 说明 |
|------|------|------|
| `e1/E1TabDisclosure.vue` | **修 TDZ** + 重构 | watch 下移；删重复 type；接 `useHostApplicableStandards`；金额换 `WpAmountInput` |
| `composables/e1CurrencyScope.ts` | **新建** | 币种枚举单一真源 + `e1CurrencyRowKey(slot, seq)` 稳定 key |
| `composables/e1RestrictedScope.ts` | **新建** | 受限类别枚举（镜像后端桶定义）+ 人工归类 map 读写 + `resolveRestrictedRows()` 合并自动分类与人工归类 |
| `e1/E1RestrictedUnclassifiedPanel.vue` | **新建** | 「待归类科目」面板：列出 `unclassified` 叶子，点选归入某类 / 新建自定义类别 / 标记不受限 |
| `composables/e1NoteSectionMap.ts` | 扩展 | 补 `flat`、`_removed_table_keys`、多段 `_note_texts`、`E1_NOTE_TOTAL_LABEL`、②表条件表语义 |
| `composables/e1FxNoteSectionMap.ts` | **新建** | 外币 → 五、73/八、92，只推「货币资金」段 |
| `composables/e1DisclosureConsistency.ts` | **新建** | F1-1~F1-6 + 源 xlsx 两条勾稽（纯函数） |
| `e1/E1FourTableSourcePanel.vue` | 改薄壳 | 委托平台 `WpFourTableSourcePanel.vue`，无备抵不传 `provisionLabel` |
| `e1/E1TabAdjudication.vue` | 扩展 | 「从四表库带入未审数」+ 溯源条 |
| `e1/E1TabCashCount.vue` / `E1TabCreditReport.vue` | 替换 | `el-input-number :formatter` → `WpAmountInput`（EP 2.13.6 无该 prop） |

### 守卫

| 守卫 | 层 | 内容 |
|------|-----|------|
| `test_e1_account_scope.py` | 后端 | `BS-002` 解析、叶子和 == 父额、零余额账户保留、无备抵、点号边界反向自检 |
| `test_note_e1_structure.py` | 后端 | openpyxl 直读源 xlsx ↔ 模板 headers/rows ↔ 载荷 columns 三向；guidance 禁 markdown；反向自检 |
| `test_e1_formula_presets.py` | 后端 | `1502` 不复活；sheet 名 ∈ 源 xlsx tabs；`account_codes` ∈ 标准科目表 ∩ 本循环报表行；明细块禁 `WP()` |
| `e1SetupOrder.spec.ts` | 前端 | **所有 `watch(` 被监听标识符声明行号 < watch 行号**（防 TDZ 复发），含反向自检 |
| `e1NoteSubtableContract.spec.ts` | 前端 | 共享 helper P1~P6 + 单级表必标 `flat` + 表名逐字 |
| `e1CurrencyScope.spec.ts` | 前端 | 组件源码不得出现币种/受限类别字面量；稳定 key 不撞键 |

## Data Models

### `tb_source_codes`（平台标准形态，消除 dead output）

```ts
interface E1TbSourceCodes {
  gross_standard: string[]      // ['1001','1002','1012']
  gross_original: string[]      // account_mapping 反解后的客户原始码前缀
  resolved_from: 'report_config' | 'fallback'
  report_row_code: 'BS-002'
  formula: string               // "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
  // 无备抵科目 → 不含 provision_* 字段
}
```

### `adjudication_prefill`

```ts
interface E1AdjudicationPrefill {
  cash:  { opening: number; closing: number; accountCode: string }
  bank:  { opening: number; closing: number; accountCode: string }
  other: { opening: number; closing: number; accountCode: string }
}
```

### 币种枚举与稳定 key

```ts
export interface E1Currency { key: string; label: string; isBase: boolean }
export const E1_DEFAULT_CURRENCIES: readonly E1Currency[] = [
  { key: 'cny', label: '人民币', isBase: true },
  { key: 'usd', label: '美元',  isBase: false },
  { key: 'jpy', label: '日元',  isBase: false },
  { key: 'aud', label: '澳元',  isBase: false },
  { key: 'eur', label: '欧元',  isBase: false },
]
// 原币表分组（源 xlsx R38/R44/R50/R56）
export const E1_FX_GROUPS = ['库存现金', '银行存款', '银行存款中：财务公司存款', '其他货币资金'] as const
// 行 key = `${groupSlot}_${currencyKey}_${seq}`；**禁用 label 作 key**（自定义币种可能同名）
```

### 外币表两级列（底稿侧，源 xlsx 7 列）

```ts
const FX_COLUMNS: ColumnDef[] = [
  { key: 'label',      label: '项  目',     is_label: true },   // rowspan=2 → 不给 group
  { key: 'end_fx',     label: '原币金额',   group: '期末数', format: 'amount' },
  { key: 'end_rate',   label: '折算率',     group: '期末数', format: 'rate'   },
  { key: 'end_rmb',    label: '人民币金额', group: '期末数', format: 'amount' },
  { key: 'begin_fx',   label: '原币金额',   group: '期初数', format: 'amount' },
  { key: 'begin_rate', label: '折算率',     group: '期初数', format: 'rate'   },
  { key: 'begin_rmb',  label: '人民币金额', group: '期初数', format: 'amount' },
]
```

> 推送到附注 `五、73`/`八、92` 时**投影为 4 列**（`项目 / 期末外币余额 / 折算汇率 / 期末折算人民币余额`，`flat`），期初留在底稿 —— 该章节跨循环共享，扩列须另立平台级 spec。

### `restricted_prefill`（受限资金动态取数）

```ts
interface E1RestrictedPrefill {
  buckets: Record<string, { opening: number; closing: number; codes: string[] }>
  /** 未命中任何桶的货币资金叶子 —— 「项目科目各不相同」的兜底通道，禁静默丢弃 */
  unclassified: Array<{ code: string; name: string; opening: number; closing: number }>
  source: { report_row_code: 'BS-002'; gross_standard: string[]; resolved_from: string }
}
```

**候选集来自映射规则，不跨出货币资金族**：`BS-002` 解析 → `account_mapping` 反解为项目原始码前缀 → `select_leaves` 取叶子 → 逐叶子 `classify_e1_restricted_leaf(name)`。

**人工归类优先**（持久化 `E1-disclosure-{variant}-restricted-map`）：

```
原始科目码 → bucketKey | '__unrestricted__'
```

合并顺序：人工归类 > 自动分类 > `unclassified`。四表新增科目自动落入 `unclassified`，不会污染已有类别行。

### 附注载荷主表（投影成附注形状）

```ts
// listed 五、1：['项目','期末余额','上年年末余额']  soe 八、1：['项目','期末余额','期初余额']
// key 不动（label 分变体），全部标 flat
{ label: string; end_amount: number; prior_amount: number; is_total?: boolean }
```

## Correctness Properties

### Property 1: 叶子和等于父科目额

对 `1001`/`1002`/`1012` 每一族，`aggregate_leaves` 的期初/期末合计必须等于该族父科目 `tb_balance` 的对应余额（容差 0.005）。活体 `df5b8403` 已验：`1002` 期末 20,751,212.11、`1012` 期末 461,130.20。

**Validates: Requirements 2.1, 2.5**

### Property 2: 点号边界安全

给定同时含 `1002.1` 与 `1002.11` 的科目集合，叶子选取结果必须同时包含 `1002.1` 与 `1002.11`（旧 `startswith` 实现会丢掉 `1002.1`，该用例必须在旧实现下失败）。

**Validates: Requirements 2.1, 2.2**

### Property 3: 零余额银行账户不丢失

`account_list` 的账户数必须等于 `1002` 族叶子总数（不受金额过滤影响）；而 `four_table_prefill.bank` 的金额行可少于它。活体 `df5b8403` 的 `1002` 有 50+ 个零余额账户，全部须出现在 `account_list`。

**Validates: Requirements 2.6**

### Property 4: 科目解析无字面量兜底泄漏

`build_e1_source_codes` 的 `resolved_from == 'report_config'` 时，`gross_standard` 必须来自 `BS-002` 公式解析；`1001`/`1002`/`1012` 三个字面量在 `_e1_monetary_fund.py` 中只允许出现在 `ReportLineAccountSpec.fallback_gross` 与 `E1_SLOTS` 两处。

**Validates: Requirements 2.3, 2.4**

### Property 5: 附注模板与源 xlsx 三向一致

对 `五、1` / `八、1`：模板 `tables[].name` 与 `rows[].label` 必须与 openpyxl 直读源 xlsx 的对应区域逐字一致（经归一化处理小节编号/「其中：」/尾冒号/多空格）；模板 `columns[].key` 必须与 `e1NoteSectionMap.ts` 的列键逐字一致。反向自检：故意打乱一个行名，守卫必须失败。

**Validates: Requirements 5.1, 5.3, 5.4, 5.5, 5.9**

### Property 6: 单级表必须显式 flat（seed 与推送两处）

`五、1`/`八、1`/`五、73`/`八、92` 的全部表在**模板 `columns`** 与**同步载荷 `columns`** 两处都必须至少一列带 `flat: true` 且不得声明 `group`；否则 `_infer_groups_from_headers` 会推出凭空父表头。

**Validates: Requirements 5.1, 7.3, 8.2**

### Property 7: setup 声明顺序（防 TDZ 复发）

`E1TabDisclosure.vue` 中每个 `watch(` 调用所引用的顶层 `const` 标识符，其声明行号必须小于该 `watch` 的行号。反向自检：把 watch 移到声明前，守卫必须失败。

**Validates: Requirements 1.1, 1.2, 1.4**

### Property 8: 外币段推送不越界

`buildE1FxSyncPayload` 产出的行键集合必须是「货币资金」段行键的子集；与 `五、73`/`八、92` 中他循环段行键（应收账款/短期借款/长期借款/应付债券）的交集必须为空；`_removed_table_keys` 与本次推送键的交集必须为空。

**Validates: Requirements 7.1, 7.2, 7.4**

### Property 9: 派生列读时推导

`人民币金额 = 原币金额 × 折算率`、外币性货币项目表各行 = 原币表对应四段之和、主表合计行 = 明细行之和 —— 三者均为 computed，持久化载荷中不含这些字段的独立存储值。

**Validates: Requirements 9.2, 10.3**

### Property 10: 受限类别宁缺勿造

`classify_e1_restricted_leaf(name)` 对活体实证的叶子名（「金华招行基本户801」「金华支付宝」「微信小程序」「聚合收款」「AFO」「小桔有车」「金华结构性存款账户」）必须全部返回 `None`（不归类，落 `unclassified`）；只有含「保证金」「信用证」「履约」「担保」「质押」「冻结」「境外」等关键字时才返回对应桶。

**Validates: Requirements 9.5, 11.3**

### Property 15: 受限分类顺序即优先级

`E1_RESTRICTED_BUCKETS` 的声明顺序必须使含包含关系的关键字得到正确归属：`信用证保证金` → `letter_of_credit`（不能被 `bank_acceptance` 或 `other` 的「保证金」吃掉）、`用于担保的定期存款` → `pledged_deposit`、`结构性存款` → **不归入** `pledged_deposit`（`exclude_keywords` 生效）。反向自检：打乱顺序后上述用例必须失败。

**Validates: Requirements 11.2, 11.4, 11.11**

### Property 16: 受限候选集不跨出货币资金族

`restricted_prefill` 中 `buckets[*].codes` ∪ `unclassified[*].code` 的每个元素，必须是 `BS-002` 解析出的原始码前缀之一的后代；且 `buckets` 各桶金额之和 + `unclassified` 金额之和 == 三族叶子合计（不重不漏）。

**Validates: Requirements 11.1, 11.5**

### Property 17: 人工归类优先且不被自动分类覆盖

给定同一叶子既有自动分类结果又有人工归类记录，`resolveRestrictedRows()` 必须采用人工归类；被标 `__unrestricted__` 的叶子不出现在任何类别行，但其金额计入 F1-5/F1-6 的差额侧。四表新增叶子必须出现在 `unclassified` 而不改动已有类别行金额。

**Validates: Requirements 11.7, 11.9, 11.10**

### Property 11: 公式预设科目合法性

E1 每个预设块的 `account_codes` 每个元素必须 ∈ 标准科目表，且 ∈ `BS-002` 公式引用的科目集合 `{1001,1002,1012}`。`1502` 必须不出现在任何 E1 块中。反向自检：把 `1502` 塞回去，守卫必须失败。

**Validates: Requirements 3.1, 3.6**

### Property 12: 预设 sheet 名存在性

E1 每个预设块的 `wp_name`/`sheet_name` 必须命中源 xlsx 四个 workbook 的 tab 名集合。`分析程序E1-3` 必须不出现（源 xlsx 无此 tab）。

**Validates: Requirements 3.2, 3.6**

### Property 13: 同步幂等与合计行

同一 snapshot 连续两次 `buildE1SyncPayload` 产出逐字节相等的载荷；主表末行 `is_total === true` 且 label 等于 `E1_NOTE_TOTAL_LABEL`（按本章节实证取值，不全局硬套）。

**Validates: Requirements 8.3, 8.6**

### Property 14: 勾稽引擎覆盖校验预设全集

`e1DisclosureConsistency` 返回的规则 id 集合必须 ⊇ `{F1-1..F1-6}`（listed 与 soe 各自），每条规则的 `refs` 必须指向真实存在的表名与行名。

**Validates: Requirements 9.1, 9.2**

## Error Handling

**后端取数（全程 fail-open，取数失败不能让底稿打不开）**

| 失败点 | 处理 | 理由 |
|--------|------|------|
| `BS-002` 解析失败 / 无配置 | 用 `fallback_gross=('1001','1002','1012')`，`resolved_from='fallback'` | 共享件既有语义；溯源面板显示「兜底」 |
| `account_mapping` 反解落空 | 退化为标准码作前缀 | 货币资金无备抵，无「宽前缀污染」风险（与 K1 `1231` 不同） |
| `tb_balance` 查询异常 | 返回空列表 + `logger.warning`，`four_table_prefill` 各槽为 `[]` | 底稿仍可手工编制 |
| `get_active_filter` | **必须传全签名** `(db, table, project_id, year)` 且 `await` | N2/N5 曾单参调用被 `except Exception` 吞成 warning → 取数恒空且无线索 |
| 叶子和 ≠ 父额 | 不阻断，`tb_source_codes.parent_check` 输出 `diff` 供 UI 提示 | 数据质量问题应暴露而非隐藏 |

**前端同步**

| 失败点 | 处理 |
|--------|------|
| `projectId` 缺失 | 手动按钮 disabled + 明确 toast（不静默 return） |
| 跨主体类型推送 → 409 `STANDARD_MISMATCH` | 静默吞（宁可不写也不写错章节，平台既有约定） |
| 请求去重取消（`ERR_CANCELED`） | 静默忽略 |
| 自动同步失败 | 静默、非阻塞、不打断录入；手动按钮才提示 |
| `saveBatch` 失败 | **必须给用户提示**（纯 `catch {}` 会让数据丢了没人发现） |

**幂等脚本**

- 默认 `--dry-run`；`--check` 返回欠账数（0 = 已对齐）；`--apply` 才写盘
- 表名改名走 `rule(aliases=)` **不能进 `drops`**（`drop_tables` 在 `apply_plan` 前执行会连行删掉）
- 外币章节 `五、73`/`八、92` 传 `rows=None`（**只补 columns/guidance，不动行集**）—— 跨循环共享，动行集会打断他循环

## Testing Strategy

**分层**

| 层 | 范围 | 手段 |
|----|------|------|
| 纯函数单测 | `build_e1_tb_values` / `build_e1_account_list` / `build_e1_adjudication_prefill` / `build_e1_source_codes` / `suggestRestrictedCategory` / `e1DisclosureConsistency` | pytest / vitest，含 Property 1~4、10、14 |
| PBT | 币种稳定 key 不撞键、派生列 = 原币×折算率、合计行守恒 | hypothesis / fast-check，`max_examples=5`；**生成器必须收敛到金额域**（`fc.float({noNaN:true})` 仍会产生 ±Infinity，D1 踩过） |
| 结构守卫 | Property 5、6、11、12 | openpyxl 直读源 xlsx 三向比对 + 反向自检 |
| 源码守卫 | Property 7（TDZ）、字面量归零、`el-input-number` 归零 | 正则 + `stripComments()` + 反向自检（守卫注释里会写反例，不去注释会误报） |
| 契约 | Property 8、13 | `_disclosureSubtableContract.helper` + 新建 `e1NoteSubtableContract.spec.ts` |
| 真实 DB 直跑 | render 三个项目（`df5b8403` 222 行 / `0ec33ac9` 57 行 / `2aa00f57` 13 行） | 绕过 HTTP 直调 `render()`，验 `resolved_from`、`parent_check.diff`、叶子和 |
| 浏览器实测 | 披露 Tab 挂载、同步落库、`_column_groups`、千分符 | chrome-devtools MCP + postgres 只读；**实测后数据必须复原** |

**测试替身注意**

- fake session 必须按 SQL/params 区分「同一张表的多次查询」（E1 会查 `tb_balance` 与 `trial_balance` 各一次）
- `get_active_filter` 的 mock 必须返回真实 `sa.true()`，不能用 `MagicMock()`（`sa.and_` 会拒绝 → 被 fail-open 吞成空 → 假绿）
- `ref(new Map())` 的桩必须读写都走 `.value`，否则 computed 不更新（是桩的坑不是实现的坑）

**测试改动诚实性**

改预设与叶子口径必然打红一批钉死旧表达式的既有测试（`1502`、`TB_SUM('1001~1012')`、`_is_leaf` 相关）。这些是**测试镜像 bug**，须显式改断言并**补上旧实现必红的新用例**（点号边界、零余额账户），不得只改断言。
