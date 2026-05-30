# Bugfix Requirements Document

## Introduction

本文档针对审计作业平台深度代码审查报告（问题1）中发现的 12 个经代码验证的问题，按 P0/P1/P2 三级优先级组织修复需求。这些问题涵盖空壳页面暴露、LLM stub 残留、底稿复核合规缺失、弹窗截断、附注编辑器功能不完整、同步路由阻塞、权限过滤缺失、看板硬编码、API 调用不统一、E2E 测试缺失、导入错误定位不足、前端 http 直接调用等系统级缺陷。

修复总工期约 20 个工作日，建议先集中 1 周完成 P0（约 4 天），再用 1 周完成 P1（约 7 天），最后 P2（约 9 天）。

---

## Bug Analysis

### Current Behavior (Defect)

**P0 — 紧急（约 4 天）**

<!-- 问题一：空壳页面从导航移除 -->
1.1 WHEN 用户点击导航进入 AIChatView / AIWorkpaperView 页面 THEN 系统展示空壳页面（12 行包装壳），AIChatPanel 调用的 3 个后端端点（POST /api/ai/chat、POST /api/ai/chat/file-analysis、GET /api/projects/{id}/chat/history）在 router_registry.py 中未注册，所有操作返回 404 错误

1.2 WHEN 用户点击导航进入 MobileProjectList / MobileReportView / MobileWorkpaperEditor / ConsolSnapshots / CheckInsPage / AuxSummaryPanel 等 6 个空壳页面 THEN 系统展示不足 50 行的空壳内容，无实际功能，CheckInsPage 的打卡功能与审计业务无关造成用户困惑

<!-- 问题三：LLM stub 入口隐藏 -->
1.3 WHEN 用户在 AIPluginManagement 页面启用任意 AI 插件并执行 THEN ai_plugin_service.py 中 8 个 Executor（InvoiceVerify / BusinessInfo / BankReconcile / SealCheck / VoiceNote / WpReview / ContinuousAudit / TeamChat）全部返回 `{"status": "stub", "message": "...尚未实现..."}`

1.4 WHEN 用户在 DisclosureEditor 点击"执行校验"按钮 THEN note_validation_engine.py 的 8 种校验中 6 种（validate_wide_table / validate_vertical / validate_cross_table / validate_aging_transition / validate_completeness / validate_llm_review）直接 return []，只有余额核对和子项校验能产出结果

1.5 WHEN WorkpaperWorkbench.vue 的 AI 变动分析调用 /api/wp-ai/{projectId}/analytical-review 且 LLM 不可用 THEN catch 块静默降级（`catch { /* LLM 不可用时静默降级 */ }`），用户看到空白的 AI 分析区域，无任何提示

<!-- 问题六：底稿复核退回原因+逐条回复强制校验 -->
1.6 WHEN 审计员提交底稿复核（submit-review）且存在 status=open 的复核意见未被 replied THEN 系统仅检查 "status != resolved 的数量 > 0" 但不检查是否所有 open 状态意见已被 replied，允许跳过未回复意见直接提交

1.7 WHEN 复核人退回底稿（level1_in_progress → level1_rejected）THEN working_paper_service.py 的 update_review_status 直接流转状态，无 reason 参数要求，WorkingPaper 模型缺少 rejection_reason 字段，退回原因丢失

1.8 WHEN 底稿被退回后 wp.status 变为 revision_required THEN 退回人（rejected_by）、退回时间（rejected_at）、退回原因（rejection_reason）三项信息均未记录，审计底稿复核痕迹不完整

<!-- 问题十：el-dialog 批量加 append-to-body -->
1.9 WHEN 用户在三栏布局（ThreeColumnLayout.vue 的 .gt-body 容器 overflow:hidden）中打开 el-dialog 弹窗 THEN 30+ 个缺少 append-to-body 属性的弹窗被截断（只显示一半或完全不可见），涉及 Adjustments / TrialBalance / WorkpaperList / WorkpaperWorkbench / ReportView / LedgerPenetration 等核心页面

**P1 — 重要（约 7 天）**

<!-- 问题七：附注编辑器上年数据+公式计算 -->
1.10 WHEN 审计员在 DisclosureEditor.vue 编辑附注表格 THEN disclosure_engine.py 中搜索 prior_year / 上年 / previous / opening / 期初结果为 0 条匹配，完全没有上年数据对比功能

