"""系统管理与基础设施路由注册

覆盖原 router_registry.py 中以下分组：
  §1  基础设施（认证/健康/WOPI）
  §2  项目与向导
  §3  查账与试算（四表穿透/试算表/调整/重要性/错报）
  §6  合并报表
  §8  系统管理与扩展
  §24 账表导入 v2
  §25 账表数据管理
  §26 Sprint 10 F43: 账表导入子系统健康检查
  §27 Sprint 8 F48: 校验规则说明文档
  §28 E2E 业务流程：数据质量检查
  §29 E2E 业务流程：工作流进度
  §53 Sprint 11：项目级配置中心
  §54 template-library-coordination：模板库管理
  §59 Address Registry V2
  §92 Redis 健康检查（§92 编号复用，实际为 health_redis）
  §96 Redis 健康检查（Phase 4 F5）
  §118 proposal-remaining-18 AT-2: Office 文件在线预览（LibreOffice）
  §120 MT-8 日志集中查看（admin only）
"""
from fastapi import FastAPI


def register_system_routers(app: FastAPI) -> None:
    """注册系统管理与基础设施相关路由"""

    # ═══ §1. 基础设施（认证/健康/WOPI） ═══
    from app.api.auth import router as auth_router
    from app.api.health import router as health_router
    from app.api.users import router as users_router
    from app.api.wopi import router as wopi_router

    app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
    app.include_router(users_router, prefix="/api/users", tags=["用户"])
    app.include_router(health_router, prefix="/api", tags=["健康检查"])
    app.include_router(wopi_router, prefix="/wopi", tags=["WOPI"])

    # ═══ §103. Phase 6 F6: 二次密码验证 ═══
    from app.routers.password_confirm import router as password_confirm_router
    app.include_router(password_confirm_router, tags=["auth"])

    # ═══ §2. 项目与向导 ═══
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

    # ═══ §3. 查账与试算 ═══
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

    # ═══ §6. 合并报表 ═══
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
    from app.routers.query_builder import router as qb_router

    for r in [consol_router, cs_router, ct_router, it_router, ca_router,
              gw_router, fx_router, mi_router, cn_router, cr_router,
              cw_router, cwd_router, cns_router, ccc_router, anm_router, fal_router, cq_router, qb_router]:
        app.include_router(r, tags=["合并报表"])

    # ═══ §8. 系统管理与扩展 ═══
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

    # ═══ §24. 账表导入 v2 ═══
    from app.routers.ledger_import_v2 import router as ledger_import_v2_router
    from app.routers.ledger_raw_extra import router as ledger_raw_extra_router
    app.include_router(ledger_import_v2_router, tags=["ledger-import-v2"])
    app.include_router(ledger_raw_extra_router, tags=["ledger-import-v2"])

    # ═══ §25. 账表数据管理 ═══
    from app.routers.ledger_data import router as ledger_data_router
    app.include_router(ledger_data_router, tags=["ledger-data"])

    # ═══ §26. Sprint 10 F43: 账表导入子系统健康检查 ═══
    from app.routers.ledger_import_health import router as ledger_health_router
    app.include_router(ledger_health_router, tags=["health"])

    # §96 Redis 健康检查
    from app.routers.health_redis import router as health_redis_router
    app.include_router(health_redis_router, tags=["health"])

    # ═══ §27. Sprint 8 F48: 校验规则说明文档 ═══
    from app.routers.validation_rules import router as validation_rules_router
    app.include_router(validation_rules_router, tags=["ledger-import-validation-rules"])

    # ═══ §28. E2E 业务流程：数据质量检查 ═══
    from app.routers.data_quality import router as data_quality_router
    app.include_router(data_quality_router, tags=["data-quality"])

    # ═══ §29. E2E 业务流程：工作流进度 ═══
    from app.routers.workflow_status import router as workflow_status_router
    app.include_router(workflow_status_router, tags=["workflow"])

    # ═══ §53. Sprint 11：项目级配置中心 ═══
    from app.routers.project_config import router as project_config_router
    app.include_router(project_config_router, tags=["project-config"])

    # ═══ §54. template-library-coordination：模板库管理 ═══
    from app.routers.template_library_mgmt import router as template_library_mgmt_router
    app.include_router(template_library_mgmt_router, tags=["template-library-mgmt"])

    # ═══ §59. Address Registry V2 ═══
    from app.routers.address_registry_v2 import router as address_registry_v2_router
    app.include_router(address_registry_v2_router, tags=["address-registry-v2"])

    # ═══ §118. proposal-remaining-18 AT-2: Office 文件在线预览（LibreOffice 转 PDF） ═══
    from app.routers.office_preview import router as office_preview_router
    app.include_router(office_preview_router, tags=["office-preview"])

    # ═══ §120. MT-8 日志集中查看（admin only） ═══
    from app.routers.logs_viewer import router as logs_viewer_router
    app.include_router(logs_viewer_router, tags=["admin-logs"])
