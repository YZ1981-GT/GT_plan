# 企业向量 / 重排模型接入与知识库向量检索修通 — 任务

- [x] 1. spec 三件套 + INDEX 登记（R1~R7）
- [x] 2. 重排模型类型与企业预设（R1、R2）
  - `AIModelType.rerank`、provider 支持、两条预设（向量声明 1024 维）、rerank 启用唯一索引（ORM）
  - `llm_runtime.rerank` / `test_runtime_config` / rerank 无启用行返回空路由；`llm_route.route_rerank`
  - `model_route_status` 加重排路由
- [x] 3. 向量调用与知识库索引（R3、R4、R5、R6）
  - `embedding` 发 `dimensions` 并校验；向量 / 重排按数据政策过滤；记录向量模型签名
  - `_upsert_chunk` 按列存在与维度写 `embedding_vec`、写签名；ORM 去外键、加列、TEXT
  - `_vector_search` 按签名过滤；其他签名分块的兜底与严格检索提示；重排阶段 fail-open
  - 顺带修 `check_embedding_health`（未传 db、调用不存在的方法，恒 False）
- [x] 4. 迁移 V261~V263 + R261~R263：一次性库 V → R → V 验证后放入 `backend/migrations/`（R4、§5）
- [x] 5. 前端：类型、tab、类型选项、说明文案、停用后果、空态、未启用重排不标红（R2.1、R2.3）
- [x] 6. 测试：新增用例 + 相关既有套件回归 + 关键判据磁盘变异（R1~R6；证据见 design §7）
- [x] 7. 共享库执行迁移、两条预设录入 Key（用户在界面手动录入，2026-11-04 改口）、启用、浏览器实测（R7.1、R7.2）
  - 已完成：共享库 V261~V263 已执行（执行前核待执行集合恰为本次三条、备份 ai_model_config）；浏览器实测配置页
    （五条预设说明、重排 tab 与预设行、调用路由「重排模型」行与空态），console 无报错
  - ~~🔴 阻断：`__global__` 审计链有 9 处分叉 / 10 个未确认链尾且无链尾行，`append_audit_log` 对全局链 fail-closed
    ⇒ Key 写入与「启用」都写不进审计（界面同样会 500）；现有分叉确认工具只接受「恰 2 个链尾」，处理不了此状态。
    待用户决定后执行 `tmp_embed_rerank/copy_preset_key.py --apply` 与界面启用（design §8）~~
    → 2026-11-04 第二批已确认分叉、解除阻断（任务 14，design §9.6）；复制密文作废（用户改口为界面手动录入，脚本已删）
  - 用户 2026-11-04 15:06 UTC 在模型配置页录入两条预设的 Key 并启用；库里 `wemm-embedding-4b`（向量）与
    `qwen3-reranker-4b`（重排）均 `is_active`、有密文，本机向量行按「向量只启用一条」自动停用；4 条
    `ai_model_config_changed` 审计（v2 哈希，录 Key 的 `credential_changed=true`、启用的 `=false`）
  - `GET /api/ai-models/routes`（配置页「调用路由」面板数据源）：向量 = 服务器 `wemm-embedding-4b` 可用 1702 ms、
    重排 = 服务器 `qwen3-reranker-4b` 可用 1686 ms，不再是「不可用」/「未启用」
- [x] 8. 端到端：【测试】知识文档 → 索引 → 语义检索 + 重排 → DSH 严格检索；清理并对账（R7.3）
  - 已完成：一次性库 + 真实致同网关走平台代码路径通过（入索引 5 块全带签名与 1024 维向量列、严格 / 普通检索
    都按重排排序且最相关排第一）
  - 共享库【测试】文档走查（2026-11-04 15:17~15:31 UTC，证据见 design §9.7）：4 篇文档经真实上传端点入索引、
    签名与 1024 维向量齐备；三条查询的普通 / 严格检索首位均正确；重排确实改变顺序（纯向量把「存货」排首位，
    重排纠正为「坏账准备」那篇）；DSH `kb_search` 工具命中并按重排排序；重排失败 fail-open、其他签名分块
    不混比两条边界行为在真实栈上复现；清理走平台删除接口后再彻底删除测试行与磁盘文件，`knowledge_index`
    回到走查前的 0 行
