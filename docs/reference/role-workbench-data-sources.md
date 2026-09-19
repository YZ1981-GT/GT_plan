# 五角色作业台数据来源盘点（P0 正式版）

> P0-1 产物：确认前置依赖已就绪，盘点现有后端 service 对五类角色作业台的数据供给情况。

## P0-1 前置依赖检查总结

| 依赖 spec | P0 交付物 | 状态 | 对本 spec 的价值 |
|-----------|----------|------|-----------------|
| `platform-context-permission-foundation` | `permission_matrix_service.py` + 7 operation codes + `usePermissionMatrix` | ✅ 已交付 | Facade 按角色分流的判定基础 |
| `platform-linkage-contract-stale` | `resolveLinkageRoute` + `LinkageContract` schema + stale 降级日志 | ✅ 已交付 | 每个 item 的跳转 route 解析 |
| 现有 service 基础数据 | 9 个 service 覆盖待办/复核/仪表盘/QC/EQCR/工时/风险/stale | ✅ 可查询 | Facade 聚合数据源 |

**结论：P0 前置依赖全部满足，P1 实施可启动。** 唯一数据缺口为 `projects.budget_hours` 列（影响工时预算消耗率），已有降级策略。

---

## 1. 前置依赖确认（详细）

### P0-1.1 `platform-context-permission-foundation` P0 已交付

| 交付物 | 文件 | 状态 |
|--------|------|------|
| `permission_matrix_service.py` | `backend/app/services/permission_matrix_service.py` | ✅ 已交付 |
| 7 个 operation code | `project:view`, `wp:edit`, `wp:review`, `report:edit`, `report:sign`, `note:edit`, `archive:manage` | ✅ 已定义 |
| 5 类系统角色 | admin / partner / manager / auditor / qc / eqcr | ✅ 映射完成 |
| 项目职责叠加 | preparer / reviewer / manager / partner / eqcr | ✅ 并集策略 |
| `get_allowed_operations()` | 根据 system_role + project_role 返回 operation set | ✅ 可调用 |
| `can()` / `why_cannot()` | 单操作权限判断 | ✅ 可调用 |
| 前端 `usePermissionMatrix` | `can(op)` / `whyCannot(op)` | ✅ 已交付 |
| 测试 | `test_permission_matrix_service.py` + `usePermissionMatrix.spec.ts` | ✅ 通过 |

**结论**：角色/职责/权限数据源已就绪，RoleWorkbenchFacade 可直接调用 `get_allowed_operations()` 判定当前用户角色，按角色返回对应作业台区块。

### P0-1.2 `platform-linkage-contract-stale` P0 已交付

| 交付物 | 文件 | 状态 |
|--------|------|------|
| `LinkageContract` schema | `backend/app/schemas/linkage_contract.py` | ✅ 已交付 |
| `linkage_contract_builder.py` | TB→WP→Note 全链路构建器 | ✅ 已交付 |
| `stale_degraded_logger.py` | stale 更新失败写 degraded 记录 | ✅ 已交付 |
| 前端 `resolveLinkageRoute` | `src/composables/useResolveLinkageRoute.ts` | ✅ 已交付 |
| 前端 `LinkageContract` 类型 | `src/types/linkageContract.ts` | ✅ 已交付 |
| route 解析覆盖 | workpaper(UUID/wp_code), report, note, trial_balance, adjustment, ledger | ✅ 测试通过 |
| 枚举一致性 | 前后端 source_type/target_type/status/confidence 同构 | ✅ 测试通过 |

**结论**：route resolver 已就绪，作业台每个待办项/下钻项可通过 `resolveLinkageRoute(contract, projectId)` 解析跳转目标，缺失时返回 `null`（前端显示 missing_reason）。

### P0-1.3 复核、QC、EQCR 现有 service 可查询基础数据

| 服务 | 文件 | 可提供数据 | 状态 |
|------|------|-----------|------|
| `my_todo_service` | `backend/app/services/my_todo_service.py` | 用户待办列表（wp_id, urgency, reason） | ✅ 可用 |
| `review_conversation_service` | `backend/app/services/review_conversation_service.py` | 复核意见列表、Aging 计算 | ✅ 可用 |
| `dashboard_aggregator_service` | `backend/app/services/dashboard_aggregator_service.py` | 项目进度聚合 | ✅ 可用 |
| `qc_dashboard_service` | `backend/app/services/qc_dashboard_service.py` | QC 总览（命中/通过率） | ✅ 可用 |
| `qc_inspection_service` | `backend/app/services/qc_inspection_service.py` | QC 抽查详情（create/verdict/list） | ✅ 可用 |
| `eqcr_workbench_service` | `backend/app/services/eqcr_workbench_service.py` | EQCR 项目列表、维度概览 | ✅ 可用 |
| `workhour_service` | `backend/app/services/workhour_service.py` | 工时录入/汇总（project_summary） | ⚠️ 缺 budget 字段 |
| `risk_summary_service` | `backend/app/services/risk_summary_service.py` | 风险概况 | ✅ 可用 |
| `stale_degraded_logger` | `backend/app/services/stale_degraded_logger.py` | stale 降级记录 | ✅ 可用 |

