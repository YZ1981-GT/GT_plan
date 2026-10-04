# Task 22* — roundtrip 实证（依赖 BP-4）

**状态**：`[ ]*` 阻塞于 BP-4（真 OnlyOffice 9.4 required scenario set）

## 阻塞说明

`evidence.sync_test_run_id` 须来自真 OO 栈，不得用 mock 充数。
当前环境无 OO 9.4 真栈可用。

## 六条前置断言（已就绪，待 BP-4 解锁后执行）

1. ✅ 真库缺身份行数现算 == 0（Task 19 backfill 后已确认）
2. ⏳ roundtrip 期间冻结 `useAdjustmentCentralSync`（`i6/core/I6TabAdjustment.vue` 3 处）
3. ⏳ `derived_total_keys` 3 个排除在业务比对之外
4. ⏳ 不改 `I6-2-detail-rows` 键名；完成后回归 H1 pilot golden digest 不变
5. ⏳ 断言未接 `useI6FormData`，且宿主/Tab 侧确实引用了新载体
6. ⏳ R20「各月比例」是 footer 不是业务行 → 不纳入行比对

## 代码已改但未实测

契约已就绪、notice 已挂载、backfill 已完成。缺的只是 OO 真栈的 roundtrip 场景集。
