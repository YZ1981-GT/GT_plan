# 需求文档：审计全链路一键生成与导出

## 引言

致同审计作业平台当前存在严重的工作流断裂问题：用户完成账套导入和调整确认后，必须手动依次触发 5+ 个独立步骤（重算试算表→生成底稿→生成报表→生成附注→导出），且每步之间无事务性保障、无进度可视化、无错误恢复机制。报表公式覆盖率仅 26.5%（BS 43%/IS 21%/CFS 0%/EQ 0%），导出格式不符合致同模板标准。

**报表模块核心问题**：未审报表表样无法正确生成——公式覆盖不足导致大部分行次为 0；前端表样缺乏缩进/合计行/千分位等格式；不支持"未审"vs"审定"双模式切换。

**附注模块核心问题**：附注模板体系未完整落地——`附注模版/` 目录下有 4 套 MD 模板（国企合并/单体 + 上市合并/单体）+ 校验公式预设 + 科目对照模板 + 宽表公式预设共 10 个文件，但后端仅使用了简化版 JSON 种子数据，未解析完整 MD 模板结构；校验公式引擎未实现；附注数据填充率低。

本功能建立"一键全链路生成+导出"机制，同时修复报表模块（公式覆盖率提升到 90%+、未审/审定双模式、致同表样格式）和附注模块（4 套 MD 模板解析、校验公式引擎、科目对照映射、宽表公式、致同 Word 导出格式），实现从账套导入到最终导出的完整闭环。

### 现有实现状态（代码分析结论）

