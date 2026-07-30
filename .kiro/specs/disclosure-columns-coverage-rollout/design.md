# Design Document

## Overview

把 `f2-inventory-disclosure-template-alignment` 验证过的两级表头范式推广到全部披露 Tab：

1. 给 14 个未覆盖 Tab 补 `columns`（R1）
2. 把存量压平 label 迁移为 `label` + `group`（R2）
3. 新增 `ColumnDef.flat` 显式抑制前缀推断，修掉单级表被凭空加父表头（R3）
4. 覆盖守卫升级为 CI 阻断（R4）

不新建渲染机制：链路已在 F2 端到端实测通过（附注 TAB 页签 + `项目(rowspan=2) | 期末余额(colspan=3) | 上年年末余额(colspan=3)`）。

## Architecture

```
前端
├── composables/disclosureColumnDefs.ts          R3 ColumnDef 增 flat 字段
├── composables/{h4,j1,k4..k7,l1,l3}*SyncPayload / *NoteSectionMap   R1 补 columns
├── composables/f2DisclosureSyncPayload.ts       R3 房企 3 表标 flat
└── (各 Tab 既有单测)                            R2.5 断言迁移

后端
├── app/services/note_sub_table_projector.py     R3 _extract_column_groups 识别 flat
└── scripts/check/check_disclosure_columns_coverage.py   R4 --strict + allowlist 原因

CI
└── .github/workflows/governance-checks.yml      R4 挂守卫
```

### 分批策略

14 个 Tab 分 4 批，每批一个循环族，批内「补 columns → 跑该循环单测 → 跑覆盖守卫」闭环：

| 批 | Tab | 说明 |
|---|---|---|
| 1 | L1 / L3（4 个） | 债务循环，表结构相对简单，作为范式样板 |
| 2 | K4 / K5 / K6 / K7（7 个） | 管理循环，同族列结构相似可复用 helper |
| 3 | J1（2 个） | 职工薪酬，已有 `j1NoteSectionMap` 可挂载 |
| 4 | H4（1 个） | 固定资产，单 Tab 收尾 |

先批 1 打样并固化 helper 写法，再批量推进，避免 14 个各写一套。

## Components and Interfaces

### R3 — `ColumnDef.flat`

```ts
export interface ColumnDef {
  key: string
  label: string
  is_label?: boolean
  align?: 'left' | 'center' | 'right'
  format?: 'amount' | 'percent' | 'text'
  /** 分组父表头；相邻且同 group 的列在渲染时合并为两级表头 */
  group?: string
  /**
   * 显式声明「本表为单级表头」→ 后端跳过 _infer_groups_from_headers 前缀推断。
   * 仅需标在任意一列（建议标签列）即对整表生效。
   */
  flat?: boolean
}
```

`defineColumns` 需同步透传 `flat`（该 helper 曾漏传 `group`，已在 F2 spec 修）。

后端 `_extract_column_groups(defs)` 现状返回 `None` 表示「无分组」→ 调用方回退推断。改为三态：

| 返回 | 含义 | 调用方行为 |
|---|---|---|
| `None` | 未声明任何分组信息 | 回退 `_infer_groups_from_headers`（**行为不变**） |
| `[]` | 显式声明单级（任一列 `flat: true`） | 不推断，渲染单行表头 |
| `[{group,start,span}, …]` | 显式分组 | 直接用 |

调用点改动（`project_sub_tables` 内）：

```python
col_groups = _extract_column_groups(defs)
if col_groups is None:                      # 仅"未声明"才推断
    col_groups = _infer_groups_from_headers(headers)
```

—— 现有代码已是此形态，只需让 `_extract_column_groups` 在遇到 `flat` 时返回 `[]` 而非 `None`。因此 R3.2 / R3.3 的向后兼容天然成立。

### R4 — 守卫升级

`check_disclosure_columns_coverage.py` 现为 `[WARN] 非 strict 不阻断`。增加：

- `--strict`：未覆盖 > 0 → `exit 1`
- allowlist 结构从裸清单改为 `{path: reason}`，`reason` 空/缺失视为未登记（防止用空 allowlist 绕过）
- 输出保留未覆盖清单，便于 CI 日志直接定位

`governance-checks.yml` 新增一步调用 `--strict`。

## Data Models

### 列头声明范式（批 1 打样，以 L1 上市为例）

压平写法（现状，需迁移）：

```ts
{ key: 'end_principal', label: '期末本金' },
{ key: 'end_interest',  label: '期末利息' },
```

目标写法：

```ts
{ key: 'end_principal', label: '本金', group: '期末数', format: 'amount' },
{ key: 'end_interest',  label: '利息', group: '期末数', format: 'amount' },
```

产出 `_column_groups = [{"group": "期末数", "start": 1, "span": 2}]`。

单级表：

```ts
{ key: 'project_name', label: '项目名称', is_label: true, flat: true },
{ key: 'opening', label: '期初余额', format: 'amount' },
```

产出 `_column_groups = []`（不推断）。

### 每 Tab 交付物

| 产出 | 位置 |
|---|---|
| `build{X}{Variant}Columns()` | 该循环的 `*SyncPayload.ts` 或 `*NoteSectionMap.ts` |
| `columns` 挂入 payload | `build{X}SyncPayload(...)` 的 `columns` 字段 |
| 列头断言 | 该循环既有 `__tests__/*.spec.ts` |

### R6 — 账龄标签披露口径映射（方案 A）

新增共享纯函数模块 `composables/disclosureAgingLabels.ts`（与 `disclosureColumnDefs.ts`
并列：一个管**列头**元数据、一个管**行标签**口径，关注点分离，不塞进同一文件）：

```ts
/** 账龄段 key → 披露口径标签（取自附注模板通用用词，实证：1至2年 31 次 / 2至3年 29 次…） */
export const DISCLOSURE_AGING_LABELS: Readonly<Record<string, string>> = {
  within1: '1年以内',
  y1to2: '1至2年',
  y2to3: '2至3年',
  y3to4: '3至4年',
  y4to5: '4至5年',
  over3: '3年以上',
  over5: '5年以上',
}

/** 账龄表结构行 → 附注模板字面（模板用全角空格分隔：`小 计` / `合 计`） */
export const DISCLOSURE_AGING_STRUCT_LABELS: Readonly<Record<string, string>> = {
  '小计': '小 计',
  '合计': '合 计',
  '1年以内小计': '1年以内小计：',
}

/**
 * 配置口径 → 披露口径。
 * - 命中预设段 key → 用映射表（可被 overrides 覆盖，供 per-section 差异）
 * - 自定义段（key 不在预设集合）→ 原样透传配置 label（禁止杜撰）
 * - 结构行按 label 精确匹配映射
 */
export function toDisclosureAgingLabel(
  seg: { key?: string; label: string },
  overrides?: Readonly<Record<string, string>>,
): string
```

**per-section 覆盖**：国企 D2 首档为 `1年以内（含1年）`（源模板 r7 + 附注模板 八、5 一致，
全模板 13 次），上市 D2 为 `1年以内`（源模板 r8 + 附注模板 五、5 一致，全模板 24 次）。
差异**不改共享表**，由各循环 `*NoteSectionMap` 声明：

```ts
// d2NoteSectionMap.ts
export const D2_AGING_LABEL_OVERRIDES = {
  listed: {},                              // 用共享表默认值
  soe: { within1: '1年以内（含1年）' },
} as const
```

**作用位置 = 同步载荷构建时**（`build*SyncPayload`），底稿 UI 不变（R6.6）。
这样项目账龄配置继续只服务底稿内部，审计师日常操作口径不受影响。

覆盖面：账龄表行 label + 组合分表行 label（两者都按账龄段生成）。

### R7 — 动态子表名孤儿清理

新增共享纯函数模块 `composables/disclosureSyncedTables.ts`：

```ts
/** 数据子表名（排除 `_` 元数据键） */
export function dataTableNames(subTableData: Record<string, unknown>): string[]

/**
 * 待删除表名 = 上次已同步 ∪ 变体历史遗留静态键 − 本次推送。
 * 由后端 `_drop_removed_tables` 消费（该函数已保证「本次推送的 key 绝不删」）。
 */
export function buildRemovedTableKeys(args: {
  previouslySynced?: readonly string[]
  legacyObsolete?: readonly string[]
  pushed: readonly string[]
}): string[]
```

链路（三个组件各担一环，与 R7.8「可复用纯函数」一致）：

```
D2DisclosureNoteBody.syncToDisclosureNotes()
   │ ① 构建载荷（快照带 previouslySyncedTables）
   ▼
buildD2SyncPayload()  ── buildRemovedTableKeys() ──> sub_table_data._removed_table_keys
   │ ② POST 成功
   ▼
useD2DisclosureNote.markSynced(pushedNames)  ──> 持久化 `D2-disc-{variant}-synced-tables`
   │ ③ 下次同步读回
   ▼
buildSnapshot().previouslySyncedTables
```

**静态常量去向**：`D2_LISTED_OBSOLETE_TABLE_KEYS` **保留但降级为 `legacyObsolete` 种子**
（R7.4：首次启用无持久化时仍要能清掉那两个旧表名）。不是死代码——它是历史遗留键的唯一记录，
持久化清单里永远不会出现它们。

**只读态**（R7.7）：`markSynced` 走既有 `isReadonly` 守卫直接 return；载荷侧
`previouslySyncedTables` 为空 + `legacyObsolete` 仍照旧，不引入新分支。

**为什么不放后端**：后端不知道「底稿本轮应该有哪些表」——它只看到浅合并后的并集。
差集必须由持有真相的底稿侧算出后显式上报。

### R7.5 — 基线播种（上线前既存孤儿表自愈）

上面的链路只覆盖「基线建立之后」的改名/删除：③ 读回的清单最早也只能是第一次同步推的那批，
**上线前就残留在附注里的孤儿表永远进不了差集**。底稿又无从判断附注里的历史 key 是自己推的
还是别的底稿推的（同一章节可被多张底稿推送，如 H2 明细 + H4 汇总）。

解法：给每张底稿声明**表名命名空间**，首次同步前用它过滤附注现存表名来播种基线。

```ts
// disclosureSyncedTables.ts（跨循环共享纯函数）
interface TableNamespaceSpec {
  known?: readonly string[]      // 该变体固定表名全集（含历史遗留静态旧名）
  prefixes?: readonly string[]   // 动态表名前缀，如 `组合计提项目：`
  suffixes?: readonly string[]   // 续表后缀，如 `（续：期初数）`
}
isOwnedTableName(name, spec)          // 严格谓词，宁漏不误杀
noteExistingTableNames(tableData)     // 只取 sub_table_data ∪ _sub_table_columns 的键
seedSyncedTableBaseline(tableData, spec)  // = 现存表名 ∩ 命名空间
```

```
D2DisclosureNoteBody.syncToDisclosureNotes()
   │ ⓿ syncedTableNames 为空 → getDisclosureNoteDetail(pid, year, section)
   ▼
useD2DisclosureNote.seedSyncedTablesFromNote(detail.table_data)
   │   seedSyncedTableBaseline(td, D2_TABLE_NAMESPACE[variant]) → 持久化为基线
   ▼
① 构建载荷（previouslySyncedTables 已含历史孤儿）→ 本轮即清理
```

**三条不变式**：
- **续表只认「已知表名 + 后缀」**（不接受任意表名 + 后缀），否则会吞掉别的底稿的续表；
- **前缀必须有内容**（`组合计提项目：` 本身不算表名）；
- **`_tables` 不纳入**：后端 `_drop_removed_tables` 只从 `sub_table_data` /
  `_sub_table_columns` 删，`_tables` 是读时投影/生成快照，纳入只会虚报待删键。

**幂等与降级**：清单非空 → 空操作（不发请求、不覆盖，R7.12）；附注未生成 / 读取失败 →
跳过播种但不阻断同步（R7.13）。HTTP 留在组件层，composable 只吃 `table_data`（R7.14，可单测）。

## Correctness Properties

### Property 1: columns 与 sub_table_data 键一一对应

**Validates: Requirements 1.5**

对任意披露 payload，`Object.keys(sub_table_data).filter(k => !k.startsWith('_'))` 与 `Object.keys(columns)` 集合相等。

### Property 2: 标签列唯一且居首

**Validates: Requirements 1.3**

每个子表的 `columns` 中 `is_label === true` 的列恰好 1 个，且位于索引 0。

### Property 3: group 相邻性

**Validates: Requirements 2.4**

同一 `group` 值的列在 `columns` 数组中索引连续；否则 `_extract_column_groups` 会产出错误区间。

### Property 4: `_column_groups` 区间合法

**Validates: Requirements 2.3**

各分组 `start >= 1`（不覆盖标签列）、`start + span <= len(headers)`、区间互不重叠。

### Property 5: flat 三态语义

**Validates: Requirements 3.1, 3.2, 3.3**

`_extract_column_groups`：任一列 `flat` → `[]`；有 `group` → 非空列表；既无 `group` 也无 `flat` → `None`（调用方回退推断）。

### Property 7: 账龄标签映射的全域性与保守性

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

对任意账龄段：`key` ∈ 预设集合 → 输出 ∈ 披露口径值域（不含 `-` 连字符形态）；
`key` ∉ 预设集合 → 输出恒等于输入 `label`（不改写、不杜撰）。
per-section overrides 只影响声明过的 key，其余仍取共享表。

### Property 8: 底稿显示口径不受映射影响

**Validates: Requirements 6.6**

映射仅发生在 `build*SyncPayload`；`agingRows` / 组合分表行的 `label`
（底稿 UI 数据源）在映射前后逐字节不变。

### Property 9: 孤儿键差集正确且不误删

**Validates: Requirements 7.2, 7.3, 7.4**

`buildRemovedTableKeys` 满足：
- 结果 ∩ `pushed` = ∅（本次推送的绝不删）
- `previouslySynced − pushed` ⊆ 结果
- `legacyObsolete − pushed` ⊆ 结果（含 `previouslySynced` 为空的首次场景）
- 结果无重复、顺序稳定（便于断言与审计日志）

### Property 10: 同步-持久化闭环幂等

**Validates: Requirements 7.1, 7.5, 7.6**

同一快照连续同步两次：第二次 `_removed_table_keys` 为空（上次已同步 = 本次推送）；
表名集合不变。改名一次后同步 → 旧名恰好出现一次于 `_removed_table_keys`。

### Property 11: 命名空间谓词只认领自己的表

**Validates: Requirements 7.9, 7.10, 7.11**

`isOwnedTableName` 满足：
- 本底稿本轮实际推送的每个数据子表名都被认领（不漏认 → 基线不残缺）；
- 命名空间外的任意表名（别的循环的表名、空白、`_` 元数据键）一律不认领（不误杀）；
- 「任意表名 + 续表后缀」不被认领，只有「已知表名 + 后缀」才认；
- `seedSyncedTableBaseline` 对 `null` / 非对象 / 无 `sub_table_data` 的 `table_data` 返回 `[]`。

### Property 6: 无英文字段键泄漏为列头

**Validates: Requirements 1.2**

所有 `label` 不匹配 `^[a-z_][a-z0-9_]*$`（即不是 snake_case 字段键形态）。

## Error Handling

| 场景 | 处理 |
|------|------|
| 某 Tab 源模板缺失 / 无法确认列名 | 不猜：登记 allowlist 并写明「源模板待补」，不填假列头 |
| 迁移后 `_column_groups` 与源模板不符 | 视为迁移失败，回退该表压平写法并记入遗留，不强推 |
| 同 `group` 列不相邻 | 调整 `columns` 顺序使其相邻；若因业务列序不能调整，则该表不做 group 化 |
| allowlist 缺 `reason` | 守卫视为未登记 → `--strict` 下阻断 |
| 存量 Tab 迁移引发既有单测红 | 逐条核对源模板后更新断言；断言与源模板冲突时以源模板为准 |
| 账龄段为自定义 key，无披露口径依据 | 原样透传配置 label，不猜（R6.4）；扫描守卫记入 warn 清单 |
| 某循环首档口径既非 `1年以内` 也非 `1年以内（含1年）` | 在该循环 `*NoteSectionMap` 声明 overrides，不改共享表 |
| 持久化清单丢失 / 首次启用 | 退化为仅用 `legacyObsolete` 静态种子（R7.4），不误删任何现存表 |
| 同步 POST 失败 | **不**写入 `markSynced`（否则下次会把本轮表名当"上次已同步"而误删） |

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 前端契约 | `__tests__/disclosureColumnsCoverage.spec.ts`（新） | P1 / P2 / P3 / P6 全 Tab 扫描 |
| 前端单测 | `disclosureColumnDefs.spec.ts` | `defineColumns` 透传 `flat` |
| 前端单测 | 各循环既有 `*NoteSectionMap.spec.ts` | R2.5 断言迁移 |
| 后端单测 | `test_note_sub_table_projector.py` | P5 flat 三态 + P4 区间合法 |
| 后端单测 | `test_note_word_export_sub_table.py` | 两行表头与投影一致 |
| 守卫 | `check_disclosure_columns_coverage.py --strict` | R4.1 |
| CI | `governance-checks.yml` | R4.2 |
| 实测 | Playwright（抽 1 上市 + 1 国企） | R5.4 |
| 前端单测 | `disclosureAgingLabels.spec.ts`（新） | P7 / P8 映射全域性与保守性 |
| 前端单测 | `disclosureSyncedTables.spec.ts`（新） | P9 差集正确性 |
| 前端单测 | `d2NoteSectionMap.spec.ts` | R6 D2 两版落地 + P10 闭环幂等 |
| 实测 | Playwright + DB 抽验（改名 → 同步 → 无残留 key） | R7.5 / R7.6 |

