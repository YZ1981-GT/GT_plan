# Design Document

## Overview

在披露表 → 附注的单向同步链上补齐**列头元数据 + 单点投影器**，让 `sub_table_data` 在附注模块与 Word 导出中忠实渲染成源模板表样。核心思路：**列头留在各披露组件（源对齐唯一真源），随载荷携带 `_columns`；后端存储后，用一个纯函数投影器在读取时把 `sub_table_data + _columns` 转成渲染器既有的 `_tables[]` 格式**——前端 `currentNoteTables` 与 `note_word_exporter` 无需理解 `sub_table_data`，只消费 `_tables`（现已支持），改动面最小、回归风险最低。

## Architecture

### 组件与数据流

```
┌────────────────────────────┐   sync payload                ┌──────────────────────────────┐
│ Disclosure_Tab_Component /  │  { section_id, current_standard,│ POST sync-from-workpaper       │
│ CNote_Component             │──  sub_table_data, _columns } ─▶│ → sync_from_workpaper()        │
│ (源对齐列头唯一真源)         │                                │   合并 sub_table_data + _columns │
└────────────────────────────┘                                │   → disclosure_notes.table_data │
                                                               └───────────────┬────────────────┘
                                                                               │ 读取（纯函数投影，非持久）
                                        ┌──────────────────────────────────────┴───────────────┐
                                        ▼                                                        ▼
                        get_note_detail → project_sub_tables()                    note_word_exporter → project_sub_tables()
                                        │ 注入 table_data._tables                                  │ 复用同一 _tables
                                        ▼                                                        ▼
                        DisclosureEditor.currentNoteTables 渲染                   Word 文档表格
```

### 关键架构决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | **投影器放后端**（`note_sub_table_projector.py`）| 附注模块详情 API 与 Word 导出都在后端消费，单点实现避免前后端两套逻辑漂移；前端 `currentNoteTables` 已支持 `_tables`，零/极小改动。 |
| D2 | **列头随载荷 `_columns` 携带，不建中央字典** | 列头权威来源是各组件既有 `<el-table-column label>` / C 类 schema（对照源模板编制）；就地声明避免中央字典重复与漂移，符合"单一真源"。 |
| D3 | **`_columns` 存 `table_data._sub_table_columns`，与 sub_table_data 同款合并语义** | 按子表 key 浅合并、空载荷 no-op，与 Requirement 8 一致，H4 只推部分子表不清空其余列头。 |
| D4 | **投影为纯函数、读时执行、不持久化 `_tables`** | 避免与 Engine_Fill_Path 的持久 `_tables` 混淆；`sub_table_data` 仍是权威存储，`_tables` 是派生视图。 |
| D5 | **优先级由 `_source` 单点决策** | `_source in (workpaper, workpaper_html)` 且 sub_table_data 非空 → 投影结果为权威 `_tables`；否则不投影、沿用 Engine_Fill_Path。杜绝重复表/覆盖。 |
| D6 | **降级不杜撰列头** | 无 `_columns` 时不以英文字段键当列头（Requirement 3/7），仅以 `label` 列可读呈现或标"待配置列头"，绝不 crash/清空。 |

## Components and Interfaces

**后端（新增/改）**
- `backend/app/services/note_sub_table_projector.py`（新增）：纯函数 `project_sub_tables(table_data: dict) -> list[dict]`。
- `backend/app/services/wp_disclosure_sync_service.py`（改）：`sync_from_workpaper` / `sync_from_html` 存储并浅合并 `_sub_table_columns`；`SyncFromWorkpaperRequest` 已由 dict 承载，服务签名增可选 `sub_table_columns`。
- `backend/app/routers/wp_disclosure_sync.py`（改）：请求体加 `columns: dict[str, list[dict]] | None`。
- `backend/app/routers/disclosure_notes.py`（改）：`get_note_detail` 读时注入投影 `_tables`（按 D5 优先级）。
- `backend/app/services/note_word_exporter.py`（改）：导出前对 workpaper 来源记录调用同一投影器得到 `_tables`。

