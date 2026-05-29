# 底稿协同感增强 — 需求文档

## 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-05-22 | 初始版本 |

## 一、为什么做

当前底稿编辑采用 Univer 纯前端方案 + WorkpaperEditingLock 软锁（5min 心跳），技术上已解决冲突问题。但用户反馈缺乏"团队协同感"——不知道同事在干什么、打开底稿时不知道有人正在编辑、复核人看不到编制人的实时进度。

**业务痛点：**
1. 审计助理打开底稿时，如果项目经理正在编辑，只看到 409 错误码，不知道是谁、在做什么、何时结束
2. 项目经理想了解"团队现在谁在线、在编辑哪张底稿"，需要逐个打开底稿才能看到
3. 复核人提交复核意见后，不知道编制人是否已看到、是否正在修改

**不做的事：**
- ❌ 不做多人同时编辑同一底稿（审计 assigned_to 单一编制人模型，业务侧不需要）
- ❌ 不引入 ONLYOFFICE 或其他独立 Document Server
- ❌ 不做 OT/CRDT 实时协同（作为 P3 候选，触发条件"≥5 次同底稿争抢"再启动）

## 二、范围

### 必做（3 个功能点）

| 编号 | 功能 | 说明 |
|------|------|------|
| F1 | 编辑锁 UX 增强 | 打开已被他人编辑的底稿时，显示友好的冲突面板（谁在编辑/心跳时间/三个操作按钮） |
| F2 | Presence 在线面板 | 底稿编辑器右上角显示当前在线查看/编辑本底稿的用户头像列表（SSE 推送） |
| F3 | 编辑锁接管通知 | 当 B 用户 force-acquire 接管 A 的锁时，A 收到实时 SSE 通知 + Toast 提示 |

### 排除

- Univer Pro 协同插件（`@univerjs-pro/collaboration`）— 作为后续 P3 候选
- 底稿内容实时同步（cell-level CRDT）
- 视频/语音通话集成

## 三、功能需求

### F1：编辑锁 UX 增强

**WHEN** 用户打开一张底稿且该底稿有活跃编辑锁（非本人持有）
**THE SYSTEM SHALL** 显示 LockConflictPanel 面板，包含：
- 锁持有者姓名 + 头像
- 最后心跳时间（"2 分钟前活跃"）
- 三个操作按钮：
  - [只读查看] — 以只读模式打开底稿（Univer readOnly=true）
  - [请求接管] — 调用 `POST /editing-lock/force`，成功后进入编辑模式
  - [稍后再来] — 关闭当前页面/返回底稿列表

**IF** 锁已过期（heartbeat_at > 5min 前）
**THE SYSTEM SHALL** 自动清理过期锁并正常进入编辑模式（现有逻辑已支持）

### F2：Presence 在线面板

**WHEN** 用户打开底稿编辑器
**THE SYSTEM SHALL** 在右上角工具栏区域显示 PresenceAvatars 组件：
- 显示当前正在查看/编辑本底稿的所有用户头像（最多 5 个 + "+N"溢出）
- 编辑中的用户头像带绿色边框 + "编辑中"tooltip
- 只读查看的用户头像带灰色边框 + "查看中"tooltip
- 用户离开底稿页面后 10s 内从列表移除

**后端实现：**
- Redis key `presence:{wp_id}` 存储 `{user_id, user_name, avatar, mode: 'edit'|'view', last_seen}`
- 前端每 30s 发送 heartbeat `PATCH /api/workpapers/{wp_id}/presence`
- 前端通过 SSE 事件 `presence.joined` / `presence.left` 实时更新列表
- 用户关闭页面时 `DELETE /api/workpapers/{wp_id}/presence`（beforeunload + visibilitychange 双保险）

### F3：编辑锁接管通知

**WHEN** 用户 B 通过 force-acquire 接管了用户 A 的编辑锁
**THE SYSTEM SHALL**：
1. 后端发布 SSE 事件 `editing_lock.force_acquired`（payload: `{wp_id, new_holder, previous_holder}`）
2. 用户 A 的前端收到事件后：
   - 显示 ElNotification 警告："[B] 已接管底稿 [wp_name] 的编辑权限，您的修改已自动保存"
   - 自动触发一次 univer-save（保存 A 的当前修改）
   - 将 Univer 切换为 readOnly 模式
3. 用户 A 可点击通知中的"重新获取编辑权"按钮尝试 acquire

## 四、非功能需求

| 维度 | 指标 |
|------|------|
| Presence 更新延迟 | ≤ 3s（从用户打开底稿到其他用户看到头像） |
| 接管通知延迟 | ≤ 2s（从 force-acquire 到原持有者收到通知） |
| Presence heartbeat 频率 | 30s（不增加后端负载） |
| Redis 内存占用 | 每个 presence key ≤ 1KB（JSON 数组，最多 20 用户） |
| 兼容性 | 不影响现有 useEditingLock composable 的 API 契约 |

## 五、测试矩阵

| 类型 | 文件 | 覆盖 |
|------|------|------|
| 后端单测 | `test_presence_service.py` | F2 Redis 操作 + TTL 过期 + 并发安全 |
| 后端单测 | `test_editing_lock_notify.py` | F3 force-acquire 事件发布 |
| 前端 vitest | `LockConflictPanel.spec.ts` | F1 三按钮交互 + 过期自动清理 |
| 前端 vitest | `PresenceAvatars.spec.ts` | F2 头像列表渲染 + 溢出 + mode 区分 |
| 前端 vitest | `usePresence.spec.ts` | F2 heartbeat + SSE 事件处理 |

## 六、依赖

- 现有：`WorkpaperEditingLock` 模型 + `editing_lock_service.py` + `useEditingLock.ts`
- 现有：SSE 基础设施（`useProjectEvents` + `eventBus` + `sse:sync-event`）
- 现有：Redis 连接（`app/core/redis.py`）
- 无新增外部依赖
