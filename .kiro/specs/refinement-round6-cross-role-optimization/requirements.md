# Refinement Round 6 — 跨角色系统级优化（门面收敛 + 守门机制 + 死代码清理）

## 起草契约

**本轮视角**：不代表任何单一角色。5 轮（合伙人 / 项目经理 / 质控 / 助理 / EQCR）已独立完成，各角色局部体验均已打磨。本轮以"**5 轮独立看都没问题、但跨角色协同时暴露的系统级矛盾**"为切入点，做一次总复盘修复。

**核心原则**：

- 不是"再加一个角色视角"，而是**修补角色之间的接缝**。
- 不重写，优先加 **Facade（门面）** 统一多套并存的实现。
- 有些系统级问题必须留给 Round 7+（例如全系统迁移到通用就绪检查服务、QC 规则 DSL 执行器全集），本轮明确收敛。
- 起草前后各做一次"代码锚定交叉核验"（grep 所有假设的字段/表/端点/枚举）。

**迭代规则**：参见 [`../refinement-round1-review-closure/README.md`](../refinement-round1-review-closure/README.md)（v2.2）。本轮 Round 6，对应 README 中 "Round 6+ 开放轮次"。

---

## 复盘背景（5 轮协同后暴露的系统级断层）

### 断层 1：归档端点三重并存 + 前端第四入口

**代码锚定**：

| 端点 | 路径 | 服务 | 语义 |
|------|------|------|------|
| A | `POST /api/workpapers/projects/{pid}/archive` | `wp_storage_service.archive_project`（`wp_storage.py:42`）| 压 tar.gz 移冷存储 |
| B | `POST /api/projects/{pid}/archive` | `private_storage_service.ProjectArchiveService.archive_project`（`private_storage.py:64`）| 锁定底稿 + 推云 + 清本地 |
| C | `POST /api/data-lifecycle/projects/{pid}/archive` | `data_lifecycle_service.archive_project_data`（`data_lifecycle.py:38`）| 软删除可恢复 |
| D | `POST /api/archive/{pid}/archive` | 前端 `apiPaths.ts:531` 调用，但后端 `router_registry.py` 无任何 `/api/archive` 前缀注册，实际**端点不存在**（前端调用必 404）|

R1 需求 5 已要求"归档向导前端收敛"，但：
- 底层 A/B/C 三套服务仍并存；
- 前端 `collaborationApi.ts:114` 和 `apiPaths.ts:531` 的 D 端点指向一个**不存在**的后端路由，是实装漂移。

### 断层 2：就绪检查三套逻辑可能给出矛盾结论

**代码锚定**：

| 实现 | 入口 | 规则数 | 形式 |
|------|------|--------|------|
| A | `gate_engine`（`gate_engine.py:59`）| 4 个 GateType：`submit_review` / `sign_off` / `eqcr_approval` / `export_package` | 插件式 GateRule 注册 |
| B | `SignReadinessService.check_sign_readiness`（`partner_service.py:139`）| 8 项硬编码 | 串行 SELECT |
| C | `ArchiveReadinessService.check_readiness`（`qc_dashboard_service.py:252`）| 11-12 项硬编码 | 串行 SELECT |

三者重叠项很多（底稿复核通过 / QC 通过 / 未解决意见 / 调整分录审批 / 未更正错报评价 / 审计报告已生成），但**实现各写一遍**。当 gate 规则更新而 B/C 未跟进时，合伙人看的"签字前 8 项"与实际 `sign_off` gate 阻断结论可能矛盾。R1 需求 3 已要求合一，本轮核心是"**立即落地 Facade 而非重写**"。

### 断层 3：复核批注两套模型长期并存

**代码锚定**：

- `ReviewRecord`（`workpaper_models.py:405`）：单行绑定 `wp_id + cell_reference`，R1 需求 2 定为工单真源。
- `ReviewConversation`（`phase10_models.py:18`）：跨对象多轮对话。
- 仍被活跃使用：`review_conversation_service.py`、`rc_enhanced_service.py:38`、`issue_ticket_service.py:50` 依然读 `review_conversations`、`router_registry.py:111` 仍注册 `review_conversations` 路由。

两套并存若不划边界，长期会漂移（比如工单真源归 ReviewRecord 但对话链留痕归 ReviewConversation，哪个是"完整评审留档"？）。

### 断层 4：QC 规则全硬编码，业务方加规则必须改代码

**代码锚定**：

