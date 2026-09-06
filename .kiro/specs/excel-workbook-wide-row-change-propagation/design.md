# Design —— 工作簿级行变更传播

## Overview

**把「行变更」的作用域从一张 sheet 提升到整个工作簿。**

现有 `RowShiftPlan` 描述的是「受管 sheet 的第 N 行插入 count 行」。它对跨 sheet 引用的处理是
**逐字不动** —— 那是一个正确但不完整的选择：正确在于不把引用改坏（表名不是坐标、别的 sheet 的
行号不该跟本 sheet 动），不完整在于**引用指向的那笔数据确实被推走了**，引用不跟着走就指向错行。

本 spec 引入 `WorkbookRowChangePlan`：受管 sheet 的行变更 + 全工作簿引用侧的**传播条目清单**，
两者在同一份冻结声明里。传播条目由计划构造时算出，验证阶段用**声明值**归一化 —— 不允许验证器
用实测差异自证合法。

同时补上删行：projection 行集少于物理行时收缩。删行的传播方向与插行相反，且多一类必须处理的
情形 —— **悬空引用**（指向被删行的引用）。

### 关键判断：为什么"逐字不动"不是 bug 而是不完整

`excel_row_shift._rewrite_formula_refs` 当前对带 sheet 前缀的引用一律不动，这挡住了四类误命中
（实测：188 份模板 81,955 处引用、其中 16,027 处表名形如 A1 引用）。本 spec **不推翻它**，而是
在它之上加一层「显式声明要传播哪个 sheet 的哪段行」的能力：

```
默认（未声明传播）→ 跨 sheet 引用逐字不动     ← 现状，Requirement 7.4 锁死
显式声明传播      → 只对声明的那个 sheet 传播  ← 本 spec 新增
```

这样传播是**加法**而不是行为翻转，未声明时零回归。

## Architecture

### 传播链

```
projection 行集 vs 物理行集
        │
        ▼
plan_workbook_row_change(contract, region, observed)   纯函数、零写入
        │
        ├─ 受管 sheet 的 RowChange（insert | delete）
        │
        └─ 扫全工作簿，找出所有指向受管 sheet 的引用载体
                ├─ 引用侧 sheet 的 <f> 文本
                ├─ 引用侧 sheet 的 sqref / ref 属性
                ├─ xl/workbook.xml 的 definedNames
                ├─ 3D / 外部工作簿引用   → 登记不传播（计数）
                └─ 图表 / 数据透视        → 登记不传播（计数）
        │
        ▼
WorkbookRowChangePlan（冻结：受管变更 + 传播条目 + 未传播登记）
        │
        ▼
apply_workbook_row_change(zf_entries, plan)            纯函数
        ├─ 受管 sheet：复用 shift_sheet_rows（insert）/ 新增 shrink_sheet_rows（delete）
        └─ 每个传播条目：定点改写引用行号
        │
        ▼
verify（用 plan 的声明值归一化，实测≠声明即漂移）
```

### 受管 sheet 的定位

传播的前提是知道「哪张 sheet 是受管的」。来源是契约的 `ManagedRegion.sheet_name` +
`sheet_part`。工作簿内 sheet 名 → part 的映射必须走
`app.services.excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part`
—— 手搓正则对含中文括号、属性顺序不定的模板会失败（B60/H1/G7 三个模板实测全部失败）。

### 悬空引用的处理位置

悬空引用只在 `delete` 时出现，且必须在**计划阶段**就发现，不能等到写盘时才报。计划构造时若
发现悬空引用且契约未声明允许，直接抛 `DanglingReferenceError` 并带上完整清单 —— 于是
「这次删行会打断哪些取数」在动手之前就是已知的。

## Components and Interfaces

```python
# backend/app/services/workpaper_sync/excel_workbook_row_change.py（新建）

class WorkbookRowChangeError(SyncDomainError): ...
class RowChangeKindError(WorkbookRowChangeError): ...          # kind 非 insert/delete
class RowChangeOutOfRegionError(WorkbookRowChangeError): ...    # 删除越过受管区
class DanglingReferenceError(WorkbookRowChangeError): ...       # 悬空引用且契约未允许
class MissingRowIdentityError(WorkbookRowChangeError): ...      # 删行但无稳定业务键
class PropagationDriftError(WorkbookRowChangeError): ...        # 实测传播 ≠ 声明
class UnpropagatedCarrierError(WorkbookRowChangeError): ...     # 出现未登记的引用载体

class RowChangeKind(str, Enum):
    INSERT = "insert"
    DELETE = "delete"

@dataclass(frozen=True)
class PropagationEntry:
    """一处引用侧改写的冻结声明。"""
    #: 载体形态。**Wave 0 Gate 2 实测后的清单** —— `sqref` / `merge` / `hyperlink_ref`
    #: 不在内：那三类的 OOXML schema 类型是 ST_Sqref / ST_Ref，表达不了 sheet 前缀，
    #: 全库 351 份实测 cross = 0/440、0/1223、0/37456、0/3950。
    #:   "formula"              —— 引用侧 sheet 的 <f> 文本
    #:   "hyperlink_location"   —— <hyperlink @location>（实测 3,138 条工作簿内跨 sheet）
    #:   "data_validation"      —— <dataValidation> 的 <formula1>/<formula2>（实测 8 条）
    #:   "conditional_format"   —— <conditionalFormatting> 的 <formula>（实测 6 条）
    #:   "defined_name"         —— xl/workbook.xml 的 <definedName>（实测 5,002 条，五分类见 Gate 2）
    carrier: str
    part: str           # zip part（definedNames 时是 xl/workbook.xml）
    locator: str        # 载体内定位（单元格坐标 / 定义名 name / 属性所在元素序号）
    ref_before: str     # 改前引用文本，如 "'审定表K11-1'!F20"
    ref_after: str      # 改后引用文本，如 "'审定表K11-1'!F21"
    row_before: int
    row_after: int

@dataclass(frozen=True)
class UnpropagatedCarrier:
    """登记但不传播的载体 —— 必须显式计数，不得静默跳过。"""
    #: "three_d_reference" | "external_workbook" | "chart" | "pivot"
    #: | "target_not_in_workbook"（Gate 2 实测：definedNames 1,991 条 + hyperlink@location 321 条）
    reason: str
    part: str
    detail: str
    count: int

@dataclass(frozen=True)
class WorkbookRowChangePlan:
    kind: RowChangeKind
    managed_sheet_name: str
    managed_sheet_part: str
    at: int                                  # insert: 第一个新行；delete: 第一个被删行
    count: int
    style_from: int | None                   # 仅 insert
    region_first_row: int
    region_last_row: int
    deleted_row_keys: tuple[str, ...]        # 仅 delete，Requirement 3.7
    #: 受管区内被引用侧引用到的行 —— **删不了的行**（Wave 0 Gate 4 裁决 / AC 3.8）。
    #: K11 实测 19/19 全被引用 ⇒ 若只有 fail-closed 抛错，删行表现为「永远失败」；
    #: 把它前置成一份声明，HTML 侧才能在**发起删行之前**把这些行标成锁定。
    undeletable_rows: tuple[int, ...]
    propagations: tuple[PropagationEntry, ...]
    unpropagated: tuple[UnpropagatedCarrier, ...]

    def shift(self, row: int) -> int: ...    # 声明值映射（insert +count / delete -count）
    def unshift(self, row: int) -> int: ...  # verifier 归一化用
    def as_dict(self) -> dict[str, Any]: ...

@dataclass(frozen=True)
class PropagationReport:
    """计数器与 `PropagationEntry.carrier` 的取值一一对应（Gate 2 实测后的清单）。

    刻意**没有** `sqrefs_changed` / `merges_changed` —— 那两类结构性不可能带跨 sheet
    引用，留一个恒为 0 的计数器等于给「空集上恒真」留位置。
    """
    formulas_changed: int
    hyperlink_locations_changed: int
    data_validations_changed: int
    conditional_formats_changed: int
    defined_names_changed: int
    unpropagated_total: int
    dangling: tuple[str, ...]

def plan_workbook_row_change(...) -> WorkbookRowChangePlan | None
def apply_workbook_row_change(
    entries: Mapping[str, bytes], *, plan: WorkbookRowChangePlan
) -> tuple[dict[str, bytes], PropagationReport]
def shrink_sheet_rows(sheet_xml: str, *, plan: WorkbookRowChangePlan) -> tuple[str, ShiftReport]
def scan_reference_carriers(
    entries: Mapping[str, bytes], *, target_sheet: str
) -> tuple[tuple[PropagationEntry, ...], tuple[UnpropagatedCarrier, ...]]
def assert_single_a1_rewrite_entrypoint() -> None   # Requirement 7.3
```

