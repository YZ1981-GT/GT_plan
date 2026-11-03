# 运行时性能与热重载加固后续 — 任务

每项必须写实际代码与测试证据；不能实现的架构项如实登记，不以文档代代码。

## 批 0 基线与边界

- [x] 0. 记录当前 HEAD / 并发改动归属、reload 分段缺口、Redis Stream/PEL、PG 设置、首页请求与底稿 DOM 基线
  - 证据：HEAD `44707a388`，当前分支 `spec/disclosure-note-doc-upload-and-batch-fill`；启动核心 / EventBus / WorkpaperWorkbench 有本 spec 前置或并发会话改动，实施放独立锁定 detached worktree，回写前逐文件哈希核冲突。主实例 health healthy，最近 reload 11.3 s、primary=true、deferred=0，lazy routes 后台物化 2544/2544 失败 0。Redis `audit:events` entries-read=8661、pending=264、lag=7。PG：shared_buffers=128MB、effective_cache_size=4GB、work_mem=32MB、jit=off、shared_preload_libraries 空。上一轮 Playwright 实证首页 assignments 2 次、role-context 3 次、Notification 2 个首屏请求；929 底稿工作台默认折叠仍用 v-show 全量建行，树算法二次扫描。
- [x] 1. 锁定本轮不做项：多 worker、取消 0.5 s grace、业务事务原子审计、PgBouncer 切流、直接虚拟化
  - 裁决：保留单 worker 与 0.5 s grace；审计只前移既有 Log commit、如实声明与业务事务非原子；PgBouncer 仅评估；底稿先 v-if + 近线性树，不直接接异构树不兼容的 el-table-v2。

## 批 0b 后端 schema 漂移清零（用户 2026-10-29 点名）

- [x] 2b. `/api/health` 的 `schema_drift` 由 4 条 `type_mismatch` 清到 **0**
  - 对齐方向逐列现读写入方 / DB / 前端契约后决定，**不是**「ORM 说什么就改 DB」：
    `diagnostic_detail` 与 `error_type` 的写入方写的都是字符串（`traceback.format_exception_only`
    拼出的文本、`type(exc).__name__`）、DB 是 TEXT、前端 `deliverableApi.ts` 声明 `string | null`
    且按 `<pre>` 纯文本展示 ⇒ 写错的是 ORM 那一层，改 ORM 为 `sa.Text`；若反过来把 DB 改成 JSONB，
    那两处写纯文本会当场崩。`file_path`（attempts / items 各一列）ORM 意图是 TEXT、写的是会追加
    `_v<n>` 的交付件路径 ⇒ V215 把 `VARCHAR(500)` 放宽成 TEXT（放宽无损）。
  - 证据：V215/R215（幂等 `udt_name` 判定 + 回滚脚本显式声明收窄有损）；经 `MigrationRunner.run_pending()`
    应用（executed `['215']`，与启动同一路径）；现算 drift `total=0 critical=0`，`/api/health` 回 healthy、
    `migration.applied_count=215/failures=0`；守卫 `test_export_attempt_column_contract.py` 7 例
    （ORM 类型 + 反向「不得改回 JSONB」+ AST 判写入方不是 dict + 跨语言 TS 契约 + 真 PG 列类型 + 迁移幂等/回滚）；
    3 处磁盘变异打红。
  - 同轮顺带：`pg_stat_statements` 扩展建**两个**关系，白名单原来只登记本体 ⇒ 补 `pg_stat_statements_info`
    （否则启用扩展后它常驻 `db_extra` 噪音）。

## 批 1 Reload promotion

- [x] 2. `_spawn(candidate)` 与 reload_handoff 候选身份；首次启动行为不变
- [x] 3. overlap 候选在 ready 前生产函数全量物化 lazy routes；失败保留旧 worker
- [x] 4. 候选 ready 后稳定 / 存活监控，覆盖 old drain 期间死亡与失败阶段
- [x] 5. primary_ready / primary_failed 事件、deferred critical 失败汇报与 health 状态
- [x] 6. handoff 跳过重复 2 s pre-drain，普通关闭不变；保留 0.5 s
- [x] 7. reload 三段计时、公开 reason 脱敏 / PID 裁决、开关与变异
  - 证据：候选与首次 worker 分离；候选同步调用 `materialize_all`，失败阻断 lifespan；父进程稳定窗、old drain 期间存活检查、单次恢复 worker、primary ready/failed/timeout 状态与三段耗时已接线。handoff_stop 区分普通关闭，公开 health 去 PID 且 critical singleton 失败翻 degraded。相关 reload/lazy/SSE scope 选集 53 passed；候选身份、drain 存活检查、同步物化、重复 pre-drain、primary_failed 五处磁盘变异均按预期打红并逐字节恢复。

## 批 2 Event/SSE 与审计

