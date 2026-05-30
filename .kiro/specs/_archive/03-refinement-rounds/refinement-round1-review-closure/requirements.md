# Refinement Round 1 — 复核闭环与合规文档一体化

## 起草契约

**起草视角**：本文档由"某大型会计师事务所资深合伙人"视角撰写——长期负责事务所系统开发，深度掌握底稿、复核、签字、归档、平台搭建等一线实操细节。分析落脚点是**前后端联动**与**用户真实使用效果**，不做空泛的技术重构。

**迭代规则**：本文档是 PDCA 循环中的一次产出。规则详见 [`README.md`](./README.md)，概要如下：

- 每一轮（Round）分析 → 三件套（requirements/design/tasks）→ 实施 → 复盘 → 下一轮新需求
- 下一轮复盘是**全量重扫**（不只看上一轮修了什么），发现新的断层点再成稿
- 合伙人认为"可改进项已穷尽"时才终止迭代（参见 README 中的"终止条件"）

**本文是 Round 1**，起草时系统刚从 production-readiness spec 收官。

## 复盘背景（合伙人视角）

系统从 production-readiness spec 收官后，技术栈、门禁引擎、属性测试都已到位。但以资深合伙人做过几轮"走一遍真实项目流程"的设想后，发现**用户侧的核心体验断层集中在"复核—签字—归档"这条链**上，而不是还缺功能模块：

1. **复核入口分裂**：`ReviewInbox.vue`（有路由，批量通过/退回，**无** AI 预审）与 `ReviewWorkstation.vue`（三栏 + AI 预审 + 键盘快捷键，**路由未注册**，是死代码）同时存在。复核人进入系统后只能用弱版本 Inbox，强版本的 Workstation 无人能到达。
   - 证据：`audit-platform/frontend/src/router/index.ts` 第 113-117 行只注册 `ReviewInbox`，全文 grep `ReviewWorkstation` 零命中。
   - 体验：复核人面对"50 个底稿全选批量通过"按钮时，实际上没人会用——因为看不到底稿内容。Workstation 才是真正的复核工作台，却被废弃了。

2. **复核意见不可追踪**：复核意见（`review_conversations`）和问题工单（`issues`）是平行体系。复核人写了"这里差异需要解释"，系统**不会**自动生成一张可追踪的整改工单，也不会在底稿上留下红点标记。编制人下次进底稿时也不知道哪里要改。
   - 证据：`backend/app/routers/issues.py` 的 `source` 枚举仅 `L2/L3/Q`，没有 `review_comment` 来源；`review_conversations` 服务与 `issue_ticket_service` 无交叉调用。

3. **三套就绪检查结论可能矛盾**：
   - `gate_engine` 三个 gate：`submit_review` / `sign_off` / `export_package`（QC-19~26 + 一致性 + 错报超限）
   - `qc_dashboard.archive-readiness`（归档前检查）
   - `partner_dashboard.sign-readiness`（合伙人签字前 8 项检查）
   
   三处逻辑分散在不同 service，条件范围不完全重合，合伙人看到 sign-readiness 全绿却在真正调用 `sign_off` gate 时被阻断——因为 gate 的 QC-25/26 没进 readiness 清单。

4. **签字流程没有终点**：`PartnerDashboard` 有"签字前检查"弹窗，但检查通过后**没有下一步签字按钮**。`POST /api/signatures/sign` 路由存在，前端 `SignatureManagement` 页面也存在（挂在 `extension/signatures`），但二者未与 `PartnerDashboard.checkSign` 弹窗串联。合伙人看完 8 项检查后无法就地签字。
   - 证据：`PartnerDashboard.vue` checkSign 函数 233-241 行仅 `showSignDialog = true` 后结束，弹窗末尾无签字确认按钮。

5. **三级签字无顺序约束**：`SignatureRecord.signature_level` 字段接受 `level1/level2/level3` 任意字符串。系统不强制"先一级复核人签，再二级，再合伙人"，也不记录每一级所需待签人。
   - 证据：`backend/app/models/extension_models.py` 47-50 行仅 `String(20)`，无状态机。

6. **PBC 与函证是空壳但已对外暴露**：`pbc.py` 和 `confirmations.py` 两个路由各 15 行，`list_xxx` 返回 `[]`。记忆里标为"production-readiness 已注册路由"，实际是**占位**，业务价值为零。前端也无相应页面，合伙人点进"函证管理"会看到 404。这在真实项目里是致命缺陷——外勤 70% 的时间花在 PBC 和函证上。

