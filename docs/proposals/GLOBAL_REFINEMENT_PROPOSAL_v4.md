# 致同审计作业平台 · 全局深度复盘建议书 v5.0

> 文档定位：本文档是 v4.x 的**重新实测基线**。v4.0/v4.1 体检 master，v4.2 切到 main，而 **v5.0（2026-06-05）基线 = `work/2026-05-30-wp-specs`（HEAD 379e87a0）**——M1 一致性收口已全量落地、多个 spec 已归档、迁移推进到 V055，数字与结构再次大幅变化，全部重测订正。
> 立场：资深合伙人视角，5 角色穿刺（审计助理 / 项目经理 / 质控 / 项目合伙人 / EQCR 独立复核合伙人）。
> 原则：**先验证后建议**。每条结论附"实测证据"，每条建议附"✅ 验收标准"。不引用过时记录，不粉饰已修复项。
>
> **v5.0 重大变更摘要（相对 v4.2）**：
> - **M1「一致性收口」整档已完成并归档**（`frontend-consistency-m1` 在 `_archive/06-engineering-governance/`）：T1 GtAmountCell 六大核心页 100% 接入、T2 catch 块内 ElMessage.error 清零（175→0）、T3 AMOUNT_DIVISOR_KEY 死代码删除（仅剩 1 个守护测试文件）、T4 状态硬编码降到 4。v4.2 列为「高价值×高紧迫」的 M1 不再是缺口。
> - **AMOUNT_DIVISOR_KEY 死代码已删**：v4.2 的"3 文件残留"现仅剩 `property-m1-dead-code-invariance.spec.ts`（守护用属性测试，非死代码）。
> - **ElMessage.error 大幅下降**：187 处/100 文件 → **57 处/33 文件**；其中 catch 块内裸用已被 CI 卡点 `elmessage-error-in-catch=0` 守护。
> - **handleApiError 覆盖面再扩**：123 文件 → **257 文件**。
> - **附注联动假性刷新已修**（`disclosure-note-linkage-and-slimdown` spec，2026-06-05）：v4.2 §T5 的"stale 不自动刷新"在附注侧已部分解决——「从底稿刷新」现真实重算金额（修了 note_stale_service 致命 import bug + 接 DisclosureEngine 填充链），但**六大数据页的 useProjectEvents 普遍接入仍未完成**（仅 6 文件）。
> - **校验端点 500 已修**：`NoteValidationEngine` 补齐 `validate_all/get_latest_results/confirm_finding` 三个 router 调用但从未实现的方法。
> - **迁移系统推进到 V055**（project-creation-enhancement），D6 MigrationRunner + SchemaDriftDetector + /api/health 三态运维护城河持续有效（T11 仍作废 alembic 门禁）。
> - 教训不变：**实测有效期 = 单次 grep 时刻**。基线随分支演进失效，立项前必须按当时分支重测，不得直接引用任何历史版本（含本文档）的数字。
> - **二次复盘补充（§二·补 T13-T16）**：写完主体后再深挖发现 4 条新债——①文件大小门禁当前红（15 文件超标，**本轮自己撑大了 2 个** + 未接 CI 空转）②baselines.json 与真实 vue-tsc/vitest 状态疑漂移 ③功能空洞不止函证（另有监管报送 + 4 个疑似废壳 Workpaper*Editor）④技术债埋点 277 处。如实记录含自我批评。

---

## 〇、本轮实测数据基线（2026-06-05，v5.0 基线 = work/2026-05-30-wp-specs @ 379e87a0）

下表是本次复盘的硬数字。**带 🔢 的行经 PowerShell 精确计数**（命令见附录 A），其余为 grep/readFile 定性。凡与 memory 记录或 v4.2 旧值冲突的，以本表 v5.0 列为准。

