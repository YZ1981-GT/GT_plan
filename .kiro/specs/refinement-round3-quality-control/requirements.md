# Refinement Round 3 — 质控人员视角（规则覆盖 + 抽查手段 + 质量评级）

## 起草契约

**起草视角**：某大型事务所质控（QC）合伙人/经理。不做具体项目执行，负责全所项目的质量抽查、规则库维护、风险项目识别、年度质量评估。本轮围绕"质控如何用系统高效识别问题、抽查项目、对项目组发整改单"展开。

**迭代规则**：参见 [`../refinement-round1-review-closure/README.md`](../refinement-round1-review-closure/README.md)。本轮 Round 3，起草时 Round 1/2 未完成。

## 复盘背景（质控人员视角）

质控的工作模式是"**抽样 + 深度 + 追责**"，和项目经理的"全覆盖 + 快速推进"完全不同。以一名质控经理身份走一遍系统，发现以下问题：

1. **QC 规则硬编码，无法自定义**：`qc_engine.py` 现有 14 条规则（QC-01~14）+ `gate_rules_phase14.py` 的 QC-19~26，全部是 Python 代码。质控想加一条"现金流量表补充资料行间平衡"检查，必须走代码发布。
   - 证据：`backend/app/services/qc_engine.py` 的 `QCRule` 是抽象基类，`register_phase14_rules()` 是硬编码注册；数据库无 `qc_rule_definitions` 表。

2. **无项目级质量评级**：`QCDashboard` 展示项目 QC 通过率，但没有"A/B/C/D"综合评级（考虑风险、规模、经验、复核严谨度），合伙人年度评审时要手工算。
   - 证据：`qc_dashboard_service.py` `get_overview` 只输出通过率数字。

3. **抽查机制缺失**：质控做抽查时需要"随机抽 10% 底稿做深度复核"，系统无抽样工具。
   - 证据：`sampling_service.py` 只服务于项目组对业务样本的抽样（应收/存货等），不服务于质控对底稿的二次抽样。

4. **QC 整改单与项目组问题单混在一起**：质控发的整改单（通常高严重度 + 强制整改）和项目组内部的 review_comment 都用 `IssueTicket`，`source='Q'` 区分但**无专属工作流**（如 48 小时强制响应、逾期升级到合伙人）。
   - 证据：`issue_ticket_service.py` 的 SLA 逻辑只按 `severity` 不按 `source`。

5. **复核人工作量未被审计**：质控想知道"每个二级复核人平均花多长时间、退回率多少、有没有走过场"，系统没提供。`QCDashboard` 人员进度只看数量不看**深度指标**（人均复核时长、平均意见条数、一次通过率）。

6. **历史项目无法对比**：质控想对比"该客户连续 3 年的审计质量趋势"，无入口。
   - 证据：`Project` 表无年度串联字段，`prior_year_entry_id` 只在合并模块用。

7. **规则引擎无"试运行"能力**：质控想在发布新规则前看"这条规则会命中多少底稿"，无 dry-run 接口。
   - 证据：`qc_engine.py` 只能对单底稿 check，无批量预览。

8. **无知识库沉淀失败案例**：`KnowledgeBase` 页面存在但定位模糊；质控想把"本季度典型问题"变成可搜索案例库，系统不支持关联底稿/错报作为教材。

9. **年度质量报告缺失**：质控每年要向事务所管理层出"本所项目质量年报"，系统无此导出能力。

10. **规则注释与准则编号无映射**：`QC-01~26` 内部编号与《审计准则》1101/1211/1301 等外部编号无对照表，合伙人一旦问"这是违反哪条准则"答不上来。
    - 证据：`qc_engine.py` 各 Rule 类仅 `rule_id = "QC-01"`，无 `standard_ref` 字段。

## 本轮范围

Round 3 聚焦"质控人员的工作工具"，不触及项目组日常操作。核心目标是让质控能：自定义规则、抽查项目、评级项目、维护案例库、出年报。

## 需求列表

### 需求 1：QC 规则定义表与管理 UI

**用户故事**：作为质控经理，我希望在系统里新增一条"补充资料平衡"检查规则，不改代码就能生效。

