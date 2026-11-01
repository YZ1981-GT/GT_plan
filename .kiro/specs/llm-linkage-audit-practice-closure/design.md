# 设计文档：LLM 联动与审计实务闭环

## 0. 设计结论

现有问题不是缺少 LLM，而是同一平台存在三类执行协议：统一 Chat Run、`llm_client` 直调、业务 service 自建生成/复核。正确收敛点不是把全部功能改成聊天，而是建立共享的 `AiTaskSpec → ContextPlan → LLM Gateway → Verifier → DraftArtifact → Human Decision → CAS Writeback` 主干。

本轮按可独立验收的交付单元实施。P0 修复先直接落现有链，统一内核随后承接新旧调用。已明确延后的 pgvector、DSH 扩面和插件实现不阻塞本轮完成。

## 1. 现状基线（2026-11-01）

| 编号 | 当前事实 | 证据 | 判定 |
|---|---|---|---|
| B1 | 前端和 `ChatRunRequest` 都提交 mentions/附件/review/sheet | `usePlatformAiChat.buildExtrasPayload`、`run_contract.ChatRunRequest` | 已接请求 |
| B2 | Native 只调用 `ContextBuilder.build(host, query, user)`；DSH 不消费四字段 | `NativeEngine._build_context`、`DshEngine._run` | 假接线 |
| B3 | mention/附件校验、review assembler、统一预算仅有定义或测试调用 | `load_mention_context`、`validate_for_run`、`SystemMessageAssembler`、`ContextBudgetPolicy` | 生产未接 |
| B4 | 后端 citation 事件键是 `citations`，前端读 `sources` | `NativeEngine._run`、`usePlatformAiChat` | 引用显示断裂 |
| B5 | coordinator 不从终态取 model，消息 `model_used` 可为空 | `run_coordinator._execute` | 留痕断裂 |
| B6 | 文件夹正文直接 LIMIT 20，无逐文档判权/排序 | `ContextBuilder._get_knowledge_folder_content` | 潜在越权/不确定 |
| B7 | `role_ai_features` 四路由已挂载，只校验登录 | `router_registry.collaboration`、`routers.role_ai_features` | 项目 IDOR 风险 |
| B8 | `llm_client` 以正文字符串返回失败；旧调用方常不识别 | `llm_client._sync/_stream_completion` | 假成功 |
| B9 | 单页复核解析失败产生 unknown finding，但总体状态只数 high/medium | `review_prompt.review_workpaper`、`LlmResponseParser.determine_pass_status` | 可假通过 |
| B10 | 专业边界函数零生产调用，多处 prompt 要“总体审计意见” | `AIService.check_boundary` 与调用搜索 | 边界未生效 |
| B11 | 附注变动分析只读请求体 current/prior，前端不传 | `note_ai.generate_analysis`、`useNoteAi.onAiGenerateAnalysis` | 模型依据为空 |
| B12 | 批量附注草稿无 message ID，“去采纳”会重新生成 | `batch_ai_fill_notes`、`DisclosureEditor.goAdoptSection` | 审阅稿≠采纳稿 |
| B13 | `AIEvidenceGate` 与 `ai_content_log` 两套确认体系并存；入口 scanner 只登记函数名，不证明实际过门 | `ai_evidence_gate.py`、`check_ai_entry_coverage.py` | 治理分叉 |
| B14 | `local_only=True` 与服务器兜底并存，Chat 上下文无按路由信任域脱敏 | `run_contract.CAPABILITIES_BY_ENGINE`、`AIService.chat_completion` | 声明不实 |
| B15 | batch review 进度/锁、MCP budget/revocation、候选冷却均为进程内状态 | 对应 service | 多 worker 不一致 |

## 2. 核心数据结构

### ADR-LLM-001 `AiTaskSpec`

新增声明式任务注册表，字段：

```text
task_code
risk_class = low | normal | high | prohibited
allowed_actions / allowed_roles
allowed_trust_zones
mask_policy
context_recipe
prompt_id / prompt_version
output_schema
verifier_id
writeback_policy
timeout_seconds / max_output_tokens
```

任务注册表描述业务语义，不保存 prompt 正文。Prompt 正文由版本化 registry 读取。禁止任务在进入模型前直接拒绝；高风险任务只允许输出证据、反例、缺口和建议程序。

### ADR-LLM-002 `ContextPlan`

Native 和 DSH 共用：

```text
host snapshot
review prompt
mentions[]
attachments[]
deterministic facts[]
knowledge hits[]
prior-year links[]
manifest[]
```

