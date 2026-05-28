# 附注模块动态表格 + 模板继承支持 — 设计文档

> 版本：v0.2（草稿，2026-05-28 大幅扩展）
> 关联需求：requirements.md（53 验收 / 6 大类 A-F）

## 一、设计核心决策

### D1 「动态」统一概念（替代 v0.1 浮动）

`row_type` 枚举扩展：

- 现有：`data | subtotal | total | header_label`
- 新增：`dynamic_anchor`（占位起点）/ `dynamic_data`（动态数据行）/ `dynamic_marker_end`（区域终点元数据）

`column.col_type` 新增：

- `fixed`（默认，模板定义）
- `dynamic`（用户/binding 添加）

**判定规则**：

```python
row.is_dynamic = row.row_type.startswith('dynamic_')
column.is_dynamic = column.col_type == 'dynamic'
```

### D2 双 sidecar 架构

```json
{
  "table_data": {
    "headers": ["项目", "期末", "期初"],   // 兼容旧路径
    "rows": [...],

    "_columns_meta": [                       // 新增：列元数据（D2.1）
      {"id": "col_label", "label": "项目", "col_type": "fixed", "value_type": "text"},
      {"id": "col_amount_end", "label": "期末", "col_type": "fixed", "value_type": "amount"},
      {"id": "col_amount_start", "label": "期初", "col_type": "fixed", "value_type": "amount"},
      {"id": "col_user_currency", "label": "币种", "col_type": "dynamic", "added_by": "user_xxx", "added_at": "2026-..."}
    ],

    "_dynamic_regions": [                    // 新增：行动态区（D2.2）
      {
        "name": "客户明细",
        "axis": "row",                       // row | column
        "start_idx": 1,
        "end_idx": 5,
        "expandable": true,
        "dynamic_source": "aux_balance | wp_data | manual",
        "source_config": {...}               // 见 D3
      },
      {
        "name": "扩展列",
        "axis": "column",
        "start_col_idx": 3,
        "end_col_idx": 999,                  // 开放式
        "expandable": true,
        "dynamic_source": "manual"
      }
    ]
  }
}
```

**好处**：

- D1 sidecar 兼容铁律（不破坏现有 rows/headers）
- 列由 `_columns_meta` 统一管理，避免按 idx 引用列易碎
- 行/列动态区共用同一 `_dynamic_regions` 数组（用 `axis` 字段区分）

### D3 source_config 模式

```json
// aux_balance
{
  "source": "aux_balance",
  "account_codes": ["1122"],
  "aux_type": "客户",
  "limit": 5,
  "order_by": "amount_desc"
}

// wp_data（新核心）
{
  "source": "wp_data",
  "wp_code": "h08",
  "sheet": "分类构成",
  "extract": "table",            // table | cell | sum_column
  "row_filter": {"is_total": false, "exclude_label_pattern": "合计|小计"},
  "label_col": "A",              // 哪一列作为附注的 label
  "value_cols": {                // 哪些列映射到附注的列
    "col_amount_end": "F",
    "col_amount_start": "G"
  }
}

// manual
{
  "source": "manual",
  "default_label": "请输入"
}
```

### D4 wp_data 数据源接入

```python
# disclosure_engine.py 新增
async def _extract_wp_data(self, project_id: UUID, year: int, source_config: dict) -> list[dict]:
    """从底稿 parsed_data 提取数据."""
    wp = await self._get_workpaper(project_id, year, source_config['wp_code'])
    if not wp or not wp.parsed_data:
        return []  # 底稿不存在 → 0 行 → 表格 is_empty=true → auto_trim v2 跳过

    sheet_data = wp.parsed_data.get(source_config['sheet'], {})
    if source_config['extract'] == 'table':
        rows = sheet_data.get('rows', [])
        # 应用 row_filter
        rows = [r for r in rows if not r.get('is_total')]
        if 'exclude_label_pattern' in source_config['row_filter']:
            import re
            pattern = re.compile(source_config['row_filter']['exclude_label_pattern'])
            rows = [r for r in rows if not pattern.match(r.get(source_config['label_col'], ''))]
        # 映射列
        result = []
        for r in rows:
            d = {'label': r.get(source_config['label_col'], '')}
            for col_id, wp_col in source_config['value_cols'].items():
                d[col_id] = r.get(wp_col, 0)
            d['row_type'] = 'dynamic_data'
            result.append(d)
        return result
    elif source_config['extract'] == 'cell':
        return [{'value': sheet_data.get('cells', {}).get(source_config['cell'])}]
    elif source_config['extract'] == 'sum_column':
        cells = sheet_data.get('cells', {})
        col = source_config['column']
        total = sum(cells.get(f"{col}{i}", 0) for i in range(2, 1000))
        return [{'value': total}]
```

### D5 auto_trim v2（三级裁剪）

