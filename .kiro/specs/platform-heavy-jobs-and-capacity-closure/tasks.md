# 平台重任务、交互性能与容量闭环 — 任务

完成必须有代码和对应测试/现场证据；外部环境项保持 `[ ]*`。

## 批 0 基线与观测

- [ ]* 0.1 固化当前 production build、核心页面、重任务、连接池与事件循环基线。
  - 🔴 需运行真实后端 + 前端正式构建 + 真实数据项目做 A/B 对照度量；本机无法伪造有意义的基线，保持阻塞。
  - 2026-11-06 工具增量（测量与门禁纠偏批，不改勾选）：`run_final.py --baseline <上一轮 summary.json>`
    真正参与对比（此前参数只解析不使用）——路径无效在发压前退出；按聚合 / 同名端点 / 同并发阶段给差值，
    只展示、不进 PASS 门。运行期 `ResourceSampler` 每 15 秒采 `/api/health`、`/metrics` 与负载机
    CPU / 内存写 `resource_samples.json`，读不到记 error、不写 0。`business_hashes` 尚无生产者，
    相等性恒为 None —— 业务恒等式探针仍待 E4 容量环境。
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
- [~] A6 流式下载提前释放 DB，会话与文件句柄在取消时及时关闭。
  - 已完成：附件、底稿 ZIP、bulk SSE/下载、chain/ledger SSE、doc AI 外层 session、
    `wp_chat`（请求内 prepare_chat + 项目权限，流期纯 LLM）、`working_paper`/`wp_download`
    的单件 `FileResponse` 与打包下载、`wp_template_download`、`wp_xlsx_export`、
    `wp_template_files` 的 function-scope DB/stream gate；第二波补 `wp_render_config.export_template`
    与 `wp_export_import_router.export_with_metadata` / `batch_export_enhanced` 三条下载路由
    `function-scope DB + require_project_access_stream`。`test_streaming_db_scope.py` 16 passed。
    2026-11-06 增量：`_cycle_import_export_common.register_cycle_import_export_endpoints` 内闭包
    `export_template` / `export_data` 一处收口 `function-scope DB + stream auth`，`import_data`
    显式保留请求级 session —— 单处改动辐射 L/M/N/K 等约 60 个 `_import_export.py` 文件的共享导出
    实现；新增闭包源码文本断言钉死导出两处迁移、导入处不改。
  - 🔴 仍有历史导出路由尚未迁移（`wp_onlyoffice_router` 机对机 WOPI 路径、部分 wp_sync 路由、
    `_x3_adjustment_import_export._register_shape_a` 的 export 闭包、各 `_g*_bond_investment_*`
    独立实现），须逐个确认响应生成器不再读 DB 后才能改 scope，保持未完成。
  - 勘误（2026-11-06 整体复核，AST 现扫，现算值禁写死）：返回 StreamingResponse / FileResponse 的路由共 213 个，
    已 function-scope 21、不取 DB 51，**仍为请求级 `Depends(get_db)` 的候选 141 个**——上条「少量历史路由」
    低估了规模，余量是跨 100+ 路由的系统性迁移，每条都要先判响应期是否仍读 DB。
  - **2026-11-16 更新（棘轮守卫已建，`[ ]`→`[~]`）**：新建 `backend/scripts/check/check_streaming_db_scope.py`
    + 冻结基线 `backend/data/streaming_db_scope_baseline.json`。**现算口径更新**：AST 扫 `backend/app/`
    得 **112 个候选**（比上条 141 少 29，因为期间已有 47 个路由迁到 function-scope 或不取 DB）；
    `--check` 现跑 **exit 0**。守卫保证三件事：①候选数**只减不增**（新增流式路由必须一开始就
    function-scope，否则点名报出）；②基线缺失即失败（不能静默退化成「无候选」）；③基线**不得虚高**
    （`_MAX_BASELINE_INFLATION=5`，防「改大基线蒙过关」）；`--write` 在候选增加时**拒绝写盘**。
    **为什么冻结而不是硬修**：112 条跨 100+ 文件，每条都要先判「响应生成器是否仍读 DB」
    （读 DB 的不能简单改 scope，否则响应期拿不到数据），属独立 spec 工作量；
    按 memory ㉗③「规模超单轮能力时冻结棘轮而非硬修」。
    **验证**：`test_streaming_db_scope_ratchet.py` 11 例（基线非空/字段完整/扫描器真命中/
    `--check` 通过/基线缺失失败/候选增加失败/基线虚高失败/`--write` 拒绝上调/tasks.md 有登记）。
    **仍未做**：逐条迁移（本批只冻结与守护）、真实大文件并发下的连接池对账。
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
  - 勘误（2026-11-06 推送前合并核查）：`app/routers/platform_jobs.py` 随 a813aede4 入库，但没在
    `router_registry` 注册 ⇒ 三个端点在应用里恒 404，本条此前的 `[x]` 是假绿；既有守卫
    `test_router_modules_mounted.py` 自那次提交起一直红，而当时的回归选集没带它（只测了自建 app 的
    router 单测）。已在 `router_registry/system.py` 注册；`app.main` 实际挂上 3 条路由，
    挂载守卫 + 路由遮蔽守卫 + router 单测 28 passed。
