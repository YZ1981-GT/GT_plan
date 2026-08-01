# Design Document

## Overview

把附注模块从「生成时静态快照」改成「跟随底稿实际内容」，四条主线：

1. **自动同步**：`WORKPAPER_SAVED` 事件驱动披露章节同步，手动按钮与自动走同一服务函数
2. **模板回流**：新增差异计算 + 补齐能力，让既有项目能补上模板后加的表
3. **单一真源**：迁移 legacy `rows` / `_tables` 到 `sub_table_data`，消费方统一经投影器
4. **空表语义**：空表折叠 + 「本期无此情形」标注，互斥披露方式不误报未完成

不新建机制：自动同步复用现有 `sync_from_workpaper`（含其全部守卫），结构渲染复用 `note_sub_table_projector`，两级表头继续走 `ColumnDef.group → _column_groups`。

灰度开关 `DISCLOSURE_AUTO_SYNC_ENABLED` 默认关，关闭时行为与改造前完全一致。

## Architecture

```
底稿保存
  └─ WORKPAPER_SAVED (EventBus)
       └─ [新] disclosure_auto_sync_handler
            ├─ 解析 wp → sheet_name → section_id（note_workpaper_sync_registry）
            ├─ 去抖（同 wp+sheet 在 N 秒内合并）
            └─ sync_from_workpaper（既有，守卫不动）
                 ├─ manual_override 守卫 → skipped
                 ├─ sub_table_data 浅合并 + 空载荷 no-op
                 └─ _removed_table_keys 清理

模板回流（用户触发）
  └─ [新] note_template_reflow_service
       ├─ diff(template_section, note_section) → {missing, renamed, column_drift}
       ├─ preview（只读，供 UI 展示）
       └─ apply（只加不覆盖 + template_lineage 记账）

读取（统一入口，不变）
  └─ note_sub_table_projector.project(sub_table_data, _sub_table_columns)
       ├─ 模块页 get_note_detail
       ├─ Word 导出 note_word_exporter._effective_table_data
       └─ 批量导出 bulk_export_service

迁移（一次性，破坏性，需确认）
  └─ [新] scripts/fix/migrate_legacy_note_snapshots.py
       --dry-run / --check / --apply --confirm
```

**关键约束**：自动同步 handler 只做「路由 + 去抖 + fail-soft」，业务逻辑全在既有 `sync_from_workpaper` 内，避免出现第二套同步语义。

## Components and Interfaces

### 1. `disclosure_auto_sync_handler`（新，`backend/app/services/event_handlers/`）

```python
async def handle_workpaper_saved_for_disclosure(
    db: AsyncSession, payload: EventPayload,
) -> dict[str, Any]:
    """WORKPAPER_SAVED → 披露章节自动同步（fail-soft）。

    Returns: {"status": "synced"|"skipped"|"no_mapping"|"failed", "section_id":..., "reason":...}
    """
```

- 由 `note_workpaper_sync_registry.json` 解析 `sheet_name → section_id`；无映射直接 `no_mapping` 返回，不报错
- 去抖：`(wp_id, sheet_name)` 为键，窗口内合并（进程内 TTL 字典，重启丢失可接受）
- 任何异常都吞掉 → 记 warning + 置 `is_stale=true`，绝不冒泡到底稿保存事务

### 2. `note_template_reflow_service`（新）

```python
@dataclass(frozen=True)
class SectionDiff:
    missing_tables: list[str]        # 模板有、附注无
    renamed_tables: list[tuple[str, str]]  # (旧名, 新名)
    column_drift: list[str]          # 列结构与模板不一致的表名
    extra_tables: list[str]          # 附注有、模板无（只报告不删）

async def diff_section(db, note_id) -> SectionDiff: ...
async def apply_reflow(db, note_id, *, include_local_override: bool = False) -> ReflowResult: ...
```

