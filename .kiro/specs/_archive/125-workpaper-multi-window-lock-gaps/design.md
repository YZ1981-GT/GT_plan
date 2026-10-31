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

## 6 第二轮设计（R3~R5，2026-10-31）

### 6.1 后端：写接口默认校验编辑锁（R3.1 / R3.6）

- D7 范围单一来源 `routers/_wp_edit_lock_scope.py`：规则表 `(类别, 路由模板正则, 理由)`，`edit_lock_scope(route_path)` 取第一条命中的类别，
  没命中 = 校验。类别：校验 / 不写底稿 / 协作与流程 / 锁管理 / 计算后可选写回。`dedicated_wp_gate` 可见性通过后对非读请求按类别处理：
  校验 ⇒ 当场按 R2.3~R2.5 判；其余放行。第一轮的 `is_content_write_route` 改为「类别 = 校验」，保留函数名。
  - 否决「列出写接口、其余放行」：第一轮就是这么漏的（`save-adjudication`、OCR、证据、公式、Univer 保存都不在名单里）；新加的写接口默认要校验。
  - 否决「只按末段判豁免」带来的风险由守卫兜住：豁免为「不写底稿」的路由逐条做静态检查（处理函数与同模块被调函数里有
    `commit` / `flush` / `add` / 裸 SQL 写 / 给 `parsed_data` 赋值 / `commit_bytes` / `write_bytes` 即红），登记过理由的非内容写除外
    （导出时记导出快照、AI 草稿留痕）。
- D8 计算后可选写回：门对非读请求把请求人（用户 + 窗口编号 + 底稿 id）放进 `ContextVar`；18 个 `_maybe_apply_*` 在
  「`apply_to_sheet` 为空就返回」之后调 `enforce_edit_lock_at_write_point(db, wp_id)`。没放过请求人（不经门调用）或底稿对不上 ⇒ 不判，
  守卫保证这些路由都经门。否决「门里解析请求体」：门不该认识各路由的请求模型。
- D9 不经门的写接口显式调用（R3.2）：版本回滚、程序行 not-applicable / restore、解除附件关联、H5 导入、A17-7 从 B3 导入、附件关联到底稿，
  处理函数加 `request: Request`，权限校验之后、写之前调 `enforce_edit_lock_for_content_write`。不经门的 `{wp_id}` 写路由在范围模块里
  逐条登记「校验 / 不校验 + 理由」，守卫要求新增的必须登记、登记为校验的处理函数里真有这次调用。
- D10 在线编辑平台（R3.3）：`wp_sync_router` 的六个入口在 `_guard` 之后（`_guard` 必须是第一句 await，既有守卫钉住）调同一判定，
  提示「…当前为只读，不能进入在线编辑。」。房间参与者只按编辑身份加入（`_join_or_reuse_participant`），没有只读进房间的路，
  所以挡在入口；会话内操作不挡，挡了已开的会话收不了尾。前端桥把 423 的 detail 原样显示在状态条（纯字符串 detail 走「本地 / 传输」分桶，
  不可重试）。
- D11 旧版按 sheet 取 OnlyOffice 配置（R3.4）：模式已判为编辑时再查 `find_blocking_lock`，挡住 ⇒ `mode = "view"`、`permissions.edit = False`，
  不占编辑席位。前端 `http.ts` 给 `/onlyoffice-config` 的 GET 也带窗口编号（同人他窗要靠它分辨）。

### 6.2 前端：只读不自动写（R3.5）

- `WorkpaperEditor` 数据刷新事件触发的 `template-file/init` 在 `effectiveCanEdit` 为假时跳过（原先非静默，只读窗口每次刷新事件弹一次 423）。
- A171 / A176 / A177 切在线编辑时的 `generate-docx`、切回时的 `sync-from-docx` 只读时跳过（A171 补 `readonly` prop；A171 / A177 显示「当前为只读，不能进入在线编辑」）。
- `useF2StocktakeDualMode` 加 `readonly`：只读时不做 Word 双向同步，照常打开在线编辑（后端给只读配置）。
- `GtCustomWpEditor.refreshProjection` 只读时不发。

### 6.3 窗口编号（R4 / R5）

- D12 认领标记：`_generateAndStore` 同时写 `gt-client-instance-claimed = id`。`getClientInstanceId` 读到的编号没有对应标记 ⇒ 升级前的页面写的，换一次。
  否决「BroadcastChannel 问旧标签页」：旧代码不会回答；否决「升级后强制刷新」：会丢未保存的编辑。代价：升级后每个旧标签页第一次刷新换一次号
  （旧文档卸载时已按旧号释放编辑锁，新文档按新号取锁，不会把自己挤成只读）。