`excel_row_shift._rewrite_formula_refs` 新增一个参数承接传播，**不新造 A1 改写入口**：

```python
def _rewrite_formula_refs(
    text: str,
    *,
    remap: Callable[[int], int],
    current_sheet: str | None = None,
    propagate_sheets: frozenset[str] = frozenset(),   # 🆕 声明要传播的 sheet 名集合
    ...
)
```

`propagate_sheets` 为空（默认）时行为与现状**逐字相同** —— Requirement 7.4 的零回归靠这个默认值。

## Data Models

本 spec **不新增数据库迁移**。传播计划是进程内的冻结声明，随 `ContentCommitPlan` 一并流转；
被删行的业务键（`deleted_row_keys`）落在既有 operation timeline 的载荷里，用既有 append-only
事件承载，不新造表。

`deleted_row_keys` 的取值来源优先级：

1. `ExcelIdentityBinding.uuid_column` 指向的 row_uuid（首选，全局唯一）
2. 契约声明的稳定序号列
3. 两者都无 → 抛 `MissingRowIdentityError`，拒绝删行（Requirement 3.7）

## Error Handling

| 异常 | error_code | 触发 | 为什么不能降级 |
|---|---|---|---|
| `RowChangeKindError` | `workbook_row_change_kind_invalid` | `kind` 非 insert/delete，或 `count<=0` | 零变更必须是 `plan is None`；`count=0` 会让「没改」与「改过」混为一谈 |
| `RowChangeOutOfRegionError` | `workbook_row_change_out_of_region` | 删除区间越过受管区 | 越界删行会删掉未管理区的行，那是 projection 无权处置的数据 |
| `DanglingReferenceError` | `workbook_row_change_dangling_reference` | 有引用指向被删行且契约未声明允许 | 静默改写会让引用指向别的数据；写 `#REF!` 会打断取数链。两者都必须由人裁决 |
| `MissingRowIdentityError` | `workbook_row_change_missing_row_identity` | 删行但无稳定业务键 | 删除是不可逆的数据丢失，无留痕不得执行 |
| `PropagationDriftError` | `workbook_row_change_propagation_drift` | 实测传播 ≠ 声明 | 用实测反推声明 = 让被检查对象自证合法 |
| `UnpropagatedCarrierError` | `workbook_row_change_unpropagated_carrier` | 出现未在登记清单里的引用载体 | 未登记载体 = 有一类引用被静默漏改；宁可打红也不能放过 |

🔴 **禁止 fail-open。** 传播失败一律抛错并放弃整次写入（临时文件 + `os.replace`，原文件完好）。
不得「传播不了就当没有传播」—— 那正是本 spec 要消除的静默错行。

## Testing Strategy

四层，每层能独立打红：

1. **纯函数层**：`plan_workbook_row_change` / `shrink_sheet_rows` / `scan_reference_carriers`
   零磁盘零 DB，秒级。
2. **真实模板层**：判据全部在**含跨 sheet 引用的真实模板**上取证。**Wave 0 Gate 1 裁决后
   载体分两级**：
   - **首要载体 = D2**（`D/D2-1至D2-4 应收账款….xlsx`，受管 sheet `明细表D2-2` anchor A11，
     被 4 张 sheet 的 **52 处**公式引用，被引用行 13 / 25 / 26）—— 它是今天**唯一**既有已审核
     契约、又有真实跨 sheet 引用的 entry，即唯一可端到端执行的样本。
   - **结构载体 = K11**（受管 sheet `审定表K11-1` 被 2 张 sheet 的 **114 处**引用，行号 7~25
     落在受管区 `A7:N25` 内，19/19 全被引用）—— 它**没有** per-entry 契约，是规模与
     100% 阻断形态的结构样本，不是可执行样本。
   每条判据必须断言引用处数 > 0，防空集恒真。
3. **零回归层**：`propagate_sheets` 为空时，`_rewrite_formula_refs` 对全库跨 sheet 引用的
   输出与现状逐字相同。**这一层必须先绿**再做传播接线。
4. **变异层**：每条结构性判据改一字，四态判定。变异用例须让被检验机制成为唯一保护 ——
   前置 spec 实测过一次反例：`'明细表K11-2'!F29` 做变异用例不敏感（行号 11 < insert_at
   位移是空操作，且 `!` 左边界是第二道防线），换成行号落在插入点之后的用例才敏感。

### 分母断言（Wave 0 实测复算值 · 2026-09-04）

