# Design Document

## Overview

本设计解决 L 循环（债务循环，L1~L8）三类缺陷：**公式预设错位**（7 处，其中 4 处活的错数）、**L2/L4 推送链路缺失**（4 个披露 Tab 零同步 + L4 录入不落库）、**附注结构与源模板不一致**（5 处）。

三条贯穿性设计原则：

1. **判据真源单一化**。公式预设的正确性判据（「cells 公式实参必须 ⊆ 本循环兜底码」）落在**已被生产消费的** `l_cycle_extraction/account_scope.py`，不新建第二份科目清单。守卫从该模块 import，改一处两侧同时红。
2. **加法式，零回归**。取数链路（`build_l_tb_payload` 四个键）逐字不动；L2/L4 接线只新增 map 与 payload 构造器，不改共享 `useDisclosureAutoSync`；附注修订走幂等脚本，非本 spec 声明的章节逐字节不变。
3. **宁缺勿造**。L7 维持不预填（`fallback_codes=()`），改的只是「把空值显示成灰态说明」而非「猜一个科目」。L4 的优先股/永续债两张表作条件表（有数据才推）。

### 缺陷成因归类

| 类 | 缺陷 | 数量 | 成因 |
|---|---|---|---|
| A | 审定表 cells 公式取到别循环科目 | 5 | 预设整块错位一个循环，`account_codes` 已修对但 cells 未跟上 |
| B | 明细表整块贴错 | 2 | L5 块内容是应付债券、L6 块内容是长期应付款 |
| C | sheet 名在源 xlsx 不存在 + 病态区间 | 1 | `L1 分析程序L1-3` |
| D | 披露 Tab 零同步链路 | 4 | L2×2 / L4×2 |
| E | 附注结构与源模板不一致 | 5 | 列 key 中文字面量 / 列序相反 / 两级压单级 / 零 text_sections |

A 类五处同修法（改 cells 公式 + description），B 类同修法（整块重写），故幂等脚本按类组织而非按循环。

## Architecture

### 现有链路（不改）

```
report_config ──┐
                ├─→ resolve_l_scope(ctx, wp_code) ──→ ResolvedScope
account_chart ──┘         │  (row_code 驱动 + 兜底 + L7 宁缺勿造)
                          ↓
                  build_l_tb_payload(ctx, wp_code)
                          │
        ┌─────────────────┼──────────────────┬────────────────┐
        ↓                 ↓                  ↓                ↓
  trial_balance   tb_source_codes   adjudication_prefill   l_bucket_defs
  (审定表 TB 核对)   (溯源面板)        (分类行预填)         (中文标签真源)
```

### 本 spec 新增/修改

```
【类 A/B/C】prefill_formula_mapping.json
    ↑ fix_l_cycle_prefill_presets.py（幂等，--check/--apply）
    ↑ 判据 import ← l_cycle_extraction.account_scope.L_CYCLE_SPECS
    ↑ 守卫 test_l_cycle_formula_presets.py（扩 cells 维度）

【类 D】L2TabDisclosure{Listed,Soe}.vue ──→ l2NoteSectionMap.ts ──→ K3 的 t01/t02 子表
        L4TabDisclosure{Listed,Soe}.vue ──→ l4NoteSectionMap.ts（已存在，补 payload 构造器）
                                        └─→ useChecklistPersistence（补落库）

【类 E】note_template_{listed,soe}.json
    ↑ fix_note_l_cycle_structure_v2.py（新建，只碰本 spec 声明的 5 处）
```

### L2 与 K3 的数据源竞争（本 spec 最重要的设计决策）

**平台既有状态是「L2 有意豁免」**：`disclosureAutoSyncCoverage.spec.ts` 把 L2 两个 Tab 登记在 `MISSING_SYNC_PATH` 并注明「`buildK3SyncPayload` 已实装推这两张表 → L2 再推会同章节同表名互相覆盖」。该注释描述的现象为真（源码实证 `buildK3SyncPayload` 确实推 `T.interest` 与 `T.interestOverdue`），但**结论方向错了** —— 真实问题不是「L2 不该推」，而是**两个数据源在竞争同一张附注子表**：

| 维度 | K3 侧（现状） | L2 侧（本 spec） |
|---|---|---|
| 数据来源 | 披露 Tab **手工录入**（`Array.from({length:3}, makeRow)` 三个空行） | **L2-2 明细自动聚合**（`useL2Disclosure.aggByCategory`） |
| 行集 | `K3_INTEREST_ROWS[variant]` + `合计` | 源模板 7 行（listed，含「其中：工具1/工具2」两级）/ 6 行（soe） |
| 源模板依据 | 无 —— K3 源 xlsx 无「应付利息」明细表 | `附注披露（上市公司）信息!B8 = SUMIF('明细表L2-2'!A:A, A8, '明细表L2-2'!U:U)` |
| 逾期表来源 | 手工录入 3 空行 | `明细表L2-2!V12:V33 > 0` 的 IF 提取 |

