# 需求文档：生产就绪改进（production-readiness）

## 简介

本文档描述审计作业平台在生产部署前需要解决的所有问题，涵盖数据正确性风险（P0）、核心流程断点（P1）、体验优化（P2）和生产部署前提（P3）四个优先级。平台面向会计师事务所，目标并发规模 6000 人，技术栈为 FastAPI + SQLAlchemy（异步）+ PostgreSQL + Redis（后端）、Vue 3 + TypeScript + Element Plus + Univer（前端）。

---

## 词汇表

- **底稿（WorkingPaper）**：审计工作底稿，由审计员在 Univer 在线表格中编辑的核心审计文件
- **附注（Disclosure）**：财务报表附注，其数据来源于底稿审定数，需与底稿保持同步
- **审定数（AuditedAmount）**：审计员在底稿中最终确认的金额数据
- **Dashboard**：审计项目总览仪表盘，展示统计数据和趋势图
- **sparkData**：Dashboard 趋势图中的迷你折线图数据
- **Dirty 标记（DirtyFlag）**：底稿编辑器中标识"有未保存变更"的状态位
- **Univer**：前端集成的在线表格组件，通过 `onCommandExecuted` 钩子监听编辑事件
- **复核收件箱（ReviewInbox）**：复核人员查看待复核底稿的入口页面
- **UUID**：系统内部用户唯一标识符
- **借贷平衡指示器（BalanceIndicator）**：显示试算平衡表借贷是否平衡的 UI 组件
- **损益类科目**：包括收入、成本、费用类会计科目，期中审计时参与借贷平衡计算
- **Lifespan**：FastAPI 应用生命周期管理函数，负责启动和关闭时的资源编排
- **Worker**：后台定时任务模块，独立于主应用运行
- **router_registry**：后端路由注册中心，统一管理所有路由前缀
- **load_test**：负载测试脚本，用于验证并发性能目标
- **Alembic**：Python 数据库迁移工具，管理 SQLAlchemy 模型的 schema 变更

---

## 需求

---

### 需求 1：底稿保存事件触发附注自动刷新

**用户故事：** 作为审计员，我希望在保存底稿后附注数据能自动更新，以确保财务报表附注中的审定数与底稿保持一致，避免手动同步遗漏导致的数据错误。

#### 验收标准

1. WHEN 底稿编辑器触发保存事件，THE 系统（System）SHALL 向附注模块发送数据刷新通知
2. WHEN 附注模块收到刷新通知，THE 附注模块（DisclosureModule）SHALL 在 3 秒内重新从底稿审定数接口拉取最新数据并更新页面展示
3. WHEN 底稿审定数发生变更且附注刷新完成，THE 附注模块（DisclosureModule）SHALL 展示与底稿审定数完全一致的金额
4. IF 附注刷新请求失败，THEN THE 系统（System）SHALL 在附注页面显示同步失败提示，并提供手动重试按钮
5. WHEN 同一底稿在 1 秒内连续触发多次保存事件，THE 系统（System）SHALL 合并为一次附注刷新请求（防抖处理）

---

### 需求 2：Dashboard 趋势图接入真实 API 数据

**用户故事：** 作为合伙人，我希望 Dashboard 上的统计趋势图展示真实的项目数据，以便准确判断审计进度和团队工作量，而不是被硬编码的模拟数据误导决策。

#### 验收标准

1. THE 仪表盘（Dashboard）SHALL 从后端 API 获取趋势图所需的时序统计数据，不得使用任何硬编码的 sparkData
2. WHEN 用户打开 Dashboard 页面，THE 仪表盘（Dashboard）SHALL 在 2 秒内完成趋势图数据加载并渲染
3. WHEN 后端返回趋势图数据，THE 仪表盘（Dashboard）SHALL 按时间维度（日/周/月）展示底稿完成数量、复核通过数量等真实统计指标
4. IF 趋势图数据接口请求失败，THEN THE 仪表盘（Dashboard）SHALL 显示数据加载失败提示，并隐藏趋势图区域，不得展示任何模拟数据
5. WHEN 用户切换项目或刷新页面，THE 仪表盘（Dashboard）SHALL 重新请求并展示对应项目的最新趋势数据

---

### 需求 3：底稿编辑器 Dirty 标记完整覆盖

**用户故事：** 作为审计员，我希望在底稿中进行任何编辑操作（包括公式输入和格式变更）后，系统都能提示我有未保存的变更，以防止意外关闭页面导致数据丢失。

#### 验收标准

