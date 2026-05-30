# Refinement Round 5 — 独立复核（EQCR）视角（独立取证 + 反向检查 + 报告前一锤定音）

## 起草契约

**起草视角**：某大型事务所独立复核合伙人（Engagement Quality Control Review，EQCR / Concurring Partner / 项目质量控制复核人）。不参与项目执行、不带项目经理，专门在**签字报告出具前**做独立二次复核，目的是从外部视角抓漏洞、防 bias。这是继 Round 1（合伙人签字）、Round 2（PM 作战）、Round 3（质控抽查）、Round 4（助理日常）之后最后一轮。

**迭代规则**：参见 [`../refinement-round1-review-closure/README.md`](../refinement-round1-review-closure/README.md)。本轮 Round 5，起草时 Round 1~4 未完成。

## 复盘背景（EQCR 视角）

EQCR 不是"质控抽查"（Round 3）的重复，关键区别：

- **质控**：系统性、规则化、对全所项目抽样
- **EQCR**：个案性、判断化、对**特定高风险项目**在签字前做深度二次复核，聚焦**专业判断合理性**（重要性水平设定、会计估计、关联方、持续经营、审计意见类型）

以一名 EQCR 合伙人接手一个即将签字的项目走一遍，问题集中在：

1. **无 EQCR 专属工作台**：系统没有"作为 EQCR 我要看哪些东西"的页面。签字合伙人看 PartnerDashboard，项目经理看 ManagerDashboard（Round 2 新增），**EQCR 无入口**。
   - 证据：router/index.ts 无 `/eqcr/*` 路由；`SignatureRecord.signature_level` 有 level3 但无 EQCR 语义。

2. **无"独立取证"通道**：EQCR 想绕过项目组直接问客户核实某事项（比如大额关联交易背景），系统无专属沟通通道，只能借用项目组的沟通记录。
   - 证据：`ProjectProgressBoard` 的沟通记录归属项目组，非 EQCR。

3. **专业判断类事项无专项展示**：EQCR 重点看"**会计估计 / 关联方 / 持续经营 / 重要性 / 审计意见**"这 5 类判断，系统没把它们聚合。
   - 证据：`subsequent_events.py` 有期后事项，但会计估计、关联方未作为独立模块（关联方有 `related_party` 散在数据里但无专项看板）；`materiality_service` 有设定但无 EQCR 复核工作流。

4. **EQCR 意见无独立留痕**：EQCR 给出的意见如果与项目组不一致，需要留痕"EQCR 认为意见应调整为保留意见，但项目组坚持无保留；合议结论如下..."。`ReviewRecord` 无 EQCR 级别的 disagreement resolution 流程。
   - 证据：`review_records.review_level` 字段只有 int，无 disagreement 状态。

5. **报告前"一锤定音"流程缺失**：系统从 `sign_off` gate 直接到 `export_package`，中间没有 EQCR 独立审批步骤。
   - 证据：`gate_engine.py` 3 个 gate 里无 `eqcr_approval`。

6. **EQCR 独立取数能力缺失**：EQCR 想独立跑一遍"现金流量表补充资料勾稽"不依赖项目组结果，系统无"以 EQCR 身份重跑"按钮。
   - 证据：`cfs_worksheet_engine` 执行后结果归属项目，无影子计算通道。

7. **EQCR 工作量/耗时统计缺失**：根据准则，EQCR 需要记录独立复核小时数存档。`workhour_service` 无 `purpose='eqcr'` 分类。

8. **审计意见类型锁定机制缺失**：项目组可以在 `audit_report.opinion_type` 任意切换（无保留/保留/无法/否定），EQCR 一旦签字认可"保留意见"后，项目组**还能改回无保留意见**。
   - 证据：`audit_report.py` 第 146 行仅防止"final 状态回退到 review"，但意见类型变更无版本锁。

9. **EQCR 历史项目一致性**：同一客户连续 3 年的 EQCR 应该查上年 EQCR 意见，避免前后矛盾。系统无该能力。

10. **EQCR 结论无独立 PDF 留痕**：EQCR 完成复核后，应生成一份"独立复核备忘录"归档。系统归档包中无此章节。

## 本轮范围

Round 5 聚焦 EQCR 这个特定角色，补齐独立复核所需的全部工具。重点：独立视角、判断类事项聚合、意见不一致处理、报告前锁定、独立留痕。

## 需求列表

### 需求 1：EQCR 工作台页面

**用户故事**：作为 EQCR 合伙人，我进系统后有一个专属工作台，看到我负责独立复核的项目队列、每个项目的关键判断事项、我还需要做什么。