- `qc_engine.py` QC-01~14 共 14 条（`SamplingCompletenessRule` 在 `qc_engine.py:374`，`PreparationDateRule` 在 `:428`，主注册器约 `:667`）。
- `gate_rules_phase14.py` QC-19~26 + 一致性 + 错报超限（`register_phase14_rules` 在 `:475`）。
- 数据库无 `qc_rule_definitions` 表（grep 零命中）。

R3 需求 1 已要求落地 `qc_rule_definitions` 表，但 R3 实装进度截止当前并未推进到 DSL 执行器层。本轮**作为前置配套**，先把"规则清单 + 元数据"表建起来，即使所有规则暂时都是 `expression_type='python'`，也能支持开关、版本、准则引用这些低风险能力，为 Round 7 做铺垫。

### 断层 5：SignatureRecord.signature_level 无顺序强制 + 字符串控制流残留

**代码锚定**：

- `SignatureRecord.signature_level: String(20)`（`extension_models.py:48`），注释 `level1/level2/level3`。
- R5 为支持 EQCR，走的是 R1 新增的 `required_order + prerequisite_signature_ids`（`extension_models.py:51+`，R5 签字写 `order=4, level="eqcr"`）。
- legacy 字符串判断仍存在：`sign_service.py:170` 的 `if record.signature_level == "level3"` 控制 CA 证书验证分支。
- `eqcr.py:1009` 写 `signature_level="eqcr"`，与 `"level3"` 不兼容（EQCR 按新语义，CA 证书分支永远走不到）。

结果：`signature_level` 字段在新旧代码中语义分裂，新代码靠 `required_order`，旧代码靠字符串比较，未来加签字级别时两边容易漏改。

### 断层 6：通知铃铛装了但没挂（5 轮全被绕过）

**代码锚定**：

- `NotificationCenter.vue`（`frontend/src/components/collaboration/NotificationCenter.vue:2-158`）组件完整含 `<el-badge>` + `<Bell>` 图标。
- `DefaultLayout.vue`（`frontend/src/layouts/DefaultLayout.vue`）grep `NotificationCenter` **零命中**。
- 5 轮都没人发现，因为各角色用自己的 Dashboard 拉新数据。
- R2 需求 3 已列但 R2 实装尚未完成到该任务。

### 断层 7：死代码未清（两处）

**代码锚定**：

- `ReviewWorkstation.vue`：R1 需求 1 验收标准 7 明确要求"旧的 ReviewWorkstation.vue shall 被删除"，但 R1 实装当前仍未推进到该任务（grep fileSearch `ReviewWorkstation` 零命中于 `router/index.ts`，确认仍是死代码）。
- `backend/app/routers/pbc.py`：15 行，`list_pbc` 直接 `return []`；`confirmations.py` 同模式。前端 `apiPaths.ts` 无对应调用，Maturity 标签 `pilot`（`ThreeColumnLayout.vue:332`），但**后端根本没数据返回**。这是空壳，应该标 `developing` 或删除。

### 断层 8：testing/lint/CI 守门机制欠缺（跨轮复盘发现的结构性问题）

**代码锚定**（R5 跨轮复盘记录，memory.md）：

- `audit_report_templates_seed.json` 71 处 CJK 字符串内用直双引号 `"XX"` 导致 JSON 解析失败 → seed 数据**无 schema 校验、无 CI pre-commit hook**。
- `qc_engine.py:383` `SamplingConfig.working_paper_id` 字段不存在 → **无 ORM 字段引用静态检查**。
- `qc_engine.py:430+` `datetime.utcnow() - aware_datetime` tz 混用 → **无 pytz/datetime 类型 lint**。
- `backend/tests/conftest.py` 曾漏导入 15+ 模型包（R5 已修）→ 说明 **SQLite create_all 路径无"模型注册完整性"检查**。
- `backend/requirements.txt` 无 `hypothesis` → 101 个属性测试（`test_phase0_property` / `test_phase1a_property` / `test_remaining_property` / `test_production_readiness_properties`）**从未运行**（R5 已装 `hypothesis@6.152.4` 但未写入 requirements.txt）。
- 根目录 `fileSearch` `.github/workflows`、`pre-commit` **零命中**，整个项目**无 CI 配置**。

### 断层 9：缓存 key 约定分散

**代码锚定**：