**裁决：收敛到 L2（用户 2026-08-09 拍板）**。三条依据：

1. **源模板把取数关系写在 L2 侧** —— L2 披露 sheet 的每一格都是指向 `明细表L2-2` 的 SUMIF/IF 公式；K3 源 xlsx 里没有任何「应付利息」明细表。
2. **消掉重复录入** —— 审计师已在 L2-2 逐笔登记应付利息（含 `source` 类别、`isOverdue`、`overdueReason`），K3 侧再手填一遍属违反「联动是核心价值」。
3. **现状是「谁最后保存谁覆盖」** —— K3 的 `if ((snapshot.interest ?? []).length > 0)` 只在**无行时**跳过；一旦审计师在 K3 填了任何一行，就会整表覆盖 L2 的聚合结果，且两侧都不知道。

**收敛落法（加法式，K3 其余五张表零改动）**：

```
K3TabDisclosure{Listed,Soe}.vue
  ├─ interest / interest-overdue 两个 section
  │    ├─ 改为只读展示（读 useL2Disclosure 的同一份聚合结果）
  │    └─ 加「前往 L2 应付利息底稿编制 →」跳转（复用 GtIndexChip / wp-id-by-code）
  └─ 其余五个 section 逐字不变

buildK3SyncPayload
  ├─ 删掉 sub[T.interest] / sub[T.interestOverdue] 两个分支
  ├─ 删掉 snapshot.interest / snapshot.interestOverdue 字段
  └─ 两张表名**不进** _removed_table_keys（它们由 L2 负责推送，K3 越权删会打断 L2）

l2NoteSectionMap.buildL2SyncPayload
  └─ 推 { 应付利息, 重要的逾期未付利息 }（listed）/ { 应付利息, 重要的已逾期未支付的利息情况 }（soe）
```

**结构性保证「不互相覆盖」**：`buildK3SyncPayload` 与 `buildL2SyncPayload` 产出的 `sub_table_data` 键集**求交集必须为空**（Property 27），改一侧另一侧立刻打红。这比靠注释约定硬。

**`K3_INTEREST_ROWS` 收敛后是死常量**，按平台铁律「死代码立即删除」删掉，不留 DEPRECATED 注释。

### L2 → K3 的落点判断

实证 `五、42`/`八、42` 的子表构成：

| idx | listed 表名 | soe 表名 | 归属 |
|---|---|---|---|
| t00 | 其他应付款 | 其他应付款 | K3 主表（含「应付利息」行） |
| **t01** | **应付利息** | **应付利息** | **L2** |
| **t02** | **重要的逾期未付利息** | **重要的已逾期未支付的利息情况** | **L2** |
| t03 | 应付股利 | 应付股利 | K3 |
| t04 | 重要的超过1年未支付的应付股利 | 按款项性质列示 | K3 |
| t05 | 其他应付款（按款项性质列示） | 账龄超过1年的重要其他应付款项 | K3 |
| t06 | 其中，账龄超过1年的重要其他应付款 | — | K3 |

⇒ **L2 与 K3 在该章节内表名零交集** ⇒ 走既有表级浅合并即可，**不需要行级合并** `_row_scope`。这比 requirements 起草时的设想简单一档，且天然无撞表风险。

**L2 不推 t00 主表的「应付利息」行** —— 那行是 K3 主表的一行、由 K3 负责；L2 只负责 t01 的明细分项。两者的勾稽（t01 合计 == t00 应付利息行）作为 L2 侧的只读校验提示，不写入。

### 类 A/B 修复的顺序约束

必须 **先扩守卫（打红）→ 再改数据**。理由：守卫当前对 cells 维度零覆盖，若先改数据则无法区分「守卫有效」与「守卫空转」（memory 已记该范式在覆盖率守卫上产生过假绿）。

## Components and Interfaces

### 1. `backend/scripts/fix/fix_l_cycle_prefill_presets.py`（新建）

幂等脚本，`--dry-run`（默认）/ `--check`（有欠账 exit 1）/ `--apply`。

```python
@dataclass(frozen=True)
class PresetFix:
    wp_code: str
    sheet: str
    kind: Literal["realign_cells", "rewrite_block", "drop_block"]
    expect_codes: tuple[str, ...]   # 从 L_CYCLE_SPECS 派生，不手写
    evidence: str                    # 为什么这么改
```

三类动作：

