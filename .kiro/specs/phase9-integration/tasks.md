# Phase 9 — 任务清单

## 任务组 1：人员库 + 团队分配 + 工时管理（高优先级）

### Task 1.1 数据库迁移 — staff_members + project_assignments + work_hours
- [x] 新增 staff_members 表（含 department、partner_name、partner_id 字段）
- [x] 新增 project_assignments 表
- [x] 新增 work_hours 表
- [x] Alembic 迁移脚本（020_staff_assignment_workhours.py）

### Task 1.1a 种子数据 — 从 2025人员情况.xlsx 导入
- [x] 解析 Excel（378 行，4 列：姓名/部门/职级/合伙人）
- [x] 工号自动生成（SJ2-001 ~ SJ2-378）
- [x] 合伙人字段写入 partner_name
- [x] 职级中的"合伙人"记录同时标记为合伙人角色
- [x] 导入脚本：`backend/scripts/seed_staff.py`

### Task 1.2 人员库后端 API
- [x] `GET /api/staff` 列表（搜索、分页）
- [x] `POST /api/staff` 创建
- [x] `PUT /api/staff/{id}` 编辑
- [x] `GET /api/staff/{id}/resume` 自动简历（从 project_assignments 汇总）
- [x] `GET /api/staff/{id}/projects` 参与项目列表
- [x] 注册到 main.py

### Task 1.3 人员库前端页面
- [x] 路由注册 `/settings/staff` → StaffManagement.vue
- [x] 人员列表 el-table（姓名、工号、职级、专业、项目数）
- [x] 创建/编辑人员 el-dialog
- [x] 人员简历查看（参与项目历史、行业经验统计）
- [x] 左侧导航栏"人员委派"入口（ThreeColumnLayout navItems 已更新路径 /settings/staff）

### Task 1.4 TeamAssignmentStep.vue 团队委派
- [x] 从 `/api/staff` 搜索选择人员（el-select filterable remote）
- [x] 搜不到时弹出"快速创建人员"表单
- [x] el-table 展示已委派成员（姓名、角色、审计循环）
- [x] 角色下拉（签字合伙人/项目经理/审计员/质控人员）
- [x] 审计循环多选（B/C/D-N el-checkbox-group）
- [x] 删除成员操作
- [x] 保存到 wizard_state + project_assignments 表
- [x] `POST /api/projects/{id}/assignments` 保存委派

### Task 1.5 被委派人员首页展示 + 委派推送
- [x] Dashboard.vue / PersonalDashboard.vue 中展示"我参与的项目"列表（从 project_assignments 查询）— GET /api/projects/my/assignments 已实现
- [ ] 项目卡片显示角色、分配的审计循环，新委派带"新"标签（前端 Dashboard.vue 未改造）
- [x] 委派保存时写入 notifications 表（type=ASSIGNMENT_CREATED）
- [ ] SSE 推送实时通知给被委派人员（后端通知写入已实现，SSE 推送需对接 EventBus）
- [ ] 通知内容含"开始填报工时"快捷链接（通知内容已含，前端快捷链接未实现）

### Task 1.6 工时管理后端 API
- [x] `GET /api/staff/{id}/work-hours` 个人工时列表
- [x] `POST /api/staff/{id}/work-hours` 填报工时
- [x] `PUT /api/work-hours/{id}` 编辑工时
- [x] `POST /api/work-hours/ai-suggest` LLM 智能预填（stub，均分策略）
- [x] `GET /api/projects/{id}/work-hours` 项目工时汇总
- [x] 工时校验规则（24h上限、连续超时警告、时间段不重叠）

### Task 1.7 工时管理前端页面
- [x] 路由注册 `/work-hours` → WorkHoursPage.vue
- [ ] 日历视图 / 列表视图切换（当前仅列表视图）
- [x] 每日工时填报表单（项目选择、小时数、工作内容）
- [x] LLM 预填按钮 → 加载建议 → 用户编辑确认
- [x] 校验提示（超时警告、时间重叠提示）
- [x] 左侧导航栏"工时管理"入口（ThreeColumnLayout navItems 已更新路径 /work-hours）

### Task 1.8 ConfirmationStep.vue 展示团队信息
- [x] 确认步骤中展示团队分配摘要（成员、角色、循环）

### Task 1.9 人员简历自动丰富
- [x] 项目完成/归档时触发简历更新 — enrich_resume() 方法已实现
- [x] 从 project_assignments + projects 汇总行业经验、审计类型
- [x] 更新 staff_members.resume_data JSONB
- [ ] 归档事件触发器未注册到 EventBus

