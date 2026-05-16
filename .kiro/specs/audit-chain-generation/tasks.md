# Implementation Plan: 审计全链路一键生成与导出

## Overview

基于现有代码基础（report_engine.py 41KB / disclosure_engine.py 35KB / formula_engine.py 17KB / event_handlers.py 26KB），通过"补齐缺口+增强格式"策略实现审计全链路闭环。按 10 个 Sprint 递进实施，每 Sprint ≤10 个编码任务。

实施语言：后端 Python（FastAPI + SQLAlchemy）/ 前端 TypeScript + Vue 3（Element Plus）

## Tasks

---

### Sprint 1: 报表公式覆盖率提升 + report_config 数据填充 + ReportEngine 未审模式

- [x] 1. 报表公式覆盖率提升与 ReportEngine 未审/审定双模式
  - [x] 1.1 补齐 report_config 公式覆盖率（BS 80%+ / IS 70%+）
    - 扩展 `backend/app/services/report_formula_service.py` 的 `fill_formulas` 方法
    - 为 BS 所有核心科目行补齐 TB() 公式（货币资金/应收/存货/固定资产/无形资产等）
    - 为 IS 所有核心行补齐公式（营业收入/营业成本/管理费用/财务费用等）
    - 为合计行自动生成 SUM_ROW() 公式（汇总其下所有子行）
    - 对无公式行自动生成 fallback：按 row_code 前缀匹配 TB 科目编码
    - _Requirements: 13.1, 13.2, 20.1, 20.2_

  - [x] 1.2 实现 CFS 间接法公式计算
    - 在 `report_formula_service.py` 新增 CFS 间接法公式集
    - 净利润 + 折旧摊销 + 资产减值 + 处置损益 + 财务费用 + 存货变动 + 经营性应收变动 + 经营性应付变动
    - 从 TB 差额（期末-期初）推算变动项
    - _Requirements: 13.3, 18.6, 20.3_

  - [x] 1.3 实现 EQ 权益变动表公式
    - 期初余额 = 上年期末余额（PREV 函数）
    - 本年增减 = 本年利润 + 其他综合收益
    - 期末余额 = 期初 + 增减
    - 从 TB 的 3xxx/4xxx 科目取数
    - _Requirements: 13.4, 18.7, 20.4_

  - [x] 1.4 ReportEngine 未审/审定双模式实现
    - 修改 `backend/app/services/report_engine.py` 的 `generate_all_reports` 方法
    - 新增 `mode` 参数（unadjusted/audited），默认 audited
    - unadjusted 模式使用 `trial_balance.unadjusted_amount`
    - audited 模式使用 `trial_balance.audited_amount`
    - _Requirements: 18.1, 18.2, 18.3_

  - [x] 1.5 公式 fallback 取数机制
    - 当公式计算结果为 0 但 TB 中该科目有余额时，使用 TB 余额作为 fallback
    - 在 `_eval_formula` 返回结果中标记 `fallback_applied=True`
    - 在 summary 中标记为 warning
    - _Requirements: 18.8, 20.1_

  - [x] 1.6 报表生成覆盖率统计
    - `generate_all_reports` 返回值新增 `coverage_stats` 字段
    - 统计：有数据行数 / 总行数 / 覆盖率百分比（按报表类型分别统计）
    - _Requirements: 13.6, 18.9_

  - [x] 1.7 公式调试模式
    - 新增 `debug=True` 参数，返回每行的公式文本 + 代入值 + 计算过程
    - 公式执行失败时记录 warning 而非抛异常（容错处理）
    - _Requirements: 20.5, 20.6_

  - [ ]* 1.8 Write property tests for report mode correctness
    - **Property 4: 报表模式取数正确性**
    - **Property 11: 公式 fallback 取数**
    - **Validates: Requirements 18.1, 18.2, 18.3, 18.8**

  - [x] 1.9 Checkpoint - 确保报表公式覆盖率达标
    - 运行 pytest 验证所有公式计算正确
    - 验证 BS 覆盖率 ≥80%、IS 覆盖率 ≥70%
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 2: ChainOrchestrator + SSE 进度 + 前端一键按钮

