# 致同审计作业平台 · 全局深度复盘建议书 v4.0

> 文档定位：本文档不是 v1/v3 的续写，而是 2026-05-29 基于**真实实测**的独立体检。**v4.2 起基线已切换到 `main` 分支**（v4.0/v4.1 体检的是 master，现已被 main 取代为唯一真理基线）。
> 立场：资深合伙人视角，5 角色穿刺（审计助理 / 项目经理 / 质控 / 项目合伙人 / EQCR 独立复核合伙人）。
> 原则：**先验证后建议**。每条结论附"实测证据"，每条建议附"✅ 验收标准"。不引用过时记录，不粉饰已修复项。
>
> **v4.1 勘误（2026-05-29 二次复核）**：本文档初稿的基线表有三处错误，均因照"被截断的 grep 输出"读数所致——这正是本文档批评 R9 时犯的同一种错。已用 PowerShell `Select-String -List | Measure-Object` 精确计数订正：handleApiError 真值 **53 文件**（非初稿"约 15"，R9 记录正确）；ElMessage.error 真值 **173 处 / 89 文件**（初稿"30+"和更早记录"清零到 11"都错）；反向穿透**已部分存在**（trace.py + report_trace.py），非初稿"完全缺失"。教训：grep 返回 `[truncated]` 时禁止数可见行下结论。
>
> **v4.2 校准（2026-05-29，基线切到 main 重测）**：v4.0/v4.1 体检 master，但当前唯一真理基线是 `main`（已 merge 报表模块增强 + migration-runner-resilience 等后续工作），多项数字与结构已变化，重测订正如下：
> - **视图数** 90 → **112**（main 含更多视图）；**GtAmountCell** 5 → **8 文件**；**GtEditableTable** 3 → **5 文件**；**GtPageHeader** 74 → **73 文件**；**handleApiError** 53 → **123 文件**（覆盖面比 v4.1 认定的更广）；**ElMessage.error** 173 处/89 文件 → **187 处/100 文件**。
> - **T11 整节作废**：v4.0/v4.1 把"CI Alembic 一致性门禁"列为 P0 头号运维风险，但 **alembic 已于 2026-05-29 彻底删除**（`backend/alembic/` + `alembic.ini` + requirements 依赖全清，git tag `pre-alembic-removal-2026-05-29`）。当前迁移系统是 **D6 MigrationRunner + 28 个 V*.sql**，且 `schema_drift_detector.py` 自检 + `/api/health` 三态语义（healthy/degraded/unhealthy）已落地——v4 想要的运维护城河已用 D6 实现，见 §二 T11 改写。
> - **AMOUNT_DIVISOR_KEY 死代码属实**：3 文件残留（`constants/amountDivisor.ts` 定义 + `GtAmountCell.vue` inject no-op + `LedgerPenetration.vue` import），符合删除条件。
> - 教训补强：**实测有效期 = 单次 grep 时刻**。基线随分支演进失效，立项前必须按当时分支重测，不得直接引用任何历史版本（含本文档）的数字。

---

## 〇、本轮实测数据基线（2026-05-29，v4.2 切到 main 重测订正）

下表是本次复盘的硬数字。**带 🔢 的行经 PowerShell 精确计数**（命令见附录 A），其余为 grep/readFile 定性。**基线 = main 分支**；凡与 memory 记录或 v4.1 旧值冲突的，以本表 v4.2 列为准。

