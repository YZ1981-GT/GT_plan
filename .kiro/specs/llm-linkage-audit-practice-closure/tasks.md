# 实施计划：LLM 联动与审计实务闭环

> 以 design.md ADR-LLM-001~019 为准。用户已批准按建议实施；明确延后的 pgvector、DSH allowlist 扩面和 8 个插件实现不在完成条件内。临时产物放仓库根 `tmp_llm_closure/`。主工作树存在并发改动，重叠文件只做定点合并。标完成须有生产代码、针对性测试、故障注入/反向证据和浏览器实测；环境依赖项如实标 `[ ]*`。
>
> **状态口径（2026-11-01 收尾）**：`[x]` = 代码 + 针对性测试 + 反向证据齐全且不涉及界面；`[ ]*` = 代码已改、单测通过，**浏览器或真实 PG / Redis / 模型未实测**（本机 5432 / 6379 / 9980 / 3030 均不可达、Docker 未运行）；`[ ]` = 仍有代码缺口（逐条列在“未做”）。第一批代码随并发会话提交 `a6c1fa93a` 入库，收尾补缺见 design §11。

## A. 先止血：接线、安全和假成功

- [x] 0. 冻结基线与调用清册
  - 现算 Chat/LLM/OCR 生产入口、能力声明、prompt 来源、确认流、项目鉴权、运行模型字段和测试集合；输出到 `tmp_llm_closure/baseline/`
  - 核对本 spec 与已归档 `project-pid-path-authz-coverage`、LLM/OCR、DSH/KB、AI 采纳 specs 的边界

- [ ]* 1. Chat Run 真实上下文计划（ADR-LLM-002/005/006）
  - 接入 mention、附件、review prompt 与统一预算；Native/DSH 共用 ContextPlan/Manifest
  - capability 由生产 consumer 推导，未接能力不得显示可用
  - Verify：四类上下文正反用例；删任一 consumer 后 capability 守卫红
  - 证据：`services/ai_chat/context_plan.py`（included / trimmed / denied / unavailable manifest）、`context_capabilities.py`；`tests/dsh_agent_panel/test_context_plan_wiring.py`、`test_context_capability_consumers.py`、`test_run_context_snapshot.py`
  - 未实测：浏览器里 mention / 附件 / 复核提示词进入 manifest

- [ ]* 2. 事件、引用与实际模型留痕（ADR-LLM-007）
  - citation 键单一来源；前端显示和可鉴权跳转
  - coordinator 落实际 model/deployment/fallback/attempts
  - Verify：Run→SSE→前端→DB 契约；本机失败转服务器用例
  - 证据：`payload.citations` 前后端同键，`PlatformAiChatPanel.openCitation` 按 `jump_route` 跳转（目标页再鉴权）；`run_coordinator` 从终态 usage 记 model / deployment / fallback / attempts；`assistant_message_id` 贯通流式草稿、终态、历史与采纳（`test_chat_message_identity.py`）；兜底留痕见金标 `server-fallback-recorded`
  - 未实测：浏览器点击引用跳转、真实本机→服务器兜底

- [ ]* 3. 文件夹上下文、全局范围和未保存提示（需求 3）
  - 文件夹逐文档判权、稳定排序、逐篇 manifest
  - 全局范围提示与真实检索一致；有项目无文档不静默变全局
  - 第一批先提示未保存内容未纳入
  - Verify：混合权限/旧版本/排序；前端范围文案
  - 证据：`doc_ai_context_builder._get_knowledge_folder_content` 逐篇 `can_retrieve`、只取最新版本；`useAiHostContext` 项目内无资源不退回全局、范围文案注明“未保存修改不会纳入本轮”；`tests/test_doc_ai_context_builder.py`
  - 未实测：浏览器范围文案

- [ ]* 4. 项目鉴权与角色能力（ADR-LLM-008/010）
  - 修 `role_ai_features` 四端点；AI ask/draft/review/adopt/agent 能力单一来源
  - AI 复核工具栏按 capability；QC/EQCR 只读独立复核可用、不可采纳
  - metrics/内部健康端点收紧
  - Verify：端点级未登录/跨项目/五角色矩阵
  - 证据：四端点按 readonly / edit / review / review 定级（`test_role_ai_feature_authz_contract.py`）；任务动作由 `AiTaskSpec.allowed_actions` 声明、执行器校验（收尾补，`test_ai_task_contract_enforcement.py`）；复核面板角色集合与 `review.workpaper` 声明逐值一致的守卫（收尾补）；采纳要求项目 edit 级，QC/EQCR（review 级）不能写回；`/api/ai-chat/metrics` 原零鉴权、改为仅 admin（收尾补，`test_ai_chat_metrics_endpoint_authz.py`）
  - 未实测：浏览器五角色矩阵

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

