# 双向回写提速后遗留问题收口 — Design

## §1 现状（2026-10-23 现读 / 现查确认）

### P1 / P2 文档 key 复用

- 每个「forcesave 之后关闭」的会话都会收到 status 2（`notmodified=true`，恒无 userdata）。生成 close-capture 的只有走 close intent 的离开；`leaveWithoutSaving()` 与强关标签都不走 ⇒ `plan_correlation` 判 `frozen_identity` ⇒ durable 后 `_unique_frozen_identity_application` 找不到同 sha 的 application（文档服务器重新组装，字节不同）⇒ recovery case `ambiguous_close`，回 `error 0`。库里 09-10 以来 140 条未认领；room 58a6484f 上每个 status 6 后面都跟一个这样的 status 2。
- 回 `error 0` 后文档服务器认定该 key 已保存。按 OnlyOffice 约定，之后用同一个 key 打开即「版本已更改」（`onOutdatedVersion` / `onRequestRefreshFile`，未声明时弹框并按原配置重载 ⇒ 载入 room 物化时的旧字节）。
- 平台没有任何代码把 room 置 `closed` / 写 `closed_at`；契约 `callback_statuses[].room_transition`（status 2 / 4 = `closing_to_closed`）无人消费。`RoomService.open_or_reuse_room` 对 `opening/active/close_barrier` 一律复用同代 key。
- 换代路径已存在：`materialize_coordinator._open_room_and_descriptor` 捕获 `RoomNotWritableError` 且 `room_generation_is_retired`（superseded / closed）⇒ `_rotate_generation_for_stale_room`（同 content version、同 artifact、新 generation）。`ROOM_EDGES` 允许 `opening/active/close_barrier/closing/refresh_required → closed`，`recovery_required` 只能到 `superseded`。
- 关闭后的写入路径：`content_mutation._advance_room` 在 `requires_refresh` 时 `assert_transition(room → refresh_required)`、`RoomService.settle_client_baseline` 不等值时 `_mark_refresh_required_locked` 并由协调器 `supersede_room` ⇒ 对 `closed`（以及已 `superseded`）的 room 都是非法边，apply 会在最后一步失败。
- 前端：`WorkpaperSyncEditorHost.vue` 只接了 `onDocumentReady` / `onDocumentStateChange` / `onError`（事件接口 `workpaperSyncEditorHostRuntime.ts`）；遮罩 `v-if="!editing"`、`position:absolute; inset:0; z-index:10`、无 `pointer-events:none` ⇒ 文档服务器弹框被挡。

### P14 apply 中断

- `repository.lock_room_oo_apply` 是会话级 `pg_advisory_lock`，临界区内至少两次 commit；`AsyncSession` 每次 commit 归还连接，`finally` 里的 unlock 可能落在另一条连接上（返回 false，锁留在池里的空闲连接上）。现查 `pg_locks` 无残留，属潜在缺陷。
- 无重驱：`startup_registry._WORKER_BINDINGS` 里没有相关 worker；`apply_durable_incoming` 对 `APPLY_ADMISSIBLE_APPLICATION_STATES` 可重入。
- 重发已应用的回调 ⇒ `ReapplyForbiddenError` 未捕获 ⇒ 500。注册失败分支（`wp_sync_router._apply_durable_incoming`）只打日志。
- 前端超时 180 s 后 `showPlainRetry` 依赖 `retryableOperation`，operation 尚未落 error 时没有任何入口。

### P4 / P6 事件循环

- 预热是事件循环上的 asyncio Task（`startup_prewarm.warm_workpaper_sync_registry`）。最重一段：`assert_contract_file_matches_source → template_definition_payload → normalized_structure_hash → structure_fingerprint`（整簿 openpyxl），LRU 只有 16 而模板 58+ ⇒ 次次未命中。
- `entry_profile.load_entry_manifest` 的 `lru_cache` 被注释，每次（含每个同步请求）重解析 1.27 MB；`SyncContract.canonical_sha256` 每次访问重算。
- `_apply_durable_incoming` 缓存未命中时自己内联冷建：不拿 `_registration_build_lock`、不写 `_REGISTRATION_CACHE`。
- 轮询：`workpaperSyncOperationTracker.ts` `setInterval` 500 ms、无在途保护；`utils/http.ts` 对 5xx 自动重试两次；`GET operation` → `_services` → `build_production_registry` → 解析 manifest。

