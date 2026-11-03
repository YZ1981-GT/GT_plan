# 运行时性能与热重载加固后续 — 设计

## 1. 现状证据与裁决

- 主实例 overlap 交接 8.4~11.8 s，连续轮询 0 失败，最大 1.39 s；其中 app 导入约 4.8 s，旧进程关闭路径固定包含 accept grace 0.5 s + lifespan pre-drain 2 s。
- lazy route 全量物化约 2.6~2.9 s，当前在 ready 后 60 s 才后台执行。安全裁决：只让 overlap 候选在旧 worker 继续服务时同步验证；首次冷启动不改。
- Redis `audit:events` 长度 8661、lag=0、PEL pending=264；首次完整启动新事件恢复 4787 ms，后续 20~167 ms。当前只读 `>`，不 reclaim pending。
- 项目 SSE drain 重连与 function-scope DB session 已在上一轮验收补修；本轮在此基础上做 replay / 竞态闭环。
- 审计中间件已做一次 `logs` INSERT+commit，但在响应发出后。本轮只前移同一次写，不新增表 / outbox；业务事务原子化明确暂缓。
- PG 现场：shared_buffers 128MB、effective_cache_size 4GB、work_mem 32MB、jit off、pg_stat_statements 未加载；容器约 730MB / 宿主 93GB。

## 2. Reload 两阶段状态机

### 2.1 候选验证

`_spawn(candidate: bool)` 把角色交给 `_WorkerTarget` / `reload_handoff`。候选 worker 的启动注册表在 `verify_lazy_routes` 项中直接调用生产 `materialize_all(app.router.routes)`；失败抛出专用异常，使 lifespan 不完成、`server.started` 不置位。非候选仍排 60 s 后的低强度任务。

验证全量物化会延长“代码生效”等待但不会造成停服，因为旧 worker 仍 accept。该路径也避免首次用户请求为新路由支付物化代价。

### 2.2 promotion 与 primary_ready

父进程事件拆为 `serving_ready`、`stop`、`primary`、`primary_ready`、`primary_failed`。候选 ready 后先做短稳定检查，再要求旧 worker 退出；等待期间每 100 ms 检查候选仍存活。旧 worker 退出后置 primary，deferred runner 完成全部 singleton 后置 primary_ready；critical 失败置 primary_failed 并把脱敏摘要写错误文件。父进程只有此后才写最终 ok/degraded。

若候选在旧 worker stop 前死亡，旧 worker不动；若在旧 worker已开始排空后死亡，记录 `failed_after_drain` 并立即拉起恢复候选。此次不伪称可恢复旧 worker。

### 2.3 关闭路径

`reload_handoff` 设置进程内 handoff 标记。lifespan 关闭时若该标记已表示“停 accept + close SSE + 0.5 s grace”完成，则跳过 `PRE_DRAIN_DELAY` 与第二次 `close_all`；普通关闭保持原逻辑。

状态文件增加 `spawn_to_ready_s`、`ready_to_old_exit_s`、`old_exit_to_primary_ready_s`、`phase`。公开 health 只给结果 / 阶段 / 耗时 / 脱敏 reason；PID 仅保留开发模式或管理员诊断。

## 3. EventBus 与 SSE replay

### 3.1 typed live id

持久化必须先于 live SSE 可见：`_persist_to_stream` 返回 Redis message id，`_dispatch` 在 Redis 可用时 await XADD，再把 id 随队列项下发；Redis 不可用则 id=None、照常 live，但标记 replay unavailable。SSE 输出 `id: <redis-id>`。

为不破坏 handler 时序，XADD 只移动到 `_notify_sse` 前；业务 handlers 仍按原顺序执行。持久化失败不阻断业务 handler。

### 3.2 reconnect replay / live barrier

`projectEventStream` 保存最后业务事件 id。重连 open 时进入 replaying，暂存随后到达的 live 消息；调用 `/events/since?last_event_id=`，按 Redis id 升序 fan-out，再合并 live buffer，按 id 去重后退出 barrier。跟随标签页通过 BroadcastChannel 同时收到 id；reconnect hook 只在 barrier 完成后触发。

