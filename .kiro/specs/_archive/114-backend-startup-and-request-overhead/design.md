# 后端冷启动、热重载与每请求固定开销 — 设计

## 1. 实测与根因（2026-10-28，fastapi 0.135.3 / starlette 0.52.1 / pydantic 2.12.5 / uvicorn 0.44.0 + httptools）

探针放仓库外（`C:\Users\Administrator\bsr_probe\`），用完删除；复测同口径。

| 项 | 实测 | 根因 |
|---|---|---|
| 导入 `app.main` | 9.9~11.6 s（`-X importtime` 下 11.9 s：app.* 自耗时 9.9 s，第三方约 2 s） | `APIRoute.__init__` 5131 次 5.92 s（51%）：子路由 `@router.get` 构造一次，`include_router` 用相同参数再构造一次，每次都重做依赖分析（`get_dependant`）和 14907 个参数 / 响应模型的 `TypeAdapter`；`stale_propagation_engine` 导入时实例化并读图 0.76 s；`app.models` 0.67 s |
| 热重载 | 约 15 s 新请求卡在监听队列 | `BaseReload.restart`：Windows 下先发 CTRL_C 等旧 worker 退出，再 spawn 新 worker（导入约 10 s + 启动任务约 1 s）；监听 socket 在父进程，请求不报错、只是没人 accept |
| 中间件 | `/api/version` 进程内 0.79 ms；去掉 8 个 `BaseHTTPMiddleware` 0.14 ms；只留 FastAPI 自带的 0.11 ms | 每个 `BaseHTTPMiddleware` 为一次请求建内存流 + 任务组并把响应改成流式 |
| 路由匹配 | 未读数（第 2419 条）0.78 ms，项目详情（第 37 条）0.011 ms | Starlette `Router.app` 逐条 `route.matches`（正则） |
| 并发 | 进程内 30 个未读数并发一批 77 ms（顺序单次墙钟 6.2 ms，其中多数在等库） | 每个请求约 2.6 ms 事件循环时间，单事件循环上串行 |

## 2. R1 冷启动导入

### 2.1 推迟路由定义（`app/core/lazy_api_routes.py`）
- `LazyAPIRoute(APIRoute)`；`install_lazy_api_routes()` 在 `app/main.py` 顶部、导入任何路由模块之前调用：把 `APIRouter.__init__.__kwdefaults__["route_class"]` 换成 `LazyAPIRoute`。FastAPI 应用自己的 router 也走这个默认值；`include_router` 按 `route_class_override=type(route)` 复制，所以应用上的 2550 条都是它。
- 构造：在「推迟」标记（ContextVar）下调用 FastAPI 自己的 `APIRoute.__init__`。`fastapi.routing` 里这些重函数在安装时包一层，标记打开时返回占位、否则调原函数：`create_model_field`、`get_dependant`、`get_parameterless_sub_dependant`、`get_flat_dependant`、`_should_embed_body_fields`、`get_body_field`、`get_request_handler`、`request_response`。于是路径正则、方法、名称、`unique_id`、响应模型解析等轻属性仍由 FastAPI 自己算，不抄它的代码。跑完删掉 10 个重属性（`response_field`、`stream_item_field`、`response_fields`、`dependant`、`_flat_dependant`、`_embed_body_fields`、`body_field`、`is_sse_stream`、`is_json_stream`、`app`），记下构造参数。推迟构造抛任何异常 ⇒ 这一条退回立即构造。
- 物化：第一次读重属性时，`__getattr__` 用原参数在标记关闭下再跑一遍完整的 `APIRoute.__init__`，与立即构造逐行相同；物化中的 AttributeError 转成 RuntimeError（否则会被 `hasattr` 吞掉，表现成「没有这个属性」）。`include_router` 只读轻属性（已核对 0.135.3 源码第 1732~1800 行），子路由那一份永远不会物化。
- 约束：物化前路由对象的属性不得被改写（物化会按原参数重算）。现状核对：生产代码没有改写；测试里只有 `test_x3_adapter_host_same_module.py` 临时换 `route.endpoint`，期间只读 `path` / `endpoint`，不触发物化。
- 闸门：只在 FastAPI == 0.135.3 时启用，其他版本退回立即构造并告警；`GT_LAZY_ROUTES=0` 关闭。判据里钉住「当前版本下已启用」，升级 FastAPI 会先在这里红。

### 2.2 等价与错误暴露
- 等价判据（子进程分别以立即 / 推迟两种方式导入应用）：逐条路由比较属性键集合与轻属性值；物化后比较依赖调用链、参数名与类型、body / 响应字段注解；`app.openapi()` 的 JSON 逐字节相同；抽样请求（含 422、依赖覆盖 `dependency_overrides`）结果相同。
- 运行时核验：启动任务 `verify_lazy_routes`（best_effort，排在预热之后）启动 60 s 后开始，每 10 ms 物化 1 条，完成后把成功数与失败清单写进启动报告，失败另记 ERROR 日志。约 2550 × 2 ms ≈ 5 s 事件循环时间分散在约 30 s 里，单次停顿 ≤ 3 ms。

### 2.3 导入时重计算
- `stale_propagation_engine`：模块单例改为 `StalePropagationEngine(defer_load=True)`，构造时不读图；`_graph` / `_reverse_graph` / `_addr_id_index` / `_degraded` / `_loaded` 任一字段第一次被读到时（实例的 `__getattr__`），在临时实例里完整加载、再把本实例还没有的字段补上，只补一次。调用方不改（含直接读写 `_graph` 的 `unified_graph_builder` / `workpaper_trace_stale_integration`）。第一次加载与 `reload_graph` 用同一把可重入锁：并发第一次读只加载一次、读者看不到加载到一半的图。见 §7-1。
- 其余：推迟路由后重跑 importtime，自耗时 > 100 ms 且不是路由定义的逐个处理，结果写回 §7。

## 3. R2 热重载不中断

### 3.1 父进程（`backend/reload_supervisor.py`，不在 `app/` 下）
- `OverlapReload(ChangeReload)`；`run_uvicorn.py` 在调 `main()` 前把 `uvicorn.main.ChangeReload` 换成它（`GT_OVERLAP_RELOAD=0` 不换）。文件监听（`should_restart`）沿用，只改 `startup / restart / shutdown`。
- 子进程入口 `_WorkerTarget(server.run, ready, stop, primary)`（可 pickle；spawn 上下文的 Event）：把三个 Event 交给 `app.core.reload_handoff`；起监视线程：`server.started` 变真 ⇒ `ready.set()`；`stop` 置位 ⇒ 在事件循环里依次 `shutdown_state.start_draining()`、`await sse_registry.close_all()`、`server.should_exit = True`（uvicorn 优雅关闭：停止 accept、等进行中的请求、再跑 lifespan 关闭）。然后 `server.run(sockets=...)`。
- `startup`：起第一个子进程并立即置 `primary`。
- `restart`：起新子进程 → 等 `ready`；等待期间新进程退出 ⇒ 记失败、保留旧进程、返回（下次改动再试）→ 置旧进程 `stop` → 等它退出（`GT_RELOAD_STOP_TIMEOUT`，默认 30 s，超时 terminate）→ 置新进程 `primary`。新旧两个进程共用父进程的监听 socket，交接期间两边都能 accept。
- `shutdown`：置所有存活子进程 `stop`，等待，超时 terminate。Windows 下 Ctrl+C 本来就同时到达同一控制台的子进程。
- 状态文件 `GT_RELOAD_STATUS_FILE`（默认 `%TEMP%/gt_reload_status_<port>.json`）：最近一次重载的时间、结果、耗时、失败原因摘要；`/api/health` 读它放进 `reload` 字段。

### 3.2 应用侧：只能一个进程做的事
- `app/core/reload_handoff.py`：`mode()`（standalone / overlap / never：没有 supervisor 时 standalone；`GT_NEVER_PRIMARY=1` 时 never）、`is_primary()`、`async wait_primary()`（`asyncio.to_thread(event.wait)`）。
- `StartupTaskSpec` 加 `singleton: bool = False`。overlap 模式下被标记的任务不在启动时执行，报告状态记 `deferred`；一个后台任务等 `wait_primary()` 后按原顺序执行并回写报告。never 模式一直 `deferred`（detail 写原因）。standalone 模式行为与现在相同。
- 标记：`replay_startup_events`、`acnr_invalidation_outbox_start`、`recover_ai_chat_runs`、`acnr_catalog_snapshot_gc`、14 个 worker。其余（日志、事件处理器注册、ACNR epoch 订阅、缓存预热、各类校验）每个进程都要，照常执行。
- 任务名、顺序、关键性不变（`FROZEN_*` 不动），只新增字段与状态。

## 4. R3 每请求固定开销

### 4.1 纯 ASGI 中间件
- 共用 `app/middleware/_asgi.py` 的 `request_path(scope)`：只处理 `http`，其余直通；判定用的路径在 Host 头正常时与原 `request.url.path` 逐字相同（路径以 `/` 开头且不含 `? # \t \r \n` 时直接取 `scope["path"]`，否则照原口径用 `urlsplit` 重算），头按 Starlette `Headers` 取。见 §7-11。
- AppVersionHeader / RequestID / Observability：包 `send`，在 `http.response.start` 加头；Observability 计时保持「到响应头发出」（原 `call_next` 返回时响应头已就绪）。RequestID 在调下游前设置 contextvar。
- Inflight：计数覆盖到下游调用结束（响应体发完）。原实现在 `call_next` 返回时就递减（响应头就绪、响应体可能还在流），drain 时会少等正在流式输出的响应——有意改进，记 §7。
- RequestBodyLimit / LLMRateLimit：判定逻辑原样，命中时发与原 `JSONResponse` 相同的 413 / 429。
- ResponseWrapper / AuditLog：看到 `http.response.start` 时按原条件判定要不要包装 / 记录，不要的原样转发；要的缓冲到最后一段，再用与原版相同的 `Response(...)` 重建（头、content-length 由 Starlette 同一段代码处理）。ResponseWrapper 累积超过 5 MB 放弃包装，已缓冲的与之后的原样转发。AuditLog 先把响应发给客户端，再在同一次 ASGI 调用里写日志（进程内调用方仍是写完才返回，测试可见性不变）。与原版的差别见 §7-10。

