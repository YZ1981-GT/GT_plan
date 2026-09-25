# Design Document

## Overview

把双向回写从「一底稿一份 900 行 provider」改成「框架层单一引擎 + 循环层 entry 声明 +
sheet 层薄声明」，并以 D1 全覆盖验证该结构。设计的全部参数都从**七家 provider 实测共性**
反推，不是先画抽象再套现实。

**本设计的成功先例**：`phase5_transposed_sheet.py`（500 行通用引擎）+ `transposed_registry.py`
（32 行注册表）已经把 D4-29 从"几何常量与算法糅死的单例"泛化成"引擎 + 两份 spec"，且
D4-29 产物逐字节零回归。本 spec 是同一手法在**行表**这个更大类上的复用。

## Architecture

```
┌─ 第 3 层 框架（全平台唯一实现，零 wp_code 分支）──────────────────────────┐
│  phase5_row_table_sheet.py     RowTableSheetSpec + 投影/合并/契约装配引擎   │
│  phase5_transposed_sheet.py    TransposedSheetSpec（已存在，不改）          │
│  store_item_registry.py        StoreItemSpec 四形态 + O(1) 分派注册表       │
│  sheet_geometry.py             _snake / _col_index / 账龄展开（收四份复制）  │
│  ── 已存在、只去掉 provider 硬编码，不改造 ──                               │
│  projection_first_publication._align_specs_to_sibling_tables(provider=…)    │
│  projection_first_publication._static_region_bindings(provider=…)           │
│  excel_materialize / excel_extract / merge / oo_to_html（删 elif 链）        │
└────────────────────────────────────────────────────────────────────────────┘
                    ▲ 只被调用，不反向依赖
┌─ 第 2 层 循环（每循环一个 entry，互不可见）────────────────────────────────┐
│  phase5_d1_notes_receivable.py   ENTRY_ID / 模板路径 / sheet 清单 / 开关     │
│  pilot_d2_large_json.py          （下一 spec 扩；本 spec 只保证零回归）      │
│  phase5_d4_revenue_detail.py     （26 per-sheet 模块保留原样，只过零回归门） │
└────────────────────────────────────────────────────────────────────────────┘
                    ▲
┌─ 第 1 层 sheet 声明（每张一个薄模块，只有数据没有算法）────────────────────┐
│  phase5_d1_02_category.py  phase5_d1_04_bad_debt.py  phase5_d1_08_…py  …   │
│  形如：SPEC_D102 = RowTableSheetSpec(managed_sheet='原值明细表（按类别）D1-2', │
│                                      first_data_row=11, …)                  │
└────────────────────────────────────────────────────────────────────────────┘
```

依赖方向单向向上。第 1 层只 import 第 3 层的 `RowTableSheetSpec` 类型；第 2 层 import 第 1 层
的 SPEC 常量并组装成 `instrumentation_specs()`；第 3 层**不 import 任何第 1/2 层模块**
（这条由需求 7.1 的 AST 卡点守）。

## Components and Interfaces

### RowTableSheetSpec（字段集从七家实测反推）

```python
@dataclass(frozen=True)
class RowTableSheetSpec:
    """一张行表型受管 sheet 的全部几何 + 字段 + store 形态。引擎行为全由本类驱动，无隐藏常量。"""

    # ── 几何（七家 100% 同构的 6 个 + 1 个可选）────────────────────────────
    managed_sheet: str          # Excel 内的 sheet 名（含 wp_code 尾巴，如 '原值明细表（按类别）D1-2'）
    sheet_key: str              # 契约内的 sheet 键（如 'd12-managed'）
    table_key: str              # 契约内的 table 键（如 'category_detail_rows'）
    template_id: str            # _GT_SYNC 的 GT_TEMPLATE_IDS 项
    table_name: str             # Excel Table displayName
    uuid_col: str               # 隐藏身份列
    first_data_row: int
    last_data_row: int          # 模板预画末行（超出按样式克隆扩行）
    footer_row: int             # 合计 footer
    header_row: int | None = None   # D1/D4 有；账龄型在 aging 声明里带

    # ── store ──────────────────────────────────────────────────────────────
    store_item_id: str = ""
    empty_payload: str = "[]"
    row_identity_key: str = "rowId"     # 🔴 必须参数化：D2 披露用 'key' 不是 'rowId'
    store_kind: StoreKind = StoreKind.rows

    # ── 字段（统一 7 元组，裁决 3）──────────────────────────────────────────
    #   (column_key, column, mode, value_type, json_key, header_text, group_header_cell)
    #   group_header_cell 为 "" 表示无分组表头
    field_specs: tuple[tuple[str, str, str, str, str, str, str], ...] = ()

    # ── 公式（裁决：mask 由引擎现算，provider 不手写字面量）──────────────────
    formula_columns: tuple[str, ...] = ()
    formula_templates: Mapping[str, str] = field(default_factory=dict)  # 可选，逐行与模板比对守卫

    # ── 分组（账龄三形态）────────────────────────────────────────────────────
    aging_layout: AgingLayout | None = None     # nested / flat / None

    # ── 错误消息标签（零回归：各家保持既有措辞）────────────────────────────
    error_label: str = ""

    @property
    def formula_mask(self) -> tuple[str, ...]:
        """七家实测形态：全为列向区间。provider 侧的手写 mask 由本属性取代。"""
        return tuple(
            f"{col}{self.first_data_row}:{col}{self.last_data_row}"
            for col in self.formula_columns
        )
```