| 维度 | 实测值（v4.2 / main） | 证据 | v4.1 旧值（master）|
|---|---|---|---|
| 视图页面数（views/，含子目录） | 🔢 **112 个 .vue** | PowerShell count | 90 |
| 全局 common 组件 | 25 个（GtPageHeader/GtAmountCell/GtEditableTable/GtStatusTag…） | listDirectory | — |
| 全局 composable | 26 个 | listDirectory | 26 |
| GtPageHeader 接入 | 🔢 **73 文件** | PowerShell count | 74 |
| **GtAmountCell 接入** | 🔢 **8 文件** | PowerShell count | 5（仍是低接入短板）|
| **GtEditableTable 接入** | 🔢 **5 文件** | PowerShell count | 3（近乎为零）|
| 裸 `<el-table` 使用 | 视图层广泛存在（TrialBalance/WorkHours/UserManagement/ValidationRules/WorkpaperList…） | grep | 同 |
| **ElMessage.error** | 🔢 **187 处 / 100 文件** | PowerShell count | 173/89；含 catch 裸用 + 业务校验两类，需分层 |
| **handleApiError 接入** | 🔢 **123 文件** | PowerShell count | 53（v4.1 认定值偏低，main 覆盖面更广）|
| v-permission 接入 | 约 20 个按钮 / 18 个文件 | grep | 一致 |
| useEditingLock 接入 | 3 编辑器（WorkpaperEditor 真锁 / DisclosureEditor+AuditReportEditor 降级前端检测） | grep | 一致 |
| useAiChat 统一 | ✅ 真实接入 AiAssistantSidebar + AIChatPanel | grep | 一致 |
| dict 字典单一真源 | ✅ dictStore + /api/system/dicts，statusMaps.ts 已删 | grep | 一致 |
| 金额单位联动 | displayPrefs store 全局 fmt()，默认万元 | readFile | 一致 |
| AMOUNT_DIVISOR_KEY 死代码 | ⚠️ **3 文件残留**（constants 定义 + GtAmountCell inject no-op + LedgerPenetration import）| grep | 待删（属实）|
| 后端事件联动链 | ✅ 完整（adjustment→TB→reports→notes→audit_report，含幂等去重+DLQ） | 子代理核验 | 一致 |
| 正向穿透端点 | 5 套（reports drilldown / ledger penetrate / penetrate-by-amount / aux / 报告 trace） | 子代理核验 | 一致 |
| **反向溯源** | ⚠️ **章节级已存在**（trace.py 事件链回放 + report_trace.py 附注→底稿→试算表→Top10 序时账 + ReportTracePanel.vue）；缺的是**单元格级即时反查** | readFile 源码 | 同 |
| stale 联动 | ⚠️ 标志位齐全（prefill_stale/is_stale），但**无自动刷新**，需手动 reload | 子代理核验 | 部分 |
| **迁移系统 / schema 漂移** | ✅ **D6 MigrationRunner + 28 V*.sql + SchemaDriftDetector 自检 + /api/health 三态**（alembic 已彻底删除）| readFile 源码 | v4.1 误列为"待建 Alembic 门禁 P0"，**已作废** |
| 函证模块 | ❌ ConfirmationHub 仍是 GtEmpty 占位（developing） | grep | 一致 |

**一句话定性**：后端的"骨"（事件链、穿透、四表可见性、下游绑定、章节级溯源、**D6 迁移自检**）已经相当扎实，是平台真正的资产；前端的"皮"中，**GtAmountCell（8/112）和 GtEditableTable（5/112）仍是确凿的低接入短板**，而错误处理（handleApiError 123 文件）已铺得相当广——真正的问题不是"没接入"，而是 **187 处 ElMessage.error 中混着该改的 catch 裸用和不该动的业务校验，两者未分层**。**原 T11 头号运维风险（schema 漂移）已被 D6 解决，不再是缺口。**

---

## 一、五角色穿刺：每个角色今天真正卡在哪

我用"打开系统走一遍典型一天"的方式，分角色找断层。只列**真实存在**的问题，不臆造。

### 1.1 审计助理（auditor）— 干活最多，但工具链最碎

典型一天：领派单 → 导账套 → 看四表 → 做底稿 → 提调整 → 提交复核。