### 4.2 路由索引（`app/core/route_index.py`）
- 每条路由的字面前缀：`path_format` 第一个 `{` 之前；没有参数的路由用全路径；`Mount` 用 `path + "/"`；其他类型（Host、未知子类）进全局表。
- 分表：静态全路径精确表、「前两个完整字面段」桶、「首个完整字面段」桶、全局表。一次请求的候选 = 各表命中的下标合并、排序（保持原顺序），逐个调 `route.matches`。FULL / PARTIAL（405）/ 尾斜杠重定向 / `default` 逻辑照抄 Starlette 0.52.1 `Router.app`（重定向那一轮也走索引）。正确性依据：路由正则以 `^` + 转义后的字面前缀开头，路径不以字面前缀开头就不可能匹配。
- `app.router.routes` 换成带版本号的列表子类，任何增删改使索引在下次请求时重建；整表被赋值替换时按对象身份重建。`register_all_routers(app)` 之后安装；`GT_ROUTE_INDEX=0` 关闭。
- 等价判据：对 2550 条路由的模板路径（参数填样例值）、加 / 去尾斜杠、错方法、随机路径，索引与线性扫描的匹配结果（路由对象、Match、child_scope）逐个相同。

## 5. 不做
- 多 worker 进程：事件总线的处理器与 SSE 队列都在进程内（`event_bus._sse_queues`），请求打到另一个进程时实时推送会丢；debounce 合并、渲染 memo / 注册缓存、进程内单飞锁都按单进程设计。要多进程需先做跨进程事件分发与缓存失效，另立 spec。
- 预热挪到接流量之前、响应体 JSON 解析再编码、`pool_pre_ping`：本次不动。

