# 企业向量 / 重排模型接入与知识库向量检索修通 — 设计

## 1 现状实证（2026-11-04 现查）

| 项 | 现状 | 后果 |
|---|---|---|
| 启用的向量行 | `Kbenkhaled/Qwen3.5-27B-NVFP4` @ `http://localhost:8100/v1`（复用对话模型） | 8100 没有 `/embeddings`，向量恒不可用 |
| 致同网关 `GET /v1/models`（qwen3.8 的 Key） | `wemm-embedding-4b` / `qwen3.8` / `qwen3-reranker-4b` | 两个模型确在同一网关、同一 Key |
| `POST /v1/embeddings` | 原生 2560 维、L2 范数 1；带 `dimensions=1024` 返回 1024 维且已归一；支持批量；约 110 ms | 可按 MRL 输出 1024 维 |
| `POST /v1/rerank` | `{results:[{index, relevance_score, document}], usage}`，`top_n` 生效；约 80 ms；`/v1/score` 404 | Cohere / Jina 形态 |
| `knowledge_index.embedding_vector` | `VARCHAR(5000)` | 1024 维逗号串约 2 万字符，任何真实向量都写不进 |
| `knowledge_index` 唯一索引 | 只有主键 | `_upsert_chunk` 的 `ON CONFLICT (project_id, source_id, chunk_index)` 在 PG 上必报错 |
| `knowledge_index.project_id` | 外键 `projects(id)`；全局哨兵 `00000000-…` 不在 `projects` | 公共文档（最主要的知识）入不了索引 |
| pgvector | 镜像带 `vector 0.8.5`，库内未安装；`embedding_vec` 列不存在（V119 当年跳过） | 只能走文本列，而文本列又写不进 |
| 数据 | `knowledge_index` 0 行；`knowledge_documents` 29 行全部已软删 | 无存量向量需要迁移；`build_index`（业务数据）全仓无调用方 |
| 重排 | 全仓没有 rerank 模型类型 / 调用 | 新能力 |

结论：向量检索链路有五处同时断开（模型行、文本列长度、冲突目标、外键、扩展），任一处都足以让写入失败；
写入失败被调用方吞掉，检索恒退回词法层，DSH `kb_search` 恒 `semantic_unavailable`。

## 2 裁决

- **ADR-ER-1 向量 1024 维（MRL）**：企业向量预设声明 `embedding_dimensions=1024`，运行时发 `dimensions`。
  与 V119 / ORM `Vector(1024)`、本机 bge-m3 同维；pgvector `vector` 类型 HNSW 上限 2000 维，2560 维要改 halfvec，
  收益不抵改动。维度只在预设上声明（非 DB 列），自建模型不发 `dimensions`。
- **ADR-ER-2 重排是独立模型类型**：走模型配置页、信任策略、调用路由面板与本机→服务器兜底；不做 `.env` 配置。
  无启用行 = 不重排（`resolve_route` 对 rerank 返回空，不回落 `.env`）。
- **ADR-ER-3 重排 fail-open、在权限过滤之后**：重排模型只看到当前用户可读的文本；重排失败保持原排序。
  路由兜底与冷却复用 `llm_route`，但不写对话的「实际服务模型」上下文（否则生成记录会记成重排模型名）。
- **ADR-ER-4 向量模型签名而非切换即重建**：`knowledge_index.embedding_model = 模型名@维度`；检索按签名过滤，
  其他签名的分块不参与相似度。重建靠既有增量更新（文档变化）与重新入索引；不做后台自动重建。
- **ADR-ER-5 去掉 `knowledge_index.project_id` 外键**：索引是可重建的派生层，哨兵分区不是项目；
  不往 `projects` 塞哨兵行（会出现在项目列表）。
- **ADR-ER-6 Key 由用户在界面录入**（2026-11-04 用户改口，原「复制 qwen3.8 密文」作废）：两条预设走模型配置页
  「录入 Key」→ `PUT /api/ai-models/{id}`，与 qwen3.8 同一个 Key；保存 / 启用按路由同口径写审计。
- **ADR-ER-7 向量 / 重排调用按数据政策过滤**：只用 `client_data_allowed` 的候选（检索文本含客户资料）；
  `.env` 兜底只有本机端点满足。

## 3 改动面

