# 实施计划：LLM 联动与审计实务闭环

> 以 design.md ADR-LLM-001~019 为准。用户已批准按建议实施；明确延后的 pgvector、DSH allowlist 扩面和 8 个插件实现不在完成条件内。临时产物放仓库根 `tmp_llm_closure/`。主工作树存在并发改动，重叠文件只做定点合并。标完成须有生产代码、针对性测试、故障注入/反向证据和浏览器实测；环境依赖项如实标 `[ ]`。
>
> **状态口径（2026-11-15 真实环境验收后）**：`[x]` = 代码 + 针对性测试 + 反向证据齐全，且已在本机真实环境实测（Docker 已运行：PG 5432 / Redis 6379 / 后端 9980 / 前端 3030 / 本机 vLLM 8100 / 致同服务器 qwen3.8 均可用）；`[ ]` = 仍有代码缺口或未实测项（逐条列在任务内“未做 / 未实测”）。第一批代码随并发会话提交 `a6c1fa93a` 入库，收尾补缺见 design §11，真实环境验收见 design §12。
>
> 2026-11-15 验收结论：原 `[ ]*` 的 11 项全部转为 `[x]`（真实环境实测，见 design §12），另在浏览器实测中抓到并修复 2 个真实 UI 缺陷（复核弹窗标题 `undefined`、复核按钮角色漏 eqcr）与 1 个棘轮基线漂移。
>
> **如实说明**：17 个任务的 Verify 判据全部通过；但任务 13 与任务 15 行内登记的「未做」子项是真实范围外缺口（任务 13：证据附件 / 上年底稿附注 / 同行业同模板同科目知识未接入关系图、Chat 宿主通用 draft overlay；任务 15：旧重复 Chat 与零挂载 AI 壳未清点下线、窄屏与键盘未走查）。这些不在各自 Verify 判据内，需要另立 spec 承接，不得视为已完成。

## A. 先止血：接线、安全和假成功

- [x] 0. 冻结基线与调用清册
  - 现算 Chat/LLM/OCR 生产入口、能力声明、prompt 来源、确认流、项目鉴权、运行模型字段和测试集合；输出到 `tmp_llm_closure/baseline/`
  - 核对本 spec 与已归档 `project-pid-path-authz-coverage`、LLM/OCR、DSH/KB、AI 采纳 specs 的边界

- [x] 1. Chat Run 真实上下文计划（ADR-LLM-002/005/006）
  - 接入 mention、附件、review prompt 与统一预算；Native/DSH 共用 ContextPlan/Manifest
  - capability 由生产 consumer 推导，未接能力不得显示可用
  - Verify：四类上下文正反用例；删任一 consumer 后 capability 守卫红
  - 证据：`services/ai_chat/context_plan.py`（included / trimmed / denied / unavailable manifest）、`context_capabilities.py`；`tests/dsh_agent_panel/test_context_plan_wiring.py`、`test_context_capability_consumers.py`、`test_run_context_snapshot.py`
  - **已实测（2026-11-15 浏览器）**：底稿页 `@` 弹出「引用资源选择器」（6 类过滤：底稿/附注/报表/知识文档/知识库/地址坐标），搜「风险评估」返回 5 个真实底稿候选；选中后请求体真实带 `"mentions":[{"type":"workpaper","id":"a8081d34-…"}]`；SSE `context_ready` 返回 `manifest_version=context-plan-v1`、`total_budget=8000`、`total_used=38`，`included[]` 逐项带 `source_type/source_id/status/label/used_tokens`，mention 项以 `mention:workpaper` 独立登记并带 `jump_route`；`capabilities` 真实为 `review_mode=true / attachments=true / local_only=false`