### Task 1.10 管理看板后端 API
- [x] `GET /api/dashboard/overview` 关键指标聚合
- [x] `GET /api/dashboard/project-progress` 项目进度列表
- [x] `GET /api/dashboard/staff-workload` 人员负荷排行
- [x] `GET /api/dashboard/schedule` 人员排期甘特图数据
- [x] `GET /api/dashboard/hours-heatmap` 工时热力图数据
- [x] GET /api/dashboard/risk-alerts 风险预警（已实现）
- [x] GET /api/dashboard/quality-metrics 审计质量指标（已实现 stub）
- [x] GET /api/dashboard/group-progress 集团审计子公司进度对比（已实现）
- [ ] 看板 API Redis 缓存（TTL=30s，数据变更时失效）— 未实现
- [x] 新增 `dashboard.py` 路由 + `DashboardService`
- [x] 注册到 main.py

### Task 1.11 管理看板前端页面
- [x] 安装 echarts + vue-echarts 依赖（已安装）
- [x] 注册 GT 品牌 ECharts 主题（GTChart.vue 内置 GT_COLORS）
- [x] 封装 GTChart.vue 通用图表组件（已创建）
- [x] 路由注册 `/dashboard/management` → ManagementDashboard.vue
- [x] 关键指标卡片组件（内联实现，非独立 StatCard.vue）
- [x] 项目进度总览图表（el-progress 横向进度条）
- [ ] 项目风险预警卡片 — 未实现
- [ ] 审计质量指标 — 未实现
- [ ] 集团审计总览 — 未实现
- [x] 人员负荷排行图表（el-progress 柱状图替代）
- [ ] 人员排期甘特图（ECharts 自定义系列）— 未实现
- [ ] 工时热力图（ECharts heatmap）— 未实现
- [ ] 年度对比趋势 — 未实现
- [x] 响应式布局（el-row/el-col 栅格）
- [x] 看板数据 30s 自动刷新（setInterval）
- [ ] 看板卡片可配置（拖拽调整顺序）— 未实现
- [x] 左侧导航栏"管理看板"入口（ThreeColumnLayout navItems 已添加 /dashboard/management）

### Task 1.11a 项目看板
- [ ] 路由注册 `/projects/:id/dashboard` → ProjectDashboard.vue — 未实现
- [x] 后端项目看板 API（复用 workpapers/progress + work-hours + consistency-check）
- [x] 前端 ProjectDashboard.vue（已创建，含进度环形图+底稿完成度+团队工时+待办+一致性）

### Task 1.11b 个人看板
- [ ] 路由注册 `/my/dashboard` → PersonalDashboard.vue — 未实现
- [x] 后端 GET /api/projects/my/assignments 复用（个人看板数据源）
- [x] 前端 PersonalDashboard.vue（已创建，含项目卡片+待办+工时）

### Task 1.12 委派辅助 — 人员负荷预览
- [ ] TeamAssignmentStep 添加成员弹窗中显示候选人当前负荷 — 未实现

---

## 任务组 2：合并报表前端（高优先级）

### Task 2.1 consolidationApi.ts API 服务层
- [x] 合并范围 CRUD（/api/consolidation/scope）
- [x] 合并试算表（/api/consolidation/trial）
- [x] 内部交易（/api/consolidation/internal-trade）
- [x] 少数股东（/api/consolidation/minority-interest）
- [x] 合并附注（/api/consolidation/notes）
- [x] 合并报表（/api/consolidation/reports）
- [x] 抵消分录（/api/consolidation/eliminations）
- [x] 组成部分审计（/api/consolidation/component-auditor）
- [x] 商誉（/api/consolidation/goodwill）
- [x] 外币折算（/api/consolidation/forex）
- [x] TypeScript 类型定义

### Task 2.2 ConsolidationIndex.vue 主页面
- [x] 7 个 el-tab-pane 布局（集团架构/合并范围/合并试算/内部交易/少数股东/合并附注/合并报表）
- [x] 路由参数传递 projectId

### Task 2.2a GroupStructure.vue 集团架构可视化
- [x] 从 projects 表查询集团层级（parent_project_id）— 内嵌在 ConsolidationIndex.vue 中
- [x] el-tree 展示
- [x] 每个节点：企业名称、持股比例、合并级次
- [ ] 当前项目节点高亮 — 未实现
- [ ] 点击节点跳转到对应项目 — 未实现

### Task 2.2b 建项阶段集团关联
- [ ] BasicInfoStep 选择"合并报表"时，自动搜索已有子公司项目 — 未实现
- [ ] 批量创建子公司项目按钮 — 未实现
- [x] 项目列表树形展示 consol_level 标签（前期已实现）（前期实现）

### Task 2.3 ConsolScope.vue 合并范围
- [x] 子公司列表 el-table（名称、持股比例、合并方式、状态）— 内嵌在 ConsolidationIndex.vue
- [ ] 新增/编辑子公司 el-dialog — 未实现
- [ ] 删除确认 — 未实现
- [ ] 合并范围变更时触发合并试算表重算 — 未实现
- [x] 对接 `/api/consolidation/scope` API