## 不做

- 不改 `_infer_groups_from_headers` 的推断算法本身（仅新增 `flat` 旁路），避免存量 Tab 静默变样
- 不动附注模板 JSON（`note_template_*.json` 的 seed 结构对齐属各循环自己的 alignment spec）
- 不为无源模板依据的表凭空补列头（走 allowlist）

---

### R8 — `sheet_name` 单一口径与漂移守卫

#### 口径链路（现状，实现已正确，测试落后）

```
{X}NoteSectionMap.ts
  X_DISCLOSURE_SHEET_NAME = { listed: '附注披露信息(上市公司)', soe: '附注披露信息(国企)' }
        │  （逐字 = DB workpaper_sheet_classification 的真实 tab 名 = 源 xlsx tab 名）
        ├──> build{X}SyncPayload().sheet_name
        │        │
        │        └──> POST /disclosure-notes/sync-from-workpaper
        │                 └──> disclosure_notes.table_data._last_sync_sheet
        │                          └──> 附注「打开同步底稿」→ GtWpRenderer ?sheet={name} 精确匹配
        │
        └──(python backend/scripts/gen_note_wp_sync_registry.py --write)──>
              backend/data/note_workpaper_sync_registry.json
                { wp_code, listed, soe, sheet_listed, sheet_soe, source_file }
```

用合成标识（`F1-note-listed`）或短名（`附注上市`）都会让 `?sheet=` 匹配不上 →
反向跳转落到底稿首个 sheet，审计师看不到自己刚同步的那张表。所以**实现改对是必须的**，
本需求只是把测试断言追平，并加守卫防止再次分叉。

#### 守卫设计

`__tests__/disclosureSheetNameRegistry.spec.ts`：

1. 读 `backend/data/note_workpaper_sync_registry.json`（路径解析方式复用
   `k1NoteSubtableContract.spec.ts` / `f1NoteSubtableContract.spec.ts` 的 `REPO_ROOT` 写法）；
2. 对每个已接入的循环，调其 `build{X}SyncPayload('listed'|'soe', …)`，断言
   `payload.sheet_name === registry[wp_code].sheet_{variant}`；
3. registry 是 `*NoteSectionMap.ts` 的**生成产物**，若不同步则报错并提示重生成命令
   —— 这样「改了 map 忘了重生成 registry」和「改了 registry 没改 map」两个方向都被拦。

覆盖面策略：守卫按 registry `entries` 驱动，新循环接入 registry 后自动纳入，
无需逐个登记；某循环尚未提供 `build*SyncPayload` 导出时跳过并计数，跳过数写入断言，
避免"静默零覆盖"。

#### Property 11: `sheet_name` 与注册表逐字一致

对任意已接入循环 `X` 与变体 `v ∈ {listed, soe}`：

```
build{X}SyncPayload(v, …).sheet_name  ==  registry.entries[wp_code=X].sheet_{v}
```

且 `registry.entries[X].sheet_{v}` 由 `gen_note_wp_sync_registry.py` 从
`{x}NoteSectionMap.ts` 的 `X_DISCLOSURE_SHEET_NAME[v]` 提取 —— 三处同源，
任一处漂移即被守卫捕获。

**反例（本需求要修掉的）**：`'F3-note-soe'`（合成标识）、`'附注上市'`（短名）。

**非目标**：不改 `sheet_name` 的实现口径，也不动 `X-note-listed` 作为 **wp_code** 的
既有用法（`_WP_CODE_OVERRIDE` / `htmlRendererRegistry` / sheet 归一化输入样本）。

---

### 批 1 列头清查：L1 / L3

> Task 5.1 产出。逐 sheet 用 openpyxl 读源模板 + 交叉验证 `附注模版/*.md`、
> `note_template_{listed,soe}.json`、`consol_note_sections_{listed,soe}.json`、
> BCD 类 md，并实跑后端 `_infer_groups_from_headers` 取推断实证。
> **未写任何实现代码**（helper 落地属 5.2）。

#### 0. 前置实测结论（先看这三条，影响 5.2 的做法）

**① 4 个 Tab 其实已经在推 `columns` —— 守卫是假阴性。**
`l1NoteSectionMap.ts` / `l3NoteSectionMap.ts` 已有 `buildCategoryColumns` /
`buildOverdueColumns` / `buildClassificationColumns` / `buildCurrentPortionColumns`
（module-private），4 个 `.vue` 均 `const { sub_table_data, columns } = buildL{1,3}SyncPayload(...)`
并把 `columns` 放进 POST body。守卫漏检有两个原因，缺一不可：

- `buildL1SyncPayload` / `buildL3SyncPayload` 不在 `COLUMN_BUILDERS` 白名单；
- 内联兜底正则是 `sub_table_data\s*:`，而这 4 处用的是**对象简写** `sub_table_data,`
  （无冒号）→ 邻近窗口检测不触发。

→ **5.2 的重点不是"从零补 columns"，而是（a）把列头校准到源模板/附注模版口径、
（b）补 `flat` / `format`、（c）让守卫认得**（导出 `buildL1{Listed,Soe}Columns` /
`buildL3{Listed,Soe}Columns` 命中 `build[A-Z]\w*Columns` 正则，即可同时满足
R1.1 与"不靠改白名单"）。

**② 源模板 8 张表全是单行表头，无一例两行。** 证据：xlsx `merged_cells.ranges`
在表头行**无跨列合并**（合并全落在标题/说明行）；`consol_note_sections_*` 对应条目
`multi_header: null`；`附注模版/*.md` 表格均只有 1 行 header。
→ 批 1 **全部标 `flat: true`**（标在标签列，整表生效），0 处 `group`。

**③ L1 上市逾期表当前被凭空加了父表头 —— 这是本批唯一的活体缺陷。**
实跑 `_infer_groups_from_headers`：

| headers | 推断结果 |
|---|---|
| `['借款单位','期末余额','借款利率(%)','逾期时间','逾期利率(%)']`（现状） | `[{'group':'逾期','start':3,'span':2}]` ← **凭空** |
| `['借款单位','期末余额','借款利率','逾期时间','逾期利率']`（附注模版口径） | `[{'group':'逾期','start':3,'span':2}]` ← 同样凭空 |
| `['债权单位','期末余额','借款利率（%）','逾期时间（月）','逾期利率']`（L1 国企附注模版 5 列） | `[{'group':'逾期','start':3,'span':2}]` ← 若将来对齐 5 列也会中招 |
| 其余 8 组（L1 分类表两版 / L3 四张表 / L3 国企 4 列方案） | `None`（列数 <4 或无共享前缀） |

现状 `columns` 已声明但**既无 `group` 也无 `flat`** → `_extract_column_groups` 返回
`None` → 调用方回退推断 → 附注侧「逾期时间 / 逾期利率」被合并到假父表头「逾期」下。
`_extract_column_groups` 三态自检同批实测：无 group/无 flat → `None`；任一列
`flat: true` → `[]`。→ 标 `flat` 即修掉。

#### 1. 源模板与附注模板定位（证据坐标）

| 循环 | 源 xlsx | 披露 sheet（xlsx tab 名） | 附注章节 | 附注模版 md |
|---|---|---|---|---|
| L1 上市 | `…/4.风险应对-实质性程序（D-N）/L 债务循环/L1 短期借款.xlsx` | `附注披露信息核对（上市公司）` | 五、33 | `上市报表附注.md` L4198~4223 |
| L1 国企 | 同上 | `附注披露信息核对（国企）` | 八、33 | `国企报表附注.md` L3337~3360 |
| L3 上市 | `…/L 债务循环/L3 长期借款.xlsx` | `附注披露信息核对（上市公司）` | 五、45 | `上市报表附注.md` L4630~4641（+ L4554 一年内到期） |
| L3 国企 | 同上 | `附注披露（国企）信息核对` | 八、49（+ 八、45） | `国企报表附注.md` L3677~3691（+ L3626 一年内到期） |

裁决口径核查：
- `note_check_preset_formulas.json` **无 L1/L3 条目**（`soe`/`listed` 两份均 0 命中）
  → 三源裁决里的「校验预设裁决者」在批 1 缺位；退到「附注模版 + note_template JSON
  + consol 印证」为准（附注是交付物）。
- `note_workpaper_sync_registry.json` **无 L1/L3 条目** → 4 个 Tab 现推
  `sheet_name: 'L1-note-listed'` 等**合成标识**，属 R8 同类漂移但未被守卫覆盖
  （守卫按 registry 驱动）。记为遗留 ⑤，不在 5.2 范围。
- BCD 类 md 只收了 L3 国企一张（`L债务循环/L债务循环底稿模板库.md` L4648~4673），
  且已被压扁（少了第二个「利率区间」列）；L1 无 md 条目。

#### 2. `L1TabDisclosureListed`（五、33，`buildL1SyncPayload({variant:'listed'})`）

`sub_table_data` 键（精确串）：`短期借款分类`、`逾期借款情况`（**条件推送**：
`overdueTableRows.length > 0` 才有键）、`_note_texts`（元数据，非表）。

**表 1 `短期借款分类`** — 源 `附注披露信息核对（上市公司）` **A7:C7 单行表头**
（该 sheet 合并区仅 `A1:E1` `A2:E2` `A15:E15` `F2:L2` `A13:C13`，表头行 7 无合并）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `category` | `项目` | note_template 五、33 t0 `headers[0]='项目'`；源 A7=`项  目`（双空格）；UI L32 `label="项目"` | `is_label: true` + `flat: true` |
| 1 | `endBalance` | `期末余额` | 源 B7；note headers[1]；UI L33 | `format: 'amount'` |
| 2 | `beginBalance` | `上年年末余额` | 源 C7；note headers[2]；UI L36 | `format: 'amount'` |

**表 2 `逾期借款情况`** — 源 **A18:E18 单行表头** → `flat`（**必须**，否则如 §0③ 被加「逾期」）

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `borrower` | `借款单位` | 源 A18；附注模版 L4218；note t1 `headers[0]`；UI L61 | `is_label: true` + `flat: true` |
| 1 | `endBalance` | `期末余额` | 源 B18；附注模版 L4218 | `format: 'amount'` |
| 2 | `rate` | `借款利率` | 源 C18 + 附注模版 L4218（**均无 `(%)`**）。UI L73 为 `借款利率(%)` → 取附注模版口径 | `format: 'percent'` |
| 3 | `overdueTime` | `逾期时间` | 源 D18；附注模版 L4218；UI L79 | `format: 'text'` |
| 4 | `penaltyRate` | `逾期利率` | 源 E18 + 附注模版 L4218。UI L85 为 `逾期利率(%)` → 同上 | `format: 'percent'` |

#### 3. `L1TabDisclosureSoe`（八、33，`buildL1SyncPayload({variant:'soe'})`）

`sub_table_data` 键：`短期借款分类`、`逾期借款情况`（条件推送）、`_note_texts`。

**表 1 `短期借款分类`** — 源 `附注披露信息核对（国企）` **A8:C8 单行表头**
（该 sheet 合并区仅 `A1:D1` `A2:D2`）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `category` | `借款类别` | 源 A8；note_template 八、33 t0 `headers[0]`；附注模版 L3341；UI L31 | `is_label: true` + `flat: true` |
| 1 | `endBalance` | `期末余额` | 源 B8；note headers[1]；UI L32 | `format: 'amount'` |
| 2 | `beginBalance` | `期初余额` | **三源冲突**：源 C8 = `年初余额`、UI L35 = `年初余额`；附注模版 L3341 + note headers[2] + consol 五-34-1 = `期初余额` → 按「附注是交付物」取 `期初余额` | `format: 'amount'` |

**表 2 `逾期借款情况`** — 源 **A16:C16 单行表头（仅 3 列）** → `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `borrower` | `债权单位` | 源 A16；note_template 八、33 t1 `headers[0]`；附注模版 L3351；UI L53。**现状 `buildOverdueColumns` 两版都写 `借款单位` → 国企侧错**（标签列头 ≠ 附注 `headers[0]` 会出孤儿列） | `is_label: true` + `flat: true` |
| 1 | `endBalance` | `期末余额` | 源 B16；附注模版 L3351 | `format: 'amount'` |
| 2 | `rate` | `借款利率（%）` | 附注模版 L3351 + note headers[2]（**全角括号**）；源 C16 = `借款利率`；UI L65 = `借款利率(%)`（半角）→ 取附注模版全角 | `format: 'percent'` |

#### 4. `L3TabDisclosureListed`（五、45，`buildL3SyncPayload({variant:'listed'})`）

`sub_table_data` 键：`长期借款`、`一年内到期的长期借款`（**无条件推送**）、`_note_texts`。

**表 1 `长期借款`** — 源 `附注披露信息核对（上市公司）` **A7:E7 单行表头**
（合并区仅 `A1:E1` `A2:E2` `F2:L2`）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 五、45 t0 `headers[0]='项目'`；源 A7=`项  目`；附注模版 L4632=`项  目`；UI L31 `label="项目"` | `is_label: true` + `flat: true` |
| 1 | `endAmount` | `期末余额` | 源 B7；附注模版 L4632；UI L34 | `format: 'amount'` |
| 2 | `endRate` | `利率区间` | 源 C7；附注模版 L4632；UI L37 | `format: 'text'` |
| 3 | `priorAmount` | `上年年末余额` | 源 D7；附注模版 L4632；UI L43 | `format: 'amount'` |
| 4 | `priorRate` | `利率区间` | 源 E7；附注模版 L4632（**与第 2 列同名，模板即如此，不去重、不加期别前缀 —— 加前缀即压平/杜撰**）；UI L46 | `format: 'text'` |

**表 2 `一年内到期的长期借款`** — 源 **A20:C20 单行表头** → `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | 源 A20=`项  目`；附注模版 L4556=`项  目`；consol 五-43-2 `headers[0]`；UI L65 | `is_label: true` + `flat: true` |
| 1 | `endAmount` | `期末余额` | 源 B20；附注模版 L4556；UI L68 | `format: 'amount'` |
| 2 | `priorAmount` | `上年年末余额` | 源 C20；附注模版 L4556；UI L71 | `format: 'amount'` |

#### 5. `L3TabDisclosureSoe`（八、49，`buildL3SyncPayload({variant:'soe'})`）

`sub_table_data` 键：`长期借款`、`一年内到期的长期借款`、`_note_texts`。

**表 1 `长期借款`** — 源 `附注披露（国企）信息核对` **A8:E8 单行表头**
（合并区仅 `A1:E1` `A2:E2`）→ `flat`。**列集三源冲突，需 5.2 定口径**：

| 来源 | 列序 |
|---|---|
| 源 xlsx A8:E8 | `借款类别` / `期末余额` / `利率区间` / `期初余额` / `利率区间`（5 列） |
| BCD md L4657 | `借款类别` / `期末余额` / `利率区间` / `期初余额`（4 列，md 重建压扁掉尾列） |
| **附注模版 L3679** + note_template 八、49 + consol 五-50-1 | `借款类别` / `期末余额` / `期初余额` / `期末利率期间（%）`（4 列） |

`note_check_preset_formulas` 无 L3 条目 → 裁决者缺位。按「附注是交付物 → 列结构随附注模版；
底稿可多留审计列，同步时投影成附注形状」，**推荐方案 A（附注模版 4 列）**：

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `借款类别` | 附注模版 L3679；note 八、49 `headers[0]`；源 A8；UI L31 | `is_label: true` + `flat: true` |
| 1 | `endAmount` | `期末余额` | 附注模版 L3679；源 B8 | `format: 'amount'` |
| 2 | `priorAmount` | `期初余额` | 附注模版 L3679；源 D8 | `format: 'amount'` |
| 3 | `endRate` | `期末利率期间（%）` | 附注模版 L3679 + note headers[3]（底稿 `rateRange(rowKey,'end')` 对位；`priorRate` 在附注侧无落点，按投影约定丢弃） | `format: 'text'` |

方案 B（保源模板 5 列 `借款类别/期末余额/利率区间/期初余额/利率区间`）会让附注侧多一列
无模板依据的期初利率 → 与附注模版/consol 双双不符，**不推荐**。**该口径需用户/5.2 确认**
（唯一需要拍板的一处；其余 7 张表无歧义）。

