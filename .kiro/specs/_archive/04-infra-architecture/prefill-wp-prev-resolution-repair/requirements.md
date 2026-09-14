# Requirements Document

## Introduction

`prefill_engine` 的 `WP()` 与 `PREV()` 两个公式解析器在运行态**恒返 `None`**，且 fail-soft
无告警。二者合计 **337 条预设**（`WP()` 176 条跨 9 个循环 / `PREV()` 161 条跨 11 个循环）
因此从未取到过任何数值 —— 这是「链条上游合格、整条链仍是死的」缺陷模式的又一实例：
预设声明正确、语法校验通过、`--check` 归零、既有测试全绿，但用户侧一格数据都拿不到。

### 根因（2026-08-07 真实库复核）

两个 resolver 都从 `working_paper.parsed_data['cells']` 取值：

```python
if wp.parsed_data.get("wp_code") == wp_code:                              # 条件 1
    cell_data = wp.parsed_data.get("cells", {}).get(f"{sheet}!{cell_ref}")  # 条件 2
```

真实库（`working_paper` 未删且 `parsed_data` 非空 = **407** 行；`IS NOT NULL` 口径 492）：

| 判据 | 实测 |
|---|---|
| `parsed_data ? 'wp_code'` | **63**（条件 1 可满足） |
| `parsed_data ? 'cells'` | **0** ← 条件 2 全库零命中（两种口径下都是 0） |
| `parsed_data ? 'html_data'` | 70（内层为 `project_context`/`tb_values`/`rows` 等结构键，非金额锚点） |

⇒ `cells` 这个键**在当前平台的任何写入路径下都不产生**。底稿录入值的真实落点是
`checklist_responses(wp_id, item_id, remark/conclusion)`。

### 第二个缺陷：`PREV()` 取到的是本年值

`_resolve_prev_formula` 的 docstring 写「从上年底稿取值（同项目 year-1）」，而查询里
**没有任何 year 条件**；且 `working_paper` 与 `wp_index` **都没有 year 列**（实测），
底稿的年度维度在 project 层 ⇒ 跨年度定位在当前数据模型下无法表达。161 条 `PREV()` 里
**118 条第三参是「审定数」**（占 73%），即「上年审定数」类预设 —— 一旦 `cells` 链修通
而 year 维度不修，这些格会取到**本年**审定数并显示在「上年数」列，属数字级错误。

### 🔴 立项判据的三处修正（2026-08-07 实证，开工前必读）

**修正 1：`cell_ref` 有两个不同口径，立项时混在一起了。**

- **宿主 `cells[].cell_ref`** —— 预设自己的格标识，表示「求出的值**往哪写**」
- **`WP()` / `PREV()` 的第三参** —— 表示「**从哪读**」

立项表格里列的 13 个样例，逐个实测：3 个只是宿主 `cell_ref`（`原值期末未审数` /
`坏账准备期末未审数` / `期初余额`，与取数无关）· 4 个是真第三参 · **7 个两个口径都不存在**
（`期末未审余额` / `期初未审余额` / `期末数-期末未审数` / `明细表期末未审数` /
`期末数-未审余额` / `减值准备期末未审数`）。本 spec 的映射对象**只能是第三参**。

**修正 2：真实规模。** D 循环 `WP()` 的 distinct 三元组是 **12 个**（不是 22/23/37），
distinct 第三参 **11 个**；D 循环 `PREV()` 是 **32 个**三元组。

**修正 3：🔴 映射键必须含 sheet。** 实测 **34 对** `(wp_code, 第三参)` 跨多个 sheet 复用：

```
F2 | 期末余额合计 | 12 sheets      ← 二元组键会把 12 张明细表塌成一条映射
F2 | 期初余额合计 | 11 sheets
H1 | 审定数       |  5 sheets
D6 | 期末合计     |  2 sheets      ← 减值准备表与明细表互相串值 = 数字级错误
D4 | 全年收入合计 |  2 sheets
```

### 🔴 第三个缺陷（本轮新发现，决定本 spec 的能力边界）：目标列大量是「派生列」，不落库

以 `WP('D1','原值明细表（按类别）D1-2','合计-期末未审数')` 为例，实测：

- 存储键是 `D1-cat-rows`（`useD1DetailCategory.ts` 的 `STORAGE_KEY`）
- 它的 `serializeRows()` **只序列化录入列**（`priorUnadjusted`/`priorAje`/`priorRje`/
  `currentIncrease`/`currentDecrease`/`currentAje`/`currentRje`）
- 而 `priorAudited` / `currentUnadjusted` / `currentAudited` 由 `recalcRow()` **加载时重算**，
  「小计」行是 `computed` 的 `subtotalRow` —— **两者都不落库**