- [x] 2. 全链路编排服务与 SSE 进度推送
  - [x] 2.1 创建 chain_executions 数据库表（Alembic 迁移）
    - 新建 `backend/alembic/versions/audit_chain_executions_20260515.py`
    - 创建 `chain_executions` 表（id/project_id/year/status/steps JSONB/trigger_type/triggered_by/started_at/completed_at/total_duration_ms/snapshot_before JSONB）
    - _Requirements: 1.10, 9.1, 9.2_

  - [x] 2.2 实现 ChainOrchestrator 核心编排逻辑
    - 新建 `backend/app/services/chain_orchestrator.py`
    - 实现 `execute_full_chain(project_id, year, steps, force)` 方法
    - 按 STEP_ORDER 顺序执行：recalc_tb → generate_workpapers → generate_reports → generate_notes
    - 步骤依赖自动补充（请求 generate_notes 自动补充 generate_reports）
    - 前置条件校验（PrerequisiteChecker 集成）
    - force=false 时前置不满足返回 400；force=true 时跳过标记 skipped
    - 互斥锁（pg_advisory_xact_lock / 内存锁降级）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x] 2.3 实现 SSE 进度推送
    - 新建 `backend/app/routers/chain_workflow.py`
    - `POST /api/projects/{pid}/workflow/execute-full-chain` 端点
    - `GET /api/projects/{pid}/workflow/progress/{execution_id}` SSE 端点
    - 每步骤开始/完成/失败推送事件
    - 全部完成后推送 `chain_completed` 终止事件
    - 支持多客户端同时订阅
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 2.4 实现执行历史与重试端点
    - `GET /api/projects/{pid}/workflow/executions` 执行历史列表
    - `POST /api/projects/{pid}/workflow/retry/{execution_id}` 重试失败步骤
    - 保留最近 100 条记录
    - 支持按时间范围和状态筛选
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 15.1, 15.2, 15.3_

  - [x] 2.5 前端一键刷新按钮与进度条
    - 修改 `audit-platform/frontend/src/views/ProjectDashboard.vue`（或对应仪表盘视图）
    - 新增"🔄 一键刷新全部"按钮（蓝色实心）
    - 点击后弹出确认对话框 → 调用 execute-full-chain → 订阅 SSE
    - 执行中按钮变为"执行中..."（禁用+旋转图标）
    - 进度条各步骤实时更新状态（灰→蓝旋转→绿勾/红叉）
    - 完成后 ElMessage 摘要通知
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 2.6 注册路由到 router_registry
    - 在 `backend/app/router_registry.py` 注册 chain_workflow router
    - 新增 apiPaths.ts 中 workflow 路径对象
    - _Requirements: 1.1, 2.1_

  - [ ]* 2.7 Write property tests for chain orchestration
    - **Property 1: 步骤依赖自动补充**
    - **Property 2: 互斥锁保证单一执行**
    - **Property 3: SSE 事件完整性**
    - **Validates: Requirements 1.3, 1.9, 2.2-2.5**

  - [x] 2.8 Checkpoint - 全链路编排端到端验证
    - 验证 4 步顺序执行 + SSE 事件流完整
    - 验证互斥锁（同项目同年度双请求 409）
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 3: ReportExcelExporter（模板填充）+ 报表前端格式化

- [x] 3. 报表 Excel 导出与前端表样呈现
  - [x] 3.1 实现 ReportExcelExporter 模板填充导出
    - 新建 `backend/app/services/report_excel_exporter.py`
    - 基于 `审计报告模板/{版本}/{范围}/` 下的 xlsx 模板文件
    - 使用 openpyxl 复制模板后填入数据（保留原有格式/边框/字体/列宽）
    - 生成 4 个 Sheet：资产负债表、利润表、现金流量表、所有者权益变动表
    - 保留致同标准表头（公司名称居中加粗、报表期间、金额单位右对齐）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Excel 导出格式细节
    - 按 indent_level 设置行缩进（每级 2 个中文字符宽度）
    - 合计行加粗字体 + 上边框
    - 金额列千分位格式 `#,##0.00` + 右对齐 + Arial Narrow
    - 负数红色字体或括号格式
    - 合计行保留 Excel SUM 公式（非硬编码数值）
    - 列宽自适应 + 打印区域设置
    - _Requirements: 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12_

  - [x] 3.3 Excel 导出端点与参数支持
    - `POST /api/projects/{pid}/reports/export-excel` 端点
    - 支持 `report_types` 参数（指定导出哪些报表）
    - 支持 `include_prior_year` 参数（是否包含上年对比列）
    - 支持 `mode` 参数（unadjusted/audited）
    - 返回 xlsx 文件流（Content-Disposition attachment）
    - _Requirements: 3.13, 3.14, 3.15_

  - [x] 3.4 报表前端表样格式化（ReportView 增强）
    - 修改 `audit-platform/frontend/src/views/ReportView.vue`
    - 按 indent_level 设置 padding-left（每级 24px）
    - 合计行加粗 + 上边框分隔线
    - 标题行加粗 + 背景色 #f0edf5
    - 金额列 Arial Narrow + 千分位 + 右对齐 + tabular-nums
    - 负数红色 + 括号格式
    - 零值行灰色文字
    - 致同标准表头（公司名称/报表期间/金额单位）
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

  - [x] 3.5 报表前端模式切换与穿透
    - 支持"未审"/"已审"/"对比"三种模式切换 Tab
    - 对比模式同时显示未审数和审定数
    - 行点击穿透到试算表对应科目
    - 空报表友好提示"请先导入账套数据并执行刷新"
    - _Requirements: 18.10, 19.8, 19.9_

  - [ ]* 3.6 Write property tests for Excel export
    - **Property 5: Excel 导出格式不变性**
    - **Property 6: Excel 合计行公式保留**
    - **Validates: Requirements 3.3, 3.5-3.10**

  - [x] 3.7 Checkpoint - 报表导出与前端表样验证
    - 导出 Excel 打开验证格式正确
    - 前端表样视觉验证（缩进/合计行/千分位）
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 4: NoteMDTemplateParser + NoteValidationEngine + 附注公式函数

