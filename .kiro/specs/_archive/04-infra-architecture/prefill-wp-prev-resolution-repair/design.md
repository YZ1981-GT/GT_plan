# Design Document

## Overview

修复 `prefill_engine` 的 `WP()` / `PREV()` 两个 resolver 的取值链，并为「预设锚点 →
真实存储键」建立单一真源映射表。

**设计的核心约束来自三条实证**：

1. 预设第三参与 `checklist_responses.item_id` **零重叠**（不同世代的独立命名空间）
   ⇒ 必须显式建映射，且映射是**会计判断**（哪个 item_id 的哪一列才是「期末合计」），
   不能靠字符串规则推导。
2. **34 对第三参跨 sheet 复用**（`F2 | 期末余额合计 | 12 sheets`）
   ⇒ 映射键必须是三元组，二元组键会让 12 张明细表塌成一条。
3. **目标列可能是前端派生列**（`D1-cat-rows` 的 `currentUnadjusted` 与小计行都不落库）
   ⇒ 后端复刻其公式就是双真源 ⇒ 本 spec 只映射持久化列，派生列进待对齐清单。

由此确定四条设计原则：

1. **映射表是声明式真源，逐条带实证** —— 每条写明它对应哪个 `item_id` 的哪个列键、
   该列在前端序列化字段集里的位置。没有实证的条目不进表。
2. **resolver 只做机械取值** —— 查表 → 定位底稿 → 取 `remark` → 按声明聚合 →
   返 `Decimal | None`。零会计判断、零启发式回退、**零公式复刻**。
3. **「未对齐」必须与「值为空」可区分** —— 两者都返 `None`（保持 fail-soft），但诊断层
   与守卫层必须能分辨六态，否则修完也不知道修没修好。
4. **持久化列约束由守卫结构性保证** —— 守卫读前端 composable 源码抽序列化字段集，
   与映射表的列键交叉锁死。这把「双真源风险」变成可检测。

### 不做的事（范围外，显式登记）

- **`PREV()` 的跨年度定位** —— `working_paper` 与 `wp_index` 都无 year 列，需数据模型变更
- **派生列/小计的后端复算** —— 正解是前端把小计另存为独立标量 `item_id`，另立 spec
- **337 条预设的逐条对齐** —— 本 spec 只交付 D 循环 `WP()` 的 12 个三元组 + 机制；
  其余 8 个循环的 164 条 `WP()` 与全部 161 条 `PREV()` 由各 per-cycle spec 按本机制补
- **`formula_engine._handle_wp`（另一条求值链）** —— 它读 `ctx.wp_data`，本 spec 不碰；
  但守卫要钉死「两条路径的实参语义差异已登记」，防后来者"统一"

## Architecture

```
预设 JSON: WP('D2','明细表D2-2','期末合计')
                    │
                    ▼
        prefill_engine._resolve_wp_formula
                    │  (args → wp_code, sheet, cell_ref)
                    ▼
    ┌───────────────────────────────────────────────┐
    │ prefill_anchor_map.resolve_anchor(             │  ← 新建真源（声明式）
    │   wp_code, sheet, cell_ref) -> AnchorSpec|None │
    │   AnchorSpec{item_id, column, aggregate,       │
    │              row_key?, evidence}               │
    │   键 = 三元组（禁二元组）                       │
    └───────────────────────────────────────────────┘
                    │  未命中 → UNALIGNED（诊断层可见 + logger.warning）
                    ▼
    ┌───────────────────────────────────────────────┐
    │ prefill_anchor_map.read_anchor_value(          │  ← 取值层（纯机械）
    │   db, project_id, spec)                        │
    │   ① wp_index JOIN → wp_id（确定性排序）        │
    │   ② checklist_responses(wp_id, item_id).remark │
    │   ③ parse_anchor_value(raw, spec)  ← 零 DB 纯函数│
    └───────────────────────────────────────────────┘
                    │
                    ▼
        AnchorReadResult{status: 六态, value, detail}
                    │  resolver 只取 .value（对外仍是 Decimal|None）
                    ▼
              Decimal | None
```

`PREV()` **不复用**这条链 —— 它在入口即返 `None`（无 year 维度，R4.2），
并在 docstring 如实说明。这是 fail-closed 而非 fail-soft。

### 为什么不复用 `_resolve_note_formula` 的实现