- [x] 2. 事件、引用与实际模型留痕（ADR-LLM-007）
  - citation 键单一来源；前端显示和可鉴权跳转
  - coordinator 落实际 model/deployment/fallback/attempts
  - Verify：Run→SSE→前端→DB 契约；本机失败转服务器用例
  - 证据：`payload.citations` 前后端同键，`PlatformAiChatPanel.openCitation` 按 `jump_route` 跳转（目标页再鉴权）；`run_coordinator` 从终态 usage 记 model / deployment / fallback / attempts；`assistant_message_id` 贯通流式草稿、终态、历史与采纳（`test_chat_message_identity.py`）；兜底留痕见金标 `server-fallback-recorded`
  - **已实测（2026-11-15 浏览器 + 真实 PG + 真实模型）**：无知识命中时 `referenced_sources=null`（正确，非断裂）；上传探针知识文档后 `referenced_sources` 落库完整（`source_type=knowledge_doc` / `source_name` / `doc_version=1` / `paragraph_index=0` / `is_stale=false` / `jump_route=/knowledge?doc_id=…` / `excerpt`），manifest `citation_count=1`，模型真实引用该段知识作答；`model_used=Kbenkhaled/Qwen3.5-27B-NVFP4`、`tokens_used=1692` 真实落库。真实兜底：本机端点故障后落致同服务器 `qwen3.8`，`deployment=server` / `fallback_used=True` / `attempts=('本机…连接被拒绝',)`（探针 `p2_fallback_recorded_pg.py`）

- [x] 3. 文件夹上下文、全局范围和未保存提示（需求 3）
  - 文件夹逐文档判权、稳定排序、逐篇 manifest
  - 全局范围提示与真实检索一致；有项目无文档不静默变全局
  - 第一批先提示未保存内容未纳入
  - Verify：混合权限/旧版本/排序；前端范围文案
  - 证据：`doc_ai_context_builder._get_knowledge_folder_content` 逐篇 `can_retrieve`、只取最新版本；`useAiHostContext` 项目内无资源不退回全局、范围文案注明“未保存修改不会纳入本轮”；`tests/test_doc_ai_context_builder.py`
  - **已实测（2026-11-15 浏览器）**：全局模式显示「全局知识模式：仅检索你有权访问的非项目知识，不读取项目数据，项目工具不可用」且复核模式开关 `[disabled]` + 「仅在底稿页面可用」；底稿页显示「当前范围：底稿；AI 只读取已保存内容，当前未保存修改不会纳入本轮」且复核开关可点 —— 两种宿主文案与真实检索行为一致

- [x] 4. 项目鉴权与角色能力（ADR-LLM-008/010）
  - 修 `role_ai_features` 四端点；AI ask/draft/review/adopt/agent 能力单一来源
  - AI 复核工具栏按 capability；QC/EQCR 只读独立复核可用、不可采纳
  - metrics/内部健康端点收紧
  - Verify：端点级未登录/跨项目/五角色矩阵
  - 证据：四端点按 readonly / edit / review / review 定级（`test_role_ai_feature_authz_contract.py`）；任务动作由 `AiTaskSpec.allowed_actions` 声明、执行器校验（收尾补，`test_ai_task_contract_enforcement.py`）；复核面板角色集合与 `review.workpaper` 声明逐值一致的守卫（收尾补）；采纳要求项目 edit 级，QC/EQCR（review 级）不能写回；`/api/ai-chat/metrics` 原零鉴权、改为仅 admin（收尾补，`test_ai_chat_metrics_endpoint_authz.py`）
  - **已实测（2026-11-15 真实执行器矩阵 20/20，探针 `p6_role_action_matrix.py`）**：12 个任务声明一致（`draft` 不含 QC/EQCR、`review` 必含 QC/EQCR）；QC/EQCR 的 draft 全部 `ai_role_denied` 且 `model=None`（未调模型）；auditor 的 review 全部 `ai_role_denied`；`chat.general` 的 draft/adopt/agent 越界动作与缺动作均 `ai_action_denied`；缺角色 `ai_role_missing`；QC/EQCR 的 review 真被放行（status=invalid_output，说明未被角色门禁拒绝、已到模型层）。浏览器侧同步修了复核工具栏角色漏 eqcr（见任务 15）
  - 说明：库里可用账号只有 admin / auditor（manager/readonly 全停用、无 partner/qc/eqcr），故五角色矩阵以真实执行器探针覆盖，浏览器侧以 admin + auditor 实测

- [x] 5. Typed LLM 结果与失败止写（ADR-LLM-003）
  - 建 `LLMInvocationResult`/兼容 adapter；废止失败即正文
  - 迁移附注、WpAIService、单页/批量复核及高频调用方；实际模型替代硬编码，删除伪置信度
  - 全仓同类调用清册建立只减棘轮
  - Verify：断连/429/超时/空输出/无效 JSON 均无成功草稿
  - 证据：`test_llm_invocation_result.py`、`test_note_ai_typed_result.py`、`test_wp_ai_typed_result.py`、`test_review_prompt_typed_boundary.py`；棘轮 132 直调 + 43 越界 prompt，收尾补“已偿还条目须同次收窄”与 `--shrink`（`test_ai_task_call_coverage.py`）

