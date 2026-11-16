# 设计：恢复丢失的 /api 前缀修复

## 1. 现状（2026-11-11 现算）
- 快照链：`8eed682ec`（10-31 gt-sync backup，父 `10810c01e`）目标文件缺前缀 0 处；11-01 的
  `227dfb429` / `dceb889c1` / `50736413a`（父 `7fbd522c8`）已回到旧代码，只多了 3 个守卫文件。
- `8eed682ec` 相对父提交、属于本问题的文件 14 个：
  - HEAD 等于 base（10-31 后没人动过）11 个：`PbcCollectionTab.vue`、`h3MortgageReconcile.ts`、
    `h3TransferReconcile.ts`、`useI1/I3/I4/I5/I6DualMode.ts`、`K10TabOtherIncomeCheck.vue`、
    `K10TabReceivableGrant.vue`（及下条守卫）。
  - HEAD 已改动 1 个：`GtH5OilGasAssets.vue` ⇒ 三方合并。
  - HEAD 已删除 1 个：`actions/DocumentRecognizeDialog.vue` ⇒ 不恢复。
  - 新增守卫 2 个 + `__tests__/apiPathPrefixGuard.spec.ts`（取 `50736413a` 版）。
- 依赖：`sync/onlyOfficeHealth.ts` 的 `fetchOnlyOfficeHealthy` HEAD 已有。

## 2. 方法
- 脚本对每个文件 `git merge-file -p --diff3 ours base theirs`（先统一 LF），无冲突写回工作区，有冲突停下人工处理。
- 守卫先在恢复前的工作区跑一次（预期红），恢复后再跑（预期绿）。

## 3. R3 两处补充
- `GtA182RegulatoryCommunication`：工具栏加「导出 Word」，复用 `GtRegulatoryLetter` 的同一端点
  `GET …/export-word/check-incomplete` + 导出，未完成项先确认。
- `GtA16Bundle`：`visibleTabs` 为空且加载结束时显示空态（说明缺少哪几张子底稿、去底稿列表生成）。
