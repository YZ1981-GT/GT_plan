# Design Document

## Overview

给 workpaper-sync 引擎补一条 **definedName-anchored 静态受管区**（`static_region_ref` kind）路径，让「一张只有绝对坐标 static cell、无任何动态行维度」的 sheet（D4-33 其他业务毛利率、D4-8 重要产品毛利）也能双向回写。核心手法是**新增旁路**——在 extract/materialize/observer 三处按 binding kind 分派，静态走新路径，动态与 D4-29 transposed 逐字节/逐字段零回归。

设计的第一性约束（贯穿全文）：

1. **静态是新增旁路，不放松动态约束**（DEC-1）：`ExcelIdentityBinding` 对动态的 uuid/table_name 强校验原样保留；静态 binding 是**另一个形态**，走另一条解析链。放松强校验会让真实动态表缺 binding 时不再 fail-closed。
2. **复用 definedName 机制，不复用 transposed 分支**（DEC-2）：静态区借 D4-29 已验证的「workbook-scope definedName 作区域锚点 + `resolve_managed_sheet` 校验入口」，但语义是「绝对坐标直写」而非「列=entity 行=字段」，走**独立 kind**。
3. **kind 显式分派**（DEC-6）：所有下游按 `binding.kind`/`is_static_region(binding)` 分派，禁按 `uuid_column` 空值隐式分派。
4. **锚点磁盘可校验**（DEC-4）：definedName 是 workbook.xml 上可校验的稳定锚点，OO 改 sheet 名不动它——这是拒绝纯内存 region 的根本原因。

## Architecture

### 三类 anchor kind 分派全景

```
binding kind 分派（extract / materialize / observer 三处一致）
├── Excel-Table（默认动态行）      ── 现有，锚点=Excel Table displayName，含 uuid_column
│     resolve_managed_region: parse_tables → 按 displayName 匹配 → table.ref 定界
│     managed_tables_of: dynamic.has_dynamic_rows 必须 True
│     extract: _scan_row_identities + uuid 采集 + row-chunk
│     materialize: row_shift + footer 两门 + minted UUID 落列
│
├── defined_name_ref / transposed（D4-29）── 现有，锚点=workbook-scope definedName，列=entity
│     observer: extract_transposed_workbook（转置反读）
│     ★本 spec 只把 observer 分派从「硬编码 D4-29 常量」泛化为「按 kind」，语义零改
│
└── static_region_ref（本 spec 新增）── 锚点=workbook-scope definedName，绝对坐标直写
      resolve_managed_region: resolve_managed_sheet(definedName) → ref 定界，region.uuid_column=None
      managed_tables_of: 不执行 has_dynamic_rows raise，返回 (None, statics)
      extract: 跳 identity scan / uuid / row-chunk，只走「7.1 静态受管块」按 static_row 收字段
      materialize: 跳 row_shift / footer / minted UUID，按绝对坐标 CellWrite（区内公式 formula_mask 保护）
      instrumentation: 注入 workbook-scope definedName（无 tableParts / 无 UUID 列）
```

### kind 判据的落点

新增显式判据（DEC-6 / Property 5）。两个可选实现，design 选 **A**（改动面小、与 frozen dataclass 兼容）：

- **方案 A（选定）**：`ExcelIdentityBinding` 增一个 `defined_name: str = ""` 字段 + `kind` 计算属性：
  ```python
  @property
  def kind(self) -> BindingKind:
      return BindingKind.static_region if self.defined_name else BindingKind.excel_table
  ```
  以及模块级 `is_static_region(binding) -> bool`。`__post_init__` 分两支校验：有 `defined_name` 走静态校验（definedName 非空合法、**且** table_name/uuid_column 必须为空——防混填）；否则走既有动态校验（table_name/uuid_column 非空，原样保留）。
  - kind 判据是 `defined_name` 字段的**存在**，不是 `uuid_column` 的**缺失**——两者不等价：合法动态 binding 永远有 uuid_column，而「按 uuid_column 缺失分派」在未来出现「动态 binding 边界态」时会误判（Property 5 变异守卫钉死这一点）。
