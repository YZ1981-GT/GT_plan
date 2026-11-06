# 平台重任务、交互性能与容量闭环 — 任务

完成必须有代码和对应测试/现场证据；外部环境项保持 `[ ]*`。

## 批 0 基线与观测

- [ ]* 0.1 固化当前 production build、核心页面、重任务、连接池与事件循环基线。
  - 🔴 需运行真实后端 + 前端正式构建 + 真实数据项目做 A/B 对照度量；本机无法伪造有意义的基线，保持阻塞。
- [x] 0.2 增加 pool checkout wait/hold/timeout、event-loop lag、任务 queue age 与 Office/OCR/LLM 排队指标。
  - DB pool wait/hold/timeout、event-loop lag、LibreOffice 与 bulk import 深度/年龄此前已有。
  - 本轮补齐统一暴露面 `capacity_slots`（`platform_slot_*` 排队/执行 Histogram + `health.capacity.slots`）：
    LLM 绑定 `llm_client._llm_semaphore` 这个**同一个**信号量（`native_engine` 流式回答也持它，
    经 slot 取用才被计量）；AST 守卫钉住「不得绕过 slot 直接 `async with _llm_semaphore`」。
  - 🔴 OCR **没有**准入队列（`unified_ocr_service` 走默认线程池、`ocr_service_v2` 自带 4 线程池），
    故只计在飞数与执行时长，快照用 `bounded=False` 显式声明，不伪造 queue depth；守卫反向钉住该声明。
  - AI 耐久队列（`platform_jobs` + `ai_task_items`）由新 `capacity_queue_worker` 周期采样
    （两条队列各用独立 session，PG 上一条失败不拖垮另一条）；health 只读快照、不在请求里扫任务表。
    采样失败标 `available=false` 并保留上次已知深度，**绝不发布 0**（读不到 ≠ 队列空）。
  - 验证：`test_capacity_slots_and_queues.py`(15) + `test_platform_capacity_metrics.py` 全绿；
    8 条磁盘变异全 RED；真库单跑 `test_shared_llm_semaphore_is_held_during_streaming` 通过（生产调用点）。
- [x] 0.3 建立不会写共享 PG 的性能测试选择器与专用数据库硬闸门。
  - 压测发起闸门 `tests/load/load_guard.py`（单一来源）：写压测除 `GT_LOAD_ALLOW_WRITES=1`
    + `GT_LOAD_DISPOSABLE_ENV=YES` 外，必须显式声明 `GT_LOAD_DISPOSABLE_DB_URL`，且该库不在
    共享/默认库黑名单（audit_platform/postgres/gt_plan/metabase）、不等于当前 `DATABASE_URL`。
    接入 run_baseline / run_final 的 main **以及 locustfile `on_test_start`**——无论用哪个 runner
    或裸 `locust` 命令发起，发任何请求前都过闸门，不通过退出码 2。
  - 性能测试选择器闸门 `tests/_perf_gate.py`（接入根 conftest 收集期）：选中「`perf` ∧ `pg_only`」
    的写真库用例（如 `test_procedure_performance` 会插 5000 行）而 `DATABASE_URL` 是 PG 时，
    必须 `GT_PERF_DISPOSABLE_DB=YES` 且库名非黑名单，否则 `pytest.UsageError` 整次失败；
    纯内存 perf（`-m 'perf and not pg_only'`）与非 PG 环境不触发。
  - 验证：`test_load_guard.py`(7) + `test_perf_write_gate.py`(5) + 既有 load_config/evidence_gate 全绿（21）；
    真实收集路径三态实证——未声明库硬失败 / 声明非黑名单库放行 7 collected / 声明但 `audit_platform` 硬失败。

## 批 A 事件循环与文件内存止血

- [x] A1 Ledger preview 解析移到受控线程；文件数、总字节、sheet、preview_rows 有硬上限和真实进度。
  - 线程隔离（`anyio.to_thread.run_sync`）、文件/总字节/sheet/preview_rows 上限、CSV 有界缓冲、
    复杂大表禁止 full mode 均已由前置提交完成。
  - 「改为可恢复任务」经评估不适用于 preview（秒级同步交互，不适合耐久任务队列）：
    R2.1 的全部验收标准（不阻塞 Web 事件循环 + 有硬上限 + AsyncSession 不跨线程）已满足。
