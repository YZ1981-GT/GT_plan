"""路由注册表 — 按业务域分组

将 main.py 中 90+ 个平铺的 include_router 收口到此模块，
按 8 个业务域分组注册，便于维护和查找。

路由前缀规范（IMPORTANT）：
  - 标准做法：路由器内部 prefix 只声明业务路径（如 prefix="/gate"），
    本文件在 include_router 时统一添加 prefix="/api"
  - 最终路径 = /api + 路由器内部路径 + 端点路径

已知例外（ADR — Architecture Decision Record）：
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ 例外 1: dashboard.py                                                    │
  │   内部 prefix="/api/dashboard"，注册时不加额外前缀                       │
  │   原因：历史遗留，dashboard 路由在 Phase 0 直接定义了完整路径，           │
  │         修改会破坏前端已部署的 API 调用。                                 │
  │   影响：仅此一个路由文件，不影响其他模块。                               │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ 例外 2: /wopi 路由                                                      │
  │   注册时 prefix="/wopi"，不加 /api 前缀                                  │
  │   原因：WOPI 协议规范要求固定路径格式 /wopi/files/{file_id}，            │
  │         Office Online Server 硬编码此路径，不可更改。                     │
  │   影响：仅 WOPI 集成，与业务 API 完全隔离。                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ 例外 3: /api/version                                                    │
  │   直接定义在 main.py（版本探针），不经过 router_registry                  │
  │   原因：极简端点（3 行），无需独立路由文件。                              │
  │   影响：无。                                                             │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ 例外 4: §13-§17 的 R3/R4/R5/R6 路由                                     │
  │   这些路由器内部已含完整 /api 前缀，注册时不加额外前缀                   │
  │   原因：后期 Round 开发时为避免与早期路由冲突，采用自包含前缀模式。       │
  │   影响：新增 Round 路由应遵循此模式（内部含 /api，注册不加前缀）。        │
  └─────────────────────────────────────────────────────────────────────────┘

变更日志：
  - 2026-05-07: 添加 ADR 注释，文档化所有例外情况
  - 2026-05-06: R6 新增 §15 qc_rules_router
  - 2026-05-05: R5 新增 §14 eqcr_router
"""
from fastapi import APIRouter, FastAPI