- `report_engine._cache_key: "report:{project_id}:{report_type}"`（`report_engine.py:347`）
- `ledger_penetration_service._cache_key`（`ledger_penetration_service.py:452`）带 JSON params
- `formula_engine._cache_key(project_id, year, formula_type, params)` md5 hash（`formula_engine.py:436`）
- `metabase_service.get_cached_or_fetch(cache_key, fetch_fn, ttl)`（外部传入）（`metabase_service.py:170`）
- `gate_engine._cache: {project_id}:{gate_type}:{trace_id}` 内存字典（`gate_engine.py:152`）
- `deps.py:215` 权限缓存 `perm:{user_id}:{project_id}`

五套命名/TTL/失效策略各不同。跨角色时（例如 PM 改了重要性，合伙人应该立即看到新的签字就绪检查），失效节点散落在 `event_handlers.py` 各处监听，容易漏。本轮仅做"**约定落盘 + 失效点 registry**"，不重写各模块。

### 断层 10：seed 数据无 schema + 无 CI

**代码锚定**：

- `backend/data/audit_report_templates_seed.json`（R5 复盘修的 71 处双引号问题）
- `backend/data/wp_account_mapping.json`（88 条致同 2025 映射）
- `backend/data/independence_questions_annual.json`（32 题）
- `backend/data/note_templates_seed.json`、`report_config_seed.json` 等。

任意合作者手工编辑任一文件都可能破坏加载。无 JSON schema 校验、无 CI lint、无单元测试验证 seed 可加载。

---

## 本轮范围

Round 6 聚焦"**收口不重写**"，7 个需求（≤ 10），重点落地：

1. 三套归档 → 单一编排 Facade（后端 + 前端双收敛），其余三端点保留并加 `Deprecation` 响应头
2. 三套就绪检查 → `gate_engine` 为唯一真源，Sign/Archive 两个 service 改为调 gate 的适配器
3. 复核批注两套模型 → 明确边界 + 迁移脚本留痕（不删 ReviewConversation）
4. QC 规则定义表骨架（不实装 DSL 执行器）
5. 签字字段 legacy 字符串控制流清理
6. 通知铃铛挂载 + 死代码清理（合并自 R1 / R2 未完成项的最后兜底）
7. 守门机制：seed schema + CI 配置 + hypothesis 入 requirements + 本项目 pre-commit

**不在本轮范围**（留 Round 7+ 或按需）：

- QC 规则 DSL 执行器（jsonpath/sql/regex）完整实装（R3 本轮仅建表）
- 缓存 key 命名统一 + 失效点 registry 改造（本轮仅落约定，不动既有 5 套代码）
- `signature_level` 字段物理移除（本轮仅解绑控制流，字段保留）
- `ReviewConversation` 模型退役（本轮仅划边界 + 留标记，不删表）
- PBC / 函证业务功能实装（本轮仅标 developing 或移除空壳）
- 跨角色数据一致性自动化回归套件（本轮仅建 CI 骨架）

---

## 需求列表

### 需求 1：归档编排 Facade（三套端点 + 前端第四入口统一）

**用户故事**：作为任何一个跨角色的使用者（PM 发起归档 / 合伙人确认 / 质控审 / EQCR 前置 / 助理查进度），我希望全系统只有一个"归档编排"真源，前端一个入口、后端一套编排，底层三个存储服务各司其职但**不暴露给业务层**。

**代码锚定**：见"断层 1"。R1 需求 5 已预约此需求，本轮落地实装。

**验收标准**：

1. The 后端 shall 新增路由器 `app/routers/archive_orchestrator.py`，挂 `prefix="/api/archive-orchestrator"`，暴露唯一端点 `POST /api/archive-orchestrator/projects/{project_id}/archive`，请求体 `{push_to_cloud: bool, cleanup_local: bool, dry_run: bool}`，返回 `{archive_id, gate_result, wp_storage_result, cloud_push_result, lifecycle_result, checklist_id}`。
2. The 编排服务 shall 串行执行：`gate_engine.evaluate(GateType.export_package)` → 若 `passed=False` 则立即返回（不进入存储层）；否则依次调 `wp_storage_service.archive_project` → `ProjectArchiveService.archive_project`（若 `push_to_cloud=True`）→ `data_lifecycle_service.archive_project_data`；任一步失败立即回滚（`wp_storage` 已归档后的回滚用"置回 `review_passed` 状态"软回滚，不物理解压）。
3. The 既有三个端点 A/B/C（`/api/workpapers/projects/{pid}/archive` / `/api/projects/{pid}/archive` / `/api/data-lifecycle/projects/{pid}/archive`）shall **保留**（向后兼容），但各自加 FastAPI `deprecated=True` 标记 + `Deprecation: version="R6"` 响应头 + warning log（`"[deprecated] Use /api/archive-orchestrator/..."`），不修改实现逻辑。
4. The 前端 `apiPaths.ts:523-538` 的 `archive.archive` 常量 shall 指向新编排端点；`collaborationApi.ts:107-124` 的 `archiveApi.archive` shall 相应更新。
5. The 前端 `apiPaths.ts:531` 当前指向的 `/api/archive/{pid}/archive` 是**未实装**端点（grep `router_registry.py` 零命中），shall 在本轮删除该常量（或换为新编排端点），并搜全部 `archive.archive` 使用点修正。
6. The 新编排端点 shall 幂等：同一 `project_id` 在 24 小时窗口内重复调用返回同一 `archive_id`；实现方式为查询 `archive_checklists` 表该项目最近记录 `created_at >= now() - 24h` 且 `status in ('completed', 'in_progress')` 则直接复用其 id，不重复打包。由于 `archive_checklists` 当前仅有 `ix_archive_checklists_project` 索引（`collaboration_models.py:421`）无唯一约束，幂等判断走应用层查询而非 DB 约束。
7. The 后端 shall 新增 `test_archive_orchestrator.py`，覆盖 4 个场景：gate 不通过拒绝、三步全成功、第二步（push_to_cloud）失败时第一步产物的回滚路径、dry_run 不落任何写。

