# LLM / OCR 本机优先路由收口 — Design

## 1. 现状实测（2026-10-19，本机 + 本地 PG）

| 项 | 实测 |
|---|---|
| 本机 vLLM 8100 | 在线，`/v1/models` = `Kbenkhaled/Qwen3.5-27B-NVFP4`；`/v1/embeddings` → 404 |
| 本机 8101（bge-m3） | 拒连（本机关闭端口的连接约 1.5 秒才报错） |
| 本机 OCR | paddleocr / pytesseract / tesseract 均未安装，`OCR_SERVICE_URL` 未设，MinerU 关闭 |
| ai_model_config | chat：本机 Qwen3.5 未启用、qwen3.8 启用；embedding：Qwen3.5@8100 启用（不可用）；OCR：本机 paddleocr 与两条远程均未启用（远程已录 Key） |
| 调用点 | chat 147 处：143 经统一运行时；绕开 3（structured_llm_service / LLMService / DSH）；J2 导入不存在函数恒失败；4 处参数错误（3 处会累计全局熔断）；2 处强制 `.env` 模型名；6 处把 `.env` 默认名记为生成模型 |
| OCR 调用点 | 26 个路由 + ocr_fields + 附件 AI 对话 + 凭证 OCR 都走 `UnifiedOCRService.recognize`（AUTO）；知识库扫描件直连 MinerU |

## 2. 决策

### ADR-ROUTE-001 部署位置存库、由端点推导
新增列 `ai_model_config.deployment`（`local` / `server`，CHECK 约束）。应用层在创建 / 更新 / 种子 / 迁移回填时统一用 `classify_deployment()` 计算：`ocr_protocol='local'` 或端点主机字面量为 `localhost` / `127.0.0.0/8` / `::1` ⇒ `local`，其余 ⇒ `server`。按字面判定、不做 DNS 解析（企业网关内网解析到 192.168.0.41 也是服务器）。存库是为了让唯一约束在 DB 层成立；不提供手工改写。

### ADR-ROUTE-002 启用语义
`is_active` 含义由「唯一生效」改为「参与路由」。唯一约束：
- chat：`(model_type, deployment)` ⇒ 本机、服务器各最多一条；
- embedding：`(model_type)` ⇒ 仍只一条（ADR-ROUTE-006）；
- ocr：`(ocr_capability, deployment)`。

启用只替换同类型（OCR 同能力槽）同部署位置的那一条。新增停用；已启用不可删除。某类无启用行时保持现行兜底（`.env` / 本机进程内 OCR）。

### ADR-ROUTE-003 错误分类决定是否转移
`LLMRuntimeError` 增加 `kind`：
| kind | 来源 | 转移 |
|---|---|---|
| unavailable | 连接失败、连接超时、HTTP 5xx、端点解析 / 策略拦截 | 是 |
| config | 401/403、404、非 OpenAI 兼容响应、缺 Key、配置非法 | 是 |
| request | 400/422/429、其他网络读写错误 | 否 |
| timeout | 读取超时（请求已被接收） | 否 |
| output | 空回复、超出 token 限制 | 否 |

`failover = kind in {unavailable, config}`。启用本机模型时只有 `unavailable` 允许「带提示启用」（R4.2），`config` 拒绝。本机候选连接超时收紧为 `LLM_LOCAL_CONNECT_TIMEOUT_SECONDS`（默认 3 秒）。

结构化输出经 openai SDK，同一口径按异常类名与 `__cause__` 判定（`_should_fail_over`）：连接阶段失败 / 端点被拦 / `InternalServerError` / 鉴权 / `NotFoundError` 转移，读超时、限流、参数错误、校验失败不转移；不转移的连接类失败（如读超时）仍按旧口径计入熔断。SDK 自带的 2 次重试保留，代价是本机刚挂掉后的首个结构化请求多等几秒，之后冷却期内直接跳过。