- [x] 4. 附注 MD 模板解析与校验公式引擎
  - [x] 4.1 实现 NoteMDTemplateParser
    - 新建 `backend/app/services/note_md_template_parser.py`
    - 解析 `附注模版/` 目录下 4 套 MD 文件（国企合并/单体 + 上市合并/单体）
    - 提取章节结构（标题层级、表格定义、文本模板、占位符）
    - 提取表格列定义（列名、对齐方式、数据类型）
    - 删除蓝色指引文字（括号内标注），保留黑色正文和红色待填充项
    - 支持模板热加载（修改 MD 文件后无需重启）
    - _Requirements: 21.1, 21.2, 21.4, 21.5, 21.7, 21.8_

  - [x] 4.2 实现附注模板自动选择逻辑
    - 根据项目 `template_type`（soe/listed）和 `report_scope`（consolidated/standalone）选择模板
    - 集成到 `disclosure_engine.py` 的 `generate_notes` 方法
    - _Requirements: 21.3_

  - [x] 4.3 创建 note_validation_results 表（Alembic 迁移）
    - 新建迁移文件
    - 创建 `note_validation_results` 表（id/project_id/year/section_code/rule_type/rule_expression/passed/expected_value/actual_value/diff_amount/details JSONB/executed_at）
    - _Requirements: 22.7_

  - [x] 4.4 实现 NoteValidationEngine（9 种校验类型）
    - 新建 `backend/app/services/note_validation_engine.py`
    - 加载校验公式预设（`国企版校验公式预设.md` / `上市版校验公式预设.md`）
    - 实现 9 种校验执行器：余额/宽表/纵向/交叉/跨科目/其中项/二级明细/完整性/LLM审核
    - 遵循互斥规则：`[余额]` 不与 `[其中项]`/`[宽表]` 共存
    - 其中项通用规则：sum(明细行) = 合计行
    - 校验结果持久化到 note_validation_results 表
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7_

  - [x] 4.5 扩展 formula_engine.py 新增 WP/REPORT/NOTE 执行器
    - 在 `backend/app/services/formula_engine.py` 新增：
    - `WPExecutor`：从底稿 parsed_data 取数（`WP('E1','审定数')`）
    - `REPORTExecutor`：从 financial_report 取数（`REPORT('BS','BS-001')`）
    - `NOTEExecutor`：从其他附注章节取数（交叉引用）
    - _Requirements: 39.1（公式绑定基础）_

  - [x] 4.6 实现附注宽表公式预设加载与执行
    - 加载 `国企版宽表公式预设.md` / `上市版宽表公式预设.md`
    - 横向公式：期初余额 + 本期增加 - 本期减少 = 期末余额
    - 纵向汇总：各明细行之和 = 合计行
    - 不平衡时标记 warning 并显示差异金额
    - _Requirements: 24.1, 24.2, 24.3, 24.4_

  - [ ]* 4.7 Write property tests for validation engine
    - **Property 12: 附注模板选择正确性**
    - **Property 13: 附注校验互斥规则**
    - **Property 14: 宽表横向公式平衡**
    - **Validates: Requirements 21.2, 21.3, 22.3, 24.2**

  - [x] 4.8 Checkpoint - 附注模板解析与校验引擎验证
    - 验证 4 套 MD 模板解析正确（章节数/表格数/占位符数）
    - 验证 9 种校验类型各自执行逻辑
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 5: 附注数据填充引擎（底稿联动）+ 附注生成规则

