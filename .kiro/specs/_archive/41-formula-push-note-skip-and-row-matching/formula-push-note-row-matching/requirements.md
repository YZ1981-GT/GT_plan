# 公式推送附注行匹配增强（formula-push-note-row-matching）

## 背景

公式推送引擎（`POST /api/projects/{project_id}/formula-push/run`）将试算表审定数推送到附注子表。当推送到附注时，引擎调用 `binding.note_rows()` 获取数据行，再用 `find_row(table.rows, [row["note_label"]])` 在附注子表中匹配目标行。

上一轮 spec（`formula-push-note-skip-reduction`）修复了旧格式 `_source=NULL` 拦截（B 类 38 项）、`has_obscured_data` 误报（F 类 2 项）、章节号动态定位（D 类 11 项），并为单科目底稿增加了合计行兜底。真库棘轮降至 skipped≤210 / coverage≥300。

**当前问题**：真库 PG 守卫显示 skipped=208，其中约 **140 项**的跳过原因是 `附注「{table_name}」表中没有「{row['note_label']}」行（公式推送不新建行）`。这些跳过来自两个机制：

### 机制一：per-row skip 计数膨胀

引擎在 data-row 循环内，对每个未匹配的行逐字段调用 `ctx.skip()`。随后合计行兜底成功写入了值，但 per-row 的 skip 记录已经追加到 `result.items`，被计入 `skipped_count`。这导致 skipped 数虚高——值实际已写入合计行，只是统计口径把 per-row 的"未匹配"也算作跳过。

**真库实证**（代码追踪）：
- 多科目底稿（如 F2 存货，6 个科目码）产生 `note_label = "存货_1401"` … `"存货_1461"` 共 6 行 × 2 字段 = 12 条 skip 记录
- 合计行兜底随后写入 2 条 write 记录（期末 + 期初）
- 净效果：值已写入合计行，但 skipped_count 增加了 12

受影响的 binding 类型（三类共用同一 `note_rows` 多科目逻辑）：
- `NoteDirectBinding`（note_direct.py）：F2, F5, D4（经 tier_a）
- `TierAAnchorBinding`（tier_a.py）：D4
- `BalanceAdjudicationBinding`（balance_adj.py）：H1, I1

6 条多科目附注规则（E1.note.main_rows / D4.note.main / F2.note.main / F5.note.main / H1.note.main / I1.note.main），共 19 个科目码，按 2 字段计 = 最多 **38 条** per-row skip 记录在合计行兜底已写入后仍被计为跳过。

### 机制二：单科目底稿 find_row 失败但无合计行兜底的残余

74 条单科目附注规则中，部分科目的 `note_label`（来自 `wp_account_mapping.json` 的 `account_name`）与附注子表行标签不匹配：
- 例：`note_label = "应交税费"` vs 附注子表行 = ["增值税", "消费税", "城市维护建设税", …, "合计"]
- `find_row` 精确匹配失败 → 产生 per-row skip
- 合计行兜底在上一轮已对单科目生效，值写入合计行
- 但 per-row skip 仍被计入 skipped_count

### 核心根因

per-row skip 记录在数据行循环阶段写入 `result.items`，而合计行兜底在循环之后才执行。一旦兜底成功写入，先前的 per-row skip **语义上不再是真正的跳过**（值已通过合计行落地），但统计未做修正。

## 术语

- **Formula_Push_Engine**：公式推送引擎，`backend/app/services/formula_push/engine.py` 中的 `run()` 函数及其调用的 `_push_note()` 内部函数
- **Note_Writer**：附注写入模块，`backend/app/services/formula_push/note_writer.py` 中的纯函数集合（`find_row`、`locate_table`、`read_cell` 等）
- **Binding**：推送绑定实例，实现 `PushBinding` 协议的类（`NoteDirectBinding` / `TierAAnchorBinding` / `BalanceAdjudicationBinding`），负责 `note_rows()` 产出附注行
- **Per-Row Skip**：数据行循环内因 `find_row` 返回 None 而调用 `ctx.skip()` 产生的跳过记录
- **Total_Row_Fallback**：合计行兜底逻辑，当所有数据行都未匹配附注行时，将汇总值写入附注子表的合计行
- **PG_Guard**：真库回归守卫测试 `test_formula_push_note_skip_pg.py`，在重药控股安徽项目上用 `dry_run=True` 验证 skipped/coverage 棘轮
- **Skip_Reason_Category**：跳过原因分类，如 A（行匹配失败）/ B（旧格式拦截）/ C（银行明细未取数）/ D（章节号不匹配）等