- **断层 A1｜金额呈现不一致**：助理在序时账穿透页看到的是 `GtAmountCell`（万元、千分位、tabular-nums、负数红字、可点击穿透），但切到底稿汇总页（WorkpaperSummary）、底稿工作台（WorkpaperWorkbench）看到的是裸 `{{ fmtAmt(row.xxx) }}`，字体、单位、颜色、对齐全不一样。**同一个数字在不同页面长得不一样**，这对审计师是认知负担，也容易看错数。
  - 证据：GtAmountCell 仅 8 视图接入（分母 112）；WorkpaperWorkbench/WorkpaperSummary 用本地 `fmtAmt`。
- **断层 A2｜错误提示风格分裂**：handleApiError 其实已接入 123 文件（铺得很广），但仍有相当数量的 `catch` 块直接 `ElMessage.error('保存失败')` 弹原始文案，没解析后端 `detail`。助理遇到失败时，有的页面告诉他"为什么失败"，有的只说"失败了"。注意：187 处 ElMessage.error 里有一部分是文件大小/表单校验等**业务主动提示**（合理保留），需要修的只是 catch 块内的裸用。
- **断层 A3｜底稿编辑无真并发锁**：WorkpaperEditor 有真后端锁，但 DisclosureEditor/AuditReportEditor 是"前端降级检测"。助理和经理同时编辑附注时，后端没有锁端点兜底，存在互相覆盖风险（memory 已知技术债 #2）。
- **断层 A4｜表格能力割裂**：序时账有 Excel 级选中/粘贴/虚拟滚动诉求（YG2101 单表 65 万行），但只有少数表用了 VirtualScrollTable；多数 `<el-table>` 全量渲染，大账套必卡。

### 1.2 项目经理（manager）— 要"看全局"，但全局视图是拼的

- **断层 M1｜异常告警靠前端 computed 派生**：ManagerDashboard 的"高风险/工时超支/逾期底稿"是前端基于 overview 端点派生的（memory 明确记录），没有后端统一的"项目健康度"真源。换个入口（PartnerDashboard）口径可能不一致。
- **断层 M2｜复核闭环可见性弱**：复核意见（ReviewRecord）→ 工单（IssueTicket）→ 整改 SLA 链路后端完整，但经理在看板上看不到"这个项目还有几条复核意见未闭环"的聚合数字，要逐页点。
- **断层 M3｜派单与可见性**：ProjectAssignment 已支持按角色裁剪，但"三码体系"（本企业/上级/最终控制方代码构建项目树）仍是待 spec 状态，集团多主体项目经理无法按树状结构看下属主体。

### 1.3 质控（qc）— 规则引擎强，但"抽查动线"未闭环

- **断层 Q1｜QC 规则可配但触发分散**：qc_rule_definitions 22 条 seed + 前端 /qc/rules 只读页已就绪，但质控发起抽查（QCDashboard 的 `qc:initiate`）后，抽查结论如何回流到归档门禁（gate）缺少前端可视的闭环展示。
- **断层 Q2｜日志合规 Tab 是亮点但孤立**：QcInspectionWorkbench 有日志合规检查，章节级溯源（report_trace.py 附注章节→底稿→试算表→序时账）也已存在，但二者没打通——质控想验证"这个审定数是谁在什么时候基于哪个数据集改的"，需要 F47 校验透明化 + 把 trace 入口下沉到金额单元格级别。

### 1.4 项目合伙人（partner）— 要"签字决策"，信息要一屏可信

- **断层 P1｜签字面板已建但 PDF 预览降级**：PartnerSignDecision 中栏是 HTML 降级渲染（不依赖不存在的 /preview-pdf 端点，memory 明确）。合伙人签字前看到的是"近似"报告而非最终版式，对"所见即所签"有心理落差。
- **断层 P2｜签字与数据冻结的可视化**：F50 下游绑定（bound_dataset_id）后端已落地——签字后报表锁定数据集、rollback 被拒。但合伙人在签字面板上**看不到**"我这一签会把哪个数据集冻结、之后谁都不能改"的明确提示，合规价值没传达到决策点。

### 1.5 EQCR 独立复核合伙人（eqcr）— 体系最完整，但"独立性"边界要更清

