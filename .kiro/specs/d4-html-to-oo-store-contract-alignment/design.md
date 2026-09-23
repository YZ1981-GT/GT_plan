# Design Document

## Overview

三处缺陷、两个缺陷类、一条结构性堵漏。核心裁决是**把 D4-1 的金额权威载体从 per-field item
迁到行清单 item 的行对象里**，因为后端 D4-1 provider 的**双向**实现早就是按那个形态写的
（`build_store_projection_d41` 读 `row.get(store_key)` / `merge_projection_into_d41_rows`
写 `target[store_key]`），且已有 12/12 归档判据覆盖。改后端去迁就前端要同时改两个方向、
还要给 `payloads` 加前缀扫描能力（`{prefix}-{rowId}-{field}` 是**无界键集**，而现有装配
是「按 item_id 逐条 SELECT」），成本与风险都更高。

| 缺陷 | 落点 | 性质 |
|---|---|---|
| A 存储模型错位（出/回双向） | 前端共享层 `shared/dynamicAdjudicationRows` | 契约对齐 + 数据迁移 |
| B 派生行不落库 | 前端 `useD4Adjudication` | 补投影供给 + 逐格覆盖状态机（选项 b） |
| D 本期 AJE/RJE 小计两侧口径不同（既有，被 b 放大） | 前端 `buildSubtotalRow` | 对齐模板公式 + 差异告警 |
| C store item 清单漏喂（D4-35 / D4-13） | 后端 provider + `store_projection_response` | 单源化 + 结构守卫 |

## Architecture

### 裁决 D1：D4-1 的金额权威载体 = 行清单 item 的行对象

```
改前（两个方向都断）
  HTML 写 ──► D4-1-rows          : [{rowId,label,source,accountCode}]      ← 无金额
        └──► D4-1-{rowId}-{field}: "153431246.16"                          ← 金额在这
  后端 读 ──► D4-1-rows.row[store_key]  ⇒ 恒 None
  后端 写 ──► D4-1-rows.row[store_key]  ⇒ 前端不读，恒不可见

改后（单一载体）
  HTML 写 ──► D4-1-rows: [{rowId,label,source,accountCode,
                           currentUnadjusted,currentAje,currentRje,
                           priorUnadjusted,priorAje,priorRje}]
  后端 读/写 ──► 同一批键（`MANAGED_FIELD_SPECS` 的 store_key，零改动）
```

`MANAGED_FIELD_SPECS` 的 7 个 store_key 就是契约，前端 SHALL 逐字对齐，**不得**在前端再
声明一份同义键名（需求 2.3 的「同一份映射声明」落点）。

### 裁决 D2：共享件按 spec 声明「哪些字段随行清单落库」，D4/K2 同时受益

`DynamicRowsSpec` 已有 `valueFields`（D4 = 6 个金额，K2 = begin/debit/credit/... ）。
`serializeRows()` 改为**把 `valueFields` 的当前值一并写进行对象**，值从调用方传入的
读取器取（共享件不认识 `allResponses`，保持它对存储介质无知）。签名扩展为
`serializeRows(rows, { readField })`，`readField(rowId, field) => string | number | null`。

🔴 **不改 `rowFieldItemId` / per-field 的写入**：per-field item 继续写（见裁决 D3 的
双写过渡），行对象里的值是**派生冗余**，读侧优先级由 D3 规定。这样 D1/J1 等未参与的
消费方零影响（需求 4.3）。

### 裁决 D3：迁移采取「双写 + 读侧行对象优先、缺则回落 per-field」

* **写**：`persistRowList()` 与 `persistFieldValue()` 都触发行清单重写（行对象带值），
  per-field item 继续写 —— 回滚只需改读侧优先级，不必回填数据。
* **读**：`getRowFieldValue(rowId, field)` 改为先读行对象，命中即返回；未命中回落
  per-field item。**旧项目零迁移脚本即可正确显示**（需求 4.2）。