**表 2 `一年内到期的长期借款`** — 源 **A21:C21 单行表头** → `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | 附注模版 L3628 = `项  目`；note_template 八、45 t0 `headers[0]='项目'`；consol 五-46-1 `headers[0]`。**源 A21 与 UI L69 均为 `借款类别`** → 冲突，取附注口径 | `is_label: true` + `flat: true` |
| 1 | `endAmount` | `期末余额` | 附注模版 L3628；源 B21；UI L72 | `format: 'amount'` |
| 2 | `priorAmount` | `期初余额` | 附注模版 L3628；源 C21；UI L75 | `format: 'amount'` |

#### 6. 汇总

| Tab | 数据子表数 | 单行表头 | 两行表头 | 需标 `flat` | allowlist |
|---|---|---|---|---|---|
| `L1TabDisclosureListed` | 2 | 2 | 0 | 2（其中逾期表**修活体缺陷**） | 0 |
| `L1TabDisclosureSoe` | 2 | 2 | 0 | 2 | 0 |
| `L3TabDisclosureListed` | 2 | 2 | 0 | 2 | 0 |
| `L3TabDisclosureSoe` | 2 | 2 | 0 | 2 | 0 |
| **合计** | **8** | **8** | **0** | **8** | **0** |

**allowlist 候选：无。** 8 张表的每个 label 都能指到源模板单元格坐标或附注模版 md 行号，
无一处需要「源模板待补」。

#### 7. 遗留（超出 5.2 范围，只登记不改）

| # | 问题 | 证据 | 归属 |
|---|---|---|---|
| ① | L1 两版推送键 `逾期借款情况` 与附注模板表名不符：上市模板表名是 `借款单位`（`#### 重要的逾期借款情况` 标题被 `_is_table_title_paragraph` 丢弃，退化为 `headers[0]`）、国企模板表名是 `已逾期未偿还的短期借款情况` → 同步出孤儿 TAB | `note_template_listed.json` 五、33 `tables[1].name='借款单位'`；`note_template_soe.json` 八、33 `tables[1].name='已逾期未偿还的短期借款情况'` | 未来 L1 alignment spec（本 spec §不做：不动附注模板 JSON） |
| ② | L1 国企逾期表底稿只有 3 列，附注模板有 5 列（多 `逾期时间（月）` / `逾期利率`）→ 附注侧两列无数据来源 | 源 A16:C16 vs 附注模版 L3351 | 同上（补录入列属底稿改版，禁在补 columns 时杜撰数据列） |
| ③ | L3 `一年内到期的长期借款` 被推进 `长期借款` 所在章节：上市侧五、45 模板无此表（`variant_matrix.listed_standalone = null`，附注模版把它挂在「一年内到期的非流动负债」五、43 下）；国企侧它是**独立章节 八、45**（`account_key = yi_nian_nei_dao_qi_de_chang_qi_jie_kuan`）→ 八、45 永久空表 | `note_template_variant_matrix.json`；`consol_note_sections_listed` 五-43-2 / `_soe` 五-46-1 | 需按 R7 式章节路由改造，另立 spec |
| ④ | 4 个 Tab 的 `sub_table_data` 键随数据条件出现（L1 逾期表为空时不推键）→ R1.5「columns 与 sub_table_data 键一一对应」在空数据下仍成立（现状 `columns` 同条件构建），9.1 契约测试须覆盖「空逾期」分支 | `l1NoteSectionMap.ts` `if (overdueTableRows.length > 0)` 双处 | 5.4 / 9.1 |
| ⑤ | L1/L3 推 `sheet_name: 'L{1,3}-note-{listed,soe}'` 合成标识（R8 同类漂移），且 `note_workpaper_sync_registry.json` 无 L1/L3 条目 → R8 守卫按 registry 驱动，扫不到 | 4 个 `.vue` 的 POST body；registry 0 命中 | R8 后续（真实 tab 名见 §1 表；国企两版 tab 名还不一致：L1=`附注披露信息核对（国企）`、L3=`附注披露（国企）信息核对`） |

#### 8. 5.2 落地清单（范式样板，供批 2~4 照抄）

1. 在 `l1NoteSectionMap.ts` / `l3NoteSectionMap.ts` **导出**
   `buildL1ListedColumns()` / `buildL1SoeColumns()` / `buildL3ListedColumns()` /
   `buildL3SoeColumns()`，返回 `Record<string, ColumnDef[]>`（键 = `sub_table_data` 数据键）；
   命名命中守卫正则 `build[A-Z]\w*Columns` → 无需动 `COLUMN_BUILDERS` 白名单。
2. 标签列一律 `is_label: true` + `flat: true`（批 1 全表单行表头）；金额列 `format: 'amount'`、
   利率/利率区间列按 §2~§5 表定 `percent` / `text`。
3. 条件表（L1 逾期）保持「有数据才进 `sub_table_data` 且才进 `columns`」的成对分支。
4. 校准 §3 表 2 的 `借款单位` → `债权单位`、§3 表 1 的 `年初余额` → `期初余额`、
   §5 两表的标签列与利率列 —— 都是**改现有 label，不是新增**。
5. 跑 `python backend/scripts/check/check_disclosure_columns_coverage.py`
   确认这 4 条从未覆盖清单消失（16 → 12）。

---

### 批 1 范式模板（批 2~4 照此办）

> **Task 5.5 产出。批 2（K4~K7）/ 批 3（J1）/ 批 4（H4）逐步照抄本节，不要各自再发明形状。**
>
> 批 1 实况（2026-07-30 实测）：`l1NoteSectionMap.ts` / `l3NoteSectionMap.ts` 落地
> 4 个导出 builder + 4 个 module-private 表级 helper；契约测试
> `composables/__tests__/l1NoteSectionMap.spec.ts`（10）+ `l3NoteSectionMap.spec.ts`（12）
> = **22/22 绿**；覆盖守卫未覆盖 **16 → 12**，消失的恰是 L1/L3 那 4 个 `.vue`。

#### T0. 先清查，再写代码（照 5.1 的形状，产出写回 design）

**顺序不可颠倒**：没有逐 sheet 的单元格证据就动手写 `columns`，等于用「常识」造披露列头。
批 1 的 8 张表每个 label 都能指到「源 xlsx 单元格坐标」或「附注模版 md 行号」，allowlist 候选 0 处。

1. **逐 sheet 读源 xlsx**（openpyxl，`data_only=True`），同时读表头行的合并区间——
   **有没有跨列合并是判 1 行 / 2 行表头的第一手证据**：

   ```python
   from openpyxl import load_workbook
   wb = load_workbook(r'基础数据/…/K 循环/K5 预计负债.xlsx', data_only=True)
   ws = wb['附注披露信息核对（上市公司）']          # tab 名逐字，勿用 wp_code
   print([str(r) for r in ws.merged_cells.ranges])   # 表头行无跨列合并 → 单行表头
   for row in ws.iter_rows(min_row=1, max_row=30, values_only=True):
       print(row)
   ```

   批 1 实证：8 张表的合并区全落在标题 / 说明行（`A1:E1` `A2:E2` `A15:E15` 之类），
   表头行零合并 → 8 张全是单行表头，0 处 `group`。

2. **交叉验证四份产物**（同一张表要在四处都对上，冲突处按 T0.3 裁决）：

   | 产物 | 看什么 |
   |---|---|
   | `基础数据/附注模版/{上市,国企}报表附注.md` | 表格 header 行（**交付物口径，label 首选源**）、行数 |
   | `backend/data/note_template_{listed,soe}.json` | 该章节 `tables[].name` / `headers[]`（**表名契约 + `headers[0]` 决定标签列头**） |
   | `backend/data/consol_note_sections_{listed,soe}.json` | `multi_header`（`null` = 单行表头的第 4 方印证）、`headers[]` |
   | `backend/data/note_check_preset_formulas.json` | 该循环 `{循环}{节号}-n` 条目（**裁决者**，直接写明某列该不该有） |

   章节号从 `backend/data/note_template_variant_matrix.json` 取；同步 sheet 名从
   `backend/data/note_workpaper_sync_registry.json` 取（无条目 = R8 漂移遗留，登记不改）。

3. **三源裁决顺序（冲突时逐级下推）**：
   **校验预设 > 附注模版 md > 源 xlsx > 底稿 UI 的 `el-table-column label`**。
   附注是交付物，所以模版口径压源 xlsx；底稿 UI 只是第 4 位参考（它常年有自己的写法）。
   批 1 实际用到三次：国企分类表 `年初余额`(源 xlsx/UI) → **`期初余额`**(附注模版)；
   国企逾期表 `借款单位`(UI) → **`债权单位`**(附注模版 + `headers[0]`)；
   上市逾期表 `借款利率(%)`(UI) → **`借款利率`**(附注模版，无 `(%)`)。
   ⚠️ 批 1 **裁决者缺位**（`note_check_preset_formulas.json` 无 L1/L3 条目）才退到附注模版；
   批 2~4 若该循环有预设条目，**预设说了算**，不得越级。

4. **「指不到源就走 allowlist 写原因，禁止杜撰」**：任何一个 label 若在四份产物里都找不到落点，
   不要填「看起来对」的字；按 R4.3 在 `ALLOWLIST` 登记该文件并写明「哪一波待迁移 / 依据哪个源模板」
   （原因空白 = 未登记，`--strict` 照旧阻断）。同理，源模板只有 3 列时**不许凭空补录入列**
   （批 1 遗留 ② 就是这么被登记为遗留、而不是被"补齐"的）。

#### T1. 命名契约（决定守卫认不认）

每个循环每个变体**导出**一个 builder，返回 `Record<string, ColumnDef[]>`，
**键 = `sub_table_data` 的数据键逐字一致**：

```ts
/** L1 上市（五、33）子表列头，键 = `sub_table_data` 数据键 */
export function buildL1ListedColumns(opts: L1ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildL1Columns('listed', opts)
}
export function buildL1SoeColumns(opts: L1ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildL1Columns('soe', opts)
}
```

- 命名必须匹配守卫正则 **`build[A-Z]\w*Columns\b`**（`_BUILDER_RE`）→ 引用即判覆盖，
  **无需往 `COLUMN_BUILDERS` 白名单里加一行**。扩白名单是"绕过"，不是"覆盖"。
- 变体分支放在 module-private 的 `buildXColumns(variant, opts)` 里，两个导出只是薄壳；
  **表级 helper 也保持 module-private**（批 1：`buildCategoryColumns` / `buildOverdueColumns` /
  `buildClassificationColumns` / `buildCurrentPortionColumns`）——导出面越小，
  测试就越只能通过 payload 入口断言，不会绕过真实组装路径。
- `ColumnDef[]` 用字面量直接写即可（批 1 即如此）。走 `defineColumns()` 也行，但它是过滤器
  （历史上曾漏传 `group`，`flat` 是补上的）——字面量少一层可能丢字段的中转。

#### T2. 声明规则（表头层级 / 格式）

| 源模板形态 | 声明 | 禁止 |
|---|---|---|
| **单行表头** | 标签列 `is_label: true` + `flat: true`；**整表 0 处 `group`** | 不标 `flat`（后端会前缀反猜父表头，见 T7） |
| **两行表头** | `label` = **子列名**、`group` = **父表头**，同 group 列必须相邻；**不要标 `flat`** | 压平成 `期末账面余额` 拼接串；两级表又标 `flat`（会显式抑制成单级） |

`flat` 标在**任意一列即整表生效**，约定统一标在标签列。

`format` 映射：金额 → `'amount'`；利率 / 百分比 → `'percent'`；
时间段 / 区间 / 说明等文本 → `'text'`。批 1 实例：

```ts
// 单行表头 + 条件表（L1 上市逾期表，5 列）
return [
  { key: 'borrower',    label: '借款单位', is_label: true, flat: true },
  { key: 'endBalance',  label: '期末余额', format: 'amount' },
  { key: 'rate',        label: '借款利率', format: 'percent' },
  { key: 'overdueTime', label: '逾期时间', format: 'text' },
  { key: 'penaltyRate', label: '逾期利率', format: 'percent' },
]
```

标签列的 `label` 必须 **= 附注 `headers[0]`**，否则同步出孤儿列（批 1 修掉的
`借款单位`→`债权单位` 就是这一类）。同名列不去重、不加期别前缀（L3 上市两列都叫
`利率区间`，模板即如此，靠 `endRate`/`priorRate` 两个 key 区分；加前缀＝压平＋杜撰）。

#### T3. 条件表：`columns` 与 `sub_table_data` 必须成对进出

只要某张表是「有数据才推」，`columns` 就得走同一个 `if`，否则 Property 1（键一一对应）
在空数据分支下必破。做法 = 一个 `includeX?: boolean` 的 options 对象：

```ts
export interface L1ColumnsOptions {
  /** 逾期表是条件推送（`overdueRows` 全空时不进 `sub_table_data`）→ columns 必须成对 */
  includeOverdue?: boolean
}

function buildL1Columns(variant, opts: L1ColumnsOptions): Record<string, ColumnDef[]> {
  const columns: Record<string, ColumnDef[]> = { '短期借款分类': buildCategoryColumns(variant) }
  if (opts.includeOverdue) columns['逾期借款情况'] = buildOverdueColumns(variant)
  return columns
}

// payload 侧：同一个判据喂给两边，禁止各写一份条件
const columnsOpts: L1ColumnsOptions = { includeOverdue: overdueTableRows.length > 0 }
```

判据取**过滤后的行数**（`overdueRows.filter(...)` 之后），不是原始入参长度——
「全空行」和「空数组」要落到同一分支（批 1 的空分支断言正是喂了这两种入参）。
`_note_texts` 等 `_` 前缀键是元数据，不参与配对。

#### T4. 位置对齐：变体列集不同 → `values` 必须按变体分支

`sub_table_data` 的行是位置化 `values[]`，与 `columns` 的**非标签列顺序**逐位对应。
一旦某变体的列集与另一变体不同（少一列 / 换序），`values` 就必须跟着分支，
否则数字会**静默落到别的列**——没有任何编译期或运行期报错。

**L3 国企是这条的具体先例**：上市 4 个值列 = `期末余额 / 利率区间(end) / 上年年末余额 / 利率区间(prior)`；
国企按方案 A 只有 3 个值列 = `期末余额 / 期初余额 / 期末利率期间（%）`（附注侧无期初利率落点，
`priorRate` 被丢弃）。于是：

```ts
// values 必须与 buildClassificationColumns(variant) 的非标签列 **同序**
values: variant === 'soe'
  ? [r.endAmount, r.priorAmount, rateRange(r.rowKey || '', 'end')]
  : [r.endAmount, rateRange(r.rowKey || '', 'end'), r.priorAmount, rateRange(r.rowKey || '', 'prior')],
```

若照抄上市写法给国企，`priorAmount` 会落到「期末利率期间」列、利率字符串落到「期初余额」——
表面仍然渲染成 3 列，肉眼极难发现。所以 T5 的「位置对齐」两族断言**每批必写**。

#### T5. 测试清单（8 个断言族，每批照抄）

放在 `composables/__tests__/{x}NoteSectionMap.spec.ts`，**全部经 `build{X}SyncPayload()` 入口**
取 `{ sub_table_data, columns }`（不要直接拼假 payload，否则测不到 T3/T4 的成对与同序）。

| # | 断言族 | 要点 |
|---|---|---|
| 1 | **Property 1** 键一一对应 | `Object.keys(columns).sort()` === 数据键（`!k.startsWith('_')`）；**外加条件表空分支**：两侧同时 `toBeUndefined()`，且空数组 / 全空行两种入参都测 |
| 2 | **Property 2** 标签列唯一居首 | 每表 `is_label === true` 恰 1 个且在索引 0 |
| 3 | **Property 6** 无字段键泄漏 | `label.trim()` 非空 且 `!/^[a-z_][a-z0-9_]*$/.test(label)` |
| 4 | **单行表头 / 无 group** | 每表「至少一列 `flat === true`」且 `group !== undefined` 的列数为 0（两行表头的表反过来断：有 `group`、无 `flat`、同 group 相邻） |
| 5 | **逐字 label**（每表 1 条） | `cols.map(c => c.label)).toEqual([...])` + `cols.map(c => c.key)).toEqual([...])` |
| 6 | **负向断言**（跟着 5 写） | 对**被裁决掉的候选串**显式反断：`not.toContain('年初余额')` / `cols[0].label).not.toBe('借款单位')` / `not.toContain('priorRate')` / `toHaveLength(3)`。→ 将来谁把 label 改回错的那个，**测试立刻响**；只写正向断言的话，改错时报错信息看不出"错在退回了哪个旧口径" |
| 7 | **位置对齐（通用）** | 每行 `values.length` === 该表非标签列数（逐表逐行） |
| 8 | **位置对齐（变体重排守卫）** | 用**回显入参的桩**把顺序钉死：`const rateRange = (rowKey, period) => \`${rowKey}:${period}\`` → 断 `rows[0].values).toEqual([1000, 900, 'pledge:end'])` 且 `not.toContain('pledge:prior')`。上市侧同样断一条完整序列 |

第 8 族的桩是这套测试里最省力的一招：把函数型入参的**参数**回显成字符串，
`values` 数组一比就知道哪个值来自哪一列、哪个期别，不需要构造真实数据也能锁死列序。

#### T6. 每批收口闭环（做完就验，不要 4 批攒一起）

```powershell
# 1) 该批前端契约测试
npx vitest run src/components/workpaper/composables/__tests__/k5NoteSectionMap.spec.ts   # cwd=audit-platform/frontend
# 2) 覆盖守卫
python backend/scripts/check/check_disclosure_columns_coverage.py                          # cwd=仓库根
```

