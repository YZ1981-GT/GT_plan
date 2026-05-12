# Refinement Round 3 — 任务清单

按 README 约定：一轮 ≤ 20 任务。本轮需求量较重，分 **3 个 Sprint**（规则库 / 抽查评级 / 案例年报）。前置依赖：R1 完成、R2 工时审批已实施（评级依赖审批数据）。

## Sprint 1：规则库元数据化（需求 1, 2, 10）

- [x] 1. 数据模型：`qc_rule_definitions` + `qc_inspections` + `project_quality_ratings` 等表
  - 新建 `backend/app/models/qc_rule_models.py`、`qc_inspection_models.py`、`qc_rating_models.py`、`qc_case_library_models.py`
  - Alembic 脚本 `round3_qc_governance_{date}.py`
  - 导入到 `app/models/__init__.py`
  - _需求_ 1, 3, 4, 8

- [x] 2. 后端：QcRuleDefinition CRUD + 版本管理
  - `backend/app/services/qc_rule_definition_service.py`
  - `GET/POST/PATCH/DELETE /api/qc/rules`（PATCH 每次 version+1，保留历史）
  - _需求_ 1

- [x] 3. 后端：Python + JSONPath 执行器
  - `backend/app/services/qc_rule_executor.py`
  - `python` 类型：加载 dotted path 类，走沙箱 timeout=10s
  - `jsonpath` 类型：只读 `parsed_data`，用 `jsonpath-ng` 库
  - `QCEngine.run` 改为从 `qc_rule_definitions` 读规则分派到执行器
  - _需求_ 1

- [x] 4. 后端：既有规则迁移 seed
  - `backend/scripts/seed_qc_rules.py` 把 QC-01~14 + QC-19~26 写入 `qc_rule_definitions`
  - `expression_type='python'`，`expression='app.services.qc_engine.ConclusionNotEmptyRule'` 等
  - 补齐每条的 `standard_ref`（需求 10，人工映射整理）
  - 启动 lifespan 里调一次确保规则存在
  - _需求_ 1, 10

- [x] 5. 后端：规则试运行 dry-run
  - `POST /api/qc/rules/{rule_id}/dry-run`
  - 采样底稿跑规则沙箱，不写 DB，返回命中率
  - 耗时超过 60s 走 BackgroundJob
  - _需求_ 2

- [x] 6. 前端：QcRuleList 页面
  - `src/views/qc/QcRuleList.vue`
  - 规则列表（显示启停状态 + 准则号标签）
  - 筛选 severity / scope / enabled
  - 路由 `/qc/rules`，权限 `role='qc'|'admin'`
  - _需求_ 1, 10

- [x] 7. 前端：QcRuleEditor + 试运行流程
  - `src/views/qc/QcRuleEditor.vue`
  - 编辑表单 + "试运行"强制步骤（保存前必须预览命中率）
  - 历史版本抽屉
  - _需求_ 1, 2

- [x] Sprint 1 验收
  - 单元测试：Python 执行器沙箱 timeout + JSONPath 3 用例
  - 回归测试：QC-01~14 迁移后跑项目得到与硬编码版本一致结果
  - UAT：requirements.md UAT 第 1 条走完

## Sprint 2：抽查 + 评级 + 整改 SLA（需求 3, 4, 5, 6）

- [x] 8. 后端：QcInspectionService
  - `backend/app/services/qc_inspection_service.py`
  - `POST /api/qc/inspections` 按策略生成批次 + items
  - 四策略 `random / risk_based / full_cycle / mixed` 纯函数
  - `POST /inspections/{id}/items/{item_id}/verdict` 质控人录入结论
  - _需求_ 4

- [x] 9. 后端：QualityRatingService
  - `backend/app/services/quality_rating_service.py`
  - 5 维度评分 + 权重配置（存 `system_settings.qc_rating_weights`）
  - 每月 1 日凌晨定时任务算上月快照（在 `sla_worker` 旁新加 `qc_rating_worker`）
  - `POST /api/qc/projects/{pid}/rating/{year}/override` 人工覆盖
  - _需求_ 3

- [x] 10. 后端：sla_worker 扩展 Q 整改单分支
  - 识别 `IssueTicket.source='Q'` 专属 SLA（48h 响应 / 7d 完成）
  - 逾期升级通知到项目签字合伙人
  - `remediation_plan / evidence_attachment / qc_verifier_id` 强制字段校验
  - _需求_ 5

- [x] 11. 后端：复核人深度指标
  - `backend/app/services/reviewer_metrics_service.py`
  - 从 `ReviewRecord.created_at/updated_at` + `IssueTicket` 算 5 指标
  - 每日凌晨定时任务落 `reviewer_metrics_snapshots`
  - `GET /api/qc/reviewer-metrics` 返回
  - _需求_ 6

- [x] 12. 前端：QcInspectionWorkbench
  - `src/views/qc/QcInspectionWorkbench.vue`
  - 左栏批次列表 + 中栏抽查底稿队列 + 右栏复核表单
  - 完成后一键生成质控报告 Word
  - 路由 `/qc/inspections`
  - _需求_ 4

- [x] 13. 前端：QCDashboard 扩展
  - 项目列表新增"评级"列（A/B/C/D 颜色区分）
  - 新增"复核人画像"Tab（雷达图 + 明细表）
  - _需求_ 3, 6

- [x] 14. 前端：IssueTicketList Q 整改单 UI
  - `source='Q'` 行加🛡️图标 + 红左边框
  - 按 source 分 Tab（Q 独立一个 Tab，突出显示）
  - 强制字段编辑器（remediation_plan/evidence_attachment/qc_verifier_id）
  - _需求_ 5

