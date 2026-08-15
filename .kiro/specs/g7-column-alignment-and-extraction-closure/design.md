# Design Document

## Overview

本设计解决一个**结构性**问题：G7 的列结构有**三个真源**（源 xlsx / 模板 seed / 运行时载荷），
而现有守卫只锁住其中**两条边**，第三条边（源 xlsx ↔ 运行时）从未有过判据 —— 这是 56 个
偏差点能长期存在且四层验证全绿的成因。

```
                    ┌─────────────────────────────┐
                    │  源 xlsx（唯一裁决者）        │
                    │  backend/wp_templates/G/     │
                    │  G7 长期股权投资.xlsx         │
                    └──────┬───────────────┬───────┘
                    边①    │               │    边③（本 spec 新建）
        test_note_g7_structure.py          │    openpyxl=3 / 运行时引用=0
        （已存在，openpyxl 直读）            │
                           ↓               ↓
        ┌──────────────────────┐   ┌──────────────────────────┐
        │  模板 seed            │←→ │  运行时载荷                │
        │  note_template_*.json│边②│  buildG7{Listed,Soe}     │
        │  → _tables 骨架       │   │  Columns()               │
        └──────────────────────┘   └──────────────────────────┘
                     _disclosureSubtableContract.helper.ts
                     （已存在，xlsx 引用=0，且只覆盖主章节 11/38 张）
```

**设计主张**：闭合三角，**每条边只断言一次**。不新建第三份判据、不把源模板事实抄成
第四个常量表 —— 边③的产出经**后端生成的列事实 JSON** 投影给前端，该 JSON 由后端守卫钉死
「与实时 openpyxl 读取逐字相等」，故它是**投影不是真源**。

### 五类偏差的处置策略总览

| 类 | 处置 | 改哪一侧 | 数据风险 | 可机械化 |
| --- | --- | --- | --- | --- |
| A（丢 group，6 张） | 补 `group` 到运行时列定义 | 运行时 | 无 | 半（需逐表读源 xlsx 定跨度） |
| B（标签列 key，16） | 统一到平台惯例 `'label'` | **两侧** | **零**（投影器双向兜底） | 是（单一裁决） |
| C（数据列 key，21） | 以运行时为准改 seed | seed（量化闸后） | **有** | 否（须逐表核） |
| D（label 文字，11） | 逐字取源 xlsx | 运行时 | 无 | 否 |
| E（列数差 1，5） | 裁决 `name` 归属 | 视裁决 | 无（列增减不动已存值） | 否 |

**A 与 D 部分同表共现**（A 的 6 张里有 3 张的 label 带 group 前缀）⇒ 同一次改动一并消除，
不拆成两个任务各改一遍同一个文件。

## Architecture

### 组件与数据流

```
┌────────────────────────────────────────────────────────────────────────┐
│ Wave 1  判据先行（守卫先建、对当前状态打红 56 处）                        │
│                                                                        │
│  backend/scripts/diagnose/diagnose_g7_column_alignment.py（只读）       │
│    ├─ openpyxl 直读源 xlsx 两张披露 sheet → 表边界 + 合并区 → 两级表头   │
│    ├─ 读 note_template_{listed,soe}.json → seed 列定义（按 (章节,表名)） │
│    └─ 产出 backend/data/g7_column_source_facts.json（投影，非真源）      │
│                                                                        │
│  backend/tests/four_table/test_g7_column_source_facts.py               │
│    └─ 断言 JSON 与实时 openpyxl 逐字相等（stale 检测）                   │
│                                                                        │
│  frontend .../__tests__/g7ColumnThreeWayAlignment.spec.ts              │
│    ├─ 读 g7_column_source_facts.json（边③的源 xlsx 端）                 │
│    ├─ 真调 buildG7{Listed,Soe}Columns()（边③的运行时端）                │
│    └─ 六维比对：is_label / flat / group / 标签列key / 数据列key / label  │
└────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│ Wave 2  零风险类落地（B + A + D）                                       │
│  g7{Listed,Soe}DisclosureModel.ts  ← 补 group / 改 label / 标签列 key   │
│  fix_note_g7_*.py（4 个既有幂等脚本）← seed 侧标签列 key                 │
└────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│ Wave 3  有数据风险类落地（C + E，须先过量化闸）                          │
│  diagnose_g7_seed_key_impact.py（只读，连库量化受影响记录数）            │
│  → 为 0 才改 seed；非 0 改运行时并保留 seed key                          │
└────────────────────────────────────────────────────────────────────────┘
```