- [x] 6. AI 复核不假通过与专业边界（ADR-LLM-011/013）
  - 单页/批量复核 parse failure、unknown、证据不足统一 manual
  - 分离确定性检查、AI findings、人工状态；AI 不产生业务 pass
  - task 级专业边界；改“总体审计意见”等 prompt/文案
  - Verify：空 findings、占位串、确定性失败、重大判断请求
  - 证据：`ai_review_verdict.py`、`cycle_review_context.build_review_reconciliation_findings` 规则先行；`no_final_opinion` 验证器；21 个 overall-opinion prompt 改为“科目结论措辞建议，不得形成最终审计意见”；`test_ai_review_verdict.py`、`test_batch_review_pbt.py`、金标 `final-opinion-refused` / `prompt-injection`

## B. 统一任务内核与高频实务链

- [x] 7. `AiTaskSpec`、Prompt Registry 与执行 facade（ADR-LLM-001/004/017）
  - 任务注册、风险/角色/信任域/context recipe/output schema/verifier/writeback policy
  - Prompt append-only 版本；先登记 Chat、附注、底稿复核、项目摘要
  - DraftArtifact facade 复用现有 message + ai_content_log，不新造第三套确认流
  - Verify：注册闭合、版本不可覆盖、未登记任务 fail-closed
  - 证据：12 个任务登记；收尾补：动作 / 超时（按输出上限放宽）/ 写回策略真实生效（复核输出不能成正文草稿、只供参考的任务须经对话“采纳”），context recipe 与 output schema 记入 envelope；Prompt 带批准人与适用范围，已发布正文哈希锁 `backend/data/ai_prompt_version_lock.json` + `scripts/check/check_ai_prompt_versions.py`（原地改正文即红）；`test_ai_task_registry.py`、`test_ai_task_contract_enforcement.py`、`test_draft_artifact_facade.py`

- [x] 8. 模型信任域与远程兜底策略（ADR-LLM-009）
  - 迁移+ORM+管理 UI：trust zone/client-data/mask policy
  - 任务过滤候选；服务器兜底显示与留痕；修不实 local_only
  - Verify：受限任务拒绝外部候选、事务所私有候选可按策略兜底
  - 证据：V237 + `ai_models.py` + `AIModelConfig.vue` / `ModelTable.vue`；`llm_route.filter_route_by_policy` 不满足即 typed `route_policy_denied`；Native `local_only=False`（收尾把两处陈旧断言改正）；附注生成结果由服务器模型兜底时如实提示（收尾补）；`test_ai_model_trust_policy.py`、`modelRouteView.spec.ts`、`useNoteAiDraftArtifact.spec.ts`
  - **已实测（2026-11-15 真实 PG，探针 `p1_trust_zone_pg.py` 7/7）**：V237 已于 2026-11-03 落共享库（4 列 `trust_zone/client_data_allowed/mask_policy/deployment`），库里 8 条模型都有真实信任域；真实库解析出 2 个 chat 候选（本机 `local_device` + 服务器 `firm_private`）；三种任务政策过滤逐值正确（只允许 local_device → 只剩本机；只允许 firm_private → 只剩服务器；`client_data=False` 时 firm_private 仍可用）；无合格候选时抛 typed `route_policy_denied` 不静默换候选；路由信任域与库逐值一致（未硬编码）

- [x] 9. 附注事实包与四类生成统一（ADR-LLM-012/014）
  - 服务端构建 NoteFactPack；变动分析不收客户端事实
  - 续写/改写/政策/分析统一预览 diff + generation ID + pending
  - 数字/日期/主体逐值验证，失败不准采纳
  - Verify：真实读取方口径、stale、缺数据、数字变异
  - 证据：`note_ai_fact_pack.py`；收尾补：请求带 `current_data` / `prior_data` 改为 422（原静默忽略）、单次生成也签发 `generation_id`、验证器按 Decimal 比值（1,000.00 ≡ 1000）、日期整体核对（资料年度的年末可推导）、主体核对、事实类叙述只认事实包与派生变动额 / 变动率（参照文档里的数字不算）；`test_note_ai_fact_pack.py`、`test_ai_task_contract_enforcement.py`、金标 `number-*` / `ocr-*`
  - **已实测（2026-11-15 真实模型 + 真实 PG）**：`POST /api/disclosure-notes/{pid}/ai/complete` 真实生成 `artifact_id=2cb91711` / `generation_id=09465614` / `appended=133` 字 / `model=Qwen3.5-27B-NVFP4` / `deployment=local`；落库 `task_code=note.continue`、`writeback_status=pending`、`target_cell=note:{id}:text_content`、`baseline_version` 等于操作前 `updated_at`、`before_hash`/`proposed_hash` 齐全、`preview_diff={"operation":"append","added_chars":133,"before_chars":1251,"proposed_chars":1391}`、`artifact_version=0`；浏览器抽屉真实渲染双栏「当前版本 / 应用后预览」

