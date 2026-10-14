# 多窗口查账工作台 — 任务清单

> spec: `multi-window-ledger-workbench`

## Phase 1: 独立查账窗口 + URL 现场恢复

- [x] Task 1: 创建 `LedgerStandalonePage.vue` 独立壳页面（顶栏 + 复用 LedgerPenetration）
- [x] Task 2: 在 `router/domains/standalone.ts` 注册 `/ledger-workbench/:projectId` 顶层路由
- [x] Task 3: 创建 `utils/openLedgerWindow.ts` 窗口打开工具函数（router.resolve + window.open + 窗口名复用）
- [x] Task 4: 在底稿编辑器工具栏、试算表页面增加「打开查账窗口」按钮并接线
- [x] Task 5: 创建 `composables/useLedgerUrlSync.ts` 实现穿透状态 ↔ URL query 双向同步
- [x] Task 6: 改造 `LedgerPenetration.vue` 接入 useLedgerUrlSync：穿透写 URL + 挂载读 URL 恢复现场

## Phase 2: 跨窗口认证同步

- [x] Task 7: 创建 `utils/crossWindowAuth.ts`（BroadcastChannel + 消息类型 + 监听/广播 API）
- [x] Task 8: 创建 `utils/clientInstance.ts`（每标签页唯一 clientInstanceId）
- [x] Task 9: 改造 `stores/auth.ts`：refreshAccessToken 加 Web Locks 单飞 + 广播 token 更新
- [x] Task 10: 改造 `stores/auth.ts`：logout 广播 + 监听其他窗口的 logout 事件
- [x] Task 11: 改造 `http.ts`：401 刷新前先检查 BroadcastChannel 是否已有新 token
- [x] Task 12: 新窗口启动时若无 token，通过 BroadcastChannel 向已有窗口请求会话

## Phase 3: 窗口实例级编辑锁

- [x] Task 13: 创建 `V185__editing_lock_client_instance.sql` + `R185` 迁移（新增 client_instance 列 + ORM 映射）
- [x] Task 14: 改造后端 `editing_lock_service.py`：acquire/release/heartbeat 支持 client_instance 隔离
- [x] Task 15: 改造后端 `routers/editing_locks.py`：从 `X-Client-Instance` header 读取并传递
- [x] Task 16: 改造前端 `http.ts`：编辑锁端点请求自动携带 `X-Client-Instance` header
- [x] Task 17: 改造前端 `useEditingLock.ts`：acquire 失败时设 forcedReadonly，暴露给宿主
- [x] Task 18: 改造 `WorkpaperEditor.vue`：editLock.forcedReadonly 时禁用所有保存按钮与自动保存

## Phase 4: 验收与守卫

- [x] Task 19: 后端 pytest 测试：同 user_id 不同 client_instance acquire 返回 locked（7 passed）
- [x] Task 20: 后端 pytest 测试：release 只释放匹配 instance 的锁（含上述 7 用例）
- [x] Task 21: 前端 vitest 测试：useLedgerUrlSync 双向同步（8 passed）
- [x] Task 22: 前端 vitest 测试：crossWindowAuth BroadcastChannel 消息收发（4 passed）
- [x] Task 23: Playwright 双窗口实测（查账窗口打开 + 穿透刷新恢复 + 登出同步）— 5 passed
- [x] Task 24: Playwright 双窗口实测（同底稿第二窗口只读门禁 — 后端 API 级验证）