### 关键架构决策

**决策 1：源 xlsx 事实经一层 JSON 投影给前端**

边③的两端分处 Python 与 TypeScript。运行时列由 `associateMatrixColumnsFor(names)` 这类
函数**动态生成**，用正则从 43 KB / 61 KB 的 `.ts` 里抽列定义抽不出真实产出（实测
`columns:` 取值表达式有 22 种不同首 token）。

⇒ 后端生成列事实 JSON，前端守卫读它并**真调** `buildG7*Columns()`。JSON 的真源性由
`test_g7_column_source_facts.py` 钉死（与实时 openpyxl 逐字相等），符合平台铁律
「源模板真源必须 openpyxl 直读」—— 前端读的是**被守卫锁住的投影**，不是第二真源。

**决策 2：三方索引用 `(章节, 表名)` 二元组**

实测模板侧跨章节同名表 listed **63 个**表名出现 >1 次、soe **40 个**（`长期股权投资`
出现 3 次：主章节 + 会计政策章 + 母公司章）。建档核实轮已复现一次事故：按表名全局索引
把 `长期股权投资` 匹配到会计政策章的空壳版（`cols=0`）并产出「seed 无列定义」的假结论。

⇒ 三方索引键统一为 `(noteSectionId, tableName)`；守卫另加「同章节内表名唯一」断言
（实测当前为 0，作防回退）。

**决策 3：标签列 key 统一到 `'label'` 而非任一现存值**

平台惯例实测：266 个标签列定义里 **241 个（91%）** 用 `key: 'label'`，跨 70 个文件；
G7 运行时硬编码的 `'项目'` 全平台仅 7 处且全在 G 循环文件。

零数据风险由投影器**双向兜底**保证（`note_sub_table_projector.py`）：

```python
# L67-68：标签列 key 非 "label" 且行内无该键 → 从 "label" 复制
if label_key and label_key != "label" and label_key not in out and "label" in out:
    out[label_key] = out["label"]
# L204-205：标签列取值为空 → 回退通用 "label"
if (label_val is None or label_val == "") and label_key != "label":
    label_val = r.get("label", label_val)
```

⇒ 无论存量行对象用 `label` 还是用 `item`/`name`/`seq`，改 key 后都仍能取到值。故 B 类是
**一次裁决**而非 16 次迁移，也**不需要**量化闸。

**决策 4：A 类的判据是 `group`，不是 `flat`**

运行时 `buildG7*Columns()` 的标签列构造是：

```ts
const hasGroup = columns.some(c => c.group)
result[key] = [
  { key: '项目', label: labelText, is_label: true, ...(hasGroup ? {} : { flat: true }) },
  ...
]
```

⇒ 运行时**结构上不可能**出现「既无 `flat` 又无 `group`」（不留 `None`）或
「`flat` 与 `group` 并存」。故 `flat` 偏差是**症状**、`group` 缺失是**病因**；
守卫对该三元表达式做**防回退**断言（改掉它必打红），而不把 `flat` 列为待修项。

**决策 5：`is_label` 必须纳入守卫维度**

投影器 `_extract_column_groups` 跳过 `is_label` 列并令 `header_idx` **从 1 起**：

```python
header_idx = 1  # headers[0] 是标签列
for d in defs:
    if d.get("is_label"):
        continue
```

⇒ 两侧 `is_label` 表态不一致会让 **group 索引整体偏移一位**（比 label 文字不符严重得多）。
实测当前两侧一致（偏差 0），故这是**防回退**断言 —— 但必须有，因为 Wave 2 会同时改
标签列 key 与 group，正是最容易碰坏 `is_label` 的时机。

## Components and Interfaces

### C1. `diagnose_g7_column_alignment.py`（新建，只读）