7. **归档入口三重并存**：
   - `wp_storage.archive_project`（按项目锁底稿）
   - `private_storage.archive_project`（锁 + 推云 + 清本地）
   - `data_lifecycle.archive_project`（软删除可恢复）
   
   三个端点语义不同但前端只有一个"归档"按钮入口，无人知道按下去发生了什么。

8. **三级签字文档缺失**：《审计质量控制准则》第 1121 号要求留存项目组长、项目经理、合伙人三级签字证据；系统生成的归档包里没有签字流水页。

## 本轮范围

Round 1 一次性修复"复核—整改—签字—归档"的闭环断点与合规文档缺口。不扩散到别的领域（PBC/函证留给 Round 2，新人上手留给 Round 3）。

## 需求列表

### 需求 1：合并 ReviewInbox 与 ReviewWorkstation 为单一"复核工作台"

**用户故事**：作为一级/二级复核人，我希望进入系统后有**唯一**的复核入口；既能看到批量视图（选中多张通过），又能一张一张切换查看底稿差异、AI 预审、写复核意见。

**代码锚定**：后端 `ReviewInboxService.get_inbox(user_id, project_id=None)` 已支持全局和单项目两种入口（`backend/app/services/pm_service.py:26`），本需求不新增后端端点，只做前端合并。

**验收标准**：

1. When 我从顶部导航点击"复核收件箱"，the 系统 shall 进入新的合并页 `ReviewWorkbench.vue`（保留路由 `/projects/:projectId/review-inbox` 和全局 `/review-inbox`，组件替换）。
2. The 页面 shall 默认是**三栏视图**：左栏队列（含筛选：项目/循环/是否退回重提/提交人）、中栏底稿预览（嵌入只读版 `WorkpaperEditor` 或快照截图）、右栏 AI 预审 + 复核意见输入。
3. When 我在队列左上角点击"切换批量模式"，the 页面 shall 切到表格视图，保留 `ReviewInbox` 现有的多选+批量通过/退回能力，批量时 AI 预审不阻断。
4. The AI 预审结果 shall 带 severity 分级（blocking/warning/info），blocking 存在时"通过"按钮禁用并提示"请先处理 N 项阻断问题"。
5. When 我按 Ctrl+Enter，the 系统 shall 触发"通过"；Ctrl+Shift+Enter 触发"退回"；↓/↑ 切换队列下一个/上一个。
6. When 我处理完一张底稿后，the 系统 shall 自动选中队列下一项（连续复核不断流）。
7. The 旧的 `ReviewWorkstation.vue` shall 被删除，避免死代码迷惑后续维护者。

### 需求 2：复核意见自动生成可追踪工单

**用户故事**：作为项目经理，我希望复核人写下的每条意见都自动变成一张可跟踪工单，编制人在底稿上能看到红点，整改完成后意见状态自动同步。

**代码锚定与系统选型**：复核批注目前并存两套：`ReviewRecord`（单行批注，绑定 wp_id + cell_reference，见 `wp_review_service.py:62`）和 `review_conversations`（多轮对话，跨对象，见 `review_conversation_service.py`）。**本需求选定 `ReviewRecord` 作为复核意见→工单的转换源**（单行批注直接对应一条整改项），`review_conversations` 保留用于复核人与编制人的后续讨论。红点显示统一用 `ReviewRecord.cell_reference`，不使用 `CellAnnotation`。

**验收标准**：