| 层 | 文件 | 要点 |
|---|---|---|
| 枚举 / 迁移 | `models/ai_models.py`、V261 | `AIModelType.rerank`；`ALTER TYPE … ADD VALUE`（同事务不可用新值 ⇒ 单独一个迁移） |
| 预设 / 种子 | `ai_model_presets.py`、V262 | `GT_WEMM_EMBEDDING_4B`（`…000004`）、`GT_QWEN3_RERANKER_4B`（`…000005`）；rerank 启用唯一索引 |
| 索引存储 | V263、`KnowledgeIndex` ORM | TEXT 列、`embedding_model`、去外键、去重后唯一索引、pgvector 列与 HNSW（容错） |
| provider | `llm_provider_registry.py` | OpenAI 兼容 / 自定义支持 rerank |
| runtime | `llm_runtime.py` | `ResolvedLLMConfig.embedding_dimensions`；`embedding` 发 `dimensions` 并校验；`rerank()`；`test_runtime_config` 分支；rerank 无行返回空路由 |
| 路由执行 | `llm_route.py` | `route_rerank`：按顺序试、可转移错误换下一个、冷却；不写对话 outcome |
| 服务 | `ai_service.py` | 向量按政策过滤并记录 `last_embedding_signature`；`rerank_route` / `rerank` |
| 状态 | `model_route_status.py` | KINDS 加 rerank（local_first），真发 `/rerank` 探测；读路由失败只记该类错误 |
| 检索 | `knowledge_index_service.py` | upsert 按列存在与维度写 `embedding_vec`、写签名；检索按签名；重排阶段；严格检索的重建提示 |
| 前端 | `aiModelApi.ts`、`AIModelConfig.vue`、`modelRouteView.ts` | 类型 / tab / 选项 / 说明文案 / 停用后果 / 空态 |

## 4 检索流程（启用重排时）

```
query ─embedding(1024)→ 向量召回(签名过滤, recall_k) ┐
       文档词法召回(recall_k) ───────────────────────┼→ 权限过滤 → 合并去重 → 上下文加权
       业务数据兜底(向量不可用或存在其他签名分块时) ──┘
   → 重排(query, 候选正文) ── 失败/未启用 → 原排序
   → 截断 top_k → 附文档名 / 路径
```

`recall_k = min(max(top_k*3, top_k), 50)`，仅在重排路由非空时放大。重排分数写 `rerank_score`，
原分数移到 `recall_score`，`score` 取重排分（跨年合并按 `score` 排序时两侧同口径）。

## 5 迁移验证

取号：本分支与共享库最高 V251，但远端 `origin/merge1103`（他人 2026-11-04 部署分支）已占 V252~V260
（内容不同），按「全部远端分支最高号 + 1」取 V261~V263，避免日后合并撞号。

V261~V263 先放 `tmp_embed_rerank/migrations/` 在一次性库（`gt_kiro_embed_*`，按共享库 DDL 建表）跑
V → R → V，确认扩展缺失分支与存在分支都不报错，再放进 `backend/migrations/`（共享工作树里的迁移会被
其他会话的重启执行，写入时内容必须已定稿）。

## 6 范围外（第一批登记；第二批处理情况见 §9）

- DSH 能力探针 `_check_embedding_health` / `startup_health._check_embedding_local` 只看 `.env`
  `LLM_EMBEDDING_BASE_URL` 做 local-only 判定，不看库里启用行 → **第二批 R12 已改**。
- `KnowledgeIndexService.build_index`（业务数据入索引）全仓无调用方 → **仍不做**：接线是新功能（入哪些业务数据、
  何时触发、单项目数千块的向量化成本），需产品口径；现状下业务数据分块在生产为空，启用向量不会让业务结果「消失」
  （本来就为空）。
- 批量向量化（网关支持 `input: [...]`）→ **仍不做**：入索引是后台任务，逐块约 110 ms 可接受，属性能优化。
- `routers/ai_models.py::_local_unavailable_warning` 对向量 / 重排的措辞 → **第二批 R11 已改**（先把请求体与规范化
  原样移出，文件降到行数门以内）。

## 7 验证记录（2026-11-04）