- **断层 E1｜影子计算结论回流约定隐晦**：ShadowCompareRow 的 pass/flag 映射到 EqcrOpinion 的 agree/disagree（memory 约定），但这个映射对 EQCR 本人不透明——他点"flag"时，不知道系统把它记成了"disagree"。
- **断层 E2｜EQCR 指标入口权限**：DefaultLayout 的 `isEqcrEligible` 已包含 eqcr 角色（实测已修），这条历史问题已解决，**不再是断层**（如实标注，不粉饰）。

---

## 二、全局横切主题：需要"全平台一盘棋"考虑的设定

这是用户最关心的部分——那些不能"看一个页面改一个页面"、必须全局统一的机制。我按用户点名的维度逐一给出现状判断 + 落地方案。

### T1｜全局组件应用一致性（最高优先级）

**现状**：21 个全局组件库存在，但接入率两极分化。GtPageHeader 接入尚可，GtAmountCell（8/112）、GtEditableTable（5/112）严重偏低。

**根因**：组件建好了，但缺少"强制接入 + CI 守护 + 漂移检测"的闭环，靠人工逐页替换，做一轮停一轮。

**方案**：
1. **GtAmountCell 全量化**：盘点所有展示金额的 `<el-table-column>` + 裸 `fmtAmt`，统一替换为 `<GtAmountCell>`。优先级：四表/报表/底稿/调整/错报/附注六大核心数据页。
2. **建立组件接入 CI 卡点**：新增 `scripts/check-component-adoption.mjs`，统计金额列裸用数 / 裸 el-table 数，设当前实测值为基线，**只减不增**。
3. **GtEditableTable 评估边界**：不是所有表都该可编辑。明确"可编辑表"清单（调整分录/合并工作底稿/试算表），其余只读表保持 GtAmountCell + el-table 即可，避免为统一而统一。

✅ 验收：GtAmountCell 接入从 8 → ≥ 30 核心数据视图；CI 基线脚本上线；金额列裸用数下降 ≥ 80%。

### T2｜错误处理统一（需先分层，不能拍总数）

**现状**：handleApiError 已接入 **123 文件**（覆盖面其实很广，R9 + 后续工作真做了）。但 ElMessage.error 全库 **187 处 / 100 文件**，其中混着两类：(a) `catch` 块内裸用——应改 handleApiError；(b) 业务主动校验提示（文件大小、表单必填、登录失败等）——合理保留。

**关键**：不能把 187 当成"待清零债务"，那会误伤第二类。必须先按"是否在 catch 块内"过滤，得出真正该改的子集，再定基线。

**方案**：写脚本（或人工 review）区分两类 → 只替换 catch 块内的 `ElMessage.error(...)` 为 `handleApiError(e, '操作名')` → CI 卡点只统计 catch 块内裸用数。

✅ 验收：catch 块内 `ElMessage.error` 命中数 → 0；CI grep 卡点基线设为分层后的 catch 残留数（不是 173）。

### T3｜数值处理（金额）全局口径

**现状（良性）**：displayPrefs store 是单一真源，`fmt()` 内置单位换算（元/万元/千元），localStorage 持久化，四表联动已通。GtAmountCell 跟随 store。后端金额已 Decimal 化（Numeric(20,2)）。

**残留风险**：
- `AMOUNT_DIVISOR_KEY` provide/inject 机制是历史双重除法 bug 的残骸，GtAmountCell 里 `scaledValue` 已经 no-op 化但代码还在。**死代码应删**（符合用户"死代码立即删除"偏好）。
- 未走 GtAmountCell 的页面（WorkpaperWorkbench 等）用本地 fmtAmt，**不跟随单位切换**——用户切到"元"，这些页面还显示万元。

**方案**：删除 AMOUNT_DIVISOR_KEY inject 残骸；T1 的 GtAmountCell 全量化会自动修复"不跟随单位切换"问题。