- `realign_cells`（类 A，5 块）：按 `expect_codes[0]` 重写 `TB(...)`/`ADJ(...)` 实参 + description 里的科目中文名（取 `LCycleSpec.account_label`）。**`PREV(...)` 不动**（它指向自己 sheet，本就正确）。
- `rewrite_block`（类 B，2 块）：整块 cells 重写为本循环科目口径。L5 明细表按 `_L5_BUCKETS` 三桶（融资租赁/保证金/长期借款）+ 未确认融资费用；L6 明细表按 `2711` + 项目维度 AUX。
- `drop_block`（类 C，1 块）：删 `L1 分析程序L1-3`，并在报告里记录依据（sheet 不存在 + 病态区间）。

**round-trip 硬闸**：`json.dumps(indent=2)+"\n"` 必须逐字复现原文才允许写盘（memory 已记该范式，防重排整个 1 MB 文件与并发会话互相回退）。

**科目中文名单一真源**：description 里的科目名从 `L_CYCLE_SPECS[wp].account_label` 取，脚本内不写第二份中文名表。

### 2. `backend/tests/l_cycle_extraction/test_l_cycle_formula_presets.py`（扩展）

现有 5631 B，`cells` 命中 2 次、`expression`/`description` 命中 0 ⇒ 盲区确认。新增四条判据：

| Property | 判据 |
|---|---|
| cells 科目一致性 | 每个 `TB`/`ADJ`/`AUX`/`LEDGER_DETAIL` 的首实参（去掉点号子级后）∈ 本循环 `fallback_codes` ∪ 跨循环白名单 |
| description 一致性 | description 里出现的科目中文名必须 == `account_label`（或不含任何已登记科目名） |
| sheet 存在性 | 每个块的 `sheet` 必须是该 wp_code 源 xlsx 的真实 visible tab 名（openpyxl 直读） |
| 区间健全性 | `SUM_TB`/`TB_SUM` 的 `a~b` 区间不得跨越本循环科目族 |

**跨循环白名单**必须显式登记（利息测算表引 `6603` 是合法的：短期借款利息测算表要取财务费用），每条带理由。

**反向自检**（防守卫空转）：
- 用替身块复现「`审定表L4-1` 写 `TB('2601')`」必须打红
- 用替身块复现「description 写『租赁负债审定表』而 account_label 是『应付债券』」必须打红
- 断言扫描面非空（L 类块数 ≥ 15）

### 3. `l2NoteSectionMap.ts`（新建）

```ts
export const L2_NOTE_SECTION = { listed: '五、42', soe: '八、42' } as const
export const L2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）信息',   // 源 xlsx 逐字（注意「信息」在后）
  soe: '附注披露（国企）信息',
} as const
export const L2_LISTED_SUBTABLE = {
  interest: '应付利息',
  overdue: '重要的逾期未付利息',
} as const
export const L2_SOE_SUBTABLE = {
  interest: '应付利息',
  overdue: '重要的已逾期未支付的利息情况',   // 与 listed 不同名，禁统一
} as const
export function buildL2ListedColumns(): ColumnDef[]
export function buildL2SoeColumns(): ColumnDef[]
export function buildL2SyncPayload(snapshot, variant): SyncPayload
```

**行集两版不对称**（源模板事实，禁对齐）：

| 行 | listed | soe |
|---|---|---|
| 1~4 | 分期付息到期还本的长期借款利息 / 企业债券利息 / 短期借款应付利息 / 划分为金融负债的优先股\永续债利息 | 同 |
| 5 | 其中：工具1 | **其他利息** |
| 6 | 工具2 | 合计 |
| 7 | 其他 → 合计 | — |

`其中：工具1`/`工具2` 是 listed 侧的可扩位（动态插行区），soe 侧无。

### 4. `l4NoteSectionMap.ts`（已存在 6317 B，**先校正常量再补构造器**）

现有 `L4_NOTE_SECTION` / `L4_WITHIN1Y_NOTE_SECTION` / `L4_LISTED_SUBTABLE`(5 张) / `L4_SOE_SUBTABLE`(2 张) 已声明，`buildL4SyncPayload` 已在导出清单但**无消费方**。

**🔴 既有常量与附注模板不一致，必须先校正（否则一接线就产出 4 张孤儿子表）**。逐字实测对照：