裁决依据（逐条对应实测）：`formula_mask` 做成 property 而非字段，因为七家**无一例外**都是
`{COL}{FIRST}:{COL}{LAST}`；做成字段会保留"手写 mask 与 formula_columns 不一致"这个漂移面。
逐格 mask（D4-1 的 48 格）不属于行表引擎的表达域 —— 它是审定表形态，由批次 6 的
`AdjudicationSheetSpec` 另行表达（见下文裁决 D3）。

### 账龄三形态参数化（AgingLayout）

实测三种真实形态，必须全部表达且不互相污染：

```python
class AgingLayout(StrEnum):
    nested = "nested"   # D3/D7：{agingPrior: {within1y: …}, agingAudited: {…}}
    flat   = "flat"     # D6：agePrior1y / ageEnd1y 平铺顶层
    # None                D1/D5/D4：无账龄组

@dataclass(frozen=True)
class AgingGroupSpec:
    json_prefix: str            # nested 时的子对象名 / flat 时的键前缀
    group_header_cell: str      # 组标题格（如 'K12'）
    segments: tuple[tuple[str, str], ...]   # (segment_key, leaf_column)
```

引擎按 `aging_layout` 分派两件事，其余完全共用：
1. **字段 key 派生** —— nested 走 `f"{_snake(json_prefix)}_{seg_key.lower()}"`（D2/D3/D7 现状），
   flat 走 `_snake(flat_key)`（D6 现状）。这两种写法现在各自散在四个文件里，收进引擎后
   **只剩一处 if**，且由 D2/D3/D6/D7 四家零回归门钉住。
2. **store 读写路径** —— nested 走 `_resolve_json_path` / `_set_json_path`（点分路径），
   flat 走顶层键直取。这两个 helper 现在也是四份复制，收敛为一份。

`MANAGED_FIELD_SPECS` 的组装（四家逐字相同的那行 `tuple(sorted(...))`）移入引擎：

```python
def managed_field_specs(spec: RowTableSheetSpec) -> tuple[FieldSpec7, ...]:
    """标量字段 + 账龄展开，按列序排序。取代四家各写一遍的 sorted(...) 表达式。"""
    fields = list(spec.field_specs)
    if spec.aging_layout is not None:
        fields.extend(_expand_aging_fields(spec))
    return tuple(sorted(fields, key=lambda row: _col_index(row[1])))
```

### StoreItemSpec 四形态注册表

D4 已在自己身上长出完整的形态分类学（46 item 收敛于 `all_store_item_ids()`），本设计把它
提成框架级：

```python
class StoreKind(StrEnum):
    rows       = "rows"        # JSON 行数组（最常见）
    dict       = "dict"        # 嵌套对象，如 D4-9 {current,prior}+totals / D1-7 {bankRows,commercialRows}
    fixed_text = "fixed_text"  # 纯文本标量，如 D4-5 业务场景 / D1-14 政策 10 项
    dedicated  = "dedicated"   # 走 provider 专用 merge 门面，如 D4-7 products+monthly

@dataclass(frozen=True)
class StoreItemSpec:
    item_id: str
    kind: StoreKind
    default: str                       # per-item 缺省值：rows→'[]' / dict→'{}' / fixed_text→''
    merge_fn: str | None = None        # dedicated 才有；框架按名从循环层 provider 取
```