1. When 复核人在复核工作台提交"退回"并附意见，the 系统 shall 同时创建 `ReviewRecord` 和自动创建 `IssueTicket`：`source='review_comment'`、`related_object_type='workpaper'`、`related_object_id=wp_id`、`cell_ref=ReviewRecord.cell_reference`、`source_ref_id=ReviewRecord.id`（建立双向关联）。
2. The `IssueTicket.source` 枚举 shall 一次性扩展为 5 轮共享的完整值集：`L2 | L3 | Q | review_comment | consistency | ai | reminder | client_commitment | pbc | confirmation | qc_inspection`（R1 一次迁移到位，避免后续轮多次迁移，依据 README "数据库迁移约定"第 4 条），前端 `IssueTicketList.vue` 的来源筛选器按本轮实际用到的 `review_comment` 新增，其余 source 由各自轮次补 UI。
3. When 编制人打开被退回的底稿，the 编辑器 shall 在对应单元格显示红点（读取 `ReviewRecord.cell_reference` 列表），点击红点弹出意见全文与关联工单状态。
4. When 编制人将工单置为 `pending_recheck`，the 关联的 `ReviewRecord.reply_text` 自动追加"已整改，请复验"记录（避免在两套系统中重复维护）。
5. When 复核人在工单详情点击"复验通过"，the 系统 shall 同时关闭工单、把关联 `ReviewRecord.status` 置为 resolved，并在底稿 `review_status` 从 `level1_rejected` 回退至 `pending_level1`。
6. The `IssueTicketList.vue` shall 支持点击行跳转到底稿对应 cell（router query `?cell=<cell_ref>`）。
7. **联动守卫**：创建 IssueTicket 失败不阻断 ReviewRecord 写入（避免复核动作被工单服务故障拖死），但 `event_handlers` 必须订阅 `REVIEW_RECORD_CREATED` 做补偿重建，防止漏单。

### 需求 3：三份"就绪检查"合一为统一门禁面板

**用户故事**：作为合伙人，我希望签字前看到的"就绪检查"结论与 `gate_engine` 真正执行签字时的判断**完全一致**，不会出现"检查全绿、真签又被阻断"的情况。

**验收标准**：

1. The `SignReadinessService.check_sign_readiness` shall 被重构为门面，内部**实际调用** `gate_engine.evaluate(gate_type="sign_off", ...)`，把所有 gate rule findings 映射为 8 项检查的子项（保持现有 8 项类目的兼容 UI）。
2. The `ArchiveReadinessService.check_readiness` shall 同理改为门面，调用 `gate_engine.evaluate(gate_type="export_package", ...)`。
3. When gate 新增规则（如未来 QC-27），readiness 弹窗 shall 自动显示新规则的 findings，无需前端改代码。
4. The readiness 响应 schema shall 统一：`{ready: bool, groups: [{name, status, findings: [{severity, message, location, action_hint}]}], gate_eval_id: uuid}`。
5. The `gate_eval_id` shall 在合伙人签字时作为幂等键提交到 `POST /api/signatures/sign`，后端校验"gate_eval_id 对应的评估结果仍为 PASS 且未过期（5 分钟内）"，否则拒绝签字返回 `GATE_STALE` 错误码。
6. The 前端 PartnerDashboard 签字弹窗 shall 用统一的 `<GateReadinessPanel>` 公共组件展示，groups 折叠展开、findings 支持点击跳转到对应底稿/错报/附注。
7. **新增 AJE→错报联动检查项**：`sign_off` gate 必须新增规则 `UnconvertedRejectedAJERule`：扫描 `Adjustment.review_status='rejected'` 且未关联到 `UnadjustedMisstatement` 的 AJE 组，findings 为 warning 级（建议转错报），阻断级由质控合伙人评估。后端 `misstatement_service.create_from_rejected_aje` 已实现但前端入口缺失，本需求补一键转换按钮到 `Adjustments.vue` 与 readiness 面板 finding 的 action_hint。
8. **新增级联完整性检查项**：`sign_off` / `export_package` gate 新增规则 `EventCascadeHealthRule`：检查最近 1 小时内的 `WORKPAPER_SAVED / REPORTS_UPDATED` 事件是否全部被 `event_handlers` 消费完成（无 pending 或 failed 状态）。未完成时阻断，提示"下游更新未同步，请等待 N 秒后重试"。

### 需求 4：合伙人签字流水线（三级顺序 + 就地签字按钮）

**用户故事**：作为合伙人，我希望在签字前检查弹窗里直接完成签字，并且看到一级、二级、三级签字的顺序和当前等待谁。

**验收标准**：