- 方案 B（未选）：并列 `StaticRegionBinding` 新 dataclass。改动面大（所有 `binding: ExcelIdentityBinding` 类型注解都要改 Union），且 adapter 层 `_all_bindings()` 要处理异质集合，回归风险高。

`BindingKind` 为新增 `enum.Enum`（`excel_table` / `static_region`；transposed 由 D4-29 自身机制标识，不进本 enum——D4-29 不构造 `ExcelIdentityBinding`，它走 observer 的 anchor payload 直接标 `transposed`）。

## Components and Interfaces

### C1. `excel_extract.py` — binding kind + 静态解析链

#### C1.1 `ExcelIdentityBinding` 增静态形态（Requirement 1）

```python
class BindingKind(enum.Enum):
    excel_table = "excel_table"
    static_region = "static_region"

@dataclass(frozen=True)
class ExcelIdentityBinding:
    table_name: str = ""          # 动态必填；静态必空
    uuid_column: str = ""         # 动态必填；静态必空
    table_key: str = ...          # 两者都必填（绑定↔契约表一一对应）
    metadata_sheet: str = GT_SYNC_SHEET_NAME
    defined_name: str = ""        # ★新增：静态必填；动态必空
    defined_name_prefix: str = "GT_"
    tombstoned_row_keys: tuple[str, ...] = ()
    dynamic_column_columns: Mapping[...] = field(default_factory=dict)

    @property
    def kind(self) -> BindingKind:
        return BindingKind.static_region if self.defined_name else BindingKind.excel_table

    def __post_init__(self) -> None:
        if self.defined_name:                       # ── 静态分支 ──
            if self.table_name or self.uuid_column:
                raise ManagedRegionResolutionError(
                    "static binding 不得同时声明 table_name/uuid_column（kind 混填）")
            for name, value in (("defined_name", self.defined_name),
                                ("table_key", self.table_key),
                                ("metadata_sheet", self.metadata_sheet)):
                if not str(value or "").strip():
                    raise ManagedRegionResolutionError(f"static ExcelIdentityBinding.{name} 不得为空")
            # definedName 合法性校验复用 D4-29 的 resolve_managed_sheet 纪律（仅字符串形态，不解 zip）
        else:                                        # ── 动态分支（原样，零改）──
            for name, value in (("table_name", self.table_name), ("uuid_column", self.uuid_column),
                                ("table_key", self.table_key), ("metadata_sheet", self.metadata_sheet)):
                if not str(value or "").strip():
                    raise ManagedRegionResolutionError(f"ExcelIdentityBinding.{name} 不得为空 —— frozen identity 必须显式")
            try:
                column_index_from_string(self.uuid_column)
            except ValueError as exc:
                raise ManagedRegionResolutionError(f"ExcelIdentityBinding.uuid_column 形态非法: {self.uuid_column!r}") from exc

def is_static_region(binding: ExcelIdentityBinding) -> bool:
    return binding.kind is BindingKind.static_region
```

`table_name`/`uuid_column` 默认值从「必填无默认」改为 `""` 以允许静态构造省略；动态路径的非空校验由 `__post_init__` 动态分支保证（校验强度不变，只是从「参数必填」下沉到「运行时非空断言」）。

#### C1.2 `resolve_managed_region` 加 definedName 分支（Requirement 2）

函数开头按 kind 分派：

