# Bug 修复：wp-ai-review-ux-fix（底稿 AI 复核弹窗 UX 缺陷）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§二十三 底稿 AI 对话/复核弹窗 UX 改进）
> 前置资产：`useCellLocate`（wp-locate-foundation spec 已实现，9 类 HTML componentType 全覆盖 + 高亮幂等）+ `TsjReviewFindings.vue` + `SideStandardsTab.vue`
> 工作流：Requirements-First（bugfix 用 bug 条件方法论）

## 一、Bug 现象（用户反馈）

用户使用底稿 AI 复核功能时反馈："复核发现列表不太方便知道是哪个底稿"、"选中文档及位置坐标时不太行"。

## 二、Bug 条件 C(X)（代码实证）

经 readCode 实证（`TsjReviewFindings.vue` + `SideStandardsTab.vue`），存在 3 个 bug 条件：

### C1：复核发现卡片不显示底稿标识
- **现象**：`TsjReviewFindings.vue` 卡片头部只显示 severity + issue_type + sheet/cell（如 `📄 Sheet1 A5`），**不显示底稿名称（wp_name）或编号（wp_code）**
- **后果**：用户看到"Sheet1 A5"不知道是哪个底稿的 Sheet1
- **代码锚点**：`TsjReviewFindings.vue` 模板 `gt-tsj-finding-header` 区有 `wp-code` prop 传入但**模板里不渲染**（只用于 emit 参数）

### C2：定位跳转是 TODO 未接入 useCellLocate
- **现象**：`handleLocateCell` 只 emit `locate-cell` 事件，注释 `// TODO: 依赖 wp-locate-foundation 的 useCellLocate 实现实际跳转`；`SideStandardsTab.vue` 的 `onLocateCell` 也只是再次 emit 给父组件
- **后果**：点"📍 定位"按钮无实际跳转效果
- **代码锚点**：`SideStandardsTab.vue` `onLocateCell` 只 `emit('locate-cell', target)`，未调 `useCellLocate`（该 composable 已由 wp-locate-foundation 实现）

### C3：复核按钮不显示底稿名称
- **现象**：`SideStandardsTab.vue` 复核按钮"🤖 用此提示词复核当前底稿"不显示当前底稿名称
- **后果**：用户不确定复核的是哪个底稿
- **代码锚点**：`SideStandardsTab.vue` 复核按钮文案固定为"当前底稿"

## 三、根因分析

`wp-locate-foundation` spec 已实现 `useCellLocate`（实际跳转能力），但 `TsjReviewFindings`/`SideStandardsTab` 在该 spec 完成**之前**编写，定位跳转留了 TODO 占位（emit 事件但无接线）；底稿标识字段（wp_code/wp_name）虽部分传入但 UI 未渲染。属"基建已就绪但消费方未接线 + UI 字段未展示"。

## 四、修复条件（满足即修复）

- **F1**：复核发现卡片显示底稿编号（wp_code）+ 名称（wp_name）
- **F2**：定位跳转接入 `useCellLocate`，点"📍 定位"真实跳转到对应 sheet/cell
- **F3**：复核按钮显示当前底稿编号/名称
- **F4**（保留扩展点）：跨底稿复核场景 findings 按底稿分组（依赖 doc-level-ai-chat，本 spec 仅留结构不实现）

## 五、保留行为（修复不能破坏）

- TsjReviewFindings 的确认/驳回逻辑不变
- SideStandardsTab 的 cycle 推断 + TSJ 提示词加载 + Markdown 渲染不变
- 既有 vitest（SideStandardsTab.spec.ts 等）不回归