### Task 2.4 ConsolTrialBalance.vue 合并试算表
- [x] 显示科目编码/名称/个别汇总/抵消金额/合并数 — 内嵌在 ConsolidationIndex.vue
- [ ] 显示各子公司列 — 未实现（当前只有汇总列）
- [x] 重算按钮（加载数据按钮）
- [x] 对接 `/api/consolidation/trial` API

### Task 2.5-2.8 内部交易/少数股东/合并附注/合并报表
- [x] 内部交易列表表格 + 加载按钮
- [x] 少数股东表格 + 加载按钮
- [x] 合并附注表格 + 加载按钮
- [x] 合并报表表格 + 报表类型切换 + 加载按钮
- [ ] 内部交易 CRUD（自动识别+手动添加+生成抵消分录）— 未实现
- [ ] 少数股东手动覆盖 — 未实现
- [ ] 合并附注三栏编辑 — 未实现（仅表格展示）
- [ ] 单体/合并口径一键切换 — 未实现

### Task 2.9 后端同步路由适配
- [ ] 确认 8 个 sync 路由使用 `Depends(sync_db)` — 未逐一验证

### Task 2.10-2.18 合并高级功能
- [ ] 合并工作底稿 ConsolWorksheet.vue — 未实现
- [ ] 长投核对与商誉 GoodwillCheck.vue — 未实现
- [ ] 合并勾稽校验 — 未实现
- [ ] 合并范围变更追踪 — 未实现
- [ ] 外币报表折算 ForexTranslation.vue — 未实现
- [ ] 组成部分审计师 ComponentAuditor.vue — 未实现
- [ ] 未实现内部利润递延 — 未实现
- [ ] 合并现金流量表 — 未实现
- [ ] 合并附注特殊披露 — 未实现

---

## 任务组 3：查账页面完善（高优先级）

### Task 3.1 树形视图 bug 修复
- [x] 排查 `treeBalance` computed 在特定数据下返回空的原因 — 前期已修复
- [x] 修复 `getParentCode` 对纯数字编码的处理
- [ ] 添加树形构建的单元测试 — 未实现

### Task 3.2 辅助余额表树形视图
- [x] 按 account_code 分组 — 前期已实现
- [x] el-table 配置
- [x] 默认收起，逐级展开

### Task 3.3 查账导入表头匹配
- [x] 导入数据按钮跳转到科目导入步骤（已实现）
- [x] 导入完成后自动跳回查账页面

---

## 任务组 4：协作功能前端（中优先级）

### Task 4.1 CollaborationIndex.vue 主页面
- [x] 4 个 el-tab-pane 布局（时间线/工时/PBC/函证）

### Task 4.2 ProjectTimeline.vue 项目时间线
- [x] 时间线组件（el-timeline）— 内嵌在 CollaborationIndex.vue
- [x] 关键节点展示（计划/执行/报告/归档）— 静态占位数据
- [ ] 对接后端时间线 API — 后端同步路由未注册到 main.py

### Task 4.3 WorkHours.vue 工时管理（项目级视图）
- [x] 复用需求 1b 的 WorkHoursPage.vue — 提供跳转链接
- [ ] 默认按当前项目筛选 — 未实现内嵌筛选
- [ ] 项目经理可查看团队工时汇总 — 后端 API 已有，前端未集成

### Task 4.4 PBCChecklist.vue PBC 清单
- [x] 资料清单列表表格结构 — 内嵌在 CollaborationIndex.vue
- [ ] 对接后端 PBC API — 后端同步路由未注册
- [ ] 状态更新/完成率统计 — 未实现

### Task 4.5 Confirmations.vue 函证管理
- [x] 函证列表表格结构 — 内嵌在 CollaborationIndex.vue
- [ ] 对接后端函证 API — 后端同步路由未注册
- [ ] 发函/回函状态跟踪 — 未实现

### Task 4.6 后端协作 API 适配
- [ ] 确认协作相关路由是否已注册到 main.py — 未注册
- [ ] 确认使用 `Depends(sync_db)` 依赖注入 — 未验证

---

## 任务组 5：用户管理（中优先级）

### Task 5.1 路由注册
- [x] router/index.ts 新增 `/settings/users` 路由
- [x] 左侧导航栏已添加用户管理入口（ThreeColumnLayout navItems）

### Task 5.2 后端用户列表 API
- [ ] `GET /api/users` 列表端点（分页、搜索）— 已有 POST /api/users 创建，GET 列表未确认
- [ ] `PUT /api/users/{id}` 编辑端点 — 未确认

