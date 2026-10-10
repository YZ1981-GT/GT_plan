# 公式推送附注行匹配增强 · 设计文档

## Overview

本 spec 解决公式推送引擎（`formula_push.engine`）向附注子表推送审定数时，因行匹配失败产生的 **skipped_count 虚高** 问题。

真库基线（重药控股安徽 2025）：skipped=208，其中约 140 项原因是 `附注「{table_name}」表中没有「{note_label}」行`。但这些项中有相当比例已由合计行兜底（Total_Row_Fallback）成功写入——值落地了，统计却仍记为"跳过"。

本设计包含三个互补改进：

1. **消除虚假 skip**（需求 1）：延迟 per-row skip 记录的写入时机，合计行兜底成功后将其重分类为 `fallback_to_total`，使 `skipped_count` 只反映真正未写入的项。
2. **增强模糊匹配**（需求 2）：在 `find_row` 的精确匹配和去后缀匹配之后，增加第三级包含匹配（substring），减少不必要的合计行兜底。
3. **分类别 PG 守卫**（需求 3）：将 PG 守卫从单一棘轮拆分为按跳过原因分类的独立棘轮，精确定位回归来源。

附带一个一次性探针脚本（需求 4）用于获取真实分布数据。

### 设计原则

- **只改统计口径，不改写入语义**：合计行兜底的写入逻辑不变，只是 skip 记录的分类更准确。
- **审计轨迹完整**：重分类后的 `fallback_to_total` 项保留原始 `addr_id` 和 `reason`，`detail()` 输出可追溯。
- **模糊匹配保守优先**：包含匹配仅在唯一命中时生效，多命中或零命中一律放弃让引擎走合计行兜底。

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  engine.py::_push_note()                                    │
│                                                             │
│  for row in binding.note_rows():                            │
│      index = find_row(table.rows, labels)  ──改动②──→       │
│      if index is None:                                      │
│          pending_row_skips.append(...)  ──改动①──→ 延迟记录  │
│      else:                                                  │
│          _push_note_cell(...)                                │
│                                                             │
│  ── Total_Row_Fallback ──                                   │
│  if not any_data_row_matched:                               │
│      total_idx = find_total_row(...)                         │
│      if total_idx and source_row:                            │
│          _push_note_cell(...)                                │
│          fallback_wrote = True  ──改动①──→ 标记成功          │
│                                                             │
│  ── Flush pending skips ──改动①──                           │
│  for (addr, reason) in pending_row_skips:                   │
│      action = FALLBACK_TO_TOTAL if fallback_wrote else SKIPPED│
│      result.items.append(PushItem(..., action, reason=reason))│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  note_writer.py::find_row()                                 │
│                                                             │
│  ① 精确匹配（现有）                                        │
│  ② 去"小计"后缀匹配（现有）                                │
│  ③ 包含匹配（新增）──改动②──                               │
│     for label in wanted:                                    │
│         candidates = [i for i,r in enum(rows)               │
│                       if label in row_label(r)              │
│                          or row_label(r) in label           │
│                       and not r.get("is_total")]            │
│         if len(candidates) == 1: return candidates[0]       │
│     return None                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  results.py                                                 │
│                                                             │
│  FALLBACK_TO_TOTAL = "fallback_to_total"  ──改动③──新常量   │
│                                                             │
│  skipped_count = count(SKIPPED, CONFLICT)                   │
│  # FALLBACK_TO_TOTAL 不在此集合内 → 不计入 skipped_count    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  test_formula_push_note_skip_pg.py                          │
│                                                             │
│  _SKIP_CATEGORIES = {A/C/D/G/I/other}  ──改动④──           │
│  per-category ratchet assertions                            │
│  total _MAX_SKIPPED as safety net                           │
└─────────────────────────────────────────────────────────────┘
```

### 改动影响面

| 模块 | 改动 | 影响面 |
|---|---|---|
| `results.py` | 新增 `FALLBACK_TO_TOTAL` 常量 | 零影响：`skipped_count` 只计 `SKIPPED`/`CONFLICT`，新常量不在其中 |
| `engine.py::_push_note` | 延迟 skip 记录 + 兜底后重分类 | 仅影响 `result.items` 中的 `action` 字段值；写入语义不变 |
| `note_writer.py::find_row` | 新增第三级包含匹配 | 只在前两级均失败时触发；唯一命中才返回索引，多命中返回 None |
| `PG 守卫` | 分类别棘轮 | 只影响测试断言，不影响生产代码 |

### 改动不涉及

- `_push_note_cell` / `_push_note_total` / `_record_note` 写入逻辑
- `decide_note` / `decide` 判定逻辑
- `panel.py` / `triggers.py` 对 `skipped_count` 的读取（它们读的是 property，行为随 `count()` 自动变化）
- `formula_push_run` 表的 `detail` 字段（`PushItem.as_dict()` 序列化所有 action 值，`fallback_to_total` 自然进入 JSONB）

## Components and Interfaces

### 改动①：延迟 skip 记录（engine.py `_push_note`）

**现状**：数据行循环内，`find_row` 返回 None 时立即调用 `ctx.skip()` 追加 `PushItem(action=SKIPPED)` 到 `result.items`。后续合计行兜底成功写入后，这些 skip 记录已无法修改。

**改动**：

```python
# 新增局部变量
pending_row_skips: list[tuple[str, str]] = []  # (addr_id, reason)

