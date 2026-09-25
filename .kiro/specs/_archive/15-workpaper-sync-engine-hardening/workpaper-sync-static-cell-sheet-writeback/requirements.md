# Requirements Document

## Introduction

D4 双向回写清册（`docs/operations/d4-bidirectional-writeback-inventory.md`）里有两张底稿被裁定为 **HTML-only（引擎限制）**：

- **D4-33 其他业务毛利率分析表**：模板 `其他业务毛利率分析表D4-33`（A1:M31），固定 12 月行 × 固定 3 业务类型列组，受管输入 = 12 月 × 3 组 × 2（收入/成本）= **72 个绝对坐标 static cell**，其余全 Excel 内部公式。
- **D4-8 重要产品毛利分析表**：固定产品块（每块 header 3 行 + 固定 12 月行 + 合计 + 行业对比），块内 12 月为固定静态行 + 大量公式。

两张表的共同硬约束（清册与 context-gather + rematerialize 实测双重实证）：**引擎的受管 cell 只能经 `ExcelIdentityBinding` 落盘，而 binding 必须锚定一张 `row_identity` 动态表的 Excel Table `<tableParts>` 载体**。`excel_extract.managed_tables_of` 对 `not dynamic.has_dynamic_rows` 直接 `raise ManagedRegionResolutionError`；`resolve_managed_region` 靠 Excel Table displayName 定界受管区。D4-9 的 `customer_totals` 静态标量能落盘，仅因它**寄生**在同 sheet 两张动态表（current/prior）的 tableParts 上。**D4-33/D4-8 整张只有静态表、无任何动态行维度** → 无载体 → materialize 写不进、反读缺全部字段。

清册为这两张写下的**唯一解除条件**是：「引擎支持『纯静态 sheet 直写绝对坐标载体』」（另一条「给它造真实动态行表当载体」因属伪造已被拒）。本 spec 就是落实这个解除条件——给引擎补一条 **definedName-anchored 静态受管区** 路径，让「一张只有绝对坐标 static cell、无任何动态行维度」的 sheet 也能双向回写，然后翻转 D4-33/D4-8 的 provider flag 走发布链验收。

### 复用而非重造：definedName 锚点机制已存在（D4-29）

引擎里**已有** workbook-scope definedName 作为受管区锚点的先例——D4-29（客户信息检查表）的**转置表**路径：`phase5_d4_29_customer_detail.py` 声明 `DEFINED_NAME="GT_MANAGED_REGION_D429"` / `MANAGED_REF="$C$10:$M$41"`，`resolve_managed_sheet` 校验 workbook-scope（非 localSheetId）definedName 唯一，`published_identity_observer.collect_workbook_structure` 有 `defined_name_ref` 分支消费它。

**但 D4-29 的语义是「转置」（每列一个 entity、每行一个字段），不是「静态 cell 直写」**。且该分支**硬编码只认 D4-29**（`if key != d429.SHEET_KEY or anchor["defined_name"] != d429.DEFINED_NAME: raise ValueError("Unsupported transposed anchor")`），并调 `d429.extract_transposed_workbook`（转置反读）。本 spec 复用的是「workbook-scope definedName 作为区域锚点」这一**机制**，但必须**新增一个与 transposed 并列的静态 kind**（不能复用 transposed 分支），并**泛化** observer 的硬编码使其按 kind 分派而非按 D4-29 常量分派。

### 范围与非目标

- **只做引擎路径 + D4-33/D4-8 两张验收**：引擎补「静态受管区」这一 anchor kind，随即翻转 D4-33/D4-8 provider flag 发布验收。
- **不动** 现有 Excel-Table-anchored 动态行路径（D4-1/2/9/34/36 等 27 张已落地张的引擎行为必须逐字节零回归）。
- **不动** D4-29 transposed 路径的语义与行为（它是另一个 anchor kind，本 spec 只把 observer 的**分派**从「硬编码 D4-29 常量」泛化为「按 anchor kind + 声明的 defined_name 分派」，D4-29 走 transposed kind 的行为不变）。
- **不改** D4-33/D4-8 的业务字段结构与前端组件模型：provider 已写好并过隔离 probe（`phase5_d4_other_margin_sheet.py`），本 spec 只解除引擎侧的落盘阻塞。
- **不伪造动态表**：拒绝「给纯静态 sheet 注入退化动态表当载体」——footer/row_shift/identity scan 会对假表误判，污染 inventory/drift 基线（这是 context-gather 已否决的 Option b）。
- **不做纯内存无锚点 region**：拒绝「纯内存 region 无 workbook 锚点」——OO 改名后退化成 sheet-id 猜测，违反「禁按 sheet_id/展示名猜受管区」铁律（context-gather 已否决的 Option c）。
- **不提高** materialize soft_limit：D4-33/D4-8 加入后整册 materialize 必须仍在 120s 生产软上限内（静态区无 row_shift/无动态解析，增量极小）。


