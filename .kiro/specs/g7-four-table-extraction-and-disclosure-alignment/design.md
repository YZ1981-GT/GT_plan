# Design Document

## Overview

G7 的链路是一条**五段级联**，本 spec 逐段补齐并对齐源模板：

```
tb_balance（四表库）
   │  ① 报表映射解析 BS-024 / IMP-009 → account_mapping 反解 → 叶子聚合
   ▼
render: tb_values / tb_leaf_categories / adjudication_prefill / tb_source_codes
   │  ② 前端消费
   ▼
G7-2 明细表  ──►  G7-1 审定表（未审数三分类 + 减值准备段）
   │                    │
   │  ③ g7DisclosureCrossSheet（已成熟，2900 行；再加四表库来源）
   ▼                    ▼
披露表（上市 / 国企）── ④ 多章节 payload ──►  附注模块
                                              上市 五、18 + 七、1
                                              国企 八、18 + 七、*（15 节）
```

现状断点：
- ① 硬编码前缀 `1511`/`1512`、自造缺点号边界的叶子判定、备抵未 abs、分类按客户编码写死；
- ② G7-1 无 `adjudication_prefill`、无溯源面板；披露表无四表库来源；
- ④ **上市侧把 15 张表全推 `五、18`**（14 张是孤儿）；G7 完全不在同步 registry 中；
- 附注模板侧：上市 `五、18` 主表 13 列被压成 5 列、`七、1` 零表格 187 段文本、
  国企 `八、18` 两张同名 `续：`（互相覆盖丢表）+ 10 表 `columns=0`。

## Architecture

### 后端（三层，全部纯函数可单测）

```
_g7_long_term_equity_main.py (render 编排)
  ├── G7_ACCOUNT_SPEC: ReportLineAccountSpec        # 声明式，不含查询
  ├── resolve_report_line_accounts(db, ...)         # 共享件（K1 建，G7 是第 N 个消费者）
  ├── select_leaves / filter_by_prefixes / aggregate_leaves   # 共享件
  ├── classify_g7_leaf(name, code) -> bucket|None   # 新增纯函数，名称优先
  ├── build_g7_tb_values(leaves, accounts) -> dict  # 新增纯函数
  ├── build_g7_leaf_categories(leaves, accounts)    # 重写（原 _build_g7_leaf_categories）
  ├── build_g7_adjudication_prefill(leaves, accounts) -> dict   # 新增纯函数
  └── build_g7_source_codes(accounts, leaves) -> dict           # 新增纯函数
```

**删除**：`_is_leaf`、`_sum_leaf_by_prefix`、`_G7_CATEGORY_MAP`、`_classify_leaf`（死代码直接删，
不留 DEPRECATED 注释）。`_G7_ACCOUNT_PREFIX` / `_G7_IMPAIRMENT_PREFIX` 降级为
`G7_ACCOUNT_SPEC` 的 fallback 常量并加注释说明「仅兜底与展示，运行态取 render 解析结果」。

### 前端

```
g7-long-term-equity-main/
  core/G7TabAdjudication.vue        + 「从四表库带入未审数」+ WpFourTableSourcePanel
  disclosure/
    g7ListedDisclosureModel.ts      + noteSectionId 分章 + group 两级表头 + 行集纠偏
    g7SoeDisclosureModel.ts         + group 两级表头（结构已是多章节，保留）
    g7NoteSectionMap.ts             ★ 新建薄壳（供 registry 生成器扫到）
    g7DisclosureConsistency.ts      ★ 新建勾稽引擎（纯函数）
    G7DisclosureConsistencyPanel.vue ★ 新建面板
composables/
  g7DisclosureCrossSheet.ts         + 四表库来源（applyMovementFromFourTable）
  g7FourTableSeed.ts                ★ 新建（审定表/披露表共用的四表 seed 纯函数）
```

### 附注模板

幂等脚本 `backend/scripts/fix/fix_note_g7_long_term_equity_structure.py`，
复用共享 kit `backend/scripts/fix/_note_structure_kit.py`
（`two_period_columns` / `flat_columns` / `rule` / `run_section` / `build_cli` / `ensure_text_sections`）。

四个作用域：上市 `五、18`、上市 `七、1`、国企 `八、18`、国企 `七、*`（15 节）。