⇒ 后端要取「期末未审数合计」，必须在后端复刻前端的行内公式（`未审+AJE+RJE` →
`+增加−减少` → `+AJE+RJE`）与小计聚合。**那是双真源**（前端改公式后端不跟），
属 memory 已登记的高发缺陷模式。故本 spec 采取**宁缺勿造**：只映射**已持久化的列**，
需要派生列的锚点显式进「待对齐清单」并写明理由，不在后端复刻公式。

好消息是实测大多数锚点的目标列**确实落库**（`D1-bd-notetype-rows` 有 `currentUnadjusted` ·
`D2-detail-rows` 有 `currentAudited`/`endBalance` · `D7-2-rows` 有 `endAudited`/`endBalance` ·
`D4-2-rows` 有 `months[]`），只有 D1-2 这一族是派生列。

### 正确范式已存在

同文件的 `_resolve_note_formula` 就是「JSON 内寻址」的正确做法（按 `key`/`label` 匹配行
+ 按列键取值，不碰 `cells`），本 spec 照它实现取值层。

## Requirements

### Requirement 1: `WP()` 取值改走真实数据落点

**User Story:** 作为审计助理，我在明细表录入并保存后，审定表引用该明细表的格应能自动
取到明细表合计，而不是空白。

#### Acceptance Criteria

1. WHEN `WP('D2','明细表D2-2','期末合计')` 求值 THEN 系统 SHALL 经 R2 的锚点映射表
   解析出目标 `item_id` 后从 `checklist_responses` 取值，不再读 `parsed_data['cells']`
2. WHEN 映射目标是标量 `item_id`（`remark` 直接是数值字符串）THEN 系统 SHALL
   直接解析为 `Decimal`
3. WHEN 映射目标是行数组 JSON THEN 系统 SHALL 按声明的聚合方式取值：
   `sum`（对指定列跨全部行求和）/ `sum_list`（列本身是数值数组，如 `months[]`，先行内求和再跨行求和）
   / `row`（按行标识定位单行后取列值）
4. WHEN 目标底稿不存在、`item_id` 未命中、值为空串、或值无法解析为数值 THEN 系统 SHALL
   返回 `None`（保持既有 fail-soft 语义，不抛异常）
5. WHEN `WP()` 实参少于 3 个 THEN 系统 SHALL 返回 `None`（保持既有行为）
6. WHERE 底稿定位需要 wp_code THEN 系统 SHALL 经 `wp_index` JOIN 取得 `wp_id`，
   不依赖 `parsed_data['wp_code']`（该键仅 63/407 存在）
7. WHEN 同一 wp_code 在项目下有多份底稿记录 THEN 系统 SHALL 按**确定性规则**选取
   （`updated_at DESC, id ASC`）并在 docstring 说明，不得依赖查询返回顺序
8. WHEN DB 查询抛异常 THEN 系统 SHALL 记 WARNING 后返回 `None`，不得静默
   （现状无 try/except 也无日志，查询失败会冒泡到上层被吞）
9. 🔴 WHEN 交付 THEN 系统 SHALL 有守卫**连真实库执行**取值层，对映射表每条断言
   不抛异常；且该守卫 SHALL 配「故意写错列名的同形查询必须失败」的反向自检
   —— 源码断言 + 替身单测 + fail-soft 三层组合**查不出 SQL 列名错误**
   （本轮实测：`checklist_responses` 无 `workpaper_id` 列，真实列名 `wp_id`，
   错误列名让 8 条已对齐锚点全部静默返 `None` 而四层验证全绿）

### Requirement 2: 第三参是**中文锚点名**，与 `item_id` 之间必须有显式映射层

**User Story:** 作为平台维护者，我需要知道「预设声明的锚点」与「底稿实际存储键」之间靠什么
对齐，而不是靠猜。

#### 实证前提

`WP()`/`PREV()` 第三参**全部是中文业务锚点名**（`期末合计` / `审定数` / `全年收入合计`），
而 `checklist_responses.item_id` 是**英文 kebab 键**（`D2-detail-rows` / `D1-cat-rows`）。
两者精确匹配 0 / 后缀匹配 0 ⇒ 「按 item_id 后缀解析」这条路不成立，必须建映射。

D 循环 `checklist_responses` 值形态分布（120 条）：json-array **60** / empty 28 /
text 17 / json-object 10 / numeric-scalar **5** —— 即绝大多数锚点值藏在行数组里，
只有 5 条是标量（且实测那 5 条是 `D1-ecl-total-*` 三条 + `D1-entry-*` 两条，
**不是**立项文档所写的 `D1-tb-total` / `D2-1-tb-total` —— 那两个 item_id 全库不存在）。

