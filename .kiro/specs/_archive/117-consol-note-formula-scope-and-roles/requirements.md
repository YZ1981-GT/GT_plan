# 需求文档：S7　合并附注公式的范围与角色

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- `consol_note` 域只列 `consolidated` 项目（现在列全部项目）。
- 全局写只给 admin（本 spec §10 的默认建议；现在 partner / manager 也能写）。

## 2. 依赖与先后
独立。

## 3. 触发条件

用户对「合并附注全局公式谁能改」拍板后启动（本 spec requirements §4.1 D 列未覆盖该项）。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 范围外明确不改「模板共享范围」与「全局发布审批流程」。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1：全局写有两个入口、两套口径（公式设置中心只给 admin，旧端点 `/api/consol-note-formulas` 给 admin / partner / manager），前端面板另带一份角色名单。
- 待拍板见 design §4（D1 即本文 §3 的触发条件）。