### 需求 2：就绪检查门面（gate_engine 为唯一真源，Sign/Archive 两视图改为适配器）

**用户故事**：作为合伙人（看签字前 8 项）或质控（看归档前 11 项），我希望看到的结论与 `gate_engine` 真正执行 `sign_off` / `export_package` 时完全一致，不会出现"检查全绿、真签被阻断"的矛盾。

**代码锚定**：见"断层 2"。R1 需求 3 已预约此需求，本轮落地 Facade（不重写三套实现）。

**验收标准**：

1. The 后端 shall 新增 `app/services/readiness_facade.py`，暴露三个方法：`check_sign_readiness(project_id) → dict`、`check_archive_readiness(project_id) → dict`、`check_submit_readiness(project_id) → dict`。
2. The `readiness_facade.check_sign_readiness` shall 调 `gate_engine.evaluate(GateType.sign_off, project_id, trace_id=<虚拟>)` 后将返回的 `failed_rules / warnings / passed` 映射到 8 项结构化输出（字段名沿用 `SignReadinessService` 现有 `id/label/passed/detail`），保证前端无需改动。
3. The `SignReadinessService.check_sign_readiness`（`partner_service.py:139`）shall 改为调 `readiness_facade.check_sign_readiness` 并保留兼容输出；旧的 8 项硬编码查询代码 shall 删除，不再保留双实现。
4. The `ArchiveReadinessService.check_readiness`（`qc_dashboard_service.py:252`）shall 改为调 `readiness_facade.check_archive_readiness`（内部映射到 `GateType.export_package`），11-12 项硬编码查询代码 shall 删除。
5. The 合伙人签字前检查与 `sign_off` gate 的规则集 shall **同源**：即 `SignReadinessService` 看到的 "8 项" 永远是 `sign_off` gate 注册规则的**投影（facet view）**，不是独立的 SELECT 链。
6. The 本轮 shall **不新增**任何独立于 gate 的检查项；若业务上 "KAM 已确认 / 独立性确认" 当前不在 gate 规则中（当前读 `wizard_state`），shall 新增两个 GateRule（`KamConfirmedRule` / `IndependenceConfirmedRule`）注册到 `sign_off` gate，由 facade 映射回同字段名输出。
7. The 后端 shall 新增 `test_readiness_facade.py`，对比旧实现与 facade 在 5 个典型 project 状态下输出的 `passed/failed` 集合，断言一致。

### 需求 3：复核批注两套模型划清边界

**用户故事**：作为助理（写评论）、复核人（回复）、PM（追进度）、合伙人（看汇总），我希望明确知道 "工单真源归 ReviewRecord、多轮讨论归 ReviewConversation"，不再两套都能单独关闭/驳回造成事实分裂。

**代码锚定**：见"断层 3"。R1 需求 2 已定 ReviewRecord 为工单真源。本轮落地边界。

**验收标准**：

