# 平台重任务、交互性能与容量闭环 — 需求

来源：2026-11-01 平台性能体检及用户“按建议来”。本 spec 承接 `platform-performance-user-experience-closure` 的保存协调与正式构建，不重复已完成的 render-config、Ledger 窗口、启动、SSE、GC 和 GET single-flight。

## R1 安全边界与可观测性

1. 所有改动先保业务结果、权限、CAS、审计和事务语义，再优化耗时。
2. 共享 PG 不运行写压测；容量测试必须指向显式声明的可销毁数据库。
3. 连接池必须暴露 checked-out、等待、超时和持有时长；事件循环必须暴露 lag。
4. 交互 API、后台任务、Office/OCR/LLM 队列分别记录排队和执行时间，不以平均值掩盖长尾。
5. 任何外部环境未具备的验收保持阻塞，不得以模拟或小并发外推为完成。

## R2 重型文件处理不得阻塞 Web

1. 账表预览中的 openpyxl/CSV CPU 解析必须离开 Web 事件循环，并有文件数、总字节、sheet 和预览行上限。
2. 底稿批量导出必须批量取元数据，直接压缩到临时文件，不在内存保存双份 ZIP；列表页统一使用异步任务入口。
3. 批量导入上传先落受控 spool，只向任务传文件引用；并发任务、单用户与单项目均有上限。
4. LibreOffice 每任务使用唯一 profile，读取子进程输出不得死锁，排队有上限和超时；超载返回可重试中文状态。
5. 流式附件下载在响应体发送前释放 DB 会话，慢客户端不得占用 PG 连接。

## R3 耐久任务与真实进度

1. 导入、导出、公式推送、附注批量 AI 和合并重新汇总采用统一耐久任务语义：queued/running/succeeded/failed/cancelled。
2. 任务状态、结果引用、heartbeat、lease、attempt 和 fencing 必须跨进程、重启可恢复。
3. CPU/文件 I/O 阶段不得持有 AsyncSession；数据库写入拆成短事务。
4. 前端显示真实阶段、已完成数、排队原因、可取消状态和失败恢复入口，不使用模拟百分比。
5. operation id 相同的重试不得产生第二个任务或重复副作用。

## R4 批量 SQL 与算法复杂度

1. 公式推送按项目一次取目标底稿，按底稿批量 CAS 写条目，按附注章节一次锁定和写回；SQL 数不得随单元格数线性增长。
2. 合并附注重新汇总一次预取所需章节与节点数据，保留章节 SAVEPOINT 和树后序依赖；`section_ids=[]` 不得隐式执行全部章节。
3. 知识检索先以真实 EXPLAIN 证明计划，再选择 tsvector/pg_trgm/pgvector；权限过滤不得旁路。
4. 大导入按阶段记录 rows/s、WAL、COPY、索引和激活耗时，优先 set-based/COPY，不做逐行 ORM 写入。

## R5 前端交互响应

1. TB、附注和合并核心表按真实 1000/5000 行数据决定虚拟化，DOM 行数有界；编辑、选择、复制、右键和公式能力不得回退。
2. 深层 watcher 改为 edit revision 或行级 patch，只重算受影响数据；自动同步采用单飞 + latest pending。
3. 大响应和保存热路径避免重复 JSON.stringify、全量 clone 和不必要的响应副本。
4. 后台轮询/自动同步不驱动全局 NProgress；写请求只有具备幂等键时才可自动重试。
5. 内网 HTTP 多标签页缺少 Web Locks 时，项目 SSE 仍应单用户单项目一条连接并可围栏接管。

## R6 容量架构与 6000 并发

1. PgBouncer transaction pool 先灰度验证 RLS、SET LOCAL、取消和 prepared statement，再切流；连接预算按副本数计算。
2. EventBus、任务、配额、single-flight 和进度等进程内状态外置后，才能从 1 个 worker 渐进扩到 2/4/8。
3. 压测脚本必须使用 UUID 用户/项目池、信封登录、读写隔离和可回收数据；任一目标阶段无样本必须 FAIL。
4. 隔离环境按 100→1000→3000→6000 VU 阶梯运行，6000 稳态至少 30 分钟，提交原始 CSV、机器可读 JSON 和摘要。
5. 核心读 p95 目标 300ms、p99 1s；全场景错误率低于 1%、核心成功请求低于 0.1%；越权、连接超时、事件丢失和数据损坏必须为 0。

## R7 验收

1. 每批保留改前/改后同输入 A/B，比较业务 hash、SQL 数、DB 时间、CPU、RSS、event-loop lag 和用户首个反馈时间。
2. 前端必须执行正式构建、包体预算、built artifact smoke、针对性 Vitest、单区域类型检查和 Playwright。
3. 后端必须执行隔离单测、静态守卫、取消/重启/幂等故障注入；涉及 PG 时只用专用可销毁库。
4. tasks.md 只在代码和对应验证真实通过后勾选。