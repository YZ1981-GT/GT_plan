# 设计：公式推送批 E — 附注推送铺开

> 核心约束：**按准则变体隔离**——上市底稿披露表数据只推上市版附注章节，国企底稿只推国企版。

## 一、准则变体隔离的实现链路

```
底稿渲染 → 披露表数据（分 listed / soe 两侧）
    ↓ binding.note_rows(entries, template_type, rule)
    ↓ 按 template_type 选行标签 + 取值
引擎 _push_note
    ↓ section = rule.target.sections.get(template_type)
    ↓ 上市项目 → sections["listed"] = "五、4"
    ↓ 国企项目 → sections["soe"]    = "八、4"
    ↓ 按 section 查 DisclosureNote → 写入
```

关键点：
1. **`template_type` 来自项目**（`DisclosureEngine._get_active_template_type(project_id)`，E1 binding 已用）
2. **`section_by_template` 来自规则**（章节号从前端 `*NoteSectionMap.ts` 逐字取，不猜）
3. **`note_rows` 按 template_type 返回该变体的行**（上市行标签 ≠ 国企行标签时，binding 须分别构建）

## 二、数据源链路

### 2.1 章节号真源

```
前端 *NoteSectionMap.ts（唯一真源）
    ↓ gen_note_wp_sync_registry.py --write
    ↓ backend/data/note_workpaper_sync_registry.json
规则 JSON
    ↓ target.section_by_template = {"listed": "五、4", "soe": "八、4"}
```

### 2.2 行标签真源

```
附注模板 JSON
    ↓ note_template_listed.json / note_template_soe.json
    ↓ sections[N].tables[T].rows[R].label
底稿渲染 → 前端 buildXSyncPayload
    ↓ 按渲染数据构建 noteLabel（附注字面）/ label（底稿字面）
binding.note_rows(entries, template_type, rule)
    ↓ 返回 [{note_label, label, ending, opening, is_total, is_memo, ending_resolved, opening_resolved}]
```

### 2.3 表名真源

```
附注模板 JSON
    ↓ sections[N].tables[T].name（如 "货币资金"、"应收票据"）
规则 JSON
    ↓ target.table = "应收票据"
```

## 三、binding 的 `note_rows` 方法

### 3.1 E1 先例

E1 的 `note_rows` 在 `e1_calc.disclosure_main_rows` 里：按 `template_type` 选行定义（listed 多两行），从 `entries`（底稿条目快照）读审定合计值。

### 3.2 通用化

批 C 的 `BalanceAdjudicationBinding` 须实现 `note_rows`：
- 从 `AdjudicationSpec.note_sections` 取该科目在附注中的表名和行标签
- 从 `entries` 读审定合计值填入 `ending`/`opening`
- 按 `template_type` 选变体（上市/国企行标签可能不同）

### 3.3 变体差异处理

```python
def note_rows(self, entries, template_type, rule):
    table_def = self._note_table_def(template_type, rule.target.table)
    if table_def is None:
        return []  # 该变体无此表（如 H5 上市无独立章节）
    rows = []
    for row_def in table_def["rows"]:
        # 从附注模板行定义取标签
        note_label = row_def["label"]
        # 从 entries 读审定合计值（按科目映射）
        ending = self._resolve_amount(entries, row_def, "ending")
        opening = self._resolve_amount(entries, row_def, "opening")
        rows.append({
            "note_label": note_label,
            "label": note_label,  # 底稿字面 = 附注字面（审定表科目）
            "ending": ending, "opening": opening,
            "ending_resolved": ending is not None,
            "opening_resolved": opening is not None,
            "is_total": row_def.get("is_total", False),
            "is_memo": False,
        })
    return rows
```

## 四、附注规则结构

```json
{
  "rule_id": "{code}.note.main_rows",
  "page_key": "workpaper:{code}",
  "stage": "note",
  "policy": "editable",
  "target": {
    "domain": "note",
    "section_by_template": {"listed": "五、N", "soe": "八、N"},
    "table": "应收票据",
    "fields": ["end_amount", "prior_amount"]
  },
  "source": {
    "kind": "derivation",
    "name": "{code}_disclosure_main_rows",
    "params": {},
    "formula_text": "按准则变体取审定表审定数推送到附注主表"
  },
  "triggers": ["WORKPAPER_SAVED", "manual"],
  "description": "附注 {表名}（上市 五、N / 国企 八、N）期末/期初数"
}
```

## 五、逐科目现读清单

每个科目实施前必须现读确认：
1. `*NoteSectionMap.ts` 中的章节号（`listed` / `soe`）
2. `note_workpaper_sync_registry.json` 中的条目（一致性）
3. `note_template_listed.json` / `note_template_soe.json` 中的表定义（行标签 + 列定义）
4. 前端 `buildXSyncPayload` 的行构建逻辑（哪些行是数据行、合计行、备注行）
5. 上市/国企行标签差异（逐行比对模板 JSON）

## 六、风险

| 风险 | 缓解 |
|------|------|
| 章节号从 `*NoteSectionMap.ts` 取，前端改章节号后后端不跟 | `note_workpaper_sync_registry.json` 的 `--check` 守卫 + 规则校验 `section_by_template` 键 ∈ {listed, soe} |
| 上市/国企行标签不同但规则只写一份 | `note_rows` 按 `template_type` 从附注模板取行标签，不硬编码 |
| 部分科目附注结构复杂（G6 有 14 张子表） | 先做简单科目（D1 主表 + 受限表），复杂科目逐步覆盖 |
| 推送与前端同步竞争 | 附注 `_cell_modes` manual/locked 保留机制（Task 7 已实现） |