#### Acceptance Criteria

1. WHEN 修复后 THEN 公式的**实参个数与位置语义** SHALL 保持 `(wp_code, sheet, cell_ref)`
   三参不变（337 条预设声明不重写）
2. WHEN 求值 THEN 系统 SHALL 经**显式声明的锚点映射表**把三参组解析为取值规格
   （`item_id` + 列键 + 聚合方式 [+ 行标识]），不得用字符串启发式匹配
3. WHEN 映射键构造 THEN 它 SHALL 是**三元组** `(wp_code, sheet, cell_ref)`；
   二元组键 SHALL 被守卫禁止（实测 34 对第三参跨 sheet 复用）
4. IF 某条预设的三参组在映射表中无登记 THEN 系统 SHALL 返回 `None`
   且该条 SHALL 出现在「待对齐清单」诊断输出中
5. WHEN 交付 THEN 「待对齐清单」的条目数 SHALL 由守卫钉死只减不增，防止新增预设时漏登记
6. WHERE 本 spec 只负责建立映射机制与 D 循环 12 条 `WP()` 三元组 THEN 其余 8 个循环的
   164 条 `WP()` 与全部 161 条 `PREV()` SHALL 登记为范围外，由各 per-cycle spec 补齐；
   该范围外登记 SHALL 由守卫断言其存在且带理由
7. 🔴 WHEN 校验范围外登记完备性 THEN 判据 SHALL **从预设实时派生**「非 D 目标集合」，
   不得写死循环字母表 —— 写死清单既不会随预设新增而打红，也**表达不了非循环 target**
   （实测 `WP('PL','利润表','净利润')` 的 `PL` 是**利润表（报表）不是底稿**，
   首字母落在 `EFGHIJKLMN` 之外 ⇒ 该条既不在映射表、也不在待对齐清单、
   也不被任何范围外登记覆盖 = 无人认领的灰区）
8. WHERE 某 `WP()` 的目标不是底稿（`wp_index` 无该 wp_code）THEN 它 SHALL 登记在
   **独立的**「非底稿目标」表而非按循环登记的表 —— 后者会暗示「补个映射就行」，
   而真实情况是取值层要换数据源（需读 `financial_report` / `report_config`）；
   该表的每条 SHALL 由守卫断言其确实不是循环编号形态（防真实循环被塞进来逃避对齐）

### Requirement 3: 映射目标必须是**已持久化的列**，禁在后端复刻前端派生公式

**User Story:** 作为平台维护者，我不希望为了取一个合计值而在后端抄一份前端的行内公式，
那会形成改一侧另一侧不跟的双真源。

#### Acceptance Criteria

1. WHEN 某锚点的目标列不在该 `item_id` 的**前端序列化字段集**内 THEN 该锚点 SHALL
   进入待对齐清单，理由写明「派生列不落库，后端复刻会形成双真源」
2. WHEN 交付 THEN 系统 SHALL 有守卫**读前端 composable 源码**抽出序列化字段集，
   与映射表声明的列键做交叉锁死；映射到非持久化列即打红
3. WHEN 该守卫的抽取失效（正则不命中 / 字段集为空）THEN 守卫 SHALL 通过反向自检打红
4. WHERE 让派生列可被后端取用需要前端把小计/派生列另存为独立标量 `item_id`
   THEN 该变更 SHALL 登记为范围外，另立 spec

### Requirement 4: `PREV()` 的跨年度缺陷显式登记

**User Story:** 作为质量控制复核合伙人，我需要知道「上年审定数」这类预设当前是否可信。

#### Acceptance Criteria

1. WHEN 本 spec 交付 THEN `_resolve_prev_formula` 的 docstring SHALL 如实说明
   「当前数据模型无 year 维度，无法定位上年底稿」，删除「同项目 year-1」的失实表述
2. WHEN `PREV()` 无法确定年度 THEN 系统 SHALL 返回 `None`，**不得**回退到本年值
3. WHEN 本 spec 交付 THEN 系统 SHALL 有守卫断言 `_resolve_prev_formula` 源码中
   不存在「查本年底稿」的回退分支
4. WHERE 跨年度取数需要数据模型变更 THEN 该变更 SHALL 登记为范围外，另立 spec

### Requirement 5: 缺陷不可回退

**User Story:** 作为平台维护者，我不希望下个会话把 `cells` 读法改回来。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN 系统 SHALL 断言 `prefill_engine` 源码中两个 resolver 不再引用
   `parsed_data['cells']`（含 `.get("cells"` 形态），判定前先剥注释与 docstring