- [x] B6 kill/reload/重复提交/租约过期故障注入证明零重复副作用。
  - `test_platform_job_fault_injection.py`(5)：kill 后恢复（lease 过期 → 新 worker 接管 + 旧 claim fence 拒写 +
    attempt 记录 lost_lease/succeeded）、重复提交幂等（3 次同键只建 1 个 job）、attempt 耗尽终态（max_attempts=1
    失败后不可再认领）、运行中取消（cancel_requested 后 finish_success 被 fence 拒 + finish_cancelled 成功）、
    并发认领只有一个赢（SQLite CAS / PG SKIP LOCKED）。

## 批 C 批量 SQL 与重计算

- [ ]* C1 公式推送现状 statement counter 与 10/1000/10000 单元基线。
  - adapter 级 10/1000/10000 计数守卫已完成（现为固定 3 次 cursor execute）。
  - 🔴 完整 run 基线需专用可销毁 PG + 真实项目数据（10000 公式单元），本机无法伪造，保持阻塞。
  - 守卫位置（2026-11-06 复核）：`tests/formula_runtime/test_workpaper_adapter.py::
    test_apply_many_statement_count_is_constant_for_existing_rows`；完整 `FormulaPushEngine` run 的
    statement count 与真 PG 基线仍缺。
  - **2026-11-16 补（引擎级 statement 计数守卫已建，`[ ]*` 保持——余真 PG 基线）**：新建
    `backend/tests/test_formula_push_statement_count.py`（2 例）。在**真 SQLite engine** 上挂
    `before_cursor_execute` 统计真发出的 SQL，跑完整 `FormulaPushEngine.run_and_commit`
    （项目年度校验 → 有效规则 → 找底稿 → binding 取数 → CAS → 状态 upsert → 运行记录）。
    **实测（现算，禁写死）**：目标单元 1 / 10 / 50 时 SQL 条数均 **14 条**、`changed_items` 分别
    1 / 10 / 50 ⇒ 引擎全链路的写回是**常数级**，R4.1「SQL 数不得随单元格数线性增长」在引擎层成立
    （此前只验过 adapter 一层）。棘轮 `_MAX_STATEMENTS_PER_RUN = 20`（只降不升）。
    变异：在 `adapter.apply_many(mutations)` 前逐条目插 `SELECT 1` ⇒ 变 15 / 24 / 64 条，2 例全 RED；
    `engine.py` 逐字节还原、`git diff` 干净。
    **仍未做**：真 PG + 10000 公式单元的实际基线与耗时（需专用可销毁库 + 真实项目数据）。
