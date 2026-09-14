# 待办（J 循环）

## 已知未做

- **J1 分配检查的 counterpart 归集完善**：`tb_ledger.counterpart_account` 填充率低时按对方科目归集会漏，
  `unattributedAmount` 只提示不分摊；改善需更可靠的对方科目还原
- **J1 → K8/K9 分配核对闭环**：J1-7 分配到销售/管理费用的金额落跨表键 `J1-7-total-*`，
  K8/K9 侧的消费与差异告警是否接全待核
- **J2 精算师专家利用（S12/S12A）联动**：J2-4 计提检查有"利用专家的工作"表 + `GtIndexChip`（S12/S12A），
  与 S 循环专家底稿的实际数据联动待核
- **J3 期权定价引擎的多模型支持**：`useJ3OptionPricingEngine` 有 B-S 模型 + PBT，
  二叉树/蒙特卡洛等复杂模型是否需要视客户
- **J1/J2/J3 附注结构化推送**：J1 已有 `j1NoteSectionMap` + `buildJ1SyncPayload`（五、40/八、40，
  含 soe 三表名重复的 owner 归属处理）；J2/J3 的结构化推送覆盖度待核
- **J1 目录 / 附注 双向跳转**：J1 已建 `j1NoteSectionMap`（五、40/八、40）、正反向跳转 + 覆盖率守卫登记；
  J2（并入 J1 五、40 的设定受益计划节）与 J3 是否需独立跳转入口待定

## 已归档 spec

- J1 相关 spec（如 review-prompt-sheet-level-split、j1-disclosure-note-linkage 等）已完成并归档，
  见 `.kiro/specs/_archive/`
