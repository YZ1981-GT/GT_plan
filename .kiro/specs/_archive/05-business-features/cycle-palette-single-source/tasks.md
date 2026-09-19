# 审计循环色板单一真源 — Tasks

- [x] 1. 创建 `constants/cyclePalette.ts`：A~S + other 唯一映射 + `cycleColor()`（大小写不敏感，兜底 other）
  - 文件：`audit-platform/frontend/src/constants/cyclePalette.ts`
  - 需求 1、3

- [x] 2. 在 `styles/gt-tokens.css` 增加 `--gt-cycle-A`…`--gt-cycle-S` + `--gt-cycle-other`，色值与 TS 同源
  - 文件：`audit-platform/frontend/src/styles/gt-tokens.css`
  - 需求 1

- [x] 3. 单元测试 `cyclePalette.spec.ts`：A~S 全覆盖 / 未知→other / 大小写不敏感 / 合法 hex
  - 文件：`audit-platform/frontend/src/__tests__/cyclePalette.spec.ts`
  - 需求 1、3

- [x] 4. 改造 `WorkpaperWorkbenchView.vue`：删本地 `CYCLE_COLORS`，引用 `cycleColor`
  - 需求 2

- [x] 5. 改造 `panorama/colorMaps.ts`：循环键从 cyclePalette 展开，保留 module/other 专有键，`CYCLE_COLOR_MAP` 导出名保留
  - 需求 2

- [x] 6. 改造 `WorkpaperDependencyGraph.vue`：删本地 `CYCLE_PALETTE`/`cycleColor`，引用统一
  - 需求 2

- [x] 7. 改造 `dashboard/projectGanttUtils.ts`：删本地映射，re-export 统一 `cycleColor`/`CYCLE_COLOR_MAP` 保持导出名
  - 需求 2

- [x] 8. 更新现有测试 `ProjectGanttChart.spec.ts`、`PanoramaComponents.spec.ts` 引用统一真源后全绿
  - 需求 3

- [x] 9. 守卫脚本 `check-cycle-palette-single-source.mjs` + 自测 + 接入 lint
  - 文件：`audit-platform/frontend/scripts/check-cycle-palette-single-source.mjs`、`package.json`
  - 需求 4

- [x] 10. 回归：前端 vitest 全绿 + Playwright 抽测工作台/全景图/依赖图/甘特图同一 D 循环同色
  - 需求 2、3

- [x]* 11. 更新 `docs/平台全局体验与一致性建议.md` §1.1 标记完成