- 网关实测：`/v1/embeddings` 原生 2560 维、`dimensions=1024` 返回 1024 维且 L2 范数 1；`/v1/rerank` Cohere 形态。
- 一次性库（`tmp_embed_rerank/scratch_migration_check.py`）：pgvector 可用分支 28 项、扩展不可用分支（无库级
  CREATE 的角色）3 项全部通过；含 V → R → V 往返、同键分块去重、哨兵分区写入、2560 维被 vector(1024) 拒收、
  重排启用唯一约束、服务层 upsert 走 ON CONFLICT、pgvector 召回与签名隔离（真实 asyncpg + pgvector 绑定）。
- 端到端（`tmp_embed_rerank/e2e_scratch_gateway.py`，一次性库 + 真实致同网关）：入索引 5 块 2.9 s，全部
  `wemm-embedding-4b@1024`；严格检索 1.4 s，最相关段落重排分 0.9996（向量召回分 0.687），其余 0.0077 / 0.0005。
- 共享库：V261~V263 执行成功（执行前待执行集合恰为本次三条；`ai_model_config` 6 行备份在 `tmp_embed_rerank/`）。
- 自动化：新用例 `backend/tests/test_enterprise_embedding_rerank.py` 20 例；24 个相关既有文件候选 23 failed /
  445 passed 与 HEAD 干净检出 23 failed / 426 passed 失败集合逐条相同（均为预存：真库夹具在隔离库地址下连不上
  21、知识库文件夹钩子 1、`recycle_bin` 函数全局名棘轮 1）；`test_v197_route_migration_pg` 显式 `DATABASE_URL`
  下通过（不设时被静默跳过）；`test_ai_chat_mcp_tools_data::TestTypedErrorSeparation` 真库 5 例通过；
  前端 `modelRouteView.spec.ts` 9 例 + `aiModelApi.spec.ts` 7 例；单区域 vue-tsc 0 错（配变异探针证明能报
  TS2741 / TS2322）。
- 磁盘变异（独立 worktree，主工作树不动）18 / 18 全红：不发 dimensions、不校验维度、重排回落 .env、非 1024 维
  写向量列、列不存在写向量列、重排失败不兜底、重排不排序、重排写对话 outcome、不按数据政策过滤、不记签名、
  召回不放大、严格检索不报重建、旧模型分块不补兜底、不按签名过滤、状态页缺重排、重复下标不去重、预设不声明维度、
  provider 不支持重排。

## 8 未完成与阻断（如实登记）

- 🔴 **全局审计链分叉阻断配置写入**：`__global__` 链无 `audit_chain_head` 行，且有 9 处分叉、10 个未确认链尾
  （2026-08-22 AI 对话并发写 7 处、2026-08-06 下载 / 查看 1 处两侧都有后继、2026-10-17 交付件 1 处）。
  `read_head` 惰性初始化时 fail-closed ⇒ 所有项目外审计写入（含模型配置的录 Key / 启用 / 停用）都抛
  `AuditChainForked`。`scripts/ops/audit_chain_fork_ack.py --apply` 要求链尾恰为 {survivor, dead}，10 个链尾下
  无法逐个确认。属 `audit-log-chain-integrity`（S10）范围，需用户决定处理方式后再执行本 spec 任务 7、8 的剩余步骤。
  → 用户 2026-11-04 放行按建议处理，见 §9.1。勘误：上面「9 处分叉」里 2026-10-17 交付件那 1 处在重药安徽项目链
  `project:0ec33ac9…`（也被阻断，2 个链尾），`__global__` 自身是 8 处分叉。→ 2026-11-04 已执行确认，两条链各恰 1 个链尾，
  阻断解除（§9.6）。
- 剩余步骤（分叉处理后）：用户在界面「录入 Key」并启用两条预设（向量预设替换本机 Qwen3.5 向量行）；之后建【测试】
  知识文档走查索引 → 语义检索 + 重排 → DSH 严格检索，清理并对账。原「复制 qwen3.8 密文」做法作废（ADR-ER-6）。
- 旧代码后端（其他会话未拉取本提交的 worktree）读全部模型配置时会因库里的 rerank 行抛 LookupError；拉取后消失。
- 共享 `schema_drift_log` 由所有连到共享库的后端写入，旧代码后端扫描后会显示 `knowledge_index.embedding_model`
  为 db_extra，不代表本 spec 有漂移（9980 实测 `/api/ai-models` 已列出 rerank 行）。

## 9 第二批：范围外问题收口（R8~R13）