1. The `SignatureRecord` 模型 shall 新增 `required_order: int`（1/2/3，强制顺序）、`required_role: str`（project_manager/qc_reviewer/partner）、`prerequisite_signature_ids: UUID[]`。
2. The `POST /api/signatures/sign` shall 校验"所有前置 signature 必须已 signed 且 verified"，否则返回 `PREREQUISITE_NOT_MET`。
3. The `GET /api/signatures/workflow/{project_id}` shall 新增，返回 `[{order, role, required_user_id, status: waiting|ready|signed, signed_at, signed_by}]`。
4. When 合伙人在签字前检查弹窗中看到 `ready:true` 且轮到自己签，the 弹窗 shall 显示"立即签字"按钮，点击后在同一弹窗内弹出签字确认（密码/短信二次验证，现有 `SignService.sign` 接口），签字成功后 toast + 关闭弹窗 + 刷新 PartnerDashboard 的待签字列表。
5. The `PartnerDashboard.sign-list` 卡片 shall 显示"已 2/3 级，待你签"等简明状态文字，不再只显示完成率。
6. The 签字记录 shall 全程审计到 `audit_logger_enhanced`，包含 IP、UA、`gate_eval_id`、是否复用了最近的评估结果。
7. **签字状态机联动**（分两种情形）：
   - 无 EQCR 项目（仅三级签字 order=1~3）：最高级签完后 `SignService.sign` 同事务切 `AuditReport.status: review → final`
   - 启用 EQCR 项目（R5 后 order=1~5，EQCR=4、归档签字=5）：order=3 签完不切 status（仍 review），等待 EQCR；order=4 EQCR 签完切 `review → eqcr_approved`（R5 落地）；order=5 归档签字完切 `eqcr_approved → final`
   - 切态失败时签字动作整体回滚；切态成功发 `Notification(type='report_finalized')` 通知项目组

### 需求 5：归档三入口收敛为项目级"归档向导"

**用户故事**：作为项目负责人，我希望看到唯一清晰的"归档"按钮，点下去走一个向导（就绪检查 → 打包 → 归档到云 → 锁定）。

**验收标准**：

1. The 三个后端归档端点 shall 合并为单一编排接口 `POST /api/projects/{id}/archive/orchestrate`，请求体 `{scope: "final", confirm_gate_pass: bool, push_to_cloud: bool, purge_local: bool}`。
2. The 编排接口 shall 串行执行：`gate_engine.evaluate("export_package")` → 通过则 `wp_storage.archive_project`（锁底稿） → `private_storage.push_to_cloud`（若请求） → `data_lifecycle.archive_project_data`（标记软删除可恢复）→ 返回 `archive_id` 与打包产物 URL。
3. The 旧的 `wp_storage.archive_project` / `private_storage.archive_project` / `data_lifecycle.archive_project` 三个直接端点 shall 保留但加 `deprecated=True` 响应头与 warning log（向后兼容），前端不再调用。
4. The 前端 shall 新增 `ArchiveWizard.vue`（挂 `/projects/:projectId/archive`），分 3 步：就绪检查 → 归档选项（是否推云、是否清本地）→ 确认执行。
5. When 用户在第 1 步看到 gate 失败项，the 向导 shall 禁用"下一步"按钮并列出阻断项的跳转链接。
6. When 用户点击"确认归档"，the 前端 shall 显示进度条（WebSocket 或轮询 `archive_job_status` 每 3s），成功后跳转到归档详情页，失败时保留断点供重试。
7. **断点续传定义**：失败时后端 shall 在 `archive_jobs` 表记录 `last_succeeded_section`（基于需求 6 的 `archive_section_registry` 章节前缀），"重试"按钮从下一章节开始执行，避免整个打包重来；章节级失败不影响已完成章节的哈希记录。

### 需求 6：归档包自动生成三级签字流水与合规封面

**用户故事**：作为质量控制合伙人/同行复核人员，我希望打开归档包就能看到项目组长、项目经理、签字合伙人三级签字页，以及合规所需的封面（项目信息、审计意见类型、签字日期）。

**验收标准**：

1. The 归档包 ZIP shall 采用"插件化章节"结构（依据 README 跨轮约束第 6 条），R1 负责定义机制并占用前缀 `00~09`，后续轮（R3/R5）可追加各自章节：
   - `00-项目封面.pdf`（R1 本需求）
   - `01-签字流水.pdf`（R1 本需求）
   - `02-EQCR备忘录.pdf`（R5 需求 9，R1 不实现但预留）
   - `03-质控抽查报告.pdf`（R3 需求 4，R1 不实现但预留）
   - `10-底稿/`、`20-报表/`、`30-附注/`、`40-附件/`（现有）
   - `99-审计日志.jsonl`（R1 本需求追加导出）
