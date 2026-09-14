# 审计循环色板单一真源 — Requirements

## 背景

codegraph + grep 实证（2026-06-23）：同一个审计循环字母在 4 个地方各定义一套颜色，且色值互相冲突。以 **D 销售循环**为例：

| 定义处 | D 循环色值 | 用途 |
|--------|-----------|------|
| `views/workpaper-list/WorkpaperWorkbenchView.vue` `CYCLE_COLORS` | `#E8590C`（橙） | 底稿工作台分组卡片 |
| `components/panorama/colorMaps.ts` `CYCLE_COLOR_MAP` | `#1976D2`（蓝） | 联动全景图 |
| `components/workpaper/WorkpaperDependencyGraph.vue` `CYCLE_PALETTE` | `#52b788`（绿） | 底稿依赖图 |
| `components/dashboard/projectGanttUtils.ts` `CYCLE_COLOR_MAP` | `#409EFF`（蓝） | 项目甘特图 |

**用户实感**：同一个"D 销售循环"，工作台是橙、全景图变蓝、依赖图变绿、甘特图又一种蓝。颜色是审计人员建立空间记忆的锚点，颜色不稳定 = 认知负担。

## 目标

建立循环色板单一真源（一份 TS 常量 + 一组 CSS 变量），4 处全部引用它，消除色值冲突。纯收口，无业务逻辑风险。

## 需求

### 需求 1：建立单一真源

#### 验收准则
1. THE 一份 `constants/cyclePalette.ts` SHALL 定义 A~S 全部循环字母 → 颜色的唯一映射，并导出 `cycleColor(code)` 取色函数（未知/空 → 统一兜底灰）。
2. THE `styles/gt-tokens.css` SHALL 定义对应 CSS 变量 `--gt-cycle-A` … `--gt-cycle-S` 与 `--gt-cycle-other`，色值与 TS 常量一致。
3. THE 取色函数 SHALL 大小写不敏感（`'d'` 与 `'D'` 同色），与现有 `projectGanttUtils.cycleColor` 行为一致。

### 需求 2：4 处引用统一真源

#### 验收准则
1. THE `WorkpaperWorkbenchView.vue` 的 `CYCLE_COLORS` SHALL 改为引用 `cyclePalette`。
2. THE `panorama/colorMaps.ts` 的 `CYCLE_COLOR_MAP` SHALL 改为引用 `cyclePalette`（保留 `module`/`other` 等全景图专有键）。
3. THE `WorkpaperDependencyGraph.vue` 的 `CYCLE_PALETTE` SHALL 改为引用 `cyclePalette`。
4. THE `dashboard/projectGanttUtils.ts` 的 `CYCLE_COLOR_MAP` SHALL 改为引用 `cyclePalette`。
5. WHEN 引用统一后 THEN 同一循环字母在 4 处 SHALL 返回完全相同的色值。

### 需求 3：选定权威色值

#### 验收准则
1. THE 权威色板 SHALL 为每个循环选定一个最终色值（建议沿用辨识度最高、对比度达标的一套；可参考 panorama 既有 14 循环色系）。
2. THE 选定色板 SHALL 通过对比度自检（文字/背景对比满足可读性，不强制 WCAG AA 断言）。
3. THE 现有依赖这些颜色的单元测试（如 `ProjectGanttChart.spec.ts`、`PanoramaComponents.spec.ts`）SHALL 更新为引用统一真源后仍全绿。

### 需求 4：防回归守卫

#### 验收准则
1. THE 一个 CI grep 守卫 SHALL 检测新增的"循环字母 → hex 色值"本地映射（`CYCLE_COLOR`/`CYCLE_PALETTE` 等模式的内联 hex），命中即告警，引导改用 `cyclePalette`。

## 非目标
- 不改循环的业务语义/排序。
- 不改 severity/node 等非循环色映射（panorama 的 SEVERITY_COLOR_MAP 保留）。
- 不引入新依赖。