没有 id 的 raw event 不进入“无损”承诺。重连完成时通配订阅者收到内部 `transport.recovered`，现有消费者按 onReconnect 清缓存 / refetch；另建清单冻结尚无恢复 hook 的 raw 事件消费者。

### 3.3 Redis PEL

恢复顺序：先 `XAUTOCLAIM` 超过租约的 pending，再读 `>` 新条目。每次最多 25，单条处理后 ACK；剩余量写报告，由 primary 后低优先级 worker 继续批次，不阻塞 server ready。consumer name 含进程 PID，禁止所有进程共用 `worker-1`。解析失败仍 ACK 并计 dropped。

## 4. 审计响应确认

`_CapturingSend` 不再立即调用外层 send，而只保存重建后的 response。下游完整返回后，middleware 解析 body、调用现有 `_write_log`；该函数返回 bool。随后发送 response。日志成功时关闭“客户端已确认、日志还没 commit”的窗口；失败仍发原 2xx，同时写 CRITICAL 与管理员持久化告警。

不改 Log 字段、不接 Redis audit queue、不写第二张 outbox。限制写进文档和测试：业务 commit 与 Log commit 仍非原子，严格闭环要等请求事务统一和幂等。

## 5. 启动 / 请求优化

- `run_then_freeze` 等待 in-flight=0 且连续空闲窗口后才 full collect/freeze；超时重排，不与 route verifier 同时执行。记录 freeze duration / object count。
- 第三方导入先重新跑 importtime；只做单库单调用边界。首次调用必须有独立耗时和功能测试，收益未达 50 ms 立即撤回。
- Observability 先算 duration/status；仅慢请求、错误或对应日志级别开启时才构造完整 log_data / Headers。`request_path` 结果存 `scope['_gt_request_path']`。
- OpenAPI：开发启动后低优先级生成并缓存；生产配置关闭 docs。不得在公共首次请求里全量物化。

## 6. 前端

- Dashboard：一个 assignments promise；项目统计 / assignments / trend 同时起；待办用 `Promise.allSettled`，按输入顺序收口。
- roleContext：`initialize()` 只 `loadGlobalContext()`；nav/homepage action 保留。
- NotificationCenter：挂载只 count；popover 首开才 list；使用 `useAdaptivePoll` 做隐藏暂停 / 恢复立即拉 / 无重叠。跨标签领导抽取为后置独立批，若影响 project stream 即不接。
- WorkpaperWorkbench：循环 body 用 `v-if`；`buildTree` 改 Set + 向前找最长真实父编码，结果预计算进 group，模板不再每次调用函数。
- Projects/Middle：2 秒 query key 微缓存与显式 invalidation；正常互斥挂载不夸大收益。

## 7. PostgreSQL

实施前备份 `postgresql.auto.conf`、记录关键表行数与设置。使用 `ALTER SYSTEM` 设置 shared_buffers=8GB、effective_cache_size=48GB、shared_preload_libraries='pg_stat_statements'，不改 work_mem；重启容器后创建扩展并验证。失败时恢复备份并重启。PgBouncer 不在本批切流。

## 8. 验收与变异

- Reload：候选坏路由、ready 后死亡、critical primary 失败、handoff 重复等待、状态阶段逐项变异；真实 9980 每 0.2 s 轮询。
- Event：live id、replay/live barrier、重复 id、raw 降级、PEL claim/ACK/租约、Redis down；前后端契约双向测试。
- Audit：日志 commit 严格早于 terminal response send；中途异常 / 非2xx / SSE不记；写失败仍发原响应且告警。
- Frontend：请求次数、并发起点、顺序稳定、隐藏页、折叠 DOM、树算法 oracle；Playwright 用 127.0.0.1。
- PG：重启前后数据计数、health、pg_stat_statements、冷/热查询；不自动删历史数据。