- [x] 9. 提交并按 `push_version.py` 推送到当前分支
  - 在远端头的分离头 worktree 里按端拆四个提交：`chore(root)`（gitleaks 精确放行预设标识
    `gt_qwen3_reranker_4b`，V262 的 `preset_key = '…'` 被 generic-api-key 误报）/ `feat(server-ai)` /
    `feat(web-ai)` / `docs(spec)`，同一版本标签原子推送；主工作区里其他会话未提交的 INDEX 行不带入

## 第二批：范围外问题收口（R8~R13，设计见 design §9）

- [x] 10. 分叉确认工具：`append_fork_acks`（多死端、侧枝根、v2 哈希、写后 `read_head` 校验）、`_unconfirmed_tails` 同口径单查询、
  `scan_forks` 链键过滤、运维脚本计划输出与多 `--dead`、`audit_chain_heads.py` 减已确认死端（R8.1~R8.3）
  - 变异 M01~M04、M14 全红；真 PG 多死端用例通过（design §9.6）
- [x] 11. 审计队列：逐条校验进死信、健康端点 `dead_letter_entries`、测试审计日志只进 fakeredis、`AuditChainError` → 503（R9.1~R9.3、R10）
  - 变异 M05~M08 全红
- [x] 12. 模型配置：路由请求体与规范化移到服务层模块、不可达提示按类型改准、更新口径与启用一致、`clear_api_key=false`
  不算连接变更、无 Key 预设不能启用（R11）
  - 变异 M09~M11 全红；`routers/ai_models.py` 684 行（行数门以内，未加白名单）
- [x] 13. DSH 向量探针按实际向量路由判定（`/capabilities` 与启动自检同一函数）（R12）
  - 变异 M12 全红
- [x] 14. 共享环境执行：一次性库按共享库链数据演练 → 共享库演示留档 → 两条链执行确认 → 校验链尾 / 扫描 / 链校验 / 健康；
  隔离区合法条目回放；测试滞留条目备份后清理（R8.4、R9.4）
  - 确认条目：`__global__` 10 条（最后一条 `81b55994-b60f-4853-8f84-00a5b838798d`）、重药安徽项目链 1 条
    （`ffed5464-eb39-4bd6-b4ff-bc7d9a2cfb7d`）；复查 `blocked_chains` 空、无未确认分叉、`verify_chain` valid；
    隔离区 45 条由 9980 重放写入（全局链 1866 → 1911）；39 条测试死信备份后删除；健康端点 `audit_chain` 三项 0
  - 偏离：没有另建一次性库复制共享链数据演练，由真 PG 用例覆盖同一路径（design §9.6）
- [x] 15. 回归（候选 vs HEAD 基线）、关键判据磁盘变异、浏览器实测模型配置页
  - 第二批：248 + 11（真 PG）通过、变异 14 / 14；逐节点回归在第三批补做（任务 20），抓到 3 个既有健康用例变红并修复
  - 浏览器：无 Key 预设「启用」被拒并提示、「录入 Key」弹窗可取消，console 无新错误（design §9.6）
- [x] 16. 文档收口：S10 任务 4 追加执行记录、本 spec、INDEX、memory；删除一次性脚本（R13）
- [x] 17. 按端拆提交并 `push_version.py` 推送
  - 代码 v1.0.118；三件套第二批文字随第三批推送（v1.0.118 漏带）

## 第三批：第二批推送后复核（R14、R15，设计见 design §10）

- [x] 18. schema 漂移检测：`db_compare_type` 只把 `public.vector` 归一成 `VECTOR`；整次扫描超时 / 抛错与读快照失败记
  critical `scan_failure`（只带异常类型）；快照写库失败不抛错（R14）
  - 共享库只读扫描：`knowledge_index.embedding_vec` 不再报 type_mismatch；v1.0.120 推送后 9980 热重载重新扫描，健康端点
    漂移 12 → 11 项、不再列出这一列（剩余 critical 2 条是其他会话的 V233 / V234 checksum 漂移）
- [x] 19. 审计链健康只缓存已知结果；既有健康用例显式声明审计链干净（R15）
- [x] 20. 第三批验证：124 个相关文件逐节点回归（基线 = 远端头去掉第二批），新增红 4 个全部归因并处理；修后 121 passed、
  真 PG 11 passed；磁盘变异 12 / 12 全红 + 1 条阴性对照；ruff 新增 0；按端拆提交并推送
