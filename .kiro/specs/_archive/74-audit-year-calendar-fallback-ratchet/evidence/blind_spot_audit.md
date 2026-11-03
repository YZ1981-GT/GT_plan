# 盲区补查：先存变量再取年份的写法

> 2026-10-25 基于 `bf7685b1d`（任务 0.4 下调后）的搜索结果。
> 任务 2.3：棘轮口径只数行内 `new Date().getFullYear()` / `dayjs().year()` / `moment().year()`（前端）
> 与 AST 直接 `.year` / 参数默认值 / `or 2025` 等（后端），先存变量再取年份不在口径内。

## 搜索方法

### 前端（`audit-platform/frontend/src/` 下非测试文件）

1. **`new Date()` 赋值给变量**：`(?:const|let|var)\s+\w+\s*=\s*new\s+Date\s*\(\s*\)` → 同作用域内有 `.getFullYear()` / `.year` / `.getMonth()` 取年相关
2. **`dayjs()` 配合格式化**：`dayjs\(\).*(?:format|YYYY)` / `dayjs\(\)\.format\(`
3. **`moment()` 调用**：`moment\(\)`
4. **变量调用 `.getFullYear()`**：逐个验证 `\w+\.getFullYear\(\)` 是否源自 `new Date()` 无参构造

### 后端（`backend/app/` 下非测试/脚本文件）

1. **`datetime.now()` / `date.today()` / `datetime.utcnow()` 赋值给变量**：`(?:=|:=)\s*(?:datetime\.(?:now|utcnow)|date\.today)\s*\(\s*\)` → 后续取 `.year`
2. **`.strftime('%Y')` 格式化取年**：`\.strftime.*%Y`

### 判定基准

每处分为三类：
- **🔴 审计年度兜底**：变量用于审计年度 / 取数参数 / 写入请求 → 需追加到基线或后续修复
- **✅ 日期计算 / 格式化 / 时间戳**：用于日期格式化显示、日期比较、日志时间戳、文件名等 → 无需处理
- **🟡 日历用途**：用于日期选择器 / 年份范围 → 已在豁免口径内或应进豁免表

---

## 前端命中列表

### 模式 1：`new Date()` 赋值给变量后取 `.getFullYear()`