### 9.1 审计链现状（2026-11-04 共享库只读现查）

- 1336 条链 / 6404 条；被阻断（未确认链尾 ≠ 1）的只有两条，均无孤儿、无多个创世根、库里 `audit.fork_ack` 条目 0 条：
  - `__global__`：1856 条、10 个链尾、8 个分叉点。主链尾 `7bf9ecb4`（2026-11-01 最新一条）。死端 9 个：2026-08-22
    AI 对话同一秒并发写出的 8 个单条侧枝（其中一个分叉点有 2 个死端）+ 2026-08-06「下载」侧枝的链尾 `82f86968`
    （侧枝 3 条，根 `60ee0e5d`，与父条目同一事务写出；「查看」一侧 1785 条通到最新记录）。
  - `project:0ec33ac9…`（重药安徽）：106 条、2 个链尾；2026-10-17 交付件分叉，死端 `bedc08d4`（无后继），主链尾 `f5a38089`。
- 分叉条目的 `xmin` 与相邻条目同期（1.4M~1.6M / 5.2M，现 6.2M），是当年无链锁的旧写法写出的，不是近期插入。
- S10 tasks.md 任务 4 记的确认条目 `25aeb13a…` 与它引用的 survivor / dead 在本库都不存在，与本库历史对不上（任务 4 追加说明）。
- 隔离区：`__global__` 45 条（下载 22、无权建项 16、用户安全变更 3、报表查看 / 编辑 4），逐条按写链内核校验全部合法，
  解除阻断后重放写入；两条假项目链 39 条（`user_id='user-001'`，来自测试）永远写不进去，且让健康端点一直 degraded。

### 9.2 分叉确认（R8）

- `forks.append_fork_acks(db, *, chain_key, survivor_entry_id, dead_entry_ids, operator_id, reason)`：
  ① `lock_chain` → `_unconfirmed_tails`（与 `read_head` 同一定义：一次查询、按会话方言、减已确认死端）必须等于
  `{survivor} ∪ dead_entry_ids`；② 一次读出链内 (id, entry_hash, prev_hash, ts)，求 survivor 的祖先集合；每个死端向上
  走到祖先集合为止，得死端侧枝；确认集合 = 死端 ∪ 侧枝里「父条目有 ≥2 个子条目」的条目（即分叉点上的侧枝根，
  也覆盖侧枝内部再分叉）；③ 按 (ts, id) 排序，从 survivor 起逐条写确认条目（v2 哈希：与 `append_entry` 同一套
  `_business_payload` / `hash_v2`，`_hash_v=2`，resource_id = 被确认条目），每条 `dead_entry_id` 为标量
  （四个读者 `head._dead_entry_ids`、`forks._unconfirmed_tails`、`scan_forks`、`verify_chain` 不改）；
  ④ 删除旧链尾行 → `read_head` 重新初始化，必须恰为最后一条确认条目，否则抛错（调用方回滚）。
- `append_fork_ack` 改为单死端的薄封装（签名、返回值不变）。
- `scan_forks(chain_key=…)`：链键从分叉父条目推导后再过滤（原实现把所有结果都标成传入值，过滤恒真）。
- 运维脚本：不带 `--apply` 时对每条被阻断链输出计划（链尾、建议主链尾 = 最新链尾、侧枝摘要、可执行命令）；
  `--apply --chain-key K --survivor S --dead D…（可重复）--operator <用户名或 id>（须 admin、在用）--reason …`。
  `audit_chain_heads.py` 链尾数减去已确认死端，与写链内核同口径。

### 9.3 审计队列（R9、R10）

- `worker.entry_problem(entry)`：按写链内核的同一组函数校验（链键 / 项目一致、`user_id` 为 UUID、年度、时间、载荷规范化），
  返回原因或 None。`write_batch` 与 `replay_quarantine` 先分拣：不合法 → `audit:log:deadletter:<链键>`（原条目 +
  `_dead_letter_reason` / `_dead_lettered_at`，不丢弃）；合法 → 原逐链事务。隔离区重放成功后照旧按原内容裁剪。
- 健康端点 `audit_chain.dead_letter_entries`（Redis 不可达为 null），>0 即 degraded。
- 测试：`tests/conftest.py` autouse 把 `AuditLoggerEnhanced._get_redis` 包一层——`app.core.redis.redis_client` 是
  fakeredis 才走原逻辑，否则返回 None（进程内降级队列），共享 Redis 一条都不进；用例显式换 fakeredis 的照旧可测队列。