| 维度 | 实测值（v5.0） | 证据 | v4.2 旧值（main） | 趋势 |
|---|---|---|---|---|
| 视图页面数（views/，含子目录） | 🔢 **116 个 .vue** | PowerShell count | 112 | ↑（新增建项/序时账导入等视图） |
| 全局 common Gt 组件 | 🔢 **15 个 Gt*.vue** | listDirectory | 25（含非 Gt 前缀，口径不同） | — |
| 全局 composable（use* 顶层） | 🔢 **129 个** | listDirectory | 26（v4.2 仅数 composables/ 顶层，本次含全部 use*） | ↑ |
| GtPageHeader 接入 | 🔢 **75 文件** | PowerShell count | 73 | ↑ |
| **GtAmountCell 接入** | 🔢 **11 文件 / 用量 105** | PowerShell count | 8 文件 | ↑ M1 已推进，六大核心页 100% |
| **GtEditableTable 接入** | 🔢 **5 文件** | PowerShell count | 5 | 持平（白名单边界，非短板） |
| 裸 `<el-table` 文件 | 🔢 **144 文件**（`<el-table[ >]` 精确） | PowerShell count | "广泛存在"（定性） | — |
| **ElMessage.error** | 🔢 **57 处 / 33 文件** | PowerShell count | 187 处 / 100 文件 | ↓↓ M1 T2 清零 catch 裸用 |
| **catch 块内 ElMessage.error** | **0**（CI 卡点守护） | baselines.json `elmessage-error-in-catch=0` | 175（M1 立项 AST 实测） | ↓↓↓ 已清零 |
| **handleApiError 接入** | 🔢 **257 文件** | PowerShell count | 123 | ↑↑ |
| v-permission 接入 | 🔢 **23 文件** | PowerShell count | 约 18 | ↑ |
| useEditingLock 接入 | **4 文件**（WorkpaperEditor 真锁 / DisclosureEditor+AuditReportEditor 降级 / LockConflictPanel） | grep | 3 | 持平（仍 1 真锁 + 2 降级） |
| useProjectEvents 接入 | 🔢 **6 文件** | PowerShell count | 未量化 | 低接入（T5/T6 仍待办） |
| **AMOUNT_DIVISOR_KEY** | ⚠️ **仅 1 个守护测试文件**（`property-m1-dead-code-invariance.spec.ts`）；死代码已删 | grep | 3 文件死代码残留 | ✅ 已删（M1 T3） |
| dict 字典单一真源 | ✅ dictStore + /api/system/dicts，statusMaps.ts 已删 | grep | 一致 | — |
| 金额单位联动 | ✅ displayPrefs store 全局，GtAmountCell 跟随，六大核心页已联动 | M1 验收 | 部分 | ↑ |
| 后端事件联动链 | ✅ 完整（adjustment→TB→reports→notes→audit_report，含幂等去重+DLQ） | 子代理核验 | 一致 | — |
| 正向穿透端点 | 5 套（reports drilldown / ledger penetrate / penetrate-by-amount / aux / 报告 trace） | 子代理核验 | 一致 | — |
| 反向溯源 | ⚠️ **章节级已存在**（trace.py + report_trace.py + ReportTracePanel.vue）；**单元格级即时反查仍缺**（GtAmountCell 无右键溯源入口） | grep GtAmountCell | 同 | 未变 |
| stale 联动 | ⚠️ **附注侧已修真实重算**（disclosure-note-linkage spec）；其余数据页仍标志位齐全但**无自动刷新** | spec 实施 | 部分 | 附注↑，全局未变 |
| 迁移系统 / schema 漂移 | ✅ **D6 MigrationRunner + 53 个 V*.sql（最高 V055）+ SchemaDriftDetector 自检 + /api/health 三态**（alembic 已彻底删除） | readFile | V052 时点 | ↑ |
| 后端 service / router / 测试 | 🔢 **408 service + 291 router + 733 后端测试文件** | PowerShell count | 未量化 | — |
| 前端测试文件 | 🔢 **235 个 .spec/.test.ts** | PowerShell count | 未量化 | — |
| 校验端点 500 | ✅ **已修**（NoteValidationEngine 补 validate_all/get_latest_results/confirm_finding） | 本轮实测 | 未识别（pre-existing） | ✅ |
| 函证模块 | ❌ **仍是 developing stub**（confirmations.py 18 行返回 `status:"developing"`） | readFile | 一致 | 未变 |
| 通用编辑锁（resource_type） | ❌ **仍缺**（仅 WorkpaperEditingLock + adjustment_editing_locks 两套专用表） | grep | 一致 | 未变 |
| OPTIONAL_DEPENDENCIES.md | ❌ **仍未建** | Test-Path False | 待办 | 未变 |

**一句话定性**：v4.2 的头号前端短板（GtAmountCell 低接入、catch 裸用、AMOUNT_DIVISOR_KEY 死代码）**已被 M1 spec 全部清掉**；后端的"骨"（事件链、穿透、四表可见性、章节级溯源、D6 迁移自检）持续扎实并修了附注假性刷新 + 校验端点 500。**当前真正剩余的缺口收敛为 4 个**：①单元格级即时反查（T5，GtAmountCell 右键溯源未做）②stale 全局自动刷新（T5/T6，useProjectEvents 仅 6 文件）③通用编辑锁（T8，附注/报告编辑器仍降级）④函证模块（T12，仍是 stub）。运维侧 OPTIONAL_DEPENDENCIES.md 仍待建。

---

## 一、五角色穿刺：每个角色今天真正卡在哪

只列**真实存在**的问题，不臆造。相对 v4.2，已修复项如实标注"已解决"。

### 1.1 审计助理（auditor）

