# Design Document

## Overview

核心设计是一句话：**把「位移」从"必然是漂移"改成"可以是一份被冻结的声明"**。

现有引擎对未管理区域的判据是「逐字节不变」。插行必然改动插入点以下的每个行号，所以在这套判据下插行永远等于漂移 —— 这不是实现缺陷，是判据的表达能力不足。本设计给判据补上一个维度：`RowShiftPlan`。它在写第一个字节之前被冻结进 `MaterializePlan`，verifier 拿同一份计划把行号**反向归一化**后再比对。于是：

- 与计划一致的位移 ⇒ 归一化后 digest 相等 ⇒ 判等价；
- 计划外的任何改动（包括位移量不符、非位移性改动）⇒ 归一化后仍不等 ⇒ 仍判漂移。

**判据没有被放宽，只是变得能表达"预期"。**

### 调查事实与方向性结论

| 维度 | 当前事实（实测） | 设计结论 |
|---|---|---|
| 插行禁令 | `plan_managed_writes` 第 4 步无条件 `RowSetDivergenceError`；模块 docstring 第四节第 1 条把它写成判据 | 改成「先算位移计划，算不出来才红」；残余红分支保留 |
| 未管理格 digest | `_managed_sheet_cell_digest` 逐格喂 `r\|t\|s\|f\|v` | 加 `row_shift` 参数，`r` 反向归一化后再喂 |
| 结构块 digest | `_sheet_structure_digest` 对 6 个 tag 整段 `ET.tostring` | 归一化 `ref`/`sqref` 里的行号后再序列化 |
| 未被检查的结构 | `dimension`/`hyperlinks`/`autoFilter`/`rowBreaks` 不在任何 aspect | 补进 `_SHEET_STRUCTURE_BLOCKS`（先补检查，再动它们） |
| footer anchor | 实测行 ≠ 冻结行即红 | 判据改 `frozen + shift == observed` |
| footer 合计 | 「共享公式主格不得在此处被改写」⇒ fail closed | 契约声明 `carries_total_formula` 时允许扩张区间 |
| 共享公式 | 只判 `ref` 含不含冒号，从不解析 `si` | 新建 `si` → (主格, ref) 索引层 |
| 写入层 | `_insert_row` 明写「不位移」；`_patch_sheet_xml` 逐 write `str.replace` | 新增独立的位移阶段，排在写格之前 |
| 新造格样式 | `_cell_xml(style="")` ⇒ 无样式 | 从样式来源行按列继承 `s=` |
| 契约 schema | `FooterAnchorSpec` 只解析 `marker`+`search_column`，`carries_total_formula` 被静默丢弃 | 解析出来，默认假 |
| 唯一「插行合法」先例 | `_classify_parts` 排除 `xl/tables/**`；`assert_identity_inventory_retained` 子集语义 | 复用这两处的语义，不再新造豁免 |
| 真实规模 | D2 store 729 行 vs 骨架 13 行；H1 store 0 行、骨架含 `'……'` 脚手架行 | D2 是插行的活证人；H1 的契约缺陷不在本 spec |

### 明确拒绝的方案

1. **把 `managed_sheet_unmanaged_cells` 与 `managed_sheet_structure` 两个 aspect 关掉**。那是把「支持插行」换成「不再检查受管 sheet」，代价是任何真实漂移都看不见了。
2. **只比对"行号之外的内容"（把 `r=` 从 digest 里剔掉）**。剔掉后「把 A30 的值挪到 A31」这种真实错误也变成等价 —— 位置是单元格语义的一部分，不能整类丢弃。
3. **按 diff 事后推断位移量**。事后推断等于让被检查对象自己声明自己合法（漂移也能被"推断"成一次位移）。位移量必须是**写之前**冻结的声明。
4. **用 openpyxl 全量重写来实现插行**。openpyxl 保不住「公式 + 缓存值」，且实测 351 个模板里 182 个含 drawing、生产上没有一个能通过 `select_write_strategy` 的门。
5. **在 `_patch_sheet_xml` 里边写格边位移**。写格阶段用 `_cell_view` 按坐标定位，位移会让同一次遍历里前后坐标语义不一致 ⇒ 静默错位。位移必须是独立且更早的阶段。
6. **让新插入行不带样式**。无样式行在 Excel 里显示为默认字体无边框，审计师看到的是一张"断裂"的表；且 AC 3.5 明令样式必须保留。
7. **改写共享公式主格为字面量以规避区间问题**。那会让整组成员失效（K11 的 `H8:H25` 是 18 行一组）。本设计只允许**位移与扩张 `ref`**。
8. **对受管区域之外的共享公式组也做区间扩张**。它们的语义不由受管行区间决定；扩张它们等于替审计师改公式。只做位移。
9. **删掉 `RowSetDivergenceError`**。它在 `FAILURE_KINDS` 里登记、且 `mutate_task38_excel_materialize_guards.py` 的锚点指向依赖它的守卫。删掉会让那条变异从 RED 变 GREEN。
10. **顺手实现结构性删行**。删行要裁决「物理行有数据但 projection 里没有该身份」是删除还是丢失，那是 merge 域的问题，与插行不同源。
11. **先动 `dimension`/`hyperlinks`/`autoFilter`/`rowBreaks` 再补检查**。顺序反了就是"改了没人看"，属假绿。必须先把它们补进 `_SHEET_STRUCTURE_BLOCKS`，让它们先能红，再让位移函数处理它们。
12. **把位移敏感清单写在注释里**。注释不可执行。清单必须是模块常量，并与位移函数按结构判据双向锁死。

