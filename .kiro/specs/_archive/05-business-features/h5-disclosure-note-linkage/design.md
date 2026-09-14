# Design Document

## Overview

纯前端改动。后端 sync-from-workpaper + note_sub_table_projector 已就绪。新建 h5NoteSectionMap.ts 纯函数 + 修改 SOE 披露表(同步+跳转) + 修改审定表(bring-in 双科目)。仅 SOE 变体（listed 无独立油气章节）。

## Architecture

纯前端 spec。新建 1 文件 + 修改 3 文件 + 守卫 1 文件。后端零改动。

### 新建
- `composables/h5NoteSectionMap.ts` — 纯函数 + 列定义 + 常量

### 修改
- `h5/core/H5TabDisclosureSoe.vue` — 同步按钮 + 跳转按钮
- `h5/core/H5TabAdjudication.vue` — bring-in 双科目按钮
- `check_disclosure_columns_coverage.py` — COLUMN_BUILDERS 登记

## Data Models

### H5SyncPayload (前端→后端)

```
{
  wp_id: string,
  sheet_name: string,          // '附注披露信息（国有企业）'
  section_id: '八、25',
  current_standard: 'soe_standalone',
  year: number,
  sub_table_data: {
    '油气资产变动表': { rows: [...], is_total: boolean }
  },
  columns: {
    '油气资产变动表': ColumnDef[]
  },
  _note_texts: [{ section, title, text }]
}
```

### AdjudicationBringIn 双实例参数

| 实例 | subjectPrefix | direction | subjectCode |
|------|---------------|-----------|-------------|
| 原值 | 1631 | debit | 1631 |
| 折耗 | 1632 | credit | 1632 |

## Components and Interfaces

### h5NoteSectionMap.ts (新建)

- `H5_NOTE_SECTION = { soe: '八、25' }`
- `buildH5SyncPayload(opts): SyncPayload` — 纯函数构造载荷
- `H5_SOE_COLUMNS: Record<string, ColumnDef[]>` — 列头定义

### H5TabDisclosureSoe.vue (修改)

- 加「同步到附注」按钮 + syncToNote()
- 加「↩ 跳转回附注（八、25）」按钮

### H5TabAdjudication.vue (修改)

- 加「📥 从集中登记带入调整」按钮
- 两个 useAdjudicationBringIn 实例 + 两个 AdjudicationBringInDialog

## Correctness Properties

### Property 1: 子表键匹配附注模板

**Validates: Requirements 1.1**

buildH5SyncPayload 产出的 sub_table_data 子表键是 note_template_soe.json 八、25 tables[].name 的子集。

### Property 2: 列头为中文

**Validates: Requirements 1.2**

columns 每个 ColumnDef.label 为非空中文字符串。

### Property 3: year 正确传入

**Validates: Requirements 1.4**

sync payload.year 等于传入的 auditYear 参数（非 new Date 当前年）。

### Property 4: 上市版无同步按钮

**Validates: Requirements 1.7, 5.1**

H5TabDisclosureListed 无 sync-from-workpaper 调用。

### Property 5: 1631 direction=debit

**Validates: Requirements 3.2**

useAdjudicationBringIn 的 1631 实例参数 direction 恒为 debit。

### Property 6: 1632 direction=credit

**Validates: Requirements 3.3**

useAdjudicationBringIn 的 1632 实例参数 direction 恒为 credit。

### Property 7: 带入累加非替换

**Validates: Requirements 3.5**

apply 后 row[field] = 原值 + net（非 net）。

### Property 8: 覆盖率守卫 exit 0

**Validates: Requirements 4.1**

check_disclosure_columns_coverage.py --strict exit 0 且含 H5。

## Error Handling

- sync POST 失败 → ElMessage.error + 不改本地
- bring-in 无匹配 → ElMessage.info
- auditYear undefined → fallback 当前年-1
- 行数据全空 → 不发请求 + warning

## Testing Strategy

- vitest 8 测试（P1-P8）：h5NoteSectionMap.spec.ts + h5AdjudicationBringIn.spec.ts
- get_diagnostics + Vite transform 200 全改动文件
- live round-trip（可选 Task 8*）：备份→sync→GET→恢复→RESTORED_IDENTICAL