**本轮范围收窄**：按 design.md 架构决策，R3 **只落地 Python 类型元数据化 + JSONPath 两种 expression_type**。SQL 类型与 regex 类型 deferred 到 Round 6+，避免 SQL 白名单沙箱 + 前端 SQL 编辑器的工程膨胀（参考上轮合伙人建议第 12 条）。

**验收标准**：

1. The 数据库 shall 新增 `qc_rule_definitions` 表：`id/rule_code/severity/scope(workpaper|project|consolidation)/category/title/description/standard_ref/expression_type(python|jsonpath)/expression/parameters_schema/enabled/version/created_by/created_at`。
2. The 现有 14 条 QC-01~14 + QC-19~26 shall 作为 `expression_type='python'` + `expression=<dotted.path.to.Rule>` 迁移入表（seed），不破坏现有行为。
3. The `QCEngine.run` shall 改为从 `qc_rule_definitions WHERE enabled=true` 读规则，按 `expression_type` 分派执行器：Python（沙箱加载 class，timeout=10s）、JSONPath（校验 `parsed_data`，用 `jsonpath-ng`）。
4. The 前端 shall 新增页面 `/qc/rules`（权限 `role='qc'|'admin'`），CRUD 规则：列表/编辑/启停/查看历史版本。
5. The 规则编辑 shall 提供测试用例输入（选一张底稿试跑），返回命中与否，避免盲发布。
6. **预留扩展**：`expression_type` 枚举值预留 `sql` 与 `regex`（模型层即支持），但执行器本轮不实现，遇到这两种类型返回 `NotImplementedError`；Round 6+ 专项补齐 SQL 白名单沙箱。

### 需求 2：新规则"试运行"（dry-run）

**用户故事**：作为质控经理，发布新规则前我想看它会命中多少底稿，会不会误伤。

**验收标准**：

1. The 后端 shall 新增 `POST /api/qc/rules/{rule_id}/dry-run`，请求体 `{scope: 'project'|'all', project_ids?: UUID[], sample_size?: int}`。
2. The 执行器 shall 在沙箱中对采样的底稿跑规则（不写数据库），返回 `{total_checked, hits, hit_rate, sample_findings: [{wp_id, wp_code, message, severity}]}`。
3. The 耗时超过 60s shall 走 BackgroundJob 异步化，前端轮询 `job_status`。
4. The dry-run 结果 shall 仅用于**预览**，不写入 `wp_qc_results` 表，避免污染项目组看到的结果。
5. The 前端"规则编辑"页 shall 在保存前强制弹"试运行"步骤，质控看到命中率可选择是否继续发布。

### 需求 3：项目质量评级（ABCD 四级）

**用户故事**：作为质控合伙人，年度评审时我希望每个项目有 ABCD 评级，自动出来，依据透明。

**验收标准**：

1. The 后端 shall 新增 `project_quality_ratings` 表：`id/project_id/year/rating(A|B|C|D)/score(0-100)/dimensions(JSONB)/computed_at/computed_by_rule_version/override_by?/override_reason?`。
2. The 评级算法 shall 由可配置权重计算：**规则得分**（QC 通过率 30%）、**复核深度**（平均意见条数、退回率、意见合理性 25%）、**门禁失败次数**（sign_off gate 被拒 20%）、**整改响应 SLA**（问题单平均关闭时长 15%）、**客户响应**（承诺事项按时完成率 10%）。
3. The 权重 shall 存 `system_settings.qc_rating_weights`，质控合伙人可调；每次调整记版本号，历史评级保留原版本。
4. The `GET /api/qc/projects/{project_id}/rating/{year}` shall 返回评级 + 各维度得分 + 推导过程（透明性）。
5. The 质控 shall 可人工 override 评级（如"项目有特殊情况"），override 必须附文字说明，系统并存系统评级与人工评级。
6. The `QCDashboard` shall 在项目列表新增"评级"列，A=绿/B=蓝/C=橙/D=红。
7. 评级计算作为定时任务，每月 1 日凌晨批量计算上月快照，快照存 `project_quality_ratings`。

### 需求 4：质控抽查底稿工具

**用户故事**：作为质控经理，我希望对指定项目"随机抽 10% 底稿 + 全部 D 循环 + 全部评级 C/D 的底稿"做深度复核，系统帮我建个待办清单。