- `AuditChainError`（分叉 / 绕过）→ 新处理器 `middleware/audit_chain_error_handler.py` 返回 503
  `{code, error_code: AUDIT_CHAIN_BLOCKED, message}`，在 `main.py` 泛型处理器之前注册（`error_handler.py` 有其他会话
  未提交的改动，不碰）。

### 9.4 模型配置（R11）

- `routers/ai_models.py`（870 行）把请求体与字段规范化（`ModelCreate` / `ModelUpdate` / `_validated_endpoint` /
  `_trust_values` / `_ocr_values_for_create` / `_apply_ocr_update` / `_apply_secret_or_raise`）原样移到
  `services/ai_model_admin_fields.py`，路由按原名导入（测试按路由模块名引用 `_trust_values`；`_audit_model_change`
  仍以裸名调用，审计 AST 守卫不变）。
- `_local_unavailable` 与启用同口径：`kind == unavailable` 且（本机或企业预设）。`clear_api_key` 只有为真才算连接变更。
- 启用：企业预设没有 Key ⇒ 400 `api_key_required`「企业预设需先录入 API Key 再启用」（否则网关不可达时会带警告启用，
  向量还会顶掉现有向量行）。
- 提示：向量——本机「本机服务恢复前语义检索不可用，知识检索改用词法召回」，企业预设「连上公司网络前…」；
  重排——有另一端兜底沿用「自动使用…兜底」，没有则「在此之前知识检索不重排，按召回分数排序」。

### 9.5 DSH 向量探针（R12）

- `AIService.embedding_route()`（公开；与真实向量调用同一个 `_client_data_route`）。
- `capability_endpoint.embedding_route_health(db=None)`：取首个可解析候选 → `validate_dsh_upstream(端点)`；
  读路由失败 / 政策挡住 / 无可用配置 → `semantic_unavailable`；端点不受信 → `local_only_violation`；通过时消息写
  模型名、部署位置、是否 `.env` 默认；不发请求。路由加载函数单独成 `_load_embedding_route`，测试注入。
- `/capabilities` 路由先 `await embedding_route_health()` 再传给同步的 `get_capabilities(embedding_health=…)`；
  `_collect_service_health` 不再读 `.env` 判向量（未传入时报「未检查」）。启动自检改用同一函数。

### 9.6 执行与验证记录（2026-11-04）

- 推送：代码 v1.0.118（`b59193ede` fix(server-audit) / `dca300ec6` fix(server-ai)，rebase 到他人 v1.0.117 `2dbc68ea0`）；
  三件套的第二批文字 v1.0.118 没有带上，随第三批一起推送。
- 共享库审计链（任务 14）：
  - 不带 `--apply` 的演示输出两条被阻断链的计划：`__global__` 1856 条 / 10 个未确认链尾，写确认 10 条（9 个死端 +
    「下载」侧枝根 `60ee0e5d`）；`project:0ec33ac9…` 106 条 / 2 个链尾，写 1 条。没有另建一次性库复制共享链数据演练；
    同一路径由真 PG 用例覆盖（`test_audit_chain_forks_pg.py`：一条链 3 个死端、其一侧枝 2 条一次确认，前置集合不符整体拒绝，
    写后恰一个链尾、可续写、链校验无内容不符）。
  - `--apply`（操作人 admin `b6f8e8d0-8b64-47ab-bbc3-bfaed2b51e98`）：`__global__` 写 10 条 v2 确认条目（最后一条
    `81b55994-b60f-4853-8f84-00a5b838798d`），项目链写 1 条（`ffed5464-eb39-4bd6-b4ff-bc7d9a2cfb7d`）。
  - 只读复查：`blocked_chains` 为空，`scan_forks` 没有未确认分叉；两条链各恰 1 个链尾；`verify_chain` 均 valid、problems 0
    （全局 1911 条，旧格式 1856 条全部复算一致；项目链 107 条，旧格式 11 条不可复算，为执行前既有情况）。
  - 隔离区：解除阻断后 9980 的审计 worker 重放 `__global__` 隔离区 45 条，全局链 1866 → 1911。
  - 两条假项目链的 39 条测试死信（`user_id='user-001'`、`custom_query.cell_writeback`）完整备份后删除，全局链写一条
    `audit.deadletter_test_cleanup`；之后 Redis 队列 / 重试 / 隔离区 / 死信均 0，健康端点 `audit_chain` 三项均 0。
    备份（死信、执行前隔离区快照、`ai_model_config` 迁移前快照）移到 `backend/backups/enterprise-embedding-rerank-20261104/`（gitignore）。