1. The `ReviewRecord` shall 新增字段 `conversation_id: UUID | null`（可选外键到 `review_conversations.id`），表示"此单行批注所归属的多轮讨论链"，alembic migration `round6_review_binding_20260507.py`。
2. The `ReviewConversationService.close_conversation`（`review_conversation_service.py:96-107`）shall 在关闭对话时校验：若存在未解决的 `ReviewRecord`（`conversation_id == this_cid` AND `status != 'resolved'`），拒绝关闭并返回 `CONVERSATION_HAS_OPEN_RECORDS` 错误。
3. The `IssueTicketService.create_from_conversation`（`issue_ticket_service.py:46`）与 `wp_review_service.add_comment(is_reject=True)` 两个路径 shall 相互去重：若目标 `ReviewRecord.id` 已存在 `IssueTicket(source='review_comment', source_ref_id=record.id)` 记录（字段名对齐 R1 实装的 `wp_review_service.py:292`），拒绝重复创建并返回已有工单 id。
4. The 前端 `ReviewInbox.vue` 列表 shall 显示每条 ReviewRecord 是否有 `conversation_id` 引用（一个"💬N"角标），点击跳转会话详情；**不新增独立的会话入口**（避免助理面对两个入口混乱）。
5. The 后端 shall 新增 `test_review_record_conversation_binding.py`，3 场景：批注→对话→关闭失败、批注→对话→解决批注→关闭成功、对话已转工单不重复转。
6. The 本轮 shall **不删除** `review_conversations` 表 / 路由 / service，仅做绑定和防重；退役时间点由 Round 7+ 决定。

### 需求 4：QC 规则定义表骨架（为 R3 需求 1 做前置）

**用户故事**：作为质控合伙人，我希望数据库里有一张 `qc_rule_definitions` 表，列出系统当前全部 22 条 QC 规则（QC-01~14 + QC-19~26）的元数据（准则引用、严重性、开关、版本），哪怕执行器本轮还没改为从表驱动，至少开关和准则引用立即可用。

**代码锚定**：见"断层 4"。R3 需求 1 完整 DSL 执行器本轮不做，仅建表 + seed。

**验收标准**：

1. The 数据库 shall 新增表 `qc_rule_definitions`：`id / rule_code(unique) / severity(blocking|warning|info) / scope(workpaper|project|consolidation|submit_review|sign_off|export_package|eqcr_approval) / category / title / description / standard_ref(JSONB array) / expression_type(python|jsonpath|sql|regex) / expression(text) / parameters_schema(JSONB) / enabled(bool default true) / version(int default 1) / created_by / created_at / updated_at`，alembic migration `round6_qc_rule_definitions_20260507.py`。
2. The 启动 seed `backend/data/qc_rule_definitions_seed.json` shall 含 22 条规则（QC-01~14 + QC-19~26），`expression_type='python'`、`expression` 为 Python dotted path（如 `app.services.qc_engine.SamplingCompletenessRule`），`standard_ref` 填入 CICPA 准则号（至少 QC-01~14 对应 CAS 1301 具体条款）。
3. The `QCEngine.run`（`qc_engine.py:736+`）shall 在运行前读取 `qc_rule_definitions WHERE enabled=true`，用 `rule_code` 交集过滤硬编码 `self.rules` 列表；`enabled=false` 的规则本轮**跳过不执行**（最小改动，不做 dotted path 加载）。
4. The `rule_registry` / `register_phase14_rules`（`gate_rules_phase14.py:475`）shall 同样在注册时 check `qc_rule_definitions.enabled`，`enabled=false` 的规则不 register_all。
5. The 前端 shall 新增只读页面 `/qc/rules`（权限 `role in ('qc','admin','partner')`），列出所有规则、准则引用、启用状态（只读，不提供编辑入口——编辑入口留 R3 实装）。
6. The 本轮 shall **不实装** `jsonpath / sql / regex` 执行器；`qc_rule_definitions` 支持该枚举以方便后续扩展，但若 `expression_type != 'python'` 的规则被 seed 或手工插入，启动时 warning log "R6 stub: non-python rule ignored"。
7. The 后端 shall 新增 `test_qc_rule_definitions_loader.py`，覆盖：seed 装载 22 条、`enabled=false` 跳过、非 python 类型 warning 但不崩。

### 需求 5：签字字段 legacy 字符串控制流清理

**用户故事**：作为一名后续维护者，我希望系统中关于"签字级别"只有 `required_order + required_role` 一套语义，`signature_level` 字段的字符串比较 `if signature_level == "level3"` 等旧逻辑不再影响控制流。

**代码锚定**：见"断层 5"。字段保留（R1 预留的向下兼容），只解耦控制流。

**验收标准**：