✅ 验收：grep `AMOUNT_DIVISOR_KEY` = 0；切换单位后所有金额页同步变化。

### T4｜枚举/字典统一

**现状（良性）**：dictStore + /api/system/dicts 单一真源，statusMaps.ts 已删，statusEnum.ts 提供 TS 类型常量。这是做得好的部分。

**残留**：memory 记录有 5 处散落 `=== 'draft'` 硬编码状态判断（QcInspectionWorkbench/ArchiveWizard/AuditReportEditor/IssueTicketList/PDFExportPanel）。

**方案**：触碰即修，替换为 statusEnum 常量引用。低优先级。

✅ 验收：grep 状态字符串硬编码（排除常量定义文件）= 0。

### T5｜联动穿透闭环（平台灵魂）

**现状（后端强）**：事件链 adjustment→TB→reports→notes→audit_report 完整且幂等；正向穿透 5 套端点齐全；**反向溯源也已部分存在**——`backend/app/routers/trace.py`（GET /trace/{trace_id}/replay 按 trace_id 回放事件链，L1/L2/L3 三级）+ `report_trace.py`（GET /api/report-review/{pid}/trace/{section} 附注章节→底稿→试算表→Top10 序时账）+ 前端 `ReportTracePanel.vue`。

**两个真实缺口（已重新定义，初稿误判"反向完全缺失"）**：
1. **反向溯源是"章节级 / trace_id 级"，缺"单元格级即时反查"**：现在要溯源得手动输入附注章节号，无法在四表/报表的某个金额单元格上右键直接"这个数字从哪来、影响了哪些下游"。粒度太粗，动线断。
2. **stale 不自动刷新**：rollback 后 prefill_stale/is_stale 标志位会置位，但前端不自动 re-fetch，用户看到的可能是旧数。useProjectEvents composable（SSE 订阅）已具备基础，但未在六大数据页普遍接入。

**方案**：
- **复用而非新建**：不从零做反向端点。在现有 trace_event_service / report_trace_service 基础上，加一个细粒度入口——输入 account_code + amount（或 voucher_id），复用 wp_account_mapping + report_config formula 反查受影响的 report rows / workpapers / notes。前端在 GtAmountCell 右键菜单加"数字溯源"，跳转或弹出 ReportTracePanel 的下钻结果。
- 六大数据页统一接入 useProjectEvents，监听 `dataset:activated` / `dataset:rolled_back` / `year:changed` 自动 re-fetch 或显示"数据已更新，点击刷新"横幅。

✅ 验收：金额单元格右键"数字溯源"入口上线（复用现有 trace 服务）；六大数据页接入 useProjectEvents；rollback 后页面自动提示刷新。

### T6｜年度（year）全局上下文

**现状（良性）**：projectStore 是单一真源，syncFromRoute 自动同步，changeYear 发 `year:changed` 事件。设计正确。

**残留**：需确认所有数据页都订阅了 `year:changed` 并重新加载（与 T5 的 useProjectEvents 接入是同一件事）。

✅ 验收：切换年度后所有当前项目数据页自动重载。

### T7｜权限（v-permission）

**现状**：ROLE_PERMISSIONS 前端硬编码兜底 + 后端 user.permissions 优先。v-permission 接入约 20 个危险按钮。

**风险点**：
- 前端 ROLE_PERMISSIONS 与后端权限表是**两套真源**，靠"优先后端、兜底前端"协调。memory 记录的"四点同步约定"（assignment_service.ROLE_MAP + role_context_service._ROLE_PRIORITY + 前端 ROLE_MAP + usePermission）维护成本高，新增权限码容易漏改一处。
- v-permission 只覆盖危险操作按钮，**读权限/页面级权限**主要靠 router meta.roles，两套机制。

**方案**：
- 中期：让后端 `/api/users/me` 成为权限的**唯一真源**，前端 ROLE_PERMISSIONS 降级为纯类型提示/离线兜底，并加 CI 测试断言"前端硬编码权限码 ⊆ 后端定义的权限码全集"，防止两套漂移。
- 不急于大改，但每次新增权限码必须同时跑该一致性测试。