* **回方向**：`merge_projection_into_d41_rows` 写进行对象 ⇒ 读侧行对象优先 ⇒ OO 改动
  立刻在 HTML 可见（需求 2.1）。这正是选「行对象优先」而不是「per-field 优先」的原因：
  反过来会让 OO 的回写永远被旧 per-field 值盖住。
* per-field item 的**删除**不在本 spec 范围（属清理，需另一轮 grep 零调用方后独立 commit）。

### 裁决 D4：派生行落库为 `source='tb'`；OO 侧覆盖**逐格生效**（用户 2026-09-23 拍板选项 b）

落库时机：**不在 `flushHtml` 里顺手写**。理由——`flushHtml` 是「切 OO」路径，在那里第一次
落库会让「切一次 OO 就改一次底稿内容版本」，把只读浏览变成写操作，并让复用命中类判据失稳。
改为在**派生源变化时**同步：`watch(crossSheetMainRows/crossSheetOtherRows)` →
`syncDerivedRowsIntoStore()`（幂等、值未变不写、`source` 恒 `'tb'`）。

派生行与手工行的可区分（需求 1.4）由**已有的 `source` 字段**承担，无需新增列。派生行的
store `rowId` 直接用派生 `rowKey`（`xsheet-{section}-{labelKey}`）⇒ 派生行与其 store 副本
是**按 rowId 精确配对**，不依赖 label 模糊匹配。

#### 覆盖判定必须有「派生快照」这个第三个量

需求 6.1 禁止用「store 值 ≠ 当前派生值」判覆盖 —— 上游一变，**所有**纯派生格都满足该条件、
会被整批误判成人工覆盖。所以行对象里增加一个 HTML-only 键 `derivedSnapshot`：
`syncDerivedRowsIntoStore()` 每次把派生值写进 store 时，**同时**把同一个值写进它。
于是每格有三个量：

| 量 | 含义 |
|---|---|
| `stored` | `D4-1-rows` 行对象里该 store_key 的当前值（可能被 OO 回写改过） |
| `snap` | `derivedSnapshot[field]`，最近一次由派生写入 store 的值 |
| `derived` | 当前现算派生值（`crossSheetMainRows` / `crossSheetOtherRows`） |

🔴 **`derivedSnapshot` 能穿过回方向不被冲掉，是有结构依据的**（不是假设）：
`merge_projection_into_d41_rows` 先 `by_id[rid] = dict(row)` 整行拷贝，随后**只**对
`_COLUMN_KEY_TO_STORE_KEY` 映射出的 7 个 store_key 赋值 ⇒ 其余键逐字保留。这同时也是
需求 2.2「不丢 HTML-only 字段」成立的同一条依据。

#### 逐格四态状态机（需求 6.2 的实现口径）

| 态 | `stored` vs `snap` | `snap` vs `derived` | 含义 | 行为 |
|---|---|---|---|---|
| S1 | = | = | 纯派生 | 显示 `derived`，无标记 |
| S2 | ≠ | = | 人工覆盖，上游未变 | 显示 `stored` + 「已人工覆盖」 |
| S3 | = | ≠ | 无覆盖，上游已变 | 自动跟随：`stored ← derived`、`snap ← derived`（幂等） |
| S4 | ≠ | ≠ | 覆盖 且 上游已变 | 显示 `stored` + 「已人工覆盖（原派生 `snap` → 现派生 `derived`）」+「恢复取数」 |

* 「恢复取数」= `stored ← derived`、`snap ← derived`（回 S1），**只作用于被点的那一格**。
* `overridden` 标记**不落库**、由上表现算（`stored ≠ snap`）—— 少一个可漂移的状态。
  审计留痕（谁/何时覆盖）不在本 spec 范围，登记为 O5。
* 相等判定 SHALL 走与 `readNum` 同源的容差口径，不得裸 `!==`：金额经 JSON/openpyxl 往返会
  出现表示差异，平台已在 projection digest 上踩过同款（`0` vs `0.0` 使复用恒不命中）。

#### `sections` 的改动：派生行做基底，逐格覆盖，不是整行二选一