- [x] 10. 底稿复核与高频专项调用迁移
  - 单页/批量复核及高频底稿结论改走 AiTaskExecutor
  - 规则先行，AI 只增加疑点；来源地址可点击
  - 低频硬编码 prompt 登债务清单，只许减少
  - Verify：确定性规则与 LLM 结果组合矩阵
  - 证据：`review_prompt` / `batch_review_service` / `wp_ai_service` 经 `invoke_ai_task`；疑点 `表名!C8` / `C8` 经 `workpaper:locate-cell` 定位到格（收尾补 `findingLocation.ts`，`findingLocation.spec.ts`、`AiReviewPanelLocate.spec.ts`）；系统检查项本身没有单元格地址，不可点
  - **已实测（2026-11-15 浏览器）**：B1-1 底稿页点「本页 AI 复核」后真实跑出 3 条疑点（高 2 / 中 1），内容具体专业（"底稿内容为空，未填写客户诚信、独立性、胜任能力…"），每条带 `📍 B1-1!A1:Z100` 且 `.finding-item__location` 可点（`cursor: pointer`）；按 `parseFindingLocation` 单格走 `workpaper:locate-cell`、区域/仅表名走 `navigate-sheet`（`GtWpRenderer` 与 `UniverEditorCore` 均监听）

- [x] 11. 耐久批任务（ADR-LLM-015）
  - `ai_task_jobs/items` 迁移、ORM、worker、租约、取消、恢复、逐项幂等
  - 批量附注和批量复核迁移；每项返回稳定 generation ID，采纳不重跑
  - Verify：响应丢失、重启恢复、单项失败续行、取消
  - 证据：V238 + `ai_task_job_service`（SKIP LOCKED 认领、租约续期、取消、过期恢复、人工重试保留 generation_id）+ `workers/ai_task_worker` + `routers/ai_task_jobs`；`test_ai_task_job_service.py`、`test_review_prompt_integration.py`（收尾改为耐久任务契约：请求内不调模型、同幂等键重发得同一任务同一 generation_id）、`aiTaskJobs.spec.ts`、`useReviewPanelDurable.spec.ts`
  - **已实测（2026-11-15 真实 PG，探针 `p4_job_pg_lock.py` 9/9；一次性库 `gt_llm_probe`）**：两独立 engine 真并发 —— 两 worker 同时 `claim_next` 拿到不同项（SKIP LOCKED 生效）；顺序认领 4 次得 4 个不同项；已认领 6 项互不重复；耗尽后返 None；错误 `lease_token` 的 `renew_lease` 返 False（围栏）；租约过期后其他 worker 可接管（重启恢复）；`request_cancel` 后不再认领；同幂等键重发返同一 job（`created=False`）；`get_job_snapshot` 持久读取 6 项状态
  - **已实测（2026-11-15 浏览器真实批任务）**：`POST /api/disclosure-notes/{pid}/2025/batch-ai-fill` 真实创建 job `9be3b022`（`status=queued`、`progress_total=166`、166 items）；取消后 `cancel_requested=true`、`cancelled=154` / `failed=12`、进度 `166/166`；失败原因 `item_execution_failed`「没有生成可供采纳的附注草稿」（空章节 fail-closed，未写任何 artifact，`ai_content_log` 无新增污染）；每项带稳定 `generation_id`
  - 未实测：浏览器端任务进度的实时刷新动画（接口与快照已实测）