## Components and Interfaces

### 1. `G7_ACCOUNT_SPEC`

```python
G7_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-024",                    # 长期股权投资，四准则一致 TB('1511','期末余额')
    fallback_gross=("1511",),
    provision_row_code="IMP-009",         # 八、长期股权投资减值准备 = TB('1512','期末余额')
    fallback_provision=("1512",),
    # BS-024 公式不引用备抵 → provision 走独立报表行；soe_consolidated 该行 formula 为 NULL
    # → 解析落空时回退 ('1512',)，此时 provision_exact=False
)
```

> `IMP-009` 只在 `soe_standalone` 有公式；上市与 soe_consolidated 均落空 → fallback。
> 因 `1512` 名称即「长期股权投资减值准备」，名称过滤无害，但仍须在 `tb_source_codes`
> 暴露 `provision_exact` 供精确判定（K1 已定的口径）。

### 2. `classify_g7_leaf(name, code)`

名称优先、编码兜底的桶分类器。**判定顺序有意义**（先具体后泛化）：

| 顺序 | 名称关键字 | 桶 | 说明 |
|-----|-----------|----|------|
| 1 | `其他综合收益` | `oci` | 必须早于 `其他权益变动`（`.04.01` 名称同时含两者） |
| 2 | `其他权益变动` | `other_equity` | |
| 3 | `损益调整` | `equity_profit` | 权益法确认的投资损益 |
| 4 | `减值准备` | `impairment` | |
| 5 | `子公司` | `subsidiary` | |
| 6 | `合营` | `jv` | |
| 7 | `联营` | `associate` | |
| — | 无命中 | `None` | 进 `unmapped`，不并入任何桶 |

编码兜底只在名称全无命中时启用，且**只认点分层级**（`1512` / `1512.` → impairment）。

### 3. `build_g7_adjudication_prefill`

输出形态（键名对齐 G7-1 前端已有的分类语义）：

```python
{
  "gross": {
    "subsidiary": {"opening":…, "increase":…, "decrease":…, "closing":…, "codes":[…], "name":"…"},
    "jv":        {…},          # 无叶子 → 该键**不出现**（宁缺勿造）
    "associate": {…},
    "other":     {…, "label": "四、损益调整/其他权益变动（四表带入）"},
  },
  "impairment": { "total": {…}, }    # 1512 无子科目 → 只给合计层
}
```

`other` 桶承载 `equity_profit` / `oci` / `other_equity` / `unmapped` 的合计 —— 它们是**变动性质**
而非**被投资单位类别**，四表数据里没有归属信息，机械摊入前三类会造假。源模板每块第 4 行
（`A11:B11` / `A16:B16` / `A21:B21` / `A26:B26` 等合并空单元格）本就是可改名占位行 → 正好落位。

`increase` / `decrease` 由 `debit` / `credit` 取，`closing` 校验 `opening + increase − decrease`；
不相等时保留 `closing` 原值并置 `roll_forward_ok: False`（暴露而非掩盖）。

### 4. 披露表两级表头（`ColumnDef.group`）

上市主表（源 `A8:M23`，13 列）：

| # | key | label | group |
|---|-----|-------|-------|
| 0 | 项目 | 被投资单位 | （标签列 `is_label`） |
| 1 | openingBook | 期初余额（账面价值） | — |
| 2 | openingImpairment | 减值准备期初余额 | — |
| 3 | addition | 追加/新增投资 | 本期增减变动 |
| 4 | reduction | 减少投资 | 本期增减变动 |
| 5 | equityProfit | 权益法下确认的投资损益 | 本期增减变动 |
| 6 | oci | 其他综合收益调整 | 本期增减变动 |
| 7 | otherEquity | 其他权益变动 | 本期增减变动 |
| 8 | dividend | 宣告发放现金股利或利润 | 本期增减变动 |
| 9 | impairment | 计提减值准备 | 本期增减变动 |
| 10 | other | 其他 | 本期增减变动 |
| 11 | closingBook | 期末余额（账面价值） | — |
| 12 | closingImpairment | 减值准备期末余额 | — |

国企明细表（源 `A210:M222`）同构，但第 1 列为 `投资成本`、第 2 列为 `期初余额`，
无「减值准备期初余额」，末列为 `减值准备期末余额`。