**前端（改）**
- 新增共享类型/助手 `audit-platform/frontend/src/components/workpaper/composables/disclosureColumnDefs.ts`：`ColumnDef` 类型 + `defineColumns()` 助手。
- 各 `*DisclosureSyncPayload.ts` / `*TabDisclosure*.vue` / `GtCNoteTable.vue`：载荷加 `_columns`（分波推进，见 tasks）。
- `DisclosureEditor.vue::currentNoteTables`：确认消费后端注入的 `_tables`；补 `sub_table_data`+`_columns` 的**客户端兜底投影**（当后端未注入时，前端用相同规则投影，保证过渡期一致）。

**CI 守卫（新增）**
- `backend/scripts/check/check_disclosure_columns_coverage.py`：扫描 `sync-from-workpaper` 调用点核对 `_columns` 覆盖，`--strict` 阻断。

## Data Models

### ColumnDef（列头定义，前端声明 + 载荷传输 + 后端消费）

```ts
interface ColumnDef {
  key: string          // 对应 sub_table_data 行对象的字段键（如 'end_gross'）
  label: string        // 中文列头，取自组件既有源对齐定义（如 '期末账面余额'）
  is_label?: boolean   // true=标签列（承载行名 label），投影为第一列
  align?: 'left' | 'center' | 'right'
  format?: 'amount' | 'percent' | 'text'  // 渲染格式提示（可选）
}
```

### 载荷扩展（additive，向后兼容）

```jsonc
{
  "wp_id": "...", "sheet_name": "...", "section_id": "...", "current_standard": "...",
  "sub_table_data": { "存货分类": [ { "label": "原材料", "end_gross": 100, ... } ] },
  "_columns": {                              // ← 新增，可选
    "存货分类": [
      { "key": "label", "label": "存货类别", "is_label": true },
      { "key": "end_gross", "label": "期末账面余额", "format": "amount" },
      { "key": "end_impairment", "label": "期末跌价准备", "format": "amount" }
    ]
  }
}
```

### 持久化（disclosure_notes.table_data）

```jsonc
{
  "sub_table_data": { "存货分类": [ ... ] },
  "_sub_table_columns": { "存货分类": [ ColumnDef, ... ] },   // ← 新增，与 sub_table_data 同款浅合并
  "_source": "workpaper",
  "_current_standard": "listed_standalone",
  "_last_sync_wp_id": "...", "_last_sync_sheet": "...", "_last_sync_at": "..."
}
```

### Projected_Tables（投影输出，注入 table_data._tables 供渲染，非持久）

```jsonc
{
  "name": "存货分类",
  "headers": ["存货类别", "期末账面余额", "期末跌价准备"],
  "columns": [ { "key": "label", "label": "存货类别", "is_label": true }, ... ],
  "rows": [
    { "label": "原材料", "values": [100, 5], "is_total": false },
    { "label": "合计", "values": [300, 15], "is_total": true }
  ],
  "_source_sub_table_key": "存货分类"
}
```

## Projector 逻辑（`project_sub_tables`，纯函数）

```
输入: table_data(dict)
1. 若 _source 不在 (workpaper, workpaper_html) → 返回 None（调用方沿用既有 _tables/rows，D5/Req6.2）
2. sub = table_data.sub_table_data；cols_map = table_data._sub_table_columns
3. 若 sub 为空 → 返回 []（无 workpaper 表可投影）
4. 对 sub 的每个 (key, rows)（按插入序，跳过 '_' 前缀 meta 键）:
   a. defs = cols_map.get(key)
   b. 若 defs 缺失 → 降级(Req7.2)：产出仅 label 列的表或标记 needs_columns，绝不用英文键当 header
   c. label_def = 首个 is_label 的 def（无则首个 def）
   d. value_defs = defs 去掉 label_def，按声明序
   e. headers = [label_def.label] + [d.label for d in value_defs]
   f. 对每行: label=row[label_def.key]；values=[row.get(d.key) for d in value_defs]；is_total=row.get('is_total', False)
   g. 输出 Projected_Table
5. 返回 tables 列表
```

- **纯函数**：无 IO、无 db、同输入同输出（Req6.4、P1）。
- 后端 `get_note_detail`：`projected = project_sub_tables(note.table_data)`；若非 None 则在返回的 `table_data` 副本注入 `_tables = projected`（不写库）。
- `note_word_exporter`：导出 workpaper 来源记录时同样调用，得到 `_tables` 后走既有多表渲染。

## Correctness Properties

### Property 1: 投影纯函数
*For any* table_data，`project_sub_tables` 同输入多次调用输出相等且不修改入参（无 IO / 无 db）。
**Validates: Requirements 6.4**