1.11 WHEN 审计员在附注表格中输入数据 THEN disclosure_engine.py 和 DisclosureEditor.vue 中搜索 formula / 公式结果为 0 条匹配，表格只有 el-input-number 手动输入，无"期初 + 本期增加 - 本期减少 = 期末"等公式联动

<!-- 问题二：合并报表模块标记 developing -->
1.12 WHEN 用户访问合并报表模块的任意路由 THEN 后端 10 个合并路由（consolidation / consol_scope / consol_trial / internal_trade / component_auditor / goodwill / forex / minority_interest / consol_notes / consol_report）全部使用 Depends(sync_db) 同步 ORM，阻塞 asyncio 事件循环，一个 2 秒查询期间所有异步请求排队等待

<!-- 问题九：scope_cycles 落地到核心 4 个路由 -->
1.13 WHEN 非 admin/partner 角色用户访问试算表（trial_balance.py）、调整分录（adjustments.py）、查账穿透（ledger_penetration.py）、附注编辑（disclosure_notes.py）THEN 系统返回所有科目/数据，未按 project_users.scope_cycles 过滤，审计员 A 可看到审计员 B 负责循环的全部数据

<!-- 问题十一：dashboard 5 个硬编码 0 指标接入真实数据 -->
1.14 WHEN 用户查看 dashboard 看板 THEN dashboard_service.py 中 overdue_projects / pending_review / qc_pass_rate / review_completion / adjustment_count 五个指标全部硬编码返回 0，看板数据完全不可信

**P2 — 优化（约 9 天）**

<!-- 问题四：前端 API 调用统一为 apiProxy -->
1.15 WHEN 前端页面混用 apiProxy.ts（方式 A，自动解包）、commonApi.ts（方式 B，手动解构）、直接 import http（方式 C，手动解构）三种 API 调用方式 THEN 解包链路不一致，部分端点被 _SKIP_PATHS 跳过包装返回原始数据时，API 函数期望已解包数据导致多包一层，随机出现 undefined

<!-- 问题五：E2E 集成测试 -->
1.16 WHEN 系统在生产环境（PostgreSQL + Redis）运行 THEN 1604 个测试全部基于 SQLite + fakeredis，行锁（FOR UPDATE）、事务隔离（READ COMMITTED vs SERIALIZABLE）、JSON 字段（JSONB vs TEXT）、异步驱动（asyncpg vs aiosqlite）、debounce timing 等行为差异从未被验证

<!-- 问题八：导入错误行号定位 -->
1.17 WHEN smart_import_engine.py 的 convert_balance_rows / convert_ledger_rows 中某行数据格式异常（日期格式错误、金额含中文字符）THEN try/except 静默跳过该行，跳过的行未记录到任何错误报告中，用户只能看到"0 条入库"或"导入失败"，不知道具体哪一行出问题

<!-- 问题十二：29 个文件 http→apiProxy 改造 -->
1.18 WHEN 29 个 Vue 文件仍直接 import http 拼 URL 调用后端 THEN 与 apiProxy.ts 的自动解包行为不一致，_SKIP_PATHS 端点（/wopi/、/api/events/）的响应格式差异成为 bug 温床


### Expected Behavior (Correct)

**P0 — 紧急**

<!-- 问题一：空壳页面从导航移除 -->
2.1 WHEN 用户浏览导航菜单 THEN AIChatView 和 AIWorkpaperView 的路由 SHALL 被完全移除（后端端点不存在，无法降级），导航中不再显示这两个入口

2.2 WHEN 用户浏览导航菜单 THEN MobileProjectList / MobileReportView / MobileWorkpaperEditor / ConsolSnapshots / CheckInsPage / AuxSummaryPanel 等 6 个空壳页面 SHALL 在 ThreeColumnLayout.vue 的 navItems 中设置 maturity: 'developing'（灰色不可点击 + 提示"开发中"），或从路由中移除

<!-- 问题三：LLM stub 入口隐藏 -->
2.3 WHEN 用户访问 AIPluginManagement 页面 THEN 系统 SHALL 移除 8 个预设 stub 插件的展示，或在每个插件卡片上标注"即将上线"并禁用执行按钮