- [ ]* 8. 模型信任域与远程兜底策略（ADR-LLM-009）
  - 迁移+ORM+管理 UI：trust zone/client-data/mask policy
  - 任务过滤候选；服务器兜底显示与留痕；修不实 local_only
  - Verify：受限任务拒绝外部候选、事务所私有候选可按策略兜底
  - 证据：V237 + `ai_models.py` + `AIModelConfig.vue` / `ModelTable.vue`；`llm_route.filter_route_by_policy` 不满足即 typed `route_policy_denied`；Native `local_only=False`（收尾把两处陈旧断言改正）；附注生成结果由服务器模型兜底时如实提示（收尾补）；`test_ai_model_trust_policy.py`、`modelRouteView.spec.ts`、`useNoteAiDraftArtifact.spec.ts`
  - 未实测：V237 未落共享库（PG 不可达）；浏览器管理页

- [ ]* 9. 附注事实包与四类生成统一（ADR-LLM-012/014）
  - 服务端构建 NoteFactPack；变动分析不收客户端事实
  - 续写/改写/政策/分析统一预览 diff + generation ID + pending
  - 数字/日期/主体逐值验证，失败不准采纳
  - Verify：真实读取方口径、stale、缺数据、数字变异
  - 证据：`note_ai_fact_pack.py`；收尾补：请求带 `current_data` / `prior_data` 改为 422（原静默忽略）、单次生成也签发 `generation_id`、验证器按 Decimal 比值（1,000.00 ≡ 1000）、日期整体核对（资料年度的年末可推导）、主体核对、事实类叙述只认事实包与派生变动额 / 变动率（参照文档里的数字不算）；`test_note_ai_fact_pack.py`、`test_ai_task_contract_enforcement.py`、金标 `number-*` / `ocr-*`
  - 未实测：浏览器预览 diff 与待确认

- [ ]* 10. 底稿复核与高频专项调用迁移
  - 单页/批量复核及高频底稿结论改走 AiTaskExecutor
  - 规则先行，AI 只增加疑点；来源地址可点击
  - 低频硬编码 prompt 登债务清单，只许减少
  - Verify：确定性规则与 LLM 结果组合矩阵
  - 证据：`review_prompt` / `batch_review_service` / `wp_ai_service` 经 `invoke_ai_task`；疑点 `表名!C8` / `C8` 经 `workpaper:locate-cell` 定位到格（收尾补 `findingLocation.ts`，`findingLocation.spec.ts`、`AiReviewPanelLocate.spec.ts`）；系统检查项本身没有单元格地址，不可点
  - 未实测：浏览器点击定位

- [ ]* 11. 耐久批任务（ADR-LLM-015）
  - `ai_task_jobs/items` 迁移、ORM、worker、租约、取消、恢复、逐项幂等
  - 批量附注和批量复核迁移；每项返回稳定 generation ID，采纳不重跑
  - Verify：响应丢失、重启恢复、单项失败续行、取消
  - 证据：V238 + `ai_task_job_service`（SKIP LOCKED 认领、租约续期、取消、过期恢复、人工重试保留 generation_id）+ `workers/ai_task_worker` + `routers/ai_task_jobs`；`test_ai_task_job_service.py`、`test_review_prompt_integration.py`（收尾改为耐久任务契约：请求内不调模型、同幂等键重发得同一任务同一 generation_id）、`aiTaskJobs.spec.ts`、`useReviewPanelDurable.spec.ts`
  - 未实测：PG 上两 worker 竞争（SKIP LOCKED 只在 PG 生效）、浏览器进度恢复

- [ ]* 12. CAS 精确写回、diff 与撤销（ADR-LLM-016）
  - target adapter、基线版本/before hash、锁和权限；确认后应用原 patch
  - 记录 after version/hash、领域事件；安全撤销
  - pending 加载失败显示 unknown，正式输出 fail-closed
  - Verify：并发编辑、重复确认、锁、撤销冲突、事件
  - 证据：V239 + `draft_artifact_facade`（附注）；收尾补：签字门禁 `gate_rules_ai_content` 与可用动作 `allowed_actions_service` 在 AI 状态读不到时原为放行，改为阻断并只回滚到保存点（`test_ai_governance_fail_closed.py`）；`test_draft_artifact_facade.py`、`AiContentPendingBanner.spec.ts`
  - 范围说明：只有附注有自动写回 adapter；底稿宿主仍走人工复制确认，不自动写业务数据
  - 未实测：浏览器确认 / 撤销