```python
def resolve_managed_region(zf, *, contract, binding):
    if is_static_region(binding):
        return _resolve_static_region(zf, contract=contract, binding=binding)
    # ── 以下为既有 Excel Table 路径，逐字节不动 ──
    sheets, _ = _sheet_part_map(zf); tables = parse_tables(zf, sheets); ...

def _resolve_static_region(zf, *, contract, binding) -> ManagedRegion:
    # 复用 D4-29 已验证的 workbook-scope definedName 校验入口（唯一/非 localSheetId/type==RANGE）
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import resolve_managed_sheet
    sheet_ws, ws = resolve_managed_sheet(_zip_bytes(zf), defined_name=binding.defined_name)
    # ↑ resolve_managed_sheet 抛 ValueError（0/多个/localSheetId/非 RANGE）→ 本函数转译窄类型
    #   0 个 → IdentityCarrierMissingError；>1 → ManagedRegionResolutionError（与既有分支同构）
    ref = _defined_name_ref(binding.defined_name, zf)      # "$C$10:$M$41" → 几何
    first_col, first_row, last_col, last_row = parse_a1_range(ref, location=...)
    sheet_name = ws.title
    sheet = next((s for s in sheets if s["name"] == sheet_name), None)  # 定位 sheet_part
    if is_platform_metadata_sheet(sheet_name):
        raise ManagedRegionResolutionError("受管静态区落在隐藏 metadata sheet 上")
    return ManagedRegion(
        table_key=binding.table_key, table_name="", sheet_name=sheet_name,
        sheet_part=..., table_ref=ref,
        first_row=first_row, last_row=last_row, first_column=first_col, last_column=last_col,
        uuid_column="")   # ★静态区无 UUID 列；不执行 contains_column(uuid) 校验
```

`ManagedRegion.uuid_column` 现为必填 str。静态区传 `""`；下游对静态 region 不访问 `uuid_column`（由 kind 分派保证）。`resolve_managed_sheet` 目前签名 `(workbook_bytes, *, defined_name)`——它接受 bytes，本处从 zf 取回字节复用（避免重解 zip 的第二真源）。`_defined_name_ref` 是新增小工具：从 workbook.xml 取该 definedName 的 `attr_text`（ref），复用 D4-29 `resolve_managed_sheet` 内部已解析的 `DefinedName.value`，不重写 XML 解析。

> 🔴 **实现期修正（2026-09-20，Task 2 落地实测）**：
> 1. **不复用 D4-29 的 `resolve_managed_sheet`**——它深度绑死 D4-29 几何（硬编码校验 `destinations[0][1] != MANAGED_REF`=`$C$10:$M$41`、`ws.max_row < LAST_FIELD_ROW`）。静态区改为直接用 `_parse_workbook_xml`（fingerprint 模块）返回的 `defined_names` 条目 `{name, scope, ref, hidden}`：`scope is None` 即 workbook-scope。新增 `_split_defined_name_ref` 剥 `'Sheet'!$C$10:$M$41` 的 sheet 前缀与 `$`，复用 `parse_a1_range` 求几何。
> 2. **locator anchor 复用 `defined_name_ref`（不自造 `static_region_ref` carrier 锚点）**：carrier gate 真值表（`onlyoffice_excel_identity_carrier_contract.json`）是**真实 OO 探针裁决**，`defined_name_ref` 已 `probe_verdict: passed`（workbook-scope definedName 经 OO 往返保留、ref 随 sheet 改名自动改写），而 `static_region_ref` 从未被 OO 探针取证→SHALL NOT 入 gate。故契约 sheet 的 `locator.anchor = "defined_name_ref"`（合规复用）；**「静态 vs 转置」的语义分派放在 binding.kind（defined_name 字段）+ observer payload 的 region_kind 标记层**，不在 carrier 锚点名层。这修正了 requirements 里「新增 static_region_ref anchor kind」的表述——kind 是**引擎内部分派标记**，不是 carrier gate 锚点。

#### C1.3 `managed_tables_of` 静态路径（Requirement 3.1）

```python
def managed_tables_of(contract, *, binding) -> tuple[TableSpec | None, tuple[TableSpec, ...]]:
    sheet = _sheet_of_table_key(contract, binding.table_key)  # 抽出既有定位逻辑
    if sheet is None:
        raise ManagedRegionResolutionError(...)  # 原样
    if is_static_region(binding):
        # 静态路径：本 sheet 全部静态表（has_dynamic_rows==False）都是受管静态块，无「dynamic 表」
        statics = tuple(t for t in sheet.tables if not t.has_dynamic_rows)
        if not statics:
            raise ManagedRegionResolutionError(
                f"static binding.table_key={binding.table_key!r} 所在 sheet 无静态表 —— kind 与契约不符")
        # Requirement 1.4：静态 binding 指向的表必须 has_dynamic_rows==False
        target = next(t for t in sheet.tables if t.table_key == binding.table_key)
        if target.has_dynamic_rows:
            raise ManagedRegionResolutionError("static binding 指向了动态表（kind 混填）")
        return None, statics
    # ── 以下为既有动态路径，逐字节不动（含 has_dynamic_rows raise）──
    dynamic = next(t for t in sheet.tables if t.table_key == binding.table_key)
    if not dynamic.has_dynamic_rows:
        raise ManagedRegionResolutionError(...)   # 动态路径这条 raise 必须保留（Requirement 1.5）
    statics = [...]; return dynamic, tuple(statics)
```