2. The `00-项目封面.pdf` shall 包含：客户名/项目名/会计期间/审计意见类型/审计报告文号/签字日期/签字合伙人姓名。
3. The `01-签字流水.pdf` shall 列出三级签字的时间戳、签字人、签字方式（电子签 / 手写签 / 双重验证）、`gate_eval_id`、验证哈希；**章节模板应设计为可扩展**——R5 EQCR 签字加入流水后，签字流水 PDF 可直接多出一行而不改模板结构。
4. The 签字流水 PDF shall 用现有 `pdf_export_engine`（LibreOffice 转换）生成，模板存 `backend/data/archive_templates/signature_ledger.docx`。
5. When 归档包被生成，the `ExportIntegrityService.persist_hash_checks` shall 记录每个章节文件的 SHA-256 到 `evidence_hash_checks` 表（现有机制，`export_integrity_service.py:53`）；后续任何下载/访问时调用 `verify_package` 做校验，发现不一致记 `integrity_check_failed` 事件。下载时**不重新计算哈希**（昂贵），只在可疑情况（归档包被移动/复制后）显式触发校验。
6. The 签字流水 PDF shall 包含"本归档包由 审计平台 v{version} 于 {time} 自动生成，SHA-256: {hash}"水印。
7. The 归档编排服务 shall 提供 `archive_section_registry` 机制：各轮通过 `register_archive_section(order_prefix, filename, generator_func)` 注册自己的章节生成器，归档时按前缀排序拼装。

### 需求 7：PBC 与函证占位路由改为"空页面守卫"或补全最小 MVP

**用户故事**：作为外勤项目经理，我不希望点击函证/PBC 入口跳到 404 或空白列表；如果功能没做好，至少要提示"开发中"并引导到别处。

**验收标准**（本轮二选一，推荐方案 A）：

**方案 A（推荐）——暂时隐藏入口**：
1. The `backend/app/routers/pbc.py` 与 `confirmations.py` shall 在路由注册时加 `include_in_schema=False`，OpenAPI 不暴露。
2. The 顶部导航/侧边栏 shall 彻底移除 PBC 与函证入口的直接链接，避免误导。
3. The 留档 TODO 到 Round 2 的"五环联动"专项，承诺在 Round 2 做 MVP（而不是再次推迟）。

**方案 B（可选）——最小 MVP**：
1. The `pbc.py` shall 新增 `POST /projects/{id}/pbc/items`、`PATCH /pbc/items/{id}`、`GET` 列表，模型复用现有 `issue_ticket_service` 但 `source='pbc'`。
2. 前端 `PBCListPage.vue` 以表格形态提供"催办 / 标记已收 / 关联到底稿"三个动作。
3. 函证同理最小 MVP（银行函证仅支持手工录入状态，自动发送留后期）。

实施时用户可选 A 或 B。如无明确偏好，默认采用 A。

## UAT 验收清单（手动验证，不生成编码任务）

以下项目必须在**所有编码任务完成后**由真人在浏览器走一遍，记录通过/失败截图。按 [`README.md`](./README.md) 的规则，UAT 不占 `tasks.md` 的 taskStatus 工作流：

1. 用 `admin/admin123` 登录，作为二级复核人，测试连续复核 10 张底稿的流畅度（队列自动切换、快捷键响应、无页面重载卡顿）。
2. 退回 3 张底稿并各写一条意见（含一条单元格级、两条底稿级），验证编制人账号进去能看到单元格红点、工单列表有 3 条新纪录、`source=review_comment` 筛选能过滤出来。
3. 合伙人账号打开 PartnerDashboard，逐个项目"签字前检查"，分别验证三种路径：
   - 全绿 → "立即签字"按钮可见并可签
   - 有阻断 → 按钮禁用、跳转链接能落到对应底稿/错报/附注
   - `gate_eval_id` 超过 5 分钟后签字 → 返回 `GATE_STALE`，提示重新检查
4. 按顺序走完三级签字（项目组长 → 项目经理 → 合伙人），验证"跳级签字"被拒（返回 `PREREQUISITE_NOT_MET`）。
5. 执行完整归档向导，打开 ZIP 包验证 `00-项目封面.pdf`、`01-签字流水.pdf`、SHA-256 水印存在；尝试再次下载，验证 `ExportIntegrityService` 记录了第二次下载哈希。
6. 验证 PBC/函证入口已按方案 A 从导航彻底移除（或按方案 B 有最小 CRUD）。

## 不在本轮范围

明确以下事项**不**在 Round 1 处理，避免任务溢出：