🔴 **下表取代 requirements.md Introduction 里的原登记值。** 原登记的 8 个数字里
**4 个复算不上**（详见 Requirement 6 的口径小节与
`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` §9 的 C 行）。
判据一律用下表，且必须能被 Task 24 的生成器（G1）复算。

🔴 **本表是分母的单一真源，与清册 JSON 及现算三向锁死。** `key` 列是机器键：
`backend/scripts/gen/generate_row_change_reachability.py` 按同名键产出，
`test_workbook_row_change_reachability.py` **解析本表**逐键比对（不把数字硬编码进守卫）。
⇒ 改本表不改代码、或改代码不改本表，都会打红。

| key | 分母 | 值 | 定义（判据必须按此口径复算） |
|---|---|---:|---|
| `xlsx_total` | xlsx 模板总数 | **351** | `backend/wp_templates/**/*.xlsx`，排除 `~$` 锁文件 |
| `templates_with_cross_sheet` | 含跨 sheet 引用的模板 | **182** | 存在指向**另一个名字**的限定引用（排除自限定、3D、外部工作簿）。**不要求目标 sheet 真实存在** |
| `cross_sheet_sites` | 跨 sheet 引用处数 | **144154** | 每个「限定前缀 + 目标 token」算一处；分词器同生产 |
| `cross_sheet_formulas` | 含跨 sheet 引用的 `<f>` 数 | **72825** | 同一 `<f>` 内多处引用只算一条 |
| `templates_with_resolvable_cross_sheet` | └ 其中目标 sheet **真实存在**的模板 | **174** | 传播/可达性的口径 |
| `resolvable_cross_sheet_sites` | └ 其中目标真实存在的引用处数 | **140726** | 只有这些能成为传播目标 |
| `resolvable_cross_sheet_formulas` | └ 其中目标真实存在的 `<f>` 数 | **70117** | |
| `unresolvable_cross_sheet_sites` | 指向**本工作簿里不存在**的 sheet 的引用处数 | **3428** | = 144154 − 140726。权威模板里**已坏**的引用，登记不传播 |
| `templates_with_unresolvable_targets` | 含上述坏引用的模板 | **18** | |
| `sheet_name_looks_like_a1_sites` | 表名含 A1 形态子串的引用处数 | **18491** | 误命中类 1 的实测规模。按**全部限定引用**计（不过滤目标存在性）—— 该防护对目标是否存在一视同仁 |
| `external_sites` | 外部工作簿引用处数 | **2908** | `[n]Sheet!A1`；登记不传播 |
| `three_d_sites` | 3D 引用处数 | **0** | `Sheet1:Sheet3!A1`；全库空集 ⇒ 判据须用注入变体 |
| `affected_templates` | 受影响模板（被引用 sheet 含动态行占位） | **136** | 占位标记集见下 |
| `delivered_contract_entries` | 有已审核 per-entry 契约的 entry | **4** | `DELIVERED_PER_ENTRY_CONTRACTS` 现读 |
| `d2_managed_sheet_sites` | D2 受管 sheet 被引用处数 | **52** | 首要判据载体 |
| `k11_managed_sheet_sites` | K11 受管 sheet 被引用处数 | **114** | 结构判据载体 |
| `k11_managed_sheet_rows` | K11 受管 sheet 被引用的不同行数 | **19** | 受管区 `A7:N25` 共 19 行 ⇒ 100% 被引用 |
| `extreme_combinations` | 引用处数 > 1,000 的组合 | **10** | 最大 **63240**（`C24` 的 `2025假期清单`） |
| `extreme_max_sites` | 最极端组合的引用处数 | **63240** | `C/C24 会计分录 - 细节测试.xlsx` 的 `2025假期清单` |
| `defined_name_cross` | definedNames 含 sheet 限定引用 | **5002** | 四分类见下四行，和恰为 5002 |
| `defined_name_builtin_self_scope` | └ 自指的 Print_Area / Print_Titles | **2457** | 传播（打印区域随插行长大） |
| `defined_name_target_not_in_workbook` | └ 目标不在本工作簿（含 builtin） | **2001** | 登记不传播 |
| `defined_name_user_self_scope` | └ 自指的用户定义名 | **292** | 传播 |
| `defined_name_user_cross_sheet` | └ 真跨 sheet 的用户定义名 | **252** | 传播（R4.1 真正的对象） |
| `hyperlink_location_cross` | `hyperlink@location` 含跨 sheet | **3480** | 三分类见下两行 + `same_sheet` 21 |
| `hyperlink_location_in_workbook` | └ 工作簿内跨 sheet | **3138** | 传播 |
| `hyperlink_location_not_in_workbook` | └ 目标不在本工作簿 | **321** | 登记不传播 |
| `dv_formula_cross` | `dataValidation/formula1\|2` 含跨 sheet | **8** | 4 份模板 |
| `cf_formula_cross` | `conditionalFormatting/formula` 含跨 sheet | **6** | 1 份模板 |
| `sqref_ref_cross` | `sqref` / `ref` 四类属性含跨 sheet | **0** | 结构性不可能，判据形态见 AC 4.2 |
| `chart_parts` | `xl/charts/**` 部件 | **8** | 1 份模板；可用真实样本 |
| `pivot_parts` | `xl/pivot*/**` 部件 | **0** | 空集 ⇒ 判据须用注入变体 |
| `max_host_name_collisions` | 契约声明的受管 sheet 名在全库最多出现在几份模板里 | **39** | AC 6.5 的反证：> 1 即按 sheet 名定位宿主必然歧义 |

### D2 首要判据载体的引用形态实测（2026-09-05）

宿主：`backend/wp_templates/D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx`
（🔴 文件名含**两个连续空格**，别按 spec 正文的省略写法拼路径）。受管 sheet `明细表D2-2`，
契约 anchor `A11`。

| 形态 | 处数 | 样本 | 覆盖的 AC |
|---|---:|---|---|
| `$` 绝对行**区间** | **18** | `SUMIF('明细表D2-2'!$AI$13:$AI$25,"单项计提",'明细表D2-2'!$S$13:$S$25)` | AC 2.3 / 2.4 |
| 相对行**单格** | **24** | `'明细表D2-2'!AC26`、`'明细表D2-2'!I26` | AC 2.2 |
| 🔴 `#REF!`（限定前缀后无 A1 坐标） | **10** | `IF(ISERROR(VLOOKUP(A109,'明细表D2-2'!#REF!,2,0)),,…)` | AC 2.6（登记不传播） |

🔴 **三条对判据形态的硬约束**：

1. **两条行锁定分支在 D2 上都有真实样本** —— 绝对行 18 处、相对行 24 处 ⇒ D2 足以承载
   AC 2.2 / 2.3 / 2.4 三条，不必为「相对行」另找载体。
