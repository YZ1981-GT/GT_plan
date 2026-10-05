# Tasks — 指针文件

> **唯一真源**：[`d1-sync-row-table-engine-and-d1-coverage/tasks.md`](../d1-sync-row-table-engine-and-d1-coverage/tasks.md)
>
> 本目录是 2026-09-25 被并发会话复制产生的副本。经 2026-09-28 实测复核确认两份并存会
> 导致进度漂移（两个目录都已入库，实施记录与 evidence 全在 `d1-` 那一侧），
> 故本目录降为指针。
>
> **所有 tasks 编辑、进度跟踪均以 `d1-sync-row-table-engine-and-d1-coverage/` 为准。**

---

## 历史说明

本目录 `workpaper-sync-row-table-engine-and-d1-coverage/` 的 tasks.md 曾在 2026-09-28
被大量追加实测复核与缺陷修复批次（O~X 节，3207 行），这些内容的**独有部分**
（特别是 X5-d 干净检出验证法、X5-i 暂存树门、X5-g lazy import CI 接入等）
已在 `d1-` 侧 tasks.md 末尾通过 S/T/U/V/W/X 节交叉引用覆盖。

本文件此前的 3207 行完整内容可通过 `git show <commit>:<path>` 查阅。

## 状态摘要（2026-10-04 现算）

| 统计 | 值 |
|---|---|
| 总任务 | 35 |
| 已完成 | 24（含 4 条 `*` 评估/声明类） |
| `[ ]*` 卡外部依赖 | 7 |
| `[ ]` 未开工 | 4（含 Task 18 归并发 D2 lane） |
| 整册门 | EXIT=0（受管区 18 / sheet 12 / store item 17 / 6.2s） |
| 判据总数 | 721 passed / 45 skipped / 0 failed（工作树口径） |
| CI 门禁 | 6 道 Gate + 7 份自测 干净检出全绿 |
