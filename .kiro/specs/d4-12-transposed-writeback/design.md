# Design — D4-12 合同检查表 转置双向回写

## 概述

把绑死 D4-29 的转置引擎泛化为参数化 `TransposedSheetSpec` + 注册表分派，再用它为 D4-12 建 provider、instrument 模板、登记契约、接前端桥。核心是 **GENERALIZE 不回归**：既有 D4-29 的 materialize 逐字节、extract 逐字段、mapping_digest 全部不变，只把「写死 D4-29」抽成「据 spec 参数化 + 注册表命中分派」。

设计对齐主控 §5.3 共享锁（改双向内核共享文件须泛化不回归单张）与清册 §判据（三维 + 第四维 OO→HTML 消费侧）。

## 现状锚点（实测，实现以此为准）

| 维度 | D4-29（既有蓝本） | D4-12（本 spec 目标） |
|---|---|---|
| managed_sheet | 客户信息检查表D4-29 | 合同检查表D4-12 |
| sheet_key | d4-29-managed | d4-12-managed |
| table_key | customer_detail_transposed | contract_inspection_transposed |
| template_id | D429 | D412 |
| store_item_id | D4-29-customers | D4-12-contracts-v2 |
| header_row | 10 | 10 |
| first_entity_column | **C** | **B**（A 是字段标签列，无独立 label 子列） |
| initial_entity_column | M | **K**（模板预画 B–K 共 10 列） |
| field_rows | 28 字段（跳 27/32/33） | **21 字段 R11–R31 连续** |
| footer_rows / static_prompt | (42,46) / 48 | R32(审计说明)/R36(结论) / R38 |
| identity_carrier_row | 9（隐藏） | 注入行（模板原无，取合同区上方一行） |
| identity_carrier_prefix | GT-CUSTOMER- | GT-CONTRACT- |
| defined_name / managed_ref | GT_MANAGED_REGION_D429 / $C$10:$M$41 | GT_MANAGED_REGION_D412 / $B$10:$K$31 |
| 模板前置 | 已有 definedName + 隐藏 R9 | **两者皆无，须 instrument 注入** |

> 🔴 D4-29 的 definedName + 隐藏载体行是**模板预置**的；D4-12 模板两者皆无，是本 spec 与 D4-29 落地路径的关键差异——D4-12 须由 instrumentation **注入**这两件（不手改源模板磁盘）。
>
> 🟡 **勘误（2026-09-20 实施期 openpyxl 实测，保留上行原设计假设作对照）**：上行「D4-29 模板前置=已有 definedName + 隐藏 R9」**事实有误**。实测 D4-29 源模板（合并模板 `D/D4 收入底稿.xlsx`，TEMPLATE_SHA256 `b8fb92d4…`）**无** `GT_MANAGED_REGION_D429`（有 1008 个 `#REF!` 垃圾 definedName 但无任何 GT_ 前缀），隐藏 R9 载体行也**不存在于源模板**——两者都是 `excel_instrumentation.instrument_workbook_bytes_multi` 的 transposed_sheets 分支在运行时字节上**注入**的（同 D4-12 完全一致的路径）。故「模板前置」维度实际对 D4-29/D4-12 **无差异**：均为 instrument 注入。**利好**：D4-12 无需任何新注入代码，provider 在 primary spec 的 `transposed_sheets` 追加 `sheet_payload_d412()` 即复用既有注入逻辑（Task 6/7 已验证）。此勘误使 requirements 「两者须由 instrumentation 注入，与 D4-29 一致由代码注入」得到实测坐实（requirements 表述正确，本表「模板前置」行的对照措辞误导）。

## 架构