1. The `sign_service.py:170` `if record.signature_level == "level3"` 判断 shall 改为基于 `SignatureRecord.required_role == 'signing_partner' AND required_order == 3`（或等价语义），或在 `SignatureRecord` 上新增方法 `requires_ca_certificate() → bool` 封装该判断。
2. The `SignatureRecord.signature_level` 字段的 docstring/comment（`extension_models.py:48`）shall 更新为：`"""Legacy: 历史兼容字段（'level1/level2/level3/eqcr'），新代码禁止用于控制流；实际签字顺序见 required_order，角色见 required_role。"""`。
3. The 本轮 shall **新增**一个静态检查 `scripts/check_signature_level_usage.py`，grep `signature_level\s*==|signature_level\s*!=` 在 `backend/app` 下的出现次数，若 > 0（除 `extension_models.py` 字段定义外）则 exit 1；该脚本纳入 CI（见需求 7）。
4. The 本轮 shall **不删除** `signature_level` 字段本身（API 响应仍回字段以兼容前端旧调用），仅解耦控制流。
5. The 后端 shall 新增 `test_signature_level_decoupled.py`，断言 `sign_service.verify_signature` 在 `signature_level='eqcr' + required_role='signing_partner' + required_order=3` 时仍能触发 CA 证书校验分支（证明控制流不再看字符串）。

### 需求 6：通知铃铛挂载 + 死代码清理（三件合并）

**用户故事**：作为任何一个进系统的角色，我要在顶部看到通知铃铛（新消息有 badge），且系统里不应同时存在"界面上不可达的死页面"和"前端调用不存在的后端路径"。

**代码锚定**：见"断层 6、7"。三件合并处理，避免 R1/R2 漏掉单独成轮。

**验收标准**：

1. The `DefaultLayout.vue` shall 挂载 `NotificationCenter.vue` 到顶部导航（与 `#nav-review-inbox` 并列），通过 `ThreeColumnLayout.vue` 新增 `#nav-notifications` slot 实现（对齐 R2 需求 3 的架构决策）；SSE 实时更新走已就绪的 `event_bus._notify_sse`（`event_bus.py:287`），无需降级为轮询。
2. The `ThreeColumnLayout.vue` 顶部导航 shall 按顺序显示：复核收件箱 🔔 通知铃铛 🛡️ 独立复核 📊 EQCR 指标（后两者 EQCR 资格可见）。
3. The `ReviewWorkstation.vue` shall 被删除（grep `router/index.ts` 零命中，确认仍是死代码），对齐 R1 需求 1 验收标准 7；**若 R1 实施时已删除**则本项自动 PASS。
4. The `backend/app/routers/pbc.py` 和 `confirmations.py` 两个空壳 shall 加 `@deprecated` 标记 + 响应体 `{"status": "developing", "items": [], "note": "Feature not implemented; scheduled for R7+"}`；路由保留避免前端 404 冲击，但响应结构明确告知"未实装"。
5. The `ThreeColumnLayout.vue:333` 的 `{ key: 'confirmation', ..., maturity: 'pilot' }` shall 改为 `maturity: 'developing'`，避免误导用户"函证功能可用"。
6. The 前端 `apiPaths.ts:523-538` 的 `archive.archive` 常量与实际后端编排端点（需求 1）对齐，删除任何指向 `/api/archive/{pid}/archive`（不存在）的旧常量。
7. The 前端 shall 新增 `test/dead-link-check.spec.ts`（或 Node 脚本）：扫描 `apiPaths.ts` 所有端点常量，断言均能在 `backend/app/router_registry.py` 注册树中找到同名 prefix；找不到则 exit 1，该脚本纳入 CI。

### 需求 7：守门机制（CI 骨架 + seed schema + hypothesis 入 requirements + pre-commit）

**用户故事**：作为整个开发团队（合作者、下一轮实装者、未来维护者），我希望基础的"代码规范守门"自动跑在提交流程中，避免 R5 跨轮复盘那种"seed 文件 71 处 JSON 坏了谁都没发现"的系统级事故。

**代码锚定**：见"断层 8、10"。本轮只建**最小 CI 骨架**，不搞完整流水线。

**验收标准**：

1. The 项目根目录 shall 新增 `.github/workflows/ci.yml`，触发条件 `push / pull_request to master`，4 个并发 job：
   - `backend-tests`（`python -m pytest backend/tests/ --ignore=backend/tests/integration --ignore=backend/tests/e2e -x --tb=short`）
   - `backend-lint`（`ruff check backend/` + `python scripts/check_signature_level_usage.py`）
   - `seed-validate`（跑下方需求 2 的 seed 加载测试）
   - `frontend-build`（`npm ci && npm run build` in `audit-platform/frontend`）