- [x] A2 批量导出一次取元数据，在线程直接写临时 ZIP 后原子改名；无 BytesIO 双份驻留。
- [x] A3 前端底稿批量下载切异步任务、展示真实进度/失败/下载，不再同步等待整包。
- [x] A4 bulk import 先落 spool，只传路径；增加全局/用户/项目并发与内存预算。
- [x] A5 LibreOffice 唯一 profile、communicate、排队上限/acquire timeout、Retry-After 与指标。
- [ ] A6 流式下载提前释放 DB，会话与文件句柄在取消时及时关闭。
  - 已完成：附件、底稿 ZIP、bulk SSE/下载、chain/ledger SSE、doc AI 外层 session、
    `wp_chat`（请求内 prepare_chat + 项目权限，流期纯 LLM）、`working_paper`/`wp_download`
    的单件 `FileResponse` 与打包下载、`wp_template_download`、`wp_xlsx_export`、
    `wp_template_files` 的 function-scope DB/stream gate；本轮第二波补 `wp_render_config.export_template`
    与 `wp_export_import_router.export_with_metadata` / `batch_export_enhanced` 三条下载路由
    `function-scope DB + require_project_access_stream`。`test_streaming_db_scope.py` 15 passed。
  - 🔴 仍有大量低频历史导出路由尚未迁移（含 `wp_render_strategies/*_import_export.py` 约 20 条、
    `wp_onlyoffice_router` 机对机 WOPI 路径、部分 wp_sync 路由），必须逐个确认响应生成器不再读 DB
    后才能改 scope，保持未完成。
- [x] A7 同输入验证文件 SHA/ZIP 清单/导入摘要不变，并测并发时 health/event-loop lag。

## 批 B 耐久任务

- [x] B1 设计并迁移公共 durable job/job attempt，V/R 成对且动态取号。
  - 由前置提交 a6c1fa93a 落地：V243/R243 `platform_jobs` + `platform_job_attempts` 两表（status 六态、lease/attempt 围栏、idempotency 唯一键）；
    ORM `platform_job_models.py`（PlatformJob + PlatformJobAttempt）。
- [x] B2 实现 claim/lease/heartbeat/fence/retry/cancel/idempotency 与恢复 worker。
  - 由前置提交 a6c1fa93a 落地：`platform_job_service.py`（create_or_get_job / claim_next with SKIP LOCKED /
    renew_lease / update_progress 单调 / finish_success / finish_failure with backoff / finish_cancelled /
    request_cancel / _settle_exhausted / enforce_active_capacity / queue_snapshot）+
    `platform_job_worker.py`（run_once 轮询 + heartbeat + 租约丢失检测 + 故障终态写入）+
    `platform_job_registry.py`（register_executor / get_executor）。
  - 验证：`test_platform_job_service.py` + `test_platform_job_worker.py` + `test_bulk_durable_job_executor.py`
    共 12 passed（幂等、claim 竞争、租约过期接管、attempt fence、进度单调、重试退避、取消、容量限制）。
- [x] B3 迁移底稿导出与 bulk import；旧内存任务只作兼容读并设退役日期。
  - 底稿文件打包导出迁入 `workpaper_pack_export` executor：提交端只做可见集过滤 +
    `create_or_get_job`；执行端重新 gate 当前权限、一次取元数据、关闭 AsyncSession 后线程写唯一
    attempt artifact；逐项进度先经 report fence 落库再发 SSE；DB 成功终态 commit 后才发 complete。
  - 状态/下载端限定 `operation=workpaper_pack_export` + actor + 当前项目 readonly 权限，拒绝其他
    durable job ID；`result_ref.zip_path` 必在 EXPORT_DIR 内，阻断任意文件读取。取消/失 lease 清理
    自己 attempt artifact，不通知伪完成。
  - bulk import 已由前置提交迁移（`durable_job_executor.py` + `bulk_async_runner` spool admission）。
  - `ExportProgressService` 已无生产创建调用，仅兼容读取至 `2027-02-05`。
  - 验证：`test_export_pack_durable.py`(11) + 既有导出/平台任务回归共 43 passed；lint 全绿。