现状对 store 里与派生行同 `labelKey` 的行是 `continue` **整行跳过**。选项 b 下必须改为
**合并**：以派生行为基底，逐格按上表决定取 `derived` 还是 `stored`。

⚠️ 这使原先「显示口径一字不改」的说法**不再成立**，Property 7 已相应改写为条件形式
（无覆盖时等值 / 有覆盖时必须显示覆盖值）。这是选项 b 的直接代价，显式登记。

### 裁决 D6：本期 AJE/RJE 小计改为逐行汇总 + D4-4 差异告警（需求 7）

模板实测 `C12 = =SUM(C8:C11)` / `D12 = =SUM(D8:D11)`（另 `E12 = =B12+C12+D12`、
`R18` 全列 `SUM(…14:…17)`、`R19 = R18+R12`），而 HTML 的
`buildSubtotalRow(..., adjTotals.mainAje, adjTotals.mainRje)` 把本期 AJE/RJE 小计取成
**D4-4 调整分录汇总额**、不逐行汇总（上期 AJE/RJE 小计反而是逐行汇总）。⇒ 两侧本期
AJE/RJE 小计**今天就可能不等且无告警**。选项 b 让逐行 AJE/RJE 可被 OO 写入，必须先对齐口径，
否则「用户在 OO 填了 C9，HTML 小计不动」会被当成本 spec 引入的新 bug。

裁决：**HTML 改为逐行汇总**（与 Excel 公式同口径），并新增「逐行汇总 ≠ D4-4 汇总额」的
**跨底稿校验告警**。反向（让 Excel 小计去取 D4-4 汇总）要把 R12 从 `FORMULA_MASK` 里挖出来
改成值投影，那会破坏需求 1.3 与已归档的 48 格判据 —— 不选。

🔴 **告警走既有同构范式，不造新机制**：本组件已有 `mainCrossValidation`/`otherCrossValidation`
（小计 vs D4-2/D4-3，超容差返回提示串、不改任何一侧）。「小计 vs D4-4」是第三条同型 computed，
容差走同一个 `BALANCE_TOLERANCE`。「小计恒等于 D4-4」是**审计要求**（由审计师看到告警后调平），
不是本组件的算法职责 —— 算法照 Excel，校验独立告警，两层不冲突（原 O4 的二选一是表述错误，
见 Open Decisions）。平台的公式管理模块是报表 DSL 求值，与这条跨底稿口径校验不同层，不并入。

`buildCrossSheetRow` 的 AJE/RJE 硬编码 `0` 同步改为走覆盖状态机（S1 时仍为 0，因为派生聚合
不产生调整额；S2/S4 取 `stored`），使其上方那条「AJE/RJE 仍从 per-field 键读 ⇒ 审计师对
派生行填的调整不丢」的注释第一次变成真的。`isEditable: r.source !== 'tb' || true` 的
`|| true` 死表达式一并清掉（需求 7.3）。

### 裁决 D5：store item 清单收敛成 provider 单一函数

新增 `phase5_d4_revenue_detail.all_store_item_ids()`（或 provider 协议级
`iter_store_item_ids()`），返回**全部**需要喂 payload 的 item_id：

```
STORE_ITEM_IDS
  ∪ STORE_ITEM_IDS_D45_FIXED
  ∪ STORE_ITEM_IDS_D413_FIXED        ← 现状出方向漏
  ∪ {STORE_ITEM_ID_D435_DICT}        ← 现状出方向漏（不在任何清单里）
  ∪ STORE_ITEM_IDS_D47_DEDICATED     （已在 STORE_ITEM_IDS 内，取并集幂等）
```

`store_projection_response.py` 与 `oo_to_html.py` **都**改为从这一个口径取。
per-item 缺省值（list → `[]` / dict/singleton → `{}` / 纯文本 fixed → `""`）保持既有
provider 单源规则不变 —— 那条规则修过一次（dict-store 拿到 `"[]"` 会抛非 domain
`ValueError` 打挂整个 entry），不得回退。

## Components and Interfaces