# 循环内：find_row 返回 None 时，不立即 ctx.skip()，而是收集到 pending
for row in binding.note_rows(overlay, template_type, rule):
    ...
    for field_name in rule.target.fields:
        ...
        if index is None:
            # 改动：延迟记录
            pending_row_skips.append((
                addr,
                f"附注「{table_name}」表中没有「{row['note_label']}」行（公式推送不新建行）"
            ))
        elif not row[f"{value_key}_resolved"]:
            # 不延迟：这是"本项目无此科目"的真正 skip，与行匹配无关
            ctx.skip(rule.rule_id, "note", "note", addr,
                     "底稿未取到该行数值（本项目无此科目），附注保持原值")
        else:
            wrote |= _push_note_cell(...)

# 合计行兜底（现有逻辑不变，新增 fallback_wrote 标记）
fallback_wrote = False
if not any_data_row_matched:
    total_idx = note_writer.find_total_row(table.rows)
    if total_idx is not None:
        ...  # 现有 source_row 选取和写入逻辑
        if source_row is not None:
            for field_name in rule.target.fields:
                ...
                wrote |= _push_note_cell(...)
            skip_total_recalc = True
            fallback_wrote = True  # 新增

# 新增：统一 flush pending skips
for addr, reason in pending_row_skips:
    action = FALLBACK_TO_TOTAL if fallback_wrote else SKIPPED
    ctx.result.items.append(PushItem(
        rule.rule_id, "note", "note", addr, action, reason=reason
    ))
```

**关键约束**：
- `"底稿未取到该行数值"` 的 skip **不参与延迟**——它代表的是科目不存在的真正跳过，不是行匹配问题。
- `pending_row_skips` 是 `_push_note` 函数内的局部变量，作用域清晰，不跨函数传播。
- `fallback_wrote` 只有在 `_push_note_cell` 返回 True（至少一个字段成功写入）时才为 True。更精确地说，`skip_total_recalc = True` 的条件已经保证了 `source_row is not None` 且至少调用了 `_push_note_cell`；但 `_push_note_cell` 可能因判定为 unchanged 而返回 False。因此 `fallback_wrote` 应该在合计行兜底**至少有一次 `_push_note_cell` 调用**（即 `source_row` 有 resolved 值）时为 True。具体实现：`fallback_wrote` 在循环结束后、`skip_total_recalc = True` 同时设置。

**修订**：仔细分析后，`fallback_wrote` 的语义应该是"合计行兜底路径被进入且产生了有意义的动作"。即使 `_push_note_cell` 返回 False（unchanged），合计行路径仍然被执行了——值已经由合计行承载。因此 `fallback_wrote` 跟随 `skip_total_recalc` 即可：

```python
if source_row is not None:
    ...
    skip_total_recalc = True
    fallback_wrote = True