- [ ] C2 目标底稿批取、mutation 批量 CAS、附注按章节一次锁写；逐项结果对拍。
  - 已完成：目标底稿单次批取、同底稿 mutation 一次锁读 + 批量 CAS；`test_formula_push_engine_locate` /
    batch-c-note / batch-c-k-cycle / reaggregate 选集 53 passed。统一写入内核骨架
    `app/services/disclosure/note_section_write_kernel.py`（`mutate_note_section` + `stable_hash`）：
    PG 下取 `pg_advisory_xact_lock` + `FOR UPDATE`，非 PG 自动降级；一次 `copy.deepcopy` 隔离工作副本；
    按 JSON canonical 哈希判 changed，变才 `flag_modified` + 一次 UPDATE；mutator 允许改 note
    的 `text_content` / `status` / `guidance_text` 等字段，退出前无条件 flush。2026-11-06 增量：
    新增 `mutate_note_by_id` 变体 + `disclosure_engine.update_note` 切至内核（保留 pushed_row_violations
    409 / note_edit_stamp 戳章语义，135 passed = pushed_row_guard + edit_stamp + ai_fill + section_write_kernel
    + module_attr + disclosure_notes_hardening）。
  - ✅ 2026-11-15 补：**`note_followup` 链已取章节级 advisory 锁**。`note_section_write_kernel` 新增只取锁入口 `acquire_section_lock`（不读不写、不 deepcopy；非 PG 返回 False 不抛），`note_workpaper_pull_service._apply_note_formulas` 在 `db.begin_nested()` 内、`execute_note_formulas` **之前**逐章节取锁 ⇒ 同 `(project, year, section)` 的并发刷新/推送串行，不同章节仍并行；SAVEPOINT 只管失败隔离、不管并发的缺口补齐。顺带修内核健壮性：原先直接访问 `db.bind.dialect`，遇无 `bind` 的 session 替身（`test_note_workpaper_pull_service._NestedDb`）整条链抛 AttributeError 并被误记成「公式执行失败」⇒ 抽 `_dialect_name(db)` 用 `getattr` 兜底，非 PG 一律 no-op。守卫 `test_note_followup_section_lock_wiring.py`（4 例，AST 判「真调用 / 在公式执行之前 / 在 sections 循环内 / 内核有只取锁入口」），磁盘变异删锁调用 **3/3 RED**、逐字节还原。选集 25 passed（锁接线 + pull service + write kernel）+ 前一轮 30 passed。
  - 🔴 仍未完成：**真实 PG 并发 barrier**（双连接重叠章节用例）必须在专用可销毁 PG 上跑，本机无法伪造，保持未勾；合并附注（C3）的差额节点与整章批取同属该项。
  - **2026-11-16 补：真实 PG 并发 barrier 已跑通（`[ ]` 保持——差额节点与整章批取仍缺）**。
    新建 `backend/tests/test_note_section_lock_concurrency_pg.py`（**5 passed**，一次性库
    `gt_heavy_jobs_barrier` 上 60 秒）。隔离用**提交型临时 schema**（复用
    `level_backfill_world` 既有做法）：`CREATE SCHEMA note_lock_<rand>` + 世界引擎
    `NullPool` + asyncpg `server_settings={"search_path": "<schema>,public"}`，
    结束 `DROP SCHEMA ... CASCADE` 并现查已不存在；`DATABASE_URL` 含 `audit_platform` 时
    **直接拒绝**（不碰共享库）。判据四条：①同章节互斥（A 持锁期间 B 在 0.6 s 内**不**完成，
    A commit 后 B 拿到）②跨章节不阻塞（锁粒度不是项目级）③`commit` 与 `rollback` 都释放
    （事务级锁不需要手工解）④两个连接并发 `mutate_note_section` 各追加一行后**两行都在**
    （不丢更新 —— 只有串行而没有「读到别人的写入」一样会丢）。
    **变异 2/2 RED 且形态正确**：锁改 no-op → 同章节 + 两种释放三例红；锁 key 去掉 section
    改成项目级 → 只有「跨章节不阻塞」红。内核逐字节还原、`git diff` 干净。
    **跳过判据**：`GT_BARRIER_PG=1` **且** `DATABASE_URL` 含 postgresql 才跑，否则 5 skipped
    （只看 URL 不够：本地库存在但连不上时会把「跳过」变成「连接被拒失败」）。
    **仍未完成**：合并附注差额节点（`fill_by_formula`）与叶子来源整章批取的真实 PG 对拍。
    **2026-11-17 补（叶子来源整章批取已接线，`[ ]` 保持——差额节点纯内存化与真实 PG 对拍仍缺）**：
    `reaggregate_subtree._Run` 新增按章节 `source_tables` 缓存：`process_section` 在逐节点后序循环前，
    收集本章全部数据叶子 project_id，一次调用 `load_source_tables`；随后每个 `_pull` 将缓存传给
    `apply_detail_refresh(prefetched_sources=...)`，写入仍按节点独立、章节 SAVEPOINT 与保护格语义不变。
    `apply_detail_refresh` 只在未传预取时读取来源，避免批取后再次查询。
    新建 `tests/test_consol_reaggregate_batch_prefetch.py`（5 passed），守卫覆盖：章节预取存在、
    预取发生在节点循环前、`_pull` 传缓存、apply 层消费缓存、process_section 不自行重复读取。
    完整磁盘变异因当前 Windows 共享进程占用 `_overlapped` 导致 pytest 子进程无法初始化，未虚报变异通过；
    代码级 AST 双向守卫已通过，后续需在干净验证环境补 3 组变异。

  - 2026-11-06 复核：未接内核的写入链具体是 `formula_push.note_followup →
    note_workpaper_pull_service._apply_note_formulas → note_formula_generator.execute_note_formulas`，
    仍直接改 `DisclosureNote.table_data` + `flag_modified` / flush，无章节 advisory lock。
    `test_note_formula_execute_tables.py` 的 2 例红（SQLite 缺 `formula_push_state` 表 /
    `KeyError: '_formula_provenance'`）在 `update_note` 切内核**之前**的提交 4c66d8ef2 的临时 worktree
    里同样复现（同两种错误），确认不是 C2 引入；上条「git stash 回滚验证」的说法不严谨，以此为准。
- [ ] C3 合并附注一次预取记录/公式、内存后序、批量写；修正空 section_ids 语义。
  - 已完成：空数组零工作、记录/公式预取、内存后序和章节 SAVEPOINT/flush；53 个相关回归通过。
    C2 的统一写入内核骨架同时可服务合并附注章节级写入（见上条）。
  - 🔴 未完成：差额节点仍经 `fill_by_formula(...)`，不能把它写成不存在的 `_compute_elimination`
    “纯内存内核”；叶子来源整章批取与真实 PG 并发对拍仍需专门收口。
  - 2026-11-16 复核：章节级写入内核的并发语义已由 `test_note_section_lock_concurrency_pg.py`
    在真实 PG 上验证（同章节串行 / 跨章节并行 / commit+rollback 释放 / 并发不丢更新，
    5 passed + 2 组变异 RED，详见 C2 条）。本条余项仍是**合并附注特有**的两件：
    差额节点走 `fill_by_formula` 而非纯内存内核、叶子来源整章批取。