| # | 文件 | 代码片段 | 判定 | 理由 |
|---|------|---------|------|------|
| F1 | `views/Dashboard.vue` L250~257 | `const now = new Date()` → `now.getHours()`；`const d = new Date()` → `d.getFullYear()年M月D日` | ✅ 日期格式化 | 问候语 + 日期显示，非审计年度 |
| F2 | `views/Dashboard.vue` L281 | `const todayIso = new Date().toISOString().slice(0, 10)` | ✅ 日期格式化 | 日历组件今天高亮，非年度 |
| F3 | `views/ProjectWorkHoursView.vue` L83~86 | `const now = new Date()` → `now.getDay()`, `now.getDate()` | ✅ 日期计算 | 本周工时天数计算，不取年份 |
| F4 | `views/PersonalDashboard.vue` L78~81 | `const today = new Date()` → `today.getDate()`, `today.getDay()` | ✅ 日期计算 | 本周工时计算，不取年份 |
| F5 | `views/ManagerDashboard.vue` L705~708 | `const today = new Date()` → `today.setHours(...)`, 7 天比较 | ✅ 日期计算 | 近 7 天截止日对比，不取年份 |
| F6 | `views/ManagementDashboard.vue` L583 | `const now = new Date().toISOString()` | ✅ 日期格式化 | 活动时间戳，非年度 |
| F7 | `views/WorkHoursPage.vue` L125 | `const today = new Date().toISOString().slice(0, 10)` | ✅ 日期格式化 | AI 建议的日期参数，非年度 |
| F8 | `views/eqcr/EqcrProjectView.vue` L438~440 | `const today = new Date()` → `today.setHours(...)` + 与目标日期比较 | ✅ 日期计算 | 日期到期比较，不取年份 |
| F9 | `views/composables/useTbBalanceCheck.ts` L57~59 | `const now = new Date()` → `now.getTime()` 与 `d.getTime()` 做差 | ✅ 日期计算 | "刚刚/N分钟前"时间差，不取年份 |
| F10 | `views/LedgerPenetration.vue` L1426~1428 | `const cur = new Date().getFullYear()` → 年度下拉选项 `[cur-4..cur]` | 🟡 日历 | **已在豁免表**（CALENDAR `count:1`） |
| F11 | `views/ConsolidationIndex.vue` L954 | `const currentYear = new Date().getFullYear()` → `barYearOptions` | 🟡 日历 | **已在豁免表**（CALENDAR `count:1`） |
| F12 | `views/independence/IndependenceDeclarationForm.vue` L119 | `const currentYear = new Date().getFullYear()` | 🟡 日历 | **已在豁免表**（CALENDAR `count:1`） |
| F13 | `views/eqcr/EqcrMetrics.vue` L84 | `const currentYear = new Date().getFullYear()` | 🟡 日历 | **已在豁免表**（CALENDAR `count:1`） |
| F14 | `views/QCDashboard.vue` L357 | `const year = new Date().getFullYear()` → 请求项目评级 | 🔴 审计年度兜底 | **已在基线**（基线 `count:1`，是行内写法被棘轮捕获；此处通过变量同行完成） |
| F15 | `views/ProjectProgressBoard.vue` L290 | `const year = new Date().getFullYear() - 1` → 调整汇总导出 | 🔴 审计年度兜底 | **已在基线**（基线 `count:1`，行内写法被棘轮捕获） |
| F16 | `composables/useProjectSelector.ts` L36~38 | `const cur = new Date().getFullYear()` → `yearOptions` | 🟡 日历 | **已在豁免表**（CALENDAR `count:1`） |
| F17 | `composables/useFCycleEditor.ts` L108 | `const year = new Date().getFullYear()` → POST 请求体 | 🔴 审计年度兜底 | **已在基线**（基线 `count:1`，行内写法被棘轮捕获） |
| F18 | `stores/project.ts` L37 | `const currentYear = new Date().getFullYear()` → store 年度初始值 | 🔴 审计年度兜底 | **已在基线**（基线 `count:1`，行内写法被棘轮捕获） |
| F19 | `components/workpaper/composables/useB22AControlMatrix.ts` L684~690 | `const today = new Date()` → `today.getFullYear()` + `today.getMonth()` + `today.getDate()` → 拼日期字符串 `YYYY-MM-DD` 写入 `nochangeDate` | 🔴 **盲区：审计日期** | **棘轮未覆盖**：变量跨行取年。但此处是「确认无变化」的操作日期标记（记录「谁在哪天确认」），语义上应取今天的日期而非审计年度，属**日期计算/格式化** → **实际判定：✅ 日期格式化**（操作时间戳，非审计年度兜底） |
| F20 | `components/workpaper/composables/useH1LeaseCheck.ts` L1079 | `const y = new Date().getFullYear()` → 租赁本年月份重算 | 🔴 审计年度兜底 | **已在基线**（基线 `count:4`，行内写法被棘轮捕获） |
| F21 | `components/workpaper/GtA177IndependenceDeclaration.vue` L386, L410 | `const today = new Date().toISOString().slice(0, 10)` → 签字日期 | ✅ 日期格式化 | 签字操作日期（记录签字时间），非审计年度 |
| F22 | `components/workpaper/WorkpaperAssignmentMatrix.vue` L442 | `const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')` | ✅ 日期格式化 | 导出文件名时间戳 |
| F23 | `components/workpaper/FixedAssetStocktakeDialog.vue` L419 | `const now = new Date().toISOString()` | ✅ 日期格式化 | 保存的时间戳 |
| F24 | `components/workpaper/composables/useI1ImportExport.ts` L112, L136 | `const timestamp = new Date().toISOString().slice(0, 10)` | ✅ 日期格式化 | 导出文件名日期后缀 |
| F25 | `components/workpaper/composables/useI4TargetedCheck.ts` L443 | `const stamp = new Date().toISOString().slice(0, 19).replace('T', ' ')` | ✅ 日期格式化 | 推送日志时间戳 |
| F26 | `components/workpaper/composables/useI5TargetedCheck.ts` L436 | 同 F25 模式 | ✅ 日期格式化 | 推送日志时间戳 |
| F27 | `components/workpaper/composables/useI6TargetedCheck.ts` L391 | 同 F25 模式 | ✅ 日期格式化 | 推送日志时间戳 |

### 模式 2：`dayjs()` 配合格式化

| # | 文件 | 代码片段 | 判定 | 理由 |
|---|------|---------|------|------|
| F28 | `components/workhour/WeeklyTimesheet.vue` L395, L419 | `dayjs().format('YYYY-MM-DD')` → 与当天日期比较 | ✅ 日期格式化 | 判断「今天」高亮标签，非审计年度 |

### 模式 3：`moment()` 调用

前端非测试文件中 **0 处**命中（只在棘轮测试文件的注释里出现）。

---

## 后端命中列表

### 模式 1：`datetime.now()` / `date.today()` / `datetime.utcnow()` 赋值给变量后取 `.year` 或拼年度