每项都带 source type/id、label、version/hash、status、used tokens、stale、reason。ContextBuilder 不再单独维护与 `ContextBudgetPolicy` 冲突的比例；预算以生效模型 context window 减 system/history/output reserve 后计算。

### ADR-LLM-003 `LLMInvocationResult`

底层运行时继续抛 typed error；兼容层不再返回错误正文。结果含：status、text、model_id/name、deployment、fallback、attempts、usage、latency、error code。旧调用方分批迁移，在迁移完成前统一适配器识别全部历史 fail-soft 串。

### ADR-LLM-004 `DraftArtifact`

先在现有 `AIChatMessage + AiContentLog` 上建立 facade，不新造第三套确认表。每份草稿绑定 generation ID、task code、内容 hash、上下文 manifest、prompt 版本、目标位置和业务基线版本。`ai_content_governance` 只保留正式输出门所需扩展字段，通过 adapter 与同一 generation ID 关联，后续再评估表合并。

## 3. Chat Run 闭合

### ADR-LLM-005 单一 ContextPlan 装配

Run 创建后、调用 engine 前：

1. 重新授权宿主；
2. 逐项加载 mention；
3. 校验附件 owner/session/status，读取完成 OCR 文本；
4. 解析 review prompt；
5. 加载宿主与知识 RAG；
6. 按统一预算裁剪；
7. 生成完整 manifest；
8. 用 `SystemMessageAssembler` 形成一条 system message。

Native 直接消费文本；DSH 将相同 manifest 和只读材料传给 Agent，同时保留 MCP 工具的二次授权。

### ADR-LLM-006 capability 必须可伪证

能力由实际 adapter 注册推导。`attachments/review_mode` 只有生产 consumer 存在才为 true。守卫删除 consumer 后 capability 测试必须红，禁止只断言常量。

### ADR-LLM-007 事件契约

citation 统一为 `payload.citations`。前端消息引用可点击，按 source type 构造深链；打开目标仍走目标页权限。coordinator 从 done payload/usage 记录 model、deployment、fallback 和 attempts。

## 4. 权限、角色与信任域

### ADR-LLM-008 动作能力

把 AI 能力拆为 ask、draft、review、adopt、agent：

- 审计助理、经理、合伙人：ask/draft；adopt 仍需目标资源写权。
- QC/EQCR：ask/review，只读独立挑战；不能 draft 到业务对象、adopt 或 agent 写动作。
- admin：受资源边界约束的全部动作。

页面不再硬编码角色数组，全部读取 capability 结果。

### ADR-LLM-009 模型信任域

在 `AIModelConfig` 增 `trust_zone`、`client_data_allowed`、`mask_policy`：

- local_device
- firm_private
- approved_provider
- restricted

`deployment` 仍用于路由位置，`trust_zone` 用于数据政策。任务执行按 task spec 过滤候选；不满足时返回 typed `route_policy_denied`，不能静默换候选。远程/事务所服务器是否可用由管理员配置和任务政策共同决定。

### ADR-LLM-010 项目鉴权

`role_ai_features`：stale-reminders readonly、weekly-report edit、qc-trend review、project-summary review；并按动作 capability 校验。metrics/health 仅 admin 或内部网络身份访问。

## 5. 审计验证器

### ADR-LLM-011 确定性结果优先

复核响应拆为 `deterministic_checks`、`ai_findings`、`human_status`。overall pass 不由 LLM 计算：

- 任一 blocking deterministic failure → fail；
- 未执行、证据不足、解析失败、模型失败、unknown → manual_review_required；
- 只有确定性检查完整通过且人工完成复核，才可形成业务“通过”；
- AI 空 findings 只表示“未发现新增疑点”。

### ADR-LLM-012 Claim 验证

第一批覆盖数字、日期、主体：结构化输出中的事实带 source_id/address/version。数字用 Decimal 与权威值逐值核对；不一致或无来源则标 unverified，不得自动采纳。准则引用只能来自授权知识文档，不允许模型自由生成条文号后直接采纳。

### ADR-LLM-013 专业边界

废弃关键词 `check_boundary` 作为门禁。`task_code` 决定允许输出。现有“overall-opinion”入口改名和 prompt，只生成“科目结论措辞建议/复核建议”，重大判断任务改输出 decision factors、evidence gaps、alternatives、recommended procedures。

## 6. 附注、批量任务和写回

### ADR-LLM-014 附注事实包

服务端按章节构造 `NoteFactPack`：当前/上期表格值、关联报表、TB、调整、上年章节、stale 和缺失项。生成叙述只能引用 fact pack；缺必要数据返回 `insufficient_context`。