### P5 address-registry

- 路由只校验登录、`limit ≤ 50000`；序列化（`jsonable_encoder` + `ResponseWrapperMiddleware` 再 `json.loads/dumps` + gzip）在事件循环上；底稿域 `_build_custom_wp_cell_entries` 读全部 `parsed_data` 且逐底稿 `register_custom`；附注模板 950 KB、`wp_account_mapping` 300 KB 等静态 JSON 每次重读。
- 🔴 路由 / service / 前端 store 三个文件有并发会话未提交的改动（截断回报 `total/returned/truncated`、前端整库加载上限 5000→50000）。本 spec 只改不重叠的代码块，暂存时按块挑。

### P15 / P16

- `callback_download._open_first_reachable` 每次先试 `::1` 再试 `127.0.0.1`。
- `disclosure_payload_builder_service.build_and_sync` 传 `User(id=UUID(int=0))`、`wp_id=UUID(int=0)`、`commit=False`；`refresh_note_section` 的 `SELECT … FOR UPDATE` 触发 autoflush，挂起的 `disclosure_notes.updated_by` UPDATE 撞外键。检查表保存发 `WORKPAPER_SAVED` 不带 `user_id`。

## §2 设计

- **D1（R1）** 新增 `RoomService.close_after_docserver_saved(room_id, reason)`：锁 room；`superseded/closed/recovery_required` 原样返回；否则 `assert_transition(→closed)`、写 `closed_at` / `refresh_reason`。路由在 `handle_callback` 返回 `response_error == 0` 且 `status == 2` 且 delivery 已 durable 时，于 apply 之后调用并 commit（apply 失败也关：key 已被文档服务器作废，重试走已有的 operation 入口）。status 4 不关：文档服务器未保存该 key，复用不触发版本过期，换代反而让下次打开多一次转换。
- **D2（R1.5）** `RETIRED_ROOM_STATES` 的 room 上：`_advance_room` 只推进 `last_applied_version_id`，不转 refresh；`settle_client_baseline` 返回 `BaselineSettlement(advanced=False, refresh_required=False, reason="room_retired")`，协调器据此不再 supersede。`requires_client_refresh` 与 application 终态照旧。
- **D3（R2）** 遮罩分两态：`descriptor_mounted` 用 `pointer-events:none` 的顶部状态条；确认中 / 失败态保持整块拦截。编辑器事件新增 `onRequestRefreshFile` / `onOutdatedVersion` ⇒ `failHost('editor_runtime', 'editor_document_outdated', …)` + 中文提示，不在宿主内自动离开重进（模式切换归页面所有）。
- **D4（R3.1）实施后定稿**：锁持在一条专用连接上（`engine.connect()`）：加锁后 commit（会话级锁不随事务结束，持锁期间连接不挂未结束的事务）；解锁在同一条连接上，之后 commit + close；任一步失败 `invalidate()`（真断开 ⇒ 数据库释放会话级锁）；同一 repository 内按 room 计重入深度；非 PG 不加锁。守卫：PG 5 例（加解锁同一 backend pid、会话中途 commit 换连接后仍解得开、失败作废连接、重入、无残留），变异 R31a~e 全杀（e 为死锁超时）。
- **D5（R3.2~3.5）实施后定稿**：
  - 重发回调（R3.3）：`ReapplyForbiddenError` / `ApplicationTerminalStaleError` ⇒ rollback + info 日志，回调回 0，照常关闭 room。
  - 协调器接手前的失败（R3.4）：注册 / 绑定失败与入口异常 ⇒ `callback_apply_failure.record_pre_apply_failure`：application 与 operation 都按既有状态边进 `error`，事件与 operation 行带错误码、阶段（`registry` / `pre_apply`）、详情；终态不动。记录本身失败只打日志，兜底 rollback 也不让异常冒出（冒出即 500 ⇒ 文档服务器重投）。
  - 重驱（R3.2）：候选 = application 状态 ∈ 协调器准入集合去掉 `error` / `conflict`（由 `APPLY_ADMISSIBLE_APPLICATION_STATES` 推出，不另写名单）、**最近一次 application 事件**早于 5 分钟、按建行时间先后取一条。worker `oo_apply_redrive_worker`：每 60 s 选主（ttl 120 s）、一轮一条、写心跳，调路由同一入口 `_apply_durable_incoming(attempt=2)`，失败由那条路径记到 operation 上，application 随即离开候选集。偏离原稿：`updated_at` 判据不成立（application 表没有这一列，事件才是推进的事实；只看建行时间会误判仍在推进的长 apply）；`durable_at IS NOT NULL` 冗余（唯一建行点同时写入），已去掉。真库现有 0 条中断 apply。
  - 前端（R3.5）：超时后出现「刷新状态」，只读取快照、显示中文说明，不喂回 sticky error 的桥（状态机在 error 上不收 `operation_observed`）；快照为 `error` 且已关联回写任务（applicationId 非空）才出现「重试回写」，重试后再读一次显示结果。超时文案改为点名「刷新状态」（原文案点名的「重试回写」此刻并不渲染）。追踪中直接读到这类失败（R3.4 记下的）也给重试入口：桥对 post-durable 失败记的是不可重试裁决（422），宿主按快照判。
  - 守卫：单测 + PG S22 / S23（宿主 `test_task26_oo_to_html_pg.py` 贴行数门，场景体放 world 文件）；变异 R33a~c、R34a~m、R32a~p 全杀；前端 vitest 14 例 + 变异 F1~F15。