它是**正确范式**（按 `key`/`label` 匹配行 + 列键取值，不碰 `cells`），本 spec 照它的
形状写取值层。但不能直接复用函数体：它查 `disclosure_notes.table_data`，而我们查
`checklist_responses`；且它只做「单行取值」，而实测本 spec 的主体是**跨行聚合**
（`期末合计` = 对整列求和），语义不同。

## Components and Interfaces

### 组件 1：`backend/app/services/prefill_anchor_map.py`（新建，单模块）

🔴 **单模块而非两模块** —— 映射表与取值层共用 `AnchorSpec`/六态枚举，拆两个文件会产生
循环 import 或第三个 types 模块；且取值层只有 ~80 行，不值得单独成文件。

```python
class AnchorAggregate(str, Enum):
    SUM = "sum"            # 对指定列跨全部行求和
    SUM_LIST = "sum_list"  # 列本身是数值数组（如 months[12]）：行内求和后跨行求和
    ROW = "row"            # 按 row_key 定位单行后取列值

@dataclass(frozen=True)
class AnchorSpec:
    item_id: str                       # checklist_responses.item_id
    column: str                        # 行数组的列键；标量态传 ""
    aggregate: AnchorAggregate
    row_key: str | None = None         # aggregate=ROW 时必填
    evidence: str = ""                 # 实证：该列在哪个 composable 的序列化字段集里
    #: 该列所属的前端序列化真源（供 Property 4 交叉锁死）
    serializer_module: str = ""

class AnchorReadStatus(str, Enum):
    HIT = "hit"
    EMPTY = "empty"                # item_id 存在但值为空/非数值/空数组
    NO_WORKPAPER = "no_workpaper"  # 该 wp_code 在本项目无底稿
    NO_ITEM = "no_item"            # 底稿存在但 item_id 未落库（未编制）
    NO_COLUMN = "no_column"        # 行数组里无该列键
    UNALIGNED = "unaligned"        # 三参组不在映射表（由调用方置入）

@dataclass(frozen=True)
class AnchorReadResult:
    status: AnchorReadStatus
    value: Decimal | None
    detail: str = ""               # 溯源：item_id + 列键 + 聚合方式 + 参与行数

#: (wp_code, sheet, cell_ref) → AnchorSpec
ANCHOR_MAP: dict[tuple[str, str, str], AnchorSpec]

#: (wp_code, sheet, cell_ref) → 原因（≥20 字，带实证标记）
UNALIGNED: dict[tuple[str, str, str], str]

#: 范围外登记：其余循环由各自 spec 补（R2.6）
OUT_OF_SCOPE_CYCLES: dict[str, str]

def resolve_anchor(wp_code, sheet, cell_ref) -> AnchorSpec | None
def parse_anchor_value(raw: str | None, spec: AnchorSpec) -> AnchorReadResult   # 零 DB
async def read_anchor_value(db, project_id, wp_code, spec) -> AnchorReadResult
def assert_map_consistent() -> None      # import 期自检
```

**`assert_map_consistent()` 在 import 期执行**（与平台既有 `note_conversion_row_codes`
同范式）：断言两表键集**互斥**、键必须是三元组、`evidence` 非空且 ≥20 字、
`aggregate=ROW` 时 `row_key` 非空、`aggregate != ROW` 时 `row_key` 必须为空。

### 组件 2：`_resolve_wp_formula` 改写

```python
async def _resolve_wp_formula(db, project_id, year, args) -> Decimal | None:
    if len(args) < 3:
        return None
    wp_code, sheet_name, cell_ref = args[0], args[1], args[2]
    spec = resolve_anchor(wp_code, sheet_name, cell_ref)
    if spec is None:
        logger.warning("WP() 锚点未对齐：(%s, %s, %s)", wp_code, sheet_name, cell_ref)
        return None
    try:
        res = await read_anchor_value(db, project_id, wp_code, spec)
    except Exception:
        logger.warning("WP() 取值失败：%s", spec.item_id, exc_info=True)
        return None
    return res.value          # HIT 才非 None
```

### 组件 3：`_resolve_prev_formula` fail-closed