| 常量键 | 当前值 | 模板真实表名 | 处置 |
|---|---|---|---|
| `LISTED.main` | `应付债券` | `应付债券` | ✅ 不变 |
| `LISTED.movement` | `应付债券增减变动` | `应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）` | **改** |
| `LISTED.within1y` | `一年内到期的应付债券` | 在 `五、46` **不存在**（它在 `五、43` t02/t03） | **移出**，改由 `L4_WITHIN1Y_*_SUBTABLE` 承载 |
| `LISTED.overdue` | `已到期未偿付的应付债券` | **模板里没有这张表** | **删**（无落点） |
| `LISTED.otherFinInstrument` | `划分为金融负债的其他金融工具` | `（3）划分为金融负债的其他金融工具`（带序号前缀） | **改** |
| — | 缺 | `应付债券（续）` | **新增** `LISTED.continued` |
| — | 缺 | `期末发行在外的优先股、永续债等其他金融工具变动情况` | **新增** `LISTED.instrumentMovement` |
| `SOE.movement` | `应付债券增减变动` | 同 listed 的长表名（soe `八、50` t01 表名逐字相同） | **改** |

**`五、43` / `八、46` 的 within1y 表名另立常量**（它们不属 `五、46`/`八、50`）：

```ts
export const L4_WITHIN1Y_NOTE_SECTION = { listed: '五、43', soe: '八、46' } as const   // ← 补 listed 键
export const L4_WITHIN1Y_LISTED_SUBTABLE = {
  bond: '一年内到期的应付债券',
  bondCont: '一年内到期的应付债券（续）',
} as const
export const L4_WITHIN1Y_SOE_SUBTABLE = {
  bond: '（2）一年内到期的应付债券',      // ← soe 侧带「（2）」前缀，与 listed 不同名
  bondCont: '一年内到期的应付债券',
} as const
```

**soe 侧 `八、46` 两张表名有陷阱**：t00 是 `（2）一年内到期的应付债券`（带序号）、t01 是 `一年内到期的应付债券`（不带）—— 而 listed 侧 t02/t03 分别是 `一年内到期的应付债券` / `一年内到期的应付债券（续）`。**四个表名两两不同，禁共用一份常量**（守卫 Property 28 断言两版键集不相等）。

**校正 `within1y` 是纯 seed 侧改动、零丢数风险**：`buildL4SyncPayload` 当前无消费方（0 处），故这些表名从未真实推送过任何数据。

本 spec 只做「前三张 + 可转债文字」：

| 子表 | listed 落点 | soe 落点 | 本 spec |
|---|---|---|---|
| main 应付债券 | 五、46 t00 | 八、50 t00 | ✅ 接 |
| movement 增减变动 | 五、46 t01 | 八、50 t01 | ✅ 接 |
| 续表（8 列） | 五、46 t02 | — | ✅ 接（仅 listed） |
| within1y 一年内到期 | 五、43 t02/t03 | 八、46 | ✅ 接（发第二个 payload） |
| otherFinInstrument 其他金融工具 | 五、46 t03/t04 | — | ⏸ 条件表，有数据才推 |

**soe 侧 movement 是 10 列**（含年初/本期应计/本期已付/期末应付利息四列），listed 是 6 列 + 续表 8 列 ⇒ 两版结构不同构，各自构造器。

**`五、43` 与 `八、46` 是跨循环共享章节**：L3 负责「一年内到期的长期借款」、L4 负责「一年内到期的应付债券」、L5 负责「一年内到期的长期应付款」。三者表名零交集 ⇒ 表级浅合并安全，与 L2 同理。

### 5. L4 录入落库（补缺）

实证 L4 披露 Tab 有 4 个 input + 2 个 textarea 但 `saveBatch`/`getField` 均 0 ⇒ 录入只在内存。接 `useChecklistPersistence`（平台共享件，天然按 `Set` 去重，避免 memory 已记的「同批次重复 item_id 整批被拒」）。

持久化键形态 `L4-disc-{variant}-{subtable}-rows`，与 L1/L3/L5 现有命名一致。

### 6. `backend/scripts/fix/fix_note_l_cycle_structure_v2.py`（新建）

**不改既有三个脚本**（`fix_note_l1_short_term_loans_structure.py` / `fix_note_l3_l4_structure.py` / `fix_note_l_cycle_structure.py`），新建第二个脚本只处理本 spec 的 5 处，避免与并发会话在同文件上互相回退。

| # | 章节 | 问题 | 修法 |
|---|---|---|---|
| E1 | soe 八、45 / 八、46 | 列 key 是中文字面量 + `flat` 标在每列 | key 改 `label`/`end_amount`/`begin_amount`；`flat` 只标标签列 |
| E2 | soe 八、57 | **列序确与源模板相反**（源 `A6/B6/C6` = 项目/年初余额/期末余额；模板 = 项目/期末余额/期初余额） | **按源模板调列序**（裁决已定，不留「登记偏离」逃逸阀） |
| E3 | listed 五、46 t04 | 优先股永续债变动**丢了 4 个「账面价值」列**（不是「只缺 group」） | **补 4 列再加 group** = 9 列，详见下 |
| E4 | listed 五、52 / soe 八、57 | 零 text_sections | 补源模板说明段（listed 五、52 源模板确无说明段 ⇒ 如实登记为零） |
| E5 | listed 五、46 t03 | `……` 行已标 expandable ✓ | 仅守卫防回退 |