## 6. 风险与回退
- 三个开关可单独关闭：`GT_LAZY_ROUTES=0`、`GT_ROUTE_INDEX=0`、`GT_OVERLAP_RELOAD=0`。
- 共享开发服（9980）随 `app/` 改动热重载：新模块先写好并在独立进程里验证，最后一步才接入 `main.py`。R2 父进程代码在 `app/` 之外，重启 start-dev 后才生效；验证用另起的测试实例（端口 9981、`GT_NEVER_PRIMARY=1`、单独的重载触发目录，不碰主实例）。

## 7. 实施偏差（以代码为准）

1. stale 引擎改在实例上推迟，不用模块级 `__getattr__`：`event_handlers` 在注册函数里 `from … import stale_engine` 并被 8 个处理器闭包引用，模块级 `__getattr__` 会在注册那一刻就构造并读图；测试还会对实例字段 `monkeypatch.setattr(…, raising=False)` / `mock.patch`。语义按「导入时加载、之后再改」对齐：已有字段不覆盖；只补一次，之后缺字段照常 AttributeError —— `mock.patch` 是第一次访问时，退出时先删属性再用 `hasattr` 判断要不要放回原值，若再补一次会拿新加载的对象顶替原值。第一次加载约 0.11 s，发生在第一次 stale 传播或联动总线请求里（每个 worker 一次）。
2. 推迟路由后重跑 importtime（同一时段 2 次，`-X importtime`）：自耗时 > 100 ms 的 app 模块是 `wp_ai_stocktake` 310 ms、`_g5_long_term_receivable_import_export` 258 ms、`wp_formula_service` 174 ms —— 三个模块体里都没有重计算，是全量 GC 记在了恰好在执行的模块头上。GC 回调实测：导入期间 gen2 收集 8 次、合计 1.15~1.23 s、单次最长 0.33~0.37 s（约 83 万个长寿对象被反复扫）。处理：`app/main.py` 第一件事调用既有的 `gc_tuning.configure_gc()`（gen0 700 → 10000，`GT_GC_TUNING=0` 关闭；原来要到启动任务里才调），导入期间 gen2 收集 8 → 0。之后自耗时 > 100 ms 的只剩 `app.main` 本身 0.21~0.36 s（645 次 `include_router`，属路由定义，不处理）。
3. 旧 worker 交接退出顺序改为：停 accept（关本进程的监听句柄，之后的新连接都由新 worker 接）→ SSE 发 `server_draining` 并关闭 → 留 `ACCEPT_GRACE_S` 0.5 s → `should_exit`。§3.1 原写「draining → close_all → should_exit」：真实进程实测 4 次交接里 1 次 ConnectionResetError —— 刚 accept、请求还没读进来的连接，uvicorn 关闭时按空闲连接直接关掉。改后 13 + 3 次交接 0 失败。另：项目事件流原来只在 30 s 心跳时检查是否已关闭，`close_all` 后最长要等 30 s，改为关闭回调往队列放 None 立刻叫醒（`sse_registry.register_queue`）；AI 对话流（0.4 s 轮询）、导入进度流（2 s 轮询）本来就及时，未改。
4. 推迟执行的关键（critical）任务按 best_effort 记录、失败另记 ERROR：此时进程已在服务，不能再让启动失败；只能一个进程做的任务在交接后失败，与原来「启动时失败、整个后端起不来」相比是降级而不是更糟。
5. `GT_NEVER_PRIMARY=1` 不要求交接父进程：不带 `--reload` 起的测量实例同样不执行那 18 个任务。
6. 残留风险（未处理）：旧 worker 关闭空闲的 keep-alive 连接时，若客户端恰好在同一时刻往这条连接上发请求（Vite 代理到后端用 keep-alive），客户端会收到连接重置；窗口是一次往返时间量级。新 worker 接手后启动预热期间仍有 1 s 左右的事件循环停顿（实测最长 1.32 s，`platform-perf-hotspots` 任务 11 的遗留），未改。
7. 路由索引由 §4.2 的「精确表 / 前两段 / 首段 / 全局」四张表改为按路径段的前缀树：现算 `/api/projects/` 一个桶 927 条、`/api/workpapers/` 558 条，桶内仍要逐条正则，达不到 ≤ 0.05 ms。前缀树里整段字面走精确子节点、单段参数走通配子节点，遇到 path 转换器（25 条路由用到，如 `sync/entries/{entry_id:path}/store-projection`）或未知转换器之后不再对齐、从那一层起对任何后续路径都是候选；部分字面段（`v{n}`，现有 0 处）按通配。索引在安装时建好（约 12 ms），不让第一个请求付。
8. `startup_registry.py` 行数 935 → 991（`verify_lazy_routes` 与交接的执行器部分），`file_size_whitelist.txt` 基线同步上调并写明理由；交接逻辑本身在 `reload_handoff.py`，核验在 `lazy_api_routes.py`。
9. 未处理（不属于 R1.4「单个模块自耗时 > 100 ms」）：第三方库按调用方计的累计导入 —— openpyxl 321 ms（`batch_project_service`）、httpx 203 ms（`ai_service`）、redis.asyncio 190 ms（`rate_limiter`）、jieba 133 ms（`_zh_tokenize`）、pypinyin 94 ms（`global_search_service`）。改成函数内导入要动这些模块的全部调用点；五项累计 0.94 s 是收益上限（其中有别的库也会导入的部分），另议。
10. 纯 ASGI 中间件与原 `BaseHTTPMiddleware` 版本的有意差别。`test_middleware_pure_asgi.py` 拿 62 个请求的快照（原实现生成）逐项比较，只放过前两条；后四条由单独的判据与探针对照（原栈 = HEAD 干净检出）：
    - 小于 GZip `minimum_size`（1000 B）的响应不再压缩、不再带 `Vary: Accept-Encoding`：原来 GZip 内侧的 `BaseHTTPMiddleware` 把每个响应都改成流式（无 content-length），GZip 对流式响应一律压缩，`minimum_size` 不起作用。要保留原样就得强制流式，正是这次要去掉的开销。整段压缩的响应现在带 Content-Length（原来是分块传输）。
    - 无 content-length 的流式 JSON 超过 5 MB：原版只交出已读到的部分（6,228,891 B 的响应只交出 5,242,970 B，状态 200、JSON 被截断），现在完整转发。
    - 会被包装或记审计的 2xx JSON 流式响应输出到一半时抛异常：原来客户端收到 200 + 半截响应体，写操作还记一条审计日志；现在响应头还没发出，返回 500（统一错误信封）、不记审计。不缓冲的流式响应（如 text/plain）与原来相同：200 + 已发出的部分。
    - 审计日志在响应发给客户端之后写（原来写完日志才发响应）。
    - in-flight 计数覆盖到响应体发完（原来响应头就绪就减一，排空时会少等正在流式输出的响应）。
    - request_id：中间件与端点跑在同一个任务里，外层的请求日志（Observability）与 500 的错误日志也带上 request_id；原来每个 `BaseHTTPMiddleware` 把内层放进新任务，外层取到的是 `-`。代价：进程内直接调用应用（测试里的 `ASGITransport`）时，请求结束后调用方任务里仍是最后一个 request_id；uvicorn 每个请求一个任务，不受影响。