2.4 WHEN 用户在 DisclosureEditor 点击"执行校验"按钮 THEN 系统 SHALL 在按钮旁显示提示"当前仅支持余额核对和子项校验"，明确告知用户可用校验范围

2.5 WHEN WorkpaperWorkbench.vue 的 AI 变动分析 LLM 不可用 THEN 系统 SHALL 将静默降级改为显示"AI 分析服务未启动"提示卡片，替代空白区域

<!-- 问题六：底稿复核退回原因+逐条回复强制校验 -->
2.6 WHEN 审计员提交底稿复核（submit-review）THEN 系统 SHALL 新增第 5 项门禁：所有 status=open 的复核意见必须已被 replied（状态至少为 replied），未逐条回复时阻断提交并返回具体未回复意见列表

2.7 WHEN 复核人退回底稿 THEN update_review_status 在 rejected 状态时 SHALL 强制要求 reason 参数（非空字符串），WorkingPaper 模型 SHALL 新增 rejection_reason（TEXT）/ rejected_by（UUID FK→users.id）/ rejected_at（TIMESTAMP）三个字段

2.8 WHEN 底稿被退回 THEN 系统 SHALL 将退回人、退回时间、退回原因三项信息永久写入 WorkingPaper 记录，并同时写入 logs 表（通过 AuditLogMiddleware 或业务层显式记录），确保复核痕迹完整可追溯

<!-- 问题十：el-dialog 批量加 append-to-body -->
2.9 WHEN 用户在三栏布局中打开任何 el-dialog 弹窗 THEN 所有 el-dialog 组件 SHALL 添加 append-to-body 属性，弹窗渲染到 body 层级不被 overflow:hidden 截断，使用 Python 脚本批量修复（避免 PowerShell 编码损坏）

**P1 — 重要**

<!-- 问题七：附注编辑器上年数据+公式计算 -->
2.10 WHEN 审计员在 DisclosureEditor.vue 编辑附注表格 THEN 系统 SHALL 从 prior_year 试算表或上年附注数据读取上年数据，在表格中增加上年数据列，实现"本期数 vs 上年数"双列对比

2.11 WHEN 审计员在附注表格中编辑数据 THEN 系统 SHALL 支持表格内实时公式计算（如"期初 + 本期增加 - 本期减少 = 期末"），编辑时即时显示差异，不需要保存后点"执行校验"才能发现不平

<!-- 问题二：合并报表模块标记 developing -->
2.12 WHEN 用户浏览导航菜单中的合并报表入口 THEN 整个合并报表模块 SHALL 标记为 developing（导航灰色不可点击 + 提示"开发中"），避免用户触发同步 ORM 路由阻塞事件循环

<!-- 问题九：scope_cycles 落地到核心 4 个路由 -->
2.13 WHEN 非 admin/partner 角色用户访问试算表 / 调整分录 / 查账穿透 / 附注编辑 THEN 系统 SHALL 从 project_users.scope_cycles 获取用户循环范围，按 scope_cycles 过滤返回的科目行 / 调整分录 / 可查询科目 / 可编辑附注章节，确保数据隔离

<!-- 问题十一：dashboard 5 个硬编码 0 指标接入真实数据 -->
2.14 WHEN 用户查看 dashboard 看板 THEN dashboard_service.py 的 overdue_projects SHALL 查询 projects 表中 status=active 且 deadline < now() 的数量，pending_review SHALL 查询 working_paper 表中 review_status=pending_level1 或 pending_level2 的数量，qc_pass_rate SHALL 从 wp_qc_results 计算通过率，review_completion SHALL 从 working_paper 计算复核完成率，adjustment_count SHALL 从 adjustments 表查询当前活跃调整数量

**P2 — 优化**

<!-- 问题四：前端 API 调用统一为 apiProxy -->
2.15 WHEN 前端页面调用后端 API THEN 所有页面 SHALL 统一使用 apiProxy.ts（api.get/api.post 自动解包直接返回业务数据），分批改造：优先核心 8 个页面（查账 / 试算表 / 调整 / 底稿 / 报表 / 附注 / 向导 / 首页），每改一个页面验证数据展示正确后再改下一个