- 期望**未覆盖数恰好减少该批 Tab 数**（批 1：16 → 12，正好 4；批 2 应 12 → 5，批 3 → 3，批 4 → 2）。
  多减了 = 正则/白名单误放宽（backlog 被掩盖）；少减了 = 有 Tab 没真接上。
- **必须正向复验 `_is_covered`，不能只看"它从清单里消失了"**（消失也可能是文件改名 / 不再含
  `SYNC_MARKERS` 而被整体跳过）：

  ```python
  import importlib.util
  spec = importlib.util.spec_from_file_location('cov', 'backend/scripts/check/check_disclosure_columns_coverage.py')
  m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
  for rel in ['components/workpaper/k5/core/K5TabDisclosureListed.vue', ...]:
      p = m.FRONTEND_SRC / rel
      print(rel, p.is_file(), m._is_covered(p.read_text(encoding='utf-8')))   # 期望 True True
  ```

  批 1 实测 4 个 `.vue` 全 `True True`。
- 守卫自身有单测 `backend/tests/scripts/test_check_disclosure_columns_coverage.py`（10 项）——
  **改守卫必须同批跑它**；改应用代码去迁就守卫正则属本末倒置（见 T7 第 4 条）。

#### T7. 已知坑（带进批 2~4）

1. **`_sub_table_columns` 是同步时快照** → 标了 `flat`（或改了任何列头）对**存量已同步附注不生效**，
   必须在底稿里**重新点一次「同步到附注」**才刷新列元数据（3.3 实测：重同步前 4 张表仍带
   推断出的凭空父表头，重同步后 `_column_groups` 全变 `[]`）。交付说明里要写这一句，
   否则复核人会以为改动没生效。
2. **不标 `flat` 就会被凭空加父表头**：后端 `_infer_groups_from_headers` 对 ≥4 列且共享前缀的
   headers 反猜分组。批 1 活体缺陷 = L1 上市逾期表 `['借款单位','期末余额','借款利率','逾期时间','逾期利率']`
   被猜出 `[{'group':'逾期','start':3,'span':2}]`。三态记牢：任一列 `flat` → `[]`（显式单级）；
   有 `group` → 非空；两者都无 → `None`（回退推断，**存量行为不变**）。
3. **附注表名不匹配 = 孤儿 TAB**：`sub_table_data` 的键必须与 `note_template_*.json` 的
   `tables[].name` 逐字一致。批 1 遗留 ① 就是 L1 推 `逾期借款情况`、而模板表名是
   `借款单位`（上市，`#### ` 标题被 `_is_table_title_paragraph` 丢弃后退化为 `headers[0]`）/
   `已逾期未偿还的短期借款情况`（国企）→ 同步出空 TAB。
   **补 `columns` 不修表名**（本 spec §不做：不动附注模板 JSON），但批 2~4 清查时若发现同类错位，
   **要登记进遗留表**，别让它悄悄过去。
4. **守卫基数是 16 不是 14**：requirements 的表漏记了 F4 两处
   （`composables/useF4DisclosureListed.ts` / `useF4DisclosureSOE.ts`，是 composable 而非
   `*TabDisclosure*.vue`，且是**真未覆盖**）。→ 批 1~4 全做完未覆盖数是 **2 而非 0**，
   `--strict` 仍 exit 1、CI 仍红；Task 8.2 需二选一（纳入某批 / 按 R4.3 登记 allowlist 写原因）。
5. **守卫认对象简写**：`_SUBTABLE_FIELD_RE = \bsub_table_data\s*[,:}\n]` /
   `_COLUMNS_FIELD_RE = \bcolumns\s*[,:}\n]`（±400 邻近窗口）。所以
   `const { sub_table_data, columns } = build…()` 这种 ES6 简写是**合规写法**，
   不要为了迁就旧正则去写成 `sub_table_data: sub_table_data`。
6. **`sheet_name` 用源 xlsx 真实中文 tab 名**（R8）。批 1 遗留 ⑤：L1/L3 四个 `.vue` 现推
   `L1-note-listed` 式合成标识，且 `note_workpaper_sync_registry.json` 无 L1/L3 条目
   → R8 守卫按 registry 驱动，扫不到。批 2~4 若该循环已在 registry 里，
   **顺手核对 `build*SyncPayload().sheet_name` 是否引用 `X_DISCLOSURE_SHEET_NAME` 常量**
   （断言也只许引用常量，写死字面量必再分叉：实测 8 种括号写法并存）。

---

### 批 2 列头清查：K4 / K5 / K6 / K7

> Task 6.1 产出，严格照 T0 执行。逐 sheet openpyxl 读源模板（含表头行 `merged_cells.ranges`）
> + 交叉验证 `附注模版/{上市,国企}报表附注.md`、`note_template_{listed,soe}.json`、
> `consol_note_sections_{listed,soe}.json`、`note_check_preset_formulas.json`，
> 并实跑后端 `_infer_groups_from_headers` / `_extract_column_groups` 取推断实证。
> **未写任何实现代码**（helper 落地属 6.2）。

#### 0. 前置实测结论（先看这五条，直接决定 6.2 的做法）

**① 守卫基数复验：12 未覆盖 = F4×2 + H4×1 + J1×2 + K4×1 + K5×2 + K6×2 + K7×2。**
本批目标 7 个：`k4/core/K4TabDisclosureSoe.vue`、`k5/core/K5TabDisclosureListed.vue`、
`k5/core/K5TabDisclosureSoe.vue`、`k6/core/K6TabDisclosureListed.vue`、
`k6/core/K6TabDisclosureSoe.vue`、`k7/core/K7TabDisclosureListed.vue`、
`k7/core/K7TabDisclosureSoe.vue`。`K4TabDisclosureListed.vue` 已覆盖（唯一 import
`k4NoteSectionMap.ts` 的组件），本节一并清查以保持族内一致。

**② 批 1 的「守卫假阴性」在批 2 不成立——这 7 个 Tab 是真未覆盖，且现状比缺 `columns` 更糟。**
7 个 `.vue` 全部在 `syncToDisclosureNotes()` 里手写内联载荷，共同形态：

```ts
sub_table_data: { rows },                                     // ← 键名是英文 `rows`
_note_texts: narrative ? [{ section: 'main', … }] : [],       // ← 挂在 payload 顶层
sheet_name: 'K5-note-listed',                                 // ← 合成标识
```

实跑后端确认三处后果（均为活体缺陷，不是理论风险）：

| 现状 | 后端行为（实证位置） | 后果 |
|---|---|---|
| 无 `columns` | `note_sub_table_projector.project_sub_tables` 的 `if not defs:` 降级分支 → `headers=['项目']`、**`values=[]`**、`_needs_columns=True` | 附注侧**整表金额全丢**，只剩行名 |
| 键名 `rows` | 键必须逐字等于 `note_template_*.json` 的 `tables[].name`（T7-3） | 每个 Tab 同步出一张名为 `rows` 的**孤儿子表**，模板原表恒空 |
| `_note_texts` 在顶层 | `wp_disclosure_sync_service.sync_from_workpaper` 走 `_extract_note_texts(sub_table_data)`，只认 `sub_table_data` 内的 `_note_texts`；请求体 `SyncFromWorkpaperRequest` 不收顶层同名字段 | 叙述文本**从未同步**，且 update 分支会把 `text_content` 置 None |

→ 6.2 不是「补 columns」，而是**把 7 处内联载荷改成 `build{X}{Variant}Columns` + 正确表名 +
`sub_table_data._note_texts`**。`K4TabDisclosureListed.vue`（走 `buildK4SyncPayload`）三项都正确，
可直接作族内范式。

**③ `k5/k6/k7NoteSectionMap.ts` 已存在但是孤儿文件（零 import）。**
三份都已写好 `COLUMNS_LISTED/COLUMNS_SOE`，但**没有任何组件引用**（实测全仓 grep
`k[567]NoteSectionMap` 命中 0；只有 `k4NoteSectionMap` 被 `K4TabDisclosureListed.vue` 引用）。
且三份的现有列头是「项目/期末余额/上年年末余额|期初余额」的通用三列模板，
与本节实测的源模板列集**对不上**（K5 少 `形成原因`、K6 应为两级 7 列、K7 应为 5~6 列变动表）。
→ 6.2 应在这三份文件里**改写**列定义并导出 `build{X}{Variant}Columns`，然后由 `.vue` 接入；
不要新建第二套 map（否则双真源）。

**④ 表头行合并实证：7 张待推送表中 5 张单行、2 张两行。**（详见 §2~§8 逐表证据）
两行的两张都是 K6「持有待售资产（情况表）」：

| sheet | 表头合并区（实测 `ws.merged_cells.ranges`） | 判定 |
|---|---|---|
| K6 上市 `附注披露信息（上市公司）` | `A6:A7`（项目 rowspan=2）、`B6:D6`（期末数 colspan=3）、`E6:G6`（上年年末数 colspan=3） | **两行表头**，2 个 `group` |
| K6 国企 `附注披露信息(国企）` | `A9:A10`、`B9:D9`（期末数）、`E9:G9`（期初数） | **两行表头**，2 个 `group` |
| K4/K5/K7 全部披露 sheet | 合并区只有 `A1:H1` `A2:H2` `A39:G39` `A13:G13` 之类的标题/说明行，表头行**零跨列合并** | 单行表头 → `flat` |

第 4 方印证：`consol_note_sections_*` 的 `multi_header` 对 K6 两表**为 `null`**——
因为 md 重建把第二行表头压成了 `rows[0]`（`["项  目","账面余额","减值准备","账面价值","账面余额","减值准备","账面价值"]`）
且 `headers` 尾部补空串。**`multi_header: null` 在 K6 是假阴性**，
判两行只能以 xlsx 合并区 + 附注模版 md 的双 header 行为准。
反向假阳性也有一例：`consol_note_sections_soe` 五-57-2（K7 政府补助表）`multi_header` **非 null**，
但源 xlsx K7 国企 `A14:J14` 表头行零合并、md L3983 只有 1 行 header
——那是把 md 的两行示例数据（`其他收益` / `营业外收入`）误当表头行。→ **该表是单行表头**。

**⑤ 不标 `flat` 会被凭空加父表头的表，本批有 7 组（比批 1 多得多）。**
实跑 `_infer_groups_from_headers`（`data_only` 真实 headers 入参）：

| headers | 推断结果 |
|---|---|
| `['项  目','期末余额','上年年末余额']`（K4/K5/K6负债 3 列） | `None` ✅ |
| `['项  目','期末余额','上年年末余额','形成原因']`（K5 上市 4 列） | `None` ✅ |
| `['项  目','期末余额','期初余额']`（K4/K5 国企） | `None` ✅ |
| `['债券名称','面值','票面利率','发行日期','债券期限','发行金额']` | `None` ✅ |
| `['债券名称','期初余额','本期发行','按面值计提利息','溢折价摊销','本期偿还','期末余额','是否违约']` | `None` ✅ |
| `['补助项目','上年年末数','本期增加','本期减少','期末数','形成原因']`（K4 上市④） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |
| `['项  目','账面余额','减值准备','账面价值','账面余额','减值准备','账面价值']`（K6 两表子列） | `[{'group':'账面','start':3,'span':2}]` ← **凭空且错**（真分组是 `期末数`/`上年年末数` 各 span=3） |
| `['项  目','期初余额','本期增加','本期转回','本期出售','期末余额']`（K6 减值准备子列） | `[{'group':'本期','start':2,'span':3}]` ← **凭空**（真分组只有 `本期减少` 覆盖转回/出售） |
| `['项  目','期末账面价值','期末公允价值','预计出售费用','时间安排']`（K6 处置组表，两版同） | `[{'group':'期末','start':1,'span':2}]` ← **凭空** |
| `['项  目','期初余额','本期增加','本期减少','期末余额','形成原因']`（K7 上市） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |
| `['项  目','期初余额','本期增加','本期减少','期末余额']`（K7 国企表1） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |
| `['补助项目','期初余额','本期新增补助金额','本期计入损益金额','本期计入损益的列报项目','本期返还的金额','其他<br/>变动','期末<br/>余额','与资产相关/与收益相关','本期返还的原因']`（K7 国企表2） | `[{'group':'本期','start':2,'span':4}]` ← **凭空** |

`_extract_column_groups` 三态同批自检：无 group 无 flat → `None`；任一列 `flat: true` → `[]`；
带 `group` → `[{'group':'期末余额','start':1,'span':2}]`。
→ **K7 两版、K6 全部 5 列以上的表都必须显式声明**（`flat` 或真 `group`），否则附注侧出假父表头。

#### 1. 源模板与附注模板定位（证据坐标）

| 循环 | 源 xlsx | 披露 sheet（xlsx tab 名，逐字） | 附注章节 | 附注模版 md | 校验预设 |
|---|---|---|---|---|---|
| K4 上市 | `…/4.风险应对-实质性程序（D-N）/K 管理循环/K4 其他流动负债.xlsx` | `附注披露信息（上市公司）` | 五、44 | `上市报表附注.md` L4591~4628 | **F44-1/2/3** |
| K4 国企 | 同上 | `附注披露信息（国企）` | 八、48 | `国企报表附注.md` L3663~3675 | **F44-1/2/3** |
| K5 上市 | `…/K 管理循环/K5 预计负债.xlsx` | `附注披露信息（上市公司)`（**前全角后半角**） | 五、50 | `上市报表附注.md` L4928~4940 | **F50-1/2/3** |
| K5 国企 | 同上 | `附注披露信息（国企）` | 八、55 | `国企报表附注.md` L3950~3962 | **F50-1/2/3** |
| K6 上市 | `…/K 管理循环/K6 持有待售资产和负债.xlsx` | `附注披露信息（上市公司）` | 五、11 | `上市报表附注.md` L2724~2826 | **F11-1/1a/2/3/4/5/6/6a**、F42-1/2/3 |
| K6 国企 | 同上 | `附注披露信息(国企）`（**前半角后全角**） | 八、12（负债另属 八、43） | `国企报表附注.md` L2309~2368、L3594~3602 | 同上 |
| K7 上市 | `…/K 管理循环/K7 递延收益.xlsx` | `附注披露信息（上市公司）` | 五、51 | `上市报表附注.md` L4946~4961 | **F51-1/2/3/6**（②表 F51-4/5/7/7a~7d） |
| K7 国企 | 同上 | `附注披露信息（国有企业）`（**「国有企业」非「国企」**） | 八、56 | `国企报表附注.md` L3970~3990 | 同上 |

裁决口径核查（T0.2 / T0.3）：

- **`note_check_preset_formulas.json` 本批有条目 → 裁决者到位**（与批 1 缺位相反）。
  条目 id 用**附注节号前缀 `F{节号}-n`**（不是循环号），两份文件的 `note_section` 都写 `五、xx`，
  靠 `section_title` 区分：`F44`=其他流动负债、`F50`=预计负债、`F51`=递延收益、
  `F11`=持有待售资产、`F42`=持有待售负债。**逐条抄录的裁决要点见 §2~§8 各表「预设裁决」行。**
- 章节号取自 `note_template_variant_matrix.json`：
  `qi_ta_liu_dong_fu_zhai` 五、44/八、48；`yu_ji_fu_zhai` 五、50/八、55；`di_yan_shou_yi` 五、51/八、56；
  `chi_you_dai_shou_zi_chan` **listed=null** / soe=八、12；`chi_you_dai_shou_fu_zhai` **listed=null** / soe=八、43；
  `chi_you_dai_shou_zi_chan_he_chi_you_dai_sho` listed=五、11 / **soe=null**。
- `note_workpaper_sync_registry.json`（34 条）**无 K4~K7 条目** → R8 守卫按 registry 驱动扫不到；
  7 个 Tab 现推 `K{4,5,6,7}-note-{listed,soe}` 合成标识，`k4~k7NoteSectionMap.ts` 里的
  `X_DISCLOSURE_SHEET_NAME` 常量也与真实 tab 名**逐字不符**（全用半角括号、K7 国企写成「国企」）。
  记为遗留 ⑦，不在 6.2 范围（但 6.2 落地 `build*SyncPayload` 时**必须引用常量而非字面量**）。
- BCD 类 md：`K管理循环` 目录未收 K4~K7 披露 sheet 条目，本批不作第 5 源。

#### 2. `K4TabDisclosureListed`（五、44，已覆盖，仅列头校准 + 补 `flat`）

`sub_table_data` 现状键：`其他流动负债`、`_note_texts`（元数据）。
底稿 UI 有 4 张表（L40 汇总 / L75 债券明细 / L113 债券续表 / L169 政府补助），**只推第 1 张**。

**表 1 `其他流动负债`** — 源 A6:C6 单行表头（该 sheet 合并区 `A1:H1` `A2:H2` `A39:G39` `A40:G40` `A41:G41`，第 6 行零合并）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 五、44 T0 `headers[0]='项目'`；源 A6=`项  目`；附注模版 L4593；UI L41 | `is_label` + **补 `flat`** |
| 1 | `end_amount` | `期末余额` | 附注模版 L4593 + note headers[1] + consol 五-44-1；源 B6=`期末数`、UI L42=`期末数` → 取附注模版 | `format:'amount'` |
| 2 | `prior_amount` | `上年年末余额` | 附注模版 L4593 + note headers[2]；源 C6=`上年年末数` → 取附注模版 | `format:'amount'` |

