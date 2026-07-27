# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 3 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`j1-employee-compensation` / `j2-defined-benefit-plan` / `j3-share-based-payment`）
- 前端目录与组件 → `Get-ChildItem -Recurse`（j1 含 core/analysis/inspection、j2 扁平、j3 含 core/__tests__）
- J1 科目 2211、J2 科目 2221 → 既有 J 循环复盘记录 + `useJ1FormData` / `useJ2` 常量
- J1 分配取数（贷方计提 + 对方科目桶映射 5001·4001→生产成本 等）→ `j1AllocationLedgerPull.ts`
- J1 凭证三模视图 + 证据字段（calc/approval/bank）→ 既有 J1-8 凭证检查复盘记录
- J2 CAS9 六要素 + 增减四栏结构 → 既有 J2-1/J2-2 重建复盘记录
- J3 引导弹窗（J3PlanDialog 14 列 / J3VariationDialog 19 列）+ 期权定价引擎 → `j3/core/` + `j3/__tests__/`
- 附注 J1 五、40 / 八、40 → 既有 j1-disclosure-note-linkage 记录

## 未核实项

- **J3 的权益工具科目码**（本文按"4004 其他权益工具/资本公积"描述，未在本轮读取 J3 常量文件确认）
- J2 附注是否有独立章节号还是并入 J1 五、40 的设定受益计划节（本文按"并入"描述，待核）
- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链
- J1 → K8/K9 分配核对的消费端闭环未逐一核实