11. 判定用的路径 `request_path` 没有逐字照抄 `request.url.path`：原口径把 Host 头拼进 URL 再拆，畸形 Host 头会带偏中间件的判定 —— `Host: x?` 让路径变空（LLM 限流认不出端点、直接放行），`Host: x/api/health?` 让写操作的路径变成 `/api/health`（不记审计日志），`Host: [` 抛 ValueError（500）。现在重算时主机名固定，只保留路径本身带来的差别（编码过的 `?`、`#`、制表 / 换行）；Host 头正常时与原口径逐字相同（判据：17 种路径 × 5 种 Host 逐个比较）。路径不以 `/` 开头又含 `[` 时原口径抛异常，现在退回原始路径、交给路由（404）。

## 8. 重启后真实验收与复盘（2026-10-28）

### 8.1 真实运行结果

- 通过 `start-dev.bat` 完整重启后，`/api/health=healthy`，Redis connected，迁移 212 / 失败 0，`reload.mode=overlap`、`primary=true`、deferred=0；前端 3030 返回 200。
- API：admin 登录 / 登出成功；version、health、未读数、角色首页、项目详情、working-papers-all 均 200，非法 UUID 为 422；`X-Request-ID` / `X-App-Version` / `X-Response-Time` 正常，小 version 响应不 gzip；30 个未读数并发后 4 批中位 56.5 ms。
- 主实例真实 overlap：四轮交接 8.4~11.8 s，普通 GET 连续轮询均 0 失败、0 次 >3 s，单次最大 1.39 s。Playwright 真实登录、首页、项目页、底稿管理通过；当前请求均 200。