def register_all_routers(app: FastAPI) -> None:
    """一次性注册所有路由，按业务域分组"""

    # ═══ 1. 基础设施（认证/健康/WOPI） ═══
    from app.api.auth import router as auth_router
    from app.api.health import router as health_router
    from app.api.users import router as users_router
    from app.api.wopi import router as wopi_router

    app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
    app.include_router(users_router, prefix="/api/users", tags=["用户"])
    app.include_router(health_router, prefix="/api", tags=["健康检查"])
    app.include_router(wopi_router, prefix="/wopi", tags=["WOPI"])

    # ═══ 2. 项目与向导 ═══
    from app.routers.project_wizard import router as project_wizard_router
    from app.routers.account_chart import router as account_chart_router
    from app.routers.mapping import router as mapping_router
    from app.routers.report_line_mapping import router as rlm_router
    from app.routers.data_import import router as data_import_router
    from app.routers.data_lifecycle import router as data_lifecycle_router
    from app.routers.continuous_audit import router as continuous_audit_router
    from app.routers.ledger_datasets import router as ledger_datasets_router
    from app.routers.dataset_force_unbind import router as dataset_force_unbind_router

    for r in [project_wizard_router, account_chart_router, mapping_router,
              rlm_router, data_import_router, data_lifecycle_router,
              continuous_audit_router, ledger_datasets_router,
              dataset_force_unbind_router]:
        app.include_router(r, tags=["项目与数据"])

    # 导入智能增强
    from app.routers.import_intelligence import router as import_intel_router
    app.include_router(import_intel_router, tags=["项目与数据"])

    # 统一导入模板
    from app.routers.import_templates import router as import_templates_router
    app.include_router(import_templates_router)

    # ═══ 3. 查账与试算（四表穿透/试算表/调整/重要性/错报） ═══
    from app.routers.drilldown import router as drilldown_router
    from app.routers.ledger_penetration import router as ledger_router
    from app.routers.trial_balance import router as tb_router
    from app.routers.adjustments import router as adj_router
    from app.routers.materiality import router as mat_router
    from app.routers.misstatements import router as mis_router
    from app.routers.events import router as events_router
    from app.routers.tb_sync import router as tb_sync_router
    from app.routers.data_validation import router as dv_router
    from app.routers.consistency import router as consistency_router

    for r in [drilldown_router, ledger_router, tb_router, adj_router,
              mat_router, mis_router, events_router, tb_sync_router,
              dv_router, consistency_router]:
        app.include_router(r, tags=["查账与试算"])

    # ═══ 4. 报表与附注 ═══
    from app.routers.report_config import router as rc_router
    from app.routers.reports import router as reports_router
    from app.routers.cfs_worksheet import router as cfs_router
    from app.routers.disclosure_notes import router as dn_router
    from app.routers.audit_report import router as ar_router
    from app.routers.export import router as export_router
    from app.routers.note_templates import router as nt_router
    from app.routers.note_wp_mapping import router as nwm_router
    from app.routers.note_trim import router as ntr_router
    from app.routers.note_ai import router as nai_router
    from app.routers.report_trace import router as rt_router

    # Phase 13: Word 导出
    from app.routers.word_export import router as word_export_router
    from app.routers.report_mapping import router as report_mapping_router

    for r in [rc_router, reports_router, cfs_router, dn_router, ar_router,
              export_router, nt_router, nwm_router, ntr_router, nai_router,
              rt_router, word_export_router, report_mapping_router]:
        app.include_router(r, tags=["报表与附注"])

    # ═══ 5. 底稿管理 ═══
    from app.routers.formula import router as formula_router
    from app.routers.wp_template import router as wpt_router
    from app.routers.working_paper import router as wp_router
    from app.routers.qc import router as qc_router
    from app.routers.wp_review import router as wpr_router
    from app.routers.wp_mapping import router as wpm_router
    from app.routers.wp_progress import router as wpp_router
    from app.routers.wp_ai import router as wpai_router
    from app.routers.wp_storage import router as wps_router
    from app.routers.wp_download import router as wpd_router
    from app.routers.wp_chat import router as wpc_router
    from app.routers.sampling import router as samp_router
    from app.routers.sampling_enhanced import router as sampe_router
    from app.routers.workpaper_summary import router as wsum_router
    from app.routers.process_record import router as pr_router
    from app.routers.review_conversations import router as rconv_router
    from app.routers.annotations import router as ann_router

    # Phase 12
    from app.routers.wp_explanation import router as wpexpl_router
    from app.routers.background_jobs import router as bgjob_router

    # 底稿通用数据规则
    from app.routers.wp_data_rules import router as wpdr_router
    # 自定义取数+溯源
    from app.routers.data_fetch_custom import router as dfc_router
    # Excel↔HTML互转
    from app.routers.excel_html import router as exhtml_router

    for r in [formula_router, wpt_router, wp_router, qc_router, wpr_router,
              wpm_router, wpp_router, wpai_router, wps_router, wpd_router,
              wpc_router, samp_router, sampe_router, wsum_router, pr_router,
              rconv_router, ann_router, wpexpl_router, bgjob_router, wpdr_router,
              dfc_router, exhtml_router]:
        app.include_router(r, tags=["底稿管理"])

    # 底稿 AI 内容确认
    from app.routers.wp_ai_confirm import router as wp_ai_confirm_router
    app.include_router(wp_ai_confirm_router, tags=["底稿管理"])

    # 底稿三式联动
    from app.routers.wp_structure import router as wpstruct_router
    app.include_router(wpstruct_router, tags=["底稿管理"])

    # 底稿操作手册
    from app.routers.wp_manuals import router as wpmanual_router
    app.include_router(wpmanual_router, tags=["底稿管理"])

    # 底稿精细化规则
    from app.routers.wp_fine_rules import router as wpfine_router
    app.include_router(wpfine_router, tags=["底稿管理"])

    # 底稿依赖关系（B→C→D联动）
    from app.routers.wp_dependencies import router as wpdep_router
    app.include_router(wpdep_router, tags=["底稿管理"])

    # 账龄分析
    from app.routers.aging_analysis import router as aging_router
    app.include_router(aging_router, tags=["底稿管理"])

    # ═══ 6. 合并报表 ═══
    from app.routers.consolidation import router as consol_router
    from app.routers.consol_scope import router as cs_router
    from app.routers.consol_trial import router as ct_router
    from app.routers.internal_trade import router as it_router
    from app.routers.component_auditor import router as ca_router
    from app.routers.goodwill import router as gw_router
    from app.routers.forex import router as fx_router
    from app.routers.minority_interest import router as mi_router
    from app.routers.consol_notes import router as cn_router
    from app.routers.consol_report import router as cr_router
    from app.routers.consol_worksheet import router as cw_router
    from app.routers.consol_worksheet_data import router as cwd_router
    from app.routers.consol_note_sections import router as cns_router
    from app.routers.consol_cell_comments import router as ccc_router
    from app.routers.account_note_mapping import router as anm_router
    from app.routers.formula_audit_log import router as fal_router
    from app.routers.custom_query import router as cq_router

    for r in [consol_router, cs_router, ct_router, it_router, ca_router,
              gw_router, fx_router, mi_router, cn_router, cr_router,
              cw_router, cwd_router, cns_router, ccc_router, anm_router, fal_router, cq_router]:
        app.include_router(r, tags=["合并报表"])

    # ═══ 7. 团队与看板 ═══
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

    for r in [staff_router, assign_router, wh_router, wh_list_router, dash_router,
              pmd_router, qcd_router, pd_router, rc2_router, proc_router,
              se_router, forum_router]:
        app.include_router(r, tags=["团队与看板"])

    # 角色AI辅助
    from app.routers.role_ai_features import router as rai_router
    app.include_router(rai_router, tags=["团队与看板"])

    # ═══ 8. 系统管理与扩展 ═══
    from app.routers.gt_coding import router as gtc_router
    from app.routers.t_accounts import router as ta_router
    from app.routers.metabase import router as mb_router
    from app.routers.attachments import router as att_router
    from app.routers.custom_templates import router as cust_router
    from app.routers.accounting_standards import router as as_router
    from app.routers.i18n import router as i18n_router
    from app.routers.audit_types import router as at_router
    from app.routers.signatures import router as sig_router
    from app.routers.ai_plugins import router as aip_router
    from app.routers.regulatory import router as reg_router
    from app.routers.ai_unified import router as aiu_router
    from app.routers.ai_models import router as aim_router
    from app.routers.recycle_bin import router as rb_router
    from app.routers.private_storage import router as ps_router
    from app.routers.knowledge_base import router as kb_router
    from app.routers.knowledge_folders import router as kf_router
    from app.routers.template_library import router as tl_router
    from app.routers.feature_flags import router as ff_router
    from app.routers.task_center import router as tc_router
    from app.routers.performance import router as perf_router
    from app.routers.security import router as sec_router
    from app.routers.system_settings import router as ss_router
    from app.routers.shared_config import router as sc_router

    for r in [gtc_router, ta_router, mb_router, att_router, cust_router,
              as_router, i18n_router, at_router, sig_router, aip_router,
              reg_router, aiu_router, aim_router, rb_router, ps_router,
              kb_router, kf_router, tl_router, ff_router, tc_router, perf_router, sec_router,
              ss_router, sc_router]:
        app.include_router(r, tags=["系统管理"])

    # 地址坐标注册表
    from app.routers.address_registry import router as addr_router
    app.include_router(addr_router, tags=["系统管理"])

    # 系统字典（枚举字典集中管理）
    from app.routers.system_dicts import router as sdict_router
    app.include_router(sdict_router, tags=["系统管理"])

    # ═══ 9. Phase 14: 门禁引擎与治理 ═══
    from app.routers.gate import router as gate_router
    from app.routers.trace import router as trace_router
    from app.routers.sod import router as sod_router

    for r in [gate_router, trace_router, sod_router]:
        app.include_router(r, prefix="/api", tags=["门禁与治理"])

    # Phase 14: 门禁规则在 main.py lifespan 中注册，此处不重复调用

    # ═══ 10. Phase 15: 任务树与事件编排 ═══
    from app.routers.task_tree import router as task_tree_router
    from app.routers.issues import router as issues_router
    from app.routers.task_events import router as task_events_router

    for r in [task_tree_router, issues_router, task_events_router]:
        app.include_router(r, prefix="/api", tags=["任务树与编排"])

    # Note: Phase 15 事件处理器注册已统一到 main.py lifespan 中

    # ═══ 11. Phase 16: 取证包与版本链 ═══
    from app.routers.version_line import router as version_line_router
    from app.routers.offline_conflicts import router as conflict_router
    from app.routers.consistency_replay import router as consistency_replay_router
    from app.routers.export_integrity import router as export_integrity_router

    for r in [version_line_router, conflict_router, consistency_replay_router,
              export_integrity_router]:
        app.include_router(r, prefix="/api", tags=["取证与版本链"])

    # ═══ 12. 协作管理（PBC 清单 / 函证管理） ═══
    from app.routers.pbc import router as pbc_router
    from app.routers.confirmations import router as confirmations_router

    app.include_router(pbc_router, prefix="/api", tags=["PBC清单"])
    app.include_router(confirmations_router, prefix="/api", tags=["函证管理"])

    # ═══ 12. 协作管理（PBC 清单 / 函证管理） ═══
    from app.routers.pbc import router as pbc_router
    from app.routers.confirmations import router as confirmations_router

    app.include_router(pbc_router, prefix="/api", tags=["PBC清单"])
    app.include_router(confirmations_router, prefix="/api", tags=["函证管理"])

    # ═══ 13. Round 4：审计助理增强 ═══
    # R4 路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。
    from app.routers.workpaper_requirements import router as wpreq_router
    from app.routers.workpaper_prior_year import router as wppy_router
    from app.routers.workpaper_html_preview import router as wphp_router
    from app.routers.editing_lock import router as editlock_router
    from app.routers.ocr_fields import router as ocrf_router
    from app.routers.penetrate_by_amount import router as pba_router

    for r in [wpreq_router, wppy_router, wphp_router, editlock_router, ocrf_router, pba_router]:
        app.include_router(r, tags=["审计助理(R4)"])

    # ═══ 14. Round 5：EQCR 工作台 ═══
    # EQCR 路由包内部已声明 prefix="/api/eqcr"，注册时不加额外前缀。
    from app.routers.eqcr import router as eqcr_router
    app.include_router(eqcr_router, tags=["eqcr"])

    # ═══ 15. Round 6：QC 规则定义管理 ═══
    # qc_rules 路由内部已声明 prefix="/api/qc/rules"，注册时不加额外前缀。
    from app.routers.qc_rules import router as qc_rules_router
    app.include_router(qc_rules_router, tags=["qc-rules"])

    # ═══ 16. Round 3：QC 审计日志合规抽查 ═══
    # qc_audit_log_compliance 路由内部已声明 prefix="/api/qc/audit-log-compliance"
    from app.routers.qc_audit_log_compliance import router as qc_alc_router
    app.include_router(qc_alc_router, tags=["qc-audit-log-compliance"])

    # ═══ 18. Round 7：Stale 底稿汇总 ═══
    # stale_summary 路由内部已声明 prefix="/api/projects/{project_id}"，注册时不加额外前缀。
    from app.routers.stale_summary import router as stale_summary_router
    app.include_router(stale_summary_router, tags=["stale"])

    # ═══ 19. Round 7：QC 本月应抽查 ═══
    from app.routers.qc_rotation_due import router as qc_rotation_due_router
    app.include_router(qc_rotation_due_router, tags=["qc-rotation"])

    # ═══ 20. Round 7：报表行关联底稿 ═══
    from app.routers.report_related_workpapers import router as rrw_router
    app.include_router(rrw_router, tags=["report-workpapers"])

    # ═══ 21. Round 8：风险摘要（签字决策面板用） ═══
    # risk_summary 路由内部已声明 prefix="/api/projects/{project_id}"，注册时不加额外前缀。
    from app.routers.risk_summary import router as risk_summary_router
    app.include_router(risk_summary_router, tags=["risk-summary"])

    # ═══ 22. Round 8：附注行关联底稿（附注→底稿穿透） ═══
    # note_related_workpapers 路由内部已声明 prefix="/api/notes"，注册时不加额外前缀。
    from app.routers.note_related_workpapers import router as note_rw_router
    app.include_router(note_rw_router, tags=["note-workpapers"])

    # ═══ 17. Round 3：QC 抽查 + 评级 + 案例库 + 年报 ═══
    # 以下 4 个路由内部已声明完整 prefix，注册时不加额外前缀。
    from app.routers.qc_inspections import router as qc_insp_router
    from app.routers.qc_ratings import router as qc_rat_router
    from app.routers.qc_cases import router as qc_case_router
    from app.routers.qc_annual_reports import router as qc_ar_router

    app.include_router(qc_insp_router, tags=["qc-inspections"])
    app.include_router(qc_rat_router, tags=["qc-ratings"])
    app.include_router(qc_case_router, tags=["qc-cases"])
    app.include_router(qc_ar_router, tags=["qc-annual-reports"])

    # ═══ 23. 通知中心 ═══
    # notifications 路由内部已声明 prefix="/api/notifications"，注册时不加额外前缀。
    from app.routers.notifications import router as notifications_router
    app.include_router(notifications_router, tags=["notifications"])

    # ═══ 24. 账表导入 v2（ledger-import-unification） ═══
    # 路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。
    from app.routers.ledger_import_v2 import router as ledger_import_v2_router
    from app.routers.ledger_raw_extra import router as ledger_raw_extra_router
    app.include_router(ledger_import_v2_router, tags=["ledger-import-v2"])
    app.include_router(ledger_raw_extra_router, tags=["ledger-import-v2"])

    # ═══ 25. 账表数据管理（查询/删除/增量追加） ═══
    # 路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。
    from app.routers.ledger_data import router as ledger_data_router
    app.include_router(ledger_data_router, tags=["ledger-data"])

    # ═══ 26. Sprint 10 F43: 账表导入子系统健康检查 ═══
    # 路由内部已声明 prefix="/api/health"，注册时不加额外前缀。
    from app.routers.ledger_import_health import router as ledger_health_router
    app.include_router(ledger_health_router, tags=["health"])

    # ═══ 27. Sprint 8 F48: 校验规则说明文档 ═══
    # 路由内部已声明 prefix="/api/ledger-import/validation-rules"，注册时不加额外前缀。
    from app.routers.validation_rules import router as validation_rules_router
    app.include_router(validation_rules_router, tags=["ledger-import-validation-rules"])

    # ═══ 28. E2E 业务流程：数据质量检查 ═══
    # 路由内部已声明 prefix="/api/projects/{project_id}/data-quality"，注册时不加额外前缀。
    from app.routers.data_quality import router as data_quality_router
    app.include_router(data_quality_router, tags=["data-quality"])

    # ═══ 29. E2E 业务流程：工作流进度 ═══
    # 路由内部已声明 prefix="/api/projects/{project_id}/workflow-status"，注册时不加额外前缀。
    from app.routers.workflow_status import router as workflow_status_router
    app.include_router(workflow_status_router, tags=["workflow"])

    # ═══ 30. Enterprise Linkage: Presence + Conflict Guard ═══
    # 路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。
    from app.routers.presence import router as presence_router
    from app.routers.conflict_guard import router as conflict_guard_router
    app.include_router(presence_router, tags=["presence"])
    app.include_router(conflict_guard_router, tags=["conflict-guard"])

    # ═══ 31. Enterprise Linkage: 联动查询 + 批量重分类 ═══
    # 路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。
    from app.routers.linkage import router as linkage_router
    from app.routers.reclassification import router as reclassification_router
    app.include_router(linkage_router, tags=["linkage"])
    app.include_router(reclassification_router, tags=["reclassification"])

    # ═══ 32. Enterprise Linkage: 管理后台事件健康 ═══
    # 路由内部已声明 prefix="/api/admin/event-health"，注册时不加额外前缀。
    from app.routers.admin_event_health import router as admin_event_health_router
    app.include_router(admin_event_health_router, tags=["admin-event-health"])
