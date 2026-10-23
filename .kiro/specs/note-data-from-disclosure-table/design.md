# 附注数据统一从披露表获取 — 设计文档

## §1 架构概览

### 正确的数据流

```
四表(TB) ──→ 调整分录(AJE/RJE) ──→ 审定数 ──→ 底稿披露表(working_paper)
                                                    │ 唯一权威源
                                                    ▼
                                              disclosure_notes
```

### 两条管道统一

| 维度 | 管道 A（前端同步） | 管道 B（后端刷新） |
|------|-------------------|-------------------|
| 触发 | 用户保存披露表 | `WORKPAPER_SAVED` 事件 / 手动「刷新附注」 |
| 数据源 | 前端内存中的披露表快照 | 后端从 DB 读取的 `wp_entries.data` |
| 行处理 | 全量替换（整表 rows） | 全量替换（整表 rows） |
| 值处理 | 携带在行中 | 携带在行中 |
| 写入目标 | `disclosure_notes.table_data.sub_table_data` | 同左 |

两条管道的数据源相同（披露表），输出格式相同（`sub_table_data`），写入路径相同（`sync_from_workpaper`），不会冲突。

## §2 后端刷新服务设计

### 2.1 新服务 `note_disclosure_refresh_service.py`

```python
async def refresh_note_from_disclosure(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,              # 如 "D2"
    *,
    triggered_by: UUID | None = None,
) -> RefreshResult:
    """从底稿披露表读取 sub_table_data → 写入附注对应章节。

    流程：
    1. 按 wp_code 查 wp_index → 找到 working_paper 记录
    2. 从 wp_entries 或 working_paper.data 中提取 sub_table_data
    3. 确定目标附注章节（从 NOTE_SECTION_MAP 按 wp_code + template_type 查）
    4. 调用 sync_from_workpaper() 写入附注（复用管道 A 的后端逻辑）
    """
```

### 2.2 披露表数据读取

披露表的 `sub_table_data` 由前端 `buildXSyncPayload` 构建后写入 DB。后端刷新时**直接从 DB 读取已保存的 `sub_table_data`**，不需要在后端重新实现 69 个 payload builder。

读取路径：
```
wp_index WHERE wp_code = 'D2' AND project_id = X
  → working_paper WHERE id = wp_index.wp_id
    → disclosure_notes WHERE note_section = section_id
      → table_data.sub_table_data  ← 这就是前端同步过来的数据
```

**关键**：如果用户从未打开过披露表（`sub_table_data` 为空），后端刷新无数据可读 → 提示用户先完成披露表编制。

### 2.3 附注章节映射 `NOTE_SECTION_MAP`

从现有 `formula_push_rules.json` 的 `section_by_template` 提取，转为静态映射：

```python
NOTE_SECTION_MAP = {
    "D1": {"listed": "五、4", "soe": "八、4"},
    "D2": {"listed": "五、5", "soe": "八、5"},
    "E1": {"listed": "五、1", "soe": "八、1"},
    # ... 全部 80 个 wp_code → 章节映射
}
```

### 2.4 `WORKPAPER_SAVED` 事件处理

现有 `WORKPAPER_SAVED` 事件已经在 EventBus 中发布。新增一个 handler：

```python
@event_handler("WORKPAPER_SAVED")
async def on_workpaper_saved_refresh_note(payload: EventPayload):
    """底稿保存时自动刷新关联附注。"""
    wp_code = payload.wp_code
    if wp_code not in NOTE_SECTION_MAP:
        return  # 非披露类底稿，跳过
    await refresh_note_from_disclosure(
        db, payload.project_id, payload.year, wp_code,
        triggered_by=payload.user_id,
    )
```

## §3 公式规则修订

### 3.1 80 条规则的改造方向

现有 80 条规则全部是 `source.kind: "derivation"`，每条有一个 `name` 指向 binding 的 `note_rows()` 方法。改造：

**不改 rules JSON 的 target 结构**（章节映射、表名、fields 保留），**改 binding 的 `note_rows()` 实现**：从直接取 TB 改为从披露表的 `sub_table_data` 读取。

### 3.2 binding 改造

以 `TierAAnchorBinding.note_rows()` 为例，当前实现：
```python
# 当前：直接从 TB 取
ending, _ = _tb_value(tb_data, code, "期末余额")
opening, _ = _tb_value(tb_data, code, "年初余额")
```

改为：
```python
# 改造后：从披露表 sub_table_data 读取
rows = disclosure_sub_table.get(table_name, [])
for row in rows:
    ending = row.get("end_amount") or row.get("ending") or 0
    opening = row.get("prior_amount") or row.get("opening") or 0
```