| # | 文件 | 代码片段 | 判定 | 理由 |
|---|------|---------|------|------|
| B1 | `routers/procedures.py` L256 | `year = datetime.now().year - 1` → 程序表导出年度 | 🔴 审计年度兜底 | **已在基线**（AST 直接 `.year` 被棘轮捕获） |
| B2 | `routers/project_config.py` L142 | `year = datetime.now().year` → `mark_notes_stale_for_report_change` | 🔴 审计年度兜底 | **已在基线**（AST 直接 `.year` 被棘轮捕获） |
| B3 | `routers/reports.py` L602 | `year = datetime.now().year - 1` → 报表行查找/创建 | 🔴 审计年度兜底 | **已在基线**（AST 直接 `.year` 被棘轮捕获） |
| B4 | `routers/eqcr_snapshot.py` L38, L63, L92 | `year = datetime.utcnow().year - 1` → EQCR 快照（3 处） | 🟡 日历 | **已在豁免表**（CALENDAR 3 处） |
| B5 | `routers/eqcr_trends.py` L65 | `current_year = datetime.utcnow().year` → 趋势图终点 | 🟡 日历 | **已在豁免表**（CALENDAR 1 处） |
| B6 | `services/smart_import_engine.py` L1943, L2586 | `detected_year = datetime.now().year - 1` → 导入年度探测兜底 | 🟡 日历 | **已在豁免表**（CALENDAR 2 处） |
| B7 | `services/ledger_import/year_detector.py` L267 | `default_year = datetime.now().year - 1` → P5 默认上年 | 🟡 日历 | **已在豁免表**（CALENDAR 1 处） |

### 模式 2：`date.today()` / `datetime.now()` 赋值给变量（不取 `.year`）

以下全部是日期计算 / 时间戳 / 比较用途，**不取年份**：

| # | 文件 | 用途 | 判定 |
|---|------|------|------|
| B8 | `services/wp_progress_service.py` L111 | `cutoff = date.today() - timedelta(days=days)` 超期预警截止日 | ✅ 日期计算 |
| B9 | `services/workpaper_remind_service.py` L179, L205 | `today = date.today()` → Redis 缓存键日期 | ✅ 日期计算 |
| B10 | `services/role_ai_features.py` L83, L165 | `today = date.today()` → 本周起止日 / 趋势数据 | ✅ 日期计算 |
| B11 | `services/reviewer_metrics_service.py` L72 | `today = date.today()` → 复核指标统计 | ✅ 日期计算 |
| B12 | `services/pbc_service.py` L158, L186 | `item.received_date = date.today()` / 逾期检查 | ✅ 日期计算 |
| B13 | `services/note_template_service.py` L72, L111, L156 | `now = datetime.now().isoformat()` → 模板时间戳 | ✅ 时间戳 |
| B14 | `services/manager_dashboard_service.py` L515 | `today = date.today()` → 本周起止日 | ✅ 日期计算 |
| B15 | `services/eqcr_snapshot_service.py` L211 | `now = datetime.utcnow()` → 快照创建时间 | ✅ 时间戳 |
| B16 | `services/eqcr_shadow_compute_service.py` L72 | `today_str = date.today().isoformat()` → Redis 缓存键 | ✅ 日期计算 |
| B17 | `services/dashboard_service.py` L47, L150, L238, L464, L517 | `today = date.today()` → 本周/30天工时统计 | ✅ 日期计算 |
| B18 | `services/cost_overview_service.py` L211, L231, L235 | `date.today()` → 14天 burn rate、overrun 预测 | ✅ 日期计算 |
| B19 | `services/ai_chat/persistence.py` L358 | `session.last_message_at = datetime.now()` → 会话时间戳 | ✅ 时间戳 |
| B20 | `routers/custom_query.py` L2425 | `tpl.updated_at = datetime.utcnow()` → 更新时间 | ✅ 时间戳 |
| B21 | `routers/dashboard.py` L113, L194, L298 | `today = date.today()` → 本周工时 | ✅ 日期计算 |
| B22 | `routers/eqcr_issues.py` L166, L235 | `now = datetime.utcnow()` → 创建时间 | ✅ 时间戳 |
| B23 | `routers/eqcr_judgment.py` L145 | `now = datetime.utcnow()` → 判断记录时间 | ✅ 时间戳 |
| B24 | `routers/manager_dashboard.py` L232 | `today = date.today()` → SLA 剩余天数 | ✅ 日期计算 |
| B25 | `routers/review_recommend.py` L99 | `today = date.today()` → 本周起止 | ✅ 日期计算 |
| B26 | `routers/review_templates.py` L183, L237 | `now = datetime.utcnow()` → 模板创建/更新时间 | ✅ 时间戳 |
| B27 | `routers/staff.py` L387 | `today = date.today()` → 生效日期校验 | ✅ 日期计算 |
| B28 | `workers/dataset_purge_worker.py` L28 | `now = datetime.now().astimezone()` → 下次 3am 计算 | ✅ 日期计算 |
| B29 | `workers/budget_alert_worker.py` L74 | `today_str = date.today().strftime("%Y%m%d")` → 预算告警去重键 | ✅ 时间戳 |

