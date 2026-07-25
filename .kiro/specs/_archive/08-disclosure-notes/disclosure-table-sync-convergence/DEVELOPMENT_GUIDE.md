# 开发指南：披露表列头随 `_columns` 携带 + 后端单点投影

> 本文档记录 disclosure-table-sync-convergence 规格确立的数据同步范式，供后续维护者参考。

## 核心范式

披露表组件 → 附注模块的单向同步链上，**列头元数据随载荷携带、后端单点投影器在读时转换为渲染格式**。

```
┌─────────────────────────────┐   sync payload {sub_table_data, _columns}
│ Disclosure_Tab_Component /   │─────────────────────────────────────────────┐
│ GtCNoteTable                 │                                             ▼
│ (列头唯一真源=源模板对齐)     │              POST sync-from-workpaper
└─────────────────────────────┘              → 合并 sub_table_data + _sub_table_columns
                                             → disclosure_notes.table_data (持久化)
                                                          │
                                                          │ 读时投影（纯函数，不持久化）
                                        ┌─────────────────┴─────────────────┐
                                        ▼                                   ▼
                     get_note_detail                          note_word_exporter
                     → project_sub_tables()                   → project_sub_tables()
                     → 注入 _tables（非持久）                  → 复用同一 _tables
                                        │                                   │
                                        ▼                                   ▼
                     currentNoteTables 消费 _tables         Word 文档表格
                     + 客户端兜底 projectSubTablesClient
```

## 关键组件

| 组件 | 路径 | 职责 |
|------|------|------|
| 投影器 | `backend/app/services/note_sub_table_projector.py` | 纯函数 `project_sub_tables(table_data)` — 读时把 sub_table_data + _sub_table_columns 转成 `_tables[]` |
| 同步服务 | `backend/app/services/wp_disclosure_sync_service.py` | `sync_from_workpaper` 存储并浅合并 `_sub_table_columns`（与 sub_table_data 同款语义） |
| 详情注入 | `backend/app/routers/disclosure_notes.py` | `get_note_detail` 读时注入投影 `_tables`（不写库） |
| Word 导出 | `backend/app/services/note_word_exporter.py` | 导出前对 workpaper 来源记录调同一投影器 |
| 前端列头定义 | `frontend/src/components/workpaper/composables/disclosureColumnDefs.ts` | `ColumnDef` 类型 + `defineColumns()` + `projectSubTablesClient()`（客户端兜底） |
| CI 守卫 | `backend/scripts/check/check_disclosure_columns_coverage.py` | `--strict` 阻断未携带 _columns 的新增 sync 调用点 |

## 接入新组件的步骤

当新建或改造 `*TabDisclosureListed/Soe.vue` 同步披露表到附注时：

1. **定义列头**：从组件既有 `<el-table-column label>` 或 C 类 schema 的 `columns[].label` 逐字提取中文列头，构造 `ColumnDef[]`（key=行对象字段键，label=中文列头，is_label 标记标签列）。
2. **载荷附 `_columns`**：在构造 sync payload 时附加 `columns: { 子表key: ColumnDef[] }`。
3. **CI 守卫通过**：运行 `python backend/scripts/check/check_disclosure_columns_coverage.py --strict`，确认新调用点被覆盖。

## 设计铁律

- **列头 label 必须取自组件既有源对齐定义**（致同 2025 源模板），禁止英文字段键当列头或凭常识杜撰。
- **投影为纯函数、读时执行、不持久化 `_tables`**：避免与 Engine_Fill_Path 的持久 _tables 混淆。
- **优先级由 `_source` 单点决策**：`_source ∈ (workpaper, workpaper_html)` 且 sub 非空 → 投影为权威 _tables；否则不投影、沿用 Engine_Fill_Path。
- **降级不杜撰列头**：无 `_columns` 时不以英文字段键当 header，仅以 label 列可读呈现或标"待配置列头"。
- **空载荷 no-op**：传入空 `sub_table_data={}` 不清空既有子表。
- **浅合并语义**：`_sub_table_columns` 按子表 key 浅合并，未推送的子表列头保留。

## 存量数据说明

代码修复后历史记录需**重新点「同步到附注」**才带上 `_sub_table_columns` 完整渲染；在此之前经降级路径仅显示标签列（不空白不报错）。