- 自动化：候选 248 例（非 PG）+ 11 例（真 PG，用例自建并删除一次性库）通过；磁盘变异 14 / 14 全红：侧枝根不确认、确认条目不带
  v2、前置集合校验跳过、扫描不按链键过滤、健康扫描失败报 0、无效条目进隔离区、坏 JSON 不进死信、测试审计推共享 Redis、
  无 Key 预设能启用、未勾选清除凭证算连接变更、重排不可达误报调用失败、DSH 探针跳过受信校验、pgvector 路径漏掉文本向量
  历史分块、全局链校验退回全表。
- 缺口：第二批推送前没有对「去掉本批的远端头」做逐节点回归，第三批补跑后抓到 3 个既有健康用例变红（§10.2）。
- 浏览器（3030，admin，只读走查，未录入 Key）：嵌入模型 tab 的 `wemm-embedding-4b`「启用」→ `POST …/activate` 400，弹出
  「启用失败：企业预设需先录入 API Key 再启用」，行状态不变；重排模型 tab「录入 Key」打开「配置企业预设」（名称 / 类型 /
  供应商 / 端点只读，只填 API Key），取消关闭；console 只有这次预期的 400 与一条既有的 NotificationCenter Vue 警告。

## 10 第三批：第二批推送后复核（R14、R15）

### 10.1 schema 漂移检测（R14）

- 误报：V263 在共享库建了 `knowledge_index.embedding_vec vector(1024)` 后，健康端点一直列
  `ORM=VECTOR vs DB=USER-DEFINED`（WARN 级 type_mismatch）。根因：`_collect_db_tables` 只取
  `information_schema.columns.data_type`，扩展类型在那里固定是 `USER-DEFINED`。
- 改：采集多取 `udt_schema` / `udt_name`，经 `db_compare_type()` 归一，只有 `USER-DEFINED` + `public` + `vector`
  归成 `VECTOR`，其他 UDT 原样比较。否决：把所有 USER-DEFINED 当兼容（业务枚举 / domain / halfvec 的真实差异会被藏起来）；
  在 allowlist 登记这一列（每加一个向量列都要登记，且同样遮住真实类型错误）。
- 静默失败：`run_drift_check_with_timeout` 超时 / 抛错原来返回 `[]`，`query_drift` 读不出快照也返回 `[]` ⇒ 启动日志与健康端点
  都读成「没有漂移」。改为写 / 返回一条 `scan_failure`（新 DriftType，进 `CRITICAL_DRIFT_TYPES`），detail 只带异常类型，异常正文
  （可能含连接串）只进服务端日志；快照写库失败只记日志，扫描结果照常返回。否决：继续返回 `[]`；把异常正文放进 health。
- 共享库只读扫描（候选代码，只 `scan` 不写快照）：11 项，`embedding_vec` 不再出现；9 条 CHAR/VARCHAR、BIGINT/INTEGER 是
  WARN 级、属其他 spec 的表；critical 2 条是 V233 / V234 checksum 漂移（`project_creation_grants`，其他会话的迁移，未改，
  健康端点因此仍 degraded）。`schema_drift_log` 由连到共享库的各后端覆盖写，要等运行新代码的后端启动扫描后才更新：v1.0.120
  推送、主工作区前移后 9980 热重载（2026-11-04 15:00:07 UTC）重新扫描，健康端点漂移 12 → 11 项，`embedding_vec` 不再出现，
  `audit_chain` 三项仍为 0。

### 10.2 审计链健康缓存（R15）

- 第二批把分叉扫描失败从 0 改成 null（degraded），但 `_query_audit_chain_health` 照旧把结果缓存 300 秒：一次瞬时失败会把
  degraded 钉住 5 分钟；同一测试进程里先跑的用例用 mock 会话把 null 写进缓存，后面的用例跟着 degraded。改为只缓存三项
  都读到的已知结果。