```python
# backend/scripts/diagnose/diagnose_g7_column_alignment.py
def read_source_facts() -> dict:
    """openpyxl 直读两张披露 sheet，产出 {(variant, section, table): TableFacts}。

    TableFacts = {
        "label_header": str,        # 源 xlsx 行标识列头原文
        "columns": [{"label": str, "group": str | None}],
        "is_two_level": bool,      # 由 merged_cells.ranges 判定
        "source_rows": str,        # 如 'A165:G187'
    }
    """

def build_alignment_report(*, apply: bool = False) -> AlignmentReport:
    """六维比对 seed 与源 xlsx；--check 时偏差非空即 exit 2。"""
```

CLI：`--dry-run`（默认）/ `--check`（exit 2 表示有欠账）/ `--emit-facts`（写 JSON）。
**只读**：无 `--apply`、不写 DB、不改模板 JSON（源码级断言钉死）。

### C2. `g7_column_source_facts.json`（新建，派生投影）

```jsonc
{
  "_meta": {
    "generated_from": "backend/wp_templates/G/G7 长期股权投资.xlsx",
    "sheet_names": ["附注披露信息（上市公司）", "附注披露信息（国企）"],
    "note": "派生投影，非真源。由 test_g7_column_source_facts.py 钉死与实时 openpyxl 相等。"
  },
  "listed": {
    "七、1": {
      "重要非全资子公司主要财务信息—期末数": {
        "label_header": "子公司名称",
        "is_two_level": true,
        "columns": [
          { "label": "流动资产", "group": "期末数" }
          // ... 6 列同 group
        ]
      }
    }
  },
  "soe": { /* ... */ }
}
```

### C3. `test_g7_column_source_facts.py`（新建，后端）

| 断言 | 内容 |
| --- | --- |
| stale 检测 | JSON 与实时 `read_source_facts()` 逐字相等（不等 ⇒ 提示重跑 `--emit-facts`） |
| 扫描面 | variant == 2 / 表数 ≥ 38 / 每表列数 ≥ 2 |
| 只读性 | 脚本源码剥注释后禁 `--apply` / `db.delete(` / `DELETE FROM` / 写模板 JSON |
| 反向自检 | 篡改 JSON 一格必打红；剥注释生效自检（原文含 `--apply` 字样于说明中） |

### C4. `g7ColumnThreeWayAlignment.spec.ts`（新建，前端 —— 边③守卫）

```ts
const facts = JSON.parse(readFileSync(resolveRepo('backend/data/g7_column_source_facts.json')))
const runtime = { listed: buildG7ListedColumns(), soe: buildG7SoeColumns() }
// 按 (section, tableName) 二元组逐表比对六维
```

六维断言 + 四项防回退 + 反向自检（改一个 label / 删一个 group / 改标签列 key 各必打红）。

### C5. 运行时模型改动面

| 文件 | 改动 | 类 |
| --- | --- | --- |
| `g7ListedDisclosureModel.ts` | 2 张表补 `group`；`associateMatrixColumnsFor(names, sub)` 加参；3 处 label 取源文；标签列 key → `'label'` | A/D/B |
| `g7SoeDisclosureModel.ts` | 4 张表补 `group`；8 处 label 取源文；标签列 key → `'label'`；E 类按裁决增列 | A/D/B/E |

🔴 `associateMatrixColumnsFor(names, sub)` 加参时 **列 key 必须不变** ——
`buildG7SlotColumns(slot, names, sub)` 拼 key 用 `{slot}_{seq}_{sub.key}`，只要 `sub.key`
仍是 `current`/`prior` 就不动 key，只动 label。

### C6. seed 侧改动面（4 个既有幂等脚本）

| 脚本 | 改动 |
| --- | --- |
| `fix_note_g7_long_term_equity_structure.py` | listed 主章节标签列 key |
| `fix_note_g7_listed_other_entities_structure.py` | listed `七、1` 14 张表标签列 key + C 类 seed key |
| `fix_note_g7_soe_structure.py` | soe `八、18` 10 张表标签列 key + C 类 seed key |
| `fix_note_g7_soe_scope_change_structure.py` | soe `七、…` 13 张表标签列 key + C/E 类 |

**不新建脚本** —— 四个脚本已覆盖全部四个作用域，新建会造成同一章节两个写入方。

## Data Models

### AlignmentDeviation（诊断脚本输出）