<!-- 问题五：E2E 集成测试 -->
2.16 WHEN 系统需要验证核心联动链路 THEN SHALL 用 Docker Compose 搭建 E2E 测试环境（PostgreSQL + Redis + 后端），至少覆盖 3 条主链路：①创建项目→导入四表→验证试算表自动生成→验证报表联动 ②创建 AJE→验证试算表增量更新→验证报表更新→验证附注更新 ③上传底稿→验证 WORKPAPER_SAVED 事件→验证审定数比对

<!-- 问题八：导入错误行号定位 -->
2.17 WHEN smart_import_engine.py 的 convert_*_rows 中 try/except 捕获异常 THEN 系统 SHALL 记录行号（Excel 行号）和错误原因到 diagnostics 列表，前端导入结果页 SHALL 展示"跳过 N 行（点击查看详情）"，详情列出行号 + 原因

<!-- 问题十二：29 个文件 http→apiProxy 改造 -->
2.18 WHEN 前端 Vue 文件需要调用后端 API THEN SHALL 按优先级分 3 批将 29 个直接 import http 的文件改造为 apiProxy：第 1 批向导组件 5 个（BasicInfoStep / AccountImportStep / AccountMappingStep / MaterialityStep / ReportLineMappingStep），第 2 批布局组件 4 个（ThreeColumnLayout / MiddleProjectList / DetailProjectPanel / FourColumnCatalog），第 3 批扩展组件 13 个；LedgerPenetration 和 WorkpaperEditor 保留直接 http 调用（游标分页 + 流式响应 / WOPI 锁刷新有正当理由）


### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户访问 LedgerPenetration / WorkpaperWorkbench / WorkpaperList / Adjustments / TrialBalance / DisclosureEditor / ReportView 等 7 个核心深度页面（500+ 行）THEN 系统 SHALL CONTINUE TO 正常展示完整功能，导航移除空壳页面不影响这些核心页面的路由和功能

3.2 WHEN 事件驱动联动链路（ADJUSTMENT_CREATED → TRIAL_BALANCE_UPDATED → REPORTS_UPDATED → 附注增量更新）触发 THEN 系统 SHALL CONTINUE TO 正确执行 5 级事件链 + EventBus debounce 500ms 去重，底稿复核门禁新增第 5 项不影响已有 4 项门禁（复核人已分配 / QC 阻断级通过 / 无未解决批注 / 无未确认 AI 内容）

3.3 WHEN submit-review 端点被调用且所有 5 项门禁（含新增的逐条回复检查）均通过 THEN 系统 SHALL CONTINUE TO 正常流转复核状态（pending_level1 → level1_in_progress → level1_passed → pending_level2 → level2_passed），不影响已有的编制状态机和复核状态机

3.4 WHEN 已有的 el-dialog 弹窗已经包含 append-to-body 属性 THEN 批量修复脚本 SHALL CONTINUE TO 保持这些弹窗不变（幂等操作），不产生重复属性或破坏已有弹窗行为

3.5 WHEN admin 或 partner 角色用户访问试算表 / 调整分录 / 查账穿透 / 附注编辑 THEN 系统 SHALL CONTINUE TO 返回所有数据不做 scope_cycles 过滤（admin/partner 跳过循环权限检查）

3.6 WHEN note_validation_engine.py 的 validate_balance（余额核对）和 validate_sub_item（子项校验）被调用 THEN 系统 SHALL CONTINUE TO 返回正确的校验结果，stub 提示不影响已实现的 2 种校验器

3.7 WHEN 底稿生命周期 7 环节（创建 / 预填充 / 编制 / 保存 / 解析 / 级联 / 离线）正常执行 THEN 系统 SHALL CONTINUE TO 完整运行，复核退回字段新增不影响已有的底稿文件链路和 WOPI 在线编辑

3.8 WHEN http.ts 的 401 刷新队列、请求去重（pendingMap）、500 自动重试、分级错误提示正常工作 THEN API 调用统一化改造 SHALL CONTINUE TO 保持这些基础设施能力不变

3.9 WHEN 已有的 1604 个 SQLite + fakeredis 单元测试运行 THEN 新增 E2E 集成测试 SHALL CONTINUE TO 不影响已有单元测试的执行和通过率

