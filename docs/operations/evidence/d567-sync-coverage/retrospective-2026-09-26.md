# d567-sync-coverage-via-row-table-engine 复盘（2026-09-26）

**角色轮转视角**：项目经理（进度诚实）+ 质控（判据非永绿）+ 审计助理（现场执行）

## 一句话结论

本 spec 在当前上游状态下**可交付边界 = Task 0（前置门）+ Task 1（聚合键缺陷）**，两项已完成并通过验收；
Task 2~22（三循环 20 个受管区声明层）**全部阻塞于上游 `d1` 框架层未入 HEAD**，本轮如实停在边界、不铺量、不假绿。

## PDCA

### Plan
按 tasks.md 波次从 Task 0 硬前置门开工，先核查上游是否已交付框架层，再决定推进面。

### Do
1. **Task 0**：`git show HEAD:` + 工作树 `file_search` + 全仓 grep 三路交叉判定，确认三个框架文件
   （`row_table_engine.py`/`adjudication_sheet_spec.py`/`row_table_registry.py`）客观不存在，`RowTableSheetSpec`/
   `AdjudicationSheetSpec`/`aging_layout` 零生产代码，D5 provider 仍老写法。⇒ 前置 A/B/C/D 未满足、E 全 False。
2. **Task 1**（唯一不受前置阻塞）：修 `D6/D7TabIndex.vue` 四处无写入方聚合键，改判真实写入方分区键；
   完成度判定提取纯函数 `isD6/D7SheetComplete` 供判据直接驱动。

### Check（验收）
- 红判据 `d67TabIndexAggregateKeyFix.spec.ts` **23 用例全绿**（14 行为 + 9 静态零残留守卫 + 反向自检防空转）。
- **变异实测打红**：临时把生产 `isD6SheetComplete` 的 D6-6 case 改回 `D6-6-rows` ⇒ 对应用例 + Property 11 守卫红
  （`expected true to be false`），还原后复绿 ⇒ 判据非永绿装饰。
- **零回归**：既有 `d6/d7SheetLabels.spec.ts` 连同新判据共 20（→23）用例全绿；`vue-tsc` 对 5 改动文件零报错；
  5 文件 0 diagnostics。
- **需求 5.4 零残留**：前端生产源码 `hasJsonRows(...'D6-6-rows'|'D6-8-rows'|'D7-4-rows'|'D7-7-rows')` 调用零命中
  （静态守卫自动化，非一次性 grep）。

### Act（下一轮解冻条件）
上游 `d1-sync-row-table-engine-and-d1-coverage` 框架层（引擎 + `aging_layout` 参数化 + `AdjudicationSheetSpec`
+ `merge._protection` 格级判定）入 HEAD 后，Task 2~22 方可推进；三家 `adapter_registered` 解除后真栈判据方可实测。

## 诚实暴露的问题（不粉饰）

1. **本 spec 三件套完备但依赖链未就绪就已创建**：Task 0 的存在正是为拦这种情况，机制生效。
   ⇒ 教训固化：Design-First spec 的 Task 0 必须在开工首件事执行，不能因「三件套齐了」就假设可全量实施。
2. **spec 对「Task 1 独立于前置」的判断经实测成立** —— 需求 5.5 声明它「不受任何前置阻塞」，
   实证四个聚合键的真实写入方（`useD6Inspection`/`useD6EclCalculation`/`useD7Analysis`/`useD7VoucherCheck`）
   均已在 HEAD，纯前端 bugfix 无需引擎。这条判断准确。
3. **提取纯函数是对 spec 的合理增强**：原缺陷判定内联在 `<script setup>` 局部函数里，难以单测且无法「判据直接驱动生产逻辑」。
   提取为 `d6/d7SheetLabels.ts` 导出后，判据零镜像键名 —— 直接消除了 spec 反复警告的「D1 那类测试恒绿而生产恒死」风险。

## 触类旁通

- 四个聚合键缺陷与 D1 的「四处拼锚点三处拼错、测试镜像同款错误」**同型**。本次修复用「提取纯函数 + 判据 import 生产函数」
  的模式根治，比「测试里复刻一份正确键映射」更强 —— 后者仍可能与生产各自漂移。
- D3 spec 已登记「D6/D7 聚合键缺陷建议随 D5/D6/D7 spec 一并修」，本次即闭环该登记项。
- E1 spec 复盘查明其 `E1TabDirectory.vue` 38 键零写入缺失（与 D6/D7 相反），故 E1 不需要同类修复 —— 本次修复范围正确限于 D6/D7。

## 预存无关问题（登记不处理）

`b23Property7And8.pbt.spec.ts` 用 `fc.stringOf`，fast-check v3 已移除该 API，该套件当前必失败。
grep 实证不引用任何本次改动文件 ⇒ 与 d567 无关，属既有 fast-check 版本债，另行处理。
