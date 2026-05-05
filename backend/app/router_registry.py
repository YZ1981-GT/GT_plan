"""路由注册表 — 按业务域分组

将 main.py 中 90+ 个平铺的 include_router 收口到此模块，
按 7 个业务域分组注册，便于维护和查找。
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

    for r in [project_wizard_router, account_chart_router, mapping_router,
              rlm_router, data_import_router, data_lifecycle_router,
              continuous_audit_router, ledger_datasets_router]:
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
    from app.routers.dashboard import router as dash_router
    from app.routers.pm_dashboard import router as pmd_router
    from app.routers.qc_dashboard import router as qcd_router
    from app.routers.partner_dashboard import router as pd_router
    from app.routers.role_context import router as rc2_router
    from app.routers.procedures import router as proc_router
    from app.routers.subsequent_events import router as se_router
    from app.routers.forum import router as forum_router

    for r in [staff_router, assign_router, wh_router, dash_router,
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
        app.include_router(r, prefix="/api" if not hasattr(r, 'prefix') or not r.prefix.startswith('/api') else "", tags=["门禁与治理"])

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
