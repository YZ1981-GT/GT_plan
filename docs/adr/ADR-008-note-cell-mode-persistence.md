# ADR-008: 附注单元格 三态模式持久化（auto / manual / locked）

**Status**: Accepted
**Date**: 2026-05-27
**Sprint**: disclosure-note-full-revamp / Sprint 2 Task 2.8

## 背景

附注引擎需要在「自动重算」与「人工覆盖」之间共存：

- 模板填数（`disclosure_engine.generate_notes` / `update_note_values`）会按 binding 重新计算 `row.values[col]`。
- 用户在线编辑（DisclosureEditor）会修改单个单元格 — 这次编辑的值不应被下次重算冲掉。
- 公式锁定（`note_formula_generator.execute_note_formulas`）会标记某些格"由公式产生"，避免被自动算覆盖。

如果只用一个布尔字段（如 `is_manual`），无法区分「用户手填」「公式锁定」「自动取数」三种来源，导致：

1. **重算误覆盖手工** — 引擎拿不到"这格是手填的"信号，把用户输入冲掉。
2. **公式与手填混淆** — 同一格既不知道是 manual 还是 formula 产物。
3. **CellTrace 无法精准展示来源** — D5 溯源链需要明确标识"这格的值是哪里来的"。

## 决策

每个附注单元格携带 **mode（三态枚举）+ meta（sidecar 元数据）**，持久化在 row 内的 `_cell_modes` / `_cell_meta` 字典中。

### 决策 1：三态枚举语义

| mode    | 触发场景 | 重算行为 | 用户编辑行为 | 视觉提示（前端） |
|---------|---------|---------|-------------|----------------|
| `auto`  | 引擎按 binding 自动取数 | **覆盖** `values[col]` | 编辑后转为 `manual` + 备份 `manual_value` | 默认（无提示） |
| `manual`| 用户手工编辑 / 引擎缺数据降级 | **保留** `values[col]`，不覆盖 | 直接编辑 `manual_value` | 灰色边框 cell |
| `locked`| 公式产物 / 业务规则锁定 | **保留** `values[col]`，不覆盖 | 编辑前必须解锁（点公式 → 转 manual） | 浅绿底色 cell |

### 决策 2：sidecar 字段拓扑（D1 兼容铁律）

每个含 `values` 的 row 必须含两个新字段：

```jsonc
{
  "label": "库存现金",
  "values": [1234.56, 800.0],
  "row_type": "data",          // ADR-008: 行类型 (data / subtotal / total / 其他)
  "_cell_modes": {              // ADR-008: 单元格 mode 三态字典
    "0": "auto",                //   key = col_idx (str)，与 values 索引对齐
    "1": "manual"
  },
  "_cell_meta": {               // ADR-008: 单元格元数据 sidecar
    "0": {
      "manual_value": null,     //   manual 备份值（auto → manual 时填）
      "semantic": "closing_balance",  // 列语义（绑定时识别）
      "binding_id": "五、1 货币资金.库存现金.closing_balance"  // CellTrace 反查键
    },
    "1": { "manual_value": 800.0, "semantic": "opening_balance", "binding_id": "..." }
  }
}
```

**字段不变量**（任何写入路径都必须保持）：

1. `_cell_modes` 的 key 集合 ⊆ `[0..len(values)-1]`（字符串化）。
2. `_cell_meta` 的 key 集合与 `_cell_modes` 一致（一一对应）。
3. `mode == "manual"` 当且仅当 `_cell_meta[col].manual_value` 非 None（首次手编时备份触发）。
4. `mode == "locked"` 时 `_cell_meta[col].manual_value` 保持 None（locked 不备份用户态值）。

### 决策 3：三态合并算法（`note_cell_merge.merge_row_preserving_cell_modes`）

引擎重算 → 与旧 row 合并的 5 步算法：

1. **mode 优先级**：旧 row 的 `_cell_modes` 决定该 col 的目标 mode；新 row（引擎产物）的 `_cell_modes` 默认全是 `auto`。
2. **values 合并**：
   - `auto` 列：`merged.values[col] = new.values[col]`（用新值）
   - `manual` 列：`merged.values[col] = old.values[col]`（保留旧值），并把首次进入 manual 的旧值备份到 `_cell_meta[col].manual_value`（首次备份后不再覆盖）
   - `locked` 列：`merged.values[col] = old.values[col]`（保留旧值），不动 `_cell_meta`
