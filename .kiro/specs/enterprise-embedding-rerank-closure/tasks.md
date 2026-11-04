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
- [ ] 7. 共享库执行迁移、两条预设复用 qwen3.8 Key 并写审计、启用、浏览器实测（R7.1、R7.2）
  - 已完成：共享库 V261~V263 已执行（执行前核待执行集合恰为本次三条、备份 ai_model_config）；浏览器实测配置页
    （五条预设说明、重排 tab 与预设行、调用路由「重排模型」行与空态），console 无报错
  - 🔴 阻断：`__global__` 审计链有 9 处分叉 / 10 个未确认链尾且无链尾行，`append_audit_log` 对全局链 fail-closed
    ⇒ Key 写入与「启用」都写不进审计（界面同样会 500）；现有分叉确认工具只接受「恰 2 个链尾」，处理不了此状态。
    待用户决定后执行 `tmp_embed_rerank/copy_preset_key.py --apply` 与界面启用（design §8）
- [ ] 8. 端到端：【测试】知识文档 → 索引 → 语义检索 + 重排 → DSH 严格检索；清理并对账（R7.3）
  - 已完成：一次性库 + 真实致同网关走平台代码路径通过（入索引 5 块全带签名与 1024 维向量列、严格 / 普通检索
    都按重排排序且最相关排第一）；共享库上的【测试】文档走查待任务 7 启用后执行
- [x] 9. 提交并按 `push_version.py` 推送到当前分支
  - 在远端头的分离头 worktree 里按端拆四个提交：`chore(root)`（gitleaks 精确放行预设标识
    `gt_qwen3_reranker_4b`，V262 的 `preset_key = '…'` 被 generic-api-key 误报）/ `feat(server-ai)` /
    `feat(web-ai)` / `docs(spec)`，同一版本标签原子推送；主工作区里其他会话未提交的 INDEX 行不带入