```

### 改动②：包含匹配（note_writer.py `find_row`）

**现有两级**：
1. 精确匹配 `row_label(row) == label`
2. 去后缀匹配 `row_label(row) == label.rstrip("小计")`

**新增第三级**：

```python
# ③ 包含匹配（新增）
for label in wanted:
    if not label:
        continue
    candidates: list[int] = []
    for index, row in enumerate(rows):
        if isinstance(row, dict) and row.get("is_total"):
            continue  # AC 2.4: 合计行不参与模糊匹配
        rl = row_label(row)
        if not rl:
            continue
        if label in rl or rl in label:
            candidates.append(index)
    if len(candidates) == 1:
        return candidates[0]  # AC 2.3: 唯一命中
    # len==0 或 len>1: 不返回，继续尝试下一个 label
return None
```

**安全性分析**：

| 场景 | 搜索标签 | 附注行 | 匹配结果 | 说明 |
|---|---|---|---|---|
| 唯一包含 | `"应收账款"` | `["应收账款——按账龄", "坏账准备", "合计"]` | `candidates=[0]` → 返回 0 | 有用场景 |
| 歧义包含 | `"借款"` | `["信用借款", "质押借款", "合计"]` | `candidates=[0,1]` → 放弃 | 安全：多命中走兜底 |
| 零命中 | `"存货_1401"` | `["原材料", "库存商品", "合计"]` | `candidates=[]` → 放弃 | 安全：无命中走兜底 |
| 合计排除 | `"合计"` | `["增值税", "合计"]` | `candidates=[]` | AC 2.4: 合计行被排除 |
| 短标签 | `"税"` | `["增值税", "消费税", "城建税"]` | `candidates=[0,1,2]` → 放弃 | 安全：多命中走兜底 |

**真库收益预估**：根据 requirements 分析，140 项行匹配失败中：
- ~38 项来自多科目底稿 per-row skip（合计行兜底已写入）→ 需求 1 消除
- 剩余 ~102 项来自单科目底稿 per-row skip → 部分由需求 1 消除（单科目兜底已成功），部分可能由需求 2 的包含匹配直接命中而不需要兜底

### 改动③：新增常量（results.py）

```python
SKIPPED = "skipped"
CONFLICT = "conflict"
FALLBACK_TO_TOTAL = "fallback_to_total"  # 新增
```

`RunResult.skipped_count` 定义为 `count(SKIPPED, CONFLICT)`，不包含 `FALLBACK_TO_TOTAL`。无需改动 `skipped_count` 的实现。

`RunResult.detail()` 序列化 `items` 列表中所有 `PushItem`，`FALLBACK_TO_TOTAL` 自然出现在 JSONB 的 `action` 字段中——审计轨迹可见。

### 改动④：分类别 PG 守卫（test_formula_push_note_skip_pg.py）

**分类规则**（正则匹配 `reason` 字段）：

```python
_SKIP_CATEGORIES: dict[str, str] = {
    "A": r"没有.*行",                    # 行匹配失败
    "C": r"银行明细|取数.*未完成",        # E1 银行明细未取数
    "D": r"不是「.*」|章节号",            # 章节号不匹配
    "G": r"没有.*表定义|无法建骨架",      # 模板缺定义
    "I": r"本项目无此科目",               # 科目不存在
}
```

匹配顺序按字典遍历；首次匹配即分类，未匹配归入 `"other"`。

**棘轮基线**（探针脚本运行后设定具体值）：

```python
_MAX_SKIPPED_BY_CATEGORY: dict[str, int] = {
    "A": TBD,   # 探针运行后填写
    "C": TBD,
    "D": TBD,
    "G": TBD,
    "I": TBD,
    "other": TBD,
}
```

**断言结构**：

```python
# 1. 分类别棘轮（主断言）
for cat, max_count in _MAX_SKIPPED_BY_CATEGORY.items():
    actual = category_counts.get(cat, 0)
    assert actual <= max_count, f"类别 {cat} skipped={actual} 超过棘轮 {max_count}"