1. WHEN 用户在底稿编辑器中输入或修改公式，THE 底稿编辑器（WorkingPaperEditor）SHALL 立即将 DirtyFlag 置为 true
2. WHEN 用户在底稿编辑器中变更单元格格式（字体、颜色、边框、数字格式等），THE 底稿编辑器（WorkingPaperEditor）SHALL 立即将 DirtyFlag 置为 true
3. WHILE DirtyFlag 为 true，THE 底稿编辑器（WorkingPaperEditor）SHALL 在页面标题或工具栏显示"有未保存的变更"提示
4. WHEN 用户尝试离开底稿编辑页面且 DirtyFlag 为 true，THE 底稿编辑器（WorkingPaperEditor）SHALL 弹出确认对话框，提示用户保存或放弃变更
5. WHEN 底稿成功保存，THE 底稿编辑器（WorkingPaperEditor）SHALL 将 DirtyFlag 重置为 false 并清除未保存提示
6. THE 底稿编辑器（WorkingPaperEditor）SHALL 通过 Univer 的 onCommandExecuted 钩子监听所有命令执行事件，覆盖公式输入、格式变更、内容删除等全部操作类型

---

### 需求 4：复核收件箱导航入口可达性

**用户故事：** 作为复核人员，我希望能通过导航菜单直接进入复核收件箱，以便及时处理待复核的底稿，确保复核流程不中断。

#### 验收标准

1. THE 导航菜单（NavigationMenu）SHALL 在复核人员（reviewer）及以上权限角色的菜单中包含"复核收件箱"入口
2. WHEN 复核人员点击导航菜单中的"复核收件箱"入口，THE 系统（System）SHALL 跳转至 ReviewInbox 页面
3. WHEN 复核人员登录系统，THE 导航菜单（NavigationMenu）SHALL 在"复核收件箱"入口旁显示待复核底稿数量的角标（badge）
4. IF 用户角色无复核权限，THEN THE 导航菜单（NavigationMenu）SHALL 不显示"复核收件箱"入口
5. WHEN 复核人员处理完所有待复核底稿，THE 导航菜单（NavigationMenu）SHALL 将"复核收件箱"角标数量更新为 0

---

### 需求 5：底稿列表负责人姓名显示

**用户故事：** 作为项目经理，我希望底稿列表中的负责人列显示真实姓名而非 UUID，以便快速识别每份底稿的责任人，提高工作分配的可读性。

#### 验收标准

1. THE 底稿列表（WorkingPaperList）SHALL 在负责人列显示用户的真实姓名，不得显示 UUID 字符串
2. WHEN 底稿列表加载，THE 底稿列表（WorkingPaperList）SHALL 将 assigned_to 字段的 UUID 映射为对应用户的显示名称
3. IF 某个 UUID 在用户列表中不存在，THEN THE 底稿列表（WorkingPaperList）SHALL 显示"未知用户"占位文本，不得显示原始 UUID
4. WHEN 用户信息发生变更（如姓名修改），THE 底稿列表（WorkingPaperList）SHALL 在下次加载时展示最新姓名

---

### 需求 6：底稿列表整体进度百分比

**用户故事：** 作为项目经理，我希望在底稿列表页面能看到整体完成进度百分比，以便在管理 80+ 份底稿时快速判断项目整体完成情况，无需逐条统计。

#### 验收标准

1. THE 底稿列表（WorkingPaperList）SHALL 在页面顶部显示整体进度指示器，包含已完成底稿数量、总底稿数量和完成百分比
2. WHEN 底稿列表数据加载完成，THE 底稿列表（WorkingPaperList）SHALL 实时计算并展示进度百分比（完成数 / 总数 × 100%，保留整数）
3. WHEN 某份底稿状态变更为"已完成"，THE 底稿列表（WorkingPaperList）SHALL 在当前页面自动更新整体进度百分比，无需手动刷新
4. WHERE 底稿列表支持按状态筛选，THE 底稿列表（WorkingPaperList）SHALL 同时提供基于全量底稿的总体进度和基于当前筛选结果的局部进度

---

### 需求 7：项目启动流程步骤引导

**用户故事：** 作为审计员，我希望在启动新审计项目时能看到清晰的步骤进度提示（导入→映射→重算），以便了解当前处于哪个阶段、还需要完成哪些步骤，避免因流程不清晰导致操作遗漏。

#### 验收标准