### 分层
```
前端 D4TabContract.vue（在线编辑）
  └─ useWorkpaperSyncBridge(entry=xlsx/gt-d4-operating-revenue, sheet=d4-12-managed)
      └─ WorkpaperSyncEditorHost
  ↕（统一同步路径：store-projection / pending-mutations / materialize）
后端 adapters/excel.py（ExcelSyncAdapter）
  └─ 转置注册表分派（本 spec 泛化点）
      └─ TransposedSheetSpec 实例：D4-29 / D4-12
          └─ 通用转置引擎（materialize_transposed / extract_transposed / build_projection / merge）
契约 d4.revenue_detail.json（+ d4-12-managed sheet + D4-12-contracts-v2 store item）
instrumentation（注入 GT_MANAGED_REGION_D412 + 隐藏载体行）
```

### 关键设计决策

**决策 1：泛化为 `TransposedSheetSpec` 数据类，不复制 provider**
`phase5_d4_29_customer_detail.py` 的模块级常量 + 4 个核心函数（`materialize_transposed_workbook` / `extract_transposed_workbook` / `build_store_projection` / `merge_projection_into_store`）里，几何/身份是数据、算法是通用的。抽法：
- 新增 `phase5_transposed_sheet.py`（通用引擎）：把 D4-29 的算法搬进来，所有 D4-29 硬编码常量改为读 `spec: TransposedSheetSpec` 的字段。
- `phase5_d4_29_customer_detail.py` 改为**薄壳**：定义 `SPEC_D429 = TransposedSheetSpec(...)` + 保留 `is_enabled`/`materialize_file`/`extract_file` 等既有导出名（委托给通用引擎 + SPEC_D429），使既有 4 处 adapter import 与守卫零改动即可先绿（灰度）。
- 新增 `phase5_d4_12_contract.py`：`SPEC_D412 = TransposedSheetSpec(...)`。
- 新增 `transposed_registry.py`：`REGISTRY = [SPEC_D429, SPEC_D412]` + `resolve_transposed_specs(contract) -> list[TransposedSheetSpec]`（据 contract_id + sheet_key 命中）。

> 为什么保薄壳而非直接删 D4-29 常量：既有守卫 `assert_mapping_digest`/adapter import 名/测试大量引用 `phase5_d4_29_customer_detail` 的符号；薄壳让「泛化」与「D4-29 零回归」可分两步验证（先泛化引擎让 D4-29 全绿，再接 D4-12），降回归风险。删旧符号非本 spec 目标。

**决策 2：`is_enabled` → 注册表命中，adapter 4 处旁路改遍历**
`adapters/excel.py` 的 4 处 `if is_enabled(contract): 调 D4-29 专属函数` 改为 `for spec in resolve_transposed_specs(contract): 调通用引擎(spec, ...)`：
- materialize 单/多 binding：逐 spec `materialize_file(output, projection, contract, spec)`（各自把自己那张转置 sheet 的列覆盖写回）。
- extract：逐 spec `extract_file(artifact, contract, spec)` 各产一段 projection 并入 `_merge_projections`。
- verify_unmanaged_regions：逐 spec 把 after 的转置区重投影回 before 副本（D4-29 现有逻辑，按 spec 各做一遍；多转置 sheet 时 before 副本链式叠加）。
- `row_oriented_sheets` 的 `layout=="customer_columns"` 排除：D4-12 契约的转置 sheet 也标同 layout，行表 instrumentation 自动跳过（无需再改此函数）。

> 兼容性：`is_enabled(contract)`（布尔）保留为 `bool(resolve_transposed_specs(contract))`，既有调用点语义不变。