- **~~断层 A1｜金额呈现不一致~~（M1 已大幅缓解）**：v4.2 批评的"同一数字在不同页面长得不一样"已通过 M1 T1 解决——六大核心数据页（四表/报表/底稿/调整/错报/附注）的展示金额列已 100% 接入 GtAmountCell，单位切换全局联动。**残留**：非核心页（WorkpaperWorkbench 等）仍有本地 fmtAmt，但已不在六大核心动线上，影响降为次要。
- **~~断层 A2｜错误提示风格分裂~~（M1 已解决）**：catch 块内裸 `ElMessage.error` 已清零（175→0），并由 CI 卡点 `elmessage-error-in-catch=0` 守护防退化。剩余 57 处 ElMessage.error 全部是合理的业务主动校验（文件大小/表单必填/返回值检查等）。
- **断层 A3｜底稿编辑无真并发锁（仍存在）**：WorkpaperEditor 有真后端锁，但 DisclosureEditor/AuditReportEditor 仍是"前端降级检测"（useEditingLock 接入 4 文件，仅 1 个真锁）。两人同时编辑附注仍有互相覆盖风险（memory 技术债 #2，T8 仍待办）。
- **断层 A4｜表格能力割裂（仍存在）**：序时账 65 万行（YG2101）等大账套场景，多数 `<el-table>`（144 文件裸用）全量渲染，VirtualScrollTable 接入有限。

### 1.2 项目经理（manager）

- **断层 M1｜异常告警靠前端 computed 派生（部分缓解）**：`project-workspace-overview-revamp` spec 已落地 ProjectHealthCards（6 卡三态降级）+ 后端 `dashboard/summary` 补 `review_completion_rate`——详情面板的健康度已接真实后端数据。**残留**：ManagerDashboard / PartnerDashboard 的跨项目聚合口径是否与新健康卡统一，仍需确认。
- **断层 M2｜复核闭环可见性弱（仍存在）**：复核意见→工单→整改 SLA 后端完整，但跨项目看板的"未闭环复核意见聚合数"仍需逐页点。
- **断层 M3｜派单与可见性 / 三码体系（部分推进）**：`project-creation-enhancement` spec 已落地 USCC 统一社会信用代码校验 + 批量建项 + 项目显示名后缀。**残留**：用三码（本企业/上级/最终控制方）构建集团项目树的视图层仍未做。

### 1.3 质控（qc）

- **断层 Q1｜QC 规则可配但触发分散（仍存在）**：qc_rule_definitions seed + /qc/rules 只读页就绪，但抽查结论回流归档门禁的前端闭环展示仍缺。
- **断层 Q2｜日志合规 Tab 与章节级溯源未打通（仍存在）**：质控想验证"审定数是谁何时基于哪个数据集改的"，仍需把 trace 入口下沉到金额单元格级别（与 T5 同根问题）。

### 1.4 项目合伙人（partner）

- **断层 P1｜签字面板 PDF 预览降级（仍存在）**：PartnerSignDecision 中栏仍是 HTML 降级渲染，"所见即所签"心理落差仍在。
- **断层 P2｜签字与数据冻结可视化（仍存在）**：F50 下游绑定（bound_dataset_id）后端已落地，但签字面板未明确提示"这一签冻结哪个数据集"。

### 1.5 EQCR 独立复核合伙人（eqcr）

- **断层 E1｜影子计算结论回流约定隐晦（仍存在）**：ShadowCompareRow pass/flag → EqcrOpinion agree/disagree 的映射对 EQCR 本人不透明。
- **~~断层 E2｜EQCR 指标入口权限~~（早已解决）**：DefaultLayout 的 `isEqcrEligible` 已含 eqcr 角色，非断层。

---

## 二、全局横切主题：现状判断 + 落地方案

按用户点名的维度逐一给出现状 + 方案。**已被 M1 解决的 T1-T4 标注"已完成"，不再展开方案。**

### T1｜全局组件应用一致性 — ✅ M1 已完成（六大核心页）

**现状**：M1 T1 已将六大核心数据页（ReportView/TrialBalance/WorkpaperSummary/Adjustments/Misstatements/DisclosureEditor）的展示金额列 100% 接入 GtAmountCell（用量 57→105，+84%），并建立 CI 卡点：`GtAmountCell-uses` 只增不减、`no-bare-amount-cell-violations`（ESLint AST 精确金额列裸用）只减不增。

**残留（延伸目标，非短板）**：全平台 GtAmountCell 覆盖率 24%（目标 80%），非核心页仍有本地 fmtAmt。设计文档已明确这是"延伸目标不强求一次到位"。

✅ 验收（已达成）：六大核心页金额列裸用 = 0；CI 基线脚本上线；GtAmountCell-uses ≥ 105。
🔲 后续（可选）：把覆盖率从 24% 推向 80%，纳入日常"触碰即接入"而非专项 Sprint。

### T2｜错误处理统一 — ✅ M1 已完成