2. WHEN 运行守卫 THEN 系统 SHALL 连库断言 `parsed_data ? 'cells'` 全库为 0，
   并配正向锚点（`? 'html_data'` > 0 且 `? 'wp_code'` > 0）证明扫描面非空
3. WHEN 对修复后的实现做变异（改回读 `cells` / 去掉 `wp_index` JOIN / 让 `PREV` 回退本年
   / 行匹配回退第一行 / 二元组键 / 映射到派生列）THEN 守卫 SHALL 打红
4. WHEN 守卫的判据本身失效（如正则不命中、常量为空）THEN 守卫 SHALL 通过反向自检打红，
   而非静默通过

### Requirement 6: 零回归

**User Story:** 作为平台维护者，我需要确认修复不影响其余 8 个 resolver。

#### Acceptance Criteria

1. WHEN 修复后 THEN `TB` / `TB_SUM` / `ADJ` / `LEDGER` / `AUX` / `NOTE` /
   `LEDGER_DETAIL` / `COUNT_LEDGER` 八个 resolver 的行为 SHALL 逐字不变
2. WHEN 修复后 THEN `_FORMULA_RESOLVERS` 的键集 SHALL 不变
   （既有 `test_formula_runtime_zero_regression.py` 已钉死，本 spec 不得改它）
3. WHEN 修复后 THEN 既有 prefill 相关测试 SHALL 全部通过，新增失败为 0
4. IF 某既有测试锁定了 `cells` 读法 THEN 该测试 SHALL 被诚实改写并在 Notes 说明原因，
   不得用跳过/放宽断言的方式绕过

### Requirement 7: 真实库验收

**User Story:** 作为现场经理，我需要看到修复后真实项目里确实取到了数。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 提供只读诊断脚本，对真实项目逐条求值 D 循环的 `WP()` 预设
   并输出结果
2. WHEN 诊断脚本运行 THEN 它 SHALL 区分**六态**：`HIT`（取到数）/ `EMPTY`（`item_id`
   存在但值为空或非数值）/ `NO_WORKPAPER`（该 wp_code 在本项目无底稿）/ `NO_ITEM`
   （底稿存在但 `item_id` 未落库=未编制）/ `NO_COLUMN`（行数组里无该列键）/
   `UNALIGNED`（三参组不在映射表中）—— 合并成「无数据」会让「本项目没录」与
   「链路仍是死的」不可区分
3. WHEN 诊断脚本对某条取到数 THEN 它 SHALL 同时输出取值路径（`item_id` + 列键 + 聚合方式
   + 参与行数）供人工核对，不只输出金额
4. WHERE 验收发现某循环锚点大面积未映射 THEN 该循环 SHALL 记入待对齐清单，
   不在本 spec 内逐条补映射（各 per-cycle spec 负责）
5. WHEN 真实库某循环全部 `NO_ITEM`（底稿未编制）THEN 诊断脚本 SHALL 如实报告，
   **不得**构造 fixture 冒充「已修好」的证据

## Glossary

| 术语 | 含义 |
|------|------|
| resolver | `prefill_engine._FORMULA_RESOLVERS` 里的取值函数，一个公式类型一个（现 10 个） |
| 死链 | 公式声明合法、语法校验通过，但 resolver 的数据源在真实库零命中 ⇒ 恒返 `None` 且无告警 |
| `parsed_data.cells` | `WP`/`PREV` 当前读取的 JSONB 键。**全库零命中**，任何写入路径都不产生它 |
| 宿主 cell_ref | 预设 `cells[].cell_ref` —— 值**往哪写**。与本 spec 的映射无关 |
| 第三参（锚点） | `WP()`/`PREV()` 的第三个实参 —— 值**从哪读**。本 spec 的映射对象 |
| item_id | `checklist_responses.item_id`，底稿录入值的真实存储键（如 `D2-detail-rows`） |
| 持久化列 | 前端 `serializeRows()` 真正写进 `remark` 的字段。**派生列不在其中** |
| 派生列 | 前端加载时由 `recalcRow()` 重算、或由 `computed` 小计产生的列，**不落库** |
| 锚点映射表 | 本 spec 新建的真源：`(wp_code, sheet, cell_ref) → 取值规格`，逐条带实证 |
| 待对齐清单 | 尚无法映射的三参组，守卫钉死其规模只减不增 |
| fail-soft | 取不到数返 `None` 不抛异常。本 spec 保留该语义，但要求六态在诊断层可分辨 |
| 六态 | `HIT`/`EMPTY`/`NO_WORKPAPER`/`NO_ITEM`/`NO_COLUMN`/`UNALIGNED`，禁合并成「无数据」 |