**决策 3：instrumentation 注入 definedName + 隐藏载体行（D4-12 独有）**
D4-29 因模板已预置，其 instrumentation 不注入这两件；D4-12 须注入。设计：
- 在 D4-12 的 instrumentation 路径注入 workbook-scope `GT_MANAGED_REGION_D412` = `$B$10:$K$31`（无 localSheetId、type RANGE）。
- 注入隐藏载体行：取合同区上方一行作 identity_carrier_row，写 `GT-CONTRACT-{id}` + `Protection(locked=True)` + `row_dimensions[row].hidden=True`。
- 复用 D4-29 的 `resolve_managed_sheet` 校验（泛化后接收 spec 的 defined_name/managed_ref）自检注入产物。
- 载体行位置裁决：D4-29 用 header_row 上方 1 行（R9）。D4-12 header 在 R10，其上 R8/R9 是审计过程文本（A8=`1.……`）。**载体行不能覆盖已有内容**——设计取 header_row 上方最近的空行或注入一行（实现阶段 census 确认 R9 是否可用；若被占用则在 R10 上方 insert 一隐藏行并相应下移几何，或另选一行）。这是 Task 阶段必须 openpyxl 实测定的几何点，requirements DEC-2 已标「注入行」为参数。

**决策 4：前端行身份稳定化 + 接桥**
- `ContractInspectionItem.id` 当前 `c-{ts}-{rand}` 已是稳定字符串（存在 store 里跨会话持久），满足「稳定 + 唯一」；只需校验安全字符（provider 侧 `_payload` 拒绝含 `/~{}`）。**不改 id 生成规则**（避免既有数据迁移），只在 provider 侧做安全校验 + 前端 CRUD 保证唯一。
- `D4TabContract.vue` 在线编辑分支参照 `D4TabCustomerDetail.vue`（D4-29 已接）：`useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` + `capabilityForEntry` + flushHtml（先 flushPendingSave 再 readStoreProjection）+ 同步态三态 tag；宿主 `isD4DedicatedSyncSheet` 加 'D4-12'。

## 数据流

### HTML → OO（materialize）
1. 前端 store `D4-12-contracts-v2` = `[{id, ...21字段}]` → build_store_projection（通用引擎按 SPEC_D412）→ stable_key `contract_inspection_transposed/{id}/{field}`。
2. adapter materialize：先普通 materialize_projection，再 `materialize_file(spec=SPEC_D412)` 逐合同写列 B.. + 隐藏载体行写 `GT-CONTRACT-{id}`。
3. verify：转置区经重投影 before 副本比对，不判 unmanaged drift。

### OO → HTML（extract + mirror 消费）
1. adapter extract：`extract_file(spec=SPEC_D412)` 读隐藏载体行 id + 字段行 → projection 并入 merge。
2. `oo_to_html` mirror 消费侧：转置 store item `D4-12-contracts-v2` 须被正确消费（第四维判据）——按 D4-29 现有 dict/list-store 消费形态对齐（转置 store 是 list `[{id,...}]`，mirror base 须以 list 保留、merge 基线非空）。

## 组件与接口

### 新增文件
- `backend/app/services/workpaper_sync/phase5_transposed_sheet.py`：`TransposedSheetSpec` dataclass + 通用 `materialize_transposed_workbook(bytes, payload, *, spec)` / `extract_transposed_workbook(bytes, *, spec)` / `build_store_projection(payload, *, contract, spec)` / `merge_projection_into_store(*, projection, base_payload, spec)` / `sheet_payload(spec)` / `resolve_managed_sheet(bytes, *, spec)`。
- `backend/app/services/workpaper_sync/transposed_registry.py`：`REGISTRY` + `resolve_transposed_specs(contract)`。
- `backend/app/services/workpaper_sync/phase5_d4_12_contract.py`：`SPEC_D412` + 契约装配 helper。
- `backend/tests/workpaper_sync/test_d4_12_contract.py`、`test_transposed_registry.py`、`test_d4_12_transposed_roundtrip.py`、`test_d4_12_mirror_consume.py`。
- 前端守卫 `d4ContractSyncHostWiring.spec.ts`。
- 变异 `backend/scripts/diagnose/mutate_d4_12_transposed_guards.py`。