## Architecture

### 分阶段流水线

```text
materialize_projection
  │
  ├─ 1. frozen 身份门（既有，不变）
  ├─ 2. substrate 准入（既有，不变）
  ├─ 3. 输出路径不得落模板库（既有，不变）
  ├─ 4. extract substrate（既有，不变）—— 得到 region / scan
  ├─ 5. 写入策略裁决（既有，不变）
  │
  ├─ 6. plan_managed_writes
  │      ├─ 6.1 动态列绑定（既有）
  │      ├─ 6.2 ◆ 算 RowShiftPlan ◆        ← 本 spec 新增，排在 footer 门之前
  │      │        orphan 身份数 → insert_at / count / style_from
  │      │        算不出来 → RowSetDivergenceError（残余分支）
  │      ├─ 6.3 shifted_region = region 按 count 重构
  │      ├─ 6.4 footer anchor（判据 += shift）
  │      ├─ 6.5 footer 合计（用 shifted_region 求值）
  │      ├─ 6.6 行集一致性（此时 orphan 必为空 —— 已被 6.2 消化）
  │      ├─ 6.7 逐字段写入（坐标基于 shifted 行号）
  │      └─ 6.8 minted identity
  │
  ├─ 7. apply_plan_zip
  │      ├─ 7.1 ◆ shift_sheet_rows(xml, plan.row_shift) ◆   ← 位移阶段，最先
  │      ├─ 7.2 ◆ extend_total_formulas(...) ◆              ← 合计扩张
  │      └─ 7.3 _patch_sheet_xml(shifted_xml, writes)       ← 写格，最后
  │
  └─ 8. 反读 staged identity inventory（既有，不变）

verify_unmanaged_regions(before, after, ..., row_shift=plan.row_shift)
  └─ unmanaged_region_digest(after, ..., row_shift=…) 归一化后比对
```

**6.2 必须排在 6.4/6.5 之前**：footer 两道门要用位移后的区间求值，而位移量在 6.2 才产生。这与既有「2/3 放在字段写入之前」的理由同源 —— 结构判据先于内容写入。

### 位移函数的结构

`shift_sheet_rows` 是纯函数，内部按位移敏感清单逐项处理：

```text
shift_sheet_rows(xml, plan) -> (new_xml, ShiftReport)
  ├─ 扫描：收集清单外携带行号的元素 tag（有则 fail closed）
  ├─ 阶段 A：<row r> 与 <c r> 重编号（自底向上，避免行号碰撞）
  ├─ 阶段 B：插入 count 个新 <row>，每列 s= 取自 style_from 行
  ├─ 阶段 C：平移 mergeCell@ref / dataValidation@sqref / conditionalFormatting@sqref
  ├─ 阶段 D：平移 hyperlink@ref / autoFilter@ref / brk@id
  ├─ 阶段 E：平移或扩张共享公式 f@ref 与公式文本内的 A1 区间
  ├─ 阶段 F：更新 dimension@ref 末行
  └─ 返回 ShiftReport（逐阶段改了几处，供 evidence 与守卫断言"不是空转"）
```

