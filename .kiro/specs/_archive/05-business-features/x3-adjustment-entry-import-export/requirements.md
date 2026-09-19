# Requirements Document

## Introduction

16 张 **X-3 调整分录汇总表**的三态导入导出接入。本 spec 是 `workpaper-import-export-lifecycle-closure`（已提交 `6c53f397`，24/25）**Task 25 的解除阻塞前置** —— 用户在「方案 A 直接删 19 个工厂模块」与「方案 B 先补齐再删」之间裁定 **方案 B**，「同一前缀只留一套实现」的收敛方向不变，但前置未满足，故单独立项。

作业面（父 spec 已实证，本 spec 直接沿用）：

`L2-3` · `L6-3` · `M1-3` · `M2-3` · `M3-3` · `M4-3` · `M5-3` · `M6-3` · `M7-3` · `M8-3` · `M9-3` · `M10-3` · `N1-3` · `N2-3` · `N3-3` · `N5-3`

（`h9` / `l7` / `l8` 的 sheet 面已被专属 router 完全覆盖，不在本 spec 作业面。）

### 缺口的精确形态 —— 能力是「两个半套」，而 catalog 只有一个 `api_prefix` 字段

本轮探针（`app.routes` 运行期 + `IE_ADAPTER_REGISTRY` 实注册，非源码 grep）得到一个 **16×16 完全互补**的矩阵：

| 判据 | 工厂前缀 `l2` / `m1` / … | 专属前缀 `l2-interest-payable` / … |
|---|---|---|
| 在 `IE_ADAPTER_REGISTRY`（批量通路） | **16 / 16 ✓** | **0 / 16 ✗** |
| 运行期三态 HTTP 端点（单份 UI 通路） | **0 / 16 ✗** | **16 / 16 ✓** |

catalog 的 `import_export.api_prefix` 是**同一个字段**同时驱动这两条通路（bulk 按它查 `IE_ADAPTER_REGISTRY`，前端 registry 生成器按它拼 HTTP 路径）。⇒ **无论填哪一个，都只能通一半**。这才是缺口的本体，而非「功能没写」。

运行期基线（本轮复算，与父 spec Task 25 记录一致）：三态端点分组 **107** · 三态齐全 **100** · `IE_ADAPTER_REGISTRY` **97** 键 · catalog **1215** sheet / **337** 启用 I/E。

### 缺陷 A — 工厂模块声明的 `item_id` 与前端真键 **0 / 16 命中**

19 个工厂模块的 `_SPECS` 把 X-3 的 `item_id` 一律声明为 `{X}-3-adj-entries`。前端逐个核实（读 `{X}TabAdjustment.vue` + `use{X}Adjustment.ts` 的 `persistEntries` / `restoreEntries` 实际读写路径）：

| 键形态 | wp_code | 实测持久化键 | 写入列 |
|---|---|---|---|
| 单键 JSON 数组（双前缀） | L2-3 | `L2-L2-3-entries` | `remark` |
| 逐行逐字段（双前缀） | L6-3 · M1-3 · M2-3 · M3-3 | `{X}-{X}-3-entry-{n}-{field}` | `remark` |
| 逐行逐字段 + 整行 JSON（单前缀，**双写**） | M4-3 · M5-3 · M6-3 · M7-3 · M8-3 · M9-3 · M10-3 | `{X}-3-entry-{n}-{field}` **且** `{X}-3-entry-{n}-data` | `remark` |
| 单键 JSON 数组 | N1-3 · N2-3 · N3-3 | `{X}-3-entries` | **`conclusion`** |
| 单键 JSON 数组 | N5-3 | `N5-3-entries` | 待确证 |

⇒ `{X}-3-adj-entries` 在前端全库（排除 `__tests__`）**零命中**。若照抄工厂 `specs` 进 catalog（父 spec `fix_acnr_catalog_ie_gap.py` 的 `SAFE` 档 AST 直取路径），**16 张 sheet 全量数据错位**：导出读空、导入写进无人读的键。

