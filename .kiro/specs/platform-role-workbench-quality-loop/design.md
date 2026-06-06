# 设计文档：五类角色作业台与质量闭环

## 概述

本 spec 面向真实事务所上线使用，按审计助理、项目经理、质控人员、项目合伙人、EQCR 五类角色重塑入口。目标是减少用户在多个模块之间寻找信息的成本，把任务、复核、质量、风险和签发阻断项聚合到角色工作台。

## 核心设计

### 1. RoleWorkbenchFacade

新增后端 `role_workbench_facade.py`，按角色聚合已有服务：

- `my_todo_service`
- `dashboard_aggregator_service`
- `review_conversation_service`
- `qc_dashboard_service`
- `eqcr_workbench_service`
- `partner_service`
- `workhour_service`
- `risk_summary_service`
- `stale_summary_aggregate`

前端新增 `RoleWorkbenchShell.vue`，根据当前系统角色和项目职责加载不同面板。

### 2. 审计助理作业台

模块：

- 今日待办
- 被退回复核
- 即将截止
- 资料缺口
- AI 建议但未确认
- 最近编辑底稿

操作目标是直接定位，不经过中间列表。

### 3. 项目经理经营驾驶舱

四象限：

| 象限 | 指标 |
|---|---|
| 进度 | 底稿完成率、程序完成率、关键里程碑 |
| 质量 | 复核 Aging、质量分、重复问题 |
| 预算 | 工时预算消耗率、人员负荷、超支预测 |
| 风险 | 重大风险、stale、conflict、资料缺口 |

### 4. 质控闭环工作台

QC 问题生命周期：

```text
identified -> assigned -> responded -> verified -> closed
```

每条问题必须关联证据链：底稿、单元格、附件、复核记录、责任人。

### 5. 合伙人签发风险雷达

只展示签发所需的高层判断：

- 重大事项
- 未解决重大复核意见
- 关键调整
- 报告意见类型
- AI 未确认内容
- stale/conflict 阻断
- 归档/交付件状态

### 6. EQCR 独立复核工作台

EQCR 维度：

- 重大判断
- KAM
- 重大估计
- 持续经营
- 关联方
- 集团审计范围
- Shadow Compute 差异
- EQCR checklist

EQCR 批注与普通复核批注分开存储和展示。

### 7. 问题类型库

新增质量问题类型：

- 程序遗漏
- 底稿说明不足
- 附件证据不足
- 金额不一致
- 复核回复不充分
- AI 内容未确认

用于培训、QC 规则优化和项目风险提示。

## 不在范围

- 不废弃现有 dashboard 页面。
- 不重写 QC 规则引擎。
- 不替代签发审批流程。

## 现有代码锚点

### 后端

- `backend/app/services/my_todo_service.py`
- `backend/app/services/dashboard_aggregator_service.py`
- `backend/app/services/manager_dashboard_service.py`
- `backend/app/services/review_conversation_service.py`
- `backend/app/services/qc_dashboard_service.py`
- `backend/app/services/qc_inspection_service.py`
- `backend/app/services/eqcr_workbench_service.py`
- `backend/app/services/partner_service.py`
- `backend/app/services/workhour_service.py`
- `backend/app/services/risk_summary_service.py`

### 前端

- `views/Dashboard.vue`
- `views/ManagerDashboard.vue`
- `views/PartnerDashboard.vue`
- `views/PartnerProjectDashboard.vue`
- `views/ReviewWorkbench.vue`
- `views/qc/QcInspectionWorkbench.vue`
- `views/eqcr/EqcrWorkbench.vue`
- `components/dashboard/MyTodoCard.vue`
- `components/review/*`
- `components/eqcr/*`

## API 草案

- `GET /api/projects/{project_id}/role-workbench?role=auditor|manager|qc|partner|eqcr`
- `GET /api/projects/{project_id}/quality-loop/issues`
- `POST /api/projects/{project_id}/quality-loop/issues/{id}/close`
- `GET /api/projects/{project_id}/signoff/risk-radar`
- `GET /api/projects/{project_id}/eqcr/checklist`

## 指标口径

| 指标 | 口径 |
|---|---|
| 底稿完成率 | 已完成底稿 / 应完成底稿 |
| 复核 Aging | 当前时间 - 复核意见创建时间，按未关闭项统计 |
| 工时预算消耗率 | 已审批工时 / 项目预算工时 |
| 人员负荷 | 未来 7 天分配任务预计工时 / 可用工时 |
| 质量分 | 现有 quality_score 或 QC 规则评分 |
| 签发阻断项 | stale/conflict/重大复核未关闭/AI 未确认/交付件缺失 |

## 迁移策略

1. 不删除现有 dashboard。
2. 新增 `RoleWorkbenchShell` 作为统一入口。
3. 试点项目默认进入新入口，保留跳回旧 dashboard 链接。
4. 指标口径先复用现有 service，后续再统一优化。