### 8.2 本轮真实浏览器抓到并修复的缺陷

1. **项目 SSE 收到 drain 后不重连**：后端已发 `server_draining`，但 fetch-based `createSSE` 遇到正常 EOF 直接返回。修为 `SSEOptions.reconnectOnCleanEnd` 显式 opt-in；只有无限的 `projectEventStream` 开启，有限 bulk / chain 进度流保持正常 EOF 即终态，避免反复重放完成事件。修复前浏览器只有 1 条流且 body 末尾是 drain；修复后两次交接形成连续 3 条流（两条 drain + 第三条新连接）。单测同时钉住 drain 立即重连、意外 EOF 退避重连、有限流默认不重连；旧实现套新测试 2/2 红。
2. **SSE 长期占用 PG 事务**：Playwright 项目流打开时 `pg_stat_activity.idle in transaction` 1→2，关标签页 2→1，最后语句是用户鉴权 SELECT。`get_current_user_sse` 与两个现有 SSE 路由的 `get_db` 改 `scope="function"`，在返回 `StreamingResponse` 前结束事务。生产依赖结构测试 2 例 + SSE 相关回归 20 例通过；热重载后项目流仍在线，PG 不再出现用户鉴权 idle transaction。

### 8.3 后续建议（本 spec 不继续扩范围）