| 文件 | 改动 |
|---|---|
| `shared/dynamicAdjudicationRows.ts` | `serializeRows(rows, {readField})` 落 `valueFields`；新增 `readRowFieldWithFallback(rows, responses, spec, rowId, field)` 单源读 |
| `useD4Adjudication.ts` | `persistRowList` 传 `readField`；`getRowFieldValue` 改走单源读；新增 `syncDerivedRowsIntoStore()` + watch；新增 `resolveCellState()` 四态解析 + `restoreDerivedValue(rowId, field)`；`sections` 改逐格覆盖合并；`buildSubtotalRow` 本期 AJE/RJE 改逐行汇总 + 差异告警；清 `buildCrossSheetRow` 的 AJE/RJE 硬编码 0 与 `\|\| true` 死表达式 |
| `D4TabAdjudication.vue` | 覆盖格「已人工覆盖」标记；S4 冲突呈现（覆盖值 / 原派生 / 现派生三值）+「恢复取数」；「逐行汇总 ≠ D4-4」告警 |
| `useK2Adjudication.ts` | 仅改为走同一套读/序列化（无业务改动，需求 4.1 判据面）。**不接覆盖状态机** —— K2-1 无派生行，接了就是死代码 |
| `phase5_d4_revenue_detail.py` | 新增 `all_store_item_ids()`；`STORE_ITEM_ID_D435_DICT` 注释同步 |
| `store_projection_response.py` | payload 装配改走 `all_store_item_ids()` |
| `oo_to_html.py` | base 装配改走 `all_store_item_ids()`（消除三处 `hasattr` 分支的清单来源） |
| `backend/scripts/check/check_store_item_ids_fully_wired.py` | 新 CI 卡点（需求 3.3） |

**后端 D4-1 provider 零改动** —— 这是本设计的一个显式结论，也是「改前端」这条路线的收益：
`build_store_projection_d41` / `merge_projection_into_d41_rows` / `MANAGED_FIELD_SPECS` /
`FORMULA_MASK` / `mapping_digest` 全部不动，已归档的 12/12 判据继续有效。

## Data Models

`D4-1-rows` 行对象（改后，键名逐字取自 `MANAGED_FIELD_SPECS` 的 store_key）：

```json
[{ "rowId": "xsheet-main-yingyeshouru-pifa-fenxiao",
   "label": "营业收入_批发_分销", "source": "tb", "accountCode": "6001",
   "sectionKey": "main-revenue",
   "currentUnadjusted": 153431246.16, "currentAje": 0, "currentRje": 0,
   "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0,
   "derivedSnapshot": { "currentUnadjusted": 153431246.16, "currentAje": 0,
                        "currentRje": 0, "priorUnadjusted": 0,
                        "priorAje": 0, "priorRje": 0 } }]
```

`derivedSnapshot` **只对 `source='tb'` 行存在**（手工行没有"上游"，不需要第三个量）。
它是 HTML-only 键：后端 7 个受管 store_key 之外的键在 merge 里逐字保留（裁决 D4 的结构依据）。
上例是 S1 纯派生态；`currentUnadjusted` 被 OO 改成 `153431300` 而 `derivedSnapshot` 不变
即 S2；此后 D4-2 再变使 `derived` 走到第三个值即 S4。

`sectionKey` 由后端 merge 回填（`SECTION_KEY_FIELD`），前端写入时也 SHALL 带上 ——
否则首次投影时 `_table_key_for_row()` 会把其他段的行默认落进主营段
（`_SECTION_TO_TABLE.get(..., ROWS_TABLE_KEY_MAIN)` 是**静默兜底**，不 fail closed）。
这是本 spec 必须显式处理的一处既有静默兜底风险。

## Error Handling

* 行对象金额值的类型：store 里 SHALL 是 `number` 或 `null`，**不是**字符串。
  `merge.normalize_value` 对 amount 接受数字；HTML store 侧若写字符串会 fail visible。
  前端 `serializeRows` SHALL 在写入前用与 `readNum` 同源的解析归一，不得直接塞
  `String(value)`（per-field item 是纯文本 remark，这是两套介质的真实差异）。