### 🔴 引擎现状实证（逐函数核实，行号为 2026-09-20 快照，非推断）

| 文件:函数 | 现状（阻塞纯静态 sheet 的具体代码） |
|---|---|
| `excel_extract.py:585` `ExcelIdentityBinding.__post_init__` | 强制 `table_name`/`uuid_column`/`table_key`/`metadata_sheet` 非空 + `column_index_from_string(uuid_column)` 合法。纯静态区无 Excel Table displayName、无 UUID 列 → 构造即抛 `ManagedRegionResolutionError` |
| `excel_extract.py:661` `resolve_managed_region` | 全程 `parse_tables(zf) → 按 binding.table_name 匹配 Excel Table displayName → 取 table.ref 定界`；0 匹配抛 `IdentityCarrierMissingError`。无 definedName 分支 |
| `excel_extract.py:748` `managed_tables_of` | `dynamic = next(t ... table_key==binding.table_key)`；`if not dynamic.has_dynamic_rows: raise ManagedRegionResolutionError`。纯静态 sheet 的 binding.table_key 指向静态表 → 必抛 |
| `excel_extract.py:1207` `_managed_coordinates` | 末尾无条件 `for row in region.row_span: coords.add(f"{region.uuid_column}{row}")` + `for row in rows: coords.add(...)`。纯静态无 uuid_column → 加入幽灵坐标 |
| `excel_extract.py:2228` `_needed_columns_and_rows` | `columns = {region.uuid_column}` 起手；纯静态无 uuid_column |
| `excel_extract.py:2249` `extract_projection` | `resolve_managed_region → _scan_row_identities(uuid_column=region.uuid_column, ...) → read_runtime_identity_inventory`。全链要求 uuid_column + 动态表 identity scan |
| `excel_materialize.py:1611` `plan_managed_writes` | `dynamic_table, _ = managed_tables_of(...)` → `row_shift`（orphan identity 插行）→ footer 两门 → minted UUID 落列。纯静态无 orphan/无 footer marker/无 UUID |
| `published_identity_observer.py:1247` `_frozen_sheet_anchors` | `defined_name_ref` 分支只产 `{sheet_key, defined_name, anchor}`；`else` 分支要求 `table_name + uuid_column + metadata_sheet` |
| `published_identity_observer.py:1364` `collect_workbook_structure` | `defined_name_ref` 分支硬编码 `if key != d429.SHEET_KEY or anchor["defined_name"] != d429.DEFINED_NAME: raise ValueError("Unsupported transposed anchor")`，且调 `d429.extract_transposed_workbook`（转置反读） |
| `excel_instrumentation.py` | 注入路径产出 Excel Table `<tableParts>` + 隐藏 UUID 列 + `_GT_SYNC` runtime binding；无「注入 workbook-scope definedName（无 Table/无 UUID）」路径 |

### 术语约定

- **静态受管区（static managed region）**：一张 sheet 上由 workbook-scope definedName 锚定的固定矩形区域，区内受管 cell 全部按**绝对坐标**（`{列}{行}` 常量，`cell.static_row`）声明，**无 `row_identity` 动态行、无 UUID 列、无 Excel Table 载体、无 footer marker**。
- **`static_region_ref` anchor kind**：新增的 anchor 类型，与既有 `defined_name_ref`（D4-29 transposed）、Excel-Table（默认动态行）并列。observer/extract/materialize 按 kind 分派。
- **transposed（D4-29）**：既有的另一种 definedName 锚定路径，语义是「列=entity、行=字段」，走 `extract_transposed_workbook`。与本 spec 的 static 正交，不合并。
- **寄生静态块**：既有动态行 sheet 上的静态标量块（如 D4-9 customer_totals），寄生在动态表 tableParts 上——这是**已支持**的，与本 spec 的「纯静态 sheet」区分：前者有载体，后者无。

## Requirements

### Requirement 1: 新增 `static_region_ref` binding/region kind（不放松既有约束）

**User Story:** 作为引擎维护者，我要让「一张只有绝对坐标 static cell、无动态行」的 sheet 有一个合法的受管区绑定形态，而不是靠放松既有动态表约束来蒙混——放松约束会让真实的动态表缺 binding 时不再 fail-closed。

#### Acceptance Criteria