- [x] 5. 附注数据填充与通用规则引擎
  - [x] 5.1 创建 note_account_mappings 表（Alembic 迁移）
    - 新建迁移文件
    - 创建 `note_account_mappings` 表（id/template_type/report_row_code/note_section_code/table_index/validation_role/wp_code/fetch_mode）
    - 加载科目对照模板数据（`国企版科目对照模板.md` / `上市版科目对照模板.md`）
    - _Requirements: 23.1, 23.2, 23.3_

  - [x] 5.2 实现附注科目对照映射服务
    - 建立报表行次 → 附注章节 → 表格的三级映射关系
    - 对每个表格标注校验角色（余额/宽表/交叉/其中项/描述）
    - 支持从报表行次自动取数填充附注合计行
    - 支持从试算表明细科目取数填充附注明细行
    - _Requirements: 23.4, 23.5, 23.6_

  - [x] 5.3 实现附注数据填充引擎（4 种取数模式）
    - 修改 `backend/app/services/disclosure_engine.py`
    - 模式 1（合计取数）：从底稿审定表合计行取期末/期初余额
    - 模式 2（明细取数）：从底稿审定表明细行逐行取数
    - 模式 3（分类取数）：从底稿按类别汇总（如按账龄/按性质）
    - 模式 4（变动取数）：从底稿本期增加/减少列取数
    - _Requirements: 36.1, 36.2, 36.3_

  - [x] 5.4 实现附注通用规则引擎（5 条规则）
    - 规则 A（余额驱动）：报表行次金额 ≠ 0 → 生成对应附注章节
    - 规则 B（变动驱动）：本期与上期差异 > 重要性水平 × 5% → 生成变动分析
    - 规则 C（底稿驱动）：对应底稿已编制且有审定数 → 从底稿取数
    - 规则 D（政策驱动）：会计政策章节始终生成
    - 规则 E（关联方驱动）：关联方交易/余额 > 0 → 生成关联方披露
    - 未触发任何规则的章节标记为"本期无此项业务"
    - _Requirements: 35.1, 35.2, 35.3, 35.4, 35.5_

  - [x] 5.5 实现附注从试算表/底稿自动填充
    - 从试算表自动填充期末余额列
    - 从上年试算表自动填充期初余额列
    - 从调整分录自动填充本期变动列
    - 从底稿审定表自动填充明细行数据
    - 无法自动填充的单元格标记为"待填写"
    - 返回填充率统计
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6_

  - [x] 5.6 实现附注内容分层处理策略（5 层）
    - A 层（会计政策）：模板文字 + 占位符替换，不联动底稿
    - B 层（合并科目注释）：底稿联动核心，90%+ 自动填充
    - C 层（母公司注释）：同 B 但取单体 TB
    - D 层（补充信息）：50% 自动 + 50% 手动
    - E 层（附录索引）：100% 自动生成
    - 按层级顺序处理：E → A → B → C → D
    - _Requirements: 46.1, 46.2, 46.5, 46.6, 46.7_

  - [x] 5.7 实现增量刷新与 stale 联动
    - 底稿数据变更时自动标记关联附注章节为 stale
    - 支持增量刷新（仅更新上游数据变更影响的单元格）
    - 支持"从底稿刷新"操作
    - _Requirements: 25.7, 36.4, 36.5_

  - [ ]* 5.8 Write property tests for note generation rules
    - **Property 15: 附注规则引擎驱动生成**
    - **Validates: Requirements 35.1, 35.2, 35.3**

  - [x] 5.9 Checkpoint - 附注数据填充验证
    - 验证 4 种取数模式正确性
    - 验证 5 条规则引擎判断逻辑
    - 验证填充率统计准确
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 6: NoteWordExporter 重写（致同格式）+ 导出包

- [x] 6. 附注 Word 导出与组合导出包
  - [x] 6.1 重写 NoteWordExporter（致同格式）
    - 重写 `backend/app/services/note_word_exporter.py`
    - 致同标准页面设置：A4、左 3cm/右 3.18cm/上 3.2cm/下 2.54cm、页眉 1.3cm/页脚 1.3cm
    - 致同标准字体：中文仿宋_GB2312 小四、数字 Arial Narrow
    - 致同标准标题层级：一级"一、二、三..."加粗、二级"（一）（二）..."、三级"1. 2. 3."
    - 致同标准表格样式：上下边框 1 磅、标题行下边框 1/2 磅、标题行加粗居中、数据行金额右对齐
    - 段落格式：段前 0 行/段后 0.9 行、单倍行距
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 27.1, 27.2, 27.3, 27.4, 27.5_

  - [x] 6.2 Word 导出功能完善
    - 生成目录（TOC 域代码，打开时自动更新）
    - 页脚页码"第 X 页 共 Y 页"
    - 支持章节间交叉引用
    - 空数据章节生成"本期无此项业务"
    - 支持 `sections` 参数指定导出章节
    - 支持 `skip_empty=true` 跳过空章节
    - 支持 HTML 格式预览（preview_html 方法）
    - _Requirements: 4.6, 4.7, 4.8, 4.9, 4.10, 27.6, 27.7, 27.8, 27.9, 27.10_

  - [x] 6.3 Word 导出端点
    - `POST /api/projects/{pid}/notes/export-word` 端点
    - 支持 `template_type` 参数（soe/listed）
    - 返回 docx 文件流
    - _Requirements: 4.1, 4.11_

  - [x] 6.4 创建 export_logs 表（Alembic 迁移）
    - 新建迁移文件
    - 创建 `export_logs` 表（id/project_id/year/export_type/file_name/file_size_bytes/exported_by/consistency_result JSONB/data_hash/created_at）
    - _Requirements: 9.5_

  - [x] 6.5 实现 ExportPackageService（ZIP 组合导出）
    - 新建 `backend/app/services/export_package_service.py`
    - `POST /api/projects/{pid}/workflow/export-package` 端点
    - ZIP 包含：`财务报表_{公司名}_{年度}.xlsx` + `财务报表附注_{公司名}_{年度}.docx`
    - 可选包含审计报告 + 审定表
    - 打包前执行 ConsistencyGate 校验
    - 校验失败返回 400；force_export=true 跳过校验附加 `_warnings.txt`
    - ZIP 根目录生成 `manifest.json`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 6.6 导出文件命名规范
    - 报表：`{公司简称}_{年度}年度财务报表.xlsx`
    - 附注：`{公司简称}_{年度}年度财务报表附注.docx`
    - 组合包：`{公司简称}_{年度}年度审计终稿.zip`
    - 从项目配置读取公司简称
    - 文件名避免特殊字符（替换为下划线）
    - _Requirements: 32.1, 32.2, 32.3, 32.4_

  - [ ]* 6.7 Write property tests for Word export and package
    - **Property 7: Word 导出页面设置**
    - **Property 8: 附注空章节占位文本**
    - **Property 9: 组合导出包完整性**
    - **Property 16: 导出文件命名规范**
    - **Validates: Requirements 4.2, 4.9, 5.2, 5.8, 27.1, 27.6, 32.1, 32.4**

  - [x] 6.8 Checkpoint - 导出功能端到端验证
    - 导出 Word 验证致同格式正确
    - 导出 ZIP 验证文件完整性
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 7: ConsistencyGate + 导出对话框 + Stale 级联 + 工作流仪表盘

