# 运行时性能与热重载加固后续 — 需求

承接 `backend-startup-and-request-overhead` 完成后真实重启复盘（design §8）。用户 2026-10-28「按建议来」。本轮按安全优先：先补接管与事件正确性，再压启动 / 前端开销，最后在受控窗口调整 PostgreSQL。

## R1 候选接管安全

1. overlap 的候选 worker 在报告 ready 前必须物化并验证全部 lazy route；失败时旧 worker 继续服务，错误写 reload 状态。首次冷启动保持后台低强度验证，不牺牲 R1 冷启动目标。
2. 父进程从候选 ready 到旧 worker 完全退出期间持续监控候选；候选死亡不得记录 `ok`，必须给出阶段化失败原因。
3. primary 后 deferred singleton 全部执行完才记录 `primary_ready`；critical 失败必须使 reload 状态和 health 可见为 degraded，不能伪装成功。此次不承诺失败后自动回滚旧 worker。

## R2 交接时延与可观测性

1. handoff 已执行 0.5 秒 accept grace 后，lifespan 不再重复执行 2 秒 pre-drain；普通 SIGTERM / 关闭窗口仍保留原等待。
2. reload 状态记录 spawn→ready、ready→old-exit、old-exit→primary-ready 分段及候选退出阶段；所有公开错误先脱敏。
3. 保留 `GT_OVERLAP_RELOAD=0` 回退与 0.5 秒 accept grace。

## R3 项目事件连续性与 Redis 恢复

1. 项目 live SSE 的 typed 事件带稳定事件 id；前端重连后按 Last-Event-ID 先补拉遗漏事件，再恢复正常 fan-out，并对 replay/live 竞态去重。
2. raw 事件若不能进入同一可重放流，必须登记为显式降级并触发相关消费者全量刷新，不能声称无损。
3. 启动恢复既消费新条目，也 reclaim PEL pending；每批有上限、进度可见，不再让最多 100 个事件阻塞 readiness 4~5 秒。
4. Redis 不可用时保持 live 降级，但 health 明确标记 replay 不可用。

## R4 HTTP 审计确认顺序

1. 仅对最终成功、非 SSE 响应，在完整 body 已形成后、向客户端发送最终响应前完成既有 `logs` INSERT/commit；不增加第二次 DB 写。
2. 审计写失败继续沿用 fail-open，避免业务已提交后返回 503 诱发重复写，但必须返回可观测失败、持久化管理员告警。明确不宣称与业务事务原子。
3. 真正 transactional outbox 暂缓到写路由统一事务 / 幂等后；禁止把现有 project-bound outbox 或非耐久 Redis RPOP 队列冒充原子闭环。

## R5 启动与固定请求开销

1. workpaper 预热、singleton、lazy route 后台核验不得并发执行两个 CPU/GIL 重阶段；full GC/freeze 只在无 in-flight 的空闲窗口运行，超时继续延后。
2. 对剩余第三方导入逐项测量，只移动能证明收益且有首次调用测试的边界；总收益不足 50 ms 的不改。
3. Observability 在 DEBUG 未启用、状态正常且不慢时不构造完整日志字典；规范化 path 可在 scope 复用。路由索引不再优化。
4. 冷 worker 的 OpenAPI 不得在公共请求中同步物化全部路由；生产可关闭 docs，开发须预生成 / 缓存且不阻塞普通请求。

## R6 前端请求与渲染

1. Dashboard 只取一次 assignments，待办项目请求并发且保持原顺序 / 截取 / 失败隔离语义。
2. role context 首屏只等待有真实消费者的 `/me`；nav/homepage action 保留为按需调用。
3. NotificationCenter 首屏只取未读数，首次打开再取列表；隐藏页暂停，恢复立即校准，不允许重叠轮询。跨标签领导抽取只有在不改变项目 SSE 行为时才接入。
4. Workpaper 工作台折叠循环不创建隐藏行 DOM；树结构预计算且与旧算法逐项等价。此次不直接替换成虚拟表。
5. Projects / MiddleProjectList 只做短时共享查询，任何新增 / 删除 / 导入必须失效，不能用长期陈旧缓存换速度。

## R7 PostgreSQL

1. 调整前保存配置与关键查询基线；受控重启 `audit-postgres`，初始设置 shared_buffers=8GB、启用 pg_stat_statements，effective_cache_size 按宿主内存保守设置；work_mem 保持 32MB。
2. 重启前后验证数据库行数 / Redis 数据不受影响、应用可恢复、迁移无失败，并用 pg_stat_statements 识别 top SQL。
3. PgBouncer 只做配置与可用性评估；没有 6000 并发压测证据前不切换生产连接。

## R8 验收

- 单元 / 契约 / 变异、真实主实例 reload 连续轮询、Playwright、PG 活连接 / 设置、前后性能对照全部留证。
- 不删除历史审计 / pending 数据，不提交、不推送，除非用户另行授权。
