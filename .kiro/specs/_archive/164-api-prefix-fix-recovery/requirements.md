# 需求：恢复丢失的 /api 前缀修复（residual 任务 26 / 27）

来源：`platform-performance-residual-findings-closure` 任务 28 的 2026-11-11 联合浏览器验证。任务 26 / 27
标为完成，但修复只在 10-31 备份提交 `8eed682ec`（父 `10810c01e`）里，从未进入当前分支；HEAD 上 H3 勾稽、
K10 识别、I 循环在线编辑切换、H5、侧栏 PBC 都请求不带 `/api` 的路径，拿到首页 HTML 或 404。

## R1 按文件三方恢复
- base = `10810c01e`，ours = HEAD，theirs = `8eed682ec`。HEAD 仍等于 base 的文件取 theirs；HEAD 已改动的
  文件逐个三方合并，冲突不自动取一边；HEAD 已删除的文件不恢复。
- 不整文件 checkout 旧版，不改与本问题无关的行。

## R2 守卫随修复一起入库
- `src/__tests__/apiPathPrefixGuard.spec.ts`、`k10OcrContract.spec.ts`、`iCycleDualModeHealth.spec.ts`。
- 守卫在恢复前的 HEAD 上必须红、恢复后必须绿（变异证明）。

## R3 补任务 26 漏掉的两处（任务 28 实测发现）
- A18-2 实际渲染 `GtA182RegulatoryCommunication.vue`（componentType `a18-2-regulatory-communication`），
  它没有「检查 / 导出 Word」入口；任务 26 修的是 `GtRegulatoryLetter.vue`。
- A16 bundle 在 wp_index 没有 `A16-1`~`A16-7` 子底稿时正文空白，需给出空态提示。

## R4 验收
- 浏览器（【测试】项目）复走 residual 任务 28 五项，console error 为 0。
- 扫描 HEAD 无不带 `/api` 的字面量请求（死代码除外，逐条登记）。