**现状**：M1 T2 用 AST 脚本（`scripts/audit-elmessage-error.mjs`）精确区分 catch 裸用（175 处）vs 业务校验（26 处），把 175 处 catch 裸用全部替换为 `handleApiError(e, '中文操作名')`，业务校验保留。CI 卡点 `elmessage-error-in-catch=0` 守护防退化。handleApiError 覆盖面已达 257 文件。

✅ 验收（已达成）：catch 块内 ElMessage.error = 0；CI 卡点基线设为 0（只减不增）。

### T3｜数值处理（金额）全局口径 — ✅ M1 已完成

**现状**：displayPrefs store 单一真源持续有效；AMOUNT_DIVISOR_KEY 死代码已删（`constants/amountDivisor.ts` 删除 + GtAmountCell inject 残骸删除 + LedgerPenetration 死 import 删除），仅剩 1 个属性测试 `property-m1-dead-code-invariance.spec.ts` 守护"删除行为不变性"。六大核心页单位切换已全局联动。

✅ 验收（已达成）：grep `AMOUNT_DIVISOR_KEY` 在生产代码 = 0（仅守护测试保留）；切换单位后核心页金额同步变化。

### T4｜枚举/字典统一 — ✅ M1 基本完成

**现状**：dictStore + /api/system/dicts 单一真源；状态硬编码从 25 降到 4（`status-hardcoding-5files=4`，CI 卡点目标 0）。

🔲 残留（低优先）：剩余 4 处状态硬编码（ArchiveWizard 等），触碰即修。

### T5｜联动穿透闭环（平台灵魂）— 部分推进，两缺口仍在

**现状（后端强 + 附注侧已修）**：
- 事件链完整、正向穿透 5 套、章节级反向溯源（trace.py + report_trace.py + ReportTracePanel.vue）持续有效。
- **附注假性刷新已修**（disclosure-note-linkage-and-slimdown spec，2026-06-05）：v4.2 批评的"stale 标志位齐全但不真重算"在附注侧已根治——修了 `note_stale_service` 的致命 import bug（`phase13_models` 不存在的 DisclosureNote → ImportError 被宽 except 静默吞），「从底稿刷新」现真实调用 DisclosureEngine 填充链重算金额，区分"已刷新 N 单元格 / 需手动重填"。

**两个真实缺口（仍在）**：
1. **单元格级即时反查仍缺**：GtAmountCell 无右键"数字溯源"入口（grep 确认无 contextmenu/trace），仍需手动输入章节号走 ReportTracePanel。粒度太粗。
2. **stale 全局自动刷新未普及**：useProjectEvents 仅 6 文件接入，六大数据页未普遍订阅 `dataset:activated`/`dataset:rolled_back`/`year:changed` 自动 re-fetch。附注侧虽修了重算，但其余页 rollback 后仍可能看旧数。

**方案**：
- **复用而非新建**：在现有 trace_event_service / report_trace_service 基础上加细粒度入口（account_code + amount 反查受影响 report rows / workpapers / notes）；GtAmountCell 右键菜单加"数字溯源"，复用 ReportTracePanel 下钻结果。
- 六大数据页统一接入 useProjectEvents，监听三事件自动 re-fetch 或显示"数据已更新"横幅。

✅ 验收：GtAmountCell 右键"数字溯源"入口上线（复用现有 trace 服务）；六大数据页接入 useProjectEvents（6→12+）；rollback 后页面自动提示刷新。

### T6｜年度（year）全局上下文 — 良性

**现状**：projectStore 单一真源，syncFromRoute 自动同步，changeYear 发 `year:changed`。设计正确。
**残留**：与 T5 的 useProjectEvents 接入是同一件事——需确认所有数据页订阅 `year:changed` 并重载。

✅ 验收：切换年度后所有当前项目数据页自动重载（合并入 T5 验收）。

### T7｜权限（v-permission）— 现状稳定，建议加一致性测试

**现状**：ROLE_PERMISSIONS 前端硬编码兜底 + 后端 user.permissions 优先；v-permission 接入 23 文件。
**风险点（未变）**：前端 ROLE_PERMISSIONS 与后端权限表两套真源，"四点同步约定"维护成本高。

**方案**：让后端 `/api/users/me` 成为权限唯一真源，前端 ROLE_PERMISSIONS 降级为类型提示/离线兜底；加 CI 测试断言"前端硬编码权限码 ⊆ 后端定义全集"。

✅ 验收：新增后端权限码一致性测试；前端权限码集合是后端子集。

### T8｜编辑（编辑锁 + 编辑模式）— 仍缺通用锁

**现状（未变）**：useEditMode 接入约 11 视图；useEditingLock 4 文件但仅 WorkpaperEditor 真锁；后端只有 `WorkpaperEditingLock`（底稿专用）+ `adjustment_editing_locks`（调整专用）两套专用表，无通用 resource_type 锁。DisclosureEditor/AuditReportEditor 仍降级前端检测。