```python
async def _resolve_prev_formula(db, project_id, year, args) -> Decimal | None:
    """=PREV('wp_code','sheet','cell') → 恒返 None（当前数据模型无 year 维度）。

    `working_paper` 与 `wp_index` **都没有 year 列**（实测），底稿的年度维度只在
    project 层 ⇒ 无法定位「上年底稿」。改造前的实现从 `parsed_data['cells']` 取值
    且查询里没有任何 year 条件 —— 一旦 `cells` 链修通就会取到**本年**值并显示在
    「上年数」列（161 条 PREV 里 118 条第三参是「审定数」），属数字级错误。
    故本函数 fail-closed：宁缺勿造。跨年度取数需数据模型变更，已登记为范围外。
    """
    return None
```

### 组件 4：诊断脚本 `backend/scripts/diagnose/verify_prefill_wp_prev_live.py`

只读。对真实项目逐条求值 D 循环 12 个 `WP()` 三元组，按六态分组输出 + 金额 + 取值路径。
`--all-cycles` 扫全部 337 条（只报六态分布，不逐条打印）。输出用
`Path.write_text(encoding='utf-8')` 自己写盘，控制台只打 ASCII。

## Data Models

### D 循环 `WP()` 的 12 个真实三元组（本 spec 的全部对齐对象）

| # | wp_code | sheet | 第三参 | 存储键 | 目标列 | 可否映射 |
|---|---|---|---|---|---|---|
| 1 | D1 | 原值明细表（按类别）D1-2 | 合计-期末未审数 | `D1-cat-rows` | `currentUnadjusted` | ❌ 派生列 |
| 2 | D1 | 原值明细表（按类别）D1-2 | 期末合计 | `D1-cat-rows` | `currentAudited` | ❌ 派生列 |
| 3 | D1 | 坏账准备明细表D1-4 | 按票据种类小计-期末未审数 | `D1-bd-notetype-rows` | `currentUnadjusted` | ✅ 持久化 |
| 4 | D2 | 坏账准备明细表D2-3 | 坏账准备期末余额 | `D2-bd-*-rows` | `currentAudited` | ⚠️ 三个键需裁决 |
| 5 | D2 | 审定表D2-1 | 审定数 | 待查 | — | ⚠️ |
| 6 | D2 | 明细表D2-2 | 期末合计 | `D2-detail-rows` | `endBalance` | ✅ 持久化 |
| 7 | D3 | 预收账款明细表D3-2 | 期末合计 | `D3-det-rows` | 待查 | ⚠️ |
| 8 | D4 | 主营业务收入明细表D4-2 | 全年收入合计 | `D4-2-rows` | `months` | ✅ SUM_LIST |
| 9 | D4 | 其他业务收入明细表D4-3 | 全年收入合计 | `D4-3-rows` | `currentUnadjusted` | ✅ 持久化 |
| 10 | D6 | 合同资产减值准备明细表D6-3 | 期末合计 | `D6-3-rows` | 待查 | ⚠️ |
| 11 | D6 | 明细表D6-2 | 期末合计 | `D6-2-rows` | 待查 | ⚠️ |
| 12 | D7 | 明细表D7-2 | 期末合计 | `D7-2-rows` | `endBalance` | ✅ 持久化 |

「待查/待裁决」项由 Task 8 逐个查源码定案，能对齐的进 `ANCHOR_MAP`，
不能的进 `UNALIGNED` 并写理由。**表中的「可否映射」列是 Task 8 的输入而非结论**。

### 持久化列 vs 派生列（本 spec 能力边界的判据）

`useD1DetailCategory.serializeRows()` 逐字：

```typescript
const data = rows.value.map(r => ({
  rowId, category, isFixed,
  priorUnadjusted, priorAje, priorRje,
  currentIncrease, currentDecrease, currentAje, currentRje,
}))
```

`priorAudited` / `currentUnadjusted` / `currentAudited` 不在其中，由 `recalcRow()`
加载时重算；`subtotalRow` 是 `computed`。⇒ 后端拿不到，映射到它们必须打红。

### 全库预设规模（决定波及面，2026-08-07 实测）

| 函数 | 调用点 | 宿主循环分布 |
|---|---|---|
| `WP` | **176** | F 48 / G 42 / D 21 / K 20 / E 17 / N 16 / H 6 / J 3 / M 3 |
| `PREV` | **161** | D 38 / G 27 / H 21 / K 15 / M 14 / N 11 / I 10 / L 10 / J 7 / F 6 / E 2 |