返回 `(None, statics)`：静态路径无动态表。**所有调用点**（`_managed_coordinates`/`_needed_columns_and_rows`/`extract_projection`/`plan_managed_writes`）当前都 `dynamic, statics = managed_tables_of(...)` 并随后访问 `dynamic.table_key` 等——必须在这些调用点前置 kind 分派，静态分支不访问 `dynamic`（为 None）。这是本 spec 改动面最广的一处，须逐调用点核查（grep `managed_tables_of` 全部 5 处调用点）。

#### C1.4 `_needed_columns_and_rows` / `_managed_coordinates` 静态分支（Requirement 3.2/3.3）

```python
def _needed_columns_and_rows(*, contract, region, binding):
    if is_static_region(binding):
        columns: set[str] = set()          # ★不含 uuid_column
        _, statics = managed_tables_of(contract, binding=binding)
        first, last = region.first_row, region.last_row
        for table in statics:
            for spec in table.fields:
                columns.add(_resolve_field_column(spec, table=table, region=region, binding=binding))
                if spec.cell is not None and spec.cell.static_row is not None:
                    first = min(first, spec.cell.static_row); last = max(last, spec.cell.static_row)
        return frozenset(columns), range(first, last + 1)
    # ── 动态原样 ──
    dynamic, statics = managed_tables_of(...); columns = {region.uuid_column}; ...

def _managed_coordinates(*, contract, region, binding, scan):
    coords: set[str] = set()
    if is_static_region(binding):
        _, statics = managed_tables_of(contract, binding=binding)
        for table in statics:
            for spec in table.fields:
                if spec.cell is None or spec.cell.static_row is None: continue
                column = _resolve_field_column(spec, table=table, region=region, binding=binding)
                coords.add(f"{column}{spec.cell.static_row}")
        return frozenset(coords)            # ★不加任何 uuid_column{row} 幽灵坐标
    # ── 动态原样（含末尾两个 uuid_column 循环）──
    dynamic, statics = managed_tables_of(...); rows = ...; ...
```

`_resolve_field_column` 对静态 field 走 `cell.column`（绝对列），不走 dynamic_column 绑定——须确认其对 `binding.uuid_column==""` 不崩（静态 field 的列解析不依赖 uuid_column）。

#### C1.5 `extract_projection` 静态分支（Requirement 3.4/3.5）

在 `region = resolve_managed_region(...)` 之后按 kind 分叉：

```python
if is_static_region(binding):
    columns, rows = _needed_columns_and_rows(contract=contract, region=region, binding=binding)
    cells = _read_cell_view(artifact, sheet_name=region.sheet_name, columns=columns, rows=rows, data_only=True)
    formula_cells = {...}  # 同动态，读 data_only=False 取 <f>
    # ★跳过 raw_uuid_by_row / _scan_row_identities / read_runtime_identity_inventory 的 row 部分
    _, static_tables = managed_tables_of(contract, binding=binding)
    # 仅锚点存在性保留门（definedName 是否还在），不比 row UUID 清册
    _assert_static_anchor_retained(definitions=definitions, binding=binding, zf=..., entry_id=entry_id)
    # 只走「7.1 静态受管块」：row_identity="", excel_rows=()
    for static_table in static_tables:
        _collect_fields(specs=[s for s in static_table.fields if s.cell is not None],
                        row_identity="", excel_rows=(), cells=cells, formula_cells=formula_cells,
                        table=static_table, region=region, binding=binding, ...)
    return ExcelExtractOutcome(projection=..., ...)  # scan=None, identity inventory 空 row
# ── 动态原样 ──
```