- [x] 7. 一致性门控与工作流仪表盘
  - [x] 7.1 实现 ConsistencyGate（5 项检查）
    - 新建 `backend/app/services/consistency_gate.py`
    - `GET /api/projects/{pid}/workflow/consistency-check` 端点
    - 检查 1：试算平衡（资产合计 = 负债合计 + 权益合计）
    - 检查 2：报表平衡（BS 资产合计 = 负债+权益合计）
    - 检查 3：利润表勾稽（营业收入 - 营业成本 - 费用 + 营业外 = 净利润）
    - 检查 4：附注完整性（有数据的报表行次对应附注章节已生成）
    - 检查 5：数据新鲜度（无 stale 标记）
    - 每项返回 `{ check_name, passed, details, severity }`
    - severity 分 blocking/warning
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 7.2 数据过期自动检测与级联标记
    - 修改 `backend/app/services/event_handlers.py`
    - 调整分录创建/修改/删除 → 标记试算表 stale
    - 试算表 stale → 级联标记所有报表 stale
    - 报表 stale → 级联标记所有附注 stale
    - 全链路执行完成后清除所有 stale 标记
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [x] 7.3 前端 Stale 横幅与刷新按钮
    - 在试算表/报表/附注页面顶部显示橙色横幅"数据已过期，请刷新"
    - 横幅中提供"立即刷新"按钮
    - 点击后执行从当前步骤开始的部分链路
    - _Requirements: 8.4, 8.5_

  - [x] 7.4 前端导出对话框
    - 新建 `audit-platform/frontend/src/components/ExportDialog.vue`
    - 3 种导出模式：仅报表 Excel / 仅附注 Word / 完整导出包
    - "完整导出包"模式下可选：包含审计报告 / 包含审定表
    - 导出前显示一致性检查结果（绿/红/黄）
    - blocking 项禁用导出按钮
    - "强制导出"复选框（admin/partner 可见）
    - 导出进度条 + 完成后自动下载
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 7.5 工作流状态仪表盘
    - 新建 `audit-platform/frontend/src/components/WorkflowDashboard.vue`
    - 6 步进度条：导入账套 → 科目映射 → 试算表 → 报表 → 底稿 → 附注
    - 每步状态图标：未开始/进行中/已完成/需刷新
    - stale 时该步骤及下游显示"需刷新"
    - "一键刷新全部"按钮 + "导出"下拉按钮
    - 执行完成后显示摘要
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 7.6 Write property tests for consistency gate and stale cascade
    - **Property 10: 一致性门控正确性**
    - **Property 17: 数据过期级联标记**
    - **Validates: Requirements 6.5, 6.6, 8.1, 8.2, 8.3**

  - [x] 7.7 Checkpoint - 一致性门控与工作流验证
    - 验证 5 项检查逻辑正确
    - 验证 stale 级联标记完整
    - 验证导出对话框交互流程
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 8: 附注编辑体验（表格结构 + 公式绑定 + 枚举联动）