```python
# note_trim_service.py 扩展
async def auto_trim_v2(self, project_id: UUID, year: int) -> dict:
    """三级裁剪.

    Returns:
        {
            "section_pruned": [...],  # 章节级（已有，按 TB 科目）
            "table_pruned": [...],    # 表格级（新）
            "paragraph_pruned": [...]  # 段落级（新）
        }
    """
    notes = await self._load_notes(project_id, year)
    result = {"section_pruned": [], "table_pruned": [], "paragraph_pruned": []}

    for note in notes:
        # 1. 段落级：text_content 空 + tables 全空
        if not note.text_content and self._all_tables_empty(note):
            note.is_deleted = True
            note.deletion_reason = "auto_trim_v2_empty"
            result["paragraph_pruned"].append(note.note_section)
            continue

        # 2. 表格级：单个表 rows 全空 → 替换为「本期无此项业务」标记
        for tbl in note.table_data.get('_tables', [note.table_data]):
            if self._all_rows_empty(tbl):
                tbl['_render_as'] = 'no_business_paragraph'
                result["table_pruned"].append({"section": note.note_section, "table": tbl.get('name')})

    return result


def _all_rows_empty(table: dict) -> bool:
    """判断表 rows 是否全空（label 列保留，数值列全 0/null/-）."""
    rows = table.get('rows', [])
    if not rows:
        return True
    value_cols = [c['id'] for c in table.get('_columns_meta', []) if c.get('value_type') == 'amount']
    for row in rows:
        if row.get('row_type') in ('total', 'subtotal'):
            continue
        for col_id in value_cols:
            val = row.get(col_id)
            if val and val not in (0, '0', '-', '', None):
                return False
    return True
```

### D6 集团模板继承架构

#### 6.1 数据模型新建

```python
# group_note_template_baseline 表
class GroupNoteTemplateBaseline(Base):
    __tablename__ = "group_note_template_baseline"
    id: UUID = primary_key
    name: str  # "中国XX集团-2025附注基线"
    parent_project_id: UUID  # 来自哪个项目
    version: str  # "v1.2"
    template_type: str  # soe | listed
    sections_data: JSONB  # 完整裁剪后的 section 数据（含文字+表样）
    created_by: UUID
    created_at: datetime
    is_active: bool = true  # 旧版本 false 不删，保留审计轨迹
```

#### 6.2 lineage 字段

```python
# DisclosureNote 新增
class DisclosureNote(Base):
    ...
    template_lineage: JSONB | None
    # 例：[
    #   {"baseline_id": "...", "version": "v1.0", "applied_at": "2026-..."},
    #   {"baseline_id": "...", "version": "v1.1", "applied_at": "2026-..."}
    # ]
    is_local_override: bool = false  # 用户改过 → true
```

#### 6.3 Service 流程

```python
async def apply_group_baseline(child_project_id: UUID, baseline_id: UUID, year: int):
    """child 应用集团基线.

    步骤：
      1. 加载 baseline.sections_data
      2. 对 child 已有 notes：
         - 若章节存在且 is_local_override=true → 跳过（保留 child 修改）
         - 否则覆盖：复制文字 + 表样 + 写 lineage
      3. baseline 没有的章节但 child 有 → 保留（local extension）
      4. 数据 = child 自己的 TB / wp_data 重新展开（不复制 parent 数据）
    """
```

### D7 前端动态行/列交互（NoteTableEditor.vue）

```
渲染顺序：
  1. 读 _columns_meta → 渲染 thead，动态列加 + 标记
  2. 读 rows → 渲染 tbody
  3. 检查 _dynamic_regions：
     - axis=row 区：行背景浅黄 + 行号 ★
     - axis=column 区：列背景浅紫 + 列名 +
  4. 浅黄区底部加「+ 添加明细行」
  5. 浅紫区右侧加「+ 添加列」（仅 admin/manager 权限）

交互：
  - 单击单元格 → 公式栏显示 binding（含 wp_data 选项）
  - 双击 → 编辑值
  - 右键动态行/列 → 删除菜单
  - 右键固定行/列 → 删除菜单 disabled
```

### D8 集团基线 UI（NoteEditor 工具栏新增）

```
工具栏新增 3 个按钮：
  📦 应用集团基线 → 弹对话框选 baseline → 预览 diff → 确认
  💾 保存为集团基线 → partner 权限 → 输入基线名 + 版本号
  🔄 同步基线 → 显示「3 章节有更新」 → 选择性 apply
```

## 二、API 变化

### 新增端点