🔴 **`default` 必须 per-item，不得 blanket `"[]"`** —— 这条有事故背书：dict-store（D4-9 `{}`）
与 singleton（D4-31 `{}`）拿到列表默认 `"[]"` 会在 provider 内抛非 domain `ValueError`，一路
冒泡成 opaque 500 并连累整个 entry 的 store-projection（`store_projection_response.py:207` 注释
记录了这次修复）。引擎沿用 per-item 单源规则。

分派入口（取代 `oo_to_html` 的 9 分支 elif 链 + 9 处 hasattr）：

```python
STORE_MERGE_REGISTRY: Final[Mapping[str, StoreMergePlan]] = {...}   # adapter_id → plan，O(1)

def resolve_store_merge_plan(adapter_id: str) -> StoreMergePlan:
    plan = STORE_MERGE_REGISTRY.get(adapter_id)
    if plan is None:
        raise StoreMergePlanNotRegisteredError(          # 需求 3.4：显式失败不静默跳过
            f"adapter {adapter_id!r} 未注册 store merge plan；已注册："
            f"{sorted(STORE_MERGE_REGISTRY)}"
        )
    return plan
```

## 关键裁决

### 裁决 D1：框架层不感知 wp_code，用 AST 卡点守而非人工纪律

`oo_to_html.py` 现有 **89 处 D4 提及**，是"通用层被特化污染"的活样本。光删一次不够 —— 下一个
接底稿的人会照原样再加一个 elif。因此卡点必须机器化：AST 扫框架层模块的字符串字面量与比较
表达式，命中 `D\d+(-\d+)?` / `d\d\.\w+` 形态即红。白名单只允许两类且须显式登记：注册表模块
本身（它的职责就是持有映射）、错误消息文案（`f"adapter {adapter_id!r} 未注册…"` 这种）。

### 裁决 D2：`_attach_sibling_bindings` 泛化只需去掉一行 import

实测 `phase5_d4_revenue_detail._attach_sibling_bindings`（:2666）已经在调用框架层共享内核
`_align_specs_to_sibling_tables(provider=…)` 与 `_static_region_bindings(provider=…)`，唯一的
D4 特化是 `import app.services.workpaper_sync.phase5_d4_revenue_detail as _provider` 这一行。
⇒ 泛化 = 把 `provider` 提成参数，函数体不动。**不要**重写对齐规则：那条规则（按 managed sheet
归组、同 sheet 双区靠 UUID 列配对、计数守卫数行 table 不数 sheet）是 publish 与 attach 两路径
共享的，重写必然漂移。

### 裁决 D3：审定表不进行表引擎，另立 `AdjudicationSheetSpec`

实测三个循环的审定表形态**互不相同**：

| | 区块 | 行模型 | 行来源 | 存储 |
|---|---|---|---|---|
| D1-1 | 3（gross/bd/net） | 动态票据种类 | D1-2 / D1-4 cross-sheet | per-cell 锚点 |
| D2-1 | 1 | **写死 4 行**（信用风险分类） | D2-2 SUMIF | per-cell 锚点 |
| D4-1 | 2（主营/其他） | 动态行 | TB 派生 + 手工 | 行数组 + per-field 双写 |

共性只有三件：逐格 mask（含小计/合计/差异行）、cross-sheet 派生 + 人工覆盖冲突、期初/期末
双期审定列。差异大于共性 ⇒ 强行塞进 `RowTableSheetSpec` 会让它长出一堆 `if is_adjudication`。
本 spec 的做法：行表引擎只管**明细类**（批次 1~4），审定表在批次 6 用独立 spec 类表达，
共享的是**四态覆盖状态机**（前端 `shared/dynamicAdjudicationRows`）而不是后端投影引擎。

### 裁决 D4：行角色与行来源两维并存，`isFixed` 收敛掉

实测四处同语义多表达（见 requirements 第三节）。统一口径：

```
rowType: 'fixed' | 'dynamic' | 'summary'     行在表结构里的角色
source:  'tb' | 'manual' | 'legacy'          行数据来源
```

