# 底稿协同感增强 — 设计文档

## ADR-1：Presence 存储选型

**决策**：Redis Hash（不用 PG 表）

**理由**：
- Presence 是高频短生命周期数据（30s heartbeat），写 PG 会产生大量 dead tuple
- Redis TTL 天然支持"用户离开后自动清理"
- 现有 `app/core/redis.py` 已有 `get_redis()` 降级逻辑（Redis 不可用时返回 None）

**数据结构**：
```
Key:   presence:wp:{wp_id}
Type:  Hash
Field: {user_id}
Value: JSON {"user_name": "张三", "avatar": null, "mode": "edit", "last_seen": 1716400000}
TTL:   60s（每次 heartbeat 刷新 TTL）
```

**降级**：Redis 不可用时 Presence 功能静默禁用（不影响编辑功能）

## ADR-2：SSE 事件扩展

**决策**：复用现有 `sse:sync-event` 通道，新增 3 个事件类型

| 事件 | payload | 触发时机 |
|------|---------|---------|
| `presence.joined` | `{wp_id, user_id, user_name, mode}` | 用户打开底稿 |
| `presence.left` | `{wp_id, user_id}` | 用户离开底稿 / heartbeat 过期 |
| `editing_lock.force_acquired` | `{wp_id, new_holder_id, new_holder_name, previous_holder_id}` | force-acquire 成功 |

**前端订阅**：通过 `useProjectEvents.onAnyEvent()` 过滤 event_type 前缀

## ADR-3：LockConflictPanel 触发时机

**决策**：在 `useEditingLock` acquire 返回 409 时触发（不改现有 composable API）

**实现**：
```ts
// WorkpaperEditor.vue
const lock = useEditingLock({ resourceId: wpId, resourceType: 'workpaper' })

// 新增：监听 lock 冲突状态
watch(lock.conflictInfo, (info) => {
  if (info) showLockConflictPanel.value = true
})
```

`useEditingLock` 扩展返回值：
```ts
interface EditingLockReturn {
  // 现有
  locked: Ref<boolean>
  isMine: Ref<boolean>
  lockedBy: Ref<string | null>
  release: () => Promise<void>
  // 新增
  conflictInfo: Ref<{ locked_by: string; acquired_at: string } | null>
  forceAcquire: () => Promise<boolean>
  enterReadOnly: () => void
}
```

## 组件结构

```
components/workpaper/
├── LockConflictPanel.vue      — F1 冲突面板（三按钮）
├── PresenceAvatars.vue        — F2 头像列表
composables/
├── useEditingLock.ts          — 扩展 conflictInfo/forceAcquire（向后兼容）
├── usePresence.ts             — F2 新建（heartbeat + SSE 订阅）
backend/app/
├── services/presence_service.py  — Redis Hash CRUD
├── routers/presence.py           — PATCH/DELETE /api/workpapers/{wp_id}/presence
```

## 端点设计

### PATCH /api/workpapers/{wp_id}/presence

心跳（加入/续期）。

```json
Request: { "mode": "edit" | "view" }
Response: { "users": [{"user_id": "...", "user_name": "...", "mode": "edit", "last_seen": 1716400000}] }
```

### DELETE /api/workpapers/{wp_id}/presence

离开。

```json
Response: { "removed": true }
```

### GET /api/workpapers/{wp_id}/presence

查询当前在线用户（初始加载用）。

```json
Response: { "users": [...] }
```

## 工时估算

| Sprint | 内容 | 工时 |
|--------|------|------|
| 1 | F1 LockConflictPanel + useEditingLock 扩展 | 1 天 |
| 2 | F2 presence_service + usePresence + PresenceAvatars | 2 天 |
| 3 | F3 force-acquire SSE 通知 + 自动保存 + readOnly 切换 | 1 天 |
| 4 | 测试 + WorkpaperEditor 集成 | 1 天 |
| **合计** | | **5 天** |