1. WHEN 引擎需要为纯静态 sheet 建 binding THEN 必须新增一个**独立的** binding 形态（`ExcelIdentityBinding` 的 static kind，或并列的 `StaticRegionBinding` 类型），其锚点是 **workbook-scope definedName**（如 `GT_MANAGED_REGION_D433`），**不含** `table_name`（Excel Table displayName）、**不含** `uuid_column`
2. WHEN 构造静态 binding THEN 必须校验 `defined_name` 非空且形如合法 definedName，**不得**要求 `uuid_column`/`table_name`；而既有动态 binding 的 `__post_init__` 对 `table_name`/`uuid_column` 非空的强校验**必须保持不变**（动态路径零回归）
3. WHEN 引擎区分 binding kind THEN 必须提供一个显式判据（如 `binding.kind` 属性或 `is_static_region(binding)`），下游 extract/materialize/observer 按此判据分派；**禁止**用「`uuid_column` 是否为空」这类隐式信号分派（隐式信号会与合法动态 binding 的边界态混淆）
4. WHEN 静态 binding 的 `table_key` 指向契约表 THEN 该契约表必须 `has_dynamic_rows == False`（纯静态表），且 binding kind 必须与契约表的 dynamic/static 属性一致；**不一致**（静态 binding 指向动态表，或动态 binding 指向静态表）必须 fail-closed
5. WHEN 既有动态 binding 走 `managed_tables_of` THEN 「binding.table_key 指向的表必须 `has_dynamic_rows`」这条 fail-closed 判据**必须保持**（对动态路径不变）；静态 binding 走**另一条**解析路径，不经过这条判据
6. WHEN 一张 sheet 同时有动态区与静态区（未来可能，非本 spec 目标张）THEN kind 分派机制必须允许两者并存不冲突；但本 spec 的 D4-33/D4-8 是**纯静态 sheet**（整张无动态区），验收以纯静态为准

### Requirement 2: `resolve_managed_region` 支持 definedName 定界静态区

**User Story:** 作为引擎，我要能从 workbook-scope definedName 求出静态受管区的矩形边界（首列/末列/首行/末行），而不是只会从 Excel Table displayName 求。

#### Acceptance Criteria

1. WHEN `resolve_managed_region` 收到 static kind binding THEN 必须走 definedName 分支：解析 workbook-scope definedName（复用 D4-29 已验证的 `resolve_managed_sheet` 校验纪律——唯一、非 localSheetId、type==RANGE），从其 `$C$10:$M$41` 形态的 ref 求出 `ManagedRegion` 的 first_row/last_row/first_column/last_column
2. WHEN definedName 命中 0 个或 >1 个 THEN 必须 fail-closed（0→`IdentityCarrierMissingError`：区域锚点没了；>1→`ManagedRegionResolutionError`：受管区不唯一），与既有 Excel Table 分支的 fail-closed 纪律同构
3. WHEN definedName 指向的 sheet 是平台隐藏 metadata sheet THEN 必须 `raise`（隐藏元数据表永不得作为受管业务 sheet），与既有分支同一判据
4. WHEN 静态区的 `ManagedRegion` 构造 THEN `uuid_column` 字段必须为空/None（静态区无 UUID 列），且**不得**执行「uuid_column 落在 table ref 列跨度内」的动态校验（该校验对静态区无意义）
5. WHEN static kind binding 走 `resolve_managed_region` THEN **不得**调用 `parse_tables`/不得按 Excel Table displayName 匹配（静态区无 Excel Table）；definedName 是唯一区域锚点
6. WHEN 既有动态 binding 走 `resolve_managed_region` THEN 现有 Excel Table displayName 匹配路径**逐字节不变**（动态路径零回归，由既有 358 单 sheet 注入字节 sha256 守卫 + 本 spec 变异反证共同保证）

### Requirement 3: extract 侧支持静态区反读（跳过 identity scan / uuid）

**User Story:** 作为引擎，我要能从静态受管区按绝对坐标反读出全部受管 cell 的值与公式，而不因缺 UUID 列或缺动态行 identity 扫描而中途崩溃。

#### Acceptance Criteria