`PREV()` 第三参「审定数」**118 条**（73%）。

## Correctness Properties

### Property 1: `cells` 键在真实库确实零命中

连库断言 `working_paper` 未删且 `parsed_data` 非空的行中 `parsed_data ? 'cells'` 为 0，
并配正向锚点（`? 'html_data'` > 0、`? 'wp_code'` > 0）证明扫描面非空。
一旦将来某写入路径开始产生它，本断言打红提醒复核设计前提。

**Validates: Requirements 5.2**

### Property 2: resolver 不再引用 `parsed_data['cells']`

源码级断言 `_resolve_wp_formula` / `_resolve_prev_formula` 函数体内不出现
`"cells"` / `'cells'`。需先 `strip_comments()`（修复说明会写该字样），
并配「原始源码确实含该字样」的反向自检防断言空转。

**Validates: Requirements 5.1**

### Property 3: 映射表与待对齐清单互斥且完备

`ANCHOR_MAP` 键集 ∩ `UNALIGNED` 键集 = ∅；且两者并集 **== D 循环 `WP()` 的 12 个
真实三元组**（从 `prefill_formula_mapping.json` 实时解析得出，不写死清单）
—— 即每条预设要么有映射，要么显式登记为待对齐，不留灰区。

**Validates: Requirements 2.4, 2.5**

### Property 4: 🔴 映射的列键必须在前端序列化字段集内（防双真源）

守卫读前端 composable 源码，抽出 `serializeRows()`（或等价持久化函数）真正写入的字段名集合，
断言 `ANCHOR_MAP` 每条的 `column` 都在其中。反向自检两条：
① 拿 `D1-cat-rows` 的 `currentUnadjusted`（已知派生列）构造替身条目，断言守卫打红；
② 断言抽取出的字段集非空（正则失效时字段集为空会让断言恒成立 = 空转）。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: 映射键是三元组，禁二元组

源码级断言 `ANCHOR_MAP` 的每个键 `len(key) == 3`；且连库/解析级断言
存在至少一组「同 `(wp_code, cell_ref)` 跨两个 sheet」的真实预设
（实测 34 对，D 循环内有 `D6 | 期末合计`）—— 证明二元组键确实会塌。

**Validates: Requirements 2.3**

### Property 6: 每条映射带实证

`AnchorSpec.evidence` 非空、长度 ≥ 20、且命中实证标记
（`item_id` / `serializeRows` / `composable` / 源模板 之一）。防映射表变成「猜出来的」。

**Validates: Requirements 2.2**

### Property 7: 六态可分辨

`parse_anchor_value` / `read_anchor_value` 对六种情形分别返回对应 `AnchorReadStatus`，
且 `HIT` ⟺ `value is not None`。反向自检：构造「`item_id` 存在但值为空串」的替身，
断言得 `EMPTY` 而非 `HIT`/`NO_ITEM`；构造「列键不存在」的行数组，断言得 `NO_COLUMN`。

**Validates: Requirements 7.2, 7.3**

### Property 8: 聚合语义正确且行匹配不回退第一行

`SUM` 对整列求和（非数值行跳过不算 0，全非数值 → `EMPTY`）；
`SUM_LIST` 先行内数组求和再跨行求和；
`ROW` 在 `row_key` 不存在于行数组时返 `NO_ROW`-等价态（`NO_COLUMN` 或专用态），
**不得**返回第一行的值。这是「静默取错行」的防线。

**Validates: Requirements 1.3, 1.4**

### Property 9: `PREV()` 不回退本年

断言 `_resolve_prev_formula` 恒返 `None`，且源码不含 `WorkingPaper` 查询与
「year-1 / 上年底稿」字样。变异检验：让它回退查本年底稿 ⇒ 守卫必须打红。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 10: 八个其余 resolver 零回归

`_FORMULA_RESOLVERS` 键集不变（复用既有 `test_formula_runtime_zero_regression.py`
的基线，本 spec 不改它）；`TB`/`TB_SUM`/`ADJ`/`LEDGER`/`AUX`/`NOTE`/
`LEDGER_DETAIL`/`COUNT_LEDGER` 八个函数体按哈希断言逐字不变。

**Validates: Requirements 6.1, 6.2**

### Property 11: 底稿定位不依赖 `parsed_data['wp_code']` 且确定性排序