两处附加事实：

- **写入列不统一**：M 族写 `remark`，N1/N2/N3 写 `conclusion`。工厂 `create_cycle_import_export_router` 的 `storage_field` 默认值是 `conclusion` ⇒ 只改 `item_id` 不改 `storage_field`，M 族仍写错列（最隐蔽的一类错位）。
- **M4~M10 是双键族并存**：`saveBatch` 写 10 个 per-field 键，`debouncedSave` 另写 `-data` 整行 JSON，两族都落 `remark`；而 `restoreEntries()` **只读 `-data`**。导入若只写 per-field 族，界面读不到；只写 `-data` 族，进度统计与跨表取数读不到。

### 缺陷 B — 既有契约清单记的是**复核键**，不是数据键（12 / 16 记错）

平台已有调整分录键对齐的单一真源：`backend/data/adjustment_ie_contract.json`（61 KB，`sheets` 14 条 aligned + `exempt` 65 条），由 archived spec `adjustment-import-export-contract` 建立，双侧守卫 = 后端 `test_*` + 前端 `adjustmentIeContract.spec.ts`。其 `_source` 已钉死**对齐方向铁律**：值一律以前端实测持久化键为准，后端向前端对齐，不启用 `dual_write`。

16 个目标在该清单里的现状：**15 条已登记于 `exempt`（`kind = no_backend_spec`）· `L6-3` 缺登记**。而已登记的 15 条里有 11 条的 `observed.frontend_keys` 是错的：

| wp_code | 条数 | 清单记录 | 实际身份 | 真实数据键 |
|---|---|---|---|---|
| L2-3 · M1-3 ~ M10-3 | **11** | `{X}-3-adjustment`（M8-3 另记 `M8-3-adjustmentNote`） | **`openReviewDialog()` 的复核弹窗 section 键** | 见缺陷 A 表 |
| N1-3 · N2-3 · N3-3 · N5-3 | 4 | `{X}-3-entries` | 数据键 ✓ | 一致 |
| L6-3 | 1 | 未登记 | — | `L6-L6-3-entry-{n}-{field}` |

成因已定位：清单构建时的提取器只识别**引号字面量**与 `ITEM_PREFIX` 拼接两种形态，不识别 `` `${X}-3-entry-${n}-${field}` `` 这种**模板字面量逐字段**形态；该形态在文件里唯一可见的 X-3 字面量恰好就是复核键 ⇒ 被当成数据键收录。⇒ 本 spec 必须先修提取判据，再改清单，不能直接采信 `observed`。

### 缺陷 C — 列面三套：源模板 10 列 / 前端 10 键 / 工厂 7 列

逐 sheet 读源模板（`backend/wp_templates/`，openpyxl 直读，16 张全部命中）：**16 张 X-3 的列头一律在第 5 行、一律 10 列，字面量逐字一致**：

`调整事项说明` · `类别（报表调整/账项调整/其他）` · `报表项目` · `科目名称` · `附注项目` · `……` · `借方调整金额` · `贷方调整金额` · `索引` · `备注`

对比工厂模块的 `_ADJ_HEADERS`（7 列）：**缺 `报表项目` · `附注项目` · `……`**。而前端行模型恰好含 `report`（报表项目）与 `note`（附注项目）。⇒ 按工厂列面导出，往返会丢这两列用户已填的内容。

模板侧另有三处已知事实，须登记而非「顺手修」：

- `L2-3` / `L6-3` 的 sheet 维度延伸到 K 列（其余 14 张到 J 列），第 5 行仍是同样 10 个标签。
- `N3-3` 的 sheet 第 2 行标题写作「递延所得税**资产**调整分录汇总表」（应为负债），第 3 行「编制人：」重复出现两次 —— **源模板笔误**。
- tab 名不统一：`应付利息调整分录汇总L2-3` / `调整分录汇总M4-3` / `调整分录汇总表N2-3`（N 族多「表」字）。catalog 的 `sheet_name` 与之逐字一致，是可用真源。
- 参考副本目录 `基础数据/致同通用审计程序及底稿模板（2025年修订）/` **在本仓库不存在**（全盘实测），故本 spec 的源模板真源唯一 = `backend/wp_templates/`，无需两处比对 size。