2. **`#REF!` 是必须显式登记的第三态**。`_QUALIFIED_PREFIX_RE` 会命中 `'明细表D2-2'!`，
   但紧随其后的 `#REF!` 不是 A1 坐标 ⇒ `_REF_TOKEN_RE` 返回 `None`。这 10 处是分母
   `unresolvable_cross_sheet_sites`（3,428）在首要载体上的具体实例。扫描器**必须**把
   「前缀命中但取不到坐标」登记为 `UnpropagatedCarrier`，不得静默跳过 —— 静默跳过会让
   「有 10 处引用没被处理」这件事不可见。
3. **引用侧 sheet 名不带引号时前缀正则不命中是正确行为**：实测 52 处**全部带引号**
   （`'明细表D2-2'!`）—— OOXML 对含 `-` 的 sheet 名强制加引号。所以
   `明细表D2-2!B13` 这种写法在真实模板里不存在，不必为它放宽正则（放宽会引入误命中）。

**definedNames 侧**（AC 4.1 在 D2 上的真实样本，两条都指向受管 sheet）：

| name | ref | 插行后 |
|---|---|---|
| `_xlnm.Print_Area` | `'明细表D2-2'!$A$1:$AM$34` | 末行 34 在插入点之下 ⇒ **必须扩张** |
| `_xlnm.Print_Titles` | `'明细表D2-2'!$2:$6` | 裸行区间（无列标），2..6 在插入点之上 ⇒ 不变 |
| `_xlnm._FilterDatabase` | `'明细表D2-2'!$A$1:$AK$31` | 末行 31 在插入点之下 ⇒ **必须扩张** |

`$2:$6` 这种**裸行区间**形态命中的是 `_REF_TOKEN_RE` 的第三个分支 `\$?\d+:\$?\d+`
（无列标）—— 判据必须含这一形态，否则「只测带列标的区间」会漏掉 `Print_Titles` 这一类。

**占位标记集**（决定「136 份受影响」这个分母，判据里必须与此表逐字一致）：

| key | 标记 | 命中 sheet | 命中模板 |
|---|---|---:|---:|
| `ellipsis_single` | `…`（单省略号） | 730 | 163 |
| `ellipsis_double` | `……`（双省略号） | 625 | 140 |
| `xx_placeholder` | `××` / `XX`（连续 2+ 个） | 465 | 150 |
| `self_fill` | `自行` | 56 | 37 |
| `add_row` | `增行` / `加行` | 54 | 16 |
| `item_n` | `项目N`（`项目` + 数字/N） | 40 | 24 |
| `dots_ascii` | `...`（半角三点） | 38 | 28 |
| `insert_row` | `插入行` | 18 | 4 |
| `fillable` | `可填` | 3 | 3 |
| `reserved` | `预留` | 2 | 2 |
| `continued` | `续表` | 1 | 1 |
| `renameable` | 🔴 `可改名` | **0** | **0** |

⚠ `可改名` 在 requirements.md 里被列为占位标记，但**全库 351 份 xlsx 里命中 0 次**
（它只出现在 docx / md 侧）。只用 requirements 列的六个标记算出的受影响模板是
**101 份**，用上表全部标记算出 **136 份** ≈ 原登记的 137。

性能：Requirement 8.5 的实测对象由「9,744 处那份」扩为**实测最坏的 C24（63,240 处）**，
阈值 **2,000 ms**（Gate 3）。

## Correctness Properties

### Property 1: 计划是纯函数且不碰磁盘

`plan_workbook_row_change` 调用前后入参对象逐字不变、无文件被创建/修改、无 DB 连接建立。

**Validates: Requirements 1.3**

### Property 2: kind 与 count 的合法域

`kind` 非 `insert`/`delete` 抛 `RowChangeKindError`；`count <= 0` 同样抛；零变更返回 `None`。

**Validates: Requirements 1.4**

### Property 3: 计划携带受管 sheet 的稳定标识

计划里的 `managed_sheet_part` 与 `managed_sheet_name` 与契约声明一致，且 part 由
`_parse_workbook_xml` + `_normalise_part` 解析而非手搓正则。

**Validates: Requirements 1.5**

### Property 4: 插行时引用侧向下传播

指向受管 sheet 且行号 `>= at` 的引用行号 `+= count`；`< at` 的逐字不变。

**Validates: Requirements 2.1, 2.2**

### Property 5: 绝对行同样传播

`'受管表'!$F$20` 在 `at <= 20` 时变为 `'受管表'!$F$21`，`$` 保留。

**Validates: Requirements 2.3**

### Property 6: 区间引用的首尾各自判定

`'受管表'!F10:F30` 在 `at=20` 时变为 `F10:F31`（首行不动、末行传播）。

**Validates: Requirements 2.4**

### Property 7: 非受管 sheet 的引用逐字不变

同一公式里同时含指向受管 sheet 与指向别的 sheet 的引用时，只有前者变。

**Validates: Requirements 2.5**

### Property 8: 3D 与外部工作簿引用登记不传播

`Sheet1:Sheet3!A20` 与 `[1]Sheet1!A20` 逐字不变，且各自在 `unpropagated` 里有一条计数。

**Validates: Requirements 2.6, 9.4**

### Property 9: K11 的 114 处引用逐处正确

在 K11 受管区插行后，114 处引用逐处比对：行号 `>= at` 的全部 `+count`，其余不变，且总处数仍为 114。

**Validates: Requirements 2.7**

### Property 10: 收缩产出正确的行集

projection 行集少于物理行时产出 `delete` 计划；受管 sheet 内被删区间的行消失、其后行上移 `count`。

**Validates: Requirements 3.1, 3.2**

### Property 11: 删行时引用侧向上传播

指向被删区间之后的引用行号 `-= count`。

**Validates: Requirements 3.3**

### Property 12: 悬空引用 fail-closed

存在指向被删区间之内的引用且契约未声明允许时抛 `DanglingReferenceError`，异常携带完整悬空清单。

**Validates: Requirements 3.4**

### Property 13: 悬空场景在真实模板上被构造出来

在 K11 受管区中间删一行，其被 114 处引用之一命中，Property 12 的判据据此打红。

**Validates: Requirements 3.5**

### Property 14: 删除不越过受管区

`at < region_first_row` 或 `at + count - 1 > region_last_row` 抛 `RowChangeOutOfRegionError`。

**Validates: Requirements 3.6**

### Property 15: 删行必须有稳定业务键