`summary` 行**不进 store**（与 D4 现在 `buildSubtotalRow` 走 computed 一致，不是新规则）。
`isFixed` 删除，由 `rowType !== 'dynamic'` 推导。D2 披露的 `kind: category|subtotal|total`
与 `key`（而非 `rowId`）作为行标识**本 spec 不动** —— 披露在范围外，但 `row_identity_key`
已参数化，为它留好了口子。D1-15 的 `autoPulled: boolean` 归一到 `source='tb'`。

### 裁决 D5：灰度开关逐张接入，不做大爆炸

照 D4 实测的 18 个 `_INCLUDE_*: Final[bool]` 开关模式（现全为 True）。每张新 sheet =
一个 `phase5_d1_xx_*.py` 声明 + 一个开关 + 一条判据。好处有事故背书：D4-35 曾"由并发会话
加入契约 sheets（8 张）但漏了 instrumentation spec"，导致 specs(7) 与 sheets(8) 不对齐、
**整个 entry attach fail-closed**。开关 + 对齐计数守卫能让这类不对齐在接入时就红，而不是
上线后整册 500。

### 裁决 D6：零回归门用 digest，但 materialize 段必须真跑

`build_contract_payload` / `build_store_projection` / `instrumentation_spec(s)` 三者取
canonical JSON sha256（8 contract × 3 = 24 个 digest）。但**digest 不能替代 materialize 真跑**：
D4 spec 的教训是判据只覆盖 adapter 两个方法，而生产路径在它们之后还有
`verify_unmanaged_regions` ⇒「判据绿而生产 500」。所以门里必须有一条穿过 verify 的真
materialize（需求 9.4）。

## D1 接入设计

### 批次与依赖

| 批次 | sheet | 引擎能力需求 | 新增风险 |
|---|---|---|---|
| 1 | D1-2、D1-4（三区） | 行表引擎 + 同 sheet 多区 | D1 首次多受管 sheet；D1-4 首次三区 |
| 2 | D1-8、D1-16（各双区）、D1-5 | 同上 | 无新增 |
| 3 | D1-9、D1-10、D1-11、D1-12、D1-15 | 行表 + 标量伴生（D1-10 的 3 个 recon 标量）| D1-15 派生列是乘法（`余额×损失率`）|
| 4 | D1-7（嵌套 dict）、D1-14（纯标量）、D1-13（标量 + 2 行表）| `StoreKind.dict` / `fixed_text` | D1-7 是一个 item 装两数组 |
| 5 | D1-6（行表 + 真二维矩阵）| 需评估 `TransposedSheetSpec` 能否表达 `cells[4][3]` | 若不能表达则按需求 5.6 登记 |
| 6 | D1-1（审定表）| `AdjudicationSheetSpec` + 四态状态机 + 存量迁移 | 最高，单独验收 |

批次 1 的 D1-2 排第一有具体理由：它与已接的 D1-3 在**同一册**模板（实测 21 张 sheet，D1-2 是
第 6 张、D1-3 是第 7 张）、同一套双期审定列、同一个宿主组件。接通它即证明"一个 entry 多受管
sheet"在 D1 上成立，且失败面最小（若挂，挂的是 D1-2 那一个 binding，且开关可立即关掉）。

### 同 sheet 多区的白拿能力

D1-4（三区）/ D1-8（双区）/ D1-16（双区）会走上 D4-1 踩过并已修的那条缺陷链。三层修复现已齐备：

1. `excel_materialize._shift_sibling_table_refs` —— 同 sheet 兄弟 Table ref 随插行位移
2. `_refresh_gt_sync_runtime_binding` —— 同 sheet 全部 template_id 的 footer 坐标重冻结
3. `excel_row_shift.CompositeRowShift` + `adapters/excel._sheet_cumulative_shift` —— 多趟累积插行
   的归一化（含 `normalise_propagated_part` 的链尾优先逆替换）

而 `test_sibling_table_ref_row_shift.py` 的判据 6 是**参数化且清单动态算**的
（`_multi_region_sheets()` 从 `instrumentation_specs()` 推，实测 30 受管 sheet 中 5 张多区），
所以 D1 这三张接进来会被自动覆盖，无需新写位移判据。⚠️ 但该判据当前只从 **D4** provider 取
清单，需扩成按 provider 参数化 —— 这是批次 1 的一项具体任务。

### D1-1 迁移（批次 6）