阶段 A **自底向上**是必须的：从上往下改会让 `r="14"` 先变成 `r="15"`，随后处理原 `r="15"` 时无法区分它是原始行还是刚改过的行。

`ShiftReport` 的每阶段计数进 evidence，让守卫能断言「这条分支真的执行了」而不是「没报错」。

### shift-aware 归一化

归一化只发生在 digest 计算时，形式是一个纯函数：

```text
normalize_row(row, plan) -> int
    return row - plan.count if row >= plan.insert_at + plan.count else row
```

即：after 侧行号 ≥ 插入点 + 插入数 的，减回去；插入点到插入点+count-1 之间的行是**新插入行**，它们属于受管区域，本来就不进"非受管格"集合。

`_managed_sheet_cell_digest` 与 `_sheet_structure_digest` 都接受 `row_shift`；为 `None` 时行为逐字节不变（Requirement 6.4 的纯增量保证）。

### 为什么这个设计不会放宽判据

三条独立理由，各自可被变异 falsify：

1. **位移量是声明值不是观测值**。verifier 用 `plan.count` 归一化，而 `plan.count` 来自 materialize 之前算出的 orphan 数量。若实际位移量与声明不符，归一化后行号对不上 ⇒ digest 不等 ⇒ 判漂移（Requirement 6.9）。
2. **归一化只作用于行号**。`t` / `s` / `f` / `v` 四项照旧逐字喂 hash。把 A30 的值改掉、样式改掉、公式改掉，归一化救不了它。
3. **新插入行不进非受管集合，但它们的内容仍被受管字段判据管**。写格阶段按 projection 落值，roundtrip 反读比对不变。

## Data Model / Types

### `RowShiftPlan`（新增，`excel_materialize.py`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `insert_at` | int | 第一个新行的行号。必须 ≥ `region.first_row` 且 ≤ `region.last_row + 1` |
| `count` | int | 插入行数。必须 > 0（为零时整个 plan 应为 `None`） |
| `style_from` | int | 样式来源行。取受管区域内最后一个既有数据行 |
| `table_key` | str | 所属受管表，进 evidence |

`__post_init__` 调 `assert_no_mutation_surface`，并校验 `count > 0`、`insert_at ≥ 1`、`style_from ≥ 1`。

派生：
- `shift(row) -> int`：`row + count if row >= insert_at else row`
- `unshift(row) -> int`：`row - count if row >= insert_at + count else row`
- `inserted_rows -> range`：`range(insert_at, insert_at + count)`

`MaterializePlan` 新增 `row_shift: RowShiftPlan | None = None`，并进 `as_dict()`。

### `ShiftReport`（新增）

| 字段 | 类型 | 说明 |
|---|---|---|
| `renumbered_rows` | int | 阶段 A 改了几个 `row@r` |
| `renumbered_cells` | int | 阶段 A 改了几个 `c@r` |
| `inserted_rows` | int | 阶段 B 插了几行 |
| `shifted_refs` | Mapping[str, int] | 阶段 C/D 逐 tag 改了几处 |
| `shifted_shared_formulas` | int | 阶段 E 位移了几组 |
| `extended_shared_formulas` | int | 阶段 E 扩张了几组 |
| `dimension_updated` | bool | 阶段 F |

守卫按它断言「每个声明处理的清单项都真的动过」，而不是只看没报错。

### 位移敏感清单（新增模块常量）

```text
ROW_BEARING_STRUCTURES = (
    ("row",                  "@r"),
    ("c",                    "@r"),
    ("mergeCell",            "@ref"),
    ("dataValidation",       "@sqref"),
    ("conditionalFormatting","@sqref"),
    ("hyperlink",            "@ref"),
    ("autoFilter",           "@ref"),
    ("brk",                  "@id"),
    ("dimension",            "@ref"),
    ("f",                    "@ref"),
    ("f",                    "<text A1 ranges>"),
    ("table",                "@ref"),      # 由 identity 保留门承接，不在本函数处理
)
```

与位移函数按 AST 结构判据双向锁死：清单里的每个 `(tag, attr)` 必须在函数里有对应处理分支；函数里出现的每个处理分支必须在清单里。

`table@ref` 标注为「由 identity 保留门承接」—— 它是唯一一项**登记但不在本函数处理**的，理由是 `_classify_parts` 已把 `xl/tables/**` 整类排除、`assert_identity_inventory_retained` 只锁列跨度。这一项的存在是为了让清单是"位移敏感结构"的完整清单，而不是"本函数处理的清单"；两者的差集必须显式登记。

