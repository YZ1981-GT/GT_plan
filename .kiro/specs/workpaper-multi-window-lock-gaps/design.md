# 底稿多窗口编辑锁两处漏洞收口 — 设计

> spec: `workpaper-multi-window-lock-gaps`

## 1 现状（2026-10-31 现算）

- 窗口编号 `utils/clientInstance.ts`：sessionStorage 有值就复用，只有「存在活着的 opener」才换新。复制标签页没有 opener ⇒ 沿用。
- 编号的使用方：`utils/http.ts` 只给 `/editing-locks/` 请求加 `X-Client-Instance`；`useEditingLock` 卸载时 keepalive DELETE 自带；
  `crossWindowAuth` 用它当广播 `senderId`，`listenAuthEvents` / `requestSession` 在启动时记下 `myId` 再比较。
- 后端：`editing_lock_service` 已按「同人不同窗口 = 冲突」处理取锁；`editing_lock_service` 只被锁路由引用，没有任何写接口校验锁。
- 后端带 `{wp_id}` 的写路由 608 条；其中导入类 / `checklist-responses` / `save` / `save-version` 共 132 条，**全部**已挂
  `dedicated_wp_gate`（路由级可见性门，探针逐条核对依赖树）。

## 2 决策

- D1 窗口编号用 Web Locks 认领：对当前编号请求 `gt-client-instance:<id>`（`ifAvailable`），拿到就持有到本页卸载；
  拿不到 ⇒ 另一个活着的标签页正用这个编号 ⇒ 换新编号再认领。刷新时旧文档卸载即释放，新文档认领回原编号。
  选它而不选 BroadcastChannel 询问：原子、无需等超时；平台已用 Web Locks（`gt-token-refresh`）。
  支持 Web Locks 时不再按 opener 换号（`window.open` 出来的标签页刷新不再每次换号）；不支持时保持原 opener 判断。
  `request` 抛错 / 拒绝 ⇒ 视为不可用，保留当前编号（不误判成重复）。
- D1b 不提供 Web Locks 时（非安全上下文）：首次取编号时在 localStorage 登记 `gt-client-instance-open:<id>`（值为登记时间），
  `pagehide` 注销、`pageshow`（从往返缓存恢复）重新登记；首次取编号时读到自己的编号已被登记 ⇒ 另一个打开着的标签页在用 ⇒ 换新号。
  同步判定，不用等。被浏览器丢弃（省内存）后重新加载（`document.wasDiscarded`）时登记是自己留下的，认回原编号。
  localStorage 不可用 ⇒ 退回 opener 判断。生成编号改用 `utils/uuid.newUuid`（没有 `randomUUID` 时用 `getRandomValues`）。
  否决「BroadcastChannel 询问」的理由同 D1；否决心跳时间戳：后台标签页定时器被浏览器压到约每分钟一次，阈值难定。
- D2 `main.ts` 启动即认领（不阻塞挂载）；`useEditingLock.acquire / forceAcquire` 先 `await` 认领结果再发请求。
- D3 `crossWindowAuth` 两处比较改读当前编号（`getClientInstanceId()` 在认领后返回新编号）。
- D4 后端校验放在 `dedicated_wp_gate`：可见性门通过后，写方法 + 路由模板匹配内容写入 + 路径参数是 `wp_id` 时，查该底稿有效锁：
  - 无有效锁 → 放行；锁是请求人的 → 请求带了窗口编号、锁上也记了窗口且二者不同才拦，否则放行；锁是别人的 → 拦。
  - 拦截：423，detail 写明谁在编辑、本次修改未保存（前端全局 423 处理直接显示 detail；静默调用方按保存失败显示）。
  - 判定函数 `editing_lock_service.find_blocking_lock`（只读查询），门里调用。
- D5 前端写请求带编号：`http.ts` 对非 GET 请求一律加 `X-Client-Instance`（不涉鉴权，仅锁隔离）；Word 底稿导入是原生 fetch，单独补。
- D6 前端只读拦截：`GtWpToolbar` 加 `readonly`（禁用导入 / 增行）；`GtWpRenderer` 传入并在 `onImportData` 只读时提示返回；
  `WorkpaperWordEditor`「导入数据」只读禁用。

## 3 风险与边界

- 持有 Web Lock 的页面不进浏览器往返缓存（bfcache）；本应用页面本就挂着事件流长连接，影响可忽略。
- 部署过渡期：升级前打开、未刷新的旧标签页不持有编号锁，从它复制出来的标签页可能认领到同一编号；旧标签页刷新后恢复正常。
- `navigator.sendBeacon`（卸载时补存）带不了请求头：持锁人本人照旧放行（R2.4）；它本身也带不了 Authorization，非本次范围。
- 只拦 132 条内容写入；AI 生成、OCR、复核、批注、在线编辑同步等写接口不在本次范围（非目标）。
- D1b：页面崩溃来不及注销 ⇒ 重新加载时多换一次号；崩溃前持锁的话，旧编号的锁要等 5 分钟心跳过期，期间本页只读。
  复制标签页的同时刷新原标签页这类同时加载，两边可能各换一次号，结果仍只有一个窗口能编辑。

## 4 涉及文件

前端：`utils/clientInstance.ts`（含 D1b）、`main.ts`、`composables/useEditingLock.ts`、`utils/crossWindowAuth.ts`、`utils/http.ts`、
`components/workpaper/GtWpToolbar.vue`、`components/workpaper/GtWpRenderer.vue`、`components/workpaper/WorkpaperWordEditor.vue`。
后端：`services/editing_lock_service.py`、`routers/_wp_gate.py`。

## 5 范围外发现（2026-10-31，未修，待用户定）

内网地址走 http（本机 `http://192.168.20.60:3030`）不是安全上下文：Chrome 实测 `navigator.locks`、`crypto.randomUUID`、
`crypto.subtle`、`navigator.clipboard`、`navigator.serviceWorker` 都是 undefined（`crypto.getRandomValues`、`document.execCommand` 仍可用）。
前端生产代码现算（剔注释后的启发式扫描，测试文件除外）：

- `crypto.randomUUID()` 调用点 130 个（96 个文件），调用前没有存在性判断的 52 个（19 个文件）：G4~G7 底稿组合函数与组件的增行、
  装载缺 id 的行，F4 审定表迁移旧行，复核对话 `useReviewDialog.sendMessage` ⇒ 内网 http 下抛 TypeError。
  另 `services/generationOperationStore.newGenerationOperationId` 判断后直接报错「当前浏览器不支持安全生成 operation id」⇒ 生成底稿弹窗不能用。
- `navigator.clipboard` 调用点 39 个（26 个文件），文件里没有 `execCommand('copy')` 回退的 38 个（25 个文件）⇒ 复制失败；
  试算表、附注编辑器、自定义查询三处在 catch 里调 `navigator.clipboard?.writeText` 后照样提示「已复制」，实际什么都没复制。
- `crypto.subtle` 只有 `sync/canonicalJson.canonicalDigest`，生产代码没有调用方；`navigator.locks` 只有 `crossWindowAuth.singleFlightRefresh`（已判断）。

本 spec 只修了窗口编号（`clientInstance.ts`，D1b）。两条出路：逐处改用 `newUuid` / 加复制回退（改 40 余个文件），或内网部署改 https
（浏览器变安全上下文，上述全部恢复，但要证书，OnlyOffice 回调地址也要跟着改）。