源码断言取值层经 `wp_index` JOIN 取 `wp_id` 且带 `ORDER BY`；
反向自检：该键仅 63/407 存在，若实现改回依赖它，对其余 344 个底稿必然取不到数。

**Validates: Requirements 1.6, 1.7**

### Property 12: DB 异常必须记 WARNING

源码断言 `_resolve_wp_formula` 的取值调用被 `try/except` 包裹且 except 分支内有
`logger.warning`。变异检验：去掉 logger ⇒ 打红。
memory 已记：`except Exception` + fail-open 会把接线错误伪装成「本项目无此数据」。

**Validates: Requirements 1.8**

### Property 13: 待对齐清单只减不增

清单条目数设上限常量，守卫断言实际 ≤ 上限，且上限只许下调。
防「对不齐就往清单里加一条」把清单当逃逸阀。每条理由 ≥20 字且含实证标记。

**Validates: Requirements 2.4, 2.5**

### Property 14: 范围外登记完备且**从预设实时派生**

🔴 **判据不得写死循环字母表** —— 初版写 `expected = set("EFGHIJKLMN")`，
它既不会随预设新增而打红，也表达不了非循环 target（见 Property 18）。
正确判据 = 从 `prefill_formula_mapping.json` 实时派生「非 D 目标集合」，
断言每一个都被 `OUT_OF_SCOPE_CYCLES`（按循环）或
`OUT_OF_SCOPE_NON_WORKPAPER_TARGETS`（按 target）之一覆盖，两表并集无遗漏。
每条理由 ≥20 字；并断言 `ANCHOR_MAP` 里**不含**非 D 循环的 wp_code
（防越界对齐后无人维护）。配反向锚点：派生出的非 D 目标数 ≥5，否则解析失效即空转。

**Validates: Requirements 2.6, 2.7, 7.4**

### Property 15: 两条 `WP` 实现路径的差异已登记

`prefill_engine._resolve_wp_formula`（三参，读 `checklist_responses`）与
`formula_engine._handle_wp`（读 `ctx.wp_data`）是**两套寻址空间**。
断言存在显式登记常量说明二者差异，防后来者"统一"时把本 spec 的修复覆盖掉。

**Validates: Requirements 6.1**

### Property 16: 范围外的数据模型/前端变更已登记且与待对齐清单挂钩

`OUT_OF_SCOPE_CHANGES` 必须含两键：`prev_year_dimension`（`working_paper`/`wp_index`
加 year 列或改走 project 年度，`PREV()` 跨年度的前置）与
`frontend_persist_derived_columns`（前端把派生列/小计另存为独立标量 `item_id`，
让后端可取用派生值的正解）。每条理由 ≥20 字。

并断言 `UNALIGNED` 里凡以「派生列」为原因的条目都在理由中引用后一条登记键 ——
把「为什么对不齐」与「正解在哪」绑死，防清单变成无出口的黑洞。

**Validates: Requirements 3.4, 4.4**

### Property 17: 🔴 取值层 SQL 必须在真实库可执行（本轮 P0 的防线）

连库**真跑** `read_anchor_value`，对 `ANCHOR_MAP` 每条断言不抛异常且不落 `ERROR` 态；
并要求至少一条 `HIT`。配两条自检：① 故意写错列名的同形查询必须失败（证明探针真在发 SQL）
② 正确列名必须可执行。

**为什么必须是「真实执行」而非源码断言**：本轮实测抓到 P0 —— 取值层写
`WHERE workpaper_id = ...` 而 `checklist_responses` 的真实列名是 **`wp_id`**（无
`workpaper_id` 列）⇒ 每次求值抛 `UndefinedColumnError`，被 `_resolve_wp_formula` 的
`except Exception` 吞成 WARNING ⇒ 8 条已对齐锚点**全部**仍返 `None`，而源码守卫
（Property 2/4/5/11/12）全绿、44 个纯函数单测全绿、characterization「恒返 None」
也全绿（恰好与「修好了」不可区分）。⇒ 「源码守卫 + 替身单测 + fail-soft」这三层组合
本身就是本 spec 要修的缺陷模式，唯一防线是真实执行。

（注：上一行原本以 `Property` 开头，会被 spec schema 校验器当成畸形 Property 标题 ——
正文提到 Property 编号时必须避免出现在行首。）