- [x] B4 迁移公式推送、附注批量 AI、合并重新汇总；按阶段发 typed SSE。
  - 公式推送：`formula_push/durable_job_executor.py` 注册 `formula_push`，实际写入 UI 传
    `async_mode=true`，worker 重新校验 edit 权限后运行引擎；试跑和旧 API 客户端保留同步契约。
  - 合并附注重新汇总：`consol_note_reaggregate_executor.py` 注册 `consol_note_reaggregate`，
    worker 重验项目/合并锁/企业树/DAG，`reaggregate_subtree(progress=...)` 在每章节边界检查
    cancellation/lease fence；取消时外层事务回滚。两处前端入口均改到 `reaggregate-async`。
  - 附注批量 AI 已有 V238 `AiTaskJob/AiTaskItem` + `ai_task_worker`（lease、重启接管、取消、
    幂等、`ai.task.updated`）；无需再把同一任务双写到 platform_jobs。
  - `platform.job.updated` 结构化 SSE 唤醒状态重拉，状态 GET 为权威。验证：公式 27、合并 39、AI 34 后端测试全绿；前端相关 46 tests 全绿。
- [x] B5 前端统一任务状态组件，断线后从状态端点恢复。
  - 新增 `platform-jobs` 项目级 GET/cancel/retry 路由（actor + 项目权限，retry 建新 job 保原审计）；
    `platformJobs.ts` 统一六态、SSE 唤醒 + 1.5s 状态轮询、断线恢复；`PlatformJobProgress.vue`
    复用 `AsyncJobProgress`，提供进度、取消、重试、终态事件。
  - 已接入公式推送面板和合并总览重新汇总；任务状态 API/组件测试 20 passed。
- [x] B6 kill/reload/重复提交/租约过期故障注入证明零重复副作用。
  - `test_platform_job_fault_injection.py`(5)：kill 后恢复（lease 过期 → 新 worker 接管 + 旧 claim fence 拒写 +
    attempt 记录 lost_lease/succeeded）、重复提交幂等（3 次同键只建 1 个 job）、attempt 耗尽终态（max_attempts=1
    失败后不可再认领）、运行中取消（cancel_requested 后 finish_success 被 fence 拒 + finish_cancelled 成功）、
    并发认领只有一个赢（SQLite CAS / PG SKIP LOCKED）。

## 批 C 批量 SQL 与重计算

- [ ]* C1 公式推送现状 statement counter 与 10/1000/10000 单元基线。
  - adapter 级 10/1000/10000 计数守卫已完成（现为固定 3 次 cursor execute）。
  - 🔴 完整 run 基线需专用可销毁 PG + 真实项目数据（10000 公式单元），本机无法伪造，保持阻塞。
- [ ] C2 目标底稿批取、mutation 批量 CAS、附注按章节一次锁写；逐项结果对拍。
  - 已完成：目标底稿单次批取、同底稿 mutation 一次锁读 + 批量 CAS；`test_formula_push_engine_locate` /
    batch-c-note / batch-c-k-cycle / reaggregate 选集 53 passed。本轮新增统一写入内核骨架
    `app/services/disclosure/note_section_write_kernel.py`（`mutate_note_section` + `stable_hash`）：
    PG 下取 `pg_advisory_xact_lock` + `FOR UPDATE`，非 PG 自动降级；一次 `copy.deepcopy` 隔离工作副本；
    按 JSON canonical 哈希判 changed，变才 `flag_modified` + 一次 UPDATE；mutator 允许改 note
    的 `text_content` / `status` / `guidance_text` 等字段，退出前无条件 flush。6 单测全绿。
  - 🔴 未完成：`disclosure_engine.update_note` / `note_followup` / 合并附注写入方尚未切到新内核；
    真实 PG 并发 barrier 必须在专用环境里跑双连接重叠章节用例验证，保持未勾。
- [ ] C3 合并附注一次预取记录/公式、内存后序、批量写；修正空 section_ids 语义。
  - 已完成：空数组零工作、记录/公式预取、内存后序和章节 SAVEPOINT/flush；53 个相关回归通过。
    C2 的统一写入内核骨架同时可服务合并附注章节级写入（见上条）。
  - 🔴 未完成：差额节点仍经 `fill_by_formula(...)`，不能把它写成不存在的 `_compute_elimination`
    “纯内存内核”；叶子来源整章批取与真实 PG 并发对拍仍需专门收口。
