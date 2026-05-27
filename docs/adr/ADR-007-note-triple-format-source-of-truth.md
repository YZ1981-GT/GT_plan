# ADR-007: 附注三式联动 — `DisclosureNote.table_data` 唯一真源

**Status**: Accepted
**Date**: 2026-05-27
**Sprint**: disclosure-note-full-revamp / Sprint 1.5 Task 1.5.5

## 背景

附注模块同时存在四种数据形态：

| 形态 | 落地位置 | 用途 |
|------|---------|------|
| `DisclosureNote.table_data` (JSONB) | PostgreSQL `disclosure_notes` | 真源，含 `headers / rows / _cell_modes / _cell_meta / _formulas / _check_presets` |
| `structure.json` | 内存或临时文件（`triple_format_adapter` 转换） | 三式联动的中间形式，对接 Univer / HTML / Excel |
| `xlsx` 导出 | `structure_to_excel` 输出 | 用户下载 / 导入 / 编辑后回写 |
| HTML 渲染 | `structure_to_html` 输出 | 在线编辑器 / Word 联动预览 |

当前问题：

1. **写入入口分散** — 自动生成（`disclosure_engine.update_note_values`）/ 用户在线编辑（前端 PATCH）/ Excel 上传重建 / 公式执行（`note_formula_generator.execute_note_formulas`）/ 三式联动同步等多条路径并行写 `table_data`。
2. **sidecar 字段易丢失** — `_cell_modes` (auto/manual/locked) 和 `_cell_meta` (binding_id/source) 是 D1 的核心契约；任何忽略这两字段的写入都会破坏「自动重算保留手动覆盖」语义。
3. **三式形态彼此可往返但不等价** — `structure.json → xlsx → structure.json` 可 round-trip，但 `table_data → structure.json → table_data` 在中间形态丢失 sidecar 时不可逆。

## 决策

**`DisclosureNote.table_data` 是附注唯一真源**，其他三种形态全部是「镜像 / 导出」。

### 决策 1：所有 structure.json → table_data 写入必须经过单入口

**单入口**：`backend/app/services/triple_format_adapter.py::DisclosureNoteAdapter.update_note_from_structure`

**职责清单**：

1. 加载现有 `note.table_data`（含 `headers / rows / _cell_modes / _cell_meta / _formulas`）。
2. 从 `structure.sheets[0].cells` 重建 `rows`，但 **保留** 旧 row 的 `_cell_modes / _cell_meta` sidecar。
3. 单元格 `mode != "auto"` 的格子（manual / locked）跳过 structure 端的值更新，确保自动重算不覆盖人工。
4. `_formulas` 顶层 dict 不被 structure 写入污染（仅 `note_formula_generator.execute_note_formulas` 写入）。
5. `flag_modified(note, "table_data")` 让 SQLAlchemy 识别 JSONB 变更。

### 决策 2：三种镜像形态的职责严格切分

| 形态 | 唯一职责 | 禁止 |
|------|---------|------|
| `structure.json` | 在线编辑 / 三式联动转换的中间形态 | 持久化（用完即弃） |
| `xlsx` 导出 | 用户下载 / 离线编辑 | 作为权威数据源 |
| HTML 渲染 | 只读预览 / 编辑器渲染 | 直接 PATCH 修改后端数据 |

任何「从 xlsx / HTML 反向更新」必须先转 `structure.json`，再走单入口 `update_note_from_structure`。

### 决策 3：自动生成 / 公式执行 / 用户编辑三条路径汇聚

| 路径 | 入口 | 写 `table_data` 的方式 |
|------|------|----------------------|
| 自动生成（引擎重生成） | `disclosure_engine.update_note_values` | 直接重建 `rows`，但 `note_cell_merge.merge_table_data` 保留 manual / locked sidecar |
| 公式执行 | `note_formula_generator.execute_note_formulas` | 仅在 `_cell_modes[col] == "auto"` 时写 `values[col]`；写 `_formulas[key].evaluated_at` |
| 用户在线编辑 | 前端 PATCH → `triple_format_adapter.update_note_from_structure` | 同决策 1 |
| Excel 上传重建 | 上传 → `excel_to_structure` → `update_note_from_structure` | 同决策 1 |

三条路径的共同不变量：**`_cell_modes / _cell_meta` 的字段拓扑不丢失**。

## 后果

### 正面

- **三态语义稳定**：auto / manual / locked 不会被误覆盖，无需在多个入口重复防御代码。
- **CellTrace 可行**：`_cell_meta.binding_id` 反查链路只在真源中维护，前端任何角度看到的 binding_id 都来自同一份 JSONB。
- **调试边界明确**：`table_data` 错位时只查写入路径，三种镜像不需要逐一排查。

### 代价

- 任何新功能（导入新格式 / 新增编辑入口）都必须接入单入口；绕开 `update_note_from_structure` 直接 `note.table_data = ...` 是反模式，code review 必须拦截。
- 镜像形态的 round-trip 测试（`xlsx → structure → xlsx`）只验证镜像层正确性，**不能** 替代对 `update_note_from_structure` 的端到端 sidecar 保留测试。

### CI 卡点

- grep `note.table_data\s*=` 在 `triple_format_adapter` 之外的 `app/services/` / `app/routers/` 必须为 0（除 `update_note_values` / `execute_note_formulas` / 内部辅助函数白名单）。
- `test_sprint1_e2e_roundtrip.py` 必须覆盖「auto 重算 → manual 编辑 → 再 auto 重算」路径，确保 manual 不被冲掉。

## 关联 ADR / Spec

- **ADR-008**（待落地，Sprint 2 Task 2.8）：Note cell mode persistence (auto/manual/locked) 三态详细语义。
- **ADR-009**（待落地，Sprint 2 Task 2.8）：GT Word template style namespace（`GTNote*` 命名）。
- **ADR-010**（待落地，Sprint 4 Task 4.5）：Note custom template versioning。
- **Spec**：`.kiro/specs/disclosure-note-full-revamp/`（D1 sidecar 兼容铁律 + D4 公式 DSL 沉淀 + D7 Word 致同样式）。

## 考虑过但未采用

### 取消 sidecar，让 `_cell_modes` 跟 `values` 平行存在

**否决原因**：`values` 是数组（按 col_idx 索引），`_cell_modes` 是 `dict[str, str]`（key 是 col_idx 的字符串），两者本就在同一 row 下。把 sidecar 拆到顶层会让 row 自包含性丢失，多表（`_tables`）场景下 row 与 sidecar 分离更难维护。

### 三式形态都允许写真源（多入口模型）

**否决原因**：每个入口都要重复实现 sidecar 保留逻辑，极易出 bug；Sprint 0 真实迁移脚本 `migrate_disclosure_notes_to_v2.py` 已经印证「sidecar 保留是必要不变量」。

### structure.json 升级为持久层

**否决原因**：JSONB 在 PostgreSQL 中已支持索引 / 部分更新，再叠一层 structure.json 文件层只增加复杂度，没有性能或语义收益。