**代码锚定说明**：`ProjectAssignment.role` 是 `String(30)`（`backend/app/models/staff_models.py:101`），可直接加新值 `eqcr`；`AssignmentRole` 枚举也需扩展。按 README 跨轮约束第 2、4、7 条，新增 role 必须同步更新权限字典、SOD 规则、i18n 字典。

**验收标准**：

1. The `AssignmentRole` 枚举 shall 新增 `eqcr`；`assignment_service.ROLE_MAP / role_context_service._ROLE_PRIORITY / 前端 ROLE_MAP / composables/usePermission.ROLE_PERMISSIONS` **四处同步更新**（缺一即视为未完成）。
2. The 系统 shall 新增路由 `/eqcr/workbench` 和页面 `EQCRWorkbench.vue`，权限 `role in ('partner', 'admin') 且 project_assignment.role='eqcr'`。
3. The `sod_guard_service` shall 新增规则：同项目内 `role='eqcr'` 的人员不能同时担任 `signing_partner / manager / auditor`（依据 README 跨轮约束第 4 条）；违规在 `ProjectAssignment` 创建/更新时立即拒绝。
4. The 页面 shall 按项目分卡片展示：项目名、即将签字日、我的 EQCR 进度（未开始 / 进行中 / 已同意 / 有异议）、关键判断事项数（未复核/已复核）、距签字 X 天。
5. The 点击项目卡片 shall 进入 `EQCRProjectView`，内含下述判断类专项 Tab。
6. The 后端 shall 新增 `GET /api/eqcr/projects` 返回本人作为 EQCR 的项目列表；排序按签字日升序。

### 需求 2：判断类事项聚合看板

**用户故事**：作为 EQCR，我要在一个页面看完这 5 类专业判断：会计估计、关联方、持续经营、重要性水平、审计意见。

**代码锚定说明**：持续经营已有后端模型 `GoingConcernEvaluation / GoingConcernIndicator`（`backend/app/models/collaboration_models.py:379-407`），本轮直接复用，**不重复建模**。关联方当前只有 `workpaper_fill_service` 的关键词列表，无独立表，本轮作为最小建模新增。

**验收标准**：

1. The `EQCRProjectView` shall 新增 5 个 Tab：**重要性**、**会计估计**、**关联方**、**持续经营**、**审计意见**，每个 Tab 聚合相关数据并附"EQCR 复核结论"录入框。
2. **重要性 Tab**：显示 `materiality` 数据（整体重要性、实际执行重要性、明显微小错报阈值），对比上年/行业基准；EQCR 可点"认可"或"有异议"，异议必须附文字说明。
3. **会计估计 Tab**：抓取所有含"估计"关键词或 `wp_index.category='estimate'` 的底稿（长期资产减值、应收账款减值、递延税、存货跌价等），列出管理层估计值、审计复核结果、与上年变化。
4. **关联方 Tab**：本轮新增最小模型 `related_party_registry(id, project_id, name, relation_type, is_controlled_by_same_party, created_at)` 和 `related_party_transactions(id, project_id, related_party_id, amount, transaction_type, is_arms_length, evidence_refs)`；EQCR 可录入/查看。UI 以汇总表 + 明细表呈现，关联方数据本轮人工录入，Round 6+ 再做自动识别。
5. **持续经营 Tab**：**直接复用** `GoingConcernEvaluation / GoingConcernIndicator` 已有模型查询，只做 EQCR 视角的渲染与意见录入，**不新增表**。
6. **审计意见 Tab**：显示当前 `audit_report.status` 与 `opinion_type`、形成理由、各强调事项段、EQCR 对意见类型的评价。
7. 每个 Tab 底部提供"记录 EQCR 意见"入口，存 `eqcr_opinions` 表：`project_id / domain(materiality|estimate|related_party|going_concern|opinion_type) / verdict(agree|disagree|need_more_evidence) / comment / created_at / created_by`。

### 需求 3：EQCR 独立复核笔记

**用户故事**：作为 EQCR，我在复核过程中需要记录独立思考与推断（如"这笔关联交易定价可疑，需要进一步证据"），这些笔记不应进入项目组日常视线，但也要有留痕，必要时可分享给项目组。

**独立性边界说明**：EQCR 不直接对外联络客户（维持项目组作为对外单一入口的专业原则，避免信息传递混乱）。如需核实事项，通过签字合伙人或项目经理转达。本需求只做**内部独立笔记**。

**验收标准**：