1. WHEN `managed_tables_of` 收到 static kind binding THEN 必须走静态路径：返回该 sheet 的静态表清册（`has_dynamic_rows==False` 的表），**不执行** `if not dynamic.has_dynamic_rows: raise`（该 raise 只对动态 binding 生效）；静态路径无「dynamic 表」概念，返回形态需与调用方约定（如 `(None, statics)` 或专用返回结构）
2. WHEN `_needed_columns_and_rows` 收到 static kind THEN columns 起手集合**不含** `region.uuid_column`（静态无 uuid），只按静态表 fields 的 `cell.static_row`/列 求列集与行区间
3. WHEN `_managed_coordinates` 收到 static kind THEN **不得**加入任何 `region.uuid_column{row}` 幽灵坐标（末尾两个 uuid 循环对静态区跳过）；受管坐标 = 静态表所有 `cell.static_row` 声明的绝对坐标
4. WHEN `extract_projection` 收到 static kind THEN 必须**跳过** `_scan_row_identities`（无动态行 identity）、跳过 `raw_uuid_by_row` 采集、跳过 row-chunk 循环；只走「7.1 静态受管块」按绝对坐标 `_collect_fields`，`row_identity=""`、`excel_rows=()`（该调用形态既有静态块路径已支持）
5. WHEN `extract_projection` 静态路径读 identity inventory THEN 若无 row UUID 载体，`read_runtime_identity_inventory` / `assert_identity_inventory_retained` 的「row identity 保留」判据必须**条件化**（无 row 身份的静态区不比对 row UUID 清册），但 definedName 锚点本身的存在性/唯一性**必须**仍被保留门校验（静态区的锚点等价于动态区的 Excel Table，缺它必须 fail-closed）
6. WHEN 静态区反读的受管字段值 THEN 必须与 provider projection 的 72 个 cell（D4-33）逐字段一致（往返等价），公式 cell 归入 `formula_inventory` 不当受管值
7. WHEN 既有动态 binding 走 extract THEN identity scan / uuid 采集 / row-chunk / inventory 保留门**全部逐行为不变**（动态路径零回归）

### Requirement 4: materialize 侧支持静态区直写（跳过 row_shift / footer / uuid）

**User Story:** 作为引擎，我要能把 projection 的受管值按绝对坐标写回静态区，而不因试图算插行位移、footer 合计门、minted UUID 落列而崩溃或误判漂移。

#### Acceptance Criteria

1. WHEN `plan_managed_writes` 收到 static kind binding THEN 必须**跳过** row_shift 计划（静态区无 orphan identity，行数固定）、跳过 footer 两门（静态区无 footer marker，合计在区内公式 cell 由 formula_mask 保护）、跳过 minted UUID 落列
2. WHEN 静态区生成写入计划 THEN 必须对每个受管 cell 按绝对坐标（`{列}{static_row}`）生成 `CellWrite`，公式 cell（区内合计/毛利率）按 formula_mask 施加「禁止普通值写入」禁令（与动态区受保护格同一机制）
3. WHEN 静态区 materialize THEN 受管坐标之外的区内 cell 与全簿其它 cell 必须**逐字节不变**（unmanaged-region digest 门对静态区仍成立，只是受管坐标集合改由静态路径求出）
4. WHEN 静态区 materialize 产物 THEN definedName 本身（`GT_MANAGED_REGION_D433`）必须原样保留（不被写操作破坏），它是下一次 extract 的锚点
5. WHEN D4-33/D4-8 加入后整册 materialize THEN 总耗时必须仍在 materialize soft_limit（120s）内；静态区无 row_shift/无动态解析，**不得**为其提高 soft_limit
6. WHEN 既有动态 binding 走 materialize THEN row_shift / footer 两门 / minted UUID 落列 / unmanaged digest **全部逐行为不变**（动态路径零回归）

### Requirement 5: observer 泛化（去 D4-29 硬编码，按 kind 分派）+ instrumentation 注入静态 definedName

**User Story:** 作为维护者，我要 observer 的 definedName 分支不再写死只认 D4-29，而是按 anchor kind 分派（transposed 走 D4-29 转置反读、static 走静态区反读），且 instrumentation 能为静态 sheet 注入 workbook-scope definedName 载体。

#### Acceptance Criteria

1. WHEN `collect_workbook_structure` 遇 `defined_name_ref`/静态 anchor THEN 必须按 anchor kind 分派：`transposed`（现 D4-29）走 `extract_transposed_workbook` 反读；`static_region_ref` 走静态区反读（按 definedName 求 region → 按契约静态表 fields 的绝对坐标建 physical 映射）；**删除**硬编码 `if key != d429.SHEET_KEY ...: raise`，改为「kind 未知才 raise」
2. WHEN observer 分派 transposed kind THEN D4-29 的行为（`resolve_managed_sheet` + `extract_transposed_workbook` + transposed fields 映射）必须**逐行为不变**（D4-29 零回归）
3. WHEN `_frozen_sheet_anchors` 从 instrumentation payload 取锚点 THEN 必须能识别并产出 static kind 锚点（`{sheet_key, defined_name, anchor: "static_region_ref"}`），与既有 `defined_name_ref`（transposed）、Excel-Table（`table_name+uuid_column`）三类并存
4. WHEN instrumentation 注入静态 sheet THEN 必须能写入 workbook-scope definedName（`GT_MANAGED_REGION_{code}` → `${区域 ref}`）到 `xl/workbook.xml`，**不注入** Excel Table `<tableParts>`、**不注入** 隐藏 UUID 列；但仍需注入必要的 runtime binding（`_GT_SYNC` 隐藏 sheet 记录该静态区的 definedName/sheet_key 供反读锚定）
5. WHEN instrumentation 静态注入的 definedName THEN 必须是 workbook-scope（无 localSheetId）、唯一、type==RANGE（满足 D4-29 已验证的 `resolve_managed_sheet` 校验纪律，复用同一校验入口不重写第二份）
6. WHEN structure_hash / structure_fingerprint 对静态 sheet 计算 THEN 必须包含静态区锚点（definedName + 区域几何）作为结构的一部分，使「definedName 被删/被改」能被结构漂移门捕获；`observe_structure_inventory` 的静态行路径（已支持静态行坐标）必须覆盖静态区受管坐标