1. THE 项目启动流程（ProjectSetupFlow）SHALL 以步骤条（stepper）形式展示"数据导入 → 科目映射 → 重新计算"三个阶段
2. WHEN 用户完成数据导入步骤，THE 项目启动流程（ProjectSetupFlow）SHALL 将步骤条中"数据导入"标记为已完成，并自动激活"科目映射"步骤
3. WHEN 用户完成科目映射步骤，THE 项目启动流程（ProjectSetupFlow）SHALL 将步骤条中"科目映射"标记为已完成，并自动激活"重新计算"步骤
4. WHILE 某步骤正在处理中，THE 项目启动流程（ProjectSetupFlow）SHALL 在该步骤显示加载动画，并禁用跳过或提前进入下一步的操作
5. IF 某步骤执行失败，THEN THE 项目启动流程（ProjectSetupFlow）SHALL 在步骤条中将该步骤标记为失败状态，并显示具体错误信息和重试按钮
6. WHEN 所有三个步骤均完成，THE 项目启动流程（ProjectSetupFlow）SHALL 显示"项目启动完成"确认信息，并提供跳转至底稿列表的入口

---

### 需求 8：借贷平衡指示器损益类科目修正

**用户故事：** 作为审计员，我希望借贷平衡指示器能正确计算包含损益类科目（收入、成本、费用）的借贷平衡，避免系统误报"不平衡"影响审计判断。

#### 验收标准

1. THE 借贷平衡指示器（BalanceIndicator）SHALL 在计算借贷平衡时始终将收入类、成本类、费用类科目纳入计算范围，不区分期中/期末模式
2. WHEN 试算平衡表中仅存在损益类科目的借贷差异，THE 借贷平衡指示器（BalanceIndicator）SHALL 正确反映实际平衡状态，不得误报为不平衡
3. WHEN 资产负债表科目与损益类科目合并计算后借贷相等（即 资产 = 负债 + 权益 + 损益净额），THE 借贷平衡指示器（BalanceIndicator）SHALL 显示"平衡"状态
4. WHEN 借贷实际不平衡（差额不为零），THE 借贷平衡指示器（BalanceIndicator）SHALL 显示"不平衡"状态及具体差额金额
5. THE 借贷平衡指示器（BalanceIndicator）的 Tooltip 文案 SHALL 显示"资产 = 负债 + 权益 + 损益净额"，反映完整的会计恒等式

---

### 需求 9：数据库迁移至 PostgreSQL

**用户故事：** 作为系统管理员，我希望将数据库从 SQLite 迁移到 PostgreSQL，以支持 6000 人并发访问，确保生产环境下的数据库性能和稳定性。

#### 验收标准

1. THE 系统（System）SHALL 使用 PostgreSQL 作为生产环境数据库，不得在生产环境使用 SQLite
2. WHEN 执行数据库迁移，THE 迁移工具（MigrationTool）SHALL 通过 Alembic 完整迁移全部 144 张表的 schema，不得遗漏任何表或索引
3. WHEN 迁移完成后运行完整测试套件，THE 系统（System）SHALL 通过所有现有测试，不得出现因数据库差异导致的新增失败
4. IF Alembic 迁移脚本执行失败，THEN THE 迁移工具（MigrationTool）SHALL 回滚至迁移前状态，并输出详细错误日志
5. THE 系统（System）SHALL 通过环境变量 `DATABASE_URL` 切换数据库连接，开发环境可保留 SQLite，生产环境强制使用 PostgreSQL

---

### 需求 10：后台定时任务模块化拆分

**用户故事：** 作为后端开发者，我希望将 main.py 中内联的三个定时任务提取为独立的 Worker 模块，以提高代码可维护性，并使 lifespan 函数职责单一、易于理解。

#### 验收标准

1. THE 系统（System）SHALL 将 `_sla_check_loop`、`_import_recover_loop`、`_outbox_replay_loop` 三个定时任务分别提取为 `app/workers/` 目录下的独立模块
2. THE lifespan 函数（LifespanFunction）SHALL 仅负责启动和关闭各 Worker 模块的编排，代码行数不超过 30 行
3. WHEN 应用启动，THE lifespan 函数（LifespanFunction）SHALL 依次启动所有 Worker 模块，确保定时任务正常运行
4. WHEN 应用关闭，THE lifespan 函数（LifespanFunction）SHALL 优雅地停止所有 Worker 模块，等待当前执行周期完成后再退出
5. IF 某个 Worker 模块在运行中抛出未捕获异常，THEN THE Worker 模块（WorkerModule）SHALL 记录错误日志并在下一个调度周期自动重试，不得导致整个应用崩溃

---