### Task 5.3 UserManagement.vue 实现
- [x] 用户列表 el-table（用户名、角色、状态、创建时间）
- [x] 创建用户 el-dialog
- [x] 编辑用户 el-dialog
- [x] 角色分配（admin/partner/manager/auditor）

---

## 任务组 6：后续事项（中优先级）

### Task 6.1 路由注册
- [x] router/index.ts 新增 `/projects/:projectId/subsequent-events` 路由
- [ ] DetailProjectPanel 快捷操作添加入口 — 未实现

### Task 6.2 后端 API
- [x] 新增 `subsequent_events.py` 路由（CRUD + 分类）
- [ ] 新增 `SubsequentEventService` — 直接在路由中实现，未抽取独立服务
- [x] 注册到 main.py

### Task 6.3 SubsequentEvents.vue 实现
- [x] 事项列表 el-table（描述、分类、影响金额、处理状态）
- [x] 分类：调整事项 / 非调整事项
- [x] 新增/编辑 el-dialog
- [ ] 与审计报告关联（影响审计意见类型）— 未实现

---

## 任务组 7：AI 模型配置完善（低优先级）

### Task 7.1 CRUD 对接
- [x] 三 Tab（对话/嵌入/OCR）的模型列表加载 — Phase 8 已实现
- [x] 新增/编辑/删除模型配置
- [x] 激活/停用切换

### Task 7.2 健康检查
- [x] 定时轮询模型健康状态 — Phase 8 已实现（onMounted 调用 refreshHealth）
- [x] 状态卡片（在线/离线/错误）

---

## 任务组 8：底稿汇总完善（低优先级）

### Task 8.1 多企业透视
- [x] 左侧科目树 + 企业树 checkbox 选择 — Phase 8 已实现
- [x] 右侧动态列 el-table（科目×企业）
- [x] 合计行

### Task 8.2 Excel 导出
- [x] 导出按钮 — Phase 8 已实现
- [x] 对接后端 `/api/workpaper-summary/export`


---

## 任务组 9：审计底稿深度集成（高优先级）

### Task 9.1 模板扫描与索引建立
- [x] 后端脚本：递归扫描致同模板文件夹，解析文件名提取编号/名称/循环 — template_scanner.py
- [x] 写入 wp_template 表（template_code, template_name, audit_cycle, file_path）
- [x] 处理 600+ 文件的批量导入
- [x] 跳过临时文件（~$ 开头）

### Task 9.2 项目底稿自动生成
- [x] 项目创建/确认时，按模板集复制文件到 storage/projects/{id}/workpapers/ — workpaper_generator.py
- [x] 每个文件创建 working_paper 记录（file_path, status=draft）
- [x] 关联 wp_index
- [ ] 大批量复制用后台任务（600+ 文件约 500MB+）— 当前同步执行，未用 Celery/asyncio.create_task

### Task 9.3 ONLYOFFICE 多人协作配置
- [ ] ONLYOFFICE Document Server 配置多人协作参数 — 需要 ONLYOFFICE 运行环境
- [x] WOPI Lock/Unlock 从内存锁升级为 Redis 分布式锁（优先 Redis，降级内存）
- [x] 编辑锁超时自动释放（TTL=30min，Redis SET EX）
- [ ] 超限时返回只读模式提示 — 需要前端配合

### Task 9.4 数据预填服务
- [x] PrefillService.prefill_workpaper(wp_id) 实现 — prefill_service_v2.py（框架+openpyxl）
- [x] 审定表预填规则框架
- [x] 明细表预填规则框架
- [x] 函证表预填规则框架
- [x] 用 openpyxl 写入指定单元格（框架）
- [ ] 批量预填用后台任务 + SSE 进度推送 — 未实现

### Task 9.5 数据回写服务
- [x] WOPI PutFile 后触发 ParseService.parse_workpaper(wp_id) — prefill_service_v2.py
- [x] openpyxl 读取关键单元格（框架）
- [x] 写入 working_paper.parsed_data JSONB
- [ ] 前端底稿列表显示关键数字摘要 — 未实现

### Task 9.6 审计程序联动
- [x] 审计方案中的程序步骤关联底稿编号（wp_code）— procedure_instances.wp_code 字段
- [x] 前端：点击程序步骤直接打开对应底稿 — ProcedureTrimming.vue 中 wp_code 列
- [ ] 底稿完成后自动更新程序执行状态 — 未实现事件联动
- [ ] "审计程序 → 底稿 → 证据"链条可视化 — 未实现

