# Task 4.0 结论 — V2 合并章节 table_data 与附注渲染契约兼容性核实

> 本文件是 **Task 4.1（`_persist_consol_sections_v2`）落库策略的权威输入**。
> 核实方式：静态读码（未跑 live，V2 生成路径当前不落库无法直接观测渲染）。
> 判定裁决：**(C) 回退仅落 provenance**（design.md §Components 3 三选一）。

---

## 一、裁决

**(C) 回退仅落 provenance** — 不落 table_data 渲染表格。

`_persist_consol_sections_v2` 落 `disclosure_notes` 时**只写穿透 provenance 三字段**
（`consolidation_breakdown` + `source_project_id` + `last_sync_source='consolidation'`），
**表格渲染保留在 `consol_note_data` 老路径**（Req3.3 零回归）。附注级穿透（Req3.2
`has_breakdown=true`）由此直接激活，**完全不依赖 table_data 渲染**。

排除 (A)：落库 as-is 前端必空表 / 列头全空白。
排除 (B)：结构适配需改造共享的 `aggregate_section` 携带子公司列定义 + 对齐异构 col_id +
为合并章节补列头，成本高，且有"臆造披露列头"的合规红线风险 → 超出 Wave 3 范围。

---

## 二、证据 A：V2 `aggregate_section` 产出的 `table_data` 实际结构

来源：`consol_note_aggregation_service.aggregate_section`（被 `consol_disclosure_service._aggregate_common_section` 调用，返回值挂在 `section_out["table_data"]`）。

```python
# aggregate_section 返回（method=simple_sum 默认）：
{
    "rows": [
        {
            "label": str,                     # 行名
            "values": {col_id: numeric} 或 [positional],  # ← 关键：dict 键为不透明 col_id（如 col_amount_end）
                                              #   或位置数组（取决于子公司单体附注行的 cells/values 形态）
            "row_type": str,                  # "data" / "total"
            "is_total": bool,
            "source_project": UUID,           # 贡献子公司（provenance 用）
            "sources"?: [...],                # 模糊合并后才有
        },
        ...
    ],
    "elimination_applied": bool,
    "elimination_amount"?: str,               # sum_after_elimination / top_n
    "provenance": [{project_id, company_name, row_count}],
    "texts"?: [{project_id, company_name, text}],   # first_n_concat 才有
    "total_rows_before_top_n"?: int,          # top_n 才有
    "method": str,
    "child_count": int,
    "section_id": str,
    # 经 _add_elimination_columns 可能追加 _pre_elimination / _post_elimination 标记
}
# 空章节占位：{rows:[], method, child_count, section_id, elimination_applied}
```

**关键缺失（对照渲染契约）**：
- ❌ 无 `_tables`
- ❌ 无 `_source`（非 `workpaper`/`workpaper_html`）+ 无 `sub_table_data` + 无 `_sub_table_columns`
- ❌ 无顶层 `headers`
- ❌ `rows[].values` 是 **dict（不透明 col_id 键）** 或位置数组，且**无 `_cell_meta.semantic`**
- ❌ `aggregate_section` **完全丢弃了子公司的列头/列定义**（只保 rows/method/provenance）

`section_out` 顶层（与 table_data 平级，Task 4.1 落库要读的 provenance）：
```python
{
    "section_id": consol_section_id,          # 经 _renumber_sections_consolidated 重排
    "table_data": <上述 aggregate 结果>,
    "source_project_id": str(parent_project_id),      # ← 落库用
    "consolidation_breakdown": {"by_company": [...], "computed_at": iso},  # ← 落库用（穿透 provenance）
    "workpaper_owned": bool,                  # P2-8：True 则落库须跳过（G7 soe 七、N 拥有）
    "section_type": "common", "scope": "consolidated", "level": 3, ...
}
```

---

## 三、证据 B：前端附注模块渲染契约的期望 shape

来源：`DisclosureEditor.vue::currentNoteTables` + `getCellValue` + `note_word_exporter._note_tables` + `get_note_detail`（读时投影）。

渲染走三条路径，任选其一命中即可渲染：

1. **`table_data._tables[]`（首选）** — 每表 `{name, headers:[str], rows:[{label, values:[位置数组], is_total}], columns?}`。
2. **`sub_table_data` + `_sub_table_columns` + `_source ∈ (workpaper, workpaper_html)`** → `note_sub_table_projector.project_sub_tables` 读时投影为 `_tables`。**非 workpaper 来源 → 返回 `None` 不投影。**
3. **legacy 顶层 `table_data.rows` + `headers:[str]`** — `getCellValue(row, colIdx)` 读 `row.values[colIdx-1]`（**values 必须是位置数组**）；`headers` 为空时靠 `note_header_projector`：
   - 优先**模板表头**（`template_headers_for(section_number, source_template)`，仅 `source_template ∈ {listed, soe}` 且列数匹配才套用）
   - 兜底**行 `_cell_meta[colIdx].semantic`** 语义派生

---

## 四、V2 输出落库 as-is 的渲染结果推演（为何排除 A）