`assert_identity_inventory_retained`（Requirement 3.5）：现签名比对 `expected: EntryIdentityInventory` 的 row UUID 清册。静态区 `retain_identity_inventory` 分支须条件化——若 binding 为静态，改调 `_assert_static_anchor_retained`（只断言 definedName 锚点在冻结 inventory 里且当前 workbook 仍有该 definedName），不比 row 清册。冻结的 `EntryIdentityInventory` 对静态 sheet 须记录「静态区锚点」而非「row UUID 载体」——这一侧由 instrumentation 冻结（C4）。

### C2. `excel_materialize.py` — `plan_managed_writes` 静态分支（Requirement 4）

```python
def plan_managed_writes(*, projection, contract, binding, region, scan, ...):
    if is_static_region(binding):
        return _plan_static_writes(projection=projection, contract=contract, binding=binding,
                                   region=region, substrate_entries=..., substrate_formulas=...,
                                   runtime_binding=..., intended_formulas=...)
    # ── 以下为既有动态路径（dynamic_columns / row_shift / footer 两门 / minted UUID），逐字节不动 ──
    dynamic_columns = assert_dynamic_column_binding_usable(...); dynamic_table, static_tables = managed_tables_of(...); ...

def _plan_static_writes(*, projection, contract, binding, region, substrate_entries, substrate_formulas,
                        runtime_binding, intended_formulas) -> MaterializePlan:
    _, static_tables = managed_tables_of(contract, binding=binding)
    writes: list[CellWrite] = []
    for table in static_tables:
        for spec in table.fields:
            if spec.cell is None or spec.cell.static_row is None: continue
            column = _resolve_field_column(spec, table=table, region=region, binding=binding)
            coord = f"{column}{spec.cell.static_row}"
            if _is_formula_masked(spec):                 # 区内合计/毛利率：只保留/还原 <f>，禁普通值
                writes.append(_formula_preserving_write(coord, spec, intended_formulas, substrate_formulas))
            else:
                value = projection.value_at(table.table_key, spec.stable_field_key)  # 受管值
                writes.append(CellWrite(coord=coord, value=value, ...))
    return MaterializePlan(cell_writes=tuple(writes), row_shift=None, ...)  # ★row_shift=None / 无 footer / 无 minted UUID
```

关键：静态分支**不构造** row_shift、**不调** footer 两门（`assert_footer_anchor_stable`/`assert_footer_formula_covers_managed_rows`）、**不落** minted UUID（无 UUID 列）。区内公式 cell（合计 B/C/D、各组毛利率 G/J/M、合计行公式）走 formula_mask 保护（与动态区受保护格同一 `_formula_preserving_write` 机制）。definedName 本身不在 cell_writes 里，写操作只碰受管值坐标 → definedName 原样保留（Requirement 4.4）。unmanaged-region digest 门（Requirement 4.3）由 `materialize_projection` 上层对「受管坐标之外逐字节相等」的既有断言保证，受管坐标集合改由静态路径 `_managed_coordinates` 求出。

`MaterializePlan` 须能表达 `row_shift=None` 且 `cell_writes` 只含绝对坐标（现结构已支持 row_shift 可选；须确认无字段强制要求 dynamic_table）。

### C3. `published_identity_observer.py` — kind 分派泛化（Requirement 5.1/5.2/5.3）

#### C3.1 `collect_workbook_structure` 去 D4-29 硬编码

现状（1377 附近）：
```python
if anchor.get("anchor") == "defined_name_ref":
    from ... import phase5_d4_29_customer_detail as d429
    if key != d429.SHEET_KEY or anchor["defined_name"] != d429.DEFINED_NAME:
        raise ValueError("Unsupported transposed anchor")   # ★硬编码
    _, ws = d429.resolve_managed_sheet(...); d429.extract_transposed_workbook(data); ...
```