**方案**：后端建通用 `editing_locks` 表支持 resource_type 字段（memory 技术债 #2），让附注/报告编辑器用真锁。并发安全硬需求，不能长期降级。

✅ 验收：通用编辑锁端点上线；三大编辑器都用真后端锁；两人并发编辑同一附注时第二人看到只读 + 锁持有人提示。

### T9｜字体字号 / 显示偏好 — 良性

**现状**：displayPrefs 管理 fontSize/decimals/negativeRed/showZero/highlightThreshold，localStorage 持久化。fontConfig computed 已暴露。

✅ 验收：切换字号后核心表格行高/字号同步变化。

### T10｜查询（自定义查询 + 知识库 + 对话）— 健康

CustomQueryDialog / 知识库 BM25 加权上下文注入 / useAiChat 统一，整体健康，无重大断层。

### T11｜运维维护便利性 — D6 护城河持续有效，两项仍待办

**现状**：D6 MigrationRunner + 53 个 V*.sql（最高 V055）+ SchemaDriftDetector 自检 + /api/health 三态（healthy/degraded/unhealthy）持续有效。alembic 已彻底删除（git tag `pre-alembic-removal-2026-05-29`）。**原 v4.0/v4.1 的 P0「CI Alembic 一致性门禁」依旧作废。**

**仍然成立的真实风险（未变）**：
1. **可选依赖分散**：python-magic/psutil/prometheus_client/fakeredis 等降级策略散在各源文件 docstring，无集中文档。**OPTIONAL_DEPENDENCIES.md 仍未建**（Test-Path False）。
2. **superseded 数据膨胀**：purge + VACUUM 已落地，缺表膨胀监控告警。
3. **D6 自检 Playwright 实测**：migration-runner-resilience Sprint 5 收尾状态需复核。

**方案（已收窄）**：
- ~~CI Alembic 一致性门禁~~ → **作废**（alembic 已删）。
- 新建 `docs/OPTIONAL_DEPENDENCIES.md` 集中可选依赖 + 降级行为。
- 补"表膨胀监控"告警（n_dead_tup/n_live_tup > 阈值）纳入运维 checklist。

✅ 验收：OPTIONAL_DEPENDENCIES.md 建立；膨胀监控查询纳入运维 checklist。

### T12｜函证模块（明确的功能空洞）— 仍是 stub

**现状（未变）**：ConfirmationHub 是 GtEmpty 占位，confirmations.py 18 行返回 `{"status":"developing","note":"scheduled for R7+"}`。5 角色都会用到的核心审计功能（询证函发收/差异/替代程序）完全缺失。

**方案**：独立 Sprint 实现 6 步工作流（清单/发函/收函/差异/替代程序/差异转错报），差异自动建议 misstatement_service.create。

✅ 验收：函证 6 步闭环；函证差异一键转错报。

---

## 二·补、深挖发现（2026-06-05 二次复盘，v5.0 主体之外的证据驱动新增）

> 这 4 条是写完 v5.0 主体后再深挖（文件大小门禁 / 类型错误基线 / 功能空洞全盘点 / 技术债埋点）发现的，均带实测证据，部分**本轮会话自己引入**，如实记录不粉饰。

### T13｜文件大小治理门禁当前是红的（🔴 含本轮自引入回退）

**现状（实测）**：`backend/scripts/check/check_file_size.py` 当前 **exit=2，15 个文件超限或超 whitelist 基线 +5%**。其中**两个是本轮 disclosure-note-linkage spec 会话撑大的**，构成本轮自引入的回退：
- `backend/app/services/disclosure_engine.py`：基线 1676 → **1949 行**（新增 `refill_sections` 窄接口 ~270 行）
- `backend/app/services/note_validation_engine.py`：基线 813 → **995 行**（新增 `validate_all/get_latest_results/confirm_finding` 修校验端点 500）

其余 13 个超限：`migration_runner.py`(1026/930) / `wp_render_config.py`(1098/800) / `address_registry.py`(1092/800) / `consol_disclosure_service.py`(1736/1267) / `formula_engine.py`(1529/800) / `knowledge_index_service.py`(819/800) / `ledger_penetration_service.py`(804/800) / `report_line_mapping_service.py`(801/800) / `wp_fine_rule_engine.py`(892/800) / `commonApi.ts`(1516/1500) / `ConsolidationIndex.vue`(1717/1500) / `WorkpaperEditor.vue`(928/835) / `ConsolNoteTab.vue`(1522/1500)。

**关键根因**：`check_file_size.py` **未接入 CI**（`.github/workflows/*.yml` grep 无引用）→ 治理信号空转，50+ 文件的瘦身成果（workpaper-editor-slimdown / gtdform-test-and-shrink / disclosure-note 瘦身等）会慢慢回弹无人拦截。本轮把 disclosure_engine 撑大 273 行而 CI 全绿，正是这个空转的直接证据。