- 回归：按引用挑出 124 个相关测试文件；基线 = 远端头 `ffab9d86a` 去掉第二批两个提交（`git revert --no-commit`），候选 =
  远端头 + 第三批；junit 逐节点比对（基线 1832 节点 / 201 红，候选 1877 / 204 红；红的多为隔离库地址下连不上 PG 的既有用例）。
  候选新增红 4：3 个既有健康用例（`test_middleware_pure_asgi` / `test_reload_handoff` / `test_startup_registry`）用 mock 会话却
  断言 healthy，原先靠「扫描失败按 0」碰巧通过，改为与迁移 / 漂移一样显式声明审计链干净（`test_health.py`、
  `test_health_endpoint_degraded.py` 用 autouse 夹具同样声明）；第 4 个是新增的真 PG 用例，隔离库地址下连不上，真 PG 下通过。
  修后重跑 7 个受影响文件 121 passed，真 PG 11 passed。
- 隔离：两次回归各用一个事前为空的 Redis 库（14 / 15 号）。基线没有第二批的 conftest 守卫，跑完 15 号库 `audit:log:queue`
  里有 29 条测试审计条目 —— 不隔离时它们会进共享 0 号库、被 9980 写进共享审计链；跑完已删这些键。

### 10.3 验证

- 磁盘变异（`third_batch_mutation_runner.py`，隔离 worktree）12 / 12 以「1 failed」形态打红，另 1 条阴性对照（只改超时日志
  文案）保持通过：vector 不归一、所有 UDT 都当 vector、采集口绕过归一、超时吞成 []、异常吞成 []、扫描异常正文进 health、
  scan_failure 不算 critical、写库失败中断、读快照失败返回 []、读快照异常正文进 health、未知审计链结果进缓存、已知结果不缓存。
- ruff 相对 HEAD 新增 0。

## 11 共享库【测试】文档端到端走查（2026-11-04 15:17~15:31 UTC，任务 7 / 8）

### 11.1 前置：用户录入 Key 并启用

- 用户 15:06 在模型配置页录入两条预设的 Key（与 qwen3.8 同一个）并启用。库里现状：`wemm-embedding-4b`
  （embedding / server）与 `qwen3-reranker-4b`（rerank / server）均 `is_active=true` 且有密文；本机向量行
  `Kbenkhaled/Qwen3.5-27B-NVFP4` 按「向量只启用一条」被自动停用。
- 审计：4 条 `ai_model_config_changed`（v2 哈希）—— 每条预设各一条录 Key（`credential_changed=true`）与一条启用
  （`=false`）。审计链写入恢复后不再 fail-closed，这正是第二批解除阻断的直接效果。
- `GET /api/ai-models/routes`（配置页「调用路由」面板的数据源）：向量 = 服务器 `wemm-embedding-4b`，`status=available`
  1702 ms；重排 = 服务器 `qwen3-reranker-4b`，`status=available` 1686 ms。此前分别是「模型或 API 路径不存在」与
  「未启用重排模型」。

### 11.2 入索引

- 经真实上传端点 `POST /api/knowledge-library/folders/{id}/upload` 往新建的【测试】全所公开目录传 4 篇 txt：
  一篇四段综合（坏账准备 / 存货 / 折旧 / 收入确认），三篇单主题（存货、固定资产、收入确认）。只发会计概念短句。
- 索引由后台 `run_indexing_pipeline` 写入（公开目录 ⇒ 全局哨兵分区 `00000000-…`；文档级 `project_ids` 为空时
  `trigger_index_update` 按设计直接返回，不重复索引）。
- 4 篇 `index_status=indexed`；`knowledge_index` 4 行，每行 `embedding_model='wemm-embedding-4b@1024'`、
  `embedding_vec` 非空、`vector_dims=1024`、L2 范数 1.0000（与网关 MRL 归一化输出一致）。
- 分块：单篇正文 349 字 < `_CHUNK_SIZE=500` ⇒ 每篇 1 块。

### 11.3 检索与重排

三条查询，`semantic_search`（普通）与 `semantic_search_strict`（DSH 口径）各跑一遍，首位均为预期文档：

