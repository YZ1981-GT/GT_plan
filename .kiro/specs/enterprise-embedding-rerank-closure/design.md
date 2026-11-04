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
- **ADR-ER-6 Key 复用 = 复制密文**：同一 `ENCRYPTION_KEY` 下 Fernet 密文与行无关，复制即可解密；
  明文不出现在请求、日志或脚本输出里；按路由同口径写 `ai_model_config_changed` 审计（credential_changed）。
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

## 6 范围外（登记不改）

- DSH 能力探针 `_check_embedding_health` / `startup_health._check_embedding_local` 只看 `.env`
  `LLM_EMBEDDING_BASE_URL` 做 local-only 判定，不看库里启用行；改它涉及 DSH local-only 政策，另议。
- `KnowledgeIndexService.build_index`（业务数据入索引）全仓无调用方；本次只修通知识文档链路。
- 批量向量化（网关支持 `input: [...]`）：入索引是后台任务，逐块调用可接受，暂不做。
- `routers/ai_models.py::_local_unavailable_warning` 对向量写死「本机恢复前向量检索不可用」，服务器预设
  不可达仍启用时措辞不对；重排走通用分支说「AI 调用会失败」（实际 fail-open）。只出现在「预设不可达仍启用」
  路径；该文件 HEAD 869 行、超 800 行门禁且未登记白名单，改一行即被 pre-commit 拒，本次不动。路由本身
  对 rerank 无需改动（provider 校验、启用槽位、测试连接都走通用分支）。

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
- 剩余步骤的做法（分叉处理后执行）：同一事务里把 `gt_qwen38` 行的 `api_key_ciphertext` 原样复制到
  `gt_wemm_embedding_4b` / `gt_qwen3_reranker_4b`（同一 `ENCRYPTION_KEY` 下密文与行无关，明文不经请求和日志；
  已有 Key 的行不覆盖），更新 `api_key_updated_at`，按模型配置路由同口径追加 `ai_model_config_changed` 审计
  （`credential_changed=true`、`credential_source=copied_from_preset:gt_qwen38`，before / after 取
  `_audit_model_snapshot`）；一次性脚本 `tmp_embed_rerank/copy_preset_key.py`（默认演练回滚，`--apply` 提交），
  也可在界面「录入 Key」手填同一个 Key。然后在界面启用两条预设（向量预设替换本机 Qwen3.5 向量行），
  建【测试】知识文档走查索引 → 语义检索 + 重排 → DSH 严格检索，最后清理并对账。
- 旧代码后端（其他会话未拉取本提交的 worktree）读全部模型配置时会因库里的 rerank 行抛 LookupError；拉取后消失。
- 共享 `schema_drift_log` 由所有连到共享库的后端写入，旧代码后端扫描后会显示 `knowledge_index.embedding_model`
  为 db_extra，不代表本 spec 有漂移（9980 实测 `/api/ai-models` 已列出 rerank 行）。