**方案**：
1. **即时修自引入回退**：把 `refill_sections` 抽到 `disclosure_engine` 伴生模块（如 `disclosure_refill.py`），把校验引擎的 3 个 router-facing 方法抽到 `note_validation_query.py`，让两文件回落基线内；或退而求其次更新 whitelist 基线（1676→1949 / 813→995）并注明原因。**优先抽模块，不优先抬基线**（符合"打磨应让文件变小不变大"）。
2. **系统补门禁**：把 `check_file_size.py` 接进 CI（先 informational/warning 级，给存量 15 文件留整改期，再转 error），否则瘦身是"做一轮弹一轮"。

✅ 验收：disclosure_engine.py + note_validation_engine.py 回落各自基线内（或基线更新有据）；`check_file_size.py` 进 CI（至少 informational）；存量 15 超限文件建整改清单。

### T14｜baselines.json 与真实状态疑似漂移

**现状（矛盾点）**：`.github/workflows/baselines.json` 声明 `vue-tsc-errors: 0` / `vitest-failed-tests: 0` / `vitest-skipped-tests: 7`，但 `frontend-consistency-m1` spec 的任务记录里多次出现"**26 个 pre-existing vue-tsc errors**"和"**33 failed tests（全部预存）**"。两者直接矛盾——要么基线是理想值从未真实测量，要么预存错误被长期默许却没记账。

**风险**：基线值若不可信，CI 的 `vue-tsc-errors=0` / `vitest-failed=0` 卡点要么是假绿（实际有错被 `|| true` 吞），要么 M1 记录的"预存错误"已被修复但基线未同步——无论哪种都说明"测量"与"基线"脱节。

**方案**：立项任何前端 spec 当天，实跑 `npx vue-tsc --noEmit` + `npx vitest run` 得到真实数字；对确实无法即修的预存错误，建一份**显式"已知失败清单"**（文件:行:原因）而非笼统"全预存"，并让 baselines 反映真实数（如 vue-tsc-errors: 26）+ 只减不增卡点。

✅ 验收：真实跑出 vue-tsc / vitest 当前数字；baselines.json 与实测一致（或建已知失败清单）；CI 卡点基于真实基线只减不增。

### T15｜功能空洞全盘点（v5.0 仅点名函证，此处补全）

**现状（实测）**：除 T12 的 ConfirmationHub 外，还有一批"developing/功能开发中"占位：
- 路由层挂载 `DevelopingPage` **3 处**。
- 视图层标"功能开发中/敬请期待"：`WorkHoursPage` / `RegulatoryFiling`（监管报送）/ `TemplateMarket`（模板市场）/ `WorkpaperFormEditor` / `WorkpaperHybridEditor` / `WorkpaperTableEditor` / `WorkpaperWordEditor`。
- 后端 router `NotImplementedError` 优雅降级：`signatures.py` / `query_builder.py`（非 stub，是降级分支，合理）。

**判断**：需把"空洞"分三类落账：
1. **真要做的核心功能**：函证（T12）、监管报送（RegulatoryFiling）——纳入功能补全 Sprint。
2. **疑似废壳应删**：`WorkpaperFormEditor / WorkpaperHybridEditor / WorkpaperTableEditor / WorkpaperWordEditor` 四个独立编辑器很可能已被统一的 `WorkpaperEditor`（componentType 注册表驱动）取代——若确认无路由引用即删（符合"死代码立即删"）。
3. **低优先长尾**：TemplateMarket（模板市场）等增值功能，标 developing 不误导即可。

**方案**：做一次"占位页 → 路由引用 → 是否被取代"的三步盘点，废壳删除、真功能进 Sprint、长尾保留标注。

✅ 验收：占位页分类清单（删/做/留）；确认废壳无路由引用后删除；函证 + 监管报送纳入 N4。

### T16｜技术债埋点规模（🟢 供参考，触碰即清）

**现状（实测）**：后端 `backend/app` 下 TODO/FIXME/XXX/HACK **92 处**；前端 `src` 下 TODO/FIXME **185 处**。量不小但高度分散，无单一热点。

**方案**：不设专项 Sprint，纳入"触碰即清"——改到含 TODO 的文件时顺手清理或转为 issue。低优先。

✅ 验收：无硬性验收，作为日常工程卫生指标，季度统计趋势只减不增。

---

## 三、优先级路线图（v5.0 — M1 已出列，重排剩余）

v4.2 的 M1（一致性收口）已整档完成出列。剩余按"对 5 角色的实际价值 × 修复紧迫度"重排。