- **D6（R4）实测后定稿**（重药安徽真库跑两段预热，旁挂 50 ms 心跳记循环停顿；包装函数按线程记耗时）：
  - 改前：注册段 46.0 s、循环停顿合计 19.9 s、最长 3.23 s；基线段 27.5 s、停顿 12.3 s、最长 3.33 s。停顿主因是 `normalized_structure_hash` 在事件循环上整册解析模板（94 次全在主线程，合计 19.4 s；36 份不同模板，结构指纹 LRU 16 份 ⇒ 第二轮全部重算）；`load_entry_manifest` 143 次 1.2 s；`canonical_digest` 588 次 0.03 s（`canonical_sha256` 记忆化**不做**，收益可忽略）。
  - 改法：①`normalized_structure_hash` 按字节摘要记忆化（只存 64 字符，上限 512，失败不入缓存，加锁；记忆本体在新模块 `structure_hash_memo.py`，`excel_instrumentation.py` 只净增 6 行委派 —— 该文件 HEAD 已 2639 行、超行数门，基线 2200 是 e7f942ff2 +473 行未登记留下的，白名单按实测值 2645 重登记并写拆分方向；被 sha256 钉死的 `excel_structure_fingerprint.py` 未动）；②冷建在 attach 之前经 `asyncio.to_thread` 按同一组 provider（有 entry_state 的 entry + 四条 pilot，capability 未放开的跳过）先算模板结构 hash（`registration_template_warmup.py`，预热失败一律交原调用点）；③`load_entry_manifest` 按 `(路径, mtime_ns, size)` 缓存，`cache_clear()` 真生效；④`_apply_durable_incoming` 改调共享入口 `_attach_pilot_adapters`（拿冷建锁、写缓存、四条 pilot 逐条隔离）。
  - 改后：注册段 47.2 s、停顿 13.1 s、**最长 0.56 s**；基线段 22.2 s、停顿 6.3 s、**最长 0.48 s**；主线程上结构指纹 / openpyxl 解析 0 次，清册解析 143 次 0.02 s。剩余停顿是工作线程算模板时的 GIL 争用（单次 ≤ 0.6 s）。