- [ ] C4 Ledger 导入分阶段 profiler；COPY/staging/set-based 合并把真实大项目目标压到 5 分钟内。
  - profiler 骨架 `app/services/ledger_import/profiler.py`（`StagedProfiler` + `StageRecord`）：
    PG 下 `pg_current_wal_lsn()` + `pg_wal_lsn_diff` 自动采集每阶段 WAL 增量字节，非 PG 环境
    `wal_bytes=None`；`rows/sec = rows / duration_s`，支持 `record_rows()` 对 COPY 真实返回行数
    事后补记；mutator 抛异常时记 `error` 后原样向上抛，不吞异常；`to_dict()` 产 JSON 可序列化的
    stage/total 摘要，供 pipeline / progress / API 直接消费。2026-11-06 增量：pipeline 接入
    `_build_profiler_report`，把既有 `_perf` 字典 + parse_write_streaming 的 `total_rows_parsed` /
    rebuild_aux_summary 的汇总行数平移进 `StagedProfiler`；`PipelineResult.profiler_report` 可选字段
    由 worker 塞进 `ImportJob.metadata`。10 单测全绿（原 7 + 新 3）。
  - 🔴 未完成：pipeline 还没有 PG 上的 WAL 探针（骨架默认每阶段 `wal_bytes=None`，需要在
    `async_session()` 边界内读 lsn 后再写回 profiler）；rows/s、WAL、COPY 真实基线须在专用可销毁
    PG + 真实大项目数据上跑，本机无法伪造，保持阻塞。
  - 勘误（2026-11-06 整体复核）：上条「由 worker 塞进 `ImportJob.metadata`」不实——现扫 worker /
    ImportJob 均无 `profiler_report` 消费方，报告只存在于 `PipelineResult`；WAL 在 pipeline 里恒 None。
  - **2026-11-16 补（两处缺口都已修，`[ ]` 保持——真实基线仍需专用环境）**：
    ①**WAL 探针已接线**：`profiler.WalStageProbe`（`start()` / `stop()` 各自新开短 session 读
    `pg_current_wal_lsn()`，`stop()` 用 `pg_wal_lsn_diff` 算增量）；`pipeline.execute_pipeline` 在
    **写阶段自己的** session 边界内 `start()` → 写阶段 → `stop()`，结果经
    `_build_profiler_report(..., write_stage_wal_bytes=...)` **只贴到写阶段那一条记录**。
    🔴 为什么必须抽成类：`pipeline.py` 在行数白名单上（见下条），探针逻辑塞进去会把主文件再推高；
    `WalStageProbe` 在伴生 `profiler.py` 里，pipeline 只 +7 行。
    读不到（非 PG / 无权限 / replica）保持 `None` —— **读不到 ≠ 0 字节**，守卫反向钉住。
    ②**消费方已补**：`import_job_runner` 的 `result_payload` 新增 `"profiler": result.profiler_report`
    （随 `JobStatus.completed` 的 `result_summary` 落库，API 可直接读分阶段 rows/s 与 WAL）。
    验证：`tests/test_ledger_import_profiler.py` 10 → **18 passed**（新增：WAL 只贴写阶段 /
    探针不可用时保持 None / `record_wal_bytes` 已知 stage 补记与未知 stage no-op /
    探针在非 PG 与无 session 时降级 None / pipeline 必须 start-before-stop /
    探针自己用 session_factory 开 session / pipeline 必须传 `write_stage_wal_bytes` /
    runner 必须落 `profiler: result.profiler_report`）。**7 组磁盘变异全 RED** 且形态正确
    （不 start / 不 stop / 漏传参 / stop 用外部 session / WAL 贴所有阶段 / runner 不落库 /
    读不到写 0），逐字节还原。
    **仍未做**：真 PG + 真实大项目上的 rows/s、WAL、COPY 与 staging/index/activation 实际基线。
  - 行数门欠账（2026-11-16 现算，如实登记）：`backend/app/services/ledger_import/pipeline.py`
    在 HEAD 已是 **916 行**（`01394c4a7`，2026-11-15 并发会话「pipeline/runner 接 attempt 三次 CAS
    状态流转」把 836 → 916，**当时未更新白名单** ⇒ 该提交起行数门对本文件一直红）。
    本 spec 的 C4 只加 7 行且探针主体已抽出。白名单基线按「必须填当前真实行数、不得虚高」
    从 804 改为 **923** 并在条目里写明上述来源与该欠账归属（拆分责任归 attempt CAS 那条 lane）。