- [x] 8. typed Redis 持久化返回 event id，live SSE 带 id；Redis down 显式降级
  - 证据：`_persist_to_stream` 返回 XADD id（bytes / str 统一成字符串），业务 handlers 保持原顺序，随后 await XADD，再把 `SSEEventPayload`（继承 `EventPayload`，传输字段 `exclude=True`）送入现有 `_notify_sse(payload)`，因此直接调用方与既有 spy 不改签名；`events._format_typed_sse` 有 id 才输出 `id:`。Redis down / XADD 失败时仍下发原 `EventPayload`、不伪造 id，并把 replay 状态显式标不可用。
- [x] 9. `/events/since` 契约与前端 replay/live barrier、id 去重、跨标签转发
  - 证据：`/since` 校验 cursor 为 Redis id，按全局 Stream 分页扫描（原来先 count=100 再按项目过滤，前 100 条若属其他项目会假返回空），最多返回 100 条本项目事件；replay 投影补齐 batch_id / entry_group_id / context，与 live 顶层字段同形。`projectEventStream` 保存最后 id；重连同步进入 barrier，期间 live 进 buffer，按 `/since` replay → live buffer 合并、Redis id 数值排序（非字符串排序）、2048 id 有界去重，barrier 完成后才触发 onReconnect。Web Locks 领导转发 event id，跟随标签接手以同一 id 建连并补拉。
- [x] 10. raw event 恢复清单与 reconnect 全量刷新降级，不夸大无损范围
  - 证据：后端 `RAW_EVENT_REPLAY_DEGRADED` + `formula_runtime.*` 前缀登记全部 production `broadcast_raw` 事件；未知 raw event 不阻断 live，但 ERROR 提醒必须登记或改 typed。前后端清单逐值对拍；barrier 后发 `transport.recovered`，载荷明确 `raw_full_refresh_required=true`。可安全重拉的 Adjustments / Attachment / Consol push / Lineage / 集中调整状态已接 onReconnect 全量校准；合并刷新进度靠 status poll；formula.pushed 因自动覆盖可能抹掉未保存编辑，明确保留手动载入提示，不伪装自动恢复。
- [x] 11. Redis PEL `XAUTOCLAIM` + 新条目有界批次、唯一 consumer、后台续跑与报告
  - 证据：`replay_pending_events` 先 `XAUTOCLAIM`（`min_idle_time=PEL_MIN_IDLE_MS=60s`）再读 `>`，单轮总量压在 `REPLAY_BATCH_SIZE=25`（新条目预算 = 批次 − 已认领）；consumer 名 `worker-{pid}`（原全进程共用 `worker-1`）；报告新增 `claimed_count / pending_remaining / consumer / exhausted`；积压由 `drain_pending_events_in_background` 在 ready 之后分批清空，启动任务只跑一批。14 个新判据 + 既有 replay/outbox/SSE 套件 148 passed。
  - 🔴 **真实重启验收抓到本项自身的回归并已修**：前台哪怕只跑一批也不行 —— 恢复要对每条认领回来的条目
    真实重跑业务 handler（stale 传播 / 公式推送 / 循环联动，每条带 DB 往返），真库 PEL 积压 264 条时
    一批 25 条就超过 `wait_for(5s)`；超时异常被启动任务的 `except` 吞掉后报告从不更新、后台续跑也排不上
    ⇒ 启动报告实测 `replay_startup_events=5047ms` 且 `events.replay_available=False`（恢复一条没做，比改之前更糟）。
    改为**恢复整体移出启动路径**（`_drain_events_after_ready` 只排后台任务），并加 `EVENT_DRAIN_START_DELAY_S=2s`
    起跑延迟 —— 否则后台回写会被 `run_startup_tasks` 末尾的 `_set_runtime_report(results)` 整份覆盖（实测 detail 为空）。
    现场复测：`replay_startup_events` **5047ms → 14ms**，detail「后台恢复 0 条，剩余 pending 0」，
    `events.replay_available=true`、`pending_remaining=0`（**PEL 264 → 0**）。
    判据 `test_startup_replay_background_continuation.py` 6 例 + 4 处变异打红。
- [x] 12. 审计 Log commit 移到成功响应发送前；失败 fail-open 但 CRITICAL + 持久化告警
  - 证据：`_CapturingSend` 只重建响应不发送，中间件在 `_write_log` 之后 `flush()`；失败仍发原 2xx（避免重复写）并记 CRITICAL + `_FAILURE_STATE` 计数，`/api/health` 的 `audit_log` 暴露且使 status=degraded。**与设计偏离并如实记录**：design §4 写的"持久化管理员告警"未实现 —— 审计写失败最常见原因就是 PG 不可用，再写一张表同样失败，而平台现扫没有独立于 PG 的告警 sink ⇒ 改为 CRITICAL 日志 + 进程内可观测状态 + health degraded，不假装有耐久告警通道。
