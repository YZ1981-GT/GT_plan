# Requirements Document — Phase 6: 数值精度 + 权限统一 + 安全加固

## 一、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-22 | 初始起草，基于《平台全局建议书》N-1~N-3 / R-4 / A-4 / SC-2 / M-1 / RV-1 六项 |
| v1.1 | 2026-05-22 | Sprint 0 基线实测填充 6 项 + V007→V008 迁移编号修正 + F1 ESLint 降级 warn + F8 依赖 F4 注记 + 回归白名单 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Phase 1~5 specs (全部完成) | 前置 | ✅ 已完成 |
| formatters.ts (fmtAmountAccounting/fmtAmountUnit) | 前端 | ✅ 已有 |
| usePermission composable (ROLE_PERMISSIONS 硬编码) | 前端 | ✅ 已有（待改造） |
| ProjectAssignment 模型 (project_assignments 表) | 后端 | ✅ 已有 |
| ReviewRecord 模型 (review_records 表) | 后端 | ✅ 已有 |
| security.py (verify_password / hash_password) | 后端 | ✅ 已有 |
| WpReviewStatus 枚举 (2 级: level1/level2) | 后端 | ✅ 已有（待扩展） |
| Project 模型 (projects 表) | 后端 | ✅ 已有（需扩展 review_config） |
| router/index.ts (meta.roles 部分路由) | 前端 | ✅ 已有（待改造） |
| Decimal.js | 前端新增依赖 | ❌ 需安装 |
| PartnerProjectDashboard.vue | 前端 | ✅ 已有 |
| displayPrefs store | 前端 | ✅ 已有 |
| F4 项目级权限端点（F8 前置依赖） | 本 spec 内部 | ❌ F4 必须先于 F8 实施 |

---

## 二、为什么做（业务痛点）

### 2.1 前端金额浮点精度风险（N-1）
- **痛点**：前端 JavaScript Number 类型对超过 2 位小数的金额运算存在精度丢失（如 0.1+0.2≠0.3），审计金额计算可能产生分差
- **影响角色**：所有用户（金额数据准确性）
- **技术根因**：前端金额计算直接使用 Number 类型四则运算，无 Decimal 库保护；formatters.ts 仅在"显示层"格式化，计算层无精度保障
- **Sprint 0 实测**：grep 全仓库 `.vue`/`.ts` 文件中金额相关运算（`+`/`-`/`*`/`/` 涉及金额变量），实测 30 处需改造（分布于 12 个文件：LedgerPenetration / Adjustments / ConsolidationIndex / DCountDialog / CapitalReserveSheet / TAccountEditor / InternalCashFlowSheet / ConfirmationSummary / InternalTradeSheet / AuditFindingPanel / EliminationSheet / TrialBalance）

### 2.2 单位换算时机不明确（N-2）
- **痛点**：DB 存"元"→API 返回"元"→前端 displayPrefs 在"显示层"换算，但部分组件在计算层就做了换算，导致导出时还原困难
- **影响角色**：所有用户（数据一致性）
- **技术根因**：无强制规范约束"换算仅在显示层"，部分组件在 computed 中提前除以 10000 后再参与计算
- **Sprint 0 实测**：grep `/ 10000\|/ 1000\|\\* 10000` 在 `.vue`/`.ts` 中出现位置 — 实测 0 处金额单位换算违规（全部 `/ 1000` 均为时间 ms→s 或百分比计算，`fmtAmountUnit` 内部的 `n / cfg.divisor` 是正确的显示层实现）；当前架构已正确遵循"仅显示层换算"规范

### 2.3 el-table sortable 列排序基于格式化字符串（N-3）
- **痛点**：el-table 的 sortable 列对格式化后的字符串排序（如 "1,234.56" < "234.56" 按字典序），导致金额排序错误
- **影响角色**：所有用户（数据浏览体验）
- **技术根因**：el-table 默认 sortable="custom" 或无 sort-method 时按 formatter 输出的字符串排序；当前仅 ReportView.vue 2 列有 `sort-method`（grep 确认），其余金额 sortable 列均无
- **Sprint 0 实测**：grep 全仓库 `sortable` 在 el-table-column 中的使用数量，确认需要补 sort-method 的列数 = 8（LedgerPenetration 4+4）+ WorkpaperTableEditor 动态列

