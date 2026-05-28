# 附注浮动行表格支持 — 设计文档

> 版本：v0.1（草稿）
> 编写：2026-05-28
> 关联需求：requirements.md（A1-E3 共 26 项验收）

## 一、设计核心决策

### D1 三态行类型扩展

现有 `row_type` 枚举：`data | subtotal | total | header_label`

新增：

- `floating_anchor` — 浮动区起点占位（模板里的「①」「……」），生成时被实际数据替换
- `floating_data` — 浮动区数据行（用户/系统添加，每行一条业务记录）
- `floating_marker_end` — 浮动区终点（仅元数据，不渲染）

**判定规则**：

```
row.is_floating = row.row_type in ('floating_anchor', 'floating_data', 'floating_marker_end')
```

### D2 _floating_regions sidecar（不破坏现有 rows）

```json
{
  "table_data": {
    "headers": [...],
    "rows": [...],         // 维持原结构
    "_floating_regions": [ // 新增 sidecar
      {
        "name": "客户明细",
        "start_idx": 1,    // rows 数组索引（从 0）
        "end_idx": 5,      // 含 = floating_marker_end 的位置
        "expandable": true,
        "floating_source": "aux_balance",
        "source_config": {
          "account_codes": ["1122"],
          "aux_type": "客户",
          "limit": 5,
          "order_by": "amount_desc"
        },
        "label_col_idx": 0,   // 哪一列作为浮动行的 label
        "value_col_indices": [1, 2]  // 哪些列是数值（参与合计）
      }
    ]
  }
}
```

**好处**：

- 完全 sidecar，主 rows 不动，符合 D1 sidecar 兼容铁律
- 渲染层「先按 rows 渲染骨架，再在 floating_region 范围内 explode」
- 用户在前端加的浮动行只 push 到 rows（带 row_type=floating_data），不动 _floating_regions

### D3 浮动行展开管线

```
generate_notes
  ↓
_build_table_data(template)
  ↓
_expand_floating_regions(template, project, year):
  for region in template._floating_regions:
    if region.floating_source == 'aux_balance':
      data_rows = await _query_aux_balance(region.source_config)
      # 替换 rows[start_idx:end_idx] 为真实数据行
      table_data.rows = (
        rows[:region.start_idx]
        + [{label: code_name, ...values, row_type: 'floating_data'} for d in data_rows]
        + rows[region.end_idx+1:]
      )
    elif region.floating_source == 'manual':
      # 保留 placeholder anchor，等用户编辑
      pass
  ↓
_build_table_data 末尾的合计行自动重算（SUM 范围按当前 rows 长度动态）
```

### D4 update_note_values 浮动行合并

`note_cell_merge.merge_table_data(template_rendered, user_edited)` 已有 label 对齐 + index 兜底。扩展：

```python
def merge_floating(rendered: TableData, user_edited: TableData) -> TableData:
    """浮动行三态合并."""
    # 1. 固定行：原 label 对齐逻辑
    # 2. 浮动行（row_type='floating_data'）：
    #    - 按 (region_name, label) 元组匹配
    #    - 用户加的行无 region_name 时落到第一个 region
    #    - 删除的行用 _legacy_row 标记保留 30 天
    # 3. 顺序保留 user 的（用户排序生效）
```

### D5 公式 SUM 范围动态扩展

现有公式 `=SUM(R3:R5, C2)` 写死行号。改进：

```
=SUM(REGION('客户明细'), C2)   # 自动展开到浮动区当前行号
=SUM(R3:R[REGION_END('客户明细')], C2)  # 显式
```

实现：`note_formula_generator.expand_region_refs(formula, table_data)` 把 `REGION('xxx')` 替换为 `R{start}:R{end}`。

### D6 前端表样编辑器交互

```
NoteTableEditor.vue:
  - 渲染时检查 _floating_regions
  - 浮动区行加 class="row-floating" → 浅黄底色 (#FFF8E1)
  - 浮动区第一行上方插入 <button>+ 添加明细行</button>
  - 用户点击 → 在浮动区末尾插入 row（row_type='floating_data', label=''）
  - 删除按钮：if row.is_floating then enable, else disable
  - 行号显示：固定行 R1, R2 ... 浮动行 R*1, R*2 (★)
```

### D7 Word 导出 GTNoteFloatingRow 样式

```python
# note_word_exporter.py 新增 helper
def _add_floating_row(doc, row, idx):
    p = doc.add_paragraph(style='GTNoteFloatingRow')
    # 视觉与 GTNoteTableRow 一致，仅 metadata 区分
    # （后期可加浅色背景导出 / 备注 - 但默认与固定行视觉一致避免审计输出花哨）
```