- [x] 13. Event/SSE/Audit 单测、契约、磁盘变异与真实浏览器重连
  - 已完成：任务 8~12 的后端选集 80 passed、前端 SSE/跨标签/raw 恢复选集 35 passed、SSE 单区域 vue-tsc 0 error；任务 8~10 新增 9 处磁盘变异（XADD id 丢失、dispatch 不持久化、SSE id 行丢失、/since 只扫一页、raw 清单漏项、barrier 关闭、id 去重关闭、跨标签不转 id、消费者移除 onReconnect）逐个打红并逐字节恢复。任务 11/12 的 9 处变异也已完成。
  - 真实浏览器现场（2026-10-29，chrome-devtools + `127.0.0.1:3030`，和平药房 2024 底稿页，fetch tee 抓每一帧）：首次建连只收 `connected`、**不**发 `/events/since`（符合「首次 open 不补拉」）；触发热重载后 conn0 在 t=30192ms 收到 `server_draining`，**42 ms** 后 conn1 `connected`；全程 id 去重集合为空（无重复 id）。因断连前没有任何带 id 的 typed 事件，`lastEventId` 为空 ⇒ 按设计走「无 typed anchor 只触发 raw 全量刷新」，故本次现场**没有**触发 replay 分支。
  - `/events/since` 改为现场直接验证（比等一个真实 typed 事件更有判别力）：全局 `audit:events` 现算 **9689** 条，本项目第一条事件在全局第 **1479** 位，**全局前 100 条里本项目 0 条** ⇒ 旧实现（先全局 count=100 再按项目过滤）对该项目恒返回空列表，这正是任务 9 修的假空；现 `last_event_id=1-0` 返回 **8** 条且全属本项目，投影含 `batch_id` / `entry_group_id` / `context` / `extra`；`last_event_id=not-a-cursor` 返回 **422**（形状校验）；默认 60 s 窗口与 1 小时 `since_timestamp` 均 0 条（期间确实无事件）。
  - 带 typed anchor 的现场 replay 仍缺（需要一个安全的事件产生器：`events.py` 没有发布端点，真实业务写入会动真项目数据）⇒ 语义由 4 条新 vitest（Redis id 数值排序 / 先 replay 再放 live / 同 id 只投一次 / replay 失败仍放行 live）+ 后端 `test_sse_event_id_replay_contract.py` 覆盖，如实登记为现场缺口。

## 批 3 启动与固定开销

- [x] 14. reload / startup 现场分段测量，确认剩余耗时归因
  - 本轮代码已写回主树并完整重启 `start-dev.bat` 后，连续 5 轮真实 overlap reload（触发方式只改 mtime，`Path.touch()`）：全部 `result=ok` / `forced_stop=false`，无一次触发 `GT_RELOAD_STOP_TIMEOUT=30` 强停。
  - 分段（秒）：`spawn_to_ready` min 6.312 / avg 6.341 / max 6.375（**方差极小 ⇒ 这段是固定开销，不受流量影响**）；`old_exit_to_primary_ready` 0.203~0.204（恒定）；`ready_to_old_exit` 2.031 / 10.906 / 9.984 / 10.172 / 9.969（**唯一高方差段**）。
  - 归因实验：同一实例再做一次「触发后 45 s 内不发任何请求」的对照 reload，`ready_to_old_exit_s` = **1.0 s**（对比有 5 Hz `/api/health` 轮询时 2.0~10.9 s）⇒ 这段与**并发流量**相关，不是进程内固定成本。已排除的候选：`ACCEPT_GRACE_S` 只有 0.5 s；`event_bus` 的 `xreadgroup` 不传 `block`；全仓 `app/` 内无 8~12 s 的轮询 sleep，也无 8~12 s 的关停超时常量；drain 时只有 1 条 established 连接。剩余最可能的机理是 uvicorn 优雅关闭等待「停 accept 前刚建立的连接」结束，**未钉死**，如实登记（见「交接项」）。
  - 可用性：整个 5 轮期间 0.2 s 轮询 `/api/health` 共 **402** 次，硬失败 **0**、503 **0**，最长单次 **812 ms**（即交接期对外不中断，但尾延迟会到 0.8 s）。
- [x] 15. GC freeze 空闲门与后台重排，和 lazy verifier / singleton 错峰
  - 证据：`freeze_when_idle` 要求 in-flight 连续 500ms 为 0；30s 等不到只重排（5s backoff），绝不强跑；获取每事件循环独立的 `heavy_phase` 锁后再次检查 in-flight，再同步 collect+freeze（GC 持 GIL，明确否决 `to_thread`）。报告记录 status/wait_s/requeues/collected/duration_ms/freeze_count 并进 health。event replay、workpaper prewarm、后台 lazy verifier、OpenAPI 共用重阶段锁；prewarm 改 singleton，候选成为 primary 且 event drain 完成后才运行。新增连续空闲重置、忙时不强跑、锁后二次检查、预热/路由互斥等判据。
- [x] 16. importtime 重测并逐项裁决第三方 lazy import；只保留收益 ≥50 ms 的改动
  - 证据：正式探针 `scripts/analyze/measure_main_imports.py`；改前 fresh-process 5轮 `import app.main` 中位 3437.2ms，目标包均提前加载。只对全仓唯一顶层导入的 jieba / pypinyin 做候选，6轮**交替** A/B：baseline `[3793.1,4248.6,4263.1,4131.0,6209.6,4247.2]` 中位 4247.9ms，candidate `[3861.5,3543.3,4013.5,3868.3,6047.9,4052.9]` 中位 3940.9ms，净省 **307.0ms**（≥50ms），且 app.main 后两包均不在 sys.modules。保留 find_spec + 首次调用锁内导入；缺包降级语义、词典只载一次不变；并发首次调用与真实分词/拼音测试覆盖。httpx/openpyxl/redis.asyncio 在其他启动链仍提前导入，单点移动净收益无证据，否决。