### 顺带发现（同源缺陷，须显式处置）

以 catalog 的 47 条「`class_code = F-调整分录` 且已启用 I/E」为作业面，把 `item_id` 与前端生产代码（排除 `__tests__`）交叉核验：**31 条找得到消费方，16 条找不到**。抽样校准确证其中至少一条是真错位 —— `K3-3`：catalog 记 `K3-3-rows`，前端 `K3TabAdjustment.vue` 是 `const ITEM_PREFIX = 'K3-3-adj'` + `` `${ITEM_PREFIX}-entries` `` ⇒ 真键 `K3-3-adj-entries`，且 `adjustment_ie_contract.json` 的 `sheets.K3-3` 记的正是 `K3-3-adj-entries`。⇒ **catalog 与契约清单彼此不一致，catalog 侧是错的**。

这 16 条是**已上线的静默数据错位**，不是本 spec 引入的。本 spec 不修它们的行为，但必须**核验并登记**，否则本 spec 的守卫要么把错值锁成基线（违反「禁止把错值锁成基线」），要么绕开它们（下一轮重复勘查）。

### 边界表 —— 只读不改

| 文件 / 目录 | 处置 | 理由 |
|---|---|---|
| `backend/wp_templates/**` | **只读** | 全平台共享模板库原件，一旦写入即跨项目污染（父 spec R6 已定） |
| `.github/workflows/governance-checks.yml` | **追加挂载，不重排** | 6 个 active spec 全部提及，最高并发争用文件 |
| `backend/data/note_template_*.json` | **不改** | 与本 spec 无关，回退高发 |
| L2 / L6 的业务表（`L2-2`/`L2-4`/`L6-2`/`L6-4`） | **不改** | active spec `l-cycle-extraction-formula-and-disclosure-completion`（3/26）在该半径内 |
| `_h5` · `_h7` · `_l1` · `_l3` · `_l4` · `_l5` · `_n4` 七个工厂模块 | **不删不当空缺口** | 未被 `include_router` 但前缀被 catalog 声明、adapter 经其直调闭包 ⇒ 是活代码 |
| 父 spec 已交付的 24 项 | **不回退** | 零回归按「当前态 → 施加改动 → 对照」判定 |

### 已知不做（显式登记）

| 项 | 理由 |
|---|---|
| 修 47 条中那 16 条已上线错位的**行为** | 属既有缺陷，半径与本 spec 不同；本 spec 只核验 + 登记 + 建 stale 检测 |
| 统一 M4~M10 的双键族（收敛成单一键族） | 改前端存储结构属独立决策（父族 spec 里 K12-3 那类改动由用户单独拍板） |
| 修 `N3-3` 源模板标题笔误 | 源模板只读；登记为已知源缺陷 |
| 把 `……` 占位列规范化为「摘要」 | 源模板字面量，逐字节不变优先 |
| 删除 19 个工厂模块 | 父 spec Task 25 的作业面；本 spec 只交付「能力等价」证明使其可执行 |
| `h9` / `l7` / `l8` | sheet 面已被专属 router 覆盖，不在作业面 |

---

## Glossary

