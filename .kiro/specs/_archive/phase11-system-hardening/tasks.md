# Phase 11 系统加固 — 任务清单

## P0：紧急修复（约 4 天）

### 任务组 1：空壳页面从导航移除（问题一）
- [x] 1.1 在 router/index.ts 中删除或注释 AIChatView 和 AIWorkpaperView 的路由条目
- [x] 1.2 在 ThreeColumnLayout.vue 的 navItems 中，给 MobileProjectList/MobileReportView/MobileWorkpaperEditor/ConsolSnapshots/CheckInsPage/AuxSummaryPanel 设置 maturity: 'developing'
- [x] 1.3 grep 验证 AIChatPanel.vue 不被其他组件引用（仅被 AIChatView 引用则无需改动）
- [x] 1.4 验证 7 个核心深度页面路由和功能不受影响

### 任务组 2：LLM stub 入口隐藏（问题三）
- [x] 2.1 AIPluginManagement.vue：8 个预设 stub 插件卡片加"即将上线"标签 + 执行按钮 disabled
- [x] 2.2 DisclosureEditor.vue："执行校验"按钮旁加 el-tooltip 提示"当前仅支持余额核对和子项校验"
- [x] 2.3 WorkpaperWorkbench.vue：AI 变动分析 catch 块从静默降级改为显示"AI 分析服务未启动"提示卡片
- [x] 2.4 WorkpaperWorkbench.vue：增加 WarningFilled 图标 import 和 gt-wpb-ai-unavailable 样式

### 任务组 3：底稿复核退回原因 + 逐条回复强制校验（问题六）
- [x] 3.1 数据库：ALTER TABLE working_paper ADD COLUMN rejection_reason/rejected_by/rejected_at
- [x] 3.2 ORM 模型：workpaper_models.py WorkingPaper 类新增 3 个字段
- [x] 3.3 Schema：working_paper.py ReviewStatusRequest 新增 reason: str | None = None
- [x] 3.4 后端服务：working_paper_service.py update_review_status 在 rejected 状态时强制 reason 非空
- [x] 3.5 后端服务：update_review_status 写入 rejection_reason/rejected_by/rejected_at 到 WorkingPaper
- [x] 3.6 后端路由：working_paper.py update_review_status 端点传递 reason 和 current_user.id
- [x] 3.7 后端路由：working_paper.py submit_review 新增第 5 项门禁（检查 ReviewRecord status=open 且未 replied 的数量）
- [x] 3.8 前端：WorkpaperList.vue 退回按钮改为弹出 el-dialog 强制填写退回原因
- [x] 3.9 前端：退回 API 调用传递 reason 参数

### 任务组 4：el-dialog 批量加 append-to-body（问题十）
- [x] 4.1 编写 Python 脚本 scripts/fix_dialog_append.py（正则替换，幂等）
- [x] 4.2 执行脚本，验证修复文件数量（实际修复 15 个文件，其余已有 append-to-body）
- [x] 4.3 验证核心页面弹窗已有 append-to-body（Adjustments/TrialBalance/WorkpaperList/ReportView 均已有）

---

## P1：重要修复（约 7 天）

### 任务组 5：附注编辑器上年数据 + 公式计算（问题七）
- [x] 5.1 后端：disclosure_engine.py 新增 get_prior_year_data 方法（查询 year-1 的附注数据）
- [x] 5.2 后端：disclosure_engine.py 新增 _get_prior_from_trial_balance 兜底方法
- [x] 5.3 后端：disclosure_notes.py 新增 GET /{project_id}/{year}/notes/{note_section}/prior-year 端点
- [x] 5.4 前端：DisclosureEditor.vue 新增 priorYearNote 状态变量和加载逻辑
- [x] 5.5 前端：DisclosureEditor.vue 表格增加"上年数"列（灰色斜体）
- [x] 5.6 前端：DisclosureEditor.vue 新增 getPriorYearValue 函数
- [x] 5.7 前端：DisclosureEditor.vue 新增 onCellValueChange 实时公式计算（纵向合计）
- [x] 5.8 前端：DisclosureEditor.vue 新增 recalcHorizontalFormula 横向公式（期初+变动=期末）
- [x] 5.9 前端：DisclosureEditor.vue el-input-number 绑定 @change="onCellValueChange"
- [x] 5.10 前端：DisclosureEditor.vue 合计行差异高亮（gt-formula-mismatch 红色波浪下划线）