预设裁决：F44-1「报表.其他流动负债期末 = ①明细表.合计行.期末余额」/ F44-2 期初 / F44-3 明细行和=合计行
→ **只需 2 个金额列 + 合计行**，无第 3 数值列。现状 3 列正确，UI 的「形成原因/备注」（L58）无附注落点，
**不得作为第 4 列推送**。

**可补的 2 张表（6.2 二选一，见 §9 决策）**——列头已可逐字确认，属条件表（有行才推）：

- `短期应付债券`（note T1 name；源 A19:F19 单行；附注模版 L4614）：
  `债券名称`(is_label,flat) / `面值`(amount) / `票面利率`(percent) / `发行日期`(text) / `债券期限`(text) / `发行金额`(amount)
- `债券名称`（note T2 name，**即「短期应付债券（续）」**；源 A25:H25 单行；附注模版 L4623）：
  `债券名称`(is_label,flat) / `期初余额`(amount，源 B25=`上年年末数`→取附注模版) / `本期发行` / `按面值计提利息` /
  `溢折价摊销` / `本期偿还` / `期末余额` / `是否违约`(text)

UI 第 4 张「递延收益-政府补助情况」（源 A32:F32）在 五、44 **无对应模板表**
（上市侧它属独立章节「计入递延收益的政府补助」，附注模版 L6873/L6890/L6902 三张表）→ 遗留 ④，不推。

#### 3. `K4TabDisclosureSoe`（八、48）

推送键应为：`其他流动负债`、`_note_texts`（现状错为 `rows` + 顶层 `_note_texts`）。

**表 1 `其他流动负债`** — 源 `附注披露信息（国企）` **A6:C6 单行表头**（合并区仅 `A1:E1` `A2:E2`）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 八、48 T0 `headers[0]='项目'`；源 A6=`项  目`；附注模版 L3665；UI L50 | `is_label` + `flat` |
| 1 | `end_amount` | `期末余额` | 源 B6；附注模版 L3665；note headers[1]；consol 五-49-1；UI L51 —— **四源一致** | `format:'amount'` |
| 2 | `prior_amount` | `期初余额` | 源 C6；附注模版 L3665；note headers[2]；UI L59 —— **四源一致** | `format:'amount'` |

预设裁决：F44-1/2/3 同上市，2 个金额列。
底稿 UI 的「增减额」（L67）与「备注」（L72）是审计列，附注无落点 → 不推（投影成附注形状）。

**⚠️ 行来源缺陷（6.2 必修，与列头同批）**：现状 `rows` 由
`sections.flatMap(s => s.rows.filter(r => !r.isFormula))` 生成，把
`一、按项目性质分类`（预提费用/待转销项税额/代扣代缴款项/待认证进项税额/应付短期利息/其他/合计）
与 `二、增减变动说明`（本期增加/本期减少/净变动）**两个 section 的行压进同一张表** →
附注表里会混进「本期增加」这种非科目行。
→ 6.2 只推 `id==='nature'` 的 section 行；`change` 段是分析用，随 `_note_texts` 走文字。

#### 4. `K5TabDisclosureListed`（五、50）

推送键应为：`预计负债`、`_note_texts`。

**表 1 `预计负债`** — 源 `附注披露信息（上市公司)` **A6:D6 单行表头**（合并区仅 `A1:E1` `A2:E2`）→ `flat`
（4 列，`_infer_groups_from_headers` 返 `None`，但按 T2 仍标 `flat` 锁死）

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 五、50 T0 `headers[0]='项目'`；源 A6=`项  目`；附注模版 L4930；consol 五-50-1；UI L30 | `is_label` + `flat` |
| 1 | `end_amount` | `期末余额` | 附注模版 L4930 + note headers[1] + consol；源 B6=`期末数` → 取附注模版 | `format:'amount'` |
| 2 | `prior_amount` | `上年年末余额` | 附注模版 L4930 + note headers[2] + consol；源 C6=`期初数` → 取附注模版（上市口径） | `format:'amount'` |
| 3 | `reason` | `形成原因` | 源 D6；附注模版 L4930；note headers[3]；consol 五-50-1 —— **四源一致** | `format:'text'` |

预设裁决：F50-1「报表.预计负债期末 = ①明细表.合计行.期末余额」/ F50-2 期初 /
F50-3「①表: sum(合计行以外的所有明细行) = 合计行（每个数值列独立校验）」
→ 2 个数值列 + 1 个文本列，**无变动表**（不要按 UI 的 roll-forward 推 4 个金额列）。

**⚠️ 列集投影（6.2 注意）**：UI 是 roll-forward（期初/本期增加/本期减少/期末，L31~L50）+「变动说明」，
附注只要「期末/上年年末/形成原因」。
→ `values = [r.endBalance, r.beginBalance, r.remark]`；`increase`/`decrease` 仅供底稿内部与
`_note_texts` 叙述，不进附注列。`remark`（UI 标签「变动说明」）填 `形成原因` 列——
这是本表唯一的文本字段，且附注模版列名为 `形成原因`，按 T0.3 取附注模版列名。

UI 的「②或有事项披露」（L80~L114）在 五、50 无模板表（附注模版只有 1 张表 + 一段文字提示
「重要的预计负债，应披露相关重要假设、估计」L4942）→ 不推，走 `_note_texts`。

#### 5. `K5TabDisclosureSoe`（八、55）

推送键应为：`预计负债`、`_note_texts`。

**表 1 `预计负债`** — 源 `附注披露信息（国企）` **A6:D6 单行表头**（合并区仅 `A1:E1` `A2:E2`）→ `flat`

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 八、55 T0 `headers[0]='项目'`；源 A6=`项  目`；附注模版 L3952；consol 五-56-1；UI L30 | `is_label` + `flat` |
| 1 | `end_amount` | `期末余额` | 附注模版 L3952 + note headers[1] + consol；源 B6=`期末数` → 取附注模版 | `format:'amount'` |
| 2 | `prior_amount` | `期初余额` | 附注模版 L3952 + note headers[2] + consol；源 C6=`期初数`（一致）；UI L46 | `format:'amount'` |

**🔴 T4 变体列集差异（本批第一处 `values` 必须分支的地方）**：
源 xlsx 国企 A6:D6 **有** `形成原因`（D6），但 **附注模版 L3952 / note_template 八、55 /
consol 五-56-1 三家都只有 3 列**（形成原因降级为表下注文字：
「注：应逐项说明未决诉讼、待执行的亏损合同的形成原因和进展」L3964）。
按 T0.3「附注是交付物 → 列结构随附注模版；底稿可多留审计列，同步时投影成附注形状」
→ **国企 3 列（2 个值列），上市 4 列（3 个值列）**。

```ts
// values 必须与 buildProvisionColumns(variant) 的非标签列 **同序**
values: variant === 'soe'
  ? [r.endBalance, r.beginBalance]                 // 2 值列
  : [r.endBalance, r.beginBalance, r.remark]       // 3 值列（末列 形成原因）
```

照抄上市写法给国企，`remark` 会溢出到不存在的第 3 值列（被投影器按列数截断/错位），
**表面仍渲染 3 列，肉眼极难发现** → T5 第 8 族断言必须两版各钉一条。

底稿 UI 国企侧的「确认依据」`basis`（L51）、「风险等级」`riskLevel`（L63）、
以及 ③未决诉讼明细（L131~L153）/ ④弃置费用明细（L165~L184）两张表，附注无落点 → 不推。

#### 6. `K6TabDisclosureListed`（五、11，**本批唯一两行表头 + 唯一需 `group`**）

推送键应为：`持有待售资产和持有待售负债`、`_note_texts`。

**表 1 `持有待售资产和持有待售负债`** — 源 `附注披露信息（上市公司）` **A6:G7 两行表头**：
`merged_cells.ranges` 实测含 `A6:A7`（项目 rowspan=2）、`B6:D6`（期末数）、`E6:G6`（上年年末数）；
第 7 行 B7~G7 = `账面余额/减值准备/账面价值` × 2。附注模版 L2726+L2728 双 header 行同构；
consol 五-11-1 `headers` 尾部补 4 个空串 + `rows[0]` 为第二行表头（压扁痕迹）。→ **`group`，不标 `flat`**

| # | key | label | group | 逐字证据 | 属性 |
|---|---|---|---|---|---|
| 0 | `label` | `项目` | — | note_template 五、11 T0 `headers[0]='项目'`；源 A6=`项  目`；附注模版 L2726 | `is_label: true` |
| 1 | `end_gross` | `账面余额` | `期末余额` | 源 B7 + 附注模版 L2728（子列名）；父表头取附注模版 L2726 `期末余额`（源 B6=`期末数` → 取附注模版） | `amount` |
| 2 | `end_impairment` | `减值准备` | `期末余额` | 源 C7；附注模版 L2728 | `amount` |
| 3 | `end_book` | `账面价值` | `期末余额` | 源 D7（D16 写明 `C=A+B=报表数`）；附注模版 L2728 | `amount` |
| 4 | `prior_gross` | `账面余额` | `上年年末余额` | 源 E7；附注模版 L2728 | `amount` |
| 5 | `prior_impairment` | `减值准备` | `上年年末余额` | 源 F7；附注模版 L2728 | `amount` |
| 6 | `prior_book` | `账面价值` | `上年年末余额` | 源 G7；附注模版 L2728 | `amount` |

产出 `_column_groups = [{"group":"期末余额","start":1,"span":3},{"group":"上年年末余额","start":4,"span":3}]`。
同名子列（`账面余额`/`减值准备`/`账面价值` 各出现两次）**不去重、不加期别前缀**（模板即如此，
靠 `end_*`/`prior_*` 两组 key 区分；加前缀＝压平＋杜撰，同 L3 上市两列都叫「利率区间」的先例）。

预设裁决（**本表是本批预设信息最密的一张**）：
- F11-1「报表.持有待售资产期末 = ①情况表.合计行.**期末账面价值**」/ F11-1a 期初账面价值
  → 确认「账面价值」是列名、且期末/期初各有一列。
- F11-4「①情况表: **账面余额 − 减值准备 = 账面价值**（期末/期初各独立校验）」
  → 确认三子列齐备且为纵向勾稽关系，**不能只推 2 列**。
- F11-3「sum(合计行以外的所有明细行) = 合计行（每个数值列独立校验；含"其中"子项时，子项之和 ≤ 对应父项）」
  → 行结构含「（一）/（二）」父行 + 「其中：」子行，6.2 保持底稿行序原样推送。

**⚠️ 值映射需定口径（§9 决策 A）**：底稿 `AssetDisclosureRow` 字段为
`originalCost / accumulatedDep / impairment / bookValue(=原值−折旧−减值) / fairValue / sellingCost /
fairValueNet / openingBalance / closingBalance`。
- 期末三列可干净落位：`end_gross = bookValue + impairment`（由 F11-4 反解，等价于 原值−折旧）、
  `end_impairment = impairment`、`end_book = bookValue`。
- **上年年末三列只有 `openingBalance` 一个来源**：`prior_book = openingBalance` 尚可，
  `prior_gross` / `prior_impairment` **无录入来源** → 按 T0.4 **不许凭空造数**，推 `null`。
  （补录入列属底稿改版，另立 spec；同批 1 遗留 ② 的处理方式。）

**⚠️ 第 2 张「持有待售负债」表：模板表名错位，6.2 不推**（§9 决策 B / 遗留 ②）。
源 A19:C19 单行 3 列（`项  目 / 期末数 / 上年年末数`），附注模版 L2743 为
`项  目 / 期末余额 / 上年年末余额`，预设 F42-1/2/3 也认这张表；
但 `note_template_listed.json` 五、11 的 `tables[1].name` 是 **`持有待售资产减值准备`**
而其 `rows` 是负债行——模板 name↔rows **整体错位一位**（T2 name=`期末，持有待售资产的情况：`
配的却是减值准备行；T5 name 退化成 `项  目`）。按此名推负债数据会把负债塞进"减值准备"表。
→ 登记遗留，**不在 6.2 补 columns 时顺手改附注模板 JSON**（本 spec §不做）。

底稿 UI 无「持有待售资产减值准备」变动表（减值只是 assetTable 的一列），
故附注 ③减值准备变动表（源 A32:F33 两行表头、预设 F11-2/5/6/6a）本批**无数据来源**，不推。

#### 7. `K6TabDisclosureSoe`（八、12，**两行表头**）

推送键应为：`持有待售资产`、`_note_texts`。

**表 1 `持有待售资产`** — 源 `附注披露信息(国企）` **A9:G10 两行表头**：
实测合并区含 `A9:A10`、`B9:D9`（期末数）、`E9:G9`（期初数）；第 10 行 B10~G10 =
`账面余额/减值准备/账面价值` × 2。附注模版 国企 L2319+L2321 双 header 行同构；
consol 五-13-1 同款压扁（`headers` 补空串 + `rows[0]` 为第二行）。→ **`group`，不标 `flat`**

| # | key | label | group | 逐字证据 | 属性 |
|---|---|---|---|---|---|
| 0 | `label` | `项目` | — | note_template 八、12 T0 `headers[0]='项目'`；源 A9=`项  目`；附注模版 L2319 | `is_label: true` |
| 1 | `end_gross` | `账面余额` | `期末数` | 源 B10；附注模版 L2321；父表头 源 B9=`期末数` + 附注模版 L2319 + note headers[1] —— **三源一致（国企用「数」不用「余额」）** | `amount` |
| 2 | `end_impairment` | `减值准备` | `期末数` | 源 C10；附注模版 L2321 | `amount` |
| 3 | `end_book` | `账面价值` | `期末数` | 源 D10（D19=`A+B=报表数`）；附注模版 L2321 | `amount` |
| 4 | `prior_gross` | `账面余额` | `期初数` | 源 E10；附注模版 L2321；父表头 源 E9=`期初数` + note headers[2] | `amount` |
| 5 | `prior_impairment` | `减值准备` | `期初数` | 源 F10；附注模版 L2321 | `amount` |
| 6 | `prior_book` | `账面价值` | `期初数` | 源 G10；附注模版 L2321 | `amount` |

产出 `_column_groups = [{"group":"期末数","start":1,"span":3},{"group":"期初数","start":4,"span":3}]`。
**父表头两版不同**（上市 `期末余额`/`上年年末余额` vs 国企 `期末数`/`期初数`）→ 6.2 的
`buildHeldForSaleColumns(variant)` 必须按变体给 `group` 串，不能共用常量。

预设裁决：与上市同一批 F11-*（预设两份文件的 F11 条目逐字相同）→ 三子列齐备、账面余额−减值准备=账面价值。

**⚠️ 值映射需定口径（§9 决策 A）**：底稿 `AssetSoeRow` = `bookValue / impairment / fairValueNet /
openingBalance / closingBalance`。
`end_impairment = impairment`；`end_book` 有 `bookValue` 与 `closingBalance` **两个候选**（UI 同时存在
「账面价值」L31 与「期末余额」L51 两列，语义重复）；`end_gross = end_book + impairment`；
`prior_book = openingBalance`，`prior_gross`/`prior_impairment` 无来源 → `null`。

**⚠️ 「持有待售负债」是独立章节 八、43，不属本 Tab 的 `section_id`**（遗留 ③）：
`variant_matrix.chi_you_dai_shou_fu_zhai.soe_standalone = '八、43'`，
其模板表 `持有待售负债` headers = `[项目, 期末账面价值, 期末公允价值, 预计处置费用, 时间安排]`
（附注模版 国企 L3596，源 A51:E51），与上市侧 3 列版**完全不同构**。
现状 `syncToDisclosureNotes()` 只推一个 `section_id: '八、12'` → 负债数据无处可去；
底稿 `liabilitySummary`（期初/本期变动/期末/说明）也与该 5 列表对不上。
→ 需按章节路由改造（同批 1 遗留 ③ 的形态），另立 spec；6.2 只推资产表。

底稿无 ③持有待售非流动资产表（源 A34:E34）/ ④处置组表（源 A43:E43）的数据来源 → 不推。

#### 8. `K7TabDisclosureListed`（五、51）/ `K7TabDisclosureSoe`（八、56）

##### 8.1 `K7TabDisclosureListed` — 推送键 `递延收益`、`_note_texts`

**表 1 `递延收益`** — 源 `附注披露信息（上市公司）` **A7:F7 单行表头**
（合并区仅 `A1:G1` `A2:G2` `A13:G13`，第 7 行零合并）→ **必须标 `flat`**（§0⑤：否则被猜出「本期」父表头）

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 五、51 T0 `headers[0]='项目'`；源 A7=`项  目`；附注模版 L4948；consol 五-51-1；UI L33 | `is_label` + **`flat`** |
| 1 | `begin_amount` | `期初余额` | 源 B7；附注模版 L4948；note headers[1]；UI L34 —— **四源一致** | `amount` |
| 2 | `increase` | `本期增加` | 源 C7；附注模版 L4948；UI L40 | `amount` |
| 3 | `decrease` | `本期减少` | 源 D7；附注模版 L4948；UI L46 | `amount` |
| 4 | `end_amount` | `期末余额` | 源 E7；附注模版 L4948；UI L52 | `amount` |
| 5 | `reason` | `形成原因` | 源 F7；附注模版 L4948；note headers[5]；UI L57 | `text` |