```python
@dataclass(frozen=True)
class AlignmentDeviation:
    variant: str            # 'listed' | 'soe'
    section: str            # 章节号（soe 的 七、… 为 md 截断值，不补全）
    table: str              # 表名
    kind: Literal['group', 'flat', 'is_label', 'key_label_col', 'key_data_col', 'label', 'count']
    seed: str               # seed 侧观测值
    runtime: str            # 运行时侧观测值
    source: str             # 源 xlsx 裁决值（含单元格坐标）
```

### SourceTemplateDefect（R10 登记表）

```python
@dataclass(frozen=True)
class SourceTemplateDefect:
    locator: str      # 'soe!r282:r286'
    original: str     # 源模板原文
    basis: str        # 判定为缺陷的依据（≥20 字）
    intent: str       # 本平台按什么意图实现
```

配 stale 检测：该缺陷在源 xlsx 已被修正时打红；条目数上限 5 且只许缩短。

### 三方比对键

```
AlignmentKey = (variant, noteSectionId, tableName)
```

🔴 禁用 `(variant, tableName)`（跨章节同名 63/40 处）；禁用 `tableId`（seed 侧无此概念）。

## Correctness Properties

### Property 1: 源 xlsx 事实 JSON 与实时读取逐字相等
派生投影不得漂移；不等时守卫打红并提示重跑 `--emit-facts`。
**Validates: Requirements 6.2, 6.4**

### Property 2: 三方索引为 (章节, 表名) 二元组
按表名全局索引会匹配到跨章节同名表；守卫断言索引键含 section 且同章节内表名唯一。
**Validates: Requirements 6.3, 9.1**

### Property 3: 源 xlsx 判两级表头的表，运行时必须用 group 表达
不得把父表头压进 label 前缀。
**Validates: Requirements 1.1, 4.2**

### Property 4: 运行时 group 与 seed group 同名同跨度
**Validates: Requirements 1.2**

### Property 5: 源 xlsx 判单级表头的表，两路径都显式表态
seed 标 `flat`；运行时由 `hasGroup` 三元表达式自动标；两侧都不得留 `None`。
**Validates: Requirements 1.3**

### Property 6: 运行时 flat 与 group 互斥且不留 None（防回退）
断言 `buildG7*Columns()` 里 `...(hasGroup ? {} : { flat: true })` 结构仍在；改掉必打红。
**Validates: Requirements 1.4**

### Property 7: A 类 6 张表 group 与 flat 偏差清零
**Validates: Requirements 1.5**

### Property 8: 标签列 key 恒为平台惯例 'label'
两路径一致；禁中文字面量当 key。
**Validates: Requirements 2.1, 2.5**

### Property 9: 标签列必须带 is_label: true
投影器靠它选标签列并跳过它算 group 索引。
**Validates: Requirements 2.2**

### Property 10: 标签列 key 改动不需量化闸（投影器双向兜底）
断言 `note_sub_table_projector` 的两处兜底分支仍在（L67-68 / L204-205）；删掉必打红。
**Validates: Requirements 2.3**

### Property 11: B 类 16 处标签列 key 偏差清零
**Validates: Requirements 2.4**

### Property 12: 数据列 key 两路径集合相等
**Validates: Requirements 3.1**

### Property 13: 动态列 key 保持 {slot}_{seq}[_{sub}] 形态
不得回退成写死序号 `c1Current`/`company1`。
**Validates: Requirements 3.2, 3.4**

### Property 14: 改 seed key 前必须过量化闸
受影响记录数为 0 才允许改 seed；非 0 改运行时并保留 seed key。
**Validates: Requirements 3.3**

### Property 15: 落地后 key 集合等于改动前某一侧
禁「两侧都改成第三套 key」（会同时丢两侧数据）。
**Validates: Requirements 3.5**

### Property 16: 列 label 逐字等于源 xlsx 对应单元格
**Validates: Requirements 4.1**

### Property 17: 全半角括号按源 xlsx 原文，禁统一
守卫登记该表原文；「统一成好看的那种」必打红。
**Validates: Requirements 4.2, 4.4**

### Property 18: 共用 slot 的两表各传自己的 sub label 且列 key 不变
`associateMatrixColumnsFor(names, sub)` 加参后 key 仍为 `{slot}_{seq}_{current|prior}`。
**Validates: Requirements 4.3**