- [ ]* C5 知识词法/向量路径真实 EXPLAIN 与量级基准；按证据实施索引/pgvector。
  - 🔴 需真实文档量级（万级分块）+ 专用 PG 做 EXPLAIN 对比，本机无法伪造，保持阻塞。
  - V263 向量扩展 + HNSW 索引已建；tsvector/GIN 路径代码已有；量级基准与索引选择待证据。
  - 勘误（2026-11-06 整体复核）：「tsvector/GIN 路径代码已有」不实——权威词法链
    `KnowledgeDocSearch._candidates` 仍是 name / content_text / tags 的 `%ILIKE%` + 候选上限，
    没有 tsvector 列、GIN / pg_trgm 索引。
  - **2026-11-16 补（真实 EXPLAIN 基准已跑，`[ ]*` 保持——索引尚未落地到生产）**：
    新建 `backend/tests/test_knowledge_retrieval_explain_pg.py`（**5 例**）。一次性库
    `gt_kb_explain` + 提交型临时 schema，`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
    （用 JSON 不用文本：文本计划缩进随版本变，JSON 才能稳定断言索引名）。
    **实测（20000 行，1% 命中率稀疏查询）**：
    · `ILIKE`（当前生产实现）→ **Seq Scan，77.7 ms**
    · `pg_trgm` GIN → **Bitmap Index Scan，68.2 ms**（计划确认真变）
    · `tsvector` GIN（生成列）→ **67.1 ms**
    · `pgvector` HNSW（5000 × 1024 维）→ **155.1 ms**
    🔴 **结论要如实说**：耗时差异很小（正文太短，塞不进 IO 密集区），**真正的收益在计划形态**
    （Seq Scan → Bitmap Index Scan 意味着行数再涨 10 倍时 ILIKE 会线性劣化、索引不会）。
    所以「必须换索引」的判据不是当前 ms，而是 `CANDIDATE_CAP`（1000）命中即告警 ——
    本文件把这条告警钉住（AST 精确到「`logger.warning` 且参数含 `CANDIDATE_CAP`」，
    因为只查「文件里有 warning」会被别处 warning 顶成假绿，v2 变异实测确认）。
    **变异 5/5 RED**，逐字节还原。
    **仍未做**：把 trgm/tsvector 索引真正落到生产迁移（需产品裁决选哪条路径，
    且要考虑 `knowledge_documents` 已有 2 万+ 行的在线建索引窗口）。


## 批 D 前端大表与请求反馈

- [ ] D1 TB 1000/5000 行虚拟化 canary，保持编辑、选区、右键、注释、公式和可访问性。
  - 现有 GtVirtualTable 不支持离屏逻辑选区/编辑，未在交互契约齐全前冒险切生产路径。
  - 🔴 需先补齐虚拟化表的编辑/选区/右键/公式/注释交互契约（约 1000 行前端），属独立 spec 工作量。
  - 2026-11-06 复核：`GtVirtualTable` 只做只读行虚拟化，生产页零接入；GridKernel 依赖真实 td，
    缺离屏逻辑选区、编辑器回收、稳定行 / 列 key、公式 / 批注 / 无障碍协议。D3 硬依赖本项。
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
    另：50MB 的 87.0ms 已超过 50ms 长任务线，即使按通用探针也不能算通过。
- [x] D7 内网 HTTP 多标签 SSE 围栏选主；1/6/12 标签始终单项目一条连接。
  - `projectEventStreamShare` 保留 Web Locks 优先；HTTP 无 locks 时以 BroadcastChannel + localStorage
    lease 选主，确定性冲突让位关闭旧连接，leader 关闭后 follower 接手并 replay。Vitest 模拟独立标签
    1/6/12 个均只有 1 条连接（11 tests）；内网 `http://192.168.20.60:3030` 实测
    `isSecureContext=false`/locks=undefined/BC+storage 可用，1/6/12 share 实测都只有 1 个 leader。

## 批 E 容量架构