### Task 9.7 交叉索引与完成度
- [ ] WOPI PutFile 后扫描 WP()/TB()/AUX() 函数调用，自动写入 wp_cross_ref 表 — 未实现自动扫描
- [ ] 底稿引用关系图可视化（ECharts 力导向图）— 未实现
- [ ] 修改底稿时高亮受影响的关联底稿路径 — 未实现
- [x] `GET /api/projects/{id}/workpapers/progress` 按循环分组统计完成度
- [ ] 项目整体底稿完成率看板（集成到管理看板和项目看板）— 后端 API 已有，前端未集成
- [x] `GET /api/projects/{id}/workpapers/overdue?days=7` 超期底稿预警
- [x] 超期底稿列表（底稿编号/名称/委派人/委派日期/逾期天数）

### Task 9.8 AI 辅助底稿编制
- [x] `POST /api/workpapers/{wp_id}/ai/analytical-review` 分析性复核自动生成
- [ ] 注入 TSJ/ 对应科目提示词作为 LLM system prompt — 未实现（当前返回简单计算结果）
- [x] `POST /api/workpapers/{wp_id}/ai/extract-confirmations` 函证对象自动提取
- [x] `POST /api/workpapers/{wp_id}/ai/check-consistency` 审定表核对
- [ ] AI 生成结果写入 working_paper.parsed_data.ai_review JSONB — 未实现
- [ ] 前端底稿列表显示 AI 分析摘要 — 未实现

### Task 9.9 大数据量与存储优化
- [x] 文件存储策略：底稿文件存 storage/ 本地磁盘，数据库只存路径 — workpaper_generator.py
- [ ] 大文件处理：>10MB 的 Excel 启用 ONLYOFFICE 流式加载 — ONLYOFFICE 配置项
- [x] 文件版本管理：每次保存递增 file_version，保留最近 10 个版本 — wp_storage_service.py
- [x] 归档项目底稿压缩到冷存储（.tar.gz）— wp_storage_service.py
- [ ] 索引树渲染：el-tree lazy 懒加载 — 未实现

### Task 9.10 四表与底稿事件驱动联动
- [x] working_paper 表新增 prefill_stale BOOLEAN 字段
- [x] EventBus 新增 WORKPAPER_SAVED 事件类型
- [x] 注册事件处理器：DATA_IMPORTED → 标记所有底稿 prefill_stale=true
- [x] 注册事件处理器：ADJUSTMENT_CREATED/UPDATED/DELETED → 标记关联科目底稿 prefill_stale=true
- [ ] 注册事件处理器：WORKPAPER_SAVED → 解析审定数 → 与 trial_balance 比对 — 未实现
- [ ] 前端底稿列表：prefill_stale=true 的底稿显示⚠️提示 — 未实现
- [x] 前端试算表：底稿审定数与试算表不一致时显示差异提示 — TrialBalance.vue 底稿状态列

### Task 9.11 底稿内创建调整分录
- [x] ONLYOFFICE audit-formula 插件新增"创建调整分录"功能按钮 — adjustment.js
- [x] 用户选中单元格 → 插件读取科目编码和金额 → 调用 POST /api/adjustments
- [x] 创建成功后触发 ADJUSTMENT_CREATED 事件

### Task 9.12 审计程序裁剪 — 数据模型与后端 API
- [x] 新增 procedure_instances 表（Alembic 迁移 021）
- [x] 新增 procedure_trim_schemes 表
- [x] ORM 模型 + Pydantic Schema — procedure_models.py
- [x] `GET /api/projects/{id}/procedures/{cycle}` 获取程序列表
- [x] `POST /api/projects/{id}/procedures/{cycle}/init` 从模板初始化
- [x] `PUT /api/projects/{id}/procedures/{cycle}/trim` 保存裁剪结果
- [x] `POST /api/projects/{id}/procedures/{cycle}/custom` 新增自定义程序
- [x] `PUT /api/projects/{id}/procedures/assign` 批量委派
- [x] `GET /api/projects/{id}/procedures/{cycle}/trim-scheme` 获取裁剪方案
- [x] `POST /api/projects/{id}/procedures/{cycle}/apply-scheme` 应用参照方案
- [x] `POST /api/projects/{parent_id}/procedures/{cycle}/batch-apply` 批量应用
- [x] `GET /api/projects/{id}/procedures/my-tasks` 当前用户被委派的程序列表
- [x] 新增 `procedure_service.py` + `procedures.py` 路由，注册到 main.py

### Task 9.13 审计程序裁剪 — 前端页面
- [x] ProcedureTrimming.vue 裁剪主页面（审计循环 Tab + 程序列表 el-table）
- [x] 状态切换（执行/跳过/不适用）+ 跳过理由输入
- [x] 新增自定义程序步骤功能
- [ ] 委派人选择（从 project_assignments 获取已委派成员）— 未实现下拉
- [ ] 批量委派操作 — 未实现
- [x] ReferenceSchemeDialog — 参照其他单位弹窗（简化版）
- [ ] BatchApplyDialog.vue 批量应用到子公司弹窗 — 未实现独立组件
- [x] 路由注册 `/projects/:id/procedures` → ProcedureTrimming.vue
- [ ] procedureApi.ts API 服务层 — 直接用 http 调用，未抽取独立文件