```
现状：D1-adj-{section}-{slug}-{field}  一格一条 checklist 记录
      section ∈ {gross, bd, net}；slug 来自 D1-2 的票据种类（bank/commercial/c-{uuid}）
      field ∈ {prior-unadj, prior-aje, prior-rje, current-unadj, current-aje, current-rje, reason}
      派生列（审定/净值/合计）一律现算不落库

目标：行数组 + per-field 双读单写，四态覆盖状态机接管 cross-sheet 冲突
```

迁移纪律照 D4 已验证的做法：**双读单写**（新写行数组，读时行对象优先、缺则回落 per-cell 锚点），
回滚只需改读侧优先级、不必回填数据。物理删除旧键归后续 spec。

必须修的现状行为：`const g = fromCat ?? readD1AnchorAmounts(...)` —— cross-sheet 有值就**无条件
盖掉**手工锚点，手工值变不可达且无任何提示。这是静默丢数据，与 D4-1 修前同型。迁移后走
`resolveCellState(stored, snap, derived)` 四态，S2/S4 亮「已人工覆盖」并提供「恢复取数」。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 注册表未命中 adapter_id | 抛 `StoreMergePlanNotRegisteredError`（含已注册清单）| 需求 3.4；静默跳过是 D4-35/D4-13 两 bug 的根因形态 |
| `RowTableSheetSpec` 字段与契约不一致 | 装配时 fail-closed 抛 `ContractSchemaError` | 现状行为不变 |
| instrumentation specs 数 ≠ 契约 sheets 数 | attach fail-closed + 精确报差集 | D4-35 事故（specs 7 vs sheets 8 打挂整个 entry）|
| store item 缺失/空 | 取 **per-item** default（rows→`[]` / dict→`{}` / fixed_text→`''`）| `store_projection_response.py:207` 的 blanket `"[]"` 事故 |
| 引擎表达不了某形态 | 显式登记 + 原因，**不开框架层特例分支** | 需求 5.6；照 `pilot_h1.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` 范式 |
| domain error 冒泡成 500 | 本 spec 新增路径 SHALL 翻 4xx | D4 遗留项 `excel_extract_identity_carrier_missing` 以 500 返回、前端自动重试 3 次 |

## Data Models

三类数据模型，边界必须分清 —— 混淆它们正是现状「同语义多表达」的来源。

### 1. 声明模型（代码内，不落库）

| 类型 | 层 | 内容 | 生命周期 |
|---|---|---|---|
| `RowTableSheetSpec` | 框架层定义 / sheet 层实例化 | 几何 9 必填 + 1 可选 / store 4 / 字段 7 元组 / 公式 2 / 分组 1 | 进程内常量，随代码发布 |
| `TransposedSheetSpec` | 同上（已存在） | 转置表几何 + 身份 + store 形态 | 同上 |
| `AdjudicationSheetSpec` | 同上（批次 6 新增） | `sections`(1 或 3) + `row_mode`(`fixed_rows`\|`dynamic_identity`) + 逐格 mask | 同上 |
| `StoreItemSpec` | 框架层 | `item_id` / `kind` / per-item `default` / 可选 `merge_fn` | 同上 |

### 2. store 载荷模型（`checklist_responses.remark`，落库）

四形态，由 `StoreKind` 分派，**per-item 缺省值不可 blanket**：

```
rows        JSON 行数组          default '[]'    D1-cust-rows / D1-cat-rows / D2-detail-rows …
dict        嵌套对象             default '{}'    D1-memo-rows {bankRows,commercialRows} / D4-9 {current,prior}
fixed_text  纯文本标量           default ''      D1-14 政策 10 项 / D4-5 业务场景 6 项
dedicated   走 provider 专用门面  同 kind         D4-7 products+monthly
```

### 3. 行模型（store 载荷内的单行，落库）

```
rowId | key       行标识（参数化 row_identity_key —— D2 披露用 key 不是 rowId）
rowType           fixed | dynamic | summary     行在表结构里的角色；summary 不落库
source            tb | manual | legacy          行数据来源
<业务字段>         由 field_specs 的 json_key 决定
derivedSnapshot   HTML-only，四态状态机的第三个量（仅审定表类需要）
```

两维正交不可合并（裁决 D4）。`summary` 行是 computed 不进 store —— 与 D4 现行
`buildSubtotalRow` 一致，不是新规则。