```
# 动态行/列
POST   /api/disclosure-notes/{note_id}/dynamic-rows + body: {region_name, after_idx?}
DELETE /api/disclosure-notes/{note_id}/dynamic-rows/{row_idx}
PUT    /api/disclosure-notes/{note_id}/dynamic-rows/sort
POST   /api/disclosure-notes/{note_id}/dynamic-columns + body: {region_name, label, value_type}
DELETE /api/disclosure-notes/{note_id}/dynamic-columns/{column_id}

# auto_trim v2
POST   /api/disclosure-notes/{project_id}/{year}/auto-trim-v2

# 集团基线
GET    /api/group-note-baselines  (按 template_type 列表)
POST   /api/group-note-baselines  (从某 parent_project 保存)
GET    /api/group-note-baselines/{id}/versions
GET    /api/group-note-baselines/{id}/preview-diff?child_project_id=...
POST   /api/projects/{project_id}/apply-group-baseline + body: {baseline_id, year}
GET    /api/projects/{project_id}/baseline-sync-status
```

### 现有端点扩展

- `GET /api/disclosure-notes/{project_id}/{year}` → 多返 `_columns_meta` / `_dynamic_regions` / `template_lineage`
- `PUT /api/disclosure-notes/{note_id}` → 接受动态行/列修改

## 三、数据迁移

### M1 模板 binding 扩展（P-1 + P-2 输入）

```csv
# note_dynamic_regions_annotation.csv (P-1)
section, region_name, axis, start_label, end_label, source, source_config_json

# note_wp_data_bindings.csv (P-2)
section, row_idx, col_id, wp_code, sheet, extract, label_col, value_cols_json
```

### M2 模板 JSON 写入

`generate_note_template_bindings.py` 扩展支持新格式。

### M3 GroupNoteTemplateBaseline 表创建

`V019__group_note_template_baseline.sql`

## 四、CI 卡点（共 8 项）

- CI-1：`_dynamic_regions` 引用的 idx/column_id 都有效
- CI-2：`row_type=dynamic_*` 必须落在 region 范围
- CI-3：动态列 `column_id` 全局唯一（per table）
- CI-4：REGION() 公式能解析
- CI-5：动态行/列删除后合计自动重算（PBT）
- CI-6：round-trip 数据无丢失（PBT）
- CI-7：apply_group_baseline 后 child lineage 字段必有 baseline_id
- CI-8：auto_trim v2 三级裁剪互斥（同章节不会被多个级别 prune）

## 五、性能预算

- 单章节动态展开 < 100ms
- wp_data 提取 < 200ms（从 wp.parsed_data JSONB GIN 索引）
- 全量 173 章节生成 < 12s
- apply_group_baseline 60 章节 < 3s
- auto_trim v2 全章节 < 2s

## 六、回退策略

| 失败阶段 | 回退手段 |
|---------|---------|
| 动态行展开错误 | 模板删 _dynamic_regions → 退回固定 |
| 动态列错误 | 删 _columns_meta → 用 headers 数组 |
| wp_data 取不到 | 回退到 manual binding（占位空 cell） |
| 集团基线 apply 失败 | DB 事务回滚 + lineage 不写入 |
| auto_trim v2 误剔 | feature flag 关闭，回退 v1 章节级 |

## 七、ADR

- ADR-007 公式 DSL — 加 REGION() / WP() 函数
- ADR-010 自定义模板版本化 — 扩展到动态行/列
- **新增 ADR-011：附注表格双 sidecar (_columns_meta + _dynamic_regions) 设计选择**
- **新增 ADR-012：集团模板继承 lineage 模型选择**

## 八、变更影响范围

| 模块 | 改动 | 工作量 |
|------|------|--------|
| 模板 JSON | 60+ 动态区 + 30+ wp_data binding | 1.5 人天（需 P-1/P-2） |
| `note_template_bindings.json` | 双扩展 | 0.5 人天 |
| `disclosure_engine.py` | _expand_dynamic_regions + _extract_wp_data | 1.5 人天 |
| `note_cell_merge.py` | 行+列三态合并扩展 | 0.5 人天 |
| `note_formula_generator.py` | REGION + WP 函数完善 | 0.5 人天 |
| `note_trim_service.py` | auto_trim v2 三级 | 0.5 人天 |
| **新建** `group_note_baseline_service.py` | 集团基线核心 | 1 人天 |
| `note_word_exporter.py` | DynamicRow/Col 样式 + 空表替换 | 0.5 人天 |
| 新增 router `note_dynamic.py` + `group_note_baseline.py` | 11 端点 | 1 人天 |
| 前端 `NoteTableEditor.vue` 扩展 | 动态行/列 + 集团基线 UI | 2 人天 |
| 前端新建 composable / 对话框 | useNoteDynamic / useGroupBaseline | 1 人天 |
| DB migration `V019` | group_note_template_baseline 表 | 0.2 人天 |
| 测试 | 单测 + PBT + UAT | 1.5 人天 |
| **合计** | | **12.2 人天** + P-1/P-2/P-3 共 2.5 人天 |