### Requirement 6: D4-33 / D4-8 翻转 provider flag 走发布链验收

**User Story:** 作为审计师，我要 D4-33 其他业务毛利率分析表和 D4-8 重要产品毛利分析表在「在线编辑」模式改完保存后，回到 HTML 结构化视图能看到同一份数据（真双向），而不是永远 HTML-only。

#### Acceptance Criteria

1. WHEN 引擎静态区路径落地并守卫全绿 THEN D4-33 provider `phase5_d4_other_margin_sheet.py` 的 `_INCLUDE_D433_MARGIN_SHEET` 翻转为 `True`，其静态 binding（definedName `GT_MANAGED_REGION_D433` + 72 cell）接入契约 `d4.revenue_detail.json`
2. WHEN D4-8 provider 落地 THEN 若 D4-8 为纯静态块矩阵（无真实动态行维度，须先 census 实测确认），走同一静态区路径接入；若 census 发现 D4-8 有可增删的真实动态产品块维度，则 D4-8 改走既有动态路径（不属本 spec，另裁）——**D4-8 的静态/动态归属必须由 census 实测裁决，不得假设**
3. WHEN D4-33 模板缺 workbook-scope definedName THEN instrumentation 注入阶段必须为其写入 `GT_MANAGED_REGION_D433`（源模板 census 确认模板无 definedName，须注入）；注入位置/区域 ref 必须与 provider 声明的 72 cell 几何一致
4. WHEN 发布链执行 THEN 必须按 `generate_phase5_d4_contract --apply` → `fix_task76_provision_projection_definitions --apply` → `d43_rematerialize_dual_sheet --apply --force` 顺序跑全，rematerialize 后 generation 递增、`--check` 返回 `already_on_desired_bundle`、无 `RoundtripEquivalenceError`/`FooterAnchorDriftError`
5. WHEN D4-33/D4-8 加入后 THEN entry `xlsx/gt-d4-operating-revenue` 整册 materialize 必须仍在 120s soft_limit 内（不提高上限）
6. WHEN 前端接桥 THEN D4-33（`D4TabOtherMargin.vue`）/D4-8（`D4TabProductMargin.vue`）从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，宿主 `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` 数组加入 `'D4-33'`/`'D4-8'`
7. WHEN 清册更新 THEN `docs/operations/d4-bidirectional-writeback-inventory.md` 中 D4-33/D4-8 从 `⛔ 引擎限制(HTML-only)` 转为 `✅ 三维代码全绿`，统计段「🔵 从零」相应减少；HTML-only 裁定段改写为「已由 spec workpaper-sync-static-cell-sheet-writeback 解除」

### Requirement 7: 守卫、变异检验与真栈实测

**User Story:** 作为维护者，我要证据证明静态区双向回写真的往返一致、动态路径逐字节零回归、D4-29 转置零回归、静态区锚点缺失能 fail-closed，而不是又一批看着有路径实则断裂或悄悄回归了动态路径的改动。

#### Acceptance Criteria

1. WHEN 引擎静态路径落地 THEN 必须有后端 pytest 断言：D4-33 的 72 cell 经 materialize → extract 往返后逐字段相等（Property 1），公式 cell 归 formula_inventory 不当受管值
2. WHEN 编写守卫 THEN 必须对每条关键改动做变异检验并四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS / WRONG-TEST）；锚点至少含：
   - 把 `managed_tables_of` 的静态路径改回「对静态 binding 也执行 `raise ManagedRegionResolutionError`」必红
   - 把 `_managed_coordinates` 对静态区改回「加 uuid_column 幽灵坐标」必红（幽灵坐标会污染受管集合）
   - 把 observer `collect_workbook_structure` 的 kind 分派改回「硬编码只认 D4-29」使 static kind 抛 `Unsupported` 必红
   - 把静态区 `resolve_managed_region` 的 definedName「唯一性校验」删掉（命中多个取第一个）必红
   - 把静态 binding 的 kind 判据改成「按 uuid_column 为空隐式分派」必红（隐式分派会误判合法动态 binding 边界态）
   - 删除 instrumentation 注入的 definedName 后 extract 必红（`IdentityCarrierMissingError`：锚点缺失 fail-closed）