✅ 验收：新增后端权限码一致性测试；前端权限码集合是后端的子集。

### T8｜编辑（编辑锁 + 编辑模式）

**现状**：useEditMode（查看/编辑切换）接入约 11 视图；useEditingLock 仅 WorkpaperEditor 真锁，另两个编辑器降级。

**根因**：后端编辑锁端点是 `/api/workpapers/{wp_id}/editing-lock`，是底稿专用的，附注/审计报告没有通用锁端点。

**方案**：后端建通用 `editing_locks` 表支持 resource_type 字段（memory 已列为技术债 #2），让 DisclosureEditor/AuditReportEditor 用真锁。这是并发安全的硬需求，不能长期降级。

✅ 验收：通用编辑锁端点上线；三大编辑器都用真后端锁；两人并发编辑同一附注时第二人看到只读 + 锁持有人提示。

### T9｜字体字号 / 显示偏好

**现状（良性）**：displayPrefs 管理 fontSize/decimals/negativeRed/showZero/highlightThreshold，localStorage 持久化。设计完整。

**残留**：fontConfig computed 已暴露，但需确认表格组件真的消费了它（字号切换是否对所有表生效）。

✅ 验收：切换字号后核心表格行高/字号同步变化。

### T10｜查询（自定义查询 + 知识库 + 对话）

- **自定义查询**：CustomQueryDialog 存在，独立功能。
- **知识库上下文注入**：R9 已做（前端 + 后端 context 参数 BM25 加权）。良性。
- **AI 对话**：useAiChat 已统一（AiAssistantSidebar + AIChatPanel），良性。

这块整体健康，无重大断层。

### T11｜运维维护便利性（上线后）— v4.2 重写

**现状**：CI 多卡点（B'/F40/F48/vue-tsc/API 硬编码），健康检查端点 /health/ledger-import，Prometheus /metrics（可选依赖降级），ADR 文档齐全。

**v4.2 重大变更：原"头号运维风险"已解决，本节降级。**
v4.0/v4.1 把"PG schema 与 Alembic 漂移"列为上线后最大运维炸弹、CI Alembic 门禁列为 P0。该判断**已过时**：

- **alembic 已于 2026-05-29 彻底删除**（`backend/alembic/` 106 .py + `alembic.ini` + requirements 依赖全清，git tag `pre-alembic-removal-2026-05-29` 防回退）。
- 当前迁移系统 = **D6 MigrationRunner + 28 个 V*.sql/R*.sql**（启动时 `run_pending` 自动执行，per-migration try/except 异常隔离，批不中断；`exec_driver_sql` 绕开 `text()` bind 解析）。
- **schema 漂移已有自检**：`backend/app/core/schema_drift_detector.py`（4 类 drift = orm_extra/db_extra/type_mismatch/enum_mismatch，PG-only 主流程）在 lifespan 启动时跑，写 `schema_drift_log` 表。
- **/api/health 三态语义**（healthy/degraded/unhealthy）暴露 `migration.failures` + `schema_drift`，degraded 是 200（应用可用，前端 banner 提示运维），unhealthy 是 503。

→ v4 想要的"根除迁移没执行类 500"的护城河**已用 D6 实现**，原方案的"CI Alembic 一致性门禁"作废（无 alembic 可跑）。

**仍然成立的真实风险**：
1. **可选依赖分散**：python-magic/psutil/prometheus_client/fakeredis 5 个可选依赖的降级策略散在各源文件 docstring，无集中文档（memory P4 已识别）。**仍待办**。
2. **superseded 数据膨胀**：每次大导入产生 200 万 superseded 行，purge worker 受 FK 约束限制，需配合 VACUUM。purge + VACUUM 已落地，缺表膨胀监控告警。
3. **D6 自检的 Playwright 实测未完成**：migration-runner-resilience spec Sprint 5（health degraded 截图 + 故意 drift 复测 + ADR-024/025）仍是 17/21，待收尾。

