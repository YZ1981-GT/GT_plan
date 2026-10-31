# 需求文档：S3　写入方归属与过期状态机

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- `section` + `field` 的唯一写方矩阵（现在同一格可能有多个写入方，互相覆盖）。
- stale 状态机：`stale_source` 必写、值不变也要清 stale。
- 试算平衡表手工值读回。
- `useEditorSave.ts` 与其余 14 处 `validateStatus` 写请求（按状态码判成功，本 spec 只改了公式管理的 3 处）。

## 2. 依赖与先后
依赖附注权威源拍板（ADR-DPA-001「留前端」与「经公式管理自动推」的冲突，见 memory 全链打通阶段三待拍板②）。

## 3. 触发条件

附注权威源拍板后启动；或 stale 误报 / 漏报再次造成真实项目数据问题时。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 只收口了报表域的过期判据（ADR-FHIC-04 计算版本 + 写入出口同事务标过期），附注与底稿域未动。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。§1 第 2~4 条不依赖附注权威源拍板，可先做；第 1 条拆成「写入方登记表冻结」（先做）与「拍板后强制唯一写方」两段（design §0）。
- 真库 227 行过期标记全部没有来源；附注置过期的写入点共 14 处，其中 10 处只置 `is_stale`（design §1 第 1 行）。本 spec 的过期状态机只管附注：合并附注与底稿预填没有来源列，不在范围（design §4 D4）。宽放行写请求的精确清单实施时用 TypeScript 语法树现算。