- [x] 8. 附注前端编辑体验增强
  - [x] 8.1 附注前端编辑器增强（DisclosureEditor）
    - 修改 `audit-platform/frontend/src/views/DisclosureEditor.vue`
    - 每个章节显示：章节标题 + 文本内容 + 表格数据
    - 表格使用 el-table，支持单元格编辑（双击进入编辑模式）
    - 金额单元格 Arial Narrow + 千分位 + 右对齐
    - 自动填充单元格浅蓝色背景
    - 校验失败单元格红色边框 + tooltip
    - "从报表刷新"按钮
    - 左侧目录树校验错误红色标记
    - 章节折叠/展开
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8_

  - [x] 8.2 附注表格结构手动编辑
    - 支持新增行/删除行/新增列/删除列/修改列名/调整列宽/调整列顺序
    - 结构编辑后自动重新计算合计行
    - 支持撤销/重做（Ctrl+Z / Ctrl+Y）
    - 结构变更持久化到数据库（不影响原始模板）
    - 支持"恢复模板结构"操作
    - _Requirements: 38.1, 38.2, 38.3, 38.4, 38.5, 38.6_

  - [x] 8.3 附注公式绑定管理
    - 每个数值单元格支持绑定公式（TB/WP/REPORT）
    - 右键菜单"编辑公式"/"清除公式"/"查看公式来源"
    - 有公式绑定的单元格显示蓝色三角标记
    - 全链路刷新时按公式重新计算
    - 公式计算失败保留上次有效值并标记 warning
    - _Requirements: 39.1, 39.2, 39.3, 39.4, 39.6_

  - [x] 8.4 附注枚举联动
    - 表格列绑定全局枚举字典（下拉选择）
    - 预置 10 种附注常用枚举（aging_period/yes_no/investment_method 等）
    - 列头右键菜单"绑定枚举"
    - 校验时检查枚举列值是否在有效范围内
    - 支持项目级临时扩展枚举值
    - _Requirements: 40.1, 40.2, 40.3, 40.4, 40.5, 40.7_

  - [x] 8.5 附注完成度追踪
    - 每个章节显示完成状态：未开始/自动填充/编辑中/已完成/已复核
    - 左侧目录树颜色区分（灰/蓝/黄/绿/紫）
    - 顶部整体完成度进度条
    - "标记为已完成"操作
    - 全部完成后启用"导出"按钮
    - _Requirements: 45.1, 45.2, 45.3, 45.4, 45.5_

  - [x] 8.6 附注目录树层级图标与筛选
    - 不同层级图标（A=📝 B=📊 C=📊 D=📋 E=📑）
    - B/C 层显示"从底稿刷新"按钮
    - 支持按负责人筛选章节
    - _Requirements: 46.3, 46.4, 45.6_

  - [x] 8.7 Checkpoint - 附注编辑体验验证
    - 验证表格编辑/公式绑定/枚举联动交互
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 9: 国企↔上市转换 + 富文本编辑器 + 上年附注导入

- [x] 9. 高级附注功能
  - [x] 9.1 国企版与上市版互转
    - 新建 `backend/app/services/note_conversion_service.py`
    - 基于 `审计报告模板/纯报表科目注释/` 对照模板执行行次映射
    - 报表行次映射：国企版 row_code → 上市版 row_code（保留金额）
    - 附注章节映射：保留已填充数据
    - 公式适配：更新 row_code 引用
    - 转换前影响预览（新增/删除/保留数量）
    - 转换操作支持撤销（保留快照 30 天）
    - 转换完成后自动执行全链路刷新
    - _Requirements: 47.1, 47.2, 47.3, 47.4, 47.5, 47.6, 47.7_

  - [x] 9.2 附注文字章节富文本编辑器
    - 对层级 A/D 文字章节提供富文本编辑器
    - 支持：标题层级/加粗/斜体/有序无序列表/表格插入/缩进/字体颜色
    - 占位符插入（{公司名称}/{年度}/{币种}等）蓝色标签样式
    - 支持从 Word 粘贴（保留基本格式）
    - 支持"查看源码"模式
    - 字数统计
    - _Requirements: 48.1, 48.2, 48.3, 48.4, 48.5, 48.6, 48.7_

  - [x] 9.3 上年附注导入与继承
    - 提供"导入上年附注"功能（接受 .docx 上传）
    - 解析 Word 章节结构（按标题层级拆分）
    - 上年文字内容填入本年对应章节（按标题匹配）
    - 上年数据标记为"待更新"（黄色高亮）
    - 上年表格数据提取到"期初余额"列
    - 连续审计项目自动从上年数据库继承
    - _Requirements: 51.1, 51.2, 51.3, 51.4, 51.5, 51.7, 51.8_

  - [x] 9.4 附注打印预览与分页控制
    - "打印预览"模式（A4 页面视图 + 分页线）
    - 跨页表格自动重复表头行
    - 孤行控制（表格至少保留 2 行同页）
    - 章节标题与后续内容保持同页
    - 支持手动插入分页符
    - _Requirements: 41.1, 41.2, 41.3, 41.4, 41.5_

  - [x] 9.5 交叉引用自动生成
    - 报表行次"附注编号"列自动填入对应章节序号
    - 附注文本中 `{ref:BS-001}` 占位符替换为"详见附注五、（一）1"
    - 章节顺序调整后自动更新所有交叉引用
    - Word 导出时生成 Word 书签+REF 域
    - Excel 导出时填入附注编号列
    - _Requirements: 42.1, 42.2, 42.3, 42.4, 42.5_

  - [x] 9.6 变动分析自动生成
    - 变动率 > 20% 的科目自动生成变动分析段落模板
    - 增加模板/减少模板（含金额/百分比/原因占位）
    - `{原因占位}` 标记为待填写（黄色高亮）
    - 变动率 ≤ 20% 不生成（除非手动要求）
    - _Requirements: 43.1, 43.2, 43.3, 43.5_

  - [ ]* 9.7 Write property tests for cross-reference and variation analysis
    - **Property 18: 交叉引用编号一致性**
    - **Property 19: 变动分析生成阈值**
    - **Validates: Requirements 42.1-42.3, 43.1, 43.5**

  - [x] 9.8 Checkpoint - 高级附注功能验证
    - 验证国企↔上市转换正确性
    - 验证交叉引用编号一致
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 10: 集团模板继承 + 多人协作 + 完成度追踪 + 属性测试