### 2.4 项目级权限端点缺失（R-4）
- **痛点**：前端 usePermission 仅基于系统级角色硬编码权限，无法获取用户在特定项目中的角色和权限；EQCR 双层判断（系统+项目）前端实现复杂
- **影响角色**：所有用户（权限准确性）、EQCR 独立复核合伙人
- **技术根因**：无 `/api/projects/{id}/my-permissions` 和 `/api/projects/{id}/my-role` 端点；前端路由守卫硬编码 `meta.roles` 数组而非调用 `can(permission)`
- **Sprint 0 实测**：ProjectAssignment 表已有 `role` 字段（String(30)），可直接查询；当前 router/index.ts 中 `meta: { roles: [...] }` 共 15 处（R-1 修复后：ArchiveWizard×2 / QCDashboard / PartnerSignDecision / LinkagePanorama / SystemSettings / EqcrMetrics / QcRuleList / QcRuleEditor / QcInspectionWorkbench / ClientQualityTrend / QcCaseLibrary / QcAnnualReports / TemplateLibraryMgmt / CustomQuery）

### 2.5 待回复批注无聚合面板（A-4）
- **痛点**：助理回复复核意见时需逐个底稿逐个 cell 找"我被@的"批注，效率极低
- **影响角色**：审计助理（日常高频操作者）
- **技术根因**：ReviewRecord 有 `commenter_id`（发起人）但无 `mentioned_user_id`（被@人）；当前无按"被@用户"聚合的查询端点；底稿 `assigned_to` 字段可作为"被@"的近似（底稿负责人 = 应回复人）
- **Sprint 0 实测**：review_records 表有 `working_paper_id` + `status`（open/replied/resolved）+ `commenter_id`；working_paper 表有 `assigned_to`（FK users.id）；可通过 JOIN 实现"我负责的底稿上的未解决批注"聚合

### 2.6 高危操作无二次密码验证（SC-2）
- **痛点**：签字/归档/删除项目等高危操作仅依赖 JWT 认证，被盗 token 在 30min 有效期内可执行任意高危操作
- **影响角色**：合伙人（签字决策）、项目经理（项目管理）
- **技术根因**：无 `POST /api/auth/verify-password` 端点；高危操作路由无二次验证中间件；`security.py` 已有 `verify_password(plain, hashed)` 函数可直接复用
- **Sprint 0 实测**：高危操作清单 = sign（签字）/ archive（归档）/ delete_project（删除项目）/ batch_delete（批量删除）；后端已有 `security.verify_password` + `User.hashed_password` 字段

### 2.7 项目经理无多项目进度总览（M-1）
- **痛点**：PartnerProjectDashboard 有 CycleProgressRing 但项目经理无独立的"我管的项目群"视图，需逐个项目查看进度
- **影响角色**：项目经理（进度管控）
- **技术根因**：无 ManagerDashboard 视图；Project 表有 `manager_id` 字段可聚合；无按循环维度聚合进度的 API
- **Sprint 0 实测**：projects 表有 `manager_id`（FK users.id）+ `status`（ProjectStatus 枚举）；working_paper 表有 `project_id` + `review_status`（WpReviewStatus）可计算完成度

### 2.8 复核层级固定不灵活（RV-1）
- **痛点**：当前固定为"助理→经理→合伙人"三级复核（WpReviewStatus 仅 level1/level2），无法适配"助理→高级→经理→合伙人"四级或"助理→经理"两级场景
- **影响角色**：项目经理（流程配置）、所有复核参与者
- **技术根因**：WpReviewStatus 枚举硬编码 `pending_level1/level1_passed/pending_level2/level2_passed`；无项目级复核链配置；状态机流转逻辑写死 2 级
- **Sprint 0 实测**：WpReviewStatus 枚举 9 个值（not_submitted + level1×4 + level2×4）；ReviewRecord.review_layer 字段已支持 L1~L5 + committee/it/tax 标记；Project 模型无 review_config 字段（需新增 JSONB 列）

---

## 三、范围边界

### A. 必做（In Scope）

| 编号 | 功能项 | 来源 |
|------|--------|------|
| F1 | 前端金额计算 Decimal.js 改造 | N-1 |
| F2 | 单位换算时机规范化 | N-2 |
| F3 | el-table sortable 列 sort-method 基于原始数值 | N-3 |
| F4 | 项目级权限端点 + useProjectRole composable + 路由守卫改造 | R-4 |
| F5 | 待回复批注聚合面板（MyReviewsPanel） | A-4 |
| F6 | 高危操作二次密码验证 | SC-2 |
| F7 | 项目经理多项目进度总览（ManagerDashboard） | M-1 |
| F8 | 复核层级灵活化（2-4 级可配置） | RV-1 |

### B. 排除（Out of Scope）

- 不涉及后端金额精度改造（Python Decimal 已原生支持，DB Numeric(20,2) 已正确）
- 不涉及 TOTP/MFA 二次认证（仅实现密码二次验证，TOTP 待后续 Phase）
- 不涉及 ManagerDashboard 甘特图/燃尽图（仅实现环形图/进度条 + SLA 排序）
- 不涉及复核链超过 4 级的场景（2-4 级覆盖 99% 业务需求）
- 不涉及 ReviewRecord 新增 `mentioned_user_id` 字段（通过 working_paper.assigned_to JOIN 实现"我的待回复"）
- 不涉及前端 Number 类型的非金额运算改造（仅改造金额相关计算）
- 不涉及 el-table 非金额列的排序改造（仅改造金额/数值列）