**E2 的裁决依据**（用户 2026-08-09 拍板「改对齐源模板」）：`L7!附注披露信息(国企)` 的 `B6=年初余额` / `C6=期末余额`，而 listed 侧 `附注披露信息（上市公司）` 是 `B6=期末数` / `C6=上年年末数` —— **两版列序相反是源模板事实**，附注模板 soe 侧当前为「期末余额/期初余额」属压扁时被 listed 侧带偏。改动同时波及 `l7NoteSectionMap` 的 soe 列定义与载荷字段顺序（key 不变、只换数组顺序），需与守卫同批提交。

**E3 的真实缺口不是 group 而是列数**。源模板 `五、46` r63/r64 是两行表头：

```
r63:  发行在外的金融工具 | 期初余额      | 本期增加      | 本期减少      | 期末余额
r64:                     | 数量 | 账面价值 | 数量 | 账面价值 | 数量 | 账面价值 | 数量 | 账面价值
```

= 1 标签列 + 4 组 × 2 = **9 列**。模板当前 5 列 `label/begin_count/increase_count/decrease_count/end_count` —— **只保留了 4 个「数量」、4 个「账面价值」全丢**。故修法是：

1. 新增 4 列 `begin_value` / `increase_value` / `decrease_value` / `end_value`
2. 按 `数量`(count) / `账面价值`(value) 交替排列成 9 列
3. 4 个 group（`期初余额` / `本期增加` / `本期减少` / `期末余额`）各 span=2
4. **标签列不带 group 也不带 `flat`**（`flat` 标在任一列即让 `_extract_column_groups` 整表返 `[]`、group 被永久打掉）

**soe 侧 `八、50` 无此表**（源模板 r52/r53 有该表但附注模板 `八、50` 只有 2 张表）⇒ 本 spec 只改 listed 侧，soe 侧登记为「源模板有、附注模板无落点」的既有欠账（该表在 soe 侧属条件表且本 spec 不接推送，补章节属附注模板结构工作，另立）。

**E1 的 `flat` 处理必须谨慎**：memory 已记「`flat` 标在任意一列即对整表生效、`_extract_column_groups` 见 flat 即返 `[]`」⇒ 八、45/46 现在每列都标 flat，虽然结果正确（这些表确实单级），但形态与其余章节不一致；改为只标标签列，保持单级语义不变。

**E3 是唯一改列数的**（5→9），需同步 `l4NoteSectionMap` 的构造器，且因该表是条件表（本 spec 不接推送）⇒ 只改模板 seed，不动载荷。

### 7. 溯源面板灰态（L7）

`WpFourTableSourcePanel` 已支持 `tb_source_codes.prefill_supported` 与 `note`。L7 的 `note` 已含依据说明。本 spec 只在前端补：`prefill_supported === false` 时金额位显示「本项目无此科目，需手工填列」而非 `0.00`。

**判据是显式 `=== false`**（memory 已记：`undefined` 是「未知」不是「不支持」）。

## Data Models

### 无 DB 迁移

本 spec 不新增/修改任何表。持久化落点：

| 数据 | 落点 | 形态 |
|---|---|---|
| L2 披露录入 | `checklist_responses` | `L2-disc-{variant}-{subtable}-rows` → `remark` 存整表 JSON |
| L4 披露录入 | `checklist_responses` | `L4-disc-{variant}-{subtable}-rows` |
| 附注结构 | `note_template_{listed,soe}.json` | 幂等脚本改写 |
| 公式预设 | `prefill_formula_mapping.json` | 幂等脚本改写 |

### `PresetFix` 判据派生关系

```
L_CYCLE_SPECS[wp].fallback_codes  ──→ expect_codes（脚本 + 守卫共用）
L_CYCLE_SPECS[wp].account_label   ──→ description 科目名 + wp_name 校验
L_CYCLE_SPECS[wp].buckets         ──→ 类 B 重写时的分项口径
源 xlsx visible sheetnames         ──→ sheet 存在性判据
```

四者都从**已被生产消费的**那份 `L_CYCLE_SPECS` 派生 ⇒ 不产生第三份真源。

## Correctness Properties

### Property 1: 公式预设 cells 实参必须属于本循环科目族