**Validates: Requirements 1.8, 7.1, 7.2**

### Property 18: 非底稿 target 必须独立登记（不得混进循环登记表）

范围外登记按预设**实时派生**「非 D 目标」集合，断言每个都被
`OUT_OF_SCOPE_CYCLES`（目标是底稿）或 `OUT_OF_SCOPE_NON_WORKPAPER_TARGETS`
（目标不是底稿）之一覆盖；并断言后者的键**不是**循环编号形态（`^[A-N]\d+$`）。

**为什么需要它**：原判据 `expected = set("EFGHIJKLMN")` 是**写死字母表**，有两个后果 ——
① 预设新增别的目标时不会打红；② 结构上表达不了非循环字母的 target。实测
`WP('PL','利润表','净利润')` 与 `'上期净利润'` 两条（宿主 `M6 明细表M6-2`）：**`PL` 是
利润表（报表）不是底稿**，`wp_index` 无此 wp_code ⇒ 本 spec 的「`wp_index` JOIN +
`checklist_responses`」取值链**结构上取不到**；而 `P` 落在字母表外，于是这两条既不在
`ANCHOR_MAP`、也不在 `UNALIGNED`、也不被任何范围外登记覆盖 = **无人认领的灰区**
（Property 3 只校验 D 循环并集，抓不到它）。两张表分开的意义在于：混进循环登记表会
暗示「补个映射就行」，而真实情况是**取值层要换数据源**（读 `financial_report` /
`report_config` 的 `ROW()`），属另一 spec。

**Validates: Requirements 2.6, 7.4**

## Error Handling

| 情形 | 行为 | 状态 | 理由 |
|---|---|---|---|
| `args` < 3 | 返 `None` | — | 保持既有行为（R1.5） |
| 三参组未在映射表 | 返 `None` + `logger.warning` | `UNALIGNED` | 不猜；进待对齐清单 |
| 该 wp_code 在本项目无底稿 | 返 `None` | `NO_WORKPAPER` | 底稿未生成是正常业务态 |
| `item_id` 未落库 | 返 `None` | `NO_ITEM` | 明细表未编制，非缺陷 |
| 行数组无该列键 | 返 `None` | `NO_COLUMN` | **禁回退别的列** |
| `aggregate=ROW` 且 `row_key` 未命中 | 返 `None` | `NO_COLUMN` | **禁回退第一行** |
| 值为空串 / 空数组 / 全非数值 | 返 `None` | `EMPTY` | 与「未编制」区分开 |
| DB 查询抛异常 | `logger.warning` 后返 `None` | — | fail-soft 但**必须留日志**（R1.8） |
| `PREV()` 任何情形 | 返 `None` | — | 无 year 维度，fail-closed（R4.2） |

## Testing Strategy

1. **单测（替身）** —— 六态各一例 + Property 7/8 反向自检 + 三种聚合语义 + 标量态
2. **连库守卫** —— Property 1（`cells` 零命中）+ Property 3（映射完备性，从 JSON 实时解析）
3. **源码守卫** —— Property 2/4/5/9/10/11/12/14/15，全部先 `strip_comments()` 并配反向自检
4. **变异检验** —— 逐条施加：改回读 `cells` / 去掉 JOIN / 去掉 ORDER BY / 让 `PREV` 回退本年 /
   行匹配回退第一行 / 二元组键 / 映射到派生列 / 去掉 logger.warning / 往待对齐清单加条目。
   **按失败测试名集合做差集判定**（baseline 本身有红时看 exit code 会误判）
5. **真实库验收** —— 诊断脚本对真实项目跑 D 循环 12 条，输出六态分布与金额；
   验收判据是「至少有 1 条 `HIT` 且金额与 `checklist_responses` 里的值逐分相等」

### 判据边界

- **不用 fixture 冒充真实数据** —— 若真实库某循环全部 `NO_ITEM`（底稿未编制），
  诊断脚本如实报告（R7.5）
- **`--check` 归零 ≠ 链路是通的** —— 验收必须是「真实库取到数」，这正是本轮踩的坑
- **已交付的 Wave 1 守卫（`test_prefill_wp_prev_resolution.py`）的 4 条 probe 实参是
  不存在的锚点** —— Task 2 反转时必须同步换成上表的真实三元组，否则反转后仍恒 None
  而看不出是接线问题还是实参问题