### C. Sprint 0 偏差修正

| 起草假设 | 实测结果 | 偏差影响 | 修正方案 |
|----------|----------|----------|----------|
| ReviewRecord 有 mentioned_user_id | 无此字段，仅有 commenter_id | F5 "被@"逻辑需改为 JOIN working_paper.assigned_to | 查询"我负责底稿上的 open 批注" |
| WpReviewStatus 支持 3 级 | 仅 2 级（level1/level2） | F8 需扩展枚举或改为动态状态 | 改为 JSONB 配置驱动 + 通用 pending_levelN/levelN_passed 模式 |
| 前端已有 Decimal.js | 未安装 | F1 需先 npm install decimal.js | 作为 Sprint 1 第一个 task |
| meta.roles 大量使用 | R-1 修复后 15 处（含 ArchiveWizard/QC/SystemSettings/EqcrMetrics/LinkagePanorama/TemplateLibraryMgmt/CustomQuery 等） | F4 路由守卫改造工作量大于预期（15 处需迁移为 can(permission)） | 分批改造：先新增 permission guard 基础设施，再逐路由迁移 |
| Project 有 review_config | 无此字段 | F8 需 DB 迁移新增 JSONB 列 | V008__add_review_config.sql（V007 已被 SC-1 audit_log append-only 占用） |
| sort-method 已有部分使用 | 2 处（ReportView.vue 本期/上期金额） | F3 需补 LedgerPenetration 8 列 + WorkpaperTableEditor 动态列 | grep sortable 列逐一补 sort-method（ReportView 已完成） |

---

## 四、功能需求（EARS 范式）

### F1 前端金额计算 Decimal.js 改造

**User Story:** 作为审计人员，我希望前端金额计算使用高精度库，以便消除浮点精度丢失导致的分差问题。

#### 验收标准

1. THE 前端项目 SHALL 安装 `decimal.js` 作为生产依赖
2. THE 系统 SHALL 提供 `useDecimalCalc` composable，封装 Decimal.js 的加减乘除四则运算
3. WHEN 前端组件需要对金额进行四则运算（加/减/乘/除），THE 组件 SHALL 使用 `useDecimalCalc` 而非 Number 直接运算
4. THE `useDecimalCalc` SHALL 默认保留 2 位小数（可配置），使用银行家舍入（ROUND_HALF_EVEN）
5. THE 系统 SHALL 新增 ESLint 规则 `no-amount-arithmetic`（**warning 级别**，高误报风险注记：变量名模式匹配 `*amount*`/`*balance*`/`*total*`/`*sum*` 会命中非金额的 count/progress/stats 类 total 变量，初期用 warn 收集误报后再升级 error）：警告在金额变量上直接使用 `+`/`-`/`*`/`/` 运算符
6. IF 存在合理的非金额 Number 运算（如百分比/计数），THE ESLint 规则 SHALL 支持 `// eslint-disable-next-line` 豁免

### F2 单位换算时机规范化

**User Story:** 作为开发人员，我希望单位换算有明确的时机规范，以便保证"DB 存元→API 返回元→显示层换算→导出还原元"的数据流一致性。

#### 验收标准

1. THE 系统 SHALL 遵循数据流规范：DB 存储"元" → API 返回"元" → 前端仅在"显示层"（template/formatter）换算 → 导出时使用原始"元"值
2. WHEN 前端组件在 computed/method 中对金额做除法换算（`/ 10000` 或 `/ 1000`），THE 代码审查 SHALL 标记为违规（应改为 template 中调用 `fmtAmountUnit`）
3. THE 系统 SHALL 新增 ESLint 规则 `no-amount-unit-in-script`：禁止在 `<script>` 块中对金额变量做 `/ 10000` 或 `/ 1000` 换算
4. THE 现有违规代码 SHALL 迁移为在 `<template>` 中使用 `fmtAmountUnit(value, displayPrefs.unit)` 格式化
5. WHEN 导出 Excel 时，THE 导出逻辑 SHALL 使用原始"元"值（不经过 displayPrefs 换算）
6. THE `fmtAmountUnit` 函数 SHALL 保持为纯显示函数，不修改原始数据

### F3 el-table sortable 列 sort-method 基于原始数值

**User Story:** 作为用户，我希望表格金额列排序基于真实数值而非格式化字符串，以便正确排序金额大小。

#### 验收标准