### 3.3 新的 binding 基类 `DisclosureSourceBinding`

```python
class DisclosureSourceBinding:
    """从披露表取数的 binding 基类。"""

    async def load_sources(self, db, project_id, year, wp_id):
        """读取披露表已保存的 sub_table_data。"""
        note = await self._load_disclosure_note(db, project_id, year)
        self._sub_table_data = note.table_data.get("sub_table_data", {}) if note else {}

    def note_rows(self, entries, template_type, rule):
        """从 sub_table_data 直接返回行（已经是附注格式）。"""
        table_name = rule.target.resolve_table(template_type)
        rows = self._sub_table_data.get(table_name, [])
        return self._normalize_rows(rows, rule.target.fields)
```

## §4 刷新性能设计

### 4.1 单科目刷新（< 2s）

```
读 wp_index (1 query) → 读 disclosure_note (1 query) → 读 sub_table_data (in-memory)
→ 写 disclosure_note (1 update) → commit
```

总共 3 个 DB 查询 + 1 个 JSON 操作，远在 2 秒内。

### 4.2 批量刷新（< 10s）

```python
async def refresh_all_notes(db, project_id, year):
    """一键刷新全部附注：并发读取所有披露表，批量写入。"""
    # 1. 一次查询拉出所有有 sub_table_data 的 disclosure_notes
    # 2. 按 wp_code 分组，逐个调用 refresh_note_from_disclosure
    # 3. 统一 commit
```

80 个科目按 `asyncio.gather` 并发读写，总时间由最慢的单次决定（< 2s）。

### 4.3 增量刷新 vs 全量

- `WORKPAPER_SAVED` 事件 → 只刷新该底稿对应的章节（增量）
- 「刷新附注」按钮 → 全量刷新所有章节

## §5 管道 A/B 协同策略

### 5.1 谁先写？

- 用户编辑披露表并保存 → 管道 A（前端）先到（800ms 防抖后立即 POST）
- `WORKPAPER_SAVED` 事件 → 管道 B（后端）稍后到（事件处理队列）
- 两者写的是**同一份数据**（都来自同一个 `sub_table_data`），所以后到的那个是幂等的——值不变，不覆盖

### 5.2 管道 A 未触发时

用户导入四表 → TB 更新 → 调整分录审批 → 审定数回写到披露表 → 此时如果用户**没有打开过**该底稿的披露表，`sub_table_data` 可能还是空的或旧的。

**处理**：后端刷新检测到 `sub_table_data` 为空时，不强行建骨架，而是标记该章节为 `stale`（需要用户去披露表确认）。附注界面显示提示：「此章节的数据待更新，请先打开底稿 D2 的披露表确认后保存」。

### 5.3 未来方向

长期来看，69 个前端 payload builder 的核心逻辑可以逐步迁移到后端（每个科目的分类逻辑、动态行构建逻辑），实现完全不依赖前端的后端驱动刷新。但这不在本 spec 范围。

## §6 改动范围评估

| 文件/模块 | 改动类型 | 工作量 |
|-----------|---------|--------|
| `note_disclosure_refresh_service.py` | 新建 | 中 |
| `formula_push/bindings/*.py` | 改造 note_rows | 大（80 个 binding） |
| `formula_push_rules.json` | 修订 source 描述 | 中 |
| `formula_push/engine.py` | 增加动态建行逻辑 | 中 |
| `event_handlers/` | 新增 WORKPAPER_SAVED handler | 小 |
| `routers/disclosure_notes.py` | 新增「刷新附注」端点 | 小 |
| 前端附注编辑器 | 新增「刷新」按钮 | 小 |
| 测试 | 新增 + 修改 | 大 |

## §7 风险与降级

- **风险 1**：披露表从未保存过（`sub_table_data` 为空）→ 降级为 stale 标记 + 提示用户
- **风险 2**：binding 改造时 79 条规则的 fields 映射可能有遗漏 → 逐 wp_code 回归测试
- **风险 3**：管道 A/B 并发写入同一行 → 用 `FOR UPDATE` 串行（现有机制已有）
- **风险 4**：刷新性能超预期 → 用 `asyncio.gather` 并发 + 按需增量

## §8 偏离记录

- 偏离 D1：合并附注的集团模板下推不在本 spec 范围（R6.3 明确排除）
- 偏离 D2：69 个前端 payload builder 不在本 spec 迁移到后端（§5.3 标记为未来方向）
- 偏离 D3：公式推送的底稿域规则（187 条）不改——它们的数据流 TB→底稿 本来就是对的
