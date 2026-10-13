# 多窗口查账工作台 — 需求

> spec: `multi-window-ledger-workbench`
> 创建日期: 2026-10-13

## 背景

审计助理的典型工作流是**一边查账一边编底稿**：在科目余额表 → 序时账 → 凭证之间反复穿透，同时在另一个页面编制审定表、明细表或程序表。当前平台只能在同一个浏览器标签页内切换，查账和底稿编辑互相覆盖，导致频繁的导航往返和上下文丢失。

用户明确要求"能同时打开多个窗口，查账界面常驻，另一个窗口做底稿"。

## 功能需求

### R1 独立查账窗口入口
- R1.1 项目页顶部工具栏、底稿编辑器工具栏、试算表页面各增加「📊 打开查账窗口」按钮
- R1.2 点击后使用 `router.resolve()` + `window.open()` 打开查账页面
- R1.3 窗口名称按 `gt-ledger-{projectId}` 固定，再次点击聚焦已有窗口而非重复创建
- R1.4 查账窗口使用独立的顶层路由（不嵌套在 DefaultLayout 三栏布局内），参考已有 `/ai-chat` standalone 模式

### R2 查账现场 URL 恢复
- R2.1 `LedgerPenetration.vue` 的穿透状态（level/account/voucherNo/voucherDate/dateFrom/dateTo/auxType/auxCode/balanceTab）同步写入 `route.query`
- R2.2 组件挂载时从 `route.query` 恢复完整穿透现场（而非只恢复 projectId/year/account 高亮）
- R2.3 刷新浏览器、复制 URL 到新标签均可回到原科目/原凭证/原筛选
- R2.4 面包屑导航和内部 level 切换同步更新 URL query

### R3 跨窗口认证同步
- R3.1 使用 `BroadcastChannel('gt-auth')` 在同源窗口间同步 access_token / refresh_token / logout 事件
- R3.2 使用 `navigator.locks.request('gt-token-refresh', ...)` 保证同一时刻只有一个窗口执行 token refresh
- R3.3 token 刷新成功后广播新 token，其他窗口更新本地 sessionStorage 和 axios header
- R3.4 任一窗口登出时广播 logout 事件，所有窗口同步跳转到登录页
- R3.5 新窗口（`window.open` 创建）在 `sessionStorage` 为空时，通过 `BroadcastChannel` 向已登录窗口请求当前会话

### R4 窗口实例级编辑锁
- R4.1 每个浏览器窗口/标签页在启动时生成唯一 `clientInstanceId`（crypto.randomUUID()），存入 sessionStorage
- R4.2 `useEditingLock` 的 acquire/heartbeat/release 请求携带 `X-Client-Instance` header
- R4.3 后端 `editing_lock_service.acquire_lock` 新增 `client_instance` 列，同一 user_id 不同 instance 视为锁冲突
- R4.4 同一底稿第二个窗口打开时收到 409（他人持锁），自动切入只读模式
- R4.5 编辑锁冲突不仅显示横幅，还必须禁用所有保存按钮与自动保存（真门禁而非仅提示）
- R4.6 窗口关闭/卸载时只释放本 instance 的锁，不影响同一用户其他窗口

### R5 SSE 连接与并发控制
- R5.1 每个窗口独立建立 SSE 连接（当前行为保持不变），在后端 6000 并发规划中按"每用户平均 2 连接"测算
- R5.2 后续可选优化：同浏览器同项目的窗口通过 BroadcastChannel 转发 SSE 事件，减少重复连接

## 非功能需求

### NR1 性能
- 查账窗口独立加载不得增加主窗口首屏时间
- BroadcastChannel 消息延迟 < 50ms（同机同进程内）

### NR2 兼容
- Chrome 90+ / Edge 90+ / Firefox 94+（BroadcastChannel + Web Locks 均已支持）
- Safari 15.4+（Web Locks 从 15.4 起支持）
- 不依赖 SharedWorker（兼容性较差）

### NR3 安全
- token 不通过 URL 传递（只经 BroadcastChannel + sessionStorage）
- clientInstanceId 不用于鉴权，仅用于锁隔离
- 编辑锁后端校验仍以 JWT user_id 为权威身份

## 产品边界

| 场景 | 支持级别 |
|------|---------|
| 查账窗口 + 底稿窗口 | ✅ 正式支持 |
| 多个不同底稿窗口 | ✅ 正式支持 |
| 不同项目分别开窗 | ✅ 正式支持 |
| 同一底稿两窗口 | ⚠️ 第二窗只读 |
| 查账窗口内抽样/挂凭 | ✅ 允许写操作 |

## 排除项
- 应用级多页签 UI（类 VS Code tabs）—— 超出本 spec 范围
- SSE 跨窗口复用 —— 作为 R5.2 可选优化，不阻塞本次交付
- 生产部署 SPA fallback —— 需独立评估部署形态