- [ ] C4 Ledger 导入分阶段 profiler；COPY/staging/set-based 合并把真实大项目目标压到 5 分钟内。
  - 本轮完成 profiler 骨架 `app/services/ledger_import/profiler.py`（`StagedProfiler` + `StageRecord`）：
    PG 下 `pg_current_wal_lsn()` + `pg_wal_lsn_diff` 自动采集每阶段 WAL 增量字节，非 PG 环境
    `wal_bytes=None`；`rows/sec = rows / duration_s`，支持 `record_rows()` 对 COPY 真实返回行数
    事后补记；mutator 抛异常时记 `error` 后原样向上抛，不吞异常；`to_dict()` 产 JSON 可序列化的
    stage/total 摘要，供 pipeline / progress / API 直接消费。7 单测全绿。
  - 🔴 未完成：pipeline（`services/ledger_import/pipeline.py` / smart_import_engine）尚未接入
    `StagedProfiler`，需要让 staging / COPY / index / activation 四阶段都走 context manager；且
    rows/s、WAL、COPY 真实基线须在专用可销毁 PG + 真实大项目数据上跑，本机无法伪造，保持阻塞。
- [ ]* C5 知识词法/向量路径真实 EXPLAIN 与量级基准；按证据实施索引/pgvector。
  - 🔴 需真实文档量级（万级分块）+ 专用 PG 做 EXPLAIN 对比，本机无法伪造，保持阻塞。
  - V263 向量扩展 + HNSW 索引已建；tsvector/GIN 路径代码已有；量级基准与索引选择待证据。

## 批 D 前端大表与请求反馈

- [ ] D1 TB 1000/5000 行虚拟化 canary，保持编辑、选区、右键、注释、公式和可访问性。
  - 现有 GtVirtualTable 不支持离屏逻辑选区/编辑，未在交互契约齐全前冒险切生产路径。
  - 🔴 需先补齐虚拟化表的编辑/选区/右键/公式/注释交互契约（约 1000 行前端），属独立 spec 工作量。
- [x] D2 TrialBalance 全表 deep watch 改行级增量重算。
- [ ] D3 附注与合并表按 canary 结果接虚拟化；活动格才挂编辑器。
  - 🔴 依赖 D1 canary 结果（虚拟化交互契约齐全后才能扩展到附注/合并），保持未完成。
- [x] D4 披露自动同步改 revision/patch 单飞 + latest pending，失败可见且可重试。
  - `useDisclosureAutoSync` 保持 100+ 披露 Tab 的既有调用签名，新增单调 revision、单飞 drain、
    latest pending（飞行期间只跑最后一次 closure）、errorMessage/onFailed/中文提示和 retry；不再
    fire-and-forget 吞失败。各 Tab 的 payload builder 仍是唯一真源，latest closure 在执行时读取最新状态。
  - 验证：7 个 Vitest（防抖、单飞、latest、失败可见、retry、只读 fail-closed、取消）+ 浏览器实测
    两次连续调度只执行 latest（revision=2）。
- [x] D5 HTTP `_background` 不驱动全局 NProgress；无幂等键的写请求不自动重试。
- [ ]* D6 大 GET/保存热路径减少 clone/stringify；用 1/10/50MB 夹具记录长任务和 heap。
  - 代码层优化已完成（普通 JSON 写请求只 stringify 一次、完整正文指纹、single-flight follower 单次
    structuredClone、TB debounce 到 drain 才冻结）。浏览器 1/10/50MB generic serialization+clone 探针为
    3.8/19.2/87.0ms，但这不是生产 GET/保存热路径的 A/B 证据，保持专用环境阻塞。
- [x] D7 内网 HTTP 多标签 SSE 围栏选主；1/6/12 标签始终单项目一条连接。
  - `projectEventStreamShare` 保留 Web Locks 优先；HTTP 无 locks 时以 BroadcastChannel + localStorage
    lease 选主，确定性冲突让位关闭旧连接，leader 关闭后 follower 接手并 replay。Vitest 模拟独立标签
    1/6/12 个均只有 1 条连接（11 tests）；内网 `http://192.168.20.60:3030` 实测
    `isSecureContext=false`/locks=undefined/BC+storage 可用，1/6/12 share 实测都只有 1 个 leader。

## 批 E 容量架构

- [ ]* E1 PgBouncer transaction 模式契约与 2%→25%→100% 灰度脚本；连接预算按副本计算。
  - 🔴 需部署环境（PgBouncer 进程 + 真实后端 + RLS/SET LOCAL 验证），本机无法伪造，保持阻塞。