对 `prefill_formula_mapping.json` 中每个 L 类块的每个 cell，其 `TB`/`ADJ`/`AUX`/`LEDGER_DETAIL` 首实参去掉点号子级后，必须 ∈ `L_CYCLE_SPECS[wp].fallback_codes` ∪ `CROSS_CYCLE_ALLOWLIST[(wp, sheet)]`。白名单每条须带理由。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: 类 A 五处错位必须全部改正且方向正确

`审定表L2-1`→`2231` / `审定表L4-1`→`2502` / `审定表L5-1`→`2701` / `审定表L6-1`→`2711` / `审定表L7-1`→ 无 TB（L7 不预填）。改正后不得出现 `2501`(在 L2)、`2601`(在 L4)、`2502`(在 L5)、`2701`(在 L6)、`2801`(在 L7)。

**Validates: Requirements 1.1, 1.5, 1.6**

### Property 3: description 科目名与 account_label 一致

每个 L 类块的 cells description 中若出现任何已登记的 L 循环科目中文名，必须等于该块 wp_code 的 `account_label`。

**Validates: Requirements 1.7, 1.8**

### Property 4: 预设 sheet 必须是源 xlsx 真实 visible tab

每个 L 类块的 `sheet` ∈ 该 wp_code 源 xlsx 的 visible sheetnames（openpyxl 直读，hidden 不算）。

**Validates: Requirements 2.1, 2.2, 3.4, 3.8**

### Property 5: 区间函数不得跨循环

`SUM_TB`/`TB_SUM` 的 `a~b` 区间内不得同时包含两个不同 L 循环的兜底码，也不得包含非 L 循环科目族的码。

**Validates: Requirements 2.4, 2.5, 3.5, 3.8**

### Property 6: 类 B 两块重写后口径正确

`明细表L5-2` 的 cells 全部引 `2701` 族（长期应付款），`明细表L6-2` 的 cells 全部引 `2711` 族（专项应付款）。且两块的 `wp_name` 与 `account_codes` 保持既有正确值不变。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 7: 幂等脚本 round-trip 与二次 apply 不变

`--apply` 后 `json.dumps(indent=2)+"\n"` 逐字复现文件；二次 `--apply` 后 md5 不变；`--check` 返回 0 欠账。

**Validates: Requirements 2.5, 2.6, 11.1**

### Property 8: 取数链路零回归

`build_l_tb_payload` 的四个键在本 spec 前后对同一输入逐字节相同；`resolve_l_scope` 的 `row_code`/`fallback_codes` 一字不改。

**Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7**

### Property 9: L2 推送只碰自己的两张子表

`buildL2SyncPayload` 产出的 `sub_table_data` 键集 ⊆ `{L2_*_SUBTABLE.interest, .overdue}`，不含 K3 的任何表名（`其他应付款`/`应付股利`/`按款项性质列示` 等）。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 10: L2 两版行集不对称且不得统一

listed 第 5~7 行为 `其中：工具1`/`工具2`/`其他`，soe 第 5 行为 `其他利息`。守卫断言两版行标签序列**不相等**（防「顺手对齐」）。

**Validates: Requirements 4.4, 4.5, 4.7, 4.8, 4.9**

### Property 11: L4 推送覆盖前三张 + 一年内到期

`buildL4SyncPayload(listed)` 含 main/movement/续表三张；`buildL4Within1ySyncPayload` 单独发 `五、43`（listed）/`八、46`（soe）。其他金融工具两张为条件表：有行才推、无行不推且进 `_removed_table_keys`。

**Validates: Requirements 5.1, 5.2, 5.3, 5.6**

### Property 12: L4 soe movement 是 10 列，listed 是 6+8 列

两版构造器产出的列数与 `note_template` 对应表 `columns` 长度逐一相等；且两版列 key 集合不相等（结构不同构的结构性证明）。

**Validates: Requirements 5.4, 5.5**

### Property 13: L4 录入必须落库

L4 两个披露 Tab 源码必须出现 `useChecklistPersistence` 或 `saveBatch`，且每个 input/textarea 的 `v-model`/`@change` 目标字段都在持久化字段集内。反向自检：移除持久化调用必须打红。

**Validates: Requirements 5.7, 5.8, 5.10**

### Property 14: 跨循环共享章节表名零交集

`五、43` 的三个 owner（L3/L4/L5）与 `五、42`/`八、42` 的两个 owner（K3/L2）各自声明的表名两两求交集必须为空。

**Validates: Requirements 4.6, 5.9**

### Property 15: 附注列 key 不得是中文字面量

`八、45`/`八、46` 的 `columns[].key` 必须是 snake_case 标识符（`^[a-z][a-z0-9_]*$`），不得含 CJK 字符。全库同类检查作防回退。

**Validates: Requirements 6.1, 6.2**

### Property 16: `flat` 只标标签列