- [x] Sprint 2 验收
  - 单元测试：`QualityRatingService` 5 维度 15 用例
  - 集成测试：`test_qc_inspection_e2e.py`（抽查→复核→报告）
  - 回归：现有 sla_worker 原逻辑不受影响
  - UAT：requirements.md UAT 第 2/3/4/5 条走完

## Sprint 3：案例库 + 客户趋势 + 年报（需求 7, 8, 9）

- [x] 15. 后端：客户趋势 API
  - `GET /api/qc/clients/{client_name}/quality-trend?years=3`
  - 按 client_name 精确匹配聚合近 N 年评级/错报/重要性
  - 缺失年份返回空槽不报错
  - _需求_ 7

- [x] 16. 前端：ClientQualityTrend 页面
  - `src/views/qc/ClientQualityTrend.vue`
  - 折线图 + 年度对比表
  - 路由 `/qc/clients/:clientName/trend`
  - _需求_ 7

- [x] 17. 后端：案例库 CRUD + 脱敏
  - `backend/app/services/qc_case_library_service.py`
  - `POST /inspections/{id}/items/{item_id}/publish-as-case` 脱敏后入库（客户名替换 + 金额 ±5%）
  - 脱敏前需质控合伙人预览确认才发布
  - _需求_ 8

- [x] 18. 前端：QcCaseLibrary 页面
  - `src/views/qc/QcCaseLibrary.vue`
  - 分类筛选 + 搜索 + 详情页
  - 从 QcInspectionWorkbench 详情提供"发布为案例"入口
  - _需求_ 8

- [x] 19. 后端：年报生成
  - `POST /api/qc/annual-reports?year=`
  - 走 `ExportJobService` 异步，每年至多一个任务（幂等锁）
  - 模板 `backend/data/archive_templates/qc_annual_report.docx`
  - 各章节：项目规模分布、评级分布饼图、Top10 问题、复核人表现、LLM 综合建议
  - _需求_ 9

- [x] 20. 前端：QcAnnualReports + 章节注册
  - `src/views/qc/QcAnnualReports.vue` 历史年报列表（年报独立管理，不进归档包 ZIP）
  - 后端 `archive_section_registry.register('03', 'qc_inspection_report.pdf', qc_inspection_pdf_generator)` 注册**抽查报告**（对应需求 4 的 `qc_inspection_report.docx`）；年报不占归档章节号
  - 归档章节号 03 = 质控抽查报告（本轮落地）；年报走独立下载路径 `/api/qc/annual-reports/{id}/download`
  - _需求_ 4, 9，依赖 R1 归档章节化

- [x] Sprint 3 验收
  - 单元测试：脱敏函数（客户名 + 金额扰动）5 用例
  - 集成测试：`test_qc_annual_report_generation.py`（数据准备 → 异步生成 → 下载）
  - UAT：requirements.md UAT 第 6/7/8 条走完

## 完成标志

- 所有任务 `[x]`
- UAT 8 项有通过记录
- `pytest backend/tests/ -v` 全过
- QC-01~26 规则迁移后跑项目结果与硬编码版本一致（diff=0）
- Round 3 关闭

## Sprint 4：AI 可溯源 + 审计日志抽查（需求 11~12，新增）

5 个任务，依赖 R1 Sprint 3（审计日志落库）完成。

- [x] 21. 后端：AI 内容统一结构化 + 门禁规则
  - `wp_ai_service` 所有 AI 输出包装为 `{type:'ai_generated', source_model, confidence, confirmed_by?, confirmed_at?}`
  - `parsed_data.ai_content` 清洗迁移脚本（老数据补 `confirmed_by=null`）
  - `gate_rules_phase14` 新增 `AIContentMustBeConfirmedRule` 注册到 sign_off
  - _需求_ 11

- [x] 22. 前端：AI 内容视觉标记 + 确认流
  - `WorkpaperEditor.vue` AI 单元格虚线紫色边框 + 🤖 图标
  - 点击图标弹"采纳/修订/拒绝"对话框
  - AI 侧栏（R4 需求 2）生成内容默认写入结论时带 ai_generated 类型
  - _需求_ 11

- [x] 23. 后端：AI 贡献声明水印
  - 简报、年报、AI 补注 PDF 生成时在首尾页加"AI 贡献声明"
  - 复用 `pdf_export_engine` 水印能力
  - _需求_ 11

- [x] 24. 后端：日志审查规则引擎
  - `qc_rule_definitions.scope` 枚举新增 `audit_log`
  - `qc_rule_executor` 新增 audit_log 分派（查 `audit_log_entries` 表，JSONPath 过滤 payload）
  - Seed 预置 AL-01~05 五条规则
  - _需求_ 12

- [x] 25. 前端：QcInspectionWorkbench 日志合规 Tab
  - 新增 Tab "日志合规抽查"
  - 命中条目列表 + 标记状态
  - 质控抽查报告 Word 新增"日志异常摘要"章节
  - _需求_ 12

- [x] Sprint 4 验收
  - 回归：QC-02（既有 AI 未确认 warning）仍能触发于 submit_review
  - 集成测试：`test_ai_content_confirm_flow.py`
  - UAT 新增：
    - AI 生成"结论建议"后点"采纳"→ confirmed_by 有值 → sign_off gate 通过
    - 未确认 AI 内容 sign_off 被 AIContentMustBeConfirmedRule 阻断
    - 手动插入一条凌晨 3 点批量删底稿的 audit_log → AL-01 命中