预设裁决：F51-3「①明细表: 期初 + 本期增加 − 本期减少 = 期末（每行独立）」/
F51-1/2 报表期末·期初 = 合计行 / F51-6 明细行和=合计行 → **正是这 4 个金额列**，
证实「本期增加/本期减少」是**并列的两个值列而非「本期」下的两个子列**（§0⑤ 的凭空 `本期` 分组必须用 `flat` 压掉）。

底稿两张 UI 表（`与资产相关的政府补助` L32 / `与收益相关的政府补助` L73）列集完全相同，
附注只有 1 张表 → 现状「两表行拼成一个列表」的做法**正确**，6.2 保留；
`values = [beginBalance, increase, decrease, beginBalance+increase-decrease, reason]`。

##### 8.2 `K7TabDisclosureSoe` — 推送键 `递延收益`、`_note_texts`

**表 1 `递延收益`** — 源 `附注披露信息（国有企业）` **A7:E7 单行表头**
（合并区仅 `A1:J1` `A2:J2`）→ **必须标 `flat`**

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `label` | `项目` | note_template 八、56 T0 `headers[0]='项目'`；附注模版 L3972=`项  目`；consol 五-57-1；UI L33。**源 A7=`项目/类别`** → 冲突，取附注口径 | `is_label` + **`flat`** |
| 1 | `begin_amount` | `期初余额` | 源 B7；附注模版 L3972；note headers[1]；UI L69 | `amount` |
| 2 | `increase` | `本期增加` | 源 C7；附注模版 L3972；UI L75 | `amount` |
| 3 | `decrease` | `本期减少` | 源 D7；附注模版 L3972；UI L81 | `amount` |
| 4 | `end_amount` | `期末余额` | 源 E7；附注模版 L3972；UI L87 | `amount` |

**🔴 T4 变体列集差异（本批第二处 `values` 必须分支）**：上市 5 个值列（末列 `形成原因`），
国企 4 个值列（**无 `形成原因`**：源 A7:E7 只 5 列、附注模版 L3972 只 5 列、note headers 只 5 项，
且底稿 `DisclosureRow` 国企版**连 `reason` 字段都没有**，L170~L178）。

```ts
values: variant === 'soe'
  ? [r.beginBalance, r.increase, r.decrease, end]
  : [r.beginBalance, r.increase, r.decrease, end, r.reason]
```

**表 2 `其中：递延收益-政府补助情况`（10 列，6.2 不推，登记遗留 ⑤）**
列头本身可逐字确认（附注模版 国企 L3983；note_template 八、56 T1 `headers` 10 项；源 A14:J14）：
`补助项目` / `期初余额` / `本期新增补助金额` / `本期计入损益金额` / `本期计入损益的列报项目` /
`本期返还的金额` / `其他<br/>变动` / `期末<br/>余额` / `与资产相关/与收益相关` / `本期返还的原因`；
**单行表头**（源 A14:J14 零合并；`consol_note_sections_soe` 五-57-2 的 `multi_header` 非 null 是
把 md 两行示例数据误当表头，见 §0④）；预设 F51-4/5/7/7a~7d 全部指向该表。
但底稿 K7 国企 Tab **无对应录入表**（只有两张 5 列的 资产相关/收益相关 表）→ 无数据来源，
按 T0.4 不推、不造列。

#### 9. 需拍板的三处（6.2 开工前定）

| # | 决策 | 备选 | 建议 |
|---|---|---|---|
| **A** | K6 两版「上年年末/期初」三子列缺录入来源 | (A1) 推 6 列，`prior_gross`/`prior_impairment` 给 `null`，`prior_book = openingBalance`；(A2) 只推期末 3 列（附注侧少一半列） | **A1**。列结构随附注模版（F11-4 要求三子列齐备），缺的是数据不是列；空值可见 = 提示审计师补录，比砍列更保守。同时登记遗留「底稿缺上年年末账面余额/减值准备录入列」 |
| **B** | K6 上市「持有待售负债」表推不推 | (B1) 不推（模板 `tables[1].name` 是 `持有待售资产减值准备`，推了就是把负债塞进减值表）；(B2) 推并同批改 `note_template_listed.json` 表名 | **B1**。本 spec §不做「不动附注模板 JSON」；B2 属未来 K6 alignment spec |
| **C** | K4 上市两张债券表补不补 | (C1) 本批只校准现有 1 表 + 补 `flat`；(C2) 同批补 `短期应付债券` + `债券名称`（续表）两张条件表 | **C2**。两张表列头四源齐全（§2）、附注模板表名现成，且 K4 上市已覆盖不影响守卫计数；顺手补齐比另开一轮便宜。若选 C1 则登记遗留 |

另有一处 K6 国企 `end_book` 取 `bookValue` 还是 `closingBalance` 的字段歧义（§7），
建议 6.2 取 `bookValue`（与 `impairment` 同源、能满足 F11-4 勾稽），并在底稿侧后续收敛重复列。

#### 10. 条件表 / 变体分支登记（供 6.2 与 9.1 契约测试）

| 项 | 结论 |
|---|---|
| **条件表** | 本批 7 个 Tab 待推送的 7 张表**全部无条件推送**（不存在批 1 L1 逾期表那种 `if (rows.length > 0)`）→ `columns` 无需 `includeX` 分支。**例外**：若采纳决策 C2，K4 上市两张债券表是条件表（`bondRows`/`bondContRows` 过滤后为空则不推），必须走成对 `if`（T3） |
| **`values` 变体分支（T4）** | 两处：**K5**（listed 3 值列含 `形成原因` / soe 2 值列）、**K7**（listed 5 值列含 `形成原因` / soe 4 值列）。K6 两版值列数相同（6 列）但 **`group` 父表头串不同**（`期末余额`/`上年年末余额` vs `期末数`/`期初数`）→ 也必须按变体构建 |
| **两行表头** | 仅 K6 两版的资产情况表（各 2 个 group）。其余 5 张全 `flat` |
| **`_note_texts`** | 7 个 Tab 现状全部挂在 payload 顶层 → 后端读不到。6.2 必须移进 `sub_table_data._note_texts`（照 `buildK4SyncPayload` 写法） |

#### 11. 汇总

| Tab | 数据子表数（6.2 推送） | 单行表头 | 两行表头 | 需标 `flat` | 需 `group` | allowlist 候选 |
|---|---|---|---|---|---|---|
| `K4TabDisclosureListed`（已覆盖） | 1（+2 待定，决策 C） | 1（+2） | 0 | 1（+2） | 0 | 0 |
| `K4TabDisclosureSoe` | 1 | 1 | 0 | 1 | 0 | 0 |
| `K5TabDisclosureListed` | 1 | 1 | 0 | 1 | 0 | 0 |
| `K5TabDisclosureSoe` | 1 | 1 | 0 | 1 | 0 | 0 |
| `K6TabDisclosureListed` | 1 | 0 | 1 | 0 | 2 | 0 |
| `K6TabDisclosureSoe` | 1 | 0 | 1 | 0 | 2 | 0 |
| `K7TabDisclosureListed` | 1 | 1 | 0 | 1 | 0 | 0 |
| `K7TabDisclosureSoe` | 1 | 1 | 0 | 1 | 0 | 0 |
| **合计（7 个未覆盖 Tab）** | **7** | **5** | **2** | **5** | **4** | **0** |

**allowlist 候选：无。** 7 张待推送表的每个 label 都能指到源 xlsx 单元格坐标 + 附注模版 md 行号 +
`note_template` `headers[]`，且**全部有校验预设条目背书**（F44 / F50 / F51 / F11）。
「无法确认」的部分不是列头而是**数据来源**（K6 上年年末两子列、K6 减值准备变动表、
K7 国企政府补助 10 列表、K4 上市政府补助表）→ 按 T0.4 走遗留登记，不填假列头、不造录入列。

#### 12. 遗留（超出 6.2 范围，只登记不改）

| # | 问题 | 证据 | 归属 |
|---|---|---|---|
| ① | **7 个 Tab 现状同步即坏**：键名 `rows`（孤儿子表）+ 无 `columns`（投影器降级分支把 `values` 全清空）+ `_note_texts` 挂顶层（后端 `_extract_note_texts` 读不到、update 分支还会把 `text_content` 置 None） | 7 个 `.vue` 的 `syncToDisclosureNotes()`；`note_sub_table_projector.py` L160~L180 `if not defs:` 分支；`wp_disclosure_sync_service.py` L320 / L512~L517 | **6.2 必修**（列头与载荷同批） |
| ② | K6 上市 五、11 模板 `tables[]` 的 name↔rows **整体错位一位**：`tables[1].name='持有待售资产减值准备'` 配的是负债行；`tables[2].name='期末，持有待售资产的情况：'` 配的是减值准备行；`tables[5].name` 退化成 `项  目`（`#### ` 标题被 `_is_table_title_paragraph` 丢弃） | `note_template_listed.json` 五、11 T0~T5 vs 附注模版 L2724~2826 六张表 | 未来 K6 alignment spec（本 spec §不做：不动附注模板 JSON） |
| ③ | K6 国企「持有待售负债」是**独立章节 八、43**（5 列：项目/期末账面价值/期末公允价值/预计处置费用/时间安排），与上市侧 3 列版不同构；现状 Tab 只推一个 `section_id='八、12'` → 负债数据无处可去，八、43 永久空表 | `note_template_variant_matrix.json` `chi_you_dai_shou_fu_zhai`；`note_template_soe.json` 八、43 T0；附注模版 国企 L3596 | 需章节路由改造（同批 1 遗留 ③），另立 spec |
| ④ | 底稿有表、附注本章节无落点：K4 上市 ④「递延收益-政府补助情况」（源 A32:F32，上市侧属独立章节「计入递延收益的政府补助」附注模版 L6873/L6890/L6902 三表）；K5 两版「或有事项/未决诉讼/弃置费用」明细；K6 两版处置组/减值准备变动表；K4 国企「增减变动说明」段 | 各 `.vue` 模板 + 对应 `note_template` 章节 tables | 各循环 alignment spec；**禁在补 columns 时把它们塞进现有表** |
| ⑤ | 附注有表、底稿无录入：K6 两版 ③减值准备变动表（两行表头 6 列，预设 F11-2/5/6/6a）、K6 两版处置组表、K7 国企 表2「其中：递延收益-政府补助情况」（10 列，预设 F51-4/5/7/7a~7d）、K4 上市两张债券表（若决策取 C1） | 附注模版 L2765/L2782/L3983/L4614；预设条目 | 底稿改版（补录入表），**禁杜撰数据列** |
| ⑥ | `k5NoteSectionMap.ts` / `k6NoteSectionMap.ts` / `k7NoteSectionMap.ts` 是**孤儿文件**（全仓零 import），且现有 `COLUMNS_LISTED/SOE` 三列模板与源模板列集不符 | 全仓 grep `k[567]NoteSectionMap` → 0 命中 | **6.2 在这三份里改写并导出 builder**，不新建第二套 map |
| ⑦ | R8 同类漂移：7 个 Tab 推 `K{4,5,6,7}-note-{listed,soe}` 合成标识；`note_workpaper_sync_registry.json`（34 条）无 K4~K7；`k4~k7NoteSectionMap.ts` 的 `X_DISCLOSURE_SHEET_NAME` 全用半角括号、K7 国企写「国企」而真实 tab 是「国有企业」。真实 tab 名见 §1 表（**4 个 sheet 4 种括号写法**：K4 全角 / K5 上市前全角后半角 / K6 国企前半角后全角 / K7 国企「国有企业」） | 7 个 `.vue` 的 POST body；registry 0 命中；4 份 xlsx 的 `wb.sheetnames` | R8 后续。**6.2 落地时把常量改对并只引用常量**（断言写死字面量必再分叉） |
| ⑧ | `consol_note_sections_*.multi_header` 双向不可靠：K6 两表真两行却为 `null`（md 重建压扁成 `rows[0]`）；K7 国企政府补助表真单行却非 `null`（两行示例数据被误当表头） | consol 五-11-1 / 五-13-1 / 五-57-2 | 判两行一律以 xlsx 合并区 + 附注模版双 header 行为准；本条写入 T0 备注即可 |

---

### 批 3 列头清查：J1

> Task 7.1 产出，严格照 T0 执行。逐 sheet openpyxl 读源模板（含表头行 `merged_cells.ranges`）
> + 交叉验证 `附注模版/{上市,国企}报表附注.md`、`note_template_{listed,soe}.json`、
> `consol_note_sections_{listed,soe}.json`、`note_check_preset_formulas.json`、
> `note_workpaper_sync_registry.json`，并实跑后端 `_infer_groups_from_headers` /
> `_extract_column_groups` / `project_sub_tables` 取推断实证。
> **本任务未写任何实现代码**（helper 落地属 7.2）。

#### 0. 前置实测结论（先看这七条，直接决定 7.2 还剩什么）

**① 守卫基数：起始 5 未覆盖 = F4×2 + H4×1 + J1×2；本会话期间已被并发会话清零。**
7.1 开工时 `check_disclosure_columns_coverage.py` 报 92 调用点 / 87 覆盖 / **5 未覆盖**
（`composables/useF4DisclosureListed.ts`、`useF4DisclosureSOE.ts`、
`h4/core/H4TabDisclosureListed.vue`、`j1/core/J1TabDisclosure{Listed,Soe}.vue`）。
清查过程中复跑同一命令得 **92 / 92 / 0**，`--strict` 已可 exit 0。
落盘核对（`python -c` 直读，非 `read_file`）确认守卫 `COLUMN_BUILDERS` 已新增三条：

```
"buildF4ListedSyncPayload",    # F4 应付账款 listed（f4NoteSectionMap 4 组列头）
"buildF4SoeSyncPayload",       # F4 应付账款 soe
"buildJ1SyncPayload",          # J1 应付职工薪酬（listed+soe，3 表共用 j1MovementColumns）
"buildH4ListedSyncPayloads",   # H4 工程物资 listed（复用 H2 五、23 列头，按实际推送键取子集）
```

正向复验 `_is_covered`（T6 要求，不能只看"从清单里消失"）：
`J1TabDisclosureListed.vue` / `J1TabDisclosureSoe.vue` 均 `is_file=True`、
`has_sync_marker=True`、`is_covered=True`，命中路径是 `COLUMN_BUILDERS` 里的
`buildJ1SyncPayload`（`_BUILDER_RE` 命中数为 **0**，见决策 B）。`ALLOWLIST` 仍为空 → 本批 allowlist 候选 0。

**② 批 2 的三处活体缺陷（英文键 `rows` / 顶层 `_note_texts` / 合成 `sheet_name`）在 J1 全部不成立。**
两个 `.vue` 都不手写内联载荷，而是 `const { body } = buildJ1SyncPayload({...})` 后直接 POST。
落盘实测逐项对照：

| 批 2 缺陷 | J1 实况 | 证据 |
|---|---|---|
| 键名英文 `rows` | ❌ 不存在 —— 键取 `J1_SUB_TABLE_KEYS[variant]`，三个值均为中文逐字表名 | `j1NoteSectionMap.ts` `sub_table_data` 组装；与 `note_template_*.json` 比对见 §2/§3 |
| `_note_texts` 挂 payload 顶层 | ❌ 不存在 —— 在 `sub_table_data._note_texts` 内（后端 `_extract_note_texts` 能读到） | 同上，`sub_table_data` 第 4 个键 |
| `sheet_name` 合成标识 | ❌ 不存在 —— 走 `J1_DISCLOSURE_SHEET_NAME` 常量，两个 `.vue` 全文无 `'J1-note` 字面量 | `sheet_name: J1_DISCLOSURE_SHEET_NAME[variant]`；R8 核对见 §1 |

→ 7.2 在 J1 的工作量本就远小于批 2：**只有 `flat` / `format` / 命名契约三件**，无需重写载荷形态。

**③ `j1NoteSectionMap.ts` 存在且不是孤儿文件（与批 2 的 k5/k6/k7 相反）。**
两个 `.vue` 都 `import { buildJ1SyncPayload, J1_NOTE_SECTION, type J1DisclosureSnapshot } from '../../composables/j1NoteSectionMap'`。
该文件是 `j1-disclosure-note-linkage` spec 的产物，头注释已冻结 Decision 2（列头取模板「期初余额」而非组件「上年年末数」）
与 Decision 3（soe 第三表键消歧），本次清查**逐条复核并全部确认成立**（见 §2 裁决行 / 遗留 ①）。

**④ 表头行合并实证：6 张待推送表 100% 单行表头，`group` 需求为 0。**
与 7.1 任务描述的预判（"J1 通常有真两行表头，预期有 group 工作"）**相反** —— 实测两个 sheet 的
合并区全部落在标题 / 提示 / 说明行，三个表头行（上市 A6/A17/A40、国企 A8/A16/A31）**零跨列合并**：

| sheet | `ws.merged_cells.ranges` 实测 | 表头行 | 判定 |
|---|---|---|---|
| `附注披露信息（上市公司）` | `A1:E1` `A2:E2` `A14:E14` `A15:E15` `A37:E37` `A38:E38` `A50:E50` `A51:E51` `A53:E53` `A54:E54` | A6:E6 / A17:E17 / A40:E40 | **单行表头 ×3** → `flat` |
| `附注披露信息（国有企业）` | `A1:E1` `A2:E2` `A42:E42` `A43:E43` `A44:E44` | A8:E8 / A16:E16 / A31:E31 | **单行表头 ×3** → `flat` |

