# Implementation Plan

## Overview

按 8 波闭合前置 spec 两个 P0 缺口：P0-1（Tier A 真生效 = **保存跳过写错库 parsed_data + 返回 evaluated_value 供即时显示，不做 DB 写回** + GET 附 value + **render transient 公式驱动 seed 作主机制**）+ P0-2（明细表维度归集 render **transient** 自动 seed，试点 D6-2，**子开关门控**）。原则：复用既有机制不新造第 3 套四表库读取；`is_known_anchor` 判别 D-cycle 锚点 vs 网格 cell；`get_active_filter` 同口径；seed 全程 transient 不落库（对齐 D6 Tier B，规避冻结/来源混淆）；手工优先；主开关默认关逐字节零回归 + P0-2 子开关独立可回退；共享 `wp_formula` 端点对非 D-cycle 底稿零回归；fail-open。**Wave 0 前置核实**：逐锚点读取字段（remark vs conclusion）+ D6-2 aux 归集是否可复用后端函数（否则先抽纯函数不改 HTTP 行为）。先 D6 试点全链再铺其余循环。禁止盲改；子代理遇错自定位根因修主代码重跑，不放宽断言/跳用例。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1"], "depends_on": ["1.1", "1.3"] },
    { "wave": 2, "tasks": ["3.1"], "depends_on": ["1.1"] },
    { "wave": 3, "tasks": ["4.1"], "depends_on": ["1.1", "1.3"] },
    { "wave": 4, "tasks": ["4.2"], "depends_on": ["4.1"] },
    { "wave": 5, "tasks": ["5.1"], "depends_on": ["1.1", "1.3"] },
    { "wave": 6, "tasks": ["6.1", "6.2", "6.3"], "depends_on": ["2.1", "3.1", "4.2", "5.1"] },
    { "wave": 7, "tasks": ["7.1", "7.2"], "depends_on": ["6.1", "6.2", "6.3"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0：安全网 + 前置核实 + 子开关 + 契约脚手架
  - [x] 1.1 characterization 基线锁零回归：锁定当前 `PUT /formulas` auto_calc 走 `write_cell_to_parsed_data`、`GET /formulas` Tier A value 恒 None、D6 render 现状（主开关关逐字节）；新增配置 `settings.D_CYCLE_DETAIL_SEED_ENABLED`（默认 False，P0-2 子开关，被主开关 AND）+ 单测确认默认关不改任何现状。
    - _Requirements: 1.6, 5.1, 5.2, 5.3_
  - [x] 1.2 契约守卫脚手架：在 `test_contract_guards.py` 加 G6（D-cycle 锚点 auto_calc 保存跳过 parsed_data 且不做 DB 写回、返回 evaluated_value）/G7（明细归集复用既有函数不新造读取）/G8（GET value·render seed 同经 get_active_filter）断言骨架（先建、随各波落地转绿）。
    - _Requirements: 7.1, 7.2_
  - [x] 1.3 前置核实（B/C）：逐 Tier A 锚点从前端 composable 核实 render seed 应写入的 `responses_snapshot` 字段（remark vs conclusion），登记进 `d_cycle_anchor_registry.json`（或 seed 映射表）；核实 D6-2 aux 客户/合同维度归集形态——若为可复用后端函数则记录入口，若仅在 HTTP handler（`/import-aux-balance`）内则先抽取纯聚合函数（不改原端点行为）并加纯函数单测。
    - _Requirements: 3.7, 4.3, 4.4_

- [x] 2. Wave 1：P0-1 保存跳过 parsed_data + 返回 evaluated_value（不做 DB 写回）
  - [x] 2.1 `PUT /api/workpapers/{wp_id}/formulas` auto_calc 分支按 `is_known_anchor(base_wp_code, target_cell)` 路由：D-cycle 锚点 + 主开关开 → **跳过 write_cell_to_parsed_data** + 求值（get_active_filter，失败不返回错误/0 值 + eval_warnings）+ 响应返回 `evaluated_value`，**不写 checklist_responses/DB**；否则/主开关关 → 现有 `write_cell_to_parsed_data`（逐字节零回归）；单测 Property 1/2/3/4/13。
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1_

- [x] 3. Wave 2：P0-1 GET /formulas 附 Tier A value
  - [x] 3.1 `_build_extraction_block` 对每条 Tier A binding 求值填 `value`（get_active_filter，有界/批量，单条失败 value=None fail-open，Tier B value 仍 None）；单测 Property 4/5；`FormulaStatusPanel.vue` 面板"当前值"显示真实求值（不再恒 `—`）vitest。
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 4. Wave 3：P0-1 render transient 公式驱动 seed（D6 试点，主机制）
  - [x] 4.1 D6 render 用 `resolve_effective` 的 Tier A 公式求值 **transient seed** TB 核对行锚点进 responses_snapshot（**不落库**，写入 1.3 核实的字段 remark|conclusion；手工优先：锚点持久层非空/disabled 跳过；默认预设求值等价 project_context.tb_amount；fail-open 静默沿用 tb_amount）；集成测试 Property 6/7/10/11/13。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.1_

- [x] 5. Wave 4：P0-1 render seed 铺其余循环
  - [x] 4.2 D1/D2/D3/D5/D7（单标量）+ D4（6001/6051 双标量）render 同法 Tier A 公式 transient seed TB 核对行（不落库 + 写对字段 + 手工优先 + fail-open + 主开关关零回归）；集成测试各循环。DRY：提取 D6 `_seed_tier_a_reconciliation` 为共享助手 `app/services/d_cycle_extraction/tier_a_seed.py::seed_tier_a_reconciliation`（依赖注入 resolve_effective/evaluate_wp_formula_expression，保各调用方模块可 monkeypatch），D6 重构为薄委托 + D1-D7 全复用；D4 双标量由锚点遍历天然覆盖。测试 `test_d1_d2_d3_d5_d7_tier_a_render_seed_integration.py`（参数化 5 单标量）+ `test_d4_tier_a_render_seed_integration.py`（6001/6051 各自独立 seed，含单条 fail-open 不牵连另一条）；D6 原测试无回归（45 passed）。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 6. Wave 5：P0-2 明细表维度归集 render transient 自动 seed（试点 D6-2，子开关门控）
  - [x] 5.1 D6-2 明细表 render 且主开关 ∧ `D_CYCLE_DETAIL_SEED_ENABLED` ∧ 明细行完全空时，调 1.3 核实/抽取的既有归集函数（tb_aux_balance 1402 客户/合同维度）**transient seed** 明细行进 render 返回（`detail_prefill`，不落库）；手工优先（有行不 seed）+ 复用既有函数不新造 + fail-open 空 + 保留前端手动一键取数按钮；集成测试 Property 8/9/11/13。
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.2, 5.3_

- [x] 7. Wave 6：全属性 + 契约守卫 + 全量门
  - [x] 6.1 补齐 Property 1–13 全覆盖 PBT（`tests/d_cycle_extraction/`）。
    - _Requirements: 7.1_
  - [x] 6.2 契约守卫 G6/G7/G8 落地转绿（写路径 checklist_responses / 明细复用不新造 / get_active_filter 同口径）。
    - _Requirements: 7.1, 7.2_
  - [x] 6.3 全量回归门：d_cycle_extraction 全测试绿 + wp_formula 相关不回归 + get_diagnostics 全清 + FormulaStatusPanel Vite transform 200。
    - _Requirements: 5.1, 6.1_

- [x] 8. Wave 7：收尾
  - [x] 7.1 更新 `.kiro/specs/INDEX.md` 登记（Active）+ 评估文档补 P0-1/P0-2 上线评估（`docs/proposals/d-cycle-four-table-extraction-evaluation.md`）。
    - _Requirements: 5.1_
  - [ ]* 7.2 Playwright 端到端（需实例化 D-cycle 项目）：编辑 Tier A 公式保存 → 底稿锚点变化；打开 D6-2 空明细 → 自动 seed；手工覆盖后重开不被回写 round-trip。
    - _Requirements: 1.1, 3.1, 4.1_

## Notes

- **不做**：改 wp_formula schema / 改 D-cycle 数据模型（仍 checklist_responses）/ **新增任何 checklist_responses/DB 写回路径（决策1：保存不写库，render transient seed 是权威）** / 给评估器补 AUX/PREV/序时账真实实现（可编辑公式仍仅 TB/SUM_TB/WP）/ 推倒既有手工一键取数（P0-2 是叠加自动 seed，保留手动）/ 一次覆盖全部 D1–D7 明细（P0-2 先 D6-2 试点，其余增量）。
- **收敛铁律**：P0-1 保存跳过写错库（parsed_data）+ 返回 evaluated_value；render/明细 seed 全程 **transient 不落库**（对齐 D6 Tier B）；P0-2 明细 seed 复用既有归集函数（必要时先抽纯函数不改 HTTP 行为）；`get_active_filter` 唯一四表查询入口；不新造第 3 套读取。
- **存储路由**：`is_known_anchor(wp_code, target_cell)` 判别——D-cycle 锚点保存跳过 parsed_data、普通网格 cell 走 parsed_data（零回归，锚点注册表天然区分）。
- **写对字段**：render seed 写入前端 composable 实际读取的 responses_snapshot 字段（remark vs conclusion，Wave0 逐锚点核实），防 L1 式错列 round-trip 断裂。
- **手工优先精度**：保存返回 evaluated_value 供前端即时显示（不落库）；render transient seed（Tier A 核对行 / P0-2 明细）仅锚点持久层完全空/明细无行时并入；已有值/行/一键取数结果不覆盖；disabled 跳过；仅真人工编辑才持久化。
- **默认等价**：未编辑的默认 Tier A 预设求值 = 现 project_context.tb_amount 口径（默认行为不变，仅编辑/禁用才改变）。
- **灰度 + 独立回退（G）**：P0-1 受主开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认关）；P0-2 额外受子开关 `D_CYCLE_DETAIL_SEED_ENABLED`（默认关，被主开关 AND）→ 可"发 P0-1、压 P0-2"；P0-1 与 P0-2 路径独立；始终 fail-open。
- **共享端点零回归**：PUT /formulas 对非 D-cycle 网格公式行为逐字节不变（Property 2 守卫）。