- **X-3**：各循环的「调整分录汇总表」sheet，本 spec 作业面为其中 16 张。
- **三态端点**：`export-template`（空白模板）/ `export-data`（含数据）/ `import-data`（回传）。
- **工厂前缀**：`create_cycle_import_export_router(api_prefix=…)` 声明的短前缀（`l2` / `m1` / …），其 router **从未被 `include_router`**，运行期零端点。
- **专属前缀**：`backend/app/routers/{name}.py` 中已注册 router 的长前缀（`l2-interest-payable` / …），运行期三态齐全，URL 形态 `/api/{prefix}/{wp_id}/{suffix}`。
- **数据键**：`checklist_responses.item_id`，由前端 `persistEntries` 写、`restoreEntries` 读。**唯一的 `item_id` 真源。**
- **复核键**：`openReviewDialog(sectionId)` 的第一参，只驱动复核弹窗，**不是数据落点**。
- **中央同步键**：`useAdjustmentCentralSync({ itemId })` 的 `itemId`，是集中调整登记的 `source_ref` 组成部分，**不是数据落点**。
- **三重键**：`item_id` + `storage_field` + `field_keys`。三者须同时对齐，只对齐 `item_id` 仍会写错列。
- **契约清单**：`backend/data/adjustment_ie_contract.json`，调整分录键对齐的既有单一真源，含 `sheets`（已对齐）/ `exempt`（豁免，带 `kind` + `reason`）两段。
- **`Key_Ledger`**：本 spec 交付的 16 张 X-3 逐 sheet 键台账，含 `item_id` / `storage_field` / `field_keys` / 取得依据（provenance）。
- **`X3_Exporter`**：产出 X-3 的 `export-template` 与 `export-data` 两态 xlsx 的实现（端点 + service）。
- **`X3_Importer`**：解析 X-3 回传 xlsx 并写 `checklist_responses` 的实现（端点 + service）。
- **`Catalog_Registrar`**：本 spec 交付的 catalog `import_export` 段登记脚本，形态对齐既有 `backend/scripts/fix/fix_acnr_catalog_ie_gap.py`。
- **`Bulk_Adapter`**：`IE_ADAPTER_REGISTRY[api_prefix]` 的 `AdapterSpec`，**直调**模块内端点函数（不经 HTTP）。
- **`no_adapter` 静默跳过**：`bulk_export_service` / `bulk_import_service` 对未注册 `api_prefix` 走 `except KeyError` → `skip_reason=no_adapter`，仅一条日志，用户拿到的 ZIP 静默少 sheet。
- **`Selected_Route`**：本 spec 设计阶段裁定的接入路线（候选：接专属 router / 走 catalog + adapter / 二者组合）。
- **`Registry_Generator`**：`backend/scripts/fix/gen_cycle_import_export_registry.py`，从 catalog 派生前端 `cycleImportExportRegistry.generated.ts`；既有 10 个手写 key 由前端 `MANUAL_OVERRIDES` 后置覆盖。
- **`Guard_Suite`**：本 spec 交付的守卫集合（后端 pytest + 前端 vitest）。
- **`Change_Set`**：本 spec 施加的全部代码与数据文件改动。
- **`Equivalence_Proof`**：本 spec 交付的「16 张 sheet 能力由非待删模块提供」的实证制品。
- **`Deviation_Registry`**：本 spec 交付的已知偏差登记表（catalog 现值 / 契约清单现值 / 前端实测值三列）。
- **`Acceptance_Run`**：本 spec 的验收执行（真实库往返 + 浏览器实测）。
- **变异检验四态**：`RED`（打红且正是预期那条测试）/ `GREEN`（守卫缺陷）/ `ANCHOR-MISS`（锚点未命中或命中多处）/ `WRONG-TEST`（打红但不是预期项）。

---

## Requirements

### Requirement 1: 路线裁定的可验证判据

**User Story:** 作为维护者，我要路线选择由可复算的判据裁定，而不是凭「哪个改动小」，这样下一轮回看时能重算同一个结论。

#### Acceptance Criteria