**结论**：核心查询基础数据已可用。唯一缺口是 `projects.budget_hours` 字段（工时预算消耗率分母），标记"待补数据"，其余指标均有数据源支撑。

## 2. 角色 → 数据项映射

| 角色 | 核心数据项 | 主数据源 |
|------|-----------|----------|
| 审计助理 (auditor) | 今日待办、被退回复核、AI 未确认、资料缺口、即将截止 | `my_todo_service`, `review_conversation_service` |
| 项目经理 (manager) | 底稿完成率、复核 Aging、工时预算消耗率、人员负荷、风险总览 | `dashboard_aggregator_service`, `review_conversation_service`, `workhour_service`, `risk_summary_service` |
| 质控人员 (qc) | 质量分、QC 规则命中、复核 Aging、问题整改趋势 | `qc_dashboard_service`, `qc_inspection_service`, `review_conversation_service` |
| 项目合伙人 (partner) | 签发阻断项、重大未关闭复核、AI 未确认内容、风险总览 | `stale_degraded_logger`, `review_conversation_service`, `risk_summary_service` |
| EQCR (eqcr) | 重大判断/KAM、持续经营、关联方、集团范围 | `eqcr_workbench_service` |

## 3. 数据流架构

```
┌─────────────────────────────────────────────────────────────────┐
│  RoleWorkbenchFacade (P1 实现)                                   │
│  ┌──────────────────┐                                           │
│  │ permission_matrix │ → 判定 role → 选择 section 组合            │
│  └──────────────────┘                                           │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐  ┌───────────────────┐  ┌─────────────────┐    │
│  │my_todo_svc  │  │review_conv_svc    │  │dashboard_agg_svc│    │
│  │(助理待办)    │  │(复核Aging/退回)    │  │(进度/完成率)     │    │
│  └─────────────┘  └───────────────────┘  └─────────────────┘    │
│  ┌─────────────┐  ┌───────────────────┐  ┌─────────────────┐    │
│  │workhour_svc │  │qc_inspection_svc  │  │eqcr_workbench   │    │
│  │(工时/预算)   │  │(QC规则/质量)       │  │(EQCR 维度)      │    │
│  └─────────────┘  └───────────────────┘  └─────────────────┘    │
│  ┌─────────────┐  ┌───────────────────┐                         │
│  │stale_logger │  │risk_summary_svc   │                         │
│  │(降级/阻断)   │  │(风险总览)          │                         │
│  └─────────────┘  └───────────────────┘                         │
│         │                                                        │
│         ▼                                                        │
│  resolveLinkageRoute() → 每个 item.route 或 missing_reason       │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 待建/待补项

| # | 缺口 | 影响指标 | 优先级 | 解决方案 |
|---|------|----------|--------|----------|
| 1 | `projects.budget_hours` 列不存在 | 工时预算消耗率 | P1 迁移补 | 新 migration 加列，默认 NULL |
| 2 | 7 天任务预测能力 | 人员负荷 | P1 | `workhour_service` 新增方法 |
| 3 | 资料缺口独立 service | 助理作业台 | P1 | 从 `my_todo_service` 扩展或新建 |
| 4 | QC 评分加权规则 | 质量分 | P2 确认 | 需与 QC 团队确认公式 |
| 5 | 签发阻断项聚合 | 合伙人风险雷达 | P1 facade | `RoleWorkbenchFacade` 多表聚合 |

## 5. 降级策略

当数据源不可用时的处理：

| 场景 | 策略 |
|------|------|
| `budget_hours` 为 NULL | 前端显示"暂无预算数据"，指标值返回 `null` |
| stale_degraded_logger 无记录 | 签发阻断项为 0（绿灯） |
| QC 无抽查记录 | 质量分显示"暂无数据"，不参与排名 |
| EQCR service 未返回数据 | 显示"尚未启动独立复核" |
| route 解析失败 | item 包含 `missing_reason` 字段说明原因 |
