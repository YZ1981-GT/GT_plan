# Design Document

## Overview

给 64 个披露 Tab 补齐「披露 Tab → 附注」的数据链路。不发明新机制——完整复刻 F2/K1 已验证的五件套，按循环分批推进，每批用同一套契约测试守住。

单个 Tab 的补齐 = 五件套：

1. **章节映射** `XNoteSectionMap.ts`（sheet_name ↔ 章节号，前端唯一真源）
2. **载荷构建器** `buildXSyncPayload`（composable 行模型 → `{sub_table_data, columns}`）
3. **列定义** 每张子表的 `ColumnDef[]`（对齐源 xlsx，`group`/`flat` 二选一表态）
4. **同步函数** `syncToDisclosureNotes`（打 `sync-from-workpaper`，手动按钮与自动同步共用）
5. **自动同步接线** `useDisclosureAutoSync` + `watch(实际数据源, ..., { deep: true })`

## Architecture

```
披露 Tab（用户录入）
  ├─ composable 行模型（既有，不动）
  │
  ├─[新] buildXSyncPayload(variant, wpId, year, snapshot)
  │      ├─ X_DISCLOSURE_SUBTABLE   子表名常量（须与 note_template tables[].name 逐字一致）
  │      ├─ buildXColumns()          ColumnDef[]（group / flat 二选一）
  │      └─ X_NOTE_SECTION[variant]  章节号（来自 XNoteSectionMap.ts）
  │
  ├─[新] syncToDisclosureNotes()    手动按钮 + 自动同步共用（幂等）
  │      └─ POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper
  │
  └─[新] useDisclosureAutoSync + watch(实际数据源)

后端（既有，全部复用）
  sync_from_workpaper
    ├─ manual_override 守卫
    ├─ sub_table_data 浅合并 + 空载荷 no-op
    ├─ _sub_table_columns 浅合并
    └─ _removed_table_keys 清理

生成产物
  XNoteSectionMap.ts ──(gen_note_wp_sync_registry.py --write)──▶
    note_workpaper_sync_registry.json（后端映射 + stale marker 用）
```

**分批策略**：按循环分批，每批 2~8 个 Tab。同批内 listed / soe 一起做（共用 payload 构建器与列定义，只有章节号和少量列名差异）。

## Components and Interfaces

### 1. 章节映射（每循环一个文件）

```typescript
// audit-platform/frontend/src/components/workpaper/composables/{x}NoteSectionMap.ts
export const X_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',   // 源 xlsx 中文 tab 名，非 wp_code
  soe: '附注披露信息（国企）',
} as const

export const X_NOTE_SECTION = {
  listed: '五、NN',   // 取自 note_template_variant_matrix.json
  soe: '八、NN',
} as const
```

### 2. 载荷构建器（每循环一个）

```typescript
export const X_SUBTABLE = {
  main: '源模板表名一',      // 🔴 逐字对齐 note_template_*.json 的 tables[].name
  detail: '源模板表名二',
} as const

export function buildXColumns(variant: Variant): Record<string, ColumnDef[]>
export function buildXSubTableData(variant: Variant, snapshot: XSnapshot): Record<string, unknown[]>
export function buildXSyncPayload(
  variant: Variant, wpId: string, year: number | null, snapshot: XSnapshot,
): SyncPayload | null   // 不适用变体返回 null
```

### 3. 同步函数（Tab 内，对齐 F2/E1 范式）

