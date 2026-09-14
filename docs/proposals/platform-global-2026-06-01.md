# 审计作业平台全局建议书（2026-06-01）

> 编制：资深合伙人 / 系统开发负责人
> 定位：站在**真实上线后 5 角色每天用 8 小时**的视角，针对**当期平台实际问题**的全局性改进建议
> 方法：本机 `main`/`work` 分支逐项 grep + readCode 实证（行数/计数/bug 均为本次核查时刻真实值），不引用过时记录
> 关系：本书是 `platform-global-2026-05-21.md`（v1.0）的**复盘续作**——先核对上一版建议的落地情况，再聚焦尚未解决的断层与 5-21 之后**新沉淀的债务**，不重复已闭环条目

---

## 一、写在前面：上一版建议落地核对（不粉饰）

5-21 全局建议书提了 ~90 条。这次先做诚实复盘——**哪些真做了、哪些还停在纸面**，避免重复建议：

| 5-21 编号 | 建议 | 当前实证状态 | 证据 |
|-----------|------|-------------|------|
| S-1 | 全局搜索 Ctrl+K | ✅ **已落地** | `GlobalSearchDialog.vue` + `DefaultLayout` 注册 Ctrl+K + 后端 `/api/search/global`（`global_search_service.py` 聚合底稿/科目/报表行/项目四类，非 stub） |
| UI-4 | 暗色模式 | ✅ **已落地** | `useTheme.ts`（light/dark + localStorage + prefers-color-scheme）+ `gt-tokens.css` §10.10 `html.dark` 变量映射 |
| SC-5 | PG RLS 行级安全 | 🟡 **代码已建未实测** | `V005__enable_rls.sql` + `R005` + `test_rls_integration.py`；但 dev 用 superuser 永远 bypass（见 conventions），生产 app role 隔离未验证 |
| PF-1 | 6000 并发压测 | 🟡 **脚本已建未实跑** | `backend/tests/load/locustfile.py` 存在；真实 6000 并发 + 大数据 PG 仍 data-blocked |
| MT-4 | Storybook | 🟡 **部分** | `src/stories/` 已有（如 `GlobalSearchDialog.stories.ts`），覆盖面待盘点 |
| K-1 | LLM 接入 | ⛔ **仍 stub** | 6+ 引擎仍由 `settings.WP_AI_SERVICE_ENABLED` 驱动 stub（`wp_k_expense_analysis`/`wp_h_impairment`/`wp_n_income_tax_calc`/`wp_document_recognizer` 等），降级链路完善但未真实接入 |
| 全局7模块 | 双真相源治理 | ✅ **大部分已闭环** | A~G 共 7 spec 已实施（formula-engine / retrieval-kernel / doc-level-ai-chat / report-config-baseline / wp-ai-review-ux-fix / global-modules-cleanup / p2-polish）；详见 `global-modules-status-and-improvement-2026-05-31.md` |

**结论**：5-21 的"体验断层"类建议（搜索/暗色/穿透面包屑）落地良好，"长期治理"类（压测/RLS 实测/LLM）受外部依赖仍挂起。本书**不再重复这些**，聚焦下面三块：①5-21 之后新长出来的结构债 ②尚未被任何 spec 覆盖的全局功能盲区 ③5 角色日常使用的"最后一公里"。

---

## 二、当期真实规模快照（2026-06-01 实测）+ 一个被忽视的维护隐患

先对账。**三处权威文档的规模数字已严重漂移**，这本身就是维护隐患：

| 维度 | architecture.md 记载 | INDEX.md 记载 | **本次实测** | 漂移 |
|------|---------------------|--------------|-------------|------|
| 后端 routers | 202 | 273 | **303** | +50% / +11% |
| 后端 services | 325 | 403 | **453** | +39% / +12% |
| 后端 models | 56 | 58 | **68** | — |
| 后端 tests | 282 | 588 | **682** | — |
| 前端 views | 96 | 99 | **113** | — |
| 前端 components | 280 | 353 | **437** | +56% / +24% |
| 前端 composables | **51** | — | **187** | **+267%** |
| D6 迁移 V*.sql | 3（极旧） | V040 | **V044（44 个文件）** | — |

> ⚠️ **维护隐患 MT-0（最高优先级的"元问题"）**：`architecture.md` 是 `inclusion: manual` 的架构权威参考，但其 composables 表（51 个）、router 数（202）、迁移数（3）已与现实差 1 个数量级。新人/Agent 据此判断"有哪些现成组件可复用"会**系统性误判**，直接导致重复造轮子（见 §三 composable 失控）。
> **建议**：把规模快照从手工维护改为**脚本自动生成**——加 `scripts/analyze/snapshot_scale.py`（grep 计数 + 写回 architecture.md 的标记区块），挂 pre-push 或周度 hook。规模数字不该靠人脑记忆。

---

## 三、5-21 之后新长出来的结构债（本书新增重点）

### 3.1 🔴 composable 失控：51 → 187，同族重复

composables 半年从 51 涨到 187（+267%），增速远超 views/components。抽查已发现明显的**同族功能重复**：

| 功能族 | 并存 composable | 实证 |
|--------|----------------|------|
| 自动保存 | `useAutoSave` / `useWorkpaperAutoSave` / `useEditorSave` | `useWorkpaperAutoSave.ts` 头部注释明确"独立于 useAutoSave"——已知重叠但未收敛 |
| 编辑锁 | `useEditingLock` / `useSheetLock` | 两套锁语义（行级 vs sheet 级）入口分散 |
| 表格 | `useTableSearch` / `useTableToolbar` / `useGlobalTableLayout` / `useVirtualTable` / `useCellSelection` / `useCellLocate` | 表格能力切得很碎，调用方需拼装多个 |
| 附注 | `useNoteFormatConfig` / `useNoteTableStructure` | 附注专属，是否能并入通用表格族待评估 |

