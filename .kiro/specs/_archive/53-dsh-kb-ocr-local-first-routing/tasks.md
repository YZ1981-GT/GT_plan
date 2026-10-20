# 任务：DSH 子进程与知识库扫描件 OCR 接入本机优先路由

- [x] 1. 拆分 `dsh_engine.py` / `dsh_discovery.py` 到 ≤800 行（行为不变）
  - 按 design §3.1 抽出 `dsh_cordis_policy` / `dsh_smoke` / `dsh_process` / `dsh_protocol`，原模块再导出
  - 拆分前后跑同一组 DSH 测试，失败集合一致
  - _需求：4.1_
  - 证据：拆分前后 7 个 DSH 测试文件均为 3 failed / 273 passed，失败集合相同（3 个 pin 用例）

- [x] 2. vendor 根目录与 pin 检出
  - `settings.DSH_VENDOR_ROOT`（默认值不变），`dsh_discovery.DSH_VENDOR_ROOT` 改读它
  - 本机 `D:\dsh_vendor_pinned` = pin 提交 + node 闭包；`.env` 配置、`.env.example` 说明
  - _需求：3.5；design ADR-DKR-004_
  - 证据：`discover_dsh_sdk` 对该目录返回 available、`validate_version_pin` 无错误；`test_dsh_discovery_task27.py` 57 passed

- [x] 3. 协议对齐 vendor（`dsh_protocol.py`）
  - `initialize`（`deepseek-official` + 候选模型名）→ `session/prompt` → 消费通知到本 session idle → `shutdown`
  - 事件映射：chunk text-delta / tool/call / tool/result / turn/end / assistant/message 兜底
  - 假运行时脚本测试：成功、turn/end error、取消、子进程提前退出
  - _需求：3.1、3.2、1.5_
  - 证据：`test_dsh_protocol_vendor.py` 10 passed（假运行时 `_fake_dsh_runtime.py`，tool/result 形状取自真实抓包）

- [x] 4. Cordis 配置、子进程 env 与进程树
  - 模型服务真实键名 + `maxTokens` / `contextWindow` 按候选；`retryPolicy` 收紧
  - `mcp-client` stdio 配置拉起 audit-data MCP（`MCP_TOKEN`），删除平台侧孤儿 MCP 进程
  - `DSH_HOME` / 会话目录隔离；env 不继承父进程；Key 不进 env 与配置文件
  - 取消 / 超时 / 结束：`shutdown` → 进程树终止 → 删会话目录
  - _需求：1.3、1.4、1.7、3.3、3.4_
  - 证据：孙进程心跳文件在终止后停止更新；`_resolve_mcp_server_path` 旧候选路径指向 `backend/tools`（不存在）已改为仓库根

- [x] 5. 模型桥：预检选候选、签名令牌、环回转发端点
  - `select_run_candidate` 共用探测缓存与冷却；无可用候选 ⇒ `engine_unavailable` 并列原因
  - 令牌签发 / 校验（篡改、过期、run 不符）；转发端点只收环回、无 XFF
  - 参数重写与 `build_chat_payload` 同一份思考参数规则（`llm_runtime.reasoning_fields`）；上游错误分类决定是否冷却
  - Cordis 校验器要求模型服务 `baseURL` 是环回转发地址、`apiKeyEnv` 不是 `DEEPSEEK_API_KEY`；上游端点按平台受信策略（`validate_dsh_upstream`），不受信 ⇒ `local_only_violation`。`validate_model_route` 不改（仍服务 `.env` 健康检查）
  - _需求：1.1、1.2、1.5、2.1~2.3_
  - 证据：`test_dsh_model_bridge.py` 42 passed（含四种代理头、403 冷却、成功转发清冷却、gzip 上游按解压字节回传、令牌密钥来自平台密钥）
  - 实施中修正（design §1.3 D11）：转发令牌与既有 MCP scoped token 的签名密钥原读不存在的 `settings.SECRET_KEY`（恒为源码常量，可伪造），两处改派生自 `JWT_SECRET_KEY`；`test_ai_chat_mcp_token.py::TestSigningKey` 2 例

- [x] 6. 引擎接线
  - usage / done 记录实际模型名与部署位置
  - 失败映射按 design §4
  - _需求：1.6、1.8、3.5_
  - 证据：真实运行 usage 含 `model` / `deployment` / `fallback_used` / token 用量；`test_dsh_protocol_vendor.py` 15 passed（新增 max-tokens 收尾、会话初始 idle 不提前结束、scoped token / 转发令牌签不出时 typed error 且不留会话目录 —— design §1.3 D12）

- [x] 7. 知识库：迁移 V198 / R198 + ORM
  - 四列 + 部分索引，`IF NOT EXISTS`；R198 可回滚
  - _需求：5.8_
  - 证据：`test_knowledge_background_ocr_pg.py::test_v198_r198_roundtrip_on_real_postgres`（真 PG 临时 schema：ORM 建表形态 = V198、ORM 与 V198 都带 CHECK、R198 去列与索引且正文保留、V198 重跑幂等）；开发库已应用 V198（`information_schema` 核对四列）