- [x] 17. Observability 日志快路与 scope path 缓存，等价测试 + 微基准
  - 证据：先按原优先级（慢请求优先）算 level/label，仅 `logger.isEnabledFor(level)` 时构造 log_data + Headers；响应 `X-Response-Time` 永远保留；日志 method/msg/args 与旧快照逐项一致。`request_path` 存 `scope['_gt_request_path']`，Observability/Audit/Inflight 复用，敏感/畸形路径语义不变。正式微基准 5×50000：eager 中位 3309.6ns/request → fast 2789.3ns，省 **520.3ns / 15.7%**。
- [x] 18. OpenAPI 开发预生成 / 生产关闭、冷请求不阻塞普通接口；health 公开面脱敏
  - 证据：`APP_ENV in {prod,production,staging}` 时 `/openapi.json`、`/docs`、`/redoc` 三路径均不注册；开发环境安装自定义 async schema 路由，同一 app 并发请求 single-flight，生成走 `asyncio.to_thread(app.openapi)` + heavy_phase，普通 API 在 schema 生成中仍可响应；后台 90s 预生成只在 primary 调度，不重复 `materialize_all`。离线 `app.openapi()` 生产仍可供契约工具调用。health reload 去 PID/reason 脱敏沿用批1。
  - 本批 8 处磁盘变异（锁后二次检查、prewarm/lazy verifier 去重阶段锁、Observability 强制构造 Headers、path 不读缓存、生产 docs 误开放、OpenAPI 回事件循环同步生成、jieba 提前导入）逐项打红并逐字节恢复。

## 批 4 前端

> 2026-10-29 实施了 19 / 20 / 21（请求收敛三项）；23 / 24（底稿折叠 DOM、Projects 微缓存）与
> 22（跨标签领导）仍未动，保持未勾。

- [x] 19. Dashboard assignments 单飞、待办并发且顺序 / 失败隔离不变
  - 证据：`onMounted` 内 `getMyAssignments()` 从两次 await 改为一个共享 promise（「今日日程」与「我的待办底稿」
    共用）；待办的 5 个项目底稿请求由串行 await 改 `Promise.allSettled` 并发，单项目失败只丢它自己那一段，
    每项目前 3 条、总共前 6 条的截取与输入顺序不变。判据 `dashboardAssignmentsSingleFlight.spec.ts` 4 例
    （含「挂起响应时已发出 5 条」证明真并发、单项目失败的顺序断言、剔注释后的源码形态判据）；2 处变异打红。
- [x] 20. roleContext 首屏 3→1，保留 nav/homepage 按需 action 与角色门禁回归
  - 证据：现算全仓**没有任何组件**读 store 的 `navItems` / `homepageContent`（所有 `navItems` 命中都是各底稿 /
    布局组件自己的局部常量；`homepageContent` 只在 store 内部出现），而 `initialize()` 是 `DefaultLayout` 唯一
    调用且被 await ⇒ 两条请求的结果没人消费却挡在首屏关键路径上。`initialize()` 改为只 `loadGlobalContext()`，
    两个 action 保留按需。判据 `roleContextInitialize.spec.ts` 4 例（含 `/me` 失败仍只发 1 条、源码判据）；1 处变异打红。
- [x] 21. NotificationCenter 列表懒取 + adaptive poll 隐藏暂停 / 恢复立即 / 无重叠
  - 证据：挂载只取未读数（列表只在 popover 打开后才显示，原来首屏就取）；列表首次打开才取、取失败不置
    `listLoaded` 下次重试、连续开关不重叠；`setInterval(30s)` 换成 `useAdaptivePoll`（隐藏暂停、恢复立即校准、
    同一时刻一条链）。判据 `notificationCenterLazyList.spec.ts` 5 例（挂真实组件，含卸载后不再轮询、源码判据
    「挂载钩子里不得再取列表」）；2 处变异打红。既有 `NotificationCenter.deeplink.spec.ts` 的夹具按新行为补了
    「打开 popover」这一真实前提（断言强度不变）。
  - 🔴 **浏览器实测前后对照**（自起无头 Chromium、真实 admin 登录、首页加载 10 秒后统计）：首屏 `/api` 请求
    **16 → 12 条，且无任何端点重复**、console error 0。逐项：`projects/my/assignments` 2→1、role-context 3→1、
    通知 2→1；两个待办项目的底稿请求并发发出。