### 需求 11：路由前缀规范统一

**用户故事：** 作为后端开发者，我希望所有路由的前缀遵循统一规范，以消除历史遗留的 hasattr 补丁，降低新路由接入的认知成本。

#### 验收标准

1. THE 路由注册中心（RouterRegistry）SHALL 采用统一规范：Phase 14（gate/trace/sod）路由器内部不携带 `/api` 前缀，由 router_registry 在注册时统一添加 `prefix="/api"`
2. THE 路由注册中心（RouterRegistry）SHALL 删除 Phase 14 引入的 `hasattr` 补丁代码，改为直接 `app.include_router(r, prefix="/api", ...)`，不得保留任何兼容性 hack
3. WHEN 注册 Phase 14 路由器，THE 路由注册中心（RouterRegistry）SHALL 直接使用 `prefix="/api"` 注册，无需运行时判断路由器是否已含 `/api` 前缀
4. WHEN 系统启动并完成路由注册，THE 系统（System）SHALL 能正确响应所有现有 API 端点，不得出现 404 错误
5. THE 路由注册中心（RouterRegistry）SHALL 提供路由前缀规范的注释说明，便于后续开发者遵循（注：`dashboard.py` 内部保留 `prefix="/api/dashboard"` 且注册时不加额外前缀，属于已知例外，无需修改）

---

### 需求 12：6000 人并发压测验证

**用户故事：** 作为系统管理员，我希望通过负载测试验证系统能支撑 6000 人并发访问，以确认生产部署前系统满足性能目标，避免上线后出现性能瓶颈。

#### 验收标准

1. THE 负载测试（LoadTest）SHALL 使用 load_test.py 模拟 6000 个并发用户同时访问核心业务接口（登录、底稿列表、底稿读取、附注查询）
2. WHEN 6000 并发用户同时请求，THE 系统（System）SHALL 保持 API 平均响应时间不超过 2000ms，P99 响应时间不超过 5000ms
3. WHEN 6000 并发用户同时请求，THE 系统（System）SHALL 保持错误率低于 1%（HTTP 5xx 响应比例）
4. WHEN 负载测试运行完成，THE 负载测试（LoadTest）SHALL 输出包含 TPS、平均响应时间、P95/P99 响应时间、错误率的完整测试报告
5. IF 压测结果未达到性能目标，THEN THE 负载测试（LoadTest）SHALL 在报告中标注具体瓶颈接口，并提供慢查询日志供优化参考

---

### 需求 13：底稿编辑器公式计算引擎集成

**用户故事：** 作为审计员，我希望在 Univer 底稿编辑器中输入公式（如 `=SUM(A1:A10)`）后能自动计算结果，而不是显示公式字符串，以确保审定表合计行数据正确。

#### 验收标准

1. THE 底稿编辑器（WorkingPaperEditor）SHALL 集成 `UniverSheetsFormulaPreset`，支持 Excel 兼容公式计算
2. WHEN 用户在底稿编辑器中输入公式，THE 底稿编辑器（WorkingPaperEditor）SHALL 立即显示计算结果，不得显示公式字符串
3. WHEN 公式引用的单元格数值发生变更，THE 底稿编辑器（WorkingPaperEditor）SHALL 自动重新计算并更新公式单元格的显示值
4. WHEN 从 xlsx 模板加载含公式的底稿，THE 底稿编辑器（WorkingPaperEditor）SHALL 正确显示公式的计算结果，不得显示空白

---

### 需求 14：底稿编辑器错误信息修正

**用户故事：** 作为审计员，我希望底稿编辑器的错误提示准确描述实际问题，避免"同步失败"掩盖"保存失败"的真实原因，以便快速定位和处理问题。

#### 验收标准

1. WHEN 同步公式操作中的保存步骤失败，THE 底稿编辑器（WorkingPaperEditor）SHALL 只显示"保存失败"提示，不得额外显示"同步失败"提示
2. THE `onSave` 函数（SaveFunction）SHALL 返回 boolean 值表示操作成功（true）或失败（false），供 `onSyncStructure` 判断是否继续执行后续步骤

---

### 需求 15：底稿 xlsx 模板公式值预加载

**用户故事：** 作为审计员，我希望从模板生成的底稿在 Univer 中打开时，公式单元格能显示上次计算的值（而非空白），以便快速了解数据概况，无需等待重算。

#### 验收标准

