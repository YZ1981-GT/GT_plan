# Implementation Plan: B60 Dedicated Component

## Overview

将 B60 系列底稿从 `word-template` componentType 迁移为专用 HTML 组件，参照 A17 Bundle 架构模式。后端提供 render 策略 + 章节定义 API + 数据拉取 API；前端实现 GtB60Bundle（el-tabs + 适用性矩阵）+ GtB60ChapterEditor（左导航 + 右编辑区）+ 两个 composable（useB60FormData / useB60Applicability）；注册四件套（wp_code_overrides + htmlRendererRegistry + RENDERER_DISPATCH）；全链路 PBT + Playwright E2E 验证。

## Tasks

- [x] 1. 后端基础设施（Render 策略 + API 端点 + JSON 数据）
  - [x] 1.1 创建 b60_chapter_definitions.json 静态章节定义文件
    - 在 `backend/app/data/b60_chapter_definitions.json` 创建 JSON 数组
    - 包含至少 9 个一级章节（总体审计策略概述、重大关注事项与风险领域、审计方法与应对措施、审计范围、时间安排与关键节点、审计资源分配、重要性水平确定、审计风险概述、其他需关注事项）
    - 每项含 chapter_id（B60-CH-{序号}）、title、level(1/2/3)、required(bool)、hint、data_source
    - _Requirements: 4.2, 10.1, 10.2_

  - [x] 1.2 创建 _b60_overall_strategy.py render 策略
    - 在 `backend/app/routers/wp_render_strategies/_b60_overall_strategy.py` 创建 `render` 异步函数
    - SQL 查询 `SELECT item_id, conclusion, remark FROM checklist_responses WHERE wp_id = :wp_id AND (item_id LIKE 'B60-CH-%' OR item_id = 'B60-applicability')`
    - 返回 html_data dict 含 chapter_definitions、responses_snapshot、project_context
    - 异常时记录 warning 日志并返回空 responses_snapshot
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 1.3 创建 b60_chapters.py 章节定义 API 路由
    - 在 `backend/app/routers/b60_chapters.py` 创建 `GET /api/b60/chapter-definitions` 端点
    - 从静态 JSON 文件加载并返回章节定义列表
    - 接受可选 query 参数 `project_id`（当前版本不做差异化处理）
    - 响应为 JSON 数组，HTTP 200
    - _Requirements: 10.1, 10.3, 10.4_

  - [x] 1.4 创建 b60_data_pull.py 数据拉取 API 路由
    - 在 `backend/app/routers/b60_data_pull.py` 创建 `POST /api/b60/chapters/{chapter_id}/pull` 端点
    - 接收 request body `{ project_id, wp_id }`
    - 从关联底稿提取数据返回 `{ content: str, source_label: str }`
    - 404/空数据时返回空 content
    - _Requirements: 8.2_

  - [x] 1.5 注册后端路由与 RENDERER_DISPATCH
    - 在 `__init__.py` import _b60_overall_strategy 并注册到 RENDERER_DISPATCH dict（键 `b60-strategy`）
    - 在 `dedicated_component_routers.py` allowlist 加入 b60_chapters 和 b60_data_pull
    - 在 workpaper.py 注册路由
    - _Requirements: 1.3, 9.1_

- [x] 2. 前端 composables（useB60FormData + useB60Applicability）
  - [x] 2.1 实现 useB60FormData.ts 章节内容持久化 composable
    - 创建 `frontend/src/components/workpaper/b60/composables/useB60FormData.ts`
    - 实现 chapterContents（Map<string, string>）、saveStatus ref、updateChapter、flushPendingSaves
    - 800ms 防抖调用 `PUT /api/workpapers/{wpId}/checklist-responses`
    - payload: `{ items: [{ item_id: chapter_id, conclusion: null, remark: 章节内容文本 }] }`
    - 成功后调用 scheduleAutoSnapshot()
    - 连续失败 3 次停止重试 + ElMessage.warning
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 11.2_

  - [x] 2.2 实现 useB60Applicability.ts 适用性矩阵 composable
    - 创建 `frontend/src/components/workpaper/b60/composables/useB60Applicability.ts`
    - 实现 applicabilityMap（Record<string, boolean>）、toggleApplicability、isApplicable
    - item_id = `B60-applicability`，remark = JSON 字符串
    - 800ms 防抖持久化到 checklist_responses
    - 缺失键默认为 true
    - _Requirements: 3.2, 3.3, 3.4_

