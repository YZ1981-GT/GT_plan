# Task 12 — D 循环账龄骨架审计与对齐（后端）证据

spec: `four-table-extraction-entry-completion` / Phase 2 / Task 12
Requirements: 2.5, 7.1, 7.2, 7.3（配套 Property 5 / Property 8）

## 结论摘要

这是一次**审计-对齐**（audit-and-align），不是重写。

1. **审计（读实际 builders）**：D3/D5/D6/D7 的 `import-aux-balance` 迁移端点
   **全部已把账龄字段留空**——无任何 `bucket[first_key]=amount` / 整额落首段的活体伪造
   （Task 4 迁移的结论属实，本次逐文件复核确认）。grep 自检：
   `first_key` / `within1=...balance` / `agePrior1y=...prior` 等塞首段模式在四个端点与
   `d_cycle_extraction/*.py` 中**零命中**（仅存在于说明「不得这样做」的注释里）。

2. **对齐（配置驱动空骨架）**：审计前四端点**都 omit 账龄键**（完全不写），前端行结构对缺失的
   账龄键默认取 0。按 Requirement 7.2/7.3，取数应 emit **由 `get_effective_segments` 键控的
   空骨架**。据前端各循环行形态**逐循环**处理（宁缺勿造，保留各自键约定）。

## 逐循环审计findings

| 循环 | 端点 | 审计前账龄状态 | 行账龄键约定 | 前端是否 useAgingConfig 驱动 | 本次处理 |
|------|------|----------------|--------------|------------------------------|----------|
| **D3** | `d3_import_aux_balance` → D3-2 | 留空（omit 键） | **nested keyed** `agingPrior`/`agingAudited`（2-period） | 是（`useD3Detail` + `useAgingConfig('D3')`） | ✅ **已接配置驱动骨架** |
| **D7** | `d7_import_aux_balance` → D7-2 | 留空（omit 键） | **nested keyed** `agingPrior`/`agingAudited`（2-period） | 是（`useD7Detail` + `useAgingConfig('D7')`） | ✅ **已接配置驱动骨架** |
| **D5** | `d5_import_aux_balance` → D5-2 | 无账龄（源表无账龄列） | 无 aging 字段 | N/A（D5-2 应收款项融资无账龄列） | ⏸ **N/A：源模板无账龄列，不生成骨架**（宁缺勿造） |
| **D6** | `d6_import_aux_balance` → D6-2 | 留空（`build_d6_detail_rows_from_aux` 只写录入列） | **flat legacy keys** `agePrior1y`/`agePrior1to2y`/`agePrior2to3y`/`agePrior3yAbove` + `ageEnd1y`/… | **否**（`useD6Detail` 用硬编码 4 档 flat keys，未接 `useAgingConfig`） | ⏸ **deferred（见下）**：仅保证不塞首段 |

## 已接配置驱动骨架的实现（D3/D7）

- 新增共享件 `d_cycle_extraction/d_aux_import.py`：
  - `resolve_d_cycle_segments(db, project_id, subject)` —— `await get_effective_segments(UUID(project_id), subject, db)`，
    `try/except` 失败按 `DEFAULT_SUBJECT_PRESETS`（D3/D7→THREE_YEAR）兜底、**不回退单段**
    （Requirement 7.6），失败时 `logger.exception` 记 ERROR（不静默）。范式对齐
    `_k1_import_export._resolve_k1_segments`（K1 是 3-period 参照实现，Task 11）。
  - `build_two_period_aging_skeleton(segments)` —— 生成 `{agingPrior:{k:0}, agingAudited:{k:0}}`，
    **只两组**（无 `agingCurrent`，因 D3/D5/D6/D7 均为 2-period，对齐 `useAgingConfig` 的
    `THREE_PERIOD_SUBJECTS = {D2,K1,K3,G5,F1}`），每段值=0（Property 5），键来自 `get_effective_segments`（Property 8）。
  - `_segment_keys` / `_empty_aging` 私有工具（去重保序 / 全 0）。
