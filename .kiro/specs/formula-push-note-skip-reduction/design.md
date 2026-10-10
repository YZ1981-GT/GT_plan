# 公式推送附注跳过减少 · 设计

## §一 改动文件清单

| 文件 | 改动类型 | 涉及需求 |
|---|---|---|
| `backend/app/services/formula_push/note_writer.py` | 修改 | 1.1-1.3, 2.2, 4.1-4.2 |
| `backend/app/services/formula_push/engine.py` | 修改 | 1.4, 3.1-3.3 |
| `backend/app/services/formula_push/bindings/note_direct.py` | 修改 | 2.1 |
| `backend/tests/test_formula_push_note_skip.py` | 新建 | 5.1 |
| `backend/tests/test_formula_push_note_skip_pg.py` | 新建 | 5.2 |

不改动 `formula_push_rules.json`（需求 3.4：`section_by_template` 保留做首选/兜底）。

## §二 缺陷 B 修复：`locate_table` 放宽 `_source` 判断（需求 1.1–1.4）

### 现状

```python
# note_writer.py:165-167
sub = table_data.get("sub_table_data")
if not isinstance(sub, dict) or not sub or table_data.get("_source") not in WORKPAPER_SOURCES:
    return None, "附注由模板取数维护（尚未与底稿同步），公式推送不改写"
```

三个条件用 `or` 连接，`_source=NULL` 就直接跳过——即使 `sub_table_data` 存在且含目标子表。真库 38 个"五、"章节全部命中此分支。

### 改动

把 `_source` 判断从硬拦改为**分级判断**：

```python
def locate_table(table_data: Any, table: str) -> tuple[NoteTable | None, str | None]:
    if not isinstance(table_data, dict) or not table_data:
        return None, "附注章节尚无表格数据"

    source = table_data.get("_source")

    # ① 明确非底稿来源 → 跳过（保留原语义）
    _KNOWN_NON_WORKPAPER = ("template", "import", "migration")
    if source is not None and source not in WORKPAPER_SOURCES and source not in _KNOWN_NON_WORKPAPER:
        pass  # 未知来源：尝试定位（不假设拒绝）
    if source in _KNOWN_NON_WORKPAPER:
        return None, "附注由模板取数维护（尚未与底稿同步），公式推送不改写"

    # ② sub_table_data 存在 → 按子表定位（与现有逻辑一致）
    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict) and sub:
        rows = sub.get(table)
        if not isinstance(rows, list):
            return None, f"附注中没有「{table}」表"
        cols = table_data.get("_sub_table_columns")
        defs = ... # 现有列定义逻辑不变
        return NoteTable(rows=rows, ...), None

    # ③ 无 sub_table_data 但有顶层 rows → 旧格式兜底（需求 1.2）
    rows = table_data.get("rows")
    if isinstance(rows, list) and rows:
        # 旧格式没有列定义，用空 value_keys（find_row 仍可按 label 匹配）
        return NoteTable(rows=rows, value_keys=[], section_locked=False), None

    return None, "附注章节无可定位的表格数据"
```

### 需求 1.4：首次推送后标记 `_source`

在 `engine.py` 的 `_push_note` 中，当 `table_data` 被修改且 `_source` 为 NULL 时，追加：

```python
if table_data.get("_source") is None:
    table_data["_source"] = "workpaper"
```

这发生在 `note.table_data = table_data` 赋值之前，确保 ORM 脏检测捕获。

## §三 缺陷 A 修复：附注行匹配改进（需求 2.1–2.4）

### 现状

`note_direct` 的 `note_rows` 对单科目底稿返回 `note_label = self._account_name`（如"应交税费"），但附注子表行是明细级（增值税/消费税/…/合计）。`find_row` 精确匹配找不到。

### 策略选择

**否决方案 A**（改 binding 产出明细行）：需要每个 binding 知道附注表的行结构，coupling 太重且附注模板频繁变化。