### Property 2: 列序保持
*For any* `_columns[key]` 声明序，投影 headers 顺序与之一致，`is_label` 列置于首列。
**Validates: Requirements 2.2**

### Property 3: 缺字段输出空单元
*For any* 行对象缺某 ColumnDef.key，该单元格投影为空值，不丢列、不报错。
**Validates: Requirements 2.3**

### Property 4: 额外字段忽略
*For any* 行对象含 `_columns` 未声明的字段键，投影不新增列。
**Validates: Requirements 2.4**

### Property 5: 合计行保持
*For any* 含 `is_total: true` 的行，投影后的 row `is_total` 为 true。
**Validates: Requirements 1.4**

### Property 6: 多表与键序
*For any* 多子表 sub_table_data，投影按其键插入序逐张产出独立表。
**Validates: Requirements 1.3**

### Property 7: 来源优先级
*For any* table_data，`_source in (workpaper, workpaper_html)` 且 sub 非空 → 投影非 None；无 workpaper 标识 → 返回 None（不投影，沿用 Engine_Fill_Path）。
**Validates: Requirements 6.1, 6.2**

### Property 8: 降级不杜撰列头
*For any* 缺失 `_columns` 的子表，投影输出的 headers 不含任何等于英文字段键的字符串。
**Validates: Requirements 3.3, 7.2**

### Property 9: 空载荷 no-op
*For any* 已有 sub_table_data 与 `_sub_table_columns` 的记录，传入空 `sub_table_data={}` 同步后二者均完整保留。
**Validates: Requirements 7.5, 8.1**

### Property 10: 部分合并保留未推送
*For any* 已有 `{t1, t2}` 的记录，推送 `{t1}` 后 t2 及其列头保留、t1 被新值覆盖。
**Validates: Requirements 8.2**

### Property 11: 变体隔离
*For any* listed/soe 变体，二者写不同 note_section，投影不跨变体合并。
**Validates: Requirements 4.1, 4.3**

### Property 12: 导出等于渲染
*For any* workpaper 来源记录，Word 导出的表结构（表名/列头/行）与模块投影结果一致（共用同一 Projector）。
**Validates: Requirements 1.2**

### Property 13: 列头合并语义
*For any* `_sub_table_columns`，其与 sub_table_data 同款按子表 key 浅合并 + 空载荷 no-op。
**Validates: Requirements 2.1, 2.5**

## Testing Strategy

- **后端**：`test_note_sub_table_projector.py`（P1~P8 纯函数 PBT，hypothesis max_examples≤10）；扩 `test_disclosure_sync.py`（P9/P10/P13 + `_columns` 合并）；`test_note_word_export_sub_table.py`（P12，投影→导出一致）。
- **前端**：`disclosureColumnDefs.spec.ts`（客户端兜底投影与后端规则一致）；抽 2~3 组件（F2/G14/K11）payload 含 `_columns` 且 label 取自组件既有列头。
- **CI 守卫**：`check_disclosure_columns_coverage.py --strict` 全绿（无漏接组件）。
- **Playwright**：改版底稿 → 推送上市版/国企版 → 附注模块可见完整表格（中文列头/合计行）→ Word 导出含表；二次空载荷同步不丢表；刷新不命中旧缓存。

## Error Handling

- 投影缺 `_columns` → 降级（Req7.2），记 `warning` 不抛。
- `sub_table_data` 结构异常（非 dict / 行非 dict）→ 跳过该子表，记 warning，不影响其余。
- Word 导出投影失败 → 回退既有 `_tables`/`rows` 路径，不阻断导出。
- 载荷 `_columns` 与 `sub_table_data` 键不匹配 → 只投影两者都有的键；`sub_table_data` 有而 `_columns` 无 → 走降级；`_columns` 有而 `sub_table_data` 无 → 忽略该列头。

## Rollout & Backward Compatibility

- 载荷 `_columns` 为 additive 可选字段，旧组件不传 → 降级不报错（Req2.5/7.2）。
- 未接入组件的历史 `disclosure_notes` 无 `_sub_table_columns` → 降级呈现，不清空。
- Engine_Fill_Path 记录（无 workpaper 来源）→ 投影返回 None，渲染/导出完全不变（Req7.1）。
- 分波推进 `_columns` 覆盖（tasks Wave3~5），每波不破坏未接入组件。
