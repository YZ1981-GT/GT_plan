# 审计循环色板单一真源 — Design

## 架构

```
   constants/cyclePalette.ts  ◄── 唯一真源（A~S + other）
          │   export CYCLE_PALETTE: Record<string,string>
          │   export function cycleColor(code): string
          │
          ├──────────────┬──────────────┬──────────────┐
          ▼              ▼              ▼              ▼
  WorkbenchView    panorama/        Dependency      dashboard/
  CYCLE_COLORS     colorMaps.ts     Graph.vue       projectGanttUtils
                   (+module/other)  CYCLE_PALETTE   CYCLE_COLOR_MAP

   styles/gt-tokens.css  ──  --gt-cycle-A … --gt-cycle-S / --gt-cycle-other
   （CSS 场景用变量，JS 场景用 TS 常量，两者色值同源手工对齐 + 测试校验）
```

设计原则（ponytail）：纯收口，第 5 步「一个配置搞定」——单一常量文件 + CSS 变量，4 处改 import。

## 权威色值选定

以 `panorama/colorMaps.ts` 现有 14 循环色系为基准（它覆盖最全、色相分布最均匀），微调对比度后定稿。示例（最终以实现为准）：

```ts
export const CYCLE_PALETTE: Record<string, string> = {
  A: '#6750A4', B: '#7B5EA7', C: '#0094B3',
  D: '#1976D2', E: '#13C2C2', F: '#D84315',
  G: '#1565C0', H: '#6A1B9A', I: '#00838F',
  J: '#AD1457', K: '#2E7D32', L: '#EF6C00',
  M: '#5D4037', N: '#455A64', S: '#C2185B',
  other: '#909399',
}
export function cycleColor(code?: string | null): string {
  if (!code) return CYCLE_PALETTE.other
  return CYCLE_PALETTE[String(code).toUpperCase()] ?? CYCLE_PALETTE.other
}
```

CSS 变量在 `gt-tokens.css`：
```css
:root {
  --gt-cycle-A: #6750A4; /* … 与 TS 同源 … */
  --gt-cycle-other: #909399;
}
```

## 改造各引用点

| 文件 | 现状 | 改法 |
|------|------|------|
| `WorkpaperWorkbenchView.vue` | 本地 `CYCLE_COLORS` 对象 | 删对象，`import { cycleColor }`，`color: cycleColor(code)` |
| `panorama/colorMaps.ts` | 本地 `CYCLE_COLOR_MAP` | 循环键从 cyclePalette 展开，保留 `module`/`other` 专有键 |
| `WorkpaperDependencyGraph.vue` | 本地 `CYCLE_PALETTE` + `cycleColor` | 删本地，import 统一 |
| `dashboard/projectGanttUtils.ts` | 本地 `CYCLE_COLOR_MAP` + `cycleColor` | 删本地，re-export 统一 `cycleColor`（保持现有 import 不破坏） |

注意：`projectGanttUtils` 和 `panorama` 的现有测试 import 了各自的 `CYCLE_COLOR_MAP`，为不破坏测试，可让这两个文件 `export const CYCLE_COLOR_MAP = CYCLE_PALETTE`（或含专有键的合并），保持导出名。

## 测试策略

- 更新 `ProjectGanttChart.spec.ts`、`PanoramaComponents.spec.ts`：断言取色来自统一真源，14 循环各有合法 hex，大小写不敏感、兜底 other。
- 新增 `cyclePalette.spec.ts`：A~S 全覆盖、未知→other、大小写不敏感。
- 守卫脚本自测：构造内联 `D: '#xxxxxx'` 片段断言能捕获。

## 守卫脚本

`scripts/check-cycle-palette-single-source.mjs`：扫 `src/**/*.{vue,ts}`，排除 `cyclePalette.ts`，命中形如 `[A-S]:\s*['"]#[0-9a-fA-F]{6}` 且上下文含 `CYCLE`/`cycle` 的内联色 → 告警。

## 风险与缓解
- **风险**：改色后用户对旧色有记忆 → 缓解：以辨识度最优一套为准，一次性统一，发版说明告知。
- **风险**：CSS 变量与 TS 常量漂移 → 缓解：测试中读取两边断言一致（或构建期生成 CSS 自 TS）。本期采用手工对齐 + 一条一致性测试。