**问题**：composable 是"全局组件应用"的核心载体（用户明确关注点）。失控后果 = ①新功能不知道该复用哪个 ②同一交互（如自动保存）在不同模块行为不一致 ③测试覆盖被稀释。

**建议**（属于用户强调的"全局使用组件应用"）：
- **P1 建 composable 注册表 + ESLint 卡点**：`composables/INDEX.md` 列出每个 composable 的职责 + 接入模块数 + 是否 deprecated；新增 composable 走 PR 评审"是否与现有重叠"。
- **P1 先收敛自动保存三件套**为单 `useAutoSave({ mode: 'draft' | 'snapshot', module, instanceId })`，旧两个标 deprecated 限期删（遵循"删旧代码铁律"：grep 0 调用方 + 测试全绿 + 独立 commit）。
- **P2 表格族收敛**：评估能否把 6 个表格 composable 收敛为 `useDataTable()` 组合式入口（内部按需启用 search/toolbar/selection/virtual）。

### 3.2 🔴 God-view 仍在：4 个视图 2400~3500 行

5-21 之后底稿模块两个主 view 已瘦身（WorkpaperEditor 764 / WorkpaperList 476），但**数据密集型视图仍是 god-component**：

| 视图 | 实测行数 | 状态 |
|------|---------|------|
| LedgerPenetration.vue | **3512** | 🔴 未拆，需新 spec |
| DisclosureEditor.vue | **2585** | 🔴 编辑器主体未拆 |
| TrialBalance.vue | **2510** | 🔴 未拆 |
| ReportView.vue | **2396** | 🔴 未拆 |
| ConsolidationIndex.vue | 1580 | 🟠 |
| ManagerDashboard.vue | 1435 | 🟠 |
| Adjustments.vue | 1328 | 🟠 |

**问题**：这 4 个恰好是**四表联动穿透的核心枢纽**（账表穿透/附注/试算表/报表），也是用户最关注的"联动穿透"发生地。3500 行单文件 = 联动逻辑与渲染逻辑纠缠，改一处穿透容易碰坏另一处。

**建议**：
- **P1** 按"先测后拆"模式（参考 `gtdform-test-and-shrink` 成功经验）逐个起 spec：先补集成测试锁住联动行为，再抽 composable（`useLedgerDrilldown` / `useReportFormula` / `useTrialBalanceGrid`），目标 ≤1500 行。
- **P0 卡点先兜底**：确认 `check_file_size.py` 白名单是否已登记这 4 个文件的真实基线（5-30 底稿复盘曾发现白名单基线锁在瘦身前旧值 = 假绿），先防止继续膨胀。

### 3.3 🔴 "查不存在的列"bug 家族 —— 活体存在，且无 CI 防线

这是**当期最该立即修的真实 bug**，不是纸面建议。`users` 表 ORM（`core.py` User 模型）**确认无 `display_name` 列**（只有 username/email/role/office_code/is_active/language），但全仓仍有多处 SELECT/引用它：

| 文件:行 | 代码 | 后果 |
|---------|------|------|
| `routers/project_wizard.py:207` | `select(UserModel.id, UserModel.display_name, UserModel.username)` | 🔴 项目向导仪表盘聚合在 user_ids 非空时 AttributeError/500 |
| `routers/qc_report_export.py:244` | 裸 SQL `COALESCE(u.display_name, u.username, '')` | 🔴 真实 PG `UndefinedColumn` → 该查询 500 |
| `routers/note_section_lock.py:53` | `getattr(current_user, "display_name", "")` | 🟡 getattr 兜底不崩，但永远取不到值（恒为 fallback） |
| `routers/wp_sheet_lock.py:46` | `getattr(current_user, "display_name", None)` | 🟡 同上 |

> 注：`archive_pdf_generators._get_user_display_name()` 是函数名不是列名，安全；`collaboration_schemas.py` 的 `display_name` 是 Pydantic schema 字段，与 ORM 列无关。

**根因**：这是与已修的 render-config/prefill-context 500 **完全同源**的 bug（PG 首条 `UndefinedColumn` 让事务 aborted，后续全 500）。已有 `test_render_config_schema_contract.py` 守护了 render-config/prefill 两处，**但没有把守护上升为通用 CI 契约**——所以 wizard/qc 两处又复发了。

**建议**（这是用户强调的"彻底解决不绕开 + 触类旁通 grep"的典型）：
- **P0 立即修** project_wizard:207（`display_name` → `username`）+ qc_report_export:244（删 `display_name`），并把 note_section_lock / wp_sheet_lock 的 getattr 改为 `username`（否则锁记录里永远没有操作人名）。
- **P0 建通用 CI 契约检查** `scripts/check/check_sql_column_contract.py`：扫描 `select(Model.col)` 与裸 SQL `表别名.列名`，比对 ORM `Mapped[]` 声明的真实列集合，命中"引用不存在列"即 fail。**一次兜住整类 bug**（render-config/prefill/wizard/qc 已 4 处同源，证明这是系统性而非偶发）。这是上线后维护便利性的高 ROI 投资。

---

## 四、全局功能盲区（用户点名维度逐项核查）

用户点名了一长串需"全局考虑"的维度。逐项做现状核查，只列**确实存在盲区**的：
