# 需求文档：S2　校对契约与附注执行器

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 附注执行器只回写 `auto_calc` 格（现在会覆盖手工格）。
- 校对目录的执行状态（现在只有定义、没有「这条规则跑过没有 / 结果是什么」）。
- XR skip 计入签字判据。
- 表间审核规则改「只提示」。
- 门禁开启阻断后，签字人逐项确认留痕（本 spec D2 把它移出范围：只做五态 + 默认 observe）。
- `ConsistencyBlockingDiffRule` 吞异常（本 spec 现读确认它走 `consistency_replay_engine`、不是本门禁的消费方，未改）。

## 2. 依赖与先后
依赖 `formula-hub-integrity-closure` ADR-FHIC-14（门禁五态 + `gate_decision` 单一判定）已落地。

## 3. 触发条件

决策项 X4（门禁切 enforce）被用户批准时必须同批启动 —— 没有逐项确认留痕，阻断会变成死路。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
- 本 spec 任务 39 范围外登记：`consistency_gate` 的 82 处 `passed=True` 里，缺数 / 异常即放行的那部分已由五态收口，
  但「签字门禁在 enforce 下如何让签字人逐项确认」仍空缺。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1；触类旁通现算：门禁规则里「异常即放行」共 27 处 / 7 个文件，§1 只点名了其中的 `ConsistencyBlockingDiffRule`，设计一并纳入（design ADR-CCN-07）。
- R1、R2、R4、R6 不依赖 X4，可先做；待拍板见 design §4。
