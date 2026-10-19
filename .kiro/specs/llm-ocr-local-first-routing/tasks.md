# LLM / OCR 本机优先路由收口 — Tasks

> 进度（2026-10-20）：14/14。证据与偏差见 design §9。干净 worktree（HEAD + 只含本次改动）回归：本次 22 个测试文件 416+ passed；按改动模块筛出的 106 个测试文件 46 failed 与干净 HEAD 的失败集合逐条相同（预存，非本次引入）。

- [x] 1. 迁移 V197 / R197 与 ORM
  - `deployment` 列回填 + CHECK + 三条按部署位置的唯一索引；R197 回到单启用语义
  - ORM 与 `AIDeployment` 枚举同步；`classify_deployment()` / `endpoint_is_loopback()`（放在 `models/ai_model_options.py`）
  - 证据：V197 经 MigrationRunner 落本地库（executed=['197']，failed=[]）；`test_v197_route_migration_pg`（临时 schema，R197 → V197 往返：双启用时先停本机行再恢复旧索引、回填与运行时分类逐行一致、新索引语义、CHECK）；SQLite 索引语义参数化用例；变异 M07 / M22 / M23 打红
  - _需求：R1.1 R1.2 R7.1_

- [x] 2. 运行时错误分类与候选解析（llm_runtime）
  - `LLMRuntimeError.kind` / `failover`；连接超时与读取超时分开；JSON 解析失败归 `invalid_response`
  - `ResolvedLLMConfig.deployment` / `identity`；本机连接超时收紧
  - `RouteCandidate` / `resolve_route()` / `order_candidates()`；`resolve_runtime_config()` 取首个可用
  - 证据：状态码 / 传输错误分类参数化用例；身份含模型类型（实施中发现对话与向量同名同端点互相污染）；变异 M01 / M03 / M08 / M25 打红
  - _需求：R1.1 R1.3 R1.4 R2.1 R2.2 R3.1_

- [x] 3. 路由执行与冷却（新 llm_route）
  - `route_chat_sync` / `route_chat_stream`：转移规则、流式首片段前才转移、冷却计划、全部失败逐个列原因
  - 路由结果 ContextVar、`last_route_outcome()`、`served_model_label()`
  - 证据：路由执行 / 流式 / 冷却 / 报错用例；报错与 attempts 列出冷却跳过的候选（`cooling_notes`）；变异 M02 / M06 / M14 / M20 打红
  - _需求：R2.1~R2.5 R5.2_

- [x] 4. llm_client 与 AIService 接入路由
  - llm_client：走路由、熔断按路由身份、参数错误不计熔断
  - AIService：chat 走路由；`get_active_model` 按路由顺序；embedding 保持单条
  - 证据：熔断用例（spy 断言兜底成功时从未记失败）；既有 health / get_active_model 用例按新语义改写通过；变异 M04 / M05 打红
  - _需求：R2.6 R3.1 R7.3_

- [x] 5. 启用 / 停用 / 删除 / 改端点规则
  - `switch_model` 按部署位置替换；本机仅 `unavailable` 带提示启用；`disable_model`
  - 路由：activate 返回 `deployment` + `warning`；新增 deactivate；删除与改端点冲突规则；DTO 增加 `deployment`
  - 证据：`test_ai_model_route_admin`（真实校验链 + MockTransport）；提示按有无服务器模型 / 向量如实说明；变异 M15 / M21 打红
  - _需求：R4.1~R4.5_

- [x] 6. OCR 本机优先
  - `resolve_ocr_route()`；`UnifiedOCRService.recognize` 本机优先 + 服务器兜底 + 原因汇总 + `route` 元数据
  - MinerU 可达、Tesseract 程序检查、`local_engine_status()`；本机 OCR 行校验改查引擎链
  - 证据：`test_ocr_local_first_routing`（11 例）、MinerU / tesseract 程序检查用例；变异 M13 / M18 / M19 打红；真实识别见 13
  - _需求：R1.1 R1.3 R2.1 R5.3_