- [x] 22. 评估并实现通知跨标签领导；若风险不满足 design §6，则留下现算否决证据
  - 裁决：**否决本轮接入**。现测未读数 API 中位 15ms，pg_stat_statements 的 count SQL 均值约 0.17ms；`useAdaptivePoll` 已把频率降到每可见标签 30s 一次，跨标签领导每增加一个标签只省 2 次/分钟。实现需新增用户维度 Web Lock + BroadcastChannel、领导退出接替、消息丢失后本地校准等至少 3 文件/一组浏览器协议；任一接力缺陷会让跟随标签红点长期陈旧。收益远低于状态正确性风险，且项目 SSE 领导机制保持完全不变。切换点：若 pg_stat_statements 显示通知 count 进入 top SQL，或实测常见 ≥10 标签，再独立接入。
- [x] 23. Workpaper 折叠 DOM `v-if` + 近线性树预计算，与旧算法逐项对拍
  - 证据：循环 body `v-show`→`v-if`，默认折叠时不再创建隐藏底稿行 DOM；模板从每次 render 调 `buildTree(group.items)` 改读 computed 预先生成的 `group.tree`。唯一算法 `workpaperTree.ts` 用 Set + 沿连字符向前找最近真实父，复杂度由 O(n²) 降为 O(Σ编码段数)；保留「父码必须真实存在、最长父、仅一层展示、重复码」旧语义。6 组边界 + 200 组确定性组合逐项对拍，源码判据禁 `codes.some` / 模板内建树。
- [x] 24. Projects/Middle 2 秒共享查询与 mutation invalidation，或按运行时证据否决
  - 证据：`/projects` 不是全宽路由，DefaultLayout 会同时挂 MiddleProjectList，正文又挂 Projects.vue，两者 onMounted 原来同时 GET `/api/projects`。新 `projectListQuery.ts` 提供 in-flight 单飞 + 完成后2秒缓存；每调用方拿浅拷贝；带筛选参数不缓存；epoch + 清 in-flight 保证 mutation 前发出的晚到响应不能回填陈旧缓存。Projects 经 commonApi、Middle 直接复用同一入口。创建/向导编辑、单删/批删/批量导入、collaboration project create/update/delete、项目回收站恢复/永久删除/清空全部显式失效。20 个新判据通过；9处树/DOM/缓存/失效磁盘变异逐项打红并恢复；单区域 vue-tsc 0 error。
- [x] 25. 前端单测、变异、Playwright 请求数 / console / long task 前后对照
  - 单测与变异：任务 19~24 各批已完成（含批 4 的 9 处磁盘变异）。本轮收口再跑**全量选集 91 个 spec**（选集由 `rprh2_fe_sel.py` 按「import 了被改源文件」∪「源码里出现被改文件名的守卫」自动收集，不手挑）：候选树 1291 用例 / 11 红，干净 HEAD 基线树 1248 用例 / 11 红，**junit 逐节点比对新增失败 0**，本轮 44 条新用例全绿。
  - 单区域类型检查：`tsconfig._rprh-sse.json` 与 `tsconfig._rprh-task4.json` 均 `error TS` **0** 且无 OOM（按方法论铁律㉔，每次都检查有无 `heap out of memory`，不只看错误计数）。
  - 现场（chrome-devtools，`127.0.0.1:3030`，任务 23/24 的直接验收点）：
    - 项目列表 `/projects` 首屏 **`GET /api/projects` 只 1 次**（该路由同时挂 `MiddleProjectList` + `Projects.vue`，单飞生效）；7 条 `/api` 请求 / 6 个唯一端点；long task 1 次 162 ms。
    - 底稿工作台 15 个循环组全折叠时 DOM **942** 个元素；展开 F 存货（98 份底稿）后 **1159**（+217）；再折叠**精确回到 942** ⇒ 折叠组不建隐藏行（`v-show` 时这些节点会常驻）。按 +217/98 外推，1017 份底稿全驻留约需额外 2.2k 个节点。
  - 顺带发现（非本轮引入，登记不改）：`/projects` 首屏 `GET /api/custom-query/indicators` 发了两次（一次带 `?depth=1`、一次不带），参数不同故不是 GET 去重能合的那种重复，需要调用方自己收口。

## 批 5 PostgreSQL 与收尾

- [x] 26. 备份 PG 配置、数据计数与查询基线；确认宿主 / 容器资源
  - 证据：`postgresql.auto.conf` 原文备份到 `C:\Users\Administrator\rprh_pg_backup\postgresql.auto.conf.bak`（246 B，原内容只有 `jit='off'` + `work_mem='32MB'`）。改前设置：shared_buffers=128MB（16384×8kB）、effective_cache_size=4GB、work_mem=32MB、maintenance_work_mem=512MB、max_connections=200（**来源 command line**，容器 CMD 带 `-c max_connections=200`，conf 改不动它）、shared_preload_libraries 空、jit=off、random_page_cost=4、扩展仅 plpgsql+citext。改前行数：projects=115 logs=108360 trial_balance=1401 disclosure_notes=2047 checklist_responses=906 schema_version=212。资源现算：宿主 189.6 GB RAM（空闲 128 GB），Docker/WSL2 VM 93 GiB（可用 82 GiB）⇒ 8GB/48GB 在 VM 内保守可行。