- PBC 与函证的完整 MVP（方案 B 只是占位选项，推荐留 Round 2）
- 五环数据联动（PBC→抽样→错报→报表）
- 新人引导、续审年度复用
- 协作深度（实时多人光标、版本合并）
- AI 实用化（RAG 知识库接入复核建议）
- 性能压测再跑（Round 2 统一做）

## 验收完成标志

本轮需求 1~7 的所有验收标准全部满足、上述 UAT 验收清单 6 项全部走完并记录结果后，Round 1 关闭。关闭后由合伙人视角启动 Round 2 的**全量复盘**（不只看本轮修复的东西，再从头把系统走一遍，找出新的断层点）。

## 变更日志

- v1.4 (2026-05-05) 一致性校对修正：
  - 需求 4 验收 7 签字状态机联动按"EQCR 启用"与"无 EQCR"两情形细化，避免 R5 启用后 order=4 误切 final
- v1.3 (2026-05-05) 合伙人第二轮深度复盘修正：
  - 需求 1 明示复用 `ReviewInboxService.get_inbox` 不新增端点
  - 需求 2 选定 `ReviewRecord` 为复核批注单一真源（`review_conversations` 保留用于讨论但不做源头），补联动守卫
  - 需求 3 新增 `UnconvertedRejectedAJERule`（AJE 被拒未转错报）和 `EventCascadeHealthRule`（级联完整性）两个 gate 规则
  - 需求 4 补签字最高级完成后自动切 `AuditReport.status` 到 final
  - 需求 5 补"章节级断点续传"机制定义
  - 需求 6 `ExportIntegrityService` 语义对齐：导出时记哈希、下载不重算、可疑时 verify
- v1.2 (2026-05-05) 跨轮交叉核验修正：
  - 需求 2 `IssueTicket.source` 枚举一次性预留全轮值集，避免后续多次迁移
  - 需求 6 归档包改为"插件化章节"机制（前缀 00~09 / 10 / 20 / 99 分区），为 R3/R5 预留章节位
  - 依赖 README v2.2 的"跨轮依赖矩阵"和"数据库迁移约定"两节
- v1.1 (2026-05-05) 将起草视角与 PDCA 迭代规则整合为"起草契约"章节；需求 8 拆为独立的 UAT 验收清单章节（不再占需求编号）；UAT 条目从 5 条扩到 6 条，增加"三级签字顺序验证"。
- v1.0 (2026-05-05) 合伙人视角首轮起草，基于 production-readiness 完成后状态。

## 补充需求（v1.5，长期运营视角）

以下 3 条需求由合伙人第三轮深度复盘新增，聚焦"**长期运营 + 监管问责**"场景，是 Round 1 收官必须补齐的硬缺口（签字留痕、独立性、保留期）。

### 需求 9：审计日志真实落库 + 不可篡改

**用户故事**：作为签字合伙人，我被监管问"某月某日为什么 gate 决定放行"时，必须能从系统里调出原始日志；进程重启、服务器迁移都不能丢。

**代码锚定**：`backend/app/services/audit_logger_enhanced.py:34` 的 `log_action` 只 `append` 到内存 `self._recent_actions` 列表，**从未落库**。所有"审计日志已记录"的承诺都是幻觉。

**验收标准**：

1. The 数据库 shall 新增 `audit_log_entries` 表：`id(UUID) / ts(带时区 datetime) / user_id / session_id / action_type / object_type / object_id / payload(JSONB 脱敏) / ip / ua / trace_id / prev_hash(str) / entry_hash(str)`。
2. The `log_action` shall 同步写 DB（非 fire-and-forget，写失败必须返回错误让调用方知情）；内存缓存作为查询加速，不作为权威来源。
3. The `entry_hash` shall 用 `sha256(ts + user_id + action_type + object_id + payload_json + prev_hash)` 计算，形成哈希链，任何篡改会断链可检测。
4. The `GET /api/audit-logs/verify-chain?project_id=&from=&to=` shall 逐条校验哈希链完整性，返回第一条断链的 entry_id，供质控/EQCR 调用（R3 需求 12 会扩展规则化校验）。
5. The `payload` 写入前 shall 过 `export_mask_service.mask_log_payload` 脱敏：金额保留级次、客户名替换为 hash、身份证脱敏。
6. The 保留策略：项目签字后 10 年内不允许物理删除日志（与需求 11 的 10 年保留期保护联动）。
7. The 性能要求：`log_action` P95 < 50ms；支持 6000 并发写入（异步队列缓冲 + 批量写入兜底）。
8. **非必须**本轮实现**外部 WORM 存储**（如 S3 Object Lock），留 Round 6+ 级别的安全加固。