1. The 后端 shall 新增 `eqcr_review_notes` 表，结构：`id, project_id, title, content(text), shared_to_team(bool default false), shared_at, created_by, created_at`。
2. The `EQCRProjectView` shall 新增 Tab"独立复核笔记"，EQCR 可增删改查。
3. 默认状态 shared_to_team=false，**项目组成员不可见**；EQCR 可单条点击"分享给项目组"切 shared_to_team=true。
4. 分享后笔记 shall 同步到 `Project.wizard_state.communications`（复用 R2 需求 5 的沟通记录体系），来源字段注明"EQCR 独立复核笔记"。
5. The EQCR 独立复核笔记在归档包中 shall **不独占章节**（归档章节 02 保留给 EQCR 备忘录，见需求 9），但会作为备忘录正文的附录之一引用。

### 需求 4：EQCR 独立取数通道（影子计算）

**用户故事**：作为 EQCR，我要独立跑一遍现金流量表补充资料、借贷平衡等核心勾稽，不依赖项目组结果。

**验收标准**：

1. The 后端 shall 新增 `POST /api/eqcr/shadow-compute`，请求体 `{project_id, computation: 'cfs_supplementary'|'debit_credit_balance'|'tb_vs_report'|'intercompany_elimination', params: {...}}`。
2. The 执行器 shall 从原始账套数据重新计算（不读项目组已存的结果），返回 EQCR 独立结果。
3. The 结果 shall 存 `eqcr_shadow_computations` 表，永久留痕用于事后争议。
4. The EQCR 可对比"项目组结果 vs 我的独立结果"，不一致自动红标。
5. The 影子计算 shall 限流（每项目每天最多 20 次）避免滥用。

### 需求 5：EQCR 新门禁阶段

**用户故事**：作为 EQCR，我希望项目组通过 `sign_off` gate 后，报告不能直接出，必须先经我 EQCR 审批。

**验收标准**：

1. The `gate_engine` shall 新增 `GateType.eqcr_approval`，位置在 `sign_off` 与 `export_package` 之间。
2. The 现有签字流水 workflow（Round 1 需求 4）shall 扩展：`order=1 项目组长 → order=2 项目经理 → order=3 签字合伙人 → order=4 EQCR → order=5 归档`；EQCR 未同意时 export_package gate 自动阻断。
3. The `POST /api/eqcr/projects/{project_id}/approve` shall 供 EQCR 调用，请求体 `{verdict: 'approve'|'disagree', comment: str, shadow_comp_refs?: UUID[], attached_opinion_ids?: UUID[]}`。
4. When `verdict='disagree'`，the 系统 shall 创建"EQCR 异议"记录，触发合议流程（项目合伙人+ EQCR + 质控合伙人合议），合议结论记 `eqcr_disagreement_resolutions`。
5. The EQCR 批准记录 shall 计入签字流水 level=EQCR，归档包签字流水页显示完整。

### 需求 6：审计意见类型锁定机制

**用户故事**：作为 EQCR，一旦我认可项目组出"保留意见"，项目组就不能再偷偷改回无保留。

**代码锚定与状态机收敛**：`AuditReport.status` 已有状态机 `draft→review→final`（`audit_report_service`），`final` 不可回退至 `review` 且不允许修改段落（`audit_report.py:129-158`）。按 README 跨轮约束第 3 条，**不新增 `opinion_locked_at` 平行字段**，改为扩展状态机新增 `eqcr_approved` 态。

**验收标准**：

1. The `ReportStatus` 枚举 shall 在 `review` 和 `final` 之间新增 `eqcr_approved` 态：`draft → review → eqcr_approved → final`。
2. When EQCR 调用 `POST /api/eqcr/projects/{project_id}/approve`（需求 5），the 系统 shall 把审计报告从 `review` 切至 `eqcr_approved`；切态后 `opinion_type` 和段落内容均不可改（扩展现有 `final` 锁定规则到 `eqcr_approved`）。
3. When 项目组尝试修改 `opinion_type` 或段落且状态为 `eqcr_approved` shall 返回 403 `OPINION_LOCKED_BY_EQCR`。
4. The EQCR 可通过 `POST /api/eqcr/projects/{project_id}/unlock-opinion` 显式回退到 `review` 态，必须附文字说明；回退操作记 `audit_logger_enhanced`。
5. The 签字合伙人完成签字后状态切至 `final`（现有逻辑延伸），`final` 下所有人都不能改。
6. The `AuditReportEditor.vue` 在意见类型下拉框旁根据当前状态显示标签：`draft` → 可编辑；`review` → ⚠ 审阅中；`eqcr_approved` → 🔒 EQCR 已锁定；`final` → 🔒 已定稿。
7. 本轮**不新增任何平行锁定字段**，消除与现有状态机的语义冲突。