模板 docx 中新增 `GTNoteFloatingRow` 样式定义（继承 GTNoteTableRow + 行号 metadata）。

## 二、API 变化

### 新增端点

```
POST   /api/disclosure-notes/{note_id}/floating-rows  + body: {region_name, after_idx?}
       → 返回新行的 idx + 默认 row 结构

DELETE /api/disclosure-notes/{note_id}/floating-rows/{row_idx}
       → 删除浮动行（带 30 天回收）

PUT    /api/disclosure-notes/{note_id}/floating-rows/sort
       + body: {region_name, order_by: 'amount_desc' | 'label_asc' | 'manual', manual_order?: [idx...]}

GET    /api/disclosure-notes/{note_id}/floating-rows/auto-fill
       + query: region_name
       → 重新从 aux_balance 拉取（不覆盖用户已改的 label）
```

### 现有端点扩展

```
GET    /api/disclosure-notes/{project_id}/{year}/{note_section}
       → 返回多增 _floating_regions 字段（向后兼容：缺则视为空）

PUT    /api/disclosure-notes/{note_id}
       → 接收 rows 中 row_type=floating_data 的修改
```

## 三、数据迁移

### M1：模板 binding 标注（外部依赖）

P-1 审计师标注 60+ 章节哪些行/区域是浮动的：

```json
// note_template_bindings.json 现有：
{ "section": "八、3", "row_idx": 0, "label": "1年以内", ... }

// 扩展：
{
  "section": "八、3",
  "floating_regions": [
    {"name": "前5名客户明细", "start_idx": 7, "end_idx": 12, "floating_source": "aux_balance", ...}
  ]
}
```

### M2：模板 JSON 写入 _floating_regions

`generate_note_template_bindings.py` 脚本扩展：从审计师标注读出 → 写入模板 JSON 的 table_template._floating_regions。

幂等：每次跑 diff 后只更新变化的章节。

## 四、CI 卡点

- CI-1：`_floating_regions` 只能引用 rows 内的有效 idx
- CI-2：`row_type=floating_*` 必须落在某个 region 范围内
- CI-3：浮动行公式 `REGION()` 必须能解析到现有 region name
- CI-4：浮动行删除后，剩余行的合计公式自动重算结果与手算一致（PBT）
- CI-5：用户加的浮动行 round-trip（generate → edit → save → reload）数据无丢失（PBT）

## 五、性能预算

- 单章节浮动展开 < 100ms（已有 aux_balance 索引）
- 全量 173 章节生成 < 11s（基线 8s + 30%）
- 浮动行合并（merge_floating）< 50ms（dict 构造）

## 六、回退策略

任何阶段出问题：

1. 模板 JSON 删除 `_floating_regions` 数组 → 引擎回退到固定行模式
2. 前端 `useNoteFloatingRows` composable feature flag → 关掉浮动 UI
3. Word 导出 `GTNoteFloatingRow` 样式与 `GTNoteTableRow` 视觉一致 → 即使 metadata 错也不影响导出

## 七、ADR 引用

- ADR-007（公式 DSL）— REGION 函数扩展属于 v1.1
- ADR-009（D1 sidecar 兼容铁律）— _floating_regions 是新 sidecar
- 待新增 ADR-011：浮动行 row_type + region 设计选择

## 八、变更影响范围

| 模块 | 改动 | 工作量 |
|------|------|--------|
| `backend/data/note_template_*.json` | 60+ 章节加 `_floating_regions` | 1 人天（依赖 P-1） |
| `backend/data/note_template_bindings.json` | 60+ 章节加浮动 binding | 0.5 人天 |
| `backend/app/services/disclosure_engine.py` | `_expand_floating_regions` 新增 | 1 人天 |
| `backend/app/services/note_cell_merge.py` | 浮动行合并扩展 | 0.5 人天 |
| `backend/app/services/note_formula_generator.py` | REGION 函数 | 0.5 人天 |
| `backend/app/services/note_word_exporter.py` | GTNoteFloatingRow 样式 + 段落 | 0.5 人天 |
| `backend/app/routers/disclosure_notes.py` + 新 router | 4 端点 | 0.5 人天 |
| 前端 `NoteTableEditor.vue` + 新 composable | 浮动区交互 | 1.5 人天 |
| 前端 `useNoteFloatingRows.ts` 新建 | API 调用 + 状态 | 0.5 人天 |
| 测试 | 单测 + PBT + UAT | 1 人天 |
| **合计** | | **7.5 人天** + P-1 审计师 1.5 人天 |