3.10 WHEN LedgerPenetration.vue 的 4 个复杂穿透调用（游标分页 + 流式响应）和 WorkpaperEditor.vue 的 WOPI 锁刷新使用直接 http 调用 THEN http→apiProxy 改造 SHALL CONTINUE TO 保留这 2 个文件的直接 http 调用（有正当理由）

3.11 WHEN dashboard_service.py 的其他非硬编码指标（如项目列表、最近活动等）正常返回 THEN 5 个指标接入真实数据 SHALL CONTINUE TO 不影响看板的其他功能和布局

3.12 WHEN 合并报表模块被标记为 developing 后，后端 10 个合并路由的代码 THEN SHALL CONTINUE TO 保持不变不删除，仅前端导航入口灰色不可点击，后续改为异步 ORM 后可重新开放

---

## Bug Condition Derivation

### C1: 空壳页面暴露（问题一）

```pascal
FUNCTION isBugCondition_ShellPage(X)
  INPUT: X of type NavigationTarget
  OUTPUT: boolean
  
  RETURN X.targetPage IN {AIChatView, AIWorkpaperView, MobileProjectList,
    MobileReportView, MobileWorkpaperEditor, ConsolSnapshots,
    CheckInsPage, AuxSummaryPanel}
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_ShellPage(X) DO
  result ← navigateTo'(X)
  ASSERT (X.targetPage IN {AIChatView, AIWorkpaperView} → route_removed(X))
    AND (X.targetPage NOT IN {AIChatView, AIWorkpaperView} → maturity(X) = 'developing' AND click_blocked(X))
END FOR

// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition_ShellPage(X) DO
  ASSERT navigateTo(X) = navigateTo'(X)
END FOR
```

### C2: LLM Stub 残留可感知（问题三）

```pascal
FUNCTION isBugCondition_StubVisible(X)
  INPUT: X of type UserAction
  OUTPUT: boolean
  
  RETURN (X.action = 'execute_ai_plugin' AND X.plugin IN {8 stub executors})
    OR (X.action = 'run_validation' AND X.validator IN {6 stub validators})
    OR (X.action = 'ai_analysis' AND llm_unavailable())
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_StubVisible(X) DO
  result ← executeAction'(X)
  ASSERT has_user_visible_notice(result)
    AND NOT shows_blank_or_stub_json(result)
END FOR
```

### C3: 复核退回缺失强制校验（问题六）

```pascal
FUNCTION isBugCondition_ReviewGap(X)
  INPUT: X of type ReviewAction
  OUTPUT: boolean
  
  RETURN (X.action = 'submit_review' AND has_unreplied_open_comments(X.wp_id))
    OR (X.action = 'reject_workpaper' AND X.reason IS NULL)
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_ReviewGap(X) DO
  result ← processReview'(X)
  ASSERT (X.action = 'submit_review' → result.blocked = true AND result.blocking_reasons CONTAINS 'unreplied_comments')
    AND (X.action = 'reject_workpaper' → result.error = 'rejection_reason_required')
END FOR
```

### C4: 弹窗截断（问题十）

```pascal
FUNCTION isBugCondition_DialogTruncated(X)
  INPUT: X of type ElDialogInstance
  OUTPUT: boolean
  
  RETURN X.parent_container.overflow = 'hidden'
    AND NOT X.has_attribute('append-to-body')
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_DialogTruncated(X) DO
  dialog ← render'(X)
  ASSERT dialog.has_attribute('append-to-body')
    AND dialog.rendered_in_body = true
END FOR
```

### C5: 附注编辑器功能缺失（问题七）

```pascal
FUNCTION isBugCondition_NoteEditorIncomplete(X)
  INPUT: X of type NoteEditSession
  OUTPUT: boolean
  
  RETURN X.requires_prior_year_comparison = true
    OR X.requires_formula_calculation = true
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_NoteEditorIncomplete(X) DO
  editor ← loadEditor'(X)
  ASSERT (X.requires_prior_year_comparison → editor.has_prior_year_column = true)
    AND (X.requires_formula_calculation → editor.has_realtime_formula = true)
END FOR
```

### C6: 同步路由阻塞（问题二）