1.1. THE Selected_Route SHALL 用同一个 `api_prefix` 取值同时打通单份 UI 通路与批量通路。
1.2. WHEN 路线裁定完成 THEN THE Selected_Route SHALL 对 16 张 sheet 逐张给出「哪个 `api_prefix` 提供运行期 HTTP 端点」与「哪个 `api_prefix` 命中 `IE_ADAPTER_REGISTRY`」两列实测值。
1.3. THE Selected_Route SHALL 说明施加后 19 个工厂模块能否被删除，以及删除后批量作业面是否等量。
1.4. IF 裁定结果使 19 个工厂模块成为批量通路的必需依赖 THEN THE Selected_Route SHALL 显式记录该冲突及其处置。
1.5. THE Selected_Route SHALL 复用既有三态端点族与既有 `Bulk_Adapter` 机制（现存实现共两套，本 spec 不增第三套）。
1.6. THE Selected_Route SHALL 使「同一 `api_prefix` 下已有的非 X-3 sheet」的导入导出产物逐字节不变。
1.7. WHERE 单份通路与批量通路无法用同一 `api_prefix` 打通，THE Selected_Route SHALL 记录改哪一侧的键面并给出该改动的影响面清单。

### Requirement 2: `item_id` 与 `storage_field` 逐 sheet 确证

**User Story:** 作为审计师，我导出的调整分录要是我在界面上填的那些行，导入回去也要出现在同一张表里，不能写进一个界面读不到的键。

#### Acceptance Criteria

2.1. THE Key_Ledger SHALL 为 16 张 sheet 各给出一条记录，含 `item_id` / `storage_field` / `field_keys` / 取得依据。
2.2. THE Key_Ledger 的取得依据 SHALL 取自「前端 `persistEntries` 写路径与 `restoreEntries` 读路径的实际键」「源模板列头」「人工核」三者之一，并逐条标明来源文件与符号名。
2.3. THE Key_Ledger 的每条 `item_id` SHALL 有一处前端读写路径作为直接依据（`{X}-3-adj-entries` 已实测 0 / 16 命中前端，不构成依据）。
2.4. THE Key_Ledger SHALL 把复核键与中央同步键排除在 `item_id` 候选之外。
2.5. WHERE 某 sheet 的前端读路径键与写路径键不同（M4-3 ~ M10-3 的 per-field 族与 `-data` 族并存），THE Key_Ledger SHALL 两族都记录并标明界面读的是哪一族。
2.6. IF 某 sheet 的 `item_id` 无法从前端代码确证 THEN THE Key_Ledger SHALL 把该 sheet 标为待人工核并排除在施工作业面之外。
2.7. THE Key_Ledger 的 `storage_field` SHALL 取前端实际写入列（实测 M 族 `remark` / N1·N2·N3 `conclusion`），工厂默认值 `conclusion` SHALL 仅在与前端实测一致时采用。
2.8. WHEN 前端持久化键或写入列发生改名 THEN THE Guard_Suite SHALL 打红。

### Requirement 3: 列面对齐源模板

**User Story:** 作为审计师，导出的表要和底稿上那张表长得一样，我填在「报表项目」「附注项目」里的内容传回来不能丢。

#### Acceptance Criteria

3.1. THE X3_Exporter 的列头 SHALL 取源模板 `backend/wp_templates/` 对应 X-3 sheet 第 5 行的 10 个标签。
3.2. THE X3_Exporter 的列集合 SHALL 与源模板第 5 行等势（工厂模块的 7 列 `_ADJ_HEADERS` 缺 `报表项目` / `附注项目` / `……`，不构成列面真源）。
3.3. THE Key_Ledger SHALL 为每一列登记其对应的前端行模型字段。
3.4. IF 某列在前端行模型中无对应字段 THEN THE Key_Ledger SHALL 登记该列为已知缺口并说明导入时的处置。
3.5. WHERE 前端行模型存在源模板未表达的字段（如 AJE / RJE 的 `type`），THE Key_Ledger SHALL 记录其导出与导入两侧的处置方式。
3.6. WHEN 实现中出现源模板第 5 行不存在的列 THEN THE Guard_Suite SHALL 打红。
3.7. THE Guard_Suite 比对列头时 SHALL 用 openpyxl 直读源模板取值，源码字符串 SHALL 仅作为被比对的一方。
3.8. THE X3_Exporter 的 sheet 名 SHALL 取 catalog `sheet_name`（与源模板 tab 名逐字一致，实测 N 族多「表」字、L2 带业务前缀）。