1. WHEN el-table-column 设置 `sortable` 且该列为金额/数值类型，THE 列 SHALL 提供 `sort-method` 基于原始数值比较
2. THE 系统 SHALL 提供 `numericSortMethod(prop: string)` 工具函数，返回基于 `row[prop]` 原始数值的比较函数
3. THE `numericSortMethod` SHALL 正确处理 null/undefined/NaN 值（统一排到末尾）
4. THE 系统 SHALL 在所有含金额列的 el-table 页面接入 `numericSortMethod`（至少覆盖：TrialBalance / AdjustmentList / WorkpaperList 金额列）
5. WHEN 用户点击金额列排序，THE 排序结果 SHALL 与数值大小一致（如 1234.56 > 234.56，而非字符串 "1,234.56" < "234.56"）
6. THE sort-method 改造 SHALL 不影响非金额列的默认排序行为

### F4 项目级权限端点 + useProjectRole + 路由守卫改造

**User Story:** 作为前端开发者，我希望有项目级权限 API 和 composable，以便路由守卫和按钮权限基于用户在具体项目中的角色判断，而非硬编码系统角色数组。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/projects/{id}/my-permissions` 端点，返回当前用户在该项目的权限列表（基于 ProjectAssignment.role 映射）
2. THE 后端 SHALL 新增 `GET /api/projects/{id}/my-role` 端点，返回当前用户在该项目的角色（ProjectAssignment.role）及系统角色
3. WHEN 用户未被分配到该项目，THE `my-role` 端点 SHALL 返回 `{ project_role: null, system_role: "..." }`（admin 角色仍有全部权限）
4. THE 前端 SHALL 新增 `useProjectRole(projectId)` composable，从端点获取项目级角色并缓存（5min TTL，项目切换时刷新）
5. THE 路由守卫 SHALL 改为调用 `can(route.meta.permission)` 而非硬编码 `meta.roles` 数组
6. THE `useProjectRole` SHALL 暴露 `projectCan(permission)` 方法，结合系统角色+项目角色判断权限
7. IF 用户为 admin 角色，THE 系统 SHALL 跳过项目级权限检查（admin 拥有所有权限）

### F5 待回复批注聚合面板（MyReviewsPanel）

**User Story:** 作为审计助理，我希望有一个"我的待回复批注"聚合面板，按底稿/优先级/创建时间排序，以便快速定位需要回复的复核意见。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/projects/{project_id}/my-reviews?status=open` 端点
2. THE 端点 SHALL 返回当前用户负责底稿（working_paper.assigned_to = current_user.id）上所有 status=open 的 ReviewRecord 列表
3. THE 返回列表 SHALL 按优先级降序（must_fix > suggest > info）+ 创建时间升序排列
4. THE 每条记录 SHALL 包含：review_id、底稿编号（wp_code）、底稿名称、cell_reference、comment_text、commenter 姓名、priority、created_at
5. THE 前端 SHALL 新增 `MyReviewsPanel` 组件，展示待回复批注列表
6. WHEN 用户点击某条批注，THE 系统 SHALL 跳转到对应底稿的对应 cell 位置
7. THE MyReviewsPanel SHALL 集成到 PartnerProjectDashboard 或作为独立视图（路由 `/projects/:id/my-reviews`）
8. THE 面板 SHALL 显示统计摘要：必须修改 N 条 / 建议修改 N 条 / 仅供参考 N 条

### F6 高危操作二次密码验证

**User Story:** 作为合伙人，我希望签字/归档/删除项目等高危操作需要二次输入密码确认，以便防止 token 被盗后的未授权操作。

#### 验收标准

1. THE 后端 SHALL 新增 `POST /api/auth/verify-password` 端点，接收 `{ password: string }` 并验证当前用户密码
2. WHEN 密码验证成功，THE 端点 SHALL 返回一次性 `confirmation_token`（有效期 5 分钟，Redis 存储）
3. WHEN 密码验证失败，THE 端点 SHALL 返回 401 并记录失败次数（5 次锁定 30 分钟，复用 LOGIN_MAX_ATTEMPTS/LOGIN_LOCK_MINUTES 配置）
4. THE 高危操作端点 SHALL 要求请求头携带 `X-Confirmation-Token`，后端验证 token 有效性后才执行操作
5. THE 高危操作列表 SHALL 包含：sign（签字）/ archive（归档）/ delete_project（删除项目）/ batch_delete（批量删除）
6. THE 前端 SHALL 新增 `PasswordConfirmDialog` 组件，在高危操作前弹出密码输入框
7. WHEN 用户输入正确密码，THE 前端 SHALL 获取 confirmation_token 并自动附加到后续高危请求头
8. IF confirmation_token 过期或已使用，THE 后端 SHALL 返回 403 要求重新验证

### F7 项目经理多项目进度总览（ManagerDashboard）