- [x] 27. 设置 shared_buffers/effective_cache_size/pg_stat_statements，重启 audit-postgres，创建扩展并验证回滚路径
  - 证据：`ALTER SYSTEM` 设 shared_buffers=8GB、effective_cache_size=48GB、shared_preload_libraries='pg_stat_statements'（`pg_stat_statements.max/.track` 在库未加载时无法设，按默认，未强设）。`docker restart audit-postgres` 到 `pg_isready` 3.1 s；重启后现算 shared_buffers=8192MB、effective_cache_size=48GB、shared_preload_libraries=pg_stat_statements、work_mem 仍 32MB、max_connections 仍 200。`CREATE EXTENSION IF NOT EXISTS pg_stat_statements` 成功。数据未受影响：除 logs 108360→108361（本次自身请求写的审计行）外逐表计数一致，schema_version 不变。回滚路径 = 把备份文件写回 `postgresql.auto.conf` 后重启容器（备份与原文逐字节保留，未执行回滚）。
- [x] 28. 用 pg_stat_statements 取 top SQL；核查连接池 / PgBouncer，6000 并发结论保持未验证
  - 证据：重启后约 12 分钟窗口内 `sum(total_exec_time)=2514 ms / sum(calls)=7360`；按调用量 top 是**后台轮询**而非业务查询 —— `wp_visibility_invalidation_outbox` 335 calls（0.10 ms/次）、`acnr_invalidation_outbox` 46 calls、`BEGIN` 1934 次、`ROLLBACK` 370 次；单条最慢是并发会话测试建表（`CREATE TABLE disclosure_notes` 22.9 ms）与迁移 DDL。结论：当前负载下 PG 不是瓶颈，真正可省的是空闲期每秒级的 outbox 轮询事务。PgBouncer 仍只做评估、未切流；6000 并发结论保持**未验证**（无压测证据）。
  - 顺带（在 PG 范围内、本轮实测暴露）：启用扩展后 `pg_stat_statements_info` 视图会常驻 `db_extra` 噪音 —— 检测器白名单原来只登记了 `pg_stat_statements` 本体，已补 `pg_stat_statements_info`（`schema_drift_detector.KNOWN_ALLOWLIST`），48 个既有判据仍绿。
- [x] 29. 后端回归、真实 reload、SSE/PG 会话、API、Playwright、性能与行数门
  - 后端回归与归因：候选树 40 个文件（reload / handoff / 启动编排 / lazy routes / 中间件等价 / event bus / replay / PEL / SSE / GC / OpenAPI / 延迟导入 / 漂移 / 迁移 / health / 守卫）**514 passed、7 failed、4 errors**。为把别人的红和自己的红分开，另建干净 HEAD 基线 worktree（`8107371f0`，locked）跑**同一份清单同一顺序**（其中 8 个文件是本轮新增 spec、HEAD 上不存在，已声明跳过）：**逐节点复现同样 11 条红** ⇒ 本轮新增后端失败 **0**。
  - 预存红清单（本轮未引入、未修，不计入本 spec）：`test_import_operations_observability` 3 条（`import_slo_service.py:185` naive/aware datetime 相减 + 2 条 Redis `Event loop is closed`）、`test_migration_drift_ledger[V200]/[V201]`（ledger 有条目而磁盘无文件）、`test_lazy_import_resolvability` 2 条（`app.services.consol_lock_service` 整模块缺失、`note_section_matcher.resolve_alias_counterparts`）、`test_v205_export_schema_drift_pg` 4 个 fixture error。
  - 真实 reload / API / Playwright / PG：见任务 14（5 轮分段 + 402 次轮询 0 硬失败）、任务 25（前端选集 + 现场 DOM / 请求数）、任务 13（SSE 断线重连 + `/events/since`）、任务 28（top SQL）。重启后现场：`status=healthy`、`migration.applied_count=218`、`schema_drift.count=0 / critical 0`。PG 连接：10 idle + 1 active，**无 `idle in transaction`**（SSE 路由 `get_db` 的 `scope="function"` 约束未被破坏）。
  - 🔴 本任务的真实收获是抓到**我自己引入的一个缺陷**（现场才暴露）：GC 空闲门把 SSE 长连接算进 in-flight ⇒ 只要有一个浏览器标签订阅事件流，`inflight_counter.value()` 永不为 0，freeze 永不发生。证据 `gc={status:requeued, wait_s:415.5, requeues:12, freeze_count:0}`。修法与判据见任务 15 的补记；修后 `gc={status:ok, wait_s:0.512, requeues:0, collected:189232, duration_ms:426.7, freeze_count:767756}`。
  - 行数门：`check_file_size.py --files-from -` 对本轮 51 个 owned 文件 **rc=0**。过程中抓到 `startup_registry.py` 1079 行 > 白名单基线 991 的 +5%（1040）—— **没有抬基线**，而是按「打磨应让文件变小」把 4 个「ready 之后才跑的重阶段调度」函数抽到新模块 `app/core/startup_deferred.py`、registry 保留同名 re-export 薄壳（既有测试按 `startup_registry._run_workpaper_prewarm` 调用，不用改），1079 → **1029** 过门；`ruff` 过，焦点选集 109 passed。