**`key` 一律不动**（同步载荷的行对象就是用这些键），只加 `group` 与修正 `label`。

### 5. 上市侧多章节 payload

```ts
export interface G7ListedSyncPayload {
  noteSectionId: string      // '五、18' | '七、1'
  noteSectionTitle: string
  sheetName: string          // '附注披露信息（上市公司）'
  subTableData: Record<string, Record<string, unknown>[]>
}
export function buildG7ListedSyncPayloads(state): G7ListedSyncPayload[]
```

给每个 `G7DisclosureSection` 增 `noteSectionId` / `noteSectionTitle`（对齐国企侧的
`G7SoeDisclosureSection`），按 `noteSectionId` 聚合，Tab 改调 `sync-batch-from-workpaper`。

分章依据（源模板行区间）：`A5:M24` → `五、18`；`A26:M243` → `七、1`。

### 6. `g7NoteSectionMap.ts`（薄壳，为 registry 生成器而建）

```ts
export const G7_NOTE_SECTION = { listed: '五、18', soe: '八、18' }
export const G7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
}
export { buildG7ListedSyncPayloads } from './g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
export { buildG7SoeSyncPayloads } from './g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
```

生成器硬约束（H10 实证）：章节号必须内联字面量、对象体内不写注释、
`X_DISCLOSURE_SHEET_NAME` 必须是**单个对象**（分离两个常量会因无分号被正则吞掉）。
跨章的 `七、1` / `七、*` 不进该常量（registry 只记主章节），由前端 payload 自行携带。

### 7. 勾稽引擎 `g7DisclosureConsistency.ts`

| 规则 | 表达式 | 级别 |
|-----|-------|------|
| 分类表合计 | `小计 − 减：长期股权投资减值准备 = 合计` | error |
| 主表 roll-forward | `期初 + Σ增加 − Σ减少 = 期末`（逐行） | error |
| 分类表 ↔ 主表 | 分类表 `小计.期末` ≥ 主表合计（主表只含权益法投资，成本法子公司投资不在主表） | warn |
| 披露 ↔ 审定 | 主表 `期末账面价值` 合计 ↔ G7-1 审定数（1511） | error |
| 减值 ↔ G7-17 | 减值准备期末 ↔ 减值测试表 G7-17 合计 | warn |
| 超额亏损小计 | 合营小计 + 联营小计 = 合计 | error |

容差 0.01 元；输出 `{label, rule, left, right, diff, level, detail, refs}`，面板复用
`WpDisclosureConsistencyPanel`（平台共用件）。

## Data Models

### `tb_source_codes`（render → `project_context`）

```jsonc
{
  "report_row": "BS-024",
  "provision_report_row": "IMP-009",
  "gross_standard": ["1511"],          // report_config 解析出的标准码
  "provision_standard": ["1512"],
  "gross": ["1511.01", "1511.02", "1511.03", "1511.04.01", "1511.04.02"],  // 参与聚合的叶子
  "provision": ["1512"],
  "provision_exact": false,            // IMP-009 在本准则下无公式 → fallback
  "parent_check": { "leaf_sum": 40459060.60, "parent": 40459060.60, "diff": 0 }
}
```

### `adjudication_prefill`

见「Components and Interfaces / 3」。前端 `useG7FormData` 从 render 抽取，
`G7TabAdjudication` 经 `pullFromTB()` 消费；**仅无持久化时套用**（编辑后不覆盖）。

### 附注模板变更清单（脚本 `--check` 的期望）

| 作用域 | 变更 |
|-------|------|
| 上市 `五、18` | 主表 headers 5→13（两级 group）、`columns` 0→13、补 `guidance`、删 1 个 `header_label` 假行、`…` 占位行按 R7.2 处理、`text_sections` 2→按源模板 R24 + R26 起的段 |
| 上市 `七、1` | `tables` 0→14（子公司权益 6 + 合营联营 7 + 共同经营 1）、`text_sections` 187→按源模板段落重排（剔除示例/提示） |
| 国企 `八、18` | 分类表 rows 5→6（补「对子公司投资」）、两张 `续：` 正名、表[8]/[9] 段落泄漏名正名、10 表补 `columns`/`guidance`、明细表两级 group、剥离 `<br/>` |
| 国企 `七、*` | 15 节表名正名（`序号`/`公司名称`/`项  目`）、补 `columns`/`guidance` |