| 查询 | 首位 | 重排分 | 召回分 |
| --- | --- | --- | --- |
| 坏账准备怎么按预期信用损失模型计量 | 综合篇 | 0.9425 | 0.7881 |
| 存货期末按成本与可变现净值较低者计量 | 存货篇 | 0.9998 | 0.9007 |
| 固定资产折旧方法有哪些，改变折旧方法怎么处理 | 固定资产篇 | 0.9999 | 0.9038 |

重排**确实改变顺序**（同一函数，只把重排路由注入为空作对照，不改库、不停用模型行）：

| 查询 | 纯向量顺序 | 开重排顺序 |
| --- | --- | --- |
| 资产负债表日要重新评估的那个减值准备怎么算 | 存货 → 验收 → 固定资产 → 收入确认 | **验收** → 存货 → 固定资产 → 收入确认 |
| 改变计提方式属于会计估计变更还是会计政策变更 | 固定资产 → 验收 → 存货 → 收入确认 | 固定资产 → **存货 → 验收** → 收入确认 |
| 数量繁多单价较低的那类资产怎么按类别计提准备 | 存货 → 验收 → 固定资产 → 收入确认 | 顺序不变（本来就对） |

第一条是决定性的：问法只命中综合篇正文里的「在资产负债表日重新评估」，纯向量把「存货」排首位，重排纠正成综合篇。
开重排时每条都有 `rerank_score` 且 `recall_score` 保留原召回分；关重排时 `rerank_score` 全为 None。

DSH 严格检索走 MCP 工具本体 `mcp_tools.tool_kb_search`（只替换授权，检索与重排都是生产代码）：4 条结果，
综合篇 0.9882 居首，其余 0.3788 / 0.0059 / 0.0008。

### 11.4 两条边界行为（真实栈，非单测）

- **重排失败 fail-open**：把 `AIService.rerank` 注入抛错 ⇒ 结果非空、顺序与纯向量一致、无 `rerank_score`，
  日志「重排失败，保持召回顺序：RuntimeError」。语义召回本身成功，不因重排失败报成不可用。
- **其他向量模型签名不混比**：把本次查询的签名改成 `other-embed-model@1024` ⇒ 普通检索的向量命中全部被过滤
  （只剩 lexical），严格检索抛「语义检索不可用：知识库索引需按当前向量模型重建」而不是「没搜到」。
- **DSH 向量健康（R12）**：`embedding_route_health` 与启动自检 `_check_embedding_route` 同一函数，均
  `available=true`、`endpoint=https://ai.gt-china.com.cn:10010`、消息「向量模型「wemm-embedding-4b」（服务器）
  已配置（未检测连通性）」，`violations` 为空（网关在 DSH 受信清单内，不报 `local_only_violation`）。

### 11.5 清理与对账

- 走查前 `knowledge_index` 全表 0 行（清点时全表计数恰等于本次 4 行，可据此确认）。
- 先走平台删除接口 `DELETE /api/knowledge-library/folders/{id}`：目录 + 4 篇文档 + 4 行索引条目全部
  `is_deleted=true`；目录树与知识库搜索（4 个关键词）均 0 命中。
- 平台软删不清磁盘文件与 `asset_blobs`。随后在一个事务里彻底删除本次测试行：先写可还原备份（含索引向量文本），
  再校验「4 篇文档与目录都带【测试】前缀且已软删」、「blob 未被其他文档 / 附件版本 / AI 会话资源 / 证据提升引用」、
  「无证据提升引用这些文档」，然后按外键顺序删 index → documents → folders → asset_blobs，**同事务内**核验
  `knowledge_index` 全表 0 行、前缀命中 0、blob 残留 0 才提交（先 dry-run 回滚验证一遍）。
- 磁盘 4 个文件先备份再删除目录。备份都在 `backend/backups/enterprise-embedding-rerank-20261104/`（gitignore）：
  可还原行备份、走查状态、上传的 4 个文件，以及第二批的死信与 `ai_model_config` 快照。
- 保留不动：6 条 `logs` HTTP 操作日志（5 次 create + 1 次 delete，本次操作的留痕）。这两个知识库端点不写审计链，
  故审计链三项仍为 0。
- 走查后 `/api/health`：`audit_chain` 三项 0；`schema_drift` 11 项、critical 2 项仍只有别的会话的 V233 / V234
  checksum 漂移（健康端点因此仍 degraded，与本 spec 无关）。