### Requirement 4: 端点接受 `sheet` 参数

**User Story:** 作为审计师，我在 X-3 页点导出，导出的要是 X-3 这张表，不能是同一底稿的别的表。

#### Acceptance Criteria

4.1. THE X3_Exporter 与 THE X3_Importer 的三态端点 SHALL 各自声明 `sheet` 参数并按其值分派到对应 sheet。
4.2. IF 端点收到未登记的 `sheet` 值 THEN THE X3_Exporter SHALL 返回可读错误。
4.3. THE `l2-interest-payable` 与 `m1-dividends-payable` 的三态端点 SHALL 接受 `sheet` 参数（实测这两个前缀的六个 handler 签名均无 `sheet`，FastAPI 对未声明的 query 参数静默丢弃）。
4.4. THE 其余 14 个专属前缀的 sheet 白名单 SHALL 含各自的 X-3，且该白名单 SHALL 有唯一真源。
4.5. WHEN 前端 registry 为某前缀声明多于一个 sheet 而该前缀后端未声明 `sheet` 参数 THEN THE Guard_Suite SHALL 打红。
4.6. THE `SHEET_AGNOSTIC_PREFIXES` 基线规模 SHALL 保持不大于现值 1（`{"l4"}`）。
4.7. IF 上传文件的 sheet 与请求的 `sheet` 不一致 THEN THE X3_Importer SHALL 在写库前返回可读错误。

### Requirement 5: 登记顺序 —— 先适配器、再 catalog

**User Story:** 作为审计师，我批量导出拿到的 ZIP 里不能静默少表。

#### Acceptance Criteria

5.1. WHEN 某 `api_prefix` 尚未在 `IE_ADAPTER_REGISTRY` 注册 THEN THE Catalog_Registrar SHALL 拒绝把该前缀写入 catalog。
5.2. THE Catalog_Registrar SHALL 只填 16 张目标 sheet 既有条目的 `import_export` 段（实测 16 张在 catalog 均已有条目、`import_export` 均为 `null`，故无需新建条目）。
5.3. THE Catalog_Registrar SHALL 为每张 sheet 写入取自 Key_Ledger 的 `enabled` / `api_prefix` / `item_id` / `storage_field`。
5.4. WHEN Catalog_Registrar 二次执行 THEN 文件内容 SHALL 零变更。
5.5. IF 写盘前 catalog 的 JSON round-trip 与磁盘内容不一致 THEN THE Catalog_Registrar SHALL 拒绝写盘（防重排整个文件与并发会话互相回退）。
5.6. THE Catalog_Registrar SHALL 提供 `--check` / `--dry-run` / `--apply` 三态，其中 `--check` SHALL 以退出码表达收口状态供 CI 判定。
5.7. WHEN 批量导出遇到本 spec 登记的 16 张 sheet THEN THE Bulk_Adapter SHALL 产出 xlsx 且 `skip_reason` SHALL 为空。
5.8. THE Catalog_Registrar SHALL 把无法登记的 sheet 连同理由写入显式登记表。

### Requirement 6: UI 可达

**User Story:** 作为审计师，我要在 X-3 页面上看得到导入导出入口，而不是只有批量包里才有。

#### Acceptance Criteria

6.1. WHEN catalog 登记完成 THEN THE Registry_Generator SHALL 把 16 张 sheet 派生进 `cycleImportExportRegistry.generated.ts`。
6.2. THE Registry_Generator SHALL 使 `MANUAL_OVERRIDES` 接管的既有 10 个 key 逐字节不变。
6.3. THE 16 张 sheet 的导入导出下拉 SHALL 挂载在各自 `{X}TabAdjustment.vue` 的渲染树内（仅被 import 而无渲染宿主视为未挂载）。
6.4. THE 下拉传给后端的 `sheet` 值 SHALL 与 catalog `sheet_code` 一致。
6.5. WHEN 用户在 X-3 页导入成功 THEN 界面重载后 SHALL 显示导入的行。
6.6. WHERE 某 sheet 的界面读路径只读 `-data` 族（M4-3 ~ M10-3），THE X3_Importer SHALL 写入该族。
6.7. IF 导入后界面读不到数据 THEN THE Acceptance_Run SHALL 判为不通过（接口返回 200 不构成通过判据）。
6.8. THE 前端 registry 条目的 `apiPrefix` SHALL 与后端 router 前缀逐字一致，并由 Guard_Suite 双向锁死。

