# 设计：附注 per-table guidance（收窄版）

## 现状对齐（复用而非重写）

现有 `disclosure_engine.py` 已具备：
- `is_guidance_paragraph(para) -> bool` — 提示检测（`（）`/`【】`包裹 + 关键词）
- `_is_table_title_paragraph(para) -> bool` — 标题行检测（`#`开头 / `（N）`编号 / ≤20字）
- `_NUMBERED_TITLE_RE` — 编号标题正则 `（1）xxx` / `1. xxx`
- `_infer_table_names_from_text()` — 标题→table name 回填
- `classify_template_content()` — 当前返回 `(substantive, guidance)`，guidance 是合并单串

**本 spec 只增强 `classify_template_content`，不新建并行函数。**

## 数据结构

### table_data._tables[n] 扩展
```json
{
  "_tables": [
    {
      "name": "货币资金",
      "headers": ["项目", "期末余额", "期初余额"],
      "rows": [...],
      "guidance": "（注：如有因抵押...）\n（提示：企业持有...）"
    },
    {
      "name": "受限制的货币资金明细",
      "headers": [...],
      "rows": [...]
    }
  ]
}
```
- `guidance: string`（可选，缺省即无）
- 章节级 `disclosure_notes.guidance_text` 列保持不变

## 后端：classify_template_content 增强

### 新签名
```python
def classify_template_content(
    text_sections: list[str] | None,
    text_template: str | None,
    tables: list[dict] | None = None,   # 新增：用于标题→table_idx 映射
) -> tuple[str | None, str | None, dict[int, str]]:
    """
    返回 (substantive_text, section_guidance_text, per_table_guidance)

    - substantive_text: 实质正文（合并）→ text_content
    - section_guidance_text: 无法归属到具体表 / 单表场景的通用提示 → guidance_text
    - per_table_guidance: {table_idx: guidance_str} → _tables[idx].guidance
    """
```

### 游标分配算法
```python
def classify_template_content(text_sections, text_template, tables=None):
    paragraphs = _flatten_paragraphs(text_sections, text_template)
    table_names = [(t.get("name") or "").strip() for t in (tables or [])]
    multi_table = len(table_names) > 1

    substantive_parts: list[str] = []
    section_guidance_parts: list[str] = []
    per_table_guidance: dict[int, list[str]] = {}
    current_idx = 0

    for para in paragraphs:
        if _is_table_title_paragraph(para):
            # 标题行：推进游标到匹配的 table_idx（复用现有匹配逻辑）
            if multi_table:
                idx = _match_title_to_table_idx(para, table_names, current_idx)
                if idx is not None:
                    current_idx = idx
            continue  # 标题行本身不进任何输出（现状已如此）

        if is_guidance_paragraph(para):
            if multi_table:
                per_table_guidance.setdefault(current_idx, []).append(para)
            else:
                section_guidance_parts.append(para)
            continue

        # 正文
        substantive_parts.append(para)

    substantive = "\n\n".join(substantive_parts) or None
    section_guidance = "\n\n".join(section_guidance_parts) or None
    table_guidance = {i: "\n\n".join(v) for i, v in per_table_guidance.items()}
    return substantive, section_guidance, table_guidance
```

### _match_title_to_table_idx
```python
def _match_title_to_table_idx(title: str, table_names: list[str], fallback: int) -> int | None:
    clean = title.lstrip("#").strip()
    # 1. 精确匹配
    for i, n in enumerate(table_names):
        if clean == n:
            return i
    # 2. 编号匹配 （N）xxx → idx N-1
    m = _NUMBERED_TITLE_RE.match(clean)
    if m:
        num = int(m.group(1) or m.group(2))
        if 1 <= num <= len(table_names):
            return num - 1
    # 3. 包含匹配
    for i, n in enumerate(table_names):
        if n and (clean in n or n in clean):
            return i
    # 4. 兜底：游标 +1
    nxt = fallback + 1
    return nxt if nxt < len(table_names) else None
```

### 生成流程接入（disclosure_engine 生成段）
```python
substantive, guidance, table_guidance = classify_template_content(
    text_sections, tmpl.get("text_template"), tmpl.get("tables"),
)
guidance_text = guidance
# ... 构建 built_tables 后 ...
for idx, g in table_guidance.items():
    if 0 <= idx < len(built_tables):
        built_tables[idx]["guidance"] = g
```

### 向后兼容
- 旧调用方 `classify_template_content(ts, tt)` 不传 tables → `table_guidance={}`，行为同旧（全归 section_guidance）
- 必须 grep 所有调用点适配新返回三元组（解构 `a, b = f(...)` 会报错）

## 前端：DisclosureEditor.vue

```typescript
const activeTableGuidance = computed(() => {
  const t = activeTableData.value
  if (t?.guidance?.trim()) return t.guidance
  return currentNote.value?.guidance_text || ''   // 降级章节级
})

const showGuidance = computed(() => {
  if (!activeTableGuidance.value?.trim()) return false
  const key = `${currentNote.value?.note_section}:${activeTableTab.value}`
  return !dismissedGuidance.has(key)
})

function dismissGuidance() {
  const sec = currentNote.value?.note_section
  if (sec) dismissedGuidance.add(`${sec}:${activeTableTab.value}`)
}
```

guidance bar 模板（两处 table/mixed）显示 `{{ activeTableGuidance }}`。

## 存量迁移：fix_note_per_table_guidance.py

针对 174 条 `text_content LIKE '%###%'`：
1. 按 `\n\n` / `\n` 分段
2. 标题行（`###`/`（N）`/匹配 table name）→ 移除 + 推进游标
3. 紧跟的提示段 → 移入 `_tables[idx].guidance`
4. 其余正文保留在 text_content
5. dry-run 默认；`--project-id` 限定；备份原 text_content 到 `_tables[0]._orig_text_content`（rollback 用）

### 安全
- 复用生产代码的 `classify_template_content`（迁移与生成同一套规则，避免漂移）
- savepoint 事务，验证后 commit

## Word 导出：note_word_exporter.py

`_render_note_content` 渲染每个表格前：
```python
for tbl in tables_to_render:
    g = tbl.get("guidance")
    if g:
        _add_guidance_paragraph(doc, g)  # 灰色小字段落
    self._render_table(...)
```
章节级 `guidance_text` 在所有表格前输出一次。

**待确认**：guidance 是否应进正式交付件（参考 note-guidance-text-separation 的"提示语不进交付件"裁定）。若不进，则 Word 导出跳过 guidance，仅前端编辑态显示。