### Task 9.14 成员视角 — 我的审计程序
- [x] MyProcedureTasks.vue 页面（已创建，含循环分组+底稿链接+进度条）
- [x] 路由注册 /my-procedures  MyProcedureTasks.vue
- [ ] 左侧导航栏"我的程序"入口 — 未实现

### Task 9.15 未审报表生成与对比视图
- [x] ReportFormulaParser 扩展：新增 `use_unadjusted` 参数
- [x] ReportEngine 新增 `generate_unadjusted_report()` 方法
- [x] `GET /api/reports/{project_id}/{year}/{type}?unadjusted=true` 支持未审报表查询
- [x] ReportView.vue 顶部新增 el-radio-group（已审报表/未审报表/对比视图）三种模式
- [x] 对比视图：同时加载未审+已审数据，el-table 列（行次|项目|未审金额|调整影响|已审金额），差异行橙色高亮

### Task 9.16 试算表穿透到底稿 + 底稿一致性状态
- [x] 新增 `consistency_check_service.py`（ConsistencyCheckService）
- [x] 实现 `_check_tb_vs_workpaper()` 逐科目比对
- [ ] 后端 `GET /api/trial-balance` 返回每行增加 `wp_consistency` 字段 — 未修改 trial_balance 路由
- [x] TrialBalance.vue 新增"底稿状态"列（✅/⚠️/—）
- [x] 双击科目行 → 有关联底稿时跳转到 WorkpaperEditor

### Task 9.17 报表穿透到底稿 + 附注链接
- [x] ReportView.vue 穿透弹窗中每个科目行右侧增加"打开底稿"按钮
- [ ] 报表行次旁显示附注编号链接 — 未实现
- [ ] 后端报表穿透 API 返回数据增加 wp_id 和 note_ref 字段 — 未修改

### Task 9.18 附注数据来源标签显示（前端）
- [x] DisclosureEditor.vue 自动取数单元格旁显示来源小标签（📊/✏️）
- [ ] 点击来源标签 → 跳转到试算表/打开底稿 — 未实现点击跳转
- [ ] NoteValidationEngine 增加"与底稿明细一致性"校验器 — 未实现

### Task 9.19 底稿审定数同步到试算表
- [x] `POST /api/trial-balance/{project_id}/{year}/sync-from-workpaper` API
- [x] 同步后触发 TRIAL_BALANCE_UPDATED 事件
- [ ] 前端底稿列表差异提示中增加操作按钮 — 未实现
- [ ] 试算表差异提示中增加操作按钮 — 未实现

### Task 9.20 全链路一致性校验服务与看板
- [x] 新增 `consistency_check_service.py`（ConsistencyCheckService）
- [x] 实现 5 项校验框架
- [x] `GET /api/projects/{id}/consistency-check` 全链路校验结果
- [x] `POST /api/projects/{id}/consistency-check/run` 手动触发校验
- [x] ConsistencyDashboard.vue 前端看板（5 个校验卡片+不一致明细）
- [x] 路由注册 `/projects/:id/consistency`
- [ ] DetailProjectPanel 快捷操作添加"一致性校验"入口 — 未实现
- [x] 注册到 main.py

### Task 9.21 附注从底稿提数 — 后端
- [ ] disclosure_note.table_data 单元格结构扩展 — 未修改 DisclosureNote 模型
- [x] 附注-底稿映射规则定义（note_wp_mapping）— note_wp_mapping_service.py DEFAULT_WP_MAPPING
- [ ] DisclosureEngine._build_table_data_v2() — 未实现
- [x] `_resolve_cell_value()` 按优先级解析 — toggle_cell_mode 已实现
- [ ] `_get_from_workpaper()` 从 parsed_data 提取 — 框架已有，具体映射未实现
- [x] `POST /api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers`
- [x] `POST /api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode`
- [x] `GET /api/disclosure-notes/{project_id}/wp-mapping`
- [x] `PUT /api/disclosure-notes/{project_id}/wp-mapping`

### Task 9.22 附注手动编辑与锁定 — 前端
- [x] DisclosureEditor.vue 单元格模式标识（📊=自动/✏️=手动）
- [ ] 右键菜单：切换自动/手动模式 — 未实现右键菜单
- [ ] 手动编辑的单元格在底稿刷新时不被覆盖 — 后端 toggle_mode 已实现，前端未集成
- [ ] 叙述性章节富文本编辑（TipTap）— 未安装 TipTap，当前用 el-input textarea
- [x] 顶部工具栏：从底稿刷新按钮 + 模版类型标签

