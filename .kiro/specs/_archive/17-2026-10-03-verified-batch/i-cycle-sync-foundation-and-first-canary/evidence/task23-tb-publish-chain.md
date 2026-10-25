# Task 23 — TB 发布链

**日期**：2026-09-27

## I6 发布门实证

| 位置 | 命中 | 内容 |
|---|---|---|
| `useI6Adjudication.ts#L609` | 定义 | `async function publishToTb(): Promise<void>` |
| `useI6Adjudication.ts#L636` | 端点 | `POST /api/workpapers/${wpId}/audit-determination/publish-to-tb` |
| `useI6Adjudication.ts#L791` | 导出 | `publishToTb,` |
| `I6TabAdjudication.vue#L96` | 调用 | `@click="adj.publishToTb()"` |
| `I6TabAdjudication.vue#L351` | 注释 | `wpId 供显式发布门 publishToTb 调 POST` |

## 铁律验证

- ✅ 只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`
- ✅ 二次确认（`useI6Adjudication.ts#L604` 注释明确标注）
- ✅ 禁在 `watch`/`onMounted`/debounce 回调内发布：grep I6 相关 12 个文件无违规
- ✅ 复用平台既有 2 道 CI 守卫（`check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate`）

## I 循环 6/6 全有发布门（GC-9 在 I 反向）

与 H 的 H8/H9 完全无门相反，I 循环 6 条 entry **全有发布门**。
canary I6 直接覆盖发布链，不需外移首例。

## 🔴 I2 例外登记

`useI2Adjudication.ts` 里 `publishToTb` **0 命中**（验证确认）。
I2 的发布门在 `.vue` 自建（`I2TabAdjudication.vue#L384`），不在 composable。
⇒ lane 2 须单独裁 I2 的发布路径，本 canary 不代它结论。