- [ ]* E1 PgBouncer transaction 模式契约与 2%→25%→100% 灰度脚本；连接预算按副本计算。
  - 🔴 需部署环境（PgBouncer 进程 + 真实后端 + RLS/SET LOCAL 验证），本机无法伪造，保持阻塞。
  - 2026-11-06 复核：仓库里没有灰度脚本；Compose 的 backend 仍直连 PG、单 worker，PgBouncer 服务存在但
    不在默认数据路径上。
  - **2026-11-16 补（transaction 模式契约已本机实测，`[ ]*` 保持——灰度脚本与按副本连接预算仍缺）**：
    新建 `backend/tests/test_pgbouncer_transaction_contract_pg.py`（**9 例：7 需 bouncer + 2 纯静态**）。
    本机起 `edoburu/pgbouncer:1.22.1-p0`（`POOL_MODE=transaction`，独立容器 `gt-pgbouncer-e1`，
    指向一次性库 `gt_e1_bouncer`），把「切 PgBouncer 前必须证明的四件事」全部实测：
    ①**transaction 模式确实生效**（同一事务内两条语句 `pg_backend_pid()` 相同）；
    ②**`SET LOCAL` 不跨事务泄漏**（事务 A 设 `app.gt_probe`，事务 B 读到空 —— 泄漏即跨项目数据泄露）；
    ③**RLS 仍隔离且 fail-closed**（临时 schema + `FORCE ROW LEVEL SECURITY` + 策略；
    项目 A 只见自己的行、项目 B 只见自己的、**未设上下文读到 0 行**）；
    ④**取消能穿透 bouncer**，且**取消后必须 `rollback()` 才能复用连接**。
    🔴 **三条只有真实环境才暴露的发现**：
    · **superuser 永远绕过 RLS**（`FORCE ROW LEVEL SECURITY` 只对表 owner 起作用）⇒ 用
      `postgres` 测 RLS 会得到「看到全部行」的假结论（第一版就踩了：项目 A 读到 `[1, 2]`）。
      修法：临时建 `NOSUPERUSER` 角色 + `SET LOCAL ROLE` 才测得到真实策略行为。
    · **`statement_cache_size` 必须为 0，且这是实锤不是理论**：开启服务端语句缓存后
      **第一次查询**（`SELECT CAST(:n AS int) * 2`）就撞
      `DuplicatePreparedStatementError`，PG 的 HINT 原文写着
      「pgbouncer with pool_mode set to "transaction" does not support prepared statements
      properly … set statement_cache_size to 0」。平台 `app/core/database.py` 已在
      `_pgbouncer_connect_args` 里设 0，本文件加**静态守卫**钉住它（含「经 `connect_args`
      指向模块级字典」的追踪 —— 只看 keyword 会漏，第一版就漏了）。
    · **取消后连接进入 `PendingRollbackError`**：`Can't reconnect until invalid transaction is
      rolled back`。这是 SQLAlchemy 语义（直连同样如此），不是 bouncer 造成 ⇒
      **平台契约 = 取消路径必须 `rollback()`**，否则带着 invalid 事务还给池会毒到下一个客户端。
    **变异 6/6 RED**（`SET LOCAL`→会话级 SET / RLS 上下文换项目 / fail-closed 改成设 A /
    默认开语句缓存 / 取消后不 rollback / 生产库模块改成 100），逐字节还原。
    🔴 **变异设计教训**：第一版 5 条里 4 条「存活」，逐条查明**全是等价变异**——
    放宽断言（`== [1]` 改 `>= 1`）在基线本来就正确时不改变结果；改 `pytest.raises` 为
    `try/except` 后 `task.cancelled()` 仍为 True。⇒ **变异必须改「被测行为」而不是「断言的松紧」**，
    且存活项要逐条证明是等价变异而非缺口（本轮 `task.cancelled()` 那条确认冗余后直接删掉，
    并在注释里写明原因，不留无用断言）。
    **跳过判据**：`GT_PGBOUNCER_URL` + `GT_PGBOUNCER_DISPOSABLE_DB=1` 才跑 7 条真连库用例；
    另 2 条纯静态判据（默认值 + 生产模块）**任何环境都跑**，无 bouncer 时 2 passed / 7 skipped。
    **仍未做**：2%→25%→100% 灰度脚本、按副本数计算连接预算（需部署环境）、
    真实后端经 bouncer 的端到端压测。
    **2026-11-17 补（灰度计划纯函数 + dry-run 已实现，`[ ]*` 保持——真实切流仍需部署系统）**：
    新建 `backend/scripts/ops/pgbouncer_canary_plan.py`，固定生成 **2% → 25% → 100%** 三阶段
    计划，不调用 Docker/Kubernetes/API，只输出机器可读 JSON；每阶段复用
    `connection_budget.compute_bouncer_budget` 同时校验 bouncer 客户端侧与 PG 服务端侧预算。
    任一阶段预算不可行时 dry-run 仍输出完整计划但退出码 **2**，杜绝「先切流、后发现连接不够」。
    每阶段计划门包含 RLS/SET LOCAL、statement_cache_size=0、取消后 rollback、pool wait/lag/错误率
    与观察窗口五项门禁。新测试 `tests/test_pgbouncer_canary_plan.py` **5 passed**；
    **5/5 变异 RED**（阶段比例、客户端预算、可行状态、不可行退出码、部署动作均改坏验证）。
    **仍未做**：真实 bouncer/后端按 2%→25%→100% 执行切流、每阶段观察窗口与自动回滚。
    **2026-11-16 追加（连接预算已实现，`[ ]*` 保持——灰度脚本与端到端压测仍缺）**：
    新建 `backend/app/core/connection_budget.py` + `backend/tests/test_connection_budget.py`
    （**14 例**）。纯计算模块（不连库），三层收窄：
    `PG max_connections − superuser_reserved − admin_reserve = 应用总额度`
    → `/ replicas = 单副本额度` → `− 池外连接 = 单副本池额度`。
    经 PgBouncer 时**两层约束同时校验**（客户端侧 `replicas × 池 ≤ bouncer MAX_CLIENT_CONN`、
    服务端侧 `bouncer 实例 × DEFAULT_POOL_SIZE ≤ PG 额度`）—— 只查一层会在另一层打满。
    🔴 **本轮最重要的实测结论（直接决定 E2 能否扩到 4 worker）**：
    默认池配置 `50 + 100 = 150/副本` 在 PG 500 连接下
    · **1~2 副本可行**（2 副本：244/副本，够 150）
    · **4 副本不可行**：489 总额度 / 4 = 122，扣池外 3 条 = **119 池额度**，
      需求 150 ⇒ **短 31**；4 × 150 = 600 > 489
    ⇒ **E2 的「2/4/8 worker」不是调个副本数就行**：4 副本前必须先降池配置或先上
    PgBouncer（PgBouncer 下 4 副本只需 bouncer 服务端侧 50×N ≤ 489 即可）。
    **变异 7/7 RED**（漏扣保留 / 不按副本拆分 / 不可行钳成可行 / 只查 bouncer 一层 /
    只查另一层 / binding_constraint 写死 / 负数不校验），逐字节还原。