### 任务组 6：合并报表模块标记 developing（问题二）
- [x] 6.1 ThreeColumnLayout.vue：合并项目/合并报表导航项设置 maturity: 'developing'
- [x] 6.2 验证后端 10 个合并路由代码不受影响（不删除不修改）

### 任务组 7：scope_cycles 落地到核心 4 个路由（问题九）
- [x] 7.1 deps.py：新增 get_user_scope_cycles 公共函数
- [x] 7.2 MappingService：新增 get_codes_by_cycles 方法（从 wp_account_mapping.json 读取循环→科目映射）
- [x] 7.3 trial_balance.py：get_trial_balance 端点增加 scope_cycles 过滤
- [x] 7.4 adjustments.py：list_adjustments 端点增加 scope_cycles 过滤
- [x] 7.5 ledger_penetration.py：balance 查询端点增加 scope_cycles 过滤
- [x] 7.6 disclosure_notes.py：get_tree 端点增加 scope_cycles 过滤
- [x] 7.7 验证 admin/partner 角色不受 scope_cycles 限制（返回全部数据）

### 任务组 8：dashboard 5 个硬编码 0 指标接入真实数据（问题十一）
- [x] 8.1 dashboard_service.py：overdue_projects 改为查询 projects 表（创建超 180 天未归档）
- [x] 8.2 dashboard_service.py：pending_review_workpapers 改为查询 working_paper 表（pending_level1/2）
- [x] 8.3 dashboard_service.py：qc_pass_rate 改为从 wp_qc_results 计算通过率
- [x] 8.4 dashboard_service.py：review_completion_rate 改为从 working_paper 计算复核完成率
- [x] 8.5 dashboard_service.py：adjustment_count 改为从 adjustments 表查询活跃数量

---

## P2：优化改进（约 9 天）

### 任务组 9：前端 API 调用统一为 apiProxy — 第 1 批向导组件（问题四+十二）
- [x] 9.1 BasicInfoStep.vue：import http → import { api } + 所有调用改为 api.get/api.post
- [x] 9.2 AccountImportStep.vue：同上改造
- [x] 9.3 AccountMappingStep.vue：同上改造
- [x] 9.4 MaterialityStep.vue：同上改造
- [x] 9.5 ReportLineMappingStep.vue：同上改造
- [x] 9.6 验证新建项目向导全流程数据展示正确

### 任务组 10：前端 API 调用统一 — 第 2 批布局组件
- [x] 10.1 ThreeColumnLayout.vue：import http → import { api }
- [x] 10.2 MiddleProjectList.vue：同上改造
- [x] 10.3 DetailProjectPanel.vue：同上改造
- [x] 10.4 FourColumnCatalog.vue：同上改造
- [x] 10.5 FourColumnContent.vue：同上改造
- [x] 10.6 验证三栏/四栏布局数据加载正确

### 任务组 11：前端 API 调用统一 — 第 3 批扩展组件
- [x] 11.1 LanguageSwitcher / StandardSelector / AuditTypeSelector 改造
- [x] 11.2 PluginList / PluginConfig 改造
- [x] 11.3 SignatureLevel1 / SignatureLevel2 / SignatureHistory 改造
- [x] 11.4 WPIndexGenerator / CICPAReportForm / ArchivalStandardForm 改造
- [x] 11.5 MetabaseDashboard / DrillDownNavigator / FilingError 改造
- [x] 11.6 NoteTrimPanel / DataImportPanel / SamplingPanel / SEChecklistPanel 改造