3. **headers 与 row label**：从 new 取（结构性变化以模板为准）。
4. **新增列**（new 列数 > old 列数）：默认 `auto` mode。
5. **缺失列**（new 列数 < old 列数）：合并后裁剪到 new 列数（旧的多余 sidecar 丢弃）。

### 决策 4：CellTrace 反查链路

`_cell_meta[col].binding_id` 是 D5 CellTrace 端点（`GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace`）的反查键：

```
binding_id = f"{note.note_section}.{row.label}.{semantic}"
```

格式硬约定（见 `disclosure_engine._build_with_binding`）。后端 trace_cell 用 `note_section + label + semantic` 三段重新查 `note_template_bindings.json` 反推完整 binding 定义。

## 后果

### 正面

- **手工不丢**：用户编辑后下次重算自动跳过 manual 列，符合"自动是辅助、人工是权威"的审计直觉。
- **PBT 可验证**：`test_note_persistence_property.py` 4 个不变量（auto/manual/locked round-trip + manual_value 不丢失）能形式化覆盖三态合并。
- **CellTrace 端点纯净**：trace_cell 只读 `_cell_meta`，不依赖任何中间状态。
- **多入口共享一套规则**：generate_notes / update_note_values / structure_to_table_data / formula_eval 全部走同一 merge 算法。

### 代价

- 任何写 `note.table_data` 的代码路径必须显式调 `merge_row_preserving_cell_modes`（或 `merge_table_data_preserving_cell_modes`）。绕开此函数直接赋值是反模式，CI 卡点 grep 拦截。
- 老版本（v1）数据无 sidecar，需要一次性迁移（`scripts/migrate_disclosure_notes_to_v2.py`）。
- sidecar 字段在 JSONB 中冗余存储（每 cell 至少 3 字段），单 note 增加 ~20% 存储；在 173 章节 × 187 项目规模下可接受（< 50MB 增量）。

### CI 卡点

- 模板 JSON `account_codes` 引用 = 0（已在 Sprint 1 Task 1.8 落地）。
- `test_note_persistence_property.py` 4 不变量必须 100% 通过（max_examples=80）。
- `test_sprint1_e2e_roundtrip.py` 端到端 sidecar 保留测试必须通过。

## 关联

- **ADR-007**：附注三式联动单一真源 — 决定了 `table_data` 是 sidecar 持久化的载体。
- **Spec**：`.kiro/specs/disclosure-note-full-revamp/` D1 sidecar 兼容铁律。
- **代码**：
  - 三态合并：`backend/app/services/note_cell_merge.py`
  - 引擎写入：`backend/app/services/disclosure_engine._build_with_binding`
  - 迁移脚本：`scripts/migrate_disclosure_notes_to_v2.py`
  - CellTrace：`backend/app/services/disclosure_engine.trace_cell`（Sprint 2 Task 2.3）

## 考虑过但未采用

### 单一布尔 `is_manual` 字段

**否决原因**：无法区分 manual 与 locked。一旦引入公式锁定（locked），又要再加字段，字段拓扑不稳定。三态枚举一次性覆盖。

### `_cell_modes` 用数组替代 dict

**否决原因**：JSONB 数组的部分更新比 dict 慢；且数组下标必须密集（不能稀疏），与 row 缺失列场景不兼容。

### 把 `_cell_meta.binding_id` 拆成单独字段（source / field / account_codes）

**否决原因**：CellTrace 端点会重新去 `note_template_bindings.json` 拉完整 binding，binding_id 只是反查键。如果存完整 binding 副本会导致模板版本变更后副本陈旧（"binding 漂移"问题）。

### 用 SQL 子表 (`disclosure_note_cells`) 而非 JSONB sidecar

**否决原因**：附注单元格 ~10000 量级 / project，SQL 子表会让"按 row 取整体" 慢 5-10x；JSONB row 自包含读写性能更优。索引需求由 `binding_id` 反查链路上的 `note_section` 解决。