## Correctness Properties

### Property 1: 叶子聚合等于父科目金额

对任意项目，`1511` 的叶子科目金额之和 SHALL 等于 `tb_balance` 中 `1511` 父行金额
（期初 / 期末 / 借 / 贷 四个维度各自成立）。实证：项目 `2aa00f57` 期初
`1511.01`(53,218,583.61) + `1511.03`(−12,759,523.01) = 40,459,060.60 = 父额。

**Validates: Requirements 1.3, 1.8**

### Property 2: 前缀匹配严格要求点号边界

对任意科目码集合，前缀 `p` SHALL 只匹配 `code == p` 或 `code.startswith(p + '.')`；
`1511` 不得命中 `15110` / `15111` 这类不同科目。旧实现 `code.startswith(prefix)` 违反本性质。

**Validates: Requirements 1.3**

### Property 3: 备抵聚合结果非负

`1512` 的聚合输出 SHALL 满足 `opening >= 0 and closing >= 0`，与 `tb_balance` 中该科目
是「无符号 + 方向列」还是「已带符号」的存储约定无关（两者 `abs()` 同解）。

**Validates: Requirements 1.4**

### Property 4: 分类按名称优先且顺序稳定

`classify_g7_leaf` SHALL 对名称含「其他权益变动_属于其他综合收益」的科目返回 `oci`
（而非 `other_equity`）；对同一 `(name, code)` 输入 SHALL 恒返回同一桶（纯函数）。

**Validates: Requirements 1.5**

### Property 5: 预填宁缺勿造

当某分类无可识别叶子科目时，`adjudication_prefill` SHALL 不包含该键；
当整个 `1511` 无任何叶子时 SHALL 返回 `{}` 而非含 0 值的骨架。

**Validates: Requirements 2.2, 2.4**

### Property 6: 变动性质不摊入被投资单位类别

`equity_profit` / `oci` / `other_equity` / `unmapped` 的金额 SHALL 只出现在 `other` 桶，
不得出现在 `subsidiary` / `jv` / `associate` 任一桶内；且 `other` 桶金额 SHALL 等于
这四类叶子之和（不重不漏）。

**Validates: Requirements 2.3**

### Property 7: fail-open 不阻断

`report_config` 无该行 / `account_mapping` 无映射 / `tb_balance` 无数据 / DB 抛错
四种情形下，render SHALL 正常返回且取数键为空值（`{}` / `None`），不抛异常。

**Validates: Requirements 1.7, 9.2**

### Property 8: 载荷表名与目标章节模板逐字一致

对每个 payload，其 `subTableData` 的每个非 `_` 前缀键 SHALL 存在于
`note_template_{variant}.json` 中 `noteSectionId` 对应章节的 `tables[].name` 集合内。

**Validates: Requirements 8.1, 8.2**

### Property 9: 列元数据两处表态一致

同一张表在「模板 seed `columns`」与「同步载荷 `columns`」两处的 `flat` / `group` 声明
SHALL 一致；单行表头的表两处都标 `flat`，两级表头的表两处都给同名 `group`。

**Validates: Requirements 6.6, 5.1**

### Property 10: 分组只声明相邻列且不跨越非分组列

`本期增减变动` 分组的列索引 SHALL 连续；`_extract_column_groups` 对该 `columns`
SHALL 输出 `[{group:'本期增减变动', start:3, span:8}]`（单级扁平格式），
不得输出凭空父表头。

**Validates: Requirements 5.1, 5.3**

### Property 11: 动态行删空即清理

底稿把某动态表的行全部删除后，同步载荷 SHALL 把该表名放入 `_removed_table_keys`
且**与 `previouslySyncedTables` 求交集**；未曾推送过的同名表 SHALL 不被删除。

**Validates: Requirements 7.4**

### Property 12: 上市联营 FS 行集不含现金行

上市「重要联营企业主要财务信息」的行标签序列 SHALL 逐字等于源模板 R171:R187（17 行），
不含「其中：现金和现金等价物」；合营表 SHALL 含该行（18 行）。

**Validates: Requirements 5.4**

### Property 13: 公式预设无项目专属字面量