**User Story:** 作为项目经理，我希望有一个"我管的项目群"进度总览视图，按 SLA 紧急度排序，以便快速判断哪个项目最需要关注。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/manager/dashboard` 端点，返回当前用户作为 manager 的所有项目进度摘要
2. THE 每个项目摘要 SHALL 包含：project_id、project_name、client_name、overall_progress（%）、cycle_progress[]（按循环维度）、sla_urgency_score、blocking_vr_count、unresolved_review_count
3. THE 项目列表 SHALL 按 sla_urgency_score 降序排列（最紧急的排最前）
4. THE sla_urgency_score SHALL 基于：SLA 剩余时间权重 40% + blocking VR 数权重 30% + 未完成底稿比例权重 30%
5. THE 前端 SHALL 新增 `ManagerDashboard.vue` 视图，包含：项目列表（卡片/表格切换）+ 循环维度环形图/进度条
6. WHEN 项目经理登录系统，THE 系统 SHALL 在导航栏提供"我的项目群"入口（仅 manager/admin 可见）
7. THE 循环维度进度 SHALL 显示每个循环的完成底稿数/总底稿数 + 百分比
8. WHEN 用户点击某个项目卡片，THE 系统 SHALL 跳转到该项目的 PartnerProjectDashboard

### F8 复核层级灵活化（2-4 级可配置）

**User Story:** 作为项目经理，我希望可以为项目配置 2-4 级复核链，以便适配不同规模项目的复核需求。

#### 验收标准

1. THE 后端 SHALL 新增 `projects.review_config` JSONB 列，存储复核链配置
2. THE review_config 结构 SHALL 为：`{ "levels": 2|3|4, "level_roles": { "L1": "manager", "L2": "partner", "L3": "qc", "L4": "committee" } }`
3. WHEN review_config 为 null，THE 系统 SHALL 使用默认 2 级配置（L1=manager, L2=partner）
4. THE 后端 SHALL 新增 `PUT /api/projects/{id}/review-config` 端点，仅 manager/partner/admin 可修改
5. THE 状态机 SHALL 根据配置的层级数动态生成状态流转：`not_submitted → pending_level1 → level1_passed → pending_level2 → ... → levelN_passed`
6. WHEN 底稿提交复核，THE 系统 SHALL 根据 review_config.levels 确定需要经过的复核层级数
7. WHEN 某层级复核通过且为最终层级，THE 系统 SHALL 将底稿标记为"复核完成"（等价于当前 level2_passed）
8. THE WpReviewStatus 枚举 SHALL 扩展支持 level3/level4 状态（pending_level3/level3_passed/level3_rejected/pending_level4/level4_passed/level4_rejected）
9. THE 前端 SHALL 在项目设置页面提供复核链配置 UI（下拉选择层级数 + 各层级角色分配）
10. IF 项目已有进行中的复核（status 非 not_submitted），THE 系统 SHALL 禁止修改 review_config（需先完成或退回所有进行中复核）

---

## 五、非功能需求

| 维度 | 要求 | 适用功能 |
|------|------|----------|
| 性能 | F1 Decimal.js 运算性能 ≤ 原生 Number 的 5 倍耗时（单次运算 < 1ms） | F1 |
| 性能 | F4 my-permissions 端点响应 ≤ 200ms | F4 |
| 性能 | F5 my-reviews 端点响应 ≤ 500ms（单项目 200 条 ReviewRecord 规模） | F5 |
| 性能 | F7 manager/dashboard 端点响应 ≤ 1s（10 个项目规模） | F7 |
| 安全 | F6 confirmation_token 一次性使用 + 5min TTL + Redis 存储 | F6 |
| 安全 | F6 密码验证失败 5 次锁定 30 分钟（复用 LOGIN_MAX_ATTEMPTS） | F6 |
| 安全 | F4 admin 角色跳过项目级权限检查 | F4 |
| 兼容性 | F1 Decimal.js 改造后所有金额显示视觉零差异 | F1 |
| 兼容性 | F3 sort-method 改造后非金额列排序行为不变 | F3 |
| 兼容性 | F8 review_config=null 时行为与当前完全一致（默认 2 级） | F8 |
| 兼容性 | F8 WpReviewStatus 扩展后现有 level1/level2 逻辑零回归 | F8 |
| 可观测性 | F6 密码验证成功/失败均写入 audit_log | F6 |
| 可观测性 | F6 高危操作执行记录写入 audit_log（含 confirmation_token_id） | F6 |
| 事务性 | F8 review_config 修改前检查无进行中复核（乐观锁） | F8 |
| 幂等性 | F4 useProjectRole 缓存 5min TTL，项目切换时主动刷新 | F4 |
| 可测试性 | F1 Decimal.js 四则运算提供 round-trip property（a + b - b ≈ a） | F1 |
| 可测试性 | F8 状态机流转提供 property：N 级配置下 submit→pass×N→completed | F8 |

---

## 六、测试矩阵

| 功能 | 单元测试 | PBT | 集成测试 | 前端 vitest | UAT |
|------|----------|-----|----------|-------------|-----|
| F1 Decimal.js | useDecimalCalc 四则运算 | round-trip + 精度保持 | — | 金额计算组件 | 金额显示无分差 |
| F2 单位换算 | — | — | — | 导出还原验证 | 导出 Excel 金额正确 |
| F3 sort-method | numericSortMethod 逻辑 | null/NaN 边界 | — | 排序行为验证 | 金额列排序正确 |
| F4 权限端点 | 权限映射逻辑 | — | API 端点 + RBAC | useProjectRole | 项目级权限生效 |
| F5 批注聚合 | 排序逻辑 + JOIN 查询 | — | API 端点 | MyReviewsPanel | 助理看到待回复 |
| F6 二次验证 | token 生成/验证/过期 | 锁定边界 | API 端点 + 高危操作 | PasswordConfirmDialog | 签字需二次验证 |
| F7 经理仪表盘 | urgency_score 计算 | 排序稳定性 | API 端点 | ManagerDashboard | 经理看到项目群 |
| F8 复核灵活化 | 状态机流转 | N 级 submit→pass 链 | API 端点 + 配置 | 配置 UI | 4 级复核正常流转 |

### 测试文件清单（预期）

| 文件 | 覆盖功能 |
|------|----------|
| `frontend/src/__tests__/useDecimalCalc.spec.ts` | F1 |
| `frontend/src/__tests__/numericSortMethod.spec.ts` | F3 |
| `frontend/src/__tests__/useProjectRole.spec.ts` | F4 |
| `frontend/src/__tests__/MyReviewsPanel.spec.ts` | F5 |
| `frontend/src/__tests__/PasswordConfirmDialog.spec.ts` | F6 |
| `frontend/src/__tests__/ManagerDashboard.spec.ts` | F7 |
| `frontend/src/__tests__/ReviewChainConfig.spec.ts` | F8 |
| `backend/tests/test_project_permissions.py` | F4 |
| `backend/tests/test_my_reviews_aggregation.py` | F5 |
| `backend/tests/test_password_verification.py` | F6 |
| `backend/tests/test_manager_dashboard.py` | F7 |
| `backend/tests/test_review_chain_config.py` | F8 |
| `backend/tests/test_phase6_pbt.py` | F1/F3/F7/F8 PBT |

### PBT 正确性属性（预期）

| 编号 | 属性 | 适用功能 | 类型 |
|------|------|----------|------|
| P1 | Decimal 加减 round-trip：`Decimal(a).plus(b).minus(b)` 精度损失 ≤ 1e-10 | F1 | Round-trip |
| P2 | Decimal 乘除 round-trip：`Decimal(a).times(b).div(b)` 精度损失 ≤ 1e-10（b≠0） | F1 | Round-trip |
| P3 | numericSortMethod 排序稳定性：相同输入多次排序结果一致 | F3 | Idempotence |
| P4 | numericSortMethod 单调性：a < b → sort(a,b) < 0 | F3 | Metamorphic |
| P5 | urgency_score 单调性：SLA 剩余时间越少 → score 越高 | F7 | Metamorphic |
| P6 | 复核状态机 N 级链完整性：levels=N → submit 后恰好经过 N 次 pass 到达 completed | F8 | Model-based |
| P7 | confirmation_token 一次性：使用后再次使用返回 403 | F6 | Idempotence |

---

## 七、成功判据 + 术语表

### 成功判据

| 指标 | 目标 |
|------|------|
| F1 金额计算精度 | 0.1+0.2=0.3（Decimal.js 保证） |
| F1 ESLint 规则覆盖 | 金额变量直接运算 0 处违规 |
| F2 计算层换算违规 | grep `/ 10000\|/ 1000` 在 script 块中 0 处（金额相关） |
| F3 sort-method 覆盖 | 所有金额 sortable 列均有 sort-method |
| F4 端点响应 | my-permissions ≤ 200ms |
| F4 路由守卫改造 | meta.roles 硬编码 → can(permission) |
| F5 聚合查询响应 | my-reviews ≤ 500ms |
| F6 token 安全性 | 一次性 + 5min TTL + 锁定机制 |
| F7 仪表盘响应 | manager/dashboard ≤ 1s |
| F7 项目排序 | 按 urgency_score 降序 |
| F8 层级支持 | 2/3/4 级均可正常流转 |
| F8 向后兼容 | review_config=null 等价当前 2 级 |
| 现有测试回归 | 零新增失败 |
| vue-tsc 编译 | 零新增错误 |

### UAT 验收清单

| # | 验收项 | P | 角色 | 验证方式 |
|---|--------|---|------|----------|
| 1 | 金额计算无浮点分差（0.1+0.2=0.3） | P0 | 开发 | useDecimalCalc 单测 |
| 2 | el-table 金额列排序正确 | P0 | 助理 | 点击排序验证 |
| 3 | my-permissions 端点返回正确权限列表 | P0 | 开发 | API 测试 |
| 4 | useProjectRole 缓存生效 | P1 | 开发 | 网络请求监控 |
| 5 | 路由守卫 can(permission) 生效 | P0 | 开发 | 权限不足时 403 |
| 6 | MyReviewsPanel 显示待回复批注 | P0 | 助理 | 登录后查看 |
| 7 | 签字操作弹出密码确认 | P0 | 合伙人 | 签字流程验证 |
| 8 | 密码错误 5 次锁定 | P1 | 开发 | API 测试 |
| 9 | ManagerDashboard 显示项目群 | P0 | 经理 | 登录后查看 |
| 10 | 项目按 SLA 紧急度排序 | P1 | 经理 | 视觉验证 |
| 11 | 复核链 3 级配置正常流转 | P0 | 经理 | 配置+提交+通过 |
| 12 | 复核链 4 级配置正常流转 | P1 | 经理 | 配置+提交+通过 |
| 13 | review_config=null 默认 2 级 | P0 | 开发 | 回归测试 |
| 14 | 导出 Excel 金额为原始"元"值 | P1 | 助理 | 导出验证 |

上线门槛：P0 全 ✓ + UAT 真实验收通过 + 关键回归零失败

---

### 术语表

| 术语 | 定义 |
|------|------|
| **Decimal.js** | JavaScript 高精度十进制运算库，避免 IEEE 754 浮点精度丢失 |
| **银行家舍入** | ROUND_HALF_EVEN，四舍六入五成双，金融领域标准舍入规则 |
| **displayPrefs** | 前端显示偏好 store（金额单位/字号/小数位数），仅控制显示层 |
| **fmtAmountUnit** | 金额格式化统一函数（formatters.ts），支持元/万元/千元换算 |
| **ProjectAssignment** | 项目团队委派模型（project_assignments 表），含 project_id + staff_id + role |
| **useProjectRole** | 本 spec 新增的项目级角色 composable，从 API 获取并缓存 |
| **confirmation_token** | 二次密码验证成功后颁发的一次性令牌，高危操作必须携带 |
| **高危操作** | sign（签字）/ archive（归档）/ delete_project（删除项目）/ batch_delete（批量删除） |
| **WpReviewStatus** | 底稿复核状态枚举，本 spec 扩展支持 level3/level4 |
| **review_config** | 项目级复核链配置（JSONB），定义层级数和各层级角色 |
| **复核链** | 底稿从提交到最终通过需经过的复核层级序列（2-4 级） |
| **urgency_score** | 项目紧急度评分，基于 SLA 剩余时间 + blocking VR 数 + 未完成底稿比例加权计算 |
| **ManagerDashboard** | 本 spec 新增的项目经理多项目进度总览视图 |
| **MyReviewsPanel** | 本 spec 新增的待回复批注聚合面板组件 |
| **PasswordConfirmDialog** | 本 spec 新增的二次密码验证弹窗组件 |
| **sort-method** | el-table-column 的自定义排序函数 prop，基于原始数值比较 |
| **numericSortMethod** | 本 spec 新增的数值排序工具函数 |
| **review_layer** | ReviewRecord 字段，标记批注所属复核层级（L1~L5/committee/it/tax） |
| **SLA** | Service Level Agreement，问题单完成时限（IssueTicket.due_at） |
| **RBAC** | Role-Based Access Control，基于角色的访问控制 |

---

## 八、附录 — Sprint 0 基线

### A. 基线变量

| 基线变量 | 实测值 | 来源 |
|----------|--------|------|
| N_decimal_js_installed | 0 | package.json 无 decimal.js 依赖 |
| N_sort_method_usage | 2 | ReportView.vue 本期金额 + 上期金额 2 列已有 sort-method |
| N_sortable_amount_columns | 10（LedgerPenetration 8 列 + ReportView 2 列；其中 ReportView 2 列已有 sort-method，需补 8 列） | grep `sortable` 在含金额列的 el-table-column 中；另 WorkpaperTableEditor 动态列全 sortable 需单独处理 |
| N_amount_arithmetic_violations | 30（分布：LedgerPenetration 8 / Adjustments 3 / ConsolidationIndex 1 / DCountDialog 1 / CapitalReserveSheet 1 / TAccountEditor 3 / InternalCashFlowSheet 1 / ConfirmationSummary 2 / InternalTradeSheet 2 / AuditFindingPanel 1 / EliminationSheet 4 / TrialBalance 3） | grep 金额变量直接 +/-/*/÷ 运算（排除 formatters.ts 内部） |
| N_unit_conversion_in_script | 0（全仓库无金额相关 `/ 10000` 或 `* 10000` 在 script 块中；现有 `/ 1000` 均为时间 ms→s 换算或百分比计算，非金额单位换算） | grep `/ 10000\|/ 1000\|* 10000` 在 script 块中，逐一排查确认 |
| ProjectAssignment.role_values | manager / signing_partner / auditor / eqcr / qc / readonly（6 种，来源：test fixtures + SOD 规则） | 代码锚定：test_cost_overview + test_eqcr_* + test_independence_service |
| ReviewRecord.status_open_count | 枚举 3 值：open / replied / resolved（ReviewCommentStatus enum）；无法查 DB 实际 open 数量，模型定义 server_default='open' | backend/app/models/workpaper_models.py ReviewCommentStatus 枚举 |
| ReviewRecord.priority | ✅ 存在（Phase 2 F5 添加），server_default='suggest'，值域 must_fix/suggest/info | backend/app/models/workpaper_models.py 第 454 行 |
| WpReviewStatus_enum_count | 9 | not_submitted + level1×4 + level2×4 |
| ReviewRecord.review_layer_values | L1~L5/committee/it/tax | 字段 comment 定义 |
| Project.review_config | 不存在 | 需 V008 迁移新增（V007 已被 SC-1 audit_log 占用） |
| security.verify_password | ✅ 存在 | backend/app/core/security.py |
| User.hashed_password | ✅ 存在 | backend/app/models/core.py |
| Project.manager_id | ✅ 存在 | FK users.id |
| WorkingPaper.assigned_to | ✅ 存在 | FK users.id |
| meta_roles_usage_count | 15 | router/index.ts R-1 修复后 15 处路由定义 meta.roles |
| LOGIN_MAX_ATTEMPTS | 5 | config.py |
| LOGIN_LOCK_MINUTES | 30 | config.py |
| BCRYPT_ROUNDS | 12 | config.py |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | 30 | config.py |

### B. 实施前必须补充的 Sprint 0 实测项

| 实测项 | 目的 | 方法 |
|--------|------|------|
| grep 金额变量运算 | 确定 F1 改造范围 | `grep -rn "amount\|balance\|total" --include="*.vue" --include="*.ts" \| grep "[+\-*/]"` |
| grep sortable 金额列 | 确定 F3 改造范围 | `grep -rn "sortable" --include="*.vue" \| grep -i "amount\|balance\|金额"` |
| grep 单位换算 | 确定 F2 违规数 | `grep -rn "/ 10000\|/ 1000\|\* 10000" --include="*.vue" --include="*.ts"` |
| SELECT DISTINCT role FROM project_assignments | 确定 F4 角色映射 | SQL 查询 |
| SELECT COUNT(*) FROM review_records WHERE status='open' | 确定 F5 数据规模 | SQL 查询 |
| SELECT COUNT(*) FROM projects WHERE manager_id IS NOT NULL | 确定 F7 数据规模 | SQL 查询 |

---

### C. 回归影响白名单

F8 WpReviewStatus 枚举扩展影响范围（需回归验证）：
- `backend/app/routers/batch_review.py` — `REVIEWABLE_REVIEW_STATUSES` 常量（当前仅含 level1/level2 状态，扩展后需包含 level3/level4）
- `backend/app/routers/wp_review.py` — 复核状态流转逻辑（submit/pass/reject 路由）
- `audit-platform/frontend/src/views/ReviewWorkbench.vue` — 复核状态筛选/显示逻辑

### D. 功能依赖注记

- **F8 depends on F4**：复核层级灵活化的"各层级角色分配"配置 UI 需要项目级权限端点（F4 `my-permissions`）来判断当前用户是否有权修改 review_config；实施顺序必须 F4 先于 F8

### E. Sprint 0 偏差修正（v1.1 更新）

| 起草假设 | 实测结果 | 偏差影响 | 修正方案 |
|----------|----------|----------|----------|
| N_sort_method_usage = 0 | 实测 = 2（ReportView.vue 已有） | F3 改造范围缩小（ReportView 不需改） | 仅需补 LedgerPenetration 8 列 + WorkpaperTableEditor 动态列 |
| meta.roles 仅 1 处 | 实测 = 15 处（R-1 修复后） | F4 路由守卫改造工作量显著增加 | 分批迁移，优先改造项目级路由 |
| N_unit_conversion_in_script 预计 3~5 处 | 实测 = 0（全部为时间/百分比换算） | F2 无现有违规代码需迁移 | F2 重点改为"ESLint 规则防新增 + 规范文档" |
| V007 可用于 review_config | V007 已被 SC-1 audit_log append-only 占用 | F8 迁移编号冲突 | 改为 V008__add_review_config.sql |

---

*本文档基于《平台全局建议书》N-1~N-3 / R-4 / A-4 / SC-2 / M-1 / RV-1 六项需求编制。*