续写、改写、政策、分析都返回 DraftArtifact 和 diff，不直接改编辑器。前端确认“应用到草稿”后仍标 AI 来源；正式确认走统一 pending。

### ADR-LLM-015 耐久批任务

批量附注和批量复核复用现有 Chat Run 的租约/事件思想，但使用独立 `ai_task_jobs/items`：请求 hash 幂等、每项状态、generation ID、基线版本、取消标记、失败重试。worker 每项独立事务，重启后恢复。

### ADR-LLM-016 CAS 精确写回

`AiWritebackAdapter` 按 host/type 分派。确认时校验目标项目、权限、锁、基线版本和 before hash；只应用预览过的 patch。成功记录 after version/hash、发领域事件。撤销只能在当前业务版本仍等于该次 after version 时执行，否则要求人工合并。

待确认列表加载失败显示 `unknown/error`，正式输出门把“治理状态未知”视为未就绪。

## 7. Prompt 与观测

### ADR-LLM-017 Prompt Registry

Prompt 版本 append-only；变更需版本号、适用准则/行业/wp_code、输入/输出 schema、批准人和回归集。迁移现有高频链，低频硬编码 prompt 先登记债务清单并由棘轮只减不增。

### ADR-LLM-018 可复现 envelope

记录 task/prompt/model/route/parameters/app version/context hashes/output hash/verifier result。敏感全文仍只留在现有受权业务表，不写 Prometheus 或哈希链 payload。

### ADR-LLM-019 分布式状态与指标

MCP budget/revocation、批任务锁/进度迁 Redis/DB。候选冷却可继续本地优化，但路由失败率需聚合观测。指标补 TTFT、tokens/s、fallback、deployment、错误类型、验证失败、采纳/修订/拒绝；标签保持低基数。

## 8. 前端实务呈现

1. 将“系统确定性检查”“AI 复核提示”“人工结论”分栏。
2. 显示实际模型位置、兜底、上下文裁剪和资料 stale。
3. 所有生成类操作先预览 diff；禁止失败占位文案进入编辑器。
4. QC/EQCR 使用“独立挑战模式”，默认不把项目组结论当权威事实。
5. 未保存内容未纳入时显示明确提示；接入 draft overlay 后显示“使用当前未保存草稿”。
6. 插件 stub 隐藏执行按钮并标“开发中”。

## 9. 测试与验收

- 契约：OpenAPI/TS 事件键、capability 与生产 consumer 对拍。
- 端点：所有 AI 项目路径测未登录、跨项目、允许角色、只读角色。
- 故障注入：模型断连、429、读超时、空输出、无效 JSON，均不得形成成功草稿。
- 数据：文件夹混合权限、同名文档、旧版本、stale、附件 owner/session。
- 复核：确定性失败不能被 AI 通过覆盖；parse failure/unknown 必须 manual。
- 写回：基线版本变化、锁、重复确认、撤销冲突。
- 批任务：响应丢失幂等、worker 重启恢复、取消、单项失败续行。
- 浏览器：mention/附件/review 真进入 manifest；附注批量采纳原草稿；角色矩阵；服务器兜底提示；console error 0。
- 真实模型 canary 使用无客户数据固定夹具，不纳入普通 PR 的强制在线依赖。

## 10. 实施边界与并发保护

当前主工作树有其他会话的大量未提交改动，且重叠 `DisclosureEditor.vue`、`DshPanel.vue`。本 spec 按文件/代码块登记归属，优先改不重叠模块；重叠文件只做最小定点编辑。每批结束在“最新 HEAD + 本批改动”的临时分离头 worktree 验证，不覆盖他人工作区内容。

## 11. 收尾补缺与复盘（2026-11-01）

### 11.1 交付形态

第一批代码（任务 1~15 主体、V236~V239）随并发会话的提交 `a6c1fa93a` 入库并推送，该提交说明是平台性能改动、未打版本标签。收尾补缺单独一个提交，用版本工具推送。任务状态口径见 tasks.md 头部：代码已改但浏览器 / 真实 PG / Redis / 模型未实测的一律 `[ ]*`。

### 11.2 收尾复核抓到的缺口（均已修复并配反向用例）