改为按 kind 分派：
```python
anchor_kind = anchor.get("anchor")
if anchor_kind == "defined_name_ref":          # D4-29 transposed —— 语义零改
    from ... import phase5_d4_29_customer_detail as d429
    if key != d429.SHEET_KEY or anchor["defined_name"] != d429.DEFINED_NAME:
        raise ValueError("Unsupported transposed anchor")   # transposed 仍只 D4-29（不扩，非本 spec 目标）
    ... 原样 ...
    continue
if anchor_kind == "static_region_ref":         # ★本 spec 新增
    physical[key] = _collect_static_region_physical(data, contract, key, anchor["defined_name"])
    continue
```

`_collect_static_region_physical`：按 definedName 求 region（复用 `resolve_managed_sheet` 校验），从契约该 sheet 的静态表 fields 建 `{stable_field_key: (col, row)}` 绝对坐标映射，供 observer 结构比对。**不调** `extract_transposed_workbook`（那是转置语义）。

> 🔴 保留 transposed 分支的 D4-29 硬编码断言不动（Requirement 5.2 D4-29 零回归）——本 spec 不扩 transposed，只**并列**加 static kind 分支。「去 D4-29 硬编码」的准确含义是「新增 static kind 不再复用/污染 transposed 的 D4-29 特判」，而非删除 transposed 的 D4-29 断言。

#### C3.2 `_frozen_sheet_anchors` 产静态锚点（Requirement 5.3）

现状：`region_boundary_locator.anchor == "defined_name_ref"` → 产 `{sheet_key, defined_name, anchor:"defined_name_ref"}`。新增：当 instrumentation payload 的 `region_boundary_locator.anchor == "static_region_ref"` → 产 `{sheet_key, defined_name, anchor:"static_region_ref"}`。二者 payload 形态一致，只 anchor 值不同 → observer 据此分派到不同反读。

### C4. `excel_instrumentation.py` — 注入静态 definedName（Requirement 5.4/5.5）

新增静态注入路径：当 instrumentation spec 标记为静态区（无 tableParts/无 uuid），注入：
1. **workbook-scope definedName** 到 `xl/workbook.xml`：`<definedName name="GT_MANAGED_REGION_D433">'其他业务毛利率分析表D433'!$E$12:$M$23</definedName>`（无 localSheetId → workbook-scope；ref 覆盖 provider 声明的受管 cell 几何）。
2. **`_GT_SYNC` runtime binding** 记录该静态区（`sheet_key` → `defined_name`、`anchor=static_region_ref`），供 `_frozen_sheet_anchors`/`read_runtime_binding_pairs` 反读锚定。
3. **不注入** Excel Table `<tableParts>`、**不注入** 隐藏 UUID 列。

definedName 合法性（workbook-scope/唯一/type==RANGE）复用 D4-29 `resolve_managed_sheet` 校验入口在注入后自检（不重写第二份校验）。structure_fingerprint 须把静态区 definedName 纳入指纹（Requirement 5.6）——这可能触发 Tier-A 保鲜门（C6）。

### C5. Provider 接入 — D4-33（已写）/ D4-8（待 census）

#### C5.1 D4-33（`phase5_d4_other_margin_sheet.py`，已写并过隔离 probe）

provider 已实现契约 parse + 72 cell projection/merge 往返、slot 位置映射（前 3 业务类型 ↔ E-G/H-J/K-M）、dict store 门面 `merge_d433_from_projection` 返 3-tuple。落地时需：
- 声明静态 binding：`ExcelIdentityBinding(table_key="d433-static", defined_name="GT_MANAGED_REGION_D433", metadata_sheet=GT_SYNC_SHEET_NAME)`（无 table_name/uuid_column）。
- 契约 sheet `d433-managed` 的 static table `has_dynamic_rows=False`，72 个 field 各带 `cell.static_row` 绝对坐标（E/F/H/I/K/L 列 × R12-23）；合计/毛利率 cell 归 formula_mask。
- 6 处接线进 `phase5_d4_revenue_detail.py`（import + flag/instrumentation_specs/STORE_ITEMS/sheet_payload/projection/dict 门面）——**只加不动** D4-2/3/34/36 等既有张。
- instrumentation spec 标 `static_region_ref`（触发 C4 注入 definedName）。
- 翻 `_INCLUDE_D433_MARGIN_SHEET=True`（Requirement 6.1）。

