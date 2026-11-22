# 平台重任务、交互性能与容量闭环 — 设计

## 1. 现状确认与不重复边界

2026-11-01 现读代码、active spec 与历史实测后确认：

- 已完成：render-config 压缩与请求收敛、底稿列表一次取回、Ledger keyset 窗口、COUNT token、后端 lazy route/纯 ASGI/路由索引、overlap reload、SSE replay、GC 空闲门、GET single-flight。
- 正在由前置 spec 完成：保存 edit revision/follow-up、Vite manifest、重组件异步边界、包体预算、verified dist 与 Nginx。
- 仍存在：`export_progress_service`/`bulk_async_runner` 的内存任务和同步 ZIP；`ledger_import_application_service.preview` 在 async 路径同步 openpyxl；`libreoffice_pool` 无等待上限且 profile 用 pid+tid；公式推送逐单元格 adapter；合并附注章节×节点读写；TB/附注/合并大表和深 watch；单 worker、直连池 150、PgBouncer 默认关闭；6000 报告缺失且旧 runner 可零样本假绿。

本 spec 不重新实现上述已完成能力。真实 6000 VU、PgBouncer 切流、外部 OCR/LLM 容量属于需专用环境的验收，不以本机模拟替代。

## 2. ROI 与批次

| 批次 | 主要文件规模 | 收益 | 风险 | 裁决 |
|---|---:|---|---|---|
| A 事件循环止血 | 8~12 文件 | 大文件不拖慢全站 | 低~中 | 先做 |
| B 耐久任务 | 15~25 文件 + 迁移 | 重启恢复、跨 worker | 高 | 独立小批 |
| C SQL 放大 | 8~15 文件 | 大项目公式/合并提速 | 中~高 | 先基准再改 |
| D 大表交互 | 10~20 文件 | 滚动与输入响应 | 高 | TB canary 后扩展 |
| E 容量架构 | 部署+事件+任务 | 支撑 6000 | 高 | 最后灰度 |

## 3. 重文件处理

- Ledger preview 使用 `anyio.to_thread.run_sync` 执行纯解析；上传解析前校验文件数、累计字节、sheet 和 preview_rows。AsyncSession 不跨线程。
- 导出先一次查询元数据与权限，工作线程直接写 `storage/.../.tmp`，完成后原子改名；Web 只返回 task id，下载用 `FileResponse`。
- bulk import 先流式落 spool，任务载荷只存路径、摘要和大小；任务结束统一清理。CPU/压缩线程池与 OCR 分离。
- LibreOffice 以 UUID profile 隔离，`communicate()` 同时排空 stdout/stderr；semaphore acquire 有超时，队列达到上限立即返回 429/503 + Retry-After。
- 所有 StreamingResponse/FileResponse 路由在返回前结束查询事务；生成器只捕获路径和标量。

## 4. 耐久任务内核

复用 `ImportJobRunner` 的 lease/recovery，而非增加第三套内存队列。公共 job 至少包含 operation、project/user、status、progress、stage、payload_ref、result_ref、attempt、lease_owner/lease_until、heartbeat、error、idempotency_key。消费者用 `FOR UPDATE SKIP LOCKED` 认领，副作用写入带 attempt fence。

Web 提交只做权限、预算、spool 和 job INSERT；worker 每个 DB 阶段使用短 session，CPU/网络阶段不持连接。SSE 只是通知，状态 GET 是权威恢复路径。取消在文件批次、章节、底稿和 LLM 调用前检查。

## 5. SQL 与算法

- 公式推送：一次取全部目标底稿；adapter 按底稿批量校验归属、读版本并条件 upsert；note rule 按章节分组后一次锁、一次 deepcopy、一次写。
- 合并附注：一次预取 `(section,node)` 记录和全部公式；内存后序计算，按章节保存点批量写；`None=全部`、`[]=零工作/422`。
- 知识检索先保存真实 EXPLAIN；正文使用 tsvector/GIN 或经证明的 pg_trgm，向量量级达到阈值后启 pgvector；缓存键必须含权限和索引版本。
- Ledger 大导入按阶段测量，优先 COPY/staging + set-based merge，禁止用扩大 CHUNK 掩盖事件循环阻塞。

## 6. 前端响应

TB 作为虚拟化 canary：固定行高、活动单元格才挂编辑器，选区/复制/右键/公式/注释逐项对拍。附注和合并随后复用。深 watch 改 edit revision/patch queue，合计仅重算受影响行。

HTTP 增 `_background`，后台请求不进入全局 NProgress；自动重试默认仅 GET/HEAD，写请求只有 `X-Idempotency-Key` 才可重试。大 payload 去重键由业务 operation id 提供，通用拦截器不再完整 stringify 两次。

## 7. 容量与验收

先增加 pool wait/hold、event-loop lag、任务 queue age、Office/OCR/LLM wait 指标。PgBouncer 2%→25%→100% 灰度，确认 RLS 和事务语义后再外置进程状态、扩 2/4/8 worker。

容量工具必须校验每阶段实际 user/request/sample 非零；ID 来自 seed 回执，账号与项目分池；写压测只在可销毁 PG。最终 6000 VU 30 分钟同时采集 API p50/p95/p99、错误分类、pool、PG、Redis、WAL、RSS、event-loop lag 和业务恒等式。