G7 的公式预设 SHALL 不含具体客户/供应商编码（如 `007960`）；每条 `cell_ref` 在同一
`page_key`（`workpaper:G7`）内唯一；明细表块 SHALL 不含 `WP(`。

**Validates: Requirements 4.2, 4.3, 4.5**

### Property 14: sheet 名与源 xlsx 逐字一致

`G7_DISCLOSURE_SHEET_NAME` 的两个值、公式预设的 `sheet` 字段、render 下发的 `sheetName`
SHALL 与 openpyxl 直读 `G7 长期股权投资.xlsx` 的 `wb.sheetnames` 中对应项逐字相等。

**Validates: Requirements 4.4, 8.5**

### Property 15: 科目码字面量只存在于单一真源

在 G7 全部前端源码中（排除测试 fixture），字面量 `'1511'` / `'1512'` SHALL 只出现在
`composables/g7AccountScope.ts` 作 fallback 常量；其余文件 SHALL 通过
`g7AccountCode(src)` / `g7GrossQueryCodes(src)` 取值，且优先取 render 下发的
`tb_source_codes`。

**Validates: Requirements 11.1, 11.2**

### Property 16: 分类桶标签可回溯到源模板单元格

对 `G7_INVESTMENT_BUCKETS` 的每一项，其 `label` SHALL 能在 openpyxl 直读源 xlsx 的
`source_ref` 所指单元格文本中命中（去空白后相等或包含）；桶集合 SHALL 无重复 `bucket`
且 `priority` 全序唯一。前端与后端 SHALL 不各持一份标签副本（前端只读 render 下发的 `bucket_defs`）。

**Validates: Requirements 11.3**

### Property 17: 章节号与表名与真源逐字相等

`G7_NOTE_SECTION` 的两个值 SHALL 逐字等于 `note_template_variant_matrix.json` 中
`account_key='chang_qi_gu_quan_tou_zi'` 的对应 variant；国企每个 `noteSectionId`
SHALL 存在于 `note_template_soe.json` 的 `section_number` 集合中（含 md 截断值原样）。

**Validates: Requirements 11.4, 11.5**

### Property 18: 列数与行数由数据决定

对任意「按被投资单位横向展开」的表，其列集 SHALL 由 `buildG7SlotColumns(slot, names)` 生成，
`names` 长度变化时列数随之变化，且列 `key` 在改名后保持不变（`{slot}_{seq}`）；
动态区骨架行数 SHALL 等于 `max(seed 行数, 1)`，不含写死的 3 / 5 / 10。

**Validates: Requirements 11.6, 11.7**

### 8. 反硬编码：三个单一真源

#### 8.1 `composables/g7AccountScope.ts`（科目单一真源，对齐 `k2AccountScope.ts`）

```ts
export const G7_REPORT_ROW_CODE = 'BS-024'
export const G7_PROVISION_REPORT_ROW_CODE = 'IMP-009'
/** 仅兜底与展示；运行态一律用 render 下发的 tb_source_codes */
export const G7_GROSS_FALLBACK_STANDARD = '1511'
export const G7_PROVISION_FALLBACK_STANDARD = '1512'

export function g7GrossQueryCodes(src?: G7TbSourceCodes | null): string[]
export function g7ProvisionQueryCodes(src?: G7TbSourceCodes | null): string[]
/** 事件载荷 / writebackTB 用的科目码 */
export function g7AccountCode(src?: G7TbSourceCodes | null): string
export function g7ImpairmentAccountCode(src?: G7TbSourceCodes | null): string
```

清零现存散落点：`GtG7LongTermEquityMain.vue` 的 `G7_ACCOUNT_CODE` / `G7_IMPAIRMENT_CODE`
（`writebackTB` 与 `substantive:adjudicated` 事件过滤在用）、
`G7TabDisclosureListed.vue` / `G7TabDisclosureSOE.vue` 各自的 `ACCOUNT_CODE = '1511'`。

守卫（参数化，按文件断言）：G7 源码中 `'1511'` / `'1512'` 字面量 SHALL 只出现在
`g7AccountScope.ts`（作 fallback 常量）与测试 fixture 内。

#### 8.2 `G7_INVESTMENT_BUCKETS`（分类桶单一真源）