### Requirement 7: 契约清单收口

**User Story:** 作为维护者，我要调整分录键的登记表说的就是代码里真实发生的事，而不是记了一个复核键。

#### Acceptance Criteria

7.1. THE Key_Ledger SHALL 以既有契约清单 `backend/data/adjustment_ie_contract.json` 为落点（该文件已是平台唯一键登记真源）。
7.2. THE 16 张 sheet SHALL 出现在契约清单 `sheets` 段（含实测缺登记的 `L6-3`）。
7.3. THE 契约清单中 11 条把复核键当数据键的 `observed` SHALL 改为实测数据键（L2-3 与 M1-3 ~ M10-3）。
7.4. THE 契约清单的键提取判据 SHALL 识别模板字面量逐字段形态 `` `${X}-3-entry-${n}-${field}` ``。
7.5. WHEN 提取判据修正后重扫前端 THEN 契约清单每条 `observed` SHALL 与重扫结果一致。
7.6. THE 契约清单既有三条铁律 SHALL 保持不变：对齐方向为后端向前端对齐、`dual_write` 保持停用、`field_keys` 为对齐完成后的期望值。
7.7. WHEN 契约清单改动后 THEN 前端守卫 `adjustmentIeContract.spec.ts` 与后端守卫 SHALL 全绿，且两侧断言基准 SHALL 仍是该同一份清单。
7.8. THE 契约清单 `sheets` 段条目数 SHALL 只许上调，`exempt` 段 `kind = no_backend_spec` 的条目数 SHALL 只许下调。

### Requirement 8: 同源缺陷核验

**User Story:** 作为维护者，我不要本 spec 的守卫把已经错了的值当成正确基线锁死。

#### Acceptance Criteria

8.1. THE Guard_Suite SHALL 逐条判定 catalog 中全部 `class_code = F-调整分录` 且已启用 I/E 的条目（实测 47 条）的 `item_id` 在前端生产代码中是否有消费方。
8.2. THE Guard_Suite 核验前端消费方时 SHALL 排除 `__tests__` 与 `*.spec.ts`（测试里出现不等于生产消费）。
8.3. IF catalog 的 `item_id` 与契约清单同一 sheet 的 `item_id` 不一致 THEN THE Guard_Suite SHALL 打红，或 THE Deviation_Registry SHALL 收录该条并附理由。
8.4. THE Deviation_Registry SHALL 逐条给出 catalog 现值、契约清单现值、前端实测值三列。
8.5. THE Deviation_Registry SHALL 逐条区分「真错位」与「探针假阴性」，并给出可复算的判定方法。
8.6. THE Guard_Suite 的基线断言 SHALL 只收录已确证正确的值（已判定为错位的值改由 Deviation_Registry 承载）。
8.7. WHEN 某条已知偏差被修正 THEN THE Guard_Suite SHALL 要求 Deviation_Registry 条目数同步下调。

### Requirement 9: 解除父 spec Task 25 的阻塞

**User Story:** 作为维护者，我要本 spec 结束时能明确说出「Task 25 现在可以执行了」，并且这句话有实证支撑。

#### Acceptance Criteria