- `apply_reflow` **只加不覆盖**：新增表写入空骨架（模板 rows）+ 列头；已有表只在 `column_drift` 时更新 `_sub_table_columns`，行数据不动
- 改名判定：模板表带 `_renamed_from` 字段时按其迁移；否则按「列结构同构 + 附注侧该名不在模板中」推断，推断结果只在 preview 展示，需用户确认

### 3. `migrate_legacy_note_snapshots.py`（新，`backend/scripts/fix/`）

- 选择集：`sub_table_data` 为空/缺失 且（`rows` 或 `_tables` 非空）
- `rows`（单表）→ 用章节模板的第一张表名作键；`_tables`（多表）→ 按各表 `name` 为键
- 删 `row_type == "header_label"` 行，其语义并入 `_sub_table_columns` 的 `group`
- 备份：迁移前把原 `table_data` 整体写入 `template_lineage._legacy_backup`
- 默认 `--dry-run`；`--apply` 必须配 `--confirm`

### 4. 空表判定（前后端共用口径）

后端 `note_empty_table_detector.py`（新，纯函数）：

```python
def is_empty_table(rows: list[dict], columns: list[dict] | None) -> bool:
    """所有数据行的数值列全空/零 且 文本列无内容 → True。合计行不计入判断。"""
```

前端 `disclosureEmptyTable.ts`（新，纯函数，与后端同口径 + vitest 镜像后端用例）。

### 5. 互斥披露组（`note_template_*.json` 表级新字段）

```json
{ "name": "按组合计提存货跌价准备", "exclusive_group": "inventory-provision-portfolio" }
```

同 `exclusive_group` 的表构成「或」关系：只要组内有一张非空，其余空表不触发未完成提示。字段缺省时行为不变。

## Data Models

### `disclosure_notes.table_data`（改造后形态）

```jsonc
{
  "sub_table_data":      { "表名": [ { "业务键": 值 } ] },   // 唯一权威存储
  "_sub_table_columns":  { "表名": [ ColumnDef ] },          // 列头元数据
  "_source": "workpaper", "_current_standard": "listed",
  "_last_sync_wp": "...", "_last_sync_sheet": "..."
  // rows / _tables 顶层键：迁移后移除
}
```

### `ColumnDef`（沿用，无新增字段）

```typescript
interface ColumnDef {
  key: string; label: string; is_label?: boolean
  group?: string      // 多级表头父级
  flat?: boolean      // 显式单级（抑制前缀推断）
  format?: 'amount' | 'percent' | 'text'
}
```

### `template_lineage`（新增子键）

```jsonc
{
  "_reflow_history": [
    { "at": "2026-07-30T10:00:00Z", "template_version": "...",
      "added": ["确认为存货的数据资源"], "column_updated": ["开发产品"] }
  ],
  "_legacy_backup": { /* 迁移前 table_data 原样 */ }
}
```

### 灰度开关

| 开关 | 默认 | 作用 |
|------|------|------|
| `DISCLOSURE_AUTO_SYNC_ENABLED` | false | R1 自动同步 |
| `DISCLOSURE_EMPTY_TABLE_COLLAPSE` | false | R4 空表折叠 |

## Correctness Properties

### Property 1: 自动同步与手动同步结果等价

对任意底稿载荷 P 与章节 S，自动同步后 S 的 `table_data` 与手动点击同步后的 `table_data` 逐键相等（除时间戳类字段）。

**Validates: Requirements 1.1, 1.6**

### Property 2: 自动同步不放大写库

同一 `(wp_id, sheet_name)` 在去抖窗口内的 N 次保存，最终对 `disclosure_notes` 的写入次数 ≤ 1，且最终内容等于最后一次载荷的同步结果。

**Validates: Requirements 1.7**

### Property 3: 自动同步失败不影响底稿保存

当 `sync_from_workpaper` 抛任意异常时，底稿保存事务仍提交成功，且该章节 `is_stale` 为 true。