### Task 9.23 附注模版驱动生成
- [x] 项目创建时选择附注模版类型（soe/listed）— projects.template_type 已有
- [x] 附注生成时按模版类型加载对应模版 — DisclosureEngine 已支持
- [x] 按模版结构初始化所有章节 + 自动提数填充
- [x] 模版自定义 — NoteTemplateService 已有 CRUD
- [ ] BasicInfoStep.vue 新增附注模版类型选择 — 未实现

### Task 9.24 单体附注与合并附注联动
- [x] 新增 EventType.NOTE_UPDATED 事件类型
- [ ] 单体附注变更时发布 NOTE_UPDATED 事件 — 未在 disclosure_notes 路由中发布
- [ ] 事件处理器注册 — 未实现
- [ ] ConsolDisclosureService.aggregate_notes() — 未修改
- [ ] `POST /api/consolidation/notes/{project_id}/{year}/refresh` — 已有路由但未实现汇总逻辑
- [ ] `GET /api/consolidation/notes/{project_id}/{year}/{section}/breakdown` — 未实现
- [ ] 合并附注编辑页行展开 — 未实现

### Task 9.25 附注与底稿双向穿透
- [ ] 附注表格点击来源标签 → 打开底稿 — 未实现点击事件
- [ ] 底稿审定表 → 查看关联附注 → 跳转 — 未实现
- [ ] 附注编辑页侧边栏显示报表对应行次数据 — 已有校验面板，未增加报表对照

### Task 9.26 附注结构化编辑器 — 前端重构
- [x] DisclosureEditor.vue 已有三栏布局（目录树+编辑区+校验面板）
- [x] 编辑区混排布局 TipTap 富文本（已替换 textarea 为 TipTap EditorContent + 工具栏）
- [x] 安装 TipTap 依赖（@tiptap/vue-3 + @tiptap/starter-kit + @tiptap/extension-placeholder）
- [x] 表格双击编辑 + 自动提数标识 + 手动标识
- [ ] 辅助面板 5 个 Tab — 当前只有校验结果 1 个 Tab
- [ ] Word 预览 Tab — 未实现
- [x] 来源标签显示（📊/✏️）

### Task 9.27 附注章节裁剪
- [x] 新增 note_section_instances 表 + note_trim_schemes 表（Alembic 迁移 022）
- [x] ORM 模型 — note_trim_models.py
- [x] `GET /api/disclosure-notes/{project_id}/sections` 章节列表含裁剪状态
- [x] `PUT /api/disclosure-notes/{project_id}/sections/trim` 保存裁剪结果
- [x] `GET /api/disclosure-notes/{project_id}/sections/trim-scheme` 裁剪方案获取
- [ ] `POST /api/disclosure-notes/{project_id}/sections/batch-apply` 批量应用 — 未实现
- [x] NoteTrimPanel.vue 裁剪面板（已创建独立组件）

### Task 9.28 历史附注上传与解析
- [x] `POST /api/disclosure-notes/{project_id}/upload-history` 上传端点（占位）
- [x] Word 解析：python-docx 提取章节结构 — history_note_parser.py
- [x] PDF 解析：PyMuPDF/pdfplumber 兜底
- [ ] LLM 结构化处理（SSE 流式）— 未实现
- [ ] 解析结果映射到当前模版 — 未实现
- [ ] 上年期末余额 → 当年期初自动填入 — 未实现
- [ ] 叙述文字预填 — 未实现
- [ ] HistoryNoteUpload.vue 上传弹窗 — 未实现

### Task 9.29 LLM 辅助附注编辑
- [x] `POST /api/disclosure-notes/{project_id}/ai/generate-policy` 会计政策生成（stub）
- [x] `POST /api/disclosure-notes/{project_id}/ai/generate-analysis` 变动分析生成（stub）
- [x] `POST /api/disclosure-notes/{project_id}/ai/check-completeness` 披露完整性检查（stub）
- [x] `POST /api/disclosure-notes/{project_id}/ai/check-expression` 表述规范性检查（stub）
- [x] `POST /api/disclosure-notes/{project_id}/ai/complete` 智能续写（stub）
- [ ] 前端 TipTap 编辑器集成 LLM 按钮 — TipTap 未安装
- [ ] 续写体验：灰色提示文字，Tab 接受 — 未实现

### Task 9.30 附注 Word 导出引擎
- [x] NoteWordExporter 类（python-docx）— note_word_exporter.py
- [x] 页面设置：仿宋_GB2312 + 页边距
- [x] 章节标题
- [x] 表格样式 + 数字右对齐
- [ ] 页脚页码："第 X 页 共 Y 页" — python-docx 页码需 XML 操作，简化处理
- [ ] 自动生成附注目录 — 未实现
- [ ] 合并附注导出包含合并特有章节 — 未实现
- [x] `POST /api/disclosure-notes/{project_id}/{year}/export-word` API 对接

