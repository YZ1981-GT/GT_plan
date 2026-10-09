# 任务清单：启动预热不阻塞事件循环

> 需求：#[[file:.kiro/specs/startup-prewarm-event-loop-unblocking/requirements.md]]
> 设计：#[[file:.kiro/specs/startup-prewarm-event-loop-unblocking/design.md]]

- [x] 1. 源码事实预热移出事件循环
  - [x] 1.1 `entry_source_facts.warm_source_fact_caches()`（失败只返回名字）
  - [x] 1.2 `_attach_pilot_adapters` 冷路径 `await asyncio.to_thread(warm_source_fact_caches)`
    - 证据：锁内、重查缓存之后、各 attach 之前；缓存命中路径不进锁不跳线程（既有用例仍绿）
  - _需求：1.1–1.3_
- [x] 2. `observe()` 经 `to_thread` 调 `_observe_workbook`
  - 证据：`_observe_workbook` 仍是同步方法（`test_d4_29_customer_detail_sync.py` 等离线直调不受影响）；观测顺序不变
    （`test_observe_workbook_runs_before_build_identity_binding` 字符偏移 / 行序判据仍绿）
  - _需求：2.1–2.2_
- [x] 3. `frontend_reference_index` 记忆化 + 真实前端树等价实测
  - 证据：真实前端树（5200 个生产源文件）与改前算法逐字段相等（scanned / imports 4732 键 / tags 5875 键）；首算 7.89s → 4.40s
  - _需求：3.1–3.2_
- [x] 4. 三处 127.0.0.1 默认值 + 守卫
  - 证据：`.env.example` / `dsh_engine.spawn_mcp_process` / `tools/audit-data-mcp/server.py`；`test_audit_data_mcp_server.py` 的豁免串同步改为
    `127.0.0.1:9980`。该文件 17 红为预存（`.venv` 无 `mcp` 包，`ModuleNotFoundError`）：HEAD 版 server + HEAD 版测试放仓库内临时树复跑同为 17 红
  - _需求：4.1–4.2_
- [x] 5. 验证
  - [x] 5.1 新增用例 + 相关套件全绿、预存红归因
    - 证据：`test_sync_registration_prewarm.py` 19（新增 5）、`test_frontend_reference_index_memo.py` 4、`test_backend_client_loopback_defaults.py` 3、
      `test_structure_fingerprint_memoization.py` 9 passed + 1 xfailed（design §六补，已知缺陷钉住）
    - 回归 12 个文件（observer / entry profile / static lane / structure hash / A entry / D4-29 / sync router / 里程碑 / DSH engine /
      phase-C gate / 指纹 / 单趟解析复用）：9 个全绿；3 个有红 —— `test_task75_published_identity_observer` 25、
      `test_task73_entry_profile_manifest` 9、`test_workpaper_sync_program_milestones` 1（`test_generated_projection_is_current_and_self_digest_bound`）。
      归因：本轮改动的生产文件替换为改前字节（HEAD blob；observer 只回退本轮 hunk）重跑，失败集合**逐项相同**（本轮引入 0），sha256 还原一致。
      前两组集中在他会话 12:03–12:09 改过的 D1/D3/D5/D6/D7/C/D2 pilot 模块，属并行进行中的状态
  - [x] 5.2 真栈对照
    - 进程内事件循环心跳（第一段预热，同一探针改前 / 改后）：最大滞后 **8.30s → 0.78s**，阻塞 Python 时间 **13.9s → 2.1s**，最长连续阻塞 7.88s → 0.50s
    - HTTP（reload 后 `/api/health`）：改前首测就绪后首请求 16.23s、>1s 尖峰 4 次；改后复测 45s 窗口最大 0.06s。🔴 如实：随后做的同法 A/B
      （临时还原改前代码）两侧都 ≤0.05s —— 那时冷注册被 fingerprint gate 在 0.1–8s 内拒掉（design §六补），负载与首测不同，
      A/B 不构成对照。HTTP 层可复现的前后对比以进程内心跳为准
    - 注册结果不变：真库逐步注册（当前代码 vs 内存还原的改前行为）两个变体 registered / failures / explicit 完全一致
      （4 个 adapter；`xlsx/gt-d1-notes-receivable` 以 `ObservedIdentityDriftError` 失败 —— 两变体相同，属他会话 12:03–12:09 改 D1 契约/provider 后的
      现场状态，非本轮引入）
  - [x] 5.3 变异 + 既有预热变异脚本全量重跑
    - 证据：`_lat_mutation_check.py` P1–P10 全 RED、sha256 还原一致；`mutate_sync_registration_prewarm_guards.py` 12/12 KILLED
      （「拿锁后不重查缓存」锚点随插入点同步）、post-restore 19 passed
  - _需求：5.1–5.3_