- **D7（R6）实施后定稿**：
  - tracker 改自调度：上一轮读回来才排下一轮（`setTimeout`），不再 `setInterval`；`refresh()` 单飞，飞行中到期的定时轮询、内容事件、重连补读都合并成读回来后的一次补读；连续失败按 2 的幂退避、封顶 5 s，成功即回到基准间隔；窗口超时照旧在每次读之前判（退避中最多晚一个间隔）。
  - 不新增 `_noRetry`：`utils/http` 现有的 `_silent` 已经同时跳过全局提示与 5xx 自动重发两次，而 operation 读取的失败全由调用方处理（桥 fail-visible、轮询退避 + 窗口超时），符合「调用方自管错误提示必带 `_silent`」的约定 ⇒ `getOperation` 一律带 `_silent`。
  - 后端不改：`GET operation` 开发服务器实测中位 17 ms、p90 23 ms（30 次）；每次请求建的空注册在 R4 的清册缓存之后只要 0.3 ms，不再解析清册。
  - 浏览器实测（隔离上下文，前端真实 tracker + 真实 http）：不存在的 operation（404）13 s 内只发 5 次，间隔 0.5 → 2 → 4 → 5 s，无全局提示（改前按 500 ms 每次都发、每次都弹）；已落地的 operation 每轮在上一轮结束后才发，无重叠。
- **D8（R5）实测后定稿**（重药安徽 2025：6.98 万条地址，整库加载返回 5 万条 / 27.6 MB；开发服务器 + `/livez` 心跳，进程内探针 50 ms 心跳 + `gc.callbacks`）：
  - 改前：热请求 1.23 s、事件循环最长停顿 1.13 s；冷（缓存失效后）3.09 s、2.10 s。构成：`jsonable_encoder` 逐值递归 0.75 s；GZip level 9 压 27.6 MB 0.35 s；Redis 二级缓存整包 `asdict + dumps` 0.7 s、`loads + 构造` 0.4 s（C 层整包调用一直持 GIL）；辅助余额 5.6 万条逐行构建 0.3 s；全量 GC 一次 0.9~1.0 s（冷路径、Redis 命中路径各触发一次）。`ResponseWrapperMiddleware` 对 > 5 MB 的响应本来就不包信封（也不重编码），所以这个项目上「整包重编码」不是成本，中小项目（≤ 5 MB）才是。
  - 静态 JSON 与自定义底稿 N+1 实测可忽略 ⇒ **不做**（R5.1 这两项按实测撤回）：进程热态下附注 0.06 s、底稿 0.09 s；全库 24 个项目里 `register_custom` 最多 3 次（≤ 50 条）。
  - 改法：①`app/core/offloop_json.py`：分块编码（每块 2000 条，与 `json.dumps` 字节逐一相同；枚举 / 集合同 `jsonable_encoder` 口径）+ 预编码响应（内部标记头 `x-gt-preencoded-payload`）；②路由在工作线程里编码、直接返回字节，不经 `jsonable_encoder`；③`ResponseWrapperMiddleware` 认标记按字节拼信封，不解析，> 5 MB 也包（原先 > 5 MB 不包，前端 `http` 拦截器两种都能解）；④`OffloadingGZipMiddleware`：上游会压的每一段 ≥ 256 KB 都在工作线程里压（zlib 压缩释放 GIL）；⑤Redis 值改逐行分块，编解码进工作线程，旧格式（整包一个数组）就是只有一行、照常读，旧代码读新格式解析失败按缓存未命中重建；⑥辅助余额逐行构建进工作线程。
  - 改后：热 0.56~0.61 s、最长停顿 0.09~0.10 s；冷 1.4~1.6 s、0.37~0.42 s，偶发 1.36 s（全量 GC，归 R9 的 P12）。
  - 🔴 第一版 gzip 只接管「首段即全部」的整段响应，单测全绿、生产上没生效（实测仍停 0.37 s）：生产栈里 GZip 与 `ResponseWrapperMiddleware` 之间还有 `ObservabilityMiddleware`（`BaseHTTPMiddleware`），它把响应改成流式（数据段 `more_body=True` + 末尾空段），而单测栈里 GZip 直接包路由、只见到整段。守卫测试栈补了一层同形的透传 `BaseHTTPMiddleware`，并断言「整段载荷在工作线程里压、只剩末尾空段在事件循环上」。