- [ ] E2 EventBus、任务、配额、进度和失效状态外置；2/4/8 worker 零丢失/零重复验证。
  - 🔴 platform_jobs / AI tasks 已 DB 耐久，SSE 跨标签已共享；但 EventBus、配额和失效状态仍有进程内部分，
    尚未完成跨 worker 外置和 2/4/8 worker 验证。
- [x] E3 修正 Locust UUID/信封/账号池/端点；6000 阶段无样本强制 FAIL。
- [ ] E4 构建可销毁大数据容量环境与分布式负载机。
  - 🔴 Docker PgBouncer transaction 配置和连接预算契约已在库；尚无独立容量 DB、种子数据和分布式 Locust 启动编排。
- [ ]* E5 100→1000→3000→6000 VU，6000 稳态 30 分钟；提交原始 CSV/JSON/摘要。
- [ ]* E6 达成核心读 p95≤300ms、p99≤1s、核心错误率<0.1%，零泄露/超时/事件丢失/数据损坏。

## 收尾

- [ ]* F1 相关测试、正式构建、包体预算、Playwright、PG 计划和故障注入全通过。
  - 2026-11-05 本轮本地证据：后端集中回归 194 passed（包含 B1/B2/B3/B4/B5/B6 全部、A6 streaming
    scope 13 项、ai_task、load guard 与 evidence gate；全程 `DATABASE_URL` 指向不存在的 PG
    库触发 sqlite 降级，不写共享数据）· 前端 Vitest 定向 69 passed（PlatformJobProgress、
    platformJobs、FormulaPushPanel、ConsolNoteView、ConsolidationIndex.grid、useDisclosureAutoSync、
    projectEventStreamShare、sseEventTypes）· `app.main` import 冒烟通过 · 定向 Ruff 对
    本次 owned 后端文件全绿 · ESLint 对 owned 前端文件 0 error · `vite build --mode production`
    通过 · `smoke-built-artifact.mjs` 通过（SPA 深链、动态 chunk、`/api` 与 `/wopi` 代理齐全）·
    内网 `http://192.168.20.60:3030` 浏览器实测 D4/D7（披露自动同步 latest=2 + SSE 1/6/12 标签页
    均单连接）。
  - 2026-11-06 增量：A6 第二波 3 条路由（`wp_render_config.export_template` /
    `wp_export_import_router.export_with_metadata` / `batch_export_enhanced`）接入 function-scope DB
    + `require_project_access_stream`，`test_streaming_db_scope.py` 13→15 passed；C4 profiler 骨架
    `app/services/ledger_import/profiler.py` + 7 单测全绿；C2/C3 附注章节原子写入内核骨架
    `app/services/disclosure/note_section_write_kernel.py` + 6 单测全绿；全部 owned 文件 Ruff /
    Diagnostics 清零。接入 pipeline 与真实 PG 并发 barrier 等验收仍留在对应 `[ ]` / `[ ]*` 项下。
  - 仍阻塞且本机无法伪造：①`check-bundle-budget.mjs` 按匿名排名比对，heavy-office/heavy-excel/
    WorkpaperEditor 的历史分类误判与 WIP 无关，须另立预算工具收口（详见该脚本注释与 design
    §7）②真实 PG 计划 / 大项目公式 run 基线 / 底稿编辑器 Playwright 在共享 PG 禁跑，须
    `GT_LOAD_DISPOSABLE_DB_URL` 专用库 + 真实数据 ③6000 VU 梯度与 30 分钟稳态（见 E5/E6
    `[ ]*`）④PgBouncer transaction 灰度与跨 worker EventBus/配额外置（E1/E2）。本条保持 `[ ]*`
    至最终容量环境验收完成。
- [x] F2 更新 6000 前置文档，勘误历史零样本假绿，不改 append-only 历史记录。
  - `backend/tests/load/README.md` 写清可销毁 DB 三重闸门、perf+pg_only 专用库、原始 CSV/summary.json
    归档要求和零样本禁止外推；`run_final.py` 不再删除 Locust CSV，新增 `--evidence-dir` 与机器可读
    `summary.json`（不含凭据）。17 个 load/evidence gate 测试全绿。
- [x] F3 更新 INDEX/memory；只提交本任务 owned 文件。
  - INDEX 更新为 21/37（余 16，其中外部环境 8）；memory 在 300 行上限内合并记录 durable jobs、
    HTTP fallback SSE lease 和专用容量环境边界。