## C. 上下文深化、分布式状态与运营闭环

- [ ] 13. 审计关系图上下文与 draft overlay
  - 按任务接 TB/调整/报表/附注/上下游底稿/证据/上年/同行业同模板同科目知识
  - 受限未保存草稿 overlay，绑定宿主、基线和 hash
  - Verify：跨项目零注入、预算裁剪、overlay 版本冲突
  - 证据：`audit_relation_context`（同项目 TB / 已批准调整 / 报表行本期上期 / 附注 / 关联底稿，逐份可见性过滤，失败记 unavailable）；附注续写 / 改写 overlay 绑定宿主、基线与 hash，收尾补：改写选区与已保存正文不一致时调用模型前拒绝、续写记录 `matches_saved` 并提示（`test_ai_audit_relation_context.py`、`test_note_ai_overlay_conflict.py`）
  - 未做：证据附件、上年底稿 / 附注、同行业同模板同科目知识未接入关系图；Chat 宿主的通用 draft overlay 未做

- [ ]* 14. 多 worker 状态与观测（ADR-LLM-018/019）
  - MCP budget/revocation、批任务锁/进度迁 Redis/DB
  - TTFT、tokens/s、deployment/fallback/error、验证结果、采纳/修订/拒绝、token/成本
  - 可复现 envelope：task/prompt/model/参数/app/context/output/verifier hashes
  - Verify：两 worker 竞争、重启、低基数指标、敏感正文不进入 metrics
  - 证据：MCP budget / 撤销走 Redis 原子操作、run 终态撤销 token（`test_ai_mcp_distributed_state.py`）；TTFT / tokens/s / 任务指标（`test_llm_metrics.py`）；收尾补：估算成本（单价 `GT_AI_TOKEN_UNIT_COST`，未配置记 0）与可复现 envelope（只存哈希与参数、不存正文，`test_ai_task_contract_enforcement.py`）
  - 未实测：真实 Redis / PG 上两 worker 竞争与重启

- [ ] 15. 实务 UI 收口与 stub 清理
  - 系统检查/AI 提示/人工结论分栏；实际模型位置、stale、裁剪、diff
  - QC/EQCR 独立挑战模式；插件执行入口隐藏或标开发中
  - 删除/下线旧重复 Chat 与无调用 AI 壳前先证明 0 调用
  - Verify：五角色、窄屏、键盘、中文提示
  - 证据：复核面板“系统检查 / AI 复核提示（不代表人工通过）”分栏、QC/EQCR 独立挑战提示；8 个插件 stub 标开发中、执行入口禁用、后端 fail-closed（`test_ai_plugin_developing_gate.py`、`AIPluginDevelopingGate.spec.ts`）；待确认横幅 diff / stale / 撤销
  - 未做：旧重复 Chat 与零挂载 AI 壳未清点、未下线；窄屏 / 键盘未走查

- [ ]* 16. 金标、真实 canary、全回归与浏览器终验
  - 无客户数据金标：引用、数字、拒绝下结论、权限、stale、fallback、注入、OCR
  - deterministic CI + 可选 live-model canary；候选树与干净 HEAD 逐节点对比
  - 浏览器使用 `http://127.0.0.1:3030`，测试项目写入后按平台路径恢复
  - INDEX.md 登记、复盘、单一 commit、按版本工具推送
  - Verify：本 spec 新增失败 0；所有完成项有实际代码与证据
  - 证据：金标 `backend/data/ai_golden_cases.json` 12 条（引用 / 数字 / 拒绝下结论 / 注入 / 权限 / 兜底 / OCR；stale 由 `test_note_ai_fact_pack.py` 与 `test_draft_artifact_facade.py` 覆盖）+ `test_ai_golden_cases.py` 确定性回放 + `scripts/check/ai_live_canary.py`（`--dry-run` 已验证）；回归对比见 design §11.3；INDEX.md 登记、复盘、提交推送随收尾完成
  - 未实测：真实模型 canary（模型 / PG 不可达）、浏览器终验、测试项目写入恢复