## 需求

### 1. 消除合计行兜底成功后的虚假 skip 记录

**User Story:** 作为审计平台运维人员，我希望 skipped_count 只反映真正未能写入附注的项，以便准确判断公式推送的覆盖率。

#### 验收标准

1. WHEN Total_Row_Fallback 成功写入合计行 THEN THE Formula_Push_Engine SHALL 将先前该规则产生的 Per-Row Skip 记录从 `result.items` 中移除或将其 `action` 改为 `"fallback_to_total"`（非 `"skipped"`），使其不计入 `skipped_count`。
2. WHEN Total_Row_Fallback 因附注子表无合计行而未能写入 THEN THE Formula_Push_Engine SHALL 保留原有的 Per-Row Skip 记录不变（`action` 仍为 `"skipped"`）。
3. THE Formula_Push_Engine SHALL 在 Per-Row Skip 记录被替换为 `"fallback_to_total"` 时，保留原始 `addr_id` 和 `reason` 字段（审计轨迹完整性）。
4. WHEN 多科目底稿（`len(binding.account_prefixes) > 1`）的所有数据行都未匹配附注行 THEN THE Formula_Push_Engine SHALL 同时执行 Total_Row_Fallback 并替换对应的 Per-Row Skip 记录。
5. WHEN 单科目底稿的唯一数据行未匹配附注行但 Total_Row_Fallback 成功 THEN THE Formula_Push_Engine SHALL 替换该 Per-Row Skip 记录。

### 2. 增强 `find_row` 模糊匹配能力

**User Story:** 作为审计平台运维人员，我希望附注行匹配能处理更多的标签变体，减少不必要的合计行兜底。

#### 验收标准

1. WHEN 精确匹配和去"小计"后缀匹配均失败 THEN THE Note_Writer SHALL 尝试第三级匹配：在附注子表行中查找 label 完全包含搜索标签或搜索标签完全包含 label 的行（包含匹配）。
2. WHEN 包含匹配命中多行 THEN THE Note_Writer SHALL 放弃包含匹配并返回 None（避免歧义），让引擎走 Total_Row_Fallback。
3. WHEN 包含匹配命中唯一一行 THEN THE Note_Writer SHALL 返回该行的索引。
4. THE Note_Writer SHALL 在包含匹配时排除 `is_total=True` 的行（合计行不参与模糊匹配）。

### 3. 分类别 PG 守卫棘轮

**User Story:** 作为开发者，我希望 PG 守卫能按跳过原因分类别设棘轮，以便精确定位回归来源。

#### 验收标准

1. THE PG_Guard SHALL 将跳过记录按 Skip_Reason_Category 分类统计，每个类别独立设棘轮基线。
2. WHEN 某一类别的跳过数超过其棘轮基线 THEN THE PG_Guard SHALL 在断言失败消息中明确报出该类别名称和超出量。
3. THE PG_Guard SHALL 至少区分以下类别：A（行匹配失败）/ C（银行明细未取数）/ D（章节号不匹配）/ G（模板缺定义）/ I（项目无此科目）/ other（其余）。
4. IF 新增跳过原因不属于已知类别 THEN THE PG_Guard SHALL 将其归入 "other" 类别（而非静默忽略）。

### 4. 探针脚本：分析真库 140 项的详细分布

**User Story:** 作为开发者，我需要一个探针脚本精确分解 ~140 项行匹配失败的构成，以便确认需求 1–2 的收益预期。

#### 验收标准

1. WHEN 在真库上运行探针脚本 THEN THE Probe_Script SHALL 输出每条 Per-Row Skip 的 rule_id、wp_code、note_label、目标 table_name、是否存在合计行、合计行兜底是否已成功写入。
2. THE Probe_Script SHALL 按"兜底已成功但仍被记为 skip"和"兜底未成功（真正 skip）"两类分别计数。
3. THE Probe_Script SHALL 输出按 wp_code 聚合的统计（每个底稿有多少虚假 skip / 真正 skip）。