### N1 联动闭环 + 并发安全（高价值 × 高紧迫，~6 人天）— 升为头号
> M1 出列后，单元格级溯源 + stale 自动刷新 + 通用编辑锁成为最高价值缺口。
1. T5 金额单元格右键"数字溯源"（复用现有 trace_event_service / report_trace_service，不新建端点）
2. T5/T6 六大数据页接入 useProjectEvents（stale 自动刷新 + 年度联动，6→12+）
3. T8 通用编辑锁端点（resource_type）+ DisclosureEditor/AuditReportEditor 真锁

### N2 运维护城河 + 工程治理（中价值 × 中紧迫，~3 人天）
4. **T13 即时修本轮自引入回退**：disclosure_engine.py + note_validation_engine.py 抽伴生模块回落基线（或更新 whitelist 有据）
5. T13 把 check_file_size.py 接进 CI（informational 级）+ 存量 15 超限文件整改清单
6. T14 实跑 vue-tsc/vitest 校准 baselines.json（建已知失败清单）
7. T11 OPTIONAL_DEPENDENCIES.md + 表膨胀监控告警
8. T7 后端权限单一真源一致性测试
9. T4 残留 4 处状态硬编码触碰即修

### N3 决策可信度（中价值 × 中紧迫，~4 人天）
10. P1 PartnerSignDecision 真实 PDF 预览（或明确标注"草稿预览"消除心理落差）
11. P2 签字面板展示"数据冻结影响"提示
12. E1 ShadowCompareRow verdict 映射对 EQCR 透明化

### N4 功能补全 + 空洞清理（高价值 × 低紧迫，独立 Sprint）
13. T15 占位页三步盘点（删废壳 Workpaper*Editor / 做函证+监管报送 / 留长尾）
14. T12 函证 6 步工作流
15. M3 三码体系集团项目树视图层（建项后端 USCC 已落地，补视图）
16. 大表格虚拟滚动全量化（YG2101 级别，144 裸 el-table 文件分批迁移）

### N5 一致性延伸（低紧迫，日常化）
17. T1 GtAmountCell 覆盖率 24%→80%（非专项 Sprint，触碰即接入）
18. T16 技术债埋点触碰即清（后端 92 + 前端 185 TODO）
19. 审计报告交付件管理中心（memory 待建 spec `audit-report-deliverable-center`，附注 Word 落盘 + 版本管理）
20. 所有底稿组件统一导入导出（memory 待建 spec `workpaper-unified-import-export`）

---

## 四、核心原则沉淀（写给后续每一轮）

1. **一致性 > 功能丰富，但一致性也会"做完"**：M1 证明组件接入是可收口的——六大核心页 GtAmountCell 100% + catch 裸用清零 + 死代码删除，靠的是"AST 精确分层 + CI 卡点只减不增 + 属性测试守护行为不变"，而非人工逐页替换。剩余覆盖率延伸目标日常化即可。
2. **声称完成 ≠ 真完成，但"实测"本身也要被实测**：本文档 v4.x 三次重测三次修正（master→main→work 分支），数字每次都变。**铁律：grep 返回 `[truncated]` 时禁止数可见行，必须用 `Select-String -List | Measure-Object` 精确计数。**
3. **基线要分层，不能拍总数**：ElMessage.error 总数里混着该改的（catch 裸用）和该留的（业务校验），M1 用 AST 区分后只治理 175/201，留下 26 业务校验——直接拿总数当债务会误伤。
4. **穿透是审计平台的灵魂**：正向 + 章节级反向都已通，附注假性刷新已修，缺的是**单元格级即时反查 + 全局 stale 自动刷新**——复用现有 trace 服务下沉粒度，不重复造端点。
5. **后端是资产**：事件链/穿透/下游绑定/章节级溯源/D6 迁移自检/附注真实重算是真正值钱的部分。
6. **D6 已解决 schema 漂移**：alembic 已删，D6 MigrationRunner + SchemaDriftDetector + /api/health 三态替代，原 P0 Alembic 门禁作废。**实测有效期 = 单次 grep 时刻，基线随分支演进失效，立项前必须按当时分支重测。**
7. **死代码立即删**（用户偏好）：AMOUNT_DIVISOR_KEY 已删，仅留守护测试证明删除安全。
8. **每条建议必须可验收**：grep 命中数 / 测试通过 / 真实样本跑通，拒绝"做了但说不清"。
9. **修历史债不限于本 spec 范围**（v5.0 新增）：校验端点 500 是 pre-existing（NoteValidationEngine 缺 3 方法），被附注 spec 的 Playwright E2E 暴露后顺手修了——全链路 E2E 的价值不仅验证本次改动，还能暴露历史债务。
10. **治理门禁不接 CI 等于没有**（v5.0 二次复盘新增，含自我批评）：`check_file_size.py` 未接 CI，导致本轮把 disclosure_engine.py 撑大 273 行而全绿无拦截——50+ 文件的瘦身成果正在无人看守地回弹。**新功能加代码后必跑 `check_file_size.py` 自查**，撑大文件优先抽模块而非抬基线。任何"只减不增"的治理脚本，不接 CI 就是空转。

