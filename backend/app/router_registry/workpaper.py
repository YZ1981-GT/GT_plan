"""底稿管理路由注册

覆盖原 router_registry.py 中以下分组：
  §5  底稿管理（formula/template/working_paper/qc/review/mapping/progress/ai/storage/...）
  §33 底稿深度优化：程序管理与裁剪
  §34 底稿深度优化：跨科目校验
  §35 底稿深度优化：证据链管理
  §36 Sprint 10：底稿复核批注
  §37 Sprint 10：底稿批量操作
  §38 Sprint 11：底稿健康监控 + 全文搜索
  §39 Sprint 11：EQCR 充分性评价
  §40 底稿模板元数据
  §41 底稿模板文件（xlsx 加载）
  §42 底稿模板下载
  §56 复核状态聚合端点
  §57 程序步骤→Sheet映射 + 跨模块引用 + 校验规则 + stale传播链
  §58 项目信息预填充上下文
  §61 用户自定义公式编辑器
  §62 前置底稿状态 + 程序状态 + 程序分类
  §63 review-records 全局列表
  §85 程序适用性裁剪
  §88 全局搜索
  §90 底稿批量状态变更
  §91 Prefill 预览+应用
  §119 proposal-remaining-18 S-4：历史版本搜索
"""
from fastapi import FastAPI


def register_workpaper_routers(app: FastAPI) -> None:
    """注册底稿管理相关路由"""

    # ═══ §5. 底稿管理 ═══
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
    from app.routers.wp_explanation import router as wpexpl_router
    from app.routers.background_jobs import router as bgjob_router
    from app.routers.wp_data_rules import router as wpdr_router
    from app.routers.data_fetch_custom import router as dfc_router
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

    # ═══ §33. 底稿深度优化：程序管理与裁剪 ═══
    from app.routers.wp_procedures import router as wp_procedures_router
    app.include_router(wp_procedures_router, tags=["workpaper-procedures"])

    # ═══ §34. 底稿深度优化：跨科目校验 ═══
    from app.routers.wp_cross_check import router as wp_cross_check_router
    app.include_router(wp_cross_check_router, tags=["cross-check"])

    # ═══ §35. 底稿深度优化：证据链管理 ═══
    from app.routers.wp_evidence import router as wp_evidence_router
    app.include_router(wp_evidence_router, tags=["workpaper-evidence"])

    # ═══ §36. Sprint 10：底稿复核批注 ═══
    from app.routers.wp_cell_annotations import router as wp_annotations_router
    app.include_router(wp_annotations_router, tags=["cell-annotations"])

    # ═══ §37. Sprint 10：底稿批量操作 ═══
    from app.routers.wp_batch_ops import router as wp_batch_ops_router
    app.include_router(wp_batch_ops_router, tags=["batch-ops"])

    # ═══ §38. Sprint 11：底稿健康监控 + 全文搜索 ═══
    from app.routers.wp_health_dashboard import router as wp_health_router
    from app.routers.wp_search import router as wp_search_router
    app.include_router(wp_health_router, tags=["workpaper-health"])
    app.include_router(wp_search_router, tags=["workpaper-search"])

    # ═══ §39. Sprint 11：EQCR 充分性评价 ═══
    from app.routers.wp_eqcr_evaluation import router as wp_eqcr_eval_router
    app.include_router(wp_eqcr_eval_router, tags=["eqcr-evaluation"])

    # ═══ §40. 底稿模板元数据 ═══
    from app.routers.wp_template_metadata import router as wp_tmpl_meta_router
    app.include_router(wp_tmpl_meta_router, tags=["wp-template-metadata"])

    # ═══ §41. 底稿模板文件（xlsx 加载） ═══
    from app.routers.wp_template_files import router as wp_tmpl_files_router
    app.include_router(wp_tmpl_files_router, tags=["wp-template-files"])

    # ═══ §42. 底稿模板下载（原始模板文件） ═══
    from app.routers.wp_template_download import router as wp_tmpl_dl_router
    app.include_router(wp_tmpl_dl_router, tags=["wp-template-download"])

    # ═══ §56. 复核状态聚合端点 ═══
    from app.routers.wp_review_status import router as wp_review_status_router
    app.include_router(wp_review_status_router, tags=["workpaper-review-status"])

    # ═══ §57. 程序步骤→Sheet映射 + 跨模块引用 + 校验规则 + stale传播链 ═══
    from app.routers.wp_step_mapping import router as wp_step_mapping_router
    app.include_router(wp_step_mapping_router, tags=["workpaper-step-mapping"])

    # ═══ §58. 项目信息预填充上下文 ═══
    from app.routers.wp_prefill_context import router as wp_prefill_context_router
    app.include_router(wp_prefill_context_router, tags=["workpaper-prefill"])

    # ═══ §61. 用户自定义公式编辑器 ═══
    from app.routers.wp_user_formulas import router as wp_user_formulas_router
    app.include_router(wp_user_formulas_router, tags=["workpaper-user-formulas"])

    # ═══ §62. 前置底稿状态 + 程序状态 + 程序分类 ═══
    from app.routers.wp_prerequisite_status import router as wp_prerequisite_status_router
    app.include_router(wp_prerequisite_status_router, tags=["workpaper-prerequisite-status"])

    from app.routers.wp_procedure_status import router as wp_procedure_status_router
    app.include_router(wp_procedure_status_router, tags=["workpaper-procedure-status"])

    from app.routers.wp_procedure_status import categories_router as wp_procedure_categories_router
    app.include_router(wp_procedure_categories_router, tags=["workpaper-procedure-categories"])

    # ═══ §63. review-records 全局列表 ═══
    from app.routers.review_records_global import router as review_records_global_router
    app.include_router(review_records_global_router, tags=["review-records"])

    # ═══ §85. 程序适用性裁剪 ═══
    from app.routers.wp_procedure_trim import router as wp_procedure_trim_router
    app.include_router(wp_procedure_trim_router, tags=["workpaper-procedure-trim"])

    # ═══ §88. 全局搜索 ═══
    from app.routers.global_search import router as global_search_router
    app.include_router(global_search_router, tags=["全局搜索"])

    # ═══ §90. 底稿批量状态变更 ═══
    from app.routers.workpaper_batch_status import router as wp_batch_status_router
    app.include_router(wp_batch_status_router, tags=["底稿批量操作"])

    # ═══ §91. Prefill 预览+应用 ═══
    from app.routers.wp_prefill_preview import router as wp_prefill_preview_router
    app.include_router(wp_prefill_preview_router, tags=["底稿Prefill预览"])

    # ═══ §119. proposal-remaining-18 S-4：历史版本搜索 ═══
    from app.routers.wp_version_search import router as wp_version_search_router
    app.include_router(wp_version_search_router, tags=["wp-version-search"])