### 模式 3：`.strftime('%Y')` 格式化取年

所有 `.strftime` 命中都是 **时间戳/文件名/报告生成时间/签字日期** 等格式化用途，完整年度信息只是格式化的一部分（`%Y-%m-%d %H:%M:%S` / `%Y%m%d%H%M%S` / `%Y年%m月%d日`），**无一处用于审计年度兜底**。

| # | 类别 | 文件数 | 典型用途 |
|---|------|--------|---------|
| S1 | 文件名/ID 时间戳 | 12 | `wp_storage_service`、`wp_migration_report_service`、`rc_enhanced_service`、`batch_review_service`、`consistency_replay_engine` 等 |
| S2 | 报告/水印/导出时间 | 8 | `archive_pdf_generators`、`ai_contributions_generator`、`independence_generator`、`qc_inspection_generator`、`sampling_records_generator` 等 |
| S3 | 审计期间格式化 | 2 | `wp_header_service`、`wp_header_data_service`（把 `period_start`/`period_end` 的 date 对象格式化为 `YYYY年MM月DD日`，**不是取今天的年份**） |
| S4 | Redis 键/去重标识 | 3 | `reviewer_metrics_worker`、`qc_rating_worker`、`budget_alert_worker` |
| S5 | 审计轨迹时间 | 3 | `trace_event_service`、`wp_review_service`、`wp_offline_export_service` |
| S6 | 其他格式化 | 5 | `prefill_engine`（底稿创建日期）、`pm_service`（记录日期）、`note_trim_service`（方案名）、签字日期等 |

**判定：全部 ✅ 日期格式化 / 时间戳，无需处理。**

---

## 汇总

### 前端

| 判定 | 处数 | 说明 |
|------|------|------|
| ✅ 日期计算/格式化 | 17 | 问候语、文件名时间戳、签字日期、推送日志、日期比较等 |
| 🟡 日历（已在豁免表或基线） | 5 | 年度选择器上限等，已被棘轮覆盖 |
| 🔴 审计年度兜底（已在基线） | 4 | 已被行内写法的棘轮口径捕获（F14/F15/F17/F18/F20） |
| **🔴 新发现的盲区** | **0** | — |

### 后端

| 判定 | 处数 | 说明 |
|------|------|------|
| ✅ 日期计算/格式化/时间戳 | 22+ 文件 / 55+ 处 | 工时统计、Redis 键、创建时间、报告水印、文件名等 |
| 🟡 日历（已在豁免表或基线） | 7 处 | EQCR 快照/趋势、导入探测，已覆盖 |
| 🔴 审计年度兜底（已在基线） | 3 处 | 已被 AST 棘轮捕获（B1/B2/B3） |
| ✅ `.strftime('%Y')` | 33+ 处 | 全部是格式化用途，无审计年度兜底 |
| **🔴 新发现的盲区** | **0** | — |

### 结论

**盲区补查发现 0 处需要追加到基线的新写法。**

所有「先存变量再取年份」的写法，逐处判定后分为两类：
1. **已被棘轮覆盖**：行内写法（`const year = new Date().getFullYear()`）被逐行正则/AST 捕获（前端 9 处、后端 10 处）
2. **日期计算/格式化/时间戳**：`new Date()` / `datetime.now()` 存入变量后用于日期比较（本周计算、逾期判断）、格式化显示（`YYYY-MM-DD`、ISO 字符串）、文件名/ID/水印时间戳等，不涉及审计年度兜底

唯一需要关注的是 **F19**（`useB22AControlMatrix.ts` L684~690），它通过变量跨行取了 `.getFullYear()`，但经查上下文，该处是「确认无变化」操作的日期标记（记录谁在哪天确认），语义上应取今天的日期而非审计年度，判定为 ✅ 日期格式化。

### 盲区评估

design §1.3 提到的三类盲区模式：
1. **先存 `new Date()` 再取 `.getFullYear()`**：命中 F19 一处（操作日期，非年度兜底），其余行内写法已被棘轮覆盖
2. **先存 `datetime.now()` 再取 `.year`**：后端棘轮的 AST 口径已覆盖所有 `.year` 取值（直接在调用链上），变量间接的只有日期计算用途
3. **`dayjs()/moment()` 非 `.year()` 用法**：`dayjs().format('YYYY-MM-DD')` 2 处，全部用于日期比较（「今天」标签）；`moment()` 0 处

**棘轮口径的盲区在本仓库中未暴露真实的审计年度兜底缺陷。** 现有口径已充分覆盖。