第 4 方印证（T0.2）：`consol_note_sections_listed` 五-40-1「应付职工薪酬」
`multi_header: null`、`headers = ["项  目","期初余额","本期增加","本期减少","期末余额"]`；
`consol_note_sections_soe` 五-41-1「应付职工薪酬列示」同款。附注模版 md 也只有一行 header
（上市 L4387 / L4406 / L4432，国企 L3476 / L3487 / L3504）。
**四源一致，`multi_header` 这次没有假阴/假阳**（对照批 2 遗留 ⑧ 的双向不可靠）。

**⑤ 不标 `flat` 会被凭空加「本期」父表头 —— J1 六张表 100% 中招（同 F2 房企 3 表缺陷）。**
实跑 `note_sub_table_projector._infer_groups_from_headers`（真实 headers 入参，非构造样本）：

| headers | 推断结果 |
|---|---|
| `['项目','期初余额','本期增加','本期减少','期末余额']`（note_template 口径，6 张表全同） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |
| `['项  目','期初余额','本期增加','本期减少','期末余额']`（md / consol 双空格口径） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |
| `['项 目','上年年末数','本期增加','本期减少','期末数']`（上市源 xlsx 原样，未裁决） | `[{'group':'本期','start':2,'span':2}]` ← **凭空** |

`_extract_column_groups` 三态同批自检：无 `group` 无 `flat` → `None`；标签列 `flat: true` → `[]`；
显式 `group:'本期'`（反例）→ `[{'group':'本期','start':2,'span':2}]`。
端到端 `project_sub_tables`（`_source=workpaper` + 位置化 `values` 行）实证：
现状列定义 → `_column_groups: [{'group':'本期','start':2,'span':2}]`；标 `flat` → `_column_groups: []`。
降级分支反例（完全不传 `columns`）→ `headers: ['项目']`、`values: []`、`_needs_columns: true`
—— J1 从未落进该分支（`columns` 一直在推），故批 2 那种"整表金额全丢"在 J1 不存在。

**⑥ 7.2 的主体（`flat` + `format` + 共享 `ColumnDef`）已由并发会话落盘。**
`j1NoteSectionMap.ts` 落盘现状（`python -c` 直读）：

```ts
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export function j1MovementColumns(): ColumnDef[] {
  return defineColumns([
    { key: '项目',     label: '项目',     is_label: true, flat: true },
    { key: '期初余额', label: '期初余额', format: 'amount' },
    { key: '本期增加', label: '本期增加', format: 'amount' },
    { key: '本期减少', label: '本期减少', format: 'amount' },
    { key: '期末余额', label: '期末余额', format: 'amount' },
  ])
}
```

原本地 `interface ColumnDef {key,label,is_label}` 已删除（无 `flat`/`format` 字段，表达不了单级声明），
改 import 共享 `disclosureColumnDefs.ColumnDef`；`defineColumns` 已按 Task 1.2 透传 `group`/`flat`（落盘复核过）。
契约测试 `composables/__tests__/j1h4DisclosureColumns.spec.ts` 实跑 **13/13 绿**
（J1 6 条：逐字 label / `flat` 且 0 处 `group` / 4 列 `format:'amount'` / Property 2 / Property 6 / Property 1 两变体；H4 7 条）。
→ 7.2 剩余口子只有**命名契约**（决策 B）与**合计行**（决策 A），列头本身已收口。

**⑦ 🔴 `read_file` 陈旧本轮踩中两次，判定一律以 `python -c` 落盘为准。**
`j1NoteSectionMap.ts` 首次 `read_file` 返回的是**并发会话改动前**的版本（本地 `ColumnDef`、
无 `flat`/`format`），`check_disclosure_columns_coverage.py` 返回的是**加白名单前**的版本
（`COLUMN_BUILDERS` 无 `buildJ1SyncPayload`）。两处都是先看到"测试应该红/守卫应该报未覆盖"、
实跑却相反才发现。批 4 沿用同一纪律：**先跑，再读；读完用 `python -c` 复核**。

#### 1. 源模板与附注模板定位（证据坐标）

| 循环 | 源 xlsx | 披露 sheet（`wb.sheetnames` 逐字） | 附注章节 | 附注模版 md | 校验预设 | registry |
|---|---|---|---|---|---|---|
| J1 上市 | `…/4.风险应对-实质性程序（D-N）/J 职工薪酬循环/J1 应付职工薪酬.xlsx` | `附注披露信息（上市公司）`（全角） | 五、40 | `上市报表附注.md` **L4385~L4444** | **F39-1~F39-12a（14 条）** | ✅ 有条目 |
| J1 国企 | 同上 | `附注披露信息（国有企业）`（全角 + **「国有企业」非「国企」**） | 八、40 | `国企报表附注.md` **L3472~L3514** | 同上（两份 bucket 逐字相同） | ✅ 有条目 |

裁决口径核查（T0.2 / T0.3）：

- **`note_check_preset_formulas.json` 有条目 → 裁决者到位。** `listed` / `soe` 两个 bucket
  各 14 条 `section_title == '应付职工薪酬'`，内容逐字相同，`table_name` 为
  `① 应付职工薪酬总表` / `② 短期薪酬明细表` / `③ 设定提存计划表` —— **确认两变体都是 3 张表**。
- **🔴 T0.2 的「id 前缀 = 附注节号」在 J1 不成立**：预设 id 前缀是 **`F39`**、`note_section` 写
  `五、39`，而 `note_template_variant_matrix.json` 的 `ying_fu_zhi_gong_xin_chou` =
  `listed 五、40 / soe 八、40`，`consol_note_sections_*` 又是 `五-40-1`（listed）/ `五-41-1`（soe）
  —— **三套编号并存，彼此错开 1**。故 J1 的预设条目只能按 `section_title` 匹配，按节号找必定落空
  （`F40-*` 在两个 bucket 里都是**应交税费**）。→ 登记遗留 ⑤，并把这条写进 T0 备注供批 4 参考。
- 章节号取自 `note_template_variant_matrix.json`：`ying_fu_zhi_gong_xin_chou`
  `soe_standalone/soe_consolidated = 八、40`、`listed_standalone/listed_consolidated = 五、40`
  —— 与 `J1_NOTE_SECTION` 常量逐字一致。
- **R8 核对（与批 2 遗留 ⑦ 相反，J1 是干净的）**：`note_workpaper_sync_registry.json`
  `entries[31]` = `{"wp_code":"J1","listed":"五、40","soe":"八、40","sheet_listed":"附注披露信息（上市公司）","sheet_soe":"附注披露信息（国有企业）","source_file":"…/composables/j1NoteSectionMap.ts"}`
  → **registry ↔ `J1_DISCLOSURE_SHEET_NAME` 常量 ↔ 源 xlsx tab 名三方逐字一致**，
  且 `build*SyncPayload` 引用常量而非字面量、两个 `.vue` 全文无 `'J1-note` 字符串。R8 无欠账。
- BCD 类 md：`J 职工薪酬循环` 目录未收 J1 披露 sheet 条目，本批不作第 5 源。

#### 2. `J1TabDisclosureListed`（五、40，3 张表，全单行表头）

推送键（现状即正确）：`应付职工薪酬`、`短期薪酬`、`设定提存计划`、`_note_texts`（元数据）。
三键与 `note_template_listed.json` 五、40 的 `tables[0..2].name` **逐字一致**（T7-3 无违反）。

三张表 `headers` 在 note_template / md / consol 三处完全相同，故**共用一份 5 列定义**
（`j1MovementColumns()`，与预设「三表同结构」一致）：

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `项目` | `项目` | note_template 五、40 T0/T1/T2 `headers[0]='项目'`；源 A6/A17/A40=`项 目`；附注模版 L4387/L4406/L4432=`项  目`；consol 五-40-1；UI L44/L104/L162=`项 目` | `is_label` + **`flat`** |
| 1 | `期初余额` | `期初余额` | 附注模版 L4387 + note `headers[1]` + consol 五-40-1 + **预设 F39-2/F39-3 明写「期初余额」**；源 B6=`上年年末数`、UI L50/L113/L171=`上年年末数` → **取预设/附注模版** | `format:'amount'` |
| 2 | `本期增加` | `本期增加` | 源 C6/C17/C40；附注模版 L4387；note `headers[2]`；预设 F39-3；UI L57/L119/L177 —— **五源一致** | `format:'amount'` |
| 3 | `本期减少` | `本期减少` | 源 D6/D17/D40；附注模版 L4387；note `headers[3]`；预设 F39-3；UI L64/L125/L183 —— **五源一致** | `format:'amount'` |
| 4 | `期末余额` | `期末余额` | 附注模版 L4387 + note `headers[4]` + consol + **预设 F39-1/F39-3**；源 E6=`期末数`、UI L71/L131/L189=`期末数` → **取预设/附注模版** | `format:'amount'` |

**三源裁决用到两次（T0.3）**：上市源 xlsx 与底稿 UI 都写 `上年年末数` / `期末数`，
而**裁决者预设**（F39-1「报表.应付职工薪酬期末 = ①总表.合计行.**期末余额**」、
F39-2「…期初 = ①总表.合计行.**期初余额**」）与附注模版 md、note_template、consol 四家都写
`期初余额` / `期末余额` → **取 `期初余额` / `期末余额`**。这正是 `j1NoteSectionMap.ts` 头注释
Decision 2 的内容，本次为其补齐了裁决者背书（原 Decision 2 只引了模板）。
→ 负向断言（T5 第 6 族）应显式反断 `not.toContain('上年年末数')` / `not.toContain('期末数')`。

**预设裁决（14 条，逐条落到本 Tab）**：

| 预设 | 结论 |
|---|---|
| F39-1 / F39-2 | 报表.应付职工薪酬期末·期初 = ①总表.合计行.期末余额·期初余额 → 列名定为 `期末余额`/`期初余额`；**要求①表有合计行**（见决策 A） |
| F39-3 / F39-6 / F39-7 | ①/②/③ 三表均「期初 + 本期增加 − 本期减少 = 期末（每行独立）」→ **确认 4 个金额列并列**，`本期增加`/`本期减少` **不是**「本期」下的子列 → §0⑤ 的凭空 `本期` 分组必须用 `flat` 压掉 |
| F39-4 / F39-5 | ①总表.「短期薪酬」行.各列 = ②表.合计行.各列；①总表.「设定提存计划」行.各列 = ③表.合计行.各列 → **三表必须同列集同序**（现状共用一份 `columns`，正确） |
| F39-8 / F39-9 / F39-10 | 三表「sum(合计行以外的明细行) = 合计行」，且②③表含「其中：」子项时子项之和 = 对应父项、合计行不含子项 → 行结构保持底稿原样（`indent` 行即「其中：」子项），**要求合计行存在** |
| F39-11 / 11a / 12 / 12a | 报表「其中：应付工资 / 应付福利费」行 ↔ ②表「工资、奖金、津贴和补贴 / 职工福利费」行 → 行名必须逐字保留（现状 `DEFAULT_SHORT_TERM` 已逐字对齐源 A18/A19） |

**行来源核对**：`summary` / `shortTerm` / `postEmployment` 三段的默认行逐字对齐源 xlsx
（A7~A10 / A18~A33 / A41~A48），`indent: 1` 对应源模板「其中：1．…」缩进层。
底稿（3）辞退福利段**只有文字无表**（源 A52~A54），现状经 `_note_texts` 推送，
与附注模版 L4444 之后无第 4 张表一致 → **无欠账**。

#### 3. `J1TabDisclosureSoe`（八、40，3 张表，全单行表头）

推送键（现状）：`应付职工薪酬列示`、`短期薪酬列示`、`设定提存计划列示`、`_note_texts`。
前两键与 `note_template_soe.json` 八、40 `tables[0].name` / `tables[1].name` 逐字一致；
第三键**模板侧无同名表**（`tables[2].name` 重名为 `短期薪酬列示`）→ 见遗留 ①。

列定义与上市**完全相同**（`j1MovementColumns()` 一份两用），且国企侧四源本就一致，无裁决冲突：

| # | key | label | 逐字证据 | 属性 |
|---|---|---|---|---|
| 0 | `项目` | `项目` | note_template 八、40 T0/T1/T2 `headers[0]='项目'`；源 A8/A16/A31=`项  目`；附注模版 L3476/L3487/L3504；consol 五-41-1；UI L44/L90/L139=`项 目` | `is_label` + **`flat`** |
| 1 | `期初余额` | `期初余额` | 源 B8/B16/B31；附注模版 L3476/L3487/L3504；note `headers[1]`；consol 五-41-1；预设 F39-2；UI L50/L99/L148 —— **六源一致** | `format:'amount'` |
| 2 | `本期增加` | `本期增加` | 源 C8/C16/C31；附注模版 L3476；note `headers[2]`；预设 F39-3；UI L56/L105/L154 —— **五源一致** | `format:'amount'` |
| 3 | `本期减少` | `本期减少` | 源 D8/D16/D31；附注模版 L3476；note `headers[3]`；预设 F39-3；UI L62/L111/L160 —— **五源一致** | `format:'amount'` |
| 4 | `期末余额` | `期末余额` | 源 E8/E16/E31；附注模版 L3476；note `headers[4]`；consol 五-41-1；预设 F39-1；UI L68/L117/L166 —— **六源一致** | `format:'amount'` |

**T4 变体列集差异：本批为零。** 两变体列数、列序、列名、`group`/`flat` 声明**全同**
（与批 2 的 K5 / K7 相反），`mapDisclosureRows` 的 `values = [beginBalance, increase, decrease, endBalance]`
两版共用即正确，**不需要按变体分支**。
→ T5 第 8 族（变体重排守卫）在 J1 退化为「两变体 `values` 同序」的反向断言：
断 `buildJ1SyncPayload` 两变体产出的每行 `values.length === 4` 且顺序一致，
并显式反断"不得为国企另造一份列定义"。

**行来源核对**：国企默认行逐字对齐源 A9~A13 / A17~A28 / A32~A39。
国企 ②表源 A20 是 `其中：医疗保险费`（拆开写），而 `note_template_soe` T1 与附注模版 L3492 写
`其中：医疗保险费及生育保险费`（合并写）—— **行标签口径差异，不是列头问题**，
且行标签真源在底稿（`_source=workpaper` 时投影器不与模板 `_tables` 合并）→ 记入遗留 ③，本批不动。

底稿国企侧「说明」单段（源 A41~A44 四行提示）经 `_note_texts`（`SOE_NOTE_KEYS` 单键 `soe`）推送 → 无欠账。

#### 4. 需拍板的三处（7.2 开工前定）

| # | 决策 | 备选 | 建议 |
|---|---|---|---|
| **A** | **三张表都不推「合计」行** —— `snapshot` 取 `summaryData/shortTermData/postEmploymentData`（纯数据行），而 `合 计` 是 `useJ1DisclosureSections` 的 computed（`buildDisclosureSubtotal('s-total','合 计',…)` 等三处），**未进载荷**。后果：附注三表无合计行 → 预设 F39-1/2/4/5/8/9/10 **七条全部落空**，且 `note_template` 三表都有 `{"label":"合计","is_total":true,"row_type":"total"}` 行 | (A1) 7.2 同批把三个 subtotal 追加为各表末行（`is_total: true`，label 用现成的 `合 计`，与 `DISCLOSURE_TOTAL_LABEL` 已逐字一致）；(A2) 只做列头，把合计行登记为遗留另立 spec | **A1**。改动点单一（`buildJ1SyncPayload` 里三处 `mapDisclosureRows(...)` 后 concat 一行），`合 计` 字面已现成不需新造，且不补的话本批"列头对了但附注勾稽全废"。⚠️ 严格说属**行内容**而非列头，若判超出 7.2 范围则按 A2 登记 —— 但必须显式登记，不能默认过去 |
| **B** | `j1MovementColumns()` **不匹配 T1 命名契约**（`build[A-Z]\w*Columns\b`），且返回 `ColumnDef[]` 而非 `Record<string, ColumnDef[]>`；现状覆盖判定完全依赖 `COLUMN_BUILDERS` 白名单里的 `buildJ1SyncPayload` | (B1) 加两个薄壳导出 `buildJ1ListedColumns()` / `buildJ1SoeColumns()` 返回 `Record<string, ColumnDef[]>`（键 = `J1_SUB_TABLE_KEYS[variant]` 三个值），`j1MovementColumns` 降为 module-private 表级 helper，同批改 `j1h4DisclosureColumns.spec.ts` 断言；(B2) 保持现状，靠白名单 | **B1**。T1 明写「扩白名单是绕过不是覆盖」；且 Task 9.1 的全 Tab 契约测试要「扫描全部 `build*Columns()`」，不改名 J1 会被整体漏扫。B1 是纯重命名 + 薄壳，零行为变化（`buildJ1SyncPayload` 内部改调 `buildJ1{Listed,Soe}Columns()[key]`）。⚠️ 该文件**并发会话正在改** → 只许 `str_replace` 增量，禁 `fs_write` 整文件覆盖 |
| **C** | `ColumnDef.key` 用**中文**（`'期初余额'`）而非各循环通行的 snake_case（`'begin_amount'`） | (C1) 保持；(C2) 改 snake_case 与其他循环统一 | **C1**。端到端已实跑验证正确（位置化 `values` 经 `normalize_sub_table_data` 按 `columns` 顺序落到中文键，`project_sub_tables` 取值 `[100,20,5,115]` 无误）；改 key 会让存量已同步项目的 `_sub_table_columns` 快照与新 key 不匹配、必须逐项目重同步（T7-1），收益仅"风格统一"。→ 在契约测试里把 `cols.map(c => c.key)` 钉死即可 |