- [x] 7. 路由状态与健康
  - `model_route_status`：探测 + 缓存 + 冷却叠加；`GET /api/ai-models/routes`
  - `AIService.health_check` 派生自状态（兼容字段 + `routes`）；公共 `/api/ai/health` 去端点
  - 证据：缓存 / 强刷 / 并发合并 / 探测联动冷却 / 调用记录覆盖缓存 / 公共健康只探对话无端点；实施中修 Windows 时钟精度致强刷失效（改探测次数 + 请求入口快照）；变异 M09 / M10 / M11 打红
  - _需求：R3.2 R6.1 R6.3_

- [x] 8. 绕开调用点收口
  - structured_llm_service 按候选建客户端 + 转移，guided_json 只发本机
  - LLMService 走路由；J2 改用统一入口并补登录鉴权
  - role_ai_features ×2、workhour_service、work_hour_nlp 参数修正；wp_explanation_service / wp_guidance_chat 去掉强制模型名
  - 证据：结构化输出转移口径参数化用例（与对话同口径）；`test_j2_ai_generate_route`；全仓 `test_chat_completion_call_contract`（按作用域解析变量），另查出并修复 G8 / G9 / report_trace 三处；变异 M12 / M16 / M17 / M24 打红
  - _需求：R5.1 R5.4_

- [x] 9. 记录实际服务模型
  - native_engine 模型接缝原样抽到 `native_model_client.py`（行数门禁），对话消息记实际模型；守卫扫描范围同步
  - wp_ai_service、batch_review_service、a17、b14、wp_explanation_service 改用 `served_model_label()`
  - 证据：native_engine 812 → 766 行；守卫扩展放在新文件 `test_native_model_client_guard.py`（`test_task6_native_engine.py` 在 HEAD 已 1691 行且未登记行数白名单，不再加行）；变异 M06 打红
  - _需求：R5.2_

- [x] 10. 前端
  - `aiModelApi.ts` 类型与 `deactivateAIModel` / `getAIRoutes`；`apiPaths/system.ts`
  - 模型配置页「调用路由」面板；表格部署列、启用 / 停用、启用提示
  - 证据：`ModelRoutePanel.vue` + 纯函数 `modelRouteView.ts`；Playwright 实测见 13
  - _需求：R6.2 R6.4_

- [x] 11. 后端测试与变异证明
  - 路由、冷却、熔断、启用规则、OCR 路由、状态、调用点修正；既有测试按新语义更新（不放宽判据）
  - 变异：转移 / 冷却 / 排序 / 熔断聚合 / ContextVar / 唯一索引条件逐条打红并逐字节恢复
  - 证据：后端 25 条 + 前端 3 条变异全部以预期用例打红（design §9 列表）；G8 / G9 原「接受 500」的假绿断言改为真实断言
  - _需求：全部_

- [x] 12. 前端测试
  - aiModelApi 新接口路径与 `_silent`；页面逻辑单测；ESLint / 单区域 tsc
  - 证据：vitest 2 文件 13 passed；ESLint 0；`tsconfig._llm-route.json` 单区域 vue-tsc 0 错，3 个文件注入 TS2322 均命中并逐字节恢复（全量 vue-tsc 本仓 OOM，既有限制）
  - _需求：R6.2_

- [x] 13. 真实环境验收
  - start-dev 重启跑 V197；本机 vLLM 在线时对话走本机；合成不可达本机候选证明转移到 qwen3.8（不停用户服务、不改库）
  - 启用本机对话行与 OCR 两槽服务器行（管理接口，真实校验）；OCR / 版面解析真实识别；Playwright 看面板与启用 / 停用
  - 证据：见 design §9「真实环境」。未重启 start-dev（共享环境，其他会话在用）；V197 以与启动同一路径的 `MigrationRunner.run_pending()` 落库
  - _需求：R1 R2 R4 R6_

- [x] 14. 文档、INDEX、memory 收尾与本地提交（不推送）
  - `docs/reference/llm-provider-configuration.md` 路由章节；INDEX 登记；临时文件清理；干净检出验证后提交
  - 证据：参考文档补「本机优先路由」章节、管理 API 表与故障排查；`.env.example` 登记两项新配置；INDEX / memory 只提交本 spec 的块（共享文件里其他会话的改动不带入）；提交前在「要提交的那棵树」的干净检出里复跑本 spec 测试与守卫