- **D9（R7）实施后定稿**：
  - 回调下载：已验证地址间的回退由并发会话在 `_open_first_reachable` 实现（本机先连 `[::1]` 立即失败，实测 0.1~17 ms；IPv6 被静默丢弃的网络要等满契约的 5 s 连接超时）。本 spec 只加 `callback_download_address_hint`：下载成功后记 (host, port) → 连通地址，下次排到首位；只在它属于本次已验证集合时生效（DNS rebinding / allowlist / 私网判据不变）；有界 64、线程安全；只接在生产入口 `download_to_staging`，直接调 `stream_download` 的回退用例不受进程内状态影响。
  - 附注刷新根因：底稿保存的 `WORKPAPER_SAVED`（全部发布方）都不带 `user_id` ⇒ `build_and_sync` 拿 `User(id=UUID(int=0))` 写 `disclosure_notes.updated_by`（真库该表唯一的用户外键）⇒ 下一条查询 autoflush 撞外键 ⇒ 整次刷新失败。修：无触发人记 NULL（系统重算）；来源底稿取 builder 读的那张（(项目, wp_code) 至多一张）；builder 全部读写放进 SAVEPOINT，跳过与失败都回滚到保存点（flush 失败后保存点已失活但仍须显式 rollback —— 守卫实测抓到「只在 is_active 时回滚」会留下 PendingRollbackError）；handler 的 user_id 解析改为容错（原先坏值在 try 之外直接抛），builder 失败升为 warning；核对表保存与编排器（四条保存路径）的事件补 `user_id`。守卫：PG 8 例（外键只有 PG 有）+ 单测；变异 R71a~e、R72a~h 全杀。
  - 未改：手动端点 `refresh-from-disclosure` 从不 commit（前端零调用方），记为范围外发现。
- **D10（R8）已坐实**：根因是浏览器对同一主机的 HTTP/1.1 并发连接上限（6，按浏览器算、所有标签页共享）被项目事件流占满。前端每个项目页标签各持一条永不结束的 `/events/stream`（`projectEventStream`）；开发 Vite :3030 与生产 nginx `listen 80` 都是 HTTP/1.1。实测（隔离浏览器上下文）：6 条流在开时 `/api/health` 8 s 仍未发出，断开一条后立即返回。真栈 10:02 的表格保存就是排在浏览器里，10:07:06 开发服务器重载把所有流断开才发出，排进监听队列，10:07:25 被新 worker 处理。
  - 修法：同用户同项目的多个标签页共用一条流（`projectEventStreamShare.ts`：Web Locks 选领导标签页建连接，BroadcastChannel 转发事件；领导关闭后排队的标签页接手，连上即按断线重连通知各标签页恢复；键含用户 id，token 在 sessionStorage、标签页可能登录不同用户；不支持时退回每页一条）。
  - 被推翻的假设：「SSE 长连接让重载等不完」—— 最小复现（uvicorn 0.44 + 9 层 BaseHTTPMiddleware + GZip）重载 0.8 s 完成，uvicorn 关闭时给流式响应发 `http.disconnect`，流被取消。
  - 残留：同时开 6 个以上**不同项目**的标签页仍会占满（每项目一条）。根治是生产 nginx 上 HTTP/2（需 TLS），属部署决策，交用户。
