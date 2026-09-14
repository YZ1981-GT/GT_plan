# Tasks: 通用审计复核对话组件 (GtReviewDialog)

## 1. 后端数据库迁移

- [x] 1.1 创建 `backend/migrations/V095__review_threads.sql`，包含 review_threads 和 review_messages 两张表定义、唯一索引、FK 约束
- [x] 1.2 创建对应的 `backend/migrations/R095__review_threads.sql` 回滚脚本

## 2. 后端路由与 API

- [x] 2.1 创建 `backend/app/routers/review_dialog.py`（~200行），实现 GET /api/review-threads（查询或自动创建线程+消息列表）、POST /api/review-threads/{thread_id}/messages（发送消息+broadcast_raw）
- [x] 2.2 实现 POST /api/workpapers/{wp_id}/review-dialog/ai-generate 端点，复用 chat_completion + system prompt
- [x] 2.3 在 `backend/app/router_registry/collaboration.py` 中注册 review_dialog router（§125）
- [x] 2.4 后端权限校验：验证当前用户对底稿的访问权限（project_assignments 角色检查）

## 3. 前端 Composable

- [x] 3.1 创建 `audit-platform/frontend/src/composables/useReviewDialog.ts`（~300行），实现消息 CRUD（openDialog/closeDialog/sendMessage/retryMessage）
- [x] 3.2 实现 SSE 订阅逻辑：eventBus.on('sse:sync-event') 过滤 review_message.created + thread_id 匹配 + 排除自己 + unreadCount
- [x] 3.3 实现多选状态管理：enterSelectMode/exitSelectMode/toggleSelect/shiftSelect/selectAll/selectedCount/canExport
- [x] 3.4 实现导出流程：exportSelected（格式化选中消息）→ aiPolish（AI润色）→ saveToReviewRecord（写入 checklist_responses）
- [x] 3.5 实现 AI 生成调用：aiGenerate（构建 context + 调用端点 + 覆盖确认）
- [x] 3.6 实现权限逻辑：canWrite/canRead 基于角色计算
- [x] 3.7 实现关闭确认逻辑：handleClose（判断消息是否为空→直接关/弹确认）

## 4. 前端 Vue 组件

- [x] 4.1 创建 `audit-platform/frontend/src/components/collaboration/GtReviewDialog.vue`（~400行），实现面板布局（el-drawer 400px 右侧滑入 + 顶部标题栏 + 消息列表 + 底部输入区）
- [x] 4.2 实现消息气泡渲染：左右对齐 + 头像(首字母圆形) + 内容 + 时间(HH:mm) + 角色标签 + 失败状态(红色❗+重发)
- [x] 4.3 实现多选模式 UI：左侧圆形选择框 + 顶部"选择消息/全选/取消" + 底部"已选N条/导出"
- [x] 4.4 实现关闭确认弹窗（el-dialog）：三按钮（关闭/继续/导出到复核记录）
- [x] 4.5 实现导出编辑弹窗（el-dialog 600px）：textarea + AI润色按钮 + 取消/保存按钮
- [x] 4.6 实现键盘交互：Enter 发送 / Shift+Enter 换行 / 新消息自动滚动底部

## 5. Property-Based Tests（前端 fast-check）

- [x] 5.1 Property 1: thread_key 构建唯一性 — `fc.uuid()` + `fc.constantFrom(...)` 验证格式和唯一性
- [x] 5.2 Property 2: 消息对齐方向 — 自定义 ReviewMessage 生成器验证 alignment 逻辑
- [x] 5.3 Property 3: 乐观更新列表长度 — 验证 sendMessage 后 messages.length === N+1
- [x] 5.4 Property 4: SSE 事件过滤 — 验证仅匹配 thread_id 且非自己的消息被追加
- [x] 5.5 Property 5: 空列表跳过确认 — 验证 messages=[] 时 handleClose 直接关闭
- [x] 5.6 Property 6: toggle 选择自逆 — 验证 toggleSelect 执行两次恢复原状
- [x] 5.7 Property 7: shift 范围选择 — 验证选中 [min,max] 闭区间所有消息
- [x] 5.8 Property 8: 导出文本格式化 — 验证按时间顺序 + 角色时间前缀
- [x] 5.9 Property 9: 失败状态保持 — 验证 API 错误不改变 exportText
- [x] 5.10 Property 10: 角色权限映射 — 验证 5 种角色对应的 canWrite/canRead
- [x] 5.11 Property 12: item_id 格式合规 — 验证正则匹配
- [x] 5.12 Property 13: 元数据完整性 — 验证 remark JSON 含全部必要字段
- [x] 5.13 Property 14: 未读计数单调递增 — 验证面板关闭时 count++，打开时 reset

## 6. 后端集成测试（hypothesis + pytest）

- [x] 6.1 Property 11: 关闭线程拒绝消息 — hypothesis 生成随机消息内容，验证 closed thread 返回 400
- [x] 6.2 测试 thread_key 唯一约束：同 wp_id+section_id 二次请求返回同一线程
- [x] 6.3 测试 broadcast_raw 调用：消息创建后验证 event_bus.broadcast_raw 被调用且 payload 正确
- [x] 6.4 测试 AI 生成端点：mock chat_completion 验证返回结构
- [x] 6.5 测试权限守卫：无关项目用户请求返回 403

## 7. 单元测试（vitest）

- [x] 7.1 useReviewDialog 基础功能：openDialog 加载消息、sendMessage 乐观更新、retryMessage 重发
- [x] 7.2 多选模式测试：进入/退出/全选/取消/选中计数/导出按钮禁用
- [x] 7.3 关闭确认逻辑：有消息弹确认、无消息直接关、三按钮行为
- [x] 7.4 GtReviewDialog 组件渲染测试：Props 传入/只读模式/气泡对齐

## 8. 集成与注册

- [x] 8.1 创建 `useReviewDialogProvider.ts`（~80行），实现 provide/inject 全局激活机制
  - provide('reviewDialog', { openReviewDialog, closeReviewDialog, isOpen, activationParams })
  - 在 WorkpaperEditor.vue 或底稿编辑器顶层组件中调用 useReviewDialogProvider()
  - 在顶层 template 中放置 `<GtReviewDialog v-if="isOpen" v-bind="activationParams" />`

- [x] 8.2 实现右键菜单激活（v-review-context 指令或 @cell-contextmenu）
  - el-table 单元格右键：自动生成 sectionId = `{prefix}-{rowKey}-{field}`
  - sectionLabel 自动拼接行标题+列标题+格式化后的值
  - 注册到右键菜单项"📝 发起复核对话"

- [x] 8.3 实现活跃线程标记
  - 新增后端端点 `GET /api/review-threads/active?wp_id={wpId}`（返回线程列表含 section_id + has_unread）
  - 底稿加载时批量查询活跃线程
  - 在对应位置渲染小圆点标记（蓝色=有对话，红色=有未读）

- [x] 8.4 在 D1TabAdjudication.vue 的"1.审计说明"和"2.审计结论"区域集成（固定入口按钮示范）

- [x] 8.5 在底稿编辑器工具栏添加"复核对话"图标（el-popover 列出活跃线程列表，点击进入对应对话）

- [x] 8.6 验证 ReviewPanel 时间线中能展示 review-record 前缀的 checklist_responses 条目
