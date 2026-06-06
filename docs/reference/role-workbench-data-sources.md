# 五角色作业台数据来源盘点

> MVP-1 产物：盘点现有后端 service 对五类角色作业台的数据供给情况。
> 本阶段不开发新 dashboard，仅冻结数据来源映射。

## 数据来源总表

| 数据项 | 来源 service | 已有/待建 | 消费角色 |
|--------|-------------|-----------|----------|
| 今日待办 | my_todo_service | ✅ 已有 | 助理 |
| 被退回复核 | review_conversation_service | ✅ 已有 | 助理 |
| 底稿完成率 | dashboard_aggregator_service | ✅ 已有 | 经理 |
| 复核 Aging | review_conversation_service | ✅ 已有 | 经理/QC |
| 工时预算消耗率 | workhour_service | ⚠️ 缺 budget 字段 | 经理 |
| 人员负荷 | workhour_service | ⚠️ 缺 7 天任务预测 | 经理 |
| 质量分 | qc_dashboard_service | ⚠️ 需确认评分规则 | QC |
| QC 规则命中 | qc_inspection_service | ✅ 已有 | QC |
| 签发阻断项 | stale_summary_aggregate + ai_content + deliverable | ⚠️ 需聚合 | 合伙人 |
| 重大判断/KAM | eqcr_workbench_service | ✅ 已有 | EQCR |
| AI 未确认内容 | ai_content_log_service | ✅ 已有 | 合伙人/助理 |
| 资料缺口 | — | ❌ 待建 | 助理 |
| 风险总览 | risk_summary_service | ✅ 已有 | 经理/合伙人 |

## 角色 → 数据项映射

| 角色 | 核心数据项 | 主要来源 |
|------|-----------|----------|
| 审计助理 | 今日待办、被退回复核、AI 未确认、资料缺口 | my_todo_service, review_conversation_service, ai_content_log_service |
| 项目经理 | 底稿完成率、复核 Aging、工时预算消耗率、人员负荷、风险总览 | dashboard_aggregator_service, review_conversation_service, workhour_service, risk_summary_service |
| 质控人员 | 质量分、QC 规则命中、复核 Aging | qc_dashboard_service, qc_inspection_service, review_conversation_service |
| 项目合伙人 | 签发阻断项、AI 未确认内容、风险总览 | stale_summary_aggregate, ai_content_log_service, risk_summary_service |
| EQCR | 重大判断/KAM | eqcr_workbench_service |

## 待建/待补项

1. **资料缺口 service**：当前无独立服务，需新建或从 my_todo_service 扩展
2. **workhour_service.budget_hours**：projects 表缺 budget_hours 字段，工时预算消耗率无法计算
3. **workhour_service 7 天预测**：人员负荷指标需要未来任务预测能力
4. **qc_dashboard_service 评分规则**：质量分口径需与 QC 团队确认
5. **签发阻断项聚合 facade**：需跨 stale_summary、ai_content、deliverable 多表聚合