- [x] 3. 前端组件（GtB60Bundle + GtB60ChapterEditor）
  - [x] 3.1 实现 GtB60Bundle.vue 顶层聚合组件
    - 创建 `frontend/src/components/workpaper/b60/GtB60Bundle.vue`
    - Props: wpId, projectId, sheetName, readonly, year
    - 通过 `GET /api/workpapers/{wpId}/wp-index` 构建 wpIdMap（wp_code → wp_id，筛选前缀 `B60-` 或精确匹配 `B60A`~`B60D`，映射值使用 item.wp_id 非 item.id）
    - 渲染适用性矩阵面板（8 个子底稿勾选框）
    - 管理 10 个固定顺序 Tab（B60 恒可见，其余由 wpIdMap + 适用性联合推导可见性）
    - Tab kind 分发：chapter-editor / navigate-sheet / docx-inline
    - 提供 el-segmented 模式切换（章节编辑 / 在线编辑）
    - 空状态占位"B60 系列子底稿尚未生成"
    - ErrorBoundary 隔离子底稿渲染失败
    - _Requirements: 1.1, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 12.1, 12.4_

  - [x] 3.2 实现 GtB60ChapterEditor.vue 章节编辑器组件
    - 创建 `frontend/src/components/workpaper/b60/GtB60ChapterEditor.vue`
    - Props: wpId, projectId, year, chapterDefinitions, responsesSnapshot, projectContext
    - 左右双栏布局（左 240px 导航 + 右 flex:1 编辑区）
    - 左侧导航：章节标题列表按 level 缩进 + 完成状态圆点指示器（绿/橙/灰）
    - 右侧编辑区：每章节独立 el-card + el-input type="textarea" :autosize="{ minRows: 5, maxRows: 20 }"
    - 点击导航 smooth 滚动 + 1 秒高亮
    - hint 非空时渲染编制提示（琥珀色左边线 details 折叠块）
    - 保存状态指示器（saved/saving/unsaved）
    - 章节按 chapter_id 字典序排列
    - required=true 显示红色必填标记
    - defineExpose({ flushPendingSaves })
    - _Requirements: 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.3_

  - [x] 3.3 实现章节 AI 辅助功能
    - 每章节 el-card 标题行右侧「🤖 AI 辅助」按钮（size=small, type=primary, plain）
    - 调用 `POST /api/workpapers/{wp_id}/ai/generate-text`
    - request body: `{ section: chapter_id, prompt: chapter.hint, context: { client_name, audit_year, business_category, chapter_title } }`
    - context 值全部转为 string 类型
    - 成功弹出确认对话框（el-dialog）预览，确认后追加到 textarea + 触发防抖保存
    - 失败时 ElMessage.warning("AI 生成失败，请稍后重试")
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 3.4 实现章节数据拉取功能
    - data_source 非空时渲染「📥 从 {data_source.label} 带入」按钮（size=small）
    - 调用 `POST /api/b60/chapters/{chapter_id}/pull`
    - 追加语义：已有内容非空时 `existingContent + '\n\n' + content`；空时直接设为 content
    - 成功后显示数据来源标签（GtIndexChip value="wp:{source_wp_code}"）
    - 404/空时 ElMessage.info("源底稿暂无数据")
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 4. 注册与接线（overrides + registry + DISPATCH）
  - [x] 4.1 更新 wp_code_overrides.json
    - 将 B60、B60-1、B60-2-1、B60-2-2、B60-2-3、B60-3、B60A、B60B、B60C、B60D 全部映射为 `b60-strategy`
    - _Requirements: 1.2_

  - [x] 4.2 更新 htmlRendererRegistry.ts
    - 注册 `b60-strategy` componentType 条目
    - 包含 defineAsyncComponent 懒加载引用指向 GtB60Bundle
    - 包含 contextProps: 'standard' 声明
    - _Requirements: 1.1_

  - [x] 4.3 接线验证（章节定义 API 降级 + OnlyOffice 健康检查）
    - GtB60ChapterEditor 加载章节定义时 10 秒超时，失败使用前端内置默认数组 + warning 提示
    - GtB60Bundle 模式切换前调 flushPendingSaves
    - 切回章节编辑模式时重新加载最新数据
    - OnlyOffice 健康检查 unhealthy 时禁用"在线编辑"选项 + el-tooltip
    - _Requirements: 4.1, 4.3, 12.2, 12.3, 12.4_

- [x] 5. Checkpoint - 确保基础功能闭环
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. AI/Pull 集成与版本链复核
  - [x] 6.1 接入版本链与复核对话
    - GtB60Bundle onMounted 调用 useWorkpaperVersionToolbar(wpId) 渲染 GtWpVersionTrail
    - GtB60Bundle 模板顶层挂载 GtWpReviewDialogHost + provide openReviewDialog
    - GtB60ChapterEditor 每章节标题行右侧（AI 按钮之后）提供「💬」复核按钮
    - 点击调用 inject('openReviewDialog')(chapter_id)
    - _Requirements: 11.1, 11.3, 11.4_

  - [x] 6.2 章节定义前端降级 fallback 数组
    - 在 `b60/constants/defaultChapterDefinitions.ts` 维护内置默认章节定义
    - 与后端 JSON 保持同步（至少 9 个一级章节）
    - _Requirements: 4.3_