### 改动文件（GENERALIZE，主控 §5.3 共享锁）
- `phase5_d4_29_customer_detail.py`：常量搬进 spec、函数改委托通用引擎（薄壳），导出名保留。
- `adapters/excel.py`：4 处旁路从 `if is_enabled` 单例改为 `for spec in resolve_transposed_specs` 遍历分派。
- `phase5_d4_revenue_detail.py`：契约装配加 D4-12（instrumentation_specs / sheet_payload / sibling store / digest 断言，只加不动既有）。
- 契约 `d4.revenue_detail.json`（generate --apply 落盘）。
- `D4TabContract.vue` + `GtD4OperatingRevenue.vue`（前端接桥 + 宿主登记）。
- instrumentation 注入路径（D4-12 definedName + 载体行）。
- `docs/operations/d4-bidirectional-writeback-inventory.md`（收口）。

## 错误处理
- definedName 非唯一/非 workbook-scope/几何漂移 → fail-closed 窄异常（复用 D4-29 `resolve_managed_sheet` 校验）。
- 载体行未 hidden / carrier 非 prefix / 字段格含公式 → extract fail-closed。
- 合同 id 含 `/~{}` 或重复 → `_payload` 拒绝。
- rematerialize 抛 `RoundtripEquivalenceError`/`FooterAnchorDriftError`/`MaterializeSoftTimeoutError` → 未落地，不得提高 soft_limit 过关。

## 测试策略

### Properties
- **Property 1（D4-29 逐字节零回归）**：泛化后 D4-29 materialize 产物 sha256 == 泛化前；extract 逐字段 == 泛化前；mapping_digest 逐字符不变。**Validates: 1.4**
- **Property 2（注册表分派正确）**：`resolve_transposed_specs` 对含 d4-29-managed 的 contract 命中 SPEC_D429、含 d4-12-managed 命中 SPEC_D412、两者都含则都命中、都不含返空。**Validates: 1.2, 1.3**
- **Property 3（D4-12 转置往返闭合）**：SPEC_D412 materialize→extract 逐字段等（21 字段 × N 合同，含空值/占位空列/扩列）。**Validates: 3.3, 3.4, 3.4a**
- **Property 4（stable_key/store 形态）**：stable_key = `contract_inspection_transposed/{id}/{field}`；row_key=id；契约 parse 含 d4-12-managed 且 layout 转置。**Validates: 3.2, 3.5**
- **Property 5（消费侧第四维）**：`oo_to_html` mirror 对 `D4-12-contracts-v2` 以 list base 消费、applied>0 时不抹 HTML-only、不静默投空。**Validates: 6.2**
- **Property 6（不打挂 entry）**：契约加 D4-12 后同 entry D4-2/3/29 store-projection 仍 200。**Validates: 3.6**
- **Property 7（首列 B 不误用 C）**：SPEC_D412.first_entity_column=B；materialize 写 B 列起、不写 A（字段标签列受保护）。**Validates: DEC-4 / 3.1, 3.3**
- **Property 8（materialize ≤120s soft_limit 不提高）**：加 D4-12 后 rematerialize 不抛 SoftTimeout。**Validates: 4.3**

### 变异反证（≥4 锚点四态 RED）
1. 泛化改回 D4-29 单例（注册表只认 D4-29）→ D4-12 命中断言 RED。
2. first_entity_column 改回 C → D4-12 往返/写列 RED。
3. 去 identity carrier hidden 强校验 → extract 松动 RED。
4. 契约去 d4-12-managed → parse/契约守卫 RED。
（每条变异 D4-29 回归须保持绿，证明泛化不牵连。）

## 部署与回滚
- 泛化改动独立 commit + tag（防回滚），先跑 D4-29 全回归再接 D4-12。
- 契约改动经 generate --apply 落盘 + assert_contract_file_matches_source OK 后才 provision/rematerialize。
- 落 flag 前确认契约能 parse + 磁盘 source 一致（D4-8 非法 key 教训）。
- provider/测试/前端守卫全部 git add，收口后 `git status` 无自己的 `??`（D4-8/D4-9 HEAD 断裂教训）。