3. WHEN 动态路径零回归 THEN 必须有守卫断言：既有动态 sheet（选 D4-2 或 D4-9 一张）的 materialize 产物字节 sha256 与改动前**逐字节相等**；D4-29 transposed 反读结果与改动前**逐字段相等**（transposed 零回归）
4. WHEN 静态区 fail-closed THEN 必须有守卫断言：definedName 缺失/重复/落在隐藏 metadata sheet 三类异常各自抛对应窄类型异常（不静默、不 fail-open 返回空）
5. WHEN structure_hash 稳定性 THEN 必须断言：加入静态区路径后，既有动态 sheet 的 structure_hash **逐字符不变**（只加静态分支不改动态分支）；静态 sheet 的 structure_hash 包含 definedName 锚点（删 definedName 则 hash 变）
6. WHEN Tier-A 保鲜 THEN 若本 spec 改动 `excel_structure_fingerprint.py`（静态区几何纳入指纹），必须刷新 `onlyoffice_excel_instrumentation_gate.json` 相关模块 digest 并重跑守卫重新实证（`ProbeEvidenceStaleError` 门）
7. WHEN 全部交付 THEN 必须至少一次真栈实测：D4-33（结构最简，纯静态 72 cell）做一次「HTML 改 → 同步到 excel → excel 改一个月度收入 → 回读 HTML 值一致」完整往返，产出 evidence JSON（`docs/operations/evidence/d4-bidirectional-acceptance/D4-33.json`）；D4-8 以单元测试 + 代码结构判据验收（若真栈环境不可用则如实标 `[~]` UNVERIFIABLE，不假绿）
8. WHEN 交付收口 THEN 必须校验 spec 三件套结构（`### Property N` 为整数、`**Validates: Requirements X.Y**` 为 `X.Y` 形态、tasks 含 waves JSON）并确认全部正式产物无 `??` 未跟踪（spec 目录本身入库）；行数门禁（改 `excel_extract.py`/`excel_materialize.py`/`published_identity_observer.py`/`phase5_d4_revenue_detail.py`/`oo_to_html.py` 等）须同步更新 `backend/scripts/file_size_whitelist.txt`

## Correctness Properties

### Property 1: 静态区往返等价

**Validates: Requirements 3.6, 4.2, 7.1**

任意静态受管区的受管 cell 值集合（D4-33 的 72 cell / D4-8 的静态块 cell），经 provider projection → `plan_managed_writes` 直写 → `extract_projection` 反读后，其受管字段必须逐字段相等（浮点容差 `1e-9`，空值保持空值不写 0）。区内公式 cell 由 formula_mask 保护，归 `formula_inventory`，不参与受管值相等性比对。

### Property 2: 动态路径字节零回归

**Validates: Requirements 2.6, 3.7, 4.6**

引入静态区路径后，任一既有动态 binding sheet（Excel-Table anchored）经 `plan_managed_writes` → apply 产出的 workbook 字节，必须与改动前**逐字节相等**（sha256 恒等）；`extract_projection` 对动态 sheet 的 identity scan / uuid 采集 / row-chunk / inventory 保留门行为逐项不变。静态分支是**新增旁路**，不得触碰动态分支的任一语句。

### Property 3: D4-29 转置零回归

**Validates: Requirements 5.2**

observer 的 kind 分派从「硬编码 D4-29 常量」泛化为「按 anchor kind 分派」后，D4-29 走 `transposed` kind 的反读结果（physical/transposed 映射）必须与改动前**逐字段相等**。泛化只改「怎么选分支」，不改 transposed 分支内部逻辑。

### Property 4: 静态区锚点缺失 fail-closed

**Validates: Requirements 2.2, 2.3, 3.5, 7.4**

静态受管区的 workbook-scope definedName 若缺失、重复（>1 个同名）、或落在隐藏 metadata sheet，`resolve_managed_region`/`collect_workbook_structure` 必须各抛对应窄类型异常（`IdentityCarrierMissingError`/`ManagedRegionResolutionError`），**不得**静默返回空 region、不得 fail-open 猜 sheet-id。definedName 是静态区唯一锚点，等价于动态区的 Excel Table。

### Property 5: kind 分派显式

**Validates: Requirements 1.3, 7.2**

extract/materialize/observer 对 binding 的 static/dynamic 分派，必须依据**显式 kind 判据**（`binding.kind` 或 `is_static_region`），不得依据「uuid_column 是否为空」这类隐式信号。变异「改成隐式分派」必须被守卫捕获（合法动态 binding 的边界态不得被误判为静态）。

### Property 6: 静态区无幽灵 UUID 坐标

**Validates: Requirements 3.3, 3.2**