1. THE xlsx 转换服务（XlsxToUniverService）SHALL 对公式单元格同时保留公式字符串（`f` 字段）和上次计算值（`v` 字段）
2. WHEN Univer 加载含公式的底稿，THE 底稿编辑器（WorkingPaperEditor）SHALL 显示公式单元格的上次计算值，并在用户编辑相关单元格后自动重算

---

### 需求 16：底稿导出 PDF

**用户故事：** 作为审计员，我希望能将底稿直接导出为 PDF，以便打印归档或发送给客户，无需借助外部工具进行格式转换。

#### 验收标准

1. THE 底稿编辑器（WorkingPaperEditor）工具栏 SHALL 提供"导出 PDF"按钮
2. WHEN 用户点击"导出 PDF"按钮，THE 系统（System）SHALL 将当前底稿内容转换为 PDF 并触发浏览器下载
3. THE 导出的 PDF SHALL 保留底稿的表格结构、样式和数据，不得出现内容丢失或格式错乱

---

### 需求 17：报表权益变动表和资产减值准备表数据填充

**用户故事：** 作为审计员，我希望权益变动表和资产减值准备表能从试算表数据自动填充，而不是显示占位符"-"。

#### 验收标准

1. WHEN 用户点击"刷新数据"，THE 报表视图（ReportView）SHALL 从后端获取权益变动表数据并填充各列金额，不得显示硬编码的"-"
2. WHEN 用户点击"刷新数据"，THE 报表视图（ReportView）SHALL 从后端获取资产减值准备表数据并填充各列金额
3. IF 后端无对应数据，THEN THE 报表视图（ReportView）SHALL 显示"0"或空白，不得显示"-"占位符

---

### 需求 18：ReviewInbox 查看按钮跳转修正

**用户故事：** 作为复核人员，我希望在复核收件箱点击"查看"后直接进入底稿编辑器，而不是跳到底稿列表页再找一遍。

#### 验收标准

1. WHEN 复核人员在复核收件箱点击"查看"按钮，THE 系统（System）SHALL 直接跳转至对应底稿的编辑器页面（WorkpaperEditor）
2. THE 跳转路径 SHALL 为 `/projects/{project_id}/workpapers/{wp_id}/edit`，不得跳转到底稿列表页

---

### 需求 19：AuditCheckDashboard N+1 请求优化

**用户故事：** 作为审计员，我希望审计检查仪表盘能在 5 秒内加载完成，而不是等待几十秒。

#### 验收标准

1. WHEN 用户打开审计检查仪表盘，THE 仪表盘（AuditCheckDashboard）SHALL 在 5 秒内完成数据加载
2. THE 仪表盘（AuditCheckDashboard）SHALL 使用批量接口一次获取所有底稿的检查结果，不得对每份底稿单独发请求

---

### 需求 20：错报超限联动 QC 门禁

**用户故事：** 作为合伙人，我希望当未更正错报超过重要性水平时，系统能阻止底稿提交复核，并在审计报告编辑器中显示警告。

#### 验收标准

1. WHEN 未更正错报累计金额超过整体重要性水平，THE 底稿提交复核门禁（GateEngine）SHALL 阻断提交，并显示"未更正错报超过重要性水平"的阻断原因
2. WHEN 未更正错报累计金额超过整体重要性水平，THE 审计报告编辑器（AuditReportEditor）SHALL 在页面顶部显示警告横幅

---

### 需求 21：重要性变更后试算表标记自动更新

**用户故事：** 作为审计员，我希望修改重要性水平后，试算表中超重要性科目的高亮标记能自动更新，无需手动触发重算。

#### 验收标准

1. WHEN 重要性水平（整体重要性或执行重要性）发生变更，THE 系统（System）SHALL 自动触发试算表 `exceeds_materiality` 字段的重新计算
2. WHEN 重算完成，THE 试算表（TrialBalance）SHALL 自动刷新页面数据，高亮显示超过新重要性水平的科目

---

### 需求 22：账套导入完成通知

**用户故事：** 作为审计员，我希望账套数据导入完成后能收到明确的通知，而不是反复刷新页面确认。

#### 验收标准

1. WHEN 后台账套导入任务完成，THE 系统（System）SHALL 在页面上显示"导入完成"的通知（`ElNotification` 或状态更新）
2. WHEN 导入完成通知出现，THE 系统（System）SHALL 自动刷新账套数据列表

---

### 需求 23：底稿工作台 AI 分析本地缓存

**用户故事：** 作为审计员，我希望在底稿工作台切换底稿时，已加载过的 AI 分析结果能立即显示，无需重新等待。

#### 验收标准

