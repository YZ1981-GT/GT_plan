"""协作管理路由注册

覆盖原 router_registry.py 中以下分组：
  §7  团队与看板（staff/assignments/workhours/dashboard/pm_dashboard/qc_dashboard/...）
  §9  Phase 14: 门禁引擎与治理
  §10 Phase 15: 任务树与事件编排
  §11 Phase 16: 取证包与版本链
  §12 协作管理（PBC 清单 / 函证管理）
  §13 Round 4：审计助理增强
  §14 Round 5：EQCR 工作台
  §15 Round 6：QC 规则定义管理
  §16 Round 3：QC 审计日志合规抽查
  §17 Round 3：QC 抽查 + 评级 + 案例库 + 年报
  §18 Round 7：Stale 底稿汇总
  §19 Round 7：QC 本月应抽查
  §20 Round 7：报表行关联底稿
  §21 Round 8：风险摘要
  §22 Round 8：附注行关联底稿
  §23 通知中心
  §30 Enterprise Linkage: Presence + Conflict Guard
  §31 Enterprise Linkage: 联动查询 + 批量重分类
  §32 Enterprise Linkage: 管理后台事件健康
  §43 全链路工作流编排
  §51 Sprint 10：批量项目操作
  §55 R10 Spec C：事件级联健康度
  §60 global-linkage-bus
  §86 合伙人仪表盘聚合端点
  §87 联动全景图
  §89 QC 风险热力图
  §95 Phase 4 F3: EQCR 快照机制
  §97 Phase 5 F1: 待办聚合
  §98 Phase 5 F2: 跨循环断裂清单
  §99 Phase 5 F3: 归档前完整性自检报告
  §100 Phase 5 F7: 批量复核通过
  §101 Phase 6 F4: 项目级权限端点
  §102 Phase 6 F5: 待回复批注聚合
  §103 Phase 6 F7: 经理项目群总览
  §104 Phase 6 F8: 复核配置 API
  §105 Phase 7 F1: EQCR 结构化判断
  §106 Phase 7 F2: EQCR 问题单
  §107 Phase 7 F3: EQCR 趋势
  §108 Phase 7 F4: 复核意见模板库
  §109 Phase 7 F5: QC 报告 Word 导出
  §110 Phase 7 F6: VR 规则覆盖度
  §111 Phase 7 F7: 工时填报 CRUD
  §112 Phase 7 F8: 工时预算对比
  §113 Phase 7 F9: 复核分派推荐
  §114 Phase 7 F10: 工时审批关联
  §115 Phase 7 F12: 多项目紧急度评分
"""
from fastapi import FastAPI


