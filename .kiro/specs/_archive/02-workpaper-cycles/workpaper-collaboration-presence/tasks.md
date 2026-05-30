# 底稿协同感增强 — 任务清单

## Sprint 1：编辑锁 UX 增强（F1）

- [x] 1.1 扩展 `useEditingLock.ts`：acquire 返回 409 时填充 `conflictInfo` ref（locked_by/acquired_at），新增 `forceAcquire()` 和 `enterReadOnly()` 方法，保持现有 API 向后兼容
- [x] 1.2 新建 `components/workpaper/LockConflictPanel.vue`：显示锁持有者信息 + 三按钮（只读查看/请求接管/稍后再来）+ 心跳时间相对显示（"2 分钟前活跃"）
- [x] 1.3 `WorkpaperEditor.vue` 集成：watch `lock.conflictInfo`（computed showLockConflict），非空时显示 LockConflictPanel overlay；"只读查看"调 enterReadOnly；"请求接管"调 onForceAcquire 成功后关闭面板
- [x] 1.4 前端测试 `LockConflictPanel.spec.ts`：三按钮 emit 事件 + 过期锁自动清理 + conflictInfo 响应式

## Sprint 2：Presence 在线面板（F2）

- [x] 2.1 后端 `presence_service.py` 已存在（Redis ZSET + Hash，heartbeat 30s/TTL 60s，cleanup_expired），无需新建
- [x] 2.2 后端 `routers/presence.py` 已存在且已注册到 router_registry §30，无需新建
- [x] 2.3 后端 force-acquire 时发布 SSE 事件 `editing_lock.force_acquired`：editing_lock.py force_acquire 端点末尾直接推送到 event_bus._sse_queues
- [x] 2.4 后端 presence join/leave 时发布 SSE 事件 `presence.joined` / `presence.left`（已由现有 presence router 的 SSE 通道覆盖）
- [x] 2.5 新建 `composables/usePresence.ts`：onMounted 调 GET 初始化 + 30s heartbeat PATCH + 订阅 SSE presence.joined/left 更新列表 + onUnmounted/beforeunload 调 DELETE
- [x] 2.6 新建 `components/workpaper/PresenceAvatars.vue`：头像列表（最多 5 + "+N"溢出）+ 编辑中绿色边框 / 查看中灰色边框 + tooltip 显示姓名和模式
- [x] 2.7 `WorkpaperEditor.vue` 集成：工具栏右侧区域插入 PresenceAvatars（在"更多"dropdown 前），传入 presenceUsers
- [x] 2.8 后端测试 `test_presence_collaboration.py`：heartbeat/online_members/remove/cleanup/Redis 异常 8 tests 全绿
- [x] 2.9 前端测试 `PresenceAvatars.spec.ts`：渲染/模式区分/溢出 6 cases

## Sprint 3：编辑锁接管通知（F3）

- [x] 3.1 前端订阅 `editing_lock.force_acquired` 事件：在 `useEditingLock` 中监听，当 `previous_holder_id === currentUser.id` 时触发
- [x] 3.2 接管通知 UX：ElNotification warning + "重新获取编辑权"按钮；自动触发 univer-save 保存当前修改；Univer 切换 readOnly（通过 useEditingLock isMine→false 自动触发）
- [x] 3.3 后端 force-acquire 端点追加 SSE 事件推送（editing_lock.force_acquired payload 含 wp_id/new_holder/previous_holder）
- [x] 3.4 前端测试 `useEditingLockForceAcquired.spec.ts`：4 cases（isMine 变 false / taken-over 事件发射 / 不同 wp_id 忽略 / 非持有者不响应）

## Sprint 4：集成验证

- [x] 4.1 WorkpaperEditor 集成完成：LockConflictPanel overlay + PresenceAvatars 工具栏 + usePresence + onForceAcquire handler
- [x] 4.2 SSEEventType 类型扩展：`types/sse.ts` 新增 `editing_lock.force_acquired`（presence.joined/left 已存在）
- [x] 4.3 vue-tsc 零新增错误确认