无 row_uuid 也无稳定序号时抛 `MissingRowIdentityError`；有键时 `deleted_row_keys` 非空且与被删行一一对应。

**Validates: Requirements 3.7**

### Property 16: definedNames 传播

`xl/workbook.xml` 的 `definedNames` 里指向受管 sheet 的 `ref` 按同规则传播。

**Validates: Requirements 4.1**

### Property 17: sqref 与 ref 属性不被误传播

`conditionalFormatting@sqref` / `dataValidation@sqref` / `mergeCell@ref` / `hyperlink@ref`
的 OOXML 类型是 `ST_Sqref` / `ST_Ref`，表达不了 sheet 前缀（全库 351 份实测
cross = 0/440、0/1223、0/37456、0/3950）。判据形态因此**反转**：往真实模板里
zip 级注入一个带 sheet 前缀的 `sqref`，传播器必须**不动它**（那不是合法的跨 sheet
引用载体），且该注入必须被 `UnpropagatedCarrierError` 或未登记载体判据打红。

**Validates: Requirements 4.2**

### Property 18: 图表与数据透视登记不处理

`xl/charts/**` 与 `xl/pivotCache/**` 里的引用逐字不变，且在 `unpropagated` 里有计数与理由。
chart 用真实样本（全库 **8** 个部件 / 1 份模板）；pivot 全库 **0** 部件 ⇒ 该分支判据必须用
真实模板 zip 级注入变体，否则在空集上恒真。

**Validates: Requirements 4.3, 9.5**

### Property 19: 载体存在性先实测再定判据形态

4.1/4.2 的判据所用载体在真实模板里的存在性有实测数字；为 0 时用真实模板 zip 级注入变体取证。

**Validates: Requirements 4.4**

### Property 20: 未登记载体打红

引入一个新的引用载体形态而不登记时，`UnpropagatedCarrierError` 打红。

**Validates: Requirements 4.3**

### Property 21: 验证用声明值归一化

未管理区域摘要归一化时读的是 `plan` 的声明传播量；把实测差异塞进去时判据打红。

**Validates: Requirements 5.1, 5.2**

### Property 22: 归一化只动行号

归一化前后 `t` / `s` / `f` / `v` 逐字进入摘要。

**Validates: Requirements 5.3**

### Property 23: 引用侧的额外改动判漂移

引用侧 sheet 除声明的传播条目外任何字节变化都打红。

**Validates: Requirements 5.4**

### Property 24: 可达性清册非空且可复算

137 份受影响模板逐份登记，状态限定三态，`blocked` 有原因，数字与现算一致。

**Validates: Requirements 6.1, 6.2, 6.4**

### Property 25: 极端规模模板单独登记并有性能数据

引用处数 > 1000 的模板（实测至少 2 份：9,744 与 3,137）单独登记，附实测耗时与阈值依据。

**Validates: Requirements 6.3, 8.5**

### Property 26: 前置 spec 的排除条款已撤销

`excel-structural-row-insertion-and-shift-aware-verification` 的 R12.1 与 R12.4 不再写"不做"，
而是注明由本 spec 承接。

**Validates: Requirements 7.1**

### Property 27: A1 改写入口仍然唯一

AST 级判据：`excel_row_shift` 里对 A1 引用做行号改写的函数只有 `_rewrite_formula_refs` 一处，
本 spec 未新造第二个入口。

**Validates: Requirements 7.2, 7.3**

### Property 28: 未声明传播时零回归

`propagate_sheets` 为空时，`_rewrite_formula_refs` 的输出与**冻结基线**逐字相同。

基线 = `backend/tests/workpaper_sync/data/workbook_row_change_zero_regression_baseline.json`
（Wave 0 Task 6 于 2026-09-04 冻结，生成器
`backend/scripts/gen/generate_workbook_row_change_zero_regression_baseline.py`）。
实测分母：**351** 份 xlsx / **126,565** 条公式 / **182** 份含跨 sheet 引用 /
**144,154** 处跨 sheet 引用 / **72,825** 条含跨 sheet 引用的公式 / 3D **0** 处 /
外部工作簿 **2,908** 处。

基线两层，缺一不可：**顺序敏感的逐模板 digest**（`(sheet, 序号, 输入, 输出, 改动数)` 滚动
sha256）+ **八类的完整输入/输出对**。只存聚合计数不够 —— 两处相反的变化会互相抵消，
判据 `test_diff_detects_offsetting_changed_counts` 把这一点实证锁死。

三个情景各自冻结（`insert_ctx` / `insert_no_ctx` / `filldown`），因为 `propagate_sheets`
可能扰动 `_rewrite_formula_refs` 的任一分支；并有判据断言「至少一份模板上三者两两不同」，
否则三组参数没被真正区分。

**Validates: Requirements 7.4**

### Property 39: 基线在上游改动之前冻结，且真挂在被观测对象上

两条各自独立可打红：

1. **时序**：基线的冻结动作只读（不碰 7.5 表里的任何共改文件）⇒ 排在 Task 101 的门之前。
   Requirement 7.4 的参照物「本 spec 前」会随上游改动 `excel_row_shift.py` 而永久消失，
   不先冻结则 7.4 无法证伪。
2. **挂载**：扰动 `_rewrite_formula_refs` 的行为后，三个情景的 digest 必须**各自**变化。
   做法是**进程内 monkeypatch**，不改磁盘上的 `excel_row_shift.py`（它归上游 spec 且正被
   并发会话编辑，变异式改文件再复原有覆盖对方改动的风险）。
   缺这一条，整份基线可能只是在比对两份互相复制来的数字。

**Validates: Requirements 7.7**

### Property 29: 变异四态

每条结构性判据的变异结果归入 RED / GREEN / ANCHOR-MISS / WRONG-TEST，后三态任一非零即不通过。

**Validates: Requirements 8.1, 8.2**

### Property 30: 变异用例的唯一保护性

每条变异用例都验证过「短路被检验机制后确实打红」且「不存在第二道防线也挡住同一用例」。

**Validates: Requirements 8.3**

### Property 31: 传播产物真实可打开

传播后的 xlsx 在真实 Excel/OnlyOffice 里可打开且被传播的公式求值指向正确数据；取不到真实环境时标 UNVERIFIABLE。

**Validates: Requirements 8.4**

### Property 32: hyperlink location 传播

`<hyperlink @location>` 指向受管 sheet 时行号按同规则传播（实测 `cross_sheet_in_workbook`
**3,138** 条）；`target_not_in_workbook`（**321** 条，如 `底稿目录!Print_Area` 指向定义名而非
坐标）登记不传播并计数。判据须分别断言这两个分母 > 0。

**Validates: Requirements 4.5**