放在后端 `app/services/four_table/g7_investment_buckets.py`（纯数据 + 纯函数，零 IO），
前端经 render 下发的 `bucket_defs` 消费 —— **不在前端抄第二份**。

```python
@dataclass(frozen=True)
class G7Bucket:
    bucket: str                  # 'subsidiary' | 'jv' | 'associate' | 'equity_profit' | 'oci' | 'other_equity' | 'impairment'
    label: str                   # 逐字取自源模板（审定表 A8/A9/A10 或披露主表列名）
    source_ref: str              # 'G7-1!A8' / '披露(上市)!F9' —— 供守卫用 openpyxl 反查
    name_keywords: tuple[str, ...]
    code_fallback: tuple[str, ...] = ()
    priority: int = 0            # 数字小者先判（其他综合收益 必须早于 其他权益变动）
    is_movement_nature: bool = False   # True → 不是被投资单位类别，归 other 桶

G7_INVESTMENT_BUCKETS: tuple[G7Bucket, ...] = (...)
```

三个消费者：`classify_g7_leaf()`、`build_g7_adjudication_prefill()` 的行标签、
render 下发给前端的 `bucket_defs`（前端 seed 与 UI 文案都读它）。

守卫：每个 `G7Bucket.label` SHALL 能在 openpyxl 直读的源 xlsx 对应 `source_ref` 单元格中
找到（去空白后包含或相等）；`priority` 顺序下「其他权益变动_属于其他综合收益」判为 `oci`；
`is_movement_nature=True` 的桶金额只出现在 `other`（Property 6）。

#### 8.3 章节号与表名的锁死方式

字面量无法避免（registry 生成器要求内联字符串），但**必须双向锁死**：

| 字面量 | 真源 | 守卫 |
|-------|------|------|
| `G7_NOTE_SECTION.listed/soe` | `note_template_variant_matrix.json` | 前端契约逐字比对 |
| 国企 15 个 `noteSectionId` | `note_template_soe.json` 的 `section_number` | 前端契约逐条比对（含 md 截断值） |
| `G7_DISCLOSURE_SHEET_NAME` | 源 xlsx `wb.sheetnames` | 后端守卫 openpyxl 直读 |
| `templateTableKey` | 对应章节的 `tables[].name` | 共享 helper P1 |
| 列 `label` / 行 `label` | 源 xlsx 单元格 | 后端三向比对守卫 |

#### 8.4 动态列与动态行

固定列数改动态列（沿用 H7 `h7ListedDisclosureModel` 已验证范式）：

```ts
export interface G7SlotColumn { key: string; label: string; seq: number; editable: true }
/** 稳定 key = `${slot}_${seq}`；改名只改 label，不动 key（否则持久化数据丢落点） */
export function buildG7SlotColumns(slot: string, names: string[], sub?: string[]): ColumnDef[]
```

适用：上市 `ownership-change-impact`（公司 N 列）、上市重要联营 FS / 续（联营企业 N × 期末/期初）、
国企重要非全资子公司主要财务信息（子公司 N × 期末/期初）、国企出售子公司财务状况/经营成果、
国企重要联营 FS / 续、国企权益份额变动影响。

**🔴 列 key 不能用 label**：源模板四个槽位的默认叶子名相同（`期末数`/`期初数`），会撞键（H7 已踩）。

骨架行数改由数据决定：`blankRows(prefix, count)` 的 `count` 由
`seedRowCount(fourTableRows, g72Rows) || 1` 得出，不写死 3/5/10。

## Error Handling