| 渲染路径 | 命中？ | 原因 |
|---|---|---|
| `_tables[]` | ❌ | V2 无 `_tables` |
| `project_sub_tables`（path 2） | ❌ | 无 `_source=workpaper` + 无 `sub_table_data` → 返回 `None` |
| 前端客户端投影 `projectSubTablesClient` | ❌ | 同上，无 sub_table_data |
| legacy `td.rows`（path 3） | ⚠️ 命中但坏 | 见下 |

**path 3 命中后**：
- `getCellValue(row, colIdx)` 读 `row.values[colIdx-1]`：
  - 若 `values` 是 **dict** → `dict[数字下标]` = `undefined` → **全空单元格**
  - 若 `values` 是位置数组 → 数据能取，但**无 headers**
- `headers` 空 → `note_header_projector`：
  - `source_template` 为 `consolidated` → 模板路径只认 `listed`/`soe` → **无模板表头**
  - 无 `_cell_meta.semantic` → 语义派生：values 是 dict → `num_value_cols=0` → `headers=["项目"]`（单列无数据列）；values 是数组 → `headers=["项目","","",…]`（**数据列表头全空白**）

**净结果**：空表 / 表格坍缩 / 数据列无标题 —— **无论哪种都不符合"直接落库可渲染"** → **排除 (A)**。

---

## 五、为何排除 B（需结构适配）

结构适配需要：① `rows[].values` dict → 位置数组（按确定列序）；② 补 `headers`（col_id → 中文列头）。

**障碍**：
1. `aggregate_section` **丢弃了全部列头/列定义**（子公司单体附注的 `sub_table_data`/`_sub_table_columns`/`headers` 在 `_extract_rows_from_table_data` 只读 `rows[].cells/values` 时被丢掉）。要正确补列头须**改造 `aggregate_section` 携带子公司列定义** —— 该函数被多个合并流程共享，改动面大、风险高。
2. col_id 是子公司单体附注的**不透明异构键**（各科目/各底稿不同），跨子公司对齐 + 跨模板列语义统一有真实复杂度。
3. 合并章节 `source_template=consolidated`（无对应模板）+ `section_id` 经 `_renumber_sections_consolidated` 重排 → 与 `listed`/`soe` 模板 `section_number` 不匹配 → **无任何可靠的 canonical 列头来源**。
4. **合规红线**：若用 col_id 英文键 / 猜测值当列头 → 违反平台铁律「禁止英文字段名当列头 / 禁止臆造披露内容」（附注披露列头错 = 披露错）。

→ B 属独立的、对 `aggregate_section` 的较大重构，**不适合 Wave 3 的"落库时加适配层"**。

---

## 六、Task 4.1 落库策略（C 方案，权威指令）

`_persist_consol_sections_v2` 对每个 V2 章节 upsert `disclosure_notes` 时：

1. **写 provenance 三字段（激活穿透，Req3.1/3.2）**：
   - `source_project_id = parent_project_id`（`section["source_project_id"]`）
   - `consolidation_breakdown = section["consolidation_breakdown"]`（`{by_company:[...], computed_at}`，落 `disclosure_notes.consolidation_breakdown` 列）
   - `last_sync_source = 'consolidation'`
2. **不落渲染表格**：`table_data` 不写 V2 的 `aggregate_section` 原始结构（避免前端空表 / 覆盖 `consol_note_data` 老路径渲染）。可写最小占位（如 `{"rows": [], "summary": <method 摘要>}`，不触发表格渲染路径），或保留既有 table_data 不动。**合并章节表格渲染继续走 `consol_note_data` 老路径**（Req3.3 零回归）。
3. `section_title` / `account_name` 经 `_resolve_section_meta(section_id, source_template)`（复用单体元数据解析，禁用 section_id 当标题）。
4. **跳过 `section["workpaper_owned"] == True` 的章节**（P2-8 owner 守卫：合并范围类章节由 G7 soe 披露 sync 的中文「七、N」子节拥有，防双写重复）。
5. 幂等（同 `(project_id, year, note_section)` upsert + 软删复活；唯一键不含 `is_deleted`，须先查软删行复活否则 INSERT 撞键 500）+ 逐章节 fail-open（单章节异常记 `errors` continue，不中断整体）。
6. 灰度门控 `CONSOL_NOTES_V2_ENABLED`（默认 False → 完全不落库，Req3.3）。

**穿透验证（Req3.2）**：`note_consol_drilldown_service` 读 `note.consolidation_breakdown.by_company` → 非空即 `has_breakdown=true`（此路径**不依赖 table_data**，C 方案直接满足）。

---

## 七、边界标注（写入交付物 / 后续 spec 输入）

- **附注模块表格渲染合并章节仍走 `consol_note_data` 老路径**；本次 V2 落库仅激活**附注级穿透（drilldown）**，不改变合并附注的表格呈现。
- 若将来要在 `disclosure_notes` 直接渲染合并附注表格（复用单体的 `_tables` 渲染 / Word 导出），需作为**独立后续任务**：改造 `aggregate_section`（或落库适配层）携带子公司列定义（`sub_table_data` + `_sub_table_columns`）并映射为渲染契约（含合并章节 canonical 列头来源的确定），届时重新评估 (B)。
- 本裁决基于静态读码；`CONSOL_NOTES_V2_ENABLED` 开启后建议 live round-trip 复核穿透 `has_breakdown=true`（create→verify→还原，零污染，见 tasks 8.2*）。