**方案（已收窄）**：
- ~~CI Alembic 一致性门禁~~ → **作废**（alembic 已删，D6 + SchemaDriftDetector 已替代）。
- 新建 `docs/OPTIONAL_DEPENDENCIES.md` 集中 5 个可选依赖 + 降级行为。
- 补一个"表膨胀监控"告警（n_dead_tup/n_live_tup > 阈值）纳入运维 checklist。
- 收尾 migration-runner-resilience Sprint 5 UAT。

✅ 验收：OPTIONAL_DEPENDENCIES.md 建立；膨胀监控查询纳入运维 checklist；migration-runner-resilience Sprint 5 完成。

### T12｜函证模块（明确的功能空洞）

**现状**：ConfirmationHub 是 GtEmpty 占位，后端 confirmations.py 返回 developing。这是 5 角色都会用到的核心审计功能（询证函发收、差异、替代程序），目前完全缺失。

**方案**：独立 Sprint 实现 6 步工作流（清单/发函/收函/差异/替代程序/差异转错报），差异自动建议 misstatement_service.create。这是功能补全，不是打磨。

✅ 验收：函证 6 步闭环；函证差异一键转错报。

---

## 三、优先级路线图（价值 × 紧迫 二维）

不按 P0-P3 线性排，按"对 5 角色的实际价值 × 修复紧迫度"分档。

### M1 一致性收口（高价值 × 高紧迫，~5 人天）
> 解决前端真实低接入短板。
1. T1 GtAmountCell 全量化（8→30+ 视图，分母 112）+ CI 卡点
2. T2 ElMessage.error 先分层（187 处中区分 catch 裸用 vs 业务校验）再改 catch 块为 handleApiError
3. T3 删除 AMOUNT_DIVISOR_KEY 死代码（3 文件）
4. T4 残留 5 处状态硬编码触碰即修

### M2 联动闭环 + 并发安全（高价值 × 中紧迫，~6 人天）
5. T5 金额单元格右键"数字溯源"（复用现有 trace_event_service / report_trace_service，不新建端点）
6. T5/T6 六大数据页接入 useProjectEvents（stale 自动刷新 + 年度联动）
7. T8 通用编辑锁端点 + 三编辑器真锁

### M3 运维护城河（中价值 × 中紧迫，~2 人天，v4.2 收窄）
> v4.2 变更：原"schema 漂移打爆生产"风险已被 D6 MigrationRunner + SchemaDriftDetector + /api/health 三态解决，本档大幅收窄。
8. ~~T11 CI Alembic 一致性门禁~~ → **作废**（alembic 已删；改为收尾 migration-runner-resilience Sprint 5 UAT）
9. T11 OPTIONAL_DEPENDENCIES.md + 表膨胀监控
10. T7 后端权限单一真源一致性测试

### M4 决策可信度（中价值 × 中紧迫，~4 人天）
11. P1 PartnerSignDecision 真实 PDF 预览（或明确标注"草稿预览"消除心理落差）
12. P2 签字面板展示"数据冻结影响"提示
13. E1 ShadowCompareRow verdict 映射对 EQCR 透明化

### M5 功能补全（高价值 × 低紧迫，独立 Sprint）
14. T12 函证 6 步工作流
15. M3 三码体系 + 集团项目树
16. 大表格虚拟滚动全量化（YG2101 级别）

---

## 四、核心原则沉淀（写给后续每一轮）