- D13 内网 http（不提供 Web Locks）：
  - 登记值改为 JSON `{n: 文档标识, t: 登记时间, f?: 1 冻结}`；第一轮的纯时间戳值按「别的文档的登记」读。
  - `getClientInstanceId` 同步决定：没有标记 / 有活着的 opener ⇒ 换号；登记里没有本编号或是本文档的 ⇒ 登记并定下；
    登记是别的文档的 ⇒ 暂用原编号、不登记，交给 `claimClientInstanceId`。
  - `claimClientInstanceId`：登记标了冻结 ⇒ 换号；否则在 `gt-client-instance-probe` 频道发 `{probe, id, from}`，等 1.5 秒：
    有 `{alive, id, to: 本文档}` ⇒ 换号；没有 ⇒ 认回。定下后登记、标记已定。浏览器不提供 BroadcastChannel ⇒ 换号（第一轮口径）。
  - 每个标签页（不提供 Web Locks 时）一开始就监听频道，问的是自己当前编号（且不是自己发的）就回答。
  - `pagehide` 只删本文档的登记；`freeze` / `resume` 改写冻结标记；`pageshow`（往返缓存恢复）重新登记。
  - 否决心跳时间戳（后台标签页定时器被压到约每分钟一次，阈值难定）、SharedWorker（内网 http 下照样可用但要多一个脚本与生命周期，问答够用）。
- D14 等认领：`isClientInstanceSettled()`；`http.ts` 请求拦截器对「要带窗口编号的请求」（非 GET、编辑锁、取 OnlyOffice 配置）在认领未定时
  先等认领再继续（其余 GET 不等）。安全上下文认领在几毫秒内定下；内网只有登记命中时最多等 1.5 秒。Web Locks 请求加 3 秒兜底超时，
  超时按「不可用」保留当前编号，避免写请求永远挂起。

### 6.4 风险与边界

- 行为变化：编制人持锁期间，复核人在程序表弹窗里「标记复核 / 批准」（写 `parsed_data.procedure_status`）、经理裁剪 / 恢复程序行、回滚版本，
  都会 423（与只读横幅「所有保存已禁用」一致）；复核意见、批注、复核状态、提交复核不受影响。
- 只读窗口里 OCR、AI 采纳、计算写回等按钮多数没禁用，点了后端 423、提示谁在编辑；本轮不逐个改按钮。
- 内网 http 下认领问答的漏判：被冻结却没收到 `freeze` 事件的标签页（非 Chrome）答不了询问 ⇒ 复制它会共用编号；
  另一个标签页主线程忙到 1.5 秒都没回答同理。
- `onlyoffice-callback`（文档服务回调）、WOPI PutFile 没有用户窗口，不校验；靠入口（物化 / 配置）不给只读窗口编辑会话。

### 6.5 涉及文件（第二轮）

后端：`routers/_wp_edit_lock_scope.py`（新）、`routers/_wp_gate.py`、18 个计算写回路由模块、`routers/version_trail.py`、`routers/procedure_trim.py`、
`routers/attachments.py`、`routers/h5_oil_gas_assets.py`、`routers/a17_summary.py`、`routers/wp_sync_router.py`、`routers/wp_onlyoffice_router.py`。
前端：`utils/clientInstance.ts`、`utils/http.ts`、`views/WorkpaperEditor.vue`、`GtA171AuditSummary.vue`、`GtA176ClosingMeeting.vue`、
`GtA177IndependenceDeclaration.vue`、`GtF2StocktakeBundle.vue` + `composables/useF2StocktakeDualMode.ts`、`GtCustomWpEditor.vue`。

## 7 第二轮范围外发现（未修，待用户定）

- `routers/review_prompt.py` 整个路由没有任何鉴权依赖（`APIRouter(tags=…)`，注册时也没加）：单底稿 AI 复核
  `POST /api/workpapers/{wp_id}/review`（读底稿内容发给模型、落复核结果）、批量复核、复核报告导出、改复核发现状态等 7 个端点。
  实测不带令牌 `GET /api/review-prompts/coverage` 返回 200，同时 `GET /api/projects` 返回 401。项目鉴权基线守卫只扫 `{project_id}`，
  这里用的是 `{pid}` / `{wp_id}`，扫不到。
- `WpPopupDocxEditor`（程序表里弹出的 A8 / A16 Word 子底稿）与 `WorkpaperWordEditor` 的 A16 路径前端自建未签名配置；容器开着浏览器令牌校验，
  这条路按理打不开编辑器，本轮没动。
- 路径不带 `{wp_id}`、底稿 id 在请求体里的写接口另有 51 条（批量预填、批量 / 离线导入、各类同步、抽样等），本轮只收编辑器内三条（D9）。