**验收标准**：

1. The 后端 shall 新增 `POST /api/qc/inspections`，请求体 `{project_id, strategy: 'random'|'risk_based'|'full_cycle'|'mixed', params: {...}, reviewer_id}`。
2. The 随机策略 shall 按 `ratio` 抽样；风险导向抽 `complexity≥high` 或 `review_rejection_count>0` 的底稿；全循环抽选定循环全部；mixed 组合前三种。
3. The 抽样结果 shall 生成 `QcInspection` 记录和一组 `QcInspectionItem` 子项，每项对应一张底稿的"质控复核任务"。
4. The 前端 shall 新增"质控抽查工作台" `/qc/inspections`：左栏抽查批次列表、中栏当前抽查底稿队列、右栏复核表单（引用现有 `ReviewWorkbench` 逻辑但 `review_type='qc_inspection'`）。
5. The 抽查 shall 不进入项目组的 `wp_review_records`，独立记 `qc_inspection_records`，避免干扰项目组复核状态。
6. The 抽查完成后 shall 生成"质控报告"Word（模板 `qc_inspection_report.docx`），含抽样方法、发现问题、整改建议。

### 需求 5：质控整改单专属工作流

**用户故事**：作为质控经理，我下发的整改单应该比普通问题单更"硬"：强制 48 小时响应、逾期直接上报合伙人、解决方案必须有复核人二次确认。

**验收标准**：

1. The `IssueTicket` 当 `source='Q'` 时 shall 触发专属 SLA：初始响应 48 小时、整改完成 7 天、逾期自动升级 `severity+1` 级并通知项目签字合伙人。
2. The 质控整改单 shall 强制字段：`remediation_plan`（整改方案文本）、`evidence_attachment`（整改证据附件 ID）、`qc_verifier_id`（二次验证质控人）。
3. When `status='pending_recheck'`，the 系统 shall 通知 `qc_verifier_id` 做二次确认；质控人确认"整改通过"后工单关闭，否则打回 `in_fix` 并记录拒绝原因。
4. The `IssueTicketList.vue` shall 按 `source` 分 tab，默认不混显；质控整改单行加🛡️图标与红左边框。
5. The `sla_worker` shall 识别质控整改单，升级规则独立配置。

### 需求 6：复核人深度指标

**用户故事**：作为质控合伙人，我要看每个复核人的"复核质量"：是不是走过场、意见提得深不深。

**验收标准**：

1. The 后端 shall 新增 `GET /api/qc/reviewer-metrics?year=&reviewer_id=`，返回：`avg_review_time_min / avg_comments_per_wp / rejection_rate / qc_rule_catch_rate(复核人发现的问题占所有问题的比例) / sampled_rework_rate(被质控抽查后发现漏审的比例)`。
2. The 时间统计 shall 从 `ReviewRecord.created_at` 到 `review_status` 切至 pass/reject 的 `updated_at` 差值。
3. The `QCDashboard` shall 新增"复核人画像"tab，按复核人展示雷达图 + 明细表。
4. 指标用于年度考评，非实时数据，允许每天凌晨刷新一次落 `reviewer_metrics_snapshots` 表。

### 需求 7：年度客户质量趋势对比

**用户故事**：作为质控合伙人，我要看 ABC 客户连续 3 年的审计质量有没有下滑。

**验收标准**：

1. The 后端 shall 新增 `GET /api/qc/clients/{client_id}/quality-trend?years=3`，返回近 N 年该客户所有项目的评级、问题数、错报金额、重要性水平变化。
2. The 前端 shall 新增页面 `/qc/clients/:clientId/trend`，展示折线图 + 年度对比表。
3. The 客户串联 shall 用 `client_name` 精确匹配（无 client_id 字段情况下作为妥协，后续 Round 补客户主数据），相同客户名视为同一实体。
4. When 数据缺失年份，the 页面 shall 显示"该年份无审计项目"，不报错。

### 需求 8：失败案例库

**用户故事**：作为质控，我要把本季度出过问题的典型底稿脱敏后变成案例，供新人学习。

**验收标准**：