### 需求 7：EQCR 连续 3 年一致性检查

**用户故事**：作为 EQCR，我接手一个连续项目，想看去年 EQCR 怎么说的，避免前后矛盾。

**验收标准**：

1. The `EQCRProjectView` shall 新增"历年 EQCR 对比"Tab，展示该客户近 3 年 EQCR 意见（按需求 2 的 5 个 domain 分列）。
2. The 对比 shall 自动高亮"今年与上年判断不同"的点（例如去年重要性 100 万、今年 200 万，或去年无保留、今年保留）。
3. 差异点 shall 强制 EQCR 写"差异原因"，作为本年 EQCR 意见的必填项，不写不能 approve。
4. 跨年查询以 `client_name` 串联（复用 Round 3 需求 7 的客户串联策略）。

### 需求 8：EQCR 工时独立留痕

**用户故事**：作为 EQCR，准则要求我记录独立复核小时数，系统应自动累计。

**验收标准**：

1. The `WorkHourRecord` 新增 `purpose: str | null`，允许值 `'preparation|review|eqcr|training|admin'`。
2. The EQCR 在 `EQCRProjectView` 点击"开始复核"自动埋 SSE 事件记开始时间；点"提交意见"记结束时间；自动生成一条 `WorkHourRecord(purpose='eqcr')`，EQCR 可再人工修正。
3. The 归档包 shall 包含"EQCR 工时汇总表"PDF，列各天耗时。
4. EQCR 工时不占项目总工时统计，独立列示，避免干扰成本核算。

### 需求 9：EQCR 备忘录自动生成

**用户故事**：作为 EQCR，完成复核后我要出一份"独立复核备忘录"归档。

**验收标准**：

1. The `POST /api/eqcr/projects/{project_id}/memo` shall 根据 EQCR 在需求 2 的各 Tab 录入的意见、独立沟通记录、影子计算结果，自动组装成"独立复核备忘录"Word 文档。
2. The 模板 `eqcr_memo.docx` shall 含章节：项目概况 / 重要性判断 / 会计估计复核 / 关联方复核 / 持续经营评估 / 审计意见合理性 / 独立沟通事项 / 独立取数结果 / 异议与合议结论 / EQCR 总评与结论。
3. The EQCR 可在前端"预览"后手工编辑再定稿（走 `AuditReportEditor` 的富文本编辑）。
4. 定稿后 PDF 转换版本 shall 进归档包 `03-EQCR备忘录.pdf`。
5. 签字合伙人可查看 EQCR 备忘录只读版本，但不能编辑。

### 需求 10：EQCR 仪表盘指标（年度）

**用户故事**：作为首席风控合伙人，我要看所有 EQCR 的年度工作量、发现问题数、与项目组意见不一致率。

**验收标准**：

1. The 后端 shall 新增 `GET /api/eqcr/metrics?year=`，返回：`[{eqcr_id, eqcr_name, project_count, total_hours, disagreement_count, disagreement_rate, material_findings_count}]`。
2. The 前端 shall 新增页面 `/eqcr/metrics`，管理员与 QC 合伙人可看。
3. 差异率高（disagreement_rate > 20%）的 EQCR 打绿标（说明独立性强、敢于提异议）；差异率 0% 的打黄标（需审查是否走过场）。
4. 指标 shall 作为年度评优参考，明确"异议率不是负面指标"。

## UAT 验收清单（手动验证）

1. 新建一个"test-eqcr"账号，role=partner，在某项目 `ProjectAssignment.role='eqcr'`，登录后进 `/eqcr/workbench` 看到该项目卡片。
2. 进项目 EQCR 视图，5 个判断 Tab 依次录入意见（重要性认可、会计估计有异议、其余认可），验证落 `eqcr_opinions` 表。
3. 独立沟通录入 3 条，分享 1 条给项目组，项目组 `ProjectProgressBoard` 看到"来源：EQCR 独立沟通"标记。
4. 影子计算点"借贷平衡"，验证返回独立结果，与项目组已存结果差额高亮。
5. 走完全流程点 EQCR approve，opinion_type 锁定；切到签字合伙人账号尝试改意见，返回 403。
6. 制造一个连续项目（同客户连续 2 年），验证 EQCR 历年对比 Tab 展示，差异点强制写原因才能 approve。
7. 完成复核后生成备忘录 Word，验证 10 个章节齐全；归档包含 `03-EQCR备忘录.pdf`。
8. 工时统计显示 `purpose='eqcr'` 独立小时数。
9. 管理员账号进 `/eqcr/metrics` 看到所有 EQCR 差异率。