| # | 缺口 | 修复 |
|---|---|---|
| 1 | 签字门禁 `gate_rules_ai_content` 与可用动作 `allowed_actions_service` 读 AI 待确认状态出错时分别 `return None`、“降级放行” | 状态未知即阻断（`AI_CONTENT_STATE_UNKNOWN` / `AI_STATE_UNKNOWN`），只读查询放保存点，失败不污染调用方事务 |
| 2 | `AiTaskSpec` 的动作、超时、写回策略三个字段没有读取方 | 执行器校验动作并按任务超时（按输出上限放宽）；草稿入口按写回策略拒绝复核输出变正文、只供参考的任务须经对话“采纳”；context recipe 与 output schema 记入 envelope |
| 3 | Prompt“append-only”只校验版本号不重复，原地改已发布正文无人发现 | 正文哈希锁 + `check_ai_prompt_versions.py`，Prompt 带批准人与适用范围 |
| 4 | 验证器按字符串比数字（1,000.00 与 1000 不同）、参照文档里的数字也算来源、不核对日期与主体 | Decimal 规范化；日期整体识别（资料年度的年末可推导）；主体核对；事实类叙述只认事实包与派生变动额 / 变动率 |
| 5 | 变动分析请求里的 `current_data` / `prior_data` 被静默忽略 | 非空即 422，提示事实由服务端加载 |
| 6 | 单次附注生成没有 `generation_id` | 消息、草稿与回执同一身份 |
| 7 | `/api/ai-chat/metrics` 零鉴权，经网关 `/api/` 对外可达 | 仅 admin；根路径 `/metrics` 不经网关（网关只代理 `/api/`），留给内网 Prometheus |
| 8 | 调用债务棘轮不查已偿还条目，删掉的旧调用可原样加回 | 基线须与现算相等，`--shrink` 只减不增 |
| 9 | 复核疑点只能跳到表 | `表名!C8` / `C8` 经 `workpaper:locate-cell` 定位到格 |
| 10 | 改写选区含未保存修改时仍调用模型、生成注定 stale 的草稿 | 调用模型前与已保存正文对账；续写记录 `matches_saved` 并提示 |
| 11 | 前端附注 AI 返回类型缺 `artifact_id`（单区域 vue-tsc 报 4 处 TS2339） | 补齐 DraftArtifact 身份字段类型 |
| 12 | 两处 `local_only is True` 断言、批量复核同步端点用例与现行实现不符 | 改为现行为断言；批量复核用例改为耐久任务契约（请求内不调模型、同幂等键重发得同一任务与 generation_id） |
| 13 | 角色 / 动作漏传即放行：`role=None` 跳过角色门禁，`action=None` 跳过动作门禁，而周报、项目摘要、底稿结论建议三条链路本来就没传角色 | 缺角色 / 缺动作一律 `rejected`（`ai_role_missing` / `ai_action_denied`）；`actor_role()` 统一取角色并贯通 `role_ai_features`、`WpAIService`（构造带角色）与 4 个路由；守卫按 AST 要求 13 个生产调用点都显式声明 |

另补：估算成本指标（单价 `GT_AI_TOKEN_UNIT_COST`，未配置时记 0）、可复现 envelope、复核面板角色集合与任务声明逐值一致的守卫、金标 12 条与真实模型 canary 脚本。

### 11.3 验证

环境：PG 5432 / Redis 6379 / 后端 9980 / 前端 3030 全部不可达，Docker 未运行 ⇒ 真实 PG、Redis、浏览器与真实模型一项都没跑，相关任务一律 `[ ]*`。

| 项 | 结果 |
|---|---|
| 本 spec 聚焦后端用例（39 文件） | 372 passed / 2 failed —— 两条是 `jsonpath_ng` 未安装的 AL-01，spec 前基线同红 |
| 前端用例（9 文件） | 69 passed / 1 failed —— `useNoteTemplate.loadNoteMappingPreset`，用 HEAD 版同一文件复跑同红 |
| 单区域 `vue-tsc` | 0 error；变异证明：`findingLocation.ts` 与 `AiReviewPanel.vue` 各注入一处类型错误后分别报 TS2322，`finally` 逐字节还原 |
| 行数门禁 | 改动的 56 个代码文件通过；`test_task6_native_engine.py` 以真实行数 1720 首次登记白名单（HEAD 即已超限且从未登记） |
| Prompt 哈希锁 | `check_ai_prompt_versions.py --check` 12/12 一致；改已发布正文即 exit 2（`compare` 的 changed/removed 用例覆盖） |
| 调用债务棘轮 | `check_ai_task_call_coverage.py` direct 132/132、prompt 43/43，新增「基线含已偿还条目即红」 |
| 真实模型 canary | `ai_live_canary.py --dry-run` 通过（6 条 live 用例任务均已登记）；真实模型未跑 |