### ADR-ROUTE-004 冷却期
进程内按候选身份（`model_type|provider|endpoint|model`）记录最近一次失败；转移类失败后 `LLM_ROUTE_COOLDOWN_SECONDS`（默认 30）内跳过该候选（仍有后续候选时）。全部在冷却期则按顺序全部尝试。成功即清除。只在进程内，不落库（多 worker 各自探测，代价是每个 worker 冷却期首个请求多一次失败尝试）。身份含模型类型：本机 8100 现状是同一端点同一模型名同时登记为对话与向量，不含类型时向量 `/embeddings` 404 会让对话跳过本机 30 秒。冷却跳过的候选在成功的 `attempts` 与全部失败的报错里都列出。

### ADR-ROUTE-005 调用方模型名只作优先提示
`requested_model` 等于某条已启用候选的模型名 ⇒ 排到最前；否则忽略。修掉「端点取 DB、模型名取 `.env`」的错配（qwen3.8 端点收到本机模型名 → 404）。无启用行走 `.env` 时保持旧语义（模型名 = requested 或默认）。

### ADR-ROUTE-006 向量不跨模型转移
已存向量与查询向量必须同模型，自动转移会让检索静默失真（同维度）或整次失败（不同维度）。向量只启用一条、失败直接报错；状态检测发真实 `/embeddings`。企业网关当前无向量模型，现库内向量行不可用 ⇒ 状态页如实显示，不改数据。

### ADR-ROUTE-007 熔断按整条路由
`llm_client._breaker` 身份 = 路由内候选身份串联。本机失败、服务器成功记成功；全部失败才记失败。调用方参数错误（非 `LLMRuntimeError`）不计入熔断（修 3 处参数错误调用每次都累计熔断、60 秒内拖垮全部 AI 功能的问题）。

### ADR-ROUTE-008 实际服务模型
路由执行成功后写 `ContextVar`：`model_name / deployment / model_id / fallback_used / attempts`。`last_route_outcome()` 与 `served_model_label()` 供记录方读取（同一请求上下文内）。AI 对话消息、底稿 AI 内容来源、批量复核、A17、B14、底稿说明草稿改记实际服务模型。

### ADR-ROUTE-009 OCR 路由
候选（按能力槽）：本机 = 已启用的本机行（`ocr_protocol=local` ⇒ 进程内引擎链或 `OCR_SERVICE_URL` 容器；环回 PaddleX ⇒ HTTP 适配器），服务器 = 已启用的远程行。无启用行：文字识别 ⇒ 隐式本机进程内；版面解析 ⇒ 报「未配置」。OCR 幂等，非最后一个候选的任何失败都转移；最后一个失败抛 `OCRServiceUnavailableError` 并逐个列原因。结果附 `route`（部署位置 / 模型 / 是否兜底）。本机引擎链修两处：Paddle、Tesseract 都不可用时仍试 MinerU；Tesseract 可用 = 能 import 且程序存在。显式 `TESSERACT` / `MINERU` 模式保持只走本机引擎。

### ADR-ROUTE-010 状态接口
`model_route_status.collect_route_status()`：按 chat / embedding / ocr / layout_parsing 列候选（含隐式兜底）、状态、原因、当前生效。探测：chat `GET /models` 且模型名在列表内；embedding 发 1 条 `/embeddings`；本机 OCR 查引擎安装；远程 OCR 用内置 240x64 测试图真实识别。结果按候选缓存（对话 / 向量 30 秒、远程 OCR 60 秒），`refresh=true` 强刷；叠加 ADR-ROUTE-004 的冷却记录。`AIService.health_check()` 由它派生（兼容既有字段，新增 `routes`）；公共 `/api/ai/health` 去掉端点地址。

同一候选并发只探一次：按候选加锁，「强刷是否可复用别人刚探的结果」用**探测次数**判断（请求入口取快照，等锁期间次数增加 ⇒ 结果晚于本次请求），不比较时间 —— Windows 上 `monotonic` 精度约 15.6 ms，同一刻内完成的旧探测会被当成新的，强刷失效。探测缓存成功之后又有实际调用失败（冷却中）时，以更新的调用记录为准显示「不可用」，与路由跳过它的事实一致。

## 3. 模块