### Property 33: dataValidation 与 conditionalFormatting 的 formula 子元素传播

`<dataValidation>` 的 `<formula1>` / `<formula2>`（实测 **8** 条 / 4 份模板）与
`<conditionalFormatting>` 的 `<formula>`（实测 **6** 条 / 1 份模板）里指向受管 sheet 的引用
按同规则传播。

🔴 判据**只能扫子元素内容，不得扫整个元素**：`<dataValidation>` 的 `error=` 属性里
有中文提示文本（实测样本 `请从G7-14名称列表…`），扫整个元素会把提示文本里的
`G7-14` 当成跨 sheet 引用 —— 这个假阳性在 Wave 0 实测中真实发生过一次。

**Validates: Requirements 4.6**

### Property 34: definedNames 按五分类处置且逐类有分母

`definedNames` 的 **5,002** 条 sheet 限定引用按 Gate 2 的五分类处置，且判据**逐类**断言分母：
`builtin_self_scope` **2,457**（传播）/ `target_not_in_workbook` **1,991**（登记不传播）/
`user_self_scope` **292**（传播）/ `user_cross_sheet` **252**（传播）/ `builtin_other_sheet`
**10**（登记）。只断言总数 5,002 不算判据 —— 五类的处置不同，混在一起会让某一类被静默漏改。

**Validates: Requirements 4.7**

### Property 35: 受管区内被引用行标记为不可删

`delete` 计划的 `undeletable_rows` 恰为「受管区内且被引用侧引用到」的行集合。
K11 上实测应为受管区全部 19 行（100% 阻断）；D2 上应为 `{13, 25, 26}` 三行、其余可删。
两侧都必须断言：不可删行数 > 0（防空集恒真）且 ≠ 受管区行数（防恒等于全区）。

**Validates: Requirements 3.8**

### Property 36: 宿主模板不按 sheet 名定位

判据禁止用「sheet 名 → 模板」查找宿主。实测 `附注披露信息（国企）` 在 **39 份**模板里都存在，
且同名 sheet 在不同模板里被引用情况完全不同（G7 宿主 0 处，`L/L5 长期应付款.xlsx` 有 5 个
被引用行）⇒ 按名定位会取到错的宿主。宿主必须由 entry → representation → 模板绑定确定。

**Validates: Requirements 6.5**

### Property 37: 新插入行的跨 sheet 相对引用随行平移

`translate_formula_rows(text, from_row=25, to_row=26)` 对 `='明细表K11-2'!F29` 输出
`F30`（相对行平移）、对 `='明细表K11-2'!F$29` 输出 `F$29`（绝对行冻结）、对 3D 与外部
工作簿引用逐字不变。

🔴 判据必须含**混合形态** `='明细表K11-2'!F29+G25` → `='明细表K11-2'!F30+G26`：
Wave 0 实测的现状输出是 `='明细表K11-2'!F29+G26` —— 同一条公式内裸引用平移了、跨 sheet
引用没平移，两个引用的行语义不一致。单独测两类引用发现不了这个形态。

判据还须断言 `translate_formula_rows` 的 docstring 不再声称「相对引用只在本 sheet 内平移」
（AC 10.6）—— 那句与 Excel 语义相反，留着会让下一个人按错的描述写判据。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.6**

### Property 38: 两个传播方向的判据各自独立

「引用侧 → 受管 sheet」（Requirement 2）与「受管 sheet 新行 → 别的 sheet」（Requirement 10）
必须有各自独立能打红的判据：短路任一方向，只有对应那组判据变红，另一组保持绿。
合在一条判据里会让其中一个方向从未被单独执行过。

**Validates: Requirements 10.7, 10.5, 9.0**

## 明确拒绝的方案

1. **推翻「跨 sheet 引用逐字不动」的默认行为。** 那会让 81,955 处引用的行为一次性翻转，
   零回归无从证明。改为加法：默认不动，显式声明才传播。

2. **另造一个 A1 改写入口。** 现有 `_rewrite_formula_refs` 已处理四类误命中（表名当坐标、
   跨 sheet 目标格误位移、`LOG10` 类函数名、字符串字面量）。另造入口必然重复这四类处理，
   而重复的那份迟早漏一类。

3. **按 diff 事后推断传播量。** 等于让被检查对象自证合法。传播量必须是计划时的声明值。

4. **悬空引用静默写 `#REF!`。** `#REF!` 会打断取数链且在报表上显示为错误值；静默改成别的
   行号更糟。必须 fail-closed 交人裁决。

5. **删行不要业务键。** 删除是不可逆数据丢失，无留痕不得执行。

6. **用 openpyxl 或 Excel COM 做传播。** openpyxl 全量重写实测毁坏（K11：zip 部件 37→19、
   共享公式主格 12→0、非空缓存值 716→28、中文表名写成 `&#23457;` 数字实体）；COM 依赖桌面
   Excel，不能在服务端跑。

7. **只做插行传播、删行留待以后。** 删行的传播器与插行是同一份代码（方向相反），拆开会写两遍。
   且 HTML 侧删行是审计师的常规动作，缺它等于双向回写只有一半。

8. **把图表/数据透视的引用一起做。** 它们的引用语法与 sheet 内引用不同（`c:f` 元素、
   pivotCache 的 `cacheField`），且实测存在性未知。先登记计数，规模明确后另起任务。

9. **跨工作簿引用也传播。** 需要解析外部链接目标文件，而目标不在本系统管辖内。登记计数。

10. **行移动（reorder）一并做。** reorder = delete + insert 的组合，但留痕语义不同
    （数据没丢，只是换了位置），判据形态也不同。单独立任务。

11. **传播失败时降级为「不传播」。** 那正是本 spec 要消除的静默错行。必须整次写入放弃。

12. **手搓正则解析 sheet 名 → part 映射。** 实测对 B60/H1/G7 三个模板全部失败（sheet 名含
    中文括号、属性顺序不保证）。必须用 `_parse_workbook_xml` + `_normalise_part`。

## Open Gates（Wave 0 已裁决 · 2026-09-04）

四个 Gate 全部**实测裁决完毕**。扫描口径复用生产分词器
（`excel_row_shift` 的 `_QUALIFIED_PREFIX_RE` / `_REF_TOKEN_RE` / `_STRING_LITERAL_RE` /
`_left_boundary_ok` / `_BARE_TOKEN_RE`）与 `excel_structure_fingerprint._parse_workbook_xml`
+ `_normalise_part`，**未手搓正则**。分母：`backend/wp_templates/**/*.xlsx` 实测 **351 份**。

### Gate 1：受管 sheet 的判定来源 —— 裁决为「一律登记 `blocked`，禁止启发式推断」