### Property 19: E 类差异列归属有源 xlsx 依据且列数清零
**Validates: Requirements 5.1, 5.2, 5.5**

### Property 20: E 类裁决落地后 headers 与 columns 数量自洽
判「公司名称由 label 承载」则 seed `headers` 同步减一列；判「是数据列」则运行时补列且
`labelHeader` 取源 xlsx 的 `序号`。
**Validates: Requirements 5.3, 5.4**

### Property 21: 六维偏差任一被改歪即打红
key / label / group / flat / is_label / 列数。
**Validates: Requirements 6.1**

### Property 22: 守卫扫描面非空
variant == 2 / 运行时表数 ≥ 38 / 各表列数 ≥ 2。
**Validates: Requirements 6.4**

### Property 23: 源模板缺陷登记配 stale 检测且条目数只许缩短
**Validates: Requirements 6.5, 10.1, 10.2, 10.3**

### Property 24: 守卫覆盖两条路径各自的产出
不得只查 seed 或只查运行时。
**Validates: Requirements 6.6**

### Property 25: 四项已绿指标锁成防回退断言
`is_label` 表态一致 / 孤儿 0 / `templateTableKey` 撞名 0 / 同章节同名 0。
**Validates: Requirements 6.7, 9.3**

### Property 26: 槽级 row_code 登记表与已声明表不重叠且落地后迁移
**Validates: Requirements 7.1, 7.2**

### Property 27: IMP 行公式全 NULL 时声明后走三态跳过
不得因「无公式可对照」而不声明。
**Validates: Requirements 7.3**

### Property 28: D1/D2 不得照抄声明
必须先修 `report_config` 真源或明确撤回并写明依据。
**Validates: Requirements 7.4**

### Property 29: 槽级 row_code 落地配真实库前后对照零回归
`standard_codes` / `resolved_from` 逐字不变。
**Validates: Requirements 7.5**

### Property 30: 取数补齐判定二选一且都有依据
补 ⇒ 真实库实证；不补 ⇒ 「宁缺勿造」登记 + 反向自检。
**Validates: Requirements 8.1, 8.2**

### Property 31: 禁摊派总额与硬编码客户码
**Validates: Requirements 8.3, 8.4**

### Property 32: 运行时表名存在于对应变体对应章节
**Validates: Requirements 9.1**

### Property 33: 守卫覆盖 38 张全部运行时表
现有契约只覆盖主章节 11 张。
**Validates: Requirements 9.2**

### Property 34: 有录入区块的条件表补 _removed_table_keys，无录入区块的只跳过
**Validates: Requirements 9.4**

### Property 35: soe 七、… 章节号按 md 截断值断言，禁补全
**Validates: Requirements 9.5**

### Property 36: 幂等双证
`--dry-run` → `--apply` → `--check` 0 欠账；二次 apply md5 不变。
**Validates: Requirements 11.1**

### Property 37: 变异检验 100% RED 且三态可区分
RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷。
**Validates: Requirements 11.2**

### Property 38: 广域回归无新增失败
**Validates: Requirements 11.3**

### Property 39: 零回归判据禁用 HEAD-swap，改前后对照
**Validates: Requirements 11.4**

### Property 40: 改模板 JSON 前后核对非本 spec 章节逐字未变
**Validates: Requirements 11.5**

### Property 41: 浏览器实测四步齐全且数据复原
录数据 → 真出数 → 查落库 → 复原（基线取 `parsed_data IS NULL`）。
**Validates: Requirements 11.6**

## Error Handling

| 场景 | 处置 | 理由 |
| --- | --- | --- |
| 源 xlsx 缺失 / 打不开 | 守卫 **fail**（不 skip） | 源模板是唯一裁决者，读不到即无法判定 |
| 事实 JSON 缺失 | 前端守卫 **fail** 并提示跑 `--emit-facts` | 缺投影 ⇒ 边③无判据，不得静默跳过 |
| 事实 JSON 与实时读取不等 | 后端守卫 **fail** | stale 投影会产出假结论 |
| 某表在 seed 缺失 | 记 `tableMissing` 偏差并 fail | 孤儿表 = 数据静默丢失 |
| 某表 seed 有但 `columns` 为空 | 记 `seedNoCols` 偏差 | 投影降级只显行名 |
| 量化闸查询失败 | **拒绝改 seed**（fail-closed） | 宁可不改也不能冒数据失联风险 |
| `--apply` 被中断 | 幂等脚本可重放；判成败查数据不看 exit code | 平台已记「中断但写入已提交」 |
| 源模板缺陷已被修正 | stale 检测打红，提示移出登记 | 防豁免变永久盲区 |