| 文件 | 改动 |
|---|---|
| `models/ai_model_options.py` | `AIDeployment` 枚举；`endpoint_is_loopback()` / `classify_deployment()`；`active_route_indexes()`（ORM 与 V197 同一组索引） |
| `models/ai_models.py` | `deployment` 列 + 三条新唯一索引 |
| `services/llm_runtime.py` | `kind`、`deployment`、`identity`；`RouteCandidate` / `resolve_route()` / `order_candidates()`；`resolve_runtime_config()` 取路由首个可用；本机连接超时；JSON / 策略错误归类 |
| `services/llm_route.py`（新） | 冷却记录、`route_chat_sync` / `route_chat_stream`、路由结果 ContextVar、`served_model_label` |
| `services/model_route_status.py`（新） | 状态汇总、探测与缓存 |
| `services/llm_client.py` | 走路由；熔断按路由；参数错误不计熔断 |
| `services/ai_service.py` | chat 走路由；`get_active_model` 按路由顺序；启用按部署位置 + 本机带提示；`disable_model`；健康派生自状态；本机 OCR 校验改查引擎链 |
| `services/remote_ocr_runtime.py` | `deployment`；`resolve_ocr_route()` |
| `services/unified_ocr_service.py` | 本机优先 + 服务器兜底；MinerU 可达；Tesseract 程序检查；`local_engine_status()` |
| `services/structured_llm_service.py` | 按候选建客户端 + 转移；guided_json 只发本机 |
| `services/llm_service.py` | `generate()` 走路由 |
| `services/ai_chat/native_model_client.py`（新） | 从 `native_engine.py`（812 行，超门禁）原样抽出模型接缝，记录实际服务模型 |
| `routers/ai_models.py` | 启用 / 停用 / 路由状态端点；`deployment`；删除与改端点冲突规则 |
| 调用点 | J2（导入 + 登录鉴权）、role_ai_features ×2、workhour_service、work_hour_nlp、wp_explanation_service、wp_guidance_chat、wp_ai_service、batch_review_service、a17、b14；实施中新发现 G8 / G9 AI 生成（`system=` / `user=`）、report_trace 底稿推荐（字符串当 messages），见 §9 |
| 前端 | `aiModelApi.ts` / `apiPaths/system.ts` / `AIModelConfig.vue` / `ModelTable.vue`；新 `components/ai/ModelRoutePanel.vue` + 纯函数 `modelRouteView.ts` |

## 4. 迁移 V197 / R197
V197：加列（可空）→ 按 ADR-ROUTE-001 回填 → `SET DEFAULT 'server'`、`SET NOT NULL` → CHECK → 删 `uq_ai_model_config_active_non_ocr` / `uq_ai_model_config_active_ocr_capability` → 建 `uq_ai_model_config_active_chat_route` / `uq_ai_model_config_active_embedding` / `uq_ai_model_config_active_ocr_route`。全部 `IF [NOT] EXISTS`。
R197：同类型（OCR 同槽）多条启用时只保留服务器那条（本 spec 前的语义里服务器行是用户显式激活的），再恢复旧索引、删新索引与列。

## 5. 接口
- `POST /api/ai-models/{id}/activate` → `{message:"已启用", model_name, provider, deployment, warning}`；`warning` 按实际后果三选一：有已启用服务器模型 ⇒「调用时会自动使用已启用的服务器模型兜底」；没有 ⇒「该类型尚未启用服务器模型，本机恢复前调用会失败」；向量 ⇒「向量模型不跨模型兜底，本机恢复前向量检索不可用」
- `PUT /api/ai-models/{id}` 同样返回 `warning`（已启用的本机模型改配置时本机不可用）
- `POST /api/ai-models/{id}/deactivate` → `{message:"已停用", model_name}`
- `GET /api/ai-models/routes?refresh=` → `{checked_at, routes:[{kind,label,policy,effective,error,has_local,has_server,candidates:[{model_id,model_name,deployment,provider,endpoint,source,reasoning_effort,implicit,status,reason,latency_ms,checked_at}]}]}`
- 模型 DTO 增加 `deployment`。