# 2. 未知类别归入 other（AC 3.4）
other_count = sum(v for k, v in category_counts.items() if k == "other")
assert other_count <= _MAX_SKIPPED_BY_CATEGORY["other"]

# 3. 总量安全网（保留）
assert total_skipped <= _MAX_SKIPPED
```

## Data Models

### `PushItem` 变更

`PushItem.action` 字段的取值集合扩展：

| action 值 | 语义 | 计入 `skipped_count` | 现有/新增 |
|---|---|---|---|
| `"skipped"` | 真正跳过（未写入任何目标） | ✅ | 现有 |
| `"conflict"` | 冲突跳过 | ✅ | 现有 |
| `"write"` | 写入 | ❌ | 现有 |
| `"unchanged"` | 值未变 | ❌ | 现有 |
| `"keep_locked"` / `"keep_manual"` / `"keep_pending"` | 保持 | ❌ | 现有 |
| **`"fallback_to_total"`** | **行匹配失败但合计行兜底已写入** | **❌** | **新增** |

`FALLBACK_TO_TOTAL` 项的字段含义：
- `addr_id`：原始数据行的地址坐标（保留，非合计行的地址）
- `reason`：原始跳过原因（保留，如 `附注「存货」表中没有「存货_1401」行`）
- `rule_id`、`stage`、`domain`：与原 skip 相同

### PG 守卫分类数据结构

```python
@dataclass
class SkipCategoryStats:
    category: str       # "A" / "C" / "D" / "G" / "I" / "other"
    count: int
    max_allowed: int
    sample_reasons: list[str]  # 至多 3 条样例，诊断用
```

### 探针脚本输出格式

```
=== 行匹配失败分析 ===
rule_id          | wp_code | note_label      | table_name | has_total | fallback_wrote
-----------------+---------+-----------------+------------+-----------+--------------
F2.note.main     | F2      | 存货_1401       | 存货       | ✅        | ✅
F2.note.main     | F2      | 存货_1403       | 存货       | ✅        | ✅
N4.note.main     | N4      | 应交税费        | 应交税费   | ✅        | ✅
...

=== 按 wp_code 聚合 ===
wp_code | 虚假 skip（兜底已写入） | 真正 skip（兜底未成功）
--------+------------------------+------------------------
F2      | 12                     | 0
E1      | 6                      | 0
N4      | 2                      | 0
...

=== 总计 ===
虚假 skip（兜底已成功但仍被记为 skip）: XX
真正 skip（兜底未成功，值确实未写入）: XX
合计: XX
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Prework Reflection

从 prework 分析的 18 条验收标准中，识别出以下可测试属性。经去重合并：

- 1.1 + 1.3 合并：兜底成功时重分类 + 字段保留是同一个不变量的两面
- 2.1 + 2.3 合并：唯一包含命中返回索引是同一属性的正面描述
- 1.4 / 1.5 是 1.1 的具体示例（多科目/单科目），由同一属性覆盖
- 5.4（幂等不变量）已由 PG 守卫的双 dry_run 断言覆盖，不重复

最终 **6 个独立属性**：

### Property 1: 合计行兜底成功后 skip 记录被重分类且字段保留

*For any* 附注推送场景，若所有数据行的 `find_row` 均返回 None 且合计行兜底（Total_Row_Fallback）成功写入，则该规则先前产生的所有 per-row skip 记录的 `action` 应为 `"fallback_to_total"`（而非 `"skipped"`），且每条记录的 `addr_id` 和 `reason` 与延迟前收集的原始值完全相同。