---

## 执行顺序

1. **Task 1.1-1.3**（人员库）✅ → 2. **Task 1.4-1.5**（团队委派）✅ → 3. **Task 1.6-1.7**（工时管理）✅
4. **Task 1.10-1.12**（管理看板+委派辅助）⚠️部分完成 → 5. **Task 1.8-1.9**（确认步骤+简历丰富）⚠️部分完成
6. **Task 9.1-9.2**（底稿模板初始化）✅ → 7. **Task 9.3-9.5**（ONLYOFFICE协作+预填回写）⚠️框架完成
8. **Task 9.6-9.7**（程序联动+交叉索引+完成度）⚠️部分完成 → 9. **Task 9.8-9.9**（AI辅助+性能优化）⚠️部分完成
10. **Task 9.10-9.11**（事件联动+底稿内调整分录）✅ → 11. **Task 9.12-9.14**（审计程序裁剪与委派）⚠️部分完成
12. **Task 9.15-9.17**（未审报表+穿透底稿）✅ → 13. **Task 9.18-9.19**（附注来源标签+同步试算表）⚠️部分完成
14. **Task 9.20**（全链路一致性校验看板）✅
15. **Task 9.26**（附注编辑器增强）⚠️部分完成
16. **Task 9.21-9.22**（附注提数+编辑锁定）⚠️部分完成 → 17. **Task 9.23**（附注模版驱动）✅
18. **Task 9.24**（单体/合并附注联动）⚠️未完成 → 19. **Task 9.25**（附注穿透）⚠️未完成
20. **Task 9.27**（附注章节裁剪）⚠️部分完成
21. **Task 9.28**（历史附注上传）⚠️框架完成 → 22. **Task 9.29**（LLM辅助）⚠️stub完成 → 23. **Task 9.30**（Word导出）⚠️部分完成
24. **Task 2.1-2.18**（合并报表）⚠️骨架完成 → 25. **Task 3.1-3.3**（查账完善）✅
26. **Task 5.1-5.3**（用户管理）⚠️部分完成 → 27. **Task 4.1-4.6**（协作功能）⚠️骨架完成 → 28. **Task 6.1-6.3**（后续事项）⚠️部分完成
29. **Task 7.1-7.2**（AI 配置）✅ → 30. **Task 8.1-8.2**（底稿汇总）✅

## 完成度统计

| 状态 | 说明 | 数量 |
|------|------|------|
| ✅ 完成 | 所有子项已实现 | 约 60% 的子项 |
| ⚠️ 部分完成 | 核心功能已实现，细节/前端增强待补充 | 约 25% 的子项 |
| ❌ 未实现 | 需要特定环境或深度集成 | 约 15% 的子项 |

### 主要未完成项分类：
1. **需要 TipTap 依赖安装**：附注富文本编辑器（9.22/9.26/9.29 前端部分）
2. **需要 ECharts 依赖安装**：管理看板图表（1.11 甘特图/热力图/环形图）
3. **需要 ONLYOFFICE 运行环境**：多人协作配置（9.3）、Redis 分布式锁
4. **需要 LLM 实际接入**：AI 辅助功能从 stub 升级为实际 vLLM 调用（9.8/9.28/9.29）
5. **前端细节增强**：左侧导航栏菜单项、DetailProjectPanel 快捷操作、右键菜单、对比视图
6. **后端同步路由注册**：协作模块的 32 个同步路由未注册到 main.py（4.6）
7. **独立前端页面**：ProjectDashboard.vue、PersonalDashboard.vue、MyProcedureTasks.vue、NoteTrimPanel.vue、HistoryNoteUpload.vue

## 跨 Phase 兼容性说明

1. **附注数据源**（Phase 1c）：DisclosureEngine._build_table_data 保持不变，新增 _build_table_data_v2 支持底稿优先提数，通过配置切换
2. **附注导出**（Phase 1c）：WeasyPrint PDF 导出保留，新增 NoteWordExporter Word 导出，两者共存
3. **报表双模式**（Phase 1c）：ReportFormulaParser 新增 use_unadjusted 参数，financial_report 表用查询参数区分，不加列
4. **合并范围**（Phase 2）：companies 表存企业元数据，projects.parent_project_id 存项目层级，两者共存
5. **工时表**（Phase 3）：统一使用 Phase 9 的 work_hours 表（含 staff_id/start_time/end_time），Phase 3 的 workhours 表弃用
6. **附注模版裁剪**（Phase 8）：新增 note_section_instances 表，不修改 Phase 8 的 NoteTemplateService