## 6. 前端
模型配置页顶部「调用路由」四行（对话 / 向量 / OCR 文字识别 / OCR 版面解析）：本机候选 → 服务器候选，各带状态点与原因，末尾「当前生效：本机 / 服务器 / 不可用」；向量行标「单模型，不跨模型兜底」。「检测状态」强刷。表格增加「部署」列（本机 / 服务器），标签「已启用 · 本机优先」/「已启用 · 服务器兜底」，按钮「启用 / 停用」；启用返回提示时用通知显示。

实施细化：本机优先的路由补出「未启用」的一端（看得出兜底链缺哪头）；服务器行在没有本机行时标「已启用 · 服务器」；停用二次确认写明停用后由谁承担调用。原四张健康卡片里的「向量库」卡显示的是 ChromaDB 心跳，而向量存储后端是 `VECTOR_STORE_BACKEND`（默认 pgtext），ChromaDB 不在调用链上 ⇒ 随健康卡一并去掉（`/api/ai-models/health` 的 `chromadb_status` 字段保留兼容）。「停用」按钮不用 warning 类型：`gt-polish.css` 给所有 `el-button--warning`（含 link）加渐变底。

## 7. 不在本 spec
| 项 | 原因 | 后续 |
|---|---|---|
| DSH 子进程端点（写死 8100 与 `Qwen3.5-27B-NVFP4`，与本机实际 served name 不一致） | `dsh_engine.py` 1069 行、`dsh_discovery.py` 891 行均超门禁未登记，任何改动须先拆分；既有 Req 12.1/12.2 本地限定；默认关闭 | 拆分后让 DSH 跟随本机候选 |
| 知识库扫描件 OCR（直连 MinerU） | 上传请求内同步执行，接服务器兜底会让上传等远程 OCR | 改后台 OCR 回填正文 |
| `/api/ai-chat/capabilities` 与启动自检模型健康 | 只读 `.env` 字符串，前端无消费方 | 随 DSH spec |
| `ocr_service_v2` 自建 PaddleOCR、`ai_service._get_*_client` | 无调用方 | 删旧代码单独提交 |
| 26 个 OCR 路由吞异常、`ocr_fields` 空文本记完成、retry-ocr 引用不存在的 `TaskType.ocr_upload` | 与路由无关的结果处理缺陷 | 单列 |
| `core/seed_ai_models.py`（零调用方） | 建行不写 `deployment`（默认 server），`ensure_active_chat_model` 用 `scalar_one_or_none()` 遇两条启用对话行会抛错；当前无人调用 | 删旧代码单独提交 |
| 模型配置页页头两个按钮横向拉满 | 既有样式问题，与路由无关 | 单列 |

## 8. 测试策略
- 纯函数：部署位置推导、候选排序、错误分类、冷却计划。
- 路由执行：本机不可达 → 服务器；本机 400 不转移；读超时不转移；流式首片段前转移、之后不转移；冷却期跳过；全部失败逐个列原因；ContextVar 记录实际模型。
- 熔断：本机失败 + 服务器成功不累计；参数错误不累计。
- 启用 / 停用：本机不可达带提示启用、本机 404 拒绝、服务器必须通过；同位置替换不动另一位置；已启用不可删；改端点冲突 409。
- OCR：本机引擎缺失 → 服务器；本机失败 → 服务器；服务器失败报错含原因；版面解析无启用 → 报错；MinerU 可达；Tesseract 无程序判不可用。
- 迁移：SQLite 建表 + PG MigrationRunner 实跑，索引语义（同位置第二条启用被拒、不同位置可共存）。
- 变异：去掉转移 / 冷却 / 排序 / 熔断聚合 / ContextVar / 唯一索引条件，各自以预期形态打红。
- 真实环境：本机 vLLM 在线时对话走本机；停用本机行或本机端口不可达时走 qwen3.8；OCR 走 paddleocrv6；版面解析走 paddleocrvl-1.6；Playwright 看状态面板与启用 / 停用。