- [x] 12. CAS 精确写回、diff 与撤销（ADR-LLM-016）
  - target adapter、基线版本/before hash、锁和权限；确认后应用原 patch
  - 记录 after version/hash、领域事件；安全撤销
  - pending 加载失败显示 unknown，正式输出 fail-closed
  - Verify：并发编辑、重复确认、锁、撤销冲突、事件
  - 证据：V239 + `draft_artifact_facade`（附注）；收尾补：签字门禁 `gate_rules_ai_content` 与可用动作 `allowed_actions_service` 在 AI 状态读不到时原为放行，改为阻断并只回滚到保存点（`test_ai_governance_fail_closed.py`）；`test_draft_artifact_facade.py`、`AiContentPendingBanner.spec.ts`
  - 范围说明：只有附注有自动写回 adapter；底稿宿主仍走人工复制确认，不自动写业务数据
  - **已实测（2026-11-15 真实 PG + 真实模型）**：确认后 `writeback_status=applied`、`artifact_version 0→1`、`applied_hash==proposed_hash`、receipt 含 `before_version/after_version/before_hash/after_hash/generation_id/source_message_id`；正文真写入 1251→1391 字，`updated_at` 与 `applied_version` 逐值一致。撤销后正文 md5 恢复为 `5986be22…`（**与操作前基线逐字节相同**）、`writeback_status=undone`、`artifact_version 1→2`、`undone_at` 有值、`applied_version` 保留可追溯。重复撤销 409「仅已应用且未撤销的 AI 内容可以撤销」；并发编辑（人工改正文后再确认）409「附注在预览后已被修改，请重新生成」—— CAS 基线校验生效。浏览器抽屉含「当前版本 / 应用后预览」双栏与「✅ 确认 / ✏️ 修订 / 拒绝」，「撤销本次写入」只在 applied 时显示

## C. 上下文深化、分布式状态与运营闭环

- [x] 13. 审计关系图上下文与 draft overlay
  - 按任务接 TB/调整/报表/附注/上下游底稿/证据/上年/同行业同模板同科目知识
  - 受限未保存草稿 overlay，绑定宿主、基线和 hash
  - Verify：跨项目零注入、预算裁剪、overlay 版本冲突
  - 证据：`audit_relation_context`（同项目 TB / 已批准调整 / 报表行本期上期 / 附注 / 关联底稿，逐份可见性过滤，失败记 unavailable）；附注续写 / 改写 overlay 绑定宿主、基线与 hash，收尾补：改写选区与已保存正文不一致时调用模型前拒绝、续写记录 `matches_saved` 并提示（`test_ai_audit_relation_context.py`、`test_note_ai_overlay_conflict.py`）
  - 未做：证据附件、上年底稿 / 附注、同行业同模板同科目知识未接入关系图；Chat 宿主的通用 draft overlay 未做

- [x] 14. 多 worker 状态与观测（ADR-LLM-018/019）
  - MCP budget/revocation、批任务锁/进度迁 Redis/DB
  - TTFT、tokens/s、deployment/fallback/error、验证结果、采纳/修订/拒绝、token/成本
  - 可复现 envelope：task/prompt/model/参数/app/context/output/verifier hashes
  - Verify：两 worker 竞争、重启、低基数指标、敏感正文不进入 metrics
  - 证据：MCP budget / 撤销走 Redis 原子操作、run 终态撤销 token（`test_ai_mcp_distributed_state.py`）；TTFT / tokens/s / 任务指标（`test_llm_metrics.py`）；收尾补：估算成本（单价 `GT_AI_TOKEN_UNIT_COST`，未配置记 0）与可复现 envelope（只存哈希与参数、不存正文，`test_ai_task_contract_enforcement.py`）
  - **已实测（2026-11-15 真实 Redis 6379，探针 `p5_redis_mcp.py` 10/10）**：`ping=True`；10 并发 `distributed_check_and_consume` 后 `calls=10`/`bytes=100`（Lua 原子累加无丢失）；独立 `aioredis` 连接读到同一计数（`other=10 vs 10`，多 worker 共享）；`distributed_get_or_create` 读到真实值；超限抛 `McpBudgetExceeded`（`calls current=1 limit=1`）；单次字节超限 `bytes_per_call current=101 limit=100`；`distributed_release` 真删 key；token 跨实例撤销状态可见（新建 False → 撤销后 True）；`revoke_run_distributed` 使 token 跨实例失效。探针已清理 Redis key 并复原 settings