#### C5.2 D4-8（`phase5_d4_product_margin_sheet.py`，待建，先 census）

Requirement 6.2 / DEC-5：D4-8「产品块动态计数」须 census 实测裁决——
- 若「块计数动态（映射固定模板块，块内 12 月固定静态行）」→ 走静态路径（同 D4-33，但多块）。多块静态区可能需要多个 definedName（每块一个）或一个覆盖全部块的大 region ref，census 定几何后裁。
- 若「真实可增删动态产品行」→ 走既有动态路径，不属本 spec。
- census 前 D4-8 落地 **blocked**（tasks 里标 `*` 可选 + census 前置）。

### C6. Tier-A 保鲜门（Requirement 7.6）

若 C4 使 `excel_structure_fingerprint.py` 纳入静态区 definedName（改动指纹计算），会触发 `ProbeEvidenceStaleError`——须：
1. 用一次性 python 脚本（字符串替换保格式）刷新 `onlyoffice_excel_instrumentation_gate.json` 的 `fingerprint_module` digest（或相关模块 digest）。
2. 重跑守卫套件重新实证（`test_task75` 等），确认 246+ passed 无回归。
若静态区 definedName 已被既有 `_parse_workbook_xml` definedName 采集覆盖（D4-29 已让指纹含 definedName），则可能无需改 fingerprint 模块 → 无 Tier-A 触发。**实现前先跑一次守卫确认是否触发**，触发才刷。

## Data Models

### `ManagedRegion`（复用，静态区填充约定）

| 字段 | 动态区 | 静态区 |
|---|---|---|
| `table_name` | Excel Table displayName | `""` |
| `uuid_column` | 隐藏 UUID 列标 | `""`（下游 kind 分派不访问） |
| `table_ref` | Excel Table ref | definedName ref（`$C$10:$M$41`） |
| `first/last_row/column` | Table ref 求得 | definedName ref 求得 |

`contains_column(uuid)` 校验对静态区跳过（`_resolve_static_region` 不调）。

### `MaterializePlan`（复用，静态区 `row_shift=None`）

静态区 plan：`cell_writes` 只含绝对坐标 CellWrite，`row_shift=None`，无 footer 相关字段值，无 minted UUID。须确认现结构 `row_shift` 可选、无强制 dynamic_table 依赖。

### `EntryIdentityInventory`（冻结预期，静态区记锚点非 row UUID）

静态 sheet 冻结的 inventory 记「静态区 definedName 锚点」（sheet_key + defined_name），不记 row UUID 载体。`assert_identity_inventory_retained` 对静态 binding 走 `_assert_static_anchor_retained`（断言 definedName 存在），不比 row 清册。

## Error Handling

| 场景 | 异常 | 判据来源 |
|---|---|---|
| 静态 definedName 命中 0 | `IdentityCarrierMissingError` | Requirement 2.2 / Property 4 |
| 静态 definedName 命中 >1 | `ManagedRegionResolutionError` | Requirement 2.2 / Property 4 |
| 静态 definedName 落隐藏 metadata sheet | `ManagedRegionResolutionError` | Requirement 2.3 / Property 4 |
| static binding 混填 table_name/uuid_column | `ManagedRegionResolutionError` | Requirement 1.1 / Property 5 |
| static binding 指向动态表 | `ManagedRegionResolutionError` | Requirement 1.4 |
| observer 遇未知 anchor kind | `ValueError` | Requirement 5.1 |
| instrumentation 注入的 definedName 非 workbook-scope/非唯一/非 RANGE | `ValueError`（复用 resolve_managed_sheet 校验） | Requirement 5.5 |

所有静态区异常都是**窄类型 fail-closed**，不静默返回空 region、不 fail-open 猜 sheet-id（DEC-4）。

## Testing Strategy

### 守卫归属边界