实测三条事实：

| 事实 | 值 | 取证 |
|---|---|---|
| `DELIVERED_PER_ENTRY_CONTRACTS` 已审核契约登记行 | **4** | `adapters/registry.py` 现读：b60 / d2 / g7 / h1 |
| 全库 xlsx 里含 Excel Table 的模板 | 🔴 **1 / 351** | 唯一一个是 `C/C24 会计分录 - 细节测试.xlsx` 的 `_2025__2`，与受管无关 |
| 每份受影响模板中「含占位标记的 sheet 张数」 | 中位数 **4**，最多 **18** | 启发式推断的歧义度 |

**这三条合起来决定了裁决**：`resolve_managed_region` 的唯一区域边界锚点是
**Excel Table displayName**（`excel_extract.resolve_managed_region`：0 个命中抛
`IdentityCarrierMissingError`，>1 抛 `ManagedRegionResolutionError`）。而权威模板里几乎没有
Excel Table —— Table 是 `excel_instrumentation` **注入**的，不是模板自带的。

⇒ 「受管 sheet 可知」的充要条件不是「模板长什么样」，而是**该 entry 有已审核 per-entry 契约**。
今天这个集合大小是 **4**：

| adapter_id | 受管 sheet | anchor | 宿主模板 | 该 sheet 被本工作簿其它 sheet 引用 |
|---|---|---|---|---|
| `b60.hour_budget` | `B60-1工时预算与控制表` | A5 | `B/B60-1 审计项目工时预算与控制表.xlsx` | **0 处** |
| `d2.receivable_detail` | `明细表D2-2` | A11 | `D/D2-1至D2-4 应收账款….xlsx` | 🔴 **52 处**（4 张引用侧 sheet，被引用行 13 / 25 / 26） |
| `g7.soe_subsidiary_disclosure` | `附注披露信息（国企）` | A78 | `G/G7 长期股权投资.xlsx` | **0 处** |
| `h1.disposal_check` | `减少检查表H1-8` | A10 | `H/H1 固定资产.xlsx` | **0 处** |

**裁决**：

1. **不做启发式推断。** 「推断错了会被什么判据抓住」这个问题**没有可接受的答案** —— 猜错
   受管 sheet 会把传播用到错的 sheet 上，产出的 xlsx 仍然能打开、公式仍然有值，只是值错了。
   这正是本 spec 要消除的那类静默错行，用它当实现手段是自相矛盾。歧义度实测中位数 4 张
   sheet 含占位标记，猜中率结构性偏低。
2. **覆盖面 = 有契约的 entry 集合**，其余一律登记 `blocked`，原因码
   `no_projection_contract`。这不是能力缺口而是**定义使然**：无契约 ⇒ 无受管区 ⇒ 不会发生
   行变更 ⇒ 无需传播。可达性清册（Task 24）的价值是**前瞻登记**：把每份模板的引用侧清册
   预先算好，将来给它发契约时传播需求已是已知量。
3. 🔴 **今天唯一有真实传播需求的 entry 是 D2**（52 处）。**D2 因此升为本 spec 的首要判据载体**，
   K11 降为**结构判据载体**。
4. 🔴 **sheet 名不是全库唯一**，禁止按 sheet 名定位宿主模板。实测 `附注披露信息（国企）`
   在 **39 份**模板里都存在，且同名 sheet 在不同模板里被引用情况完全不同（`G7 长期股权投资.xlsx`
   里 0 处，`L/L5 长期应付款.xlsx` 里有 5 个被引用行）。宿主必须由
   **entry → representation → 模板**绑定确定。

### Gate 2：引用载体的真实规模 —— 裁决为「R4.2 点名的四类是空集且结构性不可能，真载体是另外三类」

全库 351 份实测：

| 载体 | 总条数 | 其中含跨 sheet 引用 | 命中模板 |
|---|---:|---:|---:|
| `conditionalFormatting@sqref` | 440 | 🔴 **0** | 0 |
| `dataValidation@sqref` | 1,223 | 🔴 **0** | 0 |
| `mergeCell@ref` | 37,456 | 🔴 **0** | 0 |
| `hyperlink@ref` | 3,950 | 🔴 **0** | 0 |
| `hyperlink@location` | 3,764 | ✅ **3,480** | 158 |
| workbook `definedNames` | 63,973 | ✅ **5,002** | 341 |
| `dataValidation/formula1|2` | 1,094 | ✅ **8** | 4 |
| `conditionalFormatting/formula` | 552 | ✅ **6** | 1 |
| `xl/charts/**` 部件 | **8** | —— | 1 |
| `xl/pivotCache/**` `xl/pivotTables/**` 部件 | 🔴 **0** | —— | 0 |

**前四类为 0 不是「样本不够」，是 OOXML 结构性不可能**：`sqref` / `ref` 的 schema 类型是
`ST_Sqref` / `ST_Ref`，语义上就是**所在 worksheet 内**的区间，表达不了 sheet 前缀。实测取值
形态逐一印证：`H7:M7 C7:F7 J7:J48` / `A1:R1` / `X3`，无一带 `!`。

⇒ **Requirement 4.2 点名的四个属性写错了对象**。同一批元素上真能带跨 sheet 引用的是**另外的
属性/子元素**，实测样本：

- `hyperlink@location` → `底稿目录!A1`（工作簿内导航）
- `dataValidation/formula1` → `Data!$B$2:$B$3`、`底稿目录!$A$9:$A$12`、`'权益法测算表G7-14'!$B$11:$B$20`
- `conditionalFormatting/formula` → `Data!$B$2`、`$F11=Data!$B$3`

**5,002 条 definedNames 必须先分解才能定处置方式**（四类的处置完全不同）：

| 类 | 条数 | 样本 | 处置 |
|---|---:|---|---|
| `builtin_self_scope` | **2,457** | `_xlnm.Print_Area` scope=`工程施工…D4-` → `'工程施工…D4-'!$A$1:$BD$32` | **传播**（受管 sheet 插行后打印区域要跟着长） |
| `target_not_in_workbook` | **2,001** | `'[4]2004'!#REF!`、`_xlnm._FilterDatabase` → `'[1]关联交易-存款'!#REF!` | **登记不传播**（目标不在本工作簿） |
| `user_self_scope` | **292** | `Z_…_.wvu.Rows` → `'已审利润横向分析A1-13-3'!$11:$12` | **传播** |
| `user_cross_sheet` | **252** | `财务费用` → `Word附注!$B$2010` | 🔴 **传播**（R4.1 真正的对象） |