```pascal
FUNCTION isBugCondition_SyncBlocking(X)
  INPUT: X of type RouteRequest
  OUTPUT: boolean
  
  RETURN X.target_module = 'consolidation'
    AND X.route_uses_sync_db = true
END FUNCTION

// Property: Fix Checking — 标记 developing 阻止用户触发
FOR ALL X WHERE isBugCondition_SyncBlocking(X) DO
  nav ← getNavItem'(X.target_module)
  ASSERT nav.maturity = 'developing' AND nav.click_blocked = true
END FOR
```

### C7: scope_cycles 未过滤（问题九）

```pascal
FUNCTION isBugCondition_ScopeLeaks(X)
  INPUT: X of type DataRequest
  OUTPUT: boolean
  
  RETURN X.user.role NOT IN {'admin', 'partner'}
    AND X.endpoint IN {trial_balance, adjustments, ledger_penetration, disclosure_notes}
    AND X.user.scope_cycles IS NOT NULL
    AND X.user.scope_cycles != ''
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_ScopeLeaks(X) DO
  result ← queryData'(X)
  ASSERT ALL row IN result: row.cycle IN parse_cycles(X.user.scope_cycles)
END FOR

// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition_ScopeLeaks(X) DO
  ASSERT queryData(X) = queryData'(X)
END FOR
```

### C8: Dashboard 硬编码 0（问题十一）

```pascal
FUNCTION isBugCondition_DashboardZero(X)
  INPUT: X of type DashboardMetric
  OUTPUT: boolean
  
  RETURN X.metric_name IN {'overdue_projects', 'pending_review',
    'qc_pass_rate', 'review_completion', 'adjustment_count'}
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_DashboardZero(X) DO
  value ← getDashboardMetric'(X)
  ASSERT value = real_query_result(X.metric_name)
    AND NOT (value = 0 AND real_count > 0)
END FOR
```

### C9: API 调用方式不统一（问题四）

```pascal
FUNCTION isBugCondition_ApiInconsistent(X)
  INPUT: X of type VueFileApiCall
  OUTPUT: boolean
  
  RETURN X.uses_direct_http = true
    AND X.file NOT IN {LedgerPenetration, WorkpaperEditor}
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_ApiInconsistent(X) DO
  file ← refactored'(X)
  ASSERT file.uses_apiProxy = true
    AND file.data_unwrap_consistent = true
END FOR
```

### C10: E2E 测试缺失（问题五）

```pascal
FUNCTION isBugCondition_NoE2E(X)
  INPUT: X of type TestSuite
  OUTPUT: boolean
  
  RETURN X.database = 'SQLite'
    AND X.redis = 'fakeredis'
    AND X.covers_integration_path = true
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_NoE2E(X) DO
  e2e_suite ← createE2ESuite'()
  ASSERT e2e_suite.database = 'PostgreSQL'
    AND e2e_suite.redis = 'Redis'
    AND e2e_suite.covers_paths >= 3
END FOR
```

### C11: 导入错误无行号（问题八）

```pascal
FUNCTION isBugCondition_SilentSkip(X)
  INPUT: X of type ImportRow
  OUTPUT: boolean
  
  RETURN X.parse_exception IS NOT NULL
    AND X.row_number_recorded = false
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_SilentSkip(X) DO
  diag ← importWithDiag'(X)
  ASSERT diag.skipped_rows CONTAINS {row_number: X.excel_row, reason: X.exception_message}
END FOR
```

### C12: 29 文件直接 http（问题十二）

```pascal
FUNCTION isBugCondition_DirectHttp(X)
  INPUT: X of type VueFile
  OUTPUT: boolean
  
  RETURN X.imports_http_directly = true
    AND X.file NOT IN {LedgerPenetration, WorkpaperEditor}
END FUNCTION

// Property: Fix Checking
FOR ALL X WHERE isBugCondition_DirectHttp(X) DO
  file ← migrate'(X)
  ASSERT file.imports_http_directly = false
    AND file.uses_apiProxy_or_commonApi = true
END FOR

// Property: Preservation Checking — 全局
FOR ALL X WHERE NOT isBugCondition_DirectHttp(X) DO
  ASSERT F(X) = F'(X)
END FOR
```