- **P0 交接安全**：overlap 候选在停止旧 worker 前完成 lazy route 全量验证；父进程在 old drain 全程继续检查候选存活；critical singleton 增加 `primary_ready` / fencing 与失败状态，不能只记 ERROR 后仍报 reload ok。
- **P0 事件无损**：当前 EventBus / SSE queue 仍是进程内状态，旧进程已开始的写请求可能在 SSE 关闭后发布，新进程早到请求也可能发生在浏览器重连前。统一给 SSE 写 Redis message id，重连按 Last-Event-ID replay；短期至少分开统计 non-SSE in-flight，先等写请求结束再 drain 流，并建立所有 `text/event-stream` 路由的 registry inventory。
- **P1 重载耗时**：handoff 已等 `ACCEPT_GRACE_S=0.5`，进入 lifespan 后又无条件等 `PRE_DRAIN_DELAY=2`；仅 handoff 路径跳过第二次等待，普通 SIGTERM 保留，预计每轮直接少约 2 s。状态文件补 spawn→ready、ready→old-exit、old-exit→primary 分段，避免继续猜剩余 1.4~4.0 s。
- **P1 事件重放**：首次完整重启 `replay_startup_events=4787 ms`，后续为 20~167 ms。Redis `audit:events` 长度 8661，consumer group lag=0，但 pending 仍 264；当前只读 `>`，不会 reclaim PEL。用 `XAUTOCLAIM` / pending read 做有界恢复，并把重放移出 readiness、保留进度与失败报告。
- **P1 审计完整性**：纯 ASGI 审计先把成功响应发给客户端、再独立 commit 日志，进程崩溃或强杀存在成功但无粗粒度日志的窗口；改成业务事务内 durable outbox，或在最终 body 前完成持久化 enqueue，而不是恢复同步日志 DB 延迟。
- **P1 数据库**：现场仍为 shared_buffers=128 MB、effective_cache_size=4 GB、work_mem=32 MB、jit=off；pg_stat_statements 未加载，PG 容器约 730 MB / 宿主 93 GB，且没有运行 PgBouncer。安排受控 PG 重启，先设 shared_buffers=8 GB、启 pg_stat_statements 并按真实 top SQL 复测；`work_mem` 是每节点每并发预算，不再上调。6000 人目标在启用 PgBouncer并压测前不能宣称成立。
- **P2 ready 后尾延迟**：workpaper 预热末尾 full `gc.collect()+freeze()` 与 1.1~1.6 s 停顿吻合；改成无 in-flight 的空闲窗口或分批回收，并错开 singleton、预热和 lazy route 核验。不可用 `to_thread(gc.collect)`（仍持 GIL）。
- **P2 导入**：openpyxl / httpx / redis.asyncio / jieba / pypinyin 的剩余理论上限约 0.94 s；逐库移动到真实能力边界，并同时测首次调用，禁止一次性重写全部调用方。
- **P2 前端请求 / 渲染**：首页实测 `my/assignments` 发 2 次，随后按项目串行取待办；复用一次 assignments 并 `Promise.all`。role-context 同时取 me/nav/homepage，先确认后两项是否真有消费者；NotificationCenter 首屏串行取列表+数量且每标签页 30 s 轮询，改为只先取 badge、首次打开再取列表、隐藏页暂停、领导页轮询 + 广播。底稿列表最长任务仍约 0.8 s，下一轮做 DOM/组件级 Bottom-Up 后再定虚拟化或首屏分批，目标 <300 ms。
- **P2 公开面**：冷 worker 首次 `/openapi.json` 会同步物化全部 lazy route，约 2.6~2.9 s 且被 Observability 跳过；生产关闭 docs 或在受控阶段预生成。公开 health 的 reload reason / PID 应脱敏，详细信息移到管理员诊断。
- **P3 微优化**：路由已约 0.003 ms，不再重写。若继续压固定栈，只做可测的小改：DEBUG 未开启时不构造 Observability 正常请求日志字典、scope 缓存规范化 path、扩大现有 preencoded JSON 快路；先 profile 未读数的 SQL / Redis / pool checkout，再决定是否动 `pool_pre_ping`。

明确否决：取消 0.5 s accept grace；旧 worker 未退出就授予 primary；在 EventBus / cache invalidation 未跨进程前启多 Uvicorn worker；把 40~60 s 全量预热重新 await 到 ready；盲关 `pool_pre_ping`、继续提高 `work_mem`、缓存用户禁用 / token 吊销状态，或继续优化已经约 0.003 ms 的路由索引。