三方归因（spec 前基线 `53a1a4b83` / HEAD `a6c1fa93a` / 候选树，20 个相关文件 823 用例）：候选树 29 条「spec 前绿 → 现红」中 **26 条经定位是本 spec 第一批真实造成的**，已逐条修完：

- 模型配置 CRUD 改为同事务写哈希链审计（任务 8）⇒ 三份 SQLite 夹具只建了 `ai_model_config`，补建 `audit_log_entries`（20 条）；
- 远程 OCR 候选新增信任域三字段 ⇒ 替身补字段（4 条）；
- 本机不可用提示改为点明实际兜底去向 ⇒ 断言按新文案（1 条）；
- `/api/review-prompts/metrics` 收紧为仅管理员 ⇒ 用例改为「覆盖率登录即可、指标 403、admin 200」（1 条）。

另有 3 条经 `git diff` 定位到同一提交里**其他 spec** 的改动（`require_project_access_stream` 的 SSE 鉴权 1 条、知识库上传改分块 `read(size)` 2 条），记入 §11.4 未代修。

交付形态：收尾期间远端又前移 21 个提交（至 `4390aaaa3` / v1.0.89）。本批改动按「每文件的真实编辑基线」重放到远端头的分离头 worktree（62 个文件，与远端新提交重叠仅 2 个，按 LF 归一后三方合并，`role_ai_features.py` 自动合并、行数白名单两侧都在尾部追加故手工并存），候选树上重跑回归。

🔴 重放后发现远端头**干净检出就起不来**：`adjustment_import.py` 用了 `require_project_permission` 却没导入它 ⇒ `import app.main` 直接 `NameError`，凡经生产注册发请求的用例全部 collection error（CI 的 `pytest -x` 会停在这里）。属调整大厅那一侧的遗漏，但它挡住本批验证与 CI，故在本次提交里补上这一行导入并在此记录。

最终口径以「候选树 vs 干净远端头（同样只补那一行导入）」逐节点对比为准（62 个文件、约 1250 用例）：远端头 111 red → 候选树 60 red，**新增失败 0，修复 51**。修复的 51 条分三类：

1. 本 spec 第一批打红的 12 条 —— 附注 AI 的桩打在已不再走的 `llm_client.chat_completion` 上、信任域字段缺失、兜底文案、指标收紧、`local_only` 声明、底稿字段建议未取角色；
2. 远端 `audit-log-chain-integrity` 把哈希链头拆成独立表 `audit_chain_head` 后，只建 `audit_log_entries` 的 SQLite 夹具全红（模型配置三份 + `test_ai_content_gate_rule` + 本 spec 的 `test_draft_artifact_facade`），一并补齐建表；
3. 上面那行缺失的导入 —— 它让所有经生产注册发请求的用例在 collection 阶段就错。

剩余 60 条全部在远端头同样红：PG / Redis 不可达（`WinError 1225`）、`jsonpath_ng` / `pypinyin` 未安装、DSH vendor 目录缺失，以及 §11.4 列的三类他 spec 改动。

### 11.4 范围外发现（未改）

- 根路径 `/metrics`（平台性能 spec）无鉴权，依赖网关不代理；若改为直连部署须加内网身份校验。
- `useNoteTemplate.loadNoteMappingPreset` 前端用例在 HEAD 即红（函数已改为异步，用例未 await）。
- `test_deliverable_generation_membership_auth` 的「全链路进度流」期望非成员 403、实得 401：`a6c1fa93a` 把该端点改成 `require_project_access_stream`（SSE 取 query token），权限世界没有对应的 override。属平台性能 spec 的 SSE 鉴权改动，用例需按新依赖改造。
- 同文件「一键生成全套」5 条在 spec 前基线即红（旧入口已被另一 spec 退役，返回 410 `LEGACY_FULL_DELIVERABLES_RETIRED`）。
- `test_ai_content_confirm_flow` 的 AL-01 两条因 `jsonpath_ng` 未安装而红，spec 前基线同红。
- 只有附注有自动写回 adapter；底稿宿主仍人工复制确认。

### 11.5 教训

- 声明式规格字段要同时写“该字段改变行为”的用例；只登记不读取的字段等于没有（第 2 条）。
- 门禁读不到状态时的默认值决定安全性：吞异常后放行就是假绿（第 1 条）。
- 并发会话会把本 spec 未提交的文件整体带进它的提交，也会清掉仓库根全部 `tmp_*`（含已 lock 的基线 worktree，回归跑到一半被删）；回归产物要能用脚本重建，结论以重跑为准。
