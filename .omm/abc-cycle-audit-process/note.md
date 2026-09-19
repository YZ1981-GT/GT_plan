# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 为什么 A/B/C 合并为一组

用户指定 A/B/C 最后一组产出：三者都是**审计过程类**（非科目审定），结构与 D~N 差异大且互相交织
（B 计划 → C 控制 → 实质性 → A 收尾报告是一条审计时间线）。合并描述能体现风险导向审计主链。

## 本 perspective 的事实来源

- A/B/C 的 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py` 的 `RENDERER_DISPATCH`
  （A: a1-dashboard/a2-adjustment-console/a3-consolidation-console/a5-1/a3-8/a8-1/a9-1/a9-2/a10-1/a11-1/a12-1/
  a17-1/a17-2-1/a17-3/a17-3-1/a17-4/a17-6/a17-7/a18-1/a18-2/a27-1/a1-12/a1-15/a1-17；
  B: b1-risk-assessment/b1-3/b1-4/b1-5/b2-12/b19-bundle/b50-risk-assessment/b60-strategy/b22a·b22b·b22c/b23；
  C: c1-entity-level-control/c-control-test/c22-itgc-bundle/c23/c24/c25/c26）
- 风险导向链 / grid shadow / working_papers 表名 / b50_risk_reader / B19 真源 / A13 消费者 / B22/B23/B60 重建
  → A/B/C 循环大量既有复盘记录（memory）

## 未核实项

- **A/B/C 底稿数量庞大**，本文只列 render 策略注册的 componentType，未逐一 `list_directory` 每个前端目录
  （B22A/B22B/B22C/B23/B50/B60/B1/B19 结构在各自 spec 复盘中已详，A/C 的程序表类走通用 GtAProgramConsole）
- 各 A17/A18/A9 等专属文书组件的 sheet ↔ Tab 映射未逐一读
- B15 重要性 redirect 到 Materiality 模块（不在 workpaper 渲染体系内，本文未展开）
- 走 `a-program-console` 的底稿（各 xxxA 程序表）未逐一列，它们共用 GtAProgramConsole + 程序模板
- 本组是 11 个循环 perspective 的收尾；未来若补 A/B/C 更细的子元素（如 A17 收尾族、C 控制测试族），
  可在本 perspective 下加嵌套元素目录