- D3/D7 端点在归集后 `segments = await resolve_d_cycle_segments(...)` +
  `aging_skeleton = build_two_period_aging_skeleton(segments)`，每行注入
  `agingPrior=dict(...)` / `agingAudited=dict(...)`（每行独立副本，防共享引用）。
- **无任何硬编码段**：审计前四端点均无硬编码段列表可删（它们本就 omit 账龄）；
  新代码段键一律经 `get_effective_segments`，兜底走 subject 默认 preset 而非写死单段。
- 成功 message 增补「账龄骨架已按项目账龄配置生成 N 段（值全为空），请按实际账龄人工填列」。

## D6 deferred 理由（宁缺勿造）

D6-2 明细行账龄用 **flat legacy keys**（`agePrior1y` / `ageEnd1y` 等 8 个硬编码 4 档字段，
见 `useD6Detail.ts` 的 `DetailRow` 与 `newRow()`），前端**未接 `useAgingConfig`**（`useD6Detail`
无 `useAgingConfig` 引用；仅同循环的 `useD6EclCalculation` 以 `subject='D2'` 用到）。
若强行让后端 emit `get_effective_segments` 键控的骨架（如五年段 6 键），键名与前端 flat
4 档字段**对不上**，反而污染。故：

- **不为 D6 生成配置驱动骨架**（会造前后端键不一致的假数据结构）。
- **仅保证不塞首段**：`build_d6_detail_rows_from_aux` 只写录入列（`contractName`/`customerName`/
  `priorUnadjusted`），完全不写任何 `agePrior*`/`ageEnd*` 键，前端 flat 字段默认 0 →
  Property 5 成立（无伪造账龄）。已有单测 `test_d6_detail_aggregation.py::test_build_rows_only_record_columns`
  锁死"行 dict 只含录入列、不含账龄列"。
- **skeleton-sync 对 D6 deferred**，前置依赖 = 前端 `useD6Detail` 迁 flat→nested keyed +
  接 `useAgingConfig`（属前端 Task 13 范畴 / 或后续 D6 独立 spec），届时后端可复用
  `build_two_period_aging_skeleton` 一行接上。

## 守卫与变异检验

- 新增 `backend/tests/d_cycle_extraction/test_d_cycle_aging_skeleton.py`（8 测试全 PASS）：
  纯函数（两组无 current / 键集==段键有序 / 全 0 不塞首段 / 键数随枚举 / 兼容对象字典字符串）
  + 端点行为（D3/D7 端点 emit 的行带 nested 空骨架、键==段键、值全 0）。
- **变异检验（四态判定，均 RED）**：
  1. 把 `_empty_aging` 改成首段塞 999 → `test_skeleton_all_zero_never_stuffs_first_segment`
     + `test_empty_aging_all_zero` + D3/D7 端点测试 **4 项 RED**（Property 5 生效）。
  2. 把 `resolve_d_cycle_segments` 兜底改成硬编码 `[{"key":"within1"}]` 单段 →
     D3/D7 端点测试 **2 项 RED**（`['within1'] != ['within1','y1to2','y2to3','over3']`，
     Property 8 生效，证明骨架键来自配置而非硬编码）。
- 回归：`test_four_table_entry_guards.py`（5）+ `test_d6_detail_aggregation.py`（11）全 PASS，
  merge 语义与 D6 只写录入列不受影响。

## 文件改动

- `backend/app/services/d_cycle_extraction/d_aux_import.py`（新增 4 个 helper + `__all__`）
- `backend/app/routers/wp_render_strategies/_d3_import_export.py`（D3 端点注入骨架 + message）
- `backend/app/routers/wp_render_strategies/_d7_import_export.py`（D7 端点注入骨架 + message）
- `backend/tests/d_cycle_extraction/test_d_cycle_aging_skeleton.py`（新增守卫）

D5/D6 端点**未改动**（N/A / deferred，理由如上）。
