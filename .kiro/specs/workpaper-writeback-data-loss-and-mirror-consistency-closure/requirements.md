# 需求：底稿双向回写保存安全与镜像一致性收口

承接 2026-11-01 对平台双向回写的代码、守卫与共享库账面分析。用户裁定：「按建议来」。

本 spec 只做第一阶段：消除 HTML 保存静默覆盖、切换在线编辑前丢写，以及 OO→HTML 已提交内容与 HTML store 分叉。122 个 adapter 迁移、Univer 统一协议、callback 异步化另行处理。

## R1 渐进式 checklist 乐观锁

1. 已迁移客户端更新既有 `checklist_responses` 行时必须携带服务端版本；版本缺失返回 428，版本过期返回 409，整批零写入。
2. 新建行允许没有版本；并发创建使该行在写入前已经存在时按 428 拒绝，不退回 LWW。
3. 尚未迁移的旧调用方暂时保留 LWW，回执继续明确 `overwritten=true`；迁移清单只许减少，全部迁完后才能取消兼容。
4. 通用持久化层及本轮双向宿主保存入口必须保留 GET 回执中的 `version`，下一轮保存发送 `if_match`，成功后更新本地版本。
5. 409/428/423/网络失败都保留本地 dirty，不显示保存成功，不用空版本自动重试覆盖。

## R2 在线编辑前保存闸门

1. `flushPendingWrites()` 必须调用所有已登记 flusher，并等待 flusher 同步发起的全部真实 PUT。
2. 单个 flusher或 PUT 失败不妨碍其余写入完成，但最终必须抛出包含全部失败的结构化错误。
3. 任一失败时 bridge 停留 HTML 错误态；不得调用 store-projection、pending-mutations、materialize 或挂载编辑器。
4. timer 为空的 flusher必须零写入；清 timer 后不得让旧 timer 在投影读取后再次写库。
5. 当前 108 条基线逐项裁决：2 个零生产消费者移出债务；其余 106 个活路径登记 pending-only flusher。10 个父宿主及 D4 注入保存把完整批次 Promise 纳入 `trackPendingWrite`。
6. 新增或重新出现“私有写盘防抖但未登记”的生产文件必须在 CI 报红；不能用宽泛 allowlist 放行。

## R3 OO→HTML store 镜像原子性

1. 对 store-backed entry，merged projection 镜像 `checklist_responses` 必须与 content revision、content version、representation、entry pointer、application/operation 结果和 outbox 在同一个数据库事务中提交。
2. mirror provider、任意第 N 个 store item、SQL 或序列化失败时，R3.1 所列数据库状态全部回滚；incoming artifact 保持 durable，原 application/operation 落可重试错误。
3. content commit 成功后不得再执行第二次 post-commit store mirror。
4. 镜像调用必须显式 `commit=False`；`store_mirror` 内部任何分支都不得擅自提交。
5. 注册表声明了 dedicated item 但 provider 缺门面或 item 常量时必须 fail-visible，禁止静默 `continue`。
6. 既有 application/operation 重试复用同一 incoming、同一 identity 和同一 operation，不新建第二个业务 revision。

## R4 并发边界

1. 继续复用现有底稿编辑锁，非持锁窗口写 checklist 仍返回 423。
2. 原子镜像必须运行在 `ContentMutationService` 已持有的 per-wp advisory + row lock 内，不新建第二套锁键。
3. HTML CAS 与 OO 三方合并职责分开：CAS 防普通表单并发覆盖；content revision/fence 防 representation 并发推进。

## R5 验收

1. 前端覆盖：保存中再编辑、旧版本冲突、flusher 失败、在途失败、多个失败聚合、timer 为空、真实 PUT 延迟与失败时模式切换零 materialize。
2. 后端覆盖：严格/兼容 CAS、整批原子、镜像成功同事务、镜像中途失败全回滚、dedicated provider 缺口 fail-visible、既有 retry 不增第二 revision。
3. 变异至少覆盖：去掉 `if_match`、吞 pending 失败、去掉父 handler tracking、把 mirror 移回 commit 后、把 `commit=False` 改回默认、恢复 dedicated 软跳过。
4. 在【测试】项目浏览器验证：保存后立刻切在线编辑；模拟保存失败时保持 HTML；OO 改值回表单后刷新仍一致。
5. 不写真实业务项目；不在本轮自动应用新迁移。本设计不需要新增迁移。
