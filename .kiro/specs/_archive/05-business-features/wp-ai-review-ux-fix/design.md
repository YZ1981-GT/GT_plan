# 设计文档：wp-ai-review-ux-fix（底稿 AI 复核弹窗 UX 缺陷修复）

> Bug 条件：#[[file:.kiro/specs/wp-ai-review-ux-fix/bugfix.md]]
> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]] §二十三
> 工作流：Requirements-First（bugfix）

## 一、概述

修复底稿 AI 复核弹窗 3 个 UX 缺陷：C1 卡片不显示底稿编号、C2 定位跳转 TODO 未接 useCellLocate、C3 复核按钮无底稿名。修复复用已就绪的 `useCellLocate`（wp-locate-foundation），属"接线 + UI 字段展示"，改动小、风险低、ROI 高。

## 二、修复方案（最小改动 + 不破坏保留行为）

### 修复 C1：卡片显示底稿编号

`TsjReviewFindings.vue` 卡片头部追加底稿编号 tag：

```vue
<div class="gt-tsj-finding-header">
  <el-tag v-if="wpCode" size="small" type="primary" effect="plain">📋 {{ wpCode }}</el-tag>
  <el-tag :type="severityTagType(item.severity)" ...>{{ severityLabel(item.severity) }}</el-tag>
  ...
</div>
```

`TsjFinding` interface 扩展可选 `wp_code?` / `wp_name?`（后端 `tsj_structured_output_service` 返回时带上，从 WorkingPaper 查）。

### 修复 C2：定位跳转接入 useCellLocate

`SideStandardsTab.vue` 的 `onLocateCell` 改真实跳转（**已 readCode 核实真实签名**）：

```typescript
import { useCellLocate } from '@/composables/useCellLocate'
const { locateCell } = useCellLocate()

function onLocateCell(target: { wpCode: string; sheet: string; cellRange: string }) {
  // useCellLocate 真实签名是 snake_case + 需 component_type（对齐后端 LocateTarget）
  locateCell({
    wp_code: target.wpCode,
    sheet_name: target.sheet,
    cell_ref: target.cellRange,
    component_type: ???,   // 需从当前底稿的 componentType 取（c-note-table/e-control-test 等）
  })
}
```

> ⚠️ **代码实证**：`useCellLocate.ts` 导出 `locateCell(target: LocateTarget): boolean`，`LocateTarget` 字段是 **snake_case**：`wp_code` / `wp_id?` / `sheet_name` / `cell_ref` / `component_type`（不是 design 初稿的 wpCode/sheetName/cellRef）。`component_type` 必传（决定定位策略：el-table / GtIndexChip / fallback / univer 委托）→ TsjReviewFindings/SideStandardsTab 需从当前底稿上下文拿到 componentType 传入。这是 C2 接线的关键参数，emit 的 target 结构需相应扩展带上 componentType。

### 修复 C3：复核按钮显示底稿名

```vue
<el-button ...>🤖 复核 {{ wpCode || '当前底稿' }}</el-button>
```

### F4 扩展点（仅留结构，依赖 doc-level-ai-chat 不实现）

findings 按底稿分组的渲染结构预留（当前单底稿不分组），跨底稿场景待 doc-level-ai-chat 落地后启用。

## 三、后端配合

`tsj_structured_output_service.py` 的 `TsjReviewItem` 补 `wp_code` / `wp_name`（可选），`wp_ai.py` 的 tsj-review 端点从 `wpId` 查 `WorkingPaper.wp_code + name` 注入返回。

## 四、验证策略

- vitest：TsjReviewFindings 渲染底稿编号 tag（C1）+ SideStandardsTab 复核按钮含底稿名（C3）+ onLocateCell 调 useCellLocate（C2，mock）
- 既有测试零回归（确认/驳回逻辑 + cycle 推断 + Markdown 渲染）
- Playwright（待环境）：点定位真实跳转

## 五、正确性属性

- **G1 标识完整**：有 wp_code 时复核发现卡片必显示底稿编号
- **G2 定位接线**：点定位调用 useCellLocate（非仅 emit）
- **G3 零回归**：确认/驳回 + cycle 推断 + Markdown 渲染行为不变