⚠ **原先分成五类（`target_not_in_workbook` 1,991 + `builtin_other_sheet` 10）是分类边界画错了。**
`builtin_other_sheet` 的样本 `_xlnm._FilterDatabase → '[1]关联交易-存款'!#REF!` **本身就是
「目标不在本工作簿」**，类名与样本自相矛盾。处置依据是**目标可解析性**，与是否 builtin 无关
⇒ 归并为四类，`target_not_in_workbook` = **2,001**，和恰为 5,002。
这处是 Task 24 的清册与本表三向锁死时抓出来的。

`hyperlink@location` 的 3,480 同样分解：`cross_sheet_in_workbook` **3,138** / 
`target_not_in_workbook` **321** / `same_sheet` **21**。

**裁决**：

1. Requirement 4.2 改为「这四类属性**结构性**不含跨 sheet 引用，实测全库 0；判据形态是
   **注入变体后仍不得被误传播**」——「传播它们」这个需求本身取消。
2. 新增三类真载体（`hyperlink@location` / `dataValidation/formula1|2` /
   `conditionalFormatting/formula`）为必须传播项，见新增 AC 4.5 / 4.6。
3. definedNames 按上表五分类处置，见新增 AC 4.7。判据必须**逐类**带分母，禁止只断言总数。
4. `xl/pivot*/**` 全库 **0 部件** ⇒ Requirement 4.3 的 pivot 分支判据**在空集上恒真**，
   必须用真实模板 zip 级注入变体取证（chart 有 8 个部件 / 1 份模板，可用真实样本）。

### Gate 3：性能 —— 裁决为「不异步化、不登记 blocked，阈值 2,000 ms」

实测（读 zip + 对全工作簿每个 `<f>` 跑一遍生产改写器 + zip 重打包，即传播成本的**上界**）：

| 模板 | 大小 | sheet | `<f>` 文本 | 被引用处数 | 读 | 全量改写 | 重打包 | **合计** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `C/C24 会计分录 - 细节测试.xlsx` | 1,261 KiB | 11 | 10,906 | **63,240** | 17 ms | 1,063 ms | 78 ms | **1,158 ms** |
| `A/A2-1、A2-2单体报表试算.xlsx` | 664 KiB | 22 | 16,179 | **9,744** | 11 ms | 144 ms | 46 ms | **201 ms** |
| `A/A3-4 合并报表试算…-2019.xlsx` | 1,152 KiB | 43 | 14,506 | 3,659 | 15 ms | 102 ms | 64 ms | **181 ms** |
| `A/A3-1、-2 合并报表试算-2019.xlsx` | 1,031 KiB | 43 | 12,590 | **3,137** | 12 ms | 90 ms | 61 ms | **163 ms** |
| `K/K11 资产减值损失.xlsx` | 57 KiB | 7 | 317 | 114 | 2 ms | 2 ms | 3 ms | **7 ms** |
| `H/H1 固定资产.xlsx` | 195 KiB | 26 | 2,766 | 0 | 3 ms | 27 ms | 13 ms | **43 ms** |

🔴 **实测发现了一份比 spec 登记的极端样本更极端的**：`C/C24 会计分录 - 细节测试.xlsx` 的
`2025假期清单` 被引用 **63,240 处** —— 是 spec 登记的 9,744 的 6.5 倍。它才是真正的最坏样本。

**裁决**：

1. 最坏情况 **1,158 ms**，全部在交互可接受范围 ⇒ **不异步化，不登记 `blocked`**。
2. 阈值定 **2,000 ms**（实测上界的 1.7 倍余量）。依据：这是一次显式的「保存底稿」动作，
   不是键入过程中的实时反馈；且 1,063 ms 那一项是**全量**改写，真实传播只改命中受管
   sheet 的引用，实际更快。
3. `A2-1` 的 16,179 条 `<f>` 只用 144 ms 而 `C24` 的 10,906 条用了 1,063 ms ⇒ 耗时由
   **公式文本长度**主导，不由条数主导。性能判据的自变量必须是**引用处数**而非公式条数。
4. Task 24 的极端登记对象改为 **C24（63,240）+ A2-1（9,744）+ A3-4（3,659）+ A3-1（3,137）**，
   共 4 份 > 1,000 处的组合（实测 10 个组合，见 `Testing Strategy` 的分母表）。

### Gate 4：悬空引用普遍度 —— 裁决为「fail-closed 保留，但必须补第三态：不可删行」

实测两层：

**① 今天有契约的 4 张受管 sheet：fail-closed 完全可用。**

| 受管 sheet | 被引用行 | 其中 ≥ anchor | 删行受阻断的行数 |
|---|---:|---:|---:|
| `B60-1工时预算与控制表` | 0 | 0 | **0** |
| `明细表D2-2` | 3（行 13 / 25 / 26） | 3 | **3** |
| `附注披露信息（国企）`（G7 宿主） | 0 | 0 | **0** |
| `减少检查表H1-8` | 0 | 0 | **0** |

**② 但 K11 形态下 fail-closed = 删行零可用。**

K11 受管区 `A7:N25` = 19 行，被引用行落在区内 **19 / 19 = 100%**
⇒ fail-closed 下可安全删除 **0 / 19 行**。

全库代理统计（172 个「受影响模板 × 被引用 sheet」组合，代理口径 = 被引用行 span 内
被引用行占比）：

| 密度 | 组合数 |
|---|---:|
| **= 100%** | 🔴 **82（47.7%）** |
| ≥ 90% | 92 |
| ≥ 70% | 122 |

**裁决**：

1. **fail-closed 保留**，不改成静默改写、也不默认写 `#REF!` —— Requirement 3.4 不动。
2. 但**必须补第三态**：计划阶段把「受管区内被引用的行」标记为
   **不可删（`undeletable_rows`）**，在 HTML 侧删行**发起之前**就让审计师看见「这几行删不了，
   因为附注在引用它们」。理由：把 100% 阻断暴露成「点了删除然后报错」，等于让 K11 这类底稿的
   删行功能表现为「永远失败」；把它暴露成「这些行标了锁」是同一条 fail-closed 语义的**可用形态**。
   新增 AC 3.8。
3. 由于今天真正会发生删行的只有 4 个契约 entry（最坏 D2 有 3 行不可删），**Wave 3 的删行
   不因 Gate 4 阻塞**；`undeletable_rows` 是与 fail-closed 同批交付的计划字段，不是独立特性。
4. Property 13 的悬空场景载体**保留 K11**（它是唯一能构造 100% 阻断的真实样本），
   Property 11 / 12 的正常路径载体改用 **D2**（唯一有真实混合形态：3 行阻断、其余可删）。