**Validates: Requirements 1.1, 1.3**

### Property 2: 合计行兜底失败时 skip 记录保持 skipped

*For any* 附注推送场景，若合计行兜底未执行（附注子表无合计行）或未成功写入，则该规则的所有 per-row skip 记录的 `action` 应保持为 `"skipped"`。

**Validates: Requirements 1.2**

### Property 3: 包含匹配唯一命中返回正确索引

*For any* 非空附注行列表和非空搜索标签，若精确匹配和去后缀匹配均未命中，但恰好有唯一一行非 `is_total` 行的 label 与搜索标签满足包含关系（`label in row_label` 或 `row_label in label`），则 `find_row` 应返回该行的索引。

**Validates: Requirements 2.1, 2.3**

### Property 4: 包含匹配多命中返回 None

*For any* 附注行列表和搜索标签，若包含匹配命中多于一行非 `is_total` 行，则 `find_row` 应返回 None（放弃匹配，让引擎走合计行兜底）。

**Validates: Requirements 2.2**

### Property 5: 包含匹配排除合计行

*For any* 附注行列表，`find_row` 的包含匹配阶段不应返回 `is_total=True` 的行的索引。即使合计行的 label 与搜索标签满足包含关系且是唯一匹配，也应返回 None。

**Validates: Requirements 2.4**

### Property 6: 跳过原因分类完备性

*For any* 跳过原因字符串，`_categorize` 函数应返回 `_SKIP_CATEGORIES` 中某个已知类别或 `"other"`；不存在未分类的情况。对于匹配已知类别模式的原因字符串，应返回对应的类别标识。

**Validates: Requirements 3.1, 3.4**

## Error Handling

### 引擎层（engine.py）

| 错误场景 | 处理方式 | 改动影响 |
|---|---|---|
| `pending_row_skips` 为空（所有行都匹配成功） | flush 循环不执行，无副作用 | 无影响 |
| `fallback_wrote=False`（无合计行或 source_row 无 resolved 值） | 所有 pending 项以 `SKIPPED` 写入，行为与改动前一致 | 降级安全 |
| `binding.note_rows()` 返回空列表 | `pending_row_skips` 为空 + `any_data_row_matched=False` → 走合计行兜底（但无 source_row）→ 无 pending 项 | 无影响 |
| `_push_note_cell` 在合计行写入时抛异常 | `fallback_wrote` 不会被设置（异常在循环内传播），pending 项以 `SKIPPED` 写入 | 降级安全 |

### 模糊匹配层（note_writer.py）

| 错误场景 | 处理方式 | 改动影响 |
|---|---|---|
| `label` 为空字符串 | `if not label: continue` 跳过 | 无影响 |
| `row_label(row)` 为空字符串 | `if not rl: continue` 跳过 | 无影响 |
| `labels` 参数全部为空 | `wanted` 列表为空，三级匹配均不执行，返回 None | 与改动前一致 |
| 包含匹配中 `label` 是另一个 `row_label` 的子串但多行匹配 | `len(candidates) > 1` → 不返回，继续循环 → 最终返回 None | 安全降级到合计行兜底 |

### PG 守卫层

| 错误场景 | 处理方式 |
|---|---|
| 新增跳过原因不匹配任何已知模式 | 归入 `"other"` 类别（AC 3.4） |
| `"other"` 类别超过棘轮 | 断言失败，提示需要新增分类或调查原因 |
| 项目不存在或年度为空 | `pytest.skip()`（现有行为不变） |

## Testing Strategy

### PBT 框架

使用 `hypothesis` 库（项目已安装），`max_examples=5`（用户偏好）。

每个 property test 引用设计文档中的 Property 编号，tag 格式：
`Feature: formula-push-note-row-matching, Property {N}: {title}`

### 测试矩阵