- **D11（R9）实测后定稿**（重放探针：同一进程里用回调同一入口 `_apply_durable_incoming(attempt=2)` 重放重药安徽 D2 的一条真实 apply（application 4b85b961），外层事务回滚、文件根换临时副本、事件截成空操作，真实存储前后核对不变；`gc.callbacks` 记每代停顿）：
  - P7 归因：10-23 线上三次 apply（同一张底稿）10.81 / 10.33 / 8.12 s，阶段之间此消彼长（合并 1.84 / 0.55 / 0.52 s，base 提取 1.06 / 2.38 / 1.82 s），不是线上固定多出某一步。安静进程重放、默认 GC：稳态 8.0~8.1 s，与服务器空闲时那次线上（11:59，8.12 s）相同，其中循环 GC 2.13 s（gen2 1.93 s）。多出的 2~3 s 来自同进程别的请求：当时并发会话连发 `GET /api/address-registry`，每次占住事件循环 1~4 s 并与 apply 的工作线程抢 GIL（R5 已修），加上更大堆上的全量 GC（P12）。
  - P12 GC：新 `app/core/gc_tuning.py`，接在既有预热步骤里（不新增启动任务，启动顺序是钉死的契约）：冷建之前 gen0 阈值 700 → 10000；预热结束（成功或失败）先 `gc.collect()` 再 `gc.freeze()`；关闭阶段的取消不冻结；`GT_GC_TUNING=0` 关闭。重放实测（每次合并摘要与新内容版本摘要都是 `43956dd03c8c`、revision 29）：

    | 配置 | 冷注册那一轮 | 稳态 apply | 每次 apply 的 GC | gen2 单次最长 |
    |---|---|---|---|---|
    | 默认 | 48.0 s（gen2 14.4 s） | 8.0~8.1 s | 2.13 s | 0.23 s |
    | 只 freeze | — | 6.3~6.5 s | — | 0.05 s |
    | 只抬阈值 | — | 5.95~6.1 s | — | 0.32 s，随堆增长 |
    | 抬阈值 + 预热后 freeze（采用） | 37.8 s（gen2 4.0 s） | 5.97~5.99 s；另一时段复测 6.45~6.56 s | 0.31~0.43 s | 0.10~0.15 s |

    线上（开发服务器重载后）：冻结 212 万个对象（那次 `collect` 回收 6.4 万个、停约 1 s）；冷注册预热约 42 → 36.0~36.8 s，基线预热约 19 → 16.8~17.1 s；address-registry 热 0.58~0.61 s、最长停顿 0.09~0.12 s，冷 1.30~1.38 s、0.33~0.36 s（不再出现 1.36 s 的全量 GC 停顿）。改动之后线上还没有发生过 apply（日志截至 10-24 02:03），apply 的前后对比以重放为准。代价：冻结时仍存活的对象以后不参与循环回收（它们本是进程寿命的缓存，引用计数照常释放）。被否：只抬阈值（gen2 单次停顿随堆增长）、只 freeze、定期再 freeze（会冻住垃圾）、在 `main.py` import 时设（每个测试进程都受影响）。
  - P11 首发：`publish_first_generation` 的「读 substrate + 提取 + 叠加 store」改 `asyncio.to_thread`（该函数不碰会话；adapter 是本次请求新建的，等待期间事件循环不碰它）；暂存、物化、instrumentation 原本就在工作线程。PG 首发夹具（scratch schema，H1 三次、D2 一次）实测：改前事件循环被整段占住 0.19~0.37 s；改后在工作线程，事件循环最长停顿 0.03~0.19 s（GIL 争用）；projection 摘要前后相同（H1 `4d9779c61b57c834`，D2 `8986c979ebf764e6`）。
  - P8 / P9 **未实施，交用户拍板**。重放稳态各阶段：base 提取 0.78~0.87 s、current 0.75~0.79 s、incoming 0.68~0.69 s、合并 0.51 s、CPU 段 3.03~3.10 s。
    - P8（物化计划阶段把 incoming 再提 4 次）：cProfile 2.24 s，去掉剖析开销约 0.8 s；前提是证明 baseline 只影响受保护格判定。
    - P9（跨请求 base 投影缓存）：同一 OO 会话连续保存时省 base 提取约 0.8 s（current 与 base 是同一份时 cpu-hotspots ⑤ 已复用）；代价是进程内每份投影约 2 万键、多 worker 命中率低；前提是证明发布时反读的结果与下一次 base 提取对同一产物相同（cpu-hotspots §8 记过：按 sha 复用会因按路径判形态而得出不同结果）。
    - 两项都要改并发会话已暂存、未提交的 `excel_materialize.py` / `oo_to_html.py` / `adapters/excel.py`；`workpaper-sync-save-path-cpu-hotspots` §6 把它们列为后续可选。建议：若还嫌慢先做 P8（收益集中在一个函数、无内存代价），P9 暂不做。
  - 守卫：`test_gc_tuning.py` 7 例（阈值只抬 gen0、冻结前先回收、预热失败也冻结并原样抛出、关闭取消不冻结、开关、启动接线）+ AST `test_first_publication_offloop.py`；磁盘变异 G1~G7、P11a 全杀（逐条核对红在预期用例上）；32 个相关测试文件前后对比零新增失败，修好 1 条（`test_task75_published_identity_observer` 的接线判据，R4 改的）。
