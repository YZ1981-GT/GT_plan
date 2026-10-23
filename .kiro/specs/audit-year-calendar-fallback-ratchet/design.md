# 前端审计年度「取今年」兜底收口 —— 设计

## 1. 守卫

- 位置：`audit-platform/frontend/src/utils/__tests__/auditYearCalendarFallbackRatchet.spec.ts`，清单 `auditYearCalendarFallbackInventory.json`（同目录，`{ "files": { 相对 src 的路径: 处数 }, "total": N }`）。
- 写法照 `pendingWritesCoverageRatchet.spec.ts`：`node:fs` 遍历 `src`，同一组正则现算，与清单逐文件比对；失败信息列出差异与应改成的清单片段。
- 正则：`/new\s+Date\(\)\s*\.getFullYear\(\)(?!\s*-\s*1)/` 且行匹配 `/year/i`；与 2026-10-23 现算脚本同口径（当时 251 处，2026-10-24 现算 250 处）。
- 自检：内置样例串必须命中 / 不命中；`utils/resolveAuditYear.ts` 自己的 `getFullYear() - 1` 不得命中（正向反例）。
- 豁免表 `LEGIT_CURRENT_YEAR`：文件 → 理由；条目文件仍须命中扫描口径（否则是失效条目）。首批为空。

## 2. 分批收口（后续任务）

逐文件现读用途：要项目审计年度的改用 `resolveEffectiveAuditYear`（数据来源按调用方已有的 store / 路由 / 项目对象），真要今年的进豁免表；每批下调清单、跑相关 vitest、浏览器实测入口年度。