## Correctness Properties

判据面。每条都必须被变异打红，否则重写而非保留（需求 9.1）。

### Property 1: 8 contract 的 24 个 golden digest 在引擎抽取前后逐个不变

**Validates: Requirements 4.1, 4.2**　变异：引擎漏生成一条 mask 区间。

### Property 2: `formula_mask` property 输出 ≡ 七家原手写 mask 字面量

**Validates: Requirements 1.2**　逐元素相等。变异：改 `formula_columns` 顺序。

### Property 3: `managed_field_specs()` 输出 ≡ 四家原 `sorted(...)` 表达式结果

**Validates: Requirements 1.3**　逐元组相等含顺序。变异：账龄段展开顺序错乱。

### Property 4: nested / flat 两种 key 派生各自等于原写法

**Validates: Requirements 1.3**　变异：把 flat 走 nested 派生 ⇒ D6 必红（反证式先写）。

### Property 5: 出/回两方向 store item 集合逐元素相等

**Validates: Requirements 3.3**　变异：注册表漏一个 item。

### Property 6: 注册表未命中时抛显式错误且含已注册清单

**Validates: Requirements 3.4**　变异：改成静默 `return` —— 静默跳过正是 D4-35 恒空 /
D4-13 正文写不进 OO 两个已修 bug 的根因形态。

### Property 7: 注册表查表耗时不随规模上升（O(1) dict）

**Validates: Requirements 3.5, 8.2**　变异：改成线性 `for spec in REGISTRY: if spec.matches()`
—— 那是 `field_by_stable_key` O(n²) 的同款错误。

### Property 8: `attach_sibling_bindings(provider=…)` 对 D4 产出的 binding ≡ 泛化前

**Validates: Requirements 1.5, 2.4**　逐字段相等含顺序。变异：改对齐规则（数 sheet 而非数
行 table）—— publish 与 attach 共享同一内核，重写必漂移。

### Property 9: 框架层 AST 扫零 wp_code / contract_id / adapter_id 分支

**Validates: Requirements 7.1**　现状必红（`oo_to_html` 89 处 D4 提及 + 9 分支 elif）。
变异：在框架层加一个 `if adapter_id == "d1.…"`。

### Property 10: 新声明 spec 未接注册表 ⇒ CI 红并精确报漏项

**Validates: Requirements 7.2**　照 `check_store_item_ids_fully_wired.py` 已验证范式。
变异：加一个 SPEC 不接线。

### Property 11: D1 每批次接完后整册 materialize 200 且 verify 全绿

**Validates: Requirements 5.5**　🔴 判据必须**穿过** `verify_unmanaged_regions` —— D4 spec 的
教训是判据只覆盖 adapter 两方法 ⇒「判据绿而生产 500」。变异：去掉兄弟 Table ref 位移。

### Property 12: D1 多区 sheet 被位移判据参数化清单自动覆盖

**Validates: Requirements 5.4**　`_multi_region_sheets()` 从 `instrumentation_specs()` 动态算。
变异：把清单改回硬编码 D4 ⇒ D1-4/D1-8/D1-16 漏覆盖。

### Property 13: 三端点耗时 ≤ 抽取前 110%

**Validates: Requirements 8.1**　脚本现测不手抄。变异：在引擎热路径加一次整簿 load。

### Property 14: D1-1 迁移后只有 per-cell 旧数据的行读回等值（金额不归零）

**Validates: Requirements 6.1**　🔴 判据须以**真库存量形态**的 payload 驱动，不是合成理想数据。
变异：去掉读侧回落。

### Property 15: 上游变化后纯派生格不得被标成人工覆盖

**Validates: Requirements 6.3**　反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数必须
为 0。变异：用 `stored ≠ derived` 错法判覆盖。

### Property 16: D1-15 `autoPulled` 归一到 `source='tb'` 后语义有定义

**Validates: Requirements 6.5**　现状「上游变了、手工调过的值会怎样」是未定义行为。
变异：保留布尔标记。

## Testing Strategy

**红判据先行。** 批次 0 先取 24 个 golden digest（此时必绿，是**基线**不是判据）+ 打红 P9/P10
（现状框架层有 89 处 D4 提及、注册表尚不存在 ⇒ 必红）。没有这两条红，后面"修好了"与"判据本来
不会红"区分不开。