- **D12（R10）评估，不实施**：
  - 用户感知：现在点「保存并回到表单模式」到表单出现新值约 8~9 s（forcesave 0.3 s + 文档服务器组装与回调下载约 2 s + apply 约 6 s + 重载 0.2 s）。先回表单可在 incoming 落盘后约 2.5 s 回到表单，但新值出现的时间不变：中间约 6 s 该底稿表单只读、显示旧值和「正在合并在线编辑内容」。省下的是「离开编辑器」的等待，不是「看到结果」的等待。
  - 改动范围：后端一条迁移（participant 记延迟离开）、离开端点的延迟模式（现在 request 为 `correlated` 时离开回 409，`rooms._OPEN_REQUEST_STATES`）、application 终态结算同事务执行延迟离开（锁序 room → request → participant）；前端桥新增「待合并」态，operation 追踪要从宿主挪到桥或页面（现在故意放在宿主、随宿主卸载停掉，回表单正是卸载宿主），挂载 `WorkpaperSyncEditorHost` 的 108 个 `.vue` 文件经 `useWorkpaperEntryDualMode`（31 处）、`useGRenderModeSwitch`（18 处）与直接用桥的组件补只读绑定，加横幅组件。
  - 交互代价：合并期间表单必须只读（否则 HTML 编辑与 apply 撞 CAS ⇒ 落 conflict）；conflict / error 要在表单模式下给出路（现在只在编辑器宿主里有）；合并中再进在线编辑、关页、多标签页都要定规则；apply 中断时由 R3.2 的重驱补完（约 5~6 分钟），这段时间表单一直是旧值。
  - 建议：本轮不做。apply 已降到约 6 s，P10 的收益小于它带来的新状态与 108 个宿主接线；还嫌慢时先做 P8。

## §3 拒绝方案

- 打开时检查「key 已被保存」再决定换代（派生死状态、room 仍是 active，两处判据会漂）。
- status 2 `notmodified` 不下载直接 no_content（契约明文禁止）。
- 宿主收到版本过期后自动离开重进（绕过页面的模式切换与 dirty 判据）。
- 放大结构指纹 LRU（每簿一份 openpyxl 结构，内存不可控）；调大数据库连接池（掩盖堆积）。

## §4 守卫

- R1：纯函数 / PG 真栈各一组 —— status 2 durable ⇒ room closed、下一次物化 doc key 变、内容 = 当前版本；status 2 被拒 / status 4 ⇒ room 不变；closed room 上 retry 成功。变异：去掉关闭调用、关闭放到 apply 之前、对 status 4 也关，各自打红。
- R2：vitest —— `descriptor_mounted` 遮罩 `pointer-events:none`、确认中拦截；两个事件触发可见失败与中文文案。
- R3：PG —— 锁与解锁的 `pg_backend_pid()` 相同、apply 后 `pg_locks` 无 advisory 残留；重驱 worker 把卡住的 application 推到终态；重发回调回 0。
- R4~R6：缓存命中计数与等价对拍（同输入同输出）；事件循环停顿探针前后对比。
- 全部：相关套件 HEAD 对比零新增失败、golden digest 不变、行数门过；浏览器实测后还原测试编辑。