2. The `backend/requirements.txt` shall 追加 `hypothesis==6.152.4`（R5 已安装但未写入 requirements），并跑一次 `python -m pytest backend/tests/test_phase0_property.py backend/tests/test_phase1a_property.py backend/tests/test_remaining_property.py backend/tests/test_production_readiness_properties.py` 确认 101 个属性测试通过。
3. The 项目根目录 shall 新增 `.pre-commit-config.yaml`，两个 hook：`check-json`（官方 `pre-commit-hooks.check-json`，对 `backend/data/*.json` 生效）+ 自定义 `json-template-lint`（跑下方需求 4）。
4. The 后端 shall 新增 `scripts/validate_seed_files.py`：
   - 加载 `audit_report_templates_seed.json` / `report_config_seed.json` / `note_templates_seed.json` / `wp_account_mapping.json` / `independence_questions_annual.json` / `qc_rule_definitions_seed.json`（需求 4 产物）
   - 每个 seed 对应一个 `Pydantic BaseModel` schema（schema 文件 `backend/data/_seed_schemas.py`），加载失败退出码 1
5. The `backend/tests/conftest.py` shall 新增一个 `test_all_models_registered`：反射遍历 `backend/app/models/` 下所有 `.py`，断言 `Base.metadata.tables` 已注册每个 `class ... (Base)` 定义的 `__tablename__`；避免 R5 那次"漏导入 15 个模型包"的事故重演。
6. The 本轮 shall **不引入** `mypy / bandit / coverage` 等更重工具，保持 CI 最小集；Round 7+ 再扩。
7. The `README.md` 根目录 shall 新增 `CI / pre-commit` 使用说明章节（开发者如何本地跑 `pre-commit install` + CI 失败时的排查路径）。

---

## UAT 验收清单（手动验证，不入 tasks 编排）

1. **需求 1**：
   - 启动 `start-dev.bat`，登录 admin/admin123。
   - 开 DevTools Network，走完 `/projects/:pid/archive` 向导，确认只有一次 `POST /api/archive-orchestrator/...` 调用；路径 B 调用时服务端 response header 包含 `Deprecation: version="R6"`。
   - 故意让某张底稿 `review_status=level1_passed`（gate 失败），confirm 归档按钮阻断并展示失败项列表。
   - 归档成功后，手动再点一次归档按钮，服务端幂等返回同 archive_id（不重新打包）。

2. **需求 2**：
   - 同一 project 在合伙人 PartnerDashboard 的签字前 8 项，与 PM 在 ProjectDashboard 触发 `sign_off` gate evaluate 的结果对比，`passed/failed` 集合完全一致。
   - 修改某条底稿 `review_status` 打破 gate，两个入口都立即变红（非隔离的 SELECT）。

3. **需求 3**：
   - 助理对一张底稿 cell 创建 `ReviewConversation` → 发消息 → 复核人点"提升为工单"，确认 `IssueTicket.source='review_comment'`；第二次点击拒绝重复创建。
   - 批注未解决时关闭会话，服务端返回 `CONVERSATION_HAS_OPEN_RECORDS`，前端给 ElMessage 错误。

4. **需求 4**：
   - 进 `/qc/rules`，看 22 条规则列表与准则引用。
   - DB 里手工 `UPDATE qc_rule_definitions SET enabled=false WHERE rule_code='QC-14';`，跑一次底稿 QC 检查，确认 QC-14 未出现在 findings。

5. **需求 5**：
   - 跑 `python scripts/check_signature_level_usage.py`，exit 0（项目仅剩字段定义的一处引用）。
   - 合伙人 level3 签字时 CA 验证分支仍触发（manifest 中 `certificate_required=true`）。

6. **需求 6**：
   - 顶部能看到铃铛 + badge；新通知进来 SSE 实时加 1；点击铃铛展开列表跳转到 related_object。
   - 全局 grep `ReviewWorkstation` 零命中。
   - 访问 `/api/projects/:pid/pbc`，后端返回 `{status: "developing", items: [], note: ...}`。

7. **需求 7**：
   - 推一个故意坏的 JSON（如 `audit_report_templates_seed.json` 首字符改为 `{`+非法字符），`git commit` 时 pre-commit 阻止。
   - 改 `sign_service.py` 加一行 `if x.signature_level == "level1": pass`，本地跑 `python scripts/check_signature_level_usage.py`，exit 1。
   - `python -m pytest backend/tests/test_phase0_property.py backend/tests/test_phase1a_property.py` 跑通 101 个属性测试（首次正式入 CI 跑，无 skip）。