### 任务组 12：E2E 集成测试（问题五）
- [x] 12.1 新增 docker-compose.test.yml（PG + Redis 测试环境）
- [x] 12.2 新增 backend/tests/e2e/conftest.py（PG 连接 + AsyncClient 配置）
- [x] 12.3 新增 test_e2e_chain1.py：建项目 → 导数据 → 验证试算表 → 验证报表联动
- [x] 12.4 新增 test_e2e_chain2.py：创建 AJE → 验证试算表增量更新 → 验证报表更新
- [x] 12.5 新增 test_e2e_chain3.py：上传底稿 → 验证 WORKPAPER_SAVED → 验证审定数比对
- [x] 12.6 验证已有 1604 个单元测试不受影响

### 任务组 13：导入错误行号定位（问题八）
- [x] 13.1 smart_import_engine.py：convert_balance_rows 新增 diagnostics 参数，try/except 中记录 row_number + reason
- [x] 13.2 smart_import_engine.py：convert_ledger_rows 同上改造
- [x] 13.3 smart_import_streaming 调用方传入 diagnostics 列表，写入 ImportBatch 或返回前端
- [x] 13.4 前端 AccountImportStep.vue：导入结果页展示"跳过 N 行"+ 详情表格（行号+原因）

### 任务组 14：后端 stub 清理（问题十一补充）
- [x] 14.1 qc_engine.py：更新注释，去掉 "stubs" 标记（代码已全部实现）
- [x] 14.2 working_paper_service.py：删除旧 stub 方法 download_for_offline（已被 wp_download_service 替代）
- [x] 14.3 working_paper_service.py：删除旧 stub 注释 upload_offline_edit 中的 "stub: no actual file replacement"


---

## 合并报表深度开发（替代原任务组 6，约 16 天）

### 任务组 15：合并基础设施（数据库 + ORM + 树形服务）
- [x] 15.1 CREATE TABLE consol_worksheet（差额表，含 net_difference/children_amount_sum/consolidated_amount）
- [x] 15.2 CREATE TABLE consol_query_template（自定义查询模板）
- [x] 15.3 consolidation_models.py 新增 ConsolWorksheet + ConsolQueryTemplate ORM 模型
- [x] 15.4 实现 consol_tree_service.py：build_tree（三码构建）/ find_node / get_descendants / to_dict
- [x] 15.5 验证树形构建：3 级结构（集团→子公司→孙公司）正确嵌套

### 任务组 16：差额表计算引擎
- [x] 16.1 实现 consol_worksheet_engine.py：recalc_full（后序遍历，从叶子到根）
- [x] 16.2 实现 _calc_node：叶子节点 children_amount_sum = 本企业审定数（从 trial_balance 取）
- [x] 16.3 实现 _calc_node：中间节点 children_amount_sum = Σ(直接下级 consolidated_amount)
- [x] 16.4 实现 _get_elimination_map：按 related_company_codes 关联抵消分录到节点
- [x] 16.5 实现 net_difference = elim_debit - elim_credit，consolidated = children_sum + net_diff
- [x] 16.6 验证公式：3 个企业 + 2 笔抵消分录，合并数 = Σ(审定数) + Σ(差额)

### 任务组 17：节点汇总查询
- [x] 17.1 实现 consol_aggregation_service.py：query_node（self/children/descendants 三种模式）
- [x] 17.2 实现 _query_self：返回单节点差额表
- [x] 17.3 实现 _query_children：当前节点 + 直接子节点汇总
- [x] 17.4 实现 _query_descendants：当前节点 + 所有后代节点汇总
- [x] 17.5 验证：选择中间节点，三种模式返回不同的汇总结果

### 任务组 18：穿透查询
- [x] 18.1 实现 consol_drilldown_service.py：drill_to_companies（合并数→各企业构成）
- [x] 18.2 实现 drill_to_eliminations（企业→相关抵消分录明细）
- [x] 18.3 实现 drill_to_trial_balance（跳转到末端企业试算表，返回 drill_url）
- [x] 18.4 验证穿透链路：合并数 → 企业构成 → 抵消分录 → 试算表行