* 缺 `sectionKey` 的行：前端 SHALL 恒写，且后端侧 SHALL 保持现有回填；本 spec **不**放宽
  `_table_key_for_row` 的静默兜底（改它属另一范围），而是在判据里钉住「前端写出的每一行
  都带 sectionKey」。
* D4-35 / D4-13 payload 缺失时 SHALL 仍按 per-item 缺省值走，**不得**因为接进清单就改成
  抛错 —— 未填底稿是常态。

## Correctness Properties

### Property 1: HTML 可见行集 ≡ projection 两区 row_keys，且每行 7 个受管键齐全
**Validates: Requirements 1.1**　现状反例：4 个行身份 / 0 个字段。

### Property 2: projection ≡ materialize 后 extract 的反读结果（逐字段）
**Validates: Requirements 1.2**　挡「projection 对了但 binding 没写」。

### Property 3: FORMULA_MASK 48 格恒不产普通值键
**Validates: Requirements 1.3**　E/I 审定数与 R12/18/19/21 的 B–I 只由 Excel 内部公式产生。

### Property 4: 回方向 merge 后 HTML 读回等值（真链，非 mock）
**Validates: Requirements 2.1**　缺陷 A2 正是「两端各自 mock 全绿而生产双向皆死」。

### Property 5: 回方向不丢 source / accountCode / 非受管列
**Validates: Requirements 2.2**

### Property 6: 旧形态（仅 per-field）数据读回等值 —— 迁移不归零
**Validates: Requirements 4.2**　读侧行对象优先、缺则回落 per-field（裁决 D3）。

### Property 7: 无覆盖时派生行落库前后渲染等值；有覆盖时必须显示覆盖值
**Validates: Requirements 1.4, 1.5**　选项 b 下「一字不改」不再成立，故判据是**条件式**：
S1/S3 格逐行等值，S2/S4 格必须显示 `stored` 且带标记。只断言前半会放过「覆盖被吞掉」。

### Property 8: all_store_item_ids() 覆盖 provider 每一条声明，且出/回两方向都只从它取
**Validates: Requirements 3.1, 3.3**　新增一条未接线的声明必须打红。

### Property 9: D4-35 字段数 > 0、D4-13 两键值等于 store 正文（比值不比键数）
**Validates: Requirements 3.2**　现状 `0 vs 32` / `'' vs 探针正文`。

### Property 10: D1/J1 等非参与消费方的序列化输出逐字节不变
**Validates: Requirements 4.3**

### Property 11: 覆盖逐格封闭 —— 四态各一条，且不存在第五态
**Validates: Requirements 6.2**　按 `(stored vs snap, snap vs derived)` 两个布尔量穷举 4 组，
判据 SHALL 断言实现的状态解析函数对这 4 组之外无可达输出。

### Property 12: 上游变化后纯派生格不得被标成人工覆盖
**Validates: Requirements 6.1**　这是「用 store ≠ derived 判覆盖」那个错法的直接反证：
改 `derived` 而不改 `stored`/`snap`，全部格必须仍是 S3（自动跟随），覆盖标记数 = 0。

### Property 13: S3 自动跟随幂等 —— 值未变不产生第二次写库
**Validates: Requirements 6.3**

### Property 14: S4 双值同时可见，且系统不自动二选一
**Validates: Requirements 6.4**　断言覆盖值、原派生值、现派生值三者都出现在渲染输出里。

### Property 15: 恢复取数只影响被点的那一格，且下次物化把该格写回派生值
**Validates: Requirements 6.5**

### Property 16: HTML 与 OO 的本期 AJE/RJE 小计同口径（以模板公式为第三边）
**Validates: Requirements 7.1**　判据读 `backend/wp_templates/D/D4 收入底稿.xlsx` 的
`C12`/`D12` 真实公式，不拿 HTML 与 OO 互相比对（两侧同错会自洽）。

### Property 17: 逐行 AJE/RJE 之和 ≠ D4-4 汇总额时必须告警，不得任一侧静默盖掉
**Validates: Requirements 7.2**