1. The 数据库 shall 新增 `qc_case_library` 表：`id/title/category/severity/description/lessons_learned/related_wp_ids(脱敏)/related_standards/published_by/published_at/review_count`。
2. The 前端 shall 新增页面 `/qc/case-library`，支持分类筛选、搜索、查看详情。
3. The 从现有底稿"创建案例"：质控在 `QcInspectionItem` 详情点"发布为案例"，自动带入脱敏后的底稿片段（客户名替换 `[客户A]`、金额保留级次但加扰动 ±5%）。
4. The 案例详情 shall 关联《审计准则》外部编号（利用需求 10 的映射表）。
5. 案例库对所有用户开放只读，新员工培训可用。

### 需求 9：年度质量报告一键导出

**用户故事**：作为质控合伙人，年底一键生成"本所 2026 年度审计质量报告"。

**验收标准**：

1. The 后端 shall 新增 `POST /api/qc/annual-report?year=`，异步生成 Word 报告，模板 `qc_annual_report.docx`。
2. The 报告结构：封面 → 项目规模与分布 → 评级分布（ABCD 饼图）→ 典型问题 Top10 → 复核人表现 → 改进建议（LLM 生成，可编辑后留存）→ 附录（规则变更历史、抽查统计）。
3. The 生成任务 shall 走 `ExportJobService`，允许同时只有一个年度报告任务在跑。
4. The 报告落到 `/qc/annual-reports` 管理页，支持下载历史年报。

### 需求 10：QC 规则与审计准则对照

**用户故事**：作为质控，我要能说清每条 QC 规则对应《审计准则》第几号。

**验收标准**：

1. The `qc_rule_definitions.standard_ref` 字段 shall 存储准则引用数组 `[{code: '1301', section: '6.2', name: '审计工作底稿'}]`。
2. The 现有 QC-01~26 shall 在 seed 迁移时补齐 `standard_ref`（人工映射，起 tasks 时列全）。
3. The 前端规则列表页 shall 在每条规则旁显示标签形式的准则号，点击跳官方准则 URL（若有则跳 `regulatory_service` 配置的 URL，否则复制到剪贴板）。
4. The QC 结果弹窗 shall 在 finding 详情显示对应准则号，便于复核人解释。

## UAT 验收清单（手动验证）

1. 新建规则"现金流量表补充资料平衡差异 < 100"，SQL 表达式 `SELECT ... FROM ...`，试运行看命中率，发布后验证对一张违反的底稿能命中。
2. 对某项目跑质量评级，验证 ABCD 结果、各维度得分显示；人工 override 为 A，看历史保留系统评级。
3. 对某项目发起"mixed 抽查"（随机 20% + 全 D 循环），验证生成的抽查批次包含正确底稿集；完成 5 张抽查后导出质控报告 Word。
4. 发一张 `source='Q'` 整改单，验证 48 小时未响应后 severity 升级；整改人提交 `evidence_attachment` 后质控验证人收到通知。
5. 查某复核人年度指标，雷达图显示 5 个维度分值。
6. 找连续 3 年都审过的客户，看年度趋势折线是否正常。
7. 发一个案例到案例库，验证脱敏（客户名被替换）、金额扰动。
8. 导出 2026 年度质量报告，验证 Word 各节齐全。

## 不在本轮范围

- 项目组日常操作（Round 2）
- 底稿编辑器 / 助理视角（Round 4）
- EQCR（Round 5）

## 验收完成标志

需求 1~10 全部满足 + UAT 8 项完成，Round 3 关闭。

## 变更日志

- v1.0 (2026-05-05) 质控视角首稿。

## 不在本轮范围

- 项目组日常操作（Round 2）
- 底稿编辑器 / 助理视角（Round 4）
- EQCR（Round 5）
- `expression_type='sql' | 'regex'` 规则执行器（需求 1 预留枚举但不实现）

## 验收完成标志

需求 1~10 全部满足 + UAT 8 项完成（新增第 6/7/8 条覆盖案例库/年度趋势/年报），Round 3 关闭。

## 变更日志

