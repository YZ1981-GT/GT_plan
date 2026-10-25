# 设计：完善合并附注刷新对多级表头的列定位

## §1 现状代码

`consol_note_sections.py` 的 `refresh_note_by_formula` 端点，核心列匹配逻辑（约行 1820-1840）：

```python
for ci, h in enumerate(headers):
    if ci == 0:
        continue
    h_lower = h.replace(" ", "").replace("　", "")
    if "期末" in h_lower or "本期" in h_lower or "账面余额" in h_lower:
        new_row[ci] = str(matched["audited"]) if matched["audited"] else ""
    elif "期初" in h_lower or "年初" in h_lower:
        new_row[ci] = str(matched["opening"]) if matched["opening"] else ""
```

问题：
- `headers` 含斜杠路径时（如 `"期末数/账面余额/金额"`），`"期末" in h_lower` 会命中，但不知道该写哪个"期末"子列
- 多列都含"期末"时全部被写入同一值（应收账款分类表有 5 个含"期末"的列）
- `"账面余额" in h_lower` 会同时命中期末和期初的账面余额列

## §2 改进方案

```python
def _resolve_value_columns(template):
    """从模板解析数值列映射：{'audited': [col_indices], 'opening': [col_indices]}。"""
    groups = template.get("_column_groups")
    headers = template.get("headers", [])
    
    if groups:
        # 优先按 _column_groups 定位
        audited_cols = []
        opening_cols = []
        for g in groups:
            group_name = g.get("group", "")
            start = g.get("start", 0)
            span = g.get("span", 1)
            if _is_ending_group(group_name):
                audited_cols.append(start)  # 组内第一个数值列
            elif _is_opening_group(group_name):
                opening_cols.append(start)
        return {"audited": audited_cols, "opening": opening_cols}
    
    # 降级：原 headers 匹配
    audited_cols = []
    opening_cols = []
    for ci, h in enumerate(headers):
        if ci == 0:
            continue
        h_clean = h.replace(" ", "").replace("　", "")
        if not h_clean:
            continue  # 跳过空列（multi_header 占位）
        if _is_ending_header(h_clean):
            audited_cols.append(ci)
        elif _is_opening_header(h_clean):
            opening_cols.append(ci)
    # 多列命中时只取第一个（保守策略，避免写错列）
    return {
        "audited": audited_cols[:1],
        "opening": opening_cols[:1],
    }

def _is_ending_group(name):
    return any(k in name for k in ("期末", "本期"))

def _is_opening_group(name):
    return any(k in name for k in ("期初", "年初", "上期"))

def _is_ending_header(h):
    # 不含 "/" 的扁平表头
    if "/" in h:
        return False  # 斜杠路径留给 _column_groups 处理
    return any(k in h for k in ("期末", "本期", "期末余额", "期末数"))

def _is_opening_header(h):
    if "/" in h:
        return False
    return any(k in h for k in ("期初", "年初", "上期", "期初余额"))
```

## §3 写入逻辑改进

```python
col_map = _resolve_value_columns(template)
for row in template_rows:
    item_name = row[0] if row else ""
    matched = tb_map.get(clean_name)
    if matched:
        new_row = list(row)
        for ci in col_map.get("audited", []):
            new_row[ci] = str(matched["audited"]) if matched["audited"] else ""
        for ci in col_map.get("opening", []):
            new_row[ci] = str(matched["opening"]) if matched["opening"] else ""
        filled_rows.append(new_row)
    else:
        filled_rows.append(row)
```

## §4 依赖关系

- **硬依赖 P2**：`_column_groups` 字段由 P2 的 `seed_consol_note_sections.py` 生成。P2 未完成时，本 spec 的改进只能走降级路径（跳过斜杠路径的 headers）
- **软依赖 P0**：前端 `ConsolNoteTab.vue` 的 multi_header 渲染已在 P0 修复，本 spec 只改后端

## §5 风险

- **只取第一列**：有的附注表可能需要写多个"期末"列（如分类表的"账面余额金额"和"坏账准备金额"），当前刷新只推合计值到第一个匹配列是合理的——明细列需要底稿子表数据