静态受管区的受管坐标集合（`_managed_coordinates`/`_needed_columns_and_rows`）必须恰等于契约静态表 fields 声明的绝对坐标集合，**不含**任何 `uuid_column{row}` 坐标（静态区无 UUID 列）。加入幽灵坐标必被 Property 1 往返比对或专测捕获。

### Property 7: structure_hash 动态侧不变

**Validates: Requirements 5.6, 7.5**

加入静态区路径后，任一既有动态 sheet 的 `structure_hash` 必须**逐字符不变**（静态分支不触碰动态 sheet 的指纹计算）；静态 sheet 的 `structure_hash` 必须包含其 definedName 锚点（删/改 definedName 则 hash 变，使锚点漂移可被结构门捕获）。

### Property 8: materialize 软上限不破

**Validates: Requirements 4.5, 6.5**

D4-33/D4-8 静态区加入 entry `xlsx/gt-d4-operating-revenue` 后，整册 materialize 总耗时必须 ≤ materialize soft_limit（120s，不提高）。静态区无 row_shift/无动态 identity 解析，增量应远小于一张动态表。

## Decisions

- **DEC-1（已裁决）｜静态 kind 独立而非放松动态约束**：新增 `static_region_ref` anchor kind + 独立 binding 形态，而非放松 `ExcelIdentityBinding.__post_init__` 对 uuid/table_name 的强校验。理由：放松强校验会让「真实动态表缺 binding」不再 fail-closed（context-gather 已论证）。静态是**新增旁路**，动态约束原样保留。
- **DEC-2（已裁决）｜复用 definedName 机制但不复用 transposed 分支**：静态区复用 D4-29 已验证的「workbook-scope definedName 作区域锚点」机制与 `resolve_managed_sheet` 校验入口，但走**独立于 transposed 的静态 kind**——transposed 是「列=entity 行=字段」语义走 `extract_transposed_workbook`，static 是「绝对坐标直写」语义。observer 分派从硬编码 D4-29 常量泛化为按 kind 分派，D4-29 转置行为零回归。
- **DEC-3（已裁决）｜拒 Option b（注入退化动态表）**：不给纯静态 sheet 注入退化 Excel Table 当载体——footer/row_shift/identity scan 会对假表误判，污染 inventory/drift 基线。
- **DEC-4（已裁决）｜拒 Option c（纯内存无锚点 region）**：不做纯内存 region——OO 改名后退化成 sheet-id 猜测，违反「禁按 sheet_id/展示名猜受管区」铁律。definedName 是磁盘上可校验的稳定锚点。
- **DEC-5（待 census 裁决）｜D4-8 静态/动态归属**：D4-8「产品块动态计数」需 census 实测确认是「块计数动态（映射固定模板块，块内静态）」还是「真实可增删动态行」。前者走本 spec 静态路径；后者走既有动态路径（不属本 spec）。裁决前 D4-8 落地 blocked。
- **DEC-6（已裁决）｜kind 显式分派**：所有下游按 `binding.kind`/`is_static_region` 显式分派，禁止按 uuid_column 空值隐式分派（Property 5 守卫）。

## Glossary

| 术语 | 含义 |
|------|------|
| 静态受管区 | workbook-scope definedName 锚定的固定矩形区域，区内受管 cell 全按绝对坐标声明，无动态行/UUID/Excel Table/footer marker |
| `static_region_ref` | 新增 anchor kind，与 `defined_name_ref`(D4-29 transposed)、Excel-Table(动态行) 并列，按 kind 分派 |
| transposed(D4-29) | 既有 definedName 锚定路径，语义「列=entity 行=字段」，走 `extract_transposed_workbook`；与 static 正交 |
| 寄生静态块 | 既有动态行 sheet 上的静态标量（如 D4-9 customer_totals），寄生在动态表 tableParts 上——已支持，有载体，区别于纯静态 sheet |
| `ExcelIdentityBinding` | representation 冻结的 Excel identity 绑定；动态形态含 table_name+uuid_column，静态形态含 defined_name |
| `managed_tables_of` | 求 (动态表, 静态表清册)；对静态 binding 走独立路径不执行 `has_dynamic_rows` raise |
| `resolve_managed_region` | 求受管矩形区域；动态走 Excel Table displayName，静态走 workbook-scope definedName |
| `collect_workbook_structure` | observer 的物理结构采集；kind 分派点，需去 D4-29 硬编码 |
| formula_mask | 受保护公式格禁令：禁普通值写入，只保留/还原 `<f>`；静态区合计/毛利率 cell 由此保护 |
| `_INCLUDE_D433_MARGIN_SHEET` | D4-33 provider flag，静态路径落地后翻 True 接入契约 |
| GT_MANAGED_REGION_D433 | D4-33 静态区的 workbook-scope definedName（须 instrumentation 注入，源模板无） |
| 发布链 | `generate_phase5_d4_contract` → `fix_task76_provision_projection_definitions` → `d43_rematerialize_dual_sheet`（cwd=backend, `..\.venv\Scripts\python.exe`） |
| soft_limit | materialize 软上限 120s，生产门；本 spec 不提高 |
| Tier-A 保鲜门 | 改 `excel_structure_fingerprint.py` 触发 `ProbeEvidenceStaleError`，须刷 gate.json digest + 重跑守卫重新实证 |

