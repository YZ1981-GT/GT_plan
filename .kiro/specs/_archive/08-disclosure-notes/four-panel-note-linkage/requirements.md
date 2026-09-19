# Requirements Document

## Introduction

四栏视图（Four-Panel View）侧边栏已有项目列表和附注章节列表的 UI 渲染，但点击后不产生实际导航效果。本需求使四栏侧边栏的项目切换和附注章节点击与主编辑区真正联动：点击项目切换当前项目上下文（路由跳转），点击附注章节导航主附注编辑器到对应章节。

## Glossary

- **Four_Panel_Catalog**：四栏视图左侧功能目录组件（`FourColumnCatalog.vue`），包含上方项目列表和下方模块 Tab（报表/附注/底稿/试算表）
- **DefaultLayout**：默认布局组件（`DefaultLayout.vue`），接收 Four_Panel_Catalog 的事件并协调路由导航
- **DisclosureEditor**：附注编辑器主视图（`DisclosureEditor.vue`），管理附注章节树和编辑区
- **Project_Context**：当前项目上下文，由路由参数 `projectId` 和 `year` 决定，全局通过 `projectStore` 同步
- **Note_Section**：附注章节，由 `note_section` 字段标识（如"一、1"、"八、3"）

## Requirements

### Requirement 1: 四栏项目列表点击切换当前项目

**User Story:** 作为审计人员，我想在四栏视图的项目列表中点击某个项目后直接切换到该项目的工作区，这样我不需要返回项目列表页面即可快速在多项目间切换。

#### Acceptance Criteria

1. WHEN 用户在 Four_Panel_Catalog 的项目列表中点击一个非当前项目, THE DefaultLayout SHALL 执行路由导航到该项目的默认工作页面（`/projects/{projectId}/disclosure-notes?year={year}`，与当前活跃 Tab 对应的子路由）
2. WHEN 路由导航完成后, THE Project_Context SHALL 更新为目标项目的 projectId 和 year（通过 `projectStore.syncFromRoute` 自动触发）
3. WHEN 项目切换路由导航完成后, THE Four_Panel_Catalog SHALL 重新加载目标项目的附注章节、底稿、试算表等数据（由 `watch(project.id)` 自动触发）
4. WHEN 用户点击的是当前已选中的项目, THE DefaultLayout SHALL 不执行任何导航操作（避免重复加载）
5. IF 目标项目的数据加载失败（如项目已删除或无权限）, THEN THE DefaultLayout SHALL 显示错误提示并保持在当前项目上下文

### Requirement 2: 四栏附注目录点击导航编辑器到对应章节

**User Story:** 作为审计人员，我想在四栏视图的附注 Tab 中点击某个章节后，主编辑区的附注编辑器跳转到该章节内容，这样我可以通过侧边栏快速定位附注章节而不需要在编辑器内逐个查找。

#### Acceptance Criteria

1. WHILE 四栏视图附注 Tab 处于激活状态且用户当前在附注编辑器页面, WHEN 用户点击某个附注章节条目, THE DisclosureEditor SHALL 导航到该章节（等同于在编辑器内置树中点击该章节节点的效果）
2. WHILE 四栏视图附注 Tab 处于激活状态且用户当前不在附注编辑器页面, WHEN 用户点击某个附注章节条目, THE DefaultLayout SHALL 先路由导航到附注编辑器页面，再定位到目标章节
3. WHEN 附注章节导航完成后, THE DisclosureEditor SHALL 高亮显示目标章节并加载其详细内容（表格数据、富文本等）
4. WHEN 用户点击的章节与当前正在编辑的章节相同, THE DisclosureEditor SHALL 不执行重新加载（避免丢失未保存的编辑内容）
5. IF 目标章节数据加载失败, THEN THE DisclosureEditor SHALL 显示错误提示但不影响其他已加载章节的显示

### Requirement 3: 四栏视图状态与主路由的双向同步

**User Story:** 作为审计人员，我想在四栏视图中看到当前正在编辑的章节被高亮标记，并且通过编辑器内的树导航切换章节时四栏目录也同步更新高亮，这样视觉状态始终一致。

#### Acceptance Criteria

1. WHEN 用户通过 DisclosureEditor 内置树切换到新章节, THE Four_Panel_Catalog SHALL 同步更新 `selectedKey` 高亮到对应章节条目
2. WHEN 用户通过路由参数（如 URL 中的 query `section`）直接进入某个附注章节, THE Four_Panel_Catalog SHALL 在初始化后自动高亮该章节条目
3. WHILE 用户在非附注页面操作, WHEN 通过四栏切换到附注 Tab, THE Four_Panel_Catalog SHALL 不自动选中任何章节（等待用户主动点击）
4. WHEN 项目切换完成后, THE Four_Panel_Catalog SHALL 清除之前项目的选中状态并重置为无选中

### Requirement 4: 导航过程中的用户体验保障

**User Story:** 作为审计人员，我想在四栏导航切换时获得流畅的视觉反馈，不会因为网络延迟或数据加载而感到困惑。

#### Acceptance Criteria

1. WHEN 用户点击四栏项目列表中的项目触发导航, THE Four_Panel_Catalog SHALL 立即将目标项目标记为 `loading` 状态（视觉反馈），直到路由导航和数据加载完成
2. WHEN 用户点击附注章节触发导航, THE Four_Panel_Catalog SHALL 立即高亮目标章节（乐观更新），若后续加载失败则回退高亮
3. THE Four_Panel_Catalog SHALL 对连续快速点击进行 300ms 防抖处理，仅执行最后一次点击的导航操作
4. WHILE 项目切换路由导航进行中, THE Four_Panel_Catalog SHALL 禁用项目列表的点击交互（防止重复触发）