修订后的表中，`flat: true` 只出现在 `columns[0]`（标签列）；且该表 `_extract_column_groups` 仍返回 `[]`（单级语义不变）。

**Validates: Requirements 6.3**

### Property 17: 八、57 列序与源模板一致

`八、57` 的 `headers` 顺序逐字 == 源 xlsx `L7!附注披露信息(国企)` 的 `A6/B6/C6`（`项目` / `年初余额` / `期末余额`），与 listed 侧 `五、52`（`项  目` / `期末数` / `上年年末数`）**不同**。守卫同时断言两版 headers 序列**不相等**（防「顺手对齐」），并断言 `l7NoteSectionMap` 的 soe 列定义顺序与之一致。

**Validates: Requirements 6.4, 6.5**

### Property 18: 五、46 t04 补齐 4 个账面价值列并改两级 9 列

`期末发行在外的优先股、永续债等其他金融工具变动情况` 的 `columns` 长度 == 9；key 集合含 4 个 `*_count` 与 4 个 `*_value`（`begin`/`increase`/`decrease`/`end` 各一对）；`_column_groups` 含 4 组各 span=2；标签列既不带 group 也不带 `flat`。反向自检：只加 group 不补列（保持 5 列）必须打红。

**Validates: Requirements 6.6**

### Property 19: text_sections 补齐且非裸表名

`五、52`/`八、57` 的 `text_sections` 非空；每段要么以 `#### ` 开头，要么通过 `_is_table_title_paragraph` 判否（即真正的披露正文）。

**Validates: Requirements 6.7, 6.8**

### Property 20: 动态插行区可达且不预置占位

源模板标注 `……`/`可无限加行` 的位置（L5 上市 r14/r18、L2 上市 r12-13、L4 两版 r50/r39、L6 上市 10 行空白）在附注模板中标 `row_type: expandable` 或由动态行承载；`blankRows` 类骨架行数 == `max(seed 行数, 1)`，不预置空占位。

**Validates: Requirements 7.1, 7.2, 7.3, 7.5, 7.6, 7.7**

### Property 21: L7 灰态判据是显式 false

前端 L7 溯源/审定表在 `prefill_supported === false` 时显示说明文案；`undefined` 时不显示（未知 ≠ 不支持）。反向自检：改成 `!prefill_supported` 必须打红。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5**

### Property 22: 附注幂等脚本只碰声明章节

`fix_note_l_cycle_structure_v2.py --apply` 前后，除本 spec 声明的 5 处外，两份模板 JSON 的其余章节逐字节不变。

**Validates: Requirements 6.9, 11.2**

### Property 23: 既有三个附注脚本仍 0 欠账

`fix_note_l1_short_term_loans_structure.py` / `fix_note_l3_l4_structure.py` / `fix_note_l_cycle_structure.py` 的 `--check` 在本 spec 改动后仍返回 0 欠账（两写者互不打架，memory 已记该范式）。

**Validates: Requirements 11.3, 11.4**

### Property 24: row_type 取值域不被扩张

本 spec 若使用 `expandable`，必须从 C spec 的 `note_expandable_markers` service import，不得硬写字面量；取值域 ⊆ 六值。

**Validates: Requirements 7.4, 7.8, 7.9**

### Property 25: 真实库验收诚实输出

验收脚本对真实库逐项目跑八个循环，输出每个循环的 `resolved_from`/`gross_standard`/`parent_check.diff`/`prefill` 桶数；无合格对象时如实输出 `NO_CANDIDATE` 并 exit 1，禁用 fixture 冒充。

**Validates: Requirements 10.1, 10.2, 10.6, 10.7, 10.8, 10.9**

### Property 26: 变异检验全红

≥18 项变异（类 A 各 1、类 B 各 1、sheet 存在性、区间、L2 表名越界、L2 行集对齐、L4 条件表、L4 落库、列 key 中文、flat 全列、列序、两级压扁只加 group 不补列、L7 灰态判据、K3 侧写入路径复活、L4 子表名回退旧值、within1y listed 键缺失、单一 owner 断言）逐条打红并字节级还原。

**Validates: Requirements 10.3, 10.4, 10.5, 10.10, 11.5, 11.7**

### Property 27: 应付利息子表单一 owner

`buildK3SyncPayload` 产出的 `sub_table_data` 键集**不含** `应付利息` 与两版逾期表名（`重要的逾期未付利息` / `重要的已逾期未支付的利息情况`），且不把它们放进 `_removed_table_keys`（K3 不再拥有它们，删也不该由它删）。同时 `buildL2SyncPayload` 的键集**恰为**这两张表。两侧键集交集必须为空、并集必须覆盖这两张表。反向自检：把 K3 的写入路径恢复必须打红。