### `_SHEET_STRUCTURE_BLOCKS` 扩充

```text
既有：sheetPr, cols, mergeCells, dataValidations, conditionalFormatting, sheetProtection
新增：dimension, hyperlinks, autoFilter, rowBreaks
```

⚠️ 扩充本身就会让既有 digest 变化。这是**有意**的：它意味着这四类结构从今天起才开始被检查。对既有测试的影响必须逐条核对（Requirement 9.2 要求「位移计划为空时产物 digest 逐字节不变」—— 那说的是 **artifact 字节**不变，不是 digest 值不变；digest 是比对用的中间值，两侧同时变化不影响等价性判定）。

### `FooterAnchorSpec` 扩充

新增 `carries_total_formula: bool = False`。默认假 ⇒ 未声明的契约行为逐字不变。

`_parse_footer_anchor` 解析它；契约 canonical payload 因此变化的 entry 需重发 definition 链（Requirement 5.5）。

## Properties

### Property 1

位移敏感清单与位移函数双向锁死：清单里的每个 `(tag, attr)`（除显式登记的差集项）在位移函数里有对应处理分支，且函数里的每个分支在清单里。

**Validates: Requirements 1.1, 1.5**

### Property 2

`_SHEET_STRUCTURE_BLOCKS` 包含 `dimension` / `hyperlinks` / `autoFilter` / `rowBreaks`，且改动这四类结构中任一项会让 `managed_sheet_structure` aspect 打红。

**Validates: Requirements 1.3, 1.4**

### Property 3

位移计划为空时，`plan_managed_writes` 与 `apply_plan_zip` 的产物字节与本 spec 之前逐字节相同。

**Validates: Requirements 2.3, 6.4, 7.2, 9.2**

### Property 4

`RowShiftPlan` 零写入面，且非法取值（`count <= 0`、插入点越界、样式来源行缺失）各自抛独立可分辨的错误。

**Validates: Requirements 2.2, 2.5, 3.6**

### Property 5

插入行数恰等于 merged projection 中在 substrate 上无物理行的身份数量。

**Validates: Requirements 2.6**

### Property 6

位移是纯函数：同一输入重复调用得到逐字节相同输出，且不改动入参。

**Validates: Requirements 3.1**

### Property 7

位移后插入点以下的每个 `row@r` 与 `c@r` 恰好增加 `count`，其余行号不变，且 `<row>` 保持升序无重复 `r`。

**Validates: Requirements 3.3, 3.7**

### Property 8

新插入行的每一列 `s=` 与样式来源行同列相等，且新插入行不含任何业务值。

**Validates: Requirements 3.4, 3.5**

### Property 9

位移后 `dimension@ref` 的末行不小于实际最大行号。

**Validates: Requirements 3.8**

### Property 10

`si` → (主格坐标, `ref`) 索引对真实模板（K11 的 `H8:H25` si=1、footer 的 si=3）解析正确，且主格与成员可区分。

**Validates: Requirements 4.1**

### Property 11

共享公式主格在插入点之上且区间跨过插入点时，`ref` 末行与公式文本内区间末行同时增加 `count`；主格在插入点之下时首末行整体增加 `count`。

**Validates: Requirements 4.2, 4.3**

### Property 12

契约声明 `carries_total_formula` 为真时合计区间扩张后 footer 合计判据通过；声明为假时不改写任何公式且保持既有 fail-closed 语义。

**Validates: Requirements 4.4, 4.5, 5.2**

### Property 13

受管区域之外的共享公式组只被位移不被扩张。

**Validates: Requirements 4.6**

### Property 14

主格 `ref` 改写后同组成员跨度与主格不一致时 fail closed；且主格永不被替换成字面量。

**Validates: Requirements 4.7, 4.8**

### Property 15

`FooterAnchorSpec.carries_total_formula` 被解析保留，默认假，且字段名不违反 CS-12 禁令。

**Validates: Requirements 5.1, 5.3**

### Property 16

`carries_total_formula` 为真但 footer 行一处公式都没有时 fail closed。

**Validates: Requirements 5.4**

### Property 17

shift-aware 归一化后，与计划一致的插行使全部 aspect 判等价。

**Validates: Requirements 6.1, 6.2, 6.3, 6.5**