新守卫挂在 workpaper-sync 引擎既有测试边界内（`backend/tests/workpaper_sync/`）：
- 引擎静态路径单测：新增 `test_static_region_writeback.py`（往返 / kind 分派 / fail-closed）。
- 动态零回归：挂 `test_task37`/`test_task38`（binding/resolve/materialize 边界）既有归属。
- D4-29 零回归：挂 D4-29 既有守卫或新增 `test_static_region_observer_dispatch.py`。
- D4-33 契约自洽：`test_d4_33_margin_contract.py`（现钉 provider 自洽 + live 契约不含 D4-33 的诚实状态；落地后改钉 live 契约**含** D4-33 + 往返）。
- 前端接桥：`d4OtherMarginSyncHostWiring.spec.ts`（新增，同 D4-34/36 范式）。

### Property → 守卫 → 变异反证映射

| Property | 守卫（断行为非字符串存在） | 变异反证（改回旧行为必红） |
|---|---|---|
| P1 静态往返等价 | D4-33 72 cell materialize→extract 逐字段相等；公式归 formula_inventory | 把静态区某 cell 反读改成读 uuid 列 → 值错必红 |
| P2 动态字节零回归 | D4-2/D4-9 materialize 产物 sha256 == 改前 | 让静态分支意外触碰动态 `row_span` uuid 循环 → sha256 变必红 |
| P3 D4-29 转置零回归 | D4-29 transposed 反读逐字段 == 改前 | observer 把 transposed 分派错接到 static 反读 → 字段错必红 |
| P4 锚点缺失 fail-closed | definedName 删/重复/隐藏 sheet 各抛窄异常 | 把唯一性校验删（多个取第一）→ 不抛必红 |
| P5 kind 显式分派 | `is_static_region` 按 defined_name 判；混填 binding 抛 | 改成按 uuid_column 空值隐式分派 → 合法动态边界态误判必红 |
| P6 无幽灵 UUID 坐标 | `_managed_coordinates(static)` == 静态 fields 绝对坐标集 | 静态分支加 `uuid_column{row}` → 坐标集含幽灵必红 |
| P7 structure_hash 动态不变 | D4-2 structure_hash 逐字符 == 改前；D4-33 hash 含 definedName | 静态分支触碰动态 hash 计算 → 动态 hash 变必红 |
| P8 软上限不破 | D4-33/D4-8 加入后整册 materialize ≤120s（不提 soft_limit 实测不抛 SoftTimeout） | — （性能观测，非变异） |

### 变异四态判定

每条变异按 RED（守卫正确捕获）/ GREEN（守卫缺陷，变异未被抓）/ ANCHOR-MISS（变异点不可达）/ WRONG-TEST（抓错原因）判定，逐条记录进 evidence。GREEN/ANCHOR-MISS/WRONG-TEST 都要修守卫或修变异点，不留假绿。

### 真栈实测（Requirement 7.7）

D4-33 走 start-dev.bat + 真实 OO 环境：HTML 改一个月度收入 → 「同步到在线编辑」→ OO 里改另一个 cell → 保存 → 回读 HTML 值一致，产 `evidence/.../D4-33.json`。环境不可用则标 `[~]` UNVERIFIABLE（不假绿），代码结构判据 + 单测先行。

## 实现顺序（降低回归风险）

1. **先 kind 判据 + binding 静态形态**（C1.1）——地基，不接下游先单测构造/校验。
2. **extract 静态链**（C1.2~C1.5）——先让「读」通，用 provider 已过 probe 的 projection 造 substrate 单测往返。
3. **materialize 静态链**（C2）——让「写」通，闭合往返 Property 1。
4. **observer 泛化**（C3）——去硬编码、加 static kind 分派，钉 D4-29 零回归。
5. **instrumentation 注入**（C4）——注入 definedName，跑一次守卫确认是否触发 Tier-A。
6. **动态零回归全面复核**（P2/P3/P7）——所有动态张 sha256/hash 逐项比对。
7. **D4-33 provider 接线 + 发布链 + 前端接桥 + 真栈**（C5.1 / Requirement 6）。
8. **D4-8 census 裁决**（C5.2 / DEC-5）——静态则接入，动态则出本 spec 范围。
9. **清册更新 + 收口**（Requirement 6.7 / 7.8）。

> 每步守卫全绿 + 变异反证 + soft_limit 不提，才进下一步。发布链每步验 `--check` 无 drift。全程 stash-isolation 只提交自己文件。