**否决方案 B**（改 find_row 做模糊匹配）：容易误匹配（"应收账款"匹配到"应收账款_账龄"行）。

**采纳方案 C**：**单科目底稿的审定数写入合计行**。

理由：单科目底稿的试算表审定数本身就是该科目汇总数（如"应交税费"= 增值税+消费税+…的汇总），写入合计行在语义上正确。合计行用 `is_total=True` 或 `row_type="total"` 标识，100% 存在于所有附注子表（真库实证：25 个跳过的章节每个都有合计行）。

### 改动

1. **`note_direct.py` `note_rows`**：单科目底稿产出的**非 `is_total`** 数据行改为 `is_total=True`，使其走现有的 `_push_note_total` 路径。

   但这样会绕过 `find_row`——不对。更好的方式：

2. **`engine.py` `_push_note`**：在现有"遍历 binding.note_rows → find_row 匹配"循环之后，增加一个**合计行兜底**逻辑：

```python
# 现有循环结束后
if not wrote and not any_data_row_matched:
    # 所有数据行都未命中附注行 → 尝试合计行兜底（需求 2.3）
    total_idx = note_writer.find_total_row(table.rows)
    if total_idx is not None:
        # 用 binding.note_rows 中 is_total=True 的行（已含汇总值）
        total_note_row = next((r for r in binding.note_rows(...) if r["is_total"]), None)
        if total_note_row is not None:
            for field_name in rule.target.fields:
                value_key, period = note_writer.NOTE_FIELDS[field_name]
                if total_note_row[f"{value_key}_resolved"]:
                    value = total_note_row[value_key]
                    addr = note_addr_id(section, table_name, "合计", period)
                    _push_note_cell(ctx, ..., row=table.rows[total_idx], ...)
```

不改变现有 `_push_note_total`（它的作用是"数据行写完后重算合计"），而是在"所有数据行都没命中"时**直接写合计行**。

3. **`find_row` 不变**——保持精确匹配的纯净语义。如果以后附注子表增加了与科目同名的汇总行，精确匹配自然命中，兜底逻辑不触发。

### 约束

- 合计行兜底仅在 `len(binding.account_prefixes) == 1`（单科目）时启用。多科目底稿仍按现有逻辑逐行匹配 + 合计行重算。
- 兜底写入的 `addr_id` 用 `note_label="合计"`（与 `_push_note_total` 一致），避免地址空间冲突。

## §四 缺陷 D 修复：章节号动态定位（需求 3.1–3.4）

### 现状

```python
# engine.py:594
section = rule.target.sections.get(template_type)
```

直接从规则 JSON 的 `section_by_template` 取硬编码章节号，然后在 612 行做 `section_title` 比对——不匹配就跳过。

### 改动

在 `section_title` 比对失败后，增加反查：

```python
section = rule.target.sections.get(template_type) if template_type else None
if section is None:
    ctx.skip(...)
    return None

# 现有查询 disclosure_notes
note = (await ctx.db.execute(...)).scalar_one_or_none()

if note is not None and (note.section_title or "").strip() != _title_check_name:
    # ── 章节号不匹配：尝试按 section_title 反查（需求 3.1） ──
    fallback = (await ctx.db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == ctx.project_id,
            DisclosureNote.year == ctx.year,
            DisclosureNote.section_title == _title_check_name,
            DisclosureNote.is_deleted == sa.false(),
            DisclosureNote.note_section.like(f"{'五' if 'listed' == template_type else '八'}%"),
        ).with_for_update()
    )).scalars().all()
    if len(fallback) == 1:
        logger.info(
            "formula_push: 章节号动态定位 %s → %s（规则声明 %s）",
            _title_check_name, fallback[0].note_section, section,
        )
        note = fallback[0]
        section = fallback[0].note_section  # 更新后续使用的 section
    # else: 0 条或多条 → 走原逻辑（reason 已在上面赋值）
```

### 约束