### Property 18

归一化不放宽与行位移无关的判据：改动已有 sharedStrings 条目、protected_parts、跨 sheet 部件、非受管格的 `t`/`s`/`f`/`v` 任一，仍判不等价。

**Validates: Requirements 6.6, 6.8**

### Property 19

归一化不改动任何 artifact 字节。

**Validates: Requirements 6.7**

### Property 20

声明插 N 行而实测位移量不等于 N 时判不等价。

**Validates: Requirements 6.9**

### Property 21

footer anchor 判据为「实测 == 冻结 + 预期位移」，三值都出现在失败消息里。

**Validates: Requirements 7.1, 7.3**

### Property 22

footer 合计判据用位移后区间求值；两道门的返回值语义不变。

**Validates: Requirements 7.4, 7.5, 7.6**

### Property 23

`RowSetDivergenceError` 仍在 `FAILURE_KINDS` 中，且四类不可安全执行情形各自可达、两两可分辨。

**Validates: Requirements 8.1, 8.2, 8.4, 8.5**

### Property 24

既有变异锚点指向的守卫在本 spec 改动后仍可被打红（实测确认，不看退出码）。

**Validates: Requirements 8.3, 11.2**

### Property 25

K11 四条冻结模板事实继续成立，且 `backend/wp_templates/` 零字节改动。

**Validates: Requirements 9.1, 9.3**

### Property 26

已发布 definition 与 bundle 不被原地改写。

**Validates: Requirements 9.4**

### Property 27

全量底稿清册由真实库与真实模板现算，结算落在封闭词表内，不可插行的 entry 各有判据编号与解除条件。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.6**

### Property 28

清册覆盖至少一个真实超出骨架行数的 entry 与一个零增长的回归对照 entry。

**Validates: Requirements 10.5**

### Property 29

插行产物通过 OOXML 安全校验与 `structure_fingerprint` 采集（`errors` 为空），且能被 openpyxl 加载、受管区域行数等于预期。

**Validates: Requirements 11.4, 11.5**

### Property 30

六条声明的变异各自打红对应的具体测试，四态判读无 GREEN / ANCHOR-MISS / WRONG-TEST。

**Validates: Requirements 11.1, 11.3**

### Property 31

范围边界成立：无结构性删行实现、无外部关系许可放宽、无 H1 契约改动、无跨 sheet 联动改写、`openpyxl_roundtrip` 可达性判据不变、无新增迁移文件。

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**

## Rollout

1. **先补检查再动结构**：`_SHEET_STRUCTURE_BLOCKS` 扩充 + Property 2 落地，确认那四类结构从"改了没人看"变成"能红"。
2. **纯函数先行**：`RowShiftPlan` / `shift_sheet_rows` / 归一化三者都是纯函数，先在真实模板字节上单测跑通，零 DB 零发布。
3. **verifier 接线**：`row_shift` 参数打通，Property 3 确认零位移路径逐字节不变。
4. **footer 两道门**：改判据，Property 21/22。
5. **共享公式**：`si` 索引层 + 扩张，Property 10~14。
6. **契约字段**：`carries_total_formula`，Property 15/16。
7. **计划接线**：`plan_managed_writes` 第 4 步改造，残余分支保留（Property 23）。
8. **全量清册**：Property 27/28，报告全部 entry 的可插行性。
9. **变异检验**：六条全部收敛为 RED。
10. **真实环境**：插行产物在真实 Excel / OnlyOffice 9.4 打开验证；不可得则标 UNVERIFIABLE。

## Open Gates

1. **`_SHEET_STRUCTURE_BLOCKS` 扩充对既有测试的影响面未知**。四类结构进 digest 后，任何断言具体 digest 值的既有用例都会红。实施第 1 步时先实测影响面，逐条核对是"判据变严"还是"判据被破"。
2. **K11 模板是否含 `hyperlinks` / `autoFilter` / `rowBreaks` 未实测**。若含，扩充会立刻改变 K11 相关 digest；若不含，Property 2 需要另造 fixture 才能非空验证。
3. **D2 的 729 行是否会撞 `SyncLimits` 的行/field 预算未实测**。`max_table_rows=100000` / `max_projection_fields=200000`，729 行 × 39 列 ≈ 28,431 field，看似安全，但要实测确认 `StreamingProjectionBudget` 不在中途拦。