#### 5. 条件表 / 变体分支登记（供 7.2 与 9.1 契约测试）

| 项 | 结论 |
|---|---|
| **条件表** | **无。** 6 张表（两变体各 3 张）全部无条件推送（`buildJ1SyncPayload` 直接组装三键，无 `if rows.length`）→ `columns` 无需 `includeX` 分支，Property 1 在任何入参下恒成立（空数组也推空表） |
| **`values` 变体分支（T4）** | **无。** 两变体列集/列序/列名全同，`mapDisclosureRows` 一份两用即正确。这是批 1~3 里唯一不需要 T4 分支的批次 → T5 第 8 族改写成「两变体同序」反向断言 |
| **两行表头** | **无。** 6 张表全单行 → 6 处 `flat`（实际共用 1 份定义，标 1 次），`group` 0 处 |
| **`_note_texts`** | 已在 `sub_table_data` 内（上市 3 段 `shortTerm`/`postEmployment`/`severance`，国企 1 段 `soe`），后端可读 → 无需改造 |
| **`_removed_table_keys`（R7）** | 未接入。J1 子表名**全静态**（`J1_SUB_TABLE_KEYS` 常量），无审计师自定义命名 → 孤儿表风险低，登记遗留 ⑥ 不在本批 |
| **账龄标签（R6）** | **N/A**，J1 无账龄表。合计行字面 `合 计` 已与 `DISCLOSURE_TOTAL_LABEL` 逐字一致（但未推送，见决策 A） |

#### 6. 汇总

| Tab | 数据子表数（7.2 推送） | 单行表头 | 两行表头 | 需标 `flat` | 需 `group` | allowlist 候选 |
|---|---|---|---|---|---|---|
| `J1TabDisclosureListed`（五、40） | 3（`应付职工薪酬` / `短期薪酬` / `设定提存计划`） | 3 | 0 | 3（共用 1 份定义，标 1 次） | 0 | 0 |
| `J1TabDisclosureSoe`（八、40） | 3（`应付职工薪酬列示` / `短期薪酬列示` / `设定提存计划列示`） | 3 | 0 | 3（同上，与上市共用） | 0 | 0 |
| **合计（2 个 Tab）** | **6** | **6** | **0** | **6（1 份 `ColumnDef[]`）** | **0** | **0** |

**allowlist 候选：无。** 6 张表的每个 label 都能同时指到：源 xlsx 单元格坐标 +
附注模版 md 行号 + `note_template` `headers[]` + `consol_note_sections_*` `headers[]` +
**校验预设 F39-1~F39-12a 明文**。两处口径冲突（上市 `上年年末数`/`期末数`）已按 T0.3 三源裁决落定，
不存在"指不到源"的 label。
「无法确认」的部分不是列头，而是**行内容**（合计行未推送 → 决策 A；国企②表「医疗保险费」行名口径 → 遗留 ③）。

#### 7. 遗留（超出 7.2 范围，只登记不改）

| # | 问题 | 证据 | 归属 |
|---|---|---|---|
| ① | **`note_template_soe.json` 八、40 的 `tables[1].name` 与 `tables[2].name` 重名为「短期薪酬列示」**（模板笔误）。现状 Decision 3 把第三键取成 `设定提存计划列示`（附注模版国企 **L3502** `### 设定提存计划列示` 确有此标题 → **判定正确**），代价是模板 T2 恒空 + 附注多一个模板未登记的 TAB。`sub_table_data` 是 dict，重名键在物理上也无法并存 | `note_template_soe.json` 八、40 T1/T2 `name` 逐字相同；`text_sections` = `["### 应付职工薪酬列示","### 短期薪酬列示","### 设定提存计划列示"]` | 未来 J1 alignment spec（本 spec §不做：不动附注模板 JSON） |
| ② | **三张表都不推合计行**，预设 F39-1/2/4/5/8/9/10 七条无落点 | 两个 `.vue` 的 `snapshot` 取 `*Data.value`；`useJ1DisclosureSections` 的 `summaryTotal`/`shortTermSubtotal`/`postEmploymentSubtotal` 为独立 computed，`summaryRows = [...summaryData.value, summaryTotal.value]` 仅供 UI | **决策 A**：建议 7.2 同批修；若判超范围则本条即为遗留 |
| ③ | 行标签口径差异（非列头）：国企②表源 A20 `其中：医疗保险费`（另有 A22 `生育保险费`）vs `note_template_soe` T1 / 附注模版 L3492 `其中：医疗保险费及生育保险费`（合并写）；上市①表源 A10 `一年内到期的其他福利` 无数值格 | 源 xlsx A20/A22 vs md L3492；源 A10 B10:E10 空 | J1 alignment spec；**禁在补 columns 时改行名** |
| ④ | `note_template_listed.json` 五、40 T1 的 `{"label":"……","row_type":"data"}` 是**源模板占位说明被 md 重建脚本当数据行**（源 A24=`……`，语义为"可继续添加社保子项"）→ 渲染成一行空披露数据。同 H1 上市 A65/A74 先例 | `note_template_listed.json` 五、40 T1 rows[6]；源 xlsx A24；附注模版 L4414 | J1 alignment spec（语义应移入 `tables[].guidance`） |
| ⑤ | **预设 id 编号与附注章节号错开**：`F39-*` ↔ `variant_matrix` 五、40 / 八、40 ↔ consol 五-40-1（listed）/ 五-41-1（soe），三套编号并存；两个 bucket 的 `F40-*` 都是**应交税费**。→ T0.2「id 前缀 = `F{节号}`」在 J1 不成立，必须按 `section_title` 匹配 | `note_check_preset_formulas.json` `listed[456..469]`（14 条）/ `soe[460..473]`（14 条）的 `id`/`note_section`/`section_title`；`note_template_variant_matrix.json` `ying_fu_zhi_gong_xin_chou` | 写入 T0 备注（供批 4 与后续循环）；编号收敛属附注编号治理，另立 spec |
| ⑥ | R7 动态孤儿表清理未接入（无 `_removed_table_keys`）。J1 子表名全静态，风险低；但若遗留 ① 将来改名（`设定提存计划列示` → 模板修正后的名字），旧键会永久残留 | 两个 `.vue` 的 POST body；`j1NoteSectionMap.ts` 无 `buildRemovedTableKeys` 引用 | R7 后续循环接入 |
| ⑦ | 三张表 `tables[].guidance` 全为 `None`（两变体 6 张），而源模板红字提示内容丰富（上市 A13~A15 辞退福利/一年内到期口径、A36~A38 非货币性福利与利润分享计划说明、A51 其他长期职工福利界定；国企 A41~A44 三条披露要求 + 「设定受益计划详见附注八、47」）→ 附注 TAB 无编制提示 | `note_template_{listed,soe}.json` 八/五、40 三表 `guidance` 均缺失；源 xlsx 上述单元格 | J1 alignment spec（照 K1 §五、8 / H1 §五、22 的 `guidance` 范式补） |

---

### Task 11.3 Playwright 实测纪实（2026-07-30）

驱动方式：Playwright MCP `Not connected` → 按 memory 铁律改用 **chrome-devtools MCP**，
复用已登录 tab（token 在 sessionStorage，新开 tab 必被踢回 `/login`），
把「读 API → `$router.push` 到底稿披露 sheet → 等组件根挂载 → 点『同步到附注』→ 轮询 API →
读附注页 DOM」压进**单个 `evaluate_script` 原子脚本**（分步调用会被并发会话导航走）。
选择器一律带组件根作用域（`.k6-tab-disclosure-soe` / `.k7-tab-disclosure-listed` 等）。

**T7-1 复验（快照语义）**：4 个章节同步前 `last_sync_at = null`、`_sub_table_columns` 不存在，
`_tables[]._column_groups` 为 **ABSENT**（键根本不存在，模板生成时快照）；
点过「同步到附注」后 `last_sync_source = workpaper`、`_sub_table_columns` 才写入 `group`/`flat`。
→ 印证「改代码不改存量附注，必须重新同步一次」。

| 变体 | 项目 | 底稿 sheet（真实 tab 名） | 章节 | 同步前 `_column_groups` | 同步后 `_column_groups` |
|---|---|---|---|---|---|
| K6 上市（两级） | 重药控股安徽有限公司_2025 `0ec33ac9` | `附注披露信息（上市公司）` | 五、11 | `_tables` 整个缺失 | `[{期末余额,start:1,span:3},{上年年末余额,start:4,span:3}]` |
| K6 国企（两级） | 重庆医药集团宜宾医药…临港店_2025 `c8621493` | `附注披露信息(国企）` | 八、12 | 4 张模板表全 **ABSENT**（headers 被压成 3 列） | `[{期末数,start:1,span:3},{期初数,start:4,span:3}]` |
| K7 上市（flat） | 同 `0ec33ac9` | `附注披露信息（上市公司）` | 五、51 | `_tables` 整个缺失 | `[]`（显式单级） |
| K7 国企（flat） | 同 `c8621493` | `附注披露信息（国有企业）` | 八、56 | 2 张模板表 **ABSENT** | `[]`（显式单级） |

**附注页 DOM 复验**（`/projects/{pid}/disclosure-notes?section=…&year=2025` →
`.gt-de-note-table .el-table__header-wrapper thead tr`）：

| 章节 | thead 行数 | 第 1 行 `th`（text / colspan / rowspan） | 第 2 行 |
|---|---|---|---|
| 五、11 K6 上市 | **2** | `项目` 1/**2** · `期末余额` **3**/1 · `上年年末余额` **3**/1 | `账面余额`·`减值准备`·`账面价值` ×2（各 1/1） |
| 八、12 K6 国企 | **2** | `项目` 1/**2** · `期末数` **3**/1 · `期初数` **3**/1 | 同上 6 个子列 |
| 五、51 K7 上市 | **1** | `项目`·`期初余额`·`本期增加`·`本期减少`·`期末余额`·`形成原因`（全 1/1） | — |
| 八、56 K7 国企 | **1** | `项目`·`期初余额`·`本期增加`·`本期减少`·`期末余额`（全 1/1） | — |

→ 两级：父表头串按变体正确分叉（`期末余额/上年年末余额` vs `期末数/期初数`），同名子列不去重；
→ flat：**无凭空「本期」父表头**，且 K7 变体列集差异（上市多 `形成原因`）在 DOM 上成立。

**DB 侧独立印证**（postgres 只读）：`disclosure_notes.table_data._sub_table_columns`
四条记录逐一含 K6 的 6 个 `group` 串 / K7 的 `flat: true`，`last_sync_source = workpaper`。

**项目实况说明（不假绿）**：8 个在册项目 `applicable_standard_v2.entity_type` **全为 `soe`**
（唯一 listed 适用项目已软删，同 Task 3.3 结论）。但 **K6/K7 两个披露 Tab 均无
`applicable_standards` gating**，且 `0ec33ac9` 的附注是按**上市模板**生成的（章节号为 `五、x`，
与 Task 3.3 用它验 §五、9 存货一致）→ 上市变体是**真 UI 实测**（点的是底稿里的按钮），
不是 API 直灌；只是承载项目的 `entity_type` 字段为 soe。

**顺带确认（非本任务目标）**：K6 国企同步后附注只剩 1 张表 —— 投影器 `_source=workpaper`
时不与模板 `_tables` 合并，模板另 3 张表（减值准备变动 / 持有待售非流动资产 / 处置组）
底稿无数据来源，符合 §9 决策 A1/B1 与遗留 ④⑤ 的登记，不是本次回归。

---

### Task 11.4 Word 导出抽验纪实（2026-07-30）

目标：确认 Word 导出与附注 UI **消费同一份 `_column_groups`**，`group` 表出两行表头、
`flat` 表出一行表头。取证分两路，均为**真实已同步数据**（不是 `test_note_word_export_sub_table.py` 的合成夹具）。

#### 路线 A：真 docx HTTP 往返（`POST /api/projects/{pid}/notes/export-word`）

`0ec33ac9`（重药控股安徽，listed 模板）+ `sections=["五、9","五、11","五、51"]` →
`curl.exe -o tmp_11_4_listed.docx`（200 / 41326 B），python-docx 读回 `w:gridSpan` / `w:vMerge`：

| docx 表 | 表名（§五、9 存货） | 表头行数 | row0（text/colspan/vMerge） | row1 |
|---|---|---|---|---|
| 1 | 存货分类 | **2** | `项目` 1/restart · `期末余额` **3** · `上年年末余额` **3** | `账面余额`·`跌价准备/合同履约成本减值准备`·`账面价值` ×2 |
| 5 / 6 | 按组合计提存货跌价准备（+续） | **2** | `组合` 1/restart · `账面余额` **2** · `存货跌价准备` **3** · `账面价值` 1/restart | `金额`·`比例(%)`·`金额`·`计提标准`·`比例(%)` |
| 7 | 存货跌价准备及合同履约成本减值准备 | **2** | `项目` 1/restart · `期初余额` 1/restart · `本期增加` **2** · `本期减少` **2** · `期末余额` 1/restart | `计提`·`其他`·`转回或转销`·`其他` |
| 0 | 周转房 | **1** | `项目名称`·`期初余额`·`本期增加`·`本期减少`·`期末余额`（全 1/1） | 数据行 |
| 2 | 开发产品 | **1** | 7 列全 1/1 | 数据行 |
| 3 | 开发成本 | **1** | 7 列全 1/1（含 `预计竣工时间`/`预计总投资`） | 数据行 |
| 4 | 确认为存货的数据资源 | **1** | 5 列全 1/1 | 数据行 |
| 8 | 存货跌价准备…（续） | **1** | 3 列全 1/1 | 数据行 |

→ **Req 3.1/3.4 在 docx 侧成立**：`flat` 表**无**凭空「本期」（周转房/开发产品）与「预计」（开发成本）父表头；
两级表 row1 子列名不缺末列（`_build_two_level_header_rows` 的「row1 不补 rowspan 占位」约定在真数据上有效）。

#### 路线 B：真实记录 → `_note_tables` → `_render_table` → 落盘 docx（覆盖 K6/K7 四章节）

**为什么需要 B**：K6/K7 四个章节的底稿数据**全为 0**（`end_gross/…/increase/decrease` 皆 0），
`export()` 的 `_has_content`（= 共享 `note_has_data`，空表判定同口径）返回 **False** →
API 导出对这四节输出「本期无此项业务。」，docx 里**不生成表格**。这是 `disclosure-note-follow-actual-content`
的空表判定在起作用，**不是**本 spec 的回归。故对四节改用 in-process 渲染（脚本 `backend/tmp_11_4_word_spotcheck.py`，
已随任务删除）：读 DB 真记录 → `exporter._note_tables(note)`（真投影：`sub_table_data` + `_sub_table_columns` → `_column_groups`）
→ `exporter._render_table(doc, t)` → `doc.save()` → python-docx 读回。仍是 **docx 往返**，只跳过空章节闸门。

| 章节 | 变体 | 投影 `_column_groups` | docx 表头行数 | row0 | row1 |
|---|---|---|---|---|---|
| 五、11 | K6 上市 | `[{期末余额,1,3},{上年年末余额,4,3}]` | **2** | `项目` 1/restart · `期末余额` **3** · `上年年末余额` **3** | `账面余额`·`减值准备`·`账面价值` ×2 |
| 八、12 | K6 国企 | `[{期末数,1,3},{期初数,4,3}]` | **2** | `项目` 1/restart · `期末数` **3** · `期初数` **3** | 同上 6 子列 |
| 五、51 | K7 上市 | `[]` | **1** | `项目`·`期初余额`·`本期增加`·`本期减少`·`期末余额`·`形成原因`（全 1/1） | 数据行 `设备购置补助` |
| 八、56 | K7 国企 | `[]` | **1** | 同上去掉 `形成原因`（5 列全 1/1） | 数据行 `设备购置补助` |

#### 与 11.3 附注 UI 的一致性

Word `row0/row1` 的文本、colspan、`项目` 列纵向合并（`vMerge=restart/continue` ↔ UI `rowspan=2`）
与 11.3 记录的 `thead` 逐项一致；父表头串按变体正确分叉（`期末余额/上年年末余额` vs `期末数/期初数`）。
→ **Req 5.3/5.4 达成**：UI 与 Word 共用 `_column_groups` 单一真源，无第二套机制。

**顺带登记（非本任务范围）**：K6/K7 四节因数据全 0 而在交付 docx 中降级为「本期无此项业务。」；
若需在 Word 里看到这四张空骨架表，属空表判定口径问题，归 `disclosure-note-follow-actual-content`。