## Testing Strategy

| 层 | 文件 | 覆盖 Property |
| --- | --- | --- |
| 后端·事实投影 | `backend/tests/four_table/test_g7_column_source_facts.py` | 1, 22, 23 |
| 后端·结构（既有，扩容） | `backend/tests/test_note_g7_structure.py` | 4, 19, 20, 35, 36 |
| 后端·槽级 row_code（既有） | `backend/tests/four_table/test_semantic_slot_row_code.py` | 26, 27, 28, 29 |
| 后端·取数判定 | `backend/tests/g7_extraction/test_g7_extraction_scope_adjudication.py` | 30, 31 |
| 前端·三向对齐（新建，核心） | `.../composables/__tests__/g7ColumnThreeWayAlignment.spec.ts` | 2, 3, 5, 6, 8, 9, 10, 12, 13, 15, 16, 17, 18, 21, 24, 25 |
| 前端·契约（既有，扩容到 38 张） | `.../composables/__tests__/g7NoteSubtableContract.spec.ts` | 7, 11, 32, 33, 34 |
| 变异脚本 | `backend/scripts/diagnose/mutate_g7_column_alignment_guards.py` | 37 |
| 只读验收 | `backend/scripts/diagnose/verify_g7_alignment_live.py` | 14, 29, 38, 39, 40, 41 |

**变异锚点**（每条须 hits == 1）：删一个 `group` / 改一个 label 全半角 / 标签列 key 改回
`'项目'` / 去掉 `is_label` / 改 `hasGroup` 三元表达式 / 篡改事实 JSON 一格 /
删投影器兜底分支 / 把动态列 key 改回写死序号。

**反向自检**：扫描面下限断言 + 「弱判据仍通过」对照（如只断言 `flat` 存在性抓不到
`group` 缺失，须证明六维判据强于旧判据）。

## Notes

### 与并发 spec 的边界

| 文件 | 并发方 | 处置 |
| --- | --- | --- |
| `note_template_{listed,soe}.json` | C spec（`note-template-columns-…` 21/23）+ 母公司章相关 | 只动 G7 四个作用域；落地后核对非 G7 章节逐字未变 |
| `test_semantic_slot_row_code.py` | 无 | 本 spec 独占 |
| `governance-checks.yml` | 多 spec 混合 | 只加 job 不改他人 job；加完验 YAML 可解析 + job 名不重名 |

🔴 **禁用 HEAD-swap 零回归**：两份模板 JSON 含并发会话未提交成果，换文件会抹掉。

### 明确不做

- 不改 `_extract_column_groups` / `_infer_groups_from_headers`（平台共享投影器，40+ 章节消费）
- 不改 `_disclosureSubtableContract.helper.ts` 的 P1~P6 语义（40 个循环共用）
- 不新建幂等脚本（四个既有脚本已覆盖四个作用域）
- 不碰 `五、18` / `八、18` 以外章节的 seed 行集
- 不做附注模板 legacy 快照迁移（归 C spec）

### 落地前必读的实测事实

1. 运行时表数 listed **15** / soe **23**；`buildG7*Columns()` 键数与之相等（15/23）
2. `cols()` 与 `groupedCols()` 在同一 `columns` 数组内混用 **0 处** ⇒ 补 group 是安全的
   局部变换
3. soe `ASSOCIATE_FS_SUB` / `ASSOCIATE_PL_SUB` **已是按表拆分的正确形态**且带「不得简写」
   注释 ⇒ listed 侧照此范式对齐即可，不必另设计
4. 章节分布：listed = `五、18`×1 + `七、1`×14；soe = `八、18`×10 + 10 个 `七、…`×13
5. 权益法族 / 子公司族 render 的四表取数键命中数**全为 0**（只有 `client_name`/`audit_year`）
