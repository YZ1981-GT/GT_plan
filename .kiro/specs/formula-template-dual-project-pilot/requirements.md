# 需求文档：S6　公式模板双项目试点

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 双项目真 PG + 登录态 UAT（本 spec 的模板相关验证全在回滚事务里）。
- 模板回滚发版、版本 diff、新增 slot。
- 订阅按钮按 edit 权限（现在任何可见者都能点）。

## 2. 依赖与先后
依赖 S4（durable outbox）—— 模板发版会扇出到全部订阅项目，没有 outbox 不敢在真实项目试点。

## 3. 触发条件

有第二个真实项目愿意做模板订阅试点时。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 真库 `formula_template` 0 行、`formula_publish` 0 行 ⇒ 模板链路从未有真实数据流经过。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1：后端发版已支持新增公式位，缺的是界面、回滚发版与版本对比。
- 建议一并纳入评估报告 P2-4 里没有分派给任何 S spec 的四个小缺口（design §5 D2）。