1. WHEN 用户切换到已加载过 AI 分析的底稿，THE 底稿工作台（WorkpaperWorkbench）SHALL 立即显示缓存的分析结果，不得重新发起请求
2. THE 缓存 SHALL 在当前页面会话内有效，页面刷新后重新加载

---

### 需求 24：报表对比视图新增上年审定数列

**用户故事：** 作为审计员，我希望报表对比视图能显示上年审定数，以便直接在报表层面做同比分析。

#### 验收标准

1. THE 报表对比视图（ReportView compare mode）SHALL 包含"上年审定数"列
2. WHEN 用户切换到对比视图，THE 报表视图（ReportView）SHALL 同时展示本年未审数、本年调整、本年审定数、上年审定数四列

---

### 需求 25：序时账异常凭证视觉标记

**用户故事：** 作为审计员，我希望序时账中的异常凭证（金额超重要性、期末最后几天、红字冲销）能有视觉标记，以便快速定位需要关注的凭证。

#### 验收标准

1. WHEN 凭证金额（借方或贷方）超过项目重要性水平，THE 序时账（LedgerPenetration）SHALL 对该行显示橙色背景或警告图标
2. WHEN 凭证日期在审计期末最后 5 个工作日内，THE 序时账（LedgerPenetration）SHALL 对该行显示"截止"标记
3. WHEN 凭证借方或贷方金额为负数（红字冲销），THE 序时账（LedgerPenetration）SHALL 对该行显示红色文字

---

### 需求 26：QC 项目汇总 N+1 查询优化

**用户故事：** 作为项目经理，我希望 QC 汇总看板能在 3 秒内加载完成，而不是等待几十秒。

#### 验收标准

1. THE `get_project_summary` 方法（QCEngine）SHALL 使用单次 SQL 查询获取所有底稿的最新 QC 结果，不得对每份底稿单独发起查询
2. WHEN 项目有 80 份底稿时，THE QC 汇总接口（QCSummaryAPI）SHALL 在 2 秒内返回结果

---

### 需求 27：审计报告定稿后端状态保护

**用户故事：** 作为合伙人，我希望审计报告定稿后任何人都无法再修改内容，以确保最终签发的报告与归档版本一致。

#### 验收标准

1. WHEN 审计报告状态为 `final`，THE 后端（AuditReportAPI）SHALL 拒绝 `updateAuditReportParagraph` 请求，返回 HTTP 403 并提示"报告已定稿，不允许修改"
2. WHEN 审计报告状态为 `final`，THE 后端（AuditReportAPI）SHALL 同样拒绝 `updateAuditReportStatus` 将状态从 `final` 改回 `review` 的请求

---

### 需求 28：QC-16 数据一致性规则字段修正

**用户故事：** 作为审计员，我希望 QC 自检能正确检测底稿审定数与试算表的差异，而不是静默跳过。

#### 验收标准

1. THE QC-16 规则（DataReferenceConsistencyRule）SHALL 使用 `TrialBalance.audited_amount` 字段与底稿 `parsed_data.audited_amount` 进行比较
2. WHEN 底稿审定数与试算表对应科目审定数差异超过 0.01 元，THE QC-16 规则 SHALL 产生阻断级发现

---

### 需求 29：底稿汇总年度从项目上下文获取

**用户故事：** 作为审计员，我希望底稿汇总自动使用当前项目的审计年度，而不是系统当前年份。

#### 验收标准

1. THE 底稿汇总（WorkpaperSummary）SHALL 使用 `projectStore.year` 或路由参数中的年度，不得使用 `new Date().getFullYear()` 硬编码

---

### 需求 30：审计报告导出 Word 入口

**用户故事：** 作为审计员，我希望能直接从审计报告编辑器导出 Word 文档，无需借助外部工具。

#### 验收标准

1. THE 审计报告编辑器（AuditReportEditor）工具栏 SHALL 提供"导出 Word"按钮
2. WHEN 用户点击"导出 Word"，THE 系统（System）SHALL 调用后端 Word 导出接口并触发浏览器下载

---

### 需求 31：QC-17 附件充分性规则改用 ORM 查询

**用户故事：** 作为开发者，我希望 QC 规则使用 ORM 查询而非裸 SQL，以确保数据库 schema 变更时能被迁移工具感知。

#### 验收标准

1. THE QC-17 规则（AttachmentSufficiencyRule）SHALL 使用 SQLAlchemy ORM 模型查询附件关联关系，不得使用 `sa.text` 裸 SQL
2. IF 查询失败，THEN THE QC-17 规则 SHALL 记录 warning 日志并返回空发现列表，不得静默吞掉异常