> **三件套格式约定**：Property 交叉引用统一 `**Validates: Requirements N.M**`（逗号分隔多条）；`### Property` 序号为纯整数。本 spec 只做引擎静态路径 + D4-33/D4-8 验收，不动动态路径与 D4-29 transposed 语义。

## 实现期修正记录（2026-09-21 复盘补记，不改写上方需求条文）

> 需求条文保持原样作为审计轨迹；以下为实现期实测后与条文产生偏差的四处，供后续维护者对照，避免按条文字面去 grep 不存在的符号。

1. **anchor kind 命名：`static_region_ref` → `defined_name_ref` + `region_kind="static"`**
   本文档（Requirement 1 标题 / 5.3 / 术语约定 / Glossary）与 tasks.md 用 `static_region_ref` 指代新 anchor kind，
   但**实现最终未新增该 carrier 名**：carrier gate（`onlyoffice_excel_instrumentation_gate.json`）的真值表里只有
   `defined_name_ref` 通过了真实 OO 探针，新增一个从未被探针验证的 carrier 名会破坏探针证据链。故实现复用
   `defined_name_ref` 作 carrier，用 payload 上的 `region_kind`（`"static"` / 缺省=D4-29 transposed）区分语义，
   静态/动态分派仍由 `binding.kind`（`BindingKind.static_region`）显式裁决（Property 5 / DEC-6 不变）。
   详见 design.md §C1.2 的「🔴 实现期修正」注。**grep 提示**：搜 `region_kind` 与 `BindingKind.static_region`，
   而非 `static_region_ref`。

2. **Requirement 2.1 / 5.5「复用 `resolve_managed_sheet` 校验入口，不重写第二份」未能达成**
   D4-29 的 `resolve_managed_sheet` **硬编码 D4-29 几何**（校验 `destinations[0][1] != MANAGED_REF`=`$C$10:$M$41`、
   `ws.max_row < LAST_FIELD_ROW`），对任意静态区不可复用。实现改用 fingerprint 模块的 `_parse_workbook_xml`
   取 `defined_names`（`{name, scope, ref, hidden}`，`scope is None` 即 workbook-scope），并在
   `_resolve_static_region` 内自行做「唯一 / workbook-scope / 非隐藏 metadata sheet」校验 ⇒ 事实上**存在两份
   definedName 校验逻辑**（D4-29 一份、静态区一份）。**这是本 spec 留下的可重构点**：宜抽共享纯函数
   `resolve_workbook_scope_defined_name(zf, name)` 供两路共同消费，避免未来改校验纪律时改一处漏一处。

3. **Requirement 7.5「structure_hash 包含 definedName 锚点（删 definedName 则 hash 变）」机制描述不准确**
   实测 `StructureFacts.aspect_digests()` 的六个 aspect 为 `visible_sheets` / `business_values` / `formulas` /
   `styles` / `merges` / `protected_parts`，**不含 `defined_names`** ⇒ 删 definedName 不会让该 hash 变。
   真实的锚点漂移捕获机制是 **`identity_inventory` 的 `defined_name` 载体**（按 `GT_` 前缀收集 definedName
   并计数/记 hidden_flags）+ **observer 静态分派 fail-closed**（`_collect_static_region_physical` 反读不到
   definedName 即抛）——后者比「hash 变」更强（结构采集直接无法完成）。守卫见
   `test_static_region_writeback.py::TestStructureHashDynamicUnchangedStaticAnchored::test_deleting_defined_name_fails_static_structure_collection`。

4. **Property 2「逐字节相等（sha256 恒等）」在现引擎下不可证伪**
   `excel_materialize._write_entries` 用 `zipfile.writestr(name, payload)` 不传 `ZipInfo`，zip 条目会写入
   **当前时间戳** ⇒ 同一输入两次 materialize 的**整文件** sha256 必然不同。故 Property 2 的字节判据实际以
   **per-zip-member 解压内容 sha256**（剥离 date_time 噪声）落地，守卫见
   `TestDynamicMaterializeByteZeroRegression`。注：非确定性不影响正确性判定——`RoundtripEquivalenceError`
   比的是 **projection 字段值**，发布链 `--check` 比的是 **definition_bundle_sha256**，均不依赖产物字节。
