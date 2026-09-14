# Implementation Plan

## Overview

按 8 波实现两层架构：Tier B（补齐 `_build_adjudication_prefill` 范式，批量自动填充）+ Tier A（简单提取可编辑公式）+ 评估器口径统一 + 公式管理面板修复。原则：收敛到 K/M/N 既有范式（不造第 3 套四表库读取）、`get_active_filter` 同口径、`wp_formula` 复用为锚点绑定（不改 schema）、预设读时收敛、手工优先、灰度默认关零回归、锚点真实键前置发现、逐循环增量可回退。先 D6/D2 试点跑通全链再铺 D1/D3/D4/D5/D7。禁止盲改；子代理遇错自定位根因修主代码重跑，不放宽断言/跳用例。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2"], "depends_on": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "depends_on": ["2.1", "2.2"] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": ["2.1", "2.2"] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": ["3.1", "3.2", "3.3", "4.1", "4.2", "4.3"] },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "depends_on": ["5.1", "5.2"] },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "depends_on": ["6.1", "6.2", "6.3"] },
    { "wave": 7, "tasks": ["8.1", "8.2", "8.3"], "depends_on": ["7.1", "7.2", "7.3"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0：安全网 + 锚点发现 + 脚手架
  - [x] 1.1 新增 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 配置（默认 False）到 settings；characterization 测试锁定当前 D6/D2 render 返回（零回归基线）；确认 `_build_adjudication_prefill`(K9/K1/N5) 范式与 `get_active_filter` 用法。
    - _Requirements: 7.1, 7.3_
  - [x] 1.2 锚点发现：从各 D-cycle composable（`useD6Adjudication`/`useD6Detail`/`useD2Adjudication` 等，先 D6/D2）反查真实 `checklist_responses` item_id，产出 `d_cycle_anchor_registry.json`（wp_code → 已知锚点集）+ `known_anchors()` 校验函数；单测 Property 8（未知锚点拒绝）。
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 1.3 建 `d_cycle_extraction/prefill.py`（`build_d_adjudication_prefill`：get_active_filter + tb_balance 叶子级 SUM + balance/occurrence 模式 + 跳零/无名）+ `presets.py`（`load_presets`/`resolve_effective` 读时收敛）+ 空/最小 `d_cycle_extraction_presets.json`；单测 Property 1/4/5。
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.3, 5.4, 5.5_

- [x] 2. Wave 1：D6 Tier B 试点全链
  - [x] 2.1 `_d6_contract_assets.py` render 接入 `build_d_adjudication_prefill`（1402/balance，开关开→手工优先并入→返回 `adjudication_prefill`）；保留现 tb_amount/aux 手工按钮；集成测试开关开/关零回归 + 手工优先（Property 2/9）。
    - _Requirements: 1.1, 1.5, 1.6, 2.3, 7.1, 7.2_
  - [x] 2.2 D6 专属组件（`useD6Adjudication`/`D6TabAdjudication`）消费 `adjudication_prefill` seed（无持久化行时建行/填未审数，标注自动取数，手工覆盖后不回写）；vitest。
    - _Requirements: 2.1, 2.2_

- [x] 3. Wave 2：评估器口径统一 + Tier A 后端
  - [x] 3.1 `evaluate_wp_formula_expression` 的 `_resolve_tb`/`_resolve_sum_tb` 改用 `get_active_filter`（与 Tier B 同口径）；单测 Property 3/10（同口径 + 幂等）。
    - _Requirements: 4.1, 4.3_
  - [x] 3.2 Tier A 保存端点对 `AUX/PREV/序时账` 等不受支持函数返 422（方案 a），不静默返 0；单测 Property 6。
    - _Requirements: 4.2_
  - [x] 3.3 `GET /api/workpapers/{wp_id}/formulas` 合并 Tier A 预设（读时收敛 source=preset/custom/disabled）+ Tier B 只读溯源条目 + 附 seed 值；单测收敛输出 + Property 7（悬空 422 既有）。
    - _Requirements: 5.2, 5.3, 3.1, 3.2_

- [x] 4. Wave 3：公式管理面板修复 + 分层展示
  - [x] 4.1 修 `FormulaStatusPanel.vue` 端点错配（改真实端点 + 解析 items）+ 按 sheet 分组 + Tier A/Tier B 分层展示（值复用 seed 不重求值）；vitest。
    - _Requirements: 5.1, 5.2, 5.6_
  - [x] 4.2 面板加 Tier A 编辑（PUT 覆盖）/恢复默认（DELETE）/禁用 + 权限门控（`usePermissionMatrix`）；vitest（Property 5/6/7 + 只读禁用）。
    - _Requirements: 5.3, 5.4, 5.5, 5.7_
  - [x] 4.3 D6 Tier A 预设（`TB('1402',…)` 简单总额锚点，对照 Wave0 anchor registry）+ 面板 D6 展示验证。
    - _Requirements: 3.1, 3.4_

- [x] 5. Wave 4：D2 试点（分类行边界）+ 铺 D1/D3
  - [x] 5.1 D2 锚点发现 + Tier B 接入（能从 tb_balance 取的取，分类行无法拆分的不生成→宁缺勿造 R3.4）；与既有 `importFromAuxBalance`/`D2-adj-tb-amount` seed 共存不冲突（手工优先精度）；集成测试。
    - _Requirements: 1.1, 2.3, 3.4, 7.2_
  - [x] 5.2 D1(1121/balance)/D3(2203/balance) 锚点发现 + Tier B 接入 + Tier A 预设 + 集成测试。
    - _Requirements: 1.1, 1.2, 3.1, 7.4_

- [x] 6. Wave 5：铺 D4/D5/D7
  - [x] 6.1 D4(6001/occurrence，收入按序时账/发生额) 锚点发现 + Tier B 接入 + 集成测试。
    - _Requirements: 1.1, 1.2, 7.4_
  - [x] 6.2 D5(1124/balance) 锚点发现 + Tier B 接入 + Tier A 预设 + 集成测试。
    - _Requirements: 1.1, 3.1, 7.4_
  - [x] 6.3 D7(2205/balance) 锚点发现 + Tier B 接入 + Tier A 预设 + 集成测试。
    - _Requirements: 1.1, 3.1, 7.4_

- [x] 7. Wave 6：全属性 + 契约守卫 + 全量门
  - [x] 7.1 补齐 Property 1–12 全覆盖 PBT（`tests/d_cycle_extraction/`）。
    - _Requirements: 8.1, 8.2_
  - [x] 7.2 契约守卫：Tier B 复用 `_build_adjudication_prefill` 范式不新造四表库读取（Property 12）、四表库只读守卫兼容、评估器 active_filter 同口径守卫。
    - _Requirements: 7.3, 4.1_
  - [x] 7.3 全量回归门：D1–D7 render + wp_formula + FormulaStatusPanel 相关测试全绿 + get_diagnostics 全清 + Vite transform 200。
    - _Requirements: 7.1, 7.2_

- [x] 8. Wave 7：收尾
  - [x] 8.1 更新 `.kiro/specs/INDEX.md` 登记 + 灰度默认开启评估文档。
    - _Requirements: 7.1_
  - [x] 8.2 差异矩阵文档：每 D-cycle 提取覆盖的四表库字段 vs 未覆盖（宁缺勿造）清单 + 锚点-来源对照表，供 E/F/G… 循环推广参考。
    - _Requirements: 6.3, 3.4_
  - [x]* 8.3 端到端 flag-ON 实测（**standalone 脚本对真实 DB 实测**替代 Playwright——Playwright 有 SSE 抖动 + 无法安全在共享后端切灰度开关做 UI round-trip；标准做法见 memory「HTTP round-trip / standalone 脚本」）：本进程内置灰度 ON（不触碰运行中 9980），对已实例化 D-cycle 底稿（重药控股安徽 0ec33ac9）实测——① D2/D4/D5 render 无 adjudication_prefill（宁缺勿造）✓ ② Tier B 引擎 `build_d_adjudication_prefill` 对真实 tb_balance 有子科目账户（1122 应收账款 8 行→3 非零叶子，期初/期末真实金额）返回真叶子、对无子科目账户（1402 只 parent）返空（Property 1/4 live）✓ ③ D6 render 因该客户无 1402 子科目故空 seed（数据条件正确，非缺陷；有 1402 子科目时同 1122 seed）✓ ④ `_build_extraction_block`（公式管理面板 Tier A/B 数据源）flag ON 下 D6=[D6-1-tb-amount]/D2=[D2-adj-tb-amount]/D4=[D4-1-adj-tb-6001,D4-1-adj-tb-6051 双标量]/D5=[D5-1-tb-amount]，tierB_count 各 2，enabled=True（Property 5/11 live）✓。临时脚本跑完即删。UI 层可视 round-trip（表格 seed 标注/面板编辑/手工覆盖不回写）留待专用环境（flag 生产开启后）。
    - _Requirements: 5.1, 5.2, 5.3, 2.2_

## Notes

- **不做**：改 wp_formula schema / 改 D-cycle 数据模型（仍 checklist_responses）/ 推倒既有手工一键取数、明细导入导出、审定 TB 核对、附注联动 / report↔note 同步 / 非 D 循环 / 给评估器补 AUX/PREV/序时账真实实现（方案 b，留后续）。
- **收敛铁律**：Tier B 必须复用 `_build_adjudication_prefill` 范式（对齐 K9/K1/N5），不新造第 3 套四表库读取；`get_active_filter` 是唯一四表查询入口。
- **锚点准确性**：每 D-cycle 锚点必须 Wave0 从真实 composable 反查（`d_cycle_anchor_registry.json`），target ∈ known_anchors 否则拒绝，不臆造；无法从四表库映射的字段（审计判断/说明）不生成提取。
- **手工优先精度**：自动预填仅在锚点完全空时并入；一键取数/明细导入结果视为已填不覆盖；用户编辑覆盖后永久优先。
- **口径统一**：Tier A 求值与 Tier B 预填共用 `get_active_filter`，消除面板值 ≠ render 填充值漂移。
- **灰度**：默认关，D6/D2 试点验证后再铺开、再评估默认开启。