- [x] 10. 企业级功能与最终验证
  - [x] 10.1 集团模板继承与下发
    - 支持"集团模板"保存（章节结构+文字+表格结构+校验规则）
    - "下发模板"操作（选择子企业项目列表一键应用）
    - 下发策略：A 层覆盖 / B/C 层保留数据更新结构 / D 层合并
    - 支持"参照模板"模式（不强制覆盖）
    - 集团模板更新时通知子企业
    - 支持"脱离集团模板"
    - _Requirements: 52.1, 52.2, 52.3, 52.4, 52.5, 52.6, 52.7_

  - [x] 10.2 多人协作与锁定机制
    - 章节级锁定（编辑时其他用户只读）
    - 显示锁定人姓名和时间
    - 锁定自动释放（离开/5 分钟无操作/关闭浏览器）
    - 项目经理强制解锁
    - 保存时版本冲突检查（乐观锁）
    - "我的待编章节"筛选
    - _Requirements: 44.1, 44.2, 44.3, 44.4, 44.5, 44.6_

  - [x] 10.3 报表附注数据锁定与版本快照
    - 审计报告签字完成后自动锁定报表和附注
    - 锁定时生成数据快照（JSON）
    - 锁定后页面显示"🔒 已锁定"横幅
    - 支持"解锁"操作（admin/partner + 填写原因 + 审计日志）
    - 历史快照链（版本 1→版本 2→...）
    - "查看签字时版本"对比功能
    - 导出包附加快照哈希值（SHA-256）
    - _Requirements: 53.1, 53.2, 53.3, 53.4, 53.5, 53.6, 53.7_

  - [x] 10.4 批量项目操作
    - `POST /api/workflow/batch-execute` 端点
    - 接受 `{ project_ids, year, steps }` 参数
    - 每个项目独立执行，互不影响
    - 返回批量执行汇总（成功/失败/跳过数）
    - 最多同时处理 10 个项目（超过排队）
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 10.5 签字门禁集成
    - GateEngine 新增 `AllReportsGeneratedRule`
    - GateEngine 新增 `AllNotesGeneratedRule`
    - GateEngine 新增 `ConsistencyPassedRule`
    - 注册到 sign_off 和 export_package 两个 GateType
    - 签字面板显示"请先执行全链路刷新"提示
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [x] 10.6 EQCR 只读访问
    - eqcr 角色隐藏"生成"和"刷新"按钮
    - eqcr 角色隐藏附注编辑功能
    - EQCR 工作台显示最后生成时间和操作人
    - "导出只读副本"按钮（带水印"仅供复核"）
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x] 10.7 附注章节模板可扩展性
    - 支持"自定义章节"（纯文字/纯表格/混合）
    - 自定义章节支持绑定公式和校验规则
    - "章节模板库"保存为模板供其他项目复用
    - 模板升级时增量合并（保留用户自定义）
    - _Requirements: 49.1, 49.2, 49.3, 49.4, 49.5, 49.6, 49.8_

  - [x] 10.8 附注内容可视化与导航
    - "大纲视图"模式（标题+摘要+合计金额）
    - 按状态筛选 / 按金额排序 / 快速跳转
    - 折叠全部/展开全部
    - _Requirements: 50.1, 50.2, 50.3, 50.4, 50.5, 50.6_

  - [ ]* 10.9 Write property tests for data locking
    - **Property 20: 签字后数据不可变**
    - **Validates: Requirements 53.1, 53.3**

  - [x] 10.10 Final Checkpoint - 全链路端到端验证
    - 从账套导入到最终导出的完整闭环验证
    - 4 个真实项目数据验证
    - 所有 20 条属性测试通过（max_examples=100）
    - Ensure all tests pass, ask the user if questions arise.

---

### Sprint 11（补充）: 全局联动与平台级优化（覆盖缺口）