- [x] 8. 知识库：OCR 服务与 worker
  - 认领（PG `SKIP LOCKED` / SQLite 条件更新）、租约、围栏写回、退避重试、终态
  - 写回后刷新索引；worker 注册到启动流程，上传提交后唤醒
  - _需求：5.2、5.3、5.5_
  - 证据：`test_knowledge_background_ocr.py` 46 passed（认领 / 写回 / 退避 / 终态 / 租约重认领 / 围栏三种竞态 / 次数用尽后迟到结果丢弃 / worker 开关与唤醒）；`test_knowledge_background_ocr_pg.py::test_claim_skips_rows_locked_by_another_worker_and_fences_stale_results`（真 PG 两会话）

- [x] 9. 知识库：上传、列表、重试端点；OCR 冷却口径
  - 上传去掉请求内 MinerU，正文为空且可 OCR ⇒ 待识别，回执 `ocr_queued`
  - 列表返回 `ocr_status` / `ocr_error`；重新识别端点（与删除同一管理权限）
  - `unified_ocr_service` 只对 unavailable / config 冷却，读超时归 timeout
  - _需求：5.1、5.4、5.6_
  - 证据：同上文件的上传 / 列表 / 重试 / 冷却 / 远程失败归类（9 种原因逐一）用例；`test_knowledge_content_text.py` 14 passed（4 个 MinerU 用例按新契约改写）

- [x] 10. 知识库：前端
  - 上传汇总与列表按状态提示，删除「需开启 OCR」旧文案；重新识别按钮；待识别时 5 秒轮询
  - _需求：5.7_
  - 证据：`knowledgeUpload.ts`（`isOcrEligible` 与后端同一份类型、`noTextHint` 按状态、汇总分「已排队 / 可识别未排队 / 不能识别」三行）、`KnowledgeBase.vue`（状态标记、可管理且可识别才给「重新识别」、轮询静默 + 不去重 + 原地更新不清勾选、卸载即停）、A17-3 上传提示、`apiPaths.documentOcrRetry`；vitest 3 文件 98 passed；ESLint 0 error（8 条 warning 均为既有代码）；单区域 vue-tsc 改动前后同为 8 条既有错误、无新增；`test_frontend_knowledge_paths_exist.py` 6 passed

- [x] 11. 测试、变异与真实验收
  - 新增 / 改动守卫逐条磁盘注入变异、逐字节恢复
  - 真实 PG：认领不重复、租约重认领、围栏
  - DSH 真实运行：本机 vLLM；本机不可用 ⇒ 服务器 qwen3.8
  - Playwright：上传扫描 PDF → 识别中 → 完成，AI 可检索到识别文字
  - _需求：全部_
  - 证据（变异在独立 worktree 里做，不碰主工作树与共享 dev server；每条注入后逐字节恢复并校验 sha256）：知识库后端 38/38、DSH 54/54、前端 23/23 全部打红且红在预期用例（变异清单 design §5）
  - 真实 PG：两会话 `SKIP LOCKED` 不重复认领、租约过期重认领、围栏丢弃迟到结果（`test_knowledge_background_ocr_pg.py` 2 passed，临时 schema 用完删除，`kiro_%` 残留 0）
  - DSH 真实运行（令牌密钥修正后重跑）：本机 Qwen3.5 调 `wp_list` 取真实底稿并回答（6.2 秒）；模拟本机不可用 ⇒ 服务器 qwen3.8 回答（`fallback_used: true`）
  - Playwright（私有【测试】文件夹，验收后界面删除 + 清掉 1 文件夹 / 3 文档行 / 3 个存储文件）：上传汇总显示「扫描件已交给后台识别文字」；12 页扫描件列表先显示「⏳ 正在识别文字…」（无「重新识别」），5 秒后轮询刷新标记消失；把一份改成识别失败后界面显示原因与「重新识别」，点击后转「⏳ 排队识别中…」再完成；本机没装 OCR 引擎 ⇒ 实际由服务器 paddleocrv6 识别（`fallback_used: true`），三份正文逐字正确；知识库搜索与 AI 全局知识检索（`search_global_knowledge`）均命中识别出的正文；控制台 0 error

- [x] 12. 文档
  - `docs/reference/llm-provider-configuration.md`：DSH 路由、pin 检出与闭包构建步骤、知识库 OCR
  - _需求：全部_
  - 证据：该文档新增 §3「知识库扫描件的后台识别」（可 OCR 类型、worker 开关与认领 / 租约 / 围栏、状态与退避、重新识别端点、冷却口径）与 §9「DSH 智能体子进程的模型路由」（选候选、环回转发与令牌、冷却、上游受信、pin 检出与闭包三步 —— 取自 vendor `scripts/build-exe-for-python-sdk.ts` 的 `deployStaging` 源码）；`.env.example` 已说明 `DSH_VENDOR_ROOT` 与 `KNOWLEDGE_OCR_WORKER_ENABLED`