- [x] 30. 更新本 spec、INDEX、memory；清理临时文件；不提交不推送

### 任务 15 的补记（任务 29 现场暴露后修复，2026-10-29）

- 缺陷：`freeze_when_idle` 读 `inflight_counter.value()`，而 `InflightTrackingMiddleware` 的计数覆盖到响应体发完，SSE 流式响应会挂几十分钟 ⇒ 空闲窗口永不成立。
- 修法（单源，不按路由清单）：`app/middleware/inflight.py` 增 `streaming` 子计数，识别口径是 `http.response.start` 响应头 `content-type: text/event-stream`（全仓 10 处 SSE 分散在 8 个 router，清单必漂）；新增 `value_excluding_streams()`。`drain` 仍用 `value()`（停旧 worker 前必须等 SSE 断开或被强停），只有 GC 空闲判定换成排除流的视图；超时日志同时报在途数与被排除的 SSE 数。
- 判据：`test_middleware_pure_asgi` 4 例（SSE 被排除但仍计 in-flight / 非 SSE 流式**不**被排除 / SSE 中途抛错也要把子计数减回去 / 生产实际 media_type 与识别口径对拍 + 别名反向断言）；`test_gc_tuning` 3 例（挂着 1 条 SSE 仍能 freeze / SSE 之外还有请求则继续等 / **AST** 钉死「空闲判定只许读 `value_excluding_streams`」并带反向探针防扫描器失效）。
- 🔴 连带修的「判据恒绿」风险：原有 5 处 `monkeypatch.setattr(inflight_counter, "value", ...)` 在改读法后已对被测分支无效，全部改成 `value_excluding_streams`（否则「忙时不强跑」那组用例会在真实计数器下恒判空闲而假绿）。
- 变异：7 条正向变异（两处判定回退读 `value()`、识别恒假、识别恒真、不减子计数、排除视图退化、识别口径改别名）全部打红；另设 1 条**阴性对照**（只删超时日志里的诊断信息）保持绿，证明判据不是对任何改动都红。一律按字节替换 + sha256 校验恢复（`inflight.py` 工作区是 CRLF、`gc_tuning.py` 是 LF，多行锚点按各自行尾构造）。

## 交付边界（诚实登记，2026-10-29 收口）

31 项任务（0~30）全部 `[x]`。全部批次都已写回主工作树并在主实例 9980 上完整重启加载过，
现场证据见各任务条目。**未提交、未推送**（用户未授权）。

### 本轮（任务 13 / 14 / 25 / 29 / 30）的现场数据

| 指标 | 改前 | 改后 | 取数方式 |
|------|------|------|----------|
| GC freeze | `requeued`，等 415.5 s / 重排 12 次 / `freeze_count=0` | `ok`，等 **0.512 s** / 重排 **0** / 冻结 **767756** 个对象（回收 189232，停顿 426.7 ms） | 完整重启后读 `/api/health` 的 `gc` |
| `spawn_to_ready_s` | — | 6.312 / 6.341 / 6.375（min/avg/max，5 轮） | 5 轮真实 overlap reload |
| `ready_to_old_exit_s` | 11.188 s（本 spec 开工前） | 有流量 2.0~10.9 s；**无流量对照 1.0 s** | 同上 + 静默对照实验 |
| 交接期可用性 | — | 402 次 0.2 s 轮询，硬失败 **0**，最长单次 812 ms | 轮询线程与 reload 并行 |
| SSE 断线重连 | — | `server_draining` → **42 ms** 后新连接 `connected`，重复 id **0** | fetch tee 抓每一帧 |
| `/events/since` 对本项目 | 恒空（全局前 100 条里本项目 0 条，而首条在第 1479 位） | **8** 条，投影含 `batch_id`/`entry_group_id`/`context`/`extra` | 浏览器直调 + `redis-cli XRANGE` 量化 |
| `/projects` 首屏 `GET /api/projects` | 2 次（Middle + Projects 各一次） | **1 次** | chrome-devtools XHR 埋点 |
| 底稿工作台折叠态 DOM | 全部循环常驻 | 全折叠 **942** 元素；展开 98 份底稿的一组 +217；再折叠精确回 942 | 同上 |
| `startup_registry.py` | 1079 行（超白名单基线 991 的 +5%） | **1029** 行（抽出 `startup_deferred.py`，未抬基线） | `check_file_size.py --files-from -` |

### 回归归因（两侧新增失败均为 0）

| 侧 | 候选树 | 干净 HEAD 基线树 | 结论 |
|----|--------|------------------|------|
| 后端（40 文件选集） | 514 passed / 7 failed / 4 errors | 同一清单 27 文件（8 个本轮新 spec 不在 HEAD）复现同样 11 红 | 新增 **0** |
| 前端（91 spec 选集） | 1291 用例 / 11 红 | 1248 用例 / 11 红 | junit 逐节点比对新增 **0**，44 条新用例全绿 |

