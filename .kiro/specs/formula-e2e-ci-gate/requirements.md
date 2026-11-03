# 需求文档：S8　公式 Playwright 规格接入真实运行的 CI

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 把公式链路的 Playwright 规格接到**会实际运行**的 CI job（现在规格存在但 CI 不跑）。
- 与 `governance-checks.yml` 的既有门禁合并口径：判据必须「没有违规时真的会绿」（memory 铁律㉗①）。

## 2. 依赖与先后
依赖 CI 环境能跑浏览器（当前 CI 无此能力）。

## 3. 触发条件

本 spec 的「浏览器实测」项长期保持 `[ ]`（依赖决策项 X1）⇒ 一旦 X1 执行、开发服跑上新代码，就该把这条验收自动化。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 发布验收清单的「浏览器实测」是唯一允许按外部环境保持未完成的项（需求 17.4），S8 的目的就是让它不再依赖人工。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。§2「当前 CI 无此能力」经现读不准确：GitHub 托管 runner 能跑浏览器，缺的是起库、后端、前端与种子数据的独立 job；另外当前工作分支 `spec/…` 推送时不触发任何 CI（design §1）。
- 待拍板见 design §3。