- 反查范围用 `note_section LIKE '五%'`（listed）或 `'八%'`（soe）缩窄，避免匹配到"三、"/"六、"会计政策章节中的同名标题。
- 反查结果必须**唯一**（1 条）才采纳。0 条或多条视为歧义，回退硬编码逻辑。
- `section_by_template` 保留做首选和兜底——如果硬编码章节号的 `section_title` 匹配成功，不触发反查（零性能开销）。

## §五 缺陷 F 修复：`has_obscured_data` 误报（需求 4.1–4.2）

### 现状

```python
# note_writer.py:265-268
for k, v in r.items():
    if k in ("label", "row_type", "is_total", "is_label"):
        continue
    if v is not None and v != 0 and v != "" and v != "0":
        return f"顶层 rows 含非空数值（{k}={v!r}）"
```

`values=[None, None]` 是 list，`list != None` / `list != 0` / `list != ""` 全为 True → 误报。

### 改动

```python
_SKIP_KEYS = frozenset({"label", "row_type", "is_total", "is_label"})

for k, v in r.items():
    if k in _SKIP_KEYS or k.startswith("_"):
        continue
    if k == "values":
        # values 是列表，逐元素检查
        if isinstance(v, list) and any(
            e is not None and e != 0 and e != "" and e != "0"
            for e in v
        ):
            return f"顶层 rows 含非空数值（values={v!r}）"
        continue
    if v is not None and v != 0 and v != "" and v != "0":
        return f"顶层 rows 含非空数值（{k}={v!r}）"
```

## §六 测试策略

### 单元测试（`test_formula_push_note_skip.py`）

| 用例 | 覆盖需求 |
|---|---|
| `test_locate_table_source_null_with_sub_table` | 1.1 |
| `test_locate_table_source_null_old_format_rows` | 1.2 |
| `test_locate_table_source_template_rejected` | 1.3 |
| `test_source_marked_after_first_push` | 1.4 |
| `test_total_row_fallback_single_account` | 2.3 |
| `test_total_row_fallback_not_triggered_multi_account` | 2.4 |
| `test_section_dynamic_lookup_on_mismatch` | 3.1 |
| `test_section_dynamic_lookup_ambiguous_skip` | 3.2 |
| `test_has_obscured_data_values_all_none` | 4.1 |
| `test_has_obscured_data_skip_underscore_keys` | 4.2 |

### 真库回归守卫（`test_formula_push_note_skip_pg.py`）

- 在重药控股安徽项目上重跑推送，断言 `skipped_count <= 45`（需求 5.2）。
- 断言 `written_count + unchanged_count + kept_count >= 330`（覆盖率下限）。
- 断言修复前后 `unchanged` 项的值不变（幂等不变量，需求 5.4）。

### 变异验证

- 每个修复点至少一条变异：回退改动后对应测试打红。
- `locate_table` 把 `_source=NULL` 改回拒绝 → `test_locate_table_source_null_*` 红。
- `_push_note` 删掉反查逻辑 → `test_section_dynamic_lookup_on_mismatch` 红。
- `has_obscured_data` 删掉 `k == "values"` 分支 → `test_has_obscured_data_values_all_none` 红。

## §七 风险与缓解

| 风险 | 缓解 |
|---|---|
| 旧格式 rows 行结构与子表行结构不一致 | `locate_table` 返回的 `NoteTable.value_keys` 为空时，`write_cell` 走 `_is_f3` 的 `values` 列表路径，与旧格式 `{label, values}` 结构兼容 |
| 反查到错误章节 | 唯一性约束（只取 1 条）+ 日志记录 + `section_title` 精确匹配 |
| 合计行兜底写入与 `_push_note_total` 冲突 | 兜底逻辑设置 `skip_total_recalc=True`，跳过后续的 `_push_note_total`（避免合计被重算覆盖） |
| 已有测试依赖 `_source` 判断被跳过 | 搜索现有测试中 mock `_source=None` 的场景，确认改动后行为 |