| 测试 | 类型 | 覆盖 Property / AC | 文件 |
|---|---|---|---|
| `test_deferred_skip_reclassified_on_fallback` | PBT | Property 1 / AC 1.1, 1.3 | `test_formula_push_note_skip.py` |
| `test_deferred_skip_stays_skipped_without_total` | PBT | Property 2 / AC 1.2 | `test_formula_push_note_skip.py` |
| `test_deferred_skip_multi_account` | Example | AC 1.4 | `test_formula_push_note_skip.py` |
| `test_deferred_skip_single_account` | Example | AC 1.5 | `test_formula_push_note_skip.py` |
| `test_find_row_contains_unique_hit` | PBT | Property 3 / AC 2.1, 2.3 | `test_formula_push_note_skip.py` |
| `test_find_row_contains_multi_hit_returns_none` | PBT | Property 4 / AC 2.2 | `test_formula_push_note_skip.py` |
| `test_find_row_contains_excludes_total` | PBT | Property 5 / AC 2.4 | `test_formula_push_note_skip.py` |
| `test_find_row_exact_match_not_affected` | Example（回归） | AC 2（回归） | `test_formula_push_note_skip.py` |
| `test_categorize_known_patterns` | PBT | Property 6 / AC 3.1, 3.4 | `test_formula_push_note_skip_pg.py` |
| `test_pg_guard_per_category_ratchets` | Integration | AC 3.1–3.4 | `test_formula_push_note_skip_pg.py` |
| `test_pg_guard_category_assertion_message` | Example | AC 3.2 | `test_formula_push_note_skip_pg.py` |
| 现有 44 个 formula_push 单元测试 | 回归 | AC 5.1 | 多文件 |
| 现有 PG 守卫（更新棘轮基线后） | Integration | AC 5.2–5.4 | `test_formula_push_note_skip_pg.py` |

### 变异测试

| 变异操作 | 预期打红的测试 | 验证目标 |
|---|---|---|
| 删除 `fallback_wrote = True` 赋值 | `test_deferred_skip_reclassified_on_fallback` | Property 1 |
| 将 `FALLBACK_TO_TOTAL if fallback_wrote else SKIPPED` 改为 `SKIPPED` | `test_deferred_skip_reclassified_on_fallback` | Property 1 |
| 删除包含匹配（第三级） | `test_find_row_contains_unique_hit` | Property 3 |
| 删除 `len(candidates) == 1` 判断（改为 `len(candidates) > 0`） | `test_find_row_contains_multi_hit_returns_none` | Property 4 |
| 删除 `row.get("is_total")` 排除条件 | `test_find_row_contains_excludes_total` | Property 5 |
| 将 `_categorize` 默认返回值从 `"other"` 改为 `"A"` | `test_categorize_known_patterns` | Property 6 |

### 实施顺序

1. **Task 0: 探针脚本**（需求 4）  
   新建 `backend/scripts/analyze/_nrm_probe_skip_breakdown.py`，在真库运行获取行匹配失败的详细分布。用于设定分类别棘轮基线。

2. **Task 1: 延迟 skip 记录 + 重分类**（需求 1）  
   修改 `engine.py::_push_note` + `results.py` 新增 `FALLBACK_TO_TOTAL` 常量。

3. **Task 2: 包含匹配**（需求 2）  
   修改 `note_writer.py::find_row` 新增第三级匹配。

4. **Task 3: 分类别 PG 守卫**（需求 3）  
   修改 `test_formula_push_note_skip_pg.py` 新增分类逻辑和 per-category 棘轮。

5. **Task 4: 新增单元测试 + PBT + 变异验证**（需求 5）  
   修改 `test_formula_push_note_skip.py` 新增所有测试矩阵中的测试。

6. **Task 5: 真库验证 + 棘轮更新**（需求 5.2–5.3）  
   运行 PG 守卫，更新 `_MAX_SKIPPED` 和 `_MIN_COVERAGE` 基线。

7. **Task 6: 清理**（需求 5.6）  
   删除探针脚本 + 更新 memory.md。