**Validates: Requirements 1.4**

### Property 4: 模板回流只增不减

对任意章节 S 与模板 T，`apply_reflow(S, T)` 后：S 中原有每张表的行数与行标签集合不变；表集合为原集合 ∪ 模板缺失表集合。

**Validates: Requirements 2.2, 6.1**

### Property 5: 手工覆盖免疫

若 S 标记 `is_local_override` 或 manual_override，则自动同步与模板回流（未显式包含 override）后 S 的 `table_data` 完全不变。

**Validates: Requirements 1.3, 2.6, 6.2**

### Property 6: legacy 迁移保结构

对任意仅含 legacy 快照的章节 S，迁移后经投影器得到的表数与每表行数，等于迁移前从 legacy 快照读到的表数与行数（`header_label` 行除外）。

**Validates: Requirements 3.2, 3.3**

### Property 7: 三消费方结构一致

迁移后对任意章节，模块页 `get_note_detail`、`note_word_exporter`、`bulk_export_service` 得到的表名序列与每表列头序列完全一致。

**Validates: Requirements 3.1, 3.6**

### Property 8: 空表判定不吞非空数据

若某表存在任一数值列非零或任一文本列非空的数据行，则 `is_empty_table` 返回 false（合计行不参与判断）。

**Validates: Requirements 4.1**

### Property 9: 互斥组不误报

同一 `exclusive_group` 内若有一张表非空，则该组其余空表不产生「未完成」提示。

**Validates: Requirements 4.5**

### Property 10: 开关关闭即无行为变化

`DISCLOSURE_AUTO_SYNC_ENABLED = false` 且 `DISCLOSURE_EMPTY_TABLE_COLLAPSE = false` 时，所有既有测试结果与改造前一致。

**Validates: Requirements 6.5**

## Error Handling

| 场景 | 处理 |
|------|------|
| `sheet_name` 无 section 映射 | 返回 `no_mapping`，不记 error 日志（正常情况：非披露 sheet） |
| 同步抛异常 | fail-soft：warning 日志 + `is_stale=true`，底稿保存不回滚 |
| 章节 manual_override | 返回 `skipped` + reason，写审计日志 |
| 模板 JSON 缺失/损坏 | 回流预览报「模板不可用」，不修改任何数据 |
| 改名推断歧义（多个候选） | preview 列出候选，要求人工选择，不自动迁移 |
| 迁移遇到无法解析的 legacy 结构 | 跳过该章节并记入报告，不部分写入 |
| 来源底稿已删除 | 界面显示「来源底稿缺失」，禁用同步按钮 |

## Testing Strategy

**后端单测**：自动同步 handler（映射/去抖/fail-soft/skipped 四条路径）、`diff_section` 的四类差异、`apply_reflow` 只增不减、`is_empty_table` 边界（全零 / 含合计行 / 文本列非空）。

**后端契约测试**：三消费方结构一致（Property 7）；迁移前后表数行数守恒（Property 6）；开关关闭时既有断言不变（Property 10）。

**PBT（hypothesis，`max_examples=5`）**：Property 4（只增不减）、Property 8（空表判定）用随机行集合验证。

**前端单测**：`disclosureEmptyTable.ts` 镜像后端用例；过期横幅与差异明细渲染。

**迁移演练**：先在 `--dry-run` 下对全部现存章节跑一遍，产出报告核对表数行数；再对单个项目 `--apply` 后用 Playwright 对比迁移前后截图与表集合。

**Playwright 实测**：底稿改数据保存 → 不点同步 → 直接开附注模块确认已更新；模板补齐后既有项目出现新表；非房企项目空表折叠且标注「本期无此情形」。

**回归**：`test_note_inventory_structure.py`、`test_note_word_export_sub_table.py`、`test_f2_disclosure_import_export.py`、`f2NoteSectionMap.spec.ts` 全绿，不放宽断言。