---

### 需求 32：调整分录批量驳回支持逐条原因

**用户故事：** 作为复核人员，我希望批量驳回调整分录时能为每条分录填写独立的驳回原因，以满足审计工作底稿的规范要求。

#### 验收标准

1. WHEN 复核人员批量驳回多条调整分录，THE 系统（System）SHALL 允许为每条分录填写独立的驳回原因
2. IF 复核人员选择统一原因模式，THEN THE 系统（System）SHALL 允许用同一原因批量驳回所有选中分录

---

### 需求 33：PBC 清单和函证管理后端路由注册

**用户故事：** 作为审计员，我希望能在协作管理页面查看和管理 PBC 清单及函证状态，以便跟踪客户资料提供情况和函证回函进度。

#### 验收标准

1. WHEN 用户打开协作管理页面的"PBC 清单"Tab，THE 系统（System）SHALL 从后端加载并展示当前项目的 PBC 清单条目
2. WHEN 用户打开"函证管理"Tab，THE 系统（System）SHALL 从后端加载并展示函证列表及其状态
3. THE 后端路由（BackendRouter）SHALL 在 `router_registry.py` 中正确注册 PBC 清单和函证管理相关路由

---

### 需求 34：进度看板卡片直接跳转底稿编辑器

**用户故事：** 作为审计员，我希望在进度看板点击底稿卡片后直接进入该底稿的编辑器，而不是跳到列表页再找一遍。

#### 验收标准

1. WHEN 用户在进度看板点击底稿卡片，THE 系统（System）SHALL 直接跳转至对应底稿的编辑器页面（WorkpaperEditor）
2. IF 底稿 `id` 字段存在，THEN THE 系统（System）SHALL 使用该 id 构建跳转路径 `/projects/{project_id}/workpapers/{wp_id}/edit`

---

### 需求 35：个人工作台待办和工时数据加载

**用户故事：** 作为审计员，我希望个人工作台能显示我的待办事项和本周工时，以便快速了解当前工作状态。

#### 验收标准

1. WHEN 用户打开个人工作台，THE 系统（System）SHALL 加载并展示当前用户的待办事项列表
2. WHEN 用户打开个人工作台，THE 系统（System）SHALL 加载并展示本周工时记录

---

### 需求 36：抽样增强年度从项目上下文获取

**用户故事：** 作为审计员，我希望抽样增强工具自动使用当前项目的审计年度，而不是硬编码的年份。

#### 验收标准

1. THE 抽样增强（SamplingEnhanced）SHALL 使用 `projectStore.year` 作为默认年度，不得硬编码为固定年份

---

### 需求 37：审计程序裁剪"参照其他单位"改为下拉选择

**用户故事：** 作为审计员，我希望参照其他项目的审计程序方案时，能从下拉列表中选择项目，而不是手动输入 UUID。

#### 验收标准

1. THE 参照弹窗（RefDialog）SHALL 提供项目下拉选择框，从 `listProjects()` 加载项目列表
2. THE 参照弹窗 SHALL 不得要求用户手动输入项目 UUID

---

### 需求 38：工时编辑功能修正

**用户故事：** 作为审计员，我希望编辑工时记录时能正确更新原记录，而不是创建新记录。

#### 验收标准

1. WHEN 用户点击工时记录的"编辑"按钮并保存，THE 系统（System）SHALL 调用更新接口修改原记录，不得创建新记录
2. THE 填报弹窗 SHALL 在编辑模式下显示"更新"按钮，在新建模式下显示"保存"按钮

---

### 需求 39：知识库文档预览携带认证头

**用户故事：** 作为审计员，我希望知识库中的图片和 PDF 文档能正常预览，不因认证问题导致预览失败。

#### 验收标准

1. WHEN 用户预览图片或 PDF 文档，THE 系统（System）SHALL 使用携带认证信息的请求获取文件内容，不得使用裸 URL 直接赋值给 src 属性

---

### 需求 40：QC 归档检查结果缓存

**用户故事：** 作为质控人员，我希望归档检查结果能被缓存，避免每次查看都重新执行耗时的检查。

#### 验收标准

1. WHEN 用户切换到"归档检查"Tab，THE 系统（System）SHALL 先尝试加载上次的检查结果，不得自动重新执行检查
2. THE 归档检查面板 SHALL 显示上次检查的执行时间，并提供"重新检查"按钮供用户手动触发

---

### 需求 41：底稿列表编制人筛选下拉框填充