| 失效点 | 处置 | 用户可见性 |
|-------|------|-----------|
| `report_config` 无 `BS-024` / `IMP-009` | 回退 `fallback_gross` / `fallback_provision`，`provision_exact=False` | 溯源面板显示「回退兜底科目」 |
| `account_mapping` 无该项目映射 | 反解退化为标准码本身作前缀 | 溯源面板并列「标准码 / 客户码」两口径 |
| `tb_balance` 无 `1511%` 行 | `tb_values={}` / `adjudication_prefill={}` | 审定表按钮 toast「四表库无该科目数据」 |
| DB 抛错 / `get_active_filter` 失败 | `logger.warning` + 返空，**不抛异常** | render 正常返回，前端允许手填 |
| 叶子和 ≠ 父额 | 两口径都进 `tb_source_codes.parent_check`，不静默取其一 | 溯源面板显示差异额 |
| `closing ≠ opening+increase−decrease` | 保留 `closing` 原值 + `roll_forward_ok:False` | 预填 toast 提示「roll-forward 不平，请核对」 |
| 灰度开关关闭 | 取数路径零写库副作用 | 按钮 `disabled` + tooltip 明示「四表取数未启用」 |
| 附注同步 409 `STANDARD_MISMATCH` | 前端 `catch` 静默（宁可不写也不写错章节） | toast「当前项目不适用该版附注同步」 |
| 幂等脚本 `--check` 有欠账 | 非零退出，CI 红 | CI job 日志列出逐项差异 |

**保存失败不得纯 `catch {}`**：披露表 `persist()` 失败须给 `ElMessage.error`，
否则数据丢了没人发现（平台已有同类事故）。

## Testing Strategy

### 后端

| 文件 | 覆盖 |
|------|------|
| `backend/tests/four_table/test_g7_account_scope.py` | 报表行解析（含 `applicable_standards` 传参）、点号边界 + **反向自检**（旧 `startswith` 口径确实误命中 `15110`）、abs 归一、名称优先分类顺序、预填宁缺勿造、变动性质不摊入、fail-open 四种组合、`tb_source_codes` 形态、sheetName ↔ openpyxl 一致 |
| `backend/tests/four_table/test_g7_formula_presets.py` | 禁项目专属客户码字面量、`cell_ref` 唯一、明细块无 `WP(`、`sheet` 与源 xlsx 逐字一致 |
| `backend/tests/services/test_note_g7_structure.py` | openpyxl 直读源 xlsx ↔ 模板 `headers` ↔ 同步 `columns` 三向比对；两级分组；`flat` 表态；无 HTML / 无 `header_label`；两张 `续：` 不复活；上市联营 FS 17 行不含现金行；**反向自检**（压扁的 5 列 headers 必须判红） |

### 前端

| 文件 | 覆盖 |
|------|------|
| `g7FourTableSeed.spec.ts` | 手工优先幂等、`overwrite` 语义、空 prefill 零改动（3 条 PBT） |
| `g7FourTableWiring.spec.ts` | 溯源面板挂载、按钮存在、灰度关闭态、宿主 snake_case 取值、`el-input-number` 归零、`fmtAmount` 走 store 成员 |
| `g7NoteSubtableContract.spec.ts` | 共享 helper P1~P6（子表名逐字、章节号存在、`group`/`flat` 必表态、标签纯文本、标签列头对齐 `headers[0]`、模板 headers 纯文本） |
| `g7DisclosureConsistency.spec.ts` | 6 条勾稽规则、容差 0.01、无数据时返「暂无可比对数据」 |
| `disclosureColumnsCoverage.spec.ts` | `P1_ROUTE` 登记两个 builder（零入参可调） |

### 实测（Wave 7）

1. **真实 DB 直跑 render**（绕开活体 HTTP，避免 uvicorn 未重载）：项目 `2aa00f57`，
   断言叶子和 == 父额 40,459,060.60、`impairment` 为正、`other` 桶 = 损益调整合计。
2. **浏览器**（chrome-devtools MCP，登录 `admin`/`admin123`，
   URL `/projects/{pid}/workpapers/{wpId}/edit`）：两版披露 Tab 两级表头渲染、
   动态行增删、`1234567.5` → `1,234,567.50`、推送后 postgres 只读复核。
3. **数据复原**：实测前对 `disclosure_notes.table_data` / `text_content` / `last_sync_at`
   与 `checklist_responses` 做快照，实测后逐字复原。

### 已知不可测

- **上市侧无活体**：8 个在册项目 `applicable_standard_v2.entity_type` 全为 `soe`
  （唯一 `template_type=listed` 的项目 `0ec33ac9` 其 `entity_type` 亦为 `soe`）→
  上市披露 Tab 与 `五、18` / `七、1` 只能靠契约测试 + 后端守卫双向锁死，不做活体验证。
- **`G7_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False** → `tb_leaf_categories` 与
  「从四表取数」端点的运行态行为需该开关打开后才可验（Task 7.3 待用户裁决）。