- [x] 11. 全局联动补齐
  - [x] 11.1 版本对比功能
    - 全链路执行前保存当前报表快照（snapshot_before JSONB）
    - `GET /api/projects/{pid}/workflow/compare/{execution_id}` 端点
    - 返回每行变化：`{ row_code, row_name, before, after, diff, diff_percent }`
    - 前端"查看变化"按钮 → 对比抽屉（绿色/红色高亮增减）
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 11.2 四表→报表→底稿→附注全链路穿透
    - 扩展 usePenetrate composable 新增穿透路径：
    - 报表行次 → 附注章节（正向）/ 附注 → 报表（反向）
    - 报表行次 → 底稿审定表 → 调整分录
    - 调整分录 → 影响范围分析（列出受影响的报表行次和附注章节）
    - 前端右键菜单"查看附注"/"查看底稿"/"查看明细"/"影响分析"
    - 穿透跳转自动 push NavigationStack
    - _Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.6_

  - [x] 11.3 全局数据一致性实时监控
    - 项目仪表盘"数据健康度"指标（0-100 分）
    - 8 项一致性检查（TB 平衡/BS 平衡/IS 勾稽/TB vs 报表/报表 vs 附注/底稿 vs TB/调整借贷平衡/附注期初 vs 上年期末）
    - 每项通过/警告/失败状态
    - 失败时"一键修复"建议
    - 定时自动检查（保存后 + 每 30 分钟）
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5_

  - [x] 11.4 报表与附注联动编辑
    - 报表行次金额变更 → 自动标记对应附注章节 stale
    - 附注目录树橙色标记 stale 章节
    - "同步到附注"按钮（一键刷新关联附注合计行）
    - 同步时保留用户手动编辑的明细行
    - 同步后自动执行附注校验公式
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5_

  - [x] 11.5 项目级配置中心
    - 项目设置页配置项：报表标准/报表范围/金额单位/附注模板类型/导出格式偏好
    - 配置变更时自动标记受影响产物为 stale
    - 支持从其他项目复制配置
    - 报表标准变更时提示"将重新生成全部报表和附注"
    - _Requirements: 31.1, 31.2, 31.3, 31.4_

  - [x] 11.6 多年度对比支持
    - 报表生成时自动填充"上年同期"列
    - ReportView 对比模式显示 3 列（本年未审/本年审定/上年审定）+ 变动额+变动率
    - 变动率 >20% 标红
    - 附注表格自动填充"期初余额"列
    - 连续审计/首次承接两种模式
    - _Requirements: 33.1, 33.2, 33.3, 33.4, 33.5, 33.6_

  - [x] 11.7 前端全局组件统一
    - 所有金额展示统一 GtAmountCell（目标 90%+ 视图覆盖）
    - 所有表格统一致同表头样式
    - 所有空状态统一 GtEmpty
    - 所有加载状态统一 el-skeleton
    - 所有错误处理统一 handleApiError（消除剩余 11 处裸 ElMessage.error）
    - 所有分页统一标准组件
    - 所有数字列统一 .gt-amt class
    - _Requirements: 34.1, 34.2, 34.3, 34.4, 34.5, 34.6, 34.7_

  - [x] 11.8 附注智能裁剪与排序
    - 按报表行次金额自动排序附注章节
    - 小金额科目合并到"其他"（< 重要性水平 × 1%）
    - 合并/单体自动裁剪不适用章节
    - 用户手动调整顺序（拖拽）
    - 裁剪后自动重新编号
    - 保留"必披露"章节不被裁剪
    - _Requirements: 37.1, 37.2, 37.3, 37.4, 37.5, 37.6_

  - [x] 11.9 Checkpoint - 全局联动验证
    - 验证穿透链路完整性
    - 验证一致性监控 8 项检查
    - 验证报表↔附注联动同步
    - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (max_examples=100)
- Unit tests validate specific examples and edge cases
- 每个 Sprint ≤10 个任务，强制回归测试+UAT 才进下一 Sprint
- 标任务 [x] 前必须跑 pytest 验证
- 手动浏览器验证放 UAT 验收清单（不占 taskStatus 工作流）

## UAT 验收清单（手动浏览器验证）

1. 导入账套后点击"一键刷新全部"，观察进度条实时更新
2. 报表页面切换"未审/已审/对比"模式，验证数据正确
3. 报表页面验证缩进/合计行/千分位/负数红色格式
4. 导出 Excel 打开验证致同模板格式保留
5. 附注页面验证表格编辑/公式绑定/枚举下拉
6. 导出 Word 打开验证致同格式（页边距/字体/标题层级/表格样式）
7. 导出完整包验证 ZIP 内容（manifest.json + 文件命名）
8. 一致性检查验证 5 项检查结果展示
9. stale 横幅验证（修改调整分录后报表/附注显示过期提示）
10. 签字后验证报表/附注锁定不可编辑
