# 需求文档：S5　取数结果的来源信封

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 最终值持久化「定义版本 / run_id / 输入摘要」，让任何一个数都能回答「谁按哪版公式、用哪些输入算出来的」。
- `note_wp_mapping` 的来源（本 spec 现读确认该表在真库不存在，溯源子源因此恒 partial）。
- 零挂载组件逐个裁决（`formula-governance-coverage-closure` R4 已建挂载守卫，剩下的组件去留归本 spec）。

## 2. 依赖与先后
依赖 `formula-hub-integrity-closure` ADR-FHIC-04（计算版本）与 ADR-FHIC-16（溯源子源隔离）已落地。

## 3. 触发条件

审计留痕要求「可重算」时，或 S3 的 stale 状态机需要输入摘要做判据时。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 的 `calc_version` 只到「是不是当前版本」，没有记录具体定义版本与输入摘要。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1：`components/formula` 下零挂载组件现算为 0（前序 spec 已清零），R3 的真实缺口改为「来源浮层没有挂到报表与附注的最终值上」（design ADR-FPE-06）；推送域已基本具备来源信封。
- 底稿域信封建议放到 S1 之后（design §4 D1）。