def register_collaboration_routers(app: FastAPI) -> None:
    """注册协作管理相关路由"""

    # ═══ §7. 团队与看板 ═══
    from app.routers.staff import router as staff_router
    from app.routers.assignments import router as assign_router
    from app.routers.workhours import router as wh_router
    from app.routers.workhour_list import router as wh_list_router
    from app.routers.dashboard import router as dash_router
    from app.routers.pm_dashboard import router as pmd_router
    from app.routers.qc_dashboard import router as qcd_router
    from app.routers.partner_dashboard import router as pd_router
    from app.routers.role_context import router as rc2_router
    from app.routers.procedures import router as proc_router
    from app.routers.subsequent_events import router as se_router
    from app.routers.forum import router as forum_router
    from app.routers.independence import router as independence_router

    for r in [staff_router, assign_router, wh_router, wh_list_router, dash_router,
              pmd_router, qcd_router, pd_router, rc2_router, proc_router,
              se_router, forum_router, independence_router]:
        app.include_router(r, tags=["团队与看板"])

    # 角色AI辅助
    from app.routers.role_ai_features import router as rai_router
    app.include_router(rai_router, tags=["团队与看板"])

    # ═══ §9. Phase 14: 门禁引擎与治理 ═══
    from app.routers.gate import router as gate_router
    from app.routers.trace import router as trace_router
    from app.routers.sod import router as sod_router

    for r in [gate_router, trace_router, sod_router]:
        app.include_router(r, prefix="/api", tags=["门禁与治理"])

    # ═══ §10. Phase 15: 任务树与事件编排 ═══
    from app.routers.task_tree import router as task_tree_router
    from app.routers.issues import router as issues_router
    from app.routers.task_events import router as task_events_router

    for r in [task_tree_router, issues_router, task_events_router]:
        app.include_router(r, prefix="/api", tags=["任务树与编排"])

    # ═══ §11. Phase 16: 取证包与版本链 ═══
    from app.routers.version_line import router as version_line_router
    from app.routers.offline_conflicts import router as conflict_router
    from app.routers.consistency_replay import router as consistency_replay_router
    from app.routers.export_integrity import router as export_integrity_router

    for r in [version_line_router, conflict_router, consistency_replay_router,
              export_integrity_router]:
        app.include_router(r, prefix="/api", tags=["取证与版本链"])

    # ═══ §12. 协作管理（PBC 清单 / 函证管理） ═══
    from app.routers.pbc import router as pbc_router
    from app.routers.confirmations import router as confirmations_router

    app.include_router(pbc_router, prefix="/api", tags=["PBC清单"])
    app.include_router(confirmations_router, prefix="/api", tags=["函证管理"])

    # ═══ §12b. 原始凭证 LLM 识别 ═══
    from app.routers.wp_document_recognize import router as doc_recognize_router
    app.include_router(doc_recognize_router, prefix="/api", tags=["原始凭证识别"])

    # ═══ §12c. 通用编辑锁（global-refinement-v5-closure 能力域 C） ═══
    from app.routers.editing_locks import router as editing_locks_router
    app.include_router(editing_locks_router, tags=["editing-locks"])

    # ═══ §13. Round 4：审计助理增强 ═══
    from app.routers.workpaper_requirements import router as wpreq_router
    from app.routers.workpaper_prior_year import router as wppy_router
    from app.routers.workpaper_html_preview import router as wphp_router
    from app.routers.ocr_fields import router as ocrf_router
    from app.routers.penetrate_by_amount import router as pba_router

    for r in [wpreq_router, wppy_router, wphp_router, ocrf_router, pba_router]:
        app.include_router(r, tags=["审计助理(R4)"])

    # ═══ §14. Round 5：EQCR 工作台 ═══
    from app.routers.eqcr import router as eqcr_router
    app.include_router(eqcr_router, tags=["eqcr"])

    # ═══ §15. Round 6：QC 规则定义管理 ═══
    from app.routers.qc_rules import router as qc_rules_router
    app.include_router(qc_rules_router, tags=["qc-rules"])

    # ═══ §16. Round 3：QC 审计日志合规抽查 ═══
    from app.routers.qc_audit_log_compliance import router as qc_alc_router
    app.include_router(qc_alc_router, tags=["qc-audit-log-compliance"])

    # ═══ §17. Round 3：QC 抽查 + 评级 + 案例库 + 年报 ═══
    from app.routers.qc_inspections import router as qc_insp_router
    from app.routers.qc_ratings import router as qc_rat_router
    from app.routers.qc_cases import router as qc_case_router
    from app.routers.qc_annual_reports import router as qc_ar_router

    app.include_router(qc_insp_router, tags=["qc-inspections"])
    app.include_router(qc_rat_router, tags=["qc-ratings"])
    app.include_router(qc_case_router, tags=["qc-cases"])
    app.include_router(qc_ar_router, tags=["qc-annual-reports"])

    # ═══ §18. Round 7：Stale 底稿汇总 ═══
    from app.routers.stale_summary import router as stale_summary_router
    app.include_router(stale_summary_router, tags=["stale"])

    # ═══ §19. Round 7：QC 本月应抽查 ═══
    from app.routers.qc_rotation_due import router as qc_rotation_due_router
    app.include_router(qc_rotation_due_router, tags=["qc-rotation"])

    # ═══ §20. Round 7：报表行关联底稿 ═══
    from app.routers.report_related_workpapers import router as rrw_router
    app.include_router(rrw_router, tags=["report-workpapers"])

    # ═══ §21. Round 8：风险摘要 ═══
    from app.routers.risk_summary import router as risk_summary_router
    app.include_router(risk_summary_router, tags=["risk-summary"])

    # ═══ §22. Round 8：附注行关联底稿 ═══
    from app.routers.note_related_workpapers import router as note_rw_router
    app.include_router(note_rw_router, tags=["note-workpapers"])

    # ═══ §23. 通知中心 ═══
    from app.routers.notifications import router as notifications_router
    app.include_router(notifications_router, tags=["notifications"])

    # ═══ §30. Enterprise Linkage: Presence + Conflict Guard ═══
    from app.routers.presence import router as presence_router
    from app.routers.conflict_guard import router as conflict_guard_router
    app.include_router(presence_router, tags=["presence"])
    app.include_router(conflict_guard_router, tags=["conflict-guard"])

    # ═══ §31. Enterprise Linkage: 联动查询 + 批量重分类 ═══
    from app.routers.linkage import router as linkage_router
    from app.routers.reclassification import router as reclassification_router
    app.include_router(linkage_router, tags=["linkage"])
    app.include_router(reclassification_router, tags=["reclassification"])

    # ═══ §32. Enterprise Linkage: 管理后台事件健康 ═══
    from app.routers.admin_event_health import router as admin_event_health_router
    app.include_router(admin_event_health_router, tags=["admin-event-health"])

    # ═══ §43. 全链路工作流编排 ═══
    from app.routers.chain_workflow import router as chain_workflow_router
    app.include_router(chain_workflow_router, tags=["chain-workflow"])

    # ═══ §51. Sprint 10：批量项目操作 ═══
    from app.routers.chain_workflow import batch_router as chain_batch_router
    app.include_router(chain_batch_router, tags=["chain-workflow-batch"])

    # ═══ §55. R10 Spec C：事件级联健康度 ═══
    from app.routers.event_cascade_health import router as event_cascade_health_router
    app.include_router(event_cascade_health_router, tags=["event-cascade"])

    # ═══ §60. global-linkage-bus ═══
    from app.routers.linkage_bus import router as linkage_bus_router
    app.include_router(linkage_bus_router, tags=["linkage-bus"])

    # ═══ §86. 合伙人仪表盘聚合端点 ═══
    from app.routers.dashboard_aggregator import router as dashboard_aggregator_router
    app.include_router(dashboard_aggregator_router, tags=["partner-dashboard"])

    # ═══ §87. 联动全景图 ═══
    from app.routers.linkage_panorama import router as linkage_panorama_router
    app.include_router(linkage_panorama_router, tags=["linkage-panorama"])

    # ═══ §89. QC 风险热力图 ═══
    from app.routers.qc_vr_heatmap import router as qc_vr_heatmap_router
    app.include_router(qc_vr_heatmap_router, tags=["QC风险热力图"])

    # ═══ §95. Phase 4 F3: EQCR 快照机制 ═══
    from app.routers.eqcr_snapshot import router as eqcr_snapshot_router
    app.include_router(eqcr_snapshot_router, tags=["eqcr-snapshot"])

    # ═══ §97. Phase 5 F1: 待办聚合 ═══
    from app.routers.my_todo import router as my_todo_router
    app.include_router(my_todo_router, tags=["my-todo"])

    # ═══ §98. Phase 5 F2: 跨循环断裂清单 ═══
    from app.routers.cross_cycle_breakage import router as cross_cycle_breakage_router
    app.include_router(cross_cycle_breakage_router, tags=["cross-cycle-breakage"])

    # ═══ §99. Phase 5 F3: 归档前完整性自检报告 ═══
    from app.routers.archive_completeness import router as archive_completeness_router
    app.include_router(archive_completeness_router, tags=["archive-completeness"])

    # ═══ §100. Phase 5 F7: 批量复核通过 ═══
    from app.routers.batch_review import router as batch_review_router
    app.include_router(batch_review_router, tags=["batch-review"])

    # ═══ §101. Phase 6 F4: 项目级权限端点 ═══
    from app.routers.project_permissions import router as project_permissions_router
    app.include_router(project_permissions_router, tags=["project-permissions"])

    # ═══ §101b. P0-4: 权限矩阵 API ═══
    from app.routers.permission_matrix import router as permission_matrix_router
    app.include_router(permission_matrix_router, tags=["permission-matrix"])

    # ═══ §102. Phase 6 F5: 待回复批注聚合 ═══
    from app.routers.my_reviews import router as my_reviews_router
    app.include_router(my_reviews_router, tags=["my-reviews"])

    # ═══ §103. Phase 6 F7: 经理项目群总览 ═══
    from app.routers.manager_dashboard import router as manager_dashboard_router
    app.include_router(manager_dashboard_router, tags=["manager-dashboard"])

    # ═══ §104. Phase 6 F8: 复核配置 API ═══
    from app.routers.review_config import router as review_config_router
    app.include_router(review_config_router, tags=["review-config"])

    # ═══ §105. Phase 7 F1: EQCR 结构化判断 ═══
    from app.routers.eqcr_judgment import router as eqcr_judgment_router
    app.include_router(eqcr_judgment_router, tags=["eqcr-judgment"])

    # ═══ §106. Phase 7 F2: EQCR 问题单 ═══
    from app.routers.eqcr_issues import router as eqcr_issues_router
    app.include_router(eqcr_issues_router, tags=["eqcr-issues"])

    # ═══ §107. Phase 7 F3: EQCR 趋势 ═══
    from app.routers.eqcr_trends import router as eqcr_trends_router
    app.include_router(eqcr_trends_router, tags=["eqcr-metrics"])

    # ═══ §108. Phase 7 F4: 复核意见模板库 ═══
    from app.routers.review_templates import router as review_templates_router
    app.include_router(review_templates_router, tags=["review-templates"])

    # ═══ §109. Phase 7 F5: QC 报告 Word 导出 ═══
    from app.routers.qc_report_export import router as qc_report_export_router
    app.include_router(qc_report_export_router, tags=["qc-report"])

    # ═══ §110. Phase 7 F6: VR 规则覆盖度 ═══
    from app.routers.vr_coverage import router as vr_coverage_router
    app.include_router(vr_coverage_router, tags=["qc-vr-coverage"])

    # ═══ §111. Phase 7 F7: 工时填报 CRUD ═══
    from app.routers.workhour_entries import router as workhour_entries_router
    app.include_router(workhour_entries_router, tags=["workhours-entries"])

    # ═══ §112. Phase 7 F8: 工时预算对比 ═══
    from app.routers.workhour_budget import router as workhour_budget_router
    app.include_router(workhour_budget_router, tags=["workhours-budget"])

    # ═══ §113. Phase 7 F9: 复核分派推荐 ═══
    from app.routers.review_recommend import router as review_recommend_router
    app.include_router(review_recommend_router, tags=["review-recommend"])

    # ═══ §114. Phase 7 F10: 工时审批关联 ═══
    from app.routers.workhour_approval import router as workhour_approval_router
    app.include_router(workhour_approval_router, tags=["workhours-approval"])

    # ═══ §115. Phase 7 F12: 多项目紧急度评分 ═══
    from app.routers.partner_urgency import router as partner_urgency_router
    app.include_router(partner_urgency_router, tags=["partner-urgency"])

    # ═══ §120. P1: 角色作业台 ═══
    from app.routers.role_workbench import router as role_workbench_router
    app.include_router(role_workbench_router, tags=["role-workbench"])

    # ═══ §121. P2: 临时授权 ═══
    from app.routers.temporary_grants import router as temporary_grants_router
    app.include_router(temporary_grants_router, tags=["temporary-grants"])

    # ═══ §116. proposal-remaining-18 C-3: 批量导出 SSE 进度推送 ═══
    from app.routers.batch_export_progress import (
        router as batch_export_progress_router,
        download_router as batch_export_download_router,
    )
    app.include_router(batch_export_progress_router, tags=["batch-export-progress"])
    app.include_router(batch_export_download_router, tags=["batch-export-progress"])