**用户故事：** 作为项目经理，我希望底稿列表的"编制人"筛选下拉框能列出所有项目成员，以便按人员筛选底稿，而不是只有一个"全部"选项的空摆设。

#### 验收标准

1. WHEN 底稿列表页面加载，THE 系统（System）SHALL 调用 `listUsers()` 加载用户列表，并将结果填充到"编制人"筛选下拉框
2. THE 编制人筛选下拉框 SHALL 显示每个用户的真实姓名（`full_name || username`），`value` 使用用户 UUID
3. WHEN 用户选择某个编制人，THE 底稿列表（WorkpaperList）SHALL 只显示 `assigned_to` 等于该 UUID 的底稿

---

### 需求 42：底稿编辑器状态栏姓名显示

**用户故事：** 作为审计员，我希望底稿编辑器底部状态栏显示编制人和复核人的真实姓名，而不是 UUID 字符串。

#### 验收标准

1. THE 底稿编辑器（WorkpaperEditor）状态栏 SHALL 显示编制人的真实姓名，不得显示 UUID
2. THE 底稿编辑器（WorkpaperEditor）状态栏 SHALL 显示复核人的真实姓名，不得显示 UUID
3. IF 编制人或复核人 UUID 无法映射到姓名，THEN THE 状态栏 SHALL 显示"未分配"

---

### 需求 43：底稿编辑器版本历史入口

**用户故事：** 作为审计员，我希望在底稿编辑器中能查看历史版本列表，以便在误操作后找回之前的版本。

#### 验收标准

1. THE 底稿编辑器（WorkpaperEditor）工具栏 SHALL 提供"版本历史"按钮
2. WHEN 用户点击"版本历史"，THE 系统（System）SHALL 调用 `GET /api/workpapers/{wp_id}/versions` 并展示版本列表（版本号、保存时间）
3. THE 版本历史面板 SHALL 以侧边抽屉或弹窗形式展示，不遮挡编辑区域

---

### 需求 44：底稿编辑器自动保存

**用户故事：** 作为审计员，我希望底稿编辑器能每隔一段时间自动保存，避免因忘记手动保存导致数据丢失。

#### 验收标准

1. THE 底稿编辑器（WorkpaperEditor）SHALL 在 `dirty.value` 为 true 且用户停止编辑 30 秒后自动触发保存
2. WHEN 自动保存成功，THE 底稿编辑器（WorkpaperEditor）SHALL 在状态栏显示"已自动保存"提示（3 秒后消失）
3. IF 自动保存失败，THEN THE 底稿编辑器（WorkpaperEditor）SHALL 静默忽略（不弹出错误提示，保留 dirty 标记，等待下次触发）
4. THE 自动保存 SHALL 复用项目已有的 `useAutoSave` composable 实现，不重复造轮子

---

### 需求 45：底稿并发编辑版本冲突检测

**用户故事：** 作为审计员，我希望当两人同时编辑同一份底稿时，后保存的人能收到冲突提示，而不是静默覆盖前一人的工作。

#### 验收标准

1. WHEN 用户保存底稿，THE 系统（System）SHALL 在请求中携带 `expected_version` 参数（当前已知的版本号）
2. IF 服务器当前版本与 `expected_version` 不一致，THEN THE 后端（WorkpaperAPI）SHALL 返回 HTTP 409，提示"底稿已被他人修改，请刷新后重试"
3. WHEN 收到 409 响应，THE 底稿编辑器（WorkpaperEditor）SHALL 显示冲突提示，并提供"刷新并放弃本地修改"和"强制覆盖"两个选项

---

### 需求 46：预填充引擎保留公式字段

**用户故事：** 作为审计员，我希望预填充操作只填入计算值，不破坏底稿中的 `=TB()`/`=WP()` 等自定义公式，以确保五环联动（底稿→试算表→报表→附注→汇总）正常工作。

#### 验收标准

1. WHEN 预填充引擎处理含 `=TB()`/`=WP()`/`=AUX()` 公式的单元格，THE 预填充引擎（PrefillEngine）SHALL 只更新 Univer 数据中的 `v`（值）字段，不得覆盖 `f`（公式）字段
2. WHEN 预填充完成后用户在 Univer 中打开底稿，THE 底稿编辑器（WorkpaperEditor）SHALL 显示预填充的计算值，且公式仍可被 Univer 公式引擎重新计算
3. THE 预填充引擎（PrefillEngine）SHALL 不再将公式文本移入 openpyxl comment，comment 字段保持原状