9.1. WHEN Change_Set 施加完成 THEN THE Equivalence_Proof SHALL 逐张给出 16 张 sheet 的三态能力由非待删模块提供的运行期实证。
9.2. THE Equivalence_Proof SHALL 覆盖单份通路与批量通路两侧，判据 SHALL 是「产物含数据」而非「端点存在」。
9.3. THE Equivalence_Proof SHALL 给出父 spec Task 25 施加后应下调的各项基线数值。
9.4. IF Change_Set 使某个待删模块成为运行期依赖 THEN THE Equivalence_Proof SHALL 把该模块记为应从 Task 25 删除清单移出，并附理由。
9.5. THE Equivalence_Proof SHALL 复核父 spec 记录的「7 个活代码模块」判定仍成立，判定 SHALL 按模块路径而非导入别名。
9.6. THE Change_Set SHALL 保留全部工厂模块（删除属父 spec Task 25 的作业面）。

### Requirement 10: 守卫与验收

**User Story:** 作为维护者，我要这 16 张表的能力不会在下一轮改动中静默退化。

#### Acceptance Criteria

10.1. THE Guard_Suite SHALL 覆盖五类不变量：键三重对齐 / 列面对源模板 / `sheet` 参数可达 / catalog 与适配器登记顺序 / UI 有渲染宿主。
10.2. WHEN 对 Guard_Suite 的任一条判据施加对应变异 THEN 该判据 SHALL 打红。
10.3. THE 变异检验结果 SHALL 按 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态判读（退出码单独不足以定态）。
10.4. IF 某条守卫的变异检验结果为 GREEN THEN 该守卫 SHALL 被判为有缺陷并重写。
10.5. THE Guard_Suite 的判据 SHALL 落在行为或结构上（「源码中存在某字符串」不构成充分判据）。
10.6. THE Acceptance_Run SHALL 在真实库上对 16 张 sheet 各做一次「导出模板 → 填入 → 导入 → 界面读到」的往返。
10.7. IF 真实库无合法验收对象 THEN THE Acceptance_Run SHALL 输出「无法验收」（fixture 不得替代真实对象）。
10.8. THE Acceptance_Run SHALL 包含浏览器实测，且实测写入的数据 SHALL 在验收后完整复原。
10.9. THE Acceptance_Run 判定零回归 SHALL 用「当前态 → 施加改动 → 对照」三步法（HEAD-swap 在本仓库并发度下会破坏他人未提交成果，禁用）。
10.10. THE CI job SHALL 以追加 step 的方式挂载 Guard_Suite 全部守卫。
10.11. THE Guard_Suite 中的取值层守卫 SHALL 真实执行一次取数，并把捕获到的异常记为失败态。

### Requirement 11: 边界与禁区

**User Story:** 作为并发协作者，我要本 spec 的改动半径写清楚，不会把我未提交的成果覆盖掉。

#### Acceptance Criteria

11.1. THE Change_Set SHALL 使 `backend/wp_templates/` 下全部文件逐字节不变。
11.2. THE Change_Set SHALL 使 L2 / L6 的非 X-3 业务表逐字节不变（active spec `l-cycle-extraction-formula-and-disclosure-completion` 在该半径内）。
11.3. WHEN Change_Set 需要改动共享文件 THEN 改动前 SHALL 核查其他 active spec 是否也在改该文件，且核查结果 SHALL 被记录。
11.4. THE Change_Set 对 `.github/workflows/governance-checks.yml` 的改动 SHALL 限于追加 step（既有 job 顺序保持不变）。
11.5. THE Change_Set SHALL 保留 `_h5` / `_h7` / `_l1` / `_l3` / `_l4` / `_l5` / `_n4` 七个工厂模块（其前缀被 catalog 声明、adapter 经其直调闭包，是活代码）。
11.6. WHERE Change_Set 含数据库迁移，THE 迁移文件 SHALL 置于 `backend/migrations/V*.sql` 并 SHALL 幂等（`IF NOT EXISTS`）。
11.7. IF Change_Set 含破坏性数据操作 THEN 该操作 SHALL 要求显式确认参数。
11.8. THE Change_Set SHALL 在交付前清除本 spec 产生的临时诊断产物。