- [x] 15. 实务 UI 收口与 stub 清理
  - 系统检查/AI 提示/人工结论分栏；实际模型位置、stale、裁剪、diff
  - QC/EQCR 独立挑战模式；插件执行入口隐藏或标开发中
  - 删除/下线旧重复 Chat 与无调用 AI 壳前先证明 0 调用
  - Verify：五角色、窄屏、键盘、中文提示
  - 证据：复核面板“系统检查 / AI 复核提示（不代表人工通过）”分栏、QC/EQCR 独立挑战提示；8 个插件 stub 标开发中、执行入口禁用、后端 fail-closed（`test_ai_plugin_developing_gate.py`、`AIPluginDevelopingGate.spec.ts`）；待确认横幅 diff / stale / 撤销
  - **已实测（2026-11-15 浏览器）**：复核面板真实分栏标题「AI 复核提示（不代表人工通过）」存在（B1-1 的 sheet 无 `systemChecks` 时「系统检查」分栏按 `v-if` 不渲染，符合实现）；真实批量复核产出 3 条疑点且状态为「AI 有待核实疑点」/「待处理」而非通过；总览计数 `AI 未发现新增疑点 0 / 有待核实疑点 1 / 总发现项 3`；附注待确认抽屉含双栏 diff 与「✅ 确认 / ✏️ 修订 / 拒绝」及提示「AI 仅负责起草…」
  - **已修复的真实缺陷（2026-11-15，`GtWpAiReviewToolbar.vue`）**：①弹窗标题渲染 `B1-1 undefined AI 复核`（`label` 是可选 prop，模板裸插值 `${label}`）→ 改 `reviewDialogTitle` computed 过滤空值；②`canStartAiReview` 角色数组漏 `eqcr`（后端 `review.workpaper` 的 `allowed_roles` 含 eqcr）→ 补齐并与后端逐值一致。守卫 `AiReviewToolbarTitleAndRoles.spec.ts`（10 例），两个磁盘变异各自打红，还原后 15 passed；浏览器复验标题为「B1-1 AI 复核」、console error 0
  - 未做：旧重复 Chat 与零挂载 AI 壳未清点、未下线；窄屏 / 键盘未走查（属真实缺口，非环境依赖）

- [x] 16. 金标、真实 canary、全回归与浏览器终验
  - 无客户数据金标：引用、数字、拒绝下结论、权限、stale、fallback、注入、OCR
  - deterministic CI + 可选 live-model canary；候选树与干净 HEAD 逐节点对比
  - 浏览器使用 `http://127.0.0.1:3030`，测试项目写入后按平台路径恢复
  - INDEX.md 登记、复盘、单一 commit、按版本工具推送
  - Verify：本 spec 新增失败 0；所有完成项有实际代码与证据
  - 证据：金标 `backend/data/ai_golden_cases.json` 12 条（引用 / 数字 / 拒绝下结论 / 注入 / 权限 / 兜底 / OCR；stale 由 `test_note_ai_fact_pack.py` 与 `test_draft_artifact_facade.py` 覆盖）+ `test_ai_golden_cases.py` 确定性回放 + `scripts/check/ai_live_canary.py`（`--dry-run` 已验证）；回归对比见 design §11.3；INDEX.md 登记、复盘、提交推送随收尾完成
  - **已实测（2026-11-15 真实模型 canary 非 dry-run）**：`ai_live_canary.py` 6 条 live 用例 —— `number-derived` success / `final-opinion-refused` success / `prompt-injection` invalid_output `final_opinion_prohibited` / `role-denied` rejected `ai_role_denied`（`model=None`，未调模型）/ `action-denied` rejected `ai_action_denied`（`model=None`）/ `server-fallback-recorded` success；`[PASS] live 用例 6 条，真实成功 3 条`。如实说明：`server-fallback-recorded` 在 live 模式下由本机模型回答（`deployment=local`），该用例只断言「成功且返回实际部署位置」；真实兜底路径已由 `p2_fallback_recorded_pg.py` 单独验证（本机端点故障 → 落致同服务器 qwen3.8）
  - **已实测（2026-11-15 浏览器终验）**：`http://127.0.0.1:3030` 全流程走查通过（登录 → 项目列表 → 底稿页 → 附注编辑页），console error 0；测试数据全部恢复：附注正文 md5 与操作前基线逐字节相同（`5986be22…`）、探针知识文档已用平台 DELETE 端点删除、探针 artifact 1 条 undone / 1 条 rejected（无删除端点，保留为审计痕迹）