- [~] E2 EventBus、任务、配额、进度和失效状态外置；2/4/8 worker 零丢失/零重复验证。
  - 🔴 platform_jobs / AI tasks 已 DB 耐久，SSE 跨标签已共享；但 EventBus、配额和失效状态仍有进程内部分，
    尚未完成跨 worker 外置和 2/4/8 worker 验证。2026-11-06 增量：接口骨架落地
    `app/services/event_bus_state_adapter.py`（`EventBusStateAdapter` ABC + `InMemoryEventBusStateAdapter`
    默认实现 + `install_event_bus_state_adapter` / `get_event_bus_state_adapter` /
    `reset_event_bus_state_adapter` 注入 hook）：debounce pending + per-project SSE quota 两面可注入；
    内存默认实现与当前 `EventBus._pending` 行为等价。11 单测全绿。
  - **2026-11-15 更新（SSE quota 面已真实接线，`[ ]`→`[~]`）**：~~adapter 在生产代码里零调用~~ **已修**：
    `EventBus.create_sse_queue` 改 **async** 并接 `get_event_bus_state_adapter().acquire_sse_quota`，
    `remove_sse_queue` 用 `ensure_future` 异步释放（同步上下文不能 await，失败只记日志），
    新增 `SSESubscriptionLimitReached` 异常与 `_sse_queue_projects` 队列→项目映射；
    生产调用方 `routers/events.py:132` 改 `await`。**默认 `max_per_project=0` = 不限**，
    与改造前行为 100% 等价（单 worker 部署零变化），多 worker 部署注入 Redis 实现后配额才真正跨进程生效。
    **架构约束（如实记录）**：`EventBus._pending` 存的是 `asyncio.TimerHandle`（本进程事件循环句柄），
    **无法序列化到 Redis** ⇒ debounce pending 侧只能保持内存实现，这一半不在可外置范围；
    quota 只是整数计数，天然可外置，所以只接了这一面。
    **验证**：`test_event_bus_state_adapter.py` 新增 5 例（默认零行为变化 / 配额申请与释放 / 项目间隔离 /
    `create_sse_queue` 必须 async 的反向钉住 / 生产调用方必须 await），与 `test_event_bus.py` 合计 **44 passed**；
    连带改 6 个测试文件的 16 处同步调用为 `await`（脚本按 AST 判断所在函数是否 async）。
    **仍未做**：真实 2/4/8 worker 零丢失/零重复验证（需专用容量环境部署）、
    任务/进度/失效状态外置（`platform_jobs` 已 DB 耐久，进度与失效状态仍在进程内）。
  - 2026-11-06 复核：adapter 在生产代码里零调用，`EventBus` 仍直接读写 `_pending` / `_sse_queues`；
    骨架只是可注入接口，不能算外置。
- [x] E3 修正 Locust UUID/信封/账号池/端点；6000 阶段无样本强制 FAIL。
- [ ] E4 构建可销毁大数据容量环境与分布式负载机。
  - 🔴 Docker PgBouncer transaction 配置和连接预算契约已在库；尚无独立容量 DB、种子数据和分布式 Locust 启动编排。
  - 分布式负载机落地时须把各 worker 的 `stage_stats.json` 按阶段 / 端点 / 桶计数相加后再判定（格式已按
    可相加设计，合并步骤未实现）；E6 六类安全计数也要在这里建外部不变量探针。
  - **2026-11-16 补（合并步骤已实现，`[ ]` 保持——环境与编排仍缺）**：
    `tests/load/load_stage_stats.py` 新增 `merge_stage_payloads` + `load_worker_stage_stats`：
    逐阶段按位置**逐桶相加**（`requests` / `failures` / `histogram`），端点按 `(type, name)` 对齐
    后累加；`user_count_min` 取各 worker **最小**、`user_count_max` 取**最大**（不是求和）；
    `covered_seconds` 取**最小**（有 worker 中途掉线时稳态实际只覆盖到最短那份，按最长自报等于虚增）。
    `run_final.py` 新增 `--worker-stats-dir` 并串到 `parse_csv_results`；分布式分支 fail-closed
    （目录缺失 / 无 worker 文件 / 文件损坏 / 阶段数不一致 / 用户数不一致 / schema 不符一律
    `stage_stats_error`，**绝不退回单 worker 口径**——那会让样本量只有 1/N 而判定看起来更好）。
    验证：新建 `tests/load/test_stage_stats_worker_merge.py`（**18 例**，含「一个快 worker +
    一个慢 worker 合并后 p95 必须落在慢桶」这种「只取第一份就假绿」的反向对照，以及
    run_final 接线判据）；**8 组变异全 RED** 且逐字节还原；`tests/load` 全套 **130 passed**。
    **仍未做**：独立容量 DB、种子数据、分布式 Locust 启动编排、E6 六类安全计数的生产者。