```typescript
const isSyncing = ref(false)
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildXSyncPayload(variant.value, props.wpId, auditYear.value, snapshot())
  if (!payload) return                     // 不适用变体
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步到附注「${X_NOTE_SECTION[variant.value]}」`)
  } catch (e) { ElMessage.error('同步到附注失败，请重试') }
  finally { isSyncing.value = false }
}
```

### 4. 自动同步接线

```typescript
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
// 🔴 监听实际数据源（与 snapshot 构建字段一致）；不加 _xxxMounted 防护
watch([...dataSources], () => { autoSync.scheduleAutoSync(syncToDisclosureNotes) }, { deep: true })
```

### 5. 守卫扩展（既有文件）

`disclosureAutoSyncCoverage.spec.ts`：每批完成后从 `MISSING_SYNC_PATH` 移出，`length` 断言同步下调。

### 6. 新增契约测试（每循环一个）

`__tests__/xNoteSubtableContract.spec.ts`（范式：`k1NoteSubtableContract.spec.ts`）：
子表名与模板逐字一致、`headers` 无空串、每表 `group`/`flat` 二选一、章节号存在于模板。

## Data Models

### `SyncPayload`（既有契约，不变）

```typescript
interface SyncPayload {
  wp_id: string
  sheet_name: string          // 源 xlsx 中文 tab 名
  section_id: string          // 附注章节号，如 '五、9'
  current_standard: string    // 'listed_standalone' | 'soe_standalone' | …
  sub_table_data: Record<string, unknown[]>   // {表名: [业务键行]}
  columns?: Record<string, ColumnDef[]>
  year?: number
}
```

### `ColumnDef`（既有，不变）

```typescript
interface ColumnDef {
  key: string; label: string; is_label?: boolean
  group?: string      // 多级表头父级；与 flat 互斥
  flat?: boolean      // 显式单级表头（抑制前缀推断）
  format?: 'amount' | 'percent' | 'text'
}
```

### 批次划分（64 个 Tab / 35 循环）

| 批 | 循环 | Tab 数 | 备注 |
|----|------|--------|------|
| 1 | G4 G5 G6 G8 G9 G10 G11 G12 | 15 | G 循环金融工具，结构相近可复用 |
| 2 | H4 H5 H6 H7 | 6 | H 循环长期资产 |
| 3 | L2 L4 L5 L6 L7 L8 | 12 | L 循环负债 |
| 4 | M1~M10 | 19 | M 循环损益类，多为简表 |
| 5 | N2 N3 N4 N5 | 7 | N 循环 |
| 6 | D2 F4 J2 | 5 | 🔴 D2/F4 与 in-flight spec 重叠，须最后做并协调 |

## Correctness Properties

### Property 1: 子表名与模板逐字一致

对任意已补齐的 Tab 与 variant，`buildXSubTableData` 产出的每个键都存在于
`note_template_{variant}.json` 对应章节的 `tables[].name` 中。

**Validates: Requirements 1.5, 2.4**

### Property 2: 章节号存在于模板

对任意已补齐的 Tab，`X_NOTE_SECTION[variant]` 在 `note_template_{variant}.json`
的 `sections[].section_number` 中存在。

**Validates: Requirements 2.1, 2.5**

### Property 3: 列定义必表态

对任意已补齐 Tab 的任意子表，其 `ColumnDef[]` 满足「至少一列有 `group`」异或
「至少一列有 `flat`」，两者不同时出现。

**Validates: Requirements 1.6, 3.3**

### Property 4: 表头纯文本

对任意已补齐 Tab 的任意 `ColumnDef.label` / `group`，不含 HTML 标记（`<...>`）。

**Validates: Requirements 3.4**

### Property 5: 不适用变体不同步

若项目适用准则与 Tab variant 不匹配，则 `buildXSyncPayload` 返回 `null`，
且 `syncToDisclosureNotes` 不发出 HTTP 请求。

**Validates: Requirements 1.4**

### Property 6: 自动同步与手动同源

自动同步触发的 `syncFn` 与手动按钮调用的是同一个 `syncToDisclosureNotes` 引用，
故两者产出的 `table_data` 逐键相等（除时间戳）。

**Validates: Requirements 1.3, 5.1**

### Property 7: 缺口清单单调收缩

`MISSING_SYNC_PATH` 的长度在每批完成后严格减少，且不含任何已具备同步链路的 Tab。

**Validates: Requirements 4.2, 4.5**

### Property 8: 既有 Tab 零影响

补齐任一批次后，原 90 个已接链路 Tab 的源码中同步相关片段不变，
且其契约测试结果不变。

**Validates: Requirements 5.1, 5.4**

## Error Handling

| 场景 | 处理 |
|------|------|
| 目标章节在模板中不存在 | 先补模板章节（幂等脚本），不同步到不存在的章节 |
| 子表名与模板不一致 | 契约测试失败，阻止合入（否则产生孤儿子表） |
| 源 xlsx 找不到对应披露 sheet | 该 Tab 转入「显式豁免」清单并写理由（R1.7） |
| 同步 HTTP 失败 | 手动路径 `ElMessage.error` 提示重试；自动路径静默（`useDisclosureAutoSync` 已吞） |
| 不适用变体 | `buildXSyncPayload` 返回 null，不发请求，不报错 |
| 章节已被手工编辑 | 沿用后端 manual_override 守卫，返回 `blocked_by_manual_override` |

## Testing Strategy

**每循环契约测试**（`xNoteSubtableContract.spec.ts`，范式 `k1NoteSubtableContract.spec.ts`）：
子表名逐字一致（Property 1）、章节号存在（Property 2）、列定义表态（Property 3）、
表头纯文本（Property 4）、不适用变体返回 null（Property 5）。

**载荷构建器单测**：给定 snapshot → 断言 `sub_table_data` 行数与字段、`columns` 结构。

**守卫**：`disclosureAutoSyncCoverage.spec.ts` 每批后更新 `MISSING_SYNC_PATH` 与 `length` 断言（Property 7）。

**回归**：每批跑一次既有附注相关全量（前端 F2/K1/F1/D2 系列 + 后端 note_* 系列），
不允许放宽断言（Property 8）。

**浏览器实测**（每批抽 1~2 个 Tab）：改数据 → 不点同步 → 查 `disclosure_notes.table_data`
确认 `_last_sync_at` 前移且值正确。Playwright MCP 不可用时改用 chrome-devtools MCP +
postgres MCP 交叉验证（比截图更硬）。

**先读源模板**：每个循环开工前用 openpyxl 逐 sheet 读源 xlsx 披露表 + 交叉验证
附注模版 md，禁止按「常识」造列（铁律）。