测试文件：`test_llm_local_first_routing.py`（部署位置 / 排序 / 错误分类 / 冷却 / 路由执行 / 流式 / 熔断 / 唯一索引）、`test_ai_model_route_admin.py`（启用规则 / 停用 / 删除 / 改端点 / 路由状态缓存与并发 / 公共健康）、`test_ocr_local_first_routing.py`、`test_v197_route_migration_pg.py`（pg_only：临时 schema 里 R197 → V197 往返，回填与运行时分类逐行一致）、`test_chat_completion_call_contract.py`（全仓 AST 契约）、`test_j2_ai_generate_route.py`、`dsh_agent_panel/test_native_model_client_guard.py`；前端 `aiModelApi.spec.ts`、`modelRouteView.spec.ts`。

## 9. 实施记录（2026-10-19~20）

偏差与新发现（均已修 + 测试）：
1. 调用点比盘点多 3 处：G8 / G9 AI 生成传 `system=` / `user=` / `db=`（G8 恒占位、G9 恒 500，原测试接受 500 是假绿），report_trace 底稿推荐把字符串当 messages（恒走降级）。全仓守卫 `test_chat_completion_call_contract`：AST 扫描三个同名入口，**按函数作用域解析局部变量**——第一版只认字面量，变异 M17（把列表改回 `prompt` 变量）没打红，而现场三处正是变量写法；改后才抓到 report_trace。
2. 候选身份不含模型类型 ⇒ 对话与向量同名同端点时互相污染冷却与探测（见 ADR-ROUTE-004）。
3. 强刷在 Windows 时钟精度下失效、并发请求在入口之后才取基准 ⇒ 改探测次数 + 入口快照（见 ADR-ROUTE-010）。
4. 状态页可能显示缓存的「可用」而路由已在跳过 ⇒ 以更新的调用记录为准。
5. 全部失败的报错漏掉冷却跳过的候选 ⇒ `cooling_notes()`，对话、结构化输出、OCR 三处共用。
6. R4.2 的提示原文「调用时自动使用服务器兜底」在没有服务器行或向量时不成立 ⇒ 按实际后果三选一（§5）。
7. 行数门禁：`test_task6_native_engine.py` 在 HEAD 已 1691 行且未登记，不在其中加锚点，守卫扩展放进新文件 `test_native_model_client_guard.py`（含「判据没空转」的反向断言）；OCR 路由用例单独成文件，避免 `test_llm_provider_multi_provider.py` 越过 800 行。

变异证明（28 条，均在只含本次改动的干净 worktree 里磁盘注入、逐字节恢复）：转移关闭、冷却关闭、本机优先排序、熔断按候选计失败、调用方错误计熔断、不记实际服务模型、对话唯一索引丢部署位置、身份不含类型、探测快照时机、强刷 `>=`、状态页不看调用记录、结构化读超时转移、OCR / 对话报错不提冷却、启用提示不看服务器、G9 占位串当正文、调用点字符串 messages、OCR 不排序 / 失败不换候选、流式已输出仍转移、服务器不可达也带提示启用、本机判定放宽、R197 不先停本机行（pg）、J2 去鉴权、输出超限转移；前端兜底判定按对象引用、不补未启用端、路由状态总带 refresh。每条都以预期用例打红。

真实环境（本机 vLLM 8100 在线 + 企业网关）：经管理接口启用 paddleocrv6 / paddleocrvl-1.6（真实连接测试通过）、本机 paddleocr（引擎未装 ⇒ 带提示启用）、本机对话 Qwen3.5。经平台运行时真实调用：对话由本机回答；合成不可达本机候选（127.0.0.1:9）+ 库内 qwen3.8 ⇒ 2.8 秒内由服务器回答、本机进入冷却、attempts 写明「连接被拒绝（端口未监听）」；结构化输出由本机回答（guided_json）；OCR 文字识别本机引擎缺失 ⇒ paddleocrv6 识别出「GT OCR 2026」；版面解析 ⇒ paddleocrvl-1.6。Playwright：面板四行状态正确，停用本机对话行（确认框写明由 qwen3.8 承担）⇒ 当前生效变服务器，再启用 ⇒ 回本机；OCR 页签标签与部署列正确；「检测状态」刷新时间更新。向量行如实显示不可用（8100 无 `/embeddings`），未改数据。

未做 / 外部：未重启 start-dev（共享环境有其他会话在用）；V197 由 `MigrationRunner.run_pending()` 落库，与启动同一代码路径。