---

## 起草后代码锚定交叉核验

**已 grep 核对**（起草前后两次执行，减少带入错误假设）：

| 假设 | grep 命令 | 核验结果 |
|------|----------|----------|
| 三套归档服务存在 | `archive_project` in `backend/app/services/**` | ✅ wp_storage / private_storage / data_lifecycle 三处命中 |
| 前端 `/api/archive/{pid}/archive` 端点实装 | `router_registry.py` 无 `/archive` 前缀 + `routers/archive*.py` 不存在 | ✅ 确认为"前端调用后端未实装"的漂移 |
| 就绪检查三套 | `class.*ReadinessService` + `sign-readiness` + `archive-readiness` | ✅ gate_engine + SignReadinessService + ArchiveReadinessService 三处并存 |
| ReviewConversation 仍被使用 | `ReviewConversation` in backend | ✅ 3 个 service 文件 + 1 个 router 仍活跃 |
| `signature_level == "level3"` legacy 判断 | `signature_level\s*==` | ✅ `sign_service.py:170` 一处命中 |
| NotificationCenter 未挂 | `NotificationCenter` in `layouts/*.vue` | ✅ 零命中 |
| ReviewWorkstation 死代码 | `ReviewWorkstation` in `router/index.ts` | ✅ 零命中（已删除文件或未注册） |
| `qc_rule_definitions` 表不存在 | `qc_rule_definitions` in `backend/app/models/**` | ✅ 零命中 |
| `.github/workflows` / `pre-commit` 缺失 | `fileSearch` | ✅ 零命中 |
| `hypothesis` 不在 requirements.txt | grep `hypothesis` in `backend/requirements*.txt` | ✅ 零命中（但 R5 已本地安装） |
| `pbc.py` / `confirmations.py` 空壳 | `readFile pbc.py` | ✅ `return []` 确认 |
| `ThreeColumnLayout` 有 `#nav-*` slots | grep `template #nav-` | ✅ `#nav-review-inbox` + `#nav-eqcr` 已有模式可复用 |
| `SignatureRecord.signature_level` 仍是 String(20) | `extension_models.py:48` | ✅ 确认字段为字符串 |
| `required_order` / `required_role` 新语义 | `extension_models.py:51+` | ✅ R1 新增且 R5 已使用到 order=4（eqcr） |
| `IssueTicket.source_ref_id` 字段名 | `wp_review_service.py:292` | ✅ 实装已用 source_ref_id，需求 3 已对齐 |
| SSE 推送基础设施 | `event_bus.py:287 _notify_sse` | ✅ 已就绪，需求 6 无需降级 |
| `IssueSource.review_comment` 枚举已预留 | `phase15_enums.py:64` | ✅ R1 一次性预留 11 值 |
| `ReviewCommentStatus` 枚举 | `workpaper_models.py:421` | ✅ ReviewRecord.status 走该枚举，需求 3 `status != 'resolved'` 判断可行 |
| `archive_checklists` 仅有 project_id 索引无唯一约束 | `collaboration_models.py:421` | ✅ 幂等方案改走应用层 SELECT，不依赖 DB 约束 |

**未 grep 但假设存在的项**（design 阶段必须核对）：

- `archive_checklists` 表已确认有 `project_id` 索引（`collaboration_models.py:421`），但 `status` / `created_at` 字段 design 阶段需再核对
- `GateType.export_package` / `sign_off` 已注册 → `gate_engine.py:59` 已确认
- `ReviewCommentStatus.resolved` 枚举值 design 阶段核对（需求 3 AC2 依赖该状态判断）
- KAM / 独立性确认写 `wizard_state` 的字段名（`kam_confirmed` / `independence_confirmed`）design 阶段核对（`partner_service.py:228-249`）

---

## 变更日志

- v1.0 (2026-05-06) Round 6 首稿。主题"跨角色系统级优化"，7 个需求聚焦门面收敛 + 守门机制 + 死代码清理。明确不在本轮范围 6 项，UAT 清单 7 组。

## 索引

- 本轮依赖 Round 1 需求 3 / 5、Round 2 需求 3、Round 3 需求 1（均已起草，部分实装中）。实施时若前置未到位，本轮相关子项降级为"先搭骨架"由 R1/R2/R3 后续复用。
- 实施顺序建议：先跑需求 7（CI 骨架打底），再需求 5 / 6（死代码清理）低风险先行，最后需求 1 / 2 / 3 / 4（涉及服务重构）。
