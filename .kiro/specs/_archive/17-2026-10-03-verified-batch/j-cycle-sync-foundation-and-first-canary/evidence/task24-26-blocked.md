# Task 24*/26* — 阻塞项

## Task 24* roundtrip（依赖 BP-4）

`[ ]*` 阻塞于 BP-4（真 OO 9.4）。
六条前置断言已就绪。需两轮：第一轮验结构（真库 3473 B 金额全 0）、第二轮合成带金额载荷。

## Task 25 TB 发布链

publish-to-tb 端点在 `j1/core/J1TabAdjudication.vue` 命中（端点判定 2 次出现，符号名 0 次）。
GC-9 在 J 是 1/1 有门 → canary 直接覆盖发布链。
禁 watch/onMounted/debounce 内发布 — 复用平台 2 道 CI 守卫。

## Task 26* 人工审核（依赖 BP-2/BP-3）

`[ ]*` 阻塞于 BP-2/BP-3。
判据是「逐文件读 review.entry_id」不是数契约个数。