---

## 附录 A：本轮实测证据索引（可复现，2026-06-05 @ work/2026-05-30-wp-specs）

> 🔢 标记为 PowerShell 精确计数（cwd=audit-platform/frontend，除注明外），其余为 grep/readFile 定性。

| 结论 | 命令（v5.0 实测值）|
|---|---|
| 🔢 视图 116 个 | `(Get-ChildItem src/views -Recurse -Filter *.vue).Count` |
| 🔢 GtAmountCell 11 文件 / 用量 105 | `Get-ChildItem src -Recurse -Filter *.vue \| Select-String '<GtAmountCell' -List \| Measure-Object`（文件）/ 去 `-List`（用量） |
| 🔢 GtEditableTable 5 文件 | 同上模式，pattern `<GtEditableTable` |
| 🔢 GtPageHeader 75 文件 | 同上模式，pattern `<GtPageHeader` |
| 🔢 handleApiError 257 文件 | `Get-ChildItem src -Recurse -Include *.vue,*.ts \| Select-String 'handleApiError' -List \| Measure-Object` |
| 🔢 ElMessage.error 57 处 / 33 文件 | 出现数去掉 `-List`，文件数加 `-List` |
| catch 块内 ElMessage.error = 0 | `.github/workflows/baselines.json` → `elmessage-error-in-catch: 0` + `node scripts/audit-elmessage-error.mjs` |
| AMOUNT_DIVISOR_KEY 仅 1 守护测试 | `Get-ChildItem src -Recurse -Include *.vue,*.ts \| Select-String 'AMOUNT_DIVISOR_KEY'` → 仅 `property-m1-dead-code-invariance.spec.ts` |
| 🔢 裸 el-table 144 文件 | `Select-String '<el-table[ >]' -List \| Measure-Object` |
| 🔢 v-permission 23 文件 | `Select-String 'v-permission' -List \| Measure-Object` |
| 🔢 useProjectEvents 6 文件 | `Select-String 'useProjectEvents' -List \| Measure-Object` |
| useEditingLock 4 文件（1 真锁） | grep `useEditingLock`（WorkpaperEditor/DisclosureEditor/AuditReportEditor/LockConflictPanel） |
| 🔢 后端 408 service / 291 router / 733 测试（cwd=repo root） | `(Get-ChildItem backend/app/services -Filter *.py).Count` 等 |
| 🔢 前端 235 测试文件 | `(Get-ChildItem src -Recurse -Include *.spec.ts,*.test.ts).Count` |
| 🔢 迁移 53 个 V*.sql（最高 V055，cwd=repo root） | `(Get-ChildItem backend/migrations -Filter V*.sql).Count` + Sort Last |
| M1 已归档 | `Test-Path .kiro/specs/_archive/06-engineering-governance/frontend-consistency-m1` = True |
| 校验端点 500 已修 | readFile note_validation_engine.py（validate_all/get_latest_results/confirm_finding 存在）|
| 附注假性刷新已修 | readFile note_stale_service.py（refresh_from_workpaper 接 DisclosureEngine.refill_sections）|
| 函证仍 stub | readFile confirmations.py（18 行返回 developing）|
| 通用编辑锁仍缺 | grep `resource_type.*lock` → 仅 WorkpaperEditingLock + adjustment_editing_locks |
| OPTIONAL_DEPENDENCIES.md 未建 | `Test-Path docs/OPTIONAL_DEPENDENCIES.md` = False |
| D6 迁移 + 漂移自检 | `Test-Path backend/alembic`（已删）/ readFile migration_runner.py / schema_drift_detector.py |
| 🔴 文件大小门禁红 15 文件 | `python backend/scripts/check/check_file_size.py` → exit 2，含本轮撑大的 disclosure_engine.py(1949/1676) + note_validation_engine.py(995/813) |
| check_file_size 未接 CI | grep `.github/workflows/*.yml` `check_file_size` → 无匹配 |
| baselines.json 疑漂移 | `baselines.json` vue-tsc-errors:0 vs M1 spec 记录 26 预存 |
| 占位页盘点 | router DevelopingPage×3 + 视图 WorkHoursPage/RegulatoryFiling/TemplateMarket/Workpaper*Editor×4 标 developing |
| 技术债埋点 | 后端 92 TODO/FIXME/XXX + 前端 185 TODO/FIXME |

> 文档结束。建议下一步：将 N1（联动闭环 + 并发安全）收口为一个 spec 三件套（requirements/design/tasks），按"5 角色轮转 PDCA"推进。**注意：N1 的 GtAmountCell 右键溯源、useProjectEvents 普及、通用编辑锁是 spec 的核心可验收项，进入 requirements 前以本 v5.0 基线订正后的数字为准——并在立项当天按当时分支最新状态再重测一次，不得直接引用本文档数字。**