### 5. 非功能需求

**User Story:** 作为开发者，我希望所有改动有充分的测试覆盖和回归保护。

#### 验收标准

1. THE Formula_Push_Engine SHALL 在改动后通过现有 44 个 formula_push 单元测试 + 1 个 PG 守卫（零回归）。
2. WHEN 需求 1 实施后 THEN THE PG_Guard SHALL 将 `_MAX_SKIPPED` 棘轮基线下调至实测值（只许减不许增）。
3. WHEN 需求 1 实施后 THEN THE PG_Guard SHALL 将 `_MIN_COVERAGE` 棘轮基线上调至实测值（只许增不许减）。
4. THE Formula_Push_Engine SHALL 保持改动前后 unchanged 项的 addr_id 集合不变（幂等不变量）。
5. IF 包含匹配（需求 2）引入新的匹配路径 THEN THE Note_Writer SHALL 有独立的单元测试覆盖精确匹配成功/失败、包含匹配唯一命中/多命中/零命中三种情况。
6. THE Probe_Script（需求 4）SHALL 作为一次性探针用完即删（文件名以 `_` 前缀，放在 `backend/scripts/analyze/` 下）。

## 真库实证基线

> 项目：重药控股安徽有限公司_2025（`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`）
> 上一轮 PG 守卫基线（spec: formula-push-note-skip-reduction）：
> - `_MAX_SKIPPED = 210`
> - `_MIN_COVERAGE = 300`
> - 实测 skipped=208, coverage=303

## 改动文件预估

| 文件 | 改动类型 | 涉及需求 |
|---|---|---|
| `backend/app/services/formula_push/engine.py` | 修改 | 1.1–1.5 |
| `backend/app/services/formula_push/note_writer.py` | 修改 | 2.1–2.4 |
| `backend/tests/test_formula_push_note_skip.py` | 修改 | 5.5 |
| `backend/tests/test_formula_push_note_skip_pg.py` | 修改 | 3.1–3.4, 5.2–5.3 |
| `backend/scripts/analyze/_nrm_probe_skip_breakdown.py` | 新建（一次性） | 4.1–4.3 |

## 代码现状摘要（设计参考）

### `_push_note()` 中 per-row skip 与 total fallback 的执行顺序（engine.py L680-732）

```
for row in binding.note_rows(overlay, template_type, rule):
    if row["is_total"] or row["is_memo"]: continue
    index = note_writer.find_row(table.rows, [row["note_label"], row["label"]])
    if index is not None: any_data_row_matched = True
    for field_name in rule.target.fields:
        if index is None:
            ctx.skip(...)  # ← per-row skip 在此记录
        elif not row[f"{value_key}_resolved"]:
            ctx.skip(...)
        else:
            wrote |= _push_note_cell(...)

# ── 合计行兜底 ──
if not any_data_row_matched:
    total_idx = note_writer.find_total_row(table.rows)
    if total_idx is not None:
        ...  # ← 成功写入合计行，但先前的 per-row skip 已记录
```

### `note_rows()` 多科目标签模式（三个 binding 类共用）

单科目：`note_label = self._account_name`（如 "应交税费"）
多科目：`note_label = f"{self._account_name}_{code}"`（如 "存货_1401"）

附注子表行标签是领域明细（如 "增值税"、"消费税"、"信用借款"、"质押借款"），两者不匹配。

### 多科目附注规则清单（6 条，19 个科目码）

| rule_id | wp_code | account_codes | table_name |
|---|---|---|---|
| E1.note.main_rows | E1 | 1001,1002,1012 | 货币资金 |
| D4.note.main | D4 | 6001,6051 | 营业收入和营业成本 |
| F2.note.main | F2 | 1401~1461（6个） | 存货 |
| F5.note.main | F5 | 6401,6402 | 营业收入和营业成本 |
| H1.note.main | H1 | 1601,1602,1603 | 固定资产 |
| I1.note.main | I1 | 1701,1702,1703B | 无形资产 |