## Testing Strategy

* **判据先行**：P1 / P9 先写成红判据（现状必红），再动实现。P9 的红形态已用一次性探针
  实证过（D4-35 `0 vs 32`、D4-13 `'' vs 探针正文`），落成测试时 SHALL 复用同一对照结构。
* **真链优先于 mock**：P2 / P4 SHALL 在真 substrate 上跑（参照已归档 spec 的 L2 口径），
  不得两端各自 mock —— 缺陷 A2 恰恰是「两端各自 mock 全绿而生产双向皆死」的产物。
* **覆盖状态机按四态穷举**（P11/P12）：SHALL 用「两个布尔量 × 2」的穷举表驱动，不得逐场景
  手写用例 —— 手写必漏 S4，而 S4 是唯一会静默丢数据的那一态。P12 是**反证式**判据
  （只改 `derived` 不改 `stored`/`snap`，覆盖标记数必须为 0），它专门钉住「用
  `stored ≠ derived` 判覆盖」那个最容易写出来的错法。
* **P16 必须以模板为第三边**：两侧互比会同错自洽 —— 这正是 I 循环那次「38 张列契约全绿而行
  维度从来没人比过」的同型陷阱（源模板当第三边才抓到）。
* **变异检验**（需求 5.1）：至少对 P1 / P4 / P8 / P9 / P12 / P16 各做一次，记录打红条数。
* **真栈 Playwright**（需求 5.2）：D4-1 / D4-35 / D4-13 各一次，证据落
  `docs/operations/evidence/`。⚠️ 逐张 L1 必须 `--workers=1` 串行（OnlyOffice 8080
  单实例并发 contention 会假失败，已实证）。
* **不引入新 pytest 分母依赖**：P8 的守卫落 `backend/scripts/check/`（可独立红），
  理由见需求 3.3。

## Open Decisions

* ~~**O1**：派生行 OO 侧改动是否生效~~ → **2026-09-23 用户拍板选项 b：改了就算，store 为准，
  HTML 标「已人工覆盖」**。已落成需求 1.5/1.6 + 需求 6 全节 + 裁决 D4 的逐格四态状态机
  + Property 7/11~15。代价已显式登记：`sections` 从「整行跳过」改为「逐格合并」、
  「显示口径一字不改」不再成立、并连带触发裁决 D6（见 O4 的处理结论）。
* **O2**：per-field item 的物理删除时机（本 spec 只做双写，不删）。
* **O3**：其余 12 张审定表（K2-1 除外，它随共享层自动受益）何时接桥 —— 不在本 spec，
  但本 spec 的共享层改动是它们的前置。
* ~~**O4**：本期 AJE/RJE 小计口径是否改会与「恒等于 D4-4」冲突~~ → **2026-09-23 用户澄清后
  收口，不再是 Open Decision**。原表述把「算法」与「校验」混成了二选一，是错的：
  - **算法层**：小计按模板 `C12=SUM(C8:C11)` 逐行汇总 —— 这是唯一与 Excel 一致的算法，无分叉，
    不改它反而会让 OO 里填的逐行 AJE/RJE 在 HTML 小计上不生效。
  - **校验层**：「小计是否恒等于 D4-4 汇总额」是一条**跨底稿校验**，套用本组件既有
    `mainCrossValidation`/`otherCrossValidation`（小计 vs D4-2/D4-3）的同构范式：computed
    返回提示串、超容差才亮、指明差异、**不改任何一侧、不阻塞**。审计要求恒等时，由审计师看到
    告警去调平，而不是系统替他把某侧盖掉。裁决 D6 因此**不改变**"D4-1 与 D4-4 该对平"这一
    审计要求，只是把口径不一致从"静默"变成"可见"。
* **O5**：人工覆盖的审计留痕（谁/何时覆盖）。本 spec 的 `overridden` 是现算态、不落库，
  因此无留痕。若质控要求可追溯，需在行对象里加 `overrides: {field: {by, at}}` 并接审计日志
  —— 属独立范围。