**Validates: Requirements 4.10, 4.11, 4.12, 4.14**

### Property 28: K3 侧只读展示不再产生写入

`K3TabDisclosure{Listed,Soe}.vue` 的 `interest` / `interestOverdue` 区块源码内不得出现录入控件（`WpAmountInput` / `el-input` / `v-model` 指向这两个 section 的行字段），且必须存在指向 L2 的跳转入口。`K3DisclosureSnapshot` 保留 `interest`/`interestOverdue` 字段（类型不删，供勾稽读取），但 `buildK3SyncPayload` 不消费它们。

**Validates: Requirements 4.13**

### Property 29: L4 子表名与模板逐字一致且无孤儿

`L4_LISTED_SUBTABLE` / `L4_SOE_SUBTABLE` 的每个值都必须存在于对应章节的 `tables[].name`（listed 五、46 / soe 八、50）；不存在的键（如 `overdue`）必须删除。守卫按 `(章节号, 表名)` 二元组索引（附注模板跨章节大量同名表）。反向自检：把 `movement` 改回简称 `应付债券增减变动` 必须打红。

**Validates: Requirements 5.11, 5.12**

### Property 30: within1y 落点两版齐备

`L4_WITHIN1Y_NOTE_SECTION` 必须含 `listed: '五、43'` 与 `soe: '八、46'` 两个键；其子表名必须分别命中两章节的真实表名（listed `一年内到期的应付债券` + `一年内到期的应付债券（续）`；soe `（2）一年内到期的应付债券` + `一年内到期的应付债券`）。反向自检：缺 `listed` 键时 listed 侧 within1y payload 构造必须打红而非静默返回 null。

**Validates: Requirements 5.13**

### Property 31: soe 八、46 两张表名不同且不得统一

soe `八、46` 的两张表名分别是 `（2）一年内到期的应付债券`（5 列）与 `一年内到期的应付债券`（7 列），前者带序号前缀。守卫断言两名**不相等**且列数分别为 5 / 7（防「顺手统一表名」导致 `sub_table_data` 键冲突丢整表）。

**Validates: Requirements 5.14**

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| `resolve_l_scope` 抛异常 | fail-open，`prefill_supported=False` + note 记异常 | 既有行为，不改 |
| L7 无兜底码 | 返回空 `gross_*`，前端显灰态 | R8 宁缺勿造 |
| 幂等脚本 round-trip 失败 | exit 2 拒绝写盘 | Property 7 |
| 附注脚本命中数 ≠ 预期 | exit 2 中止 | 防误改同类文字 |
| L2/L4 推送失败 | `catch` 静默（自动同步不打断录入）+ 手动按钮给 toast | 平台既有范式 |
| L4 落库批次含重复 item_id | `useChecklistPersistence` 的 `Set` 去重 | memory 已记该坑 |
| 源 xlsx 读取失败（守卫） | `pytest.fail` 而非 skip | 防静默假绿 |
| K3 侧存量已录入应付利息数据 | 收敛前必须一次性只读盘查；有存量则**保留 K3 推送能力**并在两侧加冲突提示，不得静默改单写 | R4.14 数据零丢失红线 |
| K3 引导跳转拿不到 L2 底稿 id | `wp-id-by-code` 返空时按钮 disabled + tooltip「本项目未创建 L2 底稿」，不静默 no-op | 平台既有门控范式 |

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 后端预设 | `test_l_cycle_formula_presets.py`（扩展） | Property 1~6 |
| 后端幂等 | `test_l_cycle_preset_script.py`（新建） | Property 7 |
| 后端零回归 | `test_l_render_zero_regression.py`（新建） | Property 8 |
| 后端附注 | `test_note_l_cycle_structure_v2.py`（新建） | Property 15~19, 22, 23 |
| 前端 L2 | `l2NoteSectionMap.spec.ts`（新建） | Property 9, 10 |
| 前端 L4 | `l4NoteSectionMap.spec.ts`（新建） | Property 11, 12, 13, 29, 30, 31 |
| 前端共享 | `lCycleSharedSectionScope.spec.ts`（新建） | Property 14 |
| 前端 L7 | `l7PrefillGrayState.spec.ts`（新建） | Property 21 |
| 前端 L2/K3 收敛 | `interestPayableSingleOwner.spec.ts`（新建） | Property 27, 28 |
| 动态行 | 并入附注守卫 | Property 20, 24 |
| 真实库 | `verify_l_cycle_live.py`（新建，只读） | Property 25 |
| 变异 | `mutate_l_cycle_guards.py`（新建） | Property 26 |

**先打红要求**：Property 1~6 的守卫必须在类 A/B/C 修复**之前**提交并确实打红 7 处，否则无法区分守卫有效与空转。