## 不在本轮范围

- 其他 4 个角色（已各成轮）
- 关联方交易全链路（本轮最小建模够用）
- 合议流程完整 UI（本轮只落记录，后续按需加 UI）

## 验收完成标志

需求 1~10 全部满足 + UAT 9 项完成，Round 5 关闭。5 轮全部完成后进入总复盘（README 中 Round 6+ 决策点）。

## 变更日志

- v1.2 (2026-05-05) 一致性校对修正：
  - 需求 3 彻底收窄为"EQCR 独立复核笔记"（对齐 design.md 决策），移除"02-EQCR沟通记录.pdf"章节号冲突（02 归 EQCR 备忘录需求 9）
  - 独立性边界明示：不直接对外联络客户，与客户核实通过签字合伙人转达
- v1.1 (2026-05-05) 跨轮交叉核验修正：
  - 需求 1 明示 AssignmentRole 扩展 + 四处权限字典同步 + SOD 新规则（依据 README 跨轮约束第 2、4、7 条）
  - 需求 2 持续经营 Tab 直接复用已有 `GoingConcernEvaluation` 模型不重复建模；关联方改为最小新增
  - 需求 6 审计意见锁定由"新增 opinion_locked_at 字段"改为**扩展 ReportStatus 状态机** `draft→review→eqcr_approved→final`（依据 README 跨轮约束第 3 条），消除平行字段与既有 final 锁定语义的冲突
- v1.0 (2026-05-05) EQCR 视角首稿。

## 补充需求（v1.3，长期运营视角）

以下 2 条由合伙人第三轮深度复盘新增，聚焦"**组成部分审计师复核 + EQCR 独立性声明**"——集团审计和 EQCR 自身合规。

### 需求 11：EQCR 视角的组成部分审计师复核

**用户故事**：作为 EQCR，集团审计项目中我要独立评估各组成部分审计师的能力和独立性，当前系统有 `component_auditor_service` 管理这些数据，但 EQCR 视角无聚合入口。

**代码锚定**：`backend/app/routers/component_auditor.py` 完整 CRUD，`ComponentAuditor` 模型含 `competence_rating / independence_confirmed`（`consolidation_models.py:310-312`），但 EQCR 工作台未集成。

**验收标准**：

1. The `EQCRProjectView` shall 在项目为合并审计时（`project.report_scope == 'consolidated'`）新增 Tab"**组成部分审计师**"。
2. The Tab 内容 shall 聚合：组成部分清单、各审计师能力评级、独立性确认状态、重大发现反馈摘要。
3. EQCR 可对每家组成部分审计师录入"EQCR 复核意见"（复用 `eqcr_opinions` 表，`domain='component_auditor'` 新枚举）。
4. When 组成部分审计师能力评级 C/D 但仍被用作"作为子公司审计依据"，the EQCR 可在意见中标 `disagree`，触发 EQCR 门禁阻断。
5. The 归档 EQCR 备忘录（R5 需求 9）shall 新增"组成部分审计师复核"章节。

### 需求 12：EQCR 个人独立性声明（年度）

**用户故事**：作为 EQCR，事务所要求我每年度签一份独立性声明（不含有客户利益、家庭成员持证券等），系统应提醒和记录。

**代码锚定**：R1 需求 10 落地"项目级独立性声明"，R5 本需求扩展"EQCR 年度个人声明"。

**验收标准**：

1. The `independence_declarations`（R1 落地）shall 支持 `declaration_scope: 'project' | 'annual'`：`project` 是 R1 需求 10 定义的项目级；`annual` 是本需求新增年度个人。
2. The EQCR（及 signing_partner、qc_partner）shall 每自然年度首次登录时弹窗"提交年度独立性声明"，不提交不能访问 EQCR 工作台。
3. The 年度声明问题集 shall 比项目级更细（持股、家庭成员、过去服务、非审计服务收入），模板存 `backend/data/independence_questions_annual.json`（30+ 题）。
4. 年度声明 shall 接受 admin 抽查（重复 R3 需求 4 抽查框架），抽查命中率 10%。
5. 年度声明保留 10 年（R1 需求 11 保留期），与项目数据保留期策略一致。

## 变更日志（续）

- v1.3 (2026-05-05) 长期运营视角增强：
  - 新增需求 11：EQCR 视角的组成部分审计师复核（集团审计）
  - 新增需求 12：EQCR 个人年度独立性声明（依赖 R1 需求 10 的独立性声明框架）