### 需求 10：独立性声明结构化

**用户故事**：作为合伙人，每个项目签字前我必须完成独立性声明（含家庭成员证券持有情况、近期服务历史、客户关系等），系统现在只能勾个框是假合规。

**代码锚定**：`project.wizard_state.independence_confirmed` 仅 bool（`partner_service.py:250` / `qc_dashboard_service.py:407`）。

**验收标准**：

1. The 数据库 shall 新增 `independence_declarations` 表：`id / project_id / declarant_id(人员) / declaration_year / answers(JSONB: 20+ 问题答案) / attachments(JSONB: 证据文件 IDs) / signed_at / signature_record_id(关联 SignatureRecord) / reviewed_by_qc_id / reviewed_at`。
2. The 系统 shall 预置 20 条独立性问题模板（按《审计师独立性准则》整理），存 `backend/data/independence_questions.json`，UI 按问题渲染表单（yes/no/多选/文本 + 附件上传）。
3. The 项目组核心成员（`signing_partner / manager / qc / eqcr`）均需单独提交声明，**缺一个都阻断 sign_off gate**；扩展 `UnconvertedRejectedAJERule` 同级别新增 `IndependenceDeclarationCompleteRule`。
4. The 声明提交 shall 触发一条 `SignatureRecord(object_type='independence_declaration')` 留痕，满足"签字+留痕"双重要求。
5. When 独立性问题出现"存在潜在利益冲突"答案，the 系统 shall 自动通知事务所首席风控合伙人复核，该声明状态为 `pending_conflict_review`。
6. The `qc_dashboard_service.py:407` 的 `independence_confirmed` JSON bool shall 改为从 `independence_declarations` 读取（向后兼容：旧项目若只有 bool，视为 `legacy_confirmed` 类型仍算通过但打提醒徽章"升级为结构化声明")。
7. The 归档包 shall 在章节 `04-独立性声明/` 下按人员拆分独立 PDF（R1 章节化系统扩展，预留 04 给独立性）。

### 需求 11：项目 10 年保留期保护 + 关键合伙人轮换检查

**用户故事**：作为合伙人，我希望一旦项目签字归档，10 年内任何人都不能物理删除数据；同时系统要在我被指派到连续审计 5 年的客户时警示我需要轮换。

**验收标准**：

1. The `Project` 表 shall 新增 `archived_at: datetime | null / retention_until: datetime | null`（归档时 `retention_until = archived_at + 10 years`）。
2. The `data_lifecycle.purge_project_data` 端点 shall 硬校验 `now() < retention_until`，违反返回 403 `RETENTION_LOCKED`，错误附"还需保留 N 年 M 天"提示；admin 也不能绕过，仅事务所级"合规合伙人 + 首席风控合伙人"双签名 override。
3. The 新增 `partner_rotation_tracker` 表 或复用 `project_assignments` 扩展字段：按 `client_name + signing_partner_id + eqcr_id` 聚合近 N 年委派记录，提供 `GET /api/rotation/check?staff_id=&client_name=` 查询连续年数。
4. The `project_wizard` 新建项目选 signing_partner/eqcr 时 shall 自动查轮换规则：连续 4 年警告（下年需轮换）、连续 5 年及以上**阻断**（需合规合伙人 override，留痕 `rotation_overrides` 表）。
5. The 默认轮换上限 shall 可配置（上市公司 5 年 / 非上市 7 年），存 `system_settings.rotation_policy`。
6. The `Dashboard` admin 视角新增"轮换预警"卡片，列近半年需轮换的合伙人 + 客户。
7. The 轮换规则违反、retention 保护触发均进入需求 9 的审计日志，哈希链留痕。

## 变更日志（续）

- v1.5 (2026-05-05) 长期运营视角增强（不破坏既有需求编号）：
  - 新增需求 9：审计日志真实落库 + 哈希链防篡改（修复 audit_logger_enhanced 内存幻觉）
  - 新增需求 10：独立性声明结构化（替代单一 bool 标志）
  - 新增需求 11：10 年保留期保护 + 关键合伙人轮换检查
  - 归档章节系统新增前缀 04（独立性声明）