- v1.2 (2026-05-05) 一致性校对修正：
  - 需求 1 按 design.md 收窄：R3 本轮只实现 `expression_type='python'` + `'jsonpath'` 两种，SQL/regex 枚举值保留但执行器未实现，遇到时 `NotImplementedError`
  - 补齐"不在本轮范围"与"验收完成标志"章节（首版起草时遗漏）
- v1.0 (2026-05-05) 质控视角首稿。

## 补充需求（v1.3，长期运营视角）

以下 2 条由合伙人第三轮深度复盘新增，聚焦"**AI 可溯源 + 审计日志质控验证**"——监管问责时质控必须能说清"哪句话是审计师写的，哪句是 AI 写的"。

### 需求 11：AI 生成内容强标记 + 审计师确认流

**用户故事**：作为质控合伙人，检查底稿时我必须一眼看出哪些结论是 AI 生成、哪些是审计师判断；未被审计师确认的 AI 内容不能进入签字前的底稿。

**代码锚定**：`wp_ai_service` 写入 `parsed_data.ai_content` 带 confidence，`qc_engine.py` 有 `AIUnconfirmedContentRule`（QC-02）但仅 warning 级，且前端底稿编辑器不区分显示。

**验收标准**：

1. The `wp_ai_service` 写入 AI 内容时 shall 统一包装为 `{type: 'ai_generated', source_model, generated_at, confidence, content, confirmed_by?, confirmed_at?}` 结构，存 `parsed_data.ai_content[]`。
2. The `WorkpaperEditor` shall 对 AI 生成内容的单元格加**虚线紫色边框 + 🤖 图标**，hover 显示"来源：AI（模型版本 X，置信度 Y）"。
3. The 助理/复核人点击 🤖 图标 shall 弹"确认采纳 / 修订 / 拒绝"三选，选择后写 `confirmed_by / confirmed_at`；未确认的 AI 内容 **紫色边框保留**。
4. The `gate_rules_phase14` shall 新增 `AIContentMustBeConfirmedRule`：`sign_off` gate 检查 `parsed_data.ai_content` 中**未确认项 = 0**，否则阻断。QC-02（warning）保留作为 `submit_review` 提醒，新规则是 sign_off blocking。
5. The 归档包 shall 在签字流水 PDF 末尾附"AI 内容溯源表"：列所有 AI 生成内容 + 确认人 + 确认时间。
6. The LLM 综合简报、年报、AI 补注等**独立产物**类 AI 输出 shall 在文档首页/末尾生成"AI 贡献声明"水印："本文档含 AI 辅助生成内容，已由 {审计师} 审阅并定稿"。

### 需求 12：审计日志质控抽查规则

**用户故事**：作为质控合伙人，R1 需求 9 把审计日志落库了，我要能对日志做合规性抽查（谁在非工作时间批量改数据？谁频繁 override gate？）。

**代码锚定**：R1 需求 9 `audit_log_entries` 表落地后，缺"日志分析规则"。

**验收标准**：

1. The `qc_rule_definitions`（R3 需求 1）shall 新增 `scope='audit_log'` 类型，`expression_type='jsonpath'` 可查询日志条目。
2. 预置 5 条日志审查规则（seed）：
   - AL-01: 非工作时间（22:00-06:00）批量修改底稿 > 10 次/小时 → warning
   - AL-02: 同一 IP 多账号登录（admin+auditor）→ blocking（潜在越权）
   - AL-03: `retention_override` 或 `rotation_override` 动作触发 → info 提示记录
   - AL-04: `gate_override` 次数/月 > 5（某角色） → warning
   - AL-05: 哈希链断裂 → blocking（QC-AL-05 升到 sign_off gate）
3. The `QcInspectionWorkbench` 新增 Tab "日志合规抽查"，展示命中的异常条目，支持标记"已审查 / 需上报"。
4. The 质控抽查报告（R3 需求 4 生成的 Word）shall 包含"日志异常摘要"章节。
5. QC-AL-05 命中时 shall 通知事务所首席合伙人 + 首席风控合伙人，必须 48 小时内人工答复。

## 变更日志（续）

- v1.3 (2026-05-05) 长期运营视角增强：
  - 新增需求 11：AI 生成内容强标记 + 必须确认（监管可溯源）
  - 新增需求 12：审计日志质控抽查（依赖 R1 需求 9 落库后可用）