### 任务组 19：自定义透视查询 + Excel 导出
- [x] 19.1 实现 consol_pivot_service.py：execute_query（行/列维度 + 值字段 + 筛选）
- [x] 19.2 实现 _pivot_account_by_company（行=科目，列=企业，含合计列）
- [x] 19.3 实现 _pivot_company_by_account（行=企业，列=科目，含合计列）
- [x] 19.4 实现 _transpose（行列互换）
- [x] 19.5 实现 export_excel（openpyxl 导出，仿宋_GB2312 + Arial Narrow 排版）
- [x] 19.6 实现 save_template / list_templates（查询模板 CRUD）

### 任务组 20：API 路由层
- [x] 20.1 新建 consol_worksheet.py 路由文件（prefix=/api/consolidation/worksheet）
- [x] 20.2 实现 GET /tree（返回完整企业树 JSON）
- [x] 20.3 实现 POST /recalc（全量重算差额表）
- [x] 20.4 实现 GET /aggregate（节点汇总，mode=self|children|descendants）
- [x] 20.5 实现 GET /drill/companies + /drill/eliminations + /drill/trial-balance
- [x] 20.6 实现 POST /pivot + GET /pivot/export + POST /pivot/templates + GET /pivot/templates
- [x] 20.7 注册路由到 router_registry.py 的"合并报表"分组

### 任务组 21：后端同步→异步改造（10 个路由 + 13 个服务）
- [x] 21.1 consolidation.py：7 个端点从 def→async def，Depends(sync_db)→Depends(get_db)
- [x] 21.2 consol_scope.py：4 个端点同上改造
- [x] 21.3 consol_trial.py：3 个端点同上改造
- [x] 21.4 internal_trade.py：6 个端点同上改造
- [x] 21.5 component_auditor.py：8 个端点同上改造
- [x] 21.6 goodwill.py + forex.py + minority_interest.py：8 个端点同上改造
- [x] 21.7 consol_notes.py + consol_report.py：9 个端点同上改造
- [x] 21.8 对应 13 个服务文件：db.query()→await db.execute(sa.select())，.all()→.scalars().all()
- [x] 21.9 验证所有改造后的端点正常响应（不阻塞事件循环）

### 任务组 22：前端 API 服务层重建
- [x] 22.1 重写 consolidationApi.ts（40+ 个 API 函数 + 20+ 个 TypeScript 类型定义）
- [x] 22.2 验证 Pinia store（consolidation.ts）所有 action 的 API 调用正常
- [x] 22.3 验证 14 个子组件的数据加载正常

### 任务组 23：前端页面改造
- [x] 23.1 ConsolidationIndex.vue 改为 4 个 Tab（集团架构/差额表/穿透/自定义查询）+ 横幅
- [x] 23.2 Tab 1 集团架构：el-tree 三码树形 + 节点信息卡片 + 跳转项目按钮
- [x] 23.3 Tab 2 差额表：el-table（下级汇总/调整借贷/抵消借贷/差额净额/合并数）+ 汇总模式切换 + 重算按钮
- [x] 23.4 Tab 3 穿透：面包屑导航 + 三层穿透表格（企业构成→抵消分录→试算表跳转）
- [x] 23.5 Tab 4 自定义查询：行/列维度选择 + 值字段 + 转置开关 + 企业/科目筛选 + Excel 导出 + 模板管理
- [x] 23.6 导航开放：ThreeColumnLayout.vue 合并报表去掉 maturity: 'developing'

### 任务组 24：集成验证
- [x] 24.1 端到端：建合并项目 → 添加 3 个子公司 → 导入各子公司数据 → 重算差额表
- [x] 24.2 验证合并数 = Σ(下级审定数) + 差额净额
- [x] 24.3 验证穿透：合并数 → 企业构成 → 抵消分录 → 试算表 → 序时账
- [x] 24.4 验证透视：科目×企业 + 转置 + Excel 导出
- [x] 24.5 验证汇总模式：本级/直接下级/全部下级返回不同结果