### 交接项（非本轮引入，已拿到精确证据，留给对应负责人）

1. **`test_v205_export_schema_drift_pg` 的 4 个 fixture error 属测试基建缺陷，守卫有洞。** 前缀二分得最小复现前缀 k=**5**，决定性模块是 `tests/test_event_bus.py`（v205 单独跑 4 passed，与任意单个前序模块两两组合都不复现 ⇒ 至少要 3 个模块才发作）。既有守卫 `test_pg_tests_dispose_shared_engine.py` 的判据是「文件**直接 import** 了 `app.core.database` 的 `engine`/`async_session` 别名」才算 `uses_pool`，而 `test_event_bus.py` 自建模块级 `create_async_engine`、并通过 handler **间接**用到全局池，`uses_pool` 判 False ⇒ 从来没进扫描面。同类反模式全仓共 **9** 个文件（`test_formula_push_{k1_d4_canary,k2_canary,note_skip,schema}_pg`、`test_linkage_facade_conflict_pg`、`test_v176_trial_balance_wp_adjustment_pg`、`test_v205_export_schema_drift_pg`、`test_wp_templates_readonly`、`test_wp_eval_cell_pbt`）。本 spec 只在自己的 `test_export_attempt_column_contract.py` 上按「同一事件循环内自建/销毁 NullPool engine」修过一处，其余 9 个未动（跨 spec，且需裁决是改守卫判据还是加 conftest 级 module-scope dispose）。
2. **`V201`/`R201` 重复迁移仍待迁移负责人裁决。** 与已跟踪的 `V203`/`R203` SQL 体相同，但 `V201` 在主树是未跟踪的并发中间态；真实库 201 / 203 都有审计记录。本 spec 不删、不移、不弱化唯一性守卫，只在干净 worktree 里隔离验证。
3. **`ready_to_old_exit_s` 在有流量时达 ~10 s 的机理未钉死。** 已排除 `ACCEPT_GRACE_S`（0.5 s）、`xreadgroup` 无 `block`、`app/` 内无 8~12 s 轮询 sleep / 关停常量、drain 时仅 1 条 established 连接。剩余候选是 uvicorn 优雅关闭等待「停 accept 前刚建立的连接」。影响：每次保存代码会有约 10 s 两个 worker 并存（双份 DB 连接与内存），功能无影响（`forced_stop` 从未触发）。
4. **持续热重载下 GC freeze 可能走不到。** deferred 链是「等成为 primary → 等事件 drain → 预热（实测 55~80 s）→ 等连续 500 ms 空闲 → freeze」，而并发会话活跃编辑时两次 reload 间隔常短于这条链；安静重启实测 0.5 s 内完成。这是启动期优化的固有性质，不是缺陷，但不要把开发机上的 `gc: not_run` 当回归。
5. **`/projects` 首屏 `GET /api/custom-query/indicators` 发两次**（带 `?depth=1` 与不带各一次），参数不同故 GET 去重合不了，需调用方收口。

真实重启与两次真实 overlap reload 的现场数据（主实例 9980，本轮代码已加载 —— `/api/health` 的
`reload` 带新字段 `primary_state` / `candidate`）：

| 指标 | 改前 | 改后 |
|------|------|------|
| `replay_startup_events` | 5047 ms（白等且恢复一条没做） | **14 ms**（恢复移后台，detail 可见） |
| Redis `audit:events` PEL pending | 264 | **0** |
| `verify_lazy_routes` | ready 后 60 秒才后台跑 | 候选 **ready 前**全量物化 2491 ms |
| `ready_to_old_exit_s` | 11.188 s（旧代码 worker） | **1.031 s**（跳过重复 2 s pre-drain） |
| reload 全程 `duration_s` | —（旧口径不含 primary 等待） | **8.781 s**，`phase=primary_ready`，停服 0 |
| `/api/health` schema_drift | 4 条 type_mismatch | **0 / critical 0** |
| 首屏 `/api` 请求 | 16 条（3 个端点重复） | **12 条，0 重复** |

（上表是**第一轮**重启的数据，保留作为批 0b / 批 1 / 批 2 任务 11~12 的现场留痕；本轮批 2 任务 8~10、
批 3、批 4 任务 22~24 的数据见上面「本轮的现场数据」表。原先这里写的「未实施」清单在本轮已全部落地，
任务 8 的卡点解法是改用继承 `EventPayload` 的 `SSEEventPayload`（传输字段 `exclude=True`）把 id 带进
原 `_notify_sse(payload)` 签名，6 个既有读队列测试一个都不用改。）

> **2026-10-30 同步勘误（改号）**：本 spec 的 `V215__export_file_path_text.sql` / `R215__rollback_export_file_path_text.sql` 与远端已推送的 V215（`account_chart_dataset_versioning`）撞号，同步时改为 **V223 / R223**（内容不改、checksum 不变；共享库 schema_version 的 215 行同步改登记为 223）。上文「V215」均指现在的 V223；守卫 `test_export_attempt_column_contract.py` 已改指 V223。
