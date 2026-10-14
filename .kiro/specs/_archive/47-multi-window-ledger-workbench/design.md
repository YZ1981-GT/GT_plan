# 多窗口查账工作台 — 设计

> spec: `multi-window-ledger-workbench`

## §1 架构概览

```
┌─────────────────────────────────┐   BroadcastChannel('gt-auth')   ┌──────────────────────────┐
│  窗口 A — 底稿编辑              │ ◄──────────────────────────────► │  窗口 B — 查账           │
│  /projects/:pid/wp/:wpId/edit   │   token sync / logout / lock    │  /ledger-workbench/:pid  │
│                                 │                                 │  ?year=&level=&account=  │
│  ThreeColumnLayout              │                                 │  LedgerStandalonePage    │
│  useEditingLock(clientInstance)  │                                 │  (独立布局，无三栏)       │
│  SSE connection 1               │                                 │  SSE connection 2        │
└─────────────────────────────────┘                                 └──────────────────────────┘
        │                                                                    │
        └──────────── 后端 9980 ──── editing_locks + client_instance ────────┘
```

## §2 独立查账窗口（R1 + R2）

### 2.1 新路由

在 `router/domains/standalone.ts` 新增：

```ts
{
  path: '/ledger-workbench/:projectId',
  name: 'LedgerWorkbench',
  component: () => import('@/views/LedgerStandalonePage.vue'),
  meta: { requireAuth: true },
}
```

### 2.2 LedgerStandalonePage.vue

精简独立壳页面：自带顶栏（项目名 + 年度 + 回到主窗口按钮），主区域复用已有 `LedgerPenetration.vue`。不嵌套 DefaultLayout/ThreeColumnLayout。

### 2.3 查账现场 URL 同步（R2）

在 `LedgerPenetration.vue` 中：

- 新增 composable `useLedgerUrlSync(router, route)`
- 在 `drillToLedger / drillToVoucher / drillToAuxBalance / drillToAuxLedger / navigateTo` 每个穿透函数末尾调用 `syncToUrl()`
- `syncToUrl` 使用 `router.replace({ query: { ...现有query, level, account, voucher, voucherDate, dateFrom, dateTo, auxType, auxCode, balanceTab } })` 避免产生历史记录堆积
- `onMounted` 中从 `route.query` 恢复 level/account 等状态，替换当前的"只恢复 account 高亮"逻辑

### 2.4 窗口打开工具函数

```ts
// utils/openLedgerWindow.ts
export function openLedgerWindow(projectId: string, year?: number) {
  const route = router.resolve({
    name: 'LedgerWorkbench',
    params: { projectId },
    query: year ? { year: String(year) } : {},
  })
  window.open(route.href, `gt-ledger-${projectId}`)
}
```

窗口名固定使得重复调用聚焦已有窗口。

## §3 跨窗口认证同步（R3）

### 3.1 模块 `utils/crossWindowAuth.ts`

```ts
const channel = new BroadcastChannel('gt-auth')

type AuthMessage =
  | { type: 'token-updated'; token: string; refreshToken: string }
  | { type: 'logout' }
  | { type: 'session-request' }
  | { type: 'session-response'; token: string; refreshToken: string; user: any }

export function broadcastTokenUpdate(token, refreshToken) { ... }
export function broadcastLogout() { ... }
export function requestSession(): Promise<{ token, refreshToken, user } | null> { ... }
export function listenAuthEvents(handlers: { onTokenUpdate, onLogout, onSessionRequest }) { ... }
```

### 3.2 接线

- `stores/auth.ts` 的 `refreshAccessToken` 方法内加 `navigator.locks.request('gt-token-refresh', ...)` 单飞
- 刷新成功后调 `broadcastTokenUpdate`
- `logout` 方法内调 `broadcastLogout`
- `http.ts` 的 401 拦截器在排队等待刷新前，先等 BroadcastChannel 是否有新 token 到达
- 新窗口 `main.ts` 挂载前若 `sessionStorage` 无 token，调 `requestSession()` 等待已有窗口广播会话

### 3.3 Web Locks 单飞

```ts
async function singleFlightRefresh() {
  return navigator.locks.request('gt-token-refresh', async () => {
    // 先检查 sessionStorage 里的 token 是否已经被其他窗口更新
    const current = sessionStorage.getItem('token')
    if (current && !isTokenExpired(current)) return current
    // 执行真正的刷新
    const result = await authService.refresh(refreshToken)
    // 保存并广播
    ...
  })
}
```

## §4 窗口实例级编辑锁（R4）

### 4.1 clientInstanceId 生成

```ts
// utils/clientInstance.ts
const KEY = 'gt-client-instance-id'
export function getClientInstanceId(): string {
  let id = sessionStorage.getItem(KEY)
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem(KEY, id)
  }
  return id
}
```

每个浏览器标签页拥有独立的 sessionStorage（`window.open` 时从 opener 复制，但 `crypto.randomUUID()` 保证不同），因此每个标签页有不同的 instanceId。

### 4.2 前端改动

- `utils/http.ts` 请求拦截器为编辑锁端点自动添加 `X-Client-Instance` header
- `useEditingLock.ts` 的 acquire 失败（409）时设置 `forcedReadonly = true`
- `WorkpaperEditor.vue` 中将 `editLock.isMine && !editLock.forcedReadonly` 作为所有保存按钮的 `:disabled` 绑定条件
- `onBeforeUnload` 中 release 只释放本 instance 的锁

### 4.3 后端改动

- `backend/migrations/V185__editing_lock_client_instance.sql`：`ALTER TABLE editing_locks ADD COLUMN IF NOT EXISTS client_instance VARCHAR(64)`
- `editing_lock_service.acquire_lock`：同 user_id + 不同 client_instance → 返回 locked=True（冲突）
- `editing_lock_service.release_lock`：新增可选 `client_instance` 参数，传入时只释放匹配的锁
- `editing_lock_service.heartbeat_lock`：同理，只续期匹配 instance 的锁

## §5 验收判据

| # | 判据 | 验证方式 |
|---|------|---------|
| AC-1 | 点击"打开查账窗口"弹出独立查账窗口，再次点击聚焦同一窗口 | 手动 / Playwright |
| AC-2 | 查账窗口穿透到凭证后刷新浏览器，恢复到原凭证页面 | 手动 / Playwright |
| AC-3 | 窗口 A 底稿编辑 + 窗口 B 查账，持续 > 30 分钟不被登出 | 手动 |
| AC-4 | 窗口 A 登出后，窗口 B 同步跳转登录页 | 手动 |
| AC-5 | 同一底稿在第二个窗口打开时自动切为只读，所有保存按钮禁用 | 手动 |
| AC-6 | 关闭持锁窗口后，另一个窗口可正常获取锁进入编辑 | 手动 |
| AC-7 | 不同项目分别开窗，项目上下文互不影响 | 手动 |
| AC-8 | 后端测试：同 user_id 不同 client_instance acquire 返回 locked | pytest |