- [ ]* E5 100→1000→3000→6000 VU，6000 稳态 30 分钟；提交原始 CSV/JSON/摘要。
  - 2026-11-06 工具对齐（测量与门禁纠偏批，未在容量环境实跑，不改勾选）：梯度单一来源
    `tests/load/load_contract.py`，删掉 500 VU 正式阶段，6000 VU 稳态 300→1800 秒，Locust 形状与稳态窗口共用
    `stage_timeline()`。🔴 修了一处判定口径错误：开 `--csv-full-history` 后 history CSV 的分位列是最近约 10 秒
    的滚动值、计数列是全程累计，原先取「阶段最后一行」等于只看最后 10 秒、错误率被前面阶段稀释。改为
    `locustfile.py` 在 `events.request` 上按稳态窗口（标称加压结束 + 5 秒起）逐请求累计直方图，写
    `stage_stats.json`，runner 从桶里复算分位；稳态覆盖时长按合同现算（不读文件自报），短跑判失败；
    `summary.json` 改严格 JSON（无穷大写 null）。验证：`tests/load` 74 passed；11 组隔离副本变异全部红在预期
    用例、1 组改日志文案的阴性对照全绿；真实 Locust 进程 + 本机假后端冒烟（2 个短阶段）写出窗口统计，
    窗口内最低并发 = 目标、覆盖秒数 = 要求、500 响应计为失败、加压期请求不计入。
- [ ]* E6 达成核心读 p95≤300ms、p99≤1s、核心错误率<0.1%，零泄露/超时/事件丢失/数据损坏。
  - 2026-11-06 判定对齐（未实跑，不改勾选）：原 runner 用聚合 p95≤2s / p99≤5s 且 p99 不进
    `overall_pass`。现改为 6000 稳态窗口内 `trial-balance` / `working-papers` / `ledger/window/{account_code}`
    逐端点 p95≤300ms、p99≤1s、错误率<0.1%（缺样本或缺分位即失败）；全场景错误率取全程与 6000 窗口较差值
    <1%；`--safety-evidence` 必须给齐 `unauthorized_successes` / `connection_leaks` / `connection_timeouts` /
    `event_loss` / `duplicate_side_effects` / `data_corruption` 六键且全为 0，缺失即失败。🔴 这六个计数的
    生产者（越权回放、连接池对账、事件序号对账、幂等重复、业务恒等式）尚不存在，runner 只校验不生成。

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
  - 2026-11-06 测量与门禁纠偏批：上条①已修——包体预算只读 `scripts/bundle-budget.json` 一份策略
    （删 `bundle-budget.baseline.json`），普通大块按 manifest 稳定名比对，不再按带 hash 文件名或 gzip 名次；
    三个豁免重块按名计数，并检查不得进入入口静态依赖；`build-verified-dist` 快照指针改临时文件 + rename
    原子切换。`build-pipeline-contract.spec.mjs` 有 1 例在 HEAD 上恒红（按注释原文切片，公式管理 / 高级查询
    两个弹窗的注释与写法被其他会话正常改动后切片为空），改为按 `watch(...)` 调用本身判 immediate、注册位置
    与晚到响应丢弃，内存变异 5 组全红、只改注释的对照仍绿。本轮证据：预算 7 + 构建契约 7 tests passed；
    `vite build --mode production` 3m11s 通过；`bundle:check` 通过（入口 gzip 563,691 B、总 gzip
    20,825,727 B、普通块 2,673 个、三个豁免重块各 1）；`smoke:built` 通过；`build:verify` 端到端通过并发布
    `.verified-dist/c68fba13…`，`current.json` 的 `budgetBaselineSha256` 等于 `bundle-budget.json` 的 sha256。
    仍阻塞：②③④。
- [x] F2 更新 6000 前置文档，勘误历史零样本假绿，不改 append-only 历史记录。
  - `backend/tests/load/README.md` 写清可销毁 DB 三重闸门、perf+pg_only 专用库、原始 CSV/summary.json
    归档要求和零样本禁止外推；`run_final.py` 不再删除 Locust CSV，新增 `--evidence-dir` 与机器可读
    `summary.json`（不含凭据）。17 个 load/evidence gate 测试全绿。
- [x] F3 更新 INDEX/memory；只提交本任务 owned 文件。
  - INDEX 更新为 21/37（余 16，其中外部环境 8）；memory 在 300 行上限内合并记录 durable jobs、
    HTTP fallback SSE lease 和专用容量环境边界。
  - 2026-11-16 复核：INDEX 行改为 **21/37 + 2 进行中（余 14，其中 `[ ]*` 8）**并写清余项构成
    （6000 VU 实跑 / PgBouncer 灰度 / 2·4·8 worker / TB 虚拟化 / 知识检索 EXPLAIN）。
    本轮新增的三条守卫（C1 引擎级 statement 计数、C2/C3 真实 PG 并发 barrier、E4 分布式
    stage_stats 合并）与 C4 的两处补齐（WAL 探针 + profiler 落库）均已登记进对应任务项，
    **不勾选它们的主项**（C2/C3 余差额节点与整章批取、C4 余真实大项目基线）。
    **本 spec 不归档**：余 14 项中 8 项需专用环境、6 项需独立 spec 工作量
    （D1/D3 虚拟化交互契约、E4 容量环境与编排、C2/C3/C4 的合并附注与真实基线）。