| 组件 | 文件 | 大小 | 已实现 | 关键缺失 |
|------|------|------|--------|---------|
| 报表引擎 | report_engine.py | 41KB | generate_all_reports + TB/SUM_TB/ROW 公式解析 + Redis 缓存 + unadjusted 模式标记 | CFS 间接法未实现；report_config_seed.json 仅 22 行骨架（DB 中 1191 行由脚本填充但公式覆盖仅 26.5%） |
| 附注引擎 | disclosure_engine.py | 35KB | generate_notes + populate_table_data + 加载 SOE/Listed JSON 模板（173/187 章节） | TB()/WP()/REPORT() 公式未在附注中实现；校验引擎未实现；MD 模板未被使用（仅用 JSON 简化版） |
| Word 导出 | note_word_exporter.py | 3KB | python-docx 基础骨架（表格+标题+字体） | 页面设置/TOC/页码/致同格式全部缺失（极简占位） |
| 统一公式引擎 | formula_engine.py | 17KB | FormulaResult/FormulaContext/safe_eval/SUM_TB/PREV/validate | _resolve_tb 和 _resolve_row 未实现（部分骨架） |
| 事件级联 | event_handlers.py | 26KB | ADJUSTMENT→TB→REPORTS→WP 全链 + stale 标记 + cascade | LEDGER_ACTIVATED 事件未订阅 |
| 底稿预填充 | prefill_engine.py | 37KB | 94 映射/481 单元格配置 + 三级降级策略（坐标→列头→语义行） | 与 Univer 公式引擎未完全集成 |
| 底稿模板 | wp_template_init_service.py | 22KB | 模板查找/复制/多文件合并/prefill 写入 | 工作正常，已验证 |
| 附注 JSON 模板 | note_template_soe/listed.json | 420KB/759KB | SOE 173 章节 / Listed 187 章节完整结构 | 仅作为生成框架，未与 MD 模板的校验公式/科目对照联动 |
| 报表 Excel 模板 | 审计报告模板/*.xlsx | 4 套 | 文件存在，格式完整 | 未被导出引擎使用（当前导出是从零生成而非基于模板填充） |

### 实施策略

基于以上分析，本 spec 的实施不是"从零开发"而是"补齐缺口+增强格式"：
- **报表模块**：核心引擎已就绪，需补齐 report_config 公式（从 26.5% → 90%+）+ 增强 Excel 导出（基于模板填充）
- **附注模块**：生成框架已就绪（173/187 章节），需接入 MD 模板的校验公式 + 实现 TB()/WP()/REPORT() 取数 + 增强 Word 导出格式
- **全链路编排**：事件级联已就绪，需封装为单一编排端点 + SSE 进度 + 前端一键按钮
- **底稿模块**：已基本完成，仅需与报表/附注的联动取数打通

## 术语表

- **Chain_Orchestrator**：全链路编排服务，负责按依赖顺序执行生成步骤并汇报进度
- **Chain_Step**：编排链中的单个步骤（recalc_tb / generate_workpapers / generate_reports / generate_notes）
- **Chain_Execution**：一次完整的全链路执行记录，含各步骤状态和耗时
- **Report_Excel_Exporter**：报表 Excel 导出引擎，按致同模板格式生成多 Sheet 工作簿
- **Note_Word_Exporter**：附注 Word 导出引擎（已有基础版，需增强致同格式）
- **Export_Package**：组合导出包（ZIP），含报表 Excel + 附注 Word + 可选审计报告
- **Stale_Indicator**：数据过期指示器，标识上游数据变更后下游产物需要刷新
- **Progress_Stream**：SSE 进度流，实时推送各步骤执行状态给前端
- **Consistency_Gate**：一致性门控，导出前校验数据完整性（TB 平衡/报表平衡/附注完整性）
- **Workflow_Dashboard**：工作流状态仪表盘，展示项目当前所处阶段和各步骤完成情况
- **Note_Template_MD**：附注 MD 模板文件，`附注模版/` 目录下 4 套完整模板（国企合并/单体 + 上市合并/单体），定义章节结构、表格列、文本占位符
- **Note_Validation_Preset**：附注校验公式预设，`附注模版/国企版校验公式预设.md` 和 `上市版校验公式预设.md`，定义余额/宽表/纵向/交叉/其中项/完整性/LLM 审核等校验规则
- **Note_Account_Mapping**：附注科目对照模板，`附注模版/国企版科目对照模板.md` 和 `上市版科目对照模板.md`，定义报表行次→附注章节→表格的三级映射
- **Note_Wide_Table_Preset**：附注宽表公式预设，`附注模版/国企版宽表公式预设.md` 和 `上市版宽表公式预设.md`，定义横向公式（期初±变动=期末）
- **Unadjusted_Report**：未审报表，使用 trial_balance.unadjusted_amount 生成的报表（导入后即可查看）
- **Audited_Report**：审定报表，使用 trial_balance.audited_amount 生成的报表（含调整分录影响）
- **Audit_Report_Template_Dir**：审计报告模板目录，`审计报告模板/` 下按 国企版/上市版 × 合并/单体 组织，每套含 3 个文件：审计报告正文（.docx）+ 财务报表（.xlsx）+ 附注模板（.docx）
- **Report_Excel_Template**：报表 Excel 模板文件，`审计报告模板/{版本}/{范围}/` 下的 .xlsx 文件，定义报表表样格式（行次/列头/样式），系统生成报表时以此为基础填充数据

## 需求

### 需求 1：全链路编排端点

**User Story:** 作为审计助理，我想点击一个按钮就能完成从试算表重算到附注生成的全部步骤，以便节省手动逐步操作的时间。

#### 验收标准

1. THE Chain_Orchestrator SHALL 提供 `POST /api/projects/{pid}/workflow/execute-full-chain` 端点，接受 `{ year, steps, force }` 参数
2. WHEN steps 参数为空时，THE Chain_Orchestrator SHALL 按默认顺序执行全部 4 步：recalc_tb → generate_workpapers → generate_reports → generate_notes
3. WHEN steps 参数指定部分步骤时，THE Chain_Orchestrator SHALL 仅执行指定步骤并自动补充必要前置步骤
4. THE Chain_Orchestrator SHALL 在执行每步前调用 PrerequisiteChecker 校验前置条件
5. IF 前置条件不满足且 force=false，THEN THE Chain_Orchestrator SHALL 返回 HTTP 400 并指明缺失的前置条件
6. IF 前置条件不满足且 force=true，THEN THE Chain_Orchestrator SHALL 跳过该步骤并在结果中标记 skipped
7. THE Chain_Orchestrator SHALL 返回 Chain_Execution 记录，包含 execution_id、各步骤状态（pending/running/completed/failed/skipped）、耗时、错误信息
8. WHEN 某步骤执行失败时，THE Chain_Orchestrator SHALL 继续执行后续不依赖该步骤的步骤，并在最终结果中标记失败步骤
9. THE Chain_Orchestrator SHALL 在同一项目同一年度同时只允许一个 Chain_Execution 运行（互斥锁）
10. THE Chain_Orchestrator SHALL 将执行记录持久化到数据库，支持查询历史执行记录

### 需求 2：SSE 实时进度推送

**User Story:** 作为审计助理，我想在全链路执行过程中实时看到每个步骤的进度，以便了解当前执行到哪一步。

#### 验收标准

1. THE Progress_Stream SHALL 提供 `GET /api/projects/{pid}/workflow/progress/{execution_id}` SSE 端点
2. THE Progress_Stream SHALL 每个步骤开始时推送 `{ step, status: "running", started_at }` 事件
3. THE Progress_Stream SHALL 每个步骤完成时推送 `{ step, status: "completed", duration_ms, summary }` 事件
4. THE Progress_Stream SHALL 每个步骤失败时推送 `{ step, status: "failed", error_message }` 事件
5. THE Progress_Stream SHALL 在全部步骤完成后推送 `{ type: "chain_completed", total_duration_ms, results }` 终止事件
6. IF SSE 连接断开后重连，THEN THE Progress_Stream SHALL 从当前步骤状态开始推送（不重放已完成步骤）
7. THE Progress_Stream SHALL 支持同一 execution_id 的多个客户端同时订阅

### 需求 3：报表 Excel 导出（致同格式）

**User Story:** 作为审计助理，我想将四张财务报表导出为符合致同模板格式的 Excel 文件，以便直接用于审计工作底稿归档。

#### 验收标准

1. THE Report_Excel_Exporter SHALL 提供 `POST /api/projects/{pid}/reports/export-excel` 端点，返回 xlsx 文件流
2. THE Report_Excel_Exporter SHALL 基于 `审计报告模板/{版本}/{范围}/` 下的 xlsx 模板文件生成报表（国企版用 `1.1-2025国企财务报表.xlsx`，上市版用 `2.股份年审－经审计的财务报表-202601.xlsx`）
3. THE Report_Excel_Exporter SHALL 复制模板文件后，将计算结果填入对应单元格（保留模板原有格式/边框/字体/列宽）
4. THE Report_Excel_Exporter SHALL 生成包含 4 个 Sheet 的工作簿：资产负债表、利润表、现金流量表、所有者权益变动表
5. THE Report_Excel_Exporter SHALL 在每个 Sheet 顶部保留致同标准表头：公司名称（居中加粗）、报表期间（居中）、金额单位（右对齐，如"单位：人民币元"）
6. THE Report_Excel_Exporter SHALL 按 report_config 的 indent_level 设置行缩进（每级 2 个中文字符宽度）
7. THE Report_Excel_Exporter SHALL 对合计行设置加粗字体和上边框样式
8. THE Report_Excel_Exporter SHALL 对金额列设置千分位格式（`#,##0.00`）、右对齐、Arial Narrow 字体
9. THE Report_Excel_Exporter SHALL 对负数金额使用红色字体或括号格式 `(1,234.56)`
10. THE Report_Excel_Exporter SHALL 在合计行保留 Excel SUM 公式（而非硬编码数值）
11. THE Report_Excel_Exporter SHALL 设置列宽自适应（项目名称列 40 字符宽、金额列 18 字符宽）
12. THE Report_Excel_Exporter SHALL 设置打印区域和页面方向（横向/纵向根据报表类型自动选择）
13. THE Report_Excel_Exporter SHALL 支持参数 `report_types` 指定导出哪些报表（默认全部 4 张）
14. THE Report_Excel_Exporter SHALL 支持参数 `include_prior_year` 控制是否包含上年对比列
15. THE Report_Excel_Exporter SHALL 支持参数 `mode`（unadjusted/audited）控制导出未审报表还是审定报表

### 需求 4：附注 Word 导出（致同格式增强）

**User Story:** 作为审计助理，我想将财务报表附注导出为符合致同附注模板格式的 Word 文档，以便直接用于审计报告附件。

#### 验收标准

1. THE Note_Word_Exporter SHALL 提供 `POST /api/projects/{pid}/notes/export-word` 端点，返回 docx 文件流
2. THE Note_Word_Exporter SHALL 使用致同标准页面设置：A4 纸张、上 3cm/下 2.54cm/左 3.18cm/右 3.2cm 页边距
3. THE Note_Word_Exporter SHALL 使用致同标准标题层级：一级"一、二、三..."、二级"（一）（二）（三）..."、三级"1. 2. 3."
4. THE Note_Word_Exporter SHALL 对表格使用致同标准样式：表头行加粗居中、数据行金额右对齐、全边框、表头底色浅灰
5. THE Note_Word_Exporter SHALL 对金额数字使用 Arial Narrow 字体、千分位格式
6. THE Note_Word_Exporter SHALL 在文档开头生成目录（TOC 域代码，打开时自动更新）
7. THE Note_Word_Exporter SHALL 在页脚添加页码（格式："第 X 页 共 Y 页"）
8. THE Note_Word_Exporter SHALL 支持章节间的交叉引用（如"详见附注五（一）"）
9. THE Note_Word_Exporter SHALL 对空数据章节生成占位文本"本期无此项业务"
10. THE Note_Word_Exporter SHALL 支持参数 `sections` 指定导出哪些章节（默认全部）
11. THE Note_Word_Exporter SHALL 支持参数 `template_type` 指定模板类型（SOE 国企版/Listed 上市版）

### 需求 5：组合导出包

**User Story:** 作为合伙人，我想一键下载包含报表 Excel 和附注 Word 的完整导出包，以便快速获取审计终稿全套文件。

#### 验收标准

1. THE Export_Package SHALL 提供 `POST /api/projects/{pid}/workflow/export-package` 端点，返回 ZIP 文件流
2. THE Export_Package SHALL 包含以下文件：`财务报表_{公司名}_{年度}.xlsx` + `财务报表附注_{公司名}_{年度}.docx`
3. WHERE 参数 include_audit_report=true，THE Export_Package SHALL 额外包含 `审计报告_{公司名}_{年度}.docx`（基于 `审计报告模板/{版本}/{范围}/` 下的审计报告正文模板生成，填充项目信息和意见段落）
4. WHERE 参数 include_workpapers=true，THE Export_Package SHALL 额外包含 `审定表/` 目录（各循环审定表 xlsx）
5. THE Export_Package SHALL 在打包前执行 Consistency_Gate 校验
6. IF Consistency_Gate 校验发现数据不一致，THEN THE Export_Package SHALL 返回 HTTP 400 并列出不一致项
7. WHERE 参数 force_export=true，THE Export_Package SHALL 跳过一致性校验直接打包（在 ZIP 中附加 `_warnings.txt` 记录跳过的校验项）
8. THE Export_Package SHALL 在 ZIP 根目录生成 `manifest.json`（文件清单、生成时间、操作人、数据版本哈希）

### 需求 6：导出前一致性门控

**User Story:** 作为质控人员，我想在导出前自动检查数据一致性，以便确保导出的报表和附注数据正确无误。

#### 验收标准

1. THE Consistency_Gate SHALL 提供 `GET /api/projects/{pid}/workflow/consistency-check` 端点
2. THE Consistency_Gate SHALL 执行以下 5 项检查：
   - 试算平衡（资产合计 = 负债合计 + 权益合计）
   - 报表平衡（BS 资产合计 = 负债+权益合计）
   - 利润表勾稽（营业收入 - 营业成本 - 费用 + 营业外 = 净利润）
   - 附注完整性（所有有数据的报表行次对应的附注章节已生成）
   - 数据新鲜度（无 stale 标记的报表/附注）
3. THE Consistency_Gate SHALL 对每项检查返回 `{ check_name, passed, details, severity }` 结构
4. THE Consistency_Gate SHALL 将 severity 分为 blocking（阻断导出）和 warning（允许导出但提示）
5. WHEN 所有 blocking 项通过时，THE Consistency_Gate SHALL 返回 `{ overall: "pass" }`
6. WHEN 存在 blocking 项未通过时，THE Consistency_Gate SHALL 返回 `{ overall: "fail", blocking_items: [...] }`

### 需求 7：工作流状态仪表盘

**User Story:** 作为项目经理，我想在项目仪表盘看到当前项目的审计工作流进度，以便掌握项目整体完成情况。

#### 验收标准

1. THE Workflow_Dashboard SHALL 在项目详情页顶部显示 6 步进度条：导入账套 → 科目映射 → 试算表 → 报表 → 底稿 → 附注
2. THE Workflow_Dashboard SHALL 对每步显示状态图标：未开始（灰色圆圈）、进行中（蓝色旋转）、已完成（绿色勾）、需刷新（橙色感叹号）
3. WHEN 某步骤数据过期（stale）时，THE Workflow_Dashboard SHALL 在该步骤及所有下游步骤显示"需刷新"状态
4. THE Workflow_Dashboard SHALL 在进度条下方显示"一键刷新全部"按钮
5. WHEN 用户点击"一键刷新全部"时，THE Workflow_Dashboard SHALL 调用 Chain_Orchestrator 执行全链路
6. THE Workflow_Dashboard SHALL 在执行过程中实时更新各步骤状态（通过 SSE 订阅）
7. THE Workflow_Dashboard SHALL 在执行完成后显示摘要（各步骤耗时、生成行数、错误信息）
8. THE Workflow_Dashboard SHALL 提供"导出"下拉按钮（导出报表 Excel / 导出附注 Word / 导出完整包）

### 需求 8：数据过期自动检测与级联标记

**User Story:** 作为审计助理，我想在调整分录变更后自动看到哪些报表和附注需要刷新，以便及时更新受影响的产物。

#### 验收标准

1. WHEN 调整分录创建/修改/删除时，THE Stale_Indicator SHALL 标记试算表为 stale
2. WHEN 试算表标记为 stale 时，THE Stale_Indicator SHALL 级联标记所有报表为 stale
3. WHEN 报表标记为 stale 时，THE Stale_Indicator SHALL 级联标记所有附注为 stale
4. THE Stale_Indicator SHALL 在试算表/报表/附注页面顶部显示橙色横幅"数据已过期，请刷新"
5. THE Stale_Indicator SHALL 在横幅中提供"立即刷新"按钮，点击后执行从当前步骤开始的部分链路
6. WHEN 全链路执行完成后，THE Stale_Indicator SHALL 清除所有 stale 标记

### 需求 9：执行历史与审计轨迹

**User Story:** 作为质控人员，我想查看全链路执行的历史记录，以便审计生成操作的完整轨迹。

#### 验收标准

1. THE Chain_Orchestrator SHALL 提供 `GET /api/projects/{pid}/workflow/executions` 端点，返回执行历史列表
2. THE Chain_Orchestrator SHALL 对每条记录包含：execution_id、操作人、开始时间、结束时间、总耗时、各步骤状态、触发方式（手动/自动）
3. THE Chain_Orchestrator SHALL 支持按时间范围和状态筛选
4. THE Chain_Orchestrator SHALL 保留最近 100 条执行记录（超过自动清理最早的）
5. THE Chain_Orchestrator SHALL 在每次导出操作时记录导出日志（导出类型、文件名、操作人、时间）

### 需求 10：批量项目操作

**User Story:** 作为项目经理，我想对多个项目批量执行全链路刷新，以便在年审高峰期快速处理多个项目。

#### 验收标准

1. THE Chain_Orchestrator SHALL 提供 `POST /api/workflow/batch-execute` 端点，接受 `{ project_ids, year, steps }` 参数
2. THE Chain_Orchestrator SHALL 对每个项目独立执行全链路，互不影响
3. THE Chain_Orchestrator SHALL 返回批量执行汇总（成功数/失败数/跳过数）
4. THE Chain_Orchestrator SHALL 支持最多同时处理 10 个项目（超过排队等待）
5. WHEN 某个项目执行失败时，THE Chain_Orchestrator SHALL 继续处理其余项目

### 需求 11：前端一键刷新按钮

**User Story:** 作为审计助理，我想在项目仪表盘有一个醒目的"一键刷新全部"按钮，以便快速触发全链路生成。

#### 验收标准

1. THE 项目仪表盘 SHALL 在工作流进度条右侧显示"🔄 一键刷新全部"主按钮（蓝色实心）
2. WHEN 用户点击按钮时，THE 前端 SHALL 弹出确认对话框显示将执行的步骤列表
3. WHEN 用户确认后，THE 前端 SHALL 调用 Chain_Orchestrator 端点并订阅 SSE 进度流
4. THE 前端 SHALL 在执行过程中将按钮变为"执行中..."状态（禁用+旋转图标）
5. THE 前端 SHALL 在进度条各步骤实时更新状态（灰→蓝旋转→绿勾/红叉）
6. WHEN 执行完成时，THE 前端 SHALL 显示 ElMessage 摘要通知（成功/部分失败/全部失败）
7. WHEN 执行失败时，THE 前端 SHALL 在失败步骤旁显示错误详情（hover tooltip）

### 需求 12：导出对话框

**User Story:** 作为审计助理，我想通过导出对话框选择导出格式和内容，以便灵活控制导出范围。

#### 验收标准

1. THE 导出对话框 SHALL 提供 3 种导出模式：仅报表 Excel / 仅附注 Word / 完整导出包
2. THE 导出对话框 SHALL 在"完整导出包"模式下显示可选项：包含审计报告 / 包含审定表
3. THE 导出对话框 SHALL 在导出前显示一致性检查结果（绿色通过/红色阻断/黄色警告）
4. WHEN 存在 blocking 项时，THE 导出对话框 SHALL 禁用导出按钮并显示"请先修复以下问题"
5. THE 导出对话框 SHALL 提供"强制导出"复选框（仅 admin/partner 角色可见）
6. THE 导出对话框 SHALL 在导出过程中显示进度条（文件生成中...→打包中...→下载中...）
7. THE 导出对话框 SHALL 在导出完成后自动触发浏览器下载

### 需求 13：报表公式覆盖率提升

**User Story:** 作为审计助理，我想让报表生成后大部分行次有数据（而非全部为 0），以便减少手动填写工作量。

#### 验收标准

1. THE ReportEngine SHALL 对资产负债表覆盖率达到 80% 以上（核心科目行全部有公式）
2. THE ReportEngine SHALL 对利润表覆盖率达到 70% 以上（收入/成本/费用核心行全部有公式）
3. THE ReportEngine SHALL 对现金流量表支持间接法自动计算（从净利润调整到经营活动现金流）
4. THE ReportEngine SHALL 对权益变动表支持期末余额行自动取数（从 TB 的 3xxx/4xxx 科目）
5. WHEN 公式计算结果为 0 且该科目在试算表中有余额时，THE ReportEngine SHALL 在 summary 中标记为 warning
6. THE ReportEngine SHALL 在生成结果中返回覆盖率统计（有数据行数/总行数/覆盖率百分比）

### 需求 14：版本对比

**User Story:** 作为质控人员，我想对比调整前后的报表数据变化，以便审核调整分录的影响。

#### 验收标准

1. THE Chain_Orchestrator SHALL 在每次全链路执行前保存当前报表快照（snapshot）
2. THE Chain_Orchestrator SHALL 提供 `GET /api/projects/{pid}/workflow/compare/{execution_id}` 端点
3. THE 对比端点 SHALL 返回每个报表行次的变化：`{ row_code, row_name, before, after, diff, diff_percent }`
4. THE 前端 SHALL 在执行完成后提供"查看变化"按钮，打开对比抽屉
5. THE 对比抽屉 SHALL 用绿色/红色高亮显示增加/减少的金额

### 需求 15：错误恢复与重试

**User Story:** 作为审计助理，我想在全链路执行部分失败后能够重试失败的步骤，以便不必从头开始。

#### 验收标准

1. WHEN 全链路执行部分失败时，THE Chain_Orchestrator SHALL 保留已完成步骤的结果
2. THE Chain_Orchestrator SHALL 提供 `POST /api/projects/{pid}/workflow/retry/{execution_id}` 端点
3. WHEN 调用 retry 时，THE Chain_Orchestrator SHALL 仅重新执行 failed 状态的步骤
4. THE Chain_Orchestrator SHALL 支持最多 3 次自动重试（可配置），每次间隔指数退避
5. IF 3 次重试后仍失败，THEN THE Chain_Orchestrator SHALL 标记为 permanently_failed 并通知操作人

### 需求 16：签字门禁集成

**User Story:** 作为合伙人，我想在签字前确认所有报表和附注已生成且数据一致，以便避免签字后发现数据错误。

#### 验收标准

1. THE GateEngine SHALL 新增 `AllReportsGeneratedRule`：签字前检查 4 张报表均已生成且非 stale
2. THE GateEngine SHALL 新增 `AllNotesGeneratedRule`：签字前检查附注已生成且非 stale
3. THE GateEngine SHALL 新增 `ConsistencyPassedRule`：签字前检查一致性门控全部通过
4. WHEN 签字门禁不通过时，THE 签字面板 SHALL 显示"请先执行全链路刷新"提示并提供快捷按钮
5. THE 签字门禁 SHALL 注册到 sign_off 和 export_package 两个 GateType

### 需求 17：EQCR 只读访问

**User Story:** 作为独立复核合伙人，我想以只读方式查看生成的报表和附注，以便进行独立复核。

#### 验收标准

1. WHEN 用户角色为 eqcr 时，THE 报表页面 SHALL 隐藏"生成"和"刷新"按钮
2. WHEN 用户角色为 eqcr 时，THE 附注页面 SHALL 隐藏编辑功能
3. THE EQCR 工作台 SHALL 显示报表/附注的最后生成时间和操作人
4. THE EQCR 工作台 SHALL 提供"导出只读副本"按钮（导出的 Excel/Word 带水印"仅供复核"）



---

## 第二部分：报表模块修复与增强

### 需求 18：报表表样完整生成（未审/审定双模式）

**User Story:** 作为审计助理，我想在导入账套数据后立即看到完整的未审报表表样（含所有行次和金额），以便开始审计工作。

#### 验收标准

1. THE ReportEngine SHALL 支持两种生成模式：`unadjusted`（未审报表，取 TB 未审数）和 `audited`（审定报表，取 TB 审定数）
2. WHEN 生成未审报表时，THE ReportEngine SHALL 使用 `trial_balance.unadjusted_amount` 作为取数来源
3. WHEN 生成审定报表时，THE ReportEngine SHALL 使用 `trial_balance.audited_amount` 作为取数来源
4. THE ReportEngine SHALL 对资产负债表覆盖率达到 95% 以上（所有标准科目行均有公式或 fallback 取数）
5. THE ReportEngine SHALL 对利润表覆盖率达到 90% 以上
6. THE ReportEngine SHALL 对现金流量表支持间接法自动计算（从净利润出发，调整非现金项目）
7. THE ReportEngine SHALL 对权益变动表支持期末余额行自动取数（3xxx/4xxx 科目）
8. WHEN 某行次公式计算结果为 0 但该科目在 TB 中有余额时，THE ReportEngine SHALL 使用 TB 余额作为 fallback
9. THE ReportEngine SHALL 在生成结果中返回覆盖率统计（有数据行数/总行数/覆盖率百分比）
10. THE 前端 ReportView SHALL 支持"未审"/"已审"/"对比"三种模式切换，对比模式同时显示未审数和审定数

### 需求 19：报表前端表样呈现

**User Story:** 作为审计助理，我想看到格式规范的财务报表（含缩进、合计行、千分位），以便直观理解报表结构。

#### 验收标准

1. THE ReportView SHALL 按 report_config 的 indent_level 设置行缩进（每级 24px padding-left）
2. THE ReportView SHALL 对合计行（is_total_row=true）设置加粗字体 + 上边框分隔线
3. THE ReportView SHALL 对标题行（无金额的分类行）设置加粗 + 背景色 #f0edf5
4. THE ReportView SHALL 对金额列使用 Arial Narrow 字体 + 千分位格式 + 右对齐 + tabular-nums
5. THE ReportView SHALL 对负数金额显示红色 + 括号格式 `(1,234.56)`
6. THE ReportView SHALL 对零值行显示灰色文字（区分"有数据=0"和"无数据"）
7. THE ReportView SHALL 在表格顶部显示致同标准表头：公司名称（居中）、报表期间、金额单位
8. THE ReportView SHALL 支持行点击穿透到试算表对应科目
9. THE ReportView SHALL 在空报表时显示友好提示"请先导入账套数据并执行刷新"

### 需求 20：报表公式引擎完善

**User Story:** 作为管理员，我想让报表公式覆盖所有标准行次，以便生成后大部分行次有数据。

#### 验收标准

1. THE ReportEngine SHALL 对 report_config 中无公式的行自动生成 fallback 公式：按 row_code 前缀匹配 TB 科目编码
2. THE ReportEngine SHALL 对合计行自动生成 SUM_ROW 公式（汇总其下所有子行）
3. THE ReportEngine SHALL 支持 CFS 间接法公式：净利润 + 折旧摊销 + 资产减值 + 处置损益 + 财务费用 + 存货变动 + 经营性应收变动 + 经营性应付变动
4. THE ReportEngine SHALL 支持 EQ 变动表公式：期初余额 = 上年期末余额、本年增减 = 本年利润 + 其他综合收益、期末余额 = 期初 + 增减
5. THE ReportEngine SHALL 在公式执行失败时记录 warning 而非抛异常（容错处理）
6. THE ReportEngine SHALL 支持公式调试模式（返回每行的公式文本 + 代入值 + 计算过程）

---

## 第三部分：附注模块修复与增强

### 需求 21：附注模板体系（4 套模板）

**User Story:** 作为审计助理，我想根据项目类型（国企/上市 × 合并/单体）自动选择正确的附注模板，以便生成符合规范的附注。

#### 验收标准

1. THE DisclosureEngine SHALL 以 `附注模版/` 目录下的 MD 文件为附注生成的唯一模板真源（不使用 `审计报告模板/` 下的 docx 附注文件，后者仅作为最终 Word 导出的格式参考）
2. THE DisclosureEngine SHALL 支持 4 套附注模板：国企合并（`国企报表附注.md` 303KB）、国企单体（`国企报表附注_单体.md` 285KB）、上市合并（`上市报表附注.md` 519KB）、上市单体（`上市报表附注_单体.md` 516KB）
3. THE DisclosureEngine SHALL 根据项目的 `template_type`（soe/listed）和 `report_scope`（consolidated/standalone）自动选择对应模板
4. THE DisclosureEngine SHALL 解析 MD 模板中的章节结构（标题层级、表格定义、文本模板、占位符、蓝色/红色指引文字）
5. THE DisclosureEngine SHALL 从 MD 模板中提取表格列定义（列名、对齐方式、数据类型）
6. THE DisclosureEngine SHALL 保留模板中的格式说明（仿宋_GB2312 小四、Arial Narrow 数字、页边距左3/右3.18/上3.2/下2.54）供 Word 导出使用
7. THE DisclosureEngine SHALL 支持模板热加载（修改 MD 文件后无需重启即可生效）
8. THE DisclosureEngine SHALL 在生成时自动删除蓝色指引文字（括号内标注），保留黑色正文和红色待填充项

### 需求 22：附注校验公式引擎

**User Story:** 作为审计助理，我想让系统自动校验附注数据与报表数据的一致性，以便发现数据错误。

#### 验收标准

1. THE DisclosureEngine SHALL 加载校验公式预设（`国企版校验公式预设.md` / `上市版校验公式预设.md`）
2. THE DisclosureEngine SHALL 支持以下校验类型：
   - `余额`：报表科目余额 vs 附注表格合计行
   - `宽表`：横向公式（期初 ± 变动 = 期末）
   - `纵向`：多段表纵向勾稽（原值 - 折旧 - 减值 = 账面价值）
   - `交叉`：同科目多表之间金额核对
   - `跨科目`：不同科目之间金额核对
   - `其中项`：明细行之和 = 合计行
   - `二级明细`：报表二级子明细行 vs 附注明细表
   - `完整性`：数据行非空完整性校验
   - `LLM审核`：需调用 LLM 对文本内容进行合理性判断
3. THE DisclosureEngine SHALL 遵循互斥规则：`[余额]` 不与 `[其中项]`/`[宽表]` 共存
4. THE DisclosureEngine SHALL 对其中项校验采用通用规则：`sum(合计行以外的所有明细行) = 合计行`，不硬编码子项名称
5. THE DisclosureEngine SHALL 支持账龄衔接校验：本期某账龄段金额 ≤ 上期前一账龄段金额
6. THE DisclosureEngine SHALL 在校验完成后返回每条规则的通过/失败状态和差异金额
7. THE DisclosureEngine SHALL 将校验结果持久化，支持前端展示和历史查询

### 需求 23：附注科目对照映射

**User Story:** 作为审计助理，我想让系统自动将报表科目映射到附注章节，以便附注数据自动从报表取数。

#### 验收标准

1. THE DisclosureEngine SHALL 加载科目对照模板（`国企版科目对照模板.md` / `上市版科目对照模板.md`）
2. THE DisclosureEngine SHALL 建立报表行次 → 附注章节 → 表格的三级映射关系
3. THE DisclosureEngine SHALL 对每个表格标注校验角色（余额/宽表/交叉/其中项/描述）
4. THE DisclosureEngine SHALL 支持从报表行次自动取数填充附注表格的合计行
5. THE DisclosureEngine SHALL 支持从试算表明细科目取数填充附注表格的明细行
6. THE DisclosureEngine SHALL 在映射关系变更时自动标记受影响的附注章节为 stale

### 需求 24：附注宽表公式预设

**User Story:** 作为审计助理，我想让附注中的宽表（如固定资产变动表）自动计算横向公式，以便减少手动计算。

#### 验收标准

1. THE DisclosureEngine SHALL 加载宽表公式预设（`国企版宽表公式预设.md` / `上市版宽表公式预设.md`）
2. THE DisclosureEngine SHALL 对宽表自动执行横向公式：期初余额 + 本期增加 - 本期减少 = 期末余额
3. THE DisclosureEngine SHALL 对宽表合计行自动执行纵向汇总：各明细行之和 = 合计行
4. THE DisclosureEngine SHALL 在横向公式不平衡时标记 warning 并显示差异金额
5. THE DisclosureEngine SHALL 支持用户手动覆盖公式计算结果（标记为"手动调整"）

### 需求 25：附注数据填充引擎

**User Story:** 作为审计助理，我想在生成附注后看到大部分表格已自动填充数据，以便只需补充少量手动信息。

#### 验收标准

1. THE DisclosureEngine SHALL 从试算表自动填充附注表格的期末余额列
2. THE DisclosureEngine SHALL 从上年试算表自动填充附注表格的期初余额列
3. THE DisclosureEngine SHALL 从调整分录自动填充附注表格的本期变动列（增加/减少）
4. THE DisclosureEngine SHALL 从底稿审定表自动填充附注表格的明细行数据
5. THE DisclosureEngine SHALL 对无法自动填充的单元格标记为"待填写"（黄色背景）
6. THE DisclosureEngine SHALL 在填充完成后返回填充率统计（已填充单元格数/总单元格数/填充率百分比）
7. THE DisclosureEngine SHALL 支持增量刷新（仅更新上游数据变更影响的单元格）

### 需求 26：附注前端编辑体验

**User Story:** 作为审计助理，我想在附注编辑器中直观地编辑表格数据和文本内容，以便高效完成附注编制。

#### 验收标准

1. THE DisclosureEditor SHALL 对每个附注章节显示：章节标题 + 文本内容 + 表格数据
2. THE DisclosureEditor SHALL 对表格使用 el-table 展示，支持单元格编辑（双击进入编辑模式）
3. THE DisclosureEditor SHALL 对金额单元格使用 Arial Narrow 字体 + 千分位 + 右对齐
4. THE DisclosureEditor SHALL 对自动填充的单元格显示浅蓝色背景标记（区分手动输入）
5. THE DisclosureEditor SHALL 对校验失败的单元格显示红色边框 + tooltip 显示差异
6. THE DisclosureEditor SHALL 支持"从报表刷新"按钮，一键更新所有自动填充的数据
7. THE DisclosureEditor SHALL 在左侧目录树中对有校验错误的章节显示红色标记
8. THE DisclosureEditor SHALL 支持章节折叠/展开，默认展开当前编辑的章节

### 需求 27：附注 Word 导出致同格式

**User Story:** 作为审计助理，我想将附注导出为完全符合致同格式标准的 Word 文档，以便直接用于审计报告。

#### 验收标准

1. THE Note_Word_Exporter SHALL 使用致同标准页面设置：A4、左 3cm/右 3.18cm/上 3.2cm/下 2.54cm、页眉 1.3cm/页脚 1.3cm
2. THE Note_Word_Exporter SHALL 使用致同标准字体：中文仿宋_GB2312 小四、数字 Arial Narrow
3. THE Note_Word_Exporter SHALL 使用致同标准标题层级：一级"一、二、三..."加粗、二级"（一）（二）..."、三级"1. 2. 3."
4. THE Note_Word_Exporter SHALL 使用致同标准表格样式：上下边框 1 磅、标题行下边框 1/2 磅、标题行加粗居中、数据行金额右对齐
5. THE Note_Word_Exporter SHALL 使用致同标准段落格式：段前 0 行/段后 0.9 行、单倍行距、标题行左缩进 -2 字符
6. THE Note_Word_Exporter SHALL 对空数据章节生成"本期无此项业务"占位文本
7. THE Note_Word_Exporter SHALL 在文档开头生成目录（TOC 域代码）
8. THE Note_Word_Exporter SHALL 在页脚添加页码"第 X 页 共 Y 页"
9. THE Note_Word_Exporter SHALL 对"本期无此项业务"的章节在导出时可选择跳过（参数 skip_empty=true）
10. THE Note_Word_Exporter SHALL 支持导出前预览（返回 HTML 格式预览，不生成 docx）


---

## 第四部分：全局联动与平台级优化

### 需求 28：四表→报表→底稿→附注全链路穿透

**User Story:** 作为审计助理，我想从任何一个数据点出发，沿着完整的审计链路穿透到上下游数据，以便快速追溯数据来源和影响范围。

#### 验收标准

1. THE 穿透引擎 SHALL 支持以下完整链路（双向）：
   - 科目余额表 ↔ 序时账 ↔ 凭证（已实现）
   - 科目余额表 → 试算表 → 报表行次 → 附注章节（正向）
   - 附注章节 → 报表行次 → 试算表 → 科目余额表（反向）
   - 报表行次 → 底稿审定表 → 调整分录（正向）
   - 调整分录 → 试算表 → 报表 → 附注（影响范围）
2. THE 穿透引擎 SHALL 在每个穿透节点显示当前值和来源说明（如"来自 TB 科目 1122 期末余额"）
3. THE 前端 SHALL 在报表行次右键菜单提供"查看附注"/"查看底稿"/"查看明细"三个穿透入口
4. THE 前端 SHALL 在附注表格单元格右键菜单提供"溯源到报表"/"溯源到试算表"穿透入口
5. THE 前端 SHALL 在穿透跳转时自动 push 到 NavigationStack（支持 Backspace 返回）
6. THE 穿透引擎 SHALL 支持"影响分析"模式：给定一个调整分录，列出所有受影响的报表行次和附注章节

### 需求 29：全局数据一致性实时监控

**User Story:** 作为项目经理，我想实时看到项目内各模块数据是否一致，以便及时发现和修复数据断裂。

#### 验收标准

1. THE 一致性监控 SHALL 在项目仪表盘显示"数据健康度"指标（0-100 分）
2. THE 一致性监控 SHALL 检查以下 8 项一致性：
   - TB 借贷平衡（资产 = 负债 + 权益）
   - 报表 BS 平衡（资产合计 = 负债+权益合计）
   - 报表 IS 勾稽（收入-成本-费用+营业外 = 净利润）
   - TB 审定数 vs 报表金额一致
   - 报表金额 vs 附注合计行一致
   - 底稿审定数 vs TB 审定数一致
   - 调整分录借贷平衡
   - 附注期初数 vs 上年期末数一致
3. THE 一致性监控 SHALL 对每项检查显示通过/警告/失败状态
4. THE 一致性监控 SHALL 在检查失败时提供"一键修复"建议（如"请重新执行全链路刷新"）
5. THE 一致性监控 SHALL 支持定时自动检查（每次保存操作后 + 每 30 分钟定时）

### 需求 30：报表与附注联动编辑

**User Story:** 作为审计助理，我想在修改报表数据后自动看到附注中对应章节的数据同步更新，以便保持报表与附注的一致性。

#### 验收标准

1. WHEN 报表行次金额变更时，THE 联动引擎 SHALL 自动标记对应附注章节为 stale
2. WHEN 附注章节标记为 stale 时，THE 前端 SHALL 在附注目录树中显示橙色标记
3. THE 联动引擎 SHALL 提供"同步到附注"按钮，一键将报表最新数据刷新到所有关联附注章节的合计行
4. THE 联动引擎 SHALL 在同步时保留用户手动编辑的明细行数据（只更新合计行和公式驱动的单元格）
5. THE 联动引擎 SHALL 在同步完成后自动执行附注校验公式，标记不一致项

### 需求 31：项目级配置中心

**User Story:** 作为项目经理，我想在一个地方集中配置项目的报表标准、附注模板、导出格式等参数，以便统一管理项目设置。

#### 验收标准

1. THE 项目配置中心 SHALL 在项目设置页提供以下配置项：
   - 报表标准（国企版/上市版）
   - 报表范围（合并/单体）
   - 金额单位（元/万元/千元）
   - 附注模板类型（自动跟随报表标准/手动指定）
   - 导出格式偏好（报表含上年对比列/附注跳过空章节/审计报告意见类型）
2. THE 项目配置中心 SHALL 在配置变更时自动标记受影响的产物为 stale
3. THE 项目配置中心 SHALL 支持从其他项目复制配置（"继承上年配置"）
4. THE 项目配置中心 SHALL 在报表标准变更时提示"将重新生成全部报表和附注，是否继续？"

### 需求 32：导出文件命名规范

**User Story:** 作为合伙人，我想导出的文件按致同标准命名，以便归档时无需手动重命名。

#### 验收标准

1. THE Export_Package SHALL 使用以下命名规范：
   - 报表：`{公司简称}_{年度}年度财务报表.xlsx`
   - 附注：`{公司简称}_{年度}年度财务报表附注.docx`
   - 审计报告：`{公司简称}_{年度}年度审计报告.docx`
   - 组合包：`{公司简称}_{年度}年度审计终稿.zip`
2. THE Export_Package SHALL 从项目配置中读取公司简称（`project.client_name` 的前 4 个汉字或全称）
3. THE Export_Package SHALL 支持自定义文件名前缀（如加入事务所编号）
4. THE Export_Package SHALL 在文件名中避免特殊字符（替换 `/\:*?"<>|` 为下划线）

### 需求 33：多年度对比支持

**User Story:** 作为审计助理，我想在报表和附注中同时展示本年和上年数据，以便进行年度对比分析。

#### 验收标准

1. THE ReportEngine SHALL 在生成报表时自动填充"上年同期"列（从上年 financial_report 或上年 TB 取数）
2. THE ReportView SHALL 在对比模式下显示 3 列：本年未审数 / 本年审定数 / 上年审定数
3. THE ReportView SHALL 在对比模式下计算并显示变动额和变动率（变动率 >20% 标红）
4. THE DisclosureEngine SHALL 在附注表格中自动填充"期初余额"列（从上年数据取数）
5. THE DisclosureEngine SHALL 支持"连续审计"模式（同项目多年度）和"首次承接"模式（手动填写期初）
6. WHEN 上年数据不存在时，THE 系统 SHALL 在期初列显示"-"并提示"首次承接，请手动填写期初数"

### 需求 34：前端全局组件统一

**User Story:** 作为开发者，我想让所有页面使用统一的组件和样式，以便维护一致的用户体验。

#### 验收标准

1. THE 前端 SHALL 对所有金额展示统一使用 GtAmountCell 组件（当前仅 8/86 视图使用）
2. THE 前端 SHALL 对所有表格统一使用 el-table + 致同表头样式（#f0edf5 背景 + #4b2d77 文字）
3. THE 前端 SHALL 对所有空状态统一使用 GtEmpty 组件（含图标 + 标题 + 描述 + 操作按钮）
4. THE 前端 SHALL 对所有加载状态统一使用 el-skeleton（表格用 rows=5，卡片用 rows=2）
5. THE 前端 SHALL 对所有错误处理统一使用 handleApiError（当前仍有 11 处裸 ElMessage.error）
6. THE 前端 SHALL 对所有分页统一使用标准分页组件（左侧 page-size + 右侧页码 + jumper）
7. THE 前端 SHALL 对所有数字列统一使用 `.gt-amt` class（Arial Narrow + nowrap + tabular-nums）


### 需求 35：附注通用规则引擎（模板为参考，实际按企业情况填充）

**User Story:** 作为审计助理，我想让系统根据企业实际科目数据智能决定附注中哪些章节需要披露、哪些表格需要填充，而非机械地照搬模板全部章节。

#### 验收标准

1. THE DisclosureEngine SHALL 将 MD 模板视为"参考框架"而非"必须全部生成"——仅对企业实际有余额的科目生成对应附注章节
2. THE DisclosureEngine SHALL 通过以下通用规则自动判断章节是否需要生成：
   - 规则 A（余额驱动）：报表行次金额 ≠ 0 → 生成对应附注章节
   - 规则 B（变动驱动）：本期与上期金额差异 > 重要性水平 × 5% → 生成变动分析段落
   - 规则 C（底稿驱动）：对应底稿已编制且有审定数 → 从底稿取数填充附注明细
   - 规则 D（政策驱动）：会计政策章节始终生成（不依赖余额）
   - 规则 E（关联方驱动）：关联方交易/余额 > 0 → 生成关联方披露章节
3. THE DisclosureEngine SHALL 对未触发任何规则的章节标记为"本期无此项业务"（不生成空表格）
4. THE DisclosureEngine SHALL 支持用户手动添加/删除章节（覆盖自动判断结果）
5. THE DisclosureEngine SHALL 在生成摘要中显示：自动生成 X 章节 / 跳过 Y 章节 / 待手动补充 Z 章节

### 需求 36：附注与底稿联动取数

**User Story:** 作为审计助理，我想让附注表格的明细数据直接从对应底稿的审定表中取数，以便保持底稿与附注数据一致。

#### 验收标准

1. THE DisclosureEngine SHALL 建立附注章节 → 底稿编码的映射关系（如"货币资金"附注 → E1 底稿审定表）
2. THE DisclosureEngine SHALL 从底稿 parsed_data 或 xlsx 审定表中提取明细行数据填充附注表格
3. THE DisclosureEngine SHALL 支持以下取数模式：
   - 模式 1（合计取数）：从底稿审定表的合计行取期末/期初余额 → 填入附注合计行
   - 模式 2（明细取数）：从底稿审定表的明细行逐行取数 → 填入附注明细表
   - 模式 3（分类取数）：从底稿按类别汇总 → 填入附注分类表（如按账龄/按性质）
   - 模式 4（变动取数）：从底稿的本期增加/减少列 → 填入附注变动表
4. THE DisclosureEngine SHALL 在底稿数据变更时自动标记关联附注章节为 stale
5. THE DisclosureEngine SHALL 支持"从底稿刷新"操作，一键将所有底稿最新数据同步到附注
6. THE DisclosureEngine SHALL 对无法从底稿取数的单元格（如文字描述、会计政策说明）保留为用户手动填写
7. THE DisclosureEngine SHALL 在取数完成后显示取数覆盖率（自动填充单元格数 / 总数值单元格数）

### 需求 37：附注智能裁剪与排序

**User Story:** 作为项目经理，我想让附注章节按企业实际情况自动裁剪和排序，以便生成的附注简洁且符合披露要求。

#### 验收标准

1. THE DisclosureEngine SHALL 根据报表行次的实际金额自动排序附注章节（金额大的科目排前面，或按报表行次顺序）
2. THE DisclosureEngine SHALL 自动合并金额较小的同类科目到"其他"章节（金额 < 重要性水平 × 1% 的科目）
3. THE DisclosureEngine SHALL 对合并/单体报表自动裁剪不适用的章节（如单体报表不需要"合并范围变更"章节）
4. THE DisclosureEngine SHALL 支持用户手动调整章节顺序（拖拽排序）
5. THE DisclosureEngine SHALL 在裁剪后自动重新编号章节序号（一、二、三...）
6. THE DisclosureEngine SHALL 保留"必披露"章节不被裁剪（如会计政策、关联方、期后事项，即使金额为 0）


### 需求 38：附注表格结构手动编辑

**User Story:** 作为审计助理，我想手动调整附注表格的行列结构（增删行列、修改列名、调整列宽），以便适配企业实际披露需求。

#### 验收标准

1. THE DisclosureEditor SHALL 支持对附注表格执行以下结构编辑操作：
   - 新增行（在指定位置插入空行）
   - 删除行（删除选中行，合计行不可删除）
   - 新增列（在指定位置插入空列，需指定列名和数据类型）
   - 删除列（删除选中列，保护"项目"列不可删除）
   - 修改列名（双击列头编辑）
   - 调整列宽（拖拽列边框）
   - 调整列顺序（拖拽列头排序）
2. THE DisclosureEditor SHALL 在结构编辑后自动重新计算合计行公式
3. THE DisclosureEditor SHALL 对结构编辑操作支持撤销/重做（Ctrl+Z / Ctrl+Y）
4. THE DisclosureEditor SHALL 在结构变更时保留已填充的数据（新增列数据为空，删除列数据丢失需二次确认）
5. THE DisclosureEditor SHALL 将表格结构变更持久化到数据库（不影响原始模板，仅影响当前项目的附注实例）
6. THE DisclosureEditor SHALL 支持"恢复模板结构"操作（重置为模板默认结构，已填数据保留匹配列）

### 需求 39：附注与公式管理联动

**User Story:** 作为审计助理，我想让附注表格中的公式与全局公式管理中心联动，以便统一维护取数规则。

#### 验收标准

1. THE DisclosureEngine SHALL 对附注表格中的每个数值单元格支持绑定公式（如 `TB('1001','期末余额')`、`WP('E1','审定数')`、`REPORT('BS','BS-001')`）
2. THE DisclosureEditor SHALL 在单元格右键菜单提供"编辑公式"/"清除公式"/"查看公式来源"操作
3. THE DisclosureEditor SHALL 对有公式绑定的单元格显示蓝色三角标记（hover 显示公式文本）
4. THE DisclosureEngine SHALL 在全链路刷新时按公式重新计算所有绑定单元格的值
5. THE DisclosureEngine SHALL 支持从公式管理中心（`prefill_formula_mapping.json`）批量导入附注公式配置
6. THE DisclosureEngine SHALL 在公式计算失败时保留上次有效值并标记 warning（不清空单元格）
7. THE DisclosureEditor SHALL 支持"公式审计"视图：一键显示所有有公式的单元格及其当前值/公式/来源

### 需求 40：附注与全局枚举联动

**User Story:** 作为审计助理，我想让附注表格中的分类列（如账龄段、核算方法）直接引用全局枚举字典，以便保持分类标准一致。

#### 验收标准

1. THE DisclosureEngine SHALL 支持表格列绑定全局枚举字典，绑定后该列单元格显示为下拉选择（而非自由文本）
2. THE DisclosureEngine SHALL 预置以下附注常用枚举：
   - `aging_period`：账龄分段（1年以内/1至2年/2至3年/3至4年/4至5年/5年以上）
   - `aging_period_3`：3段账龄（1年以内/1至2年/2至3年/3年以上）
   - `yes_no`：是否（是/否）
   - `investment_method`：核算方法（成本法/权益法）
   - `impairment_sign`：减值迹象（有/无）
   - `currency`：币种（人民币/美元/欧元/港币/日元）
   - `guarantee_type`：担保类型（抵押/质押/保证/信用）
   - `related_party_type`：关联方类型（母公司/子公司/联营/合营/关键管理人员/其他）
   - `lease_type`：租赁类型（经营租赁/融资租赁）
   - `fair_value_level`：公允价值层级（第一层次/第二层次/第三层次）
3. THE DisclosureEditor SHALL 在列头右键菜单提供"绑定枚举"操作（从全局枚举字典列表中选择）
4. THE DisclosureEditor SHALL 对已绑定枚举的列，新增行时自动显示下拉选择器
5. THE DisclosureEngine SHALL 在校验时检查枚举列的值是否在有效枚举范围内（无效值标记 warning）
6. THE DisclosureEngine SHALL 支持枚举值变更时自动更新所有引用该枚举的附注表格（如账龄段从 5 段改为 3 段时提示用户合并数据）
7. THE DisclosureEditor SHALL 支持用户在当前项目临时扩展枚举值（不影响全局枚举，仅当前项目有效）


---

## 第五部分：用户体验与上线保障

### 需求 41：附注打印预览与分页控制

**User Story:** 作为审计助理，我想在导出 Word 前预览附注的打印效果，以便确认分页位置和表格跨页处理是否合理。

#### 验收标准

1. THE DisclosureEditor SHALL 提供"打印预览"模式（切换到 A4 页面视图，显示分页线）
2. THE Note_Word_Exporter SHALL 对跨页表格自动重复表头行（Word 表格属性"在各页顶端以标题行形式重复出现"）
3. THE Note_Word_Exporter SHALL 避免表格最后一行单独出现在下一页（孤行控制：表格至少保留 2 行在同一页）
4. THE Note_Word_Exporter SHALL 对章节标题与其后内容保持同页（段前分页控制：标题不出现在页底）
5. THE Note_Word_Exporter SHALL 支持用户手动插入分页符（在指定章节前强制分页）

### 需求 42：报表与附注交叉引用自动生成

**User Story:** 作为审计助理，我想让附注中引用报表行次时自动生成正确的交叉引用文字（如"详见附注五、（三）"），以便减少手动核对。

#### 验收标准

1. THE DisclosureEngine SHALL 在报表行次的"附注编号"列自动填入对应附注章节的序号
2. THE DisclosureEngine SHALL 在附注文本中的 `{ref:BS-001}` 占位符自动替换为"详见附注五、（一）1"格式
3. THE DisclosureEngine SHALL 在章节顺序调整后自动更新所有交叉引用编号
4. THE Note_Word_Exporter SHALL 在 Word 导出时将交叉引用生成为 Word 书签+REF 域（支持自动更新）
5. THE Report_Excel_Exporter SHALL 在报表 Excel 的"附注编号"列填入对应章节序号

### 需求 43：附注变动分析自动生成

**User Story:** 作为审计助理，我想让系统自动生成附注中的变动分析文字（如"本期增加系因..."），以便减少手动编写工作量。

#### 验收标准

1. THE DisclosureEngine SHALL 对变动率 > 20% 的科目自动生成变动分析段落模板
2. THE DisclosureEngine SHALL 使用以下模板生成变动分析文字：
   - 增加模板："{科目名称}本期末较上期末增加{金额}元（增幅{百分比}%），主要系{原因占位}所致。"
   - 减少模板："{科目名称}本期末较上期末减少{金额}元（降幅{百分比}%），主要系{原因占位}所致。"
3. THE DisclosureEngine SHALL 将 `{原因占位}` 标记为待填写（黄色高亮），由用户手动补充具体原因
4. THE DisclosureEngine SHALL 支持从底稿的审计说明中提取变动原因（如底稿已有 AI 生成的变动分析）
5. THE DisclosureEngine SHALL 对变动率 ≤ 20% 的科目不生成变动分析（除非用户手动要求）

### 需求 44：多人协作与锁定机制

**User Story:** 作为项目经理，我想让多个审计助理同时编辑不同附注章节而不互相冲突，以便提高团队协作效率。

#### 验收标准

1. THE DisclosureEditor SHALL 支持章节级锁定（用户编辑某章节时，其他用户该章节显示为只读）
2. THE DisclosureEditor SHALL 在章节被锁定时显示锁定人姓名和锁定时间
3. THE DisclosureEditor SHALL 支持锁定自动释放（离开页面/5 分钟无操作/关闭浏览器）
4. THE DisclosureEditor SHALL 允许项目经理强制解锁（覆盖他人锁定）
5. THE DisclosureEditor SHALL 在保存时检查版本冲突（乐观锁：如果他人在此期间修改了同一章节，提示冲突）
6. THE DisclosureEditor SHALL 支持"我的待编章节"筛选（只显示分配给当前用户的章节）

### 需求 45：附注完成度追踪

**User Story:** 作为项目经理，我想看到附注各章节的完成状态，以便掌握附注编制进度。

#### 验收标准

1. THE DisclosureEditor SHALL 对每个章节显示完成状态：未开始 / 自动填充 / 编辑中 / 已完成 / 已复核
2. THE DisclosureEditor SHALL 在左侧目录树中用颜色区分状态（灰/蓝/黄/绿/紫）
3. THE DisclosureEditor SHALL 在顶部显示整体完成度进度条（已完成章节数/需披露章节数）
4. THE DisclosureEditor SHALL 支持"标记为已完成"操作（用户确认该章节数据正确）
5. THE DisclosureEditor SHALL 在全部章节标记为已完成后，启用"导出"按钮（否则导出时提示"尚有 X 章节未完成"）
6. THE DisclosureEditor SHALL 支持按负责人筛选章节（项目经理分配不同章节给不同助理）


### 需求 46：附注内容分层处理策略

**User Story:** 作为审计助理，我想让系统根据附注内容类型（政策文字/科目注释表格/补充信息）采用不同的处理策略，以便每类内容都得到恰当处理。

#### 验收标准

1. THE DisclosureEngine SHALL 将附注内容分为以下 5 个层级，每层采用不同处理策略：

   **层级 A — 会计政策与基本信息（纯文字，模板驱动）**
   - 范围：公司基本情况、编制基础、遵循声明、重要会计政策（合并/收入确认/金融工具/租赁/减值等）
   - 策略：从模板复制文字框架 → 用户根据企业实际情况修改删减 → 不与底稿联动
   - 自动化：仅替换占位符（公司名称/年度/币种等），其余由用户手动编辑

   **层级 B — 财务报表主要项目注释（表格+文字，底稿联动核心）**
   - 范围：`# 财务报表主要项目注释` 章节下的所有科目（货币资金/应收账款/存货/固定资产/收入/费用等）
   - 策略：从底稿审定表取数填充表格 → 从试算表取合计行 → 自动生成变动分析文字 → 执行校验公式
   - 自动化：表格数据 90%+ 自动填充，变动分析文字模板化生成（原因由用户补充）

   **层级 C — 母公司报表主要项目附注（表格，底稿联动）**
   - 范围：`# 母公司财务报表的主要项目附注` 章节（应收账款/其他应收款/长期股权投资/收入/投资收益等）
   - 策略：与层级 B 相同，但取数来源为母公司单体试算表（非合并）
   - 自动化：仅在合并报表项目中生成，单体报表项目跳过此层级

   **层级 D — 补充信息与披露（混合，部分联动）**
   - 范围：关联方关系及交易、或有事项、期后事项、其他重要事项、母公司所有者权益变动表补充信息
   - 策略：关联方从底稿取数 → 或有事项/期后事项从底稿 A11/A12 取数 → 其他由用户手动编写
   - 自动化：约 50% 可自动填充（关联方交易表/余额表），50% 需手动

   **层级 E — 附录与索引（自动生成）**
   - 范围：附注章节索引、报表科目与附注对照表
   - 策略：全自动生成（从已生成的章节列表和报表行次映射自动构建）
   - 自动化：100%

2. THE DisclosureEngine SHALL 在生成时按层级顺序处理：E（索引）→ A（政策）→ B（合并科目注释）→ C（母公司注释）→ D（补充信息）
3. THE DisclosureEditor SHALL 在左侧目录树中用不同图标区分层级（A=📝文字 B=📊表格 C=📊表格 D=📋混合 E=📑索引）
4. THE DisclosureEditor SHALL 对层级 B/C 的表格章节显示"从底稿刷新"按钮，对层级 A/D 不显示（纯手动编辑）
5. THE DisclosureEngine SHALL 在生成摘要中按层级统计：A 层 X 章节（手动）/ B 层 Y 章节（自动填充率 Z%）/ C 层.../ D 层.../ E 层（全自动）
6. THE DisclosureEngine SHALL 对层级 B 的每个科目注释章节，自动建立与对应底稿编码的映射（如"货币资金"→ E1、"应收账款"→ D2、"存货"→ F2、"固定资产"→ H1）
7. THE DisclosureEngine SHALL 对层级 B/C 中无对应底稿的科目（如企业未编制该底稿），标记为"待手动填写"并在目录树显示黄色标记


### 需求 47：国企版与上市版互转

**User Story:** 作为项目经理，我想在项目中途切换报表标准（如从国企版转为上市版），以便适应客户上市或改制等业务变化。

#### 验收标准

1. THE 系统 SHALL 提供"报表标准转换"功能入口（项目配置中心 + 报表页面工具栏）
2. THE 系统 SHALL 基于已有转换规则（`审计报告模板/纯报表科目注释/` 目录下的对照模板）执行行次映射转换
3. THE 系统 SHALL 在转换时执行以下操作：
   - 报表行次映射：国企版 row_code → 上市版 row_code（或反向），保留已有金额数据
   - 附注章节映射：国企版章节结构 → 上市版章节结构，保留已填充的表格数据和文字
   - 公式适配：转换后自动更新公式中的 row_code 引用
4. THE 系统 SHALL 在转换前显示影响预览：
   - 将新增 X 个行次/章节（上市版比国企版多的）
   - 将删除 Y 个行次/章节（国企版有但上市版无的）
   - 将保留 Z 个行次/章节（两版共有的）
5. THE 系统 SHALL 对转换操作支持撤销（保留转换前快照，30 天内可回退）
6. THE 系统 SHALL 在转换完成后自动执行全链路刷新（重新生成报表和附注）
7. THE 系统 SHALL 支持合并↔单体转换（合并版含合并范围/内部交易抵消等章节，单体版不含）

### 需求 48：附注文字章节富文本编辑

**User Story:** 作为审计助理，我想用富文本编辑器编辑附注中的文字章节（会计政策/补充信息等），以便直观地调整格式和内容。

#### 验收标准

1. THE DisclosureEditor SHALL 对层级 A/D 的文字章节提供富文本编辑器（非纯文本框）
2. THE 富文本编辑器 SHALL 支持以下格式操作：
   - 标题层级（一级/二级/三级，对应附注标题格式）
   - 加粗/斜体/下划线
   - 有序列表（1. 2. 3.）和无序列表
   - 表格插入（行列可调）
   - 缩进调整
   - 字体颜色（黑色正文/红色待填充/蓝色指引-仅编辑时可见导出时删除）
3. THE 富文本编辑器 SHALL 支持占位符插入（从工具栏选择：{公司名称}/{年度}/{币种}/{报表期间} 等）
4. THE 富文本编辑器 SHALL 对占位符显示为蓝色标签样式（不可编辑内部文字，可整体删除）
5. THE 富文本编辑器 SHALL 支持从 Word 粘贴内容（保留基本格式，清除 Word 特有样式）
6. THE 富文本编辑器 SHALL 支持"查看源码"模式（显示 Markdown 或 HTML 源码，高级用户可直接编辑）
7. THE 富文本编辑器 SHALL 在编辑时实时显示字数统计（当前章节字数/总附注字数）

### 需求 49：附注章节模板可扩展性

**User Story:** 作为管理员，我想能够自定义附注章节模板（新增/修改/删除章节），以便适应不同行业和特殊披露要求。

#### 验收标准

1. THE DisclosureEngine SHALL 支持"自定义章节"功能：用户可在任意位置插入新章节
2. THE 自定义章节 SHALL 支持 3 种内容类型：纯文字 / 纯表格 / 文字+表格混合
3. THE 自定义章节 SHALL 支持指定表格列结构（列名/数据类型/对齐方式/是否绑定枚举）
4. THE 自定义章节 SHALL 支持绑定公式（从试算表/报表/底稿取数）
5. THE 自定义章节 SHALL 支持指定校验规则（余额核对/其中项/宽表等）
6. THE DisclosureEngine SHALL 支持"章节模板库"：将自定义章节保存为模板，供其他项目复用
7. THE DisclosureEngine SHALL 支持"行业模板包"：预置金融/房地产/制造业/零售等行业特有章节
8. THE DisclosureEngine SHALL 在模板升级时（如致同 2026 修订版发布）支持增量合并：保留用户自定义章节，仅更新标准章节

### 需求 50：附注内容可视化与导航

**User Story:** 作为项目经理，我想直观地看到附注的整体结构和各章节状态，以便快速定位需要关注的内容。

#### 验收标准

1. THE DisclosureEditor SHALL 提供"大纲视图"模式：仅显示各章节标题和摘要（首行文字或合计金额），不展开详细内容
2. THE DisclosureEditor SHALL 在大纲视图中对每个章节显示：
   - 内容类型图标（📝文字/📊表格/📋混合）
   - 完成状态色块（灰/蓝/黄/绿/紫）
   - 数据来源标签（自动填充/手动编辑/待填写）
   - 合计金额（表格章节显示期末合计行金额）
   - 校验状态（✅通过/⚠️警告/❌失败）
3. THE DisclosureEditor SHALL 支持"按状态筛选"：只看待填写/只看校验失败/只看已完成
4. THE DisclosureEditor SHALL 支持"按金额排序"：金额大的章节排前面（快速定位重要科目）
5. THE DisclosureEditor SHALL 支持"快速跳转"：输入科目名称或编号直接定位到对应章节
6. THE DisclosureEditor SHALL 支持"折叠全部/展开全部"快捷操作
7. THE DisclosureEditor SHALL 在右侧提供"章节地图"（类似 VS Code 的 minimap），显示整体结构缩略图，点击可快速滚动到对应位置


### 需求 51：上年附注导入与继承

**User Story:** 作为审计助理，我想上传上年附注 Word 文档后，系统自动提取文字内容作为本年附注的基础，以便只需修改变动部分而非从零开始。

#### 验收标准

1. THE DisclosureEngine SHALL 提供"导入上年附注"功能，接受 .docx 文件上传
2. THE DisclosureEngine SHALL 解析上年附注 Word 文档的章节结构（按标题层级拆分为章节）
3. THE DisclosureEngine SHALL 将上年文字内容自动填入本年对应章节的文字区域（按章节标题匹配）
4. THE DisclosureEngine SHALL 对上年数据（金额/日期/年度）自动标记为"待更新"（黄色高亮），提示用户替换为本年数据
5. THE DisclosureEngine SHALL 对上年附注中的表格数据提取到"期初余额"列（作为本年期初数据来源）
6. THE DisclosureEngine SHALL 支持"对比上年"视图：左右分栏显示上年内容和本年内容，差异部分高亮
7. THE DisclosureEngine SHALL 对连续审计项目（同项目多年度），自动从上年项目的附注数据库记录继承文字内容（无需上传文件）
8. THE DisclosureEngine SHALL 在继承时保留上年的自定义章节和用户修改（不被模板覆盖）

### 需求 52：集团模板继承与下发

**User Story:** 作为集团项目经理，我想将集团修改后的附注模板下发给所有子企业项目，以便子企业统一使用集团定制的披露格式。

#### 验收标准

1. THE DisclosureEngine SHALL 支持"集团模板"概念：集团项目可将其附注配置（章节结构+文字内容+表格结构+校验规则）保存为集团模板
2. THE DisclosureEngine SHALL 支持"下发模板"操作：集团项目经理选择子企业项目列表，一键将集团模板应用到所有选中项目
3. THE DisclosureEngine SHALL 在下发时执行以下操作：
   - 层级 A（会计政策）：用集团模板覆盖子企业的政策文字（子企业可在此基础上微调）
   - 层级 B/C（科目注释）：保留子企业自己的数据，仅更新表格结构和校验规则
   - 层级 D（补充信息）：合并集团要求的披露章节（如集团统一的关联方披露格式）
4. THE DisclosureEngine SHALL 支持"参照模板"模式：子企业选择参照某个集团/其他项目的模板，但不强制覆盖（仅作为参考，手动选择性采纳）
5. THE DisclosureEngine SHALL 在集团模板更新时通知所有已下发的子企业项目（"集团模板已更新，是否同步？"）
6. THE DisclosureEngine SHALL 支持子企业"脱离集团模板"操作（独立维护，不再接收集团更新）
7. THE DisclosureEngine SHALL 记录模板继承链路（集团→子企业→孙企业），支持查看"谁在用我的模板"


### 需求 53：报表附注数据锁定与版本快照

**User Story:** 作为合伙人，我想在签字前锁定报表和附注数据（防止签字后被修改），并保留签字时的数据快照用于追溯。

#### 验收标准

1. THE 系统 SHALL 在审计报告签字完成后自动锁定关联的报表和附注数据（不可编辑，不可刷新）
2. THE 系统 SHALL 在锁定时生成数据快照（报表全部行次金额 + 附注全部章节内容的 JSON 快照）
3. THE 系统 SHALL 对锁定后的报表/附注页面显示"🔒 已锁定（签字日期：YYYY-MM-DD）"横幅
4. THE 系统 SHALL 支持"解锁"操作（仅 admin/partner 角色，需填写解锁原因，记录审计日志）
5. THE 系统 SHALL 在解锁后重新编辑并再次锁定时，保留历史快照链（版本 1→版本 2→...）
6. THE 系统 SHALL 支持"查看签字时版本"功能：对比当前数据与签字时快照的差异
7. THE 系统 SHALL 在导出包中附加签字时快照的哈希值（SHA-256），用于验证导出文件与签字时数据一致