- [x] 7. PBT 属性测试
  - [x]* 7.1 后端 PBT: Property 1 — wpIdMap 构建使用 wp_id 字段
    - **Property 1: wpIdMap 构建使用 wp_id 字段**
    - 生成随机 wp_index items（含 id 和 wp_id 两个不同字段），验证映射值取自 wp_id 且键匹配 B60-前缀/B60A~D 精确
    - **Validates: Requirements 1.4**

  - [x]* 7.2 后端 PBT: Property 3 — 适用性 JSON 往返
    - **Property 3: 适用性状态序列化/反序列化往返**
    - 生成随机 boolean dict（8 个 B60 系列子底稿编码为键），序列化后反序列化应产生相等映射，缺失键默认 true
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [x]* 7.3 后端 PBT: Property 4 — 章节排序不变量
    - **Property 4: 章节列表按 chapter_id 排序不变量**
    - 生成乱序章节数组，验证排序后字典序
    - **Validates: Requirements 4.4**

  - [x]* 7.4 后端 PBT: Property 6 — 章节内容持久化往返
    - **Property 6: 章节内容持久化往返**
    - 生成随机 chapter_id + content，验证 PUT payload 中 item_id=chapter_id 且 remark=content 且 conclusion=null
    - **Validates: Requirements 6.1, 6.2**

  - [x]* 7.5 后端 PBT: Property 7 — AI context 类型安全
    - **Property 7: AI 请求 context 值全部为 string 类型**
    - 生成随机项目上下文含数字/None，验证转换后全 str
    - **Validates: Requirements 7.2**

  - [x]* 7.6 前端 PBT: Property 2 — Tab 可见性推导
    - **Property 2: Tab 可见性由 wpIdMap + 适用性状态联合推导**
    - 生成随机 wpIdMap + applicability，验证四条规则
    - **Validates: Requirements 2.1, 2.2, 3.2**

  - [x]* 7.7 前端 PBT: Property 5 — 完成指示器颜色
    - **Property 5: 完成指示器颜色由 remark + required 推导**
    - 生成随机 remark + required 组合，验证颜色规则
    - **Validates: Requirements 5.2**

  - [x]* 7.8 前端 PBT: Property 8 — 章节元数据驱动 UI
    - **Property 8: 章节元数据驱动 UI 元素渲染**
    - 生成随机 hint/data_source，验证 UI 元素渲染规则
    - **Validates: Requirements 5.5, 8.1**

  - [x]* 7.9 前端 PBT: Property 9 — 数据拉取追加语义
    - **Property 9: 数据拉取追加语义**
    - 生成随机 existing + pulled content，验证追加规则
    - **Validates: Requirements 8.3**

- [x] 8. Playwright E2E 测试
  - [x]* 8.1 E2E: B60 底稿打开渲染章节编辑器
    - 打开 B60 底稿验证章节编辑器渲染完整
    - Tab 切换 + 适用性矩阵勾选/取消验证 Tab 可见性变化
    - _Requirements: 1.1, 2.1, 3.2_

  - [x]* 8.2 E2E: 章节编辑保存与回显
    - 编辑章节内容 → 等待自动保存 → 刷新页面 → 验证内容回显
    - 验证保存状态指示器状态变化
    - _Requirements: 6.1, 6.2, 6.3_

  - [x]* 8.3 E2E: AI 辅助与模式切换
    - AI 辅助按钮点击（降级测试验证 warning 提示）
    - 模式切换（章节编辑 ↔ 在线编辑）验证 flushPendingSaves 触发
    - _Requirements: 7.1, 12.1, 12.2_

- [x] 9. Final checkpoint - 确保全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- 后端路由注册遵循 router_registry + dedicated_component_routers allowlist 模式
- wp_code_overrides.json 改动需后端 reload 生效
- checklist_responses 白名单需注册 B60-CH-/B60-applicability 前缀
- contextProps: 'standard' 自动透传 wp-id/project-id/wp-code/year

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "4.1", "4.2", "4.3"] },
    { "id": 4, "tasks": ["6.1", "6.2"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5"] },
    { "id": 6, "tasks": ["7.6", "7.7", "7.8", "7.9"] },
    { "id": 7, "tasks": ["8.1", "8.2", "8.3"] }
  ]
}
```