**禁止两端各自 mock。** D4 spec 的缺陷 A2 正是"两端各自 mock 后全绿而生产坏掉"。本 spec 的
真链判据必须：真 contract + 真 provider + 真 materialize（走 `build_workbook_bytes`）+ 真
extract + 真 merge + 穿过 `verify_unmanaged_regions`。

**纯函数判据覆盖不到时序缺陷。** D4 spec 有 13 条四态纯函数判据全绿而生产行为是坏的（同步器
把显示值当派生值写回 snap ⇒ 覆盖标记自我擦除）。批次 6 的 D1-1 四态必须有一条**跑同步器**的
判据，不能只喂 `resolveCellState` 三个入参。

**零回归分母要诚实。** 前端全量 `vitest run composables/__tests__/` 现有 11 文件 / 56 条既存
失败（L2/L4 披露、K 系附注、G7 列对齐、F3/F5 集成等），与本 spec 改动文件无交集 ⇒ 不计入本
spec 分母，但需在证据里列明归因（照 D4 spec 的处理口径）。

## 不在本 spec 范围

- **D2 接入** → 已立 `d2-sync-coverage-via-row-table-engine`（本 spec 的消费方）。本 spec 只保证
  D2 零改动通过零回归门。⚠️ 该 spec 调研发现一条本 spec 未预料的结构事实：**D2 是三册模板**
  （`D2-1至D2-4` / `D2-5` / `D2-6至D2-13`），而 entry ↔ template blob 是 1:1 且 `_entry_id` 从
  宿主文件派生 + 碰撞检查 ⇒ 一宿主恰一 entry ⇒ D2 只能覆盖第一册，后两册需新建宿主另立。
  这与 D1（单册 21 sheet）/ D4（单册 46 sheet）不同，本 spec 的「一循环一 entry」裁决对 D2
  需读作「一册一 entry」。
- **D2-7 两套并存的清理** → 归 D2 spec。⚠️ 该 spec 已查明：`useD2VoucherCheck`（旧套）
  **全仓零消费方**（死模块 310 行），前端实际挂载的是 `Enhanced`；真库旧键
  `D2-voucher-params`(1 行 87B) / `D2-voucher-samples`(1 行 332B) 内容为**空骨架/默认值**，
  新套 `D2-vc-current-rows`/`-post-rows` **全库 0 行** ⇒ 裁决为「删代码不删数据」。
- **`useD2Adjudication:182-188` 死降级路径删除**（逐行读 `D2-detail-{i}-{field}`，零写入方）
  → 归 D2 spec 任务 15。
- **性能优化**（三端点耗时根因）。归 `oo-html-writeback-performance` /
  `workpaper-sync-materialize-large-table-performance`。
- **D4 的 26 个 per-sheet 模块迁到新 spec 形态**。本 spec 只要求它们过零回归门。
- **附注披露接入**（D1 10 行接口 / D2 12 行接口，`rowType` vs `kind`、`rowId` vs `key` 不同构）。
- **per-cell 旧键物理删除**（D1-1 迁移只做双读单写）。
- **`excel_extract_identity_carrier_missing` 的 500→4xx 错误分类**（D4 遗留项，属 router 范围）。

## 顺带发现的文档过时项（不改原文，只登记指针）

1. `d4-html-to-oo-store-contract-alignment/tasks.md` 任务 18 的 🔴「`merge._protection` 修法待
   用户拍板，本轮未改」**部分过时** —— 工作树里已改为格级判定（`cell_in_ranges` +
   `_mask_spans_data_column`），判据 `test_masked_cell_protection_is_cell_level.py` 实跑 33 passed。
   ⚠️ 但 **HEAD 里仍是只比列的旧实现**（`git show HEAD:…/merge.py` 实测不含
   `_mask_spans_data_column`），判据文件仍 `??` 未跟踪 ⇒ 该修复**尚未入库**，本 spec 的批次 6
   依赖它先落 commit（需求 10）。
2. `phase5_d4_revenue_detail.instrumentation_specs()` 中 D4-1 那条注释「默认不接 …… 2 spec 会
   打挂整个 entry 的 publish」**已过时** —— `_INCLUDE_D41_ADJUDICATION_INSTRUMENTATION` 实测为
   `True`，同 sheet 双区注入内核已由 Task 1 落地。
