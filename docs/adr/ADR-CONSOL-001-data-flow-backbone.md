# ADR-CONSOL-001: 合并数据流主干裁定

## 状态
已接受 (2026-05-31)

## 背景

合并模块存在三套并行互不连通的数据模型：
1. `consol_worksheet_engine`（差额表引擎，后序遍历企业树，算法正确）
2. `consol_worksheet_data`（15 张致同底稿，前端 JSON blob 存储）
3. `consol_trial` / `consol_report`（报表数据源，`individual_sum` 无写入路径）

三套模型各算各的、互不对账，导致"组件齐全却从未产出正确合并报表"。

## 决策

**确立差额表引擎（`consol_worksheet_engine`）为计算主干**：

- **计算主干** = `consol_worksheet_engine._calc_node`（后序遍历企业树，叶子取 `audited_amount`，中间节点 = Σ子节点 + 抵销 + 调整，根节点 = 最终合并数）。
- **明细支撑表** = 15 张致同底稿（`consol_worksheet_data`），后续 Phase 将其结果转为调整/抵销分录喂入引擎；Phase 0 仅声明关系，不接线。
- **引擎投影** = `consol_trial` / `consol_report`，是引擎结果的下游投影。Phase 0 通过 B1（汇总 `individual_sum`）+ B2（worksheet↔trial 对账）把投影与主干打通。

**5 大横切能力作为设计输入**（不在 Phase 0 实现，但主干设计为其留出口）：
1. 单体联动 — 靠 `consol_lock` + 企业树
2. 溯源穿透 — 靠 `consolidation_breakdown` provenance
3. 国企↔上市模板转换 — 靠 `template_type` 字段
4. 自定义查询 — 靠 `consol_pivot_service` 查 `ConsolWorksheet`
5. 公式管理 — 后续纳入管理中心

## 后果

- Phase 0 不重写引擎，仅确立主干 + 桥接 + 投影关系
- 后续 Phase 必须把 15 张致同底稿的结果转为分录喂入引擎（而非绕过引擎直接写 trial）
- 报表/附注穿透必须从 worksheet 根节点取数（单一事实源）
- B2 对账作为观测手段，diff ≠ bug（抵销归集维度差异是已知设计性不一致）