1. **一致性 > 功能丰富**：再加功能前，先把已有 25 个组件的接入率做实（GtAmountCell 8/112、GtEditableTable 5/112 仍是真短板）。
2. **声称完成 ≠ 真完成，但"实测"本身也要被实测**：本文档初稿犯了和 R9 同样的错——照截断 grep 输出读数，把 handleApiError 误判为"约 15"（v4.1 订为 53，main 重测 123），用错误实测去推翻正确记录，比沿用记录更危险。**铁律：grep 返回 `[truncated: too many matches]` 时禁止数可见行，必须用 `Select-String -List | Measure-Object` 精确计数。**
3. **基线要分层，不能拍总数**：ElMessage.error 187 处里混着该改的（catch 裸用）和该留的（业务校验），直接拿总数当债务会误伤。
4. **穿透是审计平台的灵魂**：正向 + 章节级反向都已通，缺的是单元格级即时反查——复用现有 trace 服务下沉粒度，不重复造端点。
5. **后端是资产，前端是短板**：事件链/穿透/下游绑定/章节级溯源/可见性架构/D6 迁移自检是真正值钱的部分；精力应投向前端组件一致性。
6. **~~schema 漂移是头号运维风险~~（v4.2 已解决）**：alembic 已删，D6 MigrationRunner + SchemaDriftDetector + /api/health 三态已替代，原 P0 Alembic 门禁作废。**新铁律：实测有效期 = 单次 grep 时刻，基线随分支演进失效，立项前必须按当时分支重测，不得引用任何历史版本数字。**
7. **死代码立即删**（用户偏好）：AMOUNT_DIVISOR_KEY 等残骸不留 fallback 注释。
8. **每条建议必须可验收**：grep 命中数 / 测试通过 / 真实样本跑通，拒绝"做了但说不清"。

---

## 附录 A：本轮实测证据索引（可复现）

> 🔢 标记的命令为 PowerShell 精确计数（cwd=audit-platform/frontend），其余为 grep/readFile 定性。

| 结论 | 命令（v4.2 实测值 / main）|
|---|---|
| 🔢 视图 112 个 | `(Get-ChildItem src/views -Recurse -Filter *.vue).Count` |
| 🔢 GtAmountCell 8 文件 | `Get-ChildItem src -Recurse -Filter *.vue \| Select-String '<GtAmountCell' -List \| Measure-Object` |
| 🔢 GtEditableTable 5 文件 | 同上模式，pattern `<GtEditableTable` |
| 🔢 GtPageHeader 73 文件 | 同上模式，pattern `<GtPageHeader` |
| 🔢 handleApiError 123 文件 | 同上模式，pattern `handleApiError` |
| 🔢 ElMessage.error 187 处 / 100 文件 | 出现数去掉 `-List`，文件数加 `-List` |
| AMOUNT_DIVISOR_KEY 3 文件 | `Get-ChildItem src -Recurse -Include *.vue,*.ts \| Select-String 'AMOUNT_DIVISOR_KEY'` |
| v-permission 约 20 按钮 | grep `v-permission` |
| 事件链完整 | readFile event_handlers.py |
| 正向穿透 5 套 | 子代理 + readFile penetrate_by_amount.py / ledger_penetration.py / reports.py |
| 反向溯源（章节级）已存在 | readFile trace.py / report_trace_service.py / ReportTracePanel.vue |
| D6 迁移 + 漂移自检 | `Test-Path backend/alembic`（已删）/ readFile migration_runner.py / schema_drift_detector.py / 28 V*.sql |
| 四表 dataset_id 可见性 | readFile audit_platform_models.py |
| dict 单一真源 | readFile dict.ts |
| 金额单位 store | readFile displayPrefs.ts |
| 年度 store | readFile project.ts |
| 权限模型 | readFile usePermission.ts |
| useAiChat 接入 | grep useAiChat |
| 函证 stub | grep ConfirmationHub |

> 文档结束。建议下一步：将 M1 收口为一个 spec 三件套（requirements/design/tasks），按"5 角色轮转 PDCA"推进。**注意：M1 的 GtAmountCell 全量化和 T2 ElMessage 分层是 spec 的核心可验收项，进入 requirements 前以本 v4.2（main 基线）订正后的数字为准——并在立项当天按 main 最新状态再重测一次，不得直接引用本文档数字。**
